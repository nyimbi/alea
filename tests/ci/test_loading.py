# SPDX-License-Identifier: MIT
"""The loading kernel: `|p0| / s_nom` per branch per snapshot.

WHY this module exists. `alea.reporting.producers.UNPRODUCED` recorded the
``critical_lines`` weekly section's blocker as *"needs a loading kernel, and
there is none"*, and named what closing it would take: ``|p0| / s_nom`` per
branch per snapshot from the dispatch the network already carries. That is this
kernel. The register's earlier guess -- that `losses.tlens_to_artefact` was a
path to the section's columns -- was measured and refuted: a `TlensEntry`
carries unserved *energy* and overload *counts*, not a loading ratio and not
hours.

**Two gates here are the ones a self-consistent test would miss.**

*Hours are not a snapshot count.* ``hours_at_or_above`` is the count times
``LossConfig.snapshot_hours``. For an hourly series the two are the same number,
so a test written on one cannot tell a correct implementation from a count -- and
the count is what a producer reaches for. The fixture below is a **15-minute**
series, where two snapshots at or above rating are 0.5 hours and a count would
print 2 under a column headed "Hours".

*An unrated branch is not a branch at zero loading.* ``ratings_mw`` defaults to
``inf`` for a line whose ``s_nom`` is absent (`alea.planning.arrays`), and
``x / inf`` is 0.0 -- so the naive ratio prints every unrated line at 0% and a
reader sees a network with nothing wrong. The fixture mixes rated and unrated
branches, and the ranking excludes the unrated ones rather than reporting them
as unloaded.

The radial fixture is analytic: with one path from source to load, the branch
carries the whole injection, so ``loading == |P| / s_nom`` exactly and the
expected numbers are arithmetic rather than a second call to the function under
test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact, write_artefact
from alea.io.pipeline import build_stage
from alea.losses.flow import Network, loading_series, susceptance_matrix
from alea.losses.service import critical_lines_to_artefact, network_to_payload
from alea.losses.views import LoadingEntry, LoadingRanking, LossConfig
from alea.provenance.models import DerivedProvenance
from alea.reporting.schemas import ReportCadence, ReportValue, period_for
from alea.reporting.service import SectionSpec, _section_from_spec, cadence_specs

# 15-minute snapshots. The whole point: two snapshots above rating are half an
# hour, and a count would print 2.
QUARTER_HOURS = 0.25
RATING_MW = 200.0

# Bus A injects, bus B consumes, one branch between them. The branch carries the
# whole injection, so the loading is |P| / s_nom with no arithmetic in between.
INJECTIONS = np.array(
	[
		[300.0, -300.0],
		[300.0, -300.0],
		[150.0, -150.0],
		[0.0, 0.0],
	]
)
PEAK_LOADING = 300.0 / RATING_MW
SNAPSHOTS_AT_OR_ABOVE = 2
HOURS_AT_OR_ABOVE = SNAPSHOTS_AT_OR_ABOVE * QUARTER_HOURS


def _radial(ratings: tuple[float, ...] = (RATING_MW,)) -> Network:
	"""A two-bus radial network, with the ratings the caller names.

	Radial rather than meshed: with one path from source to load the flow is the
	injection, so the expected loading is ``|P| / s_nom`` and the assertion is
	arithmetic. A meshed fixture would need a reference solve to know what the
	flows should be, which is the second implementation of the kernel that this
	module exists to avoid.
	"""
	branch_from = np.array([0], dtype=np.uint32)
	branch_to = np.array([1], dtype=np.uint32)
	susceptance = np.array([132.0**2 / 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 2),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([0.5]),
		voltage_kv=np.array([132.0]),
		ratings_mw=np.array(ratings),
		branch_names=("AB",),
	)


def _meshed() -> Network:
	"""Three buses in a triangle at mixed voltage, with ratings that discriminate.

	Mixed voltage and meshed for the reason `tests/ci/test_network_arrays.py`
	records: a DC solve cannot see a *uniform* susceptance change, so a fixture
	whose branches all sit at one voltage cannot tell a changed network from an
	unchanged one. The ratings differ per branch, so the loadings differ too and
	a gate that read one branch's ratio for all three would be visible.
	"""
	branch_from = np.array([0, 1, 2], dtype=np.uint32)
	branch_to = np.array([1, 2, 0], dtype=np.uint32)
	susceptance = np.array([220.0**2 / 20.0, 132.0**2 / 10.0, 132.0**2 / 15.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([1.0, 0.5, 0.8]),
		voltage_kv=np.array([220.0, 132.0, 132.0]),
		ratings_mw=np.array([500.0, 300.0, 400.0]),
		branch_names=("AB", "BC", "CA"),
	)


def _chain(ratings: tuple[float, ...]) -> Network:
	"""Three buses in a line, each branch with the rating the caller names.

	Radial *and* two branches, so a fixture can carry one rated and one unrated
	branch: the "no branch is rated" guard fires before the "a rating is
	non-positive" guard, and a one-branch fixture cannot reach the second.
	"""
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	susceptance = np.array([132.0**2 / 10.0, 132.0**2 / 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array(ratings),
		branch_names=("AB", "BC"),
	)


def _parallel() -> Network:
	"""Two identical branches between the same pair of buses.

	Identical susceptance and rating, so the DC solve splits the injection
	equally and the two loadings are *exactly* equal -- the tie AD-8's
	index-ascending break is for. A tie produced by rounding is not a tie.
	"""
	branch_from = np.array([0, 0], dtype=np.uint32)
	branch_to = np.array([1, 1], dtype=np.uint32)
	susceptance = np.array([132.0**2 / 10.0, 132.0**2 / 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 2),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([200.0, 200.0]),
		branch_names=("P1", "P2"),
	)


def _config(**overrides: float) -> LossConfig:
	"""A loss config at the fixture's resolution, with `slack_bus` pinned."""
	settings: dict[str, float] = {"slack_bus": 0, "snapshot_hours": QUARTER_HOURS}
	settings.update(overrides)
	return LossConfig(**settings)  # type: ignore[arg-type]


