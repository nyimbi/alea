# Coupling pack — operational, supply-side, outage, asset-condition and grid detail

The 42 nodes in `/tmp/fam_operational-supply.txt`. Verified against the tree as it
stands: `load_graph()` returns **1344 parameters, 525 equations, 1075 edges and 284
uncoupled**. All 42 are present in the graph. **None of the 42 appears in any
equation**, as an lhs or as an rhs operand — the slice is genuinely untouched, not
merely undetermined.

| | count |
|---|---|
| nodes in slice | 42 |
| get a proposal (equation or read) | 11 |
| — become an lhs of an equality (`derive`) | 2 (`asset_age_distribution`, `payment_security_required`) |
| — become an lhs of an inequality (`bound`) | 2 (`workshop_capacity`, `loss_reduction_investment`) |
| — become an rhs operand (`read`) | 7 (`ramp_rate_coal`, `ramp_rate_gas`, `min_stable_level_coal`, `min_stable_level_gas`, `min_up_time_coal`, `min_down_time_coal`, `storage_duration_curve`) |
| equations proposed | **8** (6 equalities, 2 inequalities) |
| new nodes required | 4 |
| retyped nodes | 11 |
| deferred | 31 |
| class breakdown | PRODUCT 9 · THRESHOLD 2 · QUALITATIVE 12 · BASE-NEEDED 9 · SCENE-SWITCH 10 · DEPRECATED 0 |

The verified set closes **11 of 42** slice nodes and takes `uncoupled()` from 284 to
**273**, measured on an in-memory graph built from the shipped document with the
retypes and new nodes applied. Every proposed equation loads, passes the symbol
check, passes `check_equation` decidable-and-consistent, sits on the affine solve
path, and propagates at defaults with **no excursion and no violation**.

---

## What the verification found, before the rows

**1. Thirty-four of the 42 are catalog placeholders.** The signature is
`unit=None`, range `(0.0, 1000000.0)`, `default=500000.0`. Only eight carry a real
type: `balancing_market`, `day_ahead_market`, `intraday_market`, `real_time_market`,
`security_constrained_dispatch`, `unit_commitment`, `life_extension_possible`
(`unit='1'`, boolean descriptions) and `failure_rate_curve`
(`1`, `[0, 3]`, default 1.0, determinism `physical`). Any proposal here is a retype
first and an equation second, and a placeholder default of 500,000 is never a
plausible physical value.

**2. The placeholder default hides a range violation that no check reports.**
`ac_voltage_limit` is described as "Maximum AC voltage" with a range of `[0, 1e6]`
and a default of `500000.0`. There is no voltage unit in the graph at all: zero
nodes carry a volt-based unit, so `[0, 1e6]` is not a per-unit band and not a kV
band. `supply-emissions-grid.md` already deferred this node for the same reason;
this pack confirms the deferral and records the stronger ground — the node is not
merely missing an operand, it is missing a *dimension*.

**3. `line_outage_probability` and `line_outage_duration` cannot be multiplied.**
The shipped equation is:

```
line_outage_hours_per_year = line_outage_probability * line_outage_duration
```

with `line_outage_probability` in `1/year` and `line_outage_duration` in
`hours/event`. `check_equation` returns **decidable=True, consistent=False**:
*"the two sides do not share a dimension"* — lhs reduces to `dimensionless`, rhs to
`1/[event]`. The shipped equation is missing an events-per-year factor, and the unit
check has been reporting it. This is the finding the slice exposed and it is a defect
in an existing equation, not in a proposed one (finding F1 below).

**4. `coal_price_per_mwh` is off by a factor of 12.96 and fails its own unit check.**
The shipped identity is `coal_price_per_mwh = coal_price / (25 * 3.6)`. Coal at
25 GJ/tonne is `25/3.6 = 6.944 MWh/tonne`, so a price of USD/tonne becomes USD/MWh
by *dividing by 6.944* — that is, multiplying by 3.6/25 = 0.144. The shipped form
divides by 25 and by 3.6, giving 0.0111. At the default `coal_price = 80`, the node
evaluates to **0.8889 USD/MWh** where the conversion gives **11.52 USD/MWh** — a
factor of **12.96** (`(25*3.6)/(25/3.6)`). `check_equation` returns
**decidable=True, consistent=False**: the lhs is `USD/MWh`, the rhs is
`[currency]/[mass]`. The equation is currently harmless only because nothing reads
it: `coal_price_per_mwh` has **zero** consumers in the graph, and the LCOE path
instead uses the free node `fuel_cost_coal` (12.0 USD/MWh, which is close to the
correct conversion and confirms the intended value). Finding F2.

**5. The two best-shaped coupling candidates in the slice have no base, and the
graph proves it by name.** There is no count of starts (`starts`, `start_count`,
`cold_start`, `cycling` — all absent), so `startup_cost_coal` and `startup_cost_gas`
cannot be determined or read. There is no reservoir energy capacity
(`hydro_reservoir_energy_mwh`, `reservoir_energy` — absent), so
`hydro_reservoir_level` has nothing to be a share of. There is no water depth
(`depth`, `water_depth`, `seabed` — absent), so `wind_offshore_platform` cannot
enter a cost function. These are BASE-NEEDED, and the absence is checked by name
against the graph rather than assumed.

**6. The ten scene switches are switches, and the graph treats them that way.**
`balancing_market`, `day_ahead_market`, `intraday_market`, `real_time_market`,
`security_constrained_dispatch`, `unit_commitment` and `life_extension_possible`
are booleans (`unit='1'`, no range, defaults 1/1/0/0/1/1/0). **None is read by any
equation** — checked by collecting every rhs symbol across all 525 equations. The
precedent for a boolean that *is* read is `n_1_criterion`, which appears as an
operand of `contingency_reserve_mw_definition`. A switch that selects a solver
stage is not a quantity and must not be multiplied; the three market-design
switches in the slice (`market_coupling`, `trade_agreement`,
`maintenance_schedule_optimisation`) are the same object untyped.

**7. The catalog's own arrows point at nodes the graph does not carry.**
`docs/param_eqn.md` gives `workshop_capacity → repair_time` (23.13),
`microgrid_deployment → islanding_capability ← mini_grid_deployment` (8.17, and
8.16 sends `islanding_capability → islanded_supply`),
`loss_reduction_investment ← line_upgrade_budget` (8.20), and
`payment_security_required → cost_of_debt` (5.24). `repair_time` and
`islanded_supply` are **absent** from the graph; `islanding_capability`,
`line_upgrade_budget`, `mini_grid_deployment` and `cost_of_debt` are present. So
three of the catalog's four arrows can be honoured against shipped operands, and one
(`workshop_capacity → repair_time`) cannot. This pack takes the three that can.

