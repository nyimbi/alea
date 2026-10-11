# PyPSA-X Pan-African: The Energy Intelligence Platform for Africa

## Extension Specification: From Modelling Tool to Continental Public Utility

**Version**: 4.0 (Extension to v3.0 Product Specification)
**Status**: Strategic Vision & Implementation Blueprint
**Audience**: Product strategists, senior developers, partnership leads
**Base Platform**: PyPSA-X Pan-African v3.0

---

## Part I: The Vision — From Model to Public Utility

### 1. The Core Insight

PyPSA-X Pan-African v1.0–v3.0 defined a **modelling platform** for analysts, planners, and investors. But the platform's data, predictions, and analyses have value far beyond these original users. The same outage predictions that help a utility plan maintenance can help a **hospital** decide whether to invest in backup power. The same price forecasts that help an **investor** structure a PPA can help a **small business** decide whether to install solar. The same climate scenarios that help a **government** plan transmission can help a **farmer** understand irrigation risks.

The platform should therefore become an **Energy Intelligence Platform for Africa** — a public utility for energy information that serves **everyone** from rural communities to global investors. This is not a commercial pivot; it is a **public good mandate** with a sustainable commercial layer.

### 2. The Strategic Analogy

Think of what Bloomberg Terminal did for financial markets: it consolidated fragmented data, added analytics, and delivered it through a single interface that became indispensable. But Bloomberg is expensive, closed, and serves only finance professionals. What if there were a **Bloomberg for African Energy** that was **open, accessible, and served everyone** — from a journalist in Lagos to a mini-grid developer in Tanzania to a sovereign wealth fund in Abu Dhabi?

That is the vision. PyPSA-X Pan-African becomes the **reference platform for African energy intelligence**, with:

- **Open data** as a commons
- **Predictions and analyses** as a service
- **Multiple delivery channels** to meet users where they are
- **Community engagement** to ground-truth and enrich the data
- **Commercial layers** to sustain the platform

---

## Part II: Expanded User Taxonomy

### 3. Twenty User Archetypes

The platform currently serves five user archetypes (utilities, regulators, investors, developers, policymakers). The expanded platform shall serve **twenty**:

| # | Archetype | Primary Need | Willingness to Pay |
|---|---|---|---|
| 1 | **National utilities** | Planning, operations, outage prediction | High |
| 2 | **Regulators** | Market monitoring, tariff design | Medium |
| 3 | **Independent power producers** | Site selection, PPA structuring | High |
| 4 | **Institutional investors** | Portfolio risk, due diligence | High |
| 5 | **Development finance institutions** | Project pipeline, impact assessment | High |
| 6 | **Commercial banks** | Project finance, credit risk | High |
| 7 | **Large energy consumers** (mining, manufacturing) | Procurement, backup power | High |
| 8 | **Small businesses & SMEs** | Tariff comparison, solar viability | Low |
| 9 | **Individual households** | Rooftop solar, outage alerts | Free |
| 10 | **City & municipal governments** | Urban energy planning, district energy | Medium |
| 11 | **Journalists & media** | Story detection, data visualisation | Free/Medium |
| 12 | **NGOs & civil society** | Energy access advocacy, monitoring | Free |
| 13 | **Humanitarian organisations** | Refugee camp energy, disaster response | Medium |
| 14 | **Healthcare facilities** | Electrification, cold chain, backup | Low |
| 15 | **Educational institutions** | Teaching, research, data | Free |
| 16 | **Students & researchers** | Datasets, models, benchmarking | Free |
| 17 | **Insurance companies** | Infrastructure risk, climate risk | High |
| 18 | **Carbon markets & traders** | Carbon credit verification, offsets | High |
| 19 | **Telecommunications operators** | Tower power, data centre energy | Medium |
| 20 | **Mining companies** | Remote operations, community energy | High |

### 4. New User Personas

**Persona 1: Amina, Journalist in Lagos**
- Needs: Data for stories, visualisations, alerts on newsworthy events
- Pain point: Energy data is fragmented across dozens of sources
- How PyPSA-X helps: Story detection alerts, embeddable widgets, data downloads

**Persona 2: Kwame, Mini-Grid Developer in Tanzania**
- Needs: Settlement-level demand data, solar resource assessment, tariff design
- Pain point: Cannot afford commercial data services
- How PyPSA-X helps: Free DRE Atlas integration, mini-grid planner tool

