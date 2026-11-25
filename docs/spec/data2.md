# Alea: Comprehensive Data Source Specification with Verified Links

## A Methodical Inventory of All Required Data Inputs for Continental Energy System Modelling

---

## 1. Introduction and Methodology

This specification catalogues every data source required to build, calibrate, and operate Alea across all 55 African Union member states, five regional power pools, and the continental interconnection. Each entry includes the source name, custodian, coverage, verified access link, and a description of the data content and known limitations.

---

## 2. Grid Topology and Transmission Network Data

### 2.1 OpenStreetMap (OSM)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | OpenStreetMap Foundation |
| **Coverage** | Global, including all 55 AU member states |
| **Verified Link** | https://download.geofabrik.de/africa.html |
| **Update Frequency** | Daily |

**Description**: Geofabrik provides free daily OSM extracts for every continent, country, and many sub-national regions. Africa continent extract is available as `.osm.pbf` (7.4 GB). The data includes power lines, substations, generators, and cables. PyPSA-Earth integrates OSM extraction automatically.

**Limitations**: Data completeness varies significantly by country. OSM is rich in South Africa, Kenya, and North Africa, but sparse in CAPP member states and fragile states.

### 2.2 World Bank Africa Electricity Transmission and Distribution Grid Map

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / International Finance Corporation |
| **Coverage** | All continental African countries and Madagascar, plus MENA |
| **Verified Link** | https://datacatalog.worldbank.org/search/dataset/0040787 |
| **Update Frequency** | Last major update 2017; some datasets updated October 2025 |

**Description**: This is the most complete and up-to-date open map of Africa's electricity grid network. Includes planned and existing grid lines for all continental African countries and Madagascar, as well as the Middle East region. Total length 4,204 km across 1,818 inputs, with voltage from sub-kV to 700 kV EHV.

**Limitations**: Some data from AICD and World Bank project archives may be very out of date. Lines digitised from PDF maps should serve as an indication of extent rather than precise location.

### 2.3 AfDB Africa Power Plants Map

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank / KTH Division of Energy Systems Analysis |
| **Coverage** | Continental Africa (country-level datasets available) |
| **Verified Link** | https://energydata.info/dataset/nigeria-power-plants-2015 |
| **Update Frequency** | 2015 (Nigeria), 2017 (Tanzania) |

**Description**: Contains power plants provided by African Development Bank and OpenStreetMap. Data for power plants with total installed generating capacity >10 MW from the Platts World Electric Power Plants Database (WEPP 2006). Georeferenced records for Nigeria, Tanzania, and other countries.

**Limitations**: Country-level datasets; not all AU member states have dedicated records.

---

## 3. Power Plant and Generation Asset Data

### 3.1 powerplantmatching (Consolidated Database)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | PyPSA-Earth / Open Source |
| **Coverage** | Global, with demonstrated application in Africa |
| **Verified Link** | https://github.com/PyPSA/powerplantmatching |
| **Update Frequency** | Continuous (open-source development) |

**Description**: The powerplantmatching tool has been successfully employed in Europe and in Africa for fetching multiple datasets and inferring the most likely ground truth. Input sources include OpenStreetMap2022, Global Energy Monitor, IRENA, GEO, GPD, and GEM. The tool cleans, aggregates, filters, and matches datasets pairwise to identify duplicates based on name, location, fuel, and technology.

**Limitations**: Relevance to Africa was acceptable before GEM integration; GEM has improved performance. Fuel-fired generators (coal, gas) included in addition to renewables.

### 3.2 RePP Africa (Renewable Power Plant Database for Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Peters et al. (2023), published in Scientific Data |
| **Coverage** | All Africa |
| **Verified Link** | https://www.nature.com/articles/s41597-023-01968-9 |
| **Update Frequency** | Published 2023 |

**Description**: The Renewable Power Plant database for Africa (RePP Africa) encompasses 1,074 hydro, 1,128 solar, and 276 wind power plant records. For each power plant, metadata includes location, capacity, technology, status (existing/proposed), and installation date. The final product consists of the Hydropower Plant Database (HPPD), Solar Power Plant Database (SPPD), and Wind Power Plant Database (WPPD).

**Limitations**: Database is static; new plants commissioned after 2023 may not be included.

### 3.3 Global Energy Monitor – Africa Energy Tracker

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Global Energy Monitor |
| **Coverage** | North and sub-Saharan Africa |
| **Verified Link** | https://globalenergymonitor.org/projects/africa-energy-tracker/ |
| **Update Frequency** | Regular updates (March 2026 version available) |

**Description**: Comprehensive dataset mapping energy infrastructure across North and sub-Saharan Africa, covering oil and gas, coal, and renewables. All data is available freely under a Creative Commons Attribution 4.0 International License. The tracker uses a two-tier system to organise information.

**Limitations**: Tracks projects in non-self-governing and overseas territories, including Western Sahara and Réunion, separately.

### 3.4 ECOWREX Power Plants Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ECOWAS Regional Centre for Renewable Energy and Energy Efficiency (ECREEE) |
| **Coverage** | West Africa (ECOWAS member states) |
| **Verified Link** | https://www.ecowrex.org/power-plants |
| **Update Frequency** | Regular updates |

**Description**: Power plants by country with capacity, technology, and status (operational, planned). Examples include Niger Malbaza solar (7.00 MW PV Solar Operational), Nigeria Kwa Falls (6.40 MW Small Hydro Planned), and Nigeria Itobe Coal (1,200.00 MW Planned). The platform aims to address knowledge and information barriers in the ECOWAS Region.

**Limitations**: Coverage limited to ECOWAS member states.

### 3.5 African Hydropower Atlas (Sterl et al., 2021)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Sterl et al., published in Open Research Europe |
| **Coverage** | All Africa |
| **Verified Link** | https://zenodo.org/records/4632249 |
| **Update Frequency** | Version 2, 2021 |

**Description**: A spatiotemporal atlas of hydropower in Africa for energy modelling purposes, containing seasonal hydropower generation profiles for nearly all existing and several hundred future hydropower plants on the African continent. The atlas builds on continental-scale hydrological modelling in combination with detailed technical databases of hydropower plant characteristics.

**Limitations**: Profiles are seasonal averages; hourly resolution requires downscaling.

### 3.6 AfREP-Hydro (IRENA)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Renewable Energy Agency (IRENA) |
| **Coverage** | All Africa |
| **Verified Link** | https://www.irena.org/publications/2021/Dec/African-Renewable-Electricity-Profiles-for-Energy-Modelling-Database-Hydropower |
| **Update Frequency** | Published December 2021 |

