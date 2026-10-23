# Coupling pack: the digital, sector-coupling and instrument nodes

## What this pack covers

The 74 nodes in `/tmp/fam_digital-sector.txt`: the digital utility systems, the
sector-coupling shares, the new and unusual loads, five cost rates with typed
units and no equation, the carbon-market and tax rulebooks, the insurer's
firm-specific exposures, the five loss-mitigation switches, and the EV family.

Verified against the tree as it stands (`config/prg.yaml`, batch 34 baked):
`ParameterGraph.from_mapping` returns **1344 nodes, 525 equations, 1075 edges
and 284 uncoupled**. All 74 slice ids exist, and all 74 return `True` from
`uncoupled()` — **every one of them has zero equation readers**, measured by
parsing every equation's `rhs` and intersecting the symbol sets. That is the
defining fact of the slice: it is not a list of quantities waiting for a
formula, it is a list of *names* — **47 of the 74 carry `unit: None` and
`default: 500000.0`**, 51 carry the 500000.0 placeholder, and four more carry a
real unit with the placeholder default (`accumulation_risk`,
`business_interruption`, `catastrophe_modelling`, `liability_exposure`).

The classification is **34 QUALITATIVE, 28 BASE-NEEDED, 5 SCENE-SWITCH, 3
THRESHOLD, 2 PRODUCT, 2 DEPRECATED**. Of the 74, **5 get a proposal** — 3
`read`, 2 `bound` — carrying **5 equations**: three equalities and two bounds.
Three new left-hand-side ids are declared, all three computed by those
equalities. The other **69 are deferred**, and every row states why. Four
deferral classes are structural rather than temporary: QUALITATIVE is the
graph's declared free space; SCENE-SWITCH is run configuration the solver reads;
DEPRECATED is a node whose correct coupling is its removal; and BASE-NEEDED is a
formula whose operands the graph does not carry.

The yield is low, and that is the finding rather than a failure of effort. A
share needs a volume to be a share *of*, a load needs an intensity to multiply,
and a capability name needs a quantity. This slice has almost none of the three:
the graph states agricultural, industrial, residential and commercial
electricity demand, but no machinery energy, no tonne-km of mining haul, no m³
pumped, no visitor-nights, no PUE, no vehicle count.

### What the verification found, before the rows

Six things were checked against the tree rather than assumed, and every one of
them changes a proposal or contradicts a shipped text.

