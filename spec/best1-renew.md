# PyPSA-X Pan-African: Comprehensive Renewable Energy Integration Specification

## From Solar and Wind to Geothermal, Biomass, Marine, and Beyond

---

## 1. Introduction

The preceding specification defined PyPSA-X Pan-African as a world-best platform across all capabilities. This extension specifies the **full incorporation of all renewable energy technologies**—not just solar PV and onshore wind, but geothermal, offshore wind, hydropower (including small hydro), biomass (solid, biogas, and liquid biofuels), concentrated solar power (CSP), marine energy (wave, tidal, ocean current, and ocean thermal), and green hydrogen derived from renewables. The platform must model each technology with the same rigour, spatial granularity, and temporal resolution as solar and wind, using the best available African resource data.

---

## 2. Solar Technologies

### 2.1 Solar Photovoltaic (PV)

**Resource Data**

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Global Solar Atlas (GSA)** | `https://globalsolaratlas.info/download` | Global | PVOUT (PV electricity output) at 30 arcsec (~1 km) resolution, 12×24 monthly profiles. GHI at 9 arcsec (~250 m), DNI at 9 arcsec. Data period 1994–2025 for most of Africa |
| **ERA5 Reanalysis** | `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels` | Global | Hourly solar irradiance, temperature, and other meteorological variables for generating hourly PV profiles via `atlite` |
| **PVGIS** | `https://re.jrc.ec.europa.eu/api/` | Global | PV performance modelling with three solar databases: PVGIS-SARAH2, PVGIS-NSRDB, and PVGIS-ERA5 |
| **SARAH-2** | `https://wui.cmsaf.eu/safira/action/viewProduktSearch` | Africa, Europe | 30-minute instantaneous surface solar irradiance, 1983–2017 |
| **An all-Africa dataset of supply regions** | `https://zenodo.org/records/14228370` | All Africa | Model Supply Regions (MSRs) for solar PV with hourly temporal resolution and kilometre-scale spatial resolution. Includes cluster data and shapefiles |

**Modelling Requirements**

- **PV technologies**: Fixed-tilt, single-axis tracking, and dual-axis tracking, with country-specific optimum tilt angles from GSA's OPTA data.
- **Rooftop and utility-scale**: Separate representation of rooftop PV (using settlement-level data from DRE Atlas and GEP) and utility-scale PV (using MSRs).
- **Hybrid PV-plus-storage**: Co-optimisation of PV with battery storage, including DC-coupled and AC-coupled configurations.
- **CSP with thermal storage**: Parabolic trough, central receiver, and linear Fresnel technologies, with molten salt and direct steam storage. CSP potential must be modelled for high-DNI countries (Morocco, Egypt, South Africa, Namibia, Botswana).

---

### 2.2 Concentrated Solar Power (CSP)

**Resource Data**

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Global Solar Atlas (DNI)** | `https://globalsolaratlas.info/download` | Global | Direct Normal Irradiation at 9 arcsec (~250 m) resolution, 12×24 monthly profiles |
| **SolarPACES CSP Database** | `https://solarpaces.nrel.gov/` | Global | CSP plant performance data for validation |
| **NREL CSP Cost Data** | `https://www.nrel.gov/csp/` | Global | Capital and O&M cost assumptions |

**Modelling Requirements**

- **Thermal energy storage**: 6–15 hours of molten salt storage, with country-specific sizing based on GHI/DNI profiles.
- **Hybridisation**: CSP with supplementary natural gas firing (for dispatchability), and CSP plus PV hybrid plants.
- **Water consumption**: CSP wet-cooling versus dry-cooling trade-offs, linked to the water-energy nexus module.

---

## 3. Wind Technologies

### 3.1 Onshore Wind

**Resource Data**

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Global Wind Atlas 3.0** | `https://globalwindatlas.info/en/download/high-resolution-maps/AFR` | Global | High-resolution wind speed and power density maps. GIS data downloadable as JSON and CSV. Sub-Saharan Africa poster maps available |
| **ERA5 Reanalysis** | `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels` | Global | Hourly wind speed at 100m, for generating hourly wind profiles |
| **An all-Africa dataset of supply regions** | `https://zenodo.org/records/14228370` | All Africa | Model Supply Regions (MSRs) for onshore wind with hourly temporal resolution and kilometre-scale spatial resolution |
| **Global Wind Atlas (World Bank)** | `https://datacatalog.worldbank.org/search/dataset/0038664` | Sub-Saharan Africa | Wind speed and power potential maps, GIS data stems from GWA |

