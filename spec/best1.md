To be the best in the world across every capability, PyPSA-X Pan-African must define "best" not by European or North American standards, but by what is required to deliver rigorous, actionable, and trusted analysis **under African data and institutional realities**. The global frontier is defined by PyPSA v1.0's stochastic optimisation, agent-based market models like AMIRIS and ASSUME, the sector-coupling depth of TIMES and PyPSA-Earth-Sec, and the granularity of commercial tools like PLEXOS—but none of these were built to solve Africa's specific problems. The specification below defines the capabilities, functionality, and characteristics required to surpass all of them for the African context.

---

# PyPSA-X Pan-African: World-Best Capability Specification

## 1. Modelling & Optimisation Core

### 1.1 Multi-Scale Capacity Expansion Planning

**World-Class Benchmark**: PyPSA-Earth and Calliope Africa offer continental-scale capacity expansion, but neither combines continental, power-pool, national, and sub-national resolution in a single, dynamically configurable workflow. PLEXOS offers multi-scale but is closed-source and prohibitively expensive for African institutions.

**Required Functionality**:
- **Single codebase, four spatial scales**: Continental (55 nodes), power-pool (5 aggregated regions), national (55 country nodes with sub-national resolution), and project-scale (custom GIS polygons). The spatial resolution must be reconfigurable without rebuilding the data pipeline.
- **Co-optimisation of generation and transmission**: Simultaneous investment in generators, storage, and transmission lines, with iterative impedance recalculation after each solve to capture the effect of network expansion on power flows.
- **Multi-horizon perfect foresight**: Investment periods from 2025 to 2060 in 5-year steps, with perfect foresight across all periods, implemented via PyPSA's `multi_invest` framework. Results must be solved in a single optimisation run, not sequentially.
- **Rolling-horizon myopic optimisation**: As an alternative to perfect foresight, support rolling-horizon optimisation with user-defined foresight windows (e.g., 5, 10, 15 years) to model realistic decision-making under uncertainty.

**Required Characteristics**:
- A continental 55-node, 8,760-hour LOPF must solve within **6 hours** on a 128-core, 512 GB RAM server.
- A multi-horizon continental CEP (2025–2060, 5-year steps) must solve within **36 hours** on the same hardware.
- The model must produce identical results to PyPSA-Earth for a common African validation scenario, demonstrating numerical consistency.

---

### 1.2 Unit Commitment & Operational Dispatch

**World-Class Benchmark**: PLEXOS is the global benchmark for unit commitment (UC) and short-term dispatch, with sub-hourly resolution and detailed thermal plant constraints. PyPSA supports UC but is not optimised for large-scale UC problems.

**Required Functionality**:
- **Full unit commitment formulation**: Minimum up/down times, start-up and shut-down costs, ramp rates (up and down), minimum stable levels, and reserve constraints for all thermal generators.
- **Sub-hourly temporal resolution**: Support for 15-minute and 5-minute resolution for operational studies, in addition to hourly resolution for planning studies.
- **Adequacy assessment**: Explicit modelling of loss-of-load probability (LOLP), expected unserved energy (EUE), and reserve margins under different EAF (Energy Availability Factor) scenarios for the coal fleet.
- **Co-optimised reserves**: Simultaneous optimisation of energy and operating reserves (spinning, non-spinning, regulation) with country-specific reserve requirements.

**Required Characteristics**:
- UC with sub-hourly resolution for a 55-node continental network must solve within **12 hours** on a 128-core, 512 GB RAM server.
- Adequacy metrics (LOLP, EUE) must be computed with **95% confidence intervals** using Monte Carlo simulation of forced outages.

---

### 1.3 Sector Coupling

**World-Class Benchmark**: TIMES is the benchmark for comprehensive sector coupling, endogenising buildings, industry, transport, and hydrogen. PyPSA-Earth sector-coupled has been validated for hydrogen applications in Egypt and Brazil, demonstrating the technical feasibility of the PyPSA approach for Africa.

