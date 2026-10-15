# Alea: The Definitive Master Parameter Catalog

## Complete Single-Table Reference of All 784 Parameters, Algorithms, and Implementations

---

## Table Structure

Each row contains: **ID** | **Category** | **Parameter** | **Description** | **Algorithm** | **Python Implementation** | **Status** | **Primary Users** | **Priority**

**Status codes**: ✅ Existing (available now) | 🔨 To Build (development required) | 🔗 Integrate (exists externally, needs integration)
**Priority**: P1 (Critical, Phase 1) | P2 (Important, Phase 2) | P3 (Extended, Phase 3)

---

## CATEGORY 1: DEMAND-SIDE PARAMETERS (43)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 1.1 | Demand | `demand_growth_rate` | Annual electricity demand growth rate | Logistic / Gompertz growth curve | `scipy.optimize.curve_fit` | 🔨 | All | P1 |
| 1.2 | Demand | `demand_growth_profile` | Shape of growth curve | Growth curve shape fitting | `scipy.optimize.curve_fit` | 🔨 | All | P1 |
| 1.3 | Demand | `demand_growth_start_year` | Year growth trajectory begins | Temporal trajectory anchoring | `numpy` indexing | 🔨 | All | P1 |
| 1.4 | Demand | `demand_growth_end_year` | Year growth trajectory ends | Temporal trajectory anchoring | `numpy` indexing | 🔨 | All | P1 |
| 1.5 | Demand | `peak_demand_multiplier` | Scaling factor for peak demand | Peak-load scaling with coincidence factor | `n.loads_t.p_set` scaling | ✅ | Utilities | P1 |
| 1.6 | Demand | `load_factor_override` | Override default load factor | Load profile reshaping | To be built | 🔨 | Utilities | P2 |
| 1.7 | Demand | `industrial_demand_share` | Share of demand from industry | Sectoral disaggregation (IEA/MAED) | PyPSA-Earth `build_industry_demand` | ✅ | Planners | P1 |
| 1.8 | Demand | `residential_demand_share` | Share of demand from households | Sectoral disaggregation | PyPSA-Earth `build_demand` | ✅ | Planners | P1 |
| 1.9 | Demand | `commercial_demand_share` | Share of demand from commercial | Sectoral disaggregation | PyPSA-Earth `build_demand` | ✅ | Planners | P1 |
| 1.10 | Demand | `agricultural_demand_share` | Share of demand from agriculture | Sectoral disaggregation | PyPSA-Earth `build_demand` | ✅ | Planners | P1 |
| 1.11 | Demand | `mining_demand_growth` | Additional mining load growth | Mining load profiling | To be built | 🔨 | Mining | P2 |
| 1.12 | Demand | `data_centre_demand` | New data centre load | Data centre load profiling (constant + burst) | To be built | 🔨 | Telecom | P2 |
| 1.13 | Demand | `desalination_demand` | Desalination electricity demand | Desalination load model (RO energy curve) | To be built | 🔨 | Water, Cities | P2 |
| 1.14 | Demand | `hydrogen_production_demand` | Electricity for hydrogen production | Hydrogen demand integration | PyPSA-Earth sector-coupled | ✅ | Industry | P1 |
| 1.15 | Demand | `demand_response_potential` | Share of demand that is flexible | Elasticity-based DR optimisation | `scipy.optimize.linprog` | 🔨 | Utilities | P2 |
| 1.16 | Demand | `demand_response_cost` | Cost of demand response | DR cost curve | To be built | 🔨 | Utilities | P2 |
| 1.17 | Demand | `load_shifting_capability` | Hours of load shifting possible | MILP with time windows | `linopy` | 🔨 | Utilities | P2 |
| 1.18 | Demand | `interruptible_load_share` | Share of load that can be curtailed | Curtailable load constraint | `n.loads` p_set reduction | ✅ | Utilities | P2 |
| 1.19 | Demand | `smart_metering_penetration` | Smart meter coverage | Bottom-up load synthesis | `numpy` Monte Carlo | 🔨 | Utilities | P2 |
| 1.20 | Demand | `time_of_use_tariff_adoption` | ToU tariff adoption rate | Price elasticity matrix | To be built | 🔨 | Regulators | P2 |
| 1.21 | Demand | `electrification_rate_target` | Target electrification rate | OnSSET-style geospatial | `onsset` | 🔗 | Policymakers | P1 |
| 1.22 | Demand | `electrification_timeline` | Year to reach target | Adoption diffusion (Bass) | To be built | 🔨 | Policymakers | P1 |
| 1.23 | Demand | `grid_extension_rate` | Annual grid connection rate | Grid extension cost curve | To be built | 🔨 | Utilities | P1 |
| 1.24 | Demand | `mini_grid_deployment` | Mini-grid capacity added | HOMER-style mini-grid sizing | `HOMER` / `pypsa` isolated nodes | 🔗 | Developers | P1 |
| 1.25 | Demand | `solar_home_system_deployment` | SHS units added | SHS adoption diffusion (Bass) | To be built | 🔨 | Households | P1 |
| 1.26 | Demand | `cooking_lpg_penetration` | LPG cooking access | Fuel stacking model | To be built | 🔨 | Households | P2 |
| 1.27 | Demand | `clean_cooking_target` | Clean cooking access target | Fuel transition model | To be built | 🔨 | Policymakers | P2 |
| 1.28 | Demand | `heat_pump_adoption` | Heat pump penetration | Temperature-dependent COP | To be built | 🔨 | Households | P2 |
| 1.29 | Demand | `electric_vehicle_adoption` | EV share of vehicle stock | Monte Carlo driving patterns | `mobev` | 🔗 | Transport | P2 |
| 1.30 | Demand | `v2g_adoption` | V2G-capable EV share | Bidirectional charging MILP | To be built | 🔨 | Utilities | P3 |
| 1.31 | Demand | `rooftop_solar_adoption` | Rooftop solar penetration | Building footprint + shading | `rasterio` + `geopandas` | 🔨 | Households | P2 |
| 1.32 | Demand | `battery_storage_adoption` | Behind-the-meter battery penetration | Behind-the-meter dispatch | To be built | 🔨 | Households | P2 |
| 1.33 | Demand | `industrial_electrification` | Industrial process electrification | Industrial process electrification | To be built | 🔨 | Industry | P2 |
| 1.34 | Demand | `agricultural_irrigation_load` | Irrigation pumping load | Irrigation energy model | To be built | 🔨 | Agriculture | P2 |
| 1.35 | Demand | `post_harvest_processing_load` | Post-harvest processing load | Processing energy model | To be built | 🔨 | Agriculture | P3 |
| 1.36 | Demand | `cold_storage_load` | Cold chain energy demand | Cold chain model | To be built | 🔨 | Agriculture, Health | P2 |
| 1.37 | Demand | `fishing_community_load` | Coastal fishing load | Load profile | To be built | 🔨 | Fisheries | P3 |
| 1.38 | Demand | `tourism_load` | Tourism seasonal load | Seasonal load profile | To be built | 🔨 | Tourism | P3 |
| 1.39 | Demand | `construction_load` | Temporary construction load | Temporary load model | To be built | 🔨 | Construction | P3 |
| 1.40 | Demand | `temporary_camp_load` | Refugee camp load | Camp load model | To be built | 🔨 | Humanitarian | P2 |
| 1.41 | Demand | `emergency_shelter_load` | Emergency shelter load | Emergency load model | To be built | 🔨 | Humanitarian | P3 |
| 1.42 | Demand | `water_pumping_load` | Water utility pumping | Pumping energy model | To be built | 🔨 | Water | P2 |
| 1.43 | Demand | `wastewater_treatment_load` | Wastewater treatment energy | Treatment energy model | To be built | 🔨 | Water | P2 |

---

## CATEGORY 2: SUPPLY-SIDE / GENERATION (83)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 2.1 | Supply | `coal_capacity` | Installed coal capacity | Capacity constraint | `n.generators.p_nom` | ✅ | Utilities | P1 |
| 2.2 | Supply | `coal_eaf` | Coal energy availability factor | Availability factor | `n.generators.p_max_pu` | ✅ | Utilities | P1 |
| 2.3 | Supply | `coal_retirement_schedule` | Coal retirement years | Retirement scheduling MILP | `linopy` binary retirement | 🔨 | Planners | P1 |
| 2.4 | Supply | `coal_retirement_rate` | Annual coal retirement | Age-based retirement curve | To be built | 🔨 | Planners | P1 |
| 2.5 | Supply | `coal_new_build` | New coal capacity allowed | Investment variable | `n.generators.p_nom_extendable` | ✅ | Planners | P1 |
| 2.6 | Supply | `coal_ccs_adoption` | Coal with CCS share | CCS retrofit model | To be built | 🔨 | Planners | P3 |
| 2.7 | Supply | `gas_capacity` | Installed gas capacity | Capacity constraint | `n.generators.p_nom` | ✅ | Utilities | P1 |
| 2.8 | Supply | `gas_eaf` | Gas energy availability factor | Availability factor | `n.generators.p_max_pu` | ✅ | Utilities | P1 |
| 2.9 | Supply | `gas_new_build` | New gas capacity allowed | Investment variable | `n.generators.p_nom_extendable` | ✅ | Planners | P1 |
| 2.10 | Supply | `gas_ccs_adoption` | Gas with CCS share | CCS retrofit model | To be built | 🔨 | Planners | P3 |
| 2.11 | Supply | `oil_capacity` | Installed oil capacity | Capacity constraint | `n.generators.p_nom` | ✅ | Utilities | P2 |
| 2.12 | Supply | `oil_eaf` | Oil energy availability factor | Availability factor | `n.generators.p_max_pu` | ✅ | Utilities | P2 |
| 2.13 | Supply | `nuclear_capacity` | Installed nuclear capacity | Baseload + refuelling cycles | To be built | 🔨 | Planners | P3 |
| 2.14 | Supply | `nuclear_new_build` | New nuclear capacity | Investment variable | `n.generators.p_nom_extendable` | ✅ | Planners | P3 |
| 2.15 | Supply | `nuclear_lead_time` | Nuclear construction lead time | Construction lead-time constraint | To be built | 🔨 | Planners | P3 |
| 2.16 | Supply | `solar_pv_capacity` | Installed solar PV capacity | Capacity constraint | `n.generators.p_nom` | ✅ | All | P1 |
| 2.17 | Supply | `solar_pv_capacity_factor` | Solar PV capacity factor | Renewable profile scaling | `n.generators_t.p_max_pu` | ✅ | All | P1 |
| 2.18 | Supply | `solar_pv_cost` | Solar PV capital cost | Capital cost | `n.generators.capital_cost` | ✅ | All | P1 |
| 2.19 | Supply | `solar_pv_learning_rate` | Annual cost reduction | Endogenous learning curve | To be built | 🔨 | Planners | P2 |
| 2.20 | Supply | `solar_pv_max_build` | Maximum annual solar build | Annual build constraint | To be built | 🔨 | Planners | P2 |
| 2.21 | Supply | `solar_pv_land_constraint` | Land available for solar | Land availability constraint | `geopandas` + `rasterio` | 🔨 | Planners | P2 |
| 2.22 | Supply | `wind_onshore_capacity` | Installed onshore wind | Capacity constraint | `n.generators.p_nom` | ✅ | All | P1 |
| 2.23 | Supply | `wind_onshore_cost` | Onshore wind capital cost | Capital cost | `n.generators.capital_cost` | ✅ | All | P1 |
| 2.24 | Supply | `wind_offshore_capacity` | Installed offshore wind | Capacity constraint | `n.generators.p_nom` | ✅ | All | P2 |
| 2.25 | Supply | `wind_offshore_cost` | Offshore wind capital cost | Capital cost | `n.generators.capital_cost` | ✅ | All | P2 |
| 2.26 | Supply | `wind_offshore_platform` | Platform type | Floating vs. fixed platform | To be built | 🔨 | Developers | P2 |
| 2.27 | Supply | `hydro_capacity` | Installed hydropower | Capacity constraint | `n.generators.p_nom` | ✅ | All | P1 |
| 2.28 | Supply | `hydro_capacity_factor` | Hydro capacity factor | Hydro profile scaling | `n.generators_t.p_max_pu` | ✅ | All | P1 |
| 2.29 | Supply | `hydro_new_build` | New hydro capacity | Investment variable | `n.generators.p_nom_extendable` | ✅ | Planners | P1 |
| 2.30 | Supply | `hydro_reservoir_level` | Initial reservoir level | Reservoir operation (SDP) | `rtc-tools` | 🔗 | Utilities | P2 |
| 2.31 | Supply | `hydro_drought_multiplier` | Drought impact multiplier | Hydrological drought scenario | CMIP6-based inflow | 🔨 | Planners | P2 |
| 2.32 | Supply | `geothermal_capacity` | Installed geothermal | Flash steam / binary cycle | To be built | 🔨 | Developers | P1 |
| 2.33 | Supply | `geothermal_cost` | Geothermal capital cost | Capital cost | To be built | 🔨 | Developers | P1 |
| 2.34 | Supply | `geothermal_drilling_success` | Drilling success rate | Bayesian drilling success | `geoPFA` | 🔗 | Developers | P2 |
| 2.35 | Supply | `biomass_capacity` | Installed biomass capacity | Combustion / gasification | To be built | 🔨 | Developers | P2 |
| 2.36 | Supply | `biomass_feedstock_cost` | Biomass feedstock cost | Feedstock cost | To be built | 🔨 | Developers | P2 |
| 2.37 | Supply | `biomass_sustainability_limit` | Maximum sustainable biomass | LCA-based constraint | To be built | 🔨 | Planners | P2 |
| 2.38 | Supply | `csp_capacity` | Installed CSP capacity | CSP with thermal storage | To be built | 🔨 | Developers | P2 |
| 2.39 | Supply | `csp_storage_hours` | CSP thermal storage | Thermal storage dispatch | To be built | 🔨 | Developers | P2 |
| 2.40 | Supply | `marine_wave_capacity` | Installed wave capacity | Wave energy conversion | `MHKiT` | 🔗 | Developers | P3 |
| 2.41 | Supply | `marine_tidal_capacity` | Installed tidal capacity | Tidal energy conversion | `MHKiT` | 🔗 | Developers | P3 |
| 2.42 | Supply | `marine_otec_capacity` | Installed OTEC capacity | OTEC thermodynamic model | To be built | 🔨 | Developers | P3 |
| 2.43 | Supply | `battery_capacity` | Installed battery capacity | Storage constraint | `n.storage_units.p_nom` | ✅ | All | P1 |
| 2.44 | Supply | `battery_duration` | Battery duration | Energy-to-power ratio | `n.storage_units.max_hours` | ✅ | All | P1 |
| 2.45 | Supply | `battery_cost` | Battery capital cost | Capital cost | `n.storage_units.capital_cost` | ✅ | All | P1 |
| 2.46 | Supply | `battery_learning_rate` | Annual cost reduction | Endogenous learning | To be built | 🔨 | Planners | P2 |
| 2.47 | Supply | `battery_round_trip_efficiency` | Round-trip efficiency | Efficiency | `n.storage_units.efficiency_store/dispatch` | ✅ | All | P1 |
| 2.48 | Supply | `phs_capacity` | Pumped hydro storage | Pumped hydro | `n.storage_units` carrier=PHS | ✅ | Utilities | P1 |
| 2.49 | Supply | `phs_duration` | PHS duration | PHS duration | `n.storage_units.max_hours` | ✅ | Utilities | P1 |
| 2.50 | Supply | `phs_cost` | PHS capital cost | PHS capital cost | `n.storage_units.capital_cost` | ✅ | Utilities | P2 |
| 2.51 | Supply | `hydrogen_storage_capacity` | Hydrogen storage | Salt cavern / depleted reservoir | PyPSA-Earth-Sec | ✅ | Industry | P2 |
| 2.52 | Supply | `hydrogen_storage_cost` | Hydrogen storage cost | Storage cost | PyPSA-Earth-Sec | ✅ | Industry | P2 |
| 2.53 | Supply | `thermal_storage_capacity` | Thermal storage | Thermal storage | `n.stores` carrier=thermal | ✅ | Industry | P2 |
| 2.54 | Supply | `thermal_storage_duration` | Thermal storage duration | Thermal duration | `n.stores.e_nom` | ✅ | Industry | P2 |
| 2.55 | Supply | `gravity_storage_capacity` | Gravity storage | Gravity storage dispatch | To be built | 🔨 | Developers | P3 |
| 2.56 | Supply | `compressed_air_capacity` | Compressed air storage | CAES thermodynamic | To be built | 🔨 | Developers | P3 |
| 2.57 | Supply | `flywheel_capacity` | Flywheel storage | Flywheel fast-response | To be built | 🔨 | Developers | P3 |
| 2.58 | Supply | `storage_duration_curve` | Storage energy-to-power ratio | Storage energy-to-power ratio | `n.stores.e_nom` | ✅ | All | P2 |
| 2.59 | Supply | `min_stable_level_coal` | Coal minimum stable level | MILP with big-M | `n.generators.p_min_pu` | ✅ | Utilities | P1 |
| 2.60 | Supply | `min_stable_level_gas` | Gas minimum stable level | MILP with big-M | `n.generators.p_min_pu` | ✅ | Utilities | P1 |
| 2.61 | Supply | `ramp_rate_coal` | Coal ramp rate | Ramp rate constraints | `n.generators.ramp_limit_up/down` | ✅ | Utilities | P1 |
| 2.62 | Supply | `ramp_rate_gas` | Gas ramp rate | Ramp rate constraints | `n.generators.ramp_limit_up/down` | ✅ | Utilities | P1 |
| 2.63 | Supply | `startup_cost_coal` | Coal start-up cost | Start-up cost | `n.generators.start_up_cost` | ✅ | Utilities | P1 |
| 2.64 | Supply | `startup_cost_gas` | Gas start-up cost | Start-up cost | `n.generators.start_up_cost` | ✅ | Utilities | P1 |
| 2.65 | Supply | `min_up_time_coal` | Coal minimum up time | Minimum up time | `n.generators.min_up_time` | ✅ | Utilities | P1 |
| 2.66 | Supply | `min_down_time_coal` | Coal minimum down time | Minimum down time | `n.generators.min_down_time` | ✅ | Utilities | P1 |
| 2.67 | Supply | `forced_outage_rate_coal` | Coal forced outage rate | Stochastic outage | Monte Carlo sampling | 🔨 | Utilities | P1 |
| 2.68 | Supply | `forced_outage_rate_gas` | Gas forced outage rate | Stochastic outage | Monte Carlo sampling | 🔨 | Utilities | P1 |
| 2.69 | Supply | `maintenance_schedule` | Planned maintenance timing | Maintenance scheduling MILP | `linopy` | 🔨 | Utilities | P2 |
| 2.70 | Supply | `plant_retirement_age` | Retirement age by technology | Age-based retirement curve | To be built | 🔨 | Planners | P2 |
| 2.71 | Supply | `life_extension_possible` | Life extension allowed | Life extension cost-benefit | To be built | 🔨 | Planners | P2 |
| 2.72 | Supply | `life_extension_cost` | Life extension cost | Life extension cost | To be built | 🔨 | Planners | P2 |
| 2.73 | Supply | `tidal_range_capacity` | Tidal range capacity | Tidal range model | To be built | 🔨 | Developers | P3 |
| 2.74 | Supply | `salinity_gradient_capacity` | Salinity gradient capacity | Salinity gradient model | To be built | 🔨 | Developers | P3 |
| 2.75 | Supply | `wave_energy_converter_type` | Wave energy converter type | WEC model | To be built | 🔨 | Developers | P3 |
| 2.76 | Supply | `biogas_capacity` | Biogas capacity | Biogas model | To be built | 🔨 | Agriculture | P2 |
| 2.77 | Supply | `landfill_gas_capacity` | Landfill gas capacity | LFG model | To be built | 🔨 | Cities | P2 |
| 2.78 | Supply | `waste_to_energy_capacity` | Waste-to-energy capacity | WtE model | To be built | 🔨 | Cities | P2 |
| 2.79 | Supply | `pyrolysis_capacity` | Pyrolysis capacity | Pyrolysis model | To be built | 🔨 | Industry | P3 |
| 2.80 | Supply | `gasification_capacity` | Gasification capacity | Gasification model | To be built | 🔨 | Industry | P3 |
| 2.81 | Supply | `hydrogen_fuel_cell_capacity` | Hydrogen fuel cell capacity | Fuel cell model | To be built | 🔨 | Transport | P2 |
| 2.82 | Supply | `small_modular_reactor_capacity` | SMR capacity | SMR model | To be built | 🔨 | Planners | P3 |
| 2.83 | Supply | `fusion_capacity` | Fusion capacity | Fusion model | To be built | 🔨 | Planners | P3 |

