# ALEA: Interface Specification

## Complete Definition of All Interfaces — External, Internal, and Inbound

**Version**: 1.0
**Status**: Draft for Developer Implementation
**Audience**: Intermediate developers, API designers, integration engineers
**Companion Documents**: ALEA Product Specification v4.0

---

## Part I: Interface Philosophy

### 1. Why Interfaces Are the Product

ALEA is not a single application. It is a **platform** — a collection of analytical engines, data pipelines, and intelligence services that must be usable by twenty different user archetypes across eighteen delivery channels. The interfaces are not an afterthought; they **are** the product. A user never sees the PyPSA optimisation engine, the VIIRS processing pipeline, or the agent-based market simulator. They see an API response, a dashboard widget, a WhatsApp message, or a PDF report. If the interfaces are poor, the platform fails regardless of how sophisticated the underlying analytics are.

### 2. Interface Design Principles

| Principle | Rationale | Implementation |
|---|---|---|
| **Progressive disclosure** | Different users need different levels of detail | Simple endpoints for citizens, rich endpoints for analysts |
| **Consistency across channels** | A user should get the same answer via API, dashboard, or WhatsApp | Single source of truth in the service layer; channels are presentation |
| **Explicit uncertainty** | Every prediction carries uncertainty; hiding it is dishonest | All forecast endpoints return confidence intervals |
| **Provenance by default** | Every data point traces to its source | All responses include `source` and `provenance` metadata |
| **Open by default, closed by exception** | Public data is free; proprietary analytics are tiered | Tiered authentication; open data endpoints require no key |
| **Idempotency** | Retries must not corrupt state | All mutating operations accept idempotency keys |
| **Versioning** | Interfaces evolve; clients must not break | URL versioning (`/v1/`), deprecation headers |
| **Rate limiting** | Protect infrastructure from abuse | Token bucket per API key; tiered limits |
| **Observability** | Every request is traceable | OpenTelemetry spans, structured logging, request IDs |

### 3. Interface Taxonomy

ALEA exposes and consumes interfaces across six categories:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ALEA INTERFACE TAXONOMY                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  A. EXTERNAL INTERFACES (ALEA → Users)                             │
│     A1. REST API                                                    │
│     A2. GraphQL API                                                 │
│     A3. WebSocket / Server-Sent Events                              │
│     A4. Web Dashboard                                               │
│     A5. Mobile Applications (iOS, Android)                          │
│     A6. Conversational Bots (WhatsApp, USSD, SMS, Voice)            │
│     A7. Embeddable Widgets                                          │
│     A8. SDKs (Python, R, JavaScript, Java)                          │
│     A9. Bulk Data Portal                                            │
│     A10. Webhooks                                                   │
│     A11. Email & RSS                                                │
│     A12. Spreadsheet & BI Connectors                                │
│     A13. GIS Plugins                                                │
│                                                                     │
│  B. INTERNAL INTERFACES (Layer → Layer)                             │
│     B1. Layer 1 → Layer 2 (Planning → Sector)                       │
│     B2. Layer 2 → Layer 3 (Sector → Market)                         │
│     B3. Layer 3 → Layer 4 (Market → Predictive)                     │
│     B4. Layer 4 → Layer 5 (Predictive → What-If)                    │
│     B5. Layer 5 → Layer 6 (What-If → Reporting)                     │
│     B6. Cross-layer: Message Queue                                  │
│     B7. Cross-layer: Shared Database Schemas                        │
│     B8. Cross-layer: Model Artefact Registry                        │
│                                                                     │
│  C. INBOUND INTERFACES (External → ALEA)                            │
│     C1. Source Connectors (News, Tenders, Social, Institutional)    │
│     C2. Crowdsourcing Endpoints                                     │
│     C3. Human Review Interface                                      │
│     C4. Partner Data Exchange                                       │
│                                                                     │
│  D. PLATFORM INTERFACES (Infrastructure)                            │
│     D1. Authentication & Authorisation                              │
│     D2. Rate Limiting & Quotas                                      │
│     D3. Observability & Tracing                                     │
│     D4. Job Scheduling & Orchestration                              │
│                                                                     │
│  E. ADMINISTRATIVE INTERFACES                                       │
│     E1. Admin Console                                               │
│     E2. Model Management                                            │
│     E3. User Management                                             │
│                                                                     │
│  F. INTERFACE GOVERNANCE                                            │
│     F1. Versioning & Deprecation                                    │
│     F2. Documentation & Discovery                                   │
│     F3. Testing & Contract Validation                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part II: External Interfaces

### 4. A1 — REST API

#### 4.1.1 Design Rationale

The REST API is the **primary programmatic interface** for developers, businesses, and researchers. It follows REST conventions, uses JSON for payloads, and is versioned via URL path. It is designed to be **discoverable** (via OpenAPI specification), **predictable** (consistent naming, pagination, error codes), and **cacheable** (ETag, Cache-Control headers).

#### 4.1.2 Base URL and Versioning

```
Production:  https://api.alea.africa/v1/
Staging:     https://api.staging.alea.africa/v1/
Sandbox:     https://api.sandbox.alea.africa/v1/
```

Versioning follows **URL path versioning**. Breaking changes increment the major version. Non-breaking additions are made within a version. Deprecation is announced via `Sunset` and `Deprecation` headers at least 6 months in advance.

#### 4.1.3 Authentication

Three authentication modes:

| Mode | Use Case | Header | Rate Limit |
|---|---|---|---|
| **None** | Open data endpoints | — | 60 req/hour per IP |
| **API Key** | Standard access | `X-API-Key: <key>` | Tier-dependent |
| **OAuth 2.0** | Third-party apps on behalf of users | `Authorization: Bearer <token>` | Tier-dependent |

#### 4.1.4 Endpoint Catalogue

**4.1.4.1 System Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/health` | GET | Liveness probe | None |
| `/ready` | GET | Readiness probe | None |
| `/version` | GET | API version and build info | None |
| `/openapi.json` | GET | OpenAPI 3.1 specification | None |
| `/docs` | GET | Interactive API documentation (Swagger UI) | None |

**4.1.4.2 Country and Region Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/countries` | GET | List all 55 AU member states | None |
| `/countries/{iso}` | GET | Country metadata (population, GDP, grid stats) | None |
| `/countries/{iso}/regions` | GET | Sub-national regions | None |
| `/power-pools` | GET | List five power pools | None |
| `/power-pools/{code}` | GET | Power pool details and member states | None |

