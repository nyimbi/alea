# SPDX-License-Identifier: MIT
"""`09-layer6-reporting.md` §8: the ten gates Layer 6 must have, as real tests.

§8's table names ten gates and, for each, the canary that watches it fail. This
module is the gate half; `tests/ci/canaries/test_reporting_gates.py` plants the
defect half. The split is the point: a gate that has never been seen to fail is
not evidence of anything (AD-10), and a canary with no gate to fail is a test
that passes for the wrong reason.

Most of these gates already had a function -- `check_report_gates`,
`missing_or_empty_pdfs`, `assert_no_unverified`, `validate_reporting_config`,
`record_delivery`, `run_cadence` -- and no test named for the property the plan
promises, so the derived register read them as unimplemented. Each test below
is named for its gate and asserts the property: against a real fixture report
where the property is a property of a rendered report, and against a hand-built
context where the defect is a malformed value the gate must reject.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from alea.config.loader import ConfigError, load_config
from alea.provenance.models import Basis, DerivedProvenance, Licence, Provenance
from alea.reporting.render import fingerprint, missing_or_empty_pdfs
from alea.reporting.schedule import run_cadence
from alea.reporting.schemas import (
	PROXY_MARKER,
	ReportCadence,
	ReportChart,
	ReportContext,
	ReportDataError,
	ReportSection,
	ReportTable,
	ReportValue,
	chart_matches_table,
	find_bare_numbers,
)
from alea.reporting.service import (
	UNVERIFIED_TOKEN,
	DeliveryResult,
	assert_no_unverified,
	build_report,
	check_report_gates,
	drift_gate,
	find_unverified_token,
	record_delivery,
	validate_reporting_config,
)
from tests.fixtures.reporting import (
	AS_OF,
	DEFAULT_ROWS,
	declared_artefacts,
	declared_shapes,
	write_all_fixture_sets,
	write_fixture_artefact,
)

# --------------------------------------------------------------------------
# Builders. A value object the gate must reject is built directly rather than
# read from an artefact: the point of these tests is the *gate*, and a defect a
# fixture cannot produce (a proxy claiming four significant figures, a chart
# plotting a value its table does not print) has to be constructed.
# --------------------------------------------------------------------------


def _provenance(basis: Basis, *, uncertainty: float = 0.0, source_id: str = "gate") -> Provenance:
	return Provenance(
		source_id=source_id,
		source_url="https://example.org/gate",
		licence=Licence.CC_BY_4_0,
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis="proxy" if uncertainty else "",
	)


def _value(
	*,
	basis: Basis = Basis.MEASURED,
	value: float = 1200.0,
	uncertainty: float = 0.0,
	label: str = "canary",
	significant_figures: int | None = None,
) -> ReportValue:
	return ReportValue(
		value=value,
		unit="MW",
		provenance=_provenance(basis, uncertainty=uncertainty),
		label=label,
		significant_figures=significant_figures,
	)


def _context(*, sections: list[ReportSection], **extra: object) -> ReportContext:
	return ReportContext(
		title="Gate report",
		cadence=ReportCadence.DAILY,
		as_of=AS_OF,
		period_start=AS_OF,
		period_end=AS_OF,
		generated_at=datetime.now(UTC),
		timezone="UTC",
		sections=sections,
		**extra,
	)


def _config(results_root: Path, reports_root: Path, **reporting: object):
	"""A config built through the real loader, so defaults are the CLI's."""
	overrides: dict[str, object] = {
		"paths": {"results": str(results_root), "reports": str(reports_root)},
	}
	if reporting:
		overrides["reporting"] = reporting
	return load_config(overrides=overrides)


def _daily(tmp_path: Path, *, pdf: bool = False):
	"""A rendered daily report over the real fixture set."""
	results, reports = tmp_path / "results", tmp_path / "reports"
	write_all_fixture_sets(results)
	return build_report(
		ReportCadence.DAILY,
		_config(results, reports, pdf_enabled=pdf),
		out=reports / "daily",
		date=AS_OF,
		deliver=False,
	)


def _report_fingerprint(context: ReportContext) -> str:
	"""A digest of everything that makes one report differ from another.

	The volatile fields (``generated_at``, ``run_id``) are excluded on purpose:
	the scheduled and manual paths run at different moments with different run
	ids, and the plan's claim is that the *report* is the same, not that the two
	processes share a clock.
	"""
	return fingerprint(
		[
			{
				"label": value.label,
				"value": value.value,
				"unit": value.unit,
				"basis": value.basis.value,
				"formatted": value.formatted,
			}
			for value in context.values
		]
	)


