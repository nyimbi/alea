# How the PRG Works: A Detailed Explanation

Let me build this up from the problem it solves, through the mechanism, to a concrete worked example. By the end, you should be able to trace exactly what happens when a user changes any parameter.

---

## 1. The Problem the PRG Solves

Imagine a user opens ALEA and asks: **"What if we set the carbon price to $150?"**

Without the PRG, here's what would happen:

1. The platform takes the number `150` and plugs it into the optimisation model.
2. The optimiser solves and returns *some* answer.
3. But that answer might be **self-contradictory**:
   - The user previously set `coal_retirement_schedule = 2050`.
   - A carbon price of $150 makes coal uneconomic by 2035.
   - The model silently ignores the user's coal retirement date, or it forces coal to remain (which is economically irrational), or it fails to solve.
4. Or the answer might be **physically impossible**:
   - The user also set `renewable_target = 80%` and `reserve_margin = 8%`.
   - With 80% renewables and only 8% reserve margin, the system cannot guarantee reliability.
   - The model returns a scenario that looks fine on paper but is physically infeasible.
5. Or the answer might be **internally inconsistent**:
   - The carbon price reduces emissions, which reduces carbon revenue, which increases the subsidy needed, which raises the effective price of electricity, which reduces demand, which reduces emissions further — but the model doesn't capture that feedback loop.

The **Parameter Relationship Graph (PRG)** exists to prevent all three failures. It ensures that **every scenario the user explores is physically, economically, and policy-coherent**.

---

## 2. The One-Sentence Answer

**The PRG is a dependency graph of typed equations that knows which parameters are inputs (user-set), which are decisions (optimiser-set), and which are derived (computed), and it propagates any parameter change to all dependents while checking consistency and detecting conflicts.**

Think of it as the **"spreadsheet engine"** that sits behind ALEA. When you change a cell in Excel, every formula that references it recalculates. When you change a parameter in ALEA, every equation that involves it recalculates — and every parameter that depends on those equations recalculates too, and so on, until the whole system is consistent again.

But the PRG is **smarter than a spreadsheet** in four ways:

1. **It knows which parameters you set and which the optimiser decides.** A spreadsheet has no concept of endogenous variables.
2. **It handles feedback loops.** A spreadsheet would hit circular references. The PRG collapses cycles and solves them iteratively.
3. **It detects over- and under-determined systems.** A spreadsheet would just say "#REF!". The PRG explains *why* and suggests corrections.
4. **It translates equations into optimisation constraints.** A spreadsheet cannot feed its formulas into a MILP solver. The PRG does.

---

## 3. The Structure: Nodes, Edges, and Equations

The PRG has three components: **nodes** (parameters), **edges** (relationships), and **equations** (the math).

### Nodes: The 784 Parameters

Each parameter is a **node** in the graph. Every node has:

- A **role**: `exogenous` (you set it), `endogenous` (the optimiser decides), `derived` (computed from others), or `free` (metadata).
- A **type**: `float`, `int`, `categorical`, `timeseries`, `spatial`.
- A **unit**: e.g., `USD/tonne`, `MW`, `%`.
- A **range**: e.g., `[0, 500]`.

Here are four example nodes:

| Node | Role | Type | Unit | Range |
|---|---|---|---|---|
| `carbon_price` | exogenous | float | USD/tonne | [0, 500] |
| `coal_capacity_2035` | endogenous | float | MW | [0, 100000] |
| `total_emissions_2035` | derived | float | MtCO₂ | [0, ∞) |
| `lcoe_coal_2035` | derived | float | USD/MWh | [0, 500] |

### Edges: The ~2,500 Relationships

Each edge is a **directed relationship** between two nodes. Every edge has:

- A **source** and a **target**.
- A **relationship type**: `functional` (target = f(source)), `equality`, `inequality`, `feedback`, `temporal`.
- A **strength**: `hard` (inviolable), `soft` (usually true), `informational` (correlation).
- An **equation ID** pointing to the equation that governs the relationship.

Here are four example edges:

| Source | Target | Relationship | Strength | Equation |
|---|---|---|---|---|
| `carbon_price` | `coal_capacity_2035` | functional | soft | `carbon_price_coal_capacity` |
| `coal_capacity_2035` | `total_emissions_2035` | functional | hard | `emissions_accounting` |
| `total_emissions_2035` | `carbon_cost_2035` | functional | hard | `carbon_cost_equation` |
| `carbon_price` | `coal_retirement_schedule` | inequality | soft | `carbon_price_coal_retirement_consistency` |

