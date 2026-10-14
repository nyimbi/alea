# PRG: what is built, and what is still specified

`alea_prg.md`, `params-prg1.md` and `how_prg_works.md` are **design documents**.
They describe the target system, including parameters and behaviours that do not
exist yet. `how_prg_works.md` §5, for instance, traces a change to
`coal_retirement_schedule` and `renewable_target` and shows the engine proposing
corrections A/B/C — none of which is implemented. Read them as intent.

This file is the register of what is actually there. It is deliberately short:
the code and `config/prg.yaml` are the authority, and this says where to look.

## Built

| Piece | Where | What it does |
|---|---|---|
| Symbolic DSL | `src/alea/prg/dsl.py` | Create, render (LaTeX / Unicode / MathML / source), evaluate (scalar and array), differentiate, simplify, solve numerically |
| Models | `src/alea/prg/views.py` | `ParameterNode`, `RelationshipEdge`, `Equation`, with the cross-field rules that make an incoherent declaration a construction error |
| Graph | `src/alea/prg/graph.py` | Topological order in two phases, propagation, consistency, structure checks, `affects`/`constrains`/`depends_on`/`edges_from`/`edges_into` |
| Feedback | `src/alea/prg/feedback.py` | Tarjan SCC detection, Gauss–Seidel with damping, convergence on the residual `consistency` checks, a divergence-vs-oscillation diagnostic when it fails |
| Library | `src/alea/prg/library.py` | The 16 systems, the spec→system mapping, and the coverage register |
| Service | `src/alea/prg/service.py` | `graph_summary`, `check_scenario`, `propagate_change`, `describe` |
| Result audit | `src/alea/prg/audit.py` | Audit a *solved* what-if result against the graph's identities |
| Sensitivity | `src/alea/prg/sensitivity.py` | Exact forward-mode derivatives over the topological order; the implicit function theorem for loop variables; elasticity |
| Uncertainty | `src/alea/prg/uncertainty.py` | The declared stochastic inputs, the closure over `affects`, and the reach into derived parameters |
| Conflict detection | `src/alea/prg/conflicts.py` | The four kinds (direct, over-determined, under-determined, loop, out-of-range), ranked, with corrections |
| Translation | `src/alea/prg/translate.py` | Three declared routes from a PRG parameter to a what-if knob, and the register of the other fifty |
| The graph | `config/prg.yaml` | 84 parameters, 37 equations, 84 edges, 1 feedback loop |

Commands: `alea prg summary|equations|check|propagate|conflicts|sensitivity|audit`,
and `alea expr render|eval|diff|simplify|solve`.

## The four conflict kinds

`conflicts.py` separates what `consistency` reports as one thing, because the
fixes and the owners differ:

| Kind | What it is | The fix |
|---|---|---|
| `direct` | One set value contradicts an equation that fixes it | Change that number |
| `over_determined` | A value was set for a parameter the graph computes | Decide which of the two is authoritative |
| `under_determined` | A needed parameter that nothing supplies | Supply it |
| `loop` | A feedback system with no fixed point at these inputs | Widen a range or correct the formulation |
| `out_of_range` | The arithmetic produced a value nobody would sign | Check the inputs that produced it |

Corrections rank by *relative* move, not raw delta: a 0.2 move in an emission
factor and an 82 USD/t move in a carbon price can be the same real-world size,
and ranking on the raw number ranks the units. A correction for a direct
conflict chains `dF/dx` through the gradient table, so a lever *upstream* of
the violating equation is offered — the carbon price moves the DSCR through the
tariff and the cash flow, and a list built from the equation's own parameters
would offer only the regulator's floor for a conflict the carbon price caused.

## Not built

- **The engine is barely driven by the graph.** `translate.py` declares the
  routes, and there are **three**: `carbon_price_usd_per_tco2` and
  `demand_growth` map one-for-one, and `fuel_price_usd_per_mwh` maps to the
  engine's `gas_price_multiplier` as a ratio over the network's base gas cost.
  The other **50 of 53** settable parameters reach no what-if knob. They are
  named by `translate.untranslated()` and counted in `alea prg summary`. This
  is the register, not an omission: the graph states what the physics and the
  accounts require, and the engine states what a PyPSA network can be
  perturbed by, and the two sets were built for different purposes.