---

## CATEGORY 3: COST (45)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 3.1 | Cost | `capex_solar_pv` | Solar PV capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | All | P1 |
| 3.2 | Cost | `capex_wind_onshore` | Onshore wind capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | All | P1 |
| 3.3 | Cost | `capex_wind_offshore` | Offshore wind capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | All | P2 |
| 3.4 | Cost | `capex_hydro` | Hydropower capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | All | P1 |
| 3.5 | Cost | `capex_geothermal` | Geothermal capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Developers | P1 |
| 3.6 | Cost | `capex_biomass` | Biomass capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Developers | P2 |
| 3.7 | Cost | `capex_csp` | CSP capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Developers | P2 |
| 3.8 | Cost | `capex_coal` | Coal capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Planners | P1 |
| 3.9 | Cost | `capex_gas_ccgt` | Gas CCGT capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Planners | P1 |
| 3.10 | Cost | `capex_gas_ocgt` | Gas OCGT capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Planners | P1 |
| 3.11 | Cost | `capex_nuclear` | Nuclear capital cost | Capital cost parameter | `n.generators.capital_cost` | ✅ | Planners | P3 |
| 3.12 | Cost | `capex_battery` | Battery capital cost | Capital cost parameter | `n.storage_units.capital_cost` | ✅ | All | P1 |
| 3.13 | Cost | `capex_phs` | PHS capital cost | Capital cost parameter | `n.storage_units.capital_cost` | ✅ | Utilities | P2 |
| 3.14 | Cost | `capex_hydrogen_electrolyser` | Electrolyser capital cost | Capital cost parameter | `n.links.capital_cost` | ✅ | Industry | P2 |
| 3.15 | Cost | `capex_transmission` | Transmission line cost | Transmission line cost | `n.lines.capital_cost` | ✅ | Planners | P1 |
| 3.16 | Cost | `capex_distribution` | Distribution network cost | Distribution network cost | To be built | 🔨 | Utilities | P2 |
| 3.17 | Cost | `capex_interconnector` | Cross-border interconnector | Cross-border interconnector | `n.links.capital_cost` | ✅ | Planners | P1 |
| 3.18 | Cost | `opex_fixed_solar` | Solar fixed O&M | Fixed O&M | `n.generators.capital_cost` annualised | ✅ | All | P1 |
| 3.19 | Cost | `opex_fixed_wind` | Wind fixed O&M | Fixed O&M | `n.generators.capital_cost` annualised | ✅ | All | P1 |
| 3.20 | Cost | `opex_fixed_coal` | Coal fixed O&M | Fixed O&M | `n.generators.capital_cost` annualised | ✅ | Utilities | P1 |
| 3.21 | Cost | `opex_fixed_gas` | Gas fixed O&M | Fixed O&M | `n.generators.capital_cost` annualised | ✅ | Utilities | P1 |
| 3.22 | Cost | `opex_variable_coal` | Coal variable O&M | Variable O&M | `n.generators.marginal_cost` | ✅ | Utilities | P1 |
| 3.23 | Cost | `opex_variable_gas` | Gas variable O&M | Variable O&M | `n.generators.marginal_cost` | ✅ | Utilities | P1 |
| 3.24 | Cost | `opex_variable_battery` | Battery variable O&M | Variable O&M | `n.storage_units.marginal_cost` | ✅ | All | P2 |
| 3.25 | Cost | `opex_variable_electrolyser` | Electrolyser variable O&M | Variable O&M | `n.links.marginal_cost` | ✅ | Industry | P2 |
| 3.26 | Cost | `fuel_cost_coal` | Coal fuel cost | Fuel cost | `n.generators.marginal_cost` | ✅ | Utilities | P1 |
| 3.27 | Cost | `fuel_cost_gas` | Gas fuel cost | Fuel cost | `n.generators.marginal_cost` | ✅ | Utilities | P1 |
| 3.28 | Cost | `fuel_cost_oil` | Oil fuel cost | Fuel cost | `n.generators.marginal_cost` | ✅ | Utilities | P2 |
| 3.29 | Cost | `fuel_cost_nuclear` | Nuclear fuel cost | Nuclear fuel cost | `n.generators.marginal_cost` | ✅ | Planners | P3 |
| 3.30 | Cost | `fuel_cost_biomass` | Biomass fuel cost | Biomass fuel cost | `n.generators.marginal_cost` | ✅ | Developers | P2 |
| 3.31 | Cost | `fuel_cost_hydrogen` | Hydrogen fuel cost | Hydrogen fuel cost | `n.generators.marginal_cost` | ✅ | Industry | P2 |
| 3.32 | Cost | `fuel_price_escalation` | Annual fuel price escalation | Fuel price escalation | Time-dependent marginal cost | 🔨 | All | P2 |
| 3.33 | Cost | `fuel_price_volatility` | Fuel price volatility | Stochastic fuel price (GBM+jumps) | `numpy` GBM + Poisson jumps | 🔨 | All | P2 |
| 3.34 | Cost | `discount_rate` | Social discount rate | Social discount rate | `n.optimize(discount_rate=...)` | ✅ | Planners | P1 |
| 3.35 | Cost | `weighted_average_cost_of_capital` | WACC | WACC | `wacc-estimator` | 🔗 | Investors | P1 |
| 3.36 | Cost | `cost_of_equity` | Cost of equity | CAPM-based cost of equity | `numpy_financial` | 🔨 | Investors | P1 |
| 3.37 | Cost | `cost_of_debt` | Cost of debt | Debt pricing model | To be built | 🔨 | Investors | P1 |
| 3.38 | Cost | `debt_equity_ratio` | Debt-to-equity ratio | Optimal capital structure | To be built | 🔨 | Investors | P1 |
| 3.39 | Cost | `carbon_price` | Carbon price | Carbon price | `n.generators.marginal_cost += carbon_price * co2` | ✅ | Policymakers | P1 |
| 3.40 | Cost | `carbon_price_escalation` | Annual carbon price increase | Carbon price trajectory | `peltwtcn` | 🔗 | Policymakers | P2 |
| 3.41 | Cost | `carbon_price_coverage` | Share of emissions covered | Partial carbon price coverage | Sectoral constraint | 🔨 | Policymakers | P2 |
| 3.42 | Cost | `value_of_lost_load` | Value of lost load | VoLL as load shedding cost | `n.generators` carrier=load | ✅ | Utilities | P1 |
| 3.43 | Cost | `reserve_margin_requirement` | Minimum reserve margin | Reserve margin constraint | `linopy` constraint | 🔨 | Utilities | P1 |
| 3.44 | Cost | `planning_reserve_margin` | Planning reserve margin | Planning reserve margin | `linopy` constraint | 🔨 | Planners | P1 |
| 3.45 | Cost | `inertia_requirement` | Minimum system inertia | System inertia constraint | To be built | 🔨 | Utilities | P2 |

---

