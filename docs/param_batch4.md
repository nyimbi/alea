# ALEA PRG Ingestion Batch 5 — The Reliability, Regulatory and Type Sweep

## Closing the Asset-Condition, Regulatory-Finance and Contract Groups, and Surfacing a New Class of Error

This batch closes the first three of the four groups Batch 4 left open — **asset condition and reliability**, **regulatory finance**, and **contract** — and, in the process, surfaces a **new class of defect** that none of the previous batches could see: parameters shipped as `type: float` that are not floats at all. An ETS that is on or off is a boolean; a market structure that is one of four options is a categorical; a clustering method that names an algorithm is a categorical. The shipped graph declares each of these as `float` with `range: [0, 1e6]` and `default: 500000.0`, and every consumer that reads them as a number gets a number that no arithmetic can honestly use.

This batch corrects **63 parameters**:

- **14** asset-condition and reliability parameters, with ranges from the reliability-engineering literature;
- **18** regulatory-finance parameters, with ranges from documented regulatory practice;
- **12** contract parameters, with ranges from documented market practice;
- **19** type corrections — the boolean and categorical parameters declared as floats.

It adds **6 new equations** for derived reliability indices and asset-condition measures. It adds **17 new relationships**. It adds **10 cross-validation rules**.

The **insurance group** is deferred to Batch 6. Its parameters are firm-specific (a book's own loss ratio, a reinsurance treaty's own attachment point), and no public document can specify the admissible set of an individual firm's number. That group is not a failure of this batch; it is a different class of parameter, and it needs the firm's own data.

---

## Register 1 — `parameters`

### Part A — Asset condition and reliability (14 nodes)

These are the parameters the graph uses for outage probability, repair duration and preventive maintenance. Their ranges come from the IEEE Std 493 (the "Gold Book"), the CIGRE reliability surveys, and the NERC State of Reliability reports.

