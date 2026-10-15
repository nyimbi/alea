# 04 — Layer 1: Planning Core

**Track A.** Network construction, capacity expansion, dispatch. Budget:
**eight weeks** after Stage A1's data pipeline.

Layer 1 is the foundation every other analytical layer reads from. Get the
network wrong and every downstream number inherits the error.

---

## 1. What Layer 1 owns

| Concern | Owner | Not Layer 1's job |
|---|---|---|
| Bus topology from transmission lines | `alea.planning.topology` | — |
| Generator fleet attachment | `alea.planning.fleet` | — |
| Renewable profiles per bus | `alea.planning.renewables` | — |
| Demand per bus per hour | `alea.planning.demand` | — |
| Capacity expansion optimisation | `alea.planning.expansion` | — |
| Hourly dispatch | `alea.planning.dispatch` | — |
| Aggregation (TSAM, clustering) | `alea.planning.aggregation` | Validated per AD-9 |

It does **not** own: market clearing (Layer 3), outages (Layer 4), scenarios
(Layer 5), reporting (Layer 6).

---

## 2. The PyPSA-Earth seam (AD-1)

### 2.1 What PyPSA-Earth is

`pypsa-earth` is a Snakemake workflow repository — `pypsa-meets-earth/pypsa-earth`,
v0.9.0 as of 2026-09-03 — **not a pip package** (PyPI returns 404). It runs
inside a conda environment carrying the geospatial stack (GDAL, geopandas,
rasterio, atlite) and produces a PyPSA network as its final artefact.

