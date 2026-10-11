# 00 — Architecture and Decisions

**ALEA — African Light and Energy Analytics**
**Status**: Binding. Every other plan document conforms to this one.
**Verified against**: working tree at `9e934f9`, 2026-10-11
**Audience**: an intermediate developer joining with no prior context

---

## 0. How to read this plan set

This directory is the complete implementation plan. It is written so that an
intermediate developer can execute it without making major technical decisions:
where a choice exists, it is made here, with the reason, and the alternatives
are recorded as rejected rather than left as an exercise.

| Document | Contents | Read it when |
|---|---|---|
| `00-architecture.md` | This file. Stack, language split, conventions, decisions | First, in full |
| `01-foundations.md` | Config, provenance, country registry, data lake, CI, DVC | Before writing any code |
| `02-data-pipeline.md` | Every data source, its ingestion, and its schema | Before Track A |
| `03-rust-core.md` | The Rust crates, their APIs, and the PyO3 boundary | Before any Rust |
| `04-layer1-planning.md` | Network construction, expansion, dispatch | Track A |
| `05-layer2-sector.md` | Sector coupling | After Layer 1 |
| `06-layer3-market.md` | Agents, clearing, capture prices, PPA, risk | After Layer 1 |
| `07-layer4-predictive.md` | VIIRS, weather ML, maintenance, losses, TLENS, resilience | Track B |
| `08-layer5-whatif.md` | Scenario engine, caching, frontiers | After Layers 3–4 |
| `09-layer6-reporting.md` | Report generation and distribution | Last of the layers |
| `10-layer7-scanning.md` | Connectors, extraction, review, integration | Track C, any time |
| `11-layer8-api.md` | REST API, auth, tiers, delivery adapters | After layers land |
| `12-quality.md` | Testing, canaries, validation, benchmarks | Continuously |
| `13-deployment.md` | Hardware, containers, orchestration, ops | Before production |
| `14-roadmap.md` | Sequenced milestones with checkable gates | For scheduling |

**A note on honesty.** Several numbers in `spec/` are literature benchmarks the
plan inherits but which were **not verified** during planning (web search was
unavailable). Every such number is marked `[UNVERIFIED]` with the milestone at
which it must be confirmed. Do not report a `[UNVERIFIED]` figure to a
stakeholder as though it were established. See §9.

---

## 1. What ALEA is

A continental decision-support platform for African energy systems: capacity
expansion planning to 2060 across all 55 AU member states and five power pools,
hourly dispatch, market and price simulation, outage prediction, loss and
resilience analytics, what-if scenario exploration, and periodic intelligence
reporting — fed by a continuous scanning layer that watches the African energy
landscape for new information.

It is seven layers plus a scanning layer above them, plus an API layer for
delivery. The layering is the central architectural constraint: **each layer
depends only on those below it**, which is what makes independent development,
testing, and deployment possible.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 8  API & delivery adapters                                     │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 7  Intelligence scanning  (above everything; feeds downward)   │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 6  Periodic reporting                                          │
│ Layer 5  What-if scenario engine                                     │
│ Layer 4  Outage prediction · losses · resilience                     │
│ Layer 3  Market simulation · capture prices · PPA · risk             │
│ Layer 2  Sector coupling                                             │
│ Layer 1  Planning core                                               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. The constraint that shapes everything

**Verified hardware on the development machine: 12 cores, 96 GB RAM, 173 GB
free disk.**

The specification's continental tier assumes **128 cores, 512 GB RAM, 10 TB
NVMe**. A continental capacity-expansion problem — 55 nodes, 8760 hourly
snapshots, four planning horizons, sector-coupled — is not solvable on the
development machine and may not be solvable on any single machine the project
owns.

This single fact drives four decisions:

1. **Continental scale is a deployment concern, not a development one.** Every
   capability is built *correct* at single-country scale and made *deployable*
   at continental scale through configuration.
2. **Kenya is the development target.** HIGH data completeness, the
   specification's own case study, and a network that solves locally.
3. **Aggregation is a first-class, validated feature.** TSAM time aggregation
   and spatial clustering are not optimisations bolted on later; they are
   config switches that must be *validated against a full-resolution solve on a
   small network*, because an unvalidated aggregation is a silent change to the
   answer.
4. **The local development loop must never require a continental solve.** If a
   change cannot be tested on Kenya in minutes, the test is wrong.

---

## 3. Architecture decisions

