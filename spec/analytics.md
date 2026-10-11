# PyPSA-X Pan-African: Outage Prediction, Loss Mitigation & What-If Scenario Planning

## Extension Specification for Predictive Operations, Resilience Analytics, and Exploratory Planning

---

## Part I: Architectural Principles

### 1. Why These Capabilities Require a New Architecture

The base PyPSA-X Pan-African specification defines a **planning model** — it optimises capacity expansion and dispatch over multi-year horizons with perfect foresight. Outage prediction, transmission loss mitigation, and what-if scenario planning require a fundamentally different temporal and analytical posture:

- **Outage prediction** operates on **minutes to days** ahead, using statistical and machine learning models trained on historical fault and weather data. It is inherently probabilistic and data-driven, not optimisation-based.
- **Transmission loss mitigation** operates on **operational and planning horizons**, using the network's physical characteristics (impedance, topology, loading) to identify loss-reduction interventions. It requires the linear power flow and loss approximation capabilities already present in PyPSA.
- **What-if scenario planning** operates on **user-defined temporal horizons**, from real-time operational decisions to 30-year investment pathways. It requires an interactive, parameter-driven simulation engine that can re-solve the model rapidly.

These three capabilities share a common requirement: they must be **integrated with the planning model** but **executed independently**. The planning model provides the network topology, generation fleet, and demand profiles. The predictive and operational modules consume these as inputs and return probabilistic forecasts, mitigation options, and scenario comparisons.

### 2. Module Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: What-If Scenario Engine                           │
│  (Interactive parameter adjustment, rapid re-solve,         │
│   scenario comparison, trade-off visualisation)             │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Outage Prediction Module                          │
│  (ML models, satellite detection, weather integration,      │
│   probabilistic outage forecasting)                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Loss Mitigation Module                            │
│  (Loss decomposition, sensitivity analysis,                 │
│   mitigation option ranking, cost-benefit analysis)         │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Contingency & Resilience Engine                   │
│  (N-1 security constraints, BODF, ENS/TLENS,                │
│   stress-testing, Monte Carlo hazard simulation)            │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Operational Dispatch Engine                       │
│  (Unit commitment, sub-hourly resolution,                   │
│   rolling horizon, reserve co-optimisation)                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: PyPSA Planning Model                              │
│  (Capacity expansion, sector coupling,                      │
│   multi-horizon optimisation)                               │
└─────────────────────────────────────────────────────────────┘
```

**Why this layering**: Each layer depends only on the layers below it. The outage prediction module (Layer 5) consumes the network topology and generation fleet from Layer 1, but its outputs (probabilistic outage forecasts) feed into Layer 3 (contingency analysis) and Layer 6 (scenario planning). The loss mitigation module (Layer 4) uses PyPSA's linear power flow and loss approximation capabilities, which are part of Layer 1. This separation ensures that each module can be developed, tested, and deployed independently.

---

## Part II: Outage Prediction

### 3. Why Outage Prediction Matters for Africa

African power systems face outages from multiple, often interacting causes: aging infrastructure (Nigeria's grid has 70% of transformers exceeding design lifetime and 15% annual failure rates), extreme weather (high summer temperatures above 48°C in the Algerian Sahara, sandstorms damaging overhead infrastructure), and generation inadequacy (South Africa's load shedding, Ghana's "dumsor"). Machine learning techniques are being applied to enhance grid resilience in Africa, addressing intermittent renewable energy, limited grid visibility, and aging infrastructure.

### 4. Outage Prediction Methodology

#### 4.1 Data Requirements

| Data Category | Specific Data | Source | Direct Data Link |
|---|---|---|---|
| **Historical outage records** | Fault type, duration, location, cause | National utilities (Eskom, ECG, KPLC, etc.) | Eskom Data Portal: `https://www.eskom.co.za/dataportal/` |
| **Weather data** | Temperature, wind speed, precipitation, humidity, dust | ERA5 reanalysis | `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels` |
| **Satellite radiance** | Nightly VIIRS radiance for outage detection | NASA VIIRS | `https://www.earthdata.nasa.gov/` |
| **Grid asset data** | Transformer age, maintenance history, loading | National utilities | Country-specific portals |
| **Satellite-based outage labels** | Ground-truth outage labels from GridWatch sensors | GridWatch | `https://gridwatch.org/` |

