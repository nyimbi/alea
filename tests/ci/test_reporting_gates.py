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

import pytest

from alea.config.loader import ConfigError, load_config
from alea.provenance.models import Basis, Licence, Provenance
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
	for pattern in declared_artefacts(ReportCadence.DAILY, today):
		write_fixture_artefact(results / pattern, DEFAULT_ROWS)
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
