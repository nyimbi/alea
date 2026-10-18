# SLICE carbon-market

```text
SLICE = 72 uncoupled nodes. 61 carry unit=None; 59 carry the 500000.0 placeholder.
`capacity_price` and `cbam_price` match the pattern but are already coupled (free variable of
capacity_revenue_usd_per_year_definition; read by cbam_price_applied_definition) — 0 lines.
Node is frozen, so every retype below is authored in config/prg.yaml, never at runtime.
Dimensional caveat: `unit_of` does not reduce TWh↔MWh or MtCO2↔tonne, so every volume×price rhs
reads `USD * terawatt_hour / megawatt_hour` rather than USD. Pint confirms 1 TWh = 1e6 MWh and
1 MtCO2 = 1e6 tonne, so those readings are the walker's defect, not the equation's.
```

```
article_6_2_parameters | QUALITATIVE | -- | 1 | [0,1] | unknown | null | The bilateral cooperative-approach rulebook; its admissible set is a treaty choice, not a quantity any shipped node measures.
article_6_4_parameters | QUALITATIVE | -- | 1 | [0,1] | unknown | null | The centralised-mechanism rulebook; same reason, and the graph carries no project registry it could read.
article_6_credits | PRODUCT | article_6_credits = corresponding_adjustment * carbon_credit_volumes | MtCO2/year | [0,1000] | derived | null | Article 6 volume is the CA-cleared share of the credit book; dimension MtCO2/year verified after retype.
auction_frequency | QUALITATIVE | -- | 1/year | [0,365] | unknown | null | The auction calendar is a schedule choice (annual, quarterly, monthly); no graph quantity determines it.
auction_mechanism | QUALITATIVE | -- | 1 | -- | unknown | stoft_2002 | Uniform-price, pay-as-bid or clock: Stoft ch.5 treats these as alternative designs, not one functional.
auction_price_cap | THRESHOLD | carbon_price_escalated_usd_per_tco2 = auction_price_cap | USD/tonne | [0,500] | unknown | cbam_regulation | The ceiling the allowance price sits under; 81.44 <= 500000 holds at defaults only because the default is the placeholder, so the retype is part of the bound.
auction_volume | PRODUCT | auction_volume = ets_cap | MtCO2/year | [0,10000] | derived | cbam_regulation | All allowances auctioned because the graph carries no free-allocation share; 25.0 MtCO2/yr at defaults.
bid_ask_spread | PRODUCT | bid_ask_spread * demand_twh * 1000000 | USD/year | [0,100] | unknown | null | Spread cost over the shipped traded volume, demand 46.54 TWh; walker reads USD*TWh/MWh.
carbon_budget | PRODUCT | carbon_budget = carbon_budget_mtco2 | MtCO2 | [0,100000] | 500.0 | catalog_duplicate_resolutions | Two ids for the remaining budget, resolved by equality; 500.0 = 500.0.
carbon_credit_insurance | PRODUCT | carbon_credit_insurance * carbon_credit_prices * carbon_credit_volumes * 1000000 | USD/year | [0,1] | unknown | null | Premium as a share of the credit book's value; dimension verified.
carbon_credit_prices | PRODUCT | carbon_credit_prices * carbon_credit_volumes * 1000000 | USD/year | [0,500] | unknown | null | A price with no derivation of its own; it couples as the value of the book, volume 45.0 MtCO2/yr.
carbon_credit_rating | QUALITATIVE | -- | 1 | [0,5] | unknown | null | A rating class (AAA-B), an ordered label whose admissible set is the rater's scale.
carbon_credit_retirement | PRODUCT | carbon_credit_retirement * carbon_credit_volumes | MtCO2/year | [0,1] | unknown | null | Share of issued volume retired; dimension MtCO2/year verified.
carbon_credit_vintage | QUALITATIVE | -- | years | [0,100] | unknown | null | An issuance year attached to the credit, not a quantity the model computes.
carbon_credit_volumes | PRODUCT | carbon_credit_volumes = additional_abatement_mtco2 | MtCO2/year | [0,1000] | derived | null | Credit volume is the abatement that clears additionality, which the shipped additional_abatement_definition already computes: 45.0 MtCO2/yr at defaults.
carbon_price_risk | PRODUCT | (1 + carbon_price_risk) * carbon_price_escalated_usd_per_tco2 | USD/tonne | [0,1] | unknown | null | Risk premium on the escalated price; 81.44 USD/tonne at r = 0.
carbon_tax_coverage | PRODUCT | carbon_tax_coverage = carbon_price_coverage | 1 | [0,1] | 0.5 | catalog_duplicate_resolutions | The covered share under two names; 0.5 = 0.5, and the shipped carbon_revenue_definition reads carbon_price_coverage.
carbon_tax_interaction | PRODUCT | carbon_tax_interaction * carbon_revenue_usd_per_year | USD/year | [0,1] | unknown | standard_fiscal | Share of carbon revenue offset by lower other taxes; 650,578,257.11 USD/yr at defaults.
cdm_methodologies | QUALITATIVE | -- | 1 | -- | unknown | null | A methodology name from the CDM register; a choice among documents, not a measurement.
collusion | QUALITATIVE | -- | 1 | -- | unknown | null | A detection capability flag; no revenue or volume base exists for it to multiply.
corresponding_adjustment | PRODUCT | corresponding_adjustment * article_6_credits | MtCO2/year | [0,1] | unknown | null | Share of transferred volume carrying a corresponding adjustment; dimension verified.
cross_subsidy_level | PRODUCT | cross_subsidy_level * total_revenue_usd_per_year | USD/year | [0,1] | 0.1 | benefit_sharing_shares | Revenue moved between tariff classes; 0.1 * 6,301,608,073.79 = 630,160,807.38 USD/yr.
cross_subsidy_transparency | QUALITATIVE | -- | 1 | -- | unknown | null | A disclosure index; its admissible set is a governance choice.
direct_agreement | QUALITATIVE | -- | 1 | -- | unknown | null | A contractual form (whether a bilateral agreement exists), not a quantity.
distribution_wheeling_charges | PRODUCT | distribution_wheeling_charges * demand_twh * 1000000 | USD/year | [0,100] | unknown | pass_through_pricing | Distribution wheeling over demand, 46.54 TWh; walker reads USD*TWh/MWh.
electricity_subsidies | PRODUCT | electricity_subsidies * demand_twh * 1000000 | USD/year | [0,500] | unknown | null | Consumer subsidy over demand, 46.54 TWh; walker reads USD*TWh/MWh.
ets_cap | PRODUCT | ets_cap = carbon_price_coverage * carbon_budget_mtco2 / horizon_years | MtCO2/year | [0,10000] | derived | cbam_regulation | The covered share of the budget annualised: 0.5*500/10 = 25.0 MtCO2/yr, below emissions 26.02, so the cap binds while the budget (260.23 against 500) does not.
ets_enabled | GATE-PRODUCT | ets_enabled * ets_cap | MtCO2/year | [0,1] | 0.0 | cbam_regulation | Multiplies the capped volume; at defaults 0.0 MtCO2/yr, and the shipped carbon_revenue_definition reads no gate, so 650,578,257.11 USD/yr of carbon revenue accrues with the ETS switched off.
feed_in_tariff | PRODUCT | feed_in_tariff * renewable_generation_twh * 1000000 | USD/year | [0,500] | unknown | pass_through_pricing | Purchase obligation over the shipped VRE volume, 31.23 TWh; walker reads USD*TWh/MWh.
fossil_fuel_subsidies | PRODUCT | fossil_fuel_subsidies * (generation_twh - renewable_generation_twh) * 1000000 | USD/year | [0,500] | unknown | null | Subsidy over the non-renewable volume, 52.05 - 31.23 = 20.82 TWh; walker reads USD*TWh/MWh.
gate_closure | QUALITATIVE | -- | hours | [0,168] | unknown | null | A market rule setting when bids freeze; it selects a timeline, not a quantity.
gold_standard_methodologies | QUALITATIVE | -- | 1 | -- | unknown | null | A certification standard's methodology set; a choice among documents.
hybrid_revenue_price_cap | PRODUCT | hybrid_revenue_price_cap * price_cap * regulated_tariff_usd_per_mwh + (1 - hybrid_revenue_price_cap) * applied_tariff_usd_per_mwh | USD/MWh | [0,1] | 0.5 | world_bank_regulation | Weight on the price cap in the hybrid; 90.95 USD/MWh at defaults, equal to the applied tariff because both caps are 1.0.
insider_trading_rules | QUALITATIVE | -- | 1 | -- | unknown | null | A rule-set capability; no base exists for it to multiply.
leakage_parameters | PRODUCT | leakage_parameters * emissions_mtco2_per_year | MtCO2/year | [0,1] | unknown | null | Leaked share of covered emissions, 26.02 MtCO2/yr at defaults.
local_employment_targets | PRODUCT | local_employment_share / local_employment_targets | 1 | [0,1] | unknown | null | Substring artifact of 'ets' inside 'targets'; a geq bound fails at defaults (0.3 >= 500000 is false), so the honest form is the attainment ratio, 0.3/target.
lpg_subsidies | BASE-NEEDED | -- | USD/kg | [0,5] | unknown | null | Needs LPG consumption in kg/yr; population_total/5 = 9,000,000 households and cooking_lpg_penetration 0.2 exist, the kg base does not.
market_abuse_prevention | QUALITATIVE | -- | 1 | -- | unknown | null | A surveillance capability; a choice among regimes.
market_concentration | PRODUCT | market_concentration = 10000 * (1 - fuel_diversity_index) | 1 | [0,10000] | derived | null | HHI from the fleet's own fuel shares: 3511.30 at defaults against the declared 2500.0, so the default is not the fleet the graph ships.
market_coupling | SCENE-SWITCH | -- | 1 | [0,1] | unknown | null | Selects whether the zone clears against neighbours; the graph has one zone and one price, so no equation should carry it.
market_liquidity | PRODUCT | market_liquidity * demand_twh | TWh | [0,100] | unknown | null | Churn: traded volume as a multiple of demand, 46.54 TWh at a multiple of 1.
market_model | SCENE-SWITCH | -- | categorical | -- | regulated | null | Selects regulated / liberalised / single-buyer simulation; the engine reads it and no equation should.
market_structure | SCENE-SWITCH | -- | categorical | -- | single_buyer | null | Selects the market architecture (single buyer, wholesale, bilateral); same reason.
mini_grid_subsidies | PRODUCT | mini_grid_subsidies * mini_grid_programme_spend_usd_per_year | USD/year | [0,1] | unknown | null | Share of the shipped programme spend covered by subsidy; dimension USD/year verified.
mrv_parameters | QUALITATIVE | -- | 1 | [0,1] | unknown | null | An MRV protocol and its tiers; a choice among documents.
netting_agreements | PRODUCT | (1 - netting_agreements) * collateral_posted_usd_per_year | USD million/year | [0,1] | unknown | null | Collateral left un-netted; the shipped netting_agreements is unit=None, the retype to a share makes the product decidable.
novation_terms | QUALITATIVE | -- | 1 | -- | unknown | null | A clearing-house legal term; a choice, not a measurement.
permanence_parameters | PRODUCT | (1 - permanence_parameters) * carbon_credit_volumes | MtCO2/year | [0,1] | unknown | null | Reversal allowance on the credit book, 45.0 MtCO2/yr at defaults.
position_limits | PRODUCT | position_limits * ets_cap | MtCO2/year | [0,1] | unknown | null | Share of the cap one participant may hold; 25.0 MtCO2/yr at defaults.
price_cap | PRODUCT | price_cap = revenue_cap | 1 | [0.5,2] | 1.0 | catalog_duplicate_resolutions | The cap on average tariff is the cap on revenue in a single-part tariff; 1.0 = 1.0, and applied_tariff_definition already reads revenue_cap.
price_limits | PRODUCT | (1 + price_limits) * marginal_cost_usd_per_mwh | USD/MWh | [0,5] | unknown | stoft_2002 | Band around the marginal cost, 65.00 USD/MWh at the default price; the lower arm is (1 - price_limits) * the same.
pricing_mechanism | SCENE-SWITCH | -- | 1 | -- | unknown | stoft_2002 | Uniform versus pay-as-bid clearing; the graph carries one marginal cost and no bid stack, so the choice cannot be carried by an equation.
renewable_subsidies | PRODUCT | renewable_subsidies * renewable_generation_twh * 1000000 | USD/year | [0,500] | unknown | null | Same base as the FIT (31.23 TWh), a subsidy rather than a purchase obligation.
service_quality_reward | PRODUCT | service_quality_reward * allowed_revenue_requirement | USD million/year | [0,0.1] | 0.01 | world_bank_regulation | Reward for beating the quality target; 0.01 * 634.08 = 6.34 USD m/yr.
settlement_risk | PRODUCT | settlement_risk * carbon_credit_prices * carbon_credit_volumes * 1000000 | USD/year | [0,1] | unknown | null | Exposure as a share of the credit book's value; dimension verified.
shs_subsidies | PRODUCT | shs_subsidies * shs_programme_spend_usd_per_year | USD/year | [0,1] | unknown | null | Share of the SHS programme spend covered; dimension USD/year verified.
social_tariff | PRODUCT | social_tariff = lifeline_tariff_usd_per_mwh | USD/MWh | [0,500] | 30.0 | catalog_duplicate_resolutions | Two ids for the below-threshold tariff; 30.0 = 30.0, matching the shipped lifeline_tariff_alias.
strategic_bidding | SCENE-SWITCH | -- | 1 | -- | unknown | stoft_2002 | A behaviour mode the dispatch assumes; the graph's marginal cost is one number, not a bid function.
tariff_rebalancing | PRODUCT | tariff_rebalancing * total_revenue_usd_per_year | USD/year | [0,1] | 0.2 | world_bank_regulation | Revenue moved between classes in the first year: 0.2 * 6,301,608,073.79 = 1,260,321,614.76 USD/yr; the closed-form over ten years is 0.8926 of the base.
tariff_structure | QUALITATIVE | -- | 1 | -- | unknown | null | The tariff design (flat, block, two-part); a design choice among admissible structures.
tariff_transparency | QUALITATIVE | -- | 1 | -- | unknown | null | A disclosure index; a governance choice.
time_of_use_tariff_adoption | PRODUCT | time_of_use_tariff_adoption * demand_twh | TWh | [0,1] | 0.1 | null | Demand on a time-of-use tariff: 0.1 * 46.54 = 4.65 TWh.
trade_repository | QUALITATIVE | -- | 1 | -- | unknown | null | Whether a repository exists; an institutional fact, not a quantity.
vcs_methodologies | QUALITATIVE | -- | 1 | -- | unknown | null | A certification standard's methodology set; a choice among documents.
virtual_bidding | SCENE-SWITCH | -- | 1 | -- | unknown | null | A market rule permitting financial participation; the graph has no financial layer to price it in.
voluntary_carbon_market | GATE-PRODUCT | voluntary_carbon_market * carbon_credit_volumes | MtCO2/year | [0,1] | 0.0 | null | Participation share multiplying the credit volume, 45.0 MtCO2/yr at defaults.
wheeling_charge_cross_border | PRODUCT | wheeling_charge_cross_border * abs(net_imports_twh) * 1000000 | USD/year | [0,100] | unknown | pass_through_pricing | Charge on net imports; 0.0 USD/yr at the shipped net_imports_twh = 0.0.
wheeling_charges | PRODUCT | wheeling_charges * demand_twh * 1000000 | USD/year | [0,100] | unknown | pass_through_pricing | Transmission wheeling over demand, 46.54 TWh; walker reads USD*TWh/MWh.
women_employment_targets | PRODUCT | women_employment_share / women_employment_targets | 1 | [0,1] | unknown | null | Substring artifact of 'ets' inside 'targets'; a bound fails at defaults (0.2 >= 500000 is false), so the attainment ratio is the honest form.
working_capital_allowance | PRODUCT | working_capital_allowance * allowed_revenue_requirement | USD million/year | [0,0.25] | 0.05 | world_bank_regulation | Working capital inside allowed revenue: 0.05 * 634.08 = 31.70 USD m/yr.
x_factor | PRODUCT | (1 - x_factor) * allowed_revenue_requirement | USD million/year | [0,0.1] | 0.02 | world_bank_regulation | The RPI-X cut: 0.98 * 634.08 = 621.40 USD m/yr; subtracting x_factor from inflation_rate directly raises DimensionalMismatch (1/year vs 1).
youth_employment_targets | PRODUCT | youth_employment_share / youth_employment_targets | 1 | [0,1] | unknown | null | Substring artifact of 'ets' inside 'targets'; a bound fails at defaults (0.3 >= 500000 is false), so the attainment ratio is the honest form.
```

