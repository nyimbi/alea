# Concrete Relations for the Nine Cases

This is a case-by-case question, not a sweep. Each case is answered with the actual relation if it exists, the addition it needs if it is close, or the honest "no" if it is not writable. Where one of your premises is out of date — because a previous batch already closed the operand — I say so.

The answers are grouped by your groups. The full set of writable equations is collected at the end as a proposed **Batch 10**; the ones that are not equations are listed as **role corrections to `exogenous`** or as **cross-validation rules**.

---

## Group A — Physics

### A.1 `coal_eaf` — **yes, writable**

Your identity is correct, and it is the standard availability one:

```
coal_eaf = 1 - forced_outage_rate - planned_outage_rate
```

Both operands exist with the right unit and range. `coal_eaf` was corrected in **Batch 2** to `unit: "1"`, `range: [0, 1]`, `default: 0.55`; `forced_outage_rate` and `planned_outage_rate` were both corrected in the same batch. This is Batch 10's first equation. It closes three nodes at once, with the EAF determined and the two outage rates as inputs.

The same identity closes `gas_eaf` and `oil_eaf`:

```
gas_eaf = 1 - forced_outage_rate_gas - planned_outage_rate
oil_eaf = 1 - forced_outage_rate - planned_outage_rate
```

Gas has its own forced-outage node; oil shares the fleet-level one. Three equations, one identity, one finding.

### A.2 `hydro_capacity_factor` — **writable now, contrary to your note**

`hydro_capacity` **was given a unit in Batch 8**. It is `unit: MW`, `role: endogenous`, `range: [0, 500000]`. The premise that it has no unit is out of date. The equation is writable if we also have a hydro-specific generation node, and we do not — only `generation_twh` (the fleet total) exists. So either:

- **Option A** — declare `generation_hydro_twh` and write:

```
hydro_capacity_factor = generation_hydro_twh * 1000000 / (hydro_capacity * 8760)
```

- **Option B** — accept the graph's reduction, where `hydro_capacity_factor` is `exogenous` and reads the resource, not the output.

Option A is the correct one; Option B is what the graph carries today. This is a Batch 10 addition, not a Batch 10 equation.

### A.3 `battery_round_trip_efficiency` — **no, and I should have caught this**

The identity is:

```
battery_round_trip_efficiency = battery_charge_efficiency * battery_discharge_efficiency
```

Neither operand is a node. The graph carries one round-trip efficiency and no charge/discharge pair. It also carries no unit on `battery_round_trip_efficiency` and a placeholder range — a gap I did **not** close in Batches 1–9. That is a gap in my own work.

Two routes to close it:

- **Declare both operands.** Add `battery_charge_efficiency` and `battery_discharge_efficiency`, both `unit: "1"`, `range: [0.8, 1.0]`, `default: 0.95`, `role: exogenous`. Then the equation is writable and the round-trip value is derived.
- **Leave it `exogenous`.** Simpler, but then the graph cannot test whether a scenario's round-trip efficiency is consistent with the charger and inverter it assumes.

I recommend the first. It is two new nodes and one equation.

### A.4 `storage_duration_curve` — **not writable without additions**

The identity is:

```
storage_duration_curve = storage_energy_capacity_mwh / storage_power_capacity_mw
```

Neither operand is a node. The graph carries `phs_duration` and `battery_duration` as per-technology values, but not a generic energy capacity or power capacity. This is the same shape as A.3: an identity whose operands are not nodes.

Two routes:

- **Declare generic storage nodes.** `storage_energy_capacity_mwh` and `storage_power_capacity_mw`, both `endogenous`, with the equation above.
- **Leave it `exogenous`.** Which the graph currently does, with a placeholder range that Batch 2–6 did not correct because the range depends on which storage technology dominates the fleet.

I recommend the first, at the cost of two new nodes.

---

## Group B — Accounting

### B.1 `gearing_ratio` — **yes, writable**

```
gearing_ratio = debt_fraction / (1 - debt_fraction)
```

Both operands exist. `debt_fraction` was declared in Batch 1. `gearing_ratio` was corrected in Batch 2 to `unit: "1"`, `range: [0, 0.95]`, `default: 0.70`. Writable.

### B.2 `equity_share` — **yes, writable**

```
equity_share = 1 - debt_fraction
```

