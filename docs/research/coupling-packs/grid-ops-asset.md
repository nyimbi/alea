# Coupling pack — grid operations, asset management, digital systems and regulatory accounts

The 33 nodes assigned to this pack. Verified against the tree as it stands:
`load_graph()` returns **1352 parameters, 552 equations, 1136 edges and 240
uncoupled**. All 33 are present in the graph, all 33 are in `uncoupled()`, and
**none of the 33 is read by any equation** — as an lhs or as an rhs operand.
Measured directly: `nodes read by >=1 equation: 0`, `nodes that are an lhs: 0`.

> **Re-verified 2026-10-24, at batch 58.** The counts above were read at 1352 /
> 552 / 1136 / 240; the graph is now **1429 / 607 / 1367 / 57, 235 uncoupled**,
> and every figure below citing the old ones is a record of the tree this pack
> was written against. The verdicts were re-checked and hold: all 41 slice ids
> this document names are still in `uncoupled()` and **none is read by any
> equation**. One correction: the sentence "other 26 are catalog placeholders
> carrying `unit=None, range=(0.0, 1000000.0), default=500000.0`" no longer
> describes the slice. Measured at this tree, the 41 break down as **4 still on
> the sentinel, 13 with a declared range and `unit=None`, 12 categoricals, and
> 12 carrying a real unit** — the survey's retypes landed between this pack and
> now. The pack's conclusion is unaffected, but its sentinel count is stale.

| | count |
|---|---|
| nodes in slice | 33 |
| get a proposal (equation or read) | **0** |
| — become an lhs of an equality (`derive`) | 0 |
| — become an lhs of an inequality (`bound`) | 0 |
| — become an rhs operand (`read`) | 0 |
| equations proposed | **0** |
| new nodes required | 0 |
| retyped nodes | 0 |
| deferred | **33** |
| class breakdown | SCENE-SWITCH 8 · QUALITATIVE 23 · BASE-NEEDED 2 · PRODUCT 0 · THRESHOLD 0 · DEPRECATED 0 |

`uncoupled()` stays at **240**. This pack closes nothing, and the finding is that
nothing in the slice *should* be closed by an equation. Six nodes are booleans,
one is a categorical, and the other 26 are catalog placeholders carrying
`unit=None, range=(0.0, 1000000.0), default=500000.0` — the signature this graph
uses for a name that was never given a quantity. The slice is not an
under-determined set of numbers; it is a list of *modes, systems, procedures,
logs and schedules* that the scalar graph cannot hold, plus three quantities
whose bases are genuinely absent.

---

## What the verification found, before the rows

**1. All 33 already carry a row in a sibling pack, and this pack re-verified
rather than re-derived.** `digital-sector.md` holds rows for 18 of the 33,
`operational-supply.md` for 13, `contract-market.md` for 2 — union 33, none
missing. That is a collision of assignment, not of conclusion, and the useful
work here was to check whether the sibling verdicts survive on the post-batch-36-39
graph. They do, with one correction (finding 6) and one sharpening (finding 5).

**2. Nothing in the slice can enter arithmetic as it stands.** 26 nodes are
`unit=None` placeholders, 6 are `bool`, 1 is `categorical`. A `bool` is
arithmetically admissible (`1.0`), which is why the gate idiom works at all — but
a `categorical` is not: measured, `check_equation` returns
`decidable=False, consistent=False` with detail *"the rhs has a dimension this
walker cannot compute"*, and `propagate` raises
`TypeError: can't multiply sequence by non-int of type 'float'`. A placeholder
enters arithmetic with a value of 500,000 and silently sets the scale of whatever
it multiplies.

**3. Every boolean-gated equation the graph already ships produces a node nothing
reads.** Eight of them, and all eight have a zero-reader lhs:

```
capacity_revenue_usd_per_year_definition     capacity_revenue_usd_per_year          readers=0
cbam_price_applied_definition                cbam_price_applied                     readers=0
contingency_reserve_mw_definition            contingency_reserve_mw                 readers=0
coordinated_maintenance_definition           coordinated_maintenance_hours_per_year readers=0
offtake_risk_premium_applied_definition      offtake_risk_premium_applied           readers=0
permitted_imports_definition                 permitted_imports_twh                  readers=0
permitted_transmission_spend_definition      permitted_transmission_spend_usd       readers=0
smart_metered_population_definition          smart_metered_population               readers=0
```

This is the decisive measurement for the pack. The gate idiom
`gated_quantity = switch * quantity` is *mechanically* available — I built five
of them and they pass `check_equation` and propagate cleanly — but in this graph
its output is terminal by construction. Shipping more of them would raise the
derived-node count and the equation count while leaving every new node unread,
which is the graph's existing defect (finding 4) reproduced at scale. Closing
`uncoupled()` is not the objective; a graph where a computed quantity is consumed
is.

