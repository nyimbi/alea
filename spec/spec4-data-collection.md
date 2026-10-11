# PyPSA-X Pan-African: Automated Data Collection & Intelligence Scanning Module

## Extension Specification for Continuous Data Acquisition, Signal Detection, and Model-Updating Intelligence

**Version**: 3.0 (Extension to v2.0 Product Specification)
**Status**: Draft for Developer Implementation
**Audience**: Intermediate Python developers with energy system modelling and data engineering experience
**Base Platform**: PyPSA-X Pan-African v2.0

---

## Part I: Purpose and Design Principles

### 1. Why Automated Intelligence Scanning Is Essential

Version 2.0 of the PyPSA-X specification defined a platform that consumes data from static sources—downloaded once, processed, and used to build models. That architecture is insufficient for a platform intended to be the **best in the world** for African energy system analysis. The African energy landscape changes continuously:

- **New investment proposals** are announced weekly (solar IPPs, gas plants, transmission corridors)
- **RFPs and tenders** are published across 200+ fragmented sources in 54 countries
- **Outages** occur daily, and news of them propagates through social media, utility announcements, and news articles
- **Policy changes**, **regulatory decisions**, and **fuel price adjustments** are announced with little notice
- **Financial close**, **commissioning**, and **cancellation** of projects alter the generation and transmission landscape

The platform must therefore **continuously scan, detect, extract, and integrate** new information—including indirect signals—into its models. This is not a "nice to have"; it is a **core capability** that determines whether the platform's outputs remain accurate between major data releases. The Africa Energy & Commodities Intelligence Workbench demonstrates that scattered public information can be converted into analyst-readable monitoring signals and evidence-backed briefs.

### 2. Design Principles

1. **Continuous, Not Periodic**: The scanning module runs continuously (or at high frequency, e.g., hourly), not in batch mode. It detects new information as it appears.
2. **Indirect Signals Matter**: Not all relevant information comes from official statistical releases. A news article about a power outage in Lagos, a tweet about a transformer explosion in Nairobi, or an RFP for a solar plant in Zambia are all signals that should update the model.
3. **Human-in-the-Loop**: Automated extraction is probabilistic. The module produces **candidate signals** that are reviewed, confirmed, or rejected by human analysts before being committed to the model.
4. **Provenance and Auditability**: Every signal must carry a source URL, timestamp, extraction confidence, and a chain of custody from raw data to model update.
5. **Modular and Extensible**: New sources (new news sites, new tender portals, new social media platforms) must be addable without modifying the core pipeline.
6. **Uncertainty-Aware**: Every extracted signal carries an uncertainty estimate. Model updates propagate this uncertainty.

### 3. Module Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 7: Intelligence Scanning & Automated Data Collection            │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Source Connectors                                              │   │
│  │  (News APIs, Tender Portals, Utility Sites, Social Media,      │   │
│  │   IFI Portals, Government Gazettes, RSS Feeds)                 │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│  ┌────────────────────────────▼────────────────────────────────────┐   │
│  │  Ingestion Layer                                                │   │
│  │  (Scheduling, Rate Limiting, Deduplication, Raw Storage)        │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│  ┌────────────────────────────▼────────────────────────────────────┐   │
│  │  Extraction & Enrichment Layer                                  │   │
│  │  (NLP, LLM-based classification, Entity Extraction,             │   │
│  │   Geolocation, Event Detection, Signal Scoring)                 │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│  ┌────────────────────────────▼────────────────────────────────────┐   │
│  │  Human Review & Validation Layer                                │   │
│  │  (Review Queue, Confirm/Reject, Edit, Provenance Tracking)      │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│  ┌────────────────────────────▼────────────────────────────────────┐   │
│  │  Model Integration Layer                                        │   │
│  │  (Update Generation Fleet, Transmission, Demand, Policy,        │   │
│  │   Trigger Re-solve, Notify Analysts)                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 6: Periodic Reporting & Intelligence                             │
│  Layer 5: What-If Scenario Engine                                       │
│  Layer 4: Outage Prediction & Resilience Analytics                      │
│  Layer 3: Market Simulation & Commercial Analytics                      │
│  Layer 2: Sector-Coupled Optimisation                                   │
│  Layer 1: PyPSA-Earth Planning Core                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this placement**: The scanning module sits **above** all analytical layers. It feeds data **downward** into Layers 1–6. It does not depend on any analytical output; it is a pure data acquisition and enrichment system that continuously monitors the external world.

