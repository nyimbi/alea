# Annotating a Connection Between Two Parameters

How the PRG records the link between two parameters, which of those records is
authoritative, and how far "bidirectional" gets you.

The short version: **a connection is written in three places, they are three
different relations, and only the arithmetic drives propagation.** The edges are
a declared overlay that documents the arithmetic and carries three properties the
arithmetic cannot state — relationship class, direction, and strength.

Every figure below is measured against `config/prg.yaml` as it stands on
2026-10-16: 869 nodes, 39 equations, 88 edges. The catalog join that took the
file from 88 nodes to 869 is described in `prg-status.md`; the equations and
edges below are unchanged by it, so every figure in this document is a figure
about the 39-equation core rather than about the 781 catalog nodes that carry
`role: free` and no arithmetic.

---

## 1. The three records

### 1a. The equation — the arithmetic

`equations:` holds the DSL source, what it reads, and what it fixes.

```yaml
crf_definition:
  name: "Capital recovery factor"
  system: cost_accounting
  lhs: "discount_rate * (1 + discount_rate) ** asset_life"
  rhs: "crf * ((1 + discount_rate) ** asset_life - 1)"
  parameters: [crf, discount_rate, asset_life]
  determined_variables: [crf]
  tolerance: 1.0e-9
  reference: "Standard annuity formula; cf. LCOE definitions in IEA/NEA..."
  linearity: nonlinear
  solution_method: direct
```

This is the **only** record propagation reads. `lhs` and `rhs` are kept as text
rather than a parsed tree so the YAML a human edits and the object the engine
runs are the same artefact — a library stored as a serialised AST cannot be
reviewed by the person who owns the physics.

### 1b. The relationship edge — the declared connection

`relationships:` holds one entry per `(source, target)` pair:

```yaml
- source: discount_rate
  target: crf
  equation_id: crf_definition
  relationship: functional
  direction: forward
  strength: hard
  description: "A higher discount rate raises the annual charge on capex."
  priority: P1
```

An edge is **not** one per equation. `crf_definition` is cited by two edges —
`discount_rate → crf` and `asset_life → crf` — because the equation reads two
things and determines one. Across the graph:

| edges citing an equation | equations |
|---|---|
| 1 | 11 |
| 2 | 12 |
| 3 | 7 |
| 4 | 8 |

`relationship` takes the spec's seven classes. As shipped: 47 `equality`,
29 `functional`, 7 `constraint`, 2 `feedback`, 2 `temporal`, 1 `stochastic`.

### 1c. The node's `depends_on` / `affects` lists — a third record

The spec's `ParameterNode` carries `depends_on`, `affects` and `equations`
beside the edge set, so the same relationship is written twice. **The model does
not declare these as the source of truth.** `structure_issues()` compares them
against what the equations imply and reports the drift; the equations win.

The node holds only what is true of the parameter; the edge holds only what is
true of the relationship. Two records that agree today are not one source of
truth — the first change that adds an edge and forgets the node list leaves a
document whose declared shape and actual shape differ.

---

## 2. Which record is authoritative

**The equation, for anything that decides a number.** After construction,
`_edges` is read only by `edges_from()` and `edges_into()` — the reporting
methods. `propagate`, `order` and `_phases` walk `_determiner` and
`_loop_variables`. Grep the file: past line 603, `self._edges` appears nowhere
in a computational path.

So the division is:

| question | answered by |
|---|---|
| what number does this produce? | the equation |
| what does changing this move? | `affects()` — computed from equations |
| what does this depend on? | `depends_on()` — computed from equations |
| how is this connection *classified*? | the edge |
| how strong is the claim? | the edge (per equation, see §4) |
| which direction does causality run? | the edge |

`depends_on()` and `affects()` are **derived from the equations in both
directions**, which is why you never annotate a reverse edge: the reverse query
is computed, not stored.

`depends_on()` deliberately excludes the loop equations — `order` and `_phases`
walk it to build a topological sequence, and a loop has no place in one. A loop
variable therefore reports `()` here; its inputs are readable from
`feedback_loops()`. `affects()` *does* include the iterative equations, because
`_determiner` skips them and reading only it dropped parameters that genuinely
move the fixed point.

---

## 3. Is the annotation bidirectional?

**Two different answers, depending on which record you mean.**

### The edges are directed, not reciprocal