```yaml
parameters:
  mean_time_between_failures:
    name: Mean time between failures
    description: Expected operating hours between forced outages for a unit of the class the parameter describes. Range spans distribution equipment at the low end to transmission transformers at the high end. The shipped [0, 1e6] admitted a value that would imply a unit running for 114 years between failures, which for most equipment classes is a claim no asset register supports.
    category: Asset Condition & Lifecycle
    type: float
    unit: hours
    range: [500.0, 500000.0]
    default: 50000.0
    role: free
    determinism: stochastic
    priority: P1
    status: integrate
    source: IEEE Std 493 (Gold Book), CIGRE TB 509
    users: [Utilities]
  mean_time_to_repair:
    name: Mean time to repair
    description: Expected hours from failure to restoration, for the class the parameter describes. The range spans a distribution fuse at the low end to a transmission transformer replacement at the high end.
    category: Asset Condition & Lifecycle
    type: float
    unit: hours
    range: [1.0, 1000.0]
    default: 24.0
    role: free
    determinism: stochastic
    priority: P1
    status: integrate
    source: IEEE Std 493 (Gold Book)
    users: [Utilities]
  failure_rate_curve:
    name: Failure rate curve
    description: A scalar index of the failure-rate curve's shape — 0 for a flat exponential, 1 for a bathtub, 2 for wear-out dominated. Not the curve itself, which is a function and cannot be a scalar; this is the shape selector that a Weibull fit reduces to.
    category: Asset Condition & Lifecycle
    type: float
    unit: "1"
    range: [0.0, 3.0]
    default: 1.0
    role: free
    determinism: physical
    priority: P2
    status: integrate
    source: IEEE Std 493, Weibull shape parameter convention
    users: [Utilities]
  remaining_useful_life:
    name: Remaining useful life
    description: Expected remaining years of service for the class of asset the parameter describes. Bounded above by the longest asset life in the sample and below by zero.
    category: Asset Condition & Lifecycle
    type: float
    unit: years
    range: [0.0, 60.0]
    default: 20.0
    role: free
    determinism: physical
    priority: P1
    status: integrate
    source: Standard asset-management practice; cf. ISO 55000
    users: [Utilities]
  asset_condition_index:
    name: Asset condition index
    description: A composite condition score, normalised to [0, 1] where 1 is as-new and 0 is end-of-life. The shipped [0, 1e6] admitted a value of 500,000, which is the index on a scale no methodology uses.
    category: Asset Condition & Lifecycle
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.7
    role: free
    determinism: physical
    priority: P1
    status: to_build
    source: Composite of condition monitoring, age and loading; normalised per ISO 55000 practice
    users: [Utilities]
  forced_outage_rate_coal:
    name: Coal forced outage rate
    description: Fraction of hours the coal fleet is unavailable due to forced outage. A share; the shipped [0, 1e6] admitted a value 500,000 times the maximum.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 0.40]
    default: 0.10
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: NERC Generating Availability Data System
    users: [Utilities]
  forced_outage_rate_gas:
    name: Gas forced outage rate
    description: Fraction of hours the gas fleet is unavailable due to forced outage. Same shape as coal, lower central value because gas plants are simpler.
    category: Supply-Side
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.06
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: NERC Generating Availability Data System
    users: [Utilities]
  outage_duration:
    name: Average outage duration
    description: Mean hours per interruption event, at the system level. Distinct from the MTTR, which is per asset class; this is the customer's experience aggregated over the mix of causes.
    category: Outage
    type: float
    unit: hours
    range: [0.5, 72.0]
    default: 8.0
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: IEEE Std 1366 (distribution reliability)
    users: [Utilities]
  outage_frequency:
    name: Outage frequency
    description: Average interruptions per year, at the system level. The shipped [0, 1e6] admitted 500,000 interruptions a year.
    category: Outage
    type: float
    unit: events/year
    range: [0.0, 100.0]
    default: 12.0
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: IEEE Std 1366
    users: [Utilities]
  outage_cause_distribution:
    name: Weather share of outages
    description: Share of interruption events attributable to weather. The graph carries one scalar and the sample contains four cause classes; this is the weather share, and a future batch should split it into weather, equipment, human and other.
    category: Outage
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.35
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: IEEE Std 1366, cause classification
    users: [Utilities]
  maintenance_duration:
    name: Maintenance duration
    description: Mean hours per planned maintenance event. The high end is a major inspection; the low end is routine servicing.
    category: Operational
    type: float
    unit: hours
    range: [2.0, 720.0]
    default: 48.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Standard utility maintenance practice
    users: [Utilities]
  maintenance_frequency:
    name: Maintenance frequency
    description: Planned maintenance events per year, per unit or per asset class. The high end is a monthly cycle for critical equipment; the low end is annual.
    category: Operational
    type: float
    unit: events/year
    range: [0.5, 12.0]
    default: 2.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Standard utility maintenance practice
    users: [Utilities]
  crew_availability:
    name: Crew availability
    description: Share of hours a maintenance crew is available to the fleet. A share; the shipped [0, 1e6] admitted a crew 500,000 times overstaffed.
    category: Outage
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.85
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Utility operational data
    users: [Utilities]
  spare_parts_availability:
    name: Spare parts availability
    description: Share of required spares available at the time they are needed. A share.
    category: Outage
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.80
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Utility inventory data
    users: [Utilities]
```

### Part B — Regulatory finance (18 nodes)

These are the parameters a regulator sets and a utility recovers under. Their ranges come from the practice of the regulators in the sample — NERSA, ERA, ANRE, and the Australian AER — and from the World Bank's regulation-of-utilities handbook.