## CATEGORY 4: POLICY & REGULATORY (42)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 4.1 | Policy | `carbon_tax_rate` | Carbon tax rate | Carbon tax | `n.generators.marginal_cost` adjustment | ✅ | Policymakers | P1 |
| 4.2 | Policy | `carbon_tax_start_year` | Year carbon tax begins | Temporal carbon tax | `n.snapshots` indexing | 🔨 | Policymakers | P2 |
| 4.3 | Policy | `carbon_tax_coverage` | Sectors covered by carbon tax | Sectoral carbon tax | Sectoral constraint | 🔨 | Policymakers | P2 |
| 4.4 | Policy | `ets_enabled` | Emissions trading system | Emissions trading system | To be built | 🔨 | Policymakers | P2 |
| 4.5 | Policy | `ets_cap` | ETS emissions cap | ETS cap constraint | To be built | 🔨 | Policymakers | P2 |
| 4.6 | Policy | `ets_cap_reduction_rate` | Annual cap reduction | Annual cap reduction | To be built | 🔨 | Policymakers | P2 |
| 4.7 | Policy | `carbon_border_adjustment` | CBAM exposure | CBAM impact model | `stanzaapi-cbam-carbon` | 🔗 | Policymakers | P2 |
| 4.8 | Policy | `cbam_price` | CBAM certificate price | CBAM certificate price | `stanzaapi-cbam-carbon` | 🔗 | Policymakers | P2 |
| 4.9 | Policy | `article_6_credits` | Paris Agreement Article 6 credits | Paris Agreement credits | To be built | 🔨 | Policymakers | P3 |
| 4.10 | Policy | `voluntary_carbon_market` | VCM participation | VCM participation | To be built | 🔨 | Carbon | P2 |
| 4.11 | Policy | `renewable_target` | Renewable energy target | Renewable portfolio standard | `n.generators` carrier constraint | ✅ | Policymakers | P1 |
| 4.12 | Policy | `renewable_target_year` | Year to reach target | Temporal renewable target | `n.snapshots` indexing | 🔨 | Policymakers | P2 |
| 4.13 | Policy | `re_target_carrier` | Which renewables count | Which renewables count | `n.generators.carrier` filter | ✅ | Policymakers | P2 |
| 4.14 | Policy | `feed_in_tariff` | Feed-in tariff rate | FiT cost allocation | To be built | 🔨 | Regulators | P1 |
| 4.15 | Policy | `fit_duration` | FiT contract duration | FiT contract duration | To be built | 🔨 | Regulators | P2 |
| 4.16 | Policy | `fit_capacity_cap` | FiT capacity cap | FiT capacity cap | To be built | 🔨 | Regulators | P2 |
| 4.17 | Policy | `auction_mechanism` | Auction type | Renewable auction simulation | To be built | 🔨 | Regulators | P1 |
| 4.18 | Policy | `auction_volume` | Annual auction volume | Auction volume scheduling | To be built | 🔨 | Regulators | P1 |
| 4.19 | Policy | `auction_price_cap` | Auction price ceiling | Auction price ceiling | To be built | 🔨 | Regulators | P2 |
| 4.20 | Policy | `tax_incentives` | Tax incentives for renewables | Tax incentive cost model | To be built | 🔨 | Policymakers | P2 |
| 4.21 | Policy | `accelerated_depreciation` | Accelerated depreciation | Depreciation schedule model | To be built | 🔨 | Developers | P2 |
| 4.22 | Policy | `import_duty_exemption` | Import duty exemption | Import duty cost model | To be built | 🔨 | Developers | P2 |
| 4.23 | Policy | `local_content_requirement` | Local content requirement | Local content cost premium | To be built | 🔨 | Regulators | P2 |
| 4.24 | Policy | `market_structure` | Electricity market structure | Market structure simulation | `ASSUME` | 🔗 | Regulators | P1 |
| 4.25 | Policy | `unbundling_status` | Utility unbundling | Unbundling impact model | To be built | 🔨 | Regulators | P2 |
| 4.26 | Policy | `wheeling_charges` | Transmission wheeling charge | Wheeling charge model | `n.links.marginal_cost` | ✅ | Regulators | P1 |
| 4.27 | Policy | `distribution_wheeling_charges` | Distribution wheeling charge | Distribution wheeling charge | `n.links.marginal_cost` | ✅ | Regulators | P2 |
| 4.28 | Policy | `cross_subsidy_level` | Cross-subsidy in tariffs | Cross-subsidy redistribution | To be built | 🔨 | Regulators | P2 |
| 4.29 | Policy | `tariff_structure` | Tariff design | Tariff design optimisation | To be built | 🔨 | Regulators | P1 |
| 4.30 | Policy | `regulated_tariff_rate` | Regulated tariff | Regulated tariff | `n.loads.marginal_cost` | ✅ | Regulators | P1 |
| 4.31 | Policy | `tariff_indexation` | Tariff indexation | Tariff indexation | To be built | 🔨 | Regulators | P2 |
| 4.32 | Policy | `ppa_guarantees` | Government PPA guarantees | Government PPA guarantees | To be built | 🔨 | Regulators | P2 |
| 4.33 | Policy | `contract_for_difference` | CfD mechanism | CfD settlement | To be built | 🔨 | Regulators | P2 |
| 4.34 | Policy | `capacity_market` | Capacity market | Capacity market clearing | `pyshop` | 🔗 | Regulators | P2 |
| 4.35 | Policy | `capacity_price` | Capacity market clearing price | Capacity market clearing price | `pyshop` | 🔗 | Regulators | P2 |
| 4.36 | Policy | `ancillary_services_market` | Ancillary services market | Ancillary services clearing | `ASAM` | 🔗 | Regulators | P2 |
| 4.37 | Policy | `fossil_fuel_subsidies` | Fossil fuel subsidies | Subsidy reform impact | To be built | 🔨 | Policymakers | P1 |
| 4.38 | Policy | `renewable_subsidies` | Renewable energy subsidies | Renewable subsidy cost | To be built | 🔨 | Policymakers | P2 |
| 4.39 | Policy | `electricity_subsidies` | Consumer electricity subsidies | Consumer subsidy model | To be built | 🔨 | Policymakers | P1 |
| 4.40 | Policy | `lpg_subsidies` | LPG subsidy | LPG subsidy model | To be built | 🔨 | Policymakers | P3 |
| 4.41 | Policy | `mini_grid_subsidies` | Mini-grid capital subsidy | Mini-grid subsidy | To be built | 🔨 | Policymakers | P2 |
| 4.42 | Policy | `shs_subsidies` | Solar home system subsidy | SHS subsidy model | To be built | 🔨 | Policymakers | P2 |

---

## CATEGORY 5: TRANSMISSION & GRID (24)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 5.1 | Grid | `transmission_expansion_allowed` | Allow transmission expansion | Investment variable | `n.lines.s_nom_extendable = True` | ✅ | Planners | P1 |
| 5.2 | Grid | `transmission_cost_multiplier` | Transmission cost multiplier | Cost scaling | `n.lines.capital_cost` | ✅ | Planners | P1 |
| 5.3 | Grid | `transmission_loss_factor` | Average transmission loss | Loss approximation | `n.optimize(transmission_losses=True)` | ✅ | Planners | P1 |
| 5.4 | Grid | `transmission_capacity_factor` | Transmission utilisation | Utilisation | `n.lines.s_max_pu` | ✅ | Planners | P1 |
| 5.5 | Grid | `hvdc_share` | Share of HVDC in new lines | HVDC vs. HVAC | To be built | 🔨 | Planners | P2 |
| 5.6 | Grid | `ac_voltage_limit` | Maximum AC voltage | Voltage level selection | To be built | 🔨 | Planners | P2 |
| 5.7 | Grid | `transmission_lead_time` | Transmission construction time | Project scheduling | To be built | 🔨 | Planners | P2 |
| 5.8 | Grid | `right_of_way_cost` | Right-of-way cost | Right-of-way cost | To be built | 🔨 | Planners | P2 |
| 5.9 | Grid | `cross_border_permitting_time` | Cross-border permitting | Permitting delay model | To be built | 🔨 | Planners | P2 |
| 5.10 | Grid | `distribution_loss_factor` | Distribution losses | Distribution loss model | To be built | 🔨 | Utilities | P2 |
| 5.11 | Grid | `distribution_capex_per_connection` | Distribution cost per connection | Distribution cost curve | To be built | 🔨 | Utilities | P2 |
| 5.12 | Grid | `grid_connection_cost` | Grid connection cost | Connection cost | To be built | 🔨 | Developers | P2 |
| 5.13 | Grid | `mini_grid_cost` | Mini-grid cost | Mini-grid cost model | To be built | 🔨 | Developers | P2 |
| 5.14 | Grid | `shs_cost` | Solar home system cost | SHS cost model | To be built | 🔨 | Households | P2 |
| 5.15 | Grid | `grid_reliability_target` | Reliability target (SAIDI) | Reliability-constrained optimisation | `linopy` SAIDI constraint | 🔨 | Regulators | P1 |
| 5.16 | Grid | `grid_reliability_saifi` | Reliability target (SAIFI) | Reliability-constrained optimisation | `linopy` SAIFI constraint | 🔨 | Regulators | P1 |
| 5.17 | Grid | `cross_border_trade_allowed` | Allow cross-border trade | Trade constraint | `n.links.p_max_pu` | ✅ | Planners | P1 |
| 5.18 | Grid | `interconnector_capacity` | Interconnector capacity | Capacity constraint | `n.links.p_nom` | ✅ | Planners | P1 |
| 5.19 | Grid | `wheeling_charge_cross_border` | Cross-border wheeling charge | Wheeling charge | `n.links.marginal_cost` | ✅ | Regulators | P1 |
| 5.20 | Grid | `loss_factor_cross_border` | Cross-border loss factor | Loss factor | `n.links.efficiency` | ✅ | Planners | P2 |
| 5.21 | Grid | `trade_agreement` | Trade agreement type | Trade agreement type | Metadata | 🔨 | Planners | P3 |
| 5.22 | Grid | `market_coupling` | Market coupling | Market coupling algorithm | To be built | 🔨 | Regulators | P2 |
| 5.23 | Grid | `currency_risk_premium` | Currency risk premium | Currency risk model | To be built | 🔨 | Investors | P2 |
| 5.24 | Grid | `payment_security_required` | Payment security | Payment security model | To be built | 🔨 | Investors | P2 |

---

## CATEGORY 6: SECTOR COUPLING (59)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 6.1 | Sector | `hydrogen_demand_domestic` | Domestic hydrogen demand | Hydrogen demand | PyPSA-Earth-Sec | ✅ | Industry | P2 |
| 6.2 | Sector | `hydrogen_export_volume` | Hydrogen export volume | Export optimisation | PyPSA-Earth-Sec export | ✅ | Industry | P2 |
| 6.3 | Sector | `hydrogen_export_price` | Export price | Export price | PyPSA-Earth-Sec | ✅ | Industry | P2 |
| 6.4 | Sector | `electrolyser_capacity` | Electrolyser capacity | Electrolysis | `n.links` carrier=electrolysis | ✅ | Industry | P2 |
| 6.5 | Sector | `electrolyser_efficiency` | Electrolyser efficiency | Efficiency | `n.links.efficiency` | ✅ | Industry | P2 |
| 6.6 | Sector | `electrolyser_cost` | Electrolyser capital cost | Capital cost | `n.links.capital_cost` | ✅ | Industry | P2 |
| 6.7 | Sector | `electrolyser_learning_rate` | Annual cost reduction | Endogenous learning | To be built | 🔨 | Industry | P3 |
| 6.8 | Sector | `hydrogen_storage_type` | Storage type | Storage type | PyPSA-Earth-Sec underground | ✅ | Industry | P2 |
| 6.9 | Sector | `hydrogen_storage_capacity` | Storage capacity | Storage capacity | PyPSA-Earth-Sec | ✅ | Industry | P2 |
| 6.10 | Sector | `hydrogen_pipeline_capacity` | Pipeline capacity | Pipeline transport | `n.links` carrier=H2 pipeline | ✅ | Industry | P2 |
| 6.11 | Sector | `hydrogen_pipeline_cost` | Pipeline cost | Pipeline cost | `n.links.capital_cost` | ✅ | Industry | P2 |
| 6.12 | Sector | `ammonia_export_share` | Share exported as ammonia | Ammonia synthesis | To be built | 🔨 | Industry | P3 |
| 6.13 | Sector | `hydrogen_export_port` | Export port | Export port | Metadata | 🔨 | Industry | P3 |
| 6.14 | Sector | `heat_pump_adoption` | Heat pump penetration | Heat pump penetration | To be built | 🔨 | Households | P2 |
| 6.15 | Sector | `heat_pump_cop` | Heat pump COP | COP curve | To be built | 🔨 | Households | P2 |
| 6.16 | Sector | `heat_pump_cost` | Heat pump capital cost | Capital cost | `n.links.capital_cost` | ✅ | Households | P2 |
| 6.17 | Sector | `district_heating_share` | District heating share | District heating network | PyPSA-Earth-Sec district heating | ✅ | Cities | P2 |
| 6.18 | Sector | `thermal_storage_capacity` | Thermal storage | Thermal storage | `n.stores` carrier=thermal | ✅ | Industry | P2 |
| 6.19 | Sector | `industrial_heat_demand` | Industrial heat demand | Industrial heat demand | PyPSA-Earth-Sec industry | ✅ | Industry | P2 |
| 6.20 | Sector | `industrial_heat_electrification` | Industrial heat electrification | Industrial heat electrification | To be built | 🔨 | Industry | P2 |
| 6.21 | Sector | `solar_thermal_capacity` | Solar thermal capacity | Solar thermal | To be built | 🔨 | Industry | P3 |
| 6.22 | Sector | `ev_share_new_sales` | EV share of new vehicle sales | EV sales diffusion (Bass) | To be built | 🔨 | Transport | P2 |
| 6.23 | Sector | `ev_adoption_timeline` | Year to reach EV share | Adoption timeline | To be built | 🔨 | Transport | P2 |
| 6.24 | Sector | `ev_efficiency` | EV efficiency | EV efficiency | To be built | 🔨 | Transport | P2 |
| 6.25 | Sector | `ev_battery_size` | Average EV battery size | EV battery size | To be built | 🔨 | Transport | P2 |
| 6.26 | Sector | `v2g_adoption` | V2G-capable EV share | V2G optimisation | To be built | 🔨 | Utilities | P3 |
| 6.27 | Sector | `hydrogen_vehicle_share` | Hydrogen vehicle share | Hydrogen vehicles | PyPSA-Earth-Sec transport | ✅ | Transport | P3 |
| 6.28 | Sector | `synthetic_fuel_share_aviation` | SAF share in aviation | SAF | PyPSA-Earth-Sec synfuel | ✅ | Aviation | P2 |
| 6.29 | Sector | `synthetic_fuel_share_shipping` | Green shipping fuel share | Green shipping fuel | PyPSA-Earth-Sec synfuel | ✅ | Shipping | P2 |
| 6.30 | Sector | `public_transport_share` | Public transport modal share | Modal shift | To be built | 🔨 | Cities | P2 |
| 6.31 | Sector | `freight_electrification` | Freight electrification | Freight electrification | To be built | 🔨 | Transport | P2 |
| 6.32 | Sector | `steel_production` | Steel production | Steel production model | `cacoca` | 🔗 | Industry | P2 |
| 6.33 | Sector | `steel_h2_dri_share` | H₂-DRI share of steel | H₂-DRI process model | To be built | 🔨 | Industry | P2 |
| 6.34 | Sector | `steel_scrap_eaf_share` | Scrap-EAF share of steel | Scrap-EAF process model | To be built | 🔨 | Industry | P2 |
| 6.35 | Sector | `cement_production` | Cement production | Cement production model | To be built | 🔨 | Industry | P2 |
| 6.36 | Sector | `cement_ccus_share` | Cement with CCUS | Cement CCUS model | `AsPyCC` | 🔗 | Industry | P2 |
| 6.37 | Sector | `chemicals_ammonia_production` | Ammonia production | Ammonia production | To be built | 🔨 | Industry | P2 |
| 6.38 | Sector | `chemicals_green_ammonia_share` | Green ammonia share | Green ammonia | To be built | 🔨 | Industry | P2 |
| 6.39 | Sector | `mining_electrification` | Mining electrification | Mining electrification | To be built | 🔨 | Mining | P2 |
| 6.40 | Sector | `mining_hydrogen_haulage` | Hydrogen haulage in mining | Hydrogen haulage | To be built | 🔨 | Mining | P3 |
| 6.41 | Sector | `industrial_ccus_share` | Industrial CCUS adoption | Industrial CCUS | `pyomo` MILP for CCS hub | 🔗 | Industry | P2 |
| 6.42 | Sector | `cooling_water_demand` | Cooling water demand | Cooling water demand | To be built | 🔨 | Utilities | P2 |
| 6.43 | Sector | `water_availability` | Water availability multiplier | Water availability constraint | To be built | 🔨 | Utilities | P2 |
| 6.44 | Sector | `drought_frequency` | Drought frequency multiplier | Drought frequency model | To be built | 🔨 | Planners | P2 |
| 6.45 | Sector | `drought_severity` | Drought severity multiplier | Drought severity model | To be built | 🔨 | Planners | P2 |
| 6.46 | Sector | `desalination_capacity` | Desalination capacity | Desalination model | To be built | 🔨 | Water | P2 |
| 6.47 | Sector | `desalination_energy` | Desalination energy intensity | Desalination energy | To be built | 🔨 | Water | P2 |
| 6.48 | Sector | `irrigation_pumping_demand` | Irrigation pumping demand | Irrigation pumping | To be built | 🔨 | Agriculture | P3 |
| 6.49 | Sector | `transboundary_water_constraint` | Transboundary water limit | Transboundary water allocation | To be built | 🔨 | Policymakers | P3 |
| 6.50 | Sector | `aviation_fuel_demand` | Aviation fuel demand | Aviation fuel model | To be built | 🔨 | Aviation | P3 |
| 6.51 | Sector | `shipping_fuel_demand` | Shipping fuel demand | Shipping fuel model | To be built | 🔨 | Shipping | P3 |
| 6.52 | Sector | `railway_electrification` | Railway electrification | Rail electrification | To be built | 🔨 | Transport | P3 |
| 6.53 | Sector | `port_electrification` | Port electrification | Port electrification | To be built | 🔨 | Ports | P3 |
| 6.54 | Sector | `airport_electrification` | Airport electrification | Airport electrification | To be built | 🔨 | Aviation | P3 |
| 6.55 | Sector | `agricultural_machinery` | Agricultural machinery | Machinery electrification | To be built | 🔨 | Agriculture | P3 |
| 6.56 | Sector | `construction_machinery` | Construction machinery | Machinery electrification | To be built | 🔨 | Construction | P3 |
| 6.57 | Sector | `mining_haulage` | Mining haulage | Haulage electrification | To be built | 🔨 | Mining | P3 |
| 6.58 | Sector | `fishing_vessel_fuel` | Fishing vessel fuel | Vessel fuel model | To be built | 🔨 | Fisheries | P3 |
| 6.59 | Sector | `military_energy_demand` | Military energy demand | Military energy model | To be built | 🔨 | Defence | P3 |

