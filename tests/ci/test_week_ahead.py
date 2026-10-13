# SPDX-License-Identifier: MIT
"""The week-ahead balance: the producer, the stage, and the round trip.

`week_ahead` is the weekly cadence's only ``required=True`` section, so before
this producer existed ``alea report weekly`` *raised* rather than warned, and the
weekly cadence could not be generated from the pipeline at all. That is the claim
these tests have to discharge, and only the last one does: a frame of the right
shape, a stage that writes it, and a report that opens it are three different
facts, and a register that recorded the first as the third is the defect
`reporting/producers.py` was built to name.

The three numeric columns are the second thing under test. `_rows_for` binds each
header to the row column naming it and refuses rather than repeating the primary,
so a producer that wrote only ``value`` would *raise* in the reader -- which is
why the columns are asserted by name here rather than by count.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from alea.config.paths import resolve
from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage
from alea.planning.balance import (
	BalanceError,
	generator_capacity_mw,
	load_series,
	week_ahead_rows,
)
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import build_report
from tests.ci.test_market_report_sections import _config

REPO = Path(__file__).resolve().parents[2]

SNAPSHOTS = pd.date_range("2030-01-01", periods=24 * 9, freq="h", tz="UTC")
"""Nine days at hourly resolution, so a seven-day outlook is a *cut* of a longer
horizon rather than the whole of it. A fixture whose length equals the window
cannot tell a producer that honoured ``days`` from one that rendered every
snapshot it had."""

ISSUE_DATE = date(2030, 1, 15)


def _network(*, shedding: bool = False, extendable: bool = False) -> pypsa.Network:
	"""A network with a firm carrier, a weather-driven one, and a load.

	Solar is available for twelve hours of each day and nothing at night, so a
	day's mean renewable output is half its nameplate -- a number the test can
	compute rather than re-read from the producer. Coal is flat at 1.0, so the
	firm capacity is its nameplate in every snapshot.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add(
		"Generator",
		"coal",
		bus="north",
		carrier="coal",
		p_nom=400.0,
		marginal_cost=45.0,
		p_nom_extendable=extendable,
	)
	network.add(
		"Generator", "solar", bus="north", carrier="solar", p_nom=200.0, marginal_cost=0.0
	)
	network.generators_t.p_max_pu["solar"] = [
		1.0 if 6 <= snapshot.hour < 18 else 0.0 for snapshot in SNAPSHOTS
	]
	if shedding:
		network.add(
			"Generator",
			"shedding",
			bus="north",
			carrier="load shedding",
			p_nom=10_000.0,
			marginal_cost=10_000.0,
		)
	network.add("Load", "load", bus="north", p_set=300.0)
	return network


def test_the_balance_has_one_row_per_day_and_the_sections_own_columns():
	"""The frame's shape, and the columns `_rows_for` binds by name.

	``week_ahead`` declares ``["Day", "Demand", "Renewable", "Margin", "Basis"]``
	-- three numeric columns. The section's declared ``unit`` is ``"MW"``, so the
	primary binds to a column *named* ``demand`` and never to the row's unit; a
	frame carrying only ``value`` raises in the reader. Each numeric header is
	asserted to have a column naming it.
	"""
	frame = week_ahead_rows(_network(), days=7)

	assert list(frame.columns) == ["label", "value", "unit", "demand", "renewable", "margin"]
	assert len(frame) == 7, f"a seven-day outlook rendered {len(frame)} rows"
	assert list(frame["label"]) == [
		f"2030-01-{day:02d}" for day in range(1, 8)
	], "the day labels are the dates the snapshots fall on, in order"
	assert set(frame["unit"]) == {"MW"}


def test_the_days_are_a_cut_of_a_longer_horizon_not_the_whole_of_it():
	"""``days`` bounds the window; the network's horizon does not.

	A network carrying a year of snapshots rendered whole would put 8,760 rows
	under a heading promising a week. The fixture is nine days for this reason:
	the assertion is that the frame is *shorter* than the network, which a
	fixture as long as the window could not make.
	"""
	frame = week_ahead_rows(_network(), days=7)
	assert len(frame) == 7
	assert len(SNAPSHOTS) > 7, "the fixture is not longer than the window it tests"

	with pytest.raises(BalanceError, match="no snapshot falls on or after"):
		week_ahead_rows(_network(), days=7, start="2031-01-01")


