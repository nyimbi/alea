# Alea What-If Analysis: Comprehensive Modelable, Queryable, and Modifiable Parameters

## A Complete Taxonomy of Scenario Dimensions

---

## 1. Demand-Side Parameters

### 1.1 Demand Growth & Trajectory

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `demand_growth_rate` | Annual electricity demand growth rate | %/year | -2 to 12 | CMP trajectory | `demand.growth` |
| `demand_growth_profile` | Shape of growth curve | Categorical | Linear, Exponential, S-curve, Step | Linear | `demand.growth_profile` |
| `demand_growth_start_year` | Year growth trajectory begins | Year | 2025–2050 | 2025 | `demand.growth_start` |
| `demand_growth_end_year` | Year growth trajectory ends | Year | 2030–2060 | 2050 | `demand.growth_end` |
| `peak_demand_multiplier` | Scaling factor for peak demand | Multiplier | 0.5–2.0 | 1.0 | `demand.peak_multiplier` |
| `load_factor_override` | Override default load factor | Ratio | 0.3–0.9 | Country-specific | `demand.load_factor` |

### 1.2 Demand Composition

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `industrial_demand_share` | Share of demand from industry | % | 0–80 | Country-specific | `demand.industrial_share` |
| `residential_demand_share` | Share of demand from households | % | 0–80 | Country-specific | `demand.residential_share` |
| `commercial_demand_share` | Share of demand from commercial | % | 0–80 | Country-specific | `demand.commercial_share` |
| `agricultural_demand_share` | Share of demand from agriculture | % | 0–50 | Country-specific | `demand.agricultural_share` |
| `mining_demand_growth` | Additional mining load growth | MW/year | 0–5000 | Country-specific | `demand.mining_growth` |
| `data_centre_demand` | New data centre load | MW | 0–10000 | 0 | `demand.data_centre` |
| `desalination_demand` | Desalination electricity demand | MW | 0–2000 | 0 | `demand.desalination` |
| `hydrogen_production_demand` | Electricity for hydrogen production | MW | 0–50000 | 0 | `demand.hydrogen` |

### 1.3 Demand Flexibility & Response

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `demand_response_potential` | Share of demand that is flexible | % | 0–30 | 5 | `demand.response_potential` |
| `demand_response_cost` | Cost of demand response | $/MWh | 0–500 | 50 | `demand.response_cost` |
| `load_shifting_capability` | Hours of load shifting possible | Hours | 0–24 | 4 | `demand.shifting_hours` |
| `interruptible_load_share` | Share of load that can be curtailed | % | 0–20 | 5 | `demand.interruptible_share` |
| `smart_metering_penetration` | Smart meter coverage | % | 0–100 | Country-specific | `demand.smart_metering` |
| `time_of_use_tariff_adoption` | ToU tariff adoption rate | % | 0–100 | 0 | `demand.tou_adoption` |

### 1.4 Electrification & Access

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `electrification_rate_target` | Target electrification rate | % | 30–100 | Country NDC | `access.electrification_target` |
| `electrification_timeline` | Year to reach target | Year | 2025–2060 | 2030 | `access.timeline` |
| `grid_extension_rate` | Annual grid connection rate | %/year | 0–20 | Country-specific | `access.grid_extension` |
| `mini_grid_deployment` | Mini-grid capacity added | MW/year | 0–1000 | 0 | `access.mini_grid` |
| `solar_home_system_deployment` | SHS units added | Units/year | 0–5,000,000 | 0 | `access.shs` |
| `cooking_lpg_penetration` | LPG cooking access | % | 0–100 | Country-specific | `access.lpg` |
| `clean_cooking_target` | Clean cooking access target | % | 0–100 | Country NDC | `access.clean_cooking` |

### 1.5 Demand-Side Technology Adoption

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `heat_pump_adoption` | Heat pump penetration | % | 0–100 | 0 | `demand.heat_pump` |
| `electric_vehicle_adoption` | EV share of vehicle stock | % | 0–100 | 0 | `demand.ev_adoption` |
| `v2g_adoption` | V2G-capable EV share | % | 0–100 | 0 | `demand.v2g` |
| `rooftop_solar_adoption` | Rooftop solar penetration | % | 0–100 | 0 | `demand.rooftop_solar` |
| `battery_storage_adoption` | Behind-the-meter battery penetration | % | 0–100 | 0 | `demand.btm_battery` |
| `industrial_electrification` | Industrial process electrification | % | 0–100 | 0 | `demand.industrial_electrification` |

---

## 2. Supply-Side / Generation Parameters

### 2.1 Thermal Generation

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `coal_capacity` | Installed coal capacity | MW | 0–100,000 | Country-specific | `supply.coal_capacity` |
| `coal_eaf` | Coal energy availability factor | % | 20–90 | Country-specific | `supply.coal_eaf` |
| `coal_retirement_schedule` | Coal retirement years | Year | 2025–2060 | Country IRP | `supply.coal_retirement` |
| `coal_retirement_rate` | Annual coal retirement | MW/year | 0–10,000 | 0 | `supply.coal_retirement_rate` |
| `coal_new_build` | New coal capacity allowed | MW | 0–20,000 | 0 | `supply.coal_new_build` |
| `coal_ccs_adoption` | Coal with CCS share | % | 0–100 | 0 | `supply.coal_ccs` |
| `gas_capacity` | Installed gas capacity | MW | 0–100,000 | Country-specific | `supply.gas_capacity` |
| `gas_eaf` | Gas energy availability factor | % | 50–95 | Country-specific | `supply.gas_eaf` |
| `gas_new_build` | New gas capacity allowed | MW | 0–50,000 | Country IRP | `supply.gas_new_build` |
| `gas_ccs_adoption` | Gas with CCS share | % | 0–100 | 0 | `supply.gas_ccs` |
| `oil_capacity` | Installed oil capacity | MW | 0–20,000 | Country-specific | `supply.oil_capacity` |
| `oil_eaf` | Oil energy availability factor | % | 50–95 | Country-specific | `supply.oil_eaf` |
| `nuclear_capacity` | Installed nuclear capacity | MW | 0–10,000 | Country-specific | `supply.nuclear_capacity` |
| `nuclear_new_build` | New nuclear capacity | MW | 0–10,000 | 0 | `supply.nuclear_new_build` |
| `nuclear_lead_time` | Nuclear construction lead time | Years | 5–15 | 10 | `supply.nuclear_lead_time` |