The first three are **causal**: change the carbon price, and the coal capacity changes; change the coal capacity, and emissions change; change the emissions, and the carbon cost changes.

The fourth is a **consistency rule**: if the carbon price is high, the coal retirement must be early. It's not a physical law, but it's a policy coherence requirement.

### Equations: The 20 Systems of ~120,000 Constraints

Each equation relates two or more parameters. Every equation has:

- A **left-hand side** (LHS) — usually a single derived or endogenous variable.
- A **right-hand side** (RHS) — the expression that determines it.
- A **relation**: `eq`, `leq`, `geq`.
- A **tolerance**: how close the two sides must be.

Here's one equation from the cost system:

```yaml
total_cost:
  lhs: "total_cost"
  rhs: |
    sum(capex_g * p_nom_g for g in generators)
    + sum((opex_variable_g + fuel_cost_g / efficiency_g) * p_g_t
          for g in generators for t in timesteps)
  relation: "eq"
  parameters: [capex_g, opex_variable_g, fuel_cost_g, efficiency_g, p_nom_g, p_g_t]
  determined_variables: [total_cost]
  tolerance: 1e-3
```

And one equation from the policy system:

```yaml
carbon_price_coal_retirement_consistency:
  lhs: "carbon_price_coal_consistency_residual"
  rhs: |
    if carbon_price > 100 and coal_retirement_schedule > 2045 then 1 else 0
  relation: "eq"
  parameters: [carbon_price, coal_retirement_schedule]
  tolerance: 0.1
```

---

## 4. The Graph: What It Looks Like

The whole PRG is a directed graph. Here's a tiny slice around `carbon_price`:

```
                    ┌──────────────────┐
                    │  carbon_price    │  ← You set this
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┬─────────────────┐
              │              │              │                 │
              ▼              ▼              ▼                 ▼
    ┌─────────────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────────┐
    │ carbon_cost_    │ │ carbon_  │ │ coal_       │ │ carbon_price_    │
    │ 2035            │ │ price_   │ │ capacity_   │ │ coal_retirement_ │
    │                 │ │ escal.   │ │ 2035        │ │ consistency      │
    └────────┬────────┘ └────┬─────┘ └──────┬──────┘ └────────┬─────────┘
             │               │              │                 │
             ▼               ▼              ▼                 ▼
    ┌─────────────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────────┐
    │ total_cost_2035 │ │ carbon_  │ │ total_      │ │ coal_retirement_ │
    │                 │ │ cost_    │ │ emissions_  │ │ schedule         │
    │                 │ │ 2040     │ │ 2035        │ │                  │
    └─────────────────┘ └──────────┘ └──────┬──────┘ └──────────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ carbon_revenue_ │
                                    │ 2035            │
                                    └─────────────────┘
```

Each arrow is a directed dependency: the target depends on the source.

---

## 5. A Worked Example: Changing the Carbon Price

Let's trace exactly what happens when a user changes the carbon price from $50 to $150.

### Step 0: The Current Scenario

The user's current parameter values are:

```
carbon_price              = 50
coal_retirement_schedule  = 2050
renewable_target          = 60
demand_growth_rate        = 0.05
coal_capacity_2035        = 45000  (optimiser-determined)
total_emissions_2035      = 280    (derived)
```

### Step 1: The User Requests the Change

The user drags the `carbon_price` slider from 50 to 150.

### Step 2: Consistency Check

Before propagating, the PRG evaluates all equations that involve `carbon_price`. Most pass, but one fails:

**Equation**: `carbon_price_coal_retirement_consistency`
**Rule**: If `carbon_price > 100`, then `coal_retirement_schedule <= 2045`.
**Current values**: `carbon_price = 150`, `coal_retirement_schedule = 2050`.
**Residual**: 1.0 (violated, tolerance = 0.1).

The PRG produces a **violation**:

```
⚠ Inconsistency detected
  Equation: carbon_price_coal_retirement_consistency
  Reason: carbon_price = 150 implies coal retirement before 2045,
          but coal_retirement_schedule is set to 2050.
  Suggested corrections:
    A) Adjust coal_retirement_schedule to 2040
    B) Adjust carbon_price to 95 (below the threshold)
    C) Override the consistency rule (warning: scenario will be flagged)
```

The user picks A.

### Step 3: Propagation

Now the PRG propagates the change. It does this by:

1. Finding all descendants of `carbon_price` and `coal_retirement_schedule` in the graph.
2. Topologically sorting them (so no parameter is evaluated before its dependencies).
3. Evaluating each parameter's determining equation in order.

