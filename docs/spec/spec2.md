# Alea Continental Extension Specification

## Pan-African Deployment Architecture for 55 African Union Member States

---

## 1. Executive Summary

This specification extends Alea from a South Africa-focused platform to a **pan-African continental energy system modelling and analytics platform** covering all 55 African Union member states. The extension is built on the proven PyPSA-Earth framework, which already provides global coverage with demonstrated application in Africa. The architecture must accommodate the continent's five regional power pools (SAPP, EAPP, WAPP, CAPP, COMELEC), the African Single Electricity Market (AfSEM), and the Continental Power System Master Plan (CMP), while remaining granular enough to support national-level planning for each member state.

The core design principle is **multi-scale modelling**: a single codebase that can solve at continental, power-pool, national, and sub-national resolutions using the same data pipeline and optimisation engine.

---

## 2. Continental Data Architecture

### 2.1 Grid Topology and Network Data

**Requirement CD-1**: The system shall construct the African transmission network topology from globally available open data, primarily OpenStreetMap (OSM), supplemented by World Bank and AfDB datasets.

PyPSA-Earth already uses OSM as its primary grid topology source, extracting generators, substations, lines, and cables from OSM data. For Africa specifically, the network topology should be extracted primarily from the World Bank Group's dataset, which is based on multiple sources and available at energydata.info. The system shall:

- **CD-1.1**: Download and process OSM data for all 55 AU member states, handling the continent's incomplete grid representation by flagging missing or low-confidence links.
- **CD-1.2**: Incorporate the World Bank's Africa Electricity Grid dataset and the AfDB's Africa Power Plants map to cross-validate and supplement OSM topology.
- **CD-1.3**: Model cross-border interconnectors explicitly as `Link` components with capacity, impedance, and loss parameters, using SAPP, EAPP, WAPP, and CAPP interconnection data.
- **CD-1.4**: Support five spatial resolutions: continental (1 node per country), power-pool (aggregated regions), national (country-level nodes), provincial (sub-national), and custom GIS-based.

### 2.2 Power Plant and Generation Data

**Requirement CD-2**: The system shall use the `powerplantmatching` tool to consolidate multiple global and African power plant databases into a single ground-truth dataset.

The powerplantmatching tool has been successfully employed in Africa and now integrates global data sources including GEO, GPD, IRENA, and GEM databases. The system shall:

- **CD-2.1**: Run powerplantmatching for each African country using GEO, GPD, IRENA, and GEM as input databases, with cleaning, aggregation, and deduplication.
- **CD-2.2**: Store each plant's exact geographic location, carrier, technology, and installation date.
- **CD-2.3**: Supplement with the Renewable Power Plant database for Africa (RePP Africa), which contains records for 1,074 hydro, 1,128 solar, and 276 wind power plants.
- **CD-2.4**: Flag data confidence levels for each plant, with explicit uncertainty bounds for capacity and commissioning date in countries with limited data.

### 2.3 Renewable Resource Data

**Requirement CD-3**: The system shall generate hourly renewable generation profiles for solar PV, onshore wind, offshore wind, and hydro for all African countries using the `atlite` package.

The primary climate data source is ERA5 reanalysis. For Africa, the system shall:

- **CD-3.1**: Use the all-Africa dataset of energy model "supply regions" for solar PV and wind power, which provides spatially explicit renewable potential data.
- **CD-3.2**: Integrate Global Wind Atlas, PVGIS, and SWERA data for renewable resource assessment.
- **CD-3.3**: Generate renewable profiles at hourly resolution (8,760 hours/year) using the `atlite` package, with options for TSAM aggregation for computational efficiency.
- **CD-3.4**: Account for land-use constraints using Copernicus land cover data and the World Database on Protected Areas, excluding arable land, protected areas, and steep terrain.
- **CD-3.5**: Model offshore wind potential using GEBCO bathymetric data and Exclusive Economic Zone (EEZ) boundaries.

### 2.4 Demand and Socioeconomic Data

**Requirement CD-4**: The system shall construct hourly electricity demand profiles for each African country using a combination of measured data, proxies, and statistical models.

