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
| Service | `src/alea/prg/service.py` | `graph_summary`, `check_scenario`, `propagate_change`, `describe`, `equation_report` (an `EquationRow` carrying the declared citation, which nine equations have and nothing read until 2026-10-16) |
| Result audit | `src/alea/prg/audit.py` | Audit a *solved* what-if result against the graph's identities. `checked` is what the result's inputs *reach*, and `failure` carries a propagation that could not run — two fields whose first versions both lied in the direction that reads as a pass |
| Sensitivity | `src/alea/prg/sensitivity.py` | Exact forward-mode derivatives over the topological order; the implicit function theorem for loop variables; elasticity |
| Incremental propagation | `src/alea/prg/graph.py` | `propagate_incremental`: the closure of what changed, 9x a full walk, skipping a feedback loop nothing reached |
| Uncertainty | `src/alea/prg/uncertainty.py` | The declared stochastic inputs, the closure over `affects`, and the reach into derived parameters |
| Units | `src/alea/prg/units.py` | The dimensional check the spec asks for: each equation's two sides against a Pint registry of the graph's vocabulary, with §12's per-equation `unit_check` read into an `exempt` register — a declaration that the walk cannot decide a relation, kept apart from an equation nobody has annotated |
| Conflict detection | `src/alea/prg/conflicts.py` | The four kinds (direct, over-determined, under-determined, loop, out-of-range), ranked, with corrections |
| Cross-validation | `src/alea/prg/crossval.py` | §25's multi-parameter rules: a parsed condition, three severities, and the register of rules that could not be evaluated |
| Edge strength | `src/alea/prg/graph.py` | The declared `hard`/`soft`/`informational` tier, read by `consistency`, `conflicts`, the audit and the CLI gate |
| Translation | `src/alea/prg/translate.py` | Three declared routes from a PRG parameter to a what-if knob, the register of the other fifty, and the three refusals that name a key reaching no knob — a typo, a derived value, an uncarried parameter |
| PRG-driven solve | `src/alea/whatif/service.py` | `WhatIfEngine.solve_from_prg` + `PrgSolve`: the production caller the translation layer had none of — translate, solve, audit, with the dropped parameters carried on the payload |
| Constraints | `src/alea/prg/constraints.py` | The equation→constraint half of Part X: the two inequalities that bind a linopy solve, the four that are post-solve checks instead, and `bound_parameter_names` — the four scalars those inequalities read, which reach the optimiser with no engine knob |
| Constrained solve | `src/alea/whatif/service.py` | `solve_from_prg(constrain=True)`, the default: the graph's inequalities are added through PyPSA's `extra_functionality` hook, the constraint record enters the cache key, and an infeasible scenario raises `SolveError` instead of caching a cost |
| API | `src/alea/api/routes/prg.py` | The §43 surface: `GET /prg/summary`, `/graph`, `/graph/export`, `/parameters`, `/parameters/{id}`, `/parameters/{id}/dependents`, `/equations`, `/equations/{id}`, `/consistency/check`, `/consistency/report`; `POST /prg/propagate`, `/conflicts` (`/conflicts/detect`), `/conflicts/resolve`, `/feedback/solve`, `/translate`, `/sensitivity`, `/cross-validation`. The two reads and the two `/consistency` routes are public; the rest are analyst-tier |
| Python SDK | `src/alea/prg/sdk.py` | The §45 `PRGClient`: async, one method per §43 operation, returning the JSON the service served rather than re-modelling it. Transport failures and service errors both raise `PrgClientError`, so a caller writes one `except` and does not import `httpx` |
| Load cache | `src/alea/prg/graph.py` | `load_graph` memoised on the document's *identity* -- resolved path, mtime and size. Measured: a propagation is 6.5 ms and an incremental one 6.1 ms, while parsing the YAML is 73.0 ms of a 73.4 ms load, so §30's propagation cache targets the cheap half and the parse is what the workload asks for |
| The graph | `config/prg.yaml` | 869 parameters, 39 equations, 88 edges, 2 feedback loops (5 loop variables between them); 833 settable, 3 endogenous (the optimiser's fleet), 33 derived. The 781 with no equation carry `role: free` — the schema's word for "unconstrained within its range" — and `ParameterGraph.uncoupled()` names them, so the register is countable rather than implied |
| The catalog join | `scripts/build/prg_from_catalog.py` | The generator that joins `docs/params.md`'s 787 distinct names to the 88 shipped nodes, assigns each a system from the catalog's own category column, and writes `config/prg.yaml`. `--check` re-derives the file and diffs it, so the document and the graph cannot drift apart silently. It carries `cross_validation` through verbatim — a key it dropped once, which is the "declared is not produced" defect committed by the tool written to avoid it |

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
"reported correlation". The field was declared on all 88 edges and read by
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
object, and its denominator is the six, not the 38.

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

## What the dimensional check found

`units.py` decides every equation: 31 of 39 are dimensionally consistent, 8
are not, and 0 are undecidable. The eight are not eight of one kind, and the
fix differs by kind — which is why they are listed rather than counted:

| Equation | The mismatch | What it is |
|---|---|---|
| `crf_definition` | `1 + discount_rate`, a `1/year` rate | A rate added to the dimensionless `1`. Either `discount_rate` is a fraction and its unit is wrong, or the equation is. |
| `tariff_cost_recovery` | `1000 · annualised_capex · capacity / energy` gives `currency·time/mass/length²`, `marginal_cost` is `currency·time²/mass/length²` | The cost-recovery identity divides a *power* cost by an *energy* quantity; one side is missing a time factor. Found when the second feedback loop added this equation — it is the newest of the eight and the only one that arrived already flagged. |
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

None of the eight is reported as a *failure* by any other check, because the
graph is internally consistent either way — which is exactly the class of error
a dimensional check exists to catch, and the reason the check was worth adding
after `views.py` said the graph did not make it.

**The units vocabulary is the deferred decision behind four of them.** The
annual-quantity gap (`emissions_definition`, `hydrogen_water_definition`,
`premature_deaths_definition`, and the new `tariff_cost_recovery`) is not four
independent mistakes: it is one question about whether a node's unit names the
per-year divisor. Probed both ways — declaring the five `TWh` nodes as
`TWh/year` clears `tariff_cost_recovery` and opens `energy_balance`,
`energy_demand`, `equilibrium_demand`, `unserved_definition` and
`cooling_water_definition`. So the gap moves rather than closes, which means
the eight are not eight things to fix; they are one decision to make, and the
check is reporting the places it would land. Deferred rather than made,
because inventing the convention and then editing 88 units to agree with it is
manufacturing a decision no one took.

### The decision, made (batch 40, 2026-10-22)

Every equation in this table has since cleared. Six did so in the intervening
batches; batch 40 closed the remaining five and found three more of the class.
The graph now stands at **552 of 553 consistent**, and the one hold-out is
deliberate.

**The answer to the deferred question is that a node's unit names the divisor.**
An annual total is a rate, written `.../year`. That is the convention the graph
already used in most places — `coal_consumption` ships `tonnes/year`,
`total_revenue_usd_per_year` ships `USD/year` — so the decision ratified the
majority rather than inventing a vocabulary. The probe that made this look
expensive was reading the wrong end: retyping the five `TWh` nodes moves the
failure into `energy_balance`, because *those* equations were the ones that
needed the divisor added. Both sides move; that is a repair, not a regress.

**The finding worth carrying forward is that nine of the eleven were the
operand, not the formula.** `line_outage_hours_per_year_definition` was
`probability * duration` and still is; the node `line_outage_probability`
shipped `1/year` for a count of events. The walk reports `lhs vs rhs`, and the
natural repair is to rewrite the rhs — which would have edited nine correct
formulas and left nine wrong nodes untouched. Write the retype table from the
failing *nodes*, not from the failing equations. Three ids that look like
targets (`insurance_premium_usd_per_kw_year`, `line_outage_hours_per_year`,
`mini_grid_programme_spend_usd_per_year`) already shipped the correct unit.

**An untyped constant is refused, and that is the feature.** `coal_price_per_mwh`
divided by the literal `25 * 3.6` — right arithmetic, 12.96× low in value, and
inconsistent because the walker reads `25` as dimensionless. The fix is a typed
node (`mwh_per_coal_unit`, `MWh/tonne`), not a corrected literal. The
operational-supply pack reported this as a factor-of-12.96 error; it was not an
arithmetic error, it was the checker refusing to credit a constant it cannot
type, which is what catches the real ones.

**`rocof_definition` is the one remaining red, held on purpose.** The swing
equation is `df/dt = P_loss · f0 / (2 H S)` and the shipped body omits `f0`,
so it reports 1/50th of the correct value at 50 Hz. Correcting it drives
`frequency_nadir_hz` to 43.06 Hz against its own [45, 50] floor, because
`frequency_nadir_definition` applies the initial slope over a flat
`frequency_response_time_s` of 10 s. Either that response time is too long for
the model or the 45 Hz floor is not the UFLS setting it claims to be — a
question about the nadir chain, not about ROCOF. Bending either number to make
the other fit would be manufacturing agreement, which is the failure mode this
whole section exists to avoid.

### Dead arithmetic, found and repaired (batch 41, 2026-10-22)

The grid-operations pack measured a family that computed an identity at every
scenario. `demand_growth_start_year` and `demand_growth_end_year` both shipped
`25.0`, so `demand_growth_window_years = end - start = 0.0` and
`demand_growth_factor = (1 + g) ** 0 = 1.0` for every input. The factor then had
exactly one reader — its own definition — while the equation that should have
consumed it, `energy_demand`, compounded the exponent inline over
`horizon_years`. Two spellings of one compound growth, one dead, and the dead
one was the one the graph named as a derived quantity a report could print.

**The repair is a default, and the generator is where it came from.** The
catalog states a method for both nodes ("Temporal trajectory anchoring") and no
number; `prg_from_catalog._default_for` returns `25.0` for every node with
`unit = "years"`. That is a reasonable default for a *horizon* and a nonsense
one for a *start year*, and nothing distinguished them. Start is now the base
year (0.0) and end is the shipped horizon (10.0), so the window equals the
horizon by construction. Measured before shipping: `demand_twh` is
46.53902747054532 both ways — `33.8 · 1.0325¹⁰` — so rewriting `energy_demand`
against the factor changed no value at the defaults. It changed what the graph
can be asked: the factor now moves when `demand_growth` moves, because its
window is no longer zero.

**A switch typed as five hundred thousand.** `maintenance_schedule_optimisation`
shipped `float, unit=None, default=500000.0`. Read as an operand it raises
`GraphError: 500000.0 is outside the range`, so it could not gate anything.
Retyped to the graph's switch convention — unit `1`, range [0, 1], default 1.0,
the shape `ets_enabled` and `storage_dispatch_enabled` already use. It is
deliberately **not** coupled: the pack built the gate, and `switch ×
planned_maintenance_hours_per_year` reproduces that anchor's own 96 h/year. A
switch on by default, multiplied into the one anchor, produces a node equal to
its input and adds a terminal node to the 383 the pack counted. Closing
`uncoupled()` is not the objective; a computed quantity that is consumed is.

**The alias is a register entry, not an equation.** `cross_border_trading`
states it duplicates `cross_border_trade_allowed`, both are `unit = 1`, and the
canonical already gates `permitted_imports_definition`. Writing
`cross_border_trading = cross_border_trade_allowed` as an equation is refused
by the loader: `_deprecated_reach` raises on any edge or equation naming a
deprecated node, because a status nothing acts on is a label and the point of
deprecating a node is that the graph stops propagating through it. The
mechanism is the fragment's `aliases` register, which states the replacement
without coupling it — the right shape, since a caller migrating a scenario
needs the mapping and the graph must not compute through the retired id to
supply it.

The uncoupled count is unchanged at 239, and that is the honest reading: none of
these three nodes was uncoupled. What the batch repaired was a derived quantity
that was computed, stored and read by nothing — the declared-not-produced defect
in its cleanest form.

### The dials that moved nothing (batch 42, 2026-10-22)

The graph shipped two CCS adoption dials. Neither changed a tonne of reported
emissions. `coal_ccs_adoption` had two readers — the fleet-intensity equation
and the bound capping it with the gas share — and `gas_ccs_adoption` had one,
the bound. `emissions_mtco2_per_year` and `carbon_cost_usd_per_mwh` read
`emission_factor_t_per_mwh` directly: the factor of *one reference technology*,
not the fleet's. So the graph computed `fleet_emission_intensity_t_per_mwh`,
described it as "the fleet average at the current build", and consumed it
nowhere.

**Two defects wore one name.** The intensity applied the *coal* adoption share
to the whole fleet, so one fuel's dial reduced every tonne the fleet emitted
while the other did nothing. And neither share carried a capture rate, because
the graph held no such node — "a plant has capture" had no way to say "this
fraction of its carbon is not emitted". The repair is an arrow plus a weight:
`emissions` reads the fleet intensity, and the intensity is a
capacity-weighted average over the two capture-capable fuels times
`ccs_capture_rate` (0.90, the rate the IEA's technology tables use; archived as
`sources/archive/iea_nea_egc_2020.txt`).

**The third defect was the arrow's own precondition.** Both shares shipped
`0.5` — `_default_for`'s blanket value for every unitless fraction, on catalog
rows the document marks "To be built". While nothing read the intensity the
placeholder was inert; the moment emissions read it, a 0.5 capture share
deleted a fifth of the fleet's emissions at every default scenario. Retyped to
0.0: the shipped fleet has no capture plant. This is batch 41's 25.0 finding in
a different unit — a generator default that is plausible for one family and a
claim about the world for another.

**Measured, not asserted.** With the shares at 0.0, emissions stay at the
shipped 25.777 MtCO2/year, because the shipped fleet has no capture. Each dial
now moves it alone: coal 0→0.5→1 with gas at 0 takes emissions 25.777 → 18.044 →
10.311, and gas 0→1 with coal at 0 takes them to 18.044. Before the batch,
neither moved the reported total at all.

**`carbon_cost` was left alone, and that is the batch's own correction.** The
first draft moved it to the fleet intensity too — a carbon price should charge
the fleet for the tonnes it emits. The tree's closed-form test refuted it:
`marginal_cost_usd_per_mwh` is a *marginal* cost,
`emission_factor_t_per_mwh` is documented as the reference technology's factor,
and the test asserts `marginal_cost == fuel_price + carbon_price · factor` on
the raw factor. Moving it took marginal cost 65.0 → 53.75 and dragged both
feedback loops with it. A marginal cost prices the next MWh; the fleet average
is the right basis for a total account and the wrong one for a marginal one.

**Why a node and not a literal.** A capture rate is a technology parameter a
scenario should price. Folding 0.90 into the equation would have made it a
constant no scenario could reach — the untyped-constant defect the dimensional
walk refuses elsewhere.

**What the catalog wanted instead.** `docs/param_eqn.md` rows 2.6 and 2.10
declare `coal_ccs_adoption → coal_emissions_reduction` and
`gas_ccs_adoption → gas_emissions_reduction`. Neither node exists. Building the
per-fuel pair would duplicate the fleet decomposition the intensity now carries,
so the dials reach the fleet total a report reads, and the catalog's
decomposition stays unbuilt rather than half-built twice.

The uncoupled count holds at 239. The batch added one node, retyped two and
removed nothing from that set: all three are operands, and what the batch
repaired was a derived quantity read by nothing — the same class as batch 41,
which `uncoupled()` does not count at all.


### The constraint that was a copy of itself (batch 43, 2026-10-22)

`reserve_margin_with_firm_vre` shipped with the same lhs, the same rhs and the
same five parameters as `reserve_margin`. Not similar — byte-identical. A
reader who selected the firm-VRE variant for a solve got exactly the behaviour
of the other, and the graph carried two constraints where one was intended.
`vre_firm_capacity_mw` — the node whose description says "the value is a
quantity the reserve margin constraint reads" — was read by no reserve
equation at all. That is the register-prose defect: a description is a claim,
and nothing checks it against the payload.

**The term both equations used was the wrong quantity.** `capacity_factor` is
annual energy over rated output times 8760; a reserve margin asks for the share
of nameplate reliable *at the peak*. Capacity credit is smaller than the
capacity factor in every system, because the peak is when the fleet is least
likely to be producing. The IEA/NEA states it plainly — capacity credit "is the
portion of installed capacity that can be reliably expected to be available
during times of peak demand" (`sources/archive/iea_nea_egc_2020.txt`, §4) — and
the EIA derates intermittent renewables' credit "as a function of the
availability of the resource during peak load periods"
(`sources/archive/eia_lcoe_methodology.txt`), putting wind at 15% in its worked
example. The graph had no node for it.

**What the wrong term did, in the direction that reads as a pass.** At the
shipped defaults `vre_capacity_mw` derives to 2702.70 MW. The energy ratio gave
2702.70 × 0.35 = 945.95 MW of firm VRE capacity and `reserve_margin_actual` =
0.1701, comfortably above the 0.15 requirement. The capacity credit gives
2702.70 × 0.15 = 405.41 MW and the actual margin falls to 0.1065 — below the
requirement. The pre-batch graph reported an inadequate fleet as adequate,
which is the failure mode a reserve margin exists to catch.

**Three equations, one node, no new equation.** `capacity_credit_definition`
now multiplies nameplate by `vre_capacity_credit` (0.15, the EIA's worked wind
value, a parameter so a scenario can price a better-correlated fleet);
`reserve_margin_with_firm_vre` and `reserve_margin_actual_definition` both read
`vre_firm_capacity_mw`. Before, the requirement and the actual margin agreed on
every scenario for the worst reason: both wrote `vre_capacity_mw *
capacity_factor`, so the comparison the node exists to make was between two
copies of one number. A margin that meets its own requirement by construction
is not a check.

**`reserve_margin` was left alone deliberately.** It is a distinct constraint
over the same fleet and its body is not this batch's finding. Whether the solve
should carry the plain margin or the firm-VRE one is a modelling decision the
grid-ops pack leaves open; what this batch settles is that the two are no
longer the same equation, so the choice is real.

**A docstring caught by measurement.** The first draft of the batch's own prose
put `vre_capacity_mw` at 1250 MW and the firm contribution at 437.5 → 187.5 MW.
The node is derived, not exogenous, and propagates to 2702.70. The numbers were
rewritten from the run, not from the name.

**The reference build failed its own standard once the derating was right.**
Correcting the derating exposed a second defect underneath it.
`dispatchable_re_capacity_mw` shipped 1500 MW, and its own leaves —
`hydro_capacity` at 1500 and `geothermal_capacity` at 800 — sum to 2300. The
aggregate was neither the leaf sum nor a build anybody chose, and
`firm_capacity_definition` adds it to `thermal_capacity_mw` to get the firm
capacity the margin tests. Retyped to 2300: the leaf sum. The reference build
then reads firm 9800 MW against a 9775 MW requirement and
`reserve_margin_actual` 0.2006.

The old build passed for two reasons that cancelled. The thermal aggregate
ships 7500 MW against leaves summing 4900, an overstatement in the direction
that helps; the energy-ratio derating was a second overstatement in the same
direction; and between them the reference fleet looked adequate when its own
leaves were not. Correcting one overstatement and leaving the other in place
is what turned the defaults red — which is the useful part of the finding,
because a defect that only shows when its partner is fixed is a defect no
single check would have caught.

`thermal_capacity_mw` is deliberately left at 7500. It is the same defect in
the same direction, but it is a declared plan size rather than a sum the graph
computes, and correcting it downward would move the margin further into
violation. Sizing the reference scenario is a decision about the scenario, not
about the arithmetic this batch repairs; it is open, and it is recorded here
rather than guessed at.

**The uncoupled count holds at 239**, and for the same reason as batches 41
and 42: the batch's operands were already named by equations. What it repaired
was a *derived* quantity whose body was a copy — a class `uncoupled()` cannot
see.


### The tombstone that was still a knob (batch 44, 2026-10-23)

Batch 44 rebuilt the pollutant chain so the fleet reaches the death toll: fuel
energy from capacity, six pollutant ledgers from the EMEP/EEA factors, PM2.5
dispersion through a box model, and deaths from the concentration the fleet
actually produces. The health chain had run
`population × mortality × pm25_kt × pm25_relative_risk_per_kt` with the last
two exogenous dials nobody had to set, so a scenario that retired every coal
plant reported the same 4,800 deaths. At the shipped defaults the corrected
chain reports **17.35** deaths, and generation's share of them is **1.4%** of
the airshed's burden — the rest is the 5.0 µg/m³ regional background, which the
fleet does not own. Reporting 1,220 of 1,220 deaths as attributable to the
fleet was the first draft's answer and it was wrong by two orders of magnitude.

**The rename exposed a class the graph could not see.** The old node declared
`1/(kt/year)` — the unit of a dispersion factor — while carrying WHO's
concentration-response coefficient per µg/m³. It was deprecated in favour of
`pm25_relative_risk_per_ug_per_m3`, and the batch's own prose said the old id
was kept "so a scenario that names it fails loudly". Nothing made it fail.
`_deprecated_reach` refuses an *edge* or an *equation* naming a deprecated node;
it could not see a *value*. The node is not a determiner, not a loop variable
and not endogenous, so `is_settable` returned True, `propagate` accepted the
value, computed nothing from it, and returned it as the scenario's answer. A
caller who renamed a knob in a config got a silent no-op.

Two fixes, both at the source rather than at the counts. `is_settable` now
refuses a deprecated node — it is not a knob any more — and
`_refuse_out_of_range` raises on a supplied value that *differs from the
default*, naming the replacement. The differs-from-default test is not a
weakening: `propagate` is handed every default including the deprecated nodes'
own and cannot tell that from a caller setting it, and a caller who sets a knob
to the value it already holds has set nothing.

**The register counted the tombstone either way.** With `is_settable` fixed the
uncertainty register's input count stayed at 74 — one stochastic input replaced
by one — but `derived_stochastic` went 48 to **49**, because the deprecated node
now fell into the "not settable, not endogenous" set and was reported as a
derived parameter whose own relation is stochastic. A claim about arithmetic
nothing performs. Excluding deprecated nodes from the register's declaration set
put it back to 74 / 48, identical to the previous batch.

**The citation register refused its own keys.** Eight equations cite a row by
its register key (`reference: entsoe_adequacy`), and `Citation.resolves` matched
only the `cites` column — where **0 of 51 rows lists its own key**. So eight
load-bearing citations were reported as resolving to nothing while the rows they
named sat in the register. The key is a row's primary identifier and is now one
of the spellings. The ninth was real: `emissions_definition` cited the IPCC
Guidelines, which had no row. Equation 2.1 (printed p. 2.11) states
`Emissions = Fuel Consumption × Emission Factor`; the chapter is archived at
`sources/archive/ipcc_2006_gl_vol2_ch2.pdf` and the citation now names the
equation and records the step IPCC does not make — replacing the per-fuel factor
with the graph's own fleet average.

**Uncoupled falls 239 → 234.** Six of them are the co-pollutant nodes
(`co_emissions`, `mercury_emissions`, `nox_emissions`, `pm10_emissions`,
`sox_emissions`, `voc_emissions`), which had equations and no readers until the
batch's ledger totals named them. The other three are the deprecations leaving
the settable surface. Units hold at 564 consistent, 1 inconsistent (the
pre-existing `rocof_definition`), 3 exempt; the translate denominator falls
879 → 876 for the same three tombstones, and the constraint register is
unchanged in shape at 42 bound / 30 unbound / 72 constraint-shaped / 493
identities.


### The fuel term was priced per unit of heat (batch 45, 2026-10-23)

The three thermal LCOEs added a **thermal** fuel price to an **electric** cost.
`fuel_cost_coal` is documented, in its own description, as "delivered coal cost
per megawatt-hour of thermal energy", and every other node in the fuel family
agrees: `coal_price_per_mwh` is the commodity price converted to a thermal
basis, and the `delivered_fuel_below_commodity` rule compares the two on that
basis. `lcoe_coal_definition` was the one place that disagreed with all three,
summing the price directly into an annualised capital charge spread over
electrical output.

**No dimensional check could see it.** Both sides declare `USD/MWh`, so
`check_equation` returns decidable and consistent. Thermal and electric are the
same *dimension* and different *quantities* — the case a unit walker is
structurally blind to, which is why the defect survived 44 batches of
dimension-driven repairs. The arithmetic is valid and wrong by exactly the
plant's own efficiency.

Measured at the defaults: coal's fuel term was 12.0 where it should be
12.0 / 0.40 = 30.0; gas 35.0 where it should be 35.0 / 0.58 = 60.34; oil 80.0
where it should be 80.0 / 0.38 = 210.53. The LCOEs were 101.81, 87.82 and
213.51 and are **119.81, 113.17 and 344.03**.

**The gas error was the one that mattered.** At 87.82 gas was cheaper than coal
at 101.81 — a claim that a 58%-efficient CCGT on 35 USD/MWh_th gas beats a
40%-efficient coal plant on 12 USD/MWh_th coal. It does not. The corrected pair
sits 6.6 apart, close enough that the carbon price decides between them, which
is the comparison the graph exists to price.

The correction reuses the existing `efficiency_*` nodes rather than adding a
heat rate: each is already the divisor that turns capacity into fuel burn in
`coal_fuel_energy_definition` and its siblings, and a heat rate is the
reciprocal of an efficiency — the two-names-for-one-number defect this build
keeps removing. Biomass and nuclear also carry a fuel term and are **not**
corrected: neither has an efficiency node, and inventing a 0.33 for biomass
would be exactly the unsourced constant the walk exists to refuse. The generic
`lcoe_definition` is likewise flagged rather than touched — its
`fuel_price_usd_per_mwh` is documented per thermal MWh with no technology
efficiency to divide by.

`structure_issues()` caught the one thing the equation edit did not: `affects`
is a stored declaration the generator does not rebuild from the arithmetic, so
an edge added without the matching entry reports drift. The three lists were
updated with the edges.

Uncoupled holds at 234 — the operands were already named by equations, and what
this batch repaired was a *basis*, not a connection. Units hold at 564
consistent, 1 inconsistent, 3 exempt: the walker reads both sides as `USD/MWh`
and will keep reading them that way.

### The fleet could not make energy (batch 46, 2026-10-23)

Nothing in the graph converted an installed capacity into generated energy. The
tree carried eleven per-technology capacities, eleven capacity factors and a
typed `hours_per_year`, and no equation multiplied them. The three
`*_fuel_energy_definition` equations are the only capacity-to-energy identities
present, and they output GJ of *fuel* — the input side of the efficiency the
LCOEs divide by, not electricity.

The consequence was measurable. `generation_twh` was determined by
`energy_balance` from demand and losses alone, so no capacity could move it.
At the shipped defaults the fleet at its own capacity factors makes **68.065
TWh**; the graph reported **51.554**. Zeroing any single technology's capacity
left `generation_twh` unchanged to twelve decimal places.

**The consumer problem, and why the obvious repair is the wrong one.** Twelve
per-technology LCOEs were derived with no reader: the graph computed a ranking
— hydro 60.24, wind 63.67, solar 70.31, geothermal 79.16, biomass 87.27,
nuclear 104.19, gas 113.17, coal 119.81, offshore 121.00, csp 212.63, oil
344.03 — and nothing consumed it. Weighting those by generation and calling the
result a fleet LCOE is what the sources refuse. IEA/NEA reports that "the system
value of variable renewables such as wind and solar decreases as their share in
the power supply increases" (`iea_nea_egc_2020.txt:1143-1146`), so a fixed weight
vector is not a system cost, and that a per-technology indicator "depends on
some sort of allocation of the overall system costs between technologies"
(`:18762-18766`). What the literature does state completely is EIA's levelized
avoided cost of electricity and the value-cost ratio
`LACE / LCOE`, with its threshold stated exactly — "greater than one indicates
that the marginal new unit brings in value higher than its cost"
(`eia_lcoe_methodology.txt:194-196`). So the ranking is coupled through LACE and
a value-cost ratio, and no fleet LCOE was manufactured.

**Three designs written and reverted, each wrong for a different reason.** The
first hung one `least_cost_lcoe_usd_per_mwh = min(...)` over the eleven LCOEs
with one ratio off it. It baked, propagated, and reported sane values — then
took twenty tests red. `dsl.py:1243-1251` refuses `min` in a derivative:
*"'min' has no derivative rule; it is non-differentiable where its arguments
cross, and a formula that hid that would be used in a solver that then
oscillates."* One node therefore broke `gradients()`, `sensitivity()`, the
conflict-lever machinery (a conflict on the fleet's cost offered **zero** levers)
and the unit walker, which reported `undecidable` on a node the graph ships. A
node no gate can read is worse than no node. It was also the wrong metric: EIA
defines the value-cost ratio on a *candidate* project, not on the cheapest one.

The second replaced `min()` with a single `lace_usd_per_mwh` shared by all
eleven ratios. It passed the full suite — 212 tests — and was still wrong on the
arithmetic, in exactly the way batch 45 was wrong. Its capacity term divides by
generating hours, so it divided by the **generic** `capacity_factor` (0.35) for
coal at 0.75 and oil at 0.15 alike; and it multiplied by `vre_capacity_credit`
(0.15) for nuclear and coal, which are available at the peak and suffer no
intermittent haircut. Both sides read `USD/MWh`, so the unit walker could not see
it. The defect is invisible at the shipped defaults — `capacity_market` is 0, so
the whole capacity term vanishes — and only appears when a capacity market is
live. At `capacity_market = 1` the single-LACE design priced coal's capacity
revenue at 1.957 USD/MWh against a correct 6.088, and oil's at 1.957 against
30.441, a 15× understatement on the peaker.

The third is what ships: eleven `lace_{tech}_usd_per_mwh` nodes, each on its own
capacity factor and its own credit, and eleven `lcoe_value_cost_ratio_{tech}`
off them. EIA computes the ratio per technology — "we calculate LACE-to-LCOE …
ratios for each technology" (`eia_lcoe_methodology.txt:191`) — so this is the
faithful shape, not a workaround. The dispatchable credit is 1.0, matching
`firm_capacity_definition`, which already counts `thermal_capacity_mw` at full
nameplate in the reserve margin; a LACE that derated it would state a second,
contradictory rule for the same quantity.

**A basis error of my own, caught before the first bake.** The original LACE
draft used `capture_price_usd_per_mwh` — the VRE cannibalisation price — as the
energy term. Applying a VRE adjustment to technologies that suffer no
cannibalisation haircut is the same class of defect: both sides read `USD/MWh`,
the arithmetic is wrong by the adjustment factor, and no unit check can see it.
It read as VCR 0.729 — "no build is economic" — against 1.079 once the energy
term was EIA's actual definition, the marginal price.

**Measured after the bake.** `fleet_generation_twh` 68.065, `generation_twh`
51.554, `fleet_generation_headroom` 1.320. At the shipped defaults
(`capacity_market` 0) every LACE collapses to the marginal price of 65.00 and
the ratios are hydro 1.079 and onshore wind 1.021 clearing their cost, solar
0.924, geothermal 0.821, biomass 0.745, nuclear 0.624, gas 0.574, coal 0.543,
offshore wind 0.537, csp 0.306, oil 0.189 failing it. At `capacity_market = 1`
the capacity term separates on each technology's own basis and the ratios move
to hydro 1.217, onshore 1.048, solar 0.969, geothermal 0.889, biomass 0.820,
nuclear 0.673, gas 0.642, coal 0.593, offshore 0.551, csp 0.314, oil 0.277.

Canaries, each measured: zeroing coal drops the fleet total by exactly 19.710
TWh and the headroom to 0.938; zeroing solar by 19.272 and to 0.946;
`coal+solar = 0` takes headroom to 0.564, firing the adequacy rule.
`capex_hydro +3000` takes the hydro ratio 1.079 → 0.517, crossing EIA's
threshold downward. `fuel_price_usd_per_mwh 10` takes every LACE to 35.00 and
pushes **all eleven** ratios below one, firing the economic rule; at 80 the
fossil ratios fall (coal 0.876, gas 0.928, offshore 0.868) while the
low-fuel-cost technologies clear. All eleven LACE values were checked against an
independent closed form to 1e-9, and the fleet sum against the sum of its eleven
terms to machine precision.

**What this batch does not do.** It does not force `generation_twh` to equal the
fleet's potential, and it should not: 1.32× headroom is a fleet with surplus
capacity, and an equality would model a system spilling a third of its output.
The relationship is a `geq` — the fleet must be able to serve the load — which
is the constraint a planning exercise needs, plus the ratio as a reported
quantity. `thermal_capacity_mw` still ships 7500 against leaves summing 4900;
that is a separate finding and a separate batch.

Counts: 1426 nodes, 601 equations, 1342 edges, 57 rules; uncoupled holds at 234
— the new equations name operands that were already coupled, and all
thirty-five new nodes are derived (the batch adds 35 nodes and 36 equations). Units 600 consistent, 1 inconsistent
(`rocof_definition`, pre-existing), 3 exempt, **0 undecidable** — the figure the
`min()` draft had broken and this design restores. `structure_issues()` is empty
after the `affects` repair on the two exogenous operands the batch newly reads
(`hours_per_year`, `vre_capacity_credit`).

### The intensity weighted by the wrong quantity (batch 47, 2026-10-23)

Batch 42 gave `emissions_mtco2_per_year` the fleet intensity to read, and the
intensity it read was wrong in three ways at once. All three were measured on
the loaded graph before this batch touched anything.

**It divided by zero.** The shipped body was

```
emission_factor_t_per_mwh
  * (1 - (coal_capacity * coal_ccs_adoption + gas_capacity * gas_ccs_adoption)
         / (coal_capacity + gas_capacity) * ccs_capture_rate)
```

The DSL evaluates the quotient as a negative power, so `coal_capacity =
gas_capacity = 0` did not return an infinity a reader could see — it raised
`ZeroDivisionError: zero to a negative power` and aborted the propagation. A
thermal retirement is a scenario the model must represent; it was the one
scenario this equation could not survive.

**It weighted by capacity where the quantity is per MWh.** The lhs is
tonne/MWh, so the mean is over energy. Coal runs a 0.75 capacity factor and gas
0.6, so 3000 MW of coal makes 19.710 TWh and 1500 MW of gas 7.884 TWh — the
capacity weights are wrong in exactly the direction the two factors differ, and
no unit check can see it because the weight and the quantity both read as a
ratio. This is batch 45's basis error in a different body: same dimension,
different quantity.

**It used one generic factor for every fuel.** `emission_factor_t_per_mwh`
ships 0.5 and the graph ships seven per-fuel factors beside it — coal 0.92, gas
0.45, oil 0.78, biomass 0.04, nuclear 0.006, hydro 0.01, geothermal 0.03. The
generic node is the *reference technology's* factor, which the batch-42 section
above says in as many words, and multiplying it into every fuel discarded all
seven.

**The repair is a restructure, not a guard.** Batch 46 shipped the
per-technology `{tech}_generation_twh` nodes, so the intensity is now a
generation-weighted mean over the seven fuels that carry a factor, each capture
dial scaling only its own fuel:

```
(coal_generation_twh * emission_factor_coal_t_per_mwh * (1 - coal_ccs_adoption * ccs_capture_rate)
 + gas_generation_twh * emission_factor_gas_t_per_mwh * (1 - gas_ccs_adoption * ccs_capture_rate)
 + oil_generation_twh * emission_factor_oil_t_per_mwh
 + ...)
/ fleet_generation_twh
```

The denominator is the full eleven-technology fleet, not the seven fuels' sum.
The four zero-carbon VRE — `solar_pv`, `wind_onshore`, `wind_offshore`, `csp` —
carry no emission-factor node, contribute nothing to the numerator, and
correctly dilute the mean. A mean that dropped them from the denominator would
report the dispatchable fleet's intensity under the fleet's name.

**No epsilon guard, and the reason is structural.** After the restructure a
zero denominator requires *every* capacity factor to vanish, not the two
thermal ones alone. Measured: retiring coal and gas takes the fleet to 40.4712
TWh and the intensity to 0.014405 without raising; retiring oil as well gives
0.006874. Only a completely empty fleet still raises, and 0/0 is genuinely
undefined — that is a caller's to refuse, not something the equation should
absorb. `max()` would not have been available anyway: it has no derivative
rule, and batch 46's `min()` draft is the lesson.

**Measured at the defaults.** The intensity is **0.327098** t/MWh against the
shipped **0.500000** — a factor of 1.529 high — and
`emissions_mtco2_per_year` falls from **25.777** to **16.863** MtCO2/year. The
figure was checked against an independent hand-computation over the seven
terms, exact to the printed digits, and the fifteen new edges were verified to
be exactly the symbols the new body reads and the old one did not.

**Canaries, each measured.** The dials are zero at the defaults, so every one
of these switches a term on:

| scenario | intensity | emissions |
|---|---|---|
| `coal_ccs_adoption` 0.5 | 0.207214 | 10.683 |
| `coal_ccs_adoption` 1.0 | 0.087329 | 4.502 |
| `gas_ccs_adoption` 1.0 | 0.280187 | 14.445 |
| both at 1.0 | 0.040418 | 2.084 |
| coal 1.0, `ccs_capture_rate` 0.5 | 0.193893 | 9.996 |

The gas dial moves emissions on its own, which it could not before batch 42 and
did not after it either. The derivatives carry the right signs:
`d/d(coal_ccs_adoption)` is −0.2398 and `d/d(emission_factor_coal_t_per_mwh)`
is +0.2896.

**No cross-validation rule, and that is a grammar limit rather than a choice.**
The plausible bound — the intensity lies between the cleanest and the dirtiest
fuel's factor — is *false* under full capture: coal at adoption 1.0 with
`ccs_capture_rate` 1.0 contributes zero, so the mean can fall below nuclear's
0.006. The bound that is true is on the effective factors
`factor * (1 - adoption * rate)`, which is arithmetic, and the cross-validation
grammar admits no `BinOp`. A weaker rule would have been a gate that cannot
fail.

**The basis question, settled rather than deferred.**
`emissions_definition` applies the intensity to `generation_twh` (51.554)
rather than `fleet_generation_twh` (68.065), and that is correct.
`generation_twh` is not the demand-side figure: `energy_balance` solves
`generation_twh * (1 - transmission_loss_fraction) + net_imports_twh =
equilibrium_demand_twh`, which at the defaults gives (47.430 − 0) / 0.92 =
51.554 exactly. Because the intensity is a per-MWh mean and the graph scales
every technology's output by one dispatch ratio α = 51.554 / 68.065 = 0.7574,
the two bases are **algebraically identical** — `num / fleet_generation_twh`
and `(α·num) / (α·fleet_generation_twh)` both give 0.3270978. Applying the
intensity to `fleet_generation_twh` would be the error, not the repair: it
charges the fleet for capacity it never dispatched, 22.264 MtCO2 against
16.863. There is no batch to write here.

Counts: 1426 nodes, 601 equations, 1354 edges, 57 rules; uncoupled holds at 234
— the batch adds no node and no rule, correcting one equation and re-pointing
its edges (3 dropped as stale, 3 corrected, 15 added). Units 600 consistent, 1
inconsistent (`rocof_definition`, pre-existing), 0 undecidable.
`structure_issues()` is empty and `check_latex` reports no finding.

**Citation gap, recorded rather than papered over.** The seven
`emission_factor_{tech}_t_per_mwh` nodes name "IPCC lifecycle emission factors,
2014" in their own `source` field, and `sources/INDEX.md` carries no row for
that work — its only IPCC entry is the 2006 *Guidelines*, Volume 2, a different
document. The edges therefore cite IEA/NEA (registered at `sources/INDEX.md:50`
and archived) for the capture rate and point at the factor nodes for the
factors. Registering the lifecycle basis is a new index row plus an archived
copy, and it is the honest follow-on.


## Not built

- **`00-architecture.md` §6's repository layout declares 37 paths and one does
  not exist.** Closed 2026-10-16 by `alea.quality.layout` and
  `tests/ci/test_layout_register.py`, which parse the tree out of the document
  and require every declared path to exist or be a named gap. The finding is kept
  because the resolution is the interesting part: seven of the eight absences
  were not build tasks, and three different defects wore the same shape.

  **The five `config.*.yaml` files were a doc defect, and the tree was wrong.**
  `sector`, `predictive`, `whatif` and `reporting` are *sections* of
  `config.default.yaml` — lines 111, 18, 70 and 153 — and the loader opens
  exactly two files: `config.default.yaml` and one environment file. So §6 now
  draws `config.default.yaml`, `config.kenya.yaml` and `scenarios/`, with a
  comment saying every layer's section lives in the default file.
  `05-layer2-sector.md` §4's YAML sample headed `# config/config.sector.yaml —
  extends, does not replace` is still the older spelling and still tells a reader
  to create a file nothing reads; correcting it means rewriting the sample, which
  is a larger edit to a layer plan than a layout fix.

  **`docs/research` was a real absence and has been built**, with a `README.md`
  stating the distinction from `sources/`: a citation archive is not a research
  note, and the tree declares both.

  **`data/interim` is registered as a deliberate gap.** Declared in §6, in
  `config.default.yaml:175` and as `paths.interim` in `alea.config.models:285` —
  and read by nothing. Every stage writes to `paths.processed` and reads from
  `data/raw` or another stage's processed artefact. The directory was not
  created: an empty directory would look like a place something lands while
  `paths.interim` kept no reader. Closing it is a choice — drop the tier and the
  config key, or name the stage that needs a non-processed intermediate — so it
  is registered with the closer named rather than resolved by fiat.

  The gate was watched failing: the canary plants a `phantom/` entry into §6 and
  asserts `test_every_declared_path_exists_or_is_a_named_gap` notices. The
  mutation is in the *document*, which is the gate's input, and is therefore
  disjoint from what the predicate compares.

- **`ParameterNode.status` is declared on all 869 nodes, and now has a reader.**
  When this was written it was on all 88, read by nothing, and stale: 70
  `to_build` / 18 `existing`, with five of the `to_build` nodes already reached
  by a production path (`carbon_budget_mtco2`, `dispatchable_re_capacity_mw`,
  `horizon_years`, `storage_capacity_mw`, `thermal_capacity_mw`). Same class as
  `linearity`: a declaration whose referent was never fixed, drifted from the
  tree because nothing could read it to notice. The reader now exists —
  `catalog.py` groups the nodes by `status` and the API serves it — and the
  catalog join took the field to all 869 nodes (644 `to_build`, 160 `existing`,
  65 `integrate`), copied from the same column the legend defines.

  Two corrections to the entry as it first stood. The field is not read by
  *nothing*: `_parameter_out` serves it on `GET /prg/parameters` and
  `GET /prg/parameters/{id}`, so it reaches two doors. It is read by nothing
  that *decides* anything — no gate, no register, no solve consults it — which
  is the claim the entry is actually making and the one worth keeping. And the
  five-node disagreement was re-measured on 2026-10-16: `bound_parameter_names`
  returns `capacity_factor`, `carbon_budget_mtco2`, `horizon_years`,
  `reserve_margin_min`, and the other three are read by `audit.fleet_parameters`
  — so the five are confirmed, and the class of reader that reaches them is a
  *bound* or a *fleet readback*, not a builder. Neither reader consults `status`,
  which is why the label could drift without anything failing.

  **The referent exists and the label was copied from it.** `docs/params.md` —
  the master parameter catalog — carries a Status column with the legend
  `✅ Existing | 🔨 To Build | 🔗 Integrate`, which is exactly
  `Literal["existing", "to_build", "integrate"]`, and Users/Priority columns
  matching `tuple[str, ...]` and `Literal["P1", "P2", "P3"]`. `ParameterNode`
  was transcribed from that table. The join is only 6 of 88 nodes by name —
  the catalog is technology-specific (`coal_capacity`, `solar_pv_capacity`)
  while the graph is a single-country aggregate, so no mechanical join exists,
  which is why nothing has ever checked one against the other. On the six that
  do join, **five agree and `equity_return_target` has drifted**: `to_build` in
  the graph, `integrate` in the catalog. That is the signature of a hand-copied
  column, and it makes `status` a *transcription with no diff* rather than an
  undefined label — a much more specific defect, and a fixable one (populate
  the remaining 82 from the catalog, or drop the column and let the catalog be
  the register). Left as a finding because the choice between those two is the
  user's, not the code's.

  **The join now has a reader, and it is the one that found the drift above.**
  `prg/catalog.py` parses `docs/params.md` and `catalog.status_join` reconciles
  the two vocabularies node by node; `prg summary` carries it as `catalog`, and
  `tests/ci/test_prg_catalog.py` pins the six-node join, the five agreements and
  the one disagreement by name. So the entry's claim that "nothing has ever
  checked one against the other" was true until 2026-10-16 and is now false:
  the check exists, it is on the summary, and it fails loudly if the drift
  moves. What remains a finding is only the *resolution* — populate the
  remaining 82 from the catalog, or drop the column and let the catalog be the
  register.

  Reading the catalog to build that join turned up three things about the
  document itself, all of them the same defect class one level up: it states
  its own size three times and the three disagree. The title claims **784**
  parameters, its 28 category headings declare per-category counts summing to
  exactly **824**, and the table holds **824 numbered rows over 787 distinct
  names** — 35 names appear on more than one row. Each number is correct about
  the thing it describes (the headings do match their rows, to the row), which
  is why nothing caught the disagreement: no line is wrong, only the document
  as a whole. `catalog.summary()` serves all three side by side and
  `catalog.title_count()` reads the claim out of the heading rather than
  serving the constant, so editing the title moves the register.

  Of the 35 repeated names, 11 disagree somewhere and only **2 disagree on a
  classification column** — `planned_outage_rate` on Priority (`P1` under
  Outage, `P2` under Operational) and `resettlement_costs` on Users (`DFIs`
  against `Developers`). The other 9 differ only in their prose columns, which
  is by design: the catalog is organised by *concern*, so a quantity relevant
  to two concerns is listed under both and its Algorithm cell is written for
  each. `catalog.contradictions(classification_only=True)` is the narrow
  register; the wide one keeps the two classes apart rather than merging them,
  because reporting 11 findings where 2 are real is a register a reader stops
  reading. Both classification conflicts are left as findings — which of the
  two rows is right is an editorial call, not a code one.

- **Four declared node fields are populated on zero nodes, and the spec's own
  example populates all four.** `source`, `source_url`, `users` and
  `subcategory` are on `ParameterNode` — `subcategory` as `str | None`, the
  other three as `str | None` / `tuple[str, ...]` — and `config/prg.yaml`
  writes none of them on any of the 88 nodes. The spec's example node
  (`docs/alea_prg.md`, the `carbon_price` block) carries every one:
  `subcategory: "Climate Policy"`, `source: "IMF Effective Carbon Prices"`,
  `source_url: "https://www.imf.org/"`, `users: ["Policymakers", "Investors",
  "Utilities"]`. A document written to that example loads — the fields are on
  the model and validate — and then the values reach nothing: `ParameterOut`
  serves neither, and the register that exists to count this class did not name
  them.

  This is the `declared is not produced` shape with the twist that the
  declaration is in the *spec*, not only in this tree, so the honest reading is
  not "the YAML forgot to fill them". It is that the graph was built without a
  consumer for parameter provenance and audience, and the model kept the fields
  because the spec declares them. Two of the four have an obvious seam this
  project already owns — `provenance.models.Provenance` carries a `source_url`
  and the scanning layer fills it — and wiring PRG nodes into that layer is a
  modelling decision about whether a *parameter's* source is the same kind of
  fact as a *signal's*, not a missing adapter. The other two (`users`,
  `subcategory`) name an audience and a taxonomy the tree has nowhere to put.
  Recorded rather than built, and recorded because a field the spec's own
  example fills is one a reader will assume works.

  **Measured against the catalog on 2026-10-16, which narrows all four.** The
  referent that was missing for `status` is missing for these too, and looking
  for it separates two fields that share a name from two that do not.

  - **`subcategory` has no referent in the catalog at all.** `docs/params.md`
    has one Category column, 29 values across 824 rows, and no Subcategory
    column anywhere. The graph's `category` has 14 values, and the two lists
    are not a coarsening of each other — they share exactly two names,
    `Demand` and `Market`, and diverge on all 27 and 12 others (the catalog's
    `Aviation`, `Fisheries`, `Defence`, `Geopol` against the graph's
    `Affordability`, `Policy & Regulatory`, `Reliability`). So the catalog and
    the graph each have one flat taxonomy, they disagree about it, and neither
    has a second level — which leaves `subcategory` with no level to be the
    second of. Its only inhabitant anywhere in the tree is the spec's example
    string `"Climate Policy"`. This is the one of the four where dropping the
    field is a live option rather than a loss.
  - **`users` has a real vocabulary and a 7% join.** 34 distinct values across
    the catalog's Users column — `Policymakers`, `Investors`, `Utilities`,
    `Banks`, `DFIs`, `Agriculture`, `Cities` — so it is a curated audience
    list, not free text. But it joins to the graph on the same 6 nodes as
    `status`, for the same reason: the catalog is technology-specific and the
    graph is a country aggregate. Populating it on 6 nodes and leaving 82
    unset would make the field *look* served, which is worse than the current
    honest emptiness.
  - **`source`/`source_url` split internal from external, and the split is
    real.** The catalog's Algorithm and Python Implementation columns are
    *internal* provenance — where in this codebase a value comes from. The
    spec's `"IMF Effective Carbon Prices"` is *external* provenance — the
    literature a value was taken from. `provenance.models.Provenance` is the
    external kind and is used by 19 modules (planning, reporting, losses,
    quality, publish, sector, resilience) and by **zero** in `prg/`. Wiring
    these two fields into it is the one of the four that has an existing home
    and an existing shape; it is deferred because the catalog does not carry
    the citation for most rows either — `carbon_price`'s own row names an
    algorithm (`n.generators.marginal_cost += carbon_price * co2`) and a
    status, and no source — so the wiring would populate from the spec's
    single example. `catalog.read_catalog()` now serves the Algorithm and
    Implementation columns as data, so the internal half of that split is
    readable; the external half is still one row in a spec example.

    **The external half now has a referent, and it is not the spec's example.**
    `sources/INDEX.md` — the directory `00-architecture.md` §6 declares and the
    tree did not have — registers every work the library leans on, and
    `alea.provenance.citations` joins those rows to the citations the equations
    make. So `source_url` has something to point at, and the finding narrows
    from "there is nowhere to put an external citation" to "the nine equations
    that declare one are registered and the 88 nodes still declare none".
    Wiring `ParameterNode.source`/`source_url` into `Provenance` is now a
    decision about whether a parameter's source is the same kind of fact as a
    signal's, which was always the question — but it is no longer blocked on
    there being no register to cite.

    What the register found on its first run is worth recording, because it is
    the reason it is a gate and not a document. Of the nine citations, **four
    name a custodian** — IRENA's cost statistics, WHO's AirQ+ methodology,
    ENTSO-E's adequacy practice, IEA/NEA's LCOE definition — and **five name a
    derivation**: the annuity formula, the WACC identity, the swing equation,
    average-cost pricing, and the N-1 criterion. The five are textbook results
    with no single work behind them, and recording them as unattributed works
    would have read as five missing citations; they are marked `n/a` so the
    register says what they are. Of the four with a custodian, **one is
    archived** (IRENA's executive summary, 3 MB, `sources/archive/`) and three
    are not — IEA/NEA and the *Journal of the Aeronautical Sciences* are behind
    paywalls, and WHO's AirQ+ landing page is a JavaScript shell that archives
    as 755 bytes of nothing. The gate reports those three and does not fail
    them, because a gate nobody can pass is a gate nobody runs.

  Left as findings because every resolution here is a product decision: drop
  `subcategory`, populate `users` from the catalog on the joinable nodes or
  not, and adopt `Provenance` for parameter sources or keep parameter
  provenance out of the artefact layer.

  **The catalog is no longer an unopened document, which changes the shape of
  all four entries.** Until 2026-10-16 nothing in `src/` had read
  `docs/params.md` — it was cited in prose by this file and by
  `docs/modelling-alg-2.md:39` and read by no code, which is why a hand-copied
  Status column could drift and why nobody could say what `users`' vocabulary
  was. `prg/catalog.py` is that reader, `prg summary` carries its register, and
  every number in the three bullets above is now computed rather than
  transcribed. The four fields stay unpopulated, and that is still the right
  call: populating 6 of 88 makes a field look served. What changed is that the
  decision is now made against a measurement instead of against an impression.

- **Part X's other backends are absent.** The spec names Pyomo for MILP, SymPy
  for symbolic manipulation and a custom iterative solver. Each is a separate
  modelling decision, not a missing adapter: the translation layer's output is
  a linopy constraint, and a second backend is a second answer to "what is a
  constraint", which the graph would have to be able to state in both.
- **The engine is barely driven by the graph.** `translate.py` declares the
  routes, and there are **three**: `carbon_price_usd_per_tco2` and
  `demand_growth` map one-for-one, and `fuel_price_usd_per_mwh` maps to the
  engine's `gas_price_multiplier` as a ratio over the network's base gas cost.
  The other **49 of 52** settable parameters reach no what-if knob. They are
  named by `translate.untranslated()` and counted in `alea prg summary`. This
  is the register, not an omission: the graph states what the physics and the
  accounts require, and the engine states what a PyPSA network can be
  perturbed by, and the two sets were built for different purposes. The
  register runs both ways: `engine_fields_unreached()` names the **7** engine
  knobs no PRG parameter reaches (`coal_eaf`, `renewable_multiplier`,
  `battery_cost_multiplier`, `ssp_pathway`, `drought_multiplier`,
  `hydrogen_export_twh_per_year`, `outages`). A scenario pulling one of those cannot be
  audited against the graph, because the graph does not know the quantity
  moved.

  **Widening the seam was considered and refused, on measurement.** Five of the
  seven knobs have a genuine catalog counterpart (`coal_eaf`, `renewable_multiplier`
  → `solar_irradiance_multiplier`, `drought_multiplier` →
  `hydro_drought_multiplier`, `battery_cost_multiplier` → `battery_cost`,
  `hydrogen_export_twh_per_year` → `hydrogen_export_volume`); the other two
  cannot be carried at all, because `to_scenario_parameters` writes
  `float(value)` on both of its paths and `ssp_pathway` is a `str` while
  `outages` is an `OutageSet`. The five counterparts are all `role: free`,
  `uncoupled`, `unit: None`, range `(0, 1e6)`, default `500000.0` — and the
  engine refuses that default (`coal_eaf` is bounded `le=2.0`), while narrowing
  the PRG range to fit is refused at load by
  `ParameterNode._range_contains_default`. So each would cost authoring a real
  range and default for a node the catalog states no bounds for, to add a
  translation over a node no equation names. The denominator did not change
  either: the auditable core is **52** settable parameters, exactly as before
  the catalog join, and **3 of 52 is 5.8%** — the same fraction it always was.
  The 0.4% is the expansion diluting a denominator, not the seam narrowing.
- **The declared range is now enforced on the settable path.** It was read in
  three places and enforced in none of them for a caller's own value: it
  brackets the solver for a derived parameter, it filters the corrections the
  conflict detector proposes, and `ParameterNode._range_contains_default`
  checks it against the document's default. So `propagate` accepted
  `capacity_factor=999` against a declared `(0.05, 0.7)` and returned it as the
  scenario's value, with `range_excursions()` empty — that register is written
  from `_note_excursion`, and a settable node has no equation to derive it.
  `ParameterGraph._refuse_out_of_range` closes it on both propagation paths,
  with both bounds inclusive. **Settable only**: a derived value outside its
  range is the graph's own answer and stays a reported finding, because the
  incremental contract feeds `previous`'s derived values back in, and refusing
  them would leave a run in which one equation lands outside its range unable
  to propagate at all. The first draft checked every key and did exactly that,
  on `reliability_cost_usd` at 1.096e12 against a declared 1e12 ceiling.

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
  fifty-two settable parameters reach a solver whose *structure* the graph
  still does not set — no equation states the topology or the dispatch, and
  the graph is not yet the thing that *builds* the network.

  **The fleet is now the graph's, in both directions, and it took two steps.**
  `Role.ENDOGENOUS` — the spec's §3.4 middle layer, what the optimiser chooses
  — was declared, enum-validated, exported on `ParameterNode`, and carried by
  **zero nodes**; the graph was a two-layer DAG (53 exogenous → 31 derived)
  while the spec declares three. That is why it could not state a fleet: it
  could say "an equation fixes this" or "you set this", and a fleet is neither.
  Since 2026-10-15 three endogenous nodes carry the optimiser's own decisions
  (`thermal_capacity_mw`, `dispatchable_re_capacity_mw`,
  `storage_capacity_mw`), each with the range an LP needs and a reference
  default; `firm_capacity_mw` is *derived* from two of them by
  `firm_capacity_definition` rather than stated by fiat, so the reserve margin
  is a check on the build instead of on a declared number.

  **And the second step is the one that would have been missed.**
  `audit.fleet_parameters` reads the solve's own `capacity_mix_mw` back into
  those three nodes, classifying carriers by the registry's `CarrierClass`.
  Without it the nodes kept their reference defaults through every audit — the
  declared-is-not-produced defect *inside the layer added to fix it*, and the
  hard version to see, because 7,500 MW of thermal is a plausible number. A
  coal-and-wind result reporting 6,000 MW of firm capacity against an 8,500 MW
  peak passed the reserve margin until this landed.
- **The energy balance is single-region.** One demand, one generation total. A
  PyPSA network balances per bus and per hour and the solved result carries no
  nodal frame, so the audit cannot assert the balance *per bus* against it. What
  it can assert is the system-wide residual, and since 2026-10-15 it does: the
  result carries `energy_balance_error_mwh`, both doors print it, and the solve
  refuses one over tolerance. See "Closed since this list was written" below for
  why the per-bus assertion is still out of reach and why the system-wide one
  was worth having.

  **This item previously said wiring the check was wrong, and the reasoning is
  worth keeping because half of it was right.** PyPSA's own `consistency_check`
  does refuse a load on an undefined bus at solve time, so the check is not the
  only guard. But the other half — "it false-positives on any network carrying a
  link" — was a description of a *bug*, not a jurisdiction problem, and it was
  an underestimate: measured, a link network fails by 11.1%, not 1.6%. A gate
  scoped wider than its jurisdiction refuses correct solves until someone turns
  it off; a gate with a *defect* does the same and gets left unwired, which is
  what happened here for as long as it did. The distinction matters: the first
  is fixed by narrowing the check, the second by fixing it.
- **Emissions use one fleet-wide factor.** The engine sums per-carrier
  intensities. `audit.fleet_intensity_gap` measures the difference instead of
  pretending they agree. Since 2026-10-15 `alea whatif scenario` prints it: the
  gap was computed, carried on `PrgSolve`, and shown by no door.
- **The reliability standard was declared and unread.** `expected_unserved_fraction`
  is the share of demand the system is meant to fail to serve, and until
  2026-10-15 it was read by its own equation and by nothing else — the
  declared-is-not-produced class, on a number that states a policy. The engine
  measured the realised share (`unserved_energy_mwh` over the demand, which is
  the generation total because load shedding is itself a carrier) and reported
  it against nothing. `audit.reliability_gap` now reports the realised fraction,
  the declared one, and their ratio, and both `alea whatif scenario` and
  `alea prg audit` print it. It is a measurement and not a refusal: a scenario
  deliberately short of capacity is a stress case the frontier is built from,
  and refusing it would forbid exactly those points.
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
- **Every parameter is `float`, and `type` gates only that.** The spec's §20
  asks for type *inference* from equations. There is nothing to infer: all 88
  nodes are float, all appear in arithmetic, and none is used as an index — so
  an inference engine here would be a gate that cannot fail. What was real is
  that `type` was declared on all 88 nodes, enum-validated, exported, and read
  by **nothing**: a node declared `timeseries` with a scalar `default` was
  accepted, propagated as a float, and reported as a quantity. The node now
  refuses a non-scalar type carrying a scalar `default` or `range`, because
  the model has no field for an array. `float` and `int` are the types it can
  honestly carry; the other four wait on a field that holds the array.
- **The 784-parameter catalog is joined, and 781 of its nodes carry no
  equation — deliberately.** Every one of `docs/params.md`'s 787 distinct
  names is now a node in `config/prg.yaml`, and the honest count of the ones no
  equation names is `uncoupled()`: 782 (781 settable plus
  `storage_capacity_mw`). They are `role: free`, not `exogenous`, because
  nothing downstream reads them: `free` is the schema's own word for
  "unconstrained within its range", and calling them exogenous would claim a
  modelling decision the document does not make.

  The alternative — authoring an equation per node — was measured and refused.
  The catalog states **no formula**: `=` appears in 0 of its 787
  algorithm/description cells, and the 16 rows matching an operator word are
  PyPSA API bindings (`n.generators.p_nom`), not arithmetic. `docs/params-prg1.md`
  does state 20 systems of equations, but over parameter *classes*
  (`capex_*`, `opex_fixed_*`), and the catalog instantiates those classes
  sparsely — only three technologies carry three or more class members
  (`coal`, `gas`, `biomass`), so class instantiation reaches a handful of
  nodes, not 787.

  A per-node equation used to be the one shape the loader refused outright:
  `'1000000.0' names no parameter; a constant expression relates nothing and
  would pass every consistency check vacuously`. That refusal was mis-scoped —
  it is an argument about a *relation*, and it was being applied to a *side*,
  where a constant is what a bound is made of. `dsl.parse_side` now accepts a
  constant side, so `x == 1000000.0` and `sum(shares) <= 1.0` both load; the
  vacuity guard moved to the combined arithmetic, which is where it can be
  stated, and a relation whose two sides are identical is refused separately
  (see `e0efc70`). So the loader is no longer the reason not to author
  per-node equations.

  The surviving reason is dimensional: a sum identity over the technology
  capacities is not sound, because the
  catalog declares **no unit** for them (its columns are number, category,
  name, title, algorithm, binding, status, users, priority) while the fleet
  totals it would sum against are in MW. And every candidate total is already
  determined by a shipped equation or is `endogenous` — a sum would
  over-determine the first and remove the optimiser's choice from the second.

  `params-prg1.md` §3.2 proposes its own split for these 784 — ~420
  exogenous, ~180 endogenous, ~140 derived, ~44 free — and names
  `coal_capacity` as endogenous. Measured against the tree and refused in both
  directions. `derived` needs an equation and the catalog states none:
  flipping the nine derived-by-name nodes makes the graph refuse to propagate
  with *"a parameter that is not derived has no equation to compute it from"*.
  `endogenous` is legal — those nodes carry the range and default the schema
  demands — but would be a false diagnosis: `propagate_change` refuses an
  endogenous parameter with *"the optimisation, not the graph"*, and no
  optimiser in this tree reads `coal_capacity`. The fleet the solve chooses is
  `thermal_capacity_mw` and its three siblings. Marking 14 catalog names
  endogenous would assert a mechanism that does not exist.
- **The engine seam did not widen with the graph.** Three of 833 settable
  parameters reach a what-if knob, down from three of 52. The expansion added
  781 knobs the engine cannot be driven from, and `test_the_coverage_count_is_a_literal_and_matches_the_register`
  pins both numbers so the numerator cannot quietly grow to hide it.
- **No UI.** Packaging rather than capability, and the last door left shut. The
  CLI and the API both reach every register; a UI would render them.
- **§37's Anderson acceleration is not built, and measurement says building it
  would make convergence worse.** The spec prescribes Anderson acceleration or
  Aitken's delta-squared for slow loops. Both shipped loops are slow in the
  sense the spec means (38 and 36 iterations at the defaults), so this was the
  next item on the list until it was measured against the real propagation
  path rather than argued about.

  Plain damped Gauss–Seidel, which is what the solver already does, converges
  in **38 and 36** iterations at the defaults. Anderson with `m=3` needs **63
  and 45**; `m=5` needs **67 and 49**; `m=2` **fails** — the loop does not
  converge inside its 200-iteration budget. Across four scenarios (defaults,
  `carbon_price_usd_per_tco2=1000`, `demand_growth=0.15`,
  `renewable_multiplier=0.5`) the baseline is 37–38 and 32–36, and every
  accelerated run is worse than its baseline. So the ordering is stable and
  the direction is unambiguous: the spec's mechanism is roughly 1.5× slower
  here, and at `m=2` it does not converge at all.

  The reason is in the spec's own snippet. It extrapolates over the raw
  iterate history, and this solver's iterates are *damped* — `values[target] =
  values[target] + damping * (solved - values[target])` with `damping = 0.5`.
  A damped fixed-point sequence is a geometric one, and the least-squares
  extrapolant over a geometric sequence mostly recovers the damping factor,
  which is to say it proposes the undamped step the damping exists to
  suppress. The acceleration and the relaxation are fighting, and the
  relaxation wins because it is what makes the loop a contraction.

  **The spec's snippet does not run as written.** `X = np.column_stack([x for
  x, _ in history])` over scalar iterates is a `(1, m)` row vector, so
  `R[:, :-1]` is `(1, m-1)` and the extrapolant comes back as a shape-`(1,)`
  array; `solve_for` needs a scalar and raises `TypeError: only 0-dimensional
  arrays can be converted to Python scalars`. The counts above are from the
  most favourable reading — the scalar extracted from the array — so the
  finding is not an artefact of a strict reading of the snippet. §37 is
  pseudocode that was never run.

  Aitken's delta-squared is not measured here and the reason is structural
  rather than a gap: loop 1 is three-dimensional and loop 2 is
  two-dimensional, and the scalar extrapolant is undefined on a vector
  sequence without first choosing a component to extrapolate. Any such choice
  is a decision the spec does not make.

  Recorded rather than built, and deliberately not built: implementing §37 to
  close a checklist entry would degrade the product to make a document agree
  with itself.

  **The measurement was a script and is now a gate.** The numbers reproduce
  exactly (`python3 scripts/measure_loop_convergence.py`, deterministic across
  runs) but nothing in the tree pinned them, so a change to the damping factor
  or the loop structure could move them silently — the weakest part of this
  entry as it first stood.
  `test_both_feedback_loops_converge_in_the_iteration_count_this_tree_pins`
  pins both counts, keyed by variable rather than by
  index (Tarjan's traversal order is an artefact, and an index-based assertion
  keeps passing after the loop it meant to check is deleted, as long as another
  loop takes its place). It asserts the exact pair, not a bound: "under 50
  turns" would pass a solver needing 49 where this one needs 38, which is the
  1.3x regression the entry exists to warn about. Canaried by moving the
  damping factor from 0.5 to 0.45 — **both** counts moved, 38→45 and 36→41,
  which is why the test asserts the pair rather than one number and a spare.

  What is still not pinned is the comparison — a future reader who implements
  §37 will get no test failure telling them they have made both loops slower,
  which is exactly the failure this entry exists to warn about. Pinning it
  would mean shipping an Anderson implementation solely so a test can assert
  it is worse, and that trade is not worth making for a mechanism the spec
  itself never ran. What the gate buys is that the baseline the comparison is
  against cannot drift unnoticed, which is the half of the problem that was
  actually load-bearing.

- **Two quantities are declared twice, in `config/` and in the graph, with
  different values and nothing reconciling them.** Found on 2026-10-16 by
  cross-checking `ScenarioParameters` against `config.default.yaml`, and it is
  the same defect the plan-level sweep was looking for, one layer down.

  **`value_of_lost_load_usd_per_mwh` is `2000.0`; `voll_usd_per_mwh` is
  `5000.0`.** Same quantity, same unit, both declared, both read, no join.
  `config.market` feeds `market/stages.py`, which prices every hour the system
  sheds load; the graph's node feeds `reliability_cost_usd` by
  `unserved_energy_gwh * 1000 * voll_usd_per_mwh`. So the market layer prices a
  shortfall at 2,000 and the graph's reliability accounting prices it at 5,000
  — a **2.5x** disagreement about what an unserved megawatt-hour is worth, in
  one product, with each number internally consistent. This is the
  rate-stated-in-one-place defect the MeGuard lesson names: each figure is
  right on its own line and nothing compares the lines.

  The graph's value is the weaker of the two on its own evidence. Its node is
  `status: to_build`, so no builder writes it and nothing sources it, while the
  config value carries `value_of_lost_load_basis:
  config.market.value_of_lost_load_usd_per_mwh` and a comment recording that
  2,000 is the figure the determinism job has used since it was written. So the
  graph's 5,000 is the unsourced one. What it reaches is `reliability_cost_usd`
  — a derived node with no report reading it today, so the disagreement is
  visible through `alea prg summary` and the propagation payload rather than in
  a published figure. That is the only reason this is a finding and not an
  incident: the two numbers have not yet met in one document, and the entry
  exists so they do not.

  **`hydrogen_export_twh_per_year` is declared twice too, and there the two
  consumers disagree about what the number is *for*.** `sector.hydrogen` reads
  `config.hydrogen_export_twh_per_year` and builds an export load into the
  sector-coupled network; `whatif/apply.py` reads
  `params.hydrogen_export_twh_per_year` and adds an `h2_export` load to the
  network it is perturbing. Both default to `0.0`, so nothing is wrong today —
  but the moment one is moved, the sector build and the what-if solve export
  different volumes from the same declared quantity, and the engine's
  `engine_fields_unreached()` register counts this knob as one the graph cannot
  speak to. The graph's nearest node is `hydrogen_production_kt_per_year`
  (`kt/year`, default 50), which is a *related* quantity and not the same one —
  a country produces hydrogen and exports some of it — so the graph can state
  the system's hydrogen volume without being able to state the export it is
  asked to carry.

  **Not built, and the reason is that the join is a decision.** There is no
  mechanical reconciliation available: the two files name the quantity
  differently (`value_of_lost_load_usd_per_mwh` against `voll_usd_per_mwh`),
  they live in different layers by design — `config/` is the deployment's
  settings and `config/prg.yaml` is the library of physical and policy
  relations — and a name-identical sweep finds **zero** overlaps between the
  two files' numeric leaves. So the fix is not an adapter. It is either (a)
  make the graph the single source and have the config read its default from
  it, which makes a deployment setting depend on a library, or (b) record the
  config value as the graph node's `default` and delete the node's own, which
  makes the library depend on the deployment. Both are real modelling choices
  about which layer owns a policy number, and choosing one without the user is
  the same mistake as inventing a referent for `linearity`. Recorded so the
  2.5x is not rediscovered as a report discrepancy.

  **Closed 2026-10-16, and the closing found two defects one level down.**

  The register itself was built — `CROSS_LAYER_QUANTITIES` declares the two
  quantities, `cross_layer_disagreements` compares them, and
  `cross_layer_report` serves the result — and **neither door rendered it**.
  `graph_summary` has carried `cross_layer` and `catalog` since they were
  written, and `alea prg summary` printed neither, nor did `PrgSummaryOut` carry
  either field. That is the declared-is-not-produced class *on the registers
  built to catch it*: the check ran, was correct, was tested, and no reader
  could see its verdict. Both doors now render it, and the CLI line carries both
  measured values rather than only the sentence describing them.

  **The prose was asserting numbers nothing compared.** Every `note` in the
  register quotes its pair in words — "config is 2000.0 and the graph is
  5000.0", "a 2.5x disagreement" — and the payload carried the sentence and
  neither number, so moving either side would leave the register asserting the
  old figure forever. `cross_layer_report` now carries `config_value`,
  `graph_value` and the derived `ratio`, and
  `test_every_cross_layer_note_quotes_the_values_the_payload_holds` requires
  every note to *name* both measured values as whole numbers — positively, not
  by rejecting a blocklist of forbidden figures, because a blocklist passes when
  the note quotes a third number neither side holds. Canaried: mutating 5000.0
  to 4500.0 in the note fails the gate.

  **A third defect surfaced from the API test, and it was not about this
  register.** `prg/catalog.py`, `prg/graph.py` and `prg/library.py` did
  `from alea.config.paths import repo_root`, binding the function object at
  import time. Every fixture in the suite redirects a scratch tree by patching
  `paths.repo_root` — the documented seam, which `paths.resolve` honours because
  it calls the name as a module global — so those three modules never saw the
  patch and read the *real* repository. `test_the_summary_serves_the_catalog_join`
  was the first test to notice, and it noticed as an ordering dependence:
  passing alone, failing after another test had patched. All three now call
  `paths.repo_root()`, so the module attribute is what is consulted, and a
  scratch tree is a scratch tree for every reader.

### Closed since this list was written

**Six layer-5 gates ran and passed while the register counted them as
unpromised, and the first one was blind.** `08-layer5-whatif.md` §10's exit
criteria recorded their gates in prose — `Integration test`, `Three key tests`,
`Recorded timing`, `Recorded practice` — and the register reads a backticked
`test_` name or nothing. Naming the six turned `--check` red with six uncanaried
gates on the spot, the same way the route-inventory cell did:

    promised gates: 119   verified: 113
      unimplemented: 0
      uncanaried:    6

The six are now named in the plan and canaried in
`tests/ci/canaries/test_whatif_layer5_gates.py`; `--check` reports **119/119**.

One of the six was a real defect, not a bookkeeping gap.
`test_the_cost_emissions_frontier_is_computed` claimed *"a real solve per
point"* in its docstring and then passed `solve_fn=_CountingSolve()` — a
stand-in that counts calls and computes nothing — while checking the emissions
axis with `notna()` and `>= 0.0`. Both are shape predicates: they accept a
zeroed axis and three identical costs. The canary planted exactly the defect the
docstring promised to catch, and it went **MISSED**. The tell was measurable in
one run — the no-op solver returned `cost=14400.0, emissions=456.0` for all
three carbon prices, where the real solve returns `17857.76 / 74407.33 /
187506.47`. The gate was the finding, so it was fixed rather than canaried
around: the stand-in is gone, and it now asserts that the cost axis is
`nunique() == 3` and monotonic in the carbon price, and that the emissions axis
is strictly positive. The re-probe fires.

Emissions are deliberately *not* asserted to move with the carbon price. They
are flat (`565.495697` at all three prices) and that is the correct behaviour for
this fixture — a carbon price re-prices the objective, it does not rebuild the
dispatch. Asserting the intuitive relationship would have written a second
blind gate in place of the first.

**The route-inventory gate had no canary, and a stale exit-criteria cell was
hiding it.** `11-layer8-api.md` §9's criterion 9 — *a route inventory matches the
specification's endpoint table* — had its Gate column reading `Manual, once`
while `test_the_route_inventory_sees_every_spec_endpoint` had existed in
`tests/ci/test_api_layer8.py` since the layer was built. Correcting the cell to
name the gate turned `scripts/gate_register.py --check` red on the spot:

    promised gates: 113   verified: 112
      uncanaried:    1
      UNCANARIED:
        test_the_route_inventory_sees_every_spec_endpoint

That is the register working as designed and worth stating plainly, because the
alternative reading is that the edit *broke* something. It did not: the cell was
the only place the gate was recorded, so nothing had ever asked whether it could
fail. `test_the_inventory_canaries_against_a_known_route` is canary-*shaped* and
sits in the same file — it calls `assert_inventory`, which checks the walk
against `GET /api/v1/health` before trusting the total — but it drives the
production function rather than planting a defect, so it is a gate, not a
canary, and the register classifies by behaviour for exactly this reason.

`tests/ci/canaries/test_api_inventory_gate.py` closes it with two canaries on
disjoint files and disjoint mutations. The first blinds the unwrap — returning
early from `_walk`'s `original_router` branch — and is caught by
`assert_inventory` inside `create_app`, which reports *5 routes* instead of 65
and names the missing known route. That ordering is deliberate and the canary
documents it: the guard runs before the gate's own comparison so a broken walk
is caught before its total is read. The second renames `/capture-rates` to
`/capture_rate`, which leaves the walk intact, the route count unchanged and
`assert_every_router_mounted` satisfied — so the only thing that can notice is
the comparison against §3.1's table, which is the half the first canary never
reaches. Measured, both mutations fail the gate; both restore clean.

Criterion 1's cell was corrected at the same time. It read `Route inventory
test`, a description rather than a gate name, and criterion 1 is satisfied by the
same function criterion 9 names.

**`ParameterNode.initial` reaches a door, and the first reason written for it
was false.** The field is where a feedback loop starts iterating, declared on
the five loop variables, and until 2026-10-16 no door served it —
`ParameterOut` carried the node's `default` and `range` but not this, so a
client rebuilding the declared graph from `GET /prg/parameters/{id}` could not
tell a loop variable with a starting point from one falling back to its range
midpoint. It is served now, and the test that asserted the *absent* `default`
on `equilibrium_demand_twh` asserts the present `initial` beside it — asserting
only the absence left the payload free to serve neither, which is what it did.

**The reason I first wrote for serving it was wrong, and measurement said so.**
I claimed `initial` was the invisible baseline of a propagation's `changed`
delta, so a client holding only the delta could not interpret it. That is true
of a bare `ParameterGraph.propagate`, where `changed[name] = value - seed` and
the seed is `initial` or a range midpoint: measured, moving
`capture_price_usd_per_mwh`'s `initial` from 60 to 100 moves that `changed`
entry from −16.08 to −56.08, exactly the 40 the seed moved. But **no door reads
that field**. The served delta comes from `propagate_change`, which diffs two
*converged* fixed points, and the loop solver is a contraction — so the seed
washes out. Measured across five seed perturbations (capture +40, demand +5,
tariff −20, and all three): the served delta is identical to nine significant
figures (`23.6486486606` vs `23.648648453`, a convergence-tolerance
difference) and the iteration counts do not move from 37 and 34. A docstring
resting on the first reason would have been a false explanation of a real
field, which is worse than no explanation because the reason is what the next
reader reuses.

The build for that wrong reason was written and reverted — a `seeds` field on
`PropagationResult`, populated at both construction sites. It would have added
a *new* unread field to explain an unread one, and the measurement above is why
it is not in the tree. `graph.py` is byte-identical to its previous revision.

`initial` is served as the declaration it is, not as the explanation of a
delta: `float | None`, `None` on the 83 nodes outside every loop.

**`Equation.reference` is read.** Nine of the thirty-nine equations declare a
citation — IEA/NEA on `lcoe_definition`, Wright's law on `learning_curve`,
WHO AirQ+ on `premature_deaths_definition`, and six more — and the field was
parsed, validated and read by **nothing**: no report, no route, no CLI line.
The library's provenance was invisible to every caller, which is the
"declared is not produced" shape this document keeps recording. The reader is
`equation_report`, which now returns an `EquationRow` carrying the citation
beside the rendering, and it reaches four doors: `GET /prg/equations`,
`GET /prg/equations/{id}`, the `equations` list inside `GET /prg/graph`, and
`alea prg equations`.

The field could not simply be appended to the tuple the function returned.
Three callers unpacked it positionally, so a fourth element would have made
each raise `ValueError` — loud, which is the good failure, but the same change
made by a caller that sliced (`row[:3]`) would have dropped the citation in
silence, which is the defect the field exists to close. A `NamedTuple` keeps
the positional contract while making the citation reachable by name.

`None` is carried on the other thirty rather than an empty string: "no external
source" and "a source that rendered blank" are different findings, and a report
that printed a blank citation column would read as thirty missing citations.
The CLI prints the line only where a citation exists. Both halves are tested,
and canaried by blinding the reader — the CLI test fired as well as the service
test, so the reader is asserted at a door and not only at the function.

**The energy balance is measured and reaches a door.** It was listed here as
correctly *unwired*, on the grounds that `check_energy_balance` false-positives
on any network carrying a link. That ground was right and the conclusion was
wrong: the false positive was a **bug in the check**, not a reason to leave it
uncalled. The loss term summed `network.lines_t` only, so a link's retained
energy went unaccounted — measured on a two-bus link fixture, an 11.1% residual
on a 0.9 link and 200% on a COP-3 one, every one a *correct* dispatch refused.
Sector-coupled networks transfer by link, so the check refused most of what this
project builds, which is why no one had wired it and why the docstring's
1.6% figure was an underestimate of its own defect.

The sum now covers both branch tables, and the two signs are asserted
separately: a link below 1 absorbs the difference (`p0 + p1 > 0`) and a
heat-pump link above 1 creates it (`p0 + p1 < 0`), and both close
`generation - load - losses == 0`. A fix that special-cased the lossy direction
would pass one row and fail the other.

**And the one path that reported a balance did not check it.** The check is
live: `solve_dispatch` calls it, and `planning/service.py` and
`publish/stages.py` reach that, so a planning run refuses a residual over the
tolerance. But the what-if engine's own `_default_solve` calls
`network.optimize` directly and never goes through `solve_dispatch` — so every
`ScenarioResult` in the tree was the one result asserting a balance no code had
verified. The measurement is now split from the refusal: `balance_measurement`
returns the numbers, `check_energy_balance` raises on them, and `extract`
records the residual on the result because that is the last place the network
still exists (a `ScenarioResult` holds no network — it has to be serialisable
into a content-addressed cache entry — so a residual not taken at extraction can
never be recovered). `whatif scenario` warns when it is non-zero and `prg audit`
reports it against a stored result.

The field is `float | None` and not `float`. `extract` legally accepts an
*unsolved* network and reports `None` prices for one, so `0.0` would be a claim
that the balance was checked and closed. `None` says it was never measured,
which is what an unsolved network is. The first version defaulted to `0.0` and
raised on an unsolved network instead; ten tests that extract an unsolved
fixture caught it, and they were right.

**Line outages, and the mechanism the tree's own doc gets wrong.** The spec
states a line-outage dimension three ways (`docs/what-if-line-loss.md` §1.1:
`line_active`, `line_capacity_factor`, `line_outage_start`/`_end`). All three
are one mechanism here — a per-snapshot rating — because the obvious one does
not work. Probed on pypsa 1.4.0:

| spelling | declared as | measured |
|---|---|---|
| `lines_t.active = [T,T,F,F]` | **static only** | optimises `ok`, sends 50 MW through the line on the snapshots marked inactive. Accepted, stored, **never read**. |
| `lines_t.s_max_pu = [1,1,0,0]` | static or series | honoured exactly: 0 MW across the window, load served by shedding. |

`docs/modelling-alg-3.md:427` prescribes `n.lines.active = False` as *the*
implementation — and so do `docs/modelling-alg-2.md:39` and `docs/params.md:412`
for `line_active` and `line_outage_start`. The dynamic table is a silent no-op —
the worst of the three possible behaviours, because the solve returns and the
answer looks like an answer. So a windowed outage is a rating of zero, a
permanent one is the same with no window, and `line_capacity_factor` is `0.5` on
the same field.

The two failure modes are different and belong to different mechanisms, which
an earlier draft of this code got wrong in four docstrings. With no injector on
an islanded bus: `s_max_pu = 0` returns `status='warning' (infeasible)` and the
engine's `_default_solve` raises `SolveError`; the static `lines.active = False`
raises linopy's `ValueError: Empty LHS with non-zero RHS in nodal balance
constraint`. A rating keeps the variable and forces it, so the failure is
infeasibility rather than a malformed constraint. The canary that disabled the
islanding refusal is what surfaced it — it failed with `SolveError` where the
docstring predicted the linopy error.

`islands_without_generation` counts **load shedding as supply**, deliberately.
`docs/what-if-line-loss.md` §2.3 models shedding as a VoLL generator so the
optimiser minimises unserved energy; a check that excluded it would refuse
*every* island, forbidding the measurement and calling it validation. The
refusal is for an island with no injector at all, where the solver's answer
names neither the line nor the bus.

**The door was the part that mattered, and it caught a defect the unit tests
could not.** `--outage LINE[:FACTOR][@START..END]` on `alea whatif scenario`
builds the set and passes it to `solve_from_prg`, which carries it onto the
parameters through `with_value` (re-validated, not `model_copy`). Without the
option the field would be declared, validated, applied by `apply_parameters`,
and reachable from nothing but a direct Python call — the declared-is-not-produced
class, on the parameter that models the spec's headline scenario.

Running it end-to-end refused a *correct* window:
`--outage L1@2030-01-01T01:00..2030-01-01T02:00` matched no snapshot on a
network whose labels are plainly `2030-01-01 01:00:00`. Pandas separates date
from time with a space, ISO-8601 — what a user types, what the CLI documents,
what `datetime` prints — with `T`, and the string comparison the module
docstring defended as "the ordering the labels already carry" never matched.
Both sides now go through `_iso`. Every unit test passed throughout, because
every one of them spelled the bound the way the implementation happened to want;
the two new gates spell it the way a user does, and the canary that reverts
`_iso` fails them with `matches none of the network's 6 snapshots`.

Measured through the CLI on a 2030+2040 base: objective 11,161 with no outage;
a two-hour 2030 window takes it to 908,161 with unserved fraction 0.269 — which
is 2 of the horizon's 7.44 demand-weighted years, i.e. the parameter does
exactly what the growth model says; `L1:0.5` gives 657,330 and a full-horizon
`L1` gives 3,348,330, and all four cache keys differ.

**The §43 API surface and the §45 client.** The route module carried five
routes; §43 names thirteen operations. Twelve were added, the client was
written against them, and the client's tests — which drive the real app through
`httpx.ASGITransport` rather than a mock, because a client's defects are all
path strings and payload shapes that a mock cannot see — found two route
defects that no unit test had:

`/consistency/report` called `check_scenario({})`. A propagation needs a value
for every underived parameter, so **every call was a 422 naming the graph's own
defaults as missing inputs**; the route could not answer at all. It now seeds
them, which is what "the shipped default scenario" means.

`/conflicts/resolve` applied `corrections[0]` blindly. The ranking is by
relative move, so the smallest proportional correction to an over-determined
`marginal_cost` on this graph is a **negative fuel price** — resolving one
contradiction by producing a scenario the graph refuses. It now takes the first
correction that stays inside its declared range, which is the field the
detector was already recording and no reader was acting on.

**Three registers in one payload disagreed about one parameter.** `/translate`
merged two different findings into `untranslated`: "no knob carries this" (a
modelling gap) and "a knob carries it, but this route had no network to form
the ratio against" (an API limitation). Merged, the payload named
`fuel_price_usd_per_mwh` as both reaching and not reaching a knob, while its own
`coverage` — computed from the graph — counted it as reaching one. The route's
docstring already said the two were different findings; it then merged them.
`deferred` is now its own field, the three registers are asserted pairwise
disjoint, and the canary that re-merges them names the parameter.

**`derived` in the summary was the `order()`-vs-`computed()` defect again.** The
field is the derived half of the role partition and sat beside `endogenous`, so
it had to count the nodes carrying the derived role; it counted `order()`, the
topological *sequence*, which omits the five feedback-loop variables. The
payload therefore stated 28 derived against 52 exogenous and 3 endogenous — 83
of the 88 parameters it reports in the same response. A client cannot reconcile
that, and an inequality assertion (`derived + endogenous < parameters`) passed
throughout, because an undercount that still leaves room under the total is
exactly what an inequality cannot catch. Both sites now assert the partition
*closes*, counted from the graph rather than pinned.

**The load is cached, and the cache is identity-keyed.** Measured before
building it: a propagation is 6.5 ms and an incremental one 6.1 ms — the loop
solve dominates both — while `yaml.safe_load` is 73.0 ms of a 73.4 ms load. So
§30's propagation cache targets the cheap half, and the parse is what the
workload asks for. The key is the resolved path, mtime and size: the same
identity check `make` uses. Its limit is stated rather than hidden — a rewrite
preserving both would be served stale — and the test asserts both directions,
that an unchanged file is not re-parsed and that an edit is observed.

**The twelve routes were shipped without the value-contract gate being run
against them, and it was failing.** `test_values_carry_basis` enumerates every
response-reachable schema's numeric fields and refuses a bare quantity — a
`capacity_mw: float` where a `ValueOut` belongs. The routes added nine response
models, each carrying the graph's own arithmetic as plain floats, and the gate
listed all nine the first time it was run. It was not run because the routes
were verified against the *PRG* suites, and this gate lives in the Layer 8
suite: a check whose jurisdiction is the whole API surface was scoped, in
practice, to the files the change happened to touch. The fix is the one the
gate's own design already provides — per-model exemptions in
`PRG_EXACT_FIELDS`, which the test asserts are live, so a rename cannot make an
exemption absorb a new field. Canaried by planting a stale field name.

**The spec's §44 request examples do not run against this API, and that is
recorded rather than worked around.** `docs/alea_prg.md` §43 lists fourteen
endpoints; all fourteen are mounted. §44 then shows the bodies, and every one
of them is wrong in the same two ways:

| §44 writes | the service takes | why |
|---|---|---|
| `{"parameters": {...}}` | `{"set": {...}}` | The model forbids extra inputs, so the spec's body is a 422 naming `body.parameters`. |
| `carbon_price`, `coal_retirement_schedule`, `renewable_target`, `demand_growth_rate` | none of these is a node | They are from `how_prg_works.md` §5's illustrative trace, which this document's own preamble already says is intent and not implementation. The graph's names are `carbon_price_usd_per_tco2`, `demand_growth`, and there is no retirement-schedule or renewable-target node at all. |

So a client written from §44 verbatim does not work, and the envelope is a
decision the code made and the spec did not: `set` is what every
parameter-accepting route takes, `ConsistencyRequest` and `ConflictRequest`
share it deliberately so a caller does not assemble a second payload to ask
the follow-up question. The spec's `parameters` was not adopted because the
four names under it are the illustrative ones — adopting the envelope would
have made a body that still fails, one field later. Recorded here so the next
reader does not read §44 as a contract and conclude the routes are broken.

**`Equation.linearity` is closed, and not by giving the field a reader.** The
entry above it was right that four oracles disagree on four disjoint sets of
equations — that measurement stands. What it got wrong was the conclusion that
the disagreement was the finding. The finding is *what the four oracles are
measuring*, and once stated plainly it is not ambiguous: **linearity is a
property of a variable, not of an equation.** `x ** 2` is nonlinear in `x` and
constant in `y`; an equation has no linearity of its own, so a per-equation
`linear`/`nonlinear` column has no referent to be right or wrong about. That is
why no reading reproduced the declared column and why `mixed` appears in it
zero times — it is a hand-entered label, not a classification.

The question underneath it does have an answer, and the answer decides the
solve. Every one of the 33 determined variables is **affine in its own
unknown** — measured, zero exceptions — so each derivation's root is arithmetic
(`-b/a`) and the bracket search is a fallback that the shipped library never
takes. `solution_method` already tracked that structure honestly (28 `direct`,
5 `iterative`, and the five are exactly the loop variables); `linearity` tracked
nothing. The replacement is a computable per-variable register:

- `dsl.linearity_in(expression, symbol)` — structural, so `a * a / a` is
  nonlinear although it equals `a`. It reads the tree rather than
  differentiating, because a symbolic simplification would make the answer
  depend on which identities the simplifier happens to know.
- `dsl.linear_coefficients(expression, symbol)` — the `(c, r)` of `c*x + r`,
  which is what makes `solve_affine` possible and is testable as an identity:
  `c*x + r` reconstructs the expression at every point sampled.
- `ParameterGraph.linearity()` and `solve_paths()` — per determined variable,
  `linear`/`nonlinear` and `affine`/`numeric`. Served on the graph summary as
  `PrgSummaryOut.linearity`, defaulting to `{}` so a payload stored before the
  register existed is still valid.

**The exact solve exposed a latent bug, and that is the part worth keeping.**
`_range_excursions` was written only inside `_widen` — the bracket-widening
path — so "the answer left its declared range" and "the numeric search had to
leave the bracket to find it" were the same fact. They coincide only while
every solve is numeric. Adding the exact path would have made the register go
**blind**: a solve that returns a value outside the declared range without ever
widening a bracket would have reported nothing. Four tests failed on the first
run and every one of them was pointing at this. The fix is `_note_excursion`,
called on both paths and comparing the answer against the declared range, with a
non-finite value excluded — a failed solve is an arithmetic fault and filing it
as a scenario finding is the other half of the same conflation.

The `feedback.py` half was written and **reverted**. The loop solver's refusal
to return a root outside its bracket is behaviour three tests depend on, and
whether a loop should take the exact path is a product decision about what a
feedback iteration means, not a missing optimisation. `graph.py` and
`feedback.py` both converge unchanged — 38 and 36 turns — and the derived values
are identical to the previous revision to 14 significant figures.

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

**A direction field nothing reads is a declaration, not a relation.**
`RelationshipEdge.direction` is declared on all 88 edges, enum-validated
against `forward`/`backward`/`bidirectional`, and required by `params-prg1.md`
§3.3 — "the PRG must encode **causality**". The index behind
`edges_from`/`edges_into` was built from the `source` and `target` *fields* and
ignored it, so a `backward` edge was indexed exactly as a forward one and the
field was inert. Every shipped edge is `forward`, which is the whole reason the
defect was invisible: a declaration no instance exercises is a declaration
nothing tests. Flipping one edge in a copy of the document was the entire
diagnosis — `edges_from(source)` still contained it. The fix indexes by the
declared direction, and `bidirectional` cannot be refused instead: the spec
names `Endogenous ↔ Endogenous` ("capacity and dispatch are jointly determined
by the optimisation") as a legitimate coupling, so a value the graph forbids
would be a coupling the spec requires. The test that pins it is parametrised
over the three values and matches the edge *by identity* — a check over the set
of `source` names would have passed on the unfixed index, because dozens of
other edges touch those two parameters.

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
members, which is the one place the uncertainty most obviously lands.

**And it is not a count of anything.** This is the third site where `order()`
was read as "the derived parameters" and the second where the reader was a
payload. `audit.py` partitioned a scenario's parameters into checked and skipped
over `set(g.order())`, so when `equilibrium_demand_twh` became the tariff loop's
variable it left the sequence and entered *neither* set — the partition silently
stopped covering the graph. `service.graph_summary` counted it as `derived`, and
the response then stated 83 of its own 88 parameters. `computed()` is
`frozenset(self._determiner) | self._loop_variables` and is the set both of them
meant. The rule: `order()` is a *sequence*, and a sequence is not a set with an
ordering — anywhere a set is wanted, it is the wrong object, and it fails by
omission, which reads as a smaller number rather than as an error.

**And `not is_settable` is not "derived" either, which the fix above taught the
hard way.** That advice stood here until 2026-10-15, when the endogenous fleet
layer landed and the predicate silently became a superset: a parameter the
optimiser *chooses* is also not settable, and the uncertainty register was
folding three solved fleet nodes into a closure that reports what an equation
computed. `is_settable` answers "may the user move this" and collapses three
answers — an equation fixes it, a loop computes it, the solve determines it.
A caller that needs the *set* must say which: `graph.role(name) is Role.DERIVED`
for the first, `graph.endogenous()` for the third. The general shape is the one
this document keeps returning to: a predicate widened by a change elsewhere
stays green everywhere it is read, and the readers that assumed the old
narrower meaning are exactly the ones no test names.

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

**A refusal that names a lever must name one that moves something.** The
endogenous refusal told a reader to move "the carbon price, the demand, the
build target". The first two reach a solve; `vre_capacity_target_mw` reaches
neither an engine knob nor an inequality — it is a settable parameter the graph
carries and no path consumes, so the third is a lever a reader pulls and sees
nothing move. The list is now derived from `translated()` and
`bound_parameter_names()`, which are the two registers that decide it.

**And the gate written for it was blind to the bug it was written for.** The
first version asked whether every *name* appearing in the message was a real
lever — and the defect was prose ("the build target"), which matches no
parameter name at all, so the check passed on an empty list. The canary caught
this: reverting to the original text made the test fail with "the refusal names
no lever at all", which is the wrong reason, and a canary that fails for the
wrong reason is a finding about the gate. The assertion now pins the message's
lever list *equal* to the computed set, which fails on prose and on a stale
hand-written list alike. This is the subset rule from the other side: a
predicate over the *recognised* form of a thing cannot see the thing written in
a form it does not recognise, and prose is the form a message is most likely to
take.

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

**The gate caught the field added to satisfy it.** `PrgSummaryOut.endogenous`
shipped as a bare `int` — the count of nodes the optimiser chooses, added
beside `derived` — and `test_values_carry_basis` failed on it immediately,
naming the model and the field. `derived` was already in
`NON_QUANTITY_FIELDS` for the same reason and the sibling was simply forgotten;
the fix is one name in that set. Worth recording because the gate's value here
is not the fix but the *timing*: the count of a role is not a modelled
quantity, and the only reason it did not ship as one is that a check written
for a different purpose enumerated every numeric field on every response model.
A gate earns its keep by catching the change its author did not think was in
its jurisdiction.

**A closure over the declared edge set is not the closure over `affects`.**
The specification's incremental propagator marks dirty with
`networkx.descendants` over the declared graph. That is a different relation:
it disagrees with the `affects` closure on 27 of the graph's 52 settable
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
was declared on all 88 edges, enum-checked on every load, exported in the model
— and read by nothing, so the spec's three tiers ("inviolable", "usually true",
"reported correlation") were a comment the loader happened to accept. The
symptom of the class is that nothing fails: a graph declaring every edge
`informational` and one declaring every edge `hard` behave identically, and the
difference is only visible to a person reading the YAML. The fix is not to read
the field somewhere convenient but to make it *decide* something — here, whether
a failure blocks — and then to gate on it, canaried in both directions.

**A property of the equation cannot be read off an edge.** The strength is
declared per edge, and 27 of the 39 equations are cited by more than one, so
"the strength of this equation" was ambiguous: a reader taking it from an edge
got whichever edge they read first. The constructor now refuses a document whose
edges disagree about one, rather than resolving it by an arbitrary pick — the
same discipline as `GraphError` for a node determined by two equations. A
strength that depends on iteration order is not a declared property.

**An equation with no edge is still an equation, and the count has to say so.**
`strength_counts` iterated the edge-derived `_strength` dict while `strength_of`
and the propagation both read it with a `hard` default — so `firm_capacity_definition`,
which no edge cites, was counted as no equation at all and the register read 37
tiers over 39 equations. Two readers of one field disagreed by exactly the number
of edge-less equations, and the register was the wrong one. It now counts by
equation through `strength_of`, which is the single reader the other two use.

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

**§24's tolerance table is not honoured, and the graph is stricter than the
spec — which is the safe direction, recorded because the table is what a
reader would expect to find implemented.** §24 assigns a tolerance by equation
*type*: 1e-6 for a hard equality, 1e-3 for an accounting identity, 1e-2 for an
economic relationship or a learning curve, 5e-2 for a health impact, 1e-1 for
employment. The graph declares its own, per equation, and every one is at or
below the spec's value: 27 equations at 1e-9, six at 1e-8, six at 1e-6. The
`1e-1` the spec allows an employment identity is nowhere in the document —
`direct_jobs_definition` carries 1e-9.

Measured on the raw `graph.consistency()` path
(`python3 scripts/measure_tolerance_sensitivity.py`) — the graph's own defaults,
propagated once, then each settable parameter moved by ±0.1% and the set
re-checked without re-propagating, 104 draws. **30 of the 39 equations report
a violation**, and the worst relative residual on the top of the list is
1.93e-3 (`cfads_definition`), with a dozen more at 1.00e-3:

| equation | system | declared tolerance | worst relative residual |
|---|---|---|---|
| `cfads_definition` | financial | 1e-9 | 1.93e-3 |
| `premature_deaths_definition` | health | 1e-9 | 1.00e-3 |
| `direct_jobs_definition` | employment | 1e-9 | 1.00e-3 |
| `learning_curve` | learning | 1e-9 | 1.00e-3 |
| `carbon_cost` | emissions | 1e-9 | 1.00e-3 |
| `emissions_definition` | carbon_trajectory | 1e-9 | 1.00e-3 |
| `marginal_cost` | cost_accounting | 1e-9 | 6.15e-4 |
| `lcoe_definition` | cost_accounting | 1e-9 | 3.84e-4 |

The residual tracks the perturbation — a 0.1% move produces a ~1e-3 relative
residual — which is the point rather than a coincidence. **A spec-faithful
implementation would call most of these consistent.** §24 allows 5e-2 for a
health impact, 1e-1 for employment, 1e-2 for a learning curve, and every
residual above is under all three, so the table's answer to this scenario is
"consistent" while the shipped graph's answer is thirty violations.

That is not a defect to fix by loosening the tolerances, and the distinction
matters: the graph's tolerances are what make it a *gate* rather than a
formality, and the equations flagging here are flagging correctly — a
parameter was moved and the identity no longer holds to 1e-9. What the finding
says is that §24's table describes a different graph from the one that
shipped. The spec's numbers are sized for inputs that are *reported figures*
with rounding error; this graph's inputs are declared parameters, and its
identities are exact arithmetic over them. Applying §24 as written would make
`consistency()` accept a 10% error in an employment identity.

**Door-reachability is limited, and saying so is part of the finding.**
`/consistency/check`, `/consistency/report` and both conflict routes propagate
before they check (`check_scenario` calls `g.propagate` first — read, not
assumed), and a propagation re-derives every identity from its inputs, so a
caller arriving through a route sees the *propagated* residuals and not these.
The raw path is what a direct `consistency()` call reaches, which is how a
test reaches it. So this is real but narrow: it is a fact about the
non-propagated path, and no current route reports it. Recorded at that
strength and no stronger.

The tolerance values are also not configurable from the document in the way
§24's YAML block shows — `tolerances:` is not a key `load_graph` reads
(verified: no occurrence anywhere under `src/alea/prg/`), and a document
carrying one would be accepted and ignored. Per-equation `tolerance` on the
equation is the supported spelling, and it is what all 39 use.

**§12's `unit_check` is carried and read, and a document written to the spec's
own example now loads.** The spec declares `unit_check: bool = True` on every
equation and shows it in §12's YAML, and the model did not carry it. Because
`Equation` sets `extra="forbid"`, a document written to the spec's example was
**refused** at load with `extra_forbidden` — so this was not a missing feature
but a document the service would not accept, which is the stronger defect and
the reason it was fixed rather than recorded.

All three halves are wired. The field loads; it defaults to `True`, so no
equation's meaning changed; and `False` is **read** — `check_graph` puts the
equation's id in `UnitReport.exempt`, and `undecidable` excludes it. The three
are separate on purpose. An exemption is a declaration that the walk cannot
decide this relation, which is a different finding from "nobody has annotated
this", and folding the two would let a flag absorb a newly-undecidable
equation. It is also not a *skip*: every equation is still walked and still
reported, so an equation that later became decidable cannot hide behind a flag
nobody revisited. The count is announced rather than silently shrinking — the
summary says "N are exempt by declaration", and `UnitReportOut.exempt` carries
the list so a client that saw `undecidable` fall has the payload explaining it.

The shipped graph declares no exemption (`exempt == ()`, and the test asserts
it), which is the honest state: the walk decides all 39 equations and reports
8 inconsistent. The eight are *findings*, not undecidable relations, and marking
them exempt would be the flag used to hide what the check exists to say.

`alea prg units` prints exemptions dim and does not fail on them — the gate
still exits 1 on `inconsistent` only. Canaried by removing the field from the
model, which reproduced the exact `extra_forbidden` refusal the test documents,
and the guard was re-run by exact node id rather than through `-k`, for the
reason recorded above it.

## What the coverage sweep found, and the predicate that lied twice

Every plan in `docs/plans/` names its gates, and a register of "which named
gates exist" is exactly the kind of check this page keeps recording as absent.
So one was written on 2026-10-16, and it was wrong twice before it was right.

**The first predicate enumerated one of the two spellings.** `grep -r "def
$gate" tests/` reported **40 of 115** plan gates missing. It matched the
function name, but the plans cite gates in docstrings and the tests are free to
be named for what they assert — `test_clearing_deterministic` lives in
`test_market_layer3.py:321` as a docstring citation, not a function name.
Matching the bare name instead reported **3**, and all three exist under other
names:

| plan gate | where it actually lives |
|---|---|
| `test_raw_is_immutable` | `tests/ci/canaries/test_raw_immutability.py` — `test_edited_bytes_under_a_checksum_directory_are_refused` |
| `test_no_bare_unit_columns` | `tests/ci/test_units_columns.py` — the module's own rule check |
| `test_artefact_round_trip` | `tests/ci/test_loading.py:359`, `test_capacity_section.py:232`, and five more read `write_artefact` back through `read_artefact` |

This is the same bug as the `href="/…"`-only internal-link checker: a predicate
for "every X" that recognises one way of writing X, reporting a false negative
at a rate that makes the register useless. The lesson generalises past this
sweep — **a coverage check over a naming convention must be canaried against a
known-present instance before its count is believed**, because 40 missing looks
like a finding and 3 missing looks like a finding, and only the second was one.

**What the corrected sweep says.** 112 of 115 gates are cited somewhere in
`tests/`, and the three that are not named that way are covered. The plans'
*modules* are all present (30 of 30 declared paths exist), and of 58
plan-declared symbols, 11 are not defined in `src/` — but each is one of three
benign kinds. Four are plan code sketches rather than contracts (`fetch_viirs`,
`export_powerplantmatching`, `solve_whatif`, `verify_key`, the same finding
already recorded for §44's request bodies). Three were **renamed or redesigned**
rather than dropped, and each is worth naming because the plan's spelling and
the tree's differ for a reason: `_deep_merge` is `config/loader.py`'s public
`deep_merge`; `_cache_key` is the module-level `api/whatif.py:solve_cache_key`,
which the plan's own §2.1 explains — the plan sketches
`hash(tuple(sorted(params.__dict__.items())))` and the tree does not use
`hash()` at all, because Python's string hashing is salted per process and the
plan's `test_cache_key_stable_across_processes` gate is precisely what that
defect fails. `_init_strategy` is a sketch of the design the same plan rejects
two sections later (`06-layer3-market.md` §2.2, "An RL agent per generator is
not a design" — thousands of independent PPO policies, non-deterministic and
unreproducible), and §4.3 is titled "Rejected: reinforcement learning"; the
tree's `market/agents.py` has no strategy object at all, which is that
rejection carried out. One is a deliberate aliasing
(`ValueBasis = Basis`, with the reason written at `reporting/schemas.py:31` — a
second enum with the same four members is a second place for them to drift).

**And the engine register is honest in both directions.** Cross-checked on
2026-10-16: every `ScenarioParameters` field is read by `whatif/apply.py` or by
a validator (`ssp_pathway` is read as a gate on `drought_multiplier`, which is
a real read and not a declaration), and every `params.X` read is a declared
field. No knob is applied without being declared, and none is declared without
being applied. The 7 knobs `engine_fields_unreached()` reports are genuinely
unreached by the graph, and the 49 parameters `untranslated()` reports are
genuinely unreached by the engine — the two counts are a register, not a
defect, and the sweep found nothing hiding behind either.

## The coupling build (2026-10-17, batches 12–16)

**The decision.** The uncoupled register refused to close on the honest-arithmetic
excuse ("741 cannot be generated from this tree" — `docs/research/uncoupled-equations/README.md`),
and the programme owner overrode it: every node joins the graph, using physics,
economics and research, with the equations correct, referenced, documented and
detailed — so a researcher can retrieve an equation and question its logic. That
is the PRG's entire value; unlinked nodes have none.

**What landed.** Four batches, each authored through the coupling harness
(`scripts/build/prg_coupler.py` — family tables → fragments → every gate the
loader skips: propagate at the document's own defaults, derived values inside
their ranges, a default scenario free of blocking conflicts, every equation
dimensionally decidable) and baked into `config/prg.yaml`:

| Batch | Family | Coupled | Theory / citation |
|---|---|---|---|
| 12 | The financial core | 7 | Rate-of-return regulation: `wacc_alias` (UKRN 2023, the vanilla form the shipped `wacc_definition` already states), RAB from fleet capital less accumulated depreciation, straight-line regulatory depreciation, the allowed revenue requirement, the allowed returns as *bounds* on debt and equity costs, the applied tariff under the revenue cap (World Bank regulation handbook) |
| 13 | The technology cost layer | 25 | Per-technology LCOE in the fixed-charge-annuity form (NREL ATB 2025 Equations & Variables; Short, Packey & Holt 1995, NREL/TP-462-5173; EIA AEO methodology), per-tech CRF over each technology's own asset life, O&M at literature levels, fuel at the fleet heat rate, stack carbon priced. The two shipped VRE LCOE equations corrected: `opex_variable_battery` — a battery cost inside a solar LCOE, the known open defect — leaves, and the battery gets its own LCOS (ATB battery equations; Lazard LCOS). Solar's capacity factor corrected from the 0.5 placeholder to the regional 0.22. Twelve un-built technologies carried at real units and a zero reference build. The leaf fleet-build balance as the constraint the optimiser's decision variables needed. |
| 14 | Resolved duplicates + employment | 22 + 7 | The fragments' alias register — validated by everything, applied by nothing — applied as equality equations (20 cost dups, lifeline, disability). Property tax and the investment allowance as the rate-on-base definitions they are. Employment: indirect/induced from the kernel's direct jobs at input-output multipliers (Leontief), group-composition jobs at the programme's shares. |
| 15 | Demand synthesis + macro | 11 + 2 rules | Bottom-up load synthesis (the catalog's own method cell): the four sector demands from their shares. The macro driver in the first-order elasticity form g_D = ε·g_Y, at the reviewed values (EIA/Stanford EMF ~0.59; Burke & Csereklyei 0.88–0.95 electricity-specific; Hou & Tan 2008 China 0.85; 单葆国 2017 the 0.38–1.88 band). The planner's `demand_growth` sits *exactly on* its own implication at the reference, so the two directional checks are quiet at the default scenario and fire on any other. |
| 16 | Fuel conversions + the tariff stack | 6 + 3 | Delivered fuel prices from the markets' own quotes at named, cited conversion nodes (5.8 MMBtu/barrel; the Btu basis; NH₃ LHV 18.6 GJ/t; H₂ LHV 33.33 kWh/kg). The variable cost stack named (fuel + carbon), the pass-through dial and the pass-through tariff — the regulator's lever expressed. Battery duration 500000 → 4 h; round-trip efficiency 500000 → 0.85. |
| 17 | The financial rates | 7 | The duplicated rate spellings resolved by equality (the catalog's carbon-price ids, the CIT, the growth rates); `demand_growth_rate` left deprecated-with-replacement -- the loader's own mechanism for a migrated id. The credit-spread decomposition (BIS): `cost_of_debt = interest_rate + debt_spread` at the shipped 0.09 unchanged; the Fisher equation gives the real rate; VAT reaches the retail tariff. |
| 18 | The market instruments | 8 | The capacity market's revenue at its own price (USD/MW-year, cited to Stoft 2002); CBAM's applied price (EU ETS 2026 level); N-1/N-2 contingency reserve from the largest infeed (Billinton & Allan); the PPA guarantee releasing the sovereign risk premium; the community fund's share applied; and every uncoupled boolean's unit completed (`1`), which is data completion the nodes' own docstrings state. |

**Graph after the bake (batches 12–17):** 1078 parameters, 163 equations,
384 edges, 54 rules; then batch 18 (the market instruments: the capacity
market's revenue, the CBAM's applied price, the N-1/N-2 contingency
reserve, the PPA guarantee's risk release, the community fund) landed
1083 parameters, 168 equations, 396 edges, **702 uncoupled**. 800 free,
111 exogenous, 153 derived, 19 endogenous. The rule-cited parameters are
counted as consumed by the register (rules_reading, its own coupling
class), which is what `test_every_settable_parameter...` asserts.
Earlier state below for the record: 1075/156/375; 793 → **717**, every one
carried with its family class in `docs/param_coupling_worklist.md`. The unit
walker now decides **all 156** equations (0 undecidable); 144 are consistent and
the 12 flagged are the same vocabulary class the earlier pin recorded — annual
quantities declared without a per-year divisor, and two compounding slips — each
with a measured trade documented in `test_the_flagged_equations_are_a_known_set`.

**Provenance discipline.** Ten works are archived under `sources/` with sha256
digests recorded in `sources/INDEX.md` (NREL ATB 2025; EIA LCOE methodology;
Short, Packey & Holt 1995 via the Stanford mirror; UKRN cost-of-capital
guidance; EIA/Stanford EMF demand elasticities; Burke & Csereklyei 2016; IRENA
jobs 2024; the IEEE 1366 reliability tutorial; Tejada-Arango 2023 arXiv; the
Oree et al. 2017 GEP review). Every equation's `reference` resolves to a
register row, every archived copy has a digest, and the declared LaTeX is the
renderer's own output — so `check_latex`'s operand-set comparison holds by
construction and the descriptions carry the analytic statement.

**Loader changes the build needed.** Fragment relationships now deduplicate
against the shipped document (identical → redundant, differing → correction);
the first bake appended its way to 569 edge records over 375 claim keys. A
corrected equation's stale edges — shipped edges naming a symbol the corrected
arithmetic no longer carries — are disposed and reported (`<stale-edge>`),
judged by the arithmetic's own symbol closure, canaried in
`test_a_corrected_equation_disposes_of_its_own_stale_edges`. Before this, a
symbol-changing equation correction was unloadable, because the correction is
what makes the shipped edge stale.

**Batch 20 and the current state (2026-10-18).** The share family closed
through an overlap-aware framing — the financing-mix shares do not sum to one
(green bonds are bonds; blended packages draw on the DFI and commercial
tranches), so they couple as subset and envelope inequalities against bases
that exist: `debt_mix_bound` against the D/E ratio's own `D/(D+E)`,
`blended_finance_bound`, `green_bond_bound`, `carbon_finance_bound` against the
carbon revenue's weight in total revenue, `steel_route_bound`,
`urban_heat_supply_bound`, `powertrain_stock_bound`, `v2g_subset_bound`. The
time-index family (all 24) coupled as its own arithmetic: policy-clock lead
times, the growth window and its compound factor, retraining within
construction, the storage power-energy cost split
(`capex_battery * battery_duration` per kW; `capex_phs / phs_duration` per
kWh), and the vintage capacity factors — the factor today compounded by its
technology's degradation rate to the dataset's vintage year
(`solar_pv_capacity_factor * (1 - solar_degradation) ** solar_cf_year`), which
is what makes `solar_cf_year`/`wind_cf_year` the dataset-vintage dials they
are. 11 of the 18 shares coupled; `public_transport_share` waits on a
passenger-km base (the base-node batch). Eight placeholders found their units:
`construction_period` months, `settlement_period` half-hours,
`phs_duration`/`thermal_storage_duration` hours, the line-outage pair
(`line_outage_probability` reframed from a probability ≤1 to the expected
events-per-year rate the frequency×duration product needs, IEEE 1366's r_i
term), `chemicals_ammonia_production` and `interconnector_capacity`, the two
degradation rates. State after batch 20: **1114 parameters, 206 equations, 456
edges, 54 rules, 649 uncoupled** (694 → 649; 45 this batch). Generator
`--check` idempotent; the two batch-19 references that resolved to no register
row are corrected to null in this fragment (the products are definitions; the
H2 intensity's provenance lives on the node) and the degradation identity
carries Jordan & Kurtz (2016) in the degradation nodes' source text pending
archive.

**A bake lesson worth keeping.** The bake is a *document-level* merge, never a
whole-graph re-dump: the shipped file's bodies deliberately carry mixed shapes
(catalog rows compact, corrected nodes the model's own dump), and re-dumping
the merged graph reshapes every untouched entry — adding `source:
docs/params.md` keys that `load_existing` treats as generated and drops. Two
consequences surfaced once and are pinned: the generator re-emits
newly-coupled catalog nodes with their catalog roles (the uncoupled register
no longer forces them `free` — 15 role flips, accepted), and `net_zero_year`
is derived-*by-name* in the catalog heuristic but is not computed by anything
once it is only a coupled milestone — so a coupled milestone needs its own
preserved body (role `exogenous`, its default restored), not a name heuristics'
pass.

**Batches 21 and 22, and the current state (2026-10-18, commit 3c89cf2).**
Batch 21 coupled 18 (649 → 631). Its spend products are the ones whose bases
exist — `biomass_variable_cost_usd_per_mwh` (fuel plus non-fuel O&M),
`vre_connection_spend_usd`, the heat-pump annuity at the shipped `crf`,
`hydrogen_export_revenue_usd_per_year`, `insurance_premium_usd_per_kw_year`,
`life_extension_fraction_of_new_build`, and the three programme spends
(`mini_grid`, `shs`, `demand_response`) — and its rate arithmetic is the
half-lives (ln 2 over the annual retirement / cap-reduction / connection rate)
plus the three compound growth factors, `(1 + r) ** horizon_years`.
`uranium_fuel_cost_usd_per_mwh` reads a named `uranium_burnup_lb_per_mwh`
constant rather than a folded number, the way `hydrogen_per_t_steel_kg` does.

Batch 22 coupled 40 (631 → 591) and is the one worth reading, because the
compliance register is not a family of formulas. A `_requirements` node is a
*share of a base* or a *ceiling a shipped quantity must sit under*, so it
couples three ways and the class of each node decides which:

- **29 register-share products.** `collateral_requirements` times the revenue
  requirement; `scada_ems_requirements` times total capacity;
  `clearing_house_requirements` times the settled carbon value. The share is
  the dial, the base is what the graph already carries, and the product is the
  quantity a report can name.
- **10 `leq` thresholds** at the document's own defaults: SAIDI 96 ≤ 120,
  SAIFI 12 ≤ 15, largest credible loss 1000 ≤ 1200 MW of primary response,
  inertia 500 ≤ 36 000 MW·s, non-spinning reserve inside the margin,
  clean-cooking target above the LPG penetration already reached, FPIC
  consent share, IFC covenant share, resettlement share, and the energy-burden
  ceiling. These are the constraint register's own growth: `bound_routes` went
  16 → 21 and five of the ten bind a solve.
- **One ratio, not a bound.** The WHO annual PM2.5 guideline is *exceeded* by
  the ambient mean the graph carries (35 / 5 = 7). Writing that as a `leq`
  would make the shipped defaults a conflict, and the conflict is the finding —
  so the honest statement is the ratio `pm25_exceedance_ratio`, computed rather
  than shipped as a violated inequality. This is the register's own lesson
  applied forward: a bound that cannot hold at the document's defaults is not a
  bound, it is a measurement.

Eight extensive bases arrive with the register — `population_total`,
`distribution_feeders_total`, `pm25_annual_mean_ug_per_m3`,
`project_pipeline_count`, `scada_telemetry_sites`,
`river_mean_annual_flow_m3_per_s`, `distribution_network_km`,
`audit_accounts_per_year` — each with a default derived from a quantity the
graph already holds (population back-solved from the residential demand share
and per-household consumption; the feeders and telemetry sites from the system's
own MW at a stated per-unit density), and none with a citation invented for it.
`MVAr` joined the unit registry as `ampere * volt` and a million of it, so
`reactive_power_requirement` has a spelling the walker can decide rather than a
unit it silently skips.

State after batch 22: **1168 parameters, 261 equations, 547 edges, 54 rules,
591 uncoupled** (694 at batch 20 → 649 → 631 → 591). Generator `--check`
idempotent, `propagate` clean over all 1168 values, the five prg test files
green at 279 tests. The suite's moved literals are all re-derived from the
graph's own registers rather than adjusted to fit: dead knobs 603 → 563, audit
checked/skipped 67/131 → 86/141, computed 198 → 227, citation doors 104 → 112,
constraint-shaped 24/198/222 → 34/227/261, translate coverage 914 → 922,
catalog disagreements 30 → 65 (the 35 retyped register nodes now differ from
their catalog rows by construction — the retype *is* the disagreement, and it
is now visible rather than silent).

**Batch 23 — the extensive bases (2026-10-18).** Batches 21 and 22 left a
residue that looked like a list of unrelated knobs and was one thing: unit
rates whose product needs a physical extent the graph did not carry. A
transmission cost in USD per MW-km is not a cost until something states the
MW-km. So the batch is the bases — fifteen of them, each a settable quantity
with a default — and the sixteen products fall out of them:

- **Three Wright learning curves.** `capex * (cum/ref) ** (log(1 - rate) /
  log(2))` for solar PV, batteries and electrolysers, each against its own
  technology-specific installed/reference pair. The graph already carried a
  generic `cumulative_capacity_mw` pair and three learning rates with no base
  of their own; the technology pairs are what the rates were waiting for.
- **Seven route and capex products.** Transmission, interconnector, hydrogen
  pipeline and right-of-way costs as rate × extent; distribution capex per
  connection and against peak demand; the regulated asset value it rolls into;
  land acquisition at cost per hectare.
- **Six household, land, transport and tariff products.** Households from
  population and household size; energy-poor households and the depth of
  their gap; public-transport passenger-km; electrolysis electricity demand
  (energy × units / efficiency); and the regulated tariff ratio.

Two nodes were retyped rather than added: `right_of_way_cost` (USD/km) and
`energy_poverty_gap` (MWh/year) were 500000.0 placeholders with `unit: null`,
and are now defined quantities. `electrolyser_efficiency` (dimensionless 0.65)
and `hydrogen_pipeline_capacity` (MW) were placeholders too and are now
parameters — the efficiency retype is what made
`electrolysis_electricity_demand_mwh_per_year` decidable rather than
undecidable.

One unit-parsing defect was found and fixed before the products were authored
against it. `USD/MW-km` repaired the hyphen to `*` and Pint parsed left to
right, reading it as `USD * kilometer / megawatt` — USD·km²/MW, a *decidable*
wrong reading the walker blesses. The fix parenthesises a `*`-joined product
under a bar, so `USD/MW-km`, `USD/(MW*km)` and `USD/MW/km` are one unit and
`MW-km` not under a bar is still a product. Only one of the graph's 71 unit
strings changed and no equation verdict moved.

A household-size inconsistency is recorded in the node prose rather than
papered over: the graph's own residential demand implies 5.7 persons per
household against the 4.5 demographic figure, so the demographic number is the
base and the gap stays visible in the product it forms.

**Batch 24 — the carbon and market families, and the annual-quantity repair.**
Thirty-four new parameters and 42 retyped, 50 equations, 97 edges, one rule. Three things
landed together because they are one measurement:

* **The annual-quantity repair.** Fifteen nodes were declared as stocks where
  they are flows — `demand_twh`, `generation_twh` and the four sector demands
  as bare `TWh`; the water balance as bare `m3`; unserved energy as `GWh`; the
  reliability cost as `USD`. Every revenue and spend product against them was
  dimensionally undecidable, so no rate-times-quantity equation could be
  authored at all. Retyping them to `TWh/year`, `m3/year`, `GWh/year`,
  `USD/year` cleared nine flagged equations and opened none — the prediction
  the flagged-set docstring had carried since the promotion ("clears this
  equation and opens five others") was wrong in one direction and is corrected
  there with the measurement.
* **The carbon-market layer.** The ETS cap at the covered share of the budget
  (`ets_cap = carbon_price_coverage * carbon_budget_mtco2 / horizon_years`),
  the auction volume, the Article 6.2 chain from the corresponding adjustment
  through the transferred volume to the credit value, credit retirement and
  the reversal allowance at the permanence shortfall, leakage as the share of
  covered emissions that relocates, the position limit against the cap, the
  insurance premium and settlement exposure against the credit value, the
  hybrid revenue cap and the price band around the marginal cost. The
  `ets_enabled` gate could not be an equation — there is no
  `carbon_tax_enabled` node, the rule grammar has no `max`, and multiplying
  by the flag would double-count the covered share — so it is a cross-
  validation rule, `carbon_revenue_without_an_instrument`, which fires at the
  defaults exactly once and names the ~650 M USD/year the revenue identity
  accrues with the instrument off.
* **The market, subsidy and employment families.** Shares against the bases
  batch 23 landed: market-traded volume and time-of-use demand against demand,
  the bid-ask, wheeling, distribution and cross-border wheeling spends against
  it, the feed-in, electricity, renewable and fossil subsidy spends against
  generation, the carbon-tax offset against revenue, the cross-subsidy and
  tariff-rebalancing transfers, mini-grid and SHS subsidy spends against their
  programme spends, netting shortfall against posted collateral, the X-factor
  revenue reduction and working-capital allowance against the allowed revenue,
  and the three employment attainment ratios against their targets.

Two rules already in the register changed their verdict at the defaults, and
one test's canary had to be re-pointed. The canary that proves the dimensional
checker can tell a power from an energy used `generation_twh` as its energy
side; that node is now `TWh/year`, which is a power, so the canary would have
compared a power to a power and passed for the wrong reason. It now uses
`cumulative_battery_installed_mwh`, a stock the repair did not touch. The
rules: `carbon_revenue_without_an_instrument` fires at the shipped defaults
(the ETS is off, the covered share is half), so the "every rule is satisfiable"
canary now names that one finding instead of asserting a clean report -- a rule
that fired on *every* scenario would still fail it.

One equation was reformulated during the run: the cross-border wheeling charge
was written `wheeling_charge_cross_border * abs(net_imports_twh) * 1000000`,
and `sensitivity._partials` refuses to differentiate `abs` — deliberately,
because a solver handed a non-differentiable term oscillates at the kink.
Since `net_imports_twh` defaults to 0.0, the derivative is undefined at the
default under any `abs` form, so the equation states the signed product and
the description carries the reason: the graph holds a *net* balance, and the
sign is the direction of the transfer, not a defect.

State after batch 24: **1231 parameters, 320 equations, 676 edges, 55 rules,
532 uncoupled** (694 at batch 20 → 649 → 631 → 591 → 575 → 532). Generator
`--check` idempotent, `propagate` clean over all 1231 values at the document's
defaults with no range excursion, `gradients` clean over the whole graph, the
unit walker consistent on 308 of 320 equations with **11 flagged** (the 20 of
batch 23 less the nine the repair cleared) and 0 undecidable. The moved
literals are re-derived from the graph's registers: dead knobs 552 → 509,
audit checked/skipped 88/155 → 109/177, computed 243 → 286, constraint-shaped
34/243/277 → 34/286/320 (no new inequality — the batch is all identities),
affine coverage 243 → 286, edge strength hard 274 → 317, citation doors
115 → 138 (twenty-three new references, every spelling resolving to a
`sources/INDEX.md` row),
translate coverage 935 → 926 (nine former free knobs became derived, none
settable), uncertainty inputs unchanged at 72 (the retype preserves a node's
determinism; the units moved, the uncertainty did not), catalog disagreements
67 → 100 (the thirty-three definitions).

**What the remaining 575 are.** They are not one class, and the worklist says
so. The compliance family is down to three (`gis_requirements` is a share of
network assets in GIS with no base yet; the regulation up/down requirements
need the reserve product they are a slice of). The policy flags are 25, of
which 20 remain: they are gates, not quantities — `ets_enabled` switches a
carbon stream on, `unit_commitment` switches a dispatch mode — and the honest
coupling for a gate is a *conditional* the library does not have yet, not a
product. The genuinely qualitative remainder — capability-maturity scores,
protocol names, land-tenure classes, governance indices — is the graph's
declared free space, and `uncoupled()` will retain them by the register's own
contract. Stating that is the point: the register closing to zero is not the
goal, the register *naming every node's class* is.

**Batch 25 — the gate family.** Thirteen equations, nine retyped nodes, 48
edges, no rule. Thirteen switches with a quantity behind them, and the
distinction that made the batch: the research packs split the flags into
GATE-PRODUCT, where a switch multiplies a base the graph already carries, and
GATE-SCENE / GATE-SCENE-SWITCH, where a switch selects which model runs. Only
the first kind couples. No arithmetic expresses a branch, and a product written
for a scene switch would be a number pretending to be a branch. Batch 25
coupled thirteen of the packs' fifteen GATE-PRODUCT switches; the other two,
`carbon_credit_insurance` and `voluntary_carbon_market`, were already coupled.
The 44 scene switches remain declared.

The products: the gated carbon volume (`ets_enabled * ets_cap`), three
insurance covers against gross revenue, political-risk cover, the parent
guarantee and the sanctions exposure against capex (the guarantee against the
debt share of it), the free-trade-zone benefit and the import duty against
equipment spend, permitted imports against net imports, coordinated maintenance
hours against planned maintenance, the smart-metered population, and the
permitted transmission spend against `line_upgrade_budget`.

Nine nodes were retyped rather than added. Eight insurance and fiscal flags
shipped unit-less at the catalog's 500000.0 placeholder and are now
dimensionless shares in [0,1]; `line_upgrade_budget` is USD at 5e7. The
placeholder was not cosmetic: `import_duty_exemption` at 500000 makes the
`(1 - x)` factor in the duty product -499999, which is why the retype precedes
the equation rather than following it. All thirteen were dimensionally
pre-checked before authoring, 0 bad of 13.

State after batch 25: **1244 parameters, 333 equations, 711 edges, 55 rules,
516 uncoupled** (694 at batch 20 → 649 → 631 → 591 → 575 → 532 → 516).
Generator `--check` idempotent, `propagate` clean over all 1244 values with no
range excursion, `gradients` clean over the whole graph. Unit walker 321 of 333
consistent with **11 flagged**, 0 undecidable, 4 exempt; constraint-shaped
34/299/333 (no new inequality); translate coverage 926 total and 923
untranslated, unchanged because the batch added no settable node; catalog
disagreements 100 → 109 (agree 687 → 678); dead knobs 509 → 495; audit
checked/skipped 109/177 → 117/182; edge strength hard 317 → 330; citation
doors 138 → 139 (only `gated_carbon_volume_definition` cites; the other twelve
carry None); affine coverage 286 → 299; uncertainty inputs unchanged at 72,
reaching 119 → 122 derived parameters.

**Batch 26 — the adequacy and reserve family.** Eleven equations, 16 nodes
written, 30 edges, no rule. Eleven catalog nodes that carried a formula and
were held as placeholders, retyped and given their equations, plus five new
nodes. Six products: spinning reserve as a share of peak demand, the regulation
up and down requirements at their own shares, voltage support as a share of
reactive capability, spare capacity as the capacity above peak, and the
post-programme transmission loss at the reduction target. Five aliases to nodes
that already do the work: `spinning_reserve_requirement` to `spinning_reserve`,
`non_spinning_reserve` to `non_spinning_reserve_requirement`,
`planning_reserve_margin` to `reserve_margin_min`, `reserve_margin` to
`reserve_margin_actual`, and `grid_reliability_saifi` to
`service_quality_standards`.

Four new bases — `spinning_reserve_share` (0.05), `regulation_up_share` (0.01),
`regulation_down_share` (0.01) and `voltage_support_share` (0.10), all
dimensionless in [0,1]. `transmission_loss_reduction_target` was retyped from
unit-less 500000.0 to a share at 0.1, for the same reason as batch 25's
exemptions: the equation multiplies by `(1 - x)`, and at 500000 that factor is
-499999.

Every one of the eleven shipped at `unit=None, default=500000.0`. Spinning
reserve at 500000 MW is 500 GW of reserve on an 8.5 GW peak. At defaults the
products are 425 MW spinning, 85 MW regulation up and down, 280.5 MVAr voltage
support, 1,500 MW spare capacity, a 0.15 planning margin, a 0.170 operating
margin, a SAIFI target of 15 events/year and a post-target loss of 0.45.

The batch also surfaced a generator drift: `transmission_loss_factor` was
`free` in the shipped document while the generator infers `exogenous` from the
name. Regenerating `prg.yaml` fixed it at the same default. It is the second
time a hand-edited role has drifted from the inference: `net_zero_year` was
preserved `exogenous` at batch 20's regen against the derived-by-name
heuristic, which reads it as computed when it is a milestone. The rule that
follows is that a role is regenerated rather than typed.

State after batch 26: **1249 parameters, 344 equations, 728 edges, 55 rules,
504 uncoupled** (694 at batch 20 → 649 → 631 → 591 → 575 → 532 → 516 → 504).
Generator `--check` idempotent, `propagate` clean over all 1249 values with no
range excursion, `gradients` clean over the whole graph. Unit walker 332 of 344
consistent with **11 flagged**, 0 undecidable, 4 exempt; constraint-shaped
34/310/344 (no new inequality); translate coverage 926 → 920 total and
923 → 917 untranslated (ten reserve nodes left the settable set, four shares
entered it, net six); catalog disagreements 109 → 120 (agree 678 → 667); dead
knobs 495 → 483; audit checked/skipped 117/182 → 119/191; edge strength hard
330 → 341; citation doors 139 → 149 (ten of the eleven equations cite;
`transmission_loss_target_definition` carries None); affine coverage
299 → 310; uncertainty inputs unchanged at 72, reaching 122 → 123 derived
parameters.

**Batch 27 -- the finance family.** Fourteen equations, 21 nodes written, 34
edges, no rule. The batch reads `docs/FPE.md` (the financial pricing engine),
`docs/FRM-spec.md` (the financial risk module) and `docs/FRM-ingest-spec.md`
(the ingest contract), and ships what those three specify against bases the
graph already carries.

Four aliases where the catalog carries one quantity under two ids:
`interest_rate_debt` to `cost_of_debt`, `debt_service_coverage_ratio` to
`dscr_min`, `maladaptation_risk` to `risk_of_maladaptation`, and
`insurance_premiums` to `insurance_premium_usd_million`. The first matters
because `cost_of_debt` is what `wacc_definition` reads, so a scenario that sets
the catalog's own spelling now reaches the cost of capital.

Six products. The transaction cost is the arranging share times gross revenue
(129.7 M USD/year at defaults). The sovereign and technology risk charges split
the capital by tranche: the sovereign premium on the debt-financed part, the
technology premium on the equity-financed part, each `premium * share *
capex * capacity * 1000`. The microinsurance premium is the income share times
household income, and the microinsured population is the coverage share times
the electrified population. The ring-fenced asset value is the ring-fence share
times the regulatory asset base.

Three FRM identities shipped as the spec states them. The premium is the
annual average loss grossed up by the expense, capital and profit loadings
(50 M USD AAL at a 1.30 total loading = 65 M USD). Solvency capital is the
99.5th-percentile loss less the expected one (500 − 50 = 450 M USD), which is
the tail the insurer must hold rather than the premium it charges. The RAB
roll-forward is written as a flow on both sides -- the annual depreciation
charge less the regulatory depreciation -- because `regulatory_depreciation` is
USD million/year and adding it to a stock is the unit error the walker caught.

`project_irr_hurdle` is `discount_rate * (1 + equity_return_target)`: the
blended cost the asset must earn, grossed up by the margin equity demands over
it.

One inequality, and the only bound in the graph whose edge carries a tier:
`llcr_floor_bound` holds the loan-life coverage ratio at or above the covenant
floor, P2, hard, with a `constraint` edge from `loan_life_coverage_ratio` to
`llcr_estimate`. At defaults the estimate is 1.78 against a floor of 1.40, so
it holds; across the carbon-price sweep it binds before the DSCR covenant does,
which is why the conflict canary is now pointed at it.

Six new bases: `aal_usd_million` (50), `pml_99_5_usd_million` (500),
`expense_loading` (0.10), `capital_loading` (0.15), `profit_margin` (0.05) and
`sovereign_risk_premium` (0.0256/year). Nine nodes were retyped from the
catalog's placeholder: `transaction_costs` to a 0.02 share, `debt_tenor` to 15
years, `currency_risk_premium` to 0.0256/year, `technology_risk_premium` to
0.03/year, `microinsurance` to a 0.5 coverage share, and the three derived
outputs to their units.

The batch also repairs a defect it inherited. `cost_of_debt_priced` now charges
`interest_rate + debt_spread + currency_risk_premium`, which is FPE §6's
decomposition and puts the sovereign spread where the literature puts it rather
than in a separate charge node that would double-count. `cost_of_debt` lands at
0.1156, inside `allowed_return_on_debt`'s 0.12. And `ets_enabled` is now 1.0:
batch 24 shipped the ETS off beside a covered share of half, so the revenue
identity booked carbon revenue with no instrument collecting it and
`carbon_revenue_without_an_instrument` fired on every clean scenario. Turning
the instrument on is the repair the rule was asking for; the rule stays and
`test_every_declared_rule_can_fire` keeps it proven able to fire.

Two nodes were considered and rejected. A separate
`currency_risk_charge_usd_per_year` would double-count the premium once it sits
in `cost_of_debt`. `solvency_capital_ratio` computed as `solvency_capital /
aal_usd_million` is 9.0, a coverage multiple rather than a ratio, so it stays
out rather than shipping a misnamed quantity.

`Damodaran (2026), Country Default Spreads and Risk Premiums` enters the
register as the source for the country spread: South Africa's Ba2 rating gives
a 2.56% default spread on a 4.23% mature-market ERP, and that spread is the
`currency_risk_premium` default. The copy is archived at
`sources/archive/damodaran_ctryprem_2026-01.html` with its digest in
`sources/INDEX.md`.

State after batch 27: **1261 parameters, 359 equations, 762 edges, 55 rules,
488 uncoupled** (694 at batch 20 → 649 → 631 → 591 → 575 → 532 → 516 → 504 →
488). Generator `--check` idempotent, `propagate` clean over all 1261 values
with no range excursion, `gradients` clean over the whole graph. Unit walker
348 of 359 consistent with **11 flagged**, 0 undecidable, 4 exempt;
constraint-shaped 35/324/359 (one new inequality, the LLCR covenant); translate
coverage 920 → 918 total and 917 → 915 untranslated (nine placeholders made
derived, ten new settable knobs, net one fewer); catalog disagreements
120 → 134 (agree 667 → 653); dead knobs 483 → 467; audit checked/skipped
119/191 → 124/200; edge strength hard 341 → 356; citation doors 149 → 151
(both risk charges cite Damodaran; the eleven identities carry None); affine
coverage 310 → 324; uncertainty inputs 72 → 75, reaching 123 → 129 derived
parameters.

**Batch 28 -- the product remainder.** Fifty-eight equations, 66 nodes coupled,
no rule. The catalog's PRODUCT class is a row with a formula and, in
fifty-four cases, `unit: None` beside the 500000.0 placeholder where a share or
a rate should be. The formula is right and the node it multiplies cannot be
read, so the row is a claim with no arithmetic. This batch supplies the unit,
replaces the placeholder, and ships the identity.

**The fiscal register.** Five rates that were declared and multiplied by
nothing, plus one alias. The stamp duty and the performance bond are charged on
capital (`rate * capex * capacity * 1000`), the export duty on export revenue,
the dividend withholding on the distributable residual
(`cfads - debt_service`), and the interest withholding on the debt tranche times
its rate. That last is the finding: the shipped row multiplied a withholding
rate by capital and never by the interest, so it was a tax with nothing to tax.
At defaults it now yields 97.1 M USD/year against a dividend withholding of
110.8 M. `customs_duty` is the catalog's second id for `import_duty_equipment`
and ships as the equality.

The two residual-based products carry signed ranges, `-1e12` to `1e12`, and the
reason is the base rather than the products. Both multiply a rate by
`cfads - debt_service`, which is negative whenever a project's debt service
exceeds its cash flow -- the case a DSCR covenant exists to report. A lower
bound of zero filed that shortfall as a derived excursion, so an unfinanceable
scenario raised two range violations ahead of the `dscr_requirement` violation
that is the actual finding, and the check route's first violation stopped
naming the covenant. The DSL has no differentiable `max`, so the clamp the
earlier prose described ("nothing to sweep") could not be expressed and the
range was the only place the claim lived; the range now says what the
arithmetic does. `cfads_usd_per_kw_year` and `project_gearing_dscr` already
ship signed ranges for the same reason.

**The insurance register.** Incurred claims (`loss_ratio * premium`), the
deductible (`share * asset value`), and the ceded premium (`(1 -
retention_share) * premium`). Batch 27 shipped the pricing chain; these are the
three quantities a policyholder reads off it. 42 M USD of claims against an
18 M USD ceded premium at defaults.

**Temporal and operational scalars.** The investment period length
(`time_horizon / investment_periods`), the time-slice segment (`24 /
tsam_segments`), the dispatch cadence (`1 / dispatch_interval`), the shiftable
energy, the fishing community's annual energy, the islanding feeder count, the
fuel price band's upper edge, and the geothermal capex per productive kilowatt.
Two deserve naming. The geothermal node divides by a success probability, so its
range starts at 0.05 and not 0 -- a zero success rate is an infinite cost per
productive well, which is the arithmetic refusing the question rather than
answering it; at 75% success the 4,000 USD/kW nominal becomes 5,333 USD per
productive kilowatt. And the fuel band ships the upper edge only: the lower edge
is its mirror, and a mirror is not a measurement.

**Programme spend against allowed revenue.** Seven consumer-protection and
community programmes, each a share of the revenue cap, in the unit the cap is
in. The graph already had this idiom once, in `consumer_protection_spend_definition`.

**Employment and transition.** Ten shares against the direct workforce and two
transition instruments. The counts matter more than the shares because a
compliance finding is a count of positions: 43,000 screened against child
labour, 34,400 pension-covered, 3,870 unfilled skilled posts. The wage bill is
860 M USD/year, about 13% of gross revenue. The two transition instruments sit
on deliberately different bases -- the levy on gross revenue, the funding on the
community development fund -- so they do not tax the same revenue twice.

**Seventeen aliases.** Rows the catalog carries twice or three times, each made
the same number by an equality. One is a correction rather than a duplicate: the
catalog prices the land bill over the habitat-loss subset of the site, which
would price 500 of the 5,000 hectares and call it the bill, so the alias points
at the graph's own `land_acquisition_cost_usd` over the whole take.

Two rows were considered and rejected. `storage_duration_curve` is an LP ratio
whose denominator is endogenous, so an equality would be an equation over a
variable the optimiser chooses. `line_outage_start`/`_end` are timestamps, and
`docs/prg-status.md:980-991` already records that pypsa ignores dynamic
`lines_t.active` -- an equation there would couple a knob to a field nothing
reads. And `cross_border_trading` cannot be an alias at all: the graph refuses
any edge into a deprecated node, because `_deprecated_reach` is the contract
that a node with a replacement is not read. The two catalog rows disagree about
whether it is live; the graph's answer is the one that counts.

One equation was rewritten during the batch. `import_dependency` was first
written as `abs(net_imports_twh) / demand_twh`; the sensitivity kernel
differentiates every equation in the graph and the DSL has no derivative rule
for `abs`, correctly, because it is non-differentiable at zero. The signed ratio
`net_imports_twh / demand_twh` is the honest form anyway: a negative value is an
export position, not a dependency, and taking the absolute value would report a
large net exporter and a large net importer as equally dependent. Its range
widened from [0, 1] to [-1, 1] to admit that.

State after batch 28: **1296 parameters, 417 equations, 871 edges, 55 rules,
422 uncoupled** (694 at batch 20 → 649 → 631 → 591 → 575 → 532 → 516 → 504 →
488 → 422). Generator `--check` idempotent, `propagate` clean over all 1296
values with no range excursion, `gradients` clean over the whole graph. Unit
walker 406 of 417 consistent with **11 flagged**, 0 undecidable, 4 exempt;
constraint-shaped 35/382/417 (no new inequality); translate coverage 918 → 895
total and 915 → 892 untranslated (23 placeholders made derived, so they leave
the settable set the coverage measures; the three translated nodes unchanged);
catalog disagreements 134 → 134 (agree 653 → 653);
dead knobs 467 → 402; audit checked/skipped 124/200 → 155/227; edge strength
hard 356 → 414; citation doors 151 → 183 (the programme spends cite the World
Bank revenue-cap handbook, the employment products cite IRENA's job factors,
the aliases cite the duplicate-row register, and the investment period cites
Tejada-Arango); affine coverage 324 → 382; uncertainty inputs 75 → 76, reaching
129 → 143 derived parameters.

**A bake that dropped an authored default.** `mean_time_between_failures` ships
`default: 50000.0` in `docs/param_batch4.md` and `500000.0` in `config/prg.yaml`.
The 500000.0 is the catalog join's placeholder (`e76d4bd`), and the bake at
`b0fe572` carried it through in place of the fragment's value — so the node
whose own description calls 500000 hours "a value that would imply a unit
running for 114 years between failures, which for most equipment classes is a
claim no asset register supports" shipped with exactly that value. It sits at
the top of its own range, and `availability_definition` turns it into a forced
outage rate of 4.8e-5, three orders below any published equipment class. The
default is restored to the fragment's 50000.0; the rate becomes 4.8e-4. The
generator's `--check` stays idempotent, so the field is the document's, not the
generator's — which is why nothing regenerated it and nothing compared the two.

This is the class the "declared is not produced" register counts, in the one
direction it had not been read: not a field nothing populates, but a field
populated from the wrong source and never diffed against the one that authored
it.

**Batch 29 -- the demand and macro coupling.** Twenty equations, 40 nodes
coupled, no rule. The batch is authored from two research packs
(`docs/research/coupling-packs/demand-sector.md` and `macro-fiscal.md`), and
the two packs disagree about what a coupling build can do, which is the
batch's content.

*The demand family closes; the macro block does not.* Twenty-one demand nodes
close: four become equation targets (the desalination load, the irrigation
load, the resettlement camp load, the export terminal's throughput), eight
become operands of seven share products, and eight new bases and charges come
into being with them. Nine macro nodes close the same way. Ten macro nodes
defer, and seven of the ten defer on the same two absent levels — a GDP figure
and an import bill in currency. That is not a modelling choice: no formula in
the slice can produce either, so the macro block cannot close until those
bases are declared.

*The pack that refused a computable answer.* `remittance_dependency` is
computable today as remittances over household income, and the pack deferred
it anyway. The name denotes a share of GDP in the literature; the household
ratio would be a true number behind a false label, and a node that reads as
closed is worse than one that reads as deferred. This is the one defer in the
batch whose reason is definitional rather than a missing operand, and it is
recorded as such.

*The signed-range lesson, applied once.* `strategic_reserves` is built on days
of total demand rather than days of net imports, which is the IEA convention.
Net imports are signed and zero at defaults, so an import-based stock needs an
`abs` the DSL cannot differentiate — batch 28 found the same wall from the
other side and widened a range instead. Here the identity is rebuilt rather
than the range, and the prose states the basis.

*The finding inside the equations.* `heat_pump_cop` was a device parameter
with nothing to do. It now enters as `(1 - 1/COP)`, the fraction of resistive
heat's electricity a heat pump does not draw, so the node determines a saving
rather than a load. That is the only reading of a COP that produces
arithmetic, and it makes 535,714 MWh/year of displaced electricity at the
shipped 5% adoption.

*The prose figure that was wrong.* The pack predicted an LPG subsidy bill of
6.0e7 USD/year; the equation computes 1.5e8 — 0.5 USD/kg over 2 M LPG-using
households burning 150 kg each. The pack's own operand set gives the second
number, so the predicted figure was arithmetic done at the wrong household
count. The shipped prose carries the computed value. Numbers written into prose
before the run are guesses wearing measurements' clothes, and this one was
caught by the run rather than by review.

**Deferred by name.** Eighteen demand nodes defer, each on a stated missing
base: arable hectares, freight tonne-km, crop tonnes, tourist-nights, camp
population, shelter occupancy, installation counts, mining energy, effluent
volume, cold-storage volume, construction energy, airport and port operations
energy, machinery energy. The pack lists the eight specific-energy intensities
that would unblock seven of them and names where to look; none is archived, and
the pack says the equation should not ship until the work is on disk. Inventing
a kWh per hectare would close one node and leave a coefficient nobody can
check.

**Batch 30 -- the supply, emissions and grid layer.** Ten products and two
ceilings over thirty nodes, authored from
`docs/research/coupling-packs/supply-emissions-grid.md`. The pack's forty-two
nodes split on the seam the slice itself has: the capacities and employment
factors have bases the graph already carries, the pollutants have none. Five
nodes derive in the pack's reading, twenty-four are read, thirteen defer. The
batch lands close to that split -- twenty placeholder nodes are retyped, ten
products are determined, two shipped equations are rewritten, and thirteen
nodes defer.

*The pollutants defer as one family, not thirteen times.* The catalog's own
`param_eqn.md` writes `nox_emissions <- generation_coal, generation_gas`, and
`generation_coal` is not a node. The graph's only activity base is
`generation_twh`, a fleet total, and `emission_factor_*` covers CO2 alone. Seven
pollutant masses therefore defer on the same missing base -- generation
disaggregated by technology -- and the batch records that as one deferral with
seven names rather than seven rows that each say the same thing. Inventing a
per-TWh NOx factor would close seven nodes and leave a coefficient nobody can
check against a source that does not exist.

*The bound-edge bug that shipped twice before it was caught.* The first form of
the ceiling loop read `for sym in binder`, where `binder` is one symbol name and
not a collection, so it walked the string's characters: forty-nine one-letter
edges and a self-loop per named symbol. A fragment carrying that validates on
its own -- every endpoint exists, the equation holds every symbol it names --
and the merged graph keeps it, so nothing in the chain refused a graph whose
bound edges named no coupling at all. The count that exposed it was the edge
total falling instead of rising when the disposal rule was applied: the two
rewritten water edges left, and what replaced them was characters. The loop now
emits one edge from binder to bounded, asserts both endpoints are nodes and
asserts the pair is not a self-loop.

*The ceilings ship as inequalities because the DSL cannot differentiate a
clamp.* `min`, `max`, `abs`, `floor` and `ceil` have no derivative rule, and
`gradients()` differentiates every equation in the library. A sustainability
limit written as `biomass_capacity = min(biomass_capacity, limit)` would be a
clamp the walker cannot read; written as `limit >= biomass_capacity` with the
limit as binder and the capacity as the bounded variable, it is a bound the
constraint register already knows how to handle, and the two new bound edges run
binder to bounded rather than as self-loops -- a self-loop claims no coupling,
which is the opposite of what a ceiling is for. `biomass_sustainability_limit`
and `water_availability` are the two binders, and the `_BOUND_EDGE` map in
`prg_coupler.py` exists because the bound equation's own symbol set contains
both sides and cannot name the direction.

*The employment double count that did not ship.* Seven employment factors at
jobs/MW would each be a second count of the same job if the graph already
carried a job total, and it does: `direct_jobs` is 43,000 at defaults. The batch
therefore ships an intensity -- `fleet_employment_intensity_jobs_per_mw`,
4.169 jobs/MW over the 9,700 MW fleet -- as a determined node the factors feed,
rather than a competing headcount. `transmission_jobs` is the one genuine
product (route-km times jobs/km, 36,000 at defaults) because no shipped node
counts transmission construction jobs at all.

*Two shipped equations rewritten, and the edges they orphaned.*
`fleet_build_balance` now sums all eighteen build technologies, the six
conversion-plant capacities among them, so a plant built by the waste or biogas
family enters the same balance as a wind farm. The water constraint was
rewritten from a two-operand sum to `water_availability * water_availability_m3
>= total_water_demand_m3`, with the availability factor retyped from the
catalog's `(0, 1e6)` placeholder to a dimensionless `[0, 2]` at default 1.0.
Both rewrites orphan shipped edges -- the old constraint named
`cooling_water_demand_m3` and `desalination_water_demand_m3` directly -- and the
bake drops an edge whose equation was corrected and whose corrected arithmetic
no longer names its source. That rule is the loader's own, and the first bake
attempt omitted it: the fragment validated alone and the merged graph then
refused two edges whose equation no longer held them. The bake now applies the
loader's disposal and prints each dropped edge by name.

*Verified at defaults.* `baseline_emissions` 70.78 MtCO2/year,
`regulation_reserve` 170 MW, `black_start_capability` 4.4 units,
`lifeline_threshold` 1.0 MWh/year, `transmission_lead_time` 4.5 years,
`fleet_employment_intensity_jobs_per_mw` 4.169, `transmission_jobs` 36,000,
`spare_parts_carrying_cost_usd_per_year` 25.11 USD million,
`hydrogen_storage_capex_usd` 0.0 (no electrolyser at defaults, which is the
honest zero), `circuit_breaker_density_per_km` 0.0111. The two ceilings hold at
defaults: 9,700 MW of build against a 15,000 MW sustainability limit, and
1.0 x 2.0e8 m3 of available water against 9.32e7 m3 of demand.

*Register movement.* Parameters 1,312 to 1,317, equations 437 to 449, edges 919
to 958, uncoupled 393 to 365 -- the batch couples twenty-eight, the other two of
its thirty nodes having been named already. The constraint register counts 446
hard, one informational and two soft. The derived-node audit moves to 159
checked and 253 skipped: `baseline_emissions` reads the emissions total the
solve reports, the other nine read fleet capacities, employment factors or the
WACC and are skipped because the result does not carry their bases. The
uncertainty register is unchanged in its inputs and derived-stochastic counts --
none of the ten products is stochastic -- and its reach moves 149 to 150 on
`baseline_emissions` alone.

**Batch 31 -- the product remainder.** Thirty-four equations over fifty
nodes, authored from
`docs/research/coupling-packs/threshold-product-remainder.md`. The pack covers
sixty-six: twenty-five THRESHOLD and forty-one PRODUCT. This batch takes the
PRODUCT arithmetic and the retype both classes need. The twenty-three THRESHOLD
bounds are batch 32, because a bound and an equality couple a node by different
mechanisms and one batch over both would leave the edge register unable to say
which equation coupled which node.

*Six nodes were already coupled and the batch does not touch them.*
`archaeological_sites_density`, `sacred_sites_density`,
`synthetic_fuel_share_aviation`, `synthetic_fuel_share_shipping`,
`distribution_network_km` and `hydrogen_storage_capacity` are named by shipped
equations. The pack records what closed each rather than proposing a second
equation, which is the register's own rule: a node with one consumer and a
second proposed one is a duplicate waiting to disagree.

*Three shipped equations read the wrong operand, and each amendment is a
factor.* `coal_eaf_definition` read the *generic* `forced_outage_rate`, which
`availability_definition` derives from MTBF/MTTR as 24/50024 = 0.00048. That
is a 0.05% forced-outage rate for a coal fleet, against the 10%
`forced_outage_rate_coal` carries: a factor of 200, and the shipped equation
read the wrong one. Coal availability moves 0.9495 to 0.85.
`lcoe_wind_definition` divides by `capacity_factor_wind_onshore` -- it is an
onshore LCOE -- but read the generic `opex_fixed_wind` (40) rather than
`opex_fixed_wind_onshore` (30); the LCOE moves 66.53 to 63.67 USD/MWh. The
alternative, aliasing `opex_fixed_wind` to the onshore node, was rejected: it
makes a shipped node derived and drops its 40 default to fix an equation that
is the actual defect.
`transmission_investment_definition` did not name
`transmission_cost_multiplier` at all, so a terrain-and-tender dial was a knob
nothing multiplied.

*The defect the amendment exposed and did not fix.*
`transmission_investment_definition` computes 48 bn USD for a 10 GW fleet,
because it multiplies `capex_transmission` (USD/MW-km) by total *fleet* MW
rather than route MW. The correct form needs a route-MW base the graph does
not carry, and inventing one would put a second unverified number behind the
first. The batch records the defect in the equation's own description rather
than silently inheriting it or papering over it with a fabricated base.

*Two default corrections ship with the couplings that expose them.*
`distribution_loss_factor` moves 0.5 to 0.06 and its range narrows to
[0, 0.2]. Half of all delivered energy lost is not a loss rate; at the shipped
46.54 TWh demand the placeholder loses 23.27 TWh, which the new product
equation prints as a number rather than leaving as a dial nobody multiplies.
`water_stress_index` becomes derived: it is the ratio of two graph nodes and
computes 0.466, so its shipped 0.4 could not survive being computed.

*The alias rule, and where it stops.* Six duplicate ids carry one physical
quantity under two names and their shipped defaults disagree:
`capex_gas_ccgt` (1,100) against `capex_gas` (1,100),
`csp_storage_hours` (24) against `thermal_storage_duration` (8),
`fuel_cost_hydrogen` (120) against `hydrogen_price_per_mwh` (90.01),
`hydro_capacity_factor` (0.5) against `capacity_factor_hydro` (0.55),
`demand_response_capacity` against `interruptible_load_mw`,
`demand_response_potential` against `interruptible_load_share`. Each becomes
derived, so it cannot drift. The rule stops where the two ids name *different*
quantities that merely look alike: `solar_thermal_capacity` against
`csp_capacity` is a technology label against a capacity, so it is retyped and
bounded in batch 32 rather than aliased.

*The unit the walker caught.* `cat_bond_spread` shipped as bare
`basis_points`, which the registry reads as dimensionless, so the coupon
equation's right side resolved to `USD * MW / kW` against a left side of
`USD/year` -- inconsistent by a factor of time. A spread is quoted per annum,
and retyping it to `basis_points/year` is the fix: the equation's `0.0001`
converts basis points to a fraction and the `/year` supplies the period. This
is the first new inconsistency the walker caught inside a batch since the
density-of-state work; the batch's own dimensional pass found it before the
suite did.

*The edge strength is the equation's, not the edge's.* The first emit gave
the amended wind LCOE hard edges, and the loader refused the graph: the
shipped edges are soft, and an equation cited at two tiers is a reader taking
the strength from whichever edge they read first. The amendment now reads the
shipped tier and keeps it, with an assertion that the equation does not
already ship at two.

*Verified at defaults.* `capex_gas_ccgt` 1,100; `csp_storage_hours` 8;
`demand_response_capacity` 4,250; `demand_response_potential` 0.5;
`fuel_cost_hydrogen` 90.01; `hydro_capacity_factor` 0.55;
`cultural_heritage_sites` 1.0; `available_land_hectares` 2,500;
`parcels_to_assemble` 1,000; `internet_users` 22.5 M;
`mobile_covered_population` 40.5 M; `vulnerable_population` 22.5 M;
`peak_demand_shifted_mw` 12,750; `licence_fee_spend_usd_per_year` 5.0 M;
`transmission_transfer_mw` 5,000; `cat_bond_coupon_cost_usd` 672 M;
`thin_capitalisation_utilisation` 1.553 (the graph's own gearing breaches the
1.5 ceiling by 55%, which the ratio reports and a bound would have failed on);
`crew_shortfall_hours_per_year` 14.4; `spare_parts_deferred_hours_per_year`
19.2; `predictive_maintenance_hours_per_year` 48; `outage_events_from_cause`
4.2; `distribution_losses_twh` 2.79; `hydro_effective_capacity_factor` 0.275;
`wind_effective_capacity_factor` 0.20; `solar_effective_capacity_factor` 0.11;
`precipitation_adjusted_flow_m3_per_s` 75; `representative_snapshots` 1,200;
`water_stress_index` 0.466.

*Register movement.* Parameters 1,317 to 1,338, equations 449 to 477, edges
958 to 1,011, uncoupled 365 to 335 -- the batch couples thirty. The constraint
register counts 474 hard, one informational and two soft. The derived-node
audit moves to 164 checked and 440 skipped. The uncertainty register loses one
input: `fuel_cost_hydrogen` became an alias carrying `determinism: fixed`, so
a stochastic settable knob left the input register -- the intended effect of
one dial replacing two, recorded rather than silently accepted. Six products
with a stochastic relation join the derived-stochastic count (42 to 48), and
the reach moves 150 to 159. Dimensional walk: 466 consistent, 11 inconsistent,
0 undecidable -- the same eleven that predate the coupling build, none added.

**Batch 32 -- the THRESHOLD class.** Twenty-two bounds over twenty-two nodes,
from the twenty-five THRESHOLD rows in
`docs/research/coupling-packs/threshold-product-remainder.md`. Batch 31 took
the PRODUCT class and the retypes both classes needed; this batch takes the
inequalities.

*The class is structurally different from every batch before it.* A product
equation *determines* a node: the node becomes derived, loses its default and
enters `computed()`. A bound determines nothing. It says the node must sit on
one side of a quantity that already exists, and the node keeps its range and
default. `_a_derivation_has_exactly_one_target` enforces that -- a non-`eq`
relation carrying `determined_variables` is refused -- so every row ships
`determined_variables: ()`. The register consequence is exact and worth
stating: the batch moves the edge register and the constraint count, and
`computed()` stays at 440. A THRESHOLD node couples by being *named*; it does
not become a function of anything.

*Fourteen route `bound` and eight route `unbound`, and the prose says which.*
An `unbound` row has an endogenous left-hand side -- `coal_capacity`,
`gas_capacity`, `hydro_capacity`, `nuclear_capacity`, `solar_pv_capacity`
(twice, for the land and build ceilings), `storage_capacity_mw` and
`thermal_storage_capacity` -- so it is a post-solve feasibility check on the
solve's answer, not an LP constraint on the programme. Both are worth shipping
and neither should be counted as a restriction on the optimiser, so each row's
description says which it is. The split is read off the graph rather than the
pack: the pack states a routing for eleven of its twenty-five rows, and the
classification here follows the left-hand side's role, which is the property
that actually decides whether the optimiser can see the constraint.

*Three rows do not ship.* `remedy_periods` is deferred pending a
`max_remedy_period_days` base: its declared range is already [1, 365], so any
ceiling at 365 restates the range and can never fail, and a bound that cannot
fail is not a bound. `hydrogen_storage_capacity` is already coupled by the
shipped storage-capex equation; its MWh ceiling is deferred pending a
`hydrogen_storage_duration`, because the graph carries no hydrogen duration
and borrowing thermal storage's 8 h would make an unrelated dial move the
bound. `solvency_capital_ratio` is deferred for a third reason, and it is the
one worth stating: the pack's proposed floor is `>= 1.0`, a comparison against
a literal. It is *not* a tautology -- the node's range is [0.8, 3.0], so a
shipped 0.9 would violate a 1.0 floor -- but a literal right-hand side names
no binder node, and the graph's bound shape runs binder -> bounded. Shipping
it would put an equation in the document that no edge carries, which is the
register's own "declared is not produced" defect: the node would leave
`uncoupled()` by being named while the edge register stayed silent about what
couples it. The real fix is a `required_solvency_capital_usd` base the ratio
divides by, and that is another pack's to add.

*Two findings the pack raised and the batch records rather than fixes.*
`solar_pv_max_build` caps the PV *stock*, not the annual build its name
claims, because the graph carries no annual-increment node; the description
says so, and renaming the node or adding `solar_pv_annual_build_mw` is a base
rather than a coupling. `storage_capacity_mw` duplicates two builds it is not
tied to -- 800 MW against battery 300 plus PHS 200 -- and the bound states the
disagreement instead of inventing a third equation to explain it.

*The ceilings that would have been tautologies, and are not shipped.* Three
of the pack's alternatives were rejected on the register's own rule that a
constraint admitting every admissible value constrains nothing.
`fleet_build_balance` membership is 15,000 MW of generation plus headroom,
which admits every value of a node whose range tops at 1e6.
`solar_pv_max_build` against a 20,000 MW ceiling equal to the capacity's own
maximum cannot fail. `remedy_periods <= 365` restates the declared range. Each
rejection is in the shipped equation's description, so a reader can see what
was considered and why it was not used.

*The composite ceilings carry one edge, not one per symbol.*
`storage_capacity_mw <= total_capacity_mw + storage_headroom_mw` and
`thermal_storage_capacity <= storage_headroom_mw * thermal_storage_duration`
bound against expressions, and the graph's edge shape needs one binder node.
The batch takes the expression's first symbol as the edge source and says
"(composite ceiling)" in the description. That is a deliberate narrowing of
the edge's meaning, not an oversight: the alternative is an edge per symbol,
which is how batch 30 shipped forty-nine one-letter edges by iterating a
string. The guard is an assertion that the first symbol is a node and differs
from the bounded one, so a composite that collapsed to a self-loop fails at
emit rather than at load.

*Verified at defaults.* All forty-seven bounds in the document hold; none is
violated. `auction_price_cap` 200 against an escalated carbon price of 81.44;
`coal_new_build` 5000 against a 3000 MW fleet; `gas_new_build` 3000 against
1500; `hydro_new_build` 3000 against 1500; `nuclear_new_build` 5000 against 0;
`solar_pv_land_constraint` and `solar_pv_max_build` 20000 against a 10,000 MW
PV build; `solar_thermal_capacity` 0 against 0 (holds at the boundary, fails
the moment a scenario sets it above the CSP fleet); `storage_headroom_mw`
5000 against four novel storage technologies at 0; `total_capacity_mw` 10000
against six generators at 0; `spare_parts_lead_time` 720 h against a 50,000 h
MTBF; `transboundary_water_constraint` 200e6 m3/year against a 93.2e6 demand;
`storage_capacity_mw` 800 against 15,000; `thermal_storage_capacity` 0 against
40,000 MWh.

*Register movement.* Parameters 1,338 unchanged -- a bound adds no node.
Equations 477 to 499. Edges 1,011 to 1,033: twenty-two constraint edges, one
per bound. Uncoupled 335 to 313, and the dead register falls 318 to 298: the
twenty-two bounds couple twenty-two nodes, but only twenty of them were dead
knobs, because `storage_capacity_mw` and `thermal_storage_capacity` are
endogenous and were never in that register. That is also why the endogenous
witness in the summary test had to move: `storage_capacity_mw` was the node
proving "not every uncoupled node is free", and the bound coupled it, leaving
`firm_build_fleet_mw` as the one endogenous member. The strength register
counts equations and moves 474 to 496 hard, one informational and two soft
unchanged. The citation register moves 199 to 215: sixteen of the twenty-two
bounds cite a work -- thirteen capacity ceilings to Oree et al. (2017), the
carbon auction to EU ETS Directive 2023/959, the CSP ceiling and the thermal
store to IEA/NEA EGC -- and six carry None because each is a definitional
relation between two quantities the graph already carries. `computed()` stays
440, the audit partition stays 164 checked and 276 skipped, the uncertainty
register stays at 75 inputs, 48 derived-stochastic and 159 reach. Dimensional
walk: 488 consistent, the same 11 inconsistent, 0 undecidable -- the eleven
that predate the coupling build, none added by the bounds.

*The bound that was not a tautology and still did not ship.* The summary
test's own docstring once described `free == len(uncoupled()) - 1` as holding
"by coincidence" on the shipped graph, because exactly one endogenous node
was uncoupled there. Batch 32 is the change that ends the coincidence for
good: bounding the storage node made the witness a different node rather than
making the property false, and the test now names `firm_build_fleet_mw`
instead of counting. A count would have gone on passing while the property it
stood for quietly emptied out.

**Batch 33 -- the unclassified remainder.** Twenty-one products, six new
nodes and five bounds, from the residue of the five classification slices in
`docs/research/coupling-packs/unclassified.md`. That pack read 102 nodes no
earlier pack had called and gave 29 of them a proposal, carrying 26 equations.
All 26 ship: twenty-one equalities and five bounds. The nine proposals that add
no equation are `read` -- nodes the products consume as operands.

*What the residue is.* Of the 102, thirty-five are QUALITATIVE -- procedures,
standards and institutional arrangements with no base to multiply -- and ten
are SCENE-SWITCH nodes, run configurations the solver reads rather than
quantities it computes. Those two classes alone are 45 nodes, and no coupling
can reach them: a node whose value is "which procedure was followed" has no
arithmetic, and pretending otherwise is how a graph acquires equations that
compute nothing. Twenty-four are BASE-NEEDED, meaning the pack could state the
formula but the graph carries none of its operands; the 29 that got a proposal
are the 24 PRODUCT rows, the 5 THRESHOLD rows and one GATE-SCENE-SWITCH row.
`demand_growth_rate` is deprecated and should be removed rather than coupled;
it is left alone.

*The six new nodes are the reason this batch is a coupling and not a
renaming.* Each is a quantity the pack computes from two or three bases the
graph already carries, and none is a dial: the excise take, the mapped route
length, the cross-border loss, the electrolyser O&M bill, the rooftop count
and the annual consumer valuation. They are derived on arrival, so
`computed()` rises by exactly the twenty-six products -- 440 to 461 -- and the
parameter count rises 1,338 to 1,344.

*The aliases, and the two the pack flags for deletion rather than coupling.*
Seven of the twenty-one products are aliases of a quantity the graph already
derives: `accelerated_depreciation` of `depreciation_schedule_accelerated`,
`buffer_pool_contribution` of `permanence_parameters`,
`consumer_price_index_link` of `inflation_rate`, `health_impact_dalys` of
`dalys_per_year`, `health_impact_mortality` of `premature_deaths_per_year`,
`ppa_indexation` of `tariff_indexation`, and `premium_share_of_asset` of
`insurance_loss_share_of_cost`. An alias removes a duplicate id from the
settable set, which is the right outcome for a node that was a second
spelling. Two of them deserve a reviewer's attention rather than a
celebration.

`buffer_pool_contribution` may be a *different* object from the permanence
share: `carbon_credit_reversal_allowance_definition` computes
`(1 - permanence_parameters) * carbon_credit_volumes` and calls the complement
the buffer a registry retains. If the contribution rate is the complement and
not the share itself, this alias is wrong by construction, and the node's
coupling is its deletion rather than this equation. The shipped description
carries the question rather than burying it.

`premium_share_of_asset` ships at 0.005 against the catalog's own 0.008, and
the alias is what resolves the duplicate. `insurance_premium_definition`
computes `insurance_loss_share_of_cost * capex_usd_per_kw`, so the two ids
are one premium priced twice. Resolving in favour of 0.005 lowers the shipped
premium by 37.5% -- which is the correct direction if the catalog's 0.008 was
a second dial, and the wrong one if it was the better estimate. The rate is
recorded here as a decision, not a discovery.

*The five bounds, and the one the pack measured but could not ship as a
bound.* `electrolyser_capacity` is a build size whose MW retype had not
reached `config/prg.yaml`; this batch's retype is what makes its floor
meaningful, and the floor holds: 500 MW against the 292.68 MW average draw
the hydrogen programme implies. `fit_capacity_cap` at 4,000 MW admits the
2,702.70 MW VRE build with room and breaks at a 5,000 MW scenario -- a
ceiling equal to the build would be the tautology the sibling pack rejects.
`renewable_penetration_limit` at 0.5 admits the 0.2703 annual VRE share; the
bound compares an *annual* share to an *instantaneous* limit, which is the
weaker of the two claims, because the graph carries no instantaneous
penetration node. `regulatory_period_length` must be at least
`regulatory_lag`, 5 years against 1. `firm_build_fleet_mw` must cover
`firm_capacity_mw`, 10,000 against 9,000.

`firm_build_fleet_mw` is the one a reviewer should delete rather than bound.
Its own description calls it "the identity every build set must satisfy" and
says "the reserve margins read the firm part of it"; both claims are false.
`fleet_build_balance` is the identity, and `firm_capacity_definition` feeds
the reserve margins. The node has no readers, the bound is the first thing
that ever named it, and a bound on a quantity nothing consumes is a coupling
in the register and not in the model. It ships because the standing task is
that no node floats, and the finding is recorded so the next reader can
reverse it with one deletion.

*Three deferrals with stated reasons.* `morbidity_cases_per_year` needs a
morbidity incidence base the graph does not carry. `curtailed_twh` needs a
curtailment-volume source -- the graph has curtailment *shares* and no volume.
The four composite-index components (`institutional_capacity`,
`financial_capacity`, `technical_capacity`, `infrastructure_adequacy`) need
component data no pack proposes, which is also why the three indices they
feed -- `adaptive_capacity`, `resilience_score`, `energy_security_index` --
are BASE-NEEDED rather than PRODUCT.

*Verified at defaults.* Every product evaluates to the value the pack printed:
`fuel_excise_revenue_usd_per_year` 164,974,190.45; `gis_mapped_network_km`
34,200; `cross_border_losses_twh` 0 (a self-sufficient reference case, and
the node is signed so a net export year loses energy on the way out);
`electrolyser_variable_opex_usd_per_year` 1,666,500;
`rooftop_solar_households` 1,000,000; `willingness_to_pay_usd_per_year`
1.5e9; the three depreciation schedules 0.04, 0.08 and 0.04;
`gdp_per_capita_growth` 0.029412; `health_impact_dalys` 57,600 and
`health_impact_mortality` 4,800; `hydrogen_demand_domestic` 49.4 and
`hydrogen_production_demand` 2,563,846.15; `compensation_rates` 7,500. All
five bounds hold with residuals of +207.32, +1,297.30, +0.2297, +4 and
+1,000. All 26 equations pass the dimensional check; `range_excursions()` is
empty and `consistency()` reports no violation.

*Register movement.* Parameters 1,338 to 1,344 -- the six new ids. Equations
499 to 525. Edges 1,033 to 1,075: thirty-seven product edges and five
constraint edges. Uncoupled 313 to 284. The dead register falls 298 to 274: twenty
retyped placeholders became derived, and the six new nodes arrived already
coupled by their own equations, so they were never in it. The gap between
`uncoupled()` (284) and `dead` (274) is the rule register -- ten nodes read by
cross-validation rules and by no equation. The strength register counts
equations and moves 496 to 522 hard, one informational and two soft
unchanged. The citation register moves 215 to 226: six products and all five
bounds carry a work, the fifteen that carry None being the seven aliases and
eight definitional products. `computed()` 440 to 461. The audit partition
moves 164/276 to 165/296 -- one product joins `checked` because
`dalys_per_year` is a value the solve result carries, twenty join `skipped`.
The uncertainty register moves 75 inputs to 74: `willingness_to_pay` was a
stochastic placeholder and is now derived, and its products read fixed
process parameters, so no derived node entered the closure and the total
falls 123 to 122. Dimensional walk unchanged at 488 consistent, the same 11
inconsistent and 0 undecidable.

*The test the batch had to rewrite rather than repin.* Batch 32's summary
test named `firm_build_fleet_mw` as the endogenous witness for "not every
uncoupled node is free". Batch 33's bound names that node, so the register's
endogenous membership went to zero and the witness became false. The
assertion is now that the register is `{"free"}` and that
`firm_build_fleet_mw` is endogenous, uncoupled-by-nothing and uncomputed --
which is the distinction the two registers exist to draw: a bound *names* its
subject without fixing it, so a node can be coupled and computed by nothing
at the same time. Repinning the old witness to a new node would have hidden
that; asserting the new property states it.

**Batch 34 -- the review corrections batch 33 deferred.** One equation
corrected, and the three questions batch 33 left for a reviewer settled. This
is not a coupling batch; it is the batch that reads its predecessor's own
caveats and answers them.

*The sign error, and why it is a defect rather than a duplicate question.*
Batch 24 shipped `carbon_credit_reversal_allowance_definition` as
`(1 - permanence_parameters) * carbon_credit_volumes`. Batch 33 coupled
`buffer_pool_contribution` to `permanence_parameters` and flagged that the two
could not both be right: if the buffer contribution is the complement of the
permanence share, the alias is wrong by construction. They could not both be
right, and the alias was the one that was.

`permanence_parameters` describes itself as "the share of issued volume held
back against non-permanence". Its complement is the volume *not* held back,
which is the opposite of an allowance. The shipped form reported 40.5 of 45
MtCO2/year as the buffer -- a 90% allowance against a 10% share. A buffer that
holds back nine tenths of every issuance is not a permanence mechanism; it is
the share inverted. Batch 34 corrects it to
`permanence_parameters * carbon_credit_volumes`: 4.5 MtCO2/year, and
`buffer_pool_contribution` now agrees with the volume it names.

*The argument stops at the graph.* Registry practice -- the buffer rates
programmes actually withhold -- would corroborate the 10% and is the obvious
place to look next. It is not cited here because no copy of the standards that
state it is archived in `sources/`: Verra serves the AFOLU Non-Permanence Risk
Tool and the VCS Standard behind a 404 or a JavaScript shell, probed on
2026-10-21, and the repository's rule is that a load-bearing citation points at
a file it holds. The correction therefore rests on the graph's own two
descriptions disagreeing, which is sufficient to establish a sign error and is
the whole of what is claimed.

*Why a correction and not a re-bake of batch 24.* The bake merges one equation
body over the shipped one, so re-emitting batch 24 would do the same thing --
but batch 24 predates twenty-odd retypes, and a re-bake would couple this fix
to whether every one of them is still current. Measured before choosing: batch
24's parameters, equations and edges drift from `config/prg.yaml` in **zero**
fields today, which makes the two routes equivalent right now and the narrower
one correct by construction. A batch that owns one equation cannot revert a
node it never names.

*The two remaining questions, settled rather than deferred.* The
`premium_share_of_asset` resolution stands: `insurance_premium_definition`
computes `insurance_loss_share_of_cost * capex_usd_per_kw`, so the catalog's
0.008 was a second dial on a premium already priced, and resolving in favour of
0.005 removes it. `firm_build_fleet_mw` is kept against the pack's deletion
recommendation: it is endogenous and named by `firm_build_fleet_bound`, so it
is coupled and not floating, and deleting it would remove a bound that holds
at defaults and leave the fleet build with no ceiling. A deletion is right for
an alias and wrong for a decision variable.

*Register movement.* None. Parameters 1,344, equations 525, edges 1,075,
uncoupled 284, computed 461 -- all unchanged, because a corrected right-hand
side names the same two operands. The only movement is the value:
`carbon_credit_reversal_allowance` 40.5 to 4.5 MtCO2/year.

*The regression pin.* `test_the_reversal_allowance_is_the_share_and_not_its_complement`
asserts the identity, the value, and the wrong value *against* -- a test that
could not tell 4.5 from 40.5 would have passed on the defect. Canaried by
reverting the equation in `config/prg.yaml` and re-running: it fails with
`assert 40.5 == (0.1 * 45.0)`.

## Evaluation of the design docs against the code (2026-10-17)

**`docs/how_prg_works.md` (read-only; a teaching narrative, not read as spec).**
Where it describes *mechanisms* — roles, the two-phase propagation, the
conflict kinds, loop handling, the audit — the built engine matches: §2's four
super-spreadsheet powers are real code (`graph.py`, `feedback.py`,
`conflicts.py`, `constraints.py`), and the worked example's *shape* (consistency
check → propagation → loop iteration → translation → constrained solve) is the
`PrgSolve` pipeline. Where it states *behaviours the code contradicts*:

1. **§6 Mechanism 4 presents Anderson acceleration as the solver** — it was
   measured and *rejected* (63/45 turns vs 38/36; m=2 fails convergence within
   200): shipped is damped Gauss–Seidel, and `prg-status` records the
   rejection.
2. **"max_iter (default 20)"** — the shipped budget is 200, not 20.
3. **"~2,500 edges / ~120,000 constraints / 20 systems"** — target numbers,
   not facts: 375 edges / 13 bindable inequalities (+2 LP-carried fleet
   constraints...) — actually 10 bound routes today — over 156 equations and
   54 rules; a design target, and the register is the count.
4. **§7's single `POST /v1/prg/propagate`** — the API is the tiered §43
   surface (`/prg/propagate` is analyst-tier; there is no single
   public-compute endpoint).
5. **§7's dashboard slider/popup** — no UI exists; the delivery surface is the
   API, the SDK and the CLI.
6. **"Caching to avoid recomputing unchanged parameters"** — now actually
   built (`propagate_incremental`, 9× a full walk and pinned equal to the full
   propagation, categorical-perturbation included), so this one is *ahead of*
   the older parts of the narrative; but the caching claim in §3's "load"
   sense is the parse cache, which is where the workload's cost actually was.
7. **The example equations and node ids** (`carbon_price_coal_retirement_consistency`,
   `coal_capacity_2035`, `total_cost` with generator `sum(...)` syntax) — not
   in the library; the DSL carries `Sum`, not arithmetic generators, and
   §25's cross-validation rules are the real home of consistency conditions.

Verdict: **read as intent, as its own §1 says of the design docs; nothing in it
contradicts the engine's contracts, but five of its behaviour claims are
aspirational.** The teaching value is real; the doc is not a contract.

**`docs/prg-exam.md` (another agent's review; reviewed here, left unedited).**
Its qualitative core is right: design intent vs the honest register vs the code
is the load axis, the four core subsystems are real, and the L1 ratings for
conflict detection and correction suggestions are stale relative to what
`conflicts.py` + `constraints.py` + the API actually serve. But its *numbers*
are frozen at 2026-10-16 and this build moved them:

| Claim in `prg-exam.md` | Status at this build |
|---|---|
| Nodes 869, edges 88, equations 39, 2 feedback loops | 1075 / 375 / 156 / 2 — the coupling build moved all but the loop count |
| "~88 have real arithmetic; 781 are `role: free` placeholders" | 141 derived equations over 141 determined variables live; 717 nodes remain uncoupled, each named with its coupling class in the worklist |
| "8 of the 39 equations dimensionally inconsistent" | 12 of 156 — and **all 156 are decidable** (0 undecidable), which the pre-coupling walker could not claim |
| "2 bindable inequalities + 4 post-solve checks" | **10 bound routes bind** a linopy solve (carbon budget, reserve margins, the sector-demand bound, the employment/CCS/electrification and retention bounds, the two regulatory allowed-return caps) |
| "Incremental updates L0, not started" | Stale: `propagate_incremental` is built, tested equal to a full propagation, and 9× a full walk |
| "Conflict detector/corrections L1 stale vs built" | Confirmed — L4+ |
| "49 of 52 settable parameters reach no what-if knob" | Still true in kind, now 912 of 915 settable reach no knob; the translation layer remains the honest bottleneck |

The one place `prg-exam.md` is *wrong* rather than stale: it takes the
capability matrix's "incremental updates L0" as evidence the feature is absent
while the code carries it — the same "an inventory read from source is not an
inventory the app serves" lesson, in the review's own review.
