# ALEA: Comprehensive Parameter-Equation Relationship Table

## The Definitive Linkage Reference for All 784 Parameters

**Format**: Each row gives the parameter, its definition, the equation system(s) it participates in, and the specific equations that connect it to other parameters. Equations are identified by their system and role (as input, as determined variable, or as a constraint variable).

**Notation**:
- `→` = the parameter determines or drives
- `←` = the parameter is determined by
- `↔` = bidirectional or joint determination
- System names refer to the 20 equation systems defined in the PRG specification

---

## CATEGORY 1: DEMAND-SIDE (43 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 1.1 | `demand_growth_rate` | Annual electricity demand growth rate | Demand-Side | → `demand_t` via logistic growth; → `total_demand`; ↔ `gdp_growth_rate` (elasticity); affects all downstream |
| 1.2 | `demand_growth_profile` | Shape of growth curve | Demand-Side | Determines functional form of → `demand_t`; interacts with `demand_growth_start_year`, `demand_growth_end_year` |
| 1.3 | `demand_growth_start_year` | Year growth trajectory begins | Demand-Side | Temporal anchor for → `demand_t`; ↔ `scenario_start_year` |
| 1.4 | `demand_growth_end_year` | Year growth trajectory ends | Demand-Side | Temporal anchor for → `demand_t`; ↔ `planning_horizon` |
| 1.5 | `peak_demand_multiplier` | Scaling factor for peak demand (enters as `1 + m`, neutral 0.0) | Demand-Side, Reserve Margin | → `peak_demand_shifted_mw` |
| 1.6 | `load_factor_override` | Override default load factor | Demand-Side | → `peak_demand` via load_shape; ↔ `demand_t` shape |
| 1.7 | `industrial_demand_share` | Share of demand from industry | Demand-Side, Sector Coupling | → `industrial_demand`; ← `industrialisation_rate`; ↔ `mining_demand_growth`, `data_centre_demand` |
| 1.8 | `residential_demand_share` | Share of demand from households | Demand-Side | → `residential_demand`; ← `population_growth_rate`; ↔ `electrification_rate_target` |
| 1.9 | `commercial_demand_share` | Share of demand from commercial | Demand-Side | → `commercial_demand`; ← `gdp_growth_rate` |
| 1.10 | `agricultural_demand_share` | Share of demand from agriculture | Demand-Side | → `agricultural_demand`; ↔ `irrigation_pumping_demand` |
| 1.11 | `mining_demand_growth` | Additional mining load growth | Demand-Side, Sector Coupling | → `mining_load`; ↔ `mining_electrification`, `mining_haulage` |
| 1.12 | `data_centre_demand` | New data centre load | Demand-Side | = `data_centre_it_load_mw` × `data_centre_pue`; → `data_centre_load_twh`; ↔ `industrial_demand_share` |
| 1.13 | `desalination_demand` | Desalination electricity demand | Demand-Side, Water-Energy Nexus | → `desalination_load`; ↔ `desalination_capacity`, `desalination_energy` |
| 1.14 | `hydrogen_production_demand` | Electricity for hydrogen production | Demand-Side, Sector Coupling | → `hydrogen_electricity_demand`; ↔ `electrolyser_capacity`, `hydrogen_export_volume` |
| 1.15 | `demand_response_potential` | Share of demand that is flexible | Demand-Side, Demand-Supply Equilibrium | → `flexible_demand`; ↔ `demand_response_capacity`, `time_of_use_tariff_adoption` |
| 1.16 | `demand_response_cost` | Cost of demand response | Demand-Side, Cost Accounting | → `total_cost` via DR opex; ↔ `demand_response_potential` |
| 1.17 | `load_shifting_capability` | Hours of load shifting possible | Demand-Side | Constrains → `load_shifting_optimisation`; ↔ `interruptible_load_share` |
| 1.18 | `interruptible_load_share` | Share of load that can be curtailed | Demand-Side, Reliability | → `curtailable_load`; ↔ `value_of_lost_load` |
| 1.19 | `smart_metering_penetration` | Smart meter coverage | Demand-Side | Enables → `demand_response_potential`; ← `ami_infrastructure` |
| 1.20 | `time_of_use_tariff_adoption` | ToU tariff adoption rate | Demand-Side, Demand-Supply Equilibrium | → `demand_shift`; ← `tariff_structure` |
| 1.21 | `electrification_rate_target` | Target electrification rate | Demand-Side, Affordability | → `total_demand`; ← `electrification_timeline`; ↔ `grid_extension_rate`, `mini_grid_deployment`, `solar_home_system_deployment` |
| 1.22 | `electrification_timeline` | Year to reach target | Demand-Side | Temporal anchor; ↔ `electrification_rate_target` |
| 1.23 | `grid_extension_rate` | Annual grid connection rate | Demand-Side, Transmission | → `grid_connections`; ← `distribution_capex_per_connection`; ↔ `electrification_rate_target` |
| 1.24 | `mini_grid_deployment` | Mini-grid capacity added | Demand-Side, Sector Coupling | → `mini_grid_capacity`; ← `mini_grid_cost`, `mini_grid_subsidies` |
| 1.25 | `solar_home_system_deployment` | SHS units added | Demand-Side | → `shs_capacity`; ← `shs_cost`, `shs_subsidies` |
| 1.26 | `cooking_lpg_penetration` | LPG cooking access | Demand-Side, Sector Coupling | → `lpg_demand`; ← `lpg_subsidies` |
| 1.27 | `clean_cooking_target` | Clean cooking access target | Demand-Side, Policy | → `clean_cooking_access`; ↔ `cooking_lpg_penetration` |
| 1.28 | `heat_pump_adoption` | Heat pump penetration | Demand-Side, Sector Coupling | → `heat_pump_load`; ← `heat_pump_cop` |
| 1.29 | `electric_vehicle_adoption` | EV share of vehicle stock | Demand-Side, Sector Coupling | → `ev_load`; ← `ev_share_new_sales`; ↔ `v2g_adoption` |
| 1.30 | `v2g_adoption` | V2G-capable EV share | Demand-Side, Sector Coupling | → `v2g_capacity`; ↔ `electric_vehicle_adoption` |
| 1.31 | `rooftop_solar_adoption` | Rooftop solar penetration | Demand-Side, Renewables | → `rooftop_pv_capacity`; ← `solar_pv_cost` |
| 1.32 | `battery_storage_adoption` | Behind-the-meter battery penetration | Demand-Side, Storage | → `btm_battery_capacity`; ← `battery_cost` |
| 1.33 | `industrial_electrification` | Industrial process electrification | Demand-Side, Sector Coupling | → `industrial_load`; ← `industrial_heat_electrification` |
| 1.34 | `agricultural_irrigation_load` | Irrigation pumping load | Demand-Side, Water-Energy Nexus | → `irrigation_demand`; ↔ `irrigation_pumping_demand` |
| 1.35 | `post_harvest_processing_load` | Post-harvest processing load | Demand-Side | → `processing_demand`; ← `agricultural_demand_share` |
| 1.36 | `cold_storage_load` | Cold chain energy demand | Demand-Side | → `cold_chain_demand`; ← `healthcare_cost_per_case` |
| 1.37 | `fishing_community_load` | Coastal fishing load | Demand-Side | → `fishing_demand` |
| 1.38 | `tourism_load` | Tourism seasonal load | Demand-Side | → `tourism_demand`; ← `gdp_growth_rate` |
| 1.39 | `construction_load` | Temporary construction load | Demand-Side | → `construction_demand`; ← `industrialisation_rate` |
| 1.40 | `temporary_camp_load` | Refugee camp load | Demand-Side, Humanitarian | → `camp_demand`; ← `population_growth_rate` |
| 1.41 | `emergency_shelter_load` | Emergency shelter load | Demand-Side | → `shelter_demand` |
| 1.42 | `water_pumping_load` | Water utility pumping | Demand-Side, Water-Energy Nexus | = `water_served_population` × `water_use_per_capita_lpd` × `water_pumping_intensity_kwh_per_m3` × 365 / 1e6; ← `water_access_share`; ↔ `irrigation_pumping_demand` |
| 1.43 | `wastewater_treatment_load` | Wastewater treatment energy | Demand-Side, Water-Energy Nexus | → `treatment_demand`; ← `water_pollution_load` |

---

## CATEGORY 2: SUPPLY-SIDE / GENERATION (83 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 2.1 | `coal_capacity` | Installed coal capacity | Energy Balance, Cost Accounting | → `generation_coal`; ← `coal_new_build`, `coal_retirement_schedule`; ↔ `coal_eaf`; ← `carbon_price` |
| 2.2 | `coal_eaf` | Coal energy availability factor | Energy Balance | → `available_coal_capacity`; ← `forced_outage_rate_coal`; ↔ `maintenance_schedule` |
| 2.3 | `coal_retirement_schedule` | Coal retirement years | Cost Accounting, Policy | ← `carbon_price`, `carbon_price_coal_retirement_consistency`; → `coal_retirement_rate` |
| 2.4 | `coal_retirement_rate` | Annual coal retirement | Cost Accounting | ← `coal_retirement_schedule`, `coal_capacity` |
| 2.5 | `coal_new_build` | New coal capacity allowed | Cost Accounting, Policy | → `coal_capacity`; ← `carbon_price`, `coal_retirement_schedule` |
| 2.6 | `coal_ccs_adoption` | Coal with CCS share | Emissions, Cost Accounting | → `coal_emissions_reduction`; ← `carbon_price`, `industrial_ccus_share` |
| 2.7 | `gas_capacity` | Installed gas capacity | Energy Balance | → `generation_gas`; ← `gas_new_build`; ↔ `gas_eaf` |
| 2.8 | `gas_eaf` | Gas energy availability factor | Energy Balance | → `available_gas_capacity`; ← `forced_outage_rate_gas` |
| 2.9 | `gas_new_build` | New gas capacity allowed | Cost Accounting | → `gas_capacity`; ← `carbon_price` |
| 2.10 | `gas_ccs_adoption` | Gas with CCS share | Emissions, Cost Accounting | → `gas_emissions_reduction`; ← `carbon_price` |
| 2.11 | `oil_capacity` | Installed oil capacity | Energy Balance | → `generation_oil`; ↔ `oil_eaf` |
| 2.12 | `oil_eaf` | Oil energy availability factor | Energy Balance | → `available_oil_capacity` |
| 2.13 | `nuclear_capacity` | Installed nuclear capacity | Energy Balance | → `generation_nuclear`; ↔ `nuclear_lead_time` |
| 2.14 | `nuclear_new_build` | New nuclear capacity | Cost Accounting | → `nuclear_capacity` |
| 2.15 | `nuclear_lead_time` | Nuclear construction lead time | Temporal | Constrains → `nuclear_capacity`; ↔ `construction_period` |
| 2.16 | `solar_pv_capacity` | Installed solar PV capacity | Energy Balance, Cost Accounting | → `generation_solar`; ← `solar_pv_max_build`, `solar_pv_land_constraint`; ↔ `solar_pv_cost` |
| 2.17 | `solar_pv_capacity_factor` | Solar PV capacity factor | Energy Balance, Cost Accounting | → `solar_effective_capacity_factor`, `solar_pv_capacity_factor_at_vintage`, `lcoe_solar_usd_per_mwh`, `lace_solar_pv_usd_per_mwh` |
| 2.18 | `solar_pv_cost` | Solar PV capital cost | Cost Accounting, Learning | → `total_cost`; ← `solar_pv_learning_rate`; ↔ `solar_pv_capacity` |
| 2.19 | `solar_pv_learning_rate` | Annual cost reduction | Learning | → `solar_pv_cost`; ← `cumulative_capacity` |
| 2.20 | `solar_pv_max_build` | Maximum annual solar build | Investment | Constrains → `solar_pv_capacity` |
| 2.21 | `solar_pv_land_constraint` | Land available for solar | Investment | Constrains → `solar_pv_capacity`; ← `land_availability`, `protected_areas` |
| 2.22 | `wind_onshore_capacity` | Installed onshore wind | Energy Balance | → `generation_wind_onshore`; ← `wind_onshore_cost` |
| 2.23 | `wind_onshore_cost` | Onshore wind capital cost | Cost Accounting | → `total_cost`; ← `wind_onshore_learning_rate` |
| 2.24 | `wind_offshore_capacity` | Installed offshore wind | Energy Balance | → `generation_wind_offshore`; ← `wind_offshore_cost` |
| 2.25 | `wind_offshore_cost` | Offshore wind capital cost | Cost Accounting | → `total_cost` |
| 2.26 | `wind_offshore_platform` | Platform type | Cost Accounting | → `wind_offshore_cost` |
| 2.27 | `hydro_capacity` | Installed hydropower | Energy Balance | → `generation_hydro`; ↔ `hydro_reservoir_level` |
| 2.28 | `hydro_capacity_factor` | Hydro capacity factor | Energy Balance | ← `capacity_factor_hydro` (alias; it is derived, and drives nothing) |
| 2.29 | `hydro_new_build` | New hydro capacity | Cost Accounting | → `hydro_capacity` |
| 2.30 | `hydro_reservoir_level` | Initial reservoir level | Energy Balance | → `generation_hydro`; ← `hydro_inflow_year`; ↔ `drought_severity` |
| 2.31 | `hydro_drought_multiplier` | Drought impact multiplier | Energy Balance, Water-Energy Nexus | → `hydro_effective_capacity_factor` |
| 2.32 | `geothermal_capacity` | Installed geothermal | Energy Balance | → `generation_geothermal`; ← `geothermal_drilling_success` |
| 2.33 | `geothermal_cost` | Geothermal capital cost | Cost Accounting | → `total_cost` |
| 2.34 | `geothermal_drilling_success` | Drilling success rate | Cost Accounting | → `geothermal_capacity`; ← `geothermal_cost` |
| 2.35 | `biomass_capacity` | Installed biomass capacity | Energy Balance | → `generation_biomass`; ← `biomass_sustainability_limit` |
| 2.36 | `biomass_feedstock_cost` | Biomass feedstock cost | Cost Accounting | → `total_cost`; ← `biomass_capacity` |
| 2.37 | `biomass_sustainability_limit` | Maximum sustainable biomass | Constraint | Constrains → `biomass_capacity`; ← `land_availability` |
| 2.38 | `csp_capacity` | Installed CSP capacity | Energy Balance | → `generation_csp`; ← `csp_storage_hours` |
| 2.39 | `csp_storage_hours` | CSP thermal storage | Energy Balance | → `dispatch_csp`; ← `solar_irradiance_multiplier` |
| 2.40 | `marine_wave_capacity` | Installed wave capacity | Energy Balance | → `generation_wave`; ← `marine_wave_cost` |
| 2.41 | `marine_tidal_capacity` | Installed tidal capacity | Energy Balance | → `generation_tidal`; ← `marine_tidal_cost` |
| 2.42 | `marine_otec_capacity` | Installed OTEC capacity | Energy Balance | → `generation_otec`; ← `marine_otec_cost` |
| 2.43 | `battery_capacity` | Installed battery capacity | Energy Balance, Storage | → `storage_dispatch`; ← `battery_cost`, `battery_duration` |
| 2.44 | `battery_duration` | Battery duration | Storage | → `battery_energy_capacity`; ↔ `battery_capacity` |
| 2.45 | `battery_cost` | Battery capital cost | Cost Accounting, Learning | → `total_cost`; ← `battery_learning_rate` |
| 2.46 | `battery_learning_rate` | Annual cost reduction | Learning | → `battery_cost`; ← `cumulative_battery_capacity` |
| 2.47 | `battery_round_trip_efficiency` | Round-trip efficiency | Storage | → `storage_losses`; → `battery_dispatch` |
| 2.48 | `phs_capacity` | Pumped hydro storage | Storage | → `phs_dispatch`; ← `phs_cost`, `phs_duration` |
| 2.49 | `phs_duration` | PHS duration | Storage | → `phs_energy_capacity`; ↔ `phs_capacity` |
| 2.50 | `phs_cost` | PHS capital cost | Cost Accounting | → `total_cost` |
| 2.51 | `hydrogen_storage_capacity` | Hydrogen storage | Sector Coupling | → `hydrogen_storage_dispatch`; ← `hydrogen_storage_type` |
| 2.52 | `hydrogen_storage_cost` | Hydrogen storage cost | Cost Accounting | → `total_cost`; ← `hydrogen_storage_type` |
| 2.53 | `thermal_storage_capacity` | Thermal storage | Sector Coupling | → `thermal_storage_dispatch`; ↔ `csp_storage_hours` |
| 2.54 | `thermal_storage_duration` | Thermal storage duration | Sector Coupling | → `thermal_energy_capacity`; ↔ `thermal_storage_capacity` |
| 2.55 | `gravity_storage_capacity` | Gravity storage | Storage | → `gravity_dispatch` |
| 2.56 | `compressed_air_capacity` | Compressed air storage | Storage | → `caes_dispatch`; ← `compressed_air_cost` |
| 2.57 | `flywheel_capacity` | Flywheel storage | Storage | → `flywheel_dispatch`; ← `flywheel_cost` |
| 2.58 | `storage_duration_curve` | Storage energy-to-power ratio | Storage | → `storage_energy_capacity`; ↔ `battery_duration` |
| 2.59 | `min_stable_level_coal` | Coal minimum stable level | Unit Commitment | Constrains → `generation_coal`; ↔ `ramp_rate_coal` |
| 2.60 | `min_stable_level_gas` | Gas minimum stable level | Unit Commitment | Constrains → `generation_gas`; ↔ `ramp_rate_gas` |
| 2.61 | `ramp_rate_coal` | Coal ramp rate | Unit Commitment | Constrains → `generation_coal`; ↔ `min_up_time_coal` |
| 2.62 | `ramp_rate_gas` | Gas ramp rate | Unit Commitment | Constrains → `generation_gas`; ↔ `min_up_time_coal` |
| 2.63 | `startup_cost_coal` | Coal start-up cost | Cost Accounting, Unit Commitment | → `total_cost`; ← `min_down_time_coal` |
| 2.64 | `startup_cost_gas` | Gas start-up cost | Cost Accounting, Unit Commitment | → `total_cost`; ← `min_down_time_coal` |
| 2.65 | `min_up_time_coal` | Coal minimum up time | Unit Commitment | Constrains → `commitment_coal`; ↔ `min_down_time_coal` |
| 2.66 | `min_down_time_coal` | Coal minimum down time | Unit Commitment | Constrains → `commitment_coal`; ↔ `min_up_time_coal` |
| 2.67 | `forced_outage_rate_coal` | Coal forced outage rate | Outage, Reserve Margin | → `coal_eaf`; → `reserve_margin`; ← `predictive_maintenance_adoption` |
| 2.68 | `forced_outage_rate_gas` | Gas forced outage rate | Outage, Reserve Margin | → `gas_eaf`; → `reserve_margin` |
| 2.69 | `maintenance_schedule` | Planned maintenance timing | Outage | → `coal_eaf`, `gas_eaf`; ← `maintenance_schedule_optimisation` |
| 2.70 | `plant_retirement_age` | Retirement age by technology | Cost Accounting | → `coal_retirement_schedule`, `gas_new_build`; ← `life_extension_possible` |
| 2.71 | `life_extension_possible` | Life extension allowed | Cost Accounting | → `plant_retirement_age`; → `life_extension_cost` |
| 2.72 | `life_extension_cost` | Life extension cost | Cost Accounting | → `total_cost`; ← `life_extension_possible` |
| 2.73 | `tidal_range_capacity` | Tidal range capacity | Energy Balance | → `generation_tidal_range`; ← `marine_tidal_cost` |
| 2.74 | `salinity_gradient_capacity` | Salinity gradient capacity | Energy Balance | → `generation_salinity` |
| 2.75 | `wave_energy_converter_type` | Wave energy converter type | Energy Balance | → `wave_efficiency`; ↔ `marine_wave_capacity` |
| 2.76 | `biogas_capacity` | Biogas capacity | Energy Balance | → `generation_biogas`; ← `biomass_feedstock_cost` |
| 2.77 | `landfill_gas_capacity` | Landfill gas capacity | Energy Balance | → `generation_landfill` |
| 2.78 | `waste_to_energy_capacity` | Waste-to-energy capacity | Energy Balance | → `generation_wte` |
| 2.79 | `pyrolysis_capacity` | Pyrolysis capacity | Energy Balance | → `generation_pyrolysis`; ← `biomass_feedstock_cost` |
| 2.80 | `gasification_capacity` | Gasification capacity | Energy Balance | → `generation_gasification`; ← `biomass_feedstock_cost` |
| 2.81 | `hydrogen_fuel_cell_capacity` | Hydrogen fuel cell capacity | Sector Coupling | → `fuel_cell_dispatch`; ← `hydrogen_price` |
| 2.82 | `small_modular_reactor_capacity` | SMR capacity | Energy Balance | → `generation_smr`; ← `nuclear_lead_time` |
| 2.83 | `fusion_capacity` | Fusion capacity | Energy Balance | → `generation_fusion`; ← `fusion_cost` |

