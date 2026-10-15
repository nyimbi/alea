# Alea: Per-Country Data Completeness Assessment and Data Links

## Methodology

The completeness status for each country is derived from multiple independent assessments:

1. **OASES Project (LEAP-RE/EU-AU)**: The continental energy system case study for IRENA FlexTool 3 identified seven countries as missing from the dataset due to lack of data: **Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and São Tomé and Príncipe**.

2. **PyPSA-Earth Continental Validation**: A data validation for the entire African continent was performed, confirming that PyPSA-Earth provides power network and installed generation data matching third-party national data with adequate accuracy for most countries.

3. **Global Electrification Platform (GEP) 3.0**: Covers 58 countries, with country-level datasets available for download. GEP country datasets exist for most African countries, including Central African Republic, Chad, Niger, Namibia, Botswana, Kenya, South Africa, Ghana, and others.

4. **DRE Atlas**: Covers settlements in 58 countries, with country-level settlement data available for download, including Liberia, Guinea-Bissau, Comoros, Kenya, and others.

5. **AFREC Africa Energy Database**: Covers all 55 AU member states with annual country data tables by energy source.

6. **World Bank Africa Electricity Grid Map**: Covers all continental African countries and Madagascar.

7. **Country-Specific Portals**: Where available, links to national open data portals and datasets are provided.

**Completeness tiers**:
- **HIGH**: Full GEP, DRE Atlas, AFREC, and grid map coverage; national open data portal available; PyPSA-Earth validated.
- **MEDIUM**: GEP or DRE Atlas coverage; AFREC data available; grid map coverage; limited national open data.
- **LOW**: AFREC and grid map coverage only; no GEP/DRE Atlas; no national portal; data gaps noted in continental studies.
- **CRITICAL**: Identified as missing from continental datasets; proxy data required.

---

## Per-Country Data Completeness Table

### North Africa (COMELEC)

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Algeria** | DZ | MEDIUM | AFREC, World Bank Grid, GEP, IEA, PIDA | AFREC country data: `afrec.au.int`; IEA: `iea.org/countries/algeria`; HDX: `data.humdata.org` |
| **Egypt** | EG | HIGH | AFREC, World Bank Grid, GEP, IEA, OSeMOSYS Egypt dataset, CCG Starter Kit | Zenodo OSeMOSYS Egypt: `zenodo.org/records/14843471`; CCG Starter Kit: `zenodo.org/records/` (Egypt); Africa Energy Portal: `africa-energy-portal.org/country/egypt` |
| **Libya** | LY | MEDIUM | AFREC, World Bank Grid, IEA | AFREC country data: `afrec.au.int`; IEA: `iea.org/countries/libya`; HDX: `data.humdata.org` |
| **Mauritania** | MR | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC country data: `afrec.au.int`; no GEP country page; proxy data required |
| **Morocco** | MA | HIGH | AFREC, World Bank Grid, GEP, IEA, National Open Data Portal | Morocco Open Data: `data.gov.ma`; OME portal: `environnement.gov.ma`; AFREC: `afrec.au.int` |
| **Tunisia** | TN | MEDIUM | AFREC, World Bank Grid, GEP, IEA | AFREC country data: `afrec.au.int`; IEA: `iea.org/countries/tunisia`; HDX: `data.humdata.org` |