- **The energy balance is single-region.** One demand, one generation total. A
  PyPSA network balances per bus and per hour and the solved result carries no
  nodal frame, so the audit cannot assert the balance against it. The audit
  reports what it did not check rather than a pass it did not earn.
- **Uncertainty is registered, not propagated.** `uncertainty.py` reads the 13
  settable parameters declared `stochastic` and the one `Relationship.STOCHASTIC`
  edge, and computes the transitive closure over `affects`: 13 inputs reach 22
  derived parameters, 8 of which are stochastic by their own relation. What it
  does *not* do is sample. The spec asks for an edge *type* and says a scenario's
  inputs are uncertain; it names no distribution, no correlation, no interval.
  Inventing one would put a fabricated confidence band on a report, which is
  worse than the silence it replaces — a reader cannot tell a modelled interval
  from a guessed one. A sensitivity is a derivative at a point, and the register
  says so rather than implying otherwise.
- **Emissions use one fleet-wide factor.** The engine sums per-carrier
  intensities. `audit.fleet_intensity_gap` measures the difference instead of
  pretending they agree.
- **Not the 784-parameter graph.** 84 of them, over the systems with the
  clearest physical or accounting statement.
- **No API or UI.** Both are packaging rather than capability; the CLI is the
  only door, and every command is exercised through it in `tests/ci`.

## Two things about the graph that are easy to get wrong

**`range` on a node is the admissible set, not the solver's bracket.** They
differ for a ratio: a debt service coverage of 30 is computable and outside any
range a reviewer would sign off. A bracket miss widens until the root is found
and the excursion is reported as a violation (`<name>_out_of_range`); it does
not raise. An equation with no root anywhere still raises.

**A loop converges on the residual, not on its iterates.** With damping the
residual is the step divided by the damping factor, so a loop that stops on its
iterates can sit outside the tolerance `consistency` checks it against — and the
audit then reports an equation the solver called solved as violated.

**`affects` is "moves the number"; `constrains` is "gates the scenario".** They
are different relations and are kept apart on purpose. `affects` reads the
equations that *fix* a value — including the iterative ones, whose fixed point
is a consequence of its inputs — and it deliberately ignores inequalities,
because moving `dscr_min` changes no value at all. A regulator's lever is a
constraint, so it appears in `constrains`, not in `affects`. The declared
relationship direction is on `edges_from`/`edges_into`.

**A correction ranking on the raw delta ranks the units.** A 0.2 move in an
emission factor and an 82 USD/t move in a carbon price can be the same
real-world size; ordering by the absolute number puts whichever parameter
carries the smaller unit first, which is the same mistake as ranking a
sensitivity by derivative instead of by elasticity. `Correction.rank_key()`
compares relative moves, and a parameter sitting at zero — where a fraction is
undefined — sorts last rather than first.

**A correction for an equation must chain `dF/dx`, not read the equation's own
parameters.** `dscr_requirement` is `project_gearing_dscr >= dscr_min`; neither
name is an input, and the carbon price reaches the ratio through the tariff and
the cash flow. A correction list built from the equation's names offers only
the regulator's floor for a conflict the carbon price caused. The chain rule
through `sensitivity.gradients` is what makes the lever the right one.

**`order()` is the determiner set, not "everything derived".** A loop variable
is derived — nothing may set it — but it has no place in a topological order, so
`order()` omits it. A reachability closure filtered on `order()` therefore
reports a path that crossed a feedback loop while omitting the loop's own
members, which is the one place the uncertainty most obviously lands. Use
`not graph.is_settable(name)` for "derived".

**A ratio translation needs the *recorded* base, not the current value.**
`fuel_price_usd_per_mwh` is absolute; the engine's `gas_price_multiplier` is a
factor over each gas unit's base marginal cost. Dividing by the current cost
makes the translation depend on how many times it has already run — the same
compounding defect `apply.py`'s snapshot exists to prevent — so `translate.py`
reads that snapshot, and records it if the network has none.
