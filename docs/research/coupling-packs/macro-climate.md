# Coupling pack: macro, climate, adaptation, geopolitical, land, spatial and scenario

The slice is 105 nodes: `macro`, `climate`, `adaptation`, `geopolitical`,
`environmental-social`, `land`, `spatial`, `temporal` and scenario-combination
families. **21 nodes get a proposal** (7 equations); **84 do not**, and the
reasons are specific in each row.

| class | nodes | of which proposed |
|---|---:|---:|
| PRODUCT | 18 | 18 (5 `derive`, 13 `read`) |
| THRESHOLD | 3 | 3 (all `read`) |
| SCENE-SWITCH | 24 | 0 |
| QUALITATIVE | 18 | 0 |
| BASE-NEEDED | 42 | 0 |
| **total** | **105** | **21** |

`kind` is `derive` (the node becomes an `lhs`), `read` (the node becomes an
`rhs` operand of a named new equation) or `defer` (no proposal). The three
THRESHOLD nodes are `read`: they are operands of the two inequalities, and an
inequality's operands are read rather than derived. No node in this pack is
proposed as an `lhs` of an inequality, because the DSL's `solve_affine` path is
the one a batch should lean on and a `leq` target is a bound, not a value.

## What the verification found, before the rows

**1. The entire slice has zero equation readers.** Not one of the 105 ids
appears in any shipped equation's `parameters`, as a target or as an operand.
Every row below is a first coupling, and none of them can collide with an
existing one.

**2. 97 of 105 carry the catalog placeholder signature** — `unit: None`,
`range: [0, 1e6]`, `default: 500000.0`. That includes `temperature_increase`
(a warming of half a million degrees), `sea_level_rise`, `cvar_alpha` (a tail
probability of 500,000) and all six pollutant nodes. The eight that are typed
are `adaptive_capacity`, `ecosystem_services_index`, `energy_security_index`,
`exposure_index`, `geopolitical_risk_index`, `grievance_redress_effectiveness`,
`resilience_score` and `supply_chain_concentration`.

**3. Three large closures are unavailable and the pack says so rather than
stretching an identity.** The macro block needs a GDP denominator the graph
does not carry (`gdp_usd_per_year` is absent, so `balance_of_payments`,
`current_account_balance`, `external_debt`, `debt_sustainability`,
`foreign_direct_investment`, `official_development_assistance`,
`foreign_exchange_reserves` and `remittance_dependency` all defer). The
pollutant block needs per-fuel generation (`generation_coal`, `generation_gas`
and any `generation_by_fuel` are absent) *and* species-specific factors — the
eight `emission_factor_*_t_per_mwh` nodes that exist are all CO₂. The
adaptation block needs a damage function or a cost curve, and neither exists.

**4. `composite_governance_index` is derived and had zero readers.** The
geopolitical composite below is its first consumer. That matters for the batch:
setting `composite_governance_index` directly does nothing, because `propagate`
recomputes it from its five governance dials.

**5. A cross-validation rule fires on a legal corner of the input box once the
composites are derived.** `index_above_unity` is an `error`-severity rule
written for a *set* index. With all eight hazard dials at 1.0 — each inside its
own declared range — `exposure_index` derives to exactly 1.0 and the rule
fires. Measured below. This is a consequence of the coupling, not a defect in
it, and the batch must decide whether the rule is re-scoped or the derived
composites are exempted.

**6. `check_scenario.consistent` does not include cross-validation blocking.**
The field is `not blocking` over *equation* violations only; the cross-validation
report is a separate field and the CLI reads both. An API caller that reads
`consistent` alone will call a blocking scenario consistent. Measured:
`supply_chain_concentration = 9500` gives `consistent=True` with
`concentration_above_hhi_max [error]` in `cross_validation.violations`.

## A note on the citation column

Two proposed equations have no archived source for their construction, and
the pack says so rather than inventing one. `geopolitical_risk_index` and
`exposure_index` are unweighted means of declared dials; no archived work
states *this* aggregation, and the provenance the catalog gives their
components (World Bank WGI, ND-GAIN) is not in `sources/archive/`. Both carry
`reference: None` and both appear under **Sources to fetch**. The five
remaining equations cite either the catalog's own duplicate-row resolution or
Tejada-Arango (2023); both resolve against `sources/INDEX.md` (verified with
`citation_report`, zero failures on the five).

