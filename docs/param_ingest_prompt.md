# Prompt: generate the PRG ingestion batch

Issue this to the agent that produced `docs/param_eqn.md`, `docs/param_eqn_formula.md`
and `docs/param_eqn_formula1.md`. It is self-contained: it restates the target
schema and every rule the loader enforces, so the generating agent needs no
access to `src/`.

---

## TASK

Produce the parameter–equation ingestion batch for the ALEA PRG, in the exact
format below. The three documents you wrote describe the *physics* of a power
system. The PRG is a graph over **869 named parameters**, and it needs the
arithmetic written **over those parameter ids**. Your documents cannot be
converted — measured: 1,583 arrows and zero formulas in `param_eqn.md`, and
**0 of 237** rows in `param_eqn_formula.md` PART B define the parameter they are
listed against. That translation is the work.

## THE ONE RULE THAT DECIDES SUCCESS

**Every equation's left-hand side must be a parameter id from `config/prg.yaml`,
and every symbol on the right-hand side must be too.**

Your row for `demand_growth_rate` reads `$D_y = D_0 \cdot (1+g)^y$`. `D_y` is a
demand *quantity*. It is not a parameter. The correct equation for that physics
is:

```yaml
lhs: demand_twh
rhs: base_demand_twh * (1 + demand_growth) ** horizon_years
```

`demand_twh`, `base_demand_twh`, `demand_growth` and `horizon_years` are all
graph ids. Note that none of them is a row in your table, and that the graph
already ships this exact equation — which is the standard to hit.

**That equation is illustration, not a task.** It exists as `energy_demand` in
`config/prg.yaml`, so rule 14 below forbids adding it again. Find the parameters
that have no equation yet and write those.

Do **not** rename a graph parameter to match a symbol in a formula. Do **not**
emit an equation whose left-hand side is `D_y`, `\text{LF}`, `C^{\text{solar}}_y`
or any other physics symbol. Do **not** use a name that is not in
`config/prg.yaml` — names like `available_capacity`, `clearing_price`,
`curtailment`, `busmap`, `lcoe`, `cfads` appear in your arrows and formulas but
are **not parameters**. If such a quantity is genuinely needed as an input,
declare it in Register 1 first, with a unit and a range; otherwise eliminate it
from the right-hand side. **That list is illustrative, not exhaustive:** there
are **266** such names in your documents. The full list is every name your
arrows and formulas cite that `config/prg.yaml` does not declare.

## READ FIRST

1. `config/prg.yaml` — the authoritative list of **869 parameter ids**, their
   current `role`, `range`, `default`, `unit`, `category`; the **39 shipped
   equations** (your models to extend) and **88 relationships**. Your output
   must use these ids verbatim.
2. `docs/param_eqn.md` — your linkage table. Useful as a *hint* about which
   parameters relate; its **1,085 authorable arrows** (of the 1,583 it states)
   suggest couplings. It states no arithmetic, so it cannot be transcribed.
3. `docs/param_eqn_formula.md` and `docs/param_eqn_formula1.md` — your formula
   reference. Useful for the physics; the left-hand sides need rewriting.
4. `docs/params.md` — the 784-row catalog. Its `algorithm` column is prose
   ("Logistic / Gompertz growth curve"), not an expression.

### The four totals, reconciled

They are different counts of different things. Do not use one where another is
meant.

| Number | What it counts |
|---|---|
| **869** | parameters in the graph (`config/prg.yaml`). The authority. |
| **787** | distinct parameters with a row in `docs/param_eqn.md`. All 787 are graph nodes; the other **82** nodes have no row. |
| **781** | graph nodes whose `role` is `free` — 869 − 88, where the 88 are 33 `derived` + 52 `exogenous` + 3 `endogenous`. |
| **784** | rows in the `docs/params.md` catalog. A fourth thing: a row may cover a node, or describe a quantity the graph does not carry. |

**1,583 vs 1,085 arrows.** `param_eqn.md` states 1,583 arrows in total. **1,085**
of them have *both* endpoints among the graph's 869 nodes, and only those are
addressable; the other 498 name at least one of the 266 non-parameter quantities.

## OUTPUT FORMAT

Four YAML registers. One file per category is preferred; a single file is
acceptable. A duplicate id across fragments with differing bodies is an error.

