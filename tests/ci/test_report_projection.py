# SPDX-License-Identifier: MIT
"""A produced section is deliverable: the stage's artefact reaches the report.

WHY this module exists. `reporting/producers.py`'s ``PRODUCERS`` records the
*function* that writes a section's rows, and every rule writes them under
``paths.processed``. A section reads ``results/<dir>/{date}.parquet``. Nothing
bridged the two: `alea.io.artefacts.copy_artefact` was defined, exported in two
``__all__``s, and called by zero functions, rules or CLI commands.

The failure was invisible to every existing test. `tests/fixtures/reporting`
writes each declared dated path *by hand*, so the cadence tests pass; each
producer's own tests assert its frame's columns, so they pass too; and the
register's gate checks that the producer's *name* appears in the source. All
three are true of a pipeline that cannot deliver a single section. Measured
2026-10-13 by running `rules/reporting.smk`'s exact command and then `alea
report monthly`: the build exited 0, the dated path was absent, and the report
exited 1 with ``ReportDataError: Market report: no artefact at ...``.

**Why the assertion is a report and not a file.** Asserting the destination
exists would pass for a copy written to a path the reader does not compute.
The claim under test is that a report generated from the pipeline can read the
section, so the test builds one and looks for the section in it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, write_artefact
from alea.planning.arrays import build_capacity_update
from alea.provenance.models import Basis, DerivedProvenance
from alea.reporting.projection import project_section, unprojected_sections
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import section_artefact_path, section_by_slug

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")
ISSUE_DATE = date(2030, 2, 1)
"""The monthly report's issue date; its period end is 2030-01-31."""

PERIOD_END = date(2030, 1, 31)


def _network(coal_mw: float) -> pypsa.Network:
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add("Line", "n-s", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=400.0)
	network.add("Generator", "coal", bus="north", carrier="coal", p_nom=coal_mw, marginal_cost=45.0)
	network.add("Load", "load", bus="south", p_set=120.0)
	return network


def _config(tmp_path: Path) -> Config:
	return load_config(
		overrides=[
			f"paths.processed={tmp_path / 'processed'}",
			f"paths.results={tmp_path / 'results'}",
			f"paths.reports={tmp_path / 'reports'}",
			"reporting.pdf_enabled=false",
		]
	)


class _Context:
	def __init__(self, parameters: dict[str, object] | None = None) -> None:
		self.out: Path | None = None
		self.inputs: list[str] = []
		self.logger = None
		self.parameters = dict(parameters or {})


def _stage_output(tmp_path: Path, config: Config, *, previous: bool = False) -> Path:
	"""Run the real stage, so the source is the artefact the rule produces.

	``previous`` writes a second, earlier solve so the stage produces a
	``change`` column. With one solve the section's declared "Change" header
	cannot be filled, which is a different test's subject.
	"""
	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	older = directory / "aaaa1111-2030.nc"
	_network(300.0).export_to_netcdf(str(older))
	if previous:
		# `_newest_network` orders by mtime, so the newer solve must be written
		# second or the stage differences against the wrong one.
		_network(400.0).export_to_netcdf(str(directory / "bbbb2222-2030.nc"))
	out = Path(config.paths.processed) / "capacity_update.parquet"
	build_capacity_update(config, out, _Context({"network_dir": str(directory)}))  # type: ignore[arg-type]
	return out


# --------------------------------------------------------------------------
# The gap, measured
# --------------------------------------------------------------------------


def test_the_stage_writes_a_path_the_section_does_not_read(tmp_path: Path):
	"""The defect stated as a fact, so it cannot come back unnoticed.

	A stage output under ``paths.processed`` is not the section's artefact, and
	this asserts the two differ -- which is what makes the projection a
	necessary step rather than a redundant copy.
	"""
	config = _config(tmp_path)
	source = _stage_output(tmp_path, config)
	spec = section_by_slug(ReportCadence.MONTHLY, "capacity_update")
	target = section_artefact_path(spec, config, PERIOD_END)
	assert source.exists()
	assert source != target, (
		"the stage writes the section's dated path directly; if that is now true "
		"the projection is redundant and this test should be deleted with it"
	)
	assert not target.exists(), (
		"the section's artefact exists before anything projected it; either the "
		"stage now writes it or a previous test left state behind"
	)


def test_the_projection_lands_the_artefact_where_the_reader_looks(tmp_path: Path):
	"""The positive half: the copy is at the path the reader computes."""
	config = _config(tmp_path)
	source = _stage_output(tmp_path, config, previous=True)
	target = project_section(
		ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE
	)
	assert target.exists(), "the projection wrote nothing"
	assert target == section_artefact_path(
		section_by_slug(ReportCadence.MONTHLY, "capacity_update"), config, PERIOD_END
	), "the projection wrote a path the section does not declare"


def test_the_dated_path_is_the_period_end_and_not_the_issue_date(tmp_path: Path):
	"""A projection stamped with the run date writes a file no report opens.

	A monthly report issued on the 1st covers the month that just ended, and
	`period_for` is what the reader uses. A projection that used ``as_of``
	directly would write ``2030-02-01.parquet`` while the reader looked for
	``2030-01-31.parquet`` -- and the symptom is an absent section, not an error.
	"""
	config = _config(tmp_path)
	source = _stage_output(tmp_path, config, previous=True)
	target = project_section(
		ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE
	)
	assert target.name == f"{PERIOD_END:%Y-%m-%d}.parquet", (
		f"the projection stamped {target.name}; the monthly period ending before "
		f"{ISSUE_DATE} is {PERIOD_END}, which is where the reader looks"
	)
	assert not (target.parent / f"{ISSUE_DATE:%Y-%m-%d}.parquet").exists(), (
		"a second copy under the issue date was written; a report reads one path "
		"and an extra file is a second thing to drift"
	)


