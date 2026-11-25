# Global funding search for ALEA, 2026-11-25

Question: which grants and funders can ALEA (open-source energy planning model, parameter graph, Kenya first) apply to. Builds on `../alea-funding/` (EnAccess, Terra Viva scans). Method: web search (standard mode, eight queries), then raw copies of primary pages in `sources/` (see `sources/INDEX.md`). A figure resting only on a search snippet is marked **snippet**. Re-check every date on the funder's live page before acting.

## Result

No open call today is a clean fit. Everything realistic needs an institutional partner: a consortium (LEAP-SE, Horizon Europe), a UK lead (Energy Catalyst), or a funder that acts by approach, not by call (EnAccess, Sloan, Schmidt). Open calls that accept a solo applicant (NLnet, Sovereign Tech Fund) do not match ALEA's scope.

## Candidates

| Funder / call | Amount | Status 2026-11-25 | Fit | Evidence |
|---|---|---|---|---|
| NLnet open call | EUR 5k to 50k first grant | Open, deadline 3 Jan 2027 12:00 CET | Poor. Themes are internet stack and digital commons. EU-supported funds want a European dimension. Generative-AI policy: proposals must be made by humans | archived, `nlnet-*.html` |
| Sovereign Tech Fund (Germany) | Contracts above EUR 50k | Platform open, rolling | Poor. Funds "open digital base technologies" (libraries, tooling), "does not finance prototypes", rejects work another public body already funds. A separable library (the PRG DSL and propagation kernel) is the only angle, and a stretch | archived, `stf-*.html` |
| LEAP-SE, EU-Africa joint call | consortium grants | 2026 round closed 5 Feb 2026 (pre-proposals) | Strong in scope (sustainable energy, Kenya eligible). Needs a consortium. Watch for the 2027 round | **snippet**; earlier copy in `../alea-funding/sources/leap-se-2026.html` |
| Horizon Europe "Energy system modelling, optimisation and planning tools" | EUR 6M pot, open licence required | Listed as open on an aggregator; deadline **unconfirmed**; one search could not find the topic under CL5-2026 | Possible via an EU lead with a Kenyan partner. Verify on the Funding & Tenders portal first | **snippet** (aggregator 403 on fetch) |
| Horizon CL5-2027-02-D3-24, AI for digital energy system | not stated | deadline 31 Mar 2027 per one source; reference number differs between sources | Weak, EU grid focus | **snippet** |
| Innovate UK Energy Catalyst | GBP 50k to 5M by stage | Round 11 closed 25 Mar 2026 | Needs a UK-registered lead. Watch for Round 12 | **snippet** |
| EnAccess Foundation | up to US$250k pilot, US$50k moonshot | Rolling per listing; FAQ says no project grants | Best lead. Email first | `../alea-funding/` |
| Keeling Curve Prize | US$50k shared | 15 Jan 2027 | Long shot, small | `../alea-funding/` |
| Climate Change AI Innovation Grants | up to US$150k | No future call planned (their own page) | Closed | archived, `ccai-innovation-grants.html` |
| Schmidt Sciences climate-to-action | up to US$2M phase I | Closed 11 Sep 2026. Awardees are university PI teams (Princeton, NYU, MIT) | Not open to a solo project | archived, `schmidt-*.html` |
| Google.org via LF Energy | US$2.5M, two years | Announced Nov 2026 | Not an open call. Four European grid projects. LF Energy hosting is a possible route | archived, `lfenergy-google-org.html` |
| Sloan Foundation | grant-by-grant | Open Energy Outlook (Carnegie Mellon, 2023); a 2026 Stanford workshop grant | Approach by invitation, US-centred | archived, `sloan-g-2026-79537.html` |
| ESMAP, AESTAP, Mission 300 | n/a | No open call found | Reach via partners, not application | **snippet** |
| UNDP integrated-modelling call | US$100k | Closed 5 Dec 2025 | Closed | **snippet** |

## Decisions and rejected options

- Prioritise (1) the EnAccess email, (2) a partner conversation. The partner list comes from the search: Climate Compatible Growth (runs EMP-A), Fraunhofer IEE (OASES), OpenMod4Africa partners (Strathmore, Makerere, Addis Ababa), SEI (ONEPlanET). Each already holds EU or UK money for this topic; none is a funder.
- Rejected for now: NLnet and Sovereign Tech Fund, on scope. Revisit STF only if the PRG kernel is extracted as a standalone, documented library.
- Rejected as closed: CCAI, Schmidt, Energy Catalyst R11, UNDP.