### 2.2 Renewable Generation

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `solar_pv_capacity` | Installed solar PV capacity | MW | 0–500,000 | Country-specific | `supply.solar_capacity` |
| `solar_pv_capacity_factor` | Solar PV capacity factor multiplier | Multiplier | 0.5–1.5 | 1.0 | `supply.solar_cf` |
| `solar_pv_cost` | Solar PV capital cost | $/kW | 300–2000 | IRENA | `supply.solar_cost` |
| `solar_pv_learning_rate` | Annual cost reduction | %/year | 0–20 | 5 | `supply.solar_learning` |
| `solar_pv_max_build` | Maximum annual solar build | MW/year | 0–100,000 | Unlimited | `supply.solar_max_build` |
| `solar_pv_land_constraint` | Land available for solar | km² | 0–1,000,000 | GIS-derived | `supply.solar_land` |
| `wind_onshore_capacity` | Installed onshore wind | MW | 0–200,000 | Country-specific | `supply.wind_onshore_capacity` |
| `wind_onshore_cost` | Onshore wind capital cost | $/kW | 500–3000 | IRENA | `supply.wind_onshore_cost` |
| `wind_offshore_capacity` | Installed offshore wind | MW | 0–100,000 | Country-specific | `supply.wind_offshore_capacity` |
| `wind_offshore_cost` | Offshore wind capital cost | $/kW | 1000–6000 | IRENA | `supply.wind_offshore_cost` |
| `wind_offshore_platform` | Platform type | Categorical | Fixed, Floating | Country-specific | `supply.wind_platform` |
| `hydro_capacity` | Installed hydropower | MW | 0–100,000 | Country-specific | `supply.hydro_capacity` |
| `hydro_capacity_factor` | Hydro capacity factor multiplier | Multiplier | 0.5–1.5 | 1.0 | `supply.hydro_cf` |
| `hydro_new_build` | New hydro capacity | MW | 0–50,000 | Country IRP | `supply.hydro_new_build` |
| `hydro_reservoir_level` | Initial reservoir level | % | 0–100 | 50 | `supply.hydro_reservoir` |
| `hydro_drought_multiplier` | Drought impact multiplier | Multiplier | 0.3–1.5 | 1.0 | `supply.hydro_drought` |
| `geothermal_capacity` | Installed geothermal | MW | 0–10,000 | Country-specific | `supply.geothermal_capacity` |
| `geothermal_cost` | Geothermal capital cost | $/kW | 2000–8000 | IRENA | `supply.geothermal_cost` |
| `geothermal_drilling_success` | Drilling success rate | % | 30–90 | 70 | `supply.geothermal_success` |
| `biomass_capacity` | Installed biomass capacity | MW | 0–20,000 | Country-specific | `supply.biomass_capacity` |
| `biomass_feedstock_cost` | Biomass feedstock cost | $/GJ | 1–10 | Country-specific | `supply.biomass_cost` |
| `biomass_sustainability_limit` | Maximum sustainable biomass | PJ/year | 0–5000 | JRC-derived | `supply.biomass_limit` |
| `csp_capacity` | Installed CSP capacity | MW | 0–20,000 | Country-specific | `supply.csp_capacity` |
| `csp_storage_hours` | CSP thermal storage | Hours | 0–15 | 6 | `supply.csp_storage` |
| `marine_wave_capacity` | Installed wave capacity | MW | 0–5000 | Country-specific | `supply.wave_capacity` |
| `marine_tidal_capacity` | Installed tidal capacity | MW | 0–5000 | Country-specific | `supply.tidal_capacity` |
| `marine_otec_capacity` | Installed OTEC capacity | MW | 0–1000 | 0 | `supply.otec_capacity` |

### 2.3 Storage

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `battery_capacity` | Installed battery capacity | MW | 0–100,000 | Country-specific | `storage.battery_capacity` |
| `battery_duration` | Battery duration | Hours | 1–8 | 4 | `storage.battery_duration` |
| `battery_cost` | Battery capital cost | $/kWh | 100–1000 | IRENA | `storage.battery_cost` |
| `battery_learning_rate` | Annual cost reduction | %/year | 0–25 | 10 | `storage.battery_learning` |
| `battery_round_trip_efficiency` | Round-trip efficiency | % | 70–95 | 85 | `storage.battery_efficiency` |
| `phs_capacity` | Pumped hydro storage | MW | 0–50,000 | Country-specific | `storage.phs_capacity` |
| `phs_duration` | PHS duration | Hours | 4–24 | 10 | `storage.phs_duration` |
| `phs_cost` | PHS capital cost | $/kW | 1000–5000 | 2000 | `storage.phs_cost` |
| `hydrogen_storage_capacity` | Hydrogen storage | GWh | 0–100,000 | 0 | `storage.hydrogen_capacity` |
| `hydrogen_storage_cost` | Hydrogen storage cost | $/kWh | 1–50 | 10 | `storage.hydrogen_cost` |
| `thermal_storage_capacity` | Thermal storage | MWth | 0–50,000 | 0 | `storage.thermal_capacity` |
| `thermal_storage_duration` | Thermal storage duration | Hours | 0–24 | 6 | `storage.thermal_duration` |
| `gravity_storage_capacity` | Gravity storage | MW | 0–5000 | 0 | `storage.gravity_capacity` |
| `compressed_air_capacity` | Compressed air storage | MW | 0–5000 | 0 | `storage.caes_capacity` |
| `flywheel_capacity` | Flywheel storage | MW | 0–1000 | 0 | `storage.flywheel_capacity` |
| `storage_duration_curve` | Storage energy-to-power ratio | Hours | 1–100 | 4 | `storage.duration` |

### 2.4 Generation Fleet Characteristics

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `min_stable_level_coal` | Coal minimum stable level | % | 20–60 | 40 | `supply.coal_msl` |
| `min_stable_level_gas` | Gas minimum stable level | % | 10–50 | 30 | `supply.gas_msl` |
| `ramp_rate_coal` | Coal ramp rate | %/min | 0.5–5 | 2 | `supply.coal_ramp` |
| `ramp_rate_gas` | Gas ramp rate | %/min | 5–30 | 15 | `supply.gas_ramp` |
| `startup_cost_coal` | Coal start-up cost | $/MW | 50–500 | 200 | `supply.coal_startup` |
| `startup_cost_gas` | Gas start-up cost | $/MW | 20–200 | 80 | `supply.gas_startup` |
| `min_up_time_coal` | Coal minimum up time | Hours | 4–24 | 8 | `supply.coal_min_up` |
| `min_down_time_coal` | Coal minimum down time | Hours | 4–24 | 8 | `supply.coal_min_down` |
| `forced_outage_rate_coal` | Coal forced outage rate | % | 1–20 | 8 | `supply.coal_for` |
| `forced_outage_rate_gas` | Gas forced outage rate | % | 1–15 | 5 | `supply.gas_for` |
| `maintenance_schedule` | Planned maintenance timing | Categorical | Summer, Winter, Uniform | Uniform | `supply.maintenance` |
| `plant_retirement_age` | Retirement age by technology | Years | 20–60 | Country-specific | `supply.retirement_age` |
| `life_extension_possible` | Life extension allowed | Boolean | True/False | False | `supply.life_extension` |
| `life_extension_cost` | Life extension cost | $/kW | 100–1000 | 300 | `supply.life_extension_cost` |

---

## 3. Cost Parameters

