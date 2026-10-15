# Alea Specification

## A Better-Than-COMPASS Continental Energy Market Modelling and Analytics Platform for Africa

---

## 1. Executive Summary

This specification defines **Alea**, an open-source continental energy system modelling and market intelligence platform designed to **surpass the capabilities of Meridian Economics' COMPASS** across all 55 African Union member states. COMPASS currently delivers projections of SAWEM spot prices, renewable capture prices, and PPA benchmarks for South Africa, underpinned by Meridian's proprietary power market modelling suite and grounded in real market dynamics including policy, regulation, technology costs, and carbon pricing, with projections extending to 2060.

Alea extends this capability in five fundamental ways:

1. **Geographic scope**: From one country to 55 AU member states, five regional power pools, and the emerging African Single Electricity Market (AfSEM).
2. **Methodological transparency**: From a closed, proprietary model to a fully open-source, peer-reviewable platform built on PyPSA-Earth, which has already demonstrated data validation for the entire African continent and a 2060 net-zero planning study for Nigeria.
3. **Analytical depth**: From price projections to integrated market simulation, agent-based bidding, stochastic optimisation, and sector-coupled analysis covering hydrogen, transport, industry, and water.
4. **Delivery model**: From a subscription report to an interactive API, dashboard, and scenario database accessible to all African stakeholders.
5. **Institutional alignment**: From a South African focus to full alignment with AUDA-NEPAD's Continental Power System Masterplan (CMP), the AfSEM roadmap, and the five regional power pools.

The platform is designed for use by utilities, regulators, investors, researchers, and policymakers across the continent, and is positioned to become the reference modelling platform for Africa's energy transition.

---

## 2. Introduction

### 2.1 Purpose

This document specifies the functional and non-functional requirements for Alea, a product that extends the open-source PyPSA framework to deliver continental-scale energy market modelling, price forecasting, and investment analytics superior to COMPASS.

### 2.2 Background

COMPASS is Meridian Economics' proprietary power market modelling suite that underpins the annual South Africa Power Market Report. The report provides long-term scenario-based projections of future wholesale power market prices, capture prices for renewable energy, and market pricing curves for shorter-term PPAs, supported by a review of sector developments including market growth, regulatory and market structure evolution, technology costs, carbon pricing, and other factors. Key insights from the September 2025 edition include a 20% drop in battery costs in early 2025, gas losing competitiveness amid rising turbine costs, and carbon tax scenarios causing sharp swings in system marginal prices.

While COMPASS is a sophisticated tool, it is limited to South Africa, closed-source, and delivered as a subscription report. Alea addresses these limitations by providing an open, continental-scale platform that exceeds COMPASS in scope, transparency, and analytical capability.

### 2.3 Goals and Objectives

- **G1**: Deliver continental-scale price projections (wholesale spot, capture prices, PPA benchmarks) for all 55 AU member states to 2060.
- **G2**: Implement a continental market simulation engine covering all five power pools (SAPP, EAPP, WAPP, CAPP, COMELEC) with cross-border trade and AfSEM integration.
- **G3**: Provide stochastic and scenario-based optimisation to quantify uncertainty in fuel prices, carbon taxes, demand growth, and technology costs.
- **G4**: Integrate sector coupling (hydrogen, transport, industry, water) at continental scale.
- **G5**: Deliver commercial analytics including capture rates, PPA curves, risk metrics, and bankability assessments for all African markets.
- **G6**: Provide a modern delivery layer with REST APIs, interactive dashboards, and automated reporting.
- **G7**: Align with AUDA-NEPAD's CMP, AfSEM, and the five regional power pools.

### 2.4 Scope

**In Scope**:
- All 55 AU member states, five regional power pools, and continental interconnections.
- Electricity, hydrogen, transport, industry, and water sectors.
- Market simulation, stochastic optimisation, and commercial analytics.
- Open-source licensing (MIT or similar).
- Integration with PyPSA-Earth, PyPSA-RSA, and existing African data initiatives.

**Out of Scope**:
- Real-time SCADA integration.
- Financial trading execution.
- Legal or regulatory compliance advice.

---

## 3. Competitive Benchmarking: COMPASS vs. Alea

