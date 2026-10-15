# Alea: Comprehensive Data Source Specification with Direct Data Links

## A Methodical Inventory of All Required Data Inputs for Continental Energy System Modelling

---

## 1. Introduction and Methodology

This specification catalogues every data source required to build, calibrate, and operate Alea across all 55 African Union member states, five regional power pools, and the continental interconnection. Each entry includes the source name, custodian, coverage, **direct verified link to the actual data file, download endpoint, or API**, and a description of the data content and known limitations.

---

## 2. Grid Topology and Transmission Network Data

### 2.1 OpenStreetMap (OSM) – Africa Extract

| Attribute | Detail |
|-----------|--------|
| **Custodian** | OpenStreetMap Foundation / Geofabrik |
| **Coverage** | All 55 AU member states |
| **Direct Data Link** | `https://download.geofabrik.de/africa-latest.osm.pbf` |
| **Alternative (mirror)** | `https://dev.download.openstreetmap.fr/extracts/africa-latest.osm.pbf` |
| **Update Frequency** | Daily |

**Description**: Direct `.osm.pbf` file (7.4 GB) for the entire African continent, suitable for Osmium, Osmosis, imposm, osm2pgsql, and mkgmap. The mirror provides `africa.osm.pbf` with MD5 checksum available.

**Limitations**: Data completeness varies significantly by country. OSM is rich in South Africa, Kenya, and North Africa, but sparse in CAPP member states and fragile states.

### 2.2 World Bank Africa Electricity Transmission and Distribution Grid Map

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / IFC |
| **Coverage** | All continental African countries and Madagascar |
| **Direct Data Link (Shapefile)** | `http://purl.stanford.edu/vv645gd4791` |
| **Direct Data Link (GeoJSON)** | Available via ArcGIS REST endpoint: `https://services1.arcgis.com/.../MZ00041_WB_ElectricNetworkSHP/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson` |
| **Update Frequency** | Last major update 2017; some datasets updated October 2025 |

**Description**: The most complete and up-to-date open map of Africa's electricity grid network. Includes planned and existing grid lines for all continental African countries and Madagascar, as well as the Middle East region. Total length 4,204 km across 1,818 inputs, with voltage from sub-kV to 700 kV EHV.

**Limitations**: Some data from AICD and World Bank project archives may be very out of date. Lines digitised from PDF maps should serve as an indication of extent rather than precise location.

---

## 3. Power Plant and Generation Asset Data

### 3.1 powerplantmatching (Consolidated Database)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | PyPSA-Earth / Open Source |
| **Coverage** | Global, with demonstrated application in Africa |
| **Direct Data Link** | `https://github.com/PyPSA/powerplantmatching` |
| **Python Installation** | `pip install powerplantmatching` |
| **Update Frequency** | Continuous (open-source development) |

**Description**: The powerplantmatching tool has been successfully employed in Europe and in Africa for fetching multiple datasets and inferring the most likely ground truth. Input sources include OpenStreetMap2022, Global Energy Monitor, IRENA, GEO, GPD, and GEM. The tool cleans, aggregates, filters, and matches datasets pairwise to identify duplicates based on name, location, fuel, and technology.

**Limitations**: Relevance to Africa was acceptable before GEM integration; GEM has improved performance. Fuel-fired generators (coal, gas) included in addition to renewables.

### 3.2 RePP Africa (Renewable Power Plant Database for Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Peters et al. (2023), published in Scientific Data |
| **Coverage** | All Africa |
| **Direct Data Link (Figshare)** | `https://springernature.figshare.com/articles/dataset/RePP_Africa_a_georeferenced_and_curated_database_on_existing_and_proposed_wind_solar_and_hydropower_plants/21711900` |
| **Direct Data Link (Excel)** | `https://springernature.figshare.com/ndownloader/files/38701599` |
| **Update Frequency** | Published 2023 |

**Description**: The Renewable Power Plant database for Africa (RePP Africa) encompasses 1,074 hydro-, 1,128 solar, and 276 wind power plant records. For each power plant, metadata includes location, capacity, technology, status (existing/proposed), and installation date. The Excel file consists of eleven sheets containing one information sheet, one overarching metadata sheet, and three specific sheets per RE resource (metadata, dataset, and references).

**Limitations**: Database is static; new plants commissioned after 2023 may not be included.

### 3.3 Global Energy Monitor – Africa Energy Tracker

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Global Energy Monitor |
| **Coverage** | North and sub-Saharan Africa |
| **Direct Data Link (Tracker)** | `https://globalenergymonitor.org/projects/africa-energy-tracker/` |
| **Direct Data Download** | Data available for download from the tracker page under CC BY 4.0 license |
| **Update Frequency** | Regular updates (March 2026 version available) |

**Description**: Comprehensive dataset mapping energy infrastructure across North and sub-Saharan Africa, covering oil and gas, coal, and renewables. The tracker uses a two-tier system to organise information.

**Limitations**: Tracks projects in non-self-governing and overseas territories, including Western Sahara and Réunion, separately.

### 3.4 ECOWREX Power Plants Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ECOWAS Regional Centre for Renewable Energy and Energy Efficiency (ECREEE) |
| **Coverage** | West Africa (ECOWAS member states) |
| **Direct Data Link** | `https://www.ecowrex.org/power-plants` |
| **Direct Data Format** | XLS dataset available via JRC path `energy/ecowrex/data/xls` |
| **Update Frequency** | Regular updates; yearly temporal frequency |

**Description**: Power plants by country with capacity, technology, and status (operational, planned). Examples include Niger Malbaza solar (7.00 MW PV Solar Operational) and Nigeria Kwa Falls (6.40 MW Small Hydro Planned). The ECOWREX SDI is fully compliant with OGC standards and based on open-source software.

**Limitations**: Coverage limited to ECOWAS member states.

### 3.5 African Hydropower Atlas (Sterl et al., 2021)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Sterl et al., published in Open Research Europe |
| **Coverage** | All Africa |
| **Direct Data Link (HydroShare v2.3)** | `https://www.hydroshare.org/resource/19eab83ae424be3804ee154ed98aea8/` |
| **Direct Data Link (HydroShare v2.1)** | `https://www.hydroshare.org/resource/` (search for "all-Africa hydropower atlas v2.1") |
| **Direct Data Link (Zenodo code)** | `https://doi.org/10.4211/hs.acff23a8fcde4703a7f18a3a75b68bd` |
| **Update Frequency** | Version 2.3 (2024) |

**Description**: A spatiotemporal atlas of hydropower in Africa for energy modelling purposes, containing seasonal hydropower generation profiles for nearly all existing and several hundred future hydropower plants on the African continent. The atlas builds on continental-scale hydrological modelling in combination with detailed technical databases of hydropower plant characteristics. The dataset is made freely available in a spreadsheet-based format.

**Limitations**: Profiles are seasonal averages; hourly resolution requires downscaling.

### 3.6 AfREP-Hydro (IRENA)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Renewable Energy Agency (IRENA) |
| **Coverage** | All Africa |
| **Direct Data Link (HydroShare v2.3)** | `https://www.hydroshare.org/resource/5e8ebdc3bfd24207852539ecf219d915` |
| **Direct Data Link (HydroShare)** | `https://www.hydroshare.org/resource/19eab83ae424be3804ee154ed98aea8/` |
| **Source Code (Zenodo)** | `https://zenodo.org/records/` (search for AfREP-Hydro) |
| **Update Frequency** | Published December 2021 |

**Description**: IRENA's spatiotemporal data atlas covers all existing and several hundred committed, planned, and potential future hydropower plants across the African continent. Provides model-ready seasonal hydropower availability profiles in normal, dry, and wet years. The database can be visualized and downloaded from IRENA Global Atlas and the source code accessed from Zenodo.

