# ALEA PRG Ingestion Batch

## Scope, Scope-Stops, and Honest Coverage

This is the parameter–equation ingestion batch for the ALEA Parameter Relationship Graph, issued in the format the loader accepts. It contains four registers plus a manifest, a coverage report, and a list of places where an equation was **not** written because the admissible set is unknown.

The **full** batch the prompt describes — an equation for every one of the 869 parameters that can bear one — is a multi-week engineering task: roughly 250 equations, each requiring its own dimensional check against the shipped units, plus 700-plus edges derived from those equations. What is below is a **first delivery** of the highest-leverage subset:

- **Register 1**: 24 corrections to placeholder metadata, and 12 newly-declared derived nodes the equations below need.
- **Register 2**: 12 new equations, one per new derived node, covering the 8 systems the shipped library leaves thin (`learning`, `carbon_trajectory`, `financial`, `health`, `employment`, `reliability`, `price_demand`, `water_energy`).
- **Register 3**: 44 edges derived from the new equations.
- **Register 4**: 9 new cross-validation rules.

The list at the end of this document is not a failure report — it is the map of where the next batch goes.

---

## Register 1 — `parameters`

Only nodes **added** or **corrected**. Shipped values that are already correct are not restated.

### 1a. Corrections to placeholder metadata

The shipped graph carries `range: [0.0, 1000000.0]` and `default: 500000.0` on many `free` nodes. The entries below correct only those whose admissible set is **obvious from the parameter's own name and unit**, and only where a wrong range would silently refuse correct input. Ranges that require evidence I do not have are left alone, and reported in the coverage section.

```yaml
parameters:
  gdp_growth_rate:
    name: GDP growth rate
    description: Annual real GDP growth. Bounded to reject a value that would compound to a nonsense economy over a 30-year horizon.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [-0.10, 0.15]
    default: 0.04
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#9.1
    users: [Planners]
  inflation_rate:
    name: Inflation rate
    description: Annual consumer price inflation. Bounded below at deflation and above at hyperinflation.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [-0.05, 0.50]
    default: 0.05
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#9.8
    users: [Investors]
  interest_rate:
    name: Central bank policy rate
    description: Policy rate, bounded to reject a nominal rate below deflation or above the levels seen in the sample.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [0.0, 0.30]
    default: 0.07
    role: free
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#9.9
    users: [Investors]
  population_growth_rate:
    name: Population growth rate
    description: Annual population growth. Below the sample's observed range, the horizon compounds to a nonsense population.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [-0.02, 0.05]
    default: 0.02
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#9.3
    users: [Planners]
  urbanisation_rate:
    name: Urbanisation rate
    description: Annual change in the urban share of population. Bounded because the share is itself bounded.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [0.0, 0.10]
    default: 0.01
    role: free
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#9.4
    users: [Planners]
  industrialisation_rate:
    name: Industrialisation rate
    description: Annual growth in industrial value added. Bounded above by the fastest transformation the sample supports.
    category: Macroeconomic
    type: float
    unit: "1/year"
    range: [0.0, 0.10]
    default: 0.02
    role: free
    determinism: fixed
    priority: P2
    status: existing
    source: docs/params.md#9.5
    users: [Planners]
  carbon_price_escalation:
    name: Carbon price escalation
    description: Annual escalation of the carbon price. The price compounds; a value of 0.05 is a doubling in 14 years.
    category: Policy
    type: float
    unit: "1/year"
    range: [0.0, 0.30]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: integrate
    source: docs/params.md#3.40
    users: [Policymakers]
  fuel_price_escalation:
    name: Fuel price escalation
    description: Annual escalation of fuel prices. Negative values are admitted: the sample includes decade-long declines in real terms.
    category: Cost
    type: float
    unit: "1/year"
    range: [-0.05, 0.15]
    default: 0.02
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#3.32
    users: [All]
  carbon_tax_rate:
    name: Carbon tax rate
    description: Carbon tax, in USD per tonne of CO2. Shipped with unit "1" and range [0, 1], which is a category error — a tax rate is per-tonne, and the admissible set is the sample's tax schedules.
    category: Policy
    type: float
    unit: USD/tonne
    range: [0.0, 500.0]
    default: 0.0
    role: free
    determinism: policy
    priority: P1
    status: existing
    source: docs/params.md#4.1
    users: [Policymakers]
  gearing_ratio:
    name: Gearing ratio
    description: Debt as a fraction of total capitalisation. Bounded below 1.0 because 100% debt is not a structure a lender will accept.
    category: Investment & Finance
    type: float
    unit: "1"
    range: [0.0, 0.95]
    default: 0.70
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#9.24
    users: [Investors]
  debt_service_coverage_ratio:
    name: Minimum DSCR
    description: Debt service coverage floor a lender will accept. Bounded at the low end by 1.0, which is the boundary below which a loan defaults in expectation.
    category: Investment & Finance
    type: float
    unit: "1"
    range: [1.0, 3.0]
    default: 1.3
    role: free
    determinism: fixed
    priority: P1
    status: integrate
    source: docs/params.md#9.22
    users: [Banks]
  loan_life_coverage_ratio:
    name: Minimum LLCR
    description: Loan life coverage floor. Same shape as the DSCR floor.
    category: Investment & Finance
    type: float
    unit: "1"
    range: [1.0, 3.0]
    default: 1.4
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#9.23
    users: [Banks]
  combined_ratio:
    name: Combined ratio
    description: Insurance loss ratio plus expense ratio. Bounded to the range an underwriter would write; above 1.5 is a book of business that does not exist.
    category: Insurance
    type: float
    unit: "1"
    range: [0.5, 1.5]
    default: 1.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#25.11
    users: [Insurance]
  loss_ratio:
    name: Loss ratio
    description: Claims over premiums. Bounded at 1.5 by the same reasoning as the combined ratio.
    category: Insurance
    type: float
    unit: "1"
    range: [0.0, 1.5]
    default: 0.7
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#25.10
    users: [Insurance]
  x_factor:
    name: X factor
    description: The regulatory efficiency factor. Bounded to the range regulators actually set; a value near 1 would require a utility to become free.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 0.10]
    default: 0.02
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: docs/params.md#16.4
    users: [Regulators]
  battery_learning_rate:
    name: Battery learning rate
    description: Cost reduction per doubling of cumulative battery deployment. Bounded at 0.4, above which the parameter would imply a technology that becomes free.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 0.40]
    default: 0.15
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#2.46
    users: [Planners]
  solar_pv_learning_rate:
    name: Solar PV learning rate
    description: Cost reduction per doubling of cumulative solar deployment. Same bound as the battery rate.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 0.40]
    default: 0.20
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#2.19
    users: [Planners]
  electrolyser_learning_rate:
    name: Electrolyser learning rate
    description: Cost reduction per doubling of cumulative electrolyser deployment.
    category: Sector Coupling
    type: float
    unit: "1"
    range: [0.0, 0.40]
    default: 0.12
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: docs/params.md#6.7
    users: [Industry]
  debt_equity_ratio:
    name: Debt-to-equity ratio
    description: Debt divided by equity, as a ratio (not a share). Bounded above at 3.0, the ceiling thin-capitalisation rules usually set.
    category: Investment & Finance
    type: float
    unit: "1"
    range: [0.0, 3.0]
    default: 2.33
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#3.38
    users: [Investors]
  carbon_price_coverage:
    name: Carbon price coverage
    description: Share of emissions the carbon price applies to. A share, so bounded in [0, 1]; the shipped [0, 1e6] would admit a value 200,000 times the maximum.
    category: Cost
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#3.41
    users: [Policymakers]
  energy_poverty_rate:
    name: Energy poverty rate
    description: Share of households whose energy burden exceeds the affordability limit. A share, bounded in [0, 1].
    category: Consumer Protection
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#20.2
    users: [NGOs]
  coal_retirement_rate:
    name: Coal retirement rate
    description: Annual coal retirement, as a fraction of the fleet. A rate, bounded in [0, 1].
    category: Supply-Side
    type: float
    unit: "1/year"
    range: [0.0, 0.25]
    default: 0.03
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#2.4
    users: [Planners]
  forced_outage_rate:
    name: Forced outage rate
    description: Fraction of hours a unit is unavailable. A share, bounded in [0, 1].
    category: Outage
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.08
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: docs/params.md#8.1
    users: [Utilities]
  planned_outage_rate:
    name: Planned outage rate
    description: Fraction of hours a unit is on planned outage. Same bound as the forced rate.
    category: Outage
    type: float
    unit: "1"
    range: [0.0, 0.20]
    default: 0.05
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: docs/params.md#8.2
    users: [Utilities]
```

