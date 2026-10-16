# Ingestion format for parameter equations

The target: every one of the 869 graph parameters either determined by an
equation or named by one, with the coupling declared. This file states the
format to generate **into**, and the gates a generated batch must pass before
it is loaded.

## Why the current documents cannot be ingested

Measured against the shipped tree (`docs/param_eqn.md`, `docs/param_eqn_formula.md`,
`docs/param_eqn_formula1.md`, `config/prg.yaml`). These are not complaints about
the documents; they are the reason a converter cannot be written and a
generator is needed.

| Measurement | Value | Consequence |
|---|---|---|
| Rows in `param_eqn.md` | 824 | — |
| Distinct row parameters | 787 | all 787 are graph nodes |
| Arrows in `param_eqn.md` | 1,583 | the linkage layer, if it were addressable |
| **Formulas in `param_eqn.md`** | **0** | every row is arrows, no arithmetic |
| Cited names absent from the graph | 266 | 261 cited only by uncoupled rows |
| `param_eqn_formula.md` PART B rows | 237 | only 5 of 28 categories |
| `param_eqn_formula1.md` PART 4 rows | 410 | categories 6–28; 59 carry direction columns |
| Formula rows with a real expression | 647 | B 237 + formula1 410 |
| Formula rows whose RHS names a graph parameter **verbatim** | **4** | 0.6% |
| Formula rows whose LHS names their **own** parameter | **0 of 237** | see below |
| Shipped equations | 39 | 31 consistent, 8 inconsistent dimensionally |
| Shipped edges | 88 | all cite an equation holding both endpoints |
| Nodes with role `free` | 781 | 691 share one default (500000.0) and one range |

Three findings decide the format.

**1. The formula documents are not about these parameters.** The row for
`demand_growth_rate` gives `$D_y = D_0 \cdot (1+g)^y$` — the left-hand side is
`D_y`, a demand *quantity*, not `demand_growth_rate`. Zero of 237 rows in PART B
define the parameter they are listed against. The formulas describe the physics
of a power system; the graph's parameters are the free symbols in them. An
equation like `demand_twh = base_demand_twh * (1 + demand_growth) ** horizon_years`
is the correct translation of that row — and note the graph already ships it,
while none of its four symbols is a row parameter. So the generator must
**write the equation over graph ids**, which is a modelling act, not a
transcription.

**2. The linkage layer is not addressable.** `param_eqn.md` states 1,583 arrows
and 1,085 of them have both endpoints among the graph's nodes. But every edge in
this schema must cite an `equation_id` that exists (`graph.py:729`), and
`depends_on` / `affects` read the *equations*, not the edges (`graph.py:633`,
`graph.py:656`). An edge is a declaration that rides on an equation; it cannot
stand alone. So "linked" and "equationed" are one deliverable here, not two.

**3. The missing 266 are quantities, not parameters.** Names like
`available_capacity`, `clearing_price`, `curtailment`, `busmap`, `lcoe` appear in
the arrows and in the formulas but are not graph nodes. They are dispatch
outputs and intermediate quantities. An equation may not use them unless they
are first *declared as parameters* (with unit, range, default) or eliminated
from the right-hand side.

## The format

Four registers, all under `config/prg_ingest/`. A batch may be one file or one
file per category; the loader merges fragments and refuses a duplicate id whose
bodies differ.

### Register 1 — `parameters`

Only for nodes being **added** or **corrected**. An entry that restates the
shipped value is refused as drift, not merged silently.

```yaml
parameters:
  peak_demand_mw:
    name: Peak demand
    description: System peak demand in the planning horizon
    category: Demand-Side          # one of the 28 catalog categories
    type: float                    # float|int|bool|categorical|timeseries|spatial
    unit: MW                       # REQUIRED for float and int
    range: [0.0, 500000.0]         # REQUIRED for float and int
    default: 30000.0               # required for free/exogenous/endogenous; FORBIDDEN for derived
    role: exogenous                # exogenous|endogenous|derived|free
    determinism: policy            # fixed|stochastic|policy|physical
    priority: P1                   # P1|P2|P3
    status: to_build               # existing|to_build|integrate
    source: docs/params.md#1.5
    users: [Planners]
```

Rules the loader enforces (each is a hard error):

- `default` must lie inside `range`.
- `role: derived` must **not** carry a `default`.
- `role: endogenous` **must** carry both `range` and `default`.
- `initial` is valid only on a `derived` node that carries a `range`.
- A `timeseries` or `spatial` node may not carry a scalar `default` or `range`.
- The 691 `free` nodes currently share `range: [0.0, 1000000.0]` and
  `default: 500000.0`. A corrected entry replaces that placeholder with the
  parameter's real admissible set, or the range gate will admit nonsense.

### Register 2 — `equations`

The evaluable layer. One entry per determined variable.

```yaml
equations:
  demand_definition:
    name: Demand trajectory
    description: Compound growth from the base year over the horizon
    system: energy_balance        # one of the 17 SYSTEM_IDS
    lhs: demand_twh
    rhs: base_demand_twh * (1 + demand_growth) ** horizon_years
    relation: eq                  # eq|leq|geq
    parameters: [base_demand_twh, demand_growth, horizon_years]
    free_variables: [base_demand_twh, demand_growth, horizon_years]
    determined_variables: [demand_twh]
    tolerance: 1.0e-6
    unit_check: true
    priority: P1
```

Rules the loader enforces:

- Every symbol in `lhs`/`rhs` must be a declared parameter id, or a DSL
  function or reserved word.
