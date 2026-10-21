# Coupling pack: the 102 nodes no pack has classified

## What this pack covers

The 102 nodes in `uncoupled()` that appear in none of the five classification
slices. Verified against the tree as it stands: `load_graph()` returns 1338
parameters, 477 equations, 1011 edges and 335 uncoupled; the five packs name 480
nodes; set-differencing the two gives exactly the 102 rows below, and none of the
102 has been coupled by a later batch — the count was re-read after batches 29
and 30 baked (1317/449/961/365) and again after the next batch landed
(1338/477/1011/335), and the slice was unchanged both times. The job is
classification first — a node correctly called QUALITATIVE or a scene switch
stops being work — and a coupling proposal only where the node genuinely has an
equation behind it.

The classification is: **35 QUALITATIVE, 26 BASE-NEEDED, 24 PRODUCT, 10
SCENE-SWITCH, 5 THRESHOLD, 1 GATE-SCENE-SWITCH, 1 DEPRECATED** (a class this
pack names and defines, because none of the existing seven fits). Of the 102,
**29 get a proposal** — 15 `derive`, 9 `read`, 5 `bound` — carrying **26
equations**: 21 equalities and 5 bounds. Fifteen slice nodes become an lhs, and
six of the 21 equalities compute a node this pack declares; the nine `read` rows
are operands of those equations. The other **73 are deferred** and the reason for
each is stated in its row. Three of the deferral classes are structural rather
than temporary: QUALITATIVE is the graph's declared free space, retained by
contract; SCENE-SWITCH and GATE-SCENE-SWITCH are run configurations the solver
reads rather than quantities; and DEPRECATED is a node whose correct coupling is
its removal.

This pack uses the `kind` vocabulary the sibling THRESHOLD pack introduced:
`derive` (the node becomes an lhs of an equality), `read` (the node is an
operand of a named equation), `bound` (the node is the left operand of an
inequality; its role stays `free` and the equation computes no value for it),
and `defer`.

### What the verification found, before the rows

Six things were checked against the tree rather than assumed, and three of them
change a proposal.

1. **`firm_build_fleet_mw` cannot be derived.** Its role is `endogenous`, and
   the loader refuses an endogenous target outright:
   `GraphError: firm_build_fleet_mw is determined by 'firm_build_fleet_definition'
   but its role is 'endogenous'; a parameter an equation fixes is 'derived', and
   any other role lets a user set it and be silently overruled`. It is also the
   only non-`free` node in the slice, and it has **zero equation readers** — a
   field written and never read. Its description claims it is "the identity
   every build set must satisfy" and that "the reserve margins read the firm
   part of it"; neither is true. The identity is `fleet_build_balance` (18 leaf
   technologies, already shipped), and the reserve margins read
   `firm_capacity_mw`, which `firm_capacity_definition` computes from
   `thermal_capacity_mw + dispatchable_re_capacity_mw`, not from this node. The
   only coupling the role permits is a bound, and the row says so.

2. **`electrolyser_capacity` is a build size, and its MW retype has not
   reached `config/prg.yaml`.** `build_batch13`'s `UNBUILT_TECHS` table authors
   `("electrolyser_capacity": ("MW", "unbuilt", "0.0"))`, but the baked node
   still carries `unit=None`, range `[0, 1e6]`, `default=500000.0`. So do
   `fusion_capacity`, `flywheel_capacity`, `small_modular_reactor_capacity` and
   `tidal_range_capacity`. The retype is a prerequisite for the bound in this
   pack and is stated as one.

3. **`demand_growth_rate` is deprecated** (`deprecated_by='demand_growth'`) and
   a deprecated node cannot be an equation target. No class in the seven fits a
   node that is being retired; the pack names DEPRECATED and defines it.

4. **The worklist's claim that "all fifteen policy switches are coupled" is
   false against the graph.** All fifteen still return `True` from
   `uncoupled()`, and none is an lhs or an rhs operand. The worklist is
   conflating *a gate read as an operand of some other node's equation* — true
   of `ets_enabled`, `capacity_market`, `cross_border_trade_allowed` and three
   others — with *the flag itself being coupled*. Ten of the fifteen are in this
   slice and are classified SCENE-SWITCH below.

5. **The three composite indices cannot be derived.** `adaptive_capacity`,
   `resilience_score` and `energy_security_index` each describe themselves as a
   composite over named components, and every component is absent:
   `institutional_capacity`, `financial_capacity` and `technical_capacity` do
   not exist in the graph, nor does `infrastructure_adequacy`. They are
   BASE-NEEDED, not PRODUCT, and no pack currently proposes those four bases.

6. **`solar_pv_capacity` is not a member of `fleet_build_balance`.** Its 18
   members exclude solar, solar thermal and the two aggregates. Any sum written
   from the balance's membership therefore excludes the 10,000 MW solar build,
   which is why the `firm_build_fleet_mw` row below uses the twelve
   `REFERENCE_BUILDS` technologies and states the exclusion.

Every proposed right-hand side was run through the BRIEF's symbol check in one
pass over the table as written: **26 checked, zero unresolved symbols**, once
the six new left-hand-side ids are allowed for. The six new ids were also
confirmed absent from `g.nodes` and from every equation lhs, and the 26 proposed
equation ids from every equation id — **no name collisions**. The whole set was
then loaded into a retyped copy of `config/prg.yaml` (1344 nodes, 503 equations
after the additions) and checked: `check_equation` **26/26 decidable and
consistent**; `propagate` at defaults **no range excursions and zero consistency
violations**; all 21 derived values quoted below are the printed ones, and they
were identical on the batch-29/30 graph (1323/475) and on the tree after the next
batch landed. The five bounds were routed through `constraints._classify`: **2
route `bound`, 3 route `unbound`** (a post-solve audit check, not an LP
constraint).

### A note on the citation column

Fourteen of the 21 `derive` rows carry `reference: None`, which the BRIEF
admits only for definitional identities. That is what they are — eleven aliases
or unit conversions of a quantity the graph already derives, and three products
of a share against a base the graph already carries. This slice is the residue
after the packs that had literature behind them, and pretending otherwise by
attaching a plausible-looking paper to `health_impact_dalys eq dalys_per_year`
would be the more comfortable row and the less honest one. The seven that do
carry an archived citation, and the five bounds, name a work whose text states
the identity; each was read in the local copy, not inferred from its title.

## Classification

All 102 nodes. `kind` is the coupling this pack proposes, or `defer` with the
reason.

### QUALITATIVE (35) — the graph's declared free space

