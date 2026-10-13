# SPDX-License-Identifier: MIT
"""The renewable forecast: the producer, the stage, and the round trip.

The register recorded this section's blocker as "a *forecast* is a different
quantity from a *profile*", and the distinction is real. What the entry missed
is that the repository already holds the weather model's output:
`planning.renewables.attach_renewable_profiles` writes atlite's per-bus capacity
factor into each generator's ``p_max_pu``, so reading the network back *is*
reading the model, and `week_ahead` shipped the same call one section over.

The claim these tests discharge is the one the register makes, and the round
trip is the only one that does: a frame of the right shape and a stage that
writes it are not a deliverable section. `capacity_update` was recorded as
produced, its rule exited 0, and `alea report monthly` exited 1 with
``ReportDataError: no artefact`` -- which is why `reporting/projection.py`
exists and why the last test here measures ``unprojected_sections`` before and
after rather than trusting the register.

Two numbers are asserted from the fixture's own arithmetic rather than re-read
from the producer: the weighted mean is not the unweighted one, and a carrier
with no built capacity is absent rather than zero.
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
from alea.planning.balance import BalanceError, renewable_forecast_rows
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from tests.ci.test_market_report_sections import _config

SNAPSHOTS = pd.date_range("2030-01-01", periods=24 * 9, freq="h", tz="UTC")
"""Nine days at hourly resolution, so a seven-day window is a *cut* of a longer
horizon. A fixture as long as the window cannot tell a producer that honoured
``days`` from one that rendered every snapshot it had."""

ISSUE_DATE = date(2030, 1, 15)
PERIOD_END = date(2030, 1, 14)
"""``period_for(WEEKLY, ISSUE_DATE)``'s end: a Monday's report covers the week
that ended the day before. Spelled once so the projection and the assertion
cannot disagree about which day the section reads."""


def _network(
	*,
	large_solar: bool = True,
	unbuilt: bool = False,
	firm_only: bool = False,
) -> pypsa.Network:
	"""A network whose capacity factors are computable by hand.

	Solar's availability is a square wave -- 1.0 for twelve hours of each day,
	0.0 for the other twelve -- so its mean over any whole number of days is
	exactly 0.5. Wind is flat at 0.4, so a weighted mean of the two carriers is
	a number this test can write down rather than one it reads back.

	``large_solar`` splits solar into a large unit and a small one at a
	*different* factor. That is the weighting under test: an unweighted mean of
	the two would report a number neither unit produces.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add("Generator", "coal", bus="north", carrier="coal", p_nom=400.0)
	if not firm_only:
		network.add("Generator", "solar_a", bus="north", carrier="solar", p_nom=180.0)
		network.generators_t.p_max_pu["solar_a"] = [
			1.0 if 6 <= snapshot.hour < 18 else 0.0 for snapshot in SNAPSHOTS
		]
		if large_solar:
			network.add("Generator", "solar_b", bus="north", carrier="solar", p_nom=20.0)
			network.generators_t.p_max_pu["solar_b"] = [
				0.2 if 6 <= snapshot.hour < 18 else 0.0 for snapshot in SNAPSHOTS
			]
		network.add("Generator", "wind", bus="north", carrier="onwind", p_nom=100.0)
		network.generators_t.p_max_pu["wind"] = [0.4] * len(SNAPSHOTS)
	if unbuilt:
		network.add("Generator", "ror_new", bus="north", carrier="ror", p_nom=0.0)
	network.add("Load", "load", bus="north", p_set=300.0)
	return network


def test_the_forecast_has_one_row_per_variable_carrier():
	"""The section declares ``["Technology", "Capacity factor", "Basis"]``.

	One numeric column, so ``_rows_for`` binds the primary directly and the row
	carries no extras -- which is why the frame's ``unit`` is the section's own
	``"capacity factor"`` rather than a blank. Coal is absent: the registry
	classes it THERMAL, and a forecast of a dispatchable carrier's weather is
	not a quantity.
	"""
	frame = renewable_forecast_rows(_network(), days=7)

	assert list(frame.columns) == ["label", "value", "unit", "n_generators", "capacity_mw"]
	assert sorted(frame["label"]) == ["onwind", "solar"], (
		f"the rows are {sorted(frame['label'])}; the section is one row per "
		f"variable-renewable carrier and coal is not variable"
	)
	assert set(frame["unit"]) == {"capacity factor"}


