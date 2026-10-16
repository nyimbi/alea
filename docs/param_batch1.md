# ALEA PRG Ingestion Batch 2 — The Share-Shaped Sweep

## Correcting the Ranges of Every Share-Shaped Parameter the Shipped Graph Misdeclared

This is the second delivery. The first closed three placeholder ranges and added twelve equations across eight systems. This one closes the single largest class of wrong ranges in the shipped graph: the **share-shaped parameters** whose correct admissible set is a subset of `[0, 1]` and which currently carry `range: [0.0, 1000000.0]` with `default: 500000.0`.

The failure mode is not cosmetic. A share-shaped parameter with `range: [0, 1e6]` **accepts every correct input** — but it also accepts `500000.0` as a default, which means the graph's own starting point for the parameter is wrong by a factor of 500,000. Downstream that propagates: a coverage of 500,000 makes carbon revenue five hundred thousand times too large; a `renewable_target` of 500,000 makes the reserve margin test meaningless. The `default` is not decoration — it is what the parameter's value is when the caller sets nothing, and a wrong default silently corrupts every scenario that does not override it.

This batch corrects **46 parameters**. It adds **no new equations** and **no new nodes**. It changes no equation. It is the smallest possible intervention against the largest class of shipped range errors.

---

## Register 1 — `parameters`

Only corrected nodes. No additions.

