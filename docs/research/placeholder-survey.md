# Placeholder survey: the 181 `unit=None` / `500000.0` nodes

Survey of every node in `config/prg.yaml` that shipped with no unit and the
midpoint default. Each is classified, given an action, and the action is
evidence-backed. Nothing here was written to `config/prg.yaml`.

---

## 1. The count, and the predicate

**Verified count: 181.** Measured twice, against two independent structures.

```
from alea.prg.graph import load_graph
g = load_graph()
placeholders = [n for n in g.nodes.values() if n.unit is None and n.default == 500000.0]
len(placeholders)          # 181
```

| reading | count |
|---|---|
| `load_graph()` nodes matching `unit is None and default == 500000.0` | **181** |
| raw `config/prg.yaml` `parameters` entries matching the same two fields | **181** |
| total nodes in the graph | 1426 |
| total `parameters` entries in the YAML | 1426 |

Every one is `type: float` and `role: free` — verified as sets, not sampled:

```
types  {<ParameterType.FLOAT: 'float'>}
roles  {<Role.FREE: 'free'>}
```

**Root cause confirmed.** `_default_for` in `scripts/build/prg_from_catalog.py:358`
returns `(lo + hi) / 2.0` for any row whose `_unit_of` returns `None`, and
`_range_for` returns `(0.0, 1_000_000.0)` for the same case. `docs/params.md`
has no unit column at all, so `_unit_of` reads only the *name*. A row that is a
name therefore gets a number.

### The finding that shapes everything below

**All 181 are structurally isolated.** Not one is read by an equation, an edge,
or a cross-validation rule. Measured four ways:

| register | count |
|---|---|
| `graph.edges_into(name)` non-empty | **0 of 181** |
| `graph.affects(name)` non-empty | **0 of 181** |
| named in any equation's `lhs`/`rhs`/`parameters`/`free_variables`/`determined_variables` | **0 of 181** |
| named in any `relationships` source/target | **0 of 181** |
| named in any `cross_validation` condition | **0 of 181** |
| present in `graph.uncoupled()` | **181 of 181** |

So every classification below is a claim about a node *no arithmetic reaches*.
That is why the batch proposal (§4) is about representability and defaults
rather than about coupling: there is nothing here to couple without first
building a base the graph does not carry.

**Descriptions add no evidence.** All 181 node descriptions are byte-identical
to the catalog's `Parameter` label column (181 of 181 compared). The evidence
for a unit therefore has to come from the catalog's *Algorithm* and *Python
Implementation* columns, from the node name, or from a sibling node's shipped
unit. Where none of those settle it, the node is AMBIGUOUS rather than guessed.

---

## 2. The table

Columns: **#** · **node** · **category** · **catalog description** · **catalog
algorithm** · **prior pack verdict** · **classification** · **action** ·
**evidence**.

`prior pack` is the verdict in
`docs/research/uncoupled-classification/classification-packs.md`, which covers
135 of the 181. Where my classification differs, the evidence column says why.


