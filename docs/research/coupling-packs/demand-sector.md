# Coupling pack — demand-side and sector coupling

## What this pack covers

Thirty-three nodes from the demand-side and sector-coupling families: the
sector loads the catalog sketched as `unit: None default: 500000.0`, the
electrification shares that were inert because the energy they were a share of
did not exist, and the three transport shares whose tonne-km and route-km bases
the graph never carried. Fifteen of the thirty-three close here. Four become
equation targets — `desalination_demand`, `agricultural_irrigation_load`,
`hydrogen_export_port`, `temporary_camp_load` — and eleven close as operands of
a named new equation: `desalination_capacity` and `desalination_energy`,
`battery_storage_adoption`, `heat_pump_cop`, `industrial_heat_demand`,
`irrigation_pumping_demand`, `railway_electrification`,
`freight_electrification`, `transport_logistics`, `aviation_fuel_demand` and
`shipping_fuel_demand`. Eighteen defer, each with a stated reason; most of them
need a physical base (a volume, a tonnage, a night count) that no graph
quantity supplies and that this pack will not manufacture from a share.

The method is one rule applied twice. **A share needs a base, and a load needs
an intensity.** Where the base exists — `households_total`,
`transport_logistics`, `railway_route_km`, `hydrogen_export_volume`,
`industrial_heat_demand` — the product is arithmetic and the node closes.
Where only an intensity is missing, the node stays a scenario input and the
pack says so rather than inventing the coefficient: an invented kWh per hectare
is a number nobody can check wearing the shape of one that was measured.

Every right-hand side below was symbol-checked against the loaded graph and
every equation was run through `units.check_equation` against a retyped copy of
the graph, then propagated at the document's defaults. The results are quoted
in the rows; the verification script is reproduced under *Verification*.

