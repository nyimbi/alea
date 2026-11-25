# Is "ALEA maps Africa's power and predicts what data centres do to it" a defensible thesis?

Written 2026-11-25. Short answer: the premise is right, the claim as phrased is too big, and a narrower version is defensible and valuable. This document says which parts hold, which do not, what ALEA does today (measured, not asserted), and what has to be built before the narrower claim is true.

## 1. Verdict

| Part of the thesis | Verdict |
|---|---|
| Power availability decides where and how large AI data centres can be | **Holds.** A live case in ALEA's own first country: see section 3 |
| Without African compute, Africa stays a recipient of AI services | **Plausible, but power is one of several binding constraints**, and not always the tightest (section 4) |
| ALEA "fully maps the current power situation" | **Overreach.** It cannot, and nobody can, from open data. It maps what it can source and labels the rest |
| ALEA "predicts the effects of data centres" | **Not yet, and "predict" is the wrong word.** Today it propagates a load through a dependency graph. It does not test whether the grid can host it |
| ALEA could become an open way to **test whether a power system can host a proposed compute load, at what cost to everyone else, and what must be built first** | **Defensible, valuable, and not yet true.** About six pieces of work stand between today's code and that claim (section 6) |

The value proposition worth keeping is the last row. It is narrower, it is checkable, and it addresses the exact failure that sovereignty arguments keep running into: commitments signed before anyone counted the megawatts.

## 2. The thesis, taken apart

"ALEA seeks to address the challenge by fully mapping the current power situation and predicting the effects of data centres" bundles five claims. Each needs its own evidence.

1. **Power binds siting and sizing of AI data centres.** Empirical, and checked below.
2. **Compute sovereignty is a precondition for avoiding dependence ("a second colonisation").** A political and economic claim. Power is necessary for it, not sufficient (section 4).
3. **A model can map the current system.** Depends on data access. Partial.
4. **A model can predict the effect of a load on that system.** Depends on a network model, a load model and a reliability model. ALEA has pieces of the first and third only (section 5).
5. **Producing that map and prediction helps African institutions.** Depends on who uses it, when, and whether it changes a decision.

Claims 1 and 5 carry the argument. Claim 2 is context, and ALEA should not try to prove it.

## 3. What the evidence says about power as the binding constraint

**Kenya, the case that matters most for ALEA.** In May 2024 Microsoft and the UAE's G42 announced a US$1 billion geothermal-powered data centre campus at Olkaria, to run Azure's new East Africa region. In May 2026 Semafor reported that it is unlikely to proceed. President Ruto said the facility would require about a third of Kenya's total installed capacity of around 3,000 MW and that "to switch on that one data center, we would need to shut off power for half the country". He used it to argue for raising capacity to 10,000 MW by 2030. Semafor adds that the country's technology ministry's concept note never got Treasury approval, and its commentator warns that MoUs signed at summits are "hurriedly announced ... without adequate consideration for their actual feasibility". [Semafor, 6 May 2026; Microsoft, 22 May 2024]

Read it against Kenya's own regulator. EPRA reports 3,192 MW installed and 3,082 MW effective on the interconnected grid at 31 December 2024, of which geothermal is 940 MW installed (876 effective), and a peak demand of 2,288 MW on 29 October 2024. No new grid-connected plant was commissioned in the period. Half-year consumption was 7,222 GWh. [EPRA bi-annual report 2024/25] A 1,000 MW load on a system whose peak is about 2,300 MW and whose effective capacity is about 3,100 MW is not a rounding error. It is the whole reserve margin and more.

**The announcement was made without that arithmetic being public.** That is the gap ALEA can fill. The decision error was not a modelling error; it was that the feasibility screen came after the signing.

