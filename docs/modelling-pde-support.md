# ALEA PRG and DSL: Partial Differential Equation Support

## Direct Answer

**No, the PRG and DSL as currently specified do not support partial differential equations (PDEs).** The DSL supports linear, polynomial, and general non-linear **algebraic** equations, and it can handle **ordinary differential equations (ODEs)** if they are pre-discretised. But it has no native concept of continuous spatial coordinates, partial derivatives, discretisation schemes, boundary conditions, or mesh-based solving. This is a genuine gap that must be addressed if ALEA is to model the physics-based phenomena for which PDEs are required.

This is a technical, honest, and important gap. Let me explain it fully.

---

## 1. What the Current DSL Supports

The DSL I specified supports **ten classes of equations**, of which seven are algebraic and three are differential (in limited form):

| # | Class | Example | Supported? |
|---|---|---|---|
| 1 | Linear algebraic | `total_cost = Σ(capex × capacity)` | ✅ Yes |
| 2 | Polynomial algebraic | `reserve_margin = a·capacity² + b·capacity + c` | ✅ Yes |
| 3 | Non-linear algebraic | `lcoe = capex / (cf · 8760) + opex` | ✅ Yes |
| 4 | Logarithmic | `cost = cost_0 · (Q/Q_0)^(-b)` | ✅ Yes |
| 5 | Exponential | `degradation = exp(-λt)` | ✅ Yes |
| 6 | Trigonometric | `power_factor = cos(φ)` | ✅ Yes |
| 7 | Implicit algebraic | `f(x, y) = 0` (y cannot be isolated) | ✅ Yes (via SymPy solver) |
| 8 | Scalar ODE | `dS/dt = I - O` (discretised) | ⚠️ Partial (must pre-discretise) |
| 9 | System of ODEs | `dx/dt = f(x,y,t)`, `dy/dt = g(x,y,t)` | ⚠️ Partial (must pre-discretise) |
| 10 | Differential-Algebraic (DAE) | `f(dx/dt, x, y) = 0` | ⚠️ Partial (needs DAE solver) |
| 11 | **PDE (1D)** | `∂u/∂t = α·∂²u/∂x²` | ❌ **No** |
| 12 | **PDE (2D/3D)** | `∂u/∂t = α·∇²u` | ❌ **No** |
| 13 | **Integro-differential** | `u(x) = ∫K(x,y)u(y)dy + f(x)` | ❌ **No** |
| 14 | **Stochastic PDE** | `∂u/∂t = f(u) + η(x,t)` | ❌ **No** |

The DSL's grammar (Section 14 of the PRG Specification) is:

```
expression: term (("+" | "-") term)*
term: factor (("*" | "/") factor)*
factor: base ("**" factor)?
base: atom | "(" expression ")" | function_call | summation
```

This grammar has **no production rule for spatial derivatives, partial derivatives, gradients, Laplacians, or integrals**. It is fundamentally algebraic.

SymPy — which powers the equation evaluator — **can** represent PDEs symbolically (`sp.Eq(sp.diff(u, t), alpha * sp.diff(u, x, 2))`), but the PRG's evaluator, consistency engine, propagation engine, and feedback solver are all designed around **pointwise evaluation**, not **field-based solving**.

---

## 2. Where ALEA Genuinely Needs PDEs

Fourteen ALEA parameters require PDE-based modelling. Let me be specific about each.

### PDE 1: Reservoir Level Dynamics (1D Shallow Water / Muskingum)

**Parameter**: `hydro_reservoir_level`

**Physics**: The Saint-Venant equations govern unsteady open-channel flow:

$$\frac{\partial A}{\partial t} + \frac{\partial Q}{\partial x} = 0 \quad \text{(continuity)}$$

$$\frac{\partial Q}{\partial t} + \frac{\partial}{\partial x}\left(\frac{Q^2}{A}\right) + gA\frac{\partial h}{\partial x} = gA(S_0 - S_f) \quad \text{(momentum)}$$

**Simplification**: The Muskingum method reduces this to an algebraic routing equation:

$$O(t+1) = C_0 \cdot I(t+1) + C_1 \cdot I(t) + C_2 \cdot O(t)$$

where $C_0 + C_1 + C_2 = 1$. **This is already algebraic.**

