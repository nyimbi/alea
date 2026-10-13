# 09 — Layer 6: Periodic Reporting

**Track A/B shared.** Daily, weekly, monthly, quarterly, annual reports.
Budget: **four weeks**, after the layers whose data they carry.

Layer 6 is the platform's visible surface. It is where a modelling error becomes
a published claim, which makes it the layer with the highest cost of being
wrong.

---

## 1. What Layer 6 owns

| Concern | Module |
|---|---|
| Report schemas (what a report contains) | `reporting.schemas` |
| Data assembly per cadence | `reporting.daily`, `.weekly`, `.monthly`, `.quarterly`, `.annual` |
| Templating (Jinja2) | `reporting.templates` |
| Rendering (HTML → PDF) | `reporting.render` |
| Distribution adapters | `reporting.distribute` |
| Scheduling | `reporting.schedule` |

It computes **nothing**. Every number comes from a layer below and carries that
layer's provenance.

---

## 2. The rule that governs this layer

**A report may not contain a number whose provenance it cannot print.**

The specification's templates render values directly. That is the shape that
produces a report where a proxy estimate for Burundi sits beside a metered value
for Kenya with no visual distinction. AD-6 says uncertainty travels with the
datum; Layer 6 is where that promise is either kept or broken.

Concretely: every number in a report is a `ReportValue` carrying its
provenance, and the template renders the uncertainty marker.

```python
# src/alea/reporting/schemas.py
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from alea.provenance.models import Provenance

class ValueBasis(StrEnum):
	MEASURED = "measured"
	MODELLED = "modelled"
	PROXY = "proxy"
	FORECAST = "forecast"

@dataclass(frozen=True)
class ReportValue:
	"""One number in a report, with everything needed to read it.

	``basis`` is rendered as a superscript marker. A report where a proxy is
	indistinguishable from a measurement is a report that will be quoted
	incorrectly, and the person quoting it will not have been careless.
	"""
	value: float
	unit: str
	basis: ValueBasis
	provenance: Provenance
	label: str = ""

	@property
	def marker(self) -> str:
		return {
			ValueBasis.MEASURED: "",
			ValueBasis.MODELLED: "ᵐ",
			ValueBasis.PROXY: "ᵖ",
			ValueBasis.FORECAST: "ᶠ",
		}[self.basis]
```

**The markers are part of the acceptance test.** A report fixture containing a
proxy value must render with `ᵖ`; a canary removes the marker and the test fails.

---

## 3. Cadences

### 3.1 Daily (06:00 local)

| Section | Source | Cadence-specific hazard |
|---|---|---|
| Outage forecast (24 h) | Layer 4 | Probability, not a binary — render the CI |
| Weather alerts | ERA5 forecast | Threshold `severity >= 3` is config, recorded |
| Generation mix (day-ahead) | Layer 1 dispatch | — |
| Price forecast | Layer 3 | — |
| System alerts | Layer 4 contingency | — |
| Outage summary (yesterday) | Layer 4 VIIRS | VIIRS has ~1-day latency; state it |

**The VIIRS latency must be stated.** A daily report saying "outages yesterday"
when the satellite data is 24–48 h behind is reporting an incomplete picture as
a complete one. The report states the data's actual coverage window.

### 3.2 Weekly (Monday 06:00)

Week-ahead outlook, market summary, renewable forecast, loss decomposition,
critical-line watch, outage events, mitigation update.

### 3.3 Monthly (1st, 06:00)

Market report, capacity update, generation statistics (actual vs. forecast),
outage statistics (SAIDI/SAIFI with proxy flags), loss statistics, resilience
metrics, policy tracker.

**"Actual vs. forecast" requires the previous month's forecast to have been
retained.** A report that compares this month's actuals against a forecast it
did not save is comparing against a reconstruction. Forecasts are stored as
artefacts at generation time, keyed by issue date.

### 3.4 Quarterly and annual

Quarterly: market outlook, investment pipeline, scenario update, climate risk,
resilience scorecard.