---

## CATEGORY 3: COST (45 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 3.1 | `capex_solar_pv` | Solar PV capital cost | Cost Accounting, Learning | → `total_cost`, `lcoe_solar`; ← `solar_pv_learning_rate` |
| 3.2 | `capex_wind_onshore` | Onshore wind capital cost | Cost Accounting | → `total_cost`, `lcoe_wind_onshore`; ← `wind_onshore_learning_rate` |
| 3.3 | `capex_wind_offshore` | Offshore wind capital cost | Cost Accounting | → `total_cost`, `lcoe_wind_offshore` |
| 3.4 | `capex_hydro` | Hydropower capital cost | Cost Accounting | → `total_cost`, `lcoe_hydro` |
| 3.5 | `capex_geothermal` | Geothermal capital cost | Cost Accounting | → `total_cost`, `lcoe_geothermal` |
| 3.6 | `capex_biomass` | Biomass capital cost | Cost Accounting | → `total_cost`, `lcoe_biomass` |
| 3.7 | `capex_csp` | CSP capital cost | Cost Accounting | → `total_cost`, `lcoe_csp` |
| 3.8 | `capex_coal` | Coal capital cost | Cost Accounting | → `total_cost`, `lcoe_coal`; ← `coal_ccs_adoption` |
| 3.9 | `capex_gas_ccgt` | Gas CCGT capital cost | Cost Accounting | → `total_cost`, `lcoe_gas` |
| 3.10 | `capex_gas_ocgt` | Gas OCGT capital cost | Cost Accounting | → `total_cost`, `lcoe_gas` |
| 3.11 | `capex_nuclear` | Nuclear capital cost | Cost Accounting | → `total_cost`, `lcoe_nuclear` |
| 3.12 | `capex_battery` | Battery capital cost | Cost Accounting | → `total_cost`; ← `battery_learning_rate` |
| 3.13 | `capex_phs` | PHS capital cost | Cost Accounting | → `total_cost`; ← `phs_duration` |
| 3.14 | `capex_hydrogen_electrolyser` | Electrolyser capital cost | Cost Accounting | → `total_cost`, `lcoh`; ← `electrolyser_learning_rate` |
| 3.15 | `capex_transmission` | Transmission line cost | Cost Accounting | → `total_cost`; ← `transmission_cost_multiplier`, `right_of_way_cost` |
| 3.16 | `capex_distribution` | Distribution network cost | Cost Accounting | → `total_cost`; ← `distribution_capex_per_connection` |
| 3.17 | `capex_interconnector` | Cross-border interconnector | Cost Accounting | → `total_cost`; ← `interconnector_capacity` |
| 3.18 | `opex_fixed_solar` | Solar fixed O&M | Cost Accounting | → `total_cost`, `lcoe_solar` |
| 3.19 | `opex_fixed_wind` | Wind fixed O&M | Cost Accounting | → `total_cost`, `lcoe_wind_onshore` |
| 3.20 | `opex_fixed_coal` | Coal fixed O&M | Cost Accounting | → `total_cost`, `lcoe_coal` |
| 3.21 | `opex_fixed_gas` | Gas fixed O&M | Cost Accounting | → `total_cost`, `lcoe_gas` |
| 3.22 | `opex_variable_coal` | Coal variable O&M | Cost Accounting | → `total_cost`, `marginal_cost_coal` |
| 3.23 | `opex_variable_gas` | Gas variable O&M | Cost Accounting | → `total_cost`, `marginal_cost_gas` |
| 3.24 | `opex_variable_battery` | Battery variable O&M | Cost Accounting | → `total_cost` |
| 3.25 | `opex_variable_electrolyser` | Electrolyser variable O&M | Cost Accounting | → `total_cost`, `lcoh` |
| 3.26 | `fuel_cost_coal` | Coal fuel cost | Cost Accounting, Emissions | → `marginal_cost_coal`; ↔ `coal_price` |
| 3.27 | `fuel_cost_gas` | Gas fuel cost | Cost Accounting, Emissions | → `marginal_cost_gas`; ↔ `gas_price` |
| 3.28 | `fuel_cost_oil` | Oil fuel cost | Cost Accounting | → `marginal_cost_oil`; ↔ `oil_price` |
| 3.29 | `fuel_cost_nuclear` | Nuclear fuel cost | Cost Accounting | → `marginal_cost_nuclear`; ↔ `uranium_price` |
| 3.30 | `fuel_cost_biomass` | Biomass fuel cost | Cost Accounting | → `marginal_cost_biomass`; ↔ `biomass_feedstock_cost` |
| 3.31 | `fuel_cost_hydrogen` | Hydrogen fuel cost | Cost Accounting | → `marginal_cost_hydrogen`; ↔ `hydrogen_price` |
| 3.32 | `fuel_price_escalation` | Annual fuel price escalation | Cost Accounting | → `fuel_cost_coal_t`, `fuel_cost_gas_t`; ← `inflation_rate` |
| 3.33 | `fuel_price_volatility` | Fuel price volatility | Stochastic | → `fuel_price_scenario`; ← `exchange_rate_volatility` |
| 3.34 | `discount_rate` | Social discount rate | Financial, Cost Accounting | → `lcoe`, `npv`, `crf`; ← `weighted_average_cost_of_capital` |
| 3.35 | `weighted_average_cost_of_capital` | WACC | Financial | → `discount_rate`; ← `cost_of_equity`, `cost_of_debt`, `debt_equity_ratio`, `corporate_income_tax_rate` |
| 3.36 | `cost_of_equity` | Cost of equity | Financial | → `wacc`; ← `sovereign_risk_premium`, `technology_risk_premium`, `offtake_risk_premium` |
| 3.37 | `cost_of_debt` | Cost of debt | Financial | → `wacc`; ← `interest_rate`, `sovereign_risk_premium` |
| 3.38 | `debt_equity_ratio` | Debt-to-equity ratio | Financial | → `wacc`; ← `gearing_ratio`, `debt_service_coverage_ratio` |
| 3.39 | `carbon_price` | Carbon price | Emissions, Policy | → `carbon_cost`, `coal_capacity`, `gas_capacity`; ↔ `carbon_tax_rate`, `carbon_price_escalation` |
| 3.40 | `carbon_price_escalation` | Annual carbon price increase | Policy | → `carbon_price_t`; ← `carbon_trajectory` |
| 3.41 | `carbon_price_coverage` | Share of emissions covered | Policy | → `carbon_cost`; ← `carbon_tax_coverage` |
| 3.42 | `value_of_lost_load` | Value of lost load | Reliability | → `ens_cost`; ← `affordability_threshold` |
| 3.43 | `reserve_margin_requirement` | Minimum reserve margin | Reserve Margin | → `required_capacity`; ← `planning_reserve_margin`, `forced_outage_rate` |
| 3.44 | `planning_reserve_margin` | Planning reserve margin | Reserve Margin | → `reserve_margin_requirement`; ← `demand_growth_rate` |
| 3.45 | `inertia_requirement` | Minimum system inertia | Inertia | → `required_synchronous_capacity`; ← `renewable_penetration_limit` |

---

