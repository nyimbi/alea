# Batch rationale, moved from `config/prg_ingest/`

The ten generated batches were baked into `config/prg.yaml` on 2026-10-17,
and the fragment directory retired. `yaml.safe_dump` writes only the mapping, so
the per-batch header comments -- each batch's record of what it dropped and why --
did not survive the bake. They are reproduced verbatim below, one section per
batch, in the order the loader read them.

The counts are the merge's own report at the bake: 241 corrections, 0 refused,
0 unknown, 0 dropped, 0 redundant.

---


## `param_batch0.yaml`

```yaml
# Generated from docs/param_batch0.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R7: combined_ratio also appears in param_batch5.md; that entry is kept and this one dropped
#   R7: forced_outage_rate also appears in param_batch4.md; that entry is kept and this one dropped
#   R7: loss_ratio also appears in param_batch5.md; that entry is kept and this one dropped
#   R8: health_cost_usd_per_year -> reliability_cost_usd declared relationship='informational', which is a Strength value not a Relationship class; set to 'functional' (its strength is 'informational')
#   R8: local_jobs -> total_jobs declared relationship='informational', which is a Strength value not a Relationship class; set to 'functional' (its strength is 'informational')
#   R8: carbon_revenue_usd_per_year -> carbon_budget_ratio declared relationship='informational', which is a Strength value not a Relationship class; set to 'functional' (its strength is 'informational')
#   R4: dropped edge consumer_surplus_usd_per_year -> energy_poverty_rate -- cites 'energy_poverty_rate_definition', which no equation declares
#   R9: dropped edge carbon_price_escalated_usd_per_tco2 -> carbon_budget_ratio -- 'carbon_budget_ratio_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge fuel_price_escalated_usd_per_mwh -> marginal_cost_usd_per_mwh -- 'marginal_cost' does not hold both endpoints (gate 6)
#   R9: dropped edge fleet_emission_intensity_t_per_mwh -> emissions_mtco2_per_year -- 'emissions_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge total_water_demand_m3 -> water_availability_m3 -- 'water_availability_constraint' does not hold both endpoints (gate 6)
#   R9: dropped edge health_cost_usd_per_year -> reliability_cost_usd -- 'reliability_cost_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge local_jobs -> total_jobs -- 'total_jobs_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge carbon_revenue_usd_per_year -> carbon_budget_ratio -- 'carbon_budget_ratio_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge system_saidi_hours_per_year -> grid_reliability_target -- 'saidi_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge system_saifi_events_per_year -> grid_reliability_saifi -- 'saifi_definition' does not hold both endpoints (gate 6)
#   R21: 'gearing_ratio' range corrected from [0, 0.95] to [0, 19]. The node is
#        `debt_fraction / (1 - debt_fraction)`, a multiple of equity, and [0, 0.95]
#        is `debt_fraction`'s bound, not this node's -- the same confusion the
#        description above records for the prose, left standing in the range. The
#        image of the driver's own range [0, 0.95] is [0, 19], and at the default
#        debt_fraction = 0.7 the ratio is 2.3333, which the old range refused: the
#        node was declared out of range at its own default. The bound is derived
#        from the definition, so it moves if `debt_fraction`'s range moves.
```


## `param_batch1.yaml`

```yaml
# Generated from docs/param_batch1.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R7: digital_divide_metrics also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: smart_metering_rollout also appears in param_batch7.md; that entry is kept and this one dropped
#   R3: dropped rule 'demand_shares_over_unity' -- its condition needs arithmetic, which the cross-validation grammar refuses: residential_demand_share + commercial_demand_share + industrial_demand_share + agricultural_demand_share > 1.0
#   R3: dropped rule 'share_parameters_sum_to_unity_fuel' -- its condition needs arithmetic, which the cross-validation grammar refuses: coal_ccs_adoption + gas_ccs_adoption > 1.0
#   R3: dropped rule 'electrification_electrification_targets_exceed_demand' -- its condition needs arithmetic, which the cross-validation grammar refuses: industrial_electrification + industrial_heat_electrification > 1.5
#   R18: added 'agricultural_demand_share', which the batch's own rule names and no fragment
#        declared. The batch corrected the three sibling shares to their real values
#        (residential 0.35, commercial 0.2, industrial 0.35) and skipped the fourth, so it kept
#        the shipped placeholder 0.5 while its three siblings already summed to 0.9 -- 1.4
#        against the ceiling of 1.0 that the batch's own cross-validation rule states, and that
#        `demand_shares_bound` (Batch 11) enforces as an equation. Set to 0.1 so the four are
#        the decomposition of the total the rule describes. The omission was Batch 1's: its own
#        rule at docs/param_batch1.md:645 names all four shares, so the node was in scope.
```


