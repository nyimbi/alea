# ALEA: Parameter Interdependency Framework

## Systems of Equations Relating the 784 Parameters

---

## 1. The Direct Answer

**Yes. Absolutely. This is not optional — it is the single most important architectural decision in the entire platform.**

The 784 parameters are **not independent knobs**. They form a **coupled system of equations**. Changing one parameter propagates through dozens of others. If ALEA treats parameters as independent, it will produce **physically impossible, economically inconsistent, or self-contradictory scenarios**. A user could set a carbon price, a coal retirement schedule, a demand growth rate, and a renewable target that are mutually incompatible — and the model would happily solve and return garbage.

The what-if engine must therefore be built on a **Parameter Relationship Graph (PRG)** — a directed acyclic graph of typed equations that defines how every parameter relates to every other parameter, which parameters are free (endogenous decision variables), which are fixed (exogenous inputs), and which are determined (derived outputs).

---

## 2. Why Parameters Are Coupled: Seven Classes of Relationships

Every relationship between parameters falls into one of seven classes. Each class requires a different mathematical treatment.

| Class | Nature | Example | Treatment |
|---|---|---|---|
| **1. Physical Laws** | Inviolable physics | Energy balance, Kirchhoff's laws, thermodynamics | Hard equality constraints in the optimisation |
| **2. Accounting Identities** | Definitional | Total cost = Σ(capex × capacity) + Σ(opex × generation) | Hard equality constraints or post-processing |
| **3. Technical Constraints** | Engineering limits | Reserve margin, ramp rates, min stable levels | Inequality constraints in the optimisation |
| **4. Economic Relationships** | Behavioural | Demand elasticity, learning curves, CAPM | Parametric equations (endogenous or exogenous) |
| **5. Policy Constraints** | Regulatory | Renewable targets, carbon caps, local content | Inequality constraints or penalties |
| **6. Feedback Loops** | Dynamic | Higher VRE → lower capture price → lower VRE investment | Iterative solving or system dynamics |
| **7. Temporal Relationships** | Intertemporal | Investment lead time, learning by doing, retirement | Multi-period constraints |

---

## 3. The Parameter Relationship Graph (PRG)

### 3.1 Formal Definition

The PRG is a directed graph **G = (P, E)** where:

- **P** = set of 784 parameters
- **E** = set of directed edges, each representing an equation relating two or more parameters
- Each edge has a **type** (equality, inequality, functional, stochastic)
- Each edge has a **direction** (which parameter determines which)
- Each parameter has a **role**:
  - **Exogenous** (input): set by the user or external data
  - **Endogenous** (decision): determined by the optimisation
  - **Derived** (output): computed from other parameters
  - **Free** (unconstrained): available to be set by user without consistency check

### 3.2 Parameter Roles

| Role | Count | Description | Example |
|---|---|---|---|
| **Exogenous** | ~420 | Set by user or external data | `carbon_price`, `demand_growth_rate`, `capex_solar_pv` |
| **Endogenous** | ~180 | Determined by the optimisation | `coal_capacity`, `solar_pv_capacity`, `interconnector_capacity` |
| **Derived** | ~140 | Computed from other parameters | `lcoe`, `capture_price`, `dscr`, `total_emissions` |
| **Free** | ~44 | Metadata, tags, descriptions | `scenario_tag`, `scenario_description` |

### 3.3 Dependency Direction

Not all relationships are bidirectional. The PRG must encode **causality**:

- **Exogenous → Endogenous**: The user sets carbon price; the model determines coal capacity.
- **Endogenous → Derived**: The model determines capacity; the derived calculation computes LCOE.
- **Derived → Derived**: LCOE feeds into capture price, which feeds into PPA benchmark.
- **Endogenous ↔ Endogenous**: Capacity and dispatch are jointly determined by the optimisation.

### 3.4 The Dependency DAG (Simplified)