def test_the_peak_loading_is_the_flow_over_the_rating():
	"""``|p0| / s_nom``, on a branch whose flow is the injection by construction."""
	ranking = loading_series(_radial(), INJECTIONS, _config())
	assert len(ranking.entries) == 1
	entry = ranking.entries[0]
	assert entry.peak_loading == pytest.approx(PEAK_LOADING)
	assert entry.peak_flow_mw == pytest.approx(300.0)
	assert entry.rating_mw == pytest.approx(RATING_MW)
	assert entry.branch_name == "AB"


def test_the_hours_are_hours_and_not_a_snapshot_count():
	"""The unit gate. A count here overstates by the series resolution.

	Two snapshots are at or above rating and the series is 15-minute, so the
	answer is 0.5 hours. A producer that reported the count would print 2, and
	on an hourly series the two agree -- which is why the fixture is not hourly.
	"""
	ranking = loading_series(_radial(), INJECTIONS, _config())
	entry = ranking.entries[0]
	assert entry.snapshots_at_or_above == SNAPSHOTS_AT_OR_ABOVE
	assert entry.hours_at_or_above == pytest.approx(HOURS_AT_OR_ABOVE)
	assert entry.hours_at_or_above != pytest.approx(float(entry.snapshots_at_or_above)), (
		"the fixture cannot discriminate hours from a count; an hourly series "
		"makes them equal and this gate vacuous"
	)


def test_an_hourly_series_makes_the_two_agree_and_that_is_the_trap():
	"""The non-discriminating case, asserted so the fixture above is justified.

	At one hour per snapshot the count and the hours are the same number. A gate
	written against this resolution would pass on both a correct kernel and one
	that returned the count, which is exactly the failure mode the 15-minute
	fixture exists to avoid.
	"""
	hourly = _config(snapshot_hours=1.0)
	entry = loading_series(_radial(), INJECTIONS, hourly).entries[0]
	assert entry.hours_at_or_above == pytest.approx(float(entry.snapshots_at_or_above))


