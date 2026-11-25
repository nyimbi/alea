# NLnet application: ALEA parameter graph

Draft in the form's own order. Limits are NLnet's. Counts are the repository's output on 2026-11-25; re-run and requote on the day you submit. Rewrite in your own words: NLnet wants proposals made by humans.

## Introduction

ALEA is an open-source (MIT) planning model for African power systems. Its core is a Parameter Relationship Graph (PRG): every assumption a planner can change is a node with a unit, a range and a source, and every relationship between assumptions is an equation whose dimensions are checked by machine. Changing one dial, such as a discount rate or a build cost, shows which other quantities move and by how much.

The graph is a dependency graph. It is not a validated causal model, and this proposal does not ask for money to claim it is one. It asks for money to make the graph honest, complete and reusable: refuse inputs it cannot honour, connect it to the solver, back every cited number with an archived source, and publish the whole thing as data and a library that other planning projects can load.

## Concept note

**Problem.** Public planning models for national grids are hard to audit. Assumptions sit in spreadsheets and code, units are implicit, sources are links that rot, and a policy dial often changes nothing in the optimisation without anyone noticing. Governments and lenders decide on grid investment from these models.

**What exists today (measured).** 1,881 parameters, 841 equations over 17 systems, 1,993 edges, 57 cross-validation rules, 43 inequality routes that bound solver constraints, 2 feedback loops resolved by damped Gauss-Seidel. 841 of 841 equations pass the dimension checker, 3 by declared exemption. 108 citations registered, 39 archived on disk. 1,656 tests and 142 of 142 promised quality gates, each with a canary that proves the gate can fail.

**What is wrong (measured).** Four defects matter most:
1. Setting a derived parameter by hand is silently discarded.
2. `propagate` accepts parameter names that do not exist.
3. The default scenario fails its own check: frequency nadir 43.6 Hz against a declared range of 45 to 50 Hz.
4. Only 81 of 1,095 settable parameters (7.4%) reach the solver. 1,014 change nothing in the optimisation. 7 of 10 engine fields are named by no parameter.

Also: no full-year Kenya solve exists (optimal on windows up to 91 days), 43 cited works are not archived, and 10 claims on the project's own unverified register are unverified. The full register is `docs/plans/15-completion.md`.

**What the grant does.** Three work packages (budget in `use-of-funds.md`):
- **Data acquisition.** Archive the 43 unarchived cited works with checksums. Build the Kenya hourly weather-year and renewable profiles from ERA5 with atlite, and the transmission topology from OpenStreetMap, as versioned open datasets with provenance.
- **System development.** Make `propagate` refuse hand-set derived values and unknown names. Add an intervention operator (`do`) that sets a node and cuts its incoming edges. Make the default scenario pass its own check. Raise solver coupling from 7.4% to a target set from the measured baseline (gate: a re-run of `scripts/measure_prg_engine_coupling.py`). Clear the type and lint findings.
- **Research.** Complete the full-year Kenya solve and report its solve time and optimality gap. Check each of the 10 unverified claims against a primary source or a re-run, and publish the result either way. Report which parameters the solver is sensitive to.

**Outputs.** A tagged release of the library and graph, the datasets with provenance records, and a short public report with the measured before and after table. All MIT or CC BY.

**Not claimed.** That the graph is causal, that coupling reaches 100%, or that results are validated against Kenyan operational data. A claim moves off the unverified register only with a source or a re-run.

## Form answers

### Fund
Other / open call.

### Proposal title
ALEA PRG: an open, cited, dimension-checked parameter graph for power-system planning

### Project website(s) / repositories
https://github.com/nyimbi/alea

### Summary (max 1000 characters)
ALEA is an MIT-licensed planning model for African grids. Its core is a graph of 1,881 parameters and 841 equations, each with a unit, range and source, and dimensions checked by machine. The graph is a dependency graph, not a validated causal model. Today it has defects I can measure: hand-set derived values are silently discarded, the default scenario fails its own check, and only 7.4% of settable parameters reach the solver. This grant fixes those, archives the 43 cited works not yet saved, builds open Kenya weather-year and grid datasets with provenance, and completes the first full-year Kenya solve. Results: a tagged release, open datasets, and a public report with before and after numbers, including what stays unverified.

