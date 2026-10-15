# Alea: Comprehensive Data Source Specification

## A Methodical Inventory of All Required Data Inputs for Continental Energy System Modelling

---

## 1. Introduction and Methodology

This specification catalogues every data source required to build, calibrate, and operate Alea across all 55 African Union member states, five regional power pools, and the continental interconnection. Sources are organised by functional category, with each entry specifying the source name, custodian, coverage, access method, update frequency, and known limitations. Where PyPSA-Earth already integrates a source, this is noted.

The inventory follows the data pipeline sequence: (1) grid topology, (2) generation assets, (3) renewable resources, (4) demand, (5) fuel and technology costs, (6) policy and regulatory, (7) market and price, (8) water and hydro, (9) sector coupling, (10) power pool-specific, and (11) continental institutional data.

---

## 2. Grid Topology and Transmission Network Data

### 2.1 OpenStreetMap (OSM)

**Custodian**: OpenStreetMap Foundation
**Coverage**: Global, including all 55 AU member states
**Access**: Bulk download via Geofabrik; PyPSA-Earth integrates OSM extraction automatically
**Update frequency**: Continuous (crowd-sourced)
**Content**: Power lines (location, path, partial voltage data), substations, generators, cables
**Limitations**: Data completeness varies significantly by country. OSM is rich in South Africa, Kenya, and North Africa, but sparse in CAPP member states and fragile states. Technical parameters (impedance, capacity) are often missing and must be inferred or supplemented.

### 2.2 World Bank Africa Electricity Transmission and Distribution Grid Map (2017)

**Custodian**: World Bank Group / International Finance Corporation
**Coverage**: All continental African countries and Madagascar, plus MENA region
**Access**: enerdydata.info; also available via Stanford SearchWorks
**Update frequency**: Last major update 2017, with some datasets updated October 2025
**Content**: Transmission lines above 110 kV, total length 4,204 km across 1,818 inputs; planned and existing grid lines; voltage from sub-kV to 700 kV EHV
**Sources compiled from**: Africa Infrastructure Country Diagnostic (AICD), OSM, Arab Union of Electricity, WAPP GIS database, World Bank project archives
**Limitations**: Some data, notably from AICD and World Bank project archives, may be very out of date. Many new lines may exist which are not shown, and planned lines may have changed. Data from World Bank project archives has been digitised from PDF maps and should serve as an indication of extent rather than precise location

### 2.3 AfDB Africa Power Plants Map

**Custodian**: African Development Bank
**Coverage**: Continental Africa
**Access**: Via AfDB open data portal and Africa Energy Portal
**Content**: Power plant locations, capacity, technology type
**Use**: Cross-validation of OSM and World Bank topology

### 2.4 ENTSO-E and Regional TSO Data

For North African countries (COMELEC members), transmission data may be supplemented by:
- **ENTSO-E Transparency Platform** for Morocco, Algeria, Tunisia, Libya, Egypt interconnections
- **Med-TSO** (Mediterranean Transmission System Operators) data for cross-Mediterranean links

### 2.5 GridKit, Transnet, SciGrid

**Custodian**: Various research institutions
**Coverage**: Limited to specific regions (primarily Europe)
**Access**: Open-source packages
**Limitations**: Not global coverage; cannot be used as primary source for Africa

---

## 3. Power Plant and Generation Asset Data

### 3.1 powerplantmatching (Consolidated Database)

**Custodian**: PyPSA-Earth / Open Source
**Coverage**: Global, with demonstrated application in Africa
**Access**: Python package; integrated into PyPSA-Earth workflow
**Input databases consolidated**:
- **GEO** (Global Energy Observatory)
- **GPD** (Global Power Plant Database, World Resources Institute)
- **IRENA** (International Renewable Energy Agency)
- **GEM** (Global Energy Monitor)
**Method**: Raw datasets are cleaned, aggregated at power plant level, filtered, then matched pairwise to identify duplicates based on name, location, fuel, and technology. Consolidated into a singular dataset with exact geographical location, carrier, technology, and installation date
**Limitations**: Relevance to Africa was acceptable before GEM integration; GEM has improved performance. Fuel-fired generators (coal, gas) included in addition to geothermal.

### 3.2 RePP Africa (Renewable Power Plant Database for Africa)

**Custodian**: Peters et al. (2023), published in Scientific Data
**Coverage**: All Africa
**Access**: Open access via Springer Nature / Figshare
**Content**: 1,074 hydropower plant records, 1,128 solar power plant records, 276–282 wind power plant records. Spatially explicit, georeferenced, and curated database for existing and proposed renewable power plants
**Attributes**: For each power plant, metadata includes location, capacity, technology, status (existing/proposed), and installation date
**Use**: Supplement and cross-validate powerplantmatching output for renewable technologies