---

## Part II: Source Connectors

### 4. Source Taxonomy

The scanning module shall connect to five categories of sources:

| Category | Examples | Signal Types | Update Frequency |
|---|---|---|---|
| **News & Media** | Reuters Africa, Bloomberg, Energy Monitor, The Electricity Hub, regional newspapers | Outages, investment announcements, policy changes, fuel prices | Continuous (RSS/API) |
| **Tender & Procurement** | AfDB, World Bank, TED, national e-procurement portals (Kenya eGP, Morocco Marchés Publics), utility portals (KPLC, ZESCO, KenGen) | RFPs, tenders, contract awards | Hourly |
| **Social Media** | X (Twitter), Facebook, LinkedIn, WhatsApp public groups | Outages, equipment failures, local energy issues | Continuous (streaming) |
| **Institutional & Regulatory** | AFREC, AUDA-NEPAD, NERSA, national regulators, government gazettes | Policy decisions, tariff adjustments, licence approvals | Daily |
| **Investment & Finance** | IJGlobal, Africa Energy Portal, AfDB project pipeline, IFC disclosures | Financial close, project pipeline updates, cancellations | Daily |

### 5. Source Connector Implementation

Each source connector shall implement a common interface:

```python
# scripts/scanning/connectors/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class RawDocument:
    """Universal container for raw scanned content."""
    source_id: str
    source_type: str          # "news", "tender", "social", "institutional", "investment"
    source_name: str          # "Reuters Africa", "AfDB Procurement", "X/Twitter"
    url: str
    title: str
    body: str
    published_at: datetime
    language: str             # ISO 639-1
    country_hints: List[str]  # ISO 3166-1 alpha-2 codes if detectable
    raw_metadata: dict        # Source-specific metadata

class SourceConnector(ABC):
    """Abstract base class for all source connectors."""

    @abstractmethod
    def fetch_new(self, since: datetime) -> List[RawDocument]:
        """Fetch documents published since the given timestamp."""
        pass

    @abstractmethod
    def health_check(self) -> dict:
        """Return connector health status."""
        pass
```

### 6. Specific Connectors

#### 6.1 News Connectors

```python
# scripts/scanning/connectors/news.py
import feedparser
import requests
from datetime import datetime

class RSSNewsConnector(SourceConnector):
    """Connector for RSS/Atom feeds from news sources."""

    FEEDS = {
        "reuters_africa": "https://feeds.reuters.com/reuters/AfricaNews",
        "the_electricity_hub": "https://theelectricityhub.com/feed/",
        "esi_africa": "https://www.esi-africa.com/feed/",
        "energy_monitor": "https://www.energymonitor.ai/feed/",
        "africa_energy_portal": "https://africa-energy-portal.org/rss.xml",
    }

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        documents = []
        for name, url in self.FEEDS.items():
            feed = feedparser.parse(url)
            for entry in feed.entries:
                published = datetime(*entry.published_parsed[:6])
                if published > since:
                    documents.append(RawDocument(
                        source_id=f"{name}_{entry.id}",
                        source_type="news",
                        source_name=name,
                        url=entry.link,
                        title=entry.title,
                        body=entry.get("summary", entry.get("description", "")),
                        published_at=published,
                        language="en",
                        country_hints=[],
                        raw_metadata={"tags": [t.term for t in entry.get("tags", [])]}
                    ))
        return documents

class NewsAPIConnector(SourceConnector):
    """Connector for NewsAPI.org (requires API key)."""

    def __init__(self, api_key: str, queries: List[str]):
        self.api_key = api_key
        self.queries = queries  # e.g., ["power outage Nigeria", "solar tender Kenya"]

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        documents = []
        for query in self.queries:
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": since.isoformat(),
                    "language": "en",
                    "sortBy": "publishedAt",
                    "apiKey": self.api_key
                }
            )
            for article in response.json().get("articles", []):
                documents.append(RawDocument(
                    source_id=f"newsapi_{hash(article['url'])}",
                    source_type="news",
                    source_name=article["source"]["name"],
                    url=article["url"],
                    title=article["title"],
                    body=article.get("content", ""),
                    published_at=datetime.fromisoformat(
                        article["publishedAt"].replace("Z", "+00:00")
                    ),
                    language="en",
                    country_hints=[],
                    raw_metadata={"query": query}
                ))
        return documents
```

