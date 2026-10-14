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
| Result audit | `src/alea/prg/audit.py` | Audit a *solved* what-if result against the graph's identities. `checked` is what the result's inputs *reach*, and `failure` carries a propagation that could not run — two fields whose first versions both lied in the direction that reads as a pass |
| Sensitivity | `src/alea/prg/sensitivity.py` | Exact forward-mode derivatives over the topological order; the implicit function theorem for loop variables; elasticity |
| Incremental propagation | `src/alea/prg/graph.py` | `propagate_incremental`: the closure of what changed, 9x a full walk, skipping a feedback loop nothing reached |
| Uncertainty | `src/alea/prg/uncertainty.py` | The declared stochastic inputs, the closure over `affects`, and the reach into derived parameters |
| Units | `src/alea/prg/units.py` | The dimensional check the spec asks for: each equation's two sides against a Pint registry of the graph's vocabulary |
| Conflict detection | `src/alea/prg/conflicts.py` | The four kinds (direct, over-determined, under-determined, loop, out-of-range), ranked, with corrections |
| Cross-validation | `src/alea/prg/crossval.py` | §25's multi-parameter rules: a parsed condition, three severities, and the register of rules that could not be evaluated |
| Edge strength | `src/alea/prg/graph.py` | The declared `hard`/`soft`/`informational` tier, read by `consistency`, `conflicts`, the audit and the CLI gate |
| Translation | `src/alea/prg/translate.py` | Three declared routes from a PRG parameter to a what-if knob, the register of the other fifty, and the three refusals that name a key reaching no knob — a typo, a derived value, an uncarried parameter |
| PRG-driven solve | `src/alea/whatif/service.py` | `WhatIfEngine.solve_from_prg` + `PrgSolve`: the production caller the translation layer had none of — translate, solve, audit, with the dropped parameters carried on the payload |
| Constraints | `src/alea/prg/constraints.py` | The equation→constraint half of Part X: the two inequalities that bind a linopy solve, the four that are post-solve checks instead, and `bound_parameter_names` — the four scalars those inequalities read, which reach the optimiser with no engine knob |
| Constrained solve | `src/alea/whatif/service.py` | `solve_from_prg(constrain=True)`, the default: the graph's inequalities are added through PyPSA's `extra_functionality` hook, the constraint record enters the cache key, and an infeasible scenario raises `SolveError` instead of caching a cost |
| API | `src/alea/api/routes/prg.py` | Five routes: `GET /prg/summary`, `GET /prg/equations`, `POST /prg/conflicts`, `POST /prg/sensitivity`, `POST /prg/cross-validation` |
| The graph | `config/prg.yaml` | 84 parameters, 37 equations, 84 edges, 1 feedback loop |

Commands: `alea prg summary|equations|check|propagate|conflicts|sensitivity|units|constraints|audit`,
`alea whatif scenario`, and `alea expr render|eval|diff|simplify|solve`.

The two reads are public and the three computations are analyst-tier. Every
response carries its registers: `/prg/summary` reports how many equations the
dimensional check could not decide, `/prg/conflicts` reports what it examined,
and `/prg/cross-validation` reports the rules that could not be evaluated. A
client that renders a green count from a check whose coverage shrank is
reporting something the service never claimed, and the only place to prevent
that is in the payload.

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

## Cross-validation, and what it is not

`crossval.py` runs the rules `config/prg.yaml` declares under
`cross_validation:` — four of them, over pairs of parameters **no equation
couples**: a carbon price against a budget ratio, a lender's coverage floor
against a sponsor's return, a reserve margin against a build target. Each is a
boundary a reviewer would argue about, not a physical constant, and each holds
at every parameter's declared default.

Three severities, and they are not decoration: `error` gates (`alea prg check`
exits non-zero), `warning` and `info` are printed and block nothing. The
condition describes the *bad* state — `if carbon_price > 100 and
coal_retirement > 2045: warning` — so a finding fires when the condition
**holds**.

The grammar is comparisons and boolean operators, deliberately **no
arithmetic**: `a * b > c` is a coupling the graph should state as an equation,
where it is checked dimensionally and propagated. `cooling + hydrogen <=
availability` is the worked example — it is already `water_availability_constraint`,
so it is an equation here and not a rule. A sign on a *number* is allowed
(`price_elasticity < -1.5`), a sign on a *parameter* is not.

What it is not: a value rule. §19's per-parameter `validation_rules` — "value
>= 0", "value <= 500" — are what `range` already states and the node model
enforces on every load; the text is dropped because it adds nothing the graph
does not already check.