**4. 383 of 481 derived nodes have zero readers.** Measured excluding each node's
own defining equation. The graph's derived population is four-fifths terminal.

**5. The gate has no coefficient, so a gate on these switches would assert 100% of
the benefit.** `dg_placement_enabled * transmission_loss_fraction * generation_twh`
computes 4.124 TWh/year and unit-checks clean — but it states that enabling DG
placement recovers *the entire* transmission loss fraction. The real quantity is a
reduction per unit of DG placed, and no such node exists
(`distributed_generation_capacity` is absent). The same holds for phase shifting,
topology switching and voltage optimisation, which is why their measured values
(0.0, 4.124, 4.124 TWh/year) are the same number scaled by a switch: the equation
carries no engineering content beyond the switch.

**6. `coal_retirement_schedule` cannot be represented even as a scalar, because
the catalog means an absolute calendar year and the graph has no such convention.**
The catalog uses it as `2050` and `2035` (and a cross-validation rule
`coal_retirement_schedule > 2045`). All **51** nodes with `unit='years'` are
horizon offsets: the most common range is `(0.0, 100.0)`, and **no node range in
the graph admits 2045**. Retyping this node to `years` therefore either states a
different quantity than the catalog's (years-from-now) or ships a value its own
range rejects. `operational-supply.md` deferred it as "a retirement *year* per
unit; no unit-level vintage register" — correct, and the absolute-year problem is
a second, independent reason.

**7. A `bound` cannot repair a placeholder either.** A bound leaves the node
`free`, so the node still needs a `default` — and the placeholder's default of
500,000 is not a value any of these quantities can take. I built three bounds with
defensible retypes and defaults; all three unit-check and all three are
**satisfied at their own defaults**, so they assert nothing:

```
regulatory_accounts[USD million] >= 0, default 4800      dec=True cons=False unc=239 value=4800.0
microgrid_deployment[MW] <= mini_grid, default 0         dec=True cons=False unc=239 value=0.0
maintenance_schedule[h/yr] >= planned, default 96        dec=True cons=True  unc=239 value=96.0
```

`microgrid_deployment`'s bound is vacuous against a shipped
`mini_grid_deployment = 100000.0`, and `maintenance_schedule`'s is an equality
against a shipped `planned_maintenance_hours_per_year = 96.0` that has been
retuned to sit on the boundary. A bound a node satisfies before anyone measures
anything is a row in a register, not a coupling.

**8. The catalog names seven operands these nodes would need, and the graph has
none of them.** Absent, checked by id: `dg_placement_benefit`,
`phase_shifting_benefit`, `topology_switching_benefit`,
`voltage_optimisation_benefit`, `storage_dispatch_benefit`,
`distributed_generation_capacity`, `revenue_collection`. Also absent:
`reserve_account_share`, which an earlier pack considered for
`regulatory_accounts`.

---

## Rows

Every row is `kind: defer`. The `equation` column is `--` throughout because no
equation ships; the `prose` column carries the reason for the deferral, which is
the deliverable for a deferred row. `citation` is `--` for the same reason — a
node with no equation carries no `reference`, and the citation rule binds
equations, not nodes. `role`/`det` are the *shipped* values, unchanged: this pack
retypes nothing.

