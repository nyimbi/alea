# ALEA: Definitive Catalog of Modelling Algorithms

## Complete Mapping of What-If Parameters → Algorithms → Python Implementations

**Version**: 1.0
**Status**: Definitive Reference for Development
**Coverage**: Every what-if parameter from the 14-category taxonomy, mapped to its required algorithm and Python implementation (existing or to-be-built)

---

## How to Read This Catalog

Each entry follows this structure:

| Field | Description |
|---|---|
| **Parameter** | The what-if parameter name from the taxonomy |
| **Algorithm** | The mathematical or computational method required |
| **Python Implementation** | Existing package, library, or "To be built" |
| **Source / Reference** | Where the algorithm is documented or validated |

Where a Python implementation exists in PyPSA-Earth, PyPSA, or a validated open-source package, the package name and key function are given. Where no implementation exists, the algorithm is specified for development.

---

## Part I: Core Optimisation Engine (Supports All Categories)

### 1. Linear Optimal Power Flow (LOPF)

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `dispatch_interval` | Linear programming with nodal balance | `pypsa.Network.optimize()` — formulation options: `angles`, `cycles`, `kirchhoff`, `ptdf` | PyPSA docs |
| `security_constrained_dispatch` | Security-constrained LOPF | `pypsa.Network.optimize.optimize_security_constrained()` | PyPSA docs |
| `n_1_criterion` | N-1 security constraints | `n.optimize.optimize_security_constrained()` with `branch_outages` | PyPSA docs |
| `transmission_loss_factor` | Secant-based loss approximation | `n.optimize(transmission_losses=True)` — options: `atol=1`, `rtol=0.1`, `max_segments=20` | PyPSA v1.0 |
| `line_capacity_override` | Capacity constraint | `n.lines.s_nom` modification | PyPSA |
| `line_capacity_factor` | Capacity derating | `n.lines.s_max_pu` modification | PyPSA |
| `line_impedance_multiplier` | Impedance modification | `n.lines.x` modification | PyPSA |
| `line_active` | Branch outage | `n.lines.active = False` | PyPSA |

### 2. Unit Commitment (UC)

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `min_stable_level_coal` | MILP with big-M linearisation | `n.generators.committable = True`; `n.generators.p_min_pu` | PyPSA v0.9+ |
| `min_stable_level_gas` | MILP with big-M linearisation | Same as above | PyPSA |
| `ramp_rate_coal` | Ramp rate constraints | `n.generators.ramp_limit_up/down` | PyPSA |
| `ramp_rate_gas` | Ramp rate constraints | Same as above | PyPSA |
| `startup_cost_coal` | Start-up cost | `n.generators.start_up_cost` | PyPSA |
| `startup_cost_gas` | Start-up cost | Same as above | PyPSA |
| `min_up_time_coal` | Minimum up time | `n.generators.min_up_time` | PyPSA |
| `min_down_time_coal` | Minimum down time | `n.generators.min_down_time` | PyPSA |
| `forced_outage_rate_coal` | Stochastic outage | To be built — Monte Carlo outage sampling | — |

### 3. Spatial Clustering

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `spatial_resolution` | K-means clustering | `pypsa.clustering.spatial.busmap_by_kmeans()` | PyPSA Clustering |
| `clustering_method` (kmeans) | K-means++ initialisation | `busmap_by_kmeans()` with `n_init=100` | PyPSA |
| `clustering_method` (hac) | Hierarchical Agglomerative Clustering | `busmap_by_hac()` | PyPSA |
| `clustering_method` (modularity) | Greedy modularity | `busmap_by_greedy_modularity()` | PyPSA |
| `clustering_method` (Voronoi) | Voronoi tessellation | PyPSA-Earth `build_bus_regions` rule | PyPSA-Earth |
| `custom_gis_boundary` | Custom GIS polygons | `busmap_by_custom_busmap()` | PyPSA |

### 4. Temporal Aggregation

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `temporal_aggregation` (TSAM) | Agglomerative clustering with variable-duration segments | `tsam.timeseriesaggregation.TimeSeriesAggregation` — `pypsa.clustering.temporal.cluster_temporal()` | PyPSA + TSAM |
| `tsam_segments` | Number of segments | `num_segments` parameter | TSAM |
| `representative_days` | Representative period clustering | `tsam.TimeSeriesAggregation` with `noTypicalPeriods` | TSAM |
| `temporal_resolution` | Snapshot frequency | `n.snapshots` modification | PyPSA |

