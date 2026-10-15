# Product Specification: Alea

## An Open, Extensible Platform for South African Energy Market Modelling and Analytics

---

## 1. Executive Summary

Alea is a comprehensive extension of the open-source PyPSA framework designed to deliver the full analytical, market-simulation, and commercial-intelligence capabilities required to supersede proprietary tools such as COMPASS. It provides a modular, transparent, and scalable platform for modelling South Africa's energy system across physical, market, and financial dimensions. Alea integrates sector coupling, agent-based market simulation, stochastic optimisation, advanced risk analytics, and a modern delivery layer comprising APIs, dashboards, and automated reporting. The platform is built on open standards, supports reproducible research, and is designed for use by utilities, regulators, investors, and researchers.

---

## 2. Introduction

### 2.1 Purpose

The purpose of this document is to specify the functional and non-functional requirements for Alea, a product that extends the PyPSA optimisation engine to provide a complete energy-market modelling and analytics solution tailored to the South African context.

### 2.2 Background

PyPSA is a powerful open-source tool for power system analysis, but it lacks the market-simulation, stochastic planning, and commercial-intelligence layers needed to produce bankable price forecasts, capture rates, and PPA benchmarks. COMPASS, Meridian Economics' proprietary suite, fills this gap but is closed-source and subscription-based. Alea aims to replicate and surpass COMPASS by building an open, extensible, and transparent alternative.

### 2.3 Goals and Objectives

- **G1**: Extend PyPSA to model the South African power system with full sector coupling (electricity, heat, hydrogen, transport, industry) and water-energy nexus.
- **G2**: Implement a market-simulation layer capable of clearing day-ahead and real-time markets, modelling strategic bidding, and simulating institutional dynamics.
- **G3**: Provide stochastic and scenario-based optimisation to quantify uncertainty and risk.
- **G4**: Deliver commercial analytics including capture prices, PPA benchmarks, and risk metrics.
- **G5**: Provide a modern delivery layer with REST APIs, interactive dashboards, and automated reporting.
- **G6**: Integrate machine learning for forecasting, surrogate modelling, and bidding strategies.
- **G7**: Ensure transparency, reproducibility, and extensibility through open-source development.

### 2.4 Scope

**In Scope**:
- All layers of the architecture described in Section 3.
- South African energy system context (Eskom, SAWEM, REIPPPP, IRP, etc.).
- Open-source licensing (MIT or similar).
- Integration with existing PyPSA workflows and data structures.

**Out of Scope**:
- Real-time SCADA integration.
- Financial trading execution.
- Legal or regulatory compliance advice.

### 2.5 Definitions

| Term | Definition |
|------|------------|
| PyPSA | Python for Power System Analysis |
| COMPASS | Meridian Economics' proprietary power market modelling suite |
| SAWEM | South African Wholesale Electricity Market |
| CEP | Capacity Expansion Planning |
| LOPF | Linear Optimal Power Flow |
| UC | Unit Commitment |
| TSAM | Time Series Aggregation Module |
| ABM | Agent-Based Modelling |
| CVaR | Conditional Value at Risk |
| PPA | Power Purchase Agreement |
| CCUS | Carbon Capture, Utilisation, and Storage |
| REDZ | Renewable Energy Development Zone |
| EAF | Energy Availability Factor |

---

## 3. System Overview

### 3.1 Architecture Layers

Alea is organised into six layers:

```
┌─────────────────────────────────────────────────────┐
│  Layer 5: Delivery & Interface                      │
├─────────────────────────────────────────────────────┤
│  Layer 4: Analytics & Market Intelligence           │
├─────────────────────────────────────────────────────┤
│  Layer 3: Stochastic & Scenario Optimisation        │
├─────────────────────────────────────────────────────┤
│  Layer 2: Market & Institutional Simulation         │
├─────────────────────────────────────────────────────┤
│  Layer 1: Enhanced Physical Modelling               │
├─────────────────────────────────────────────────────┤
│  Layer 0: PyPSA Core (LOPF, CEP, UC)                │
└─────────────────────────────────────────────────────┘
```

### 3.2 Key Components

- **PyPSA Core**: The existing PyPSA engine, extended with custom constraints and components.
- **Sector Coupling Module**: Adds Links and Stores for heat, hydrogen, transport, and industry.
- **Water-Energy Nexus Module**: Models reservoir dynamics and cooling water constraints.
- **CCUS Module**: Represents carbon capture, transport, and storage.
- **Market Simulation Engine**: Clears markets, models bidding, and integrates agent-based behaviour.
- **Stochastic Optimiser**: Supports multi-stage stochastic programming and CVaR.
- **Analytics Engine**: Calculates capture prices, PPA curves, and risk metrics.
- **API Server**: RESTful API for programmatic access.
- **Dashboard**: Interactive web interface for scenario exploration.
- **Report Generator**: Automated PDF/HTML report creation.
- **Scenario Database**: Version-controlled storage of scenarios and results.