## CATEGORY 4: POLICY & REGULATORY (42 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 4.1 | `carbon_tax_rate` | Carbon tax rate | Policy, Emissions | → `carbon_price`; ↔ `ets_cap` |
| 4.2 | `carbon_tax_start_year` | Year carbon tax begins | Policy | Temporal anchor; ↔ `carbon_trajectory` |
| 4.3 | `carbon_tax_coverage` | Sectors covered by carbon tax | Policy | → `carbon_price_coverage`; ↔ `carbon_tax_rate` |
| 4.4 | `ets_enabled` | Emissions trading system | Policy | → `carbon_price`; ↔ `carbon_tax_rate` |
| 4.5 | `ets_cap` | ETS emissions cap | Policy, Emissions | → `carbon_price`; ← `carbon_trajectory` |
| 4.6 | `ets_cap_reduction_rate` | Annual cap reduction | Policy | → `ets_cap_t`; ← `net_zero_year` |
| 4.7 | `carbon_border_adjustment` | CBAM exposure | Policy, Trade | → `export_competitiveness`; ← `cbam_price` |
| 4.8 | `cbam_price` | CBAM certificate price | Policy, Trade | → `carbon_border_adjustment`; ↔ `carbon_price` |
| 4.9 | `article_6_credits` | Paris Agreement Article 6 credits | Policy, Carbon | → `carbon_revenue`; ↔ `voluntary_carbon_market` |
| 4.10 | `voluntary_carbon_market` | VCM participation | Policy, Carbon | → `carbon_revenue`; ↔ `article_6_credits` |
| 4.11 | `renewable_target` | Renewable energy target | Policy, Energy Balance | → `required_renewable_capacity`; ← `re_target_carrier` |
| 4.12 | `renewable_target_year` | Year to reach target | Policy | Temporal anchor; ↔ `net_zero_year` |
| 4.13 | `re_target_carrier` | Which renewables count | Policy | → `renewable_target`; ↔ `renewable_capacity` |
| 4.14 | `feed_in_tariff` | Feed-in tariff rate | Policy, Market | → `renewable_revenue`; ← `fit_duration`, `fit_capacity_cap` |
| 4.15 | `fit_duration` | FiT contract duration | Policy | → `feed_in_tariff`; ← `ppa_duration` |
| 4.16 | `fit_capacity_cap` | FiT capacity cap | Policy | → `feed_in_tariff`; ↔ `auction_volume` |
| 4.17 | `auction_mechanism` | Renewable auction type | Policy, Market | → `auction_price`; ↔ `auction_volume` |
| 4.18 | `auction_volume` | Annual auction volume | Policy, Market | → `auction_price`; ← `renewable_target` |
| 4.19 | `auction_price_cap` | Auction price ceiling | Policy | → `auction_price`; ↔ `auction_volume` |
| 4.20 | `tax_incentives` | Tax incentives for renewables | Policy, Tax | → `after_tax_cost`; ↔ `accelerated_depreciation` |
| 4.21 | `accelerated_depreciation` | Accelerated depreciation | Policy, Tax | → `after_tax_cost`; ↔ `tax_incentives` |
| 4.22 | `import_duty_exemption` | Import duty exemption | Policy, Tax | → `after_tax_cost`; ↔ `local_content_requirement` |
| 4.23 | `local_content_requirement` | Local content requirement | Policy, Employment | → `local_employment`; ↔ `import_duty_exemption` |
| 4.24 | `market_structure` | Electricity market structure | Market Design | → `market_pricing_mechanism`; ↔ `unbundling_status` |
| 4.25 | `unbundling_status` | Utility unbundling | Market Design | → `market_structure`; ↔ `retail_competition` |
| 4.26 | `wheeling_charges` | Transmission wheeling charge | Market Design, Cost | → `transmission_cost`; ↔ `distribution_wheeling_charges` |
| 4.27 | `distribution_wheeling_charges` | Distribution wheeling charge | Market Design, Cost | → `distribution_cost`; ↔ `wheeling_charges` |
| 4.28 | `cross_subsidy_level` | Cross-subsidy in tariffs | Policy, Affordability | → `effective_tariff`; ← `lifeline_tariff`, `social_tariff` |
| 4.29 | `tariff_structure` | Tariff design | Policy, Affordability | → `effective_tariff`; ← `time_of_use_tariff_adoption` |
| 4.30 | `regulated_tariff_rate` | Regulated tariff | Policy, Affordability | → `consumer_cost`; ← `tariff_structure`, `tariff_indexation` |
| 4.31 | `tariff_indexation` | Tariff indexation | Policy, Affordability | → `regulated_tariff_rate_t`; ← `inflation_rate` |
| 4.32 | `ppa_guarantees` | Government PPA guarantees | Policy, Contract | → `ppa_price`; ↔ `contract_for_difference` |
| 4.33 | `contract_for_difference` | CfD mechanism | Policy, Contract | → `ppa_price`; ↔ `ppa_guarantees` |
| 4.34 | `capacity_market` | Capacity market | Policy, Market | → `capacity_price`; ↔ `ancillary_services_market` |
| 4.35 | `capacity_price` | Capacity market clearing price | Policy, Market | → `producer_revenue`; ← `capacity_market` |
| 4.36 | `ancillary_services_market` | Ancillary services market | Policy, Market | → `ancillary_revenue`; ↔ `capacity_market` |
| 4.37 | `fossil_fuel_subsidies` | Fossil fuel subsidies | Policy, Cost | → `effective_fuel_cost`; ↔ `renewable_subsidies` |
| 4.38 | `renewable_subsidies` | Renewable energy subsidies | Policy, Cost | → `effective_renewable_cost`; ↔ `fossil_fuel_subsidies` |
| 4.39 | `electricity_subsidies` | Consumer electricity subsidies | Policy, Affordability | → `effective_tariff`; ← `energy_poverty_rate` |
| 4.40 | `lpg_subsidies` | LPG subsidy | Policy, Affordability | → `lpg_price`; ↔ `cooking_lpg_penetration` |
| 4.41 | `mini_grid_subsidies` | Mini-grid capital subsidy | Policy, Cost | → `mini_grid_cost`; ← `mini_grid_deployment` |
| 4.42 | `shs_subsidies` | Solar home system subsidy | Policy, Cost | → `shs_cost`; ← `solar_home_system_deployment` |

---

## CATEGORY 5: TRANSMISSION & GRID (24 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 5.1 | `transmission_expansion_allowed` | Allow transmission expansion | Energy Balance | Constrains → `transmission_capacity`; ↔ `transmission_lead_time` |
| 5.2 | `transmission_cost_multiplier` | Transmission cost multiplier | Cost Accounting | → `capex_transmission`; ← `right_of_way_cost` |
| 5.3 | `transmission_loss_factor` | Average transmission loss | Energy Balance | → `transmission_losses`; ↔ `distribution_loss_factor` |
| 5.4 | `transmission_capacity_factor` | Transmission utilisation | Energy Balance | → `transmission_flow_limit`; ← `line_capacity_override` |
| 5.5 | `hvdc_share` | Share of HVDC in new lines | Cost Accounting | → `transmission_capex`; ↔ `ac_voltage_limit` |
| 5.6 | `ac_voltage_limit` | Maximum AC voltage | Cost Accounting | → `transmission_capex`; ↔ `hvdc_share` |
| 5.7 | `transmission_lead_time` | Transmission construction time | Temporal | Constrains → `transmission_capacity`; ↔ `construction_period` |
| 5.8 | `right_of_way_cost` | Right-of-way cost | Cost Accounting | → `capex_transmission`; ← `land_acquisition_costs` |
| 5.9 | `cross_border_permitting_time` | Cross-border permitting | Temporal | Constrains → `interconnector_capacity`; ↔ `trade_agreement` |
| 5.10 | `distribution_loss_factor` | Distribution losses | Energy Balance | → `distribution_losses`; ↔ `transmission_loss_factor` |
| 5.11 | `distribution_capex_per_connection` | Distribution cost per connection | Cost Accounting | → `capex_distribution`; ← `grid_extension_rate` |
| 5.12 | `grid_connection_cost` | Grid connection cost | Cost Accounting | → `capex_distribution`; ↔ `distribution_capex_per_connection` |
| 5.13 | `mini_grid_cost` | Mini-grid cost | Cost Accounting | → `mini_grid_deployment`; ← `mini_grid_subsidies` |
| 5.14 | `shs_cost` | Solar home system cost | Cost Accounting | → `solar_home_system_deployment`; ← `shs_subsidies` |
| 5.15 | `grid_reliability_target` | Reliability target (SAIDI) | Reliability | Constrains → `interruption_duration`; ↔ `grid_reliability_saifi` |
| 5.16 | `grid_reliability_saifi` | Reliability target (SAIFI) | Reliability | Constrains → `interruption_frequency`; ↔ `grid_reliability_target` |
| 5.17 | `cross_border_trade_allowed` | Allow cross-border trade | Market Design | → `cross_border_flow`; ↔ `interconnector_capacity` |
| 5.18 | `interconnector_capacity` | Interconnector capacity | Energy Balance | → `cross_border_flow`; ← `capex_interconnector` |
| 5.19 | `wheeling_charge_cross_border` | Cross-border wheeling charge | Cost Accounting | → `trade_cost`; ← `trade_agreement` |
| 5.20 | `loss_factor_cross_border` | Cross-border loss factor | Energy Balance | → `trade_losses`; ↔ `transmission_loss_factor` |
| 5.21 | `trade_agreement` | Trade agreement type | Market Design | → `wheeling_charge_cross_border`; ↔ `market_coupling` |
| 5.22 | `market_coupling` | Market coupling | Market Design | → `cross_border_trade_allowed`; ↔ `trade_agreement` |
| 5.23 | `currency_risk_premium` | Currency risk premium | Financial | → `cost_of_debt`; ← `exchange_rate_volatility` |
| 5.24 | `payment_security_required` | Payment security | Financial | → `cost_of_debt`; ↔ `counterparty_risk` |

---

## CATEGORY 6: SECTOR COUPLING (59 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 6.1 | `hydrogen_demand_domestic` | Domestic hydrogen demand | Sector Coupling | → `hydrogen_production_demand`; ← `industrial_heat_demand` |
| 6.2 | `hydrogen_export_volume` | Hydrogen export volume | Sector Coupling, Trade | → `electrolyser_capacity`; ← `hydrogen_export_price` |
| 6.3 | `hydrogen_export_price` | Export price | Sector Coupling, Cost | → `hydrogen_revenue`; ← `lcoh` |
| 6.4 | `electrolyser_capacity` | Electrolyser capacity | Sector Coupling | → `hydrogen_production_demand`; ← `electrolyser_cost` |
| 6.5 | `electrolyser_efficiency` | Electrolyser efficiency | Sector Coupling | → `hydrogen_production_demand`; ↔ `electrolyser_cost` |
| 6.6 | `electrolyser_cost` | Electrolyser capital cost | Cost Accounting | → `lcoh`; ← `electrolyser_learning_rate` |
| 6.7 | `electrolyser_learning_rate` | Annual cost reduction | Learning | → `electrolyser_cost`; ← `cumulative_electrolyser_capacity` |
| 6.8 | `hydrogen_storage_type` | Storage type | Sector Coupling | → `hydrogen_storage_cost`; ↔ `hydrogen_storage_capacity` |
| 6.9 | `hydrogen_storage_capacity` | Storage capacity | Sector Coupling | → `hydrogen_storage_dispatch`; ← `hydrogen_storage_type` |
| 6.10 | `hydrogen_pipeline_capacity` | Pipeline capacity | Sector Coupling | → `hydrogen_pipeline_flow`; ← `hydrogen_pipeline_cost` |
| 6.11 | `hydrogen_pipeline_cost` | Pipeline cost | Cost Accounting | → `lcoh`; ← `hydrogen_pipeline_capacity` |
| 6.12 | `ammonia_export_share` | Share exported as ammonia | Sector Coupling | → `ammonia_production`; ↔ `hydrogen_export_volume` |
| 6.13 | `hydrogen_export_port` | Export port | Sector Coupling | → `hydrogen_pipeline_capacity`; ↔ `port_electrification` |
| 6.14 | `heat_pump_adoption` | Heat pump penetration | Sector Coupling | → `heat_pump_load`; ← `heat_pump_cost` |
| 6.15 | `heat_pump_cop` | Heat pump COP | Sector Coupling | → `heat_pump_load`; ← `temperature_increase` |
| 6.16 | `heat_pump_cost` | Heat pump capital cost | Cost Accounting | → `total_cost`; ↔ `heat_pump_adoption` |
| 6.17 | `district_heating_share` | District heating share | Sector Coupling | → `district_heat_demand`; ← `thermal_storage_capacity` |
| 6.18 | `thermal_storage_capacity` | Thermal storage | Sector Coupling | → `thermal_storage_dispatch`; ↔ `csp_storage_hours` |
| 6.19 | `industrial_heat_demand` | Industrial heat demand | Sector Coupling | → `industrial_load`; ← `industrialisation_rate` |
| 6.20 | `industrial_heat_electrification` | Industrial heat electrification | Sector Coupling | → `industrial_electrification`; ← `heat_pump_adoption` |
| 6.21 | `solar_thermal_capacity` | Solar thermal capacity | Sector Coupling | → `solar_thermal_output`; ← `solar_irradiance_multiplier` |
| 6.22 | `ev_share_new_sales` | EV share of new vehicle sales | Sector Coupling | → `electric_vehicle_adoption`; ← `ev_efficiency` |
| 6.23 | `ev_adoption_timeline` | Year to reach EV share | Sector Coupling | Temporal anchor; ↔ `ev_share_new_sales` |
| 6.24 | `ev_efficiency` | EV efficiency | Sector Coupling | → `ev_load`; ↔ `ev_battery_size` |
| 6.25 | `ev_battery_size` | Average EV battery size | Sector Coupling | → `ev_load`, `v2g_capacity`; ↔ `v2g_adoption` |
| 6.26 | `v2g_adoption` | V2G-capable EV share | Sector Coupling | → `v2g_capacity`; ↔ `electric_vehicle_adoption` |
| 6.27 | `hydrogen_vehicle_share` | Hydrogen vehicle share | Sector Coupling | → `hydrogen_transport_demand`; ← `hydrogen_price` |
| 6.28 | `synthetic_fuel_share_aviation` | SAF share in aviation | Sector Coupling | → `saf_demand`; ← `aviation_fuel_demand` |
| 6.29 | `synthetic_fuel_share_shipping` | Green shipping fuel share | Sector Coupling | → `green_shipping_demand`; ← `shipping_fuel_demand` |
| 6.30 | `public_transport_share` | Public transport modal share | Sector Coupling | → `public_transport_demand`; ← `urbanisation_rate` |
| 6.31 | `freight_electrification` | Freight electrification | Sector Coupling | → `freight_electricity_demand`; ← `ev_share_new_sales` |
| 6.32 | `steel_production` | Steel production | Sector Coupling, Industry | → `steel_energy_demand`; ← `industrialisation_rate` |
| 6.33 | `steel_h2_dri_share` | H₂-DRI share of steel | Sector Coupling | → `hydrogen_demand_domestic`; ← `hydrogen_price` |
| 6.34 | `steel_scrap_eaf_share` | Scrap-EAF share of steel | Sector Coupling | → `steel_electricity_demand`; ← `steel_production` |
| 6.35 | `cement_production` | Cement production | Sector Coupling, Industry | → `cement_energy_demand`; ← `industrialisation_rate` |
| 6.36 | `cement_ccus_share` | Cement with CCUS | Sector Coupling | → `cement_emissions_reduction`; ← `industrial_ccus_share` |
| 6.37 | `chemicals_ammonia_production` | Ammonia production | Sector Coupling | → `hydrogen_demand_domestic`; ← `industrialisation_rate` |
| 6.38 | `chemicals_green_ammonia_share` | Green ammonia share | Sector Coupling | → `hydrogen_demand_domestic`; ← `hydrogen_price` |
| 6.39 | `mining_electrification` | Mining electrification | Sector Coupling | → `mining_demand_growth`; ← `mining_haulage` |
| 6.40 | `mining_hydrogen_haulage` | Hydrogen haulage in mining | Sector Coupling | → `hydrogen_demand_domestic`; ← `hydrogen_price` |
| 6.41 | `industrial_ccus_share` | Industrial CCUS adoption | Sector Coupling, Emissions | → `industrial_emissions_reduction`; ← `carbon_price` |
| 6.42 | `cooling_water_demand` | Cooling water demand | Water-Energy Nexus | → `total_water_demand`; ← `generation_coal`, `generation_gas` |
| 6.43 | `water_availability` | Water availability multiplier | Water-Energy Nexus | Constrains → `water_availability_m3` (the `water_availability_constraint` bound); `drought_frequency` drives nothing |
| 6.44 | `drought_frequency` | Drought frequency multiplier | Water-Energy Nexus | → nothing: it carries no edge, and no equation names it |
| 6.45 | `drought_severity` | Drought severity multiplier | Water-Energy Nexus | → `hydro_reservoir_level`; ← `ssp_pathway` |
| 6.46 | `desalination_capacity` | Desalination capacity | Water-Energy Nexus | → `desalination_demand`; ← `desalination_energy` |
| 6.47 | `desalination_energy` | Desalination energy intensity | Water-Energy Nexus | → `desalination_demand`; ↔ `desalination_capacity` |
| 6.48 | `irrigation_pumping_demand` | Irrigation pumping demand | Water-Energy Nexus | → `agricultural_irrigation_load`; ← `water_availability` |
| 6.49 | `transboundary_water_constraint` | Transboundary water limit | Water-Energy Nexus | Constrains → `total_water_demand`; ↔ `water_availability` |
| 6.50 | `aviation_fuel_demand` | Aviation fuel demand | Sector Coupling | → `saf_demand`; ← `gdp_growth_rate` |
| 6.51 | `shipping_fuel_demand` | Shipping fuel demand | Sector Coupling | → `green_shipping_demand`; ← `gdp_growth_rate` |
| 6.52 | `railway_electrification` | Railway electrification | Sector Coupling | → `rail_electricity_demand`; ← `ev_share_new_sales` |
| 6.53 | `port_electrification` | Port electrification | Sector Coupling | → `port_electricity_demand`; ← `shipping_fuel_demand` |
| 6.54 | `airport_electrification` | Airport electrification | Sector Coupling | → `airport_electricity_demand`; ← `aviation_fuel_demand` |
| 6.55 | `agricultural_machinery` | Agricultural machinery | Sector Coupling | → `agricultural_electricity_demand`; ← `agricultural_demand_share` |
| 6.56 | `construction_machinery` | Construction machinery | Sector Coupling | → `construction_demand`; ← `industrialisation_rate` |
| 6.57 | `mining_haulage` | Mining haulage | Sector Coupling | → `mining_demand_growth`; ← `mining_electrification` |
| 6.58 | `fishing_vessel_fuel` | Fishing vessel fuel | Sector Coupling | → `fishing_demand`; ← `fishing_community_load` |
| 6.59 | `military_energy_demand` | Military energy demand | Sector Coupling | → `military_load`; ← `geopolitical_risk_index` |

