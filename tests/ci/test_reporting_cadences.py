# SPDX-License-Identifier: MIT
"""`09-layer6-reporting.md` exit criterion 1: all five cadences render end to end.

The criterion is a *fixture* deliverable, not a production-data one: every
section a cadence declares reads an artefact a lower layer owns, and no lower
layer exists yet, so before this test the only thing that could be asserted was
that the cadences fail. `tests/fixtures/reporting` writes those artefacts as
real payloads with real provenance sidecars; this module runs the real
`build_report` over them and asserts a report comes out.

The gate earns its place because a required section that resolves is not the
same as a report that renders: the sections are assembled, the context built,
the template rendered, and the index published, and any of those can fail while
every individual section reads fine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import build_report, cadence_specs
from tests.fixtures.reporting import (
	AS_OF,
	declared_artefacts,
	sections_without_fixtures,
	write_all_fixture_sets,
)


def _config(results_root: Path, reports_root: Path) -> Config:
	"""A config whose results root is the fixture tree and whose PDFs are off.

	Built through the real loader so the defaults a production run gets are the
	defaults this test exercises -- hand-validating a `Config` would test a
	configuration the CLI never produces. PDF rendering needs a headless
	browser; the criterion is that the report renders, and the HTML is the
	render, so turning PDF off keeps the test about the report rather than about
	Chromium being installed.
	"""
	return load_config(
		overrides={
			"paths": {"results": str(results_root), "reports": str(reports_root)},
			"reporting": {"pdf_enabled": False},
		}
	)


def test_the_fixture_set_covers_every_declared_section():
	"""A cadence that gains a section must gain a fixture, or this fails.

	Without it the fixture set falls behind silently and the render test below
	passes for the cadences that happen to be covered.
	"""
	for cadence in ReportCadence:
		missing = sections_without_fixtures(cadence, AS_OF)
		assert not missing, f"{cadence.value} declares sections with no fixture: {missing}"


def test_every_cadence_declares_at_least_one_required_section():
	"""The premise of the defect: each cadence has a required section.

	If a cadence had none, it would have rendered all along and this whole
	exercise would be measuring nothing.
	"""
	for cadence in ReportCadence:
		specs, _ = cadence_specs(cadence)
		assert any(spec.required for spec in specs), f"{cadence.value} has no required section"


@pytest.mark.parametrize("cadence", list(ReportCadence), ids=lambda c: c.value)
def test_each_cadence_renders_end_to_end_on_fixtures(cadence: ReportCadence, tmp_path: Path):
	"""The criterion itself, one cadence at a time so a failure names which."""
	results_root = tmp_path / "results"
	reports_root = tmp_path / "reports"
	written = write_all_fixture_sets(results_root)[cadence]
	assert written, f"{cadence.value} wrote no fixtures"

	built = build_report(
		cadence,
		_config(results_root, reports_root),
		out=reports_root / cadence.value,
		date=AS_OF,
		deliver=False,
	)

	assert built.cadence == cadence.value
	assert built.paths, f"{cadence.value} rendered no format"
	html = built.paths["html"]
	assert html.exists(), f"{cadence.value} reported {html} but wrote nothing"
	assert html.stat().st_size > 0, f"{cadence.value} wrote an empty report"
	assert built.context.values, f"{cadence.value} rendered with no values"


def test_the_declared_artefact_paths_are_the_ones_the_fixtures_write(tmp_path: Path):
	"""The fixture module and the cadence modules must agree on paths.

	`sections_without_fixtures` compares filenames; this compares the resolved
	path a section actually reads against a file the fixtures wrote, which is
	the stronger statement and the one that catches a directory-level drift.
	"""
	results_root = tmp_path / "results"
	write_all_fixture_sets(results_root)
	for cadence in ReportCadence:
		for pattern in declared_artefacts(cadence, AS_OF):
			assert (results_root / pattern).exists(), f"{cadence.value} reads {pattern}, not written"