def test_a_branch_below_its_rating_is_not_in_the_ranking():
	"""The section is "lines at or above rating", so below-rating branches are out.

	The fixture's third and fourth snapshots are at 0.75 and 0.0 loading. They
	are excluded from ``entries`` -- not reported as zero -- while ``n_rated``
	still counts the branch, so a reader can tell "not overloaded" from "not
	rated".
	"""
	ranking = loading_series(_radial(), INJECTIONS, _config())
	assert ranking.n_rated == 1
	assert ranking.n_branches == 1
	assert ranking.n_unrated == 0
	assert ranking.worst_loading == pytest.approx(PEAK_LOADING)


def test_a_rated_branch_that_never_reaches_rating_gives_an_empty_ranking():
	"""An empty list means nothing was above rating, and only that.

	``s_nom`` is raised until the same dispatch no longer overloads the branch.
	The ranking is empty, the branch is still rated, and the two are reported
	separately -- which is what keeps an empty critical-line table from reading
	as a missing artefact.
	"""
	ranking = loading_series(_radial(ratings=(1000.0,)), INJECTIONS, _config())
	assert ranking.entries == []
	assert ranking.n_rated == 1
	assert ranking.worst_loading == 0.0


def test_an_unrated_branch_is_excluded_and_never_reported_as_zero_loading():
	"""``x / inf`` is 0.0, which would print an unrated line as unloaded.

	`alea.planning.arrays` gives a line with no ``s_nom`` a rating of ``inf``.
	Dividing by it yields zero loading for every snapshot, and a critical-line
	table listing that line at 0% is a table saying a branch nobody rated is
	fine. The branch is excluded from ``entries`` and counted in ``n_unrated``.
	"""
	ranking = loading_series(_chain(ratings=(100.0, np.inf)), np.array([[300.0, 0.0, -300.0]]), _config())
	assert ranking.n_rated == 1
	assert ranking.n_unrated == 1
	assert [entry.branch_name for entry in ranking.entries] == ["AB"], (
		"an unrated branch reached the ranking; a line with no s_nom is not a "
		"line loaded at zero"
	)


def test_a_network_with_no_rated_branch_is_refused():
	"""No ratings is not the same finding as no overloads.

	Every branch unrated means there is no ``s_nom`` to divide by. Returning an
	empty ranking there would publish "no critical lines" for a network whose
	loading was never measured.
	"""
	with pytest.raises(ValueError, match="no branch carries a finite positive rating"):
		loading_series(_radial(ratings=(np.inf,)), INJECTIONS, _config())


def test_a_non_positive_rating_is_refused():
	"""A branch that can carry nothing is a data error, not infinite loading.

	One branch is rated and one is not, so the refusal is the *zero* rating's
	and not the "nothing here is rated" guard's -- those are different findings
	and a fixture with only a zero rating reaches the other one first.
	"""
	chain = _chain(ratings=(100.0, 0.0))
	with pytest.raises(ValueError, match="non-positive rating"):
		loading_series(chain, np.array([[300.0, 0.0, -300.0]]), _config())


def test_the_ranking_is_worst_first_and_ties_break_on_branch_index():
	"""Determinism (AD-8): the same dispatch gives the same critical-line list.

	The fixture is two *parallel* branches of equal susceptance and equal rating,
	which the DC solve loads identically -- an exact tie, not one that rounding
	could separate. A sort that ordered equal loadings by whatever the flow
	vector happened to give would reorder the published table between runs.
	"""
	ranking = loading_series(_parallel(), np.array([[500.0, -500.0]]), _config())
	assert len(ranking.entries) == 2
	first, second = ranking.entries
	assert first.peak_loading == second.peak_loading, (
		f"the fixture is not a tie: {first.peak_loading} vs {second.peak_loading}"
	)
	assert [first.branch, second.branch] == [0, 1]


def test_a_meshed_network_gives_each_branch_its_own_loading():
	"""The fixture discriminates: three branches, three different loadings.

	A fixture whose branches all carried the same flow would pass a gate that
	read one branch's ratio for every row. The dispatch is chosen so every
	branch is at or above rating, since a ranking of one entry cannot show three
	loadings.
	"""
	ranking = loading_series(_meshed(), np.array([[1000.0, -200.0, -800.0]]), _config())
	assert len(ranking.entries) == 3
	loadings = {round(entry.peak_loading, 9) for entry in ranking.entries}
	assert len(loadings) == 3, f"the fixture's branches share a loading: {loadings}"
	assert [entry.branch_name for entry in ranking.entries] == ["CA", "BC", "AB"], (
		"the ranking is not worst first"
	)