**8. A conversion carried as a bare literal is a dimension the walker does read.**
`lcoe_coal_definition` uses `1000` and `8760` to convert kW→MW and hours→years.
Because the walker multiplies the literal into the operand's dimension, a constant in
the wrong *place* shows up as a dimension mismatch, not as a silent scale error. That
is exactly what happened to finding 4: `coal_price_per_mwh = coal_price / (25 * 3.6)`
has lhs `USD/MWh` (`[currency]·[time]²/[mass]/[length]²`) against an rhs of
`[currency]/[mass]`, so `check_equation` returns **consistent=False**. The walker
caught it. What the walker cannot catch is a constant with the right dimension and
the wrong magnitude — which is why every row in this pack prints its value at
defaults.

---

## A note on the citation column

The rule is stronger than the BRIEF's prose states, and the pack is written to the
code rather than the prose. `Citation.resolves()` in
`src/alea/provenance/citations.py:130` tests

```python
return any(needle.casefold() in haystack for needle in self.cites)
```

so the registered spelling must appear **inside** the citation text — one direction,
not both. Every citation below was run through that predicate, not merely compared
by eye; the five keys used here resolve as:

```
ramp / msl / up-down / workshop -> entsoe_adequacy   (gep_review_2017 also cited on ramp)
storage                         -> iea_nea_egc
payment / loss                  -> world_bank_regulation
age                             -> catalog_duplicate_resolutions
```

Every quoted phrase in a citation cell was also checked against the archived text
whitespace-normalised, and all twelve appear verbatim.

The archive files named (`entsoe_maf_2019_methodology.pdf`,
`iea_nea_egc_2020.pdf`, `world_bank_regulating_utilities_handbook.pdf`) are present
in `sources/archive/`, so `archive_path.is_file()` holds for each.

The one class with no archived source is the maintenance-regime block (CBM, RCM,
RBM, ISO 55000, AM maturity). A grep over every `.txt` in `sources/archive/` for
`condition.based`, `reliability.centred`, `risk.based`, `ISO 55000`, `RCM`, `CBM`
returns nothing on point — the single `risk-based` hit is CBAM's customs-control
language in `cbam_regulation_2023_956.txt`, not maintenance. Those five nodes go to
**Sources to fetch** and get no citation, because there is no file to point at —
including `condition_based_maintenance`, which this pack therefore leaves free
rather than aliasing onto `predictive_maintenance_adoption` (see Rejected).

---

## Classification

| node | class | kind | reason |
|---|---|---|---|
| `ramp_rate_coal` | PRODUCT | read | A per-unit ramp rate in `1/hour`; multiplies fleet capacity to give MW/hour. |
| `ramp_rate_gas` | PRODUCT | read | As coal. |
| `min_stable_level_coal` | PRODUCT | read | A share of rated capacity; multiplies fleet capacity to give MW. |
| `min_stable_level_gas` | PRODUCT | read | As coal. |
| `min_up_time_coal` | PRODUCT | read | Hours; enters the cycling ceiling as a denominator. |
| `min_down_time_coal` | PRODUCT | read | Hours; enters the cycling ceiling as a denominator. |
| `storage_duration_curve` | PRODUCT | read | Energy-to-power ratio in hours; multiplies the storage fleet's power rating. |
| `asset_age_distribution` | PRODUCT | derive | Mean fleet age = asset life minus remaining life. |
| `condition_based_maintenance` | QUALITATIVE | defer | A regime selector. CBM is *not* the same object as `predictive_maintenance_adoption`: CBM is one input to that adoption, and an alias would overstate it. |
| `payment_security_required` | PRODUCT | derive | A security amount = share × value at risk; the value at risk ships. |
| `workshop_capacity` | THRESHOLD | bound | Throughput must cover the maintenance workload; an inequality, not an equality. |
| `loss_reduction_investment` | THRESHOLD | bound | Spend is capped by the line-upgrade budget; an inequality. |
| `microgrid_deployment` | BASE-NEEDED | defer | No microgrid capacity or count; `mini_grid_deployment` is a different programme. |
| `startup_cost_coal` | BASE-NEEDED | defer | No starts count, no archived per-start cost. |
| `startup_cost_gas` | BASE-NEEDED | defer | As coal. |
| `nuclear_lead_time` | BASE-NEEDED | defer | No nuclear-specific build duration. |
| `hydro_reservoir_level` | BASE-NEEDED | defer | No reservoir energy capacity. |
| `ac_voltage_limit` | BASE-NEEDED | defer | No voltage dimension anywhere in the graph. |
| `wave_energy_converter_type` | BASE-NEEDED | defer | No wave-height or converter efficiency base. |
| `wind_offshore_platform` | BASE-NEEDED | defer | No water-depth base. |
| `coal_retirement_schedule` | BASE-NEEDED | defer | A retirement *year* per unit; no unit-level vintage register. |
| `failure_rate_curve` | QUALITATIVE | defer | A shape selector (0 flat / 1 bathtub / 2 wear-out); the curve is a function, and the DSL carries no function-valued node. |
| `degradation_model` | QUALITATIVE | defer | A model selector, not a rate; `solar_degradation`/`wind_degradation` are the rates and already ship. |
| `asset_management_maturity` | QUALITATIVE | defer | A maturity level; no archived source for its scale. |
| `iso_55000_compliance` | QUALITATIVE | defer | A compliance flag against a standard; no archived source. |
| `reliability_centred_maintenance` | QUALITATIVE | defer | A regime selector; no archived source. |
| `risk_based_maintenance` | QUALITATIVE | defer | A regime selector; no archived source. |
| `failure_history` | QUALITATIVE | defer | An event log, not a scalar. |
| `maintenance_history` | QUALITATIVE | defer | An event log, not a scalar. |
| `maintenance_schedule` | QUALITATIVE | defer | A schedule (a table of periods), not a scalar; ENTSO-E describes it as "explicit periods in which specified plants are unavailable for dispatch". |
| `line_outage_start` | QUALITATIVE | defer | A timestamp with no unit; the honoured pypsa spelling is a rating, not a window. |
| `line_outage_end` | QUALITATIVE | defer | As start. |
| `balancing_market` | SCENE-SWITCH | defer | Boolean stage selector. |
| `day_ahead_market` | SCENE-SWITCH | defer | Boolean stage selector. |
| `intraday_market` | SCENE-SWITCH | defer | Boolean stage selector. |
| `real_time_market` | SCENE-SWITCH | defer | Boolean stage selector. |
| `security_constrained_dispatch` | SCENE-SWITCH | defer | Boolean: whether network limits bind. |
| `unit_commitment` | SCENE-SWITCH | defer | Boolean: whether the model enforces UC. |
| `life_extension_possible` | SCENE-SWITCH | defer | Boolean: whether the optimiser may extend life. |
| `market_coupling` | SCENE-SWITCH | defer | A coupling algorithm selector, untyped. |
| `trade_agreement` | SCENE-SWITCH | defer | A contract-type selector, untyped; the catalog calls it "Metadata affecting F_l". |
| `maintenance_schedule_optimisation` | SCENE-SWITCH | defer | A switch on whether maintenance timing is optimised. |