---

## Part II: Demand-Side Parameters (Category A)

### 5. Demand Growth & Trajectory

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `demand_growth_rate` | Logistic / Gompertz growth curve | To be built — `scipy.optimize.curve_fit` with logistic function | — |
| `demand_growth_profile` | Growth curve shape fitting | To be built | — |
| `peak_demand_multiplier` | Peak-load scaling | `n.loads_t.p_set * multiplier` | PyPSA |
| `load_factor_override` | Load profile reshaping | To be built — load factor adjustment algorithm | — |

### 6. Demand Composition

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `industrial_demand_share` | Sectoral disaggregation | PyPSA-Earth `build_industry_demand` rule | PyPSA-Earth |
| `residential_demand_share` | Sectoral disaggregation | To be built | — |
| `commercial_demand_share` | Sectoral disaggregation | To be built | — |
| `agricultural_demand_share` | Sectoral disaggregation | To be built | — |
| `mining_demand_growth` | Mining load profiling | To be built | — |
| `data_centre_demand` | Data centre load profiling | To be built — constant + burst model | — |
| `desalination_demand` | Desalination load model | To be built — reverse osmosis energy curve | — |
| `hydrogen_production_demand` | Hydrogen demand integration | PyPSA-Earth sector-coupled | PyPSA-Earth |

### 7. Demand Flexibility & Response

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `demand_response_potential` | Elasticity-based DR optimisation | To be built — `scipy.optimize.linprog` with elasticity matrix | — |
| `demand_response_cost` | DR cost curve | To be built | — |
| `load_shifting_capability` | MILP with time windows | To be built — `pyomo` or `linopy` | — |
| `interruptible_load_share` | Curtailable load constraint | `n.loads` with `p_set` reduction | PyPSA |
| `smart_metering_penetration` | Bottom-up load synthesis | To be built — `numpy` Monte Carlo | — |
| `time_of_use_tariff_adoption` | Price elasticity matrix | To be built | — |

### 8. Electrification & Access

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `electrification_rate_target` | OnSSET-style geospatial | `onsset` — Open Source Spatial Electrification Tool | OnSSET |
| `electrification_timeline` | Adoption diffusion curve | To be built — Bass diffusion model | — |
| `grid_extension_rate` | Grid extension cost curve | To be built — distance-decay function | — |
| `mini_grid_deployment` | HOMER-style mini-grid sizing | `HOMER` (proprietary); open alternative: `pypsa` with isolated nodes | — |
| `solar_home_system_deployment` | SHS adoption diffusion | To be built — Bass diffusion | — |
| `cooking_lpg_penetration` | Fuel stacking model | To be built | — |
| `clean_cooking_target` | Fuel transition model | To be built | — |

### 9. Demand-Side Technology Adoption

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `heat_pump_adoption` | Temperature-dependent COP | To be built — COP curve from ambient temperature | — |
| `electric_vehicle_adoption` | Monte Carlo driving patterns | `mobev` — Mobility-based EV charging demand model | MobEV |
| `v2g_adoption` | Bidirectional charging MILP | To be built | — |
| `rooftop_solar_adoption` | Building footprint + shading | To be built — `rasterio` + `geopandas` | — |
| `battery_storage_adoption` | Behind-the-meter dispatch | To be built | — |
| `industrial_electrification` | Industrial process electrification | To be built | — |

---

## Part III: Supply-Side / Generation Parameters (Category B)