## PRODUCT

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `geopolitical_risk_index` | PRODUCT | derive | `1` (was `None`) | `[0,1]`, unchanged — an unweighted mean of six `[0,1]` dials is in `[0,1]` | `derived` / `fixed` | `geopolitical_risk_index = (1 - political_stability + cross_border_tension + 1 - maritime_security + cyber_threat_level + terrorism_risk + civil_unrest_risk) / 6` | Composite of political, security and diplomatic risk. `political_stability` and `maritime_security` are scored higher-is-better, so both enter inverted; the other four are already risk-scaled. Unweighted because the graph carries no weights and a reader can check an unweighted mean from its components. | `None` — definitional composite; component provenance unarchived (see Sources to fetch) | Weighting by a `[0,1]` severity vector — no such vector is declared, and inventing one is the operand-invention failure. Including `energy_security_index` — it is a separate composite with its own three components and the catalog does not nest it. |
| `exposure_index` | PRODUCT | derive | `1`, unchanged | `[0,1]`, unchanged — mean of eight `[0,1]` hazards | `derived` / `fixed` | `exposure_index = (flood_risk + coastal_erosion + drought_risk + heat_stress + wildfire_risk + landslide_risk + storm_surge + glacial_lake_outburst) / 8` | Share of the eight declared climate hazards that are present, on average. Every hazard is a `[0,1]` intensity, so the mean is the expected hazard loading and needs no normalising constant. | `None` — definitional composite; ND-GAIN provenance unarchived | A maximum over hazards (a site is exposed if *any* hazard bites) — `max` has no derivative rule and `gradients()` raises. A product of complements (`1 - Π(1-hᵢ)`) — a power with a symbolic exponent, which the unit walker cannot decide. |
| `land_availability` | PRODUCT | derive | `hectare` (was `None`) | `[0,500000]` — the exact range of its driver, so the alias cannot narrow the image | `derived` / `physical` | `land_availability = available_land_hectares` | Alias. The catalog declares both `land_availability` and `available_land_hectares`; the latter is derived as `land_availability_fraction * land_area_hectares` and is the one the land block reads. Keeping the second id as a free placeholder would let a scenario set a land availability that the project's own take contradicts. | `The catalog's own duplicate rows, resolved` — `sources/INDEX.md` row `catalog_duplicate_resolutions` | Retiring `land_availability` as `deprecated_by` — a deprecated id cannot be an equation target and 0 equations read it today, so deprecation is available and is the cleaner long-run choice; rejected here only because the slice's mandate is to couple, not to retire, and the batch owner should make the retirement call with the whole land block in view. |
| `land_aggregation` | PRODUCT | derive | `parcels` (was `None`) | `[0,2500000]` — the exact range of `parcels_to_assemble` | `derived` / `fixed` | `land_aggregation = parcels_to_assemble` | Alias onto the transaction count the assembly programme has to clear (`land_aggregation_fragmentation * land_area_hectares / 100`, 1,000 parcels at defaults). Same duplicate-row argument as `land_availability`. | `The catalog's own duplicate rows, resolved` — `catalog_duplicate_resolutions` | Same as above. |
| `snapshot_weightings` | PRODUCT | derive | `hours` (was `None`) | `[0,876000]` — `time_horizon ≤ 100` years × 8,760 h, divided by `representative_snapshots ≥ 1` | `derived` / `fixed` | `snapshot_weightings = time_horizon * 8760 / representative_snapshots` | Hours each representative snapshot stands for: the horizon's hours divided by the number of snapshots. At defaults 25 × 8,760 / 1,200 = 182.5 h, and 182.5 × 1,200 = 219,000 h = 25 years, so the weights sum to the horizon by construction. | `Tejada-Arango (2023), arXiv:2307.16842` — `sources/archive/tejada_multiyear_investment_2023.html` | `1 / representative_snapshots` (a pure share) — dimensionless, so the unit walker cannot reconcile it with an hours-denominated weight and the horizon drops out of the accounting. Deriving it from `representative_days` — the days are already collapsed into `representative_snapshots`; reading both double-counts the sampling. |
| `cross_border_tension` | PRODUCT | read | `1` (was `None`) | `[0,1]` — a normalised index, and the composite divides by 6 | `free` / `fixed` | `--` (operand of `geopolitical_risk_index_definition`) | Risk-scaled already: higher is more tension. | same equation | — |
| `maritime_security` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | **Stated assumption:** scored higher-is-safer, so the composite inverts it. `docs/params.md` 22.18 gives no polarity; the inversion is the pack's reading of the name, not a sourced fact. If the batch's owner reads it as higher-is-riskier, drop the `1 -`. | same equation | Un-inverted — would score a well-policed sea as riskier, which inverts the quantity's meaning. |
| `cyber_threat_level` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | Threat level: higher is worse, not inverted. | same equation | — |
| `terrorism_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | Risk: higher is worse, not inverted. | same equation | — |
| `civil_unrest_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | Risk: higher is worse, not inverted. | same equation | — |
| `flood_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` (operand of `exposure_index_definition`) | Normalised hazard intensity, 0 absent and 1 at the top of the scale. | same equation | — |
| `coastal_erosion` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `drought_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `heat_stress` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `wildfire_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `landslide_risk` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `storm_surge` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |
| `glacial_lake_outburst` | PRODUCT | read | `1` (was `None`) | `[0,1]` | `free` / `fixed` | `--` | as above | same equation | — |

## THRESHOLD

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `temperature_increase` | THRESHOLD | read | `degC` (was `None`) | `[0,6]` — AR6 end-century warming under SSP5-8.5 is ~3.3–5.7 °C above 1850–1900; 6 is headroom. Lower bound 0 refuses a negative warming, which no scenario produces. | `free` / `fixed`, default 1.2 | `temperature_increase <= temperature_target` | Warming the scenario assumes, in °C above the pre-industrial baseline. Default 1.2 places a default run at roughly the present level rather than at a century-end projection. | `None` — definitional inequality between two declared quantities | A `[0,4]` upper bound — excludes the SSP5-8.5 upper end and would refuse a legal scenario. |
| `temperature_target` | THRESHOLD | read | `degC` (was `None`) | `[1,3]` — must contain 1.5 and 2.0 (Paris), 3 admits a weak target | `free` / `policy`, default 1.5 | same inequality | Policy warming ceiling. | `None` | A `[0,1e6]` placeholder — admits a target of 500,000 °C, which no scenario can violate, so the inequality would never bind. |
| `rolling_horizon_window` | THRESHOLD | read | `years` (was `None`) | `[1,100]` — a look-ahead of at least one year; 100 matches `time_horizon`'s own bound | `free` / `fixed`, default 5.0 | `rolling_horizon_window <= time_horizon` | Years of look-ahead in the rolling-horizon solve. A window longer than the modelled horizon reads beyond the data and is refused. | `None` | A `≤ 1` share — the quantity is a duration, not a fraction. |

## SCENE-SWITCH