---

## CATEGORY 7: CLIMATE & WEATHER (21)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 7.1 | Climate | `ssp_pathway` | Shared Socioeconomic Pathway | CMIP6 downscaling + bias correction | `cmip6-downscaling` (QDM) | 🔗 | Planners | P1 |
| 7.2 | Climate | `temperature_target` | Temperature target | Temperature target constraint | To be built | 🔨 | Policymakers | P2 |
| 7.3 | Climate | `climate_sensitivity` | Climate sensitivity | Climate sensitivity model | To be built | 🔨 | Scientists | P3 |
| 7.4 | Climate | `carbon_budget` | Remaining carbon budget | Carbon budget constraint | To be built | 🔨 | Policymakers | P2 |
| 7.5 | Climate | `emissions_peak_year` | Global emissions peak year | Emissions peak constraint | To be built | 🔨 | Policymakers | P2 |
| 7.6 | Climate | `net_zero_year` | Global net-zero year | Net-zero constraint | To be built | 🔨 | Policymakers | P2 |
| 7.7 | Climate | `solar_irradiance_multiplier` | Solar irradiance multiplier | Solar scenario generator | `numpy` perturbation | 🔨 | Planners | P2 |
| 7.8 | Climate | `wind_speed_multiplier` | Wind speed multiplier | Wind scenario generator | `numpy` perturbation | 🔨 | Planners | P2 |
| 7.9 | Climate | `precipitation_multiplier` | Precipitation multiplier | Precipitation scenario | `numpy` perturbation | 🔨 | Planners | P2 |
| 7.10 | Climate | `temperature_increase` | Temperature increase | Temperature-dependent demand | To be built | 🔨 | Planners | P2 |
| 7.11 | Climate | `heatwave_frequency` | Heatwave frequency | Heatwave generator | `mews` | 🔗 | Planners | P2 |
| 7.12 | Climate | `cold_snap_frequency` | Cold snap frequency | Cold snap generator | To be built | 🔨 | Planners | P3 |
| 7.13 | Climate | `extreme_weather_events` | Extreme weather frequency | Extreme weather generator | `RainyDay` | 🔗 | Planners | P2 |
| 7.14 | Climate | `interannual_variability` | Interannual variability | Interannual variability | To be built | 🔨 | Planners | P3 |
| 7.15 | Climate | `solar_cf_year` | Solar capacity factor year | Solar capacity factor year | `atlite` year selection | ✅ | Planners | P2 |
| 7.16 | Climate | `wind_cf_year` | Wind capacity factor year | Wind capacity factor year | `atlite` year selection | ✅ | Planners | P2 |
| 7.17 | Climate | `hydro_inflow_year` | Hydro inflow year | Hydro inflow year | `atlite` year selection | ✅ | Planners | P2 |
| 7.18 | Climate | `solar_degradation` | Solar degradation | Solar degradation | `n.generators.p_max_pu` decay | 🔨 | Planners | P2 |
| 7.19 | Climate | `wind_degradation` | Wind degradation | Wind degradation | `n.generators.p_max_pu` decay | 🔨 | Planners | P2 |
| 7.20 | Climate | `renewable_curtailment_limit` | Maximum curtailment | Maximum curtailment | `linopy` constraint | 🔨 | Planners | P2 |
| 7.21 | Climate | `renewable_penetration_limit` | Maximum instantaneous penetration | Maximum instantaneous penetration | `linopy` constraint | 🔨 | Planners | P2 |

---

## CATEGORY 8: OUTAGE & RESILIENCE (30)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 8.1 | Outage | `forced_outage_rate` | Forced outage rate multiplier | Stochastic outage model | Monte Carlo sampling | 🔨 | Utilities | P1 |
| 8.2 | Outage | `planned_outage_rate` | Planned outage rate | Planned outage scheduling | To be built | 🔨 | Utilities | P1 |
| 8.3 | Outage | `outage_duration` | Average outage duration | Outage duration distribution | To be built | 🔨 | Utilities | P1 |
| 8.4 | Outage | `outage_frequency` | Outage frequency | Outage frequency model | To be built | 🔨 | Utilities | P1 |
| 8.5 | Outage | `outage_cause_distribution` | Cause distribution | Cause-specific outage model | To be built | 🔨 | Utilities | P2 |
| 8.6 | Outage | `maintenance_schedule_optimisation` | Optimise maintenance timing | Maintenance scheduling MILP | `linopy` | 🔨 | Utilities | P2 |
| 8.7 | Outage | `predictive_maintenance_adoption` | Predictive maintenance adoption | Predictive maintenance impact | `lifelines` | 🔗 | Utilities | P1 |
| 8.8 | Outage | `spare_parts_availability` | Spare parts availability | Spare parts inventory | To be built | 🔨 | Utilities | P2 |
| 8.9 | Outage | `crew_availability` | Maintenance crew availability | Crew scheduling | To be built | 🔨 | Utilities | P2 |
| 8.10 | Outage | `reserve_margin` | Operating reserve margin | Operating reserve margin | `linopy` constraint | 🔨 | Utilities | P1 |
| 8.11 | Outage | `spinning_reserve` | Spinning reserve requirement | Spinning reserve constraint | `linopy` constraint | 🔨 | Utilities | P1 |
| 8.12 | Outage | `non_spinning_reserve` | Non-spinning reserve | Non-spinning reserve | `linopy` constraint | 🔨 | Utilities | P1 |
| 8.13 | Outage | `regulation_reserve` | Regulation reserve | Regulation reserve | `linopy` constraint | 🔨 | Utilities | P2 |
| 8.14 | Outage | `inertia_requirement` | System inertia requirement | Inertia constraint | To be built | 🔨 | Utilities | P2 |
| 8.15 | Outage | `black_start_capability` | Black start units available | Black start model | To be built | 🔨 | Utilities | P2 |
| 8.16 | Outage | `islanding_capability` | Islanding capability | Islanding model | To be built | 🔨 | Utilities | P3 |
| 8.17 | Outage | `microgrid_deployment` | Microgrid deployment | Microgrid deployment | To be built | 🔨 | Utilities | P3 |
| 8.18 | Outage | `demand_response_capacity` | Demand response capacity | Demand response capacity | To be built | 🔨 | Utilities | P2 |
| 8.19 | Outage | `transmission_loss_reduction_target` | Loss reduction target | Loss reduction target | To be built | 🔨 | Utilities | P2 |
| 8.20 | Outage | `loss_reduction_investment` | Investment in loss reduction | Investment in loss reduction | To be built | 🔨 | Utilities | P2 |
| 8.21 | Outage | `topology_switching_enabled` | Topology switching | Topology switching | To be built | 🔨 | Utilities | P2 |
| 8.22 | Outage | `phase_shifting_enabled` | Phase shifting transformers | Phase shifting transformers | To be built | 🔨 | Utilities | P3 |
| 8.23 | Outage | `voltage_optimisation_enabled` | Voltage optimisation | Voltage optimisation | To be built | 🔨 | Utilities | P2 |
| 8.24 | Outage | `dg_placement_enabled` | Distributed generation placement | DG placement | To be built | 🔨 | Utilities | P2 |
| 8.25 | Outage | `storage_dispatch_enabled` | Storage dispatch for losses | Storage dispatch for losses | `n.storage_units` dispatch | ✅ | Utilities | P2 |
| 8.26 | Outage | `line_upgrade_budget` | Line upgrade budget | Line upgrade budget | To be built | 🔨 | Utilities | P2 |
| 8.27 | Outage | `line_outage_start` | When the outage begins | Temporal outage model | `n.lines.active = False` | ✅ | Utilities | P1 |
| 8.28 | Outage | `line_outage_end` | When the outage ends | Temporal outage model | `n.lines.active = False` | ✅ | Utilities | P1 |
| 8.29 | Outage | `line_outage_probability` | Probability of outage | Probabilistic outage model | Monte Carlo | 🔨 | Utilities | P1 |
| 8.30 | Outage | `line_outage_duration` | Expected duration | Outage duration model | To be built | 🔨 | Utilities | P1 |

---

## CATEGORY 9: MACROECONOMIC (51)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 9.1 | Macro | `gdp_growth_rate` | GDP growth rate | GDP-demand elasticity | `statsmodels` regression | 🔨 | Planners | P1 |
| 9.2 | Macro | `gdp_per_capita_growth` | GDP per capita growth | GDP per capita-demand | `statsmodels` regression | 🔨 | Planners | P2 |
| 9.3 | Macro | `population_growth_rate` | Population growth rate | Population-demand model | `statsmodels` regression | 🔨 | Planners | P1 |
| 9.4 | Macro | `urbanisation_rate` | Urbanisation rate | Urbanisation-demand model | `statsmodels` regression | 🔨 | Planners | P2 |
| 9.5 | Macro | `industrialisation_rate` | Industrialisation rate | Industrialisation-demand | `statsmodels` regression | 🔨 | Planners | P2 |
| 9.6 | Macro | `exchange_rate_usd_local` | Exchange rate (USD/local) | Exchange rate model | To be built | 🔨 | Investors | P1 |
| 9.7 | Macro | `exchange_rate_volatility` | Exchange rate volatility | FX volatility model | `arch` GARCH | 🔗 | Investors | P2 |
| 9.8 | Macro | `inflation_rate` | Inflation rate | Inflation model | To be built | 🔨 | Investors | P1 |
| 9.9 | Macro | `interest_rate` | Central bank interest rate | Interest rate model | To be built | 🔨 | Investors | P2 |
| 9.10 | Macro | `sovereign_risk_premium` | Sovereign risk premium | Sovereign risk model | To be built | 🔨 | Investors | P1 |
| 9.11 | Macro | `country_risk_rating` | Country risk rating | Country risk model | To be built | 🔨 | Investors | P1 |
| 9.12 | Macro | `oil_price` | Oil price | Oil price model | GBM + jumps | 🔨 | All | P1 |
| 9.13 | Macro | `gas_price` | Gas price | Gas price model | PyPSA stochastic example | ✅ | All | P1 |
| 9.14 | Macro | `coal_price` | Coal price | Coal price model | GBM | 🔨 | All | P1 |
| 9.15 | Macro | `lng_price` | LNG price | LNG price model | GBM | 🔨 | All | P2 |
| 9.16 | Macro | `uranium_price` | Uranium price | Uranium price model | GBM | 🔨 | Planners | P3 |
| 9.17 | Macro | `hydrogen_price` | Hydrogen price | Hydrogen price model | GBM | 🔨 | Industry | P2 |
| 9.18 | Macro | `ammonia_price` | Ammonia price | Ammonia price model | GBM | 🔨 | Industry | P2 |
| 9.19 | Macro | `fuel_price_scenario` | Fuel price scenario | Fuel price scenario generator | `horizon-zcs` | 🔗 | All | P2 |
| 9.20 | Macro | `debt_tenor` | Debt tenor | Debt tenor model | To be built | 🔨 | Investors | P1 |
| 9.21 | Macro | `interest_rate_debt` | Interest rate on debt | Debt pricing model | To be built | 🔨 | Investors | P1 |
| 9.22 | Macro | `debt_service_coverage_ratio` | Minimum DSCR | DSCR constraint | `numpy_financial` | 🔗 | Banks | P1 |
| 9.23 | Macro | `loan_life_coverage_ratio` | Minimum LLCR | LLCR constraint | To be built | 🔨 | Banks | P1 |
| 9.24 | Macro | `gearing_ratio` | Debt-to-equity ratio | Gearing model | To be built | 🔨 | Investors | P1 |
| 9.25 | Macro | `equity_return_target` | Target equity IRR | Equity IRR model | `numpy_financial.irr` | 🔗 | Investors | P1 |
| 9.26 | Macro | `project_irr_hurdle` | Project IRR hurdle | Project IRR model | `numpy_financial.irr` | 🔗 | Investors | P1 |
| 9.27 | Macro | `construction_period` | Construction period | Construction period model | To be built | 🔨 | Developers | P2 |
| 9.28 | Macro | `contingency` | Contingency on capex | Contingency model | To be built | 🔨 | Developers | P2 |
| 9.29 | Macro | `political_risk_insurance` | Political risk insurance | Political risk insurance | To be built | 🔨 | Investors | P2 |
| 9.30 | Macro | `currency_hedge_cost` | Currency hedge cost | Currency hedge model | To be built | 🔨 | Investors | P2 |
| 9.31 | Macro | `force_majeure_insurance` | Force majeure insurance | Force majeure model | To be built | 🔨 | Investors | P2 |
| 9.32 | Macro | `business_interruption_insurance` | Business interruption insurance | Business interruption | To be built | 🔨 | Investors | P2 |
| 9.33 | Macro | `carbon_price_risk` | Carbon price risk premium | Carbon price risk model | To be built | 🔨 | Investors | P2 |
| 9.34 | Macro | `technology_risk_premium` | Technology risk premium | Technology risk model | To be built | 🔨 | Investors | P2 |
| 9.35 | Macro | `offtake_risk_premium` | Offtake risk premium | Offtake risk model | To be built | 🔨 | Investors | P2 |
| 9.36 | Macro | `dfi_share` | DFI share | DFI financing model | To be built | 🔨 | DFIs | P2 |
| 9.37 | Macro | `commercial_bank_share` | Commercial bank share | Commercial bank financing | To be built | 🔨 | Banks | P2 |
| 9.38 | Macro | `bond_share` | Bond market share | Bond financing model | To be built | 🔨 | Investors | P2 |
| 9.39 | Macro | `equity_share` | Equity share | Equity financing model | To be built | 🔨 | Investors | P2 |
| 9.40 | Macro | `blended_finance_share` | Blended finance share | Blended finance model | To be built | 🔨 | DFIs | P2 |
| 9.41 | Macro | `green_bond_share` | Green bond share | Green bond model | To be built | 🔨 | Investors | P2 |
| 9.42 | Macro | `carbon_finance_share` | Carbon finance share | Carbon finance model | To be built | 🔨 | Carbon | P2 |
| 9.43 | Macro | `remittance_flows` | Remittance flows | Remittance model | To be built | 🔨 | Households | P2 |
| 9.44 | Macro | `foreign_direct_investment` | Foreign direct investment | FDI model | To be built | 🔨 | Investors | P2 |
| 9.45 | Macro | `official_development_assistance` | Official development assistance | ODA model | To be built | 🔨 | DFIs | P2 |
| 9.46 | Macro | `debt_sustainability` | Debt sustainability | DSA model | To be built | 🔨 | DFIs | P2 |
| 9.47 | Macro | `balance_of_payments` | Balance of payments | BoP model | To be built | 🔨 | Macro | P3 |
| 9.48 | Macro | `current_account_balance` | Current account balance | CA model | To be built | 🔨 | Macro | P3 |
| 9.49 | Macro | `external_debt` | External debt | Debt model | To be built | 🔨 | Macro | P3 |
| 9.50 | Macro | `foreign_exchange_reserves` | Foreign exchange reserves | FX reserves model | To be built | 🔨 | Macro | P3 |
| 9.51 | Macro | `remittance_dependency` | Remittance dependency | Remittance model | To be built | 🔨 | Households | P3 |