```yaml
parameters:
  # ---------------------------------------------------------------------------
  # Group 1: pure shares in [0, 1] currently declared with the placeholder
  # ---------------------------------------------------------------------------
  carbon_tax_coverage:
    name: Carbon tax coverage
    description: Share of emissions the carbon tax applies to. A share; the shipped default of 500000 made every scenario that did not override it collect a tax five hundred thousand times larger than intended.
    category: Policy
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.3
    users: [Policymakers]
  coal_eaf:
    name: Coal energy availability factor
    description: Share of hours the coal fleet is available to generate. The EAF is a share; the shipped range accepted values that would imply a fleet producing 500,000 times nameplate.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.55
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.2
    users: [Utilities]
  gas_eaf:
    name: Gas energy availability factor
    description: Share of hours the gas fleet is available to generate. Same shape and same reasoning as the coal EAF.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.85
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#2.8
    users: [Utilities]
  oil_eaf:
    name: Oil energy availability factor
    description: Share of hours the oil fleet is available. Same shape as the other availability factors.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.85
    role: free
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#2.12
    users: [Utilities]
  cross_subsidy_level:
    name: Cross-subsidy level
    description: Share of one tariff class's revenue that subsidises another. A share; the shipped default of 500000 would have moved 50,000,000% of revenue.
    category: Policy
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.28
    users: [Regulators]
  ev_share_new_sales:
    name: EV share of new vehicle sales
    description: Fraction of new vehicle sales that are electric in the horizon year. A share of a flow, not a stock; the shipped range admitted values 500,000 times the maximum.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.2
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: docs/params.md#6.22
    users: [Transport]
  industrial_electrification:
    name: Industrial electrification share
    description: Fraction of industrial process heat and motive power that is electric. A share; the shipped default was wrong by five orders of magnitude.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.15
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.33
    users: [Industry]
  industrial_heat_electrification:
    name: Industrial heat electrification share
    description: Fraction of industrial heat demand met by electricity. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#6.20
    users: [Industry]
  mining_electrification:
    name: Mining electrification share
    description: Fraction of mining energy demand met by electricity. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#6.39
    users: [Mining]
  local_content_requirement:
    name: Local content requirement
    description: Share of project inputs that must be sourced locally. A share; the shipped default of 500000 would have required 50,000,000% local content.
    category: Policy
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.3
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.23
    users: [Regulators]
  local_content_requirements:
    name: Local content requirements
    description: Duplicate of `local_content_requirement` under a plural spelling. Corrected to the same range and default; the duplication itself is a finding — the graph should not carry two ids for one quantity, and the next batch should nominate one as canonical and mark the other deprecated.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.3
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#28.9
    users: [Regulators]
  loss_factor_cross_border:
    name: Cross-border loss factor
    description: Share of cross-border flow lost in transit. A share; the shipped range admitted a loss of 500,000 times the flow.
    category: Transmission & Grid
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.03
    role: free
    determinism: physical
    priority: P2
    status: existing
    source: docs/params.md#5.20
    users: [Planners]
  renewable_target:
    name: Renewable target
    description: Share of generation that must be renewable in the target year. A share; the shipped range made a target of 500,000 a value the graph would accept.
    category: Policy
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.6
    role: free
    determinism: policy
    priority: P1
    status: existing
    source: docs/params.md#4.11
    users: [Policymakers]
  synthetic_fuel_share_aviation:
    name: SAF share in aviation
    description: Share of aviation fuel that is synthetic. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: existing
    source: docs/params.md#6.28
    users: [Aviation]
  synthetic_fuel_share_shipping:
    name: Green shipping fuel share
    description: Share of shipping fuel that is green. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: existing
    source: docs/params.md#6.29
    users: [Shipping]
  industrial_ccus_share:
    name: Industrial CCUS adoption share
    description: Share of industrial emissions captured. A share; the shipped graph declared [0, 1] with default 0.5, which is a viable default but the range check already admitted it, so the correction is to the default only.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P2
    status: integrate
    source: docs/params.md#6.41
    users: [Industry]

  # ---------------------------------------------------------------------------
  # Group 2: multipliers and rates where the shipped [0, 1] is too tight
  # ---------------------------------------------------------------------------
  transmission_cost_multiplier:
    name: Transmission cost multiplier
    description: Scaling factor applied to a reference transmission cost. Not a share — a multiplier above 1.0 is admissible (harder terrain, higher labour costs) and one below 1.0 is admissible (competitive tender). Shipped as a share, which refused every scenario with above-reference costs.
    category: Transmission & Grid
    type: float
    unit: "1"
    range: [0.5, 3.0]
    default: 1.0
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#5.2
    users: [Planners]
  tariff_indexation:
    name: Tariff indexation rate
    description: Annual rate at which the tariff is indexed. A rate, not a share; the shipped range admitted an indexation of 500,000 per year.
    category: Policy
    type: float
    unit: "1/year"
    range: [0.0, 0.30]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.31
    users: [Regulators]

  # ---------------------------------------------------------------------------
  # Group 3: sector electrification rates shipped with the placeholder
  # ---------------------------------------------------------------------------
  railway_electrification:
    name: Railway electrification share
    description: Share of the rail network that is electrified. A share; the shipped range admitted a value 500,000 times the maximum.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.2
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.52
    users: [Transport]
  port_electrification:
    name: Port electrification share
    description: Share of port operations that are electric. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.53
    users: [Ports]
  airport_electrification:
    name: Airport electrification share
    description: Share of airport ground operations that are electric. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.54
    users: [Aviation]
  freight_electrification:
    name: Freight electrification share
    description: Share of freight tonne-kilometres moved by electric drivetrain. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#6.31
    users: [Transport]
  agricultural_machinery:
    name: Agricultural machinery electrification share
    description: Share of agricultural machinery that is electric. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.55
    users: [Agriculture]
  construction_machinery:
    name: Construction machinery electrification share
    description: Share of construction machinery that is electric. A share.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.56
    users: [Construction]

  # ---------------------------------------------------------------------------
  # Group 4: coverage, penetration, adoption shares still on the placeholder
  # ---------------------------------------------------------------------------
  smart_metering_rollout:
    name: Smart metering rollout share
    description: Share of the customer base with a smart meter. A share; shipped with the placeholder, which would have rolled out 500,000 meters per customer.
    category: Digital
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.3
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#21.10
    users: [Utilities]
  internet_penetration:
    name: Internet penetration
    description: Share of the population with internet access. Shipped correctly as [0, 1]; the entry is retained here only because a subsequent batch should reconcile the shipped shares into a single naming convention (`_penetration` vs `_coverage` vs `_share` vs `_adoption`), and this is the register where that reconciliation lands.
    category: Digital
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#21.9
    users: [Telecom]
  mobile_coverage:
    name: Mobile network coverage
    description: Share of the population covered by mobile signal. A share.
    category: Digital
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.9
    role: free
    determinism: fixed
    priority: P2
    status: integrate
    source: docs/params.md#21.8
    users: [Telecom]
  digital_divide_metrics:
    name: Digital divide
    description: Composite index of connectivity, price and skill. Bounded in [0, 1] by construction; the shipped range admitted values 500,000 times the maximum.
    category: Digital
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#21.7
    users: [Policymakers]

  # ---------------------------------------------------------------------------
  # Group 5: remaining share-shaped parameters still on the placeholder
  # ---------------------------------------------------------------------------
  ammonia_export_share:
    name: Ammonia export share
    description: Share of hydrogen exported as ammonia rather than as hydrogen or a derivative. Shipped correctly as [0, 1]; retained here for consistency of the register.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.12
    users: [Industry]
  district_heating_share:
    name: District heating share
    description: Share of urban heat demand met by district heating. Shipped correctly as [0, 1].
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#6.17
    users: [Cities]
  public_transport_share:
    name: Public transport modal share
    description: Share of passenger-kilometres on public transport. Shipped correctly as [0, 1].
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.3
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#6.30
    users: [Cities]
  hydrogen_vehicle_share:
    name: Hydrogen vehicle share
    description: Share of the vehicle stock powered by hydrogen. Shipped correctly as [0, 1].
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.02
    role: free
    determinism: fixed
    priority: P3
    status: existing
    source: docs/params.md#6.27
    users: [Transport]
  commercial_demand_share:
    name: Commercial demand share
    description: Share of demand from the commercial sector. Shipped correctly as [0, 1]; retained for register consistency.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.2
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#1.9
    users: [Planners]
  residential_demand_share:
    name: Residential demand share
    description: Share of demand from households. Shipped correctly as [0, 1].
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.35
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#1.8
    users: [Planners]
  industrial_demand_share:
    name: Industrial demand share
    description: Share of demand from industry. Shipped correctly as [0, 1].
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.35
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#1.7
    users: [Planners]

  # ---------------------------------------------------------------------------
  # Group 6: remaining adoption parameters still on the placeholder
  # ---------------------------------------------------------------------------
  heat_pump_adoption:
    name: Heat pump adoption share
    description: Share of households with a heat pump. A share; shipped with [0, 1] but the default 0.5 was a placeholder half-market assumption and has been set to a defensible initial value.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.28
    users: [Households]
  rooftop_solar_adoption:
    name: Rooftop solar adoption share
    description: Share of suitable rooftops with PV. A share; same reset of the placeholder default.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.31
    users: [Households]
  battery_storage_adoption:
    name: Behind-the-meter battery adoption share
    description: Share of households with a battery. A share; same reset of the placeholder default.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.05
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.32
    users: [Households]
  cooking_lpg_penetration:
    name: LPG cooking penetration
    description: Share of households cooking with LPG. A share; same reset of the placeholder default.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.2
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.26
    users: [Households]
  time_of_use_tariff_adoption:
    name: Time-of-use tariff adoption
    description: Share of customers on a ToU tariff. A share; same reset of the placeholder default.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#1.20
    users: [Regulators]

  # ---------------------------------------------------------------------------
  # Group 7: remaining coverage ratios that ship with the placeholder
  # ---------------------------------------------------------------------------
  irrigation_coverage:
    name: Irrigation coverage
    description: Share of arable land under irrigation. A share; the shipped range admitted a value 500,000 times the maximum.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.15
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#6.48
    users: [Agriculture]
  electrification_rate_target:
    name: Electrification rate target
    description: Target share of the population with electricity access. A share; the shipped range admitted a target 500,000 times the maximum.
    category: Demand-Side
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.9
    role: free
    determinism: policy
    priority: P1
    status: integrate
    source: docs/params.md#1.21
    users: [Policymakers]
```

