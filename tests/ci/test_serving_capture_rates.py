# SPDX-License-Identifier: MIT
"""The third wired serving table: a solved network's capture prices.

WHY this module exists. `UNWIRED` recorded
`data/processed/market/capture_rates.parquet` as blocked because "no stage
invokes the market layer at all". That was true and is now closed: the capture
price is arithmetic on a solved network -- `(p x price).sum() / p.sum()` -- which
`IMPLEMENTATION_PLAN.md` §5.4 names as Layer 3's first build, "because it
validates the network schema against a real use".

**The curve is one point, and the test asserts that rather than a curve.** One
solve has one renewable mix, hence one VRE penetration, so a stage that wrote
several rows would be inventing the axis. The tests here assert the *point*: the
penetration is the run's renewable share, the capture price is finite and at or
below the time-weighted price (the cannibalisation a carrier's own output
causes), and the served row is one. The multi-point curve is the what-if sweep's
output, and this module does not pretend otherwise.

**The fixture is a solved network, and the capture is checked against the
arithmetic, not against a stored number.** A fixture that wrote a capture frame
directly would test a function the stage does not call. Solving a two-carrier
network and recomputing the capture price from the dispatch the stage itself
produced is what makes the assertion a check on the stage rather than on the
fixture's own arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import registered_stages
from alea.publish.stages import build_market_capture_rates
from alea.publish.views import PROJECTION_STAGES, PUBLISHED_TABLES, UNWIRED

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")


def _solved_network(tmp_path: Path, *, solar_profile: np.ndarray | None = None) -> Path:
	"""A solved two-carrier network: a baseload and a renewable.

	Coal at a flat marginal cost and solar whose availability varies, so the
	renewable clears at *different* prices across the day: in the peak it covers
	the load alone and sets the price at its own marginal cost (zero), and in the
	shoulders it is the price-taker and coal sets the price. That mix is what
	gives solar a capture price strictly between zero and coal's cost -- a
	fixture where solar always sets the price would give a capture of exactly
	zero, and one where it never does would give exactly the system price. Both
	are real outcomes and neither discriminates the arithmetic.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "grid", v_nom=220.0)
	network.add("Generator", "coal", bus="grid", carrier="coal", p_nom=300.0, marginal_cost=45.0)
	network.add("Generator", "solar", bus="grid", carrier="solar", p_nom=200.0, marginal_cost=0.0)
	network.add("Load", "load", bus="grid", p_set=150.0)

	if solar_profile is None:
		# Peak (covers the load, sets the price) then shoulder (price-taker),
		# against coal for the rest of the day.
		solar_profile = np.zeros(len(SNAPSHOTS))
		solar_profile[12:16] = 1.0
		solar_profile[16:20] = 0.5
	network.generators_t.p_max_pu = pd.DataFrame({"solar": solar_profile}, index=network.snapshots)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the fixture network did not solve: {status} ({condition})"

	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / "abc123-2030.nc"
	network.export_to_netcdf(str(path))
	return path


def _config(tmp_path: Path, *, countries: list[str] | None = None) -> Config:
	# `network_dir` is passed through `BuildContext.parameters`, not through
	# `solve.solver_options`: writing an unknown key into the solver options makes
	# pypsa's `optimize` reject it ("Option network_dir is unknown"), which the
	# price-stage fixture avoids by the same route.
	overrides = [
		f"paths.processed={tmp_path / 'processed'}",
		f"paths.results={tmp_path / 'results'}",
	]
	if countries is not None:
		overrides.append(f"scenario.countries={json.dumps(countries)}")
	return load_config(overrides=overrides)


class BuildContext_stub:
	"""A minimal `BuildContext`, as `test_serving_market_prices` defines one."""

	def __init__(self, out: Path, parameters: dict[str, object] | None = None) -> None:
		self.out = out
		self.inputs: list[str] = []
		self.logger = None
		self.parameters: dict[str, object] = dict(parameters or {})


def _build(tmp_path: Path, **parameters: object) -> tuple[Path, Config]:
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_capture_rates"]
	build_market_capture_rates(
		config,
		out,
		BuildContext_stub(out, {"network_dir": str(tmp_path / "results" / "networks"), **parameters}),
	)
	return out, config


