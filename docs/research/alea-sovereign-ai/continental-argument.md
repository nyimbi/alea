# Why finishing ALEA, with open data for every African country, matters to AI in Africa

Written 2026-11-25. Extends `README.md` in this directory, which assessed the narrower thesis against what the code does today. This document argues from the goal, not from the current state. Where a claim rests on an unverified premise it is marked **[premise]**, and section 7 lists what would falsify each.

## 1. The goal, stated apart from where ALEA is

**End state.** For every African country, an open, versioned, cited country pack (demand, generation fleet, network, weather years, tariffs, outage history, each with provenance and licence) feeding one open, unit-checked, tested model. Any party can ask the same question of any country and get an answer whose assumptions they can read: "can this system host this load, at what cost to others, what must be built first, how sure are we?"

**Where it is today** (README section 5): a generic default baseline, no network or siting, load enters as energy and not as peak, reliability does not respond to headroom, 7.4% of settable parameters reach the solver. Nothing in this document describes the present. It describes why the end state is worth the work, and what ordering protects it from failing on the way.

## 2. The argument in six steps

1. **AI capacity is a power-and-place decision before it is a software decision.** A training or inference campus is sized in megawatts at a node with firm supply. Kenya's stalled Olkaria project (Semafor, 6 May 2026) is the existence proof that the arithmetic can be missing at signing.
2. **The decision recurs across 54 countries, each time from scratch.** Every ministry, utility, lender and developer re-derives hosting feasibility privately, or does not. **[premise: no open, comparable, continental evidence base exists. Not yet surveyed; section 7 test 1.]**
3. **The parties are not equally informed.** A hyperscaler or fund holds benchmarks from many deployments. A host ministry holds one grid. This is bargaining under asymmetric information, and it sets the terms of the deal (tariff, firm-power guarantees, who funds reinforcement, how much compute stays in-country).
4. **Cheap talk dominates until claims become checkable.** An MoU costs nothing to announce and nothing to abandon. A published, cited feasibility check is a costly signal in the game-theory sense: it can be wrong in public. Making it open converts "we will host 1 GW" from an announcement into a claim with a standard of proof.
5. **Open, comparable data for all countries changes the game in ways one-country data cannot.**
   - Countries can see each other's real constraints, which reduces the pull of competitive overbidding on incentives and tariffs. **[premise]**
   - Cross-border supply matters: the regional power pools trade across borders, so a siting question in one country is often a regional question. A model of one country cannot see the neighbour's surplus or shortfall.
   - Buyers operate continentally. A deployment plan across several countries (Cassava's announced five-country rollout, per the arXiv tracker's account) needs one comparable frame, not five incompatible ones.
   - Small and data-poor countries gain most from a shared schema, because they cannot afford a bespoke study. They are also where the evidence is thinnest.
6. **Sovereignty is not the model's output, but it is a precondition the model supports.** Sovereign compute needs a host that can negotiate from facts, plan supply ahead of demand, and say no to a load it cannot carry. That is what open data plus a trusted model give. Chips, capital, talent and law remain separate, and ALEA claims nothing about them.

The conclusion that follows: the benefit is **informational and structural**. It lowers the cost of knowing, for everyone, equally.

## 3. Why completion matters and progress alone does not

A half-built model is worse than none here, for a specific reason: it produces confident numbers.

- The README run shows it. At 1,000 MW the graph reports a falling tariff, an artefact of what the model leaves out. A planner who reads that as a benefit is misled by a tool that looks authoritative.
- One public wrong answer in a politically charged decision (a presidential data-centre announcement) discredits the method for every country after it. Trust is the asset, and it is lost faster than it is built.
- The project's own defect register (`docs/plans/15-completion.md`) is the difference between a demonstration and a standard: refusal of inputs it cannot honour, an intervention operator, solver coupling classified for every settable parameter, claims either produced or withdrawn.

So "complete" has a meaning, and it is checkable: every settable parameter either reaches the solver or is justified as not doing so; every headline number carries an interval; every cited source is archived; every unverified claim is settled or withdrawn. A model short of that should not be used to advise a hosting decision, and should say so.

## 4. Why the data is half the contribution

The graph's structure is country-agnostic. What is country-specific, and what limits every outside effort, is the data. Three consequences.

- **Open data outlives the model.** If ALEA fails, a licence-clean, provenance-recorded set of national demand, fleet and network data still serves every other modeller. That is the fallback value, and it is real.
- **Data is where the gaps hide.** EPRA publishes Kenya's installed, effective and captive capacity and its peak. Whether the same is available, current and licensable for every country is unknown and has to be surveyed. **[premise]**
- **Provenance is the product.** A table of numbers is cheap. A table in which each figure has a source, a date, a licence, a unit and a confidence grade is what makes a public hosting study defensible.