### 3.1 Capital Costs

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `capex_solar_pv` | Solar PV capital cost | $/kW | 300–2000 | IRENA | `costs.solar_capex` |
| `capex_wind_onshore` | Onshore wind capital cost | $/kW | 500–3000 | IRENA | `costs.wind_onshore_capex` |
| `capex_wind_offshore` | Offshore wind capital cost | $/kW | 1000–6000 | IRENA | `costs.wind_offshore_capex` |
| `capex_hydro` | Hydropower capital cost | $/kW | 1000–8000 | IRENA | `costs.hydro_capex` |
| `capex_geothermal` | Geothermal capital cost | $/kW | 2000–8000 | IRENA | `costs.geothermal_capex` |
| `capex_biomass` | Biomass capital cost | $/kW | 1000–5000 | IRENA | `costs.biomass_capex` |
| `capex_csp` | CSP capital cost | $/kW | 3000–10000 | IRENA | `costs.csp_capex` |
| `capex_coal` | Coal capital cost | $/kW | 1000–4000 | IEA | `costs.coal_capex` |
| `capex_gas_ccgt` | Gas CCGT capital cost | $/kW | 500–2000 | IEA | `costs.gas_ccgt_capex` |
| `capex_gas_ocgt` | Gas OCGT capital cost | $/kW | 300–1200 | IEA | `costs.gas_ocgt_capex` |
| `capex_nuclear` | Nuclear capital cost | $/kW | 3000–10000 | IEA | `costs.nuclear_capex` |
| `capex_battery` | Battery capital cost | $/kWh | 100–1000 | IRENA | `costs.battery_capex` |
| `capex_phs` | PHS capital cost | $/kW | 1000–5000 | IEA | `costs.phs_capex` |
| `capex_hydrogen_electrolyser` | Electrolyser capital cost | $/kW | 300–2000 | IEA | `costs.electrolyser_capex` |
| `capex_transmission` | Transmission line cost | $/MW-km | 100–2000 | World Bank | `costs.transmission_capex` |
| `capex_distribution` | Distribution network cost | $/kW | 100–1000 | World Bank | `costs.distribution_capex` |
| `capex_interconnector` | Cross-border interconnector | $/MW-km | 200–3000 | World Bank | `costs.interconnector_capex` |

### 3.2 Operational Costs

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `opex_fixed_solar` | Solar fixed O&M | $/kW/year | 5–30 | IRENA | `costs.solar_opex` |
| `opex_fixed_wind` | Wind fixed O&M | $/kW/year | 10–60 | IRENA | `costs.wind_opex` |
| `opex_fixed_coal` | Coal fixed O&M | $/kW/year | 20–80 | IEA | `costs.coal_opex` |
| `opex_fixed_gas` | Gas fixed O&M | $/kW/year | 10–40 | IEA | `costs.gas_opex` |
| `opex_variable_coal` | Coal variable O&M | $/MWh | 2–15 | IEA | `costs.coal_vom` |
| `opex_variable_gas` | Gas variable O&M | $/MWh | 1–10 | IEA | `costs.gas_vom` |
| `opex_variable_battery` | Battery variable O&M | $/MWh | 0–5 | 1 | `costs.battery_vom` |
| `opex_variable_electrolyser` | Electrolyser variable O&M | $/MWh | 0–5 | 1 | `costs.electrolyser_vom` |
| `fuel_cost_coal` | Coal fuel cost | $/GJ | 1–10 | Country-specific | `costs.coal_fuel` |
| `fuel_cost_gas` | Gas fuel cost | $/GJ | 2–20 | Country-specific | `costs.gas_fuel` |
| `fuel_cost_oil` | Oil fuel cost | $/GJ | 5–30 | Country-specific | `costs.oil_fuel` |
| `fuel_cost_nuclear` | Nuclear fuel cost | $/GJ | 0.5–3 | IEA | `costs.nuclear_fuel` |
| `fuel_cost_biomass` | Biomass fuel cost | $/GJ | 1–10 | Country-specific | `costs.biomass_fuel` |
| `fuel_cost_hydrogen` | Hydrogen fuel cost | $/kg | 0.5–10 | IEA | `costs.hydrogen_fuel` |
| `fuel_price_escalation` | Annual fuel price escalation | %/year | -5 to 10 | 2 | `costs.fuel_escalation` |
| `fuel_price_volatility` | Fuel price volatility | % | 0–50 | 20 | `costs.fuel_volatility` |

### 3.3 System-Level Costs

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `discount_rate` | Social discount rate | % | 0–15 | 7 | `costs.discount_rate` |
| `weighted_average_cost_of_capital` | WACC | % | 3–20 | 10 | `costs.wacc` |
| `cost_of_equity` | Cost of equity | % | 5–30 | 15 | `costs.cost_of_equity` |
| `cost_of_debt` | Cost of debt | % | 3–15 | 8 | `costs.cost_of_debt` |
| `debt_equity_ratio` | Debt-to-equity ratio | Ratio | 0–90 | 70 | `costs.debt_equity` |
| `carbon_price` | Carbon price | $/tCO₂ | 0–500 | 0 | `costs.carbon_price` |
| `carbon_price_escalation` | Annual carbon price increase | %/year | 0–20 | 5 | `costs.carbon_escalation` |
| `carbon_price_coverage` | Share of emissions covered | % | 0–100 | 0 | `costs.carbon_coverage` |
| `value_of_lost_load` | Value of lost load | $/MWh | 1000–50000 | 10000 | `costs.voll` |
| `reserve_margin_requirement` | Minimum reserve margin | % | 5–30 | 15 | `costs.reserve_margin` |
| `planning_reserve_margin` | Planning reserve margin | % | 10–40 | 20 | `costs.planning_reserve` |
| `inertia_requirement` | Minimum system inertia | MWs | 0–10000 | 2000 | `costs.inertia` |

---

## 4. Policy & Regulatory Parameters

### 4.1 Climate Policy

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `carbon_tax_rate` | Carbon tax rate | $/tCO₂ | 0–300 | Country-specific | `policy.carbon_tax` |
| `carbon_tax_start_year` | Year carbon tax begins | Year | 2025–2050 | 2025 | `policy.carbon_tax_start` |
| `carbon_tax_coverage` | Sectors covered by carbon tax | Categorical | Power only, Power+Industry, Economy-wide | Power only | `policy.carbon_tax_coverage` |
| `ets_enabled` | Emissions trading system | Boolean | True/False | False | `policy.ets` |
| `ets_cap` | ETS emissions cap | MtCO₂ | 0–1000 | 0 | `policy.ets_cap` |
| `ets_cap_reduction_rate` | Annual cap reduction | %/year | 0–20 | 5 | `policy.ets_reduction` |
| `carbon_border_adjustment` | CBAM exposure | Boolean | True/False | False | `policy.cbam` |
| `cbam_price` | CBAM certificate price | $/tCO₂ | 0–300 | 0 | `policy.cbam_price` |
| `article_6_credits` | Paris Agreement Article 6 credits | Boolean | True/False | False | `policy.article6` |
| `voluntary_carbon_market` | VCM participation | Boolean | True/False | False | `policy.vcm` |

### 4.2 Renewable & Clean Energy Policy

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `renewable_target` | Renewable energy target | % | 0–100 | Country NDC | `policy.renewable_target` |
| `renewable_target_year` | Year to reach target | Year | 2025–2060 | 2030 | `policy.renewable_target_year` |
| `re_target_carrier` | Which renewables count | Categorical | All, Solar+Wind, Excluding Hydro | All | `policy.re_target_carrier` |
| `feed_in_tariff` | Feed-in tariff rate | $/MWh | 0–300 | 0 | `policy.fit` |
| `fit_duration` | FiT contract duration | Years | 0–30 | 20 | `policy.fit_duration` |
| `fit_capacity_cap` | FiT capacity cap | MW | 0–100,000 | 0 | `policy.fit_cap` |
| `auction_mechanism` | Auction type | Categorical | Sealed-bid, Descending clock, Hybrid | Sealed-bid | `policy.auction_type` |
| `auction_volume` | Annual auction volume | MW/year | 0–50,000 | 0 | `policy.auction_volume` |
| `auction_price_cap` | Auction price ceiling | $/MWh | 0–500 | 200 | `policy.auction_cap` |
| `tax_incentives` | Tax incentives for renewables | Boolean | True/False | False | `policy.tax_incentives` |
| `accelerated_depreciation` | Accelerated depreciation | Boolean | True/False | False | `policy.accelerated_depreciation` |
| `import_duty_exemption` | Import duty exemption | Boolean | True/False | False | `policy.import_exemption` |
| `local_content_requirement` | Local content requirement | % | 0–100 | 0 | `policy.local_content` |

