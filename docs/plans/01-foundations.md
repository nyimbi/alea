# 01 — Foundations

**Stage 0.** Nothing in the platform can be trusted until this exists, and every
item here is cheaper to build now than to retrofit. Budget: **one week.**

Deliverables: config system, provenance, country registry, data lake, CI with
canaries, DVC, CLI.

---

## 1. Config system

### 1.1 Why Pydantic and not YAML access

The specification passes config through Snakemake `params` and reads raw YAML
keys. That means a typo (`plannning_horizons`) is discovered at the point of use
— potentially five hours into a solve. A typed config fails at load, in under a
second, naming the key and the file.

### 1.2 Structure

```
src/alea/config/
├── __init__.py
├── models.py        # every config model
├── loader.py        # precedence, overlay, interpolation
└── paths.py         # repo-root discovery, artefact path construction
```

### 1.3 Base model

Every config model inherits this. `extra="forbid"` is the whole point.

```python
# src/alea/config/models.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

class AleaConfig(BaseModel):
	"""Base for every config model.

	``extra='forbid'`` is not stylistic: an unknown key is a typo, and a typo
	that reaches a solve costs hours. Fail at load.
	"""
	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		frozen=True,
	)
```

### 1.4 Precedence

Highest wins:

1. CLI flag (`--set solve.solver=gurobi`)
2. Scenario overlay (`config/scenarios/<name>.yaml`)
3. Environment-specific file (`config/config.kenya.yaml`)
4. Default file (`config/config.default.yaml`)
5. Model defaults (the `Field(default=...)` values)

**Deep merge, not shallow replace.** A scenario that sets
`solve.solver: gurobi` must not delete the rest of the `solve` block. Merging is
recursive over dicts; lists replace wholesale (a scenario that sets a list means
*that* list).

### 1.5 Loader

```python
# src/alea/config/loader.py
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from alea.config.models import Config

def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
	"""Recursive merge. Dicts merge; everything else replaces.

	A shallow merge here would make a scenario that sets one key silently
	discard its siblings, which is the failure mode that produces a solve with
	the right carbon price and the default planning horizons.
	"""
	out = dict(base)
	for key, value in overlay.items():
		if key in out and isinstance(out[key], dict) and isinstance(value, dict):
			out[key] = _deep_merge(out[key], value)
		else:
			out[key] = value
	return out

def load_config(
	path: Path | None = None,
	scenario: str | None = None,
	overrides: dict[str, Any] | None = None,
) -> Config:
	"""Load, merge, and validate configuration."""
	layers: list[dict[str, Any]] = [_read(DEFAULT_PATH)]
	if path is not None:
		layers.append(_read(path))
	if scenario is not None:
		layers.append(_read(SCENARIOS_DIR / f"{scenario}.yaml"))
	merged = layers[0]
	for layer in layers[1:]:
		merged = _deep_merge(merged, layer)
	if overrides:
		merged = _deep_merge(merged, overrides)
	return Config.model_validate(merged)
```

### 1.6 The config model set

One model per concern, composed into a root `Config`. Each field carries the
unit in its name or its docstring — `capacity_mw`, `cost_usd_per_mwh`,
`horizon_years`.

```python
class ScenarioConfig(AleaConfig):
	countries: list[CountryIso]
	clusters: list[int]
	planning_horizons: list[int]
	base_year: int = 2025

	@model_validator(mode="after")
	def _horizons_ascend(self) -> ScenarioConfig:
		if self.planning_horizons != sorted(self.planning_horizons):
			raise ValueError("planning_horizons must be ascending")
		if self.base_year >= self.planning_horizons[0]:
			raise ValueError("base_year must precede the first horizon")
		return self

class SolveConfig(AleaConfig):
	solver: Literal["highs", "gurobi", "cplex"] = "highs"
	transmission_losses: bool = True          # AD: see 04-layer1 §5
	linearized_unit_commitment: bool = False
	time_aggregation: int = 1                  # TSAM periods; 1 = full resolution
	solver_options: dict[str, Any] = {}

	@model_validator(mode="after")
	def _gurobi_needs_a_licence(self) -> SolveConfig:
		# A commercial solver is not installed by default. Catching it here
		# beats discovering it 40 minutes into a model build.
		if self.solver in ("gurobi", "cplex"):
			import importlib.util
			if importlib.util.find_spec(self.solver) is None:
				raise ValueError(
					f"solver={self.solver!r} selected but not installed; "
					f"use 'highs' or install the solver"
				)
		return self
```