**Country pack, minimum contents (proposed):** annual demand and hourly or typical-day shape; peak demand; installed and effective capacity by technology; transmission topology at the voltage a campus connects at; weather years for solar, wind and hydro; tariff structure; outage record with its collection method; and a data-quality grade per field. A country enters the model only when its pack passes a schema check and every field names a source. A country with an incomplete pack is listed as such, not filled with a default.

## 5. What this does for AI in Africa, as testable claims

1. **Fewer stalled flagships.** A feasibility screen before an announcement should reduce announce-then-stall cycles. Testable by listing announced African compute projects and checking, ex post, which stalled for power reasons. **[premise]**
2. **Better terms.** Hosts that publish verified headroom should extract firmer supply commitments and clearer cost allocation. Hard to test and slow; treat as a hypothesis, not a promise.
3. **Right-sizing.** Many African countries cannot host gigawatt campuses but can host tens of megawatts of inference and edge capacity at specific nodes. A node-level answer tells them what is feasible, instead of a binary "no" or a mismatched yes. Compare the continent's present scale: reported operational capacity is roughly 360 to over 500 MW in total, depending on source and definition (Fortren via Nairametrics; the sources disagree, README section 3).
4. **Planning for supply as well as load.** If a country knows what hosting 100 MW costs it, it can price the supply it must build first. This links AI demand to grid investment, the real bottleneck the Kenyan president named.
5. **Sovereign data on African grids.** An open, well-labelled power dataset is itself training and evaluation material for models built in Africa for African utilities. **[premise: whether it is useful as such is untested.]**

## 6. Sequencing, and the conflict with "all countries"

The plan in memory and in `docs/plans/14-roadmap.md` holds that Kenya completes before any second country. The intent to cover every country does not conflict with that rule. It sets the order and the reason for it:

1. **Kenya to the gate standard first.** It is the proof that "complete" can be reached and is the template every pack follows. A second country started early inherits the unfixed defects and multiplies them.
2. **Define the country-pack schema and the readiness tiers while Kenya completes.** This costs little and means data collection for other countries can start in parallel as pure data work, with no model claim attached.
3. **Collect packs country by country, ordered by decision pressure** (where announced compute projects are largest relative to the grid), not alphabetically or by data availability.
4. **A country's results are published only when its pack is complete.** Until then it appears in a coverage table as "data only" or "not started".

The risk to name: breadth gets rewarded and depth does not. The completion gates in section 3 are what stop that.

## 7. What would show this argument is wrong

1. **A comparable continental evidence base already exists, open, and is used.** If planners already have this, the marginal value is the model, not the data, and the pitch must change. Test: survey open grid datasets and ask two or more planners per region. Not done.
2. **Power is not what stalls African compute projects.** If a review of announced projects finds finance, chips, connectivity or politics dominant, the thesis names the wrong bottleneck for most countries and fits only some.
3. **Open data does not change negotiations.** If hosts with published feasibility numbers get no better terms, claim 2 fails. This takes years to observe.
4. **Data-licensing and utility secrecy block the packs.** If key national data cannot be released openly, the all-country goal degrades to a few countries plus estimates, and the estimates must be labelled as such.
5. **The model cannot be made trustworthy at the needed resolution.** If a full-year, network-level Kenya solve cannot be validated against operations, the siting claim stays unproven and only the screening claim survives.

## 8. The thesis, in three strengths

- **Strong (defensible once the work is done).** An open, cited, tested model plus open country packs lets any African government, lender or developer check whether a proposed compute load fits a given power system, under stated assumptions, with ranges.
- **Weaker (plausible, needs evidence).** Doing this for every country reduces announce-then-stall cycles and improves host bargaining power.
- **Weakest (a hope, not a claim ALEA should make).** It contributes to African sovereign AI. Say instead: it removes one named obstacle, the absence of shared checkable power evidence, from that path.

## 9. Consequences for the work

- Add a **country-pack schema and readiness tier** deliverable to the plan, ahead of any second country.
- Add the **survey of existing open African grid data** (test 1) before the grant text asserts that none exists. Until it is done, the applications should say "I found no" and not "there is no".
- Add the **announced-projects review** (test 2) as a short research task. It is the cheapest way to learn whether the thesis fits most countries or only a few.
- Keep README section 6 work packages H1 to H3 first. They are the part of this argument a reviewer can run.
- Do not state in any application that ALEA covers, or will cover, all countries as a promise. State the schema, the sequencing rule and the Kenya gates, and name coverage as an aim.

## 10. Sources

Archived in `sources/`: Semafor (Kenya stall), EPRA bi-annual report 2024/25 (Kenya capacity and peak), IEA Energy and AI (per-capita use), Nairametrics citing Fortren (operational and pipeline capacity), arXiv 2603.21795 (compute barriers, Cassava). Claims about the regional power pools, open-data availability by country and announced-project outcomes are not yet sourced and appear above only as premises.