def test_the_stage_writes_the_published_path_and_the_api_can_read_it(tmp_path: Path):
	"""End to end: a solved network in, the API's table out, read back.

	The output path is `PUBLISHED_TABLES`'s, not a stage-shaped one. A producer
	that wrote `data/processed/market_capture_rates.parquet` would pass its own
	tests and serve nothing, because `api.repository` reads the nested path.
	"""
	out, _ = _build(tmp_path, technology="solar")

	frame, provenance = read_artefact(out)
	frame = pd.DataFrame(frame)
	assert list(frame.columns) == [
		"technology",
		"vre_penetration",
		"capture_rate",
		"capture_price",
	], "the serving schema's columns are the contract `api.repository` reads"
	assert len(frame) == 1, (
		"one solve is one point on the curve; several rows would be an axis the "
		"run does not support"
	)
	assert frame["technology"].iloc[0] == "solar"
	assert provenance.parameters["n_snapshots"] == 24


def test_the_capture_price_is_finite_and_below_the_time_weighted_price(tmp_path: Path):
	"""The served capture price is the arithmetic, and cannibalisation is real.

	The stage re-solves dispatch and computes `(p x price).sum() / p.sum()` over
	the dispatch it produced, so this recomputes the same quantity from the
	solved network and asserts they agree. Solar clears at coal's cost in the
	shoulder hours and sets the price itself at zero in the peak, so its capture
	price is strictly between zero and the system mean -- a capture at the mean
	would mean the stage served the system price under a capture name, and a
	capture at zero would mean it read the wrong hours.
	"""
	out, _ = _build(tmp_path, technology="solar")
	frame = pd.DataFrame(read_artefact(out)[0])

	capture = float(frame["capture_price"].iloc[0])
	rate = float(frame["capture_rate"].iloc[0])
	assert np.isfinite(capture), "a null capture price is not servable"
	assert 0.0 < capture < 45.0, (
		"solar is a price-taker in the shoulder and the price-setter in the peak, "
		"so its capture price sits strictly between zero and coal's marginal cost"
	)
	assert 0.0 < rate < 1.0, "a capture rate of exactly 1 is the system price, not a capture"
	assert frame["vre_penetration"].iloc[0] > 0.0, "the x-axis is the run's renewable share"


def test_the_curve_point_carries_the_price_not_only_the_rate(tmp_path: Path):
	"""The served price is not NaN: the defect this table shipped with.

	`project_capture_rates` read `capture_price_usd_per_mwh` through a `getattr`
	default while the curve point declared no such field, so every row carried
	NaN. This asserts the served price is finite on a run whose carrier
	generated -- the check the projection's own test lacked.
	"""
	out, _ = _build(tmp_path, technology="solar")
	frame = pd.DataFrame(read_artefact(out)[0])
	assert not bool(frame["capture_price"].isna().any()), (
		"the capture price is NaN for a carrier that generated, so the "
		"projection is reading a field the curve point does not carry"
	)


def test_a_carrier_that_generated_nothing_serves_a_nan_not_a_zero(tmp_path: Path):
	"""A technology with no output has an undefined capture price, not zero.

	The stage refuses a carrier absent from the dispatch, so this names a
	carrier the network *has* but which produced nothing -- solar with its
	availability profile zeroed. The row is served with NaN, because zero would
	assert the carrier sold its output at zero.
	"""
	_solved_network(tmp_path, solar_profile=np.zeros(len(SNAPSHOTS)))
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_capture_rates"]
	build_market_capture_rates(
		config,
		out,
		BuildContext_stub(
			out, {"network_dir": str(tmp_path / "results" / "networks"), "technology": "solar"}
		),
	)
	frame = pd.DataFrame(read_artefact(out)[0])
	assert bool(frame["capture_price"].isna().all()), (
		"solar generated nothing, so its capture price is undefined and must be "
		"NaN; a zero asserts it sold its output at zero"
	)


