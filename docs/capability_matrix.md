# Alea: Comprehensive Capabilities Coverage Matrix

## The Definitive Reference for the Most Featureful and Capable Version of the Platform

**Version**: 1.0 — Aspirational Target State
**Purpose**: To define, exhaustively and measurably, every capability the platform shall possess when fully realised, across every dimension that matters: analytical, geographic, user, channel, technological, data, validation, integration, and non-functional.
**Audience**: Product strategists, engineering leads, investors, partner institutions, regulators.
**Companion Documents**: Alea Product Specification v4.0, PRG Specification, Definitive Parameter Catalog, Per-Country Data Completeness Assessment.

---

## How to Read This Matrix

Every capability is scored on the **Alea Maturity Model (L0–L5)**:

| Level | Name | Definition | Evidence Required |
|---|---|---|---|
| **L0** | Specified | Documented in a specification; no implementation exists. | Specification section reference |
| **L1** | Prototype | Proof-of-concept implementation; works for one case. | Demo, notebook, unit test |
| **L2** | Functional | Works for a defined class of cases; limited validation. | Integration test, internal validation report |
| **L3** | Production | Full functionality; documented; deployed; supported. | Production SLA, user documentation, monitoring |
| **L4** | Validated | Independently validated against historical data or peer-reviewed benchmarks. | Validation report, backtest, peer-reviewed publication |
| **L5** | Best-in-class | Exceeds global benchmarks; sets the reference standard. | Comparative study against global best-in-class tools |

Every capability is scored on **six coverage dimensions**:

| Dimension | Symbol | Meaning |
|---|---|---|
| **Analytical** | A | Depth and rigour of the analytical method |
| **Geographic** | G | Coverage across the 55 AU member states and 5 power pools |
| **User** | U | Coverage across the 20 user archetypes |
| **Channel** | C | Delivery across the 18 delivery channels |
| **Data** | D | Coverage of the required data sources |
| **Validation** | V | Degree of independent validation |

Each cell is a maturity level (L0–L5).

---

## Part I: Capability Domains

The platform comprises **eighteen capability domains**, each with sub-capabilities. The domains are ordered from foundational (data) through analytical (modelling) to delivery (interfaces) and governance.

| # | Domain | Sub-Capabilities | Primary Users |
|---|---|---|---|
| 1 | **Data Acquisition & Ingestion** | Static sources, real-time feeds, crowdsourcing, partner exchange | All |
| 2 | **Parameter Relationship Graph (PRG)** | DSL, graph, equations, consistency, propagation, conflict, feedback, translation | Analysts, Developers |
| 3 | **Planning Core** | Capacity expansion, unit commitment, transmission expansion, multi-horizon | Planners, Utilities |
| 4 | **Sector Coupling** | Electricity, hydrogen, heat, transport, industry, water | Planners, Industry |
| 5 | **Renewable Technologies** | Solar, wind, hydro, geothermal, biomass, marine, CSP, hydrogen | Developers, Planners |
| 6 | **Market Simulation** | Agent-based bidding, market clearing, capture prices, PPA benchmarks | Traders, Regulators |
| 7 | **Stochastic Optimisation** | Two-stage, CVaR, chance constraints, Monte Carlo, efficient frontiers | Investors, Planners |
| 8 | **Outage Prediction** | VIIRS detection, weather-driven, predictive maintenance, cascade, restoration | Utilities, Regulators |
| 9 | **Loss Mitigation** | Loss decomposition, TLENS, mitigation ranking, resilience metrics | Utilities, Regulators |
| 10 | **What-If Engine** | Parameter exploration, propagation, scenario comparison, frontiers, sensitivity | All |
| 11 | **Intelligence Scanning** | News, tenders, social media, LLM extraction, human review | Journalists, Analysts |
| 12 | **Reporting** | Daily, weekly, monthly, quarterly, annual, custom | All |
| 13 | **Delivery Interfaces** | REST, GraphQL, WebSocket, dashboard, mobile, bots, widgets, SDKs, portal, webhooks, email, RSS, BI, GIS | All |
| 14 | **Data Management** | Metadata, time series, spatial, object storage, versioning, provenance | All |
| 15 | **Security & Governance** | Auth, authorization, rate limiting, audit, privacy, compliance | All |
| 16 | **Validation & QA** | Backtesting, cross-model, peer review, regression, property, uncertainty | All |
| 17 | **User Experience** | Dashboards, visualisations, documentation, training, support | All |
| 18 | **Operations** | Monitoring, logging, alerting, deployment, scaling | Operators |

---

## Part II: Master Capability Coverage Matrix

This is the central matrix. Each row is a capability; each column is a coverage dimension. Maturity is scored per cell.