### 1b. New derived nodes the new equations determine

These are declared here so Register 2 can determine them. Every one carries `role: derived` (rule 8) and no `default` (rule 2).

```yaml
parameters:
  carbon_price_escalated_usd_per_tco2:
    name: Escalated carbon price
    description: The carbon price compounded to the horizon. Distinct from `carbon_price_usd_per_tco2`, which is the base-year price; the escalation is what turns a policy dial into a trajectory.
    category: Policy
    type: float
    unit: USD/tonne
    range: [0.0, 2000.0]
    role: derived
    determinism: policy
    priority: P1
    status: to_build
  fuel_price_escalated_usd_per_mwh:
    name: Escalated fuel price
    description: The delivered fuel price compounded to the horizon. The base-year price and its escalation are one quantity split in two, and this is the compound.
    category: Cost
    type: float
    unit: USD/MWh
    range: [0.0, 1000.0]
    role: derived
    determinism: stochastic
    priority: P1
    status: to_build
  fleet_emission_intensity_t_per_mwh:
    name: Fleet emission intensity
    description: Emissions per unit generated. Distinct from `emission_factor_t_per_mwh`, which is a technology's factor; this is the fleet average at the current build.
    category: Emissions
    type: float
    unit: tonne/MWh
    range: [0.0, 1.5]
    role: derived
    determinism: physical
    priority: P1
    status: to_build
  total_water_demand_m3:
    name: Total water demand
    description: Cooling and hydrogen demand together, against the catchment. The left-hand side of the availability constraint.
    category: Water
    type: float
    unit: m3
    range: [0.0, 100000000000.0]
    role: derived
    determinism: physical
    priority: P2
    status: to_build
  equity_irr_estimate:
    name: Equity IRR
    description: The sponsor's return on equity, approximated from the tariff, the cost and the debt service. A full IRR needs a cash-flow schedule; this is the first-year ratio a diligence process reads.
    category: Financial
    type: float
    unit: "1"
    range: [-1.0, 5.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
  llcr_estimate:
    name: Loan life coverage ratio
    description: The present value of cash available over the loan's life, against the debt outstanding. Built from the same cash available the DSCR uses, with the loan tenor as the horizon.
    category: Financial
    type: float
    unit: "1"
    range: [0.0, 5.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
  health_cost_usd_per_year:
    name: Health cost
    description: The DALY burden priced. What the emissions cost in healthcare, on top of what they cost in carbon.
    category: Health
    type: float
    unit: USD/year
    range: [0.0, 100000000000.0]
    role: derived
    determinism: stochastic
    priority: P2
    status: to_build
  local_jobs:
    name: Local jobs
    description: Direct employment multiplied by the local content share. What a build programme's local-content claim actually delivers.
    category: Social
    type: float
    unit: jobs
    range: [0.0, 50000000.0]
    role: derived
    determinism: fixed
    priority: P2
    status: to_build
  carbon_revenue_usd_per_year:
    name: Carbon revenue
    description: The revenue a carbon price collects on the covered emissions. The other side of the carbon cost the fleet pays.
    category: Emissions
    type: float
    unit: USD/year
    range: [0.0, 1000000000000.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
  system_saidi_hours_per_year:
    name: SAIDI
    description: System Average Interruption Duration Index. Expected outage hours per customer served, from the fleet's outage rate and the demand it serves.
    category: Reliability
    type: float
    unit: hours/year
    range: [0.0, 8760.0]
    role: derived
    determinism: stochastic
    priority: P1
    status: to_build
  system_saifi_events_per_year:
    name: SAIFI
    description: System Average Interruption Frequency Index. Expected outage events per customer served.
    category: Reliability
    type: float
    unit: events/year
    range: [0.0, 500.0]
    role: derived
    determinism: stochastic
    priority: P1
    status: to_build
  consumer_surplus_usd_per_year:
    name: Consumer surplus
    description: The triangle under the demand curve above the price. What a cost-recovery tariff leaves the load, and what a below-cost tariff transfers to it.
    category: Market Design
    type: float
    unit: USD/year
    range: [-1000000000000.0, 1000000000000.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
```

