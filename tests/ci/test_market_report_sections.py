# SPDX-License-Identifier: MIT
"""The two report sections Layer 3 produces, read back through the real reader.

WHY this module exists. `reporting/producers.py` recorded `market_report` and
`market_outlook` as unproduced, and the blocker it named was measured and right:
no module built a market fleet from a solved network, so `clear_scenario` had no
caller and `BiddingUnit` was constructed nowhere outside tests. Both are now
produced, and a producer is only produced if the *report* can read what it
writes -- which is a different claim from the producer returning a frame.

**The binding trap this module is built around.** `reporting/service.py`'s
`_rows_for` binds each numeric column of a section to the quantity whose name
matches. `market_report` declares ``["Carrier", "Volume", "Average price",
"Basis"]``, so it has *two* numeric columns and the reader requires each row to
carry a ``volume`` extra *and* an ``average_price`` extra. There is an escape
hatch -- a section with exactly one numeric column binds the primary into it --
and `market_outlook` declares ``["Quarter", "Price", "Basis"]``, which is
exactly one, so it takes the hatch. **The two sections exercise opposite
branches of the same function**, and a producer written for one shape silently
raises under the other.

The assertion that matters is not "the section rendered". It is that
``volume`` and ``average_price`` are *different numbers*: a producer that wrote
the primary into both columns would render, would pass a schema check, and would
print the average price under the header "Volume". That is the same failure
`test_loading.py` pins for the weekly section's "Hours" column, and it is the
one a fixture that hand-wrote the artefact cannot see.

**The fixture is a solved network, not a hand-built fleet.** The stage resolves
the newest solved network in a directory and builds the fleet from it, so a
fixture that constructed `Agent`s directly would test a function the stage does
not call -- and would hide the whole class of defect this layer has produced
before, where a capability exists and nothing reaches it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import registered_stages
from alea.market.fleet import build_fleet, load_series
from alea.market.stages import build_market_outlook, build_market_report
from alea.reporting.schemas import ReportCadence, ReportValue, period_for
from alea.reporting.service import SectionSpec, _section_from_spec, cadence_specs

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")
"""One day at hourly resolution, in a single planning horizon.

A single horizon rather than a multi-investment-period index, so the outlook's
period labels are the calendar quarter the snapshots fall in and the assertion
on them is arithmetic rather than a re-read of the labelling function.
"""

AS_OF = date(2030, 1, 15)


def _solved_network(tmp_path: Path) -> Path:
	"""A solved network with two carriers at different costs, where the stage looks.

	Two carriers, because the section is per carrier and a one-generator fixture
	cannot tell a producer that aggregated everything into one row from one that
	did not. Different marginal costs, because a flat stack clears at one price
	and the volume-weighted price would then equal the clearing price for every
	carrier -- which is exactly the coincidence that lets a producer writing the
	primary into both columns pass.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add("Line", "north-south", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=400.0)
	# Coal is dear and must run: solar alone cannot meet 120 MW at every hour.
	network.add(
		"Generator", "coal", bus="north", carrier="coal", p_nom=400.0, marginal_cost=45.0
	)
	network.add(
		"Generator",
		"solar",
		bus="south",
		carrier="solar",
		p_nom=200.0,
		marginal_cost=0.0,
		p_max_pu=0.0,
	)
	# Solar is available for half the day and nothing at night, so its *average*
	# price differs from coal's: it earns the clearing price only in the hours it
	# generates, and the hours it generates are the cheap ones.
	network.generators_t.p_max_pu["solar"] = [
		1.0 if 6 <= snapshot.hour < 18 else 0.0 for snapshot in SNAPSHOTS
	]
	network.add("Load", "load", bus="south", p_set=120.0)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the fixture network did not solve: {status} ({condition})"

	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / "deadbeef-2030.nc"
	network.export_to_netcdf(str(path))
	return path


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
	"""A minimal `BuildContext`, as the serving tests define one."""

	def __init__(self, parameters: dict[str, object] | None = None) -> None:
		self.out: Path | None = None
		self.inputs: list[str] = []
		self.logger = None
		self.parameters = dict(parameters or {})