### 3.3 Africa Energy Tracker (Global Energy Monitor)

**Custodian**: Global Energy Monitor
**Coverage**: Continental Africa
**Access**: globalenergymonitor.org
**Content**: Comprehensive dataset of energy infrastructure across Africa, covering oil and gas, coal, renewables, and other power infrastructure specifically for power generation (solar, wind, hydro, etc.)
**Update frequency**: Regular updates

### 3.4 ECOWREX Power Plants Database

**Custodian**: ECOWAS Regional Centre for Renewable Energy and Energy Efficiency (ECREEE)
**Coverage**: West Africa (ECOWAS member states)
**Access**: ecowrex.org
**Content**: Power plants by country with capacity, technology, status (operational, planned)
**Use**: WAPP-specific validation and supplementation

### 3.5 African Hydropower Atlas (Sterl et al., 2021)

**Custodian**: Sterl et al., published in Open Research Europe
**Coverage**: All Africa
**Access**: HydroShare repository; version 2.2 as of 2023
**Content**: Seasonal hydropower generation profiles for nearly all existing and several hundred future hydropower plants on the African continent. Built on continental-scale hydrological modelling combined with detailed technical databases of hydropower plant characteristics
**Use**: Hydropower resource assessment and seasonal generation profiling

### 3.6 AfREP-Hydro (IRENA)

**Custodian**: International Renewable Energy Agency (IRENA)
**Coverage**: All Africa
**Access**: IRENA Global Atlas; source code on Zenodo; data on HydroShare (version 2.3)
**Content**: Spatiotemporal data atlas covering all existing and several hundred committed, planned, and potential future hydropower plants across Africa. Includes reservoir plant upstream and run-of-river cascaded configurations
**Use**: Hydropower generation profiles for energy modelling; specifically designed for the energy modelling community

### 3.7 Freshwater Demand for Electricity in Africa Database

**Custodian**: CGIAR / Foresight
**Coverage**: All Africa
**Access**: foresight.cgiar.org
**Content**: Power plants categorised by fuel type, operation cycle, infrastructure, cooling system, and local climate. Utilises GEM Wiki, Power Technology, Google Maps, and validated against IEA and IRENA data for 2021
**Use**: Water-energy nexus modelling; cooling water demand estimation

---

## 4. Renewable Resource Data

### 4.1 ERA5 Reanalysis

**Custodian**: ECMWF / Copernicus Climate Change Service (C3S)
**Coverage**: Global, including all Africa
**Access**: Copernicus Climate Data Store (CDS); DOI: 10.24381/cds.adbb2d47
**Content**: State-of-the-art global reanalysis providing hourly data on wind speed, solar irradiance, temperature, and other meteorological variables
**Resolution**: ~30 km globally; used as primary input for `atlite` renewable profile generation
**Use**: Hourly renewable generation profiles for solar PV, onshore wind, offshore wind

### 4.2 Global Wind Atlas (GWA) 3.0

**Custodian**: Technical University of Denmark (DTU)
**Coverage**: Global
**Access**: globalwindatlas.info; free web-based application
**Content**: High-resolution wind resource maps with improved accuracy from novel modelling methodologies and high-quality input data; pushed by latest ERA5 reanalysis data
**Use**: Downscaling ERA5 wind data to higher spatial resolution; validation of wind resource estimates

### 4.3 Global Solar Atlas (GSA)

**Custodian**: World Bank Group / Solargis
**Coverage**: Global
**Access**: globalsolaratlas.info
**Content**: Solar resource maps (GHI, DNI, DIF) at high spatial resolution
**Use**: Solar PV resource assessment; validation of ERA5-derived solar profiles

### 4.4 PVGIS

**Custodian**: European Commission Joint Research Centre
**Coverage**: Global, including Africa
**Access**: re.jrc.ec.europa.eu/pvgis
**Content**: Solar radiation database and PV performance modelling tool
**Use**: Solar resource validation and PV yield estimation

### 4.5 SARAH-2 Satellite Data

**Custodian**: EUMETSAT CM SAF
**Coverage**: Africa, Europe, and parts of Atlantic
**Access**: CM SAF data portal
**Content**: Surface radiation dataset with high temporal and spatial resolution
**Use**: Solar resource assessment for Africa; complements ERA5

### 4.6 SWERA (Solar and Wind Energy Resource Assessment)

**Custodian**: UNEP / NREL
**Coverage**: Selected developing countries including African nations
**Access**: UNEP GRID databases
**Content**: Solar and wind resource maps and data
**Use**: Validation and supplementation in regions with limited ERA5 accuracy

### 4.7 Global Wind Atlas (ERA5_GWA Downscaled)