Counts: PRODUCT 9, THRESHOLD 2, QUALITATIVE 12, BASE-NEEDED 9, SCENE-SWITCH 10,
DEPRECATED 0 — 42 rows, every slice node exactly once.

`payment_security_required` is classed PRODUCT rather than THRESHOLD because the
node is determined by an equality; its rejected alternative is the inequality that
would have made it a bound. `loss_reduction_investment` and `workshop_capacity` are
THRESHOLD because the only coupling the graph supports is one-sided.

---

## Proposals

### New nodes

Four lhs ids that do not exist in the graph. Each is created derived, with a range
and no default, per the loader's rule that a determined parameter is `derived` and a
derived node carries no default.

| id | unit | range | role / determinism | category | why it must exist |
|---|---|---|---|---|---|
| `thermal_ramp_capability_mw_per_hour` | `MW/hour` | `[0, 20000]` — 20 GW/hour is the largest plausible national fleet's full range in one hour; zero is a fleet with no ramping capability | derived / physical | Operational | A ramp rate is per-unit-of-capacity; without a fleet-level MW/hour the rate has no magnitude. Nothing else in the graph multiplies capacity by a ramp. |
| `thermal_minimum_generation_mw` | `MW` | `[0, 100000]` — 100 GW is above any single country's thermal fleet; zero is a fleet with no must-run floor | derived / physical | Operational | As above: a minimum stable *level* is a share, and the share needs the capacity. |
| `coal_cycling_ceiling_per_year` | `1/year` | `[0, 8760]` — an upper bound of one cycle per hour, which is the physical maximum; the minimum-up/down constraint makes the real value far lower | derived / physical | Operational | The only arithmetically clean use of min-up/min-down hours is a cycle ceiling. Without it the two nodes can only be typed and left. |
| `storage_energy_capacity_mwh` | `MWh` | `[0, 1e8]` — 100 TWh is several times any plausible national store; zero is a store with no energy | derived / physical | Supply | A duration in hours multiplied by power gives energy; the graph carries the storage fleet's power (`storage_capacity_mw`) and its duration, but no energy. |

### Retypes

Ten nodes are retyped in the table below, and `asset_age_distribution` is retyped
in its own row under PRODUCT — eleven in all. No node changes id. The placeholder
default `500000.0` is replaced everywhere it appeared.

| node | unit | range | default | role / determinism | why |
|---|---|---|---|---|---|
| `ramp_rate_coal` | `1/hour` | `[0, 0.1]` | 0.02 | free / physical | A ramp rate is a fraction of rated output per hour. 0.02/h is 2%/h — a large coal unit's upward limit; 0.1/h is the top of the once-through band. |
| `ramp_rate_gas` | `1/hour` | `[0, 0.4]` | 0.1 | free / physical | CCGT ramps an order faster than coal; 10%/h at the default, 40%/h the fast-start ceiling. |
| `min_stable_level_coal` | `1` | `[0, 1]` | 0.4 | free / physical | ENTSO-E defines it "as a percentage of the unit's nominal capacity"; 40% is the conventional coal floor. |
| `min_stable_level_gas` | `1` | `[0, 1]` | 0.3 | free / physical | As coal; CCGTs hold a lower floor. |
| `min_up_time_coal` | `hours` | `[1, 48]` | 6 | free / physical | Hours a unit must stay on. 48 h is a cold-start-to-shutdown minimum for a large unit. |
| `min_down_time_coal` | `hours` | `[1, 48]` | 4 | free / physical | Hours a unit must stay off. |
| `storage_duration_curve` | `hours` | `[0, 100]` | 6 | free / physical | The node is an energy-to-power ratio in hours; 100 h is the long-duration ceiling (pumped hydro at the top of its band). |
| `workshop_capacity` | `events/year` | `[0, 2000]` | 500 | free / fixed | A workshop's throughput in maintenance events per year. 2,000 is ten a working day across a large utility's shops. |
| `loss_reduction_investment` | `USD` | `[0, 1e10]` | 5,000,000 | free / policy | An investment amount in currency, matching `line_upgrade_budget`'s unit. |
| `payment_security_required` | `USD/year` | `[0, 1e11]` | — (derived) | derived / fixed | A security amount per year, matching `collateral_posted_usd_per_year`'s annualised convention. |

`asset_age_distribution` is also retyped, in its own row below.
`condition_based_maintenance` is **not** retyped: it is deferred, so its shipped
placeholder unit and range stay as they are.

### PRODUCT

