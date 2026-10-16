# Social Media Monitoring in the Capability Matrix: Honest Assessment

## Short Answer

**Yes — but only thinly, and not at the depth the platform actually requires.**

Social media monitoring appears in three places in the matrix I produced, each as a single row:

| Location | Capability | Maturity |
|---|---|---|
| Domain 1: Data & Ingestion | "Real-time streaming connectors (X/Twitter, WebSocket feeds)" | L3 |
| Domain 1: Data & Ingestion | "Crowdsourced outage reporting (WhatsApp, USSD, SMS, app)" | L4 |
| Domain 11: Intelligence Scanning | "Social media monitoring (X, Facebook, LinkedIn)" | L3 |

That is **not enough**. Social media monitoring for outage detection, cause attribution, and severity assessment is one of the platform's most distinctive capabilities, and it deserves its own sub-domain with full coverage scoring. The current treatment conflates three different things — passive monitoring, active crowdsourcing, and signal extraction — into two rows that don't do justice to the analytical depth required.

---

## What's Missing

To be a genuinely comprehensive capability, social media monitoring for outages must cover:

### 1. African Platform Coverage

The current matrix names only X, Facebook, and LinkedIn. But Africa's social media landscape is different:

| Platform | Regional Dominance | Currently in Matrix? |
|---|---|---|
| **WhatsApp** | Dominant messaging platform across Africa (public groups used for outage reports) | ❌ Not enumerated |
| **X (Twitter)** | Important for journalists, utilities, policy community | ✅ |
| **Facebook** | Large user base; public groups and pages | ✅ |
| **Telegram** | Used in some countries (Ethiopia, Nigeria) | ❌ |
| **LinkedIn** | Professional commentary, less for outages | ✅ |
| **Nairaland** (Nigeria) | Country-specific forum with active outage threads | ❌ |
| **r/southafrica, r/kenya, etc.** | Reddit communities with outage discussion | ❌ |
| **YouTube** | Video evidence of outages, transformer explosions | ❌ |
| **TikTok** | Growing, but rare for outage reporting | ❌ |
| **Local forums** | Country-specific (Kenya Talk, Nairaland, GhanaWeb) | ❌ |

### 2. Language Coverage

Africa has 2,000+ languages. The platform must handle at minimum:

| Language | Speakers | Currently in Matrix? |
|---|---|---|
| English | ~700M | ✅ |
| French | ~300M | ✅ |
| Portuguese | ~30M | ✅ |
| Arabic | ~150M | ✅ |
| Swahili | ~200M | ❌ Not enumerated |
| Hausa | ~80M | ❌ |
| Yoruba | ~45M | ❌ |
| Amharic | ~35M | ❌ |
| Zulu | ~28M | ❌ |
| Oromo | ~35M | ❌ |
| Nigerian Pidgin | ~120M | ❌ |
| Afrikaans | ~7M | ❌ |

### 3. Full Analytical Pipeline

The current matrix collapses the entire social media pipeline into two L3–L4 rows. The actual pipeline has **twelve distinct capabilities**, each with its own maturity target:

| # | Capability | Current | Target |
|---|---|---|---|
| 1 | Real-time streaming ingestion (per platform) | L3 | L4 |
| 2 | Search-based retrieval with geolocation filters | L3 | L4 |
| 3 | Multilingual NLP (12+ African languages) | L2 | L4 |
| 4 | Outage classification (binary) | L4 | L5 |
| 5 | Cause classification (weather, vandalism, equipment, load shedding) | L3 | L4 |
| 6 | Severity classification (minor, local, widespread) | L2 | L4 |
| 7 | Geolocation inference (text, profile, check-in, image) | L3 | L4 |
| 8 | Temporal aggregation and deduplication across posts | L3 | L4 |
| 9 | Corroboration scoring (multiple independent reports) | L2 | L4 |
| 10 | Bot detection and spam filtering | L2 | L4 |
| 11 | Misinformation detection and correction | L2 | L4 |
| 12 | Signal fusion with VIIRS, weather, and GridWatch | L3 | L4 |