def _section(slug: str, cadence: ReportCadence) -> SectionSpec:
	"""A section's declaration as it is written, refused if the slug moved."""
	specs, _ = cadence_specs(cadence)
	by_slug = {spec.slug: spec for spec in specs}
	assert slug in by_slug, f"the {cadence.value} cadence no longer declares {slug}"
	return by_slug[slug]


def _as_value(cell: ReportValue | str) -> ReportValue:
	assert isinstance(cell, ReportValue), f"expected a numeric cell, got {cell!r}"
	return cell


# --------------------------------------------------------------------------
# The stages register, and each is reachable through `alea build`
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["market_report", "market_outlook"])
def test_the_stage_is_registered(stage: str):
	"""A `@stage` in a module `_REGISTRATION_MODULES` omits registers nothing."""
	assert stage in registered_stages(), (
		f"`{stage}` did not register; `alea.market.stages` is missing from "
		f"`_REGISTRATION_MODULES`, so the stage is written, decorated and unreachable"
	)


# --------------------------------------------------------------------------
# The fleet the producers clear, built from a solved network
# --------------------------------------------------------------------------


def test_the_fleet_excludes_load_shedding_and_sums_the_network_capacity(tmp_path: Path):
	"""The fleet is the network's generators, less the ones that are not bidders.

	Load shedding is excluded deliberately and the reason is in `fleet.py`: it is
	a *shortage*, not a participant, and bidding it in would clear at the value of
	lost load by construction -- which is a price for a system in blackout
	presented as a market outcome. This asserts the exclusion is real rather than
	documented, because a `skip_carriers` default that nothing tests is a comment.
	"""
	path = _solved_network(tmp_path)
	network = pypsa.Network(str(path))
	network.add(
		"Generator",
		"load shedding",
		bus="south",
		carrier="load shedding",
		p_nom=1000.0,
		marginal_cost=2000.0,
	)
	fleet = build_fleet(network)
	identifiers = {agent.unit.unit_id for agent in fleet}
	assert "load shedding" not in identifiers, (
		"the load-shedding unit is in the fleet; a clearing that includes it prices "
		"the shortage instead of reporting it"
	)
	assert identifiers == {"coal", "solar"}
	assert sum(agent.unit.capacity_mw for agent in fleet) == pytest.approx(600.0)


def test_the_fleet_carries_the_network_s_own_marginal_cost(tmp_path: Path):
	"""The bid is the network's cost, not a default.

	A fleet whose every unit bid the same number would clear at that number and
	the section's average price would be a constant -- plausible, and wrong.
	"""
	path = _solved_network(tmp_path)
	fleet = build_fleet(pypsa.Network(str(path)))
	cost = {agent.unit.unit_id: agent.unit.marginal_cost_usd_per_mwh for agent in fleet}
	assert cost == {"coal": pytest.approx(45.0), "solar": pytest.approx(0.0)}


def test_load_series_is_the_network_s_total_load(tmp_path: Path):
	path = _solved_network(tmp_path)
	network = pypsa.Network(str(path))
	series = load_series(network)
	assert series.shape[0] == len(SNAPSHOTS)
	assert all(value == pytest.approx(120.0) for value in series)


# --------------------------------------------------------------------------
# The monthly section: two numeric columns, so both extras must be real
# --------------------------------------------------------------------------


