# 02 — Data Pipeline

**Track A, Stage A1.** Every input the platform consumes, its ingestion, and its
schema. Budget: **six weeks** for the Kenya-critical path, longer for the full
continental set.

The governing rule: **every datum enters through this document.** A layer that
downloads its own data is a layer whose inputs are unauditable.

---

## 1. Source register

`data1.md` → `data3.md` catalogue the sources; `data3.md` is current. This
register is the *implementable* form: it names the module, the target dataset,
and the priority.

**Priority** is by dependency, not by the specification's section order. The goal
is to reach a solvable Kenya network with the fewest sources, then widen.

| P | Source ID | Module | Target | Why here |
|---|---|---|---|---|
| 1 | `worldbank_grid_map` | `planning/topology` | transmission lines | Smallest complete topology source; enough for a first network |
| 2 | `powerplantmatching` | `planning/fleet` | generation fleet | One call, consolidated; validates the plant schema |
| 3 | `afrec_demand` | `planning/demand` | national demand totals | The denominator for everything downstream |
| 4 | `era5_cutout` | `planning/renewables` | renewable profiles | Heaviest download; gates solar and wind |
| 5 | `osm_africa` | `planning/topology` | refined topology | Replaces World Bank lines once the network builds |
| 6 | `hydro_atlas` | `planning/hydro` | hydro profiles | Seasonal; needs downscaling |
| 7 | `viirs_vnp46a2` | `outages/viirs` | nighttime radiance | **Track B, independent of 1–6** |
| 8 | `gridwatch` | `outages/validate` | ground truth | **Track B, independent** |
| 9 | `geothermal_atlas` | `planning/geo` | geothermal potential | After core solves |
| 10 | `jrc_bioenergy` | `planning/biomass` | biomass potential | After core solves |
| 11 | `irena_costs` | `planning/costs` | technology costs | Needed for expansion, not dispatch |
| 12 | `global_petrol_prices` | `market/fuel` | fuel prices | Needed for marginal cost |
| 13 | `cmip6` | `planning/climate` | climate scenarios | Last; scenario-only |
| 14 | `gwa_gsa` | `planning/renewables` | resource validation | Cross-check against ERA5-derived |
| 15 | `repp_africa` | `planning/fleet` | plant cross-check | Validates powerplantmatching |

### 1.1 Sources needing custom ingestion

Most sources are a file download plus a parse. Five need real ingestion code,
and each has a specific hazard.

#### `powerplantmatching` — offline mode is mandatory

The library fetches from live upstreams (OSM, GEM, IRENA, GEO, GPD). Those
upstreams change without notice, which makes a pipeline that calls it directly
**non-reproducible**: the same config yields a different fleet next month.

**Decision.** Run `powerplantmatching` once, export to `data/raw/`, and commit
the export. The pipeline reads the committed export. A refresh is a deliberate,
reviewed act that produces a new checksum.

```python
# src/alea/planning/fleet.py
import powerplantmatching as ppm

def export_powerplantmatching(countries: list[str], target_year: int, out: Path) -> None:
	"""Export the consolidated fleet once, for a fixed upstream snapshot.

	This is deliberately NOT part of the regular pipeline. `ppm.powerplants()`
	hits live upstreams, so calling it per-run makes every result depend on
	when it ran. Export is a manual, reviewed step; the pipeline reads the
	export.
	"""
	config = ppm.Config(countries=countries, target_date=target_year)
	df = ppm.powerplants(config=config, mock_snakemake=False)
	df = ppm.clean(df)
	assert df["Country"].notna().all(), "unmatched plants need manual review"
	df.to_parquet(out)
```

**Hazard:** `ppm.clean()` can silently drop rows. The assertion above is not
decoration — the export records `len(df)` before and after cleaning, and a drop
above 5% fails the export and requires review.

#### `era5_cutout` — the download is large and the licence is Copernicus

```python
# src/alea/planning/renewables.py
import atlite

def build_cutout(bbox: tuple[float, float, float, float], years: range, path: Path) -> None:
	"""Build an ERA5 cutout. Idempotent: an existing cutout is reused.

	The cutout is the single largest artefact in the pipeline (~10s of GB for
	Africa). It is DVC-tracked, never rebuilt in CI, and CI uses a small Kenya
	subset committed as a fixture.
	"""
	cutout = atlite.Cutout(path=path, module="era5", bounds=bbox, time=slice(*years))
	cutout.prepare()
```

