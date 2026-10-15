# Alea: Parameter Relationship Graph (PRG) System Specification

## Comprehensive Product Specification for the Parameter Relationship Graph, Equation Library, Consistency Engine, Propagation System, and Associated Subsystems

**Version**: 1.0
**Status**: Draft for Developer Implementation
**Audience**: Intermediate Python developers with experience in graph systems, symbolic mathematics, and optimisation
**Companion Documents**: Alea Product Specification v4.0, Alea Definitive Parameter Catalog v1.0

---

## Part I: Vision, Purpose, and Scope

### 1. Why the PRG Exists

Alea exposes **784 parameters** to its users across **28 categories**. These parameters are not independent. They are coupled by **physical laws** (energy conservation, Kirchhoff's laws, thermodynamics), **accounting identities** (cost = capex + opex, emissions = Σ generation × emission factor), **technical constraints** (reserve margins, ramp rates, minimum stable levels), **economic relationships** (demand elasticity, learning curves, CAPM), **policy constraints** (renewable targets, carbon caps, local content), **feedback loops** (higher VRE → lower capture price → lower VRE investment), and **temporal relationships** (investment lead times, learning by doing, retirement schedules).

If Alea treated these parameters as independent knobs, it would produce **physically impossible, economically inconsistent, or self-contradictory scenarios**. A user could set a carbon price, a coal retirement schedule, a demand growth rate, and a renewable target that are mutually incompatible — and the model would either fail to solve or return garbage.

The **Parameter Relationship Graph (PRG)** is the subsystem that prevents this. It is a directed acyclic graph of typed equations that defines how every parameter relates to every other parameter, which parameters are free (endogenous decision variables), which are fixed (exogenous inputs), and which are determined (derived outputs). It validates every parameter change, propagates the change to all dependents, detects conflicts, suggests corrections, and feeds a consistent parameter set to the optimisation engine.

### 2. What the PRG Is Not

The PRG is **not** the optimisation model. It does not solve the LOPF, unit commitment, or capacity expansion. It sits **above** the optimisation model, ensuring that the parameters fed to it are consistent.

The PRG is **not** a constraint solver. It does not use SAT/SMT solvers for general constraint satisfaction. It uses a **directed acyclic graph with typed equations**, which is more efficient for this domain because the relationships are mostly causal and one-directional.

The PRG is **not** a static schema. It is a **living system** that evolves as new parameters are added, new relationships are discovered, and new feedback loops are identified.

### 3. Scope

**In scope**:

- The PRG data model (graph structure, node types, edge types)
- The Equation Library (20 systems of equations with ~120,000 constraints)
- The Consistency Engine (validation, conflict detection, correction suggestions)
- The Propagation Engine (change propagation, topological sorting, incremental updates)
- The Feedback Solver (iterative solving of dynamic feedback loops)
- The Translation Layer (conversion of equations to PyPSA/Linopy constraints)
- The API for programmatic access
- The User Interface for interactive exploration
- The Testing and Validation framework

**Out of scope**:

- The optimisation engine itself (PyPSA/PyPSA-Earth)
- The data pipeline (covered in Alea v2.0)
- The market simulation engine (covered in Alea v2.0)
- The predictive analytics modules (covered in Alea v3.0)

---

## Part II: Architecture

### 4. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                                 │
│  Dashboard  │  API  │  SDKs  │  Bots  │  Reports                       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                    PARAMETER RELATIONSHIP ENGINE (PRE)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Consistency │  │ Propagation │  │  Conflict   │  │  Feedback   │   │
│  │   Engine    │  │   Engine    │  │  Detector   │  │   Solver    │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │                │          │
│  ┌──────▼────────────────▼────────────────▼────────────────▼──────┐   │
│  │              PARAMETER RELATIONSHIP GRAPH (PRG)                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────┐  │   │
│  │  │   Graph    │  │  Equation  │  │   Type     │  │ Metadata│  │   │
│  │  │  Store     │  │  Library   │  │  System    │  │  Store  │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └─────────┘  │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │              TRANSLATION LAYER                                 │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────┐  │   │
│  │  │  PyPSA     │  │  Linopy    │  │  SymPy     │  │ Custom  │  │   │
│  │  │ Translator │  │ Translator │  │ Translator │  │ Solver  │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └─────────┘  │   │
│  └────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       OPTIMISATION ENGINE                               │
│  PyPSA-Earth  │  PyPSA  │  Custom MILP  │  Stochastic  │  Market      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5. Component Responsibilities

| Component | Responsibility | Technology |
|---|---|---|
| **Graph Store** | Persist the PRG structure (nodes, edges, attributes) | NetworkX + SQLite/PostgreSQL |
| **Equation Library** | Store the 20 systems of equations as symbolic expressions | SymPy + custom DSL |
| **Type System** | Define parameter types, units, ranges, and validation rules | Pydantic + Pint |
| **Metadata Store** | Store parameter descriptions, sources, users, priorities | PostgreSQL |
| **Consistency Engine** | Validate parameter sets against all equations | Custom + SymPy |
| **Propagation Engine** | Propagate parameter changes to dependents | NetworkX + custom |
| **Conflict Detector** | Detect over/under-determined systems and conflicts | Custom SAT/SMT |
| **Feedback Solver** | Iteratively solve dynamic feedback loops | Custom convergence loop |
| **Translation Layer** | Convert equations to PyPSA/Linopy/SymPy constraints | Multiple backends |
| **API** | Expose PRG capabilities programmatically | FastAPI |
| **UI** | Interactive exploration of the PRG | Plotly Dash + Cytoscape |

### 6. Repository Structure

```
alea-prg/
├── pyproject.toml
├── README.md
├── src/
│   └── alea_prg/
│       ├── __init__.py
│       ├── graph/
│       │   ├── store.py                 # Graph persistence
│       │   ├── node.py                  # Parameter node model
│       │   ├── edge.py                  # Relationship edge model
│       │   └── builder.py               # Graph construction from YAML
│       ├── equations/
│       │   ├── library.py               # Equation library loader
│       │   ├── dsl.py                   # Domain-specific language parser
│       │   ├── evaluator.py             # Symbolic + numeric evaluator
│       │   └── systems/
│       │       ├── energy_balance.py
│       │       ├── cost_accounting.py
│       │       ├── emissions.py
│       │       ├── demand_supply.py
│       │       ├── financial.py
│       │       ├── learning.py
│       │       ├── reserve_margin.py
│       │       ├── inertia.py
│       │       ├── water_nexus.py
│       │       ├── capture_price.py
│       │       ├── reliability.py
│       │       ├── employment.py
│       │       ├── health.py
│       │       ├── affordability.py
│       │       ├── price_demand.py
│       │       ├── vre_investment.py
│       │       ├── carbon_trajectory.py
│       │       ├── tech_cost.py
│       │       ├── debt_sizing.py
│       │       └── ppa_pricing.py
│       ├── types/
│       │   ├── parameter.py             # Parameter type definitions
│       │   ├── units.py                 # Unit handling (Pint)
│       │   └── validation.py            # Pydantic validators
│       ├── consistency/
│       │   ├── engine.py                # Consistency engine
│       │   ├── checker.py               # Individual equation checker
│       │   ├── tolerance.py             # Tolerance management
│       │   └── reporter.py              # Violation reporting
│       ├── propagation/
│       │   ├── engine.py                # Propagation engine
│       │   ├── topological.py           # Topological sort
│       │   ├── incremental.py           # Incremental updates
│       │   └── cache.py                 # Propagation cache
│       ├── conflict/
│       │   ├── detector.py              # Conflict detection
│       │   ├── resolver.py              # Conflict resolution
│       │   ├── suggester.py             # Correction suggestions
│       │   └── ranking.py               # Suggestion ranking
│       ├── feedback/
│       │   ├── solver.py                # Feedback loop solver
│       │   ├── convergence.py           # Convergence checks
│       │   └── acceleration.py          # Convergence acceleration
│       ├── translation/
│       │   ├── pypsa.py                 # PyPSA translator
│       │   ├── linopy.py                # Linopy translator
│       │   ├── sympy.py                 # SymPy translator
│       │   └── custom.py                # Custom solver interface
│       ├── api/
│       │   ├── main.py                  # FastAPI app
│       │   ├── routes.py                # API routes
│       │   ├── models.py                # Pydantic models
│       │   └── auth.py                  # Authentication
│       ├── ui/
│       │   ├── app.py                   # Dash app
│       │   ├── graph_view.py            # Graph visualisation
│       │   ├── parameter_view.py        # Parameter editor
│       │   └── conflict_view.py         # Conflict resolution UI
│       └── utils/
│           ├── logging.py
│           ├── config.py
│           └── exceptions.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── regression/
├── data/
│   ├── prg.yaml                         # The PRG definition
│   ├── equations.yaml                   # Equation library
│   ├── parameters.yaml                  # Parameter metadata
│   └── scenarios/                       # Example scenarios
└── docs/
    ├── user_guide.md
    ├── developer_guide.md
    └── api_reference.md
```

---

## Part III: The PRG Data Model

### 7. Parameter Nodes

Each parameter is a node in the graph with the following attributes:

```python
# src/alea_prg/graph/node.py
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from pint import Unit

class ParameterNode(BaseModel):
    """A node in the Parameter Relationship Graph."""

    id: str = Field(..., description="Unique parameter identifier, e.g., 'carbon_price'")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Detailed description")
    category: str = Field(..., description="One of 28 categories")
    subcategory: Optional[str] = None

    # Type and units
    type: Literal["float", "int", "bool", "categorical", "timeseries", "spatial"]
    unit: Optional[str] = Field(None, description="Pint-compatible unit string")
    range: Optional[tuple[float, float]] = None
    default: Optional[float] = None

    # Role in the PRG
    role: Literal["exogenous", "endogenous", "derived", "free"]
    determinism: Literal["fixed", "stochastic", "policy", "physical"]

    # Metadata
    source: Optional[str] = None
    source_url: Optional[str] = None
    users: List[str] = Field(default_factory=list)
    priority: Literal["P1", "P2", "P3"] = "P2"
    status: Literal["existing", "to_build", "integrate"] = "to_build"

    # Graph relationships
    depends_on: List[str] = Field(default_factory=list)
    affects: List[str] = Field(default_factory=list)
    equations: List[str] = Field(default_factory=list)

    # Validation
    validation_rules: List[str] = Field(default_factory=list)
    cross_validation: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
```

**Example node definition** (from `parameters.yaml`):

```yaml
carbon_price:
  name: "Carbon Price"
  description: "Price per tonne of CO2 emitted, applied to covered sectors"
  category: "Policy & Regulatory"
  subcategory: "Climate Policy"
  type: float
  unit: "USD / tonne"
  range: [0, 500]
  default: 0
  role: exogenous
  determinism: policy
  source: "IMF Effective Carbon Prices"
  source_url: "https://www.imf.org/"
  users: ["Policymakers", "Investors", "Utilities"]
  priority: P1
  status: existing
  depends_on: []
  affects:
    - coal_capacity
    - gas_capacity
    - renewable_target
    - coal_retirement_schedule
    - carbon_price_escalation
    - emission_factor
  equations:
    - carbon_cost_equation
    - emissions_accounting
  validation_rules:
    - "value >= 0"
    - "value <= 500"
  cross_validation:
    - "if carbon_price > 100 and coal_retirement_schedule > 2045: warning"
```

### 8. Relationship Edges

Each edge is a directed relationship between two parameters, with the following attributes:

```python
# src/alea_prg/graph/edge.py
class RelationshipEdge(BaseModel):
    """A directed edge in the PRG."""

    source: str = Field(..., description="Source parameter ID")
    target: str = Field(..., description="Target parameter ID")
    equation_id: str = Field(..., description="ID of the equation relating them")

    # Edge type
    relationship: Literal[
        "equality",           # source = f(target) or target = f(source)
        "inequality",         # source >= f(target) or source <= f(target)
        "functional",         # target = f(source)
        "constraint",         # Hard constraint
        "feedback",           # Feedback loop
        "temporal",           # Time-dependent
        "stochastic",         # Probabilistic
    ]

    # Direction
    direction: Literal["forward", "backward", "bidirectional"]

    # Strength
    strength: Literal["hard", "soft", "informational"]

    # Metadata
    description: str
    reference: Optional[str] = None
    priority: Literal["P1", "P2", "P3"] = "P1"
```

**Example edge definition** (from `prg.yaml`):

```yaml
edges:
  - source: "carbon_price"
    target: "coal_capacity"
    equation_id: "carbon_cost_equation"
    relationship: "functional"
    direction: "forward"
    strength: "soft"
    description: "Higher carbon price reduces optimal coal capacity"

  - source: "coal_capacity"
    target: "total_emissions"
    equation_id: "emissions_accounting"
    relationship: "functional"
    direction: "forward"
    strength: "hard"
    description: "Coal generation contributes to total emissions"

  - source: "total_emissions"
    target: "carbon_cost"
    equation_id: "carbon_cost_equation"
    relationship: "functional"
    direction: "forward"
    strength: "hard"
    description: "Emissions multiplied by carbon price equals carbon cost"
```

### 9. Graph Structure

The complete PRG is a **directed graph** with:

- **784 nodes** (one per parameter)
- **~2,500 edges** (relationships between parameters)
- **20 equation systems** (groupings of related equations)
- **~120,000 constraints** (when expanded for all time steps and nodes)

The graph is stored in:

- **YAML** for human-readable definition (`data/prg.yaml`)
- **NetworkX** for in-memory manipulation
- **PostgreSQL** for persistence and querying
- **GraphML** for export and visualisation

### 10. Graph Properties

| Property | Value | Notes |
|---|---|---|
| **Nodes** | 784 | One per parameter |
| **Edges** | ~2,500 | Includes all relationships |
| **Components** | ~5 | Some subgraphs are disconnected |
| **Cycles** | ~15 | Feedback loops |
| **Depth** | ~12 | Longest path from exogenous to derived |
| **Fan-out** | ~20 | Maximum outgoing edges from one node |
| **Fan-in** | ~15 | Maximum incoming edges to one node |
| **Density** | ~0.004 | Sparse graph |

### 11. Cycle Handling

The PRG contains **~15 cycles** (feedback loops). These are handled by:

1. **Identifying cycles** using Tarjan's strongly connected components algorithm.
2. **Collapsing cycles** into **super-nodes** for propagation.
3. **Iteratively solving** the super-nodes using the Feedback Solver.
4. **Expanding** the super-nodes back into individual parameters after convergence.

**Example cycle**: Price-Demand Feedback

```
carbon_price → electricity_price → demand → generation → emissions → carbon_price
```

This cycle is collapsed into a super-node and solved iteratively.

---

## Part IV: The Equation Library

### 12. Equation Representation

Each equation is stored as a **symbolic expression** using SymPy, with metadata:

```python
# src/alea_prg/equations/library.py
class Equation(BaseModel):
    """A single equation in the library."""

    id: str
    name: str
    description: str
    system: str  # Which of the 20 systems

    # Symbolic representation
    lhs: str  # Left-hand side (SymPy expression string)
    rhs: str  # Right-hand side (SymPy expression string)
    relation: Literal["eq", "leq", "geq"] = "eq"

    # Variables
    parameters: List[str]  # Parameter IDs involved
    free_variables: List[str]  # Parameters that can vary
    determined_variables: List[str]  # Parameters determined by this equation

    # Validation
    tolerance: float = 1e-6
    unit_check: bool = True

    # Metadata
    reference: Optional[str] = None
    priority: Literal["P1", "P2", "P3"] = "P1"

    # Solver hints
    solution_method: Literal["direct", "iterative", "symbolic", "numeric"] = "numeric"
    linearity: Literal["linear", "nonlinear", "mixed"] = "linear"
```

### 13. Equation Systems (20 Systems)

#### System 1: Energy Balance

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `nodal_balance` | generation, storage, line_flow, demand, curtailment | Equality | P1 |
| `carrier_balance` | carrier_flow, conversion_efficiency, demand | Equality | P1 |
| `storage_balance` | storage_level, charge, discharge, efficiency | Equality | P1 |
| `reservoir_balance` | inflow, outflow, storage, spillage | Equality | P1 |
| `curtailment_definition` | available, dispatched, curtailment | Equality | P2 |

#### System 2: Cost Accounting

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `total_cost` | capex, opex, fuel_cost, generation, capacity | Equality | P1 |
| `lcoe_definition` | capex, opex, fuel, generation, discount_rate | Equality | P1 |
| `crf_definition` | discount_rate, asset_life | Equality | P1 |
| `annualised_capex` | capex, crf | Equality | P1 |
| `marginal_cost` | vom, fuel_cost, efficiency, carbon_cost | Equality | P1 |
| `consumer_cost` | tariff, consumption, fixed_charge | Equality | P2 |
| `producer_revenue` | price, generation, capacity_payment | Equality | P2 |

#### System 3: Emissions Accounting

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `emissions_total` | generation, emission_factor, ccs_capture | Equality | P1 |
| `emissions_intensity` | emissions, generation | Equality | P1 |
| `carbon_cost` | emissions, carbon_price, coverage | Equality | P1 |
| `carbon_revenue` | emissions, carbon_price, coverage | Equality | P2 |
| `emissions_budget` | cumulative_emissions, carbon_budget | Inequality | P2 |

#### System 4: Demand-Supply Equilibrium

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `market_clearing` | supply, demand, price | Equality | P1 |
| `elasticity_relationship` | demand_change, price_change, elasticity | Functional | P2 |
| `consumer_surplus` | wtp, price, quantity | Equality | P2 |
| `producer_surplus` | price, marginal_cost, quantity | Equality | P2 |
| `welfare` | consumer_surplus, producer_surplus, externality | Equality | P2 |

#### System 5: Financial Identities

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `wacc_definition` | equity, debt, cost_of_equity, cost_of_debt, tax | Equality | P1 |
| `capm_definition` | risk_free, beta, market_premium, country_risk | Equality | P1 |
| `dscr_definition` | cfads, debt_service | Equality | P1 |
| `llcr_definition` | pv_cfads, debt_outstanding | Equality | P1 |
| `irr_definition` | cash_flows, irr | Equality | P1 |
| `npv_definition` | cash_flows, discount_rate, npv | Equality | P1 |
| `debt_sizing` | dscr_min, cfads, debt_size, debt_tenor | Inequality | P1 |
| `dividend_policy` | net_income, dividends, retained_earnings | Equality | P2 |

#### System 6: Learning Curves

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `single_factor_learning` | cost, cumulative_capacity, learning_rate | Functional | P2 |
| `two_factor_learning` | cost, cumulative_capacity, rd_investment | Functional | P3 |
| `cumulative_capacity` | capacity_additions, cumulative_capacity | Equality | P1 |
| `experience_curve` | cost_index, cumulative_production | Functional | P2 |

#### System 7: Reserve Margin

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `reserve_margin` | capacity, forced_outage, peak_demand, reserve | Inequality | P1 |
| `capacity_credit` | vre_capacity, capacity_credit_factor | Equality | P1 |
| `effective_capacity` | capacity, forced_outage, capacity_credit | Equality | P1 |
| `reserve_requirement` | peak_demand, reserve_margin_min | Equality | P1 |

#### System 8: Inertia Constraint

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `inertia_total` | synchronous_capacity, inertia_constant, vre_share | Equality | P2 |
| `inertia_requirement` | inertia_total, inertia_min | Inequality | P2 |
| `rocof_constraint` | inertia_total, largest_contingency, rocof_max | Inequality | P3 |

#### System 9: Water-Energy Nexus

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `water_balance` | water_withdrawal, water_consumption, water_availability | Inequality | P2 |
| `cooling_water` | generation, cooling_intensity, cooling_technology | Equality | P2 |
| `hydrogen_water` | hydrogen_production, water_intensity | Equality | P2 |
| `desalination_balance` | desalination_capacity, water_production, energy_use | Equality | P2 |

#### System 10: Capture Price

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `capture_price` | generation, market_price, capture_price | Equality | P1 |
| `capture_rate` | capture_price, average_price | Equality | P1 |
| `cannibalisation` | vre_penetration, capture_rate | Functional | P2 |
| `ppa_benchmark` | capture_price, contract_tenor, risk_premium | Functional | P2 |

#### System 11: Reliability Indices

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `said_definition` | interruption_duration, customers, total_customers | Equality | P1 |
| `saifi_definition` | interruptions, customers, total_customers | Equality | P1 |
| `ens_definition` | demand, served, ens | Equality | P1 |
| `eens_definition` | ens, probability | Equality | P1 |
| `tlens_definition` | ens_base, ens_post_outage, tlens | Equality | P2 |
| `lolp_definition` | probability, generation, demand | Equality | P2 |

#### System 12: Employment

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `direct_jobs` | capacity, employment_factor | Equality | P2 |
| `indirect_jobs` | direct_jobs, multiplier | Equality | P2 |
| `induced_jobs` | direct_jobs, multiplier | Equality | P2 |
| `local_employment` | direct_jobs, local_content | Equality | P2 |

#### System 13: Health Impact

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `premature_deaths` | population, baseline_mortality, relative_risk | Functional | P2 |
| `dalys` | premature_deaths, yll, morbidity, yld | Equality | P2 |
| `health_cost` | dalys, cost_per_daly | Equality | P2 |

#### System 14: Affordability

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `energy_burden` | monthly_bill, monthly_income | Equality | P2 |
| `energy_poverty_rate` | households_burden, total_households | Equality | P2 |
| `affordability_threshold` | energy_burden, threshold | Inequality | P2 |

#### System 15: Price-Demand Feedback

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `demand_response` | demand, price, elasticity | Functional | P2 |
| `long_run_elasticity` | demand, income, price | Functional | P3 |
| `feedback_convergence` | demand_t, demand_t_minus_1, price | Convergence | P2 |

#### System 16: VRE Investment Feedback

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `vre_investment` | expected_price, cost, investment | Functional | P2 |
| `capture_price_feedback` | vre_penetration, capture_price | Functional | P2 |
| `penetration_definition` | vre_generation, total_generation | Equality | P1 |
| `feedback_convergence` | vre_penetration_t, vre_penetration_t_minus_1 | Convergence | P2 |

#### System 17: Carbon Price Trajectory

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `carbon_price_escalation` | carbon_price_t, carbon_price_0, escalation | Equality | P2 |
| `emissions_reduction` | emissions_t, emissions_t_minus_1, reduction_rate | Equality | P2 |
| `carbon_revenue` | emissions, carbon_price, coverage | Equality | P2 |

#### System 18: Technology Cost Trajectory

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `cost_trajectory` | cost_t, cost_0, trend, learning | Functional | P2 |
| `learning_by_doing` | cost_t, cumulative_capacity, learning_rate | Functional | P2 |
| `rd_spillover` | cost_t, rd_investment, spillover_rate | Functional | P3 |

#### System 19: Debt Sizing

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `debt_sizing_constraint` | dscr_t, dscr_min, debt_size | Inequality | P1 |
| `debt_schedule` | debt_size, tenor, amortisation | Equality | P1 |
| `interest_schedule` | debt_outstanding, interest_rate | Equality | P1 |
| `principal_schedule` | debt_size, tenor, grace_period | Equality | P1 |

#### System 20: PPA Pricing

| Equation ID | Parameters | Type | Priority |
|---|---|---|---|
| `ppa_price` | lcoe, risk_premium, return, availability | Equality | P1 |
| `ppa_indexation` | ppa_t, ppa_0, index, escalation | Equality | P2 |
| `ppa_npv` | ppa_t, discount_rate | Equality | P2 |

### 14. Equation DSL

Equations are written in a **domain-specific language (DSL)** that is human-readable and machine-parseable:

```yaml
# data/equations.yaml
equations:
  total_cost:
    name: "Total System Cost"
    description: "Sum of all capital and operational costs"
    system: "cost_accounting"
    lhs: "total_cost"
    rhs: |
      sum(capex_g * p_nom_g for g in generators)
      + sum(opex_fixed_g * p_nom_g for g in generators)
      + sum((opex_variable_g + fuel_cost_g / efficiency_g) * p_g_t
            for g in generators for t in timesteps)
      + sum(capex_l * f_l for l in lines)
      + sum(capex_s * e_nom_s for s in storage)
    relation: "eq"
    parameters: [capex_g, opex_fixed_g, opex_variable_g, fuel_cost_g,
                 efficiency_g, p_nom_g, p_g_t, capex_l, f_l, capex_s, e_nom_s]
    free_variables: [p_nom_g, p_g_t, f_l, e_nom_s]
    determined_variables: [total_cost]
    tolerance: 1e-6
    unit_check: true
    reference: "PyPSA objective function"
    priority: P1
    solution_method: "numeric"
    linearity: "linear"
```

**DSL syntax**:

| Symbol | Meaning |
|---|---|
| `sum(expr for var in set)` | Summation |
| `+`, `-`, `*`, `/` | Arithmetic |
| `**` | Power |
| `==`, `<=`, `>=` | Relations |
| `if cond else alt` | Conditional |
| `min(a, b)`, `max(a, b)` | Min/max |
| `abs(x)` | Absolute value |
| `log(x)`, `exp(x)` | Logarithms |
| `sqrt(x)` | Square root |

### 15. Equation Parser

The DSL is parsed by a custom parser built on **Lark** (a parsing library for Python):

```python
# src/alea_prg/equations/dsl.py
from lark import Lark, Transformer

GRAMMAR = """
    start: equation
    equation: lhs relation rhs
    lhs: expression
    rhs: expression
    relation: "==" | "<=" | ">="
    expression: term (("+" | "-") term)*
    term: factor (("*" | "/") factor)*
    factor: base ("**" factor)?
    base: atom | "(" expression ")" | function_call | summation
    function_call: NAME "(" expression ("," expression)* ")"
    summation: "sum(" expression "for" NAME "in" NAME ("," NAME "in" NAME)* ")"
    atom: NUMBER | NAME
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    NUMBER: /-?[0-9]+(\.[0-9]+)?/
"""

class EquationParser:
    def __init__(self):
        self.parser = Lark(GRAMMAR, parser="lalr")
        self.transformer = EquationTransformer()

    def parse(self, equation_str: str):
        tree = self.parser.parse(equation_str)
        return self.transformer.transform(tree)
```

### 16. Equation Evaluator

The equation evaluator supports three modes:

| Mode | Purpose | Technology |
|---|---|---|
| **Symbolic** | Manipulate equations algebraically | SymPy |
| **Numeric** | Evaluate equations with given values | NumPy/SciPy |
| **Constraint** | Translate to optimisation constraints | Linopy/Pyomo |

```python
# src/alea_prg/equations/evaluator.py
import sympy as sp
import numpy as np

class EquationEvaluator:
    def __init__(self, equation: Equation):
        self.equation = equation
        self.symbolic_form = self._to_sympy()

    def _to_sympy(self):
        """Convert equation to SymPy expression."""
        lhs = sp.sympify(self.equation.lhs)
        rhs = sp.sympify(self.equation.rhs)
        return sp.Eq(lhs, rhs)

    def evaluate(self, values: dict) -> float:
        """Numerically evaluate the equation's residual."""
        residual = self.symbolic_form.lhs - self.symbolic_form.rhs
        return float(residual.subs(values))

    def solve_for(self, variable: str, values: dict) -> float:
        """Solve the equation for a specific variable."""
        solution = sp.solve(self.symbolic_form, variable)
        return float(solution[0].subs(values))

    def to_constraint(self, model):
        """Convert to a Linopy constraint."""
        return model.add_constraints(
            self.symbolic_form.lhs == self.symbolic_form.rhs,
            name=self.equation.id
        )
```

---

## Part V: Type System

### 17. Parameter Types

Each parameter has a **type** that determines its validation rules, unit handling, and default value:

```python
# src/alea_prg/types/parameter.py
from pydantic import BaseModel, validator
from pint import UnitRegistry

ureg = UnitRegistry()

class ParameterType(BaseModel):
    """Base class for parameter types."""
    type_name: str

class FloatParameter(ParameterType):
    type_name: str = "float"
    unit: str
    min_value: float
    max_value: float
    default: float

    @validator("unit")
    def validate_unit(cls, v):
        return str(ureg.parse_units(v))

class CategoricalParameter(ParameterType):
    type_name: str = "categorical"
    categories: list[str]
    default: str

class TimeSeriesParameter(ParameterType):
    type_name: str = "timeseries"
    frequency: str  # "hourly", "daily", "monthly", "annual"
    start_date: str
    end_date: str
    unit: str

class SpatialParameter(ParameterType):
    type_name: str = "spatial"
    resolution: str  # "country", "region", "node"
    unit: str
    geometry_type: str  # "point", "polygon", "raster"
```

### 18. Unit Handling

All parameters carry units, and all equations must be **dimensionally consistent**. The PRG uses **Pint** for unit handling:

```python
# src/alea_prg/types/units.py
from pint import UnitRegistry

ureg = UnitRegistry()

def check_dimensional_consistency(equation: Equation) -> bool:
    """Check that an equation is dimensionally consistent."""
    lhs_unit = get_unit(equation.lhs)
    rhs_unit = get_unit(equation.rhs)
    return lhs_unit.dimensionality == rhs_unit.dimensionality

def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a value between units."""
    return (value * ureg(from_unit)).to(to_unit).magnitude
```

### 19. Validation Rules

Each parameter has a set of validation rules:

| Rule Type | Description | Example |
|---|---|---|
| **Range** | Value must be within range | `carbon_price >= 0 and <= 500` |
| **Unit** | Unit must be valid | `unit == "USD/tonne"` |
| **Type** | Value must be of correct type | `isinstance(value, float)` |
| **Consistency** | Must be consistent with other parameters | `carbon_price > 100 implies coal_retirement < 2045` |
| **Temporal** | Must respect temporal ordering | `start_year <= end_year` |
| **Spatial** | Must respect spatial resolution | `resolution in ["country", "region", "node"]` |
| **Categorical** | Must be one of allowed values | `market_model in ["monopoly", "single_buyer", "wholesale", "retail"]` |

### 20. Type Inference

The PRG can infer parameter types from equation relationships:

```python
# src/alea_prg/types/inference.py
def infer_type(param: str, prg: nx.DiGraph, equations: dict) -> str:
    """Infer the type of a parameter from its equations."""
    # Find equations involving the parameter
    param_equations = [eq for eq in equations.values() if param in eq.parameters]
    # Look for the equation where the parameter is determined
    for eq in param_equations:
        if param in eq.determined_variables:
            # Infer from RHS
            return infer_from_expression(eq.rhs)
    return "unknown"
```

---

## Part VI: Consistency Engine

### 21. Purpose

The Consistency Engine validates a parameter set against all equations in the PRG. It answers the question: **"Is this parameter set internally consistent?"**

### 22. Architecture

```python
# src/alea_prg/consistency/engine.py
import networkx as nx
from typing import List, Dict, Optional

class ConsistencyEngine:
    """Validates parameter sets against the PRG."""

    def __init__(self, prg: nx.DiGraph, equations: Dict[str, Equation]):
        self.prg = prg
        self.equations = equations
        self.tolerance = 1e-6

    def check(self, parameters: Dict[str, float]) -> "ConsistencyReport":
        """Check a parameter set for consistency."""
        violations = []
        warnings = []
        info = []

        for eq_id, equation in self.equations.items():
            if not equation.is_active:
                continue

            # Check that all parameters are present
            missing = set(equation.parameters) - set(parameters.keys())
            if missing:
                warnings.append({
                    "equation": eq_id,
                    "type": "missing_parameters",
                    "parameters": list(missing)
                })
                continue

            # Evaluate the equation
            evaluator = EquationEvaluator(equation)
            try:
                residual = evaluator.evaluate(parameters)
            except Exception as e:
                violations.append({
                    "equation": eq_id,
                    "type": "evaluation_error",
                    "error": str(e)
                })
                continue

            # Check tolerance
            if abs(residual) > equation.tolerance:
                violations.append({
                    "equation": eq_id,
                    "type": "residual_too_large",
                    "residual": residual,
                    "tolerance": equation.tolerance,
                    "parameters": equation.parameters,
                    "suggestion": self._suggest_correction(equation, residual)
                })

        return ConsistencyReport(
            violations=violations,
            warnings=warnings,
            info=info,
            is_consistent=len(violations) == 0
        )

    def _suggest_correction(self, equation: Equation, residual: float) -> dict:
        """Suggest a correction for a violated equation."""
        # Find the most likely parameter to adjust
        adjustable = [p for p in equation.free_variables
                      if p in self._user_adjustable_parameters()]
        if not adjustable:
            return {"type": "no_suggestion", "reason": "No adjustable parameters"}

        # Rank by sensitivity
        sensitivities = {}
        for param in adjustable:
            sensitivities[param] = self._compute_sensitivity(equation, param)

        # Suggest adjusting the most sensitive parameter
        best = max(sensitivities, key=sensitivities.get)
        current = self._get_current_value(best)
        delta = -residual / sensitivities[best]

        return {
            "type": "adjust_parameter",
            "parameter": best,
            "current_value": current,
            "suggested_value": current + delta,
            "delta": delta,
            "sensitivity": sensitivities[best]
        }

    def _compute_sensitivity(self, equation: Equation, param: str) -> float:
        """Compute the sensitivity of the equation residual to a parameter."""
        evaluator = EquationEvaluator(equation)
        epsilon = 1e-6
        values = self._get_current_values(equation.parameters)
        base = evaluator.evaluate(values)
        values[param] += epsilon
        perturbed = evaluator.evaluate(values)
        return (perturbed - base) / epsilon
```

### 23. Consistency Report

```python
# src/alea_prg/consistency/reporter.py
class ConsistencyReport(BaseModel):
    """Report of a consistency check."""

    violations: List[dict] = []
    warnings: List[dict] = []
    info: List[dict] = []
    is_consistent: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)
    parameters_hash: str = ""

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Consistency Check Report ({self.timestamp})",
            f"Status: {'PASSED' if self.is_consistent else 'FAILED'}",
            f"Violations: {len(self.violations)}",
            f"Warnings: {len(self.warnings)}",
        ]
        if self.violations:
            lines.append("\nViolations:")
            for v in self.violations:
                lines.append(f"  - {v['equation']}: {v['type']}")
        if self.warnings:
            lines.append("\nWarnings:")
            for w in self.warnings:
                lines.append(f"  - {w['equation']}: {w['type']}")
        return "\n".join(lines)

    def to_json(self) -> str:
        return self.json()

    def to_dataframe(self) -> "pd.DataFrame":
        import pandas as pd
        return pd.DataFrame(self.violations + self.warnings)
```

### 24. Tolerance Management

Different equations have different tolerances:

| Equation Type | Tolerance | Rationale |
|---|---|---|
| **Hard equality** (energy balance) | 1e-6 | Numerical precision |
| **Accounting identity** (cost) | 1e-3 | Rounding in financial data |
| **Economic relationship** (elasticity) | 1e-2 | Empirical uncertainty |
| **Learning curve** | 1e-2 | Empirical uncertainty |
| **Health impact** | 5e-2 | Epidemiological uncertainty |
| **Employment** | 1e-1 | Survey uncertainty |

Tolerances are configurable per equation:

```yaml
tolerances:
  nodal_balance: 1e-6
  total_cost: 1e-3
  elasticity_relationship: 1e-2
  single_factor_learning: 1e-2
  premature_deaths: 5e-2
  direct_jobs: 1e-1
```

### 25. Cross-Validation Rules

Beyond equation-level consistency, the PRG checks **cross-validation rules** that span multiple equations:

```yaml
cross_validation:
  - id: "carbon_price_coal_retirement"
    condition: "carbon_price > 100 and coal_retirement_schedule > 2045"
    severity: "warning"
    message: "High carbon price is inconsistent with late coal retirement"
    suggestion: "Adjust coal_retirement_schedule to 2040 or carbon_price to 80"

  - id: "reserve_margin_vre_penetration"
    condition: "reserve_margin < 10 and renewable_target > 80"
    severity: "error"
    message: "Low reserve margin with high renewable target is infeasible"
    suggestion: "Increase reserve_margin or decrease renewable_target"

  - id: "water_drought_hydro_capacity"
    condition: "drought_multiplier < 0.5 and hydro_capacity > 50000"
    severity: "warning"
    message: "Severe drought with high hydro capacity is risky"
    suggestion: "Reduce hydro_capacity or increase drought_multiplier"
```

---

## Part VII: Propagation Engine

### 26. Purpose

The Propagation Engine propagates a parameter change to all dependent parameters. It answers the question: **"If I change parameter X, what else changes?"**

### 27. Architecture

```python
# src/alea_prg/propagation/engine.py
import networkx as nx
from typing import Dict, Set, List

class PropagationEngine:
    """Propagates parameter changes through the PRG."""

    def __init__(self, prg: nx.DiGraph, equations: Dict[str, Equation]):
        self.prg = prg
        self.equations = equations
        self.cache = {}

    def propagate(self, changed_param: str, new_value: float,
                  current_values: Dict[str, float]) -> Dict[str, float]:
        """Propagate a change to all dependent parameters."""
        # Find all descendants
        descendants = nx.descendants(self.prg, changed_param)

        # Topologically sort them
        ordered = list(nx.topological_sort(
            self.prg.subgraph(descendants | {changed_param})
        ))

        # Start with the changed parameter
        new_values = current_values.copy()
        new_values[changed_param] = new_value

        # Propagate in topological order
        for param in ordered:
            if param == changed_param:
                continue
            if param in self.cache and self.cache[param] == new_values[param]:
                continue
            new_values[param] = self._compute_value(param, new_values)
            self.cache[param] = new_values[param]

        return new_values

    def _compute_value(self, param: str, values: Dict[str, float]) -> float:
        """Compute the value of a parameter from its determining equation."""
        # Find the equation that determines this parameter
        determining_eq = self._find_determining_equation(param)
        if determining_eq is None:
            return values.get(param, 0.0)

        # Solve for the parameter
        evaluator = EquationEvaluator(determining_eq)
        try:
            return evaluator.solve_for(param, values)
        except Exception:
            return values.get(param, 0.0)

    def _find_determining_equation(self, param: str) -> Optional[Equation]:
        """Find the equation that determines a parameter."""
        for eq in self.equations.values():
            if param in eq.determined_variables:
                return eq
        return None
```

### 28. Topological Sorting

NetworkX provides topological sorting, but the PRG may contain **cycles** (feedback loops). These are handled by:

1. **Detecting cycles** using `nx.simple_cycles()`.
2. **Collapsing cycles** into **super-nodes**.
3. **Topologically sorting** the collapsed graph.
4. **Iteratively solving** each super-node.
5. **Expanding** the super-nodes back into individual parameters.

```python
# src/alea_prg/propagation/topological.py
def topological_sort_with_cycles(prg: nx.DiGraph):
    """Topologically sort a graph with cycles."""
    # Find strongly connected components
    sccs = list(nx.strongly_connected_components(prg))
    # Build a DAG of SCCs
    scc_graph = nx.condensation(prg, sccs)
    # Topologically sort the DAG
    ordered_sccs = list(nx.topological_sort(scc_graph))
    # Expand back to nodes
    ordered_nodes = []
    for scc_id in ordered_sccs:
        ordered_nodes.extend(sccs[scc_id])
    return ordered_nodes
```

### 29. Incremental Updates

For large parameter sets, full propagation is expensive. The PRG supports **incremental updates**:

```python
# src/alea_prg/propagation/incremental.py
class IncrementalPropagator:
    def __init__(self, engine: PropagationEngine):
        self.engine = engine
        self.dirty = set()
        self.last_values = {}

    def mark_dirty(self, param: str):
        """Mark a parameter as changed."""
        self.dirty.add(param)
        self.dirty.update(nx.descendants(self.engine.prg, param))

    def propagate_incremental(self, values: Dict[str, float]) -> Dict[str, float]:
        """Propagate only dirty parameters."""
        new_values = values.copy()
        for param in self._topological_order(self.dirty):
            new_values[param] = self.engine._compute_value(param, new_values)
        self.dirty.clear()
        return new_values

    def _topological_order(self, params: Set[str]) -> List[str]:
        """Topologically sort the dirty parameters."""
        subgraph = self.engine.prg.subgraph(params)
        return list(nx.topological_sort(subgraph))
```

### 30. Propagation Cache

The PRG caches propagation results to avoid recomputation:

```python
# src/alea_prg/propagation/cache.py
import hashlib
import pickle

class PropagationCache:
    def __init__(self, backend: str = "redis"):
        self.backend = backend
        if backend == "redis":
            import redis
            self.client = redis.Redis()

    def get(self, param: str, values: Dict[str, float]) -> Optional[float]:
        key = self._make_key(param, values)
        cached = self.client.get(key)
        return pickle.loads(cached) if cached else None

    def set(self, param: str, values: Dict[str, float], result: float):
        key = self._make_key(param, values)
        self.client.set(key, pickle.dumps(result), ex=3600)  # 1 hour TTL

    def _make_key(self, param: str, values: Dict[str, float]) -> str:
        # Only include parameters that affect this one
        relevant = self._relevant_parameters(param)
        relevant_values = {k: v for k, v in values.items() if k in relevant}
        serialized = str(sorted(relevant_values.items()))
        return f"prg:prop:{param}:{hashlib.sha256(serialized.encode()).hexdigest()}"
```

---

## Part VIII: Conflict Detector

### 31. Purpose

The Conflict Detector identifies **over-determined** or **under-determined** parameter sets, and **conflicts** between user-set values and equation-derived values.

### 32. Architecture

```python
# src/alea_prg/conflict/detector.py
class ConflictDetector:
    """Detects conflicts in parameter sets."""

    def __init__(self, prg: nx.DiGraph, equations: Dict[str, Equation]):
        self.prg = prg
        self.equations = equations

    def detect(self, parameters: Dict[str, float]) -> List["Conflict"]:
        """Detect all conflicts in a parameter set."""
        conflicts = []

        # 1. Over-determined: more equations than free parameters
        over = self._detect_over_determined(parameters)
        if over:
            conflicts.append(over)

        # 2. Under-determined: more free parameters than equations
        under = self._detect_under_determined(parameters)
        if under:
            conflicts.append(under)

        # 3. Direct conflicts: user value differs from equation-derived value
        direct = self._detect_direct_conflicts(parameters)
        conflicts.extend(direct)

        # 4. Cycle conflicts: feedback loops do not converge
        cycle = self._detect_cycle_conflicts(parameters)
        conflicts.extend(cycle)

        return conflicts

    def _detect_over_determined(self, parameters):
        """Detect if more equations than free parameters."""
        free_params = [p for p in parameters if self._is_free(p)]
        active_eqs = [eq for eq in self.equations.values() if eq.is_active]
        if len(active_eqs) > len(free_params):
            return Conflict(
                type="over_determined",
                severity="error",
                surplus=len(active_eqs) - len(free_params),
                message="More equations than free parameters"
            )
        return None

    def _detect_under_determined(self, parameters):
        """Detect if more free parameters than equations."""
        free_params = [p for p in parameters if self._is_free(p)]
        active_eqs = [eq for eq in self.equations.values() if eq.is_active]
        if len(free_params) > len(active_eqs):
            return Conflict(
                type="under_determined",
                severity="warning",
                deficit=len(free_params) - len(active_eqs),
                message="More free parameters than equations; system has degrees of freedom"
            )
        return None

    def _detect_direct_conflicts(self, parameters):
        """Detect when user value differs from equation-derived value."""
        conflicts = []
        for eq in self.equations.values():
            if not eq.is_active:
                continue
            for param in eq.determined_variables:
                if param in parameters:
                    derived = EquationEvaluator(eq).solve_for(param, parameters)
                    if abs(parameters[param] - derived) > eq.tolerance:
                        conflicts.append(Conflict(
                            type="direct_conflict",
                            severity="error",
                            parameter=param,
                            user_value=parameters[param],
                            derived_value=derived,
                            equation=eq.id,
                            message=f"User value for {param} differs from equation-derived value"
                        ))
        return conflicts
```

### 33. Conflict Resolution

The Conflict Resolver suggests corrections:

```python
# src/alea_prg/conflict/resolver.py
class ConflictResolver:
    """Resolves conflicts in parameter sets."""

    def resolve(self, conflict: Conflict,
                parameters: Dict[str, float]) -> List["Resolution"]:
        """Suggest resolutions for a conflict."""
        if conflict.type == "direct_conflict":
            return self._resolve_direct(conflict, parameters)
        elif conflict.type == "over_determined":
            return self._resolve_over(conflict, parameters)
        elif conflict.type == "under_determined":
            return self._resolve_under(conflict, parameters)
        return []

    def _resolve_direct(self, conflict, parameters):
        """Resolve a direct conflict by adjusting one of the conflicting parameters."""
        resolutions = []
        # Option 1: Adjust the user value
        resolutions.append(Resolution(
            type="adjust_user_value",
            parameter=conflict.parameter,
            current=conflict.user_value,
            suggested=conflict.derived_value,
            reason="Match equation-derived value"
        ))
        # Option 2: Adjust the equation
        resolutions.append(Resolution(
            type="deactivate_equation",
            equation=conflict.equation,
            reason="Disable consistency check"
        ))
        # Option 3: Adjust upstream parameters
        upstream = self._find_upstream_adjustments(conflict, parameters)
        resolutions.extend(upstream)
        return resolutions
```

### 34. Suggestion Ranking

Suggestions are ranked by:

| Criterion | Weight | Rationale |
|---|---|---|
| **Minimal change** | 30% | Prefer small adjustments |
| **User priority** | 25% | Respect user's parameters |
| **Data quality** | 20% | Prefer adjusting less reliable parameters |
| **Domain precedent** | 15% | Prefer adjustments consistent with practice |
| **Computational cost** | 10% | Prefer adjustments that are cheap to evaluate |

```python
# src/alea_prg/conflict/ranking.py
def rank_suggestions(suggestions: List[Resolution],
                     parameters: Dict[str, float]) -> List[Resolution]:
    """Rank suggestions by a weighted score."""
    for s in suggestions:
        s.score = (
            0.30 * s.minimal_change_score()
            + 0.25 * s.user_priority_score()
            + 0.20 * s.data_quality_score()
            + 0.15 * s.domain_precedent_score()
            + 0.10 * s.computational_cost_score()
        )
    return sorted(suggestions, key=lambda s: -s.score)
```

---

## Part IX: Feedback Loop Solver

### 35. Purpose

The Feedback Loop Solver iteratively solves the ~15 feedback loops in the PRG until convergence. It answers the question: **"Given these feedback relationships, what is the equilibrium?"**

### 36. Architecture

```python
# src/alea_prg/feedback/solver.py
class FeedbackSolver:
    """Iteratively solves feedback loops in the PRG."""

    def __init__(self, prg: nx.DiGraph, equations: Dict[str, Equation],
                 max_iter: int = 20, tol: float = 1e-4):
        self.prg = prg
        self.equations = equations
        self.max_iter = max_iter
        self.tol = tol

    def solve(self, parameters: Dict[str, float]) -> "FeedbackResult":
        """Solve all feedback loops."""
        # Find cycles
        cycles = list(nx.simple_cycles(self.prg))

        # Collapse cycles into super-nodes
        super_graph, super_nodes = self._collapse_cycles(cycles)

        # Solve each super-node iteratively
        results = {}
        for super_node in super_nodes:
            result = self._solve_super_node(super_node, parameters)
            results[super_node] = result

        # Merge results
        final = parameters.copy()
        for result in results.values():
            final.update(result.values)

        return FeedbackResult(
            values=final,
            converged=all(r.converged for r in results.values()),
            iterations=max(r.iterations for r in results.values()),
            residual=max(r.residual for r in results.values())
        )

    def _solve_super_node(self, super_node, parameters):
        """Iteratively solve a super-node."""
        values = parameters.copy()
        for i in range(self.max_iter):
            prev = values.copy()
            for param in super_node:
                eq = self._find_determining_equation(param)
                if eq:
                    values[param] = EquationEvaluator(eq).solve_for(param, values)
            if self._converged(prev, values):
                return FeedbackResult(
                    values=values,
                    converged=True,
                    iterations=i + 1,
                    residual=self._residual(prev, values)
                )
        return FeedbackResult(
            values=values,
            converged=False,
            iterations=self.max_iter,
            residual=self._residual(prev, values)
        )

    def _converged(self, prev, curr):
        return all(abs(curr[k] - prev[k]) < self.tol for k in curr)

    def _residual(self, prev, curr):
        return max(abs(curr[k] - prev[k]) for k in curr)
```

### 37. Convergence Acceleration

For slow-converging loops, the solver uses **Anderson acceleration** or **Aitken's delta-squared method**:

```python
# src/alea_prg/feedback/acceleration.py
class AndersonAccelerator:
    def __init__(self, m: int = 5):
        self.m = m  # History size
        self.history = []

    def accelerate(self, x_k: np.ndarray, g_k: np.ndarray) -> np.ndarray:
        """Apply Anderson acceleration."""
        self.history.append((x_k, g_k))
        if len(self.history) < 2:
            return g_k

        # Use last m iterations
        history = self.history[-self.m:]
        X = np.column_stack([x for x, _ in history])
        G = np.column_stack([g for _, g in history])
        R = G - X

        # Solve least-squares problem
        try:
            gamma = np.linalg.lstsq(R[:, :-1], R[:, -1], rcond=None)[0]
            return (1 - gamma.sum()) * G[:, -1] + G[:, :-1] @ gamma
        except np.linalg.LinAlgError:
            return g_k
```

### 38. Convergence Monitoring

```python
# src/alea_prg/feedback/convergence.py
class ConvergenceMonitor:
    def __init__(self, tol: float = 1e-4):
        self.tol = tol
        self.history = []

    def check(self, iteration: int, residual: float) -> bool:
        """Check if convergence is reached."""
        self.history.append({"iteration": iteration, "residual": residual})
        return residual < self.tol

    def report(self) -> dict:
        """Report convergence diagnostics."""
        if not self.history:
            return {"converged": False, "iterations": 0}
        return {
            "converged": self.history[-1]["residual"] < self.tol,
            "iterations": len(self.history),
            "final_residual": self.history[-1]["residual"],
            "history": self.history
        }
```

---

## Part X: Translation Layer

### 39. Purpose

The Translation Layer converts PRG equations into the constraint format required by the optimisation engine.

### 40. Architecture

```python
# src/alea_prg/translation/pypsa.py
import pypsa

class PyPSATranslator:
    """Translates PRG equations to PyPSA constraints."""

    def __init__(self, prg, equations):
        self.prg = prg
        self.equations = equations

    def translate(self, network: pypsa.Network, parameters: dict):
        """Add PRG-derived constraints to a PyPSA network."""
        for eq_id, equation in self.equations.items():
            if equation.system == "energy_balance":
                self._add_energy_balance(network, equation, parameters)
            elif equation.system == "emissions":
                self._add_emissions(network, equation, parameters)
            elif equation.system == "reserve_margin":
                self._add_reserve_margin(network, equation, parameters)
            elif equation.system == "inertia":
                self._add_inertia(network, equation, parameters)
            elif equation.system == "water_nexus":
                self._add_water_nexus(network, equation, parameters)
            # ... etc.

    def _add_energy_balance(self, network, equation, parameters):
        """Energy balance is already handled by PyPSA's LOPF."""
        pass

    def _add_reserve_margin(self, network, equation, parameters):
        """Add reserve margin constraint."""
        import linopy
        m = network.model
        total_capacity = m.add_variables(
            name="total_capacity",
            coords=[network.generators.index],
            lower=0
        )
        # ... add constraint
```

### 41. Backends

| Backend | Purpose | When to Use |
|---|---|---|
| **PyPSA** | Native constraints | Energy balance, capacity expansion |
| **Linopy** | Custom linear constraints | Reserve margin, inertia, water nexus |
| **Pyomo** | Complex MILP constraints | Unit commitment, maintenance scheduling |
| **SymPy** | Symbolic manipulation | Equation solving, sensitivity analysis |
| **Custom** | Iterative solvers | Feedback loops, debt sizing |

### 42. Constraint Generation

```python
# src/alea_prg/translation/linopy.py
import linopy

class LinopyTranslator:
    """Translates PRG equations to Linopy constraints."""

    def translate(self, model: linopy.Model, equation: Equation,
                  parameters: dict):
        """Add a Linopy constraint for an equation."""
        # Parse the equation
        lhs = self._parse_to_linopy(equation.lhs, model, parameters)
        rhs = self._parse_to_linopy(equation.rhs, model, parameters)

        # Add constraint
        if equation.relation == "eq":
            model.add_constraints(lhs == rhs, name=equation.id)
        elif equation.relation == "leq":
            model.add_constraints(lhs <= rhs, name=equation.id)
        elif equation.relation == "geq":
            model.add_constraints(lhs >= rhs, name=equation.id)
```

---

## Part XI: API Specification

### 43. REST API Endpoints

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/v1/prg/graph` | GET | Retrieve the full PRG | API key |
| `/v1/prg/graph/export` | GET | Export PRG as GraphML | API key |
| `/v1/prg/parameters` | GET | List all parameters | API key |
| `/v1/prg/parameters/{id}` | GET | Get parameter details | API key |
| `/v1/prg/parameters/{id}/dependents` | GET | Get dependent parameters | API key |
| `/v1/prg/equations` | GET | List all equations | API key |
| `/v1/prg/equations/{id}` | GET | Get equation details | API key |
| `/v1/prg/consistency/check` | POST | Check parameter set | API key |
| `/v1/prg/consistency/report` | GET | Get last consistency report | API key |
| `/v1/prg/propagate` | POST | Propagate a change | API key |
| `/v1/prg/conflicts/detect` | POST | Detect conflicts | API key |
| `/v1/prg/conflicts/resolve` | POST | Resolve conflicts | API key |
| `/v1/prg/feedback/solve` | POST | Solve feedback loops | API key |
| `/v1/prg/translate` | POST | Translate to PyPSA/Linopy | API key |

### 44. Request/Response Examples

**Check consistency**:

```bash
POST /v1/prg/consistency/check
{
  "parameters": {
    "carbon_price": 150,
    "coal_retirement_schedule": 2050,
    "renewable_target": 80,
    "demand_growth_rate": 0.06
  }
}
```

**Response**:

```json
{
  "is_consistent": false,
  "violations": [
    {
      "equation": "carbon_coal_retirement_consistency",
      "type": "residual_too_large",
      "residual": 0.35,
      "tolerance": 0.1,
      "parameters": ["carbon_price", "coal_retirement_schedule"],
      "suggestion": {
        "type": "adjust_parameter",
        "parameter": "coal_retirement_schedule",
        "current_value": 2050,
        "suggested_value": 2040,
        "delta": -10
      }
    }
  ],
  "warnings": [],
  "info": [
    {
      "message": "2 parameters adjusted by propagation",
      "parameters": ["coal_retirement_rate", "just_transition_funding"]
    }
  ]
}
```

**Propagate a change**:

```bash
POST /v1/prg/propagate
{
  "changed_parameter": "carbon_price",
  "new_value": 200,
  "current_values": { ... }
}
```

**Response**:

```json
{
  "propagated_values": {
    "carbon_price": 200,
    "carbon_price_escalation": 0.05,
    "carbon_cost": 40.0,
    "coal_capacity": 15000,
    "coal_retirement_schedule": 2035,
    "coal_retirement_rate": 2500,
    "total_emissions": 200,
    "electricity_price": 85.0,
    "renewable_target": 85,
    "renewable_capacity": 55000
  },
  "propagation_path": [
    "carbon_price",
    "carbon_cost",
    "coal_capacity",
    "coal_retirement_schedule",
    "coal_retirement_rate",
    "total_emissions",
    "electricity_price",
    "renewable_target",
    "renewable_capacity"
  ],
  "iterations": 3,
  "converged": true
}
```

### 45. Python SDK

```python
# alea_prg/sdk.py
from alea_prg import PRGClient

client = PRGClient(api_key="...")

# Get the PRG
graph = client.get_graph()

# Check consistency
report = client.check_consistency({
    "carbon_price": 150,
    "coal_retirement_schedule": 2050,
    "renewable_target": 80,
})

if not report.is_consistent:
    for violation in report.violations:
        print(f"{violation['equation']}: {violation['suggestion']}")

# Propagate a change
result = client.propagate("carbon_price", 200, current_values={...})
print(result.propagated_values)
```

---

## Part XII: User Interface

### 46. Interactive Graph Visualisation

The PRG UI provides an **interactive graph view** using **Cytoscape.js**:

- **Nodes** are coloured by category (28 colours)
- **Edges** are styled by relationship type (solid = equality, dashed = inequality, dotted = feedback)
- **Click** a node to see parameter details
- **Drag** a node to reposition
- **Zoom** and **pan** to explore
- **Filter** by category, role, priority
- **Search** for a parameter by name
- **Highlight** dependencies when a node is selected

### 47. Parameter Editor

The parameter editor provides:

- **Sliders** for continuous parameters
- **Dropdowns** for categorical parameters
- **Date pickers** for temporal parameters
- **Map editors** for spatial parameters
- **Time-series editors** for temporal parameters
- **Validation feedback** in real time
- **Propagation preview** showing what will change
- **Consistency status** (green/yellow/red)

### 48. Conflict Resolution UI

When a conflict is detected, the UI shows:

- **The conflicting equation** with its parameters
- **The current values** and the **derived values**
- **Suggested corrections** ranked by score
- **One-click apply** for each suggestion
- **Manual override** with explanation
- **Comparison** of scenarios with and without correction

### 49. Propagation Visualisation

When a parameter is changed, the UI shows:

- **Animated propagation** along the graph edges
- **List of affected parameters** with their new values
- **Magnitude of change** (colour-coded)
- **Time to propagate** (for performance monitoring)
- **Convergence status** for feedback loops

---

## Part XIII: Performance Requirements

### 50. Performance Targets

| Operation | Target | Hardware |
|---|---|---|
| **Load PRG** | < 2 seconds | 8 cores, 16 GB RAM |
| **Consistency check (full)** | < 5 seconds | 8 cores, 16 GB RAM |
| **Consistency check (incremental)** | < 100 ms | 8 cores, 16 GB RAM |
| **Propagate a single change** | < 500 ms | 8 cores, 16 GB RAM |
| **Propagate a batch of 100 changes** | < 5 seconds | 8 cores, 16 GB RAM |
| **Detect conflicts** | < 3 seconds | 8 cores, 16 GB RAM |
| **Resolve conflicts** | < 1 second | 8 cores, 16 GB RAM |
| **Solve feedback loops** | < 30 seconds | 8 cores, 16 GB RAM |
| **Translate to PyPSA constraints** | < 10 seconds | 8 cores, 16 GB RAM |
| **Graph visualisation load** | < 3 seconds | Browser |

### 51. Scalability

| Metric | Target |
|---|---|
| **Maximum parameters** | 10,000 |
| **Maximum equations** | 500 |
| **Maximum edges** | 50,000 |
| **Maximum cycles** | 100 |
| **Maximum propagation depth** | 50 |
| **Concurrent users** | 100 |

### 52. Caching Strategy

| Cache | TTL | Size | Purpose |
|---|---|---|---|
| **PRG graph** | 1 hour | 100 MB | Avoid reloading graph |
| **Equation evaluations** | 5 min | 1 GB | Avoid recomputing |
| **Propagation results** | 5 min | 500 MB | Avoid recomputing |
| **Consistency reports** | 5 min | 100 MB | Avoid recomputing |
| **Conflict suggestions** | 5 min | 50 MB | Avoid recomputing |
| **Feedback solutions** | 5 min | 200 MB | Avoid recomputing |

---

## Part XIV: Testing and Validation

### 53. Unit Tests

| Test Category | Coverage Target | Examples |
|---|---|---|
| **Graph construction** | 100% | Build PRG from YAML |
| **Node/edge models** | 100% | Pydantic validation |
| **Equation parsing** | 100% | DSL parser |
| **Equation evaluation** | 100% | Symbolic and numeric |
| **Consistency engine** | 95% | All equation types |
| **Propagation engine** | 95% | All propagation scenarios |
| **Conflict detector** | 95% | All conflict types |
| **Feedback solver** | 90% | All feedback loops |
| **Translation layer** | 90% | All backends |
| **API endpoints** | 100% | All endpoints |

### 54. Integration Tests

| Test | Purpose |
|---|---|
| **End-to-end consistency** | Check a complete parameter set |
| **Propagation across all systems** | Change a parameter and verify all dependents update |
| **Conflict detection and resolution** | Introduce a conflict and resolve it |
| **Feedback loop convergence** | Solve a feedback loop and verify convergence |
| **PyPSA translation** | Translate equations and solve a small network |
| **API integration** | Call all API endpoints and verify responses |

### 55. Regression Tests

| Test | Purpose |
|---|---|
| **Scenario reproducibility** | Re-run a scenario and verify identical results |
| **Parameter sensitivity** | Verify that changing a parameter changes the output as expected |
| **Cross-validation** | Verify that cross-validation rules fire correctly |
| **Performance regression** | Verify that performance targets are met |

### 56. Property-Based Tests

| Property | Test |
|---|---|
| **Unit consistency** | All equations are dimensionally consistent |
| **Range consistency** | All parameter values are within their ranges |
| **Type consistency** | All parameter values match their types |
| **Graph acyclicity** | The PRG (after cycle collapsing) is acyclic |
| **Propagation termination** | Propagation always terminates |
| **Feedback convergence** | Feedback loops always converge (or raise) |

---

## Part XV: Roadmap and Delivery

### 57. Phased Delivery

| Phase | Duration | Deliverable |
|---|---|---|
| **1. Data model** | 3 weeks | Node, edge, equation models |
| **2. Graph store** | 2 weeks | NetworkX + PostgreSQL persistence |
| **3. Equation library** | 4 weeks | 20 systems of equations |
| **4. DSL and parser** | 3 weeks | Equation DSL + Lark parser |
| **5. Type system** | 2 weeks | Parameter types, units, validation |
| **6. Consistency engine** | 4 weeks | Validation, tolerance, reporting |
| **7. Propagation engine** | 3 weeks | Topological sort, incremental updates |
| **8. Conflict detector** | 3 weeks | Detection, resolution, ranking |
| **9. Feedback solver** | 3 weeks | Iterative solver, acceleration |
| **10. Translation layer** | 4 weeks | PyPSA, Linopy, Pyomo backends |
| **11. API** | 2 weeks | FastAPI endpoints |
| **12. UI** | 4 weeks | Cytoscape graph view, parameter editor |
| **13. Testing** | 4 weeks | Unit, integration, regression tests |
| **14. Documentation** | 2 weeks | User guide, developer guide, API reference |
| **15. Production release** | 2 weeks | Deployment, monitoring, support |

**Total: 45 weeks (approximately 11 months)**

### 58. Milestones

| Milestone | Target Date | Success Metric |
|---|---|---|
| **PRG defined** | Month 2 | All 784 parameters with 2,500 edges |
| **Equations implemented** | Month 4 | All 20 systems, ~120,000 constraints |
| **Consistency working** | Month 6 | All equations validated |
| **Propagation working** | Month 8 | Change propagates correctly |
| **Conflicts working** | Month 9 | Conflicts detected and resolved |
| **Feedback working** | Month 10 | All 15 cycles converge |
| **Translation working** | Month 11 | PyPSA/Linopy constraints generated |
| **API and UI working** | Month 12 | Full end-to-end workflow |
| **Production release** | Month 14 | Live in production |

---

## Part XVI: Conclusion

The Parameter Relationship Graph (PRG) is the **subsystem that makes Alea coherent**. It transforms 784 independent parameters into a **coupled system of 20 equation systems and ~120,000 constraints** that enforce physical, economic, and policy consistency. It validates every parameter change, propagates it to all dependents, detects conflicts, suggests corrections, solves feedback loops, and translates equations into optimisation constraints.

Without the PRG, Alea would produce physically impossible, economically inconsistent, or self-contradictory scenarios. With it, Alea becomes a **world-class energy intelligence platform** whose outputs are internally consistent, physically possible, and economically coherent — trusted by every stakeholder in Africa's energy transition.

The specification defines:

- **784 parameter nodes** with types, units, roles, and metadata
- **~2,500 relationship edges** with relationship types, directions, and strengths
- **20 equation systems** with ~120,000 constraints
- **A DSL** for defining equations in a human-readable format
- **A type system** with Pydantic validation and Pint unit handling
- **A consistency engine** that validates parameter sets
- **A propagation engine** that propagates changes
- **A conflict detector** that detects and resolves conflicts
- **A feedback solver** that iteratively solves 15 feedback loops
- **A translation layer** that converts equations to PyPSA, Linopy, and Pyomo constraints
- **A REST API** for programmatic access
- **An interactive UI** for graph exploration, parameter editing, conflict resolution, and propagation visualisation
- **Performance targets** for all operations
- **Testing and validation** frameworks for all subsystems
- **A 14-month roadmap** with clear milestones

This specification is designed for **intermediate Python developers** to implement incrementally, with each phase independently testable and deployable. It is grounded in **validated methodologies** (NetworkX, SymPy, Pydantic, Pint, Linopy, PyPSA) and uses **open-source tools** wherever possible. The result is a subsystem that makes Alea not just a model but a **coherent, consistent, and trusted decision-support system** for Africa's energy transition.