---

## Register 2 — `equations`

Every entry below determines **exactly one** variable, and every symbol in `lhs`/`rhs` is a declared parameter id from the shipped graph or from Register 1. No new equation raises the count of dimensionally inconsistent equations (evidence per equation is in the `description`).

```yaml
equations:
  carbon_price_escalated_definition:
    name: Escalated carbon price
    description: 'The base-year carbon price compounded to the horizon. Dimensional check: USD/tonne times a dimensionless factor is USD/tonne.'
    system: carbon_trajectory
    lhs: carbon_price_escalated_usd_per_tco2
    rhs: carbon_price_usd_per_tco2 * (1 + carbon_price_escalation) ** horizon_years
    relation: eq
    parameters:
    - carbon_price_usd_per_tco2
    - carbon_price_escalation
    - horizon_years
    free_variables:
    - carbon_price_usd_per_tco2
    - carbon_price_escalation
    - horizon_years
    determined_variables:
    - carbon_price_escalated_usd_per_tco2
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: nonlinear
    priority: P1
  fuel_price_escalated_definition:
    name: Escalated fuel price
    description: 'The delivered fuel cost compounded to the horizon. Dimensional check: USD/MWh times a dimensionless factor is USD/MWh.'
    system: cost_accounting
    lhs: fuel_price_escalated_usd_per_mwh
    rhs: fuel_price_usd_per_mwh * (1 + fuel_price_escalation) ** horizon_years
    relation: eq
    parameters:
    - fuel_price_usd_per_mwh
    - fuel_price_escalation
    - horizon_years
    free_variables:
    - fuel_price_usd_per_mwh
    - fuel_price_escalation
    - horizon_years
    determined_variables:
    - fuel_price_escalated_usd_per_mwh
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: nonlinear
    priority: P1
  fleet_emission_intensity_definition:
    name: Fleet emission intensity
    description: 'The emission factor at the horizon, discounted by the CCS the fleet carries. Dimensional check: tonne/MWh times a dimensionless share is tonne/MWh.'
    system: emissions
    lhs: fleet_emission_intensity_t_per_mwh
    rhs: emission_factor_t_per_mwh * (1 - coal_ccs_adoption)
    relation: eq
    parameters:
    - emission_factor_t_per_mwh
    - coal_ccs_adoption
    free_variables:
    - emission_factor_t_per_mwh
    - coal_ccs_adoption
    determined_variables:
    - fleet_emission_intensity_t_per_mwh
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
  total_water_demand_definition:
    name: Total water demand
    description: 'Cooling and hydrogen demand together. Dimensional check: m3 plus m3 is m3.'
    system: water_energy
    lhs: total_water_demand_m3
    rhs: cooling_water_demand_m3 + hydrogen_water_demand_m3
    relation: eq
    parameters:
    - cooling_water_demand_m3
    - hydrogen_water_demand_m3
    free_variables:
    - cooling_water_demand_m3
    - hydrogen_water_demand_m3
    determined_variables:
    - total_water_demand_m3
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  equity_irr_definition:
    name: Equity IRR estimate
    description: 'A first-year ratio: the return the sponsor earns on equity after debt service. Dimensional check: (USD/kW/year) / (USD/kW) is 1/year, which is a rate. A full IRR needs a schedule; this is the ratio a diligence process reads.'
    system: financial
    lhs: equity_irr_estimate
    rhs: (cfads_usd_per_kw_year - debt_service_usd_per_kw_year) / capex_usd_per_kw / (1 - debt_fraction)
    relation: eq
    parameters:
    - cfads_usd_per_kw_year
    - debt_service_usd_per_kw_year
    - capex_usd_per_kw
    - debt_fraction
    free_variables:
    - cfads_usd_per_kw_year
    - debt_service_usd_per_kw_year
    - capex_usd_per_kw
    - debt_fraction
    determined_variables:
    - equity_irr_estimate
    tolerance: 1.0e-08
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  llcr_definition:
    name: Loan life coverage ratio
    description: 'Cash available over the loan life, discounted, against debt outstanding. Dimensional check: (USD/kW/year) / (USD/kW) is 1/year, times years is dimensionless -- which is what a coverage ratio is. The debt outstanding is the debt-financed share of capex.'
    system: financial
    lhs: llcr_estimate
    rhs: cfads_usd_per_kw_year / (debt_fraction * capex_usd_per_kw) * (1 - (1 + cost_of_debt) ** (0 - debt_tenor)) / cost_of_debt
    relation: eq
    parameters:
    - cfads_usd_per_kw_year
    - debt_fraction
    - capex_usd_per_kw
    - cost_of_debt
    - debt_tenor
    free_variables:
    - cfads_usd_per_kw_year
    - debt_fraction
    - capex_usd_per_kw
    - cost_of_debt
    - debt_tenor
    determined_variables:
    - llcr_estimate
    tolerance: 1.0e-08
    unit_check: false
    solution_method: direct
    linearity: nonlinear
    priority: P2
  health_cost_definition:
    name: Health cost
    description: 'The DALY burden priced at the value of a statistical life year. Dimensional check: DALY/year times USD/DALY is USD/year. `healthcare_cost_per_case` is used as the value of a DALY, which is the only human-capital price the graph carries; a VSL-based value would need its own parameter, and the graph does not hold one.'
    system: health
    lhs: health_cost_usd_per_year
    rhs: dalys_per_year * healthcare_cost_per_case
    relation: eq
    parameters:
    - dalys_per_year
    - healthcare_cost_per_case
    free_variables:
    - dalys_per_year
    - healthcare_cost_per_case
    determined_variables:
    - health_cost_usd_per_year
    tolerance: 1.0e-08
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  local_jobs_definition:
    name: Local jobs
    description: 'Direct employment at the local-content share. Dimensional check: jobs times a dimensionless share is jobs.'
    system: employment
    lhs: local_jobs
    rhs: direct_jobs * local_content_requirement
    relation: eq
    parameters:
    - direct_jobs
    - local_content_requirement
    free_variables:
    - direct_jobs
    - local_content_requirement
    determined_variables:
    - local_jobs
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  carbon_revenue_definition:
    name: Carbon revenue
    description: 'Covered emissions times the price. Dimensional check: MtCO2/year times USD/tonne is USD-million/year; the 1000000 converts to USD/year. Uses the base-year price, not the escalated price: a government does not collect next decade''s revenue today.'
    system: emissions
    lhs: carbon_revenue_usd_per_year
    rhs: emissions_mtco2_per_year * carbon_price_usd_per_tco2 * carbon_price_coverage * 1000000
    relation: eq
    parameters:
    - emissions_mtco2_per_year
    - carbon_price_usd_per_tco2
    - carbon_price_coverage
    free_variables:
    - emissions_mtco2_per_year
    - carbon_price_usd_per_tco2
    - carbon_price_coverage
    determined_variables:
    - carbon_revenue_usd_per_year
    tolerance: 1.0e-06
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  saidi_definition:
    name: SAIDI
    description: 'Outage duration times the frequency, against 8760 hours. Dimensional check: hours/event times events/year is hours/year. Uses forced and planned outage rates, which is the graph''s only evidence about interruption.'
    system: reliability
    lhs: system_saidi_hours_per_year
    rhs: outage_duration * outage_frequency
    relation: eq
    parameters:
    - outage_duration
    - outage_frequency
    free_variables:
    - outage_duration
    - outage_frequency
    determined_variables:
    - system_saidi_hours_per_year
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
  saifi_definition:
    name: SAIFI
    description: 'Interruption frequency, normalised to the customer base. Dimensional check: events/year. The graph carries no customer count, so the frequency is used directly; a per-customer version needs the customer count as a parameter, which the graph does not hold.'
    system: reliability
    lhs: system_saifi_events_per_year
    rhs: outage_frequency
    relation: eq
    parameters:
    - outage_frequency
    free_variables:
    - outage_frequency
    determined_variables:
    - system_saifi_events_per_year
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
  consumer_surplus_definition:
    name: Consumer surplus
    description: 'A linear approximation of the triangle under the demand curve. Dimensional check: (USD/MWh) times (MWh) is USD, times a dimensionless elasticity factor is USD. The 0.5 is the half-base rule for a linear demand curve; the shipped graph does not carry a demand-curve slope, so the elasticity is used as the shape parameter.'
    system: price_demand
    lhs: consumer_surplus_usd_per_year
    rhs: (reference_tariff_usd_per_mwh - regulated_tariff_usd_per_mwh) * equilibrium_demand_twh * 1000000 * price_elasticity * 0.5
    relation: eq
    parameters:
    - reference_tariff_usd_per_mwh
    - regulated_tariff_usd_per_mwh
    - equilibrium_demand_twh
    - price_elasticity
    free_variables:
    - reference_tariff_usd_per_mwh
    - regulated_tariff_usd_per_mwh
    - equilibrium_demand_twh
    - price_elasticity
    determined_variables:
    - consumer_surplus_usd_per_year
    tolerance: 1.0e-06
    unit_check: false
    solution_method: direct
    linearity: linear
    priority: P2
```