- **CD-4.1**: Use the AfDB's African Regional Energy Statistics (51,051 rows, 2000–2014) as a baseline for historical demand and generation data.
- **CD-4.2**: Integrate the African Energy Balance and Indicators from AFREC, which covers all 55 member states and is aligned with international standards.
- **CD-4.3**: Use GDP raster data from DRYAD and WorldPop population data to spatially disaggregate demand within countries.
- **CD-4.4**: Apply the Global Electrification Platform (GEP) and Distributed Renewable Energy (DRE) Atlas for settlement-level demand estimation across 58 African countries.
- **CD-4.5**: Model demand growth scenarios aligned with the CMP and AfSEM projections, including electrification targets and industrial demand growth.

### 2.5 Fuel and Cost Data

**Requirement CD-5**: The system shall incorporate country-specific fuel prices, technology costs, and carbon pricing for all African countries.

- **CD-5.1**: Use IRENA and IEA cost databases for technology capital costs, O&M costs, and fuel prices, with country-specific adjustments for transport and logistics.
- **CD-5.2**: Model fossil fuel availability and pricing using the approximation approach in PyPSA-Earth, which approximates the location of existing fossil fuel fields without detailed field-level data.
- **CD-5.3**: Include carbon pricing scenarios aligned with the AU Common Position on energy access and transition, including carbon border adjustment mechanism (CBAM) implications for exports.
- **CD-5.4**: Support green hydrogen cost modelling for countries with export potential, using the PyPSA-Earth sector-coupled framework demonstrated for Global South countries.

---

## 3. Power Pool and Regional Integration

### 3.1 Five Regional Power Pools

**Requirement PP-1**: The system shall model all five African power pools as interconnected regional markets, each with its own regulatory framework, market structure, and operational rules.

The five pools are SAPP (Southern Africa), EAPP (Eastern Africa), WAPP (Western Africa), CAPP (Central Africa), and COMELEC (North Africa). The system shall:

- **PP-1.1**: Model SAPP as a mature, interconnected market with 12 member countries, nine of which are interconnected, with installed capacity of approximately 80 GW and operating capacity of about 48 GW.
- **PP-1.2**: Model EAPP as a developing market with 13 member states, currently dominated by natural gas (65% of 54 GW) and large hydro (21% of 17.8 GW), with expected diversification toward renewables.
- **PP-1.3**: Model WAPP with 14 interconnected ECOWAS member states and the WAPP Information and Coordination Center (ICC) serving as Market System Operator.
- **PP-1.4**: Model CAPP as the least developed pool with minimal cross-border trade and limited infrastructure, using proxy data where measured data is unavailable.
- **PP-1.5**: Model COMELEC as the North African pool, with specific attention to the Egypt–Libya–Tunisia–Algeria–Morocco interconnection and potential links to European markets.

### 3.2 Cross-Pool Interconnections

**Requirement PP-2**: The system shall model interconnections between power pools, including the SAPP–EAPP link and the planned AfSEM interconnections.

The SAPP–EAPP MoU signed in February 2026 establishes a structured framework for regulatory harmonization, market monitoring, and infrastructure coordination. The system shall:

- **PP-2.1**: Model the SAPP–EAPP interconnection with capacity, loss, and wheeling charge parameters.
- **PP-2.2**: Model the planned AfSEM linking SAPP to EAPP going live by 2028.
- **PP-2.3**: Model the Continental Power System Master Plan (CMP) vision of a fully connected African grid linking all five power pools by 2040.
- **PP-2.4**: Support scenario analysis for incremental interconnection build-out, including HVDC and HVAC options.

### 3.3 Market Structure Simulation

**Requirement PP-3**: The system shall simulate different market structures across the five power pools, from bilateral contracts to spot markets.

- **PP-3.1**: Model SAPP's competitive market structure with day-ahead and real-time markets.
- **PP-3.2**: Model EAPP's transition from bilateral to market-based trading.
- **PP-3.3**: Model WAPP's emerging market structure with the ICC as market operator.
- **PP-3.4**: Model CAPP and COMELEC's predominantly bilateral structures with future market development scenarios.
- **PP-3.5**: Implement cross-border wheeling charges, transmission loss factors, and regulatory harmonization constraints.

---

## 4. National Model Parametrization

### 4.1 Country-Specific Configuration

