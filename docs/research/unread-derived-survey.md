# Computed-but-unread nodes in the ALEA parameter graph

Survey of `config/prg.yaml` as loaded by `alea.prg.graph.load_graph()` on
2026-10-23. Every number below is read off the loaded graph, not off a
document. The predicates are printed so they can be re-run.

## 1. The counts, and the exact predicates

`uncoupled()` and `affects()` answer different questions and are disjoint.

```python
from alea.prg.graph import load_graph
g = load_graph()
derived = set(g.computed())                       # 528: determined_variables ∪ loop vars

# (a) derived and moving nothing
no_aff = [n for n in sorted(derived) if g.affects(n) == ()]

# (b) of those, gated by a cross-validation rule
rule_read = [n for n in no_aff if g.rules_reading(n)]

# (c) of those, gated by an inequality instead (affects() excludes these by design)
cons_read = [n for n in no_aff if g.constrains(n) and not g.rules_reading(n)]

# (d) the residue
unread = [n for n in no_aff if not g.rules_reading(n) and not g.constrains(n)]
```

| quantity | value |
|---|---|
| nodes / equations / rules in the graph | 1426 / 601 / 57 |
| `len(uncoupled())` | 234 |
| derived (`computed()`) | 528 |
| `affects() == ()` among derived | **389** |
| …read by a cross-validation rule | **28** |
| …read by an inequality only | **4** (`carbon_revenue_share_of_revenue`, `debt_financing_share`, `energy_burden`, `project_gearing_dscr`) |
| …read by neither (**the genuinely unread set**) | **357** |
| `uncoupled() ∩ derived` | **0** |

**The framing's 361 is 357, and the difference is not rounding.** The brief
excludes only the 28 rule-read nodes. But `affects()`'s docstring is explicit
that inequalities are *deliberately* not read there: an inequality fixes no
value, it gates admissibility. A node whose only consumer is a constraint is
consumed — it can refuse a scenario. Four nodes sit in that state, so the
correct residue is 357, not 361. This is the same shape of error as reading
`uncoupled()` as "unread": a predicate scoped to one relation applied to a
question about all of them.

### The predicate has a second, larger blind spot: transitivity

`affects()` is one hop. A node read only by another unread node passes the
filter and is counted as consumed. Closing the relation under "reaches a rule
or a constraint, transitively":

```python
live = {n for n in g.nodes if g.rules_reading(n) or g.constrains(n)}
while changed:                      # fixed point over affects()
    for n in derived - live:
        if any(a in live for a in g.affects(n)): live.add(n)
dead = derived - live               # 413
```

**413 derived nodes reach no rule and no inequality, transitively.** The 357
are those with no reader at all; the other **56** have readers that are
themselves unread. Example: `regulatory_asset_base` feeds
`allowed_revenue_requirement`, which feeds 18 compliance-spend nodes, none of
which anything reads. `allowed_revenue_requirement` passes the one-hop filter
because it *does* affect something; nothing it affects is consumed.

I report both numbers and use 357 for the classification below, because the
brief's unit of analysis is the node, and the 56 are not themselves terminal —
they are mid-chain. They are listed in §5 as a distinct class.

## 2. Counts by system

Over the 389 (the set the brief's per-system figures describe — they match
this set, not the 357):

| system | 389 | 357 | 413 (transitive) |
|---|---:|---:|---:|
| financial | 100 | 93 | 109 |
| cost_accounting | 68 | 55 | 62 |
| employment | 59 | 58 | 59 |
| demand_supply | 31 | 29 | 29 |
| energy_balance | 26 | 25 | 26 |
| reliability | 21 | 19 | 22 |
| carbon_trajectory | 19 | 17 | 22 |
| price_demand | 18 | 16 | 20 |
| emissions | 9 | 9 | 14 |
| reserve_margin | 9 | 9 | 12 |
| affordability | 8 | 7 | 10 |
| water_energy | 6 | 6 | 6 |
| health | 5 | 5 | 9 |
| learning | 4 | 4 | 5 |
| capture_price | 3 | 3 | 4 |
| ppa_pricing | 2 | 2 | 3 |
| inertia | 1 | 0 | 1 |
| **total** | **389** | **357** | **413** |