#### 6.2 Tender & Procurement Connectors

```python
# scripts/scanning/connectors/tender.py
from playwright.sync_api import sync_playwright
import requests

class WorldBankProcurementConnector(SourceConnector):
    """
    Connector for World Bank Procurement Notices.
    Uses the keyless MCP endpoint (pipeworx-io/mcp-worldbank-procurement).
    """

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        response = requests.get(
            "https://search.worldbank.org/api/v3/procnotices",
            params={
                "format": "json",
                "rows": 100,
                "os": 0,
                "fct": "Procurement Notices",
                "countrycode_exact": "AF",  # Africa region
                "sort": "submission_deadline desc"
            }
        )
        documents = []
        for notice in response.json().get("procnotices", []):
            documents.append(RawDocument(
                source_id=f"wb_{notice['id']}",
                source_type="tender",
                source_name="World Bank Procurement",
                url=notice.get("url", ""),
                title=notice.get("project_name", ""),
                body=notice.get("notice_type", "") + " " + notice.get("description", ""),
                published_at=datetime.fromisoformat(notice["notice_date"]),
                language="en",
                country_hints=[notice.get("country_code", "")],
                raw_metadata=notice
            ))
        return documents

class KenyaTenderConnector(SourceConnector):
    """
    Connector for Kenya e-Procurement Portal and KPLC/KETRACO tenders.
    Uses Playwright for JavaScript-rendered pages.
    """

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        documents = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # KPLC planned interruptions
            page.goto("https://kplc.co.ke/category/view/50/planned-power-interruptions")
            page.wait_for_load_state("networkidle")
            for link in page.query_selector_all("a"):
                href = link.get_attribute("href")
                if href and "pdf" in href.lower():
                    documents.append(RawDocument(
                        source_id=f"kplc_{hash(href)}",
                        source_type="outage_notice",
                        source_name="KPLC Planned Interruptions",
                        url=href,
                        title=link.inner_text(),
                        body="",
                        published_at=datetime.now(),
                        language="en",
                        country_hints=["KE"],
                        raw_metadata={"type": "planned_interruption"}
                    ))
            browser.close()
        return documents
```

#### 6.3 Social Media Connectors

```python
# scripts/scanning/connectors/social.py
import tweepy
from datetime import datetime

class TwitterOutageConnector(SourceConnector):
    """
    Connector for X/Twitter outage-related posts.

    Based on GLISSA (GenAI-Augmented Framework for Real-time Situation
    Awareness of Power Infrastructure), validated in Uganda. The framework
    uses Twitter API-based data ingestion and LLM-driven filtering.
    """

    KEYWORDS = [
        "power outage", "no power", "blackout", "load shedding",
        "power cut", "electricity out", "grid failure",
        "transformer", "vandalism", "cable theft",
        # Country-specific terms
        "dumsor", "loadshedding", "coupure", "corte de luz",
        "stroomonderbreking", "kusagala kwa umeme"
    ]

    def __init__(self, bearer_token: str):
        self.client = tweepy.Client(bearer_token=bearer_token)

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        documents = []
        for keyword in self.KEYWORDS:
            tweets = self.client.search_recent_tweets(
                query=f"{keyword} -is:retweet lang:en",
                start_time=since,
                max_results=100,
                tweet_fields=["created_at", "geo", "public_metrics", "lang"]
            )
            for tweet in tweets.data or []:
                documents.append(RawDocument(
                    source_id=f"twitter_{tweet.id}",
                    source_type="social",
                    source_name="X/Twitter",
                    url=f"https://twitter.com/i/web/status/{tweet.id}",
                    title=tweet.text[:200],
                    body=tweet.text,
                    published_at=tweet.created_at,
                    language=tweet.lang or "en",
                    country_hints=self._infer_country(tweet),
                    raw_metadata={
                        "metrics": tweet.public_metrics,
                        "geo": tweet.geo
                    }
                ))
        return documents

    def _infer_country(self, tweet) -> List[str]:
        """Infer country from tweet text or geo."""
        # Simple keyword-based inference; LLM layer refines this
        country_map = {
            "nigeria": "NG", "lagos": "NG", "abuja": "NG",
            "kenya": "KE", "nairobi": "KE", "mombasa": "KE",
            "south africa": "ZA", "johannesburg": "ZA", "cape town": "ZA",
            "ghana": "GH", "accra": "GH",
            "uganda": "UG", "kampala": "UG",
            "tanzania": "TZ", "dar es salaam": "TZ",
        }
        text_lower = tweet.text.lower()
        return list(set(
            iso for keyword, iso in country_map.items()
            if keyword in text_lower
        ))
```