| # | node | cat | catalog description | algorithm | prior pack | class | action | evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | `adaptation_benefits` | Adapt | Adaptation benefits | Benefit model | — | **QUANTITY** | unit `USD/year`, range [0.0, 1e10], default `0.0` | sibling `community_benefit_usd_per_year` = USD/year |
| 2 | `adaptation_costs` | Adapt | Adaptation costs | Cost model | — | **QUANTITY** | unit `USD/year`, range [0.0, 1e10], default `0.0` | sibling `community_benefit_usd_per_year` = USD/year |
| 3 | `adaptation_measures` | Adapt | Adaptation measures | Portfolio model | — | **AMBIGUOUS** | defer | "Portfolio model" — a portfolio is not a scalar, and no source in the tree enumerates the options |
| 4 | `resilience_investment` | Adapt | Resilience investment | Investment model | — | **QUANTITY** | unit `USD`, range [0.0, 1e10], default `0.0` | sibling `loss_reduction_investment` = USD |
| 5 | `resilience_metrics` | Adapt | Resilience metrics | Metrics | — | **AMBIGUOUS** | defer | a metrics *set*; the schema has no set type |
| 6 | `risk_transfer_mechanisms` | Adapt | Risk transfer | Financial model | QUALITATIVE | **NAME** | retype `categorical`, options (none, insurance, cat_bond, parametric, guarantee), default `none` | catalog "Risk transfer"; `parametric_insurance_coverage` exists as the numeric sibling |
| 7 | `sea_level_rise` | Adapt | SLR | CMIP6 projection | GATE-SCENE-SWITCH | **QUANTITY** | unit `m`, range [0.0, 2.0], default `0.5` | catalog "SLR" = sea-level rise, a length; prior pack row gives m, [0,2] |
| 8 | `asset_management_maturity` | Asset | AM maturity | Assessment | QUALITATIVE | **NAME** | retype `categorical`, options (initial, developing, defined, managed, optimising), default `developing` | catalog "AM maturity"; an ordinal ISO 55000 ladder is a level, not a magnitude |
| 9 | `condition_based_maintenance` | Asset | CBM | Optimisation | GATE-SCENE | **NAME** | retype `bool`, default `false` | catalog "CBM"; prior pack GATE-SCENE — switches which maintenance model applies |
| 10 | `degradation_model` | Asset | Degradation | Physics model | QUALITATIVE | **NAME** | retype `categorical`, options (linear, exponential, physics_based), default `linear` | catalog "Degradation" + "Physics model"; selects a curve family |
| 11 | `failure_history` | Asset | Failure history | Data model | QUALITATIVE | **AMBIGUOUS** | defer | an event *record set*, not a scalar; the rates it would feed already exist (`forced_outage_rate`) |
| 12 | `iso_55000_compliance` | Asset | ISO 55000 | Compliance | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "ISO 55000"; a compliance flag |
| 13 | `maintenance_history` | Asset | Maintenance history | Data model | QUALITATIVE | **AMBIGUOUS** | defer | a record set, same as `failure_history` |
| 14 | `reliability_centred_maintenance` | Asset | RCM | Optimisation | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "RCM"; a programme choice |
| 15 | `risk_based_maintenance` | Asset | RBM | Optimisation | GATE-SCENE | **NAME** | retype `bool`, default `false` | catalog "RBM"; prior pack GATE-SCENE — a switch |
| 16 | `article_6_2_parameters` | Carbon | Article 6.2 | Compliance | QUALITATIVE | **AMBIGUOUS** | defer | a rulebook *bundle*, plural in the catalog name; no bundle type exists |
| 17 | `article_6_4_parameters` | Carbon | Article 6.4 | Compliance | QUALITATIVE | **AMBIGUOUS** | defer | a rulebook bundle, same as `article_6_2_parameters` |
| 18 | `carbon_credit_rating` | Carbon | Rating | Scoring | QUALITATIVE | **NAME** | retype `categorical`, options (aaa, aa, a, bbb, bb, b, ccc, d), default `bbb` | catalog "Rating" — an ordered rating scale |
| 19 | `carbon_credit_vintage` | Carbon | Vintage | Temporal model | QUALITATIVE | **AMBIGUOUS** | defer | an issuance *year*; `years` is defensible but a calendar year is not a duration, so the unit string would be wrong |
| 20 | `cdm_methodologies` | Carbon | CDM | Methodology | QUALITATIVE | **AMBIGUOUS** | defer | an open methodology register (ACM0002, AMS-I.D, ...); categorical needs a closed list and nothing in the tree enumerates one |
| 21 | `corsia_parameters` | Carbon | CORSIA | Compliance | — | **AMBIGUOUS** | defer | a compliance *bundle* |
| 22 | `gold_standard_methodologies` | Carbon | Gold Standard | Methodology | QUALITATIVE | **AMBIGUOUS** | defer | an open methodology register, same as `cdm_methodologies` |
| 23 | `mrv_parameters` | Carbon | MRV | Methodology | QUALITATIVE | **AMBIGUOUS** | defer | a protocol *bundle* with tiers |
| 24 | `vcs_methodologies` | Carbon | VCS | Methodology | QUALITATIVE | **AMBIGUOUS** | defer | an open methodology register, same as `cdm_methodologies` |
| 25 | `climate_sensitivity` | Climate | Climate sensitivity | Climate sensitivity model | — | **QUANTITY** | unit `degC`, range [1.0, 6.0], default `3.0` | catalog "Climate sensitivity" = ECS, a temperature; siblings `temperature_target`/`temperature_increase` = degC |
| 26 | `cold_snap_frequency` | Climate | Cold snap frequency | Cold snap generator | QUALITATIVE | **QUANTITY** | unit `events/year`, range [0.0, 100.0], default `2.0` | catalog "Cold snap generator"; sibling `outage_frequency` = events/year |
| 27 | `extreme_weather_events` | Climate | Extreme weather frequency | Extreme weather generator | — | **QUANTITY** | unit `events/year`, range [0.0, 500.0], default `12.0` | catalog "Extreme weather frequency"; sibling `outage_events_from_cause` = events/year |
| 28 | `heatwave_frequency` | Climate | Heatwave frequency | Heatwave generator | QUALITATIVE | **QUANTITY** | unit `events/year`, range [0.0, 100.0], default `3.0` | catalog "Heatwave generator"; sibling `outage_frequency` = events/year |
| 29 | `interannual_variability` | Climate | Interannual variability | Interannual variability | QUALITATIVE | **AMBIGUOUS** | defer | a coefficient of variation of what is unstated (inflow? wind? temperature); the reference series is not named |
| 30 | `renewable_curtailment_limit` | Climate | Maximum curtailment | Maximum curtailment | — | **KEEP** | unit `1`, range [0.0, 1.0], default `0.05` | catalog "Maximum curtailment"; a share of VRE output, sibling `renewable_penetration_limit` = unit `1` |
| 31 | `ssp_pathway` | Climate | Shared Socioeconomic Pathway | CMIP6 downscaling + bias correction | QUALITATIVE | **NAME** | retype `categorical`, options (ssp1_1_9, ssp1_2_6, ssp2_4_5, ssp3_7_0, ssp5_8_5), default `ssp2_4_5` | catalog "Shared Socioeconomic Pathway" — a closed, standard set |
| 32 | `cvar_alpha` | Combined | CVaR tail level | CVaR tail level | QUALITATIVE | **KEEP** | unit `1`, range [0.5, 0.999], default `0.95` | catalog "CVaR tail level"; a confidence level is dimensionless |
| 33 | `cvar_omega` | Combined | Risk-aversion weight | Risk-aversion weight | QUALITATIVE | **KEEP** | unit `1`, range [0.0, 10.0], default `1.0` | catalog "Risk-aversion weight"; a weight is dimensionless |
| 34 | `efficient_frontier` | Combined | Efficient frontier | ω sweep | — | **AMBIGUOUS** | defer | the catalog algorithm is "ω sweep" and the implementation "Loop over omega values" — it names a *procedure*; no successor node exists to deprecate it toward |
| 35 | `human_review` | Combined | Human review | Priority queue | GATE-SCENE | **NAME** | retype `bool`, default `false` | catalog "Priority queue"; prior pack GATE-SCENE — gates release of an automated decision |
| 36 | `near_duplicate_detection` | Combined | Near-duplicate detection | MinHash + LSH | QUALITATIVE | **NAME** | retype `categorical`, options (none, exact, minhash_lsh), default `minhash_lsh` | catalog "MinHash + LSH" |
| 37 | `parameter_overrides` | Combined | Parameter overrides | Parameter override | QUALITATIVE | **NAME** | BLOCKED — a dict of overrides; the schema has float/int/bool/categorical/timeseries/spatial and no mapping type | no schema type represents it |
| 38 | `probability_weight` | Combined | Scenario probability | Scenario probability | QUALITATIVE | **KEEP** | unit `1`, range [0.0, 1.0], default `0.5` | catalog "Scenario probability"; a weight. Per-scenario, so one number is the degenerate case |
| 39 | `scenario_description` | Combined | Scenario description | Scenario description | QUALITATIVE | **NAME** | BLOCKED — free text; the schema has no text type | no schema type represents it |
| 40 | `scenario_owner` | Combined | Scenario owner | Scenario owner | QUALITATIVE | **NAME** | BLOCKED — free text; no text type in the schema | no schema type represents it |
| 41 | `scenario_tag` | Combined | Scenario tagging | Scenario tagging | QUALITATIVE | **NAME** | BLOCKED — free text; no text type in the schema | no schema type represents it |
| 42 | `scenario_template` | Combined | Scenario template | Scenario composition | QUALITATIVE | **NAME** | retype `categorical`, options (baseline, policy, stress, custom), default `baseline` | catalog "Scenario composition" |
| 43 | `scenario_visibility` | Combined | Scenario visibility | Visibility | QUALITATIVE | **NAME** | retype `categorical`, options (private, team, organisation, public), default `private` | catalog "Visibility" — an access level |
| 44 | `signal_extraction` | Combined | Signal extraction | LLM prompt extraction | QUALITATIVE | **NAME** | retype `categorical`, options (llm, regex, manual), default `llm` | catalog "LLM prompt extraction" |
| 45 | `signal_scoring` | Combined | Signal scoring | Weighted scoring function | QUALITATIVE | **NAME** | retype `categorical`, options (weighted, rule_based, llm), default `weighted` | catalog "Weighted scoring function" |
| 46 | `stochastic_scenarios` | Combined | Stochastic scenarios | Two-stage stochastic programming | QUALITATIVE | **AMBIGUOUS** | defer | catalog "Two-stage stochastic programming" names a *method*; the prior pack read it as a leaf count, which the catalog does not state |
| 47 | `arrears_management` | Consumer | Arrears management | Financial model | — | **NAME** | retype `bool`, default `false` | catalog "Financial model"; a programme-presence flag |
| 48 | `bill_shock_protection` | Consumer | Bill shock protection | Tariff model | — | **NAME** | retype `bool`, default `false` | catalog "Tariff model"; a protection-presence flag |
| 49 | `compensation_mechanisms` | Consumer | Compensation | Financial model | — | **NAME** | retype `bool`, default `false` | catalog "Compensation"; a mechanism-presence flag |
| 50 | `debt_management` | Consumer | Debt management | Financial model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Financial model"; an organisational capability |
| 51 | `disconnection_protection` | Consumer | Disconnection protection | Compliance model | — | **NAME** | retype `bool`, default `false` | catalog "Compliance model"; a protection-presence flag |
| 52 | `dispute_resolution_mechanism` | Consumer | Dispute resolution | Compliance model | QUALITATIVE | **NAME** | retype `categorical`, options (regulator, arbitration, court), default `regulator` | catalog "Dispute resolution" — an institutional venue |
| 53 | `payment_plans` | Consumer | Payment plans | Financial model | — | **NAME** | retype `bool`, default `false` | catalog "Financial model"; a programme-presence flag |
| 54 | `prepayment_metering` | Consumer | Prepayment | Metering model | — | **NAME** | retype `bool`, default `false` | catalog "Prepayment"; a metering-mode switch |
| 55 | `assignment_rights` | Contract | Assignment rights | Contract model | — | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause, present or absent |
| 56 | `change_of_control` | Contract | Change of control | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 57 | `concession_terms` | Contract | Concession terms | Contract model | QUALITATIVE | **AMBIGUOUS** | defer | contract *terms* (plural); the numeric sibling is `concession_duration` = years |
| 58 | `cross_default` | Contract | Cross-default | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 59 | `default_events` | Contract | Events of default | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 60 | `direct_agreement` | Contract | Direct agreement | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; whether a bilateral agreement exists |
| 61 | `distribution_conditions` | Contract | Distribution conditions | Financial model | QUALITATIVE | **AMBIGUOUS** | defer | a condition *class*; no source in the tree enumerates the classes |
| 62 | `environmental_representations` | Contract | Environmental reps | Contract model | — | **NAME** | retype `bool`, default `false` | catalog "Environmental reps"; a clause |
| 63 | `licence_conditions` | Contract | Licence conditions | Compliance model | QUALITATIVE | **AMBIGUOUS** | defer | licence *text/enum*; the numeric sibling is `licence_fees` = USD/MW/year |
| 64 | `material_adverse_change` | Contract | MAC clause | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "MAC clause"; a clause |
| 65 | `ppa_arbitration_venue` | Contract | Arbitration venue | Metadata | — | **NAME** | retype `categorical`, options (icc, lcia, uncitral, local_court), default `lcia` | catalog "Arbitration venue" — a closed set of fora |
| 66 | `ppa_change_in_law` | Contract | Change in law | Contract model | — | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 67 | `ppa_curtailment_compensation` | Contract | Curtailment compensation | Contract model | — | **AMBIGUOUS** | defer | could be a bool (is compensation owed) or a QUANTITY (USD/MWh); the catalog says only "Contract model" |
| 68 | `ppa_dispute_resolution` | Contract | Dispute resolution | Contract model | QUALITATIVE | **NAME** | retype `categorical`, options (regulator, arbitration, court), default `arbitration` | catalog "Dispute resolution"; sibling of `dispute_resolution_mechanism` |
| 69 | `ppa_force_majeure` | Contract | Force majeure | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 70 | `ppa_governing_law` | Contract | Governing law | Metadata | — | **NAME** | retype `categorical`, options (local, english, new_york, other), default `local` | catalog "Governing law" — a closed set of jurisdictions |
| 71 | `ppa_pricing_formula` | Contract | PPA pricing | Pricing model | — | **NAME** | retype `categorical`, options (fixed, escalating, indexed, merchant), default `fixed` | catalog "PPA pricing"; a formula family |
| 72 | `ppa_take_or_pay` | Contract | Take-or-pay provisions | Contract model | — | **NAME** | retype `bool`, default `false` | catalog "Take-or-pay provisions"; a clause |
| 73 | `refinancing_terms` | Contract | Refinancing | Financial model | QUALITATIVE | **AMBIGUOUS** | defer | negotiated *terms*; no single reading |
| 74 | `reserve_accounts` | Contract | Reserve accounts | Financial model | BASE-NEEDED | **QUANTITY** | unit `USD million`, range [0.0, 50000.0], default `0.0` | siblings `regulatory_asset_base` = USD million, `allowed_revenue_requirement` = USD million/year |
| 75 | `social_representations` | Contract | Social reps | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Social reps"; a clause |
| 76 | `step_in_rights` | Contract | Step-in rights | Contract model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Contract model"; a clause |
| 77 | `cold_storage_load` | Demand | Cold chain energy demand | Cold chain model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Cold chain energy demand"; sibling `fishing_community_load` = MW |
| 78 | `construction_load` | Demand | Temporary construction load | Temporary load model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 1000.0], default `0.0` | catalog "Temporary construction load"; sibling `fishing_community_load` = MW |
| 79 | `data_centre_demand` | Demand | New data centre load | Data centre load profiling (constant + burst) | — | **QUANTITY** | unit `MW`, range [0.0, 5000.0], default `0.0` | catalog "New data centre load"; sibling `fishing_community_load` = MW |
| 80 | `demand_growth_profile` | Demand | Shape of growth curve | Growth curve shape fitting | — | **NAME** | retype `categorical`, options (linear, logistic, gompertz), default `logistic` | catalog "Shape of growth curve" + "Growth curve shape fitting" |
| 81 | `electrification_timeline` | Demand | Year to reach target | Adoption diffusion (Bass) | — | **QUANTITY** | unit `years`, range [0.0, 50.0], default `20.0` | catalog "Year to reach target"; siblings `renewable_target_year`, `net_zero_year` = years |
| 82 | `emergency_shelter_load` | Demand | Emergency shelter load | Emergency load model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Emergency shelter load"; sibling `fishing_community_load` = MW |
| 83 | `mining_demand_growth` | Demand | Additional mining load growth | Mining load profiling | BASE-NEEDED | **AMBIGUOUS** | defer | "Additional mining load growth" reads as MW (an added load) or 1/year (a rate); the catalog gives no unit and both fit |
| 84 | `post_harvest_processing_load` | Demand | Post-harvest processing load | Processing energy model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Post-harvest processing load"; sibling `fishing_community_load` = MW |
| 85 | `tourism_load` | Demand | Tourism seasonal load | Seasonal load profile | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Tourism seasonal load"; sibling `fishing_community_load` = MW |
| 86 | `wastewater_treatment_load` | Demand | Wastewater treatment energy | Treatment energy model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Wastewater treatment energy"; sibling `fishing_community_load` = MW |
| 87 | `water_pumping_load` | Demand | Water utility pumping | Pumping energy model | BASE-NEEDED | **QUANTITY** | unit `MWh/year`, range [0.0, 1e6], default `0.0` | catalog "Water utility pumping"; sibling `electrolysis_electricity_demand_mwh_per_year` = MWh/year |
| 88 | `ami_infrastructure` | Digital | AMI infrastructure | System model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "AMI infrastructure"; a capability flag |
| 89 | `asset_management_systems` | Digital | EAM | System model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "EAM"; a system-presence flag |
| 90 | `billing_systems` | Digital | Billing | System model | — | **NAME** | retype `bool`, default `false` | catalog "Billing"; a system-presence flag |
| 91 | `communication_protocols` | Digital | Protocols | Metadata | — | **NAME** | retype `categorical`, options (iec_61850, dnp3, modbus, mqtt), default `iec_61850` | catalog "Protocols" — a closed set of standards |
| 92 | `customer_information_systems` | Digital | CIS | System model | — | **NAME** | retype `bool`, default `false` | catalog "CIS"; a system-presence flag |
| 93 | `cyber_incident_response` | Digital | Incident response | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Incident response"; a capability flag |
| 94 | `data_backup_recovery` | Digital | Backup & recovery | System model | — | **NAME** | retype `bool`, default `false` | catalog "Backup & recovery"; a capability flag |
| 95 | `der_management_systems` | Digital | DERMS | System model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "DERMS"; a capability flag |
| 96 | `outage_management_systems` | Digital | OMS | System model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "OMS"; a capability flag |
| 97 | `work_management_systems` | Digital | WMS | System model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "WMS"; a capability flag |
| 98 | `cumulative_impact_assessment` | EnvSoc | CIA | Impact assessment | — | **NAME** | retype `bool`, default `false` | catalog "CIA"; an assessment-presence flag |
| 99 | `emergency_preparedness` | EnvSoc | Emergency prep | Compliance model | — | **NAME** | retype `bool`, default `false` | catalog "Emergency prep"; a capability flag |
| 100 | `equator_principles` | EnvSoc | Equator Principles | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Equator Principles"; an adoption flag |
| 101 | `gender_impact` | EnvSoc | Gender dimensions | Impact assessment | QUALITATIVE | **KEEP** | unit `1`, range [0.0, 1.0], default `0.5` | catalog "Gender dimensions"; a normalised score, sibling `resilience_score` = unit `1` |
| 102 | `grievance_redress_mechanism` | EnvSoc | GRM | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "GRM"; sibling `grievance_redress_effectiveness` = unit `1` carries the numeric reading |
| 103 | `health_impact_morbidity` | EnvSoc | Illness cases | Health impact assessment | — | **AMBIGUOUS** | defer | a real quantity in cases/year, but the pint registry has no `case` base dimension — the retype needs `case = [case]` added to `units.py` first |
| 104 | `ilo_conventions` | EnvSoc | ILO conventions | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "ILO conventions"; an adoption flag |
| 105 | `stakeholder_engagement_plan` | EnvSoc | SEP | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "SEP"; a plan-presence flag |
| 106 | `water_pollution_load` | EnvSoc | Pollution load | Impact assessment | BASE-NEEDED | **QUANTITY** | unit `kg/year`, range [0.0, 1e6], default `0.0` | catalog "Pollution load"; the registry parses kg/year. Prior pack said kg BOD/yr, which the registry does not parse |
| 107 | `worker_grievance_mechanism` | EnvSoc | Grievance mechanism | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Grievance mechanism"; a mechanism-presence flag |
| 108 | `world_bank_esf` | EnvSoc | World Bank ESF | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "World Bank ESF"; an adoption flag |
| 109 | `critical_mineral_dependencies` | Geopol | Critical minerals | Supply chain model | — | **KEEP** | unit `1`, range [0.0, 1.0], default `0.2` | catalog "Critical minerals"; an import-dependency share, sibling `sanctions_exposure` = unit `1` |
| 110 | `export_competitiveness` | Geopol | Export competitiveness | Trade model | QUALITATIVE | **KEEP** | unit `1`, range [0.0, 1.0], default `0.5` | catalog "Export competitiveness"; an index on the graph's own [0,1] convention |
| 111 | `rare_earth_dependencies` | Geopol | Rare earths | Supply chain model | — | **KEEP** | unit `1`, range [0.0, 1.0], default `0.3` | catalog "Rare earths"; sibling `sanctions_exposure` = unit `1` |
| 112 | `trade_flow_parameters` | Geopol | Trade flows | Trade model | QUALITATIVE | **AMBIGUOUS** | defer | a *bundle* of trade-model parameters (`gtap`); not one scalar |
| 113 | `ac_voltage_limit` | Grid | Maximum AC voltage | Voltage level selection | BASE-NEEDED | **AMBIGUOUS** | defer | the unit is kV and the name states a ceiling, but the graph carries no nominal-voltage node; whether this is a ceiling or the selected level is unresolved |
| 114 | `market_coupling` | Grid | Market coupling | Market coupling algorithm | SCENE-SWITCH | **NAME** | retype `bool`, default `false` | catalog "Market coupling"; prior pack SCENE-SWITCH — selects whether the zone clears against neighbours |
| 115 | `trade_agreement` | Grid | Trade agreement type | Trade agreement type | SCENE-SWITCH | **NAME** | retype `categorical`, options (none, bilateral, pool, regional_pool), default `none` | catalog "Trade agreement type"; prior pack gives {Bilateral, Pool, AfSEM} |
| 116 | `cat_bond_parameters` | Insurance | Cat bonds | Financial model | QUALITATIVE | **AMBIGUOUS** | defer | a *bundle* of tranche terms; the numeric siblings are `cat_bond_spread` and `cat_bond_coupon_cost_usd` |
| 117 | `climate_risk_disclosure` | Insurance | TCFD | Compliance | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "TCFD"; a disclosure-regime flag |
| 118 | `buffer_zones` | Land | Buffer zones | Spatial analysis | — | **AMBIGUOUS** | defer | a buffer is a width in m or an area in hectares; the catalog says only "Spatial analysis" |
| 119 | `conservation_easements` | Land | Easements | Legal model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Easements"; a legal instrument, present or absent |
| 120 | `land_rights` | Land | Land rights | Legal model | QUALITATIVE | **NAME** | retype `categorical`, options (customary, statutory, mixed, none), default `customary` | catalog "Legal model" — a tenure class |
| 121 | `land_tenure` | Land | Land tenure | Legal model | QUALITATIVE | **NAME** | retype `categorical`, options (freehold, leasehold, customary, communal), default `customary` | catalog "Legal model" — a tenure class |
| 122 | `land_use_planning` | Land | Land use planning | Spatial optimisation | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Spatial optimisation"; a governance presence flag |
| 123 | `traditional_land_use` | Land | Traditional use | Spatial analysis | QUALITATIVE | **NAME** | retype `categorical`, options (none, grazing, cultivation, sacred, mixed), default `none` | catalog "Traditional use"; a use class |
| 124 | `balance_of_payments` | Macro | Balance of payments | BoP model | BASE-NEEDED | **QUANTITY** | unit `USD/year`, range [-1e12, 1e12], default `0.0` | catalog "BoP model"; sibling `remittance_flows` = USD/year. A signed annual flow |
| 125 | `country_risk_rating` | Macro | Country risk rating | Country risk model | QUALITATIVE | **NAME** | retype `categorical`, options (aaa, aa, a, bbb, bb, b, ccc, d), default `b` | catalog "Country risk rating"; the same scale as `carbon_credit_rating` |
| 126 | `current_account_balance` | Macro | Current account balance | CA model | BASE-NEEDED | **QUANTITY** | unit `USD/year`, range [-1e12, 1e12], default `0.0` | catalog "CA model"; sibling `remittance_flows` = USD/year. Signed |
| 127 | `debt_sustainability` | Macro | Debt sustainability | DSA model | BASE-NEEDED | **AMBIGUOUS** | defer | a DSA *model* output; could be a ratio (unit `1`) or a horizon (years), and the catalog gives no unit |
| 128 | `exchange_rate_usd_local` | Macro | Exchange rate (USD/local) | Exchange rate model | QUALITATIVE | **AMBIGUOUS** | defer | a real FX rate, but `USD/local` does not parse — the registry has `USD = [currency]` and no local-currency base; needs `local = [currency]` added to `units.py` |
| 129 | `exchange_rate_volatility` | Macro | Exchange rate volatility | FX volatility model | BASE-NEEDED | **QUANTITY** | unit `1/year`, range [0.0, 2.0], default `0.1` | catalog "FX volatility model" (GARCH); the volatility of a rate is 1/year |
| 130 | `external_debt` | Macro | External debt | Debt model | BASE-NEEDED | **QUANTITY** | unit `USD`, range [0.0, 1e13], default `0.0` | catalog "Debt model"; sibling `loss_reduction_investment` = USD |
| 131 | `foreign_direct_investment` | Macro | Foreign direct investment | FDI model | BASE-NEEDED | **QUANTITY** | unit `USD/year`, range [0.0, 1e12], default `0.0` | catalog "FDI model"; sibling `remittance_flows` = USD/year |
| 132 | `foreign_exchange_reserves` | Macro | Foreign exchange reserves | FX reserves model | BASE-NEEDED | **QUANTITY** | unit `USD`, range [0.0, 1e12], default `0.0` | catalog "FX reserves model"; sibling `loss_reduction_investment` = USD |
| 133 | `fuel_price_scenario` | Macro | Fuel price scenario | Fuel price scenario generator | QUALITATIVE | **NAME** | retype `categorical`, options (base, high, low, net_zero), default `base` | catalog "Fuel price scenario generator"; selects among the shipped price nodes |
| 134 | `official_development_assistance` | Macro | Official development assistance | ODA model | BASE-NEEDED | **QUANTITY** | unit `USD/year`, range [0.0, 1e11], default `0.0` | catalog "ODA model"; sibling `remittance_flows` = USD/year |
| 135 | `remittance_dependency` | Macro | Remittance dependency | Remittance model | BASE-NEEDED | **DEAD** | `status: deprecated`, `deprecated_by: remittance_income_share` | `remittance_income_share` carries unit `1`, default 0.05 and affects 1 node; this node is the same quantity with zero readers |
| 136 | `collusion` | Market | Collusion detection | Collusion detection | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Collusion detection"; a detection-capability flag |
| 137 | `new_entrants` | Market | Market entry | Market entry model | — | **NAME** | retype `bool`, default `false` | catalog "Market entry"; a market-entry flag |
| 138 | `number_of_retailers` | Market | Number of retailers | Number of retailers | — | **KEEP** | unit `1`, range [1.0, 1000.0], default `5.0` | catalog "Number of retailers"; sibling `number_of_generators` = unit `1` (the graph spells counts dimensionless) |
| 139 | `retail_competition` | Market | Retail competition | Retail competition model | — | **KEEP** | unit `1`, range [0.0, 1.0], default `0.5` | catalog "Retail competition model"; sibling `market_concentration` = unit `1` |
| 140 | `collateral_valuation` | MktOps | Collateral valuation | Financial model | — | **AMBIGUOUS** | defer | "Collateral valuation" names a *method* (market/notional/model); the numeric sibling is `collateral_requirements` = unit `1` |
| 141 | `insider_trading_rules` | MktOps | Insider trading | Compliance | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Insider trading"; a rule-set flag |
| 142 | `market_abuse_prevention` | MktOps | Market abuse | Compliance | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Market abuse"; a surveillance flag |
| 143 | `novation_terms` | MktOps | Novation | Financial model | QUALITATIVE | **NAME** | retype `categorical`, options (none, full, partial), default `full` | catalog "Novation"; a clearing term |
| 144 | `trade_repository` | MktOps | Trade repository | Compliance | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Trade repository"; an institutional presence flag |
| 145 | `line_outage_end` | Outage | When the outage ends | Temporal outage model | PRODUCT | **QUANTITY** | unit `hours`, range [0.0, 8760.0], default `6.0` | sibling `line_outage_duration` = hours/event; the window is end minus start |
| 146 | `line_outage_start` | Outage | When the outage begins | Temporal outage model | PRODUCT | **QUANTITY** | unit `hours`, range [0.0, 8760.0], default `0.0` | siblings `line_outage_hours_per_year` = hours/year, `maintenance_duration` = hours/event; an hour-of-year. `whatif/outage.py` names the window |
| 147 | `microgrid_deployment` | Outage | Microgrid deployment | Microgrid deployment | — | **QUANTITY** | unit `connections/year`, range [0.0, 1e6], default `0.0` | sibling `mini_grid_deployment` = connections/year |
| 148 | `regulatory_accounts` | RegFin | Regulatory accounts | Accounting model | — | **AMBIGUOUS** | defer | an *account set*; the numeric siblings are `regulatory_asset_base` and `allowed_revenue_requirement` |
| 149 | `drought_frequency` | Sector | Drought frequency multiplier | Drought frequency model | GATE-SCENE-SWITCH | **KEEP** | unit `1`, range [0.0, 5.0], default `1.0` | catalog "Drought frequency multiplier"; sibling `hydro_drought_multiplier` = unit `1` |
| 150 | `drought_severity` | Sector | Drought severity multiplier | Drought severity model | GATE-SCENE-SWITCH | **KEEP** | unit `1`, range [0.0, 5.0], default `1.0` | catalog "Drought severity multiplier"; sibling `hydro_drought_multiplier` = unit `1` |
| 151 | `ev_adoption_timeline` | Sector | Year to reach EV share | Adoption timeline | — | **QUANTITY** | unit `years`, range [0.0, 50.0], default `20.0` | catalog "Year to reach EV share"; sibling `renewable_target_year` = years |
| 152 | `ev_battery_size` | Sector | Average EV battery size | EV battery size | — | **QUANTITY** | unit `kWh`, range [20.0, 200.0], default `60.0` | catalog "Average EV battery size"; the registry parses kWh |
| 153 | `ev_efficiency` | Sector | EV efficiency | EV efficiency | — | **QUANTITY** | unit `kWh/km`, range [0.05, 0.5], default `0.18` | catalog "EV efficiency"; the registry parses kWh/km |
| 154 | `fishing_vessel_fuel` | Sector | Fishing vessel fuel | Vessel fuel model | BASE-NEEDED | **QUANTITY** | unit `litre/year`, range [0.0, 1e6], default `0.0` | catalog "Vessel fuel model"; the registry parses litre/year |
| 155 | `hydrogen_storage_type` | Sector | Storage type | Storage type | QUALITATIVE | **NAME** | retype `categorical`, options (salt_cavern, above_ground, pipeline), default `salt_cavern` | catalog "Storage type" (PyPSA-Earth-Sec underground) |
| 156 | `military_energy_demand` | Sector | Military energy demand | Military energy model | BASE-NEEDED | **QUANTITY** | unit `MW`, range [0.0, 500.0], default `0.0` | catalog "Military energy model"; sibling `fishing_community_load` = MW |
| 157 | `mining_haulage` | Sector | Mining haulage | Haulage electrification | BASE-NEEDED | **QUANTITY** | unit `tonne*km/year`, range [0.0, 1e10], default `0.0` | sibling `transport_logistics` = tonne*km/year |
| 158 | `mining_hydrogen_haulage` | Sector | Hydrogen haulage in mining | Hydrogen haulage | BASE-NEEDED | **QUANTITY** | unit `tonne*km/year`, range [0.0, 1e10], default `0.0` | sibling `transport_logistics` = tonne*km/year |
| 159 | `clustering_method` | Spatial | Clustering method | Clustering method selection | SCENE-SWITCH | **NAME** | retype `categorical`, options (kmeans, hac, greedy_modularity, custom), default `kmeans` | catalog implementation names all four: `busmap_by_kmeans`, `_hac`, `_greedy_modularity`, `_custom_busmap` |
| 160 | `custom_gis_boundary` | Spatial | Custom GIS boundary | Custom GIS polygons | SCENE-SWITCH | **AMBIGUOUS** | defer | a geometry or a path, not a scalar; no type for it |
| 161 | `distribution_detail` | Spatial | Distribution detail | Distribution detail level | SCENE-SWITCH | **NAME** | retype `categorical`, options (aggregate, feeder, settlement), default `aggregate` | catalog "Aggregate vs. feeder vs. settlement" names the three levels |
| 162 | `spatial_clustering` | Spatial | Spatial clustering | Spatial clustering | SCENE-SWITCH | **AMBIGUOUS** | defer | overlaps `clustering_method` and `spatial_resolution`; which of the three is the selector is not determinable from the catalog |
| 163 | `spatial_resolution` | Spatial | Spatial resolution | K-means clustering | SCENE-SWITCH | **AMBIGUOUS** | defer | could be the cluster count (unit `1`) or the same selector as `clustering_method`; the catalog gives "K-means clustering" and the name says resolution |
| 164 | `transmission_detail` | Spatial | Transmission detail | Transmission detail level | SCENE-SWITCH | **NAME** | retype `categorical`, options (copper_plate, zonal, nodal), default `zonal` | catalog "Copper plate vs. zonal vs. nodal" names the three levels |
| 165 | `coal_retirement_schedule` | Supply | Coal retirement years | Retirement scheduling MILP | QUALITATIVE | **QUANTITY** | unit `years`, range [0.0, 100.0], default `25.0` | sibling `net_zero_year` = years; a retirement *year*. `crossval.py` compares it to 2045 |
| 166 | `hydro_reservoir_level` | Supply | Initial reservoir level | Reservoir operation (SDP) | BASE-NEEDED | **KEEP** | unit `1`, range [0.0, 1.0], default `0.5` | catalog "Initial reservoir level"; a level as a share of full supply is dimensionless |
| 167 | `maintenance_schedule` | Supply | Planned maintenance timing | Maintenance scheduling MILP | QUALITATIVE | **AMBIGUOUS** | defer | a scheduling *artefact*; the numeric sibling is `maintenance_frequency` = events/year |
| 168 | `nuclear_lead_time` | Supply | Nuclear construction lead time | Construction lead-time constraint | BASE-NEEDED | **QUANTITY** | unit `years`, range [0.0, 25.0], default `7.0` | siblings `transmission_lead_time` = years, `cross_border_permitting_time` = years |
| 169 | `startup_cost_coal` | Supply | Coal start-up cost | Start-up cost | BASE-NEEDED | **QUANTITY** | unit `USD`, range [0.0, 1e6], default `40000.0` | catalog names `n.generators.start_up_cost`; pypsa declares that attribute unit "currency". A per-start unit needs a `start` base the registry lacks |
| 170 | `startup_cost_gas` | Supply | Gas start-up cost | Start-up cost | BASE-NEEDED | **QUANTITY** | unit `USD`, range [0.0, 1e6], default `20000.0` | same pypsa attribute, unit "currency" |
| 171 | `wave_energy_converter_type` | Supply | Wave energy converter type | WEC model | QUALITATIVE | **NAME** | retype `categorical`, options (point_absorber, oscillating_water_column, overtopping, attenuator), default `point_absorber` | catalog "WEC model"; a closed set of converter types |
| 172 | `wind_offshore_platform` | Supply | Platform type | Floating vs. fixed platform | QUALITATIVE | **NAME** | retype `categorical`, options (fixed, floating), default `fixed` | catalog "Floating vs. fixed platform" names the two |
| 173 | `double_tax_treaty` | Tax | Treaty network | Treaty lookup | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Treaty lookup"; whether a treaty is in force |
| 174 | `tax_holiday_conditions` | Tax | Conditions for holiday | Constraint | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Constraint"; sibling `tax_holiday_duration` = years is the numeric reading |
| 175 | `tax_incentive_zones` | Tax | Special economic zones | Spatial override | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Spatial override"; a legal designation flag |
| 176 | `thin_capitalisation_rules` | Tax | Thin cap rules | Constraint | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Constraint"; sibling `thin_capitalisation_limit` = unit `1` is the numeric reading |
| 177 | `transfer_pricing_rules` | Tax | Transfer pricing | Compliance model | QUALITATIVE | **NAME** | retype `bool`, default `false` | catalog "Compliance model"; a regime flag |
| 178 | `foresight` | Temporal | Foresight type | Foresight type | QUALITATIVE | **NAME** | retype `categorical`, options (perfect, myopic), default `perfect` | catalog "Foresight type" — two modes |
| 179 | `temporal_aggregation` | Temporal | Temporal aggregation | Temporal aggregation | SCENE-SWITCH | **NAME** | retype `categorical`, options (none, tsam, representative_days), default `none` | catalog "Temporal aggregation" |
| 180 | `temporal_clustering` | Temporal | Temporal clustering | Temporal clustering | SCENE-SWITCH | **NAME** | retype `categorical`, options (kmeans, hac, tsam), default `kmeans` | catalog "Temporal clustering" |
| 181 | `temporal_resolution` | Temporal | Temporal resolution | Snapshot frequency | SCENE-SWITCH | **QUANTITY** | unit `hours`, range [0.25, 24.0], default `1.0` | catalog "Snapshot frequency"; siblings `settlement_period` = hours, `maintenance_duration` = hours/event |