These select *how* a run is constructed. None is a number, and the graph has no
enum-typed node to hold one; a coupling would have to invent a categorical base.
They close when a categorical node type ships, not when an equation does.

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `clustering_method` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Selects the clustering algorithm; no numeric identity. | — | Any numeric mapping — would invent an ordinal scale for a nominal choice. |
| `custom_gis_boundary` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | A geometry, not a scalar. | — | — |
| `distribution_detail` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Level of distribution-network detail. | — | — |
| `efficient_frontier` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Whether to trace a frontier; a method flag. | — | — |
| `foresight` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Perfect vs myopic foresight. | — | — |
| `fuel_price_scenario` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Selects a price path; the path itself is data the graph does not carry. | — | Deriving from `fuel_price_usd_per_mwh` — that is the level, not the scenario selector. |
| `human_review` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Review flag on the scenario. | — | — |
| `near_duplicate_detection` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Method flag. | — | — |
| `parameter_overrides` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | A mapping, not a scalar. | — | — |
| `scenario_description` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Free text. | — | — |
| `scenario_owner` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Identity. | — | — |
| `scenario_tag` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Label. | — | — |
| `scenario_template` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Template selector. | — | — |
| `scenario_visibility` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Access control. | — | — |
| `signal_extraction` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Method flag. | — | — |
| `signal_scoring` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Method flag. | — | — |
| `spatial_clustering` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Method flag. | — | — |
| `spatial_resolution` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | A grid resolution in km; the graph carries no `km2`-per-cell base and the quantity is a construction choice, not a derived one. | — | Deriving from `land_area_hectares` — resolution is not a function of the study area. |
| `ssp_pathway` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | A categorical SSP selector. `temperature_increase` is the numeric consequence and is read by the threshold instead. | — | Deriving `temperature_increase` from `ssp_pathway` — needs a mapping table the graph does not carry, and inventing one is the operand-invention failure. |
| `stochastic_scenarios` | SCENE-SWITCH | defer | — | — | `free` / `stochastic` | `--` | Scenario count / mode. | — | — |
| `temporal_aggregation` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Aggregation method. | — | — |
| `temporal_clustering` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Method flag. | — | — |
| `temporal_resolution` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Step size; a construction choice. | — | Deriving from `representative_snapshots` — that is the *count*, not the step. |
| `transmission_detail` | SCENE-SWITCH | defer | — | — | `free` / `fixed` | `--` | Level of network detail. | — | — |

## QUALITATIVE

Non-numeric governance and safeguard constructs. A number here would be a
judgement with no unit and no source, and the graph has no ordinal node to hold
one. The one governance quantity that *is* numeric, `grievance_redress_effectiveness`,
is in BASE-NEEDED because it has a declared unit and share range but no
operand to derive it from.

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `buffer_zones` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A siting practice. The hectare quantity that would make it numeric is `protected_areas`, which is already derived from its own equation. | — | Deriving from `protected_areas` — that would make a practice flag an alias of a land area. |
| `conservation_easements` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A legal instrument. | — | — |
| `cumulative_impact_assessment` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A process requirement (CIA). | — | — |
| `emergency_preparedness` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A preparedness programme. | — | — |
| `equator_principles` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | Adoption of a framework; a boolean in substance. | — | — |
| `gender_impact` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A qualitative assessment dimension. | — | — |
| `grievance_redress_mechanism` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | The mechanism exists or not; `grievance_redress_effectiveness` is its measured share. | — | — |
| `ilo_conventions` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | Ratification status. | — | — |
| `land_rights` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | Tenure security; no scale. | — | — |
| `land_tenure` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | as above | — | — |
| `land_use_planning` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A planning regime. | — | — |
| `resilience_metrics` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A metrics *selection*. `resilience_score` is the scored result and is BASE-NEEDED. | — | — |
| `risk_transfer_mechanisms` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | Insurance/transfer instruments; the cost side is `insurance_premium_usd_per_kw_year`, already derived. | — | Deriving from `insurance_premium_usd_per_kw_year` — a mechanism's existence is not a premium. |
| `stakeholder_engagement_plan` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A plan document. | — | — |
| `trade_flow_parameters` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A parameter *set* for a trade model, not a scalar. | — | — |
| `traditional_land_use` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | A land-use classification. | — | — |
| `worker_grievance_mechanism` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | as `grievance_redress_mechanism` | — | — |
| `world_bank_esf` | QUALITATIVE | defer | — | — | `free` / `fixed` | `--` | Adoption of a framework. | — | — |

## BASE-NEEDED