**Hazard:** `atlite` writes a `.nc` plus a `.nc.aux` sidecar. Both must be
checksummed; checksumming only the `.nc` produces a cutout that verifies but
fails to open.

#### `viirs_vnp46a2` — access, volume, and quality flags

```python
# src/alea/outages/viirs.py
import earthaccess

def fetch_viirs(bbox, start, end, out_dir: Path) -> list[Path]:
	"""Fetch VNP46A2 granules. Requires Earthdata credentials via ~/.netrc."""
	earthaccess.login(strategy="netrc")
	results = earthaccess.search_data(
		short_name="VNP46A2", temporal=(start, end), bounding_box=bbox
	)
	return earthaccess.download(results, out_dir)
```

**Hazards, all three of which have bitten this class of work:**

1. **Volume.** A country-year of VNP46A2 is thousands of granules at ~100 MB.
   The pipeline processes granules streaming and writes only the extracted
   statistics, never the archive. `data/raw/` for VIIRS holds *granule
   checksums*, not the granules.
2. **Quality flags.** `QF_Cloud_Mask` bit 0–1 encodes cloud confidence
   (`00` confident clear, `01` probably clear, `10` probably cloudy,
   `11` confident cloudy). The specification's example writes
   `ds["QF_Cloud_Mask"] & 0b11 == 0` in one place and
   `(ds["QF_Cloud_Mask"] & 0b11) != 0` in another — **opposite meanings**. The
   correct reading is: keep bits 0–1 `== 0` (confident clear). This is pinned in
   a test with a synthetic flag array.
3. **Gap-filled vs. observed.** VNP46A2 contains gap-filled values where the
   observation was cloudy. `DNB_BRDF_Corrected_NTL` is the observed,
   BRDF-corrected band and is the one to use; the gap-filled band must never
   enter detection, or cloud becomes "no outage".

#### `gridwatch` — credentialed and small

Access is by registration. The Ghana dataset (147 sensors, Greater Accra,
2019–mid-2023) is the specification's primary validation set. Store the token in
`GRIDWATCH_TOKEN`, never in config. If the token is absent, the validation stage
**skips with an explicit message and records the skip in the artefact** — it does
not silently report a model as unvalidated.

#### `hydro_atlas` — seasonal, needs downscaling

The Sterl et al. atlas gives seasonal averages. Hourly profiles require
downscaling against ERA5 runoff. The downscaling method is a modelling choice
that must be recorded: use the same method as the atlas's own published
approach, cite it, and store the citation in `sources/INDEX.md`.

### 1.2 Placeholder links in the spec

`data3.md` contains several placeholder links — `zenodo.org/records/` with
"search for AfREP-Hydro", `zenodo.org/records/` (Zambia), and others. **Each is
a broken citation.** Before implementing a fetcher, resolve the placeholder to a
concrete record and record the resolved DOI in the source registry. If it cannot
be resolved, the source is marked unavailable and the plan's dependency on it is
revisited — a source the pipeline cannot fetch is not a source.

---

## 2. Schema conventions

### 2.1 Spatial

All spatial artefacts are **EPSG:4326** on disk (lon, lat order), with
projected computation in **EPSG:3857** or an appropriate UTM zone where metric
accuracy matters (buffering, areas). Conversion happens at the boundary; no
artefact is stored in a projected CRS.

**Hazard:** GeoPandas and pyproj disagree about axis order for EPSG:4326 —
GeoPandas uses (x, y) = (lon, lat), the OGC standard says (lat, lon). Pin it:
every spatial artefact declares `crs` and `axis_order` in its provenance, and a
test asserts round-trip fidelity.

### 2.2 Temporal

- **All timestamps UTC and timezone-aware.** No naive datetimes anywhere.
- Hourly series use a `pandas.DatetimeIndex` with `freq="h"` and an explicit
  `tz="UTC"`.
- **Leap years and DST are not special-cased.** Africa's timezones are almost
  all fixed-offset, so DST is nearly a non-issue — but the two exceptions
  (Morocco, and Egypt historically) must not corrupt an hourly series. The
  conversion to local time happens only at report rendering.

### 2.3 Units

Every numeric column carries its unit in the name. A test asserts that no
column in a processed artefact matches `^(capacity|cost|price|energy|power)$`
without a unit suffix.