| node | class | kind | unit | range | role/determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `ramp_rate_coal` | PRODUCT | read | `1/hour` (retyped from `None`) | `[0, 0.1]` | free / physical | `--` (operand of `thermal_ramp_capability_definition`) | The fraction of rated output a coal unit can move in one hour. A ramp limit is a rate against capacity; the graph's placeholder default of 500,000 admitted a unit that ramps its entire rating 500,000 times an hour. | `entsoe_adequacy` — ENTSO-E adequacy studies, MAF 2019 Appendix 2: "accurate ramp rates and start-up/shut-down times for each unit" (`sources/archive/entsoe_maf_2019_methodology.pdf`); `gep_review_2017` — Oree et al. (2017), RSER 69:790-803: "Ramping capability refers to the speed at which a generating unit can change its output" (`sources/archive/whiterose_gep_review_2017.pdf`) | Making it a MW/hour directly. A per-unit rate is the thing TSOs collect per unit; converting at the node would bake one fleet's capacity into a rate that must be reused across capacities. |
| `ramp_rate_gas` | PRODUCT | read | `1/hour` (retyped) | `[0, 0.4]` | free / physical | `--` (operand of `thermal_ramp_capability_definition`) | As coal, with the wider band a gas unit's controls allow. | As coal | As coal |
| `min_stable_level_coal` | PRODUCT | read | `1` (retyped) | `[0, 1]` | free / physical | `--` (operand of `thermal_minimum_generation_definition`) | The share of rated capacity below which a coal unit cannot run stably. ENTSO-E defines the parameter "as a percentage of the unit's nominal capacity" and states the simulation does "not allow the unit to run under this limit". | `entsoe_adequacy` — ENTSO-E adequacy studies: "Minimum stable generation in MW is a parameter defining the unit's technical minimum power output" (`sources/archive/entsoe_maf_2019_methodology.pdf`) | Making it MW directly, as ENTSO-E's own prose does. The graph carries per-technology capacity and a per-technology share; a MW value would have to be re-derived for every scenario's fleet, and the share is what transfers. |
| `min_stable_level_gas` | PRODUCT | read | `1` (retyped) | `[0, 1]` | free / physical | `--` (operand of `thermal_minimum_generation_definition`) | As coal. | `entsoe_adequacy` — ENTSO-E adequacy studies, as coal | As coal |
| `min_up_time_coal` | PRODUCT | read | `hours` (retyped) | `[1, 48]` | free / physical | `--` (operand of `coal_cycling_ceiling_definition`) | The minimum hours a coal unit must stay running once started. | `entsoe_adequacy` — ENTSO-E adequacy studies ("Minimum Up Time defines the minimum number of hours a unit must stay in operation before it can be idled") | A per-unit start count. Absent (finding 5); the ceiling is what the two durations *can* support without one. |
| `min_down_time_coal` | PRODUCT | read | `hours` (retyped) | `[1, 48]` | free / physical | `--` (operand of `coal_cycling_ceiling_definition`) | The minimum hours a coal unit must stay off before restart. | `entsoe_adequacy` — ENTSO-E adequacy studies ("Minimum Down Time defines the minimum number of hours a unit must remain idle before it can be restarted") | As above |
| `storage_duration_curve` | PRODUCT | read | `hours` (retyped) | `[0, 100]` | free / physical | `--` (operand of `storage_energy_capacity_definition`) | The energy-to-power ratio of the storage fleet in hours. IEA/NEA define discharge duration as `E/P` at nominal power, which is exactly this node; multiplying it by the fleet's power rating gives the fleet's energy. | `iea_nea_egc` — IEA/NEA Projected Costs of Generating Electricity: "the installed energy capacity E (allowing thus the specification of the discharge duration E/P at nominal power per cycle)" (`sources/archive/iea_nea_egc_2020.pdf`; footnote 8: "E/P represents the charging and discharging duration at nominal power") | Making this node the equation's lhs — `storage_duration_curve = storage_energy_capacity_mwh / storage_capacity_mw` — rejected on the BRIEF's affine rule read in reverse: `storage_energy_capacity_mwh` is the node this pack *creates*, so the lhs must be the new node, and `storage_duration_curve` is the shipped dial. It is `free` and typed here, which is the form a scenario actually varies. |
| `asset_age_distribution` | PRODUCT | **derive** | `years` (retyped from `None`) | `[0, 100]` | **derived** / physical | `asset_age_distribution = asset_life - remaining_useful_life` | The fleet's mean age. `remaining_useful_life` already ships as `asset_life * asset_condition_index`, so the age is the part of life already spent — 25 × (1 − 0.7) = 7.5 years at defaults. The node's name says *distribution*; a mean is the one moment of a distribution the graph can carry, and the description is corrected to say so. | `catalog_duplicate_resolutions` — "The catalog's own duplicate rows, resolved" by equality over two shipped nodes (`sources/INDEX.md`, `n/a` row); no external work is needed for an identity the graph itself states | Deriving it from `plant_retirement_age`: that node is an alias of `asset_life` (`plant_retirement_age_alias`), so the result would be `asset_life - remaining_useful_life` with extra steps and a longer dependency chain. Rejected as a duplicate path to the same number. |
| `payment_security_required` | PRODUCT | **derive** | `USD/year` (retyped from `None`) | `[0, 1e11]` | **derived** / fixed | `payment_security_required = settlement_risk * total_revenue_usd_per_year` | The security a counterparty must post: the share of settled value exposed to settlement failure times the value settled. `settlement_risk` (0.01) is the shipped share; `total_revenue_usd_per_year` (6.487 bn at defaults) is the shipped value at risk. | `world_bank_regulation` — World Bank Regulation of Utilities handbook, revenue caps: §4.9 "External Regulatory Risk Mitigation Methods and Partial Risk Guarantees", the treatment of security instruments (`sources/archive/world_bank_regulating_utilities_handbook.pdf`) | `payment_security_required = collateral_requirements * allowed_revenue_requirement` — **rejected**, and `unclassified.md`'s deferral partly overturned. That equation is `collateral_posted_usd_per_year` exactly (`collateral_posted_usd_per_year = collateral_requirements * allowed_revenue_requirement`, shipped), in a different unit (`USD million/year` against this node's `USD/year`); shipping both would ship the same number twice under two names. The settlement-risk product is a different quantity with a different base and it is the one the catalog's own arrow (`payment_security_required → cost_of_debt`) needs. A third form, `settlement_risk * tariff_usd_per_mwh * demand_twh ... / 8760`, was built and rejected on measurement: its dimensionality is `[currency]`, not `[currency]/[time]`, because `demand_twh` is an annual *rate* and dividing by 8760 converts hours to years rather than the reverse. |

### THRESHOLD

Both are inequalities whose lhs stays `free`; neither is an equation target, so no
role changes.