### 3.3 Data Flow

1. **Data Ingestion**: Raw data from weather, GIS, cost, demand, and policy sources.
2. **Pre-processing**: Scripts (Snakemake) clean, aggregate, and format data.
3. **Model Building**: PyPSA network is constructed with all components.
4. **Optimisation**: Solver runs LOPF, CEP, or stochastic optimisation.
5. **Post-processing**: Results are analysed, metrics calculated, and scenarios stored.
6. **Delivery**: Results served via API, dashboards, and reports.

---

## 4. Functional Requirements

### 4.1 Layer 0: PyPSA Core Enhancements

- **FR-0.1**: The system shall use PyPSA version 0.26 or later as the core optimisation engine.
- **FR-0.2**: The system shall support linear optimal power flow (LOPF), capacity expansion planning (CEP), and unit commitment (UC).
- **FR-0.3**: The system shall support multi-horizon investment periods with perfect foresight.
- **FR-0.4**: The system shall support rolling-horizon optimisation via `optimize_with_rolling_horizon()`.
- **FR-0.5**: The system shall support both open-source (HiGHS, CBC) and commercial (Gurobi, CPLEX) solvers.

### 4.2 Layer 1: Enhanced Physical Modelling

#### 4.2.1 Sector Coupling

- **FR-1.1**: The system shall model electricity, heat, hydrogen, transport, and industrial demand as interconnected energy carriers using PyPSA `Link` and `Store` components.
- **FR-1.2**: The system shall include hydrogen production via electrolysis, storage, and reconversion through fuel cells.
- **FR-1.3**: The system shall model hydrogen export terminals and pipeline networks.
- **FR-1.4**: The system shall support biomass, synthetic fuels, and direct air capture (DAC).
- **FR-1.5**: The system shall track CO₂ flows through all carriers, including negative emissions.

#### 4.2.2 Water-Energy Nexus

- **FR-1.6**: The system shall model cascaded hydro systems with reservoir dynamics and intra-seasonal variability.
- **FR-1.7**: The system shall link water availability to thermal plant cooling requirements.
- **FR-1.8**: The system shall incorporate drought scenarios and water scarcity constraints.

#### 4.2.3 CCUS

- **FR-1.9**: The system shall model CCUS retrofits for existing coal and gas plants.
- **FR-1.10**: The system shall represent CO₂ transport and storage infrastructure.
- **FR-1.11**: The system shall account for parasitic energy losses in capture processes.

### 4.3 Layer 2: Market & Institutional Simulation

#### 4.3.1 Bidding and Market Clearing

- **FR-2.1**: The system shall implement a day-ahead market clearing module with supply and demand bids.
- **FR-2.2**: Supply bids shall be represented as generators with marginal costs equal to bid prices.
- **FR-2.3**: Demand bids shall be represented as loads with willingness-to-pay values.
- **FR-2.4**: The market shall clear at the intersection of aggregated supply and demand curves.
- **FR-2.5**: The system shall support multiple bidding zones, flow-based market coupling, and NTC constraints.

#### 4.3.2 Agent-Based Modelling (ABM)

- **FR-2.6**: The system shall integrate MESA with PyPSA to simulate generator, retailer, and consumer agents.
- **FR-2.7**: Agents shall exhibit bounded rationality and heterogeneous strategies.
- **FR-2.8**: The system shall model strategic bidding behaviour using game-theoretic or reinforcement learning approaches.
- **FR-2.9**: The system shall simulate regulatory interventions such as carbon taxes, capacity markets, and renewable auctions.

#### 4.3.3 Institutional Dynamics

- **FR-2.10**: The system shall model the unbundling of Eskom into separate generation, transmission, and distribution entities.
- **FR-2.11**: The system shall include entity-level constraints such as separate balance sheets and regulatory mandates.
- **FR-2.12**: The system shall support multiple market structures (monopoly, single buyer, competitive market).

### 4.4 Layer 3: Stochastic & Scenario Optimisation