### West Africa (WAPP/ECOWAS)

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Benin** | BJ | MEDIUM | AFREC, World Bank Grid, GEP, PyPSA-Earth supported | GEP Benin: `energydata.info`; AFREC: `afrec.au.int` |
| **Burkina Faso** | BF | MEDIUM | AFREC, World Bank Grid, GEP | GEP Burkina Faso: `energydata.info`; AFREC: `afrec.au.int` |
| **Cabo Verde** | CV | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC country data: `afrec.au.int`; no GEP country page; proxy data required |
| **Côte d'Ivoire** | CI | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Côte d'Ivoire: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |
| **Gambia** | GM | MEDIUM | AFREC, World Bank Grid, GEP | GEP Gambia: `energydata.info`; AFREC: `afrec.au.int` |
| **Ghana** | GH | HIGH | AFREC, World Bank Grid, GEP, DRE Atlas, National Open Data Portal, Energy Commission | Ghana Open Data: `data.gov.gh`; Energy Commission: `energycom.gov.gh`; GEP Ghana: `energydata.info` |
| **Guinea** | GN | MEDIUM | AFREC, World Bank Grid, GEP | GEP Guinea: `energydata.info`; AFREC: `afrec.au.int` |
| **Guinea-Bissau** | GW | LOW | AFREC, World Bank Grid, DRE Atlas | DRE Atlas Guinea-Bissau: `energydata.info`; AFREC: `afrec.au.int` |
| **Liberia** | LR | MEDIUM | AFREC, World Bank Grid, GEP, DRE Atlas | DRE Atlas Liberia: `data.amerigeoss.org`; GEP Liberia: `energydata.info` |
| **Mali** | ML | MEDIUM | AFREC, World Bank Grid, GEP | GEP Mali: `energydata.info`; AFREC: `afrec.au.int` |
| **Niger** | NE | MEDIUM | AFREC, World Bank Grid, GEP | GEP Niger: `energydata.info`; AFREC: `afrec.au.int` |
| **Nigeria** | NG | HIGH | AFREC, World Bank Grid, GEP, PyPSA-Earth validated (2060 net-zero study), National Energy Data Bank | Nigeria Energy Data Bank: `databank.energy.gov.ng`; GEP Nigeria: `energydata.info`; Power Plants GeoJSON: `energydata.info` |
| **Senegal** | SN | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Senegal: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |
| **Sierra Leone** | SL | MEDIUM | AFREC, World Bank Grid, GEP | GEP Sierra Leone: `energydata.info`; AFREC: `afrec.au.int` |
| **Togo** | TG | MEDIUM | AFREC, World Bank Grid, GEP | GEP Togo: `energydata.info`; AFREC: `afrec.au.int` |

### Central Africa (CAPP/ECCAS)

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Angola** | AO | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Angola: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |
| **Burundi** | BI | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC country data: `afrec.au.int`; no GEP country page; proxy data required |
| **Cameroon** | CM | MEDIUM | AFREC, World Bank Grid, GEP, Africa Energy Portal | GEP Cameroon: `energydata.info`; Africa Energy Portal: `africa-energy-portal.org/country/cameroon` |
| **Central African Republic** | CF | LOW | AFREC, World Bank Grid, GEP | GEP CAR: `energydata.info`; AFREC: `afrec.au.int` |
| **Chad** | TD | LOW | AFREC, World Bank Grid, GEP | GEP Chad: `energydata.info`; AFREC: `afrec.au.int` |
| **Congo (Republic)** | CG | MEDIUM | AFREC, World Bank Grid, GEP | GEP Congo: `energydata.info`; AFREC: `afrec.au.int` |
| **Congo (DRC)** | CD | MEDIUM | AFREC, World Bank Grid, GEP, major hydro potential | GEP DRC: `energydata.info`; AFREC: `afrec.au.int` |
| **Equatorial Guinea** | GQ | LOW | AFREC, World Bank Grid | AFREC: `afrec.au.int`; no GEP country page; limited data |
| **Gabon** | GA | MEDIUM | AFREC, World Bank Grid, GEP | GEP Gabon: `energydata.info`; AFREC: `afrec.au.int` |
| **São Tomé and Príncipe** | ST | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC country data: `afrec.au.int`; no GEP country page; proxy data required |