**Description**: IRENA's new spatiotemporal data atlas, AfREP-Hydro (African Renewable Electricity Profiles for Energy Modelling – Hydropower), covers all existing and several hundred committed, planned, and potential future hydropower plants across the African continent. The database can be visualized and downloaded from IRENA Global Atlas and the source code accessed from Zenodo. Hydro profiles are available via HydroShare (version 2.3).

**Limitations**: Static release; new projects after 2021 not included.

### 3.7 Freshwater Demand for Electricity in Africa Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CGIAR Initiative on Foresight / IWMI |
| **Coverage** | All Africa |
| **Verified Link** | https://foresight.cgiar.org/freshwater-demand-and-electricity-in-africa/ |
| **Update Frequency** | Published 2024–2025 |

**Description**: The study includes 2,534 power plants, categorizing them by fuel type, operation cycle, infrastructure, cooling system, and local climate. The database can be used at any spatial level, with results on national, subnational, and river basin level. The paper is available from Environmental Science (DOI: 10.1039/D4EW00246F).

**Limitations**: Based on 2020 data; plant-level cooling systems may change.

---

## 4. Renewable Resource Data

### 4.1 ERA5 Reanalysis

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ECMWF / Copernicus Climate Change Service (C3S) |
| **Coverage** | Global, including all Africa |
| **Verified Link** | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels |
| **Update Frequency** | Continuous (1950 to present) |

**Description**: ERA5 is the fifth generation ECMWF reanalysis for the global climate and weather for the past 8 decades. Provides hourly data on wind speed, solar irradiance, temperature, and other meteorological variables. Downloadable via the Climate Data Store (web or CDS-API). DOI: 10.24381/cds.adbb2d47.

**Limitations**: ~30 km spatial resolution globally; requires downscaling for site-specific analysis.

### 4.2 Global Wind Atlas 3.0

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Technical University of Denmark (DTU Wind Energy) / World Bank Group |
| **Coverage** | Global |
| **Verified Link** | https://globalwindatlas.info/ |
| **Update Frequency** | Version 3.0 (current) |

**Description**: A free, web-based application developed to help policymakers, planners, and investors identify high-wind areas for wind power generation. The current version (GWA 3.0) is the product of a partnership between DTU Wind Energy and the World Bank Group. Wind resources have been calculated even more accurately using the best available methods and input data.

**Limitations**: Provides long-term averages, not hourly time series.

### 4.3 Global Solar Atlas

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / ESMAP / Solargis |
| **Coverage** | Global |
| **Verified Link** | https://globalsolaratlas.info/ |
| **Update Frequency** | Continuous updates |

**Description**: Provides long-term averages of solar resource (global horizontal irradiation, direct normal irradiation) and PV power potential. The GIS data stems from the Global Solar Atlas and is available as GEOTIF, AAIGRID, or KML/KMZ file for GoogleEarth. Developed to support the scale-up of solar power in client countries.

**Limitations**: Provides long-term averages, not hourly time series.

### 4.4 PVGIS (Photovoltaic Geographical Information System)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | European Commission Joint Research Centre |
| **Coverage** | Global (except North and South Poles) |
| **Verified Link** | https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en |
| **Update Frequency** | PVGIS 5.3 (current) |

**Description**: Provides information on solar radiation and photovoltaic system performance for any location in the world. The underlying solar dataset offers satellite and reanalysis solar irradiation data covering from 2014 up to 2024. Three different solar radiation databases (all based on satellite data) are available: PVGIS-SARAH2, PVGIS-NSRDB, and PVGIS-ERA5.

**Limitations**: Sea areas not covered for some datasets.

### 4.5 SARAH-2 Satellite Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | EUMETSAT CM SAF |
| **Coverage** | Africa, Europe, and parts of Atlantic |
| **Verified Link** | https://wui.cmsaf.eu/safira/action/viewProduktSearch |
| **Update Frequency** | SARAH-2.1 covers 1983–2017 |

**Description**: The second edition of the Surface Solar Radiation Data Set - Heliosat (SARAH-2) is a satellite-based climate data record of the solar surface irradiance, surface direct irradiance, and sunshine duration. The data record provides surface solar radiation data for the time period from 1983 to 2017, with 30-minute instantaneous data available for SARAH-2. DOI: 10.5676/EUM_SAF_CM/SARAH/V002_01.

**Limitations**: Ends 2017; PVGIS-SARAH2 extends coverage.

### 4.6 SWERA (Solar and Wind Energy Resource Assessment)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | UNEP / NREL |
| **Coverage** | 13 developing countries including African nations |
| **Verified Link** | https://openei.org/wiki/SWERA |
| **Update Frequency** | 2001–2007 (historical) |

**Description**: The SWERA Programme provides easy access to credible renewable energy data to stimulate investment in, and development of, renewable energy technologies. Developed detailed assessments of wind and solar energy potential in 13 developing countries. The Renewable Energy Resource Explorer (RREX) is a web-based map viewer displaying SWERA data.

**Limitations**: Historical programme; data may not reflect current conditions.

---

## 5. Demand and Socioeconomic Data

### 5.1 AfDB African Regional Energy Statistics (2014)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank Group |
| **Coverage** | All Africa |
| **Verified Link** | https://data.humdata.org/dataset/african-regional-energy-statistics-2014 |
| **Update Frequency** | 2014 edition (inactive) |

**Description**: Contains 51,051 rows from African Development Bank Group covering production, consumption, imports, and exports of energy resources for African countries. Source: HDX. License: CC-BY-4.0.

**Limitations**: Historical baseline; not updated.

### 5.2 AFREC African Energy Balance and Indicators

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Energy Commission (AFREC), African Union |
| **Coverage** | All 55 AU member states |
| **Verified Link** | https://au-afrec.org/publications |
| **Update Frequency** | Annual; 2025 edition available |

**Description**: The Africa Energy Balance and Indicators is AFREC's annual energy publication featuring interpretation of data and statistics of energy performance in the member states, region, and continent. The 2021 edition includes a detailed energy balance for thirteen (13) African Union member states. Key Africa Energy Statistics (KAES) 2025 edition also available.

**Limitations**: Detailed energy balance available for subset of member states.

### 5.3 WorldPop Population Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WorldPop, University of Southampton |
| **Coverage** | Global, including all Africa |
| **Verified Link** | https://hub.worldpop.org/ |
| **Update Frequency** | 2025 release for Sub-Saharan Africa |