```text
NEW BASES NEEDED

1. lpg_consumption_kg_per_year — kg/year, range [0, 5e8], default unknown.
   Derivation available in the graph: population_total / 5 = 9,000,000 households (batch 22's own
   five-persons-per-household derivation), times cooking_lpg_penetration 0.2 = 1,800,000 LPG
   households. The one non-graph input is kg per household per year; a 12.5 kg cylinder per
   quarter gives 50, which is a physical assumption and not a graph quantity, so the default stays
   unknown until a fuel-table row supplies it. Product then formed:
   lpg_subsidy_spend_usd_per_year = lpg_subsidies * lpg_consumption_kg_per_year  [USD/year].

2. clearing_price_usd_per_tonne — USD/tonne, range [0, 500], default unknown.
   The ETS has a cap (ets_cap, 25.0 MtCO2/yr) and an auction (auction_volume) but no price at
   which the cap clears; carbon_price_usd_per_tco2 is the exogenous tax rate, not the market
   clearing price. Without it auction_price_cap and price_limits are ceilings over nothing, and
   auction revenue cannot be computed. It would come from the market-clearing solve, so it is an
   endogenous output of the ETS layer, not a settable parameter.

3. free_allocation_share — 1, range [0, 1], default unknown.
   The share of ets_cap given free rather than auctioned. At 0 the auction volume equals the cap
   (the proposed alias), which is the correct special case but not the general one. Source: the
   ETS directive's free-allocation schedule; no graph quantity implies it.
```

```text
PROPOSED BATCHES

Batch 23 — carbon market arithmetic (17 nodes). Method: alias / share x base / rate x volume, all
  on carbon quantities the graph already carries.
  carbon_budget, carbon_tax_coverage, ets_cap, auction_volume, auction_price_cap, ets_enabled,
  carbon_credit_volumes, carbon_credit_prices, carbon_credit_retirement, carbon_credit_insurance,
  carbon_price_risk, carbon_tax_interaction, leakage_parameters, permanence_parameters,
  corresponding_adjustment, article_6_credits, voluntary_carbon_market.
  The batch's live defect to fix while there: carbon_revenue_definition reads no ets_enabled, so
  650,578,257.11 USD/yr accrues with the ETS off.

Batch 24 — regulatory finance and tariff shares (10 nodes). Method: share x allowed revenue or
  share x total revenue, plus the two cap aliases.
  price_cap, hybrid_revenue_price_cap, x_factor, working_capital_allowance,
  service_quality_reward, tariff_rebalancing, cross_subsidy_level, social_tariff,
  time_of_use_tariff_adoption, market_concentration.
  market_concentration carries a finding: the declared 2500.0 disagrees with the fleet's own
  3511.30, so the default must move or the fleet does.

Batch 25 — subsidy and charge rates (10 nodes). Method: USD/MWh rate x TWh base x 1e6, the same
  shape batch 21 used for mini_grid_programme_spend.
  feed_in_tariff, renewable_subsidies, fossil_fuel_subsidies, electricity_subsidies,
  mini_grid_subsidies, shs_subsidies, lpg_subsidies, wheeling_charges,
  distribution_wheeling_charges, wheeling_charge_cross_border.
  These are the lines the TWh/MWh non-reduction will flag as inconsistent; either the registry
  gains the equivalence or the batch exempts them with the reason recorded.

Batch 26 — market-operations rates (6 nodes). Method: rate or share x an existing base, with the
  clearing-house family the shipped collateral equations already use.
  bid_ask_spread, price_limits, position_limits, settlement_risk, market_liquidity,
  netting_agreements.

Batch 27 — employment-target artifacts (3 nodes). Method: attainment ratio, because a bound fails
  at defaults.
  local_employment_targets, women_employment_targets, youth_employment_targets.

Batch 28 — qualitative and scene register (26 nodes). Method: retype only, no equations; each row
  is a categorical, a boolean or a unit-bearing label, and the batch records why no equation may
  read it.
  article_6_2_parameters, article_6_4_parameters, auction_frequency, auction_mechanism,
  carbon_credit_rating, carbon_credit_vintage, cdm_methodologies, collusion,
  cross_subsidy_transparency, direct_agreement, gate_closure, gold_standard_methodologies,
  insider_trading_rules, market_abuse_prevention, market_coupling, market_model,
  market_structure, mrv_parameters, novation_terms, pricing_mechanism, strategic_bidding,
  tariff_structure, tariff_transparency, trade_repository, vcs_methodologies, virtual_bidding.

72 nodes, 28 of them deriving a value from the graph. Batch 23 is the one to author first: it
closes the ETS chain end to end and exposes the ets_enabled gate the carbon revenue path bypasses.
```

# SLICE risk-insurance

Verification basis: every `rhs` below was passed through `unit_of(parse_side(rhs), g)`. `USD·MW/kW` is dimensionally `USD` (MW/kW = 1000, and the `* 1000` makes it exact). `~` means `unit_of` returned **None** — undecidable, not a pass, because an operand is declared `unit: None`. No proposed rhs reads an ENDOGENOUS node (checked against `g.nodes[n].role`). Values are `propagate()` at document defaults.

```
NODE | CLASS | lhs = rhs | unit | range | default | reference | reason
accumulation_risk | QUALITATIVE | -- | USD | (0, 5e10) | unknown | null | The value is the insurer's own single-event book; no share of it exists in the graph, so the admissible set is the firm's balance sheet, not a measurement.
balance_of_payments | BASE-NEEDED | balance_of_payments = current_account_share_of_gdp * gdp_usd_per_year | USD/year | (-1e12, 1e12) | unknown | null | Needs gdp_usd_per_year; the graph carries gdp_growth_rate but no level.
business_interruption_insurance | GATE-PRODUCT | business_interruption_insurance = business_interruption_insurance * total_revenue_usd_per_year | ~ USD/year | (0, 1) | unknown | null | A cover flag times the revenue it indemnifies; re-declare as share '1' first.
capital_gains_tax | BASE-NEEDED | capital_gains_tax_paid = capital_gains_tax * realised_capital_gain_usd | USD/year | (0, 0.4) | 0.2 | null | A rate whose base (realised gains) the graph does not carry.
carbon_credit_insurance | GATE-PRODUCT | carbon_credit_insurance = carbon_credit_insurance * carbon_revenue_usd_per_year | ~ USD/year | (0, 1) | unknown | null | Cover against carbon-credit invalidation scales with carbon revenue (650,578,257.11).
carbon_price_risk | PRODUCT | carbon_price_risk = carbon_price_risk * carbon_revenue_usd_per_year | ~ USD/year | (0, 0.1) | unknown | null | A premium share charged against carbon revenue; docs/what-if.md puts it at 2% (13,011,565.14), but the node's default is the placeholder.
carbon_tax_coverage | PRODUCT | carbon_tax_coverage = carbon_tax_coverage * emissions_mtco2_per_year | MtCO2/year ✓ | (0, 1) | 13.0116 | null | The taxed share of emissions; unit_of returns MtCO2/year.
carbon_tax_interaction | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | Whether a carbon tax offsets or stacks with other levies is a regime design, not a measurable share.
cash_sweep | PRODUCT | cash_sweep = cash_sweep * (cfads_usd_per_kw_year - debt_service_usd_per_kw_year) * total_capacity_mw * 1000 | ~ USD/year | (0, 1) | unknown | null | A share of distributable cash swept to debt service; unit_of is None until cash_sweep is re-declared '1' and its 500000 placeholder replaced.
cat_bond_parameters | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | Tranche structure, trigger and attachment are negotiated terms with no arithmetic relation to the project.
cat_bond_spread | PRODUCT | cat_bond_spread = cat_bond_spread * 0.0001 * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000 | USD (dim [currency]) ✓ | (200, 2500) | 671,999,999.99 | null | The coupon on the debt tranche; basis_points is dimensionless, so the additive `cost_of_debt + spread/10000` form RAISES and only the multiplicative form is legal.
change_of_control | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A contract clause, present or absent.
civil_unrest_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index; the graph's continuous analogue is geopolitical_risk_index.
claims_history | PRODUCT | claims_history = loss_ratio * insurance_premium_usd_per_kw_year * total_capacity_mw * 1000 | USD/year ✓ | (0, 1e11) | 42,000,000 | null | Incurred claims are the loss ratio applied to premium; the declared unit '1' and range (0, 1e6) must widen or the value is refused.
climate_risk_disclosure | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | TCFD alignment is a disclosure regime, an admissible set of practices.
counterparty_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A counterparty rating; param_eqn.md's margin link needs a notional the graph does not carry.
country_risk_rating | QUALITATIVE | -- | categorical | {AAA..D} | unknown | null | A letter rating; the continuous analogue is sovereign_risk_premium.
cross_default | QUALITATIVE | -- | bool | {0,1} | unknown | null | A contract clause.
currency_hedge_cost | BASE-NEEDED | currency_hedge_cost_usd = currency_hedge_cost * fx_denominated_debt_usd | USD/year | (0, 0.1) | unknown | null | Needs the FX-denominated debt stock; the worklist already flags that its base is a currency exposure.
currency_risk_premium | PRODUCT | currency_risk_premium = currency_risk_premium * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 0.2) | unknown | null | A premium on the debt tranche; docs/what-if.md gives 5% (420,000,000), the node default is the placeholder.
current_account_balance | BASE-NEEDED | current_account_balance = current_account_share_of_gdp * gdp_usd_per_year | USD/year | (-1e12, 1e12) | unknown | null | Needs gdp_usd_per_year.
customs_duty | PRODUCT | customs_duty = import_duty_equipment | 1 ✓ | (0, 0.5) | 0.1 | Rate-based levy and allowance definitions (standard fiscal accounting) | Duplicate row; nominate import_duty_equipment canonical and make this the alias.
cyber_incident_response | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An incident-response capability, not a quantity.
cyber_insurance | GATE-PRODUCT | cyber_insurance = cyber_insurance * total_revenue_usd_per_year | ~ USD/year | (0, 1) | unknown | null | Cover flag times the revenue at risk; re-declare as a share first.
cyber_threat_level | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A threat index.
debt_management | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An organisational capability.
debt_service_coverage_ratio | PRODUCT | debt_service_coverage_ratio = dscr_min | 1 ✓ | (1, 3) | 1.3 | null | The same lender floor as dscr_min; two names for one number.
debt_sustainability | BASE-NEEDED | debt_sustainability = external_debt_usd / gdp_usd_per_year | years | (0, 20) | unknown | null | Needs external debt in currency and a GDP level; neither exists.
default_events | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A contract clause.
deductible_levels | PRODUCT | deductible_levels = deductible_share * capex_usd_per_kw * total_capacity_mw * 1000 | USD ✓ | (0, 1e10) | 240,000,000 | null | The share-of-asset version the description names; unit '1' must become USD.
double_tax_treaty | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A treaty network is a legal set, not a measurement.
drought_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index.
exchange_rate_usd_local | QUALITATIVE | -- | USD/local | (0.0001, 10000) | unknown | null | An exogenous market price; no equation fixes it, only a real unit and range.
exchange_rate_volatility | BASE-NEEDED | exchange_rate_volatility = stdev(exchange_rate_usd_local_series) | 1/year | (0, 2) | unknown | null | Needs the FX series; a single rate cannot give a volatility.
export_competitiveness | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A composite index.
export_duty | PRODUCT | export_duty = export_duty * hydrogen_export_revenue_usd_per_year | USD/year ✓ | (0, 0.3) | 0.0 | Rate-based levy and allowance definitions (standard fiscal accounting) | The duty on exported energy carriers; zero at the shipped rate.
exposure_index | QUALITATIVE | -- | 1 | (0, 1) | 0.5 | null | A composite index whose construction is the admissible set.
external_debt | BASE-NEEDED | external_debt = external_debt_share_of_gdp * gdp_usd_per_year | USD | (0, 1e13) | unknown | null | Needs gdp_usd_per_year; the project tranche (8,400,000,000) is a different object.
flood_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index.
force_majeure_insurance | GATE-PRODUCT | force_majeure_insurance = force_majeure_insurance * total_revenue_usd_per_year | ~ USD/year | (0, 1) | unknown | null | Cover flag times revenue at risk.
foreign_direct_investment | BASE-NEEDED | foreign_direct_investment = fdi_share_of_gdp * gdp_usd_per_year | USD/year | (0, 1e12) | unknown | null | Needs gdp_usd_per_year.
foreign_exchange_reserves | BASE-NEEDED | foreign_exchange_reserves = reserve_cover_months * imports_usd_per_year / 12 | USD | (0, 1e12) | unknown | null | Needs imports_usd_per_year; reserve cover is measured in months of imports.
free_trade_zone_benefits | GATE-PRODUCT | free_trade_zone_benefits = free_trade_zone_benefits * import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 1) | unknown | null | The share of duty forgone in a zone; unit None makes unit_of undecidable.
geopolitical_risk_index | QUALITATIVE | -- | 1 | (0, 1) | 0.5 | null | A composite index.
grid_reliability_saifi | PRODUCT | grid_reliability_saifi = service_quality_standards | events/year ✓ | (1, 50) | 15 | IEEE Std 1366 (distribution reliability) | The SAIFI target is the service-quality standard the ceiling bound already reads.
import_duty_equipment | PRODUCT | import_duty_equipment = import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000 | USD ✓ | (0, 0.5) | 1,200,000,000 | Rate-based levy and allowance definitions (standard fiscal accounting) | Duty on the landed equipment value.
import_duty_exemption | GATE-PRODUCT | import_duty_exemption = import_duty_exemption * import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 1) | unknown | null | The exempt share of duty; the `(1 - exemption)` form evaluates to -49,999.9 at the placeholder and must not be written.
insurance_premiums | PRODUCT | insurance_premiums = premium_share_of_asset * capex_usd_per_kw * total_capacity_mw * 1000 | USD ✓ | (0, 1e10) | 96,000,000 | null | The share-of-asset version the description names; unit '1' must become USD.
interest_rate_debt | PRODUCT | interest_rate_debt = cost_of_debt | 1/year ✓ | (0.03, 0.2) | 0.09 | Credit-spread decomposition (BIS) | Alias of the derived borrower rate; note the catalog says 8% while the graph's cost_of_debt is 9%.
landslide_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index.
liability_exposure | QUALITATIVE | -- | USD | (0, 1e11) | unknown | null | The scope of liability is the firm's book; no share of it exists in the graph.
loan_life_coverage_ratio | THRESHOLD | llcr_estimate geq loan_life_coverage_ratio | 1 ✓ | (1, 3) | lhs 2.8389 / rhs 1.4 HOLDS | null | The LLCR floor a lender accepts; holds at document defaults.
maladaptation_risk | PRODUCT | maladaptation_risk = risk_of_maladaptation | 1 ✓ | (0, 1) | 0.2 | null | Duplicate of risk_of_maladaptation.
material_adverse_change | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A contract clause.
microinsurance | BASE-NEEDED | microinsurance = households_covered * microinsurance_premium_share_of_income * household_income_usd_per_year | USD/year | (0, 1e10) | unknown | null | Needs households_covered; the whole population would give the market (400,000,000), not the firm's book.
microinsurance_premium_share_of_income | PRODUCT | microinsurance_premium_share_of_income = microinsurance_premium_share_of_income * household_income_usd_per_year | USD/year ✓ | (0.001, 0.05) | 40.0 | null | The per-household premium; 40 USD/year at the shipped 1% of 4,000.
official_development_assistance | BASE-NEEDED | official_development_assistance = oda_share_of_gdp * gdp_usd_per_year | USD/year | (0, 1e11) | unknown | null | Needs gdp_usd_per_year.
parametric_insurance | BASE-NEEDED | parametric_insurance = parametric_insurance_coverage * expected_annual_loss_usd | USD | (0, 1e11) | unknown | null | Needs the expected annual loss; physical_risk_score is a score, not a loss.
parametric_insurance_coverage | BASE-NEEDED | parametric_insurance_coverage = parametric_insurance_coverage * expected_annual_loss_usd | USD | (0, 1) | unknown | null | A share whose base the graph does not carry.
parametric_trigger_threshold | QUALITATIVE | -- | 1 | (0.5, 1) | 0.9 | null | A trigger level is a policy design choice against the hazard distribution.
parent_company_guarantee | GATE-PRODUCT | parent_company_guarantee = parent_company_guarantee * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 1) | unknown | null | The guaranteed share of the debt tranche.
performance_bond | PRODUCT | performance_bond = performance_bond * capex_usd_per_kw * total_capacity_mw * 1000 | USD ✓ | (0, 0.2) | 600,000,000 | null | Bond posted as a share of capex.
physical_risk_score | QUALITATIVE | -- | 1 | (0, 1) | 0.4 | null | A composite score; its construction is the admissible set, and products read it as a weight.
political_risk_insurance | GATE-PRODUCT | political_risk_insurance = political_risk_insurance * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 1) | unknown | null | The insured share of the asset against political events.
ppa_force_majeure | QUALITATIVE | -- | bool | {0,1} | unknown | null | A contract clause.
project_irr_hurdle | PRODUCT | project_irr_hurdle = discount_rate * (1 + equity_return_target) | 1/year ✓ | (0.05, 0.25) | 0.095784 | null | The additive `discount_rate + equity_return_target` RAISES because equity_return_target is '1'; only multiplicative composition is legal, giving 9.58% against docs' 12%.
refinancing_terms | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | Negotiated terms.
reinsurance_parameters | PRODUCT | reinsurance_parameters = (1 - retention_share) * insurance_premium_usd_per_kw_year * total_capacity_mw * 1000 | USD/year ✓ | (0, 1e10) | 18,000,000 | null | The ceded share of premium; the market-level statistic the description names.
reliability_centred_maintenance | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A maintenance programme flag.
remittance_dependency | BASE-NEEDED | remittance_dependency = remittance_flows / gdp_usd_per_year | 1 | (0, 1) | unknown | null | Needs gdp_usd_per_year.
remittance_flows | BASE-NEEDED | remittance_flows = remittance_share_of_gdp * gdp_usd_per_year | USD/year | (0, 1e12) | unknown | null | Needs gdp_usd_per_year.
ring_fencing_rules | PRODUCT | ring_fencing_rules = ring_fencing_rules * regulatory_asset_base | USD million ✓ | (0, 1) | 2,400 | null | The legally ring-fenced share of the regulatory asset base (4,800).
risk_based_maintenance | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A programme flag.
risk_of_maladaptation | QUALITATIVE | -- | 1 | (0, 1) | 0.2 | null | A probability index; the alias target stays a declared index.
risk_transfer_mechanisms | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A menu of instruments, not a quantity.
sanctions_exposure | GATE-PRODUCT | sanctions_exposure = sanctions_exposure * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 1) | unknown | null | The exposed share of the asset; unit None makes the dimension undecidable.
settlement_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A settlement practice; param_eqn.md's margin link needs a notional.
solvency_capital | BASE-NEEDED | solvency_capital = solvency_capital_ratio * required_solvency_capital_usd | USD | (0, 1e11) | unknown | null | The ratio's denominator (the SCR) is not in the graph; eligible own funds cannot be computed without it.
solvency_capital_ratio | THRESHOLD | solvency_capital_ratio geq 1.0 | 1 ✓ | (0.8, 3) | lhs 1.6 / rhs 1.0 HOLDS | null | The prudential floor; holds at defaults and the constant rhs is legal through parse_side.
sovereign_risk_premium | PRODUCT | sovereign_risk_premium = sovereign_risk_premium * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 0.2) | unknown | null | A country premium on the debt tranche; docs give it as country-specific, so no single default is justified.
stamp_duty | PRODUCT | stamp_duty = stamp_duty * capex_usd_per_kw * total_capacity_mw * 1000 | USD ✓ | (0, 0.1) | 240,000,000 | Rate-based levy and allowance definitions (standard fiscal accounting) | Duty on the property transfer at 2% of asset value.
step_in_rights | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A contract clause.
tax_holiday_conditions | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | Legal eligibility conditions.
tax_incentive_zones | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A spatial legal designation.
tax_incentives | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A policy menu.
technology_risk_premium | PRODUCT | technology_risk_premium = technology_risk_premium * (1 - debt_fraction) * capex_usd_per_kw * total_capacity_mw * 1000 | ~ USD | (0, 0.1) | unknown | null | A premium on the equity-funded share; docs give 3%, but the node carries the placeholder.
terrorism_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index.
thin_capitalisation_limit | PRODUCT | thin_capitalisation_limit = debt_equity_ratio / thin_capitalisation_limit | 1 ✓ | (1, 5) | 1.5533 | null | The leq bound FAILS at defaults (2.33 > 1.5), so the honest form is the utilisation ratio, per batch 22.
thin_capitalisation_rules | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A tax-code regime.
trade_agreement | SCENE-SWITCH | -- | categorical | {Bilateral, Pool, AfSEM} | unknown | null | Selects the trade regime the graph does not model; it is a mode, not a quantity.
trade_flow_parameters | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A parameter set whose members are not in the graph.
transaction_costs | PRODUCT | transaction_costs = transaction_costs * total_revenue_usd_per_year | ~ USD/year | (0, 0.1) | unknown | null | A share of revenue; unit_of is None until re-declared '1', and the 500000 placeholder must go.
transfer_pricing_rules | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A tax-code regime.
weather_derivatives | BASE-NEEDED | weather_derivatives = weather_derivative_notional_share * weather_sensitive_revenue_usd | USD | (0, 1e10) | unknown | null | Needs the weather-sensitive revenue the derivative hedges.
wildfire_risk | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A hazard index.
withholding_tax_dividends | PRODUCT | withholding_tax_dividends = withholding_tax_dividends * (cfads_usd_per_kw_year - debt_service_usd_per_kw_year) * total_capacity_mw * 1000 | USD/year ✓ | (0, 0.3) | 129,102,749.56 | Rate-based levy and allowance definitions (standard fiscal accounting) | Tax on distributed cash after debt service.
withholding_tax_interest | PRODUCT | withholding_tax_interest = withholding_tax_interest * debt_fraction * capex_usd_per_kw * cost_of_debt * total_capacity_mw * 1000 | USD/year ✓ | (0, 0.3) | 75,600,000 | Rate-based levy and allowance definitions (standard fiscal accounting) | Tax on interest paid.
working_capital_allowance | PRODUCT | working_capital_allowance = working_capital_allowance * total_revenue_usd_per_year | USD/year ✓ | (0, 0.25) | 315,080,403.69 | null | The regulator's working-capital allowance as a share of revenue.
```