### Domain 1: Data Acquisition & Ingestion

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Static source connectors (news RSS, tender portals, institutional feeds) | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| Real-time streaming connectors (X/Twitter, WebSocket feeds) | L3 | L3 | L3 | L2 | L3 | L2 | **L3** |
| Satellite data ingestion (VIIRS, ERA5, Sentinel) | L4 | L4 | L4 | L3 | L5 | L4 | **L4** |
| Automated source discovery (new feeds) | L2 | L2 | L2 | L1 | L2 | L1 | **L2** |
| Crowdsourced outage reporting (WhatsApp, USSD, SMS, app) | L4 | L3 | L5 | L5 | L3 | L3 | **L4** |
| Partner data exchange (SFTP, API, data-sharing agreements) | L3 | L3 | L4 | L2 | L4 | L3 | **L3** |
| OCR and PDF extraction (gazettes, IRPs, tenders) | L3 | L3 | L3 | L2 | L3 | L2 | **L3** |
| Multilingual ingestion (EN, FR, PT, AR, SW, HA, YO, AM) | L3 | L4 | L4 | L3 | L4 | L2 | **L3** |
| Data quality scoring and provenance | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Rate limiting and backoff for external APIs | L4 | L4 | L4 | L2 | L4 | L3 | **L4** |

### Domain 2: Parameter Relationship Graph (PRG)

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| DSL: parser, evaluator, differentiator, renderers (LaTeX/Unicode/source/MathML) | L5 | L5 | L4 | L3 | L4 | L4 | **L5** |
| Graph: nodes, edges, equations, loading, validation | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Equation library: 20 systems, ~120,000 constraints | L3 | L3 | L4 | L2 | L3 | L3 | **L3** |
| Type system: Pydantic models, ranges, units, roles | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| Unit checking (dimensional consistency) | L2 | L2 | L3 | L2 | L3 | L2 | **L2** |
| Consistency engine: residual checks, relative tolerance | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Propagation engine: topological sort, phase splitting | L5 | L5 | L4 | L3 | L4 | L4 | **L5** |
| Feedback solver: iterative, convergence, damping | L5 | L5 | L4 | L3 | L4 | L4 | **L5** |
| Conflict detector: over/under/direct/cycle detection | L1 | L1 | L2 | L1 | L1 | L1 | **L1** |
| Correction suggestions: ranked, sensitivity-based | L1 | L1 | L2 | L1 | L1 | L1 | **L1** |
| Translation layer: PyPSA, Linopy, Pyomo, SymPy | L1 | L1 | L2 | L1 | L1 | L1 | **L1** |
| Cross-validation rules: severity, messages, suggestions | L2 | L2 | L2 | L1 | L2 | L2 | **L2** |
| Persistence: YAML, PostgreSQL, GraphML | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Incremental updates: dirty-set tracking, caching | L0 | L0 | L0 | L0 | L0 | L0 | **L0** |
| Type inference from equations | L0 | L0 | L0 | L0 | L0 | L0 | **L0** |

### Domain 3: Planning Core

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Linear optimal power flow (LOPF) with four formulations | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |
| Unit commitment (MILP, big-M, linearised) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Transmission loss approximation (secant, tangent) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Spatial clustering (k-means, HAC, modularity, Voronoi) | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |
| Temporal aggregation (TSAM, representative days) | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |
| Multi-horizon investment with perfect foresight | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Rolling-horizon optimisation (myopic foresight) | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| Iterative transmission expansion (SLP) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| N-1 security-constrained dispatch | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| N-2 contingency analysis | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Reserve margin constraints | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Inertia constraints | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |

### Domain 4: Sector Coupling

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Electricity sector | L5 | L5 | L5 | L3 | L5 | L5 | **L5** |
| Hydrogen value chain (electrolysis, storage, pipelines, export) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Heat sector (heat pumps, district heating, thermal storage) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Transport sector (EVs, V2G, hydrogen vehicles, SAF) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Industry sector (steel H₂-DRI, cement CCUS, ammonia, mining) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Water-energy nexus (cooling, desalination, irrigation, transboundary) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Additionality constraint for hydrogen | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Multi-carrier optimisation (Links, Stores) | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |

### Domain 5: Renewable Technologies

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Solar PV (fixed, tracking, rooftop, utility-scale) | L5 | L5 | L5 | L3 | L5 | L5 | **L5** |
| Concentrated solar power (parabolic trough, central receiver, storage) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Onshore wind (multiple turbine classes) | L5 | L5 | L5 | L3 | L5 | L5 | **L5** |
| Offshore wind (fixed, floating) | L4 | L3 | L4 | L3 | L4 | L3 | **L3** |
| Geothermal (flash steam, binary cycle, EGS) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Hydropower (RoR, reservoir, PHS, small hydro, cascade) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Biomass (solid, biogas, liquid) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Marine energy (wave, tidal, OTEC) | L2 | L2 | L2 | L1 | L2 | L2 | **L2** |
| Green hydrogen | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Renewable integration (curtailment, inertia, stability) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |

### Domain 6: Market Simulation

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Agent-based market model (AMIRIS) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Reinforcement learning bidding (ASSUME, MATD3) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Day-ahead market clearing | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Real-time market clearing | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Intraday and balancing markets | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Capture price calculation | L5 | L5 | L5 | L4 | L5 | L5 | **L5** |
| PPA benchmark curves | L4 | L4 | L5 | L4 | L4 | L4 | **L4** |
| Cross-border trade and market coupling | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Capacity markets | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Ancillary services markets | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| CfD and contract modelling | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |

### Domain 7: Stochastic Optimisation

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Two-stage stochastic programming | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| CVaR risk-averse optimisation | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Multi-stage stochastic programming | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Chance-constrained optimisation | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Monte Carlo simulation | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Latin Hypercube Sampling | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Copula-based scenario generation | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Efficient frontier generation | L4 | L4 | L5 | L3 | L4 | L4 | **L4** |
| Climate risk integration (CMIP6) | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |

### Domain 8: Outage Prediction

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| VIIRS Black Marble ingestion and correction | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| OWL-I outage detection (deconfounding, neural calibration) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Weather-driven outage forecasting (RF, XGBoost, LightGBM) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Predictive maintenance (Cox PHM, CNN-LSTM) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Cascade simulation (LODF-based) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Restoration sequencing optimisation | L2 | L2 | L2 | L1 | L2 | L2 | **L2** |
| Cross-validation against GridWatch | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Probabilistic outage forecasting with confidence intervals | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |

### Domain 9: Loss Mitigation

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Loss decomposition (load, generation, topology, weather) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Power flow tracing (Proportional Sharing Principle) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| TLENS critical line identification | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Mitigation option ranking (cost-benefit) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Resilience metrics (ENS, EENS, SAIDI, SAIFI, LOLP) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |

### Domain 10: What-If Engine

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Parameter exploration (784 parameters, 28 categories) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Change propagation via PRG | L5 | L5 | L5 | L4 | L5 | L5 | **L5** |
| Scenario comparison (side-by-side) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Efficient frontier generation | L4 | L4 | L5 | L4 | L4 | L4 | **L4** |
| Sensitivity analysis | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Multi-objective optimisation (ε-constraint, AUGMECON) | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Rapid re-solve with warm-starting and caching | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Feedback loop solving in what-if | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |

### Domain 11: Intelligence Scanning

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| News and media monitoring (RSS, API, scraping) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Tender and procurement detection | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Social media monitoring (X, Facebook, LinkedIn) | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| Institutional and regulatory monitoring | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| LLM-based signal extraction | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Near-duplicate detection (MinHash LSH) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Human review and validation workflow | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Signal-to-model-update integration | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |

### Domain 12: Reporting

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Daily reports (outage, weather, prices, alerts) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Weekly reports (outlook, market, losses, critical lines) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Monthly reports (market, capacity, outage statistics) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Quarterly reports (outlook, pipeline, scenarios) | L3 | L3 | L4 | L4 | L3 | L3 | **L3** |
| Annual reports (continental outlook, CMP alignment) | L3 | L3 | L4 | L4 | L3 | L3 | **L3** |
| Custom report generation | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Multi-language reporting (EN, FR, PT, AR) | L3 | L4 | L4 | L4 | L3 | L3 | **L3** |
| Report distribution (email, API, dashboard, S3) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |

### Domain 13: Delivery Interfaces

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| REST API | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| GraphQL API | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| WebSocket streaming | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Web dashboard | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| Mobile applications (iOS, Android) | L3 | L3 | L4 | L5 | L3 | L3 | **L3** |
| WhatsApp bot | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| USSD interface | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| SMS interface | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| Voice interface | L3 | L3 | L5 | L5 | L3 | L3 | **L3** |
| Embeddable widgets | L3 | L3 | L4 | L4 | L3 | L3 | **L3** |
| SDKs (Python, R, JavaScript, Java) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Bulk data portal | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Webhooks | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Email and RSS | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Spreadsheet add-ons (Google Sheets, Excel) | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| BI connectors (Power BI, Tableau) | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| GIS plugins (QGIS, ArcGIS) | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |

### Domain 14: Data Management

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Metadata store (PostgreSQL) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Time-series store (TimescaleDB) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Spatial store (PostGIS) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Object storage (MinIO, S3-compatible) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Caching (Redis) | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Version control (DVC, git) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Provenance tracking | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Data quality scoring | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Data lineage and audit trails | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |

### Domain 15: Security & Governance

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Authentication (API key, OAuth 2.0, JWT, magic link) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Authorization (RBAC, fine-grained scopes) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Rate limiting (tiered, token bucket) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Audit logging | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Data privacy (GDPR, POPIA compliance) | L3 | L4 | L3 | L3 | L3 | L3 | **L3** |
| Multi-tenancy | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| Key rotation and secret management | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |

### Domain 16: Validation & QA

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Unit tests (per module) | L5 | L5 | L4 | L3 | L5 | L5 | **L5** |
| Integration tests (end-to-end) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Regression tests (scenario reproducibility) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Property-based tests (Hypothesis) | L3 | L3 | L4 | L2 | L3 | L3 | **L3** |
| Backtesting against historical data | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Cross-model comparison (vs. PyPSA-Earth, OSeMOSYS, Calliope, PLEXOS) | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Peer review (academic publication) | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |
| Uncertainty quantification | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Independent third-party validation | L2 | L2 | L3 | L2 | L2 | L2 | **L2** |

### Domain 17: User Experience

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Interactive dashboards (role-based) | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| Data visualisation (charts, maps, 3D) | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| Documentation (user, developer, API) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Tutorials and notebooks | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Training and certification | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Community forum | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Support (community, commercial) | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| Multi-language support (EN, FR, PT, AR, SW, HA, YO, AM) | L3 | L4 | L4 | L4 | L3 | L2 | **L3** |
| Accessibility (WCAG compliance) | L2 | L2 | L4 | L3 | L2 | L2 | **L2** |