| Quantity | Unit | Column name |
|---|---|---|
| Capacity | MW | `capacity_mw` |
| Energy | MWh | `energy_mwh` |
| Power | MW | `power_mw` |
| Cost (capital) | USD | `capex_usd` |
| Cost (marginal) | USD/MWh | `marginal_cost_usd_per_mwh` |
| Emission intensity | tCO₂/MWh | `co2_t_per_mwh` |
| Distance | km | `length_km` |
| Currency | — | never converted silently; a rate and its date are recorded |

**Currency is the trap.** The project's own history includes a document that
converted $1M at 145 KES while stating its target in KES at a different implied
rate — a 10% self-contradiction invisible to every lint because each number was
internally consistent with its own line. **Every currency conversion records the
rate and the rate's date in the artefact provenance.**

---

## 3. Processed datasets

Each is a versioned artefact with a schema and a provenance file.

| Dataset | Format | Key columns | Source |
|---|---|---|---|
| `topology` | GeoJSON + Parquet | `line_id, bus_from, bus_to, voltage_kv, length_km, capacity_mw, status` | World Bank, OSM |
| `fleet` | Parquet | `plant_id, name, country_iso, lat, lon, capacity_mw, carrier, technology, commission_year, status` | powerplantmatching |
| `demand_national` | Parquet | `country_iso, year, demand_twh` | AFREC |
| `demand_hourly` | Parquet | `country_iso, timestamp_utc, demand_mw` | AFREC + WorldPop disaggregation |
| `renewable_profiles` | NetCDF | `(bus, time) → capacity_factor` per carrier | ERA5 + atlite |
| `hydro_profiles` | Parquet | `plant_id, month, capacity_factor` | Hydro atlas |
| `costs` | Parquet | `technology, year, capex_usd_per_kw, opex_usd_per_kw_yr, lifetime_years` | IRENA |
| `fuel_prices` | Parquet | `country_iso, fuel, year, price_usd_per_mwh` | Global Petrol Prices, UNDP |
| `outage_history` | Parquet | `grid_zone, timestamp_utc, outage, confidence, source` | VIIRS |
| `outage_truth` | Parquet | `sensor_id, timestamp_utc, event_type, duration_min` | GridWatch |

### 3.1 Demand disaggregation

National AFREC totals are disaggregated to buses using WorldPop population and
GDP rasters. The method must be stated, because it is a modelling choice:

```
demand(bus, t) = national_demand(t) × weight(bus)
weight(bus) = α · pop_share(bus) + (1 − α) · gdp_share(bus)
```

`α` defaults to 0.5 and is **configurable, with the chosen value recorded in the
artefact provenance**. A disaggregation whose α is unrecorded produces a map
nobody can defend.

**What is implemented, and the step this section leaves out.** `demand_hourly`
consumes `pop_share(bus)` and `gdp_share(bus)` directly, as a table at
`resources/weights/bus_weights.parquet`. It does **not** read a WorldPop raster,
and it cannot: `worldpop` is in no register, has no fetcher, and the reduction
from a raster to a per-bus share is unspecified here. That reduction is not a
detail — it is a function of the bus geometry this run built, so it cannot be a
fixed source artefact the way the topology or the fleet are. Until a step names
it, the weight table is a human artefact and the stage refuses without one.
(It previously carried a `worldpop` fallback that called `_require_raw` with an
unregistered id, so the branch raised `unknown source` rather than reading
anything; `tests/ci/test_io_registry.py` now gates that class.)

For the seven CRITICAL-tier countries, the national total is itself a proxy —
estimated from regional averages scaled by population. Those artefacts carry
`uncertainty_basis="proxy"` and `uncertainty > 0`, and no report may present them
alongside measured values without distinguishing them.

---

## 4. Stages

Each stage: reads versioned artefacts, writes a versioned artefact, is
idempotent, and is individually re-runnable.

```
fetch_worldbank_grid → build_topology_raw
fetch_powerplants    → build_fleet_raw
fetch_afrec          → build_demand_national
fetch_worldpop       → build_demand_hourly  (needs demand_national)
fetch_era5           → build_cutout → build_renewable_profiles
fetch_hydro          → build_hydro_profiles
fetch_viirs          → build_outage_history  (Track B)
fetch_gridwatch      → build_outage_truth    (Track B)
fetch_irena          → build_costs
fetch_fuel_prices    → build_fuel_prices
```

### 4.1 Idempotence

Every stage checks its output checksum against a recorded manifest and exits
without work if unchanged. `--force` overrides.