def test_the_monthly_section_reads_back_with_both_numbers_distinct(tmp_path: Path):
	"""The whole chain over the real reader, and the binding trap with it.

	`market_report` declares two numeric columns, so `_rows_for` requires a
	``volume`` extra and an ``average_price`` extra on every row and does *not*
	fall back to the primary. The last assertion is the one that matters: a
	producer that wrote the average price into both columns renders perfectly and
	prints a price under a header that says "Volume".
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	spec = _section("market_report", ReportCadence.MONTHLY)
	_, period_end = period_for(ReportCadence.MONTHLY, AS_OF)

	# The dated path the section's own template resolves to, and the stage writes
	# *there* rather than to a stage-shaped path. That is the losses precedent
	# read one step further: `critical_lines` writes the processed form and leaves
	# the dated projection to an `--out` someone passes, and the projection is the
	# same producer at the section's path. Writing it through `write_artefact`
	# rather than `to_parquet` is not incidental -- the reader refuses an artefact
	# with no provenance sidecar, so a fixture that wrote the frame directly would
	# be exercising a path production never takes.
	dated = Path(config.paths.results) / spec.artefact.format(date=f"{period_end:%Y-%m-%d}")
	dated.parent.mkdir(parents=True, exist_ok=True)
	build_market_report(config, dated, _context(tmp_path))

	section = _section_from_spec(spec, config, period_end, [])
	assert section is not None, "the section was skipped despite its artefact existing"
	rows = section.tables[0].rows
	assert len(rows) == 2, f"expected one row per carrier, got {rows!r}"

	by_label = {row[0]: row[1:] for row in rows}
	assert set(by_label) == {"coal", "solar"}

	coal = by_label["coal"]
	volume = _as_value(coal[0])
	average = _as_value(coal[1])
	assert volume.value > 0.0, "coal dispatched nothing, so the fixture is not clearing"
	assert average.value == pytest.approx(45.0), (
		"coal is the marginal unit in every hour it runs, so its average price is "
		"its own marginal cost"
	)
	assert volume.value != pytest.approx(average.value), (
		"the report printed the average price under 'Volume'; the section's second "
		"numeric column is reading the primary, which is what the two-column "
		"escape hatch in `_rows_for` exists to prevent"
	)
	assert coal[2] == "modelled"


def test_the_monthly_section_s_average_price_is_the_volume_weighted_one(tmp_path: Path):
	"""Solar earns the cheap hours, so its average is below the system mean.

	This is the difference between the price a *generator* received and the price
	a buyer paid, and it is the whole reason the section carries a capture price
	rather than a mean of the clearing prices. A producer that averaged the
	clearing prices would give both carriers the same number.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)
	build_market_report(config, out, _context(tmp_path))

	frame = pd.DataFrame(read_artefact(out)[0])
	price = dict(zip(frame["label"], frame["average_price"], strict=True))
	assert price["solar"] != pytest.approx(price["coal"]), (
		"every carrier reports the same average price, which is what a mean of the "
		"clearing prices produces -- the section's column is a capture price"
	)
	assert price["solar"] == pytest.approx(0.0), (
		"solar bids zero and is dispatched only when it is available, so it is "
		"never the marginal unit and its average price is its own bid"
	)


def test_a_network_with_no_generators_is_refused_rather_than_written(tmp_path: Path):
	"""An empty frame renders as a month in which nothing was dispatched.

	The refusal is the finding: a market report with no carriers is a report that
	says a system did not run, and the honest answer is that there is nothing to
	report. `build_fleet` returns an empty list rather than raising, so the
	producer is the place the refusal has to be.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"

	# A network with the loads and the lines but every generator removed: the
	# fleet is empty and the clearing has nothing to clear.
	directory = Path(config.paths.results) / "networks"
	network = pypsa.Network(str(directory / "deadbeef-2030.nc"))
	network.remove("Generator", list(network.generators.index))
	network.export_to_netcdf(str(directory / "cafebabe-2030.nc"))

	with pytest.raises(ValueError, match="no fleet to clear"):
		build_market_report(config, out, _context(tmp_path))


# --------------------------------------------------------------------------
# The quarterly section: one numeric column, so the primary binds directly
# --------------------------------------------------------------------------


def test_the_quarterly_section_reads_back_from_the_single_numeric_column(tmp_path: Path):
	"""The other branch of `_rows_for`, and the label is a real quarter.

	`market_outlook` declares one numeric column, so the reader binds the primary
	and no extra is needed -- the opposite branch from the monthly section. A
	producer written to the monthly shape would carry a stray column here and a
	producer written to this shape would raise there.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	spec = _section("market_outlook", ReportCadence.QUARTERLY)
	_, period_end = period_for(ReportCadence.QUARTERLY, AS_OF)
	dated = Path(config.paths.results) / spec.artefact.format(date=f"{period_end:%Y-%m-%d}")
	dated.parent.mkdir(parents=True, exist_ok=True)
	build_market_outlook(config, dated, _context(tmp_path))

	section = _section_from_spec(spec, config, period_end, [])
	assert section is not None, "the section was skipped despite its artefact existing"
	rows = section.tables[0].rows
	assert rows, "the outlook section rendered with no rows"
	for row in rows:
		label = row[0]
		assert label.startswith("2030-Q"), (
			f"the period label {label!r} is not a calendar quarter; the series is the "
			f"solve's own horizons and its labels must be the periods those horizons are"
		)
		price = _as_value(row[1])
		assert price.value > 0.0, f"a clearing price of {price.value} is not one"
		assert row[2] == "modelled"