### 4.3 Market Structure & Regulation

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `market_structure` | Electricity market structure | Categorical | Monopoly, Single Buyer, Wholesale, Retail | Single Buyer | `policy.market_structure` |
| `unbundling_status` | Utility unbundling | Categorical | Integrated, Legal, Functional, Ownership | Integrated | `policy.unbundling` |
| `wheeling_charges` | Transmission wheeling charge | $/MWh | 0–50 | Country-specific | `policy.wheeling` |
| `distribution_wheeling_charges` | Distribution wheeling charge | $/MWh | 0–100 | Country-specific | `policy.distribution_wheeling` |
| `cross_subsidy_level` | Cross-subsidy in tariffs | % | 0–50 | 10 | `policy.cross_subsidy` |
| `tariff_structure` | Tariff design | Categorical | Flat, ToU, Critical Peak, RTP | Flat | `policy.tariff_structure` |
| `regulated_tariff_rate` | Regulated tariff | $/MWh | 20–300 | Country-specific | `policy.tariff` |
| `tariff_indexation` | Tariff indexation | Categorical | CPI, USD, Fixed | CPI | `policy.tariff_indexation` |
| `ppa_guarantees` | Government PPA guarantees | Boolean | True/False | False | `policy.ppa_guarantees` |
| `contract_for_difference` | CfD mechanism | Boolean | True/False | False | `policy.cfd` |
| `capacity_market` | Capacity market | Boolean | True/False | False | `policy.capacity_market` |
| `capacity_price` | Capacity market clearing price | $/MW-year | 0–200,000 | 0 | `policy.capacity_price` |
| `ancillary_services_market` | Ancillary services market | Boolean | True/False | False | `policy.ancillary_market` |

### 4.4 Subsidies & Support

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `fossil_fuel_subsidies` | Fossil fuel subsidies | $/year | 0–50B | Country-specific | `policy.fossil_subsidies` |
| `renewable_subsidies` | Renewable energy subsidies | $/year | 0–20B | 0 | `policy.re_subsidies` |
| `electricity_subsidies` | Consumer electricity subsidies | $/year | 0–30B | Country-specific | `policy.electricity_subsidies` |
| `lpg_subsidies` | LPG subsidy | $/kg | 0–2 | Country-specific | `policy.lpg_subsidies` |
| `mini_grid_subsidies` | Mini-grid capital subsidy | % | 0–100 | 50 | `policy.mini_grid_subsidy` |
| `shs_subsidies` | Solar home system subsidy | % | 0–100 | 0 | `policy.shs_subsidy` |

---

## 5. Transmission & Grid Parameters

### 5.1 Transmission Capacity

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `transmission_expansion_allowed` | Allow transmission expansion | Boolean | True/False | True | `grid.expansion_allowed` |
| `transmission_cost_multiplier` | Transmission cost multiplier | Multiplier | 0.5–3.0 | 1.0 | `grid.cost_multiplier` |
| `transmission_loss_factor` | Average transmission loss | % | 2–15 | 8 | `grid.loss_factor` |
| `transmission_capacity_factor` | Transmission utilisation | % | 20–80 | 50 | `grid.capacity_factor` |
| `hvdc_share` | Share of HVDC in new lines | % | 0–100 | 0 | `grid.hvdc_share` |
| `ac_voltage_limit` | Maximum AC voltage | kV | 220–800 | 400 | `grid.ac_voltage` |
| `transmission_lead_time` | Transmission construction time | Years | 2–10 | 5 | `grid.lead_time` |
| `right_of_way_cost` | Right-of-way cost | $/km | 1000–50000 | 10000 | `grid.right_of_way` |
| `cross_border_permitting_time` | Cross-border permitting | Years | 1–15 | 5 | `grid.cross_border_permitting` |

### 5.2 Distribution & Access

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `distribution_loss_factor` | Distribution losses | % | 2–20 | 10 | `grid.distribution_loss` |
| `distribution_capex_per_connection` | Distribution cost per connection | $/connection | 100–3000 | 500 | `grid.distribution_capex` |
| `grid_connection_cost` | Grid connection cost | $/kW | 50–500 | 150 | `grid.connection_cost` |
| `mini_grid_cost` | Mini-grid cost | $/connection | 500–5000 | 1500 | `grid.mini_grid_cost` |
| `shs_cost` | Solar home system cost | $/unit | 50–1000 | 300 | `grid.shs_cost` |
| `grid_reliability_target` | Reliability target | SAIDI hours | 1–100 | Country-specific | `grid.reliability_target` |
| `grid_reliability_saifi` | Reliability target | SAIFI events | 1–50 | Country-specific | `grid.reliability_saifi` |

### 5.3 Cross-Border Trade

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `cross_border_trade_allowed` | Allow cross-border trade | Boolean | True/False | True | `trade.allowed` |
| `interconnector_capacity` | Interconnector capacity | MW | 0–20,000 | Country-specific | `trade.interconnector_capacity` |
| `wheeling_charge_cross_border` | Cross-border wheeling charge | $/MWh | 0–50 | 5 | `trade.wheeling_charge` |
| `loss_factor_cross_border` | Cross-border loss factor | % | 0–10 | 3 | `trade.loss_factor` |
| `trade_agreement` | Trade agreement type | Categorical | Bilateral, Pool, AfSEM | Bilateral | `trade.agreement` |
| `market_coupling` | Market coupling | Categorical | None, Loose, Tight | None | `trade.coupling` |
| `currency_risk_premium` | Currency risk premium | % | 0–20 | 5 | `trade.currency_premium` |
| `payment_security_required` | Payment security | Boolean | True/False | True | `trade.payment_security` |

---

## 6. Sector Coupling Parameters

### 6.1 Hydrogen

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `hydrogen_demand_domestic` | Domestic hydrogen demand | Mt/year | 0–50 | Country-specific | `hydrogen.domestic_demand` |
| `hydrogen_export_volume` | Hydrogen export volume | Mt/year | 0–50 | 0 | `hydrogen.export_volume` |
| `hydrogen_export_price` | Export price | $/kg | 1–10 | 3 | `hydrogen.export_price` |
| `electrolyser_capacity` | Electrolyser capacity | GW | 0–200 | 0 | `hydrogen.electrolyser_capacity` |
| `electrolyser_efficiency` | Electrolyser efficiency | % | 50–85 | 70 | `hydrogen.electrolyser_efficiency` |
| `electrolyser_cost` | Electrolyser capital cost | $/kW | 200–2000 | 700 | `hydrogen.electrolyser_cost` |
| `electrolyser_learning_rate` | Annual cost reduction | %/year | 0–25 | 10 | `hydrogen.electrolyser_learning` |
| `hydrogen_storage_type` | Storage type | Categorical | Salt cavern, Depleted reservoir, Above-ground | Salt cavern | `hydrogen.storage_type` |
| `hydrogen_storage_capacity` | Storage capacity | TWh | 0–1000 | 0 | `hydrogen.storage_capacity` |
| `hydrogen_pipeline_capacity` | Pipeline capacity | GW | 0–50 | 0 | `hydrogen.pipeline_capacity` |
| `hydrogen_pipeline_cost` | Pipeline cost | $/kg/1000km | 0.1–2 | 0.5 | `hydrogen.pipeline_cost` |
| `ammonia_export_share` | Share exported as ammonia | % | 0–100 | 0 | `hydrogen.ammonia_share` |
| `hydrogen_export_port` | Export port | Categorical | Tangier, Suez, Walvis Bay, Saldanha | None | `hydrogen.export_port` |