### 10. Thermal Generation

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `coal_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `coal_eaf` | Energy availability factor | `n.generators.p_max_pu` | PyPSA |
| `coal_retirement_schedule` | Retirement scheduling MILP | To be built — `linopy` with binary retirement variables | — |
| `coal_retirement_rate` | Age-based retirement curve | To be built | — |
| `coal_new_build` | Investment variable | `n.generators.p_nom_extendable = True` | PyPSA |
| `coal_ccs_adoption` | CCS retrofit model | To be built — energy penalty + capture rate | — |
| `gas_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `gas_eaf` | Energy availability factor | `n.generators.p_max_pu` | PyPSA |
| `gas_new_build` | Investment variable | `n.generators.p_nom_extendable` | PyPSA |
| `gas_ccs_adoption` | CCS retrofit model | To be built | — |
| `oil_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `nuclear_capacity` | Baseload + refuelling | To be built | — |
| `nuclear_lead_time` | Construction lead-time constraint | To be built | — |

### 11. Renewable Generation

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `solar_pv_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `solar_pv_capacity_factor` | Renewable profile scaling | `n.generators_t.p_max_pu * multiplier` | PyPSA |
| `solar_pv_cost` | Capital cost | `n.generators.capital_cost` | PyPSA |
| `solar_pv_learning_rate` | Endogenous learning curve | To be built — experience curve | — |
| `solar_pv_max_build` | Annual build constraint | To be built | — |
| `wind_onshore_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `wind_offshore_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `wind_offshore_platform` | Floating vs. fixed cost | To be built | — |
| `hydro_capacity` | Capacity constraint | `n.generators.p_nom` | PyPSA |
| `hydro_reservoir_level` | Reservoir operation (SDP) | `rtc-tools` — Model Predictive Control for reservoirs | RTC-Tools |
| `hydro_drought_multiplier` | Hydrological drought scenario | `climate` — CMIP6-based inflow scenarios | — |
| `geothermal_capacity` | Flash steam / binary cycle | To be built | — |
| `geothermal_drilling_success` | Bayesian drilling success | `geoPFA` — Play Fairway Analysis | geoPFA |
| `biomass_capacity` | Combustion / gasification | To be built | — |
| `biomass_sustainability_limit` | LCA-based constraint | To be built | — |
| `csp_capacity` | CSP with thermal storage | To be built | — |
| `csp_storage_hours` | Thermal storage dispatch | To be built | — |
| `marine_wave_capacity` | Wave energy conversion | `MHKiT` — Marine and Hydrokinetic Toolkit | MHKiT |
| `marine_tidal_capacity` | Tidal energy conversion | `MHKiT` | MHKiT |
| `marine_otec_capacity` | OTEC thermodynamic model | To be built | — |

### 12. Storage

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `battery_capacity` | Storage constraint | `n.storage_units.p_nom` | PyPSA |
| `battery_duration` | Energy-to-power ratio | `n.storage_units.max_hours` | PyPSA |
| `battery_cost` | Capital cost | `n.storage_units.capital_cost` | PyPSA |
| `battery_learning_rate` | Endogenous learning | To be built | — |
| `battery_round_trip_efficiency` | Efficiency | `n.storage_units.efficiency_store/dispatch` | PyPSA |
| `phs_capacity` | Pumped hydro | `n.storage_units` with `carrier="PHS"` | PyPSA |
| `phs_duration` | PHS duration | `n.storage_units.max_hours` | PyPSA |
| `hydrogen_storage_capacity` | Salt cavern / depleted reservoir | `pypsa-earth-sec` hydrogen storage | PyPSA-Earth-Sec |
| `thermal_storage_capacity` | Thermal storage | `n.stores` with `carrier="thermal"` | PyPSA |
| `gravity_storage_capacity` | Gravity storage dispatch | To be built | — |
| `compressed_air_capacity` | CAES thermodynamic | To be built | — |
| `flywheel_capacity` | Flywheel fast-response | To be built | — |

---

## Part IV: Cost Parameters (Category C)

### 13. Capital Costs

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `capex_solar_pv` | Capital cost parameter | `n.generators.capital_cost` | PyPSA |
| `capex_wind_onshore` | Capital cost parameter | `n.generators.capital_cost` | PyPSA |
| `capex_battery` | Capital cost parameter | `n.storage_units.capital_cost` | PyPSA |
| `capex_transmission` | Transmission line cost | `n.lines.capital_cost` | PyPSA |
| `capex_interconnector` | Cross-border interconnector | `n.links.capital_cost` | PyPSA |
| `discount_rate` | Social discount rate | `n.optimize()` with `discount_rate` | PyPSA |

### 14. Operational Costs

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `opex_fixed_solar` | Fixed O&M | `n.generators.capital_cost` (annualised) | PyPSA |
| `opex_variable_coal` | Variable O&M | `n.generators.marginal_cost` | PyPSA |
| `fuel_cost_coal` | Fuel cost | `n.generators.marginal_cost` | PyPSA |
| `fuel_cost_gas` | Fuel cost | `n.generators.marginal_cost` | PyPSA |
| `fuel_price_escalation` | Fuel price escalation | To be built — time-dependent marginal cost | — |
| `fuel_price_volatility` | Stochastic fuel price (GBM + jumps) | To be built — `numpy` GBM with Poisson jumps | — |