## Rows

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `agricultural_irrigation_load` | PRODUCT | derive | `MW` | `[0, 5000]` — 5 GW is four times the propagated 57 MW and still under a tenth of the system's 8,500 MW peak; the bound admits a decade of irrigation build-out without admitting a value that would swamp the load balance | `derived` / `fixed` | `agricultural_irrigation_load = irrigation_pumping_demand * 1000000 / 8760` | The average power irrigation pumping draws: the annual pumping energy in TWh converted to MWh and divided by the year's 8,760 hours. It is an average and not a peak — the catalog calls it a load, and a load that runs in daylight and in season has a peak well above this number; the graph carries one annual energy figure for it, so the average is the honest reading. At the shipped 0.5 TWh/year it is 57.1 MW. | `None` — a unit conversion and an averaging, no work behind it | The catalog's `A_irr × h_pump × ρ g η_pump` needs arable hectares, a pumping head and a pump efficiency, none of which exist; the hydraulic form is a different model of the same load and is not reproducible here. |
| `agricultural_machinery` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | The share is of *machinery energy*, not of agricultural demand; `agricultural_demand_twh` is the sector's electricity, which already excludes diesel machinery. Multiplying the share by it would count a fuel share against an electricity base and call the product electrification. Deferred until a machinery-energy base exists. |
| `airport_electrification` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | Ground-operations energy is the base and the graph carries no airport energy. `demand_twh` is the whole economy; taking a share of it would make the airport share a share of everything. |
| `aviation_fuel_demand` | PRODUCT | read | `MWh/year` | `[0, 2e7]` — 20 TWh is roughly seven times the shipped 3 TWh, enough for a decade of growth on a single-country market; the lower bound is zero, which is a scenario the model must be able to represent | `free` / `fixed` | `--` (operand of `synthetic_aviation_fuel_mwh`) | Aviation fuel loaded in the year, on a lower-heating-value energy basis. Retyped from `None`: the SAF share multiplies it, and a share of a unitless number is a unitless number. 3 TWh is about 250 kt of jet fuel, a domestic-and-regional volume, not a hub's throughput. | `None` — a scenario input | `PJ/year` (the classification pack's second proposal) is not a unit the registry carries, so the SAF product would be undecidable rather than merely awkward. `MWh/year` is what `synthetic_fuel_share_aviation` needs. |
| `battery_storage_adoption` | PRODUCT | read | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` (operand of `household_batteries`) | — | — | The share closes against the graph's own `households_total` (10 M at defaults), which batch 22 derived from population and household size. 0.05 gives 500,000 household batteries. |
| `cold_storage_load` | BASE-NEEDED | defer | `MWh/year` | `[0, 1e7]` | `free` / `fixed` | `--` | — | — | The catalog's cold-chain model is volume × intensity × capacity factor; there is no volume, no throughput and no degree-day base. A share of `agricultural_demand_twh` would be an invented coefficient, and the cold chain is not a fixed fraction of farm electricity — it is a stock of equipment that either exists or does not. |
| `construction_load` | BASE-NEEDED | defer | `MW` | `[0, 1000]` | `free` / `fixed` | `--` | — | — | `construction_period` exists (30 months) but construction *energy* does not. The catalog's `construction_energy_mwh / (construction_period × 730)` divides a quantity the graph lacks by a scale it would have to assume; the 730 is a month count the unit walker cannot see. |
| `construction_machinery` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | Same missing construction-energy base as `construction_load`. The share is of machinery energy and there is no machinery energy. |
| `desalination_capacity` | PRODUCT | read | `m3/year` | `[0, 2e9]` — 2 km³/year is the catalog's own `0–2000 Mm³/year` ceiling and four times the world's largest plant; the default 50 Mm³/year is a large coastal plant, about 137,000 m³/day | `free` / `fixed` | `--` (operand of `desalination_demand`) | Desalination capacity as an annual water volume, which is how the catalog states it (`Mm³/year`). Retyped from `None`: a capacity that multiplies an intensity in kWh/m³ has to be a volume, and a nameplate in MW would make the product an energy per unit of power. | `None` — a scenario input | `MW` nameplate, the classification pack's first proposal, would make `desalination_demand = capacity × 8760 × load_factor` a second, inconsistent statement of the same identity (two ways to compute one node). The volume basis is the catalog's own. |
| `desalination_demand` | PRODUCT | derive | `MWh/year` | `[0, 2e7]` — the 2 km³ ceiling at the 10 kWh/m³ top of the intensity range is 20 TWh; the propagated default is 0.2 TWh | `derived` / `fixed` | `desalination_demand = desalination_capacity * desalination_energy / 1000` | The electricity a desalination programme draws: the annual water volume times the specific energy of the process. Reverse osmosis sits at 2–6 kWh/m³ and thermal processes at 10–25, so the intensity node carries the process choice and this node carries the scale. At 50 Mm³/year and 4 kWh/m³ it is 200,000 MWh/year. | `Bottom-up load synthesis (catalog method cell)` | Deriving the *capacity* from a demand (`demand / (8760 × load_factor)`) would require the demand this equation determines — the target on both sides, which the affine solve path refuses. The volume basis is also the catalog's own. |
| `desalination_energy` | PRODUCT | read | `kWh/m3` | `[2, 10]` — 2 is the best modern RO with energy recovery, 10 is the top of the catalog's own band and the low end of thermal; the default 4 is a brackish-to-seawater RO plant | `free` / `fixed` | `--` (operand of `desalination_demand`) | Specific energy consumption of the desalination process, in kWh per cubic metre of product water. Retyped from `None`; the catalog's `what-if` table carries the same range and a default of 4. | `None` — a process parameter, not a work | `kWh/m3` is not in the unit registry's declared vocabulary but parses cleanly through Pint as `[mass]/[length]/[time]²`; the walker verified the equation decidable, so no registry entry is needed. |
| `emergency_shelter_load` | BASE-NEEDED | defer | `MW` | `[0, 500]` | `free` / `fixed` | `--` | — | — | Needs a shelter occupancy. `exposed_population` is the population in a dispersion range, not the population in shelters, and `resettlement_population_share` is already the camp base below — using it here would make the shelter load and the camp load the same quantity under two names. |
| `fishing_vessel_fuel` | BASE-NEEDED | defer | `litre/year` | `[0, 1e6]` | `free` / `fixed` | `--` | — | — | Needs effort hours and a burn rate, neither of which exists. `fishing_community_load` is the settlement's electricity, a different quantity from the fleet's diesel, and the two cannot be scaled into each other without a fuel-to-electricity conversion the graph does not carry. |
| `freight_electrification` | PRODUCT | read | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` (operand of `freight_electric_tonne_km`) | — | — | The share closes against `transport_logistics`, retyped below to tonne-km/year. 0.05 × 45 bn tonne-km = 2.25 bn electric tonne-km. |
| `heat_pump_cop` | PRODUCT | read | `1` | `[2, 6]` — the catalog's own band and the physically admissible one; below 2 a heat pump is a resistive heater with extra steps, and 6 is the top of the ground-source range at mild ambient | `free` / `fixed` | `--` (operand of `heat_pump_electricity_saving_mwh_per_year`) | Coefficient of performance: heat delivered per unit of electricity. Retyped from `None` to dimensionless with the catalog's own default 3.5. Held as a constant rather than a temperature curve because the graph's `temperature_increase` is itself a placeholder with no unit, and a curve over a placeholder is a curve over nothing. | `None` — a device parameter | `f(temperature_increase)`: `temperature_increase` is `None`-unit with the 500,000 placeholder, so any equation reading it is undecidable. The curve is the right long-run form and the wrong form until that node is repaired. |
| `hydrogen_export_port` | PRODUCT | derive | `MW` | `[0, 1000]` — the export hub's own scale; the propagated default is 2.3 MW average, which is a terminal at the shipped 20 GWh/year | `derived` / `fixed` | `hydrogen_export_port = hydrogen_export_volume / 8760` | The port's average throughput in megawatts: the annual hydrogen energy the terminal loads, spread over the year. A port is not a nameplate — the berth count and the storage inventory are the other two readings, and the graph carries neither — so the average flow is what the export volume determines. At 20,000 MWh/year it is 2.28 MW. | `None` — an energy-per-year to average-power conversion | A categorical `Tangier/Suez/Walvis Bay` port id, which is what `what-if.md` lists. A categorical cannot be an equation target and a name is not a quantity; the throughput is the numeric reading the name was standing in for. |
| `industrial_heat_demand` | PRODUCT | read | `TWh/year` | `[0, 200]` — the catalog's `0–500` narrowed: 200 TWh thermal is several times the graph's whole electricity demand (46.5 TWh), and a heat demand ten times the power system is outside anything a single-country scenario means | `free` / `fixed` | `--` (operand of `electrified_industrial_heat_twh`) | Industrial process heat in the year, on a thermal basis. Retyped from `None` to the catalog's own `TWh/year`. The 20 TWh default is a scenario assumption — about 1.7× the graph's industrial electricity demand (11.8 TWh) — and it is an assumption, not a measurement; the heat-to-electricity ratio of an industrial base is a survey result this repository does not hold. | `None` — a scenario input | Deriving it as `industrial_demand_twh × industrial_growth_factor` would state that process heat is electricity times a growth factor, which is a category error dressed as an identity. The catalog's `D_0 (1+g)^y` needs a base year's heat demand, which is exactly this node. |
| `irrigation_coverage` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | A share of arable land and the graph carries no arable-land node. The tempting identity — `irrigation_pumping_demand = irrigation_coverage × agricultural_demand_twh` — is false: coverage is the share of *land* irrigated, not the share of *electricity* that is pumping, and it would make a land statistic the allocation key for an energy total. Recorded in *Rejected* rather than shipped. |
| `irrigation_pumping_demand` | PRODUCT | read | `TWh/year` | `[0, 20]` — the catalog's own `0–100` narrowed to the graph's demand scale; 20 TWh is 43% of the whole system's demand at defaults, which is already an implausibly irrigation-heavy economy | `free` / `fixed` | `--` (operand of `agricultural_irrigation_load`) | The electricity irrigation pumping draws in the year. Retyped from `None` to the catalog's own `TWh/year`; the 0.5 TWh default is 15% of the graph's agricultural demand (3.38 TWh), which is the fraction the sector's own pumping is usually taken to be — stated as a scenario input, not derived. | `None` — a scenario input | Deriving it from `irrigation_coverage` is rejected above. Deriving it from a hectares × kWh/ha product needs both the land base and the intensity, and the intensity is the coefficient this pack will not invent. |
| `military_energy_demand` | BASE-NEEDED | defer | `MW` | `[0, 500]` | `free` / `fixed` | `--` | — | — | Needs an installation count and a per-base load. Neither exists, and a share of national demand would be a policy assumption about defence budgets wearing the shape of a measurement. |
| `mining_demand_growth` | BASE-NEEDED | defer | `MW` | `[0, 1000]` | `free` / `fixed` | `--` | — | — | Needs a mining load base and a mining growth rate; the graph has neither (`mining_growth_rate` does not exist, and `industrial_growth_factor` is the industrial sector's). The catalog's `ΔD_0 (1+g)^y` is a growth-on-a-base identity with both terms missing. |
| `mining_electrification` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | The share is of mining energy and no mining-energy node exists. Multiplying it by `industrial_demand_twh` would treat mining as a subset of manufacturing electricity, which it is not — mining load is largely off-grid and self-generated. |
| `mining_haulage` | BASE-NEEDED | defer | `tonne*km/year` | `[0, 1e10]` | `free` / `fixed` | `--` | — | — | Needs ore tonnage and haul distance. `steel_production` is the nearest activity base and it is the *output* of a different industry; using it would price the ore haul of a steel mill's feedstock as the whole mining fleet's haulage. |
| `mining_hydrogen_haulage` | BASE-NEEDED | defer | `tonne*km/year` | `[0, 1e10]` | `free` / `fixed` | `--` | — | — | Depends on `mining_haulage`, itself unbased. A share of a deferred base is deferred. |
| `port_electrification` | BASE-NEEDED | defer | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` | — | — | Port operations energy is the base and the graph carries none. `hydrogen_export_port` is a hydrogen terminal's throughput, not a port's total energy. |
| `post_harvest_processing_load` | BASE-NEEDED | defer | `MWh/year` | `[0, 1e7]` | `free` / `fixed` | `--` | — | — | Needs a crop tonnage and a processing intensity. `agricultural_demand_twh` is the sector's electricity, and taking a share of it would assume processing is a fixed fraction of farm demand — an assumption with no source and no way to be wrong. |
| `railway_electrification` | PRODUCT | read | `1` | `[0, 1]` (unchanged) | `free` / `fixed` | `--` (operand of `electrified_route_km`) | — | — | The share closes against the new `railway_route_km` base. 0.2 × 2,000 km = 400 electrified route-km. |
| `shipping_fuel_demand` | PRODUCT | read | `MWh/year` | `[0, 2e7]` — 20 TWh is ten times the shipped 2 TWh and the ceiling of a single-country bunker market; zero is a scenario the model must be able to represent | `free` / `fixed` | `--` (operand of `synthetic_shipping_fuel_mwh`) | Marine bunker fuel loaded in the year, on an LHV energy basis. Retyped from `None` for the same reason as aviation: the green-fuel share needs a dimensioned base. 2 TWh is about 170 kt of heavy fuel oil. | `None` — a scenario input | `PJ/year`, as above: not a registry unit. |
| `temporary_camp_load` | PRODUCT | derive | `MW` | `[0, 500]` — the classification pack's own ceiling for a camp load; the propagated default is 0.89 MW | `derived` / `fixed` | `temporary_camp_load = exposed_population * resettlement_population_share * energy_poor_consumption_mwh_per_year / persons_per_household / 8760` | The power a resettlement camp draws: the displaced population, divided by household size to get households, times the consumption an energy-poor household actually draws, spread over the year. The camp population is the resettled population — `resettlement_population_share` is the share of the exposed population physically or economically displaced, which is who a camp houses. The per-household figure is the graph's *energy-poor* draw (0.35 MWh/year) and not the mean (1.5), because a camp household is by construction at the bottom of the distribution; using the mean would overstate the load fourfold. At defaults: 5 M exposed × 2% = 100,000 people, 22,222 households, 0.89 MW. | `None` — a per-capita product over the graph's own population and household nodes | A dedicated `camp_population` base with an `unknown` default would close nothing and leave the node unreadable, which is the state it is in now. The proxy is stated in the prose so a scenario that wants a different camp size can move the resettlement share. |
| `tourism_load` | BASE-NEEDED | defer | `MW` | `[0, 500]` | `free` / `fixed` | `--` | — | — | Needs tourist-nights. No tourist, bed-night, or visitor node exists, and `commercial_demand_twh` is the whole service sector's electricity — a share of it would be a guess about the tourism share of the economy. |
| `transport_logistics` | PRODUCT | read | `tonne*km/year` | `[0, 1e12]` — 1e12 tonne-km is twenty times the shipped 45 bn and well above any single country's freight task; the lower bound is zero | `free` / `fixed` | `--` (operand of `freight_electric_tonne_km`) | Freight tonne-kilometres moved in the year: the base the batch-20 freight share was deferred for. Retyped from `None` to `tonne*km/year`. 45 bn tonne-km at 45 M people is about 1,000 tonne-km per person, the low end of the middle-income band. | `None` — a scenario input | Making it a *derived* product of a new `freight_tonne_km` base would add a node that is this node under another name; the classification pack's own row has `freight_tonne_km` as the operand and the logistics energy as the product, which reverses which of the two the graph actually needs. |
| `wastewater_treatment_load` | BASE-NEEDED | defer | `MWh/year` | `[0, 1e7]` | `free` / `fixed` | `--` | — | — | `total_water_demand_m3` is water *withdrawn*, not effluent returned, and the treatment intensity (kWh/m³) does not exist. Using the withdrawal as the effluent volume assumes every litre withdrawn is treated, which is the assumption the water balance exists to test. |
| `water_pumping_load` | BASE-NEEDED | defer | `MWh/year` | `[0, 1e7]` | `free` / `fixed` | `--` | — | — | The demand base exists (`total_water_demand_m3`, 93.2 M m³/year at defaults); the pumping intensity does not. A 0.3–1.0 kWh/m³ coefficient is the standard range and is not in this repository's archive, so the product waits rather than inventing the number. See *Sources to fetch*. |

### New nodes this pack declares

Four of the equations above target nodes that do not exist yet. Each is a
derived quantity with no default, per constraint 4.

| node | unit | range | equation | why it is a node and not an inline expression |
|---|---|---|---|---|
| `household_batteries` | `1` | `[0, 1e8]` | `household_batteries = battery_storage_adoption * households_total` | A count a report can name: 500,000 at defaults. The alternative is that `battery_storage_adoption` stays a share of nothing, which is its present state. |
| `railway_route_km` | `km` | `[0, 5e4]` | free, default `2000.0` | The base the rail share needs. 2,000 route-km is a single-country network of the size the graph's other bases assume (45,000 distribution circuit-km, 12,000 transmission-km). Free with a default, following batch 23's extensive-bases idiom. |
| `electrified_route_km` | `km` | `[0, 5e4]` | `electrified_route_km = railway_electrification * railway_route_km` | The product the share was waiting for; 400 km at defaults. |
| `freight_electric_tonne_km` | `tonne*km/year` | `[0, 1e12]` | `freight_electric_tonne_km = freight_electrification * transport_logistics` | 2.25 bn tonne-km at defaults. |
| `synthetic_aviation_fuel_mwh` | `MWh/year` | `[0, 2e7]` | `synthetic_aviation_fuel_mwh = synthetic_fuel_share_aviation * aviation_fuel_demand` | 150,000 MWh at defaults. |
| `synthetic_shipping_fuel_mwh` | `MWh/year` | `[0, 2e7]` | `synthetic_shipping_fuel_mwh = synthetic_fuel_share_shipping * shipping_fuel_demand` | 100,000 MWh at defaults. |
| `heat_pump_electricity_saving_mwh_per_year` | `MWh/year` | `[0, 1e8]` | `heat_pump_electricity_saving_mwh_per_year = heat_pump_adoption * households_total * household_consumption_mwh_per_year * (1 - 1 / heat_pump_cop)` | The electricity the heat pumps *displace*: `(1 − 1/COP)` is the fraction of resistive heat's electricity that a heat pump does not draw. 535,714 MWh/year at defaults. It is the only reading of the COP node that turns it into arithmetic. |
| `electrified_industrial_heat_twh` | `TWh/year` | `[0, 200]` | `electrified_industrial_heat_twh = industrial_heat_electrification * industrial_heat_demand` | 2.0 TWh at defaults. |

### Retypes

Eight nodes keep their identity and change their declaration. No unit the
registry does not carry is introduced; `kWh/m3` and `tonne*km/year` both parse
through Pint, and the walker returned `decidable=True, consistent=True` for
every equation that uses them.

| node | was | becomes | default |
|---|---|---|---|
| `desalination_capacity` | `None`, 500,000 | `m3/year` | `5e7` (50 Mm³/year) |
| `desalination_energy` | `None`, 500,000 | `kWh/m3` | `4.0` |
| `aviation_fuel_demand` | `None`, 500,000 | `MWh/year` | `3e6` |
| `shipping_fuel_demand` | `None`, 500,000 | `MWh/year` | `2e6` |
| `transport_logistics` | `None`, 500,000 | `tonne*km/year` | `45e9` |
| `heat_pump_cop` | `None`, 500,000 | `1` | `3.5` |
| `industrial_heat_demand` | `None`, 500,000 | `TWh/year` | `20.0` |
| `irrigation_pumping_demand` | `None`, 500,000 | `TWh/year` | `0.5` |

## Verification

The symbol check from BRIEF.md, run over every right-hand side in the pack:

```
from alea.prg.service import load_graph
from alea.prg.dsl import parse_side
g = load_graph()
for name, rhs in EQUATIONS:          # the eleven equations above
    missing = sorted(s for s in parse_side(rhs).symbols
                     if s not in g.nodes and s != name)
    assert not missing, (name, missing)
```

All eleven right-hand sides resolve against the graph's own node set; no operand
was invented. The eight new nodes were then added to a retyped copy of the
graph and every equation run through `alea.prg.units.check_equation` and
`propagate` at the document's defaults:

```
unit walker: 11/11 decidable+consistent
desalination_demand                          200000.0  [0, 2e7]     ok
agricultural_irrigation_load              57.07762557  [0, 5000]    ok
temporary_camp_load                       0.8878741755  [0, 500]     ok
hydrogen_export_port                      2.2831050228  [0, 1000]    ok
household_batteries                            500000.0  [0, 1e8]     ok
electrified_route_km                              400.0  [0, 5e4]     ok
freight_electric_tonne_km                  2250000000.0  [0, 1e12]    ok
synthetic_aviation_fuel_mwh                    150000.0  [0, 2e7]     ok
synthetic_shipping_fuel_mwh                    100000.0  [0, 2e7]     ok
heat_pump_electricity_saving_mwh_per_year  535714.2857  [0, 1e8]     ok
electrified_industrial_heat_twh                     2.0  [0, 200]     ok
railway_route_km                                 2000.0  [0, 5e4]     ok
```

No range excursion at defaults, no undecidable unit, no blocking conflict.
`gradients` was not run against the copy — every right-hand side is a product,
a quotient and a sum of declared symbols, with no `abs`, `min`, `max`, `floor`
or `ceil`, and the only function call in the pack is the reciprocal inside the
heat-pump saving, which is a `Pow`.

## Dependencies

- **`synthetic_fuel_share_aviation` and `synthetic_fuel_share_shipping` are
  outside this slice but close as a side effect.** They are the numerators of
  the two synthetic-fuel equations. If another pack owns them, that pack should
  know they are already read by this one; if it proposes a different product
  for them, the two batches will collide at authoring time.
- **`households_total`, `exposed_population`, `resettlement_population_share`,
  `energy_poor_consumption_mwh_per_year`, `persons_per_household`,
  `household_consumption_mwh_per_year`, `heat_pump_adoption`,
  `industrial_heat_electrification`, `hydrogen_export_volume`, `load_factor`,
  `agricultural_demand_twh`, `demand_twh`** are read here and are already
  declared and coupled. No change is asked of them.
- **`total_water_demand_m3`** is the base `water_pumping_load` and
  `wastewater_treatment_load` both need and cannot use without an intensity.
  When the intensity nodes land, both close in one batch against this base.
- **`temperature_increase`** is the operand `heat_pump_cop` would need for the
  temperature curve. It is `None`-unit with the 500,000 placeholder. Repairing
  it would let the COP become `f(ΔT)`; until then the COP is a constant and the
  curve is deferred.
- **`arable_land_hectares`, `freight_tonne_km`, `crop_tonnes`,
  `tourist_nights`, `camp_population`, `shelter_occupancy`, `military_bases`,
  `mining_energy_mwh`, `wastewater_m3_per_year`, `cold_storage_volume_m3`,
  `construction_energy_mwh`, `airport_operations_mwh`, `port_operations_mwh`,
  `agricultural_machinery_energy_mwh`** — the activity bases the eighteen
  deferred nodes need. Each is named in the classification pack's *NEW BASES
  NEEDED* section. This pack does not declare them: a base with an `unknown`
  default closes nothing, and inventing a default would be the placeholder
  problem in a new unit.

## Rejected

- **`irrigation_pumping_demand = irrigation_coverage * agricultural_demand_twh`.**
  The tempting identity, and false. Coverage is the share of arable *land*
  irrigated; the agricultural demand is the sector's *electricity*. Making a
  land statistic the allocation key for an energy total states that the two
  shares are the same number, which they are not: an irrigated hectare and a
  pumped kilowatt-hour are related by a head, a flow and an efficiency the
  graph does not carry. It would also have closed `irrigation_coverage` for
  free, which is exactly the kind of free closure that hides the error.
- **`desalination_capacity = desalination_demand / (8760 * load_factor)`.**
  Circular: the capacity would be determined by the demand that this pack
  determines from the capacity. Constraint 2 (the target only on the left)
  refuses it, and the volume basis is the catalog's own declaration anyway.
- **`desalination_demand` in `MWh` rather than `MWh/year`.** Batch 24's
  annual-quantity repair exists because fifteen nodes were stocks where they
  are flows; a demand that a revenue product divides is a flow, and this one is
  declared per year from the start.
- **`aviation_fuel_demand` and `shipping_fuel_demand` in `PJ/year`.** The
  classification pack proposes it twice. `PJ` is not in the registry, so the
  SAF product would be undecidable; `MWh/year` is the unit
  `synthetic_fuel_share_aviation` actually needs and the unit the rest of the
  sector family uses.
- **`heat_pump_cop = f(temperature_increase)`.** The right long-run form. The
  operand is a placeholder with no unit, so the equation would load, render,
  and read a name that supplies nothing — the exact failure BRIEF.md constraint
  3 describes. Deferred behind the `temperature_increase` repair.
- **`hydrogen_export_port` as a categorical.** `what-if.md` lists it as
  `Tangier / Suez / Walvis Bay / Saldanha`. A categorical cannot be an equation
  target, and a port *name* is not a quantity; the throughput in MW is the
  numeric reading the name was standing in for.
- **`emergency_shelter_load` sharing the camp population.** It would make the
  shelter load and the camp load one quantity under two names. They are
  different populations (displaced versus disaster-sheltered) and the graph
  carries neither.
- **`mining_haulage` from `steel_production`.** The nearest activity base and
  the wrong one: steel output is the mill's product, not the mine's ore
  tonnage, and the haul distance is absent regardless.
- **`transport_logistics` as a derived product of a new `freight_tonne_km`.**
  The classification pack's row has logistics *energy* as the product and
  tonne-km as the base. That reverses which of the two the graph needs: the
  freight share multiplies tonne-km, so tonne-km is the base and it is the node
  the share was deferred for. Declaring a second base would be the same
  quantity under another name.
- **`agricultural_machinery`, `construction_machinery` and the two port/airport
  shares as products against sector demand.** All four are shares of a
  *machinery* or *operations* energy that the graph does not carry. The
  sector electricity they would multiply excludes the fuel the machinery burns,
  so the product would report a fuel share against an electricity base and call
  it electrification.
- **Invented intensities.** A kWh per hectare, per tonne of crop, per cubic
  metre pumped, per tonne-km hauled, or per tourist-night would each close one
  deferred node and leave a coefficient nobody can check. The pack defers
  instead, and lists the works that would supply them.

## Sources to fetch

The four intensities the deferred loads need. None is archived; each is a
standard figure with a published range, and the equation should not ship until
the work is on disk and the range in the node cites it.

| quantity | node it unblocks | what is needed | where to look |
|---|---|---|---|
| Water pumping specific energy, kWh/m³ | `water_pumping_load` | A stated range covering source lift and distribution pressure (roughly 0.3–1.0 kWh/m³) | IEA or World Bank water-energy nexus reports; US DOE pumping-system sourcebooks |
| Wastewater treatment specific energy, kWh/m³ | `wastewater_treatment_load` | A range by treatment level (primary/secondary/tertiary) | IEA *Water-Energy Nexus*; national utility benchmarks |
| Cold-chain specific energy, kWh/m³/year or kWh/t | `cold_storage_load` | A per-volume or per-tonne intensity and a capacity factor | FAO cold-chain assessments; IIR cold-chain reports |
| Post-harvest processing energy, kWh/t | `post_harvest_processing_load` | Per-crop or per-process intensity | FAO agricultural energy handbooks; IRENA bioenergy assessments |
| Irrigation pumping energy, kWh/ha/year | `agricultural_irrigation_load`, `irrigation_pumping_demand` | A per-hectare intensity by irrigation method | FAO irrigation and drainage papers; World Bank irrigation energy studies |
| Mining haulage energy, kWh/tonne-km | `mining_haulage`, `mining_hydrogen_haulage` | Diesel and trolley-assist intensities by haul profile | ICMM or mining-industry decarbonisation studies |
| Heat pump COP curves | `heat_pump_cop` (to replace the constant) | COP against source/sink temperature difference | IEA *Heat Pumps* annexes; EHPA statistics |
| Aviation and marine bunker volumes | `aviation_fuel_demand`, `shipping_fuel_demand` (to replace the scenario defaults) | National bunker sales, MWh or tonnes | IEA oil statistics; national energy balances |

Two citations in this pack resolve to an existing index row.
`desalination_demand` cites **Bottom-up load synthesis (catalog method cell)**
(`sources/INDEX.md` key `catalog_method_cells`, `archived: n/a` — it names the
catalog's own method cell, and there is no paper to archive for it). Every
other equation carries `reference: None`, and each of those is a unit
conversion, an averaging, or a share-of-base product whose identity is the
arithmetic itself. That is ten `None`s, which is more than a handful; it is
the honest count for a batch of definitions and it is why the deferred rows
carry a fetch list rather than a fabricated reference.