**4.1.4.3 Grid and Generation Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/grid/{iso}/topology` | GET | Transmission network (GeoJSON) | Public |
| `/grid/{iso}/substations` | GET | Substations with capacity | Public |
| `/grid/{iso}/interconnectors` | GET | Cross-border lines | Public |
| `/generation/{iso}/plants` | GET | Power plants with capacity, fuel, status | Public |
| `/generation/{iso}/capacity` | GET | Aggregated capacity by technology | Public |
| `/generation/{iso}/dispatch` | GET | Historical or simulated dispatch | Professional |

**4.1.4.4 Renewable Resource Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/renewables/{iso}/solar` | GET | Solar resource (GHI, DNI, PVOUT) | Public |
| `/renewables/{iso}/wind` | GET | Wind resource (speed, power density) | Public |
| `/renewables/{iso}/hydro` | GET | Hydropower potential and profiles | Public |
| `/renewables/{iso}/geothermal` | GET | Geothermal resource (temperature-depth) | Public |
| `/renewables/{iso}/biomass` | GET | Biomass potential by feedstock | Public |
| `/renewables/{iso}/marine` | GET | Wave, tidal, OTEC potential | Public |
| `/renewables/{iso}/profiles` | GET | Hourly generation profiles | Professional |

**4.1.4.5 Demand Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/demand/{iso}/current` | GET | Current estimated demand | Public |
| `/demand/{iso}/forecast` | GET | Demand forecast (hourly to 7 days) | Professional |
| `/demand/{iso}/historical` | GET | Historical demand (monthly) | Public |
| `/demand/{iso}/profile` | GET | Hourly load profile | Professional |
| `/demand/{iso}/settlements` | GET | Settlement-level demand (DRE Atlas) | Professional |

**4.1.4.6 Price and Market Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/prices/{iso}/current` | GET | Current wholesale price | Public |
| `/prices/{iso}/forecast` | GET | Price forecast (hourly to 30 days) | Professional |
| `/prices/{iso}/historical` | GET | Historical prices | Public |
| `/prices/{iso}/capture-rates` | GET | Renewable capture rates by technology | Professional |
| `/prices/{iso}/ppa-benchmarks` | GET | PPA benchmark curves | Enterprise |
| `/markets/{pool}/clearing` | GET | Pool-level market clearing prices | Professional |
| `/markets/{pool}/flows` | GET | Cross-border power flows | Professional |

**4.1.4.7 Outage and Resilience Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/outages/{iso}/forecast` | GET | Outage probability forecast | Public |
| `/outages/{iso}/history` | GET | Historical outage events (VIIRS-derived) | Public |
| `/outages/{iso}/zones` | GET | Outage probability by grid zone | Professional |
| `/outages/report` | POST | Crowdsourced outage report | None |
| `/resilience/{iso}/metrics` | GET | ENS, EENS, SAIDI, SAIFI, TLENS | Professional |
| `/resilience/{iso}/contingency` | POST | Run N-1 contingency analysis | Enterprise |

**4.1.4.8 Loss Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/losses/{iso}/decompose` | GET | Loss decomposition by driver | Professional |
| `/losses/{iso}/critical-lines` | GET | TLENS-ranked critical corridors | Professional |
| `/losses/{iso}/mitigations` | POST | Rank mitigation options | Enterprise |

**4.1.4.9 Scenario and What-If Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/scenarios` | GET | List available scenarios | Public |
| `/scenarios` | POST | Create a scenario | Professional |
| `/scenarios/{id}` | GET | Retrieve scenario definition | Professional |
| `/scenarios/{id}/results` | GET | Retrieve scenario results | Professional |
| `/scenarios/{id}/status` | GET | Check solve status | Professional |
| `/whatif/solve` | POST | Solve a what-if scenario | Enterprise |
| `/whatif/compare` | POST | Compare multiple scenarios | Enterprise |
| `/whatif/frontier` | POST | Generate efficient frontier | Enterprise |

**4.1.4.10 Reporting Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/reports/daily` | GET | Latest daily report (PDF/HTML) | Professional |
| `/reports/weekly` | GET | Latest weekly report | Professional |
| `/reports/monthly` | GET | Latest monthly report | Professional |
| `/reports/{type}/{date}` | GET | Specific report by date | Professional |
| `/reports/subscribe` | POST | Subscribe to report delivery | Professional |

**4.1.4.11 Intelligence Scanning Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/signals` | GET | Query extracted signals | Professional |
| `/signals/{id}` | GET | Retrieve specific signal | Professional |
| `/signals/pending` | GET | Signals awaiting review | Admin |
| `/signals/{id}/confirm` | POST | Confirm a signal | Admin |
| `/signals/{id}/reject` | POST | Reject a signal | Admin |
| `/sources` | GET | List active source connectors | Public |
| `/sources/{id}/health` | GET | Connector health status | Professional |

**4.1.4.12 Data Portal Endpoints**

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/datasets` | GET | List available datasets | Public |
| `/datasets/{id}` | GET | Dataset metadata | Public |
| `/datasets/{id}/download` | GET | Download dataset (signed URL) | Tier-dependent |
| `/datasets/{id}/versions` | GET | Dataset version history | Public |
| `/datasets/{id}/citation` | GET | Citation metadata (DOI, BibTeX) | Public |

#### 4.1.5 Common Response Patterns

**Standard response envelope**:

```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_01HXYZ...",
    "timestamp": "2026-10-11T14:23:00Z",
    "version": "v1",
    "source": "VIIRS VNP46A2",
    "provenance": {
      "pipeline": "outage_prediction_v2.3",
      "model_hash": "sha256:abc123...",
      "data_hash": "sha256:def456..."
    },
    "uncertainty": {
      "confidence_level": 0.95,
      "lower": 0.62,
      "upper": 0.84
    }
  },
  "links": {
    "self": "/v1/outages/NG/forecast",
    "related": "/v1/outages/NG/history"
  }
}
```