| Capability | COMPASS (Meridian Economics) | Alea |
|---|---|---|
| **Geographic scope** | South Africa only | 55 AU member states, 5 power pools, AfSEM |
| **Model transparency** | Proprietary, closed-source | Open-source, peer-reviewable |
| **Price projections** | SAWEM spot prices to 2060 | Wholesale spot prices, capture prices, PPA benchmarks for all African markets to 2060 |
| **Capture price modelling** | Yes (SAWEM only) | Yes (all markets, with cross-border effects) |
| **PPA benchmarks** | Yes (South Africa) | Yes (all African markets, with currency and regulatory adjustments) |
| **Sector coupling** | Limited | Full (electricity, hydrogen, transport, industry, water) |
| **Market simulation** | Merit-order dispatch | Agent-based bidding, multi-market clearing, cross-border trade |
| **Stochastic optimisation** | Scenario-based | Multi-stage stochastic with CVaR, Monte Carlo, chance constraints |
| **Transmission modelling** | Copper plate | Full AC/DC network with iterative expansion |
| **Delivery model** | Subscription report | API, dashboard, scenario database, automated reports |
| **Institutional alignment** | South African policy | CMP, AfSEM, AU frameworks, all 55 member states |
| **Computational accessibility** | Proprietary | Open-source, deployable on national servers to continental HPC |

---

## 4. Functional Requirements

### 4.1 Continental Data Architecture

#### 4.1.1 Grid Topology

**FR-1.1**: The system shall construct the African transmission network topology from OpenStreetMap (OSM), the World Bank Africa Electricity Grid dataset, and the AfDB Africa Power Plants map.

**FR-1.2**: The system shall model cross-border interconnectors as `Link` components with capacity, impedance, and loss parameters for SAPP, EAPP, WAPP, CAPP, and COMELEC.

**FR-1.3**: The system shall support five spatial resolutions: continental (1 node per country), power-pool, national, provincial, and custom GIS-based.

**FR-1.4**: The system shall incorporate the SAPP–EAPP interconnection and the planned AfSEM link (targeted for 2028).

#### 4.1.2 Generation Data

**FR-1.5**: The system shall use the `powerplantmatching` tool to consolidate GEO, GPD, IRENA, and GEM databases into a single ground-truth dataset for all African countries.

**FR-1.6**: The system shall supplement with the RePP Africa database (1,074 hydro, 1,128 solar, 276 wind plants).

**FR-1.7**: The system shall store each plant's geographic location, carrier, technology, and installation date with confidence scores.

#### 4.1.3 Renewable Resources

**FR-1.8**: The system shall generate hourly renewable profiles for solar PV, onshore wind, offshore wind, and hydro using the `atlite` package with ERA5 reanalysis data.

**FR-1.9**: The system shall integrate Global Wind Atlas, PVGIS, and SWERA data for renewable resource assessment.

**FR-1.10**: The system shall account for land-use constraints using Copernicus land cover and the World Database on Protected Areas.

#### 4.1.4 Demand and Socioeconomic Data

**FR-1.11**: The system shall construct hourly electricity demand profiles for each country using AfDB African Regional Energy Statistics, AFREC African Energy Balance, and WorldPop population data.

**FR-1.12**: The system shall use the Global Electrification Platform (GEP) and DRE Atlas for settlement-level demand estimation across 58 African countries.

**FR-1.13**: The system shall model demand growth aligned with CMP and AfSEM projections, including electrification targets.

#### 4.1.5 Fuel and Cost Data

**FR-1.14**: The system shall incorporate country-specific fuel prices, technology costs, and carbon pricing from IRENA, IEA, and AU sources.

**FR-1.15**: The system shall model green hydrogen cost and export potential for high-potential countries (Morocco, Egypt, Namibia, South Africa, Mauritania).

### 4.2 Continental Market Simulation

#### 4.2.1 Power Pool Integration

**FR-2.1**: The system shall model SAPP as a mature interconnected market with 12 member countries and approximately 80 GW installed capacity.

**FR-2.2**: The system shall model EAPP with 13 member states, natural gas (65% of 54 GW) and large hydro (21% of 17.8 GW).

**FR-2.3**: The system shall model WAPP with 14 ECOWAS member states and the WAPP ICC as Market System Operator.