# --------------------------------------------------------------------------
# The ten gates
# --------------------------------------------------------------------------


def test_every_value_has_provenance(tmp_path: Path):
	"""§9 ``test_every_value_has_provenance``: no bare float reaches a template.

	A float in the context is a number the template prints with no basis and no
	provenance. The real report carries none, and a table cell holding one is
	caught rather than rendered.
	"""
	built = _daily(tmp_path)
	html = built.paths["html"].read_text()
	assert find_bare_numbers(built.context) == [], "the fixture report carries a bare number"
	assert not any("bare numbers" in problem for problem in check_report_gates(built.context, html))

	# The defect: a table cell that is a bare float, which the template's
	# `cell` macro would print as a plain number with no marker.
	leaky_rows = cast("list[list[ReportValue | str]]", [["Nairobi", 1200.0]])
	leaky = ReportTable(slug="leaky", title="Leaky", columns=["Item", "Value"], rows=leaky_rows)
	context = _context(sections=[ReportSection(slug="leaky", title="Leaky", tables=[leaky])])
	problems = check_report_gates(context)
	assert any("bare numbers" in problem for problem in problems), problems


def test_proxy_values_marked(tmp_path: Path):
	"""§9 ``test_proxy_values_marked``: a proxy renders with its marker.

	A report where a proxy estimate is indistinguishable from a measurement is
	a report that will be quoted as though the estimate were metered, and the
	person quoting it will not have been careless.
	"""
	built = _daily(tmp_path)
	html = built.paths["html"].read_text()
	proxies = built.context.proxied_values
	assert proxies, "the fixture set carries no proxy, so the gate measures nothing"
	for value in proxies:
		assert value.marker == PROXY_MARKER, value.label
		assert value.marker in html, f"{value.label}: proxy rendered with no marker"

	# The defect: a proxy whose marker is absent from the rendered HTML. The
	# value and its marker live in separate elements, so the gate checks both.
	unmarked = _value(basis=Basis.PROXY, value=95.0, uncertainty=0.3)
	context = _context(sections=[ReportSection(slug="s", title="S", values=[unmarked])])
	problems = check_report_gates(context, rendered_html="<p>95</p>")
	assert any("marker" in problem for problem in problems), problems


def test_precision_matches_uncertainty(tmp_path: Path):
	"""§9 ``test_precision_matches_uncertainty``: ±30% renders ≤ 2 sig figs.

	A proxy estimate with ±30% uncertainty rendered as ``1,234 MW`` claims three
	figures of precision that do not exist. Report readers quote the digits they
	are given.
	"""
	built = _daily(tmp_path)
	proxies = built.context.proxied_values
	assert proxies
	for value in proxies:
		assert value.figures <= 2, (
			f"{value.label}: {value.uncertainty:.0%} uncertainty rendered "
			f"{value.figures} significant figures"
		)

	# The defect: the same 30% proxy rendered to four significant figures.
	over_precise = _value(basis=Basis.PROXY, value=1234.0, uncertainty=0.3, significant_figures=4)
	context = _context(sections=[ReportSection(slug="s", title="S", values=[over_precise])])
	problems = check_report_gates(context)
	assert any("significant figures" in problem for problem in problems), problems


def test_table_and_chart_agree(tmp_path: Path):
	"""§9 ``test_table_and_chart_agree``: the chart's data is the table's data.

	A chart is a view of the data, not a second data path. A chart rendered from
	its own copy of the numbers is how a report's table and its chart come to
	tell different stories.
	"""
	values = [_value(value=10.0, label="a"), _value(value=20.0, label="b")]
	table = ReportTable(
		slug="mix",
		title="Mix",
		columns=["Item", "Value", "Basis"],
		rows=[[value.label, value, value.basis.value] for value in values],
	)
	chart = ReportChart(slug="mix", title="Mix", values=list(values))
	section = ReportSection(slug="mix", title="Mix", values=values, tables=[table], charts=[chart])
	assert chart_matches_table(chart, table)
	assert not any("disagree" in problem for problem in check_report_gates(_context(sections=[section])))

	# The defect: the chart plots a value the table does not print.
	ghost = _value(value=999.0, label="ghost")
	diverged = ReportChart(slug="mix", title="Mix", values=[*values, ghost])
	bad = ReportSection(slug="mix", title="Mix", values=values, tables=[table], charts=[diverged])
	problems = check_report_gates(_context(sections=[bad]))
	assert any("disagree" in problem for problem in problems), problems