**Continent-level context.**
- The IEA's base case has global data centre electricity use roughly doubling to about 945 TWh by 2030. Africa has the lowest per-capita data centre use: under 1 kWh per person in 2024, rising to just under 2 kWh by 2030. South Africa is more than 15 times the continental average in 2030 (above 25 kWh per person). [IEA, Energy and AI]
- Operational African data centre capacity is reported above 500 MW with 890 MW more in development, over 60% of it in South Africa. Estimates differ by source (about 360 MW to over 500 MW) and by definition (IT load against facility power). [Fortren via Nairametrics, July 2026]
- A 2026 paper notes that Africa's barriers to AI are infrastructure and policy: limited high-performance computing, cloud payment mismatches, volatile exchange rates and data-sovereignty laws that fragment regional collaboration, and argues sustainable adoption needs balanced access to compute, data and energy. [Manouan et al., arXiv 2603.21795]

So claim 1 holds, and Kenya shows it at full scale. One caveat on the evidence: the Kenya account rests on a presidential statement relayed by one outlet and the project's non-response, not on a published grid study. That is itself the point.

## 4. Where the thesis overreaches

**Power is necessary, not sufficient.** Even with abundant firm power, a sovereign AI stack needs accelerators (which Africa does not manufacture and mostly buys under foreign export regimes), capital, skilled people, connectivity, a domestic market, and access to models and data. Treating power as the lever risks naming the most legible constraint instead of the tightest. In South Africa, which has the most capacity, the story is not power scarcity alone. ALEA cannot say which constraint binds in a given country, and should not claim to.

**"Sovereign" is not "local".** A data centre inside Kenya, owned by a foreign hyperscaler, running a foreign model, on foreign chips, may be on Kenyan soil and still not be sovereign. Siting a load in-country is a different question from who controls it. A power model can say what the load costs the host. It cannot say who benefits.

**The second-colonisation frame is a political claim, not a modelled one.** It is a reasonable thing for a person to argue. ALEA's credibility with planners depends on not smuggling it into a model's output. The graph is a dependency graph, not a validated causal model, and the project says so everywhere else.

**"Fully mapping" is not achievable.** Three reasons. Open data on African grids is partial: GridWatch coverage, satellite night-light detection and published utility reports all have gaps. ALEA's own outage-detection claims are on the unverified register (VIIRS AUC 0.8346 for Ghana, 89.41% accuracy for Johannesburg, 99% weather accuracy at Adrar), and none is verified. And the system keeps changing. A defensible phrase is "maps what open data supports and labels what it cannot".

**"Predicts" claims too much.** Load growth for AI is genuinely uncertain, and the Kenya project itself went from announced to stalled in two years. A model that tests scenarios and reports sensitivity is useful. A model that says "will" is not defensible.

## 5. What ALEA does today, measured

I ran the graph on 2026-11-25 with the data-centre IT load set to three values and read what moved (`uv run alea prg propagate --set data_centre_it_load_mw=...`). The default is 15 MW of IT load and a power usage effectiveness (PUE) of 1.89, taken from the LBNL data centre report (Shehabi et al., 2016) in batch 72.

| IT load | Facility draw (IT x PUE) | Annual energy | Demand (graph default 46.79 TWh) | Fleet generation headroom | Emissions | Regulated tariff |
|---|---|---|---|---|---|---|
| 15 MW (default) | 28 MW | 0.25 TWh | 47.04 TWh | 1.31 | 15.4 MtCO2 | 93.71 USD/MWh |
| 100 MW | 189 MW | 1.66 TWh | 48.19 TWh | not read | not read | 92.79 USD/MWh |
| 1,000 MW | 1,890 MW | 16.56 TWh | 63.10 TWh | **0.95** | 21.3 MtCO2 | 85.73 USD/MWh |

Reading it, in order of what it supports and what it does not.

**What is real.** The graph accepts a data centre as a load, converts it by an unit-checked chain (MW, PUE, hours per year, TWh), adds it to demand, and moves downstream quantities: emissions, cooling water (+36 million m3 at 1,000 MW), tariffs, cover costs. Fleet generation headroom, which the graph defines as fleet output capability divided by dispatched generation, falls from 1.31 to 0.95 at 1,000 MW. A value under 1 is the right qualitative warning and agrees in direction with what Kenya's president said.