| node | class | kind | reason |
|---|---|---|---|
| `arrears_management` | QUALITATIVE | defer | A collections policy: a procedure, not a quantity. No base in the graph it could multiply. |
| `assignment_rights` | QUALITATIVE | defer | A contract's transferability clause. A legal term; the admissible set is a drafting choice. |
| `bill_shock_protection` | QUALITATIVE | defer | A consumer-protection rule (notice period, payment smoothing). A procedure. |
| `billing_systems` | QUALITATIVE | defer | The billing platform's capability. A system description, not a measurement. |
| `business_interruption` | QUALITATIVE | defer | The node's own description says FIRM-SPECIFIC: scope, waiting period and indemnity period vary by policy. Not correctable to a scalar. |
| `catastrophe_modelling` | QUALITATIVE | defer | The node's own description says this is a cat model's *output* for a specific book — not a parameter. A future batch should split it. |
| `climate_sensitivity` | QUALITATIVE | defer | Equilibrium climate sensitivity is a physical quantity, but the graph carries no forcing or temperature path for it to enter; the climate dials that exist (`temperature_increase`, `temperature_target`) are GATE-SCENE-SWITCH and are separate. |
| `collateral_valuation` | QUALITATIVE | defer | A valuation methodology (haircut schedule, mark model). A choice among methods. |
| `communication_protocols` | QUALITATIVE | defer | The protocol stack (IEC 61850, DNP3, …). A standard's name. |
| `compensation_mechanisms` | QUALITATIVE | defer | The consumer-compensation rule set. A procedure; `compensation_rates` is the quantity and is coupled below. |
| `corsia_parameters` | QUALITATIVE | defer | An aviation offset scheme's rulebook; a treaty choice with no volume base in the graph. |
| `cost_pass_through_mechanism` | QUALITATIVE | defer | Which costs pass through automatically and which go to a review. A rule, not a rate. |
| `cumulative_impact_assessment` | QUALITATIVE | defer | An assessment process and its scope. A procedure. |
| `customer_information_systems` | QUALITATIVE | defer | The CIS capability. A system description. |
| `data_backup_recovery` | QUALITATIVE | defer | A recovery objective (RPO/RTO policy). A procedure. |
| `demand_growth_profile` | QUALITATIVE | defer | "Shape of growth curve" — a curve *family* (linear, S-curve, logistic). The graph carries the rate (`demand_growth`) and the horizon; the shape is a functional form, and no equation can select among forms. |
| `disconnection_protection` | QUALITATIVE | defer | A licence condition on disconnection. A rule. |
| `efficient_frontier` | QUALITATIVE | defer | The frontier itself is a locus, not a number; `efficiency_benchmarking` is the utility's position relative to it and is BASE-NEEDED below. |
| `electrification_timeline` | QUALITATIVE | defer | "Year to reach target" — a scenario schedule. The target it reaches is a separate node; the year is a choice. |
| `emergency_preparedness` | QUALITATIVE | defer | A preparedness programme's scope. A procedure. |
| `environmental_representations` | QUALITATIVE | defer | Contractual representations and warranties. A legal term. |
| `ev_adoption_timeline` | QUALITATIVE | defer | "Year to reach EV share" — the same schedule argument as `electrification_timeline`; `ev_share_new_sales` is the share and is BASE-NEEDED. |
| `maritime_security` | QUALITATIVE | defer | A security posture. No base; no measurement. |
| `payment_plans` | QUALITATIVE | defer | An instalment arrangement. A procedure. |
| `ppa_arbitration_venue` | QUALITATIVE | defer | A seat of arbitration (a city or institution). A legal choice. |
| `ppa_change_in_law` | QUALITATIVE | defer | A change-in-law clause's scope. A legal term. |
| `ppa_governing_law` | QUALITATIVE | defer | A choice of law. A legal term. |
| `ppa_pricing_formula` | QUALITATIVE | defer | Which indexation and escalation formula the PPA uses. A functional-form choice; `ppa_indexation` is the rate and is coupled below. |
| `ppa_take_or_pay` | QUALITATIVE | defer | The take-or-pay clause's threshold. A contractual term. |
| `ppa_termination_payments` | QUALITATIVE | defer | The termination payment schedule. A contractual term. |
| `prepayment_metering` | QUALITATIVE | defer | A metering mode. A configuration. |
| `re_target_carrier` | QUALITATIVE | defer | "Which renewables count" — a categorical eligibility list, not a quantity. A string, not a float. |
| `regulatory_accounts` | QUALITATIVE | defer | The chart of regulatory accounts. A register's structure. |
| `regulatory_asset_valuation_method` | QUALITATIVE | defer | A categorical (0 historical, 1 indexed historical, 2 current cost) smuggled into a float; the node's own description says the type correction is the substantive fix. A label, not a number. |
| `resilience_metrics` | QUALITATIVE | defer | A metric *set*. Which metrics are reported is a choice; `resilience_score` is the scalar and is BASE-NEEDED. |

### BASE-NEEDED (26) — a real product, waiting on a quantity the graph does not carry

| node | class | kind | reason |
|---|---|---|---|
| `adaptation_benefits` | BASE-NEEDED | defer | A benefit stream needs a damage function and an avoided-damage base; neither exists. |
| `adaptation_costs` | BASE-NEEDED | defer | Needs an adaptation-measure cost curve; `adaptation_measures` is itself uncoupled and unquantified. |
| `adaptation_measures` | BASE-NEEDED | defer | A menu of measures, not a quantity. It is the base the other two adaptation nodes wait on, and it has no unit. |
| `adaptive_capacity` | BASE-NEEDED | defer | Its three described components — `institutional_capacity`, `financial_capacity`, `technical_capacity` — are all absent from the graph. **Finding:** no pack proposes any of them. |
| `buffer_zones` | BASE-NEEDED | defer | Needs an area (hectares) and a set-back distance; the graph has `land_area_hectares` but no buffer fraction and no set-back. |
| `critical_mineral_dependencies` | BASE-NEEDED | defer | Needs per-mineral import shares and a weighting; neither exists. `import_dependency` is an energy share, not a mineral one. |
| `data_centre_demand` | BASE-NEEDED | defer | Needs an IT load (MW) or a stock of racks and a PUE. The graph has `peak_demand_mw` but no data-centre load and no PUE. |
| `efficiency_benchmarking` | BASE-NEEDED | defer | Needs a frontier or peer-group efficiency to normalise against; `efficient_frontier` is a locus, not a level, and no operating-cost-per-unit node exists. |
| `energy_security_index` | BASE-NEEDED | defer | Described as a composite of import dependency, fuel diversity and infrastructure adequacy. The first two exist (`import_dependency`, `fuel_diversity_index`); `infrastructure_adequacy` does not, and no weighting scheme is declared. |
| `ev_battery_size` | BASE-NEEDED | defer | A kWh-per-vehicle base is needed; the graph carries no vehicle stock in units and no battery size. `electric_vehicle_adoption` is a share of stock. |
| `ev_efficiency` | BASE-NEEDED | defer | kWh/km per vehicle. Needs both a distance base and a consumption base; neither exists. |
| `ev_share_new_sales` | BASE-NEEDED | defer | A share of a *flow*. The graph carries `electric_vehicle_adoption` (share of the stock) but no new-vehicle sales count, so the flow share cannot be converted to a stock or a load. |
| `health_impact_morbidity` | BASE-NEEDED | defer | Needs an illness-case count; the graph carries `dalys_per_year` and `premature_deaths_per_year` but no morbidity count, and a DALY is not a case. |
| `loss_reduction_investment` | BASE-NEEDED | defer | An investment in loss reduction needs a loss-reduction cost curve; the graph has `transmission_loss_reduction_target` (a share) but no USD per point of reduction. |
| `microgrid_deployment` | BASE-NEEDED | defer | Needs an installed microgrid capacity (MW) or a count of sites; neither exists. |
| `new_entrants` | BASE-NEEDED | defer | A count of new market participants needs a market-entry base; `number_of_generators` exists but a generator is not an entrant. |
| `number_of_retailers` | BASE-NEEDED | defer | A count, but its only natural consumer is a retail HHI, and no market-share vector exists — a count alone cannot give a concentration index. |
| `payment_security_required` | BASE-NEEDED | defer | Needs the exposure it secures (a counterparty obligation). `collateral_posted_usd_per_year` exists but is the posted amount, not the requirement. |
| `ppa_curtailment_compensation` | BASE-NEEDED | defer | Needs a curtailed volume and a compensation rate; no curtailment volume node exists anywhere in the graph. |
| `rare_earth_dependencies` | BASE-NEEDED | defer | As `critical_mineral_dependencies`: no per-material import share and no weighting. |
| `renewable_curtailment_limit` | BASE-NEEDED | defer | A ceiling on curtailment needs a curtailed-energy base, and the graph has none — no `curtailed_twh`, no `curtailment_share`. |
| `resilience_investment` | BASE-NEEDED | defer | Needs a resilience cost curve or a hard-adaptation spend base; neither exists. |
| `resilience_score` | BASE-NEEDED | defer | A composite with no declared components in the graph; `resilience_metrics` is its own unquantified metric set. |
| `retail_competition` | BASE-NEEDED | defer | Needs a retail market-share vector or a switching rate; the graph has neither. |
| `supply_chain_concentration` | BASE-NEEDED | defer | Already an HHI in [0, 10000], but computing one needs per-supplier shares, which do not exist. Its range was already repaired; the value is a judgement. |
| `workshop_capacity` | BASE-NEEDED | defer | A workshop's throughput (units/year) needs a maintenance-workload base; `planned_maintenance_hours_per_year` is hours, not units. |