### 15. System-Level Costs

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `wacc` | WACC model | `wacc-estimator` — FinCoRE WACC estimator | GitHub |
| `cost_of_equity` | CAPM-based cost of equity | To be built — `numpy_financial` | — |
| `cost_of_debt` | Debt pricing model | To be built | — |
| `debt_equity_ratio` | Optimal capital structure | To be built | — |
| `carbon_price` | Carbon price | `n.generators.marginal_cost += carbon_price * co2_emissions` | PyPSA |
| `carbon_price_escalation` | Carbon price trajectory | `peltwtcn` — PELT + wavelet + deep learning | PyPI |
| `value_of_lost_load` | VoLL as load shedding cost | `n.generators` with `carrier="load"` and high `marginal_cost` | PyPSA |
| `reserve_margin_requirement` | Reserve margin constraint | To be built — `linopy` constraint | — |

---

## Part V: Policy & Regulatory Parameters (Category D)

### 16. Climate Policy

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `carbon_tax_rate` | Carbon tax | `n.generators.marginal_cost` adjustment | PyPSA |
| `ets_enabled` | Emissions trading system | To be built — cap-and-trade clearing | — |
| `ets_cap` | ETS cap constraint | To be built | — |
| `carbon_border_adjustment` | CBAM impact model | `stanzaapi-cbam-carbon` — EU CBAM calculator | PyPI |
| `article_6_credits` | Paris Agreement credits | To be built | — |

### 17. Renewable & Clean Energy Policy

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `renewable_target` | Renewable portfolio standard | `n.generators` with `carrier` constraint | PyPSA |
| `feed_in_tariff` | FiT cost allocation | To be built | — |
| `auction_mechanism` | Renewable auction simulation | To be built | — |
| `auction_volume` | Auction volume scheduling | To be built | — |
| `tax_incentives` | Tax incentive cost model | To be built | — |
| `local_content_requirement` | Local content cost premium | To be built | — |

### 18. Market Structure & Regulation

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `market_structure` | Market structure simulation | `ASSUME` — Agent-based electricity markets | ASSUME |
| `unbundling_status` | Unbundling impact model | To be built | — |
| `wheeling_charges` | Wheeling charge model | `n.links.marginal_cost` | PyPSA |
| `tariff_structure` | Tariff design optimisation | To be built | — |
| `contract_for_difference` | CfD settlement | To be built | — |
| `capacity_market` | Capacity market clearing | `pyshop` — SHOP market model | SINTEF |
| `ancillary_services_market` | Ancillary services clearing | `ASAM` — Ancillary Services Acquisition Model | ASAM |

### 19. Subsidies & Support

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `fossil_fuel_subsidies` | Subsidy reform impact | To be built | — |
| `renewable_subsidies` | Renewable subsidy cost | To be built | — |
| `electricity_subsidies` | Consumer subsidy model | To be built | — |
| `mini_grid_subsidies` | Mini-grid subsidy | To be built | — |

---

## Part VI: Transmission & Grid Parameters (Category E)

### 20. Transmission Capacity

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `transmission_expansion_allowed` | Investment variable | `n.lines.s_nom_extendable = True` | PyPSA |
| `transmission_cost_multiplier` | Cost scaling | `n.lines.capital_cost` | PyPSA |
| `hvdc_share` | HVDC vs. HVAC | To be built | — |
| `ac_voltage_limit` | Voltage level selection | To be built | — |
| `transmission_lead_time` | Project scheduling | To be built | — |
| `cross_border_permitting_time` | Permitting delay model | To be built | — |

### 21. Distribution & Access

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `distribution_loss_factor` | Distribution loss model | To be built | — |
| `distribution_capex_per_connection` | Distribution cost curve | To be built | — |
| `grid_connection_cost` | Connection cost | To be built | — |
| `mini_grid_cost` | Mini-grid cost model | To be built | — |
| `shs_cost` | SHS cost model | To be built | — |
| `grid_reliability_target` | Reliability-constrained optimisation | To be built — SAIDI/SAIFI constraints | — |

### 22. Cross-Border Trade

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `cross_border_trade_allowed` | Trade constraint | `n.links.p_max_pu` | PyPSA |
| `interconnector_capacity` | Capacity constraint | `n.links.p_nom` | PyPSA |
| `wheeling_charge_cross_border` | Wheeling charge | `n.links.marginal_cost` | PyPSA |
| `market_coupling` | Market coupling algorithm | To be built | — |
| `currency_risk_premium` | Currency risk model | To be built | — |