**Limitations**: Static release; new projects after 2021 not included.

### 3.7 Freshwater Demand for Electricity in Africa Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CGIAR Initiative on Foresight / IWMI |
| **Coverage** | All Africa |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "Sectoral water demand data for Africa") |
| **Direct Data Link (Excel via paper)** | `https://doi.org/10.1039/D4EW00246F` (supporting information) |
| **Direct Data Link (CGIAR)** | `https://foresight.cgiar.org/freshwater-demand-and-electricity-in-africa/` |
| **Update Frequency** | Published 2024–2025 |

**Description**: The study includes 2,534 power plants, categorizing them by fuel type, operation cycle, infrastructure, cooling system, and local climate. The database can be used at any spatial level, with results on national, subnational, and river basin level. The data is currently available through the paper's supporting information in EXCEL format and via Zenodo as sectoral water demand data for 2020.

**Limitations**: Based on 2020 data; plant-level cooling systems may change.

---

## 4. Renewable Resource Data

### 4.1 ERA5 Reanalysis

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ECMWF / Copernicus Climate Change Service (C3S) |
| **Coverage** | Global, including all Africa |
| **Direct Data Link (CDS Web)** | `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels` |
| **Direct Data Link (API)** | `https://cds.climate.copernicus.eu/api/v2` (requires CDS API key) |
| **Python Download** | `cdsapi` package: `pip install cdsapi` |
| **Update Frequency** | Continuous (1940 to present) |

**Description**: ERA5 is the fifth generation ECMWF reanalysis for the global climate and weather. Provides hourly data on wind speed, solar irradiance, temperature, and other meteorological variables. Downloadable via the Climate Data Store web interface or programmatically using the CDS API service. DOI: 10.24381/cds.adbb2d47.

**Limitations**: ~30 km spatial resolution globally; requires downscaling for site-specific analysis.

### 4.2 Global Wind Atlas 3.0

| Attribute | Detail |
|-----------|--------|
| **Custodian** | DTU Wind Energy / World Bank Group |
| **Coverage** | Global |
| **Direct Data Link (GIS Files)** | `https://globalwindatlas.info/en/download/gis-files` |
| **Direct API Endpoint** | `https://globalwindatlas.info/api/gis/global/wind-speed/50` |
| **Update Frequency** | Version 3.0 (current) |

**Description**: The Global Wind Atlas facilitates online queries and provides freely downloadable datasets based on the latest input data and modeling methodologies. Users can download high-resolution maps of the wind resource potential for use in GIS tools at global, country, and first-administrative unit level.

**Limitations**: Provides long-term averages, not hourly time series.

### 4.3 Global Solar Atlas

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / ESMAP / Solargis |
| **Coverage** | Global |
| **Direct Data Link (Download)** | `https://globalsolaratlas.info/download` |
| **Direct Data Link (World)** | `https://globalsolaratlas.info/download/world` |
| **Direct Data Format** | GEOTIF, AAIGRID, KML/KMZ |
| **Update Frequency** | Continuous updates |

**Description**: Provides long-term averages of solar resource (global horizontal irradiation, direct normal irradiation) and PV power potential. The GIS data stems from the Global Solar Atlas and is available as GEOTIF, AAIGRID, or KML/KMZ file for GoogleEarth. The GSA features a rich download section organized by countries or regions.

**Limitations**: Provides long-term averages, not hourly time series.

### 4.4 PVGIS (Photovoltaic Geographical Information System)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | European Commission Joint Research Centre |
| **Coverage** | Global (except North and South Poles) |
| **Direct Data Link (Downloads)** | `https://ec.europa.eu/jrc/en/PVGIS/downloads/data` |
| **Direct API Endpoint** | `https://re.jrc.ec.europa.eu/api/` |
| **Python Package** | `pvlib.iotools.get_pvgis_tmy()` |
| **Update Frequency** | PVGIS 5.3 (current) |

**Description**: Provides information on solar radiation and photovoltaic system performance for any location in the world. The underlying solar dataset offers satellite and reanalysis solar irradiation data covering from 2014 up to 2024. Three different solar radiation databases (all based on satellite data) are available: PVGIS-SARAH2, PVGIS-NSRDB, and PVGIS-ERA5.

**Limitations**: Sea areas not covered for some datasets.

### 4.5 SARAH-2 Satellite Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | EUMETSAT CM SAF |
| **Coverage** | Africa, Europe, and parts of Atlantic |
| **Direct Data Link (Web UI)** | `https://wui.cmsaf.eu/safira/action/viewProduktSearch` |
| **Direct DOI** | `10.5676/EUM_SAF_CM/SARAH/V002_01` |
| **Direct Data Format** | CF-netCDF |
| **Update Frequency** | SARAH-2.1 covers 1983–2017 |

**Description**: The second edition of the Surface Solar Radiation Data Set - Heliosat (SARAH-2) is a satellite-based climate data record of the solar surface irradiance, surface direct irradiance, and sunshine duration. All CM SAF data can be downloaded free of charge via the Web User Interface. The data record provides surface solar radiation data for 1983–2017, with 30-minute instantaneous data available.

**Limitations**: Ends 2017; PVGIS-SARAH2 extends coverage.

### 4.6 SWERA (Solar and Wind Energy Resource Assessment)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | UNEP / NREL |
| **Coverage** | 13 developing countries including African nations |
| **Direct Data Link (OpenEI)** | `https://openei.org/wiki/SWERA` |
| **Direct Data Link (UNEP)** | `https://na.unep.net/` (SWERA Interactive Form) |
| **Direct Data Download** | XML or CSV format via download section |
| **Update Frequency** | 2001–2007 (historical) |

**Description**: The SWERA Programme provides easy access to credible renewable energy data to stimulate investment in, and development of, renewable energy technologies. Developed detailed assessments of wind and solar energy potential in 13 developing countries. Users can download all selected layers in XML or CSV format. The SWERA web service API is also available for programmatic access.

**Limitations**: Historical programme; data may not reflect current conditions.

---

## 5. Demand and Socioeconomic Data

### 5.1 AfDB African Regional Energy Statistics (2014)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank Group |
| **Coverage** | All Africa |
| **Direct Data Link (HDX)** | `https://data.humdata.org/dataset/african-regional-energy-statistics-2014` |
| **Direct Download (XLSX)** | `https://data.humdata.org/dataset/7e7a0724-2959-4.../resource/8baa3.../download/african-regional-energy-statistics-2014.xlsx` |
| **Update Frequency** | 2014 edition (inactive) |

**Description**: Contains 51,051 rows from African Development Bank Group covering production, consumption, imports, and exports of energy resources for African countries. Source: HDX. License: CC-BY-4.0. The dataset is also available via Hugging Face mirror.

**Limitations**: Historical baseline; not updated.

### 5.2 AFREC African Energy Balance and Indicators

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Energy Commission (AFREC), African Union |
| **Coverage** | All 55 AU member states |
| **Direct Data Link** | `https://au-afrec.org/publications` |
| **Direct Data Link (Database)** | `https://au-afrec.org/` (Africa Energy Database 2024) |
| **Update Frequency** | Annual; 2024 edition available |

**Description**: The AFREC Africa Energy Statistics is a comprehensive collection of statistical data based on production, consumption, imports, and exports of energy resources of the African countries. The Africa Energy Database 2024 represents the 2019 Edition with secondary data collected by international database providers. AFREC started energy data collection of all African countries since 2006 and relied on a questionnaire prepared by WEC (Joint Energy Reporting Format for Africa).

**Limitations**: Detailed energy balance available for subset of member states.