Each row names the missing operand that blocks it. None of these operands is
invented; where the operand belongs to another slice it is also listed under
**Dependencies**.

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected alternative |
|---|---|---|---|---|---|---|---|---|---|
| `adaptation_benefits` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs avoided-damage: no damage function, no `damage` node, no `compliance_cost`. A benefit-cost form needs both sides and only one is declarable. | — | `adaptation_benefits = adaptation_costs` — asserts a benefit-cost ratio of exactly 1 for every project. |
| `adaptation_costs` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs a measure count × unit cost. `adaptation_measures` has no unit, so the product is undecidable. | — | `adaptation_costs = capex_usd_per_kw * capacity_mw` — attributes all capex to adaptation. |
| `adaptation_measures` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A count of measures; needs `unit: 1` and a per-measure cost base, neither declared. | — | — |
| `adaptive_capacity` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | ND-GAIN defines it over institutional, financial and technical sub-indices; the graph carries `composite_governance_index` (institutional) but no financial or technical capacity dial. Deriving from governance alone would rename one component as the whole. | — | `adaptive_capacity = composite_governance_index` — a one-third proxy presented as a composite. |
| `balance_of_payments` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs `gdp_usd_per_year`; absent. Also deferred by the macro-fiscal pack on the same ground. | — | Any ratio against a denominator the graph does not carry. |
| `climate_sensitivity` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Equilibrium climate sensitivity in °C per doubling of CO₂. Needs a radiative-forcing chain (`co2_concentration`, forcing, feedback parameters); none exists. | — | `climate_sensitivity = temperature_increase` — conflates a physical parameter with a scenario outcome. |
| `co_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs an emission factor × activity. No per-fuel generation and no species factor. See the emissions-family note below. | — | Any invented factor. |
| `cold_snap_frequency` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A frequency in events/year needs a weather series or a return-period base; neither exists. | — | Deriving from `extreme_weather_events` — that node is itself a placeholder with no base. |
| `country_risk_rating` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | The catalog's edge is `country_risk_rating → sovereign_risk_premium`, and it is unimplemented: `sovereign_risk_premium` is free with default 0.0256 and a Damodaran citation. Making it derived needs a rating→spread table, which the graph does not carry. The inverse direction (premium → rating) is available and is proposed under Findings as a candidate for the batch, not taken here because the catalog states the arrow the other way. | — | `country_risk_rating = sovereign_risk_premium` — a spread in `1/year` is not a rating, and the arrow would be reversed. |
| `critical_mineral_dependencies` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs import shares by mineral. `supply_chain_concentration` is an HHI over suppliers generally, not a mineral basket. | — | Reusing the HHI — measures supplier concentration, not import dependence. |
| `current_account_balance` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs `gdp_usd_per_year`; absent. | — | — |
| `cvar_alpha` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A tail probability in `(0,1)`; `cvar_value` is absent, so nothing consumes it. Retype to `1` `[0.01,0.5]` is still worth doing — a tail level of 500,000 is not a probability. | — | Deriving it — a risk preference is an input, not a derived quantity. |
| `cvar_omega` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A risk-aversion weight; same missing `cvar_value`. | — | — |
| `debt_sustainability` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs debt and GDP. `external_debt` exists as a placeholder with no unit; both are blocked by the same missing denominator. | — | — |
| `ecosystem_services_index` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Typed `1` `[0,1]`, default 0.7, but its components (provisioning, regulating, cultural service sub-indices) are not declared. | — | — |
| `energy_security_index` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Its own description names three components: `import_dependency` (exists, derived), `fuel_diversity_index` (exists, derived) and *infrastructure adequacy* (absent — no `infrastructure_adequacy` node). Two of three is a composite with a hole. | — | A two-component mean renamed as the three-component index. |
| `exchange_rate_usd_local` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A price, not a derived quantity; also deferred by the macro-fiscal pack. | — | — |
| `exchange_rate_volatility` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs a rate series; the graph carries no timeseries. | — | — |
| `export_competitiveness` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs a real effective exchange rate and unit labour costs; neither exists. | — | — |
| `external_debt` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs `gdp_usd_per_year`. | — | — |
| `extreme_weather_events` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A frequency in events/year. The eight hazard dials in `exposure_index` are intensities, not event counts, and none is derived from this node. | — | Averaging the hazard dials into a frequency — a dimensionless intensity is not an events/year rate. |
| `foreign_direct_investment` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs `gdp_usd_per_year`. | — | — |
| `foreign_exchange_reserves` | BASE-NEEDED | defer | `--` | — | `free` / `fixed` | `--` | Needs months-of-imports cover, hence an import bill. | — | — |
| `grievance_redress_effectiveness` | BASE-NEEDED | defer | `1` `[0,1]`, default 0.75 | — | `free` / `policy` | `--` | Already typed as a share. Deriving it needs grievances-filed and grievances-resolved counts, neither declared. | — | — |
| `health_impact_morbidity` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Illness cases. The catalog's six-pollutant edge set targets it, but `health_impact_mortality` is already derived by `health_impact_mortality_definition` (= `premature_deaths_per_year`); a morbidity equation would need a second lhs and a concentration–response function. See the emissions note. | — | — |
| `heatwave_frequency` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Events/year; needs a weather series. | — | — |
| `interannual_variability` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A coefficient of variation over a generation series; the series is not in the graph. | — | Deriving from `capacity_factor` — that is a mean, not a variability. |
| `mercury_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | See emissions note. | — | — |
| `nox_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | See emissions note. | — | — |
| `official_development_assistance` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Needs `gdp_usd_per_year`. | — | — |
| `pm10_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | See emissions note. | — | — |
| `probability_weight` | BASE-NEEDED | defer | — | — | `free` / `stochastic` | `--` | Scenario weight. A sum-to-unity rule is inexpressible: the cross-validation grammar has no `BinOp`, so no rule can state `Σ wᵢ = 1`. Needs `scenario_count` and a scenario registry, neither declared. | — | A normalisation equation over an unbounded scenario set — the lhs would need a sum over a variable-length collection, which the DSL does not have. |
| `rare_earth_dependencies` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Import shares by rare earth; no mineral basket. | — | — |
| `remittance_dependency` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | The literature's denominator is GDP; the graph has household income but not GDP. The macro-fiscal pack defers it on the same ground and this pack follows rather than re-deriving it against a denominator the literature does not use. | — | `remittance_income_share` over a household-income denominator — measures a different ratio under the same name. |
| `renewable_curtailment_limit` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | A maximum curtailment *share*; the graph has no `curtailment_mwh` or `curtailment_share` node, and `renewable_generation_twh` is a level. Retype to `1` `[0,1]` is still worth doing. | — | — |
| `resilience_investment` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | An investment amount in USD; needs a unit and a budget base. | — | — |
| `resilience_score` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Typed `1` `[0,1]`, default 0.5. Its components (absorptive, adaptive, restorative capacity) are not declared, and `adaptive_capacity` is itself blocked. | — | `resilience_score = adaptive_capacity` — one of three named capacities. |
| `sea_level_rise` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Metres above baseline; needs `unit: m` and a scenario link from `ssp_pathway`/`temperature_increase`, i.e. a mapping table the graph does not carry. | — | Deriving from `temperature_increase` — needs a sea-level response function, which is not a declared node. |
| `sox_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | See emissions note. | — | — |
| `supply_chain_concentration` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | Typed HHI `[0,10000]`, default 2500, and it is an input: an HHI is computed from supplier shares, which the graph does not carry. | — | Deriving it from `market_concentration` — that is the same index for a different market, not a source. |
| `voc_emissions` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | See emissions note. | — | — |
| `water_pollution_load` | BASE-NEEDED | defer | — | — | `free` / `fixed` | `--` | The catalog routes it to `water_quality_impact → compliance_cost`. `water_quality_impact` exists and is derived as `1.0 - water_quality_index`; `compliance_cost` is absent. The missing link is the load→quality function (a load in `t/year` against a receiving-water assimilative capacity), not the downstream chain. | — | `water_quality_impact = water_pollution_load` — a dimensionless index is not a load in `t/year`, and the units do not reconcile. |

### The emissions-species family

The brief asks specifically whether an intensity × activity identity is
available for CO, NOx, SOx, VOC, PM10 and mercury. **It is not.**

The graph does carry emission factors, and the pack checked rather than
assumed: `emission_factor_coal_t_per_mwh` (0.92), `emission_factor_gas_t_per_mwh`
(0.45), `emission_factor_oil_t_per_mwh`, `emission_factor_t_per_mwh` (0.5) and
one each for biomass, geothermal, hydro and nuclear. **Every one of them is CO₂**
— the coal factor's own description reads "CO2 per megawatt-hour for coal" —
and the derived quantities they feed are `emissions_mtco2_per_year` and
`fleet_emission_intensity_t_per_mwh`, both CO₂.

So the identity `species_emissions = species_factor × activity` is unavailable
for a different reason than "no factors": the factors exist and are CO₂-only.
Six species would need six factors per fuel, and none of the six exists at any
fuel. That is an emission factor the brief forbids inventing, six times over.

The activity side is also thin. `generation_coal` and `generation_gas` — the
operands the catalog names at 18.2–18.7 — are absent; only total
`generation_twh` exists. So even with a species factor, the per-fuel split would
have to be invented too.

The catalog's own edge set (18.2–18.7) targets `health_impact_mortality`, which
is already derived by `health_impact_mortality_definition` (=
`premature_deaths_per_year`). So even with factors, the edge would need a
*second* lhs — a morbidity or damage node — that does not exist.
`health_impact_morbidity` is the natural target and is itself a placeholder.

**No emission factor is proposed.**

### The adaptation family

The brief asks whether adaptation admits a benefit-cost or damage-function form
over shipped exposure and value bases. **It does not.**

The benefit side needs avoided damage: `damage`, `damage_function` and
`compliance_cost` are all absent. The cost side needs a measure count times a
unit cost, and `adaptation_measures` has neither a unit nor a per-measure cost
base. `exposure_index` (proposed above) is the exposure *share*, not a damage
value: it is dimensionless, so no product of it with a currency quantity yields
a benefit without a vulnerability coefficient and a value at risk, neither
declared.

The one adaptation quantity that is genuinely close is `resilience_score`, and
it too names three sub-capacities that are not declared. It stays BASE-NEEDED.

## Proposals

### New nodes

**None.** Every `lhs` above is an existing node id. No equation in this pack
introduces an id, which is the strongest form of the symbol check.

### Retypes

| node | was | becomes | reason |
|---|---|---|---|
| `geopolitical_risk_index` | `None`, `[0,1e6]`, 500000.0, free | `1`, `[0,1]`, no default, derived/fixed | becomes an lhs; a derived node carries no default. Range already `[0,1]`. |
| `exposure_index` | `None` unit, `[0,1]`, 0.5, free | `1`, `[0,1]`, no default, derived/fixed | as above |
| `land_availability` | `None`, `[0,1e6]`, 500000.0, free | `hectare`, `[0,500000]`, no default, derived/physical | aliases `available_land_hectares`; the range must equal the driver's or the alias narrows its image |
| `land_aggregation` | `None`, `[0,1e6]`, 500000.0, free | `parcels`, `[0,2500000]`, no default, derived/fixed | aliases `parcels_to_assemble` |
| `snapshot_weightings` | `None`, `[0,1e6]`, 500000.0, free | `hours`, `[0,876000]`, no default, derived/fixed | becomes an lhs |
| `representative_snapshots` | `1`, `[0,9600]`, derived | `1`, `[1,9600]`, derived | **prerequisite**: a zero denominator is a pole. Outside this slice (Temporal) — see Dependencies. |
| `representative_days` | `days`, `[0,100]`, 50.0, exogenous | `days`, `[1,100]`, 50.0, exogenous | **prerequisite**: the pole is `representative_days = 0`, which reaches `snapshot_weightings` through `representative_snapshots`; only the day bound converts the pole into a clean `GraphError`. Outside this slice. |
| `cross_border_tension` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | index component |
| `maritime_security` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | index component |
| `cyber_threat_level` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | index component |
| `terrorism_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | index component |
| `civil_unrest_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | index component |
| `flood_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `coastal_erosion` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `drought_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `heat_stress` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `wildfire_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `landslide_risk` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `storm_surge` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `glacial_lake_outburst` | `None`, `[0,1e6]`, 500000.0 | `1`, `[0,1]`, 0.5 | hazard component |
| `temperature_increase` | `None`, `[0,1e6]`, 500000.0 | `degC`, `[0,6]`, 1.2 | threshold operand |
| `temperature_target` | `None`, `[0,1e6]`, 500000.0, policy | `degC`, `[1,3]`, 1.5, policy | threshold operand |
| `rolling_horizon_window` | `None`, `[0,1e6]`, 500000.0 | `years`, `[1,100]`, 5.0 | threshold operand |

