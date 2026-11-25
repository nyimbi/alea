# A dependency graph is not a causal model

ALEA's Parameter Relationship Graph (PRG) is a dependency graph. This page says what that means, what a causal model adds, and where ALEA sits between the two today. The plan for closing the gap is `docs/plans/16-causal-model.md`.

## The short version

A dependency graph answers: **what must I know before I can compute this?**

A causal model answers: **what would happen to this if I changed that, and the world responded the way it really responds?**

The first is a fact about how a calculation is organised. The second is a claim about how the world is organised. The same picture (nodes and arrows) can stand for either, and that is why the two get confused.

## What each one is

| | Dependency graph | Causal model |
|---|---|---|
| An arrow `A -> B` means | B's formula reads A | Setting A by an outside hand changes B, and B responds by a mechanism that stays the same whatever else we do |
| The unit of meaning | The graph as a whole (a topological order) | Each equation on its own (a mechanism) |
| Where its truth comes from | Parsing the formulas | Evidence about the world |
| Can an arrow be wrong? | Only if the parser is wrong | Yes, in many ways: direction, existence, size, confounding, missing arrows |
| Can an equation be rewritten algebraically? | Freely: `y = 2x` and `x = y / 2` are the same dependency | No: they assert different mechanisms. The first says x drives y |
| Handles a change by | Recomputing everything downstream (`propagate`) | Replacing one mechanism and recomputing what that mechanism reaches (`do`) |
| Supports | Impact analysis, evaluation order, unit and range checks | Intervention questions, and with more structure, counterfactuals |
| Fails by | Giving an arithmetic answer to a question about the world | Being wrong about the world |

## The test that separates them

Take an equation `Y = f(X)` and ask: **if I change how X is set, does this equation for Y still hold?**

- `residential_demand_twh = residential_demand_share * demand_twh` is an accounting identity. It holds by how the terms are defined. It is a dependency, and it is not a mechanism: nobody pushes on `residential_demand_twh` through this equation.
- `rocof = f0 * largest_loss / (2 * inertia)` is the swing equation. It holds when you change the loss, the inertia, or the policy that led to either. That invariance is what makes it a mechanism.
- `equilibrium_demand` with a price elasticity claims that consumers respond to price in a stable way. It holds only if that response does not change when the tariff rule changes. That is an empirical claim, and it can be false.

An equation that fails the test can still be a perfectly good dependency. It just cannot carry a causal claim.

## Three levels of question

Pearl's ladder is the usual way to say what a model can answer.

1. **Association.** If I observe X, what do I expect for Y? A dependency graph with default values can be read this way. It is not what ALEA is for.
2. **Intervention.** If I set X to x, what happens to Y? Needs mechanisms (equations that survive the change) and a way to cut the equation that would normally have set X. Written `do(X = x)`.
3. **Counterfactual.** Given what actually happened in this case, what would have happened had X been x? Needs, in addition, the part of each variable that the equations leave unexplained, so it can be held fixed while X changes.

Each level needs strictly more than the one below it. ALEA is at the bottom of level 2 for some questions, and does not reach level 3.

## Where ALEA is today

Measured on the 841 equations and the shipped graph, 2026-11-25:

| Property | Status |
|---|---|
| Edges computed from the formula text | Yes, sound |
| Refuses to silently discard a supplied derived value | Yes (T1). A bare override of a computed quantity is an error |
| An explicit intervention operator | Yes (T2). `intervene` removes the producing equation, pins the value, recomputes descendants, reports what it cut |
| Cycles | Two feedback loops (five equations). `intervene` breaks a loop at the pinned node |
| Equations classified by what they claim | Partly. Structure is classified for all 841. The claim (definition, physical law, empirical, behavioural, assumption) is hand-labelled for 44 functional forms and a sample of 40 of the 588 arithmetic ones. No `claim` field exists on an equation yet |
| Equations with a stated source | 540 of 841. 301 have no `reference` |
| Mechanisms estimated from data | None. The behavioural equations are documented relationships, not fits |
| Uncertainty on the mechanism itself | None. Ranges cover parameters, not functional form |
| Exogenous noise terms | None, so no counterfactuals |
| Reach to the optimiser | 9 of 1,095 settable parameters can move the plan. For the other 99.2 percent a change is arithmetic in the graph |
| Validated against a real intervention | No |

So ALEA has the **grammar** of a causal model (a pure intervention operator, direction taken from the equation, loop handling) and almost none of the **content** (mechanisms known to be autonomous, evidence for the behavioural ones, any check against what happened when someone actually intervened).

## What `intervene` does and does not tell you

`intervene(values, do={"x": v})` answers: *within this model's equations, if x were v, what would everything downstream be?* That is a correct computation of a consequence of the stated equations.

It does not tell you what would happen in Kenya if the policy behind x changed, because that needs the equations to be right, complete, and invariant to the change. For an accounting identity that is usually true. For a behavioural edge it is a hypothesis.

For that reason the README keeps the phrase "dependency graph", and the plan sets explicit criteria for when "causal model" may be used, and for which part of the graph.

## Why bother

Planners ask intervention questions: what if the tariff rises, what if a plant is delayed, what if the carbon price doubles. A dependency graph answers them mechanically and with no warning when the answer is only as good as an unvalidated assumption. A causal model answers them with the same arithmetic and also says, for each answer, which mechanisms it travelled through and what evidence stands behind each. The second is the more useful product for a regulator, and the more honest one.

## Further reading

Pearl, *Causality* (2nd ed., 2009), chapters 1, 3 and 7 for structural models, `do`, and counterfactuals. Peters, Janzing and Schölkopf, *Elements of Causal Inference* (2017) for autonomy and invariance. Hernán and Robins, *Causal Inference: What If* (2020) for estimation from data. These are textbooks and are not archived under `docs/sources/`. No claim in this page depends on a theorem from them beyond the definitions; any plan task that does will archive the source first.
