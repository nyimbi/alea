# Code vs. documentation: the gaps

The repo has three documentation layers, and they disagree with each other in useful ways:

- **Design intent** — `docs/how_prg_works.md`, `docs/alea_prg.md`, `docs/param_eqn.md`: describe the *target* system (784 nodes, ~2,500 edges, 20 systems, ~120,000 constraints, ~15 feedback loops, a dashboard UI, PyPSA/Linopy/Pyomo/SymPy backends, SAT/SMT conflict detection).
- **The honest register** — `docs/prg-status.md`: explicitly says the design docs are "intent," that "the code and `config/prg.yaml` are the authority," and lists what is actually built.
- **The code** — `src/alea/prg/` (`graph.py`, `feedback.py`, `conflicts.py`, `translate.py`, `constraints.py`, `dsl.py`, `views.py`, `library.py`, `service.py`, `audit.py`) plus `tests/ci/test_prg*.py`.

One qualitative point up front: **the code is honest about its own limits.** `prg-status.md` is a deliberate register, `audit.py` states that the nodal balance "cannot yet" be checked, `ScenarioCheck` reports `unmodelled` systems, and `translate.py` names the 49/52 parameters that reach no knob. So the gaps below are *acknowledged* gaps, not hidden ones — but they are still large gaps versus what the design documents promise.

## 1. Scale and coverage — the biggest gaps

| Dimension | Design doc says | Shipped reality | Source of reality |
|---|---|---|---|
| Nodes | **784** (one per parameter, all live) | **869** after the catalog join, but only **~88** have real arithmetic; **781** are `role: free` placeholders (691 share one default/range) | `prg-annotation.md`, `param_ingest.md`, `prg_from_catalog.py` |
| Edges | **~2,500** | **88** | `prg-annotation.md`, `param_ingest.md` |
| Equation systems | **20** | **16** | `prg-status.md` (built table), `library.py` |
| Equations | "20 systems … ~120,000 constraints" | **39 equations** (31 consistent, **8 dimensionally inconsistent**); a handful of translated constraints | `param_ingest.md`, `constraints.py` |
| Feedback loops | **~15 cycles** | **2** (pinned by test: `vre_capacity_mw`→38, `equilibrium_demand_twh`→36) | `tests/ci/test_prg.py` |
| Constraints | **~120,000** | 2 bindable inequalities + 4 post-solve checks | `constraints.py`, `prg-status.md` |

So the shipped graph is a *scaffold* around a small arithmetic core: the 869 nodes are mostly free placeholders with no equations, and the real engine is the 39-equation / 88-edge / 16-system kernel. The design's "784 live parameters, ~2,500 edges, 120k constraints" is a target the code is far from.

## 2. Subsystems the design promises but the code lacks

- **User interface.** The design describes a Plotly Dash + Cytoscape dashboard, an interactive slider that turns yellow/green, live ripple previews, and correction-acceptance popups. The register and code show only a **CLI** (`alea prg summary|equations|check|propagate|conflicts|sensitivity|units|constraints|audit`) and a **FastAPI** service. No UI is built.
- **Persistence layer.** Design: "NetworkX + PostgreSQL persistence," "GraphML for export," "Metadata Store … PostgreSQL." Reality: the graph is loaded from `config/prg.yaml` into a **custom, in-memory `ParameterGraph`** (`graph.py` uses `math`/`collections`/`deque`, not NetworkX). YAML is the persistence; PostgreSQL and GraphML are not in the register. The capability matrix rates persistence **L2**.
- **Incremental updates.** Design §29: "the PRG supports incremental updates." Capability matrix rates "Incremental updates: dirty-set tracking, caching" **L0** (not started).
- **Pyomo and SymPy backends.** Design §41 lists PyPSA, Linopy, Pyomo, SymPy, and a custom backend. `prg-status.md` is explicit: "Part X's other backends are absent … the translation layer's output is a linopy constraint." Only the PyPSA/Linopy path exists.
- **PDE support.** Design §12 ("It does not solve PDEs. See the earlier discussion on PDE support") implies a PDE design discussion; nothing in the register or code implements it.
- **Type inference from equations.** Capability matrix rates this **L0**.

## 3. Behaviors the design overstates or contradicts

