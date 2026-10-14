The ALEA platform derives its predictions and insights through a multi-layered modelling architecture, where each layer consumes the outputs of the one below it, adding analytical depth and predictive capability. This specification details the mathematical formulations, data flows, and computational methods that transform raw data into actionable intelligence.

---

## Part I: The Optimisation Core — How ALEA Determines the Least-Cost System

### 1.1 The Objective Function

ALEA inherits its optimisation core from PyPSA-Earth, which is driven by a **cost-optimisation objective function** in linear form. The objective minimises total system cost across all nodes (countries or regions), technologies, branches (transmission lines), and snapshots (time steps):

$$\text{Minimize} \quad \text{Costs} = \sum_{N,S} c_{n,s}\bar{G}_{n,s} + \sum_{N,S} c_{n,s}\bar{H}_{n,s} + \sum_{L} c_{l}F_{l} + \sum_{T} w_{t} \left[ \sum_{N,S} o_{n,s}G_{n,s,t} + \sum_{N,S} o_{n,s}H_{n,s,t} \right]$$

Where:
- $c_{n,s}$ = capital cost for technology $s$ at node $n$
- $\bar{G}_{n,s}$ = nominal capacity of generators
- $\bar{H}_{n,s}$ = nominal capacity of storage
- $c_l$ = capital cost of branch $l$
- $F_l$ = nominal capacity of branch $l$
- $w_t$ = snapshot weighting (hours represented by each time step)
- $o_{n,s}$ = operational (marginal) cost
- $G_{n,s,t}$ = dispatch of generator at node $n$, technology $s$, time $t$
- $H_{n,s,t}$ = dispatch of storage

The model is solved as a **linear optimal power flow (LOPF)** problem, which optimises generation, grid, and storage capacities simultaneously by minimising annualised system costs, using a discount rate of 7%.

### 1.2 The Nodal Balance Constraint (Kirchhoff's Current Law)