**Required Functionality**:
- **Full multi-energy carrier integration**: Electricity, heat (district heating and industrial process heat), hydrogen (production, storage, transport, reconversion), synthetic fuels (aviation, shipping), biomass, and water.
- **Hydrogen value chain**: Electrolysis (PEM, alkaline, SOEC), salt cavern and depleted reservoir storage, pipeline transport, liquefaction, ammonia synthesis, and export terminal modelling.
- **Industrial demand**: Steel (H₂-DRI and scrap-EAF), cement (CCUS and alternative fuels), chemicals (green ammonia, methanol), and mining (electrification and hydrogen haulage).
- **Transport demand**: Electric vehicles (smart charging, V2G), hydrogen fuel cell vehicles, and synthetic aviation fuel.

**Required Characteristics**:
- The sector-coupled continental model must support up to **10,000 Links** and **5,000 Stores** without performance degradation beyond 2× the electricity-only solve time.
- Hydrogen export scenarios must be validated against the Egypt case, which quantified PV exceeding 35 GW and electrolysis in Suez and Damietta for meeting 16% of EU hydrogen demand.
- The model must reproduce the key finding from the Sub-Saharan Africa hydrogen cost-potential study: hydrogen costs starting at **1.6 EUR/kg in Mauritania** with a total potential of **~259 TWh/a under 2 EUR/kg in 2050**.

---

## 2. Data & Resolution

### 2.1 Spatial Granularity

**World-Class Benchmark**: PyPSA-Earth offers a spatial resolution of **30 km × 30 km** globally. This is the finest open-source resolution available for continental-scale modelling.

**Required Functionality**:
- **Sub-30 km renewable resource grids**: For countries with high renewable potential (South Africa, Morocco, Egypt, Kenya, Ethiopia, Namibia), support **10 km × 10 km** or finer resolution for solar and wind resource assessment, using downscaled ERA5 and Global Wind Atlas data.
- **Settlement-level demand**: For all countries with DRE Atlas or GEP coverage, support **settlement-level** demand and generation modelling for electrification planning.
- **Dynamic spatial reconfiguration**: Users must be able to switch between spatial resolutions (e.g., from 55 nodes to 159 nodes for South Africa) without rebuilding the data pipeline, using a configuration flag.

**Required Characteristics**:
- The 10 km resolution model must produce renewable capacity factors within **±5%** of the 30 km model for the same location.
- Settlement-level modelling must support **up to 100,000 settlements** per country without exceeding 256 GB RAM.

---

### 2.2 Temporal Granularity

**World-Class Benchmark**: PLEXOS supports sub-hourly resolution (down to 1 minute) for operational studies. PyPSA-Earth uses hourly resolution (8,760 hours/year) for planning studies.

**Required Functionality**:
- **Multi-resolution temporal modelling**: 1-minute, 5-minute, 15-minute, hourly, and representative-period resolution, selectable by the user based on study purpose.
- **Adaptive temporal aggregation**: Automatic selection of the optimal temporal resolution using the Time Series Aggregation Module (TSAM), with validation against full chronology. The model must report the **error introduced by temporal aggregation** for key outputs (cost, emissions, renewable curtailment).
- **Multi-year rolling horizon**: For operational studies, support rolling-horizon optimisation with user-defined foresight windows.

**Required Characteristics**:
- TSAM aggregation must achieve **< 1% error** in total system cost and **< 2% error** in renewable curtailment for a 20-segment aggregation, validated against the full 8,760-hour model.
- The model must automatically recommend the minimum temporal resolution required to keep key output errors below a user-defined threshold (e.g., 1% cost error).

---

### 2.3 Data Completeness for Africa

**World-Class Benchmark**: No existing model achieves complete data coverage for all 55 AU member states. The OASES continental study identified seven countries as missing due to lack of data: Burundi, Cabo Verde, Comoros, Djibouti, Mauritania, Seychelles, and São Tomé and Príncipe. GEP and DRE Atlas do not cover all countries.

**Required Functionality**:
- **Automated data gap detection**: A data quality module that quantifies completeness for every country across every data category (grid topology, generation, demand, renewables, fuel costs, policy) and assigns a completeness score.
- **Proxy data generation**: For countries with missing data, automatically generate proxy estimates using:
  - **Satellite-based asset detection**: Using the OASES machine learning models for PV and wind detection from satellite imagery.
  - **Regional extrapolation**: Using demand, cost, and technology parameters from neighbouring countries with similar GDP per capita, electrification rate, and resource endowment.
  - **WorldPop and GDP raster downscaling**: For demand estimation at settlement level.