---

## CATEGORY 7: CLIMATE & WEATHER (21 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 7.1 | `ssp_pathway` | Shared Socioeconomic Pathway | Climate | → `temperature_increase`, `drought_frequency`, `drought_severity`; ← `carbon_budget` |
| 7.2 | `temperature_target` | Temperature target | Climate | → `carbon_budget`; ↔ `net_zero_year` |
| 7.3 | `climate_sensitivity` | Climate sensitivity | Climate | → `temperature_increase`; ↔ `carbon_budget` |
| 7.4 | `carbon_budget` | Remaining carbon budget | Climate, Carbon Trajectory | → `carbon_price_escalation`; ← `temperature_target` |
| 7.5 | `emissions_peak_year` | Global emissions peak year | Climate, Carbon Trajectory | → `carbon_trajectory`; ↔ `net_zero_year` |
| 7.6 | `net_zero_year` | Global net-zero year | Climate, Carbon Trajectory | → `carbon_trajectory`; ↔ `emissions_peak_year` |
| 7.7 | `solar_irradiance_multiplier` | Solar irradiance multiplier | Climate, Energy Balance | → `solar_effective_capacity_factor` |
| 7.8 | `wind_speed_multiplier` | Wind speed multiplier | Climate, Energy Balance | → `wind_effective_capacity_factor` |
| 7.9 | `precipitation_multiplier` | Precipitation multiplier | Climate, Water-Energy Nexus | → `hydro_inflow_year`; ← `ssp_pathway` |
| 7.10 | `temperature_increase` | Temperature increase | Climate, Demand-Side | → `cooling_demand`; ← `ssp_pathway`, `climate_sensitivity` |
| 7.11 | `heatwave_frequency` | Heatwave frequency | Climate | → `peak_demand_multiplier`; ← `ssp_pathway` |
| 7.12 | `cold_snap_frequency` | Cold snap frequency | Climate | → `peak_demand_multiplier`; ← `ssp_pathway` |
| 7.13 | `extreme_weather_events` | Extreme weather frequency | Climate, Outage | → `forced_outage_rate`; ← `ssp_pathway` |
| 7.14 | `interannual_variability` | Interannual variability | Climate | → `hydro_capacity_factor` variance; ← `ssp_pathway` |
| 7.15 | `solar_cf_year` | Solar capacity factor year | Climate | → `solar_pv_capacity_factor`; ← `solar_irradiance_multiplier` |
| 7.16 | `wind_cf_year` | Wind capacity factor year | Climate | → `wind_onshore_capacity_factor`; ← `wind_speed_multiplier` |
| 7.17 | `hydro_inflow_year` | Hydro inflow year | Climate, Water-Energy Nexus | → `hydro_capacity_factor`; ← `precipitation_multiplier` |
| 7.18 | `solar_degradation` | Solar degradation | Climate | → `solar_pv_capacity_factor_t`; ← `solar_pv_learning_rate` |
| 7.19 | `wind_degradation` | Wind degradation | Climate | → `wind_onshore_capacity_factor_t`; ← `wind_onshore_learning_rate` |
| 7.20 | `renewable_curtailment_limit` | Maximum curtailment | Climate, Energy Balance | Constrains → `curtailment`; ← `renewable_penetration_limit` |
| 7.21 | `renewable_penetration_limit` | Maximum instantaneous penetration | Climate, Inertia | Constrains → `renewable_share`; ← `inertia_requirement` |

---

## CATEGORY 8: OUTAGE & RESILIENCE (30 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 8.1 | `forced_outage_rate` | Forced outage rate multiplier | Outage, Reserve Margin | → `available_capacity`; ← `extreme_weather_events`, `predictive_maintenance_adoption` |
| 8.2 | `planned_outage_rate` | Planned outage rate | Outage | → `available_capacity`; ← `maintenance_schedule_optimisation` |
| 8.3 | `outage_duration` | Average outage duration | Outage, Reliability | → `ens`; ← `repair_time`, `crew_availability` |
| 8.4 | `outage_frequency` | Outage frequency | Outage, Reliability | → `saifi`; ← `forced_outage_rate` |
| 8.5 | `outage_cause_distribution` | Cause distribution | Outage | → `outage_frequency`; ← `extreme_weather_events` |
| 8.6 | `maintenance_schedule_optimisation` | Optimise maintenance timing | Outage | → `planned_outage_rate`; ← `maintenance_schedule` |
| 8.7 | `predictive_maintenance_adoption` | Predictive maintenance adoption | Outage | → `forced_outage_rate`; ← `asset_condition_index` |
| 8.8 | `spare_parts_availability` | Spare parts availability | Outage | → `repair_time`; ← `spare_parts_inventory` |
| 8.9 | `crew_availability` | Maintenance crew availability | Outage | → `repair_time`; ← `outage_frequency` |
| 8.10 | `reserve_margin` | Operating reserve margin | Reserve Margin | → `required_capacity`; ← `reserve_margin_requirement` |
| 8.11 | `spinning_reserve` | Spinning reserve requirement | Reserve Margin | → `required_spinning_capacity`; ↔ `non_spinning_reserve` |
| 8.12 | `non_spinning_reserve` | Non-spinning reserve | Reserve Margin | → `required_non_spinning_capacity`; ↔ `spinning_reserve` |
| 8.13 | `regulation_reserve` | Regulation reserve | Reserve Margin | → `required_regulation_capacity`; ↔ `spinning_reserve` |
| 8.14 | `inertia_requirement` | System inertia requirement | Inertia | Constrains → `synchronous_capacity`; ← `renewable_penetration_limit` |
| 8.15 | `black_start_capability` | Black start units available | Outage | → `restoration_time`; ← `unit_commitment` |
| 8.16 | `islanding_capability` | Islanding capability | Outage | → `islanded_supply`; ← `microgrid_deployment` |
| 8.17 | `microgrid_deployment` | Microgrid deployment | Outage | → `islanding_capability`; ← `mini_grid_deployment` |
| 8.18 | `demand_response_capacity` | Demand response capacity | Outage, Demand-Side | → `flexible_demand`; ← `demand_response_potential` |
| 8.19 | `transmission_loss_reduction_target` | Loss reduction target | Loss Mitigation | → `required_loss_reduction`; ← `loss_reduction_investment` |
| 8.20 | `loss_reduction_investment` | Investment in loss reduction | Loss Mitigation, Cost | → `transmission_loss_reduction_target`; ← `line_upgrade_budget` |
| 8.21 | `topology_switching_enabled` | Topology switching | Loss Mitigation | → `topology_switching_benefit`; ↔ `phase_shifting_enabled` |
| 8.22 | `phase_shifting_enabled` | Phase shifting transformers | Loss Mitigation | → `phase_shifting_benefit`; ↔ `topology_switching_enabled` |
| 8.23 | `voltage_optimisation_enabled` | Voltage optimisation | Loss Mitigation | → `voltage_optimisation_benefit`; ↔ `reactive_power_requirement` |
| 8.24 | `dg_placement_enabled` | Distributed generation placement | Loss Mitigation | → `dg_placement_benefit`; ← `distributed_generation_capacity` |
| 8.25 | `storage_dispatch_enabled` | Storage dispatch for losses | Loss Mitigation | → `storage_dispatch_benefit`; ← `battery_capacity` |
| 8.26 | `line_upgrade_budget` | Line upgrade budget | Loss Mitigation, Cost | → `loss_reduction_investment`; ← `capex_transmission` |
| 8.27 | `line_outage_start` | When the outage begins | Outage, Energy Balance | Temporal anchor; ↔ `line_outage_end` |
| 8.28 | `line_outage_end` | When the outage ends | Outage, Energy Balance | Temporal anchor; ↔ `line_outage_start` |
| 8.29 | `line_outage_probability` | Probability of outage | Outage | → `line_outage_scenario`; ← `forced_outage_rate` |
| 8.30 | `line_outage_duration` | Expected duration | Outage | → `ens_line`; ↔ `outage_duration` |

---

## CATEGORY 9: MACROECONOMIC (51 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 9.1 | `gdp_growth_rate` | GDP growth rate | Macro, Demand-Side | → `demand_growth_rate`; ← `industrialisation_rate` |
| 9.2 | `gdp_per_capita_growth` | GDP per capita growth | Macro | → `demand_growth_rate`; ← `population_growth_rate` |
| 9.3 | `population_growth_rate` | Population growth rate | Macro, Demand-Side | → `demand_growth_rate`, `residential_demand_share`; ↔ `urbanisation_rate` |
| 9.4 | `urbanisation_rate` | Urbanisation rate | Macro | → `commercial_demand_share`, `public_transport_share`; ↔ `population_growth_rate` |
| 9.5 | `industrialisation_rate` | Industrialisation rate | Macro | → `industrial_demand_share`, `steel_production`, `cement_production`; ↔ `gdp_growth_rate` |
| 9.6 | `exchange_rate_usd_local` | Exchange rate (USD/local) | Macro, Financial | → `import_cost`, `debt_service`; ← `inflation_rate` |
| 9.7 | `exchange_rate_volatility` | Exchange rate volatility | Macro, Financial | → `currency_risk_premium`; ← `inflation_rate` |
| 9.8 | `inflation_rate` | Inflation rate | Macro, Financial | → `tariff_indexation`, `interest_rate`; ← `gdp_growth_rate` |
| 9.9 | `interest_rate` | Central bank interest rate | Macro, Financial | → `cost_of_debt`; ← `inflation_rate` |
| 9.10 | `sovereign_risk_premium` | Sovereign risk premium | Macro, Financial | → `cost_of_equity`, `cost_of_debt`; ← `country_risk_rating` |
| 9.11 | `country_risk_rating` | Country risk rating | Macro, Financial | → `sovereign_risk_premium`; ← `political_stability`, `rule_of_law_index` |
| 9.12 | `oil_price` | Oil price | Macro, Cost | → `fuel_cost_oil`; ← `fuel_price_escalation` |
| 9.13 | `gas_price` | Gas price | Macro, Cost | → `fuel_cost_gas`; ← `fuel_price_escalation` |
| 9.14 | `coal_price` | Coal price | Macro, Cost | → `fuel_cost_coal`; ← `fuel_price_escalation` |
| 9.15 | `lng_price` | LNG price | Macro, Cost | → `gas_price`; ↔ `oil_price` |
| 9.16 | `uranium_price` | Uranium price | Macro, Cost | → `fuel_cost_nuclear`; ↔ `oil_price` |
| 9.17 | `hydrogen_price` | Hydrogen price | Macro, Cost | → `fuel_cost_hydrogen`, `steel_h2_dri_share`; ← `lcoh` |
| 9.18 | `ammonia_price` | Ammonia price | Macro, Cost | → `hydrogen_export_price`; ← `hydrogen_price` |
| 9.19 | `fuel_price_scenario` | Fuel price scenario | Macro, Stochastic | → `oil_price`, `gas_price`, `coal_price`; ← `fuel_price_volatility` |
| 9.20 | `debt_tenor` | Debt tenor | Financial | → `debt_service`; ↔ `loan_life_coverage_ratio` |
| 9.21 | `interest_rate_debt` | Interest rate on debt | Financial | → `cost_of_debt`; ← `interest_rate` |
| 9.22 | `debt_service_coverage_ratio` | Minimum DSCR | Financial | Constrains → `debt_sizing`; ← `cfads` |
| 9.23 | `loan_life_coverage_ratio` | Minimum LLCR | Financial | Constrains → `debt_sizing`; ← `cfads` |
| 9.24 | `gearing_ratio` | Debt-to-equity ratio | Financial | → `debt_equity_ratio`; ← `debt_service_coverage_ratio` |
| 9.25 | `equity_return_target` | Target equity IRR | Financial | → `ppa_price`; ← `project_irr_hurdle` |
| 9.26 | `project_irr_hurdle` | Project IRR hurdle | Financial | → `equity_return_target`; ← `wacc` |
| 9.27 | `construction_period` | Construction period | Financial | → `project_timeline`; ↔ `nuclear_lead_time`, `transmission_lead_time` |
| 9.28 | `contingency` | Contingency on capex | Financial, Cost | → `total_capex`; ← `technology_risk_premium` |
| 9.29 | `political_risk_insurance` | Political risk insurance | Financial | → `cost_of_equity`; ← `country_risk_rating` |
| 9.30 | `currency_hedge_cost` | Currency hedge cost | Financial | → `cost_of_debt`; ← `exchange_rate_volatility` |
| 9.31 | `force_majeure_insurance` | Force majeure insurance | Financial | → `cost_of_debt`; ← `extreme_weather_events` |
| 9.32 | `business_interruption_insurance` | Business interruption insurance | Financial | → `cost_of_debt`; ← `outage_frequency` |
| 9.33 | `carbon_price_risk` | Carbon price risk premium | Financial | → `cost_of_equity`; ← `carbon_price_escalation` |
| 9.34 | `technology_risk_premium` | Technology risk premium | Financial | → `cost_of_equity`; ← `industrial_ccus_share` |
| 9.35 | `offtake_risk_premium` | Offtake risk premium | Financial | → `cost_of_equity`; ← `counterparty_risk` |
| 9.36 | `dfi_share` | DFI share | Financial | → `cost_of_debt`; ↔ `commercial_bank_share` |
| 9.37 | `commercial_bank_share` | Commercial bank share | Financial | → `cost_of_debt`; ↔ `dfi_share` |
| 9.38 | `bond_share` | Bond market share | Financial | → `cost_of_debt`; ↔ `green_bond_share` |
| 9.39 | `equity_share` | Equity share | Financial | → `debt_equity_ratio`; ↔ `dfi_share` |
| 9.40 | `blended_finance_share` | Blended finance share | Financial | → `cost_of_debt`; ← `dfi_share` |
| 9.41 | `green_bond_share` | Green bond share | Financial | → `cost_of_debt`; ← `renewable_target` |
| 9.42 | `carbon_finance_share` | Carbon finance share | Financial, Carbon | → `cost_of_debt`; ← `voluntary_carbon_market` |
| 9.43 | `remittance_flows` | Remittance flows | Macro | → `household_income`; ← `exchange_rate_usd_local` |
| 9.44 | `foreign_direct_investment` | Foreign direct investment | Macro | → `capital_inflow`; ← `country_risk_rating` |
| 9.45 | `official_development_assistance` | Official development assistance | Macro | → `capital_inflow`; ← `dfi_share` |
| 9.46 | `debt_sustainability` | Debt sustainability | Macro | Constrains → `debt_sizing`; ← `external_debt` |
| 9.47 | `balance_of_payments` | Balance of payments | Macro | → `exchange_rate_usd_local`; ← `current_account_balance` |
| 9.48 | `current_account_balance` | Current account balance | Macro | → `balance_of_payments`; ← `export_competitiveness` |
| 9.49 | `external_debt` | External debt | Macro | → `debt_sustainability`; ← `debt_sizing` |
| 9.50 | `foreign_exchange_reserves` | Foreign exchange reserves | Macro | → `exchange_rate_usd_local`; ← `balance_of_payments` |
| 9.51 | `remittance_dependency` | Remittance dependency | Macro | → `household_income`; ← `remittance_flows` |