def test_html_pdf_pair_exists(tmp_path: Path):
	"""§9 ``test_html_pdf_pair_exists``: every HTML has a non-empty PDF.

	The PDF is not checksum-stable, so the drift gate diffs the HTML and this
	asserts separately the thing that matters about the PDF: that it exists and
	has content.
	"""
	built = _daily(tmp_path, pdf=True)
	root = built.paths["html"].parent
	assert set(built.paths) == {"html", "pdf"}, built.paths
	assert built.paths["pdf"].stat().st_size > 0
	assert missing_or_empty_pdfs(root) == []
	assert drift_gate(root)["ok"]

	# The defect: the PDF is deleted from under the HTML.
	built.paths["pdf"].unlink()
	missing = missing_or_empty_pdfs(root)
	assert missing == [built.paths["html"].name], missing
	assert not drift_gate(root)["ok"], "a missing PDF did not fail the pair check"


def test_drift_gate_covers_html_only(tmp_path: Path):
	"""§9 ``test_drift_gate_covers_html_only``: the drift gate diffs HTML, not PDF.

	A PDF is stamped with render metadata, so two renders of an unchanged
	document differ by bytes and a gate that diffed them could never pass -- and
	a gate that cannot pass is indistinguishable from no gate.
	"""
	root = tmp_path / "reports"
	root.mkdir()
	(root / "r.html").write_text("<p>v1</p>", encoding="utf-8")
	before = drift_gate(root)["checksums"]
	assert before == {"r.html": before["r.html"]}

	# Add a PDF. It is not HTML, so the checksum map is unchanged and the gate
	# still passes -- which is the whole scoping claim.
	(root / "r.pdf").write_bytes(b"%PDF-1.4 stamped with render metadata")
	report = drift_gate(root, before=before)
	assert report["checksums"] == before, "a PDF changed the HTML checksums; the gate is not scoped"
	assert report["drift_clean"] and report["ok"], report

	# A changed HTML is still caught.
	(root / "r.html").write_text("<p>v2</p>", encoding="utf-8")
	assert drift_gate(root, before=before)["drift"]["changed"] == ["r.html"]


def test_delivery_recorded(tmp_path: Path):
	"""§9 ``test_delivery_recorded``: every send writes a DeliveryResult.

	A report that was generated but not delivered is a report that was not
	published, and the platform must be able to say which. The record is the
	only thing that distinguishes the two.
	"""
	results, reports = tmp_path / "results", tmp_path / "reports"
	write_all_fixture_sets(results)
	built = build_report(
		ReportCadence.DAILY,
		_config(results, reports, pdf_enabled=False),
		out=reports / "daily",
		date=AS_OF,
		deliver=True,
	)
	assert built.deliveries, "a build with deliver=True recorded no delivery"
	assert all(isinstance(delivery, DeliveryResult) for delivery in built.deliveries)

	records = sorted((reports / "daily" / "deliveries").glob("*.json"))
	assert records, "no delivery record reached disk"
	payload = json.loads(records[-1].read_text(encoding="utf-8"))
	assert payload["status"] in {"sent", "failed", "skipped"}
	assert payload["report_id"] == built.report_id

	# The record is written for a skip as well as a send: the disabled-email
	# path is the one most likely to be silently unrecorded.
	directory = tmp_path / "records"
	skipped = record_delivery("email", [], "skipped", report_id="r", directory=directory)
	assert skipped.status == "skipped"
	assert len(list(directory.glob("*.json"))) == 1


def test_config_validated_at_load(tmp_path: Path):
	"""§9 ``test_config_validated_at_load``: missing SMTP config fails at load.

	An email channel with no SMTP configuration must fail when the config
	loads, not at 06:00 when the report is due and nobody is watching.
	"""
	# The defect: email_enabled with no smtp_host or email_from.
	with pytest.raises(ConfigError, match="email_enabled requires smtp_host"):
		load_config(overrides={"reporting": {"email_enabled": True}})

	# The clean case loads, and the service's filesystem check passes with it.
	config = _config(
		tmp_path / "results",
		tmp_path / "reports",
		email_enabled=True,
		smtp_host="smtp.example.org",
		email_from="reports@example.org",
	)
	assert validate_reporting_config(config).email_enabled