**Custodian**: DTU / World Bank
**Coverage**: Global
**Access**: Derived product from GWA and ERA5
**Content**: Statistical downscaling variant of ERA5 using Global Wind Atlas; estimates show similar average wind energy potential to ERA5 but with improved spatial detail
**Use**: Higher-resolution wind resource assessment for Africa

### 4.8 Land-Use and Environmental Constraints

- **Copernicus Land Cover**: Global land cover data for excluding arable land, protected areas, and steep terrain
- **World Database on Protected Areas (WDPA)**: Protected area boundaries for exclusion constraints
- **SAPAD (South African Protected Areas Database)**: For South Africa-specific constraints
- **SACAD (South African Conservation Areas Database)**: For South Africa-specific constraints
- **GEBCO Bathymetric Data**: For offshore wind potential assessment
- **EEZ Boundaries**: Exclusive Economic Zone boundaries for offshore resource allocation

---

## 5. Demand and Socioeconomic Data

### 5.1 AfDB African Regional Energy Statistics (2014)

**Custodian**: African Development Bank Group
**Coverage**: All Africa
**Access**: HDX (Humanitarian Data Exchange); Hugging Face dataset mirror
**Content**: 51,051 rows covering production, consumption, imports, and exports of energy resources for African countries
**Update frequency**: 2014 edition (inactive dataset); historical baseline
**Use**: Baseline demand and generation statistics; validation

### 5.2 AFREC African Energy Balance and Indicators

**Custodian**: African Energy Commission (AFREC), African Union
**Coverage**: All 55 AU member states
**Access**: au-afrec.org; AFREC Africa Energy Statistics; African Energy Database (digital format)
**Content**: Comprehensive collection of statistical data based on production, consumption, imports, and exports of energy resources. Includes Key Africa Energy Statistics (KAES) 2025 edition, Africa Energy Balance, and African Energy Database
**Update frequency**: Annual; 2025 edition available
**Use**: Primary demand and supply baseline for all 55 member states; aligned with international standards

### 5.3 WorldPop Population Data

**Custodian**: WorldPop, University of Southampton
**Coverage**: Global, including all Africa
**Access**: worldpop.org
**Content**: Population counts at 100 m resolution (2020); constrained population counts for individual countries
**Use**: Spatial disaggregation of demand; settlement-level demand estimation

### 5.4 Global Electrification Platform (GEP) 3.0

**Custodian**: World Bank Group / ESMAP
**Coverage**: 58 countries globally, including all of Sub-Saharan Africa
**Access**: energydata.info; GEP 3.0 released August 2024
**Content**: Geodatabase offering insights into least-cost electrification options for millions of unserved settlements. Utilises GIS-based analysis considering distance to grid network, settlement density, and other factors
**Use**: Electrification planning; demand estimation for unserved areas; Mission 300 alignment

### 5.5 Distributed Renewable Energy (DRE) Atlas

**Custodian**: ESMAP / World Bank
**Coverage**: 58 countries including Sub-Saharan Africa, Asia-Pacific, Latin America
**Access**: energydata.info
**Content**: Detailed information on settlements across 58 countries, including settlement clusters in CSV and GeoJSON formats
**Use**: Settlement-level demand estimation; mini-grid and off-grid planning; supports Mission 300 (connecting 300 million people in Africa)

### 5.6 GDP Raster Data (DRYAD)

**Custodian**: DRYAD / various research institutions
**Coverage**: Global, including Africa
**Access**: DRYAD repository
**Content**: Spatially disaggregated GDP data
**Use**: Spatial demand disaggregation; economic activity proxies

### 5.7 IEA World Energy Outlook – Africa Data

**Custodian**: International Energy Agency
**Coverage**: Africa region (North Africa, West Africa, Central Africa, Eastern Africa, Southern Africa)
**Access**: IEA WEO reports and data services
**Content**: Historical and projected electricity demand, capacity, and generation by region. Africa total demand projected to reach 1,869 TWh by 2040; SSA 1,297 TWh; North Africa 572 TWh
**Use**: Demand projection benchmarking; scenario calibration

### 5.8 AfDB African Economic Outlook

**Custodian**: African Development Bank
**Coverage**: All Africa
**Access**: AfDB publications
**Content**: GDP growth, population, economic indicators by country
**Use**: Demand growth scenario development; macroeconomic assumptions

### 5.9 Transport Starter Data Kit

**Custodian**: Various (published in Data in Brief, 2024)
**Coverage**: Selected countries in Africa, Asia, and South America
**Access**: PMC / ScienceDirect
**Content**: Historical annual data (1990–2021) on passenger and freight activity, energy intensities, load factors, and vehicle stock, segregated by mode and fuel where available
**Use**: Transport sector demand modelling; electrification scenario development

### 5.10 AFREC Industry Sector Data