**`transmission_losses` defaults to `True`** and there is a validation test
asserting it. The specification's own benchmark (PyPSA-Eur) found that
neglecting losses overestimates optimal expansion by ~20%, and losses consume
15–25% of generated energy in many African systems. A default of `False` would
mean every published capacity mix was wrong by default.

**Every layer that owns parameters owns a section, and the root `Config`
declares it.** The list above is the config models the layers need, and the root
composes all of them — `scenario`, `solve`, `sector`, `costs`, `scanning`,
`reporting`, `api`, `paths`, `logging`, `renewables`, and `predictive`
(`07-layer4-predictive.md`). A layer whose parameters are declared on its own
model but absent from the root is a layer whose parameters cannot be set:
`extra="forbid"` turns the section in YAML into a load error, and a service that
reads it with `getattr(config, "<section>", None)` falls back to the class
defaults without saying so. That is not a missing feature, it is a config that
reads like one — the values are documented, validated, and recorded in
provenance, and none of them can be moved. The check is per-section and it is
mechanical: for each parameter a plan calls "config", confirm the root model
carries its section, then confirm the *service resolves the configured value*
rather than only that the field exists.

### 1.7 Gate

```sh
uv run alea config validate --config config/config.kenya.yaml
```

Exits non-zero on any unknown key, wrong type, or violated invariant.
**Canary:** add `plannning_horizons: [2030]` to a fixture config; the command
must exit non-zero and name the key. Committed as
`tests/ci/canaries/test_config_rejects_typo.py`.

---

## 2. Provenance

### 2.1 The model

Every artefact on disk carries provenance. This is AD-6 made concrete.

```python
# src/alea/provenance/models.py
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from alea._uuid7 import uuid7str

class Licence(StrEnum):
	CC_BY_4_0 = "CC-BY-4.0"
	ODBL = "ODbL-1.0"
	CC0 = "CC0-1.0"
	COPERNICUS = "Copernicus"
	PROPRIETARY = "proprietary"
	UNKNOWN = "unknown"

class Provenance(BaseModel):
	"""Where a datum came from, and how much to trust it.

	``uncertainty`` is required even when zero. A schema that makes it optional
	produces artefacts that cannot answer "is this measured or modelled?" —
	and the answer matters most for the seven CRITICAL-tier countries whose
	values are proxies.
	"""
	model_config = ConfigDict(extra="forbid", frozen=True)

	source_id: str                       # registry key, e.g. "worldbank_grid_map"
	source_url: str
	retrieved_at: datetime
	checksum: str                        # sha256 of the raw payload
	licence: Licence
	uncertainty: float = Field(ge=0.0)   # relative, 0.0 = exact
	uncertainty_basis: str = ""          # "measured" | "published RMSE" | "proxy"
	notes: str = ""

	@model_validator(mode="after")
	def _uncertainty_is_justified(self) -> Provenance:
		# Non-zero uncertainty with no stated basis is an uninterpretable
		# number. It will be quoted in a report and nobody will know what it
		# means.
		if self.uncertainty > 0 and not self.uncertainty_basis:
			raise ValueError("non-zero uncertainty requires uncertainty_basis")
		return self
```

### 2.2 Threading

Provenance is threaded explicitly, never via a global. A stage receives
`Provenance` objects for its inputs and produces one for its output that records
its inputs' checksums.

```python
class DerivedProvenance(Provenance):
	"""Provenance of a computed artefact."""
	inputs: list[str]        # checksums of input artefacts
	code_version: str        # git sha
	run_id: str = Field(default_factory=uuid7str)
	parameters: dict[str, Any]
```

