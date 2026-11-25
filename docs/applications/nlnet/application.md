# NLnet application: ALEA parameter graph

Paste-ready. Each answer under "Form answers" is within NLnet's character limit (counted by `docs/applications/check_limits.py`). Read each answer once and amend where you would say it differently: NLnet wants your own words, and you answer its AI disclosure yourself. Counts are the repository's output on 2026-11-25; re-run `uv run alea prg summary` and `scripts/measure_prg_engine_coupling.py` before submitting and update any figure that moved.

## The case in one page

**The problem.** A national power plan commits a country to decades of generation, grid and debt. The models behind such plans are rarely open to inspection. Assumptions sit in spreadsheets and code, units are implicit, sources are links that decay, and a policy dial can be wired to nothing without anyone noticing. A planner, regulator or lender who asks "what happens if this assumption is wrong, and where did it come from?" usually cannot get a checkable answer.

**What ALEA is.** An MIT-licensed planning model for African power systems, built Kenya first. At its centre is a Parameter Relationship Graph (PRG): 1,881 parameters and 841 equations across 17 systems (cost, finance, demand, reliability, emissions, employment, water, and others). Each parameter has a unit, a range and a source. Each equation is checked by machine to have the same dimension on both sides (841 of 841 pass; 3 are exempt by written declaration). Change one dial and the graph shows what else moves.

**What it is not.** It is a dependency graph. It is not a validated causal model, and nothing in this proposal claims it is.

**Why it matters now.** Compute for AI is sized in megawatts at a grid node, so power decides where it can go. In May 2024 Microsoft and G42 announced a US$1 billion geothermal data centre at Olkaria, Kenya. In May 2026 Semafor reported it unlikely to proceed: President Ruto said it would need about a third of Kenya's roughly 3,000 MW of installed capacity. The regulator's own figures (EPRA, 2024) show a 2,288 MW peak against 3,082 MW effective capacity. The arithmetic was not public when the announcement was made. The use case I am building towards is a public check of whether a power system can host a proposed load, at the evening peak, at what cost to others and with what uncertainty. That check does not exist in ALEA yet (see the last defect below), and the grant finishes the base it needs. The longer aim is open, sourced data packs for more African countries, after Kenya meets its gates. My competitive survey finds that PyPSA-Earth, AETOS and Calliope Africa already provide open continental data and models, so I do not claim open African data is missing. What I add is per-field provenance, archived sources and checked units.

**Why it needs this grant.** The graph has defects I can measure, and they are the kind that make a model untrustworthy while it looks finished:

| Defect | Measured today | Consequence |
|---|---|---|
| Hand-set derived values are silently discarded | set 136, get 45.0 back, no error | a planner believes they ran a scenario they did not |
| Unknown parameter names are accepted | a typo returns unchanged | a misspelt dial does nothing and says nothing |
| Defaults fail their own check | frequency nadir 43.6 Hz against a 45 to 50 Hz range | every "what moved" report starts from a violated state |
| Most dials do not reach the optimiser | 81 of 1,095 settable parameters (7.4%); 1,014 reach none | most scenario choices change nothing in the plan |
| No full-year Kenya solve | optimal on windows up to 91 days | the headline planning claim is not yet shown |
| Sources not archived | 43 of 108 citations have no local copy | links rot and a number cannot be re-checked |
| Unverified claims | 10 on the project's own register, all unverified | published claims outrun evidence |
| Data-centre load is energy only, on a generic baseline | a 1,000 MW IT load raises demand 16.3 TWh on a default of about 47 TWh, which is not Kenya (EPRA's half-year 7.2 TWh annualises to about 14); no peak check; reliability does not respond to headroom | the model cannot yet say whether a grid can host a load, so it must not be quoted as doing so |

**What the money buys, and how you will know.** Every item has a command that prints a number before and after.

| Deliverable | Gate (how it is checked) |
|---|---|
| The input door refuses what it cannot honour | the 136 probe raises an error naming the equation; unknown names raise with a suggestion |
| An explicit intervention operator (`do`) | pinning a derived node to its own derived value reproduces the normal result on every derived node |
| Defaults consistent | `alea prg check` exits 0 at defaults |
| Coupling made visible and mostly closed | every one of the 1,095 settable parameters classified as knob, constraint, audit or none, each "none" justified in writing; the 7 unnamed engine fields named; a plain `alea solve` and the what-if path produce identical `ScenarioParameters` |
| Sources preserved | 43 archived works with checksums, the index updated |
| Open Kenya data | hourly weather-year profiles and grid topology with provenance records, on Zenodo |
| First full-year Kenya solve | optimal, two runs agree to 1e-6, solve time and gap reported |
| Claims settled | claims #1, #2, #3, #6, #9 produced or withdrawn with evidence; the other five get a written failure condition |

**Value to the commons.** One open, auditable reference for how a national plan's assumptions connect, which anyone can load, check and extend. Reusable well beyond Kenya: the graph, its checker and its data are libraries and files, not a service.

**Why NLnet.** What this project most needs, and what no optimiser provides, is the trust layer: provenance, units, and honest labelling of what is unverified. That is tedious infrastructure work on a commons, which is what this grant would pay for.

## Introduction

ALEA is an open planning model for African power systems. I am building it so that a planner in Nairobi, a regulator or a lender can see every assumption behind a grid plan, its unit and its source, change one and watch the effect, and see clearly what has not been verified. The graph at its centre has 1,881 parameters and 841 dimension-checked equations. It is unfinished in ways I can measure, and this proposal funds finishing it in a way a reviewer can re-run.

## Concept note

**Idea.** Make a public, cited, machine-checked parameter graph that cannot lie by omission: it refuses inputs it cannot honour, shows which dials reach the optimiser and which do not, keeps a copy of every source it cites, and labels every unverified claim as such.

**Why existing tools do not already do this.** Optimisers (PyPSA, OSeMOSYS and others) take assumptions as input tables. The ontology work (Open Energy Ontology) shares vocabulary for data but not computable equations. Documented-equation frameworks (MESSAGEix) publish the maths without checking units or tracking where each number came from. System-dynamics tools check units but are not open energy planning models. Modelica declares units but its own 2008 paper says checking semantics were not specified. No project I found combines typed parameters, per-equation dimension checking, per-number citations and an explicit account of which dials reach the solver. The survey with archived sources is `docs/research/alea-prior-art/README.md`.

**Approach.** Three work packages, in the order that their dependencies require: (1) data acquisition, (2) system development, (3) research. The plan with gates for every defect is `docs/plans/15-completion.md`. Refusal first, then defaults, then intervention, then coupling, because coupling built on a graph that accepts bad input measures noise.

**Method.** Each fix lands as test, then change, then a canary: a deliberate break that the new test must catch, so no gate passes by default. The project has 1,656 tests and 142 of 142 promised gates with canaries; the discipline is documented in `docs/plans/12-quality.md`. This matters because most of ALEA was written with an AI assistant, and checks that have never been seen to fail are the main risk.

**Outputs.** A tagged release (MIT). Datasets and the 43 archived sources (CC BY, with ERA5 and OSM terms recorded). A public report with the before and after table and the claims outcomes.

**What I do not claim.** That the graph is causal. That coupling reaches every parameter. That the model is validated against Kenyan operational data. That a claim is verified before the artefact exists.

**Risks.** The full-year solve may need decomposition and may not reach optimality within the time; the report will say so either way. Coupling a parameter changes a constraint, so each coupling is gated by an optimality test.

## Form answers

### Fund
Other / open call

### Proposal title
ALEA PRG: an open, cited, dimension-checked parameter graph for power-system planning

### Project website(s) / repositories
https://github.com/nyimbi/alea

### Summary (max 1000 characters)
ALEA is an MIT-licensed model for planning African power systems. Its core is a graph of 1,881 parameters and 841 equations. Every assumption has a unit, range and source, and a machine checks that each equation is dimensionally consistent. A planner changes one dial and sees what moves. It is a dependency graph, not a validated causal model. It also has measurable defects: a hand-set derived value is silently discarded, the default scenario fails its own check, and only 81 of 1,095 settable parameters (7.4%) reach the optimiser, so most dials change nothing. This grant fixes these, archives the 43 cited sources not yet saved, publishes open Kenya weather and grid datasets with provenance, and attempts the first full-year Kenya solve, the base for testing whether a grid can host a data centre. Output: a tagged release, datasets, and a public report with before and after numbers, including what stays unverified.

### Amount requested (EUR)
37500

### Budget breakdown (max 4000 characters)
Rate: EUR 50 per hour. 720 hours (EUR 36,000) plus EUR 1,500 expenses = EUR 37,500. Every task ends in a command that prints a before and after number.

1. Data acquisition: 120 h (EUR 6,000) + EUR 1,500 expenses = EUR 7,500
- Archive the 43 cited works not yet saved, with checksums and an index entry: 40 h
- Kenya hourly weather-year profiles from ERA5 via atlite, with provenance record: 50 h
- Kenya transmission topology from OpenStreetMap, checked against published line lists: 30 h
- Expenses: cloud compute for profile processing EUR 1,000; access to paywalled cited sources EUR 500

2. System development: 400 h = EUR 20,000
- Refuse hand-set derived values and unknown names in the input door: 60 h
- Intervention operator (`do`) that pins a node and recomputes its descendants, including the two feedback loops: 80 h
- Make the default scenario pass its own check: 40 h
- Solver coupling: classify all 1,095 settable parameters, name the 7 unnamed engine fields, make `alea solve` and the what-if path produce identical scenario parameters, test that each of the 43 bound routes binds or is slack in a known case: 160 h
- Type and lint clean (16 pyright errors, 4 ruff findings): 60 h

3. Research: 200 h = EUR 10,000
- Full-year Kenya solve with decomposition, solve time and optimality gap reported: 100 h
- Claims register: produce or withdraw claims 1, 2, 3, 6 and 9, and write a failure condition for the other five: 60 h
- Sensitivity report on which parameters move the solve: 40 h

Gates: the probe that returns 45.0 raises; `alea prg check` exits 0; the coupling script classifies all 1,095; pyright and ruff exit 0; the full-year solve is optimal and two runs agree to 1e-6. Not funded: documentation debt beyond this scope. If a gate fails I report it as failed.

### Comparison with other efforts (max 4000 characters)
Optimisers: PyPSA, PyPSA-Earth, OSeMOSYS and similar frameworks are mature. ALEA solves with PyPSA and I did not consider replacing it. These tools take assumptions as input tables; they do not hold the assumptions as a typed, cited graph with machine-checked units. PyPSA-Earth is a workflow, not a library, so ALEA reads its outputs at a defined seam instead of depending on it.

Shared vocabularies: the Open Energy Ontology and Knowledge Graph give a common language for annotating energy data and models. They describe data, not computable equations.

Documented equations: MESSAGEix publishes its mathematical specification openly. It does not, as far as I could read, check dimensions per equation or record a source per number.

Other fields: system-dynamics tools (Vensim, Stella) check units, and Modelica declares units, but neither is an open energy planning model, and the 2008 Modelica paper states that unit-checking semantics were not specified.

COSIMO (Politecnico di Torino) organises models, parameters and interconnections machine-readably for multi-energy co-simulation. I have read only its abstract and have not compared it further.

What is new: one open graph that combines (a) typed parameters, (b) a dimension check on every equation, (c) a source recorded for every number, (d) an explicit, measured account of which dials reach the solver, and (e) a register that labels every unverified claim. The novelty is the audit trail, not the optimiser. I do not claim the graph is causal: an edge is causal only if it survives intervention, and the equations are documented relationships, not estimated from interventional data. The intervention operator I propose answers "what if this quantity were X within the model's equations", and the documentation says so.

Contributing instead: I considered it. The optimiser communities are the right place for solver work and I will contribute data corrections I find (technology costs, grid data) upstream. The graph and its checks do not fit an existing project's scope, which is why it is its own project. The survey with archived sources is in docs/research/alea-prior-art/.

### Technical challenges (max 4000 characters)
1. Coupling without breaking solves. Each parameter that newly reaches the optimiser changes a cost or a constraint. I add each behind a test that the solve still reaches optimality and that the same scenario through `alea solve` and through the what-if path gives identical scenario parameters.

2. Full-year solve. The Kenya model solves to optimality on windows up to 91 days. A full 8,760-hour year may exceed memory or time. I will use rolling-window decomposition, record solver, gap, wall time and peak memory, and report a non-optimal result as such. An aggregation kernel in this project once produced a large cost error that only a differential test against the unaggregated solve exposed, so every aggregation change gets that test.

3. Intervention on a cyclic graph. Two feedback loops exist (capture price and VRE share; demand and tariff), solved by damped Gauss-Seidel. Pinning a node inside a loop breaks the loop, so the loop must be re-solved without that variable. I test each loop separately, and a property test checks that pinning a node to its own derived value reproduces the normal result.

4. Refusal that does not break callers. Several callers pass every default plus overrides. The new refusal must accept a supplied derived value equal to the computed one and reject only a differing one, and every caller must turn the refusal into a clear error.

5. Gates that pass by default. A check that has never failed is not evidence. Each new gate gets a canary: a deliberate break the test must catch, restored from a backup. The project's own register shows the ways gates failed open (a test suite that ran nothing, a dispatcher that ran 0 of 4 groups and exited 0).

6. Data licences. ERA5 and OpenStreetMap carry different terms. Each dataset records its licence, and a release is split where the terms cannot be combined.

7. Honesty about what was verified. For paywalled sources I archive the landing page and abstract and mark them abstract-only; I do not claim to have read content I did not.

8. Hosting a load is a peak and network question. Data-centre load enters today as annual energy on a generic baseline. Testing whether a grid can host it needs a Kenya baseline, a load shape and a reserve check against effective capacity first. Siting needs a network and the full-year solve, so I treat it as later work and do not promise it.

### Ecosystem and engagement (max 2000 characters)
Depends on: PyPSA and linopy (model and solver interface), HiGHS (solver), atlite and ERA5 (weather data), OpenStreetMap (grid), PyPSA technology-data (costs), Zenodo (archiving). Upstream issues for data errors I find go to those projects.

Main users: energy-planning analysts in African ministries, regulators and utilities; lenders and civil-society groups who need to check a plan's assumptions; academic energy modellers who want a cited parameter set; open-energy-modelling researchers who want to compare structures.

Engagement: publish the graph, datasets and report on Zenodo and GitHub; open upstream issues with evidence; present the Kenya case to the open energy modelling community; ask two African planners to run the model and tell me what they cannot see or trust, and record their answer. I list no partner as committed until they have agreed.

Beyond Kenya, I aim to publish open, sourced country data packs under a shared schema, one country at a time, only after Kenya passes its gates. I will build on PyPSA-Earth's open data, not replace it, and add provenance, archived sources and licence records per field. I will ask planners what they already have and report the answer whether or not it favours this project.

### Why this applicant (max 2000 characters)
I am Nyimbi Odero, a software developer in Kenya and the founder of datacraft.co.ke, a registered Kenyan software company. I started ALEA on 11 October 2026 and have written it as a single maintainer since, with 371 commits, 1,656 tests and 142 quality gates. I know the problem as a Kenyan practitioner: the data and assumptions behind African grid plans are hard to reach. I applied as an individual because the work is public-interest and the code is MIT. The project's record includes defects I found in my own work and the gates built to catch them; the full list is in docs/plans/15-completion.md, written before applying, and I would rather the reviewer read it than discover it.

### Other funding (max 1000 characters)
None received. I have applied or plan to apply to the Research Software Catalyst Fund (US$45,000, for a verification template and playbook extracted from this work) and the Mozilla Foundation Fellowship (letter of intent). The graph hardening is the shared base; if more than one is awarded I will divide scope and will not bill any task twice. I have sent an introduction to EnAccess; no funding has been agreed.

### Attachments
None. The proposal is self-contained.

### AI disclosure
**Did you use generative AI in writing this proposal?** Yes.
**Which model?** Claude (Anthropic).
**What did you use it for?** To draft the text from the repository's measured outputs and the project's written plan, and to check character limits. I reviewed the draft, checked each figure against the printed output of the repository's commands, and amended it. I am responsible for what is submitted. [Amend if you change how you worked. Upload your prompts and outputs if NLnet's form requires them.]

**Does the codebase contain AI-generated code?** Yes, a significant amount.
**High-level description (max 1000 characters):** ALEA was written with Claude Code under my direction. A large part of the code, the equations and the tests was generated by the model, then checked by 1,656 tests, 142 quality gates (each with a canary that proves it can fail), and a machine check that every equation is dimensionally consistent. Defects in the AI-written work are recorded in docs/plans/15-completion.md and in the commit history. Part of this grant exists to harden exactly that: refuse inputs the graph cannot honour, label unverified claims, and keep a copy of every cited source. I review the equations and sources and am responsible for them.

### Contact and applicant
Name: Nyimbi Odero. Type of applicant: Individual. Country: Kenya. [Email, phone with country code, optional OpenPGP key.]
