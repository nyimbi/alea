# SPDX-License-Identifier: MIT
"""The `scenario_update` producer: the quarterly range across a sweep.

`reporting/producers.py` recorded this section's blocker as a *wiring* gap and
that is what it was: `alea.whatif` could sweep a parameter and cache the
solves, and `alea.api.whatif` could write a frontier -- to a caller-chosen path,
from an HTTP job, which is a route's shape rather than a report's. No rule ran a
sweep and landed the section's frame at the section's own dated path.

Four things are pinned here, each because the alternative is a table that looks
right:

* the register move -- the slug left `UNPRODUCED` and arrived in `PRODUCERS`
  and `PROJECTED`, with a rule and a dvc stage behind it;
* `frontier_rows`, whose two numeric columns are what let `_rows_for` bind
  `Capacity` and `Cost` to *different* numbers rather than repeating the
  primary into both;
* the binding itself, through the real `_rows_for` -- the frame is only correct
  if the reader that consumes it renders four columns from it;
* the provenance, which states that a sweep is a range across scenarios and not
  a forecast of one, because a table of five costs under a header promising a
  range reads as five predictions if nothing says otherwise.

The sweep goes through `sweep_parameter` rather than `efficient_frontier`, and
`test_the_rows_come_from_the_result_and_not_the_frontier_frame` is that choice
pinned: the frontier frame drops `capacity_mix_mw`, so a producer built on it
would have to re-derive capacity from cost.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage
from alea.provenance.models import Basis
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.service import _rows_for
from alea.whatif.params import ScenarioParameters
from alea.whatif.service import WhatIfEngine
from alea.whatif.stages import frontier_rows, scenario_update_to_artefact
from alea.whatif.sweep import sweep_parameter
from alea.whatif.views import SolveOutcome

REPO = Path(__file__).resolve().parents[2]

#: Two planning years, because `ScenarioParameters.demand_growth` defaults to
#: 0.04 and `apply_parameters` refuses it on a single-period network -- the
#: growth exponent would be zero everywhere and the parameter would silently do
#: nothing. Layer 1 produces a multi-period network, so this is the shape the
#: engine is handed in production.
SNAPSHOTS = pd.DatetimeIndex(
	[
		ts
		for year in (2030, 2040)
		for ts in pd.date_range(f"{year}-01-01", periods=4, freq="h")
	]
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _network() -> pypsa.Network:
	"""A coal unit and an extendable solar farm, as `test_whatif_layer5` builds.

	The carbon price is a surcharge on the coal unit's marginal cost, so every
	sweep point costs *differently* -- a fixture where the parameter touched
	nothing would give a flat frontier, which is the shape a broken sweep
	produces and this module has to be able to tell from a working one.

	The nameplate does *not* move across the sweep here, and that is the
	fixture's economics rather than a defect: `p_nom_max=400` is never binding
	against a 120 MW load, so the build is fixed by the peak and the carbon
	price only decides how much of it runs. A fixture whose capacity *does*
	move needs the build to sit against a binding `p_nom_max` with load above
	the fixed fleet -- a different test's fixture, not this one's claim.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "b1", carrier="AC")
	network.add(
		"Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0
	)
	network.add(
		"Generator",
		"solar",
		bus="b1",
		carrier="solar",
		p_nom=20.0,
		p_nom_max=400.0,
		p_nom_extendable=True,
		capital_cost=50_000.0,
	)
	network.add("Load", "load", bus="b1", p_set=120.0)
	return network


def _solved_file(tmp_path: Path) -> Path:
	"""A solved base network on disk, at the path a rule's input resolves to."""
	network = _network()
	network.optimize(solver_name="highs", log_to_console=False)
	network.model.solver_model = None
	path = tmp_path / "results" / "networks" / "abcd1234-2030.nc"
	path.parent.mkdir(parents=True, exist_ok=True)
	network.export_to_netcdf(str(path))
	return path


def _config(tmp_path: Path, **whatif: object) -> Config:
	overrides = [
		f"paths.processed={tmp_path / 'processed'}",
		f"paths.results={tmp_path / 'results'}",
		f"paths.reports={tmp_path / 'reports'}",
		"reporting.pdf_enabled=false",
	]
	overrides.extend(f"whatif.{key}={value}" for key, value in whatif.items())
	return load_config(overrides=overrides)


def _outcomes(tmp_path: Path, values: list[float]) -> list[SolveOutcome]:
	engine = WhatIfEngine(_solved_file(tmp_path), cache_root=tmp_path / "cache")
	return list(sweep_parameter(engine, "carbon_price_usd_per_tco2", values))