**Persona 3: Dr. Ngozi, Hospital Administrator in rural Nigeria**
- Needs: Reliable power for vaccine cold chain, operating theatres
- Pain point: Grid outages are unpredictable and costly
- How PyPSA-X helps: Outage forecasts, backup power ROI calculator, SMS alerts

**Persona 4: Sarah, ESG Analyst at a European Bank**
- Needs: Portfolio exposure to climate risk, carbon accounting
- Pain point: African energy data is opaque and inconsistent
- How PyPSA-X helps: Climate risk dashboard, carbon accounting API

**Persona 5: Professor Mwangi, University Researcher in Nairobi**
- Needs: Datasets for teaching, model benchmarking, publication-quality visualisations
- Pain point: Data collection is time-consuming and expensive
- How PyPSA-X helps: Open data portal, Jupyter notebooks, citation-ready datasets

**Persona 6: Fatima, Small Business Owner in Morocco**
- Needs: Understanding of electricity costs, solar viability
- Pain point: Tariffs are complex, solar quotes are opaque
- How PyPSA-X helps: Tariff comparison tool, solar calculator, Arabic language support

**Persona 7: David, Insurance Underwriter in Johannesburg**
- Needs: Risk assessment for energy infrastructure investments
- Pain point: Climate risk models are Europe-focused
- How PyPSA-X helps: Africa-specific climate risk dashboard, asset-level risk scores

**Persona 8: Chen, Carbon Trader in Singapore**
- Needs: Verification of African carbon offset projects
- Pain point: Additionality and baseline verification is difficult
- How PyPSA-X helps: Carbon accounting API, project-level emissions baselines

---

## Part III: New Capabilities by User Group

### 5. Capabilities for Citizens & Communities

#### 5.1 WhatsApp/SMS Outage Bot

**What**: A conversational bot that allows users to report outages and receive forecasts via WhatsApp or SMS.

**Why**: Mobile penetration in Africa is >80%, but smartphone penetration is lower. WhatsApp and SMS are universal. The GLISSA framework validated social media outage detection in Uganda.

**How**:

```python
# scripts/bots/whatsapp_bot.py
from twilio.rest import Client
from fastapi import FastAPI, Request

app = FastAPI()
twilio = Client(account_sid, auth_token)

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    from_number = form["From"]
    message = form["Body"].strip().lower()
    if message == "outage":
        # User reporting an outage
        location = request.form.get("Location", {}).get("Latitude"), \
                   request.form.get("Location", {}).get("Longitude")
        # Record report
        record_crowdsourced_outage(from_number, location)
        reply = "Thank you. Your report has been recorded. " \
                "Current outage probability in your area: 78%."
    elif message == "forecast":
        # User requesting forecast
        forecast = get_forecast_for_number(from_number)
        reply = format_forecast_message(forecast)
    elif message == "subscribe":
        subscribe_to_alerts(from_number)
        reply = "You are now subscribed to outage alerts for your area."
    else:
        reply = "Commands: OUTAGE (report), FORECAST (check), " \
                "SUBSCRIBE (alerts), STOP (unsubscribe)"
    twilio.messages.create(
        from_="whatsapp:+14155238886",
        to=from_number,
        body=reply
    )
    return {"status": "ok"}
```

**Features**:
- Report outage (with or without location)
- Check outage forecast for user's area
- Subscribe to alerts for specific grid zones
- Receive daily/weekly forecasts
- Multilingual (English, French, Portuguese, Arabic, Swahili, Hausa, Yoruba, Amharic)

#### 5.2 USSD Interface for Feature Phones

**What**: A USSD (`*XXX#`) interface for users without smartphones or data.

**Why**: USSD works on any mobile phone, requires no data, and is familiar to millions of Africans who use it for mobile money.

**How**:

```python
# scripts/bots/ussd_handler.py
@app.post("/ussd/callback")
async def ussd_callback(request: Request):
    form = await request.form()
    session_id = form["sessionId"]
    phone_number = form["phoneNumber"]
    text = form["text"]
    # Parse USSD input
    if text == "":
        response = "CON Welcome to Energy Watch\n"
        response += "1. Check outage forecast\n"
        response += "2. Report outage\n"
        response += "3. Subscribe to alerts\n"
        response += "4. Energy prices\n"
    elif text == "1":
        forecast = get_forecast_for_number(phone_number)
        response = f"END Outage probability: {forecast['probability']}%\n"
        response += f"Expected duration: {forecast['duration']} hours"
    elif text == "2":
        record_crowdsourced_outage(phone_number)
        response = "END Thank you. Your report has been recorded."
    # ...
    return Response(response, media_type="text/plain")
```