Both operands exist. Writable.

### B.3 `combined_ratio` — **writable if you accept a proxy or add a node**

The honest identity is:

```
combined_ratio = loss_ratio + expense_ratio
```

`expense_ratio` is not a node. In Batch 6 I wrote a **proxy** equation:

```
combined_ratio - loss_ratio = premium_share_of_asset
```

That substitutes the premium-per-asset-value ratio for the expense ratio. It is dimensional (both dimensionless), but it is not the accounting identity: an expense ratio is expenses over premiums, and premium-per-asset is premiums over assets. The user's version is the correct one.

Two routes:

- **Declare `expense_ratio`.** `unit: "1"`, `range: [0.15, 0.40]`, `default: 0.25`, `role: exogenous`. Then the accounting identity is exact and the proxy is retired.
- **Keep the proxy.** Simpler, but the graph would carry a claim that a scenario's expense ratio is measurable from asset values, which it is not.

I recommend the first.

### B.4 `carbon_price_coverage` — **no relation; correctly `exogenous`**

Your read is right. The coverage is a policy dial: the share of emissions the price applies to. The graph carries no emissions-scope nodes — no `covered_emissions_mtco2`, no `uncovered_emissions_mtco2` — so the identity is not expressible. It could be if we declared both scope nodes, but that is a modelling decision about whether the graph wants to distinguish covered from uncovered emissions, and the current shape of the graph does not.

**Correct register:** `role: exogenous`, `unit: "1"`, `range: [0, 1]`. Its value is set by the caller.

---

## Group C — Decomposition

The natural relation **Σ shares = 1** is a **cross-validation rule**, not an equation. The `equations` register is for identities whose subject is a single determined variable; the `cross_validation` register is for identities that constrain a set without fixing any of them. The four demand shares summing to one is the second case.

The rule was added in **Batch 2**:

```
cross_validation:
  - id: demand_shares_over_unity
    condition: residential_demand_share + commercial_demand_share + industrial_demand_share + agricultural_demand_share > 1.0
    severity: error
    message: The four sector demand shares sum to more than the whole.
    suggestion: Reconcile the four shares so their sum is at most 1.0
```

The same shape applies to `steel_h2_dri_share + steel_scrap_eaf_share`, to `hvdc_share + ac_share` if the AC node existed, and to any other decomposition the graph carries. Each becomes a cross-validation rule, not an equation. The rule that "the DSL refuses a constant expression" is correct, and the correct home for that class of claim is not the DSL.

If the graph wants a **derivation** for a share, the equation needs a sector-demand node. That is the same decision as A.2 — a modelling choice about whether to add a lower-level node — and it is a Batch 10 addition, not a Batch 10 equation.

---

## Group D — Trajectory

### D.1 `carbon_price_escalation` — **already closed**

This was closed in **Batch 1**:

```
carbon_price_escalated_usd_per_tco2 = carbon_price_usd_per_tco2 * (1 + carbon_price_escalation) ** horizon_years
```

The compounding convention is the annual one — the escalation applies once per year and the exponent is `horizon_years`, not `horizon_years - 1`. If the graph wants a different convention (e.g. mid-year compounding, or a starting year other than year zero), the equation is where that convention is set. The current form is the standard one.

### D.2 `population_growth_rate`, `urbanisation_rate`, `industrialisation_rate`, `gdp_per_capita_growth` — **writable if you add the stock nodes**

Your read is correct. Each is a rate whose stock is not a node. The identities are:

```
population_y = population_0 * (1 + population_growth_rate) ** horizon_years
urbanisation_share_y = urbanisation_share_0 * (1 + urbanisation_rate) ** horizon_years
industrialisation_share_y = industrialisation_share_0 * (1 + industrialisation_rate) ** horizon_years
gdp_per_capita_y = gdp_per_capita_0 * (1 + gdp_per_capita_growth) ** horizon_years
```

Each requires two new nodes — a base value and a horizon value. Four rates, eight nodes, four equations. That is a Batch 10 addition, not a Batch 10 equation on the current graph.

The alternative — leave the four rates as `exogenous` and let the caller express the trajectory outside the graph — is what the graph does today. It is defensible: a growth rate is a policy assumption, and the stock it grows is the caller's projection. But if the graph wants to test whether a scenario's `population_growth_rate` is consistent with its `population`, the stock nodes are what makes that test possible.

