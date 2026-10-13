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
from alea.reporting.schemas import ReportCadence, period_for
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


# --------------------------------------------------------------------------
# The other three: the same claim, per section, through a real report
# --------------------------------------------------------------------------


def _solved(tmp_path: Path, config: Config) -> pypsa.Network:
	"""A solved two-carrier network under ``results/networks``.

	Solved rather than hand-built, because the producers read a *solve*: the
	monthly frame is one row per carrier that dispatched, and a network with no
	dispatch has no market to clear.
	"""
	import pypsa

	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add("Line", "n-s", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=400.0)
	network.add(
		"Generator", "coal", bus="north", carrier="coal", p_nom=300.0, marginal_cost=45.0
	)
	network.add(
		"Generator", "hydro", bus="south", carrier="hydro", p_nom=200.0, marginal_cost=5.0
	)
	network.add("Load", "load", bus="south", p_set=120.0)
	network.optimize()
	network.export_to_netcdf(str(directory / "aaaa1111-2030.nc"))
	return network


def _projected_source(tmp_path: Path, config: Config, stage: str) -> Path:
	"""Run the registered stage whose artefact the projection moves.

	Through `build_stage` rather than by calling the producer, so the fixture
	writes exactly what the rule's command writes -- including the sidecar the
	projection's `read_artefact` verifies.
	"""
	from alea.io.pipeline import build_stage

	directory = str(tmp_path / "results" / "networks")
	out = Path(config.paths.processed) / f"{stage}.parquet"
	result = build_stage(
		stage, config, out, inputs=[], parameters={"network_dir": directory}
	)
	assert not result.skipped, f"{stage} skipped; the fixture wrote nothing"
	return out


@pytest.mark.parametrize(
	("cadence", "slug"),
	[
		(ReportCadence.WEEKLY, "critical_lines"),
		(ReportCadence.MONTHLY, "market_report"),
		(ReportCadence.QUARTERLY, "market_outlook"),
		(ReportCadence.DAILY, "generation_mix"),
		(ReportCadence.DAILY, "price_forecast"),
	],
	ids=lambda value: value.value if isinstance(value, ReportCadence) else value,
)
def test_every_projected_section_lands_where_its_cadence_reads(
	tmp_path: Path, cadence: ReportCadence, slug: str
):
	"""The projections after `capacity_update`, one claim per section.

	Each is asserted the same way the capacity one is, and for the same reason:
	the destination must be the path the *reader* computes, resolved from the
	cadence's period. `market_outlook` is the one that would be wrong under a
	projection that stamped its run date -- a quarterly report issued in April
	reads the quarter ending 31 March, so the file is named for a day that is
	not the day the rule ran. The two daily ones are the sharpest case of it: a
	daily report generated at 06:00 covers *yesterday*, so a projection that
	used the issue date would write a file no report opens and the symptom would
	be an absent section rather than an error.
	"""
	config = _config(tmp_path)
	if slug in {"market_report", "market_outlook", "generation_mix", "price_forecast"}:
		_solved(tmp_path, config)
	else:
		# `critical_lines` reads the arrays and dispatch artefacts rather than a
		# solved network, so it needs the tree `test_loading.py` builds.
		from tests.ci.test_loading import _stage_tree

		_stage_tree(tmp_path)
	source = _projected_source(tmp_path, config, slug)

	report_date = period_for(cadence, ISSUE_DATE)[1]
	target = project_section(cadence, slug, source, config, as_of=ISSUE_DATE)
	assert target == section_artefact_path(section_by_slug(cadence, slug), config, report_date), (
		f"{slug}: the projection wrote {target}, and the reader computes "
		f"{section_artefact_path(section_by_slug(cadence, slug), config, report_date)}"
	)
	assert target.exists(), f"{slug}: the projection wrote nothing"
	assert unprojected_sections(cadence, config, as_of=ISSUE_DATE).count(slug) == 0, (
		f"{slug} still reads as undelivered after being projected"
	)