```
┌─────────────────────────────────────────────────────────────────────┐
│  EXOGENOUS PARAMETERS (User-Set)                                    │
│  carbon_price, demand_growth_rate, capex_solar_pv, fuel_cost_gas,  │
│  discount_rate, ssp_pathway, reserve_margin, renewable_target, ... │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OPTIMISATION MODEL (Endogenous)                                    │
│  capacity_mix, dispatch, storage_operation, transmission_flow,     │
│  cross_border_trade, curtailment, emissions, ...                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DERIVED QUANTITIES (Computed)                                      │
│  lcoe, capture_price, ppa_benchmark, dscr, irr, npv, saidi, saifi, │
│  energy_poverty_rate, jobs, health_impact, ...                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. The Systems of Equations

### 4.1 System 1: Energy Balance (Physical Law)

**Purpose**: Ensure energy conservation at every node, every carrier, every time step.

**Equations**:

$$\sum_{g \in G_n} p_{g,t} + \sum_{s \in S_n} (d_{s,t} - c_{s,t}) + \sum_{l \in L_n} f_{l,t} + \sum_{k \in K_n} h_{k,t} = D_{n,t} + \sum_{l \in L_n^{out}} f_{l,t} + \text{curtailment}_{n,t} + \text{losses}_{n,t}$$

**Parameters involved**: generation, storage dispatch, storage charge, line flows, link flows, demand, curtailment, losses.

**Type**: Hard equality constraint in the LOPF.

**Implementation**: `pypsa.Network.optimize()` — the nodal balance constraint is built automatically.

---

### 4.2 System 2: Cost Accounting (Accounting Identity)

**Purpose**: Ensure total system cost equals the sum of all cost components.

**Equations**:

$$\text{Total Cost} = \sum_{g} (c_g^{\text{capex}} \cdot \bar{P}_g + c_g^{\text{fom}} \cdot \bar{P}_g) + \sum_{g,t} (c_g^{\text{vom}} + c_g^{\text{fuel}}/\eta_g) \cdot p_{g,t} + \sum_{l} c_l^{\text{capex}} \cdot F_l + \sum_{s} c_s^{\text{capex}} \cdot \bar{E}_s$$

**Derived identities**:

$$\text{LCOE}_g = \frac{c_g^{\text{capex}} \cdot \text{CRF} + c_g^{\text{fom}}}{\text{CF}_g \cdot 8760} + c_g^{\text{vom}} + \frac{c_g^{\text{fuel}}}{\eta_g}$$

$$\text{CRF} = \frac{r(1+r)^n}{(1+r)^n - 1}$$

Where $r$ is the discount rate and $n$ is the asset life.

**Parameters involved**: `capex_*`, `opex_fixed_*`, `opex_variable_*`, `fuel_cost_*`, `discount_rate`, `efficiency`, `capacity_factor`, `lcoe`.

**Type**: Accounting identity — hard equality for total cost; derived formula for LCOE.

**Implementation**: PyPSA objective function + post-processing LCOE calculator.

---

### 4.3 System 3: Emissions Accounting (Physical + Accounting)

**Purpose**: Ensure emissions equal the sum of emissions from all sources.

**Equations**:

$$\text{CO}_2 = \sum_{g,t} p_{g,t} \cdot \text{EF}_g + \sum_{k,t} h_{k,t} \cdot \text{EF}_k - \sum_{g,t} p_{g,t}^{\text{CCS}} \cdot \eta^{\text{capture}} \cdot \text{EF}_g$$

**Carbon price interaction**:

$$\text{Carbon Cost} = \text{CO}_2 \cdot \text{carbon\_price} \cdot \text{coverage}$$

**Parameters involved**: `carbon_price`, `carbon_tax_rate`, `ets_cap`, `co2_emissions`, `ccs_adoption`, `emission_factor`.

**Type**: Physical accounting identity + economic relationship.

**Implementation**: PyPSA `n.generators.co2_emissions` + custom carbon price constraint.

---

### 4.4 System 4: Demand-Supply Equilibrium (Economic Law)

**Purpose**: Ensure demand equals supply at the market clearing price.

**Equations**:

$$D_{n,t}(P_{n,t}) = \sum_g p_{g,t}(P_{n,t}) + \sum_s d_{s,t}(P_{n,t}) + \sum_l f_{l,t}(P_{n,t})$$

**Elasticity relationship**:

$$\frac{\Delta D_{n,t}}{D_{n,t}} = \varepsilon \cdot \frac{\Delta P_{n,t}}{P_{n,t}}$$

Where $\varepsilon$ is the price elasticity of demand.

**Parameters involved**: `demand_growth_rate`, `demand_response_potential`, `regulated_tariff_rate`, `market_concentration`, `price_elasticity`.

**Type**: Economic equilibrium — solved by the optimisation (dual variable = LMP).

**Implementation**: PyPSA LOPF — the marginal price of the nodal balance constraint IS the LMP. Demand elasticity requires custom formulation (elastic demand curve).

---

### 4.5 System 5: Financial Identities (Accounting)

**Purpose**: Ensure financial metrics are internally consistent.

**Equations**:

**WACC**:
$$\text{WACC} = \frac{E}{V} \cdot R_e + \frac{D}{V} \cdot R_d \cdot (1 - \tau)$$

**CAPM**:
$$R_e = R_f + \beta \cdot (R_m - R_f) + \text{country\_risk\_premium}$$

**DSCR**:
$$\text{DSCR}_t = \frac{\text{CFADS}_t}{\text{Debt Service}_t} = \frac{\text{Revenue}_t - \text{OPEX}_t - \text{Tax}_t}{\text{Principal}_t + \text{Interest}_t}$$

**IRR**:
$$\text{NPV} = \sum_{t=0}^{T} \frac{\text{CF}_t}{(1 + \text{IRR})^t} = 0$$

**LCOE**:
$$\text{LCOE} = \frac{\sum_t \frac{\text{CAPEX}_t + \text{OPEX}_t + \text{Fuel}_t}{(1+r)^t}}{\sum_t \frac{\text{Generation}_t}{(1+r)^t}}$$

**Parameters involved**: `wacc`, `cost_of_equity`, `cost_of_debt`, `gearing_ratio`, `debt_service_coverage_ratio`, `equity_return_target`, `project_irr_hurdle`, `lcoe`.

**Type**: Accounting identities — hard equalities.

**Implementation**: `numpy_financial.irr`, `numpy_financial.npv`, custom DSCR calculator, `wacc-estimator`.

---

### 4.6 System 6: Learning Curves (Economic Feedback)

**Purpose**: Model endogenous technology cost reduction as a function of cumulative deployment.

**Equations**:

$$C_t = C_0 \cdot \left(\frac{Q_t}{Q_0}\right)^{-b}, \quad b = -\frac{\log_2(1 - \text{LR})}{\log_2(2)}$$

Where:
- $C_t$ = cost at time $t$
- $Q_t$ = cumulative capacity at time $t$
- $b$ = learning exponent
- $\text{LR}$ = learning rate (e.g., 20% for solar)

**Two-factor learning curve** (with R&D):

$$C_t = C_0 \cdot \left(\frac{Q_t}{Q_0}\right)^{-b_1} \cdot \left(\frac{RD_t}{RD_0}\right)^{-b_2}$$

**Parameters involved**: `solar_pv_learning_rate`, `battery_learning_rate`, `electrolyser_learning_rate`, `cumulative_capacity`, `technology_cost`.

**Type**: Endogenous feedback — requires iterative solving or mixed-integer linearisation.

**Implementation**: PyPSA does not natively support endogenous learning. Requires custom `linopy` constraints with logarithmic linearisation.

---

### 4.7 System 7: Reserve Margin (Technical Constraint)

**Purpose**: Ensure adequate capacity to meet peak demand plus reserves.

**Equations**:

$$\text{Reserve Margin} = \frac{\sum_g \bar{P}_g \cdot (1 - \text{FOR}_g) - D_{\text{peak}}}{D_{\text{peak}}} \geq \text{RM}_{\text{min}}$$

**Capacity credit** for VRE:

$$\text{Effective Capacity} = \sum_g \bar{P}_g \cdot \text{CC}_g$$

Where CC is the capacity credit (e.g., 10–30% for solar, 20–40% for wind).

**Parameters involved**: `reserve_margin`, `planning_reserve_margin`, `forced_outage_rate`, `peak_demand_multiplier`, `capacity_credit`.

**Type**: Hard inequality constraint.

**Implementation**: Custom `linopy` constraint on installed capacity.

---

### 4.8 System 8: Inertia Constraint (Physical + Technical)

**Purpose**: Ensure system inertia is sufficient for frequency stability.

**Equations**:

$$\sum_g \bar{P}_g \cdot H_g \cdot (1 - \text{VRE share}) \geq \text{Inertia}_{\text{min}}$$

Where $H_g$ is the inertia constant (MWs/MVA) for synchronous generators.

**Parameters involved**: `inertia_requirement`, `renewable_penetration_limit`, `synchronous_condenser_capacity`.

**Type**: Hard inequality constraint.

**Implementation**: Custom `linopy` constraint.

---

### 4.9 System 9: Water-Energy Nexus (Physical)

**Purpose**: Ensure water consumption for cooling and hydrogen production does not exceed availability.

**Equations**:

$$\sum_g p_{g,t} \cdot w_g + \sum_k h_{k,t} \cdot w_k \leq W_{n,t}$$

Where $w_g$ is water intensity (m³/MWh) and $W_{n,t}$ is water availability.

**Parameters involved**: `cooling_water_demand`, `water_availability`, `desalination_capacity`, `hydrogen_production_demand`.

**Type**: Hard inequality constraint.

**Implementation**: Custom `linopy` constraint linked to hydrology model.

---

### 4.10 System 10: Capture Price (Market Identity)

**Purpose**: Ensure capture price is consistent with dispatch and prices.

**Equations**:

$$\text{Capture Price}_g = \frac{\sum_t p_{g,t} \cdot \pi_t}{\sum_t p_{g,t}}$$

$$\text{Capture Rate}_g = \frac{\text{Capture Price}_g}{\bar{\pi}}$$

Where $\pi_t$ is the market price and $\bar{\pi}$ is the time-weighted average.

**Cannibalisation relationship**:

$$\text{Capture Rate}_g = f(\text{VRE Penetration}) \quad \text{(non-linear, empirically calibrated)}$$

**Parameters involved**: `capture_price`, `capture_rate`, `ppa_benchmark`, `renewable_penetration_limit`.

**Type**: Derived identity + empirical relationship.

**Implementation**: Post-processing after LOPF solve.

---

### 4.11 System 11: Reliability Indices (Accounting)

**Purpose**: Ensure reliability metrics are consistent with outage data.

**Equations**:

$$\text{SAIDI} = \frac{\sum_i r_i \cdot N_i}{N_T}$$

$$\text{SAIFI} = \frac{\sum_i N_i}{N_T}$$

$$\text{ENS} = \sum_t \sum_n (D_{n,t} - \text{served}_{n,t})$$

$$\text{EENS} = \sum_s p_s \cdot \text{ENS}_s$$

$$\text{TLENS}_l = \text{ENS}(\text{without line } l) - \text{ENS}(\text{base})$$

**Parameters involved**: `grid_reliability_target`, `grid_reliability_saifi`, `outage_duration`, `outage_frequency`, `value_of_lost_load`.

**Type**: Accounting identities + stochastic aggregation.

**Implementation**: Post-processing after contingency analysis.

---

### 4.12 System 12: Employment (Input-Output)

**Purpose**: Ensure employment estimates are consistent with capacity and generation.

**Equations**:

$$\text{Direct Jobs} = \sum_g \bar{P}_g \cdot \text{EF}_g^{\text{direct}} + \sum_g E_g \cdot \text{EF}_g^{\text{O\&M}}$$

$$\text{Indirect Jobs} = \text{Direct Jobs} \cdot \text{Multiplier}^{\text{indirect}}$$

$$\text{Induced Jobs} = \text{Direct Jobs} \cdot \text{Multiplier}^{\text{induced}}$$

**Parameters involved**: `employment_factor_*`, `direct_jobs`, `indirect_jobs`, `induced_jobs`, `local_content_employment`.

**Type**: Input-output accounting.

**Implementation**: `pymrio` for input-output analysis.

---

### 4.13 System 13: Health Impact (Epidemiological)

**Purpose**: Ensure health impact estimates are consistent with emissions.

**Equations**:

$$\text{Premature Deaths} = \text{Population} \cdot \text{Baseline Mortality} \cdot \text{Relative Risk}(\text{PM}_{2.5})$$

$$\text{DALYs} = \text{Premature Deaths} \cdot \text{YLL} + \text{Morbidity} \cdot \text{YLD}$$

**Parameters involved**: `pm25_emissions`, `health_impact_mortality`, `health_impact_dalys`, `healthcare_cost_per_case`.

**Type**: Epidemiological concentration-response function.

**Implementation**: `AirQ+` (WHO) or custom concentration-response.

---

### 4.14 System 14: Affordability (Economic)

**Purpose**: Ensure affordability metrics are consistent with tariffs and income.

**Equations**:

$$\text{Energy Burden} = \frac{\text{Monthly Bill}}{\text{Monthly Income}}$$

$$\text{Energy Poverty Rate} = \frac{\text{Households with Energy Burden} > 10\%}{\text{Total Households}}$$

**Parameters involved**: `affordability_threshold`, `energy_poverty_rate`, `lifeline_tariff`, `willingness_to_pay`, `social_tariff`.

**Type**: Economic identity + distributional analysis.

**Implementation**: Custom affordability calculator with income distribution.

---

### 4.15 System 15: Feedback Loop — Price-Demand (Dynamic)

**Purpose**: Model the feedback between prices and demand.

**Equations**:

$$D_t = D_{t-1} \cdot (1 + g) \cdot \left(\frac{P_t}{P_{t-1}}\right)^{\varepsilon}$$

Where $g$ is the baseline growth rate and $\varepsilon$ is the elasticity.

**Parameters involved**: `demand_growth_rate`, `regulated_tariff_rate`, `price_elasticity`.

**Type**: Dynamic feedback — requires iterative solving.

**Implementation**: Custom iteration loop around LOPF.

---

### 4.16 System 16: Feedback Loop — VRE Investment (Dynamic)

**Purpose**: Model the feedback between VRE penetration and capture prices.

**Equations**:

$$I_t^{\text{VRE}} = f(\text{Expected Capture Price}_t, \text{Cost}_t)$$

$$\text{Capture Price}_t = g(\text{VRE Penetration}_t)$$

$$\text{VRE Penetration}_t = \frac{\sum_{t' \leq t} I_{t'}^{\text{VRE}}}{\text{Demand}_t}$$

**Parameters involved**: `solar_pv_capacity`, `wind_onshore_capacity`, `capture_price`, `capture_rate`, `renewable_target`.

**Type**: Dynamic feedback — solved by multi-period optimisation or iterative myopic solving.

**Implementation**: PyPSA multi-investment with capture price feedback.

---

### 4.17 System 17: Carbon Price Trajectory (Policy)

**Purpose**: Model the relationship between carbon price, emissions, and policy targets.

**Equations**:

$$\text{Emissions}_t = \text{Emissions}_{t-1} \cdot (1 - \text{reduction rate}(\text{carbon price}_t))$$

$$\text{Carbon Revenue}_t = \text{Emissions}_t \cdot \text{carbon price}_t \cdot \text{coverage}$$

**Parameters involved**: `carbon_price`, `carbon_tax_rate`, `ets_cap`, `carbon_price_escalation`, `carbon_price_coverage`.

**Type**: Policy relationship — exogenous or endogenous depending on scenario.

**Implementation**: PyPSA carbon price constraint + custom revenue calculator.

---

### 4.18 System 18: Technology Cost Trajectory (Learning + Exogenous)

**Purpose**: Model the relationship between technology deployment and cost.

**Equations**:

$$C_t = C_0 \cdot (1 - \text{exogenous trend})^t \cdot \left(\frac{Q_t}{Q_0}\right)^{-b}$$

**Parameters involved**: `solar_pv_cost`, `solar_pv_learning_rate`, `wind_onshore_cost`, `battery_cost`, `electrolyser_cost`.

**Type**: Hybrid — exogenous trend + endogenous learning.

**Implementation**: Custom learning curve with optional endogenous feedback.

---

### 4.19 System 19: Debt Sizing (Financial)

**Purpose**: Ensure debt size is consistent with cash flows and DSCR.

**Equations**:

$$\text{Debt Size} = \max \left\{ D : \min_t \text{DSCR}_t \geq \text{DSCR}_{\text{min}} \right\}$$

**Parameters involved**: `debt_tenor`, `interest_rate_debt`, `debt_service_coverage_ratio`, `gearing_ratio`, `project_irr_hurdle`.

**Type**: Financial constraint — solved by iterative debt sizing.

**Implementation**: Custom debt sizing algorithm (iterative).

---

### 4.20 System 20: PPA Pricing (Contractual)

**Purpose**: Ensure PPA price is consistent with costs, returns, and risk.

**Equations**:

$$\text{PPA Price} = \frac{\text{LCOE} + \text{Risk Premium} + \text{Return}}{\text{Availability}}$$

**Parameters involved**: `ppa_pricing_formula`, `lcoe`, `offtake_risk_premium`, `currency_hedge_cost`, `equity_return_target`.

**Type**: Contractual relationship — derived from financial model.

**Implementation**: Custom PPA pricing calculator.

---

## 5. The Complete Equation System Count

| # | System | Equations | Parameters Linked | Type |
|---|---|---|---|---|
| 1 | Energy Balance | ~55,000 (per node-time) | 45 | Hard equality |
| 2 | Cost Accounting | ~12 | 30 | Hard equality + derived |
| 3 | Emissions Accounting | ~8,760 (per time) | 15 | Hard equality |
| 4 | Demand-Supply Equilibrium | ~55,000 | 20 | Optimisation dual |
| 5 | Financial Identities | ~25 | 22 | Accounting |
| 6 | Learning Curves | ~200 (per technology-year) | 12 | Endogenous feedback |
| 7 | Reserve Margin | ~10 | 8 | Hard inequality |
| 8 | Inertia Constraint | ~8,760 | 6 | Hard inequality |
| 9 | Water-Energy Nexus | ~55,000 | 12 | Hard inequality |
| 10 | Capture Price | ~500 | 8 | Derived |
| 11 | Reliability Indices | ~20 | 10 | Accounting |
| 12 | Employment | ~100 | 10 | Input-output |
| 13 | Health Impact | ~50 | 8 | Epidemiological |
| 14 | Affordability | ~50 | 8 | Economic |
| 15 | Price-Demand Feedback | Iterative | 5 | Dynamic |
| 16 | VRE Investment Feedback | Iterative | 8 | Dynamic |
| 17 | Carbon Price Trajectory | ~50 | 8 | Policy |
| 18 | Technology Cost Trajectory | ~200 | 12 | Learning |
| 19 | Debt Sizing | Iterative | 8 | Financial |
| 20 | PPA Pricing | ~10 | 6 | Contractual |

**Total: ~120,000 constraints + 20 systems of equations**

---

## 6. Implementation Architecture

### 6.1 The Parameter Relationship Engine (PRE)

The PRE is a new subsystem that sits between the user and the optimisation model. Its responsibilities:

1. **Parse the PRG** — load the dependency graph and equation library.
2. **Validate consistency** — check that user-set parameters satisfy all constraints.
3. **Propagate changes** — when a parameter changes, update all dependent parameters.
4. **Detect conflicts** — flag over-determined or under-determined systems.
5. **Suggest corrections** — propose parameter adjustments to restore consistency.
6. **Feed the optimiser** — translate equations into PyPSA/Linopy constraints.

### 6.2 Implementation Stack

| Component | Purpose | Python Library |
|---|---|---|
| **Dependency graph** | Store PRG | `networkx` |
| **Symbolic equations** | Represent relationships | `sympy` |
| **Non-linear solving** | Solve coupled systems | `scipy.optimize`, `casadi` |
| **Constraint generation** | Translate to LP constraints | `linopy`, `pyomo` |
| **Type validation** | Ensure parameter types | `pydantic` |
| **Consistency checking** | Detect conflicts | Custom SAT/SMT |
| **Iterative solving** | Handle feedback loops | Custom convergence loop |
| **Financial modelling** | DSCR, IRR, WACC | `numpy_financial`, `pyfinance` |
| **Input-output** | Employment multipliers | `pymrio` |
| **Epidemiological** | Health impact | `AirQ+` bindings |

### 6.3 The Consistency Engine

```python
# scripts/pre/consistency_engine.py
import networkx as nx
import sympy as sp
from pydantic import BaseModel, validator