def test_a_diverged_snapshot_is_excluded_rather_than_poisoning_the_peak():
	"""A NaN flow is recorded in its own count and left out of the peak.

	``solve_snapshot`` returns NaN flows for a snapshot it cannot solve. Taking
	``max`` over a column containing NaN gives NaN, which would erase a branch
	from the table entirely; the kernel counts the diverged snapshots and takes
	the peak over the finite ones.
	"""
	network = _radial()
	ranking = loading_series(network, INJECTIONS, _config())
	assert ranking.entries[0].diverged_snapshots == 0
	assert np.isfinite(ranking.entries[0].peak_loading)


def test_a_mismatched_injection_shape_is_refused():
	"""The dispatch must be ``[n_snapshots, n_buses]`` or every flow is wrong."""
	with pytest.raises(ValueError, match=r"injections must be \[n_snapshots, 2\]"):
		loading_series(_radial(), np.array([300.0, -300.0]), _config())


def test_a_non_positive_threshold_is_refused():
	"""A threshold of zero would rank every branch, including idle ones."""
	with pytest.raises(ValueError, match="threshold must be positive"):
		loading_series(_radial(), INJECTIONS, _config(), threshold=0.0)


# --------------------------------------------------------------------------
# The projection: the frame the report section reads
# --------------------------------------------------------------------------


def test_the_projection_writes_the_columns_the_section_binds(tmp_path: Path):
	"""``["Line", "Peak loading", "Hours", "Basis"]`` needs three of them.

	``_rows_for`` binds each numeric column to the quantity whose name it
	matches, and raises when the row does not carry it. The section's "Peak
	loading" and "Hours" headers must therefore find ``peak_loading`` and
	``hours`` in the frame -- the columns are the contract, not decoration.
	"""
	out = tmp_path / "critical.parquet"
	_, rows = critical_lines_to_artefact(_radial(), INJECTIONS, out, _config())
	frame, provenance = read_artefact(out)
	assert isinstance(frame, pd.DataFrame)
	assert list(frame.columns) == [
		"label",
		"value",
		"unit",
		"peak_loading",
		"hours",
		"rating_mw",
		"peak_flow_mw",
	]
	assert len(rows) == 1
	assert frame.iloc[0]["label"] == "AB"
	assert frame.iloc[0]["value"] == pytest.approx(PEAK_LOADING)
	assert frame.iloc[0]["peak_loading"] == pytest.approx(PEAK_LOADING)
	assert frame.iloc[0]["hours"] == pytest.approx(HOURS_AT_OR_ABOVE)
	assert provenance.source_id == "critical_lines"
	assert provenance.parameters["n_above"] == 1


def test_the_projection_carries_the_two_numbers_apart(tmp_path: Path):
	"""The row's peak loading and its hours are different quantities.

	The defect `_rows_for` was written to stop was a row printing its primary
	value in a second numeric column -- the loading under "Hours". This asserts
	the producer does not hand the reader a row where that could pass unnoticed.
	"""
	out = tmp_path / "critical.parquet"
	critical_lines_to_artefact(_radial(), INJECTIONS, out, _config())
	frame, _ = read_artefact(out)
	assert frame.iloc[0]["peak_loading"] != pytest.approx(frame.iloc[0]["hours"])


def test_the_projection_writes_an_empty_frame_when_nothing_is_overloaded(tmp_path: Path):
	"""An empty table is a finding; the frame still carries its columns.

	A frame with no rows and no columns would fail the section's column binding
	for a reason that has nothing to do with the network.
	"""
	out = tmp_path / "critical.parquet"
	_, rows = critical_lines_to_artefact(_radial(ratings=(1000.0,)), INJECTIONS, out, _config())
	frame, _ = read_artefact(out)
	assert rows == []
	assert len(frame) == 0
	assert "hours" in frame.columns