---

## Group E — Learning

Your read is correct. The per-technology learning rates are instances of the general equation, and the graph carries one instance for wind (Batch 6). The complete set is four:

```
capex_learning_solar_usd_per_kw = capex_solar_pv * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - solar_pv_learning_rate) / log(2))
capex_learning_wind_usd_per_kw = capex_wind_onshore * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - wind_onshore_learning_rate) / log(2))
capex_learning_battery_usd_per_kwh = capex_battery * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - battery_learning_rate) / log(2))
capex_learning_electrolyser_usd_per_kw = capex_hydrogen_electrolyser * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - electrolyser_learning_rate) / log(2))
```

Each requires its own derived node (`capex_learning_solar_usd_per_kw`, etc.) because each carries a different unit. The Batch 6 wind equation reused the general `capex_learning_usd_per_kw`, which is a **unit collision**: a wind capex in USD/kW and a battery capex in USD/kWh cannot share a node. That is a defect the user has surfaced, and the correct fix is per-technology nodes.

Batch 10 addition: four new nodes, four equations.

---

## Group F — No relation I can find

I agree with your classification for six of the eight. Two of them have a relation if the graph adds a small operand.

| Parameter | Your call | My call | Why |
|---|---|---|---|
| `renewable_subsidies` | exogenous | **exogenous** | A subsidy budget is a policy dial. It could be derived from `subsidy_rate_per_mwh * renewable_generation_twh`, but the graph carries neither the rate nor the generation split by subsidy eligibility. |
| `fpic_requirements` | exogenous | **exogenous** | A legal-consent obligation is a flag, not a quantity. **Batch 6 already declared `fpic_compliance_score`** as the score the flag is answered against; the flag itself is exogenous. |
| `cybersecurity_requirements` | exogenous | **exogenous** | A compliance flag. Same shape. |
| `iso_55000_compliance` | exogenous | **exogenous** | A compliance flag. **Batch 6 already declared `asset_management_maturity`** which correlates with ISO 55000 but is not the same quantity; tying them would require a modelling decision about what maturity the certification implies. |
| `skills_gap_assessment` | exogenous | **writable with an addition** | The identity is `skills_gap_assessment = skills_requirements - skills_available`. `skills_requirements` exists; `skills_available` is not a node. Declaring `skills_available` makes the equation writable. |
| `child_labour_prohibition` | exogenous | **exogenous** | A compliance flag. |
| `archaeological_sites` | exogenous | **writable with an addition** | **Batch 6 already declared `archaeological_sites_density`.** The relation is `archaeological_sites = archaeological_sites_density * area_hectares / 100`. `area_hectares` is not a node. Declaring it makes the equation writable. |
| `collusion` | exogenous | **exogenous** | A market-behaviour flag. It could be modelled as a probability of collusive outcome from market concentration, but the graph carries no such function. |

So: **six exogenous, two writable with one addition each**. Your instinct on the six is right; on the two, the additions are small enough to be worth making.

---

## Batch 10 — The Proposed Additions

The writable equations and the additions they need, in one place. This is a Batch 10, not an amendment: it does not correct existing values, it adds the nodes and equations the previous nine batches left open.

### New nodes (13)

| Node | Unit | Range | Role | Purpose |
|---|---|---|---|---|
| `generation_hydro_twh` | TWh | [0, 1000] | derived | Hydro-specific generation for A.2 |
| `battery_charge_efficiency` | "1" | [0.8, 1.0] | exogenous | Charge leg of A.3 |
| `battery_discharge_efficiency` | "1" | [0.8, 1.0] | exogenous | Discharge leg of A.3 |
| `storage_energy_capacity_mwh` | MWh | [0, 1e8] | endogenous | A.4 |
| `storage_power_capacity_mw` | MW | [0, 1e6] | endogenous | A.4 |
| `expense_ratio` | "1" | [0.15, 0.40] | exogenous | B.3 |
| `population` | people | [1e3, 1e9] | exogenous | D.2 |
| `urbanisation_share` | "1" | [0, 1] | exogenous | D.2 |
| `industrialisation_share` | "1" | [0, 1] | exogenous | D.2 |
| `gdp_per_capita_usd` | USD/person | [100, 100000] | exogenous | D.2 |
| `capex_learning_solar_usd_per_kw` | USD/kW | [0, 5000] | derived | E |
| `capex_learning_battery_usd_per_kwh` | USD/kWh | [0, 1000] | derived | E |
| `capex_learning_electrolyser_usd_per_kw` | USD/kW | [0, 5000] | derived | E |