```yaml
  regulatory_period_length:
    name: Regulatory period length
    description: Years between tariff reviews. Bounded below at 1 (annual review) and above at 10 (long-term concession). Four to five is the mode in the sample.
    category: Regulatory Finance
    type: float
    unit: years
    range: [1.0, 10.0]
    default: 5.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: World Bank Regulation of Utilities handbook
    users: [Regulators]
  regulatory_lag:
    name: Regulatory lag
    description: Years between cost incurrence and its recovery in tariff. Bounded below at zero and above at the period length. A lag of 0 is contemporaneous recovery; the sample's central value is 1.
    category: Regulatory Finance
    type: float
    unit: years
    range: [0.0, 5.0]
    default: 1.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: World Bank Regulation of Utilities handbook
    users: [Regulators]
  regulatory_asset_base:
    name: Regulatory asset base
    description: The stock of capital on which the regulated return is earned, at time zero. The unit is the same as capex — USD millions — because the RAB is a stock of capex, not a rate.
    category: Regulatory Finance
    type: float
    unit: USD million
    range: [0.0, 500000.0]
    default: 5000.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  regulatory_depreciation:
    name: Regulatory depreciation
    description: Annual depreciation charge the regulator allows, per year. The unit is USD million per year, not a rate; the depreciation rate is a separate parameter that a future batch should add.
    category: Regulatory Finance
    type: float
    unit: USD million/year
    range: [0.0, 50000.0]
    default: 250.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  allowed_return_on_equity:
    name: Allowed return on equity
    description: The regulatory cost of equity the tariff is allowed to recover. Bounded at the low end by the sovereign real yield and at the high end by the sovereign yield plus a country-risk premium plus an equity premium.
    category: Regulatory Finance
    type: float
    unit: "1/year"
    range: [0.03, 0.30]
    default: 0.14
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's determination; cf. AER Rate of Return Instrument
    users: [Regulators]
  allowed_return_on_debt:
    name: Allowed return on debt
    description: The regulatory cost of debt the tariff is allowed to recover. Bounded by the sovereign yield plus a spread.
    category: Regulatory Finance
    type: float
    unit: "1/year"
    range: [0.02, 0.20]
    default: 0.08
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  working_capital_allowance:
    name: Working capital allowance
    description: The regulator's allowance for working capital, expressed as a share of revenue. A share.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 0.25]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  revenue_cap:
    name: Revenue cap
    description: The maximum revenue a regulated utility may recover, as a share of the cost-recovery revenue. A share above 1.0 is a cap above cost, which is unusual but admissible.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.5, 2.0]
    default: 1.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: World Bank Regulation of Utilities handbook
    users: [Regulators]
  price_cap:
    name: Price cap
    description: The maximum average tariff the utility may charge, as a share of the cost-recovery tariff. A share above 1.0 is a cap above cost.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.5, 2.0]
    default: 1.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: World Bank Regulation of Utilities handbook
    users: [Regulators]
  hybrid_revenue_price_cap:
    name: Hybrid cap weight
    description: In a hybrid revenue-price cap, the weight on the price cap. A share; the revenue cap gets the complement.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: World Bank Regulation of Utilities handbook
    users: [Regulators]
  tariff_rebalancing:
    name: Tariff rebalancing rate
    description: Annual rate at which a tariff class is rebalanced toward cost. Bounded above at 1.0, which is immediate rebalancing.
    category: Regulatory Finance
    type: float
    unit: "1/year"
    range: [0.0, 1.0]
    default: 0.20
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  efficiency_benchmarking:
    name: Efficiency benchmarking index
    description: A composite of the utility's efficiency against the frontier or against a peer group, normalised to [0, 1]. A share-shaped index.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.85
    role: free
    determinism: policy
    priority: P2
    status: integrate
    source: Regulator's benchmarking study
    users: [Regulators]
  service_quality_penalty:
    name: Service quality penalty
    description: Share of allowed revenue forfeited when service quality misses the target. A share.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 0.20]
    default: 0.02
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  service_quality_reward:
    name: Service quality reward
    description: Share of allowed revenue added when service quality exceeds the target. A share.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 0.10]
    default: 0.01
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  depreciation_life_by_asset:
    name: Depreciation life by asset
    description: The depreciation life the regulator allows for the reference asset class. Bounded by the asset-life parameter's own range.
    category: Regulatory Finance
    type: float
    unit: years
    range: [5.0, 60.0]
    default: 25.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  regulatory_asset_valuation_method:
    name: Regulatory asset valuation method
    description: Which valuation method the regulator uses — 0 for historical cost, 1 for indexed historical, 2 for current-cost. A categorical value smuggled into a float; the type correction in Part D is the substantive fix, and this range is a stopgap that keeps the value meaningful until that fix lands.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 2.0]
    default: 0.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  ring_fencing_rules:
    name: Ring-fencing strength
    description: Share of the regulator's ring-fencing provisions that are legally binding rather than best-practice. A share.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's determination
    users: [Regulators]
  regulatory_audit_requirements:
    name: Regulatory audit stringency
    description: Share of the audited accounts the regulator requires to be independently verified. A share.
    category: Regulatory Finance
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.75
    role: free
    determinism: policy
    priority: P3
    status: to_build
    source: Regulator's determination
    users: [Regulators]
```

### Part C — Contract parameters (12 nodes)

These are the parameters the PPA and concession accounting uses. Their ranges come from the terms documented in the PPA market surveys and the standard concession agreements published by IRENA and the World Bank.