NEW BASES NEEDED

| base | unit | default | where the default comes from | product it completes |
|---|---|---|---|---|
| gdp_usd_per_year | USD/year | unknown | No level exists; `population_total` (45,000,000) × a `gdp_per_capita_usd` that is also absent. `gdp_growth_rate` gives only the growth. | balance_of_payments, current_account_balance, debt_sustainability, external_debt, foreign_direct_investment, official_development_assistance, remittance_dependency, remittance_flows |
| imports_usd_per_year | USD/year | unknown | No import value in currency; `net_imports_twh` (0.0) is a quantity, not a value. | foreign_exchange_reserves |
| households_covered | count | energy_poor_households (5,000,000) | The graph's own eligible-population count, derived from `population_total` and the poverty line. | microinsurance |
| expected_annual_loss_usd | USD/year | unknown | `physical_risk_score` is a normalised score, not a loss; multiplying it by asset value would invent a loss ratio. | parametric_insurance, parametric_insurance_coverage |
| required_solvency_capital_usd | USD | unknown | The SCR depends on the firm's book; `physical_risk_score × asset` would invent the standard formula. | solvency_capital |
| fx_denominated_debt_usd | USD | unknown | The project tranche (`debt_fraction × capex × capacity × 1000` = 8,400,000,000) is the upper bound, but the foreign share is not in the graph. | currency_hedge_cost |
| weather_sensitive_revenue_usd | USD/year | unknown | No revenue split by weather sensitivity exists. | weather_derivatives |
| realised_capital_gain_usd | USD/year | unknown | No disposal or gain line exists. | capital_gains_tax |
| exchange_rate_usd_local_series | USD/local, timeseries | unknown | A single rate cannot give a volatility; the catalog's method cell is `arch` (GARCH). | exchange_rate_volatility |

PROPOSED BATCHES

**Batch 23 — insurance share-of-asset products (7).** Method: share × `capex_usd_per_kw × total_capacity_mw × 1000`, the graph's own asset-value identity. `insurance_premiums`, `deductible_levels`, `performance_bond`, `claims_history`, `reinsurance_parameters`, `ring_fencing_rules`, `cat_bond_spread`. Six of seven verify dimensionally today; `claims_history` needs its unit and range corrected before the equation can hold its own value.

**Batch 24 — insurance and contract gates (9).** Method: a declared share times the base it indemnifies, with every gate re-declared `unit: '1'` and its 500000 placeholder replaced in the same batch. `business_interruption_insurance`, `force_majeure_insurance`, `cyber_insurance`, `carbon_credit_insurance`, `political_risk_insurance`, `parent_company_guarantee`, `sanctions_exposure`, `free_trade_zone_benefits`, `import_duty_exemption`. All nine are undecidable until the re-declaration; the `(1 - exemption)` form must be avoided.

**Batch 25 — tax and duty products (9).** Method: rate × the base the levy attaches to, cited to the standard-fiscal row. `import_duty_equipment`, `export_duty`, `stamp_duty`, `withholding_tax_dividends`, `withholding_tax_interest`, `carbon_tax_coverage`, `working_capital_allowance`, `customs_duty` (alias), `thin_capitalisation_limit` (ratio, not bound).

**Batch 26 — aliases, thresholds and the hurdle (9).** Method: equality where two rows are one quantity, `geq` where a floor holds at defaults, ratio where a bound fails. `debt_service_coverage_ratio`, `interest_rate_debt`, `grid_reliability_saifi`, `maladaptation_risk`, `loan_life_coverage_ratio`, `solvency_capital_ratio`, `project_irr_hurdle`, `microinsurance_premium_share_of_income`, `ring_fencing_rules` if not taken in 23.

**Batch 27 — risk-premium charges and cash shares (6).** Method: a premium share times the tranche or revenue it prices, multiplicative only because every premium is dimensionless. `sovereign_risk_premium`, `technology_risk_premium`, `currency_risk_premium`, `carbon_price_risk`, `cash_sweep`, `transaction_costs`. Each needs its unit set to `'1'` and a real default; docs/what-if.md supplies 5%, 3%, 5%, 2% for the four premiums.

**Batch 28 — the macro and insurance bases (17 + the 9 new bases).** Method: declare the base with a justified default where one exists, then write the product. `balance_of_payments`, `capital_gains_tax`, `currency_hedge_cost`, `current_account_balance`, `debt_sustainability`, `exchange_rate_volatility`, `external_debt`, `foreign_direct_investment`, `foreign_exchange_reserves`, `microinsurance`, `official_development_assistance`, `parametric_insurance`, `parametric_insurance_coverage`, `remittance_dependency`, `remittance_flows`, `solvency_capital`, `weather_derivatives`.

**Batch 29 — the declaration register (41).** Method: none — these are documented declarations, not equations, and the register's contract says so. `accumulation_risk`, `carbon_tax_interaction`, `cat_bond_parameters`, `change_of_control`, `civil_unrest_risk`, `climate_risk_disclosure`, `counterparty_risk`, `country_risk_rating`, `cross_default`, `cyber_incident_response`, `cyber_threat_level`, `debt_management`, `default_events`, `double_tax_treaty`, `drought_risk`, `exchange_rate_usd_local`, `export_competitiveness`, `exposure_index`, `flood_risk`, `geopolitical_risk_index`, `landslide_risk`, `liability_exposure`, `material_adverse_change`, `parametric_trigger_threshold`, `physical_risk_score`, `ppa_force_majeure`, `refinancing_terms`, `reliability_centred_maintenance`, `risk_based_maintenance`, `risk_of_maladaptation`, `risk_transfer_mechanisms`, `settlement_risk`, `step_in_rights`, `tax_holiday_conditions`, `tax_incentive_zones`, `tax_incentives`, `terrorism_risk`, `thin_capitalisation_rules`, `trade_flow_parameters`, `transfer_pricing_rules`, `wildfire_risk`. `trade_agreement` is the one SCENE-SWITCH and belongs here as a categorical declaration.

Counts: 28 PRODUCT, 9 GATE-PRODUCT, 2 THRESHOLD, 1 SCENE-SWITCH, 17 BASE-NEEDED, 41 QUALITATIVE = 98.

# SLICE land-water-env

