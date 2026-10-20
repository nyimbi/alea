# Coupling pack — supply, emissions, grid and employment factors

## What this pack covers

Forty-two nodes, all `role=free` on the shipped graph, and all but four still
carrying the catalog placeholder signature (`unit: None`, range `(0, 1e6)`,
default `500000.0`): eight employment factors, seven pollutant masses, six
conversion-plant capacities, three marine/gravity capital rates, three project
lead times, and a remainder of grid, asset and reserve stocks. The work splits
along the seam the slice itself has. The **capacities** and the **employment
factors** have bases the graph already carries — the fleet balance, the
installed MW of each technology, the route-km of transmission — so they couple
by being named, and five of them by determining a new product. The
**pollutants** have no base at all: the catalog's own `param_eqn.md` says
`nox_emissions ← generation_coal, generation_gas`, and `generation_coal` is not
a node; the graph's only activity base is `generation_twh`, a fleet total, and
`emission_factor_*` covers CO2 only. That family is deferred with the reason
stated per row rather than closed on a fabricated factor. Five nodes derive,
twenty-four are read, thirteen defer. Every proposed right-hand side was run
through the BRIEF's symbol check and the dimensional walker; both are printed at
the end.

**State:** 42 in scope — 5 derive, 24 read (3 of the reads blocked on a
capacity retype outside this slice), 13 defer. Two shipped equations are
rewritten (`fleet_build_balance`, `water_availability_constraint`) and five new
nodes are proposed to carry the products that close a read.

## Rows

`kind` is `derive` (this node becomes an lhs), `read` (this node is an operand
of the named equation) or `defer`. For a read row the `equation` cell names the
consumer; the consumer's own arithmetic is in **Products that close a read**
below, so the table stays one screen wide.