Annual: continental outlook, investment requirements, CMP alignment, AfSEM
progress, just transition, climate scenarios.

**The annual report is the one that gets cited.** It carries the fullest
provenance and the most prominent `[UNVERIFIED]` handling — every literature
benchmark still unverified at that point is either resolved or printed with its
status.

---

## 4. Rendering

```python
# src/alea/reporting/render.py
def render_report(
	template: str,
	context: dict[str, object],
	out: Path,
	*,
	formats: tuple[str, ...] = ("html", "pdf"),
) -> dict[str, Path]:
	"""Render a report to HTML and PDF.

	HTML is the source of truth; PDF is a rendering of it. The PDF is not
	checksum-stable — WeasyPrint stamps metadata — so the *drift gate covers
	the HTML only* and asserts separately that each HTML has a non-empty PDF
	beside it. A gate that diffs the PDFs fails forever on a clean tree.
	"""
```

**This is the drift-gate scoping lesson, applied in advance.** A PDF is not
byte-reproducible; a gate that diffs it is a gate that cannot pass, which is
indistinguishable from no gate.

### 4.1 Charts

Charts are rendered by `matplotlib` to SVG and embedded. **No chart is rendered
from a number that is not also in the report's context** — a chart is a view of
the data, not a separate data path. This is what prevents a report whose table
and whose chart disagree.

### 4.2 Number formatting

- Units always in the header or the cell, never implied.
- Currency always with its rate date when converted.
- Percentages: one decimal, and a percentage of what is stated in the header.
- **No number is rounded to fewer significant figures than its uncertainty
  justifies.** A proxy estimate with ±30% uncertainty rendered as `1,234 MW` is
  a false precision claim. Proxy values render to the precision their
  uncertainty supports (typically two significant figures).

```python
def format_value(v: ReportValue) -> str:
	"""Format respecting uncertainty.

	A value with 30% relative uncertainty has one significant figure of
	information; rendering it as a 4-digit integer claims three more than
	exist. Report readers quote the digits they are given.
	"""
```

---

## 5. Distribution

The specification's `ReportDistributor` has three defects:

1. **Credentials in code**: `msg["From"] = "reports@pypsa-x.africa"` is fine, but
   the SMTP host is hardcoded and the password comes from `os.environ` with no
   check — an unset `SMTP_PASSWORD` raises `KeyError` at send time, after the
   report is built.
2. **`_publish_api` is `pass`** — a distribution channel that does nothing.
3. **No delivery record.** Nothing records whether a report was sent, so a
   silently failed send is invisible.

```python
# src/alea/reporting/service.py
class DeliveryResult(BaseModel):
	channel: str
	recipients: list[str]
	sent_at: datetime
	status: Literal["sent", "failed", "skipped"]
	detail: str = ""
```

**Every distribution writes a `DeliveryResult` artefact.** A report that was
generated but not delivered is a report that was not published, and the platform
must be able to say which.

**Config validation at load, not at send:** an email channel with no SMTP
configuration fails at config load (`01-foundations.md` §1), not at 06:00 when
the report is due.

---

## 6. Scheduling

```python
# src/alea/reporting/schedule.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
```

The specification's schedule is correct in shape. Three requirements:

1. **Timezones explicit.** `CronTrigger(hour=6)` uses the scheduler's timezone.
   A report "at 06:00 local" across 55 countries in 5 timezones needs the
   timezone named. Reports are generated per-country-timezone, or at a single
   UTC time with the local equivalent stated.
2. **A missed run is visible.** APScheduler's default `misfire_grace_time` can
   silently drop a run if the process was down. `misfire_grace_time` is set
   explicitly and a missed run writes a `DeliveryResult(status="skipped")`.
3. **The scheduler is not the only way to run.** `alea report daily --date X`
   must produce the same report the scheduler would. A scheduled-only report
   cannot be backfilled, and backfill is required for the "actual vs. forecast"
   comparison.

---

## 7. Module layout