### 5.3 WorldPop Population Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WorldPop, University of Southampton |
| **Coverage** | Global, including all Africa |
| **Direct Data Link (Africa 1km)** | `https://data.worldpop.org/GIS/Population/Whole_Continent/Africa_1km_Population.7z` |
| **Direct Data Link (UN Adjusted)** | `https://data.worldpop.org/GIS/Population/Global_2021_2022_1km_UNadj/constrained/2022/0_Mosaicked/africa_ppp_2022_1km_UNadj_constrained.tif` |
| **Update Frequency** | 2025 release for Sub-Saharan Africa |

**Description**: Gridded population estimates at 3 arcseconds (approximately 100-metre grid cells). The Africa Continental Population Datasets (2000–2020) mosaic all WorldPop country-level African datasets resampled to 1km resolution. Datasets are available in Geotiff and ASCII XYZ format at 3 and 30 arc-seconds.

**Limitations**: Spatial resolution varies by country.

### 5.4 Global Electrification Platform (GEP) 3.0

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Bank Group / ESMAP |
| **Coverage** | 58 countries globally, including all of Sub-Saharan Africa |
| **Direct Data Link** | `https://electrifynow.energydata.info/` |
| **Direct Data Link (Country Models)** | `https://electrifynow.energydata.info/countries/{ISO2}/models` |
| **Direct Data Download** | Zipfile of all 95 scenario results in CSV format |
| **Update Frequency** | GEP 3.0 released August 2024 |

**Description**: Aims to standardize and simplify the use of geospatial tools to create least-cost electrification plans. The latest version, GEP 3.0, includes a shadow price of carbon in the calculation of each technology solution. Provides a high-level overview of the technology mix (grid, mini-grid, standalone solar) and investment required to achieve universal access by 2030 for each country. The GEP is one of the few energy optimization modelling tools that is open source, publicly available, and freely replicable.

**Limitations**: Scenarios represent high-level pathways, not project-level detail.

### 5.5 Distributed Renewable Energy (DRE) Atlas

| Attribute | Detail |
|-----------|--------|
| **Custodian** | ESMAP / World Bank |
| **Coverage** | 58 countries including Sub-Saharan Africa |
| **Direct Data Link** | `https://dre.energydata.info` |
| **Direct Data Link (Kenya GeoJSON)** | `https://energydata.info/dataset/.../download/kenya_dre_atlas_settlements.pmtiles` |
| **Direct Data Link (Source Cooperative)** | Available on Source Cooperative for wider reach |
| **Update Frequency** | Launched June 2025 |

**Description**: A publicly accessible, web-based, interactive platform offering comprehensive data on settlements in 58 countries. Explore over 60 high-resolution indicators per settlement. Designed for easy navigation, providing detailed insights into communities suitable for the deployment of mini grid and off-grid solar systems. All settlement data is available for download.

**Limitations**: Settlement-level data; not all countries covered.

### 5.6 GDP Raster Data (DRYAD)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | DRYAD / Kummu et al. |
| **Coverage** | Global |
| **Direct Data Link (DRYAD)** | `https://doi.org/10.5061/DRYAD.DK110` |
| **Direct Data Link (NetCDF)** | `GDP_PPP_1990_2015_5arcmin_v2.nc` |
| **Update Frequency** | 1990–2015 (Version 2) |

**Description**: Gridded global datasets for Gross Domestic Product and Human Development Index over 1990–2015. Spatial resolution is 1km, with time range 1990–2015. License: CC0. The data is available as gap-filled multiannual datasets in gridded form for Gross Domestic Product (GDP).

**Limitations**: Ends 2015; extrapolation required for recent years.

### 5.7 IEA World Energy Outlook – Africa Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Africa region |
| **Direct Data Link (Harvard Dataverse)** | `https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VE8IBL` |
| **Direct Data Link (Free Dataset)** | `https://www.iea.org/data-and-statistics/data-product/world-energy-outlook-2024-free-dataset` |
| **Direct Data Format** | EXCEL and .csv files (requires account) |
| **Update Frequency** | Annual |

**Description**: Historical and projected electricity demand, capacity, and generation by region. The WEO-2024 Extended Dataset includes more detailed information at regional and country-level. Free access data is available as EXCEL and .csv files, licensed under CC BY NC SA 4.0.

**Limitations**: Regional aggregation; country-level detail available in WEO data services.

### 5.8 AfDB African Economic Outlook

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank |
| **Coverage** | All Africa |
| **Direct Data Link (AEO 2025)** | `https://www.afdb.org/en/documents/african-economic-outlook-2025` |
| **Direct Data Link (Statistics Portal)** | `https://www.afdb.org/en/knowledge/statistics` |
| **Direct Data Link (HDX)** | `https://data.humdata.org/` (search for "African Economic Outlook") |
| **Update Frequency** | Annual |

**Description**: Provides GDP growth, population, and economic indicators by country. Source: AfDB Statistics Department, IMF World Economic Outlook, and AfDB Development Data Portal Database. The AEO provides short-to-medium term forecasts on the evolution of key macroeconomic indicators for all 54 regional member countries.

**Limitations**: Macroeconomic projections; energy-specific data requires supplementary sources.

### 5.9 Transport Starter Data Kit

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in Data in Brief, 2024) / CCG |
| **Coverage** | Selected countries in Africa, Asia, and South America |
| **Direct Data Link (TDC Portal)** | `https://ckan.transport-data.org/` |
| **Direct Data Link (CCG)** | `https://climatecompatiblegrowth.com/starter-kits/` |
| **Direct Data Link (Zenodo – Botswana)** | `https://zenodo.org/records/6539125` |
| **Direct Data Link (Zenodo – Zambia)** | `https://doi.org/10.5281/ZENODO.10410338` |
| **Update Frequency** | 2024 |

**Description**: Contains historical annual data (1990–2021) on passenger and freight activity, energy intensities, load factors, and vehicle stock, segregated by mode and fuel where available. The Kit contains historical annual data on passenger and freight activity, energy intensities, and other transport-related indicators. Available via the TDC Data Portal with API access.

**Limitations**: Selected countries; not all AU member states covered.

### 5.10 AFREC Industry Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All Africa |
| **Direct Data Link** | `https://au-afrec.org/publications` |
| **Direct Data Link (Database)** | `https://au-afrec.org/` (Africa Energy Database 2024) |
| **Update Frequency** | Annual |

**Description**: Total final consumption by sector including industry. The AFREC Africa Energy Database is a comprehensive collection of statistical data based on production, consumption, imports, and exports of energy resources of the African countries. The 2024 edition represents the 2019 Edition with secondary data collected by international database providers mainly IEA for missing or unsupplied data.

**Limitations**: Industry data collection is ongoing; not all countries report.

---

## 6. Fuel Price and Technology Cost Data

### 6.1 IRENA Renewable Cost Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Renewable Energy Agency |
| **Coverage** | Global, with country-specific data for Africa |
| **Direct Data Link (IRENASTAT)** | `https://www.irena.org/Data/Downloads/IRENASTAT` |
| **Direct Data Link (Costs Report)** | `https://www.irena.org/Publications/2024/Sep/Renewable-Power-Generation-Costs-in-2023` |
| **Update Frequency** | Annual (2025 edition available) |

**Description**: Contains approximately 20,000 utility-scale renewable power generation projects and 13,000 PPA and tender/auction results. Includes information on installed costs, capacity factors, and LCOEs for over 15,000 utility-scale renewable power generation projects. A download link for the data used to produce the charts of the report can be requested online.

**Limitations**: Project-level data; not all African countries represented.