# --------------------------------------------------------------------------
# The claim that matters: a report reads the section
# --------------------------------------------------------------------------


def test_the_monthly_report_reads_the_projected_section(tmp_path: Path):
	"""The round trip through `build_report`, which is the whole point.

	Everything else in this repository passed while this failed: the producer's
	frame was right, the register named it, the cadence fixture wrote the dated
	path by hand. Only generating the report from the pipeline shows whether the
	section is deliverable.
	"""
	from alea.reporting.service import build_report

	config = _config(tmp_path)
	# Two solves, so the stage writes the ``change`` column the section's
	# second numeric header binds. With one solve the section cannot be filled
	# at all, which `test_a_section_its_artefact_cannot_fill_is_refused` pins.
	source = _stage_output(tmp_path, config, previous=True)
	project_section(ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE)

	# `market_report` is the monthly cadence's other required section and has no
	# producer reachable from this fixture, so it is projected from a
	# hand-written frame to isolate the claim under test: that *this* section is
	# readable once projected. Without it `build_report` raises on the *other*
	# required section and the test would pass or fail for the wrong reason.
	_market_rows = pd.DataFrame(
		{"label": ["coal"], "value": [400.0], "unit": ["MWh"], "volume": [400.0], "average_price": [45.0]}
	)
	market_source = Path(config.paths.processed) / "market_report.parquet"
	write_artefact(
		market_source,
		_market_rows,
		DerivedProvenance(
			source_id="market_report", inputs=["fixture:network"], basis=Basis.MODELLED
		),
		format="parquet",
	)
	project_section(
		ReportCadence.MONTHLY, "market_report", market_source, config, as_of=ISSUE_DATE
	)

	built = build_report(
		ReportCadence.MONTHLY,
		config,
		tmp_path / "reports",
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	slugs = {section.slug for section in built.context.sections}
	assert "capacity_update" in slugs, (
		f"the monthly report generated without the capacity section; it carries "
		f"{sorted(slugs)}. The section's artefact is at "
		f"{section_artefact_path(section_by_slug(ReportCadence.MONTHLY, 'capacity_update'), config, PERIOD_END)}"
	)
	section = next(s for s in built.context.sections if s.slug == "capacity_update")
	rows = section.tables[0].rows
	assert rows, "the capacity section rendered with no rows"
	assert {str(row[0]) for row in rows} == {"coal"}, f"the rows are not carriers: {rows}"


def test_a_section_its_artefact_cannot_fill_is_refused(tmp_path: Path):
	"""One solve: the section declares "Change" and the artefact has no such column.

	This is the failure the first version of the projection produced. The stage
	omits ``change`` deliberately when there is nothing to difference against --
	inventing a zero would assert capacity did not move -- and `_rows_for` then
	refuses the section's second numeric header. Projecting anyway turns a
	producer-side omission into a report that raises, naming the section, so the
	projection refuses first and says which quantity is owed.
	"""
	config = _config(tmp_path)
	source = _stage_output(tmp_path, config)  # one solve, so no `change`
	with pytest.raises(ArtefactError, match="Change"):
		project_section(
			ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE
		)


def test_the_refusal_names_the_producer_that_owes_the_column(tmp_path: Path):
	"""A refusal an operator cannot act on is one they route around."""
	config = _config(tmp_path)
	source = _stage_output(tmp_path, config)
	with pytest.raises(ArtefactError) as raised:
		project_section(
			ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE
		)
	message = str(raised.value)
	assert str(source) in message, "the refusal does not name the artefact it read"
	assert "capacity_update" in message, "the refusal does not name the section"


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_a_slug_the_cadence_does_not_declare_is_refused(tmp_path: Path):
	"""A misspelled slug must not write somewhere plausible.

	The destination is the section's own declaration, so a slug that matches no
	section has no destination -- and inventing one would produce a file no
	report reads, which is the defect this module exists to remove.
	"""
	from alea.reporting.schemas import ReportDataError

	config = _config(tmp_path)
	# Two solves so the source would pass the fill check: this test is about the
	# slug, and a source that fails earlier would make it pass for the wrong
	# reason.
	source = _stage_output(tmp_path, config, previous=True)
	with pytest.raises(ReportDataError, match="declares no section"):
		project_section(ReportCadence.MONTHLY, "capacity_updates", source, config, as_of=ISSUE_DATE)


def test_a_source_that_is_not_there_is_refused(tmp_path: Path):
	"""A missing producer output names the producer, not the reader."""
	config = _config(tmp_path)
	with pytest.raises(ArtefactError, match="no artefact at"):
		project_section(
			ReportCadence.MONTHLY,
			"capacity_update",
			tmp_path / "nothing.parquet",
			config,
			as_of=ISSUE_DATE,
		)


def test_the_measurement_names_the_sections_a_cadence_cannot_deliver(tmp_path: Path):
	"""``unprojected_sections`` is the measurement ``PRODUCERS`` cannot make.

	The register says which sections have a writer. This says which of them a
	report can actually read, and the two answers differ for every section whose
	producer writes only the processed form.
	"""
	config = _config(tmp_path)
	missing = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "capacity_update" in missing, (
		"the capacity section reads as deliverable with nothing projected; the "
		"measurement is not reading the dated path"
	)

	source = _stage_output(tmp_path, config, previous=True)
	project_section(ReportCadence.MONTHLY, "capacity_update", source, config, as_of=ISSUE_DATE)
	after = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "capacity_update" not in after, "the projection did not change the measurement"
	assert len(after) == len(missing) - 1, (
		f"projecting one section changed the set by {len(missing) - len(after)}"
	)
