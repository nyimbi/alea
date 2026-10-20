# Coupling pack brief

A coupling pack is the research a batch is authored from. It is not the batch:
`config/prg.yaml`, `scripts/build/prg_coupler.py` and everything under `tests/`
are off limits to whoever writes a pack. The pack is a proposal, reviewed before
it becomes arithmetic.

## What a coupling is

A node in `ParameterGraph.uncoupled()` is named by no equation. Closing it means
either **determining** it (it becomes an equation's `lhs`, and its role becomes
`derived`) or **naming** it as an input to an equation that determines something
else. Both count. A node that is merely read by a *rule* still counts as
uncoupled, which is why a cross-validation rule alone does not close a node.

## Hard constraints, all of them discovered the hard way

1. **The DSL has no derivative rule for `abs`, `min`, `max`, `floor`, `ceil`.**
   `alea.prg.sensitivity.gradients()` differentiates every equation in the graph
   and raises `DslError` on any of them. An equation using `max(x, 0)` breaks
   thirteen tests. If a quantity wants a clamp, either widen the range to admit
   the sign and say so in the prose, or find an identity that needs no clamp.

2. **Every `lhs` must appear only on the left** for the affine solve path
   (`solve_for`). Do not propose a formula whose target also appears on the right.

3. **Every symbol on the right must already be a declared node.** Run the check
   (below). Inventing an operand is the failure this whole register exists to
   stop: the equation loads, renders, and reads a name nothing supplies.

4. **A derived node must not carry a `default`.** Its value comes from the
   equation; a default is a value that stands in whenever the equation is not
   run.

5. **A node with `deprecated_by` set cannot be an equation's target.** The graph
   refuses an edge whose target is deprecated — "a node with a replacement is
   not read". So an alias onto a deprecated id is not available.

6. **`propagate` at defaults must be clean.** No range excursion, no blocking
   conflict, no undecidable unit. A batch that ships a violation at its own
   defaults has shipped an inconsistent graph.

## Units

The registry is Pint, extended with `USD`, `DALY`, `m3` and the graph's own
spellings. Common ones in this graph: `USD/kW`, `USD/kW/year`, `USD/MWh`,
`USD/year`, `USD`, `MW`, `MWh`, `TWh/year`, `km`, `km2`, `hectares`, `1`
(dimensionless), `tCO2/MWh`, `MtCO2/year`, `t/year`, `jobs/MW`, `years`,
`hours`, `persons`, `MWh/person/year`. Read `src/alea/prg/units.py` for the
authoritative list rather than guessing; a unit the registry does not carry makes
the equation undecidable, and undecidable is a finding, not a pass.

## The citation rule

Every equation carries a `reference`. It is prose, and it must match a row in
`sources/INDEX.md` by case-insensitive substring **in both directions**. A
citation whose work is not archived locally is a link that will rot: check
`sources/archive/` and, if the work is not there, either (a) find a work already
archived that states the identity, or (b) say in the pack that the source must be
fetched and archived before the equation ships. Do not cite a label you cannot
point at a file for.

`reference: None` is admissible only where the identity is definitional — an
alias, a unit conversion — and a batch that leans on it more than a handful of
times is a batch with no literature behind it.

## What a pack row must contain

For each node, one row with all of these:

| field | what it must say |
|---|---|
| `node` | the graph id, exactly |
| `class` | the pack's class for it (PRODUCT / BASE-NEEDED / THRESHOLD / …) |
| `kind` | `derive` (this node becomes an lhs) or `read` (this node becomes an rhs operand of a named new equation) |
| `unit` | the declared unit, or the unit this batch retypes it to |
| `range` | `[low, high]`, with the reason the bounds are what they are |
| `role` / `determinism` | `derived` or `free`; `fixed` / `policy` / `stochastic` |
| `equation` | the exact `lhs = rhs` string, DSL syntax, or `--` for a pure read |
| `prose` | the description that will ship on the node — what the quantity is, and why the formula is the right one |
| `citation` | the reference prose, and the archive file it matches |
| `rejected` | what else was considered and why it lost |

The `rejected` column is not decoration. A batch whose packs do not record what
was rejected cannot be reviewed, only accepted.

## The check to run before writing the pack

```python
from alea.prg.service import load_graph
from alea.prg.dsl import parse_side
g = load_graph()
for name, rhs in [("target", "a * b / c"), ...]:
    missing = sorted(s for s in parse_side(rhs).symbols
                     if s not in g.nodes and s != name)
    assert not missing, (name, missing)
```

Every symbol on every proposed right-hand side must resolve. Run it over the
whole pack, not one row.

## Scope discipline

Stay inside the node list you were given. A pack that reaches into another
agent's slice collides at authoring time and one of the two batches loses. If a
node in your slice genuinely needs an operand that belongs to another slice, say
so in a `## Dependencies` section rather than proposing that node too.