### PRODUCT equations

| id | system | equation | relation | solution | citation |
|---|---|---|---|---|---|
| `geopolitical_risk_index_definition` | `financial` | `geopolitical_risk_index = (1 - political_stability + cross_border_tension + 1 - maritime_security + cyber_threat_level + terrorism_risk + civil_unrest_risk) / 6` | `eq` | direct | `None` |
| `exposure_index_definition` | `reliability` | `exposure_index = (flood_risk + coastal_erosion + drought_risk + heat_stress + wildfire_risk + landslide_risk + storm_surge + glacial_lake_outburst) / 8` | `eq` | direct | `None` |
| `land_availability_alias` | `demand_supply` | `land_availability = available_land_hectares` | `eq` | direct | `The catalog's own duplicate rows, resolved` |
| `land_aggregation_alias` | `cost_accounting` | `land_aggregation = parcels_to_assemble` | `eq` | direct | `The catalog's own duplicate rows, resolved` |
| `snapshot_weightings_definition` | `energy_balance` | `snapshot_weightings = time_horizon * 8760 / representative_snapshots` | `eq` | direct | `Tejada-Arango (2023), arXiv:2307.16842` |

### THRESHOLD equations

| id | system | equation | relation | solution | citation |
|---|---|---|---|---|---|
| `temperature_target_bound` | `carbon_trajectory` | `temperature_increase <= temperature_target` | `leq` | numeric | `None` |
| `rolling_horizon_window_bound` | `demand_supply` | `rolling_horizon_window <= time_horizon` | `leq` | numeric | `None` |

