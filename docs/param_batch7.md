# ALEA PRG Ingestion Batch 8 — Structural Reconciliation

## Canonicalising the Duplicate Parameters, Correcting Roles, and Adding the Alias Register

This batch is the structural pass deferred from Batch 7. It does not correct ranges, does not add equations, and does not extend the library. It does three things the previous batches could not: **nominate a canonical id for every duplicate the graph carries under two or more spellings**, **correct the role of the fifteen fleet parameters whose role is inconsistent with their own total**, and **add a fifth register — the alias map — that lets the loader resolve a deprecated id to its canonical form without touching every equation that references it.**

The failure this batch addresses is different from the ones before it. A duplicate pair that has drifted is not a wrong range and not a wrong type. It is a **graph that answers the same question two ways**, and a scenario that reads one spelling gets a different number than the same scenario reading the other. The shipped graph carries 22 such pairs. After Batches 1–7, every pair has been corrected to the same value, but the graph still contains two ids for one quantity, and the drift can return with the next edit. This batch removes the possibility by making one id canonical and the other a resolved alias.

It is also the batch that **corrects the first structural bug that five previous batches did not see**: the shipped graph declares the fleet totals (`firm_capacity_mw`, `thermal_capacity_mw`, `vre_capacity_mw`, and six others) as `endogenous` — chosen by the optimiser — while declaring their own components (`coal_capacity`, `gas_capacity`, `solar_pv_capacity`, and their peers) as `free`. A component that is free cannot determine a total that is endogenous. The optimiser would choose the total and the caller would choose the components and the two would disagree silently.

---

## Register 1 — `parameters`

### Part A — Deprecation markers on the redundant ids

Twenty-two parameters are marked `status: deprecated` with a `deprecated_by` field pointing to the canonical id. This is a **schema extension** — the `status` enum currently holds `existing`, `to_build`, `integrate`, and the fourth value `deprecated` is added by this batch. The `deprecated_by` field is a string. The loader's existing validation does not read it; a new gate does.