#### 5.3 Mobile App

**What**: A React Native mobile app for iOS and Android.

**Features**:
- Personalised dashboard based on location
- Outage forecasts and alerts
- Energy price comparison
- Solar calculator
- Report an outage
- Community forum
- Offline mode (cached data)

#### 5.4 Rooftop Solar Calculator

**What**: A web and mobile tool that estimates rooftop solar potential for individual buildings.

**Why**: Millions of African households and businesses want to know if solar is viable for them. The Global Solar Atlas provides the resource data; PyPSA-X provides the economic analysis.

**How**:

```python
# scripts/tools/solar_calculator.py
class RooftopSolarCalculator:
    def calculate(self, latitude, longitude, roof_area_m2,
                  monthly_bill_usd, tariff_structure):
        # Get solar resource from Global Solar Atlas
        ghi = get_ghi(latitude, longitude)
        # Estimate generation
        system_capacity_kw = roof_area_m2 * 0.15  # 15% roof utilisation
        annual_generation_kwh = (
            system_capacity_kw * ghi * 365 * 0.75  # 75% performance ratio
        )
        # Estimate costs
        capex = system_capacity_kw * get_solar_capex(country)
        # Estimate savings
        self_consumption = estimate_self_consumption(
            annual_generation_kwh, monthly_bill_usd
        )
        annual_savings = self_consumption * tariff_structure.rate
        payback_years = capex / annual_savings
        return {
            "system_capacity_kw": system_capacity_kw,
            "annual_generation_kwh": annual_generation_kwh,
            "capex_usd": capex,
            "annual_savings_usd": annual_savings,
            "payback_years": payback_years,
            "co2_avoided_tonnes": annual_generation_kwh * 0.5 / 1000
        }
```

#### 5.5 Tariff Comparison Tool

**What**: A tool that allows consumers to compare electricity tariffs across utilities and countries.

**Why**: Tariff structures are complex and opaque. Consumers cannot easily compare.

**Features**:
- Input: Monthly consumption (kWh), country, utility
- Output: Estimated monthly bill, comparison to alternatives
- API: `GET /api/v1/tariffs/compare?country=KE&consumption=500`

---

### 6. Capabilities for Journalists & Media

#### 6.1 Story Detection & Alerts

**What**: Automated detection of newsworthy energy events.

**Why**: Journalists need leads. The scanning module (v3.0) already detects signals; this capability surfaces them as story leads.

**How**:

```python
# scripts/media/story_detector.py
class StoryDetector:
    NEWSWORTHY_SIGNALS = [
        "outage_event",       # If widespread or prolonged
        "generation_investment",  # If > 100 MW or > $100M
        "policy_change",      # If significant tariff or subsidy change
        "fuel_price_change",  # If > 10% change
        "climate_event",      # If affecting infrastructure
    ]

    def detect_stories(self, signals, threshold=70):
        """Detect newsworthy events from signals."""
        stories = []
        for signal in signals:
            if signal["signal_type"] in self.NEWSWORTHY_SIGNALS:
                newsworthiness = self._score(signal)
                if newsworthiness >= threshold:
                    stories.append({
                        "headline": self._generate_headline(signal),
                        "summary": self._generate_summary(signal),
                        "signal": signal,
                        "suggested_visualisations": self._suggest_viz(signal),
                        "related_signals": self._find_related(signal, signals),
                        "newsworthiness": newsworthiness
                    })
        return sorted(stories, key=lambda s: -s["newsworthiness"])
```

#### 6.2 Embeddable Widgets

**What**: JavaScript widgets that journalists can embed in articles.

**Examples**:
- Live outage map for a country
- Price forecast chart
- Capacity mix pie chart
- Interactive scenario explorer

**How**:

```html
<!-- Embed code -->
<div id="pypsa-x-outage-map" data-country="NG"></div>
<script src="https://cdn.pypsa-x.africa/widgets/outage-map.js"></script>
```

#### 6.3 Data Journalism Toolkit

**What**: A toolkit for data journalists.

**Contents**:
- Pre-built Jupyter notebooks for common analyses
- Data dictionaries and codebooks
- Visualisation templates (Plotly, D3.js)
- Story angle suggestions
- Expert contact directory