| node | class | kind | unit | range | role / det | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `dg_placement_enabled` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | On/off switch for distributed-generation siting. A mode selector: its correct coupling is none. The gate `dg_placement_enabled * transmission_loss_fraction * generation_twh` was built and measures `decidable=True, consistent=True`, 4.124 TWh/year — rejected because it asserts that siting DG recovers the whole transmission loss fraction, and the coefficient that would make it a reduction (loss removed per MW placed) is `distributed_generation_capacity`, which the graph does not hold. | -- | `dg_placement_benefit_twh = dg_placement_enabled * transmission_loss_fraction * generation_twh` — dec/cons clean, 4.124 TWh/year, lhs would be a zero-reader node. |
| `phase_shifting_enabled` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | Phase-balancing on/off. Default 0.0. Same gate argument as above; the built probe computes 0.0 TWh/year at the shipped default, i.e. a node that is identically zero until a user flips a switch. | -- | `phase_shifting_benefit_twh = phase_shifting_enabled * transmission_loss_fraction * generation_twh` — dec/cons clean, value 0.0, zero-reader lhs. |
| `topology_switching_enabled` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | Network reconfiguration on/off. The reconfiguration saving is a function of network topology, which the graph holds as no spatial node (measured: 0 spatial nodes in 1352). | -- | `topology_switching_benefit_twh = topology_switching_enabled * transmission_loss_fraction * generation_twh` — dec/cons clean, 4.124 TWh/year, no coefficient, zero-reader lhs. |
| `voltage_optimisation_enabled` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | Voltage set-point optimisation on/off. A voltage-dependent loss curve is the base it needs; the graph carries none. | -- | `reactive_capability_mvar = voltage_optimisation_enabled * reactive_power_requirement * peak_demand_mw` — dec/cons clean in isolation, but **refused at load**: `GraphError: reactive_capability_mvar is determined by both 'reactive_capability_definition' and 'probe'`. The node is already derived; the gate would be an over-determination, not a coupling. |
| `storage_dispatch_enabled` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | Storage dispatch on/off. The gate `storage_dispatch_enabled * storage_energy_capacity_mwh` measures `decidable=True, consistent=True`, 4800 MWh, and reduces `uncoupled()` 240→239. Rejected on two grounds: `storage_energy_capacity_mwh` already has zero readers, so the gate would gate an unread quantity; and the equation states that enabling dispatch makes the *entire* installed energy capacity dispatchable, with no availability or depth-of-discharge term. | -- | `dispatchable_storage_energy_mwh = storage_dispatch_enabled * storage_energy_capacity_mwh` — the cleanest gate in the slice, and still a zero-reader output. |
| `life_extension_possible` | SCENE-SWITCH | defer | `1` (bool) | none | free / policy | -- | Whether the optimiser may extend an ageing plant's life. The gate `life_extension_possible * life_extension_cost * total_capacity_mw * 1000` measures `decidable=True, consistent=True` and computes 0.0 at the shipped default (switch off), 6.0e9 USD with the switch on. Rejected because it extends the *entire* fleet whenever the switch is on, and because the fraction family it belongs to already ships unread: `life_extension_fraction_of_new_build = life_extension_cost / capex_usd_per_kw` = 0.5, zero readers. A third spelling of a dead quantity is what `operational-supply.md` rejected `maintenance_schedule` for. | -- | `life_extension_capex_usd = life_extension_possible * life_extension_cost * total_capacity_mw * 1000` — dec/cons clean, 240→239, but zero at defaults and zero-reader. |
| `maintenance_schedule_optimisation` | SCENE-SWITCH | defer | `1` | `[0,1]` | free / fixed | -- | "Optimise maintenance timing" — a switch, shipped as `float` with `unit=None` and `default=500000.0`. Read as an operand it fails immediately: `GraphError: maintenance_schedule_optimisation=500000.0 is outside the range`. A switch typed as an untyped float cannot gate anything until it is retyped to `bool`/`1`, and retyping is a batch action this pack does not take. | -- | `optimised_maintenance_hours_per_year = maintenance_schedule_optimisation * planned_maintenance_hours_per_year` — propagates to 48,000,000 h/year, a value 5,479x the node's own range ceiling of 8760. The placeholder default is what breaks it. |
| `regulatory_asset_valuation_method` | SCENE-SWITCH | defer | none (categorical) | none | free / policy | -- | How the RAB is valued: `('historical_cost', 'indexed_historical', 'current_cost')`, default `historical_cost`. A mode selector over the RAB's valuation convention. It cannot enter arithmetic: measured, `check_equation` on `regulatory_asset_valuation_method * regulatory_asset_base` returns `decidable=False, consistent=False`, and `propagate` raises `TypeError: can't multiply sequence by non-int of type 'float'`. Gating the RAB on it is also refused at load — `regulatory_asset_base` is already determined by `regulatory_asset_base_definition`. The three levels are three *equations*, not three values, and choosing among equations is what a batch does, not what the DSL does. | -- | `regulatory_asset_base = regulatory_asset_valuation_method * regulatory_asset_base` — **refused**: `GraphError: regulatory_asset_base is determined by both 'regulatory_asset_base_definition' and 'probe'`. Also refused for self-reference on the right, which the affine `solve_for` path forbids. |
| `condition_based_maintenance` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A maintenance *regime* selector (CBM). Not the same object as `predictive_maintenance_adoption` (0.5, exogenous), which is the share actually adopted: CBM is one input to that adoption. Aliasing would collapse a regime into a share. | -- | `condition_based_maintenance = predictive_maintenance_adoption` — retyped to `1`, `dec/cons` clean, computes 0.5. Rejected: different objects, and no archived source states the identity. |
| `reliability_centred_maintenance` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A regime selector (RCM). No quantity in the graph is the RCM regime; the reliability *outcomes* it targets are separately derived (`system_saidi_hours_per_year`, `system_saifi_events_per_year`). | -- | Alias onto any reliability outcome — rejected: a regime is not its result. |
| `risk_based_maintenance` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A regime selector (RBM). Same argument as CBM and RCM: a procedure's name, not a measurable share. | -- | Alias onto `predictive_maintenance_adoption` or a maintenance-hours node — rejected for the same reason. |
| `iso_55000_compliance` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A compliance flag against ISO 55000. A standard's name. Even retyped to a binary, a compliance flag has no quantity to scale and no archived source in this repo for the standard's content. | -- | Retype to `1` and gate a spend node — rejected: no spend node is attributable to ISO compliance, and the work is not archived. |
| `asset_management_maturity` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A maturity level on an asset-management scale. The scale itself is the missing base: there is no archived source defining the levels, so no range can be defended and no equation can consume the level. | -- | Retype to a `[1,5]` level and gate maintenance spend — rejected: the scale is not sourced and the gated quantity would be invented. |
| `asset_management_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An EAM system: a system description, not a measurement. The graph's quantitative counterparts for asset management are the maintenance-hours family, which already ships (`planned_maintenance_hours_per_year`, `predictive_maintenance_hours_per_year`, `coordinated_maintenance_hours_per_year`, `crew_shortfall_hours_per_year`, `spare_parts_deferred_hours_per_year`) — all five with zero readers. | -- | Gate a maintenance saving on EAM presence — rejected: the gated quantity would be invented, and the existing family is unread. |
| `maintenance_history` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An event log over time, not a scalar. The scalar summary of a maintenance history is `maintenance_frequency` (already consumed by `planned_maintenance_hours_per_year_definition` and `workshop_capacity_workload_bound`). | -- | `maintenance_history = predictive_maintenance_adoption` — retyped to `1`, `dec/cons` clean, computes 0.5. Rejected: an adoption share is not a history. |
| `maintenance_schedule` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A table of periods in which specified plant is unavailable — a schedule, not an annual total. The annual total it is not is `planned_maintenance_hours_per_year` (96.0, derived). ENTSO-E, which this graph already cites for adequacy, describes maintenance as explicit unavailability periods; a table cannot be an lhs. | -- | `maintenance_schedule = planned_maintenance_hours_per_year` — retyped `hours/year`, `dec/cons` clean, 96.0. Rejected: a schedule is a table. Also `planned_maintenance_hours_per_year * (1 - predictive_maintenance_adoption)` — `dec/cons` clean, 48.0, rejected as a third spelling of the shipped `coordinated_maintenance_hours_per_year` and `predictive_maintenance_hours_per_year`. |
| `failure_history` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An event log, not a scalar. Its scalar summary is `forced_outage_rate`, already derived by `availability_definition` from MTTR and MTBF and read by `oil_eaf_definition`. | -- | `failure_history = forced_outage_rate` — retyped `1/year`, `decidable=True` but **`consistent=False`** (the two sides do not share a dimension), and rejected anyway as an event log aliased to a rate. |
| `degradation_model` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A model *selector* (linear, exponential, …), not a rate. The rates it selects among already ship and are already consumed: `solar_degradation` (0.005/year) feeds `solar_pv_capacity_factor_at_vintage_definition`; `wind_degradation` (0.003/year) feeds `wind_capacity_factor_at_vintage_definition`. The model choice is expressed by which equation a batch ships, not by a scalar. | -- | `degradation_model = solar_degradation` — retyped `1/year`, `dec/cons` clean, 0.005. Rejected: a selector is not a rate, and aliasing would lose the wind case. |
| `microgrid_deployment` | BASE-NEEDED | defer | none | `[0,1e6]` placeholder | free / fixed | -- | Needs an installed microgrid capacity (MW) or a site count. Neither exists. `mini_grid_deployment` is a *different programme* with its own spend equation; `islanding_capability` is present and consumed by `islanding_capable_feeders`, but the microgrid base is not. | -- | `microgrid_deployment <= mini_grid_deployment` — retyped `MW`, `decidable=True`, and vacuous (0.0 ≤ 100000.0 before anyone measures). Rejected: a bound that never bites. |
| `outage_management_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An OMS: a system description. The reliability quantities an OMS produces are separately derived and consumed: `system_saidi_hours_per_year` (by `saidi_definition`), `system_saifi_events_per_year` (by `saifi_definition`), `outage_events_from_cause`. | -- | Gate a reliability improvement on OMS presence — rejected: no coefficient exists, and the reliability family is already built. |
| `work_management_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | A WMS: a system description. Its quantitative shadow is `crew_shortfall_hours_per_year` and `spare_parts_deferred_hours_per_year`, both shipped and both zero-reader. | -- | Gate crew productivity on WMS presence — rejected: the productivity coefficient is absent. |
| `ami_infrastructure` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | AMI: a metering platform, a system description. The quantitative counterpart already ships and is already derived: `smart_metered_population = smart_metering_rollout * smart_metering_penetration * electrified_population`. | -- | `ami_reached_population = ami_infrastructure * smart_metered_population` — `decidable=False, consistent=False`, propagates to 1.0125e13 people. Rejected: an untyped platform name multiplying a shipped population produces an absurdity, and the quantity it would add is the one already shipped. |
| `billing_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | The billing platform's capability: a procedure. No node in the graph measures billing performance, so there is nothing for it to scale. | -- | Gate a collection rate on billing presence — rejected: `revenue_collection` is absent from the graph. |
| `customer_information_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | CIS capability: a system description. The customer-facing spend nodes that exist (`complaint_handling_spend_usd_per_year`, `consumer_education_spend_usd_per_year`) are derived from their own drivers and would not take CIS as an operand without a coefficient. | -- | Gate complaint volume on CIS presence — rejected: no coefficient, and the complaint family is derived elsewhere. |
| `communication_protocols` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | The protocol stack (IEC 61850, DNP3, …): a standard's name. No base to multiply. | -- | Retype to a count of protocols — rejected: a count of standards is not a quantity any shipped equation consumes. |
| `cyber_incident_response` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An incident-response procedure (detect, contain, recover). Two quantitative siblings exist and are coupled: `cybersecurity_requirements` → `cybersecurity_spend_usd_per_year`, and `cyber_insurance` → `cyber_cover_usd_per_year`. A third, `cyber_threat_level`, is itself an untyped placeholder with zero readers — so the cyber family is half built, which is a finding, not a base. | -- | Gate cyber spend on response capability — rejected: the capability would have to be invented, and the family it would join is itself unread. |
| `data_backup_recovery` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | An RPO/RTO policy: a procedure. The graph holds no data-loss quantity for it to bound. | -- | Retype to an RTO in hours and bound downtime — rejected: the downtime quantity it would bound does not exist. |
| `der_management_systems` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | DERMS: a system description. The base it would manage — distributed-generation capacity — is absent from the graph, which is the same missing base that blocks `dg_placement_enabled`. | -- | Gate a DER hosting-capacity figure on DERMS presence — rejected: `distributed_generation_capacity` is absent. |
| `regulatory_accounts` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / policy | -- | The chart of regulatory accounts: a register's *structure*, not a balance. The RAB and its components are separately derived and consumed (`regulatory_asset_base` = 4800.0, read by four equations; `regulatory_depreciation` = 192.0, read by two). The account structure is what a reporting batch reads out of the graph; it is not a node the graph computes. | -- | `regulatory_accounts = regulatory_asset_base` — retyped `USD million`, `dec/cons` clean, 4800.0. Rejected: an account register is not the balance in one of its accounts. Also `reserve_account_share * regulatory_asset_base` — **symbol check fails**: `reserve_account_share` is not a declared node. |
| `coal_retirement_schedule` | BASE-NEEDED | defer | none | `[0,1e6]` placeholder | free / fixed | -- | The catalog's own meaning is an absolute calendar year (`2050`, `2035`), and the graph has no such convention: all 51 `unit='years'` nodes are horizon offsets, the commonest range is `(0.0, 100.0)`, and **no range in the graph admits 2045**. The fleet-level retirement quantities already ship: `coal_retirement_rate` (0.03/year) and `coal_retirement_half_life_years` (= log 2 / rate = 23.1049, zero readers). What is missing is a per-unit vintage register, and a register is not a scalar. | -- | `coal_retirement_schedule = coal_retirement_half_life_years` — retyped `years`, `dec/cons` clean, 23.1049. Rejected: a schedule aliased to a half-life. `= log(2.0) / coal_retirement_rate` — `dec/cons` clean, same value, and a verbatim duplicate of the shipped `coal_retirement_half_life_definition`, which would make two nodes one quantity. |
| `demand_growth_profile` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | The *shape* of a growth curve (linear, S-curve, logistic) — a curve family. The rate is `demand_growth` (0.0325/year, exogenous) and it is already consumed. No equation can select among functional forms; a batch selects by shipping the form it wants. | -- | `demand_growth_profile = demand_growth` — retyped `1/year`, `dec/cons` clean, 0.0325. Rejected: a curve family is not its rate. |
| `electrification_timeline` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / policy | -- | "Year to reach target" — a scenario schedule. The target it reaches is a separate node (`electrification_rate_target` = 0.9, zero readers); the year is not a quantity the graph computes. | -- | `electrification_timeline = electrification_rate_target` — retyped `1`, `dec/cons` clean, 0.9. Rejected: a year aliased to a share. |
| `ev_adoption_timeline` | QUALITATIVE | defer | none | `[0,1e6]` placeholder | free / fixed | -- | "Year to reach EV share" — the same schedule argument. The share is `ev_share_new_sales` (0.2, zero readers); the year it is reached by is a scenario input. | -- | `ev_adoption_timeline = ev_share_new_sales` — retyped `1`, `dec/cons` clean, 0.2, and the only probe in the slice that closes **two** nodes (`unc=238`). Rejected anyway: a year aliased to a share, and the extra closure is an artefact of two uncoupled nodes being set equal. |

