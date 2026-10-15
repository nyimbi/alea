# Alea: Exhaustive List of Modelling Algorithms

This specification catalogues every algorithm required to implement Alea across all six analytical layers, plus the data pipeline and intelligence scanning module. Each entry specifies the algorithm name, its purpose, the layer it belongs to, and the mathematical or computational method it implements.

---

## Part I: Layer 1 — PyPSA-Earth Planning Core

### 1. Linear Optimal Power Flow (LOPF)

**Purpose**: Determine the least-cost dispatch of generation and storage subject to network constraints.

**Algorithm**: Linear programming with the following formulations:

| Formulation | Description | When to Use |
|---|---|---|
| **Angles** (`formulation="angles"`) | Uses voltage angles θ as variables; flow = (θᵢ − θⱼ)/xᵢⱼ | Default for most studies |
| **Cycles** (`formulation="cycles"`) | Uses cycle flows as variables; eliminates angle variables | Large networks with many meshes |
| **Kirchhoff** (`formulation="kirchhoff"`) | Uses cycle-based KVL constraints | Networks with high meshing |
| **PTDF** (`formulation="ptdf"`) | Uses Power Transfer Distribution Factors; eliminates flow variables | Real-time applications |

The LOPF minimises total system cost subject to nodal power balance (Kirchhoff's Current Law), Kirchhoff's Voltage Law, generator capacity constraints, storage constraints, and branch flow limits.

### 2. Unit Commitment (UC)

**Purpose**: Determine which thermal generators to commit and decommit over time, subject to technical constraints.

**Algorithm**: Mixed-Integer Linear Programming (MILP) with binary status variables uₙ,ₛ,ₜ ∈ {0,1}. PyPSA uses a **big-M formulation** to linearise the non-linear product of binary status variables and continuous capacity variables.

**Constraints implemented**:
- Minimum up/down times
- Start-up and shut-down costs
- Ramp rate limits (up and down)
- Minimum stable levels
- Reserve requirements

**Linearised UC**: For large problems where binary variables are computationally prohibitive, PyPSA supports `linearized_unit_commitment=True`, which relaxes binary variables to continuous [0,1] while retaining cost and ramp constraints.

### 3. Transmission Loss Approximation

**Purpose**: Account for non-linear quadratic losses in the linear LOPF formulation.

**Algorithms**:

| Method | Description | Configuration |
|---|---|---|
| **Secant-based approximation** | Piecewise linear secant lines with error control | `transmission_losses=True`; options: `atol=1` (MW), `rtol=0.1`, `max_segments=20` |
| **Tangent-based approximation** (deprecated) | Tangent lines to the quadratic loss curve | `transmission_losses=N` (number of tangents) |

Research shows that **two or three tangents** suffice to represent power flows and losses adequately in design studies. Disregarding losses overestimates optimal grid expansion by approximately 20%.

### 4. Spatial Clustering

**Purpose**: Reduce the spatial resolution of the network to make optimisation tractable.

**Algorithms**:

| Method | Description | Application |
|---|---|---|
| **K-means clustering** | Partitions network nodes into k clusters by minimising within-cluster variance | PyPSA-Earth default; configurable between 2 and 62 clusters |
| **K-means++** | Improved initialisation for k-means, avoiding poor local optima | Recommended for large networks |
| **Voronoi tessellation** | Divides space into polygons around each cluster centre | Used for assigning generators and loads to buses |
| **Max-p clustering** | Constrained clustering with maximum cluster size | Recommended alongside k-means for balanced clusters |

### 5. Temporal Aggregation (TSAM)

**Purpose**: Reduce the number of time steps while preserving statistical properties of the time series.

**Algorithm**: Time Series Aggregation Module (TSAM) using **agglomerative clustering** with variable-duration segments. The algorithm:

1. Clusters snapshots into typical periods using hierarchical clustering.
2. Assigns each original time step to a representative period.
3. Computes snapshot weightings (hours represented by each segment).

**Configuration**: `segments=20` (typical range 4–20 for energy system models). The model reports the **error introduced by temporal aggregation** for key outputs (cost, emissions, curtailment).

### 6. Iterative Transmission Expansion

**Purpose**: Handle the dependence of line impedances on line capacities when transmission expansion is enabled.

**Algorithm**: **Sequential Linear Programming (SLP)** with iterative impedance recalculation. After each solve, line impedances and resistances are recalculated based on optimised capacities. The process repeats until (i) line expansion choices converge, or (ii) a maximum number of iterations is reached.

**Warm-starting**: The solution from the previous iteration is used to accelerate the next solve.

### 7. Multi-Horizon Investment Optimisation

**Purpose**: Optimise investment decisions across multiple investment periods with perfect foresight.

**Algorithm**: Linear programming with `multi_investment_periods=True`. The model optimises all periods simultaneously, using a discount rate (default 7%) to annualise costs.

### 8. Stochastic Programming with CVaR

**Purpose**: Optimise investment decisions that are robust across multiple uncertain future scenarios.

**Algorithm**: **Two-stage stochastic programming** with scenario trees. First-stage decisions (investment) are made before uncertainty resolves; second-stage decisions (dispatch) are scenario-specific.

**Risk-averse formulation**: **Conditional Value at Risk (CVaR)** with parameters:
- **α (alpha)**: Tail level (e.g., 0.95 for worst 5% of outcomes)
- **ω (omega)**: Trade-off between expectation and risk (0 = risk-neutral, 1 = fully risk-averse)

The objective augments expected cost with a CVaR penalty: min (1−ω)·E[Cost] + ω·CVaR_α.

---

## Part II: Layer 2 — Sector Coupling

### 9. Multi-Energy Carrier Optimisation

**Purpose**: Optimise flows across electricity, hydrogen, heat, transport, industry, and water carriers.

**Algorithm**: Extended LOPF with `Link` components (conversion technologies with efficiencies) and `Store` components (storage). PyPSA automatically handles links with multiple inputs (bus0) and/or outputs (bus1, bus2, bus3).

### 10. Hydrogen Value Chain Modelling

**Purpose**: Optimise hydrogen production, storage, transport, and export.

**Algorithms**:
- **Electrolysis**: PEM, alkaline, and SOEC modelled as Links with efficiency and capital cost.
- **Storage**: Salt caverns, depleted reservoirs, above-ground storage modelled as Stores.
- **Export optimisation**: Four delivery modes — constant, ship profile, limitedly flexible, fully flexible.

### 11. Additionality Constraint

**Purpose**: Ensure hydrogen production does not divert renewable generation from domestic demand.

**Algorithm**: Distribution-key-based constraint that compares hydrogen production scenarios against a reference case, using country-specific keys (keyₙ,ₛ)【from PyPSA-Earth sector-coupled documentation】.

---

## Part III: Layer 3 — Market Simulation

### 12. Agent-Based Market Clearing (AMIRIS)

**Purpose**: Simulate day-ahead electricity market clearing with strategic bidding.

**Algorithm**: **Merit-order bidding model**. Bids are submitted by market participants, ranked according to the merit order principle, and the market clears at the intersection of aggregated supply and demand curves.

**Agent types**:
- **Markets**: Determine prices by collecting bids
- **Traders**: Fulfil marketing strategies
- **Plant operators**: Control power plants, bid at marginal cost + markup
- **Flexibility providers**: Optimise dispatch using dynamic programming
- **Information providers**: Create forecasts
- **Policy**: Model feed-in tariffs, capacity payments

### 13. Reinforcement Learning Bidding (ASSUME)

**Purpose**: Learn optimal bidding strategies through repeated market simulations.

**Algorithm**: **Multi-Agent Twin Delayed DDPG (MATD3)** , which extends TD3 to multi-agent settings.

**TD3 improvements over DDPG**:
- **Twin critics**: Two Q-value functions reduce overestimation bias
- **Delayed policy updates**: Actor updated less frequently than critic
- **Target policy smoothing**: Adds noise to target actions for robustness

**Observation space**: Portfolio costs, market prices, competitor behaviour.

**Action space**: Markup multiplier per cost bin per time step.

### 14. Capture Price Calculation

**Purpose**: Compute revenue-weighted mean price for each generator.

**Algorithm**:

$$\text{Capture Price}_i = \frac{\sum_t p_{i,t} \cdot \pi_t}{\sum_t p_{i,t}}$$

Where pᵢ,ₜ is generation and πₜ is market price. The **capture rate** is capture price divided by time-weighted average price.

### 15. PPA Benchmark Derivation

**Purpose**: Derive PPA curves from simulated wholesale price paths.

**Algorithm**: Scenario-based price path aggregation with adjustments for:
- Contract tenor (discount rate curve)
- Indexation (CPI, USD, EUR)
- Counterparty risk (credit spread)
- Currency risk (FX forward curve)

---

## Part IV: Layer 4 — Outage Prediction & Resilience

### 16. VIIRS Black Marble Angular Effect Correction

**Purpose**: Remove satellite viewing angle artefacts from nighttime light data.

**Algorithms**:

| Method | Description |
|---|---|
| **VZA grouping** | Group observations by Viewing Zenith Angle to establish per-angle baselines |
| **Self-adjusting Filter and Angular Effect Correction (SFAC)** | Eliminates angular effect without auxiliary data, using 16-day satellite cycle |
| **Relative calibration** | Uses the 16-day cycle of satellite view angles for correction |
| **Angular normalization** | Universal method applicable to any hazard or geographic location |

### 17. OWL-I Outage Detection

**Purpose**: Detect power outages from VIIRS/Black Marble nighttime light observations.

**Algorithm**: **Two-stage pipeline**:

1. **Deconfounding model**: A physically motivated linear model removes non-outage sources of brightness variability (lunar illumination, viewing geometry, seasonality, day-of-week effects). Outage fraction is computed by comparing observed radiance (L_obs) with expected brightness (L̂_dec) predicted by the deconfounding model.

2. **Neural calibration model**: A machine learning model maps residual dimming to outage fraction. The architecture is **pixel-independent**, meaning it generalises to new regions without retraining.

### 18. Weather-Driven Outage Forecasting

**Purpose**: Predict outage probability using weather, temporal, and historical features.

**Algorithms**:

| Algorithm | Description | Validation |
|---|---|---|
| **Random Forest** | Ensemble of decision trees with bagging | Ghana: AUC 0.8346 |
| **XGBoost** | Gradient boosting with regularisation | Acc = 1.00, F1 = 0.97–1.00 |
| **LightGBM** | Gradient boosting with leaf-wise growth | Competitive with XGBoost |
| **Logistic Regression** | Baseline linear classifier | Used for benchmarking |

**Feature engineering**: Temporal (hour, day, month, season), meteorological (temperature, wind speed, precipitation, humidity, heat index), historical (30-day and 90-day outage rates), interaction (temperature × wind speed).

**Class imbalance handling**: **SMOTE** (Synthetic Minority Over-sampling Technique).

### 19. Predictive Maintenance (Survival Analysis)

**Purpose**: Predict failure probability for critical assets (transformers, circuit breakers).

**Algorithm**: **Cox Proportional Hazards Model**:

$$h(t | X) = h_0(t) \cdot \exp(\beta_1 X_1 + \beta_2 X_2 + \cdots + \beta_p X_p)$$

Where h(t|X) is hazard rate, h₀(t) is baseline hazard, and X are covariates (age, loading factor, oil DGA, moisture content).

**Hybrid extension**: **CNN-LSTM + Cox PHM** for remaining useful life (RUL) prediction using dissolved gas analysis (DGA) data over 30 years.

### 20. Loss Decomposition (Power Flow Tracing)

**Purpose**: Attribute transmission losses to individual generators and loads.

**Algorithm**: **Proportional Sharing Principle (PSP)** . Each node is equivalent to two nodes (active power node and reactive power node). A proportional sharing matrix M is built up. The negative value of branch loss is treated as the output of a virtual power source (downstream tracing) or as consumption of a virtual load (upstream tracing).

**Allocation matrices**:
- **Downstream allocation matrix A_d**: Traces power from generators to loads
- **Upstream allocation matrix A_u**: Traces power from loads to generators

### 21. TLENS (Transmission Lines' Contribution to Energy Not Supplied)

**Purpose**: Identify transmission lines whose failure contributes most to energy not served.

**Algorithm**:

1. Solve base case LOPF to establish base ENS.
2. For each line l, deactivate the line and re-solve LOPF.
3. Compute TLENS_l = ENS_post-outage − ENS_base.
4. Rank lines by TLENS.

**Validation**: Malawi study identified Nanjoka–Nkhotakota, Nkhotakota–Dwangwa, Dwangwa–Chintheche, and Kapichila–Mlambe as critical.

### 22. N-1 Contingency Analysis (LODF)

**Purpose**: Efficiently compute post-contingency line flows without re-solving the full power flow for each contingency.

**Algorithm**: **Line Outage Distribution Factors (LODF)** :

$$\text{LODF}_{M,O} = \text{PTDF}_M \cdot C_{L_O}^T \cdot (E - \text{PTDF}_O \cdot C_{L_O}^T)^{-1}$$

Where PTDF is the Power Transfer Distribution Factor matrix, C_L is the line incidence matrix, and E is the identity matrix.

**Generalized LODF (GLODF)** for multiple simultaneous outages.

### 23. Resilience Metrics

**Purpose**: Quantify system resilience using standard reliability indices.

| Metric | Formula | Description |
|---|---|---|
| **ENS** | Σ (demand − served) | Energy Not Served (MWh) |
| **EENS** | Σ p_s · ENS_s | Expected Energy Not Served |
| **SAIDI** | Σ(rᵢ × Nᵢ) / N_T | System Average Interruption Duration Index |
| **SAIFI** | Σ Nᵢ / N_T | System Average Interruption Frequency Index |
| **LOLP** | P(load > available generation) | Loss of Load Probability |

---

## Part V: Layer 5 — What-If Scenario Engine

### 24. Scenario Generation

**Purpose**: Generate representative scenarios for stochastic optimisation and what-if analysis.

**Algorithms**:

| Method | Description | When to Use |
|---|---|---|
| **Monte Carlo Simulation (MCS)** | Random sampling from probability distributions | Baseline; simple to implement |
| **Latin Hypercube Sampling (LHS)** | Stratified sampling with even coverage of probability space | Higher efficiency; closer to optimum with fewer scenarios |
| **Copula-based sampling** | Models complex dependencies between variables | When correlations matter |
| **Stratified LHS (SLHS)** | Combines stratification with LHS | Enhanced efficiency for VPP planning |

### 25. Multi-Objective Optimisation (ε-Constraint)

**Purpose**: Generate Pareto fronts for trade-offs between cost, emissions, resilience, and other objectives.

**Algorithm**: **ε-constraint method**. One objective is optimised while others are transformed into constraints with upper/lower bounds (εᵢ). By varying εᵢ across a grid, the Pareto front is traced.

**Augmented ε-constraint (AUGMECON)** : Adds slack variables to ensure Pareto optimality and avoid weakly Pareto optimal solutions.

### 26. Efficient Frontier Generation

**Purpose**: Generate trade-off curves between system cost and risk (CVaR).

**Algorithm**: Sweep ω from 0 to 1 in increments (e.g., 0.1), solving the stochastic optimisation at each point. The result is a frontier from risk-neutral (lower expected cost, higher risk) to risk-averse (higher expected cost, lower risk).

### 27. Warm-Starting and Caching

**Purpose**: Accelerate repeated what-if solves.

**Algorithms**:
- **Warm-starting**: Use the solution from the base network as the initial point for the modified network.
- **Hash-based caching**: Compute a hash of all parameter values; return cached results if the hash matches a previous solve.
- **Incremental solving**: For small parameter changes, use the previous solution as a starting point.

---

## Part VI: Layer 6 — Intelligence Scanning

### 28. LLM-Based Signal Extraction

**Purpose**: Extract structured signals from unstructured text (news, tenders, social media).

**Algorithm**: **Prompt-based extraction** using large language models (GPT-4, Mixtral). The LLM receives a system prompt defining the signal taxonomy and returns a JSON array of signals with confidence scores and evidence quotes.

**Validation**: Mixtral-8 achieved **91% success rate** for flagging outage-related social media posts【from GLISSA framework】.

### 29. Near-Duplicate Detection

**Purpose**: Detect when the same event is reported by multiple sources.

**Algorithm**: **MinHash with Locality-Sensitive Hashing (LSH)** . Documents are shingled (k=5), MinHash signatures are computed (num_perm=128), and LSH indexes them for efficient near-duplicate queries with threshold 0.7.

### 30. Signal Scoring and Prioritisation

**Purpose**: Rank signals for human review.

**Algorithm**: Weighted scoring function:

```
score = confidence × 30 + source_reliability × 20 + signal_type_impact × 25
      + (1 − data_completeness) × 15 + (1 − corroboration_count) × 10
```

### 31. Human-in-the-Loop Validation

**Purpose**: Ensure extracted signals are accurate before committing to model.

**Algorithm**: Priority queue (Redis sorted set) with confirm/reject/edit actions. Confirmed signals are committed to the model update queue.

---

## Part VII: Data Pipeline Algorithms

### 32. Power Plant Matching

**Purpose**: Consolidate multiple power plant databases into a single ground-truth dataset.

**Algorithm**: **powerplantmatching** — cleans, aggregates, filters, and matches datasets pairwise to identify duplicates based on name, location, fuel, and technology. Inputs: OSM, GEM, IRENA, GEO, GPD.

### 33. Renewable Profile Generation (atlite)

**Purpose**: Convert meteorological data into hourly renewable generation profiles.

**Algorithm**: `atlite` — uses ERA5 reanalysis data with turbine power curves and PV panel models to compute capacity factors. Aggregates over Voronoi cells.

### 34. Demand Disaggregation

**Purpose**: Downscale national demand to sub-national nodes.

**Algorithm**: **GDP-population weighted disaggregation**. National demand is distributed to grid nodes in proportion to a weighted combination of GDP raster and population raster values within each node's catchment area.

### 35. Grid Topology Extraction

**Purpose**: Build the transmission network from OpenStreetMap and World Bank data.

**Algorithm**: OSM extraction using **Osmium** or **PyOsmium**; World Bank lines merged using voltage and capacity attributes.

---

## Part VIII: Summary Matrix

| Layer | Algorithm | Purpose |
|---|---|---|
| **1. Planning** | LOPF (4 formulations) | Least-cost dispatch |
| | Unit Commitment (MILP, big-M) | Thermal scheduling |
| | Secant/Tangent loss approximation | Loss linearisation |
| | K-means, K-means++, Voronoi, Max-p | Spatial clustering |
| | TSAM (agglomerative clustering) | Temporal aggregation |
| | Sequential Linear Programming | Iterative transmission expansion |
| | Two-stage stochastic + CVaR | Risk-averse investment |
| **2. Sector Coupling** | Multi-carrier Links/Stores | Hydrogen, heat, transport, industry |
| | Additionality constraint | Hydrogen domestic priority |
| **3. Market** | AMIRIS merit-order | Market clearing |
| | MATD3 (TD3 multi-agent) | RL bidding strategies |
| | Capture price formula | Revenue-weighted price |
| **4. Outage/Resilience** | VZA grouping, SFAC, angular normalisation | VIIRS correction |
| | OWL-I (deconfounding + neural calibration) | Outage detection |
| | Random Forest, XGBoost, LightGBM | Outage forecasting |
| | SMOTE | Class imbalance |
| | Cox PHM, CNN-LSTM + Cox | Predictive maintenance |
| | Proportional Sharing Principle | Loss decomposition |
| | TLENS | Critical line identification |
| | LODF, GLODF | Contingency analysis |
| | ENS, EENS, SAIDI, SAIFI, LOLP | Resilience metrics |
| **5. What-If** | Monte Carlo, LHS, Copula, SLHS | Scenario generation |
| | ε-constraint, AUGMECON | Multi-objective Pareto |
| | ω sweep | Efficient frontier |
| | Warm-start, hash caching | Rapid re-solve |
| **6. Intelligence** | LLM prompt extraction | Signal extraction |
| | MinHash + LSH | Near-duplicate detection |
| | Weighted scoring | Signal prioritisation |
| **Data Pipeline** | powerplantmatching | Asset consolidation |
| | atlite | Renewable profiles |
| | GDP-pop weighted disaggregation | Demand downscaling |
| | OSM/World Bank merge | Grid topology |

This exhaustive list defines every algorithm Alea requires across all six analytical layers, the data pipeline, and the intelligence scanning module. Each algorithm is grounded in validated methodologies from PyPSA, PyPSA-Earth, AMIRIS, ASSUME, OWL-I, and peer-reviewed literature, ensuring that Alea's predictions and insights are both rigorous and reproducible.