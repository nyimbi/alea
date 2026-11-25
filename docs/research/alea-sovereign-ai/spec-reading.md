# What the spec says ALEA is for, and what that does to the sovereign-AI thesis

Written 2026-11-25 after reading `docs/spec/` (spec, spec1 to spec4, analytics, best1, users, competition-eval, the data inventories and the interface spec), with the code and plan checked where a claim about status is made. It corrects an imbalance in `README.md` and `continental-argument.md` in this directory, and in the three grant applications: they were written around the parameter graph (PRG). The spec does not describe a parameter graph.

## 1. Where the spec is going

A repository search finds no mention of a parameter relationship graph in `docs/spec/`. The graph is a later addition, born in the plans. The spec defines something else: a **full-lifecycle decision-support system for African energy**, "from long-term planning through operational forecasting to periodic reporting" (`spec4-base.md`, Part I). Its layers:

| Layer | What it does | Spec home |
|---|---|---|
| 1 Planning core | Capacity expansion on PyPSA-Earth, multi-horizon, all renewables | spec4-base Part IV |
| 2 Sector coupling | Hydrogen, heat, transport, industry, water | Part V |
| 3 Market simulation | Agent-based bidding, capture prices, PPA curves, VaR and CVaR | Part VI |
| 4 Predictive operations | VIIRS outage detection, weather-driven outage forecasting, predictive maintenance, loss decomposition, TLENS, ENS, EENS, SAIDI, SAIFI | Part VII, `analytics.md` |
| 5 What-if engine | Interactive parameters, rapid re-solve, efficient frontiers | Part VIII |
| 6 Reporting | Daily to annual intelligence briefings and alerts | Part IX |
| 7 Intelligence scanning | Continuous news, tender and utility-site scanning, extraction, human review, model update | `spec4-data-collection.md` |
| 8 Delivery | REST API, dashboard, WhatsApp and USSD channels | spec4-ext, base4-intf |

Three ideas run through it.

- **A Bloomberg for African energy.** `spec4-ext.md` states the analogy directly: open data as a commons, predictions as a service, many delivery channels, a commercial layer for sustainability, and a public-good mandate. Users range from a household in Malawi to a sovereign wealth fund.
- **The model replaces a closed product.** `spec.md` sets out to surpass Meridian's COMPASS, which forecasts South African prices, across 55 member states, openly.
- **Operations and planning share one platform.** An outage forecast for next week and a capacity plan for 2060 come from the same data and the same system.

## 2. Reading "understand and predict outages, demand surges, etc."

| Capability | In the spec | In the code today | Verified? |
|---|---|---|---|
| Outage detection from satellite | Yes: VIIRS radiance, 0.01 degree patches, random forest, GridWatch labels | Modules exist (`outages/viirs*.py`, `gridwatch.py`) | No. Claims #1 and #2 are on the unverified register |
| Weather-driven outage forecast | Yes: three models per country, probabilistic | `outages/weather.py` | No. Claim #3 |
| Predictive maintenance | Yes: survival models and ML on transformers | `outages/maintenance.py` | No. Claim #4 |
| Loss mitigation, resilience metrics | Yes: loss decomposition, TLENS, ENS, EENS, SAIDI, SAIFI | `losses/`, `resilience/` | Partly; claim #6 unverified |
| Scanning for news, tenders, outages | Yes | `scanning/` with ten signal types | Built; precision measured per type is the project's own gate |
| **Demand surges** | **Almost absent.** One API line (`/demand/{iso}/forecast`, hourly to 7 days) and one scanning signal type, `demand_signal`, defined as "new industrial load or electrification programme" | `DEMAND_SIGNAL` is extracted and scored at 0.60 impact (investment and policy signals score 0.85 to 0.90); no demand forecaster exists, and `market/service.py` says so in its own docstring ("no demand forecast, no price forecast") | **A gap in the spec and the code** |

The validation targets in the spec (AUC above 0.80, accuracy above 95 percent, 87 percent failure detection) are **benchmarks from the published studies, not results from ALEA.** Treat them as aims. The spec's validation table is not evidence that the modules meet them.

So the user's description is right and the applications under-describe it. "Predict outages" is Layer 4, a large and central part. "Demand surges" is the layer the spec names least, and the most relevant one to AI data centres, because a data centre is the clearest demand surge there is.

## 3. What this does to the sovereign-AI thesis

The earlier documents argued from the graph: put a load in, see what moves. The spec supports a stronger and different argument.

**A data centre is a joint planning, operations and reliability problem, and the spec has a layer for each.**