**Why these data sources**: The Ghana study used NASA VIIRS satellite radiance paired with ground-truth outage labels from 147 GridWatch sensors across Greater Accra (2019–mid-2023). Spatially aggregating sensor sites into 0.01-degree patches produced the single largest improvement in detection performance. The best-performing model was a random forest combining weather, temporal, and historical features with an AUC of 0.8346. This demonstrates that **meteorological covariates can support outage detection in data-scarce power systems**.

#### 4.2 Model Architecture

The outage prediction module shall implement a **hybrid ensemble architecture** with three components:

**Component 1: Satellite-Based Outage Detection**

For countries with limited ground monitoring infrastructure, satellite-based detection provides an alternative. The pipeline shall:

1. **Ingest VIIRS nightly radiance data** from NASA's Earthdata portal.
2. **Aggregate radiance pixels into 0.01-degree patches** (the single largest performance improvement in the Ghana study).
3. **Train a random forest classifier** combining weather features (temperature, wind speed, precipitation), temporal features (hour, day, season), and historical outage rates.
4. **Validate against ground-truth labels** where available (GridWatch sensors, utility fault records).

**Component 2: Weather-Driven Outage Forecasting**

For countries with historical outage records, the module shall:

1. **Engineer features** from temporal, meteorological, and historical data, as demonstrated in the Adrar, Algeria study (99% accuracy, precision/recall/F1 > 98%).
2. **Train multiple models** — logistic regression, random forest, and XGBoost — and select the best performer per country.
3. **Time-match weather features** to the forecast horizon (e.g., 1 AM local time for satellite overpass).
4. **Produce probabilistic forecasts** with confidence intervals.

**Component 3: Predictive Maintenance for Critical Assets**

For transmission and distribution assets, the module shall:

1. **Ingest transformer oil data** (dissolved gas analysis, moisture content) for predictive modelling, as demonstrated in South African studies.
2. **Train survival models** for transformer failure prediction on 132 kV networks, as demonstrated in Uganda.
3. **Implement a machine learning framework** that identified 87% of critical failures while reducing false alarms by 64%, with a 260% return on investment, as demonstrated for Nigerian distribution transformers.

#### 4.3 Implementation

```python
# scripts/predict_outages.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support

class OutagePredictor:
    def __init__(self, country_iso, model_type="random_forest"):
        self.country = country_iso
        self.model = None
        self.feature_columns = []

    def load_historical_data(self, outage_records_path, weather_path):
        """Load and merge outage records with weather data."""
        outages = pd.read_csv(outage_records_path)
        weather = pd.read_csv(weather_path)
        # Time-match weather to outage events
        merged = pd.merge_asof(outages, weather, on='timestamp')
        return merged

    def engineer_features(self, df):
        """Engineer temporal, meteorological, and historical features."""
        df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
        df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.dayofweek
        df['month'] = pd.to_datetime(df['timestamp']).dt.month
        df['historical_outage_rate'] = df.groupby('grid_zone')['outage'].transform(
            lambda x: x.shift(1).rolling(30, min_periods=1).mean()
        )
        # Weather interaction features
        df['temp_wind_interaction'] = df['temperature'] * df['wind_speed']
        df['heat_index'] = df['temperature'] + 0.5 * df['humidity']
        self.feature_columns = ['hour', 'day_of_week', 'month',
                                'historical_outage_rate', 'temperature',
                                'wind_speed', 'precipitation', 'humidity',
                                'temp_wind_interaction', 'heat_index']
        return df

    def train(self, df):
        """Train the outage prediction model."""
        X = df[self.feature_columns]
        y = df['outage']
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        self.model = RandomForestClassifier(
            n_estimators=500, max_depth=15, min_samples_leaf=10,
            class_weight='balanced', random_state=42, n_jobs=-1
        )
        self.model.fit(X_train, y_train)
        y_pred_proba = self.model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_pred_proba)
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_test, (y_pred_proba > 0.5).astype(int), average='binary'
        )
        return {'auc': auc, 'precision': precision, 'recall': recall, 'f1': f1}

    def predict(self, forecast_df):
        """Produce probabilistic outage forecasts."""
        X = forecast_df[self.feature_columns]
        proba = self.model.predict_proba(X)[:, 1]
        return pd.DataFrame({
            'timestamp': forecast_df['timestamp'],
            'grid_zone': forecast_df['grid_zone'],
            'outage_probability': proba,
            'confidence_lower': proba - 0.1,
            'confidence_upper': proba + 0.1
        })
```