### Register 1 — `parameters` (only nodes you ADD or CORRECT)

```yaml
parameters:
  peak_demand_mw:
    name: Peak demand
    description: System peak demand over the planning horizon
    category: Demand-Side            # one of the 28 catalog categories
    type: float                      # float|int|bool|categorical|timeseries|spatial
    unit: MW                         # supply it whenever you know it
    range: [0.0, 500000.0]           # required for endogenous; strongly wanted everywhere else
    default: 30000.0                 # required for free|exogenous|endogenous; FORBIDDEN for derived
    role: exogenous                  # exogenous|endogenous|derived|free
    determinism: policy              # fixed|stochastic|policy|physical
    priority: P1                     # P1|P2|P3
    status: to_build                 # existing|to_build|integrate
    source: docs/params.md#1.5
    users: [Planners]
```

Do not restate a shipped value that is already correct; an entry that disagrees
with `config/prg.yaml` is reported as drift, not merged.

**What is actually required, as opposed to what you should supply.** Only three
of these are loader rules: `default` inside `range`; `range` and `default` both
present on an `endogenous` node; no `default` on a `derived` node. `unit` and
`range` are **not** required on a `free` or `exogenous` float node — a node with
neither loads cleanly. Supply them anyway wherever you know them, because
without a `range` the range gate cannot refuse a caller's nonsense value, and
without a `unit` the dimensional walker cannot decide any equation the node
appears in. Both are what makes the parameter *usable*, not merely loadable.

**691 of the 781 `free` nodes currently carry placeholder metadata:**
`range: [0.0, 1000000.0]` and `default: 500000.0`. If you have the real
admissible set for one of them, correct it here. **Do not invent a range.** A
fabricated range is worse than a missing equation, because the range gate
refuses a caller's value against it — a wrong range silently rejects correct
input. If the admissible set is unknown, leave the node `free` and report it
uncoupled.

### Register 2 — `equations` (the evaluable layer)

```yaml
equations:
  demand_definition:
    name: Demand trajectory
    description: Compound growth from the base year over the horizon
    system: energy_balance           # one of the 17 systems listed below
    lhs: demand_twh
    rhs: base_demand_twh * (1 + demand_growth) ** horizon_years
    relation: eq                     # eq | leq | geq
    parameters: [base_demand_twh, demand_growth, horizon_years]
    free_variables: [base_demand_twh, demand_growth, horizon_years]
    determined_variables: [demand_twh]
    tolerance: 1.0e-6
    unit_check: true
    solution_method: numeric         # direct|iterative|symbolic|numeric
    linearity: linear                # linear|nonlinear|mixed
    priority: P1
```

`parameters` and `free_variables` are read identically by every consumer (always
unioned). Put the inputs in both, or split them semantically — the loader only
requires that their **union with `determined_variables` equals the symbol set
the arithmetic names, exactly.**

### Register 3 — `relationships` (the declaration layer)

```yaml
relationships:
  - source: demand_growth
    target: demand_twh
    equation_id: demand_definition
    relationship: functional         # equality|inequality|functional|constraint|feedback|temporal|stochastic
    direction: forward               # forward|backward|bidirectional
    strength: hard                   # hard|soft|informational
    description: Growth rate scales the demand trajectory
    priority: P1
```

**Both endpoints must appear among the symbols of the cited equation.** An edge
is a claim about a coupling, not a restatement of the equation, and it cannot
stand alone — every edge must cite an equation that exists.

### Register 4 — `cross_validation` (relations no single equation states)

For inequalities with no determined variable, and for consistency conditions
spanning parameters.

```yaml
cross_validation:
  - id: reserve_margin_vre_penetration
    condition: reserve_margin_min < 0.10 and vre_capacity_target_mw > 20000
    severity: error                  # error|warning|info
    message: A reserve margin floor below 10% with a 20 GW-plus VRE target is a system with no firm capacity
    suggestion: Raise reserve_margin_min, or lower vre_capacity_target_mw
```

The `condition` is text, parsed by the engine. **It is not `eval`** — it is
`ast.parse` with an allow-list, and the grammar is narrow: comparisons
`< <= > >= == !=` between a parameter name and a literal or another parameter,
joined with `and` / `or` / `not`, with parentheses. **Arithmetic is refused.**
`a * 2 > b`, `a + b > c`, `2 * a > b` and `a ** 2 > b` are all rejected at load
with `BinOp is not part of a cross-validation condition`.