## Edge strength, and what the tiers actually gate

Every edge in `config/prg.yaml` carries a `strength` — `hard`, `soft`, or
`informational` — which the spec defines as "inviolable", "usually true", and
"reported correlation". The field was declared on all 84 edges and read by
**nothing** until it was wired: a violation was a violation, and a graph that
distinguished a contradiction from a correlation did so in a comment.

The tier is now carried on the `Violation` and the `Conflict`, and it decides
whether a failure blocks. `informational` does not: it is printed, it stays in
the report, and `consistent` excludes it — so `alea prg check` and
`alea prg conflicts` exit zero on a correlation that moved, and the API's
`blocks` field says the same thing the CLI's exit code does rather than leaving
a client to re-derive it.

The shipped graph declares **two tiers, not three**: 36 `hard` equations and
one `informational`. No `soft` equation exists, and the register says so
(`alea prg summary` prints the counts, `/prg/summary` serves them) because a
reader who assumed all three were in use would misread the model.

**Where the tier can actually fire, and where it cannot.** The one
`informational` equation is `capture_price_ratio_definition`, and it
*determines* its own variable — so `propagate` recomputes the ratio from the
capture price and the marginal cost, and the equation holds by construction.
The tier is reachable through `consistency` on a set that was not re-propagated
and through nothing else; `check_scenario` never reports it. That is a fact
about this document rather than a property of the mechanism, and it is pinned
in `tests/ci/test_prg.py` so a second informational equation that *is*
reachable through a solve will be looked at rather than assumed.

## The constraint register, and the canary that did not fire

The six inequalities in the library are not six constraints. Two bind —
`reserve_margin` and `carbon_budget_constraint` — and the other four are stated
over quantities the graph derives from a solved result, so the network has no
column for them and the audit checks them after the solve instead. The register
is `alea prg summary`'s `constraints:` line and `/prg/summary`'s `constraints`
object, and its denominator is the six, not the 37.

Three things about it are worth keeping.

**A symbol is read from a declared source, never inferred.** Nothing in the
graph records that `firm_capacity_mw` is the summed nameplate of the
dispatchable fleet. Inferring it from the name would map it onto whatever
quantity shares the most characters. `SOURCES` states each mapping with the
assumption behind it written down — that storage is not counted toward firm
capacity, that "dispatchable" is the registry's classification and not an
availability guarantee, that the emissions term carries the same fleet-average
intensity stand-in the graph's own identity makes.

**An undeclared symbol falls back to the parameter set only if it is settable
with a default, and the route records that it did.** `reserve_margin_min` and
`capacity_factor` come from the scenario, not the network, and the route's
`assumed` tuple says so — because a constraint whose terms are half read off
the fleet and half off a default is a weaker claim than one read entirely off
the fleet. `firm_capacity_mw` and `peak_demand_mw` are *also* settable scalars
with defaults, which is why they carry declared sources: without them the
fallback would have swallowed the two terms that matter most.

**The canary that did not fire was the finding.** The carbon budget's unit
chain is MW × hours = MWh, × tonne/MWh = tonne, ÷ 1e6 = Mt, then scaled by
8,760 over the modelled hours. Dropping the annualisation is the mutation that
should break the test, and it did not: the fixture spans exactly 8,760 hours,
so the factor is 1 and removing it changed nothing. A canary that passes is
evidence about the canary before it is evidence about the gate — here the gate
was fine and the *fixture* was blind. The fix is
`test_the_carbon_budget_annualises_a_short_horizon`: a two-hour horizon, where
the same budget permits 4,380× more emissions per modelled hour, and the
assertion is on the emissions the solve actually produces. Re-running the
annualisation canary against it now fails as it must.

## What the dimensional check found`units.py` decides every equation: 30 of 37 are dimensionally consistent, 7
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