## Verification

Every number below was measured on a graph built from the shipped
`config/prg.yaml` plus the retypes and equations above, via
`ParameterGraph.from_mapping`. The shipped file was not modified.

```
baseline : 1344 nodes 525 eqs 1075 edges 284 uncoupled
proposed : 1344 nodes 532 eqs 1075 edges 263 uncoupled

closed 21 : civil_unrest_risk, coastal_erosion, cross_border_tension,
  cyber_threat_level, drought_risk, exposure_index, flood_risk,
  geopolitical_risk_index, glacial_lake_outburst, heat_stress,
  land_aggregation, land_availability, landslide_risk, maritime_security,
  rolling_horizon_window, snapshot_weightings, storm_surge, temperature_increase,
  temperature_target, terrorism_risk, wildfire_risk

symbols_ok: True        (every rhs symbol is a declared node; no lhs on any rhs)
unit_ok:    7 / 7       (decidable and consistent)
  geopolitical_risk_index_definition  dimensionless == dimensionless
  exposure_index_definition           dimensionless == dimensionless
  land_availability_alias             [length] ** 2 == [length] ** 2
  land_aggregation_alias              [parcel] == [parcel]
  snapshot_weightings_definition      [time] == [time]
  temperature_target_bound            [temperature] == [temperature]
  rolling_horizon_window_bound        [time] == [time]

excursions: {}          |  violations: 0
routes: 5 unbound (the five equalities read a derived operand)
        2 bound   (temperature_target_bound, rolling_horizon_window_bound)
```

**Values at defaults, as printed by `propagate`:**

```
political_stability         = 0.5      cross_border_tension  = 0.5
maritime_security           = 0.5      cyber_threat_level    = 0.5
terrorism_risk              = 0.5      civil_unrest_risk     = 0.5
geopolitical_risk_index     = 0.5      (the unweighted mean of six 0.5s)

flood_risk                  = 0.5      coastal_erosion       = 0.5
drought_risk                = 0.5      heat_stress           = 0.5
wildfire_risk               = 0.5      landslide_risk        = 0.5
storm_surge                 = 0.5      glacial_lake_outburst = 0.5
exposure_index              = 0.5

land_availability           = 2500.0   available_land_hectares = 2500.0
land_aggregation            = 1000.0   parcels_to_assemble     = 1000.0

time_horizon                = 25.0     representative_days     = 50.0
representative_snapshots    = 1200.0   snapshot_weightings     = 182.5
                                        (25 * 8760 / 1200 = 182.5 h)

rolling_horizon_window      = 5.0      (<= 25.0, holds)
temperature_increase        = 1.2      temperature_target      = 1.5  (holds)
```

**Canaries — each predicate shown in both directions:**

```
geopolitical composite
  political_stability=0.0, cbt=1.0, mar=0.0, cyber=1.0, ter=1.0, civ=1.0  -> 1.0
  political_stability=1.0, cbt=0.0, mar=1.0, cyber=0.0, ter=0.0, civ=0.0  -> 0.0
  political_stability=1.0, cbt=1.0, mar=0.0, cyber=0.0, ter=0.0, civ=0.0  -> 0.333333

exposure composite
  all eight hazards 0.0  -> 0.0
  all eight hazards 0.25 -> 0.25
  all eight hazards 1.0  -> 1.0

temperature_target_bound
  1.2 / 1.5 holds | 1.4 / 1.5 holds | 2.0 / 1.5 VIOLATION residual 0.500000
  1.2 / 1.0 VIOLATION residual 0.200000

rolling_horizon_window_bound
  5.0 holds | 25.0 holds | 26.0 VIOLATION residual 1.000000

snapshot_weightings (the pole test)
  representative_days=1   -> snapshots 24,   weight 9125.0
  representative_days=50  -> snapshots 1200, weight 182.5
  representative_days=100 -> snapshots 2400, weight 91.25
  representative_days=0   -> GraphError: outside the range (1.0, 100.0)
                             declared for it
```