---

## 3. Summary by classification

| classification | count | meaning |
|---|---:|---|
| **NAME** | 92 | a procedure, standard, technology or selector — not a quantity |
| **QUANTITY** | 41 | a real physical or economic quantity with a discoverable unit |
| **KEEP** | 13 | genuinely dimensionless **and** a real scalar |
| **DEAD** | 1 | superseded by a shipped node |
| **AMBIGUOUS** | 34 | genuinely undecidable from the tree — deferred, not forced |
| **total** | **181** | |

**Status as of batch 57 (2026-10-24).** The **KEEP** class is shipped: all
thirteen rows carry the unit `1`, the range and the default this document's §2
table states, and `config/prg.yaml` no longer holds the `500000.0` sentinel for
any of them. The retype was applied in `build_batch57` of
`scripts/build/prg_coupler.py`, which asserts each row's pre-merge placeholder
state before overwriting it, so a later batch that retypes one of these first
fails this build rather than being silently overwritten. The QUANTITY rows were
done at batch 54; the NAME, AMBIGUOUS and DEAD rows are still open. See
`docs/prg-status.md` for what the thirteen measured.

### NAME, broken down by the action it needs

| action | count |
|---|---:|
| retype `bool` | 55 |
| retype `categorical` with options | 33 |
| **BLOCKED** — no schema type represents it | 4 |