Here's what the propagation looks like:

| Order | Parameter | Old Value | New Value | Equation Used |
|---|---|---|---|---|
| 1 | `carbon_price` | 50 | 150 | (user-set) |
| 2 | `coal_retirement_schedule` | 2050 | 2040 | (user-corrected) |
| 3 | `carbon_price_escalation` | 0.03 | 0.05 | `carbon_price_escalation_equation` |
| 4 | `carbon_cost_per_MWh_coal` | 42 | 128 | `marginal_cost_equation` |
| 5 | `carbon_cost_per_MWh_gas` | 18 | 55 | `marginal_cost_equation` |
| 6 | `coal_capacity_2035` | 45000 | 28000 | `optimal_capacity_equation` (optimiser) |
| 7 | `coal_generation_2035` | 180 TWh | 105 TWh | `dispatch_equation` (optimiser) |
| 8 | `total_emissions_2035` | 280 Mt | 165 Mt | `emissions_accounting` |
| 9 | `carbon_revenue_2035` | $14B | $24.75B | `carbon_revenue_equation` |
| 10 | `coal_retirement_rate` | 1500 MW/yr | 3200 MW/yr | `retirement_rate_equation` |
| 11 | `renewable_capacity_2035` | 62000 MW | 89000 MW | `optimal_capacity_equation` (optimiser) |
| 12 | `storage_capacity_2035` | 8000 MW | 14000 MW | `optimal_capacity_equation` (optimiser) |
| 13 | `electricity_price_2035` | $65/MWh | $82/MWh | `market_clearing_equation` |
| 14 | `consumer_cost_2035` | $130B | $164B | `consumer_cost_equation` |
| 15 | `energy_poverty_rate_2035` | 18% | 24% | `energy_poverty_equation` |
| 16 | `direct_jobs_coal_2035` | 85000 | 52000 | `employment_equation` |
| 17 | `just_transition_funding` | $1.2B | $4.1B | `just_transition_equation` |
| 18 | `health_impact_dalys_2035` | 420000 | 260000 | `health_impact_equation` |
| 19 | `healthcare_cost_2035` | $3.2B | $1.9B | `healthcare_cost_equation` |
| 20 | `total_system_cost_2035` | $42B | $58B | `total_cost_equation` |

Every one of these 20 changes happened **automatically** as a consequence of changing one parameter.

Notice the **ripple effects**:

- The carbon price increase reduced coal capacity (step 6).
- This reduced emissions (step 8).
- But the carbon revenue actually **increased** (step 9) because the price effect dominates the volume effect.
- The consumer cost went **up** (step 14) — this is the political cost.
- The energy poverty rate went **up** (step 15) — this is the social cost.
- Coal jobs went **down** (step 16) — this is the just transition issue.
- Just transition funding went **up** (step 17) — this is the policy response.
- Health improved (steps 18–19) — this is the health benefit.
- Total system cost went **up** (step 20) — this is the economic cost.

### Step 4: Feedback Loops

Some of the parameters in the propagation feed back into each other. Consider this loop:

```
carbon_price ↑ → coal_capacity ↓ → emissions ↓ → carbon_revenue ↓
                                                       │
                                                       ▼
                                              subsidies_needed ↑
                                                       │
                                                       ▼
                                              electricity_price ↑
                                                       │
                                                       ▼
                                              demand ↓ (if elastic)
                                                       │
                                                       ▼
                                              emissions ↓
```