Each decision below is binding. Rejected alternatives are recorded so they are
not re-litigated.

### AD-1 — PyPSA-Earth is an external workflow, not a dependency

**Decision.** ALEA depends on `pypsa` (the library) directly. PyPSA-Earth is
consumed as an **external producer of network artefacts**. The seam between
them is **files** — NetCDF networks, GeoJSON topology, CSV profiles — never
Python imports.

**Reason.** `pypsa-earth` is not on PyPI (the project returns 404) and is not a
library. It is a Snakemake workflow repository — `pypsa-meets-earth/pypsa-earth`,
v0.9.0 as of 2026-09-03, 33.5 MB — cloned and run inside a conda environment
that carries the geospatial stack. The specification's `pypsa-earth>=0.7.0`
dependency line is therefore not implementable as written.

**Consequences.**
- ALEA stays pip-installable and unit-testable on Python 3.14. PyPSA-Earth keeps
  its own conda environment. The two never share an interpreter.
- Every artefact crossing the seam is versioned and checksummed, so any result
  traces to the network it came from.
- ALEA cannot call PyPSA-Earth internals. Where a spec example reaches into
  `pypsa_earth.*`, reimplement it in `alea.planning` or require the data to
  arrive in the artefact.

**Rejected.** *Import PyPSA-Earth as a library* — forces ALEA onto the conda
environment's Python (which cannot be 3.14) and couples every layer to another
project's internals. *Fork PyPSA-Earth into the repo* — inherits a 33 MB
workflow and its maintenance burden for a fraction of its functionality.

**Reversal cost if wrong:** moderate. If the artefact schema cannot carry what
Layer 3 needs, `alea.planning` must own more network construction. Falsification
check at M1 (§9).

---

### AD-2 — Rust for computation, Python for orchestration

**Decision.** Split by **data size**, not by conceptual layer.

| Concern | Language | Why |
|---|---|---|
| Numerical kernels: VIIRS pixel algebra, LSH/minhash, loss decomposition, time-series aggregation, Monte Carlo | **Rust** | Data size 10⁸–10¹¹ elements; Python overhead dominates |
| Orchestration, config, provenance, I/O glue, API, reporting | **Python** | Ecosystem: pypsa, pandas, xarray, fastapi, jinja2 |
| Optimisation modelling | **Python** (pypsa/linopy) | The solver does the work; the modelling layer is small |
| ML training | **Python** (xgboost/lightgbm/sklearn) | Mature, GPU-capable, SHAP integration |

**Reason.** ALEA's performance problems are all element-wise array algebra over
rasters and time series, not algorithmic complexity. VIIRS VNP46A2 at 500 m over
Africa is roughly 10⁹ pixels per day; the VZA-binned quantile baseline is a
grouped reduction over that. Python + numpy does this at perhaps 5–20× the
memory bandwidth of Rust and with per-call overhead that dominates at the
chunking granularity the algorithm requires. The same is true of the LSH
shingling in the scanning layer and the Monte Carlo in the risk layer.

Conversely, ALEA's *complexity* is in orchestration and I/O — configuration
precedence, provenance threading, artefact versioning, multi-format ingestion.
That is exactly where Python is strongest and Rust would cost development time
for no runtime gain.

**The boundary is the artefact, not the object.** Rust functions take and return
arrays (numpy buffers, Arrow, Parquet), never Python objects. A Rust call that
returns a Python object graph has thrown away the advantage.

**Verified.** PyO3 0.23 with the `abi3-py312` feature builds a single
forward-compatible wheel (`cp312-abi3-macosx_11_0_arm64`) that imports and runs
under the project's Python 3.14.8. Confirmed by building and importing a probe
extension during planning. `maturin` is required — a bare `cargo build` of an
`extension-module` crate fails on macOS with `ld: symbol(s) not found for
architecture arm64`, because the platform needs `-undefined dynamic_lookup`.

**Rejected.** *Python only* — the VIIRS and LSH kernels would need Cython or
numba, which is Rust-with-worse-tooling for this purpose. *Rust everywhere* —
reimplements pypsa, pandas, xarray, and fastapi; years of work, no benefit.
*C++* — no memory-safety guarantee, and PyO3's ergonomics are better than
pybind11's for this use.

---

### AD-3 — The signal contract is the only Layer 7 boundary

**Decision.** The scanning layer hands `Signal` objects to everything else and
nothing more. Already implemented in `src/alea/signals/models.py`.

