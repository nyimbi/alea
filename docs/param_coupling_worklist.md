# Coupling worklist

Every node still in `uncoupled()` (488 of 1261, as of the batch 27 bake on
2026-10-19) and the family class its coupling belongs to. Batches 12-27
coupled 305 nodes (793 -> 488): the financial core and fleet, the
duplicate-pair aliases, sector demand, fuel conversions, rate aliases, the
instrument and sector-coupling layers, the share family's products and the
time-index arithmetic (batch 20), the cost and rate families (batch 21), the
compliance register (batch 22), the extensive bases with the products they
unblock (batch 23), the carbon-market, subsidy and employment families with the
annual-quantity repair that unblocked them (batch 24), the gate family (batch
25), the adequacy and reserve family (batch 26), and the finance family -- the
two risk premiums, the insurance bases and their products, the transaction
cost, the ring-fence, the RAB roll-forward and the LLCR covenant (batch 27).
The classes name the method each coupling gets; nothing escapes the register.

## Batch 27's tail, and what is left

Batch 27 coupled sixteen nodes (504 -> 488) and added none to `uncoupled()`.
Four were aliases the catalog carries twice (`interest_rate_debt`,
`debt_service_coverage_ratio`, `maladaptation_risk`, `insurance_premiums`), and
twelve were products and charges the finance family supplies a base for: the
transaction cost against revenue, the sovereign and technology risk charges
against the debt- and equity-financed capital, the microinsurance premium and
the population it covers, the ring-fenced asset value, the solvency capital,
the RAB roll-forward, the project hurdle, and the two risk premiums and the
coverage share that drive them.

What remains, by the packs' own classification of the current `uncoupled()`
set: 104 PRODUCT, of which 50 still sit at the `unit=None def=500000.0`
placeholder; 96 BASE-NEEDED; 120 QUALITATIVE; 25 THRESHOLD; 44 scene switches;
and 102 that appear in no pack at all. The classes are read off the packs'
first class column, so a node the packs list twice is counted once, under the
class they gave it first; three nodes are both scene switches and qualitative,
which is why the six counts sum to 491 against a set of 488.

The PRODUCT remainder is the next authoring batch, and its size is the point:
50 nodes with a formula proposed and a placeholder where a unit should be. The
THRESHOLD and BASE-NEEDED remainders are the two that need something built
first: a bound needs an lhs whose value at defaults is not 500000, and a base
needs a quantity the graph does not carry. The QUALITATIVE remainder is the
graph's declared free space and `uncoupled()` retains it by the register's own
contract. The next families the research packs rank are the PRODUCT remainder
and the temporal and investment arithmetic.

## compliance register (1)

Batch 22 coupled 43 of the 46, and batch 26 closed two more: the regulation
up/down requirements are now slices of peak demand rather than waiting on a
`regulation_reserve` product. What is left is a missing base, not a deferral:

- `gis_requirements` -- a share of network assets in the GIS; needs an asset-count base (the graph carries km, not asset records).

## policy flag (bool) (15)

`ancillary_services_market`, `balancing_market`, `contract_for_difference`, `cross_border_trading`, `day_ahead_market`, `dg_placement_enabled`, `intraday_market`, `life_extension_possible`, `phase_shifting_enabled`, `real_time_market`, `security_constrained_dispatch`, `storage_dispatch_enabled`, `topology_switching_enabled`, `unit_commitment`, `voltage_optimisation_enabled`

These are **gates, not quantities**, and the GATE-PRODUCT half is now closed: all fifteen such switches are coupled, thirteen of them in batch 25 and the other two earlier. What is left are the scene switches: `unit_commitment`, `security_constrained_dispatch`, `topology_switching_enabled`, `dg_placement_enabled`, `storage_dispatch_enabled`, `phase_shifting_enabled`, `voltage_optimisation_enabled` and the market-design flags configure the run, and no equation should pretend otherwise. Recording that distinction is the coupling for this kind.

## rate family (0)

Cleared by batch 23. `energy_poverty_rate` is now `energy_poor_households /
households_total` against the household base the batch added, and
`regulated_tariff_rate` is the cost-recovery ratio
`regulated_tariff_usd_per_mwh / reference_tariff_usd_per_mwh` -- the two
revenue quantities the first form wanted are in different units (USD/year
against USD million/year), so the ratio is taken at the tariff rather than at
the revenue, where both sides are USD/MWh.

## cost family (2)

Batch 23 coupled seven of the nine, each against the extent it was waiting for:
`capex_transmission`, `capex_interconnector`, `hydrogen_pipeline_cost` and
`right_of_way_cost` against route km, `distribution_capex_per_connection`
against new connections, `capex_distribution` against peak demand and
`land_acquisition_cost_per_hectare` against hectares. Two remain:

- `hydrogen_storage_cost` -- the rate is USD/kWh of storage capacity, and the
  graph carries `hydrogen_storage_capacity` in MW without a duration. It needs
  a `hydrogen_storage_duration_hours` base (the energy/power split) before the
  product means anything.
- `currency_hedge_cost` -- the odd one. Its base is a currency exposure, not a
  physical quantity, and the graph carries no exposure node. A borrowed product
  would be a fabricated coupling, so it stays declared.

## unassigned (470)

The remainder, and it is not one class. It splits by what the node *is*:

- **Products waiting on a base** -- the extensive-base family above, plus the shares whose denominators are quantities the graph does not model (`import_dependency`, `remittance_dependency`, `balance_of_payments`).
- **Qualitative and organisational** -- capability-maturity scores, protocol and standard names, land-tenure classes, governance and risk indices, dispute-resolution fora. Their admissible set is a choice, not a measurement. They are the graph's declared free space and `uncoupled()` retains them by the register's own contract; the coupling for this class is a documented declaration, not an equation.
- **Scene switches and scenario controls** -- `market_model`, `market_structure`, `scenario_tag`, `scenario_owner`, `ssp_pathway`, `representative_days`, `temporal_aggregation` and the like. These configure the run; the engine reads them and no equation should.

The full list with descriptions is below.

## Every uncoupled node, with its description
Note on the placeholder signature: `unit=None def=500000.0` marks a node the catalog carries with no unit and the placeholder default the expansion gave every row. It is the placeholder register, not a value -- the unit is what a coupling needs first, and the default is what a node without one ships.


All 488, generated from the loaded graph so the list cannot drift from it. The family headings above name the method each node's coupling takes; this section is the inventory.

