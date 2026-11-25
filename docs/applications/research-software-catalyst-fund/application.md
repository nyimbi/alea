# How to make AI-written research software trustworthy: a verification template and playbook, with a worked example

Research Software Catalyst Fund, exploratory grant. Applicant: Nyimbi Odero, Kenya. Request: US$45,000 (includes US$4,500 indirect). Duration: six months, April to September 2027.

Paste-ready. Amend where you would say it differently. Target length is five pages (about 2,600 words); `wc -w` is run on the body below. Figures were measured 2026-11-25; re-run the commands in `../README.md` before submitting.

---

## Summary

I will release three open outputs that help researchers who write code with AI assistants catch what those assistants get wrong. First, a small verification template (MIT) that adds four checks to any Python research project. Second, a playbook (CC BY) of real defects found in an AI-written research codebase, how each was caught, and which checks failed open first. Third, a hardened release of that codebase, ALEA, an open model for planning African power systems, as the worked example with a published before and after table.

## The problem

Anyone who lets a model write code that produces numbers a decision depends on has the same problem: the code runs, the tests pass, the result looks plausible, and it is wrong. The community has named this. The Edinburgh workshop asked "what does correct mean when code and tests share an author?" and ranked verification and validation among its priorities.

I have lived it. ALEA was written largely with an AI assistant. ALEA's quality plan (`docs/plans/12-quality.md`), its defect register (`docs/plans/15-completion.md`) and its commit history record these failures, each of which went unnoticed under the checks that existed at the time:
- a test suite that reported success while running nothing (an async plugin was missing);
- a test dispatcher that ran 0 of 4 groups and exited 0;
- a "canary" meant to prove a check could fail, whose patch never applied, so the check was believed without ever having been seen to fail;
- a link checker that matched one spelling of a link and passed 15 dead ones;
- a table of seven emission factors in which three were combustion-only and four were whole-lifecycle values, so the numbers were not comparable;
- a default scenario that fails its own validity check (a frequency nadir of 43.6 Hz against a declared range of 45 to 50 Hz);
- 7.4% of the model's settable parameters (81 of 1,095) reaching the solver, so most dials a user could turn changed nothing in the result;
- a data-centre load that raised demand by 16.3 TWh on a generic baseline that is not Kenya, while a headroom figure fell below 1 and no reliability output moved: a plausible-looking answer to a question the model cannot yet answer.

The pattern is the same each time: **a check that has never been seen to fail is a check that may not be running.** Model-written code is especially prone to it, because the model writes the code and the check, and both can share the same blind spot.

## The value proposition

| For whom | What they get | What it replaces |
|---|---|---|
| A researcher using an AI assistant on numerical code | Four checks they can add in an afternoon, and a playbook that says what to look at first | Trusting that green tests mean correct |
| A research software engineer reviewing AI-assisted code | A concrete list of ways gates fail open, each with a real example and a probe | Ad hoc review with no shared vocabulary |
| A team lead deciding whether to allow AI-assisted work | A recorded account of what went wrong in one project, with counts | Policy written from fear or enthusiasm |
| Energy-modelling and policy communities | An open Kenya power-planning model whose assumptions can be inspected, with a stated list of what is unverified | A closed or opaque model |

The unique offer is the combination of a method and a body of evidence from one real project, including its failures. Most guidance on AI-assisted research code is opinion. This is a log of defects with their detection.

## What exists at the end

**1. A verification template (MIT licence, GitHub).** A small repository with four components, each already working in ALEA and each to be separated from it, tested on its own and documented:
- a **unit and dimension checker** for equations, so a model cannot add a cost to a power;
- a **gate register**: a list of every check the project promises, failing if a promised check has no test;
- a **canary harness**: for each gate, a deliberate break that the gate must catch, restored from a backup, so no gate passes by default;
- a **claims register**: every statement of fact marked verified or unverified with its source, so an unverified claim cannot be published as verified.

**2. A playbook (CC BY, Zenodo).** About 20 pages. Each defect above, and the others recorded in the repository, as a case: what it looked like, how it was caught, why the earlier checks missed it, and the probe to look for the same class elsewhere. It ends with a short order of checks for a project that starts today.

**3. A hardened ALEA release (MIT).** The worked example. The five defects listed in "Work" are fixed with before and after counts printed by the repository's own commands.

A short note on what I learned closes the grant, as the fund asks.

## Why the template is not "a new package for one project"

The four checks are written for ALEA today. The work in this grant is to remove every ALEA-specific assumption, run them on a second, unrelated Python project (a public one I do not control, chosen by month 3 and named in the note), and document what had to change. If the template cannot run there, that result goes in the playbook.

## Work, schedule and gates