### 6.2 Heat

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `heat_pump_adoption` | Heat pump penetration | % | 0–100 | 0 | `heat.heat_pump` |
| `heat_pump_cop` | Heat pump COP | Ratio | 2–6 | 3.5 | `heat.cop` |
| `heat_pump_cost` | Heat pump capital cost | $/kW | 300–2000 | 800 | `heat.heat_pump_cost` |
| `district_heating_share` | District heating share | % | 0–100 | 0 | `heat.district_heating` |
| `thermal_storage_capacity` | Thermal storage | GWh | 0–1000 | 0 | `heat.thermal_storage` |
| `industrial_heat_demand` | Industrial heat demand | TWh/year | 0–500 | Country-specific | `heat.industrial_demand` |
| `industrial_heat_electrification` | Industrial heat electrification | % | 0–100 | 0 | `heat.industrial_electrification` |
| `solar_thermal_capacity` | Solar thermal capacity | GWth | 0–100 | 0 | `heat.solar_thermal` |

### 6.3 Transport

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `ev_share_new_sales` | EV share of new vehicle sales | % | 0–100 | 0 | `transport.ev_share` |
| `ev_adoption_timeline` | Year to reach EV share | Year | 2025–2060 | 2050 | `transport.ev_timeline` |
| `ev_efficiency` | EV efficiency | km/kWh | 3–8 | 5 | `transport.ev_efficiency` |
| `ev_battery_size` | Average EV battery size | kWh | 20–150 | 60 | `transport.ev_battery` |
| `v2g_adoption` | V2G-capable EV share | % | 0–100 | 0 | `transport.v2g` |
| `hydrogen_vehicle_share` | Hydrogen vehicle share | % | 0–100 | 0 | `transport.hydrogen_vehicle` |
| `synthetic_fuel_share_aviation` | SAF share in aviation | % | 0–100 | 0 | `transport.saf` |
| `synthetic_fuel_share_shipping` | Green shipping fuel share | % | 0–100 | 0 | `transport.green_shipping` |
| `public_transport_share` | Public transport modal share | % | 0–100 | Country-specific | `transport.public_share` |
| `freight_electrification` | Freight electrification | % | 0–100 | 0 | `transport.freight_electrification` |

### 6.4 Industry

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `steel_production` | Steel production | Mt/year | 0–100 | Country-specific | `industry.steel` |
| `steel_h2_dri_share` | H₂-DRI share of steel | % | 0–100 | 0 | `industry.steel_h2_dri` |
| `steel_scrap_eaf_share` | Scrap-EAF share of steel | % | 0–100 | 20 | `industry.steel_scrap` |
| `cement_production` | Cement production | Mt/year | 0–100 | Country-specific | `industry.cement` |
| `cement_ccus_share` | Cement with CCUS | % | 0–100 | 0 | `industry.cement_ccus` |
| `chemicals_ammonia_production` | Ammonia production | Mt/year | 0–50 | Country-specific | `industry.ammonia` |
| `chemicals_green_ammonia_share` | Green ammonia share | % | 0–100 | 0 | `industry.green_ammonia` |
| `mining_electrification` | Mining electrification | % | 0–100 | 0 | `industry.mining_electrification` |
| `mining_hydrogen_haulage` | Hydrogen haulage in mining | % | 0–100 | 0 | `industry.mining_hydrogen` |
| `industrial_ccus_share` | Industrial CCUS adoption | % | 0–100 | 0 | `industry.ccus` |

### 6.5 Water-Energy Nexus

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `cooling_water_demand` | Cooling water demand | Mm³/year | 0–5000 | Country-specific | `water.cooling_demand` |
| `water_availability` | Water availability multiplier | Multiplier | 0.3–2.0 | 1.0 | `water.availability` |
| `drought_frequency` | Drought frequency multiplier | Multiplier | 0.5–3.0 | 1.0 | `water.drought_frequency` |
| `drought_severity` | Drought severity multiplier | Multiplier | 0.5–3.0 | 1.0 | `water.drought_severity` |
| `desalination_capacity` | Desalination capacity | Mm³/year | 0–2000 | 0 | `water.desalination` |
| `desalination_energy` | Desalination energy intensity | kWh/m³ | 2–10 | 4 | `water.desalination_energy` |
| `irrigation_pumping_demand` | Irrigation pumping demand | TWh/year | 0–100 | Country-specific | `water.irrigation` |
| `transboundary_water_constraint` | Transboundary water limit | % | 0–100 | 100 | `water.transboundary` |

---

## 7. Climate & Weather Parameters

### 7.1 Climate Scenarios

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `ssp_pathway` | Shared Socioeconomic Pathway | Categorical | SSP1-1.9, SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5 | SSP2-4.5 | `climate.ssp` |
| `temperature_target` | Temperature target | °C | 1.5–4.0 | 2.0 | `climate.temperature_target` |
| `climate_sensitivity` | Climate sensitivity | °C per doubling CO₂ | 1.5–5.0 | 3.0 | `climate.climate_sensitivity` |
| `carbon_budget` | Remaining carbon budget | GtCO₂ | 0–2000 | 1000 | `climate.carbon_budget` |
| `emissions_peak_year` | Global emissions peak year | Year | 2020–2050 | 2030 | `climate.emissions_peak` |
| `net_zero_year` | Global net-zero year | Year | 2040–2100 | 2050 | `climate.net_zero_year` |

### 7.2 Weather Variability

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `solar_irradiance_multiplier` | Solar irradiance multiplier | Multiplier | 0.7–1.3 | 1.0 | `weather.solar_multiplier` |
| `wind_speed_multiplier` | Wind speed multiplier | Multiplier | 0.7–1.3 | 1.0 | `weather.wind_multiplier` |
| `precipitation_multiplier` | Precipitation multiplier | Multiplier | 0.5–2.0 | 1.0 | `weather.precipitation` |
| `temperature_increase` | Temperature increase | °C | 0–5 | 1.5 | `weather.temperature_increase` |
| `heatwave_frequency` | Heatwave frequency multiplier | Multiplier | 0.5–5.0 | 1.0 | `weather.heatwave` |
| `cold_snap_frequency` | Cold snap frequency multiplier | Multiplier | 0.5–3.0 | 1.0 | `weather.cold_snap` |
| `extreme_weather_events` | Extreme weather frequency | Multiplier | 0.5–5.0 | 1.0 | `weather.extreme_events` |
| `interannual_variability` | Interannual variability | % | 0–50 | 15 | `weather.interannual_variability` |

### 7.3 Renewable Resource Variability

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `solar_cf_year` | Solar capacity factor year | Year | 2000–2025 | 2013 | `renewables.solar_year` |
| `wind_cf_year` | Wind capacity factor year | Year | 2000–2025 | 2013 | `renewables.wind_year` |
| `hydro_inflow_year` | Hydro inflow year | Year | 2000–2025 | 2013 | `renewables.hydro_year` |
| `solar_degradation` | Solar degradation | %/year | 0–2 | 0.5 | `renewables.solar_degradation` |
| `wind_degradation` | Wind degradation | %/year | 0–2 | 0.3 | `renewables.wind_degradation` |
| `renewable_curtailment_limit` | Maximum curtailment | % | 0–50 | 20 | `renewables.curtailment_limit` |
| `renewable_penetration_limit` | Maximum instantaneous penetration | % | 0–100 | 80 | `renewables.penetration_limit` |

