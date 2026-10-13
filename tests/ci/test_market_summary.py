# SPDX-License-Identifier: MIT
"""The weekly market summary: the producer, the stage, and the round trip.

`market_summary` is the weekly cadence's *optional* section, which is why its
absence warned rather than raised and nothing noticed it was missing -- a
warning in a published report is still a section a reader expected and did not
get. `reporting/producers.py` recorded the blocker as "no rule runs
`market.capture_by_technology` or `market.build_stack` against
`market/summary/{date}.parquet`", and that was exact.

**The column that makes this section different from its monthly sibling.**
`market_report` declares ``["Carrier", "Volume", "Average price", "Basis"]`` and
`market_summary` declares ``["Carrier", "Volume", "Capture price", "Basis"]``.
Both have two numeric columns, so `_rows_for` binds each header to the row
column *naming* it -- ``Capture price`` normalises to ``captureprice`` and would
**raise** against a row carrying only ``average_price``. That is the whole
reason this producer writes its own column rather than reusing the monthly one,
and it is asserted by name here.

**What the capture price is, and why it is not the system mean.** A carrier's
capture price is the volume-weighted price it actually received. Solar generates
in the cheap hours, so its capture sits below the system mean and coal's above
it; a producer that averaged the clearing prices would give both carriers the
same number and the section's second column would carry no information. The
fixture is built so those two numbers differ, because a flat stack makes them
equal and a test against a flat stack cannot tell the two apart.

The last test is the only one that discharges the register's claim: the frame is
projected, a weekly report is generated, and the section is read back out of it
with both numbers distinct.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.paths import resolve
from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage, registered_stages
from alea.market.service import weekly_market_to_artefact
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import build_report
from tests.ci.test_market_report_sections import _config, _solved_network

ISSUE_DATE = date(2030, 1, 15)

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")
"""One day at hourly resolution, matching the monthly fixture's own network.