| node | class | kind | unit | range | role/determinism | inequality | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `workshop_capacity` | THRESHOLD | **bound** | `events/year` (retyped from `None`) | `[0, 2000]` | free / fixed | `workshop_capacity >= number_of_generators * maintenance_frequency` | The workshop must be able to take the fleet's planned maintenance workload: 220 units × 2 events/year = 440 events/year, against a capacity of 500. The inequality is one-sided because a workshop larger than the workload is idle capacity, not a violation. | `entsoe_adequacy` — ENTSO-E adequacy studies: "Planned outage – State of an asset when it is not available in the power system and the outage was planned. These outages include maintenance, mothballing and any other non-availabilities known in advance", and the model is fed maintenance "as explicit periods in which specified plants are unavailable for dispatch" (`sources/archive/entsoe_maf_2019_methodology.pdf`); the identity itself is definitional | `workshop_capacity = number_of_generators * maintenance_frequency` as an equality. That would make the workshop exactly sized to the fleet, which is a policy statement the graph has no basis for — and it would put the lhs on the determined path, where `workshop_capacity` would stop being a dial. The catalog's own arrow (23.13) wants a *capacity* that constrains `repair_time`, not a capacity defined by the workload. |
| `loss_reduction_investment` | THRESHOLD | **bound** | `USD` (retyped from `None`) | `[0, 1e10]` | free / policy | `loss_reduction_investment <= line_upgrade_budget` | Spend on loss reduction comes out of the line-upgrade budget, not out of thin air: 5 m against a budget of 50 m. The bound is what makes `transmission_loss_reduction_target` (the 10% target the graph already carries) achievable only to the extent the budget allows. | `world_bank_regulation` — World Bank Regulation of Utilities handbook, revenue caps: "companies are not permitted to recover those costs from captive consumers" (imprudent or unjustified expenditure, cost-of-service review), the ground for capping spend against an allowed budget (`sources/archive/world_bank_regulating_utilities_handbook.pdf`) | `loss_reduction_investment = transmission_loss_reduction_target * allowed_revenue_requirement * 1000000` as an **equality**. Built and measured: it loads, unit-checks consistent, and computes 69.43 USD — because `allowed_revenue_requirement` is in USD *million*, the product needs a 1e6 scale, and the resulting number is an annual revenue share, not a capital spend. As a bound the same operands give 69.43 m against a 50 m budget and **violate** (residual +19.4 m) — which is the finding, not a defect: the graph's own defaults say the loss-reduction target costs more than the budget allows. The final form uses `line_upgrade_budget` (a shipped `USD` free node at 50 m) because the catalog's own arrow names it and the units need no scale. |

### Read-only (no equation of their own)

| node | class | kind | unit | range | role/determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `line_outage_start` | QUALITATIVE | defer | — | — | free / fixed | `--` | A timestamp. Not proposed; see deferrals. | — | `line_outage_start` as an hours-of-year index — see deferrals. |

---

## Verification

Measured on an in-memory `ParameterGraph` built from the shipped document
(`g.nodes`, `g.equations`, `g.edges`) with the eleven retypes and four new nodes
applied, then constructed through `ParameterGraph(...)` so `_validate()` runs. Values
are `propagate` from the defaults-fill used by `audit.py:268`
(`{name: node.default for name, node in g.nodes.items() if node.default is not None}`).

```
load                                    OK   (ParameterGraph constructed, _validate() passed)
symbol check, all 8 rhs + lhs           {}   (zero missing symbols)
lhs appears on rhs                      []   (zero; affine solve path available)

check_equation, all 8:
  thermal_ramp_capability_definition    decidable=True   consistent=True
  thermal_minimum_generation_definition decidable=True   consistent=True
  coal_cycling_ceiling_definition       decidable=True   consistent=True
  storage_energy_capacity_definition    decidable=True   consistent=True
  payment_security_required_definition  decidable=True   consistent=True
  workshop_capacity_workload_bound      decidable=True   consistent=True
  loss_reduction_budget_bound           decidable=True   consistent=True
  asset_age_distribution_definition     decidable=True   consistent=True

propagate at defaults:
  range_excursions                      {}
  violations                            []
  equations on the numeric search path  []   (all eight are affine; solve_paths reports True)

computed values:
  thermal_ramp_capability_mw_per_hour   210.0      = 0.02*3000 + 0.1*1500
  thermal_minimum_generation_mw        1650.0      = 0.4*3000 + 0.3*1500   (36.67% of 4500 MW thermal)
  coal_cycling_ceiling_per_year         876.0      = 8760 / (6 + 4)
  storage_energy_capacity_mwh          4800.0      = 6 * 800
  payment_security_required    64870160.593007125  = 0.01 * 6487016059.300713
  asset_age_distribution                  7.5      = 25 - 17.5

bound residuals (lhs - rhs):
  workshop_capacity_workload_bound      +60.0      (500 - 440; holds)
  loss_reduction_budget_bound      -45000000.0     (5e6 - 5e7; holds)

operands read:
  ramp_rate_coal 0.02 | coal_capacity 3000 | ramp_rate_gas 0.1 | gas_capacity 1500
  min_stable_level_coal 0.4 | min_stable_level_gas 0.3
  min_up_time_coal 6 | min_down_time_coal 4
  storage_capacity_mw 800 | number_of_generators 220 | maintenance_frequency 2
  settlement_risk 0.01 | total_revenue_usd_per_year 6487016059.300713
  line_upgrade_budget 50000000 | asset_life 25 | remaining_useful_life 17.5

uncoupled() before 284  ->  after 273
closed in slice: asset_age_distribution, loss_reduction_investment,
  min_down_time_coal, min_stable_level_coal, min_stable_level_gas,
  min_up_time_coal, payment_security_required, ramp_rate_coal,
  ramp_rate_gas, storage_duration_curve, workshop_capacity
```

Two unit checks failed on the first pass and are recorded here because the failures
are the evidence that the check is live:

- `line_outage_end = line_outage_start + line_outage_duration` — *"adds [time] to
  [time] / [event], which cannot share a dimension"*. The duration is `hours/event`,
  so the window needs an event count. Corrected to
  `line_outage_start + line_outage_duration * outage_frequency` (72 h/year at
  defaults), which unit-checks clean — and then **rejected on other grounds** (see
  deferrals): the node would read a window that pypsa does not honour.
- `payment_security_required` with the tariff × demand form — *"the two sides do not
  share a dimension"*. `demand_twh` is a rate, so the `/ 8760` converts the wrong
  way. The `total_revenue_usd_per_year` form unit-checks clean.