**What is wrong or missing, and each is a finding.**

1. **The baseline is not Kenya.** The graph's default demand is 46.8 TWh (base 33.8 TWh). EPRA's half-year figure of 7.2 TWh annualises to about 14.4 TWh. So the quantities above describe a generic default system, not Kenya. The numbers cannot be quoted as Kenyan effects.
2. **Energy, not capacity.** The load enters as TWh. What broke the Kenya project was megawatts at the evening peak. A 1,890 MW draw against a 2,288 MW national peak is invisible in a TWh-based chain. The load needs a shape (data centres run at a high, flat load factor, so their coincidence with the peak is close to 1) and the check has to be a capacity check.
3. **Reliability does not respond.** Expected unserved energy is defined as demand times a constant `expected_unserved_fraction` (default 0.001) times 1,000, so it rises in proportion to demand and does not depend on headroom. Headroom falling below 1.0 changes no reliability figure. A hosting study needs loss-of-load results that worsen when reserve shrinks.
4. **The tariff falls.** The regulated tariff drops by about US$8 per MWh at 1,000 MW. I did not trace the equation chain, but the likely cause is fixed costs spread over more energy with no new capacity built. In reality a load that large forces new build, and who pays for it is the central policy question. The falling tariff is probably a modelling artefact and would mislead anyone who read it as a benefit.
5. **No location.** The graph has no network. Siting needs buses, lines, thermal limits and candidate nodes. The planning engine is built on PyPSA, which supports a network, but no hosting-capacity analysis exists in ALEA.
6. **No supply response.** The graph cannot say "the data centre brings its own solar and storage" or "it takes a geothermal block that would otherwise serve households". The additionality question, whether the load is met by new supply or by diverting existing supply, is the sovereign-AI question in power terms.

**What the measurements support.** ALEA today is a usable scaffold for the question, with a correct unit chain for load and a sensible headroom signal. It does not yet answer it. Anyone who describes it as "predicting the effects of data centres" would be describing the plan, not the code.

## 6. What it would take

Each row is a work package with a gate that prints a number, in the style of `docs/plans/15-completion.md`. The numbered plan tasks T1 to T5 (refuse bad input, intervention, consistent defaults, solver coupling) come first, because a hosting test built on a graph that silently discards inputs measures nothing.

| Work | What it adds | Gate |
|---|---|---|
| H1 Kenya baseline | Demand, capacity and peak from EPRA (14 TWh scale, 3,192 MW installed, 2,288 MW peak) as the default scenario, with the sources archived | Default demand within 5% of EPRA annualised; every figure cited |
| H2 Load shape | An AI-load profile with a stated load factor and a peak coincidence factor, as parameters with sources | A 1,000 MW load raises the evening peak by its coincident draw, tested |
| H3 Capacity adequacy | A reserve-margin check against effective, not installed, capacity; loss-of-load from reserve | Headroom below 1 raises expected unserved energy, in a test that fails if the link is cut |
| H4 Network and siting | Candidate buses, line limits and a hosting-capacity result per node, on the Kenya network | A node's reported hosting capacity is reproduced by a hand calculation on a three-bus case |
| H5 Supply response and cost allocation | On-site generation and storage options, and a finding on who bears the capacity cost | The tariff falls only if new capacity is not built, and the report states which |
| H6 Uncertainty | Load growth as a distribution, with results as ranges | Every headline figure carries an interval and the inputs that dominate it |

Two caveats on effort. H4 depends on the Kenya network data and on the full-year solve (M1 in the roadmap), which is not yet finished: the model solves to optimality on windows up to 91 days. And H1 to H3 do not need the network, so they can be built and shipped first.

## 7. A thesis ALEA can defend

> ALEA is an open, cited, unit-checked model of power-system assumptions. For a proposed compute load it answers four questions in public, before commitments are signed: Can the system host it at the evening peak? What does it do to reliability and to everyone else's tariff? What must be built first, and who pays? How sure are we?