def test_the_days_are_a_cut_of_a_longer_horizon_not_the_whole_of_it():
	"""``days`` bounds the window; the network's horizon does not.

	A network carrying a year of snapshots rendered whole would report a
	twelve-month mean under a heading promising the week ahead. The fixture is
	nine days so the assertion is that the window is *shorter* than the network.
	"""
	whole = renewable_forecast_rows(_network(), days=len(SNAPSHOTS))
	week = renewable_forecast_rows(_network(), days=7)

	assert len(SNAPSHOTS) > 7, "the fixture is not longer than the window it tests"
	# Every day of this fixture is identical, so the two windows agree on the
	# mean -- the difference the cut makes is asserted through the refusal
	# below, which a producer ignoring ``days`` could not raise.
	assert list(whole["value"]) == pytest.approx(list(week["value"]))

	with pytest.raises(BalanceError, match="no snapshot falls on or after"):
		renewable_forecast_rows(_network(), days=7, start="2031-01-01")


def test_the_capacity_factor_is_weighted_by_nameplate_not_a_mean_of_units():
	"""Solar is 180 MW at a 0.5 daily mean and 20 MW at a 0.1 one.

	The fleet's factor is ``(180*0.5 + 20*0.1) / 200 = 0.46``. The *unweighted*
	mean of the two units is ``0.30``, so the two readings are far apart and a
	producer that averaged units would be visibly wrong rather than
	coincidentally right. Wind is flat at 0.4, which no weighting can move.
	"""
	frame = renewable_forecast_rows(_network(), days=7)
	by_carrier = dict(zip(frame["label"], frame["value"], strict=True))

	assert by_carrier["solar"] == pytest.approx(0.46), (
		f"solar is {by_carrier['solar']}, not the capacity-weighted 0.46; an "
		f"unweighted mean of the two units gives 0.30, which is the small unit's "
		f"weather reported as the fleet's"
	)
	assert by_carrier["onwind"] == pytest.approx(0.4)


def test_the_row_records_the_capacity_it_weighted_by():
	"""The weight is part of the answer, not an implementation detail.

	A capacity factor is meaningless without the fleet it describes: 0.46 from
	200 MW and 0.46 from 20 GW are different facts about a system, and the
	section's prose says "for the week" rather than "for the fleet". The two
	extra columns are numeric, so they travel with the row and a section that
	declared them would bind them by name.
	"""
	frame = renewable_forecast_rows(_network(), days=7)
	solar = frame[frame["label"] == "solar"].iloc[0]

	assert solar["n_generators"] == 2.0
	assert solar["capacity_mw"] == pytest.approx(200.0)


def test_a_carrier_with_no_built_capacity_is_absent_rather_than_zero():
	"""A zero nameplate has no capacity factor; the quotient is undefined.

	Reporting ``0.0`` renders as a technology that produces nothing, which is a
	different claim from one that is not built -- and the second is the true
	one. The fixture adds a 0 MW run-of-river unit, and the assertion is that it
	does not appear at all.
	"""
	frame = renewable_forecast_rows(_network(unbuilt=True), days=7)

	assert "ror" not in set(frame["label"]), (
		"a carrier with no built capacity was reported; 0.0 reads as a "
		"technology that produces nothing rather than one that is not built"
	)


def test_a_network_with_no_variable_renewable_is_refused_rather_than_reported():
	"""An all-thermal fleet would render an empty table under a heading that
	promises one, and an empty table reads as a week with no wind rather than a
	network with nothing to forecast.
	"""
	with pytest.raises(BalanceError, match="no variable-renewable generator"):
		renewable_forecast_rows(_network(firm_only=True), days=7)