**Error response format**:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "You have exceeded the rate limit for your tier.",
    "details": {
      "limit": 1000,
      "window": "1h",
      "retry_after_seconds": 342
    },
    "documentation_url": "https://docs.alea.africa/errors/RATE_LIMIT_EXCEEDED",
    "request_id": "req_01HXYZ..."
  }
}
```

**Pagination**:

```
GET /v1/signals?page=2&page_size=50&sort=-published_at

Response:
{
  "data": [...],
  "pagination": {
    "page": 2,
    "page_size": 50,
    "total_items": 1247,
    "total_pages": 25,
    "next": "/v1/signals?page=3&page_size=50",
    "prev": "/v1/signals?page=1&page_size=50"
  }
}
```

**Filtering and field selection**:

```
GET /v1/generation/ZA/plants?fuel=solar&min_capacity=100&fields=name,capacity,lat,lon

Response:
{
  "data": [
    {"name": "De Aar Solar", "capacity": 175, "lat": -30.65, "lon": 24.01},
    ...
  ]
}
```

#### 4.1.6 Rate Limits

| Tier | Requests/hour | Burst | Concurrent | Cost |
|---|---|---|---|---|
| **Public** | 60 | 10 | 2 | Free |
| **Researcher** | 10,000 | 100 | 10 | Free (academic) |
| **Professional** | 100,000 | 500 | 50 | $500/month |
| **Enterprise** | 1,000,000 | 5,000 | 200 | $5,000/month |
| **Partner** | Custom | Custom | Custom | Negotiated |

Rate limit headers are returned on every response:

```
X-RateLimit-Limit: 100000
X-RateLimit-Remaining: 99847
X-RateLimit-Reset: 1728654000
Retry-After: 342
```

---

### 5. A2 — GraphQL API

#### 5.2.1 Design Rationale

The REST API is efficient for known queries but inefficient for **complex, nested, or exploratory queries**. A user wanting "the 10 largest solar plants in each SAPP country, with their capture prices and 2026 outage forecasts" would need 4+ REST calls. GraphQL solves this with a **single query** that returns exactly what the client needs.

#### 5.2.2 Endpoint

```
POST https://api.alea.africa/graphql
GET  https://api.alea.africa/graphql  (for introspection)
```

#### 5.2.3 Schema Excerpt

```graphql
type Query {
  country(iso: String!): Country
  countries(powerPool: String, limit: Int, offset: Int): [Country!]!
  generator(id: ID!): Generator
  generators(country: String, technology: String, minCapacity: Float): [Generator!]!
  outageForecast(country: String!, horizonHours: Int = 24): OutageForecast!
  priceForecast(country: String!, horizonDays: Int = 30): PriceForecast!
  scenario(id: ID!): Scenario
  signals(type: String, country: String, since: DateTime): [Signal!]!
}

type Country {
  iso: String!
  name: String!
  population: Int!
  gdpUsd: Float!
  powerPool: PowerPool!
  installedCapacity: CapacityMix!
  generators: [Generator!]!
  demandProfile: TimeSeries!
  priceForecast: PriceForecast!
  outageForecast: OutageForecast!
  renewablePotential: RenewablePotential!
}

type Generator {
  id: ID!
  name: String!
  country: Country!
  technology: String!
  capacityMw: Float!
  latitude: Float!
  longitude: Float!
  commissioned: Date
  status: String!
  capturePrice: CapturePrice
  outageRisk: Float
}

type OutageForecast {
  country: Country!
  generatedAt: DateTime!
  horizonHours: Int!
  zones: [OutageZone!]!
  systemRisk: Float!
  confidence: Float!
}

type OutageZone {
  id: ID!
  name: String!
  probability: Float!
  confidenceLower: Float!
  confidenceUpper: Float!
  expectedDurationHours: Float
  riskLevel: RiskLevel!
}

enum RiskLevel { LOW MEDIUM HIGH CRITICAL }
```

#### 5.2.4 Example Query

```graphql
query SAPPInvestmentScan {
  countries(powerPool: "SAPP") {
    iso
    name
    installedCapacity { solar wind coal gas }
    generators(technology: "solar", minCapacity: 100) {
      name
      capacityMw
      capturePrice { value currency year }
      outageRisk
    }
    priceForecast(horizonDays: 3650) {
      yearly {
        year
        avgPrice
        p10
        p90
      }
    }
  }
}
```

**Why this matters**: A single query returns a complete investment-scanning dataset across all SAPP countries. Equivalent REST calls would require 15+ round trips.

---

### 6. A3 — WebSocket & Server-Sent Events

#### 6.3.1 Design Rationale

Some interfaces require **real-time streaming**: outage alerts, price movements, scenario solve progress, and live dashboard updates. Polling is inefficient and slow. WebSocket provides bidirectional streaming; SSE provides unidirectional server-to-client streaming (simpler, works through proxies).

#### 6.3.2 Endpoints

```
WebSocket:  wss://api.alea.africa/v1/stream
SSE:        https://api.alea.africa/v1/stream/sse
```

#### 6.3.3 Channel Subscription

```json
// Client sends (WebSocket):
{
  "action": "subscribe",
  "channels": [
    {"name": "outages", "filter": {"country": "NG", "min_probability": 0.5}},
    {"name": "prices", "filter": {"country": "ZA", "market": "day_ahead"}},
    {"name": "scenario", "filter": {"id": "scenario_abc123"}},
    {"name": "signals", "filter": {"types": ["outage_event", "generation_investment"]}}
  ]
}

// Server responds:
{
  "action": "subscribed",
  "subscriptions": ["sub_1", "sub_2", "sub_3", "sub_4"]
}
```

#### 6.3.4 Event Stream

```json
// Outage alert
{
  "channel": "outages",
  "event": "outage_forecast_update",
  "timestamp": "2026-10-11T14:23:00Z",
  "data": {
    "country": "NG",
    "zone": "Lagos Island",
    "probability": 0.82,
    "confidence": [0.71, 0.91],
    "risk_level": "HIGH"
  }
}