Why this version is stronger.

- It is **checkable**. Each question maps to a gate in section 6.
- It does not claim sovereignty. It claims that a host country can see the power arithmetic of a proposal and negotiate with it. That is a necessary part of sovereignty, and the Kenya case shows what happens without it.
- It is **useful whichever way a decision goes**: a country that learns it can host 100 MW at a named node, or that a 1 GW MoU needs 1.9 GW of new build, has learned something it can act on.
- It names its **users**: a technology ministry drafting a concept note, a treasury judging it, a regulator setting a connection charge, a utility planning supply, and a journalist or lender asking what the number rests on.

## 8. What would show the thesis is wrong

1. If the Kenya hosting test (H1 to H4) says a 100 MW or 1 GW load is easily hosted and the real project still stalled for other reasons, power was not the binding constraint, and ALEA addresses a minor one.
2. If planners already have this analysis privately and simply do not publish it, the value of an open version is lower than argued here. The test is to ask two Kenyan planners what they have. The Mozilla and NLnet drafts already plan for that conversation.
3. If a result depends mostly on an input that no source can pin down (the load factor, the coincidence factor, the supply response), the model reports a range too wide to inform a decision. Then the honest output is "we cannot tell", and that has value, but a smaller one.
4. If the 10 unverified claims fail on verification, the mapping side (outage detection) cannot be presented as a map.

## 9. Consequences for the three applications

- Add the narrower thesis, as a stated use case, to the Mozilla letter of intent (issue area "Hard infrastructure: compute, energy, quantum, and the extremes" fits it directly) and to the NLnet and Catalyst Fund concept notes. Use the Kenya stall as the example, cited to Semafor and EPRA.
- Do not write "fully maps" or "predicts". Write "tests whether a system can host a load" and "reports a range".
- Include H1 to H3 in the data and development work packages. They are small, they need no network, and they turn the use case from a story into a deliverable. H4 to H6 belong to the Mozilla year.
- Disclose the baseline defect of section 5 (a generic default, not Kenya) in each application's "what is wrong" list. It is true, it is measurable, and a reviewer who runs the graph will see it.

## 10. Sources (archived in `sources/`)

| File | What it supports |
|---|---|
| `semafor-kenya-microsoft-datacentre-2026-05.html` (+ `.txt`) | Ruto's capacity statement, the stall, Treasury non-approval, the MoU feasibility caution. News reporting, not a grid study |
| `microsoft-g42-kenya-announcement-2024-05.html` (+ `.txt`) | The original announcement: geothermal-run campus at Olkaria, Azure East Africa region |
| `tomshardware-microsoft-kenya-stalls.html` (+ `.txt`) | Secondary coverage of the same event. The text is mostly page furniture; rely on Semafor |
| `epra-bi-annual-2024-25.pdf` (+ `epra.txt`) | Kenya installed 3,192 MW, effective 3,082 MW, geothermal 940 MW, peak 2,288.35 MW, half-year consumption 7,222.37 GWh |
| `iea-energy-and-ai-demand.html` (+ `.txt`) | Global 945 TWh in 2030; Africa under 1 kWh per capita in 2024 and just under 2 by 2030; South Africa above 25 |
| `nairametrics-africa-dc-capacity-2026-07.html` (+ `.txt`) | Fortren: over 500 MW operational, 890 MW pipeline, South Africa over 60% |
| `arxiv-africa-ai-compute-tracker-2603.21795.pdf` | Barriers to compute, data and energy access in Africa |
| `datacenterdynamics-microsoft-g42-kenya.html` | 403 error page. Not evidence |

Not archived because the page was unreadable to the fetcher: the McKinsey report on African data centres (its figures reached me only through a search summary and are not used here), and the Bloomberg and Gulf News announcement coverage. The "100 MW rising to 1 GW" figure in some coverage is not used because I could not read it in a primary source.

The graph measurements in section 5 are the printed output of `uv run alea prg propagate` on the committed `config/prg.yaml` on 2026-11-25.