```
NODE | CLASS | lhs = rhs | unit | range | default | reference | reason
agricultural_irrigation_load | BASE-NEEDED | agricultural_irrigation_load = irrigation_coverage * arable_land_hectares * irrigation_kw_per_ha / 1000.0 | MW | 0-5000 | unknown | null | Needs arable_land_hectares and a pumping intensity; neither exists.
agricultural_machinery | BASE-NEEDED | agricultural_machinery_electricity_mwh = agricultural_machinery * agricultural_machinery_energy_mwh | 1 | 0-1 | 0.05 | null | Share of machinery energy, not of sector demand; no machinery-energy base.
airport_electrification | BASE-NEEDED | airport_electricity_mwh = airport_electrification * airport_operations_mwh | 1 | 0-1 | 0.1 | null | Ground-operations energy is the base; the graph carries no airport energy.
archaeological_sites | BASE-NEEDED | archaeological_sites = archaeological_sites_density * study_area_km2 / 100.0 | sites | 0-1e6 | unknown | null | Count = density x area; study_area_km2 is absent and the /100 is the density's denominator.
archaeological_sites_density | PRODUCT | (operand of archaeological_sites) | sites/100km2 | 0-30 | 1.0 | null | Measured layer, named by the count once area exists.
aviation_fuel_demand | BASE-NEEDED | synthetic_aviation_fuel_mwh = synthetic_fuel_share_aviation * aviation_fuel_demand | MWh/yr | 0-1e6 | unknown | null | Node carries no unit, so every product against it is undecidable; MWh/yr is what the SAF share needs.
biodiversity_impact | PRODUCT | biodiversity_impact = biodiversity_intactness_before - biodiversity_intactness_index | 1 | 0-1 | derived | null | The loss is the difference the two BII nodes express; both ship 0.7 so it is 0 at defaults, unlike the other impact indices.
biodiversity_intactness_before | PRODUCT | (operand of biodiversity_impact) | 1 | 0-1 | 0.7 | null | Measured baseline; named as the minuend.
biodiversity_intactness_index | PRODUCT | (operand of biodiversity_impact) | 1 | 0-1 | 0.7 | null | Measured post-project value; equal to baseline, which is why impact is zero.
biogas_capacity | BASE-NEEDED | biogas_capacity = biogas_yield_mwh_per_t * organic_waste_t_per_year / 8760.0 | MW | 0-1000 | unknown | null | Sized from a feedstock the graph does not carry.
biomass_sustainability_limit | BASE-NEEDED | biomass_capacity * 8760 * capacity_factor_biomass * biomass_fuel_t_per_mwh <= biomass_sustainability_limit | tonne/yr | 0-1e6 | unknown | null | A fuel-mass ceiling; comparing capacity to it needs a heat rate the graph lacks.
co_emissions | BASE-NEEDED | co_emissions = generation_twh * 1000000.0 * co_emission_factor_t_per_mwh | tonne/yr | 0-1e6 | unknown | null | Activity base exists; the per-pollutant factor does not and cannot be borrowed from the CO2 factor.
coastal_erosion | GATE-SCENE-SWITCH | -- | m/yr | 0-10 | unknown | null | Coastal-hazard projection; configures the adaptation scenario.
cold_snap_frequency | GATE-SCENE-SWITCH | -- | events/yr | 0-100 | unknown | null | Climate-scenario dial read by the demand model.
cold_storage_load | BASE-NEEDED | cold_storage_load = cold_storage_volume_m3 * cold_storage_kw_per_m3 / 1000.0 | MW | 0-1000 | unknown | null | No volume, throughput or degree-day base exists.
conservation_easements | QUALITATIVE | -- | hectares (instrument) | 0-1e6 | unknown | null | A tenure instrument, not a measurement.
construction_load | BASE-NEEDED | construction_load = construction_energy_mwh / (construction_period * 730.0) | MW | 0-1000 | unknown | null | construction_period exists; construction energy does not, and the 730 is a scale the walker cannot see.
construction_machinery | BASE-NEEDED | construction_machinery_electricity_mwh = construction_machinery * construction_energy_mwh | 1 | 0-1 | 0.05 | null | Same missing construction-energy base.
cooling_water_demand | PRODUCT | cooling_water_demand = cooling_water_demand_m3 | m3 | 0-1e11 | derived | The fragments' alias register | Duplicate of the coupled extensive node; alias is the honest coupling.
cultural_heritage_impact | PRODUCT | cultural_heritage_impact = cultural_heritage_impact_score | 1 | 0-1 | derived | The fragments' alias register | Duplicate of the index node.
cultural_heritage_impact_score | PRODUCT | (operand of cultural_heritage_impact) | 1 | 0-1 | 0.2 | null | Measured composite score.
cultural_heritage_sites_density | PRODUCT | (operand of cultural_heritage_sites) | sites/100km2 | 0-50 | 2.0 | null | Measured layer; its count needs study_area_km2.
desalination_capacity | BASE-NEEDED | desalination_capacity = desalination_demand / (8760 * load_factor) | MW | 0-1000 | unknown | null | Capacity from a demand the graph does not carry in MWh.
desalination_demand | BASE-NEEDED | desalination_demand = desalinated_water_m3_per_year * desalination_energy_kwh_per_m3 / 1000.0 | MWh/yr | 0-1e6 | unknown | null | Needs a water volume and an RO intensity; catalog method is the RO energy curve.
desalination_energy | BASE-NEEDED | (intensity) | kWh/m3 | 2-6 | unknown | null | Unit rate with no base; pairs with desalination_demand.
drought_frequency | GATE-SCENE-SWITCH | -- | multiplier | 0-5 | unknown | null | Hydrology-scenario dial.
drought_risk | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Composite hazard index; admissible set is a choice.
drought_severity | GATE-SCENE-SWITCH | -- | multiplier | 0-5 | unknown | null | Hydrology-scenario dial.
ecosystem_services_index | QUALITATIVE | -- | 1 | 0-1 | 0.7 | null | Composite index; a choice, not a measurement.
emergency_shelter_load | BASE-NEEDED | emergency_shelter_load = shelter_occupancy * shelter_kw_per_person / 1000.0 | MW | 0-500 | unknown | null | Needs an occupancy base; exposed_population is not the shelter population.
export_competitiveness | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Trade index; admissible set is a choice.
export_duty | PRODUCT | export_duty_usd_per_year = export_duty * hydrogen_export_revenue_usd_per_year | USD/yr | 0-6e8 | derived | null | Rate times the revenue base; verified [currency]/[time]. Defaults give 0.
fishing_community_load | BASE-NEEDED | fishing_community_load = fishing_vessels * vessel_kw / 1000.0 | MW | 0-200 | unknown | null | Needs a vessel count; fishing_vessel_fuel is a fuel, not a count.
fishing_vessel_fuel | BASE-NEEDED | fishing_vessel_fuel = fishing_vessel_hours * fishing_fuel_l_per_h | litre/yr | 0-1e6 | unknown | null | Needs effort hours and a burn rate.
flood_risk | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Composite hazard index.
freight_electrification | BASE-NEEDED | freight_electric_mwh = freight_electrification * freight_tonne_km * freight_kwh_per_tonne_km | 1 | 0-1 | 0.05 | null | Tonne-km base absent (recorded in batch 20); the share alone is inert.
gasification_capacity | BASE-NEEDED | gasification_capacity = gasification_feed_t_per_year * gasification_mwh_per_t / 8760.0 | MW | 0-1000 | unknown | null | Feedstock base absent.
glacial_lake_outburst | GATE-SCENE-SWITCH | -- | 1 | 0-1 | unknown | null | GLOF hazard dial; no derivation exists.
habitat_loss | PRODUCT | habitat_loss = habitat_loss_hectares | hectares | 0-50000 | derived | The fragments' alias register | Duplicate of the coupled extensive node.
habitat_loss_hectares | PRODUCT | (operand of habitat_loss, land_acquisition_costs) | hectares | 0-50000 | 500.0 | null | Measured land take; the base of two products.
heat_pump_cop | BASE-NEEDED | heat_pump_cop = f(temperature_increase) | 1 | 1.5-6 | unknown | null | COP is a temperature curve; temperature_increase carries no unit and no equation may read it as a scalar.
heat_stress | GATE-SCENE-SWITCH | -- | 1 | 0-1 | unknown | null | Temperature-scenario dial.
heatwave_frequency | GATE-SCENE-SWITCH | -- | events/yr | 0-100 | unknown | null | Climate-scenario dial.
hydro_drought_multiplier | PRODUCT | hydro_capacity_factor_effective = capacity_factor_hydro * hydro_drought_multiplier | 1 | 0-1 | derived | null | Verified dimensionless; gives the drought-adjusted factor nothing currently computes (capacity_factor_hydro 0.55 x 0.5 = 0.275).
hydrogen_export_port | BASE-NEEDED | hydrogen_export_port_throughput = hydrogen_export_volume / 8760.0 | MW | 0-1e6 | unknown | null | Port throughput from the export volume; the node itself carries no unit.
import_dependency | PRODUCT | import_dependency_share = abs(net_imports_twh) / demand_twh | 1 | 0-1 | derived | null | Verified dimensionless; abs() is needed because net_imports is signed and the range admits -1000.
import_duty_equipment | PRODUCT | import_duty_cost_mm_usd = import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000.0 / 1000000.0 | USD million | 0-3e4 | derived | null | House capex idiom (climate_proofed_capex_definition); dimensions resolve to [currency] although the walker's unit string keeps the MW/kW pair.
import_duty_exemption | BASE-NEEDED | import_duty_cost_mm_usd = (1.0 - import_duty_exemption) * import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000.0 / 1000000.0 | 1 | 0-1 | unknown | null | Placeholder with no unit; as a fraction exempted its product is the duty actually paid, and 1.0 - None is undecidable today.
industrial_heat_demand | BASE-NEEDED | industrial_heat_demand = industrial_demand_twh * industrial_heat_share * 1000.0 / 8760.0 | MW | 0-5000 | unknown | null | Sector electricity exists; the heat share and a thermal base do not.
irrigation_coverage | BASE-NEEDED | irrigated_hectares = irrigation_coverage * arable_land_hectares | 1 | 0-1 | 0.15 | null | Share with no arable-land denominator.
irrigation_pumping_demand | BASE-NEEDED | irrigation_pumping_demand = irrigated_hectares * irrigation_kwh_per_ha / 1000.0 | MWh/yr | 0-1e6 | unknown | null | Same missing arable base plus an intensity.
islanding_capability | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Capability score; admissible set is a choice.
land_acquisition_cost_per_hectare | PRODUCT | (operand of land_acquisition_costs) | USD/hectare | 100-5e5 | 5000.0 | null | Measured rate; base of one product.
land_acquisition_costs | PRODUCT | land_acquisition_costs = land_acquisition_cost_per_hectare * habitat_loss_hectares | USD | 5e4-2.5e10 | derived | null | Verified [currency]; 2.5e6 at defaults.
land_aggregation | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Organisational difficulty; the measurable part is land_aggregation_fragmentation.
land_aggregation_fragmentation | PRODUCT | parcels_to_assemble = land_aggregation_fragmentation * habitat_loss_hectares / 100.0 | parcels | 0-2.5e5 | derived | null | Density x area / 100; resolves to [parcel], which is why the registry carries the base dimension.
land_availability | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Organisational; the measured part is land_availability_fraction.
land_availability_fraction | PRODUCT | available_hectares = land_availability_fraction * study_area_km2 * 100.0 | 1 | 0-1 | 0.5 | null | Share with no area base; pairs with land_availability.
land_rights | QUALITATIVE | -- | class | n/a | unknown | null | Legal class.
land_tenure | QUALITATIVE | -- | class | n/a | unknown | null | Legal class.
land_use_change | PRODUCT | land_use_change = habitat_loss_hectares | hectares | 0-50000 | derived | The fragments' alias register | Same physical quantity under the catalog's second name.
land_use_conflict_index | PRODUCT | (operand of land_use_conflicts) | 1 | 0-1 | 0.3 | null | Measured composite index.
land_use_conflicts | PRODUCT | land_use_conflicts = land_use_conflict_index | 1 | 0-1 | derived | The fragments' alias register | Duplicate of the index node.
land_use_planning | QUALITATIVE | -- | class | n/a | unknown | null | Governance class.
landfill_gas_capacity | BASE-NEEDED | landfill_gas_capacity = landfilled_waste_t_per_year * lfg_mwh_per_t / 8760.0 | MW | 0-500 | unknown | null | Waste-mass base absent.
landslide_risk | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Geotechnical hazard index.
mercury_emissions | BASE-NEEDED | mercury_emissions = generation_twh * 1000000.0 * mercury_factor_kg_per_gwh / 1000.0 | tonne/yr | 0-100 | unknown | null | Per-pollutant factor absent; mercury is quoted per GWh, hence the 1e6/1000 pair.
military_energy_demand | BASE-NEEDED | military_energy_demand = military_bases * base_mw | MW | 0-500 | unknown | null | Needs an installation base.
mining_demand_growth | BASE-NEEDED | mining_demand_growth = mining_demand_mwh * mining_growth_rate | MW | 0-1000 | unknown | null | Needs a mining load base and a growth rate.
mining_electrification | BASE-NEEDED | mining_electric_mwh = mining_electrification * mining_energy_mwh | 1 | 0-1 | 0.1 | null | Mining energy base absent; the share alone is inert.
mining_haulage | BASE-NEEDED | mining_haulage = ore_tonnes * haul_km * haul_kwh_per_tonne_km | tonne-km | 0-1e7 | unknown | null | Tonne-km base absent.
mining_hydrogen_haulage | BASE-NEEDED | mining_hydrogen_haulage = mining_haulage * hydrogen_haulage_share | tonne-km | 0-1e7 | unknown | null | Depends on mining_haulage, itself unbased.
nox_emissions | BASE-NEEDED | nox_emissions = generation_twh * 1000000.0 * nox_factor_t_per_mwh | tonne/yr | 0-1e5 | unknown | null | Per-pollutant factor absent.
pm10_emissions | BASE-NEEDED | pm10_emissions = generation_twh * 1000000.0 * pm10_factor_t_per_mwh | tonne/yr | 0-1e5 | unknown | null | Per-pollutant factor absent; distinct from the ambient pm25 node batch 22 added.
pm25_emissions | PRODUCT | pm25_emissions = pm25_kt_per_year | kt/yr | 0-1000 | derived | The fragments' alias register | Duplicate of the coupled emission-rate node.
port_electrification | BASE-NEEDED | port_electric_mwh = port_electrification * port_operations_mwh | 1 | 0-1 | 0.1 | null | Port energy base absent.
post_harvest_processing_load | BASE-NEEDED | post_harvest_processing_load = crop_tonnes * processing_kwh_per_t / 1000.0 | MW | 0-500 | unknown | null | Needs a crop-volume base.
precipitation_multiplier | PRODUCT | river_flow_adjusted_m3_per_s = precipitation_multiplier * river_mean_annual_flow_m3_per_s | 1 | 0-1 | derived | null | Verified m3/s; the batch-22 flow node is otherwise read only by environmental_flow.
protected_areas | BASE-NEEDED | protected_area_hectares = protected_area_fraction * study_area_km2 * 100.0 | hectares | 0-1e6 | unknown | null | Needs the area base and a fraction; land_availability_fraction already carries the complement's intent.
public_transport_share | BASE-NEEDED | public_transport_pkm = public_transport_share * total_passenger_km | 1 | 0-1 | 0.3 | null | Passenger-km base absent (batch 20 recorded this).
pyrolysis_capacity | BASE-NEEDED | pyrolysis_capacity = pyrolysis_feed_t_per_year * pyrolysis_mwh_per_t / 8760.0 | MW | 0-1000 | unknown | null | Feedstock base absent.
railway_electrification | BASE-NEEDED | electrified_route_km = railway_electrification * railway_route_km | 1 | 0-1 | 0.2 | null | Route-km base absent; distribution_network_km is a different network.
sacred_sites | BASE-NEEDED | sacred_sites = sacred_sites_density * study_area_km2 / 100.0 | sites | 0-1e6 | unknown | null | Count = density x area; area absent.
sacred_sites_density | PRODUCT | (operand of sacred_sites) | sites/100km2 | 0-20 | 1.0 | null | Measured layer, named by the count.
salinity_gradient_capacity | BASE-NEEDED | salinity_gradient_capacity = salinity_gradient_m3_per_s * salinity_gradient_w_per_m3 / 1e6 | MW | 0-100 | unknown | null | Needs a flow and a power density.
sea_level_rise | GATE-SCENE-SWITCH | -- | m | 0-2 | unknown | null | CMIP6 projection; a scenario input.
shipping_fuel_demand | BASE-NEEDED | green_shipping_fuel_mwh = synthetic_fuel_share_shipping * shipping_fuel_demand | MWh/yr | 0-1e6 | unknown | null | Node has no unit; the share needs MWh/yr.
soil_contamination | PRODUCT | soil_contamination = soil_contamination_index | 1 | 0-1 | derived | The fragments' alias register | Duplicate of the index node.
soil_contamination_index | PRODUCT | (operand of soil_contamination) | 1 | 0-1 | 0.1 | null | Measured composite index.
solar_pv_land_constraint | THRESHOLD | solar_pv_capacity <= solar_pv_land_constraint | MW | 0-5e5 | unknown | null | A land ceiling in MW; holds only once the node carries MW and a default above the shipped 10000 MW solar_pv_capacity.
sox_emissions | BASE-NEEDED | sox_emissions = generation_twh * 1000000.0 * sox_factor_t_per_mwh | tonne/yr | 0-1e5 | unknown | null | Per-pollutant factor absent.
storm_surge | GATE-SCENE-SWITCH | -- | m | 0-5 | unknown | null | Coastal scenario dial.
synthetic_fuel_share_aviation | PRODUCT | (rate) | 1 | 0-1 | 0.05 | null | Rate on aviation_fuel_demand once that node has a unit.
synthetic_fuel_share_shipping | PRODUCT | (rate) | 1 | 0-1 | 0.05 | null | Rate on shipping_fuel_demand once that node has a unit.
temperature_increase | GATE-SCENE-SWITCH | -- | K | 0-5 | unknown | null | Scenario control; carries no unit today, which blocks every dependent curve.
temperature_target | GATE-SCENE-SWITCH | -- | K | 0-3 | unknown | null | Policy target; configures the run.
temporary_camp_load | BASE-NEEDED | temporary_camp_load = camp_population * camp_kw_per_person / 1000.0 | MW | 0-500 | unknown | null | Needs a camp occupancy base.
tourism_load | BASE-NEEDED | tourism_load = tourist_nights * tourism_kwh_per_night / 1000.0 | MW | 0-500 | unknown | null | Needs a tourist-night base.
traditional_land_use | QUALITATIVE | -- | class | n/a | unknown | null | Tenure/use class.
transboundary_water_constraint | THRESHOLD | total_water_demand_m3 <= transboundary_water_constraint | m3 | 0-1e11 | unknown | null | Ceiling on the coupled demand; needs m3 and a default above 94.1e6, the propagated demand.
transport_logistics | BASE-NEEDED | transport_logistics = freight_tonne_km * logistics_kwh_per_tonne_km | tonne-km | 0-1e8 | unknown | null | Tonne-km base absent.
voc_emissions | BASE-NEEDED | voc_emissions = generation_twh * 1000000.0 * voc_factor_t_per_mwh | tonne/yr | 0-1e5 | unknown | null | Per-pollutant factor absent.
voltage_support_requirement | PRODUCT | voltage_support_requirement = reactive_power_requirement | 1 | 0-2 | derived | The fragments' alias register | Duplicate of the coupled reactive-power share.
waste_to_energy_capacity | BASE-NEEDED | waste_to_energy_capacity = msw_t_per_year * wte_mwh_per_t / 8760.0 | MW | 0-1000 | unknown | null | Municipal-waste base absent.
wastewater_treatment_load | BASE-NEEDED | wastewater_treatment_load = wastewater_m3_per_year * treatment_kwh_per_m3 / 1000.0 | MW | 0-500 | unknown | null | Needs a wastewater volume; total_water_demand is supply, not effluent.
water_availability | BASE-NEEDED | water_availability = water_availability_m3 | m3 | 0-1e11 | unknown | null | Catalog calls it a multiplier while the coupled node is an extensive m3; aliasing would change the unit, so the semantics must be settled first.
water_pollution_load | BASE-NEEDED | water_pollution_load = effluent_m3 * bod_kg_per_m3 | kg BOD/yr | 0-1e6 | unknown | null | Needs effluent volume and a loading.
water_pumping_load | BASE-NEEDED | water_pumping_load = total_water_demand_m3 * pumping_kwh_per_m3 / 1000.0 | MWh/yr | 0-1e6 | unknown | null | The demand base exists; the intensity does not.
water_quality_impact | PRODUCT | water_quality_impact = 1.0 - water_quality_index | 1 | 0-1 | derived | null | Verified dimensionless; 0.4 at defaults.
water_quality_index | PRODUCT | (operand of water_quality_impact) | 1 | 0-1 | 0.6 | null | Measured composite index.
water_stress_index | PRODUCT | water_stress_index = total_water_demand_m3 / water_availability_m3 | 1 | 0-1 | derived | null | Verified dimensionless; 0.47 at defaults against the shipped 0.4 — the shipped default is not the document's own ratio.
wildfire_risk | QUALITATIVE | -- | 1 | 0-1 | unknown | null | Fire hazard index.
```

**NEW BASES NEEDED** (each unblocks the nodes listed; default is a derivation from a graph quantity where one exists, `unknown` where none does)

- `study_area_km2` (km2, default unknown) — unblocks archaeological_sites, sacred_sites, cultural_heritage_sites, protected_areas, land_availability_fraction. No graph quantity yields an area; deriving one from habitat_loss_hectares / land_availability_fraction would make the share its own denominator.
- `arable_land_hectares` (hectares, unknown) — unblocks irrigation_coverage, irrigation_pumping_demand, agricultural_irrigation_load.
- `railway_route_km`, `total_passenger_km`, `freight_tonne_km` (km, passenger-km, tonne-km; all unknown) — unblocks the four transport shares and transport_logistics.
- Six per-pollutant factors `co|nox|sox|pm10|voc_emission_factor_t_per_mwh`, `mercury_factor_kg_per_gwh` (unknown) — unblock the six emission nodes; they cannot be borrowed from `emission_factor_t_per_mwh` (0.5 t/MWh, CO2).
- `organic_waste_t_per_year`, `pyrolysis_feed_t_per_year`, `gasification_feed_t_per_year`, `msw_t_per_year`, `landfilled_waste_t_per_year` plus four yield rates (MWh/t) — unblock the five waste-to-energy capacities.
- `cold_storage_volume_m3`, `construction_energy_mwh`, `crop_tonnes`, `tourist_nights`, `camp_population`, `shelter_occupancy`, `military_bases`, `mining_energy_mwh`, `wastewater_m3_per_year`, `effluent_m3` (unknown) — the activity bases behind the thirteen `*_load` / `*_demand` nodes.
- `airport_operations_mwh`, `port_operations_mwh`, `agricultural_machinery_energy_mwh` (unknown) — the three electrification shares' bases.