#### 6.4 Institutional & Investment Connectors

```python
# scripts/scanning/connectors/institutional.py
import requests
from bs4 import BeautifulSoup

class IJGlobalConnector(SourceConnector):
    """
    Connector for IJGlobal infrastructure finance data.

    IJGlobal provides detailed information on financial structure, pricing,
    bidders, key deal participants, and fundraising trends across 52,000+
    transactions and 39,000+ assets.
    """
    # Requires subscription; use API key if available
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://api.ijglobal.com/v1"

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        if not self.api_key:
            return []
        response = requests.get(
            f"{self.base_url}/deals",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={
                "region": "Africa",
                "sector": "Power,Renewables",
                "updated_since": since.isoformat(),
                "limit": 100
            }
        )
        documents = []
        for deal in response.json().get("deals", []):
            documents.append(RawDocument(
                source_id=f"ijglobal_{deal['id']}",
                source_type="investment",
                source_name="IJGlobal",
                url=deal.get("url", ""),
                title=deal.get("name", ""),
                body=deal.get("description", ""),
                published_at=datetime.fromisoformat(deal["updated_at"]),
                language="en",
                country_hints=[deal.get("country", "")],
                raw_metadata=deal
            ))
        return documents

class AfDBProjectConnector(SourceConnector):
    """Connector for AfDB project pipeline (MapAfrica platform)."""

    def fetch_new(self, since: datetime) -> List[RawDocument]:
        response = requests.get(
            "https://mapafrica.afdb.org/api/projects",
            params={
                "sector": "Energy",
                "status": "Approved,Implementation",
                "updated_since": since.isoformat()
            }
        )
        # Parse and return documents
        ...
```

---

## Part III: Ingestion Layer

### 7. Scheduling and Orchestration

The ingestion layer shall use **APScheduler** for continuous scheduling and **Redis** for deduplication and queue management.

```python
# scripts/scanning/ingestion/scheduler.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import redis
import json
import hashlib

class IngestionScheduler:
    def __init__(self, connectors: list, redis_client: redis.Redis):
        self.connectors = connectors
        self.redis = redis_client
        self.scheduler = BlockingScheduler()

    def start(self):
        for connector in self.connectors:
            self.scheduler.add_job(
                self._run_connector,
                IntervalTrigger(minutes=connector.poll_interval_minutes),
                args=[connector],
                id=f"connector_{connector.source_name}"
            )
        self.scheduler.start()

    def _run_connector(self, connector):
        since = self._get_last_run(connector.source_name)
        documents = connector.fetch_new(since)
        for doc in documents:
            doc_hash = self._hash_document(doc)
            if not self.redis.sismember("seen_documents", doc_hash):
                self.redis.rpush("raw_documents", json.dumps(doc.__dict__, default=str))
                self.redis.sadd("seen_documents", doc_hash)
        self._set_last_run(connector.source_name)

    def _hash_document(self, doc: RawDocument) -> str:
        """Create a stable hash for deduplication."""
        content = f"{doc.source_name}|{doc.url}|{doc.title}|{doc.published_at}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_last_run(self, source_name: str) -> datetime:
        ts = self.redis.get(f"last_run:{source_name}")
        return datetime.fromisoformat(ts.decode()) if ts else datetime(2025, 1, 1)

    def _set_last_run(self, source_name: str):
        self.redis.set(f"last_run:{source_name}", datetime.now().isoformat())
```