### Domain 18: Operations

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| Monitoring (Prometheus) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Logging (structured, centralized) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Alerting (PagerDuty) | L3 | L3 | L4 | L4 | L3 | L3 | **L3** |
| Deployment (Docker, Kubernetes) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Scaling (horizontal, auto) | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Backup and recovery | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Disaster recovery | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| SLA and uptime guarantees | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |

---

## Part III: User Coverage Matrix

This matrix shows how well each capability domain serves each of the 20 user archetypes. Cell values are maturity levels.

| Domain | Utility | Regulator | IPP | Investor | DFI | Bank | Large Consumer | SME | Household | City | Journalist | NGO | Humanitarian | Healthcare | Education | Researcher | Insurance | Carbon Trader | Telecom | Mining |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Data & Ingestion** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L4 | L4 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 |
| **PRG** | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L2 | L4 | L3 | L3 | L3 | L3 | L4 | L4 | L4 | L4 | L3 | L3 |
| **Planning Core** | L5 | L4 | L4 | L4 | L4 | L3 | L4 | L3 | L2 | L4 | L3 | L3 | L3 | L3 | L4 | L5 | L4 | L3 | L3 | L3 |
| **Sector Coupling** | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L2 | L2 | L3 | L3 | L3 | L3 | L3 | L4 | L4 | L3 | L3 | L3 | L3 |
| **Renewables** | L5 | L4 | L5 | L4 | L4 | L4 | L4 | L3 | L3 | L4 | L3 | L4 | L4 | L3 | L4 | L5 | L4 | L3 | L3 | L4 |
| **Market Sim** | L4 | L4 | L5 | L5 | L4 | L4 | L4 | L3 | L3 | L4 | L3 | L3 | L3 | L3 | L4 | L4 | L4 | L4 | L4 | L3 |
| **Stochastic** | L4 | L4 | L4 | L5 | L5 | L4 | L4 | L3 | L2 | L4 | L3 | L3 | L3 | L3 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Outage Pred** | L5 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L4 | L5 | L4 | L4 | L4 |
| **Loss Mitigation** | L5 | L5 | L4 | L4 | L4 | L4 | L3 | L2 | L2 | L4 | L3 | L3 | L3 | L3 | L3 | L4 | L4 | L3 | L3 | L3 |
| **What-If** | L4 | L4 | L4 | L5 | L4 | L4 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Intelligence** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L4 | L5 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Reporting** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L4 | L5 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Delivery** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L5 | L5 | L4 | L5 | L5 | L5 | L5 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Data Mgmt** | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L2 | L4 | L4 | L4 | L4 | L3 | L4 | L5 | L4 | L4 | L4 | L4 |
| **Security** | L4 | L4 | L4 | L4 | L4 | L5 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L5 | L4 | L4 | L4 |
| **Validation** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L3 | L4 | L4 | L4 | L4 | L3 | L5 | L5 | L4 | L4 | L4 | L4 |
| **UX** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Operations** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 |

**Average maturity by user archetype**:

| User | Average |
|---|---|
| Utility | L4.4 |
| Regulator | L4.2 |
| IPP Developer | L4.3 |
| Investor | L4.4 |
| DFI | L4.2 |
| Commercial Bank | L4.0 |
| Large Consumer | L3.9 |
| SME | L3.4 |
| Household | L3.1 |
| City Government | L4.0 |
| Journalist | L4.1 |
| NGO | L3.9 |
| Humanitarian | L3.9 |
| Healthcare | L3.5 |
| Education | L4.1 |
| Researcher | L4.5 |
| Insurance | L4.1 |
| Carbon Trader | L3.9 |
| Telecom | L3.8 |
| Mining | L3.8 |

**Highest served**: Researcher (L4.5), Utility and Investor (L4.4)
**Lowest served**: Household (L3.1), SME (L3.4), Healthcare (L3.5)

The household and SME gaps reflect the platform's analytical depth, which serves professionals more completely than citizens. Closing these gaps requires the delivery channels (WhatsApp, USSD, mobile) to reach their full L5 maturity.

---

## Part IV: Geographic Coverage Matrix

This matrix shows coverage across the five African power pools and the five UN sub-regions.

| Capability | North Africa | West Africa | Central Africa | East Africa | Southern Africa | Continental |
|---|---|---|---|---|---|---|
| **Data: Grid topology** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Data: Generation assets** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Data: Renewables** | L5 | L5 | L4 | L5 | L5 | L5 |
| **Data: Demand** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Data: Fuel & costs** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Data: Water** | L3 | L3 | L3 | L4 | L4 | L3 |
| **Data: Policy** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Planning** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Sector coupling** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Market simulation** | L4 | L4 | L2 | L4 | L5 | L4 |
| **Outage prediction** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Loss mitigation** | L4 | L4 | L3 | L4 | L4 | L3 |
| **What-if** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Reporting** | L4 | L4 | L3 | L4 | L5 | L4 |
| **Delivery** | L4 | L4 | L3 | L4 | L5 | L4 |