#### 4.4 Integration with PyPSA

Outage predictions feed into the PyPSA network as **probabilistic generator and branch availability profiles**. For generator outages, set `p_max_pu` to zero for a scenario-dependent outage period, as documented in PyPSA's stochastic optimisation guidance. For branch outages, use PyPSA's contingency analysis functions to compute post-outage line flows.

---

## Part III: Transmission Loss Mitigation

### 5. Why Loss Mitigation Matters

Minimising transmission losses is essential for ensuring efficient and reliable operation in large-scale power systems. Disregarding transmission losses overestimates optimal grid expansion by 20%. In African systems with long transmission distances and aging infrastructure, loss reduction can defer or avoid costly network upgrades.

### 6. Loss Mitigation Methodology

#### 6.1 Loss Decomposition

The module shall decompose total system losses into four components:

1. **Load-driven losses**: Losses proportional to the square of load current.
2. **Generation-driven losses**: Losses due to the spatial mismatch between generation and load.
3. **Topology-driven losses**: Losses caused by network configuration and impedance.
4. **Weather-driven losses**: Losses influenced by temperature-dependent conductor resistance.

This decomposition follows the approach of decoupling the impacts of changes in load, generation, and topology on overall system losses, which is increasingly required for evaluating long-term benefits of transmission expansion projects.

#### 6.2 Loss Approximation in PyPSA

PyPSA provides two methods for linearising the non-linear loss function:

- **Tangent-based approximation** (`define_tangent_loss_constraints()`): Uses tangent lines to approximate the quadratic loss curve.
- **Secant-based approximation with error control** (`define_secant_loss_constraints()`): Uses secant lines with explicit error bounds.

The module shall use the secant-based approximation with error control, configured via `transmission_losses` in the PyPSA optimisation call. A passed number denotes the number of tangents used for the piecewise linear approximation. Defaults to 0, which ignores losses.

#### 6.3 Mitigation Option Identification

The module shall identify and rank loss mitigation options across four categories:

**Category 1: Network Reconfiguration**

- **Topology switching**: Open/close switching devices to reroute power flows.
- **Phase shifting transformers**: Coordinated deployment and control to minimise active power losses, as demonstrated on the IEEE 300-bus system.
- **Loop connections**: Alternative supply routes that reduce losses in disaster-prone regions.

**Category 2: Voltage and Reactive Power Optimisation**

- **Generator voltage setpoints**: Optimise generator AVR setpoints to reduce losses.
- **Transformer tap positions**: Coordinated tap adjustment, as demonstrated with the HGAPSO framework (Hybrid Genetic Algorithm–Particle Swarm Optimization).
- **Reactive power compensation**: Capacitor banks, SVCs, and STATCOMs.

**Category 3: Distributed Generation and Storage**

- **Optimal DG placement**: Locate distributed generation to minimise losses.
- **Energy storage dispatch**: Use storage to reduce peak losses.
- **PV inverter power factor**: Adjust power factor of PV inverters to reduce line losses.