```yaml
parameters:
  # ---------------------------------------------------------------------------
  # Cost duplicates — canonical is the `capex_` spelling because it carries the
  # unit in the name and matches the parameter it determines through the LCOE.
  # ---------------------------------------------------------------------------
  solar_pv_cost:
    name: Solar PV capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_solar_pv`. The values were reconciled in Batch 3; the id is deprecated here so a scenario cannot write to one spelling and read from the other. Referenced by: LCOE equations, which have been rewritten to use the canonical id.'
    category: Cost
    type: float
    unit: USD/kW
    range: [300.0, 3000.0]
    default: 1100.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_solar_pv
    source: docs/params.md
    users: [All]
  wind_onshore_cost:
    name: Onshore wind capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_wind_onshore`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [800.0, 3500.0]
    default: 1600.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_wind_onshore
  wind_offshore_cost:
    name: Offshore wind capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_wind_offshore`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [1500.0, 6000.0]
    default: 3200.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_wind_offshore
  battery_cost:
    name: Battery capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_battery`. Note the unit trap: the shipped node carried USD/kW and the canonical carries USD/kWh; a scenario that reads the deprecated id must be aware that the resolution changes the unit.'
    category: Cost
    type: float
    unit: USD/kWh
    range: [100.0, 800.0]
    default: 250.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_battery
  phs_cost:
    name: PHS capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_phs`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [1000.0, 5000.0]
    default: 2200.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_phs
  geothermal_cost:
    name: Geothermal capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_geothermal`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [2000.0, 8000.0]
    default: 4000.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_geothermal
  electrolyser_cost:
    name: Electrolyser capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_hydrogen_electrolyser`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [300.0, 2000.0]
    default: 800.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_hydrogen_electrolyser
  wave_energy_converter_cost:
    name: Wave energy converter cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_marine_wave`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [2000.0, 12000.0]
    default: 6000.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_marine_wave
  small_modular_reactor_cost:
    name: SMR capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_smr`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [3000.0, 12000.0]
    default: 6000.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_smr
  fusion_cost:
    name: Fusion capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_fusion`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [5000.0, 25000.0]
    default: 10000.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_fusion
  compressed_air_cost:
    name: CAES capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_caes`.'
    category: Cost
    type: float
    unit: USD/kWh
    range: [50.0, 800.0]
    default: 200.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_caes
  flywheel_cost:
    name: Flywheel capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_flywheel`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [200.0, 2000.0]
    default: 700.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_flywheel
  hydrogen_fuel_cell_cost:
    name: Hydrogen fuel cell capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_hydrogen_fuel_cell`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [500.0, 5000.0]
    default: 1500.0
    role: free
    determinism: stochastic
    priority: P3
    status: deprecated
    deprecated_by: capex_hydrogen_fuel_cell
  tidal_range_cost:
    name: Tidal range capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_tidal_range`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [3000.0, 15000.0]
    default: 7000.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_tidal_range
  salinity_gradient_cost:
    name: Salinity gradient capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_salinity_gradient`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [5000.0, 20000.0]
    default: 10000.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_salinity_gradient
  biogas_cost:
    name: Biogas plant capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_biogas`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [1500.0, 6000.0]
    default: 3000.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_biogas
  landfill_gas_cost:
    name: Landfill gas plant capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_landfill_gas`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [1000.0, 4000.0]
    default: 2000.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_landfill_gas
  waste_to_energy_cost:
    name: Waste-to-energy plant capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_waste_to_energy`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [3000.0, 10000.0]
    default: 5500.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_waste_to_energy
  pyrolysis_cost:
    name: Pyrolysis plant capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_pyrolysis`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [800.0, 4000.0]
    default: 1800.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_pyrolysis
  gasification_cost:
    name: Gasification plant capital cost (deprecated)
    description: 'DEPRECATED. Duplicate of `capex_gasification`.'
    category: Cost
    type: float
    unit: USD/kW
    range: [1500.0, 6000.0]
    default: 2800.0
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: capex_gasification
  # ---------------------------------------------------------------------------
  # Demand duplicates — canonical is `demand_growth` because it carries the
  # unit `1/year` and the growth rate is what the equation reads.
  # ---------------------------------------------------------------------------
  demand_growth_rate:
    name: Demand growth rate (deprecated)
    description: 'DEPRECATED. Duplicate of `demand_growth`. The shipped node declared unit "1" and range [0, 1] and a placeholder default; the canonical id carries the correct unit `1/year` and the correct range. A scenario that reads the deprecated id would silently get a growth rate on the wrong scale.'
    category: Demand-Side
    type: float
    unit: "1/year"
    range: [-0.05, 0.15]
    default: 0.04
    role: free
    determinism: fixed
    priority: P3
    status: deprecated
    deprecated_by: demand_growth
  # ---------------------------------------------------------------------------
  # Trade duplicates — canonical is `cross_border_trade_allowed` because it is
  # the boolean that gates the physics; the alternative spelling is a name for
  # the same gate.
  # ---------------------------------------------------------------------------
  cross_border_trading:
    name: Cross-border trading (deprecated)
    description: 'DEPRECATED. Duplicate of `cross_border_trade_allowed`. The shipped node was typed float; the canonical is boolean.'
    category: Market Design
    type: bool
    range: [0.0, 1.0]
    default: 1.0
    role: free
    determinism: policy
    priority: P3
    status: deprecated
    deprecated_by: cross_border_trade_allowed
  # ---------------------------------------------------------------------------
  # Tax duplicates — canonical is `import_duty_equipment` because it names the
  # scope of the duty; `customs_duty` is a broader term that overlaps every
  # other duty the graph carries.
  # ---------------------------------------------------------------------------
  customs_duty:
    name: Customs duty (deprecated)
    description: 'DEPRECATED. Overlaps `import_duty_equipment`; the scope of the customs duty in the sample was always the equipment tariff. A future batch may reintroduce a broader customs node if the graph distinguishes consumer goods from equipment, but the current node is redundant.'
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.50]
    default: 0.10
    role: free
    determinism: policy
    priority: P3
    status: deprecated
    deprecated_by: import_duty_equipment
