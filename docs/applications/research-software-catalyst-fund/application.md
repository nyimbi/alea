# Catching what AI-written research code gets wrong: a verification template and playbook from ALEA

Draft for the Research Software Catalyst Fund exploratory grant. Target five pages. Plain language. Rewrite in your own words and fill the `[APPLICANT]` markers. Counts measured 2026-11-25.

## Introduction

Applicant: [APPLICANT: name, location Kenya, affiliation if any]. Request: US$45,000 including US$4,500 (10%) indirect. Duration: six months, April to September 2027.

ALEA is an MIT-licensed model for planning African power systems. I built it with an AI coding assistant, and a large share of its code and equations were written by the model. That makes it a live test of the question this fund asks: how do you get trustworthy research software out of AI-assisted development?

I do not claim the answer is solved. I claim that the project has recorded, working methods for catching what the model gets wrong, and records of where those methods themselves failed. I propose to turn them into something other research software engineers can run and teach.

## What I will do, and what exists at the end

Three public outputs, each released openly:

1. **A verification template (MIT).** A small repository that adds four checks to any Python research project: a unit and dimension checker for equations; a gate register that lists every promised check and fails if a gate has no test; a canary harness that breaks each gate on purpose and requires it to fail; and a claims register in which every statement of fact is marked verified or unverified, with its source. All four exist in ALEA today and are tied to it. The work is to separate them from ALEA and document them.
2. **A playbook (CC BY).** Case studies of defects found in AI-written research code, how each was caught, and which gates failed open first. The case studies are real and in the repository's history: a test suite that passed without running; a dispatcher that ran 0 of 4 test groups and exited 0; a canary patch that never applied; a link checker that matched one spelling and passed 15 dead links; seven emission factors of which three were combustion-only and four were lifecycle values, mixed in one table. The playbook says what to check, in what order, and what a passing result does and does not show.
3. **A hardened ALEA release (MIT)** as the worked example, with a before and after table: defects fixed, coupling measured, claims checked.

## Why it matters, and who benefits

Anyone who lets a model write code that produces numbers a decision depends on has this problem. The common failure is a gate that has never been seen to fail. The template makes that failure visible, and the playbook teaches the habit. Beneficiaries are research software engineers and researchers using AI assistants in any numerical field, and the energy-modelling community, who get an auditable open Kenya model.

It connects to the community priorities in the Edinburgh workshop report (verification and validation, "what does correct mean when code and tests share an author"). I make no claim to have answered those questions. The proposal contributes evidence and tooling.

If a reviewer finds it does not fit those priorities: it still leaves a citable, reusable method and a Kenya model that other people can inspect.

## Where ALEA stands (so the work is measurable)

- 1,881 parameters, 841 equations over 17 systems; 841 of 841 pass the dimension checker, 3 by declared exemption.
- 1,656 tests; 142 of 142 promised gates have a test and a canary.
- 108 citations registered, 39 archived, 43 not.

Known defects the grant fixes (register in `docs/plans/15-completion.md`):
- A derived parameter set by hand is silently discarded.
- The default scenario fails its own check (frequency nadir 43.6 Hz against a 45 to 50 Hz range).
- 81 of 1,095 settable parameters (7.4%) reach the solver.
- There is no full-year Kenya solve; the model solves to optimality on windows up to 91 days.
- 10 claims on the project's unverified register are unverified.

The graph is a dependency graph. It is not a validated causal model, and the work does not make it one.

## Work and schedule (six months)

| Month | Work | Result |
|---|---|---|
| 1 | Archive the 43 unarchived sources. Build weather-year and grid datasets with provenance | Data on Zenodo, sources indexed |
| 2 | Refuse hand-set derived values and unknown names; default scenario passes its check | Gates with canaries |
| 3 | Intervention operator; start raising solver coupling | Tests for do-semantics |
| 4 | Solver coupling; full-year Kenya solve attempt | Coupling count re-measured |
| 5 | Check the 10 unverified claims; extract the template | Template repository |
| 6 | Write the playbook; tag the release; short note on what I learned | Playbook, release, note |

Readiness: the code, tests and plan exist now. I can start in April and finish inside six months.

## Who is involved

[APPLICANT: you, role and hours. Name any independent reviewer who has agreed. The budget includes a modest honorarium for one outside reviewer of the playbook; do not list a name unless they have said yes.]

## Budget

US$45,000: labour 600 h at US$60 (US$36,000, an assumption), expenses US$4,500, indirect US$4,500. Detail in `use-of-funds.md`: data acquisition US$8,000, system development US$22,000, research and verification US$10,500, indirect US$4,500.

## Related proposals

I have applied or plan to apply to NLnet (EUR 37,500, open call) and the Mozilla Foundation Fellowship (letter of intent). The NLnet work is the graph hardening and data; this proposal funds the template and playbook and shares the ALEA fixes. If both are awarded I will split scope and not claim one task twice.

## Openness and AI use

All outputs are public: code on GitHub under MIT, documents and data on Zenodo under CC BY. ALEA's code is substantially AI-generated, and this proposal was drafted with an AI assistant and checked against repository output. [APPLICANT: state this in your own words if the form asks.]