**Requirement NM-1**: The system shall support country-specific configuration files for all 55 AU member states, specifying national parameters, policy constraints, and data sources.

Each country model shall include:

- **NM-1.1**: National demand profiles, load shapes, and growth trajectories.
- **NM-1.2**: Installed capacity inventory by technology, age, and efficiency.
- **NM-1.3**: Planned capacity additions from national IRPs and utility plans.
- **NM-1.4**: Fuel supply constraints, including import dependencies and domestic production.
- **NM-1.5**: Renewable resource potential at national and sub-national resolution.
- **NM-1.6**: Transmission constraints and planned grid expansions.
- **NM-1.7**: Policy instruments including feed-in tariffs, auctions, tax incentives, and carbon pricing.
- **NM-1.8**: Electrification targets and access deficit constraints.

### 4.2 Data Quality and Uncertainty

**Requirement NM-2**: The system shall implement a data quality scoring system that quantifies uncertainty for each country and each data category.

- **NM-2.1**: Assign confidence scores (High/Medium/Low) to each data input based on source reliability and completeness.
- **NM-2.2**: Propagate uncertainty through the optimisation using scenario weighting or stochastic parameters.
- **NM-2.3**: Flag countries with significant data gaps (e.g., CAPP members, fragile states) and apply conservative assumptions with explicit documentation.
- **NM-2.4**: Provide a data quality dashboard showing coverage and confidence by country and category.

### 4.3 Language and Localization

**Requirement NM-3**: The system shall support configuration and reporting in English, French, Portuguese, and Arabic, reflecting the AU's working languages.

- **NM-3.1**: Provide configuration file templates in all four languages.
- **NM-3.2**: Support country name and region name localization in dashboards and reports.
- **NM-3.3**: Provide documentation and training materials in at least English and French.

---

## 5. Continental Optimisation Capabilities

### 5.1 Multi-Scale Solving

**Requirement CO-1**: The system shall solve optimisation problems at four spatial scales using the same codebase and data pipeline.

- **CO-1.1**: **Continental scale**: 1 node per country (55 nodes), solving for least-cost generation and transmission expansion across Africa.
- **CO-1.2**: **Power pool scale**: Aggregated regions within each pool, solving for pool-level optimisation.
- **CO-1.3**: **National scale**: Country-level nodes with sub-national resolution for large countries (e.g., Nigeria, Ethiopia, DRC).
- **CO-1.4**: **Project scale**: Sub-national nodes for specific investment decisions, using custom GIS boundaries.

The PyPSA-Earth framework already supports this multi-scale approach, with the Africa continental case study using 80 clusters.

### 5.2 Sector Coupling at Continental Scale

**Requirement CO-2**: The system shall extend sector coupling to the continental scale, modelling electricity, hydrogen, synthetic fuels, and industrial demand across Africa.

The PyPSA-Earth sector-coupled framework has been demonstrated for hydrogen applications in Global South countries. The system shall:

- **CO-2.1**: Model green hydrogen production, storage, and export from high-potential countries (e.g., Morocco, Egypt, Namibia, South Africa, Mauritania).
- **CO-2.2**: Model hydrogen pipeline networks and shipping routes for intra-African and export trade.
- **CO-2.3**: Model synthetic fuel production for aviation and shipping, aligned with the Continental Framework on Electric Mobility and aviation resilience.
- **CO-2.4**: Model industrial demand for hydrogen and synfuels in mining, chemicals, and steel sectors.

### 5.3 Water-Energy Nexus at Continental Scale

**Requirement CO-3**: The system shall model the water-energy nexus across Africa's major river basins, including the Nile, Congo, Niger, Zambezi, and Orange.

- **CO-3.1**: Model cascaded hydro systems with reservoir dynamics and intra-seasonal variability for all major African river basins.
- **CO-3.2**: Link water availability to thermal plant cooling for coal, gas, and nuclear plants.
- **CO-3.3**: Incorporate drought and flood scenarios using climate model projections (CMIP6).
- **CO-3.4**: Model transboundary water allocation constraints using international agreements (e.g., Nile Basin Initiative).

---

## 6. Institutional and Policy Integration

### 6.1 African Union Frameworks

**Requirement IP-1**: The system shall align with and support the implementation of AU energy frameworks and initiatives.