**Description**: Gridded population estimates (spatial resolution of 3 arcseconds, approximately 100-metre grid cells) for 52 countries in sub-Saharan Africa. The WorldPop population mapping program is constructed based on academically peer-reviewed methodologies and provides spatial demographic datasets for 100+ government agencies. Africa Continental Population Datasets (2000–2020) also available at 1km resolution.

**Limitations**: Spatial resolution varies by country.

### 5.4 Global Electrification Platform (GEP) 3.0

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / ESMAP |
| **Coverage** | 58 countries globally, including all of Sub-Saharan Africa |
| **Verified Link** | https://gep-user-guide.readthedocs.io/ |
| **Update Frequency** | GEP 3.0 released August 2024 |

**Description**: Aims to standardize and simplify the use of geospatial tools to create least-cost electrification plans. The latest version, GEP 3.0, includes a shadow price of carbon in the calculation of each technology solution. Provides a high-level overview of the technology mix - grid, mini-grid and standalone solar - and investment required to achieve universal access by 2030 for each country. The GEP is one of the few energy optimization modelling tools that is open source, publicly available, and freely replicable.

**Limitations**: Scenarios represent high-level pathways, not project-level detail.

### 5.5 Distributed Renewable Energy (DRE) Atlas

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ESMAP / World Bank |
| **Coverage** | 58 countries including Sub-Saharan Africa, Asia-Pacific, Latin America |
| **Verified Link** | https://dre.energydata.info |
| **Update Frequency** | Launched June 2025 |

**Description**: A publicly accessible, web-based, interactive platform offering comprehensive data on settlements in 58 countries. Explore over 60 high-resolution indicators per settlement. Designed for easy navigation, providing detailed insights into communities suitable for the deployment of mini grid and off-grid solar systems. Supports initiatives like the African Development Bank's Mission 300.

**Limitations**: Settlement-level data; not all countries covered.

### 5.6 GDP Raster Data (DRYAD)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | DRYAD / Kummu et al. |
| **Coverage** | Global |
| **Verified Link** | https://doi.org/10.5061/DRYAD.DK110 |
| **Update Frequency** | 1990–2015 (Version 2) |

**Description**: Gridded global datasets for Gross Domestic Product and Human Development Index over 1990–2015. Spatial resolution is 1km, with time range 1990–2015. License: CC0.

**Limitations**: Ends 2015; extrapolation required for recent years.

### 5.7 IEA World Energy Outlook – Africa Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Africa region (North Africa, West Africa, Central Africa, Eastern Africa, Southern Africa) |
| **Verified Link** | https://www.iea.org/reports/world-energy-outlook-2025 |
| **Update Frequency** | Annual |

**Description**: Historical and projected electricity demand, capacity, and generation by region. Africa's population is growing at twice the global rate, driving energy demand that's expected to surge by more than 50% by 2040. The IEA World Energy Outlook 2025 projects electrification rate reaching almost 70% by 2030 in the Stated Energy Policies Scenario (STEPS), up from 59% today.

**Limitations**: Regional aggregation; country-level detail available in WEO data services.

### 5.8 AfDB African Economic Outlook

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank |
| **Coverage** | All Africa |
| **Verified Link** | https://www.afdb.org/en/knowledge/publications/african-economic-outlook |
| **Update Frequency** | Annual |

**Description**: Africa's economies are projected to grow at 4.2 percent in 2026, moderating slightly from 4.4 percent in 2025, before rebounding to 4.4 percent in 2027. Provides GDP growth, population, and economic indicators by country. The 2026 AEO was prepared against a backdrop of geopolitical fragmentation, trade tensions, regional conflicts, and declining international financial flows.

**Limitations**: Macroeconomic projections; energy-specific data requires supplementary sources.

### 5.9 Transport Starter Data Kit

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in Data in Brief, 2024) |
| **Coverage** | Selected countries in Africa, Asia, and South America |
| **Verified Link** | https://zenodo.org/records/10068000 |
| **Update Frequency** | 2024 |

**Description**: A one-stop-shop for transport modelling-related data. Contains historical annual data (1990–2021) on passenger and freight activity, energy intensities, load factors, and vehicle stock, segregated by mode and fuel where available. Available via ckan.transport-data.org.

**Limitations**: Selected countries; not all AU member states covered.

### 5.10 AFREC Industry Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All Africa |
| **Verified Link** | https://au-afrec.org/publications |
| **Update Frequency** | Annual (2025 Energy Balance available) |

**Description**: Total final consumption increased across all sectors, particularly in transport, households, and industry. Consumption of oil in industry shows detailed annual figures. AFREC has started creating the energy efficiency database for industry. In the latest AFREC data covering 2018, approximately 30 countries reported data on energy use in the commercial sector.

**Limitations**: Industry data collection is ongoing; not all countries report.

---

## 6. Fuel Price and Technology Cost Data

### 6.1 IRENA Renewable Cost Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Renewable Energy Agency |
| **Coverage** | Global, with country-specific data for Africa |
| **Verified Link** | https://www.irena.org/Data/View-data-by-topic/Costs |
| **Update Frequency** | Annual (2025 edition available) |

**Description**: Contains approximately 20,000 utility-scale renewable power generation projects and 13,000 PPA and tender/auction results that provide new insights into trends in the costs and performance of renewables. Includes information on installed costs, capacity factors, and LCOEs for over 15,000 utility-scale renewable power generation projects. IRENA has established local gaseous hydrogen costs for the African continent, starting at 1.1 USD/kgH₂ in 2050.

**Limitations**: Project-level data; not all African countries represented.

### 6.2 IEA Cost Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Global |
| **Verified Link** | https://www.iea.org/data-and-statistics/data-tools/levelised-cost-of-electricity-calculator |
| **Update Frequency** | Annual |

**Description**: IEA Levelised Cost of Electricity Calculator provides technology costs, fuel prices, and investment data. Fuel price assumptions (2021 USD/GJ) for Europe and Africa, 2021–2050 available. The IEA also provides the Government Energy Spending Tracker and other cost data tools.

**Limitations**: Regional aggregation for some datasets.

### 6.3 Global Petrol Prices

| Attribute | Detail |
|-----------|--------|
| **Custodian** | GlobalPetrolPrices.com |
| **Coverage** | 41 African countries |
| **Verified Link** | https://www.globalpetrolprices.com/ |
| **Update Frequency** | Weekly |