A third check passed and was still rejected: `storage_duration_curve =
(battery_capacity * battery_duration + phs_capacity * phs_duration) / (battery_capacity
+ phs_capacity)` computes 16.8 h, unit-checks consistent, and propagates clean. It
was rejected because it replaces a scenario dial with a weighted average of two LP
variables — not on the endogenous-operand ground `threshold-product-remainder.md`
gave, which measurement refutes (18 shipped equality edges read endogenous operands;
see Rejected).

---

## Deferrals

### BASE-NEEDED (9)

| node | what is missing, checked by name against the graph |
|---|---|
| `microgrid_deployment` | An installed microgrid capacity (MW) or a count of sites. `microgrid_*` returns exactly one node — this one. `mini_grid_deployment` (1/year) is a *different programme* with its own spend equation (`mini_grid_programme_spend_definition`); aliasing onto it would state that every mini-grid is a microgrid. The catalog's other neighbour, `islanding_capability` (8.16/8.17), *is* present (`1`, free, 0.1, read by `islanding_capable_feeders = islanding_capability * distribution_feeders_total`), but `islanded_supply`, which 8.16 makes islanding's own target, is absent — so the chain stops one hop short. |
| `startup_cost_coal` | A count of starts. `starts`, `start_count`, `cold_start`, `hot_start` return nothing. Without one, a per-start cost cannot be determined or read. The archived IEA/NEA text mentions "quick start-up time" once (line 21575) and Short/Packey/Holt mention "preproduction or start-up costs" once (line 5673); neither prints a per-start cost. |
| `startup_cost_gas` | As coal. |
| `nuclear_lead_time` | A nuclear-specific build duration. `construction_period` is a single fleet-average of 30 months and is already the base of `transmission_lead_time`; reusing it would state that a nuclear plant is built in 2.5 years. IEA/NEA say only that construction times "differ considerably and are, on average, somewhat longer for new nuclear" (lines 2175-2177) — a comparative, not a duration. Confirmed deferral from `supply-emissions-grid.md`. |
| `hydro_reservoir_level` | A reservoir energy capacity. `reservoir`, `reservoir_energy`, `hydro_reservoir_energy_mwh` return nothing; `hydro_capacity` is power, and `hydro_drought_multiplier` is an inflow factor. Confirmed deferral. |
| `ac_voltage_limit` | Any voltage dimension. Zero nodes carry a volt-based unit (`kv` returns nothing). Confirmed deferral, on the stronger ground that the node has no unit to be limited in. |
| `wave_energy_converter_type` | A wave-height or converter-efficiency base. `wave` returns five nodes: `marine_wave_capacity` (MW nameplate, 0.0), `wave_energy_converter_cost` (USD/kW, derived, and one of two ids for `capex_marine_wave`), this node, `heatwave_frequency`, and `capex_marine_wave`. There is a resource (nameplate MW) and a cost, but no wave *height* and no converter efficiency, so the catalog's own form `η^wave = f(type, wave height)` has no operand to be a function of. |
| `wind_offshore_platform` | A water depth. `depth`, `water_depth`, `seabed` return nothing. The catalog's form is `C^offshore = f(platform type, depth)`. |
| `coal_retirement_schedule` | A per-unit vintage register. The node is a *retirement year*, not a rate; `coal_retirement_rate` and `coal_retirement_half_life_years` are already determined and are the fleet-level quantities. |

### QUALITATIVE (12)

`condition_based_maintenance`, `failure_rate_curve`, `degradation_model`,
`asset_management_maturity`, `iso_55000_compliance`,
`reliability_centred_maintenance`, `risk_based_maintenance`, `failure_history`,
`maintenance_history`, `line_outage_start`, `line_outage_end`,
`maintenance_schedule`.

Each is a selector, a level, a regime or an event log. No equation is possible
because there is no arithmetic on a level name or an event log — the graph's own
categorical precedent is `market_model` and `market_structure`, which carry
`categories` and are read by no equation either. `failure_rate_curve` deserves a
note: its description is careful that it is "not the curve itself, which is a
function and cannot be a scalar", and it is right. A bathtub curve is a function of
age; the DSL has no function-valued node, and the scalar index is what a Weibull fit
reduces to. It is correctly typed and correctly free.

`maintenance_schedule` is here rather than in BASE-NEEDED for the reason the base
row gives: a schedule is a table of periods — ENTSO-E's "explicit periods in which
specified plants are unavailable for dispatch" — and a scalar node cannot carry it.
`planned_maintenance_hours_per_year` already carries the annual total, so the
missing thing is a shape, not an operand.

`condition_based_maintenance` is here because CBM is a regime, and the only shipped
candidate to alias it onto — `predictive_maintenance_adoption` — is the share of
maintenance already moved into that regime, one level downstream. The alias was
built, unit-checked and measured (0.5 at defaults); see Rejected.

`line_outage_start` / `line_outage_end`: **prior rejection in
`threshold-product-remainder.md` confirmed**, and one more ground added. That pack
rejected the pair because the endpoints are untyped timestamps and because
`docs/prg-status.md:978-995` records that pypsa accepts a dynamic `lines_t.active`
and **never reads it**. This pack re-checked the second ground against the graph and
found the prior pack's last clause wrong: the honoured spelling is
`lines_t.s_max_pu`, a rating, and the graph's rating node is
`transmission_capacity_factor` (`1`, exogenous, 0.5, read by
`transmission_transfer_definition`) — **not** `line_capacity_factor`, which is
**absent** from the graph. The conclusion survives, the citation to it did not.
An hours-of-year retype would make the pair
unit-checkable — `line_outage_end = line_outage_start + line_outage_duration *
outage_frequency` computes 72 h/year and passes `check_equation` — but it would
couple a knob to a field the solver ignores, which is the defect the register exists
to stop, one layer up.

### SCENE-SWITCH (10)

`balancing_market`, `day_ahead_market`, `intraday_market`, `real_time_market`,
`security_constrained_dispatch`, `unit_commitment`, `life_extension_possible`,
`market_coupling`, `trade_agreement`, `maintenance_schedule_optimisation`.

The first seven are booleans; the last three are the same object untyped. None is
read by any equation (checked). `unit_commitment` is the clearest: multiplying it by
anything produces a product of a solver flag. The graph's precedent for a switch
that *is* read is `n_1_criterion`, read by `contingency_reserve_mw_definition` — and
there the switch selects a magnitude (`largest_loss_mw`) that exists independently.
None of these ten has such a magnitude in the slice. `market_coupling` and
`trade_agreement` are the two that could become read operands if a market-price
equation existed; `market_coupling` would multiply `market_traded_volume_twh` and
`trade_agreement` would scale `cross_border_trade_allowed`, but both are shares of a
volume the graph already computes elsewhere and neither is in this slice's jurisdiction.