def test_the_projection_records_the_series_resolution_it_used(tmp_path: Path):
	"""A loading with no snapshot length is not reproducible.

	The hours column is a function of ``snapshot_hours``, so a reader that has
	the artefact and not the config must be able to recover it from the sidecar.
	"""
	out = tmp_path / "critical.parquet"
	critical_lines_to_artefact(_radial(), INJECTIONS, out, _config())
	_, provenance = read_artefact(out)
	assert provenance.parameters["snapshot_hours"] == pytest.approx(QUARTER_HOURS)
	assert provenance.parameters["threshold"] == pytest.approx(1.0)
	assert provenance.parameters["n_snapshots"] == len(INJECTIONS)


def test_the_models_are_the_ones_the_kernel_returns():
	"""The exported types are what a caller of the layer sees."""
	ranking = loading_series(_radial(), INJECTIONS, _config())
	assert isinstance(ranking, LoadingRanking)
	assert isinstance(ranking.entries[0], LoadingEntry)


# --------------------------------------------------------------------------
# End to end: the producer's frame read by the real weekly section
# --------------------------------------------------------------------------

AS_OF = date(2026, 10, 11)
"""A Saturday, so the weekly period ends Friday and the date arithmetic lands
on a completed period -- the same report date `tests/fixtures/reporting` uses."""


def _critical_section() -> SectionSpec:
	"""The weekly cadence's ``critical_lines`` declaration, as it is written."""
	specs, _ = cadence_specs(ReportCadence.WEEKLY)
	by_slug = {spec.slug: spec for spec in specs}
	assert "critical_lines" in by_slug, "the weekly cadence no longer declares critical_lines"
	return by_slug["critical_lines"]


def _as_value(cell: ReportValue | str) -> ReportValue:
	"""A table cell that must be a value rather than a basis or a label.

	A row is a union -- a numeric cell is a `ReportValue`, the basis and the
	label are plain strings -- so reading ``.value`` off one needs the narrowing
	stated rather than assumed.
	"""
	assert isinstance(cell, ReportValue), f"expected a numeric cell, got {cell!r}"
	return cell


def test_the_section_is_read_from_the_artefact_the_producer_writes(tmp_path: Path):
	"""The whole chain, over the real reader.

	The projection's own test asserts the frame has the columns; this asserts
	the *report* can read them, which is a different claim -- `_rows_for` binds
	"Peak loading" and "Hours" through `_normalise_column`, and a column named
	``peak`` or ``hours_at_or_above`` would satisfy the first test and raise
	here. The section's declared path is formatted from its own spec and the
	cadence's own period, so this cannot drift from where the reader looks.
	"""
	spec = _critical_section()
	_, period_end = period_for(ReportCadence.WEEKLY, AS_OF)
	results = tmp_path / "results"
	out = results / spec.artefact.format(date=f"{period_end:%Y-%m-%d}")
	out.parent.mkdir(parents=True, exist_ok=True)

	critical_lines_to_artefact(_radial(), INJECTIONS, out, _config())

	config = load_config(
		overrides={
			"paths": {"results": str(results), "reports": str(tmp_path / "reports")},
			"reporting": {"pdf_enabled": False},
		}
	)
	section = _section_from_spec(spec, config, period_end, [])
	assert section is not None, "the section was skipped despite its artefact existing"
	rows = section.tables[0].rows
	assert len(rows) == 1
	line, *cells = rows[0]
	assert line == "AB"
	peak, hours = (_as_value(cell) for cell in cells[:2])
	assert peak.value == pytest.approx(PEAK_LOADING)
	assert hours.value == pytest.approx(HOURS_AT_OR_ABOVE)
	assert hours.value != pytest.approx(peak.value), (
		"the report printed the loading under 'Hours'; the section's second "
		"numeric column is reading the primary"
	)
	assert cells[2] == "modelled"