---

## CATEGORY 10: INVESTMENT & FINANCE (25 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 10.1 | `debt_tenor` | Debt tenor | Financial | → `debt_service`; ↔ `loan_life_coverage_ratio` |
| 10.2 | `interest_rate_debt` | Interest rate on debt | Financial | → `cost_of_debt` |
| 10.3 | `debt_service_coverage_ratio` | Minimum DSCR | Financial | Constrains → `debt_sizing` |
| 10.4 | `loan_life_coverage_ratio` | Minimum LLCR | Financial | Constrains → `debt_sizing` |
| 10.5 | `gearing_ratio` | Debt-to-equity ratio | Financial | → `wacc` |
| 10.6 | `equity_return_target` | Target equity IRR | Financial | → `ppa_price` |
| 10.7 | `project_irr_hurdle` | Project IRR hurdle | Financial | → `equity_return_target` |
| 10.8 | `construction_period` | Construction period | Financial | → `project_timeline` |
| 10.9 | `contingency` | Contingency on capex | Financial | → `total_capex` |
| 10.10 | `political_risk_insurance` | Political risk insurance | Financial | → `cost_of_equity` |
| 10.11 | `currency_hedge_cost` | Currency hedge cost | Financial | → `cost_of_debt` |
| 10.12 | `force_majeure_insurance` | Force majeure insurance | Financial | → `cost_of_debt` |
| 10.13 | `business_interruption_insurance` | Business interruption insurance | Financial | → `cost_of_debt` |
| 10.14 | `carbon_price_risk` | Carbon price risk premium | Financial | → `cost_of_equity` |
| 10.15 | `technology_risk_premium` | Technology risk premium | Financial | → `cost_of_equity` |
| 10.16 | `offtake_risk_premium` | Offtake risk premium | Financial | → `cost_of_equity` |
| 10.17 | `dfi_share` | DFI share | Financial | → `cost_of_debt` |
| 10.18 | `commercial_bank_share` | Commercial bank share | Financial | → `cost_of_debt` |
| 10.19 | `bond_share` | Bond market share | Financial | → `cost_of_debt` |
| 10.20 | `equity_share` | Equity share | Financial | → `debt_equity_ratio` |
| 10.21 | `blended_finance_share` | Blended finance share | Financial | → `cost_of_debt` |
| 10.22 | `green_bond_share` | Green bond share | Financial | → `cost_of_debt` |
| 10.23 | `carbon_finance_share` | Carbon finance share | Financial | → `cost_of_debt` |
| 10.24 | `carbon_finance_share` | Carbon finance share | Financial | → `cost_of_debt` |
| 10.25 | `carbon_finance_share` | Carbon finance share | Financial | → `cost_of_debt` |

---

## CATEGORY 11: OPERATIONAL (24 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 11.1 | `dispatch_interval` | Dispatch interval | Energy Balance, Temporal | → `snapshot_frequency`; ↔ `temporal_resolution` |
| 11.2 | `day_ahead_market` | Day-ahead market | Market | → `clearing_price`; ↔ `real_time_market` |
| 11.3 | `real_time_market` | Real-time market | Market | → `clearing_price_rt`; ↔ `day_ahead_market` |
| 11.4 | `intraday_market` | Intraday market | Market | → `clearing_price_id`; ↔ `day_ahead_market` |
| 11.5 | `balancing_market` | Balancing market | Market | → `balancing_price`; ↔ `ancillary_services_market` |
| 11.6 | `unit_commitment` | Unit commitment | Energy Balance, Unit Commitment | → `commitment_schedule`; ← `min_up_time_coal` |
| 11.7 | `security_constrained_dispatch` | Security-constrained dispatch | Energy Balance | → `dispatch_with_constraints`; ← `n_1_criterion` |
| 11.8 | `n_1_criterion` | N-1 security criterion | Energy Balance | → `security_constrained_dispatch`; ↔ `n_2_criterion` |
| 11.9 | `n_2_criterion` | N-2 security criterion | Energy Balance | → `security_constrained_dispatch`; ↔ `n_1_criterion` |
| 11.10 | `spinning_reserve_requirement` | Spinning reserve | Reserve Margin | → `required_spinning_capacity` |
| 11.11 | `non_spinning_reserve_requirement` | Non-spinning reserve | Reserve Margin | → `required_non_spinning_capacity` |
| 11.12 | `regulation_up_requirement` | Regulation up | Reserve Margin | → `required_regulation_up` |
| 11.13 | `regulation_down_requirement` | Regulation down | Reserve Margin | → `required_regulation_down` |
| 11.14 | `reactive_power_requirement` | Reactive power | Energy Balance | Constrains → `reactive_power_supply`; ↔ `voltage_support_requirement` |
| 11.15 | `voltage_support_requirement` | Voltage support | Energy Balance | Constrains → `voltage_support`; ↔ `reactive_power_requirement` |
| 11.16 | `black_start_requirement` | Black start capability | Outage | → `black_start_capability`; ← `restoration_time` |
| 11.17 | `frequency_response_requirement` | Frequency response | Inertia | Constrains → `frequency_response`; ← `inertia_requirement` |
| 11.18 | `maintenance_schedule` | Maintenance schedule | Outage | → `planned_outage_rate`; ↔ `maintenance_schedule_optimisation` |
| 11.19 | `maintenance_duration` | Maintenance duration | Outage | → `planned_outage_rate`; ← `maintenance_frequency` |
| 11.20 | `maintenance_frequency` | Maintenance frequency | Outage | → `maintenance_duration`; ← `asset_condition_index` |
| 11.21 | `forced_outage_rate` | Forced outage rate | Outage, Reserve Margin | → `available_capacity` |
| 11.22 | `planned_outage_rate` | Planned outage rate | Outage | → `available_capacity` |
| 11.23 | `outage_coordination` | Outage coordination | Outage | → `planned_outage_rate`; ← `maintenance_schedule` |
| 11.24 | `spare_capacity` | Spare capacity | Reserve Margin | → `available_capacity`; ← `reserve_margin` |

---

## CATEGORY 12: SPATIAL & TEMPORAL (16 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 12.1 | `spatial_resolution` | Spatial resolution | Spatial | → `node_count`, `spatial_clustering`; ↔ `temporal_resolution` |
| 12.2 | `clustering_method` | Clustering method | Spatial | → `busmap`; ↔ `spatial_resolution` |
| 12.3 | `custom_gis_boundary` | Custom GIS boundary | Spatial | → `busmap`; ← `spatial_resolution` |
| 12.4 | `transmission_detail` | Transmission detail | Spatial | → `line_representation`; ↔ `spatial_resolution` |
| 12.5 | `distribution_detail` | Distribution detail | Spatial | → `distribution_representation`; ↔ `transmission_detail` |
| 12.6 | `temporal_resolution` | Temporal resolution | Temporal | → `snapshot_frequency`; ↔ `spatial_resolution` |
| 12.7 | `time_horizon` | Time horizon | Temporal | → `planning_horizon`; ↔ `investment_periods` |
| 12.8 | `investment_periods` | Investment periods | Temporal | → `planning_periods`; ↔ `time_horizon` |
| 12.9 | `foresight` | Foresight type | Temporal | → `solving_method`; ← `rolling_horizon_window` |
| 12.10 | `rolling_horizon_window` | Rolling horizon window | Temporal | → `foresight`; ↔ `time_horizon` |
| 12.11 | `temporal_aggregation` | Temporal aggregation | Temporal | → `snapshot_reduction`; ← `tsam_segments` |
| 12.12 | `tsam_segments` | TSAM segments | Temporal | → `temporal_aggregation`; ↔ `representative_days` |
| 12.13 | `representative_days` | Representative days | Temporal | → `temporal_aggregation`; ↔ `tsam_segments` |
| 12.14 | `spatial_clustering` | Spatial clustering | Spatial | → `busmap`; ← `spatial_resolution` |
| 12.15 | `temporal_clustering` | Temporal clustering | Temporal | → `snapshot_reduction`; ← `temporal_aggregation` |
| 12.16 | `snapshot_weightings` | Snapshot weightings | Temporal | → `objective_function`; ← `temporal_aggregation` |

---

## CATEGORY 13: MARKET DESIGN (15 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 13.1 | `market_model` | Market model | Market Design | → `market_pricing_mechanism`; ← `market_structure` |
| 13.2 | `pricing_mechanism` | Pricing mechanism | Market Design | → `clearing_price`; ↔ `market_model` |
| 13.3 | `settlement_period` | Settlement period | Market Design | → `settlement_volume`; ↔ `dispatch_interval` |
| 13.4 | `gate_closure` | Gate closure | Market Design | → `bid_deadline`; ↔ `day_ahead_market` |
| 13.5 | `market_coupling` | Market coupling | Market Design | → `cross_border_trade_allowed`; ↔ `trade_agreement` |
| 13.6 | `cross_border_trading` | Cross-border trading | Market Design | → `cross_border_flow`; ← `interconnector_capacity` |
| 13.7 | `financial_transmission_rights` | FTR model | Market Design | → `transmission_congestion_cost`; ↔ `virtual_bidding` |
| 13.8 | `virtual_bidding` | Virtual bidding | Market Design | → `clearing_price`; ↔ `financial_transmission_rights` |
| 13.9 | `number_of_generators` | Number of generators | Market Design | → `market_concentration`; ← `coal_capacity` |
| 13.10 | `number_of_retailers` | Number of retailers | Market Design | → `retail_competition`; ↔ `market_structure` |
| 13.11 | `market_concentration` | Market concentration | Market Design | → `market_power`; ← `number_of_generators` |
| 13.12 | `strategic_bidding` | Strategic bidding | Market Design | → `clearing_price`; ← `market_concentration` |
| 13.13 | `collusion` | Collusion detection | Market Design | → `clearing_price`; ← `market_concentration` |
| 13.14 | `new_entrants` | Market entry | Market Design | → `market_concentration`; ← `retail_competition` |
| 13.15 | `retail_competition` | Retail competition | Market Design | → `new_entrants`; ← `market_structure` |

---

## CATEGORY 14: COMBINED & CROSS-CUTTING (15 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 14.1 | `scenario_template` | Scenario template | Combined | → `parameter_set`; ↔ `parameter_overrides` |
| 14.2 | `parameter_overrides` | Parameter overrides | Combined | → `scenario_parameters`; ← `scenario_template` |
| 14.3 | `probability_weight` | Scenario probability | Stochastic | → `expected_value`; ← `stochastic_scenarios` |
| 14.4 | `scenario_tag` | Scenario tagging | Combined | Metadata only |
| 14.5 | `scenario_description` | Scenario description | Combined | Metadata only |
| 14.6 | `scenario_owner` | Scenario owner | Combined | Metadata only |
| 14.7 | `scenario_visibility` | Scenario visibility | Combined | Metadata only |
| 14.8 | `stochastic_scenarios` | Stochastic scenarios | Stochastic | → `probability_weight`; ↔ `cvar_alpha` |
| 14.9 | `cvar_alpha` | CVaR tail level | Stochastic | → `cvar_value`; ↔ `cvar_omega` |
| 14.10 | `cvar_omega` | Risk-aversion weight | Stochastic | → `objective_function`; ↔ `cvar_alpha` |
| 14.11 | `efficient_frontier` | Efficient frontier | Stochastic | ← `cvar_omega` sweep; → `risk_return_tradeoff` |
| 14.12 | `signal_extraction` | Signal extraction | Intelligence | → `signals`; ← `signal_scoring` |
| 14.13 | `near_duplicate_detection` | Near-duplicate detection | Intelligence | → `unique_signals`; ← `signals` |
| 14.14 | `signal_scoring` | Signal scoring | Intelligence | → `review_priority`; ← `signal_extraction` |
| 14.15 | `human_review` | Human review | Intelligence | → `confirmed_signals`; ← `signal_scoring` |

---

## CATEGORY 15: TAX & FISCAL (25 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 15.1 | `corporate_income_tax_rate` | Corporate tax rate | Tax | → `after_tax_cash_flow`; ← `tax_holiday_duration` |
| 15.2 | `vat_rate` | VAT/GST rate | Tax | → `consumer_cost`; ← `regulated_tariff_rate` |
| 15.3 | `withholding_tax_dividends` | Dividend WHT | Tax | → `equity_return`; ← `corporate_income_tax_rate` |
| 15.4 | `withholding_tax_interest` | Interest WHT | Tax | → `debt_cost`; ← `corporate_income_tax_rate` |
| 15.5 | `import_duty_equipment` | Import duty on equipment | Tax | → `capex_solar_pv`, `capex_wind_onshore`; ← `import_duty_exemption` |
| 15.6 | `export_duty` | Export duty | Tax | → `export_price`; ← `export_competitiveness` |
| 15.7 | `property_tax` | Property tax | Tax | → `total_cost`; ← `land_acquisition_costs` |
| 15.8 | `tax_holiday_duration` | Tax holiday period | Tax | → `corporate_income_tax_rate`; ↔ `tax_incentives` |
| 15.9 | `tax_holiday_conditions` | Conditions for holiday | Tax | Constrains → `tax_holiday_duration`; ← `local_content_requirement` |
| 15.10 | `transfer_pricing_rules` | Transfer pricing | Tax | → `profit_allocation`; ← `double_tax_treaty` |
| 15.11 | `thin_capitalisation_rules` | Thin cap rules | Tax | Constrains → `debt_equity_ratio`; ← `interest_rate_debt` |
| 15.12 | `loss_carryforward_years` | Loss carry-forward | Tax | → `taxable_income`; ↔ `loss_carryback_years` |
| 15.13 | `loss_carryback_years` | Loss carry-back | Tax | → `taxable_income`; ↔ `loss_carryforward_years` |
| 15.14 | `depreciation_schedule_linear` | Linear depreciation | Tax | → `taxable_income`; ↔ `depreciation_schedule_accelerated` |
| 15.15 | `depreciation_schedule_accelerated` | Accelerated depreciation | Tax | → `taxable_income`; ↔ `depreciation_schedule_linear` |
| 15.16 | `depreciation_schedule_declining` | Declining balance | Tax | → `taxable_income`; ↔ `depreciation_schedule_linear` |
| 15.17 | `capital_gains_tax` | Capital gains tax | Tax | → `after_tax_return`; ← `equity_return_target` |
| 15.18 | `stamp_duty` | Stamp duty | Tax | → `transaction_cost`; ← `land_acquisition_costs` |
| 15.19 | `customs_duty` | Customs duty | Tax | → `import_cost`; ← `import_duty_equipment` |
| 15.20 | `excise_duty_fuel` | Fuel excise | Tax | → `fuel_cost_coal`, `fuel_cost_gas`; ← `fossil_fuel_subsidies` |
| 15.21 | `carbon_tax_interaction` | Carbon tax vs. other taxes | Tax, Policy | → `effective_carbon_price`; ← `carbon_tax_rate` |
| 15.22 | `double_tax_treaty` | Treaty network | Tax | → `withholding_tax_dividends`; ← `transfer_pricing_rules` |
| 15.23 | `tax_incentive_zones` | Special economic zones | Tax | → `corporate_income_tax_rate`; ← `local_content_requirement` |
| 15.24 | `free_trade_zone_benefits` | FTZ benefits | Tax | → `import_duty_equipment`; ← `tax_incentive_zones` |
| 15.25 | `investment_allowance` | Investment allowance | Tax | → `taxable_income`; ← `capex_solar_pv` |