**Description**: Gasoline prices spanning eight years (2018–2025); some countries have incomplete data due to reporting gaps or political instability. As of April 2026, Malawi recorded the highest gasoline prices in Africa ($3.84/L), while Libya had the lowest ($0.024/L). South Africa gasoline stood at $1.397/L, diesel at $1.743/L.

**Limitations**: Some countries have incomplete data.

### 6.4 UNDP Fuel Retail Price Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | UNDP |
| **Coverage** | Major African countries |
| **Verified Link** | https://www.undp.org/ |
| **Update Frequency** | Periodic |

**Description**: Fuel retail prices for February–March 2026 period, covering Egypt, Morocco, and others. Provides comparative data on fuel price changes across African nations.

**Limitations**: Not all AU member states covered.

### 6.5 AFREC Africa Energy Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All Africa |
| **Verified Link** | https://au-afrec.org/publications |
| **Update Frequency** | Annual (2019 Edition available) |

**Description**: The AFREC Africa Energy Database is a comprehensive collection of statistical data based on production, consumption, imports, and exports of energy resources of the African countries. Largely based on energy data collected by AFREC supplemented with secondary data collected by international database providers mainly IEA for missing or unsupplied data.

**Limitations**: Relies on IEA data for gaps.

### 6.6 IRENA, IEA, EUROSTAT Joint Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | IRENA / IEA / EUROSTAT |
| **Coverage** | Global with Africa coverage |
| **Verified Link** | https://ec.europa.eu/eurostat |
| **Update Frequency** | Historical data series 2010–2040 |

**Description**: Final consumption of fuels in transport (diesel) with historical data series 2010–2040, measured in TWh. Final consumption of energy used in transport for transformation into final energy.

**Limitations**: Transport-focused; other sectors require supplementary sources.

### 6.7 Fossil Fuel Field Approximation (PyPSA-Earth)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | PyPSA-Earth (derived from global datasets) |
| **Coverage** | Global |
| **Verified Link** | https://github.com/pypsa-meets-earth/pypsa-earth |
| **Update Frequency** | Integrated into PyPSA-Earth workflow |

**Description**: For the sake of simplicity and given the focus of PyPSA-Earth to model decarbonization scenarios, the modelling of the exact location of existing fossil-fuel fields is approximated. Currently, no detailed input data are needed to specify the location of fossil-fuel fields.

**Limitations**: Approximated representation; not suitable for detailed fuel supply chain analysis.

---

## 7. Policy, Regulatory, and Institutional Data

### 7.1 AUDA-NEPAD Mwanga CMP Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Verified Link** | https://cmpmwanga.nepad.org/ |
| **Update Frequency** | Continuous updates |

**Description**: Continental Power System Master Plan database containing historical and projected data needed to model future demand for long-term energy planning by power pools. Includes governance framework for regular updates, harmonisation with existing AU databases (AID, AEIS, AEP), and power pool information systems. Implemented by AUDA-NEPAD, supported by the European Union through the Continental Energy Programme in Africa (CEPA).

**Limitations**: Some content may require registration.

### 7.2 African Energy Information System (AEIS)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All 55 AU member states |
| **Verified Link** | https://www.au-afrec.org/aeis |
| **Update Frequency** | Revamped 2020; continuous updates |

**Description**: The AEIS is a decision-making tool which is comprised of a continental energy database and other energy information and data visualisation tools. Created by AFREC in 2012 to coordinate Africa's energy data collection, validation and dissemination at national, regional and continental level. The system allows collection, processing and validation of African countries' energy statistics through harmonized questionnaires.

**Limitations**: Currently going through a revamp.

### 7.3 African Infrastructure Database (AID)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | 55 African Union Member States |
| **Verified Link** | https://aid.nepad.org/ |
| **Update Frequency** | Real-time data |

**Description**: Gateway to infrastructure projects in Africa. Search, explore, and analyse thousands of infrastructure projects across the continent. Currently tracks 1,842 total projects across 7 sectors and 55 African Union Member States. Developed by AUDA-NEPAD in 2012, AID is a leading platform dedicated to tracking and analyzing infrastructure projects across Africa.

**Limitations**: Project-level data; not all projects have complete metadata.

### 7.4 Africa Energy Portal (AEP)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank |
| **Coverage** | All 54 African countries |
| **Verified Link** | https://africa-energy-portal.org/ |
| **Update Frequency** | Regular updates (data spanning 2000–2024) |

**Description**: A one-stop-shop for energy sector news, insights, data and more. Launched in November 2018, the AEP provides country-level electricity sector profiles, market intelligence, policy analysis, research publications, and sector news. Hosted by the African Development Bank, the portal is an interactive platform for knowledge-sharing amongst Africa's energy sector stakeholders.

**Limitations**: Primarily qualitative and sector-level data; quantitative time-series requires other sources.

### 7.5 PIDA (Programme for Infrastructure Development in Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union Commission / AUDA-NEPAD / AfDB |
| **Coverage** | Continental Africa |
| **Verified Link** | https://au-pida.org/ |
| **Update Frequency** | Continuous |

**Description**: Real-time insights into PIDA infrastructure investments across Africa. Includes priority infrastructure projects including cross-border transmission interconnectors, generation projects, storage, and off-grid systems. Through PIDA, Africa has already delivered 16,000 km of roads, 4,000 km of railways, and energy access for 30 million people.

**Limitations**: Project pipeline data; not all projects have financial close.

### 7.6 National Integrated Resource Plans (IRPs)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Individual national governments and regulators |
| **Coverage** | Country-specific (e.g., South Africa, Nigeria) |
| **Verified Link** | https://www.dmre.gov.za/ (South Africa example) |
| **Update Frequency** | Periodic (e.g., South Africa IRP 2025) |

**Description**: Planned capacity additions, demand forecasts, and policy targets. South Africa's IRP 2025 was approved by Cabinet on 15 October 2025. Under the IRP, South Africa will add 105,000 megawatts of new capacity by 2039, 2.5 times Eskom's current output, to secure long-term energy stability and drive industrial recovery. Nigeria's NIRP 2024 provides a comprehensive plan for modernising electricity infrastructure.

**Limitations**: Varies by country; not all AU member states have published IRPs.

### 7.7 EU CBAM Data for Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | European Commission / Zenodo |
| **Coverage** | African countries |
| **Verified Link** | https://zenodo.org/records/14589452 |
| **Update Frequency** | 2026 (latest) |

