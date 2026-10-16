# 08 — Layer 5: What-If Scenario Engine

**Track A/B shared.** Parameter-driven re-solve, caching, comparison, frontiers.
Budget: **four weeks**, after Layers 3 and 4.

Layer 5 is thin. It is a parameter overlay plus a cache plus a sweep. Its
difficulty is entirely in getting caching and reproducibility right, because a
scenario engine that returns a stale cached result is a decision-support tool
that lies.

---

## 1. What Layer 5 owns

| Concern | Module |
|---|---|
| Parameter model | `whatif.params` |
| Network mutation from parameters | `whatif.apply` |
| Result extraction | `whatif.extract` |
| Content-addressed caching | `whatif.cache` |
| Comparison and frontiers | `whatif.sweep` |
| Scenario persistence | `whatif.store` |

It owns **no physics**. Every solve calls Layer 1/2; every price calls Layer 3;
every risk metric calls Layer 3's risk module.

---

## 2. The cache-key defect, and the fix

### 2.1 The specification's key

```python
def _cache_key(self, params):
    return hash(tuple(sorted(params.__dict__.items())))
```

**This is non-deterministic across processes.** Python randomises string hashing
per interpreter (`PYTHONHASHSEED`), so `hash("carbon_price")` differs between
runs. The consequences:

- The cache never hits across processes, so every restart re-solves everything.
- The reproducibility test — `solve(p)`, clear cache, `solve(p)`, compare — passes
  because it compares two fresh solves, **not** a cached result against a fresh
  one. The test passes for the wrong reason and the cache is never exercised.

This is the same class as AD-8's other precedents: a defect that looks like a
working optimisation.

### 2.2 The fix: content hash

```python
# src/alea/whatif/cache.py
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

def cache_key(params: Any, network_checksum: str, code_version: str) -> str:
	"""Content-addressed cache key. Stable across processes.

	``hash()`` is unusable here: Python randomises string hashing per
	interpreter, so the same parameters give a different key in a different
	process. The result is a cache that never hits across runs and a
	reproducibility test that passes without ever exercising the cache.

	The key covers the parameters, the *network checksum* it applies to, and
	the code version. A key over parameters alone returns a result computed
	against a different network — which is the failure mode that makes a
	scenario engine untrustworthy, because the number looks right.
	"""
	payload = json.dumps(
		{"params": params, "network": network_checksum, "code": code_version},
		sort_keys=True,
		separators=(",", ":"),
		default=str,
	)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

**Three things in the key, and each is necessary:**

| Component | Omitted → |
|---|---|
| `params` | Cache returns the wrong scenario |
| `network_checksum` | Cache returns a result from a different network |
| `code_version` | Cache returns a result from older code after a fix |

### 2.3 The cache-liveness test

The specification's reproducibility test cannot detect a broken cache. The
correct test:

```python
def test_cache_actually_hits():
	"""A second identical solve must not re-solve."""
	engine = WhatIfEngine(FIXTURE_NETWORK)
	with count_solves() as n:
		engine.solve(params)
		engine.solve(params)
	assert n.calls == 1, "second solve must be served from cache"