---

## CATEGORY 16: REGULATORY FINANCE (25 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 16.1 | `regulatory_asset_base` | Regulatory asset base | Regulatory Finance | → `allowed_revenue`; ← `regulatory_depreciation` |
| 16.2 | `rab_roll_forward` | RAB roll-forward | Regulatory Finance | → `regulatory_asset_base`; ← `capex_transmission` |
| 16.3 | `regulatory_period_length` | Regulatory period | Regulatory Finance | → `allowed_revenue_period`; ↔ `regulatory_lag` |
| 16.4 | `x_factor` | Efficiency factor | Regulatory Finance | → `allowed_revenue`; ← `efficiency_benchmarking` |
| 16.5 | `allowed_return_on_equity` | Regulatory ROE | Regulatory Finance | → `allowed_revenue`; ← `cost_of_equity` |
| 16.6 | `allowed_return_on_debt` | Regulatory ROD | Regulatory Finance | → `allowed_revenue`; ← `cost_of_debt` |
| 16.7 | `regulatory_depreciation` | Regulatory depreciation | Regulatory Finance | → `regulatory_asset_base`; ← `depreciation_life_by_asset` |
| 16.8 | `regulatory_lag` | Regulatory lag | Regulatory Finance | → `allowed_revenue`; ↔ `regulatory_period_length` |
| 16.9 | `cost_pass_through_mechanism` | Pass-through rules | Regulatory Finance | → `allowed_revenue`; ← `fuel_cost_coal` |
| 16.10 | `efficiency_benchmarking` | Benchmarking | Regulatory Finance | → `x_factor`; ← `cost_allocation_methodology` |
| 16.11 | `service_quality_penalty` | Quality penalty | Regulatory Finance | → `allowed_revenue`; ← `grid_reliability_target` |
| 16.12 | `service_quality_reward` | Quality reward | Regulatory Finance | → `allowed_revenue`; ← `grid_reliability_target` |
| 16.13 | `revenue_cap` | Revenue cap | Regulatory Finance | → `allowed_revenue`; ↔ `price_cap` |
| 16.14 | `price_cap` | Price cap | Regulatory Finance | → `regulated_tariff_rate`; ↔ `revenue_cap` |
| 16.15 | `hybrid_revenue_price_cap` | Hybrid cap | Regulatory Finance | → `allowed_revenue`, `regulated_tariff_rate`; ↔ `revenue_cap` |
| 16.16 | `tariff_rebalancing` | Tariff rebalancing | Regulatory Finance | → `regulated_tariff_rate`; ← `cost_allocation_methodology` |
| 16.17 | `cost_allocation_methodology` | Cost allocation | Regulatory Finance | → `tariff_rebalancing`; ← `cost_pass_through_mechanism` |
| 16.18 | `demand_forecast_methodology` | Demand forecast | Regulatory Finance | → `demand_growth_rate`; ← `gdp_growth_rate` |
| 16.19 | `regulatory_accounts` | Regulatory accounts | Regulatory Finance | → `regulatory_asset_base`; ← `ring_fencing_rules` |
| 16.20 | `ring_fencing_rules` | Ring-fencing | Regulatory Finance | → `regulatory_accounts`; ← `unbundling_status` |
| 16.21 | `regulatory_audit_requirements` | Audit requirements | Regulatory Finance | → `compliance_cost`; ← `regulatory_accounts` |
| 16.22 | `consumer_price_index_link` | CPI link | Regulatory Finance | → `tariff_indexation`; ← `inflation_rate` |
| 16.23 | `regulatory_asset_valuation_method` | Valuation method | Regulatory Finance | → `regulatory_asset_base`; ↔ `depreciation_life_by_asset` |
| 16.24 | `depreciation_life_by_asset` | Asset lives | Regulatory Finance | → `regulatory_depreciation`; ← `regulatory_asset_valuation_method` |
| 16.25 | `working_capital_allowance` | Working capital | Regulatory Finance | → `allowed_revenue`; ← `regulatory_asset_base` |

---

## CATEGORY 17: CONTRACT & LEGAL (33 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 17.1 | `ppa_duration` | PPA contract length | Contract | → `ppa_price`; ↔ `fit_duration` |
| 17.2 | `ppa_pricing_formula` | PPA pricing | Contract | → `ppa_price`; ← `lcoe` |
| 17.3 | `ppa_indexation` | Indexation formula | Contract | → `ppa_price_t`; ← `inflation_rate` |
| 17.4 | `ppa_take_or_pay` | Take-or-pay provisions | Contract | → `ppa_volume`; ← `demand_growth_rate` |
| 17.5 | `ppa_curtailment_compensation` | Curtailment compensation | Contract | → `ppa_price`; ← `renewable_curtailment_limit` |
| 17.6 | `ppa_change_in_law` | Change in law | Contract | → `ppa_price`; ← `carbon_tax_rate` |
| 17.7 | `ppa_force_majeure` | Force majeure | Contract | → `ppa_availability`; ← `extreme_weather_events` |
| 17.8 | `ppa_termination_payments` | Termination payments | Contract | → `project_npv`; ← `ppa_duration` |
| 17.9 | `ppa_governing_law` | Governing law | Contract | Metadata; ↔ `ppa_arbitration_venue` |
| 17.10 | `ppa_arbitration_venue` | Arbitration venue | Contract | Metadata; ↔ `ppa_governing_law` |
| 17.11 | `ppa_dispute_resolution` | Dispute resolution | Contract | → `contract_enforceability`; ↔ `ppa_governing_law` |
| 17.12 | `concession_duration` | Concession length | Contract | → `project_npv`; ↔ `licence_duration` |
| 17.13 | `concession_terms` | Concession terms | Contract | → `project_npv`; ← `concession_duration` |
| 17.14 | `licence_conditions` | Licence conditions | Contract | → `compliance_cost`; ↔ `licence_fees` |
| 17.15 | `licence_duration` | Licence length | Contract | → `licence_fees`; ↔ `concession_duration` |
| 17.16 | `licence_fees` | Licence fees | Contract | → `total_cost`; ← `licence_duration` |
| 17.17 | `performance_bond` | Performance bond | Contract | → `debt_sizing`; ← `ppa_termination_payments` |
| 17.18 | `parent_company_guarantee` | PCG | Contract | → `debt_sizing`; ← `counterparty_risk` |
| 17.19 | `direct_agreement` | Direct agreement | Contract | → `step_in_rights`; ← `debt_sizing` |
| 17.20 | `step_in_rights` | Step-in rights | Contract | → `debt_sizing`; ← `direct_agreement` |
| 17.21 | `security_package` | Security package | Contract | → `debt_sizing`; ← `performance_bond` |
| 17.22 | `assignment_rights` | Assignment rights | Contract | → `refinancing_terms`; ↔ `change_of_control` |
| 17.23 | `change_of_control` | Change of control | Contract | → `refinancing_terms`; ↔ `assignment_rights` |
| 17.24 | `refinancing_terms` | Refinancing | Contract | → `debt_service`; ← `debt_tenor` |
| 17.25 | `cash_sweep` | Cash sweep | Contract | → `debt_service`; ← `dscr` |
| 17.26 | `reserve_accounts` | Reserve accounts | Contract | → `debt_service`; ← `cash_sweep` |
| 17.27 | `distribution_conditions` | Distribution conditions | Contract | → `equity_return`; ← `dscr` |
| 17.28 | `default_events` | Events of default | Contract | → `project_npv`; ← `dscr` |
| 17.29 | `remedy_periods` | Remedy periods | Contract | → `project_npv`; ← `default_events` |
| 17.30 | `cross_default` | Cross-default | Contract | → `project_npv`; ← `default_events` |
| 17.31 | `material_adverse_change` | MAC clause | Contract | → `project_npv`; ← `force_majeure` |
| 17.32 | `environmental_representations` | Environmental reps | Contract | → `compliance_cost`; ← `ifc_performance_standards` |
| 17.33 | `social_representations` | Social reps | Contract | → `compliance_cost`; ← `undrip_compliance` |

---

## CATEGORY 18: ENVIRONMENTAL & SOCIAL IMPACT (39 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 18.1 | `pm25_emissions` | PM2.5 emissions | Environmental | → `health_impact_mortality`; ← `generation_coal`, `generation_gas` |
| 18.2 | `pm10_emissions` | PM10 emissions | Environmental | → `health_impact_mortality`; ← `generation_coal`, `generation_gas` |
| 18.3 | `nox_emissions` | NOx emissions | Environmental | → `health_impact_mortality`; ← `generation_coal`, `generation_gas` |
| 18.4 | `sox_emissions` | SOx emissions | Environmental | → `health_impact_mortality`; ← `generation_coal` |
| 18.5 | `co_emissions` | CO emissions | Environmental | → `health_impact_mortality`; ← `generation_coal` |
| 18.6 | `voc_emissions` | VOC emissions | Environmental | → `health_impact_mortality`; ← `generation_gas` |
| 18.7 | `mercury_emissions` | Mercury | Environmental | → `health_impact_mortality`; ← `generation_coal` |
| 18.8 | `air_quality_standards` | Air quality limits | Environmental | Constrains → `pm25_emissions`; ← `world_bank_esf` |
| 18.9 | `health_impact_dalys` | DALYs | Health | ← `pm25_emissions`; → `healthcare_cost_per_case` |
| 18.10 | `health_impact_mortality` | Premature deaths | Health | ← `pm25_emissions`; → `health_impact_dalys` |
| 18.11 | `health_impact_morbidity` | Illness cases | Health | ← `pm25_emissions`; → `health_impact_dalys` |
| 18.12 | `healthcare_cost_per_case` | Healthcare costs | Health, Cost | ← `health_impact_mortality`; → `total_cost` |
| 18.13 | `biodiversity_impact` | Biodiversity | Environmental | ← `land_use_change`; → `compliance_cost` |
| 18.14 | `habitat_loss` | Habitat loss | Environmental | ← `land_use_change`; → `biodiversity_impact` |
| 18.15 | `land_use_change` | Land use change | Environmental | ← `solar_pv_land_constraint`, `wind_onshore_capacity`; → `habitat_loss` |
| 18.16 | `water_quality_impact` | Water quality | Environmental | ← `water_pollution_load`; → `compliance_cost` |
| 18.17 | `water_pollution_load` | Pollution load | Environmental | ← `generation_coal`, `industrial_ccus_share`; → `water_quality_impact` |
| 18.18 | `soil_contamination` | Soil contamination | Environmental | ← `industrial_ccus_share`; → `compliance_cost` |
| 18.19 | `resettlement_requirements` | Resettlement | Social | ← `land_acquisition_costs`; → `resettlement_costs` |
| 18.20 | `resettlement_costs` | Resettlement costs | Social, Cost | ← `resettlement_requirements`; → `total_cost` |
| 18.21 | `indigenous_peoples_rights` | FPIC | Social | Constrains → `land_acquisition_costs`; ← `undrip_compliance` |
| 18.22 | `cultural_heritage_impact` | Cultural heritage | Social | ← `land_use_change`; → `compliance_cost` |
| 18.23 | `gender_impact` | Gender dimensions | Social | → `gender_action_plan`; ← `local_employment_targets` |
| 18.24 | `gender_action_plan` | Gender plan | Social | ← `gender_impact`; → `compliance_cost` |
| 18.25 | `labour_standards` | Labour standards | Social | → `compliance_cost`; ← `ilo_conventions` |
| 18.26 | `child_labour_prohibition` | Child labour | Social | → `compliance_cost`; ← `ilo_conventions` |
| 18.27 | `occupational_health_safety` | OHS | Social | → `compliance_cost`; ← `ilo_conventions` |
| 18.28 | `worker_grievance_mechanism` | Grievance mechanism | Social | → `compliance_cost`; ← `stakeholder_engagement_plan` |
| 18.29 | `community_health_safety` | Community H&S | Social | → `compliance_cost`; ← `emergency_preparedness` |
| 18.30 | `emergency_preparedness` | Emergency prep | Social | → `community_health_safety`; ← `extreme_weather_events` |
| 18.31 | `equator_principles` | Equator Principles | Compliance | → `compliance_cost`; ← `ifc_performance_standards` |
| 18.32 | `ifc_performance_standards` | IFC PS | Compliance | → `compliance_cost`; ← `world_bank_esf` |
| 18.33 | `world_bank_esf` | World Bank ESF | Compliance | → `compliance_cost`; ← `undrip_compliance` |
| 18.34 | `undrip_compliance` | UNDRIP | Compliance | → `compliance_cost`; ← `ilo_conventions` |
| 18.35 | `ilo_conventions` | ILO conventions | Compliance | → `compliance_cost`; ← `labour_standards` |
| 18.36 | `stakeholder_engagement_plan` | SEP | Compliance | → `compliance_cost`; ← `grievance_redress_mechanism` |
| 18.37 | `grievance_redress_mechanism` | GRM | Compliance | → `compliance_cost`; ← `stakeholder_engagement_plan` |
| 18.38 | `environmental_flow_requirements` | E-flows | Environmental | Constrains → `hydro_reservoir_level`; ← `water_availability` |
| 18.39 | `cumulative_impact_assessment` | CIA | Environmental | → `compliance_cost`; ← `biodiversity_impact` |

---

