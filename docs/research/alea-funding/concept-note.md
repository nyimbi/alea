# ALEA: an open model for planning African power systems

Concept note, draft for a Moonshot-scale request. Fill the bracketed fields. The budget below is a proposal to react to, not a quote: it uses round numbers inside a US$50k ceiling and should be rebuilt from your own time and compute costs.

## Problem

Electrification plans for African countries rest on planning models that are closed, expensive, or rebuilt from scratch for each study. A ministry or a mini-grid investor cannot rerun the analysis behind a plan, change one assumption, and see what moves. That blocks the scrutiny that open tools in other regions get.

## What ALEA is

An MIT-licensed platform that links capacity expansion, dispatch, market simulation and what-if analysis for the 55 African Union member states and five regional power pools. Every quantity the model uses is a named parameter with a unit, a range, a source, and the equations that determine it. Nothing is a hidden constant.

## What exists now (verifiable in the repository)

- **Parameter graph.** 1,881 parameters and 841 equations. Every parameter appears in at least one equation. This is structural linkage; it does not by itself validate the equations, and the repo says so.
- **Explorer.** A local page to search parameters, read each definition and its equations, zoom a neighbourhood diagram, set values, watch a step-by-step propagation through the real equation solver, save what-if sets, and print.
- **Kenya network.** Built entirely from open data and documented with provenance. It solves to proven optimality on 14-day and 91-day windows; two runs agree to 1e-6 and the objective was recomputed independently from dispatch and capital cost.
- **Defects found and fixed by testing.** A solve stopped at the time limit was being accepted as optimal, and capital costs were entering the objective un-annualised. Both are fixed with tests.

## Honest limits

- The full-year Kenya solve (8,760 hours) does not reach optimality in one hour on one thread. Time aggregation with a validation record, or more cores, is the planned route.
- The Kenya fleet covers 77% of installed capacity against a 90% target, hydro has no energy limit, and solar and wind profiles come from a station-derived stand-in while the reanalysis download is pending.
- The market-simulation and regional power-pool stages are not yet validated against an independent series.

## What this request would deliver

A Kenya reference case that a third party can reproduce end to end, then the first regional step.

1. **Full-year Kenya solve with a published validation of the time aggregation.** Deliverable: a documented run and a record of how much the aggregation changes cost and capacity against the unaggregated 91-day and 14-day cases.
2. **Fleet and hydro completeness.** Close the fleet gap and add a hydro energy limit, so dispatch is not overstated. Deliverable: coverage figure against a named public source.
3. **Eastern Africa Power Pool extension.** Add the neighbouring countries on the Kenya build pattern. Deliverable: a multi-country network that solves and reproduces.
4. **Open documentation for planners.** A short guide that takes a user from the explorer to a Kenya what-if without reading code.

## Why open source matters here

Every dataset used is open and archived with its source; every derived artefact carries provenance. A planner can verify a number back to its origin and fork the model. That is the property closed commercial tools do not offer, and it is the reason this belongs in an open-source funder's portfolio.

## Fit with energy access

ALEA does not install energy. It answers the questions that decide where and how fast it can be installed: what the grid can serve, what capacity to add first, what an assumption costs. The Kenya case is the first of those answers.

## Budget (proposal)

| Item | US$ |
|---|---|
| Developer time, [x] months part-time on items 1 to 4 | [ ] |
| Compute for full-year and multi-country solves | [ ] |
| Documentation and a planner-facing guide | [ ] |
| Independent review of the aggregation validation | [ ] |
| Total (ceiling for a Moonshot) | up to 50,000 |

## Team and contact

[name, role, relevant work]. [Affiliation]. [Contact].

## Evidence

Repository: [URL]. Kenya results and caveats: `docs/research/milestone-data/README.md`. Parameter graph: `docs/prg-docs.md`.