**Modelling Requirements**

- **Turbine classes**: IEC Class I, II, III, and IV turbines, with country-specific hub heights (80m, 100m, 120m, 150m).
- **Wake effects**: Simplified wake loss modelling using fixed loss factors (5–12%) by country, or explicit wake modelling using PyPSA's `Link` components.
- **Repowering**: Modelling of wind farm repowering (replacing old turbines with newer, larger units) for existing sites.
- **Land-use constraints**: Exclusion of protected areas, steep terrain, and urban areas, using Copernicus land cover and WDPA data.

---

### 3.2 Offshore Wind

**Resource Data**

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Global Wind Atlas (Offshore)** | `https://globalwindatlas.info/en/download/gis-files` | Global | Offshore wind speed and power density |
| **GEBCO Bathymetric Data** | `https://www.gebco.net/data_and_products/gridded_bathymetry_data/` | Global | Seafloor depth for fixed-bottom versus floating platform assessment |
| **EEZ Boundaries** | `https://www.marineregions.org/` | Global | Exclusive Economic Zone boundaries for offshore resource allocation |
| **ERA5 (Offshore)** | `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels` | Global | Hourly offshore wind speeds |

**Modelling Requirements**

- **Platform types**: Fixed-bottom (monopile, jacket) for water depth <50m, and floating (semi-submersible, spar) for deeper waters.
- **Offshore wind potential by country**: High potential in South Africa, Namibia, Morocco, Senegal, Cabo Verde, and the Western Indian Ocean (Mozambique, Madagascar, Mauritius, Réunion).
- **Grid connection**: Submarine cable costs and losses, with distance-to-shore and distance-to-grid penalties.

---

## 4. Geothermal Energy

### 4.1 Resource Data

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Geothermal Atlas for Africa** | `https://geothermalatlasforafrica.org` | All Africa | Temperature models at 1km, 2km, 3km, and 4km depth, 3D conductive thermal model of the African lithosphere |
| **East African Rift Temperature and Heatflow Model (EARTH)** | `https://www.data.gov.uk/dataset/943bb8b3-3412-44c3-8ced-70b258d9a346/east-african-rift-temperature-and-heatflow-model-earth` | East Africa | GIS heat flow and temperature model with geothermal sites, hot springs, thermal conductivities, heat flow data, and major faults |
| **CRM-geothermal Fluid Atlas** | `https://crm-geothermal.eu` | Europe and Eastern Africa | GIS-based online platform with geospatial and geochemical data on geothermal fluids and critical raw materials |
| **Geothermal Wells** | `https://africa-knowledge-platform.ec.europa.eu` | All Africa | Shapefiles detailing geographical locations and attributes of geothermal wells across Africa |
| **BGS Well Data (GG HF TC)** | `https://africa-knowledge-platform.ec.europa.eu` | All Africa | Geothermal well data from British Geological Survey |

### 4.2 Modelling Requirements

- **Resource temperature-depth mapping**: Use the Geothermal Atlas temperature models at 1–4 km depth to identify high-enthalpy resources (>150°C) for power generation and low-enthalpy resources (<150°C) for direct use.
- **Technology representation**:
  - **Flash steam plants** for high-enthalpy resources (>180°C).
  - **Binary cycle plants** for medium-enthalpy resources (100–180°C).
  - **Enhanced Geothermal Systems (EGS)** for regions with hot dry rock but limited permeability.
- **Country potential**: High potential in Kenya (Olkaria, Menengai), Ethiopia (Corbetti, Aluto), Tanzania, Rwanda, Uganda, Djibouti, and Comoros. Kenya currently leads Africa with approximately 950 MW installed geothermal capacity.
- **Drilling cost curves**: Capital costs per MW as a function of resource depth and temperature, with country-specific drilling cost adjustments.
- **Dispatchability**: Geothermal as baseload, with ramp rate constraints and minimum stable levels.

---

## 5. Hydropower