```

`count_solves` is a fixture that wraps the Layer 1 solve entry point and counts
invocations. **Canary:** revert the key to `hash(tuple(sorted(...)))` and run the
test in two processes; it must fail. Without this canary the test is the
specification's test, which cannot fail.

### 2.4 Cache invalidation

The cache is content-addressed and therefore never *invalidated* — a changed
network produces a new key. Old entries are garbage-collected by an explicit
`alea whatif gc --keep-days N`, never by age-based eviction during a run, because
eviction during a sweep changes which scenarios are computed and therefore the
frontier.

---

## 3. Parameters

```python
# src/alea/whatif/params.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ScenarioParameters(BaseModel):
	"""Every knob the what-if engine exposes.

	Frozen and ``extra='forbid'``: a scenario is a value, and a typo in a
	scenario name must fail at construction, not produce a scenario that
	silently runs with the default.
	"""
	model_config = ConfigDict(extra="forbid", frozen=True)

	demand_growth: float = Field(default=0.04, ge=-0.05, le=0.15)
	coal_eaf: float = Field(default=0.55, ge=0.0, le=1.0)
	carbon_price_usd_per_tco2: float = Field(default=50.0, ge=0.0, le=1000.0)
	gas_price_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
	renewable_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
	hydrogen_export_twh_per_year: float = Field(default=0.0, ge=0.0)
	battery_cost_multiplier: float = Field(default=1.0, gt=0.0, le=5.0)
	ssp_pathway: str = "SSP2-4.5"
	drought_multiplier: float = Field(default=1.0, gt=0.0, le=3.0)

	@model_validator(mode="after")
	def _drought_needs_a_climate_scenario(self) -> ScenarioParameters:
		# A drought multiplier applied to a non-climate pathway is a
		# hydrological change with no climate story behind it. The result is
		# reportable as a sensitivity but not as a scenario.
		if self.drought_multiplier != 1.0 and self.ssp_pathway not in (
			"SSP3-7.0", "SSP5-8.5",
		):
			raise ValueError(
				f"drought_multiplier={self.drought_multiplier} requires a "
				f"high-emissions SSP pathway, got {self.ssp_pathway!r}"
			)
		return self
```

**Bounds are not decoration.** `demand_growth` above 15%/year is not a scenario,
it is a typo; catching it at construction beats catching it after a 40-minute
solve that produces a nonsense frontier.

### 3.1 Rejected parameter: `coal_eaf` as a global

The specification applies one `coal_eaf` to all coal units. Availability is
unit-specific and age-dependent. **Decision:** `coal_eaf` is a *scenario-level
multiplier* over per-unit base availability from the fleet data, not an absolute
override. The parameter's effect is therefore relative and recorded as such.

---

## 4. Applying parameters

```python
# src/alea/whatif/apply.py
def apply_parameters(
	base: pypsa.Network,
	params: ScenarioParameters,
) -> pypsa.Network:
	"""Return a mutated copy. ``base`` is never modified.

	Two corrections to the specification's ``_apply``:

	1. ``n.generators.loc[mask, "p_nom_max"] *= multiplier`` scales an
	   *absolute* MW potential by a dimensionless factor. Applied twice to the
	   same network it compounds; applied to an already-scaled network it is
	   wrong. The base potential is read from the *original* network's
	   provenance, and the multiplier is applied to that, not to whatever the
	   current value happens to be.

	2. ``n.loads_t.p_set *= (1 + g) ** (years - years.min())`` uses
	   ``years`` from the snapshot index. For a single-period network the
	   exponent is zero everywhere and the parameter silently does nothing.
	   The function asserts the network is multi-period when
	   ``demand_growth != 0``.
	"""
```

**The silent-no-op class is the danger here.** A parameter that does nothing on
a single-period network produces a frontier that is flat in that parameter, and
a flat frontier reads as "demand growth does not matter" rather than "the
parameter was not applied". The assertion makes it a loud failure.

### 4.1 Immutability

`base` is copied and never mutated. The specification's `_apply` starts with
`n = self.base.copy()`, which is correct — but `_load_driven` in Layer 4's
`LossDecomposer` shows the project's own precedent for in-place mutation going
wrong. A test asserts `base` is byte-identical after `apply_parameters`.

---

## 5. Extraction

```python
# src/alea/whatif/extract.py
def extract(n: pypsa.Network) -> ScenarioResult:
	"""Summarise a solved network.

	Every field carries the units in its name and the uncertainty of its
	inputs. ``capacity_mix_mw`` is a dict carrier -> MW; ``total_cost_usd`` is
	the objective; ``renewable_share`` is a fraction in [0, 1] and is NaN when
	total generation is zero (never 0 — see 06-layer3-market.md §5.1).
	"""
```

The specification's `_renewable_share` returns `0` when total generation is
zero. Same defect as the capture price: **NaN, not zero.**

---

## 6. Sweeps and frontiers

```python
# src/alea/whatif/sweep.py
def efficient_frontier(
	engine: WhatIfEngine,
	param_name: str,
	values: Sequence[float],
	template: ScenarioParameters,
) -> pd.DataFrame:
	"""Sweep one parameter; return cost, emissions, renewable share, risk.

	The sweep is deterministic (AD-8) and each point is cached independently.
	A sweep that fails partway leaves the completed points cached, so a re-run
	resumes rather than restarting.
	"""
