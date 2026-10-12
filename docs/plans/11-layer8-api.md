# 11 — Layer 8: API and Delivery

**Track A/B/C shared.** One REST API, many delivery adapters (AD-7). Budget:
**five weeks**, after the layers whose outputs it serves.

Layer 8 exposes everything below it through one API. The specification lists
eighteen delivery channels; they are adapters over that API, not separate
systems.

---

## 1. What Layer 8 owns

| Concern | Module |
|---|---|
| REST API | `api.app`, `api.routes.*` |
| Authentication and tiers | `api.auth`, `api.tiers` |
| Response models | `api.views` |
| Caching and rate limiting | `api.middleware` |
| Delivery adapters | `api.adapters.*` |
| OpenAPI and docs | generated |

**No route computes.** Every route reads an artefact or calls a service below.

---

## 2. The specification's API section is a sketch

`spec4-base.md` §22–23 is explicitly flagged in this plan's memory as unreliable.
Three concrete defects:

### 2.1 A GET with a Pydantic body

```python
@app.get("/api/v1/outages/forecast")
async def get_outage_forecast(
    request: OutageForecastRequest,
    key: str = Depends(verify_key)
):
```

FastAPI does not bind a Pydantic model as a GET's query parameters this way — a
GET has no body, and a model parameter in a GET signature is treated as a query
parameter group only in specific configurations. The example as written does not
work.

**Fix:** GET endpoints take **scalar query parameters** with defaults; anything
with a complex body is a **POST**. The rule is mechanical and applied to every
route.

```python
@app.get("/api/v1/outages/forecast")
async def get_outage_forecast(
	country: CountryIso,
	grid_zone: str | None = None,
	horizon_hours: int = Query(default=24, ge=1, le=168),
	principal: Principal = Depends(require_tier(Tier.PUBLIC)),
) -> list[OutageForecastRow]: ...
```

### 2.2 Undefined names

```python
async def verify_key(api_key: str = Depends(api_key_header)):
    if api_key not in VALID_KEYS:
```

`VALID_KEYS` is never defined; `os` is used in `get_daily_report` without an
import. These are sketches, not code.

### 2.3 A synchronous solver call in an async route

```python
@app.post("/api/v1/whatif/solve")
async def solve_whatif(request: WhatIfRequest, key: str = Depends(verify_key)):
    engine = WhatIfEngine("results/base_network.nc")
    return engine.solve(params)
```

`engine.solve` runs for up to two hours and blocks the event loop. Every
long-running route is **enqueued**, not executed inline.

---

## 3. The API

### 3.1 The endpoint set

| Group | Endpoints | Tier |
|---|---|---|
| Planning | `/scenarios`, `/scenarios/{id}`, `/scenarios/{id}/results` | Public / Analyst |
| Market | `/prices`, `/capture-rates`, `/ppa-benchmarks` | Public / Analyst |
| Outages | `/outages/forecast`, `/outages/history`, `/outages/validate` | Public / Analyst |
| Maintenance | `/maintenance/predict` | Restricted |
| Losses | `/losses/decompose`, `/losses/tlens`, `/losses/mitigate` | Analyst |
| Resilience | `/resilience/metrics`, `/resilience/contingency` | Analyst |
| What-if | `/whatif/solve`, `/whatif/compare`, `/whatif/frontier` | Analyst |
| Reports | `/reports/{cadence}`, `/reports/{cadence}/{date}` | Public |
| Scanning | `/signals`, `/signals/{id}`, `/signals/review` | Restricted |
| System | `/health`, `/version`, `/runs/{run_id}` | Public |

### 3.2 The job pattern for anything slow

Anything that takes more than a few seconds is a job:

```
POST /api/v1/whatif/solve     -> 202 {job_id, status_url}
GET  /api/v1/jobs/{job_id}    -> {status, result_url | error}
GET  /api/v1/jobs/{job_id}/result -> the result
```

The job store is the same SQLite/artefact mechanism as the review queue: a
durable record, not in-memory state. **A job that dies with the process is a job
whose result the caller never learns**, and a two-hour solve that fails silently
is worse than one that fails loudly.

