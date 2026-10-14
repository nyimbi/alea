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
| Incremental propagation | `src/alea/prg/graph.py` | `propagate_incremental`: the closure of what changed, 9x a full walk, skipping a feedback loop nothing reached |
| Uncertainty | `src/alea/prg/uncertainty.py` | The declared stochastic inputs, the closure over `affects`, and the reach into derived parameters |
| Units | `src/alea/prg/units.py` | The dimensional check the spec asks for: each equation's two sides against a Pint registry of the graph's vocabulary |
| Conflict detection | `src/alea/prg/conflicts.py` | The four kinds (direct, over-determined, under-determined, loop, out-of-range), ranked, with corrections |
| Translation | `src/alea/prg/translate.py` | Three declared routes from a PRG parameter to a what-if knob, and the register of the other fifty |
| API | `src/alea/api/routes/prg.py` | Four routes: `GET /prg/summary`, `GET /prg/equations`, `POST /prg/conflicts`, `POST /prg/sensitivity` |
| The graph | `config/prg.yaml` | 84 parameters, 37 equations, 84 edges, 1 feedback loop |

Commands: `alea prg summary|equations|check|propagate|conflicts|sensitivity|units|audit`,
and `alea expr render|eval|diff|simplify|solve`.

The two reads are public and the two computations are analyst-tier. Every
response carries its registers: `/prg/summary` reports how many equations the
dimensional check could not decide, and `/prg/conflicts` reports what it
examined. A client that renders a green count from a check whose coverage
shrank is reporting something the service never claimed, and the only place to
prevent that is in the payload.

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

## What the dimensional check found

`units.py` decides every equation: 30 of 37 are dimensionally consistent, 7
are not, and 0 are undecidable. The seven are not seven of one kind, and the
fix differs by kind — which is why they are listed rather than counted:

| Equation | The mismatch | What it is |
|---|---|---|
| `crf_definition` | `1 + discount_rate`, a `1/year` rate | A rate added to the dimensionless `1`. Either `discount_rate` is a fraction and its unit is wrong, or the equation is. |
| `energy_demand` | `(1 + demand_growth) ** horizon_years` | The same, for the growth rate. |
| `debt_service_definition` | `(1 + cost_of_debt) ** asset_life` | The same, for the cost of debt. |
| `rocof_definition` | `MW / MW.s` gives `1/[time]`, the node says `Hz/s` = `1/[time]²` | The standard formula is `ΔP·f₀/(2·E)`; the nominal frequency (50 Hz) is missing. |
| `emissions_definition` | `TWh · t/MWh = Mt`, the node says `MtCO2/year` | The left side is an annual quantity declared without its per-year divisor. |
| `hydrogen_water_definition` | `kt/year · m3/kg = m3/year`, the node says `m3` | The same annual-quantity gap. |
| `premature_deaths_definition` | `people · 1/year · kt/year · 1/kt = 1/year²`, the node says `deaths/year` | The same, and it compounds two per-year factors. |

The three rate cases are one question asked three times: is a `1/year` rate a
*frequency* (per-year, so it cannot be added to 1) or a *fraction per year*
(dimensionless, so it can)? The equations use it as a fraction. The units say
frequency. One of the two is wrong in each equation, and the check cannot say
which — that is a modelling decision, not a dimensional one. The other four are
the annual-quantity gap: the graph writes a yearly total in a unit that names
the year, then divides it by something else that also names a year, and the
year cancels to a dimension the node does not claim.

None of the seven is reported as a *failure* by any other check, because the
graph is internally consistent either way — which is exactly the class of error
a dimensional check exists to catch, and the reason the check was worth adding
after `views.py` said the graph did not make it.

## Not built

- **The engine is barely driven by the graph.** `translate.py` declares the
  routes, and there are **three**: `carbon_price_usd_per_tco2` and
  `demand_growth` map one-for-one, and `fuel_price_usd_per_mwh` maps to the
  engine's `gas_price_multiplier` as a ratio over the network's base gas cost.
  The other **50 of 53** settable parameters reach no what-if knob. They are
  named by `translate.untranslated()` and counted in `alea prg summary`. This
  is the register, not an omission: the graph states what the physics and the
  accounts require, and the engine states what a PyPSA network can be
  perturbed by, and the two sets were built for different purposes. The
  register runs both ways: `engine_fields_unreached()` names the **6** engine
  knobs no PRG parameter reaches (`coal_eaf`, `renewable_multiplier`,
  `battery_cost_multiplier`, `ssp_pathway`, `drought_multiplier`,
  `hydrogen_export_twh_per_year`). A scenario pulling one of those cannot be
  audited against the graph, because the graph does not know the quantity
  moved.
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
- **Every parameter is `float`, and `type` gates only that.** The spec's §20
  asks for type *inference* from equations. There is nothing to infer: all 84
  nodes are float, all appear in arithmetic, and none is used as an index — so
  an inference engine here would be a gate that cannot fail. What was real is
  that `type` was declared on all 84 nodes, enum-validated, exported, and read
  by **nothing**: a node declared `timeseries` with a scalar `default` was
  accepted, propagated as a float, and reported as a quantity. The node now
  refuses a non-scalar type carrying a scalar `default` or `range`, because
  the model has no field for an array. `float` and `int` are the types it can
  honestly carry; the other four wait on a field that holds the array.