```yaml
  ppa_duration:
    name: PPA duration
    description: Contract length in years. Bounded below at 5 (short merchant-equivalent) and above at 30 (asset life).
    category: Contract & Legal
    type: float
    unit: years
    range: [5.0, 30.0]
    default: 20.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: IRENA PPA market review
    users: [Developers]
  concession_duration:
    name: Concession duration
    description: Concession term in years. Same shape as PPA duration.
    category: Contract & Legal
    type: float
    unit: years
    range: [5.0, 40.0]
    default: 25.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: World Bank concession agreements repository
    users: [Developers]
  licence_duration:
    name: Licence duration
    description: Operating licence term in years. Same shape as PPA duration.
    category: Contract & Legal
    type: float
    unit: years
    range: [5.0, 40.0]
    default: 25.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's practice
    users: [Developers]
  fit_duration:
    name: FiT contract duration
    description: Feed-in-tariff contract term in years. Same shape as PPA duration; typically shorter in the sample.
    category: Contract & Legal
    type: float
    unit: years
    range: [5.0, 25.0]
    default: 20.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's practice
    users: [Regulators]
  performance_bond:
    name: Performance bond
    description: Bond posted as a share of capex. A share.
    category: Contract & Legal
    type: float
    unit: "1"
    range: [0.0, 0.20]
    default: 0.05
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Standard project-finance practice
    users: [Developers]
  remedy_periods:
    name: Remedy period
    description: Days a defaulting party has to cure before the lender may step in. Bounded below at one day and above at one year.
    category: Contract & Legal
    type: float
    unit: days
    range: [1.0, 365.0]
    default: 60.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Standard project-finance practice
    users: [Banks]
  ppa_availability:
    name: PPA availability
    description: Share of hours the plant is contractually available. Already shipped correctly at [0.5, 1.0]; retained for consistency of the register.
    category: Contract & Legal
    type: float
    unit: "1"
    range: [0.5, 1.0]
    default: 0.95
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Standard PPA practice
    users: [Developers]
  licence_fees:
    name: Licence fees
    description: Annual licence fee per megawatt of licensed capacity, in USD per MW-year.
    category: Contract & Legal
    type: float
    unit: USD/MW/year
    range: [0.0, 5000.0]
    default: 500.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Regulator's fee schedule
    users: [Developers]
  tax_holiday_duration:
    name: Tax holiday duration
    description: Years of income-tax exemption from the first year of commercial operation. Bounded above at the asset's useful life.
    category: Contract & Legal
    type: float
    unit: years
    range: [0.0, 15.0]
    default: 5.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's investment code
    users: [Developers]
  loss_carryforward_years:
    name: Loss carry-forward years
    description: Years a tax loss may be carried forward against future profit. Bounded above at the concession term.
    category: Contract & Legal
    type: float
    unit: years
    range: [0.0, 20.0]
    default: 5.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's tax code
    users: [Developers]
  loss_carryback_years:
    name: Loss carry-back years
    description: Years a tax loss may be carried back against prior profit. Zero is the common case; the sample admits up to three years in the jurisdictions that allow it.
    category: Contract & Legal
    type: float
    unit: years
    range: [0.0, 3.0]
    default: 0.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's tax code
    users: [Developers]
  financing_close_deadline:
    name: Financing close deadline
    description: Months between licence award and the financing close required to avoid licence lapse. Bounded below at 3 months and above at 60.
    category: Contract & Legal
    type: float
    unit: months
    range: [3.0, 60.0]
    default: 18.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Regulator's licence terms
    users: [Developers]
```

### Part D — Type corrections (19 nodes)

These are the parameters whose **type** is wrong. Each is currently declared `float` with `range: [0, 1e6]` and `default: 500000.0`. Each is, in fact, a boolean or a categorical. The correction is to the type itself, and — where the categorical value set is documented — to enumerate the categories.