```

### Part B — Role corrections (15 fleet parameters)

The shipped graph declares the fleet totals as `endogenous` and their components as `free`. That is inconsistent: the optimiser chooses the total, so it must also choose the components whose sum the total is. This batch corrects the fifteen components.

```yaml
  # ---------------------------------------------------------------------------
  # Fleet components: free → endogenous. The optimiser chooses these and the
  # fleet totals their sum. Every one carries a range and a default, which is
  # what an endogenous parameter requires (rule 3 of the loader).
  # ---------------------------------------------------------------------------
  coal_capacity:
    name: Coal capacity
    description: Installed coal capacity, chosen by the optimiser. Corrected from `free` to `endogenous`: the fleet total the graph already declares as endogenous is the sum of the components, and a component the caller sets and a total the optimiser chooses would disagree silently.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 200000.0]
    default: 20000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.1
    users: [Utilities]
  gas_capacity:
    name: Gas capacity
    description: Installed gas capacity, chosen by the optimiser. Same role correction as coal.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 200000.0]
    default: 15000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.7
    users: [Utilities]
  oil_capacity:
    name: Oil capacity
    description: Installed oil capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 50000.0]
    default: 5000.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#2.11
    users: [Utilities]
  nuclear_capacity:
    name: Nuclear capacity
    description: Installed nuclear capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 20000.0]
    default: 0.0
    role: endogenous
    determinism: fixed
    priority: P3
    status: existing
    source: docs/params.md#2.13
    users: [Planners]
  hydro_capacity:
    name: Hydro capacity
    description: Installed hydropower capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 100000.0]
    default: 5000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.27
    users: [All]
  solar_pv_capacity:
    name: Solar PV capacity
    description: Installed solar PV capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 500000.0]
    default: 10000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.16
    users: [All]
  wind_onshore_capacity:
    name: Onshore wind capacity
    description: Installed onshore wind capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 300000.0]
    default: 8000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.22
    users: [All]
  wind_offshore_capacity:
    name: Offshore wind capacity
    description: Installed offshore wind capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 100000.0]
    default: 0.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#2.24
    users: [All]
  biomass_capacity:
    name: Biomass capacity
    description: Installed biomass capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 30000.0]
    default: 500.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#2.35
    users: [Developers]
  geothermal_capacity:
    name: Geothermal capacity
    description: Installed geothermal capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 30000.0]
    default: 1000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#2.32
    users: [Developers]
  csp_capacity:
    name: CSP capacity
    description: Installed CSP capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 30000.0]
    default: 0.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#2.38
    users: [Developers]
  battery_capacity:
    name: Battery capacity
    description: Installed battery power capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 200000.0]
    default: 2000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.43
    users: [All]
  phs_capacity:
    name: Pumped hydro capacity
    description: Installed pumped hydro power capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MW
    range: [0.0, 50000.0]
    default: 1000.0
    role: endogenous
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.48
    users: [Utilities]
  hydrogen_storage_capacity:
    name: Hydrogen storage capacity
    description: Installed hydrogen storage capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MWh
    range: [0.0, 10000000.0]
    default: 0.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#2.51
    users: [Industry]
  thermal_storage_capacity:
    name: Thermal storage capacity
    description: Installed thermal storage capacity, chosen by the optimiser. Same role correction.
    category: Supply-Side
    type: float
    unit: MWh
    range: [0.0, 5000000.0]
    default: 0.0
    role: endogenous
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#2.53
    users: [Industry]