---

## CATEGORY 10: INVESTMENT & FINANCE (25)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 10.1 | Finance | `debt_tenor` | Debt tenor | Debt tenor model | To be built | 🔨 | Investors | P1 |
| 10.2 | Finance | `interest_rate_debt` | Interest rate on debt | Debt pricing model | To be built | 🔨 | Investors | P1 |
| 10.3 | Finance | `debt_service_coverage_ratio` | Minimum DSCR | DSCR constraint | `numpy_financial` | 🔗 | Banks | P1 |
| 10.4 | Finance | `loan_life_coverage_ratio` | Minimum LLCR | LLCR constraint | To be built | 🔨 | Banks | P1 |
| 10.5 | Finance | `gearing_ratio` | Debt-to-equity ratio | Gearing model | To be built | 🔨 | Investors | P1 |
| 10.6 | Finance | `equity_return_target` | Target equity IRR | Equity IRR model | `numpy_financial.irr` | 🔗 | Investors | P1 |
| 10.7 | Finance | `project_irr_hurdle` | Project IRR hurdle | Project IRR model | `numpy_financial.irr` | 🔗 | Investors | P1 |
| 10.8 | Finance | `construction_period` | Construction period | Construction period model | To be built | 🔨 | Developers | P2 |
| 10.9 | Finance | `contingency` | Contingency on capex | Contingency model | To be built | 🔨 | Developers | P2 |
| 10.10 | Finance | `political_risk_insurance` | Political risk insurance | Political risk insurance | To be built | 🔨 | Investors | P2 |
| 10.11 | Finance | `currency_hedge_cost` | Currency hedge cost | Currency hedge model | To be built | 🔨 | Investors | P2 |
| 10.12 | Finance | `force_majeure_insurance` | Force majeure insurance | Force majeure model | To be built | 🔨 | Investors | P2 |
| 10.13 | Finance | `business_interruption_insurance` | Business interruption insurance | Business interruption | To be built | 🔨 | Investors | P2 |
| 10.14 | Finance | `carbon_price_risk` | Carbon price risk premium | Carbon price risk model | To be built | 🔨 | Investors | P2 |
| 10.15 | Finance | `technology_risk_premium` | Technology risk premium | Technology risk model | To be built | 🔨 | Investors | P2 |
| 10.16 | Finance | `offtake_risk_premium` | Offtake risk premium | Offtake risk model | To be built | 🔨 | Investors | P2 |
| 10.17 | Finance | `dfi_share` | DFI share | DFI financing model | To be built | 🔨 | DFIs | P2 |
| 10.18 | Finance | `commercial_bank_share` | Commercial bank share | Commercial bank financing | To be built | 🔨 | Banks | P2 |
| 10.19 | Finance | `bond_share` | Bond market share | Bond financing model | To be built | 🔨 | Investors | P2 |
| 10.20 | Finance | `equity_share` | Equity share | Equity financing model | To be built | 🔨 | Investors | P2 |
| 10.21 | Finance | `blended_finance_share` | Blended finance share | Blended finance model | To be built | 🔨 | DFIs | P2 |
| 10.22 | Finance | `green_bond_share` | Green bond share | Green bond model | To be built | 🔨 | Investors | P2 |
| 10.23 | Finance | `carbon_finance_share` | Carbon finance share | Carbon finance model | To be built | 🔨 | Carbon | P2 |
| 10.24 | Finance | `carbon_finance_share` | Carbon finance share | Carbon finance model | To be built | 🔨 | Carbon | P2 |
| 10.25 | Finance | `carbon_finance_share` | Carbon finance share | Carbon finance model | To be built | 🔨 | Carbon | P2 |

---

## CATEGORY 11: OPERATIONAL (24)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 11.1 | Operational | `dispatch_interval` | Dispatch interval | Sub-hourly dispatch | `n.snapshots` at 15-min | ✅ | Utilities | P1 |
| 11.2 | Operational | `day_ahead_market` | Day-ahead market | Day-ahead market clearing | `ASSUME` | 🔗 | Traders | P1 |
| 11.3 | Operational | `real_time_market` | Real-time market | Real-time market clearing | To be built | 🔨 | Traders | P2 |
| 11.4 | Operational | `intraday_market` | Intraday market | Intraday market clearing | To be built | 🔨 | Traders | P2 |
| 11.5 | Operational | `balancing_market` | Balancing market | Balancing market clearing | To be built | 🔨 | Traders | P2 |
| 11.6 | Operational | `unit_commitment` | Unit commitment | Unit commitment | `n.optimize()` with committable | ✅ | Utilities | P1 |
| 11.7 | Operational | `security_constrained_dispatch` | Security-constrained dispatch | Security-constrained dispatch | `n.optimize.optimize_security_constrained()` | ✅ | Utilities | P1 |
| 11.8 | Operational | `n_1_criterion` | N-1 security criterion | N-1 security criterion | `n.optimize.optimize_security_constrained()` | ✅ | Utilities | P1 |
| 11.9 | Operational | `n_2_criterion` | N-2 security criterion | N-2 contingency analysis | `itertools.combinations` + LODF | 🔨 | Utilities | P2 |
| 11.10 | Operational | `spinning_reserve_requirement` | Spinning reserve | Spinning reserve | `linopy` constraint | 🔨 | Utilities | P1 |
| 11.11 | Operational | `non_spinning_reserve_requirement` | Non-spinning reserve | Non-spinning reserve | `linopy` constraint | 🔨 | Utilities | P1 |
| 11.12 | Operational | `regulation_up_requirement` | Regulation up | Regulation up | `linopy` constraint | 🔨 | Utilities | P2 |
| 11.13 | Operational | `regulation_down_requirement` | Regulation down | Regulation down | `linopy` constraint | 🔨 | Utilities | P2 |
| 11.14 | Operational | `reactive_power_requirement` | Reactive power | Reactive power constraint | To be built | 🔨 | Utilities | P2 |
| 11.15 | Operational | `voltage_support_requirement` | Voltage support | Voltage support constraint | To be built | 🔨 | Utilities | P2 |
| 11.16 | Operational | `black_start_requirement` | Black start capability | Black start capability | To be built | 🔨 | Utilities | P2 |
| 11.17 | Operational | `frequency_response_requirement` | Frequency response | Frequency response constraint | To be built | 🔨 | Utilities | P2 |
| 11.18 | Operational | `maintenance_schedule` | Maintenance schedule | Maintenance schedule | `linopy` | 🔨 | Utilities | P2 |
| 11.19 | Operational | `maintenance_duration` | Maintenance duration | Maintenance duration | To be built | 🔨 | Utilities | P2 |
| 11.20 | Operational | `maintenance_frequency` | Maintenance frequency | Maintenance frequency | To be built | 🔨 | Utilities | P2 |
| 11.21 | Operational | `forced_outage_rate` | Forced outage rate | Forced outage rate | Monte Carlo | 🔨 | Utilities | P1 |
| 11.22 | Operational | `planned_outage_rate` | Planned outage rate | Planned outage rate | To be built | 🔨 | Utilities | P2 |
| 11.23 | Operational | `outage_coordination` | Outage coordination | Outage coordination | To be built | 🔨 | Utilities | P2 |
| 11.24 | Operational | `spare_capacity` | Spare capacity | Spare capacity | `linopy` constraint | 🔨 | Utilities | P2 |

---

## CATEGORY 12: SPATIAL & TEMPORAL (16)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 12.1 | Spatial | `spatial_resolution` | Spatial resolution | K-means clustering | `pypsa.clustering.spatial.busmap_by_kmeans()` | ✅ | All | P1 |
| 12.2 | Spatial | `clustering_method` | Clustering method | Clustering method selection | `busmap_by_kmeans()`, `busmap_by_hac()`, `busmap_by_greedy_modularity()`, `busmap_by_custom_busmap()` | ✅ | All | P1 |
| 12.3 | Spatial | `custom_gis_boundary` | Custom GIS boundary | Custom GIS polygons | `busmap_by_custom_busmap()` | ✅ | All | P2 |
| 12.4 | Spatial | `transmission_detail` | Transmission detail | Transmission detail level | Copper plate vs. zonal vs. nodal | ✅ | All | P1 |
| 12.5 | Spatial | `distribution_detail` | Distribution detail | Distribution detail level | Aggregate vs. feeder vs. settlement | 🔨 | Utilities | P2 |
| 12.6 | Temporal | `temporal_resolution` | Temporal resolution | Snapshot frequency | `n.snapshots` modification | ✅ | All | P1 |
| 12.7 | Temporal | `time_horizon` | Time horizon | Time horizon | `n.investment_periods` | ✅ | All | P1 |
| 12.8 | Temporal | `investment_periods` | Investment periods | Investment periods | `n.investment_periods` | ✅ | All | P1 |
| 12.9 | Temporal | `foresight` | Foresight type | Foresight type | `n.optimize(multi_investment_periods=True)` | ✅ | All | P1 |
| 12.10 | Temporal | `rolling_horizon_window` | Rolling horizon window | Rolling horizon window | `n.optimize.optimize_with_rolling_horizon()` | ✅ | All | P2 |
| 12.11 | Temporal | `temporal_aggregation` | Temporal aggregation | Temporal aggregation | `pypsa.clustering.temporal.cluster_temporal()` | ✅ | All | P1 |
| 12.12 | Temporal | `tsam_segments` | TSAM segments | TSAM segments | `tsam.timeseriesaggregation.TimeSeriesAggregation` | ✅ | All | P1 |
| 12.13 | Temporal | `representative_days` | Representative days | Representative days | `tsam.TimeSeriesAggregation` noTypicalPeriods | ✅ | All | P1 |
| 12.14 | Spatial | `spatial_clustering` | Spatial clustering | Spatial clustering | `busmap_by_kmeans()` | ✅ | All | P1 |
| 12.15 | Temporal | `temporal_clustering` | Temporal clustering | Temporal clustering | `cluster_temporal()` | ✅ | All | P1 |
| 12.16 | Temporal | `snapshot_weightings` | Snapshot weightings | Snapshot weightings | `n.snapshot_weightings` | ✅ | All | P1 |

---

## CATEGORY 13: MARKET DESIGN (15)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 13.1 | Market | `market_model` | Market model | Market model | `ASSUME` | 🔗 | Regulators | P1 |
| 13.2 | Market | `pricing_mechanism` | Pricing mechanism | Pricing mechanism | Uniform vs. pay-as-bid vs. nodal | 🔨 | Regulators | P2 |
| 13.3 | Market | `settlement_period` | Settlement period | Settlement period | `n.snapshots` | ✅ | Traders | P2 |
| 13.4 | Market | `gate_closure` | Gate closure | Gate closure | To be built | 🔨 | Traders | P2 |
| 13.5 | Market | `market_coupling` | Market coupling | Market coupling | To be built | 🔨 | Regulators | P2 |
| 13.6 | Market | `cross_border_trading` | Cross-border trading | Cross-border trading | `n.links` | ✅ | Traders | P1 |
| 13.7 | Market | `financial_transmission_rights` | FTR model | FTR model | To be built | 🔨 | Traders | P3 |
| 13.8 | Market | `virtual_bidding` | Virtual bidding | Virtual bidding | To be built | 🔨 | Traders | P3 |
| 13.9 | Market | `number_of_generators` | Number of generators | Number of generators | Metadata | 🔨 | Regulators | P3 |
| 13.10 | Market | `number_of_retailers` | Number of retailers | Number of retailers | Metadata | 🔨 | Regulators | P3 |
| 13.11 | Market | `market_concentration` | Market concentration | Market concentration (HHI) | HHI calculation | 🔨 | Regulators | P2 |
| 13.12 | Market | `strategic_bidding` | Strategic bidding | Strategic bidding | `ASSUME` (RL) | 🔗 | Traders | P2 |
| 13.13 | Market | `collusion` | Collusion detection | Collusion detection | To be built | 🔨 | Regulators | P3 |
| 13.14 | Market | `new_entrants` | Market entry | Market entry model | To be built | 🔨 | Regulators | P3 |
| 13.15 | Market | `retail_competition` | Retail competition | Retail competition model | To be built | 🔨 | Regulators | P3 |

---