**Custodian**: AFREC
**Coverage**: All Africa
**Access**: au-afrec.org
**Content**: Total final consumption by sector including industry. Africa total final consumption increased across transport, households, and industry. Residential and industrial sectors expected to account for 32% and 30% of total consumption respectively by 2050
**Use**: Industrial demand modelling; sectoral disaggregation

---

## 6. Fuel Price and Technology Cost Data

### 6.1 IRENA Renewable Cost Database

**Custodian**: International Renewable Energy Agency
**Coverage**: Global, with country-specific data for Africa
**Access**: IRENA publications and data services
**Content**: Capital costs, O&M costs, and levelised cost of electricity for solar PV, wind, hydro, biomass, and other renewables. IRENA has established local gaseous hydrogen costs for the African continent, starting at 1.1 USD/kgH₂ in 2050
**Use**: Technology cost assumptions for capacity expansion modelling

### 6.2 IEA Cost Data

**Custodian**: International Energy Agency
**Coverage**: Global
**Access**: IEA publications and data services
**Content**: Technology costs, fuel prices, and investment data. IEA Africa Energy Outlook 2022 provides key findings for African energy sector
**Use**: Technology cost validation; fuel price projections

### 6.3 Global Petrol Prices

**Custodian**: GlobalPetrolPrices.com / ADH Data Portal
**Coverage**: 41 African countries
**Access**: ckan.africadatahub.org; globalpetrolprices.com
**Content**: Gasoline prices spanning eight years (2018–2025); some countries have incomplete data due to reporting gaps or political instability
**Use**: Transport fuel cost modelling; consumer price benchmarks

### 6.4 UNDP Fuel Retail Price Data

**Custodian**: UNDP
**Coverage**: Major African countries
**Access**: UNDP publications
**Content**: Fuel retail prices for February–March 2026 period, covering Egypt, Nigeria, South Africa, and others
**Use**: Near-term fuel price validation

### 6.5 AFREC Africa Energy Database

**Custodian**: AFREC
**Coverage**: All Africa
**Access**: au-afrec.org; Africa Energy Browser
**Content**: Energy statistics including fuel prices, production, and consumption
**Use**: Fuel price and availability data for all AU member states

### 6.6 IRENA, IEA, EUROSTAT Joint Data

**Custodian**: IRENA / IEA / EUROSTAT
**Coverage**: Global with Africa coverage
**Access**: Via respective agency data services
**Content**: Final consumption of fuels in transport (diesel) with historical data series 2010–2040, measured in TWh
**Use**: Transport fuel demand modelling

### 6.7 Fossil Fuel Field Approximation (PyPSA-Earth)

**Custodian**: PyPSA-Earth (derived from global datasets)
**Coverage**: Global
**Access**: Integrated into PyPSA-Earth workflow
**Content**: Approximates location of existing fossil fuel fields without detailed field-level data. For decarbonisation scenarios, no detailed input data is currently needed to specify exact fossil fuel field locations
**Use**: Fossil fuel supply modelling for coal and gas carriers

---

## 7. Policy, Regulatory, and Institutional Data

### 7.1 AUDA-NEPAD Mwanga CMP Database

**Custodian**: AUDA-NEPAD (African Union Development Agency)
**Coverage**: Continental Africa
**Access**: cmpmwanga.nepad.org
**Content**: Continental Power System Master Plan database containing historical and projected data needed to model future demand for long-term energy planning by power pools. Includes governance framework for regular updates, harmonisation with existing AU databases (AID, AEIS, AEP), and power pool information systems
**Update frequency**: Continuous updates; regular maintenance of Mwanga platform
**Use**: CMP alignment; continental scenario development

### 7.2 African Energy Information System (AEIS)

**Custodian**: AFREC
**Coverage**: All 55 AU member states
**Access**: Via AFREC
**Content**: Continental energy information system designed by AFREC to host and process energy datasets of all available energy sources. Currently going through a revamp
**Use**: Harmonised energy data collection, transfer, and quality control

### 7.3 Africa Infrastructure Database (AID)

**Custodian**: AUDA-NEPAD
**Coverage**: Continental Africa
**Access**: Via AUDA-NEPAD
**Content**: Infrastructure project data including renewable energy projects
**Use**: Project pipeline validation; transmission expansion planning

### 7.4 Africa Energy Portal (AEP)

**Custodian**: African Development Bank
**Coverage**: All 54 African countries
**Access**: africa-energy-portal.org
**Content**: One-stop-shop for energy sector news, insights, data. Country-level electricity sector profiles, market intelligence, policy analysis, research publications, and sector news. Focuses exclusively on Africa, serving as a repository for accurate and relevant information across the energy value chain
**Update frequency**: Regular updates; data spanning 2000–2024
**Use**: Policy analysis; market intelligence; sector profiles