#### 6.4 Automated Newsletter Service

**What**: Curated intelligence briefings delivered by email.

**Segments**:
- **Daily Brief**: Top signals, outage forecasts, price movements
- **Weekly Digest**: Deep dives, analysis, interviews
- **Monthly Report**: Comprehensive market and policy review
- **Sector-Specific**: Solar, wind, hydro, gas, mining, etc.
- **Country-Specific**: 55 country editions

---

### 7. Capabilities for Researchers & Educators

#### 7.1 Open Data Portal

**What**: A portal for bulk data downloads, APIs, and documentation.

**Why**: Researchers need data to conduct studies. The portal becomes the **reference data source for African energy research**.

**Features**:
- Bulk downloads (CSV, Parquet, NetCDF, GeoJSON)
- API access (REST, GraphQL)
- Data dictionaries and codebooks
- Citation metadata (DOI, BibTeX)
- Version history and changelogs
- Usage analytics

**Data products**:
- Grid topology (all 55 countries)
- Power plants (consolidated)
- Renewable profiles (hourly, all technologies)
- Demand profiles (hourly, all countries)
- Outage history (VIIRS-derived)
- Price projections (scenario-based)
- Climate scenarios (CMIP6)

#### 7.2 Jupyter Notebook Templates

**What**: Pre-built notebooks for common research tasks.

**Examples**:
- `01_explore_grid_topology.ipynb`
- `02_analyse_renewable_potential.ipynb`
- `03_compute_capture_prices.ipynb`
- `04_run_scenario_analysis.ipynb`
- `05_validate_outage_predictions.ipynb`
- `06_climate_risk_assessment.ipynb`

#### 7.3 Teaching Datasets & Exercises

**What**: Curated datasets and exercises for university courses.

**Courses supported**:
- Energy Systems Modelling
- Renewable Energy Engineering
- Power Systems Analysis
- Energy Economics
- Climate Policy

#### 7.4 Benchmarking Service

**What**: A service that allows researchers to benchmark their models against PyPSA-X outputs.

**How**:
- Submit model outputs
- Compare against PyPSA-X reference scenarios
- Receive divergence metrics and visualisations
- Publish results (optional)

#### 7.5 Model Zoo

**What**: A repository of pre-trained models for common tasks.

**Models**:
- Outage prediction (per country)
- Demand forecasting (per country)
- Renewable generation forecasting
- Price forecasting
- Asset failure prediction

---

### 8. Capabilities for Businesses & SMEs

#### 8.1 Energy Procurement Advisor

**What**: A tool that helps businesses optimise energy procurement.

**Features**:
- Compare tariffs across utilities
- Evaluate PPA options
- Assess solar + storage viability
- Model backup power costs
- Optimise load shifting

#### 8.2 Backup Power ROI Calculator

**What**: A tool that helps businesses evaluate backup power investments.

**Inputs**:
- Location, industry, load profile
- Current outage frequency and duration
- Cost of downtime
- Options: diesel generator, battery, solar + battery, dual-fuel

**Outputs**:
- NPV, IRR, payback period
- Reliability improvement
- Emissions impact

#### 8.3 Carbon Accounting

**What**: A tool that helps businesses calculate their Scope 1, 2, and 3 emissions.

**Why**: Growing demand for ESG reporting, carbon border adjustments (CBAM), and supply chain decarbonisation.

**Features**:
- Scope 1: Direct emissions (fuel combustion)
- Scope 2: Indirect emissions (purchased electricity)
- Scope 3: Supply chain emissions
- Country-specific grid emission factors
- Time-matched renewable energy certificates

#### 8.4 Supply Chain Risk Assessment

**What**: A tool that assesses energy supply chain risks.

**Features**:
- Critical minerals (lithium, cobalt, copper, rare earths)
- Equipment lead times (turbines, transformers, cables)
- Supplier concentration risk
- Geopolitical risk
- Logistics risk

---

### 9. Capabilities for Financial Institutions

#### 9.1 Project Finance Toolkit

**What**: A toolkit for project finance professionals.

**Contents**:
- Financial model templates (Excel, Python)
- Due diligence checklists
- Risk assessment frameworks
- PPA structuring guides
- Regulatory compliance checklists

#### 9.2 Portfolio Risk Assessment

**What**: A tool that assesses portfolio-level climate and energy transition risks.