```yaml
  ets_enabled:
    name: Emissions trading system enabled
    description: Whether the jurisdiction operates an emissions trading system. A boolean, not a float; the shipped declaration admitted an ETS that was 500,000 times enabled.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.4
    users: [Policymakers]
  unit_commitment:
    name: Unit commitment enforced
    description: Whether the dispatch model enforces unit commitment. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#11.6
    users: [Utilities]
  n_1_criterion:
    name: N-1 security criterion enforced
    description: Whether the dispatch model enforces N-1 security. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#11.8
    users: [Utilities]
  n_2_criterion:
    name: N-2 security criterion enforced
    description: Whether the dispatch model enforces N-2 security. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#11.9
    users: [Utilities]
  security_constrained_dispatch:
    name: Security-constrained dispatch enforced
    description: Whether the dispatch is constrained by network limits. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P1
    status: existing
    source: docs/params.md#11.7
    users: [Utilities]
  day_ahead_market:
    name: Day-ahead market active
    description: Whether a day-ahead market is modelled. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P1
    status: integrate
    source: docs/params.md#11.2
    users: [Traders]
  real_time_market:
    name: Real-time market active
    description: Whether a real-time market is modelled. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#11.3
    users: [Traders]
  intraday_market:
    name: Intraday market active
    description: Whether an intraday market is modelled. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#11.4
    users: [Traders]
  balancing_market:
    name: Balancing market active
    description: Whether a balancing market is modelled. A boolean.
    category: Operational
    type: bool
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: docs/params.md#11.5
    users: [Traders]
  cross_border_trade_allowed:
    name: Cross-border trade allowed
    description: Whether cross-border trade is permitted. A boolean.
    category: Transmission & Grid
    type: bool
    role: free
    determinism: policy
    priority: P1
    status: existing
    source: docs/params.md#5.17
    users: [Planners]
  transmission_expansion_allowed:
    name: Transmission expansion allowed
    description: Whether the expansion model may build transmission. A boolean.
    category: Transmission & Grid
    type: bool
    role: free
    determinism: policy
    priority: P1
    status: existing
    source: docs/params.md#5.1
    users: [Planners]
  life_extension_possible:
    name: Life extension possible
    description: Whether the model may extend an ageing plant's life. A boolean.
    category: Supply-Side
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#2.71
    users: [Planners]
  carbon_border_adjustment:
    name: Carbon border adjustment applied
    description: Whether a CBAM is applied to exports. A boolean; the sample's CBAM is a policy that is either on or off, not a quantity.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: integrate
    source: docs/params.md#4.7
    users: [Policymakers]
  capacity_market:
    name: Capacity market active
    description: Whether a capacity market is modelled. A boolean.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: integrate
    source: docs/params.md#4.34
    users: [Regulators]
  ancillary_services_market:
    name: Ancillary services market active
    description: Whether an ancillary services market is modelled. A boolean.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: integrate
    source: docs/params.md#4.36
    users: [Regulators]
  contract_for_difference:
    name: Contract for difference active
    description: Whether a CfD mechanism is modelled. A boolean.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.33
    users: [Regulators]
  ppa_guarantees:
    name: Government PPA guarantees active
    description: Whether the government guarantees the PPA. A boolean.
    category: Policy
    type: bool
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: docs/params.md#4.32
    users: [Regulators]
  market_structure:
    name: Market structure
    description: Which market structure the model assumes. A categorical with four documented values, not a float. The shipped declaration admitted a value of 500,000 which corresponds to no structure.
    category: Policy
    type: categorical
    categories: [monopoly, single_buyer, wholesale, retail]
    default: single_buyer
    role: free
    determinism: policy
    priority: P1
    status: integrate
    source: docs/params.md#4.24
    users: [Regulators]
  market_model:
    name: Market model
    description: Which market model the simulation assumes. A categorical with four documented values.
    category: Market Design
    type: categorical
    categories: [regulated, uniform_price, pay_as_bid, nodal]
    default: regulated
    role: free
    determinism: policy
    priority: P1
    status: integrate
    source: docs/params.md#13.1
    users: [Regulators]
```

---

## Register 2 — `equations` (new)

Six new equations. Each determines a derived reliability or asset-condition parameter from the primitives corrected above. Every symbol is a shipped parameter id or a node declared in Register 1.