### 2.3 Gate

Round-trip test: write an artefact, read it, assert the provenance is identical.
Plus a canary that a `Provenance` with `uncertainty=0.1` and no basis raises.

---

## 3. Country and technology registries

### 3.1 Why this exists

The specification's `data-completeness.md` has a **summary table that
contradicts its own body**: the per-country tables sum to 55 (one row per AU
member state), while the summary reports HIGH 5 / MEDIUM 32 / LOW 7 and places
Eritrea and Equatorial Guinea in MEDIUM where the tables put both in LOW. The
registry is generated from the *tables*, and a test asserts the total is 55.

Verified counts, parsed from the tables:

| Tier | Count | ISO codes |
|---|---|---|
| HIGH | 6 | EG, GH, KE, MA, NG, ZA |
| MEDIUM | 34 | AO BF BJ BW CD CG CI CM DZ ET GA GM GN LR LS LY MG ML MU MW MZ NA NE RW SD SL SN SZ TG TN TZ UG ZM ZW |
| LOW | 8 | CF EH ER GQ GW SO SS TD |
| CRITICAL | 7 | BI CV DJ KM MR SC ST |

### 3.2 Schema

```python
# src/alea/registry/countries.py
class CompletenessTier(StrEnum):
	HIGH = "high"
	MEDIUM = "medium"
	LOW = "low"
	CRITICAL = "critical"

class Country(BaseModel):
	model_config = ConfigDict(extra="forbid", frozen=True)

	iso2: CountryIso
	iso3: str
	name: str
	power_pool: Literal["COMELEC", "WAPP", "CAPP", "EAPP", "SAPP", "none"]
	completeness: CompletenessTier
	currency: str                 # ISO 4217
	timezone: str                 # IANA
	population: int | None = None
	notes: str = ""

	@property
	def needs_proxy_data(self) -> bool:
		return self.completeness is CompletenessTier.CRITICAL
```

### 3.3 Gates

- `test_registry_covers_all_au_members` — `len(registry) == 55`.
- `test_registry_tier_counts_match_tables` — the four counts above.
- `test_every_country_has_a_power_pool` — `power_pool` is never unset for a
  continental country (Sahrawi Arab Democratic Republic is `none` with a note).
- Canary: remove one country from the source table; the count test must fail.

---

## 4. Data lake

### 4.1 Layout

```
data/
├── raw/<source_id>/<checksum>/          # immutable, as retrieved
│   ├── payload.<ext>
│   └── provenance.json
├── interim/<stage>/<run_id>/            # regenerable, not authoritative
└── processed/<dataset>/<version>/       # the artefacts layers consume
    ├── data.parquet
    └── provenance.json
```

**`raw/` is immutable and content-addressed.** Nothing writes to a checksum
directory that already exists; a re-download that produces the same bytes is a
no-op. A re-download that produces *different* bytes creates a new checksum
directory and the old one stays — so a result can always be traced to the exact
bytes that produced it.

### 4.2 Artefact I/O

```python
# src/alea/io/artefacts.py
def write_artefact(
	path: Path,
	data: pd.DataFrame | xr.Dataset,
	provenance: DerivedProvenance,
	*,
	format: Literal["parquet", "netcdf", "geojson"] | None = None,
) -> str:
	"""Write data plus its provenance. Returns the artefact checksum.

	The provenance file is written *after* the payload and its checksum covers
	the payload only, so the pair is verifiable.
	"""
```

### 4.3 Gates

- `test_artefact_round_trip` — write, read, compare data and provenance.
- `test_raw_is_immutable` — a second write to an existing checksum dir raises.
- Canary: mutate one byte of a payload; the read-side checksum check must fail.

---

## 5. CI

### 5.1 Jobs