The four BLOCKED nodes are real NAME findings with no available action today:
`scenario_description`, `scenario_owner`, `scenario_tag` are free text and
`parameter_overrides` is a mapping. `ParameterType` is
`float`, `int`, `bool`, `categorical`, `timeseries`, `spatial` — verified against
`src/alea/prg/views.py:72`. There is no text or mapping type. These four should
be **recorded and left**, not retyped to something wrong.

### QUANTITY, by unit

| unit | count | nodes |
|---|---:|---|

| `MW` | 8 | `cold_storage_load`, `construction_load`, `data_centre_demand`, `emergency_shelter_load`, `post_harvest_processing_load`, `tourism_load`, `wastewater_treatment_load`, `military_energy_demand` |
| `USD/year` | 6 | `adaptation_benefits`, `adaptation_costs`, `balance_of_payments`, `current_account_balance`, `foreign_direct_investment`, `official_development_assistance` |
| `USD` | 5 | `resilience_investment`, `external_debt`, `foreign_exchange_reserves`, `startup_cost_coal`, `startup_cost_gas` |
| `years` | 4 | `electrification_timeline`, `ev_adoption_timeline`, `coal_retirement_schedule`, `nuclear_lead_time` |
| `events/year` | 3 | `cold_snap_frequency`, `extreme_weather_events`, `heatwave_frequency` |
| `hours` | 3 | `line_outage_start`, `line_outage_end`, `temporal_resolution` |
| `tonne*km/year` | 2 | `mining_haulage`, `mining_hydrogen_haulage` |
| `1/year` | 1 | `exchange_rate_volatility` |
| `MWh/year` | 1 | `water_pumping_load` |
| `USD million` | 1 | `reserve_accounts` |
| `connections/year` | 1 | `microgrid_deployment` |
| `degC` | 1 | `climate_sensitivity` |
| `kWh` | 1 | `ev_battery_size` |
| `kWh/km` | 1 | `ev_efficiency` |
| `kg/year` | 1 | `water_pollution_load` |
| `litre/year` | 1 | `fishing_vessel_fuel` |
| `m` | 1 | `sea_level_rise` |

