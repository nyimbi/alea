# Mozilla Fellowship letter of intent: ALEA

Track II Independent. Answers follow the letter-of-intent form's sections. Counts measured 2026-11-25. Section 4 and 5 are about you; only scaffolds are given. Mozilla asks that content "reflect your own original work, ideas, and voice". Rewrite everything.

## Introduction

Power-system plans decide where grids, generators and debt go. In most African countries the models behind them are closed, spreadsheet-bound or run by foreign consultants, and the assumptions cannot be audited or questioned. ALEA is an open model I am building so that a planner in Nairobi, a regulator or a lender can see every assumption, its unit, its source and what it touches, and change one and watch the effect.

The unusual part is the parameter graph at the centre: 1,881 parameters and 841 equations, each typed and dimension-checked by machine, each citation recorded. It is a dependency graph, not a validated causal model, and I say so. It is also unfinished, which is why I am asking.

## Concept note

**Idea.** An auditable, open planning model for African grids in which no assumption is hidden, and in which a claim that nobody has verified is labelled as such.

**Why now.** AI makes models cheap to write and hard to trust. ALEA was largely written with an AI assistant, and I have recorded what that produces and how it was caught: a gate that exited 0 while testing nothing, a canary that never ran, a default scenario that fails its own check. Open models need this discipline more than closed ones, because anyone can inspect them and should be able to rely on what they find.

**What exists.** 1,881 parameters, 841 equations over 17 systems, 1,993 edges. 841 of 841 equations pass the dimension checker. 108 citations registered, 39 archived. 1,656 tests and 142 of 142 promised gates, each with a canary. A Kenya model that solves to optimality on windows up to 91 days. MIT licence. 371 commits since 2026-10-11.

**What is wrong.** A hand-set derived parameter is silently discarded. The default scenario fails its own check. Only 81 of 1,095 settable parameters (7.4%) reach the solver. There is no full-year solve. 10 claims on the unverified register are unverified.

**The fellowship year** (details in `use-of-funds.md`):
- Q1 (Jun to Aug 2027): fix the input door and the default scenario; archive every cited source; build open Kenya weather and grid datasets.
- Q2 (Sep to Nov 2027): intervention operator; raise solver coupling; full-year Kenya solve.
- Q3 (Dec 2027 to Feb 2028): check the unverified claims; run the model with two African planners who say what they cannot see or trust.
- Q4 (Mar to May 2028): a second country on the same graph; publish the verification template and playbook; hand-off plan.

## Form answers

**Track and issue area.** Track II Independent. Primary issue area: Hard infrastructure: compute, energy, quantum, and the extremes. (Alternative: Sovereign AI, public infrastructure, and maintenance.)

**Title.** ALEA: an auditable open planning model for African power systems

**One-liner.** Every assumption in a national grid plan, with its unit and its source, in the open and machine-checked.

**Target users.** Energy-planning analysts in African ministries, regulators and utilities; lenders and civil-society groups who need to question a plan; academic modellers. [APPLICANT: name any who have agreed to try it.]

**Traction to date.** Pre-launch. Measured: 1,881 parameters, 841 equations, 1,656 tests, 371 commits, one contributor. Users: none yet. What I am measuring: share of settable parameters that reach the solver (7.4% today), cited works archived (39 archived, 43 not), and the first two outside planners who run it. [APPLICANT: correct if you have users or partners.]

**Outputs.** Technology platform or tool; dataset; research publication; educational resource.

**Project stage.** Working prototype.

**Impact beyond your wildest imagination.** A planning ministry in any African country starts from an open, cited graph instead of a consultant's spreadsheet, and funders ask for the assumptions graph with every plan the way they ask for audited accounts.

**Disruption.** Closed consultancy models and anyone who relies on assumptions nobody can inspect.

**Milestones.** As the four quarters above. Subject to revision with Mozilla.

**Charitable purpose.** Yes. Public benefit: open, auditable grid planning for public decisions, beyond the users: electricity consumers and taxpayers whose money follows these plans. The project is not a product for Datacraft's customers.

**Work in the open.** Open sourcing code and assets; publishing educational materials; openly sharing datasets; publishing research papers.

**Section 4, Professional background.** [APPLICANT: your own words. Facts available: founder of datacraft.co.ke; author of ALEA; years of experience band per the form.]

**Technical expertise.** [APPLICANT]

**Your role in the field at year end.** [APPLICANT: yours. Do not use the draft's words.]

**What's next.** [APPLICANT: candidates to consider: a regional open-energy data commons, a public-interest institution that maintains it, a funder who requires the graph with plans. Name who must say yes.]

**Section 5, Fellowship motivation (pick up to three).** [APPLICANT: your choice and reasons.]

**External support.** Applied or planning to apply to: NLnet (EUR 37,500), Research Software Catalyst Fund (US$45,000), EnAccess (email sent). None awarded. [APPLICANT: update.]

**AI and translation disclosure.** Were AI tools used to complete this application: [APPLICANT: answer truthfully]. This draft was produced with an AI assistant; ALEA's code is substantially AI-generated, and that is a subject of the project.

## What not to say

- Not that the graph is causal.
- Not that the model is validated against Kenyan operations.
- Not that Mozilla's US$ amounts or the 501(c)(3) condition are confirmed until you have read them.