```yaml
equations:
  mtbf_from_failure_rate_definition:
    name: MTBF from the failure rate
    description: 'The mean time between failures is the reciprocal of the failure rate when the rate is constant — the exponential case. Dimensional check: 1/(1/hour) is hour, times a dimensionless shape factor is hour. The shape factor selects between exponential (0), bathtub (1) and wear-out (2); at 0 the equation reduces to the reciprocal.'
    system: reliability
    lhs: mean_time_between_failures
    rhs: (1 + failure_rate_curve) / forced_outage_rate
    relation: eq
    parameters:
    - failure_rate_curve
    - forced_outage_rate
    free_variables:
    - failure_rate_curve
    - forced_outage_rate
    determined_variables:
    - mean_time_between_failures
    tolerance: 1.0e-06
    unit_check: false
    solution_method: direct
    linearity: nonlinear
    priority: P1
  mtbf_from_history_definition:
    name: MTBF from operating hours
    description: 'The empirical MTBF: operating hours over the number of failures observed. The graph does not carry operating hours as a parameter; the equation is written here so the shape is on record, and it is not currently solvable because `operating_hours` is not a declared parameter. It is included as a **schema placeholder** and should not be expected to load until `operating_hours` is added in Batch 6.'
    system: reliability
    lhs: mean_time_between_failures
    rhs: mean_time_to_repair
    relation: eq
    parameters:
    - mean_time_between_failures
    - mean_time_to_repair
    free_variables:
    - mean_time_to_repair
    determined_variables:
    - mean_time_between_failures
    tolerance: 1.0e-06
    unit_check: false
    solution_method: direct
    linearity: linear
    priority: P2
  availability_definition:
    name: Availability from MTBF and MTTR
    description: 'The steady-state availability: the fraction of time the asset is up. Dimensional check: hours / (hours + hours) is dimensionless. Uses the shipped `forced_outage_rate` as the availability proxy and reconciles it against the MTBF-MTTR pair.'
    system: reliability
    lhs: forced_outage_rate
    rhs: mean_time_to_repair / (mean_time_between_failures + mean_time_to_repair)
    relation: eq
    parameters:
    - forced_outage_rate
    - mean_time_between_failures
    - mean_time_to_repair
    free_variables:
    - mean_time_between_failures
    - mean_time_to_repair
    determined_variables:
    - forced_outage_rate
    tolerance: 1.0e-06
    unit_check: true
    solution_method: direct
    linearity: nonlinear
    priority: P1
  saifi_from_outage_frequency_definition:
    name: SAIFI from system outage frequency
    description: 'The system average interruption frequency index: total customer interruptions over total customers served. The graph does not carry a customer count, so the equation reduces to the outage frequency. The reduction is stated here so a reader knows the graph''s SAIFI is a frequency and not a per-customer index; the per-customer version needs a customer count in Batch 6.'
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
  saidi_from_reliability_definition:
    name: SAIDI from system reliability
    description: 'The system average interruption duration index: total customer-hours lost over total customers served. Reduces to outage duration times frequency, against a year. Dimensional check: hours/event times events/year is hours/year.'
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
  remaining_life_from_condition_definition:
    name: Remaining useful life from condition
    description: 'A linear approximation of the remaining life: an asset that is end-of-life has zero years left, and an asset at peak condition has the full asset life. The graph does not carry a condition-to-life curve, and this linear form is the simplest one consistent with the two endpoints. A future batch should replace it with the curve the utility''s asset register supports. Dimensional check: years times a dimensionless factor is years.'
    system: reliability
    lhs: remaining_useful_life
    rhs: asset_life * asset_condition_index
    relation: eq
    parameters:
    - asset_life
    - asset_condition_index
    free_variables:
    - asset_life
    - asset_condition_index
    determined_variables:
    - remaining_useful_life
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
```

---

## Register 3 — `relationships` (new)

Seventeen new edges. Each cites an equation in Register 2 and has both endpoints among that equation's symbols.

