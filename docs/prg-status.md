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
| The graph | `config/prg.yaml` | 84 parameters, 37 equations, 84 edges, 1 feedback loop |

Commands: `alea prg summary|equations|check|propagate|audit`, and
`alea expr render|eval|diff|simplify|solve`.

## Not built

- **The engine is not driven by the graph.** `whatif/params.py` exposes 9 knobs
  and 2 of them name PRG parameters; the rest are PyPSA-level multipliers over
  network data, which the graph has nothing to say about. `alea.prg.audit` is
  the seam, and it checks the *result* rather than driving the solve.
- **The energy balance is single-region.** One demand, one generation total. A
  PyPSA network balances per bus and per hour and the solved result carries no
  nodal frame, so the audit cannot assert the balance against it. The audit
  reports what it did not check rather than a pass it did not earn.
- **No correction suggestions.** A violation names the equation and the
  residual. It does not propose which parameter to move, which is
  `how_prg_works.md` §5's A/B/C.
- **No uncertainty or stochastic edges.** `Relationship.STOCHASTIC` is declared
  and one edge uses it; nothing consumes the distinction.
- **Emissions use one fleet-wide factor.** The engine sums per-carrier
  intensities. `audit.fleet_intensity_gap` measures the difference instead of
  pretending they agree.
- **Not the 784-parameter graph.** 84 of them, over the systems with the
  clearest physical or accounting statement.

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