**PROPOSED BATCHES**

- **Batch 23 — alias and duplicate resolutions (18).** cooling_water_demand, cultural_heritage_impact, habitat_loss, land_use_change, land_use_conflicts, pm25_emissions, soil_contamination, voltage_support_requirement, plus the nine index operands. Method: equality equations, reference `The fragments' alias register`. Caveat: water_availability is *not* included — its catalog description contradicts the coupled node's unit.
- **Batch 24 — products against bases the graph already carries (9).** land_acquisition_costs, land_aggregation_fragmentation, biodiversity_impact, water_quality_impact, water_stress_index, import_dependency, hydro_drought_multiplier, precipitation_multiplier, import_duty_equipment. Method: verified arithmetic; every rhs above was dimension-checked.
- **Batch 25 — rates on revenue bases (2) + thresholds (3).** export_duty, import_duty_exemption; biomass_sustainability_limit, solar_pv_land_constraint, transboundary_water_constraint. Method: rate x base, and `leq` ceilings that must carry a unit and a default above the propagated value.
- **Batch 26 — the area and activity bases (~20 nodes + ~14 bases).** The land-density counts, the load family, the electrification shares. Method: extensive base with a derived or `unknown` default, then the products.
- **Batch 27 — the pollutant and waste families (~15).** Six emission nodes, five capacity nodes, four intensities. Method: activity x per-unit factor.
- **Batch 28 — the qualitative and scene register (~25).** Every QUALITATIVE and GATE-SCENE-SWITCH row. Method: a documented declaration, no equation — the register's own contract.

Two findings the batch author should carry: `water_stress_index` computed from the document's defaults is 0.47, not the shipped 0.4; and `biodiversity_impact` is exactly 0 because both BII nodes ship 0.7, so the impact index is silent at defaults while its three siblings are not.

# SLICE employment-social

`unit_of(parse_side(rhs), g)` was run against a retyped copy of the current graph (`ParameterGraph(nodes, g.equations, g.edges, rules=g.rules)`), and every value below was read from `g.propagate(seed).values` with `seed` = each non-derived node's default. Tree moved under me mid-task: uncoupled 591→575, nodes 1168→1197, and `energy_poverty_gap`/`energy_poverty_rate` were coupled by the concurrent batch, so the slice is **78 nodes**, not 80.

Convention: in PRODUCT rows the lhs is the node in column 1 when the row is an alias; otherwise the lhs is a **new** node id and `unit/range` describe that new node. `derived` means no default is stored.

```
asset_age_distribution | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A histogram over vintages, not a scalar; the placeholder signature is the tell.
asset_management_maturity | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An ordinal maturity level (ISO 55000 ladder); no arithmetic consumes it.
asset_management_systems | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A capability set (EAM/CMMS presence), not a quantity.
child_labour_prohibition | PRODUCT | child_labour_screened_jobs = child_labour_prohibition * direct_jobs | jobs | (0,1e7) | derived | null | Share of the workforce screened, applied to the graph's own direct_jobs (43,000).
coal_community_dependencies | PRODUCT | coal_dependent_population = coal_community_dependencies * exposed_population | people | (0,1e9) | derived | null | Retype to a share of exposed population; 0.05 x 5e6 = 250,000.
community_benefit_sharing | PRODUCT | community_benefit_sharing = community_benefit_share_of_revenue | 1 | (0,0.05) | derived (0.01) | The catalog's own duplicate rows, resolved | Catalog duplicate of the canonical share; equality is the whole content.
community_development_funds | PRODUCT | community_development_funds = community_development_fund_share | 1 | (0,0.03) | derived (0.005) | The catalog's own duplicate rows, resolved | Duplicate of the fund share already used by community_development_fund_usd_per_year.
community_health_safety | PRODUCT | community_health_safety_spend_usd_per_year = community_health_safety * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Programme standard x allowed revenue, the shipped consumer_protection_spend idiom; 1.268 at defaults.
community_transition_funding | PRODUCT | community_transition_funding_usd_per_year = community_transition_funding * community_development_fund_usd_per_year | USD/year | (0,1e10) | derived | Benefit-sharing programmes (the graph's own revenue identity) | Share of the community fund; 3.15e6 at defaults.
complaint_handling | PRODUCT | complaint_handling_spend_usd_per_year = complaint_handling * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Complaint-handling programme spend as a share of allowed revenue; 1.268.
concession_terms | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | Contract terms are prose/enum; duration already exists as concession_duration.
condition_based_maintenance | GATE-SCENE | -- | 1 | (0,1) | 0.5 | null | Selects condition-triggered maintenance; it switches which hours model applies, it is not a product.
consumer_education | PRODUCT | consumer_education_spend_usd_per_year = consumer_education * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Consumer-education spend share of ARR; 0.634 at defaults.
crew_availability | PRODUCT | crew_shortfall_hours_per_year = (1 - crew_availability) * planned_maintenance_hours_per_year | hours/year | (0,8760) | derived | null | Unavailable crew converts planned hours into a shortfall; 14.4 h/year at defaults.
cross_subsidy_transparency | PRODUCT | cross_subsidy_transparency_spend_usd_per_year = cross_subsidy_transparency * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Disclosure programme cost as a share of ARR; 0.317.
digital_divide_metrics | QUALITATIVE | -- | 1 | (0,1) | 0.5 | null | A metric bundle; the scalar readings already exist as internet_penetration and mobile_coverage.
dispute_resolution_mechanism | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An institutional mechanism (enum), not a quantity.
early_retirement_packages | PRODUCT | early_retirement_jobs = early_retirement_packages * direct_jobs | jobs | (0,1e7) | derived | null | Share of the workforce offered early retirement; 860 at defaults.
employment_factor_biomass | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Employment intensity is an input; 4.3 = construction_jobs_per_mw + om_jobs_per_mw, the graph's own intensity.
employment_factor_coal | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_coal.
employment_factor_gas | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_gas.
employment_factor_geothermal | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_geothermal.
employment_factor_hydro | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_hydro.
employment_factor_solar | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_solar.
employment_factor_transmission | BASE-NEEDED | -- | jobs/km | (0,50) | 3.0 | IRENA employment factors | Line-km intensity; 3.0 x 12,000 km = 36,000 jobs. Planning figure, not extracted from the archive.
employment_factor_wind | BASE-NEEDED | -- | jobs/MW | (0,50) | 4.3 | IRENA employment factors | Same intensity basis; consumed by jobs_from_wind.
equator_principles | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An adoption flag for a lender standard; no row in sources/INDEX.md, so no reference.
fishing_community_load | PRODUCT | fishing_community_load_twh = fishing_community_load * 8760 / 1000000 | TWh/year | (0,30000) | derived | null | Retype to MW, then the graph's own MW x 8760 / 1e6 conversion; 0.0438 TWh/year.
gender_impact | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An assessment artefact; the numeric reading is gender_action_plan_spend_usd_per_year.
grievance_redress_effectiveness | PRODUCT | grievances_resolved_per_year = grievance_redress_effectiveness * grievances_received_per_year | events/year | (0,1e5) | derived | null | Effectiveness applied to received grievances; 0.75 x 1000 = 750.
grievance_redress_mechanism | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A mechanism design (enum); effectiveness already carries the numeric reading.
human_review | GATE-SCENE | -- | 1 | (0,1) | 0.5 | null | Queue-backed review stage: it gates whether an automated decision is released, so it is a switch.
ilo_conventions | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A convention-adoption set; no ILO row in sources/INDEX.md, so no reference.
indigenous_peoples_rights | PRODUCT | indigenous_peoples_rights = fpic_compliance_score | 1 | (0,1) | derived (0.7) | The catalog's own duplicate rows, resolved | Duplicate of fpic_compliance_score; UNDRIP has no index row, so the reference is the alias register.
internet_penetration | PRODUCT | internet_users = internet_penetration * population_total | people | (0,2e8) | derived | null | Penetration share x population; 22.5e6 at defaults.
iso_55000_compliance | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A compliance level, not a quantity; asset_management_maturity is its ordinal form.
just_transition_fund | PRODUCT | just_transition_fund_usd_per_year = just_transition_fund * total_revenue_usd_per_year | USD/year | (0,1e12) | derived | Benefit-sharing programmes (the graph's own revenue identity) | Retype to a share; 0.005 x 6.30e9 = 31.5e6.
licence_conditions | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | Licence text/enum; the numeric sibling is licence_fees.
licence_fees | PRODUCT | licence_fee_spend_usd_per_year = licence_fees * total_capacity_mw | USD/year | (0,1e12) | derived | null | Unit fee already carries USD/MW/year; x 10,000 MW = 5.0e6.
local_content_employment | PRODUCT | local_content_employment = local_employment_share | 1 | (0,0.9) | derived (0.3) | The catalog's own duplicate rows, resolved | Duplicate of local_employment_share; local_jobs already computes the count.
local_employment_targets | PRODUCT | local_employment_targets = local_employment_share | 1 | (0,0.9) | derived (0.3) | Composition-target shares (planning policy) | Duplicate share; its ceiling already exists as local_employment_targets_bound.
maintenance_history | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A record set; failure history already feeds reliability metrics.
maintenance_schedule | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A schedule artefact (MILP output); its hours reading is planned_maintenance_hours_per_year.
maintenance_schedule_optimisation | GATE-SCENE | -- | 1 | (0,1) | 0.5 | null | Selects optimised scheduling over fixed intervals; a mode switch, not a quantity.
mobile_coverage | PRODUCT | mobile_covered_population = mobile_coverage * population_total | people | (0,2e8) | derived | null | Coverage share x population; 40.5e6 at defaults.
occupational_health_safety | PRODUCT | occupational_health_safety_spend_usd_per_year = occupational_health_safety * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | OHS programme spend as a share of ARR; 3.17.
pension_security | PRODUCT | pension_covered_jobs = pension_security * direct_jobs | jobs | (0,1e7) | derived | null | Share of the workforce covered; 34,400 at defaults.
ppa_dispute_resolution | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An arbitration venue (enum); dispute_resolution_mechanism is its general form.
predictive_maintenance_adoption | PRODUCT | predictive_maintenance_hours_per_year = predictive_maintenance_adoption * planned_maintenance_hours_per_year | hours/year | (0,8760) | derived | null | Adoption share moves planned hours into the predictive regime; 48 h/year.
redeployment_options | PRODUCT | redeployed_jobs = redeployment_options * direct_jobs | jobs | (0,1e7) | derived | null | Share of the workforce redeployable; 4,300 at defaults.
reliability_centred_maintenance | GATE-SCENE | -- | 1 | (0,1) | 0.5 | null | Selects RCM as the maintenance regime; a switch over the hours model.
remedy_periods | THRESHOLD | remedy_periods leq max_remedy_period_days | days | (1,365) | 60 | null | Licence remedy window must sit under the ceiling; 60 leq 90 HOLDS at defaults.
resettlement_costs | PRODUCT | resettlement_costs = resettlement_costs_total_usd | USD | (0,1e11) | derived (5.0e8) | The catalog's own duplicate rows, resolved | Duplicate of resettlement_costs_total_usd (exposed_population x share x per-person cost).
retraining_costs | PRODUCT | retraining_spend_usd = retraining_costs * direct_jobs | USD | (0,1e10) | derived | null | Retype to USD/job; 2,000 x 43,000 = 86e6.
ring_fencing_rules | PRODUCT | ring_fenced_provisions = ring_fencing_rules * ring_fencing_provisions | 1 | (0,1000) | derived | null | Rule strength x provision count; 0.5 x 100 = 50.
risk_based_maintenance | GATE-SCENE | -- | 1 | (0,1) | 0.5 | null | Selects risk-ranked maintenance; a switch, not a product.
security_package | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A contractual security instrument (enum); payment_security_required already holds the flag.
skills_gap_assessment | PRODUCT | skills_gap_jobs = skills_gap_assessment * skills_requirements * direct_jobs | jobs | (0,1e7) | derived | null | Gap share of the skilled requirement; 0.3 x 0.3 x 43,000 = 3,870.
skills_requirements | PRODUCT | skills_requirements_jobs = skills_requirements * direct_jobs | jobs | (0,1e7) | derived | null | Share of jobs needing skills certification; 12,900 at defaults.
social_protection_parameters | PRODUCT | socially_protected_jobs = social_protection_parameters * direct_jobs | jobs | (0,1e7) | derived | null | Share of the workforce under social protection; 21,500.
social_representations | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A representation arrangement (enum); no scalar reading.
social_tariff | PRODUCT | social_tariff = lifeline_tariff_usd_per_mwh | USD/MWh | (0,200) | derived (30) | The catalog's own duplicate rows, resolved | Duplicate of lifeline_tariff_usd_per_mwh.
spare_parts_availability | PRODUCT | spare_parts_deferred_hours_per_year = (1 - spare_parts_availability) * planned_maintenance_hours_per_year | hours/year | (0,8760) | derived | null | Stockout converts planned hours into deferred work; 19.2 h/year.
spare_parts_inventory | BASE-NEEDED | -- | USD | (0,1e9) | unknown | null | A stock value, not a count; the 500000.0 signature cannot justify a default.
spare_parts_lead_time | THRESHOLD | spare_parts_lead_time leq 365 / maintenance_frequency | days | (1,365) | 45 | null | A part must arrive before the next service; 45 leq 182.5 HOLDS at defaults.
stakeholder_engagement_plan | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A plan document; its numeric siblings are the spend and grievance nodes.
tariff_transparency | PRODUCT | tariff_transparency_spend_usd_per_year = tariff_transparency * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Transparency programme cost as a share of ARR; 0.634.
unbundling_status | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A policy status enum; the accounting split it implies lives in the regulatory equations.
undrip_compliance | PRODUCT | undrip_compliance = fpic_compliance_score | 1 | (0,1) | derived (0.7) | The catalog's own duplicate rows, resolved | Duplicate of fpic_compliance_score; UNDRIP itself has no row in sources/INDEX.md.
union_agreements | PRODUCT | unionised_jobs = union_agreements * direct_jobs | jobs | (0,1e7) | derived | null | Retype to a coverage share; 0.3 x 43,000 = 12,900.
vulnerability_index | PRODUCT | vulnerable_customers = vulnerability_index * population_total | people | (0,2e8) | derived | null | Vulnerability share x population; 22.5e6 at defaults.
vulnerable_customer_protection | PRODUCT | vulnerable_customer_protection_spend_usd_per_year = vulnerable_customer_protection * allowed_revenue_requirement | USD million/year | (0,20) | derived | null | Protection programme spend as a share of ARR; 1.268.
wage_levels_by_sector | PRODUCT | wage_bill_usd_per_year = wage_levels_by_sector * direct_jobs | USD/year | (0,1e12) | derived | null | Retype to USD/job/year; 20,000 x 43,000 = 860e6 (13.6% of revenue).
women_employment_targets | PRODUCT | women_employment_targets = women_employment_share | 1 | (0,0.6) | derived (0.2) | Composition-target shares (planning policy) | Duplicate share; women_jobs already computes the count.
work_management_systems | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A systems capability set (scheduling/work management), not a quantity.
worker_grievance_mechanism | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | A mechanism design (enum); effectiveness is the numeric sibling.
world_bank_esf | QUALITATIVE | -- | 1 | (0,1e6) | 500000.0 | null | An adoption flag for a framework; no ESF row in sources/INDEX.md, so no reference.
youth_employment_targets | PRODUCT | youth_employment_targets = youth_employment_share | 1 | (0,0.8) | derived (0.3) | Composition-target shares (planning policy) | Duplicate share; youth_jobs already computes the count.
```

Class tally: PRODUCT 40 (10 aliases + 30 consumers), BASE-NEEDED 9, QUALITATIVE 22, GATE-SCENE 5, THRESHOLD 2.

**NEW BASES NEEDED**