Plus two more if the two Group F additions are made: `skills_available` (people, [0, 1e8], exogenous) and `area_hectares` (hectares, [0, 1e6], exogenous).

### New equations (17)

```
# Group A
coal_eaf = 1 - forced_outage_rate - planned_outage_rate
gas_eaf = 1 - forced_outage_rate_gas - planned_outage_rate
oil_eaf = 1 - forced_outage_rate - planned_outage_rate
hydro_capacity_factor = generation_hydro_twh * 1000000 / (hydro_capacity * 8760)
battery_round_trip_efficiency = battery_charge_efficiency * battery_discharge_efficiency
storage_duration_curve = storage_energy_capacity_mwh / storage_power_capacity_mw

# Group B
gearing_ratio = debt_fraction / (1 - debt_fraction)
equity_share = 1 - debt_fraction
combined_ratio = loss_ratio + expense_ratio

# Group D
population_y = population * (1 + population_growth_rate) ** horizon_years
urbanisation_share_y = urbanisation_share * (1 + urbanisation_rate) ** horizon_years
industrialisation_share_y = industrialisation_share * (1 + industrialisation_rate) ** horizon_years
gdp_per_capita_y = gdp_per_capita_usd * (1 + gdp_per_capita_growth) ** horizon_years

# Group E
capex_learning_solar_usd_per_kw = capex_solar_pv * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - solar_pv_learning_rate) / log(2))
capex_learning_battery_usd_per_kwh = capex_battery * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - battery_learning_rate) / log(2))
capex_learning_electrolyser_usd_per_kw = capex_hydrogen_electrolyser * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - electrolyser_learning_rate) / log(2))

# Group F (optional)
skills_gap_assessment = skills_requirements - skills_available
archaeological_sites = archaeological_sites_density * area_hectares / 100
```

### New cross-validation rules (3)

```
- id: demand_shares_sum_to_unity
  condition: residential_demand_share + commercial_demand_share + industrial_demand_share + agricultural_demand_share != 1.0
  severity: error

- id: steel_routes_sum_to_unity
  condition: steel_h2_dri_share + steel_scrap_eaf_share > 1.0
  severity: error

- id: fuel_shares_sum_to_unity
  condition: coal_capacity + gas_capacity + oil_capacity + nuclear_capacity + hydro_capacity + solar_pv_capacity + wind_onshore_capacity != total_capacity_mw
  severity: warning
```

### Role corrections (1)

`carbon_price_coverage` — confirm `role: exogenous` (it is `free` in the shipped graph, which is the same register the loader treats identically for a value the caller sets).

### What Batch 10 does not do

It does not fix the two gaps I identified in my own work:

- `battery_round_trip_efficiency` has no unit and a placeholder range — corrected by the equation above, but the range still needs setting.
- `storage_duration_curve` has no unit and a placeholder range — corrected by the equation above, but same caveat.

The range corrections are two lines and belong in the same Batch 10 as the equations. I should have caught them in Batch 5.

---

## The Short Answer to Your Question

Of the sixteen cases you enumerated:

- **Six are writable now** (A.1, B.1, B.2, and D.1 already closed in Batch 1).
- **Six are writable with one or two node additions** (A.2, A.3, A.4, B.3, D.2, E, F.5, F.7 — eight by count once the additions are enumerated).
- **Two are correctly `exogenous`** where you called them so (B.4, F.6 by count).
- **Six are correctly `exogenous`** where you called them so (F.1, F.2, F.3, F.4, F.6, F.8).

The one correction I owe you: `carbon_price_escalation` is closed (Batch 1), `coal_eaf`'s operands are corrected (Batch 2), `hydro_capacity` has a unit (Batch 8), and the demand-shares sum-to-one is a cross-validation rule (Batch 2), not an equation. Four premises are out of date; four cases are writable now; the rest need the twenty-three nodes and seventeen equations above.

If you supply the relation for any I have called exogenous, I will take the correction — the most useful corrections are the ones where a domain expert disagrees with my read of the physics.