---

## 4. The proposal for the next batch

**Do the 88 nodes whose action is `bool` or `categorical`.** Not the quantities.

### Why that subset and not the quantities

1. **It needs no unit decision.** A `bool` or a `categorical` carries no unit
   and no range, so the retype cannot be wrong about a dimension. Every
   quantity retype in §2 rests on a sibling's shipped unit, which is strong
   evidence but is still an inference; the NAME retypes rest on the catalog's
   own algorithm column naming a switch or a closed set.
2. **It is the largest defensible slice.** 88 of 181 in one batch, each
   verified constructible against the model (§4.3).
3. **It makes the graph refuse a wrong value — for the categoricals.** Measured
   on a copy of the YAML: a categorical rejects a level it does not declare —

   ```
   trade_agreement='nonsense' is not one of the levels the graph declares for
   it (['bilateral', 'pool', 'regional_pool'])
   ```

   That is the probe against this survey's own three-level proposal. The
   shipped batch declares a fourth, `none` (a zone that trades on bilateral
   contracts alone), so the message as shipped lists all four. The arithmetic
   of the point is unchanged.

   while a `float` on `[0, 1e6]` accepts a procedure name's placeholder of
   500,000 silently. That is the defect being closed.

   **The bool retype does NOT close it on its own, and this was measured, not
   assumed.** A `bool` with `range: null` accepts `7.0`:

   ```
   market_coupling: type bool, range null  ->  propagate(market_coupling=7.0) ACCEPTED
   market_coupling: type bool, range [0,1] ->  propagate(market_coupling=7.0) REFUSED
   ```

   `range: null` is the shipped convention — **23 of the 24 bools in the graph
   carry no range**, and only `cross_border_trading` declares `[0, 1]`. So a
   batch that retypes 55 nodes to `bool` with no range closes nothing: a
   scenario can still set a procedure name to 500,000. **The batch must give
   every retyped bool an explicit `range: [0.0, 1.0]`.** That is the whole
   point of the slice, and the convention it departs from is the defect.