**Reason.** This is what makes the scanning layer independently buildable and
what makes the audit trail possible. Any proposal to have a connector write
directly to a model is a proposal to delete provenance.

**Consequences.** The `SignalType` taxonomy is load-bearing for both the
extraction pipeline and the story detector in the strategy spec. Adding a member
means updating the story detector's newsworthiness rules in the same commit.

---

### AD-4 — Artefacts over objects, everywhere

**Decision.** Every stage writes a versioned file and reads versioned files. No
stage holds a live Python object across a boundary.

**Reason.** It is what allows Snakemake to schedule the pipeline, DVC to version
it, and any stage to be re-run in isolation. It is also the precondition for the
"reproducibility to machine precision" validation target — you cannot reproduce
what you cannot address.

**Consequence.** Every artefact carries provenance (§AD-6). Schemas are declared
once and validated on both write and read.

---

### AD-5 — Snakemake calls a library; no logic in rules

**Decision.** `alea` is a library with a CLI. Snakemake rules declare inputs,
outputs, and parameters, and shell out to `alea`. **No logic lives in a `.smk`
file.**

**Reason.** Logic in a rule is logic that cannot be unit-tested, cannot be
type-checked, and cannot be imported. The specification's example rules contain
`# ... download logic` and `# ... disaggregation logic` placeholders — exactly
the shape of code that becomes untestable.

**Consequence.** A rule that needs a new behaviour means a new CLI subcommand,
with tests, not a longer shell string.

---

### AD-6 — Uncertainty and provenance travel with the datum

**Decision.** Every artefact schema carries `value`, `uncertainty`, and
`provenance`. `uncertainty` may be zero for measured data, but the field is
never absent.

**Reason.** The specification requires "uncertainty-quantified proxy estimates"
for data-poor countries. That is only honest if uncertainty travels with the
data. Seven countries (Burundi, Cabo Verde, Comoros, Djibouti, Mauritania,
Seychelles, São Tomé) are absent from continental datasets entirely; their
values are proxies. A report must be able to distinguish "modelled from WorldPop"
from "reported by the national utility" — which means the distinction must be in
the data, not in a footnote someone forgot to write.

**Rejected.** *Add uncertainty later* — means re-deriving every downstream
number, and in practice means never adding it.

---

### AD-7 — One API, many delivery adapters

**Decision.** Layer 8 exposes one REST API. The strategy specification's
seventeen additional channels (WhatsApp, USSD, SMS, widgets, Excel, QGIS,
Zapier, …) are **adapters over that API**, not separate systems.

**Reason.** The specification lists eighteen channels. Eighteen codebases is
unmaintainable; eighteen adapters over one API is routine. The architecture
question is whether a USSD menu and a terminal dashboard can read the same
endpoints. They can, and that is the whole design.

---

### AD-8 — Determinism is a feature, enforced

**Decision.** Every computation that feeds a published number is deterministic
given its inputs. This means: no unseeded randomness, no iteration over
unordered sets where order affects output, no `hash()` of strings, no reliance
on filesystem enumeration order.

**Reason.** Two verified examples of this class already exist in the
specification's own sample code:

- `WhatIfEngine._cache_key` uses `hash(tuple(sorted(params.__dict__.items())))`.
  Python randomises string hashing per interpreter, so this key differs between
  runs: cached results silently miss, and the reproducibility test passes for
  the wrong reason.
- The project's own history includes a check whose output ordering was
  non-deterministic (`alembic check` walking indexes held in sets gave
  `add_index` counts of 30, 28, 30, 28, 26 across five runs).

**Consequence.** A determinism test runs each stage twice in separate processes
and asserts byte-identical output. `PYTHONHASHSEED=0` is pinned in the CI
subprocess environment.

---

### AD-9 — Aggregation must be validated against full resolution

**Decision.** Any time-series aggregation (TSAM) or spatial clustering used to
make a problem tractable must be validated by comparing the aggregated result
against a full-resolution solve on a small network, and the comparison recorded
as an artefact.

**Reason.** Aggregation is the only way to reach continental scale on available
hardware, which makes it load-bearing — and it is a silent change to the answer.
An aggregation that shifts system cost by 8% is indistinguishable from a model
change if nobody measured it.

**Consequence.** `alea.planning.aggregation` ships with a validation harness and
a recorded error budget. A config that raises the aggregation level without a
passing validation artefact is refused.

---

### AD-10 — Gates are canaried before they are trusted