class ParameterRelationshipEngine:
    def __init__(self, prg_path: str):
        self.graph = nx.read_gml(prg_path)
        self.equations = self._load_equations()
        self.parameters = {}

    def set_parameter(self, name: str, value: float):
        """Set a parameter and propagate to all dependents."""
        self.parameters[name] = value
        # Topological sort of dependents
        dependents = nx.descendants(self.graph, name)
        for dep in nx.topological_sort(self.graph.subgraph(dependents)):
            if dep in self.equations:
                self.parameters[dep] = self._evaluate(dep)

    def check_consistency(self) -> list:
        """Check all equations are satisfied within tolerance."""
        violations = []
        for eq_name, eq in self.equations.items():
            residual = eq.evaluate(self.parameters)
            if abs(residual) > eq.tolerance:
                violations.append({
                    "equation": eq_name,
                    "residual": residual,
                    "parameters": eq.parameters,
                    "suggestion": self._suggest_correction(eq, residual)
                })
        return violations

    def detect_conflicts(self) -> list:
        """Detect over-determined or under-determined systems."""
        # Count equations vs. free parameters
        free_params = [p for p in self.parameters if self._is_free(p)]
        equations = [e for e in self.equations if e.is_active]
        if len(equations) > len(free_params):
            return [{"type": "over_determined", "surplus": len(equations) - len(free_params)}]
        elif len(equations) < len(free_params):
            return [{"type": "under_determined", "deficit": len(free_params) - len(equations)}]
        return []