1. `planned_capacity_{solar,wind,hydro,gas,coal,biomass,geothermal}_mw` — MW, exogenous. Defaults 10000, 2000, 1500, 1500, 3000, 100, 800 (copied from the current endogenous `solar_pv_capacity`, `wind_onshore_capacity`, `hydro_capacity`, `gas_capacity`, `coal_capacity`, `biomass_capacity`, `geothermal_capacity`). Derivation: the employment factors must not read the endogenous capacity nodes (equality to an endogenous lhs is forbidden); the planning capacity is the exogenous quantity they multiply. **Hazard:** summing `jobs_from_<tech>` against the existing `direct_jobs` double-counts — 4.3 jobs/MW over 19,900 MW is 85,570 against `direct_jobs` = 43,000. The batch must either retire `construction_jobs_per_mw`/`om_jobs_per_mw` or keep the per-tech split as a diagnostic only.
2. `grievances_received_per_year` — events/year, default 1000. Derivation: 43,000 direct jobs at ~1 grievance per 40 job-years gives ~1,000/year; the events/year dimension is what makes `grievance_redress_effectiveness * received` dimensionally equal to `events/year` (verified).
3. `ring_fencing_provisions` — dimensionless count, default 100. Derivation: the number of provisions a ring-fencing rule can bind; `ring_fencing_rules` is the [0,1] strength.
4. `max_remedy_period_days` — days, default 90. Derivation: the licence ceiling that `remedy_periods` (default 60) must not exceed; without it the remedy bound has no rhs.
5. `spare_parts_inventory` retype to USD, **default unknown** — the 500000.0 signature is not a stock value. Its consumer is `spare_parts_carrying_cost_usd_per_year = spare_parts_inventory * discount_rate` (USD x 1/year = USD/year).

Retypes required by the PRODUCT rows (unit, default): `employment_factor_*` jobs/MW 4.3 (transmission jobs/km 3.0); `coal_community_dependencies` 1 / 0.05; `fishing_community_load` MW / 5.0; `wage_levels_by_sector` USD/job/year / 20000; `retraining_costs` USD/job / 2000; `just_transition_fund` 1 / 0.005; `community_transition_funding` 1 / 0.1; `consumer_education` 1 / 0.001; `complaint_handling` 1 / 0.002; `tariff_transparency` 1 / 0.001; `cross_subsidy_transparency` 1 / 0.0005; `vulnerable_customer_protection` 1 / 0.002; `occupational_health_safety` 1 / 0.005; `community_health_safety` 1 / 0.002; `skills_requirements` 1 / 0.3; `skills_gap_assessment` 1 / 0.3; `early_retirement_packages` 1 / 0.02; `pension_security` 1 / 0.8; `redeployment_options` 1 / 0.1; `social_protection_parameters` 1 / 0.5; `child_labour_prohibition` 1 / 1.0; `union_agreements` 1 / 0.3; `spare_parts_lead_time` days / 45.

**PROPOSED BATCHES**

- **A. Employment intensity and the technology split (23 nodes).** 8 `employment_factor_*` retypes + 7 `planned_capacity_*_mw` bases + 8 `jobs_from_<tech> = employment_factor_<tech> * planned_capacity_<tech>_mw` (transmission: `* transmission_line_length_km`, 36,000 jobs). Method: intensity x exogenous capacity, the same idiom as the shipped `direct_jobs_definition`. Reference `IRENA employment factors`. Carries the double-count hazard above.
- **B. Just-transition job shares (16).** 8 slice shares x `direct_jobs` (skills 12,900; gap 3,870; early retirement 860; pension 34,400; redeployment 4,300; social protection 21,500; child labour 43,000; union 12,900). Method: share x the graph's own job base. Reference null except the composition targets.
- **C. Consumer-protection and OHS programme spend (14).** 7 shares x `allowed_revenue_requirement` (0.634–3.17 USD million/year). Method: the shipped `consumer_protection_spend_definition` pattern, unchanged. Below the 15-node floor only because the slice holds seven such rows.
- **D. Community funds, wages and retraining (6).** `just_transition_fund` and `community_transition_funding` as shares of revenue and of the community fund; `wage_levels_by_sector` and `retraining_costs` as rates over `direct_jobs`; plus the two alias rows `community_benefit_sharing`, `community_development_funds`. Method: share/rate x an existing aggregate. Reference `Benefit-sharing programmes`.
- **E. Coverage and population (5).** `internet_penetration`, `mobile_coverage`, `vulnerability_index`, `coal_community_dependencies` x `population_total`/`exposed_population`, plus `fishing_community_load` -> TWh/year. Method: share x population, and the graph's own MW x 8760 / 1e6 conversion.
- **F. Asset and maintenance availability (10).** `(1 - availability) * planned_maintenance_hours_per_year` for crew (14.4 h) and spares (19.2 h); `predictive_maintenance_adoption * planned hours` (48 h); `ring_fencing_rules * ring_fencing_provisions` (50); the two thresholds (`remedy_periods` is in batch H); `spare_parts_inventory` carrying cost; and the five scene switches (`condition_based`, `reliability_centred`, `risk_based`, `maintenance_schedule_optimisation`, `human_review`). Method: availability shortfall and regime selection.
- **G. Alias register (10).** The ten equality rows: `community_benefit_sharing`, `community_development_funds`, `local_content_employment`, `local_employment_targets`, `women_employment_targets`, `youth_employment_targets`, `undrip_compliance`, `indigenous_peoples_rights`, `resettlement_costs`, `social_tariff`. Method: equality to the canonical twin; reference `The catalog's own duplicate rows, resolved`. Do not cite UNDRIP, IFC, Equator or ILO for these — none resolves in `sources/INDEX.md` (checked with `read_index()`).
- **H. Grievance, remedy, licence and load (5).** `grievances_resolved_per_year` (750), `remedy_periods leq max_remedy_period_days` (60 leq 90 HOLDS), `licence_fee_spend_usd_per_year` (5.0e6), `spare_parts_lead_time leq 365 / maintenance_frequency` (45 leq 182.5 HOLDS), and `human_review` if it is kept out of F.

The 22 QUALITATIVE rows need no batch: they are document/enum rows whose numeric readings already exist under other names, and the honest fix is to leave them free rather than manufacture an equation.

# SLICE grid-ops