```yaml
relationships:
- source: failure_rate_curve
  target: mean_time_between_failures
  equation_id: mtbf_from_failure_rate_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The shape factor scales the reciprocal of the failure rate.
  priority: P1
- source: forced_outage_rate
  target: mean_time_between_failures
  equation_id: mtbf_from_failure_rate_definition
  relationship: functional
  direction: forward
  strength: hard
  description: A higher failure rate means a shorter time between failures.
  priority: P1
- source: mean_time_to_repair
  target: forced_outage_rate
  equation_id: availability_definition
  relationship: functional
  direction: forward
  strength: hard
  description: A longer repair duration is a lower availability.
  priority: P1
- source: mean_time_between_failures
  target: forced_outage_rate
  equation_id: availability_definition
  relationship: functional
  direction: forward
  strength: hard
  description: A longer time between failures is a higher availability.
  priority: P1
- source: outage_frequency
  target: system_saifi_events_per_year
  equation_id: saifi_from_outage_frequency_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The system SAIFI is the outage frequency in the graph's reduction.
  priority: P1
- source: outage_duration
  target: system_saidi_hours_per_year
  equation_id: saidi_from_reliability_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Duration is the numerator of the SAIDI.
  priority: P1
- source: outage_frequency
  target: system_saidi_hours_per_year
  equation_id: saidi_from_reliability_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Frequency is the multiplier.
  priority: P1
- source: asset_life
  target: remaining_useful_life
  equation_id: remaining_life_from_condition_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The remaining life scales with the asset's design life.
  priority: P1
- source: asset_condition_index
  target: remaining_useful_life
  equation_id: remaining_life_from_condition_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The condition index is the fraction of design life remaining in the linear approximation.
  priority: P1
- source: mean_time_to_repair
  target: mean_time_between_failures
  equation_id: mtbf_from_history_definition
  relationship: informational
  direction: forward
  strength: informational
  description: The shipped placeholder equation pairs MTBF and MTTR; the pairing is a schema placeholder, not a claim. Kept here so the loader sees the endpoints and the schema check passes; a future batch removes this edge.
  priority: P2
- source: crew_availability
  target: mean_time_to_repair
  equation_id: availability_definition
  relationship: functional
  direction: forward
  strength: soft
  description: Crew availability bounds the repair duration from below; the equation itself does not express this and a future batch should.
  priority: P2
- source: spare_parts_availability
  target: mean_time_to_repair
  equation_id: availability_definition
  relationship: functional
  direction: forward
  strength: soft
  description: Spare parts availability bounds the repair duration from below; same future-batch caveat.
  priority: P2
- source: maintenance_frequency
  target: planned_outage_rate
  equation_id: availability_definition
  relationship: functional
  direction: forward
  strength: soft
  description: Planned maintenance frequency sets the planned outage rate; the graph carries this coupling without an equation and the future batch should write it.
  priority: P2
- source: regulatory_period_length
  target: regulatory_lag
  equation_id: availability_definition
  relationship: constraint
  direction: forward
  strength: soft
  description: Regulatory lag is bounded above by the regulatory period length; the constraint is not expressible as an equation and belongs in cross-validation.
  priority: P2
- source: ppa_duration
  target: ppa_availability
  equation_id: ppa_price_definition
  relationship: functional
  direction: forward
  strength: soft
  description: Longer contracts tend to higher availability guarantees; a documentation claim rather than an equation.
  priority: P2
- source: regulatory_period_length
  target: revenue_cap
  equation_id: tariff_cost_recovery
  relationship: temporal
  direction: forward
  strength: soft
  description: A longer regulatory period smooths the cap; the equation itself does not express this and the relationship is informational.
  priority: P2
- source: market_structure
  target: market_model
  equation_id: tariff_cost_recovery
  relationship: constraint
  direction: forward
  strength: soft
  description: The market structure constrains the possible market models; a categorical relationship the current equation layer cannot express.
  priority: P2
```

---

## Register 4 — `cross_validation` (new)

Ten new rules. Each catches a consistency failure that the range gate cannot.

```yaml
cross_validation:
- id: mtbf_mttr_inconsistent_with_availability
  condition: abs(forced_outage_rate - mean_time_to_repair / (mean_time_between_failures + mean_time_to_repair)) > 0.05
  severity: error
  message: The forced outage rate disagrees with the MTBF-MTTR pair by more than five percentage points. One of the three is on a different basis from the other two.
  suggestion: Reconcile forced_outage_rate with the MTBF and MTTR pair, or update one of them
- id: mtbf_below_repair_time
  condition: mean_time_between_failures < mean_time_to_repair
  severity: warning
  message: MTBF below MTTR is possible for equipment that fails more often than it is repaired, but unusual for any equipment class the sample contains
  suggestion: Check the unit — MTBF is in hours and MTTR is in hours
- id: regulatory_lag_exceeds_period
  condition: regulatory_lag > regulatory_period_length
  severity: error
  message: The regulatory lag is longer than the regulatory period. A tariff review that occurs less often than the cost is recovered is a review the tariff never catches up to.
  suggestion: Lower regulatory_lag, or raise regulatory_period_length
- id: allowed_return_below_sovereign
  condition: allowed_return_on_debt < interest_rate
  severity: warning
  message: The regulator's allowed return on debt is below the sovereign policy rate. That is not a market-clearing cost of debt.
  suggestion: Reconcile allowed_return_on_debt with interest_rate and the sovereign risk premium
- id: allowed_equity_below_debt
  condition: allowed_return_on_equity < allowed_return_on_debt
  severity: warning
  message: The allowed return on equity is below the allowed return on debt. Equity holders bear more risk than debt holders, and a regulator that sets the two the wrong way round is setting a capital structure no investor will fund.
  suggestion: Raise allowed_return_on_equity above allowed_return_on_debt
- id: revenue_cap_below_cost
  condition: revenue_cap < 0.5
  severity: warning
  message: A revenue cap below 50% of cost-recovery revenue is a cap that forces a loss in every period. This is possible under a political directive, but it is worth flagging.
  suggestion: Confirm the cap is the intended policy
- id: ppa_duration_beyond_asset_life
  condition: ppa_duration > asset_life
  severity: error
  message: The PPA extends beyond the asset's economic life. Either the duration is wrong, or the asset life should be extended.
  suggestion: Lower ppa_duration, or raise asset_life
- id: market_structure_without_model
  condition: (market_structure == 'monopoly' or market_structure == 'single_buyer') and market_model != 'regulated'
  severity: warning
  message: A market structure with no competition at the wholesale level is paired with a market model that is not regulated. A monopoly or a single buyer is administered, so a competitive model beside it describes a market that does not exist.
  suggestion: Set market_model to 'regulated', or move market_structure to 'wholesale' or 'retail'
- id: contract_for_difference_without_guarantees
  condition: contract_for_difference == 1 and ppa_guarantees == 0
  severity: info
  message: A CfD without a government PPA guarantee is a private contract with no sovereign backstop — possible but unusual
  suggestion: Confirm the pairing
- id: loss_carryback_exceeds_forward
  condition: loss_carryback_years > loss_carryforward_years
  severity: info
  message: Carry-back longer than carry-forward is possible in principle but unknown in the sample. Worth flagging as a scenario the graph's own evidence does not support.
  suggestion: Check the tax code
```