### 8. Deduplication Strategy

Deduplication operates at two levels:

1. **Exact hash deduplication**: Prevents the same document from being processed twice. Uses SHA-256 of source name, URL, title, and published timestamp.
2. **Near-duplicate detection**: Detects when the same event is reported by multiple sources. Uses MinHash/LSH (Locality-Sensitive Hashing) on document text. When near-duplicates are detected, the module keeps the **most detailed** document and annotates the others as corroborating sources.

```python
# scripts/scanning/ingestion/dedup.py
from datasketch import MinHash, MinHashLSH

class NearDuplicateDetector:
    def __init__(self, threshold=0.7, num_perm=128):
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self.counter = 0

    def add_document(self, doc_id: str, text: str) -> list:
        """Add a document and return IDs of near-duplicates."""
        mh = MinHash(num_perm=128)
        for shingle in self._shingles(text):
            mh.update(shingle.encode("utf-8"))
        duplicates = self.lsh.query(mh)
        self.lsh.insert(doc_id, mh)
        return duplicates

    def _shingles(self, text: str, k: int = 5) -> set:
        words = text.lower().split()
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}
```

---

## Part IV: Extraction & Enrichment Layer

### 9. NLP and LLM-Based Signal Extraction

The extraction layer converts raw unstructured text into structured **signals** that can update the model. It uses a hybrid approach: deterministic NLP for high-confidence extraction (regex, named entity recognition) and LLMs for classification, summarisation, and relationship extraction.

#### 9.1 Signal Taxonomy

| Signal Type | Description | Model Impact |
|---|---|---|
| **Outage Event** | Reported power outage in a specific location and time | Updates outage history; triggers outage prediction retraining |
| **Outage Cause** | Cause of an outage (weather, vandalism, equipment failure, load shedding) | Updates outage prediction features |
| **Generation Investment** | New generation project announced, financed, or commissioned | Updates generation fleet and capacity expansion options |
| **Generation Retirement** | Plant retirement or decommissioning announced | Updates generation fleet |
| **Transmission Investment** | New transmission line or substation announced or financed | Updates transmission topology |
| **Policy Change** | New tariff, subsidy, carbon price, or regulatory decision | Updates policy parameters |
| **Fuel Price Change** | Change in fuel prices (gasoline, diesel, natural gas, coal) | Updates fuel cost parameters |
| **Tender/RFP** | New procurement opportunity for energy infrastructure | Updates project pipeline and investment options |
| **Demand Signal** | New industrial load, electrification program, or demand growth signal | Updates demand projections |
| **Climate Event** | Drought, flood, extreme weather affecting energy infrastructure | Updates climate risk scenarios |

#### 9.2 LLM-Based Signal Extraction