### PRODUCT (24) — a share against a base, or an alias

| node | class | kind | reason |
|---|---|---|---|
| `accelerated_depreciation` | PRODUCT | derive | Rate per year; alias of the accelerated schedule. |
| `accelerated_depreciation_factor` | PRODUCT | **read** | The multiple of straight-line the code permits; the operand of the accelerated schedule. |
| `buffer_pool_contribution` | PRODUCT | derive | Alias of `permanence_parameters`; the buffer a registry retains. |
| `compensation_rates` | PRODUCT | derive | Share of market value × land cost per hectare. |
| `compensation_share_of_market` | PRODUCT | **read** | The multiple of market value the package offers; the operand of `compensation_rates`. |
| `consumer_price_index_link` | PRODUCT | derive | Alias of `inflation_rate`. |
| `depreciation_schedule_accelerated` | PRODUCT | derive | Factor over asset life. |
| `depreciation_schedule_declining` | PRODUCT | derive | 200% declining balance over asset life. |
| `depreciation_schedule_linear` | PRODUCT | derive | 1 over asset life. |
| `excise_duty_fuel` | PRODUCT | **read** | A share of the retail fuel price; the operand of the excise revenue. |
| `firm_build_fleet_mw` | PRODUCT | **bound** | An aggregate that cannot be an equation target (role `endogenous`); coupled by a containment bound. |
| `gdp_per_capita_growth` | PRODUCT | derive | The Fisher relation between the GDP and population rates. |
| `gis_requirements` | PRODUCT | **read** | The share of network assets in the GIS, 0.6 at defaults; the operand of the mapped route length. The worklist files it BASE-NEEDED for "no asset-count base", and that is wrong: the route-km base exists, so the node has a consumer. |
| `health_impact_dalys` | PRODUCT | derive | Alias of `dalys_per_year`. |
| `health_impact_mortality` | PRODUCT | derive | Alias of `premature_deaths_per_year`. |
| `hydrogen_demand_domestic` | PRODUCT | derive | Production less exports, converted to kt. |
| `hydrogen_production_demand` | PRODUCT | derive | Alias of `electrolysis_electricity_demand_mwh_per_year`. |
| `loss_factor_cross_border` | PRODUCT | **read** | A loss share; the operand of cross-border losses. |
| `opex_variable_electrolyser` | PRODUCT | **read** | USD per MWh of hydrogen; the operand of the electrolyser opex. |
| `ppa_indexation` | PRODUCT | derive | Alias of `tariff_indexation`. |
| `premium_share_of_asset` | PRODUCT | derive | Alias of `insurance_loss_share_of_cost`. |
| `rooftop_solar_adoption` | PRODUCT | **read** | A share of suitable rooftops; the operand of the household count. |
| `value_of_lost_load` | PRODUCT | derive | Alias of `voll_usd_per_mwh`. |
| `willingness_to_pay` | PRODUCT | **read** | USD/MWh of consumption; the operand of the annual willingness-to-pay. |

Seven of these rows are `read` rather than `derive` because the node is a
plausible operand that no equation reads today; fifteen are aliases or products
that become an lhs, and one — `firm_build_fleet_mw` — is a bound.
`excise_duty_fuel`, `loss_factor_cross_border` and
`opex_variable_electrolyser` were already typed correctly and needed a consumer,
not a repair.

### SCENE-SWITCH (10) — run configuration, no equation

| node | class | kind | reason |
|---|---|---|---|
| `ancillary_services_market` | SCENE-SWITCH | defer | "Whether an ancillary services market is modelled. A boolean." Selects a model. |
| `balancing_market` | SCENE-SWITCH | defer | Same; selects whether a balancing stage exists. |
| `contract_for_difference` | SCENE-SWITCH | defer | Selects whether the CfD instrument is modelled. |
| `day_ahead_market` | SCENE-SWITCH | defer | Selects a market stage. |
| `dg_placement_enabled` | SCENE-SWITCH | defer | Selects whether distributed generation placement is optimised. |
| `intraday_market` | SCENE-SWITCH | defer | Selects a market stage. |
| `life_extension_possible` | SCENE-SWITCH | defer | Selects whether the optimiser may extend plant life. A capability of the model. |
| `phase_shifting_enabled` | SCENE-SWITCH | defer | Selects whether phase-shifting transformers are available. |
| `real_time_market` | SCENE-SWITCH | defer | Selects a market stage. |
| `unit_commitment` | SCENE-SWITCH | defer | "Whether the dispatch model enforces unit commitment." The clearest case in the graph: it switches the *model*, and an equation that multiplied it by anything would be a product of a solver flag. |

These ten plus the five the worklist names (`cross_border_trading`,
`security_constrained_dispatch`, `storage_dispatch_enabled`,
`topology_switching_enabled`, `voltage_optimisation_enabled`) are the fifteen
whose "all coupled" claim the worklist makes. None is coupled.

### THRESHOLD (5) — a ceiling or a floor, coupled only by being an lhs

| node | class | kind | reason |
|---|---|---|---|
| `electrolyser_capacity` | THRESHOLD | **bound** | A build size floored by the average electrolyser draw. Retype to MW is a prerequisite. |
| `fit_capacity_cap` | THRESHOLD | **bound** | The FiT programme's capacity ceiling over the VRE build. |
| `regulatory_lag` | THRESHOLD | **read** | The lag the review period must cover; the rhs operand of the period bound. |
| `regulatory_period_length` | THRESHOLD | **bound** | The review period must be at least the recovery lag. |
| `renewable_penetration_limit` | THRESHOLD | **bound** | The instantaneous penetration ceiling over the realised VRE share. |

### GATE-SCENE-SWITCH (1)

| node | class | kind | reason |
|---|---|---|---|
| `extreme_weather_events` | GATE-SCENE-SWITCH | defer | "Extreme weather frequency" — a climate-scenario dial of the same kind as `heatwave_frequency`, `drought_frequency` and `storm_surge`, all of which the scene pack classifies GATE-SCENE-SWITCH and none of which carries an equation. It configures the hazard scenario; it is not a product. |

### DEPRECATED (1) — a new class, defined

| node | class | kind | reason |
|---|---|---|---|
| `demand_growth_rate` | DEPRECATED | defer | `deprecated_by='demand_growth'`. The node exists so a scenario that still names it fails loudly rather than silently reading a rate on the wrong scale. A deprecated node refuses any edge or equation (`GraphError`), so it cannot be a target and must not be an operand — coupling it would defeat the deprecation. |

**Why a new class.** The seven existing classes all describe a node that is a
candidate for coupling: PRODUCT and BASE-NEEDED want an equation now or later,
THRESHOLD wants a bound, QUALITATIVE and the two scene classes are declarations,
and GATE-PRODUCT is a share that multiplies. A deprecated node is none of these
— it is *retired*, its correct coupling is its own removal, and any equation
that named it would resurrect the id the deprecation exists to kill. Calling it
QUALITATIVE would file a tombstone under "declared free space", which is the
wrong register.

## Proposals

### New nodes this pack declares

Six left-hand-side ids do not exist in the graph. Each is a quantity the
equations below compute and no shipped node holds.