- **IP-1.1**: Align scenario definitions with the Continental Energy Security Policy Framework and its recommendations.
- **IP-1.2**: Support the Energy Transition Strategy and Action Plan (ETSAP) domestication across member states.
- **IP-1.3**: Align with the AU Common Position on energy access and transition.
- **IP-1.4**: Support the AfSEM implementation roadmap toward 2040.
- **IP-1.5**: Contribute to the CMP's phased approach: Phase I baseline study, Phase II expertise and platform, and Phase III capacity building.

### 6.2 Regulatory Harmonization

**Requirement IP-2**: The system shall model regulatory harmonization scenarios across power pools and countries.

- **IP-2.1**: Model the regulatory readiness assessments being conducted for AfSEM, including institutional capacity, utilities restructuring, and policy harmonization.
- **IP-2.2**: Model the SAPP–EAPP regulatory harmonization framework, including market monitoring procedures, access rules, and sanctions frameworks.
- **IP-2.3**: Model the impact of harmonized technical standards, grid codes, and interconnection rules.

### 6.3 Just Transition and Energy Access

**Requirement IP-3**: The system shall model just transition pathways and universal energy access targets.

- **IP-3.1**: Model universal electricity access scenarios, including grid extension, mini-grids, and stand-alone systems.
- **IP-3.2**: Use the EA-MiniGrid-Bench dataset for solar mini-grid viability assessment across East Africa.
- **IP-3.3**: Model the socioeconomic impacts of energy transition scenarios, including employment, GDP, and energy poverty metrics.
- **IP-3.4**: Align with Mission 300 objectives for universal energy access.

---

## 7. Delivery and Interface

### 7.1 Pan-African Dashboard

**Requirement DI-1**: The system shall provide an interactive continental dashboard visualising energy system scenarios for all 55 AU member states.

- **DI-1.1**: Interactive map of Africa showing generation capacity, transmission network, and resource potential by country.
- **DI-1.2**: Country-level drill-down with national dashboards showing demand, supply, prices, and emissions.
- **DI-1.3**: Power-pool comparison views showing cross-border trade flows and market integration.
- **DI-1.4**: Scenario exploration tools allowing users to adjust key parameters and visualise results.
- **DI-1.5**: Export capabilities for charts, maps, and datasets in multiple formats.

### 7.2 API for Continental Access

**Requirement DI-2**: The system shall provide a REST API for programmatic access to continental and country-level data and results.

- **DI-2.1**: Endpoints for country-level price projections, capture rates, and capacity mix.
- **DI-2.2**: Endpoints for power-pool-level trade flows and market prices.
- **DI-2.3**: Endpoints for continental-level scenarios and CMP alignment metrics.
- **DI-2.4**: Authentication and rate limiting appropriate for national and regional stakeholders.

### 7.3 Capacity Building and Training

**Requirement DI-3**: The system shall include a comprehensive capacity building programme for African energy planners and researchers.

- **DI-3.1**: Align with the IRENA Eastern Africa Regional Model Analysis & Planning Support Programme, which delivers an 18-month regional training programme for 50 participants.
- **DI-3.2**: Contribute to the Energy Modelling Platform for Africa (EMP-A) network of energy planning and research hubs.
- **DI-3.3**: Provide open-source training materials, tutorials, and example notebooks.
- **DI-3.4**: Establish a continental network of certified trainers across all five power pools.

---

## 8. Computational and Deployment Strategy

### 8.1 Hardware Requirements

**Requirement CD-4**: The system shall support deployment on a range of computing infrastructures, from national servers to continental HPC clusters.

- **CD-4.1**: National deployment: 32 cores, 128 GB RAM for single-country models.
- **CD-4.2**: Power-pool deployment: 64 cores, 256 GB RAM for regional models.
- **CD-4.3**: Continental deployment: 128+ cores, 512+ GB RAM, GPU acceleration for ML components.
- **CD-4.4**: Cloud deployment options on AWS, Azure, or GCP for countries without local HPC infrastructure.

### 8.2 Solver Strategy

**Requirement CD-5**: The system shall support both open-source and commercial solvers, with automatic selection based on problem size and complexity.