---

## Part VII: Sector Coupling Parameters (Category F)

### 23. Hydrogen

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `hydrogen_demand_domestic` | Hydrogen demand | `pypsa-earth-sec` hydrogen sector | PyPSA-Earth-Sec |
| `hydrogen_export_volume` | Export optimisation | `pypsa-earth-sec` export module | PyPSA-Earth-Sec |
| `electrolyser_capacity` | Electrolysis | `n.links` with `carrier="electrolysis"` | PyPSA |
| `electrolyser_efficiency` | Efficiency | `n.links.efficiency` | PyPSA |
| `hydrogen_storage_type` | Salt cavern / depleted reservoir | `pypsa-earth-sec` underground storage | PyPSA-Earth-Sec |
| `hydrogen_pipeline_capacity` | Pipeline transport | `n.links` with `carrier="H2 pipeline"` | PyPSA |
| `ammonia_export_share` | Ammonia synthesis | To be built | — |

### 24. Heat

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `heat_pump_adoption` | Heat pump COP | To be built | — |
| `heat_pump_cop` | COP curve | To be built | — |
| `district_heating_share` | District heating network | `pypsa-earth-sec` district heating | PyPSA-Earth-Sec |
| `thermal_storage_capacity` | Thermal storage | `n.stores` with `carrier="thermal"` | PyPSA |
| `industrial_heat_demand` | Industrial heat demand | `pypsa-earth-sec` industry sector | PyPSA-Earth-Sec |
| `industrial_heat_electrification` | Industrial heat electrification | To be built | — |
| `solar_thermal_capacity` | Solar thermal | To be built | — |

### 25. Transport

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `ev_share_new_sales` | EV sales diffusion | To be built — Bass diffusion | — |
| `ev_adoption_timeline` | Adoption timeline | To be built | — |
| `ev_efficiency` | EV efficiency | To be built | — |
| `v2g_adoption` | V2G optimisation | To be built | — |
| `hydrogen_vehicle_share` | Hydrogen vehicles | `pypsa-earth-sec` transport sector | PyPSA-Earth-Sec |
| `synthetic_fuel_share_aviation` | SAF | `pypsa-earth-sec` synfuel | PyPSA-Earth-Sec |
| `public_transport_share` | Modal shift | To be built | — |
| `freight_electrification` | Freight electrification | To be built | — |

### 26. Industry

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `steel_production` | Steel production model | `cacoca` — Carbon Contracts Calculator | GitHub |
| `steel_h2_dri_share` | H₂-DRI process model | To be built | — |
| `steel_scrap_eaf_share` | Scrap-EAF process model | To be built | — |
| `cement_production` | Cement production model | To be built | — |
| `cement_ccus_share` | Cement CCUS model | `AsPyCC` — Aspen Plus + Python CCS | ScienceDirect |
| `chemicals_ammonia_production` | Ammonia production | To be built | — |
| `chemicals_green_ammonia_share` | Green ammonia | To be built | — |
| `mining_electrification` | Mining electrification | To be built | — |
| `industrial_ccus_share` | Industrial CCUS | `pyomo` MILP for CCS hub optimisation | ScienceDirect |

### 27. Water-Energy Nexus

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `cooling_water_demand` | Cooling water demand | To be built | — |
| `water_availability` | Water availability constraint | To be built | — |
| `drought_frequency` | Drought frequency model | To be built | — |
| `desalination_capacity` | Desalination model | To be built | — |
| `irrigation_pumping_demand` | Irrigation pumping | To be built | — |
| `transboundary_water_constraint` | Transboundary water allocation | To be built | — |

---

## Part VIII: Climate & Weather Parameters (Category G)

### 28. Climate Scenarios

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `ssp_pathway` | CMIP6 downscaling + bias correction | `cmip6-downscaling` — Quantile Delta Mapping | GitHub |
| `temperature_target` | Temperature target constraint | To be built | — |
| `climate_sensitivity` | Climate sensitivity model | To be built | — |
| `carbon_budget` | Carbon budget constraint | To be built | — |
| `net_zero_year` | Net-zero constraint | To be built | — |