- **FR-3.1**: The system shall support multi-stage stochastic programming with investment decisions at each stage.
- **FR-3.2**: The system shall implement CVaR as an objective term to capture tail risks.
- **FR-3.3**: The system shall support two-stage stochastic optimisation with investments as first-stage decisions and dispatch as recourse.
- **FR-3.4**: The system shall incorporate uncertainty in gas prices, carbon taxes, renewable costs, and demand growth with explicit probability distributions.
- **FR-3.5**: The system shall support scenario generation using Monte Carlo simulation and Latin Hypercube Sampling.
- **FR-3.6**: The system shall support rolling-horizon optimisation with myopic foresight.

### 4.5 Layer 4: Analytics & Market Intelligence

#### 4.5.1 Capture Prices

- **FR-4.1**: The system shall calculate capture prices (market values) for all generators.
- **FR-4.2**: Capture rates shall be disaggregated by technology, location, and scenario.
- **FR-4.3**: The system shall account for cannibalisation effects as VRE penetration increases.

#### 4.5.2 PPA Benchmarks

- **FR-4.4**: The system shall derive PPA benchmark curves from simulated wholesale price paths.
- **FR-4.5**: Curves shall account for contract tenor, indexation, and counterparty risk.
- **FR-4.6**: The system shall model contract-for-difference (CfD) structures and their impact on investment decisions.

#### 4.5.3 Risk Metrics

- **FR-4.7**: The system shall calculate Value-at-Risk (VaR) and CVaR for asset revenues.
- **FR-4.8**: The system shall stress-test portfolios against extreme weather, fuel price shocks, and policy changes.
- **FR-4.9**: The system shall produce probabilistic forecasts of wholesale prices to 2060.

### 4.6 Layer 5: Delivery & Interface

#### 4.6.1 REST API

- **FR-5.1**: The system shall provide a RESTful API for programmatic access to price projections, capture rates, and scenario data.
- **FR-5.2**: The API shall support authentication, rate limiting, and versioning.
- **FR-5.3**: The API shall return JSON and CSV formats.

#### 4.6.2 Dashboards

- **FR-5.4**: The system shall provide an interactive web dashboard using Plotly Dash or Streamlit.
- **FR-5.5**: The dashboard shall allow users to explore scenarios, adjust parameters, and visualise results.
- **FR-5.6**: The dashboard shall support export of charts and data.

#### 4.6.3 Automated Reporting

- **FR-5.7**: The system shall generate PDF and HTML reports with charts, tables, and executive summaries.
- **FR-5.8**: Reports shall be generated on demand or on a scheduled basis.
- **FR-5.9**: Reports shall be template-driven and customisable.

#### 4.6.4 Scenario Database

- **FR-5.10**: The system shall maintain a version-controlled database of scenarios and results.
- **FR-5.11**: The database shall support audit trails and reproducibility.
- **FR-5.12**: The database shall be queryable via the API and dashboard.

### 4.7 Advanced Capabilities

#### 4.7.1 Machine Learning Integration

- **FR-6.1**: The system shall use LSTM and DNN models for renewable generation forecasting.
- **FR-6.2**: The system shall train surrogate models to approximate PyPSA optimisation results for rapid scenario screening.
- **FR-6.3**: The system shall apply reinforcement learning for optimal bidding strategies in market simulations.

#### 4.7.2 Demand Response & Flexibility

- **FR-6.4**: The system shall model multi-sector demand response with energy-carrier-specific pricing strategies.
- **FR-6.5**: The system shall include electric vehicle smart charging and vehicle-to-grid (V2G) capabilities.
- **FR-6.6**: The system shall model heat pump flexibility with thermal storage and event response.

#### 4.7.3 Transmission Expansion

- **FR-6.7**: The system shall support iterative transmission expansion optimisation with recalculated line impedances.
- **FR-6.8**: The system shall co-optimise generation and transmission under policy constraints.
- **FR-6.9**: The system shall model both AC and DC transmission options.

---

## 5. Non-Functional Requirements

### 5.1 Performance

- **NFR-1.1**: A single-year LOPF with full chronology (8,760 hours) and 159 nodes shall solve within 4 hours on a 64-core, 256 GB RAM server.
- **NFR-1.2**: A multi-horizon CEP (2025–2050) with 5-year steps and full chronology shall solve within 24 hours on the same hardware.
- **NFR-1.3**: The API shall respond to queries within 2 seconds for cached results and 30 seconds for on-demand computations.
- **NFR-1.4**: The dashboard shall load and render visualisations within 5 seconds.

### 5.2 Scalability

- **NFR-2.1**: The system shall support up to 1,000 nodes and 10,000 generators without architectural changes.
- **NFR-2.2**: The system shall support parallel solving of multiple scenarios using job scheduling (e.g., Slurm, Kubernetes).
- **NFR-2.3**: The scenario database shall scale to 10,000 scenarios and 1 TB of results.