### 6.2 IEA Cost Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Global |
| **Direct Data Link (LCOE Calculator)** | `https://www.iea.org/data-and-statistics/data-tools/levelised-cost-of-electricity-calculator` |
| **Direct Data Link (NEA Report)** | `https://www.oecd-nea.org/` (Projected Costs of Generating Electricity) |
| **Update Frequency** | Annual |

**Description**: The IEA Levelised Cost of Electricity Calculator allows for easy download of all data tables in the report and empowers the user to examine the impact of changing select variables such as the discount rate. The calculator also allows for download of all data tables in the 2020 edition of Projected Costs of Generating Electricity.

**Limitations**: Regional aggregation for some datasets.

### 6.3 Global Petrol Prices

| Attribute | Detail |
|-----------|--------|
| **Custodian** | GlobalPetrolPrices.com |
| **Coverage** | 41 African countries |
| **Direct Data Link (Download)** | `https://www.globalpetrolprices.com/` (download data section) |
| **Direct Data Link (API)** | `https://www.globalpetrolprices.com/api/` |
| **Direct Data Format** | Excel, XML feed |
| **Update Frequency** | Weekly |

**Description**: Gasoline prices spanning eight years (2018–2025). The API provides data on retail fuel prices in 135 countries, electricity prices in 145 countries, and natural gas prices in 48 countries. The values can be downloaded via a simple XML feed or as Excel files. You can download custom data sets in Excel based on a selection of countries, data frequency, and time period.

**Limitations**: Some countries have incomplete data.

### 6.4 UNDP Fuel Retail Price Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | UNDP |
| **Coverage** | Major African countries |
| **Direct Data Link** | `https://www.undp.org/` (search for fuel price data) |
| **Direct Data Link (Bloomberg source)** | Table A.3 in UNDP publications provides fuel retail prices for February–March 2026 |
| **Update Frequency** | Periodic |

**Description**: Fuel retail prices for February–March 2026 period, covering Egypt, Morocco, and others. Provides comparative data on fuel price changes across African nations.

**Limitations**: Not all AU member states covered.

### 6.5 AFREC Africa Energy Database

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All Africa |
| **Direct Data Link** | `https://au-afrec.org/publications` |
| **Direct Data Link (Database)** | `https://au-afrec.org/` (Africa Energy Database 2024) |
| **Update Frequency** | Annual (2019 Edition available) |

**Description**: The AFREC Africa Energy Statistics is a comprehensive collection of statistical data based on production, consumption, imports, and exports of energy resources of the African countries. Largely based on energy data collected by AFREC supplemented with secondary data collected by international database providers mainly IEA for missing or unsupplied data.

**Limitations**: Relies on IEA data for gaps.

### 6.6 IRENA, IEA, EUROSTAT Joint Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | IRENA / IEA / EUROSTAT |
| **Coverage** | Global with Africa coverage |
| **Direct Data Link (EUROSTAT)** | `https://ec.europa.eu/eurostat` |
| **Update Frequency** | Historical data series 2010–2040 |

**Description**: Final consumption of fuels in transport (diesel) with historical data series 2010–2040, measured in TWh. Final consumption of energy used in transport for transformation into final energy.

**Limitations**: Transport-focused; other sectors require supplementary sources.

### 6.7 Fossil Fuel Field Approximation (PyPSA-Earth)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | PyPSA-Earth (derived from global datasets) |
| **Coverage** | Global |
| **Direct Data Link** | `https://github.com/pypsa-meets-earth/pypsa-earth` |
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
| **Direct Data Link** | `https://cmpmwanga.nepad.org/` |
| **Direct Data Download** | Records downloadable in spreadsheet format (Excel and CSV) |
| **Update Frequency** | Continuous updates |

**Description**: Continental Power System Master Plan database containing historical and projected data needed to model future demand for long-term energy planning by power pools. Includes governance framework for regular updates, harmonisation with existing AU databases (AID, AEIS, AEP), and power pool information systems. The Mwanga platform ensures continuous updates, improvement and re-engineering to contain the most up-to-date data.

**Limitations**: Some content may require registration.

### 7.2 African Energy Information System (AEIS)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AFREC |
| **Coverage** | All 55 AU member states |
| **Direct Data Link** | `https://au-afrec.org/aeis` |
| **Direct Data Link (Database)** | `https://au-afrec.org/` |
| **Update Frequency** | Revamped 2020; continuous updates |

**Description**: The AEIS is a decision-making tool comprised of a continental energy database and other energy information and data visualisation tools. Created by AFREC in 2012 to coordinate Africa's energy data collection, validation and dissemination at national, regional and continental level. The system allows collection, processing and validation of African countries' energy statistics through harmonized questionnaires.

**Limitations**: Currently going through a revamp.

### 7.3 African Infrastructure Database (AID)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | 55 African Union Member States |
| **Direct Data Link** | `https://aid.nepad.org/` |
| **Direct Data Link (Export)** | Export options: PDF, Excel, Print |
| **Update Frequency** | Real-time data |

**Description**: Gateway to infrastructure projects in Africa. Search, explore, and analyse thousands of infrastructure projects across the continent. Currently tracks 1,842 total projects across 7 sectors and 55 African Union Member States. Developed by AUDA-NEPAD in 2012, AID is a leading platform dedicated to tracking and analyzing infrastructure projects across Africa.

**Limitations**: Project-level data; not all projects have complete metadata.

### 7.4 Africa Energy Portal (AEP)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Development Bank |
| **Coverage** | All 54 African countries |
| **Direct Data Link** | `https://africa-energy-portal.org/` |
| **Update Frequency** | Regular updates (data spanning 2000–2024) |

**Description**: A one-stop-shop for energy sector news, insights, data and more. Launched in November 2018, the AEP provides country-level electricity sector profiles, market intelligence, policy analysis, research publications, and sector news. The portal is designed to address a lack of information in the sector by providing accurate, reliable, relevant, and up-to-date information on energy in Africa.

**Limitations**: Primarily qualitative and sector-level data.

### 7.5 PIDA (Programme for Infrastructure Development in Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union Commission / AUDA-NEPAD / AfDB |
| **Coverage** | Continental Africa |
| **Direct Data Link (API)** | `https://www.au-pida.org/` (API documentation) |
| **Direct Data Link (AID API)** | `https://aid.nepad.org/` (PIDA API v1) |
| **Direct Data Link (Project Prospectus)** | `https://www.au-pida.org/wp-content/uploads/2023/08/EN-NEPAD-PIDA-PAP2-Project-Prospectus-Web.pdf` |
| **Update Frequency** | Continuous |

**Description**: Priority infrastructure projects including cross-border transmission interconnectors, generation projects, storage, and off-grid systems. The PIDA API provides programmatic access to infrastructure project data across Africa with endpoints for listing projects with pagination and filters. PIDA PAP2 (2021–2030) is the blueprint for achieving the goals of the Second Ten-Year Implementation Plan of Agenda 2063.

**Limitations**: Project pipeline; not all projects have secured financing.

### 7.6 National Integrated Resource Plans (IRPs)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Individual national governments and regulators |
| **Coverage** | Country-specific (e.g., South Africa, Nigeria) |
| **Direct Data Link (South Africa)** | `https://www.dmre.gov.za/` |
| **Direct Data Link (Nigeria)** | `https://www.power.gov.ng/` |
| **Update Frequency** | Periodic (e.g., South Africa IRP 2025) |

**Description**: Planned capacity additions, demand forecasts, and policy targets. South Africa's IRP 2025 was approved by Cabinet on 15 October 2025, adding 105,000 megawatts of new capacity by 2039. Nigeria's NIRP 2024 provides a comprehensive plan for modernising electricity infrastructure.

**Limitations**: Varies by country; not all AU member states have published IRPs.