## CATEGORY 19: JUST TRANSITION (28 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 19.1 | `employment_factor_solar` | Jobs/MW solar | Employment | → `direct_jobs`; ← `solar_pv_capacity` |
| 19.2 | `employment_factor_wind` | Jobs/MW wind | Employment | → `direct_jobs`; ← `wind_onshore_capacity` |
| 19.3 | `employment_factor_coal` | Jobs/MW coal | Employment | → `direct_jobs`; ← `coal_capacity` |
| 19.4 | `employment_factor_gas` | Jobs/MW gas | Employment | → `direct_jobs`; ← `gas_capacity` |
| 19.5 | `employment_factor_geothermal` | Jobs/MW geothermal | Employment | → `direct_jobs`; ← `geothermal_capacity` |
| 19.6 | `employment_factor_hydro` | Jobs/MW hydro | Employment | → `direct_jobs`; ← `hydro_capacity` |
| 19.7 | `employment_factor_biomass` | Jobs/MW biomass | Employment | → `direct_jobs`; ← `biomass_capacity` |
| 19.8 | `employment_factor_transmission` | Jobs/km transmission | Employment | → `direct_jobs`; ← `transmission_capacity` |
| 19.9 | `direct_jobs` | Direct employment | Employment | ← `employment_factor_*`; → `indirect_jobs` |
| 19.10 | `indirect_jobs` | Indirect employment | Employment | ← `direct_jobs`; → `induced_jobs` |
| 19.11 | `induced_jobs` | Induced employment | Employment | ← `direct_jobs` |
| 19.12 | `skills_requirements` | Skills by technology | Employment | → `skills_gap_assessment`; ← `employment_factor_*` |
| 19.13 | `skills_gap_assessment` | Skills gap | Employment | ← `skills_requirements`, `retraining_duration` |
| 19.14 | `retraining_costs` | Retraining cost | Employment, Cost | → `just_transition_fund`; ← `skills_gap_assessment` |
| 19.15 | `retraining_duration` | Retraining time | Employment | → `skills_gap_assessment`; ← `retraining_costs` |
| 19.16 | `community_transition_funding` | Transition funding | Employment, Cost | → `just_transition_fund`; ← `coal_community_dependencies` |
| 19.17 | `coal_community_dependencies` | Coal community reliance | Employment | → `community_transition_funding`; ← `employment_factor_coal` |
| 19.18 | `social_protection_parameters` | Social protection | Employment | → `just_transition_fund`; ← `pension_security` |
| 19.19 | `wage_levels_by_sector` | Wage levels | Employment | → `household_income`; ← `gdp_per_capita_growth` |
| 19.20 | `union_agreements` | Union agreements | Employment | → `wage_levels_by_sector`; ← `labour_standards` |
| 19.21 | `just_transition_fund` | JT fund | Employment, Financial | ← `community_transition_funding`; → `retraining_costs` |
| 19.22 | `pension_security` | Pension security | Employment | → `social_protection_parameters`; ← `early_retirement_packages` |
| 19.23 | `early_retirement_packages` | Early retirement | Employment | → `pension_security`; ← `coal_retirement_schedule` |
| 19.24 | `redeployment_options` | Redeployment | Employment | → `direct_jobs`; ← `skills_gap_assessment` |
| 19.25 | `local_content_employment` | Local employment | Employment | → `direct_jobs`; ← `local_content_requirement` |
| 19.26 | `women_employment_targets` | Women employment | Employment | **DEPRECATED (batch 70)** — a second id for `women_employment_share`; the attainment ratio that divided one by the other is removed, and both nodes are tombstones |
| 19.27 | `youth_employment_targets` | Youth employment | Employment | **DEPRECATED (batch 70)** — a second id for `youth_employment_share`; see 19.26 |
| 19.28 | `disability_inclusion` | Disability inclusion | Employment | → `direct_jobs`; ← `labour_standards` |

---

## CATEGORY 20: CONSUMER PROTECTION & AFFORDABILITY (22 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 20.1 | `affordability_threshold` | Affordability limit | Affordability | → `energy_poverty_rate`; ← `household_income` |
| 20.2 | `energy_poverty_rate` | Energy poverty | Affordability | ← `energy_burden`; → `electricity_subsidies` |
| 20.3 | `energy_poverty_gap` | Poverty gap | Affordability | ← `energy_poverty_rate`; → `social_tariff` |
| 20.4 | `willingness_to_pay` | WTP | Affordability | → `demand_response_potential`; ← `household_income` |
| 20.5 | `consumer_protection_standards` | Consumer standards | Affordability | → `compliance_cost`; ← `service_quality_standards` |
| 20.6 | `dispute_resolution_mechanism` | Dispute resolution | Affordability | → `complaint_handling`; ← `consumer_protection_standards` |
| 20.7 | `service_quality_standards` | Service standards | Affordability | → `grid_reliability_target`; ← `consumer_protection_standards` |
| 20.8 | `compensation_mechanisms` | Compensation | Affordability | → `consumer_cost`; ← `service_quality_standards` |
| 20.9 | `lifeline_tariff` | Lifeline tariff | Affordability | → `regulated_tariff_rate`; ← `lifeline_threshold` |
| 20.10 | `lifeline_threshold` | Lifeline threshold | Affordability | → `lifeline_tariff`; ← `household_income` |
| 20.11 | `prepayment_metering` | Prepayment | Affordability | → `billing_systems`; ← `smart_metering_penetration` |
| 20.12 | `debt_management` | Debt management | Affordability | → `arrears_management`; ← `bill_shock_protection` |
| 20.13 | `disconnection_protection` | Disconnection protection | Affordability | → `vulnerable_customer_protection`; ← `lifeline_tariff` |
| 20.14 | `vulnerable_customer_protection` | Vulnerable customers | Affordability | → `disconnection_protection`; ← `energy_poverty_rate` |
| 20.15 | `complaint_handling` | Complaint handling | Affordability | → `dispute_resolution_mechanism`; ← `consumer_protection_standards` |
| 20.16 | `consumer_education` | Consumer education | Affordability | → `willingness_to_pay`; ← `complaint_handling` |
| 20.17 | `tariff_transparency` | Tariff transparency | Affordability | → `willingness_to_pay`; ← `tariff_structure` |
| 20.18 | `bill_shock_protection` | Bill shock protection | Affordability | → `debt_management`; ← `tariff_structure` |
| 20.19 | `payment_plans` | Payment plans | Affordability | → `debt_management`; ← `disconnection_protection` |
| 20.20 | `arrears_management` | Arrears management | Affordability | → `debt_management`; ← `payment_plans` |
| 20.21 | `social_tariff` | Social tariff | Affordability | → `regulated_tariff_rate`; ← `energy_poverty_gap` |
| 20.22 | `cross_subsidy_transparency` | Cross-subsidy | Affordability | → `cross_subsidy_level`; ← `tariff_transparency` |

---

## CATEGORY 21: DIGITAL, DATA & CYBERSECURITY (22 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 21.1 | `data_sovereignty_requirements` | Data sovereignty | Digital | → `compliance_cost`; ← `data_privacy_requirements` |
| 21.2 | `data_privacy_requirements` | Privacy (GDPR/POPIA) | Digital | → `compliance_cost`; ← `data_sovereignty_requirements` |
| 21.3 | `cybersecurity_requirements` | Cybersecurity | Digital | → `compliance_cost`; ← `cyber_threat_level` |
| 21.4 | `scada_ems_requirements` | SCADA/EMS | Digital | → `operational_cost`; ← `adms_requirements` |
| 21.5 | `communication_protocols` | Protocols | Digital | → `interoperability_standards`; ← `scada_ems_requirements` |
| 21.6 | `interoperability_standards` | Interoperability | Digital | → `communication_protocols`; ← `gis_requirements` |
| 21.7 | `digital_divide_metrics` | Digital divide | Digital | → `internet_penetration`; ← `mobile_coverage` |
| 21.8 | `mobile_coverage` | Mobile coverage | Digital | → `digital_divide_metrics`; ← `population_growth_rate` |
| 21.9 | `internet_penetration` | Internet penetration | Digital | → `internet_users`; ← `digital_divide_metrics` |
| 21.10 | `smart_metering_rollout` | Smart meter rollout | Digital | → `smart_metering_penetration`; ← `ami_infrastructure` |
| 21.11 | `ami_infrastructure` | AMI infrastructure | Digital | → `smart_metering_rollout`; ← `scada_ems_requirements` |
| 21.12 | `der_management_systems` | DERMS | Digital | → `distributed_generation_capacity`; ← `adms_requirements` |
| 21.13 | `adms_requirements` | ADMS | Digital | → `der_management_systems`; ← `gis_requirements` |
| 21.14 | `gis_requirements` | GIS | Digital | → `adms_requirements`; ← `interoperability_standards` |
| 21.15 | `outage_management_systems` | OMS | Digital | → `outage_frequency`; ← `scada_ems_requirements` |
| 21.16 | `work_management_systems` | WMS | Digital | → `maintenance_duration`; ← `asset_management_systems` |
| 21.17 | `asset_management_systems` | EAM | Digital | → `work_management_systems`; ← `asset_condition_index` |
| 21.18 | `customer_information_systems` | CIS | Digital | → `billing_systems`; ← `data_privacy_requirements` |
| 21.19 | `billing_systems` | Billing | Digital | → `revenue_collection`; ← `customer_information_systems` |
| 21.20 | `cyber_insurance` | Cyber insurance | Digital | → `cost_of_debt`; ← `cyber_threat_level` |
| 21.21 | `cyber_incident_response` | Incident response | Digital | → `cybersecurity_requirements`; ← `cyber_threat_level` |
| 21.22 | `data_backup_recovery` | Backup & recovery | Digital | → `data_sovereignty_requirements`; ← `cybersecurity_requirements` |

---

## CATEGORY 22: GEOPOLITICAL & STRATEGIC (21 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 22.1 | `supply_chain_concentration` | Supply chain concentration | Geopolitical | → `technology_risk_premium`; ← `critical_mineral_dependencies` |
| 22.2 | `critical_mineral_dependencies` | Critical minerals | Geopolitical | → `supply_chain_concentration`; ← `rare_earth_dependencies` |
| 22.3 | `rare_earth_dependencies` | Rare earths | Geopolitical | → `critical_mineral_dependencies`; ← `supply_chain_concentration` |
| 22.4 | `trade_flow_parameters` | Trade flows | Geopolitical | → `current_account_balance`; ← `export_competitiveness` |
| 22.5 | `sanctions_exposure` | Sanctions | Geopolitical | → `country_risk_rating`; ← `geopolitical_risk_index` |
| 22.6 | `strategic_reserves` | Strategic reserves | Geopolitical | → `fuel_price_volatility`; ← `energy_security_index` |
| 22.7 | `energy_security_index` | Energy security | Geopolitical | → `country_risk_rating`; ← `import_dependency` |
| 22.8 | `import_dependency` | Import dependency | Geopolitical | → `energy_security_index`; ← `fuel_price_volatility` |
| 22.9 | `export_competitiveness` | Export competitiveness | Geopolitical | → `current_account_balance`; ← `cbam_price` |
| 22.10 | `geopolitical_risk_index` | Geopolitical risk | Geopolitical | → `country_risk_rating`; ← `political_stability` |
| 22.11 | `country_risk_rating` | Country risk | Geopolitical | → `sovereign_risk_premium`; ← `political_stability` |
| 22.12 | `political_stability` | Political stability | Geopolitical | → `country_risk_rating`; ← `rule_of_law_index` |
| 22.13 | `regulatory_predictability` | Regulatory predictability | Geopolitical | → `country_risk_rating`; ← `rule_of_law_index` |
| 22.14 | `contract_enforceability` | Contract enforcement | Geopolitical | → `country_risk_rating`; ← `rule_of_law_index` |
| 22.15 | `rule_of_law_index` | Rule of law | Geopolitical | → `country_risk_rating`; ← `corruption_perception` |
| 22.16 | `corruption_perception` | Corruption | Geopolitical | → `rule_of_law_index`; ← `political_stability` |
| 22.17 | `cross_border_tension` | Cross-border tension | Geopolitical | → `geopolitical_risk_index`; ← `trade_flow_parameters` |
| 22.18 | `maritime_security` | Maritime security | Geopolitical | → `geopolitical_risk_index`; ← `cross_border_tension` |
| 22.19 | `cyber_threat_level` | Cyber threat | Geopolitical | → `cybersecurity_requirements`; ← `geopolitical_risk_index` |
| 22.20 | `terrorism_risk` | Terrorism risk | Geopolitical | → `country_risk_rating`; ← `political_stability` |
| 22.21 | `civil_unrest_risk` | Civil unrest | Geopolitical | → `country_risk_rating`; ← `political_stability` |

---

## CATEGORY 23: ASSET CONDITION & LIFECYCLE (19 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 23.1 | `asset_age_distribution` | Age distribution | Asset | → `remaining_useful_life`; ← `plant_retirement_age` |
| 23.2 | `asset_condition_index` | Condition index | Asset | → `predictive_maintenance_adoption`; ← `failure_history` |
| 23.3 | `remaining_useful_life` | RUL | Asset | ← `asset_age_distribution`; → `plant_retirement_age` |
| 23.4 | `maintenance_history` | Maintenance history | Asset | → `asset_condition_index`; ← `maintenance_frequency` |
| 23.5 | `failure_history` | Failure history | Asset | → `asset_condition_index`; ← `forced_outage_rate` |
| 23.6 | `mean_time_between_failures` | MTBF | Asset | → `asset_condition_index`; ← `failure_history` |
| 23.7 | `mean_time_to_repair` | MTTR | Asset | → `repair_time`; ← `maintenance_duration` |
| 23.8 | `failure_rate_curve` | Bathtub curve | Asset | → `forced_outage_rate`; ← `asset_age_distribution` |
| 23.9 | `degradation_model` | Degradation | Asset | → `remaining_useful_life`; ← `asset_condition_index` |
| 23.10 | `spare_parts_inventory` | Spare parts | Asset | → `spare_parts_availability`; ← `spare_parts_lead_time` |
| 23.11 | `spare_parts_lead_time` | Lead time | Asset | → `spare_parts_availability`; ← `supply_chain_concentration` |
| 23.12 | `crew_availability` | Crew availability | Asset | → `repair_time`; ← `work_management_systems` |
| 23.13 | `workshop_capacity` | Workshop capacity | Asset | → `repair_time`; ← `crew_availability` |
| 23.14 | `transport_logistics` | Transport logistics | Asset | → `repair_time`; ← `infrastructure_quality` |
| 23.15 | `asset_management_maturity` | AM maturity | Asset | → `predictive_maintenance_adoption`; ← `iso_55000_compliance` |
| 23.16 | `iso_55000_compliance` | ISO 55000 | Asset | → `asset_management_maturity`; ← `risk_based_maintenance` |
| 23.17 | `risk_based_maintenance` | RBM | Asset | → `maintenance_schedule_optimisation`; ← `condition_based_maintenance` |
| 23.18 | `condition_based_maintenance` | CBM | Asset | → `risk_based_maintenance`; ← `asset_condition_index` |
| 23.19 | `reliability_centred_maintenance` | RCM | Asset | → `maintenance_schedule_optimisation`; ← `failure_history` |

---