# --------------------------------------------------------------------------
# The register move
# --------------------------------------------------------------------------


def test_the_section_left_the_unproduced_register():
	"""The quarterly range now has a producer, and a rule that delivers it.

	Pinned as a set rather than a boolean: "not in `UNPRODUCED`" alone is
	satisfied by a slug in neither register, which is the state a half-finished
	move leaves.
	"""
	assert "scenario_update" not in UNPRODUCED, (
		"`scenario_update` is back in `UNPRODUCED`; the quarterly range has a "
		"producer, so the entry would be a claim about a gap that is closed"
	)
	assert PRODUCERS.get("scenario_update") == "whatif.stages.build_scenario_update", (
		f"`PRODUCERS` names {PRODUCERS.get('scenario_update')!r}; the producer is "
		f"the stage in `whatif/stages.py`"
	)
	assert PROJECTED.get("scenario_update") == "project_scenario_update", (
		f"`PROJECTED` names {PROJECTED.get('scenario_update')!r}; the quarterly "
		f"projection is what lands the section at its dated path"
	)


def test_the_stage_is_reachable_by_name():
	"""The producer is registered, not merely decorated.

	A `@stage`-decorated function is reachable only once its module is imported,
	and the registry's own history is a stage that was "written, decorated and
	unreachable". The call must fail on the *data*, never on `unknown stage`.
	"""
	with pytest.raises(Exception) as caught:
		build_stage("scenario_update", _config(Path("/tmp/unused")), Path("/tmp/unused.parquet"))
	assert "unknown stage" not in str(caught.value), (
		"`scenario_update` is not in the stage registry; the CLI would report "
		"`unknown stage` for a producer the register says exists"
	)


# --------------------------------------------------------------------------
# frontier_rows: the frame, and the two numbers it must keep apart
# --------------------------------------------------------------------------


def test_the_rows_come_from_the_result_and_not_the_frontier_frame(tmp_path: Path):
	"""Capacity is read off the solved result, which the frontier frame drops.

	`efficient_frontier`'s points carry cost, emissions and renewable share and
	no `capacity_mix_mw`. Building this frame from them would mean re-deriving
	capacity from cost, which is inventing the section's own first quantity.
	"""
	outcomes = _outcomes(tmp_path, [0.0, 100.0])
	frame = frontier_rows(outcomes, "carbon_price_usd_per_tco2")

	assert "capacity" in frame.columns and "cost" in frame.columns
	# The base network's own carriers, summed from `capacity_mix_mw` -- the
	# field the frontier point does not carry.
	for position, outcome in enumerate(outcomes):
		expected = float(sum(outcome.result.capacity_mix_mw.values()))
		assert frame["capacity"].iloc[position] == pytest.approx(expected), (
			"the row's capacity is not the result's own `capacity_mix_mw` sum"
		)
		assert frame["cost"].iloc[position] == pytest.approx(outcome.result.total_cost_usd)


def test_the_sweep_moves_the_cost_the_section_reports(tmp_path: Path):
	"""A frontier whose rows are identical is the failure this section hides.

	A parameter that reaches no column produces a flat table that renders
	perfectly and says "this does not matter". The carbon price is a surcharge
	on every emitting carrier's marginal cost, so the system cost must rise with
	it -- strictly, because the surcharge is positive on every MWh coal serves.

	**Capacity is a different claim and is deliberately not asserted here.** On
	a network whose capacity factors are flat, the build is set by the peak load
	and the optimiser's choice is *which* carrier, not how much -- so a carbon
	price that moves the cost can leave the total nameplate unchanged, and that
	is correct physics rather than a broken sweep. The property this producer
	owes the section is that `capacity` is the *result's* own field and not a
	number re-derived from the cost, which
	`test_the_rows_come_from_the_result_and_not_the_frontier_frame` pins.
	"""
	frame = frontier_rows(
		_outcomes(tmp_path, [0.0, 50.0, 200.0]), "carbon_price_usd_per_tco2"
	)
	costs = list(frame["cost"])
	assert costs == sorted(costs) and len(set(costs)) == 3, (
		f"the sweep costs {costs}; a carbon price raises every emitting "
		f"carrier's marginal cost, so a flat or falling sequence means the "
		f"parameter did not reach the solve and the section would report a range "
		f"that is not one"
	)