---

## New nodes this pack declares

**None.**

Five candidate new lhs nodes were built and measured, and all five were rejected
for one reason: in this graph a boolean-gated node is terminal. Each of the five
measured `decidable=True, consistent=True` and propagated cleanly, and each would
have added a node with no reader to a graph where 383 of 481 derived nodes already
have none.

| candidate | equation | measured | why rejected |
|---|---|---|---|
| `dg_placement_benefit_twh` | `dg_placement_enabled * transmission_loss_fraction * generation_twh` | dec/cons clean, 4.124 TWh/year | No coefficient: asserts 100% of the loss fraction. `distributed_generation_capacity` absent. |
| `phase_shifting_benefit_twh` | `phase_shifting_enabled * transmission_loss_fraction * generation_twh` | dec/cons clean, 0.0 TWh/year | Identically zero at the shipped default; no coefficient. |
| `topology_switching_benefit_twh` | `topology_switching_enabled * transmission_loss_fraction * generation_twh` | dec/cons clean, 4.124 TWh/year | The reconfiguration saving is topological; the graph holds 0 spatial nodes. |
| `voltage_optimisation_benefit_twh` | `voltage_optimisation_enabled * transmission_loss_fraction * generation_twh` | dec/cons clean, 4.124 TWh/year | A voltage-dependent loss curve is absent; the four benefits are one number scaled by four switches. |
| `dispatchable_storage_energy_mwh` | `storage_dispatch_enabled * storage_energy_capacity_mwh` | dec/cons clean, 4800 MWh | `storage_energy_capacity_mwh` already has zero readers; the gate gates an unread quantity. |