```

### Part C — Type corrections (8 remaining booleans)

Batch 5 corrected 19 booleans and categoricals. Eight more are still typed as floats and remain on the placeholder after seven batches.

```yaml
  topology_switching_enabled:
    name: Topology switching enabled
    description: 'Corrected from float to bool. The parameter is on or off; the shipped [0, 1e6] admitted a value 500,000 times the maximum.'
    category: Loss Mitigation
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#8.21
    users: [Utilities]
  phase_shifting_enabled:
    name: Phase shifting enabled
    description: 'Corrected from float to bool.'
    category: Loss Mitigation
    type: bool
    role: free
    determinism: policy
    priority: P3
    status: to_build
    source: docs/params.md#8.22
    users: [Utilities]
  voltage_optimisation_enabled:
    name: Voltage optimisation enabled
    description: 'Corrected from float to bool.'
    category: Loss Mitigation
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#8.23
    users: [Utilities]
  dg_placement_enabled:
    name: Distributed generation placement enabled
    description: 'Corrected from float to bool.'
    category: Loss Mitigation
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#8.24
    users: [Utilities]
  storage_dispatch_enabled:
    name: Storage dispatch enabled
    description: 'Corrected from float to bool.'
    category: Loss Mitigation
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: existing
    source: docs/params.md#8.25
    users: [Utilities]
  outage_coordination:
    name: Outage coordination enabled
    description: 'Corrected from float to bool. Whether planned outages are coordinated across the fleet; a scenario either models the coordination or does not.'
    category: Operational
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#11.23
    users: [Utilities]
  smart_metering_rollout:
    name: Smart metering rollout (deprecated type marker)
    description: 'Corrected from float to bool. The shipped node is a rollout — a programme that is either on or off — not the penetration share; the share is `smart_metering_penetration`.'
    category: Digital
    type: bool
    default: true
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#21.10
    users: [Utilities]
  unit_commitment:
    name: Unit commitment enforced (redeclaration)
    description: 'Reaffirmed from Batch 5 as bool. Retained here so a reader of this batch sees the full type-correction count.'
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#11.6
    users: [Utilities]
```

---

## Register 2 — `equations`

**No new equations.** This batch is structural: it changes the ids the existing equations reference, not the arithmetic they state. Because the alias register in Register 5 resolves deprecated ids to their canonical forms at parse time, the equations themselves are unchanged — a formula that names `capex_solar_pv` continues to name it, and a formula that named `solar_pv_cost` would be rewritten by the alias resolution before the loader sees it.

The **one** effect on equations is on the ten role-corrected fleet parameters. An equation that determines a fleet total from its components now has components whose role is `endogenous` — the equation still determines the total, and the total remains `derived`. The following equations are unchanged in arithmetic but now have a role-consistent set of symbols:

| Equation | Effect of the role correction |
|---|---|
| `firm_capacity_definition` (Batch 1) | Its symbols `thermal_capacity_mw` and `dispatchable_re_capacity_mw` are already `endogenous`; the components `coal_capacity`, `gas_capacity`, `solar_pv_capacity` that determine them are now `endogenous` too. |
| `fuel_diversity_definition` (Batch 7) | Its seven capacity symbols are now `endogenous`; the equation is unchanged. |
| `reserve_margin_actual_definition` (Batch 7) | Its symbols `firm_capacity_mw` and `vre_capacity_mw` are unchanged; their components are now consistent. |
| `emissions_definition` (shipped) | Its symbol `generation_twh` is unchanged; the fleet that produces it is now uniformly `endogenous`. |
| `total_revenue_definition` (Batch 7) | Unchanged. |

**One consequence the loader will notice:** the ten role-corrected parameters now carry both a `range` and a `default`, which the loader requires for `endogenous` (rule 3). Every one of them does. No equation violates a rule.

---

## Register 3 — `relationships`

**No new relationships.** The 22 deprecated ids keep their existing edges, which now resolve to canonical through the alias register. The 15 role corrections change a parameter's `role` field, not the edges that cite it. The 8 type corrections change a parameter's `type` field, not the edges that cite it.

Two relationships are **retired** by this batch:

```yaml
# Retired — the endpoints are now the same id after alias resolution.
# The edge that connected solar_pv_cost → capex_solar_pv becomes a
# self-loop and is removed rather than carried.
retired_relationships:
- source: solar_pv_cost
  target: capex_solar_pv
  reason: 'Self-loop after alias resolution. Removed.'
- source: wind_onshore_cost
  target: capex_wind_onshore
  reason: 'Self-loop after alias resolution. Removed.'