## CATEGORY 14: COMBINED & CROSS-CUTTING (15)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 14.1 | Combined | `scenario_template` | Scenario template | Scenario composition | `pypsa.Network` with overrides | ✅ | All | P1 |
| 14.2 | Combined | `parameter_overrides` | Parameter overrides | Parameter override | Dictionary of changes | ✅ | All | P1 |
| 14.3 | Combined | `probability_weight` | Scenario probability | Scenario probability | `n.set_scenarios()` with weights | ✅ | All | P1 |
| 14.4 | Combined | `scenario_tag` | Scenario tagging | Scenario tagging | Metadata | 🔨 | All | P2 |
| 14.5 | Combined | `scenario_description` | Scenario description | Scenario description | Metadata | 🔨 | All | P2 |
| 14.6 | Combined | `scenario_owner` | Scenario owner | Scenario owner | Metadata | 🔨 | All | P2 |
| 14.7 | Combined | `scenario_visibility` | Scenario visibility | Visibility | Metadata | 🔨 | All | P2 |
| 14.8 | Combined | `stochastic_scenarios` | Stochastic scenarios | Two-stage stochastic programming | `n.set_scenarios()` + `n.optimize()` | ✅ | All | P1 |
| 14.9 | Combined | `cvar_alpha` | CVaR tail level | CVaR tail level | `n.set_risk_preference(alpha=...)` | ✅ | All | P1 |
| 14.10 | Combined | `cvar_omega` | Risk-aversion weight | Risk-aversion weight | `n.set_risk_preference(omega=...)` | ✅ | All | P1 |
| 14.11 | Combined | `efficient_frontier` | Efficient frontier | ω sweep | Loop over omega values | ✅ | All | P1 |
| 14.12 | Combined | `signal_extraction` | Signal extraction | LLM prompt extraction | `openai` / `transformers` | 🔗 | All | P1 |
| 14.13 | Combined | `near_duplicate_detection` | Near-duplicate detection | MinHash + LSH | `datasketch` | 🔗 | All | P2 |
| 14.14 | Combined | `signal_scoring` | Signal scoring | Weighted scoring function | To be built | 🔨 | All | P2 |
| 14.15 | Combined | `human_review` | Human review | Priority queue | `redis` sorted set | 🔗 | All | P1 |

---

## CATEGORY 15: TAX & FISCAL (25)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 15.1 | Tax | `corporate_income_tax_rate` | Corporate tax rate | Tax calculation | `numpy_financial` | 🔨 | Developers | P1 |
| 15.2 | Tax | `vat_rate` | VAT/GST rate | Tax calculation | `numpy_financial` | 🔨 | Developers | P1 |
| 15.3 | Tax | `withholding_tax_dividends` | Dividend WHT | Tax calculation | `numpy_financial` | 🔨 | Investors | P1 |
| 15.4 | Tax | `withholding_tax_interest` | Interest WHT | Tax calculation | `numpy_financial` | 🔨 | Investors | P1 |
| 15.5 | Tax | `import_duty_equipment` | Import duty on equipment | Cost adder | To be built | 🔨 | Developers | P2 |
| 15.6 | Tax | `export_duty` | Export duty | Cost adder | To be built | 🔨 | Developers | P2 |
| 15.7 | Tax | `property_tax` | Property tax | Cost adder | To be built | 🔨 | Developers | P2 |
| 15.8 | Tax | `tax_holiday_duration` | Tax holiday period | Temporal override | To be built | 🔨 | Developers | P2 |
| 15.9 | Tax | `tax_holiday_conditions` | Conditions for holiday | Constraint | To be built | 🔨 | Developers | P2 |
| 15.10 | Tax | `transfer_pricing_rules` | Transfer pricing | Compliance model | To be built | 🔨 | Investors | P2 |
| 15.11 | Tax | `thin_capitalisation_rules` | Thin cap rules | Constraint | To be built | 🔨 | Investors | P2 |
| 15.12 | Tax | `loss_carryforward_years` | Loss carry-forward | Temporal model | To be built | 🔨 | Developers | P2 |
| 15.13 | Tax | `loss_carryback_years` | Loss carry-back | Temporal model | To be built | 🔨 | Developers | P2 |
| 15.14 | Tax | `depreciation_schedule_linear` | Linear depreciation | Tax calculation | `numpy_financial` | 🔨 | Developers | P1 |
| 15.15 | Tax | `depreciation_schedule_accelerated` | Accelerated depreciation | Tax calculation | `numpy_financial` | 🔨 | Developers | P1 |
| 15.16 | Tax | `depreciation_schedule_declining` | Declining balance | Tax calculation | `numpy_financial` | 🔨 | Developers | P2 |
| 15.17 | Tax | `capital_gains_tax` | Capital gains tax | Tax calculation | `numpy_financial` | 🔨 | Investors | P2 |
| 15.18 | Tax | `stamp_duty` | Stamp duty | Transaction cost | To be built | 🔨 | Developers | P3 |
| 15.19 | Tax | `customs_duty` | Customs duty | Import cost | To be built | 🔨 | Developers | P2 |
| 15.20 | Tax | `excise_duty_fuel` | Fuel excise | Fuel cost | To be built | 🔨 | Utilities | P2 |
| 15.21 | Tax | `carbon_tax_interaction` | Carbon tax vs. other taxes | Fiscal model | To be built | 🔨 | Policymakers | P2 |
| 15.22 | Tax | `double_tax_treaty` | Treaty network | Treaty lookup | To be built | 🔨 | Investors | P3 |
| 15.23 | Tax | `tax_incentive_zones` | Special economic zones | Spatial override | To be built | 🔨 | Policymakers | P3 |
| 15.24 | Tax | `free_trade_zone_benefits` | FTZ benefits | Cost override | To be built | 🔨 | Developers | P3 |
| 15.25 | Tax | `investment_allowance` | Investment allowance | Tax calculation | To be built | 🔨 | Developers | P2 |

---

## CATEGORY 16: REGULATORY FINANCE (25)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 16.1 | RegFin | `regulatory_asset_base` | Regulatory asset base | Asset valuation | To be built | 🔨 | Regulators | P1 |
| 16.2 | RegFin | `rab_roll_forward` | RAB roll-forward | Temporal model | To be built | 🔨 | Regulators | P1 |
| 16.3 | RegFin | `regulatory_period_length` | Regulatory period | Temporal parameter | To be built | 🔨 | Regulators | P1 |
| 16.4 | RegFin | `x_factor` | Efficiency factor | Productivity model | To be built | 🔨 | Regulators | P1 |
| 16.5 | RegFin | `allowed_return_on_equity` | Regulatory ROE | Cost of capital | To be built | 🔨 | Regulators | P1 |
| 16.6 | RegFin | `allowed_return_on_debt` | Regulatory ROD | Cost of debt | To be built | 🔨 | Regulators | P1 |
| 16.7 | RegFin | `regulatory_depreciation` | Regulatory depreciation | Depreciation model | To be built | 🔨 | Regulators | P1 |
| 16.8 | RegFin | `regulatory_lag` | Regulatory lag | Temporal model | To be built | 🔨 | Regulators | P2 |
| 16.9 | RegFin | `cost_pass_through_mechanism` | Pass-through rules | Cost model | To be built | 🔨 | Regulators | P1 |
| 16.10 | RegFin | `efficiency_benchmarking` | Benchmarking | DEA / SFA | `pydeabm` | 🔗 | Regulators | P2 |
| 16.11 | RegFin | `service_quality_penalty` | Quality penalty | Incentive model | To be built | 🔨 | Regulators | P2 |
| 16.12 | RegFin | `service_quality_reward` | Quality reward | Incentive model | To be built | 🔨 | Regulators | P2 |
| 16.13 | RegFin | `revenue_cap` | Revenue cap | Constraint | To be built | 🔨 | Regulators | P1 |
| 16.14 | RegFin | `price_cap` | Price cap | Constraint | To be built | 🔨 | Regulators | P1 |
| 16.15 | RegFin | `hybrid_revenue_price_cap` | Hybrid cap | Constraint | To be built | 🔨 | Regulators | P2 |
| 16.16 | RegFin | `tariff_rebalancing` | Tariff rebalancing | Optimisation | To be built | 🔨 | Regulators | P2 |
| 16.17 | RegFin | `cost_allocation_methodology` | Cost allocation | Allocation model | To be built | 🔨 | Regulators | P2 |
| 16.18 | RegFin | `demand_forecast_methodology` | Demand forecast | Forecasting | To be built | 🔨 | Regulators | P2 |
| 16.19 | RegFin | `regulatory_accounts` | Regulatory accounts | Accounting model | To be built | 🔨 | Regulators | P2 |
| 16.20 | RegFin | `ring_fencing_rules` | Ring-fencing | Constraint | To be built | 🔨 | Regulators | P2 |
| 16.21 | RegFin | `regulatory_audit_requirements` | Audit requirements | Compliance model | To be built | 🔨 | Regulators | P3 |
| 16.22 | RegFin | `consumer_price_index_link` | CPI link | Indexation | To be built | 🔨 | Regulators | P1 |
| 16.23 | RegFin | `regulatory_asset_valuation_method` | Valuation method | Valuation model | To be built | 🔨 | Regulators | P2 |
| 16.24 | RegFin | `depreciation_life_by_asset` | Asset lives | Depreciation model | To be built | 🔨 | Regulators | P2 |
| 16.25 | RegFin | `working_capital_allowance` | Working capital | Financial model | To be built | 🔨 | Regulators | P2 |

---

## CATEGORY 17: CONTRACT & LEGAL (33)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 17.1 | Contract | `ppa_duration` | PPA contract length | Temporal parameter | To be built | 🔨 | Developers | P1 |
| 17.2 | Contract | `ppa_pricing_formula` | PPA pricing | Pricing model | To be built | 🔨 | Developers | P1 |
| 17.3 | Contract | `ppa_indexation` | Indexation formula | Indexation model | To be built | 🔨 | Developers | P1 |
| 17.4 | Contract | `ppa_take_or_pay` | Take-or-pay provisions | Contract model | To be built | 🔨 | Developers | P2 |
| 17.5 | Contract | `ppa_curtailment_compensation` | Curtailment compensation | Contract model | To be built | 🔨 | Developers | P2 |
| 17.6 | Contract | `ppa_change_in_law` | Change in law | Contract model | To be built | 🔨 | Developers | P2 |
| 17.7 | Contract | `ppa_force_majeure` | Force majeure | Contract model | To be built | 🔨 | Developers | P2 |
| 17.8 | Contract | `ppa_termination_payments` | Termination payments | Contract model | To be built | 🔨 | Investors | P2 |
| 17.9 | Contract | `ppa_governing_law` | Governing law | Metadata | To be built | 🔨 | Lawyers | P3 |
| 17.10 | Contract | `ppa_arbitration_venue` | Arbitration venue | Metadata | To be built | 🔨 | Lawyers | P3 |
| 17.11 | Contract | `ppa_dispute_resolution` | Dispute resolution | Contract model | To be built | 🔨 | Lawyers | P3 |
| 17.12 | Contract | `concession_duration` | Concession length | Temporal parameter | To be built | 🔨 | Developers | P2 |
| 17.13 | Contract | `concession_terms` | Concession terms | Contract model | To be built | 🔨 | Developers | P2 |
| 17.14 | Contract | `licence_conditions` | Licence conditions | Compliance model | To be built | 🔨 | Developers | P1 |
| 17.15 | Contract | `licence_duration` | Licence length | Temporal parameter | To be built | 🔨 | Developers | P1 |
| 17.16 | Contract | `licence_fees` | Licence fees | Cost adder | To be built | 🔨 | Developers | P1 |
| 17.17 | Contract | `performance_bond` | Performance bond | Financial model | To be built | 🔨 | Developers | P2 |
| 17.18 | Contract | `parent_company_guarantee` | PCG | Financial model | To be built | 🔨 | Investors | P2 |
| 17.19 | Contract | `direct_agreement` | Direct agreement | Contract model | To be built | 🔨 | Banks | P2 |
| 17.20 | Contract | `step_in_rights` | Step-in rights | Contract model | To be built | 🔨 | Banks | P2 |
| 17.21 | Contract | `security_package` | Security package | Financial model | To be built | 🔨 | Banks | P2 |
| 17.22 | Contract | `assignment_rights` | Assignment rights | Contract model | To be built | 🔨 | Banks | P3 |
| 17.23 | Contract | `change_of_control` | Change of control | Contract model | To be built | 🔨 | Banks | P3 |
| 17.24 | Contract | `refinancing_terms` | Refinancing | Financial model | To be built | 🔨 | Banks | P2 |
| 17.25 | Contract | `cash_sweep` | Cash sweep | Financial model | To be built | 🔨 | Banks | P2 |
| 17.26 | Contract | `reserve_accounts` | Reserve accounts | Financial model | To be built | 🔨 | Banks | P2 |
| 17.27 | Contract | `distribution_conditions` | Distribution conditions | Financial model | To be built | 🔨 | Banks | P2 |
| 17.28 | Contract | `default_events` | Events of default | Contract model | To be built | 🔨 | Banks | P2 |
| 17.29 | Contract | `remedy_periods` | Remedy periods | Contract model | To be built | 🔨 | Banks | P2 |
| 17.30 | Contract | `cross_default` | Cross-default | Contract model | To be built | 🔨 | Banks | P2 |
| 17.31 | Contract | `material_adverse_change` | MAC clause | Contract model | To be built | 🔨 | Banks | P2 |
| 17.32 | Contract | `environmental_representations` | Environmental reps | Contract model | To be built | 🔨 | Banks | P3 |
| 17.33 | Contract | `social_representations` | Social reps | Contract model | To be built | 🔨 | Banks | P3 |

---