### Amount requested
37500

### Budget breakdown (max 4000 characters)
Rate assumed: EUR 50 per hour, 720 hours, plus EUR 1,500 expenses. [APPLICANT: confirm or replace the rate.]
Data acquisition, 120 h = EUR 6,000, plus EUR 1,500 expenses (EUR 1,000 cloud compute for atlite processing, EUR 500 for access to paywalled cited sources). Subtotal EUR 7,500.
System development, 400 h = EUR 20,000. Propagate refusal 60 h, intervention operator 80 h, default consistency 40 h, solver coupling 160 h, type and lint clean 60 h.
Research, 200 h = EUR 10,000. Full-year solve 100 h, claims register 60 h, sensitivity report 40 h.
Total EUR 37,500. Per-task detail in `use-of-funds.md`.

### Comparison with other efforts (max 4000 characters)
PyPSA, PyPSA-Earth, OSeMOSYS, TIMES and GenX are optimisation frameworks. They are mature and ALEA builds on PyPSA; I did not consider replacing them. They keep assumptions as input tables. None I found exposes a typed, cited, dimension-checked graph of the assumptions themselves with machine-checked unit consistency. Reuse of PyPSA-Earth as a dependency is not possible because it is a workflow, not a library, so ALEA reads its outputs at a defined seam. A prior-art survey with archived sources is in `docs/research/alea-prior-art/`. What is new is the graph and its audit trail, not the optimiser. Contributing upstream: the technology-data and PyPSA-Earth communities are where I would send corrections to shared data, and the budget includes that.

### Technical challenges (max 4000 characters)
1. Raising solver coupling without breaking solves. Each newly coupled parameter changes a constraint or cost, so each is added behind a test that the solve still reaches optimality.
2. Full-year Kenya solve time. Windows up to 91 days solve to optimality; a full year may need decomposition or a coarser time aggregation. The aggregation kernel has already produced a large cost error once (a fix is in the history), so every aggregation change gets a differential test against the unaggregated solve.
3. Intervention semantics on a cyclic graph. Two feedback loops exist, so cutting incoming edges must be consistent with the damped iteration.
4. Data licences. ERA5 and OSM terms differ; each dataset carries its licence and the release is split where they cannot be combined.
5. Gates that pass vacuously. Each new gate gets a canary that fails it on purpose; this discipline is documented in `docs/plans/12-quality.md`.

### Ecosystem and engagement (max 2000 characters)
Depends on PyPSA and linopy (solver interface), HiGHS (solver), atlite and ERA5 (weather), OpenStreetMap (grid), PyPSA technology-data (costs). Main users: energy-planning analysts in African utilities and ministries, academic modellers, and lenders who need to audit assumptions. I will engage them by posting the dataset and graph on Zenodo, opening upstream issues for data errors found, and offering the Kenya case to the open-energy-modelling community. [APPLICANT: name any partner who has agreed to review or use it; do not list one who has not.]

### Why this applicant (max 2000 characters)
[APPLICANT: your own words. Facts that exist: runs datacraft.co.ke, a registered Kenyan software company; author of ALEA since 2026-10-11 (371 commits); previous power-sector and software experience. Add only what you can evidence.]

### Other funding (max 1000 characters)
None received. Applied or planning to apply to the Research Software Catalyst Fund (US$45,000, scope: verification layer and playbook) and the Mozilla Fellowship letter of intent. The work packages overlap on the graph hardening; I will split scope and not bill one task twice. [APPLICANT: update if any outcome is known.]

### AI disclosure
- Generative AI used in writing this proposal: [APPLICANT: answer truthfully. This draft was produced with an AI assistant and checked against repository output.]
- Codebase contains AI-generated code: **Yes.** High-level description (max 1000 characters): ALEA was built with Claude Code under my direction. A large part of the code and the equations was written by the model, then checked by tests, by 142 quality gates each with a failing canary, and by machine dimension checks. Defects found in AI-written work are recorded in `docs/plans/15-completion.md` and in the commit history. Review of the equations and sources is my responsibility.

### Contact and applicant
Individual. Country: Kenya. [APPLICANT: name, email, phone with country code.]