- **Uncertainty quantification for proxy data**: Every proxy estimate must carry an explicit uncertainty range, propagated through the optimisation using scenario weighting or stochastic parameters.

**Required Characteristics**:
- Every country in the model must have a **data completeness score** (0–100%) reported for each data category, visible in the dashboard and API.
- For countries with completeness < 50%, the model must automatically run **three scenarios** using different proxy assumptions and report the resulting range of key outputs.
- The proxy generation module must be validated against countries with complete data: for example, generate proxy data for Kenya using regional averages and compare the resulting model outputs to the data-rich Kenya model, demonstrating **< 15% error** in total system cost.

---

## 3. Market Simulation

### 3.1 Agent-Based Market Clearing

**World-Class Benchmark**: AMIRIS and ASSUME are the leading open-source agent-based market models, achieving a Mean Absolute Error (MAE) of **5.6–6.4 €/MWh** against the ENTSO-E benchmark dataset for European electricity markets. Neither has been applied at continental African scale.

**Required Functionality**:
- **Multi-agent market simulation**: Model generators, retailers, consumers, and flexibility providers as heterogeneous agents with bounded rationality and adaptive strategies.
- **Multi-market clearing**: Day-ahead, intraday, and balancing markets, with cross-border market coupling across power pools.
- **Strategic bidding**: Support for reinforcement learning (RL) agents that learn optimal bidding strategies over repeated market simulations, as demonstrated by ASSUME.
- **Regulatory interventions**: Simulate carbon taxes, capacity markets, renewable auctions, and feed-in tariffs as exogenous policy instruments with agent-level responses.

**Required Characteristics**:
- The market simulation must achieve **MAE < 5 €/MWh** against historical SAWEM data for South Africa and available SAPP market data.
- The simulation must support **up to 1,000 agents** per market without exceeding 128 GB RAM.
- RL agents must converge to Nash-equilibrium-like bidding strategies within **10,000 simulation episodes**.

---

### 3.2 Capture Price & PPA Analytics

**World-Class Benchmark**: COMPASS provides capture prices and PPA benchmarks for South Africa. No open-source tool provides these at continental scale with currency and regulatory risk adjustments.

**Required Functionality**:
- **Capture price calculation**: Revenue-weighted mean price per generator, disaggregated by technology, location, and scenario, with explicit cannibalisation modelling.
- **PPA benchmark curves**: Simulated wholesale price paths adjusted for contract tenor, indexation (CPI, USD, EUR), counterparty risk, and currency risk.
- **Contract-for-difference (CfD) modelling**: Impact of CfD structures on investment decisions and market prices.
- **Bankability metrics**: Debt service coverage ratio (DSCR), project IRR, and equity IRR under different PPA structures and price scenarios.

**Required Characteristics**:
- Capture prices must be calculated for **every generator** in every country, with **hourly resolution** and **scenario-based ranges**.
- PPA curves must be available for **all 55 AU member states**, with currency adjustments for local currency, USD, and EUR.
- Bankability metrics must be stress-tested against **at least five scenarios**: base case, low demand, high fuel price, low renewable cost, and high carbon price.

---

### 3.3 Cross-Border Trade & Power Pool Integration

**World-Class Benchmark**: The CMP and AfSEM represent the institutional framework for continental trade, but no open-source model operationalises cross-border trade across all five power pools with market clearing.

**Required Functionality**:
- **Five power pool models**: SAPP, EAPP, WAPP, CAPP, and COMELEC, each with country-level nodes, interconnectors, and pool-specific market rules.
- **Cross-pool interconnections**: SAPP–EAPP link, AfSEM interconnections, and planned CMP transmission corridors.
- **Wheeling charges and loss factors**: Country-specific transmission pricing, loss factors, and regulatory harmonisation constraints.
- **Trade flow visualisation**: Interactive maps showing hourly cross-border flows, congestion, and price differentials.

**Required Characteristics**:
- The model must reproduce the SAPP market outcomes for a historical year (e.g., 2024) with **< 10% error** in total traded volume and **< 15% error** in average clearing price.
- Cross-border trade flows must be visualised at **hourly resolution** for all interconnectors, with congestion events flagged.

---

## 4. Stochastic & Risk Optimisation

### 4.1 Multi-Stage Stochastic Programming

