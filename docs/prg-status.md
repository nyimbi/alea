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