- `ac_voltage_limit` unit=None def=500000.0 -- Maximum AC voltage
- `accelerated_depreciation` unit=None def=500000.0 -- Accelerated depreciation
- `accelerated_depreciation_factor` unit='1' def=1.0 -- The multiple of straight-line depreciation the tax code permits. Bounded above by the fastest schedule any jurisdiction allows.
- `accumulation_risk` unit='1' def=500000.0 -- FIRM-SPECIFIC. The value is the total exposure the insurer has to a single event, and depends on the firm's own book. Not corrected; a fabricated range would silently reject a firm's correct figure. The default is retained as the graph's declared unknown.
- `adaptation_benefits` unit=None def=500000.0 -- Adaptation benefits
- `adaptation_costs` unit=None def=500000.0 -- Adaptation costs
- `adaptation_measures` unit=None def=500000.0 -- Adaptation measures
- `adaptive_capacity` unit='1' def=0.5 -- Composite index of institutional, financial and technical capacity to adapt, normalised to [0, 1]. Range is the index's construction.
- `agricultural_irrigation_load` unit=None def=500000.0 -- Irrigation pumping load
- `agricultural_machinery` unit='1' def=0.05 -- Share of agricultural machinery that is electric. A share.
- `airport_electrification` unit='1' def=0.1 -- Share of airport ground operations that are electric. A share.
- `ami_infrastructure` unit=None def=500000.0 -- AMI infrastructure
- `ancillary_services_market` unit='1' def=0.0 -- Whether an ancillary services market is modelled. A boolean.
- `archaeological_sites` unit=None def=500000.0 -- Archaeology
- `archaeological_sites_density` unit='sites/100km2' def=1.0 -- Number of documented archaeological sites per hundred square kilometres in the study area.
- `arrears_management` unit=None def=500000.0 -- Arrears management
- `article_6_2_parameters` unit=None def=500000.0 -- Article 6.2
- `article_6_4_parameters` unit=None def=500000.0 -- Article 6.4
- `asset_age_distribution` unit=None def=500000.0 -- Age distribution
- `asset_management_maturity` unit=None def=500000.0 -- AM maturity
- `asset_management_systems` unit=None def=500000.0 -- EAM
- `assignment_rights` unit=None def=500000.0 -- Assignment rights
- `auction_frequency` unit=None def=500000.0 -- Auction frequency
- `auction_mechanism` unit=None def=500000.0 -- Auction type
- `auction_price_cap` unit=None def=500000.0 -- Auction price ceiling
- `aviation_fuel_demand` unit=None def=500000.0 -- Aviation fuel demand
- `balance_of_payments` unit=None def=500000.0 -- Balance of payments
- `balancing_market` unit='1' def=1.0 -- Whether a balancing market is modelled. A boolean.
- `baseline_emissions` unit=None def=500000.0 -- Baseline emissions
- `battery_storage_adoption` unit='1' def=0.05 -- Share of households with a battery. A share; same reset of the placeholder default.
- `bill_shock_protection` unit=None def=500000.0 -- Bill shock protection
- `billing_systems` unit=None def=500000.0 -- Billing
- `biodiversity_impact` unit=None def=500000.0 -- Biodiversity
- `biodiversity_intactness_before` unit='1' def=0.7 -- The Biodiversity Intactness Index at the project site before development. Normalised to [0, 1].
- `biodiversity_intactness_index` unit='1' def=0.7 -- Biodiversity Intactness Index, normalised to [0, 1] where 1 is intact and 0 is devoid of its original species. Range is the index's construction.
- `biogas_capacity` unit=None def=500000.0 -- Biogas capacity
- `biomass_sustainability_limit` unit=None def=500000.0 -- Maximum sustainable biomass
- `black_start_capability` unit=None def=500000.0 -- Black start units available
- `buffer_pool_contribution` unit=None def=500000.0 -- Buffer pool
- `buffer_zones` unit=None def=500000.0 -- Buffer zones
- `business_interruption` unit='1' def=500000.0 -- FIRM-SPECIFIC. The scope of cover, waiting period and indemnity period vary by policy. Not corrected.
- `capex_gas_ccgt` unit='USD/kW' def=1100.0 -- Overnight installed cost of combined-cycle gas turbine. Range spans single-shaft at the low end to multi-shaft with district heating at the high end.
- `capex_gas_ocgt` unit='USD/kW' def=650.0 -- Overnight installed cost of open-cycle gas turbine. Lower capex and lower efficiency than the CCGT; that trade is why both live in the graph.
- `capex_gravity_storage` unit='USD/kWh' def=800.0 -- Installed cost of gravity-based energy storage. The technology is deployed at small scale; the range is inferred from the pilot installations, not from a cost curve.
- `capex_marine_otec` unit='USD/kW' def=12000.0 -- Installed cost of ocean thermal energy conversion. No commercial OTEC plant exists; the range is derived from the pilot projects and the thermodynamic cycle's own scaling, and the parameter is a speculative number that should be treated as such.
- `capex_marine_tidal` unit='USD/kW' def=7000.0 -- Installed cost of tidal stream and tidal range. The range is wide because tidal range with civil works is not the same technology as a tidal stream turbine; the graph does not distinguish them and the parameter therefore admits both.
- `capital_gains_tax` unit='1' def=0.2 -- Tax rate on realised capital gains. A share; the range spans the sample's jurisdictions.
- `carbon_credit_rating` unit=None def=500000.0 -- Rating
- `carbon_credit_vintage` unit=None def=500000.0 -- Vintage
- `cash_sweep` unit=None def=500000.0 -- Cash sweep
- `cat_bond_parameters` unit=None def=500000.0 -- Cat bonds
- `cat_bond_spread` unit='basis_points' def=800.0 -- The coupon a catastrophe bond pays above the risk-free rate, in basis points. Range spans the best-rated tranches at the low end to the riskiest at the high end. The unit is basis points; 100 bp is 1 percent.
- `catastrophe_modelling` unit='1' def=500000.0 -- FIRM-SPECIFIC. The output of a cat model applied to a specific book. Not corrected; this is a model output, not a parameter, and a future batch should either remove the node or replace it with a cat-model reference id.
- `cdm_methodologies` unit=None def=500000.0 -- CDM
- `change_of_control` unit=None def=500000.0 -- Change of control
- `child_labour_prohibition` unit=None def=500000.0 -- Child labour
- `circuit_breakers` unit=None def=500000.0 -- Circuit breakers
- `civil_unrest_risk` unit=None def=500000.0 -- Civil unrest
- `claims_history` unit='1' def=500000.0 -- FIRM-SPECIFIC. The firm's own loss history, not a market statistic. Not corrected.
- `climate_risk_disclosure` unit=None def=500000.0 -- TCFD
- `climate_sensitivity` unit=None def=500000.0 -- Climate sensitivity
- `clustering_method` unit=None def=500000.0 -- Clustering method
- `co_emissions` unit=None def=500000.0 -- CO emissions
- `coal_community_dependencies` unit=None def=500000.0 -- Coal community reliance
- `coal_new_build` unit=None def=500000.0 -- New coal capacity allowed
- `coal_retirement_schedule` unit=None def=500000.0 -- Coal retirement years
- `coastal_erosion` unit=None def=500000.0 -- Coastal erosion
- `cold_snap_frequency` unit=None def=500000.0 -- Cold snap frequency
- `cold_storage_load` unit=None def=500000.0 -- Cold chain energy demand
- `collateral_valuation` unit=None def=500000.0 -- Collateral valuation
- `collusion` unit=None def=500000.0 -- Collusion detection
- `communication_protocols` unit=None def=500000.0 -- Protocols
- `community_benefit_sharing` unit=None def=500000.0 -- Benefit sharing
- `community_development_funds` unit=None def=500000.0 -- Community funds
- `community_health_safety` unit=None def=500000.0 -- Community H&S
- `community_transition_funding` unit=None def=500000.0 -- Transition funding
- `compensation_mechanisms` unit=None def=500000.0 -- Compensation
- `compensation_rates` unit=None def=500000.0 -- Compensation
- `compensation_share_of_market` unit='1' def=1.5 -- The multiple of market value the compensation package pays. A share of a share; the sample's practice varies from exact market value to a multiplier where livelihoods are lost. The upper bound is the multiplier, not a fraction.
- `complaint_handling` unit=None def=500000.0 -- Complaint handling
- `compressed_air_capacity` unit=None def=500000.0 -- Compressed air storage
- `concession_terms` unit=None def=500000.0 -- Concession terms
- `condition_based_maintenance` unit=None def=500000.0 -- CBM
- `conservation_easements` unit=None def=500000.0 -- Easements
- `construction_load` unit=None def=500000.0 -- Temporary construction load
- `construction_machinery` unit='1' def=0.05 -- Share of construction machinery that is electric. A share.
- `consumer_education` unit=None def=500000.0 -- Consumer education
- `consumer_price_index_link` unit=None def=500000.0 -- CPI link
- `contingency` unit=None def=500000.0 -- Contingency on capex
- `contract_for_difference` unit='1' def=0.0 -- Whether a CfD mechanism is modelled. A boolean.
- `cooling_water_demand` unit=None def=500000.0 -- Cooling water demand
- `corsia_parameters` unit=None def=500000.0 -- CORSIA
- `cost_pass_through_mechanism` unit=None def=500000.0 -- Pass-through rules
- `counterparty_risk` unit=None def=500000.0 -- Counterparty risk
- `country_risk_rating` unit=None def=500000.0 -- Country risk rating
- `crew_availability` unit='1' def=0.85 -- Share of hours a maintenance crew is available to the fleet. A share; the shipped [0, 1e6] admitted a crew 500,000 times overstaffed.
- `critical_mineral_dependencies` unit=None def=500000.0 -- Critical minerals
- `cross_border_permitting_time` unit=None def=500000.0 -- Cross-border permitting
- `cross_border_tension` unit=None def=500000.0 -- Cross-border tension
- `cross_border_trading` unit='1' def=1.0 -- DEPRECATED. Duplicate of `cross_border_trade_allowed`. The shipped node was typed float; the canonical is boolean.
- `cross_default` unit=None def=500000.0 -- Cross-default
- `cross_subsidy_transparency` unit=None def=500000.0 -- Cross-subsidy
- `csp_storage_hours` unit='hours' def=24.0 -- CSP thermal storage
- `cultural_heritage_impact` unit=None def=500000.0 -- Cultural heritage
- `cultural_heritage_impact_score` unit='1' def=0.2 -- A composite score of the project's impact on cultural heritage, normalised to [0, 1]. Higher is greater impact.
- `cultural_heritage_sites_density` unit='sites/100km2' def=2.0 -- Number of documented cultural heritage sites per hundred square kilometres in the study area.
- `cumulative_impact_assessment` unit=None def=500000.0 -- CIA
- `currency_hedge_cost` unit=None def=500000.0 -- Currency hedge cost
- `current_account_balance` unit=None def=500000.0 -- Current account balance
- `custom_gis_boundary` unit=None def=500000.0 -- Custom GIS boundary
- `customer_information_systems` unit=None def=500000.0 -- CIS
- `customs_duty` unit='1' def=0.1 -- Customs duty as a share of imported goods value. Overlaps with import duty; the graph carries both and the next batch should nominate one as canonical.
- `cvar_alpha` unit=None def=500000.0 -- CVaR tail level
- `cvar_omega` unit=None def=500000.0 -- Risk-aversion weight
- `cyber_incident_response` unit=None def=500000.0 -- Incident response
- `cyber_threat_level` unit=None def=500000.0 -- Cyber threat
- `data_backup_recovery` unit=None def=500000.0 -- Backup & recovery
- `data_centre_demand` unit=None def=500000.0 -- New data centre load
- `day_ahead_market` unit='1' def=1.0 -- Whether a day-ahead market is modelled. A boolean.
- `debt_management` unit=None def=500000.0 -- Debt management
- `debt_sustainability` unit=None def=500000.0 -- Debt sustainability
- `deductible_levels` unit='1' def=500000.0 -- FIRM-SPECIFIC. The deductible schedule is a property of a specific policy book. Not corrected; the market-level statistic is `deductible_share`, which is declared in Part A.
- `default_events` unit=None def=500000.0 -- Events of default
- `degradation_model` unit=None def=500000.0 -- Degradation
- `demand_growth_profile` unit=None def=500000.0 -- Shape of growth curve
- `demand_growth_rate` unit='1/year' def=0.04 -- DEPRECATED. Duplicate of `demand_growth`. The shipped node declared unit "1" and range [0, 1] and a placeholder default; the canonical id carries the correct unit `1/year` and the correct range. A scenario that reads the deprecated id would silently get a growth rate on the wrong scale.
- `demand_response_capacity` unit=None def=500000.0 -- Demand response capacity
- `demand_response_potential` unit=None def=500000.0 -- Share of demand that is flexible
- `depreciation_schedule_accelerated` unit=None def=500000.0 -- Accelerated depreciation
- `depreciation_schedule_declining` unit=None def=500000.0 -- Declining balance
- `depreciation_schedule_linear` unit=None def=500000.0 -- Linear depreciation
- `der_management_systems` unit=None def=500000.0 -- DERMS
- `desalination_capacity` unit=None def=500000.0 -- Desalination capacity
- `desalination_demand` unit=None def=500000.0 -- Desalination electricity demand
- `desalination_energy` unit=None def=500000.0 -- Desalination energy intensity
- `dg_placement_enabled` unit='1' def=1.0 -- Corrected from float to bool.
- `digital_divide_metrics` unit='1' def=0.5 -- A composite index of connectivity, price and skill, normalised to [0, 1]. The shipped [0, 1e6] admitted values the index's own construction cannot produce. The range is set by the index's normalisation, not by observation.
- `direct_agreement` unit=None def=500000.0 -- Direct agreement
- `disconnection_protection` unit=None def=500000.0 -- Disconnection protection
- `dispatch_interval` unit=None def=500000.0 -- Dispatch interval
- `dispute_resolution_mechanism` unit=None def=500000.0 -- Dispute resolution
- `distribution_conditions` unit=None def=500000.0 -- Distribution conditions
- `distribution_detail` unit=None def=500000.0 -- Distribution detail
- `distribution_loss_factor` unit='1' def=0.5 -- Distribution losses
- `distribution_network_km` unit='km' def=45000.0 -- Distribution circuit-km: a 10 GW single-country network at about 4-5 km per MW.
- `double_tax_treaty` unit=None def=500000.0 -- Treaty network
- `drought_frequency` unit=None def=500000.0 -- Drought frequency multiplier
- `drought_risk` unit=None def=500000.0 -- Drought risk
- `drought_severity` unit=None def=500000.0 -- Drought severity multiplier
- `early_retirement_packages` unit=None def=500000.0 -- Early retirement
- `ecosystem_services_index` unit='1' def=0.7 -- Composite index of ecosystem service provision, normalised to [0, 1]. Range is the index's construction.
- `efficiency_benchmarking` unit='1' def=0.85 -- A composite of the utility's efficiency against the frontier or against a peer group, normalised to [0, 1]. A share-shaped index.
- `efficient_frontier` unit=None def=500000.0 -- Efficient frontier
- `electrification_timeline` unit=None def=500000.0 -- Year to reach target
- `electrolyser_capacity` unit=None def=500000.0 -- Electrolyser capacity
- `emergency_preparedness` unit=None def=500000.0 -- Emergency prep
- `emergency_shelter_load` unit=None def=500000.0 -- Emergency shelter load
- `employment_factor_biomass` unit=None def=500000.0 -- Jobs/MW biomass
- `employment_factor_coal` unit=None def=500000.0 -- Jobs/MW coal
- `employment_factor_gas` unit=None def=500000.0 -- Jobs/MW gas
- `employment_factor_geothermal` unit=None def=500000.0 -- Jobs/MW geothermal
- `employment_factor_hydro` unit=None def=500000.0 -- Jobs/MW hydro
- `employment_factor_solar` unit=None def=500000.0 -- Jobs/MW solar
- `employment_factor_transmission` unit=None def=500000.0 -- Jobs/km transmission
- `employment_factor_wind` unit=None def=500000.0 -- Jobs/MW wind
- `energy_security_index` unit='1' def=0.5 -- Composite index of import dependency, fuel diversity and infrastructure adequacy, normalised to [0, 1]. Range is the index's construction, not a policy range.
- `environmental_representations` unit=None def=500000.0 -- Environmental reps
- `equator_principles` unit=None def=500000.0 -- Equator Principles
- `ev_adoption_timeline` unit=None def=500000.0 -- Year to reach EV share
- `ev_battery_size` unit=None def=500000.0 -- Average EV battery size
- `ev_efficiency` unit=None def=500000.0 -- EV efficiency
- `ev_share_new_sales` unit='1' def=0.2 -- Fraction of new vehicle sales that are electric in the horizon year. A share of a flow, not a stock; the shipped range admitted values 500,000 times the maximum.
- `exchange_rate_usd_local` unit=None def=500000.0 -- Exchange rate (USD/local)
- `exchange_rate_volatility` unit=None def=500000.0 -- Exchange rate volatility
- `excise_duty_fuel` unit='1' def=0.2 -- Excise duty on fuel, as a share of the retail price. A share.
- `export_competitiveness` unit=None def=500000.0 -- Export competitiveness
- `export_duty` unit='1' def=0.0 -- Export duty rate on exported energy or energy carriers. A share.
- `exposure_index` unit='1' def=0.5 -- Composite index of a system's exposure to climate hazards, normalised to [0, 1]. Range is the index's construction.
- `external_debt` unit=None def=500000.0 -- External debt
- `extreme_weather_events` unit=None def=500000.0 -- Extreme weather frequency
- `failure_history` unit=None def=500000.0 -- Failure history
- `failure_rate_curve` unit='1' def=1.0 -- A scalar index of the failure-rate curve's shape — 0 for a flat exponential, 1 for a bathtub, 2 for wear-out dominated. Not the curve itself, which is a function and cannot be a scalar; this is the shape selector that a Weibull fit reduces to.
- `financial_transmission_rights` unit=None def=500000.0 -- FTR model
- `firm_build_fleet_mw` unit='MW' def=10000.0 -- Sum of the optimiser's per-technology builds. Not a decision the graph computes in propagation -- the technologies' variables are the LP's -- but the identity every build set must satisfy is declared here, and the reserve margins read the firm part of it.
- `fishing_community_load` unit=None def=500000.0 -- Coastal fishing load
- `fishing_vessel_fuel` unit=None def=500000.0 -- Fishing vessel fuel
- `fit_capacity_cap` unit=None def=500000.0 -- FiT capacity cap
- `flood_risk` unit=None def=500000.0 -- Flood risk
- `flywheel_capacity` unit=None def=500000.0 -- Flywheel storage
- `forced_outage_rate_coal` unit='1' def=0.1 -- Fraction of hours the coal fleet is unavailable due to forced outage. A share; the shipped [0, 1e6] admitted a value 500,000 times the maximum.
- `foreign_direct_investment` unit=None def=500000.0 -- Foreign direct investment
- `foreign_exchange_reserves` unit=None def=500000.0 -- Foreign exchange reserves
- `foresight` unit=None def=500000.0 -- Foresight type
- `freight_electrification` unit='1' def=0.05 -- Share of freight tonne-kilometres moved by electric drivetrain. A share.
- `fuel_cost_hydrogen` unit='USD/MWh' def=120.0 -- Delivered hydrogen cost per megawatt-hour of thermal energy. Converted from USD per kg at 33.3 kWh/kg LHV; the conversion is an admission, not a fact — a different calorific value would change the number.
- `fuel_price_scenario` unit=None def=500000.0 -- Fuel price scenario
- `fuel_price_volatility` unit=None def=500000.0 -- Fuel price volatility
- `fusion_capacity` unit=None def=500000.0 -- Fusion capacity
- `gas_new_build` unit=None def=500000.0 -- New gas capacity allowed
- `gasification_capacity` unit=None def=500000.0 -- Gasification capacity
- `gate_closure` unit=None def=500000.0 -- Gate closure
- `gdp_per_capita_growth` unit=None def=500000.0 -- GDP per capita growth
- `gender_impact` unit=None def=500000.0 -- Gender dimensions
- `geopolitical_risk_index` unit='1' def=0.5 -- Composite index of political, security and diplomatic risk, normalised to [0, 1]. Higher is riskier. Range is the index's construction.
- `geothermal_drilling_success` unit=None def=500000.0 -- Drilling success rate
- `gis_requirements` unit='1' def=0.6 -- The share of network assets in the GIS.
- `glacial_lake_outburst` unit=None def=500000.0 -- GLOF
- `gold_standard_methodologies` unit=None def=500000.0 -- Gold Standard
- `gravity_storage_capacity` unit=None def=500000.0 -- Gravity storage
- `grievance_redress_effectiveness` unit='1' def=0.75 -- Share of grievances resolved to the complainant's satisfaction, per the project's own GRM. A share.
- `grievance_redress_mechanism` unit=None def=500000.0 -- GRM
- `habitat_loss` unit=None def=500000.0 -- Habitat loss
- `habitat_loss_hectares` unit='hectares' def=500.0 -- Hectares of natural habitat lost to the project.
- `health_impact_dalys` unit='DALY/year' def=50000000.0 -- DALYs
- `health_impact_morbidity` unit=None def=500000.0 -- Illness cases
- `health_impact_mortality` unit=None def=500000.0 -- Premature deaths
- `heat_pump_cop` unit=None def=500000.0 -- Heat pump COP
- `heat_stress` unit=None def=500000.0 -- Heat stress
- `heatwave_frequency` unit=None def=500000.0 -- Heatwave frequency
- `human_review` unit=None def=500000.0 -- Human review
- `hydro_capacity_factor` unit='1' def=0.5 -- Hydro capacity factor
- `hydro_drought_multiplier` unit='1' def=0.5 -- Drought impact multiplier
- `hydro_new_build` unit=None def=500000.0 -- New hydro capacity
- `hydro_reservoir_level` unit=None def=500000.0 -- Initial reservoir level
- `hydrogen_demand_domestic` unit=None def=500000.0 -- Domestic hydrogen demand
- `hydrogen_export_port` unit=None def=500000.0 -- Export port
- `hydrogen_fuel_cell_capacity` unit=None def=500000.0 -- Hydrogen fuel cell capacity
- `hydrogen_production_demand` unit=None def=500000.0 -- Electricity for hydrogen production
- `hydrogen_storage_capacity` unit='MWh' def=0.0 -- Installed hydrogen storage capacity, chosen by the optimiser. Same role correction.
- `hydrogen_storage_cost` unit='USD/kWh' def=15.0 -- Installed cost of hydrogen storage. The unit is USD per kWh of energy capacity; the range spans above-ground at the low end to salt cavern at the high end (the cavern is not expensive per unit but the exploration is).
- `hydrogen_storage_type` unit=None def=500000.0 -- Storage type
- `ilo_conventions` unit=None def=500000.0 -- ILO conventions
- `import_dependency` unit=None def=500000.0 -- Import dependency
- `indigenous_peoples_rights` unit=None def=500000.0 -- FPIC
- `industrial_heat_demand` unit=None def=500000.0 -- Industrial heat demand
- `insider_trading_rules` unit=None def=500000.0 -- Insider trading
- `interannual_variability` unit=None def=500000.0 -- Interannual variability
- `internet_penetration` unit='1' def=0.5 -- Share of the population with internet access. Shipped correctly as [0, 1]; the entry is retained here only because a subsequent batch should reconcile the shipped shares into a single naming convention (`_penetration` vs `_coverage` vs `_share` vs `_adoption`), and this is the register where that reconciliation lands.
- `intraday_market` unit='1' def=0.0 -- Whether an intraday market is modelled. A boolean.
- `investment_periods` unit=None def=500000.0 -- Investment periods
- `irrigation_coverage` unit='1' def=0.15 -- Share of arable land under irrigation. A share; the shipped range admitted a value 500,000 times the maximum.
- `irrigation_pumping_demand` unit=None def=500000.0 -- Irrigation pumping demand
- `islanding_capability` unit=None def=500000.0 -- Islanding capability
- `iso_55000_compliance` unit=None def=500000.0 -- ISO 55000
- `just_transition_fund` unit=None def=500000.0 -- JT fund
- `land_acquisition_costs` unit=None def=500000.0 -- Land costs
- `land_aggregation` unit=None def=500000.0 -- Land aggregation
- `land_aggregation_fragmentation` unit='parcels/km2' def=20.0 -- The number of distinct parcels the project must assemble per unit of area, expressed as parcels per square kilometre. Higher means more negotiation. The shipped node has no unit and no range; this is the parameter's own physical definition.
- `land_availability` unit=None def=500000.0 -- Land availability
- `land_availability_fraction` unit='1' def=0.5 -- Share of the study area that is technically and legally available for the project. A share; complements the protected-area constraint the graph already carries.
- `land_rights` unit=None def=500000.0 -- Land rights
- `land_tenure` unit=None def=500000.0 -- Land tenure
- `land_use_change` unit=None def=500000.0 -- Land use change
- `land_use_conflict_index` unit='1' def=0.3 -- A composite index of competing land uses in the project's vicinity, normalised to [0, 1]. Higher is more contested.
- `land_use_conflicts` unit=None def=500000.0 -- Land use conflicts
- `land_use_planning` unit=None def=500000.0 -- Land use planning
- `landfill_gas_capacity` unit=None def=500000.0 -- Landfill gas capacity
- `landslide_risk` unit=None def=500000.0 -- Landslide risk
- `liability_exposure` unit='1' def=500000.0 -- FIRM-SPECIFIC. The scope of liability is a property of the firm's book. Not corrected.
- `licence_conditions` unit=None def=500000.0 -- Licence conditions
- `licence_fees` unit='USD/MW/year' def=500.0 -- Annual licence fee per megawatt of licensed capacity, in USD per MW-year.
- `life_extension_possible` unit='1' def=0.0 -- Whether the model may extend an ageing plant's life. A boolean.
- `lifeline_threshold` unit=None def=500000.0 -- Lifeline threshold
- `line_outage_end` unit=None def=500000.0 -- When the outage ends
- `line_outage_start` unit=None def=500000.0 -- When the outage begins
- `load_factor_override` unit=None def=500000.0 -- Override default load factor
- `load_shifting_capability` unit=None def=500000.0 -- Hours of load shifting possible
- `local_content_employment` unit=None def=500000.0 -- Local employment
- `loss_factor_cross_border` unit='1' def=0.03 -- Share of cross-border flow lost in transit. A share; the shipped range admitted a loss of 500,000 times the flow.
- `loss_reduction_investment` unit=None def=500000.0 -- Investment in loss reduction
- `lpg_subsidies` unit=None def=500000.0 -- LPG subsidy
- `maintenance_history` unit=None def=500000.0 -- Maintenance history
- `maintenance_schedule` unit=None def=500000.0 -- Planned maintenance timing
- `maintenance_schedule_optimisation` unit=None def=500000.0 -- Optimise maintenance timing
- `marine_otec_capacity` unit=None def=500000.0 -- Installed OTEC capacity
- `marine_tidal_capacity` unit=None def=500000.0 -- Installed tidal capacity
- `marine_wave_capacity` unit=None def=500000.0 -- Installed wave capacity
- `maritime_security` unit=None def=500000.0 -- Maritime security
- `market_abuse_prevention` unit=None def=500000.0 -- Market abuse
- `market_coupling` unit=None def=500000.0 -- Market coupling
- `market_model` unit=None def='regulated' -- Which market model the simulation assumes. A categorical with four documented values.
- `market_structure` unit=None def='single_buyer' -- Which market structure the model assumes. A categorical with four documented values, not a float. The shipped declaration admitted a value of 500,000 which corresponds to no structure.
- `material_adverse_change` unit=None def=500000.0 -- MAC clause
- `mercury_emissions` unit=None def=500000.0 -- Mercury
- `microgrid_deployment` unit=None def=500000.0 -- Microgrid deployment
- `military_energy_demand` unit=None def=500000.0 -- Military energy demand
- `min_down_time_coal` unit=None def=500000.0 -- Coal minimum down time
- `min_stable_level_coal` unit=None def=500000.0 -- Coal minimum stable level
- `min_stable_level_gas` unit=None def=500000.0 -- Gas minimum stable level
- `min_up_time_coal` unit=None def=500000.0 -- Coal minimum up time
- `mining_demand_growth` unit=None def=500000.0 -- Additional mining load growth
- `mining_electrification` unit='1' def=0.1 -- Fraction of mining energy demand met by electricity. A share.
- `mining_haulage` unit=None def=500000.0 -- Mining haulage
- `mining_hydrogen_haulage` unit=None def=500000.0 -- Hydrogen haulage in mining
- `mobile_coverage` unit='1' def=0.9 -- Share of the population covered by mobile signal. A share.
- `mrv_parameters` unit=None def=500000.0 -- MRV
- `near_duplicate_detection` unit=None def=500000.0 -- Near-duplicate detection
- `new_entrants` unit=None def=500000.0 -- Market entry
- `novation_terms` unit=None def=500000.0 -- Novation
- `nox_emissions` unit=None def=500000.0 -- NOx emissions
- `nuclear_lead_time` unit=None def=500000.0 -- Nuclear construction lead time
- `nuclear_new_build` unit=None def=500000.0 -- New nuclear capacity
- `number_of_generators` unit=None def=500000.0 -- Number of generators
- `number_of_retailers` unit=None def=500000.0 -- Number of retailers
- `occupational_health_safety` unit=None def=500000.0 -- OHS
- `official_development_assistance` unit=None def=500000.0 -- Official development assistance
- `opex_fixed_wind_onshore` unit='USD/kW/year' def=30.0 -- Fixed operations and maintenance for wind onshore: the per-kilowatt annual cost of staff, inspection and scheduled overhaul, paid whether or not the plant runs.
- `opex_variable_electrolyser` unit='USD/MWh' def=1.0 -- Variable O&M of electrolysis per megawatt-hour of hydrogen produced. Excludes electricity, which is the dominant cost and enters as an input to the Link.
- `outage_cause_distribution` unit='1' def=0.35 -- Share of interruption events attributable to weather. The graph carries one scalar and the sample contains four cause classes; this is the weather share, and a future batch should split it into weather, equipment, human and other.
- `outage_management_systems` unit=None def=500000.0 -- OMS
- `parameter_overrides` unit=None def=500000.0 -- Parameter overrides
- `parametric_insurance` unit='1' def=500000.0 -- FIRM-SPECIFIC. The share-of-loss version and the trigger threshold are declared in Part A. Not corrected.
- `parametric_insurance_coverage` unit='1' def=0.5 -- Share of the loss a parametric instrument covers when its trigger fires. A share.
- `parametric_trigger_threshold` unit='1' def=0.9 -- The physical hazard level at which a parametric policy pays out, expressed as a share of the policy's notional hazard. A share; the range spans the mean trigger at the low end to the 1-in-100-year at the high end.
- `payment_plans` unit=None def=500000.0 -- Payment plans
- `payment_security_required` unit=None def=500000.0 -- Payment security
- `peak_demand_multiplier` unit='1' def=0.5 -- Scaling factor for peak demand
- `pension_security` unit=None def=500000.0 -- Pension security
- `performance_bond` unit='1' def=0.05 -- Bond posted as a share of capex. A share.
- `phase_shifting_enabled` unit='1' def=0.0 -- Corrected from float to bool.
- `physical_risk_score` unit='1' def=0.4 -- A composite score of the asset's physical climate risk, normalised to [0, 1]. Higher is riskier. The shipped declaration admitted a value 500,000 times the maximum.
- `plant_retirement_age` unit=None def=500000.0 -- Retirement age by technology
- `pm10_emissions` unit=None def=500000.0 -- PM10 emissions
- `pm25_emissions` unit=None def=500000.0 -- PM2.5 emissions
- `port_electrification` unit='1' def=0.1 -- Share of port operations that are electric. A share.
- `post_harvest_processing_load` unit=None def=500000.0 -- Post-harvest processing load
- `ppa_arbitration_venue` unit=None def=500000.0 -- Arbitration venue
- `ppa_change_in_law` unit=None def=500000.0 -- Change in law
- `ppa_curtailment_compensation` unit=None def=500000.0 -- Curtailment compensation
- `ppa_dispute_resolution` unit=None def=500000.0 -- Dispute resolution
- `ppa_force_majeure` unit=None def=500000.0 -- Force majeure
- `ppa_governing_law` unit=None def=500000.0 -- Governing law
- `ppa_indexation` unit=None def=500000.0 -- Indexation formula
- `ppa_pricing_formula` unit=None def=500000.0 -- PPA pricing
- `ppa_take_or_pay` unit=None def=500000.0 -- Take-or-pay provisions
- `ppa_termination_payments` unit=None def=500000.0 -- Termination payments
- `precipitation_multiplier` unit='1' def=0.5 -- Precipitation multiplier
- `predictive_maintenance_adoption` unit='1' def=0.5 -- Predictive maintenance adoption
- `premium_share_of_asset` unit='1' def=0.008 -- Annual premium as a fraction of the insured asset's value. A share; the range spans utility-scale generation at the low end to distributed assets at the high end.
- `prepayment_metering` unit=None def=500000.0 -- Prepayment
- `pricing_mechanism` unit=None def=500000.0 -- Pricing mechanism
- `probability_weight` unit=None def=500000.0 -- Scenario probability
- `protected_areas` unit=None def=500000.0 -- Protected areas
- `pyrolysis_capacity` unit=None def=500000.0 -- Pyrolysis capacity
- `railway_electrification` unit='1' def=0.2 -- Share of the rail network that is electrified. A share; the shipped range admitted a value 500,000 times the maximum.
- `ramp_rate_coal` unit=None def=500000.0 -- Coal ramp rate
- `ramp_rate_gas` unit=None def=500000.0 -- Gas ramp rate
- `rare_earth_dependencies` unit=None def=500000.0 -- Rare earths
- `re_target_carrier` unit=None def=500000.0 -- Which renewables count
- `real_time_market` unit='1' def=0.0 -- Whether a real-time market is modelled. A boolean.
- `redeployment_options` unit=None def=500000.0 -- Redeployment
- `refinancing_terms` unit=None def=500000.0 -- Refinancing
- `regulation_reserve` unit=None def=500000.0 -- Regulation reserve
- `regulatory_accounts` unit=None def=500000.0 -- Regulatory accounts
- `regulatory_asset_valuation_method` unit='1' def=0.0 -- Which valuation method the regulator uses — 0 for historical cost, 1 for indexed historical, 2 for current-cost. A categorical value smuggled into a float; the type correction in Part D is the substantive fix, and this range is a stopgap that keeps the value meaningful until that fix lands.
- `regulatory_lag` unit='years' def=1.0 -- Years between cost incurrence and its recovery in tariff. Bounded below at zero and above at the period length. A lag of 0 is contemporaneous recovery; the sample's central value is 1.
- `regulatory_period_length` unit='years' def=5.0 -- Years between tariff reviews. Bounded below at 1 (annual review) and above at 10 (long-term concession). Four to five is the mode in the sample.
- `reinsurance_parameters` unit='1' def=500000.0 -- FIRM-SPECIFIC. The market-level statistic is `retention_share`, declared in Part A. Not corrected.
- `reliability_centred_maintenance` unit=None def=500000.0 -- RCM
- `remedy_periods` unit='days' def=60.0 -- Days a defaulting party has to cure before the lender may step in. Bounded below at one day and above at one year.
- `remittance_dependency` unit=None def=500000.0 -- Remittance dependency
- `remittance_flows` unit=None def=500000.0 -- Remittance flows
- `renewable_curtailment_limit` unit=None def=500000.0 -- Maximum curtailment
- `renewable_penetration_limit` unit=None def=500000.0 -- Maximum instantaneous penetration
- `representative_days` unit='days' def=50.0 -- Representative days
- `reserve_accounts` unit=None def=500000.0 -- Reserve accounts
- `resettlement_costs` unit=None def=500000.0 -- Resettlement costs
- `resilience_investment` unit=None def=500000.0 -- Resilience investment
- `resilience_metrics` unit=None def=500000.0 -- Resilience metrics
- `resilience_score` unit='1' def=0.5 -- Composite score of a system's resilience to shocks, normalised to [0, 1]. Range is the index's construction.
- `retail_competition` unit=None def=500000.0 -- Retail competition
- `retraining_costs` unit=None def=500000.0 -- Retraining cost
- `risk_based_maintenance` unit=None def=500000.0 -- RBM
- `risk_transfer_mechanisms` unit=None def=500000.0 -- Risk transfer
- `rolling_horizon_window` unit=None def=500000.0 -- Rolling horizon window
- `rooftop_solar_adoption` unit='1' def=0.1 -- Share of suitable rooftops with PV. A share; same reset of the placeholder default.
- `sacred_sites` unit=None def=500000.0 -- Sacred sites
- `sacred_sites_density` unit='sites/100km2' def=1.0 -- Number of documented sacred sites per hundred square kilometres in the study area. Distinct from cultural heritage because sacred sites often have no legal register.
- `salinity_gradient_capacity` unit=None def=500000.0 -- Salinity gradient capacity
- `scenario_description` unit=None def=500000.0 -- Scenario description
- `scenario_owner` unit=None def=500000.0 -- Scenario owner
- `scenario_tag` unit=None def=500000.0 -- Scenario tagging
- `scenario_template` unit=None def=500000.0 -- Scenario template
- `scenario_visibility` unit=None def=500000.0 -- Scenario visibility
- `sea_level_rise` unit=None def=500000.0 -- SLR
- `security_constrained_dispatch` unit='1' def=1.0 -- Whether the dispatch is constrained by network limits. A boolean.
- `security_package` unit=None def=500000.0 -- Security package
- `shipping_fuel_demand` unit=None def=500000.0 -- Shipping fuel demand
- `signal_extraction` unit=None def=500000.0 -- Signal extraction
- `signal_scoring` unit=None def=500000.0 -- Signal scoring
- `skills_gap_assessment` unit=None def=500000.0 -- Skills gap
- `skills_requirements` unit=None def=500000.0 -- Skills by technology
- `small_modular_reactor_capacity` unit=None def=500000.0 -- SMR capacity
- `snapshot_weightings` unit=None def=500000.0 -- Snapshot weightings
- `social_protection_parameters` unit=None def=500000.0 -- Social protection
- `social_representations` unit=None def=500000.0 -- Social reps
- `soil_contamination` unit=None def=500000.0 -- Soil contamination
- `soil_contamination_index` unit='1' def=0.1 -- A composite soil contamination index, normalised to [0, 1]. Higher is more contaminated. The shipped graph declares the parameter with the placeholder; this corrects it to the index's own scale.
- `solar_irradiance_multiplier` unit='1' def=0.5 -- Solar irradiance multiplier
- `solar_pv_land_constraint` unit=None def=500000.0 -- Land available for solar
- `solar_pv_max_build` unit=None def=500000.0 -- Maximum annual solar build
- `solar_thermal_capacity` unit=None def=500000.0 -- Solar thermal capacity
- `solvency_capital_ratio` unit='1' def=1.6 -- Eligible own funds as a share of the required solvency capital. The prudential floor is 1.0; markets target 1.5–2.0. The shipped graph carries no such parameter and this one is declared because the solvency test is the insurance equivalent of the DSCR floor.
- `sox_emissions` unit=None def=500000.0 -- SOx emissions
- `spare_parts_availability` unit='1' def=0.8 -- Share of required spares available at the time they are needed. A share.
- `spare_parts_inventory` unit=None def=500000.0 -- Spare parts
- `spare_parts_lead_time` unit=None def=500000.0 -- Lead time
- `spatial_clustering` unit=None def=500000.0 -- Spatial clustering
- `spatial_resolution` unit=None def=500000.0 -- Spatial resolution
- `ssp_pathway` unit=None def=500000.0 -- Shared Socioeconomic Pathway
- `stakeholder_engagement_plan` unit=None def=500000.0 -- SEP
- `stamp_duty` unit='1' def=0.02 -- Stamp duty on property transfer, as a share of the transaction value. A share.
- `startup_cost_coal` unit=None def=500000.0 -- Coal start-up cost
- `startup_cost_gas` unit=None def=500000.0 -- Gas start-up cost
- `step_in_rights` unit=None def=500000.0 -- Step-in rights
- `stochastic_scenarios` unit=None def=500000.0 -- Stochastic scenarios
- `storage_capacity_mw` unit='MW' def=800.0 -- Battery, pumped hydro and thermal storage, at their power rating. Not a Generator in the network, so it counts toward neither firm nor VRE capacity -- the reserve margin is a nameplate adequacy criterion and counting a battery's rating as firm is a modelling choice this graph does not make.
- `storage_dispatch_enabled` unit='1' def=1.0 -- Corrected from float to bool.
- `storage_duration_curve` unit=None def=500000.0 -- Storage energy-to-power ratio
- `storm_surge` unit=None def=500000.0 -- Storm surge
- `strategic_bidding` unit=None def=500000.0 -- Strategic bidding
- `strategic_reserves` unit=None def=500000.0 -- Strategic reserves
- `supply_chain_concentration` unit='1' def=2500.0 -- Herfindahl-Hirschman Index of supplier concentration, bounded in [0, 10000]. The shipped [0, 1e6] admitted values a hundred times the index's maximum, which is why a monopoly supplier would have registered as a diversified market.
- `synthetic_fuel_share_aviation` unit='1' def=0.05 -- Share of aviation fuel that is synthetic. A share.
- `synthetic_fuel_share_shipping` unit='1' def=0.05 -- Share of shipping fuel that is green. A share.
- `tariff_structure` unit=None def=500000.0 -- Tariff design
- `tariff_transparency` unit=None def=500000.0 -- Tariff transparency
- `tax_holiday_conditions` unit=None def=500000.0 -- Conditions for holiday
- `tax_incentive_zones` unit=None def=500000.0 -- Special economic zones
- `tax_incentives` unit=None def=500000.0 -- Tax incentives for renewables
- `temperature_increase` unit=None def=500000.0 -- Temperature increase
- `temperature_target` unit=None def=500000.0 -- Temperature target
- `temporal_aggregation` unit=None def=500000.0 -- Temporal aggregation
- `temporal_clustering` unit=None def=500000.0 -- Temporal clustering
- `temporal_resolution` unit=None def=500000.0 -- Temporal resolution
- `temporary_camp_load` unit=None def=500000.0 -- Refugee camp load
- `terrorism_risk` unit=None def=500000.0 -- Terrorism risk
- `thermal_storage_capacity` unit='MWh' def=0.0 -- Installed thermal storage capacity, chosen by the optimiser. Same role correction.
- `thin_capitalisation_limit` unit='1' def=1.5 -- The debt-to-equity ceiling above which interest deductibility is limited. A ratio; the sample's jurisdictions range from 1.5:1 to 4:1.
- `thin_capitalisation_rules` unit=None def=500000.0 -- Thin cap rules
- `tidal_range_capacity` unit=None def=500000.0 -- Tidal range capacity
- `time_horizon` unit='years' def=25.0 -- Time horizon
- `topology_switching_enabled` unit='1' def=1.0 -- Corrected from float to bool. The parameter is on or off; the shipped [0, 1e6] admitted a value 500,000 times the maximum.
- `tourism_load` unit=None def=500000.0 -- Tourism seasonal load
- `trade_agreement` unit=None def=500000.0 -- Trade agreement type
- `trade_flow_parameters` unit=None def=500000.0 -- Trade flows
- `trade_repository` unit=None def=500000.0 -- Trade repository
- `traditional_land_use` unit=None def=500000.0 -- Traditional use
- `transboundary_water_constraint` unit=None def=500000.0 -- Transboundary water limit
- `transfer_pricing_rules` unit=None def=500000.0 -- Transfer pricing
- `transmission_capacity_factor` unit='1' def=0.5 -- Transmission utilisation
- `transmission_cost_multiplier` unit='1' def=1.0 -- Scaling factor applied to a reference transmission cost. Not a share — a multiplier above 1.0 is admissible (harder terrain, higher labour costs) and one below 1.0 is admissible (competitive tender). Shipped as a share, which refused every scenario with above-reference costs.
- `transmission_detail` unit=None def=500000.0 -- Transmission detail
- `transmission_lead_time` unit=None def=500000.0 -- Transmission construction time
- `transport_logistics` unit=None def=500000.0 -- Transport logistics
- `tsam_segments` unit=None def=500000.0 -- TSAM segments
- `unbundling_status` unit=None def=500000.0 -- Utility unbundling
- `undrip_compliance` unit=None def=500000.0 -- UNDRIP
- `union_agreements` unit=None def=500000.0 -- Union agreements
- `unit_commitment` unit='1' def=1.0 -- Whether the dispatch model enforces unit commitment. A boolean.
- `value_of_lost_load` unit=None def=500000.0 -- Value of lost load
- `vcs_methodologies` unit=None def=500000.0 -- VCS
- `virtual_bidding` unit=None def=500000.0 -- Virtual bidding
- `voc_emissions` unit=None def=500000.0 -- VOC emissions
- `voltage_optimisation_enabled` unit='1' def=1.0 -- Corrected from float to bool.
- `vulnerability_index` unit='1' def=0.5 -- Composite index of exposure, sensitivity and adaptive capacity, normalised to [0, 1]. Higher is more vulnerable. Range is the index's construction.
- `vulnerable_customer_protection` unit=None def=500000.0 -- Vulnerable customers
- `wage_levels_by_sector` unit=None def=500000.0 -- Wage levels
- `waste_to_energy_capacity` unit=None def=500000.0 -- Waste-to-energy capacity
- `wastewater_treatment_load` unit=None def=500000.0 -- Wastewater treatment energy
- `water_availability` unit=None def=500000.0 -- Water availability multiplier
- `water_pollution_load` unit=None def=500000.0 -- Pollution load
- `water_pumping_load` unit=None def=500000.0 -- Water utility pumping
- `water_quality_impact` unit=None def=500000.0 -- Water quality
- `water_quality_index` unit='1' def=0.6 -- A composite water quality index, normalised to [0, 1]. Higher is cleaner.
- `water_stress_index` unit='1' def=0.4 -- Ratio of water withdrawal to renewable freshwater supply, expressed as a share. Higher is more stressed. Range is the index's construction.
- `wave_energy_converter_type` unit=None def=500000.0 -- Wave energy converter type
- `weather_derivatives` unit='1' def=500000.0 -- FIRM-SPECIFIC. The notional of a weather derivative depends on the exposure it hedges. Not corrected.
- `wildfire_risk` unit=None def=500000.0 -- Wildfire risk
- `willingness_to_pay` unit=None def=500000.0 -- WTP
- `wind_offshore_platform` unit=None def=500000.0 -- Platform type
- `wind_speed_multiplier` unit='1' def=0.5 -- Wind speed multiplier
- `withholding_tax_dividends` unit='1' def=0.1 -- Withholding tax rate on dividends. Bounded by the sample's double-tax treaties, which cap the rate for treaty partners.
- `withholding_tax_interest` unit='1' def=0.1 -- Withholding tax rate on interest. Same shape as dividend WHT.
- `work_management_systems` unit=None def=500000.0 -- WMS
- `worker_grievance_mechanism` unit=None def=500000.0 -- Grievance mechanism
- `workshop_capacity` unit=None def=500000.0 -- Workshop capacity
- `world_bank_esf` unit=None def=500000.0 -- World Bank ESF