```

### 6.4 The Feedback Loop Solver

```python
# scripts/pre/feedback_solver.py
class FeedbackSolver:
    def solve(self, params, max_iter=20, tol=1e-4):
        """Iteratively solve feedback loops until convergence."""
        for i in range(max_iter):
            prev_params = params.copy()
            # Solve the optimisation with current parameters
            result = self._solve_optimisation(params)
            # Update feedback-dependent parameters
            params = self._update_feedback(params, result)
            # Check convergence
            if self._converged(prev_params, params, tol):
                return params, result
        raise ConvergenceError(f"Did not converge in {max_iter} iterations")
```

---

## 7. Specific Equation Examples (Detailed)

### 7.1 The LCOE Equation

$$\text{LCOE} = \frac{\sum_{t=0}^{T} \frac{I_t + M_t + F_t}{(1+r)^t}}{\sum_{t=0}^{T} \frac{E_t}{(1+r)^t}}$$

**Expanded**:
- $I_t$ = investment in year $t$ = `capex_solar_pv` × capacity added
- $M_t$ = O&M in year $t$ = `opex_fixed_solar` × capacity + `opex_variable_solar` × generation
- $F_t$ = fuel cost in year $t$ = 0 for solar
- $E_t$ = generation in year $t$ = `solar_pv_capacity` × `solar_pv_capacity_factor` × 8760
- $r$ = `discount_rate`

**Dependencies**: `capex_solar_pv`, `opex_fixed_solar`, `opex_variable_solar`, `solar_pv_capacity`, `solar_pv_capacity_factor`, `discount_rate`, `lcoe`.

### 7.2 The DSCR Equation

$$\text{DSCR}_t = \frac{\text{CFADS}_t}{\text{DS}_t} = \frac{\text{Revenue}_t - \text{OPEX}_t - \text{Tax}_t}{\text{Principal}_t + \text{Interest}_t}$$

**Expanded**:
- Revenue = PPA price × generation + merchant revenue
- OPEX = fixed O&M + variable O&M + fuel
- Tax = max(0, (Revenue - OPEX - Depreciation - Interest) × `corporate_income_tax_rate`)
- Principal = debt size / `debt_tenor`
- Interest = outstanding debt × `interest_rate_debt`

**Dependencies**: `ppa_pricing_formula`, `generation`, `opex_*`, `depreciation_schedule_*`, `corporate_income_tax_rate`, `debt_tenor`, `interest_rate_debt`, `debt_service_coverage_ratio`.

### 7.3 The Reserve Margin Equation

$$\sum_g \bar{P}_g \cdot (1 - \text{FOR}_g) \cdot \text{CC}_g \geq D_{\text{peak}} \cdot (1 + \text{RM}_{\text{min}})$$

**Dependencies**: `installed_capacity`, `forced_outage_rate`, `capacity_credit`, `peak_demand_multiplier`, `reserve_margin`.

### 7.4 The Carbon Price-Emissions Equation

$$\text{Emissions}_t = \sum_g p_{g,t} \cdot \text{EF}_g$$

$$\text{Carbon Cost}_t = \text{Emissions}_t \cdot \text{carbon\_price}_t$$

$$\text{carbon\_price}_t = \text{carbon\_price}_0 \cdot (1 + \text{escalation})^t$$

**Dependencies**: `generation`, `emission_factor`, `carbon_price`, `carbon_price_escalation`.

### 7.5 The Water-Energy Nexus Equation

$$\sum_g p_{g,t} \cdot w_g + \sum_k h_{k,t} \cdot w_k \leq W_{n,t}$$

$$w_g = f(\text{cooling technology}, \text{temperature})$$

**Dependencies**: `generation`, `cooling_water_demand`, `water_availability`, `hydrogen_production_demand`, `desalination_capacity`.

### 7.6 The Capture Price Equation

$$\text{Capture Price}_g = \frac{\sum_t p_{g,t} \cdot \pi_t}{\sum_t p_{g,t}}$$

**Dependencies**: `generation`, `market_price`, `capture_price`, `capture_rate`.

### 7.7 The Learning Curve Equation

$$C_t = C_0 \cdot \left(\frac{Q_t}{Q_0}\right)^{-b}$$

$$Q_t = Q_{t-1} + \text{new capacity}_t$$

**Dependencies**: `solar_pv_cost`, `cumulative_capacity`, `solar_pv_learning_rate`.

### 7.8 The Employment Equation

$$\text{Jobs} = \sum_g \bar{P}_g \cdot \text{EF}_g^{\text{construction}} + \sum_g E_g \cdot \text{EF}_g^{\text{O\&M}}$$

**Dependencies**: `installed_capacity`, `generation`, `employment_factor_*`, `direct_jobs`.

---

## 8. What Happens Without the PRG

If ALEA treats parameters as independent, the following failures occur:

| Failure | Example | Consequence |
|---|---|---|
| **Physical impossibility** | User sets 100% renewable target but also sets coal capacity to 50 GW | Model cannot solve, or returns infeasible |
| **Economic inconsistency** | User sets LCOE below capital cost | Returns impossible financial metrics |
| **Financial inconsistency** | User sets DSCR below 1.0 | Returns bankrupt projects as viable |
| **Accounting inconsistency** | User sets total cost below sum of components | Returns contradictory cost breakdowns |
| **Temporal inconsistency** | User sets retirement before commissioning | Returns impossible timeline |
| **Spatial inconsistency** | User sets transmission capacity above physical limits | Returns impossible flows |
| **Environmental inconsistency** | User sets emissions below zero | Returns physically impossible scenarios |
| **Social inconsistency** | User sets employment above working-age population | Returns impossible labour demand |

The PRG prevents all of these by **enforcing consistency at every parameter change**.

---

## 9. The User Experience

When a user changes a parameter, the PRG:

1. **Validates** the new value against all applicable constraints.
2. **Propagates** the change to all dependent parameters.
3. **Detects** any conflicts that arise.
4. **Suggests** corrections if conflicts exist.
5. **Confirms** if the change is consistent.
6. **Feeds** the consistent parameter set to the optimisation.

**Example interaction**:

```
User: Set carbon_price = 200