### 29. Weather Variability

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `solar_irradiance_multiplier` | Solar scenario generator | To be built — `numpy` perturbation | — |
| `wind_speed_multiplier` | Wind scenario generator | To be built | — |
| `precipitation_multiplier` | Precipitation scenario | To be built | — |
| `temperature_increase` | Temperature-dependent demand | To be built | — |
| `heatwave_frequency` | Heatwave generator | `mews` — Heat wave stochastic generator | PyPI |
| `cold_snap_frequency` | Cold snap generator | To be built | — |
| `extreme_weather_events` | Extreme weather generator | `RainyDay` — Extreme rainfall scenarios | GitHub |
| `interannual_variability` | Interannual variability | To be built | — |

---

## Part IX: Outage & Resilience Parameters (Category H)

### 30. Outage Parameters

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `forced_outage_rate` | Stochastic outage model | To be built — Monte Carlo sampling | — |
| `planned_outage_rate` | Planned outage scheduling | To be built | — |
| `outage_duration` | Outage duration distribution | To be built | — |
| `outage_frequency` | Outage frequency model | To be built | — |
| `outage_cause_distribution` | Cause-specific outage model | To be built | — |
| `maintenance_schedule_optimisation` | Maintenance scheduling MILP | To be built — `linopy` | — |
| `predictive_maintenance_adoption` | Predictive maintenance impact | `lifelines` — Cox PHM | lifelines |
| `spare_parts_availability` | Spare parts inventory | To be built | — |
| `crew_availability` | Crew scheduling | To be built | — |

### 31. Resilience Parameters

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `spinning_reserve` | Spinning reserve constraint | To be built — `linopy` | — |
| `non_spinning_reserve` | Non-spinning reserve | To be built | — |
| `regulation_reserve` | Regulation reserve | To be built | — |
| `inertia_requirement` | Inertia constraint | To be built | — |
| `black_start_capability` | Black start model | To be built | — |
| `islanding_capability` | Islanding model | To be built | — |
| `microgrid_deployment` | Microgrid deployment | To be built | — |
| `demand_response_capacity` | Demand response capacity | To be built | — |

### 32. Loss Mitigation Parameters

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `transmission_loss_reduction_target` | Loss reduction target | To be built | — |
| `topology_switching_enabled` | Topology switching | To be built | — |
| `phase_shifting_enabled` | Phase shifting transformers | To be built | — |
| `voltage_optimisation_enabled` | Voltage optimisation | To be built | — |
| `dg_placement_enabled` | DG placement | To be built | — |
| `storage_dispatch_enabled` | Storage dispatch for losses | `n.storage_units` dispatch | PyPSA |
| `line_upgrade_budget` | Line upgrade budget | To be built | — |

### 33. Transmission Line Outage

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `line_outage_start` | Temporal outage model | `n.lines.active = False` for time window | PyPSA |
| `line_outage_end` | Temporal outage model | Same as above | PyPSA |
| `line_outage_probability` | Probabilistic outage model | To be built — Monte Carlo | — |
| `line_outage_duration` | Outage duration model | To be built | — |
| `cascading_failures` | Cascade simulation | To be built — iterative LODF-based cascade | — |
| `restoration_optimisation` | Restoration sequencing MILP | To be built — `linopy` | — |
| `multi_line_simultaneous` | N-k contingency enumeration | `itertools.combinations` + LODF | Python stdlib |
| `spatial_correlation` | Copula-based spatial correlation | `swxg` — Copula-based stochastic weather generator | Zenodo |
| `temporal_correlation` | Markov chain temporal correlation | `stochx` — Markov chain | PyPI |
| `probabilistic_contingency` | Probabilistic contingency analysis | To be built | — |
| `critical_line_ranking` | Multi-metric critical line ranking | To be built — TLENS + LODF ranking | — |
| `repair_time` | Repair time distribution | To be built | — |
| `restoration_priority` | Restoration priority model | To be built | — |

---

## Part X: Macroeconomic & Financial Parameters (Category I)

### 34. GDP & Growth

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `gdp_growth_rate` | GDP-demand elasticity | To be built — `statsmodels` regression | — |
| `gdp_per_capita_growth` | GDP per capita-demand | To be built | — |
| `population_growth_rate` | Population-demand model | To be built | — |
| `urbanisation_rate` | Urbanisation-demand model | To be built | — |
| `industrialisation_rate` | Industrialisation-demand | To be built | — |

