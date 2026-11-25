# Mozilla Fellowship letter of intent: ALEA

Track II Independent. Answers follow the letter-of-intent form (https://mzl.la/fellowshipsLOI), section by section. The form shows no character limits in its page text; keep each answer short enough to read in a minute. Paste-ready, with a few facts only you can supply marked `[ ]`. Mozilla asks that content reflect your own voice: read each answer once and amend where you would say it differently. Figures measured 2026-11-25.

## The case in one page

**The problem.** Governments and lenders commit very large sums to power plans built on models that outsiders often cannot open. The assumptions are in spreadsheets, units are implicit, sources decay, and a policy dial can be wired to nothing without anyone noticing. Where the model sits with an outside consultancy, the people who live with the plan cannot question it. [ amend with an example you know first-hand ]

**The idea.** ALEA is an open intelligence system for African power, specified as a full lifecycle: plan the system, predict where and when it fails, test what-ifs, and watch for news that changes the picture. Its planning core is a PyPSA-Earth model, its predictive layer detects and forecasts outages from satellite and weather data, its scanning layer reads news and tenders for signals, and a parameter graph holds every assumption with a unit, a range and a source. Every claim nobody has verified is labelled unverified. A planner in Nairobi can change one dial, see what else moves, and see where each number came from.

**Why a Fellowship.** This is "too early, too unexpected, too ambitious for anyone else to fund": energy-modelling money flows to consortia and invited partners, and I found no open call that pays for the unglamorous part, the trust layer. The project is real (1,881 parameters, 841 equations, 1,656 tests) and unfinished in ways I can measure. A year of full-time work closes the gaps and puts the model in the hands of people who can use it.

**Value, stated plainly.**
- To planners: assumptions they can inspect and change, with sources.
- To lenders and civil society: a way to ask "what if this is wrong?" and get a checkable answer.
- To the open-source energy community: a cited, dimension-checked parameter graph and open Kenya datasets, reusable far beyond Kenya.
- To the AI-and-software community: a worked example of how to verify AI-written technical software, with the defects and the checks that caught them.

**Why now, and why this issue area.** Compute for AI is sized in megawatts at a grid node, so power decides where it can go. Microsoft and G42's US$1 billion Kenyan data centre was reported in May 2026 (Semafor) as unlikely to proceed, with the president saying it would need about a third of installed capacity. The regulator's 2024 figures show a 2,288 MW peak against 3,082 MW effective capacity. That arithmetic was not public at the announcement. The use case ALEA is built towards is a public check of whether a grid can host a proposed load, at the evening peak, at what cost to others, with what uncertainty. Countries that can run that check can negotiate compute deals from facts. That removes one obstacle to African compute sovereignty, not all of them: chips, capital, talent and law are separate.

**Not claimed.** The graph is a dependency graph, not a validated causal model. Only 7.4% of settable parameters currently reach the optimiser. There is no full-year Kenya solve yet. It cannot yet test data-centre hosting or forecast demand surges, and its outage-prediction results are unverified: load enters as annual energy on a generic baseline, not Kenya, with no peak or network check. Coverage of other countries is an aim, not a promise.

## Section 1: Applicant information

First name: Nyimbi. Last name: Odero. Preferred name: Nyimbi. Pronouns: [ select ]. Email: [ ]. Current location: [city], Kenya. Permission to work elsewhere: none to list [ amend ].
Current role: Founder, datacraft.co.ke. Organisation: datacraft.co.ke (registered Kenyan company; not the applicant, which is me as an individual). LinkedIn: [ ]. GitHub: https://github.com/nyimbi. Professional website: https://datacraft.co.ke
Builder profile: **Yes, there is a public link**: https://github.com/nyimbi/alea (MIT, 371 commits, 1,656 tests; defect register at `docs/plans/15-completion.md`).
Years of relevant professional experience: [ select band ].
Fellowship availability and legal availability acknowledgements: tick only if true for you.

## Section 2: Track and focus

Track: **Track II: Independent Fellow.**
Primary issue area: **Hard infrastructure: compute, energy, quantum, and the extremes.** (The alternative, "Sovereign AI, public infrastructure and maintenance", also fits: an African-owned, public, maintained planning model.)

## Section 3: Project proposal

**Proposed project title.** ALEA: an auditable open planning model for African power systems

**Project summary.** ALEA is an open, MIT-licensed system for planning power across Africa: it solves a capacity plan, forecasts outages and tests what-ifs, and every assumption carries a unit, a range and a source. The goal is every African country, on one open schema; Kenya is the first country and the proof that the method works. Today it solves Kenya to optimality on windows up to 91 days. Its graph of 1,881 parameters and 841 equations passes a dimension check (841 of 841), but it is a dependency graph, not a validated causal model, the outage predictions are unverified, and only 81 of 1,095 settable parameters (7.4%) reach the optimiser. In the Fellowship year I will close those gaps: refuse inputs the model cannot honour, connect the graph to the solver, complete the first full-year Kenya solve, archive every cited source, settle or withdraw each of the 10 unverified claims, publish open Kenya datasets, define the country-data schema the next countries will follow, and put the model in front of African planners.

**One-liner.** An open system that plans, forecasts and watches African power, with every assumption carrying its unit and its source, and every unverified claim labelled.

**Target users.** Energy-planning analysts in African ministries, regulators and utilities; lenders and civil-society groups who must question a plan; academic modellers; journalists and ministries who want to check an announced project, such as a data centre, against the grid's headroom and reliability. I will recruit two African planners as named testers in the first quarter and record what they cannot see or trust. [ name any who have already agreed; leave none if none have ]

**Traction to date.** Pre-launch, so these are build numbers: 1,881 parameters, 841 equations over 17 systems, 1,993 edges, 57 cross-validation rules, 1,656 tests, 142 of 142 promised quality gates each with a failing canary, 371 commits since 11 October 2026, one contributor, no outside users yet. What I am measuring: share of settable parameters that reach the solver (81 of 1,095 today), citations archived (39 of 108), unverified claims settled (0 of 10), and the first two outside planners to run it.

**Primary project outputs.** Technology platform or tool; dataset; research publication; educational resource.

**Project stage.** Working prototype.

**Impact beyond your wildest imagination.** If it works, the people affected by African power decisions can check them.
- **Planners** stop inheriting models they cannot open. They change one assumption and see what moves and where each number came from.
- **Lenders** ask for the assumptions graph with every plan, as they ask for audited accounts.
- **Governments weighing a data-centre load** see before signing whether the grid can carry it at peak. Kenya lacked that check in May 2024.
- **Journalists and civil society** test announced projects against grid headroom and publish the working.
- **Citizens and small businesses**, who pay for these plans, can question the assumptions in public. Outage forecasts are an aim, not a result.
- **Modellers and students** reuse a cited, unit-checked parameter set.

One open schema across African countries lets neighbouring decisions be compared.

**Disruption.** Closed-model consultancies and vendors, whose value is that nobody can check the assumptions. If any planner, lender or journalist can rerun a plan and see every source, a hidden assumption stops being an asset. So do announcements made without a feasibility check, like Kenya's data-centre deal.

**Quarterly milestones (June 2027 to May 2028).**
- Q1, Jun to Aug 2027: publish a check of what PyPSA-Earth, AETOS and Calliope Africa offer for data-centre hosting; Kenya baseline from EPRA figures; the model refuses hand-set derived values and unknown names; 43 unarchived sources saved; Kenya weather and grid datasets published; two African planners recruited.
- Q2, Sep to Nov 2027: demand-surge forecasting design with a held-out gate; data-centre load with a peak shape, checked against capacity; country-data schema; intervention operator; all 1,095 settable parameters classified; first full-year Kenya solve.
- Q3, Dec 2027 to Feb 2028: each of the 10 unverified claims produced or withdrawn; large-load signal replayed against the May 2024 Olkaria announcement; planner findings and sensitivity report published.
- Q4, Mar to May 2028: verification playbook tested on a second codebase; handover to a maintaining institution; final report with before and after numbers.
Subject to revision with Mozilla.

**Charitable purpose and public benefit.** Yes. The project is open-source public infrastructure for public decisions. Beyond its users, the beneficiaries are electricity consumers and taxpayers whose money and bills follow these plans, and the citizens who can for the first time check the assumptions behind them. It is not a product for Datacraft's customers and I will keep the books separate.

**How I will work in the open.** Open sourcing code and assets (MIT, GitHub); publishing educational materials (playbook, plain-language guide); openly sharing datasets (Zenodo, CC BY, with licences recorded); publishing research papers (findings and the before and after report); public workshops or presentations.

## Section 4: Professional background

I have spent 30 years building national-scale technology in Africa, mostly public-sector systems where failure affects millions.

**Most relevant experience.**
1. **Nigeria's electoral commission, CTO (2010 to 2013).** Rejected hardware-heavy vendor quotes, built a custom Linux and PostgreSQL stack, saved over US$100M in licensing, and registered 73.5 million citizens in 21 days.
2. **Kenya Judiciary, ICT advisor to the Chief Justice (2016 to 2019).** Found the 40-day filing time was a workflow problem; cutting manual handoffs brought it to 7 days. Adoption reached 93% of stations and the systems remain in national use.
3. **Power and compute.** Lead architect on Kebulania, a US$4.5B venture pairing a hyperscale data centre with 1GW of clean energy; earlier, diagnostics for the Power Holding Company of Nigeria.

I am CEO and CTO of datacraft.co.ke, which builds platforms for African telecom, finance and public agencies. ALEA is separate from Datacraft's customers and its books are kept apart.

**Technical expertise.**
- **Management:** led engineering teams of 120+ across Africa, a 12-month group turnaround as managing director, and enterprise product portfolios.
- **Research:** B.Sc. Theoretical Physics, published physics and computing papers, and agent-based policy simulation for government and NGO clients.
- **System design and large systems:** national registers, court systems and a hyperscale data-centre design, built for constraints such as offline capture at 120,000 polling units.
- **Government liaison and negotiation:** advised Kenya's Ministry of ICT and Judiciary, won coalition support for a national rollout, and negotiated against large vendors.
- **Technical skills:** Python (FastAPI), Go, Rust, TypeScript, C and C++; PostgreSQL and PostGIS; Bayesian modelling and machine learning; AWS, Kubernetes, Terraform; ISO 27001 and NIST 800-53. For ALEA: PyPSA, linopy, HiGHS, quality-gate design, and verifying AI-written code.

**Your role in the field at the end of the year.** The person African planners and open-energy modellers turn to for an auditable model of their grid; the author of the first public account of verifying AI-written technical software in a real energy model, defects included; and the maintainer who has handed the model to an institution that will keep it alive. What has changed because of the work: assumptions behind one country's plan can be inspected by anyone, and the method is reusable.

**What's next.** Three doors, any of which I can name a decision-maker for: (1) a public-interest institution in the region (a regulator, a university energy centre or a regional power pool) that adopts and maintains the model, which needs its leadership to say yes; (2) a funder that requires the assumptions graph with every plan it finances, which needs its programme committee; (3) a standard or community project that adopts the parameter-graph format. [ name the institutions you will approach ]

**After the Fellowship.** The code, graph and datasets are open and stay available without revenue. The ALEA specification plans a free open core with paid tiers for institutions (API volume, reports, consulting), run by Datacraft with books kept apart from the Fellowship. That is a plan: no customer has paid and willingness to pay is untested, so door (1) is the fallback.

## Section 5: Mission alignment and motivation

**Three things I hope to get (select up to three).** Funding to focus on my work; Access to Mozilla's network of partners and collaborators; Visibility and platforms to share my work.
Why: I am one person with a company to run, and the work needs a year of full attention. The network matters because the project's value depends on planners and funders trying it. Visibility is how a public tool earns the outside users it does not have yet.

**External support.** None received. Planned or submitted: NLnet open call (EUR 37,500, graph hardening and datasets); Research Software Catalyst Fund (US$45,000, verification template and playbook); EnAccess (introduction sent). If more than one is awarded I will divide scope and not bill a task twice. [ update with any outcome ]

## Section 6: Additional information

How did you hear about the Fellowships program: [ select ]. Social handles: [ ]. Anything else: the project's own defect register is public (`docs/plans/15-completion.md`) and I would rather a reviewer read my failures than discover them.

**AI and translation disclosure.** Were AI tools used to complete this application? **Yes.** How: I used Claude (Anthropic) to draft answers from the repository's measured outputs and from my plan, and to check figures. I reviewed and amended every answer and I am responsible for them. ALEA itself is substantially AI-generated and that is a subject of the project. [ amend if you wrote more of it yourself ]

## Section 7: Acknowledgements

Previous engagement with Mozilla, MozFest or the community: [ yes or no, and how ]. Privacy agreement: your decision.

## What not to say in any follow-up

- That the graph is causal.
- That the model is validated against Kenyan operations.
- That a claim is verified before its artefact exists.
- That ALEA predicts the effects of data centres, fully maps any grid, or covers every African country. Say it tests whether a modelled system can host a load, under stated assumptions, with ranges.
- That the US$100,000 stipend, US$25,000 project budget or any 501(c)(3) condition is confirmed, until you have read the RFP.