```
NODE | CLASS | lhs = rhs (or --) | unit | range | default | reference | one-sentence reason
ac_voltage_limit | BASE-NEEDED | ac_voltage_limit_pu = ac_voltage_limit_kv / nominal_voltage_kv | 1 (pu) | (0, 2) | unknown | null | A voltage ceiling needs the bus voltage it ceilings and the graph carries no kV node (no nominal_voltage_kv, no bus_voltage_kv); base nominal_voltage_kv, kV, default 220 (the low end of capex_transmission's own 220-765 kV prose).
ami_infrastructure | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An AMI maturity indicator; the admissible set is a programme choice, not a measurement, so no equation can fix it.
asset_age_distribution | QUALITATIVE | -- | years (vector) | -- | unknown | null | A distribution, not a scalar; typed float it cannot hold the object its name denotes and no single equation can express one.
auction_frequency | SCENE-SWITCH | -- | 1/year | (0, 365) | unknown | null | Selects the market-clearing cadence (annual/monthly/day-ahead auction); the graph models no auction sequence, so no equation should carry it.
aviation_fuel_demand | BASE-NEEDED | synthetic_aviation_fuel_pj = synthetic_fuel_share_aviation * aviation_fuel_demand | PJ/year | (0, 5000) | unknown | null | It is itself the missing extensive base for the synthetic-fuel share; retype to PJ/year, default unknown, and the share forms the product.
baseline_emissions | BASE-NEEDED | abatement_fraction = (baseline_emissions - emissions_mtco2_per_year) / baseline_emissions | 1 | (0, 1) | unknown | null | The carbon trajectory has no baseline to abate from; retype to MtCO2, and the ratio against the derived annual emissions is the only product it forms.
battery_storage_adoption | BASE-NEEDED | household_batteries = battery_storage_adoption * households_total | 1 | (0, 1) | 0.05 | null | A share of households and the graph carries no household count; base households_total = population_total / 5 = 9,000,000 (the same five-persons-per-household derivation batch 22 used for population_total).
biogas_capacity | THRESHOLD | biogas_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | A member of the fleet build balance; at the placeholder 500000.0 the bound FAILS against 15000.0, so the coupling is the retype to MW (default 0, as the 13 unbuilt siblings already carry) and then the balance membership.
biomass_sustainability_limit | THRESHOLD | biomass_capacity leq biomass_sustainability_limit | MW | (0, 30000) | unknown | null | A ceiling on the biomass build: lhs is 100.0 MW at defaults and the bound holds for any limit at or above it.
black_start_capability | BASE-NEEDED | black_start_units = black_start_requirement * number_of_generators | 1 | (0, 1000) | unknown | null | The share exists (black_start_requirement 0.02) but the generator count it multiplies is a placeholder; retype to a count and the product is the black-start unit set.
capex_distribution | PRODUCT | distribution_capex_usd = capex_distribution * total_capacity_mw * 1000.0 | USD | (100, 1500) | 400.0 | null | Installed distribution cost scales with served kW; at defaults 400 x 10000 x 1000 = 4.0e9 USD (the checker leaves the unit as USD*megawatt/kilowatt, which reduces to USD).
capex_gas_ccgt | PRODUCT | lcoe_gas_ccgt_usd_per_mwh = (capex_gas_ccgt * crf_gas + opex_fixed_gas) * 1000 / (8760 * capacity_factor_gas) + opex_variable_gas + fuel_cost_gas + emission_factor_gas_t_per_mwh * carbon_price_usd_per_tco2 | USD/MWh | (500, 2000) | 1100.0 | IEA/NEA Projected Costs of Generating Electricity | The CCGT is a distinct capital cost the shipped gas LCOE does not read; 85.51 USD/MWh at defaults, and unit_of cannot decide it because the 1000 and 8760 constants carry the kW->MW and year->h conversions (USD/kW/year is what it returns -- undecidable, not a pass).
capex_gas_ocgt | PRODUCT | lcoe_gas_ocgt_usd_per_mwh = (capex_gas_ocgt * crf_gas + opex_fixed_gas) * 1000 / (8760 * capacity_factor_gas) + opex_variable_gas + fuel_cost_gas + emission_factor_gas_t_per_mwh * carbon_price_usd_per_tco2 | USD/MWh | (300, 1200) | 650.0 | IEA/NEA Projected Costs of Generating Electricity | The peaker's lower capex and lower efficiency are the trade the graph says it carries and does not; 77.02 USD/MWh at defaults, same undecidable unit as the CCGT line.
capex_gravity_storage | BASE-NEEDED | gravity_storage_capex_usd = capex_gravity_storage * gravity_storage_energy_mwh | USD | (200, 2000) | 800.0 | null | USD/kWh needs MWh of energy capacity and gravity_storage_capacity is a placeholder in MW; base gravity_storage_energy_mwh, MWh, default unknown (a 100 MW / 8 h pilot is 800 MWh).
capex_marine_otec | BASE-NEEDED | marine_otec_capex_usd = capex_marine_otec * marine_otec_capacity * 1000.0 | USD | (5000, 25000) | 12000.0 | null | USD/kW needs an MW base and marine_otec_capacity is a placeholder; base the capacity node retyped to MW, default 0 (no commercial OTEC plant, as its own description says).
capex_marine_tidal | BASE-NEEDED | marine_tidal_capex_usd = capex_marine_tidal * marine_tidal_capacity * 1000.0 | USD | (2500, 15000) | 7000.0 | null | Same shape: the rate needs tidal MW and the capacity node carries the placeholder signature.
capex_transmission | BASE-NEEDED | transmission_capex_usd = capex_transmission * transmission_route_mw_km | USD | (50, 5000) | 400.0 | Oree et al. (2017), RSER 69:790-803 | USD per MW-km needs route MW-km and the graph carries km of distribution only; base transmission_route_mw_km, MW-km, default 10000 x 500 = 5e6 MW-km (the 10 GW fleet over a 500 km corridor).
circuit_breakers | BASE-NEEDED | breaker_density_per_km = circuit_breakers / distribution_network_km | 1/km | (0, 1e6) | unknown | null | A count with no unit; retype to a count and it forms the breaker density against the 45000 km the graph carries.
clustering_method | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the spatial clustering algorithm; the graph models no clustering, so no equation should carry it.
coal_community_dependencies | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A just-transition dependency index; its admissible set is a policy classification, not a measurement.
coal_new_build | THRESHOLD | coal_capacity leq coal_new_build | MW | (0, 1e6) | unknown | null | A policy ceiling on the coal build: lhs is 3000.0 MW at the reference build and the bound holds for any cap at or above it.
coal_retirement_schedule | QUALITATIVE | -- | years (vector) | -- | unknown | null | A per-unit retirement schedule is a vector; the graph already carries the rate (coal_retirement_rate) and its half-life (23.10 years), which is the scalar form of the same fact.
cold_snap_frequency | QUALITATIVE | -- | events/year | (0, 100) | unknown | null | A climate-scenario frequency; the scenario's own distribution sets it, not an equation.
cold_storage_load | BASE-NEEDED | -- | MWh/year | (0, 1e6) | unknown | null | A cold-chain energy demand the graph carries no base for and no share reaches; retype and leave as a scenario input.
compressed_air_capacity | THRESHOLD | compressed_air_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance; the placeholder 500000.0 fails against 15000.0, so retype to MW at 0 first, then the membership holds.
contingency | PRODUCT | contingency_allowance_usd = contingency * capex_usd_per_kw * total_capacity_mw * 1000.0 | 1 | (0, 1) | unknown | null | A capex contingency share; the default 500000.0 is not a share and must be retyped, after which the allowance at 0.10 is 1.2e9 USD.
cross_border_permitting_time | BASE-NEEDED | cross_border_lead_time_years = cross_border_permitting_time + construction_period / 12 | years | (0, 20) | unknown | null | A duration with no unit; retype to years and it forms the cross-border project lead time against the 30-month construction period.
cross_border_tension | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A geopolitical index; the admissible set is an analyst's classification.
cross_border_trade_allowed | GATE-PRODUCT | permitted_imports_twh = cross_border_trade_allowed * net_imports_twh | TWh | -- | 1.0 | null | A boolean with a quantity base the graph carries: it gates the net-import flow (0.0 TWh at defaults, so the product is zero either way -- the gate is live but the base is empty).
cross_border_trading | PRODUCT | cross_border_trading eq cross_border_trade_allowed | 1 | (0, 1) | 1.0 | The fragments' alias register (docs/param_batch7.md and successors), applied | Its own description says DEPRECATED duplicate of the boolean; the alias is the coupling.
csp_storage_hours | PRODUCT | csp_storage_energy_mwh = csp_storage_hours * csp_capacity | MWh | (0, 100) | 24.0 | null | Thermal storage hours times the CSP build; unit_of returns hour*megawatt (MWh) and the value is 0.0 at the zero CSP build.
custom_gis_boundary | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the study boundary the spatial model uses; a run configuration, not a quantity.
cvar_alpha | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | The tail level a risk-averse objective is evaluated at; a chosen confidence, not a measurement.
cvar_omega | QUALITATIVE | -- | 1 | (0, 10) | unknown | null | The risk-aversion weight; a preference parameter whose admissible set is a modelling choice.
degradation_model | QUALITATIVE | -- | categorical | -- | unknown | null | Selects a degradation curve family; the graph carries the rates (solar_degradation, wind_degradation) and no curve library.
demand_response_capacity | PRODUCT | demand_response_capacity eq demand_response_potential * peak_demand_mw | MW | (0, 1e6) | unknown | null | The flexible share times peak demand; the placeholder default makes 4.25e9 MW, so the retype of demand_response_potential to a share is the precondition, and at 0.15 the product is 1275.0 MW.
demand_response_potential | PRODUCT | demand_response_capacity eq demand_response_potential * peak_demand_mw | 1 | (0, 1) | unknown | null | The share in that same equation: a share of peak demand, the base the graph already carries.
der_management_systems | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A DERMS capability indicator; a programme maturity, not a measurement.
dispatch_interval | PRODUCT | dispatch_intervals_per_hour = 1 / dispatch_interval | 1/hour | (0.05, 24) | unknown | null | Retype to hours and it is the settlement/dispatch cadence; unit_of returns None on the bare 1, so the reciprocal is numerically 2/h at 0.5 h and dimensionally undecidable.
distribution_capex_per_connection | BASE-NEEDED | distribution_connection_capex_usd = distribution_capex_per_connection * new_connections_per_year | USD | (100, 4000) | 600.0 | null | USD per connection needs connections and the graph carries no connection count; base new_connections_per_year, connections/year, default 200000 (a 45 M population at 2% electrification growth is ~900k people, five per connection).
distribution_conditions | QUALITATIVE | -- | categorical | -- | unknown | null | A condition class for the distribution network; an admissible-set choice.
distribution_detail | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects how finely the distribution network is represented; a run configuration.
distribution_loss_factor | PRODUCT | distribution_losses_twh = distribution_loss_factor * demand_twh | TWh | (0, 1) | unknown | null | Distribution losses as a share of delivered demand; 23.27 TWh at the placeholder 0.5, which is absurd for losses, so the retype is the precondition and a 0.05 share gives 2.33 TWh.
distribution_network_km | PRODUCT | distribution_network_density_km_per_mw = distribution_network_km / total_capacity_mw | km/MW | (0, 200000) | 45000.0 | null | The density its own description asserts (4-5 km per MW); 4.5 at defaults.
distribution_wheeling_charges | BASE-NEEDED | distribution_wheeling_usd = distribution_wheeling_charges * demand_twh * 1000000.0 | USD/MWh | (0, 100) | unknown | null | A unit charge with no unit typed; retype to USD/MWh and it multiplies the delivered energy the graph carries.
employment_factor_transmission | BASE-NEEDED | transmission_jobs = employment_factor_transmission * transmission_route_km | jobs/km | (0, 20) | unknown | null | A jobs-per-km factor with no route length to multiply; base transmission_route_km, km, default 500 (the corridor in the capex_transmission base).
failure_history | QUALITATIVE | -- | events (vector) | -- | unknown | null | An event record, not a scalar; the graph carries the derived rates (forced_outage_rate, availability) that summarise it.
failure_rate_curve | QUALITATIVE | -- | 1 | (0, 3) | 1.0 | null | Its own description: a shape selector (0 exponential, 1 bathtub, 2 wear-out), not the curve, which is a function and cannot be a scalar.
financial_transmission_rights | QUALITATIVE | -- | categorical | -- | unknown | null | An FTR market design; the graph models no congestion-revenue allocation.
flywheel_capacity | THRESHOLD | flywheel_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0; the placeholder fails the bound.
forced_outage_rate_coal | PRODUCT | coal_unavailable_hours_per_year = forced_outage_rate_coal * 8760 | hours/year | (0, 0.4) | 0.1 | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck | A forced-outage share of the year: 876 h/year at defaults; unit_of returns dimensionless because 8760 is a bare constant, so the unit is undecidable from the expression.
foreign_exchange_reserves | BASE-NEEDED | -- | USD | (0, 1e12) | unknown | null | A macro stock with no reader; retype to USD, and any import-cover ratio it forms divides by a net-import bill that is 0.0 TWh at defaults.
foresight | QUALITATIVE | -- | categorical | -- | unknown | null | Perfect versus myopic foresight is a modelling choice, not a measurement.
fossil_fuel_subsidies | BASE-NEEDED | fossil_subsidy_usd_per_mwh = fossil_fuel_subsidies / generation_twh | USD/year | (0, 1e11) | unknown | null | An annual fiscal flow the graph carries no unit for; retype to USD/year and it forms a per-MWh subsidy against the 52.05 TWh generated at defaults.
fuel_cost_hydrogen | PRODUCT | fuel_cost_hydrogen eq hydrogen_price_per_mwh | USD/MWh | (50, 400) | 120.0 | null | The derived hydrogen price (3.0 USD/kg / 0.03333 MWh/kg = 90.0 USD/MWh) already exists; the two spellings differ by 30 USD/MWh and the alias resolves which is canonical.
fuel_price_scenario | QUALITATIVE | -- | categorical | -- | unknown | null | An enumerated price path; the graph carries the price nodes it selects among.
fuel_price_volatility | PRODUCT | fuel_price_upper_usd_per_mwh = fuel_price_usd_per_mwh * (1 + fuel_price_volatility) | 1 | (0, 1) | unknown | null | A volatility share; the placeholder 500000.0 must be retyped, after which the band's upper edge is 44.0 USD/MWh at a 0.10 volatility.
fusion_capacity | THRESHOLD | fusion_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
gas_new_build | THRESHOLD | gas_capacity leq gas_new_build | MW | (0, 1e6) | unknown | null | A policy ceiling on gas build: lhs is 1500.0 MW at the reference build and the bound holds for any cap at or above it.
gender_impact | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A gender-dimension score; an assessment, not a measurement.
geothermal_drilling_success | PRODUCT | geothermal_effective_capex_usd_per_kw = capex_geothermal / geothermal_drilling_success | 1 | (0, 1) | unknown | null | A dry-hole rate raises the effective cost of a successful well; unit_of returns None (the share has no unit) so the division is undecidable as written, and at 0.6 the effective capex is 6667 USD/kW.
gravity_storage_capacity | THRESHOLD | gravity_storage_capacity leq total_capacity_mw + storage_headroom_mw | MWh | (0, 1000) | unknown | null | A storage build member; retype to MWh at 0 before the balance membership holds.
grid_reliability_saifi | PRODUCT | grid_reliability_saifi eq service_quality_standards | events/year | (0, 100) | 15.0 | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck | The shipped saifi_ceiling_bound already bounds SAIFI by service_quality_standards; this node is a second spelling of the same target and the alias is the coupling.
heatwave_frequency | QUALITATIVE | -- | events/year | (0, 100) | unknown | null | A climate-scenario frequency; the scenario sets it.
hydro_capacity_factor | PRODUCT | hydro_capacity_factor eq capacity_factor_hydro | 1 | (0, 1) | 0.55 | null | A duplicate of capacity_factor_hydro, which lcoe_hydro already reads; the alias keeps one spelling.
hydro_drought_multiplier | PRODUCT | hydro_effective_capacity_factor = hydro_capacity_factor * hydro_drought_multiplier | 1 | (0, 1) | 0.5 | null | The drought-adjusted hydro output share: 0.25 at defaults, and unit_of returns dimensionless as expected.
hydro_new_build | THRESHOLD | hydro_capacity leq hydro_new_build | MW | (0, 1e6) | unknown | null | A policy ceiling on hydro build: lhs is 1500.0 MW at the reference build.
hydro_reservoir_level | BASE-NEEDED | hydro_stored_energy_mwh = hydro_reservoir_level * hydro_reservoir_energy_mwh | 1 | (0, 1) | unknown | null | An initial state as a share of full supply; the graph carries no reservoir energy capacity, so the base is hydro_reservoir_energy_mwh (MWh, default 1500 MW x 0.55 x 8760 x 0.5 = 3.6e6 MWh at half a year of storage).
hydrogen_fuel_cell_capacity | THRESHOLD | hydrogen_fuel_cell_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
hydrogen_pipeline_capacity | BASE-NEEDED | -- | MW | (0, 5000) | unknown | null | The pipeline's transfer capacity is itself the base the pipeline cost needs; retype to MW, default 0 (no hydrogen network built).
hydrogen_pipeline_cost | BASE-NEEDED | hydrogen_pipeline_capex_usd = hydrogen_pipeline_cost * hydrogen_pipeline_capacity * hydrogen_pipeline_route_km | USD/MW-km | (10, 500) | 120.0 | null | The rate needs both a capacity and a route length; the capacity is a placeholder and the length does not exist, so 120 x 500 MW x 100 km = 6.0e6 USD is the product once both bases are typed.
hydrogen_storage_capacity | THRESHOLD | hydrogen_storage_capacity leq storage_headroom_mw * storage_duration_curve | MWh | (0, 1e7) | 0.0 | null | An endogenous storage build; a leq is the only form an endogenous node may appear in, and 0.0 sits far under the headroom.
hydrogen_storage_cost | BASE-NEEDED | -- | USD/kWh | (1, 100) | 15.0 | null | Its base is the MWh built, and hydrogen_storage_capacity is endogenous, so the capex product cannot be an equality at all -- it belongs in the LP's objective or a leq, not an equation.
hydrogen_storage_type | QUALITATIVE | -- | categorical | -- | unknown | null | An enumerated storage technology (salt cavern, above-ground); an admissible-set choice.
insider_trading_rules | QUALITATIVE | -- | categorical | -- | unknown | null | A market-conduct regime; a legal class, not a quantity.
interannual_variability | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A scenario switch over climate years; the choice of year set is the content.
investment_periods | PRODUCT | investment_period_length_years = time_horizon / investment_periods | 1 | (1, 20) | unknown | null | The count of investment periods; retype to a count and it divides the horizon the graph carries.
islanding_capability | PRODUCT | islanding_capable_feeders = islanding_capability * distribution_feeders_total | 1 | (0, 1) | unknown | null | A share of the 500 primary feeders; the placeholder 500000.0 is not a share, and at 0.10 the product is 50 feeders.
landfill_gas_capacity | THRESHOLD | landfill_gas_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
lifeline_threshold | BASE-NEEDED | lifeline_eligible_households = lifeline_share * households_total | kWh/month | (0, 500) | unknown | null | A consumption threshold whose base (households, and the share below it) the graph does not carry; base households_total = 9,000,000.
line_outage_end | PRODUCT | line_outage_window_hours = line_outage_end - line_outage_start | hours | (0, 8760) | unknown | null | The outage window is the difference of its two endpoints; both must be retyped to hours of the year first.
line_outage_start | PRODUCT | line_outage_window_hours = line_outage_end - line_outage_start | hours | (0, 8760) | unknown | null | The other endpoint of the same equation.
line_upgrade_budget | BASE-NEEDED | -- | USD | (0, 1e10) | unknown | null | A capital envelope with no unit and no reader; retype to USD, and it is the base transmission_expansion_allowed gates.
load_factor_override | PRODUCT | load_factor_override eq load_factor | 1 | (0.3, 0.9) | unknown | null | An override of the derived load factor (0.6469 at defaults); the alias records that it replaces rather than adds.
load_shifting_capability | PRODUCT | load_shifting_energy_mwh = load_shifting_capability * interruptible_load_mw | hours | (0, 24) | unknown | null | Hours of shifting times the interruptible MW; unit_of returns None because the node has no unit, and the placeholder 500000.0 makes 2.1e9 MWh, so the retype to hours is the precondition.
marine_otec_capacity | THRESHOLD | marine_otec_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
marine_tidal_capacity | THRESHOLD | marine_tidal_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
marine_wave_capacity | THRESHOLD | marine_wave_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
min_down_time_coal | SCENE-SWITCH | -- | hours | (0, 72) | unknown | null | Parameterises the unit-commitment mode the parameter graph does not model; no equation can read it until that mode exists.
min_stable_level_coal | SCENE-SWITCH | -- | 1 | (0, 1) | unknown | null | The minimum stable load fraction belongs to the UC formulation, which the graph does not carry.
min_stable_level_gas | SCENE-SWITCH | -- | 1 | (0, 1) | unknown | null | Same UC formulation gap for gas.
min_up_time_coal | SCENE-SWITCH | -- | hours | (0, 72) | unknown | null | Same UC formulation gap.
near_duplicate_detection | QUALITATIVE | -- | categorical | -- | unknown | null | A deduplication method selector for the parameter set itself; a tool setting, not a quantity.
non_spinning_reserve | PRODUCT | non_spinning_reserve eq non_spinning_reserve_requirement | MW | (0, 3000) | 400.0 | null | A duplicate spelling of the typed MW requirement the shipped bound already reads; the alias is the coupling.
nuclear_lead_time | BASE-NEEDED | nuclear_lead_time_years = nuclear_lead_time + construction_period / 12 | years | (0, 25) | unknown | null | A duration with no unit; retype to years and it forms the nuclear project lead time against the 30-month construction period.
nuclear_new_build | THRESHOLD | nuclear_capacity leq nuclear_new_build | MW | (0, 1e6) | unknown | null | A policy ceiling on nuclear build: lhs is 0.0 MW at the reference build.
number_of_generators | BASE-NEEDED | -- | 1 | (0, 1000) | unknown | null | The generator count is itself a missing base; retype to a count, default 220 (the scada_telemetry_sites count batch 22 derived for generation sites plus bulk supply points).
opex_fixed_wind_onshore | PRODUCT | annualised_capex_usd_per_kw_wind + opex_fixed_wind_onshore | USD/kW/year | (0, 400) | 30.0 | NREL ATB 2025 Equations & Variables | The wind LCOE reads opex_fixed_wind (40.0) instead of the onshore-specific 30.0 the coupler deliberately left free; repairing lcoe_wind_definition is the coupling.
outage_cause_distribution | PRODUCT | weather_related_interruptions_per_year = outage_cause_distribution * system_saifi_events_per_year | events/year | (0, 1) | 0.35 | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck | The weather share of the 12 interruptions/year; 4.2 events/year at defaults and unit_of returns events/year.
outage_coordination | GATE-PRODUCT | coordinated_maintenance_hours_per_year = outage_coordination * planned_maintenance_hours_per_year | hours/year | -- | 1.0 | null | A boolean multiplying a quantity base the graph carries: 192 h/year at defaults, and 0 when coordination is off.
outage_management_systems | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An OMS capability indicator; a programme maturity.
parameter_overrides | QUALITATIVE | -- | categorical | -- | unknown | null | A scenario override list; it is the run's input, not an object the run computes.
peak_demand_multiplier | PRODUCT | peak_demand_scaled_mw = (1 + peak_demand_multiplier) * peak_demand_mw | 1 | (0, 1) | unknown | null | A scaling factor on peak demand: the shipped 0.5 is a midpoint of an unknown range and the honest form is 1 + the multiplier, giving 12750 MW at 0.5.
planning_reserve_margin | PRODUCT | planning_reserve_margin eq reserve_margin_min | 1 | (0, 1) | 0.15 | Standard N-1 planning criterion | A duplicate spelling of the shipped 0.15 margin the reserve equations already read.
plant_retirement_age | PRODUCT | plant_retirement_age eq asset_life | years | (5, 60) | 25.0 | null | The retirement age is the asset life the graph already carries (25.0 years), and remaining_useful_life reads it.
probability_weight | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | A scenario weight; the constraint it must satisfy (weights summing to one) is over the scenario set, which no single equation can state.
ramp_rate_coal | SCENE-SWITCH | -- | MW/min | (0, 100) | unknown | null | A UC parameter for a dispatch mode the graph does not model.
ramp_rate_gas | SCENE-SWITCH | -- | MW/min | (0, 200) | unknown | null | Same UC formulation gap.
regulation_down_requirement | PRODUCT | regulation_down_requirement = regulation_down_share * regulation_reserve | MW | (0, 3000) | unknown | null | A slice of the operating reserve; needs regulation_down_share (1, default 0.5) and the regulation_reserve product below, giving 85.0 MW.
regulation_reserve | BASE-NEEDED | regulation_reserve = regulation_reserve_share * peak_demand_mw | MW | (0, 3000) | unknown | null | The reserve band is a share of peak demand and the share is not a node; base regulation_reserve_share, 1, default 0.02 (the 1-2% band a primary-frequency reserve is sized at), giving 170.0 MW.
regulation_up_requirement | PRODUCT | regulation_up_requirement = regulation_up_share * regulation_reserve | MW | (0, 3000) | unknown | null | A slice of the operating reserve; needs regulation_up_share (1, default 0.5), giving 85.0 MW.
reliability_centred_maintenance | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An RCM programme indicator; a maintenance-strategy choice.
representative_days | PRODUCT | representative_hours = representative_days * 24 | hours | (0, 100) | 50.0 | null | The sampled days times 24; unit_of returns day because the 24 carries no unit, so the checker cannot see the hour and the numeric value is 1200 h.
reserve_accounts | BASE-NEEDED | reserve_account_balance_usd = reserve_account_share * regulatory_asset_base | USD million | (0, 50000) | unknown | null | A balance-sheet stock whose base is the regulatory asset base the graph carries; base reserve_account_share, 1, default 0.02 (a two-percent reserve account is the common licence condition).
reserve_margin | PRODUCT | reserve_margin eq reserve_margin_min | 1 | (0, 1) | 0.15 | Standard N-1 planning criterion | A duplicate of the 0.15 margin; note the id collides with the shipped equation `reserve_margin`, so the alias needs a distinct id.
rolling_horizon_window | SCENE-SWITCH | -- | hours | (0, 8760) | unknown | null | Selects the dispatch look-ahead length; a run configuration.
scenario_description | QUALITATIVE | -- | text | -- | unknown | null | Scenario metadata.
scenario_owner | QUALITATIVE | -- | text | -- | unknown | null | Scenario metadata.
scenario_tag | QUALITATIVE | -- | text | -- | unknown | null | Scenario metadata.
scenario_template | QUALITATIVE | -- | categorical | -- | unknown | null | Selects a scenario template; a run configuration.
scenario_visibility | QUALITATIVE | -- | categorical | -- | unknown | null | An access-control setting on the scenario; not a physical quantity.
security_constrained_dispatch | SCENE-SWITCH | -- | bool | -- | 1.0 | null | Selects whether the dispatch respects network limits -- a mode the parameter graph does not model, named as a scene switch by the worklist.
shipping_fuel_demand | BASE-NEEDED | synthetic_shipping_fuel_pj = synthetic_fuel_share_shipping * shipping_fuel_demand | PJ/year | (0, 5000) | unknown | null | The missing extensive base for the shipping synthetic-fuel share; retype to PJ/year, default unknown.
signal_extraction | QUALITATIVE | -- | categorical | -- | unknown | null | A signal-extraction method selector.
signal_scoring | QUALITATIVE | -- | categorical | -- | unknown | null | A scoring method selector.
small_modular_reactor_capacity | THRESHOLD | small_modular_reactor_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
smart_metering_penetration | PRODUCT | smart_metered_population = smart_metering_penetration * electrified_population | 1 | (0, 1) | 0.5 | null | The metered share of the 40.5 M electrified population; 20,250,000 people at defaults, unit_of returns people.
smart_metering_rollout | GATE-PRODUCT | smart_metered_population = smart_metering_rollout * smart_metering_penetration * electrified_population | bool | -- | 1.0 | null | A programme switch multiplying the metered-population base; off, the same base goes to zero.
snapshot_weightings | QUALITATIVE | -- | 1 (vector) | -- | unknown | null | A per-snapshot weight vector; typed float it cannot hold the object, and its normalisation is over the snapshot set.
soil_contamination | QUALITATIVE | -- | categorical | -- | unknown | null | A contamination descriptor with no unit; a site classification.
soil_contamination_index | QUALITATIVE | -- | 1 | (0, 1) | 0.1 | null | A composite index; its construction is the measurement and the graph carries no soil data to build it from.
solar_irradiance_multiplier | PRODUCT | solar_effective_capacity_factor = solar_pv_capacity_factor * solar_irradiance_multiplier | 1 | (0, 1) | 0.5 | null | An irradiance scenario multiplier on the 0.22 PV capacity factor; 0.11 at defaults, dimensionless as expected.
solar_pv_land_constraint | THRESHOLD | solar_pv_capacity leq solar_pv_land_constraint | MW | (0, 1e6) | unknown | null | A land ceiling on the PV build: lhs is 10000.0 MW at the reference build.
solar_pv_learning_rate | PRODUCT | capex_solar_pv_learning_usd_per_kw = capex_solar_pv * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - solar_pv_learning_rate) / log(2)) | USD/kW | (0, 0.4) | 0.2 | Wright's law; IRENA renewable cost statistics | Wright's law with the PV-specific rate, exactly the form the shipped learning_curve uses with the generic 0.18; 880.0 USD/kW at defaults and unit_of returns USD/kilowatt.
solar_pv_max_build | THRESHOLD | solar_pv_capacity leq solar_pv_max_build | MW | (0, 1e6) | unknown | null | An annual build ceiling: lhs is 10000.0 MW at the reference build.
solar_thermal_capacity | THRESHOLD | solar_thermal_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
spare_capacity | PRODUCT | spare_capacity = total_capacity_mw - peak_demand_mw | MW | (0, 1e6) | unknown | null | Installed capacity less peak demand: 1500.0 MW at defaults and unit_of returns megawatt.
spatial_clustering | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the spatial clustering; a run configuration.
spatial_resolution | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the spatial grid the model resolves; a run configuration.
spinning_reserve | PRODUCT | spinning_reserve eq spinning_reserve_requirement | MW | (0, 3000) | unknown | null | A duplicate spelling of the requirement; the alias is the coupling.
spinning_reserve_requirement | PRODUCT | spinning_reserve_requirement = spinning_reserve_share * peak_demand_mw | MW | (0, 3000) | unknown | null | Needs the share base spinning_reserve_share (1, default 0.03 -- the three-percent spinning band the operating reserve is sized at), giving 255.0 MW.
ssp_pathway | QUALITATIVE | -- | categorical | -- | unknown | null | An enumerated socioeconomic pathway; the admissible set is the scenario's.
stakeholder_engagement_plan | QUALITATIVE | -- | 1 | (0, 1) | unknown | null | An engagement-programme indicator.
startup_cost_coal | BASE-NEEDED | coal_startup_cost_usd_per_year = startup_cost_coal * coal_starts_per_year | USD/start | (0, 1e6) | unknown | null | A per-start cost needs a starts count the graph does not carry; base coal_starts_per_year, starts/year, default 60 (a 3000 MW coal fleet cycling roughly weekly).
startup_cost_gas | BASE-NEEDED | gas_startup_cost_usd_per_year = startup_cost_gas * gas_starts_per_year | USD/start | (0, 1e6) | unknown | null | Same missing base for the 1500 MW gas fleet; default 200 starts/year (daily cycling of half the fleet).
stochastic_scenarios | QUALITATIVE | -- | 1 | (0, 100) | unknown | null | A count of the scenario tree's leaves; the tree's construction is a modelling choice.
storage_capacity_mw | THRESHOLD | storage_capacity_mw leq total_capacity_mw + storage_headroom_mw | MW | (0, 1e6) | 800.0 | null | An endogenous storage build; a leq is the only admissible form, and 800.0 MW sits under 15000.0 MW.
storage_dispatch_enabled | SCENE-SWITCH | -- | bool | -- | 1.0 | null | Selects whether storage is dispatched at all -- a mode the graph does not model, named as a scene switch by the worklist.
storage_duration_curve | PRODUCT | storage_energy_capacity_mwh = storage_duration_curve * storage_capacity_mw | hours | (0, 24) | unknown | null | The energy-to-power ratio; retype to hours and it multiplies the endogenous 800 MW -- but the endogenous operand means this belongs in the LP, not an equality, so it is stated as a ratio to be applied where the build is known.
strategic_reserves | BASE-NEEDED | strategic_reserve_volume_twh = strategic_reserve_days * net_imports_twh / 365 | days | (0, 365) | unknown | null | A stock of import cover; retype to days and it forms a volume against the net-import flow, which is 0.0 TWh at defaults.
synthetic_fuel_share_aviation | BASE-NEEDED | synthetic_aviation_fuel_pj = synthetic_fuel_share_aviation * aviation_fuel_demand | 1 | (0, 1) | 0.05 | null | A share whose base (aviation fuel demand) the graph does not carry in a typed form.
synthetic_fuel_share_shipping | BASE-NEEDED | synthetic_shipping_fuel_pj = synthetic_fuel_share_shipping * shipping_fuel_demand | 1 | (0, 1) | 0.05 | null | Same missing base for shipping.
temporal_aggregation | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects how time is aggregated; a run configuration.
temporal_clustering | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the time-series clustering; a run configuration.
temporal_resolution | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects the time step; a run configuration.
thermal_storage_capacity | THRESHOLD | thermal_storage_capacity leq storage_headroom_mw * storage_duration_curve | MWh | (0, 5e6) | 0.0 | null | An endogenous storage build; the leq is the only admissible form and 0.0 sits far under the headroom.
tidal_range_capacity | THRESHOLD | tidal_range_capacity leq total_capacity_mw + storage_headroom_mw | MW | (0, 1000) | unknown | null | Member of the fleet balance after the retype to MW at 0.
time_horizon | PRODUCT | investment_period_length_years = time_horizon / investment_periods | years | (0, 100) | 25.0 | null | The planning horizon; its coupling is the investment-period length identity with the period count.
topology_switching_enabled | SCENE-SWITCH | -- | bool | -- | 1.0 | null | Selects reconfigurable-topology operation, a dispatch mode the parameter graph does not model; named as a scene switch by the worklist.
transmission_capacity_factor | PRODUCT | transmission_transfer_mw = transmission_capacity_factor * total_capacity_mw | 1 | (0, 1) | 0.5 | null | The utilised share of installed capacity; 5000.0 MW at defaults, unit_of returns megawatt.
transmission_cost_multiplier | PRODUCT | effective_capex_transmission_usd_per_mw_km = transmission_cost_multiplier * capex_transmission | 1 | (0.5, 3) | 1.0 | null | The terrain/tender multiplier on the reference cost; 400.0 USD/MW-km at defaults and unit_of returns USD/kilometer/megawatt.
transmission_detail | SCENE-SWITCH | -- | categorical | -- | unknown | null | Selects how finely the transmission network is represented; a run configuration.
transmission_expansion_allowed | GATE-PRODUCT | permitted_transmission_spend_usd = transmission_expansion_allowed * line_upgrade_budget | bool | -- | 1.0 | null | A boolean multiplying a capital base the graph would carry once line_upgrade_budget is retyped to USD.
transmission_lead_time | BASE-NEEDED | transmission_lead_time_years = transmission_lead_time + construction_period / 12 | years | (0, 20) | unknown | null | A duration with no unit; retype to years and it forms the line lead time against the 30-month construction period.
transmission_loss_factor | PRODUCT | transmission_loss_factor eq transmission_loss_fraction | 1 | (0, 1) | 0.5 | null | A duplicate spelling of the 0.08 fraction energy_balance already uses; the alias also removes the 50%-loss default.
transmission_loss_reduction_target | PRODUCT | transmission_loss_target_fraction = (1 - transmission_loss_reduction_target) * transmission_loss_fraction | 1 | (0, 1) | unknown | null | A reduction share; a ceiling (`target leq fraction`) would fail at any target above 0.08, so the honest form is the ratio that yields the post-programme loss (0.064 at a 0.20 target).
tsam_segments | PRODUCT | tsam_segment_hours = 24 / tsam_segments | 1 | (1, 96) | unknown | null | The segments per day; unit_of returns None on the bare 24 and the placeholder 500000.0 makes 0.0 h, so the retype to a count is the precondition.
voltage_optimisation_enabled | SCENE-SWITCH | -- | bool | -- | 1.0 | null | Selects voltage-optimised operation, a dispatch mode the graph does not model.
voltage_support_requirement | PRODUCT | voltage_support_mvar = voltage_support_requirement * reactive_capability_mvar | MVAr | (0, 1) | unknown | null | A share of the 2805 MVAr reactive capability; unit_of returns None because the share has no unit, and at 0.25 the requirement is 701.25 MVAr.
wave_energy_converter_type | QUALITATIVE | -- | categorical | -- | unknown | null | An enumerated converter technology; an admissible-set choice.
wind_offshore_platform | QUALITATIVE | -- | categorical | -- | unknown | null | An enumerated platform type.
wind_speed_multiplier | PRODUCT | wind_effective_capacity_factor = capacity_factor_wind_onshore * wind_speed_multiplier | 1 | (0, 1) | 0.5 | null | A wind-resource scenario multiplier on the 0.40 onshore capacity factor; 0.20 at defaults, dimensionless as expected.
```