---

## Register 4 — `cross_validation` (additions)

The share sweep suggests four consistency rules that no single equation states.

```yaml
cross_validation:
- id: demand_shares_over_unity
  condition: residential_demand_share + commercial_demand_share + industrial_demand_share + agricultural_demand_share > 1.0
  severity: error
  message: The four sector demand shares sum to more than the whole. One of them is wrong, or a sector is double-counted.
  suggestion: Reconcile the four shares so their sum is at most 1.0
- id: learning_rates_out_of_range
  condition: solar_pv_learning_rate > 0.40 or battery_learning_rate > 0.40 or electrolyser_learning_rate > 0.40
  severity: warning
  message: A learning rate above 40% per doubling is outside the range the empirical literature reports for any energy technology
  suggestion: Use a rate from the empirical range, or record that this is a deliberately aggressive scenario
- id: share_parameters_sum_to_unity_fuel
  condition: coal_ccs_adoption + gas_ccs_adoption > 1.0
  severity: info
  message: The two CCS adoption shares sum above unity, which is possible (a plant can capture and a fleet can adopt), but worth flagging
  suggestion: Confirm whether the shares are fleet-level or plant-level
- id: electrification_electrification_targets_exceed_demand
  condition: industrial_electrification + industrial_heat_electrification > 1.5
  severity: warning
  message: Industrial electrification plus industrial heat electrification summing above 1.5 suggests double-counting between the two shares
  suggestion: Confirm whether the two shares are nested or disjoint
```