def test_the_renewable_column_is_the_variable_carriers_mean_available_output():
	"""What "renewable" means here, computed rather than re-read.

	Solar is at 1.0 for twelve hours of each day and 0.0 for the other twelve, so
	its mean available output over any whole day is exactly half of its 200 MW
	nameplate -- 100 MW. Coal is not in the column: it is dispatchable, and the
	registry classes it THERMAL. A producer that summed *every* generator would
	report 600 MW here, which is the number this assertion refuses.
	"""
	frame = week_ahead_rows(_network(), days=7)

	assert list(np.round(frame["renewable"], 6)) == [100.0] * 7, (
		"the renewable column is not the VRE carriers' mean available output; "
		"200 MW of solar at a 0.5 daily mean is 100 MW, and coal is not variable"
	)
	assert list(frame["demand"]) == [300.0] * 7, "the load is a flat 300 MW in this fixture"


def test_the_margin_is_firm_plus_renewable_minus_demand():
	"""The row is one table, not three series: a reader can check the arithmetic.

	The identity is what makes ``Margin`` a defined quantity rather than a number
	a reader assumes. Firm capacity is coal's 400 MW at every snapshot, renewable
	is the 100 MW above, and demand is 300 MW, so the margin is 200 MW.
	"""
	frame = week_ahead_rows(_network(), days=7)

	for _, row in frame.iterrows():
		assert row["margin"] == pytest.approx(row["renewable"] + 400.0 - row["demand"]), (
			"the margin is not the available capacity less the demand; the row's "
			"three numbers must satisfy one identity or they are three series"
		)
	assert list(frame["margin"]) == [200.0] * 7


def test_load_shedding_is_excluded_from_the_capacity_the_margin_measures():
	"""A shedding unit is the model's *unserved* demand, not a power station.

	Counting it would report a system that always meets its load -- because the
	generator standing in for not meeting it was in the total. The fixture adds a
	10,000 MW shedding unit, so a producer that included it would report a margin
	of 10,200 MW instead of 200 MW. That is the difference between a table that
	hides a blackout and one that shows it.
	"""
	with_shedding = week_ahead_rows(_network(shedding=True), days=7)
	without = week_ahead_rows(_network(), days=7)

	assert list(with_shedding["margin"]) == list(without["margin"]), (
		"a load-shedding unit moved the reserve margin; it is a representation of "
		"unserved demand and must not count as available capacity"
	)
	assert list(with_shedding["margin"]) == [200.0] * 7


def test_capacity_is_the_optimisers_build_where_a_component_is_extendable():
	"""``p_nom_opt`` where extendable, ``p_nom`` otherwise -- one definition.

	An extendable unit's capacity is what the solve chose; reading ``p_nom``
	reports the capacity *before* the expansion the network is the answer to. On
	this unsolved fixture ``p_nom_opt`` is zero, so the extendable reading is
	visibly different from the fixed one rather than coincidentally equal.
	"""
	fixed = _network()
	extendable = _network(extendable=True)

	fixed_capacity = generator_capacity_mw(fixed.generators)
	extendable_capacity = generator_capacity_mw(extendable.generators)

	assert fixed_capacity[0] == pytest.approx(400.0), "a fixed unit's capacity is its p_nom"
	assert extendable_capacity[0] == pytest.approx(0.0), (
		"an extendable unit's capacity is p_nom_opt, which is zero before a solve; "
		"reading p_nom here would report capacity the optimiser never chose"
	)