### 3.3 Response models

Every response is a pydantic model. Values that carry uncertainty expose it:

```python
# src/alea/api/views.py
class ValueOut(BaseModel):
	"""A number with its basis. The API does not serve bare numbers.

	The reporting layer's rule (09-layer6 §2) applies here too: a consumer that
	receives a number without its basis will publish it without its basis.
	"""
	value: float
	unit: str
	basis: ValueBasis
	uncertainty: float
	source_id: str
```

**This is the API's most important design decision.** An API that returns
`{"capacity_mw": 2100}` invites a dashboard that renders `2100 MW`. An API that
returns the basis invites a dashboard that renders `2100 MW ᵖ`.

---

## 4. Authentication and tiers

### 4.1 Tiers

| Tier | Access | Auth |
|---|---|---|
| Public | Reports, forecasts, prices at national resolution | API key, generous limit |
| Analyst | Losses, resilience, what-if, signals | API key, registered |
| Restricted | Maintenance, raw signals, review actions | API key + role |
| Internal | Pipeline triggers, admin | mTLS or network |

### 4.2 Keys

- Keys are **stored hashed** (argon2), never in plaintext. The specification's
  `VALID_KEYS` list of plaintext keys is a credential leak waiting to happen.
- Keys carry a tier and an optional expiry.
- **Rate limits are per key and per tier**, enforced in middleware, with the
  limit in the response headers so a client can back off.
- A key is revoked by marking it revoked; it is never deleted, so a request
  against a revoked key is distinguishable from one against a nonexistent key.

### 4.3 The delivery-adapter tiers

An adapter (WhatsApp, USSD) authenticates as a **service principal** with its
own key, and the end user is identified in the request. This is what allows
per-user rate limiting through a shared adapter credential.

---

## 5. Delivery adapters

The specification's eighteen channels. **They are adapters, and each is small.**
The list, with what each actually requires:

| Channel | Requires | Layer 8 work |
|---|---|---|
| Web dashboard | A frontend | Separate app, consumes API |
| Mobile app | A frontend | Separate app |
| WhatsApp bot | Meta Business API, templates | Adapter: format + webhook |
| USSD | A telco aggregator contract | Adapter: 182-char menu |
| SMS | An SMS gateway | Adapter: truncate + link |
| Email digests | SMTP | `reporting.distribute` |
| API | — | This layer |
| Embeddable widgets | CORS, a JS bundle | Small static asset |
| RSS | A feed serializer | Trivial |
| Podcast | Content production | Not engineering |
| YouTube | Content production | Not engineering |
| Slack/Teams | Webhooks | Adapter |
| Google Sheets add-on | Apps Script | Adapter |
| Excel plugin | Office JS | Adapter |
| QGIS plugin | Python plugin, OGC API | Adapter over `/topology` |
| Power BI / Tableau | OData or a connector | Adapter |
| Zapier / IFTTT | A public trigger API | Webhooks |
| Voice | A speech provider | Adapter |

**The engineering insight: a USSD menu and a terminal dashboard can read the same
endpoints.** That is the whole reason for AD-7. The adapter count is large; the
architecture question is small.

**Priority:** web dashboard, API, email, RSS, and the QGIS plugin cover the
professional users. WhatsApp/USSD/SMS cover the citizen users and are the
specification's differentiator. Voice, podcast, and video are content operations
that the platform enables rather than implements.

### 5.1 The one non-obvious adapter requirement

**USSD and SMS are 182 and 160 characters.** A forecast that renders as a table
must render as a sentence. That formatting is per-adapter and testable:

```python
def format_ussd_forecast(rows: list[OutageForecastRow]) -> str:
	"""Render a forecast for a 182-character USSD screen.

	Truncation is not acceptable: a truncated forecast is a wrong forecast.
	The adapter selects the top-N zones by probability and states how many were
	omitted, so the message is complete at its own resolution.
	"""
```

---

## 6. Caching and performance