**FR-2.4**: The system shall model CAPP and COMELEC with proxy data where measured data is unavailable.

**FR-2.5**: The system shall simulate cross-border trade flows, wheeling charges, and transmission loss factors across all power pools.

#### 4.2.2 Market Clearing and Bidding

**FR-2.6**: The system shall implement a day-ahead market clearing module with supply and demand bids for each power pool.

**FR-2.7**: Supply bids shall be represented as generators with marginal costs equal to bid prices; demand bids as loads with willingness-to-pay values.

**FR-2.8**: The system shall model strategic bidding using agent-based approaches, including the AMIRIS framework demonstrated for Eastern Africa electricity markets.

**FR-2.9**: The system shall simulate regulatory interventions such as carbon taxes, capacity markets, and renewable auctions.

**FR-2.10**: The system shall model the unbundling of national utilities (e.g., Eskom into three entities) and the evolution toward competitive market structures.

#### 4.2.3 Capture Price and PPA Analytics

**FR-2.11**: The system shall calculate capture prices (market values) for all generators across all African markets.

**FR-2.12**: Capture rates shall be disaggregated by technology, location, and scenario, accounting for cannibalisation effects.

**FR-2.13**: The system shall derive PPA benchmark curves from simulated wholesale price paths, accounting for contract tenor, indexation, and counterparty risk.

**FR-2.14**: The system shall model contract-for-difference (CfD) structures and their impact on investment decisions.

### 4.3 Stochastic and Scenario Optimisation

**FR-3.1**: The system shall support multi-stage stochastic programming with investment decisions at each stage.

**FR-3.2**: The system shall implement CVaR as an objective term to capture tail risks in price and demand scenarios.

**FR-3.3**: The system shall incorporate uncertainty in gas prices, carbon taxes, renewable costs, and demand growth with explicit probability distributions.

**FR-3.4**: The system shall support scenario generation using Monte Carlo simulation and Latin Hypercube Sampling.

**FR-3.5**: The system shall support rolling-horizon optimisation with myopic foresight.

**FR-3.6**: The system shall implement chance-constrained optimisation for demand satisfaction flexibility, as demonstrated for sub-Saharan Africa.

### 4.4 Sector Coupling

**FR-4.1**: The system shall model electricity, heat, hydrogen, transport, and industrial demand as interconnected energy carriers using PyPSA `Link` and `Store` components.

**FR-4.2**: The system shall include hydrogen production via electrolysis, storage, and reconversion through fuel cells, with the Egypt case demonstrating PV exceeding 35 GW and electrolysis in Suez and Damietta for meeting 16% of EU hydrogen demand.

**FR-4.3**: The system shall model hydrogen pipeline networks and shipping routes for intra-African and export trade.

**FR-4.4**: The system shall model synthetic fuel production for aviation and shipping.

**FR-4.5**: The system shall model industrial demand for hydrogen and synfuels in mining, chemicals, and steel sectors.

### 4.5 Water-Energy Nexus

**FR-5.1**: The system shall model cascaded hydro systems with reservoir dynamics for the Nile, Congo, Niger, Zambezi, and Orange river basins.

**FR-5.2**: The system shall link water availability to thermal plant cooling for coal, gas, and nuclear plants.

**FR-5.3**: The system shall incorporate drought and flood scenarios using CMIP6 climate projections.

**FR-5.4**: The system shall model transboundary water allocation constraints (e.g., Nile Basin Initiative).

### 4.6 Delivery and Interface

#### 4.6.1 API

**FR-6.1**: The system shall provide a REST API for programmatic access to price projections, capture rates, PPA curves, and scenario data.

**FR-6.2**: The API shall support authentication, rate limiting, and versioning, returning JSON and CSV formats.

#### 4.6.2 Dashboard

**FR-6.3**: The system shall provide an interactive continental dashboard visualising generation capacity, transmission network, and resource potential for all 55 AU member states.

**FR-6.4**: Country-level drill-down, power-pool comparison, and scenario exploration tools shall be provided.

**FR-6.5**: Export capabilities for charts, maps, and datasets in multiple formats shall be supported.

#### 4.6.3 Reporting

**FR-6.6**: The system shall generate PDF and HTML reports with charts, tables, and executive summaries, template-driven and customisable.

