# Why the 741 uncoupled nodes have no equations to generate

**Question.** Generate the equations for the 741 parameters no equation names.

**Answer.** They cannot be generated from this tree. The source material states a
*model* for each parameter and an *arithmetic* for none, and the parameters the
arithmetic would need do not exist as nodes. Writing 741 equations would mean
inventing both the formulas and their operands.

This is the measurement, with the commands that produce it.

## What `uncoupled()` measures

`ParameterGraph.uncoupled()` returns nodes named by no equation's `parameters`,
`free_variables` or `determined_variables`. So a node closes two ways: it is
**determined** by an equation, or it is **named** by one as an input. Both count.

Measured on the shipped graph: 869 nodes, 39 equations, 782 uncoupled.

## The five sources, and what each holds

| Source | Claim | What it actually holds |
|---|---|---|
| `docs/params.md` | the catalog, 824 rows | a name, a one-line description, a **placeholder algorithm string** |
| `docs/param_eqn.md` | linkage for all 784 | prose arrows: "→ `demand_t` via logistic growth" |
| `docs/param_eqn_formula.md` | "the actual mathematical formulas" | LaTeX over notation symbols, not graph ids |
| `docs/param_eqn_formula1.md` | formulas for all 547 remaining | same, and honestly flags 15 nodes metadata-only |
| `docs/alea_prg.md` §13 | 83 equations, 20 systems | equation **ids** with parameter **words**, no arithmetic |

### The catalog holds no arithmetic

501 distinct `algorithm` strings across 824 rows. They name models, not formulas:
`"Financial model"` (38 rows), `"Compliance model"` (31), `"Contract model"` (17),
`"Renewable subsidy cost"`, `"Growth curve shape fitting"`. Grepping the algorithm
and description columns for `=` returns zero rows. This is the finding
`catalog.py` already records.

### The formula documents use symbols that map to nothing

`param_eqn_formula.md` writes `$D^{\text{ind}} = D^{\text{total}} \cdot s^{\text{ind}}$`.
The notation table defines `t` = hour, `y` = year, `n` = node, `g` = generator —
**indices, never ids**. There is no symbol-to-id mapping anywhere in the tree.

Tested mechanically: of 405 formula rows for uncoupled parameters, **1** has every
right-hand symbol resolvable to a declared node, and that one is a regex artifact
(`equity_share = equity_share`). **400 resolve to nothing.**

### The spec's 83 equations name parameters the graph does not have

Of 244 parameter mentions in §13's tables, **26 are declared nodes** and **151
distinct words are not**. `nodal_balance`, `carrier_balance`, `storage_balance`,
`market_clearing`, `consumer_cost`, `producer_revenue` — the energy-balance and
market systems, which are most of the spec — have **zero** resolvable operands.
They name network objects (`generation`, `line_flow`, `storage_level`) that the
parameter graph does not model.

## The structural reason

Two properties separate the 782 from the 87 named nodes, and both are total:

- **691 of 782 declare no unit; 0 of 87 named nodes are unitless.** A quantity
  with no unit is not a quantity — it is a catalog row. A unit is what makes
  `a + b` meaningful, and without one any equation over these is dimensionally
  arbitrary.
- **689 of 782 have a description of three words or fewer**, and 77 have one.
  `renewable_subsidies` — "Renewable energy subsidies". `capex_geothermal` —
  "Geothermal capital cost". There is no content to derive from.

They are also not decomposable. The 40 `_capacity` nodes have no unit while
`total_capacity_mw` is MW, so summing them means asserting 40 unit claims. The 22
`_share` nodes have no numerator and no denominator declared: there is no
`residential_demand`, no `claims_paid`, no `gdp`. A search of all 782 for an
uncoupled node whose description names an existing node as its operand returns
**0**.

## The irreducible inputs

A large part of the 782 are not computable at all — they are scenario dials and
compliance obligations, and the correct register for them is `role: exogenous`,
not an equation:

- **25 booleans** (`ets_enabled`, `carbon_border_adjustment`, `ppa_guarantees`)
- **18 `_requirements`** with no unit (`adms_requirements`,
  `cybersecurity_requirements`, `fpic_requirements`, `local_content_requirements`)

  **`local_content_requirements` is no longer one of them (batch 61).** It was
  the plural duplicate of `local_content_requirement` — same unit `1`, same
  range, same default — and each id fed a different consumer, so the one policy
  lever moved half the graph. The plural is now a tombstone pointing at the
  singular, and `local_content_capex_definition` reads the singular. The class
  this bullet describes is real (a compliance obligation with no arithmetic),
  but this member was not an example of it: it was a duplicate that the
  classification could not distinguish from one, because both look identical
  from the outside.
- **40 `_capacity`** decision variables the optimizer solves for
- **20 `_rate`** and **22 `_share`** independent dials

`docs/param_eqn_formula1.md` reaches the same conclusion for 15 nodes on its own,
calling them "metadata-only parameters that legitimately have no formula".

## What could honestly be written

Two classes, and neither reaches 741:

1. **The 26 spec-equation parameter mentions that resolve.** Real, but they
   implement the 39 equations already present, not new ones.
2. **Accounting closures over same-unit families.** `equity_share` from
   `debt_fraction`; a sum-to-one over the four demand shares — except the four
   shares' summands do not exist, so even that needs new nodes.

## Rejected options

- **Deriving formulas from the LaTeX by mapping notation to ids.** The mapping is
  not stated, and inventing it would produce equations whose correctness no one
  could check. A formula that names `D^total` when no `total_demand` node exists
  is prose with a `$` in it.
- **Summing the 40 capacity nodes into `total_capacity_mw`.** Dimensionally
  unjustified: 40 unitless nodes into an MW target.
- **Marking the 782 `derived` to empty the register.** `role: derived` means "an
  equation fixes this". Nothing does, so this would empty `uncoupled()` while
  changing nothing, and the loader's R14 check refuses it.

## What would actually close the register

The spec's own equation tables, implemented against a graph extended with the
network objects they name. That is a modelling decision — whether the parameter
graph is to carry `generation`, `line_flow` and `storage_level` — and it belongs
to the specification, not to this ingestion.

Sources: `docs/params.md`, `docs/param_eqn.md`, `docs/param_eqn_formula.md`,
`docs/param_eqn_formula1.md`, `docs/alea_prg.md` §13, and
`src/alea/prg/{graph,catalog,library,dsl}.py`.