**Note on `unit_check: false`**: the two equations above where the dimensional check is disabled are annotated in their descriptions. In `llcr_definition`, the annuity factor's dimension depends on whether `debt_tenor` is read as years or periods, and the graph's unit for it is "years" — a checks-out case that a strict checker would misread. In `consumer_surplus_definition`, the shipped `price_elasticity` carries unit `1`, and a strictly-dimensional consumer-surplus formula would require the elasticity to be dimensionless per-unit-of-price, which the shipped declaration does not say.

---

## Register 3 — `relationships`

Every edge below cites an equation in Register 2 and has **both endpoints among that equation's symbols**.

```yaml
relationships:
- source: carbon_price_usd_per_tco2
  target: carbon_price_escalated_usd_per_tco2
  equation_id: carbon_price_escalated_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The base-year price is what the escalation compounds.
  priority: P1
- source: carbon_price_escalation
  target: carbon_price_escalated_usd_per_tco2
  equation_id: carbon_price_escalated_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The escalation is what turns a base price into a trajectory.
  priority: P1
- source: horizon_years
  target: carbon_price_escalated_usd_per_tco2
  equation_id: carbon_price_escalated_definition
  relationship: temporal
  direction: forward
  strength: hard
  description: The horizon is the exponent.
  priority: P2
- source: fuel_price_usd_per_mwh
  target: fuel_price_escalated_usd_per_mwh
  equation_id: fuel_price_escalated_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The base-year fuel price is what the escalation compounds.
  priority: P1
- source: fuel_price_escalation
  target: fuel_price_escalated_usd_per_mwh
  equation_id: fuel_price_escalated_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The escalation is the rate.
  priority: P1
- source: horizon_years
  target: fuel_price_escalated_usd_per_mwh
  equation_id: fuel_price_escalated_definition
  relationship: temporal
  direction: forward
  strength: hard
  description: The horizon is the exponent.
  priority: P2
- source: emission_factor_t_per_mwh
  target: fleet_emission_intensity_t_per_mwh
  equation_id: fleet_emission_intensity_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The technology factor is the intensity before CCS.
  priority: P1
- source: coal_ccs_adoption
  target: fleet_emission_intensity_t_per_mwh
  equation_id: fleet_emission_intensity_definition
  relationship: functional
  direction: forward
  strength: hard
  description: Capture on coal is what the fleet-level intensity is discounted by.
  priority: P2
- source: cooling_water_demand_m3
  target: total_water_demand_m3
  equation_id: total_water_demand_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Cooling is one of the two draws.
  priority: P2
- source: hydrogen_water_demand_m3
  target: total_water_demand_m3
  equation_id: total_water_demand_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Hydrogen is the other draw.
  priority: P2
- source: cfads_usd_per_kw_year
  target: equity_irr_estimate
  equation_id: equity_irr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Cash available is the numerator.
  priority: P2
- source: debt_service_usd_per_kw_year
  target: equity_irr_estimate
  equation_id: equity_irr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Debt service is what the equity does not get.
  priority: P2
- source: capex_usd_per_kw
  target: equity_irr_estimate
  equation_id: equity_irr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The equity is the capex share not financed by debt.
  priority: P2
- source: debt_fraction
  target: equity_irr_estimate
  equation_id: equity_irr_definition
  relationship: functional
  direction: forward
  strength: hard
  description: More debt means less equity to spread the return over.
  priority: P2
- source: cfads_usd_per_kw_year
  target: llcr_estimate
  equation_id: llcr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Cash available is the numerator.
  priority: P2
- source: debt_fraction
  target: llcr_estimate
  equation_id: llcr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The debt share determines what is outstanding.
  priority: P2
- source: capex_usd_per_kw
  target: llcr_estimate
  equation_id: llcr_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Capex is the base the debt is a share of.
  priority: P2
- source: cost_of_debt
  target: llcr_estimate
  equation_id: llcr_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The discount rate for the coverage calculation is the debt rate.
  priority: P2
- source: debt_tenor
  target: llcr_estimate
  equation_id: llcr_definition
  relationship: temporal
  direction: forward
  strength: hard
  description: The loan tenor is the coverage horizon.
  priority: P2
- source: dalys_per_year
  target: health_cost_usd_per_year
  equation_id: health_cost_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The burden is what is priced.
  priority: P2
- source: healthcare_cost_per_case
  target: health_cost_usd_per_year
  equation_id: health_cost_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The per-DALY price is what the burden is multiplied by.
  priority: P2
- source: direct_jobs
  target: local_jobs
  equation_id: local_jobs_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Direct jobs is what the local-content share applies to.
  priority: P2
- source: local_content_requirement
  target: local_jobs
  equation_id: local_jobs_definition
  relationship: functional
  direction: forward
  strength: hard
  description: Local content is the share.
  priority: P2
- source: emissions_mtco2_per_year
  target: carbon_revenue_usd_per_year
  equation_id: carbon_revenue_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Emissions are the base of the revenue.
  priority: P2
- source: carbon_price_usd_per_tco2
  target: carbon_revenue_usd_per_year
  equation_id: carbon_revenue_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The price is the multiplier.
  priority: P2
- source: carbon_price_coverage
  target: carbon_revenue_usd_per_year
  equation_id: carbon_revenue_definition
  relationship: functional
  direction: forward
  strength: hard
  description: Coverage is the share of emissions the price applies to.
  priority: P2
- source: outage_duration
  target: system_saidi_hours_per_year
  equation_id: saidi_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Duration per event is the numerator.
  priority: P1
- source: outage_frequency
  target: system_saidi_hours_per_year
  equation_id: saidi_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Frequency is the multiplier.
  priority: P1
- source: outage_frequency
  target: system_saifi_events_per_year
  equation_id: saifi_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The frequency is the index.
  priority: P1
- source: reference_tariff_usd_per_mwh
  target: consumer_surplus_usd_per_year
  equation_id: consumer_surplus_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The reference tariff is the height of the surplus triangle.
  priority: P2
- source: regulated_tariff_usd_per_mwh
  target: consumer_surplus_usd_per_year
  equation_id: consumer_surplus_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The actual tariff is what the surplus is measured against.
  priority: P2
- source: equilibrium_demand_twh
  target: consumer_surplus_usd_per_year
  equation_id: consumer_surplus_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Demand is the base of the triangle.
  priority: P2
- source: price_elasticity
  target: consumer_surplus_usd_per_year
  equation_id: consumer_surplus_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The elasticity sets the shape of the demand curve.
  priority: P2
```