def test_scheduled_matches_manual(tmp_path: Path):
	"""§9 ``test_scheduled_matches_manual``: the scheduler's report is the CLI's.

	Both paths call `build_report`, so a backfilled report is the same artefact
	a scheduled run would have produced. That is what makes the monthly "actual
	versus forecast" comparison possible: a forecast can only be compared
	against if the month it was issued for can be regenerated.
	"""
	results, reports = tmp_path / "results", tmp_path / "reports"
	today = datetime.now(UTC).date()
	shapes = declared_shapes(ReportCadence.DAILY, today)
	for pattern in declared_artefacts(ReportCadence.DAILY, today):
		columns, categorical = shapes[pattern]
		write_fixture_artefact(
			results / pattern, DEFAULT_ROWS, columns=columns, categorical=categorical
		)
	config = _config(results, reports, pdf_enabled=False)

	scheduled = run_cadence(ReportCadence.DAILY, config, run_id="scheduled")
	manual = build_report(
		ReportCadence.DAILY, config, out=reports / "manual", date=scheduled.as_of, run_id="manual"
	)

	assert scheduled.as_of == manual.as_of == today
	assert scheduled.report_id == manual.report_id, "the two paths minted different report ids"
	assert _report_fingerprint(scheduled.context) == _report_fingerprint(manual.context)
	assert [section.slug for section in scheduled.context.sections] == [
		section.slug for section in manual.context.sections
	]


def test_no_unverified_benchmark(tmp_path: Path):
	"""§9 ``test_no_unverified_benchmark``: no ``[UNVERIFIED]`` figure is published.

	AD-10's honesty rule is only real if a check fails when one appears. The
	annual report's unresolved benchmarks are printed with their status in the
	unverified block, never with the token in a table or a sentence.
	"""
	results, reports = tmp_path / "results", tmp_path / "reports"
	write_all_fixture_sets(results)
	built = build_report(
		ReportCadence.ANNUAL,
		_config(results, reports, pdf_enabled=False),
		out=reports / "annual",
		date=AS_OF,
		deliver=False,
	)
	html = built.paths["html"].read_text()
	assert built.context.unresolved_unverified, "the annual report carries no unverified register"
	assert find_unverified_token(built.context, html) == []
	assert UNVERIFIED_TOKEN not in html
	assert_no_unverified(html, built.context)

	# The defect: a figure pasted in carrying the token.
	poisoned = _context(
		sections=[
			ReportSection(
				slug="s",
				title="S",
				prose=f"Capacity was {UNVERIFIED_TOKEN} 1,234 MW last year.",
			)
		]
	)
	assert find_unverified_token(poisoned) != []
	with pytest.raises(ReportDataError, match="UNVERIFIED"):
		assert_no_unverified("", poisoned)
	# The token is caught in the rendered HTML as well as in the context.
	assert find_unverified_token(_context(sections=[]), f"<p>{UNVERIFIED_TOKEN} 1,234</p>") != []