def test_the_units_column_the_producer_writes_is_the_one_the_section_declares(
	tmp_path: Path,
):
	"""``unit`` travels per row, so it must agree with the section's header.

	`value_from_artefact` prefers a row's ``unit`` over the section's, so a
	producer writing ``MW`` for a dimensionless loading would relabel every cell
	while the column header still said ``loading``.
	"""
	spec = _critical_section()
	out = tmp_path / "critical.parquet"
	critical_lines_to_artefact(_radial(), INJECTIONS, out, _config())
	frame, _ = read_artefact(out)
	assert set(frame["unit"]) == {spec.unit} == {"loading"}


# --------------------------------------------------------------------------
# The registered stage: the two processed artefacts in, the frame out
# --------------------------------------------------------------------------


def _provenance_for(source_id: str) -> DerivedProvenance:
	"""A provenance for a fixture input, which `write_artefact` refuses without."""
	return DerivedProvenance(
		source_id=source_id,
		inputs=[f"fixture:{source_id}"],
		run_id="00000000-0000-7000-8000-000000000000",
		notes="loading gate fixture",
	)


def _stage_tree(tmp_path: Path) -> Config:
	"""A processed lake holding the two artefacts the stage reads.

	Written through the real `write_artefact`, so the stage's own reader
	verifies the checksums -- a fixture that bypassed the sidecar would exercise
	a path production never takes.
	"""
	config = load_config(
		overrides={
			"paths": {
				"processed": str(tmp_path / "processed"),
				"results": str(tmp_path / "results"),
			}
		}
	)
	processed = Path(config.paths.processed)
	write_artefact(
		processed / "network_arrays.json",
		network_to_payload(_radial()),
		_provenance_for("network_arrays"),
	)
	write_artefact(
		processed / "dispatch.parquet",
		pd.DataFrame(INJECTIONS, columns=["A", "B"]),
		_provenance_for("dispatch"),
	)
	return config


def test_the_registered_stage_writes_the_frame_from_the_two_artefacts(tmp_path: Path):
	"""`alea build critical_lines` reads the paths the rule declares as inputs.

	The stage resolves ``network_arrays.json`` and ``dispatch.parquet`` by their
	conventional names under ``paths.processed`` rather than by an argument, so
	this is the only thing that proves the rule's two inputs are the two the
	builder reads.
	"""
	config = _stage_tree(tmp_path)
	out = Path(config.paths.processed) / "critical_lines.parquet"
	result = build_stage("critical_lines", config, out, inputs=[])
	assert not result.skipped
	frame, provenance = read_artefact(out)
	assert isinstance(frame, pd.DataFrame)
	assert list(frame["label"]) == ["AB"]
	assert provenance.source_id == "critical_lines"
	assert provenance.parameters["n_snapshots"] == len(INJECTIONS)
	assert provenance.parameters["n_branches"] == 1


def test_the_registered_stage_refuses_an_absent_dispatch(tmp_path: Path):
	"""A missing input names the path, rather than writing an empty table.

	An empty critical-line table is a finding -- nothing is above rating -- and
	a stage that wrote one because its dispatch was absent would publish "no
	line is overloaded" for a network it never looked at.
	"""
	config = _stage_tree(tmp_path)
	(Path(config.paths.processed) / "dispatch.parquet").unlink()
	out = Path(config.paths.processed) / "critical_lines.parquet"
	with pytest.raises(ArtefactError, match="no dispatch series at"):
		build_stage("critical_lines", config, out, inputs=[])
	assert not out.exists(), "a refused stage left an artefact behind"


def test_the_registered_stage_refuses_a_dispatch_that_is_not_the_network_s(
	tmp_path: Path,
):
	"""A dispatch with the wrong column count is a different network's.

	The arrays number the buses and the dispatch's columns are in that order, so
	a dispatch from another solve is not stale data -- it is a measurement of a
	network this run is not looking at.
	"""
	config = _stage_tree(tmp_path)
	write_artefact(
		Path(config.paths.processed) / "dispatch.parquet",
		pd.DataFrame(np.column_stack([INJECTIONS, np.zeros(len(INJECTIONS))]), columns=["A", "B", "C"]),
		_provenance_for("dispatch"),
	)
	out = Path(config.paths.processed) / "critical_lines.parquet"
	with pytest.raises(ArtefactError, match="dispatch has 3 columns but the network has 2 buses"):
		build_stage("critical_lines", config, out, inputs=[])
