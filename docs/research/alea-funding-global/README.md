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

## Still not covered

GIZ, Norad and Sida's own portals (only reached through aggregators), the World Bank direct trust funds, Kenyan ministries, and Terra Viva pages 6 to 81 (older by post date). Each of those was a single aggregator hit or unread. Treat "nothing found" for them as "not checked well".

## Next actions

0. Calendar the AFD Digital Energy Challenge: look for the 2027 call around April to June. It needs a registered company, so decide which entity would apply.
1. Fill the placeholders in `../alea-funding/enaccess-email.md` and send it.
2. Open the Horizon Funding & Tenders portal and search the exact topic title to confirm status and deadline.
3. Ask one of the partner organisations whether it plans a LEAP-SE or Horizon bid that needs an open planning model.
4. Run the funder-by-funder follow-up in "Not searched".