**Key**: L5 = South Africa, L4 = North/West/East/Southern Africa, L3 = Central Africa, L2 = CAPP-specific gaps.

**Central Africa** is consistently the weakest region due to documented data scarcity (CAPP member states: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, São Tomé and Príncipe were identified as missing from continental datasets).

---

## Part V: Delivery Channel Matrix

This matrix shows how well each capability domain is delivered through each channel.

| Domain | REST API | GraphQL | WebSocket | Dashboard | Mobile | WhatsApp | USSD | SMS | Voice | Widgets | SDKs | Data Portal | Webhooks | Email/RSS | Sheets/Excel | BI | GIS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Data & Ingestion** | L4 | L2 | L3 | L3 | L2 | L2 | L2 | L2 | L2 | L2 | L4 | L4 | L3 | L4 | L3 | L3 | L3 |
| **PRG** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L2 | L4 | L3 | L2 | L2 | L3 | L3 | L2 |
| **Planning** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L3 | L4 | L4 | L2 | L3 | L4 | L4 | L3 |
| **Sector Coupling** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L2 | L4 | L4 | L2 | L3 | L3 | L3 | L2 |
| **Renewables** | L4 | L3 | L2 | L4 | L3 | L2 | L2 | L2 | L2 | L4 | L4 | L5 | L3 | L4 | L4 | L4 | L5 |
| **Market Sim** | L4 | L3 | L3 | L4 | L3 | L2 | L2 | L2 | L2 | L3 | L4 | L4 | L3 | L4 | L4 | L4 | L2 |
| **Stochastic** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L2 | L4 | L3 | L2 | L3 | L3 | L3 | L2 |
| **Outage Pred** | L4 | L3 | L4 | L5 | L5 | L5 | L5 | L5 | L4 | L4 | L4 | L4 | L4 | L5 | L3 | L3 | L4 |
| **Loss Mitigation** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L2 | L4 | L3 | L2 | L3 | L3 | L3 | L3 |
| **What-If** | L4 | L3 | L3 | L5 | L3 | L2 | L2 | L2 | L2 | L3 | L4 | L4 | L3 | L4 | L4 | L4 | L3 |
| **Intelligence** | L4 | L3 | L4 | L4 | L3 | L3 | L2 | L3 | L2 | L3 | L4 | L4 | L4 | L5 | L3 | L3 | L2 |
| **Reporting** | L4 | L3 | L2 | L4 | L3 | L3 | L2 | L3 | L3 | L3 | L4 | L4 | L3 | L5 | L3 | L3 | L2 |
| **Data Mgmt** | L4 | L3 | L3 | L4 | L3 | L2 | L2 | L2 | L2 | L3 | L4 | L5 | L3 | L4 | L3 | L3 | L4 |
| **Security** | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L4 | L3 | L4 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Validation** | L4 | L3 | L2 | L4 | L2 | L1 | L1 | L1 | L1 | L2 | L5 | L5 | L2 | L3 | L3 | L3 | L3 |

**Most mature channels**: Dashboard, REST API, SDKs, Data Portal, Email/RSS — all L4+.
**Least mature channels**: Voice, USSD, SMS, WhatsApp for analytical domains — L1–L2.

This reflects the reality that conversational and low-bandwidth channels are ideal for simple queries (outage forecast, price check) but cannot deliver the full analytical depth of the platform. That is a correct design decision, not a gap — but it means the L5 ambition for household service requires further investment in channel-specific UX.

---

## Part VI: Technology Coverage Matrix

This matrix shows coverage across every generation and storage technology.

| Technology | Resource Data | Cost Data | Planning | Dispatch | Market | Outage | Validation |
|---|---|---|---|---|---|---|---|
| **Solar PV (fixed)** | L5 | L5 | L5 | L5 | L5 | L4 | L5 |
| **Solar PV (tracking)** | L5 | L5 | L5 | L5 | L5 | L4 | L5 |
| **Solar PV (rooftop)** | L4 | L4 | L4 | L4 | L4 | L4 | L3 |
| **CSP (parabolic trough)** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **CSP (central receiver)** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Onshore wind** | L5 | L5 | L5 | L5 | L5 | L4 | L5 |
| **Offshore wind (fixed)** | L4 | L4 | L4 | L4 | L4 | L3 | L3 |
| **Offshore wind (floating)** | L3 | L3 | L3 | L3 | L3 | L3 | L2 |
| **Geothermal (flash)** | L4 | L3 | L3 | L4 | L4 | L4 | L3 |
| **Geothermal (binary)** | L3 | L3 | L3 | L4 | L4 | L4 | L3 |
| **Geothermal (EGS)** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **Hydropower (RoR)** | L4 | L4 | L4 | L4 | L4 | L3 | L4 |
| **Hydropower (reservoir)** | L4 | L4 | L4 | L5 | L4 | L4 | L4 |
| **Pumped-storage hydro** | L4 | L4 | L4 | L5 | L4 | L4 | L4 |
| **Small hydro** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Biomass (solid)** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Biogas** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Liquid biofuels** | L3 | L3 | L3 | L3 | L3 | L3 | L2 |
| **Marine (wave)** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **Marine (tidal)** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **Marine (OTEC)** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **Coal** | L5 | L5 | L5 | L5 | L5 | L5 | L5 |
| **Gas (CCGT)** | L5 | L5 | L5 | L5 | L5 | L5 | L5 |
| **Gas (OCGT)** | L5 | L5 | L5 | L5 | L5 | L5 | L5 |
| **Oil** | L4 | L4 | L4 | L4 | L4 | L4 | L4 |
| **Nuclear** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Battery (Li-ion)** | L5 | L5 | L5 | L5 | L5 | L4 | L5 |
| **Battery (flow)** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Battery (NaS)** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Hydrogen (electrolysis)** | L4 | L4 | L4 | L4 | L4 | L3 | L4 |
| **Hydrogen (storage)** | L4 | L4 | L4 | L4 | L4 | L3 | L3 |
| **Hydrogen (pipeline)** | L3 | L3 | L3 | L3 | L3 | L2 | L3 |
| **Hydrogen (export)** | L4 | L4 | L4 | L4 | L4 | L3 | L4 |
| **Thermal storage** | L3 | L3 | L3 | L3 | L3 | L3 | L3 |
| **Gravity storage** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **CAES** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |
| **Flywheel** | L2 | L2 | L2 | L2 | L2 | L2 | L2 |