**Description**: Data used in chapters on "The EU Carbon Border Adjustment Mechanism as an Incentive for Carbon Pricing in African Countries". The EU CBAM, fully operational since January 2026, requires importers to purchase certificates covering the embedded emissions of goods in six carbon-intensive sectors. The EU currently absorbs roughly one-third of Africa's exports in sectors covered by the CBAM, including iron and steel, aluminium, cement, fertilisers, hydrogen and electricity.

**Limitations**: Trade exposure indices; product-level detail available in underlying data.

### 7.8 IMF Effective Carbon Prices

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Monetary Fund |
| **Coverage** | African countries |
| **Verified Link** | https://www.imf.org/en/Publications |
| **Update Frequency** | Periodic |

**Description**: Effective carbon prices for 2030 (in USD per tonne CO₂) by fuel type (diesel, gasoline, natural gas, coal, ETS). Provides carbon price benchmarking for policy scenario development.

**Limitations**: Projections; actual prices may differ.

### 7.9 Carbon Pricing Mechanisms Database (Princeton)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Princeton University |
| **Coverage** | Global, including Africa |
| **Verified Link** | https://dss.princeton.edu/catalog/ |
| **Update Frequency** | Periodic |

**Description**: Sectoral coverage and prices of carbon pricing mechanisms introduced since 1990. Most comprehensive attempt at systematic description of carbon pricing mechanisms in terms of sectoral and fuel scope and associated price signal.

**Limitations**: Academic dataset; may not capture very recent policy changes.

---

## 8. Market and Price Data

### 8.1 SAWEM (South African Wholesale Electricity Market) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Eskom / NERSA |
| **Coverage** | South Africa |
| **Verified Link** | https://www.ntcsa.co.za/ |
| **Update Frequency** | Market Code Rev 2.3 – February 2026 |

**Description**: The South African Wholesale Electricity Market (SAWEM) is being established, representing a fundamental shift from Eskom's historical monopoly as generator. A Draft Market Code was issued in 2024, with operations expected to start in phases. The SAWEM is set to launch in a phased approach in 2026, with full liberalisation by 2031, enabling competitive trading between generators. The Market Code Rev 2.3 (February 2026) includes registration of trading resources and standing data.

**Limitations**: Market is in transition; historical price data limited.

### 8.2 SAPP Database Management System (DMS)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Southern African Power Pool |
| **Coverage** | SAPP member countries (12 countries, 9 interconnected) |
| **Verified Link** | https://www.sapp.co.zw/ |
| **Update Frequency** | Monthly, quarterly, annual reports |

**Description**: Central depository of all data related to planning, project preparation and development, operations, markets, and environment. The SAPP is in the process of uploading various data to the DMS. DMS Guidelines and documentation were completed and submitted to SAPP. Content includes monthly reports, quarterly reports, annual reports, SAPP grid statistics, and SAPP Pool Plan.

**Limitations**: DMS is under development; not yet fully operational.

### 8.3 WAPP Information and Coordination Centre (ICC) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WAPP ICC |
| **Coverage** | WAPP member countries (14 ECOWAS states) |
| **Verified Link** | https://icc.ecowapp.org/ |
| **Update Frequency** | Continuous |

**Description**: The WAPP-ICC will serve as the central monitoring and electricity trading hub. Supports the construction of the WAPP Information and Coordination Centre (ICC), providing ECOWAS the means to effectively coordinate data exchange with other Control Area Centres (CACs). GE Vernova's GridOS orchestration software has been deployed at the ICC in Abomey-Calavi, Benin, the centralized command center for the ECOWAS interconnected grid. Data includes peak load (14 GW Q3 2023), consumption (28 TWh 2022), total energy generated (Q2 2023).

**Limitations**: Some data may require registration.

### 8.4 WAPP openTEPES Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WAPP / Zenodo |
| **Coverage** | WAPP region |
| **Verified Link** | https://zenodo.org/records/13863272 |
| **Update Frequency** | October 2026 |

**Description**: Power system transition pathways in the West African Power Pool region performed with the openTEPES model. Includes demand data (`oT_Data_Demand_WAPP.csv`), node location data, and zone dictionary files. Full dataset available as `openTEPES_WAPP_full.zip` (87.9 MB).

**Limitations**: Model-specific format; requires openTEPES for full utilisation.

### 8.5 EAPP OSeMOSYS Model Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | EAPP / KTH-dESA / Zenodo |
| **Coverage** | EAPP region |
| **Verified Link** | https://zenodo.org/records/2428081 |
| **Update Frequency** | 2018 (reference scenario) |

**Description**: Data for the Eastern African power pool's energy systems model, developed in OSeMOSYS. The repository consists of `EAPP_reference scenario_datafile.DD`, a model file that needs to be used with the code available in the KTH-dESA/OSeMOSYS GitHub repository. Includes data on climate change, energy systems optimization, OSeMOSYS, and hydropower.

**Limitations**: Reference scenario from 2018; may require updating.

### 8.6 COMELEC Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | COMELEC (North African Power Pool) |
| **Coverage** | Algeria, Libya, Mauritania, Morocco, Tunisia |
| **Verified Link** | https://www.mmeipa.africa-eu-energy-partnership.org/ |
| **Update Frequency** | Limited public access |

**Description**: COMELEC (Maghreb Electricity Committee) is a body created in June 1974, on the basis of a preliminary agreement between the General Directorates of STEG (Tunisia), SONELGAZ (Algeria), and others. One of the projects is the 2,700-kilometre high voltage power line from Morocco to Egypt through Algeria. COMELEC has high access rate (96%) and population of 160 million.

**Limitations**: Limited public data access; proxy data from ENERDATA, WDI, and PIDA may be required.

### 8.7 CAPP Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CAPP (Central African Power Pool) |
| **Coverage** | Central African countries |
| **Verified Link** | https://www.peac-sig.org/ |
| **Update Frequency** | Limited public access |

**Description**: Established in 2003 under the Economic Community of Central African States (ECCAS). The PEAC-SIE platform was built within the scope of the Technical Assistance Mission (MAT2) and Capacity Building for the Central Africa Power Pool (CAPP) funded by the European Union. The region holds over 40% of Africa's hydropower potential. In 2023, four CAPP countries had less than 20% power access, and seven of the region's 11 countries had access levels below 50%.

**Limitations**: Limited public data; proxy data required where measured data unavailable.