NEW BASES NEEDED

| base | unit | default | derivation |
|---|---|---|---|
| nominal_voltage_kv | kV | 220 | Low end of capex_transmission's own 220-765 kV prose. |
| households_total | 1 | 9000000 | population_total 45,000,000 / 5, the five-persons-per-household ratio batch 22 used to back-solve population_total. |
| transmission_route_mw_km | MW-km | 5000000 | 10,000 MW fleet over a 500 km corridor. |
| transmission_route_km | km | 500 | Same corridor, for the jobs-per-km factor. |
| new_connections_per_year | connections/year | 200000 | 2% electrification growth on 40.5 M electrified people at five per connection. |
| aviation_fuel_demand | PJ/year | unknown | The node itself; no figure is justifiable from the graph. |
| shipping_fuel_demand | PJ/year | unknown | As above. |
| baseline_emissions | MtCO2 | unknown | As above. |
| cold_storage_load | MWh/year | unknown | As above. |
| hydro_reservoir_energy_mwh | MWh | 3600000 | hydro_capacity 1500 MW x capacity_factor_hydro 0.55 x 8760 x 0.5 year of storage. |
| gravity_storage_energy_mwh | MWh | 800 | A 100 MW / 8 h pilot. |
| regulation_reserve_share | 1 | 0.02 | The 1-2% primary-frequency band. |
| regulation_up_share | 1 | 0.5 | Symmetric split of the regulation band. |
| regulation_down_share | 1 | 0.5 | Symmetric split. |
| spinning_reserve_share | 1 | 0.03 | Three-percent spinning band. |
| reserve_account_share | 1 | 0.02 | Two-percent licence reserve account. |
| strategic_reserve_days | days | unknown | No stockholding norm is held in sources/. |
| coal_starts_per_year | starts/year | 60 | 3000 MW cycling roughly weekly. |
| gas_starts_per_year | starts/year | 200 | 1500 MW, half the fleet daily. |
| breakers_per_feeder | 1 | unknown | No density figure in the graph. |
| lifeline_share | 1 | unknown | The share of households below the threshold. |
| households / number_of_generators | 1 | 220 | number_of_generators = the scada_telemetry_sites count batch 22 derived. |

PROPOSED BATCHES

1. **Reserve and reliability arithmetic (24).** spinning_reserve_requirement, spinning_reserve, non_spinning_reserve, regulation_reserve, regulation_up_requirement, regulation_down_requirement, spare_capacity, planning_reserve_margin, reserve_margin, reserve_accounts, strategic_reserves, black_start_capability, islanding_capability, voltage_support_requirement, grid_reliability_saifi, outage_cause_distribution, outage_coordination, forced_outage_rate_coal, number_of_generators, circuit_breakers, line_outage_start, line_outage_end, transmission_loss_reduction_target, contingency. Method: shares against bases the graph carries, aliases for the duplicate spellings, and one leq where a ceiling fails at defaults.

2. **Fleet builds and the unbuilt technologies (20).** biogas_capacity, landfill_gas_capacity, fusion_capacity, small_modular_reactor_capacity, tidal_range_capacity, marine_otec_capacity, marine_tidal_capacity, marine_wave_capacity, flywheel_capacity, compressed_air_capacity, hydrogen_fuel_cell_capacity, solar_thermal_capacity, gravity_storage_capacity, hydrogen_pipeline_capacity, storage_duration_curve, storage_capacity_mw, thermal_storage_capacity, hydrogen_storage_capacity, csp_storage_hours, coal_new_build. Method: retype to the technology's own unit at default 0 (as the 13 UNBUILT_TECHS already do), then fleet-balance membership or the energy-capacity product.

3. **Build ceilings and land (7).** gas_new_build, hydro_new_build, nuclear_new_build, solar_pv_max_build, solar_pv_land_constraint, biomass_sustainability_limit, coal_retirement_schedule. Method: leq ceilings on endogenous builds, with the lhs value at the reference build stated so the bound is checkable.

4. **Capital rates and their extensive bases (16).** capex_transmission, capex_distribution, distribution_capex_per_connection, hydrogen_pipeline_cost, hydrogen_storage_cost, capex_gravity_storage, capex_marine_otec, capex_marine_tidal, capex_gas_ccgt, capex_gas_ocgt, opex_fixed_wind_onshore, solar_pv_learning_rate, contingency, line_upgrade_budget, transmission_expansion_allowed, geothermal_drilling_success. Method: the batch-21/22 rate-against-base pattern, plus two Wright's-law and LCOE products the graph already carries in generic form.

5. **Network losses, density and cost multipliers (10).** transmission_loss_factor, distribution_loss_factor, transmission_capacity_factor, transmission_cost_multiplier, distribution_network_km, distribution_wheeling_charges, employment_factor_transmission, capex_marine_otec (deferred to 4), ac_voltage_limit, voltage_support_requirement (shared with 1). Method: shares multiplying the TWh and MW bases, aliases where a duplicate spelling already ships.

6. **Demand-side flexibility and digital (7).** demand_response_capacity, demand_response_potential, load_shifting_capability, load_factor_override, peak_demand_multiplier, smart_metering_penetration, smart_metering_rollout. Method: share x peak/interruptible base, with the programme gate multiplying the metered population.

7. **Temporal and investment arithmetic (6).** time_horizon, investment_periods, representative_days, tsam_segments, dispatch_interval, snapshot_weightings. Method: retype the counts and evaluate the quotients; snapshot_weightings stays qualitative as a vector.

8. **Scenario and qualitative register (declaration, no equations, ~40).** ami_infrastructure, asset_age_distribution, auction_frequency, clustering_method, coal_community_dependencies, cross_border_tension, custom_gis_boundary, cvar_alpha, cvar_omega, degradation_model, der_management_systems, distribution_conditions, distribution_detail, failure_history, failure_rate_curve, financial_transmission_rights, foresight, fossil_fuel_subsidies, fuel_price_scenario, gender_impact, heatwave_frequency, cold_snap_frequency, drought_frequency, insider_trading_rules, interannual_variability, near_duplicate_detection, outage_management_systems, parameter_overrides, probability_weight, reliability_centred_maintenance, scenario_description, scenario_owner, scenario_tag, scenario_template, scenario_visibility, security_constrained_dispatch, signal_extraction, signal_scoring, soil_contamination, soil_contamination_index, spatial_clustering, spatial_resolution, ssp_pathway, stakeholder_engagement_plan, stochastic_scenarios, temporal_aggregation, temporal_clustering, temporal_resolution, topology_switching_enabled, transmission_detail, voltage_optimisation_enabled, storage_dispatch_enabled, wave_energy_converter_type, wind_offshore_platform, hydrogen_storage_type, min_up_time_coal, min_down_time_coal, min_stable_level_coal, min_stable_level_gas, ramp_rate_coal, ramp_rate_gas. Method: a documented declaration in the worklist, no equation — the batch-22 compliance-register precedent.

Two cross-cutting findings. First, `unit_of` cannot decide the LCOE family: the 1000 and 8760 constants carry the kW→MW and year→hour conversions, so it returns USD/kW/year for an expression that is USD/MWh. That is the same blindness the shipped `lcoe_*_definition` equations already sit under, and it should be recorded rather than worked around. Second, `transmission_loss_factor` (0.5) and `transmission_loss_fraction` (0.08) are two spellings of one quantity with a six-fold disagreement, and only the second is read by `energy_balance` — an alias, not a product, is the fix.