**FR-6.7**: Reports shall be generated on demand or on a scheduled basis.

#### 4.6.4 Scenario Database

**FR-6.8**: The system shall maintain a version-controlled database of scenarios and results with audit trails and reproducibility.

**FR-6.9**: The database shall be queryable via the API and dashboard.

### 4.7 Institutional Alignment

**FR-7.1**: The system shall align scenario definitions with the Continental Energy Security Policy Framework and ETSAP.

**FR-7.2**: The system shall support the AfSEM implementation roadmap toward 2040.

**FR-7.3**: The system shall contribute to the CMP's phased approach, including Pillar 1 (long-term planning and capacity building) and Pillar 2 (bankable pipeline of CMP projects).

**FR-7.4**: The system shall model regulatory harmonization scenarios across power pools, including the SAPP–EAPP regulatory framework.

**FR-7.5**: The system shall model just transition pathways and universal energy access targets, aligning with Mission 300 objectives.

---

## 5. Non-Functional Requirements

### 5.1 Performance

- **NFR-1.1**: A continental LOPF with 55 nodes and full chronology (8,760 hours) shall solve within 8 hours on a 128-core, 512 GB RAM server.
- **NFR-1.2**: A multi-horizon continental CEP (2025–2060) with 5-year steps shall solve within 48 hours on the same hardware.
- **NFR-1.3**: The API shall respond to queries within 2 seconds for cached results and 60 seconds for on-demand computations.
- **NFR-1.4**: The dashboard shall load and render continental visualisations within 10 seconds.

### 5.2 Scalability

- **NFR-2.1**: The system shall support up to 5,000 nodes and 50,000 generators.
- **NFR-2.2**: The system shall support parallel solving of multiple scenarios using Kubernetes or Slurm.
- **NFR-2.3**: The scenario database shall scale to 50,000 scenarios and 10 TB of results.

### 5.3 Reliability

- **NFR-3.1**: The system shall have an uptime of 99.5% for the API and dashboard.
- **NFR-3.2**: The system shall automatically retry failed solver runs up to 3 times.
- **NFR-3.3**: All errors and warnings shall be logged to a centralised logging service.

### 5.4 Security

- **NFR-4.1**: The API shall use OAuth 2.0 or API keys for authentication.
- **NFR-4.2**: All data in transit shall be encrypted using TLS 1.3.
- **NFR-4.3**: The system shall comply with GDPR, POPIA, and national data protection laws across all 55 AU member states.

### 5.5 Usability

- **NFR-5.1**: The dashboard shall be usable by non-technical users with minimal training.
- **NFR-5.2**: The system shall provide documentation, tutorials, and example notebooks in English, French, Portuguese, and Arabic.
- **NFR-5.3**: Error messages shall be clear and actionable.

### 5.6 Maintainability

- **NFR-6.1**: The codebase shall follow PEP 8 style guidelines.
- **NFR-6.2**: The system shall have automated unit, integration, and regression tests with >80% coverage.
- **NFR-6.3**: The system shall be modular with clear separation of concerns.

### 5.7 Portability

- **NFR-7.1**: The system shall run on Linux, macOS, and Windows.
- **NFR-7.2**: The system shall be deployable via Docker and Conda.
- **NFR-7.3**: The system shall support cloud deployment on AWS, Azure, or GCP.

---

## 6. Data Requirements

### 6.1 Data Sources

| Data Type | Source | Coverage |
|---|---|---|
| Grid topology | OSM, World Bank, AfDB | All Africa |
| Power plants | powerplantmatching, RePP Africa | All Africa |
| Renewables | ERA5, Global Wind Atlas, PVGIS | All Africa |
| Demand | AfDB, AFREC, WorldPop, GEP | All Africa |
| Costs | IRENA, IEA | Global |
| Policy | AUDA-NEPAD, DMRE, NERSA | Continental |
| Market | SAWEM, SAPP, WAPP | Where available |

### 6.2 Data Formats

- **Input**: CSV, Excel, NetCDF, Shapefile, GeoJSON, YAML.
- **Internal**: PyPSA network (NetCDF, HDF5), Pandas DataFrames.
- **Output**: JSON, CSV, PDF, HTML, PNG, SVG.

### 6.3 Data Management