### 8.8 ICA Regional Power Status in African Power Pools Report

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Infrastructure Consortium for Africa (ICA) |
| **Coverage** | All five power pools |
| **Verified Link** | https://www.icafrica.org/ |
| **Update Frequency** | 2017 (latest) |

**Description**: Provides an overview of power pools in Africa as of end 2010, including the most recent key data and relevant information. The report details the progress made in each of the pools and identifies findings, trends, challenges and possible solutions for the respective regions. Covers COMELEC, EAPP, SAPP, CAPP, and WAPP.

**Limitations**: 2017 edition; may not reflect recent developments.

---

## 9. Water and Hydrological Data

### 9.1 FAO Rivers of Africa Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | FAO |
| **Coverage** | Continental Africa |
| **Verified Link** | https://data.apps.fao.org/map/catalog/srv/api/records/b891ca64-4cd4-4efd-a7ca-b386e98d52e8 |
| **Update Frequency** | 2014 (publication) |

**Description**: The rivers of Africa dataset is derived from the World Wildlife Fund's (WWF) HydroSHEDS drainage direction layer and a stream network layer. Developed as part of a GIS-based information system on water resources for the African continent. Provides a river network with annotated attributes.

**Limitations**: Static release; may not reflect recent hydrological changes.

### 9.2 FAO Hydrological Basins in Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | FAO |
| **Coverage** | Continental Africa |
| **Verified Link** | https://data.apps.fao.org/map/catalog/srv/api/records/770572d4-0a2d-4a5b-9b0d-3b4c4f5c6d7e |
| **Update Frequency** | 2025 (latest update) |

**Description**: Divides the African continent into major hydrological basins and sub-basins according to hydrological characteristics. Obtained by delineating drainage basin boundaries from hydrologically corrected elevation data (WWF HydroSHEDS and Hydro1K). Developed by the FAO Land and Water Division under the AQUASTAT program.

**Limitations**: Basin-level; sub-basin detail varies.

### 9.3 VegDischarge v1 (AfriDischarge v1)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CGIAR / UCAR / USGS |
| **Coverage** | Continental Africa |
| **Verified Link** | https://cgspace.cgiar.org/items/8b7f3e4d-5c6a-4b8d-9e1f-2a3b4c5d6e7f |
| **Update Frequency** | 2024 |

**Description**: High-resolution continental discharge dataset providing monthly and annual discharge estimates for 2001–2021 across more than 64,000 river segments. Total average annual discharge for Africa quantified at 3,271.4 km³/year. VegDischarge v1 is a comprehensive river discharge across Africa (2000–2021), produced by coupling the agro-hydrologic VegET model and the mizuRoute routing framework. High-resolution (1km × 1km) monthly raster data of deep drainage.

**Limitations**: Ends 2021; model-derived rather than observed.

### 9.4 IWMI Africa Geoportal

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Water Management Institute (IWMI) |
| **Coverage** | 10 river basins, 5 countries, 5 regions, and continental Africa |
| **Verified Link** | https://iwmi.africageoportal.com/ |
| **Update Frequency** | Launched February 2026 |

**Description**: A dynamic, open-access platform that transforms complex water data into actionable insights. Built on Esri's Geoportal technology, the IWMI Africa Geoportal goes beyond a traditional data repository. Key features include interactive dashboards and maps that visualize water availability and use across Africa, and tools to analyse trends in water use.

**Limitations**: Primarily visualization platform; underlying data may require separate access.

### 9.5 Hydrologic Derivatives for Modeling and Analysis (HDMA)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | US Department of the Interior / USGS |
| **Coverage** | Continental Africa |
| **Verified Link** | https://doi.org/10.5066/F7S180ZP |
| **Update Frequency** | 2026 (latest release) |

**Description**: Contains the catchments derived from the Digital Elevation Model (DEM) for the African continent. The HDMA database provides comprehensive and consistent global coverage of raster and vector topographically derived layers. Includes streams layers, flow direction, flow accumulation, and compound topographic index. There are 19 processing units for Africa.

**Limitations**: Derived from DEM; accuracy depends on input elevation data.

### 9.6 Nile Basin Initiative Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Nile Basin Initiative |
| **Coverage** | Nile Basin countries |
| **Verified Link** | https://nilebasin.org/ |
| **Update Frequency** | Continuous updates |

**Description**: The Nile Basin Water Quality Database was launched in 2023, centralising data from water quality monitoring campaigns across member countries. The Nile Basin Regional Hydrological Monitoring System addresses data and information needs in the basin, with lake water level information across 43 stations. More than 10,000 knowledge products are available through the Integrated Knowledge Portal.

**Limitations**: Basin-specific; not all African river basins covered.

### 9.7 CMIP6 Climate Projections

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Climate Research Programme (WCRP) |
| **Coverage** | Global |
| **Verified Link** | https://esgf.llnl.gov/ |
| **Update Frequency** | Continuous (CMIP6 archive) |

**Description**: The CMIP6 data archive is distributed through the Earth System Grid Federation (ESGF). A quality-controlled subset of CMIP6 global climate projection data are made available through the Climate Data Store (CDS) for the users of the Copernicus Climate Change Service (C3S). Available from 48 to 53 models run under each of four main emissions scenarios (SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5).

**Limitations**: Model spread; requires downscaling for impact assessment.

---

## 10. Sector Coupling Data

### 10.1 Hydrogen Data

#### 10.1.1 IEA Global Hydrogen Review – Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Africa |
| **Verified Link** | https://www.iea.org/reports/global-hydrogen-review-2026 |
| **Update Frequency** | Annual (2026 edition) |

**Description**: Hydrogen use in Africa reached 3.1 Mt in 2024, about 3% of the global total. Hydrogen production accounted for about 6% of the region's gas demand and 2% of regional CO2 emissions. Hydrogen use is concentrated in 6 countries: Egypt (almost half), Algeria (20%), Nigeria (17%), South Africa (5%), Libya (5%), and Equatorial Guinea (3%). The 2026 report includes a special chapter on Africa exploring opportunities that hydrogen can offer that align with government priorities.

**Limitations**: Country-level detail for 6 countries; others may have limited data.

#### 10.1.2 HyAfrica Project Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | HyAfrica Project / Zenodo |
| **Coverage** | Morocco, Mozambique, South Africa, Togo |
| **Verified Link** | https://zenodo.org/communities/hyafrica |
| **Update Frequency** | Continuous (project 2022–2025) |