## `param_batch10.yaml`

```yaml
# Generated from the Batch 10 relation set, in answer to the case-by-case review
# of the nodes the graph declared and no equation reached.
#
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# WHAT THIS BATCH IS. Batches 0-9 corrected the shipped placeholder nodes and
# added the parameters the catalog carried and the graph did not. This batch is
# the first that adds *relations*: five identities whose operands are all
# already declared, so each one closes its subject without a new operand, a new
# unit, or a modelling decision.
#
# WHY ONLY FIVE. Every other relation in the review needs an operand the graph
# does not carry -- a `generation_hydro_twh`, an `expense_ratio`, a
# `population`, a per-technology learning capex. Declaring an operand to make an
# identity writable is a modelling decision, and a batch that took those
# decisions silently would be asserting physics nobody reviewed. The five here
# are the ones where the arithmetic is over names that already exist and the
# units already agree.
#
# WHY EVERY EQUATION CARRIES A `latex`. The DSL renders LaTeX on demand and
# folds constants while doing it: `log(1 - rate) / log(2)` typesets with the
# literal `0.693147` where the base-2 doubling convention belongs. A rendering
# cannot explain a relation whose most load-bearing constant it has erased, so
# the relations here declare their own rendering and `alea.prg.service.check_latex`
# holds each one to the operand set of its arithmetic.
#
# REPAIRS APPLIED TO THIS BATCH AS DELIVERED:
#   R13: coal_eaf, gas_eaf, oil_eaf, gearing_ratio and equity_share are moved from
#        `role: free` to `role: derived` -- each is now determined by an equation
#        here, and the loader refuses a determined node that is not `derived`
#        (invariant v), because any other role lets a user set a value the
#        equation then overwrites.
#   R14: expense_ratio is declared because the accounting identity needs it. It is
#        `exogenous`, so the relation is a check on a scenario rather than a
#        derivation: the graph can say whether a scenario's expense ratio is
#        consistent with its loss and combined ratios, and it cannot invent one.
```


## `param_batch11.yaml`

```yaml
# The five arithmetic rules the cross-validation grammar refused, stated as
# bound equations instead.
#
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# WHY THESE ARE EQUATIONS AND NOT RULES. The cross-validation grammar has no
# `ast.BinOp`, deliberately: `alea.prg.crossval`'s own allowlist comment says
# "an expression like `a * b > c` is an equation the graph should state, not a
# rule buried in a condition where nothing checks it dimensionally". So a rule
# of the form `a + b > 1.0` is refused at parse, and the refusal names the right
# home for it. Five such rules were dropped from the batch set for want of that
# home. This batch is where they land.
#
# WHAT MADE THEM WRITABLE. Until now the graph could not state them either: the
# loader read each side's symbols with `dsl.parse`, which refuses any expression
# naming no parameter, and the right-hand side of a bound is a constant by
# definition. So `sum(shares) <= 1.0` was refused by the very check that would
# have guarded it, while the residual the solver builds -- `(lhs) - (rhs)` --
# parsed and evaluated correctly all along. `dsl.parse_side` is the door that
# closed the gap, and the vacuity guard moved to the combined arithmetic rather
# than being dropped.
#
# WHAT EACH ONE BUYS. Twelve nodes that no equation reached now carry a bound,
# which is the difference between "a knob with a declared range" and "a knob
# whose value is constrained by the rest of the system". Every operand is
# already declared, already carries unit `1`, and is `role: free` -- nothing
# here is determined by another equation, so each bound is a new claim rather
# than a second one about a value the graph already computes.
#
# WHY EVERY EQUATION CARRIES A `latex`. The DSL renders LaTeX on demand and
# folds constants while doing it. A bound's whole content is the ceiling, so a
# rendering that erased or moved it would be a rendering of a different claim.
# `alea.prg.service.check_latex` holds each declared rendering to the operand
# set of its arithmetic.
#
# WHY `leq` AND NOT `lt`. The relations are stated as ceilings, and a scenario
# that sits exactly on one is at the boundary rather than outside it. The
# residual comparison carries the equation's own tolerance, so equality passes.
```