| Job | Command | Budget |
|---|---|---|
| `lint` | `uv run ruff check && uv run ruff format --check` | 30 s |
| `types` | `uv run pyright` | 60 s |
| `test` | `uv run pytest -q` | 5 min |
| `rust` | `cargo fmt --check && cargo clippy -- -D warnings && cargo test` | 5 min |
| `canaries` | `uv run pytest tests/ci/canaries -q` | 2 min |
| `determinism` | run each stage twice in separate processes, diff outputs | 5 min |

### 5.2 The canary job is separate and must be seen to fail

`tests/ci/canaries/` contains tests that **plant a defect, run the corresponding
gate, and assert the gate fails**. They are separated into their own job because
a canary that passes proves the gate works, whereas a canary that *fails* proves
the gate is blind — and that distinction must be visible in CI output, not
buried in the main test run.

### 5.3 Determinism job

```sh
PYTHONHASHSEED=0 uv run alea stage <stage> --config tests/data/kenya_fixture.yaml --out /tmp/run1
PYTHONHASHSEED=0 uv run alea stage <stage> --config tests/data/kenya_fixture.yaml --out /tmp/run2
diff -r /tmp/run1 /tmp/run2
```

AD-8 made executable. `PYTHONHASHSEED=0` is pinned because the project's history
includes a gate whose output ordering varied across runs purely from set
iteration order.

### 5.4 Why the workflow must be at the repository root

GitHub reads workflows only from `.github/workflows/` at the **repository
root**. A workflow kept in a subdirectory is never executed, and every check
that "passes" locally is unenforced. This project's history includes exactly
that failure: checks at `llocal-com/.github/workflows/` returned
`total_count: 0` across 148 commits.

**Verification is by run history, not by file existence.** After wiring CI:

```sh
gh api repos/nyimbi/alea/actions/runs --jq '.total_count'
```

Must be non-zero. A YAML file that parses is not a job that ran.

---

## 6. DVC

```sh
dvc init
dvc remote add -d storage <remote>
dvc add data/raw data/processed resources
```

- `data/raw/` — tracked, never modified.
- `data/processed/` — tracked; regenerable but expensive.
- `resources/`, `results/` — tracked where a result is load-bearing (a published
  capacity mix), ignored where it is scratch.

**Gate:** `dvc repro` on a clean clone reproduces the Kenya fixture network
checksum exactly. Canary: perturb an input; the checksum must change.

---

## 7. CLI

The only entry point Snakemake rules call (AD-5). One subcommand per stage.

```python
# src/alea/cli.py
import typer

app = typer.Typer(no_args_is_help=True)

@app.command()
def config_validate(config: Path) -> None: ...
@app.command()
def registry_export(out: Path) -> None: ...
@app.command()
def fetch(source_id: str, config: Path, out: Path) -> None: ...
@app.command()
def build(stage: str, config: Path, out: Path) -> None: ...
@app.command()
def solve(config: Path, network: Path, out: Path) -> None: ...
@app.command()
def report(kind: str, date: str, out: Path) -> None: ...
@app.command()
def scan(source_id: str | None, config: Path) -> None: ...
```

Every subcommand: `--config` required, `--out` required, exit non-zero on any
error, log the run id on both entry and exit.

---

## 8. Exit criteria for Stage 0

| # | Criterion | Gate |
|---|---|---|
| 1 | Config typo fails at load, naming the key | Canary test |
| 2 | Scenario overlay deep-merges without discarding siblings | Unit test |
| 3 | Registry has exactly 55 countries, tier counts match tables | Unit test |
| 4 | Every artefact round-trips provenance | Unit test |
| 5 | `raw/` is immutable | Canary test |
| 6 | CI runs and its run history is non-empty | `gh api .../actions/runs` |
| 7 | Every gate has a canary that fails on a planted defect | `tests/ci/canaries` green |
| 8 | Determinism job passes | Two runs byte-identical |
| 9 | `dvc repro` reproduces the fixture | Checksum match |
| 10 | `make setup` installs uv, Rust 1.90, maturin and verifies all three | Manual, once |

**Nothing in Track A, B, or C starts until all ten pass.** They are one week of
work and they are what makes the following six months' output trustworthy.