**Category 4: Network Reinforcement**

- **Line upgrades**: Reconductor with larger cross-section conductors.
- **Parallel lines**: Add parallel circuits to critical corridors.
- **New substations**: Add substations to reduce transmission distances.

#### 6.4 Implementation

```python
# scripts/mitigate_losses.py
import pypsa
import pandas as pd
import numpy as np

class LossMitigator:
    def __init__(self, network):
        self.n = network
        self.loss_components = {}

    def compute_base_losses(self, snapshot):
        """Compute base case losses without mitigation."""
        self.n.lpf(snapshot)
        line_losses = self.n.lines_t.p0.loc[snapshot].abs().sum()
        transformer_losses = self.n.transformers_t.p0.loc[snapshot].abs().sum()
        return line_losses + transformer_losses

    def decompose_losses(self, snapshot):
        """Decompose losses by driver."""
        # Load-driven: losses with flat generation
        # Generation-driven: losses with flat load
        # Topology-driven: losses with optimal topology
        base_losses = self.compute_base_losses(snapshot)
        self.loss_components = {
            'base': base_losses,
            'load_driven': self._compute_load_driven(snapshot),
            'generation_driven': self._compute_generation_driven(snapshot),
            'topology_driven': self._compute_topology_driven(snapshot)
        }
        return self.loss_components

    def identify_critical_lines(self, snapshot, n_outages=10):
        """Identify lines contributing most to losses using TLENS approach."""
        self.n.lpf(snapshot)
        # Compute base case line flows
        base_flows = self.n.lines_t.p0.loc[snapshot].abs()
        # Compute BODF for contingency analysis
        critical_lines = []
        for line in self.n.lines.index[:n_outages]:
            # Simulate outage of this line
            self.n.lines.loc[line, 'active'] = False
            self.n.lpf(snapshot)
            post_outage_flows = self.n.lines_t.p0.loc[snapshot].abs()
            # Compute change in losses
            loss_change = post_outage_flows.sum() - base_flows.sum()
            critical_lines.append({
                'line': line,
                'loss_change': loss_change,
                'loading_post_outage': post_outage_flows.max()
            })
            self.n.lines.loc[line, 'active'] = True
        return pd.DataFrame(critical_lines).sort_values(
            'loss_change', ascending=False
        )

    def rank_mitigation_options(self, snapshot, options_df):
        """Rank mitigation options by cost-benefit."""
        results = []
        for _, option in options_df.iterrows():
            # Apply option to network
            self._apply_option(option)
            # Re-solve
            self.n.lpf(snapshot)
            new_losses = self.compute_base_losses(snapshot)
            # Compute benefit
            loss_reduction = self.loss_components['base'] - new_losses
            results.append({
                'option': option['name'],
                'type': option['type'],
                'loss_reduction_MW': loss_reduction,
                'capex_USD': option['capex'],
                'opex_savings_USD_year': loss_reduction * 8760 * option['price_USD_MWh'],
                'payback_years': option['capex'] / (
                    loss_reduction * 8760 * option['price_USD_MWh']
                ) if loss_reduction > 0 else np.inf
            })
            self._revert_option(option)
        return pd.DataFrame(results).sort_values('payback_years')
```

#### 6.5 Resilience Metrics

The module shall compute the following resilience metrics for each transmission corridor:

| Metric | Definition | Formula |
|---|---|---|
| **Energy Not Served (ENS)** | Total energy not delivered during an outage | Sum of unserved load × duration |
| **Expected Energy Not Supplied (EENS)** | Probability-weighted ENS across scenarios | $\sum_s p_s \cdot ENS_s$ |
| **TLENS (Transmission Lines' Contribution to Energy Not Supplied)** | How specific line failures impact overall ENS | $\Delta ENS / \Delta P_{line}$ |
| **SAIDI** | System Average Interruption Duration Index | $\sum (r_i \times N_i) / N_T$ |
| **SAIFI** | System Average Interruption Frequency Index | $\sum N_i / N_T$ |
| **Load Not Served (LNS)** | Peak load not served during an outage | MW unserved at peak |

The TLENS metric, introduced for Malawi's transmission grid, measures how specific transmission line failures impact overall energy not supplied. Using TLENS, critical lines are identified, and redundancy effectiveness is evaluated. The study identified Nanjoka–Nkhotakota, Nkhotakota–Dwangwa, Dwangwa–Chintheche, and Kapichila–Mlambe as substantial ENS contributors, posing significant resilience risks.

---

## Part IV: What-If Scenario Planning

### 7. Why What-If Scenario Planning Matters

Scenario models help plan energy systems more effectively. They help planners simulate futures varying in demand, resource availability, and policy. Unlike deterministic projections of a few envisioned scenario cases, what-if planning identifies robust investments in an era of polycrisis and uncertainty. The output of scenario models should not be interpreted as predictions of the future energy system, but rather as a variety of "what-if" scenarios that can derive insights to support stakeholders' decision making.

### 8. Scenario Planning Engine

#### 8.1 Architecture

The what-if scenario engine shall be an **interactive, parameter-driven simulation layer** that sits above the PyPSA planning model. It shall support:

1. **Parameter sliders**: Users adjust key parameters and see results in near-real-time.
2. **Rapid re-solve**: Pre-computed scenario results are cached; new scenarios trigger on-demand solving.
3. **Scenario comparison**: Side-by-side comparison of up to four scenarios.
4. **Trade-off visualisation**: Efficient frontiers showing cost vs. risk, cost vs. emissions, etc.

#### 8.2 Scenario Parameters

| Parameter Category | Specific Parameters | Range | Default |
|---|---|---|---|
| **Demand** | Annual demand growth rate | 0–8% | CMP trajectory |
| | Electrification rate | 30–100% | Country-specific |
| | Peak demand multiplier | 0.8–1.5× | 1.0 |
| **Supply** | Coal EAF | 30–80% | Country-specific |
| | Renewable capacity multiplier | 0.5–3.0× | 1.0 |
| | Hydrogen export volume | 0–500 TWh/year | 0 |
| **Costs** | Carbon price | 0–200 USD/tCO₂ | 50 |
| | Gas price multiplier | 0.5–3.0× | 1.0 |
| | Battery cost multiplier | 0.5–2.0× | 1.0 |
| **Policy** | Renewable target | 20–100% | Country NDC |
| | Coal phase-out year | 2030–2060 | 2050 |
| | Transmission expansion multiplier | 0.5–2.0× | 1.0 |
| **Climate** | SSP pathway | SSP1-2.6 to SSP5-8.5 | SSP2-4.5 |
| | Drought frequency multiplier | 0.5–3.0× | 1.0 |

#### 8.3 Implementation

```python
# scripts/whatif_engine.py
import pypsa
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class ScenarioParameters:
    demand_growth: float = 0.04
    coal_eaf: float = 0.55
    carbon_price: float = 50.0
    gas_price_multiplier: float = 1.0
    renewable_multiplier: float = 1.0
    hydrogen_export: float = 0.0
    battery_cost_multiplier: float = 1.0
    ssp_pathway: str = "SSP2-4.5"
    drought_multiplier: float = 1.0

class WhatIfEngine:
    def __init__(self, base_network_path, cache_dir):
        self.base_network = pypsa.Network(base_network_path)
        self.cache_dir = cache_dir
        self.scenario_cache = {}

    def apply_parameters(self, params: ScenarioParameters):
        """Apply scenario parameters to a copy of the base network."""
        n = self.base_network.copy()
        # Demand scaling
        n.loads_t.p_set *= (1 + params.demand_growth) ** n.snapshots.year
        # Coal EAF
        coal_mask = n.generators.carrier == 'coal'
        n.generators.loc[coal_mask, 'p_max_pu'] = params.coal_eaf
        # Carbon price
        n.generators.loc[coal_mask, 'marginal_cost'] += (
            params.carbon_price * n.generators.loc[coal_mask, 'co2_emissions']
        )
        # Gas price
        gas_mask = n.generators.carrier == 'gas'
        n.generators.loc[gas_mask, 'marginal_cost'] *= params.gas_price_multiplier
        # Renewable multiplier
        for carrier in ['solar', 'onwind', 'offwind', 'hydro']:
            mask = n.generators.carrier == carrier
            n.generators.loc[mask, 'p_nom_max'] *= params.renewable_multiplier
        # Hydrogen export
        if params.hydrogen_export > 0:
            self._add_hydrogen_export(n, params.hydrogen_export)
        # Battery cost
        n.storage_units.loc[:, 'capital_cost'] *= params.battery_cost_multiplier
        return n

    def solve_scenario(self, params: ScenarioParameters,
                       cache_key: Optional[str] = None) -> Dict:
        """Solve a what-if scenario and cache results."""
        if cache_key and cache_key in self.scenario_cache:
            return self.scenario_cache[cache_key]
        n = self.apply_parameters(params)
        n.optimize(solver_name='gurobi', multi_investment_periods=True)
        results = {
            'total_cost': n.objective,
            'capacity_mix': n.generators.groupby('carrier')['p_nom_opt'].sum(),
            'generation_mix': n.generators_t.p.groupby(
                n.generators.carrier, axis=1
            ).sum(),
            'emissions': n.generators_t.p.multiply(
                n.generators.co2_emissions, axis=1
            ).sum(),
            'prices': n.buses_t.marginal_price.mean(),
            'curtailment': self._compute_curtailment(n)
        }
        if cache_key:
            self.scenario_cache[cache_key] = results
        return results

    def compare_scenarios(self, scenarios: List[ScenarioParameters]) -> pd.DataFrame:
        """Compare multiple scenarios side-by-side."""
        comparison = []
        for i, params in enumerate(scenarios):
            results = self.solve_scenario(params, cache_key=f"scenario_{i}")
            comparison.append({
                'scenario': i,
                'demand_growth': params.demand_growth,
                'coal_eaf': params.coal_eaf,
                'carbon_price': params.carbon_price,
                **results
            })
        return pd.DataFrame(comparison)

    def generate_efficient_frontier(self, param_name: str,
                                     param_range: np.ndarray,
                                     param_template: ScenarioParameters,
                                     n_points: int = 10) -> pd.DataFrame:
        """Generate efficient frontier for a single parameter."""
        frontier = []
        for value in np.linspace(param_range[0], param_range[1], n_points):
            params = ScenarioParameters(**{
                **param_template.__dict__,
                param_name: value
            })
            results = self.solve_scenario(params)
            frontier.append({
                param_name: value,
                'total_cost': results['total_cost'],
                'emissions': results['emissions'],
                'renewable_share': (
                    results['generation_mix'].get('solar', 0) +
                    results['generation_mix'].get('onwind', 0) +
                    results['generation_mix'].get('offwind', 0)
                ) / results['generation_mix'].sum()
            })
        return pd.DataFrame(frontier)
```

#### 8.4 What-If Questions the Engine Shall Answer

| Question Type | Example Question | Parameters Varied |
|---|---|---|
| **Demand uncertainty** | "What if demand grows at 6% instead of 4%?" | `demand_growth` |
| **Coal performance** | "What if coal EAF drops to 40%?" | `coal_eaf` |
| **Carbon policy** | "What if carbon price reaches $150/tCO₂?" | `carbon_price` |
| **Fuel prices** | "What if gas prices triple?" | `gas_price_multiplier` |
| **Technology costs** | "What if battery costs halve?" | `battery_cost_multiplier` |
| **Hydrogen demand** | "What if Europe demands 200 TWh/year of African hydrogen?" | `hydrogen_export` |
| **Climate** | "What if drought frequency doubles?" | `drought_multiplier` |
| **Combined** | "What if demand grows 6%, coal EAF drops to 40%, and carbon price reaches $150?" | Multiple |

---

## Part V: Integration with PyPSA-X Pan-African

### 9. Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│  PyPSA Planning Model (Layer 1)                              │
│  Outputs: network topology, generation fleet, demand,        │
│           renewable profiles, cost parameters                │
└──────────────────────┬───────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Outage      │ │ Loss        │ │ What-If     │
│ Prediction  │ │ Mitigation  │ │ Scenario    │
│ Module      │ │ Module      │ │ Engine      │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       ▼               ▼               ▼
┌──────────────────────────────────────────────────────────────┐
│  Contingency & Resilience Engine (Layer 3)                   │
│  Consumes: outage probabilities, loss metrics, scenario      │
│            parameters                                        │
│  Produces: ENS, EENS, TLENS, SAIDI, SAIFI, stress-test       │
│            results, resilience scores                        │
└──────────────────────────────────────────────────────────────┘
```

### 10. Configuration

```yaml
# config/predictive.yaml
outage_prediction:
  enabled: true
  model: "random_forest"  # or "xgboost", "logistic_regression"
  features:
    temporal: ["hour", "day_of_week", "month"]
    weather: ["temperature", "wind_speed", "precipitation", "humidity"]
    historical: ["outage_rate_30d", "outage_rate_90d"]
  satellite_detection:
    enabled: true
    source: "VIIRS"
    aggregation: "0.01_degree"
  predictive_maintenance:
    enabled: true
    asset_types: ["transformer", "circuit_breaker"]
    features: ["oil_dga", "age", "loading_history"]

loss_mitigation:
  enabled: true
  loss_approximation: "secant"  # or "tangent"
  n_tangents: 5
  mitigation_options:
    topology_switching: true
    phase_shifting: true
    voltage_optimisation: true
    dg_placement: true
    storage_dispatch: true
    line_upgrades: true
  resilience_metrics: ["ENS", "EENS", "TLENS", "SAIDI", "SAIFI"]

whatif:
  enabled: true
  cache_size: 100
  parameters:
    demand_growth: {min: 0.0, max: 0.08, default: 0.04}
    coal_eaf: {min: 0.3, max: 0.8, default: 0.55}
    carbon_price: {min: 0, max: 200, default: 50}
    gas_price_multiplier: {min: 0.5, max: 3.0, default: 1.0}
    renewable_multiplier: {min: 0.5, max: 3.0, default: 1.0}
    hydrogen_export: {min: 0, max: 500, default: 0}
    battery_cost_multiplier: {min: 0.5, max: 2.0, default: 1.0}
```

---

## Part VI: Computational Requirements

### 11. Performance Targets

| Capability | Problem Size | Target Solve Time | Hardware |
|---|---|---|---|
| **Outage prediction (training)** | 5 years hourly data, 10 features | < 30 minutes | 32 cores, 64 GB RAM |
| **Outage prediction (inference)** | 168-hour forecast, 55 nodes | < 10 seconds | 8 cores, 16 GB RAM |
| **Loss decomposition** | 55-node network, 1 snapshot | < 5 minutes | 16 cores, 32 GB RAM |
| **Contingency analysis (N-1)** | 200 branches, 8,760 snapshots | < 2 hours | 64 cores, 128 GB RAM |
| **What-if scenario (single solve)** | 55 nodes, 8,760 hours | < 2 hours | 64 cores, 256 GB RAM |
| **What-if efficient frontier (10 points)** | 55 nodes, 8,760 hours | < 20 hours | 64 cores, 256 GB RAM |

### 12. Computational Strategy

- **Outage prediction**: Train per-country models in parallel using joblib or Dask. Cache trained models with version control.
- **Loss mitigation**: Use PyPSA's `lpf_contingency()` for branch outage analysis. Pre-compute BODF matrices for all branches.
- **Contingency analysis**: Use N-1 security constraints via `n.optimize.optimize_security_constrained()`. To avoid the computational burden of full N-1, use `s_max_pu=0.7` to prevent line loading above 70% of rated capacity, as recommended in PyPSA documentation.
- **What-if**: Pre-compute and cache scenario results. Use warm-starting from the base network solution to accelerate re-solves.

---

## Part VII: Validation

### 13. Outage Prediction Validation

| Metric | Target | Benchmark |
|---|---|---|
| **AUC** | > 0.80 | Ghana study: 0.8346 |
| **Accuracy** | > 95% | Algeria study: 99% |
| **Precision** | > 90% | Algeria study: >98% |
| **Recall** | > 90% | Algeria study: >98% |
| **False alarm reduction** | > 50% | Nigeria study: 64% |

### 14. Loss Mitigation Validation

| Metric | Target | Benchmark |
|---|---|---|
| **Loss approximation error** | < 2% | PyPSA-Eur: neglecting losses overestimates grid expansion by 20% |
| **TLENS identification** | Top 10 critical lines correctly identified | Malawi study identified 4 critical corridors |
| **Cost-benefit accuracy** | < 15% error vs. full AC power flow | Standard benchmark |

### 15. What-If Scenario Validation

| Metric | Target | Benchmark |
|---|---|---|
| **Scenario reproducibility** | Identical results to machine precision | Required for audit trails |
| **Parameter sensitivity** | Monotonic response to parameter changes | Required for intuitive user experience |
| **Cross-model consistency** | < 10% divergence from PyPSA-Earth | OASES continental study |

---

## Part VIII: Delivery Integration

### 16. API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/outages/predict` | POST | Predict outages for a country and time horizon |
| `/api/v1/outages/history` | GET | Retrieve historical outage data |
| `/api/v1/losses/decompose` | GET | Decompose losses by driver |
| `/api/v1/losses/mitigate` | POST | Rank mitigation options |
| `/api/v1/resilience/metrics` | GET | Compute ENS, EENS, TLENS, SAIDI, SAIFI |
| `/api/v1/whatif/scenario` | POST | Solve a what-if scenario |
| `/api/v1/whatif/compare` | POST | Compare multiple scenarios |
| `/api/v1/whatif/frontier` | POST | Generate efficient frontier |

### 17. Dashboard Integration

The dashboard shall include three new interactive views:

1. **Outage Prediction View**: Map of outage probabilities by grid zone, with time-series forecast and confidence intervals.
2. **Loss Mitigation View**: Network map with loss intensity overlay, critical line highlighting (TLENS), and ranked mitigation options with payback periods.
3. **What-If View**: Parameter sliders with real-time result updates, scenario comparison charts, and efficient frontier visualisation.

---

## Part IX: Summary

This specification extends PyPSA-X Pan-African with three capabilities that transform it from a planning model into a **predictive, operational, and exploratory decision-support platform**:

1. **Outage Prediction**: Machine learning models trained on historical fault, weather, and satellite data, producing probabilistic outage forecasts for every country and grid zone.

2. **Transmission Loss Mitigation**: Loss decomposition, critical line identification (TLENS), mitigation option ranking, and resilience metrics (ENS, EENS, SAIDI, SAIFI).

3. **What-If Scenario Planning**: Interactive parameter adjustment, rapid re-solve, scenario comparison, and efficient frontier generation for exploring robust investment pathways.

These capabilities are built on PyPSA's existing power flow, contingency analysis, and optimisation engines, extended with data science and interactive delivery layers. They enable PyPSA-X Pan-African to answer not just "what is the least-cost system?" but "what could go wrong?", "how do we mitigate it?", and "what if the future unfolds differently?"