So if a relation needs arithmetic — a ratio, a product, a sum — it is an
**equation** in Register 2, not a rule here. A rule is for a comparison of
already-computed values.

## ENUMERATED VOCABULARIES

**The 17 systems** (`system:` must be one of these):
`affordability`, `capture_price`, `carbon_trajectory`, `cost_accounting`,
`demand_supply`, `emissions`, `employment`, `energy_balance`, `financial`,
`health`, `inertia`, `learning`, `ppa_pricing`, `price_demand`, `reliability`,
`reserve_margin`, `water_energy`.

These are the systems that **exist**. The library holds **17**, not 20 — the
specification enumerates 20 §4 headings, and three of them are refinements of a
system already here (System 16 is the capture-price loop, 17 is the carbon
trajectory, 18 is the learning curve, 19 is debt sizing, which is part of
`financial`). If a system your physics needs is not in this list, say so in the
coverage report rather than inventing an id — a misspelt system is a load error,
and a new system is a change to the library's own enumeration.

**DSL grammar** for `lhs`/`rhs`: arithmetic `+ - * / **`, parentheses,
subscripts `x[i]`, and an explicit summation with integer bounds:
`sum(x[i] for i in range(0, 8760))`.

**The 21 functions**: `abs acos asin atan ceil cos cosh erf exp floor ln log
log10 log2 max min sin sinh sqrt tan tanh`.

**Reserved words** (may not be a parameter id or a sum index): `abs acos and
asin atan ceil cos cosh erf exp floor for in ln log log10 log2 max min not or
range sin sinh sqrt sum tan tanh`.

**`category`**: a free-text field, **not validated** against a vocabulary. Use
the catalog's category name for the parameter's category, taken from
`docs/params.md` — the 28 headings are: Demand-Side, Supply-Side, Cost, Policy,
Transmission, Sector Coupling, Climate, Outage, Macroeconomic, Investment,
Operational, Spatial/Temporal, Market Design, Combined, Tax, Regulatory
Finance, Contract, Environmental/Social, Just Transition, Consumer Protection,
Digital, Geopolitical, Asset, Market Operations, Insurance, Carbon Market,
Adaptation, Land Use.

Note the graph's own category field currently holds **40 distinct spellings**
for these 28 categories (`Contract` and `Contracts`, `Cost` and `Costs`,
`Market` and `MktOps`), because nothing checks it. If you are adding a node,
match the catalog. Do not add a 41st spelling.

## RULES THE LOADER ENFORCES (each is a hard error)

1. `default` must lie inside `range` (checked only when both are present).
2. `role: derived` must **not** carry a `default`.
3. `role: endogenous` **must** carry both `range` and `default`.
4. `initial` is valid only on a `derived` node that carries a `range`.
5. A `timeseries` or `spatial` node may not carry a scalar `default` or `range`.
6. Every symbol in `lhs`/`rhs` must be a declared parameter id, a DSL function,
   or a reserved word.
7. `parameters ∪ free_variables ∪ determined_variables` must equal **exactly**
   the set of symbols the arithmetic names. A symbol in the arithmetic but not
   in the lists, and a listed symbol absent from the arithmetic, are **both**
   errors.
8. Every `determined_variables` entry must have `role: derived`.
9. An equation determines **at most one** variable.
10. A non-`eq` relation may not carry `determined_variables` — an inequality
    bounds a value, it does not fix one.
11. At most one equation may determine a given parameter.
12. `lhs` must reduce to a single parameter id, or to a linear combination of
    them whose subject is the determined variable.
13. `tolerance` must be positive.
14. Every id added must be new; every id corrected must match an existing one.

## GATES YOUR BATCH MUST PASS

State, in your reply, the value you expect for each:

1. **Schema** — every entry parses with no extra fields.
2. **Closure** — every symbol is a declared parameter. (This is the gate that
   catches the 266 quantity names.)
3. **Exactness** — rule 7 above, both directions.
4. **Role consistency** — rules 2, 3, 8.
5. **Edge support** — both endpoints in the cited equation; `relationship:
   inequality` requires the equation's `relation` to be `leq`/`geq`;
   `equality` requires `eq`.