| Month | Work | Gate |
|---|---|---|
| 1 | Archive the 43 cited sources not yet saved. Build Kenya weather-year and grid datasets with provenance | 43 archived with checksums; datasets on Zenodo |
| 2 | Refuse hand-set derived values and unknown parameter names. Fix the default scenario | The probe that returns 45.0 now raises; `alea prg check` exits 0 |
| 3 | Add an intervention operator (`do`). Choose and run the template on a second project | Pinning a node to its own derived value reproduces the normal result on every derived node |
| 4 | Raise solver coupling. Attempt the full-year Kenya solve | Every one of 1,095 settable parameters classified as knob, constraint, audit or none; each "none" justified |
| 5 | Settle the unverified claims. Extract and test the template | Claims #1, #2, #3, #6 and #9 produced or withdrawn; template tests pass on both projects |
| 6 | Write the playbook. Independent review. Tag the release. Write the note | Playbook on Zenodo with a CC BY licence; reviewer's comments addressed or published |

**Readiness.** The code, tests and a task-by-task plan exist now (`docs/plans/15-completion.md`, committed 2026-11-25). Nothing waits on a dependency. I can start in April and finish inside six months.

## Where ALEA stands (measured 2026-11-25)

1,881 parameters and 841 equations over 17 systems; 841 of 841 equations pass the dimension checker, 3 by written exemption. 1,656 tests; 142 of 142 promised gates have a test and a canary. 108 citations registered, 39 archived. Defects: a hand-set derived parameter silently discarded; unknown names accepted; the default scenario failing its own check; 81 of 1,095 settable parameters reaching the solver; no full-year Kenya solve (optimal on windows up to 91 days); 10 claims on the unverified register, all unverified.

The graph is a dependency graph, not a validated causal model. This grant does not change that.

## Why the worked example is worth hardening

ALEA's use case has a public stake. In May 2026 Semafor reported that Microsoft and G42's US$1 billion Kenyan data centre was unlikely to proceed, with the president saying it would need about a third of the country's installed capacity. The regulator's 2024 figures show a 2,288 MW peak against 3,082 MW effective capacity. Whether a grid can host a compute load is a question a checkable model should answer in public, before an announcement. ALEA cannot answer it yet: data-centre load enters as annual energy on a generic baseline, there is no peak check, and reliability does not respond to reserve falling. I state this because a model that looks authoritative and is not is the exact failure this grant studies. The grant does not build the hosting test. It builds the verification layer a hosting test would need to be trusted, and the Kenya fixes it funds are its base. ALEA does not claim open African grid data is missing: my competitive survey finds PyPSA-Earth, AETOS and Calliope Africa already provide it. The survey does not cover data-centre hosting, and I have not checked whether those tools do.

## How it connects to community priorities

It addresses the Edinburgh priorities on verification and validation and on tradeoffs: it produces a tested method for agentic verification, a case-study collection of AI-assisted work (the fund's examples list both), and evidence on what "correct" means when code and tests share an author. I make no claim to settle those questions. If a reviewer judges it does not match a stated priority, it still leaves a citable method, a body of case studies, and an open Kenya model.

## Who benefits, beyond me

Researchers and RSEs in any numerical field using AI assistants. The energy-modelling community and African planners, who get an inspectable model. Teachers of computational skills, who get real defect cases. The applicant benefits least: the outputs are public, and the fund's own rule excludes work that mainly benefits an individual.

## Who is involved

I am Nyimbi Odero, a software developer in Kenya, founder of datacraft.co.ke, and the sole author of ALEA (371 commits since 11 October 2026). I apply as an individual because the fund pays individuals through Hack Club Bank and does not fund companies. One independent reviewer of the playbook is budgeted (US$1,500 honorarium) and will be named when they agree. No other person is listed as involved.

## Budget (US$45,000)

| Item | US$ |
|---|---|
| Data acquisition (100 h, plus US$2,000 expenses) | 8,000 |
| System development (350 h, plus US$1,000 compute) | 22,000 |
| Research and verification (150 h, plus US$1,500 reviewer honorarium) | 10,500 |
| Direct total | 40,500 |
| Indirect costs (10% of the total) | 4,500 |
| **Total** | **45,000** |

600 hours at US$60. Itemised in `use-of-funds.md`. The budget is proportionate: about 60% pays for the engineering and testing that make the template real, 25% for the evidence behind the playbook, and the rest for data, compute and review.

## Risks, stated plainly

- The template may not run cleanly on a second project. That outcome is reported, not hidden.
- The full-year solve may not reach optimality. The report says so.
- Some of the 10 unverified claims need large milestones. I commit to five and to a written failure condition for the other five.
- I am one person. The plan is ordered so each month ends in a usable, public artefact.

## Related proposals

I have applied or plan to apply to NLnet (EUR 37,500, for the graph hardening and open datasets) and to the Mozilla Foundation Fellowship (letter of intent). The overlap is the ALEA fixes. This grant's distinct scope is the template, the second-project test and the playbook. If more than one is awarded I will divide the scope and will not claim any task twice.

## Openness and AI use

Code on GitHub under MIT; documents and data on Zenodo under CC BY. ALEA's code is substantially AI-generated (Claude Code), and this proposal was drafted with an AI assistant from the repository's measured output and then reviewed and amended by me. The playbook discloses the same for itself.