def test_the_load_reader_reads_a_static_and_a_dynamic_profile_alike():
	"""``p_set`` has two homes, and a network may carry either.

	A network built without a demand stage carries the static column; reading only
	``loads_t.p_set`` reports zero demand for it, and a balance against zero
	demand has a margin equal to the whole fleet.
	"""
	static = _network()
	assert list(load_series(static)) == [300.0] * len(SNAPSHOTS)

	dynamic = _network()
	dynamic.loads_t.p_set["load"] = [
		500.0 if 6 <= snapshot.hour < 18 else 100.0 for snapshot in SNAPSHOTS
	]
	series = load_series(dynamic)
	assert series[0] == pytest.approx(100.0), "the dynamic profile was not read"
	assert series[12] == pytest.approx(500.0)


def test_a_network_with_no_generators_is_refused_rather_than_reported():
	"""An empty fleet would render every day as a whole-of-demand shortfall.

	That is a table saying "blackout" where the true statement is "this network
	has nothing in it", and the two are not the same claim.
	"""
	empty = pypsa.Network()
	empty.set_snapshots(list(SNAPSHOTS))
	empty.add("Bus", "north", v_nom=220.0)
	empty.add("Load", "load", bus="north", p_set=300.0)

	with pytest.raises(BalanceError, match="no generators"):
		week_ahead_rows(empty, days=7)


def test_the_stage_writes_the_frame_and_the_register_names_it():
	"""The producer exists, and the register moved with it.

	A slug in ``PRODUCERS`` is a claim that a function computes the section's
	rows, and a claim in ``PROJECTED`` that a rule lands them where the report
	reads. Both are asserted here because closing this gap means moving both.
	"""
	assert PRODUCERS["week_ahead"] == "planning.arrays.build_week_ahead"
	assert PROJECTED["week_ahead"] == "project_week_ahead"
	assert "week_ahead" not in UNPRODUCED


def test_the_weekly_report_renders_the_section_from_the_stage(tmp_path: Path):
	"""The round trip: the stage's output, projected, in a generated report.

	This is the only test that discharges the claim the register makes. A frame of
	the right shape and a stage that writes it are not a *deliverable section* --
	`capacity_update` was recorded as produced, its rule exited 0, and
	`alea report monthly` exited 1 with ``ReportDataError: no artefact``. So the
	report is generated here, and the section is asserted to be *in* it with the
	three numbers the producer computed.
	"""
	from alea.reporting.projection import project_section

	config = _config(tmp_path)
	network = _network()
	directory = resolve(config.paths.results) / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / "deadbeef-2030.nc"
	network.export_to_netcdf(str(path))

	out = resolve(config.paths.processed) / "week_ahead.parquet"
	build_stage("week_ahead", config, out, parameters={"network_dir": str(directory)})
	frame, _ = read_artefact(out)
	assert len(frame) == 7

	project_section(ReportCadence.WEEKLY, "week_ahead", out, config, as_of=ISSUE_DATE)

	built = build_report(
		ReportCadence.WEEKLY,
		config,
		resolve(config.paths.reports),
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	sections = {section.slug: section for section in built.context.sections}
	assert "week_ahead" in sections, (
		f"the weekly report does not carry its required section; it holds "
		f"{sorted(sections)}"
	)
	assert not any("week_ahead" in warning for warning in built.context.warnings), (
		f"the section warned instead of rendering: {built.context.warnings}"
	)
	rendered = sections["week_ahead"]
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one "
		f"table of the producer's rows"
	)
	table = rendered.tables[0]
	assert table.columns == ["Day", "Demand", "Renewable", "Margin", "Basis"], (
		f"the table's headers are {table.columns}, not the section's declared columns"
	)
	assert len(table.rows) == 7, f"the section rendered {len(table.rows)} rows, not seven"
	assert [str(row[0]) for row in table.rows] == [f"2030-01-{day:02d}" for day in range(1, 8)]

	# The three numbers the producer computed, read back through the render path.
	# Each header binds to the column naming it rather than to the row's primary,
	# so a producer that wrote only ``value`` would have raised above.
	numeric = [
		[cell.value for cell in row[1:4]]  # type: ignore[union-attr]
		for row in table.rows
	]
	assert numeric == [[300.0, 100.0, 200.0]] * 7, (
		f"the rendered rows are {numeric}, not the demand, renewable and margin the "
		f"producer computed (300 MW, 100 MW, 200 MW)"
	)