| node | unit | range | default | role / determinism | why |
|---|---|---|---|---|---|
| `fuel_excise_revenue_usd_per_year` | USD/year | [0, 4.5e12] — 0.5 × 300 USD/MWh × 30,000 TWh × 1e6, the product of the three operands' own maxima | — | derived / fixed | The excise take. The graph has the share and the price but no revenue, and the shipped `fossil_fuel_subsidy_spend_usd_per_year` is the same arithmetic on a different share, so the family has a slot for it. |
| `gis_mapped_network_km` | km | [0, 400000] — the sum of the two route-km ceilings | — | derived / fixed | The mapped route length. `gis_requirements` is a share of assets and the graph states route km, so the product is the only form the base admits. |
| `cross_border_losses_twh` | TWh/year | [-1000, 1000] — the loss share [0,1] times `net_imports_twh`'s own signed range | — | derived / fixed | Energy lost in transit. Signed because the flow is signed: a net exporter loses energy on the way out. |
| `electrolyser_variable_opex_usd_per_year` | USD/year | [0, 2e12] — 5 USD/MWh × 10,000 kt × 1e6 × 40 MWh/kg | — | derived / fixed | The electrolyser's variable O&M bill. `opex_variable_electrolyser` is stated per MWh of hydrogen and no node converts it to a spend. |
| `rooftop_solar_households` | 1 | [0, 1e8] — the household ceiling | — | derived / fixed | Households with rooftop PV. A count, because the share alone says nothing about how many connections the distribution network carries. |
| `willingness_to_pay_usd_per_year` | USD/year | [0, 5e12] — 1000 USD/MWh × 50 MWh × 1e8 households | — | derived / fixed | The annual consumer surplus at the declared willingness to pay. |

### Retypes

Nineteen nodes change unit, range or default. Every retype below is authored in
`config/prg.yaml` (the node is frozen, so it cannot be changed at runtime).

| node | from | to |
|---|---|---|
| `accelerated_depreciation` | `None`, [0, 1e6], 500000.0, free | `1/year`, [0.01, 0.8], no default, derived |
| `depreciation_schedule_accelerated` | `None`, [0, 1e6], 500000.0, free | `1/year`, [0.01, 0.8], no default, derived |
| `depreciation_schedule_declining` | `None`, [0, 1e6], 500000.0, free | `1/year`, [0.03, 0.4], no default, derived |
| `depreciation_schedule_linear` | `None`, [0, 1e6], 500000.0, free | `1/year`, [0.01, 0.2], no default, derived |
| `buffer_pool_contribution` | `None`, [0, 1e6], 500000.0, free | `1`, [0, 1], no default, derived |
| `compensation_rates` | `None`, [0, 1e6], 500000.0, free | `USD/hectare`, [50, 2.5e6], no default, derived |
| `consumer_price_index_link` | `None`, [0, 1e6], 500000.0, free | `1/year`, [-0.05, 0.5], no default, derived |
| `gdp_per_capita_growth` | `None`, [0, 1e6], 500000.0, free | `1/year`, [-0.05, 0.18], no default, derived |
| `health_impact_dalys` | `None`, [0, 1e6], 500000.0, free | `DALY/year`, [0, 1e8], no default, derived |
| `health_impact_mortality` | `None`, [0, 1e6], 500000.0, free | `deaths/year`, [0, 1e7], no default, derived |
| `hydrogen_demand_domestic` | `None`, [0, 1e6], 500000.0, free | `kt/year`, [-400, 10000], no default, derived |
| `hydrogen_production_demand` | `None`, [0, 1e6], 500000.0, free | `MWh/year`, [0, 1e10], no default, derived |
| `ppa_indexation` | `None`, [0, 1e6], 500000.0, free | `1/year`, [0, 0.3], no default, derived |
| `premium_share_of_asset` | `None`, [0, 1e6], 500000.0, free | `1`, [0.001, 0.03], no default, derived |
| `value_of_lost_load` | `None`, [0, 1e6], 500000.0, free | `USD/MWh`, [100, 100000], no default, derived |
| `willingness_to_pay` | `None`, [0, 1e6], 500000.0, free | `USD/MWh`, [0, 1000], 100.0, free |
| `fit_capacity_cap` | `None`, [0, 1e6], 500000.0, free | `MW`, [0, 1e6], 4000.0, free |
| `renewable_penetration_limit` | `None`, [0, 1e6], 500000.0, free | `1`, [0, 1], 0.5, free |
| `electrolyser_capacity` | `None`, [0, 1e6], 500000.0, free | `MW`, [0, 1e6], 500.0, free |

Two retypes carry a substantive judgement rather than a unit. `fit_capacity_cap`
at 4000 MW sits above the shipped 2,702.70 MW VRE build, so the ceiling holds
with room and a 5,000 MW scenario breaks it — a ceiling equal to the build is
the tautology the sibling pack rejects. `electrolyser_capacity` at 500 MW is the
value that satisfies the bound below at defaults; the arithmetic floor is
292.68 MW and the row says so.