### 7.7 EU CBAM Data for Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | European Commission / Zenodo |
| **Coverage** | African countries |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "CBAM Africa") |
| **Direct Data DOI** | Available via Nature Scientific Data |
| **Update Frequency** | 2026 (latest) |

**Description**: Data used in chapters on "The EU Carbon Border Adjustment Mechanism as an Incentive for Carbon Pricing in African Countries". The EU CBAM, fully operational since January 2026, requires importers to purchase certificates covering the embedded emissions of goods in six carbon-intensive sectors. All data used and generated for this study are available on Zenodo.

**Limitations**: Trade exposure indices; product-level detail available in underlying data.

### 7.8 IMF Effective Carbon Prices

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Monetary Fund |
| **Coverage** | African countries |
| **Direct Data Link (IMF eLibrary)** | `https://www.elibrary.imf.org/` (Appendix Table 36) |
| **Direct Data Link (IMF Carbon Price Tool)** | `https://www.imf.org/` (Carbon Price Tool) |
| **Update Frequency** | Periodic |

**Description**: Effective carbon prices for 2030 (in USD per tonne CO₂) by fuel type (diesel, gasoline, natural gas, coal, ETS). Appendix Table 36 provides AFR Countries: Effective Carbon Prices, 2030. The IMF Carbon Price Tool allows users to simulate the detailed impact of imposing a carbon price at the industry level.

**Limitations**: Projections; actual prices may differ.

### 7.9 Carbon Pricing Mechanisms Database (Princeton)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Princeton University / Dolphin & Merkle |
| **Coverage** | Global, including Africa |
| **Direct Data Link (GitHub)** | `https://github.com/gdolphin/WorldCarbonPricingDatabase` |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "World Carbon Pricing Database") |
| **Update Frequency** | Periodic (version as of June 20, 2024 available) |

**Description**: Sectoral coverage and prices of carbon pricing mechanisms introduced since 1990. The full dataset is available on GitHub with a version on Zenodo. The World Carbon Pricing Database provides the price level and scope of carbon taxes and ETSs implemented from 1990–2020.

**Limitations**: Academic dataset; may not capture very recent policy changes.

---

## 8. Market and Price Data

### 8.1 SAWEM (South African Wholesale Electricity Market) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Eskom / NTCSA / NERSA |
| **Coverage** | South Africa |
| **Direct Data Link (NTCSA)** | `https://www.ntcsa.co.za/` |
| **Direct Data Link (Market Code)** | `https://www.ntcsa.co.za/` (Market Code Rev 2.3, February 2026) |
| **Update Frequency** | Market Code Rev 2.3 – February 2026 |

**Description**: The SAWEM is being established, representing a fundamental shift from Eskom's historical monopoly as generator. The SAWEM is set to launch in a phased approach in 2026, with full liberalisation by 2031. To participate in SAWEM, businesses must develop API-driven data pipelines capable of communicating with the National Transmission Company South Africa (NTCSA).

**Limitations**: Market is in transition; historical price data limited.

### 8.2 SAPP Database Management System (DMS)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Southern African Power Pool |
| **Coverage** | SAPP member countries |
| **Direct Data Link (Dispa-SET)** | `http://data.europa.eu/89h/d2872591-6ed7-44e0-b7ec-c38850d8c6a6` |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "water-power nexus modelling SAPP") |
| **Direct Data Link (Market Reports)** | `https://www.sapp.co.zw/` |
| **Update Frequency** | Monthly, quarterly, annual reports |

**Description**: Central depository of all data related to planning, project preparation and development, operations, markets, and environment. The Dispa-SET dataset for SAPP provides input datasets and simulation results of the Southern African Power Pool simulations. Market reports include SAPP Market Performance Report with total traded volumes.

**Limitations**: DMS is under development; not yet fully operational.

### 8.3 WAPP Information and Coordination Centre (ICC) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WAPP ICC |
| **Coverage** | WAPP member countries (14 ECOWAS states) |
| **Direct Data Link (ICC)** | `https://icc.ecowapp.org/` |
| **Direct Data Link (Dispa-SET)** | `http://data.europa.eu/89h/f77d3a7d-c75a-432b-bec0-15c8c448e910` |
| **Direct Data Link (openTEPES)** | `https://zenodo.org/records/13863272` |
| **Update Frequency** | Continuous |

**Description**: The WAPP-ICC serves as the central monitoring and electricity trading hub. GE Vernova's GridOS orchestration software has been deployed at the ICC in Abomey-Calavi, Benin, the centralized command center for the ECOWAS interconnected grid. Data includes peak load (14 GW Q3 2023), consumption (28 TWh 2022). The Dispa-SET dataset provides Unit Commitment simulation for WAPP considering hydrological years 1979–2010.

**Limitations**: Some data may require registration.

### 8.4 WAPP openTEPES Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | WAPP / Zenodo |
| **Coverage** | WAPP region |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/13863272` |
| **Direct Data Files** | `oT_Data_Demand_WAPP.csv` (2.3 MB), `oT_Data_Duration_WAPP.csv` (332.0 kB) |
| **Full Dataset** | `openTEPES_WAPP_full.zip` (87.9 MB) |
| **Update Frequency** | October 2026 |

**Description**: Power system transition pathways in the West African Power Pool region performed with the openTEPES model. Includes demand data, node location data, and zone dictionary files. The research is done in dialogue with stakeholder groups in both the EAPP and WAPP regions.

**Limitations**: Model-specific format; requires openTEPES for full utilisation.

### 8.5 EAPP OSeMOSYS Model Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | EAPP / KTH-dESA / Zenodo |
| **Coverage** | EAPP region |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/2428081` |
| **Direct Data File** | `EAPP_reference scenario_datafile.DD` |
| **Model Code** | `https://github.com/KTH-dESA/OSeMOSYS/blob/master/OSeMOSYS_GNU_MathProg/osemosys_short.txt` |
| **Update Frequency** | 2018 (reference scenario) |

**Description**: Data for the Eastern African power pool's energy systems model, developed in OSeMOSYS. The repository consists of `EAPP_reference scenario_datafile.DD`, a model file that needs to be used with the code available in the KTH-dESA/OSeMOSYS GitHub repository. Includes data on climate change, energy systems optimization, OSeMOSYS, and hydropower.

**Limitations**: Reference scenario from 2018; may require updating.

### 8.6 COMELEC Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | COMELEC (North African Power Pool) |
| **Coverage** | Algeria, Libya, Mauritania, Morocco, Tunisia |
| **Direct Data Link** | `https://www.mmeipa.africa-eu-energy-partnership.org/` |
| **Direct Data Link (PIDA)** | `https://au-pida.org/` (North Africa Power Transmission Corridor) |
| **Update Frequency** | Limited public access |

**Description**: COMELEC (Maghreb Electricity Committee) is a body created in June 1974. One of the projects is the 2,700-kilometre high voltage power line from Morocco to Egypt through Algeria. COMELEC has high access rate (96%) and population of 160 million.

**Limitations**: Limited public data access; proxy data from ENERDATA, WDI, and PIDA may be required.

### 8.7 CAPP Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CAPP (Central African Power Pool) |
| **Coverage** | Central African countries |
| **Direct Data Link (PEAC-SIE)** | `https://www.peac-sig.org/` |
| **Direct Data Link (JRC)** | `http://data.europa.eu/89h/063030d6-458c-4817-94e0-f94560f6f11f` |
| **Update Frequency** | Limited public access |

**Description**: Established in 2003 under ECCAS. The PEAC-SIE platform was built within the scope of the Technical Assistance Mission (MAT2) and Capacity Building for the Central Africa Power Pool (CAPP) funded by the European Union. The JRC dataset provides analysis of the water-power nexus in the North, Eastern and Central African Power Pools.