---

## 8. Outage & Resilience Parameters

### 8.1 Outage Parameters

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `forced_outage_rate` | Forced outage rate multiplier | Multiplier | 0.5–3.0 | 1.0 | `outages.forced_rate` |
| `planned_outage_rate` | Planned outage rate | %/year | 0–20 | 5 | `outages.planned_rate` |
| `outage_duration` | Average outage duration | Hours | 0.5–48 | 4 | `outages.duration` |
| `outage_frequency` | Outage frequency | Events/year | 0–100 | Country-specific | `outages.frequency` |
| `outage_cause_distribution` | Cause distribution | Categorical | Weather, Equipment, Vandalism, Load Shedding | Weather | `outages.cause` |
| `maintenance_schedule_optimisation` | Optimise maintenance timing | Boolean | True/False | False | `outages.maintenance_optimisation` |
| `predictive_maintenance_adoption` | Predictive maintenance adoption | % | 0–100 | 0 | `outages.predictive_maintenance` |
| `spare_parts_availability` | Spare parts availability | % | 0–100 | 80 | `outages.spare_parts` |
| `crew_availability` | Maintenance crew availability | % | 0–100 | 90 | `outages.crew_availability` |

### 8.2 Resilience Parameters

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `reserve_margin` | Operating reserve margin | % | 5–50 | 15 | `resilience.reserve_margin` |
| `spinning_reserve` | Spinning reserve requirement | % of load | 0–20 | 5 | `resilience.spinning_reserve` |
| `non_spinning_reserve` | Non-spinning reserve | % of load | 0–15 | 3 | `resilience.non_spinning_reserve` |
| `regulation_reserve` | Regulation reserve | % of load | 0–10 | 2 | `resilience.regulation_reserve` |
| `inertia_requirement` | System inertia requirement | MWs | 0–10000 | 2000 | `resilience.inertia` |
| `black_start_capability` | Black start units available | Units | 0–50 | 5 | `resilience.black_start` |
| `islanding_capability` | Islanding capability | Boolean | True/False | False | `resilience.islanding` |
| `microgrid_deployment` | Microgrid deployment | MW | 0–10,000 | 0 | `resilience.microgrid` |
| `demand_response_capacity` | Demand response capacity | MW | 0–50,000 | 0 | `resilience.demand_response` |

### 8.3 Loss Mitigation Parameters

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `transmission_loss_reduction_target` | Loss reduction target | % | 0–50 | 0 | `losses.reduction_target` |
| `loss_reduction_investment` | Investment in loss reduction | $M | 0–10000 | 0 | `losses.investment` |
| `topology_switching_enabled` | Topology switching | Boolean | True/False | True | `losses.topology_switching` |
| `phase_shifting_enabled` | Phase shifting transformers | Boolean | True/False | False | `losses.phase_shifting` |
| `voltage_optimisation_enabled` | Voltage optimisation | Boolean | True/False | True | `losses.voltage_optimisation` |
| `dg_placement_enabled` | Distributed generation placement | Boolean | True/False | True | `losses.dg_placement` |
| `storage_dispatch_enabled` | Storage dispatch for losses | Boolean | True/False | True | `losses.storage_dispatch` |
| `line_upgrade_budget` | Line upgrade budget | $M | 0–10000 | 0 | `losses.line_upgrade_budget` |

---

## 9. Macroeconomic Parameters

### 9.1 GDP & Growth

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `gdp_growth_rate` | GDP growth rate | %/year | -5 to 15 | Country-specific | `macro.gdp_growth` |
| `gdp_per_capita_growth` | GDP per capita growth | %/year | -5 to 15 | Country-specific | `macro.gdp_per_capita` |
| `population_growth_rate` | Population growth rate | %/year | 0–5 | Country-specific | `macro.population_growth` |
| `urbanisation_rate` | Urbanisation rate | %/year | 0–5 | Country-specific | `macro.urbanisation` |
| `industrialisation_rate` | Industrialisation rate | %/year | 0–10 | Country-specific | `macro.industrialisation` |

### 9.2 Currency & Finance

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `exchange_rate_usd_local` | Exchange rate (USD/local) | Ratio | 0.001–100 | Country-specific | `macro.exchange_rate` |
| `exchange_rate_volatility` | Exchange rate volatility | % | 0–50 | 10 | `macro.fx_volatility` |
| `inflation_rate` | Inflation rate | %/year | 0–30 | Country-specific | `macro.inflation` |
| `interest_rate` | Central bank interest rate | % | 0–30 | Country-specific | `macro.interest_rate` |
| `sovereign_risk_premium` | Sovereign risk premium | % | 0–20 | Country-specific | `macro.sovereign_risk` |
| `country_risk_rating` | Country risk rating | Categorical | AAA to D | Country-specific | `macro.risk_rating` |

### 9.3 Energy Prices

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `oil_price` | Oil price | $/barrel | 20–200 | 80 | `macro.oil_price` |
| `gas_price` | Gas price | $/MMBtu | 1–30 | 5 | `macro.gas_price` |
| `coal_price` | Coal price | $/tonne | 20–200 | 80 | `macro.coal_price` |
| `lng_price` | LNG price | $/MMBtu | 2–40 | 8 | `macro.lng_price` |
| `uranium_price` | Uranium price | $/lb | 20–150 | 50 | `macro.uranium_price` |
| `hydrogen_price` | Hydrogen price | $/kg | 0.5–10 | 3 | `macro.hydrogen_price` |
| `ammonia_price` | Ammonia price | $/tonne | 200–1500 | 500 | `macro.ammonia_price` |
| `fuel_price_scenario` | Fuel price scenario | Categorical | Low, Base, High, Volatile | Base | `macro.fuel_scenario` |

---

## 10. Investment & Finance Parameters

### 10.1 Project Finance

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `debt_tenor` | Debt tenor | Years | 5–25 | 15 | `finance.debt_tenor` |
| `interest_rate_debt` | Interest rate on debt | % | 3–20 | 8 | `finance.interest_rate` |
| `debt_service_coverage_ratio` | Minimum DSCR | Ratio | 1.0–2.5 | 1.3 | `finance.dscr` |
| `loan_life_coverage_ratio` | Minimum LLCR | Ratio | 1.0–2.5 | 1.4 | `finance.llcr` |
| `gearing_ratio` | Debt-to-equity ratio | % | 0–90 | 70 | `finance.gearing` |
| `equity_return_target` | Target equity IRR | % | 5–30 | 15 | `finance.equity_irr` |
| `project_irr_hurdle` | Project IRR hurdle | % | 5–25 | 12 | `finance.project_irr` |
| `construction_period` | Construction period | Years | 1–10 | 3 | `finance.construction_period` |
| `contingency` | Contingency on capex | % | 0–30 | 10 | `finance.contingency` |

### 10.2 Risk & Insurance

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `political_risk_insurance` | Political risk insurance | Boolean | True/False | False | `finance.political_risk` |
| `currency_hedge_cost` | Currency hedge cost | % | 0–10 | 2 | `finance.currency_hedge` |
| `force_majeure_insurance` | Force majeure insurance | Boolean | True/False | True | `finance.force_majeure` |
| `business_interruption_insurance` | Business interruption insurance | Boolean | True/False | True | `finance.business_interruption` |
| `carbon_price_risk` | Carbon price risk premium | % | 0–10 | 2 | `finance.carbon_risk` |
| `technology_risk_premium` | Technology risk premium | % | 0–10 | 3 | `finance.technology_risk` |
| `offtake_risk_premium` | Offtake risk premium | % | 0–10 | 2 | `finance.offtake_risk` |