def test_an_interval_in_the_artefact_reaches_the_interval_column(tmp_path: Path):
	"""§9 ``test_every_value_has_provenance``'s sibling: a band that survives the read.

	``reporting/daily.py``'s ``outage_forecast`` section declares an ``Interval``
	column and its module docstring says a 12% forecast renders with its band
	"because 'outage: yes' for a 12% forecast is a forecast rendered as a fact".
	Nothing read the band out of the artefact: ``ReportValue.interval`` was set
	by no line in ``src/alea``, and ``interval_text`` -- what ``_rows_for``
	writes into that column -- is empty unless it is. The column rendered blank
	in every daily report, and no gate noticed because the fixture writes one
	``value`` column per row and the reader had nothing to be missing.

	The round trip, not the reader. A test that sets ``interval`` on a
	hand-built ``ReportValue`` asserts the renderer and says nothing about
	whether an artefact's band ever gets there, which is the half that was
	broken.
	"""
	from alea.io.artefacts import write_artefact
	from alea.reporting.assemble import values_from_artefact
	from alea.reporting.service import _rows_for

	frame = pd.DataFrame(
		{
			"label": ["Line A", "Line B"],
			"value": [0.12, 0.40],
			"unit": ["probability", "probability"],
			"interval_low": [0.04, 0.30],
			"interval_high": [0.25, 0.52],
		}
	)
	target = tmp_path / "forecast.parquet"
	write_artefact(target, frame, _derived_provenance())
	values = values_from_artefact(target)
	assert [value.interval for value in values] == [(0.04, 0.25), (0.30, 0.52)], (
		"the artefact carries a band per row and the read path dropped it"
	)

	columns = ["Line", "Probability", "Interval", "Basis"]
	rows = _rows_for(values, columns, slug="outage_forecast")
	rendered = [row[columns.index("Interval")] for row in rows]
	assert all(str(cell) for cell in rendered), f"the Interval column rendered empty: {rendered}"
	assert "0.04" in str(rendered[0]), f"the band is not in the cell: {rendered[0]!r}"

	# The half-interval defect: one bound is not an interval, and printing it as
	# `low-high` would pair a number with a bound that belongs to nothing.
	partial = pd.DataFrame(
		{
			"label": ["Line A"],
			"value": [0.12],
			"unit": ["probability"],
			"interval_low": [0.04],
		}
	)
	half = tmp_path / "half.parquet"
	write_artefact(half, partial, _derived_provenance())
	assert values_from_artefact(half)[0].interval is None, (
		"a one-sided bound was read as an interval"
	)


def test_a_band_in_the_artefact_reaches_the_category_column(tmp_path: Path):
	"""The text half of the same read: a severity band survives into its column.

	``daily.py``'s ``system_alerts`` declares ``["Element", "State", "Basis"]``
	and ``State`` is a category -- ``publish.views.RESILIENCE_CONTINGENCY``
	types it ``str`` and ``project_resilience_contingency`` bands each element
	into ``"high"``/``"medium"``/``"low"``. The reader had no path for a text
	cell: ``values_from_artefact`` kept only the *numeric* columns as ``extra``,
	so ``state`` was dropped on read, and ``_rows_for`` -- which binds every
	non-first column to a number -- printed the element's load shed under a
	header promising a state. Measured on a contingency frame: the projection
	guard passed, the read dropped the column, and the row rendered
	``["line_a", 150.0, "modelled"]``.

	The round trip again, because a hand-built ``ReportValue`` with
	``categories`` set asserts the renderer and says nothing about whether an
	artefact's band ever reaches it.
	"""
	from alea.io.artefacts import write_artefact
	from alea.reporting.assemble import values_from_artefact
	from alea.reporting.service import _rows_for

	frame = pd.DataFrame(
		{
			"label": ["line_a", "line_b"],
			"value": [150.0, 8.0],
			"unit": ["MW", "MW"],
			"state": ["high", "low"],
		}
	)
	target = tmp_path / "contingency.parquet"
	write_artefact(target, frame, _derived_provenance())
	values = values_from_artefact(target)
	assert [dict(value.categories).get("state") for value in values] == ["high", "low"], (
		"the artefact carries a band per row and the read path dropped it"
	)

	columns = ["Element", "State", "Basis"]
	rows = _rows_for(values, columns, slug="system_alerts", categorical=("State",))
	assert [row[columns.index("State")] for row in rows] == ["high", "low"], (
		f"the State column does not carry the band: {rows}"
	)

	# The refusal, which is what makes the declaration load-bearing. A frame
	# with no `state` column is a frame the reader must not paper over: with one
	# numeric column the fallback would put the load shed under `State`.
	without = pd.DataFrame({"label": ["line_a"], "value": [150.0], "unit": ["MW"]})
	bare = tmp_path / "bare.parquet"
	write_artefact(bare, without, _derived_provenance())
	with pytest.raises(ReportDataError, match="declared a category"):
		_rows_for(
			values_from_artefact(bare),
			columns,
			slug="system_alerts",
			categorical=("State",),
		)


def _derived_provenance() -> DerivedProvenance:
	"""A derived provenance carrying an input, which ``write_artefact`` requires.

	``DerivedProvenance`` refuses an artefact that records no input checksum,
	because a result that cannot be traced to what produced it is not derived
	from anything.
	"""
	return DerivedProvenance(
		source_id="outage_forecast",
		basis=Basis.MEASURED,
		inputs=["fixture:outage_forecast"],
		run_id="00000000-0000-7000-8000-000000000000",
	)