**Most mature**: Solar, wind, battery, coal, gas, hydro, hydrogen — the technologies that drive the African energy transition.
**Least mature**: Marine, EGS geothermal, gravity storage, CAES, flywheel — long-term or niche technologies.

---

## Part VII: Data Source Coverage Matrix

This matrix shows coverage across the major data source categories.

| Data Category | Coverage | Primary Sources | Maturity | Validation |
|---|---|---|---|---|
| **Grid topology** | 55/55 countries | OSM, World Bank, AfDB | L4 | L4 |
| **Generation assets** | 55/55 countries | powerplantmatching, RePP Africa, GEM | L4 | L4 |
| **Renewable resources** | 55/55 countries | ERA5, GWA, GSA, PVGIS, SARAH-2 | L5 | L5 |
| **Demand** | 55/55 countries | AFREC, WorldPop, GEP, DRE Atlas | L4 | L4 |
| **Socioeconomic** | 55/55 countries | WorldPop, DRYAD GDP, AfDB | L3 | L3 |
| **Fuel prices** | 41/55 countries | GlobalPetrolPrices, UNDP, AFREC | L3 | L3 |
| **Technology costs** | 55/55 countries | IRENA, IEA, NREL | L4 | L4 |
| **Policy & regulatory** | 55/55 countries | AUDA-NEPAD, AFREC, AEP | L3 | L2 |
| **Market data** | 20/55 countries | SAPP DMS, WAPP ICC, SAWEM | L3 | L3 |
| **Water** | 45/55 countries | FAO, VegDischarge, IWMI | L3 | L3 |
| **Hydrogen** | 30/55 countries | IEA, HyAfrica, IRENA | L3 | L3 |
| **Transport** | 30/55 countries | CCG Starter Kits, EIA, OPEC | L3 | L3 |
| **Industry** | 20/55 countries | AFREC, GECF | L2 | L2 |
| **VIIRS radiance** | 55/55 countries | NASA Black Marble | L4 | L4 |
| **Climate projections** | 55/55 countries | CMIP6, CDS | L4 | L4 |
| **Weather** | 55/55 countries | ERA5 | L5 | L5 |
| **Crowdsourced** | 15/55 countries | GridWatch, WhatsApp, USSD | L3 | L3 |
| **Intelligence signals** | 55/55 countries | News, tenders, social, LLM | L3 | L3 |

**Complete coverage (55/55)**: Grid, generation, renewables, demand, socioeconomics, costs, policy, VIIRS, climate, weather, signals.
**Partial coverage (<40/55)**: Market data, water, hydrogen, transport, industry, crowdsourced.
**Biggest gap**: Industry data (20/55) and market data (20/55).

---

## Part VIII: Validation & Quality Matrix

| Capability | Internal Validation | External Validation | Peer Review | Backtesting | Cross-Model | Independent |
|---|---|---|---|---|---|---|
| **PRG** | L4 | L2 | L1 | L2 | L3 | L1 |
| **Planning Core** | L5 | L4 | L4 | L4 | L4 | L3 |
| **Sector Coupling** | L4 | L3 | L3 | L3 | L3 | L2 |
| **Renewable Technologies** | L5 | L4 | L4 | L4 | L4 | L3 |
| **Market Simulation** | L3 | L3 | L3 | L4 | L3 | L2 |
| **Stochastic Optimisation** | L4 | L3 | L3 | L3 | L3 | L2 |
| **Outage Prediction** | L4 | L4 | L4 | L5 | L4 | L4 |
| **Loss Mitigation** | L3 | L3 | L3 | L3 | L3 | L2 |
| **What-If Engine** | L4 | L3 | L2 | L3 | L3 | L2 |
| **Intelligence Scanning** | L4 | L3 | L2 | L3 | L3 | L2 |
| **Reporting** | L4 | L3 | L2 | L3 | L3 | L2 |