**World-Class Benchmark**: PyPSA v1.0 supports **two-stage stochastic programming** with scenario trees and **CVaR-based risk-averse optimisation**, controlled by omega (trade-off between expectation and risk) and alpha (tail level). PLEXOS offers stochastic optimisation with efficient frontier generation.

**Required Functionality**:
- **Multi-stage stochastic programming**: Investment decisions at each stage (2025, 2030, 2035, 2040, 2045, 2050) with recourse decisions in subsequent stages, using scenario trees.
- **CVaR risk aversion**: User-controllable risk preference via omega and alpha, generating an efficient frontier of solutions from risk-neutral (omega=0) to highly risk-averse (omega=1).
- **Chance constraints**: Probabilistic constraints on demand satisfaction, renewable curtailment, and reserve margins, with user-defined confidence levels.
- **Uncertainty propagation**: Monte Carlo simulation for fuel prices, demand growth, technology costs, and climate variables, with Latin Hypercube Sampling for efficient scenario generation.

**Required Characteristics**:
- The multi-stage stochastic CEP must solve for **at least 100 scenarios** within **72 hours** on a 256-core, 1 TB RAM server.
- The efficient frontier must be generated with **at least 10 risk levels**, from omega=0 to omega=1 in 0.1 increments.
- Chance constraints must be satisfied with **95% confidence** for demand satisfaction and **90% confidence** for reserve margins.

---

### 4.2 Climate Risk & Resilience

**World-Class Benchmark**: No existing energy system model fully integrates climate risk (drought, flood, extreme weather) into continental-scale capacity expansion for Africa.

**Required Functionality**:
- **Hydrological uncertainty**: CMIP6-based drought and flood scenarios for all major African river basins (Nile, Congo, Niger, Zambezi, Orange), with reservoir inflow time series.
- **Temperature-driven demand**: Temperature-dependent demand profiles using CMIP6 temperature projections, with cooling and heating degree-day adjustments.
- **Extreme weather events**: Stochastic generation of extreme weather events (heatwaves, cold snaps, droughts) and their impact on renewable output, thermal plant efficiency, and demand.
- **Resilience metrics**: System resilience indicators including expected energy not served under extreme events, recovery time, and adaptive capacity.

**Required Characteristics**:
- Climate scenarios must cover **at least four SSP pathways** (SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5) from CMIP6.
- The model must compute **resilience metrics** for at least 10 extreme weather events per scenario.
- Reservoir inflow time series must be downscaled to **daily resolution** for all major hydropower plants.

---

## 5. Delivery & Accessibility

### 5.1 API & Programmatic Access

**World-Class Benchmark**: Most energy models, including PLEXOS and TIMES, lack modern REST APIs. PyPSA-Earth requires significant technical expertise to run and does not offer programmatic access to results.

**Required Functionality**:
- **RESTful API** with endpoints for:
  - Scenario management (create, list, retrieve, delete)
  - Results retrieval (prices, capture rates, PPA curves, capacity mix, emissions)
  - Data access (grid topology, generation assets, demand profiles)
  - On-demand computation (run a scenario, get results within a timeout)
- **GraphQL endpoint** for flexible, efficient querying of complex nested data.
- **WebSocket streaming** for real-time progress updates on long-running optimisation jobs.
- **Python SDK** for programmatic access from Jupyter notebooks and scripts.

**Required Characteristics**:
- API response time must be **< 2 seconds** for cached results and **< 60 seconds** for on-demand computations.
- API must support **OAuth 2.0** and **API keys** for authentication, with rate limiting.
- API must be versioned (v1, v2) and backwards-compatible for at least two major versions.

---

### 5.2 Interactive Dashboard

**World-Class Benchmark**: No open-source energy model provides a continental-scale, interactive dashboard with country-level drill-down. COMPASS delivers a static PDF report.

**Required Functionality**:
- **Interactive continental map**: Visualise generation capacity, transmission network, renewable resource potential, and cross-border flows for all 55 AU member states.
- **Country-level drill-down**: Click on any country to see its dashboard with demand, supply, prices, emissions, and scenario comparison.
- **Power-pool comparison**: Side-by-side comparison of SAPP, EAPP, WAPP, CAPP, and COMELEC across key metrics.
- **Scenario exploration**: Sliders for key parameters (fuel prices, carbon taxes, demand growth, technology costs) with real-time visualisation of results.
- **Export capabilities**: Download charts, maps, and datasets in CSV, PNG, SVG, and PDF formats.