---

## The Missing Sub-Domain

I propose adding a **new sub-domain within Domain 11 (Intelligence Scanning) or as its own Domain 19**:

### Domain 19: Social Media & Crowdsourced Outage Intelligence

| Capability | A | G | U | C | D | V | Overall |
|---|---|---|---|---|---|---|---|
| **Platform connectors** | | | | | | | |
| X/Twitter streaming and search | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Facebook public groups and pages | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| WhatsApp public group monitoring (opt-in) | L2 | L2 | L3 | L3 | L2 | L2 | **L2** |
| Telegram public channels | L2 | L2 | L2 | L2 | L2 | L2 | **L2** |
| Country-specific forums (Nairaland, Kenya Talk, GhanaWeb) | L2 | L3 | L3 | L2 | L2 | L2 | **L2** |
| Reddit African communities | L2 | L2 | L2 | L2 | L2 | L2 | **L2** |
| **Multilingual NLP** | | | | | | | |
| English, French, Portuguese, Arabic | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| Swahili, Hausa, Yoruba, Amharic | L3 | L3 | L3 | L2 | L3 | L2 | **L3** |
| Zulu, Oromo, Nigerian Pidgin | L2 | L2 | L2 | L2 | L2 | L1 | **L2** |
| **Classification** | | | | | | | |
| Outage detection (binary) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Cause attribution (weather, equipment, vandalism, load shedding) | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| Severity assessment (local, regional, widespread) | L3 | L3 | L3 | L3 | L3 | L3 | **L3** |
| **Geolocation** | | | | | | | |
| Text-based location extraction | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| User profile location inference | L3 | L3 | L3 | L2 | L3 | L2 | **L3** |
| Image-based location inference | L2 | L2 | L2 | L2 | L2 | L2 | **L2** |
| **Quality and trust** | | | | | | | |
| Bot detection | L3 | L3 | L3 | L2 | L3 | L2 | **L3** |
| Spam filtering | L4 | L4 | L4 | L3 | L4 | L3 | **L4** |
| Misinformation detection | L2 | L2 | L2 | L2 | L2 | L1 | **L2** |
| Corroboration scoring across posts | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| **Fusion** | | | | | | | |
| Fusion with VIIRS outage detection | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Fusion with weather data | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| Fusion with GridWatch ground truth | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Cross-platform corroboration | L3 | L3 | L3 | L2 | L3 | L3 | **L3** |
| **Active crowdsourcing** | | | | | | | |
| WhatsApp bot for user reports | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| USSD reporting | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| SMS reporting | L4 | L4 | L5 | L5 | L4 | L4 | **L4** |
| Mobile app reporting with photo | L3 | L3 | L4 | L5 | L3 | L3 | **L3** |
| Report verification workflow | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |
| **Delivery** | | | | | | | |
| Real-time outage map (heat map from social reports) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| Alert triggering (threshold-based) | L4 | L4 | L4 | L4 | L4 | L4 | **L4** |
| API access to social signals | L4 | L4 | L4 | L3 | L4 | L4 | **L4** |
| Journalist story alerts | L4 | L4 | L5 | L4 | L4 | L4 | **L4** |
| Utility operational dashboard integration | L3 | L3 | L4 | L3 | L3 | L3 | **L3** |

---

## Where Social Media Appears Across the Rest of the Matrix

Beyond the new sub-domain, social media intelligence must be threaded through the following domains:

### Domain 1: Data & Ingestion

| Capability | Should Include |
|---|---|
| Real-time streaming connectors | X/Twitter streaming API, Facebook Graph API, Telegram Bot API, WhatsApp Cloud API |
| Crowdsourced reporting | WhatsApp bot, USSD, SMS, mobile app — all already at L4 |