def test_the_label_names_the_parameter_and_its_value(tmp_path: Path):
	"""A table of five numbers under one header is unreadable without it.

	The first column is `Scenario`, and a UUID7 would be stable and tell a
	reader nothing about where the row sits on the sweep.
	"""
	frame = frontier_rows(_outcomes(tmp_path, [0.0, 50.0]), "carbon_price_usd_per_tco2")
	assert list(frame["label"]) == [
		"carbon_price_usd_per_tco2=0",
		"carbon_price_usd_per_tco2=50",
	], f"the labels are {list(frame['label'])}"


def test_the_frame_carries_the_three_columns_the_assembler_needs(tmp_path: Path):
	"""`label`/`value`/`unit` are the contract; the rest are the row's quantities."""
	frame = frontier_rows(_outcomes(tmp_path, [0.0, 50.0]), "carbon_price_usd_per_tco2")
	assert list(frame.columns) == ["label", "value", "unit", "capacity", "cost"], (
		f"the frame's columns are {list(frame.columns)}"
	)
	assert set(frame["unit"]) == {"MW"}, (
		"the section's unit is MW, and `value` is the capacity column"
	)
	assert frame["value"].tolist() == frame["capacity"].tolist(), (
		"`value` is the primary the section's caption names; it must be the "
		"capacity the `Capacity` column also reads"
	)


def test_an_empty_sweep_is_refused():
	"""A frontier over nothing is not a scenario set."""
	with pytest.raises(AssertionError):
		frontier_rows([], "carbon_price_usd_per_tco2")


# --------------------------------------------------------------------------
# The binding: the frame against the columns the section declares
# --------------------------------------------------------------------------


def test_the_frame_fills_the_sections_four_columns(tmp_path: Path):
	"""The reader's own layout function, on the producer's own frame.

	The section declares `["Scenario", "Capacity", "Cost", "Basis"]`. Two of
	those are numeric, and `_rows_for` binds each header to the row column
	*naming* it -- so a frame that folded capacity and cost together would raise
	here rather than printing the capacity twice.
	"""
	from alea.reporting.assemble import values_from_artefact

	config = _config(tmp_path, sweep_values=[0.0, 50.0])
	path = Path(config.paths.processed) / "scenario_update.parquet"
	scenario_update_to_artefact(config, path, engine=_engine(tmp_path))

	values = values_from_artefact(path)
	rows = _rows_for(values, ["Scenario", "Capacity", "Cost", "Basis"], slug="scenario_update")

	assert len(rows) == 2, f"{len(rows)} rows for a two-point sweep"
	for row in rows:
		assert str(row[0]).startswith("carbon_price_usd_per_tco2="), (
			f"the identity column holds {row[0]!r}"
		)
		capacity, cost = row[1], row[2]
		assert getattr(capacity, "value", capacity) != getattr(cost, "value", cost), (
			"Capacity and Cost hold the same number; the frame folded the two "
			"quantities into one column and the reader repeated it"
		)
		assert row[3] == Basis.MODELLED.value, f"the basis column holds {row[3]!r}"


# --------------------------------------------------------------------------
# The artefact and its provenance
# --------------------------------------------------------------------------


def test_the_producer_writes_the_sections_frame(tmp_path: Path):
	config = _config(tmp_path)
	path = Path(config.paths.processed) / "scenario_update.parquet"
	provenance, frame = scenario_update_to_artefact(
		config, path, engine=_engine(tmp_path)
	)

	assert path.exists(), "the producer wrote nothing"
	data, read_back = read_artefact(path)
	assert list(data.columns) == list(frame.columns)
	assert read_back.source_id == "scenario_update"
	assert provenance.basis is Basis.MODELLED, (
		"a sweep is a modelled quantity; a different basis would downgrade every "
		"row the section renders"
	)


def test_the_provenance_records_which_parameter_was_swept(tmp_path: Path):
	"""A reader cannot tell one frontier from another by its shape.

	A frontier over carbon price and one over demand growth have the same
	columns, the same units and the same row count. The parameter is the only
	thing that says which question the table answers, so it travels in the
	artefact and not only in the config file that produced it.
	"""
	config = _config(tmp_path, sweep_values=[0.0, 50.0])
	path = Path(config.paths.processed) / "scenario_update.parquet"
	provenance, _ = scenario_update_to_artefact(config, path, engine=_engine(tmp_path))

	assert provenance.parameters["parameter"] == "carbon_price_usd_per_tco2"
	assert provenance.parameters["sweep_values"] == [0.0, 50.0]
	assert provenance.parameters["points"] == 2
	assert provenance.parameters["network_checksum"], (
		"the base network is not recorded; two frontiers over different networks "
		"would be incomparable with nothing in the artefact saying so"
	)