**Required Characteristics**:
- Dashboard must load and render the continental map within **5 seconds** on a standard broadband connection.
- Dashboard must support **50 concurrent users** without performance degradation.
- Scenario exploration must update results within **10 seconds** for pre-computed scenarios.

---

### 5.3 Automated Reporting

**World-Class Benchmark**: COMPASS delivers a professionally formatted PDF report. Open-source models typically deliver raw data or Jupyter notebooks.

**Required Functionality**:
- **Template-driven report generation**: Jinja2 or LaTeX templates for PDF and HTML reports, with charts, tables, and executive summaries.
- **Scheduled reports**: Automated generation of periodic reports (monthly, quarterly, annual) using Airflow or Cron.
- **Multi-language support**: Reports in English, French, Portuguese, and Arabic.
- **Customisable branding**: Allow stakeholders (e.g., national utilities, regulators) to add their logos and branding.

**Required Characteristics**:
- Report generation must complete within **5 minutes** for a 50-page report with 20 charts.
- Reports must be generated in **all four AU working languages** with identical content.

---

### 5.4 Scenario Database

**World-Class Benchmark**: No open-source energy model provides a version-controlled, auditable scenario database with query capabilities.

**Required Functionality**:
- **Version-controlled scenario storage**: Every scenario, input parameter, and output result must be versioned with git-like semantics.
- **Audit trails**: Complete provenance for every data point, from raw input to final result.
- **Query interface**: SQL-like query language for retrieving scenarios, results, and metadata.
- **Reproducibility**: Every scenario must be reproducible from its configuration and data snapshot, with a single command.

**Required Characteristics**:
- Database must support **50,000 scenarios** and **10 TB of results** without performance degradation.
- Every scenario must have a **unique hash** that captures the complete model state (code version, data version, parameters).
- Reproducibility must be verified by automated regression tests: re-running a scenario must produce **identical results** (to machine precision) within 24 hours.

---

## 6. Validation & Transparency

### 6.1 Backtesting Against Historical Data

**World-Class Benchmark**: AMIRIS and ASSUME achieve MAE of 5.6–6.4 €/MWh against ENTSO-E benchmark data. No African model has been validated at this level.

**Required Functionality**:
- **Historical price backtesting**: Compare simulated wholesale prices to historical SAWEM prices (South Africa) and available SAPP/WAPP market data.
- **Dispatch backtesting**: Compare simulated generation dispatch to historical Eskom and SAPP dispatch data.
- **Error metrics**: Calculate MAE, RMSE, MAPE, and correlation coefficients for all backtesting exercises.
- **Bias identification**: Systematic analysis of model biases and their sources (data, assumptions, structure).

**Required Characteristics**:
- Backtesting must cover **at least five years** of historical data for South Africa.
- Error metrics must be reported for **hourly, daily, monthly, and annual** resolution.
- The model must achieve **MAE < 8 €/MWh** for South African wholesale prices by 2027, improving to **< 5 €/MWh** by 2029.

---

### 6.2 Benchmarking Against Global Models

**World-Class Benchmark**: A multi-criteria assessment framework has screened 122 open-source energy system modelling tools against 113 capabilities, using a three-level rubric. PyPSA, Calliope, GENeSYS-MOD, and TIMES scored highest.

**Required Functionality**:
- **Capability benchmarking**: Score PyPSA-X Pan-African against the 113-capability framework, with a target of **> 95% coverage**.
- **Cross-model comparison**: Run the same African scenario in PyPSA-X, PyPSA-Earth, OSeMOSYS, and Calliope, and compare key outputs.
- **Peer review**: Publish model documentation and validation results for independent peer review in academic journals.

**Required Characteristics**:
- The model must achieve **> 95%** on the 113-capability framework by 2028.
- Cross-model comparison must demonstrate **< 10% divergence** in total system cost for a common African scenario by 2028.
- At least **three peer-reviewed publications** validating the model by 2029.

---

## 7. Continental & Institutional Integration

### 7.1 CMP & AfSEM Alignment

**World-Class Benchmark**: The CMP and AfSEM represent the official continental planning framework. No open-source model is directly aligned with these frameworks.