4. **It costs nothing structurally.** Measured on the same copy:
   `uncoupled()` stays at its pre-batch value, the dead-knob register stays
   224, and the unit checker stays at 1 inconsistent / 0 undecidable. The
   retype changes what a scenario may *say*, not what the arithmetic *does*.
   (This paragraph first read `uncoupled()` 234. Re-measured on the tree at
   batch 49 it is **236**, and 236 after batch 50: none of the 88 is named by
   an equation, so the register cannot move. The 234 was taken on an earlier
   tree and is corrected here rather than left as a number a later batch
   would diff against.)

### What the batch would be

| | count |
|---|---:|
| nodes retyped `bool` | 55 |
| nodes retyped `categorical` | 33 |
| **total** | **88** |

Every one must be authored in `config/prg.yaml`, following the batch-36
precedent in `scripts/build/prg_coupler.py:15421`:

- **categorical** — `type: categorical`, `unit: null`, `range: null`,
  `categories: [...]`, a level name as `default`, `determinism: policy`.
- **bool** — `type: bool`, `unit: null`, `range: [0.0, 1.0]`,
  `default: false`. **The range is not optional** — see §4.3.

### The two canaries the batch must ship

1. **A wrong level is refused.** Set a retyped categorical to a string it does
   not declare and assert the validation failure names the node and lists its
   levels. Verified as a real refusal above, not assumed.