### 5.1 Resource Data

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **African Hydropower Atlas (Sterl et al.)** | `https://www.hydroshare.org/resource/19eab83ae424be3804ee154ed98aea8/` | All Africa | Seasonal hydropower generation profiles for nearly all existing and several hundred future hydropower plants. Includes reservoir plant upstream and run-of-river cascaded configurations |
| **AfREP-Hydro (IRENA)** | `https://www.irena.org/Publications/2021/Dec/African-Renewable-Electricity-Profiles-Hydropower` | All Africa | Covers all existing and several hundred committed, planned, and potential future hydropower plants. Provides model-ready seasonal availability profiles in normal, dry, and wet years |
| **AfriDischarge v1** | `https://doi.org/10.5066/P14H6TFY` | Continental Africa | High-resolution (1km) monthly and annual discharge estimates for 2001–2021 across 64,000+ river segments |
| **FAO Rivers of Africa** | `https://data.apps.fao.org/map/catalog/srv/api/records/b891ca64-4cd4-4efd-a7ca-b386e98d52e8` | Continental Africa | River network derived from HydroSHEDS, with annotated attributes |
| **FAO Hydrological Basins** | `https://data.apps.fao.org/catalog//iso/7707086d-af3c-41cc-8aa5-323d8609b2d1` | Continental Africa | Major hydrological basins and sub-basins delineated from HydroSHEDS and Hydro1K |

### 5.2 Modelling Requirements

- **Plant categories**: Run-of-river, reservoir (with seasonal storage), and pumped-storage hydro (PSH).
- **Cascade modelling**: Explicit modelling of cascaded hydro systems on the Nile, Congo, Niger, Zambezi, and Orange river basins, with upstream/downstream dependencies.
- **Reservoir dynamics**: Multi-year reservoir operation with inflow time series, spillage, and minimum environmental flows.
- **Pumped-storage hydro**: Round-trip efficiency (70–80%), charge/discharge rate limits, and reservoir capacity constraints.
- **Small hydro**: Plants <10 MW, using MSR data and DRE Atlas settlement-level demand for mini-grid integration.
- **Climate uncertainty**: CMIP6-based inflow scenarios for drought and flood years, with reservoir operation rules that adapt to changing hydrology.

---

## 6. Biomass and Bioenergy

### 6.1 Resource Data

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **JRC Bioenergy Atlas** | `https://data.jrc.ec.europa.eu/` | Europe and Africa | Geo-spatial analysis of economic potential of biomass feedstock for bioenergy production |
| **COMPETE Interactive Maps** | `https://www.compete-bioafrica.net` | 8 African countries | Biomass potentials for energy and non-energy uses, aggregating multiple high-quality sources to identify suitable areas |
| **FAO WISDOM** | `https://www.fao.org/` | East Africa, Sub-Saharan Africa | Woodfuel integrated supply/demand overview mapping, with geodatabase at 5 arc-minute (9×9 km) resolution |
| **GEO Bioenergy Atlas for Africa** | `https://old.earthobservations.org/` | All Africa | Combines layers of land-use, hydrology, and biomass data for bioenergy planning |
| **Nigeria/Kenya/South Africa Biomass Maps** | `https://zenodo.org/records/` (search "Geospatial Visualisations of Biomass Feedstock") | Nigeria, Kenya, South Africa | 21 high-resolution geospatial maps showing agricultural residues, OFMSW, and used cooking oil feedstock distribution |

### 6.2 Modelling Requirements

- **Feedstock categories**:
  - **Solid biomass**: Agricultural residues (maize stover, rice husk, sugarcane bagasse), forestry residues, and energy crops.
  - **Biogas**: Animal manure, municipal solid waste (organic fraction), and industrial wastewater.
  - **Liquid biofuels**: Used cooking oil, vegetable oils, and lignocellulosic ethanol.
- **Conversion technologies**:
  - **Combustion**: Biomass-fired power plants (direct combustion, co-firing with coal).
  - **Gasification**: Biomass gasification for electricity and syngas.
  - **Anaerobic digestion**: Biogas for electricity, heat, and biomethane injection.
  - **Pyrolysis**: Bio-oil and biochar production.