def test_the_outlook_s_records_that_the_series_is_not_a_forecast(tmp_path: Path):
	"""No price-forecast model exists here, and the artefact has to say so.

	The section's prose asks for "the next four quarters, under the central
	scenario". What this producer writes is the clearing prices the solved
	network's own horizons support. Those are different claims, and a reader who
	cannot tell them apart will read a single-horizon solve as a projection. The
	provenance is where the difference lives.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_outlook.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)
	build_market_outlook(config, out, _context(tmp_path))

	_, provenance = read_artefact(out)
	assert provenance.parameters["series_basis"] == (
		"the solved network's own horizons, not a price forecast"
	), "the outlook's provenance no longer distinguishes its series from a forecast"


def test_the_voll_and_its_basis_travel_into_the_artefact(tmp_path: Path):
	"""The rate a clearing price is a function of, recorded with where it came from.

	A clearing price from a short stack *is* the value of lost load, so a reader
	who cannot see the rate cannot tell a defaulted one from a sourced one. The
	config carries both fields and the stage passes both; this is the gate that
	they arrive.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)
	build_market_report(config, out, _context(tmp_path))

	_, provenance = read_artefact(out)
	assert provenance.parameters["value_of_lost_load_usd_per_mwh"] == pytest.approx(
		config.market.value_of_lost_load_usd_per_mwh
	)
	assert provenance.parameters["value_of_lost_load_basis"] == (
		config.market.value_of_lost_load_basis
	)


# --------------------------------------------------------------------------
# The stage resolves the network the way the workflow declares it
# --------------------------------------------------------------------------


def test_the_stage_refuses_when_no_network_was_solved(tmp_path: Path):
	"""A market clears a solved network's fleet; an unsolved one has none.

	The refusal names the command to run rather than raising a `FileNotFoundError`
	from somewhere inside `pypsa`, because the failure a user will actually hit is
	"the network is not there yet".
	"""
	config = _config(tmp_path)
	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	out = Path(config.paths.processed) / "market_report.parquet"
	with pytest.raises(ArtefactError, match="run `alea solve` first"):
		build_market_report(config, out, _context(tmp_path))


def test_the_stage_reads_the_network_dir_parameter(tmp_path: Path):
	"""The parameter the rule passes, and the reason the rule passes it.

	The solved network's filename carries a content hash no rule can know at
	parse time, so the rule declares the *directory* and the stage resolves the
	newest file in it. A stage that ignored the parameter would read the default
	and the workflow's declaration would be decorative.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	elsewhere = tmp_path / "somewhere" / "networks"
	elsewhere.mkdir(parents=True, exist_ok=True)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)

	with pytest.raises(ArtefactError, match="run `alea solve` first"):
		build_market_report(config, out, _context(tmp_path, str(elsewhere)))


def _context(tmp_path: Path, network_dir: str | None = None) -> _Context:
	"""The parameters the rule passes, defaulting to the fixture's network tree."""
	parameters: dict[str, object] = {
		"network_dir": network_dir or str(tmp_path / "results" / "networks")
	}
	return _Context(parameters)