**Limitations**: Limited public data; proxy data required.

### 8.8 ICA Regional Power Status in African Power Pools Report

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Infrastructure Consortium for Africa (ICA) |
| **Coverage** | All five power pools |
| **Direct Data Link** | `https://www.icafrica.org/` |
| **Direct Data Link (2016 Update)** | `https://www.icafrica.org/` (search for "Regional Power Status in Africa Power Pools – 2016 update") |
| **Update Frequency** | 2016 update (latest) |

**Description**: Provides an overview of power pools in Africa as of end 2010, including the most recent key data and relevant information. The report details the progress made in each of the pools and identifies findings, trends, challenges and possible solutions. Covers COMELEC, EAPP, SAPP, CAPP, and WAPP.

**Limitations**: 2016 edition; may not reflect recent developments.

---

## 9. Water and Hydrological Data

### 9.1 FAO Rivers of Africa Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | FAO |
| **Coverage** | Continental Africa |
| **Direct Data Link (FAO Catalog)** | `https://data.apps.fao.org/map/catalog/srv/api/records/b891ca64-4cd4-4efd-a7ca-b386e98d52e8` |
| **Direct Download** | `https://data.apps.fao.org/map/catalog/srv/api/records/b891ca64-4cd4-4efd-a7ca-b386e98d52e8/formatters/xml` |
| **Direct Data Format** | ESRI shapefile (ZIP) |
| **Update Frequency** | 2014 (publication) |

**Description**: The rivers of Africa dataset is derived from the World Wildlife Fund's (WWF) HydroSHEDS drainage direction layer and a stream network layer. Developed as part of a GIS-based information system on water resources for the African continent. The Rivers of Africa dataset is available through the FAO GeoNetwork.

**Limitations**: Static release; may not reflect recent hydrological changes.

### 9.2 FAO Hydrological Basins in Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | FAO |
| **Coverage** | Continental Africa |
| **Direct Data Link (FAO Catalog)** | `https://data.apps.fao.org/catalog//iso/7707086d-af3c-41cc-8aa5-323d8609b2d1` |
| **Direct Download (SDG6)** | `https://data.apps.fao.org/catalog/` (SDG6_FBU_v1_Africa.zip) |
| **Update Frequency** | 2025 (latest update) |

**Description**: Divides the African continent into major hydrological basins and their sub-basins according to hydrological characteristics. Obtained by delineating drainage basin boundaries from hydrologically corrected elevation data (WWF HydroSHEDS and Hydro1K). Developed by the FAO Land and Water Division under the AQUASTAT program.

**Limitations**: Basin-level; sub-basin detail varies.

### 9.3 VegDischarge v1 (AfriDischarge v1)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | CGIAR / UCAR / USGS |
| **Coverage** | Continental Africa |
| **Direct Data Link (USGS)** | `https://doi.org/10.5066/P14H6TFY` |
| **Direct Data Link (ScienceBase)** | `https://www.sciencebase.gov/catalog/item/65d758c4d34ec3e1801d7e02` |
| **Direct Data Dashboard** | `http://afridischarge.iwmi.org/app/` |
| **Update Frequency** | 2024 |

**Description**: High-resolution continental discharge dataset providing monthly and annual discharge estimates for 2001–2021 across more than 64,000 river segments. Total average annual discharge for Africa quantified at 3,271.4 km³/year. The AfriDischarge Dashboard provides map-based exploration, visualization of discharge time series and climatologies, and straightforward data downloads.

**Limitations**: Ends 2021; model-derived rather than observed.

### 9.4 IWMI Africa Geoportal

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Water Management Institute (IWMI) |
| **Coverage** | 10 river basins, 5 countries, 5 regions, and continental Africa |
| **Direct Data Link** | `https://iwmi.africageoportal.com/` |
| **Direct Data Access** | Free and unrestricted access to datasets, dashboards, and tools |
| **Update Frequency** | Launched February 2026 |

**Description**: A dynamic, open-access platform that transforms complex water data into actionable insights. Built on Esri's Geoportal technology, the IWMI Africa Geoportal goes beyond a traditional data repository. Key features include interactive dashboards and maps that visualize water availability and use across Africa. The Geoportal is built on the principles of open science and inclusivity, offering free and unrestricted access to datasets.

**Limitations**: Primarily visualization platform; underlying data may require separate access.

### 9.5 Hydrologic Derivatives for Modeling and Analysis (HDMA)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | US Department of the Interior / USGS |
| **Coverage** | Continental Africa |
| **Direct Data Link (DEM)** | `https://data.usgs.gov/datacatalog/metadata/USGS.65d758c4d34ec3e1801d7e02.xml` |
| **Direct Data Link (Streams)** | `https://catalog.data.gov/` (search for "Africa Streams HDMA") |
| **Direct Data Link (Flow Direction)** | `https://catalog.data.gov/` (search for "Africa Flow Direction HDMA") |
| **Update Frequency** | 2026 (latest release) |

**Description**: Contains the catchments derived from the Digital Elevation Model (DEM) for the African continent. The HDMA database provides comprehensive and consistent global coverage of raster and vector topographically derived layers. Includes streams layers, flow direction, flow accumulation, and compound topographic index. There are 19 processing units for Africa.

**Limitations**: Derived from DEM; accuracy depends on input elevation data.

### 9.6 Nile Basin Initiative Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Nile Basin Initiative |
| **Coverage** | Nile Basin countries |
| **Direct Data Link (NBI)** | `https://nilebasin.org/` |
| **Direct Data Link (Data Service Portal)** | `http://5.175.16.252:8002/` |
| **Direct Data Link (Flood & Drought)** | `https://www.flooddroughtmonitor.com/data` |
| **Update Frequency** | Continuous updates |

**Description**: The Nile Basin Water Quality Database was launched in 2023, centralising data from water quality monitoring campaigns across member countries. The database is fed regularly by NBI member countries and currently contains almost 45,000 physico-chemical analyses. The data service database portal is available on the NBI website. Climate change projections data set for impact studies in Nile Basin is also available.

**Limitations**: Basin-specific; not all African river basins covered.

### 9.7 CMIP6 Climate Projections

| Attribute | Detail |
|-----------|--------|
| **Custodian** | World Climate Research Programme (WCRP) |
| **Coverage** | Global |
| **Direct Data Link (CDS)** | `https://cds.climate.copernicus.eu/datasets/projections-cmip6?tab=download` |
| **Direct Data Link (ESGF)** | `https://esgf.llnl.gov/` |
| **Python API (nex-gddp)** | `pip install nex-gddp` |
| **Update Frequency** | Continuous (CMIP6 archive) |

**Description**: The CMIP6 data archive is distributed through the Earth System Grid Federation (ESGF). A quality-controlled subset of CMIP6 global climate projection data is made available through the Climate Data Store (CDS). The nex-gddp Python package allows downloading NASA NEX-GDDP-CMIP6 climate projection data with spatial and temporal filtering. Available from 48 to 53 models run under each of four main emissions scenarios.

**Limitations**: Model spread; requires downscaling for impact assessment.

---

## 10. Sector Coupling Data

### 10.1 Hydrogen Data

#### 10.1.1 IEA Global Hydrogen Review – Africa

| Attribute | Detail |
|-----------|--------|
| **Custodian** | International Energy Agency |
| **Coverage** | Africa |
| **Direct Data Link** | `https://www.iea.org/reports/global-hydrogen-review-2026` |
| **Direct PDF** | `https://iea.blob.core.windows.net/assets/.../GlobalHydrogenReview2025.pdf` |
| **Update Frequency** | Annual (2026 edition) |