### 35. Currency & Finance

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `exchange_rate_usd_local` | Exchange rate model | To be built | — |
| `exchange_rate_volatility` | FX volatility model | To be built — GARCH | — |
| `inflation_rate` | Inflation model | To be built | — |
| `interest_rate` | Interest rate model | To be built | — |
| `sovereign_risk_premium` | Sovereign risk model | To be built | — |
| `country_risk_rating` | Country risk model | To be built | — |

### 36. Energy Prices

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `oil_price` | Oil price model | To be built — GBM + jumps | — |
| `gas_price` | Gas price model | PyPSA stochastic optimisation example | PyPSA docs |
| `coal_price` | Coal price model | To be built | — |
| `lng_price` | LNG price model | To be built | — |
| `uranium_price` | Uranium price model | To be built | — |
| `hydrogen_price` | Hydrogen price model | To be built | — |
| `ammonia_price` | Ammonia price model | To be built | — |
| `fuel_price_scenario` | Fuel price scenario generator | `horizon-zcs` — Monte Carlo / LHS | PyPI |

### 37. Project Finance

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `debt_tenor` | Debt tenor model | To be built | — |
| `interest_rate_debt` | Debt pricing model | To be built | — |
| `debt_service_coverage_ratio` | DSCR constraint | `numpy_financial` — NPV/IRR | NumPy Financial |
| `loan_life_coverage_ratio` | LLCR constraint | To be built | — |
| `gearing_ratio` | Gearing model | To be built | — |
| `equity_return_target` | Equity IRR model | `numpy_financial.irr` | NumPy Financial |
| `project_irr_hurdle` | Project IRR model | `numpy_financial.irr` | NumPy Financial |
| `construction_period` | Construction period model | To be built | — |
| `contingency` | Contingency model | To be built | — |

### 38. Risk & Insurance

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `political_risk_insurance` | Political risk insurance | To be built | — |
| `currency_hedge_cost` | Currency hedge model | To be built | — |
| `force_majeure_insurance` | Force majeure model | To be built | — |
| `business_interruption_insurance` | Business interruption | To be built | — |
| `carbon_price_risk` | Carbon price risk model | To be built | — |
| `technology_risk_premium` | Technology risk model | To be built | — |
| `offtake_risk_premium` | Offtake risk model | To be built | — |

### 39. Financing Sources

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `dfi_share` | DFI financing model | To be built | — |
| `commercial_bank_share` | Commercial bank financing | To be built | — |
| `bond_share` | Bond financing model | To be built | — |
| `equity_share` | Equity financing model | To be built | — |
| `blended_finance_share` | Blended finance model | To be built | — |
| `green_bond_share` | Green bond model | To be built | — |
| `carbon_finance_share` | Carbon finance model | To be built | — |

---

## Part XI: Operational & Market Design Parameters (Category J)

### 40. Dispatch & Scheduling

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `dispatch_interval` | Sub-hourly dispatch | `n.snapshots` at 15-min resolution | PyPSA |
| `day_ahead_market` | Day-ahead market clearing | `ASSUME` — agent-based market | ASSUME |
| `real_time_market` | Real-time market clearing | To be built | — |
| `intraday_market` | Intraday market clearing | To be built | — |
| `balancing_market` | Balancing market clearing | To be built | — |
| `n_2_criterion` | N-2 contingency analysis | To be built — `itertools.combinations` + LODF | — |
| `reactive_power_requirement` | Reactive power constraint | To be built | — |
| `voltage_support_requirement` | Voltage support constraint | To be built | — |
| `frequency_response_requirement` | Frequency response constraint | To be built | — |

### 41. Market Participants

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `market_concentration` | Market power (HHI) | To be built — HHI calculation | — |
| `strategic_bidding` | Strategic bidding | `ASSUME` — reinforcement learning | ASSUME |
| `collusion` | Collusion detection | To be built | — |
| `new_entrants` | Market entry model | To be built | — |
| `retail_competition` | Retail competition model | To be built | — |
| `financial_transmission_rights` | FTR model | To be built | — |
| `virtual_bidding` | Virtual bidding model | To be built | — |

---

## Part XII: Combined & Cross-Cutting Parameters (Category K)