- **Sustainability constraints**: Exclusion of areas with high biodiversity value, primary forests, and food-security-sensitive land. Maximum biomass extraction rates by country, based on FAO WISDOM and JRC analyses.
- **Cost curves**: Feedstock collection, transport, and processing costs by country, with distance-decay functions for collection radius.

---

## 7. Marine Energy

### 7.1 Resource Data

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **Global Wave Statistics** | `https://www.oceanenergy-europe.eu/` | Global | Wave height and period data for wave energy assessment |
| **NOAA WaveWatch III** | `https://polar.ncep.noaa.gov/waves/` | Global | Hindcast wave data for validation |
| **Tidal Stream Data** | `https://www.marineregions.org/` | Global | Tidal speed and range data |
| **Atlantic Council Marine Energy** | `https://www.atlanticcouncil.org/` | Atlantic Africa | Wave and tidal potential for South Africa, Namibia, Senegal, Cabo Verde, and Morocco |
| **Western Indian Ocean Ocean Energy** | `https://www.sciencedirect.com/` | WIO region | High wave power (≥25 kW/m) in Southern Mozambique, Southern Madagascar, Réunion, Mauritius, and Eastern Madagascar |
| **Gulf of Guinea Marine Energy** | `https://link-proxy.springer.com/` | Gulf of Guinea | Wave, tidal, and floating solar potential assessment for Cameroon and Gulf of Guinea countries |

### 7.2 Modelling Requirements

- **Technology representation**:
  - **Wave energy**: Point absorbers, oscillating water columns, and overtopping devices.
  - **Tidal energy**: Tidal stream turbines (horizontal axis) and tidal range (barrage/lagoon).
  - **Ocean current energy**: Turbines in the Agulhas, Somali, and Canary currents.
  - **Ocean thermal energy conversion (OTEC)**: For equatorial waters with temperature differentials >20°C.
- **Country potential**: High wave potential in South Africa, Namibia, Senegal, Cabo Verde, Morocco, Mozambique, Madagascar, Mauritius, and Réunion. High tidal potential in the Wouri estuary (Cameroon) and Tangier (Morocco).
- **Cost curves**: Capital and O&M costs per MW for each technology, with learning rates reflecting global deployment.
- **Grid connection**: Submarine cable costs and losses, with distance-to-shore penalties.

---

## 8. Green Hydrogen from Renewables

### 8.1 Resource Data

| Data Source | Direct Data Link | Coverage | Description |
|---|---|---|---|
| **IEA Global Hydrogen Review – Africa** | `https://www.iea.org/reports/global-hydrogen-review-2026` | Africa | Hydrogen use reached 3.1 Mt in 2024; 6 kt low-emissions hydrogen produced. Concentrated in Egypt, Algeria, Nigeria, South Africa, Libya, and Equatorial Guinea |
| **Green Hydrogen Cost-Potential (SSA)** | `https://www.sciencedirect.com/science/article/pii/S0360319925006789` | Sub-Saharan Africa | Hydrogen costs starting at 1.6 EUR/kg in Mauritania, ~259 TWh/a under 2 EUR/kg in 2050. Aggregate potentials ~200,000 TWh/a |
| **African Hydrogen LCOH Dataset** | `https://github.com/tarekhemdan/Hydrogen_AI` | 54 African countries | Harmonized dataset of 54 scenarios with LCOH (EUR/kg) as target variable and 14 predictors |
| **HyAfrica Project Data** | `https://zenodo.org/communities/hyafrica` | Morocco, Mozambique, South Africa, Togo | Natural hydrogen exploration results, soil gas measurements, and lab analyses |

### 8.2 Modelling Requirements

- **Electrolysis technologies**: PEM, alkaline, and solid oxide electrolysis, with country-specific capacity factors and costs.
- **Storage**: Salt caverns, depleted gas reservoirs, and above-ground storage, with geological suitability assessment.
- **Transport**: Pipeline networks, liquefaction, ammonia synthesis, and shipping routes.
- **Export scenarios**: Hydrogen and ammonia export to Europe, Asia, and intra-African markets, with port infrastructure and shipping costs.
- **Sector coupling**: Hydrogen for industry (steel, cement, chemicals), transport (fuel cell vehicles, shipping), and power generation (fuel cells, hydrogen turbines).

---

## 9. Renewable Integration Modelling Requirements