### East Africa (EAPP)

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Burundi** | BI | **CRITICAL** | (Listed under Central Africa; EAPP member) | See Central Africa entry |
| **Comoros** | KM | **CRITICAL** | AFREC, World Bank Grid, DRE Atlas; **MISSING** from GEP and OASES continental dataset | DRE Atlas Comoros: `energydata.info`; no GEP country page; proxy data required |
| **Djibouti** | DJ | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC: `afrec.au.int`; no GEP country page; proxy data required |
| **Egypt** | EG | HIGH | (Listed under North Africa; EAPP member) | See North Africa entry |
| **Eritrea** | ER | LOW | AFREC, World Bank Grid | AFREC: `afrec.au.int`; no GEP country page |
| **Ethiopia** | ET | MEDIUM | AFREC, World Bank Grid, GEP, major hydro potential | GEP Ethiopia: `energydata.info`; AFREC: `afrec.au.int` |
| **Kenya** | KE | HIGH | AFREC, World Bank Grid, GEP, DRE Atlas, National Data Portal, KPLC data, County Demand Starter Kit | Kenya Open Data: `opendata.go.ke`; GEP Kenya: `energydata.info`; KPLC: `kplc.co.ke`; Zenodo County Kit: `zenodo.org/records/` (Kenya) |
| **Madagascar** | MG | MEDIUM | AFREC, World Bank Grid, GEP | GEP Madagascar: `energydata.info`; AFREC: `afrec.au.int` |
| **Malawi** | MW | MEDIUM | AFREC, World Bank Grid, GEP | GEP Malawi: `energydata.info`; AFREC: `afrec.au.int` |
| **Mauritius** | MU | MEDIUM | AFREC, World Bank Grid, GEP | GEP Mauritius: `energydata.info`; AFREC: `afrec.au.int` |
| **Mozambique** | MZ | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Mozambique: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |
| **Rwanda** | RW | MEDIUM | AFREC, World Bank Grid, GEP | GEP Rwanda: `energydata.info`; AFREC: `afrec.au.int` |
| **Seychelles** | SC | **CRITICAL** | AFREC, World Bank Grid; **MISSING** from GEP and OASES continental dataset | AFREC: `afrec.au.int`; no GEP country page; proxy data required |
| **Somalia** | SO | LOW | AFREC, World Bank Grid | AFREC: `afrec.au.int`; no GEP country page; limited data |
| **South Sudan** | SS | LOW | AFREC, World Bank Grid, GEP | GEP South Sudan: `energydata.info`; AFREC: `afrec.au.int` |
| **Sudan** | SD | MEDIUM | AFREC, World Bank Grid, GEP | GEP Sudan: `energydata.info`; AFREC: `afrec.au.int` |
| **Tanzania** | TZ | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Tanzania: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |
| **Uganda** | UG | MEDIUM | AFREC, World Bank Grid, GEP, CCG Starter Kit | GEP Uganda: `energydata.info`; CCG Starter Kit: `climatecompatiblegrowth.com/starter-kits/` |

### Southern Africa (SAPP)

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Angola** | AO | MEDIUM | (Listed under Central Africa; SAPP member) | See Central Africa entry |
| **Botswana** | BW | MEDIUM | AFREC, World Bank Grid, GEP, SAPP DMS, CCG Starter Kit (Botswana) | GEP Botswana: `energydata.info`; Zenodo Botswana Starter Kit: `zenodo.org/records/6539125` |
| **Eswatini** | SZ | MEDIUM | AFREC, World Bank Grid, GEP, SAPP DMS | GEP Eswatini: `energydata.info`; AFREC: `afrec.au.int` |
| **Lesotho** | LS | MEDIUM | AFREC, World Bank Grid, GEP, SAPP DMS | GEP Lesotho: `energydata.info`; AFREC: `afrec.au.int` |
| **Malawi** | MW | MEDIUM | (Listed under East Africa; SAPP member) | See East Africa entry |
| **Mozambique** | MZ | MEDIUM | (Listed under East Africa; SAPP member) | See East Africa entry |
| **Namibia** | NA | MEDIUM | AFREC, World Bank Grid, GEP, DRE Atlas, SAPP DMS | GEP Namibia: `data.amerigeoss.org`; DRE Atlas Namibia: `energydata.info` |
| **South Africa** | ZA | **HIGH** | AFREC, World Bank Grid, GEP, DRE Atlas, Eskom Data Portal, Zenodo Techno-Economic Dataset, SAPP DMS, validated by multiple studies | Eskom Data Portal: `eskom.co.za/dataportal/`; Zenodo Dataset: `zenodo.org/records/13710940`; GEP South Africa: `energydata.info`; DataFirst: `datafirst.uct.ac.za` |
| **Zambia** | ZM | MEDIUM | AFREC, World Bank Grid, GEP, SAPP DMS, CCG Starter Kit (Zambia) | GEP Zambia: `energydata.info`; Zenodo Zambia Starter Kit: `zenodo.org/records/` (Zambia) |
| **Zimbabwe** | ZW | MEDIUM | AFREC, World Bank Grid, GEP, SAPP DMS | GEP Zimbabwe: `energydata.info`; AFREC: `afrec.au.int` |

