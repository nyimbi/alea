# Prior art for the parameter graph, and how much of it reaches the solver

Date: 2026-11-25. Question: is the PRG new, is it causal, is it ALEA's core.
Method: eight web searches (standard mode), eleven pages archived in `sources/`, plus a measurement on the shipped graph. Not an exhaustive review: no paper was read past its abstract or the cited passage.

## Prior art found

| Family | What it already does | Source |
|---|---|---|
| Open Energy Ontology and Knowledge Graph | A shared vocabulary and graph for annotating energy data and models, argued as a precondition for model coupling. Describes data, not computable equations | `oeo-booshehri-2021-pik.pdf`, `oep-knowledge-representation.html` |
| COSIMO (Politecnico di Torino) | Organises models, technologies, parameters and interconnections machine-readably, for multi-energy co-simulation. Unread beyond the abstract | search snippet only |
| MESSAGEix | Open framework whose variables and equations are documented | `messageix-core-math-spec.html` |
| Modelica | Acausal components governed by equations. Declares units; the 2008 paper says checking semantics were not in the specification | `modelica-spec-intro.html`, `modelica-units-2008-session1a1.pdf` |
| System dynamics (Vensim, Stella) | Stock-flow models with unit-consistency checks; causal loop diagrams used for Kenya and Tanzania power studies | `vensim-units-check.html`, `isee-units-check.html` |
| Pearl's structural causal models | An edge is causal if it survives intervention: do(X) cuts X's incoming edges | `pearl-do-calculus-intro-arxiv-1305.5506.pdf` (secondary) |

## Reading

- Parameters linked by equations, dimension checks, documented equations and causal-loop mapping are each established. No claim of a new data structure holds.
- Not found in these searches: an open model whose equations number in the hundreds across technical, financial, health, employment and water systems, each tied to an archived citation by a CI gate, with the same propagation routine behind the CLI and the explorer. That is a finding about eight searches, not proof of absence. `docs/capability_matrix.md` line 547 states "No comparable system exists"; this review does not support that sentence and it has been softened.
- "Causal" is not earned. Setting a derived node by hand is discarded without a message: with `additional_abatement_mtco2` (derived, 45.0) overridden to 136, propagation returned 45.0 and left its child unchanged. The graph has no intervention operator, so under Pearl's definition its edges are dependencies, not causal claims. Most edges are accounting identities or cited fits.

## Coupling count

`uv run python scripts/measure_prg_engine_coupling.py`, measured 2026-11-25:

| Measure | Value |
|---|---|
| Nodes / settable / derived / endogenous | 1,881 / 1,095 / 767 / 19 |
| Settable parameters reaching an engine knob | 3 of 1,095 (carbon price, demand growth, fuel price) |
| Settable parameters read as constraint terms | 78, across 43 bound inequality routes |
| Overlap | 0 |
| Settable parameters reaching any solver input | 81 of 1,095 (7.4%) |
| Settable parameters reaching none | 1,014 |
| Engine knobs the graph never names | 7 of 10 |
| Modules outside `prg/` that import it | `cli.py`, `api/routes/prg.py`, `whatif/service.py`; `planning/` imports none |

The other 1,014 are connected to other nodes (no isolated node), so they propagate to derived values and feed the post-solve audit, but changing one does not change the optimiser's answer. Constraint terms only bind on the what-if path with `constrain=True`.

## Consequence for the claim

The graph is the core of what makes ALEA inspectable. It is not yet the core of what ALEA computes: 7.4% of its settable surface moves the solver. Closing that, by adding translations and constraint routes, is what would make "core" accurate.

## Language adopted

"An open, cited, dimension-checked parameter graph spanning technical, economic and social systems." Not "novel causal graph". Applied to the README, `docs/capability_matrix.md`, and both websites.