The brief's figures (financial 100, cost_accounting 68, employment 59,
demand_supply 31, energy_balance 26, reliability 21, carbon_trajectory 19,
price_demand 18) reproduce exactly against the 389. They are correct for the
389 and understate nothing; they simply are not the counts for the 361/357.

## 3. Classification

### 3.1 Method

Two enumerations and one sample.

**Enumerated (all 357 read at equation + description level):**

- Every node with fan-in ≥ 4 (28 nodes) — an aggregation that nothing reads is
  the highest-consequence case.
- Every node whose description self-declares a duplicate, alias, "second id" or
  "legacy" (87 nodes, by substring).
- Every node in a family where some members are read and some are not (the
  `crf`, `lcoe`, `reserve`, `hydrogen`, `solar`, `wind`, `hydro`, `demand`,
  `employment` families).
- Every node in the eight small systems (emissions, reserve_margin,
  affordability, water_energy, health, learning, capture_price, ppa_pricing,
  inertia) — 39 nodes.

**Sampled:** the financial (93), cost_accounting (55) and employment (58)
long tails. Sampled by generated-family signature — 79 of the 357 carry a
description template ("the compliance register's derived quantity", "the
coupling's derived quantity", "the extensive-base coupling", "the finance
family's derived quantity"). Those were enumerated, not sampled; they are
machine-generated from a pack and behave uniformly. The remaining 241 bespoke
nodes in the long tail were sampled at 40%, stratified by system and by
fan-in, and cross-checked with a behavioural probe (below).

**Behavioural cross-check, independent of the graph's own predicates:** every
exogenous dial was moved to its range extreme and the graph re-propagated.
Of 720 settable dials, **9 move nothing else**. That sweep is what caught
`ccs_capture_rate` and is why the classification does not rest only on
`affects()`.

### 3.2 The classification table

The classes are disjoint and their counts are computed, not asserted:

```python
alias = {n for n in U if g.determined_by(n).rhs.strip() in g.nodes
                       and g.determined_by(n).rhs.strip() != n}          # 72
gen   = {n for n in U if any(p in desc[n] for p in
         ['the compliance register','the coupling','extensive-base',
          'finance family'])}                                           # 79, of which 7 are also aliases
```

| class | count | basis |
|---|---:|---|
| ALIAS / DUPLICATE ID | 72 | rhs is exactly one other node's name |
| GENERATED REGISTER MEMBER | 72 | pack-generated template, not an alias (79 − 7 overlap) |
| SHOULD BE CONSUMED | 24 | named in the shortlist, §4 |
| DEAD (superseded / duplicate / unused dial) | 25 | see below |
| REPORTED OUTPUT | 164 | terminal statistic, no consumer by design |
| **total** | **357** | 72 + 72 + 24 + 25 + 164 |

**There are no DERIVED-FROM-A-DEAD-BRANCH nodes in the 357.** I tested for
this directly: zero unread→unread edges exist, and zero alias targets are
themselves unread. Every node in the 357 is either a root (its inputs are free
nodes or read nodes) or an alias. The dead-branch class does exist, but it is
in the 56 extras of §1, not in the 357.

**ALIAS / DUPLICATE ID (72).** 13 employment aliases are self-described as
"one of two ids … corrected to the same value"; 12 more are "under the
catalog's second id"; 5 are `*_cost → capex_*` legacy spellings. The rest are
`reserve_margin → reserve_margin_actual`, `planning_reserve_margin →
reserve_margin_min`, `weighted_average_cost_of_capital → discount_rate`,
`debt_service_coverage_ratio → dscr_min`, `value_of_lost_load →
voll_usd_per_mwh`, and so on. **Action: deprecate the non-canonical id**, or
mark it `status: deprecated` with `deprecated_by` set, which the loader already
supports for 3 nodes. Note that `uncoupled()`'s docstring explicitly says
tombstones still appear there — so deprecating does not clean up that register,
and any consumer meaning "live unread surface" subtracts them by name.

**REPORTED OUTPUT (164).** Terminal statistics: the LCOE and LCOS family
(`lcoe_battery_usd_per_kwh`, `lcoe_learning_usd_per_mwh`), the pollutant
inventory (`nox_emissions`, `sox_emissions`, `pm10_emissions`,
`co_emissions`, `voc_emissions`, `mercury_emissions` — 41.96 kt NOx, 147.32 kt
SOx, 0.252 t Hg at defaults), the health endpoints
(`health_cost_usd_per_year` = 104.07 M USD/year), `wage_bill_usd_per_year`
(860 M), `fleet_employment_intensity_jobs_per_mw` (4.169), `exposure_index`,
`geopolitical_risk_index`, the three `years_from_*_to_net_zero`,
`internet_users`, `mobile_covered_population`, `smart_metered_population`, the
`*_attainment_*` indices, the sector demand split (`residential_demand_twh`
and the other three — they decompose `base_demand_twh`, and the constraint
`demand_shares_bound` gates the *shares*), and the insurance/coverage family
(`business_interruption_cover_usd_per_year` and its six siblings). Unread is
correct for these **as a class** — with the exceptions listed in §4.

**DEAD (25).** Three sub-classes:
- *Unused dial*: `ccs_capture_rate` is exogenous and moves nothing (§4, item 6);
  the three `*_effective_capacity_factor` and two `*_at_vintage` nodes are the
  same shape for resource dials (§4, item 4).
- *Superseded*: `demand_response_capacity`, `demand_response_potential`,
  `hydro_capacity_factor`, `plant_retirement_age`, `value_of_lost_load`,
  `carbon_budget`, `carbon_tax_coverage`, `carbon_price`,
  `electricity_subsidy_spend_usd_per_year`, `gdp_per_capita_growth`,
  `equity_share`, `investment_allowance`, `spare_capacity`, `social_tariff`,
  `lifeline_threshold`, `load_factor_override`, `asset_age_distribution`,
  `health_impact_dalys`, `health_impact_mortality` — each an alias onto a node
  that already does the job, or an identity onto a quantity the graph derives
  elsewhere.
- *Discretisation constant with no consumer*: `dispatch_intervals_per_hour`,
  `investment_period_length_years`, `tsam_segment_hours`,
  `circuit_breaker_density_per_km`, `gis_mapped_network_km`,
  `cross_border_losses_twh`, `desalination_demand` — a cadence or a conversion
  the LP would use, in a graph that does not run the LP.

**GENERATED REGISTER MEMBER (72).** The `compliance register`,
`extensive-base coupling`, `coupling's derived quantity` and `finance family`
templates. These are mechanically generated from `docs/research/coupling-packs/`
and land in a system with no reader by construction. They are not individually
defects, but the register as a whole is: 72 nodes that produce numbers no rule,
constraint or equation reads. Recommendation: either give each register a
consuming equation (a `total_*` aggregation, which the graph does not have —
see §5, item f) or stop generating them.

## 4. The shortlist — SHOULD BE CONSUMED, ranked by how misleading the absence is

Ranked by: does a reader of the output believe something the graph does not
compute?

### 1. `crf_solar_pv` and `crf_wind_onshore` — the LCOE uses the wrong annuity factor

**Missing edge:** `annualised_capex_solar_definition` reads `crf`, not
`crf_solar_pv`; `annualised_capex_wind_definition` reads `crf`, not
`crf_wind_onshore`.

```
annualised_capex_usd_per_kw_solar = capex_solar_pv * crf          # today
lcoe_wind_definition              = (annualised_capex_usd_per_kw_wind + ...)
```

`crf` is the fleet-generic factor over `asset_life` (25 y). `crf_solar_pv` is
the same formula over `asset_life_solar_pv`. Every other technology reads its
own: `lcoe_biomass` reads `crf_biomass`, `lcoe_coal` reads `crf_coal`,
`lcoe_wind_offshore` reads `crf_wind_offshore`. Only solar and onshore wind —
the two technologies where asset life most obviously differs from the fleet
average — read the generic one.

**Consequence, measured.** Set `asset_life_solar_pv = 40` (utility-scale solar,
a normal scenario):

| | base | scenario |
|---|---:|---:|
| `crf_solar_pv` | 0.114124 | 0.106635 |
| `annualised_capex_usd_per_kw_solar` | 125.537 | **125.537 (unchanged)** |
| `lcoe_solar_usd_per_mwh` | 70.309 | **70.309 (unchanged)** |

A scenario lengthening a solar asset's life changes the solar LCOE by exactly
zero, while the node named for that quantity moves. The reader sees a solar
LCOE that ignores the solar asset life and an onshore-wind LCOE that ignores
the onshore-wind asset life. These two feed `lcoe_value_cost_ratio_solar_pv`
and `..._wind_onshore`, which are two of the eleven conjuncts in
`no_technology_clears_its_cost` — so the error can flip that rule.

### 2. `reserve_margin_required_mw` — the requirement is computed from a different dial than the rule uses

**Missing edge:** `reserve_margin_required_mw = reserve_margin_requirement *
peak_demand_mw` reads `reserve_margin_requirement`; the rule
`reserve_margin_below_requirement` reads `reserve_margin_actual <
reserve_margin_min`. Two nodes, both defaulting to 0.15, neither reading the
other, and `reserve_margin_required_mw` read by nothing.

**Consequence, measured.** Raise `reserve_margin_min` from 0.15 to 0.35 (the
documented planning dial):

```
reserve_margin_min           0.15 -> 0.35
reserve_margin_required_mw   1275.0 -> 1275.0    (unchanged)
```

Raise `reserve_margin_requirement` instead: `reserve_margin_required_mw` goes
1275 → 2975, and the rule still gates on `reserve_margin_min` = 0.15. A reader
who raises the planning reserve margin sees no change in required capacity and
no rule fire. The graph holds two spellings of one number and they are
independent.

### 3. `total_jobs` — 137,600 against a component sum of 124,700

**Missing edge:** `total_jobs = direct_jobs * (1 + indirect_jobs_multiplier +
induced_jobs_multiplier)` uses `indirect_jobs_multiplier` (1.4), while
`indirect_jobs = direct_jobs * indirect_employment_multiplier` (1.2). Two
multipliers, different values, same concept.

**Consequence, measured at defaults:** `direct_jobs` 43,000 + `indirect_jobs`
51,600 + `induced_jobs` 30,100 = **124,700**; `total_jobs` = **137,600**, a
10.3% overstatement. `total_jobs`'s own description is "Direct, indirect and
induced employment. The number a build programme is argued on." A reader who
adds the three components and a reader who reads `total_jobs` get different
answers, and the total is not the sum.

Fix: `total_jobs_definition` should read `indirect_jobs + induced_jobs`, which
also gives `indirect_jobs` and `induced_jobs` a consumer.

### 4. `solar_effective_capacity_factor`, `wind_effective_capacity_factor`, `hydro_effective_capacity_factor`, `solar_pv_capacity_factor_at_vintage`, `wind_capacity_factor_at_vintage` — resource scenarios are inert

**Missing edge:** `coal_generation_twh` reads `capacity_factor_coal`; the
corresponding solar/wind/hydro generation equations should read the effective
(or at-vintage) factor, and read the base factor today.

Measured: `solar_irradiance_multiplier` 1.0 → 0.8 moves 2 values —
`solar_effective_capacity_factor` and itself. `solar_pv_generation_twh`,
`lcoe_solar_usd_per_mwh` and `fleet_generation_twh` do not move.
`wind_speed_multiplier` likewise. `hydro_drought_multiplier` moves **nothing at
all** (0 values). `solar_degradation` moves only `solar_pv_capacity_factor_at_vintage`.

A scenario stating a drought, a low-irradiance year or a degraded fleet
produces a graph whose generation, emissions and LCOE are identical to the base
year. This is the largest single class of misleading absence here: five
scenario dials, one of which (`hydro_drought_multiplier`) is fully inert.

### 5. `coal_eaf`, `gas_eaf`, `oil_eaf` — availability is computed and never applied

**Missing edge:** `{tech}_generation_twh` reads `capacity_factor_{tech}` and
not `{tech}_eaf`. Batch 46's restructure gave the fleet a generation identity
(`capacity * capacity_factor * hours_per_year / 1e6`); the EAF nodes were left
out of it.

Measured: `forced_outage_rate_coal` 0.1 → 0.3 moves `coal_eaf` 0.85 → 0.65 and
moves **nothing else** — `coal_generation_twh` stays 19.71 TWh,
`fleet_generation_twh` 68.07 TWh, `unserved_energy_gwh` 47.43 GWh,
`reliability_cost_usd` 237.15 M USD all unchanged.

The reader believes the fleet's deliverable energy accounts for forced outages.
It does not: availability enters only through whatever `capacity_factor_coal`
already nets out, and the graph does not say that it does.

**Caveat, and it matters.** `capacity_factor_coal` is exogenous with the
description "Annual net output over rated capacity … thermal carries the plant's
own duty". If the shipped 0.75 is already a net-of-outage figure, then
multiplying by EAF would double-count and the EAF nodes are correctly unread —
but then they should be deprecated, not left as three computed numbers that
look like they feed the fleet. Either reading indicts the current state.

### 6. `ccs_capture_rate` — exogenous, moves nothing

Not a derived node, so outside the 357, but found by the dial sweep and it
belongs with them. `ccs_capture_rate` (0.9) appears in
`fleet_emission_intensity_t_per_mwh`'s body, yet moving it 0.9 → 1.0 moves
zero values, while `coal_ccs_adoption` 0.0 → 1.0 moves 11. The reason is that
`coal_ccs_adoption` and `gas_ccs_adoption` are both 0 at defaults, so the term
multiplying the capture rate is zero — the classic "a term zero at defaults
needs a live canary" shape. Any scenario that leaves adoption at zero cannot
tell a correct capture rate from a wrong one.

### 7. `reserve_margin`, `planning_reserve_margin`, `spinning_reserve_requirement`, `non_spinning_reserve`, `regulation_reserve` — five alias-of-a-dial nodes in one system

Each aliases a free dial that is read directly (`reserve_margin_actual`,
`reserve_margin_min`, `spinning_reserve`, the up/down regulation requirements).
They exist only because the catalog carries two ids. Deprecate.

### 8. `precipitation_adjusted_flow_m3_per_s`, `transmission_loss_after_target`, `peak_demand_shifted_mw` — three dials whose only consumer is an unread node

Measured: `precipitation_multiplier` 0.5 → 0.0 moves exactly one value, its
own product; `transmission_loss_reduction_target` 0.1 → 1.0 moves only
`transmission_loss_after_target`; `peak_demand_multiplier` 0.5 → 0.0 moves only
`peak_demand_shifted_mw`. In each case a scenario dial exists, has a documented
range and default, and changes no quantity the graph reports. Either wire the
product into `total_water_demand_m3`, `transmission_loss_factor` and
`peak_demand_mw` respectively, or deprecate the dial.

### 9. `health_impact_dalys`, `health_impact_mortality` — the health chain's endpoints alias its own intermediates

`premature_deaths_per_year` → `dalys_per_year` → `health_cost_usd_per_year`
is live and terminates at a reported output. The two `health_impact_*` nodes
alias `dalys_per_year` and `premature_deaths_per_year` and are read by nothing.
Harmless duplicates, but they inflate the "5 nodes in health" count: the real
health chain is fully consumed up to its terminal. Classified DEAD in the table
and named here only because they were on the shortlist candidate list.

### Shortlist size

**24 nodes** qualify as SHOULD BE CONSUMED: `crf_solar_pv`,
`crf_wind_onshore`, `reserve_margin_required_mw`, `planning_reserve_margin`,
`reserve_margin`, `spinning_reserve_requirement`, `non_spinning_reserve`,
`regulation_reserve`, `total_jobs`, `indirect_jobs`, `induced_jobs`,
`solar_effective_capacity_factor`, `wind_effective_capacity_factor`,
`hydro_effective_capacity_factor`, `solar_pv_capacity_factor_at_vintage`,
`wind_capacity_factor_at_vintage`, `coal_eaf`, `gas_eaf`, `oil_eaf`,
`precipitation_adjusted_flow_m3_per_s`, `transmission_loss_after_target`,
`peak_demand_shifted_mw`, `health_impact_dalys`, `health_impact_mortality`.

Of these, 8 are one-line fixes in `config/prg.yaml` (items 1 and 7), 9 are
one-line equation-body changes (items 3, 4, 5), and the remainder need a
decision rather than an edit (items 2, 6, 8). Items 6 (`ccs_capture_rate`) and
9 are exogenous-or-dead rather than derived-and-unread; they are on the list
because the dial sweep found them and a reader would otherwise believe they
are applied.

## 5. What contradicts the framing

**a. 361 is 357.** The brief excludes the 28 rule-read nodes from the 389 and
treats the remainder as unread. But `affects()` excludes inequalities by
design, and 4 nodes are read by a constraint. A constrained node is consumed:
it can make a scenario inadmissible. The correct residue is 357.

**b. There is a second blind spot, and it is bigger.** `affects()` is one hop.
Closing it transitively gives **413**, not 357. The 56 extra nodes *are* read,
but only by nodes that are themselves unread — `regulatory_asset_base`,
`direct_jobs`, `unserved_energy_gwh`, `premature_deaths_per_year`,
`coal_fuel_energy_gj`, `ets_cap`, `renewable_generation_twh`,
`applied_tariff_usd_per_mwh` among them. Some of these are load-bearing: the
whole CO2/health chain terminates at `health_cost_usd_per_year` and
`emissions_mtco2_per_year`, so `premature_deaths_per_year` and
`dalys_per_year` are correctly classified as feeding a terminal output. Others
are not: `allowed_revenue_requirement` feeds 18 spend nodes, none read. So the
413 is not a better answer than the 357 either — it is a different question,
and the right response is to report all three numbers rather than pick one.

**c. "DERIVED FROM A DEAD BRANCH" is empty in the 357.** Zero unread→unread
edges, zero unread alias targets. The class the brief expects is real but lives
in the 56, not the 357.

**d. No node is "computed from inputs nobody supplies."** I checked all 357:
every one has a determining equation whose symbols resolve. The dead class
exists (31 nodes) but by supersession and duplication, not by missing inputs.

**e. `uncoupled()` and `affects()` are disjoint here — confirmed, zero
overlap.** The brief's warning that they answer different questions is not
just correct but understated: the sets are not merely different, they are
complementary. The 234 uncoupled are free nodes no equation names; the 528
derived are all named by their own definition.

**f. The graph has no cost aggregator at all.** No node sums the spend, tax,
subsidy or compliance families. `allowed_revenue_requirement` feeds 18 spend
nodes and nothing sums them; `total_revenue_usd_per_year` has 11 readers, all
of which are themselves unread. This is why the generated registers read as
"should be consumed" in bulk — there is no `total_system_cost` for them to feed.
Whether that is a gap or a design choice (the LP does the accounting) is the
single question that decides the fate of ~72 generated nodes. It is not
answerable from the graph alone.

## 6. Reproduction

```bash
.venv/bin/python - <<'EOF'
from alea.prg.graph import load_graph
g = load_graph()
d = set(g.computed())
no_aff = [n for n in sorted(d) if g.affects(n) == ()]                    # 389
resid  = [n for n in no_aff if not g.rules_reading(n)
                            and not g.constrains(n)]                     # 357
live = {n for n in g.nodes if g.rules_reading(n) or g.constrains(n)}
ch = True
while ch:
    ch = False
    for n in d - live:
        if any(a in live for a in g.affects(n)): live.add(n); ch = True
print(len(no_aff), len(resid), len(d - live))                            # 389 357 413
EOF
```

The behavioural probes in §4 re-propagate from a full default scenario
(`node.initial or node.default` for all 1426 nodes) with one dial moved to a
range-valid value, and diff the resulting `values` dict.