### 7.5 PIDA (Programme for Infrastructure Development in Africa)

**Custodian**: African Union Commission / AUDA-NEPAD / AfDB
**Coverage**: Continental Africa
**Access**: au-pida.org
**Content**: Priority infrastructure projects including energy interconnectors. PIDA demand forecasts for 2011–2040 covering COMELEC, WAPP, EAPP, CAPP, SAPP
**Use**: Transmission expansion planning; interconnector project validation

### 7.6 National Integrated Resource Plans (IRPs)

**Custodian**: Individual national governments and regulators
**Coverage**: Country-specific
**Access**: Various national energy ministry websites
**Content**: Planned capacity additions, demand forecasts, policy targets
**Use**: National model parametrisation; scenario calibration

### 7.7 EU Carbon Border Adjustment Mechanism (CBAM) Data

**Custodian**: European Commission / Zenodo
**Coverage**: African countries
**Access**: Zenodo repository
**Content**: Data used in analysis of CBAM as incentive for carbon pricing in African countries. Based on GTAP database (version 11c)
**Use**: Carbon pricing scenario development; export competitiveness analysis

### 7.8 IMF Effective Carbon Prices Data

**Custodian**: International Monetary Fund
**Coverage**: African countries
**Access**: IMF eLibrary
**Content**: Effective carbon prices for 2030 (in USD per tonne CO₂) by fuel type (diesel, gasoline, natural gas, coal, ETS)
**Use**: Carbon price benchmarking; policy scenario development

### 7.9 Carbon Pricing Mechanisms Database (Princeton)

**Custodian**: Princeton University
**Coverage**: Global, including Africa
**Access**: dss.princeton.edu
**Content**: Sectoral coverage and prices of carbon pricing mechanisms introduced since 1990. Most comprehensive attempt at systematic description of carbon pricing mechanisms in terms of sectoral and fuel scope and associated price signal
**Use**: Carbon pricing policy analysis

### 7.10 UNDP-Sylvera Carbon Data Access Partnership (CaDAP)

**Custodian**: UNDP / Sylvera
**Coverage**: African governments
**Access**: Via UNDP / Sylvera
**Content**: Insights on over 21,000 carbon projects; enhanced access to carbon market insights for African countries
**Use**: Carbon market analysis; nature-based mitigation potential

### 7.11 Climate Action Platform Africa

**Custodian**: CAPA
**Coverage**: Africa by subregion, country, or subnational level
**Access**: capa.earthrise.media
**Content**: Nature-based mitigation potential data; carbon value and pricing data
**Use**: Nature-based solutions; carbon pricing scenario development

---

## 8. Market and Price Data

### 8.1 SAWEM (South African Wholesale Electricity Market) Data

**Custodian**: Eskom / SAPP
**Coverage**: South Africa
**Access**: Eskom data portal; SAPP reports
**Content**: Wholesale electricity prices, dispatch data, market clearing prices
**Use**: Backtesting of Alea price projections; validation against COMPASS

### 8.2 SAPP Database Management System (DMS)

**Custodian**: Southern African Power Pool
**Coverage**: SAPP member countries (12 countries, 9 interconnected)
**Access**: sapp.co.zw; SAPP Database Management System
**Content**: Central depository of all data related to planning, project preparation and development, operations, markets, and environment. SAPP is in the process of uploading various data to the DMS
**Content type**: Monthly reports, quarterly reports, annual reports, SAPP grid statistics, SAPP Pool Plan
**Use**: SAPP market simulation; cross-border trade analysis

### 8.3 WAPP Information and Coordination Centre (ICC) Data

**Custodian**: WAPP ICC
**Coverage**: WAPP member countries (14 ECOWAS states)
**Access**: icc.ecowapp.org
**Content**: Operational data, reliability studies, WAPP interconnected power system operation manual, peak load (14 GW Q3 2023), consumption (28 TWh 2022), total energy generated (Q2 2023)
**Use**: WAPP market simulation; cross-border trade analysis

### 8.4 WAPP openTEPES Model Data

**Custodian**: WAPP / Zenodo
**Coverage**: WAPP region
**Access**: Zenodo repository (October 2026)
**Content**: Power system transition pathways dataset for WAPP performed with openTEPES model; includes demand data (oT_Data_Demand_WAPP.csv)
**Use**: WAPP modelling validation; demand benchmarking

### 8.5 EAPP OSeMOSYS Model Data

**Custodian**: EAPP / KTH-dESA / Zenodo
**Coverage**: EAPP region
**Access**: Zenodo repository; GitHub (KTH-dESA/OSeMOSYS)
**Content**: EAPP reference scenario datafile for OSeMOSYS model; includes demand, capacity, and system data
**Use**: EAPP modelling validation; capacity and demand benchmarking