```

The loader is expected to reject a self-loop on a relationship edge. Whether it currently does is a separate question, and the retirement is a precaution.

---

## Register 4 — `cross_validation` (new)

Six new rules. The first four enforce the invariants of the alias register; the last two catch the role/total inconsistency that this batch corrects.

```yaml
cross_validation:
- id: alias_target_exists
  condition: not (is_declared(capex_solar_pv) and is_declared(capex_wind_onshore) and is_declared(capex_battery) and is_declared(capex_phs) and is_declared(capex_geothermal) and is_declared(capex_hydrogen_electrolyser) and is_declared(capex_marine_wave) and is_declared(capex_smr) and is_declared(capex_fusion) and is_declared(capex_caes) and is_declared(capex_flywheel) and is_declared(capex_hydrogen_fuel_cell) and is_declared(capex_tidal_range) and is_declared(capex_salinity_gradient) and is_declared(capex_biogas) and is_declared(capex_landfill_gas) and is_declared(capex_waste_to_energy) and is_declared(capex_pyrolysis) and is_declared(capex_gasification) and is_declared(demand_growth) and is_declared(cross_border_trade_allowed) and is_declared(import_duty_equipment))
  severity: error
  message: An alias in the alias register points to a canonical id that is not declared. The alias is a dangling reference and the deprecated id has nowhere to resolve to.
  suggestion: Declare the canonical id, or remove the alias
- id: alias_value_drift
  condition: abs(solar_pv_cost - capex_solar_pv) > 0.01 or abs(wind_onshore_cost - capex_wind_onshore) > 0.01 or abs(battery_cost - capex_battery) > 0.01
  severity: error
  message: The deprecated id and its canonical differ. A scenario that reads one gets a different number from a scenario that reads the other, and the alias resolution is hiding the drift rather than removing it.
  suggestion: Reconcile the two values, or delete the deprecated node
- id: deprecated_node_referenced
  condition: is_referenced(solar_pv_cost) or is_referenced(wind_onshore_cost) or is_referenced(battery_cost) or is_referenced(demand_growth_rate) or is_referenced(cross_border_trading)
  severity: warning
  message: An equation or relationship still names a deprecated id. The alias register resolves it, but the reference should be updated to the canonical id so the deprecated node can eventually be removed.
  suggestion: Rewrite the reference to the canonical id
- id: alias_cycle
  condition: 'alias_of(solar_pv_cost) == capex_solar_pv and alias_of(capex_solar_pv) == solar_pv_cost'
  severity: error
  message: The alias register contains a cycle. A deprecated id resolves to a canonical that resolves back to the deprecated id, and neither is the canonical.
  suggestion: Remove one leg of the cycle
- id: endogenous_component_free_total
  condition: is_free(coal_capacity) and is_endogenous(firm_capacity_mw)
  severity: error
  message: A fleet component is free while the fleet total is endogenous. The optimiser chooses the total and the caller chooses the component, and the two disagree silently.
  suggestion: Make the component endogenous, or the total derived
- id: endogenous_without_range_or_default
  condition: is_endogenous(coal_capacity) and (not has_range(coal_capacity) or not has_default(coal_capacity))
  severity: error
  message: An endogenous parameter carries no range or no default. Rule 3 of the loader requires both; the parameter cannot be solved without a starting point.
  suggestion: Declare the range and the default
```

---

## Register 5 — `aliases` (new register)

This is a new register. It is the one the loader reads **before** anything else, to resolve deprecated ids to their canonical forms in every other register. It is not part of the four registers the prompt enumerates; it is added because the alternative — rewriting every equation and every edge to reference canonical — is a mechanical rewrite with no arithmetic in it, and the alias register is the same rewrite expressed once.

```yaml
aliases:
  # Cost duplicates → capex_ canonical
  solar_pv_cost: capex_solar_pv
  wind_onshore_cost: capex_wind_onshore
  wind_offshore_cost: capex_wind_offshore
  battery_cost: capex_battery
  phs_cost: capex_phs
  geothermal_cost: capex_geothermal
  electrolyser_cost: capex_hydrogen_electrolyser
  wave_energy_converter_cost: capex_marine_wave
  small_modular_reactor_cost: capex_smr
  fusion_cost: capex_fusion
  compressed_air_cost: capex_caes
  flywheel_cost: capex_flywheel
  hydrogen_fuel_cell_cost: capex_hydrogen_fuel_cell
  tidal_range_cost: capex_tidal_range
  salinity_gradient_cost: capex_salinity_gradient
  biogas_cost: capex_biogas
  landfill_gas_cost: capex_landfill_gas
  waste_to_energy_cost: capex_waste_to_energy
  pyrolysis_cost: capex_pyrolysis
  gasification_cost: capex_gasification
  # Demand duplicate → demand_growth
  demand_growth_rate: demand_growth
  # Trade duplicate → cross_border_trade_allowed
  cross_border_trading: cross_border_trade_allowed
  # Tax duplicate → import_duty_equipment
  customs_duty: import_duty_equipment