---

## Dependencies

Operands this pack reads that belong to another slice (named, not proposed here):

- `outage_frequency` (`events/year`, 12.0) — outage slice; needed only by the
  rejected `line_outage_end` equation.
- `mini_grid_deployment` — demand slice; needed only by the rejected
  `microgrid_deployment` bound.
- `line_upgrade_budget` (`USD`, 50 m) — already coupled (read by
  `permitted_transmission_spend_definition`), so no new dependency.
- `total_revenue_usd_per_year`, `settlement_risk`, `storage_capacity_mw`,
  `number_of_generators`, `maintenance_frequency`, `asset_life`,
  `remaining_useful_life` — all already coupled.
  `predictive_maintenance_adoption` is **not** a dependency of this pack: the only
  equation that would have read it (the CBM alias) was rejected.

The four new nodes this pack creates are candidates for adoption by other packs:
`thermal_ramp_capability_mw_per_hour`, `thermal_minimum_generation_mw`,
`coal_cycling_ceiling_per_year` (operational slice) and
`storage_energy_capacity_mwh` (supply slice). A pack that proposes a different id
for any of these should reconcile rather than duplicate.

---

## Sources to fetch

These are needed and **not** in `sources/archive/`, so no citation is offered for
the rows that would use them. A grep over every `.txt` in `sources/archive/` for the
relevant terms returns nothing for the first four.

1. **ISO 55000:2014, Asset management — Overview, principles and terminology.**
   Needed for `iso_55000_compliance`, `asset_management_maturity`, and the maturity
   scale the catalog implies. Not archived; the standard is paywalled, so a
   secondary source that states the maturity ladder would have to be archived
   instead.
2. **A condition-based / reliability-centred / risk-based maintenance reference**
   (e.g. Moubray, *RCM II*, or a utility CBM standard). Needed for
   `condition_based_maintenance`, `reliability_centred_maintenance`,
   `risk_based_maintenance`. Not archived. Without one, the node stays free; the
   alias onto `predictive_maintenance_adoption` was considered and rejected.
3. **A per-start cost table** (e.g. a NREL or EPRI cycling-cost study). Needed for
   `startup_cost_coal` and `startup_cost_gas`, together with a starts count. Not
   archived; IEA/NEA and Short/Packey/Holt mention start-up costs only in passing.
4. **A nuclear construction-duration reference** (e.g. IEA *Nuclear Power* or a
   construction-time dataset). Needed for `nuclear_lead_time`. IEA/NEA state the
   comparative ("somewhat longer") but print no duration.
5. **A transmission loss-reduction cost curve** (USD per percentage point of loss
   reduction). Needed for a `loss_reduction_investment` *equality*; the inequality
   proposed here needs only the budget and does not cite a curve.
6. **A payment-security / credit-support standard** (e.g. an ISDA or exchange
   margin methodology). The World Bank handbook discusses guarantees as regulatory
   instruments but prints no security-sizing identity; the proposed equation is
   cited to it for the regulatory framing, not for the arithmetic.

---

## Rejected

- **`storage_duration_curve` as a capacity-weighted fleet average** —
  `(battery_capacity*battery_duration + phs_capacity*phs_duration) / (battery_capacity
  + phs_capacity)`. Computes 16.8 h, unit-checks consistent, propagates clean, and
  is still rejected — but **not** on the ground `threshold-product-remainder.md`
  gave. That pack said no shipped equality determines a derived node from an
  endogenous operand. Measured: **18 shipped equality edges read an endogenous
  operand** (`firm_capacity_mw` ← `thermal_capacity_mw`, `fleet_employment_intensity_jobs_per_mw`
  ← seven capacities, `fuel_diversity_index`, `hydrogen_storage_capex_usd`). The
  endogenous *lhs* count is what is zero. The real ground is that the weighted mean
  would replace a dial with an average: a scenario that sets the fleet's duration
  could no longer do so, and `battery_capacity`/`phs_capacity` are LP variables, so
  the node would move with the solve rather than describe it.
- **`storage_duration_curve` as the lhs** —
  `storage_duration_curve = storage_energy_capacity_mwh / storage_capacity_mw`.
  Unit-checks clean in principle, and rejected because `storage_energy_capacity_mwh`
  is a node this pack *creates*: making the shipped dial the target and the new node
  the operand inverts which quantity is data and which is arithmetic. The pack's
  form reads the dial and computes the energy.
- **`storage_energy_capacity_mwh = storage_duration_curve * storage_headroom_mw`** —
  the form this pack first proposed, built and measured at **30,000 MWh**, clean.
  Withdrawn on the node's own description: `storage_headroom_mw` is "how far the
  storage builds may exceed the generation fleet's declared size", an allowance on
  the build, not the storage fleet's rating. Multiplying a duration by an allowance
  yields an energy nobody stores. The rating is `storage_capacity_mw` (800 MW at
  defaults), which gives **4,800 MWh**. The `thermal_storage_capacity_bound` this
  form was said to match is itself `thermal_storage_capacity = storage_headroom_mw *
  thermal_storage_duration` — the same conflation, and it is a shipped `leq` bound
  whose lhs is endogenous, so it is not a precedent for an equality.
- **`ac_voltage_limit = 1 + voltage_support_share`** — built and measured: 1.1,
  unit-checks consistent (both dimensionless), propagates clean. Rejected because it
  makes the voltage limit a function of the reactive-support policy share, which is
  a different quantity; `supply-emissions-grid.md` deferred this node and this pack
  agrees the node has no operand, not merely no convenient one.
- **`nuclear_lead_time = construction_period / 12 + cross_border_permitting_time`** —
  computes 4.5 years, unit-checks consistent, propagates clean. Rejected: it is
  `transmission_lead_time`'s exact formula (shipped), so shipping it again would make
  a nuclear plant and a transmission line take the same time to build — the
  comparative the archive states points the other way.
- **`microgrid_deployment >= mini_grid_deployment`** — built, unit-checks consistent,
  propagates clean, and rejected because the two are different programmes; the
  inequality would assert a relationship the catalog does not state.