- **Convergence speed.** Design: loops converge in "5–10" / "5–15" iterations. Reality: **38 and 36** iterations with plain damped Gauss–Seidel — about 2.5× slower than the design claims.
- **Anderson acceleration.** Design §4 ("Mechanism 4") presents Anderson acceleration as the solver's speedup. Reality: it was **tested and rejected** — 63/45 turns vs 38/36 for damped Gauss–Seidel, and `m=2` fails to converge in 200 iterations. `prg-status.md` records the rejection; the design still presents it as a feature.
- **Iteration budget.** Design: "max_iter (default 20)." Reality: the solver runs against a **200-iteration budget** (the non-convergence test forces a one-turn budget; the status doc cites a 200-iteration budget).
- **SAT/SMT conflict detection.** Design §5's component table says the conflict detector uses "Custom SAT/SMT." Design §2 explicitly says the PRG "does not use SAT/SMT solvers." The actual code uses **direct residual checking plus counting free vs. computed parameters** — no SAT/SMT. So the design is internally contradictory, and the implementation follows the "no SAT/SMT" line.
- **Dimensional consistency.** Design property test: "All equations are dimensionally consistent." Reality: **8 of the 39 shipped equations are dimensionally inconsistent** (`param_ingest.md`), and the units checker only reports "how many equations the dimensional check could not decide" (`prg-status.md`) rather than guaranteeing consistency. The shipped graph does not pass the design's own property test.
- **API shape.** Design: "A single `POST /v1/prg/propagate` call returns the full set of updated parameters and the propagation path." Reality: the API is a **tiered set of endpoints** — public reads `/prg/summary`, `/prg/conflicts`, `/prg/cross-validation`, and the three computations are analyst-tier (`prg-status.md`, `test_api_prg.py` with public/analyst keys). No single propagate endpoint with that contract.

## 4. A documentation-internal inconsistency (the capability matrix lags the code)

The `docs/capability_matrix.md` rates three items **L1**:

- Conflict detector (over/under/direct/cycle detection)
- Correction suggestions (ranked, sensitivity-based)
- Translation layer

But the register and code show conflict detection and correction suggestions are **actually built and tested**: `conflicts.py` implements `detect_conflicts` with five `ConflictKind`s, a `ranked()` ordering, and per-candidate corrections carrying `within_range`, `delta`, `elasticity`, and `relative_move`; `tests/ci/test_prg.py` gates the ranking and the "supplied vs. arithmetic" distinction; and the API route (`src/alea/api/routes/prg.py`) actually *applies* a correction only if it stays in range. So the **L1 ratings for conflict detection and correction suggestions appear stale** relative to the current register — unlike the translation layer, whose L1 rating *is* accurate (only 3 parameter→knob routes + 2 bindable inequalities; 49 of 52 settable parameters reach no knob; Pyomo/SymPy absent).

## 5. What actually matches the design

To be fair, the **core engine is real and matches the design's central claims**, and it's the part the capability matrix rates **L4–L5**:

- Symbolic DSL (render, evaluate, differentiate, simplify, solve) — `dsl.py`.
- Graph model with cross-field rules and `structure_issues` self-check — `views.py`, `graph.py`.
- Two-phase topological propagation with the determined-vs-feedback distinction — `graph.py`.
- Feedback solver (Tarjan SCC, damped Gauss–Seidel, divergence-vs-oscillation diagnosis) — `feedback.py`.
- Consistency checking with P1/P2/P3 priorities — `graph.py`.
- A real, ranked conflict detector with corrections — `conflicts.py` (despite the stale L1 rating).
- A working PyPSA/Linopy translation that actually constrains a solve — `translate.py`, `constraints.py`, `whatif/service.py` (`solve_from_prg(constrain=True)`), gated by `test_prg_scenario.py`.

## Bottom line

The PRG's **core is built and matches the design** (graph, propagation, feedback, consistency, conflict detection, and a thin PyPSA/Linopy translation). The gaps are concentrated in **scale** (88 core nodes / 39 equations / 88 edges / 16 systems / 2 feedback loops vs. the design's 784 / ~2,500 / 20 / ~120k / ~15), **coverage** (781 free-placeholder nodes, 49/52 parameters reaching no what-if knob, single-region energy balance that can't be audited nodally), **missing subsystems** (UI, PostgreSQL/GraphML/NetworkX persistence, incremental updates, Pyomo/SymPy backends, PDE, type inference), and **overstated behaviors** (5–15 vs 38/36 convergence, the rejected Anderson acceleration, the "SAT/SMT" contradiction, 8/39 dimensionally inconsistent equations, and the single-endpoint API that is actually tiered). The most reliable single source for the truth is `docs/prg-status.md`, which is the register the code is held to.