### 8.6 COMELEC Data

**Custodian**: COMELEC (North African power pool)
**Coverage**: North African countries (Morocco, Algeria, Tunisia, Libya, Egypt, Mauritania)
**Access**: Limited public access; data primarily from ENERDATA, World Development Indicators (WDI), and PIDA reports
**Content**: Installed capacity, demand, generation mix. COMELEC has high access rate (96%) and population of 160 million
**Use**: North Africa market simulation; cross-Mediterranean trade analysis

### 8.7 CAPP Data

**Custodian**: CAPP (Central African Power Pool)
**Coverage**: Central African countries
**Access**: Limited; ICA Regional Power Status report
**Content**: Peak load by country (MW), investment requirements, power sector overview
**Use**: CAPP modelling with proxy data where measured data unavailable

### 8.8 ICA Regional Power Status in African Power Pools Report

**Custodian**: Infrastructure Consortium for Africa (ICA)
**Coverage**: All five power pools
**Access**: icafrica.org
**Content**: Regional power status report with annexes for COMELEC, EAPP, SAPP, CAPP, and WAPP. Includes peak load by country, investment requirements, and power sector overviews
**Use**: Cross-pool validation; benchmarking

### 8.9 African Energy Portal Market Intelligence

**Custodian**: AfDB
**Coverage**: All Africa
**Access**: africa-energy-portal.org
**Content**: Market intelligence, policy analysis, and investment flow data
**Use**: Market structure analysis; investment trend validation

---

## 9. Water and Hydrological Data

### 9.1 FAO Rivers of Africa Dataset

**Custodian**: FAO
**Coverage**: Continental Africa
**Access**: data.apps.fao.org
**Content**: Derived from World Wildlife Fund's (WWF) HydroSHEDS drainage direction layer and a stream network layer. Provides river network with annotated attributes. Developed as part of an assessment of water resources in Africa
**Use**: Hydro cascade modelling; river basin analysis

### 9.2 FAO Hydrological Basins in Africa

**Custodian**: FAO
**Coverage**: Continental Africa
**Access**: data.apps.fao.org
**Content**: Divides African continent into major hydrological basins and sub-basins according to hydrological characteristics. Delineated from hydrologically corrected elevation data (WWF HydroSHEDS and Hydro1K)
**Use**: Basin-level water allocation modelling; transboundary water constraints

### 9.3 VegDischarge v1 (AfriDischarge v1)

**Custodian**: CGIAR / UCAR
**Coverage**: Continental Africa
**Access**: cgspace.cgiar.org; catalog.data.gov
**Content**: High-resolution continental discharge dataset providing monthly and annual discharge estimates for 2001–2021 across more than 64,000 river segments, with expansion to 600,000 underway. Total average annual discharge for Africa quantified at 3,271.4 km³/year
**Use**: Water availability assessment; hydro generation modelling; drought scenario development

### 9.4 IWMI Africa Geoportal

**Custodian**: International Water Management Institute (IWMI)
**Coverage**: 10 river basins, 5 countries, 5 regions, and continental Africa
**Access**: iwmi.africageoportal.com
**Content**: Water resources data with regular additions
**Use**: Water resource validation; irrigation and cooling water demand

### 9.5 Hydrologic Derivatives for Modeling and Analysis (HDMA)

**Custodian**: US Department of the Interior / USGS
**Coverage**: Continental Africa
**Access**: catalog.data.gov
**Content**: Catchments derived from Digital Elevation Model (DEM) for the African continent
**Use**: Catchment-level hydrological modelling; water balance analysis

### 9.6 Nile Basin Initiative Data

**Custodian**: Nile Basin Initiative
**Coverage**: Nile Basin countries
**Access**: nilebasin.org
**Content**: Transboundary water allocation data, power transmission corridor data (e.g., North-South Power Transmission Corridor Zambia-Tanzania-Kenya)
**Use**: Nile Basin water allocation constraints; transboundary hydro modelling

### 9.7 CMIP6 Climate Projections

**Custodian**: World Climate Research Programme (WCRP)
**Coverage**: Global
**Access**: ESGF data nodes
**Content**: Climate model projections for drought and flood scenarios
**Use**: Climate risk assessment; long-term water availability scenarios

---

## 10. Sector Coupling Data

### 10.1 Hydrogen Data

#### 10.1.1 IEA Global Hydrogen Review 2026 – Africa

**Custodian**: International Energy Agency
**Coverage**: Africa
**Access**: IEA publications
**Content**: Hydrogen use in Africa reached 3.1 Mt in 2024 (about 3% of global total). Only 6 kt of low-emissions hydrogen produced in Africa, exclusively from renewables
**Use**: Hydrogen demand and production baseline