- **Part X's other backends are absent.** The spec names Pyomo for MILP, SymPy
  for symbolic manipulation and a custom iterative solver. Each is a separate
  modelling decision, not a missing adapter: the translation layer's output is
  a linopy constraint, and a second backend is a second answer to "what is a
  constraint", which the graph would have to be able to state in both.
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

  **The three routes were, until 2026-10-14, reached by no production caller.**
  That is the register's own defect class — declared is not produced — applied
  to the register itself: `translate.py` was written, tested, and imported by
  nothing but its own test file, so "three of fifty-three" counted a route no
  solve walked and the honest figure was zero. `WhatIfEngine.solve_from_prg`
  and `alea whatif scenario` are the seam; the count of reachable routes is now
  three.

  **Four more parameters reach the solve, and not through a knob.** The same
  defect applied to the other half of Part X: `constraints.py` was written,
  tested, and its `constraint_function` — the `extra_functionality` hook PyPSA
  calls — had zero callers in `src/`. So the reserve margin and the carbon
  budget constrained no optimiser, and `carbon_budget_mtco2`,
  `horizon_years`, `capacity_factor` and `reserve_margin_min` were refused by
  the strict path as uncarriable at the exact moment the graph could carry
  them. Since 2026-10-15 the solve runs under both inequalities by default, the
  four terms are named by `bound_parameter_names` rather than reported as
  dropped, and a fleet the reserve margin rejects is infeasible rather than
  silently solved without it. The gap that remains is the real one: seven of
  fifty-three settable parameters reach a solver whose *structure* the graph
  still does not set — no equation states the fleet, the topology, or the
  dispatch, and the graph cannot yet be the thing that builds the network.
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

**A constraint's terms are not "parameters that reach nothing".** The register
of what reaches an engine knob is built from `translated()`, and
`carbon_budget_mtco2`, `horizon_years`, `capacity_factor` and
`reserve_margin_min` are settable parameters with no knob — so a register built
from that alone names them as dropped. They reach the optimiser, through the
inequality the graph binds. `bound_parameter_names` is the complement that
makes the register honest: a parameter can reach a solve by tightening a bound
rather than by moving a number, and a register that knows only the second is
the same defect as `untranslated()` being unable to name a typo.

**An infeasible solve is not an exception, and a constraint makes one
reachable.** `network.optimize` returns `(status, condition)` and leaves the
objective where it was, so an engine that reads the objective without reading
the status caches a cost no feasible dispatch produced, wearing a solved
result's shape. That path was dead until the graph's inequalities reached the
model: the reserve margin is stated over the *grown* peak, so a fleet smaller
than the graph's own requirement is infeasible, and the graph's default
`firm_capacity_mw` of 9,000 MW is below the 14,469 MW the reserve margin
requires at `demand_growth`'s default over a ten-year horizon. `SolveError`
carries it, and the CLI exits 3.

**A constrained solve is a different solve, and the cache key must say so.**
The key covered the parameters, the network and the code version. A constrained
solve adds a fourth component — the record of the inequalities it ran under —
because one network solved under a carbon budget and solved without it are two
different optimisations. Omitting it is the network-checksum failure one level
up: whichever ran first is served to the other, and the number looks right.

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

**A declaration the loader pops is a comment that parses.** `from_mapping`
popped `validation_rules` *and* `cross_validation` off every node and dropped
both. The first is genuinely redundant — `range` states the same constraint and
the node model enforces it — but the second is §25's multi-parameter rules,
which relate parameters **no equation couples**, so nothing else in the graph
can supply them. Every rule an author wrote was silently discarded, and the
symptom is not an error: it is a check that reports "no findings" because it
never looked. The test is not that a rule can be parsed but that a rule
*declared in a document reaches `graph.rules` and is evaluated* — the
"declared is not produced" class, closed by making the pop-list and the
read-list the same list.

**A condition read as a requirement inverts every rule.** The spec writes
`if carbon_price > 100 and coal_retirement > 2045: warning`, so the condition
describes the *bad* state and a finding fires when it **holds**. The first
implementation appended a finding when it *failed*, which is the reading a
"must hold" habit produces — and the shipped graph then reported all four rules
violated at every default, a clean scenario flagged pathological. The canary
that catches it is a rule set that must hold at defaults; the one that catches
the opposite error is a probe that must make each rule fire.

**A one-parameter-at-a-time probe cannot trigger a conjunctive rule.** The
canary for "every rule can fire" moved each parameter to an endpoint of its
range in turn, and `carbon_price > 150 and carbon_budget_ratio > 1.0` never
fired: it needs *both* past threshold, and the probe held one at its default.
The fix is to walk the corners of the rule's parameters' ranges, not one axis
at a time. A canary whose probe is weaker than the condition reports a live
rule as dead.

**A rule the scenario cannot run is not a pass.** A rule naming a parameter the
set does not carry is reported in `undecided` with the reason, never dropped —
the same discipline as `units.undecidable`. A report reading "no
cross-validation findings" for a rule that was never evaluated is a clean bill
of health for a check that did not happen.