The core physical constraint is the **nodal power balance**, which ensures that the amount of power flowing into a bus equals the amount flowing out (Kirchhoff's Current Law). This is expressed as:

$$\sum_{r} g_{n,r,t} + \sum_{s} e_{n,s,t} + \sum_{l} \alpha_{n,l} \cdot f_{l,t} + \sum_{k} \alpha_{n,k} \cdot p_{n,k,t} = d_{n,t} \quad \forall n,t$$

Where $g$ represents generation, $e$ represents storage discharge, $f$ represents line flows, $p$ represents link flows, and $d$ is demand.

The **dual variable** of this constraint is the **Locational Marginal Price (LMP)** — the shadow price of supplying one additional MW of power at that node and time. When cheap generation is trapped behind a congested line, LMPs can drop below zero as the system redistributes power flows.

### 1.3 Kirchhoff's Voltage Law (KVL)

Power flows in lines and transformers must comply with Kirchhoff's Voltage Law. PyPSA uses the **cycle-based formulation** of KVL:

$$\sum_{l} C_{l,c} \cdot x_l \cdot f_{l,t} = 0 \quad \forall c, t$$

Where $C_{l,c}$ is the cycle incidence matrix, $x_l$ is line reactance, and $f_{l,t}$ is line flow.

### 1.4 Unit Commitment Constraints

For thermal generators, ALEA applies **unit commitment** constraints, which introduce binary status variables for each committable unit. The key constraints are:

- **Minimum up/down times**: A generator committed at time $t$ must remain committed for a minimum number of periods.
- **Start-up and shut-down costs**: Incurred when the status variable changes.
- **Ramp rate limits**: The change in output between consecutive time steps is bounded.
- **Big-M linearisation**: Used to linearise the non-linear product of status and output variables.

### 1.5 Spatial Resolution and Clustering

ALEA supports **five spatial resolutions** for the African continent:

| Resolution | Nodes | Use Case |
|---|---|---|
| **Continental** | 55 (one per AU member state) | Continental planning, CMP alignment |
| **Power pool** | ~20 (aggregated regions) | Regional market analysis |
| **National** | 55 country nodes with sub-national resolution | National planning |
| **Provincial** | Sub-national clusters | Detailed investment analysis |
| **Custom GIS** | User-defined polygons | Project-scale assessment |

Spatial clustering uses a **Voronoi cell approach**, where each cluster is represented by a single node with aggregated generation, demand, and transmission capacity. A broad range of clustering and grid meshing strategies help adapt the model to computational and practical needs.

### 1.6 Temporal Resolution and Aggregation

The default temporal resolution is **full chronology (8,760 hours per year)** to capture renewable variability. For computationally intensive studies, ALEA uses the **Time Series Aggregation Module (TSAM)** to cluster snapshots into segments of varying lengths. Three aggregation methods are available:

1. **Averaging**: Simple averaging of snapshots within segments.
2. **Segmentation (TSAM)**: Agglomerative clustering with variable-duration segments that preserves the statistical properties of the time series.
3. **Pre-computed snapshot map**: User-supplied mapping of hours to representative periods.

The model reports the **error introduced by temporal aggregation** for key outputs (cost, emissions, curtailment), ensuring that users can validate aggregation against full chronology.

### 1.7 Transmission Loss Approximation

Transmission losses are non-linear (quadratic with flow) and must be linearised for the LP formulation. ALEA uses **secant-based approximation with error control**, configured via the `transmission_losses` parameter:

- **Secant method**: Uses piecewise linear secant lines with explicit error bounds (default: absolute tolerance 1 MW, relative tolerance 0.1, maximum 20 segments).
- **Tangent method** (deprecated): Uses tangent lines to approximate the quadratic loss curve.

Research shows that adding a convex relaxation of quadratic losses with **two or three tangents** to the linearised power flow equations suffices to represent power flows and losses adequately in design studies. Disregarding losses overestimates optimal grid expansion by approximately 20%.

---

## Part II: Sector Coupling — How ALEA Models the Full Energy System

### 2.1 Multi-Energy Carrier Architecture

ALEA extends the electricity-only model with **sector coupling**, adding hydrogen, heat, transport, industry, and water as interconnected energy carriers. The core mathematical formulation follows closely the work done in PyPSA-EUR.

Each sector is represented by a **Bus** (energy carrier), **Links** (conversion technologies with efficiencies), and **Stores** (storage). PyPSA can automatically handle links with more than one input (bus0) and/or output (bus1, bus2, bus3) with given efficiencies.

### 2.2 Hydrogen Value Chain Modelling

The hydrogen sector includes:

- **Electrolysis**: PEM, alkaline, and SOEC technologies, modelled as Links with efficiency and capital cost.
- **Storage**: Salt caverns, depleted reservoirs, and above-ground storage, modelled as Stores with charge/discharge rates.
- **Reconversion**: Fuel cells and hydrogen turbines, modelled as Links with efficiency.
- **Export**: Four delivery modes — constant delivery, ship profiles, limitedly flexible delivery, and fully flexible delivery.

The **additionality constraint** ensures that hydrogen production does not divert renewable generation from meeting domestic demand, using distribution keys ($\text{key}_{n,s}$) for reference case comparisons.

### 2.3 Heat, Transport, and Industry

| Sector | Key Technologies | Modelling Approach |
|---|---|---|
| **Heat** | Heat pumps, thermal storage, district heating | Heat pumps as Links with COP; thermal storage as Stores |
| **Transport** | Electric vehicles, hydrogen fuel cell vehicles, synthetic fuels | EV demand as flexible loads; hydrogen vehicles as Links |
| **Industry** | Steel (H₂-DRI, scrap-EAF), cement (CCUS), chemicals (green ammonia, methanol) | Process-specific Links with feedstock and energy inputs |
| **Water** | Desalination, cooling water, irrigation pumping | Water demand linked to thermal plant cooling and hydrogen production |

---

## Part III: Stochastic Optimisation — How ALEA Handles Uncertainty

### 3.1 Two-Stage Stochastic Programming

PyPSA v1.0 introduces **two-stage stochastic programming** with scenario trees out of the box. The formulation is:

- **Stage 1 (here-and-now)**: Investment decisions made before uncertainty is resolved. These decisions must be feasible across all scenarios.
- **Stage 2 (wait-and-see)**: Operational decisions made after uncertainty is resolved. Each scenario has its own optimal dispatch.

The objective minimises the **expected system cost** across all scenarios:

$$\min_{x} \quad c^T x + \sum_{s \in S} p_s \cdot Q(x, \xi_s)$$

Where $x$ is the first-stage investment vector, $p_s$ is the probability of scenario $s$, and $Q(x, \xi_s)$ is the second-stage operational cost given scenario realisation $\xi_s$.

### 3.2 CVaR Risk Aversion

ALEA implements **Conditional Value at Risk (CVaR)-based risk-averse optimisation**, controlled by two parameters:

- **$\alpha$ (alpha)**: The tail level (e.g., 0.95 for the worst 5% of outcomes).
- **$\omega$ (omega)**: The trade-off between expectation and risk (0 = risk-neutral, 1 = fully risk-averse).

The risk-averse objective augments the expected cost with a CVaR penalty:

$$\min_{x} \quad (1-\omega) \cdot \mathbb{E}[\text{Cost}] + \omega \cdot \text{CVaR}_\alpha$$

This generates an **efficient frontier** of solutions from risk-neutral (lower expected cost, higher risk) to risk-averse (higher expected cost, lower risk).

### 3.3 Scenario Generation

Uncertain parameters (fuel prices, demand growth, technology costs, climate variables) are represented as scenarios with explicit probabilities. The model supports:

- **Monte Carlo simulation**: Random sampling from probability distributions.
- **Latin Hypercube Sampling**: Stratified sampling for efficient scenario generation.
- **User-defined scenarios**: Analysts can specify named scenarios with weights via `n.set_scenarios({name: weight, ...})`.

---

## Part IV: Market Simulation — How ALEA Derives Prices

### 4.1 Agent-Based Market Model (AMIRIS)

ALEA integrates the **AMIRIS** agent-based market model for endogenous price formation. AMIRIS simulates an **Energy-Only Market with hourly resolution**, where bids are submitted by market participants and the energy exchange ranks them according to the **merit order principle**.

**Agent types**:

| Agent Type | Role | Bidding Behaviour |
|---|---|---|
| **Markets** | Determine prices | Collect bids, clear market |
| **Traders** | Fulfil marketing strategies | Submit supply/demand bids |
| **Plant operators** | Control power plants | Bid at marginal cost + markup |
| **Flexibility providers** | Optimise dispatch | Use price forecasts, maximise profits with dynamic programming |
| **Information providers** | Create forecasts | Provide price and demand forecasts |
| **Policy** | Provide support | Model feed-in tariffs, capacity payments |

AMIRIS **computes electricity prices endogenously** based on the simulation of strategic bidding behaviour of prototyped market actors. It accounts for actor uncertainty and market distortions, and can run yearly simulations on laptops in less than a minute.

### 4.2 Reinforcement Learning Bidding (ASSUME)

ALEA integrates **ASSUME**, an open-source agent-based simulation framework that incorporates **multi-agent deep reinforcement learning** for modelling adaptive market participants. ASSUME's unique feature is the integration of **Deep Reinforcement Learning** methods into the behavioural strategies of market agents.

**Reinforcement learning approach**: Instead of bidding each unit independently, the RL agent observes the full portfolio state and learns a **joint bidding policy**. The observation space includes portfolio costs, market prices, and competitor behaviour. The agent outputs a **markup multiplier per cost bin per time step**.

This enables **dynamic strategy exploration**, where agents learn optimal bidding strategies over repeated market simulations, converging to Nash-equilibrium-like outcomes.

### 4.3 Capture Price Calculation

Capture price (market value) is the revenue-weighted mean price a generator earns:

$$\text{Capture Price}_i = \frac{\sum_t p_{i,t} \cdot \pi_t}{\sum_t p_{i,t}}$$

Where $p_{i,t}$ is the generation of asset $i$ at time $t$, and $\pi_t$ is the market price. The **capture rate** is:

$$\text{Capture Rate}_i = \frac{\text{Capture Price}_i}{\text{Time-Weighted Average Price}}$$

Capture rates decline as VRE penetration increases (cannibalisation effect), because solar and wind generate when prices are lowest.

---

## Part V: Outage Prediction — How ALEA Forecasts Disruptions

### 5.1 Satellite-Based Outage Detection (OWL-I Framework)

ALEA uses the **OWL-I (Outage Framework for Luminosity Interruptions)** methodology, which detects power outages from VIIRS/Black Marble nighttime light observations **without knowledge of the driver event or infrastructural records**.

**Step 1: Angular Effect Correction**

The raw daily radiance fluctuates due to the satellite's changing viewing angle. ALEA corrects for this by grouping observations by **Viewing Zenith Angle (VZA)** to establish a normal radiance baseline for each pixel and time.

**Step 2: Deconfounding**

Confounding factors — lunar illumination, satellite viewing geometry, snow albedo, and temporal factors — are **jointly corrected** in a unified framework. The deconfounded brightness is computed by comparing observed radiance ($L_{\text{obs}}$) with expected brightness predicted by a deconfounding linear model ($\hat{L}_{\text{dec}}$).

**Step 3: Outage Detection**

Outage fraction is derived from the deconfounded brightness signal using a **neural calibration model** that maps residual dimming to outage fraction. The method is **pixel-independent**, meaning it generalises to new regions without retraining.

**Step 4: Aggregation**

Pixel-level anomalies are aggregated to **0.01-degree grid zones**. The Ghana study found that this aggregation produced the **single largest improvement in detection performance**.

### 5.2 Weather-Driven Outage Forecasting

For countries with historical outage records, ALEA trains supervised machine learning models using weather, temporal, and historical features.

**Feature engineering**:

| Feature Category | Specific Features |
|---|---|
| **Temporal** | Hour, day of week, month, season |
| **Meteorological** | Temperature, wind speed, precipitation, humidity, heat index |
| **Historical** | 30-day and 90-day outage rates by grid zone |
| **Interaction** | Temperature × wind speed, heat index |

**Model selection**: Random Forest, XGBoost, and LightGBM are trained and evaluated per country. The Ghana study found that a **random forest** combining weather, temporal, and historical features achieved an **AUC of 0.8346**. The Algeria study achieved **99% accuracy** with precision/recall/F1 > 98%.

**Class imbalance handling**: Outages are rare events. ALEA uses **SMOTE (Synthetic Minority Over-sampling Technique)** to balance the training data.

### 5.3 Predictive Maintenance

For critical assets (transformers, circuit breakers), ALEA uses **survival analysis** with Cox Proportional Hazards models:

$$h(t | X) = h_0(t) \cdot \exp(\beta_1 X_1 + \beta_2 X_2 + \cdots + \beta_p X_p)$$

Where $h(t | X)$ is the hazard rate at time $t$ given covariates $X$ (age, loading factor, oil DGA, moisture content), $h_0(t)$ is the baseline hazard, and $\beta$ are coefficients learned from historical failure data.

The Nigeria study achieved **87% critical failure detection** with a **64% false alarm reduction** and **260% return on investment**.

---

## Part VI: Loss Mitigation — How ALEA Identifies and Reduces Losses

### 6.1 Loss Decomposition

ALEA decomposes total system losses into four components using **power flow tracing**:

1. **Load-driven losses**: Losses proportional to the square of load current.
2. **Generation-driven losses**: Losses due to the spatial mismatch between generation and load.
3. **Topology-driven losses**: Losses caused by network configuration and impedance.
4. **Weather-driven losses**: Losses influenced by temperature-dependent conductor resistance.

The decomposition uses **Virtual Contribution Theory**, where the negative value of branch loss is treated as the output of a virtual power source, allowing losses to be attributed to individual loads and generators.

### 6.2 TLENS — Critical Line Identification

ALEA computes **TLENS (Transmission Lines' Contribution to Energy Not Supplied)** , a novel resilience indicator that measures how specific line failures impact overall Energy Not Supplied (ENS):

$$\text{TLENS}_l = \Delta \text{ENS} \text{ when line } l \text{ fails}$$

The computation proceeds as follows:

1. Solve the base case LOPF to establish base ENS.
2. For each line $l$, deactivate the line and re-solve the LOPF.
3. Compute the change in ENS: $\text{TLENS}_l = \text{ENS}_{\text{post-outage}} - \text{ENS}_{\text{base}}$.
4. Rank lines by TLENS to identify critical corridors.

The Malawi study identified **Nanjoka–Nkhotakota, Nkhotakota–Dwangwa, Dwangwa–Chintheche, and Kapichila–Mlambe** as substantial ENS contributors, posing significant resilience risks.

### 6.3 Mitigation Option Ranking

Mitigation options are ranked by **cost-benefit analysis**:

$$\text{Payback}_i = \frac{\text{CAPEX}_i}{\text{Annual Savings}_i} = \frac{\text{CAPEX}_i}{\Delta \text{Loss}_i \cdot 8760 \cdot \text{Price}_i}$$

Options are categorised into four types:

| Category | Options |
|---|---|
| **Network reconfiguration** | Topology switching, phase shifting transformers |
| **Voltage optimisation** | Generator voltage setpoints, transformer taps, reactive compensation |
| **Distributed resources** | Optimal DG placement, storage dispatch, PV inverter power factor |
| **Network reinforcement** | Line upgrades, parallel lines, new substations |

---

## Part VII: What-If Scenario Engine — How ALEA Explores Futures

### 7.1 Parameter-Driven Simulation

The What-If Engine allows users to adjust **key parameters** and see results in near-real-time. Parameters are grouped into five categories:

| Category | Parameters | Range |
|---|---|---|
| **Demand** | Growth rate, electrification, peak multiplier | 0–8%, 30–100%, 0.8–1.5× |
| **Supply** | Coal EAF, renewable multiplier, hydrogen export | 30–80%, 0.5–3.0×, 0–500 TWh |
| **Costs** | Carbon price, gas price, battery cost | 0–200 $/tCO₂, 0.5–3.0×, 0.5–2.0× |
| **Policy** | Renewable target, coal phase-out year, transmission multiplier | 20–100%, 2030–2060, 0.5–2.0× |
| **Climate** | SSP pathway, drought frequency multiplier | SSP1-2.6 to SSP5-8.5, 0.5–3.0× |

### 7.2 Rapid Re-Solve and Caching

The What-If Engine uses **warm-starting** from the base network solution and **caching** of pre-computed scenario results. The cache key is a hash of all parameter values, ensuring that identical scenarios return cached results instantly.

### 7.3 Efficient Frontier Generation

The engine generates **efficient frontiers** by sweeping a single parameter across its range and solving the model at each point. For example, varying carbon price from 0 to 200 $/tCO₂ in 20 steps produces a frontier showing the trade-off between emissions and total system cost.

---

## Part VIII: Intelligence Scanning — How ALEA Discovers New Information

### 8.1 Signal Extraction Pipeline

The Intelligence Scanning module continuously monitors external sources and extracts **structured signals** from unstructured text.

**Signal taxonomy**:

| Signal Type | Model Impact |
|---|---|
| **Outage event** | Updates outage history; triggers retraining |
| **Generation investment** | Updates generation fleet and capacity expansion options |
| **Transmission investment** | Updates transmission topology |
| **Policy change** | Updates policy parameters |
| **Fuel price change** | Updates fuel cost parameters |
| **Tender/RFP** | Updates project pipeline |
| **Demand signal** | Updates demand projections |
| **Climate event** | Updates climate risk scenarios |

### 8.2 LLM-Based Extraction

ALEA uses **large language models (LLMs)** to extract signals from raw documents. The GLISSA framework (validated in Uganda) achieves a **91% success rate** for flagging outage-related social media posts.

The extraction prompt instructs the LLM to identify signal types, extract entities (country, capacity, technology, investment), and provide **evidence quotes** supporting each extraction. Every signal carries a **confidence score** and is placed in a **human review queue** before being committed to the model.

### 8.3 Human-in-the-Loop Validation

All extracted signals are reviewed by analysts who can **confirm**, **reject**, or **edit** the signal before it updates the model. The review queue is prioritised by a **priority score** computed from:

- Extraction confidence
- Source reliability
- Signal type impact
- Country data completeness
- Novelty (first report vs. corroborating report)

---

## Part IX: Periodic Reporting — How ALEA Communicates Insights

### 9.1 Report Generation Pipeline

Reports are generated on a schedule (daily, weekly, monthly, quarterly, annual) by the Reporting Orchestrator. Each report type has a **Jinja2 template** and a **data gathering function** that pulls the relevant metrics from the model outputs, database, and API.

### 9.2 Report Content by Cadence

| Report | Content | Primary Audience |
|---|---|---|
| **Daily** | Outage forecast, weather alerts, generation mix, price forecast, system alerts | Utility operators, traders |
| **Weekly** | Week-ahead outage outlook, market summary, renewable forecast, loss trends | Analysts, investors |
| **Monthly** | Market report, capacity update, generation statistics, outage statistics, resilience metrics | Regulators, policymakers |
| **Quarterly** | Market outlook, investment pipeline, scenario update, climate risk, resilience scorecard | DFIs, institutional investors |
| **Annual** | Continental energy outlook, investment requirements, CMP alignment, just transition metrics | AUDA-NEPAD, governments |

### 9.3 Distribution

Reports are distributed via **email**, **API**, **dashboard**, and **S3-compatible object storage**. Webhooks notify subscribers when new reports are published.

---

## Summary: The Complete Prediction Chain

| Layer | Input | Method | Output |
|---|---|---|---|
| **Planning** | Grid topology, generation assets, renewable profiles, demand | Linear optimal power flow with capacity expansion | Least-cost capacity mix, dispatch, nodal prices |
| **Sector Coupling** | Planning network + hydrogen, heat, transport, industry demands | Multi-energy carrier optimisation with Links and Stores | Inter-sector flows, hydrogen costs, industrial emissions |
| **Market Simulation** | Sector-coupled network + agent strategies | Agent-based bidding (AMIRIS) + RL (ASSUME) | Market prices, capture rates, PPA benchmarks |
| **Outage Prediction** | VIIRS radiance + weather + historical outages | OWL-I deconfounding + Random Forest/XGBoost | Outage probability by grid zone, confidence intervals |
| **Loss Mitigation** | Network topology + dispatch | Power flow tracing + TLENS | Loss decomposition, critical lines, mitigation payback |
| **Predictive Maintenance** | Asset metadata + SCADA + oil DGA | Cox Proportional Hazards survival analysis | Failure probability within horizon |
| **What-If** | All above + user parameters | Rapid re-solve with warm-start and caching | Scenario comparisons, efficient frontiers |
| **Intelligence Scanning** | News, tenders, social media, institutional sources | LLM extraction + human review | Structured signals updating model parameters |
| **Reporting** | All model outputs | Jinja2 templates + WeasyPrint | PDF/HTML reports on schedule |

The ALEA platform's predictive power derives not from any single model, but from the **integration of physical optimisation, market simulation, satellite-based detection, machine learning, and human-validated intelligence** into a unified, continuously updating system.