Also built and rejected as new lhs nodes:
`life_extension_capex_usd` (dec/cons clean, 0.0 at defaults, 6.0e9 with the switch
on — the whole-fleet assumption and the already-shipped
`life_extension_fraction_of_new_build` with zero readers),
`optimised_maintenance_hours_per_year` (propagates to 48,000,000 h/year, 5,479x
its range, because the switch is an untyped float at 500,000), and
`ami_reached_population` (`decidable=False`, 1.0125e13 people).

---

## Verification

All figures below are printed output from `load_graph()` on the tree as it stands,
with the probe equations built in memory through `ParameterGraph(...)`. No file
was modified.

### Graph state and slice membership

```
graph: 1352 nodes 552 eqs 1136 edges uncoupled 240
nodes read by >=1 equation: 0
nodes that are an lhs: 0
in slice uncoupled: 33 of 33
placeholder signature (unit=None, (0.0,1e6), 500000.0): 26
type counts: {'bool': 6, 'float': 26, 'categorical': 1, 'timeseries': 0, 'spatial': 0}
graph-wide timeseries: 0   spatial: 0   unit=None: 196   categorical: 8
derived: 481, of which zero-reader (excl. own definition): 383
slice nodes out of declared range at own default: []
```

### Symbol check, over every rhs this pack considered

