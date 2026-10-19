# Product Specification: ALEA Financial Report Ingestion Module (FRIM)

**Version**: 1.0
**Status**: Implementation-ready specification
**Audience**: Intermediate Python developers with data-engineering and financial-reporting experience
**Companion modules**: `alea.prg` (Parameter Relationship Graph), `alea.frm` (Financial & Risk Model), PyPSA-Earth (optimisation engine)

---

## 1. Purpose and Scope

The Financial Report Ingestion Module (FRIM) is the **evidence layer** of the ALEA financial stack. Its single job is to convert the annual financial statements of African energy entities — utilities, independent power producers, holding companies — into a **normalised, provenance-tagged, machine-readable dataset** that the Financial & Risk Model (FRM) can use to **calibrate and challenge** its parameters.

The FRIM does **not**:

- Recompute the FRM's cash flow, debt schedule, or tax return
- Override FRM parameters directly
- Interpret the entity's strategy or produce narrative analysis
- Predict future financial performance

It **does**:

- Locate and retrieve the audited financial statements for each entity in the FRM universe
- Extract the income statement, balance sheet, and cash flow statement
- Normalise values across currency, fiscal year, accounting standard, and language
- Produce a **calibration report** that compares extracted evidence to FRM-assumed parameters
- Maintain a complete provenance chain from raw document to normalised value

The FRIM is used by:

- **FRM developers**, who need to validate their parameter assumptions against reality
- **Analysts**, who need to see how the FRM's assumptions compare to the entity's own reporting
- **Auditors**, who need to trace every FRM calibration back to a source document
- **Regulators**, who may want to see the FRM's cost-of-debt assumption compared to the utility's actual borrowing cost

---

## 2. Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Source Registry                                                            │
│  config/frm/report_sources.yaml                                             │
│  • entity_id, country, annual_report_url, fiscal_year_end, currency        │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Acquisition Layer                                                          │
│  • HTTP download of PDF/XBRL                                                │
│  • Object storage (MinIO/S3) with SHA-256 hash                             │
│  • Retrieval metadata                                                       │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ raw documents
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Extraction Layer                                                          │
│  • XBRL parser (Brel) for structured filings                               │
│  • PDF table extraction (pdfplumber, Camelot, Tabula)                      │
│  • OCR (OCRmyPDF) for scanned documents                                    │
│  • LLM fallback (Claude/GPT-4) for narrative sections                     │
│  • Fuzzy line-item matching against canonical taxonomy                    │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ extracted values with page and quote
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Normalisation Layer                                                       │
│  • Currency conversion to USD (annual average FX)                         │
│  • Fiscal year calendarisation                                             │
│  • Accounting standard alignment (IFRS baseline)                          │
│  • Language normalisation (EN/FR/PT synonyms)                              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ normalised values
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Calibration Layer                                                         │
│  • Compare extracted values to FRM parameters                              │
│  • Produce CalibrationFinding records                                     │
│  • Severity classification                                                 │
└──────────────────────────────┬──────────────────────────────────────────────────────────────┘
                               │ calibration findings
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Human Review                                                              │
│  • Analyst confirms, corrects, or rejects extracted values                │
│  • Confirmed values become FRM overrides                                  │
└──────────────────────────────┬─────────────────────────────────────────────────────────────┘
                               │ confirmed values
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM Parameter Store                                                       │
│  • Per-entity overrides                                                    │
│  • Fall back to PRG defaults where no evidence exists                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Design principle**: the FRIM is **read-only** with respect to the FRM. It produces evidence, not decisions. The FRM decides whether to accept the evidence, and the human review step is where that decision is recorded.

---

## 3. Source Registry

### 3.1 Registry format

The source registry is a YAML file that names every entity in the FRM universe:

```yaml
# config/frm/report_sources.yaml
entities:
  - entity_id: ESKOM
    name: Eskom Holdings SOC Ltd
    entity_type: utility
    country_iso: ZA
    annual_report_url: https://www.eskom.co.za/IR/Pages/FinancialReports.aspx
    xbrl_url: null
    fiscal_year_end_month: 3
    reporting_currency: ZAR
    language: en
    accounting_standard: IFRS
    notes: >
      State-owned utility; reports in ZAR; fiscal year ends March.
      Annual reports available from 2000 onwards.
  - entity_id: KPLC
    name: Kenya Power and Lighting Company
    entity_type: utility
    country_iso: KE
    annual_report_url: https://kplc.co.ke/category/view/32/annual-reports
    xbrl_url: null
    fiscal_year_end_month: 6
    reporting_currency: KES
    language: en
    accounting_standard: IFRS
    notes: >
      Listed on Nairobi Securities Exchange; fiscal year ends June.
  - entity_id: UMME
    name: Umeme Limited
    entity_type: utility
    country_iso: UG
    annual_report_url: https://www.umeme.co.ug/investor-relations/annual-reports
    xbrl_url: null
    fiscal_year_end_month: 12
    reporting_currency: UGX
    language: en
    accounting_standard: IFRS
    notes: >
      Listed on Uganda Securities Exchange; fiscal year ends December.
  - entity_id: CIE
    name: Compagnie Ivoirienne d'Electricité
    entity_type: utility
    country_iso: CI
    annual_report_url: https://www.cie.ci/finance/rapports-annuels
    xbrl_url: null
    fiscal_year_end_month: 12
    reporting_currency: XOF
    language: fr
    accounting_standard: IFRS
    notes: >
      Reports in French; fiscal year ends December.
  - entity_id: NIGELEC
    name: Société Nigérienne d'Électricité
    entity_type: utility
    country_iso: NE
    annual_report_url: https://www.nigelec.ne/rapports
    xbrl_url: null
    fiscal_year_end_month: 12
    reporting_currency: XOF
    language: fr
    accounting_standard: SYSCOHADA
    notes: >
      Reports under SYSCOHADA (OHADA accounting system), not IFRS.
      Fiscal year ends December.
  - entity_id: ZESCO
    name: Zambia Electricity Supply Corporation
    entity_type: utility
    country_iso: ZM
    annual_report_url: https://www.zesco.co.zm/investors/annual-reports
    xbrl_url: null
    fiscal_year_end_month: 12
    reporting_currency: ZMW
    language: en
    accounting_standard: IFRS
    notes: >
      State-owned utility; fiscal year ends December.
```

### 3.2 Registry validation

The registry is validated at load time:

- Every `entity_id` is unique
- Every `country_iso` is a valid ISO 3166-1 alpha-2 code
- Every `reporting_currency` is a valid ISO 4217 code
- Every `annual_report_url` is reachable
- Every `accounting_standard` is one of `IFRS`, `US_GAAP`, `SYSCOHADA`, `LOCAL_GAAP`

If a URL is unreachable, the entity is marked `registry_status: unreachable` and excluded from the current ingestion run.

---

## 4. Acquisition Layer

### 4.1 Retrieval

Each entity's annual report is retrieved from its registered URL. The acquisition layer must handle:

- **Direct PDF links**: the URL points to a PDF file
- **Index pages**: the URL points to a page listing multiple years' reports
- **JavaScript-rendered pages**: the URL requires a browser to render (use `playwright`)

```python
import httpx
from playwright.sync_api import sync_playwright

def acquire_report(entity: ReportSource, fiscal_year: int) -> Path:
    if entity.xbrl_url:
        return _download_xbrl(entity.xbrl_url, fiscal_year)
    if _is_direct_pdf(entity.annual_report_url):
        return _download_pdf(entity.annual_report_url, fiscal_year)
    return _discover_and_download(entity.annual_report_url, fiscal_year)
```

### 4.2 Storage

Every retrieved document is stored in object storage (MinIO/S3) with a content-addressed key:

```
frm/raw/{entity_id}/{fiscal_year}/{sha256}.pdf
frm/raw/{entity_id}/{fiscal_year}/{sha256}.xbrl
```

The retrieval metadata is recorded in a sidecar JSON:

```json
{
  "entity_id": "ESKOM",
  "fiscal_year": 2024,
  "source_url": "https://www.eskom.co.za/IR/FinancialResults/2024/...",
  "retrieved_at": "2026-10-19T14:23:00Z",
  "http_status": 200,
  "content_length": 4820104,
  "content_type": "application/pdf",
  "sha256": "8f2a...",
  "retrieval_method": "direct",
  "document_type": "integrated_report"
}
```

### 4.3 Refresh policy

The acquisition layer runs on a schedule:

- **Annual**: every February, after most African utilities have published their fiscal-year results
- **On-demand**: when an analyst needs a specific year's report
- **Retry**: failed retrievals are retried daily for 30 days before being marked `unreachable`

---

## 5. Extraction Layer

### 5.1 Format detection

The extracted document's type is detected from its content, not its extension:

```python
def detect_format(path: Path) -> Literal["xbrl", "pdf", "html"]:
    with open(path, "rb") as f:
        header = f.read(8)
    if header.startswith(b"%PDF"):
        return "pdf"
    if header.startswith(b"<?xml") or path.suffix in (".xbrl", ".xml"):
        return "xbrl"
    return "html"
```

### 5.2 XBRL extraction (preferred)

If the document is XBRL, extraction is deterministic. Use the `Brel` library, which handles XBRL instance parsing, taxonomy resolution, and fact extraction across IFRS and local GAAP taxonomies.

```python
from brel import XBRLReport

def extract_xbrl(path: Path, entity: ReportSource) -> dict:
    report = XBRLReport.open(path)
    return {
        "revenue": report.get_fact("ifrs-full:Revenue"),
        "cost_of_sales": report.get_fact("ifrs-full:CostOfSales"),
        "ebitda": _compute_ebitda(report),
        "depreciation": report.get_fact("ifrs-full:DepreciationAndAmortisationExpense"),
        "interest_expense": report.get_fact("ifrs-full:FinanceCosts"),
        "tax_expense": report.get_fact("ifrs-full:IncomeTaxExpenseContinuingOperations"),
        "total_debt": report.get_fact("ifrs-full:Borrowings"),
        "equity": report.get_fact("ifrs-full:Equity"),
        "capex": report.get_fact("ifrs-full:PurchaseOfPropertyPlantAndEquipment"),
    }
```

**Confidence**: 1.0 for every value; no fuzzy matching is needed.

### 5.3 PDF table extraction

For PDF documents, the extraction has three steps.

#### 5.3.1 Table detection

Use `pdfplumber` for digital PDFs:

```python
import pdfplumber

def detect_tables(path: Path) -> list[dict]:
    tables = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                tables.append({
                    "page": page_num,
                    "rows": table,
                    "text": page.extract_text(),
                })
    return tables
```

For scanned PDFs, run OCR first:

```python
import subprocess

def ocr_if_needed(path: Path) -> Path:
    if _is_scanned(path):
        output = path.with_suffix(".ocr.pdf")
        subprocess.run(["ocrmypdf", "--force-ocr", str(path), str(output)])
        return output
    return path
```

#### 5.3.2 Statement identification

Financial statements are identified by heading and line-item match:

```python
STATEMENT_HEADINGS = {
    "income_statement": [
        "statement of profit or loss",
        "income statement",
        "statement of comprehensive income",
        "compte de résultat",
        "demonstração do resultado",
    ],
    "balance_sheet": [
        "statement of financial position",
        "balance sheet",
        "bilan",
        "balanço patrimonial",
    ],
    "cash_flow": [
        "statement of cash flows",
        "cash flow statement",
        "tableau des flux de trésorerie",
        "demonstração dos fluxos de caixa",
    ],
}

def identify_statement(table: dict) -> str | None:
    text = table["text"].lower()
    for statement, headings in STATEMENT_HEADINGS.items():
        if any(h in text for h in headings):
            return statement
    return None
```

#### 5.3.3 Line-item extraction

Each row is matched against the canonical taxonomy using fuzzy matching:

```python
from rapidfuzz import fuzz

CANONICAL_LINE_ITEMS = {
    "revenue": ["Revenue", "Total revenue", "Sales", "Turnover", "Chiffre d'affaires", "Receita"],
    "cost_of_sales": ["Cost of sales", "Cost of revenue", "Operating costs", "Coût des ventes", "Custo dos produtos vendidos"],
    "ebitda": ["EBITDA", "Operating profit before depreciation", "Résultat d'exploitation avant amortissements"],
    "depreciation": ["Depreciation", "Depreciation and amortisation", "D&A", "Amortissements"],
    "interest_expense": ["Finance costs", "Interest expense", "Borrowing costs", "Charges financières"],
    "tax_expense": ["Income tax expense", "Taxation", "Current tax", "Impôt sur le résultat"],
    "total_debt": ["Borrowings", "Total borrowings", "Debt", "Loans", "Dettes financières", "Empréstimos"],
    "equity": ["Total equity", "Shareholders' equity", "Equity attributable", "Capitaux propres", "Patrimônio líquido"],
    "capex": ["Purchase of property, plant and equipment", "Capital expenditure", "Capex", "Acquisitions d'immobilisations"],
}

def match_line_item(row: list[str]) -> str | None:
    label = row[0].strip().lower()
    best_match = None
    best_score = 0
    for canonical, synonyms in CANONICAL_LINE_ITEMS.items():
        for synonym in synonyms:
            score = fuzz.partial_ratio(label, synonym.lower())
            if score > best_score and score >= 85:
                best_match = canonical
                best_score = score
    return best_match
```

The numeric value is extracted from the row's second (or later) column, parsed as a float, and tagged with its confidence (the match score).

### 5.4 LLM fallback

For narrative sections, MD&A discussions, or non-standard layouts, use an LLM with a structured prompt:

```python
import anthropic

EXTRACTION_PROMPT = """
You are extracting financial data from an African utility's annual report.
Return a JSON object with these keys: revenue, ebitda, interest_expense,
tax_expense, total_debt, equity, capex. For each, return:
- value (float or null)
- currency (ISO 4217)
- page_number (int or null)
- exact_quote (string or null)
- confidence (0.0-1.0)

If a value is not stated, return null for that key.
"""

def extract_llm(text: str) -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT + "\n\n" + text}],
    )
    return json.loads(response.content[0].text)
```

**Confidence**: the LLM's own confidence estimate, capped at 0.90 (never fully trusted). LLM extractions are always queued for human review.

### 5.5 Extraction priority

For each statement, the extraction layer tries in order:

1. **XBRL** (if available): deterministic, confidence 1.0
2. **PDF table extraction**: deterministic, confidence = match score
3. **LLM fallback**: probabilistic, confidence ≤ 0.90

If XBRL is available, PDF and LLM extraction are skipped. If PDF extraction fails to find a statement, LLM is used. The method used is recorded for every value.

---

## 6. Normalisation Layer

### 6.1 Currency conversion

Extracted values are converted to USD using the **fiscal-year average** exchange rate, not the year-end spot:

```python
def normalise_currency(value: float, from_ccy: str, to_ccy: str, fiscal_year: int) -> float:
    rate = average_exchange_rate(from_ccy, to_ccy, fiscal_year)
    return value / rate
```

The FX series is loaded from `config/frm/fx_rates.yaml`, which carries annual averages for every African currency against USD, sourced from IMF IFS and the World Bank WDI:

```yaml
fx_rates:
  ZAR:
    2023: 17.84
    2024: 18.32
  KES:
    2023: 138.50
    2024: 145.20
  UGX:
    2023: 3,720.0
    2024: 3,810.0
```

### 6.2 Fiscal year calendarisation

If the fiscal year does not end in December, the value is split across two calendar years:

```python
def calendarise(value: float, fy_end_month: int) -> list[tuple[int, float]]:
    if fy_end_month == 12:
        return [(fiscal_year, value)]
    # A June-ending FY has 6 months in the prior calendar year.
    months_prior = fy_end_month
    months_current = 12 - months_prior
    return [
        (fiscal_year - 1, value * months_prior / 12),
        (fiscal_year, value * months_current / 12),
    ]
```

### 6.3 Accounting standard alignment

The FRM assumes IFRS. If the entity reports under a different standard, the extraction layer flags it and the normalisation layer applies a **standard-specific adjustment**:

| Standard | Adjustment |
|---|---|
| **IFRS** | None |
| **US GAAP** | Add back operating lease payments to EBITDA; restate revenue under IFRS 15 |
| **SYSCOHADA** | Restate under IFRS 16 for leases; restate revenue recognition |
| **Local GAAP** | Case-by-case; the entity is flagged for manual review |

The adjustment is a **calibration finding**, not an automatic correction. The FRM's parameter is the forward-looking IFRS-equivalent, and the normalisation layer records the gap.

### 6.4 Language normalisation

Line-item synonyms are maintained in English, French, and Portuguese. If a report is in Arabic or another language, the extraction layer uses the LLM fallback with a translation step.

---

## 7. Calibration and Mapping to FRM

### 7.1 The calibration report

The calibration layer compares each extracted value to the corresponding FRM parameter:

```python
@dataclass(frozen=True)
class CalibrationFinding:
    entity_id: str
    fiscal_year: int
    parameter: str
    frm_value: float
    extracted_value: float
    relative_error: float
    severity: Literal["error", "warning", "info"]
    recommendation: Literal["update_parameter", "investigate", "accept"]
    source_document: str  # SHA-256
    page_number: int
    extraction_method: str
```

### 7.2 Mapping rules

| Extracted item | FRM parameter | Comparison |
|---|---|---|
| Revenue | `revenue_usd_per_year` | The FRM's modelled revenue vs. the entity's reported revenue |
| EBITDA | `ebitda_usd_per_year` | The FRM's modelled margin vs. the entity's reported margin |
| Interest expense | `interest_expense_usd_per_year` | Calibrates `cost_of_debt` |
| Tax expense | `tax_expense_usd_per_year` | Validates the tax model's output |
| Total debt | `debt_outstanding_usd` | Calibrates `debt_fraction` and `gearing_ratio` |
| Equity | `equity_usd` | Validates the capital structure |
| Capex | `capex_usd_per_year` | Validates the capex assumption |

### 7.3 Severity classification

```python
def classify_severity(relative_error: float) -> str:
    if relative_error > 0.20:
        return "error"      # the FRM's parameter is likely wrong
    elif relative_error > 0.10:
        return "warning"    # the FRM's parameter is plausible but should be checked
    else:
        return "info"       # the FRM's parameter is consistent with the evidence
```

### 7.4 What the calibration does **not** do

The calibration does **not** automatically update the FRM's parameters. A 3-point gap between the FRM's cost of debt and the entity's actual borrowing cost is a **finding**, not a decision. The finding is presented to the analyst, who decides whether to:

- **Update the parameter** (the evidence is strong, the FRM's assumption was wrong)
- **Investigate** (the gap has an explanation — old debt at low rates, new debt at high rates, subsidy)
- **Accept** (the FRM's parameter is deliberately different from the historical value, e.g., because the future is expected to differ)

That decision is recorded in the human review workflow.

---

## 8. Human Review Workflow

### 8.1 Review queue

Every extracted value with `confidence < 0.85` is placed in a review queue. Every calibration finding with `severity == "error"` is also queued.

```python
@dataclass
class ReviewItem:
    item_id: str
    entity_id: str
    fiscal_year: int
    parameter: str
    extracted_value: float
    confidence: float
    source_document: str
    page_number: int
    exact_quote: str
    status: Literal["pending", "confirmed", "corrected", "rejected"]
    reviewer: str | None
    reviewed_at: datetime | None
```

### 8.2 Review interface

The review interface is a web UI (Plotly Dash or similar) that shows:

- The extracted value, with its confidence
- The page image from the source document, with the value highlighted
- The exact quote from the report
- The corresponding FRM parameter
- Actions: **Confirm**, **Correct** (with a new value), **Reject**

### 8.3 Confirmed values

Confirmed values become **FRM parameter overrides** for that entity and fiscal year:

```yaml
# data/frm/confirmed/ESKOM/2024.yaml
entity_id: ESKOM
fiscal_year: 2024
overrides:
  interest_expense_usd_per_year: 1250000000.0
  total_debt_usd: 480000000000.0
reviewer: analyst@alea.africa
reviewed_at: 2026-10-19T15:00:00Z
```

The FRM reads these overrides during its projection. Where no override exists, the PRG default is used.

---

## 9. Provenance and Data Quality

### 9.1 Provenance record

Every extracted value carries a **provenance record**:

```python
@dataclass(frozen=True)
class Provenance:
    source_document_sha256: str
    source_url: str
    retrieved_at: datetime
    page_number: int
    table_index: int | None
    row_index: int | None
    extraction_method: str  # "xbrl", "pdfplumber", "camelot", "llm"
    extraction_timestamp: datetime
    confidence: float
    exact_quote: str
```

### 9.2 Data quality rules

| Rule | Action |
|---|---|
| Extracted value is negative for a quantity that should be positive (revenue, EBITDA) | Flag for review |
| Extracted value is zero | Flag for review |
| Extracted value is more than 10× the prior year's value | Flag for review |
| Extracted value is more than 10× the PRG default | Flag for review |
| Two extraction methods disagree | Use the higher-confidence method; flag the disagreement |
| Currency is unknown | Reject the value |

### 9.3 Data quality dashboard

A dashboard shows:

- Extraction coverage (how many entities have been ingested for each year)
- Extraction confidence (mean, median, minimum per entity)
- Review queue depth and age
- Calibration findings by severity
- Provenance completeness

---

## 10. Pipeline Implementation

The FRIM is a **Snakemake workflow**, consistent with the rest of ALEA:

```
Snakefile
├── rules/frm/download.smk           # acquisition
├── rules/frm/extract_xbrl.smk       # XBRL extraction
├── rules/frm/extract_pdf.smk        # PDF extraction
├── rules/frm/extract_llm.smk        # LLM fallback
├── rules/frm/normalise.smk          # currency, fiscal year, accounting, language
├── rules/frm/calibrate.smk          # calibration findings
├── rules/frm/review.smk             # human review integration
└── rules/frm/export.smk             # export to FRM parameter store
```

### 10.1 Configuration

```yaml
# config/frm/ingestion.yaml
frm_ingestion:
  enabled: true
  entities: "config/frm/report_sources.yaml"
  fiscal_years: [2020, 2021, 2022, 2023, 2024]
  extraction:
    preferred_method: "xbrl_then_pdf_then_llm"
    pdf_tool: "pdfplumber"
    fuzzy_threshold: 85
    llm_model: "claude-sonnet-4-20250514"
  normalisation:
    target_currency: "USD"
    target_accounting_standard: "IFRS"
    target_language: "en"
  calibration:
    severity_thresholds:
      error: 0.20
      warning: 0.10
    auto_accept_below: 0.05
  review:
    confidence_threshold: 0.85
    queue_path: "data/frm/review_queue.parquet"
  provenance:
    storage: "minio://frm-provenance"
    retention_years: 10
```

### 10.2 Execution

```bash
# Ingest all entities for all configured years
snakemake -s Snakefile frm_ingestion_all --cores 4

# Ingest a specific entity and year
snakemake -s Snakefile frm_ingest_entity --config entity_id=ESKOM fiscal_year=2024

# Run calibration on already-extracted values
snakemake -s Snakefile frm_calibrate_all --cores 2

# Export confirmed values to the FRM parameter store
snakemake -s Snakefile frm_export --config entity_id=ESKOM
```

### 10.3 Dependencies

```yaml
dependencies:
  - python>=3.11
  - snakemake>=7.32
  - pdfplumber>=0.10
  - camelot-py>=0.11
  - ocrmypdf>=15.0
  - brel>=0.1
  - rapidfuzz>=3.0
  - anthropic>=0.30
  - httpx>=0.27
  - playwright>=1.40
  - minio>=7.2
  - pandas>=2.0
  - pyyaml>=6.0
  - pydantic>=2.0
```

---

## 11. African-Specific Considerations

### 11.1 Report availability

| Country | Typical publication lag | Availability |
|---|---|---|
| South Africa | 3–4 months | High (Eskom publishes annually) |
| Kenya | 3–4 months | High (KPLC publishes annually) |
| Nigeria | 6–12 months | Medium (some utilities publish, some do not) |
| Francophone West Africa | 6–18 months | Medium (CIE publishes, NIGELEC rarely) |
| Central Africa | > 18 months | Low (many utilities do not publish) |

For entities with no published report, the FRIM records `evidence_status: unavailable` and the FRM falls back to PRG defaults.

### 11.2 Currency redenomination

Zimbabwe redenominated from ZWD to ZWL to ZiG. The FRIM must handle currency changes by:

- Storing the currency code as reported
- Applying the redenomination factor to convert to a single currency
- Recording the redenomination in provenance

### 11.3 Hyperinflation

For entities reporting in a hyperinflationary currency (Zimbabwe, Sudan, South Sudan), the FRIM extracts **both** the nominal and the inflation-adjusted values if the report provides them. If only nominal is available, the FRIM applies the country's CPI series to deflate to the base year.

### 11.4 Restatements

Entities frequently restate prior years. The FRIM uses the **most recent restated** value, not the originally reported one. The provenance record notes both.

### 11.5 Consolidated vs. standalone

The FRIM extracts **both** if both are reported, and tags each with `scope: consolidated` or `scope: standalone`. The FRM uses consolidated for group-level analysis and standalone for entity-level.

### 11.6 Language

The FRIM supports English, French, and Portuguese. Reports in Arabic or other languages are flagged for manual translation.

### 11.7 Accounting standards

- **IFRS**: South Africa, Kenya, Uganda, Nigeria, Ghana, most listed entities
- **SYSCOHADA**: Francophone West and Central Africa (OHADA member states)
- **Local GAAP**: Some state-owned utilities

The FRIM records the standard and applies the IFRS-equivalent adjustment where possible.

---

## 12. Testing and Validation

| Test type | What it checks |
|---|---|
| **Unit tests** | Each extractor on a small fixture PDF/XBRL |
| **Integration tests** | Full pipeline on 3 real reports (one IFRS, one French, one scanned) |
| **Property-based tests** | `hypothesis` over cash-flow inputs: extracted revenue is monotonic in the table's numeric column; currency conversion is invertible |
| **Regression tests** | Known values from a curated set of reports; extraction must reproduce them |
| **Calibration tests** | The calibration report's severity classification is correct for known gaps |
| **Provenance tests** | Every extracted value has a complete provenance record |
| **FX tests** | Currency conversion uses the correct fiscal-year average |
| **Fiscal year tests** | Calendarisation splits a June-year correctly |

**Acceptance criteria**:

- Extraction accuracy ≥ 95% on the curated regression set
- Calibration coverage ≥ 80% of entities for the last 3 years
- Review queue processed within 5 business days
- Every confirmed value has a complete provenance record

---

## 13. Performance and Scalability

| Operation | Target | Hardware |
|---|---|---|
| XBRL extraction | < 5 seconds per document | 4 cores, 8 GB RAM |
| PDF table extraction | < 30 seconds per document | 4 cores, 8 GB RAM |
| OCR (scanned PDF) | < 3 minutes per document | 8 cores, 16 GB RAM |
| LLM extraction | < 60 seconds per document | API-bound |
| Full ingestion (55 entities × 5 years) | < 4 hours | 8 cores, 32 GB RAM |
| Calibration | < 5 minutes for all entities | 4 cores, 8 GB RAM |

The pipeline is **parallelisable** across entities: each entity is independent, and Snakemake handles the parallelism.

---

## 14. Security and Compliance

### 14.1 Data protection

- Extracted financial data is **public** (from audited reports) and does not require PII protection.
- If an entity's report contains PII (director names, salaries), the FRIM redacts it before storage.

### 14.2 Access control

- The FRIM is accessible to **FRM developers** and **analysts**.
- The review interface requires **analyst** authentication.
- The source registry is **version-controlled** in git; changes require review.

### 14.3 Audit trail

- Every extraction is logged with the source document, page number, method, and confidence.
- Every review action is logged with the reviewer, timestamp, and decision.
- Every FRM parameter override is logged with the evidence that justified it.

---

## 15. Roadmap

| Phase | Duration | Deliverable |
|---|---|---|
| **1. Registry and acquisition** | 2 weeks | Source registry, HTTP download, object storage |
| **2. XBRL extraction** | 2 weeks | `Brel`-based extractor, unit tests |
| **3. PDF table extraction** | 4 weeks | `pdfplumber`/`Camelot` extractor, fuzzy matching, OCR |
| **4. LLM fallback** | 2 weeks | Anthropic/OpenAI client, prompt engineering, validation |
| **5. Normalisation** | 2 weeks | Currency, fiscal year, accounting standard, language |
| **6. Calibration** | 2 weeks | Finding generation, severity classification |
| **7. Review workflow** | 3 weeks | Web UI, review queue, confirmed-value export |
| **8. Pipeline integration** | 2 weeks | Snakemake rules, provenance, logging |
| **9. Testing and validation** | 3 weeks | Regression set, accuracy benchmarks |
| **10. Production release** | 2 weeks | Documentation, monitoring, support |

**Total: 24 weeks (6 months)** for the full build. A minimum viable version covering Phases 1–5 and 8 is **12 weeks**.

---

## 16. Non-Functional Requirements

| Requirement | Target |
|---|---|
| **Availability** | 99% for the extraction service |
| **Throughput** | 55 entities × 5 years in < 4 hours |
| **Accuracy** | ≥ 95% on the regression set |
| **Provenance completeness** | 100% of extracted values |
| **Review turnaround** | < 5 business days |
| **Data retention** | 10 years for raw documents and provenance |
| **Portability** | Runs on Linux, macOS; deployable via Docker |
| **Maintainability** | Modular extractors; adding a new format is a new module |
| **Documentation** | User guide, developer guide, API reference |

---

## 17. Deliverables

1. **Source registry** (`config/frm/report_sources.yaml`) with 20+ entities
2. **Acquisition pipeline** (Snakemake rules, HTTP client, object storage)
3. **Extraction pipeline** (XBRL, PDF, LLM extractors)
4. **Normalisation pipeline** (currency, fiscal year, accounting, language)
5. **Calibration engine** with severity classification
6. **Review UI** (web interface)
7. **Provenance store** (MinIO/S3 with SHA-256 hashing)
8. **FRM parameter overrides** (`data/frm/confirmed/{entity_id}/{fiscal_year}.yaml`)
9. **Test suite** (unit, integration, regression, property-based)
10. **Documentation** (user guide, developer guide, API reference)
11. **Data quality dashboard**
12. **Monitoring and alerting** (extraction failures, review queue depth, accuracy drift)

---

## 18. What This Specification Does Not Cover

The FRIM is an ingestion pipeline. It does **not**:

- Model future financial performance (that is the FRM)
- Recompute the PRG's parameters (that is the PRG)
- Validate the audited accounts (that is the auditor's job)
- Interpret the entity's strategy (that is the analyst's job)
- Replace the FRM's forward-looking assumptions (it calibrates them, it does not overwrite them)

The FRIM's value is that it makes the FRM's parameters **accountable to the entities they model**. A cost-of-debt assumption that has never been compared to a utility's actual borrowing cost is an assumption, not a fact. The FRIM turns assumptions into evidence, and the calibration report is where the FRM's parameters meet reality.

---

**End of Specification**