```
src/alea/reporting/
├── __init__.py
├── schemas.py      # ReportValue, report contexts
├── daily.py
├── weekly.py
├── monthly.py
├── quarterly.py
├── annual.py
├── render.py       # Jinja2 → HTML → PDF
├── schedule.py     # APScheduler wiring
├── templates/      # Jinja2 templates per cadence
└── service.py      # build, deliver, and the DeliveryResult adapters
```

---

## 8. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_every_value_has_provenance` | No bare float reaches a template | Inject a float; must fail |
| `test_proxy_values_marked` | Proxy renders with `ᵖ` | Remove marker; must fail |
| `test_precision_matches_uncertainty` | ±30% value renders ≤ 2 sig figs | Render 4 digits; must fail |
| `test_table_and_chart_agree` | Chart data is the table's data | Diverge them; must fail |
| `test_html_pdf_pair_exists` | Every HTML has a non-empty PDF | Delete a PDF; must fail |
| `test_drift_gate_covers_html_only` | Drift gate diffs HTML, not PDF | Add PDF; gate must still pass |
| `test_delivery_recorded` | Every send writes a DeliveryResult | Drop the record; must fail |
| `test_config_validated_at_load` | Missing SMTP config fails at load | Remove config; must fail |
| `test_scheduled_matches_manual` | Scheduler output == CLI output | Diverge; must fail |
| `test_no_unverified_benchmark` | No `[UNVERIFIED]` figure in a published report | Inject one; must fail |
| `test_the_projected_registers_partition_the_produced_sections` | Every produced section is recorded as projected or unprojected | Delete the entry; must fail |
| `test_every_projected_section_has_a_rule_and_a_dvc_stage` | A projection recorded as delivered is declared by both workflows | Rename the rule; must fail |
| `test_a_projection_writes_the_pattern_its_section_declares` | The rule's output is the section's own `artefact` pattern | Move the directory; must fail |
| `test_the_projection_register_and_the_workflow_declare_the_same_set` | The register and the workflow files name the same projections | Drop a rule; must fail |

**`test_no_unverified_benchmark` is the gate that keeps the plan's honesty rule
enforceable.** AD-10's rule — no `[UNVERIFIED]` figure in a published report —
is only real if a check fails when one appears.

**The three projection gates are the ones that distinguish a producer from a
delivery.** `reporting/producers.py` records the *function* that computes a
section's rows, and every stage writes `data/processed/` while every section
reads `results/<dir>/{date}.parquet`. Nothing bridged the two: no subcommand, no
rule, no test — so `capacity_update` sat in `PRODUCERS`, its rule exited 0, and
`alea report monthly` exited 1 with `ReportDataError: no artefact`, while 918
tests passed because `tests/fixtures/reporting` writes every dated path by hand.
A fixture that manufactures a section's input cannot see that no layer produces
it, which is why the delivery claim needs a gate over the *workflow files* and
not over the register's own wording.

---

## 9. Exit criteria for Layer 6

| # | Criterion | Gate |
|---|---|---|
| 1 | All five cadences render end-to-end on fixtures | Integration test |
| 2 | Every value carries provenance and a basis marker | `test_every_value_has_provenance` |
| 3 | Proxy values visibly marked | `test_proxy_values_marked` |
| 4 | Precision respects uncertainty | `test_precision_matches_uncertainty` |
| 5 | Delivery recorded per channel | `test_delivery_recorded` |
| 6 | Manual and scheduled generation identical | `test_scheduled_matches_manual` |
| 7 | Drift gate scoped to HTML, PDFs asserted non-empty | `test_drift_gate_covers_html_only` |
| 8 | No unverified benchmark in a report | `test_no_unverified_benchmark` |
| 9 | A produced section's artefact is delivered to the dated path its report reads | `test_a_projection_writes_the_pattern_its_section_declares` |
| 10 | Daily report generates in < 5 min | Recorded timing |
| 11 | Every gate canaried | `tests/ci/canaries` |

**Criterion 8 is the one that makes the rest credible.** A platform whose
reports distinguish measured from modelled from proxy, and which refuses to
print an unverified figure as though it were established, is a platform whose
numbers can be used. That is the whole value proposition.