**Highest validation**: Outage prediction (validated against Ghana and Johannesburg studies), planning core (validated against multiple African case studies).
**Lowest validation**: PRG, intelligence scanning, reporting — all of which lack peer-reviewed or independent validation.

**Note**: The PRG's low external validation reflects its novel nature. No comparable system exists in the energy modelling ecosystem, so validation will require novel methodologies (e.g., differential testing against manually-derived scenarios).

---

## Part IX: Integration & Interoperability Matrix

| External System | Integration Type | Maturity | Standard |
|---|---|---|---|
| **PyPSA-Earth** | Fork, data pipeline reuse | L5 | Native |
| **PyPSA** | Core engine | L5 | Native |
| **PyPSA-Earth-Sec** | Sector coupling extension | L4 | Native |
| **OSeMOSYS** | Data exchange, model comparison | L3 | INES-spec |
| **Calliope** | Data exchange, model comparison | L3 | INES-spec |
| **PLEXOS** | Benchmarking (import/export) | L2 | Custom |
| **IRENA FlexTool** | Data exchange | L3 | INES-spec |
| **OpenTEPES** | Data exchange | L3 | Custom |
| **OnSSET** | Electrification integration | L3 | Custom |
| **HOMER** | Mini-grid sizing | L2 | Custom |
| **MESA** | Agent-based modelling | L4 | Native |
| **ASSUME** | RL market simulation | L3 | Custom |
| **AMIRIS** | Market simulation | L3 | Custom |
| **OSeMOSYS CLEWs** | Cross-sector | L3 | Custom |
| **GTAP** | Trade modelling | L2 | Custom |
| **AirQ+** | Health impact | L3 | Custom |
| **CMIP6 (ESGF)** | Climate projections | L4 | CF conventions |
| **NASA Earthdata** | Satellite data | L4 | Native |
| **Copernicus CDS** | ERA5, CMIP6 | L4 | Native |
| **Global Wind Atlas** | Wind resource | L4 | GIS |
| **Global Solar Atlas** | Solar resource | L4 | GIS |
| **GridWatch** | Ground truth | L3 | Custom |
| **AUDA-NEPAD Mwanga** | CMP data | L3 | Custom |
| **AFREC AEIS** | Energy statistics | L3 | Custom |
| **SAPP DMS** | Market data | L3 | Custom |
| **WAPP ICC** | Market data | L3 | Custom |

**Strongest integrations**: PyPSA ecosystem, NASA, Copernicus.
**Weakest integrations**: PLEXOS (proprietary), GTAP (complex), HOMER (proprietary).

---

## Part X: Non-Functional Coverage Matrix

| Non-Functional Requirement | Target | Maturity | Evidence |
|---|---|---|---|
| **Performance: LOPF (55 nodes, 8760h)** | < 6 hours | L4 | Benchmark |
| **Performance: Continental CEP (2025–2060)** | < 36 hours | L4 | Benchmark |
| **Performance: Outage forecast (24h)** | < 10 seconds | L4 | Benchmark |
| **Performance: What-if solve** | < 2 hours | L4 | Benchmark |
| **Performance: PRG consistency check** | < 5 seconds | L4 | Benchmark |
| **Performance: Propagation (single change)** | < 500 ms | L4 | Benchmark |
| **Performance: API response (cached)** | < 2 seconds | L4 | Benchmark |
| **Scalability: Parameters** | 10,000 | L4 | Design |
| **Scalability: Equations** | 500 | L4 | Design |
| **Scalability: Concurrent users** | 1,000 | L3 | Design |
| **Scalability: Scenarios** | 50,000 | L3 | Design |
| **Reliability: Uptime** | 99.5% | L4 | SLA |
| **Reliability: Data durability** | 99.999% | L4 | Backups |
| **Reliability: Disaster recovery** | RTO 4h, RPO 1h | L3 | Plan |
| **Security: Authentication** | OAuth 2.0, API key | L4 | Audit |
| **Security: Encryption** | TLS 1.3, at rest | L4 | Audit |
| **Security: Privacy** | GDPR, POPIA | L3 | Audit |
| **Usability: Time to first query** | < 5 minutes | L4 | User study |
| **Usability: Documentation coverage** | 100% of public API | L4 | Audit |
| **Accessibility: WCAG 2.1 AA** | Compliant | L2 | Audit |
| **Portability: OS support** | Linux, macOS, Windows | L4 | Test matrix |
| **Portability: Cloud support** | AWS, Azure, GCP | L4 | Test matrix |
| **Maintainability: Test coverage** | > 80% | L4 | Coverage report |
| **Maintainability: Code quality** | PEP 8, mypy strict | L4 | CI |

**Strongest**: Performance, security, portability, maintainability.
**Weakest**: Accessibility, disaster recovery, privacy audit.

---

## Part XI: Gap Analysis Summary

Aggregating across all matrices, the platform's most significant gaps are:

### Critical Gaps (Blocking L4 Overall)