### 10.3 Financing Sources

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `dfi_share` | Development finance institution share | % | 0–100 | 30 | `finance.dfi_share` |
| `commercial_bank_share` | Commercial bank share | % | 0–100 | 40 | `finance.commercial_share` |
| `bond_share` | Bond market share | % | 0–100 | 10 | `finance.bond_share` |
| `equity_share` | Equity share | % | 0–100 | 20 | `finance.equity_share` |
| `blended_finance_share` | Blended finance share | % | 0–100 | 0 | `finance.blended_share` |
| `green_bond_share` | Green bond share | % | 0–100 | 0 | `finance.green_bond` |
| `carbon_finance_share` | Carbon finance share | % | 0–100 | 0 | `finance.carbon_finance` |

---

## 11. Operational Parameters

### 11.1 Dispatch & Scheduling

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `dispatch_interval` | Dispatch interval | Minutes | 5–60 | 60 | `operations.dispatch_interval` |
| `day_ahead_market` | Day-ahead market | Boolean | True/False | True | `operations.day_ahead` |
| `real_time_market` | Real-time market | Boolean | True/False | False | `operations.real_time` |
| `intraday_market` | Intraday market | Boolean | True/False | False | `operations.intraday` |
| `balancing_market` | Balancing market | Boolean | True/False | True | `operations.balancing` |
| `unit_commitment` | Unit commitment | Boolean | True/False | True | `operations.unit_commitment` |
| `security_constrained_dispatch` | Security-constrained dispatch | Boolean | True/False | True | `operations.scuc` |
| `n_1_criterion` | N-1 security criterion | Boolean | True/False | True | `operations.n1` |
| `n_2_criterion` | N-2 security criterion | Boolean | True/False | False | `operations.n2` |

### 11.2 Reserve & Ancillary Services

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `spinning_reserve_requirement` | Spinning reserve | % of load | 0–20 | 5 | `operations.spinning_reserve` |
| `non_spinning_reserve_requirement` | Non-spinning reserve | % of load | 0–15 | 3 | `operations.non_spinning` |
| `regulation_up_requirement` | Regulation up | MW | 0–5000 | 200 | `operations.regulation_up` |
| `regulation_down_requirement` | Regulation down | MW | 0–5000 | 200 | `operations.regulation_down` |
| `reactive_power_requirement` | Reactive power | MVAr | 0–5000 | 500 | `operations.reactive_power` |
| `voltage_support_requirement` | Voltage support | MVAr | 0–5000 | 300 | `operations.voltage_support` |
| `black_start_requirement` | Black start capability | Units | 0–50 | 5 | `operations.black_start` |
| `frequency_response_requirement` | Frequency response | MW/Hz | 0–1000 | 100 | `operations.frequency_response` |

### 11.3 Maintenance & Outages

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `maintenance_schedule` | Maintenance schedule | Categorical | Optimised, Fixed, Seasonal | Optimised | `operations.maintenance` |
| `maintenance_duration` | Maintenance duration | Days | 1–60 | 14 | `operations.maintenance_duration` |
| `maintenance_frequency` | Maintenance frequency | Events/year | 1–4 | 2 | `operations.maintenance_frequency` |
| `forced_outage_rate` | Forced outage rate | % | 1–20 | 8 | `operations.forced_outage` |
| `planned_outage_rate` | Planned outage rate | % | 0–15 | 5 | `operations.planned_outage` |
| `outage_coordination` | Outage coordination | Boolean | True/False | True | `operations.outage_coordination` |
| `spare_capacity` | Spare capacity | % | 0–30 | 15 | `operations.spare_capacity` |

---

## 12. Spatial & Temporal Parameters

### 12.1 Spatial Resolution

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `spatial_resolution` | Spatial resolution | Nodes | 1–1000 | 55 | `spatial.resolution` |
| `clustering_method` | Clustering method | Categorical | Country, Voronoi, K-means, Custom | Country | `spatial.clustering` |
| `custom_gis_boundary` | Custom GIS boundary | File | GeoJSON, Shapefile | None | `spatial.custom_boundary` |
| `transmission_detail` | Transmission detail | Categorical | Copper plate, Zonal, Nodal | Zonal | `spatial.transmission_detail` |
| `distribution_detail` | Distribution detail | Categorical | Aggregate, Feeder, Settlement | Aggregate | `spatial.distribution_detail` |

### 12.2 Temporal Resolution

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `temporal_resolution` | Temporal resolution | Minutes | 1–60 | 60 | `temporal.resolution` |
| `time_horizon` | Time horizon | Years | 1–50 | 30 | `temporal.horizon` |
| `investment_periods` | Investment periods | Years | 1–20 | 5 | `temporal.investment_periods` |
| `foresight` | Foresight type | Categorical | Perfect, Myopic, Rolling | Perfect | `temporal.foresight` |
| `rolling_horizon_window` | Rolling horizon window | Years | 1–20 | 5 | `temporal.rolling_window` |
| `temporal_aggregation` | Temporal aggregation | Categorical | Full, TSAM, Representative days | Full | `temporal.aggregation` |
| `tsam_segments` | TSAM segments | Count | 5–100 | 20 | `temporal.tsam_segments` |
| `representative_days` | Representative days | Count | 1–52 | 12 | `temporal.rep_days` |

---

## 13. Market Design Parameters

### 13.1 Market Structure

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `market_model` | Market model | Categorical | Monopoly, Single Buyer, Wholesale, Retail | Single Buyer | `market.model` |
| `pricing_mechanism` | Pricing mechanism | Categorical | Regulated, Uniform, Pay-as-bid, Nodal | Regulated | `market.pricing` |
| `settlement_period` | Settlement period | Minutes | 5–60 | 30 | `market.settlement` |
| `gate_closure` | Gate closure | Hours | 0–24 | 1 | `market.gate_closure` |
| `market_coupling` | Market coupling | Categorical | None, Loose, Tight | None | `market.coupling` |
| `cross_border_trading` | Cross-border trading | Boolean | True/False | True | `market.cross_border` |
| `financial_transmission_rights` | Financial transmission rights | Boolean | True/False | False | `market.ftr` |
| `virtual_bidding` | Virtual bidding | Boolean | True/False | False | `market.virtual_bidding` |

### 13.2 Market Participants

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `number_of_generators` | Number of generators | Count | 1–1000 | Country-specific | `market.generators` |
| `number_of_retailers` | Number of retailers | Count | 0–100 | 0 | `market.retailers` |
| `market_concentration` | Market concentration (HHI) | Index | 0–10000 | Country-specific | `market.hhi` |
| `strategic_bidding` | Strategic bidding | Boolean | True/False | False | `market.strategic_bidding` |
| `collusion` | Collusion allowed | Boolean | True/False | False | `market.collusion` |
| `new_entrants` | New entrants allowed | Boolean | True/False | True | `market.new_entrants` |
| `retail_competition` | Retail competition | Boolean | True/False | False | `market.retail_competition` |

---

## 14. Combined & Cross-Cutting Scenarios

### 14.1 Pre-Built Scenario Templates