def test_the_notes_say_a_range_is_not_a_forecast(tmp_path: Path):
	"""Five costs under a header promising a range read as five predictions.

	The parameter is the only thing that moved between rows and every other
	parameter is the engine's default; the provenance has to say so, because a
	consumer reading the parquet has no access to this module's docstrings.
	"""
	config = _config(tmp_path)
	path = Path(config.paths.processed) / "scenario_update.parquet"
	provenance, _ = scenario_update_to_artefact(config, path, engine=_engine(tmp_path))

	assert "range" in provenance.notes, (
		f"the notes do not describe the table as a range: {provenance.notes!r}"
	)
	assert "not a forecast" in provenance.notes, (
		f"the notes do not refuse the forecast reading: {provenance.notes!r}"
	)


# --------------------------------------------------------------------------
# The stage: the directory walk and the idempotence check
# --------------------------------------------------------------------------


def _engine(tmp_path: Path) -> WhatIfEngine:
	return WhatIfEngine(_solved_file(tmp_path), cache_root=tmp_path / "cache")


def test_a_directory_with_no_solve_is_refused(tmp_path: Path):
	"""An empty frame would render as a section that found no scenarios.

	That is a claim about the model rather than about the directory, so the
	stage raises and names the directory it looked in.
	"""
	config = _config(tmp_path)
	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	with pytest.raises(Exception) as caught:
		build_stage(
			"scenario_update",
			config,
			Path(config.paths.processed) / "scenario_update.parquet",
			inputs=[],
			parameters={"network_dir": str(directory)},
		)
	assert "no solved network" in str(caught.value), (
		f"the refusal does not name the gap: {caught.value}"
	)


def test_the_stage_is_idempotent_on_the_same_solve(tmp_path: Path):
	"""A second run against an unchanged network must exit without work.

	The stage resolves the newest solve itself -- a rule cannot name a filename
	carrying a content hash -- so it calls `skip_if_current` on the checksum it
	resolved. Without that, every `alea build` re-solved the whole sweep.
	"""
	config = _config(tmp_path)
	_solved_file(tmp_path)
	out = Path(config.paths.processed) / "scenario_update.parquet"
	parameters = {"network_dir": str(tmp_path / "results" / "networks")}

	first = build_stage("scenario_update", config, out, inputs=[], parameters=parameters)
	assert not first.skipped, "the first run skipped; the fixture wrote nothing"
	second = build_stage("scenario_update", config, out, inputs=[], parameters=parameters)
	assert second.skipped, (
		"the second run re-solved the sweep; the stage's `skip_if_current` check "
		"did not see the network checksum it recorded"
	)


def test_a_sweep_of_one_point_is_refused_by_the_config(tmp_path: Path):
	"""A frontier needs two values or it reports a scenario set of one.

	The override is written as a list because that is what `_coerce` parses it
	to: `yaml.safe_load("(50.0,)")` is the *string* `"(50.0,)"`, which pydantic
	refuses as a tuple before any validator sees it. Written as a tuple literal
	the test would pass on the wrong message and never exercise the check.
	"""
	with pytest.raises(Exception) as caught:
		_config(tmp_path, sweep_values=[50.0])
	assert "not a range" in str(caught.value), (
		f"a one-point sweep loaded without complaint: {caught.value}"
	)


def test_an_unknown_parameter_is_refused_at_load(tmp_path: Path):
	"""A typo is a `KeyError` minutes into a sweep, not a flat frontier.

	`extra="forbid"` already refuses an unknown config *key*; this refuses an
	unknown *value*, which is the failure that reaches the solver.
	"""
	with pytest.raises(Exception) as caught:
		_config(tmp_path, parameter="carbon_price")
	assert "unknown scenario parameter" in str(caught.value), (
		f"an unsweepable parameter loaded without complaint: {caught.value}"
	)


def test_every_configured_parameter_is_a_scenario_field():
	"""The validator's own list is the model's, not a copy that can drift."""
	from alea.whatif.views import WhatIfConfig

	known = set(ScenarioParameters.model_fields)
	for name in sorted(known):
		assert WhatIfConfig(parameter=name).parameter == name, (
			f"{name} is a `ScenarioParameters` field the config refuses"
		)