| node | class | kind | unit | range | role / det | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `baseline_emissions` | PRODUCT | derive | `MtCO2/year` | `[0, 10000]` — the counterfactual is at least the observed and at most the graph's own `emissions_mtco2_per_year` ceiling, doubled for headroom | derived / physical | `baseline_emissions = emissions_mtco2_per_year + additional_abatement_mtco2` | Emissions the fleet would have produced without the abatement the project delivers. The identity is the FRM's own `reductions = baseline − project − leakage`, solved for the baseline with the leakage term omitted; the graph carries `additional_abatement_mtco2` (45.0 MtCO2/year at defaults) and `emissions_mtco2_per_year` (25.777), giving 70.777. The omitted leakage term is stated rather than invented: no node carries a leakage mass. | `None` — algebraic rearrangement of the shipped identity, no coefficient asserted | `baseline_emissions = abatement_fraction`-style ratio: `abatement_fraction` is not a node, and a ratio cannot be an lhs that is also the denominator's base. `baseline_emissions = generation_twh * emission_factor_coal_t_per_mwh` was rejected: it prices the whole fleet at the coal factor and calls that a baseline |
| `regulation_reserve` | PRODUCT | derive | `MW` | `[0, 3000]` — the two shipped components are each `(0, 20000)`, but each is a share of peak demand bounded at 0.5, so 2 × 0.5 × peak = peak; 3000 covers the 10 GW fleet with margin | derived / policy | `regulation_reserve = regulation_up_requirement + regulation_down_requirement` | The regulation band the system must hold, up plus down. Both halves already ship as `regulation_up_requirement` and `regulation_down_requirement`, each `share × peak_demand` at 0.01 × 8500 = 85.0 MW; the total is 170.0 MW. The node is the sum, not a second derivation of its parts. | `Stoft 2002, Power System Economics, ch. 5` — the source the two shipped components cite | `regulation_reserve = regulation_reserve_share * peak_demand_mw`, which the prior classification pack proposed. It double-counts: the shipped `regulation_up_definition` and `regulation_down_definition` already partition the band, and a third share over the same peak would leave the three equations inconsistent at any default. A `regulation_reserve_share` node also does not exist |
| `black_start_capability` | PRODUCT | derive | `1` | `[0, 1000]` — a unit count; 0.02 × a fleet of at most a few hundred units | derived / policy | `black_start_capability = black_start_requirement * number_of_generators` | Units the operator must hold capable of black start. The share ships (`black_start_requirement`, 0.02) and the count is retyped in this pack; the product is 4.4 units at defaults. Distinct from the shipped `black_start_capable_mw` = 180 MW, which states the same requirement in capacity rather than in units — the two are the two registers of one obligation. | `None` — product of a shipped share and a shipped count | Deriving it from `firm_capacity_mw` would repeat `black_start_capable_mw` under a second name. A `max(1, …)` floor would break the derivative rule |
| `lifeline_threshold` | ALIAS | derive | `MWh/year` | `[0, 10]` — the shipped `energy_poverty_line_mwh_per_household` carries `(0, 10)`; a threshold above 10 MWh/year is not a lifeline | derived / physical | `lifeline_threshold = energy_poverty_line_mwh_per_household` | The consumption level below which a household qualifies for the lifeline tariff. The graph already carries that level: the MTF Tier 2/3 boundary at 1.0 MWh/year per household, with `energy_poor_consumption_mwh_per_year` (0.35) as the draw of a household below it. The threshold is the line, so the node is an alias onto it. | `None` — alias | `lifeline_threshold` in kWh/month: the prior pack's form needs `households_total × lifeline_share`, and `lifeline_share` is not a node. kWh/month is also a different unit from every other consumption node in the graph |
| `transmission_lead_time` | PRODUCT | derive | `years` | `[0, 20]` — permitting plus a construction period capped at 96 months (8 years); 20 covers both at their ceilings | derived / physical | `transmission_lead_time = construction_period / 12 + cross_border_permitting_time` | Years from decision to energisation for a transmission line: the build period plus the cross-border permit. `construction_period` ships in **months** (30), so the division is a unit conversion, not a scale factor; the permit is retyped to years in this pack at 2.0. Total 4.5 years at defaults. | `None` — sum of two durations the graph carries | `transmission_lead_time + construction_period / 12` (the prior pack's form) puts the target on the right, which `solve_for` cannot invert. `capex_transmission`-derived length was considered and rejected: route length does not determine permit duration |
| `number_of_generators` | BASE-NEEDED | read | `1` | `[0, 1000]` — a 10–19 GW fleet holds tens to a few hundred units; 1000 is the ceiling for a heavily distributed fleet | free / physical | `--` rhs of `black_start_capability` | Units in the fleet, not sites. Default 220, the count `scada_telemetry_sites` carries, because the graph has no unit-level register and 220 units over a ~19 GW installed fleet averages ~86 MW per unit — the right order for a mixed thermal/hydro fleet. The placeholder 500000.0 is not a count. | `None` — a register count | `number_of_generators = scada_telemetry_sites` as an equality: a site is not a unit, and several units share a site. Making it an equation would assert one unit per site and put the two nodes permanently in lockstep when the fleet grows |
| `circuit_breakers` | BASE-NEEDED | read | `1` | `[0, 5000]` — one breaker per primary feeder bay plus a margin; `distribution_feeders_total` ships `(0, 5000)` | free / physical | `--` rhs of `circuit_breaker_density_per_km` | Feeder-head circuit breakers on the distribution network. Default 500, one per primary feeder (`distribution_feeders_total` = 500). Sectionalisers and LV breakers are outside the count; the node states the primary-feeder bay only. | `None` — a register count | `circuit_breakers = distribution_feeders_total` as an equality, which asserts 1:1 where the honest statement is a count that happens to sit near the feeder count. Reading it into a density keeps the number an input |
| `biomass_sustainability_limit` | THRESHOLD | read | `MW` | `[0, 30000]` — the range of `biomass_capacity` itself, so the ceiling can bind or not | free / policy | `biomass_capacity <= biomass_sustainability_limit` (`leq`) | The sustainable biomass resource expressed as an installable capacity ceiling. Default 200 MW against a 100 MW build at defaults, so the bound holds with room; setting it below 100 makes the constraint bind, which is what a ceiling is for. | `IEA/NEA Projected Costs of Generating Electricity` — the archived text's treatment of sustainable-biomass supply as a limit on the build | The prior pack's `biomass_capacity * 8760 * capacity_factor_biomass * biomass_fuel_t_per_mwh <= limit` in tonne/yr: the graph has no heat rate and no fuel-mass factor for biomass, so the mass ceiling cannot be formed. A `leq` whose lhs is `biomass_capacity` needs no heat rate |
| `water_availability` | PRODUCT | read | `1` | `[0, 2]` — a multiplier on a flow: 0 is a closed source, 2 a wet year; the shipped flow carries its own ceiling | free / physical | `--` rhs of the rewritten `water_availability_constraint` | A multiplier on the water the project may withdraw. The graph already ships the flow (`water_availability_m3`, 200e6 m3/year) and the inequality that compares it to demand; the multiplier is the scenario lever on that comparison. Default 1.0 — the unmodified flow — so the constraint reads 200e6 ≥ 93.2e6 at defaults. | `None` — dimensionless multiplier | Aliasing `water_availability` onto `water_availability_m3`, which the catalog's own description ("Water availability multiplier") forbids: one is a share and the other is a flow, and the two spellings would collapse a multiplier into the quantity it multiplies |
| `biogas_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` — the band of the shipped `biomass_capacity` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of anaerobic digestion. Default 0.0: the graph's fleet balance ships a build that does not include it, and adding a non-zero default would move a balance the graph has already checked. | `None` — capacity register | Deriving it from `capex_biogas` inverts a rate into a quantity the optimiser chooses. `biomass_feedstock_cost` is a price and cannot size a plant |
| `landfill_gas_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of landfill-gas capture and generation. Default 0.0, same reason. | `None` — capacity register | Deriving from `capex_landfill_gas`, which is a cost rate. A landfill tonnage base does not exist in the graph |
| `gasification_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of biomass gasification. Default 0.0. | `None` — capacity register | Deriving from `capex_gasification`. No syngas or feedstock mass base exists |
| `pyrolysis_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of pyrolysis. Default 0.0. | `None` — capacity register | Deriving from `capex_pyrolysis`. No feedstock mass base |
| `waste_to_energy_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of municipal-waste combustion with energy recovery. Default 0.0. | `None` — capacity register | Deriving from `capex_waste_to_energy`. No MSW tonnage base; the IRENA jobs table counts 26,000 waste-to-energy jobs (note d) but gives no capacity to divide them by |
| `salinity_gradient_capacity` | BASE-NEEDED | read | `MW` | `[0, 30000]` | free / physical | `--` rhs of the rewritten `fleet_build_balance` | Electrical capacity of salinity-gradient conversion. Default 0.0; the technology is pre-commercial, as `capex_salinity_gradient`'s own description says. | `None` — capacity register | Deriving from `capex_salinity_gradient`. A river-mouth flow base does not exist |
| `employment_factor_biomass` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` — the band the graph's own `construction_jobs_per_mw` (0–50) and `om_jobs_per_mw` (0–10) bracket | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of biomass capacity. Default 5.1, the ratio the archived IRENA review implies (765,000 solid-biomass jobs over 149 GW of bioenergy capacity = 5.13 jobs/MW), with the caveat that the numerator is biomass jobs and the denominator is all bioenergy capacity, so the ratio is an upper estimate. | `IRENA employment factors` — Table 1 and the cumulative-capacity passage in `sources/archive/irena_jobs_2024.txt` | 4.3, the prior pack's uniform default, which is the graph's own fleet intensity (`construction_jobs_per_mw` + `om_jobs_per_mw`) applied to every technology. IRENA's own table implies 1.43–5.04 across technologies, so a uniform 4.3 erases the heterogeneity the node exists to carry |
| `employment_factor_coal` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of coal capacity. Default 4.3 — the graph's own construction-plus-O&M intensity — because the archived IRENA review covers renewable technologies only and prints no coal figure. The default is an assumption, stated as one. | `None` for the default — no archived coal employment factor; the identity it feeds cites IRENA | Citing IRENA for this row, which would attribute a number the review does not contain |
| `employment_factor_gas` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of gas capacity. Default 4.3, the graph's own intensity; IRENA covers no gas. | `None` for the default | As coal |
| `employment_factor_geothermal` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of geothermal capacity. Default 4.3, the graph's own intensity. The IRENA review gives 160,000 geothermal jobs but prints no geothermal capacity in the archived text, so the ratio cannot be read off it. | `None` for the default | Inventing a geothermal capacity to divide 160,000 by |
| `employment_factor_hydro` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of hydro capacity. Default 1.8: 2,324,000 jobs over 1,265 GW = 1.84. The lowest of the technologies in the table, which is the point — a hydro-heavy fleet is not a jobs fleet per MW. | `IRENA employment factors` | 4.3 uniform |
| `employment_factor_solar` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of solar PV capacity. Default 5.0: 7,107,000 jobs over 1,411 GW = 5.04. The highest, and it carries the manufacturing share, so it overstates an O&M-only intensity. | `IRENA employment factors` | 4.3 uniform |
| `employment_factor_wind` | BASE-NEEDED | read | `jobs/MW` | `[0, 20]` | free / fixed | `--` rhs of `fleet_employment_intensity_jobs_per_mw` | Jobs per installed MW of wind capacity. Default 1.4: 1,457,000 jobs over 1,017 GW = 1.43. | `IRENA employment factors` | 4.3 uniform |
| `employment_factor_transmission` | BASE-NEEDED | read | `jobs/km` | `[0, 20]` — jobs per route-km; 3.0 × 12,000 km = 36,000 jobs | free / fixed | `--` rhs of `transmission_jobs` | Jobs per route-km of high-voltage line. Default 3.0 is a planning figure, not extracted from the archive: the IRENA review covers generation, not networks, and no archived work states a line-km intensity. Stated as an assumption. | `IRENA employment factors` for the identity; `None` for the coefficient | 4.3 jobs/MW applied to line-km, which mixes the two units |
| `spare_parts_inventory` | BASE-NEEDED | read | `USD million` | `[0, 1000]` — a stock; the shipped fleet's gross capital is 12,000 USD million, so 1000 is an 8% spares holding | free / fixed | `--` rhs of `spare_parts_carrying_cost_usd_per_year` | The value of spares held against failure. Default 240, two percent of gross fleet capital (1,200 USD/kW × 10,000 MW = 12,000 USD million), which is a stated assumption rather than a measured figure. The placeholder 500000.0 is not a stock value. | `None` — a stock value | Retaining the placeholder as a default: 500000.0 USD million would be four percent of the entire fleet's capital in spare parts |
| `hydrogen_storage_cost` | PRODUCT | read | `USD/kWh` | `[1, 100]` — the shipped band, above-ground at the low end to salt cavern at the high end | free / stochastic | `--` rhs of `hydrogen_storage_capex_usd` | Installed cost per kWh of hydrogen storage. Already typed and ranged by the catalog; what it lacked is the base it multiplies, and `hydrogen_storage_capacity` (MWh, endogenous) is that base. The product is 0 at defaults only because the optimiser builds no hydrogen storage at defaults, not because the node is unread. | `Lazard LCOS` — the archived storage-cost analysis | `hydrogen_storage_cost = capex_battery` as an alias: the two technologies do not share a cost curve, and the node's own description distinguishes cavern from vessel |
| `capex_gravity_storage` | PRODUCT | read (blocked) | `USD/kWh` | `[200, 2000]` — the shipped band, inferred from pilot installations | free / stochastic | `--` rhs of `gravity_storage_capex_usd` (blocked) | Installed cost per kWh of gravity storage. The product that closes it needs `gravity_storage_capacity` in MWh, and that node is still a placeholder outside this slice — see Dependencies. | `Lazard LCOS` — the archived analysis lists gravity storage among the mechanical technologies | Aliasing it onto `capex_battery` or `capex_caes`; the pilot range is not a mature cost curve and the description says so |
| `capex_marine_otec` | PRODUCT | read (blocked) | `USD/kW` | `[5000, 25000]` — the shipped band, derived from pilots and cycle scaling | free / stochastic | `--` rhs of `marine_otec_capex_usd` (blocked) | Installed cost per kW of ocean-thermal conversion. Blocked on `marine_otec_capacity` being retyped to MW — see Dependencies. | `Lazard LCOS` for the storage-cost method; `None` for OTEC specifically, which no archived work prices | Treating the node as a levelised cost; it is a capital rate and needs a capacity |
| `capex_marine_tidal` | PRODUCT | read (blocked) | `USD/kW` | `[2500, 15000]` — the shipped band, wide because tidal range and tidal stream are one node | free / stochastic | `--` rhs of `marine_tidal_capex_usd` (blocked) | Installed cost per kW of tidal capacity. Blocked on `marine_tidal_capacity` — see Dependencies. The graph's separate `capex_tidal_range` (7,000, `(3000, 15000)`) is a second spelling of the range technology and is not in this slice. | `None` — no archived tidal cost table | Merging it with `capex_tidal_range`; that is a deprecation, and a deprecated node cannot be an equation target |
| `cross_border_permitting_time` | BASE-NEEDED | read | `years` | `[0, 10]` — a permit that outlasts a 10-year horizon is a refusal, not a delay | free / policy | `--` rhs of `transmission_lead_time` | Years to secure the cross-border permit for a line. Default 2.0 — two permitting cycles, the figure the graph's `financing_close_deadline` (18 months) sits inside. Retyped from the placeholder, which carried no unit. | `ENTSO-E adequacy studies` — the archived methodology's treatment of cross-border capacity as a lead-time item | The prior pack's `cross_border_permitting_time + construction_period / 12` as an lhs, which puts the target on the right of its own sum |
| `ac_voltage_limit` | DEFER | defer | — | — | free / policy | `--` | No voltage base exists. The prior pack's `ac_voltage_limit_kv / nominal_voltage_kv` needs `nominal_voltage_kv`, and the graph carries no kV node at all (checked: zero nodes with a volt-based unit). A constant rhs such as `ac_voltage_limit = 420.0` is a default wearing an equation's clothes. | — | Deriving it from `transmission_line_length_km` or `capex_transmission`, neither of which determines a voltage |
| `hydro_reservoir_level` | DEFER | defer | — | — | free / physical | `--` | The node is an initial state as a share of full supply, and the graph carries no reservoir energy capacity to take a share of. The prior pack's `hydro_reservoir_energy_mwh` base does not exist, and `hydro_drought_multiplier` is an inflow factor, not a level. | — | Aliasing it onto `hydro_capacity_factor` (0.5), which is an annual average output share, not a state at the start of the year |
| `nuclear_lead_time` | DEFER | defer | — | — | free / physical | `--` | No nuclear-specific duration base. `construction_period` is a single 30-month fleet-average build; reusing it would state that a nuclear plant is built in 2.5 years, which contradicts `asset_life_nuclear` (60 years) and the archived IEA/NEA text's own discussion of nuclear lead times. A technology-specific build period is the missing operand. | — | `nuclear_lead_time = construction_period / 12`; it is arithmetically clean and physically false |
| `reserve_accounts` | DEFER | defer | — | — | free / fixed | `--` | The base exists (`regulatory_asset_base`, 4,800 USD million) but the share does not, and no archived work states one. The two works that mention a reserve account define a different object: Short/Packey/Holt define it as accumulated deferred taxes reducing the rate base, and the World Bank handbook's "reserve" is a generation reserve. A 5% share would be a policy number with no citation. | — | `reserve_accounts = reserve_account_share * regulatory_asset_base` with a new uncited share node; `reserve_accounts = debt_service_usd_per_kw_year * total_capacity_mw / 1000`, which is a full year of debt service and so a debt-service reserve rather than an accounting reserve |
| `startup_cost_coal` | DEFER | defer | — | — | free / physical | `--` | A per-start cost with no starts count. `coal_starts_per_year` is not a node, and `min_up_time_coal` is itself a placeholder. The archived IEA/NEA and Short/Packey/Holt texts mention start-up costs only in passing ("avoiding start-ups and shut-downs"; "preproduction or start-up costs") and print no per-start table. | — | A per-start cost multiplied by a share of capacity; a share is not a count of starts |
| `startup_cost_gas` | DEFER | defer | — | — | free / physical | `--` | As coal: no starts count and no archived per-start cost. | — | As coal |
| `co_emissions` | DEFER | defer | — | — | free / physical | `--` | No per-pollutant emission factor and no per-fuel activity base. The catalog's own edge is `co_emissions ← generation_coal`, and `generation_coal` is not a node; the only activity base is `generation_twh`, a fleet total that is more than half hydro, wind and solar at defaults, so a CO factor times it would attribute a coal pollutant to a low-carbon fleet. `emission_factor_*` in the graph covers CO2 only. | — | `co_emissions = factor * generation_twh`; it is dimensionally clean and wrong about which plant emits |
| `nox_emissions` | DEFER | defer | — | — | free / physical | `--` | As `co_emissions`. The catalog's edge is `generation_coal, generation_gas`, neither of which is a node. | — | As `co_emissions` |
| `sox_emissions` | DEFER | defer | — | — | free / physical | `--` | As `co_emissions`. Catalog edge: `generation_coal`. | — | As `co_emissions` |
| `pm10_emissions` | DEFER | defer | — | — | free / physical | `--` | As `co_emissions`, with one extra route considered and refused: the graph ships `pm25_emissions` (aliased to `pm25_kt_per_year`, 20 kt/year), so a PM10/PM2.5 mass ratio would close this node. No archived work in `sources/archive/` states that ratio — the WHO AirQ+ manual works in ambient concentrations, not in a PM10/PM2.5 mass factor. | — | A PM10/PM2.5 ratio of 1.5–2, which is the right order and has no archived source |
| `mercury_emissions` | DEFER | defer | — | — | free / physical | `--` | As `co_emissions`. Catalog edge: `generation_coal`. No archived work in the directory mentions mercury at all. | — | As `co_emissions` |
| `voc_emissions` | DEFER | defer | — | — | free / physical | `--` | As `co_emissions`. Catalog edge: `generation_gas`. | — | As `co_emissions` |
| `water_pollution_load` | DEFER | defer | — | — | free / physical | `--` | No effluent volume and no loading factor. The prior pack's `effluent_m3 * bod_kg_per_m3` needs both and the graph carries neither; the water-quality nodes it does carry (`water_quality_index`, `water_quality_impact`) are normalised indices, not masses, and cannot be rescaled into a load without the volume. | — | `water_pollution_load = water_quality_impact`, which is a dimensionless index aliased onto a mass |

## Products that close a read

Five new nodes, each an lhs whose right-hand side reads one or more rows above.
None exists in the graph today (checked: no name collision).

```
fleet_employment_intensity_jobs_per_mw =
    (employment_factor_coal * coal_capacity
     + employment_factor_gas * gas_capacity
     + employment_factor_hydro * hydro_capacity
     + employment_factor_geothermal * geothermal_capacity
     + employment_factor_biomass * biomass_capacity
     + employment_factor_solar * solar_pv_capacity
     + employment_factor_wind * (wind_onshore_capacity + wind_offshore_capacity))
    / (coal_capacity + gas_capacity + hydro_capacity + geothermal_capacity
       + biomass_capacity + solar_pv_capacity + wind_onshore_capacity
       + wind_offshore_capacity)

transmission_jobs = employment_factor_transmission * transmission_line_length_km

spare_parts_carrying_cost_usd_per_year = spare_parts_inventory * discount_rate

hydrogen_storage_capex_usd = hydrogen_storage_cost * hydrogen_storage_capacity * 1000

circuit_breaker_density_per_km = circuit_breakers / distribution_network_km
```

At defaults: fleet intensity 78,800 / 18,900 = **4.169 jobs/MW** (coal 4.3×3000,
gas 4.3×1500, hydro 1.8×1500, geothermal 4.3×800, biomass 5.1×100, solar
5.0×10,000, wind 1.4×2,000); transmission **36,000 jobs** (3.0 × 12,000 km);
spares carrying **25.1 USD million/year** (240 × 0.1046); hydrogen storage
capex **0 USD** (capacity is 0 at defaults); breaker density **0.0111 /km**
(500 / 45,000).

Two shipped equations are rewritten rather than added.

```
battery_capacity + biomass_capacity + coal_capacity + csp_capacity + gas_capacity
+ geothermal_capacity + hydro_capacity + nuclear_capacity + oil_capacity
+ phs_capacity + wind_offshore_capacity + wind_onshore_capacity
+ biogas_capacity + landfill_gas_capacity + gasification_capacity
+ pyrolysis_capacity + waste_to_energy_capacity + salinity_gradient_capacity
    <= total_capacity_mw + storage_headroom_mw                      [fleet_build_balance]

water_availability * water_availability_m3 >= total_water_demand_m3
                                                    [water_availability_constraint]
```

The balance's left side sums to 9,700 MW against a 15,000 MW right side at
defaults, and the six added capacities are 0, so the rewrite does not move a
constraint the graph has already checked. The water constraint reads
200e6 ≥ 93.2e6 at the multiplier's default of 1.0.

## The two hazards this pack records

**The employment factors are bases, not a jobs total.** The prior classification
pack proposed `jobs_from_<tech> = employment_factor_<tech> * planned_capacity_<tech>_mw`
for all seven technologies and flagged the double count itself. It is real and
it is large: the fleet-intensity factors applied to installed capacity give
4.694 × 18,900 = 88,717 jobs against a shipped `direct_jobs` of 43,000, because
`direct_jobs` is already `total_capacity_mw * (construction_jobs_per_mw + om_jobs_per_mw)`.
Two nodes measuring the same employment at a factor of two is worse than an
uncoupled node. The identity shipped here is a **weighted-average intensity**,
dimensionally jobs/MW, which no total can be confused with. `transmission_jobs`
is the one genuine total, and it must not be added to `direct_jobs` either: the
transmission construction is already inside `construction_jobs_per_mw × total_capacity_mw`.
It is a separate stock, and the graph has no identity that adds it.

**The oil fleet is outside the identity.** The slice has no
`employment_factor_oil`; `oil_capacity` (300 MW) is therefore excluded from both
the numerator and the denominator, which keeps the ratio well defined. The
consequence is that the intensity describes 18,900 MW of an 18,900 MW fleet with
the 300 MW oil unit omitted — a 1.6% gap stated rather than silently averaged in.

## Dependencies

Operands this slice needs and does not own. Each is named in another pack's
register and must not be proposed here.

- `gravity_storage_capacity`, `marine_otec_capacity`, `marine_tidal_capacity` —
  all three still carry `unit: None`, range `(0, 1e6)`, default `500000.0`. They
  must be retyped to MW (MWh for gravity, whose cost is per kWh of *energy*)
  before the three blocked capex rows can ship. Each product is
  `rate * capacity * 1000`, and the walker returns `None` for a `None`-unit
  operand — undecidable, which is not a pass.
- `generation_coal`, `generation_gas` — named by the catalog's own
  `param_eqn.md` edges into the pollutant family, and absent from the graph.
  Without a per-fuel activity base, all seven pollutant rows stay deferred
  regardless of what factor is found.
- `nominal_voltage_kv` or `bus_voltage_kv` — the base `ac_voltage_limit` would
  ceiling. No node in the graph carries a volt-based unit.
- `coal_starts_per_year`, `gas_starts_per_year` — the count the two startup
  costs multiply.
- `hydro_reservoir_energy_mwh` — the capacity `hydro_reservoir_level` is a share
  of.
- `reserve_account_share` — the policy share `reserve_accounts` would multiply
  `regulatory_asset_base` by. No archived work states a value.
- `effluent_m3`, `bod_kg_per_m3` — the volume and loading `water_pollution_load`
  needs.
- Per-pollutant emission factors (any of NOx, SOx, CO, PM10, Hg, VOC) — not a
  node and not in `sources/archive/`.

## Rejected

- **`regulation_reserve = regulation_reserve_share * peak_demand_mw`** (the
  prior pack's row). It would double-count the shipped `regulation_up_definition`
  and `regulation_down_definition`, which already partition the band at
  0.01 × peak each, and the share node does not exist.
- **A uniform 4.3 jobs/MW for all eight employment factors.** The archived IRENA
  table implies 1.43 (wind) to 5.04 (solar) across the technologies it covers,
  so the uniform value is the graph's own fleet intensity masquerading as a
  per-technology factor.
- **`jobs_from_<tech>` totals for the seven technologies.** 88,717 jobs against
  a shipped `direct_jobs` of 43,000; see the hazard above.
- **`pollutant = factor * generation_twh`** for all seven emissions nodes. The
  activity base is a fleet total dominated by hydro, wind and solar; the factor
  would be a coal factor. Dimensionally clean, physically wrong.
- **`baseline_emissions` from an `abatement_fraction` ratio.** The ratio is not
  a node and cannot be the lhs while also dividing into the baseline.
- **`ac_voltage_limit` as per-unit against `nominal_voltage_kv`.** The base does
  not exist; a constant rhs is a default wearing an equation's clothes.
- **`water_availability` aliased onto `water_availability_m3`.** One is a
  multiplier, the other a flow; the catalog's own description of the first
  ("Water availability multiplier") forbids the merge.
- **`number_of_generators = scada_telemetry_sites` as an equality.** A site is
  not a unit; the count is a default justified in prose instead.
- **`biomass_sustainability_limit` as a tonne/yr fuel ceiling.** No heat rate
  and no biomass mass factor exist; the `leq` in MW needs neither.
- **Any `max(0, …)` or `min(…, ceiling)` clamp.** `gradients()` differentiates
  every equation and raises `DslError` on `abs`/`min`/`max`/`floor`/`ceil`. The
  two ceilings here are inequalities, which the DSL carries, not clamps.
- **`lifeline_threshold` in kWh/month.** A different unit from every other
  consumption node, and its base (`lifeline_share`) is not a node.

## Sources to fetch

Nothing in this pack cites a work whose copy is not already archived and
registered in `sources/INDEX.md`. The gaps are all coefficients, and each would
need a copy before the row it blocks could ship.

- **A per-pollutant emission-factor table by fuel** — US EPA AP-42, or the
  EMEP/EEA air-pollutant emission inventory guidebook. Unblocks all seven
  pollutant rows together with `generation_coal` / `generation_gas`.
- **IRENA's employment-factor annex**, or a national jobs study, giving
  jobs/MW by technology as a *factor* rather than as a jobs total. The archived
  2024 review states the method ("employment factor calculations") and prints
  jobs and capacity, but no factor table.
- **A coal, gas and geothermal employment intensity** — the archived review
  covers renewable technologies only, and gives geothermal jobs without a
  geothermal capacity to divide them by.
- **A transmission jobs-per-route-km figure.** The 3.0 jobs/km default is a
  planning assumption with no archived source.
- **Nuclear construction lead times by reactor type** — the archived IEA/NEA
  2020 text discusses lead times but prints no table.
- **Per-start cost for coal and gas units** — absent from IEA/NEA and from
  Short/Packey/Holt, which mention start-up costs only in passing.
- **A PM10/PM2.5 mass ratio**, if `pm10_emissions` is to be tied to the shipped
  `pm25_kt_per_year` node. The WHO AirQ+ manual works in concentrations.
- **A reserve-account share as a licence condition**, if `reserve_accounts` is
  to be closed. Neither archived work that mentions a reserve account means an
  accounting reserve.

## The check

Run against the shipped graph, with the retypes applied in memory only (no file
touched), over every proposed right-hand side — the five products, the two
rewritten equations, and each derive row.

```
SYMBOL CHECK: PASS — 0 unresolved rhs symbols across 16 proposed equations
UNIT CHECK  : PASS — every rhs dimension matches its lhs
UNDECIDABLE : none
DEPRECATED  : none
LHS ON RHS  : none
```

The one symbol the check would report as missing on an unmodified graph is
`reserve_account_share`, and that row is a `defer` — no equation reads it.
`fleet_employment_intensity_jobs_per_mw` reads `employment_factor_oil` in the
first draft of the identity and the check caught it: the node does not exist, so
oil is outside the ratio by construction rather than by omission.