## CATEGORY 24: MARKET OPERATIONS (20 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 24.1 | `bid_ask_spread` | Bid-ask spread | Market Ops | → `transaction_costs`; ← `market_liquidity` |
| 24.2 | `market_liquidity` | Liquidity | Market Ops | → `bid_ask_spread`; ← `market_concentration` |
| 24.3 | `transaction_costs` | Transaction costs | Market Ops | → `total_cost`; ← `bid_ask_spread` |
| 24.4 | `clearing_house_requirements` | Clearing house | Market Ops | → `margin_requirements`; ← `counterparty_risk` |
| 24.5 | `margin_requirements` | Margin requirements | Market Ops | → `collateral_requirements`; ← `settlement_risk` |
| 24.6 | `settlement_risk` | Settlement risk | Market Ops | → `margin_requirements`; ← `counterparty_risk` |
| 24.7 | `counterparty_risk` | Counterparty risk | Market Ops | → `settlement_risk`; ← `country_risk_rating` |
| 24.8 | `credit_support_requirements` | Credit support | Market Ops | → `collateral_requirements`; ← `counterparty_risk` |
| 24.9 | `collateral_requirements` | Collateral | Market Ops | → `credit_support_requirements`; ← `margin_requirements` |
| 24.10 | `collateral_valuation` | Collateral valuation | Market Ops | → `collateral_requirements`; ← `exchange_rate_usd_local` |
| 24.11 | `netting_agreements` | Netting | Market Ops | → `collateral_requirements`; ← `counterparty_risk` |
| 24.12 | `novation_terms` | Novation | Market Ops | → `counterparty_risk`; ← `netting_agreements` |
| 24.13 | `trade_repository` | Trade repository | Market Ops | → `reporting_requirements`; ← `market_abuse_prevention` |
| 24.14 | `reporting_requirements` | Reporting | Market Ops | → `compliance_cost`; ← `trade_repository` |
| 24.15 | `market_abuse_prevention` | Market abuse | Market Ops | → `reporting_requirements`; ← `insider_trading_rules` |
| 24.16 | `insider_trading_rules` | Insider trading | Market Ops | → `market_abuse_prevention`; ← `market_concentration` |
| 24.17 | `position_limits` | Position limits | Market Ops | → `market_concentration`; ← `market_abuse_prevention` |
| 24.18 | `price_limits` | Price limits | Market Ops | → `clearing_price`; ← `market_abuse_prevention` |
| 24.19 | `circuit_breakers` | Circuit breakers | Market Ops | → `clearing_price`; ← `price_limits` |
| 24.20 | `auction_frequency` | Auction frequency | Market Ops | → `clearing_price`; ← `day_ahead_market` |

---

## CATEGORY 25: INSURANCE & CATASTROPHE (17 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 25.1 | `catastrophe_modelling` | Cat modelling | Insurance | → `physical_risk_score`; ← `extreme_weather_events` |
| 25.2 | `physical_risk_score` | Physical risk | Insurance | → `insurance_premiums`; ← `catastrophe_modelling` |
| 25.3 | `business_interruption` | BI parameters | Insurance | → `insurance_premiums`; ← `outage_frequency` |
| 25.4 | `liability_exposure` | Liability | Insurance | → `insurance_premiums`; ← `compliance_cost` |
| 25.5 | `accumulation_risk` | Accumulation | Insurance | → `solvency_capital`; ← `physical_risk_score` |
| 25.6 | `reinsurance_parameters` | Reinsurance | Insurance | → `solvency_capital`; ← `accumulation_risk` |
| 25.7 | `deductible_levels` | Deductibles | Insurance | → `insurance_premiums`; ← `loss_ratio` |
| 25.8 | `insurance_premiums` | Premiums | Insurance | ← `physical_risk_score`; → `total_cost` |
| 25.9 | `claims_history` | Claims history | Insurance | → `loss_ratio`; ← `business_interruption` |
| 25.10 | `loss_ratio` | Loss ratio | Insurance | ← `claims_history`; → `combined_ratio` |
| 25.11 | `combined_ratio` | Combined ratio | Insurance | ← `loss_ratio`; → `solvency_capital` |
| 25.12 | `solvency_capital` | Solvency capital | Insurance | ← `combined_ratio`; → `reinsurance_parameters` |
| 25.13 | `cat_bond_parameters` | Cat bonds | Insurance | → `capital_inflow`; ← `reinsurance_parameters` |
| 25.14 | `parametric_insurance` | Parametric insurance | Insurance | → `insurance_premiums`; ← `physical_risk_score` |
| 25.15 | `microinsurance` | Microinsurance | Insurance | → `insurance_premiums`; ← `household_income` |
| 25.16 | `weather_derivatives` | Weather derivatives | Insurance | → `financial_hedge`; ← `extreme_weather_events` |
| 25.17 | `climate_risk_disclosure` | TCFD | Insurance | → `compliance_cost`; ← `physical_risk_score` |

---

## CATEGORY 26: CARBON MARKET METHODOLOGY (20 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 26.1 | `additionality_test` | Additionality | Carbon | → `carbon_credit_issuance`; ← `baseline_emissions` |
| 26.2 | `baseline_methodology` | Baseline | Carbon | → `baseline_emissions`; ← `mrv_parameters` |
| 26.3 | `baseline_emissions` | Baseline emissions | Carbon | → `additionality_test`; ← `baseline_methodology` |
| 26.4 | `leakage_parameters` | Leakage | Carbon | → `carbon_credit_issuance`; ← `baseline_emissions` |
| 26.5 | `permanence_parameters` | Permanence | Carbon | → `carbon_credit_reversal_allowance` (the share times the credit volume); → `carbon_credit_issuance` |
| 26.6 | `buffer_pool_contribution` | Buffer pool | Carbon | **DEPRECATED (batch 69)** — duplicate of `permanence_parameters`; the equation `buffer_pool_contribution = permanence_parameters` was a rename, so both the equation and its edge are removed |
| 26.7 | `mrv_parameters` | MRV | Carbon | → `carbon_credit_issuance`; ← `corresponding_adjustment` |
| 26.8 | `corresponding_adjustment` | CA | Carbon | → `carbon_credit_issuance`; ← `article_6_2_parameters` |
| 26.9 | `article_6_2_parameters` | Article 6.2 | Carbon | → `corresponding_adjustment`; ← `article_6_4_parameters` |
| 26.10 | `article_6_4_parameters` | Article 6.4 | Carbon | → `corresponding_adjustment`; ← `cdm_methodologies` |
| 26.11 | `corsia_parameters` | CORSIA | Carbon | → `carbon_credit_issuance`; ← `aviation_fuel_demand` |
| 26.12 | `cdm_methodologies` | CDM | Carbon | → `carbon_credit_issuance`; ← `mrv_parameters` |
| 26.13 | `vcs_methodologies` | VCS | Carbon | → `carbon_credit_issuance`; ← `mrv_parameters` |
| 26.14 | `gold_standard_methodologies` | Gold Standard | Carbon | → `carbon_credit_issuance`; ← `mrv_parameters` |
| 26.15 | `carbon_credit_prices` | Credit prices | Carbon | → `carbon_revenue`; ← `carbon_credit_rating` |
| 26.16 | `carbon_credit_volumes` | Credit volumes | Carbon | → `carbon_revenue`; ← `carbon_credit_issuance` |
| 26.17 | `carbon_credit_retirement` | Retirement | Carbon | → `carbon_revenue`; ← `carbon_credit_volumes` |
| 26.18 | `carbon_credit_vintage` | Vintage | Carbon | → `carbon_credit_prices`; ← `carbon_credit_issuance` |
| 26.19 | `carbon_credit_rating` | Rating | Carbon | → `carbon_credit_prices`; ← `mrv_parameters` |
| 26.20 | `carbon_credit_insurance` | Insurance | Carbon | → `carbon_credit_rating`; ← `permanence_parameters` |

---

## CATEGORY 27: CLIMATE ADAPTATION & RESILIENCE (20 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 27.1 | `adaptation_costs` | Adaptation costs | Adaptation | → `total_cost`; ← `adaptation_measures` |
| 27.2 | `adaptation_benefits` | Adaptation benefits | Adaptation | → `cost_benefit_ratio`; ← `adaptation_measures` |
| 27.3 | `resilience_investment` | Resilience investment | Adaptation | → `adaptive_capacity`; ← `adaptation_costs` |
| 27.4 | `climate_proofing_requirements` | Climate proofing | Adaptation | → `compliance_cost`; ← `sea_level_rise` |
| 27.5 | `sea_level_rise` | SLR | Adaptation | → `flood_risk`, `coastal_erosion`; ← `ssp_pathway` |
| 27.6 | `flood_risk` | Flood risk | Adaptation | → `exposure_index`; ← `sea_level_rise` |
| 27.7 | `storm_surge` | Storm surge | Adaptation | → `flood_risk`; ← `sea_level_rise` |
| 27.8 | `coastal_erosion` | Coastal erosion | Adaptation | → `exposure_index`; ← `sea_level_rise` |
| 27.9 | `drought_risk` | Drought risk | Adaptation | → `exposure_index`; ← `drought_frequency` |
| 27.10 | `heat_stress` | Heat stress | Adaptation | → `exposure_index`; ← `temperature_increase` |
| 27.11 | `wildfire_risk` | Wildfire risk | Adaptation | → `exposure_index`; ← `temperature_increase` |
| 27.12 | `landslide_risk` | Landslide risk | Adaptation | → `exposure_index`; ← `precipitation_multiplier` |
| 27.13 | `glacial_lake_outburst` | GLOF | Adaptation | → `flood_risk`; ← `temperature_increase` |
| 27.14 | `adaptation_measures` | Adaptation measures | Adaptation | → `adaptation_costs`, `adaptation_benefits`; ← `resilience_investment` |
| 27.15 | `maladaptation_risk` | Maladaptation | Adaptation | → `adaptation_costs`; ← `adaptation_measures` |
| 27.16 | `resilience_metrics` | Resilience metrics | Adaptation | ← `adaptive_capacity`; → `resilience_investment` |
| 27.17 | `adaptive_capacity` | Adaptive capacity | Adaptation | → `resilience_metrics`; ← `resilience_investment` |
| 27.18 | `vulnerability_index` | Vulnerability | Adaptation | → `exposure_index`; ← `adaptive_capacity` |
| 27.19 | `exposure_index` | Exposure | Adaptation | → `vulnerability_index`; ← `flood_risk` |
| 27.20 | `risk_transfer_mechanisms` | Risk transfer | Adaptation | → `insurance_premiums`; ← `vulnerability_index` |

---

## CATEGORY 28: LAND USE & COMMUNITY (20 parameters)

| ID | Parameter | Definition | Equation System | Equations / Connected Parameters |
|---|---|---|---|---|
| 28.1 | `land_availability` | Land availability | Land | → `solar_pv_land_constraint`, `wind_onshore_capacity`; ← `protected_areas` |
| 28.2 | `land_use_conflicts` | Land use conflicts | Land | → `land_acquisition_costs`; ← `traditional_land_use` |
| 28.3 | `land_rights` | Land rights | Land | → `land_acquisition_costs`; ← `land_tenure` |
| 28.4 | `land_tenure` | Land tenure | Land | → `land_rights`; ← `traditional_land_use` |
| 28.5 | `land_acquisition_costs` | Land costs | Land, Cost | → `capex_solar_pv`; ← `land_use_conflicts` |
| 28.6 | `resettlement_costs` | Resettlement | Land, Cost | → `total_cost`; ← `resettlement_requirements` |
| 28.7 | `compensation_rates` | Compensation | Land, Cost | → `resettlement_costs`; ← `land_acquisition_costs` |
| 28.8 | `community_benefit_sharing` | Benefit sharing | Land, Financial | ← `community_benefit_share_of_revenue`; its former `local_employment_targets` edge was removed in batch 70 with that tombstone |
| 28.9 | `local_content_requirements` | Local content | Land, Policy | → `local_content_employment`; ← `regulatory_predictability` |
| 28.10 | `local_employment_targets` | Local employment | Land, Employment | **DEPRECATED (batch 70)** — the catalog's second "Local employment" row (19.25 is the first); `local_employment_share` is canonical |
| 28.11 | `community_development_funds` | Community funds | Land, Financial | → `community_benefit_sharing`; ← `local_content_requirements` |
| 28.12 | `fpic_requirements` | FPIC | Land, Compliance | → `land_acquisition_costs`; ← `undrip_compliance` |
| 28.13 | `traditional_land_use` | Traditional use | Land | → `land_use_conflicts`; ← `land_tenure` |
| 28.14 | `sacred_sites` | Sacred sites | Land | → `land_use_conflicts`; ← `cultural_heritage_impact` |
| 28.15 | `archaeological_sites` | Archaeology | Land | → `land_use_conflicts`; ← `cultural_heritage_impact` |
| 28.16 | `protected_areas` | Protected areas | Land | → `land_availability`; ← `biodiversity_impact` |
| 28.17 | `buffer_zones` | Buffer zones | Land | → `land_availability`; ← `protected_areas` |
| 28.18 | `conservation_easements` | Easements | Land | → `land_availability`; ← `protected_areas` |
| 28.19 | `land_aggregation` | Land aggregation | Land | → `land_acquisition_costs`; ← `land_availability` |
| 28.20 | `land_use_planning` | Land use planning | Land | → `land_availability`; ← `urbanisation_rate` |

---

## Summary of the Parameter-Equation Web

| Category | Parameters | Equation Systems Involved | Connected Parameters |
|---|---|---|---|
| **1. Demand-Side** | 43 | 8 systems | ~180 connections |
| **2. Supply-Side** | 83 | 12 systems | ~340 connections |
| **3. Cost** | 45 | 10 systems | ~200 connections |
| **4. Policy** | 42 | 12 systems | ~170 connections |
| **5. Transmission** | 24 | 6 systems | ~90 connections |
| **6. Sector Coupling** | 59 | 10 systems | ~250 connections |
| **7. Climate** | 21 | 7 systems | ~90 connections |
| **8. Outage** | 30 | 6 systems | ~120 connections |
| **9. Macroeconomic** | 51 | 8 systems | ~180 connections |
| **10. Investment** | 25 | 4 systems | ~70 connections |
| **11. Operational** | 24 | 7 systems | ~100 connections |
| **12. Spatial/Temporal** | 16 | 4 systems | ~50 connections |
| **13. Market Design** | 15 | 5 systems | ~60 connections |
| **14. Combined** | 15 | 4 systems | ~30 connections |
| **15. Tax** | 25 | 4 systems | ~80 connections |
| **16. Regulatory Finance** | 25 | 3 systems | ~60 connections |
| **17. Contract** | 33 | 3 systems | ~90 connections |
| **18. Env/Social** | 39 | 3 systems | ~90 connections |
| **19. Just Transition** | 28 | 2 systems | ~70 connections |
| **20. Consumer Protection** | 22 | 2 systems | ~50 connections |
| **21. Digital** | 22 | 2 systems | ~40 connections |
| **22. Geopolitical** | 21 | 2 systems | ~50 connections |
| **23. Asset** | 19 | 2 systems | ~40 connections |
| **24. Market Ops** | 20 | 2 systems | ~40 connections |
| **25. Insurance** | 17 | 2 systems | ~35 connections |
| **26. Carbon Market** | 20 | 2 systems | ~45 connections |
| **27. Adaptation** | 20 | 2 systems | ~50 connections |
| **28. Land Use** | 20 | 3 systems | ~50 connections |
| **TOTAL** | **784** | **20 systems** | **~2,500 connections** |

---

## How to Use This Table

**For development**: Each row is an implementation task. The equation system column tells you which PRG system the parameter belongs to; the connected parameters column tells you which edges to create in `prg.yaml`.

**For validation**: Each row can be checked for: (a) does the parameter exist in the catalog? (b) does the equation exist in the library? (c) do the connections appear as edges in the graph?

**For users**: This table is the answer to "what does this parameter affect?" and "what affects this parameter?" — the two questions every scenario explorer asks.

**For documentation**: Each row is a paragraph in the user guide, a note in the API reference, and an entry in the parameter dictionary.

**For QA**: The `structure_issues` check in `ParameterGraph` can be extended to verify that every declared connection in this table appears as an actual edge in the PRG — closing the loop between specification and implementation.