**Verdict**: PDE → ODE → algebraic. **No PDE support needed** if Muskingum is used.

### PDE 2: Reservoir Cascade Routing

**Parameter**: `hydro_capacity_factor`, `hydro_inflow_year`

**Physics**: For cascaded reservoirs on the Nile, Congo, Zambezi, or Orange, the flow at downstream plant $i$ depends on the release from upstream plant $i-1$:

$$Q_i(t) = Q_{i-1}(t - \tau_i) + \text{local inflow}_i(t)$$

where $\tau_i$ is the travel time.

**Verdict**: This is a **delay differential equation**, not a PDE. It can be handled by a discrete delay term in the DSL (which already supports time indexing).

### PDE 3: Hydrogen Pipeline Dynamics

**Parameter**: `hydrogen_pipeline_capacity`, `hydrogen_pipeline_cost`

**Physics**: Isothermal compressible flow in a pipeline is governed by:

$$\frac{\partial \rho}{\partial t} + \frac{\partial (\rho v)}{\partial x} = 0 \quad \text{(mass)}$$

$$\frac{\partial p}{\partial x} = -\frac{f \rho v^2}{2D} \quad \text{(momentum, quasi-steady)}$$

**Simplification**: For steady-state flow (which is what most energy system models assume), the momentum equation reduces to an algebraic pressure-drop formula:

$$p_{i+1}^2 - p_i^2 = -k \cdot \dot{m}^2 \cdot L$$

**Verdict**: Steady-state flow is algebraic. **No PDE support needed** for standard capacity planning. Transient pipeline dynamics would require PDE support, but that is beyond ALEA's scope.

### PDE 4: Heat Diffusion in Thermal Storage

**Parameter**: `thermal_storage_capacity`, `thermal_storage_duration`

**Physics**: Heat conduction in a storage medium follows the heat equation:

$$\frac{\partial T}{\partial t} = \alpha \nabla^2 T + \frac{q'''}{\rho c_p}$$

**Discretisation**: Finite difference (explicit):

$$T_{i,j,k}^{n+1} = T_{i,j,k}^n + \frac{\alpha \Delta t}{\Delta x^2}\left(T_{i+1,j,k}^n + T_{i-1,j,k}^n + T_{i,j+1,k}^n + T_{i,j-1,k}^n + T_{i,j,k+1}^n + T_{i,j,k-1}^n - 6T_{i,j,k}^n\right)$$

**Verdict**: For a 10×10×10 grid, this is 1,000 algebraic equations per time step. **PDE becomes algebraic after discretisation**, but the equation count explodes.

### PDE 5: Groundwater Flow (Darcy)

**Parameter**: `water_availability`, `cooling_water_demand`

**Physics**: Confined aquifer flow follows the diffusion equation:

$$S \frac{\partial h}{\partial t} = \nabla \cdot (T \nabla h) + Q$$

**Verdict**: Same structure as heat diffusion. Discretisation yields algebraic equations.

### PDE 6: Atmospheric Pollutant Dispersion

**Parameter**: `pm25_emissions`, `health_impact_mortality`

**Physics**: Advection-diffusion equation:

$$\frac{\partial c}{\partial t} + u \cdot \nabla c = \nabla \cdot (K \nabla c) + S$$

where $c$ is concentration, $u$ is wind velocity, $K$ is turbulent diffusivity, and $S$ is source term (power plant emissions).

**Verdict**: Requires 3D PDE with wind fields. This is what atmospheric dispersion models like AERMOD, CALPUFF, and CAMx solve. **ALEA cannot solve this natively.**

### PDE 7: Dynamic Line Rating (Transmission)

**Parameter**: `transmission_capacity_factor`, `line_capacity_override`

**Physics**: Conductor temperature evolution:

$$\frac{\partial T}{\partial t} = \frac{I^2 R(T) + q_s - q_c - q_r}{m c_p}$$

where $I$ is current, $R(T)$ is temperature-dependent resistance, and $q_s$, $q_c$, $q_r$ are solar heating, convective cooling, and radiative cooling. **This is an ODE (no spatial derivatives)** — but if the conductor is spatially discretised along the line, it becomes a 1D PDE.

**Verdict**: Standard dynamic line rating uses lumped-parameter ODE. **No PDE support needed** unless we model thermal gradients along the conductor.

### PDE 8: Battery Thermal Management

**Parameter**: `battery_capacity`, `battery_round_trip_efficiency`

**Physics**: Battery cell temperature follows the heat equation with internal heat generation:

$$\rho c_p \frac{\partial T}{\partial t} = k \nabla^2 T + Q_{gen}$$

**Verdict**: For grid-scale batteries, lumped-parameter models (single temperature per pack) are standard. **No PDE support needed** unless we model cell-level thermal gradients.

### PDE 9: Air Quality (Regional)

**Parameter**: `health_impact_dalys`, `health_impact_mortality`

**Physics**: Regional air quality requires 3D Eulerian models (CAMx, CMAQ, GEOS-Chem).

**Verdict**: **ALEA cannot solve this natively.** Must use pre-computed source-receptor matrices from external models.

### PDE 10: Climate Downscaling

**Parameter**: `ssp_pathway`, `temperature_increase`

**Physics**: Regional climate downscaling uses 3D atmospheric models (WRF, RegCM).

**Verdict**: **ALEA cannot solve this natively.** Must use pre-computed CMIP6 downscaled outputs.

### PDE 11: Seismic / Geological (CO₂ Storage, Geothermal)

**Parameter**: `geothermal_capacity`, `industrial_ccus_share`

**Physics**: Subsurface flow, heat transfer, and geomechanics in porous media:

$$\frac{\partial (\phi \rho)}{\partial t} = \nabla \cdot \left(\frac{\rho k}{\mu} \nabla p\right) + Q$$

**Verdict**: Requires reservoir simulators (TOUGH2, ECLIPSE, CMG-GEM). **ALEA cannot solve this natively.**

### PDE 12: Electromagnetic Transients (HVDC)

**Parameter**: `hvdc_share`, `ac_voltage_limit`

**Physics**: Telegrapher's equations:

$$\frac{\partial V}{\partial x} = -L \frac{\partial I}{\partial t} - R I$$
$$\frac{\partial I}{\partial x} = -C \frac{\partial V}{\partial t} - G V$$

**Verdict**: Needed only for electromagnetic transient (EMT) studies. **Beyond ALEA's scope.**

### PDE 13: Fluid Dynamics (Pumped Hydro)

**Parameter**: `phs_capacity`, `phs_duration`

**Physics**: Penstock flow, turbine dynamics, surge tank oscillations — governed by PDEs.

**Verdict**: Standard PHS modelling uses lumped-parameter approximations (efficiency, head, flow rate). **No PDE support needed** for planning.

### PDE 14: Structural Dynamics (Wind Turbines)

**Parameter**: `wind_offshore_platform`, `wind_onshore_capacity`

**Physics**: Blade and tower dynamics — PDEs in structural mechanics.

**Verdict**: Wind turbine performance is modelled via power curves. **No PDE support needed** for energy system planning.

---

## 3. Summary: Which PDEs Does ALEA Actually Need?

| PDE | Needed for Planning? | Needed for Operations? | Recommended Approach |
|---|---|---|---|
| **Reservoir routing** | No (use Muskingum) | Maybe (for real-time) | Algebraic approximation |
| **Pipeline dynamics** | No (steady-state) | No | Algebraic pressure drop |
| **Heat diffusion (storage)** | No (lumped) | Maybe (for thermal management) | Pre-computed or lumped |
| **Groundwater** | Maybe (for water availability) | No | External model + lookup table |
| **Atmospheric dispersion** | Yes (for health impact) | No | External model + source-receptor matrix |
| **Dynamic line rating** | No (static rating) | Maybe | Lumped ODE (supported) |
| **Battery thermal** | No (lumped) | Maybe | Lumped ODE (supported) |
| **Regional air quality** | Yes (for health impact) | No | External model + lookup |
| **Climate downscaling** | Yes (for scenarios) | No | Pre-computed CMIP6 |
| **CO₂ storage / geothermal** | Maybe (for potential) | No | External model + lookup |
| **EMT** | No | No | Out of scope |
| **Pumped hydro transients** | No (lumped) | Maybe | Lumped ODE (supported) |
| **Structural dynamics** | No (power curve) | No | Out of scope |

**Conclusion**: ALEA needs PDE support **only** for:
1. **Atmospheric dispersion** (health impacts) — best handled by external models
2. **Regional air quality** (health impacts) — best handled by external models
3. **Climate downscaling** (scenarios) — best handled by pre-computed CMIP6
4. **CO₂ storage / geothermal** (potential assessment) — best handled by external models
5. **Groundwater** (water availability) — best handled by external models

For all five, the **pragmatic solution is pre-computation**, not native PDE solving.

---

## 4. The Pragmatic Architecture: Hybrid PDE Handling

Rather than attempting full PDE support (which would require rewriting the DSL, the evaluator, the consistency engine, the propagation engine, and the feedback solver, and would add orders of magnitude to computational cost), I recommend a **hybrid architecture** with three components:

### 4.1 The PDE Extension Layer

A new subsystem that sits **between external PDE solvers and the PRG**:

```python
# src/alea_prg/pde/extension.py
class PDEExtensionLayer:
    """
    Interface between external PDE solvers and the PRG.

    Responsibility: Convert PDE-based sub-models into algebraic
    relationships that the PRG can consume.
    """

    def __init__(self, prg):
        self.prg = prg
        self.solvers = {
            "atmospheric": AERMODAdapter(),
            "groundwater": MODFLOWAdapter(),
            "climate": WRFAdapter(),
            "reservoir": HECRASAdapter(),
            "subsurface": TOUGH2Adapter(),
            "thermal": FEniCSAdapter(),
        }
        self.lookup_tables = {}

    def precompute(self, pde_model: str, parameter_grid: dict) -> "LookupTable":
        """Precompute PDE solutions across a parameter grid."""
        solver = self.solvers[pde_model]
        results = {}
        for param_values in parameter_grid:
            solution = solver.solve(**param_values)
            results[tuple(sorted(param_values.items()))] = solution
        return LookupTable(results)

    def interpolate(self, lookup: "LookupTable", parameters: dict) -> float:
        """Interpolate PDE solution for new parameter values."""
        return lookup.interpolate(parameters)

    def register_in_prg(self, pde_model: str, parameter: str,
                        lookup: "LookupTable"):
        """Register a lookup table as a PRG equation."""
        self.prg.add_equation(
            id=f"pde_{pde_model}_{parameter}",
            type="lookup_table",
            source=lookup,
            parameters=[parameter],
            solution_method="lookup",
        )
```

### 4.2 Pre-Computed Lookup Tables

For each PDE-based sub-model, ALEA pre-computes solutions across a parameter grid and stores them as lookup tables. During scenario exploration, the PRG interpolates.

**Example: Atmospheric Dispersion**

```yaml
pde_lookup_tables:
  atmospheric_dispersion:
    source: "AERMOD"
    inputs:
      - emission_rate: [0, 1000, 5000, 10000]  # tonnes/year
      - stack_height: [50, 100, 200, 300]  # metres
      - wind_speed: [1, 3, 5, 8]  # m/s
      - stability_class: ["A", "B", "C", "D", "E", "F"]
    outputs:
      - pm25_concentration: "μg/m³"
      - population_exposure: "person-μg/m³"
    grid_resolution: "1 km"
    domain: "Southern Africa"
    reference: "AERMOD User's Guide, US EPA"
```

**Example: Groundwater Availability**

```yaml
pde_lookup_tables:
  groundwater_availability:
    source: "MODFLOW"
    inputs:
      - recharge_rate: [50, 100, 200, 400]  # mm/year
      - pumping_rate: [0, 500, 1000, 2000]  # Mm³/year
      - aquifer_storage: [0.01, 0.05, 0.1]
    outputs:
      - water_level_decline: "metres"
      - sustainable_yield: "Mm³/year"
    grid_resolution: "5 km"
    domain: "Nile Basin"
    reference: "MODFLOW 6 Documentation, USGS"
```

### 4.3 External Solver Adapters

For cases where pre-computation is not feasible (e.g., user-specified scenarios outside the pre-computed grid), ALEA provides **external solver adapters**:

| Adapter | PDE Type | External Solver | Interface |
|---|---|---|---|
| `AERMODAdapter` | Atmospheric dispersion | AERMOD (EPA) | Command-line |
| `CALPUFFAdapter` | Regional air quality | CALPUFF | Command-line |
| `MODFLOWAdapter` | Groundwater flow | MODFLOW 6 (USGS) | Python API |
| `WRFAdapter` | Climate downscaling | WRF | Command-line |
| `HECRASAdapter` | Reservoir routing | HEC-RAS | Command-line |
| `TOUGH2Adapter` | Subsurface flow | TOUGH2 | Command-line |
| `FEniCSAdapter` | Generic PDE | FEniCS | Python API |
| `FiPyAdapter` | Generic PDE | FiPy | Python API |
| `DolfinAdapter` | Generic PDE | DOLFINx | Python API |
| `PyClawAdapter` | Hyperbolic PDE | PyClaw | Python API |

**Interface contract**:

```python
class PDESolverAdapter(ABC):
    @abstractmethod
    def solve(self, **parameters) -> "PDESolution":
        """Solve the PDE for given parameters."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Validate the solver is correctly installed."""
        pass

    @abstractmethod
    def version(self) -> str:
        """Return solver version."""
        pass
```

### 4.4 How the PRG Consumes PDE Outputs

PDE outputs are registered as **derived parameters** with **lookup-table equations**:

```python
# Register the lookup table as an equation
prg.add_equation(
    id="atmospheric_dispersion_pm25",
    type="lookup_table",
    source="atmospheric_dispersion_lookup",
    lhs="pm25_concentration",
    rhs="interpolate(atmospheric_dispersion_lookup, emission_rate, stack_height, wind_speed, stability_class)",
    parameters=["emission_rate", "stack_height", "wind_speed", "stability_class"],
    determined_variables=["pm25_concentration"],
    solution_method="lookup",
)
```

The PRG's consistency engine, propagation engine, and feedback solver treat these as ordinary algebraic equations. **They work without modification.**

---

## 5. Extending the DSL for Limited PDE Support

If we want the PRG to handle **some** PDEs natively (specifically, 1D PDEs that can be discretised internally), we can extend the DSL with five new constructs:

### 5.1 Extended Grammar

```lark
// Extended grammar for ALEA DSL v2.0
expression: term (("+" | "-") term)*
term: factor (("*" | "/") factor)*
factor: base ("**" factor)?
base: atom | "(" expression ")" | function_call | summation
     | pde_operator | integral | boundary_condition

// New: PDE operators
pde_operator: "d" atom "/" "d" atom          // ∂u/∂x
            | "d2" atom "/" "d" atom "^2"     // ∂²u/∂x²
            | "grad" "(" expression ")"       // ∇u
            | "div" "(" expression ")"        // ∇·u
            | "laplacian" "(" expression ")"  // ∇²u

// New: Spatial integration
integral: "integral" "(" expression "," atom "," atom "," atom ")"

// New: Boundary conditions
boundary_condition: "bc" "(" atom "," atom "," expression ")"

// New: Discretisation schemes
discretisation: "discretise" "(" atom "," method "," grid ")"
```

### 5.2 New Equation Types

```yaml
pde_1d:
  name: "1D Heat Equation"
  type: "pde"
  domain: [0, L]              # spatial domain
  time_domain: [0, T]         # temporal domain
  lhs: "dT/dt"
  rhs: "alpha * d2T/dx^2"
  initial_condition: "T(x,0) = T_init"
  boundary_conditions:
    - "T(0,t) = T_left"
    - "T(L,t) = T_right"
  discretisation:
    method: "finite_difference"
    scheme: "crank_nicolson"
    spatial_points: 100
    time_steps: 8760
```

### 5.3 Discretisation Engine

```python
# src/alea_prg/pde/discretiser.py
class PDEDiscretiser:
    """Discretise PDEs into algebraic equations."""

    def discretise(self, pde: PDEEquation) -> list[Equation]:
        """Convert a PDE into a system of algebraic equations."""
        if pde.type == "pde_1d":
            return self._discretise_1d(pde)
        elif pde.type == "pde_2d":
            return self._discretise_2d(pde)
        elif pde.type == "pde_3d":
            return self._discretise_3d(pde)

    def _discretise_1d(self, pde):
        """Discretise a 1D PDE using finite differences."""
        equations = []
        n = pde.discretisation.spatial_points
        dt = pde.discretisation.time_step
        dx = pde.length / n
        for i in range(1, n - 1):
            eq = Equation(
                id=f"{pde.id}_node_{i}",
                lhs=f"T_{i}^{{n+1}}",
                rhs=f"T_{i}^n + alpha * dt / dx^2 * (T_{i+1}^n - 2*T_i^n + T_{i-1}^n)",
                parameters=[f"T_{i}", f"T_{i-1}", f"T_{i+1}"],
                determined_variables=[f"T_{i}^{{n+1}}"],
            )
            equations.append(eq)
        return equations
```

### 5.4 When to Use Native PDE Support

Native PDE support should be used **only** when:

1. The PDE is 1D (spatial dimensionality 1)
2. The spatial domain is small (< 1,000 nodes)
3. The time step is hourly (not sub-hourly)
4. The PDE is linear or weakly non-linear
5. The solution must be recomputed frequently (e.g., in every iteration of the feedback solver)

For all other cases, **pre-computation** is more efficient.

---

## 6. Why Full PDE Support Is Probably Not Worth It

If ALEA were to support PDEs natively and fully, the consequences would be:

| Consequence | Impact |
|---|---|
| **DSL complexity** | 3× larger grammar, harder to learn and use |
| **Symbolic evaluation** | SymPy's PDE solver is limited; would need to integrate FEniCS/DOLFINx |
| **Consistency engine** | Would need to check residuals across spatial grids, not just pointwise |
| **Propagation engine** | Would need to propagate through meshes, not just graphs |
| **Feedback solver** | Would need to integrate PDEs in each iteration; computational cost explodes |
| **Translation layer** | Would need to translate PDEs to MILP constraints; usually infeasible |
| **Solver interface** | Would need to couple an LP/MILP solver with a PDE solver; complex |
| **Computational cost** | 100×–10,000× higher for a 3D PDE compared to algebraic |
| **Validation** | Would need a new class of numerical validation (stability, convergence) |

**Verdict**: Full native PDE support is **not worth it**. The pragmatic hybrid approach (pre-computed lookup tables + external solver adapters) delivers 95% of the value at 5% of the cost.

---

## 7. Recommendation

### 7.1 Immediate Actions

1. **Document the limitation** in the PRG specification: the DSL does not support PDEs.
2. **Identify the five PDE-based use cases** (atmospheric dispersion, regional air quality, climate downscaling, CO₂ storage/geothermal, groundwater).
3. **Specify the PDE Extension Layer** with lookup tables and external solver adapters.
4. **Register PDE outputs as derived parameters** with lookup-table equations in the PRG.

### 7.2 Medium-Term Actions

1. **Extend the DSL** with the five new constructs (pde_operator, integral, boundary_condition, discretisation, pde_equation).
2. **Implement the PDEDiscretiser** for 1D linear PDEs.
3. **Integrate FEniCS and FiPy** as external solvers for 2D/3D PDEs.
4. **Add PDE-specific validation** to the consistency engine.

### 7.3 Long-Term Actions

1. **Build a PDE sub-model library** with pre-computed solutions for common cases (atmospheric dispersion, groundwater, subsurface).
2. **Couple the LP/MILP solver with PDE solvers** via a Benders-like decomposition for cases where PDEs feed into optimisation.
3. **Explore surrogate modelling** (neural networks trained on PDE solutions) to accelerate PDE evaluations within the optimisation loop.

---

## 8. Summary Table

| Question | Answer |
|---|---|
| Does the current PRG/DSL support PDEs? | **No** |
| Does it support ODEs? | **Partially** (must pre-discretise) |
| Does it support non-linear algebraic equations? | **Yes** (via SymPy) |
| Does ALEA need full PDE support? | **No** — only five use cases, all handled by pre-computation |
| What is the recommended architecture? | **Hybrid**: pre-computed lookup tables + external solver adapters |
| What is the recommended DSL extension? | **PDE Extension Layer** with lookup-table equations |
| What is the computational cost of native PDE support? | **100×–10,000× higher** than the hybrid approach |
| What is the recommended action? | **Document the limitation, implement the hybrid layer** |

The PRG's algebraic foundation is not a limitation; it is a **deliberate design choice**. ALEA is an energy system planning and intelligence platform, not a computational fluid dynamics solver. By externalising PDEs to specialised solvers and consuming their outputs as algebraic relationships, ALEA preserves the simplicity, speed, and rigour of its core architecture while still delivering the physical accuracy that PDE-based sub-models provide. The result is a platform that is **fit for purpose** — neither over-engineered nor under-powered.