2. **A wrong magnitude is refused.** Set a retyped bool to `7.0` and assert the
   range refusal. **Canary this on the retyped node specifically** — the
   shipped convention (`range: null`) accepts `7.0`, so a test written against
   a shipped bool would pass while the batch's own nodes stayed unguarded.

### What the batch must NOT do

- **Do not deprecate anything except `remittance_dependency`.** The
  `uncoupled()` docstring is explicit that a tombstone stays in the register,
  and `tests/ci/test_prg_catalog.py:523` asserts `deprecated_by` names a live
  node. One deprecation is safe; a wave of them would need every alias entry
  authored and would close nothing.
- **Do not give a free node `default: null`.** Canaried: `propagate` refuses a
  parameter set missing a non-derived node —

  ```
  the parameter set is missing ['adaptation_benefits']; a parameter that is not
  derived has no equation to compute it from
  ```

  So a QUANTITY retype must supply a real default. There are zero free nodes
  with `default: None` in the shipped graph, and that is why.
- **Do not add a unit the pint registry cannot parse.** Measured: `USD/local`,
  `USD/start`, `cases/year` and `m3/year` all fail `ureg.parse_units`. Each
  would turn its equation from *checked* to *undecidable*, which the
  `units.py` docstring calls a hole rather than a pass.

### The follow-on batches, in order

| batch | slice | why it comes next |
|---|---|---|
| 2 | the **41 QUANTITY** nodes | each needs a unit, a range and a real default; the evidence is in §2 and the registry parses every proposed string (verified) |
| 3 | the **3 registry-gap quantities** (`health_impact_morbidity`, `exchange_rate_usd_local`, plus any `USD/start` desire) | each needs a base dimension added to `units.py` first (`case`, `local`, `start`) |
| 4 | the **34 AMBIGUOUS** | each needs a research pack that names the object; forcing them now would be the guessing the brief forbids |

### Outcome of batch 2 (batch 54, 2026-10-24)

Done, with one coupling and 40 retypes. Where this survey and a coupling pack
disagreed, the pack was re-measured against the graph's own convention:

- **Four `_load` nodes stay `MW`.** The demand pack
  (`docs/research/coupling-packs/demand-sector.md`) proposed `MWh/year` for
  `cold_storage_load`, `post_harvest_processing_load`, `tourism_load` and
  `wastewater_treatment_load`. Every typed `_load` node in the graph is `MW`
  and every `_demand` node is an energy per year. The survey's unit stands; the
  pack's reading would have made these four the only energy-per-year members
  of a twelve-node family.
- **`coal_retirement_schedule` keeps the offset reading.** The spec's worked
  example uses the absolute year 2050, which the graph's `[0, 100]` year
  convention refuses. Offset kept, mismatch recorded in the node prose.