### Domain 8: Outage Prediction

| Capability | Should Include |
|---|---|
| Signal fusion | VIIRS + weather + social media + GridWatch → unified outage probability |
| Cause attribution | Weather + social media classification → cause-specific outage model |
| Real-time operational view | Social media signals + VIIRS → live outage map |

### Domain 11: Intelligence Scanning

The domain should split into three distinct pipelines:
- **News and media** (already L4)
- **Tender and procurement** (already L3)
- **Social media and crowdsourced** (new — L2–L4 after build)

### Domain 12: Reporting

| Report | Should Include |
|---|---|
| Daily report | Social media outage summary from previous 24h |
| Weekly report | Social vs. VIIRS vs. GridWatch comparison |
| Monthly report | Social media coverage statistics, language coverage, platform breakdown |

### Domain 18: Operations

| Capability | Should Include |
|---|---|
| Rate limiting | Per-platform API limits (X streaming is generous; Facebook is restrictive) |
| Terms of service compliance | Per-platform (X, Meta, Telegram, etc. all have different ToS) |
| Data retention | Social media posts have retention limits; PII must be managed |
| GDPR/POPIA compliance | Social media user data is subject to privacy laws |

---

## The GLISSA Precedent

The specification already cites GLISSA (GenAI-Augmented Framework for Real-time Situation Awareness of Power Infrastructure), validated in Uganda. GLISSA demonstrated:
- **Real-time ingestion** from X/Twitter for power disruption detection
- **LLM-based filtering** for relevance
- **Geolocation inference** from posts
- **Visualisation** of social signals over time

And Mixtral-8 achieved a **91% success rate** in flagging posts related to ongoing outages.

Yet the current capability matrix treats social media as a single L3 row. This is a significant understatement of both the platform's ambition and the analytical depth required to deliver it.

---

## Recommended Actions

| # | Action | Priority |
|---|---|---|
| 1 | Add **Domain 19: Social Media & Crowdsourced Outage Intelligence** with the full sub-matrix above | P0 |
| 2 | Expand Domain 1's social media rows to enumerate **per-platform** connectors (WhatsApp, Telegram, X, Facebook, forums) | P0 |
| 3 | Add **multilingual NLP** capability to Domain 11 with scoring across 12+ African languages | P1 |
| 4 | Add **signal fusion** (social + VIIRS + weather + GridWatch) to Domain 8 | P1 |
| 5 | Add **geolocation inference** as its own capability in Domain 11 | P1 |
| 6 | Add **bot detection, spam filtering, and misinformation detection** to Domain 11 | P1 |
| 7 | Add **cross-platform corroboration** as a capability | P2 |
| 8 | Add **per-platform ToS compliance** to Domain 15 (Security & Governance) | P2 |
| 9 | Add **social media outage statistics** to Domain 12 (Reporting) | P2 |
| 10 | Add **social media-specific rate limits** to Domain 18 (Operations) | P2 |

---

## Honest Conclusion

The capability matrix I produced **mentions** social media monitoring, but it does not **cover** it. Social media is:

- A **distinctive source of operational intelligence** for African grids, where traditional SCADA data is sparse.
- A **dominant communication channel** for outage reports, especially via WhatsApp.
- A **multilingual challenge** requiring handling of 12+ African languages.
- A **fusion problem**, not a standalone signal — it must be combined with VIIRS, weather, and ground truth.
- A **compliance-sensitive activity**, subject to platform-specific terms of service and data protection laws.

If Alea is to be the world's best energy intelligence platform for Africa, social media monitoring cannot be a footnote. It must be a first-class capability with full coverage scoring, dedicated engineering, and continuous validation. The matrix above is the specification for that capability.

The gap in the current matrix is a real finding — not a documentation error, but an indication that this capability deserves more analytical attention than it has received so far. Fixing it is a P0 item before the platform's next major release.