**Decision.** Every automated check — CI job, validation gate, drift detector —
must be demonstrated to **fail** on a deliberately planted defect before it is
trusted, and re-canaried after any change to the check itself.

**Reason.** This project has already produced a gate that passed because it
never ran: `asyncio_mode = "auto"` was configured with no `pytest-asyncio`
installed, so on an async-throughout codebase every async test silently passed
without executing. The canary — an async test that raises — was the only thing
that revealed it. The same failure mode has five independent precedents in this
codebase's history: a `case` statement inside a command substitution that was a
parse error, a bash variable named `GROUPS` shadowing the shell's special
variable so a dispatcher ran zero of its four groups and exited 0, a GitHub
workflow kept at a path GitHub does not read so every check was unenforced, and
a canary patch that did not apply so the test passed against untouched code.

**Consequence.** Each check has a companion canary in `tests/ci/canaries/`. A
check without a canary is reported as unverified in `12-quality.md`'s gate
register.

---

## 4. Language split: the concrete boundary

### 4.1 Rust crates

A Cargo workspace at `rust/`, producing abi3 wheels consumed as the
`alea-core` Python package.

| Crate | Purpose | Replaces | Why Rust |
|---|---|---|---|
| `alea-rasters` | VIIRS pixel algebra, VZA binning, grouped quantiles, cloud masking | numpy over xarray | 10⁹ elements/day; grouped reductions dominate |
| `alea-dedup` | MinHash/LSH near-duplicate detection | `datasketch` | Shingling is 10⁶–10⁷ strings/document-set; hashing dominates |
| `alea-series` | TSAM aggregation, representative-period selection, load-duration curves | `tsam` | 8760 × 10⁴ matrix reductions |
| `alea-losses` | Loss decomposition, DC power flow, N-1 contingency sweep | pypsa `lpf` per contingency | 200 lines × 8760 snapshots, each an independent solve |
| `alea-risk` | Monte Carlo, VaR/CVaR, efficient-frontier sweeps | numpy | 10⁵–10⁶ scenario paths |

**Rule for adding a crate:** if the kernel operates on more than 10⁷ elements
per call and is called more than 100 times per pipeline run, it belongs in Rust.
Below that, write it in Python — the development cost is not repaid.

**Rule against:** a Rust crate must not depend on `pandas`, `xarray`, or
`pypsa`. It takes arrays and returns arrays. This is what keeps the boundary
thin and the crates testable without a Python interpreter.

### 4.2 Python packages

```
src/alea/
├── _core/            # thin wrappers over alea-core; the ONLY place Rust is imported
├── config/           # Pydantic config models, YAML loading, scenario overlays
├── provenance/       # provenance and uncertainty models
├── registry/         # country, power pool, technology registries
├── io/               # artefact read/write, checksums, versioning
├── signals/          # the signal contract (Layer 7 ↔ everything)
├── scanning/         # Layer 7
├── planning/         # Layer 1
├── sector/           # Layer 2
├── market/           # Layer 3
├── outages/          # Layer 4a
├── losses/           # Layer 4b
├── resilience/       # Layer 4b
├── whatif/           # Layer 5
├── reporting/        # Layer 6
├── api/              # Layer 8
└── cli.py            # the only entry point Snakemake rules call
```

**`_core/` is the single import site for Rust.** No other Python module imports
`alea_core` directly. This means the Rust boundary can be stubbed for testing,
and a Rust failure has exactly one place to be caught.

### 4.3 The wrapper contract

Every Rust-backed function has a Python wrapper with this shape:

```python
# src/alea/_core/rasters.py
from __future__ import annotations
import numpy as np
from numpy.typing import NDArray
import alea_core

def vza_baseline(
    radiance: NDArray[np.float32],
    sensor_zenith: NDArray[np.float32],
    bin_size_deg: float,
    quantile: float,
) -> NDArray[np.float32]:
    """Per-(pixel, VZA bin, month) first-quartile baseline.

    Pure function over arrays. No Python objects cross the boundary.
    """
    assert radiance.shape == sensor_zenith.shape
    assert radiance.dtype == np.float32
    assert 0.0 < quantile < 1.0
    result = alea_core.vza_baseline(radiance, sensor_zenith, bin_size_deg, quantile)
    assert result.shape == radiance.shape
    return result
```

Rules: assertions at entry and exit (project convention), arrays only, and the
wrapper never contains logic that belongs in the kernel or vice versa.

---

## 5. Cross-cutting conventions