### 5.3 Reliability

- **NFR-3.1**: The system shall have an uptime of 99.5% for the API and dashboard.
- **NFR-3.2**: The system shall automatically retry failed solver runs up to 3 times.
- **NFR-3.3**: The system shall log all errors and warnings to a centralised logging service.

### 5.4 Security

- **NFR-4.1**: The API shall use OAuth 2.0 or API keys for authentication.
- **NFR-4.2**: All data in transit shall be encrypted using TLS 1.3.
- **NFR-4.3**: The system shall comply with GDPR and POPIA for data privacy.

### 5.5 Usability

- **NFR-5.1**: The dashboard shall be usable by non-technical users with minimal training.
- **NFR-5.2**: The system shall provide comprehensive documentation, tutorials, and example notebooks.
- **NFR-5.3**: Error messages shall be clear and actionable.

### 5.6 Maintainability

- **NFR-6.1**: The codebase shall follow PEP 8 style guidelines.
- **NFR-6.2**: The system shall have a modular architecture with clear separation of concerns.
- **NFR-6.3**: The system shall have automated unit, integration, and regression tests with >80% coverage.

### 5.7 Portability

- **NFR-7.1**: The system shall run on Linux, macOS, and Windows.
- **NFR-7.2**: The system shall be deployable via Docker and Conda.
- **NFR-7.3**: The system shall not depend on proprietary software except for optional commercial solvers.

---

## 6. Data Requirements

### 6.1 Data Sources

| Data Type | Source | Format |
|-----------|--------|--------|
| Weather | ERA5, SARAH-2 | NetCDF |
| GIS | SAPAD, SACAD, REDZs | Shapefile, GeoJSON |
| Demand | Eskom, IRP | CSV, Excel |
| Costs | NREL, IEA, CSIR | CSV, Excel |
| Policy | DMRE, NERSA | PDF, CSV |
| Market | SAWEM, Eskom | CSV, API |

### 6.2 Data Formats

- **Input**: CSV, Excel, NetCDF, Shapefile, GeoJSON, YAML.
- **Internal**: PyPSA network (NetCDF, HDF5), Pandas DataFrames.
- **Output**: JSON, CSV, PDF, HTML, PNG, SVG.

### 6.3 Data Management

- **FR-7.1**: The system shall use a version-controlled data repository (e.g., DVC).
- **FR-7.2**: The system shall provide data validation and quality checks.
- **FR-7.3**: The system shall support data provenance tracking.

---

## 7. External Interfaces

### 7.1 API Specification

- **Endpoint**: `/api/v1/`
- **Authentication**: API key in header.
- **Methods**: GET, POST, PUT, DELETE.
- **Resources**:
  - `/scenarios`: List, create, retrieve scenarios.
  - `/results`: Retrieve results for a scenario.
  - `/prices`: Get price projections.
  - `/capture-rates`: Get capture rates.
  - `/ppa-benchmarks`: Get PPA curves.
  - `/risk-metrics`: Get VaR/CVaR.

### 7.2 Dashboard Interface

- **Framework**: Plotly Dash or Streamlit.
- **Features**:
  - Scenario selection and parameter adjustment.
  - Interactive maps of the transmission network.
  - Time-series plots of prices, generation, and emissions.
  - Comparison of scenarios.
  - Export to CSV, PNG, PDF.

### 7.3 Reporting Interface

- **Templates**: Jinja2 or similar.
- **Output**: PDF (via WeasyPrint or LaTeX), HTML.
- **Scheduling**: Cron or Airflow.

---

## 8. Validation and Testing

### 8.1 Backtesting

- **FR-8.1**: The system shall backtest against historical SAWEM prices and Eskom dispatch data.
- **FR-8.2**: The system shall calculate error metrics (MAE, RMSE, MAPE) for price forecasts.

### 8.2 Benchmarking

- **FR-8.3**: The system shall benchmark against COMPASS outputs (if accessible) to identify systematic biases.
- **FR-8.4**: The system shall benchmark against other open-source models (PyPSA-Eur, PyPSA-USA).

### 8.3 Unit/Integration Testing

- **FR-8.5**: The system shall have unit tests for all modules.
- **FR-8.6**: The system shall have integration tests for the full workflow.
- **FR-8.7**: The system shall have regression tests for key scenarios.

### 8.4 Acceptance Criteria