**Features**:
- Asset-level exposure to climate hazards
- Transition risk (carbon pricing, policy changes)
- Physical risk (drought, flood, extreme weather)
- Stranded asset risk
- Scenario-based stress testing

#### 9.3 Carbon Credit Verification

**What**: A tool that verifies carbon credit projects.

**Features**:
- Baseline emissions calculation
- Additionality assessment
- Leakage risk analysis
- Permanence risk assessment
- Monitoring, reporting, and verification (MRV)

#### 9.4 Green Bond Framework

**What**: A framework for issuing green bonds for African energy projects.

**Contents**:
- Eligibility criteria
- Impact reporting metrics
- Verification guidelines
- Case studies

---

### 10. Capabilities for Cities & Municipalities

#### 10.1 Urban Energy Planning

**What**: A tool for municipal energy planning.

**Features**:
- Building energy benchmarking
- District heating and cooling assessment
- Waste-to-energy potential
- Rooftop solar potential
- EV charging infrastructure planning

#### 10.2 Climate Action Planning

**What**: A tool for developing municipal climate action plans.

**Features**:
- GHG inventory
- Emissions reduction target setting
- Action identification and prioritisation
- Progress tracking

#### 10.3 Resilience Dashboard

**What**: A dashboard for municipal resilience planning.

**Features**:
- Critical infrastructure mapping
- Hazard exposure assessment
- Vulnerability analysis
- Adaptation options
- Investment planning

---

### 11. Capabilities for Humanitarian & Development

#### 11.1 Refugee Camp Energy Planning

**What**: A tool for planning energy systems in refugee camps.

**Features**:
- Population and demand estimation
- Solar mini-grid design
- Cooking fuel assessment
- Health facility electrification
- Water pumping optimisation

#### 11.2 Disaster Response Toolkit

**What**: A toolkit for energy in disaster response.

**Features**:
- Rapid needs assessment
- Pre-positioned equipment inventory
- Temporary power solutions
- Coordination mechanisms

#### 11.3 Health Facility Electrification

**What**: A tool for electrifying health facilities.

**Features**:
- Facility-level demand assessment
- Solar + storage design
- Vaccine cold chain integration
- Telemedicine connectivity

#### 11.4 School Electrification

**What**: A tool for electrifying schools.

**Features**:
- School-level demand assessment
- Solar + storage design
- Computer lab integration
- Distance learning connectivity

---

### 12. Capabilities for New Markets

#### 12.1 Carbon Markets Integration

**What**: Integration with carbon markets.

**Features**:
- Carbon credit issuance
- Trading platform integration
- Registry integration (Verra, Gold Standard)
- Price discovery

#### 12.2 Blockchain/Crypto Energy Trading

**What**: Integration with blockchain-based energy trading.

**Features**:
- Energy attribute certificates (EACs)
- Peer-to-peer trading
- Tokenised carbon credits
- Smart contract integration

#### 12.3 Gaming & Simulation

**What**: Serious games for energy planning education.

**Examples**:
- "Power Africa" — a simulation game for energy planners
- "Mini-Grid Tycoon" — a game for mini-grid developers
- "Climate Challenge" — a game for climate policy

#### 12.4 Digital Twin for Operations

**What**: A real-time digital twin of the African power system.

**Features**:
- Real-time SCADA integration (where available)
- State estimation
- Contingency analysis
- Predictive maintenance
- Operator training simulator

#### 12.5 Predictive Maintenance Marketplace

**What**: A marketplace connecting asset owners with predictive maintenance service providers.

**Features**:
- Asset registry
- Service provider directory
- Condition monitoring data
- Maintenance scheduling
- Performance benchmarking

#### 12.6 Energy-as-a-Service Platforms

**What**: Integration with energy-as-a-service platforms.

**Features**:
- Subscription-based energy services
- Solar leasing
- Battery-as-a-service
- Efficiency-as-a-service

---

## Part IV: Delivery Channels & Interfaces

### 13. Multi-Channel Delivery Matrix