This is a **negative feedback loop**: it damps the effect of the original change. The PRG detects the loop (using Tarjan's strongly connected components algorithm), collapses it into a super-node, and iterates until convergence.

For this loop, the iteration might look like:

| Iteration | carbon_revenue | subsidies | electricity_price | demand | emissions |
|---|---|---|---|---|---|
| 0 | $24.75B | $2.1B | $82 | 100 TWh | 165 Mt |
| 1 | $24.2B | $2.4B | $83.5 | 98 TWh | 162 Mt |
| 2 | $23.8B | $2.6B | $84.3 | 97 TWh | 160 Mt |
| 3 | $23.6B | $2.7B | $84.7 | 96.5 TWh | 159 Mt |
| ... | ... | ... | ... | ... | ... |
| Converged | $23.5B | $2.8B | $85 | 96 TWh | 158 Mt |

The loop converges in about 5–10 iterations (residual < 1e-4).

### Step 5: Consistency Re-Check

After propagation and feedback convergence, the PRG re-checks all equations. If any are now violated, it flags them and either auto-corrects or reports to the user.

In this example, everything is now consistent. The scenario passes.

### Step 6: Translation to Optimisation Constraints

Finally, the PRG translates the parameter set into:

- **PyPSA network attributes**: `n.generators.p_nom`, `n.generators.marginal_cost`, `n.lines.capital_cost`, etc.
- **Linopy constraints**: reserve margin, inertia, water balance, etc.
- **Exogenous inputs**: carbon price trajectory, fuel prices, demand profile.

### Step 7: Solve and Return

The optimiser solves the network. The results are returned to the user, who sees:

- The full set of 784 parameter values (updated).
- A summary of what changed and why.
- A list of any remaining warnings.
- The optimisation results.

---

## 6. The Four Mechanisms

The worked example touches on all four mechanisms. Let me name them clearly.

### Mechanism 1: Consistency Checking

The consistency engine evaluates every equation and reports violations. It runs:
- **Before** propagation (to catch initial inconsistencies).
- **After** propagation (to catch new ones).

Each violation has:
- The equation ID.
- The residual (how far from consistent).
- The parameters involved.
- One or more suggested corrections.

### Mechanism 2: Propagation

The propagation engine computes the values of all dependent parameters. It uses:
- **Topological sorting** to ensure no parameter is evaluated before its dependencies.
- **Cycle collapsing** to handle feedback loops.
- **Caching** to avoid recomputing unchanged parameters.

The propagation is **transitive**: if A changes B, and B changes C, and C changes D, then changing A changes D — automatically.

### Mechanism 3: Conflict Detection

The conflict detector identifies three types of conflicts:

**Over-determined**: More equations than free parameters. Example: the user sets both `carbon_price = 150` and `coal_retirement = 2050`, violating a consistency rule. Two constraints, one degree of freedom.

**Under-determined**: More free parameters than equations. Example: the user leaves both `carbon_price` and `coal_retirement` unset. Two unknowns, no constraints. The system has degrees of freedom, and the user must supply more information.

**Direct conflict**: The user sets a parameter that is also determined by an equation. Example: the user sets `total_cost = $42B`, but the equation `total_cost = Σ(capex + opex)` determines it. Two values for the same parameter.

### Mechanism 4: Feedback Solving

Feedback loops are collapsed into super-nodes and solved iteratively. The solver uses:
- **Fixed-point iteration**: repeatedly evaluate the loop's equations until values stop changing.
- **Anderson acceleration**: speeds up convergence by extrapolating from previous iterates.
- **Convergence monitoring**: reports convergence status and diagnostics.

If a loop fails to converge after `max_iter` (default 20), the solver raises an error and reports the loop to the user.

---

## 7. What the User Sees

From the user's perspective, changing one parameter is simple. Behind the scenes, the PRG does all the work. The user sees:

**In the dashboard**: a slider for `carbon_price`. When they drag it:

- The slider turns **yellow** while the PRG propagates.
- The dashboard shows a **live preview** of the ripple effects.
- If a conflict is detected, a **popup** appears with suggested corrections.
- Once the user accepts a correction, the slider turns **green** and the propagation completes.

**In the propagation view**: a **graph visualisation** showing which parameters changed, with edges colour-coded by magnitude.

**In the consistency report**: a **summary** of what changed and why, with links to the underlying equations.

**In the API**: a single `POST /v1/prg/propagate` call returns the full set of updated parameters and the propagation path.

---

## 8. What Happens Without the PRG

To make the value concrete, here's what would happen if ALEA didn't have the PRG:

| Change | Without PRG | With PRG |
|---|---|---|
| User sets carbon_price = 150 | Model silently ignores coal_retirement = 2050, or fails to solve | Model detects conflict, suggests correction |
| User sets renewable_target = 100% | Model returns physically infeasible solution (no reserve margin) | Model flags inconsistency with reserve margin, suggests adjustment |
| User sets both carbon_price and coal_retirement | Model over-determined, either crashes or returns garbage | Model detects over-determination, offers correction options |
| Feedback between price and demand | Model ignores feedback, returns wrong equilibrium | Model iterates to convergence |
| Derived parameters (LCOE, DSCR, SAIDI) | Model does not compute them | Model computes them automatically |
| Cross-validation (carbon price vs. coal retirement) | Model does not check | Model flags and corrects |

Without the PRG, ALEA is a **parameter playground** that produces numbers. With the PRG, ALEA is a **coherent system** that produces scenarios.

---

## 9. The Hard Part: Feedback Loops

The trickiest part of the PRG is feedback loops. Let me explain what they are and why they're hard.

### What Is a Feedback Loop?

A feedback loop is a cycle in the graph: A affects B, B affects C, ..., and Z affects A. The PRG contains about 15 such loops.

**Example 1: Price-Demand Feedback**

```
carbon_price → coal_capacity → electricity_price → demand → emissions → carbon_revenue → subsidies → electricity_price
```

Higher carbon price → less coal → higher electricity price → lower demand → lower emissions → lower carbon revenue → higher subsidies → higher electricity price...

**Example 2: VRE Investment Feedback**

```
renewable_capacity → VRE_penetration → capture_price → renewable_investment → renewable_capacity
```

More renewable capacity → higher VRE penetration → lower capture price → lower renewable investment → less renewable capacity...

### Why Are They Hard?

If the PRG just did a topological sort on the raw graph, it would fail because cycles have no topological order. There is no "first" parameter to evaluate.

The solution is to:

1. **Detect cycles** using Tarjan's strongly connected components algorithm.
2. **Collapse each cycle** into a single super-node.
3. **Topologically sort** the graph of super-nodes.
4. **Iterate** each super-node until its values converge.
5. **Expand** the super-nodes back into individual parameters.

### Convergence

Iteration converges if the equations are **contractions** — that is, each iteration brings the values closer to the fixed point. In practice, most feedback loops in ALEA converge within 5–15 iterations because the equations are well-behaved (elasticities are small, learning rates are bounded, etc.).

When convergence fails, the PRG:

1. Reports the loop that failed to converge.
2. Reports the last residual.
3. Suggests either adjusting the loop's parameters or relaxing the tolerance.
4. Offers to run the loop with more iterations or a different acceleration method.

---

## 10. An Analogy: The PRG as a Mechanical Linkage

To understand the PRG intuitively, think of it as a **mechanical linkage** — a system of gears, cams, and levers connected by rods.

- Each **parameter** is a **joint** in the linkage.
- Each **equation** is a **rod** connecting two joints.
- Each **relationship** is a **direction of force**.
- Each **role** determines whether the joint is **driven** (exogenous), **free** (endogenous), or **constrained** (derived).

When you turn one joint (change a parameter), the mechanical linkage transmits the motion through all connected rods. Some joints move a lot; some move a little. Some move in the opposite direction. The whole system reconfigures itself to a new mechanical equilibrium.

The PRG is the **design of that linkage**. It ensures that every joint moves in a way that is **mechanically consistent** — no joints move in ways that violate the physical constraints of the rods.

This is why changing a carbon price ripples through coal capacity, emissions, carbon revenue, subsidies, electricity price, demand, jobs, health, and total cost. Each of those is a joint in the linkage, and each is connected to the carbon price through a chain of equations.

---

## 11. Summary: The PRG in Ten Sentences

1. The PRG is a directed graph of 784 parameters connected by ~2,500 typed relationships and governed by 20 systems of equations with ~120,000 constraints.
2. Each parameter has a role (exogenous, endogenous, derived, free), a type, a unit, and a range.
3. Each relationship has a type (functional, equality, inequality, feedback), a strength (hard, soft, informational), and an equation.
4. When a user changes a parameter, the PRG checks consistency, propagates the change to all dependents, detects conflicts, and suggests corrections.
5. Propagation works by finding all descendants, topologically sorting them, and evaluating each in turn.
6. Feedback loops are collapsed into super-nodes and solved iteratively until convergence.
7. Over-determined and under-determined systems are detected and reported with suggested corrections.
8. Once consistent, the PRG translates the parameter set into PyPSA network attributes and Linopy constraints.
9. The optimiser then solves the network and returns results.
10. The PRG makes ALEA a coherent system rather than a parameter playground — the difference between a model and a platform.

---

## 12. The Limits of the PRG

For honesty, here's what the PRG does **not** do:

- It does **not** solve PDEs. (See the earlier discussion on PDE support.)
- It does **not** guarantee convergence for arbitrary user inputs. Badly-specified feedback loops may not converge, and the PRG will report this.
- It does **not** replace human judgment. It suggests corrections, but the user decides.
- It does **not** validate every possible cross-category relationship. The ~2,500 edges cover the known relationships, but new ones may be discovered.

These limits are documented, tested, and reported. The PRG is powerful, but it is not a panacea.

---

If you want, I can walk through another example — say, changing the `reserve_margin` or the `renewable_target` — to show how the PRG handles different types of conflicts and ripples. Or I can go deeper into any specific mechanism: the topological sort, the feedback solver, the conflict detector, or the translation layer.