## Second sweep (same day): philanthropy, bilateral, Kenya, open-source funds

Ten more searches plus primary pages. Result: still no open call for ALEA. Two things to watch.

| Funder / call | Amount | Status | Fit | Evidence |
|---|---|---|---|---|
| AFD Digital Energy Challenge | EUR 150k (Tech Accelerator), EUR 400k (Partnership) | 2026 round closed 17 Jun 2026. Themes included "optimizing planning and investments". Open to SMEs, startups and software developers | **Best watch item.** Closest thematic match found. Likely recurs yearly (my inference, not stated). Needs a registered company | archived, `afd-digital-energy-challenge-2026.html` |
| AECF REACT 2.0 DIFEC (Sida) | SEK 50M programme, 2026 to 2028 | Both windows closed 17 Apr 2026. Gives priority to open-source and digital-public-goods alignment | Watch for later windows. Enterprises only | **snippet** (programme page 404 on fetch) |
| CCG-TWAS Catalyst Research Group Grants | research assistants, MSc scholarships, hardware | "Proposed, subject to funding secured" (Oct 2025). No call found | Universities in developing countries only. A route if a Kenyan university hosts ALEA | archived, `ccg-twas-catalyst.html` |
| UK PACT Kenya | clean energy round had an integrated-planning theme | Last energy round closed 29 Jan 2025. 2025 call was nature-based. No 2026 energy round found | Needs a partner. Strathmore and Practical Action already hold the planning awards | **snippet** |
| Open Source for Science Fund (Renaissance Philanthropy, Biohub, Wellcome) | up to US$250k or US$1M | First call life sciences only; applications closed 21 Jul 2026 per a listing | Wrong domain. Check whether a later call opens energy | archived, `os4science-renaissance.html` |
| EEP Africa 2026 | n/a | EOI deadline 16 Mar 2026, closed | Project finance, not software | **snippet** |
| Eni Award 2027 | EUR 200k Energy Transition prize | Main deadline 20 Nov 2026, closed. "Eni for Innovation" recognitions 31 Jan 2027 | Prize for researchers and ventures. Unclear fit | **snippet** |
| Gates, Open Philanthropy, Bloomberg, Breakthrough, ClimateWorks, IKEA, Rockefeller | n/a | No relevant open call or committed grant found. Gates committed-grants listings surfaced a 2024 Global Energy Alliance grant only | None. Approach funders, no open route | **snippet** |
| Mitigation Action Facility 2026, GCF readiness, GEF, UNDP, AfDB | n/a | No call for energy planning tools found | Government-facing. No fit | **snippet** |
| Sovereign Tech, SSI Research Software Maintenance Fund, NSF PESOSE, Digital Research Alliance of Canada | various | UK, US and Canada institutions only, or closed | No | **snippet** |
| Terra Viva category pages 4 and 5 | n/a | All deadlines passed (latest 31 Dec 2026, a conference award). Pages are ordered by post date, so pages 6 to 81 are older | None | archived, `terraviva-category-energy-climate-p4.html`, `p5.html` |

## Third sweep (later the same day): what is open now

Brief was "at least 10 open grants". I did not find 10 that are open, eligible and in scope. I found 12 that are open on paper; three are worth an application, and the rest fail on eligibility or scope. Method: eight more searches, a subagent read of two aggregators, then primary pages archived in `sources/third-sweep/`. Dates marked **primary** were read on the funder's own page; **snippet** rested on an aggregator or search result.

### Worth applying to

| # | Funder / call | Amount | Deadline | Fit and conditions | Evidence |
|---|---|---|---|---|---|
| 1 | NLnet open call | EUR 5k to 50k, then follow-on | 3 Jan 2027, 12:00 CET | General fund has no European-dimension rule (only the EU-funded themes do). Open licence required, proposal must be written by a human. Theme fit is the risk: frame as open geospatial and energy data infrastructure, not "a planning model" | **primary** |
| 2 | Research Software Catalyst Fund, exploratory grants | up to US$50k, 3 to 6 months | 31 Dec 2026 | Worldwide, individuals and informal teams. **Excludes LLCs and companies**, so Datacraft cannot be the applicant; apply as an individual or team. Scope is trustworthy AI-assisted research software, so frame the PRG (cited, dimension-checked, gate-tested) as a verification layer for model-written code. OSI licence required (MIT qualifies) | **primary** |
| 3 | Mozilla Foundation Fellowship 2027, Independent track | up to US$125k over 12 months | letter of intent 17 Dec 2026 | Individual only. Focus areas listed include energy. Funds must pass through a US 501(c)(3) sponsor, which may be a barrier | **snippet**; page 403 to curl, read by a subagent |