// Scenario progress
{
  "channel": "scenario",
  "event": "solve_progress",
  "timestamp": "2026-10-11T14:24:00Z",
  "data": {
    "scenario_id": "scenario_abc123",
    "stage": "optimization",
    "progress_pct": 67,
    "estimated_completion": "2026-10-11T15:10:00Z"
  }
}
```

---

### 7. A4 — Web Dashboard

#### 7.4.1 Design Rationale

The dashboard is the **primary human interface**. It must serve users ranging from a journalist needing a quick visualisation to an analyst building a complex scenario. It uses **role-based views**, **progressive disclosure**, and **embeddable components**.

#### 7.4.2 Technology Stack

- **Framework**: Next.js 14 (React 18, App Router)
- **Styling**: Tailwind CSS + shadcn/ui
- **Charts**: Plotly.js, D3.js for custom visualisations
- **Maps**: MapLibre GL JS (open source, no API key)
- **State**: Zustand + React Query
- **Auth**: NextAuth.js (OAuth 2.0 + API key)

#### 7.4.3 Route Structure

```
/                           → Landing page
/login                      → Authentication
/dashboard                  → Role-based home dashboard
/countries                  → Country list and comparison
/countries/[iso]            → Country dashboard
/power-pools                → Power pool comparison
/power-pools/[code]         → Pool dashboard
/map                        → Continental interactive map
/generation                 → Generation asset explorer
/renewables                 → Renewable resource explorer
/demand                     → Demand explorer and forecast
/prices                     → Price explorer and forecast
/outages                    → Outage map and forecast
/losses                     → Loss analysis and mitigation
/resilience                 → Resilience metrics and stress testing
/scenarios                  → Scenario library
/scenarios/new              → Scenario builder
/scenarios/[id]             → Scenario results
/whatif                     → Interactive what-if explorer
/signals                    → Intelligence signal feed
/signals/[id]               → Signal detail
/reports                    → Report library
/reports/[type]/[date]      → Specific report
/datasets                   → Data portal
/datasets/[id]              → Dataset detail
/api-keys                   → API key management
/settings                   → User settings
/admin                      → Admin console (role-restricted)
```

#### 7.4.4 Role-Based Dashboards

| Role | Default Dashboard Widgets |
|---|---|
| **Utility operator** | Outage forecast, generation dispatch, reserve margin, critical lines |
| **Regulator** | Market prices, capacity mix, compliance metrics, policy tracker |
| **Investor** | Price forecasts, capture rates, PPA benchmarks, portfolio risk |
| **Developer** | Site selection map, resource assessment, PPA curves |
| **Journalist** | Story alerts, data explorer, visualisation builder |
| **Researcher** | Data download, Jupyter integration, model benchmarking |
| **Policymaker** | Scenario explorer, CMP alignment, climate risk |
| **Citizen** | Local outage forecast, tariff comparison, solar calculator |

#### 7.4.5 Key Interactive Components

**7.4.5.1 Continental Map**

- Vector tiles served from a CDN
- Layers: grid topology, generation assets, renewable potential, outage risk, price zones
- Click a country → country dashboard
- Click a generator → generator detail panel
- Time slider for historical and forecast data
- Export as PNG, SVG, GeoJSON

**7.4.5.2 Scenario Builder**

- Drag-and-drop parameter selection
- Sliders for continuous parameters (carbon price, demand growth)
- Dropdowns for discrete parameters (SSP pathway, technology)
- Real-time preview of expected results
- Save, share, and compare scenarios

**7.4.5.3 What-If Explorer**

- Parameter panel on the left
- Live results on the right
- Efficient frontier chart
- Scenario comparison table
- Export to PDF, CSV, or shareable link

**7.4.5.4 Signal Feed**

- Infinite scroll of signals
- Filters by type, country, source, confidence
- Confirm/reject/edit actions (for reviewers)
- Related signals and corroborating sources
- Link to source document

---

### 8. A5 — Mobile Applications

#### 8.5.1 Design Rationale

Africa is mobile-first. Many users do not have reliable desktop access. The mobile app must work **offline**, be **lightweight**, and support **low-bandwidth** conditions.

#### 8.5.2 Technology Stack

- **Framework**: React Native (Expo)
- **Offline storage**: SQLite + WatermelonDB
- **Sync**: Background sync with conflict resolution
- **Push notifications**: Firebase Cloud Messaging
- **Maps**: MapLibre Native

#### 8.5.3 Features

| Feature | Description | Offline Support |
|---|---|---|
| **Outage forecast** | Location-based forecast with alerts | Cached (24h) |
| **Report outage** | One-tap reporting | Queued |
| **Price check** | Current and forecast prices | Cached (7d) |
| **Solar calculator** | Rooftop solar ROI | Fully offline |
| **Tariff comparison** | Compare utility tariffs | Cached |
| **Data explorer** | Browse key statistics | Cached (30d) |
| **Notifications** | Push alerts for outages, prices | N/A |

---

### 9. A6 — Conversational Bots

#### 9.6.1 Design Rationale

The most inclusive interfaces are those that require **no smartphone, no data, and no literacy**. WhatsApp, USSD, SMS, and voice reach users that no app can.

#### 9.6.2 WhatsApp Bot

**Endpoint**: Meta Cloud API webhook at `https://api.alea.africa/v1/bots/whatsapp/webhook`

**Supported languages**: English, French, Portuguese, Arabic, Swahili, Hausa, Yoruba, Amharic

**Command grammar**:

| Command | Response |
|---|---|
| `HELLO` | Welcome menu |
| `OUTAGE` | Report an outage (with optional location) |
| `FORECAST` | Outage forecast for user's registered location |
| `PRICE` | Current electricity price for user's country |
| `SUBSCRIBE` | Subscribe to alerts |
| `UNSUBSCRIBE` | Unsubscribe |
| `LANGUAGE <code>` | Change language |
| `HELP` | Command list |

**Rich responses**: WhatsApp supports interactive buttons and lists. Example:

```
ALEA: What would you like to do?
[Check outage forecast] [Report outage]
[Check prices] [Settings]
```

#### 9.6.3 USSD Interface

**Endpoint**: `https://api.alea.africa/v1/bots/ussd`

**Session flow**:

```
CON Welcome to ALEA
1. Outage forecast
2. Report outage
3. Electricity prices
4. Subscribe to alerts
5. Change language
```

Sessions time out after 180 seconds. All responses are ≤ 182 characters.

#### 9.6.4 SMS Interface