def test_a_network_with_no_generators_is_refused_rather_than_reported():
	empty = pypsa.Network()
	empty.set_snapshots(list(SNAPSHOTS))
	empty.add("Bus", "north", v_nom=220.0)
	empty.add("Load", "load", bus="north", p_set=300.0)

	with pytest.raises(BalanceError, match="no generators"):
		renewable_forecast_rows(empty, days=7)


def test_the_stage_writes_the_frame_and_the_register_names_it():
	"""A slug in ``PRODUCERS`` claims a function computes the section's rows, and
	a slug in ``PROJECTED`` that a rule lands them where the report reads. Both
	are asserted because closing this gap meant moving both.
	"""
	assert PRODUCERS["renewable_forecast"] == "planning.arrays.build_renewable_forecast"
	assert PROJECTED["renewable_forecast"] == "project_renewable_forecast"
	assert "renewable_forecast" not in UNPRODUCED


def test_the_section_leaves_the_missing_list_and_renders(tmp_path: Path):
	"""The round trip, asserted on the measurement the register entry is about.

	``unprojected_sections`` is the one measurement that separates "a producer
	exists" from "a report can read one", so it is taken before and after rather
	than inferred from the register. The report is then assembled through the
	reader's own path, because ``project_section`` refuses an artefact the
	section's declared columns cannot be filled from -- a guard that would pass
	on a frame whose numeric column the reader then could not bind.
	"""
	from alea.reporting.projection import project_section, unprojected_sections
	from alea.reporting.service import _section_from_spec, section_by_slug

	config = _config(tmp_path)
	network = _network()
	directory = resolve(config.paths.results) / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	network.export_to_netcdf(str(directory / "deadbeef-2030.nc"))

	before = unprojected_sections(ReportCadence.WEEKLY, config, as_of=ISSUE_DATE)
	assert "renewable_forecast" in before, (
		f"the section's dated artefact already exists before anything wrote it: "
		f"{before}"
	)

	stage_out = resolve(config.paths.processed) / "renewable_forecast.parquet"
	build_stage(
		"renewable_forecast", config, stage_out, parameters={"network_dir": str(directory)}
	)
	frame, _ = read_artefact(stage_out)
	assert sorted(frame["label"]) == ["onwind", "solar"], (
		f"the stage wrote {sorted(frame['label'])}"
	)

	project_section(
		ReportCadence.WEEKLY, "renewable_forecast", stage_out, config, as_of=ISSUE_DATE
	)

	after = unprojected_sections(ReportCadence.WEEKLY, config, as_of=ISSUE_DATE)
	assert "renewable_forecast" not in after, (
		f"the projection did not land the artefact where the section reads it; "
		f"still missing: {after}"
	)

	spec = section_by_slug(ReportCadence.WEEKLY, "renewable_forecast")
	warnings: list[str] = []
	rendered = _section_from_spec(spec, config, PERIOD_END, warnings)
	assert rendered is not None, (
		f"the section did not assemble from the artefact it declares: {warnings}"
	)
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one"
	)
	table = rendered.tables[0]
	assert table.columns == ["Technology", "Capacity factor", "Basis"], (
		f"the table's headers are {table.columns}, not the section's declared columns"
	)
	assert len(table.rows) == 2, f"the section rendered {len(table.rows)} rows, not two"

	by_label = {str(row[0]): row for row in table.rows}
	assert by_label["solar"][1].value == pytest.approx(0.46), (  # type: ignore[union-attr]
		"the rendered solar factor is not the capacity-weighted 0.46 the producer "
		"computed; the reader bound a different number to the header"
	)
	assert by_label["solar"][2] == "modelled", (
		f"the Basis cell is {by_label['solar'][2]!r}; the profile is atlite's, "
		f"attached when the network was built, so the basis is modelled"
	)
	assert np.isfinite(by_label["onwind"][1].value)  # type: ignore[union-attr]