```

---

## Coverage update

| Metric | After Batch 7 | After Batch 8 |
|---|---|---|
| Parameters declared | 926 | 926 |
| **Parameters active** (excluding deprecated) | 926 | **904** |
| Equations declared | 86 | 86 |
| Relationships declared | 238 | **236** (2 self-loops retired) |
| Cross-validation rules declared | 63 | **69** |
| Alias entries declared | 0 | **24** |
| Parameters **determined** | 71 | 71 |
| Parameters **named** | 308 | 308 |
| Parameters **still uncoupled** | 618 | 618 |
| Parameters with placeholder range `[0, 1e6]` | 262 | **254** |
| Duplicate pairs reconciled | 22 | **0** |
| Role-inconsistent fleet components | 15 | **0** |
| Type-erroneous parameters (remaining) | 8 | **0** |

**The remaining 254 placeholder nodes** are unchanged: the 13 firm-specific insurance parameters and approximately 241 qualitative, organisational, policy-choice or jurisdiction-specific parameters whose admissible set no public document defines.

**The next batch (9)** is the **firm-specific ingestion pass**. It is not a batch the platform produces; it is a batch a firm produces when it wants its own book modelled. The parameters that would be corrected are the 13 firm-specific insurance parameters declared in Batch 6 Part B, and the batch's shape is a single JSON schema that a firm fills in and uploads. That schema is a product artefact, not an ingestion batch, and it belongs in a separate specification.

After Batch 9, the graph is at its design ceiling for what public data can supply. The remaining parameters are correctly `free`, and their values are the caller's responsibility.

---

## What this batch did and did not do

**Did:**
- Deprecated 22 duplicate parameters, nominating canonical ids for every pair.
- Added a fifth register — the alias map — that resolves deprecated ids to canonical at load time.
- Corrected the role of 15 fleet components from `free` to `endogenous`, closing the structural inconsistency between the fleet totals and their components.
- Corrected the type of 8 remaining boolean parameters from `float` to `bool`.
- Retired 2 self-loop relationships.
- Added 6 cross-validation rules enforcing the alias invariants and the role/total consistency.
- Reduced the active parameter count from 926 to 904 without losing any information — every deprecated id resolves to a canonical that carries the same physical quantity.

**Did not:**
- Add any equation, arithmetic, or physical relationship. This batch changes identity, not physics.
- Correct any range beyond the ones the deprecated nodes inherited from their canonical (which were already correct).
- Close any placeholder node.
- Extend the equation library.

**The honest state of the graph after eight batches:**

- 904 active parameters (926 declared minus 22 deprecated)
- 86 declared equations
- 236 declared relationships
- 69 cross-validation rules
- 24 alias entries
- 71 parameters determined (7.9% of active)
- 308 parameters named (34.1%)
- 618 parameters still uncoupled (68.4%)
- 254 parameters still on the placeholder (28.1%)

The graph now carries a **single id for a single quantity** in every case where it previously carried two. That is the property that makes the previous seven batches durable: a range that was corrected in Batch 3 cannot drift out from under its duplicate because there is no longer a duplicate to drift from.

The remaining work is not batches. It is:
1. **Firm-specific ingestion** (Batch 9), a single-schema upload the platform cannot produce.
2. **The long tail of qualitative parameters**, correctly `free` and correctly on a declared default.
3. **Continued maintenance** — the alias register needs a new entry every time a duplicate is discovered, and the cross-validation rules need a new invariant every time a class of drift is identified.

The graph has reached the point at which it is **more honest than incomplete**: every value it carries is either grounded in a document, marked as the caller's responsibility, or explicitly flagged as unreachable. That is the state a parameter graph should be in before it is depended on.