### 9.1 Variable Renewable Energy (VRE) Integration

- **Hourly profiles**: For solar PV, onshore wind, and offshore wind, using `atlite` with ERA5 data.
- **Sub-hourly resolution**: Optional 15-minute and 5-minute resolution for operational studies, capturing wind ramps and solar transients.
- **Curtailment modelling**: Explicit representation of curtailment due to transmission constraints, minimum inertia requirements, and oversupply conditions.
- **Inertia and stability**: Simplified inertia constraints for systems with high VRE penetration, with synchronous condenser and grid-forming inverter options.

### 9.2 Dispatchable Renewables

- **Geothermal**: Baseload with ramp rate constraints (5–10% per minute) and minimum stable levels.
- **Hydropower**: Flexible dispatch with reservoir constraints and cascade dependencies.
- **Biomass**: Dispatchable with fuel supply constraints and minimum stable levels.
- **CSP with storage**: Dispatchable with thermal storage and solar field constraints.

### 9.3 Renewable Curtailment and Storage

- **Battery storage**: Li-ion, flow, and sodium-sulphur, with 2–8 hour duration and country-specific costs.
- **Pumped-storage hydro**: Long-duration storage with 6–20 hour discharge.
- **Green hydrogen storage**: Seasonal storage with salt caverns and depleted reservoirs.
- **Thermal storage**: Molten salt for CSP, and hot water for industrial heat.

---

## 10. Data Integration into PyPSA-X

| Renewable Technology | Primary Data Source(s) | PyPSA-Earth Integration | Additional Sources Required |
|---|---|---|---|
| **Solar PV** | GSA, ERA5, MSRs | ✓ Built-in | PVGIS, SARAH-2 |
| **CSP** | GSA (DNI), SolarPACES | Partial | NREL cost data |
| **Onshore Wind** | GWA, ERA5, MSRs | ✓ Built-in | World Bank GWA |
| **Offshore Wind** | GWA, GEBCO, EEZ | Partial | Marine Regions |
| **Geothermal** | Geothermal Atlas for Africa, EARTH | ✗ | CRM-geothermal, BGS wells |
| **Hydropower** | African Hydropower Atlas, AfREP-Hydro | ✓ Built-in | AfriDischarge, FAO |
| **Biomass** | JRC Bioenergy Atlas, COMPETE, FAO WISDOM | Partial | GEO Bioenergy Atlas |
| **Marine Energy** | Global Wave Statistics, NOAA WaveWatch III | ✗ | Atlantic Council, WIO studies |
| **Green Hydrogen** | IEA, SSA cost-potential, Hydrogen_AI | Partial | HyAfrica, IRENA |

---

## 11. Summary: Renewable Capability Targets

| Technology | Global Best | PyPSA-X Target | Target Date |
|---|---|---|---|
| **Solar PV** | 1 km resolution, hourly | 250 m resolution, sub-hourly | 2028 |
| **CSP** | Site-specific | Country-level with thermal storage | 2027 |
| **Onshore Wind** | 1 km resolution, hourly | 100 m resolution, sub-hourly | 2028 |
| **Offshore Wind** | Site-specific | Country-level with floating platforms | 2028 |
| **Geothermal** | Country-level | 1 km resolution with EGS potential | 2028 |
| **Hydropower** | Plant-level, seasonal | Plant-level, daily with cascade modelling | 2027 |
| **Biomass** | Country-level | 1 km resolution with sustainability constraints | 2028 |
| **Marine Energy** | Site-specific | Country-level with wave, tidal, OTEC | 2029 |
| **Green Hydrogen** | Country-level | Site-level with export infrastructure | 2028 |

---

## 12. Conclusion

This specification defines the full incorporation of all renewable energy technologies into PyPSA-X Pan-African. By leveraging the best available African resource data—from the Geothermal Atlas for Africa to the Global Wind Atlas, from the African Hydropower Atlas to the all-Africa supply regions dataset—the platform will model solar, wind, geothermal, hydropower, biomass, marine, and hydrogen technologies with world-class spatial and temporal granularity. This ensures that PyPSA-X Pan-African is not merely a solar-and-wind model, but a comprehensive renewable energy system modelling platform capable of optimising Africa's entire clean energy portfolio.