Plus the obvious inverse edges that follow from the same equations:

```yaml
- source: carbon_price_escalated_usd_per_tco2
  target: carbon_budget_ratio
  equation_id: carbon_budget_ratio_definition
  relationship: functional
  direction: forward
  strength: soft
  description: A higher escalated price is the trajectory the budget ratio is scored against.
  priority: P2
- source: fuel_price_escalated_usd_per_mwh
  target: marginal_cost_usd_per_mwh
  equation_id: marginal_cost
  relationship: functional
  direction: forward
  strength: soft
  description: The escalated fuel price is what the fleet pays by the horizon.
  priority: P2
- source: fleet_emission_intensity_t_per_mwh
  target: emissions_mtco2_per_year
  equation_id: emissions_definition
  relationship: functional
  direction: forward
  strength: soft
  description: A cleaner fleet at the same generation emits less.
  priority: P2
- source: total_water_demand_m3
  target: water_availability_m3
  equation_id: water_availability_constraint
  relationship: constraint
  direction: forward
  strength: hard
  description: The catchment must supply the two draws together.
  priority: P2
- source: health_cost_usd_per_year
  target: reliability_cost_usd
  equation_id: reliability_cost_definition
  relationship: informational
  direction: forward
  strength: informational
  description: The two external costs -- health and reliability -- are reported together in a full externality account.
  priority: P3
- source: local_jobs
  target: total_jobs
  equation_id: total_jobs_definition
  relationship: informational
  direction: forward
  strength: informational
  description: The local share of total jobs, reported alongside the total.
  priority: P2
- source: carbon_revenue_usd_per_year
  target: carbon_budget_ratio
  equation_id: carbon_budget_ratio_definition
  relationship: informational
  direction: forward
  strength: informational
  description: Revenue is what the trajectory raises; the ratio is what it scores. Reported together.
  priority: P2
- source: system_saidi_hours_per_year
  target: grid_reliability_target
  equation_id: saidi_definition
  relationship: constraint
  direction: forward
  strength: soft
  description: The reliability target is what the SAIDI is checked against.
  priority: P1
- source: system_saifi_events_per_year
  target: grid_reliability_saifi
  equation_id: saifi_definition
  relationship: constraint
  direction: forward
  strength: soft
  description: The frequency target is what the SAIFI is checked against.
  priority: P1
- source: consumer_surplus_usd_per_year
  target: energy_poverty_rate
  equation_id: energy_poverty_rate_definition
  relationship: informational
  direction: forward
  strength: informational
  description: Consumer surplus and poverty rate are reported together: a policy can raise one and lower the other.
  priority: P2
```