## CATEGORY 18: ENVIRONMENTAL & SOCIAL IMPACT (39)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 18.1 | EnvSoc | `pm25_emissions` | PM2.5 emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P1 |
| 18.2 | EnvSoc | `pm10_emissions` | PM10 emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P1 |
| 18.3 | EnvSoc | `nox_emissions` | NOx emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P1 |
| 18.4 | EnvSoc | `sox_emissions` | SOx emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P1 |
| 18.5 | EnvSoc | `co_emissions` | CO emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P2 |
| 18.6 | EnvSoc | `voc_emissions` | VOC emissions | Emissions inventory | `emissions` | 🔗 | DFIs | P2 |
| 18.7 | EnvSoc | `mercury_emissions` | Mercury | Emissions inventory | To be built | 🔨 | DFIs | P2 |
| 18.8 | EnvSoc | `air_quality_standards` | Air quality limits | Compliance check | To be built | 🔨 | Regulators | P1 |
| 18.9 | EnvSoc | `health_impact_dalys` | DALYs | Health impact assessment | `AirQ+` (WHO) | 🔗 | Health | P1 |
| 18.10 | EnvSoc | `health_impact_mortality` | Premature deaths | Health impact assessment | `AirQ+` | 🔗 | Health | P1 |
| 18.11 | EnvSoc | `health_impact_morbidity` | Illness cases | Health impact assessment | `AirQ+` | 🔗 | Health | P2 |
| 18.12 | EnvSoc | `healthcare_cost_per_case` | Healthcare costs | Economic model | To be built | 🔨 | Health | P2 |
| 18.13 | EnvSoc | `biodiversity_impact` | Biodiversity | Impact assessment | To be built | 🔨 | DFIs | P2 |
| 18.14 | EnvSoc | `habitat_loss` | Habitat loss | Spatial analysis | `geopandas` | 🔗 | DFIs | P2 |
| 18.15 | EnvSoc | `land_use_change` | Land use change | Spatial analysis | `geopandas` | 🔗 | DFIs | P2 |
| 18.16 | EnvSoc | `water_quality_impact` | Water quality | Impact assessment | To be built | 🔨 | DFIs | P2 |
| 18.17 | EnvSoc | `water_pollution_load` | Pollution load | Impact assessment | To be built | 🔨 | DFIs | P2 |
| 18.18 | EnvSoc | `soil_contamination` | Soil contamination | Impact assessment | To be built | 🔨 | DFIs | P3 |
| 18.19 | EnvSoc | `resettlement_requirements` | Resettlement | Impact assessment | To be built | 🔨 | DFIs | P1 |
| 18.20 | EnvSoc | `resettlement_costs` | Resettlement costs | Economic model | To be built | 🔨 | DFIs | P1 |
| 18.21 | EnvSoc | `indigenous_peoples_rights` | FPIC | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.22 | EnvSoc | `cultural_heritage_impact` | Cultural heritage | Impact assessment | To be built | 🔨 | DFIs | P2 |
| 18.23 | EnvSoc | `gender_impact` | Gender dimensions | Impact assessment | To be built | 🔨 | DFIs | P2 |
| 18.24 | EnvSoc | `gender_action_plan` | Gender plan | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.25 | EnvSoc | `labour_standards` | Labour standards | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.26 | EnvSoc | `child_labour_prohibition` | Child labour | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.27 | EnvSoc | `occupational_health_safety` | OHS | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.28 | EnvSoc | `worker_grievance_mechanism` | Grievance mechanism | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.29 | EnvSoc | `community_health_safety` | Community H&S | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.30 | EnvSoc | `emergency_preparedness` | Emergency prep | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.31 | EnvSoc | `equator_principles` | Equator Principles | Compliance model | To be built | 🔨 | Banks | P2 |
| 18.32 | EnvSoc | `ifc_performance_standards` | IFC PS | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.33 | EnvSoc | `world_bank_esf` | World Bank ESF | Compliance model | To be built | 🔨 | DFIs | P1 |
| 18.34 | EnvSoc | `undrip_compliance` | UNDRIP | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.35 | EnvSoc | `ilo_conventions` | ILO conventions | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.36 | EnvSoc | `stakeholder_engagement_plan` | SEP | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.37 | EnvSoc | `grievance_redress_mechanism` | GRM | Compliance model | To be built | 🔨 | DFIs | P2 |
| 18.38 | EnvSoc | `environmental_flow_requirements` | E-flows | Constraint | To be built | 🔨 | Regulators | P2 |
| 18.39 | EnvSoc | `cumulative_impact_assessment` | CIA | Impact assessment | To be built | 🔨 | DFIs | P2 |

---

## CATEGORY 19: JUST TRANSITION (28)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 19.1 | JustTrans | `employment_factor_solar` | Jobs/MW solar | Employment model | To be built | 🔨 | Policymakers | P1 |
| 19.2 | JustTrans | `employment_factor_wind` | Jobs/MW wind | Employment model | To be built | 🔨 | Policymakers | P1 |
| 19.3 | JustTrans | `employment_factor_coal` | Jobs/MW coal | Employment model | To be built | 🔨 | Policymakers | P1 |
| 19.4 | JustTrans | `employment_factor_gas` | Jobs/MW gas | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.5 | JustTrans | `employment_factor_geothermal` | Jobs/MW geothermal | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.6 | JustTrans | `employment_factor_hydro` | Jobs/MW hydro | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.7 | JustTrans | `employment_factor_biomass` | Jobs/MW biomass | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.8 | JustTrans | `employment_factor_transmission` | Jobs/km transmission | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.9 | JustTrans | `direct_jobs` | Direct employment | Employment model | To be built | 🔨 | Policymakers | P1 |
| 19.10 | JustTrans | `indirect_jobs` | Indirect employment | Input-output model | `pymrio` | 🔗 | Policymakers | P2 |
| 19.11 | JustTrans | `induced_jobs` | Induced employment | Input-output model | `pymrio` | 🔗 | Policymakers | P2 |
| 19.12 | JustTrans | `skills_requirements` | Skills by technology | Skills model | To be built | 🔨 | Policymakers | P2 |
| 19.13 | JustTrans | `skills_gap_assessment` | Skills gap | Gap analysis | To be built | 🔨 | Policymakers | P2 |
| 19.14 | JustTrans | `retraining_costs` | Retraining cost | Cost model | To be built | 🔨 | Policymakers | P2 |
| 19.15 | JustTrans | `retraining_duration` | Retraining time | Temporal model | To be built | 🔨 | Policymakers | P2 |
| 19.16 | JustTrans | `community_transition_funding` | Transition funding | Financial model | To be built | 🔨 | Policymakers | P2 |
| 19.17 | JustTrans | `coal_community_dependencies` | Coal community reliance | Spatial analysis | `geopandas` | 🔗 | Policymakers | P2 |
| 19.18 | JustTrans | `social_protection_parameters` | Social protection | Policy model | To be built | 🔨 | Policymakers | P2 |
| 19.19 | JustTrans | `wage_levels_by_sector` | Wage levels | Economic model | To be built | 🔨 | Policymakers | P2 |
| 19.20 | JustTrans | `union_agreements` | Union agreements | Metadata | To be built | 🔨 | Unions | P3 |
| 19.21 | JustTrans | `just_transition_fund` | JT fund | Financial model | To be built | 🔨 | Policymakers | P2 |
| 19.22 | JustTrans | `pension_security` | Pension security | Financial model | To be built | 🔨 | Policymakers | P2 |
| 19.23 | JustTrans | `early_retirement_packages` | Early retirement | Financial model | To be built | 🔨 | Policymakers | P2 |
| 19.24 | JustTrans | `redeployment_options` | Redeployment | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.25 | JustTrans | `local_content_employment` | Local employment | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.26 | JustTrans | `women_employment_targets` | Women employment | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.27 | JustTrans | `youth_employment_targets` | Youth employment | Employment model | To be built | 🔨 | Policymakers | P2 |
| 19.28 | JustTrans | `disability_inclusion` | Disability inclusion | Employment model | To be built | 🔨 | Policymakers | P3 |

---

## CATEGORY 20: CONSUMER PROTECTION & AFFORDABILITY (22)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 20.1 | Consumer | `affordability_threshold` | Affordability limit | Affordability model | To be built | 🔨 | Regulators | P1 |
| 20.2 | Consumer | `energy_poverty_rate` | Energy poverty | Affordability model | To be built | 🔨 | NGOs | P1 |
| 20.3 | Consumer | `energy_poverty_gap` | Poverty gap | Affordability model | To be built | 🔨 | NGOs | P1 |
| 20.4 | Consumer | `willingness_to_pay` | WTP | Survey model | To be built | 🔨 | Regulators | P2 |
| 20.5 | Consumer | `consumer_protection_standards` | Consumer standards | Compliance model | To be built | 🔨 | Regulators | P1 |
| 20.6 | Consumer | `dispute_resolution_mechanism` | Dispute resolution | Compliance model | To be built | 🔨 | Regulators | P2 |
| 20.7 | Consumer | `service_quality_standards` | Service standards | Compliance model | To be built | 🔨 | Regulators | P1 |
| 20.8 | Consumer | `compensation_mechanisms` | Compensation | Financial model | To be built | 🔨 | Regulators | P2 |
| 20.9 | Consumer | `lifeline_tariff` | Lifeline tariff | Tariff model | To be built | 🔨 | Regulators | P1 |
| 20.10 | Consumer | `lifeline_threshold` | Lifeline threshold | Tariff model | To be built | 🔨 | Regulators | P1 |
| 20.11 | Consumer | `prepayment_metering` | Prepayment | Metering model | To be built | 🔨 | Utilities | P2 |
| 20.12 | Consumer | `debt_management` | Debt management | Financial model | To be built | 🔨 | Utilities | P2 |
| 20.13 | Consumer | `disconnection_protection` | Disconnection protection | Compliance model | To be built | 🔨 | Regulators | P1 |
| 20.14 | Consumer | `vulnerable_customer_protection` | Vulnerable customers | Compliance model | To be built | 🔨 | Regulators | P1 |
| 20.15 | Consumer | `complaint_handling` | Complaint handling | Compliance model | To be built | 🔨 | Regulators | P2 |
| 20.16 | Consumer | `consumer_education` | Consumer education | Cost model | To be built | 🔨 | Regulators | P2 |
| 20.17 | Consumer | `tariff_transparency` | Tariff transparency | Compliance model | To be built | 🔨 | Regulators | P2 |
| 20.18 | Consumer | `bill_shock_protection` | Bill shock protection | Tariff model | To be built | 🔨 | Regulators | P2 |
| 20.19 | Consumer | `payment_plans` | Payment plans | Financial model | To be built | 🔨 | Utilities | P2 |
| 20.20 | Consumer | `arrears_management` | Arrears management | Financial model | To be built | 🔨 | Utilities | P2 |
| 20.21 | Consumer | `social_tariff` | Social tariff | Tariff model | To be built | 🔨 | Regulators | P2 |
| 20.22 | Consumer | `cross_subsidy_transparency` | Cross-subsidy | Tariff model | To be built | 🔨 | Regulators | P2 |

---

## CATEGORY 21: DIGITAL, DATA & CYBERSECURITY (22)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 21.1 | Digital | `data_sovereignty_requirements` | Data sovereignty | Compliance model | To be built | 🔨 | Regulators | P2 |
| 21.2 | Digital | `data_privacy_requirements` | Privacy (GDPR/POPIA) | Compliance model | To be built | 🔨 | Regulators | P1 |
| 21.3 | Digital | `cybersecurity_requirements` | Cybersecurity | Compliance model | To be built | 🔨 | Utilities | P1 |
| 21.4 | Digital | `scada_ems_requirements` | SCADA/EMS | System model | To be built | 🔨 | Utilities | P1 |
| 21.5 | Digital | `communication_protocols` | Protocols | Metadata | To be built | 🔨 | Utilities | P2 |
| 21.6 | Digital | `interoperability_standards` | Interoperability | Compliance model | To be built | 🔨 | Utilities | P2 |
| 21.7 | Digital | `digital_divide_metrics` | Digital divide | Metrics | To be built | 🔨 | Policymakers | P2 |
| 21.8 | Digital | `mobile_coverage` | Mobile coverage | Spatial analysis | `geopandas` | 🔗 | Telecom | P2 |
| 21.9 | Digital | `internet_penetration` | Internet penetration | Metrics | To be built | 🔨 | Telecom | P2 |
| 21.10 | Digital | `smart_metering_rollout` | Smart meter rollout | Deployment model | To be built | 🔨 | Utilities | P2 |
| 21.11 | Digital | `ami_infrastructure` | AMI infrastructure | System model | To be built | 🔨 | Utilities | P2 |
| 21.12 | Digital | `der_management_systems` | DERMS | System model | To be built | 🔨 | Utilities | P2 |
| 21.13 | Digital | `adms_requirements` | ADMS | System model | To be built | 🔨 | Utilities | P2 |
| 21.14 | Digital | `gis_requirements` | GIS | System model | To be built | 🔨 | Utilities | P1 |
| 21.15 | Digital | `outage_management_systems` | OMS | System model | To be built | 🔨 | Utilities | P1 |
| 21.16 | Digital | `work_management_systems` | WMS | System model | To be built | 🔨 | Utilities | P2 |
| 21.17 | Digital | `asset_management_systems` | EAM | System model | To be built | 🔨 | Utilities | P2 |
| 21.18 | Digital | `customer_information_systems` | CIS | System model | To be built | 🔨 | Utilities | P1 |
| 21.19 | Digital | `billing_systems` | Billing | System model | To be built | 🔨 | Utilities | P1 |
| 21.20 | Digital | `cyber_insurance` | Cyber insurance | Financial model | To be built | 🔨 | Insurance | P3 |
| 21.21 | Digital | `cyber_incident_response` | Incident response | Compliance model | To be built | 🔨 | Utilities | P2 |
| 21.22 | Digital | `data_backup_recovery` | Backup & recovery | System model | To be built | 🔨 | Utilities | P2 |

---

## CATEGORY 22: GEOPOLITICAL & STRATEGIC (21)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 22.1 | Geopol | `supply_chain_concentration` | Supply chain concentration | HHI | To be built | 🔨 | Policymakers | P1 |
| 22.2 | Geopol | `critical_mineral_dependencies` | Critical minerals | Supply chain model | To be built | 🔨 | Policymakers | P1 |
| 22.3 | Geopol | `rare_earth_dependencies` | Rare earths | Supply chain model | To be built | 🔨 | Policymakers | P2 |
| 22.4 | Geopol | `trade_flow_parameters` | Trade flows | Trade model | `gtap` | 🔗 | Policymakers | P2 |
| 22.5 | Geopol | `sanctions_exposure` | Sanctions | Compliance model | To be built | 🔨 | Investors | P2 |
| 22.6 | Geopol | `strategic_reserves` | Strategic reserves | Inventory model | To be built | 🔨 | Policymakers | P2 |
| 22.7 | Geopol | `energy_security_index` | Energy security | Index | To be built | 🔨 | Policymakers | P1 |
| 22.8 | Geopol | `import_dependency` | Import dependency | Metrics | To be built | 🔨 | Policymakers | P1 |
| 22.9 | Geopol | `export_competitiveness` | Export competitiveness | Trade model | To be built | 🔨 | Policymakers | P2 |
| 22.10 | Geopol | `geopolitical_risk_index` | Geopolitical risk | Index | To be built | 🔨 | Investors | P1 |
| 22.11 | Geopol | `country_risk_rating` | Country risk | Rating model | To be built | 🔨 | Investors | P1 |
| 22.12 | Geopol | `political_stability` | Political stability | Index | To be built | 🔨 | Investors | P1 |
| 22.13 | Geopol | `regulatory_predictability` | Regulatory predictability | Index | To be built | 🔨 | Investors | P1 |
| 22.14 | Geopol | `contract_enforceability` | Contract enforcement | Index | To be built | 🔨 | Investors | P1 |
| 22.15 | Geopol | `rule_of_law_index` | Rule of law | Index | To be built | 🔨 | Investors | P1 |
| 22.16 | Geopol | `corruption_perception` | Corruption | Index | To be built | 🔨 | Investors | P1 |
| 22.17 | Geopol | `cross_border_tension` | Cross-border tension | Index | To be built | 🔨 | Policymakers | P2 |
| 22.18 | Geopol | `maritime_security` | Maritime security | Index | To be built | 🔨 | Policymakers | P2 |
| 22.19 | Geopol | `cyber_threat_level` | Cyber threat | Index | To be built | 🔨 | Utilities | P2 |
| 22.20 | Geopol | `terrorism_risk` | Terrorism risk | Index | To be built | 🔨 | Investors | P2 |
| 22.21 | Geopol | `civil_unrest_risk` | Civil unrest | Index | To be built | 🔨 | Investors | P2 |

---