- `parameters ∪ free_variables ∪ determined_variables` must equal **exactly**
  the set of symbols the arithmetic names. A symbol in the arithmetic but not
  in the lists is a coupling the graph would not report; a listed symbol absent
  from the arithmetic is a coupling the engine would never apply. Both are load
  errors (`graph.py:760`, `graph.py:767`).
- Every `determined_variables` entry must have `role: derived`.
- At most one equation may determine a given parameter.
- `lhs` must reduce to a single parameter id, or to a linear combination of
  them whose determined variable is the subject.
- `system` must be one of the 17 library systems.

**DSL grammar.** Arithmetic `+ - * / **`; parentheses; the function set
`abs acos asin atan ceil cos cosh erf exp floor ln log log10 log2 max min sin
sinh sqrt tan tanh`; subscripts `x[i]`; and an explicit summation
`sum(x[i] for i in range(0, 8760))` with integer bounds. Identifiers must be
valid Python identifiers and may not be reserved words (`sum`, `range`, `for`,
`in`, `and`, `or`, `not`, and every function name).

### Register 3 — `relationships`

The declaration layer. Every edge cites an equation that holds **both** its
endpoints.

```yaml
relationships:
  - source: demand_growth
    target: demand_twh
    equation_id: demand_definition
    relationship: functional      # equality|inequality|functional|constraint|feedback|temporal|stochastic
    direction: forward            # forward|backward|bidirectional
    strength: hard                # hard|soft|informational
    description: Growth rate scales the demand trajectory
    priority: P1
```

Rules:

- `source` and `target` must be declared parameters, must differ, and must both
  appear in the symbols of `equation_id`. All 88 shipped edges obey this; it is
  the house convention and nothing currently enforces it.
- `relationship: inequality` requires the cited equation to have
  `relation: leq` or `geq`; `equality` requires `eq`.
- An equation may carry many edges. An edge is a claim about a coupling, not a
  restatement of the equation.

### Register 4 — `cross_validation`

Conditions spanning parameters that no single equation states. This is where a
relation the formula documents express as an inequality but which has no
determined variable belongs.

```yaml
cross_validation:
  - id: reserve_margin_vre_penetration
    condition: reserve_margin_min < 0.10 and vre_capacity_target_mw > 20000
    severity: error               # error|warning|info
    message: A reserve margin floor below 10% with a 20 GW-plus VRE target is a system with no firm capacity
    suggestion: Raise reserve_margin_min, or lower vre_capacity_target_mw
```

A rule naming a parameter the scenario does not carry is reported as
*undecided*, never dropped.

## The gates a batch must pass

A generated batch is loaded only if all of these pass. Each is canaried against
a planted instance of the defect it names.

1. **Schema** — every entry parses against the models with `extra="forbid"`.
2. **Identity** — no id added, renamed, or removed outside the batch's own
   declared additions; no parameter id spelled two ways.
3. **Closure** — every symbol in every `lhs`/`rhs` is a declared parameter.
   This is the gate that catches the 266 quantity names.
4. **Exactness** — `parameters ∪ free_variables ∪ determined_variables` equals
   the arithmetic's symbol set, both directions.
5. **Role consistency** — determined ⇒ `derived`; no default on a derived node;
   range and default on every endogenous node.
6. **Edge support** — both endpoints of every edge appear in the cited
   equation, and the edge's `relationship` agrees with the equation's
   `relation`.
7. **Dimensional** — the existing unit walker decides each equation; a batch may
   not increase the count of inconsistent equations (currently 8 of 39).
8. **Coverage, reported not gated** — how many of the 869 are now determined,
   named, or still uncoupled. The number is the progress measure; it is not a
   pass condition, because a correct batch may legitimately leave a metadata
   parameter uncoupled.

## What the generator must not do

- **Do not rename graph parameters to match a formula.** Use the ids in
  `config/prg.yaml` verbatim. The 4-of-647 verbatim match rate is the whole
  problem; a generator that renames makes it worse, not better.
- **Do not emit an equation whose left-hand side is a physics symbol** (`D_y`,
  `\text{LF}`, `C^{\text{solar}}_y`). The left-hand side is a graph parameter id.
- **Do not use one of the 266 absent names** without declaring it first, with a
  unit and a range.
- **Do not write an edge citing an equation that does not hold both endpoints.**
- **Do not give a `derived` node a default**, and do not make a `free` node a
  determined variable.
- **Do not invent a range.** A parameter whose admissible set is unknown stays
  `role: free` with the placeholder range, and is reported as uncoupled. A
  fabricated range is worse than a missing equation: the range gate refuses a
  caller's value against it, so a wrong range silently rejects correct input.

## Order of work

1. Registers 1 and 4 first — they need no new equations and close the
   inequality-shaped relations and the placeholder metadata.
2. Then Register 2 per system, starting with the 17 systems the library already
   holds, extending the shipped 39 equations.
3. Register 3 last, generated from the equations rather than written by hand:
   an edge is a projection of an equation onto a pair of its symbols.

## Sources

- `docs/param_eqn.md` — the linkage spec: 824 rows, 1,583 arrows, no formulas.
- `docs/param_eqn_formula.md` — PART A system formulas, PART B 237 parameter
  rows (categories 1–5), PART C worked example, PART D implementation notes.
- `docs/param_eqn_formula1.md` — coverage audit, direction convention, 24
  metadata-only parameters, PART 4 formulas for categories 6–28.
- `docs/params.md` — the 784-row catalog with an `algorithm` column (prose, not
  expressions).
- `config/prg.yaml` — 869 nodes, 39 equations, 88 relationships, 4 rules.