The brief's script, run over all 19 proposed right-hand sides:

```
19 rhs checked, 1 with unresolved symbols
  MISSING regulatory_accounts  ['reserve_account_share']
```

### `check_equation(equation, graph)` — equation first, graph second

Retyped to a defensible unit and `role=derived` (what a batch would do). `dec` =
`decidable`, `cons` = `consistent`.

```
=== lhs kept as its shipped placeholder (unit=None) ===
coal_sched = coal_half_life              dec=False cons=False unc=239 value=23.104906018664845
coal_sched = log(2)/coal_rate            dec=False cons=False unc=239 value=23.104906018664845
degradation_model = solar_degradation    dec=False cons=False unc=239 value=0.005
failure_history = forced_outage_rate     dec=False cons=False unc=239 value=0.0004797697105389413
maintenance_history = pred_adoption      dec=False cons=False unc=239 value=0.5
maintenance_schedule = planned_hours     dec=False cons=False unc=239 value=96.0
demand_growth_profile = demand_growth    dec=False cons=False unc=239 value=0.0325
ev_adoption_timeline = ev_share          dec=False cons=False unc=238 value=0.2
electrification_timeline = rate_target   dec=False cons=False unc=239 value=0.9
regulatory_accounts = RAB                dec=False cons=False unc=239 value=4800.0

=== same, retyped to a defensible unit ===
coal_sched[years] = coal_half_life       dec=True  cons=True  unc=239 value=23.104906018664845
coal_sched[years] = log(2)/rate          dec=True  cons=True  unc=239 value=23.104906018664845
degradation_model[1/year] = solar        dec=True  cons=True  unc=239 value=0.005
failure_history[1/year] = forced         dec=True  cons=False unc=239 value=0.0004797697105389413
maint_history[1] = pred_adoption         dec=True  cons=True  unc=239 value=0.5
maint_sched[h/yr] = planned              dec=True  cons=True  unc=239 value=96.0
maint_sched[h/yr] = planned*(1-pred)     dec=True  cons=True  unc=239 value=48.0
profile[1/year] = demand_growth          dec=True  cons=True  unc=239 value=0.0325
ev_tl[1] = ev_share                      dec=True  cons=True  unc=238 value=0.2
elec_tl[1] = rate_target                 dec=True  cons=True  unc=239 value=0.9
reg_accts[USD m] = RAB                   dec=True  cons=True  unc=239 value=4800.0
```