def test_the_weekly_report_reads_the_projected_critical_lines(tmp_path: Path):
	"""The round trip for a non-required section, through the real report.

	`critical_lines` is optional to the weekly cadence, so a report generates
	without it and warns -- which is exactly why asserting the *file* exists is
	not enough. The claim is that the section appears in a generated report, and
	only generating one shows that.
	"""
	from alea.reporting.service import build_report
	from tests.ci.test_loading import _stage_tree

	config = _config(tmp_path)
	_stage_tree(tmp_path)
	# The weekly cadence's *required* section has no producer at all, so it is
	# projected from a hand-written frame: without it `build_report` raises on
	# that section and this test would pass or fail for the wrong reason.
	# The frame carries a column per numeric header the section declares. Not a
	# convenience: `_rows_for` refuses a numeric column whose quantity the row
	# does not carry, and `week_ahead` declares three -- the section's declared
	# `unit` is "MW", so the primary binds to a *`demand` column* and not to the
	# row's unit. A fixture with only `value` would raise in the reader, and this
	# test would then be measuring the fixture rather than the projection.
	_week_ahead = pd.DataFrame(
		{
			"label": ["Mon"],
			"value": [120.0],
			"unit": ["MW"],
			"demand": [120.0],
			"renewable": [40.0],
			"margin": [80.0],
		}
	)
	required_source = Path(config.paths.processed) / "week_ahead.parquet"
	write_artefact(
		required_source,
		_week_ahead,
		DerivedProvenance(
			source_id="week_ahead", inputs=["fixture:network"], basis=Basis.MODELLED
		),
		format="parquet",
	)
	project_section(ReportCadence.WEEKLY, "week_ahead", required_source, config, as_of=ISSUE_DATE)

	source = _projected_source(tmp_path, config, "critical_lines")
	project_section(ReportCadence.WEEKLY, "critical_lines", source, config, as_of=ISSUE_DATE)

	built = build_report(
		ReportCadence.WEEKLY,
		config,
		tmp_path / "reports",
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	slugs = {section.slug for section in built.context.sections}
	assert "critical_lines" in slugs, (
		f"the weekly report generated without the critical-lines section; it "
		f"carries {sorted(slugs)}"
	)
	section = next(s for s in built.context.sections if s.slug == "critical_lines")
	rows = section.tables[0].rows
	assert rows, "the critical-lines section rendered with no rows"
	assert {str(row[0]) for row in rows} == {"AB"}, f"the rows are not lines: {rows}"


def test_the_quarterly_report_reads_the_projected_outlook(tmp_path: Path):
	"""The round trip for the quarterly required section.

	`market_outlook` is required, so before its projection the quarterly cadence
	could not be generated at all. This is that cadence generating, with the
	section present and carrying the period the projection resolved.
	"""
	from alea.reporting.service import build_report

	config = _config(tmp_path)
	_solved(tmp_path, config)
	source = _projected_source(tmp_path, config, "market_outlook")
	project_section(ReportCadence.QUARTERLY, "market_outlook", source, config, as_of=ISSUE_DATE)

	built = build_report(
		ReportCadence.QUARTERLY,
		config,
		tmp_path / "reports",
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	slugs = {section.slug for section in built.context.sections}
	assert "market_outlook" in slugs, (
		f"the quarterly report generated without the outlook section; it carries "
		f"{sorted(slugs)}"
	)
	section = next(s for s in built.context.sections if s.slug == "market_outlook")
	assert section.tables[0].rows, "the outlook section rendered with no rows"


def test_the_daily_report_reads_the_projected_mix_and_prices(tmp_path: Path):
	"""The round trip for both daily sections, through the real report.

	Two sections rather than one because they are the pair that measured the
	distinction the register's prose draws. `generation_mix` had a writer and no
	rule; `price_forecast` had its quantity computed for the API's serving table
	at a different shape. Both are optional, so a daily report generates without
	either and warns -- which is why asserting the *file* exists is not enough
	and the claim has to be that the section appears in a generated report.

	The daily cadence's *required* section is `outage_forecast`, whose producer
	is blocked on the VIIRS fetcher (`UNIMPLEMENTED_FETCHERS`), so it is
	projected from a hand-written frame. Without it `build_report` raises on that
	section and this test would pass or fail for the wrong reason -- the same
	reason the weekly round trip writes `week_ahead` by hand.
	"""
	from alea.reporting.service import build_report

	config = _config(tmp_path)
	_solved(tmp_path, config)
	# `outage_forecast` declares `["Line", "Probability", "Interval", "Basis"]`
	# and its unit is "probability", so the primary binds to the row's unit and
	# no extra column is needed -- unlike `week_ahead`, whose unit is "MW" and
	# which therefore needs a `demand` column.
	_outage_forecast = pd.DataFrame(
		{
			"label": ["n-s"],
			"value": [0.12],
			"unit": ["probability"],
			"interval_low": [0.05],
			"interval_high": [0.22],
		}
	)
	required_source = Path(config.paths.processed) / "outage_forecast.parquet"
	write_artefact(
		required_source,
		_outage_forecast,
		DerivedProvenance(
			source_id="outage_forecast", inputs=["fixture:network"], basis=Basis.FORECAST
		),
		format="parquet",
	)
	project_section(
		ReportCadence.DAILY, "outage_forecast", required_source, config, as_of=ISSUE_DATE
	)

	for slug in ("generation_mix", "price_forecast"):
		source = _projected_source(tmp_path, config, slug)
		project_section(ReportCadence.DAILY, slug, source, config, as_of=ISSUE_DATE)

	built = build_report(
		ReportCadence.DAILY,
		config,
		tmp_path / "reports",
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	slugs = {section.slug for section in built.context.sections}
	for slug in ("generation_mix", "price_forecast"):
		assert slug in slugs, (
			f"the daily report generated without the {slug} section; it carries "
			f"{sorted(slugs)}"
		)
		section = next(s for s in built.context.sections if s.slug == slug)
		rows = section.tables[0].rows
		assert rows, f"the {slug} section rendered with no rows"

	# The mix's first column is the carrier, and the fixture network dispatches
	# two of them -- so the rows are carriers rather than a repeated label.
	mix = next(s for s in built.context.sections if s.slug == "generation_mix")
	assert {str(row[0]) for row in mix.tables[0].rows} == {"coal", "hydro"}, (
		f"the mix rows are not carriers: {mix.tables[0].rows}"
	)