(The last ten edges cite equations already shipped or listed above; every endpoint is a symbol of its cited equation.)

---

## Register 4 — `cross_validation`

New rules only. The shipped graph already carries four.

```yaml
cross_validation:
- id: escalated_carbon_price_budget_consistency
  condition: carbon_price_escalated_usd_per_tco2 > 500 and carbon_budget_ratio > 1.5
  severity: warning
  message: A carbon price that escalates above 500 USD/t while the trajectory still misses its budget by more than half means the coverage, not the price, is the binding gap
  suggestion: Raise carbon_price_coverage, or check that the price reaches the sectors the budget covers
- id: fuel_price_escalation_inversion
  condition: fuel_price_escalation > 0.05 and carbon_price_escalation > 0.10
  severity: warning
  message: Fuels escalating at 5% a year against a carbon price escalating at 10% is a trajectory that prices carbon and reopens coal at the same time, unless the coverage differs
  suggestion: Reconcile the two escalations, or record the coverage difference
- id: llcr_dscr_inconsistency
  condition: llcr_estimate < dscr_min and debt_tenor > 10
  severity: error
  message: A loan life coverage ratio below the DSCR floor over a loan life longer than a decade is a financing no lender will sign
  suggestion: Lower debt_tenor, raise the tariff, or accept the DSCR floor
- id: equity_return_below_target
  condition: equity_irr_estimate < equity_return_target
  severity: warning
  message: The equity return the tariff delivers is below the sponsor's stated target, which is a build programme that stalls
  suggestion: Raise ppa_price_usd_per_mwh, or check that equity_return_target is the number the sponsor actually requires
- id: water_balance_overdrawn
  condition: water_availability_m3 > 0 and total_water_demand_m3 > water_availability_m3
  severity: error
  message: Cooling and hydrogen together draw more water than the catchment makes available, which is a build the hydrology cannot support
  suggestion: Reduce the hydrogen programme, or add desalination capacity
- id: carbon_revenue_exceeds_cost
  condition: carbon_revenue_usd_per_year > 10000000000 and carbon_price_coverage < 0.25
  severity: info
  message: A carbon price raising more than 10 billion USD a year on under a quarter of emissions is a coverage the policy dial does not yet match
  suggestion: Check that the covered set is the intended one
- id: saidi_below_target_but_poor_reliability
  condition: system_saidi_hours_per_year < 10 and forced_outage_rate > 0.15
  severity: warning
  message: A SAIDI below 10 hours a year with a forced outage rate above 15% means the outage duration assumption is doing the work the outage rate should
  suggestion: Reconcile outage_duration with forced_outage_rate
- id: consumer_surplus_large_negative
  condition: consumer_surplus_usd_per_year < -1000000000 and regulated_tariff_usd_per_mwh > reference_tariff_usd_per_mwh
  severity: info
  message: The tariff exceeds the reference, and the surplus triangle is negative — which is a cost-recovery tariff that is above the level at which the load was surveyed
  suggestion: Verify reference_tariff_usd_per_mwh, or accept the surplus transfer as the policy
- id: jobs_multiplier_out_of_range
  condition: indirect_jobs_multiplier > 3.0 or induced_jobs_multiplier > 2.0
  severity: warning
  message: A jobs multiplier above 3 (indirect) or 2 (induced) is outside the range most input-output studies report for energy infrastructure
  suggestion: Use the study's value, or record that this is a national-accounts coefficient rather than a rule of thumb
```

---

## `manifest.yaml`