| Channel | Target Users | Content | Frequency |
|---|---|---|---|
| **Web Dashboard** | All | Full analytics, scenario explorer | Real-time |
| **Mobile App** | Citizens, SMEs, field workers | Alerts, forecasts, calculators | Real-time |
| **WhatsApp Bot** | Citizens, communities | Outage reports, forecasts | Real-time |
| **USSD** | Feature phone users | Forecasts, reports, subscriptions | Real-time |
| **SMS Alerts** | All mobile users | Critical alerts | Event-driven |
| **Email Digests** | Professionals | Newsletters, reports | Daily/Weekly/Monthly |
| **API** | Developers, researchers, businesses | Data, predictions, analytics | Real-time |
| **Embeddable Widgets** | Journalists, bloggers | Maps, charts, forecasts | Real-time |
| **RSS Feeds** | Aggregators, power users | Signals, reports | Real-time |
| **Podcast** | Commuters, general public | Analysis, interviews | Weekly |
| **YouTube** | General public, students | Tutorials, explainers | Weekly |
| **Slack/Teams** | Corporate users | Alerts, reports, queries | Real-time |
| **Google Sheets Add-on** | Analysts, SMEs | Data access, calculations | On-demand |
| **Excel Plugin** | Finance professionals | Data access, models | On-demand |
| **QGIS Plugin** | GIS professionals | Spatial data, analysis | On-demand |
| **Power BI Connector** | Business analysts | Dashboards, reports | On-demand |
| **Tableau Connector** | Data analysts | Dashboards, reports | On-demand |
| **Zapier/IFTTT** | Power users, automation | Triggers, actions | Event-driven |
| **Voice Interface** | Low-literacy users | Forecasts, reports | Real-time |

### 14. Personalization Engine

**What**: A system that personalises content based on user profile, location, and preferences.

**Features**:
- Role-based dashboards
- Location-based alerts
- Language preferences (English, French, Portuguese, Arabic, Swahili, Hausa, Yoruba, Amharic, etc.)
- Content preferences (sectors, countries, technologies)
- Alert thresholds (price, outage probability, emissions)
- Delivery channel preferences

**How**:

```python
# scripts/personalization/engine.py
class PersonalizationEngine:
    def get_dashboard(self, user_id: str) -> dict:
        profile = self._get_profile(user_id)
        return {
            "widgets": self._select_widgets(profile),
            "alerts": self._get_alerts(profile),
            "recommendations": self._get_recommendations(profile),
            "language": profile["language"],
            "theme": profile["theme"]
        }

    def _select_widgets(self, profile: dict) -> list:
        widgets = []
        if profile["role"] == "investor":
            widgets.extend(["price_forecast", "capture_rates", "risk_metrics"])
        elif profile["role"] == "utility":
            widgets.extend(["outage_forecast", "loss_analysis", "resilience_metrics"])
        elif profile["role"] == "journalist":
            widgets.extend(["story_alerts", "data_explorer", "visualisation_builder"])
        # Add location-specific widgets
        for country in profile["countries_of_interest"]:
            widgets.append(f"country_dashboard_{country}")
        return widgets
```

---

## Part V: Open Data & API Ecosystem

### 15. Open Data Commons

**What**: All non-proprietary data generated by the platform shall be freely available under open licences (CC BY 4.0, ODbL, or similar).

**Data products**:

| Dataset | Licence | Format | Update |
|---|---|---|---|
| Grid topology (OSM-derived) | ODbL | GeoJSON, Shapefile | Monthly |
| Power plants (consolidated) | CC BY 4.0 | CSV, Parquet | Weekly |
| Renewable profiles | CC BY 4.0 | NetCDF, Parquet | Annual |
| Demand profiles | CC BY 4.0 | CSV, Parquet | Monthly |
| Outage history (VIIRS) | CC BY 4.0 | CSV, Parquet | Daily |
| Price projections | CC BY 4.0 | CSV, Parquet | Quarterly |
| Climate scenarios | CC BY 4.0 | NetCDF | Annual |
| Country statistics | CC BY 4.0 | CSV | Monthly |

### 16. API Ecosystem

**API Tiers**:

| Tier | Rate Limit | Data Access | Price |
|---|---|---|---|
| **Public** | 100 requests/day | Open data, basic forecasts | Free |
| **Researcher** | 10,000 requests/day | Open data, full forecasts | Free (academic email) |
| **Professional** | 100,000 requests/day | All data, custom scenarios | $500/month |
| **Enterprise** | 1M requests/day | All data, custom models, SLA | $5,000/month |
| **Partner** | Custom | All data, white-label, co-development | Negotiated |

**SDKs**:

| Language | Package | Repository |
|---|---|---|
| Python | `pypsa-x` | `github.com/pypsa-x/pypsa-x-python` |
| R | `pypsaX` | `github.com/pypsa-x/pypsa-x-r` |
| JavaScript | `@pypsa-x/sdk` | `github.com/pypsa-x/pypsa-x-js` |
| Java | `pypsa-x-java` | `github.com/pypsa-x/pypsa-x-java` |