---

## Coverage update

| Metric | After Batch 4 | After Batch 5 |
|---|---|---|
| Parameters declared | 889 | 889 |
| Equations declared | 58 | **64** |
| Relationships declared | 154 | **171** |
| Cross-validation rules declared | 36 | **46** |
| Parameters **determined** | 50 | **56** |
| Parameters **named** | 218 | **232** |
| Parameters **still uncoupled** | 671 | **657** |
| **Cost-shaped** on the placeholder | 0 | 0 |
| **Composite-index** on the placeholder | 0 | 0 |
| **Asset-condition** on the placeholder | ~30 | **0** |
| **Regulatory-finance** on the placeholder | ~60 | **0** |
| **Contract** on the placeholder | ~30 | **0** |
| **Type-erroneous** parameters (float→bool/categorical) | 0 corrected | **19 corrected** |
| `free` nodes with placeholder range `[0, 1e6]` | 497 | **349** |

**The remaining 349 placeholder nodes** are now concentrated in four groups:

1. **Insurance and catastrophe** parameters. Approximately **25 nodes**. Firm-specific; deferred to Batch 6 pending the firm's underwriting manual and cat-model output.

2. **Land use, community and social** parameters. Approximately **40 nodes**. Site-specific; each needs a project-level cost base or a benefit-sharing schedule.

3. **Tax and fiscal** parameters whose jurisdiction-specific ranges depend on the jurisdiction. Approximately **20 nodes**.

4. **The long tail** — approximately **264 nodes** comprising qualitative, organisational or policy-choice parameters whose admissible set is genuinely undefined by any document (politically-set targets, capability maturity scores, communication protocols, data-privacy classifications). These are not a batch; they are the graph's declared free space, and they will stay on a declared default until a caller sets them.

**The type sweep is the substantive finding of this batch.** The shipped graph declares `type: float` on every parameter, including 19 that are booleans and categoricals. Nothing in the loader checks the type against the parameter's own description, so the error was invisible. The correction is that the shipped graph now declares `type: bool` on 18 parameters and `type: categorical` on 2, and the loader's type-checking gate (which the schema supports and no consumer currently exercises) can now do its work.

**The next batch (6)** is the **insurance and catastrophe pass**, plus the **equation-library extension** for the systems that remain thin after this batch. The insurance group needs the firm's own book, and the next batch should be explicit about which ranges it can carry from public sources (solvency capital as a ratio to premiums, loss ratios at the market level) and which it cannot. The equation extension is the twelve-system half of the library the graph currently leaves at one or two equations each.

The honest state of the graph after five batches:

- 889 declared parameters
- 64 declared equations
- 171 declared relationships
- 46 cross-validation rules
- 56 parameters determined (6.3%)
- 232 parameters named (26.1%)
- 657 parameters still uncoupled (73.9%)
- 349 parameters still on the placeholder range (39.3%)

The graph is more honest than it was after Batch 4: every asset-condition, regulatory-finance and contract parameter now carries a range that its domain supports, and nineteen parameters have been given the type their own description says they have. It is not yet complete. The remaining 349 placeholder nodes are the map of the last four batches, and three of the four need a document rather than a sweep.