```python
# scripts/scanning/extraction/llm_extractor.py
import openai
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Signal(BaseModel):
    """A structured signal extracted from a raw document."""
    signal_id: str
    signal_type: str          # From taxonomy above
    confidence: float         # 0.0 to 1.0
    source_document_id: str
    source_url: str
    source_name: str
    extracted_at: datetime
    # Signal-specific fields
    country_iso: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    event_date: Optional[datetime] = None
    capacity_mw: Optional[float] = None
    technology: Optional[str] = None
    fuel_type: Optional[str] = None
    investment_usd: Optional[float] = None
    description: str = ""
    evidence_quotes: List[str] = []
    # Uncertainty
    uncertainty_notes: str = ""
    requires_review: bool = True

class LLMSignalExtractor:
    """
    Extract structured signals from raw documents using LLMs.

    Based on GLISSA framework (Uganda validation) and
    Mixtral-8 validation (91% success rate for outage flagging).
    """

    SYSTEM_PROMPT = """You are an energy system analyst extracting structured signals
    from news articles, tender notices, and social media posts about African energy systems.

    For each document, identify whether it contains any of the following signal types:
    - outage_event: A power outage reported to have occurred
    - generation_investment: New generation capacity announced, financed, or commissioned
    - transmission_investment: New transmission infrastructure announced or financed
    - policy_change: Tariff, subsidy, or regulatory change
    - fuel_price_change: Change in fuel prices
    - tender_rfp: Procurement opportunity for energy infrastructure
    - demand_signal: New industrial load or electrification program
    - climate_event: Drought, flood, or extreme weather affecting energy

    For each signal found, extract:
    - signal_type (from list above)
    - country (ISO 3166-1 alpha-2)
    - region/state/province if mentioned
    - event_date (YYYY-MM-DD if mentioned)
    - capacity_mw (if generation/transmission)
    - technology (solar, wind, hydro, gas, coal, geothermal, biomass, nuclear, battery)
    - fuel_type (for thermal plants)
    - investment_usd (if mentioned)
    - description (1-2 sentences)
    - evidence_quotes (exact quotes supporting the extraction)
    - confidence (0.0-1.0)

    Return a JSON array of signals. If no signals are found, return [].
    Be conservative: only extract signals with clear evidence. Do not speculate.
    """

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def extract(self, document: RawDocument) -> List[Signal]:
        """Extract signals from a single document."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"""
                Source: {document.source_name}
                Title: {document.title}
                Date: {document.published_at.isoformat()}
                URL: {document.url}
                Body: {document.body[:4000]}
                """}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        raw_signals = json.loads(response.choices[0].message.content)
        signals = []
        for s in raw_signals.get("signals", []):
            signals.append(Signal(
                signal_id=f"{document.source_id}_{hash(str(s))}",
                source_document_id=document.source_id,
                source_url=document.url,
                source_name=document.source_name,
                extracted_at=datetime.now(),
                **s
            ))
        return signals
```

#### 9.3 Social Media Outage Detection

For social media, the extraction layer uses a specialised pipeline, following the GLISSA framework validated in Uganda:

```python
# scripts/scanning/extraction/social_outage.py
class SocialOutageDetector:
    """
    Detect outage events from social media posts.

    GLISSA framework: Twitter API ingestion + LLM filtering + geolocation
    inference + visualisation. Validated in Uganda for power disruption events.

    Mixtral-8: 91% success rate for flagging posts related to ongoing outages.
    """

    OUTAGE_PROMPT = """Analyse this social media post. Determine:
    1. Is it reporting a power outage? (yes/no)
    2. If yes, what is the location? (country, city, neighbourhood)
    3. What is the likely cause? (weather, vandalism, equipment failure,
       load shedding, unknown)
    4. What is the severity? (minor, moderate, widespread)
    5. Extract exact quotes supporting your assessment.

    Return JSON: {"is_outage": bool, "country": str, "city": str,
    "neighbourhood": str, "cause": str, "severity": str,
    "quotes": [str], "confidence": float}
    """

    def detect(self, document: RawDocument) -> Optional[Signal]:
        # LLM classification
        response = self._call_llm(document.body)
        if not response.get("is_outage"):
            return None
        # Geolocation inference
        location = self._geocode(
            response.get("city", ""),
            response.get("country", "")
        )
        return Signal(
            signal_id=f"outage_{document.source_id}",
            signal_type="outage_event",
            confidence=response.get("confidence", 0.5),
            source_document_id=document.source_id,
            source_url=document.url,
            source_name=document.source_name,
            extracted_at=datetime.now(),
            country_iso=self._to_iso(response.get("country")),
            region=response.get("city"),
            latitude=location[0] if location else None,
            longitude=location[1] if location else None,
            event_date=document.published_at,
            description=f"Outage reported in {response.get('city', 'unknown')}. "
                        f"Cause: {response.get('cause', 'unknown')}. "
                        f"Severity: {response.get('severity', 'unknown')}.",
            evidence_quotes=response.get("quotes", [])
        )
```

### 10. Signal Scoring and Prioritisation

Not all signals are equally important. The module computes a **priority score** for each signal:

```python
# scripts/scanning/extraction/scoring.py
def compute_priority(signal: Signal, context: dict) -> float:
    """
    Compute priority score (0-100) for a signal.

    Factors:
    - Confidence of extraction
    - Source reliability (Reuters > random blog)
    - Signal type impact (investment > outage)
    - Country data completeness (lower completeness = higher priority)
    - Novelty (first report of an event > corroborating report)
    """
    score = 0.0
    score += signal.confidence * 30
    score += SOURCE_RELIABILITY.get(signal.source_name, 0.5) * 20
    score += SIGNAL_TYPE_IMPACT.get(signal.signal_type, 0.5) * 25
    score += (1 - context.get("data_completeness", 0.5)) * 15
    score += (1 - context.get("corroboration_count", 0)) * 10
    return min(score, 100)
```

---

## Part V: Human Review & Validation Layer

### 11. Review Queue

All signals with `requires_review = True` (i.e., all signals by default) are placed in a review queue. The queue is accessible via the dashboard and API. Analysts can:

- **Confirm**: Accept the signal as accurate and commit it to the model.
- **Reject**: Mark the signal as false positive and exclude it.
- **Edit**: Correct extracted fields (country, capacity, technology, etc.) before confirming.
- **Merge**: Combine multiple signals referring to the same event.

```python
# scripts/scanning/review/queue.py
class ReviewQueue:
    def __init__(self, redis_client):
        self.redis = redis_client

    def push(self, signal: Signal):
        priority = compute_priority(signal, {})
        self.redis.zadd("review_queue", {json.dumps(signal.__dict__, default=str): priority})

    def get_pending(self, limit: int = 50) -> list:
        """Get highest-priority pending signals."""
        items = self.redis.zrevrange("review_queue", 0, limit - 1, withscores=True)
        return [
            {"signal": json.loads(item[0]), "priority": item[1]}
            for item in items
        ]

    def confirm(self, signal_id: str, analyst: str, edits: dict = None):
        """Confirm a signal and commit to model update queue."""
        signal = self._get_signal(signal_id)
        if edits:
            signal.update(edits)
        signal["status"] = "confirmed"
        signal["reviewed_by"] = analyst
        signal["reviewed_at"] = datetime.now().isoformat()
        self.redis.rpush("confirmed_signals", json.dumps(signal))
        self.redis.zrem("review_queue", json.dumps(signal))

    def reject(self, signal_id: str, analyst: str, reason: str):
        """Reject a signal."""
        ...
```

### 12. Model Integration

Confirmed signals are processed by the **Model Integration Layer**, which determines the appropriate model update:

```python
# scripts/scanning/integration/model_updater.py
class ModelUpdater:
    """Apply confirmed signals to the PyPSA-X model."""

    def apply_signal(self, signal: dict):
        handler = self._get_handler(signal["signal_type"])
        if handler:
            handler(signal)
            self._log_update(signal)

    def _get_handler(self, signal_type: str):
        handlers = {
            "generation_investment": self._apply_generation,
            "generation_retirement": self._apply_retirement,
            "transmission_investment": self._apply_transmission,
            "policy_change": self._apply_policy,
            "fuel_price_change": self._apply_fuel_price,
            "demand_signal": self._apply_demand,
            "outage_event": self._apply_outage,
        }
        return handlers.get(signal_type)

    def _apply_generation(self, signal: dict):
        """Add or update a generator in the network."""
        n = self._load_network()
        new_gen = {
            "name": signal.get("description", "")[:50],
            "bus": self._find_bus(signal["country_iso"], signal.get("region")),
            "carrier": signal["technology"],
            "p_nom": signal.get("capacity_mw", 0),
            "p_nom_extendable": False,
            "marginal_cost": 0,  # Set after fuel price lookup
            "capital_cost": 0,   # Set after cost lookup
        }
        n.add("Generator", **new_gen)
        n.export_to_netcdf(self._network_path())
        self._trigger_resolve()

    def _apply_outage(self, signal: dict):
        """Record outage event for model retraining."""
        outage_record = {
            "timestamp": signal["event_date"],
            "country_iso": signal["country_iso"],
            "latitude": signal.get("latitude"),
            "longitude": signal.get("longitude"),
            "cause": signal.get("description", ""),
            "source": signal["source_url"],
            "confidence": signal["confidence"],
        }
        self._append_outage_history(outage_record)
        self._flag_outage_model_retrain(signal["country_iso"])
```

---

## Part VI: Integration with Periodic Reporting

### 13. Intelligence Briefs in Daily Reports

