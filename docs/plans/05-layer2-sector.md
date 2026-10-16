# 05 — Layer 2: Sector Coupling

**Track A.** Hydrogen, heat, transport, industry, water, and the full renewable
portfolio. Budget: **six weeks**, after Layer 1.

Layer 2 extends the electricity network into a multi-energy system. It is
*additive*: Layer 1's electricity-only network remains valid and is the fallback
if sector coupling is misconfigured.

---

## 1. What sector coupling buys, and what it costs

**Buys.** An electricity-only model cannot see that hydrogen production is a
flexible load, that a heat pump substitutes for electric resistance heating at a
different COP, or that an EV fleet is storage. Without these, a system with high
VRE looks more expensive than it is, because curtailment has nowhere to go.

**Costs.** Every added sector roughly doubles the variable count. The
specification's continental sector-coupled problem is beyond the development
machine (12 cores / 96 GB) at full resolution — it is reachable only with the
aggregation Layer 1 already validates (AD-9).

**The governing rule:** sector coupling is a **config layer over Layer 1**, not a
separate pipeline. The `sector` section of `config.default.yaml` is overlaid by
the environment file (`config.kenya.yaml`); it does not replace it.

---

## 2. The sectors

### 2.1 Hydrogen

| Element | Component | Notes |
|---|---|---|
| Production | `Electrolysis` (PEM / alkaline) | Efficiency 60–70% LHV; record which |
| Storage | `Store` + `Link` (cavern) | Salt cavern only where geology permits |
| Export | `Load` at a port bus | `h2export` in TWh/year |
| Demand | `Load` (industry) | Green ammonia / methanol feedstock |

**The efficiency figure is a modelling choice, not a constant.** Electrolyser
efficiency spans 60–70% LHV and system efficiency is lower. It is a config
parameter, recorded in provenance, with a cited source. A hardcoded 0.7 that
nobody can trace is how a hydrogen result becomes indefensible.

**Egypt validation:** `spec4-base.md` §8 claims PyPSA-Earth sector-coupled "has
been validated for hydrogen applications in Egypt". This is `[UNVERIFIED]` —
no citation is given. It is confirmed at **M5** by reproducing the configuration
or the claim is recorded as unsupported.

### 2.2 Heat

- Heat pumps (`Link` with a COP), thermal storage (`Store` with standing loss),
  resistive backup.
- **COP is temperature-dependent.** A fixed COP=3 is wrong in a way that matters
  for a heating-dominated system. If a fixed COP is used, it is recorded as a
  simplification in provenance; the better path is a COP time series from ERA5
  temperature.

### 2.3 Transport

- EV smart charging: flexible load with an availability profile.
- V2G: bidirectional `Link`, constrained by battery degradation cost.
- Hydrogen vehicles: a `Load` on the H₂ bus.

**V2G without a degradation cost is free storage**, which the optimiser will use
without limit and which no real fleet provides. The degradation cost is
required, not optional.

### 2.4 Industry

Steel (H₂-DRI, scrap EAF), cement (CCUS), chemicals (green ammonia, methanol).
Each is a `Link` with a conversion efficiency and a `Load`.

**These are the largest single modelling assumptions in Layer 2.** Industrial
decarbonisation pathways are contested and country-specific. Every industrial
`Link` carries a provenance record naming the pathway's source.

### 2.5 Water

The water-energy nexus: desalination as a flexible load, hydro cooling
constraints, and the drought–hydrology coupling to Layer 4's climate scenarios.

---

## 3. The renewable portfolio

Beyond solar and wind, the specification lists CSP, offshore wind, geothermal,
four hydro types, biomass conversion routes, and marine. Each needs a config
block **and** a data source, and the sources differ in quality by an order of
magnitude.

| Technology | Source | Quality | Kenya-critical |
|---|---|---|---|
| Solar PV | Global Solar Atlas | Good, validated | Yes |
| CSP | Global Solar Atlas (DNI) | Good | No |
| Onshore wind | Global Wind Atlas 3.0 | Good | Yes |
| Offshore wind | GEBCO bathymetry | Good | No (landlocked) |
| Geothermal | Geothermal Atlas for Africa | Moderate | **Yes** |
| Hydro (RoR/reservoir/PHS) | African Hydropower Atlas | Moderate, seasonal | **Yes** |
| Biomass | JRC Bioenergy Atlas | Moderate | No |
| Marine | Global Wave Statistics | Poor, sparse | No |