def test_the_stage_is_idempotent_over_the_same_network(tmp_path: Path):
	"""A second build over the same inputs writes nothing and says so.

	`skip_if_current` is what makes `alea build` a stage rather than a script: the
	workflow reruns it whenever the network directory changes, and a stage that
	rebuilt every time would re-clear the market on every `snakemake all`. The
	observable is the run id, which is the one already recorded.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)

	first = build_market_report(config, out, _context(tmp_path))
	second = build_market_report(config, out, _context(tmp_path))
	assert second.run_id == first.run_id, (
		"the second build re-cleared the market over unchanged inputs; "
		"`skip_if_current` is not firing"
	)


def test_a_re_solve_rebuilds_the_artefact(tmp_path: Path):
	"""The negative half: a different network is a different measurement.

	An idempotence check that never lets a rebuild through is worse than none --
	it would leave the report showing last month's clearing after a re-solve, with
	nothing to indicate it.
	"""
	path = _solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)

	first = build_market_report(config, out, _context(tmp_path))

	# A re-solve with a dearer coal unit: a different network, a different
	# digest, and therefore a different clearing.
	network = pypsa.Network(str(path))
	network.generators.loc["coal", "marginal_cost"] = 90.0
	network.optimize(solver_name="highs", log_to_console=False)
	network.export_to_netcdf(str(path))

	second = build_market_report(config, out, _context(tmp_path))
	assert second.run_id != first.run_id, (
		"the stage skipped a build over a re-solved network; the report would keep "
		"serving the previous solve's clearing"
	)
	frame = pd.DataFrame(read_artefact(out)[0])
	price = dict(zip(frame["label"], frame["average_price"], strict=True))
	assert price["coal"] == pytest.approx(90.0), (
		"the rebuild wrote the old cost, so the digest it compared was not the "
		"network's"
	)


def test_the_market_config_section_is_reachable_by_name():
	"""The VoLL is settable from YAML, which is the defect the section closes.

	Without a `market:` field on the root model, a `market:` block in a config
	file is a load error under ``extra="forbid"`` -- so the rate a run cleared at
	could not be set, recorded or changed. `tests/ci/test_config_reachability.py`
	sweeps every scalar of every layer section; this is the narrower claim that the
	one parameter this layer needs is one of them.
	"""
	config = load_config(
		overrides=["market.value_of_lost_load_usd_per_mwh=1234.5"],
	)
	assert config.market.value_of_lost_load_usd_per_mwh == pytest.approx(1234.5)
	assert config.market.value_of_lost_load_basis, (
		"the basis is empty, so a reader cannot tell a defaulted rate from a sourced "
		"one -- which is the reason the field exists"
	)


def test_the_default_config_names_the_rate_and_its_basis():
	"""The shipped config is the one a deployment reads, and it must carry both."""
	import yaml

	root = Path(__file__).resolve().parents[2]
	document = yaml.safe_load((root / "config" / "config.default.yaml").read_text())
	assert "market" in document, "config.default.yaml has no market block"
	assert document["market"]["value_of_lost_load_usd_per_mwh"] == pytest.approx(2000.0)
	assert document["market"]["value_of_lost_load_basis"] == (
		"config.market.value_of_lost_load_usd_per_mwh"
	)


def test_the_stage_parameters_round_trip_through_json(tmp_path: Path):
	"""`--set` values arrive as strings, and the provenance has to be JSON-safe.

	The rule passes ``network_dir`` as a shell-quoted string and the CLI parses
	values as JSON; a parameter that arrives as a non-serialisable object makes
	`write_artefact` fail after the clearing has already run.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = Path(config.paths.processed) / "market_report.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)
	build_market_report(config, out, _context(tmp_path))

	_, provenance = read_artefact(out)
	json.dumps(provenance.model_dump(mode="json"))