**Description**: Hydrogen use in Africa reached 3.1 Mt in 2024, about 3% of the global total. Hydrogen production accounted for about 6% of the region's gas demand and 2% of regional CO2 emissions. Hydrogen use is concentrated in 6 countries: Egypt (almost half), Algeria (20%), Nigeria (17%), South Africa (5%), Libya (5%), and Equatorial Guinea (3%). The 2026 report includes a special chapter on Africa.

**Limitations**: Country-level detail for 6 countries.

#### 10.1.2 HyAfrica Project Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | HyAfrica Project / Zenodo |
| **Coverage** | Morocco, Mozambique, South Africa, Togo |
| **Direct Data Link (Zenodo Community)** | `https://zenodo.org/communities/hyafrica` |
| **Direct Data Link (Project)** | `https://leap-re.app/` |
| **Update Frequency** | Continuous (project 2022–2025) |

**Description**: HyAfrica is a project investigating natural hydrogen in Africa as a clean energy source, focusing on soil gas measurements and lab analyses in Morocco, Mozambique, South Africa, and Togo. Results show minimal hydrogen in Morocco, significant anomalies in Mozambique (up to ~1%), exceptionally high concentrations in South Africa (up to 4.4%). The HyAfrica Zenodo repository serves as the project's official long-term digital archive. More than 1000 in situ measurements with H₂ detection have been made.

**Limitations**: Four countries only; natural hydrogen resource estimates preliminary.

#### 10.1.3 Green Hydrogen Cost-Potential Data (Sub-Saharan Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in International Journal of Hydrogen Energy, 2025) |
| **Coverage** | Sub-Saharan Africa |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "Comprehensive Techno-Economic Analysis") |
| **Direct Data Link (arXiv)** | `https://arxiv.org/pdf/2408.10184` |
| **Update Frequency** | 2025 |

**Description**: Participatory mapping of local green hydrogen cost-potentials in Sub-Saharan Africa. Results show that hydrogen costs start at 1.6 EUR/kg in Mauritania with a total potential of ~259 TWh/a under 2 EUR/kg in 2050. Aggregate hydrogen potentials in West Africa and combined potentials in Southern and East Africa approximately 200,000 TWh/a.

**Limitations**: Theoretical potentials; project-level feasibility requires further analysis.

#### 10.1.4 African Hydrogen LCOH Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Various (published in Nature Scientific Reports) |
| **Coverage** | 54 African countries |
| **Direct Data Link (GitHub)** | `https://github.com/tarekhemdan/Hydrogen_AI` |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "Mapping cost competitiveness African green hydrogen") |
| **Update Frequency** | 2025 |

**Description**: A harmonized dataset of 54 African scenarios was compiled, with LCOH (EUR/kg) as the target variable and 14 predictors capturing project scale, renewable capacity, storage and transport infrastructure, investment and maturity stage, energy security and sustainability indices. The datasets and associated code are available in the Hydrogen_AI repository. LCOH is modelled for all African countries with access to ports, excluding landlocked countries.

**Limitations**: Scenario-based; not all project configurations represented.

### 10.2 Transport Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | US Energy Information Administration / CCG |
| **Coverage** | Africa (Region) |
| **Direct Data Link (TDC Portal)** | `https://ckan.transport-data.org/` |
| **Direct Data Link (CCG)** | `https://climatecompatiblegrowth.com/starter-kits/` |
| **Update Frequency** | Historical (2005–2035) |

**Description**: Energy Intensity Index for two/three wheel vehicles with data points for 2005, 2015, 2025, and 2035. Energy consumption for 16 regions including Africa. Historical energy intensity data (2004–2018) segregated by mode and fuel, where available, is available via the Transport Data Commons.

**Limitations**: Historical projections; may not reflect current policy.

### 10.3 Industry Sector Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Gas Exporting Countries Forum (GECF) |
| **Coverage** | Africa |
| **Direct Data Link** | `https://www.gecf.org/` |
| **Direct Data Format** | Tables and figures in GECF Annual Gas Market Report 2025 |
| **Update Frequency** | Annual (2026 report) |

**Description**: Africa's gas consumption increased by 4% to 185 bcm in 2025. Africa's natural gas demand is set to more than double by 2050, raising its share to around one-fifth of the continent's total energy mix. GECF projected that Africa's natural gas demand will more than double by 2050, driven by power generation, industrial production, and clean cooking.

**Limitations**: Gas-focused; other industry energy sources require supplementary data.

---

## 11. Power Pool-Specific Data Sources

### 11.1 SAPP (Southern African Power Pool)

| Source | Custodian | Direct Data Link | Content |
|--------|-----------|------------------|---------|
| Dispa-SET SAPP Dataset | JRC / EU Open Data | `http://data.europa.eu/89h/d2872591-6ed7-44e0-b7ec-c38850d8c6a6` | Input datasets and simulation results |
| SAPP Market Reports | SAPP | `https://www.sapp.co.zw/` | Monthly, quarterly market reports |
| Water-Power Nexus SAPP | Zenodo | `https://zenodo.org/records/` | Input datasets and simulation results |

### 11.2 EAPP (Eastern Africa Power Pool)

| Source | Custodian | Direct Data Link | Content |
|--------|-----------|------------------|---------|
| EAPP OSeMOSYS Data | KTH-dESA / Zenodo | `https://zenodo.org/records/2428081` | Reference scenario datafile |
| EAPP Model Code | KTH-dESA / GitHub | `https://github.com/KTH-dESA/OSeMOSYS/blob/master/OSeMOSYS_GNU_MathProg/osemosys_short.txt` | OSeMOSYS model code |

### 11.3 WAPP (West African Power Pool)

| Source | Custodian | Direct Data Link | Content |
|--------|-----------|------------------|---------|
| WAPP ICC Data Portal | WAPP ICC | `https://icc.ecowapp.org/` | Operational data, reliability studies |
| WAPP openTEPES Data | WAPP / Zenodo | `https://zenodo.org/records/13863272` | Demand data, transition pathways |
| Dispa-SET WAPP Dataset | JRC / EU Open Data | `http://data.europa.eu/89h/f77d3a7d-c75a-432b-bec0-15c8c448e910` | Unit Commitment simulation data |

### 11.4 CAPP (Central African Power Pool)

| Source | Custodian | Direct Data Link | Content |
|--------|-----------|------------------|---------|
| PEAC-SIE Platform | CAPP | `https://www.peac-sig.org/` | Real-time information |
| Water-Power Nexus CAPP | JRC / EU Open Data | `http://data.europa.eu/89h/063030d6-458c-4817-94e0-f94560f6f11f` | Water-power nexus analysis |

### 11.5 COMELEC (North African Power Pool)

| Source | Custodian | Direct Data Link | Content |
|--------|-----------|------------------|---------|
| COMELEC Data | COMELEC | `https://www.mmeipa.africa-eu-energy-partnership.org/` | North African electricity data |
| Med-TSO Data | Med-TSO | `https://www.med-tso.org/` | Mediterranean transmission data |

---

## 12. Continental Institutional and Planning Data

### 12.1 CMP (Continental Power System Masterplan) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Direct Data Link** | `https://cmpmwanga.nepad.org/` |
| **Direct Data Download** | Records downloadable in spreadsheet format (Excel and CSV) |
| **Update Frequency** | Ongoing; Phase II validated, Phase III in progress |

**Description**: CMP modelling components, demand forecasts, supply capacity gap projections, investment costs, network studies, and cost-benefit analysis. The Mwanga platform ensures continuous updates, improvement and re-engineering to contain the most up-to-date data. The CMP was initiated in 2019, following a decision of the African Energy Ministers to serve as a blueprint for the African Single Electricity Market (AfSEM).

**Limitations**: Some content may require registration.