```

### 6.1 The risk frontier

The specification's frontier is cost–emissions only. `users.md` asks for the
**cost–risk frontier** — the trade-off between system cost and portfolio risk.
That is produced by, for each parameter value, running Layer 3's risk metrics
over the resulting price distribution and plotting cost against CVaR.

**This is the frontier that answers the investment question.** A cost–emissions
frontier answers a policy question; a cost–risk frontier answers whether a
portfolio survives a bad year, which is what a lender asks.

### 6.2 Convergence and parallelism

Sweeps are embarrassingly parallel across parameter values. They run through
`joblib` with an explicit `n_jobs`, and **each worker writes its own cache
entry** (content-addressed, so no lock contention). A sweep of N points on 12
cores uses 11 workers, leaving one core for the orchestrator.

---

## 7. Scenario persistence

A scenario is a **named, versioned artefact**: the parameters, the network
checksum, the code version, and the result checksum. It is stored in
`results/scenarios/<name>/<version>/`.

**A scenario without its network checksum is not reproducible.** The
specification's `WhatIfEngine` holds a base network path in the constructor and
never records it; two engines built on different networks produce incomparable
results under the same scenario name.

```python
# src/alea/whatif/store.py
def save_scenario(
	name: str,
	params: ScenarioParameters,
	result: ScenarioResult,
	network_checksum: str,
	code_version: str,
) -> Path:
	"""Persist a scenario with everything needed to reproduce it."""
```

---

## 8. Module layout

```
src/alea/whatif/
├── __init__.py
├── params.py       # ScenarioParameters
├── apply.py        # network mutation, immutability
├── extract.py      # result summarisation
├── cache.py        # content-addressed cache
├── sweep.py        # frontiers, parallel sweeps
├── store.py        # scenario persistence
└── service.py
```

---

## 9. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_cache_key_stable_across_processes` | Same params → same key in two processes | Revert to `hash()`; must fail |
| `test_cache_actually_hits` | Second identical solve does not re-solve | Break the cache; must fail |
| `test_cache_key_includes_network` | Different network → different key | Drop network from key; must fail |
| `test_cache_key_includes_code_version` | Different code version → different key | Drop version; must fail |
| `test_apply_does_not_mutate_base` | `base` byte-identical after apply | Mutate in place; must fail |
| `test_demand_growth_requires_multi_period` | Single-period + growth raises | Remove assertion; must fail |
| `test_renewable_multiplier_absolute` | Applied twice gives the same result as once | Compound; must fail |
| `test_renewable_share_nan_on_zero_gen` | Zero generation → NaN | Return 0; must fail |
| `test_frontier_deterministic` | Same sweep twice byte-identical | Unseed workers; must fail |
| `test_scenario_records_network` | Saved scenario carries network checksum | Drop it; must fail |

---

## 10. Exit criteria for Layer 5

| # | Criterion | Gate |
|---|---|---|
| 1 | Cache hits across processes | `test_cache_actually_hits` in a subprocess |
| 2 | Cache key covers params, network, code | `test_cache_key_includes_params`, `test_cache_key_includes_network`, `test_cache_key_includes_code_version` |
| 3 | No parameter is a silent no-op | `test_demand_growth_requires_multi_period` |
| 4 | Base network never mutated | `test_apply_does_not_mutate_base` |
| 5 | Cost–emissions frontier computed | `test_the_cost_emissions_frontier_is_computed` |
| 6 | Cost–risk frontier computed | `test_the_cost_risk_frontier_is_computed_when_a_price_model_is_present` |
| 7 | A 20-point sweep completes on 12 cores | `test_a_twenty_point_sweep_completes` |
| 8 | Partial sweep resumes from cache | `test_a_partial_sweep_resumes_from_cache` |
| 9 | Scenarios are reproducible from their artefact alone | `test_a_saved_scenario_reproduces_from_its_artefact_alone` |
| 10 | Every gate canaried | `tests/ci/canaries` |

**Criterion 1 is the one the specification's own test cannot make.** It must run
in a **subprocess**, because the whole point is that the key differs between
interpreters — a same-process test passes against the broken `hash()` key.