**A negative literal is `USub(Constant)`, and refusing every unary operator
refuses it.** The condition grammar allowed comparisons and booleans and
nothing else, so `price_elasticity < -1.5` — over a parameter declared
`(-3.0, 0.0)`, where a negative threshold is the only sensible one — was a load
error. The grammar refused a condition the graph needs. `USub`/`UAdd` are now
allowed on a *constant* only, so the arithmetic door stays shut: `-a` is still
refused.

**A declaration with no reader is a comment, even when it validates.** `strength`
was declared on all 84 edges, enum-checked on every load, exported in the model
— and read by nothing, so the spec's three tiers ("inviolable", "usually true",
"reported correlation") were a comment the loader happened to accept. The
symptom of the class is that nothing fails: a graph declaring every edge
`informational` and one declaring every edge `hard` behave identically, and the
difference is only visible to a person reading the YAML. The fix is not to read
the field somewhere convenient but to make it *decide* something — here, whether
a failure blocks — and then to gate on it, canaried in both directions.

**A property of the equation cannot be read off an edge.** The strength is
declared per edge, and 26 of the 37 equations are cited by more than one, so
"the strength of this equation" was ambiguous: a reader taking it from an edge
got whichever edge they read first. The constructor now refuses a document whose
edges disagree about one, rather than resolving it by an arbitrary pick — the
same discipline as `GraphError` for a node determined by two equations. A
strength that depends on iteration order is not a declared property.

**A determined equation cannot fail after a solve.** `capture_price_ratio_definition`
is the one `informational` equation, and it determines its own variable, so
`propagate` recomputes it and the equation holds by construction. A test written
against "a scenario whose only failure is informational is still consistent"
passed a raw set to `consistency` and a *solved* set to `check_scenario`, and
the second assertion failed because the solve had erased the finding. The tier
is real; the path that reaches it is narrower than the name suggests, and the
test now says which path it does and does not reach rather than asserting a
property the shipped graph does not have.

**An intersection with the derived set is empty by construction.** The audit
reported `checked = supplied ∩ derived`, and a solved result supplies only
*exogenous* parameters — `total_capacity_mw`, the carbon price, the growth rate
— because a derived value is what the graph computes *for* the result. The
intersection was therefore always empty, and `alea prg audit` printed
"consistent over 0 parameter(s)" for an audit that had evaluated eighteen
identities. The count was wrong in the direction that reads as a clean bill of
health, and a test asserting only `checked ∪ skipped == derived` passes on it,
which is why the corrected counts (18 and 10) are pinned individually. The
honest count is the *reach*: `affected_by(supplied) ∩ derived`. When a set
intersection is the denominator of a report, check it is not empty for the
reason the report is supposed to have a number in it.

**A check that cannot run must not be allowed to crash its caller, and must not
be allowed to pass.** The audit propagates a solved result's parameters through
the graph, and the graph can decline to have an opinion: the capture-price
feedback loop has no root in its `(0, 1)` bracket once the VRE build-out passes
the fleet's total capacity. Letting the exception escape destroys a valid
solve's answer inside a check that was never the answer; catching it and
returning `consistent=True` reports an unevaluated check as a pass. Both are
wrong, so the failure travels on the audit as a `failure` field, `consistent`
is `False` whenever it is set, and the canary removes the guard and watches the
test fail on `assert not audit.consistent`.

**A name that is not in the graph is neither translated nor untranslated, so a
register filtered on either is blind to it.** `to_scenario_parameters` skipped
any key that was not a settable graph parameter, and under `strict` — the
default — it skipped it *silently*: a misspelt `--set carbon_price_usd_per_ton=200`
solved, returned a plausible objective, and moved nothing. The strict path
exists precisely to prevent that, and it had a hole exactly the width of a typo.
Three classes of key reach no knob, and each now carries its own message,
because one message sends an author to the wrong fix: `unknown` is a string the
graph does not declare (a typo — and calling a real parameter one is itself a
false statement); `derived` is a graph parameter the graph *computes*, which
`propagate` overwrites, so setting it changes nothing and the fix is to set what
determines it; `skipped` is a settable graph parameter the engine has no knob
for, which is the only one whose fix is to widen the engine. The first two are
the reason the loose path's register had the same hole from the other side —
`solve_from_prg` built `dropped` by filtering on `untranslated()`, which
enumerates the graph's *own settable* parameters, so a typo and a derived value
were in neither `translated()` nor `untranslated()` and both were reported as
cleanly carried. The register is now the complement of `translated()`. The
general shape, and the third instance in this file: **a set built by enumerating
the graph cannot name what is not in the graph**, and a filter written from it
fails open toward "clean".