- **CD-5.1**: Use HiGHS or CBC for national-level LOPF problems.
- **CD-5.2**: Use Gurobi or CPLEX for continental CEP and stochastic optimisation.
- **CD-5.3**: Implement Benders decomposition or Lagrangian relaxation for large-scale stochastic problems.
- **CD-5.4**: Provide solver-agnostic interfaces to avoid vendor lock-in.

### 8.3 Data Management

**Requirement CD-6**: The system shall implement a continental data repository with version control, provenance tracking, and quality assurance.

- **CD-6.1**: Use DVC (Data Version Control) for data and model versioning.
- **CD-6.2**: Store all data in open formats (CSV, NetCDF, GeoJSON, Parquet).
- **CD-6.3**: Implement automated data quality checks and validation rules.
- **CD-6.4**: Provide data provenance metadata for all inputs and outputs.
- **CD-6.5**: Support data sharing with AUDA-NEPAD, IRENA, and other continental partners.

---

## 9. Validation and Benchmarking

### 9.1 Continental Validation

**Requirement VB-1**: The system shall be validated against existing continental modelling initiatives and historical data.

- **VB-1.1**: Benchmark against the IRENA FlexTool continental Africa case study, which uses PyPSA-Earth as its data source and models renewable-only investment scenarios to 2030.
- **VB-1.2**: Compare with the CMP modelling results, including the expected solar dominance (42% of electricity by 2030) and EAPP diversification trends.
- **VB-1.3**: Validate against historical SAWEM prices for South Africa and available market data from SAPP and WAPP.
- **VB-1.4**: Backtest against AfDB and AFREC historical energy statistics.

### 9.2 Uncertainty Quantification

**Requirement VB-2**: The system shall quantify and report uncertainty in all continental projections.

- **VB-2.1**: Use Monte Carlo simulation for key uncertain parameters (fuel prices, demand growth, technology costs).
- **VB-2.2**: Report confidence intervals for all price, capacity, and emission projections.
- **VB-2.3**: Conduct sensitivity analysis for critical assumptions and policy parameters.
- **VB-2.4**: Provide uncertainty visualisation in dashboards and reports.

---

## 10. Roadmap and Phasing

| Phase | Milestone | Duration | Deliverable |
|-------|-----------|----------|-------------|
| 1 | Continental data pipeline (OSM, powerplants, renewables, demand) | 4 months | Data repository with quality scores |
| 2 | National model templates for all 55 AU states | 3 months | Configuration files and initial models |
| 3 | Power pool integration (SAPP, EAPP, WAPP, CAPP, COMELEC) | 4 months | Interconnected pool models |
| 4 | Continental CEP with sector coupling | 5 months | Full continental optimisation |
| 5 | Market simulation and regulatory harmonization | 4 months | Price projections and trade flows |
| 6 | Dashboard, API, and reporting | 4 months | Delivery platform |
| 7 | Capacity building and training | 6 months | Trained planners across all pools |
| 8 | Validation, calibration, and documentation | 3 months | Validated continental model |
| 9 | Production release and maintenance | Ongoing | Live platform |

---

## 11. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Data scarcity in CAPP and fragile states | High | High | Use proxy data, expert elicitation, and flag uncertainty |
| Computational cost of continental CEP | High | Medium | Use TSAM, decomposition, and cloud HPC |
| Institutional resistance to open modelling | Medium | Medium | Engage AUDA-NEPAD, IRENA, and power pools early |
| Regulatory fragmentation across pools | High | High | Build flexible market simulation with country-specific rules |
| Funding for capacity building | Medium | High | Partner with AfDB, EU, and GIZ for training programmes |
| Solver licensing costs | Medium | Medium | Prioritise open-source solvers, negotiate academic licences |

---

## 12. Conclusion

This specification defines a pan-African extension of Alea that leverages the proven PyPSA-Earth framework, existing continental data initiatives, and institutional partnerships with AUDA-NEPAD, IRENA, AfDB, and the five regional power pools. The system is designed to support the African Single Electricity Market, the Continental Power System Master Plan, and national energy planning for all 55 AU member states. By building on open data, open-source software, and transparent methodologies, Alea can become the reference modelling platform for Africa's energy transition, providing the analytical foundation for a unified, sustainable, and equitable continental energy system.