A single day, so a seven-day window is the whole of it -- the assertion about
the window is then that the producer did not *invent* days the network does not
have, which is the failure a fixture longer than the window could not see.
"""

VOLL = 10_000.0


def test_the_stage_is_registered():
	"""A `@stage` in a module `_REGISTRATION_MODULES` omits registers nothing."""
	assert "market_summary" in registered_stages(), (
		"`market_summary` did not register; `alea.market.stages` is missing from "
		"`_REGISTRATION_MODULES`, so the stage is written, decorated and unreachable"
	)


def test_the_frame_carries_the_columns_the_section_binds_by_name(tmp_path: Path):
	"""The two numeric headers, each with a column naming it.

	``Capture price`` and ``Volume`` both normalise to a word the row must carry
	as its own column. A frame written with the monthly section's
	``average_price`` raises in the reader rather than rendering -- which is the
	refusal `_rows_for` was written to make, and the reason this producer exists
	separately from its monthly sibling.
	"""
	path = _solved_network(tmp_path)
	out = tmp_path / "market_summary.parquet"
	frame = weekly_market_to_artefact(
		pypsa.Network(str(path)), out, value_of_lost_load_usd_per_mwh=VOLL, inputs=["sha256:x"]
	)

	assert list(frame.columns) == ["label", "value", "unit", "volume", "capture_price"]
	assert set(frame["label"]) == {"coal", "solar"}, (
		f"the frame is not one row per carrier: {list(frame['label'])}"
	)
	assert set(frame["unit"]) == {"USD/MWh"}


def test_the_capture_price_is_the_price_each_carrier_actually_received(tmp_path: Path):
	"""Solar earns the cheap hours, so its capture is below the system mean.

	This is the difference between the price a *generator* received and the price
	a buyer paid, and it is the whole reason the section carries a capture price
	rather than a mean of the clearing prices. The two carriers must differ: a
	producer that averaged the clearing prices would give both the same number,
	and on this fixture that number is neither carrier's capture.
	"""
	path = _solved_network(tmp_path)
	out = tmp_path / "market_summary.parquet"
	frame = weekly_market_to_artefact(
		pypsa.Network(str(path)), out, value_of_lost_load_usd_per_mwh=VOLL, inputs=["sha256:x"]
	)

	captures = dict(zip(frame["label"], frame["capture_price"], strict=True))
	assert captures["solar"] < captures["coal"], (
		f"solar's capture {captures['solar']} is not below coal's {captures['coal']}; "
		f"solar generates only in the cheap midday hours, so a capture at or above "
		f"coal's means the producer averaged the clearing prices instead of "
		f"weighting them by what each carrier sold"
	)

	# The system mean is what a producer that ignored the weighting would write
	# into both rows. Asserting the two captures *straddle* it is what makes the
	# assertion above a statement about the weighting rather than about the
	# fixture happening to have one dear carrier.
	network = pypsa.Network(str(path))
	mean_price = float(network.buses_t.marginal_price.to_numpy().mean())
	assert captures["solar"] < mean_price < captures["coal"], (
		f"the two captures ({captures['solar']}, {captures['coal']}) do not straddle "
		f"the system mean ({mean_price}), so this fixture cannot tell a "
		f"volume-weighted capture from a mean of the clearing prices"
	)


def test_every_row_carries_a_volume_that_is_not_its_price(tmp_path: Path):
	"""The binding trap, asserted on the numbers rather than on the schema.

	``volume`` is MWh and ``capture_price`` is USD/MWh. A producer that wrote the
	price into both satisfies every schema check the artefact has and prints a
	price under the header "Volume" -- the defect the market section's own canary
	plants. Distinctness is the check that catches it.
	"""
	path = _solved_network(tmp_path)
	out = tmp_path / "market_summary.parquet"
	frame = weekly_market_to_artefact(
		pypsa.Network(str(path)), out, value_of_lost_load_usd_per_mwh=VOLL, inputs=["sha256:x"]
	)

	for _, row in frame.iterrows():
		assert row["volume"] > 0.0, f"{row['label']} dispatched nothing but has a row"
		assert row["volume"] != row["capture_price"], (
			f"{row['label']}: volume and capture price are the same number "
			f"({row['volume']}), so one of the two columns is a copy of the other"
		)


def test_a_network_with_no_generators_is_refused_rather_than_reported(tmp_path: Path):
	"""An empty fleet would render a week in which nothing cleared.

	That is a table saying "no market" where the true statement is "this network
	has nothing in it", and the two are not the same claim.
	"""
	empty = pypsa.Network()
	empty.set_snapshots(list(SNAPSHOTS))
	empty.add("Bus", "north", v_nom=220.0)
	empty.add("Load", "load", bus="north", p_set=120.0)

	with pytest.raises(ValueError, match="no generators"):
		weekly_market_to_artefact(
			empty, tmp_path / "x.parquet", value_of_lost_load_usd_per_mwh=VOLL, inputs=[]
		)


def test_the_register_moved_with_the_producer():
	"""A slug in `PRODUCERS` is a claim, and closing the gap moves two registers."""
	assert PRODUCERS["market_summary"] == "market.service.weekly_market_to_artefact"
	assert PROJECTED["market_summary"] == "project_market_summary"
	assert "market_summary" not in UNPRODUCED


def test_the_weekly_report_renders_the_section_from_the_stage(tmp_path: Path):
	"""The round trip: the stage's output, projected, in a generated report.

	The section is optional, so a missing artefact warns rather than raises --
	which is exactly why it stayed missing through every green suite. So the
	assertion is not merely that the report built: the section must be *in* it,
	with no warning, and with both of its numbers distinct.
	"""
	from alea.reporting.projection import project_section

	config = _config(tmp_path)
	path = _solved_network(tmp_path)
	directory = path.parent

	# `week_ahead` is the weekly cadence's *required* section, so the report
	# raises without it and this test would be measuring that absence rather than
	# this section's presence. Both sections are produced from the one solved
	# network, which is what the pipeline does.
	for slug in ("week_ahead", "market_summary"):
		stage_out = resolve(config.paths.processed) / f"{slug}.parquet"
		build_stage(slug, config, stage_out, parameters={"network_dir": str(directory)})
		project_section(ReportCadence.WEEKLY, slug, stage_out, config, as_of=ISSUE_DATE)

	out = resolve(config.paths.processed) / "market_summary.parquet"
	frame, _ = read_artefact(out)
	assert len(frame) == 2

	built = build_report(
		ReportCadence.WEEKLY,
		config,
		resolve(config.paths.reports),
		date=ISSUE_DATE,
		deliver=False,
		formats=("html",),
	)
	sections = {section.slug: section for section in built.context.sections}
	assert "market_summary" in sections, (
		f"the weekly report does not carry the section; it holds {sorted(sections)}"
	)
	assert not any("market_summary" in warning for warning in built.context.warnings), (
		f"the section warned instead of rendering: {built.context.warnings}"
	)

	rendered = sections["market_summary"]
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one"
	)
	table = rendered.tables[0]
	assert table.columns == ["Carrier", "Volume", "Capture price", "Basis"], (
		f"the table's headers are {table.columns}, not the section's declared columns"
	)
	assert len(table.rows) == 2, f"the section rendered {len(table.rows)} rows, not two"

	# Both numbers, per row, and they are not the same number: the reader binds
	# each header to the column naming it, so a producer that wrote one quantity
	# twice renders happily and lies.
	for row in table.rows:
		volume = row[1]
		capture = row[2]
		assert volume != capture, (  # type: ignore[comparison-overlap]
			f"the rendered row prints {volume} under both 'Volume' and 'Capture price'"
		)