- **Not the 784-parameter graph.** 84 of them, over the systems with the
  clearest physical or accounting statement.
- **No UI.** Packaging rather than capability, and the last door left shut. The
  CLI and the API both reach every register; a UI would render them.

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

**A canary run with `-k` can miss the test that guards the branch.** I removed
the symbolic-exponent branch from `units.py`, ran `pytest -k "decidable or
flagged"`, saw two passes and nearly recorded "the branch is not load-bearing".
The guarding test is named `test_the_unit_checker_decides_the_graph_without_giving_up`
— `-k decidable` does not match `decides`, so it never ran, and the two tests
that did pass were testing something else. Re-run by exact node id
(`pytest path::test_name`), or assert the count of selected tests equals the
count you meant to select. A `-k` filter that selects zero of the tests you
believe are guarding a branch is the same failure as a canary whose patch does
not apply: the instrument, not the subject, is what lied.

**A dimension declared as a base dimension manufactures its own findings.**
`DALY` was first declared `[health]`, and `dalys = deaths x years_of_life_lost`
then read as `[health]` vs `[count]` — a mismatch in the registry, not in the
graph. A DALY is a person-year. Declaring it `person * year` cleared the
finding, and the count fell from 8 to 7. Before reporting a dimensional
finding, check the registry's definition of the unit is not the thing that is
wrong: the graph's units are a vocabulary, and a wrong entry in the vocabulary
accuses every equation that uses it.

**A gate that reads only `properties` is blind to `dict[str, float]`.**
`test_values_carry_basis` walks each response schema for numeric fields and
fails on any bare quantity. It read `schema["properties"]` and never
`additionalProperties`, so a mapping of numbers — a derivative table, a count
per system — was invisible to the one check whose whole job is to find bare
numbers in responses. `SensitivityOut.derivatives` and `PrgSummaryOut.systems`
both shipped through it. The general shape: a walker enumerates the *writings*
of a thing it recognises and silently omits the others, which is the same
defect as the internal-link checker that matched only `href="/…"` and passed
fifteen relative links. When a gate enumerates a schema, enumerate every way
the schema can express the thing — `properties`, `additionalProperties`,
`items`, `anyOf`, `$ref` — and canary each one.

**Exempting a field *name* globally exempts it everywhere.** The same gate had
`value` and `uncertainty` in its global `NON_QUANTITY_FIELDS`, because they are
the members of a `ValueOut` and a `ProvenanceOut`. That also exempted a bare
`value: float` on any response model that is not a wrapper — the exact
regression the contract exists to catch — and `SensitivityOut.value` was
sitting in that hole. The exemption is now scoped to the wrapper that gives the
name its meaning (`WRAPPER_MEMBERS`), and a bare `uncertainty` planted on
`EquationOut` fails the gate. An exemption is a claim about *where* a name is
acceptable, and a set of names cannot express "where".

**An exemption that follows a `$ref` is applied to the wrong model.**
`ConflictOut` exempts `residual` and `tolerance`; `ConflictReportOut` holds a
`list[ConflictOut]`. The walker followed the ref and flattened the inner
model's fields onto the outer one, so every exempt field was re-reported as an
offender on the model that merely contains it. The walker no longer follows
refs: it walks the transitive closure one component at a time, and each model
is judged against its own exemptions. A canary that plants a bare float on a
deeply nested model (`PrgSummaryOut → UnitReportOut → EquationCheckOut`) still
fails, so the coverage did not shrink with the flattening.

**A closure over the declared edge set is not the closure over `affects`.**
The specification's incremental propagator marks dirty with
`networkx.descendants` over the declared graph. That is a different relation:
it disagrees with the `affects` closure on 27 of the graph's 53 settable
parameters, missing members in *both* directions — the declared edges omit a
loop's feedback, and they carry relationships the equations do not fix. The
`affects` closure is the one that matches what actually moves, and it was
checked against the arithmetic: every settable parameter perturbed in turn, and
every value that moved was inside its closure (43 of 50 perturbations moved
something, so the check was not vacuous).

**"Determining which are unaffected requires the same topological walk" was
false, and unmeasured.** `propagate`'s docstring used it to justify recomputing
the whole graph on every call. The closure is 10 microseconds against a 4.2
millisecond full propagation — four hundred times cheaper — so
`propagate_incremental` skips what did not move and runs 9x faster on this
graph. A performance claim in a docstring is a claim like any other: it needs a
measurement, and the measurement here contradicted it.

**An iterative solver's warm start is not bit-identical to a cold one.** The
incremental result agrees with a full propagation to the loop solver's
tolerance (measured worst case 1.1e-8 against a declared 1e-8), not exactly.
A test demanding exact equality would be asserting something false about a
fixed-point solver; the honest contract is agreement at the tolerance, and the
test says so rather than loosening a number until it passes.