- **`line_outage_end = line_outage_start + line_outage_duration * outage_frequency`** —
  unit-checks clean after correction and is rejected on the pypsa ground above.
- **`maintenance_schedule = planned_maintenance_hours_per_year * (1 -
  predictive_maintenance_adoption)`** — computes 48 h/year, unit-checks consistent,
  propagates clean. Rejected because it duplicates
  `coordinated_maintenance_hours_per_year` and `predictive_maintenance_hours_per_year`
  (both shipped) in a third spelling, and because a *schedule* is a table, not an
  annual total.
- **`coal_retirement_schedule = coal_retirement_half_life_years`** — computes
  23.10 years, unit-checks consistent. Rejected as an alias that would name a
  *schedule* as a half-life; the two are different objects and the alias would make
  the node look coupled while carrying no new information.
- **`condition_based_maintenance = predictive_maintenance_adoption`** — built and
  measured: it loads, unit-checks consistent, propagates clean, and computes 0.5.
  Rejected because CBM is one *input* to predictive-maintenance adoption, not the
  same object; the alias would make the node look coupled while collapsing two
  distinct shares into one. No archived source states the identity.
- **`ramp_rate_*` and `min_stable_level_*` as MW/MW-per-hour directly** — rejected
  for the per-unit transfer reason in the PRODUCT table.

---

## Findings

**F1. `line_outage_hours_per_year_definition` fails its own unit check, and has
since it shipped.**

```
line_outage_hours_per_year = line_outage_probability * line_outage_duration
```

`check_equation` → **decidable=True, consistent=False**, detail *"the two sides do
not share a dimension"*; measured lhs `dimensionless`, rhs `1 / [event]`. The
operands are `1/year` and `hours/event`; the product is `hours/(year·event)`, which
reduces to `1/[event]` because `hour` and `year` are both `[time]`, against an lhs
in `hours/year`, which reduces to `dimensionless` for the same reason. The identity
needs an events count per year — and the reduction is a second, quieter problem: an
`hours/year` node cannot be dimensionally distinguished from any other pure ratio. A full sweep of all 525 equations returns **11 inconsistent
equations**, and this is one of them; it is the one this slice touches. Evidence:
`.venv/bin/python -c "...check_equation(g.equations['line_outage_hours_per_year_definition'], g)"`.
The fix is an events factor (`outage_frequency` is the shipped node at 12 events/year);
it is out of this pack's scope because it edits a shipped equation rather than
coupling an uncoupled node.

**F2. `coal_price_per_mwh_definition` converts the wrong way by a factor of 12.96.**

```
coal_price_per_mwh = coal_price / (25 * 3.6)
```

Coal at 25 GJ/tonne is 6.944 MWh/tonne, so USD/tonne → USD/MWh is *division by*
6.944, i.e. multiplication by 0.144. The shipped form divides by 90, giving 0.0111.
Measured at defaults: `coal_price = 80` → **0.888889 USD/MWh**; the conversion gives
**11.52 USD/MWh**. Ratio: **12.96**. `check_equation` returns **decidable=True,
consistent=False** — the lhs is `USD/MWh`, the rhs `[currency]/[mass]` — so the
walker does flag this one; the wrong constant happens to be in the wrong place, not
merely the wrong size. The node is currently inert (`coal_price_per_mwh` has
**zero** consumers), and the LCOE path uses the free `fuel_cost_coal` at
12.0 USD/MWh, which is within 4% of the correct conversion — so the defect has not
reached a reported number. It will the moment anyone wires the node in.
`gas_price_per_mwh = gas_price / 0.293` is the *correct* direction for its
conversion (0.293 MWh/MMBtu) and passes `check_equation`; the contrast is what makes
the coal form a transposition rather than a convention.

**F3. Thirty-four placeholder nodes carry a default of 500,000 in ranges whose
upper bound is 1e6.** This is not a defect in any one equation; it is the reason
eleven of this slice's nodes cannot be coupled without a retype first. The retypes
proposed here remove the signature from ten of them; the rest are deferred with the
reason recorded. The pattern is visible in one command:
`.venv/bin/python -c "...; [n for n in names if g.nodes[n].default == 500000.0]"` → 34
of 42.

**F4. The catalog's arrow for `workshop_capacity` points at a node that does not
exist.** `docs/param_eqn.md:893` says `workshop_capacity → repair_time`, and
`repair_time` is absent from the graph (`g.nodes.get('repair_time')` → `None`). The
same is true of `islanded_supply` (8.16). Note that `repair_time` is named as a
target by seven catalog rows (8.3, 8.8, 8.9, 23.7, 23.12, 23.13, 23.14), so its
absence is not a one-row slip. The proposed bound routes the workshop's capacity to
a workload that *does* exist rather than to the missing `repair_time`, which is the
honest coupling available.

---

## Pack check, as run

```python
from alea.prg.service import load_graph
from alea.prg.dsl import parse_side
g = load_graph()
for name, lhs, rhs in [
    ("thermal_ramp_capability_definition", "thermal_ramp_capability_mw_per_hour",
     "ramp_rate_coal * coal_capacity + ramp_rate_gas * gas_capacity"),
    ("thermal_minimum_generation_definition", "thermal_minimum_generation_mw",
     "min_stable_level_coal * coal_capacity + min_stable_level_gas * gas_capacity"),
    ("coal_cycling_ceiling_definition", "coal_cycling_ceiling_per_year",
     "8760 / (min_up_time_coal + min_down_time_coal)"),
    ("storage_energy_capacity_definition", "storage_energy_capacity_mwh",
     "storage_duration_curve * storage_capacity_mw"),
    ("payment_security_required_definition", "payment_security_required",
     "settlement_risk * total_revenue_usd_per_year"),
    ("workshop_capacity_workload_bound", "workshop_capacity",
     "number_of_generators * maintenance_frequency"),
    ("loss_reduction_budget_bound", "loss_reduction_investment", "line_upgrade_budget"),
    ("asset_age_distribution_definition", "asset_age_distribution",
     "asset_life - remaining_useful_life"),
]:
    missing = sorted(s for s in parse_side(rhs).symbols
                     if s not in g.nodes and s != lhs)
    assert not missing, (name, missing)
```

Run against the shipped graph, the four new lhs ids are the only symbols that
resolve to nothing (each is created by this pack). Against the in-memory graph with
the new nodes applied, the check returns `{}` for all eight — recorded in the
Verification block above.