## CATEGORY 23: ASSET CONDITION & LIFECYCLE (19)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 23.1 | Asset | `asset_age_distribution` | Age distribution | Statistics | `pandas` | 🔗 | Utilities | P1 |
| 23.2 | Asset | `asset_condition_index` | Condition index | Scoring | To be built | 🔨 | Utilities | P1 |
| 23.3 | Asset | `remaining_useful_life` | RUL | Survival analysis | `lifelines` | 🔗 | Utilities | P1 |
| 23.4 | Asset | `maintenance_history` | Maintenance history | Data model | To be built | 🔨 | Utilities | P1 |
| 23.5 | Asset | `failure_history` | Failure history | Data model | To be built | 🔨 | Utilities | P1 |
| 23.6 | Asset | `mean_time_between_failures` | MTBF | Statistics | `reliability` | 🔗 | Utilities | P2 |
| 23.7 | Asset | `mean_time_to_repair` | MTTR | Statistics | `reliability` | 🔗 | Utilities | P2 |
| 23.8 | Asset | `failure_rate_curve` | Bathtub curve | Reliability model | `reliability` | 🔗 | Utilities | P2 |
| 23.9 | Asset | `degradation_model` | Degradation | Physics model | To be built | 🔨 | Utilities | P2 |
| 23.10 | Asset | `spare_parts_inventory` | Spare parts | Inventory model | To be built | 🔨 | Utilities | P2 |
| 23.11 | Asset | `spare_parts_lead_time` | Lead time | Supply chain | To be built | 🔨 | Utilities | P2 |
| 23.12 | Asset | `crew_availability` | Crew availability | Scheduling | To be built | 🔨 | Utilities | P2 |
| 23.13 | Asset | `workshop_capacity` | Workshop capacity | Capacity model | To be built | 🔨 | Utilities | P3 |
| 23.14 | Asset | `transport_logistics` | Transport logistics | Logistics model | To be built | 🔨 | Utilities | P3 |
| 23.15 | Asset | `asset_management_maturity` | AM maturity | Assessment | To be built | 🔨 | Utilities | P2 |
| 23.16 | Asset | `iso_55000_compliance` | ISO 55000 | Compliance | To be built | 🔨 | Utilities | P2 |
| 23.17 | Asset | `risk_based_maintenance` | RBM | Optimisation | To be built | 🔨 | Utilities | P2 |
| 23.18 | Asset | `condition_based_maintenance` | CBM | Optimisation | To be built | 🔨 | Utilities | P2 |
| 23.19 | Asset | `reliability_centred_maintenance` | RCM | Optimisation | To be built | 🔨 | Utilities | P2 |

---

## CATEGORY 24: MARKET OPERATIONS (20)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 24.1 | MktOps | `bid_ask_spread` | Bid-ask spread | Market microstructure | To be built | 🔨 | Traders | P2 |
| 24.2 | MktOps | `market_liquidity` | Liquidity | Market microstructure | To be built | 🔨 | Traders | P2 |
| 24.3 | MktOps | `transaction_costs` | Transaction costs | Cost model | To be built | 🔨 | Traders | P2 |
| 24.4 | MktOps | `clearing_house_requirements` | Clearing house | Financial model | To be built | 🔨 | Banks | P2 |
| 24.5 | MktOps | `margin_requirements` | Margin requirements | Financial model | To be built | 🔨 | Banks | P2 |
| 24.6 | MktOps | `settlement_risk` | Settlement risk | Risk model | To be built | 🔨 | Banks | P2 |
| 24.7 | MktOps | `counterparty_risk` | Counterparty risk | Risk model | `creditrisk` | 🔗 | Banks | P1 |
| 24.8 | MktOps | `credit_support_requirements` | Credit support | Financial model | To be built | 🔨 | Banks | P2 |
| 24.9 | MktOps | `collateral_requirements` | Collateral | Financial model | To be built | 🔨 | Banks | P2 |
| 24.10 | MktOps | `collateral_valuation` | Collateral valuation | Financial model | To be built | 🔨 | Banks | P2 |
| 24.11 | MktOps | `netting_agreements` | Netting | Financial model | To be built | 🔨 | Banks | P2 |
| 24.12 | MktOps | `novation_terms` | Novation | Financial model | To be built | 🔨 | Banks | P3 |
| 24.13 | MktOps | `trade_repository` | Trade repository | Compliance | To be built | 🔨 | Regulators | P3 |
| 24.14 | MktOps | `reporting_requirements` | Reporting | Compliance | To be built | 🔨 | Regulators | P2 |
| 24.15 | MktOps | `market_abuse_prevention` | Market abuse | Compliance | To be built | 🔨 | Regulators | P2 |
| 24.16 | MktOps | `insider_trading_rules` | Insider trading | Compliance | To be built | 🔨 | Regulators | P2 |
| 24.17 | MktOps | `position_limits` | Position limits | Compliance | To be built | 🔨 | Regulators | P2 |
| 24.18 | MktOps | `price_limits` | Price limits | Market design | To be built | 🔨 | Regulators | P2 |
| 24.19 | MktOps | `circuit_breakers` | Circuit breakers | Market design | To be built | 🔨 | Regulators | P2 |
| 24.20 | MktOps | `auction_frequency` | Auction frequency | Market design | To be built | 🔨 | Regulators | P2 |

---

## CATEGORY 25: INSURANCE & CATASTROPHE (17)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 25.1 | Insurance | `catastrophe_modelling` | Cat modelling | CAT model | To be built | 🔨 | Insurance | P1 |
| 25.2 | Insurance | `physical_risk_score` | Physical risk | Risk scoring | To be built | 🔨 | Insurance | P1 |
| 25.3 | Insurance | `business_interruption` | BI parameters | BI model | To be built | 🔨 | Insurance | P1 |
| 25.4 | Insurance | `liability_exposure` | Liability | Liability model | To be built | 🔨 | Insurance | P2 |
| 25.5 | Insurance | `accumulation_risk` | Accumulation | Risk model | To be built | 🔨 | Insurance | P2 |
| 25.6 | Insurance | `reinsurance_parameters` | Reinsurance | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.7 | Insurance | `deductible_levels` | Deductibles | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.8 | Insurance | `insurance_premiums` | Premiums | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.9 | Insurance | `claims_history` | Claims history | Data model | To be built | 🔨 | Insurance | P2 |
| 25.10 | Insurance | `loss_ratio` | Loss ratio | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.11 | Insurance | `combined_ratio` | Combined ratio | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.12 | Insurance | `solvency_capital` | Solvency capital | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.13 | Insurance | `cat_bond_parameters` | Cat bonds | Financial model | To be built | 🔨 | Insurance | P3 |
| 25.14 | Insurance | `parametric_insurance` | Parametric insurance | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.15 | Insurance | `microinsurance` | Microinsurance | Financial model | To be built | 🔨 | Insurance | P2 |
| 25.16 | Insurance | `weather_derivatives` | Weather derivatives | Financial model | To be built | 🔨 | Insurance | P3 |
| 25.17 | Insurance | `climate_risk_disclosure` | TCFD | Compliance | To be built | 🔨 | Insurance | P1 |

---

## CATEGORY 26: CARBON MARKET METHODOLOGY (20)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 26.1 | Carbon | `additionality_test` | Additionality | Methodology | To be built | 🔨 | Carbon | P1 |
| 26.2 | Carbon | `baseline_methodology` | Baseline | Methodology | To be built | 🔨 | Carbon | P1 |
| 26.3 | Carbon | `baseline_emissions` | Baseline emissions | Emissions model | To be built | 🔨 | Carbon | P1 |
| 26.4 | Carbon | `leakage_parameters` | Leakage | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.5 | Carbon | `permanence_parameters` | Permanence | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.6 | Carbon | `buffer_pool_contribution` | Buffer pool | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.7 | Carbon | `mrv_parameters` | MRV | Methodology | To be built | 🔨 | Carbon | P1 |
| 26.8 | Carbon | `corresponding_adjustment` | CA | Compliance | To be built | 🔨 | Carbon | P1 |
| 26.9 | Carbon | `article_6_2_parameters` | Article 6.2 | Compliance | To be built | 🔨 | Carbon | P1 |
| 26.10 | Carbon | `article_6_4_parameters` | Article 6.4 | Compliance | To be built | 🔨 | Carbon | P1 |
| 26.11 | Carbon | `corsia_parameters` | CORSIA | Compliance | To be built | 🔨 | Carbon | P2 |
| 26.12 | Carbon | `cdm_methodologies` | CDM | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.13 | Carbon | `vcs_methodologies` | VCS | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.14 | Carbon | `gold_standard_methodologies` | Gold Standard | Methodology | To be built | 🔨 | Carbon | P2 |
| 26.15 | Carbon | `carbon_credit_prices` | Credit prices | Price model | To be built | 🔨 | Carbon | P1 |
| 26.16 | Carbon | `carbon_credit_volumes` | Credit volumes | Volume model | To be built | 🔨 | Carbon | P1 |
| 26.17 | Carbon | `carbon_credit_retirement` | Retirement | Registry model | To be built | 🔨 | Carbon | P2 |
| 26.18 | Carbon | `carbon_credit_vintage` | Vintage | Temporal model | To be built | 🔨 | Carbon | P2 |
| 26.19 | Carbon | `carbon_credit_rating` | Rating | Scoring | To be built | 🔨 | Carbon | P2 |
| 26.20 | Carbon | `carbon_credit_insurance` | Insurance | Financial model | To be built | 🔨 | Carbon | P3 |

---

## CATEGORY 27: CLIMATE ADAPTATION & RESILIENCE (20)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 27.1 | Adapt | `adaptation_costs` | Adaptation costs | Cost model | To be built | 🔨 | DFIs | P1 |
| 27.2 | Adapt | `adaptation_benefits` | Adaptation benefits | Benefit model | To be built | 🔨 | DFIs | P1 |
| 27.3 | Adapt | `resilience_investment` | Resilience investment | Investment model | To be built | 🔨 | DFIs | P1 |
| 27.4 | Adapt | `climate_proofing_requirements` | Climate proofing | Compliance | To be built | 🔨 | DFIs | P1 |
| 27.5 | Adapt | `sea_level_rise` | SLR | CMIP6 projection | To be built | 🔨 | Cities | P2 |
| 27.6 | Adapt | `flood_risk` | Flood risk | Hydrology model | `floodsim` | 🔗 | Cities | P1 |
| 27.7 | Adapt | `storm_surge` | Storm surge | Coastal model | To be built | 🔨 | Cities | P2 |
| 27.8 | Adapt | `coastal_erosion` | Coastal erosion | Coastal model | To be built | 🔨 | Cities | P2 |
| 27.9 | Adapt | `drought_risk` | Drought risk | Hydrology model | To be built | 🔨 | Cities | P1 |
| 27.10 | Adapt | `heat_stress` | Heat stress | Temperature model | To be built | 🔨 | Cities | P2 |
| 27.11 | Adapt | `wildfire_risk` | Wildfire risk | Fire model | To be built | 🔨 | Cities | P2 |
| 27.12 | Adapt | `landslide_risk` | Landslide risk | Geotechnical model | To be built | 🔨 | Cities | P3 |
| 27.13 | Adapt | `glacial_lake_outburst` | GLOF | Glacial model | To be built | 🔨 | Cities | P3 |
| 27.14 | Adapt | `adaptation_measures` | Adaptation measures | Portfolio model | To be built | 🔨 | DFIs | P2 |
| 27.15 | Adapt | `maladaptation_risk` | Maladaptation | Assessment | To be built | 🔨 | DFIs | P2 |
| 27.16 | Adapt | `resilience_metrics` | Resilience metrics | Metrics | To be built | 🔨 | DFIs | P1 |
| 27.17 | Adapt | `adaptive_capacity` | Adaptive capacity | Index | To be built | 🔨 | DFIs | P2 |
| 27.18 | Adapt | `vulnerability_index` | Vulnerability | Index | To be built | 🔨 | DFIs | P1 |
| 27.19 | Adapt | `exposure_index` | Exposure | Index | To be built | 🔨 | DFIs | P1 |
| 27.20 | Adapt | `risk_transfer_mechanisms` | Risk transfer | Financial model | To be built | 🔨 | DFIs | P2 |

---

## CATEGORY 28: LAND USE & COMMUNITY (20)

| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |
|---|---|---|---|---|---|---|---|---|
| 28.1 | Land | `land_availability` | Land availability | Spatial analysis | `geopandas` | 🔗 | Developers | P1 |
| 28.2 | Land | `land_use_conflicts` | Land use conflicts | Spatial analysis | `geopandas` | 🔗 | Developers | P1 |
| 28.3 | Land | `land_rights` | Land rights | Legal model | To be built | 🔨 | Developers | P1 |
| 28.4 | Land | `land_tenure` | Land tenure | Legal model | To be built | 🔨 | Developers | P1 |
| 28.5 | Land | `land_acquisition_costs` | Land costs | Cost model | To be built | 🔨 | Developers | P1 |
| 28.6 | Land | `resettlement_costs` | Resettlement | Cost model | To be built | 🔨 | Developers | P1 |
| 28.7 | Land | `compensation_rates` | Compensation | Cost model | To be built | 🔨 | Developers | P1 |
| 28.8 | Land | `community_benefit_sharing` | Benefit sharing | Financial model | To be built | 🔨 | Developers | P2 |
| 28.9 | Land | `local_content_requirements` | Local content | Compliance | To be built | 🔨 | Regulators | P2 |
| 28.10 | Land | `local_employment_targets` | Local employment | Employment model | To be built | 🔨 | Developers | P2 |
| 28.11 | Land | `community_development_funds` | Community funds | Financial model | To be built | 🔨 | Developers | P2 |
| 28.12 | Land | `fpic_requirements` | FPIC | Compliance | To be built | 🔨 | Developers | P1 |
| 28.13 | Land | `traditional_land_use` | Traditional use | Spatial analysis | `geopandas` | 🔗 | Developers | P2 |
| 28.14 | Land | `sacred_sites` | Sacred sites | Spatial analysis | `geopandas` | 🔗 | Developers | P2 |
| 28.15 | Land | `archaeological_sites` | Archaeology | Spatial analysis | `geopandas` | 🔗 | Developers | P2 |
| 28.16 | Land | `protected_areas` | Protected areas | Spatial analysis | `geopandas` | 🔗 | Developers | P1 |
| 28.17 | Land | `buffer_zones` | Buffer zones | Spatial analysis | `geopandas` | 🔗 | Developers | P2 |
| 28.18 | Land | `conservation_easements` | Easements | Legal model | To be built | 🔨 | Developers | P2 |
| 28.19 | Land | `land_aggregation` | Land aggregation | Spatial analysis | `geopandas` | 🔗 | Developers | P2 |
| 28.20 | Land | `land_use_planning` | Land use planning | Spatial optimisation | `geopandas` | 🔗 | Cities | P1 |

---

## MASTER SUMMARY TABLE

| Category | # | Parameters | Existing (✅) | Integrate (🔗) | To Build (🔨) | P1 | P2 | P3 |
|---|---|---|---|---|---|---|---|---|
| 1. Demand-Side | 43 | 10 | 3 | 30 | 15 | 22 | 6 |
| 2. Supply-Side | 83 | 38 | 5 | 40 | 30 | 35 | 18 |