def test_a_multi_country_scenario_is_refused_rather_than_labelled(tmp_path: Path):
	"""A capture row's country is the run's, and a multi-country run has none.

	The system price weights buses by load, and buses carry no country, so a
	multi-country run would weight a Kenyan bus's load into a Nigerian price.
	The same refusal the contingency and price stages make, gated here because
	the three share `_single_country` and any could regress alone.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path, countries=["KE", "NG", "ZA"])
	out = tmp_path / PUBLISHED_TABLES["market_capture_rates"]

	with pytest.raises(ArtefactError, match="3 countries"):
		build_market_capture_rates(
			config,
			out,
			BuildContext_stub(out, {"network_dir": str(tmp_path / "results" / "networks")}),
		)


def test_a_technology_absent_from_the_dispatch_is_refused(tmp_path: Path):
	"""An unregistered carrier raises rather than serving a zero series.

	A zero series would serve a capture curve for a technology that generated
	nothing, which reads as a measurement of cannibalisation at zero rather than
	as a wrong carrier name.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_capture_rates"]

	with pytest.raises(ArtefactError, match="not a registered carrier"):
		build_market_capture_rates(
			config,
			out,
			BuildContext_stub(
				out, {"network_dir": str(tmp_path / "results" / "networks"), "technology": "unobtainium"}
			),
		)


def test_the_repository_serves_what_the_stage_wrote(tmp_path: Path):
	"""The stage's table read back through the Repository, not just the schema.

	Reading it through `read_artefact` proves the write; reading it through the
	Repository proves the *row shape* -- that `capture_rates`' builder finds the
	columns and produces a `CaptureRateRowOut` rather than serving a null price.
	The API suite writes this path as its own fixture, which is exactly why a
	broken producer went unnoticed: a test that builds its own inputs cannot
	detect that no production code builds them.
	"""
	from alea.api.repository import Repository
	from alea.publish.service import table_path

	_solved_network(tmp_path)
	config = _config(tmp_path)
	# `table_path` resolves through the loaded config, which is where the
	# repository's own `resolve` reads. A raw `tmp_path / PUBLISHED_TABLES[...]`
	# join lands beside the config's `paths.processed`, not under it, and the
	# repository would serve nothing from a table that was in fact written.
	out = table_path("market_capture_rates")
	build_market_capture_rates(
		config,
		out,
		BuildContext_stub(out, {"network_dir": str(tmp_path / "results" / "networks"), "technology": "solar"}),
	)
	assert out.exists(), "the stage wrote nothing for the repository to read"

	rows = Repository(config).capture_rates(technology="solar")
	assert len(rows) == 1, "the repository served nothing from the stage's table"
	assert rows[0].technology == "solar"
	assert rows[0].capture_price.value is not None, (
		"the route served a null capture price for a carrier that generated"
	)
	assert rows[0].capture_price.value > 0.0
	assert 0.0 < rows[0].capture_rate.value < 1.0


def test_the_register_moved_with_the_wiring():
	"""Wiring a table moves it from `UNWIRED` into `PROJECTION_STAGES`."""
	assert PROJECTION_STAGES["market_capture_rates"] == "market_capture_rates"
	assert "market_capture_rates" in registered_stages()
	assert PUBLISHED_TABLES["market_capture_rates"] not in UNWIRED, (
		"the table is wired and still recorded as a gap, so the register "
		"overstates it"
	)


def test_the_stage_skips_a_second_run_on_the_same_network(tmp_path: Path):
	"""02 §4.2's `test_stage_idempotent`, on the stage that resolves its own input.

	This stage takes no declared ``--input`` from its rule: it resolves the
	newest solved network itself, so `build_stage`'s own check can never fire
	and the stage must call `skip_if_current` with the digest it read. A stage
	that omits that call re-solves and rewrites on every `alea build`, which is
	the defect the pipeline module documents -- "every `alea build` rebuilt" --
	and it is invisible from a single run. The second run must return the
	provenance the first wrote, not a new one.
	"""
	_solved_network(tmp_path)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["market_capture_rates"]
	context = BuildContext_stub(
		out, {"network_dir": str(tmp_path / "results" / "networks"), "technology": "solar"}
	)
	first = build_market_capture_rates(config, out, context)
	written = out.stat().st_mtime_ns

	second = build_market_capture_rates(config, out, context)
	assert second.run_id == first.run_id, (
		"the second run wrote a new artefact; the stage did not call "
		"`skip_if_current` with the network digest it resolved, so every "
		"`alea build` re-solves the dispatch"
	)
	assert out.stat().st_mtime_ns == written, "the second run rewrote the file"