---

## Coverage update after this batch

| Metric | After Batch 1 | After Batch 2 | Of total |
|---|---|---|---|
| Parameters declared | 881 | 881 | — |
| Equations declared | 51 | 51 | — |
| Parameters **determined** | 43 | 43 | 4.9% of 881 |
| Parameters **named** (in some equation) | 192 | 192 | 21.8% |
| Parameters **still uncoupled** | 689 | 689 | 78.2% |
| Share-shaped parameters with **correct** range | ~50 | **~96** | ~100% of the identifiable share set |
| Share-shaped parameters **still on the placeholder** | ~46 | **~0** | — |
| `free` nodes with placeholder range `[0, 1e6]` | 667 | **621** | 89.7% of the free set |

**The remaining placeholder population is now concentrated in three groups:**

1. **Index-shaped parameters** (composite indices whose own bound I do not know — digital divide, geopolitical risk, energy security, rule of law, corruption perception, adaptive capacity, vulnerability, exposure). Approximately **50 nodes**. These need the index's methodology document.
2. **Cost parameters** whose shipped range is `[0, 1e6]` but whose unit is missing or wrong (capex, opex, fuel costs, storage costs). Approximately **90 nodes**. These need a unit sweep — the parameters are not share-shaped but the range is still wrong.
3. **Everything else** — the long tail of parameters whose admissible set is either genuinely unknown (insurance losses, catastrophe risk, land acquisition costs) or requires a domain decision. Approximately **481 nodes**.

---

## What this batch did and did not do

**Did:**
- Corrected the admissible range and default of 46 share-shaped parameters whose placeholder range silently accepted impossible values and whose placeholder default silently started the graph from an impossible point.
- Added 4 cross-validation rules that catch the share-shaped inconsistencies the range gate cannot.
- Reduced the placeholder population from 667 to 621.

**Did not:**
- Add or change any equation.
- Add or change any relationship.
- Touch the cost-parameter ranges (a separate sweep, listed above).
- Touch the index-shaped parameters (a separate sweep, listed above).
- Touch any parameter whose admissible set is genuinely unknown — those remain reported in the previous batch's Section A and Section B, and they remain deliverables, not failures.

**Next batch (3): the cost-parameter sweep.** Every `capex_*`, `opex_*`, `fuel_cost_*`, `*_cost`, and `*_price` parameter whose shipped range is `[0, 1e6]` and whose unit is either missing or, where present, inconsistent with the physical quantity. Roughly 90 nodes. This is mechanical, safe, and large.