6. **Dimensional** — equations must be dimensionally consistent. The shipped
   graph has 39 equations: **31 consistent, 8 inconsistent, 0 undecidable, 0
   exempt**. Your batch must not raise the 8. If an equation's dimensions
   genuinely cannot be decided, set `unit_check: false` and say why in the
   `description`.

   **The 8 are a deliverable, not just a bound.** They are a known set, pinned
   by a test, and three of them are one class. Fixing them is welcome and is
   part of the work:

   | equation | why it is flagged |
   |---|---|
   | `crf_definition`, `debt_service_definition`, `energy_demand` | the `(1 + rate)` convention: `discount_rate`, `cost_of_debt` and `demand_growth` are declared `unit: 1/year`, and `1 + 1/year` cannot be added to `1` |
   | `rocof_definition` | missing nominal frequency |
   | `emissions_definition`, `hydrogen_water_definition`, `premature_deaths_definition` | the two sides do not share a dimension |
   | `tariff_cost_recovery` | annual quantities declared without a per-year divisor |

   The `(1 + rate)` class is the one with a clean fix and it is a **modelling
   decision, not a patch**: a per-year growth or discount rate used as `(1 + r)`
   is *dimensionless*, and declaring it `1/year` is what breaks it. Say in your
   reply which convention you are adopting and correct the declarations
   consistently. The `tariff_cost_recovery` class is the same shape one level
   down — `equilibrium_demand_twh` is an annual energy declared as bare `TWh`,
   so `USD/year / TWh` reads as `USD/(MWh·year)` when the physics is
   `USD/year / (MWh/year) = USD/MWh`. Declaring the `TWh` nodes as `TWh/year`
   clears this one and opens five others in the same class (`energy_balance`,
   `energy_demand`, `equilibrium_demand`, `unserved_definition`,
   `cooling_water_definition`), so decide it once and say so.
7. **Coverage** — report how many of the 869 parameters are now *determined*
   (a `determined_variables` entry), *named* (appear in some equation), and
   *still uncoupled*. This is progress, not a pass condition.

## FORBIDDEN

- Renaming a graph parameter to match a formula symbol.
- A left-hand side that is a physics symbol rather than a graph id.
- Using one of the non-parameter names (`available_capacity`, `clearing_price`,
  `curtailment`, `busmap`, `lcoe`, `cfads`, `ens`, `debt_service`,
  `cumulative_capacity`, `heat_pump_load`, `hydrogen_revenue`, …) without first
  declaring it in Register 1 with a unit and a range. There are 266 such names;
  the list above is a sample, and the set is every cited name that
  `config/prg.yaml` does not declare.
- An edge citing an equation that does not hold both endpoints.
- A `default` on a `derived` node; a `free` node as a determined variable.
- Inventing a range or a unit to fill a schema slot.
- Emitting an equation for a quantity that is a dispatch *output* rather than a
  parameter, unless you declare that quantity first.

## ORDER OF WORK

1. Register 1 and Register 4 first — they need no new equations, and they close
   the inequality-shaped relations and the placeholder metadata.
2. Then Register 2, system by system, starting with the 17 systems the library
   already holds and extending the 39 shipped equations.
3. Register 3 last, derived *from* your equations: an edge is a projection of an
   equation onto a pair of its symbols.

## DELIVERABLE

- The four registers, as YAML, in the layout above.
- A `manifest.yaml` listing, per file: the register, the category or system, the
  count of entries, and the ids added.
- A coverage report: of 869 parameters, how many determined, how many named,
  how many uncoupled; and the same split for the 781 `free` nodes.
- A list of every place you could not write an equation because the parameter's
  admissible set is unknown, with the reason. That list is a deliverable, not a
  failure.
- **A unit-convention note**, if you touch gate 6: which convention you adopted
  for per-year rates (`1/year` vs dimensionless) and for annual energies
  (`TWh` vs `TWh/year`), which equations it moves, and whether the inconsistent
  count went down or stayed at 8. Do not change a unit without saying which
  equations it re-decides — the dimensional register is pinned by a test, and a
  unit edit that clears one equation and flags five is a net regression the
  count alone will not show.
- **A list of any relation that is not expressible** in the cross-validation
  grammar because it needs arithmetic, and which equation you wrote for it
  instead.