### 2.2 The seam is files

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  PyPSA-Earth            │         │  Alea                    │
│  (conda env, Snakemake) │         │  (uv, Python 3.14)       │
│                         │         │                          │
│  build_network ─────────┼────────▶│  data/processed/topology │
│  add_electricity ───────┼────────▶│  data/processed/fleet    │
│  solve_network ─────────┼────────▶│  results/networks/*.nc   │
└─────────────────────────┘         └──────────────────────────┘
              artefacts: NetCDF, GeoJSON, Parquet, CSV
```

**What crosses:** NetCDF networks, GeoJSON topology, Parquet tables, CSV
profiles. **What never crosses:** Python objects, imports, or a shared
interpreter.

### 2.3 The integration contract

`alea.planning` must be able to build a network from the *artefacts* alone. That
means:

- Every PyPSA-Earth output Alea consumes has a **schema** declared in
  `alea.planning.schemas` and validated on read.
- Alea can build a network with **zero** PyPSA-Earth output present, using its
  own ingestion (`02-data-pipeline.md`) — the Kenya path does exactly this.
- PyPSA-Earth is an **optional accelerator** for continental runs where its
  Voronoi clustering and preprocessing are worth the conda dependency. It is
  never a requirement.

**Why this matters:** the Kenya development loop must never need a conda
environment. A developer clones Alea, runs `uv sync`, and builds a network from
the processed datasets. PyPSA-Earth appears only in `13-deployment.md` as a
continental-scale preprocessing step.

### 2.4 Rejected: importing PyPSA-Earth

Where `spec4-base.md` reaches into `pypsa_earth.*` internals, the function is
reimplemented in `alea.planning` or the data is required to arrive as an
artefact. The specification's `create_network` example is a config snippet, not
an API — it configures a workflow, not a function call.

---

## 3. Network construction

### 3.1 Topology

```python
# src/alea/planning/topology.py
from __future__ import annotations
import geopandas as gpd
import pandas as pd
import pypsa
from alea.provenance.models import DerivedProvenance

def build_topology(
	lines: gpd.GeoDataFrame,
	*,
	voltage_kv_min: float = 66.0,
	snap_tolerance_m: float = 500.0,
) -> tuple[pypsa.Network, DerivedProvenance]:
	"""Build bus/line topology from transmission line geometries.

	Buses are placed at line endpoints. Endpoints within ``snap_tolerance_m``
	of each other are the same bus — without this, every line gets two unique
	buses and the network is a graph of isolated edges with no power flow.

	Lines below ``voltage_kv_min`` are dropped: sub-transmission is not part of
	a national planning model and including it multiplies bus count for no
	analytical gain.
	"""
```

**The snap tolerance is the load-bearing parameter.** Too small and a substation
shared by five lines becomes five buses; too large and two distinct substations
merge. It is configurable, recorded in provenance, and validated by a test that
asserts the resulting network is **connected** (one weakly-connected component
per synchronous area) and has **no orphan buses** (every bus has at least one
line or generator attached).

### 3.2 Fleet

```python
def attach_generators(
	n: pypsa.Network,
	fleet: pd.DataFrame,
	*,
	max_attach_km: float = 50.0,
) -> None:
	"""Attach each plant to its nearest bus.

	A plant further than ``max_attach_km`` from any bus is *reported*, not
	silently attached. It usually means a missing line, and silently attaching
	it to a bus 200 km away distorts the network's spatial structure.
	"""
```

### 3.3 Renewable profiles

Profiles come from `atlite` over the ERA5 cutout (`02-data-pipeline.md` §1.1),
aggregated to buses. Output is a `capacity_factor` in [0, 1] per (bus, carrier,
hour) — validated by a range test.

**Hazard:** `atlite`'s `pv` and `wind` convertibles return capacity factor per
unit of *installed capacity* given a layout. The layout parameters (turbine
type, panel tilt, spacing) are modelling choices that must be recorded in the
artefact provenance, because they change the capacity factor by 10–20%.

### 3.4 Demand

From `demand_hourly` (`02-data-pipeline.md` §3), disaggregated by the recorded
α. The profile is attached to buses with `p_set` in MW.

**The Kenya validation:** national annual demand from the built hourly series
must match AFREC's national total within **2%**. A demand series that is 15% low
produces a capacity mix that is 15% low and looks entirely plausible.

---

## 4. Aggregation (AD-9)

### 4.1 The two levers

| Lever | Reduces | Mechanism | Config |
|---|---|---|---|
| **Temporal** | 8760 → 12–52 snapshots | TSAM representative periods | `solve.time_aggregation` |
| **Spatial** | 55 → 5–10 nodes | k-means on bus features | `scenario.clusters` |

Both are **silent changes to the answer** and both are the only route to
continental scale on 12 cores.

### 4.2 The validation harness

```python
# src/alea/planning/aggregation.py
def validate_aggregation(
	network: pypsa.Network,
	n_periods: int,
	n_clusters: int,
	*,
	tolerance_cost_pct: float = 2.0,
	tolerance_mix_pct: float = 5.0,
) -> AggregationValidation:
	"""Solve full-resolution and aggregated; compare.

	Writes an ``AggregationValidation`` artefact. A config selecting this
	aggregation without a passing artefact for this network is refused at load.
	"""
```

The comparison metrics are total system cost, capacity mix (L1 distance on
shares), emissions, and peak price. The harness is expensive (two solves) and is
run once per network, not per solve.

### 4.3 The gate

```python
# in config loading
if config.solve.time_aggregation > 1:
	validation = load_validation_artefact(network_id)
	if validation is None:
		raise ValueError(
			f"time_aggregation={config.solve.time_aggregation} selected for "
			f"network {network_id!r} but no validation artefact exists. "
			f"Run `alea validate aggregation` first."
		)
```

**Canary:** set `time_aggregation: 12` on a fixture network with no validation
artefact; config load must fail. Then create a validation artefact recording an
8% cost error and confirm the config still refuses it.

**This is the single most important gate in Layer 1.** Aggregation without
measurement is how a platform reports a capacity mix that is 8% off and cannot
say so.

---

## 5. Expansion and dispatch

### 5.1 Transmission losses

`transmission_losses=True` from the first solve. The specification's benchmark
(PyPSA-Eur: neglecting losses overestimates expansion ~20%) is `[UNVERIFIED]`
and is confirmed at **M1** by solving Kenya both ways and recording the
difference as an artefact. If Kenya contradicts the benchmark, the benchmark is
wrong for African networks and that is a finding worth publishing.

### 5.2 Solver selection

| Problem size | Solver | Licence | Default |
|---|---|---|---|
| < 500k variables | HiGHS | MIT | **Yes** |
| 500k–5M variables | HiGHS (slow) or Gurobi | — / commercial | Ask |
| > 5M variables | Gurobi / CPLEX | commercial | Required |

**HiGHS is the default and is a direct dependency of `pypsa` 1.4** — verified
via `uv pip show pypsa`. It is not a separate extra. A config selecting
`gurobi` or `cplex` validates that the solver is importable at config load
(`01-foundations.md` §1.6), not forty minutes into a model build.

### 5.3 Multi-investment periods

`multi_investment_periods=True` for capacity expansion across the planning
horizons (2030, 2040, 2050, 2060). This is a pypsa feature and requires the
snapshots to be a `MultiIndex` with a `period` level — a common source of
confusing failures when the network was built single-period.

### 5.4 The Kenya case study, as a validation target

`users.md` states the specification's own Kenya result: geothermal is the
least-cost expansion option, and limiting it to 2 GW requires ~8 GW of
additional solar and raises annual system cost by **€600 million**.

**This is a validation target, not a claim.** It is `[UNVERIFIED]` here (the
figure appears in `users.md` without a citation to the underlying study). M1
reproduces it or records the discrepancy. If Alea's Kenya model does not
reproduce it, either the model or the claim is wrong, and finding out which is
the point of having the target.

**Currency:** the figure is in EUR. Every comparison against it records the
EUR/USD rate and date in the artefact provenance (`02-data-pipeline.md` §2.3).

---

## 6. Module layout

```
src/alea/planning/
├── __init__.py
├── schemas.py        # artefact schemas, validated on read
├── topology.py       # buses, lines, snapping
├── fleet.py          # generator attachment, powerplantmatching export
├── renewables.py     # atlite cutout, capacity factors
├── demand.py         # disaggregation, profiles
├── aggregation.py    # TSAM, clustering, the validation harness
├── expansion.py      # multi-period CEP
├── dispatch.py       # single-period LOPF
└── service.py        # the orchestration entry points
```

---

## 7. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_network_connected` | One weakly-connected component per synchronous area | Cut a line; must fail |
| `test_no_orphan_buses` | Every bus has a line or generator | Add a bus with nothing; must fail |
| `test_capacity_factors_in_range` | Every CF in [0, 1] | Inject CF=1.2; must fail |
| `test_demand_matches_national` | Built series within 2% of AFREC | Scale demand 0.8×; must fail |
| `test_aggregation_requires_validation` | Aggregated config without artefact refused | Config with no artefact; must fail |
| `test_aggregation_accuracy` | Kenya: cost within 2%, mix within 5% | Inject a bad aggregation; must fail |
| `test_losses_default_on` | `transmission_losses` defaults `True` | Flip default; must fail |
| `test_reproducible_solve` | Two solves byte-identical (AD-8) | Unseed the solver; must fail |
| `test_the_capacity_section_carries_both_numbers_per_row` | §7.1's monthly section reads a capacity *and* a change from each row | Write the capacity into `change`; must fail |
| `test_the_capacity_section_refuses_to_invent_a_change` | One solve in the directory omits `change` rather than writing `0.0` | Write zeros; must fail |

**The last two are the "declared is not produced" class, one layer down.** The
monthly cadence declares ``capacity_update`` with columns ``["Carrier",
"Capacity", "Change", "Basis"]`` -- two numeric columns, so `_rows_for` binds
each header to the row column naming it and does **not** fall back to the
primary. Two defects are therefore available and both render: a producer that
wrote one number into both columns prints a capacity under the header "Change",
and a producer that wrote ``0.0`` for a change it could not compute asserts the
strongest claim available -- capacity did not move -- from a directory holding a
single solve. The first is the same shape as `market_report`'s; the second is
particular to a section whose quantity is a *difference*, which needs two
artefacts where the pipeline writes one.

---

## 8. Exit criteria for Layer 1

| # | Criterion | Gate |
|---|---|---|
| 1 | Kenya network builds, connected, no orphans | `test_network_connected` |
| 2 | Kenya expansion solve completes under HiGHS | Integration test |
| 3 | Demand matches AFREC within 2% | `test_demand_matches_national` |
| 4 | Aggregation validated and recorded | Validation artefact |
| 5 | Losses on, difference vs. lossless recorded | M1 artefact |
| 6 | Kenya case study reproduced or discrepancy recorded | M1 artefact |
| 7 | Continental config builds (not solves) | Integration test |
| 8 | Two solves byte-identical | Determinism job |
| 9 | Every gate canaried | `tests/ci/canaries` |
| 10 | Layer 1 solves without PyPSA-Earth present | CI job with conda absent |
| 11 | The monthly capacity section is produced, with both numbers | `test_the_capacity_section_carries_both_numbers_per_row` |

**Criterion 10 is the one that keeps AD-1 honest.** If Layer 1 cannot build a
network with PyPSA-Earth absent, the seam has leaked and the dependency is
real regardless of what the architecture document says.