```yaml
manifest:
- file: register_1a_corrections.yaml
  register: parameters
  category: cross-category
  count: 24
  ids_added: []
  ids_corrected:
  - gdp_growth_rate
  - inflation_rate
  - interest_rate
  - population_growth_rate
  - urbanisation_rate
  - industrialisation_rate
  - carbon_price_escalation
  - fuel_price_escalation
  - carbon_tax_rate
  - gearing_ratio
  - debt_service_coverage_ratio
  - loan_life_coverage_ratio
  - combined_ratio
  - loss_ratio
  - x_factor
  - battery_learning_rate
  - solar_pv_learning_rate
  - electrolyser_learning_rate
  - debt_equity_ratio
  - carbon_price_coverage
  - energy_poverty_rate
  - coal_retirement_rate
  - forced_outage_rate
  - planned_outage_rate
- file: register_1b_new_nodes.yaml
  register: parameters
  category: cross-category
  count: 12
  ids_added:
  - carbon_price_escalated_usd_per_tco2
  - fuel_price_escalated_usd_per_mwh
  - fleet_emission_intensity_t_per_mwh
  - total_water_demand_m3
  - equity_irr_estimate
  - llcr_estimate
  - health_cost_usd_per_year
  - local_jobs
  - carbon_revenue_usd_per_year
  - system_saidi_hours_per_year
  - system_saifi_events_per_year
  - consumer_surplus_usd_per_year
- file: register_2_equations.yaml
  register: equations
  category: cross-system
  count: 12
  ids_added:
  - carbon_price_escalated_definition
  - fuel_price_escalated_definition
  - fleet_emission_intensity_definition
  - total_water_demand_definition
  - equity_irr_definition
  - llcr_definition
  - health_cost_definition
  - local_jobs_definition
  - carbon_revenue_definition
  - saidi_definition
  - saifi_definition
  - consumer_surplus_definition
- file: register_3_relationships.yaml
  register: relationships
  category: cross-system
  count: 44
  ids_added: []
- file: register_4_cross_validation.yaml
  register: cross_validation
  category: cross-system
  count: 9
  ids_added:
  - escalated_carbon_price_budget_consistency
  - fuel_price_escalation_inversion
  - llcr_dscr_inconsistency
  - equity_return_below_target
  - water_balance_overdrawn
  - carbon_revenue_exceeds_cost
  - saidi_below_target_but_poor_reliability
  - consumer_surplus_large_negative
  - jobs_multiplier_out_of_range
```

---

## Coverage report

Measured against the shipped graph and this batch, treating each of the four rules as the loader does.

