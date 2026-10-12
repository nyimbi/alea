# SPDX-License-Identifier: MIT
"""The second wired serving table: a solved network's marginal prices.

WHY this module exists, and it is the register's own correction. `UNWIRED`
recorded `data/processed/market/prices.parquet` as blocked because it "needs a
solved network's marginal prices keyed by bus and a bus-to-country mapping ...
no artefact carries one". The first half is true and the second is not: the
country comes from the run's own scenario, which is where the one already-wired
serving table reads it (`_single_country`), and `scenario.countries` names one
country by default. The blocker was a config value wearing a dataset's clothes,
so the register was overstating the gap by one table.

**The refusal is the part that must survive.** A multi-country solve has no
per-bus country -- buses carry lon/lat and nothing else -- so labelling every bus
with the first country would serve a Kenyan price for a Nigerian bus. That is
the same failure `test_a_multi_country_scenario_is_refused_rather_than_labelled`
gates for contingencies, and it is gated here for prices because the two share
`_single_country` and either could regress alone.

**The fixture is a solved network, not a hand-built price frame.** The stage
resolves the newest solved network in a directory and reads
`buses_t.marginal_price` from it, so a fixture that wrote a price Parquet
directly would test a function the stage does not call. Solving a three-bus
network with two carriers gives buses that are *not* all at one price only if
the network is congested; on an uncongested one every marginal price equals the
marginal generator's cost and a stage that read the wrong bus column would still
produce a plausible frame. The fixture asserts the prices are non-empty and
finite, and the mapping gate asserts the country, which is the claim the
register got wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import registered_stages
from alea.publish.stages import build_market_prices
from alea.publish.views import PROJECTION_STAGES, PUBLISHED_TABLES, UNWIRED

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")


def _solved_network(tmp_path: Path) -> Path:
	"""A solved three-bus network, exported where the stage looks for it.

	Two carriers at different marginal costs, so the price column is a
	meaningful number rather than a constant: a fixture with one generator gives
	one price for every bus and a stage that mislabelled them would look right.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	for name, voltage in (("north", 220.0), ("mid", 132.0), ("south", 132.0)):
		network.add("Bus", name, v_nom=voltage)
	network.add("Line", "north-mid", bus0="north", bus1="mid", r=0.5, x=10.0, s_nom=400.0)
	network.add("Line", "mid-south", bus0="mid", bus1="south", r=0.5, x=10.0, s_nom=400.0)
	network.add("Generator", "coal", bus="north", carrier="coal", p_nom=400.0, marginal_cost=45.0)
	network.add("Generator", "solar", bus="mid", carrier="solar", p_nom=80.0, marginal_cost=0.0)
	network.add("Load", "load", bus="south", p_set=120.0)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the fixture network did not solve: {status} ({condition})"

	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / "abc123-2030.nc"
	network.export_to_netcdf(str(path))
	return path


def _config(tmp_path: Path, *, countries: list[str] | None = None) -> Config:
	overrides = [
		f"paths.processed={tmp_path / 'processed'}",
		f"paths.results={tmp_path / 'results'}",
		f"solve.solver_options={json.dumps({'network_dir': str(tmp_path / 'results' / 'networks')})}",
	]
	if countries is not None:
		overrides.append(f"scenario.countries={json.dumps(countries)}")
	return load_config(overrides=overrides)


class BuildContext_stub:
	"""A minimal `BuildContext`, as `test_serving_contingency` defines one."""

	def __init__(self, out: Path, parameters: dict[str, object] | None = None) -> None:
		self.out = out
		self.inputs: list[str] = []
		self.logger = None
		self.parameters: dict[str, object] = dict(parameters or {})


def test_the_stage_writes_the_published_path_and_the_api_can_read_it(tmp_path: Path):
	"""End to end: a solved network in, the API's table out, read back.

	The output path is `PUBLISHED_TABLES`'s, not a stage-shaped one. A producer
	that wrote `data/processed/market_prices.parquet` would pass its own tests
	and serve nothing, because `api.repository` reads the nested path.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_prices"]

	build_market_prices(
		config,
		out,
		BuildContext_stub(out, {"network_dir": str(tmp_path / "results" / "networks")}),
	)

	frame, provenance = read_artefact(out)
	frame = pd.DataFrame(frame)
	assert list(frame.columns) == ["at", "country_iso", "price", "unit"], (
		"the serving schema's columns are the contract `api.repository` reads"
	)
	assert not frame.empty, "the stage wrote no price rows"
	assert set(frame["country_iso"]) == {"KE"}, (
		"the buses are labelled with the scenario's country, not with the bus name"
	)
	assert set(frame["unit"]) == {"USD/MWh"}
	assert bool(frame["price"].notna().all()), "a null price is not servable"
	assert provenance.parameters["n_buses"] == 3
	assert provenance.parameters["n_snapshots"] == 24


def test_a_multi_country_scenario_is_refused_rather_than_labelled(tmp_path: Path):
	"""A price row's country is the run's, and a multi-country run has none.

	The network carries no per-bus country, so taking the first from
	`scenario.countries` would label every bus with it. A consumer filtering on
	that code gets rows that are real numbers about the wrong network -- the
	same failure the contingency stage refuses, and gated separately because the
	two stages share `_single_country` and either could regress alone.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path, countries=["KE", "NG", "ZA"])
	out = tmp_path / PUBLISHED_TABLES["market_prices"]

	with pytest.raises(ArtefactError, match="3 countries"):
		build_market_prices(
			config,
			out,
			BuildContext_stub(out, {"network_dir": str(tmp_path / "results" / "networks")}),
		)


def test_a_missing_solved_network_is_refused(tmp_path: Path):
	"""An absent input raises rather than writing an empty table.

	An empty serving table is worse than an absent one: the route answers 200
	with no rows, which reads as "no prices today" rather than as a broken
	pipeline.
	"""
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_prices"]
	empty = tmp_path / "results" / "networks"
	empty.mkdir(parents=True, exist_ok=True)

	with pytest.raises(ArtefactError, match="no solved network"):
		build_market_prices(config, out, BuildContext_stub(out, {"network_dir": str(empty)}))
	assert not out.exists(), "the stage wrote an artefact despite refusing"


def test_the_register_moved_with_the_wiring():
	"""Wiring a table moves it from `UNWIRED` into `PROJECTION_STAGES`.

	The bidirectional half, stated here as well as in the register's own gate so
	a reader of *this* module sees which table it wired and what left the gap.
	"""
	assert PROJECTION_STAGES["market_prices"] == "market_prices"
	assert "market_prices" in registered_stages()
	assert PUBLISHED_TABLES["market_prices"] not in UNWIRED, (
		"the table is wired and still recorded as a gap, so the register "
		"overstates it"
	)