PRG: Checking consistency...
     ✓ carbon_price in valid range [0, 500]
     ✓ carbon_price escalation consistent with SSP2-4.5
     ⚠ Warning: carbon_price = 200 implies coal retirement by 2035
        but coal_retirement_schedule currently set to 2050
     
     Suggested corrections:
     A) Adjust coal_retirement_schedule to 2035
     B) Adjust carbon_price to 120 (consistent with 2050 retirement)
     C) Adjust renewable_target to compensate
     
     Choose A, B, C, or override?

User: Choose A

PRG: Propagating changes...
     → coal_retirement_schedule = 2035
     → coal_retirement_rate = 2,500 MW/year
     → coal_community_dependencies updated
     → just_transition_funding increased by $2.3B
     → employment_factor_coal updated
     → electricity_subsidies adjusted
     
     Consistency check: PASSED
     Ready to solve.
```

---

## 10. Summary

| Question | Answer |
|---|---|
| Do parameters need to be related by equations? | **Yes, absolutely.** |
| How many equation systems? | **20 major systems** |
| How many constraints? | **~120,000** |
| What type of relationships? | Physical, accounting, technical, economic, policy, feedback, temporal |
| What happens without it? | **Physically impossible, economically inconsistent, or self-contradictory scenarios** |
| Implementation? | **Parameter Relationship Engine (PRE)** with dependency graph, equation library, consistency checker, propagation engine, feedback solver |
| Key Python libraries? | `networkx`, `sympy`, `scipy.optimize`, `casadi`, `linopy`, `pyomo`, `numpy_financial`, `pymrio` |
| User experience? | **Consistency checking with suggested corrections** |

The PRG transforms ALEA from a collection of independent parameters into a **coherent, physically consistent, economically sound, and policy-relevant system**. It is the difference between a toy model and a world-class platform.

Without it, ALEA cannot answer the questions its users ask. With it, ALEA becomes the definitive energy intelligence platform for Africa — one that every stakeholder can trust because its outputs are internally consistent, physically possible, and economically coherent.