**Endpoint**: Aggregator webhook (Twilio, Africa's Talking, Infobip)

**Short codes**: Per-country short codes provisioned through aggregators

**Commands**: Same as WhatsApp, but no rich responses

#### 9.6.5 Voice Interface

**Endpoint**: `https://api.alea.africa/v1/bots/voice`

**Technology**: Twilio Voice + Whisper (ASR) + GPT-4 (NLU) + ElevenLabs (TTS) for local languages

**Supported languages**: English, French, Portuguese, Arabic, Swahili

**Use case**: A farmer calls a toll-free number, asks "Will there be power tomorrow?", and hears a spoken forecast.

---

### 10. A7 — Embeddable Widgets

#### 10.7.1 Design Rationale

Journalists, bloggers, and partner websites want to embed ALEA data without building their own integrations. Widgets provide **ready-made, styled components** that can be embedded with a single `<script>` tag.

#### 10.7.2 Widget Catalogue

| Widget | Description | Embed Code |
|---|---|---|
| **Outage Map** | Live outage probability map | `<div data-alea-widget="outage-map" data-country="NG"></div>` |
| **Price Chart** | Price forecast chart | `<div data-alea-widget="price-chart" data-country="ZA"></div>` |
| **Capacity Mix** | Current capacity mix | `<div data-alea-widget="capacity-mix" data-country="KE"></div>` |
| **Signal Feed** | Latest intelligence signals | `<div data-alea-widget="signal-feed" data-country="EG"></div>` |
| **Scenario Explorer** | Mini what-if tool | `<div data-alea-widget="scenario-mini"></div>` |
| **Tariff Calculator** | Consumer tariff comparison | `<div data-alea-widget="tariff-calculator"></div>` |

#### 10.7.3 Configuration

All widgets accept `data-*` attributes for configuration. The loader script reads these and renders the widget:

```html
<script src="https://cdn.alea.africa/widgets/v1/loader.js" async></script>
```

Widgets are rendered in an iframe to isolate styles. They inherit the parent's theme via `postMessage`.

---

### 11. A8 — SDKs

#### 11.8.1 Python SDK

```python
# Installation
pip install alea

# Usage
from alea import AleaClient

client = AleaClient(api_key="...")

# Get outage forecast
forecast = client.outages.forecast(country="NG", horizon_hours=24)
for zone in forecast.zones:
    print(f"{zone.name}: {zone.probability:.0%}")

# Run what-if scenario
result = client.whatif.solve(
    demand_growth=0.06,
    coal_eaf=0.45,
    carbon_price=150,
)
print(f"Total cost: ${result.total_cost/1e9:.2f}B")

# Stream live updates
for event in client.stream.subscribe("outages", country="NG"):
    print(event)
```

#### 11.8.2 R SDK

```r
# Installation
install.packages("alea")

# Usage
library(alea)
client <- alea_client(api_key = "...")
forecast <- client$outages$forecast(country = "NG", horizon_hours = 24)
plot(forecast)
```

#### 11.8.3 JavaScript/TypeScript SDK

```typescript
import { AleaClient } from '@alea/sdk';

const client = new AleaClient({ apiKey: '...' });

const forecast = await client.outages.forecast({
  country: 'NG',
  horizonHours: 24,
});

forecast.zones.forEach(zone => {
  console.log(`${zone.name}: ${(zone.probability * 100).toFixed(0)}%`);
});
```

#### 11.8.4 Java SDK

```java
AleaClient client = new AleaClient.Builder()
    .apiKey("...")
    .build();

OutageForecast forecast = client.outages()
    .forecast("NG", 24);
```

---

### 12. A9 — Bulk Data Portal

#### 12.9.1 Design Rationale

Researchers, analysts, and businesses need **bulk data downloads** for offline analysis. The portal provides versioned, citable datasets with clear licences.

#### 12.9.2 Dataset Catalogue

| Dataset | Format | Update | Licence | Size |
|---|---|---|---|---|
| Grid topology (all Africa) | GeoJSON, Parquet | Monthly | ODbL | ~500 MB |
| Power plants | CSV, Parquet | Weekly | CC BY 4.0 | ~50 MB |
| Renewable profiles (hourly) | NetCDF, Parquet | Annual | CC BY 4.0 | ~50 GB |
| Demand profiles | CSV, Parquet | Monthly | CC BY 4.0 | ~10 GB |
| Outage history (VIIRS) | CSV, Parquet | Daily | CC BY 4.0 | ~20 GB |
| Price projections | CSV, Parquet | Quarterly | CC BY 4.0 | ~5 GB |
| Climate scenarios (CMIP6) | NetCDF | Annual | CC BY 4.0 | ~200 GB |
| Country statistics | CSV | Monthly | CC BY 4.0 | ~100 MB |

#### 12.9.3 Download Mechanism

Datasets are stored in S3-compatible object storage. Downloads are served via **signed URLs** with time-limited access:

```json
// GET /v1/datasets/power-plants-2026-10/download
{
  "download_url": "https://data.alea.africa/power-plants-2026-10.parquet?X-Amz-Signature=...",
  "expires_at": "2026-10-11T15:23:00Z",
  "size_bytes": 52428800,
  "sha256": "abc123...",
  "format": "parquet"
}
```

Bulk downloads (e.g., the full renewable profiles dataset) use **BitTorrent** for efficient distribution, with a `.torrent` file provided.

---

### 13. A10 — Webhooks

#### 13.10.1 Design Rationale

Businesses want to **react** to ALEA events without polling. Webhooks push events to their systems when they occur.

#### 13.10.2 Webhook Events

| Event | Trigger | Payload |
|---|---|---|
| `outage.forecast.high_risk` | Outage probability > threshold | Zone, probability, confidence |
| `outage.event.detected` | VIIRS or crowdsourced outage detected | Location, time, cause |
| `price.threshold.crossed` | Price crosses configured threshold | Country, price, threshold |
| `signal.new` | New signal matching filter | Signal details |
| `signal.confirmed` | Signal confirmed by reviewer | Signal details |
| `scenario.completed` | Scenario solve completed | Scenario ID, results URL |
| `report.published` | New report published | Type, date, URL |

#### 13.10.3 Webhook Configuration

```json
// POST /v1/webhooks
{
  "url": "https://mycompany.com/alea-webhook",
  "events": ["outage.forecast.high_risk", "price.threshold.crossed"],
  "filters": {
    "countries": ["NG", "KE"],
    "outage_probability_threshold": 0.7,
    "price_threshold": {"currency": "USD", "value": 100}
  },
  "secret": "whsec_...",
  "active": true
}
```

#### 13.10.4 Webhook Delivery

Webhooks are delivered with **retry and backoff**. Failed deliveries retry 5 times over 24 hours. Every webhook includes a signature header:

```
X-ALEA-Signature: t=1728654000,v1=abc123...
```

The signature is computed as `HMAC-SHA256(secret, timestamp + "." + payload)`. Clients must verify it.

---

### 14. A11 — Email & RSS

#### 14.11.1 Email Newsletter Service

| Newsletter | Frequency | Content |
|---|---|---|
| **Daily Brief** | Daily 06:00 | Top signals, outage forecasts, price movements |
| **Weekly Digest** | Monday 06:00 | Deep dives, analysis, interviews |
| **Monthly Report** | 1st of month | Comprehensive market and policy review |
| **Country Edition** | Weekly | Per-country edition (55 available) |
| **Sector Edition** | Bi-weekly | Solar, wind, hydro, gas, mining editions |

#### 14.11.2 RSS Feeds

| Feed | URL | Content |
|---|---|---|
| All signals | `/rss/signals.xml` | All extracted signals |
| Outages | `/rss/outages.xml` | Outage events |
| Investment | `/rss/investment.xml` | Investment signals |
| Reports | `/rss/reports.xml` | New reports |

---

### 15. A12 — Spreadsheet & BI Connectors

#### 15.12.1 Google Sheets Add-on

Users can pull ALEA data directly into Google Sheets:

```
=ALEA_FORECAST("NG", "outage", "2026-10-12", 24)
=ALEA_PRICE("ZA", "2026-10-12")
=ALEA_SIGNALS("outage_event", "NG", "2026-10-01", "2026-10-11")
```

#### 15.12.2 Excel Plugin

Similar functions for Excel:

```
=ALEA.FORECAST("NG", "outage", "2026-10-12", 24)
=ALEA.PRICE("ZA", "2026-10-12")
```

#### 15.12.3 Power BI Connector

A custom Power BI connector that pulls ALEA data via the REST API. Published in the Power BI marketplace.

#### 15.12.4 Tableau Connector

A Web Data Connector (WDC) for Tableau.

---

### 16. A13 — GIS Plugins

#### 16.13.1 QGIS Plugin

A QGIS plugin for loading ALEA spatial data:

- Grid topology
- Generation assets
- Renewable resource layers
- Outage zones
- Scenario results as raster/vector layers

#### 16.13.2 ArcGIS Plugin

Similar capabilities for ArcGIS Pro.

---

## Part III: Internal Interfaces

### 17. Layer-to-Layer Interfaces

ALEA's six layers communicate through **well-defined contracts**. Each layer exposes its outputs as **artefacts** (files, database records, or message queue topics) that the next layer consumes.

#### 17.1 B1 — Layer 1 → Layer 2 (Planning → Sector)

**Interface**: The planning model produces a **network snapshot** in NetCDF format. The sector layer consumes this as its starting point.

**Contract**:

```yaml
# resources/network_snapshot.yaml
format: netcdf
path: "resources/networks/planning_{year}.nc"
schema:
  buses: [...]
  generators: [...]
  lines: [...]
  loads: [...]
  stores: [...]
required_attributes:
  - carrier
  - p_nom
  - marginal_cost
  - capital_cost
validation:
  - all buses connected
  - no negative capacities
  - all generators have carrier
```

#### 17.2 B2 — Layer 2 → Layer 3 (Sector → Market)

**Interface**: The sector-coupled network produces **marginal costs** by node and time, which the market layer uses as supply bids.

**Contract**:

```python
# The sector layer writes:
n.export_to_netcdf("resources/networks/sector_{year}.nc")

# The market layer reads:
n = pypsa.Network("resources/networks/sector_{year}.nc")
marginal_costs = n.buses_t.marginal_price  # Used as supply bids
```

#### 17.3 B3 — Layer 3 → Layer 4 (Market → Predictive)

**Interface**: The market layer produces **price time series**; the predictive layer produces **outage probabilities**. They are combined in the resilience engine.

**Contract**:

```yaml
# Message queue topic: alea.market.prices
messages:
  - country: "NG"
    timestamp: "2026-10-11T14:00:00Z"
    price_usd_mwh: 87.50
    market: "day_ahead"

# Message queue topic: alea.outages.forecast
messages:
  - country: "NG"
    zone: "Lagos Island"
    timestamp: "2026-10-11T14:00:00Z"
    probability: 0.82
    confidence: [0.71, 0.91]
```

#### 17.4 B4 — Layer 4 → Layer 5 (Predictive → What-If)

**Interface**: The predictive layer produces **outage forecasts** and **loss metrics**; the what-if engine consumes these as scenario parameters.

#### 17.5 B5 — Layer 5 → Layer 6 (What-If → Reporting)

**Interface**: The what-if engine produces **scenario results**; the reporting layer consumes these to generate periodic reports.

#### 17.6 B6 — Cross-Layer: Message Queue

**Technology**: Apache Kafka (production), Redis Streams (development)

**Topics**:

| Topic | Producer | Consumer | Schema |
|---|---|---|---|
| `alea.data.grid` | Data pipeline | All layers | Avro |
| `alea.data.generation` | Data pipeline | All layers | Avro |
| `alea.data.renewables` | Data pipeline | Layers 1–3 | Avro |
| `alea.data.demand` | Data pipeline | Layers 1–3 | Avro |
| `alea.market.prices` | Layer 3 | Layers 4–6 | Avro |
| `alea.outages.forecast` | Layer 4 | Layers 5–6 | Avro |
| `alea.signals.raw` | Ingestion | Extraction | JSON |
| `alea.signals.extracted` | Extraction | Review | JSON |
| `alea.signals.confirmed` | Review | Model updater | JSON |
| `alea.scenario.completed` | Layer 5 | Reporting | JSON |
| `alea.report.published` | Reporting | Distribution | JSON |

**Why Kafka**: Provides durable, ordered, replayable message streams. Supports multiple consumers per topic. Enables event-driven architecture.

#### 17.7 B7 — Cross-Layer: Shared Database Schemas

**Technology**: PostgreSQL (metadata), TimescaleDB (time series), PostGIS (spatial)

**Core schemas**:

```sql
-- Countries
CREATE TABLE countries (
    iso CHAR(2) PRIMARY KEY,
    name TEXT NOT NULL,
    population BIGINT,
    gdp_usd NUMERIC,
    power_pool CHAR(8),
    data_completeness NUMERIC CHECK (data_completeness BETWEEN 0 AND 1)
);

-- Generators
CREATE TABLE generators (
    id UUID PRIMARY KEY,
    country_iso CHAR(2) REFERENCES countries(iso),
    name TEXT NOT NULL,
    carrier TEXT NOT NULL,
    capacity_mw NUMERIC NOT NULL,
    latitude NUMERIC,
    longitude NUMERIC,
    commissioned DATE,
    status TEXT,
    data_source TEXT,
    confidence NUMERIC
);

-- Time series (TimescaleDB hypertable)
CREATE TABLE price_forecasts (
    time TIMESTAMPTZ NOT NULL,
    country_iso CHAR(2) NOT NULL,
    scenario_id UUID NOT NULL,
    price_usd_mwh NUMERIC,
    confidence_lower NUMERIC,
    confidence_upper NUMERIC
);
SELECT create_hypertable('price_forecasts', 'time');

-- Signals
CREATE TABLE signals (
    id UUID PRIMARY KEY,
    signal_type TEXT NOT NULL,
    confidence NUMERIC,
    country_iso CHAR(2),
    event_date TIMESTAMPTZ,
    description TEXT,
    source_url TEXT,
    source_name TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 17.8 B8 — Cross-Layer: Model Artefact Registry

**Technology**: MLflow (model registry), DVC (data version control)

**Purpose**: Every model and dataset has a versioned, reproducible identifier. Every prediction records which model and data versions produced it.

**Artefact schema**:

```yaml
artefact:
  id: "outage_model_NG_v2.3"
  type: "model"
  framework: "xgboost"
  training_data: "outage_history_NG_v1.8"
  training_date: "2026-09-15"
  metrics:
    auc: 0.847
    precision: 0.91
    recall: 0.88
  hash: "sha256:abc123..."
  path: "s3://alea-models/outages/NG/v2.3/"
```

---

## Part IV: Inbound Interfaces

### 18. C1 — Source Connectors

Each source connector implements a **common interface** and writes to the `alea.signals.raw` Kafka topic. Connectors are **pluggable** — new sources can be added without modifying the core pipeline.

**Connector contract**:

```python
class SourceConnector(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...
    
    @property
    @abstractmethod
    def source_type(self) -> str: ...  # "news", "tender", "social", "institutional", "investment"
    
    @property
    @abstractmethod
    def poll_interval_seconds(self) -> int: ...
    
    @abstractmethod
    def fetch_new(self, since: datetime) -> List[RawDocument]: ...
    
    @abstractmethod
    def health_check(self) -> dict: ...
```

### 19. C2 — Crowdsourcing Endpoints

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/crowdsource/outage` | POST | Report an outage | None (rate-limited) |
| `/crowdsource/validation` | POST | Validate a VIIRS-detected outage | None |
| `/crowdsource/photo` | POST | Upload a photo (e.g., damaged equipment) | None |
| `/crowdsource/feedback` | POST | Report a data error | None |

**Anti-abuse**: Rate limiting by IP + device fingerprint. Reputation scoring for repeat contributors. Manual review for high-impact reports.

### 20. C3 — Human Review Interface

A dedicated web interface for analysts to review, confirm, reject, or edit extracted signals.

**Routes**:

```
/review/queue              → Priority-sorted review queue
/review/signal/[id]        → Signal detail with source document
/review/batch              → Batch review interface
/review/analytics          → Reviewer performance metrics
```

**Keyboard shortcuts**: For efficiency, reviewers can process signals entirely via keyboard (`j`/`k` to navigate, `c` to confirm, `r` to reject, `e` to edit).

### 21. C4 — Partner Data Exchange

For institutional partners (AUDA-NEPAD, AFREC, power pools, national utilities), ALEA provides a **secure data exchange interface**:

- **SFTP** for bulk data transfers
- **API keys** with elevated scopes for programmatic access
- **Data sharing agreements** with clear terms
- **Provenance tracking** for partner-supplied data

---

## Part V: Platform Interfaces

### 22. D1 — Authentication & Authorisation

**Authentication**:

| Method | Use Case | Token Lifetime |
|---|---|---|
| **API Key** | Server-to-server, scripts | Long-lived (rotatable) |
| **OAuth 2.0** | Third-party apps, user context | Access: 1h; Refresh: 30d |
| **JWT** | Session tokens for web/mobile | 15 min |
| **Magic Link** | Passwordless login for non-technical users | 15 min |

**Authorisation**: Role-Based Access Control (RBAC) with fine-grained scopes.

| Role | Scopes |
|---|---|
| `anonymous` | `public:read` |
| `researcher` | `public:read`, `forecasts:read`, `data:download` |
| `professional` | All researcher scopes + `scenarios:write`, `reports:read` |
| `enterprise` | All professional scopes + `whatif:write`, `webhooks:write` |
| `admin` | All scopes + `signals:review`, `models:manage`, `users:manage` |

### 23. D2 — Rate Limiting & Quotas

**Technology**: Redis-based token bucket with sliding window.

**Policies**:

```yaml
rate_limits:
  anonymous:
    requests_per_hour: 60
    burst: 10
    concurrent: 2
  researcher:
    requests_per_hour: 10000
    burst: 100
    concurrent: 10
  professional:
    requests_per_hour: 100000
    burst: 500
    concurrent: 50
  enterprise:
    requests_per_hour: 1000000
    burst: 5000
    concurrent: 200
```

**Quota enforcement**: Separate from rate limiting. Monthly quotas apply to expensive operations (scenario solves, bulk downloads, what-if runs).

### 24. D3 — Observability & Tracing

Every request is instrumented with **OpenTelemetry**:

- **Traces**: Distributed tracing across microservices
- **Metrics**: Prometheus metrics for latency, throughput, errors
- **Logs**: Structured JSON logs with request IDs
- **Dashboards**: Grafana dashboards for operational monitoring
- **Alerts**: PagerDuty integration for critical incidents

### 25. D4 — Job Scheduling & Orchestration

- **Snakemake** for data pipeline orchestration
- **APScheduler** for periodic reports and scans
- **Celery** for long-running tasks (scenario solves, bulk operations)
- **Airflow** (optional, for enterprise deployments) for complex workflows

---

## Part VI: Administrative Interfaces

### 26. E1 — Admin Console

A restricted web interface for platform administrators.

**Routes**:

```
/admin                     → Overview dashboard
/admin/users               → User management
/admin/api-keys            → API key management
/admin/models              → Model registry
/admin/data-sources        → Source connector management
/admin/review              → Signal review queue
/admin/scenarios           → Scenario management
/admin/jobs                → Job queue monitoring
/admin/logs                → Log explorer
/admin/health              → System health
```

### 27. E2 — Model Management

Administrators can:

- Register new models (with version, metrics, hash)
- Promote models from staging to production
- Roll back to previous versions
- Inspect model performance over time
- Trigger retraining

### 28. E3 — User Management

Administrators can:

- Create, edit, deactivate users
- Assign roles and scopes
- Issue and revoke API keys
- View usage analytics per user
- Manage organisation accounts

---

## Part VII: Interface Governance

### 29. F1 — Versioning & Deprecation

**API versioning**: URL path (`/v1/`, `/v2/`). Breaking changes increment major version.

**Deprecation policy**:
1. Deprecation announced via `Deprecation` header
2. 6-month grace period
3. `Sunset` header indicates removal date
4. Migration guide published
5. Automated email to affected API key holders

**SDK versioning**: Semantic versioning (`MAJOR.MINOR.PATCH`). SDKs track API version.

**Dataset versioning**: Datasets are versioned by date (`power-plants-2026-10`). Older versions remain available for 24 months.

### 30. F2 — Documentation & Discovery

- **OpenAPI 3.1** specification for REST API
- **GraphQL schema** with introspection
- **AsyncAPI** specification for WebSocket and webhooks
- **Interactive docs** at `https://docs.alea.africa`
- **Code samples** in Python, R, JavaScript, Java, cURL
- **Postman collection** for quick testing
- **Status page** at `https://status.alea.africa`

### 31. F3 — Testing & Contract Validation

**Contract testing**: All internal layer interfaces are validated with **Pact** contract tests. Producers and consumers must agree on the contract before deployment.

**API testing**:
- Unit tests for each endpoint
- Integration tests for common workflows
- Load tests for performance requirements
- Fuzz tests for input validation
- Security tests for authentication and authorisation

**Schema validation**: All API responses are validated against JSON Schema. Schema changes require version bumps.

---

## Part VIII: Interface Summary Matrix

| Interface | Type | Audience | Auth | Rate Limit | Versioning |
|---|---|---|---|---|---|
| REST API | External | Developers | Key/OAuth | Tiered | URL |
| GraphQL API | External | Developers | Key/OAuth | Tiered | Schema |
| WebSocket | External | Real-time apps | Key | Tiered | URL |
| Web Dashboard | External | All | Session | N/A | N/A |
| Mobile App | External | Citizens, SMEs | Session | N/A | Store |
| WhatsApp Bot | External | Citizens | Phone | Per-user | Implicit |
| USSD | External | Feature phones | Phone | Per-session | Implicit |
| SMS | External | All mobile | Phone | Per-user | Implicit |
| Voice | External | Low-literacy | Phone | Per-call | Implicit |
| Widgets | External | Journalists | None | CDN | URL |
| SDKs | External | Developers | Key | Tiered | SemVer |
| Data Portal | External | Researchers | Tiered | Monthly quota | Date |
| Webhooks | External | Businesses | Signed | N/A | URL |
| Email | External | All | Opt-in | N/A | N/A |
| RSS | External | Power users | None | None | N/A |
| Spreadsheet | External | Analysts | OAuth | Tiered | Add-on |
| BI Connectors | External | Analysts | OAuth | Tiered | Add-on |
| GIS Plugins | External | GIS pros | OAuth | Tiered | Plugin |
| Layer 1→2 | Internal | Layers | N/A | N/A | Hash |
| Layer 2→3 | Internal | Layers | N/A | N/A | Hash |
| Layer 3→4 | Internal | Layers | N/A | N/A | Hash |
| Layer 4→5 | Internal | Layers | N/A | N/A | Hash |
| Layer 5→6 | Internal | Layers | N/A | N/A | Hash |
| Kafka | Internal | Services | mTLS | N/A | Topic |
| Database | Internal | Services | mTLS | N/A | Migration |
| MLflow | Internal | ML ops | mTLS | N/A | SemVer |
| Source Connectors | Inbound | External sources | Varies | Varies | Interface |
| Crowdsourcing | Inbound | Citizens | None | IP | URL |
| Review Interface | Inbound | Analysts | Session | N/A | N/A |
| Partner Exchange | Inbound | Institutions | mTLS | N/A | Agreement |
| Auth | Platform | All | N/A | N/A | URL |
| Rate Limiting | Platform | All | N/A | N/A | N/A |
| Observability | Platform | Ops | N/A | N/A | N/A |
| Scheduling | Platform | Ops | N/A | N/A | N/A |
| Admin Console | Admin | Admins | Session | N/A | URL |

---

## Part IX: Conclusion

This specification defines the **complete interface surface** of ALEA — the 13 external interfaces, 8 internal layer interfaces, 4 inbound interfaces, 4 platform interfaces, 3 administrative interfaces, and 3 governance interfaces that together constitute the platform's connection to its users, its data sources, and itself.

The interfaces are designed around six principles: **progressive disclosure**, **cross-channel consistency**, **explicit uncertainty**, **provenance by default**, **open by default**, and **observability everywhere**. They serve twenty user archetypes across eighteen delivery channels, from a farmer in Malawi using USSD to a sovereign wealth fund using the Enterprise API.

The specification is intentionally **implementation-ready**. Each endpoint, schema, and contract is defined with enough precision that an intermediate developer can implement it without further clarification. Where decisions remain open (e.g., the specific model architecture for a given prediction), the specification defines the **interface contract** that any implementation must satisfy, leaving the implementation details to the development team.

The result is a platform whose interfaces are not merely functional but **strategic** — they are the mechanism by which ALEA becomes the reference energy intelligence platform for Africa, usable by everyone, from anywhere, on any device.