#### 10.1.2 HyAfrica Project Data

**Custodian**: HyAfrica Project / Zenodo
**Coverage**: Morocco, Mozambique, South Africa, Togo
**Access**: Zenodo repository
**Content**: Natural hydrogen exploration results; ranking of hydrogen resource clusters in Mozambique (Macia, Boane), South Africa (Chrissiesmeer, Hendrina, Komati), Morocco, and Togo
**Use**: Natural hydrogen potential assessment; hydrogen cluster identification

#### 10.1.3 Green Hydrogen Cost-Potential Data (Sub-Saharan Africa)

**Custodian**: Various (published in ScienceDirect, 2025)
**Coverage**: Sub-Saharan Africa
**Access**: ScienceDirect
**Content**: Participatory mapping of local green hydrogen cost-potentials. Aggregate hydrogen potentials in West Africa and combined potentials in Southern and East Africa approximately 200,000 TWh/a; all exhibiting comparable technical potentials of approximately 56,000 TWh/a
**Use**: Green hydrogen production potential; cost curve development

#### 10.1.4 African Hydrogen LCOH Dataset

**Custodian**: Various (compiled in scientific literature)
**Coverage**: Africa
**Access**: Scientific publications
**Content**: Levelised Cost of Hydrogen (LCOH) for African locations with main influencing parameters. Mauritania hydrogen costs start at 1.6 EUR/kg with total potential of ~259 TWh/a under 2 EUR/kg in 2050; IRENA established costs starting at 1.1 USD/kgH₂ in 2050
**Use**: Hydrogen cost modelling; export competitiveness analysis

### 10.2 Transport Sector Data

- **Transport Starter Data Kit** (Section 5.9)
- **OPEC Africa Oil Demand by Sector** (2025–2050): Transportation demand projections in mb/d
- **EIA Africa Transport Energy Intensity Data**: Service energy intensity for two/three wheel vehicles, 2005–2035
- **CCG Whole Energy System Model Starter Data Kit for Kenya**: Structured annual data covering historical values and projections for 2023–2050; end-use energy demands for residential, transport, industry, services, and agriculture

### 10.3 Industry Sector Data

- **AFREC Industry Energy Consumption Data**: Total final consumption by sector including industry; correlation between electricity consumption and GDP
- **AFREC Energy Usage by Businesses in Africa**: Energy usage data for industrial and commercial sectors
- **GECF Africa Gas Demand Data**: Natural gas consumption by power and residential demand; 185 bcm in 2025, driven by power and residential demand

### 10.4 Water-Energy Nexus Data

- **Freshwater Demand for Electricity in Africa Database** (Section 3.7)
- **FAO Rivers and Basins Data** (Sections 9.1–9.2)
- **VegDischarge v1** (Section 9.3)

---

## 11. Power Pool-Specific Data Sources

### 11.1 SAPP (Southern African Power Pool)

| Source | Custodian | Access | Content |
|--------|-----------|--------|---------|
| SAPP Monthly Reports | SAPP | sapp.co.zw | Monthly operational data, market reports |
| SAPP Quarterly Reports | SAPP | sapp.co.zw | Quarterly market and operational data |
| SAPP Annual Reports | SAPP | sapp.co.zw | Annual statistics, pool plan |
| SAPP DMS | SAPP | sapp.co.zw | Central data depository (under development) |
| SAPP Pool Plan | SAPP | sapp.co.zw | Long-term planning documents |

### 11.2 EAPP (Eastern Africa Power Pool)

| Source | Custodian | Access | Content |
|--------|-----------|--------|---------|
| EAPP OSeMOSYS Data | KTH-dESA / Zenodo | Zenodo | Reference scenario datafile for EAPP model |
| EAPP Long-Term Interconnection Plan | EAPP | EAPP Secretariat | Interconnection planning schedule (2011 study) |
| JICA EAPP Reports | JICA | openjicareport.jica.go.jp | EAPP analysis reports |

### 11.3 WAPP (West African Power Pool)

| Source | Custodian | Access | Content |
|--------|-----------|--------|---------|
| WAPP ICC Data Portal | WAPP ICC | icc.ecowapp.org | Operational data, reliability studies, manuals |
| WAPP openTEPES Data | WAPP / Zenodo | Zenodo | Demand data, transition pathways |
| WAPP GIS Database | WAPP | PAUWES Data Portal | Transmission line spatial data (January 2017) |
| EcoWapp Platform | WAPP | erp.kartoza.com | Secure information sharing platform |
| JRC Dispa-SET WAPP Dataset | European Commission JRC | data.europa.eu | WAPP power system dataset |

### 11.4 CAPP (Central African Power Pool)