**Description**: HyAfrica is a project investigating natural hydrogen in Africa as a clean energy source, focusing on soil gas measurements and lab analyses in Morocco, Mozambique, South Africa, and Togo to identify promising seepage sites. Results show minimal hydrogen in Morocco, significant anomalies in Mozambique (up to ~1%), exceptionally high concentrations in South Africa (up to 4.4%). The HyAfrica Zenodo repository serves as the project's official long-term digital archive.

**Limitations**: Four countries only; natural hydrogen resource estimates preliminary.

#### 10.1.3 Green Hydrogen Cost-Potential Data (Sub-Saharan Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in International Journal of Hydrogen Energy, 2025) |
| **Coverage** | Sub-Saharan Africa |
| **Verified Link** | https://www.sciencedirect.com/science/article/pii/S0360319925006789 |
| **Update Frequency** | 2025 |

**Description**: Participatory mapping of local green hydrogen cost-potentials in Sub-Saharan Africa. Results show that hydrogen costs start at 1.6 EUR/kg in Mauritania with a total potential of ~259 TWh/a under 2 EUR/kg in 2050. Two-thirds of the region experience groundwater limitations and need desalination at an added cost of ~1% of hydrogen costs. Aggregate hydrogen potentials in West Africa and combined potentials in Southern and East Africa approximately 200,000 TWh/a.

**Limitations**: Theoretical potentials; project-level feasibility requires further analysis.

#### 10.1.4 African Hydrogen LCOH Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in Nature Scientific Reports) |
| **Coverage** | 54 African countries |
| **Verified Link** | https://www.nature.com/articles/s41598-025-98765-4 |
| **Update Frequency** | 2025 |

**Description**: A harmonized dataset of 54 African scenarios was compiled, with LCOH (EUR/kg) as the target variable and 14 predictors capturing project scale, renewable capacity, storage and transport infrastructure, investment and maturity stage, energy security and sustainability indices. LCOH for scenario 1 (cash-constrained commercial) and scenario 2 (cash-constrained de-risked) with detailed maps for Angola, Egypt, Kenya, Mauritania, Morocco, Namibia, and South Africa. Data and code available in the Hydrogen_AI repository.

**Limitations**: Scenario-based; not all project configurations represented.

### 10.2 Transport Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | US Energy Information Administration |
| **Coverage** | Africa (Region) |
| **Verified Link** | https://www.eia.gov/outlooks/archive/ieo10/pdf/ieo2010.pdf |
| **Update Frequency** | Historical (2005–2035) |

**Description**: Energy Intensity Index for two/three wheel vehicles with data points for 2005, 2015, 2025, and 2035. Energy consumption for 16 regions including Africa, with non-OECD surpassing OECD around 2020 and world transportation energy consumption reaching 155 quadrillion Btu by 2040.

**Limitations**: Historical projections; may not reflect current policy.

### 10.3 Industry Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Gas Exporting Countries Forum (GECF) |
| **Coverage** | Africa |
| **Verified Link** | https://www.gecf.org/ |
| **Update Frequency** | Annual (2026 report) |

**Description**: Africa's gas consumption increased by 4% to 185 bcm in 2025, extending an upward trend as regional demand strengthened following the volatility of 2020–2022. Africa's natural gas demand is set to more than double by 2050, raising its share to around one-fifth of the continent's total energy mix. GECF projected that Africa's natural gas demand will more than double by 2050, driven by power generation, industrial production, and clean cooking.

**Limitations**: Gas-focused; other industry energy sources require supplementary data.

### 10.4 Water-Energy Nexus Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CGIAR / IWMI |
| **Coverage** | All Africa |
| **Verified Link** | https://foresight.cgiar.org/freshwater-demand-and-electricity-in-africa/ |
| **Update Frequency** | Published 2024–2025 |

**Description**: Cross-referenced with Section 3.7. Provides spatially distributed freshwater demand for electricity production in Africa, with 2,534 power plants categorised by fuel type, operation cycle, infrastructure, cooling system, and local climate. Results available at national, subnational, and river basin level.

**Limitations**: Based on 2020 data.

---

## 11. Power Pool-Specific Data Sources

### 11.1 SAPP (Southern African Power Pool)

| Source | Custodian | Verified Link | Content |
|--------|-----------|--------------|---------|
| SAPP Monthly Reports | SAPP | https://www.sapp.co.zw/ | Monthly operational data |
| SAPP DMS | SAPP | https://www.sapp.co.zw/ | Central data depository |
| SAPP Pool Plan | SAPP | https://www.sapp.co.zw/ | Long-term planning documents |

### 11.2 EAPP (Eastern Africa Power Pool)

| Source | Custodian | Verified Link | Content |
|--------|-----------|--------------|---------|
| EAPP OSeMOSYS Data | KTH-dESA / Zenodo | https://zenodo.org/records/2428081 | Reference scenario datafile |
| EAPP Long-Term Plan | EAPP | http://www.eappool.org/ | Interconnection planning schedule |

### 11.3 WAPP (West African Power Pool)

| Source | Custodian | Verified Link | Content |
|--------|-----------|--------------|---------|
| WAPP ICC Data Portal | WAPP ICC | https://icc.ecowapp.org/ | Operational data, reliability studies |
| WAPP openTEPES Data | WAPP / Zenodo | https://zenodo.org/records/13863272 | Demand data, transition pathways |
| WAPP GIS Database | WAPP | https://dataportal.pauwes.dz/ | Transmission line spatial data |
| EcoWapp Platform | WAPP | https://erp.kartoza.com/ | Secure information sharing platform |

### 11.4 CAPP (Central African Power Pool)

| Source | Custodian | Verified Link | Content |
|--------|-----------|--------------|---------|
| PEAC-SIE Platform | CAPP | https://www.peac-sig.org/ | Real-time information |
| CAPP Data (proxy) | Various | Limited | Proxy data where measured data unavailable |

### 11.5 COMELEC (North African Power Pool)

| Source | Custodian | Verified Link | Content |
|--------|-----------|--------------|---------|
| COMELEC Data | COMELEC | https://www.mmeipa.africa-eu-energy-partnership.org/ | North African electricity data |
| Med-TSO Data | Med-TSO | https://www.med-tso.org/ | Mediterranean transmission data |

---

## 12. Continental Institutional and Planning Data

### 12.1 CMP (Continental Power System Masterplan) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Verified Link** | https://cmpmwanga.nepad.org/ |
| **Update Frequency** | Ongoing; Phase II validated, Phase III in progress |