---

## Part VI: Community & Crowdsourcing

### 17. Community Engagement Platform

**What**: A platform for community engagement, crowdsourcing, and collaboration.

**Features**:
- **Crowdsourced outage reports**: Users report outages via app, WhatsApp, USSD, or web
- **Ground-truthing**: Users validate VIIRS-detected outages
- **Data quality feedback**: Users flag data errors
- **Discussion forums**: Users discuss energy issues
- **Expert Q&A**: Users ask questions, experts answer
- **User-generated content**: Users share analyses, visualisations, stories
- **Collaborative projects**: Users form teams to work on projects

### 18. Gamification

**What**: Gamification to encourage participation.

**Features**:
- **Points and badges**: For contributions (outage reports, validations, analyses)
- **Leaderboards**: Top contributors by country, category
- **Challenges**: Monthly challenges (e.g., "Map your neighbourhood's grid")
- **Rewards**: Recognition, early access to features, conference invitations

### 19. Citizen Science

**What**: Citizen science projects that leverage the community.

**Examples**:
- **Solar potential mapping**: Users photograph rooftops, AI estimates solar potential
- **Outage documentation**: Users document outage impacts
- **Energy poverty mapping**: Users report energy access issues
- **Air quality monitoring**: Users host low-cost sensors near power plants

---

## Part VII: Commercial Model & Sustainability

### 20. Freemium Model

**Free Tier**:
- Open data access
- Basic forecasts (7-day outage, monthly prices)
- Dashboard with standard widgets
- Newsletter subscriptions
- Community participation

**Professional Tier** ($500/month):
- Full data access
- Extended forecasts (30-day outage, 5-year prices)
- Custom scenarios
- API access (100k requests/day)
- Priority support

**Enterprise Tier** ($5,000/month):
- All Professional features
- Custom models
- White-label options
- Dedicated support
- SLA
- On-premise deployment

**Partner Tier** (Negotiated):
- Co-development
- Data sharing
- Revenue sharing
- Joint go-to-market

### 21. Additional Revenue Streams

| Stream | Description | Target |
|---|---|---|
| **Consulting** | Bespoke analysis for clients | $250k–$2M/project |
| **Training** | Capacity building programmes | $500–$5,000/participant |
| **Certification** | Professional certification | $1,000/exam |
| **Data Licensing** | Bulk data for commercial use | $10k–$100k/year |
| **Sponsorships** | Report sponsorship | $50k–$500k/year |
| **Grants** | Foundation and development grants | $100k–$5M |
| **Advertising** | Non-intrusive ads for energy services | $10k–$100k/year |

### 22. Sustainability Plan

**Phase 1 (Years 1–2): Grant-funded**
- Development funded by development finance institutions, foundations
- Free access for all users
- Build user base and credibility

**Phase 2 (Years 3–4): Hybrid**
- Introduce Professional and Enterprise tiers
- Continue grant funding for public good components
- Revenue covers 50% of operating costs

**Phase 3 (Years 5+): Self-sustaining**
- Revenue covers 100% of operating costs
- Surplus reinvested in platform development
- Public good components funded by cross-subsidy

---

## Part VIII: Partnership & Ecosystem Strategy

### 23. Partnership Network

| Partner Type | Examples | Role |
|---|---|---|
| **Continental institutions** | AUDA-NEPAD, AFREC, AfDB | Data sharing, co-development, endorsement |
| **Power pools** | SAPP, EAPP, WAPP, CAPP, COMELEC | Data sharing, validation |
| **National utilities** | Eskom, KPLC, ECG, ZESCO | Data sharing, validation |
| **Regulators** | NERSA, KPLC, ERA | Data sharing, validation |
| **Universities** | University of Cape Town, KTH, Makerere | Research collaboration, student projects |
| **NGOs** | GridWatch, Energy Access Network | Data sharing, community engagement |
| **Development finance** | World Bank, IFC, AfDB, BII | Funding, data sharing |
| **Media** | Reuters, Bloomberg, Energy Monitor | Distribution, story collaboration |
| **Tech companies** | Google, Microsoft, AWS | Cloud infrastructure, AI/ML |
| **Data providers** | Global Energy Monitor, RePP Africa | Data sharing |
| **Standards bodies** | Open Energy Modelling Initiative | Standards, interoperability |