| Source | Custodian | Access | Content |
|--------|-----------|--------|---------|
| ICA Regional Power Status Report | ICA | icafrica.org | CAPP overview, investment requirements, peak load |
| CAPP Data (proxy) | Various | Limited | Proxy data required where measured data unavailable |

### 11.5 COMELEC (North African Power Pool)

| Source | Custodian | Access | Content |
|--------|-----------|--------|---------|
| ENERDATA | ENERDATA | Commercial | North African electricity data |
| World Development Indicators | World Bank | data.worldbank.org | Macroeconomic and energy indicators |
| PIDA Reports | AU/AUDA-NEPAD/AfDB | au-pida.org | COMELEC demand forecasts (2011–2040) |
| Med-TSO Data | Med-TSO | med-tso.org | Mediterranean transmission data |

---

## 12. Continental Institutional and Planning Data

### 12.1 CMP (Continental Power System Masterplan) Data

**Custodian**: AUDA-NEPAD
**Coverage**: Continental Africa
**Access**: cmpmwanga.nepad.org; AUDA-NEPAD publications
**Content**: CMP modelling components, demand forecasts, supply capacity gap projections, investment costs, network studies, cost-benefit analysis. CMP Phase II deliverables validated on network studies and reports. Expected solar dominance (42% of electricity by 2030) and EAPP diversification trends
**Update frequency**: Ongoing; Phase II validated, Phase III in progress
**Use**: Continental scenario alignment; CMP project pipeline validation

### 12.2 AfSEM (African Single Electricity Market) Data

**Custodian**: African Union / AUDA-NEPAD
**Coverage**: Continental Africa
**Access**: Via AUDA-NEPAD CMP platform
**Content**: Regulatory harmonization assessments, market readiness, institutional capacity, utilities restructuring, policy harmonization
**Use**: Market structure simulation; regulatory scenario development

### 12.3 PIDA (Programme for Infrastructure Development in Africa)

**Custodian**: African Union Commission / AUDA-NEPAD / AfDB
**Coverage**: Continental Africa
**Access**: au-pida.org
**Content**: Priority infrastructure projects including cross-border transmission interconnectors, generation projects, storage, and off-grid systems
**Use**: Transmission expansion planning; project pipeline validation

### 12.4 Africa Infrastructure Database (AID)

**Custodian**: AUDA-NEPAD
**Coverage**: Continental Africa
**Access**: Via AUDA-NEPAD
**Content**: Renewable energy project data, infrastructure project pipeline
**Use**: Project validation; investment planning

### 12.5 Mwanga CMP Platform

**Custodian**: AUDA-NEPAD
**Coverage**: Continental Africa
**Access**: cmpmwanga.nepad.org
**Content**: Continental Power System Master Plan database with historical and projected data. Includes governance framework for regular updates, harmonisation with existing AU databases (AID, AEIS, AEP), and power pool information systems
**Update frequency**: Continuous updates
**Use**: Central data repository for CMP-aligned modelling

---

## 13. Open Modelling Toolbox for Africa (OM4A)

### 13.1 OM4A Toolbox

**Custodian**: Horizon Europe OpenMod4Africa Project (2023–2026)
**Coverage**: Continental Africa
**Access**: Zenodo
**Content**: A suite of linked and open-source models adapted to Africa, including:
- **openTEPES**: Decision support system for integrated generation and transmission planning
- **OnSSET**: GIS-based tool for electrification planning and energy access goals in unserved areas
**Use**: Model interoperability; electrification planning

### 13.2 LEAP-RE / OASES Project Data

**Custodian**: LEAP-RE / OASES Project (EU-AU Partnership)
**Coverage**: Continental Africa
**Access**: Zenodo; OASES project deliverables
**Content**: Continental case study using PyPSA-Earth as data source, transformed to IRENA FlexTool model using INES-spec. Includes 80 clusters for Africa continental case, 48 demand nodes. Some countries missing for lack of data: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, Sao Tome and Principe
**Use**: PyPSA-Earth validation; model interoperability

### 13.3 IRENA FlexTool Africa Dataset

**Custodian**: IRENA / OASES Project
**Coverage**: South Africa (initial), expandable to continental
**Access**: Zenodo (DOI: 10.5281/zenodo.15222894)
**Content**: National electricity system model for South Africa; simplified one-node model. Built based on Ali et al. (2019), Open Infrastructure Map, and other open sources. Data is not comprehensive
**Use**: South Africa validation; model interoperability

---

## 14. Data Quality, Uncertainty, and Gaps

### 14.1 Known Data Gaps

The following countries have been identified as missing from continental datasets due to lack of data: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and Sao Tome and Principe.

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

This specification provides the complete data foundation for Alea. Each source has been catalogued with its custodian, coverage, access method, and known limitations, enabling systematic data acquisition, validation, and integration into the continental modelling platform.