### 5.1 Python

- **Python 3.14+.** Tabs, not spaces. Modern typing (`str | None`, `list[str]`).
- **Async throughout.** Async tests are plain `async def` with no decorator;
  `asyncio_mode = "auto"` handles them. `pytest-asyncio` **must** be installed —
  see AD-10.
- **Pydantic v2** with
  `ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)`.
  `extra="forbid"` is not optional: a typo in a config key must fail at load,
  not at hour five of a solve.
- **UUID7 identifiers** via `alea._uuid7.uuid7str()`. Time-ordered, so sorting by
  id sorts by creation time and ids cluster in B-tree indexes without leaking a
  sequence.
- **Logging** methods are `_log_`-prefixed.
- **Runtime checks** at function start and end.
- **Structure.** Main code in `service.py`, models in `views.py` unless complex.
- **No mocks** except LLM calls. pytest fixtures, real objects,
  `pytest-httpserver` for HTTP.

### 5.2 Rust

- **Edition 2021**, MSRV 1.90 (verified working toolchain).
- **`abi3-py312`** on all PyO3 crates, so one wheel serves every supported
  Python. Verified: a `cp312-abi3` wheel imports and runs under 3.14.8.
- **`#![forbid(unsafe_code)]`** in every crate. If a kernel needs `unsafe`, the
  justification goes in the crate's README and is reviewed.
- **No `unwrap()`/`expect()` outside tests.** Errors are typed and returned;
  the wrapper turns them into Python exceptions.
- **Property tests via `proptest`** for every kernel, plus a golden-file test
  against a Python reference implementation of the same algorithm.
- **`cargo clippy -- -D warnings`** and **`cargo fmt --check`** in CI.
- **Every crate has a Python reference implementation** in
  `tests/reference/` used only for differential testing. This is the single
  highest-value testing decision in the Rust half: it means the kernels are
  checked against a second, independently written implementation of the same
  mathematics, not merely against themselves.

### 5.3 Toolchain

| Tool | Version | Purpose |
|---|---|---|
| `uv` | 0.9.22 (verified) | Python env, locking |
| `maturin` | 1.15.0 (verified) | Rust → wheel |
| `cargo` | 1.90.0 (verified) | Rust build |
| `ruff` | configured | Lint, format |
| `pyright` | configured, standard mode | Types |
| `pytest` | configured | Tests |
| `dvc` | to add | Data versioning |

**Note on the Rust install.** The `stable` rustup toolchain on the development
machine has **no binaries** (`~/.rustup/toolchains/stable-aarch64-apple-darwin/bin`
does not exist), so `cargo` fails with "the 'cargo' binary … is not applicable
to the 'stable-aarch64-apple-darwin' toolchain". Pin the toolchain explicitly via
`rust-toolchain.toml` to `1.90.0` and use the versioned path, or run
`rustup toolchain install stable`. This is an environment defect, not a project
one, but it will waste a newcomer's afternoon.

---

## 6. Repository layout

```
alea/
├── Cargo.toml                  # Rust workspace root
├── rust-toolchain.toml         # pins 1.90.0
├── pyproject.toml              # Python project (maturin build backend)
├── rust/
│   ├── alea-rasters/
│   ├── alea-dedup/
│   ├── alea-series/
│   ├── alea-losses/
│   └── alea-risk/
├── src/alea/                   # Python package (§4.2)
├── tests/
│   ├── ci/                     # autodiscovery path
│   │   └── canaries/           # AD-10
│   ├── reference/              # Python reference impls for Rust differential tests
│   └── data/                   # fixtures
├── config/
│   ├── config.default.yaml
│   ├── config.kenya.yaml
│   ├── config.africa.yaml
│   ├── config.sector.yaml
│   ├── config.predictive.yaml
│   ├── config.whatif.yaml
│   ├── config.reporting.yaml
│   └── scenarios/
├── rules/                      # Snakemake, thin (AD-5)
├── scripts/                    # thin CLI shims, no logic
├── data/{raw,interim,processed}/   # DVC-tracked, content-addressed
├── resources/                  # intermediates
├── results/                    # solved networks, model outputs
├── reports/{daily,weekly,monthly,quarterly,annual}/
├── sources/                    # archived citations + INDEX.md
├── docs/
│   ├── plans/                  # this plan set
│   └── research/               # research notes with sources
├── envs/
└── spec/                       # the specification (authoritative for intent)
```

---

## 7. Testing strategy