- **AC-1**: The system shall produce price projections within ±10% of COMPASS for a common scenario.
- **AC-2**: The system shall solve a full-year LOPF within 4 hours on specified hardware.
- **AC-3**: The API shall return results within 2 seconds for cached queries.
- **AC-4**: The dashboard shall be usable by 10 concurrent users without performance degradation.

---

## 9. Deployment and Operations

### 9.1 Hardware Requirements

- **Minimum**: 16 cores, 64 GB RAM, 1 TB SSD.
- **Recommended**: 64 cores, 256 GB RAM, 4 TB NVMe SSD.
- **Optimal**: 128 cores, 512 GB RAM, 10 TB NVMe SSD, GPU (for ML).

### 9.2 Software Requirements

- **OS**: Linux (Ubuntu 22.04 LTS recommended).
- **Python**: 3.10 or later.
- **Dependencies**: PyPSA, Pandas, NumPy, SciPy, Snakemake, MESA, scikit-learn, TensorFlow/PyTorch, Plotly Dash/Streamlit, FastAPI, PostgreSQL.
- **Solvers**: HiGHS, CBC, Gurobi (optional), CPLEX (optional).

### 9.3 Installation

- **FR-9.1**: The system shall be installable via Conda or Docker.
- **FR-9.2**: The system shall provide an installation script.
- **FR-9.3**: The system shall provide a `docker-compose.yml` for full-stack deployment.

### 9.4 Configuration

- **FR-9.4**: The system shall use YAML configuration files.
- **FR-9.5**: The system shall support environment variables for secrets.
- **FR-9.6**: The system shall provide a configuration wizard.

### 9.5 Monitoring

- **FR-9.7**: The system shall expose Prometheus metrics.
- **FR-9.8**: The system shall provide a Grafana dashboard.
- **FR-9.9**: The system shall log to stdout and files.

---

## 10. Documentation and Support

- **FR-10.1**: The system shall provide a user guide, developer guide, and API reference.
- **FR-10.2**: The system shall provide Jupyter notebooks for common workflows.
- **FR-10.3**: The system shall provide a community forum or Slack channel.
- **FR-10.4**: The system shall provide commercial support options.

---

## 11. Roadmap and Milestones

| Phase | Milestone | Duration |
|-------|-----------|----------|
| 1 | Core PyPSA enhancements and sector coupling | 3 months |
| 2 | Water-energy nexus and CCUS | 2 months |
| 3 | Market simulation engine (bidding, ABM) | 4 months |
| 4 | Stochastic optimisation and CVaR | 3 months |
| 5 | Analytics engine (capture prices, PPA, risk) | 2 months |
| 6 | Delivery layer (API, dashboard, reporting) | 4 months |
| 7 | ML integration and advanced capabilities | 3 months |
| 8 | Validation, testing, and documentation | 3 months |
| 9 | Beta release and user feedback | 2 months |
| 10 | Production release | 1 month |

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Solver performance issues | High | High | Use commercial solvers, decomposition algorithms |
| Data unavailability | Medium | High | Establish data partnerships, use proxies |
| Model validation challenges | High | Medium | Backtest against historical data, peer review |
| Computational resource constraints | Medium | High | Optimise code, use cloud HPC |
| Adoption resistance | Medium | Medium | Engage stakeholders early, provide training |
| Regulatory changes | Low | High | Build flexible scenario framework |

---

## 13. Appendices

### 13.1 Glossary

- **PyPSA**: Python for Power System Analysis
- **COMPASS**: Meridian Economics' proprietary power market modelling suite
- **SAWEM**: South African Wholesale Electricity Market
- **CEP**: Capacity Expansion Planning
- **LOPF**: Linear Optimal Power Flow
- **UC**: Unit Commitment
- **TSAM**: Time Series Aggregation Module
- **ABM**: Agent-Based Modelling
- **CVaR**: Conditional Value at Risk
- **PPA**: Power Purchase Agreement
- **CCUS**: Carbon Capture, Utilisation, and Storage
- **REDZ**: Renewable Energy Development Zone
- **EAF**: Energy Availability Factor

### 13.2 References

1. PyPSA Documentation: https://pypsa.readthedocs.io/
2. PyPSA-RSA Repository: https://github.com/MeridianEconomics/pypsa-rsa
3. PyPSA-Eur: https://github.com/PyPSA/pypsa-eur
4. PyPSA-Earth: https://github.com/pypsa-meets-earth/pypsa-earth
5. MESA: https://mesa.readthedocs.io/
6. TSAM: https://github.com/FZJ-IEK3-VSA/tsam
7. South African IRP 2023: https://www.dmre.gov.za/
8. Eskom Data Portal: https://www.eskom.co.za/

---

**End of Specification**