### Other AU Member States

| Country | ISO | Completeness | Available Data Sources | Country-Specific Data Links |
|---------|-----|-------------|------------------------|---------------------------|
| **Sahrawi Arab Democratic Republic** | EH | LOW | AFREC, World Bank Grid | AFREC: `afrec.au.int`; limited data; status disputed |

---

## Summary Statistics

| Completeness Tier | Count | Countries |
|-------------------|-------|-----------|
| **HIGH** | 5 | Egypt, Ghana, Kenya, Morocco, Nigeria, South Africa (6) |
| **MEDIUM** | 32 | Algeria, Angola, Benin, Botswana, Burkina Faso, Cameroon, Congo (Rep.), Congo (DRC), Côte d'Ivoire, Equatorial Guinea, Eritrea, Eswatini, Ethiopia, Gabon, Gambia, Guinea, Lesotho, Liberia, Libya, Madagascar, Malawi, Mali, Mauritius, Mozambique, Namibia, Niger, Rwanda, Senegal, Sierra Leone, Sudan, Tanzania, Togo, Tunisia, Uganda, Zambia, Zimbabwe |
| **LOW** | 8 | Central African Republic, Chad, Equatorial Guinea, Guinea-Bissau, Somalia, South Sudan, Sahrawi Republic |
| **CRITICAL** | 7 | Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, São Tomé and Príncipe |

---

## Data Gaps and Mitigation Strategy

### Priority 1: CRITICAL Countries (7)
These countries are entirely missing from the OASES continental dataset and GEP. Mitigation requires:
- **Proxy demand estimation** using WorldPop population data, GDP rasters, and regional averages from neighbouring countries.
- **Expert elicitation** with national utilities and regional bodies (e.g., CAPP for Burundi, São Tomé).
- **Satellite-based asset detection** using the OASES machine learning models for PV and wind detection.
- **Regional aggregation** until country-level data becomes available.

### Priority 2: LOW Countries (8)
These countries have AFREC and grid map coverage but lack GEP or DRE Atlas. Mitigation:
- **Extend GEP modelling** to these countries using the open-source GEP methodology.
- **Deploy DRE Atlas settlement mapping** where security conditions permit.
- **Use PIDA and AID project data** to supplement infrastructure inventories.

### Priority 3: MEDIUM Countries (32)
These countries have good baseline data but lack high-resolution, validated datasets. Mitigation:
- **National portal engagement** to publish open data (following Ghana, Kenya, South Africa models).
- **CCG Starter Kit expansion** to all medium-tier countries.
- **SAPP/EAPP/WAPP data sharing** through power pool databases.

---

## Regional Data Aggregators

For countries without national portals, the following regional resources provide consolidated data:

| Region | Resource | Direct Link |
|--------|----------|-------------|
| All Africa | AFREC Africa Energy Database | `https://au-afrec.org/publications` |
| All Africa | GEP Country Datasets | `https://energydata.info` |
| All Africa | DRE Atlas Settlement Data | `https://dre.energydata.info` |
| All Africa | World Bank Grid Map | `https://energydata.info` |
| West Africa | ECOWREX Power Plants | `https://www.ecowrex.org/power-plants` |
| SAPP | SAPP Database Management System | `https://www.sapp.co.zw/` |
| WAPP | WAPP ICC Data Portal | `https://icc.ecowapp.org/` |
| EAPP | EAPP OSeMOSYS Dataset | `https://zenodo.org/records/2428081` |
| Continental | CMP Mwanga Database | `https://cmpmwanga.nepad.org/` |
| Continental | OASES Continental Dataset | `https://doi.org/10.5281/zenodo.14843471` |

This per-country assessment enables Alea to systematically prioritise data acquisition, quantify uncertainty, and transparently communicate data quality to stakeholders across all 55 AU member states.