### 12.2 AfSEM (African Single Electricity Market) Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union / AUDA-NEPAD |
| **Coverage** | Continental Africa |
| **Direct Data Link (CMP Mwanga)** | `https://cmpmwanga.nepad.org/` |
| **Direct Data Link (AU)** | `https://au.int/` |
| **Update Frequency** | Ongoing |

**Description**: Regulatory harmonization assessments, market readiness, institutional capacity, utilities restructuring, and policy harmonization. AfSEM will be the largest single electricity market globally, covering 55-member states serving a population of over 1.3 billion. The progressive implementation of AfSEM and its full operationalisation by 2040 will make it the largest single electricity market in the world.

**Limitations**: Nascent market; data limited.

### 12.3 PIDA (Programme for Infrastructure Development in Africa)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | African Union Commission / AUDA-NEPAD / AfDB |
| **Coverage** | Continental Africa |
| **Direct Data Link (API)** | `https://www.au-pida.org/` (API documentation) |
| **Direct Data Link (AID)** | `https://aid.nepad.org/` |
| **Direct Data Link (Project Prospectus)** | `https://www.au-pida.org/wp-content/uploads/2023/08/EN-NEPAD-PIDA-PAP2-Project-Prospectus-Web.pdf` |
| **Update Frequency** | Continuous |

**Description**: Priority infrastructure projects including cross-border transmission interconnectors, generation projects, storage, and off-grid systems. The PIDA API provides programmatic access to infrastructure project data across Africa. PIDA PAP 1 brings together 397 infrastructure projects worth $113.49 B in total investment across 53 countries and 6 regions.

**Limitations**: Project pipeline; not all projects have secured financing.

### 12.4 Africa Infrastructure Database (AID)

| Attribute | Detail |
|-----------|--------|
| **Custodian** | AUDA-NEPAD |
| **Coverage** | 55 African Union Member States |
| **Direct Data Link** | `https://aid.nepad.org/` |
| **Direct Data Download** | Export options: PDF, Excel, Print |
| **Update Frequency** | Real-time |

**Description**: AID is an online data management tool for capturing, validating and storing infrastructure projects information in Africa using standard metadata descriptors. Currently tracks 1,842 total projects across 7 sectors and 55 African Union Member States. Access to the African Infrastructure Database can be done through the designated website.

**Limitations**: Project-level data; completeness varies.

---

## 13. Open Modelling Toolbox for Africa (OM4A)

### 13.1 OM4A Toolbox

| Attribute | Detail |
|-----------|--------|
| **Custodian** | Horizon Europe OpenMod4Africa Project (2023–2026) |
| **Coverage** | Continental Africa |
| **Direct Data Link** | `https://africaenergymodels.net/` |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "OM4A ToolBox") |
| **Direct Data Link (GitHub)** | `https://github.com/jonathanhanto/OM4A_GEN` |
| **Update Frequency** | Continuous (project 2023–2026) |

**Description**: The OM4A Toolbox is populated with a suite of open, integrated, state-of-the-art models and a common database including all necessary data for conducting analyses of future energy and power systems in Africa. The Toolbox includes the full model suite, a shared data platform (Scenario Explorer), visualisation tools, training materials, and detailed case studies. Includes openTEPES and OnSSET models.

**Limitations**: Project ends 2026; long-term maintenance plan under development.

### 13.2 LEAP-RE / OASES Project Data

| Attribute | Detail |
|-----------|--------|
| **Custodian** | LEAP-RE / OASES Project (EU-AU Partnership) |
| **Coverage** | Continental Africa |
| **Direct Data Link (Zenodo – Continental)** | `https://zenodo.org/records/` (search for "continental energy system case study Africa IRENA FlexTool") |
| **Direct Data Link (Zenodo – Algeria)** | `https://zenodo.org/records/` (search for "OASES Algeria regional case study") |
| **Direct Data Format** | `.sqlite` database files |
| **Update Frequency** | 2025 |

**Description**: Continental case study using PyPSA-Earth as data source, transformed to IRENA FlexTool model using INES-spec. Includes 80 clusters for Africa continental case, 48 demand nodes. Some countries missing for lack of data: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and Sao Tome and Principe. The case study is one of six case studies published in the OASES project.

**Limitations**: Seven countries missing due to data gaps.

### 13.3 IRENA FlexTool Africa Dataset

| Attribute | Detail |
|-----------|--------|
| **Custodian** | IRENA / OASES Project |
| **Coverage** | Continental Africa |
| **Direct Data Link (Zenodo)** | `https://zenodo.org/records/` (search for "Model and dataset for continental energy system case study in Africa") |
| **Direct Data Format** | `.sqlite` database |
| **Model Code** | `https://github.com/irena-flextool/flextool` |
| **Update Frequency** | February 2025 |

**Description**: This dataset covers an African continental energy system model. It is made for IRENA FlexTool 3. The database can be run with open and free IRENA FlexTool 3 that can be downloaded from GitHub. The continental case study covers an African continental energy system model transformed to IRENA FlexTool using the interoperable energy system data specification INES-spec.

**Limitations**: Simplified model; continental model is high-level.

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

| Data Category | Primary Source(s) | Direct Data Link(s) | Additional Sources Required |
|---------------|-------------------|---------------------|----------------------------|
| Grid Topology | OSM, World Bank | `download.geofabrik.de/africa-latest.osm.pbf`; `purl.stanford.edu/vv645gd4791` | AfDB, ENTSO-E (MENA) |
| Power Plants | powerplantmatching | `github.com/PyPSA/powerplantmatching` | RePP Africa, GEM Tracker, ECOWREX |
| Renewables | ERA5, GWA, GSA | `cds.climate.copernicus.eu`; `globalwindatlas.info/api`; `globalsolaratlas.info/download` | SARAH-2, PVGIS, SWERA |
| Demand | AfDB, AFREC | `data.humdata.org/dataset/african-regional-energy-statistics-2014`; `au-afrec.org/publications` | WorldPop, GEP, DRE Atlas, IEA |
| Fuel Costs | IRENA, IEA | `irena.org/Data/Downloads/IRENASTAT`; `iea.org/data-and-statistics/data-tools/levelised-cost-of-electricity-calculator` | GlobalPetrolPrices, UNDP, AFREC |
| Policy | AUDA-NEPAD, AFREC | `cmpmwanga.nepad.org`; `au-afrec.org/aeis` | AEP, PIDA, CBAM, IMF |
| Market Prices | SAPP, WAPP | `data.europa.eu/89h/d2872591...`; `icc.ecowapp.org` | SAWEM, EAPP, COMELEC |
| Water | FAO, VegDischarge | `data.apps.fao.org`; `doi.org/10.5066/P14H6TFY` | IWMI, HDMA, Nile Basin |
| Hydrogen | IEA, HyAfrica | `iea.org/reports/global-hydrogen-review-2026`; `zenodo.org/communities/hyafrica` | LCOH datasets, cost-potential |
| Transport | Starter Data Kits | `ckan.transport-data.org`; `climatecompatiblegrowth.com/starter-kits/` | OPEC, EIA, CCG |
| Industry | AFREC | `au-afrec.org/publications` | GECF, World Bank |
| Power Pools | SAPP, EAPP, WAPP | `data.europa.eu`; `zenodo.org/records/2428081`; `zenodo.org/records/13863272` | CAPP, COMELEC, ICA |
| Continental | CMP, AfSEM | `cmpmwanga.nepad.org`; `au.int` | PIDA, AID, Mwanga |

This specification provides the complete data foundation for Alea, with each source catalogued with its custodian, coverage, **direct verified link to the actual data file, download endpoint, or API**, and known limitations. This enables systematic data acquisition, validation, and integration into the continental modelling platform without requiring users to search websites again.