The daily report (Section 18.1 of v2.0) shall include a new section: **"New Intelligence Signals"**, listing:

- Confirmed signals from the last 24 hours, grouped by type and country
- Pending signals awaiting review (with priority scores)
- Signals that triggered a model update (with link to updated results)
- Signals that were rejected (with analyst reason)

### 14. Scanning Module Health Dashboard

A dedicated dashboard view shows:

- Connector health (last successful fetch, error rates)
- Ingestion throughput (documents per hour, per source)
- Extraction accuracy (confirmed vs. rejected signals by source)
- Review queue depth and oldest pending signal
- Model update log (signals applied, model versions)

---

## Part VII: Implementation Roadmap

### 15. Phased Delivery

| Phase | Duration | Deliverable |
|---|---|---|
| **1. Core infrastructure** | 4 weeks | Redis, PostgreSQL, connector base class, scheduler |
| **2. News connectors** | 3 weeks | RSS feeds, NewsAPI, country-specific news sites |
| **3. Tender connectors** | 4 weeks | World Bank, AfDB, national portals (Kenya, Nigeria, South Africa, Morocco) |
| **4. Social media connectors** | 3 weeks | Twitter/X streaming, Facebook public posts |
| **5. LLM extraction pipeline** | 4 weeks | Signal taxonomy, LLM prompts, Pydantic models, scoring |
| **6. Human review interface** | 3 weeks | Review queue UI in dashboard, API endpoints |
| **7. Model integration** | 4 weeks | Signal-to-model-update handlers, re-solve triggers |
| **8. Testing & validation** | 3 weeks | Unit tests, integration tests, accuracy benchmarks |
| **9. Production deployment** | 2 weeks | Monitoring, alerting, documentation |

### 16. Key Performance Indicators

| Metric | Target | Measurement |
|---|---|---|
| **Connector uptime** | > 99% | Health check logs |
| **Ingestion latency** | < 5 minutes from publication | Timestamp comparison |
| **Extraction precision** | > 90% | Confirmed / (Confirmed + Rejected) |
| **Extraction recall** | > 85% | Confirmed / (Confirmed + Missed) |
| **Review queue depth** | < 100 pending at any time | Queue monitor |
| **Model update latency** | < 1 hour from confirmation to re-solve | Pipeline timestamps |
| **Signal coverage** | > 80% of significant events detected | Validation against known events |

---

## Part VIII: Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **LLM hallucination** | Medium | High | Require evidence quotes; human review before model commit |
| **Source coverage gaps** | High | Medium | Continuously add sources; use aggregation platforms (Jorpex, Deepbloo) |
| **Language barriers** | High | Medium | Use multilingual LLMs (GPT-4, Mixtral); prioritise French, Portuguese, Arabic |
| **Rate limiting** | Medium | Low | Implement backoff; use API keys where available |
| **Deduplication failures** | Medium | Medium | Combine exact hash and MinHash LSH; manual review |
| **Review bottleneck** | High | Medium | Prioritise by score; auto-confirm high-confidence signals |
| **Cost of LLM API calls** | Medium | Medium | Cache extractions; use smaller models for simple classification |

---

## Part IX: Conclusion

This specification defines the **Automated Data Collection & Intelligence Scanning Module** for PyPSA-X Pan-African. The module transforms the platform from a static modelling tool into a **living system** that continuously monitors the African energy landscape, extracts structured signals from unstructured information, and updates its models accordingly.

The module is grounded in **validated methodologies**:

- **GLISSA** (GenAI-Augmented Framework for Real-Time Situation Awareness of Power Infrastructure) for social media outage detection, validated in Uganda
- **Mixtral-8** LLM for outage flagging, achieving **91% success rate**
- **Africa Energy & Commodities Intelligence Workbench** for public-data monitoring and evidence-backed intelligence synthesis
- **Jorpex** and **Deepbloo** for tender aggregation across 50+ and 200+ sources respectively

By integrating this module, PyPSA-X Pan-African becomes not just a model but an **intelligence system**—one that knows what is happening in African energy systems as it happens, and that can update its predictions accordingly. This is the capability that separates a **world-class** platform from a good one.

---

**End of Specification**