- **`temporal_resolution` is not a retype.** It is the same quantity
  `tsam_segment_hours` already derives as `24 / tsam_segments`, and the range
  proposed here (`[0.25, 24]`) is exactly that node's image under `24/r` --
  which is the strongest evidence in this document that the two are one
  quantity. It became `derived` rather than a dial, and the response canary
  (2.0 h at 12 segments/day) is the check a defaults-only value test cannot
  make.

The other 40 are retyped with a unit, a range and a real default but remain
`role: free` and remain in the dead-knob register: the packs deferred them
because a share needs a base and a load needs an intensity, and the graph
carries neither. **A retype gives the node a dimension, not a citation** -- the
defaults are the catalog's own value where it has one and a stated mid-range
where it does not.

---

## 5. Genuinely ambiguous nodes

Listed rather than forced. 34 nodes, grouped by what is
missing.

**A bundle, not a scalar — the catalog row names a parameter *set*:**

- `article_6_2_parameters` — a rulebook *bundle*, plural in the catalog name; no bundle type exists
- `article_6_4_parameters` — a rulebook bundle, same as `article_6_2_parameters`
- `corsia_parameters` — a compliance *bundle*
- `mrv_parameters` — a protocol *bundle* with tiers
- `cat_bond_parameters` — a *bundle* of tranche terms; the numeric siblings are `cat_bond_spread` and `cat_bond_coupon_cost_usd`
- `trade_flow_parameters` — a *bundle* of trade-model parameters (`gtap`); not one scalar
- `regulatory_accounts` — an *account set*; the numeric siblings are `regulatory_asset_base` and `allowed_revenue_requirement`
- `resilience_metrics` — a metrics *set*; the schema has no set type
- `concession_terms` — contract *terms* (plural); the numeric sibling is `concession_duration` = years
- `licence_conditions` — licence *text/enum*; the numeric sibling is `licence_fees` = USD/MW/year
- `refinancing_terms` — negotiated *terms*; no single reading
- `adaptation_measures` — "Portfolio model" — a portfolio is not a scalar, and no source in the tree enumerates the options
- `failure_history` — an event *record set*, not a scalar; the rates it would feed already exist (`forced_outage_rate`)
- `maintenance_history` — a record set, same as `failure_history`
- `maintenance_schedule` — a scheduling *artefact*; the numeric sibling is `maintenance_frequency` = events/year


**A real quantity the unit registry cannot yet express:**

- `health_impact_morbidity` — a real quantity in cases/year, but the pint registry has no `case` base dimension — the retype needs `case = [case]` added to `units.py` first
- `exchange_rate_usd_local` — a real FX rate, but `USD/local` does not parse — the registry has `USD = [currency]` and no local-currency base; needs `local = [currency]` added to `units.py`


**No schema type represents it:**

- `custom_gis_boundary` — a geometry or a path, not a scalar; no type for it


**Two readings fit and the catalog disambiguates neither:**

- `mining_demand_growth` — "Additional mining load growth" reads as MW (an added load) or 1/year (a rate); the catalog gives no unit and both fit
- `buffer_zones` — a buffer is a width in m or an area in hectares; the catalog says only "Spatial analysis"
- `debt_sustainability` — a DSA *model* output; could be a ratio (unit `1`) or a horizon (years), and the catalog gives no unit
- `ppa_curtailment_compensation` — could be a bool (is compensation owed) or a QUANTITY (USD/MWh); the catalog says only "Contract model"
- `interannual_variability` — a coefficient of variation of what is unstated (inflow? wind? temperature); the reference series is not named
- `carbon_credit_vintage` — an issuance *year*; `years` is defensible but a calendar year is not a duration, so the unit string would be wrong
- `spatial_resolution` — could be the cluster count (unit `1`) or the same selector as `clustering_method`; the catalog gives "K-means clustering" and the name says resolution
- `stochastic_scenarios` — catalog "Two-stage stochastic programming" names a *method*; the prior pack read it as a leaf count, which the catalog does not state
- `collateral_valuation` — "Collateral valuation" names a *method* (market/notional/model); the numeric sibling is `collateral_requirements` = unit `1`
- `distribution_conditions` — a condition *class*; no source in the tree enumerates the classes


**Overlaps two other nodes, and which is the selector is undecidable:**

- `spatial_clustering` — overlaps `clustering_method` and `spatial_resolution`; which of the three is the selector is not determinable from the catalog


**Names a procedure with no successor to deprecate toward:**

- `efficient_frontier` — the catalog algorithm is "ω sweep" and the implementation "Loop over omega values" — it names a *procedure*; no successor node exists to deprecate it toward


**Needs a base the graph does not carry:**

- `ac_voltage_limit` — the unit is kV and the name states a ceiling, but the graph carries no nominal-voltage node; whether this is a ceiling or the selected level is unresolved


**An open register — `categorical` needs a closed list:**

- `cdm_methodologies` — an open methodology register (ACM0002, AMS-I.D, ...); categorical needs a closed list and nothing in the tree enumerates one
- `gold_standard_methodologies` — an open methodology register, same as `cdm_methodologies`
- `vcs_methodologies` — an open methodology register, same as `cdm_methodologies`


---

## 6. Method and the checks that back this report

| check | result |
|---|---|
| count via `load_graph()` | 181 |
| count via raw YAML `parameters` | 181 (agrees) |
| all `type: float` | verified as a set |
| all `role: free` | verified as a set |
| equation/edge/rule readers | 0 of 181, measured four ways |
| descriptions vs catalog labels | 181/181 identical — no extra evidence |
| prior pack coverage | 135 of 181 carry a verdict; 46 are new to this survey |
| every proposed action constructed as a `ParameterNode` | 143 of 143 construct |
| every proposed unit parses under `ureg.parse_units` | all pass except the 3 flagged registry gaps, which are deferred |
| a categorical with no `categories` | refused by the model (probed) |
| `deprecated` with no `deprecated_by` | refused by the model (probed) |
| free node with `default: null` | constructs, but `propagate` then refuses the default set (probed) |
| `bool` with `range: null` accepts `7.0` | **measured** — so the retype needs an explicit `[0,1]` |
| `bool` with `range: [0,1]` refuses `7.0` | **measured** |
| applying all 143 actions to a copy | placeholders 181 → 39; `uncoupled()` unchanged (236 on the tree at batch 49, see §4.3); dead 224 → 223; unit checker 1/0 → 1/0 |

### One finding worth carrying forward

**Deprecating a node does not remove it from the placeholder predicate.** The
copy after applying all 143 actions still reports **39** residual placeholders
where 38 were expected: `remittance_dependency` is `status: deprecated` but
still carries `unit: null` and `default: 500000.0`, because the status field
does not touch either. A future gate written as "no node ships the placeholder
signature" would count a tombstone as a defect. Scope such a gate with
`and node.status != "deprecated"`, or clear the fields on deprecation.

### Files read, not modified

- `config/prg.yaml` — read only; every canary ran on a `/tmp` copy
- `scripts/build/prg_from_catalog.py` — read `_unit_of`, `_range_for`, `_default_for`
- `scripts/build/prg_coupler.py` — read the batch-36 retype mechanism
- `src/alea/prg/views.py`, `graph.py`, `units.py` — read the type, status and unit vocabularies
- `docs/params.md` — the catalog
- `docs/research/uncoupled-classification/classification-packs.md` — prior verdicts

