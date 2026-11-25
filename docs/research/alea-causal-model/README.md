# From dependency graph to causal model: what the equations are, and what T2 must add

2026-11-25. Classification by `classify.py` (reproducible, output in `equation-classes.csv`). T2 reviewed as written in `docs/plans/15-completion.md`.

## 1. What the 841 equations are

Structure is computed from the equation text and is sound. Claim is what the equation asserts, and syntax cannot decide it for the arithmetic ones.

| Structure | Count | Reading |
|---|---|---|
| Arithmetic (sums, products, ratios of declared quantities) | 588 | Claim not assigned by the script; see the audit below |
| Alias (`a = b`) | 95 | Naming. No claim |
| Inequality (`<=`, `>=`) | 74 | Constraint, not a determination. No direction |
| Lookup table (`choose`) | 40 | Stated values selected by a category. Assumption |
| Functional form (exp, log, power) | 44 | Hand-labelled below |

The 44 functional-form equations, labelled by hand (every one received exactly one label, asserted in the script):

| Claim | Count | Examples |
|---|---|---|
| Definition (finance maths, unit conversions) | 21 | capital recovery factors, annuities, half-lives |
| Projection assumption (an exogenous trajectory) | 12 | escalation, growth factors, indexation |
| Empirical relation | 9 | learning curves, degradation, Weibull hazard, climate sensitivity |
| Behavioural | 1 | `equilibrium_demand` (price elasticity) |
| Physical law | 1 | `line_surge_impedance_loading` |

**Audit of the 588 arithmetic equations.** I read 40 chosen at random (seed 11) and labelled each by hand. This is a sample of 40, so each share carries a wide interval.

| My reading | of 40 | Example |
|---|---|---|
| Accounting or definition | about 24 | `residential_demand_twh = residential_demand_share * demand_twh` |
| Assumed effect size (`flag * base * share`) | about 10 | `grm_delay_avoided = grievance_redress_mechanism * delay_cost * share` |
| Scenario multiplier on a weather or load quantity | 2 | `wind_effective_capacity_factor = cf * wind_speed_multiplier` |
| Physical or engineering law | 2 | `rocof = f0 * largest_loss / (2 * inertia)` (the swing equation) |
| Behavioural | 1 | `generator_bid_price = marginal_cost * (1 + strategic_bidding ...)` |

A first attempt at classifying by keywords ("rate", "premium", "ratio") was wrong in most cases I audited: it labelled capital recovery factors and price bands as behavioural. I discarded it. Syntax cannot tell a mechanism from an identity; an author has to say.

## 2. What this means

1. **The graph is an assumptions-and-accounting layer around the optimiser.** Behavioural mechanisms are a handful out of 841: the demand elasticity, the capture-price cannibalisation, and perhaps a few more. Physical laws in the graph are fewer still. The physics of dispatch and power flow lives in PyPSA, not here.
2. **The only feedback loops are the causal heart.** `ParameterGraph.feedback_loops()` returns two loops, five equations: `loop_1` (capture price, VRE build, VRE share) and `loop_2` (equilibrium demand, regulated tariff). Those are the behavioural mechanisms. Cycle handling in T2 therefore covers exactly the part that matters most.
3. **The causal claim ALEA can make is bounded.** "What changes in the plan if this assumption is X" is answered by the optimiser, for the 81 of 1,095 settable parameters that reach it. For the rest, a propagated change is arithmetic in a graph.
4. **301 of 841 equations have no `reference`** (231 arithmetic, 37 inequalities, 15 functional-form, 18 aliases). Any of these that make an empirical claim has no stated evidence.

## 3. Review of T2 against the eight requirements

| # | Requirement | T2 as written | Verdict and change |
|---|---|---|---|
| 1 | Intervention semantics | `intervene(values, do=...)` cuts the determining equation, pins, recomputes descendants, pure function, reports `cut` | **Good.** Add three cases: (a) an equation that determines more than one variable (cutting it removes the others' source, so refuse or split); (b) a pinned name that is an alias (pin the canonical name; 95 aliases); (c) report any inequality the pinned value violates (74 constraints) |
| 2 | Classify equations by claim | Not used | **Gap.** Add a `claim` field to `Equation` (definition, identity, physical, empirical, behavioural, assumption) seeded from `equation-classes.csv`, defaulting to `unreviewed`. The result then states which claim classes an effect travelled through |
| 3 | Direction of causation | Takes direction from `determined_variables` | **Gap.** 74 inequalities have none, and nothing audits that an equation points the right way (an inverted shipped equation was found earlier). Add a test that every equation has exactly one determined variable or is an inequality, and a `direction_source` note for behavioural ones |
| 4 | Cycles | SCC re-solved without the pinned variable; tests on `loop_1`, `loop_2` | **Good, incomplete.** Also test the unpinned loop against its fixed point and state existence and uniqueness conditions (for `loop_2`, the elasticity and tariff rule decide whether it converges) |
| 5 | Solver connection | Stops at the graph | **Gap.** Return `reaches_solver` for each pinned name and each changed descendant, and warn "moved in the graph, not in the plan" for the other 92.6% |
| 6 | Identification | Docs state `intervene` does not identify a real-world effect | **Good.** Strengthen: each result lists the references behind the edges used and flags those with none (301) |
| 7 | Test against interventions | Identity property test: pinning a node to its own derived value is a no-op | **Consistency, not validity.** Keep it, and add the defining causal property: `do(X)` leaves every non-descendant of X unchanged. Out-of-sample tests against real past interventions (a tariff change, a plant outage) are a separate task |
| 8 | Uncertainty on mechanisms | Not addressed | **Out of T2.** Ranges cover parameters, not functional form. A later task |

## 4. Proposed additions

1. **T2a (inside T2):** the three cases in row 1, `reaches_solver` in the result, and the non-descendant invariance test.
2. **T2b:** the `claim` field on `Equation`, loaded from the CSV, with a gate that no equation is assigned a claim class it contradicts (for example a `definition` containing an elasticity parameter).
3. **T9 (new):** review the 588 arithmetic equations by hand into claim classes, starting with the loops and every equation that carries a `*_share`, `*_factor` or `*_uplift` parameter. This needs the author of each equation, not a script.
4. **T10 (new):** one out-of-sample intervention check on a Kenyan event, so "validated" means something for at least one behavioural edge.

## 5. What would show this reading is wrong

- If a hand audit of all 588 arithmetic equations finds many more behavioural mechanisms than the 1 in 40 sampled, the "handful" claim fails. The sample is small.
- If the solver, not the graph, turns out to carry the behavioural response (price-responsive demand inside PyPSA), then the graph's causal content matters less than I say.
- If `determined_variables` is wrong for some equations, rows 1 and 3 are understated.