### 24. Open Source Community

**What**: A vibrant open-source community that contributes to the platform.

**Features**:
- **GitHub repository**: Public, MIT-licensed
- **Contributor guidelines**: Clear, welcoming
- **Issue tracker**: Public, transparent
- **Pull requests**: Reviewed, merged
- **Community calls**: Monthly
- **Hackathons**: Annual
- **Bounties**: For priority features

---

## Part IX: Technical Architecture for Scale

### 25. Microservices Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  API Gateway (Kong)                                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Auth     │ │ Data     │ │ Predict  │ │ Report   │ │ Bots     │   │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Scenario │ │ Market   │ │ Outage   │ │ Loss     │ │ What-If  │   │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  Message Queue (RabbitMQ / Kafka)                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Data Layer                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │PostgreSQL│ │ Timescale│ │  Redis   │ │ MinIO    │ │ Neo4j    │   │
│  │(metadata)│ │ (time-   │ │ (cache)  │ │ (objects)│ │ (graph)  │   │
│  │          │ │  series) │ │          │ │          │ │          │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 26. Scalability Strategy

| Component | Scaling Strategy |
|---|---|
| **API Gateway** | Horizontal (Kubernetes HPA) |
| **Data Service** | Read replicas, caching |
| **Predict Service** | GPU nodes, batch processing |
| **Report Service** | Queue-based, auto-scaling |
| **Bots Service** | Serverless (AWS Lambda, Cloud Functions) |
| **Scenario Service** | HPC cluster, job queue |
| **Database** | Sharding by country/region |
| **Object Storage** | S3-compatible, CDN |
| **Message Queue** | Kafka partitioning |

---

## Part X: Roadmap

### 27. Phased Delivery

| Phase | Duration | Deliverable | User Groups |
|---|---|---|---|
| **1. Foundation** | 6 months | Core platform (v1.0–v2.0) | Utilities, regulators, investors |
| **2. Predictive** | 4 months | Outage prediction, loss mitigation | Utilities, regulators, insurers |
| **3. What-If** | 3 months | Scenario engine | Investors, policymakers |
| **4. Reporting** | 3 months | Periodic reports | All professionals |
| **5. Scanning** | 4 months | Automated intelligence | All |
| **6. Open Data** | 3 months | Data portal, APIs | Researchers, developers |
| **7. Multi-Channel** | 6 months | Mobile, WhatsApp, USSD, SMS | Citizens, SMEs, communities |
| **8. Tools** | 6 months | Solar calculator, tariff comparison, carbon accounting | Citizens, SMEs, businesses |
| **9. Community** | 4 months | Crowdsourcing, forums, gamification | All |
| **10. Ecosystem** | 6 months | Partnerships, SDKs, integrations | All |
| **11. Commercial** | 3 months | Paid tiers, consulting, training | Enterprises |
| **12. Scale** | Ongoing | Microservices, global CDN | All |

### 28. Key Milestones

| Milestone | Target Date | Success Metric |
|---|---|---|
| **10,000 users** | Month 12 | Registered users |
| **1,000 API consumers** | Month 18 | Active API keys |
| **100,000 monthly active users** | Month 24 | MAU |
| **1M data downloads** | Month 30 | Total downloads |
| **$1M annual revenue** | Month 36 | Revenue |
| **Self-sustaining** | Month 48 | Revenue > costs |

---

## Part XI: Conclusion

This specification defines the transformation of PyPSA-X Pan-African from a **modelling platform** into an **Energy Intelligence Platform for Africa** — a public utility for energy information that serves **twenty user archetypes** across **eighteen delivery channels** with **thirty new capabilities**.

The platform becomes:

- **A data commons**: Open data for all
- **A prediction service**: Outage, price, demand, climate forecasts
- **A toolkit**: Solar calculators, tariff comparators, carbon accounting
- **A community**: Crowdsourcing, forums, gamification
- **A marketplace**: Connecting asset owners, service providers, financiers
- **A public good**: Free access for citizens, journalists, researchers, NGOs
- **A sustainable business**: Freemium model with commercial tiers

The vision is nothing less than a **Bloomberg Terminal for African Energy** — but open, accessible, and serving everyone from a farmer in Malawi to a sovereign wealth fund in Abu Dhabi. It is the platform that **democratises energy intelligence** and **accelerates Africa's energy transition** by putting world-class data, predictions, and analyses in the hands of everyone who needs them.

---

**End of Specification**