1. **`opex_fixed_wind` has zero readers, and the amendment that was supposed to
   consume it has already landed.** The shipped `lcoe_wind_definition` rhs is
   `(annualised_capex_usd_per_kw_wind + opex_fixed_wind_onshore) * 1000 /
   (8760 * capacity_factor_wind_onshore) + opex_variable_wind` — it reads the
   **onshore** 30, and its `latex` field typesets
   `\mathrm{opex}_{fixed\_wind\_onshore}`. The offshore equation
   (`lcoe_wind_offshore_definition`) reads its own `opex_fixed_wind_offshore`
   (80). The generic node (40) is read by nothing. Measured:
   `lcoe_wind_usd_per_mwh` = **63.673170220862986** at
   defaults; substituting 40 gives **66.52705149940181**. So the prior pack's
   row (*threshold-product-remainder.md* line 144, "the shipped wind LCOE …
   reads the generic `opex_fixed_wind` (40) … takes the LCOE from 66.53 to
   63.67") describes a tree that no longer exists, and **the shipped equation's
   own `description` field is stale in the same way** — it still narrates the
   amendment in the future tense ("The amendment takes the LCOE from 66.53 to
   63.67"). The `latex` and the `rhs` agree with each other; only the prose is
   behind. `opex_fixed_wind` is a dead generic duplicate whose description
   claims "the shipped graph does not [distinguish onshore from offshore]",
   which is false — `opex_fixed_wind_offshore` exists at 80.

2. **The `capex_gas_ocgt` deferral's stated reason does not hold, and the prior
   pack's own row contradicts it.** *threshold-product-remainder.md* line 123
   says "at any capacity factor the OCGT LCOE comes out *below* the CCGT's (78.4
   against 87.8 at 0.6)". Measured from the shipped form with
   `capex_gas_ocgt` = 650: at 0.6 the OCGT LCOE is **78.38595266656986** (the
   quoted 78.4 is right); at 0.3 — the duty the archived IEA/NEA text states for
   OCGTs — it is **96.77190533313974**, *above* the CCGT's 87.82174919126577.
   The crossing is at a capacity factor of **0.3965**. So "at any capacity
   factor" is false, and the same pack's `rejected` column already prints 96.77.
   The real blocker is narrower: the graph has **no `capacity_factor_gas_ocgt`
   node** (only `capacity_factor_gas` = 0.6, the CCGT's), and no heat-rate term
   anywhere (`grep` for `heat_rate`, `conversion_eff`, `lhv`, `calorific` over
   the node table returns nothing). That is why this pack couples the node with
   a **bound** rather than an LCOE.

   A trap worth naming, because I fell into it while checking: the shipped
   `lcoe_gas_definition` is **not** the annuity form alone. Its rhs is
   `(capex_gas * crf_gas + opex_fixed_gas) * 1000 / (8760 * capacity_factor_gas)
   + opex_variable_gas + fuel_cost_gas + emission_factor_gas_t_per_mwh *
   carbon_price_usd_per_tco2` — three per-MWh terms, of which fuel (35.0) and
   carbon (0.45 × 50 = 22.5) are 57.5 of the 87.82. Substituting
   `capex_gas_ocgt` into the annuity alone gives 20.89 at 0.6 and 39.27 at 0.3,
   against a CCGT figure that still carries its fuel and carbon; the comparison
   is then between a partial OCGT cost and a complete CCGT cost, and the OCGT
   looks 67% cheaper. The 78.39 and 96.77 above carry all three per-MWh terms.
   The deeper point stands and is the one that blocks an LCOE: **an OCGT and a
   CCGT do not share a heat rate**, so reusing `fuel_cost_gas` and
   `emission_factor_gas_t_per_mwh` is the same error as reusing the capacity
   factor, in a larger term.

3. **The three marine/gravity capacities are already typed, so the supply pack's
   dependency register is stale.** *supply-emissions-grid.md* lines 159-160 say
   `gravity_storage_capacity`, `marine_otec_capacity` and `marine_tidal_capacity`
   "still carry `unit: None`, range `(0, 1e6)`, default `500000.0`". Measured:
   all three carry **`MW`, range [0, 1e6], default 0.0**. The two marine capex
   products therefore close now (rows below), and the gravity one does **not** —
   for a different reason, see finding 4.

4. **`capex_gravity_storage` is blocked by an energy base, not by a retype — and
   the retype the supply pack proposes would break a shipped equation.** The
   rate is USD/kWh. Measured three forms:
   - `capex_gravity_storage * gravity_storage_capacity * 1000` →
     `decidable=True consistent=False`, "the two sides do not share a dimension"
     (USD/kWh × MW is USD·MW/kWh).
   - `… * storage_duration_curve * 1000` → `decidable=False`, "the rhs has a
     dimension this walker cannot compute" (`storage_duration_curve` is
     `unit: None`, default 500000.0).
   - with `gravity_storage_capacity` retyped to `MWh`, the plain product is
     consistent and reads 0.0 at defaults — **but the retype breaks the shipped
     `gravity_storage_capacity_bound`** (`gravity_storage_capacity leq
     storage_headroom_mw`), which goes from `consistent=True` to
     `decidable=True consistent=False`, "the two sides do not share a
     dimension". The correct coupling is a *new* `gravity_storage_energy_mwh`
     node, not a retype of the MW capacity.

5. **The prior pack's `solvency_capital_ratio >= 1.0` bound duplicates a shipped
   cross-validation rule, and the duplication is visible at run time.**
   `solvency_below_regulatory_floor` (`condition: solvency_capital_ratio < 1.0`,
   `severity: error`) is one of the 55 shipped rules. Measured at
   `solvency_capital_ratio = 0.9`: the rule alone yields one finding and
   `blocks=True`; adding the bound yields the rule's finding **and** a
   consistency violation on `solvency_floor_bound` — one breach, reported twice.
   The node is coupled here as a `read` operand of a new equality instead, which
   closes it from `uncoupled()` without restating the rule.

6. **`accumulation_risk` is a currency quantity declared dimensionless.** Its
   description is "the total exposure the insurer has to a single event" and its
   unit is `1`, range [0, 1e6], default 500000.0 — so a USD quantity carries no
   currency and the 500000.0 placeholder reads as a plausible-looking exposure.
   The same defect is present on `liability_exposure`, `business_interruption`
   and `catastrophe_modelling`, none of which this pack can repair because none
   has a rhs operand to bound it against; `accumulation_risk` can, and the bound
   is what forces the retype (measured without it: `decidable=True
   consistent=False`, "the two sides do not share a dimension"). The retype was
   checked against every equation in the tree: **525 checked, 11 failures
   before, 11 after, none new** (the 11 are pre-existing and untouched).

### A note on the citation column

Four equations carry `reference: None`. Three are unit conversions
(`USD/kW × MW × 1000 = USD` twice, and a ratio × its own denominator), which the
BRIEF admits explicitly. The fourth is a coherence condition — a loss cannot
exceed the exposure it is drawn from — which is definitional and has no paper
behind it, and inventing one would be the comfortable row and the dishonest one.
The fifth equation, the OCGT/CCGT capex ordering, cites the archived IEA/NEA 2020 text,
which states the ordering in prose ("gas-fired OCGTs are typically peak load
plants – CCGTs cover a wider range from mid- to baseload operation") and prints
the costs (Table 3.2a/3.2b: 14 CCGT rows, median **895 USD/kWe**, range
254–1,109; 8 OCGT rows, median **629 USD/kWe**, range 325–1,141). The *rates*
those products multiply are themselves unarchived stochastic placeholders, and
that is recorded under **Sources to fetch** rather than papered over.

## Classification

All 74 nodes. `kind` is the coupling this pack proposes, or `defer` with the
reason.

### PRODUCT (2) — a rate over a base the graph already carries

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `capex_marine_otec` | PRODUCT | read | `USD/kW` (already typed) | [5000, 25000] — unchanged, the node's own pilot-derived band | free / stochastic | `marine_otec_capex_usd = capex_marine_otec * marine_otec_capacity * 1000` (read) | Installed cost per kW of ocean-thermal conversion. The base is `marine_otec_capacity`, already typed `MW` at 0.0, so the product is a unit conversion and reads 0 USD at defaults. 100 MW at 12,000 USD/kW is 1.2 bn USD (canaried). | — (unit conversion: USD/kW × MW × 1000 kW/MW) | A levelised cost. The node is a capital rate; an LCOE needs `crf_marine_otec`, `capacity_factor_marine_otec` and `opex_fixed_marine_otec`, and **none of the three exists** (checked: no node begins `crf_marine`, `capacity_factor_marine` or `opex_fixed_marine`). |
| `capex_marine_tidal` | PRODUCT | read | `USD/kW` (already typed) | [2500, 15000] — unchanged, wide because tidal range and tidal stream are one node | free / stochastic | `marine_tidal_capex_usd = capex_marine_tidal * marine_tidal_capacity * 1000` (read) | Installed cost per kW of tidal capacity. 100 MW at 7,000 USD/kW is 0.7 bn USD (canaried); 0 USD at defaults because the capacity default is 0. | — (unit conversion: USD/kW × MW × 1000 kW/MW) | The same LCOE route, blocked identically. `capex_tidal_range` (7,000, [3000, 15000]) is a second spelling of the range technology and is *not* this node — aliasing them would merge a 15,000 USD/kW ceiling with a 2,500 one. |

### THRESHOLD (3) — a ceiling or a floor, coupled by being an operand or an lhs

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `capex_gas_ocgt` | THRESHOLD | bound | `USD/kW` (already typed) | [300, 1200] — unchanged, the peaker band | free / fixed | `capex_gas_ocgt <= capex_gas` (`leq`) | A peaker costs less per kW than the combined cycle it backs up, and the node's own description already says so ("Lower capex and lower efficiency than the CCGT; that trade is why both live in the graph"). 650 ≤ 1100 at defaults; set to 1200 the bound fails by 100 (canaried), so it is live rather than vacuous. | IEA/NEA Projected Costs of Generating Electricity (`sources/archive/iea_nea_egc_2020.pdf`) | The prior pack's deferral, whose stated reason is false (finding 2). Also rejected: `lcoe_gas_ocgt_usd_per_mwh = (capex_gas_ocgt * crf_gas + opex_fixed_gas) * 1000 / (8760 * capacity_factor_gas) + opex_variable_gas + fuel_cost_gas + emission_factor_gas_t_per_mwh * carbon_price_usd_per_tco2` — the full shipped form with only the capex swapped. It reuses **three** CCGT parameters the peaker does not share: the capacity factor, the fuel cost per MWh (a heat-rate proxy) and the emission factor per MWh. At the CCGT's own 0.6 it ranks the peaker 78.39 against 87.82; at the archived 0.3 duty it ranks it 96.77. Neither number is a cost model, because the two per-MWh terms are the CCGT's. |
| `solvency_capital_ratio` | THRESHOLD | read | `1` (already typed) | [0.8, 3.0] — the node's own prudential band | free / policy | `eligible_own_funds_usd_million = solvency_capital_ratio * solvency_capital` (read) | Eligible own funds as a share of required capital; the ratio times the required capital is the funds themselves, which no node held. 1.6 × 450 = **720 USD million** at defaults. | — (definitional: the ratio's own definition, solved for its numerator) | `solvency_capital_ratio >= 1.0` — **rejected as a duplicate**: the shipped rule `solvency_below_regulatory_floor` states the identical condition at `error` severity and blocks (measured, finding 5). A bound would report one breach twice. |
| `accumulation_risk` | THRESHOLD | bound | `USD million` (**retyped** from `1`) | [0, 1e6] — unchanged; in USD million this admits exposures to 1e12 USD | free / fixed | `accumulation_risk >= pml_99_5_usd_million` (`geq`) | The insurer's total exposure to a single event must cover the loss it models at the 99.5th percentile, or the tail loss is drawn from a distribution the book cannot pay. 500,000 ≥ 500 at defaults; at 100 the bound fails by 400 (canaried). The value of the row is the retype: the bound is what forces the currency the node's own description names. | — (coherence: a loss cannot exceed the exposure it is drawn from) | Leaving the node dimensionless and comparing against `pml_99_5_usd_million` (USD million) — measured `decidable=True consistent=False`, "the two sides do not share a dimension". Also rejected: `accumulation_risk = pml_99_5_usd_million` (an equality), which would make a firm-specific input derived from a modelled output and delete the dial. |

### QUALITATIVE (34) — a procedure, a standard, or a rulebook

| node | class | kind | reason |
|---|---|---|---|
| `ami_infrastructure` | QUALITATIVE | defer | Advanced metering infrastructure: a system deployment, not a measurement. The graph's quantitative counterpart is `smart_metering_penetration` (already coupled by `smart_metered_population_definition`); this node is the platform's name. |
| `asset_management_systems` | QUALITATIVE | defer | EAM. A system description. `docs/modelling-alg-3a.md` classifies it as "System model". |
| `billing_systems` | QUALITATIVE | defer | The billing platform's capability. A procedure. |
| `communication_protocols` | QUALITATIVE | defer | The protocol stack (IEC 61850, DNP3, …). A standard's name; no base it could multiply. |
| `customer_information_systems` | QUALITATIVE | defer | CIS capability. A system description. |
| `cyber_incident_response` | QUALITATIVE | defer | An incident-response procedure (detect, contain, recover). Two quantitative siblings exist and are coupled: `cybersecurity_requirements` → `cybersecurity_spend_usd_per_year`, `cyber_insurance` → `cyber_cover_usd_per_year`. A third, `cyber_threat_level`, is itself uncoupled (`unit: None`, 500000.0) and has zero readers — so the cyber family is only half built, which is a finding rather than a base for this row. |
| `data_backup_recovery` | QUALITATIVE | defer | An RPO/RTO policy. A procedure. |
| `der_management_systems` | QUALITATIVE | defer | DERMS. A system description; the graph carries no distributed-generation capacity for it to manage. |
| `outage_management_systems` | QUALITATIVE | defer | OMS. A system description; the reliability *quantities* (`outage_frequency`, `outage_duration`, `system_saidi_hours_per_year`, `system_saifi_events_per_year`) are separately derived by `saidi_definition` / `saifi_definition` and already coupled. |
| `work_management_systems` | QUALITATIVE | defer | WMS. A system description. |
| `article_6_2_parameters` | QUALITATIVE | defer | The Paris Agreement's bilateral-transfer rulebook. A treaty choice. Its quantitative counterpart exists and is coupled: `corresponding_adjustment` → `article_6_credits`. |
| `article_6_4_parameters` | QUALITATIVE | defer | The 6.4 mechanism's rulebook (methodologies, corresponding adjustments, share of proceeds). A procedure; no volume base distinguishes it from 6.2's. |
| `carbon_credit_rating` | QUALITATIVE | defer | A credit rating is a level name (AAA … BB), not a magnitude. The price it would shift is `carbon_credit_prices` (already typed and coupled); a rating-to-price curve is a rating agency's output, not a graph identity. |
| `carbon_credit_vintage` | QUALITATIVE | defer | A vintage year is a label. The volume is `carbon_credit_volumes` (derived) and the value `carbon_credit_value_usd_per_year` (derived); neither reads a vintage. |
| `cdm_methodologies` | QUALITATIVE | defer | The Clean Development Mechanism's methodology set. A rulebook. |
| `corsia_parameters` | QUALITATIVE | defer | An aviation offset scheme's rulebook. The aviation *energy* base exists (`aviation_fuel_demand`, 3,000,000 MWh/year), but CORSIA's parameters (baseline year, offset obligation factor) have no operand in the graph and no emissions line is derived from that fuel. |
| `gold_standard_methodologies` | QUALITATIVE | defer | A certification standard's methodology set. A rulebook. |
| `mrv_parameters` | QUALITATIVE | defer | Monitoring, reporting and verification. A procedure; the measured quantity it verifies is `carbon_credit_volumes`, derived by `carbon_credit_volumes_definition` from `additional_abatement_mtco2` and already coupled. |
| `vcs_methodologies` | QUALITATIVE | defer | The Verified Carbon Standard's methodology set. A rulebook. |
| `business_interruption` | QUALITATIVE | defer | FIRM-SPECIFIC by its own description: "scope of cover, waiting period and indemnity period vary by policy". The *share* of revenue indemnified is the separate, coupled `business_interruption_insurance` (0.01) → `business_interruption_cover_usd_per_year` = 64,870,160.59 at defaults. |
| `cat_bond_parameters` | QUALITATIVE | defer | A bond's structural terms (tranche, trigger, attachment). The priceable quantity is `cat_bond_spread` (800 bp) → `cat_bond_coupon_cost_usd`, already shipped. |
| `catastrophe_modelling` | QUALITATIVE | defer | A cat model's *output for a specific book*, by its own description. A model reference id, not a parameter; a future batch should split or remove it. |
| `climate_risk_disclosure` | QUALITATIVE | defer | TCFD disclosure practice. A reporting regime; no quantity it could determine. |
| `liability_exposure` | QUALITATIVE | defer | FIRM-SPECIFIC. Carries the same unit defect as `accumulation_risk` (`unit: 1` for a currency quantity, 500000.0 placeholder) but has **no** rhs operand to bound it against, so the retype would be unforced. Recorded as a finding for a batch that has a base. |
| `parametric_trigger_threshold` | QUALITATIVE | defer | A hazard level expressed as a share of the policy's notional hazard. The graph has no hazard level with a unit (`exposure_index` and `vulnerability_index` are both normalised composites; `drought_risk`, `flood_risk`, `wildfire_risk`, `landslide_risk`, `cold_snap_frequency`, `heatwave_frequency`, `extreme_weather_events` are all `unit: None` placeholders). A share of nothing. |
| `double_tax_treaty` | QUALITATIVE | defer | A treaty network's existence and scope. A legal fact; its effect is already a rate (`withholding_tax_dividends` and `withholding_tax_interest`, both typed `1` and both already read by their own spend definitions). |
| `tax_holiday_conditions` | QUALITATIVE | defer | The eligibility conditions for a holiday. The holiday's *duration* is `tax_holiday_duration` (5 years) → `taxed_fraction_of_concession`, already coupled. |
| `tax_incentive_zones` | QUALITATIVE | defer | Special economic zones. A geography designation with no land or activity base in the graph. |
| `thin_capitalisation_rules` | QUALITATIVE | defer | The thin-cap rulebook. The ceiling is the quantity: `thin_capitalisation_limit` (1.5) → `thin_capitalisation_utilisation`, already coupled. |
| `transfer_pricing_rules` | QUALITATIVE | defer | Transfer-pricing methodology. A rulebook; the graph has no intra-group transaction volume for it to price. |
| `demand_growth_profile` | QUALITATIVE | defer | A curve *family* (linear, S-curve, logistic). The rate is `demand_growth` (0.0325/year, exogenous) and it is already coupled; no equation can select among functional forms. |
| `electrification_timeline` | QUALITATIVE | defer | "Year to reach target" — a scenario schedule. The target is a separate node. |
| `ev_adoption_timeline` | QUALITATIVE | defer | The same schedule argument. The share it reaches is `ev_share_new_sales`, which is BASE-NEEDED below. |
| `hydrogen_storage_type` | QUALITATIVE | defer | A storage type (salt cavern, depleted field, above-ground vessel) — a level name. The quantity is `hydrogen_storage_cost` (15 USD/kWh), already coupled by `hydrogen_storage_capex_definition`. |

### BASE-NEEDED (28) — a formula is statable and an operand is absent

| node | class | kind | reason |
|---|---|---|---|
| `agricultural_machinery` | BASE-NEEDED | defer | A share (0.05) of agricultural machinery that is electric. The missing base is machinery energy or machinery fuel volume. `agricultural_demand_twh` is the sector's *total electricity* demand, derived as `agricultural_demand_share * base_demand_twh` — applying a machinery-electrification share to it double-counts the very quantity the share is meant to create, and it is itself a derived node with zero readers. |
| `airport_electrification` | BASE-NEEDED | defer | A share (0.1) of airport ground operations that are electric. `aviation_fuel_demand` exists (3,000,000 MWh/year) but it is *fuel*, not ground-operations energy, and its only reader is `synthetic_aviation_fuel_mwh_definition` (`synthetic_fuel_share_aviation * aviation_fuel_demand`). There is no airport ground-equipment energy node. |
| `capital_gains_tax` | BASE-NEEDED | defer | A rate (0.2) on realised capital gains. The base `realised_capital_gain_usd_per_year` does not exist and no asset-sale or disposal line does either — `grep` for `gain` over the node table returns this node alone. Concurring with *macro-fiscal.md*. |
| `cold_storage_load` | BASE-NEEDED | defer | A cold-chain load. Missing: a specific energy (kWh/m³/year or kWh/t) and a store volume. |
| `construction_load` | BASE-NEEDED | defer | Temporary construction load. The graph has `total_capacity_mw` (10,000 MW), `construction_period` (30 months) and `construction_jobs_per_mw`, so a *workforce* base exists — but not an energy one: there is no site-power intensity (kWh/MW-month) and no floor area, and `construction_load` is a load, not a headcount. |
| `construction_machinery` | BASE-NEEDED | defer | A share (0.05) of construction machinery that is electric. Missing: machinery energy, as for the agricultural share. |
| `data_centre_demand` | BASE-NEEDED | defer | A new data-centre load. Missing: an IT load in MW and a PUE. Neither `pue` nor any server/IT-load node exists. |
| `digital_divide_metrics` | BASE-NEEDED | defer | A composite of connectivity, price and skill, normalised to [0, 1]. Only connectivity exists (`internet_penetration` 0.5); there is no electricity-price-affordability component tied to connectivity and no digital-skill share — `skills_requirements` is the craft share of *construction* jobs. Note it is already read by the shipped rule `index_above_unity`, which does not close it. |
| `drought_frequency` | BASE-NEEDED | defer | A "drought frequency multiplier" with `unit: None`. A multiplier with no multiplicand: the graph has `hydro_drought_multiplier` (already read by `hydro_effective_capacity_factor_definition`), which is the *result*, not the base. The missing operand is a drought-loss or drought-affected-capacity node. |
| `drought_severity` | BASE-NEEDED | defer | As `drought_frequency`: a severity multiplier with nothing to multiply. |
| `emergency_shelter_load` | BASE-NEEDED | defer | Missing: shelter occupancy (persons) and a kWh/person/day intensity. |
| `ev_battery_size` | BASE-NEEDED | defer | Average EV battery size. Missing a vehicle count or sales flow — the graph carries shares of the vehicle stock (`electric_vehicle_adoption` 0.5, `ev_share_new_sales`, `hydrogen_vehicle_share` 0.02) and no stock or sales volume. |
| `ev_efficiency` | BASE-NEEDED | defer | EV efficiency (kWh/km). Missing vehicle-km: no distance or mileage node exists. |
| `ev_share_new_sales` | BASE-NEEDED | defer | A share (0.2) of new vehicle sales that are electric. A share of a flow with no flow: there is no new-vehicle-sales volume, and `transport_logistics` is tonne-km of freight, a different quantity. |
| `fishing_vessel_fuel` | BASE-NEEDED | defer | Missing: the fishing fleet's fuel volume. The graph's fishing quantity is the *community's* electricity (`fishing_community_load`, 5 MW, already coupled through `fishing_community_load_definition`), which is a different sector from the vessels' own fuel. |
| `irrigation_coverage` | BASE-NEEDED | defer | A share (0.15) of arable land under irrigation. The only land node is `land_area_hectares` (the project's own 5,000 ha take), not national arable area; there is no arable-area node. Note the *load* side is already coupled: `irrigation_pumping_demand` (0.5 TWh) → `agricultural_irrigation_load`. |
| `military_energy_demand` | BASE-NEEDED | defer | Missing: any military fuel or energy volume. |
| `mining_demand_growth` | BASE-NEEDED | defer | "Additional mining load growth". Missing: a mining load for the growth to apply to. |
| `mining_electrification` | BASE-NEEDED | defer | A share (0.1) of mining energy met by electricity. Missing: mining energy demand. |
| `mining_haulage` | BASE-NEEDED | defer | Missing: tonne-km of mining haul and a kWh/tonne-km intensity. `transport_logistics` (45e9 tonne·km/year) is national freight, not mine haul, and using it would attribute all road and rail freight to mining. |
| `mining_hydrogen_haulage` | BASE-NEEDED | defer | As `mining_haulage`, with a hydrogen intensity the graph also does not carry. |
| `physical_risk_score` | BASE-NEEDED | defer | A composite of the asset's physical climate risk, normalised to [0, 1]. The graph carries `exposure_index` and `adaptive_capacity` but no `sensitivity` and no hazard term with a unit. **The tempting product `exposure_index * (1 - adaptive_capacity)` is rejected**: *threshold-product-remainder.md* already refused `vulnerability_index = 1 - adaptive_capacity` on the ground that vulnerability is a composite of three terms and not the complement of one, and this is the same claim under a third id. |
| `port_electrification` | BASE-NEEDED | defer | A share (0.1) of port operations that are electric. Missing: port operations energy (shore power, cranes, yard equipment). |
| `post_harvest_processing_load` | BASE-NEEDED | defer | Missing: crop volume (t/year) and a kWh/t intensity. |
| `tourism_load` | BASE-NEEDED | defer | Missing: visitor-nights and a kWh/visitor-night intensity. |
| `wastewater_treatment_load` | BASE-NEEDED | defer | Missing: m³ treated and a kWh/m³ intensity by treatment level. `total_water_demand_m3` exists but is the *supply* side (`cooling_water_demand_m3 + hydrogen_water_demand_m3`) — it is what the project consumes, not what it discharges, and the graph has no specific-energy node matching `kwh_per_m3` at all. |
| `water_pumping_load` | BASE-NEEDED | defer | Missing: a kWh/m³ pumping intensity. The volume side now exists (`total_water_demand_m3`, m³/year, derived), but the intensity does not — `grep` for `kwh_per_m3` over the node table returns nothing, and the closest analogue (`irrigation_pumping_demand`, 0.5 TWh/year) is a *load*, not a rate, so multiplying by it would square a load. |
| `capex_gravity_storage` | BASE-NEEDED | defer | USD/kWh with no energy base. `gravity_storage_capacity` is MW; the product is dimensionally inconsistent (measured), `storage_duration_curve` is `unit: None` so the duration-corrected form is undecidable (measured), and retyping the capacity to MWh breaks the shipped `gravity_storage_capacity_bound` (measured). The missing operand is `gravity_storage_energy_mwh`. |

### SCENE-SWITCH (5) — run configuration, no equation

| node | class | kind | reason |
|---|---|---|---|
| `dg_placement_enabled` | SCENE-SWITCH | defer | A `bool` with `range: None`, default 1.0. Distributed-generation siting on or off. |
| `phase_shifting_enabled` | SCENE-SWITCH | defer | A `bool`, default 0.0. Phase-balancing on or off. |
| `storage_dispatch_enabled` | SCENE-SWITCH | defer | A `bool`, default 1.0. Storage dispatch on or off. |
| `topology_switching_enabled` | SCENE-SWITCH | defer | A `bool`, default 1.0. Reconfiguration on or off. |
| `voltage_optimisation_enabled` | SCENE-SWITCH | defer | A `bool`, default 1.0. Voltage set-point optimisation on or off. |

**A boolean multiplied into a formula is a hidden branch, and this pack ships no
arithmetic for any of the five.** There is precedent in the tree — `ets_enabled`
is a `float` in [0, 1] read by `gated_carbon_volume_definition`, and eight
equations multiply one of nine `bool` nodes into a product
(`capacity_market`, `carbon_border_adjustment`, `n_1_criterion` and
`n_2_criterion` in one equation, `outage_coordination`, `ppa_guarantees`,
`cross_border_trade_allowed`, `transmission_expansion_allowed`,
`smart_metering_rollout`) — but every one of those is a *gate on an existing
quantity*: the branch is the whole point and the operand on the other side is a
number the graph already carries. For these five there is no gated quantity, and
the distinction is worth stating precisely because two of them look close:

- `dg_placement_enabled` needs distributed-generation capacity. Measured: no node
  matches `distribut|^dg_capacity|rooftop|behind_meter` except
  `rooftop_solar_adoption`, which is a household *share* with no capacity under
  it.
- `phase_shifting_enabled` needs a phase-imbalance loss. Measured: the only node
  matching `phase` is the switch itself.
- `storage_dispatch_enabled` needs an unserved-energy quantity *with dispatch
  off*. `unserved_energy_gwh` exists (`equilibrium_demand_twh *
  expected_unserved_fraction * 1000`), but it is the unserved energy the system
  already has — gating it by this switch would zero the system's own unserved
  energy when dispatch is on, which is the wrong sign and the wrong quantity.
- `topology_switching_enabled` needs a reconfiguration saving. Measured: no node
  matches `reconfig`, and `distribution_losses_twh` is a total, not a delta.
- `voltage_optimisation_enabled` needs a voltage-dependent loss curve.
  `distribution_losses_twh` and `distribution_loss_factor` both exist, but
  neither is a saving: a gate would delete losses when optimisation is on rather
  than reduce them, and `ac_voltage_limit` — the one node that would set the
  curve — is itself `unit: None` with the 500000.0 placeholder.

A switch times an absent base is a branch with nothing behind it, and a switch
multiplied into a *total* is worse: it asserts that the total vanishes when the
feature is off. The five stay run configuration.

### DEPRECATED (2) — a node whose correct coupling is its removal

| node | class | kind | reason |
|---|---|---|---|
| `demand_growth_rate` | DEPRECATED | defer | `deprecated_by: demand_growth`; the loader refuses a deprecated target outright. Carries the correct unit (`1/year`), range [-0.05, 0.15] and default 0.04; the canonical `demand_growth` is 0.0325. Not to be touched — the shipped value is right and the coupling is deletion once no scenario names it. |
| `opex_fixed_wind` | DEPRECATED | defer | **Shipped in batch 55 (2026-10-24) as proposed.** Proposed `status: deprecated`, `deprecated_by: opex_fixed_wind_onshore`. **Measured**: the pair loads (`nodes 1344`, `uncoupled 284`, no `GraphError`) and the node remains in `uncoupled()` — deprecation is a classification, not a coupling, and removal is the batch's job. Evidence for the class: zero equation readers, zero code readers (the only `src`/`scripts` hits are four comment and description strings in `prg_coupler.py`, none of which executes), `lcoe_wind_definition` reads `opex_fixed_wind_onshore` and typesets it, and `lcoe_wind_offshore_definition` reads its own 80. A generic 40 has nothing left to serve. |

## Proposals

### New nodes this pack declares

Three left-hand-side ids do not exist in the graph (checked: absent from
`g.nodes`, and no equation id `*_definition` collides).

| node | unit | range | default | role / determinism | why |
|---|---|---|---|---|---|
| `marine_otec_capex_usd` | `USD` | [0, 2.5e13] — 25,000 USD/kW × 1e6 MW × 1000, the product of the two operands' own maxima | — | derived / physical | OTEC's installed capital cost. `capex_marine_otec` is a rate and the graph held no total; the storage family already has this shape (`hydrogen_storage_capex_usd`). |
| `marine_tidal_capex_usd` | `USD` | [0, 1.5e13] — 15,000 USD/kW × 1e6 MW × 1000 | — | derived / physical | Tidal's installed capital cost, same construction. |
| `eligible_own_funds_usd_million` | `USD million` | [-1.5e6, 1.5e6] — the ratio's [0.8, 3.0] times `solvency_capital`'s [-5e5, 5e5] | — | derived / physical | The capital an insurer actually holds. `solvency_capital_ratio`'s own description defines the ratio as "eligible own funds as a share of the required solvency capital", and the denominator is `solvency_capital`; the numerator was missing, so the ratio was a bare number with no balance-sheet quantity behind it. |

### Retype

One node changes unit. Authored in `config/prg.yaml`; the node is frozen, so it
cannot be changed at runtime.

| node | from | to |
|---|---|---|
| `accumulation_risk` | `1`, [0, 1e6], 500000.0, free / fixed | `USD million`, [0, 1e6], 500000.0, free / fixed |

The range and default are unchanged; only the dimension is corrected, and the
bound is what forces it. Measured across all 525 equations: **11 unit failures
before, 11 after, none new, none fixed** — the retype is safe for the tree as it
stands.

### PRODUCT (2 slice rows, plus the 3 declared nodes they and the threshold rows compute)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `marine_otec_capex_usd` | PRODUCT | derive | `USD` (new node) | [0, 2.5e13] — see the new-node table | derived / physical | `marine_otec_capex_usd = capex_marine_otec * marine_otec_capacity * 1000` | OTEC's installed capital cost: the per-kW rate over the built capacity. 0 USD at defaults because no OTEC is built; 100 MW at 12,000 USD/kW is **1.2e9 USD**. | — (unit conversion: USD/kW × MW × 1000 kW/MW) | An LCOE: `crf_marine_otec`, `capacity_factor_marine_otec` and `opex_fixed_marine_otec` all absent (checked). A capex-per-MWh: no energy base exists, since the capacity factor that would produce one is the absent node. |
| `marine_tidal_capex_usd` | PRODUCT | derive | `USD` (new node) | [0, 1.5e13] | derived / physical | `marine_tidal_capex_usd = capex_marine_tidal * marine_tidal_capacity * 1000` | Tidal's installed capital cost. 0 USD at defaults; 100 MW at 7,000 USD/kW is **7.0e8 USD**. | — (unit conversion) | As OTEC. Aliasing `capex_marine_tidal` onto `capex_tidal_range` — rejected: the two carry different bands ([2500, 15000] against [3000, 15000]) and the tidal-stream half of this node's band has no range analogue. |
| `eligible_own_funds_usd_million` | PRODUCT | derive | `USD million` (new node) | [-1.5e6, 1.5e6] | derived / physical | `eligible_own_funds_usd_million = solvency_capital_ratio * solvency_capital` | The capital held against the solvency requirement: the ratio times the required capital. 1.6 × 450 = **720 USD million** at defaults; at a ratio of 0.9 it is **405** (canaried). Signed because `solvency_capital` is signed — `pml_99_5 - aal` can go negative when the expected loss exceeds the tail, which is a book no capital covers. | — (definitional: the ratio's own definition, solved for its numerator) | `eligible_own_funds_usd_million = solvency_capital` (an alias) — rejected: it makes the ratio identically 1.0 and deletes the dial the prudential regime is about. |

### THRESHOLD (3 rows)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `capex_gas_ocgt` | THRESHOLD | bound | `USD/kW` | [300, 1200] — unchanged | free / fixed | `capex_gas_ocgt <= capex_gas` (`leq`) | A peaker costs less per kW than the combined cycle it backs up. 650 ≤ 1100 at defaults (residual -450); at 1200 the residual is **+100** and the bound fails, so it is live. Routes `bound`. | IEA/NEA Projected Costs of Generating Electricity (`sources/archive/iea_nea_egc_2020.pdf`) | The prior deferral (its reason is false — finding 2), and an OCGT LCOE over the CCGT's capacity factor (finding 2's crossing at 0.3965). |
| `solvency_capital_ratio` | THRESHOLD | read | `1` | [0.8, 3.0] — unchanged | free / policy | `eligible_own_funds_usd_million = solvency_capital_ratio * solvency_capital` (read) | The ratio times the required capital is the funds themselves: 720 USD million at defaults. | — (definitional) | `solvency_capital_ratio >= 1.0` — rejected as a duplicate of the shipped blocking rule (measured: one breach, two reports). |
| `accumulation_risk` | THRESHOLD | bound | `USD million` (retyped) | [0, 1e6] | free / fixed | `accumulation_risk >= pml_99_5_usd_million` (`geq`) | Exposure must cover the modelled tail loss. 500,000 ≥ 500 at defaults (residual 499,500); at 100 the residual is **-400** and the bound fails. Routes `bound`. | — (coherence: a loss cannot exceed the exposure it is drawn from) | An equality against `pml_99_5_usd_million`, which would delete a firm-specific input; and the dimensionally-inconsistent comparison without the retype (measured `consistent=False`). |

## Verification

Run against `config/prg.yaml` as it stands, with the one retype and the three new
nodes applied in memory and the five equations added:

```
BASE  nodes 1344 equations 525 edges 1075 uncoupled 284
BUILT nodes 1347 equations 530 edges 1075 uncoupled 279
symbol check: 5 right-hand sides, 0 unresolved symbols
lhs appears on no other rhs: 5 of 5 clean
check_equation: 5 of 5 decidable=True consistent=True
routes: bound 2, unbound 3
excursions: {}
violations: []
consistent: True   (cross-validation findings: 0)
```

`uncoupled()` loses exactly the five proposed nodes and gains none:
`accumulation_risk`, `capex_gas_ocgt`, `capex_marine_otec`, `capex_marine_tidal`,
`solvency_capital_ratio`. The three declared ids are new, so they are not in the
before-set.

The values at the propagated defaults, as printed:

```
marine_otec_capex_usd          = 0.0
marine_tidal_capex_usd         = 0.0
eligible_own_funds_usd_million = 720.0
solvency_capital_ratio         = 1.6
solvency_capital               = 450.0
accumulation_risk              = 500000.0
pml_99_5_usd_million           = 500.0
capex_gas_ocgt                 = 650.0
capex_gas                      = 1100.0
```

The two marine products read 0.0 because both capacities default to 0 — the
shipped graph builds no marine plant. That is a correct zero, not a dead
equation, and the canary is what says so:

```
marine_otec_capacity  = 100  -> marine_otec_capex_usd = 1.2e9
marine_tidal_capacity = 100  -> marine_tidal_capex_usd = 7.0e8
solvency_capital_ratio = 0.9 -> eligible_own_funds_usd_million = 405.0
capex_gas_ocgt = 1200        -> ocgt_capex_ordering_bound residual   +100.0   (fails)
accumulation_risk = 100      -> accumulation_exposure_bound residual -400.0   (fails)
```

The three equalities route `unbound` — each lhs is derived, so there is no
network column and the audit checks them post-solve. The two bounds route
`bound`: every term is a settable scalar, so both are LP constraints.

Numbers quoted elsewhere in this pack, measured on the same run:
`lcoe_wind_usd_per_mwh` = **63.673170220862986** (and **66.52705149940181** with
`opex_fixed_wind`'s 40 substituted), `lcoe_wind_offshore_usd_per_mwh` =
121.00390761790821, `lcoe_gas_usd_per_mwh` = **87.82174919126577**,
`crf_gas` = 0.11021010340844806, the OCGT LCOE over the shipped form =
**78.38595266656986** at 0.6 and **96.77190533313974** at 0.3,
`business_interruption_cover_usd_per_year` = 64870160.593007125,
`cyber_cover_usd_per_year` = 12974032.118601425, and the three per-MWh terms in
`lcoe_gas_definition` that the OCGT discussion turns on — `fuel_cost_gas` = 35.0,
`emission_factor_gas_t_per_mwh` = 0.45, `carbon_price_usd_per_tco2` = 50.0, so
fuel and carbon are 57.5 of the CCGT's 87.82.

## Deferrals

Sixty-nine of the 74 are deferred, in six registers. This section is the count;
the reasons are in the class tables above.

| class | deferred | what would close it |
|---|---|---|
| QUALITATIVE | 34 | nothing, by construction — a procedure, standard or rulebook has no base to multiply. The class is the graph's declared free space. |
| BASE-NEEDED | 28 | a named operand the graph does not carry, listed per row and consolidated under **Dependencies**. Every one is a quantity, not a source: this is the class that a later batch closes by *adding nodes*, not by adding equations. |
| SCENE-SWITCH | 5 | a run configuration the solver reads. Closing these is a solver change, not an equation; see the argument under the SCENE-SWITCH table. |
| THRESHOLD | 0 | all three carry a proposal. |
| PRODUCT | 0 | both carry a proposal. |
| DEPRECATED | 2 | deletion. `demand_growth_rate` once no scenario names it; `opex_fixed_wind` now — it has zero readers and zero code consumers. |

The overlap with the four prior packs, measured by id substring rather than
assumed: 46 of the 74 appear in at least one prior pack — 18 in
*demand-sector.md*, 21 in *unclassified.md*, 3 in *supply-emissions-grid.md*, 3
in *threshold-product-remainder.md*, 1 in *macro-fiscal.md* — and 28 appear in
none. No id appears in two packs. Where this pack contradicts a prior one, the
contradiction is named in the findings rather than silently resolved: findings 1,
2, 3 and 4 are four such cases, and finding 5 is a fifth.

## Findings

What this pack found that contradicts shipped text, prior packs, or the graph's
own declarations. Each was measured; none is inferred.

1. **`lcoe_wind_definition`'s `description` describes an amendment that has
   already landed, and *threshold-product-remainder.md* line 144 is premised on
   the pre-amendment tree.** The `rhs` reads `opex_fixed_wind_onshore` (30) and
   the `latex` typesets it; only the prose still says the shipped form reads the
   generic 40 and that "the amendment takes the LCOE from 66.53 to 63.67". The
   shipped value is 63.673170220862986 — post-amendment — and the 66.53 figure
   is what the generic would give. Two comments in
   `scripts/build/prg_coupler.py` (lines 9438-9441, 10679) repeat the same stale
   claim, and line 10679 states it as a rendering defect ("typesets the generic
   `opex_fixed_wind` (40) where the body holds `opex_fixed_wind_onshore`") that
   the `latex` field does not exhibit. The consequence: `opex_fixed_wind` has
   **zero** equation readers and is a dead duplicate. **Closed in batch 55
   (2026-10-24):** the description was rewritten through `_rebuild` and now
   states the shipped value and the reason the form reads the onshore node. Two
   corrections to this finding's own numbers. (a) The 66.53 -> 63.67 pair
   describes the batch-35 tree, two batches before this pack was written; the
   live LCOE is **63.68245924494044**, which rounds to the 63.67 printed here —
   the three-decimal figure was right and the fifteen-significant-figure one was
   stale, which is how the drift went unseen. (b) The three `prg_coupler.py`
   sites this finding cites are build records, not claims about the shipped
   tree: lines 9430 and 9590 sit inside `build_batch31`, which is the payload
   that shipped the false description, and line 11003 sits inside
   `build_batch35`'s docstring recording the rendering defect that batch 35 then
   repaired. Reading the third as a live defect is the error — the `latex` field
   does not exhibit it *because* batch 35 fixed it. Batch 55 left all three
   alone: a build record describes the tree at the batch that wrote it, and
   rewriting history to match today is worse than a stale comment.

2. **The `capex_gas_ocgt` deferral's reason is false as stated.**
   *threshold-product-remainder.md* line 123 says "at any capacity factor the
   OCGT LCOE comes out *below* the CCGT's". Measured over the full shipped form:
   below at 0.6 (78.39), above at the archived 0.3 (96.77), crossing at 0.3965.
   The same row's `rejected` column already prints the 96.77, so the pack
   contradicts itself. The blocker is not a sign error but three absent peaker
   rates — `capacity_factor_gas_ocgt`, and the fuel and emission factors the
   shipped form prices per MWh.

3. **`supply-emissions-grid.md` lines 159-160 are stale on all three
   capacities.** It says `gravity_storage_capacity`, `marine_otec_capacity` and
   `marine_tidal_capacity` "still carry `unit: None`, range `(0, 1e6)`, default
   `500000.0`". All three carry `MW`, range [0, 1e6], default 0.0. Its requested
   retype of `gravity_storage_capacity` to MWh is **not** safe either: measured,
   it turns the shipped `gravity_storage_capacity_bound` from
   `consistent=True` to `decidable=True consistent=False` ("the two sides do not
   share a dimension"), because that bound compares the capacity against
   `storage_headroom_mw`.

4. **The prior pack's `solvency_capital_ratio >= 1.0` bound duplicates the
   shipped rule `solvency_below_regulatory_floor`.** Measured at
   `solvency_capital_ratio = 0.9`: the rule alone yields one finding and
   `blocks=True` with no consistency violation; adding the bound yields the same
   finding **and** a hard violation on `solvency_floor_bound`. One breach, two
   reports, and the bound adds nothing the rule does not already block.

5. **`accumulation_risk` is a currency quantity declared `unit: 1`, and three of
   its siblings cannot be repaired yet.** Its own description calls it "the total
   exposure the insurer has to a single event"; the unit is `1` and the default
   is the 500000.0 placeholder. The retype to `USD million` is measured safe
   across all 525 equations (11 unit failures before, 11 after, none new). The
   same defect is on `liability_exposure`, `business_interruption` and
   `catastrophe_modelling`, which stay unforced because no rhs operand bounds
   them.

6. **`solvency_capital` is the *required* capital, not the eligible own funds,
   so the new id `eligible_own_funds_usd_million` is a deliberate misnomer to
   state in prose.** `solvency_capital_definition` is `pml_99_5_usd_million -
   aal_usd_million`, which is a capital requirement; multiplying by the ratio
   gives the funds held *if* the ratio is read as funds-over-requirement, which
   is the node's own definition. The arithmetic is right and the name is
   approximate: a reader who takes `solvency_capital` for a balance-sheet
   quantity will misread the product by the ratio.

7. **The cyber family is half built.** `cybersecurity_requirements` and
   `cyber_insurance` are coupled; `cyber_threat_level` is uncoupled, `unit:
   None`, default 500000.0, with zero readers. A threat level nothing reads is a
   dial with no consequence.

8. **Nine hazard nodes form one placeholder family.** `drought_risk`,
   `flood_risk`, `wildfire_risk`, `landslide_risk`, `cold_snap_frequency`,
   `heatwave_frequency`, `extreme_weather_events`, `drought_frequency` and
   `drought_severity` all carry `unit: None` and default 500000.0. Two of the
   nine are in this slice; the other seven are not, which makes the family a
   cross-slice batch rather than a row here. `parametric_trigger_threshold` and
   `physical_risk_score` both need a hazard level with a unit, and there is none.

9. **`gravity_storage_capacity` is MW while `hydrogen_storage_capacity` and
   `thermal_storage_capacity` are MWh.** The graph spells storage capacity two
   ways, and the gravity capex rate (USD/kWh) is priced in the unit its capacity
   node does not carry. That is the structural reason `capex_gravity_storage`
   cannot close, and it will recur for any storage technology added with an
   energy-denominated cost.

## Dependencies

Bases this slice needs and does not own. Each is named in a row above and must
not be proposed here.

- **A machinery-energy base** — blocks `agricultural_machinery` and
  `construction_machinery`. The graph states sector *electricity*, which is the
  output of electrification, not its input.
- **A mining load and a mining tonne-km** — blocks `mining_electrification`,
  `mining_haulage`, `mining_hydrogen_haulage` and `mining_demand_growth`.
  `transport_logistics` (45e9 tonne·km/year) is national freight and cannot
  stand in.
- **A vehicle stock or sales volume** — blocks `ev_share_new_sales`,
  `ev_battery_size` and `ev_efficiency`. The graph carries three shares of the
  stock and no stock.
- **A pumping and treatment intensity in kWh/m³** — blocks `water_pumping_load`
  and `wastewater_treatment_load`. The volume side exists for pumping
  (`total_water_demand_m3`, derived) but not the rate; for treatment neither
  side does, since `total_water_demand_m3` is supply and the graph has no
  discharge volume.
- **`gravity_storage_energy_mwh`** (MWh) — blocks `capex_gravity_storage`. A
  retype of `gravity_storage_capacity` to MWh is **not** an acceptable substitute:
  it breaks the shipped `gravity_storage_capacity_bound` (measured, finding 4).
- **`capacity_factor_gas_ocgt`** (1, 0.3 per the archived IEA/NEA text), a
  `fuel_cost_gas_ocgt` (USD/MWh) and an `emission_factor_gas_ocgt_t_per_mwh` —
  needed before any OCGT LCOE can ship, because the shipped form prices fuel and
  carbon per MWh and those three rates are the peaker's, not the CCGT's. This
  pack couples `capex_gas_ocgt` with a bound instead and states why.
- **`sensitivity`** and a hazard term with a unit — blocks `physical_risk_score`
  and `parametric_trigger_threshold`. The graph's whole hazard family
  (`drought_risk`, `flood_risk`, `wildfire_risk`, `landslide_risk`,
  `cold_snap_frequency`, `heatwave_frequency`, `extreme_weather_events`,
  `drought_frequency`, `drought_severity`) is `unit: None` with the 500000.0
  placeholder — **nine placeholders in one family**, which is a batch of its own.
- **`realised_capital_gain_usd_per_year`** — blocks `capital_gains_tax`;
  concurring with *macro-fiscal.md*, which already names it.
- **A PUE and an IT load in MW** — blocks `data_centre_demand`.
- **The digital divide's price and skill components** — blocks
  `digital_divide_metrics`. `internet_penetration` supplies connectivity alone.

One dependency runs the other way: `eligible_own_funds_usd_million` reads
`solvency_capital`, which `solvency_capital_definition` derives as
`pml_99_5_usd_million - aal_usd_million`. Both operands are `free` with defaults,
so the chain is computable at defaults and is checked here; a scenario that sets
either will move the funds.

## Rejected

Approaches considered for the slice as a whole and not taken.

- **A product for every QUALITATIVE node.** The 34 rows have no base. A protocol
  stack times a revenue is a number with no meaning, and the class exists
  precisely so that this is recorded rather than manufactured.
- **Multiplying the five loss-mitigation booleans into the quantities they are
  named after.** The tree has precedent for bool-in-product, but each precedent
  gates an existing number; here the candidates are absent or wrong-shaped (no
  distributed-generation capacity, no phase-imbalance node, no
  unserved-energy-with-dispatch-off quantity, no reconfiguration saving, no
  voltage-dependent loss curve — and the two loss *totals* that do exist are
  totals, not savings). A switch times an absent base is a hidden branch over
  nothing; a switch times a total asserts the total vanishes when the feature is
  off.
- **Restating the solvency floor as an equation.** Measured: at
  `solvency_capital_ratio = 0.9` the shipped rule and the bound both fire, so one
  breach is reported twice and the equation adds a violation the rule already
  blocks on.
- **An OCGT LCOE.** Measured: the shipped form prices fuel and carbon as flat
  per-MWh terms (`fuel_cost_gas`, `emission_factor_gas_t_per_mwh * carbon_price`)
  rather than through a heat rate, so both belong to the CCGT; swapping only the
  capex and the capacity factor would rank the peaker cheaper at 0.6 (78.39
  against 87.82) and dearer at the archived 0.3 (96.77). The crossing sits at
  0.3965 and nothing in the form knows which side of it a plant is on. A peaker
  LCOE needs its own fuel cost, emission factor and capacity factor.
- **`physical_risk_score = exposure_index * (1 - adaptive_capacity)`.** The same
  claim *threshold-product-remainder.md* refused as `vulnerability_index = 1 -
  adaptive_capacity`, under a third id. Vulnerability is a composite of exposure,
  sensitivity and adaptive capacity; the complement of one term is not it.
- **Retyping `opex_fixed_wind` to derived.** It would drop the default to fix a
  consumer that no longer exists, and it would leave a generic node whose only
  defensible content is the onshore value it duplicates.
- **Deleting `opex_fixed_wind` outright.** Correct in the end, but a pack cannot
  delete and a deprecation is reviewable; the node is classified DEPRECATED with
  its successor named so the removal is a decision someone can see.
- **Retyping `liability_exposure`, `business_interruption` and
  `catastrophe_modelling` to currency.** All three carry `unit: 1` for
  firm-specific monetary quantities and the 500000.0 placeholder. Unlike
  `accumulation_risk` there is no rhs operand to bound them against, so the
  retype would be unforced — and an unforced unit change on a FIRM-SPECIFIC node
  is a guess about what the firm's book contains.
- **Reading `transport_logistics` as a mining or agricultural base.** It is the
  national freight total; a share applied to it attributes all road and rail
  haul to one sector.
- **Reading `agricultural_demand_twh` as the base for
  `agricultural_machinery`.** It is the sector's total electricity demand
  (`agricultural_demand_share * base_demand_twh`), so the machinery share would
  be applied to a quantity that already contains its own output.

## Sources to fetch

Cited in prose above but not held locally, so no equation in this pack may lean
on them until a copy is archived and a row added to `sources/INDEX.md`:

- **A marine-energy cost study (IRENA or IEA-OES) that prices OTEC and tidal.**
  The two marine capex *rates* are the graph's own stochastic placeholders —
  `capex_marine_otec`'s description says "no commercial OTEC plant exists … the
  parameter is a speculative number" — and no archived work states either band.
  The products this pack proposes are unit conversions and need no source; the
  rates they multiply do, and *supply-emissions-grid.md* records the same gap.
- **A gravity-storage cost study.** `capex_gravity_storage`'s range is "inferred
  from the pilot installations, not from a cost curve" by its own description.
  The archived *Lazard LCOS v7* covers mechanical storage methods but the pack
  could not verify it prints a gravity-specific USD/kWh band, so it is not cited.
- **Solvency II Directive 2009/138/EC, Art. 100 and the delegated regulation's
  eligible-own-funds rules.** `solvency_capital_ratio`'s 1.0 floor and 1.5–2.0
  market target come from the prudential regime, and the archived corpus holds
  no insurance regulation. The equality this pack proposes is definitional and
  needs no source; the floor's provenance still does.
- **An insurance accumulation/aggregate-exposure standard (a regulator's
  catastrophe-exposure return, or a reinsurer's accumulation definition).** The
  coherence bound needs no source, but `accumulation_risk`'s meaning — total
  exposure to a single event, by peril and by zone — is a defined regulatory
  object and the graph states it in one sentence.
- **A digital-divide index construction (ITU or a national regulator's
  connectivity index).** `digital_divide_metrics` describes a composite of
  connectivity, price and skill and the graph holds only connectivity; no
  archived work states the weights.
- **The five IEA/NEA gaps this slice leans on indirectly** — the OCGT/CCGT
  ordering *is* archived (`iea_nea_egc_2020.pdf`, Table 3.2a/3.2b and the
  peaker/mid-merit text at "gas-fired OCGTs are typically peak load plants"), so
  the bound's citation resolves; nothing further is required for it.