Note the pattern: **every one of these is `decidable=False` on the shipped
placeholder and `decidable=True` only after a retype.** `decidable=False` on a
placeholder is not a defect in the equation; it is the placeholder saying it has
no unit.

### Gate candidates, and the over-determination refusals

```
life_extension_capex_usd                      dec=True  cons=True  unc=239 value=0.0
  same, switch ON                             dec=True  cons=True  unc=239 value=6000000000.0
dispatchable_storage_energy_mwh               dec=True  cons=True  unc=239 value=4800.0
reactive_capability_mvar (overdet)            LOAD-REFUSED GraphError: reactive_capability_mvar is
                                              determined by both 'reactive_capability_definition' and 'probe'
optimised_maint_hours                         dec=True  cons=True  unc=239
                                              value=GraphError: maintenance_schedule_optimisation=500000.0
                                              is outside the range
ami_reached_population                        dec=False cons=False unc=239 value=10125000000000.0
RAB = method * RAB                            LOAD-REFUSED GraphError: regulatory_asset_base is
                                              determined by both 'regulatory_asset_base_definition' and 'probe'
```

### The categorical cannot enter arithmetic

```
check_equation: EquationCheck(equation_id='c', decidable=False, consistent=False, lhs='', rhs='',
  detail='the rhs has a dimension this walker cannot compute')
propagate raises TypeError: can't multiply sequence by non-int of type 'float'
```

All 8 categorical nodes in the graph have zero readers and none is an lhs:
`auction_mechanism`, `market_model`, `market_structure`, `pricing_mechanism`,
`re_target_carrier`, `regulatory_asset_valuation_method`, `tariff_structure`,
`unbundling_status`.

### `propagate` at defaults

Fill: `{n.id: n.default for n in g.nodes.values() if n.default is not None}` —
**871 of 1352 nodes filled**, the same fill the sibling packs use. Clean: no
excursion, no blocking conflict, no undecidable unit; 1352 values returned.

```
demand_growth_start_year         = 25.0
demand_growth_end_year           = 25.0
demand_growth_window_years       = 0.0
demand_growth_factor             = 1.0
demand_growth                    = 0.0325
horizon_years                    = 10.0
demand_twh                       = 46.53902747054532
plant_retirement_age             = 25.0
remaining_useful_life            = 17.5
asset_age_distribution           = 7.5
coal_retirement_half_life_years  = 23.104906018664845
coal_retirement_rate             = 0.03
regulatory_asset_base            = 4800.0
regulatory_depreciation          = 192.0
solar_degradation                = 0.005
wind_degradation                 = 0.003
forced_outage_rate               = 0.0004797697105389413
```

A `1.0` fill for *derived* nodes raises `FeedbackError` on
`loop_1_capture_price_usd_per_mwh_vre_capacity_mw` (residual 13 at 0.0, 5013 at
5000.0). The fill above is the one that works; a batch that seeds derived nodes
poisons the feedback loop and reads the failure as a graph defect.

### Constraints this pack respected

- **No `abs`, `min`, `max`, `floor`, `ceil`** anywhere in any proposed rhs. Every
  candidate is a product or quotient of declared nodes.
- **No derived node carries a default.** This pack ships no derived node, so the
  constraint is vacuous here; the retypes used in probes set `default=None`.
- **Every lhs appears only on the left.** The one candidate that violated it
  (`regulatory_asset_base = regulatory_asset_valuation_method * regulatory_asset_base`)
  is recorded as refused on exactly that ground.
- **No `deprecated_by` target.** Measured: none of the 33 has `deprecated_by` set,
  so the constraint is not what blocks anything here.

---

## Sources to fetch

This pack ships no equation, so **no citation is owed and none is given**. The
`reference: None` allowance does not arise: it is admissible only for a
definitional identity, and there are no identities here.

If a later batch decides to retype and couple any of these, the following works
are the ones that would have to back the arithmetic. Four are already archived and
were checked on disk; four are not.

**Already archived — usable today:**

| work | archive file | would back |
|---|---|---|
| ENTSO-E MAF 2019, Appendix 2 — Methodology | `sources/archive/entsoe_maf_2019_methodology.pdf` | `maintenance_schedule` as explicit unavailability periods; `outage_management_systems` against adequacy practice |
| IEEE Guide for Electric Power Distribution Reliability Indices (1366) | `sources/archive/ieee_1366_reliability_tutorial.pdf` | `failure_history`, `degradation_model` against the reliability indices the graph already derives |
| Brown, Stern & Tenenbaum, *Handbook for Evaluating Infrastructure Regulatory Systems* | `sources/archive/world_bank_regulating_utilities_handbook.pdf` | `regulatory_accounts` as a reporting structure; `regulatory_asset_valuation_method` as a regulatory convention |
| UKRN, *Guidance for regulators on the methodology for setting the cost of capital* (2023) | `sources/archive/ukrn_cost_of_capital_2023.pdf` | the RAB and depreciation family that `regulatory_accounts` and the valuation method sit beside |