## `param_batch2.yaml`

```yaml
# Generated from docs/param_batch2.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R7: battery_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: electrolyser_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: geothermal_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: phs_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: solar_pv_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: wind_offshore_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R7: wind_onshore_cost is claimed by ['param_batch2.md', 'param_batch7.md']; this entry kept
#   R8: coal_price_per_mwh -> fuel_cost_coal declared relationship='informational', which is a Strength value not a Relationship class; set to 'functional' (its strength is 'informational')
#   R8: gas_price_per_mwh -> fuel_cost_gas declared relationship='informational', which is a Strength value not a Relationship class; set to 'functional' (its strength is 'informational')
#   R9: dropped edge coal_price_per_mwh -> fuel_cost_coal -- 'coal_price_per_mwh_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge gas_price_per_mwh -> fuel_cost_gas -- 'gas_price_per_mwh_definition' does not hold both endpoints (gate 6)
#   R3: dropped rule 'capex_duplicates_disagree' -- its condition needs a function call, which the cross-validation grammar refuses: abs(capex_solar_pv - solar_pv_cost) > 1.0 or abs(capex_wind_onshore - wind_onshore_cost) > 1.0 or abs(capex_battery - battery_cost) > 1.0
#   R3: dropped rule 'hydrogen_price_far_from_lcoh' -- its condition needs a function call, which the cross-validation grammar refuses: abs(hydrogen_price - lcoe_hydrogen_usd_per_mwh) > 100
#   R3: dropped rule 'lcoe_solar_and_wind_disagree' -- its condition needs a function call, which the cross-validation grammar refuses: abs(lcoe_solar_usd_per_mwh - lcoe_wind_usd_per_mwh) > 200 and lcoe_solar_usd_per_mwh > 0 and lcoe_wind_usd_per_mwh > 0
#   R10: lcoe_solar_definition was cited at ['hard', 'soft']; every edge citing it set to strength='soft', because the strength is a property of the equation
#   R10: lcoe_wind_definition was cited at ['hard', 'soft']; every edge citing it set to strength='soft', because the strength is a property of the equation
#   R22: rule 'discount_rate_gearing_interaction' threshold corrected from
#        `gearing_ratio > 0.8` to `> 4.0`. The rule's own message reads "gearing
#        above 80%", which is the debt FRACTION, but `gearing_ratio` is a multiple
#        of equity (`debt_fraction / (1 - debt_fraction)`) and Batch 0 corrected
#        its range to the image [0, 19] (R21). Under the multiple reading a
#        threshold of 0.8 fires at a debt fraction of 0.444 -- a gearing of 44%,
#        not 80% -- so the rule would have warned on ordinary capital structures.
#        80% debt is a multiple of 4.0.
```


## `param_batch3.yaml`

```yaml
# Generated from docs/param_batch3.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R7: biogas_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: compressed_air_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: digital_divide_metrics is claimed by ['param_batch1.md', 'param_batch3.md']; this entry kept
#   R7: flywheel_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: fusion_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: gasification_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: hydrogen_fuel_cell_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: landfill_gas_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: pyrolysis_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: salinity_gradient_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: small_modular_reactor_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: tidal_range_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: waste_to_energy_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R7: wave_energy_converter_cost is claimed by ['param_batch3.md', 'param_batch7.md']; this entry kept
#   R3: dropped rule 'capex_duplicates_still_drift' -- its condition needs a function call, which the cross-validation grammar refuses: abs(capex_marine_wave - wave_energy_converter_cost) > 1.0 or abs(capex_smr - small_modular_reactor_cost) > 1.0 or abs(capex_fusion - fusion_cost) > 1.0 or abs(capex_caes - compressed_air_cost) > 1.0 or abs(capex_flywheel - flywheel_cost) > 1.0
```


## `param_batch4.yaml`