### PRODUCT (24 slice rows, plus the six declared nodes they compute)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `accelerated_depreciation` | PRODUCT | derive | `1/year` (retyped from `None`) | [0.01, 0.8] — the accelerated schedule's own band | derived / policy | `accelerated_depreciation = depreciation_schedule_accelerated` | The tax code's accelerated rate, as the schedule it names. At defaults 0.04/year against the 0.04 straight-line rate, because the shipped factor is 1.0. | — (alias of the graph's own quantity) | `accelerated_depreciation = accelerated_depreciation_factor / depreciation_life_by_asset` — rejected as a second spelling of the row below: the same expression computes `depreciation_schedule_accelerated`, and two ids for one number is the defect this batch exists to remove. |
| `accelerated_depreciation_factor` | PRODUCT | read | `1` (already typed) | [1, 4] — the multiple any jurisdiction allows, 1.0 to 4.0 | free / policy | `depreciation_schedule_accelerated = accelerated_depreciation_factor / depreciation_life_by_asset` (read) | The multiple of straight-line depreciation the code permits. At 1.0 the accelerated schedule is the linear one; at 2.0 it doubles. | — (read as an operand; the identity it enters is cited on its lhs row) | Making it the lhs (`= schedule_accelerated * life`) — rejected: the factor is a policy dial the modeller sets, and deriving it from the life would let a 25-year asset change the tax code. |
| `buffer_pool_contribution` | PRODUCT | derive | `1` (retyped from `None`) | [0, 1] — a share of issued credits | derived / policy | `buffer_pool_contribution = permanence_parameters` | The share of issued credits the registry holds in its buffer against reversal, which is the permanence share the graph already carries. 0.1 at defaults. | — (alias of the graph's own quantity) | A separate buffer base — rejected: `carbon_credit_reversal_allowance_definition` already computes `(1 - permanence_parameters) * carbon_credit_volumes` and its prose calls the complement "the buffer a registry retains". **A reviewer must decide** whether this alias is a second spelling of one object or a distinct contribution rate; if the former, the node should be deleted, not coupled. |
| `compensation_rates` | PRODUCT | derive | `USD/hectare` (retyped from `None`) | [50, 2.5e6] — 0.5 × 100 to 5.0 × 500,000, the operands' own extremes | derived / policy | `compensation_rates = compensation_share_of_market * land_acquisition_cost_per_hectare` | The compensation the project pays per hectare, as the multiple of market value the package offers applied to the land's own acquisition rate. 1.5 × 5000 = 7,500 USD/hectare at defaults. | — (definitional: multiple × rate; the land rate's own identity is cited on `land_acquisition_cost_definition`) | `compensation_rates * land_area_hectares` as a total bill — rejected: that is `land_acquisition_cost_usd` with a multiplier folded in, and the graph already carries the unmultiplied bill. **Citation gap:** the shipped prose names IFC land-acquisition practice and no archived copy states the multiple's range; listed under **Sources to fetch**. |
| `compensation_share_of_market` | PRODUCT | read | `1` (already typed) | [0.5, 5.0] — exact market value to a multiple of it | free / policy | `compensation_rates = compensation_share_of_market * land_acquisition_cost_per_hectare` (read) | The multiple of market value the compensation package pays. 1.5 at defaults, i.e. a 50% premium over the land's acquisition rate. | — (read as an operand; the multiple's range has no archived source, see **Sources to fetch**) | Making it the lhs (`= compensation_rates / land_cost`) — rejected: the multiple is the policy dial and the per-hectare rate is what the project pays; inverting them would let the land market set the compensation policy. |
| `consumer_price_index_link` | PRODUCT | derive | `1/year` (retyped from `None`) | [-0.05, 0.5] — `inflation_rate`'s own band | derived / fixed | `consumer_price_index_link = inflation_rate` | The annual indexation rate a CPI-linked tariff or contract applies, which is the inflation rate the graph already carries. 0.05/year at defaults. | — (alias of the graph's own quantity) | A distinct index base — rejected: the graph has one inflation series, and a second dial would let the CPI link and the discount rate's inflation disagree about the same economy. **Finding:** the node's name promises an *index*, and the graph carries a *rate*; the alias is honest only if the prose says the link is a rate. |
| `depreciation_schedule_accelerated` | PRODUCT | derive | `1/year` (retyped from `None`) | [0.01, 0.8] — 1/60 to 4/5, the factor and life bands divided | derived / policy | `depreciation_schedule_accelerated = accelerated_depreciation_factor / depreciation_life_by_asset` | The accelerated rate: the permitted multiple of straight-line divided by the asset's depreciable life. 1.0 / 25 = 0.04/year at defaults. | Straight-line and declining-balance depreciation formulas; cf. Short, Packey & Holt (1995), NREL/TP-462-5173 (`sources/archive/short_packey_holt_1995.pdf`) | `accelerated_depreciation_factor * (1 / life)` — rejected as a no-op respelling; the DSL has no precedence surprise here, so the two forms are identical and the simpler one ships. |
| `depreciation_schedule_declining` | PRODUCT | derive | `1/year` (retyped from `None`) | [0.03, 0.4] — 2/60 to 2/5 | derived / fixed | `depreciation_schedule_declining = 2.0 / depreciation_life_by_asset` | The declining-balance rate at 200%, the double-declining convention: twice the straight-line rate over the asset's life. 2.0 / 25 = 0.08/year at defaults. | Straight-line and declining-balance depreciation formulas; cf. Short, Packey & Holt (1995), NREL/TP-462-5173 (`sources/archive/short_packey_holt_1995.pdf`) | `150% declining balance` (1.5 / life) as the shipped default — rejected: the source describes both the 200% and 150% conventions and states no preference; 200% is the MACRS default and the row's prose says which convention it took. A second node for the 150% case is a dial nobody asked for. |
| `depreciation_schedule_linear` | PRODUCT | derive | `1/year` (retyped from `None`) | [0.01, 0.2] — 1/60 to 1/5 | derived / fixed | `depreciation_schedule_linear = 1.0 / depreciation_life_by_asset` | The straight-line rate: the asset's cost spread evenly over its depreciable life. 1.0 / 25 = 0.04/year at defaults. | Straight-line and declining-balance depreciation formulas; cf. Short, Packey & Holt (1995), NREL/TP-462-5173 (`sources/archive/short_packey_holt_1995.pdf`) | A salvage-value term (`(1 - salvage) / life`) — rejected: the graph carries no salvage rate, and adding one to make the formula look complete would be a base this pack does not own. |
| `excise_duty_fuel` | PRODUCT | read | `1` (already typed) | [0, 0.5] — a share of the retail price | free / policy | `fuel_excise_revenue_usd_per_year = excise_duty_fuel * fuel_price_usd_per_mwh * (generation_twh - renewable_generation_twh) * 1000000` (read) | Excise duty on fuel as a share of the retail price. 0.2 at defaults, which is the duty on 20.62 TWh of non-renewable generation at 40 USD/MWh. | Rate-based levy and allowance definitions (standard fiscal accounting) (`sources/INDEX.md` row `standard_fiscal`, `n/a`) | `excise_duty_fuel * fuel_price_escalated_usd_per_mwh` — rejected: the escalated price compounds to the horizon while generation is an annual quantity, so the product would mix a horizon price with a one-year volume. The base-year price is the right partner for an annual volume, and it is the shipped convention in `fossil_fuel_subsidy_spend_usd_per_year`. |
| `fuel_excise_revenue_usd_per_year` | PRODUCT | derive | `USD/year` (new node) | [0, 4.5e12] — see the new-node table | derived / fixed | `fuel_excise_revenue_usd_per_year = excise_duty_fuel * fuel_price_usd_per_mwh * (generation_twh - renewable_generation_twh) * 1000000` | The excise the treasury collects on fossil generation: the duty share of the delivered price over the non-renewable volume. 0.2 × 40 × 20.62 TWh × 1e6 = 164,974,190.45 USD/year at defaults. | Rate-based levy and allowance definitions (standard fiscal accounting) (`sources/INDEX.md` row `standard_fiscal`, `n/a`) | `excise_duty_fuel * fuel_price_usd_per_mwh * generation_twh * 1000000` (all generation) — rejected: the duty falls on fossil fuel, and charging it on renewables would make the excise a generation tax. `(generation_twh - renewable_generation_twh)` is the graph's own fossil decomposition, the same one `fossil_fuel_subsidy_spend_usd_per_year` uses. |
| `firm_build_fleet_mw` | PRODUCT | **bound** | `MW` (already typed) | [0, 2e6] — unchanged | endogenous / fixed | `firm_build_fleet_mw >= firm_capacity_mw` (`geq`) | The optimiser's total build must cover the firm part of the fleet it is building. 10,000 MW against 9,000 MW at defaults. Routes `unbound` — both sides are endogenous or derived, so this is a post-solve audit check, not an LP constraint. | Least-cost generation expansion: Koltsaklis & Dagoumas (2018), Applied Energy 230:563-589; Tejada-Arango (2023), arXiv:2307.16842; Oree et al. (2017), RSER 69:790-803 (`sources/archive/whiterose_gep_review_2017.pdf`) | `firm_build_fleet_mw = <twelve builds>` (the classification this pack would have preferred) — **refused by the loader**: `GraphError: ... its role is 'endogenous'; a parameter an equation fixes is 'derived', and any other role lets a user set it and be silently overruled`. The same sum without the endogenous role is `fleet_build_balance`, already shipped over 18 leaves. **Finding:** the node has zero readers and its description's claim — "the identity every build set must satisfy ... the reserve margins read the firm part of it" — is false on both counts; `fleet_build_balance` is the identity and `firm_capacity_definition` feeds the reserve margins. A reviewer should prefer deleting it to bounding it. |
| `gdp_per_capita_growth` | PRODUCT | derive | `1/year` (retyped from `None`) | [-0.05, 0.18] — the GDP band less the population band, over (1 + the population band) | derived / fixed | `gdp_per_capita_growth = (gdp_growth - population_growth_rate) / (1.0 + population_growth_rate)` | Growth in output per head, from the two rates the graph carries. (0.05 − 0.02) / 1.02 = 0.029412/year at defaults, against a 3% headline GDP rate and a 2% population rate. | The Fisher equation applied to per-capita growth: (1 + g)/(1 + n) − 1 = (g − n)/(1 + n) (`sources/INDEX.md` row `fisher_equation`, `n/a`) | `(1.0 + gdp_growth) / (1.0 + population_growth_rate) - 1.0` — **rejected on units**: the lhs is `1/year` but `1 + rate` is dimensionless, so the ratio is dimensionless and `check_equation` returns `consistent=False`. The difference form is the same algebra with the `1`s cancelled and it is `1/year`. `gdp_growth - population_growth_rate` alone — rejected: it drops the denominator and misstates the per-capita rate by 2% at defaults, which is the whole correction. |
| `gis_mapped_network_km` | PRODUCT | derive | `km` (new node) | [0, 400000] — see the new-node table | derived / fixed | `gis_mapped_network_km = gis_requirements * (transmission_line_length_km + distribution_network_km)` | The route length held in the GIS: the mapped share of the transmission and distribution networks. 0.6 × (12,000 + 45,000) = 34,200 km at defaults. | — (definitional: share × route length) | A count of GIS *asset records* — rejected: the graph carries km and no asset-record count, so the km base is the only one the tree states, and the worklist's "needs an asset-count base" is a deferral on a base the node does not need. |
| `gis_requirements` | PRODUCT | read | `1` (already typed) | [0, 1] — a share of assets | free / policy | `gis_mapped_network_km = gis_requirements * (transmission_line_length_km + distribution_network_km)` (read) | The share of network assets in the GIS, 0.6 at defaults, over the 57,000 route-km the graph states. | — (read as an operand; the product's own row carries the citation) | A record count (`gis_requirements * number_of_generators`) — rejected: a generator is not a network asset, and the route-km base is the one the node's own description — "share of network assets" — implies. |
| `health_impact_dalys` | PRODUCT | derive | `DALY/year` (retyped from `None`) | [0, 1e8] — `dalys_per_year`'s own band | derived / fixed | `health_impact_dalys = dalys_per_year` | Disability-adjusted life years lost to the fleet's emissions, which is the burden the shipped health chain already computes. 57,600 DALY/year at defaults. | — (alias of the graph's own quantity) | `premature_deaths_per_year * years_of_life_lost` — rejected: that is `dalys_definition` verbatim, so the new equation would add a second spelling of one number. |
| `health_impact_mortality` | PRODUCT | derive | `deaths/year` (retyped from `None`) | [0, 1e7] — `premature_deaths_per_year`'s own band | derived / fixed | `health_impact_mortality = premature_deaths_per_year` | Deaths attributable to the fleet's PM2.5 over the year, which the shipped concentration-response chain already computes. 4,800 deaths/year at defaults. | — (alias of the graph's own quantity) | A separate exposure-response form — rejected: `premature_deaths_definition` already carries it and cites WHO AirQ+; recomputing it under a second id is the alias defect. |
| `hydrogen_demand_domestic` | PRODUCT | derive | `kt/year` (retyped from `None`) | [-400, 10000] — negative because exports can exceed domestic production | derived / fixed | `hydrogen_demand_domestic = hydrogen_production_kt_per_year - hydrogen_export_volume / (mwh_per_hydrogen_unit * 1000000)` | Hydrogen consumed at home: production less what is exported, with the export volume converted from MWh to kilotonnes through the graph's own 0.03333 MWh/kg. 50 − 0.6 = 49.4 kt/year at defaults. | — (definitional: production less a unit-converted export) | `hydrogen_production_kt_per_year * (1 - export_share)` — rejected: no export share exists, and the MWh-to-kt conversion through `mwh_per_hydrogen_unit` is the graph's own identity (`electrolysis_electricity_demand_definition` uses it in the other direction). |
| `hydrogen_production_demand` | PRODUCT | derive | `MWh/year` (retyped from `None`) | [0, 1e10] — `electrolysis_electricity_demand_mwh_per_year`'s own band | derived / fixed | `hydrogen_production_demand = electrolysis_electricity_demand_mwh_per_year` | The electricity hydrogen production draws, which the shipped electrolysis identity already computes from volume, energy per kilogram and efficiency. 2,563,846.15 MWh/year at defaults. | — (alias of the graph's own quantity) | A second conversion from kt through `mwh_per_hydrogen_unit` alone — rejected: that omits `electrolyser_efficiency` (0.65) and would understate the demand by 35%, duplicating a shipped identity incorrectly. |
| `loss_factor_cross_border` | PRODUCT | read | `1` (already typed) | [0, 1] — a loss share cannot exceed the flow | free / fixed | `cross_border_losses_twh = loss_factor_cross_border * net_imports_twh` (read) | The share of cross-border flow lost in transit, 0.03 at defaults. Signed flow in, signed loss out: at 0 net imports the losses are 0 TWh/year. | — (read as an operand; the product's own row carries the citation) | `loss_factor_cross_border * (generation_twh + net_imports_twh)` — rejected: the loss is on the cross-border flow, not on domestic generation, and the wider base would charge transit losses to the domestic fleet. |
| `cross_border_losses_twh` | PRODUCT | derive | `TWh/year` (new node) | [-1000, 1000] — see the new-node table | derived / fixed | `cross_border_losses_twh = loss_factor_cross_border * net_imports_twh` | The energy lost in transit on the cross-border flow: the loss share applied to net imports. 0.03 × 0 = 0 TWh/year at defaults, because the reference case is self-sufficient; a 100 TWh import year loses 3 TWh. | — (definitional: share × flow) | `loss_factor_cross_border * demand_twh` — rejected: losses fall on the traded flow, and using demand would charge transit losses to energy that never crossed a border. |
| `opex_variable_electrolyser` | PRODUCT | read | `USD/MWh` (already typed) | [0, 5] — the variable O&M band | free / fixed | `electrolyser_variable_opex_usd_per_year = opex_variable_electrolyser * hydrogen_production_kt_per_year * 1000000 * mwh_per_hydrogen_unit` (read) | Variable O&M per MWh of hydrogen produced, excluding electricity, which the node's own description calls the dominant cost. 1.0 USD/MWh × 50 kt × 1e6 kg/kt × 0.03333 MWh/kg = 1,666,500 USD/year at defaults. | — (read as an operand; the product's own row carries the citation) | Dividing by `electrolyser_efficiency` — rejected: the opex is stated per MWh *of hydrogen produced*, which is the output, so the efficiency is already inside the rate and dividing again would double-count it. |
| `electrolyser_variable_opex_usd_per_year` | PRODUCT | derive | `USD/year` (new node) | [0, 2e12] — see the new-node table | derived / fixed | `electrolyser_variable_opex_usd_per_year = opex_variable_electrolyser * hydrogen_production_kt_per_year * 1000000 * mwh_per_hydrogen_unit` | The electrolyser fleet's variable O&M bill: the rate per MWh of hydrogen over the year's production, with the kilotonnes converted through the graph's 0.03333 MWh/kg. 1,666,500 USD/year at defaults. | IEA/NEA Projected Costs of Generating Electricity (`sources/archive/iea_nea_egc_2020.pdf`) | `opex_variable_electrolyser * electrolysis_electricity_demand_mwh_per_year` — rejected: that charges O&M per MWh of *electricity*, which is the input, not per MWh of hydrogen, which is what the rate's own description states. |
| `ppa_indexation` | PRODUCT | derive | `1/year` (retyped from `None`) | [0, 0.3] — `tariff_indexation`'s own band | derived / fixed | `ppa_indexation = tariff_indexation` | The annual escalation a power purchase agreement applies to its strike price, which is the tariff indexation rate the graph already carries. 0.05/year at defaults. | — (alias of the graph's own quantity) | A separate PPA index base — rejected: `ppa_indexed_price_definition` already reads `tariff_indexation` to escalate `ppa_price_usd_per_mwh`, so a second dial would let two escalations move the same price. |
| `premium_share_of_asset` | PRODUCT | derive | `1` (retyped from `None`) | [0.001, 0.03] — `insurance_loss_share_of_cost`'s own band | derived / fixed | `premium_share_of_asset = insurance_loss_share_of_cost` | The annual premium as a fraction of the insured asset's value, which is the loss share of cost the graph already carries. 0.005 at defaults. | — (alias of the graph's own quantity) | A distinct premium rate at the shipped 0.008 — rejected: `insurance_premium_definition` computes `insurance_loss_share_of_cost * capex_usd_per_kw`, so the two ids are one premium and the catalog's 0.008 against 0.005 is a duplicate row, not a second product. **Finding:** the alias resolves the duplicate in favour of 0.005, which lowers the shipped premium by 37.5%; a reviewer should confirm that is the intended resolution. |
| `rooftop_solar_adoption` | PRODUCT | read | `1` (already typed) | [0, 1] — a share of suitable rooftops | free / policy | `rooftop_solar_households = rooftop_solar_adoption * households_total` (read) | The share of suitable rooftops carrying PV, 0.1 at defaults, over the 10,000,000 households the graph derives. | — (read as an operand; the count's own row carries the citation) | Multiplying by `population_total` — rejected: the share is of rooftops, and `households_total` is the graph's own rooftop proxy (`population_total / persons_per_household`); using population would overstate the count 3.9-fold. |
| `rooftop_solar_households` | PRODUCT | derive | `1` (new node) | [0, 1e8] — see the new-node table | derived / fixed | `rooftop_solar_households = rooftop_solar_adoption * households_total` | Households with rooftop PV: the adoption share over the household count. 0.1 × 10,000,000 = 1,000,000 households at defaults. | — (definitional: share × count) | A capacity in MW — rejected: the graph carries no kW per rooftop, and inventing one would be a base this pack does not own; the count is what the share and the household base can actually give. |
| `value_of_lost_load` | PRODUCT | derive | `USD/MWh` (retyped from `None`) | [100, 100000] — `voll_usd_per_mwh`'s own band | derived / fixed | `value_of_lost_load = voll_usd_per_mwh` | What a megawatt-hour of unserved energy costs the system, which is the VoLL the graph already carries and `reliability_cost_definition` already prices unserved energy at. 5,000 USD/MWh at defaults. | Value of lost load as the price customers pay to avoid an outage; cf. ENTSO-E adequacy studies (`sources/archive/entsoe_maf_2019_methodology.pdf`, definition at §3.6) | A separate outage-cost curve — rejected: `reliability_cost_definition` already computes `unserved_energy_gwh * 1000 * voll_usd_per_mwh`, so a second value of lost load would give one quantity two prices. |
| `willingness_to_pay` | PRODUCT | read | `USD/MWh` (retyped from `None`) | [0, 1000] — the consumer's valuation band; the shipped default 100 is the residential tariff order | free / policy | `willingness_to_pay_usd_per_year = willingness_to_pay * household_consumption_mwh_per_year * households_total` (read) | What a household will pay per megawatt-hour of consumption, 100 USD/MWh against the 1.5 MWh a household uses. | Willingness to pay as the valuation of a benefit; cf. Short, Packey & Holt (1995), NREL/TP-462-5173 (`sources/archive/short_packey_holt_1995.pdf`) | `willingness_to_pay * total_revenue_usd_per_year` — rejected: revenue is what consumers are *charged*, and a willingness-to-pay product against it would return the ratio of valuation to price, not a surplus. |
| `willingness_to_pay_usd_per_year` | PRODUCT | derive | `USD/year` (new node) | [0, 5e12] — see the new-node table | derived / fixed | `willingness_to_pay_usd_per_year = willingness_to_pay * household_consumption_mwh_per_year * households_total` | The annual consumer valuation of the electricity households consume: 100 USD/MWh × 1.5 MWh × 10,000,000 households = 1.5e9 USD/year at defaults. The quantity a cost-benefit test needs and no node holds. | Willingness to pay as the valuation of a benefit; cf. Short, Packey & Holt (1995), NREL/TP-462-5173 (`sources/archive/short_packey_holt_1995.pdf`) | `willingness_to_pay * demand_twh * 1000000` — rejected: demand is economy-wide and the willingness to pay here is the household's, so the product would value industrial load at a residential rate. |

### THRESHOLD (5 rows)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `electrolyser_capacity` | THRESHOLD | bound | `MW` (retyped from `None`) | [0, 1e6] — the fleet's own nameplate ceiling; default 500, above the 292.68 MW floor | free / fixed | `electrolyser_capacity >= electrolysis_electricity_demand_mwh_per_year / 8760` (`geq`) | The installed electrolyser must be able to carry the average electricity draw its own hydrogen programme implies: 2,563,846.15 MWh/year over 8,760 hours is 292.68 MW, and the shipped default of 500 MW clears it. Routes `unbound` — the rhs is derived. | IEA/NEA Projected Costs of Generating Electricity (`sources/archive/iea_nea_egc_2020.pdf`) | `electrolyser_capacity = electrolysis_electricity_demand_mwh_per_year / 8760` (an equality) — rejected: a build is a *decision*, and deriving it would make the optimiser's variable a computed number. It is also wrong by construction: 292.68 MW is an average draw, and a plant sized to its average has no capacity to run above it. **Canary:** with the shipped default of 0.0 the bound fails (residual −292.677); with 300.0 it holds. **Prerequisite:** the `MW` retype in `build_batch13`'s `UNBUILT_TECHS` has not reached `config/prg.yaml` — the baked node is still `unit=None, default=500000.0`, and this bound is meaningless until that lands. |
| `fit_capacity_cap` | THRESHOLD | bound | `MW` (retyped from `None`) | [0, 1e6]; default 4000, above the 2,702.70 MW VRE build | free / policy | `fit_capacity_cap >= vre_capacity_mw` (`geq`) | The feed-in-tariff programme's capacity ceiling must admit the VRE the fleet actually builds, or the programme's own cap is violated by its own scenario. 2,702.70 MW under 4,000 at defaults. Routes `bound`: `vre_capacity_mw` is a declared network quantity. | Oree et al. (2017), RSER 69:790-803 (`sources/archive/whiterose_gep_review_2017.pdf`) | `fit_capacity_cap <= vre_capacity_mw` (a floor that forces build) — rejected: the node is a *cap*, and a floor would make the programme compel capacity rather than admit it. A cap at the shipped 500000 placeholder — rejected as vacuous: it admits every admissible VRE build. |
| `regulatory_lag` | THRESHOLD | read | `years` (already typed) | [0, 5] — unchanged | free / policy | `regulatory_period_length >= regulatory_lag` (read) | Years between cost incurrence and its recovery in tariff. The node's own description already states the invariant this pack is about to enforce: "bounded below at zero and above at the period length". 1 year at defaults. | World Bank Regulation of Utilities handbook, revenue caps (`sources/archive/world_bank_regulating_utilities_handbook.pdf`) | `regulatory_lag = regulatory_period_length / 2` (a midpoint convention) — rejected: the lag is a measured institutional fact, not a fraction of the review cycle, and the sample's central value (1 year) is not half of a five-year cycle. |
| `regulatory_period_length` | THRESHOLD | bound | `years` (already typed) | [1, 10] — unchanged | free / policy | `regulatory_period_length >= regulatory_lag` (`geq`) | The review period must be at least the lag between incurring a cost and recovering it, or a cost incurred inside one period cannot be recovered before the next review closes. 5 years against a 1-year lag at defaults. Routes `bound`. | World Bank Regulation of Utilities handbook, revenue caps (`sources/archive/world_bank_regulating_utilities_handbook.pdf`) | `regulatory_period_length <= 5` — rejected as a **tautology**: the node's declared range is already [1, 10] and the sample's mode is 4–5, so a ceiling at 5 restates a judgement the range already carries. The lag bound is the one that can fail. |
| `renewable_penetration_limit` | THRESHOLD | bound | `1` (retyped from `None`) | [0, 1] — a share of instantaneous demand; default 0.5 | free / policy | `renewable_penetration_limit >= vre_share` (`geq`) | The instantaneous penetration ceiling must admit the annual VRE share the fleet achieves, or the limit is breached by the build the plan chose. 0.2703 under 0.5 at defaults. Routes `unbound` — `vre_share` is derived. | Oree et al. (2017), RSER 69:790-803 (`sources/archive/whiterose_gep_review_2017.pdf`) | The classification pack's `renewable_penetration_limit * vre_share` as a curtailed-energy product — rejected: no curtailed-energy node exists, so the product has no lhs. A limit at the shipped 500000 placeholder — rejected as vacuous and meaningless: a penetration share of 500,000. **Note:** the bound compares an *annual* share to an *instantaneous* limit, which is the weaker of the two claims; the graph carries no instantaneous penetration node, so this is the strongest form the tree admits and the prose says so. |

## Verification

Run against `config/prg.yaml` as it stands, with the retypes and new nodes
applied in memory and the 26 equations added:

```
nodes 1344 equations 503 edges 1011
unit failures: none | checked 26
excursions: {}
violations: []
```

`check_equation` returns `decidable=True, consistent=True` for all 26. The 21
derived values at the propagated defaults, as printed:

```
depreciation_schedule_accelerated = 0.04
depreciation_schedule_declining   = 0.08
depreciation_schedule_linear      = 0.04
accelerated_depreciation          = 0.04
buffer_pool_contribution          = 0.1
compensation_rates                = 7500.0
consumer_price_index_link         = 0.05
fuel_excise_revenue_usd_per_year  = 164974190.45325273
gdp_per_capita_growth             = 0.029411764705882353
gis_mapped_network_km             = 34200.0
health_impact_dalys               = 57600.0
health_impact_mortality           = 4800.0
hydrogen_demand_domestic          = 49.399939993999396
hydrogen_production_demand        = 2563846.1538461535
cross_border_losses_twh           = 0.0
electrolyser_variable_opex_usd_per_year = 1666500.0
ppa_indexation                    = 0.05
premium_share_of_asset            = 0.005
rooftop_solar_households          = 1000000.0
value_of_lost_load                = 5000.0
willingness_to_pay_usd_per_year   = 1500000000.0
```

The five bounds hold at defaults: 4000 ≥ 2702.70, 0.5 ≥ 0.2703, 5 ≥ 1,
500 ≥ 292.68, 10000 ≥ 9000. Routing through `constraints._classify`:
`fit_capacity_bound` and `regulatory_lag_bound` are **`bound`** (linopy
constraints); `penetration_limit_bound`, `electrolyser_capacity_bound` and
`firm_build_fleet_bound` are **`unbound`** (post-solve audit checks), because
each has a derived or endogenous symbol on one side. A batch author who expects
those three to shape the LP should know that before writing them.

The bound canary: `electrolyser_capacity >= electrolysis_electricity_demand_mwh_per_year / 8760`
with the shipped default of 0.0 yields **one violation at residual −292.677**;
with 300.0 it yields none. A `geq` on a free lhs is therefore genuinely enforced
at defaults, and the shipped default must be ≥ 292.68 MW.

Unit-walker readings to record, so the next reader does not mistake them for
defects in these equations: `fuel_excise_revenue_usd_per_year` reads
`USD * terawatt_hour / megawatt_hour / year`, and
`electrolyser_variable_opex_usd_per_year` reads `USD * kt / kilogram / year`.
Pint reduces both to `USD/year`; `unit_of` does not cancel the prefixes, and
both still return `consistent=True` because the reduction happens on both sides.

## Dependencies

Three deferrals are waiting on a base that no pack currently proposes. They are
not this pack's to add, and a later batch that wants these nodes must add them:

- `morbidity_cases_per_year` (cases/year) — the base `health_impact_morbidity`
  needs. `dalys_per_year` and `premature_deaths_per_year` exist; a case count
  does not, and a DALY is a severity-weighted lost year, not a case.
- A curtailed-energy node (`curtailed_twh`, TWh/year) — the base both
  `renewable_curtailment_limit` and `ppa_curtailment_compensation` need. The
  graph carries no curtailment volume anywhere; `renewable_penetration_limit`
  is a ceiling on a share and cannot stand in for a volume.
- `institutional_capacity`, `financial_capacity`, `technical_capacity` and
  `infrastructure_adequacy` (all shares, [0, 1]) — the components that
  `adaptive_capacity` and `energy_security_index` describe and that no node in
  the graph holds.

Two proposals depend on work outside this pack:

- `electrolyser_capacity`'s bound depends on the `MW` retype authored in
  `build_batch13`'s `UNBUILT_TECHS`, which has not baked. The same table would
  also retype `fusion_capacity`, `flywheel_capacity`,
  `small_modular_reactor_capacity` and `tidal_range_capacity`, all still at
  `unit=None, default=500000.0` — those five are in the THRESHOLD pack's slice,
  not this one, and that pack's rows assume the retype has landed.
- `firm_build_fleet_mw`'s bound reads `firm_capacity_mw`, which is derived by
  `firm_capacity_definition` from `thermal_capacity_mw +
  dispatchable_re_capacity_mw`. Both of those are `endogenous` with defaults and
  no definition of their own, so the containment claim is about the LP's own
  variables and cannot be checked in propagation beyond the defaults.

## Rejected

Approaches considered for the slice as a whole and not taken.

- **A product for every QUALITATIVE node.** The 35 rows have no base: a
  collections policy times a revenue is a number with no meaning, and the class
  exists precisely so that this is recorded rather than manufactured. The scene
  pack's precedent — a documented declaration, no equation — is followed.
- **A bound for every THRESHOLD node.** Three of the five had no non-vacuous
  bound available. `regulatory_period_length <= 5` and a
  `renewable_penetration_limit` ceiling at the placeholder are tautologies, and
  `regulatory_lag`'s only role is as the operand of the period bound. A bound
  whose range is a superset of the quantity it bounds constrains nothing.
- **Deriving `firm_build_fleet_mw`.** Refused by the loader on the role, not by
  preference; the row records the `GraphError` verbatim.
- **Folding `premium_share_of_asset` and `buffer_pool_contribution` into
  deletion.** Both are aliases of quantities the graph already derives, and
  deletion is arguably the right coupling for each. This pack proposes the alias
  because that is what removes the node from `uncoupled()`, and flags both in
  their `rejected` columns as candidates for a reviewer's deletion instead.
- **Retyping `demand_growth_rate`.** A deprecated node must not be touched: the
  shipped value is already correct (`1/year`, [-0.05, 0.15], 0.04) and the
  correct coupling is its removal once no scenario names it.
- **Using `total_capacity_mw` as the base for `firm_build_fleet_mw`.** It is an
  exogenous 10,000 MW constant, not the sum of builds, so a bound against it
  would compare a dial to a dial.
- **Reading `solar_pv_capacity` into any fleet sum.** It is not a member of
  `fleet_build_balance`; including it would make the twelve-technology sum
  19,700 MW and silently change the meaning of `firm_build_fleet_mw` from "the
  optimiser's per-technology builds" to "plus the solar stock".

## Sources to fetch

Cited in prose above but not held locally, so no equation in this pack may lean
on them until a copy is archived and a row added to `sources/INDEX.md`:

- **IFC Performance Standard 5 / Land Acquisition and Involuntary
  Resettlement (2012).** The shipped `land_acquisition_cost_definition` prose
  names IFC land-acquisition practice and no archived copy states it; the
  `compensation_rates` row's multiplier band (0.5–5.0 × market value) has the
  same gap. `sources/INDEX.md` has no row for it.
- **MACRS / IRS Publication 946, Appendix A (200% and 150% declining-balance
  conventions and the half-year convention).** Short, Packey & Holt (1995)
  describes both conventions and states no preference; the shipped 200% is the
  MACRS default and the row says so, but the choice deserves a source of its own.
- **Ofgem RIIO-2 Final Determinations, or any regulator's stated CPI/RPI
  indexation rule for a price control.** `consumer_price_index_link` aliases
  `inflation_rate`, and the archived World Bank handbook discusses price reviews
  without stating an indexation rule. The alias is defensible without a source;
  a *distinct* CPI link would not be.
- **A curtailment-volume source (e.g. a system operator's annual curtailment
  report) if `curtailed_twh` is ever added.** No archived work states a
  curtailment volume, and the two deferrals that need one are recorded under
  **Dependencies**.