### Open but a weak or conditional fit

| # | Funder / call | Deadline | Why it is weak |
|---|---|---|---|
| 4 | FLOSS/fund (Zerodha), up to US$100k | rolling, quarterly review | Wants widely used projects; ALEA has no users yet. Revisit after release. **primary** |
| 5 | Sovereign Tech Fund | rolling | EUR 50k minimum, no prototypes, rejects publicly funded work. Only a separable PRG library fits. **primary** |
| 6 | GitHub Secure Open Source Fund, US$10k plus credits | rolling | Security-focused. ALEA is not a security project. **primary** |
| 7 | RICH Hub Climate AI Innovation (AI4D), scaling grants to US$200k | rolling EOI | Needs a pilot-stage AI or data innovation; ALEA has no deployed pilot. **snippet** |
| 8 | Keeling Curve Prize, US$50k each to 10 projects | 15 Jan 2027 | Rewards operating climate projects with measured impact. ALEA has none yet. **snippet** |
| 9 | IEEE and UNDP GenAI for Good, Cities Edition, up to US$30k | 13 Dec 2026 | Teams of two or more people only, companies cannot enter, named city use cases, Apache 2.0 code. **primary** |
| 10 | Tony Elumelu Foundation 2027, US$5k | not open; one aggregator says 31 Mar 2027, previous cycle opened 1 Jan | Seed capital for African early-stage businesses; would suit Datacraft, not ALEA. **snippet** |
| 11 | AWS and Google Cloud research credits | rolling | Aimed at accredited institutions; a Kenyan company does not obviously qualify. **snippet** |
| 12 | Breakthrough Energy Fellows Explorer track, US$50k to 250k | rolling per FAQ | Hard-tech decarbonisation startups; a planning model is not what it funds. Innovator concept papers closed 2 Nov 2026. **primary** |

### Checked and rejected as closed or out of scope

Climate Intervention Environmental Impact Fund (1 Dec 2026; the page states clean energy is out of scope), Horizon Europe CL5-2026-11 energy AI (1 Dec 2026, EUR 10M consortia), NOSTRADAMUS (EU SMEs), MIT Solve 2027 (closed 2 Nov 2026), Google for Startups AI First Africa (closed March 2026), TotalEnergies Startupper and AWS Compute for Climate (closed), Africa Prize 2027 (closed 8 Sep 2026), Sovereign Tech Fellowship (closed 6 Apr 2026), NumFOCUS small grants (closed), DOE Genesis Mission (US only), Kenya NRF (no energy or software call), Mission 300 and AESTAP (routed through national delivery units, no public call).

### Reading

- Three applications are realistic before the new year, and two of them (NLnet, Research Software Catalyst) need framing that the project can honestly support. Neither funds "an energy planning model" as such. NLnet funds open infrastructure; the Catalyst Fund funds trustworthy AI-assisted research software. Do not stretch a claim to fit: ALEA's graph is a cited dependency graph and 7.4% of its settable parameters reach the solver (see `docs/plans/15-completion.md`), and a reviewer can check.
- Two of the three exclude Datacraft as applicant. Decide who applies as a person or team before drafting.
- The count of grants for which ALEA fits cleanly is zero. The pattern across three sweeps is that energy-modelling money flows through consortia and invited partners, not open calls. The 10-grant target is better met by the partner route listed under "Decisions" than by more searching.

## Still not covered

GIZ, Norad and Sida's own portals (only reached through aggregators), the World Bank direct trust funds, Kenyan ministries, and Terra Viva pages 6 to 81 (older by post date). Each of those was a single aggregator hit or unread. Treat "nothing found" for them as "not checked well".

## Next actions

00. Decide the applicant (person or team, not Datacraft) and draft NLnet (3 Jan 2027) and the Research Software Catalyst Fund (31 Dec 2026) first; Mozilla letter of intent is due 17 Dec 2026.
0. Calendar the AFD Digital Energy Challenge: look for the 2027 call around April to June. It needs a registered company, so decide which entity would apply.
1. Fill the placeholders in `../alea-funding/enaccess-email.md` and send it.
2. Open the Horizon Funding & Tenders portal and search the exact topic title to confirm status and deadline.
3. Ask one of the partner organisations whether it plans a LEAP-SE or Horizon bid that needs an open planning model.
4. Run the funder-by-funder follow-up in "Not searched".