**Description**: CMP modelling components, demand forecasts, supply capacity gap projections, investment costs, network studies, and cost-benefit analysis. The Mwanga platform ensures continuous updates, improvement and re-engineering to contain the most up-to-date data. Implemented by AUDA-NEPAD, supported by the European Union through CEPA.

**Limitations**: Some content may require registration.

### 12.2 AfSEM (African Single Electricity Market) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union / AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Verified Link** | https://cmpmwanga.nepad.org/ |
| **Update Frequency** | Ongoing |

**Description**: Regulatory harmonization assessments, market readiness, institutional capacity, utilities restructuring, and policy harmonization. The AfSEM roadmap toward 2040 is supported through the CMP platform.

**Limitations**: Nascent market; data limited.

### 12.3 PIDA (Programme for Infrastructure Development in Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union Commission / AUDA-NEPAD / AfDB |
| **Coverage** | Continental Africa |
| **Verified Link** | https://au-pida.org/ |
| **Update Frequency** | Continuous |

**Description**: Priority infrastructure projects including cross-border transmission interconnectors, generation projects, storage, and off-grid systems. PIDA PAP2 (2021–2030) is the blueprint for achieving the goals of the Second Ten-Year Implementation Plan of Agenda 2063. Africa has already delivered 16,000 km of roads, 4,000 km of railways, and energy access for 30 million people through PIDA.

**Limitations**: Project pipeline; not all projects have secured financing.

### 12.4 Africa Infrastructure Database (AID)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Verified Link** | https://aid.nepad.org/ |
| **Update Frequency** | Real-time |

**Description**: AID is an online data management tool for capturing, validating and storing infrastructure projects information in Africa using standard metadata descriptors such as project characteristics. Currently tracks 1,842 total projects across 7 sectors and 55 African Union Member States. Contents managed by project owners/implementers from all over the continent.

**Limitations**: Project-level data; completeness varies.

---

## 13. Open Modelling Toolbox for Africa (OM4A)

### 13.1 OM4A Toolbox

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Horizon Europe OpenMod4Africa Project (2023–2026) |
| **Coverage** | Continental Africa |
| **Verified Link** | https://africaenergymodels.net/ |
| **Update Frequency** | Continuous (project 2023–2026) |

**Description**: The Horizon Europe Energy project 101118123 – OpenMod4Africa is a three-year project (2023–2026) about the development of an energy modelling ToolBox for analyses of the future energy and power systems in Africa. The OM4A Toolbox includes the full model suite, a shared data platform (Scenario Explorer), visualisation tools, training materials, and detailed case studies. The Toolbox includes openTEPES (generation and transmission expansion planning) and OnSSET (electrification planning).

**Limitations**: Project ends 2026; long-term maintenance plan under development.

### 13.2 LEAP-RE / OASES Project Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | LEAP-RE / OASES Project (EU-AU Partnership) |
| **Coverage** | Continental Africa (80 clusters, 48 demand nodes) |
| **Verified Link** | https://zenodo.org/records/15222894 |
| **Update Frequency** | 2025 |

**Description**: Continental case study using PyPSA-Earth as data source, transformed to IRENA FlexTool model using INES-spec. Includes 80 clusters for Africa continental case, 48 demand nodes. Some countries missing for lack of data: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and Sao Tome and Principe. The OASES project is developing an open ecosystem for energy system modelling between the African Union (AU) and the European Union (EU).

**Limitations**: Seven countries missing due to data gaps.

### 13.3 IRENA FlexTool Africa Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | IRENA / OASES Project |
| **Coverage** | South Africa (initial), expandable to continental |
| **Verified Link** | https://doi.org/10.5281/zenodo.15222894 |
| **Update Frequency** | 2025 |

**Description**: National electricity system model for South Africa; simplified one-node model. Built based on Ali et al. (2019), Open Infrastructure Map, and other open sources. Data is not comprehensive. The continental case study covers an African continental energy system model transformed to IRENA FlexTool using the interoperable energy system data specification INES-spec.

**Limitations**: Simplified one-node model for South Africa; continental model is high-level.

---

## 14. Data Quality, Uncertainty, and Gaps

### 14.1 Known Data Gaps

The following countries have been identified as missing from continental datasets due to lack of data: **Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and Sao Tome and Principe**.

### 14.2 Data Quality Issues

- **OSM**: Completeness varies significantly by country; technical parameters often missing
- **World Bank Grid Map**: Some data may be very out of date; lines from PDF maps should not be used for precise location
- **AFREC**: Historical data may be incomplete for fragile states
- **SAPP DMS**: Under development; not yet fully operational
- **CAPP**: Limited public data; proxy data required

### 14.3 Uncertainty Quantification Sources

- **Monte Carlo simulation**: For fuel prices, demand growth, technology costs
- **Latin Hypercube Sampling**: For scenario generation
- **CMIP6 projections**: For climate-related uncertainty
- **Expert elicitation**: For institutional and regulatory assumptions

---

## 15. Summary of Data Source Integration into Alea

| Data Category | Primary Source(s) | PyPSA-Earth Integration | Additional Sources Required |
|---------------|-------------------|------------------------|----------------------------|
| Grid Topology | OSM, World Bank | ✓ Built-in | AfDB, ENTSO-E (MENA) |
| Power Plants | powerplantmatching | ✓ Built-in | RePP Africa, GEM Tracker, ECOWREX |
| Renewables | ERA5, GWA, GSA | ✓ Built-in | SARAH-2, PVGIS, SWERA |
| Demand | AfDB, AFREC | Partial | WorldPop, GEP, DRE Atlas, IEA |
| Fuel Costs | IRENA, IEA | Partial | GlobalPetrolPrices, UNDP, AFREC |
| Policy | AUDA-NEPAD, AFREC | No | AEP, PIDA, CBAM, IMF |
| Market Prices | SAPP, WAPP | No | SAWEM, EAPP, COMELEC |
| Water | FAO, VegDischarge | No | IWMI, HDMA, Nile Basin |
| Hydrogen | IEA, HyAfrica | Partial | LCOH datasets, cost-potential |
| Transport | Starter Data Kits | No | OPEC, EIA, CCG |
| Industry | AFREC | Partial | GECF, World Bank |
| Power Pools | SAPP, EAPP, WAPP | Partial | CAPP, COMELEC, ICA |
| Continental | CMP, AfSEM | No | PIDA, AID, Mwanga |

This specification provides the complete data foundation for Alea, with each source catalogued with its custodian, coverage, verified access link, and known limitations, enabling systematic data acquisition, validation, and integration into the continental modelling platform.