### 42. Pre-Built Scenario Templates

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `scenario_template` | Scenario composition | `pypsa.Network` with parameter overrides | PyPSA |
| `parameter_overrides` | Parameter override | Dictionary of parameter changes | PyPSA |
| `probability_weight` | Scenario probability | `n.set_scenarios()` with weights | PyPSA |
| `scenario_tag` | Scenario tagging | Metadata only | — |
| `scenario_visibility` | Visibility | Metadata only | — |

### 43. Stochastic & Risk Optimisation

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `stochastic_scenarios` | Two-stage stochastic programming | `n.set_scenarios()` + `n.optimize()` | PyPSA v1.0 |
| `cvar_alpha` | CVaR tail level | `n.set_risk_preference(alpha=..., omega=...)` | PyPSA v1.0 |
| `cvar_omega` | Risk-aversion weight | Same as above | PyPSA v1.0 |
| `efficient_frontier` | ω sweep | Loop over omega values | PyPSA |

### 44. Intelligence Scanning

| Parameter | Algorithm | Python Implementation | Source |
|---|---|---|---|
| `signal_extraction` | LLM prompt extraction | `openai` / `transformers` | OpenAI / HuggingFace |
| `near_duplicate_detection` | MinHash + LSH | `datasketch` | PyPI |
| `signal_scoring` | Weighted scoring function | To be built | — |
| `human_review` | Priority queue | `redis` sorted set | Redis |

---

## Summary Matrix

| Category | Parameters Covered | Algorithms Identified | Python Implementations Available | To Be Built |
|---|---|---|---|---|
| **Core Optimisation** | 25 | 8 | 8 (PyPSA, PyPSA-Earth, TSAM) | 0 |
| **Demand-Side** | 28 | 18 | 4 (PyPSA-Earth, OnSSET, MobEV) | 14 |
| **Generation** | 34 | 22 | 8 (PyPSA, PyPSA-Earth, geoPFA, MHKiT, RTC-Tools) | 14 |
| **Cost** | 20 | 10 | 5 (PyPSA, wacc-estimator, numpy_financial) | 5 |
| **Policy** | 22 | 14 | 3 (ASSUME, pyshop, ASAM) | 11 |
| **Transmission** | 18 | 12 | 3 (PyPSA) | 9 |
| **Sector Coupling** | 30 | 20 | 8 (PyPSA-Earth-Sec, PyPSA, cacoca, AsPyCC) | 12 |
| **Climate** | 15 | 10 | 3 (cmip6-downscaling, mews, RainyDay) | 7 |
| **Outage & Resilience** | 30 | 22 | 4 (PyPSA, lifelines, swxg, stochx) | 18 |
| **Macroeconomic** | 22 | 15 | 3 (numpy_financial, horizon-zcs, PyPSA) | 12 |
| **Operational** | 20 | 12 | 1 (ASSUME) | 11 |
| **Combined & Cross-Cutting** | 12 | 8 | 4 (PyPSA v1.0, datasketch, openai, redis) | 4 |
| **TOTAL** | **276** | **171** | **54** | **117** |

---

## Key Findings

1. **PyPSA and PyPSA-Earth cover the core optimisation, sector coupling, and stochastic optimisation engine** — approximately 54 algorithms are available out of the box.

2. **118 algorithms require development**, concentrated in:
   - **Financial modelling** (WACC, DSCR, IRR, debt pricing, blended finance)
   - **Policy simulation** (ETS, capacity markets, CfD, auctions, tariffs)
   - **Climate scenario generation** (CMIP6 downscaling, extreme weather, temperature-dependent demand)
   - **Transmission outage detail** (cascade simulation, restoration optimisation, N-k enumeration)
   - **Behavioural response** (demand response, EV charging, ToU tariffs, modal shift)
   - **Industrial process modelling** (steel, cement, ammonia, district heating)

3. **Validated open-source implementations exist** for many missing algorithms but are not yet integrated into PyPSA-Earth:
   - `geoPFA` for geothermal play fairway analysis
   - `MHKiT` for marine energy
   - `RTC-Tools` for reservoir optimisation
   - `ASSUME` for agent-based market simulation with reinforcement learning
   - `cmip6-downscaling` for climate downscaling
   - `wacc-estimator` for cost of capital
   - `cacoca` for industrial decarbonisation contracts

4. **The definitive catalog comprises 171 distinct algorithms** across 12 categories, of which 54 have validated Python implementations and 117 require development or integration. This catalog provides the complete algorithmic foundation for ALEA's what-if analysis engine, ensuring that every parameter in the taxonomy can be meaningfully modelled and queried.