Four tiers, each with a defined cost budget:

| Tier | Scope | Runtime budget | Runs |
|---|---|---|---|
| **Unit** | One function, real objects, no mocks | < 1 s each | Every commit |
| **Differential** | Rust kernel vs. Python reference on random + edge inputs | < 30 s | Every commit |
| **Integration** | A stage end-to-end on a fixture network/document | < 5 min | Every commit |
| **Validation** | Against external ground truth (GridWatch, published benchmarks) | Minutes–hours | Weekly + release |

**Differential testing is the core discipline.** Every Rust kernel has a Python
reference implementation of the same mathematics, written independently, in
`tests/reference/`. Random inputs plus adversarial edges (empty, single element,
NaN, ±inf, all-equal, monotonic, extreme magnitude) are compared to a tight
tolerance. This catches the failure mode that pure property testing misses: a
kernel that is self-consistently wrong.

**Test data is generated, not committed, where possible.** Synthetic networks
and synthetic VIIRS tiles with *known* answers let the algorithm be verified
independently of the data. A committed fixture is a test that cannot say why it
expects what it expects.

---

## 8. Error handling and observability

- **Typed errors in Rust**, converted at the boundary to Python exceptions that
  carry the same information.
- **Python exceptions are never swallowed.** A bare `except:` is a bug.
- **Structured logging** via `structlog`, JSON in production, human-readable
  locally. Every log line carries the run id.
- **Run ids.** Every pipeline invocation generates a UUID7 run id, threaded
  through logs, artefact provenance, and report footers. This is what makes
  "which run produced this number" answerable.
- **Fail loud on missing data.** A missing input raises. It does not fall back
  to a default, and it does not silently use a neighbouring country's value.
  Proxy estimates are *explicit* artefacts with `uncertainty > 0`, not silent
  substitutions.

---

## 9. Unverified claims and their falsification points

Web search was unavailable during planning, so the following literature figures
are inherited from `spec/` and are **not verified**. Each is marked
`[UNVERIFIED]` throughout this plan set, and each has a milestone at which it is
confirmed or the claim is withdrawn.

| Claim | Source in spec | Falsified by | Milestone |
|---|---|---|---|
| VIIRS outage detection AUC 0.8346 (Ghana); 89.41% accuracy (Johannesburg) | spec4-base §5.5, §12.2 | Reproduce on independently obtained data | **M2** |
| Weather outage forecasting 99% accuracy (Adrar, Algeria) | spec4-base §12.3 | Reproduce, or drop the claim | **M2** |
| Predictive maintenance: 87% critical failure detection, 64% false-alarm reduction, 260% ROI (Nigeria) | spec4-base §12.4 | Reproduce | **M6** |
| AMIRIS/ASSUME MAE 5.6–6.4 €/MWh | spec4-base §10 | Reproduce against a known network | **M8** |
| Neglecting losses overestimates expansion by 20% (PyPSA-Eur) | spec4-base §26 | Compute both ways on Kenya | **M1** |
| Mixtral-8 91% success rate for outage flagging | spec4-data-collection §9.3 | Measure against human review | **M3** |
| Continental LOPF < 6 h on 128 cores | spec4-base §25 | Scale from local core-hours | **M7** |

**Rule.** No `[UNVERIFIED]` figure appears in a published report. It is either
verified, or the report states the claim as an unverified input from the
literature with its source, or the claim is dropped.

---

## 10. What this architecture costs

Stated plainly so it is a choice rather than a surprise:

- **Two toolchains.** A newcomer needs Python, uv, Rust, and maturin. Mitigated
  by a `make setup` that installs and verifies all four, and by Rust being
  confined to `_core/`.
- **A boundary to maintain.** Every Rust kernel needs a Python reference
  implementation for differential testing — roughly doubling the work of writing
  a kernel. This is deliberate: it is what makes the Rust half trustworthy.
- **A wheel to build.** CI must build wheels per platform, which is slower and
  more failure-prone than a pure-Python install. Mitigated by `abi3`, which
  means one wheel per platform rather than one per Python version.
- **Aggregation risk.** Continental scale depends on aggregation whose error
  must be measured. AD-9 exists because this is the single largest source of
  silent error in the whole platform.

The alternative — pure Python — avoids all four costs and cannot process a
continental VIIRS archive, cannot run a 200-line N-1 contingency sweep in a
useful time, and cannot reach continental capacity expansion on available
hardware. The costs are accepted.