- **FR-8.1**: The system shall use DVC (Data Version Control) for data and model versioning.
- **FR-8.2**: All data shall be stored in open formats (CSV, NetCDF, GeoJSON, Parquet).
- **FR-8.3**: Automated data quality checks and validation rules shall be implemented.
- **FR-8.4**: Data provenance metadata shall be provided for all inputs and outputs.
- **FR-8.5**: Data sharing with AUDA-NEPAD, IRENA, and other continental partners shall be supported.

---

## 7. Validation and Benchmarking

### 7.1 Continental Validation

**FR-9.1**: The system shall benchmark against the IRENA FlexTool continental Africa case study, which uses PyPSA-Earth as its data source.

**FR-9.2**: The system shall compare with CMP modelling results, including expected solar dominance (42% of electricity by 2030) and EAPP diversification trends.

**FR-9.3**: The system shall validate against historical SAWEM prices for South Africa and available market data from SAPP and WAPP.

**FR-9.4**: The system shall backtest against AfDB and AFREC historical energy statistics.

### 7.2 Uncertainty Quantification

**FR-9.5**: The system shall use Monte Carlo simulation for key uncertain parameters.

**FR-9.6**: Confidence intervals for all price, capacity, and emission projections shall be reported.

**FR-9.7**: Sensitivity analysis for critical assumptions and policy parameters shall be conducted.

**FR-9.8**: Uncertainty visualisation in dashboards and reports shall be provided.

### 7.3 Acceptance Criteria

- **AC-1**: The system shall produce price projections within ±15% of COMPASS for South Africa in a common scenario.
- **AC-2**: The system shall solve a continental LOPF within 8 hours on specified hardware.
- **AC-3**: The API shall return results within 2 seconds for cached queries.
- **AC-4**: The dashboard shall be usable by 50 concurrent users without performance degradation.
- **AC-5**: The system shall be validated against at least three independent continental studies.

---

## 8. Deployment and Operations

### 8.1 Hardware Requirements

- **National deployment**: 32 cores, 128 GB RAM for single-country models.
- **Power-pool deployment**: 64 cores, 256 GB RAM for regional models.
- **Continental deployment**: 128+ cores, 512+ GB RAM, GPU acceleration for ML components.
- **Cloud deployment**: Options on AWS, Azure, or GCP for countries without local HPC infrastructure.

### 8.2 Software Requirements

- **OS**: Linux (Ubuntu 22.04 LTS recommended).
- **Python**: 3.10 or later.
- **Dependencies**: PyPSA, PyPSA-Earth, Pandas, NumPy, SciPy, Snakemake, MESA, scikit-learn, TensorFlow/PyTorch, Plotly Dash/Streamlit, FastAPI, PostgreSQL.
- **Solvers**: HiGHS, CBC, Gurobi (optional), CPLEX (optional).

### 8.3 Installation

- **FR-10.1**: The system shall be installable via Conda or Docker.
- **FR-10.2**: An installation script and `docker-compose.yml` for full-stack deployment shall be provided.

### 8.4 Configuration

- **FR-10.3**: The system shall use YAML configuration files.
- **FR-10.4**: Environment variables for secrets shall be supported.
- **FR-10.5**: A configuration wizard shall be provided.

### 8.5 Monitoring

- **FR-10.6**: Prometheus metrics and a Grafana dashboard shall be provided.
- **FR-10.7**: Logging to stdout and files shall be supported.

---

## 9. Documentation and Support

- **FR-11.1**: A user guide, developer guide, and API reference shall be provided.
- **FR-11.2**: Jupyter notebooks for common workflows shall be provided.
- **FR-11.3**: A community forum or Slack channel shall be maintained.
- **FR-11.4**: Commercial support options shall be available.

---

## 10. Roadmap and Phasing