| Response | Cache | Invalidation |
|---|---|---|
| Reports | Immutable once generated | Never (dated artefacts) |
| National prices | 1 hour | Time-based |
| Outage forecasts | 1 hour | Time-based |
| Historical outages | 1 day | New data |
| Topology | 1 day | New data |
| What-if results | Content-addressed | Never |

**Cache keys include the artefact checksum**, not just the endpoint. A cache
keyed on the URL alone serves a result computed against a previous network —
the same defect as Layer 5's cache key (08-layer5 §2.2).

Each lifetime is a field on `ApiConfig` (`cache_ttl_seconds` and its `_history`
and `_topology` siblings), read by the route that declares it. A route-local
constant is a lifetime an operator cannot move, which is how §6's four
lifetimes became two hard-coded numbers and two that existed only in this table.

**Topology is an endpoint, not only a table row.** §5 names the QGIS adapter as
one "over `/topology`", so `GET /api/v1/topology` serves the transmission lines
and their extent, public tier, keyed on the artefact checksum. It is not
paginated: a paginated geometry is a partially drawn grid, and a client
rendering page one shows a connected-looking network with its interconnectors
missing.

---

## 7. Module layout

```
src/alea/api/
├── __init__.py
├── app.py          # FastAPI application
├── auth.py         # keys, tiers, hashing
├── tiers.py        # tier definitions
├── views.py        # response models
├── middleware.py   # rate limiting, run id, logging
├── jobs.py         # durable job store
├── routes/
│   ├── planning.py
│   ├── market.py
│   ├── outages.py
│   ├── losses.py
│   ├── resilience.py
│   ├── whatif.py
│   ├── reports.py
│   ├── signals.py
│   └── system.py
└── adapters/
    ├── ussd.py
    ├── sms.py
    ├── whatsapp.py
    └── ...
```

---

## 8. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_no_get_with_body` | No GET route takes a Pydantic body | Add one; must fail |
| `test_no_blocking_solve_in_route` | No route calls a solver inline | Add one; must fail |
| `test_keys_stored_hashed` | No plaintext key in the store | Insert plaintext; must fail |
| `test_rate_limit_enforced` | Exceeding the limit returns 429 with headers | Disable limiter; must fail |
| `test_revoked_key_distinguishable` | Revoked ≠ nonexistent | Collapse them; must fail |
| `test_values_carry_basis` | No bare number in any response | Serve a float; must fail |
| `test_job_survives_restart` | A job's result is readable after a restart | Use in-memory store; must fail |
| `test_cache_key_includes_checksum` | Different artefact → different key | Drop checksum; must fail |
| `test_ussd_never_truncates` | USSD output ≤ 182 chars and complete | Truncate; must fail |
| `test_openapi_valid` | Generated OpenAPI validates | Break a model; must fail |

---

## 9. Exit criteria for Layer 8

| # | Criterion | Gate |
|---|---|---|
| 1 | Every endpoint in §3.1 implemented | Route inventory test |
| 2 | No GET takes a body; no route blocks | `test_no_get_with_body`, `test_no_blocking_solve_in_route` |
| 3 | Keys hashed, tiered, revocable | `test_keys_stored_hashed` |
| 4 | Rate limiting per key and tier | `test_rate_limit_enforced` |
| 5 | Every value carries its basis | `test_values_carry_basis` |
| 6 | Long jobs durable across restart | `test_job_survives_restart` |
| 7 | USSD and SMS adapters complete and bounded | `test_ussd_never_truncates` |
| 8 | OpenAPI generated and valid | `test_openapi_valid` |
| 9 | A route inventory matches the specification's endpoint table | Manual, once |
| 10 | Every gate canaried | `tests/ci/canaries` |

**Criterion 9 has a specific history worth avoiding.** An inventory of routes
read from source is not an inventory of routes the app serves — a wrapper class
around `include_router` once hid 1,074 of 1,080 routes from a static extractor,
and three different wrong counts were each internally consistent. The inventory
is read from `app.routes` at runtime and canaried against a route known to exist.