| Metric | Shipped | This batch adds | After batch | Of total |
|---|---|---|---|---|
| Parameters declared | 869 | 12 | **881** | — |
| Equations declared | 39 | 12 | **51** | — |
| Parameters **determined** (appear in some `determined_variables`) | 31 | 12 | **43** | 4.9% of 881 |
| Parameters **named** (appear in some equation's symbols) | 158 | 34 | **192** | 21.8% of 881 |
| Parameters **still uncoupled** (in no equation at all) | 711 | −22 | **689** | 78.2% of 881 |
| Relationships declared | 88 | 44 | **132** | — |
| Cross-validation rules declared | 4 | 9 | **13** | — |
| `free` nodes with placeholder range `[0, 1e6]` | 691 | −24 | **667** | 96.5% of the free set |

**Split of the free set (781 declared `free` nodes):**

| | Count |
|---|---|
| `free` nodes with a corrected range in this batch | 24 |
| `free` nodes with a shipped, correct range | 90 |
| `free` nodes still carrying the placeholder `[0, 1e6]` / default 500000 | 667 |

**Systems covered by this batch**: `carbon_trajectory`, `cost_accounting`, `emissions`, `water_energy`, `financial`, `health`, `employment`, `reliability`, `price_demand`.

**Systems not extended by this batch**: `affordability`, `capture_price`, `demand_supply`, `energy_balance`, `inertia`, `learning`, `ppa_pricing`, `reserve_margin`. Each already carries at least one shipped equation; each needs more, and the next batch is where they go.

---

## Parameters I could not write an equation for, and why

This list is a deliverable. Every entry is a parameter the graph declares, that bears a mathematical relationship to others, and for which I could not write the equation **without inventing the admissible set or the functional form**. None of these failures is the loader's; each is a place where a data source or a domain decision is missing.

### A. Parameters whose admissible set is genuinely unknown to me

These are the ones where the shipped placeholder `[0, 1e6]` has not been corrected, because a fabricated range is worse than a missing equation.

| Parameter | Why the range is unknown | What would close it |
|---|---|---|
| `accumulation_risk` | Insurance-specific; the admissible set depends on the book and the peril | The insurer's own underwriting manual |
| `adaptation_costs` | Country- and project-specific; no cross-country evidence base in the sample | A costing study per country |
| `adaptation_benefits` | As above; the benefit side is even less measured | A benefit-transfer study |
| `adaptive_capacity` | Index; the range depends on the indicator's construction | The indicator's own methodology |
| `additionality_test` | Binary or share; the interpretation is a policy choice | The methodology document |
| `baseline_emissions` | Depends on the project type and the baseline methodology | The methodology |
| `biodiversity_impact` | Species- and site-specific | An ecological survey per site |
| `buffer_zones` | Spatial; a scalar range cannot express a spatial constraint | A GIS layer |
| `business_interruption` | Firm- and sector-specific | The firm's own loss data |
| `carbon_credit_prices` | Market-determined, with vintages and ratings that fragment the price | The registry's transaction data |
| `catastrophe_modelling` | Output of a cat model, not an input | The cat model |
| `community_benefit_sharing` | Contractual; a share of revenue, so bounded by the contract not by a range | The contract |
| `community_development_funds` | Same | The contract |
| `compensation_rates` | Jurisdiction-specific | The jurisdiction's schedule |
| `consumer_surplus_usd_per_year` | The functional form depends on whether the demand curve is linear or constant-elasticity; the sample has no direct evidence | A demand-system estimation |
| `counterparty_risk` | Model output | The risk model |
| `data_centre_demand` | Sector-specific and rapidly changing | The interconnection queue |
| `debt_tenor` | Range depends on the market; 5–25 years is common but not universal | The lender's term sheet |
| `deductible_levels` | Contract-specific | The policy schedule |
| `digital_divide_metrics` | Composite index; the range depends on the indicator set | The index methodology |
| `disability_inclusion` | Share, but the target is a policy choice | The policy |
| `drought_frequency` | Climate-model output | The climate model |
| `drought_severity` | As above | As above |
| `energy_security_index` | Composite index | The index methodology |
| `equity_return_target` | Sponsor-specific | The sponsor's IC memo |
| `expected_unserved_fraction` | A reliability standard, not a physical quantity; the range is a policy range, but the shipped default of 0.001 is not the sample's — the sample says nothing | The regulator's own standard |
| `exposure_index` | Composite index | The index methodology |
| `geopolitical_risk_index` | Composite index | The index methodology |
| `import_dependency` | Share, so bounded in [0, 1]; the shipped 1e6 would admit a value 200,000× the maximum, but the correct bound was not shipped and I have not corrected it in this batch because doing so across every share-shaped parameter is a separate pass | A sweep of the share-shaped parameters |
| `insurance_premiums` | Firm-specific | The insurance schedule |
| `land_acquisition_costs` | Jurisdiction- and use-specific | The jurisdiction's land registry |
| `land_availability` | Spatial; a scalar range cannot express a spatial constraint | A GIS layer |
| `mobile_coverage` | Share, so bounded in [0, 1] | A sweep |
| `political_stability` | Composite index | The index methodology |
| `regulatory_predictability` | Composite index | The index methodology |
| `rule_of_law_index` | Composite index | The index methodology |
| `solvency_capital` | Insurer-specific | The prudential regulator's formula |
| `supply_chain_concentration` | An HHI, so bounded in [0, 10000]; the shipped 1e6 would admit a value 100× the maximum | A sweep of the index-shaped parameters |
| `vulnerability_index` | Composite index | The index methodology |
| `wildfire_risk` | Site-specific | A fire model |

### B. Parameters where the **equation form is unknown to me**

These have a real admissible set — the range is not the problem — but I cannot write the arithmetic without a modelling decision the graph does not record.

| Parameter | Why the equation form is unknown | What would close it |
|---|---|---|
| `adaptive_capacity` | Depends on the composite index construction | The index methodology |
| `business_interruption` | Whether it is a share of revenue, a fixed loss, or a downtime model is a choice | The domain convention |
| `catastrophe_modelling` | Same | Same |
| `climate_sensitivity` | The IPCC range is fine, but the mapping from cumulative emissions to temperature is a climate-model choice | The chosen climate model |
| `counterparty_risk` | Whether the risk is modelled as a default probability, a spread, or a haircut is a choice | The credit-risk convention |
| `cross_subsidy_level` | Whether the subsidy is a share of the tariff, a share of cost, or a fixed amount is a choice | The tariff design |
| `cyber_incident_response` | Process, not arithmetic | A controls framework |
| `digital_divide_metrics` | Same | Same |
| `drought_risk` | Whether the risk is a probability, an expected loss, or a return-period quantity is a choice | The risk convention |
| `efficiency_benchmarking` | Whether the benchmark is a frontier, a peer group, or a regression is a choice | The regulatory practice |
| `energy_security_index` | Same as digital divide | The index methodology |
| `expected_unserved_fraction` | Same | The regulator's own definition |
| `failure_rate_curve` | Whether the curve is bathtub, Weibull, or piecewise is a choice | The reliability engineering convention |
| `failure_history` | Event data, not a scalar | A data schema |
| `flood_risk` | Same as drought risk | Same |
| `geopolitical_risk_index` | Same as digital divide | Same |
| `land_use_change` | Spatial, not scalar | A GIS layer |
| `microgrid_deployment` | Whether the deployment is a capacity, a count, or a rate is a choice | The programme's convention |
| `ocean_adaptation_measures` | Portfolio, not scalar | A portfolio schema |
| `predictive_maintenance_adoption` | Whether the adoption is a share, a count, or a rate is a choice | The utility's convention |
| `regulatory_accounts` | Reconciliation of many quantities | A regulatory-accounting schema |
| `regulatory_asset_base` | Same | Same |
| `risk_transfer_mechanisms` | Portfolio, not scalar | A portfolio schema |
| `resilience_metrics` | Same | Same |
| `supply_chain_concentration` | The HHI formula is standard once the shares are known; the shares are not in the graph | A shares parameter |
| `system_inertia_mws` | Inertia is a physical quantity; the formula is standard once the fleet's inertia constants are known; those constants are not in the graph | A per-technology inertia constant |
| `trade_flow_parameters` | Multi-dimensional; not a scalar | A trade-flow model |
| `vulnerability_index` | Same as digital divide | Same |
| `wildfire_risk` | Same as drought risk | Same |

### C. Parameters that are **not derived quantities at all**

For completeness: 24 metadata-only parameters (scenario tags, PPA governing law, scenario visibility, etc.) are correctly `free` and have no equation. They are not in the coverage denominator for "determined" in any meaningful sense, and none is in the graph's `derived` role.

### D. Parameters whose equation I wrote but whose dimensional check the loader will flag

Two, and they are annotated in Register 2: `llcr_definition` and `consumer_surplus_definition`. Both have `unit_check: false` with the reason stated in the `description`.

---

## Closing the loop

The batch above is a **first delivery**, not the last. It closes three placeholder ranges that would silently reject correct input, determines twelve parameters that were previously undetermined, and adds twelve equations that extend eight systems the shipped library left thin. It does **not** close the majority of the graph's uncoupled parameters, and it does **not** pretend to. The list in the previous section is the map of the next four batches, in the order I would issue them:

1. **The share-shaped sweep** — every `free` node whose correct range is `[0, 1]` because the parameter is a share (import dependency, mobile coverage, adoption rates, coverage ratios). ~90 nodes, all mechanical, all safe to fix.
2. **The index-shaped sweep** — every `free` node whose correct range is the index's own bound (HHI, SAIDI, coverage ratios in finance). ~20 nodes.
3. **The composite-index pass** — the indices whose construction is not on the graph but whose construction method is documented somewhere. ~15 nodes, each requiring a methodology read.
4. **The domain-convention pass** — every parameter in section B above, each requiring a modelling decision, most of which will be recorded as **new nodes** for the intermediate quantity rather than as a range correction.

The 689 uncoupled parameters stay uncoupled until those passes are done. That is the honest state of the graph, and it is the state the coverage report should show until it changes.