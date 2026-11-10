What we do that PyPSA-Earth does not is a specific and defensible list, because PyPSA-Earth is a **planning engine** — it builds a network from open data and solves a least-cost optimisation — while ALEA (as specified) is a **consistency, prediction, and intelligence layer** wrapped around such an engine.

**PyPSA-Earth does the modelling. ALEA does the checking, the prediction, and the delivery.**

Here is the honest gap, organized by what PyPSA-Earth actually covers and what it explicitly does not.

---

### What PyPSA-Earth Already Does

PyPSA-Earth is a global, sector-coupled, open-source optimisation model. It downloads open data, builds a PyPSA network, and co-optimises investment and operation with high spatial and temporal resolution . It covers electricity, heating, transport, industry, and hydrogen . It handles hydrogen export with four delivery modes . It supports clustering (k-means, GADM, custom shapes) . It can integrate custom user data without programming . It has been demonstrated for Nigeria, Egypt, Brazil, Zambia, and Tunisia .

PyPSA-Earth is the **model**. ALEA is not trying to replace it.

---

### What ALEA Does That PyPSA-Earth Does Not

#### 1. Parameter Consistency Checking (the PRG)

PyPSA-Earth accepts inputs and solves. It does not check whether the inputs contradict each other. If you set `coal_eaf = 0.55` and `forced_outage_rate = 0.60`, PyPSA-Earth will solve with both and return a result. ALEA's PRG refuses the combination, because the two cannot both be true.

**No equivalent exists in PyPSA-Earth.** The model has no consistency layer between the parameter set and the solve.

#### 2. Outage Prediction from Satellite Data

PyPSA-Earth models forced outage rates as **declared inputs** (`forced_outage_rate_coal` is a number you supply). It does not predict outages, detect them from VIIRS, or forecast them from weather. ALEA's Layer 4 (Outage Prediction) uses VIIRS Black Marble detection, OWL-I deconfounding, weather-driven ML, and predictive maintenance — none of which is in PyPSA-Earth.

#### 3. Transmission Loss Decomposition and TLENS

PyPSA-Earth computes transmission losses as part of the LOPF. It does not decompose them by driver, identify critical lines via TLENS, or rank mitigation options. ALEA's Loss Mitigation module does all three.

#### 4. Market Simulation and Capture Prices

PyPSA-Earth produces **shadow prices** (marginal prices from the LOPF dual). It does not simulate an agent-based market, model strategic bidding, or produce capture prices through a market-clearing mechanism. ALEA's Market Simulation layer (AMIRIS, ASSUME) produces endogenous prices from strategic behaviour, which is what COMPASS does for South Africa .

#### 5. What-If Scenario Engine with Propagation

PyPSA-Earth re-runs the whole model for each scenario. It does not have a parameter relationship graph that propagates a single change through dependent parameters before the solve, reports which parameters moved and by how much, or refuses a scenario that is internally inconsistent. ALEA's What-If Engine does all three.

#### 6. Periodic Intelligence Reports

PyPSA-Earth produces model outputs. It does not produce daily outage forecasts, weekly market summaries, or monthly capacity reports on a schedule. ALEA's Reporting layer generates reports at five cadences with distribution via API, email, and dashboard.

#### 7. Automated Intelligence Scanning

PyPSA-Earth does not scan news, tenders, social media, or regulatory announcements for new information. ALEA's Intelligence Scanning module does, with LLM extraction and human review.

#### 8. Multi-Channel Delivery for Non-Modellers

PyPSA-Earth is a Python workflow for modellers. It requires technical expertise to run. ALEA's Delivery layer provides REST API, dashboard, WhatsApp, USSD, SMS, and SDKs for users who will never touch the model.

#### 9. Cross-Layer Audit

PyPSA-Earth does not compare its own solved result against an independent identity checker. ALEA's audit module compares the engine's solved emissions, unserved energy, and fleet capacity against the PRG's identities, reporting gaps rather than assuming agreement.

#### 10. Africa-Specific Continental Scope

PyPSA-Earth is global. It covers Africa as one region among many . ALEA is **Africa-first**: all 55 AU member states, five power pools, AfSEM alignment, CMP integration, and country-specific data completeness assessment. The scope is the same model engine, but the **data layer, the institutional alignment, and the prioritisation** are African.

---

### The One Thing ALEA Does Not Do (Yet)

**ALEA does not have a complete African data layer.** PyPSA-Earth has a global data pipeline. ALEA's PRG has 926 parameters with mostly global defaults. What ALEA lacks — and what PyPSA-Earth also lacks for Africa — is **country-specific values for all 55 AU member states**: 55 coal EAFs, 55 demand profiles, 55 renewable targets, 55 transmission networks.

That is the gap identified in the previous response. It is a **data project**, not a code project. ALEA's consistency checker is ready to consume those values; the values themselves do not yet exist.

---

### Succinct Summary

| Capability | PyPSA-Earth | ALEA |
|---|---|---|
| Least-cost capacity expansion | Yes | No (uses PyPSA-Earth) |
| Sector coupling | Yes | No (uses PyPSA-Earth) |
| Hydrogen export modelling | Yes | No (uses PyPSA-Earth) |
| **Parameter consistency checking** | **No** | **Yes (PRG)** |
| **Outage prediction (VIIRS, ML)** | **No** | **Yes** |
| **Loss decomposition / TLENS** | **No** | **Yes** |
| **Agent-based market simulation** | **No** | **Yes** |
| **What-if propagation** | **No** | **Yes** |
| **Periodic reporting** | **No** | **Yes** |
| **Intelligence scanning** | **No** | **Yes** |
| **Multi-channel delivery** | **No** | **Yes** |
| **Cross-layer audit** | **No** | **Yes** |
| **Continental Africa scope** | Global, not Africa-first | **Yes (55 AU states, 5 pools)** |
| **Country-specific data for Africa** | **No (global defaults)** | **No (also missing)** |

The two are complementary. PyPSA-Earth is the engine. ALEA is the layer that makes the engine's outputs **trustworthy, predictive, and accessible**. Neither replaces the other, and ALEA does not work without PyPSA-Earth (or an equivalent engine) underneath it.