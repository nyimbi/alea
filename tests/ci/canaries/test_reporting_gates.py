# SPDX-License-Identifier: MIT
"""Canaries for `09-layer6-reporting.md` §8: watch each Layer 6 gate fail.

Every gate in §8's table is promised a canary that plants its defect and shows
the gate noticing. Most of these gates take a value object, so the defect is a
malformed `ReportContext` built directly and handed to `check_report_gates`.
Two of them -- delivery recording and config validation at load -- are code
paths rather than value shapes, and those use `planted` to blind the function
and run the gate in a subprocess against the mutated source.

A canary that passes without the gate failing proves nothing, so each asserts
the failure explicitly rather than trusting the gate's exit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from alea.config.loader import ConfigError, load_config
from alea.provenance.models import Basis, Licence, Provenance
from alea.reporting.render import fingerprint, missing_or_empty_pdfs
from alea.reporting.schemas import (
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
	assert_no_unverified,
	check_report_gates,
	drift_gate,
	find_unverified_token,
)
from tests.ci.canaries import REPO, assert_raises, planted

RENDER_PY = REPO / "src" / "alea" / "reporting" / "render.py"
MODELS_PY = REPO / "src" / "alea" / "config" / "models.py"
# `tests` is not part of the installed package, so a subprocess that reads the
# fixture module needs the repo root on its path.
ROOT = str(REPO)


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
		provenance=Provenance(
			source_id="canary",
			licence=Licence.CC_BY_4_0,
			basis=basis,
			uncertainty=uncertainty,
			uncertainty_basis="proxy" if uncertainty else "",
		),
		label=label,
		significant_figures=significant_figures,
	)


def _context(*, sections: list[ReportSection], **extra: object) -> ReportContext:
	when = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)
	return ReportContext(
		title="Canary report",
		cadence=ReportCadence.DAILY,
		as_of=when.date(),
		period_start=when.date(),
		period_end=when.date(),
		generated_at=when,
		timezone="UTC",
		sections=sections,
		**extra,
	)


def _run(program: str) -> subprocess.CompletedProcess[str]:
	"""Run a snippet against the tree as it stands on disk, with tests importable."""
	env = {**os.environ, "PYTHONPATH": ROOT}
	return subprocess.run(
		[sys.executable, "-c", program], capture_output=True, text=True, check=False, env=env
	)


# --------------------------------------------------------------------------
# test_every_value_has_provenance -- inject a float; must fail
# --------------------------------------------------------------------------


def test_every_value_has_provenance():
	"""A table cell that is a bare float must fail the report gate.

	The template's `cell` macro prints a float as a plain number with no basis
	and no provenance, which is the failure this layer exists to prevent. The
	scanner must see the float in a nested table, not just at the top level.
	"""
	leaky = ReportTable(
		slug="leaky",
		title="Leaky",
		columns=["Item", "Value"],
		rows=[["Nairobi", 1200.0]],  # type: ignore[list-item]  # the planted defect
	)
	context = _context(sections=[ReportSection(slug="leaky", title="Leaky", tables=[leaky])])
	assert find_bare_numbers(context), "the bare-number scanner is blind to a float in a table cell"
	assert any("bare numbers" in problem for problem in check_report_gates(context))


# --------------------------------------------------------------------------
# test_proxy_values_marked -- remove marker; must fail
# --------------------------------------------------------------------------


def test_proxy_values_marked():
	"""A proxy rendered without its marker must fail the report gate."""
	proxy = _value(basis=Basis.PROXY, value=95.0, uncertainty=0.3)
	context = _context(sections=[ReportSection(slug="s", title="S", values=[proxy])])
	# The marker is present in the value; the defect is the rendered HTML missing
	# it, which is what a template that printed the number without the macro
	# would produce.
	assert proxy.marker
	problems = check_report_gates(context, rendered_html="<p>95</p>")
	assert any("marker" in problem for problem in problems), problems


# --------------------------------------------------------------------------
# test_precision_matches_uncertainty -- render 4 digits; must fail
# --------------------------------------------------------------------------


def test_precision_matches_uncertainty():
	"""A ±30% proxy rendered to four significant figures must fail the gate."""
	over = _value(basis=Basis.PROXY, value=1234.0, uncertainty=0.3, significant_figures=4)
	context = _context(sections=[ReportSection(slug="s", title="S", values=[over])])
	assert over.figures == 4
	assert any("significant figures" in problem for problem in check_report_gates(context))


# --------------------------------------------------------------------------
# test_table_and_chart_agree -- diverge them; must fail
# --------------------------------------------------------------------------


def test_table_and_chart_agree():
	"""A chart plotting a value its table does not print must fail the gate."""
	values = [_value(value=10.0, label="a"), _value(value=20.0, label="b")]
	table = ReportTable(
		slug="mix",
		title="Mix",
		columns=["Item", "Value", "Basis"],
		rows=[[value.label, value, value.basis.value] for value in values],
	)
	ghost = _value(value=999.0, label="ghost")  # the planted divergence
	chart = ReportChart(slug="mix", title="Mix", values=[*values, ghost])
	section = ReportSection(slug="mix", title="Mix", values=values, tables=[table], charts=[chart])
	assert not chart_matches_table(chart, table)
	assert any("disagree" in problem for problem in check_report_gates(_context(sections=[section])))


# --------------------------------------------------------------------------
# test_html_pdf_pair_exists -- delete a PDF; must fail
# --------------------------------------------------------------------------


def test_html_pdf_pair_exists(tmp_path: Path):
	"""Deleting the PDF beside an HTML must fail the pair check."""
	root = tmp_path / "reports"
	root.mkdir()
	(root / "r.html").write_text("<p>report</p>", encoding="utf-8")
	(root / "r.pdf").write_bytes(b"%PDF-1.4 real bytes")
	assert missing_or_empty_pdfs(root) == []

	(root / "r.pdf").unlink()  # the planted defect
	assert missing_or_empty_pdfs(root) == ["r.html"]
	assert not drift_gate(root)["ok"], "the pair gate passed with no PDF beside the HTML"


# --------------------------------------------------------------------------
# test_drift_gate_covers_html_only -- add PDF; gate must still pass
# --------------------------------------------------------------------------


def test_drift_gate_covers_html_only(tmp_path: Path):
	"""Adding a PDF must leave the HTML drift gate passing.

	The plan's canary is the *positive* case: a PDF is not byte-reproducible, so
	if adding one moved the gate the gate could never pass on a clean tree. The
	gate must ignore it and still catch a changed HTML.
	"""
	root = tmp_path / "reports"
	root.mkdir()
	(root / "r.html").write_text("<p>v1</p>", encoding="utf-8")
	before = drift_gate(root)["checksums"]

	(root / "r.pdf").write_bytes(b"%PDF-1.4 stamped with render metadata")
	report = drift_gate(root, before=before)
	assert report["checksums"] == before, "a PDF entered the HTML checksums; the gate is not scoped"
	assert report["ok"], report

	(root / "r.html").write_text("<p>v2</p>", encoding="utf-8")
	assert drift_gate(root, before=before)["drift"]["changed"] == ["r.html"]


# --------------------------------------------------------------------------
# test_delivery_recorded -- drop the record; must fail
# --------------------------------------------------------------------------

_DELIVERY_PROGRAM = (
	"import tempfile\n"
	"from pathlib import Path\n"
	"from alea.config.loader import load_config\n"
	"from alea.reporting.service import build_report\n"
	"from tests.fixtures.reporting import AS_OF, write_all_fixture_sets\n"
	"tmp = Path(tempfile.mkdtemp())\n"
	"results, reports = tmp / 'results', tmp / 'reports'\n"
	"write_all_fixture_sets(results)\n"
	"cfg = load_config(overrides={'paths': {'results': str(results), 'reports': str(reports)},\n"
	"  'reporting': {'pdf_enabled': False}})\n"
	"built = build_report('daily', cfg, out=reports / 'daily', date=AS_OF, deliver=True)\n"
	"on_disk = list((reports / 'daily' / 'deliveries').glob('*.json'))\n"
	"print('deliveries:', len(built.deliveries), 'on_disk:', len(on_disk))\n"
)


def _delivery_records() -> str:
	completed = _run(_DELIVERY_PROGRAM)
	assert completed.returncode == 0, completed.stderr
	return completed.stdout.strip()


def test_delivery_recorded():
	"""Dropping the delivery record must fail the gate.

	The writer is blinded at the source and the build run in a subprocess: the
	in-memory `DeliveryResult` is still returned, so only the disk check notices
	-- which is the "generated but not delivered" invisibility the gate exists
	to prevent.
	"""
	assert _delivery_records().endswith("on_disk: 1"), "the shipped build wrote no record to check"

	with planted(
		RENDER_PY,
		'\ttarget.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")',
		"\tpass",
	):
		blinded = _delivery_records()
	assert blinded.endswith("on_disk: 0"), (
		f"the gate still found a record with the writer blinded: {blinded}"
	)
	# Restored from the backup by `planted`; the record is written again.
	assert _delivery_records().endswith("on_disk: 1")


# --------------------------------------------------------------------------
# test_config_validated_at_load -- remove config; must fail
# --------------------------------------------------------------------------

_CONFIG_PROGRAM = (
	"from alea.config.loader import load_config\n"
	"try:\n"
	"  load_config(overrides={'reporting': {'email_enabled': True}})\n"
	"  print('loaded')\n"
	"except Exception as exc:\n"
	"  print('refused:', type(exc).__name__)\n"
)


def _config_load() -> str:
	completed = _run(_CONFIG_PROGRAM)
	assert completed.returncode == 0, completed.stderr
	return completed.stdout.strip()


def test_config_validated_at_load():
	"""An email channel with no SMTP config must be refused at load.

	The validator is neutered at the source and the load run in a subprocess;
	with it relaxed the same config loads clean, and the missing host would
	surface at 06:00 instead -- after the report is built.
	"""
	# The gate, as shipped.
	assert_raises(ConfigError, lambda: load_config(overrides={"reporting": {"email_enabled": True}}))
	assert _config_load() == "refused: ConfigError"

	with planted(
		MODELS_PY,
		"\t\tif self.email_enabled and not (self.smtp_host and self.email_from):",
		"\t\tif False and self.email_enabled and not (self.smtp_host and self.email_from):",
	):
		blinded = _config_load()
	assert blinded == "loaded", (
		f"the config was still refused with the validator relaxed: {blinded}"
	)
	assert _config_load() == "refused: ConfigError"


# --------------------------------------------------------------------------
# test_scheduled_matches_manual -- diverge; must fail
# --------------------------------------------------------------------------


def test_scheduled_matches_manual():
	"""A report whose values differ from the scheduled one must fail the gate.

	The gate compares the two paths by a fingerprint of the report's values; a
	divergence in any value must move that fingerprint, or the gate would call
	two different reports identical.
	"""
	left = _context(sections=[ReportSection(slug="s", title="S", values=[_value(value=1.0)])])
	right = _context(sections=[ReportSection(slug="s", title="S", values=[_value(value=2.0)])])
	assert fingerprint([v.value for v in left.values]) != fingerprint([v.value for v in right.values])

	# A same-valued context fingerprints the same, so the comparison is not
	# simply always-unequal.
	same = _context(sections=[ReportSection(slug="s", title="S", values=[_value(value=1.0)])])
	assert fingerprint([v.value for v in left.values]) == fingerprint([v.value for v in same.values])


# --------------------------------------------------------------------------
# test_no_unverified_benchmark -- inject one; must fail
# --------------------------------------------------------------------------


def test_no_unverified_benchmark():
	"""An injected ``[UNVERIFIED]`` token must fail the gate."""
	poisoned = _context(
		sections=[
			ReportSection(slug="s", title="S", prose=f"Capacity was {UNVERIFIED_TOKEN} 1,234 MW.")
		]
	)
	assert find_unverified_token(poisoned) != []
	assert_raises(ReportDataError, assert_no_unverified, "", poisoned)
	# And in the rendered HTML, where a pasted figure actually lands.
	assert find_unverified_token(_context(sections=[]), f"<p>{UNVERIFIED_TOKEN}</p>") != []


# --------------------------------------------------------------------------
# test_no_repeated_table_cell -- plant a duplicated cell; must fail
# --------------------------------------------------------------------------


def test_no_repeated_table_cell():
	"""A row printing one number in two columns must fail the gate.

	The defect this watches for was live and silent: `_rows_for` filled every
	numeric column with the row's primary value, so ``Hours`` printed the peak
	loading and SAIFI printed SAIDI. The gate's whole value is that it fails on
	a duplicated cell, so the canary builds one directly -- a table whose two
	numeric columns hold the same formatted number -- and asserts the gate
	reports it.

	A row whose numbers genuinely coincide is indistinguishable from this
	defect, and that is deliberate: a reader cannot tell either, so the producer
	must carry a distinct quantity per column or the report is not publishable.
	"""
	first = _value(value=1200.0, label="north-south")
	second = _value(value=1200.0, label="north-south")
	table = ReportTable(
		slug="critical_lines",
		title="Lines at or above rating",
		columns=["Line", "Peak loading", "Hours", "Basis"],
		rows=[[first.label, first, second, first.basis.value]],
	)
	section = ReportSection(
		slug="critical_lines", title="Critical lines", values=[first], tables=[table]
	)
	problems = check_report_gates(_context(sections=[section]))
	assert any("repeats a value" in problem for problem in problems), problems

	# And the correct shape passes: two distinct quantities in the two columns.
	distinct = _value(value=1440.0, label="north-south")
	good = ReportTable(
		slug="critical_lines",
		title="Lines at or above rating",
		columns=["Line", "Peak loading", "Hours", "Basis"],
		rows=[[first.label, first, distinct, first.basis.value]],
	)
	clean = ReportSection(
		slug="critical_lines", title="Critical lines", values=[first], tables=[good]
	)
	assert not [
		problem
		for problem in check_report_gates(_context(sections=[clean]))
		if "repeats a value" in problem
	], "the gate fires on a table whose columns carry distinct numbers"