The last line is the prerequisite in action: without the
`representative_days [1,100]` retype, `representative_days = 0` reaches the
division and raises `ZeroDivisionError: zero to a negative power` from inside
`propagate`; with it, the same input is a clean range refusal at the door.

**Citation join**, run through `alea.provenance.citations.citation_report` on
the five non-`None` references: zero failures against `sources/INDEX.md`.

## Dependencies

- **`representative_days` retype `[0,100] → [1,100]`** belongs to the Temporal
  slice, not this one. `snapshot_weightings` is safe at every value the node's
  own range admits *only if* this retype lands; without it the pole is reachable.
  The same applies to `representative_snapshots [0,9600] → [1,9600]`, which is
  in the slice's neighbourhood but is not one of the 105.
- **`time_horizon`** is used as an operand by two proposed equations. It is
  exogenous with default 25.0 and range `[0,100]` years — already read by
  `investment_period_length_definition`, so no retype is needed, but the
  `rolling_horizon_window <= time_horizon` bound is only meaningful while the
  horizon's lower bound is 0: a zero horizon admits a zero window.
- **`available_land_hectares` and `parcels_to_assemble`** are the drivers of the
  two land aliases. Both are already derived by their own equations
  (`available_land_hectares_definition`, `parcels_to_assemble_definition`), so
  the aliases add no new base — but they do make the land block's range
  depend on `land_area_hectares [0,500000]`, which the land slice owns.
- **`political_stability`** is a governance dial owned by the macro slice; the
  geopolitical composite reads it and does not retype it.
- **`composite_governance_index`** is derived and has zero equation readers; the
  geopolitical composite is its first consumer. Not used directly because
  inverting a five-dial mean is not the same as inverting `political_stability`
  alone, and the catalog names `political_stability` as the political parent.

## Rejected

- **A GDP-normalised macro block.** `balance_of_payments`, `current_account_balance`,
  `external_debt`, `debt_sustainability`, `foreign_direct_investment`,
  `official_development_assistance` and `foreign_exchange_reserves` are all
  ratios whose denominator is GDP, and `gdp_usd_per_year` is absent. Deriving
  them against `revenue_usd_per_year` or `household_income_usd_per_year` would
  measure a different ratio under the same name — the exact defect the
  macro-fiscal pack's deferral of `remittance_dependency` avoids.
- **`country_risk_rating = sovereign_risk_premium`.** Available today (both
  nodes exist, the premium is a declared free node), but the catalog's arrow is
  `country_risk_rating → sovereign_risk_premium`, and a `1/year` spread is not
  a rating. Taking it would implement the arrow backwards. Flagged under
  Findings as a candidate the batch may take with the arrow reversed and a
  stated scale.
- **A hazard product `1 - Π(1 - hᵢ)` for `exposure_index`.** Thematically
  better than a mean (exposure is a union, not an average), but a symbolic
  exponent makes the unit walker undecidable and the derivative rule cannot
  carry a product of eight terms cleanly. Recorded so the batch does not
  rediscover the idea and take it.
- **`max(h₁..h₈)` for `exposure_index`.** The most faithful reading of
  "exposure", and refused on the hard constraint: `max` has no derivative rule
  and `gradients()` raises on any equation that uses it.
- **`snapshot_weightings = 1 / representative_snapshots`.** Dimensionless, so
  the walker cannot reconcile it with an hours-denominated weight, and the
  horizon drops out of the accounting entirely.
- **`adaptation_benefits = adaptation_costs * (1 + adaptation_measures / 100)`.**
  Invented: no source, and `adaptation_measures` has no unit so the `/100` is
  a fabricated conversion.
- **Weighting the geopolitical composite by `supply_chain_concentration`.**
  Tempting because the HHI is typed, but the catalog does not nest supply-chain
  concentration in the geopolitical index, and a weight is an operand.

## Sources to fetch

Both are needed before the two `reference: None` composites can carry a
citation. Neither is in `sources/archive/` and neither has a row in
`sources/INDEX.md`.

- **ND-GAIN Country Index — Technical Report** (University of Notre Dame Global
  Adaptation Initiative). The catalog's stated source for `adaptive_capacity`,
  `vulnerability_index` and `exposure_index` components
  (`docs/param_batch3.md`). Needed to justify the hazard set and the unweighted
  mean in `exposure_index_definition`.
- **World Bank Worldwide Governance Indicators — Methodology** (Kaufmann,
  Kraay & Mastruzzi). The catalog's stated source for `geopolitical_risk_index`
  and `composite_governance_index` (`docs/param_batch3.md` line 523). Needed to
  justify the governance component and, more importantly, to establish the
  **polarity** of the security dials — `docs/params.md` 22.17–22.21 gives none,
  which is why `maritime_security`'s inversion is stated as an assumption
  rather than sourced.

Also worth fetching before the batch ships, though not load-bearing for any
equation above:

- **IPCC AR6 WG1, Summary for Policymakers** — for the `[0,6] °C` bound and the
  1.2 °C default on `temperature_increase`, and the 1.5/2.0 °C anchors in
  `temperature_target`'s range. Currently asserted from general knowledge, not
  from an archived document.

## Findings

**1. Eleven shipped equations fail the unit walk.** `check_graph` reports
521 of 532 consistent after this pack's equations are added; the 11 failures
are pre-existing and unchanged:

```
ammonia_export_volume_tonnes_definition   co2_captured_cement_tonnes_definition
co2_captured_industry_tonnes_definition   coal_price_per_mwh_definition
equity_irr_definition                     insurance_premium_definition
line_outage_hours_per_year_definition     mini_grid_programme_spend_definition
premature_deaths_definition               rocof_definition
steel_hydrogen_demand_tonnes_definition
```

`insurance_premium_definition` is inside the slice's neighbourhood (it is the
equation that makes `insurance_premium_usd_per_kw_year` derived) and its
failure means the premium is currently computed without a decidable dimension.

**2. The slice is entirely unread.** Zero of the 105 nodes appear in any
equation's `parameters`. 97 of 105 carry the placeholder signature
(`unit: None`, `[0,1e6]`, `500000.0`). The pack's 21 proposals are the first
coupling for every one of them.

**3. `import_dependency` escapes its own range on any net-exporter scenario,
and the guard that catches it is a per-node rule rather than the arithmetic.**
`import_dependency_definition` is `net_imports_twh / demand_twh`; the node's
range is `(-1,1)` and its description says "in absolute value", but the DSL has
no `abs` and the equation does not use one. Measured:

```
net_imports_twh = -100   -> import_dependency =  -2.148734200844448
net_imports_twh = -1000  -> import_dependency = -21.48734200844448
```

`check_scenario` does report these, as `import_dependency_out_of_range`
(blocking) in `violations` and in `excursions` — the graph is not silent. The
defect is narrower and still real: the description states a bound the equation
does not carry, so the *equation* is wrong about its own sign convention and the
guard has to be re-stated by hand. A net-exporter of 100 TWh/yr is an ordinary
scenario, and it produces an index 2.1 units outside a `(-1,1)` range that its
own prose says cannot happen.

**4. `renewable_generation_twh`'s range cannot hold its own formula's image.**
The node is `[0,50] TWh/year`, derived as `renewable_target * generation_twh`
with `renewable_target ∈ (0,1)` and `generation_twh ∈ (0,30000)`. The image's
supremum is 18,000, which the declared range refuses by a factor of 360. At
defaults the value is 30.93 and the defect is invisible. Measured: pushing
`net_imports_twh` to −30 (a legal value inside its own `(-1000,1000)` range)
raises `generation_twh` and drives `renewable_generation_twh` to **50.4979** —
outside its declared `[0,50]`. `check_scenario` reports
`renewable_generation_twh_out_of_range` (blocking), so the guard fires; the
finding is that the range was declared narrower than the arithmetic's image, and
a modest scenario change reaches it.

**5. The six-pollutant edge set targets an already-derived node.** The catalog
(18.2–18.7) routes CO, NOx, SOx, VOC, PM10 and mercury to
`health_impact_mortality`, which `health_impact_mortality_definition` already
derives as `premature_deaths_per_year`. Implementing the catalog's edges
literally would give that node two determiners. The species block needs a
different target (`health_impact_morbidity`, currently a placeholder) and a
concentration–response function that is not declared.

**6. `country_risk_rating → sovereign_risk_premium` is unimplemented, and the
consequence is visible in the numbers.** `sovereign_risk_premium` is free with
default 0.0256 and a Damodaran citation; `country_risk_rating` is a float
placeholder with zero readers. A scenario cannot currently move the sovereign
premium from a country rating, which is the edge the catalog states.

**7. `energy_security_index` names a component the graph does not have.** Its
description lists "import dependency, fuel diversity and infrastructure
adequacy". `import_dependency` and `fuel_diversity_index` are both declared and
derived; `infrastructure_adequacy` is absent. A two-of-three mean shipped under
the three-component name is the "declared is not produced" class.

**8. The `index_above_unity` cross-validation rule fires on a legal corner
once the composites are derived.** The rule is `> 0.99`, `severity: error`.
With all eight hazard dials at 1.0 — each inside `[0,1]` — `exposure_index`
derives to 1.0 and the rule fires:

```
all hazards 0.5  -> exposure 0.5  xv: []
all hazards 0.99 -> exposure 0.99 xv: ['index_above_unity [error] ...']
all hazards 1.0  -> exposure 1.0  xv: ['index_above_unity [error] ...']
```

`propagate` reports `excursions: {}` and `check_scenario.consistent = True`
throughout; only `cross_validation.blocks` is `True`, and the CLI exits 1 on
it. The rule was written for an index a user *sets*; once it is *derived*, a
legal input vector produces a scenario the CLI refuses. The batch must decide
whether to re-scope the rule or exempt derived composites.

**9. `check_scenario.consistent` ignores cross-validation blocking.** Measured
on the shipped graph with no changes: `supply_chain_concentration = 9500` gives
`consistent = True` with `concentration_above_hhi_max [error]` in
`cross_validation.violations`. The CLI reads both fields and exits 1, but an
API caller that reads `consistent` alone — the field name says what a caller
would check — is told the scenario is fine. The docstring on
`cross_validation.summary` already states the principle ("a summary that
reported only the first would call that consistent"); `consistent` does not
follow it.

**10. Two zero-valued poles sit behind the snapshot machinery.**
`representative_days` is `[0,100]` and `representative_snapshots` is `[0,9600]`;
either at zero reaches `time_horizon * 8760 / representative_snapshots` and
raises `ZeroDivisionError` from inside `propagate`. Measured: retyping
`representative_snapshots` to `[1,9600]` alone does **not** prevent it, because
the product is already zero before the node's range is consulted; only
`representative_days [1,100]` converts the pole into a clean `GraphError`.

**11. A derived node with no reader is a computed quantity nobody uses.**
`composite_governance_index` is one of 22 derived nodes with zero equation
readers (306 of 1,344 nodes overall have no reader). The geopolitical composite
below closes one of those 22. The register is worth a sweep separately.