1. **Planning (Layers 1 to 3).** Can the system supply it in the long run, at what cost to others? This is what the README of this directory scoped as H1 to H6.
2. **Operations and reliability (Layer 4).** A data centre needs very high availability. The grid's outage record at a candidate node decides how much backup, usually diesel or batteries, the operator must build, and so its real cost and emissions. Outage prediction and SAIDI/SAIFI by node answer a question the PRG cannot: how reliable is the supply at this site? That belongs in any siting decision and has no counterpart in the earlier drafts.
3. **Signals (Layer 7).** The scanning layer is built to detect announcements. The Kenya project was an announcement. A `demand_signal` (or a new type, `large_load_announcement`) extracted from news, tenders and gazettes, checked against modelled headroom, is how the platform could flag "this announced load exceeds the node's capacity" within days of the announcement. That is the Kenya failure, caught early, by a layer the spec already describes.
4. **Reporting and delivery (Layers 6 and 8).** A public weekly or monthly briefing on announced loads against headroom is the product a ministry, lender or journalist could use.

**The thesis, restated.**

> ALEA is an open, continuously updated intelligence system for African power: it maps what open data supports, predicts outages, tests plans and loads against the grid, and watches announcements. For compute sovereignty, it lets a host see three things before and after a data-centre deal: whether the supply is there (planning), whether it will be reliable at the site (outage prediction), and whether an announced load is credible against headroom (scanning).

What it adds: the siting question becomes **reliability-adjusted**: not "is there power" but "is there dependable power here, and what does the backup cost". It also becomes **dynamic**, because the scanning layer watches announcements as they arrive, where a static study ages.

## 4. Where the spec and the claims diverge

- **The sovereign-AI use case is not in the spec.** `spec4-ext.md` lists telecom operators (tower power, data centre energy) as one of 19 user groups, rated medium. Data centres as a driver are the user's own extension. That is fine, but the spec cannot be cited as support for it.
- **"Demand surges" needs building.** There is no demand forecaster to point at. The nearest asset is the `DEMAND_SIGNAL` pipeline, which is rated below investment and policy signals (0.60 against 0.85 to 0.90). Before the applications say ALEA predicts demand surges, a design and a gate are needed.
- **The spec's scope is far wider than the plan funds.** The roadmap's single-country-first rule and the current defect register cover a small part of the spec. The grant applications fund the repair of the PRG and its coupling. They say little about outage prediction, scanning or demand, which the spec treats as central. A reviewer who reads the spec and then the applications will see a gap.
- **"Fully mapping" is closer to the spec than I credited.** The spec does aim at a map of the grid (data pipeline, completeness grades, scanning). My earlier verdict that it overreaches stands for "fully", because the completeness tables give HIGH for 6 of 55 countries and the unverified claims remain. But "mapping" is a stated goal, not a stretch.
- **The competitive survey grades the plan, not the code.** `competition-eval.md` rates ALEA "Strong" to "Pioneering" against PyPSA-Earth, AETOS and Calliope Africa on what the spec promises. It cannot be quoted as a measure of what exists.

## 5. What this means for the applications

I have not changed them. The question for the user is which story to tell each funder, because the applications currently describe only the graph.

| Funder | Story the spec supports | Why |
|---|---|---|
| NLnet (EUR 37,500) | The graph and its trust layer, as now, plus one line that it sits inside an operations-and-planning platform | NLnet funds a bounded, checkable commons deliverable. The graph hardening is that |
| Research Software Catalyst Fund | The verification method, as now | The fund is about research software practice, not the whole product |
| Mozilla Fellowship (a year) | The full platform story: planning, outage prediction, scanning, with the Kenya hosting case as the lead use case | A fellowship funds a person's year and a vision. The "hard infrastructure: compute, energy" area fits the whole spec, not one layer |

Add to the plan, ahead of any claim:

1. A **demand-surge design**: what is predicted (announced large loads, electrification, seasonal peaks), from what data, and a gate with a held-out check.
2. A **large-load signal type** in scanning and a check against node headroom, with the Kenya announcement as the replay test: would the pipeline have flagged it in May 2024?
3. **Site reliability** as an output of the outage layer (SAIDI or an outage-hours estimate per node), with its validation status stated plainly. The 10 unverified claims gate this.

## 6. What would show this reading is wrong

1. If outage data cannot be validated beyond Ghana and Johannesburg, the reliability-adjusted siting claim does not generalise, and the thesis falls back to planning plus scanning.
2. If the scanning layer's precision on large-load announcements is low, the early-warning claim fails. The gate is the project's own measured precision per signal type.
3. If a large load's site matters less to the host than its financing, the reliability angle is real but not decisive.
4. If funders judge the platform vision too broad for the evidence, the applications should return to the narrow graph story. Section 5 leaves that choice with the user.

## 7. Sources

All from the repository at HEAD on 2026-11-25: `docs/spec/spec4-base.md` (Parts I, VII, XII, XIII), `docs/spec/analytics.md`, `docs/spec/spec4-ext.md`, `docs/spec/spec4-data-collection.md`, `docs/spec/users.md`, `docs/spec/competition-eval.md`, `src/alea/signals/models.py`, `src/alea/scanning/score.py`, `src/alea/scanning/integrate.py`, `docs/plans/14-roadmap.md`. The search results that the demand forecaster and the PRG are absent from the spec and `src/alea` come from pattern searches on 2026-11-25 and should be re-run before they are quoted.