**Kenya needs solar, wind, geothermal, and hydro.** The remaining four are
continental-only and are built after the Kenya path closes. This is the
priority order in `02-data-pipeline.md` §1, and it is deliberate: a complete
Kenya model with four technologies beats a partial continental model with nine.

### 3.1 Geothermal is Kenya's decisive technology

`users.md` reports that geothermal is Kenya's least-cost expansion option and
that capping it at 2 GW requires ~8 GW of additional solar at +€600M/year. If
the geothermal potential is wrong, Kenya's entire result is wrong. The
geothermal resource is therefore validated separately: per-field potential is
cross-checked against KenGen's published capacity and against the Geothermal
Atlas for Africa, and the cross-check is an artefact.

---

## 4. Configuration

```yaml
# config.default.yaml — the `sector:` section; extends, does not replace
sector:
  hydrogen:
    enabled: true
    electrolyser:
      technology: pem
      efficiency_lhv: 0.65
      efficiency_source: "IRENA 2024 electrolyser cost study"
    export:
      enabled: true
      volume_twh_per_year: 100
      port_bus: "KE_Mombasa"
    storage:
      type: salt_cavern
      enabled: false        # no verified Kenyan cavern geology
  heat:
    heat_pumps: true
    cop_source: "era5_temperature_series"   # not a constant
    thermal_storage: true
  transport:
    ev_smart_charging: true
    v2g: true
    v2g_degradation_usd_per_mwh: 15.0       # required; see §2.3
  industry:
    steel: {h2_dri: true, scrap_eaf: true}
    cement: {ccus: true}
    chemicals: {green_ammonia: true}
```

**Every efficiency, COP, and degradation figure carries a `_source` field.**
A config with a numeric efficiency and no source fails validation. This is
AD-6 applied to parameters rather than artefacts: an untraceable number is
exactly as bad as an untraceable datum.

---

## 5. Module layout

```
src/alea/sector/
├── __init__.py
├── hydrogen.py      # electrolysis, storage, export
├── heat.py          # heat pumps, thermal storage
├── transport.py     # EV, V2G, H2 vehicles
├── industry.py      # steel, cement, chemicals
├── water.py         # desalination, cooling
├── renewables.py    # CSP, offshore, geothermal, hydro, biomass, marine
├── coupling.py      # compose the multi-energy network
└── service.py
```

---

## 6. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_sector_is_additive` | Sector config extends Layer 1; electricity-only result unchanged | Disable sectors; compare to Layer 1 output |
| `test_efficiency_has_source` | Every efficiency/COP has a `_source` | Remove a source; must fail |
| `test_v2g_has_degradation_cost` | V2G enabled without a cost fails | Enable V2G, omit cost; must fail |
| `test_hydrogen_mass_balance` | H₂ produced = consumed + stored + exported | Inject a leak; must fail |
| `test_energy_balance_closes` | Total energy in = out + losses per carrier | Inject a loss; must fail |
| `test_geothermal_potential_crosscheck` | Kenya geothermal within tolerance of KenGen published | Perturb; must fail |

**`test_sector_is_additive` is the structural gate.** A sector-coupled model that
disagrees with the electricity-only model *when sectors are disabled* has a
coupling bug, not a modelling difference. It isolates the bug from the physics.

---

## 7. Exit criteria for Layer 2

| # | Criterion | Gate |
|---|---|---|
| 1 | Kenya sector-coupled network couples without replacing Layer 1 | `test_the_sector_layer_extends_a_layer_one_config_without_replacing_it` |
| 2 | Disabling all sectors reproduces Layer 1 exactly | `test_sector_is_additive` |
| 3 | Hydrogen mass balance closes | `test_hydrogen_mass_balance` |
| 4 | Every efficiency/COP traceable to a source | `test_efficiency_has_source` |
| 5 | Kenya geothermal potential cross-checked | Artefact |
| 6 | Egypt hydrogen claim reproduced or withdrawn | M5 |
| 7 | All four Kenya technologies present | `test_all_four_kenya_sector_technologies_are_present` |
| 8 | Sector-coupled Kenya solves within the aggregation budget | Recorded timing |
| 9 | Every gate canaried | `tests/ci/canaries` |
| 10 | Sector config is a strict superset of Layer 1's schema | `test_the_sector_layer_extends_a_layer_one_config_without_replacing_it` |

**Criterion 8 is the practical one.** If sector-coupled Kenya cannot solve in a
useful time on 12 cores, the honest response is to record the achievable
configuration (fewer sectors, coarser aggregation) and state what was dropped —
not to report a result from a configuration nobody can re-run.