All 88 are `forward`. None is `backward`, none is `bidirectional`. Only **2**
ordered pairs have a reverse partner — and they are loop 2:

```
regulated_tariff_usd_per_mwh → equilibrium_demand_twh   via equilibrium_demand
equilibrium_demand_twh → regulated_tariff_usd_per_mwh   via tariff_cost_recovery
```

That is not a `bidirectional` edge. It is **two forward edges in opposite
directions through two different equations** — the loop's two halves, each
stating its own causality. `direction: bidirectional` exists for the spec's
jointly-determined pairs and is supported by the index (such an edge lands on all
four lists, making `edges_into` the mirror of `edges_from`), but the shipped
document declares none.

Direction is genuinely read, not decorative. The constructor indexes by the
*declared* direction rather than by the `source`/`target` fields, so a `backward`
edge belongs on its target's outgoing list. Reading the fields alone made the
field inert — and because all 88 edges happen to be `forward`, that defect was
invisible: a field no edge exercises is a field nothing tests.

### The derived relations are bidirectional in the useful sense

`depends_on(crf)` = `(asset_life, discount_rate)`.
`affects(discount_rate)` ⊇ `{crf}`.

Both computed from the equations. So the reverse of any connection is always
*queryable* — you get bidirectionality from the derivation, not from a second
annotation.

---

## 4. Strength is per equation, not per edge

`strength` (`hard` / `soft` / `informational`) is a property of the **equation**,
enforced at construction: an equation reached by a `hard` edge and an
`informational` one would mean two things, and the graph raises rather than
picking one. A strength that depends on which edge a caller happened to read is
not a declared property.

As shipped: 87 `hard` edges, 1 `informational` — 38 `hard` equations, 1
`informational`. `strength_of()` defaults an uncited equation to `hard`, the
conservative reading: nothing softened it.

---

## 5. Intermediate variables do not exist as a concept

`firm_capacity_mw` is what you would call an intermediate:

```yaml
firm_capacity_definition:
  lhs: firm_capacity_mw
  rhs: thermal_capacity_mw + dispatchable_re_capacity_mw
  parameters: [firm_capacity_mw, thermal_capacity_mw, dispatchable_re_capacity_mw]
  determined_variables: [firm_capacity_mw]
```

It is **an ordinary node** — `role: derived`, with an equation. A two-hop
connection (`thermal_capacity_mw → firm_capacity_mw → reserve margin`) is two
edges through an ordinary node.

"Intermediate variable" appears nowhere in `spec/` or in `src/alea/prg/`. There
is no third node kind between exogenous and derived. If you want to annotate a
mid-chain quantity, you give it a node and an equation; that *is* the annotation.

---

## 6. Systems group equations, not parameters

`system` on an equation groups it: 17 systems, all populated, every equation
covered.

| system | equations | | system | equations |
|---|---|---|---|---|
| financial | 5 | | emissions | 1 |
| capture_price | 4 | | demand_supply | 1 |
| cost_accounting | 4 | | ppa_pricing | 1 |
| carbon_trajectory | 3 | | price_demand | 1 |
| water_energy | 3 | | employment | 2 |
| affordability | 2 | | energy_balance | 2 |
| health | 2 | | inertia | 2 |
| learning | 2 | | reliability | 2 |
| reserve_margin | 2 | | | |

A system is a **grouping of equations**, not a coupling annotation between
parameters. And it does not partition the parameters: **18 of 87** span more than
one system. `capacity_factor` appears in equations belonging to four
(`cost_accounting`, `financial`, `learning`, `reserve_margin`). So a parameter
has no single system, and you cannot annotate a connection by naming the systems
at its ends.

---

## 7. The gap: the edge set is not verified complete

**Eleven connections the arithmetic states are declared by no edge.**

For every equation that determines something, each `(read, determined)` pair
should appear as an edge citing that equation. Eleven do not:

| arithmetic | connection | equation |
|---|---|---|
| `annualised_capex` | `crf → annualised_capex_usd_per_kw` | `capex_usd_per_kw * crf` |
| `capture_price_equation` | `capture_price_sensitivity → capture_price_usd_per_mwh` | |
| `capture_price_equation` | `marginal_cost_usd_per_mwh → capture_price_usd_per_mwh` | |
| `capture_price_ratio_definition` | `marginal_cost_usd_per_mwh → capture_price_ratio` | |
| `firm_capacity_definition` | `thermal_capacity_mw → firm_capacity_mw` | `thermal + dispatchable_re` |
| `firm_capacity_definition` | `dispatchable_re_capacity_mw → firm_capacity_mw` | |
| `lcoe_definition` | `marginal_cost_usd_per_mwh → lcoe_usd_per_mwh` | |
| `marginal_cost` | `fuel_price_usd_per_mwh → marginal_cost_usd_per_mwh` | |
| `vre_build` | `marginal_cost_usd_per_mwh → vre_capacity_mw` | |
| `vre_build` | `vre_capacity_target_mw → vre_capacity_mw` | |
| `vre_share_definition` | `total_capacity_mw → vre_share` | |

None of the eleven is declared against a *different* equation either — the
connection is absent from `relationships:` entirely. The omissions are not
random: `marginal_cost_usd_per_mwh` is the missing source four times, so the
cost chain's influence on capture price, LCOE, VRE build and capture ratio is
undeclared throughout.

The reverse holds: **0** edges name a source their cited equation does not read.
So the edge set is a strict *subset* of what the arithmetic implies — no
spurious edges, only missing ones.

### Why nothing catches it

`_validate()` checks the forward direction — that an edge's `source`, `target`
and `equation_id` all exist. Nothing checks the reverse: that every determining
equation has the edges its arithmetic implies. `structure_issues()` compares
declared node lists against derived ones, which is a different comparison and
does not consult the edge set at all.

### Why it matters, and why it does not

**No number is wrong.** Propagation never reads the edges; `depends_on()`
returns `crf` and `thermal_capacity_mw` and `marginal_cost_usd_per_mwh` because
it reads the equations. Every downstream value is correct.

**The documentation is wrong.** A reader who builds the causal diagram from
`relationships:` gets a graph eleven connections short of the one the engine
walks — and specifically misses that the cost chain drives capture price, LCOE
and the VRE build. Nothing reports it, so the silence is indistinguishable from
completeness.

Note that `structure_issues()` is **empty** on this document. The node-list
cross-check passes: every declared `depends_on`/`affects` list agrees with what
the equations imply. The edge set is a *third* record and is compared against
nothing, which is why a clean `structure_issues` and an eleven-connection edge
gap coexist without contradiction.

It is the `declared is not produced` class this project keeps recording, in its
milder form: the declaration is *absent* rather than inert. The fix is a
completeness check — for each determining equation, assert the edge set carries
an entry for every `(read, determined)` pair — which is exactly the check whose
absence let these eleven accumulate.

---

## 8. Worked trace: changing the discount rate

```
discount_rate ──crf_definition──▶ crf ──annualised_capex──▶ annualised_capex_usd_per_kw
```

1. **Annotation.** Three records exist: `crf_definition` (arithmetic, reads
   `discount_rate` and `asset_life`, determines `crf`); two edges
   (`discount_rate → crf`, `asset_life → crf`, both `functional/forward/hard`);
   and the node lists, which `structure_issues()` cross-checks.

2. **Propagation.** `propagate({"discount_rate": 0.08})` reads
   `_determiner["crf"] → crf_definition`, evaluates `lhs`/`rhs`, solves for
   `crf`. It never touches `_edges`.

3. **The reverse query.** `affects("discount_rate")` returns `crf` and
   everything transitively downstream — computed from the equations, no reverse
   edge needed.

4. **The classification.** A caller asking "is this a definition or a
   correlation?" reads the edge: `relationship: functional`, `strength: hard`.

---

## Summary

| | answer |
|---|---|
| Where is a connection annotated? | the equation (arithmetic), the edge (declared relation), the node lists (a cross-checked third record) |
| Which is authoritative? | the equation, for every number; the edge, for classification/direction/strength |
| Do edges drive propagation? | no — `propagate`, `order`, `_phases` read `_determiner` and `_loop_variables` |
| Are edges bidirectional? | no — 88 forward, 0 bidirectional, 2 reciprocal pairs (loop 2, two forward edges) |
| Are the derived relations bidirectional? | yes — `depends_on`/`affects` are computed both ways from the equations |
| Intermediate variables? | not a concept — an intermediate is an ordinary derived node |
| Systems? | group equations; 18 of 87 parameters span more than one |
| Strength? | per equation, not per edge; enforced at construction |
| Verified complete? | no — 11 connections the arithmetic states are declared by no edge, and nothing checks the edge set against the arithmetic |