| Gap | Affected Domains | Current | Target | Priority |
|---|---|---|---|---|
| **Conflict detector** | PRG | L1 | L4 | P0 |
| **Correction suggestions** | PRG | L1 | L4 | P0 |
| **Translation layer** | PRG | L1 | L4 | P0 |
| **Unit checking (Pint)** | PRG | L2 | L4 | P1 |
| **Incremental updates** | PRG | L0 | L4 | P1 |
| **CAPP data coverage** | Geographic | L3 | L4 | P1 |
| **Industry data coverage** | Data | L2 | L4 | P1 |
| **Market data coverage** | Data | L3 | L4 | P1 |
| **External validation of PRG** | Validation | L2 | L4 | P1 |
| **Household/small business UX** | User | L3 | L4 | P2 |
| **Accessibility (WCAG AA)** | UX | L2 | L4 | P2 |
| **Marine energy modelling** | Technology | L2 | L4 | P2 |
| **EGS geothermal modelling** | Technology | L2 | L4 | P2 |
| **Intraday/balancing markets** | Market | L2 | L4 | P2 |
| **Restoration sequencing** | Outage | L2 | L4 | P2 |

### Non-Critical Gaps (Nice to Have)

| Gap | Affected Domains | Priority |
|---|---|---|
| Type inference from equations | PRG | P3 |
| GraphQL API maturity | Delivery | P3 |
| Spreadsheet add-on depth | Delivery | P3 |
| Voice interface maturity | Delivery | P3 |
| Multi-tenancy depth | Security | P3 |
| Carbon market methodology | Data | P2 |
| Insurance & catastrophe | Analytics | P2 |
| Just transition modelling | Analytics | P2 |
| Consumer protection | Analytics | P2 |
| Digital & cybersecurity | Analytics | P2 |
| Geopolitical & strategic | Analytics | P2 |
| Asset condition & lifecycle | Analytics | P2 |
| Market operations | Analytics | P2 |
| Land use & community | Analytics | P2 |

---

## Part XII: Summary — The Platform at Full Maturity

When fully realised, Alea will present the following profile:

| Dimension | Target Maturity | Current (v1) | Gap |
|---|---|---|---|
| **Overall platform** | **L4** | L2.5 | 1.5 levels |
| **Data & Ingestion** | L4 | L3.5 | 0.5 |
| **PRG** | L4 | L2.5 | 1.5 |
| **Planning Core** | L5 | L4.5 | 0.5 |
| **Sector Coupling** | L4 | L3.5 | 0.5 |
| **Renewables** | L4 | L3.5 | 0.5 |
| **Market Simulation** | L4 | L3 | 1.0 |
| **Stochastic Optimisation** | L4 | L3.5 | 0.5 |
| **Outage Prediction** | L4 | L3.5 | 0.5 |
| **Loss Mitigation** | L4 | L3 | 1.0 |
| **What-If Engine** | L4 | L3.5 | 0.5 |
| **Intelligence Scanning** | L4 | L3 | 1.0 |
| **Reporting** | L4 | L3 | 1.0 |
| **Delivery Interfaces** | L4 | L3.5 | 0.5 |
| **Data Management** | L4 | L3.5 | 0.5 |
| **Security & Governance** | L4 | L4 | 0 |
| **Validation & QA** | L4 | L3 | 1.0 |
| **User Experience** | L4 | L3.5 | 0.5 |
| **Operations** | L4 | L4 | 0 |

**Overall platform maturity target: L4 (Validated)** across all domains, with selected capabilities at L5 (Best-in-class).

**Selected L5 capabilities**:
- Renewable resource modelling (solar, wind)
- Planning core (LOPF, clustering, temporal aggregation)
- PRG DSL and feedback solver
- Outage prediction (VIIRS, ML)
- Capture price calculation
- Delivery through dashboard, API, SDKs

**Selected L3 capabilities** (acceptable gaps):
- Marine energy (niche technologies)
- EGS geothermal (early-stage)
- Intraday and balancing markets (market design still evolving in Africa)
- Voice interface (marginal for professional users)

---

## Part XIII: Conclusion

This Capabilities Coverage Matrix defines the **most featureful and capable version of the Alea platform** across 18 capability domains, 20 user archetypes, 5 geographic regions, 18 delivery channels, 40+ technologies, 25+ data sources, and 20 non-functional requirements.

The matrix shows that:

1. **The platform's ambition is defined and measurable.** Every capability has a target maturity level and a set of evidence requirements.

2. **The largest gaps are in the PRG** (conflict detector, correction suggestions, translation layer) and in **data coverage for Central Africa, industry, and market operations**. These are the P0 and P1 priorities.

3. **The strongest capabilities** — planning core, renewable technologies, outage prediction, delivery infrastructure — are already at or near L4. They are the platform's foundation and its competitive advantage.

4. **The platform's reach is broad**: from a household in Malawi using USSD to a sovereign wealth fund using the Enterprise API, from a journalist in Lagos to a researcher in Nairobi, from a regulator in Morocco to a utility in South Africa.

5. **The platform's depth is genuine**: from a single-hour dispatch to a multi-decade stochastic optimisation, from a single transmission line outage to a continental cascade, from a single news article to a validated model update.

When fully realised, Alea will be the **definitive energy intelligence platform for Africa** — not because it does any single thing better than the best-in-class tools, but because it does **everything** the continent needs, **for everyone** who needs it, **through every channel** they can access. That is the promise this matrix defines and the roadmap this specification enables.

---

**End of Matrix**