**Not archived — must be fetched and archived before an equation ships:**

| work | would back | why it is needed |
|---|---|---|
| ISO 55000:2014, *Asset management — Overview, principles and terminology* | `iso_55000_compliance`, `asset_management_maturity`, `asset_management_systems` | The maturity scale and the compliance definition are the missing base for all three. Without the standard archived, no range can be defended. |
| Ofgem RIIO-2 / Ofwat PR24 methodology chapters on RAB indexation | `regulatory_asset_valuation_method` | The three levels (`historical_cost`, `indexed_historical`, `current_cost`) are three distinct valuation equations. The graph cites Ofwat PR24 for the RAB definition but not for the valuation convention. |
| IEA, *Global EV Outlook* (current edition) | `ev_adoption_timeline`, `electrification_timeline`, `demand_growth_profile` | The schedules are scenario curves. Only a published scenario set would let a year be a quantity rather than a guess. |
| Global Energy Monitor, *Global Coal Plant Tracker* | `coal_retirement_schedule` | The per-unit vintage register and announced retirement years. This is the base the node needs, and it is a dataset, not a paper. |

**A note on what an archived source would not fix.** Three of the 33 are blocked
by a missing *coefficient*, not a missing citation: the four loss-mitigation
switches need a loss-reduction-per-MW term, and `der_management_systems` needs a
distributed-generation capacity. No citation supplies a coefficient that is not in
the graph; those are new nodes, and a new node needs its own source.

---

## Findings a later batch must fix

**F1. The demand-growth factor family is dead arithmetic.**
`demand_growth_start_year` and `demand_growth_end_year` both default to **25.0**,
so `demand_growth_window_years = end - start` = **0.0** and
`demand_growth_factor = (1 + demand_growth) ** window` = **1.0** for every
scenario at defaults. `demand_growth_factor` then has **zero readers**, and the
consuming equation `energy_demand` does not use it — it uses
`base_demand_twh * (1 + demand_growth) ** horizon_years` (10 years, 13 readers).
So the window machinery exists, computes the identity, and is bypassed. Either the
start year should differ from the end year, or the family should be retired;
shipping both conventions is the defect.

**F2. A node's description asserts a read that does not exist.**
`plant_retirement_age`'s description says *"`remaining_useful_life` reads this
node, so the equality is what puts a retirement age behind the remaining-life
arithmetic."* Measured: `plant_retirement_age` has **zero readers**.
`remaining_useful_life` is derived by `remaining_life_from_condition_definition`
from `asset_life * asset_condition_index` and reads `plant_retirement_age`
nowhere. The description is prose the graph does not implement — the same defect
class as a register row that names a caller which does not exist.

**F3. 383 of 481 derived nodes have zero readers, and all 8 boolean-gated
equations produce one.** Any batch that closes `uncoupled()` by adding gated
nodes increases this count. A closing batch should state, per new node, which
equation reads it — or it is adding to the terminal set.

**F4. `coal_retirement_schedule`'s catalog semantics cannot be represented.** The
catalog uses absolute years (2050, 2035) and a rule `coal_retirement_schedule >
2045`; all 51 `unit='years'` nodes are horizon offsets and **no range admits
2045**. Either the node needs a new unit convention for calendar years, or the
catalog's cross-validation rule is unimplementable as written.

**F5. `maintenance_schedule_optimisation` is a switch typed as an untyped float.**
`type=float, unit=None, default=500000.0`, description "Optimise maintenance
timing". Read as an operand it raises `GraphError: 500000.0 is outside the range`.
The same retype that fixed the five loss-mitigation booleans was not applied here.

**F6. The catalog's coal/carbon cross-validation is not in the shipped rules.**
`docs/alea_prg.md` line 1044 states
`carbon_price > 100 and coal_retirement_schedule > 2045`; the graph ships 55 rules
and none names `coal_retirement_schedule`. `carbon_price` is present with
`unit='USD/tonne'` and **`default=None`**, so even a ported rule would have no
value to test at defaults.

**F7. Seven nodes the catalog's grid-operations section names are absent from the
graph:** `dg_placement_benefit`, `phase_shifting_benefit`,
`topology_switching_benefit`, `voltage_optimisation_benefit`,
`storage_dispatch_benefit`, `distributed_generation_capacity`,
`revenue_collection`. Also absent: `reserve_account_share`. The switches in this
slice are the *gates* for a benefit family that was never built — which is why
gating them produces terminal nodes.

**F8. The cyber family is half built.** `cyber_threat_level` is an untyped
placeholder (`unit=None`, 500000.0) with zero readers, while
`cybersecurity_requirements` and `cyber_insurance` are coupled. A family with one
endogenous driver missing reads as complete to any count that only checks the
coupled side.