```yaml
# Generated from docs/param_batch4.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R16: dropped equation 'mtbf_from_failure_rate_definition' and its two edges,
#        and reverted 'mean_time_between_failures' to `free`. The equation made
#        the derived subgraph CYCLIC -- it computed MTBF from
#        `forced_outage_rate`, which 'availability_definition' computes from
#        MTBF -- so the ingested graph could not propagate at all: every
#        `check_scenario` raised `CycleError ... form a cycle and have no
#        evaluation order`. Its arithmetic was also dimensionally incoherent and
#        said so itself: the description gives the dimensional check "1/(1/hour)
#        is hour", but the divisor is `forced_outage_rate`, unit `1`, so the RHS
#        is dimensionless. The equation the description actually wants divides by
#        a *failure rate* in 1/hour, and the graph carries no such node (only
#        `failure_rate_curve`, a dimensionless shape selector). The tell is that
#        it shipped with `unit_check: false` -- the check was switched off on the
#        one equation that needed it. Dropping it keeps 'availability_definition',
#        whose two inputs (`mean_time_to_repair`, `mean_time_between_failures`)
#        are then both free, and restores the shipped default for MTBF.
#   R17: 'availability_definition' described its result as "the steady-state
#        availability: the fraction of time the asset is up". MTTR/(MTBF+MTTR) is
#        the DOWN fraction, and the node it assigns to is `forced_outage_rate`,
#        an outage rate. The arithmetic is right and the description was its
#        complement; corrected to say unavailability.
#   R15: 17 nodes re-typed float -> bool were given the `default` this batch
#        omitted. `docs/param_ingest.md:78` requires a default on a free node and
#        the loader does not enforce it, so the omission loaded -- and because the
#        shipped graph had declared each of these `float` with `default: 500000.0`
#        on the `(0, 1e6)` placeholder, re-typing them to `bool` *removed* the
#        only value they had. `check_scenario` over a defaults-built set then
#        raised `the parameter set is missing [...]` for all 26 such nodes across
#        batches 4 and 7. The values are the ones `docs/what-if.md` documents for
#        each parameter, so nothing here is invented.
#   R11: dropped equation 'mtbf_from_history_definition' -- its own description declares it a placeholder that cannot load
#   R11: dropped equation 'saifi_from_outage_frequency_definition' -- it determines 'system_saifi_events_per_year', which 'saifi_definition' already determines
#   R11: dropped equation 'saidi_from_reliability_definition' -- it determines 'system_saidi_hours_per_year', which 'saidi_definition' already determines
#   R13: forced_outage_rate is determined by 'availability_definition'; role set to 'derived' and its default removed
#   R13: mean_time_between_failures is determined by 'mtbf_from_failure_rate_definition'; role set to 'derived' and its default removed
#   R13: remaining_useful_life is determined by 'remaining_life_from_condition_definition'; role set to 'derived' and its default removed
#   R7: forced_outage_rate is claimed by ['param_batch0.md', 'param_batch4.md']; this entry kept
#   R7: unit_commitment is claimed by ['param_batch4.md', 'param_batch7.md']; this entry kept
#   R4: dropped edge outage_frequency -> system_saifi_events_per_year -- cites 'saifi_from_outage_frequency_definition', which no equation declares
#   R4: dropped edge outage_duration -> system_saidi_hours_per_year -- cites 'saidi_from_reliability_definition', which no equation declares
#   R4: dropped edge outage_frequency -> system_saidi_hours_per_year -- cites 'saidi_from_reliability_definition', which no equation declares
#   R4: dropped edge mean_time_to_repair -> mean_time_between_failures -- cites 'mtbf_from_history_definition', which no equation declares
#   R9: dropped edge crew_availability -> mean_time_to_repair -- 'availability_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge spare_parts_availability -> mean_time_to_repair -- 'availability_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge maintenance_frequency -> planned_outage_rate -- 'availability_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge regulatory_period_length -> regulatory_lag -- 'availability_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge ppa_duration -> ppa_availability -- 'ppa_price_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge regulatory_period_length -> revenue_cap -- 'tariff_cost_recovery' does not hold both endpoints (gate 6)
#   R9: dropped edge market_structure -> market_model -- 'tariff_cost_recovery' does not hold both endpoints (gate 6)
#   R3: dropped rule 'mtbf_mttr_inconsistent_with_availability' -- its condition needs a function call, which the cross-validation grammar refuses: abs(forced_outage_rate - mean_time_to_repair / (mean_time_between_failures + mean_time_to_repair)) > 0.05
```


## `param_batch5.yaml`

```yaml
# Generated from docs/param_batch5.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R6: vre_firm_capacity_mw was nested under `equations:` and is a parameter node
#   R6: lifeline_tariff_usd_per_mwh was nested under `equations:` and is a parameter node
#   R6: community_benefit_usd_per_year was nested under `equations:` and is a parameter node
#   R6: resettlement_costs_total_usd was nested under `equations:` and is a parameter node
#   R11: dropped equation 'learning_curve_wind_definition' -- it determines 'capex_learning_usd_per_kw', which 'learning_curve' already determines
#   R11: dropped equation 'capture_price_from_ppa_definition' -- it determines 'capture_price_usd_per_mwh', which 'capture_price_equation' already determines
#   R11: dropped equation 'energy_burden_with_lifeline_definition' -- it determines 'energy_burden', which 'energy_burden_definition' already determines
#   R12: dropped equation 'emissions_peak_constraint' -- as delivered it read
#        `emissions_mtco2_per_year <= emissions_mtco2_per_year`, a tautology. The
#        batch's own repair rule pruned `emissions_peak_year` from its
#        `parameters` on the grounds that "the arithmetic does not name them",
#        which removed the one operand that made the relation a relation and left
#        `x <= x`. That repair treated the symptom: the delivered arithmetic was
#        wrong, not the metadata. The intended claim (docs/param_eqn_formula1.md
#        :173) is `CO2(y_peak) >= CO2(y) for all y` -- a property of a trajectory
#        indexed by year, i.e. a curve, and this graph carries a single annual
#        scalar `emissions_mtco2_per_year`. So the claim has no encoding here and
#        the equation is removed rather than re-pointed: writing
#        `emissions_mtco2_per_year <= emissions_peak_year` would compare
#        MtCO2/year against years under the equation's own `unit_check: true`.
#        This leaves `emissions_peak_year` uncoupled, which is the honest state
#        -- it was already uncoupled, because R12 had pruned it from the only
#        equation that named it. The spec's relation column
#        (docs/param_eqn.md:361-362) states `emissions_peak_year <->
#        net_zero_year`, and its formula for `net_zero_year` is a trajectory
#        claim too (`CO2(y) = 0`), so a future batch that gives the graph a
#        year-indexed trajectory would land both together.
#   R7: combined_ratio is claimed by ['param_batch0.md', 'param_batch5.md']; this entry kept
#   R7: customs_duty is claimed by ['param_batch5.md', 'param_batch7.md']; this entry kept
#   R7: loss_ratio is claimed by ['param_batch0.md', 'param_batch5.md']; this entry kept
#   R4: dropped edge capex_wind_onshore -> capex_learning_usd_per_kw -- cites 'learning_curve_wind_definition', which no equation declares
#   R4: dropped edge cumulative_capacity_mw -> capex_learning_usd_per_kw -- cites 'learning_curve_wind_definition', which no equation declares
#   R4: dropped edge learning_rate -> capex_learning_usd_per_kw -- cites 'learning_curve_wind_definition', which no equation declares
#   R4: dropped edge ppa_price_usd_per_mwh -> capture_price_usd_per_mwh -- cites 'capture_price_from_ppa_definition', which no equation declares
#   R4: dropped edge offtake_risk_premium -> capture_price_usd_per_mwh -- cites 'capture_price_from_ppa_definition', which no equation declares
#   R4: dropped edge lifeline_tariff -> energy_burden -- cites 'energy_burden_with_lifeline_definition', which no equation declares
#   R4: dropped edge household_consumption_mwh_per_year -> energy_burden -- cites 'energy_burden_with_lifeline_definition', which no equation declares
#   R4: dropped edge regulated_tariff_usd_per_mwh -> energy_burden -- cites 'energy_burden_with_lifeline_definition', which no equation declares
#   R4: dropped edge lifeline_threshold -> energy_burden -- cites 'energy_burden_with_lifeline_definition', which no equation declares
#   R4: dropped edge household_income_usd_per_year -> energy_burden -- cites 'energy_burden_with_lifeline_definition', which no equation declares
#   R4: dropped edge fpic_compliance_score -> land_use_conflict_index -- cites 'land_availability_fraction', which no equation declares
#   R4: dropped edge habitat_loss_hectares -> biodiversity_intactness_before -- cites 'land_availability_fraction', which no equation declares
#   R4: dropped edge grievance_redress_effectiveness -> fpic_compliance_score -- cites 'land_availability_fraction', which no equation declares
#   R9: dropped edge emissions_mtco2_per_year -> emissions_peak_year -- 'emissions_peak_constraint' does not hold both endpoints (gate 6)
#   R9: dropped edge corporate_income_tax_rate -> discount_rate -- 'wacc_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge investment_allowance_rate -> annualised_capex_usd_per_kw -- 'annualised_capex' does not hold both endpoints (gate 6)
#   R9: dropped edge accelerated_depreciation_factor -> discount_rate -- 'wacc_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge thin_capitalisation_limit -> debt_equity_ratio -- 'wacc_definition' does not hold both endpoints (gate 6)
#   R9: dropped edge premium_share_of_asset -> total_capacity_mw -- 'annualised_capex' does not hold both endpoints (gate 6)
#   R9: dropped edge insurance_loss_share_of_cost -> annualised_capex_usd_per_kw -- 'annualised_capex' does not hold both endpoints (gate 6)
#   R9: dropped edge land_acquisition_cost_per_hectare -> annualised_capex_usd_per_kw -- 'annualised_capex' does not hold both endpoints (gate 6)
#   R3: dropped rule 'retention_plus_deductible_above_unity' -- its condition needs arithmetic, which the cross-validation grammar refuses: retention_share + deductible_share > 1.0
#   R3: dropped rule 'local_employment_exceeds_total' -- its condition needs arithmetic, which the cross-validation grammar refuses: local_employment_share + women_employment_share + youth_employment_share > 2.0
#   R10: dropped equation 'loss_ratio_from_claims_definition' and its two edges -- it stated
#        `combined_ratio - loss_ratio == premium_share_of_asset`, which is not the accounting
#        identity. An expense ratio is expenses over premiums; premium-per-asset is premiums over
#        assets. The equation asserted a false relation between three real parameters, and a false
#        equation is worse than a missing one because `cross_validate` reports it satisfied or
#        violated at every scenario. It is replaced by `insurance_combined_ratio_definition`, which
#        states the identity over an expense ratio, and by the `insurance_combined_below_loss` rule
#        that already bounds the pair.
```


## `param_batch6.yaml`

```yaml
# Generated from docs/param_batch6.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R3: dropped rule 'ppa_indexed_price_doubles' -- its condition needs arithmetic, which the cross-validation grammar refuses: ppa_indexed_price_usd_per_mwh > 3 * ppa_price_usd_per_mwh
#   R19: 'lolp_definition' recalibrated. It read `exp(-10 * m)`, and at the default
#        `reserve_margin_min = 0.15` that returns lolp = 0.2231 -- a loss-of-load of
#        one hour in 4.5 -- which puts LOLE at 1954.6 h/yr, 81x the 24 h/yr ceiling
#        this same batch's `lole_exceeds_days` rule enforces and outside the node's
#        own declared range [0, 500]. The batch's prose claimed the decay constant
#        was "set so a margin equal to the required minimum gives a LOLP near the
#        regulatory ceiling of 1 in 100 hours"; 10 does not do that, and nothing
#        compared the claim to the curve it describes. Recalibrated to the graph's
#        own reliability rule instead: `(24 / 8760) ** (m / 0.15)` is pinned to
#        lolp = 24/8760 at m = 0.15, so LOLE = 24 h/yr exactly at the required
#        minimum margin. A base in [0, 1] to a non-negative power is in [0, 1], so
#        the node's range is now a property of the form for every value set.
#   R20: 'fuel_diversity_definition' denominator corrected from `total_capacity_mw`
#        to the sum of the seven fuels it indexes. An HHI divides by the total of
#        the shares it is taken over, and the two are different parameters free to
#        disagree: at the shipped defaults the seven sum to 63000 MW while
#        `total_capacity_mw` is 10000 MW, so the index returned 1 - 8.39 = -7.39
#        against a declared range of [0, 1]. With the seven's own total the shares
#        sum to 1 by construction and Cauchy-Schwarz bounds the index in [0, 1] for
#        every value set. The `total_capacity_mw -> fuel_diversity_index` edge was
#        dropped with it: the equation no longer holds that endpoint (gate 6).
```


## `param_batch7.yaml`

```yaml
# Generated from docs/param_batch7.md by the parameter-equation ingestion.
# Merged onto config/prg.yaml by alea.prg.graph.load_ingested().
#
# Repairs applied to the batch as delivered:
#   R15: 6 nodes re-typed float -> bool were given the `default` this batch
#        omitted -- the same defect as batch 4's 17, and the same repair. See
#        param_batch4.yaml's R15 for the full account. `smart_metering_rollout`
#        is the one bool left without a default, and deliberately: batch 1 types
#        it a share (`default: 0.3`), this batch a bool, and
#        `docs/param_eqn_formula1.md` a year-indexed count, so the documents
#        disagree about what the node is and a default would pick a side.
#   retired edge solar_pv_cost -> capex_solar_pv (Self-loop after alias resolution. Removed.)
#   retired edge wind_onshore_cost -> capex_wind_onshore (Self-loop after alias resolution. Removed.)
#   R7: battery_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: biogas_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: compressed_air_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: customs_duty also appears in param_batch5.md; that entry is kept and this one dropped
#   R7: electrolyser_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: flywheel_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: fusion_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: gasification_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: geothermal_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: hydrogen_fuel_cell_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: landfill_gas_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: phs_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: pyrolysis_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: salinity_gradient_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: small_modular_reactor_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: smart_metering_rollout is claimed by ['param_batch1.md', 'param_batch7.md']; this entry kept
#   R7: solar_pv_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: tidal_range_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: unit_commitment also appears in param_batch4.md; that entry is kept and this one dropped
#   R7: waste_to_energy_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: wave_energy_converter_cost also appears in param_batch3.md; that entry is kept and this one dropped
#   R7: wind_offshore_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R7: wind_onshore_cost also appears in param_batch2.md; that entry is kept and this one dropped
#   R3: dropped rule 'alias_target_exists' -- its condition needs a function call, which the cross-validation grammar refuses: not (is_declared(capex_solar_pv) and is_declared(capex_wind_onshore) and is_declared(capex_battery) and is_declared(capex_phs) and is_declared(capex_geothermal) and is_declared(capex_hydrogen_electrolyser) and is_declared(capex_marine_wave) and is_declared(capex_smr) and is_declared(capex_fusion) and is_declared(capex_caes) and is_declared(capex_flywheel) and is_declared(capex_hydrogen_fuel_cell) and is_declared(capex_tidal_range) and is_declared(capex_salinity_gradient) and is_declared(capex_biogas) and is_declared(capex_landfill_gas) and is_declared(capex_waste_to_energy) and is_declared(capex_pyrolysis) and is_declared(capex_gasification) and is_declared(demand_growth) and is_declared(cross_border_trade_allowed) and is_declared(import_duty_equipment))
#   R3: dropped rule 'alias_value_drift' -- its condition needs a function call, which the cross-validation grammar refuses: abs(solar_pv_cost - capex_solar_pv) > 0.01 or abs(wind_onshore_cost - capex_wind_onshore) > 0.01 or abs(battery_cost - capex_battery) > 0.01
#   R3: dropped rule 'deprecated_node_referenced' -- its condition needs a function call, which the cross-validation grammar refuses: is_referenced(solar_pv_cost) or is_referenced(wind_onshore_cost) or is_referenced(battery_cost) or is_referenced(demand_growth_rate) or is_referenced(cross_border_trading)
#   R3: dropped rule 'alias_cycle' -- its condition needs a function call, which the cross-validation grammar refuses: alias_of(solar_pv_cost) == capex_solar_pv and alias_of(capex_solar_pv) == solar_pv_cost
#   R3: dropped rule 'endogenous_component_free_total' -- its condition needs a function call, which the cross-validation grammar refuses: is_free(coal_capacity) and is_endogenous(firm_capacity_mw)
#   R3: dropped rule 'endogenous_without_range_or_default' -- its condition needs a function call, which the cross-validation grammar refuses: is_endogenous(coal_capacity) and (not has_range(coal_capacity) or not has_default(coal_capacity))
```


---

## Corrections applied after the bake (same day, 2026-10-17)

Four classes of defect surfaced once the baked graph ran the full suite.
These are recorded here rather than left as a diff, because the fragments are
gone and the yaml carries no comments.

**Eight status bumps were reverted, `existing` → `to_build`.** The fragments
bumped the implementation status of `gdp_growth_rate`, `geothermal_cost`,
`industrialisation_rate`, `inflation_rate`, `interest_rate`,
`nuclear_capacity`, `population_growth_rate` and `urbanisation_rate` to
`existing` alongside the range/default/unit corrections they made. The
node's `status` is *where the parameter stands in the build* (its own
docstring at `views.py` says so), and a tightened range is a data
declaration, not an implementation. Nothing reads these nodes in model code;
they are still things to build. The data corrections themselves stand.

**Two nodes carry the unit their equation reads them in.** `outage_duration`
was declared bare `hours` while `saidi_definition` multiplies it by
`outage_frequency` in `events/year` — the arithmetic is hours/year, and the
bare declaration made exactly that equation read as a dimensional mismatch.
Declared now as `hours/event`. `healthcare_cost_per_case` carried no unit
while `health_cost_definition` prices `dalys_per_year` — declared now as
`USD/DALY`, the only unit under which that identity is decidable. The node
is catalog-sourced, so both corrections live at their sources of truth: the
catalog row 18.12 in `docs/params.md` and the generator's unit table
(`scripts/build/prg_from_catalog.py`), with `config/prg.yaml` regenerated
from them.

**Four uncoupled `free` roles became `exogenous` under the generator.**
`coal_ccs_adoption`, `debt_tenor`, `gas_ccs_adoption` and
`solar_pv_capacity_factor` were uncoupled before the bake, so the generator's
own register set them `free`; the batches' equations now name them, and a
node a shipped equation reads but does not determine is `exogenous` — the
convention `carbon_price_usd_per_tco2` and `asset_life` already carry. The
regeneration applied it.

**Nine rule thresholds were moved inside their parameter's declared range.**
The fragments tightened ranges from the shipped `(0, 1e6)` placeholder while
the rules kept thresholds from the old range, and `check_scenario` range-gates
at the door, so the rules could never fire. `carbon_tax_rate_units` was also
self-contradictory — `> 5 and < 0.5`, with a message stating "between 0.5 and 5".

| rule | condition before | condition after |
|---|---|---|
| `learning_rates_out_of_range` | `> 0.40` | `> 0.35` |
| `capex_battery_units_consistent` | `> 5000` | `> 700` |
| `capex_transmission_out_of_band` | `< 20 or > 8000` | `< 100 or > 2000` |
| `carbon_tax_rate_units` | `> 5 and < 0.5` | `> 0 and < 0.5` |
| `index_above_unity` | `> 1.0` | `> 0.99` |
| `concentration_above_hhi_max` | `> 10000` | `> 9000` |
| `geothermal_cost_below_drilling` | `< 1500` | `< 3000` |
| `revenue_cap_below_cost` | `< 0.5` | `< 0.8` |
| `resettlement_population_exceeds_exposed` | `> 1.0` | `> 0.4` |

Two alias corrections were also applied before the bake. The alias register
the fragments ship is validated but not applied — nothing rewrites citations
under it — so the two corrections were made directly.

**Known open findings, not corrected:**

* `lcoe_solar_definition` and `lcoe_wind_definition` both add
  `opex_variable_battery` to their LCOE numerators — a battery cost inside a
  solar or wind LCOE. Both are `soft` equations; the arithmetic is wrong and
  the fix needs the battery's share of the hybrid plant's own energy, which
  the graph does not declare yet.
* Twenty equations read `inconsistent` under the dimensional walker, all in
  two declared classes (the `(1 + rate)` convention and annual quantities
  declared without a per-year divisor). Pinning them is
  `test_the_flagged_equations_are_a_known_set`; repairing them is one
  vocabulary decision over the annual-quantity family, measured in the pin.
* `debt_tenor`'s default is 500000.0 — the catalog placeholder midpoint,
  effectively a perpetuity in `llcr_definition`. A tenor should be 1–30
  years; the fix moves `llcr_estimate` and `dscr_requirement`'s behaviour,
  which is scoped work, not a data edit.