### 4.2 Gates

- `test_stage_idempotent` — run twice, second run makes no writes.
- `test_topology_schema` — all required columns present, dtypes correct.
- `test_fleet_carriers_known` — every `carrier` is in the technology registry.
- `test_no_bare_unit_columns` — §2.3's naming rule.
- `test_demand_hourly_covers_horizon` — no gaps in the hourly index.
- `test_every_registered_stage_is_a_rule_or_a_named_exception` — every stage the
  registry holds is either a rule the workflow runs or recorded with the reason
  it is not. `test_every_stage_has_a_snakemake_rule` checks the declared stages
  have rules and not the converse, so a builder can register, be reachable
  from `alea build`, and be run by nothing — which reads as a working stage.
- Canary: inject a row with an unknown carrier; the schema gate must fail.

**Four stages register and have no rule**: `resilience`, `outage_validation`,
`sector_coupling`, `quality_validation`. They are named in
`STAGES_WITHOUT_RULES` with the reason, and the gate above is what keeps the set
from growing unnoticed. `resilience` reads `interruptions.parquet` and
`zone_population.parquet`, **neither of which anything writes** — a rule for it
would fail on its first input, and the missing producers are a Layer 4 task, not
a Stage A1 one.

`tlens` and `critical_lines` are no longer in that set. Both read
`network_arrays.json` and `dispatch.parquet`, which `rule network_arrays` now
writes from a solved network, so each has a rule of its own. The register shrank
by moving the slug rather than by deleting it: `losses/flow.loading_series` is
the loading kernel `reporting/producers.py` recorded as missing, and
`critical_lines` is the first weekly section to leave `UNPRODUCED`.


---

## 5. The loss decision, recorded

`transmission_losses=True` from the first solve. The specification's benchmark
(PyPSA-Eur: neglecting losses overestimates expansion by ~20%) is
`[UNVERIFIED]` here and is confirmed at **M1** by solving Kenya both ways and
recording the difference as an artefact. If the Kenya result contradicts the
benchmark, the benchmark is wrong for African networks and that is a finding.

Losses consume 15–25% of generated energy in many African systems, so this is not
a marginal modelling choice.

---

## 6. Exit criteria for Stage A1

| # | Criterion | Gate |
|---|---|---|
| 1 | Kenya topology builds with > 0 lines and no orphan buses | `test_topology_schema` |
| 2 | Kenya fleet covers > 90% of installed capacity vs. the RePP cross-check | `test_fleet_coverage_notices_a_missing_carrier` |
| 3 | Hourly demand series has no gaps over the fixture horizon | `test_demand_hourly_covers_horizon` |
| 4 | Renewable profiles in [0, 1] for every bus and hour | `test_capacity_factors_in_range` |
| 5 | Every processed artefact has provenance with a checksum | `test_every_artefact_a_stage_writes_has_provenance_with_a_checksum` |
| 6 | VIIRS quality-flag handling matches the pinned semantics | `test_cloud_flag_semantics` |
| 7 | CRITICAL-tier proxies carry `uncertainty_basis="proxy"` | `test_a_critical_tier_national_total_carries_a_proxy_basis` |
| 8 | Every stage is idempotent | `test_the_stage_is_idempotent_through_the_cli` |
| 9 | Every placeholder link in `data3.md` is resolved or the source is dropped | Manual, recorded in the source registry |
| 10 | Every registered stage is a rule the workflow runs, or a named exception | `test_every_registered_stage_is_a_rule_or_a_named_exception` |

**Criterion 2 is the one to watch.** A fleet that covers 60% of national
installed capacity will produce a capacity mix that looks plausible and is
wrong. The coverage check compares the built fleet, carrier by carrier, against
the published capacity total and fails below 90%, naming the missing capacity.

**The yardstick is RePP, not AFREC.** AFREC's registered target is
``demand_national`` (§1's table, and the register's own entry): it publishes
consumption, and no version of it carries installed capacity. `spec/spec3.md`
§17 names EIA and IRENA for capacity validation; of those, only RePP is
registered against `planning/fleet` here, and its fetcher is the one fleet
source with a stable DOI. RePP covers renewables only and ends in 2023, so it
is a cross-check and not a total — a fleet missing its thermal plants will
legitimately read low against it, which is why the stage records the verdict
rather than raising on it. A run with no RePP export records that the check did
not run, which is a different claim from a check that passed.