| Phase | Milestone | Duration | Deliverable |
|---|---|---|---|
| 1 | Continental data pipeline (OSM, powerplants, renewables, demand) | 4 months | Data repository with quality scores |
| 2 | National model templates for all 55 AU states | 3 months | Configuration files and initial models |
| 3 | Power pool integration (SAPP, EAPP, WAPP, CAPP, COMELEC) | 4 months | Interconnected pool models |
| 4 | Continental CEP with sector coupling | 5 months | Full continental optimisation |
| 5 | Market simulation and regulatory harmonization | 4 months | Price projections and trade flows |
| 6 | Capture price and PPA analytics | 3 months | Commercial analytics engine |
| 7 | Stochastic optimisation and CVaR | 3 months | Risk analytics |
| 8 | Dashboard, API, and reporting | 4 months | Delivery platform |
| 9 | Capacity building and training | 6 months | Trained planners across all pools |
| 10 | Validation, calibration, and documentation | 3 months | Validated continental model |
| 11 | Production release and maintenance | Ongoing | Live platform |

---

## 11. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data scarcity in CAPP and fragile states | High | High | Use proxy data, expert elicitation, and flag uncertainty |
| Computational cost of continental CEP | High | Medium | Use TSAM, decomposition, and cloud HPC |
| Institutional resistance to open modelling | Medium | Medium | Engage AUDA-NEPAD, IRENA, and power pools early |
| Regulatory fragmentation across pools | High | High | Build flexible market simulation with country-specific rules |
| Funding for capacity building | Medium | High | Partner with AfDB, EU, and GIZ for training programmes |
| Solver licensing costs | Medium | Medium | Prioritise open-source solvers, negotiate academic licences |
| Currency and macroeconomic volatility | High | Medium | Model currency risk in PPA analytics; scenario-based FX assumptions |

---

## 12. How Alea Surpasses COMPASS

### 12.1 Geographic and Institutional Scope

COMPASS covers South Africa only. Alea covers all 55 AU member states, five regional power pools, and the emerging AfSEM, providing a continental perspective that COMPASS cannot offer. This enables analysis of cross-border trade, regional integration, and continental energy security that is essential for the CMP and AfSEM.

### 12.2 Methodological Transparency

COMPASS is proprietary and closed-source. Alea is fully open-source, built on PyPSA-Earth, which has already demonstrated data validation for the entire African continent and a 2060 net-zero planning study for Nigeria. This transparency enables peer review, replication, and trust among stakeholders.

### 12.3 Analytical Depth

COMPASS delivers price projections and capture rates for South Africa. Alea delivers these plus:
- **Agent-based market simulation** for strategic bidding and regulatory intervention analysis, using frameworks like AMIRIS demonstrated for Eastern Africa.
- **Stochastic optimisation** with CVaR, Monte Carlo, and chance constraints, enabling rigorous risk quantification.
- **Sector coupling** covering hydrogen, transport, industry, and water, with demonstrated hydrogen applications for Egypt and Brazil.
- **Water-energy nexus** modelling for Africa's major river basins.
- **Transmission expansion** co-optimisation with generation.

### 12.4 Commercial Analytics

COMPASS provides capture prices and PPA benchmarks for South Africa. Alea provides these for all African markets, with:
- **Currency risk adjustments** for PPA curves.
- **Counterparty risk** modelling.
- **CfD structure** analysis.
- **Portfolio stress-testing** against extreme weather, fuel price shocks, and policy changes.
- **Bankability assessments** for projects across the continent.

### 12.5 Delivery Model

COMPASS is delivered as a subscription report. Alea provides:
- **REST API** for programmatic access.
- **Interactive dashboard** for scenario exploration.
- **Scenario database** with version control and audit trails.
- **Automated reporting** in multiple languages.
- **Open data** for all stakeholders.

### 12.6 Institutional Alignment

COMPASS is aligned with South African policy. Alea is aligned with:
- **AUDA-NEPAD's CMP** for continental electricity planning.
- **AfSEM** for the African Single Electricity Market.
- **AU Common Position** on energy access and transition.
- **Mission 300** for universal energy access.
- **Five regional power pools** for regional integration.

---

## 13. Conclusion

This specification defines Alea, an open-source continental energy system modelling and market intelligence platform that surpasses COMPASS in geographic scope, methodological transparency, analytical depth, commercial analytics, and delivery model. By building on PyPSA-Earth, which has already demonstrated continental-scale data validation and optimisation for Africa, and aligning with AUDA-NEPAD's CMP and the AfSEM roadmap, Alea is positioned to become the reference platform for Africa's energy transition, serving all 55 AU member states, five regional power pools, and the continent as a whole.

---

**End of Specification**