**Required Functionality**:
- **CMP scenario alignment**: Scenarios must be defined to match the CMP's demand forecasts (2,368 TWh by 2040) and generation mix projections (solar dominance at 42% by 2030).
- **AfSEM market design**: Model the AfSEM market structure, including regulatory harmonisation, market coupling, and cross-border trading rules.
- **CMP project pipeline**: Integrate the CMP's bankable project pipeline into the model as investment options.

**Required Characteristics**:
- The model must reproduce the CMP's headline projections within **±10%** for 2030 and 2040.
- The model must support **AfSEM market clearing** across all five power pools by 2027.

---

### 7.2 Capacity Building & Training

**World-Class Benchmark**: The IRENA Eastern Africa Regional Model Analysis & Planning Support Programme delivers an 18-month training programme for 50 participants. No training programme covers continental-scale modelling.

**Required Functionality**:
- **Continental training programme**: A 24-month programme covering all five power pools, with 100+ participants.
- **Certification**: A certification programme for energy planners and researchers across Africa.
- **Open educational resources**: Online courses, tutorials, and example notebooks in English, French, Portuguese, and Arabic.
- **Train-the-trainer**: A network of certified trainers in each power pool.

**Required Characteristics**:
- Training programme must reach **at least 200 participants** across all five power pools by 2029.
- Certification must be recognised by **at least three AU member states** by 2029.
- Open educational resources must be accessed by **at least 10,000 users** by 2029.

---

## 8. Summary: Capability Targets vs. Global Best

| Capability | Global Best | PyPSA-X Target | Target Date |
|---|---|---|---|
| **Spatial resolution** | 30 km (PyPSA-Earth) | 10 km (high-potential countries) | 2028 |
| **Temporal resolution** | 1-minute (PLEXOS) | 5-minute (operational studies) | 2028 |
| **Sector coupling** | Full (TIMES) | Full + African hydrogen value chain | 2027 |
| **Market simulation MAE** | 5.6–6.4 €/MWh (AMIRIS/ASSUME) | < 5 €/MWh (SAWEM) | 2029 |
| **Stochastic optimisation** | Two-stage CVaR (PyPSA v1.0) | Multi-stage CVaR + chance constraints | 2028 |
| **Climate risk** | None at continental scale | CMIP6 integration + resilience metrics | 2029 |
| **Data completeness** | 48/55 countries (OASES) | 55/55 countries with proxy data | 2027 |
| **API** | None (open models) | REST + GraphQL + WebSocket | 2027 |
| **Dashboard** | None (open models) | Continental interactive dashboard | 2027 |
| **Validation** | 5.6–6.4 €/MWh MAE (Europe) | < 5 €/MWh MAE (South Africa) | 2029 |
| **Capability coverage** | 113 capabilities (framework) | > 95% coverage | 2028 |
| **CMP alignment** | CMP SPLAT model | CMP-aligned + AfSEM market clearing | 2027 |

---

## 9. The Decisive Advantage: Africa-Specific World-Class Capabilities

Being "best in the world" for Africa requires capabilities that no global model possesses, because no global model was built to solve Africa's problems. The following capabilities are **non-negotiable** for world-class status in this context:

1. **Proxy data generation at scale**: The ability to generate defensible, uncertainty-quantified proxy data for countries with no data, validated against data-rich countries. No global model does this.

2. **Satellite-based asset detection**: Automated detection of PV and wind installations from satellite imagery, validated for African conditions.

3. **Multi-scale reconfigurability**: The ability to switch from continental (55 nodes) to settlement-level (100,000 nodes) without rebuilding the data pipeline. No model does this.

4. **Continental market simulation**: Agent-based market clearing across all five power pools with cross-border trade, currency risk, and regulatory harmonisation. No model does this.

5. **Climate-resilient planning**: CMIP6-driven hydrological and temperature uncertainty integrated into continental capacity expansion. No model does this.

6. **AfSEM-aligned delivery**: API, dashboard, and reporting aligned with the African Single Electricity Market's institutional framework. No model does this.

These six capabilities, combined with world-class performance on the standard benchmarks, define what it means to be the best in the world **for Africa**. The target is not to replicate PyPSA-Earth or PLEXOS; it is to build a platform that is **more transparent than COMPASS, more granular than PyPSA-Earth, more market-aware than TIMES, and more accessible than any commercial tool**—while solving the data, institutional, and climate problems that are unique to the African continent.