| Scenario Name | Description | Key Parameters |
|---|---|---|
| **Base Case** | Current policies, moderate growth | CMP trajectory, current policies |
| **Net Zero 2050** | Deep decarbonisation by 2050 | Carbon price $150, 100% RE, coal phase-out 2040 |
| **Nationally Determined Contributions** | NDC-aligned | Country NDCs, moderate carbon price |
| **Fossil Fuel Renaissance** | Continued fossil dependence | Low carbon price, high gas growth |
| **Renewable Superpower** | Africa as global hydrogen exporter | High hydrogen export, high RE build |
| **Climate Crisis** | High warming, severe impacts | SSP5-8.5, high drought, high heat |
| **Just Transition** | Emphasis on equity and access | High electrification, social protections |
| **Energy Sovereignty** | Reduced cross-border trade | Low trade, high self-sufficiency |
| **AfSEM Integration** | Full continental market | Full trade, market coupling, harmonised regulation |
| **Technology Breakthrough** | Rapid cost declines | Aggressive learning rates, new technologies |
| **Supply Chain Crisis** | Constrained equipment supply | High capex, long lead times |
| **Currency Crisis** | Severe devaluation | High FX volatility, high inflation |
| **Carbon Border Adjustment** | EU CBAM impact | High CBAM price, export competitiveness |
| **Mission 300** | Universal energy access | Universal access by 2030, high mini-grid |
| **Green Hydrogen Export** | 100 Mt/year export | High electrolyser, high pipeline, high port |

### 14.2 Combined Scenario Parameters

| Parameter | Description | Unit | Range | Default | Query |
|---|---|---|---|---|---|
| `scenario_template` | Pre-built template | Categorical | See above | Base Case | `scenario.template` |
| `parameter_overrides` | Override any parameter | Dict | — | {} | `scenario.overrides` |
| `probability_weight` | Scenario probability | Ratio | 0–1 | 1.0 | `scenario.probability` |
| `scenario_tag` | User-defined tags | List | — | [] | `scenario.tags` |
| `scenario_description` | Scenario description | Text | — | "" | `scenario.description` |
| `scenario_owner` | Scenario owner | User ID | — | Current user | `scenario.owner` |
| `scenario_visibility` | Visibility | Categorical | Private, Team, Public | Private | `scenario.visibility` |

---

## 15. Query Capabilities

### 15.1 Query Types

| Query Type | Description | Example |
|---|---|---|
| **Point query** | Retrieve a single value | `GET /whatif/result?scenario_id=abc&metric=total_cost` |
| **Time series query** | Retrieve time series | `GET /whatif/result?scenario_id=abc&metric=price&country=NG&start=2030&end=2050` |
| **Comparison query** | Compare scenarios | `POST /whatif/compare` with list of scenario IDs |
| **Sensitivity query** | Sweep one parameter | `POST /whatif/sensitivity` with param and range |
| **Frontier query** | Generate efficient frontier | `POST /whatif/frontier` with param and range |
| **Ranking query** | Rank options | `POST /whatif/rank` with options and criteria |
| **Optimisation query** | Find optimal parameter value | `POST /whatif/optimise` with objective and constraints |
| **Decomposition query** | Decompose results | `POST /whatif/decompose` with metric and dimension |
| **Attribution query** | Attribute change to drivers | `POST /whatif/attribute` with scenarios and metric |
| **Scenario query** | List and filter scenarios | `GET /scenarios?tags=netzero&country=NG` |

### 15.2 Query Metrics

| Metric Category | Metrics | Query |
|---|---|---|
| **Cost** | Total system cost, LCOE, marginal cost, consumer cost, producer cost | `metric=cost.*` |
| **Capacity** | Installed capacity by technology, new build, retirements | `metric=capacity.*` |
| **Generation** | Generation by technology, curtailment, capacity factor | `metric=generation.*` |
| **Emissions** | Total emissions, emissions intensity, emissions by sector | `metric=emissions.*` |
| **Prices** | Wholesale price, capture price, retail tariff, LMP | `metric=price.*` |
| **Reliability** | ENS, EENS, LOLP, SAIDI, SAIFI, reserve margin | `metric=reliability.*` |
| **Losses** | Total losses, loss decomposition, TLENS | `metric=losses.*` |
| **Trade** | Cross-border flows, trade volume, trade value | `metric=trade.*` |
| **Employment** | Jobs by technology, jobs by country | `metric=employment.*` |
| **Access** | Electrification rate, connections, clean cooking access | `metric=access.*` |
| **Water** | Water consumption, water withdrawal, water intensity | `metric=water.*` |
| **Land** | Land use by technology, land use change | `metric=land.*` |
| **Hydrogen** | Hydrogen production, export, cost, LCOH | `metric=hydrogen.*` |
| **Health** | Air quality, premature deaths, health costs | `metric=health.*` |

### 15.3 Query Filters

| Filter | Description | Example |
|---|---|---|
| `country` | Filter by country ISO | `country=NG` |
| `region` | Filter by region | `region=West Africa` |
| `power_pool` | Filter by power pool | `power_pool=SAPP` |
| `technology` | Filter by technology | `technology=solar` |
| `carrier` | Filter by energy carrier | `carrier=electricity` |
| `year` | Filter by year | `year=2030` |
| `scenario` | Filter by scenario | `scenario=netzero` |
| `metric` | Select metric | `metric=total_cost` |
| `aggregation` | Aggregation method | `aggregation=sum` |
| `group_by` | Group results | `group_by=country` |
| `sort` | Sort order | `sort=-total_cost` |
| `limit` | Limit results | `limit=100` |

### 15.4 Query Outputs

| Output Format | Description | Use Case |
|---|---|---|
| **JSON** | Standard structured output | API consumers |
| **CSV** | Tabular output | Spreadsheet analysis |
| **Parquet** | Columnar output | Big data analysis |
| **NetCDF** | Scientific data format | Climate and weather data |
| **GeoJSON** | Spatial output | GIS analysis |
| **PDF** | Formatted report | Sharing and presentation |
| **HTML** | Interactive output | Web embedding |
| **PNG/SVG** | Chart output | Presentations |
| **Excel** | Spreadsheet with charts | Business analysis |

---

## Summary

The Alea What-If Analysis engine allows users to **model, query, and modify** an exhaustive set of parameters across **fourteen categories**:

1. **Demand-side** — growth, composition, flexibility, electrification, technology adoption
2. **Supply-side** — thermal, renewable, storage, fleet characteristics
3. **Cost** — capital, operational, system-level, financing
4. **Policy** — climate, renewable, market structure, subsidies
5. **Transmission & Grid** — capacity, distribution, cross-border trade
6. **Sector Coupling** — hydrogen, heat, transport, industry, water
7. **Climate & Weather** — SSP pathways, variability, extremes
8. **Outage & Resilience** — outage rates, reserves, loss mitigation
9. **Macroeconomic** — GDP, currency, energy prices
10. **Investment & Finance** — project finance, risk, financing sources
11. **Operational** — dispatch, reserves, maintenance
12. **Spatial & Temporal** — resolution, horizon, foresight
13. **Market Design** — structure, participants, pricing
14. **Combined & Cross-Cutting** — pre-built templates, combined scenarios

Users can query results across **thirteen metric categories** and **twelve filter dimensions**, with outputs in **nine formats**. The engine supports **ten query types**, from simple point queries to complex attribution analysis. This makes Alea the most comprehensive what-if analysis platform for African energy systems, capable of answering any question a policymaker, investor, utility, or researcher might ask about the future of African energy.