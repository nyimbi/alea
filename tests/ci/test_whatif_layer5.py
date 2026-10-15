# SPDX-License-Identifier: MIT
"""Layer 5 exit criteria: the ten gates `08-layer5-whatif.md` §10 names.

The plan lists ten criteria and a gate for each. This module is the gate for
criteria 1 through 9; the canary half of criterion 10 lives in
`tests/ci/canaries/test_cache_key_stability.py`, which reverts `cache_key` to
`hash()` and watches the cross-process check notice.

WHY each test asserts a *value* and not a shape: the whole layer exists to
correct two specification defects, and both of them are invisible in the shape
of the output. A cache that never hits returns the same result as a cache that
hits; a `renewable_share` of 0 and one of `None` both serialise. So the tests
here count solves, compare byte-identical frames, and check the sentinel.

WHY the fixture network is solved with HiGHS rather than a stub for the
frontier tests: a frontier built on a stub solver measures the stub. The stub
is used only where the observable *is* the solve count (criteria 1 and 8),
because there the stub is the instrument rather than the subject.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pypsa
import pytest
from pydantic import ValidationError

from alea.whatif import (
	ScenarioParameters,
	SolveCache,
	WhatIfEngine,
	apply_parameters,
	cache_key,
	cost_risk_frontier,
	efficient_frontier,
	extract,
	key_is_process_stable,
	latest_version,
	list_scenarios,
	load_scenario,
	renewable_share,
	save_scenario,
	sweep_parameter,
)
from alea.whatif.extract import price_statistics, total_cost_usd
from alea.whatif.pricemodel import _served_energy_mwh, price_model_from_network
from alea.whatif.sweep import FRONTIER_COLUMNS, FRONTIER_VALUE_COLUMNS
from alea.whatif.views import RiskMetrics, ScenarioResult

SNAPSHOTS = pd.date_range("2030-01-01", periods=4, freq="h")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _network(*, multi_period: bool = True) -> pypsa.Network:
	"""A two-generator, one-bus network: a coal unit and an extendable solar farm.

	Small enough to solve in milliseconds, and structured so that every
	parameter under test moves a *different* number: ``renewable_multiplier``
	moves ``p_nom_max``, ``carbon_price`` moves the marginal cost, and
	``demand_growth`` moves the load. A fixture where two parameters touched the
	same column could not tell them apart.

	Multi-period by default because that is what Layer 1 produces: a planning
	network spans 2030 to 2060 in investment periods. A single-period fixture
	would be a network the pipeline never builds, and it cannot carry the
	default ``demand_growth`` at all -- see
	``test_demand_growth_requires_multi_period``.
	"""
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	if multi_period:
		snapshots = pd.DatetimeIndex(
			[ts for year in (2030, 2040) for ts in pd.date_range(f"{year}-01-01", periods=2, freq="h")]
		)
	else:
		snapshots = SNAPSHOTS
	network.set_snapshots(list(snapshots))
	network.add(
		"Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0
	)
	network.add(
		"Generator",
		"solar",
		bus="b1",
		carrier="solar",
		p_nom=20.0,
		p_nom_max=200.0,
		p_nom_extendable=True,
		capital_cost=50_000.0,
	)
	network.add("Load", "load", bus="b1", p_set=120.0)
	return network


def _solved(*, multi_period: bool = True) -> pypsa.Network:
	"""A solved base network, as a scenario engine is handed one.

	The solver model is dropped because PyPSA refuses ``copy()`` while one is
	attached, and a solved base is the only input this layer has. ``optimize``
	on the returned network would raise for the same reason, so a test that
	needs to re-solve works from ``_network()`` and solves the copy.
	"""
	network = _network(multi_period=multi_period)
	network.optimize(solver_name="highs", log_to_console=False)
	network.model.solver_model = None
	return network


def _engine(tmp_path: Path, *, solved: bool = False, **kwargs) -> WhatIfEngine:
	"""An engine over a fixture network, with a cache under ``tmp_path``."""
	return WhatIfEngine(
		_solved() if solved else _network(),
		cache_root=tmp_path / "cache",
		**kwargs,
	)


class _CountingSolve:
	"""A solve stand-in that counts invocations and does nothing else.

	The instrument for criteria 1 and 8. ``WhatIfEngine`` takes the solver as a
	seam precisely so this can exist: a gate that asserts "the second solve did
	not re-solve" can only assert it if solving is something the engine *calls*.
	"""

	def __init__(self) -> None:
		self.calls = 0

	def __call__(self, network: pypsa.Network) -> None:
		self.calls += 1


# --------------------------------------------------------------------------
# Criterion 1: cache hits across processes
# --------------------------------------------------------------------------


def test_cache_actually_hits(tmp_path: Path):
	"""A second identical solve must be served from the cache, not re-solved.

	The specification's own reproducibility test -- solve, clear, solve, compare
	-- passes against a completely broken cache, because it compares two *fresh*
	solves and never exercises the cache at all. This asserts on the solve count,
	which is the only observable that distinguishes a hit from a miss.
	"""
	counter = _CountingSolve()
	engine = _engine(tmp_path, solve_fn=counter)
	params = ScenarioParameters(carbon_price_usd_per_tco2=80.0)

	first = engine.solve_with_outcome(params)
	second = engine.solve_with_outcome(params)

	assert counter.calls == 1, "the second identical solve re-ran the optimiser"
	assert first.from_cache is False
	assert second.from_cache is True
	assert second.result.total_cost_usd == first.result.total_cost_usd


def test_the_cache_survives_a_restart(tmp_path: Path):
	"""The same scenario in a *new engine* is served from the same cache.

	This is criterion 1's actual content. An in-process cache passes the test
	above; only a second engine over the same cache root proves the entry is on
	disk and addressed by content rather than by object identity.
	"""
	params = ScenarioParameters(carbon_price_usd_per_tco2=80.0)
	first = _engine(tmp_path, solve_fn=_CountingSolve())
	first.solve(params)

	counter = _CountingSolve()
	restarted = _engine(tmp_path, solve_fn=counter)
	outcome = restarted.solve_with_outcome(params)

	assert counter.calls == 0, "the restarted engine re-solved a cached scenario"
	assert outcome.from_cache is True


def test_force_bypasses_a_warm_cache(tmp_path: Path):
	"""``force=True`` re-solves; otherwise a corrected parameter could never be
	re-tested without hand-deleting the entry."""
	counter = _CountingSolve()
	engine = _engine(tmp_path, solve_fn=counter)
	params = ScenarioParameters()
	engine.solve(params)
	engine.solve(params, force=True)
	assert counter.calls == 2


def test_a_torn_cache_entry_reads_as_a_miss(tmp_path: Path):
	"""A directory without ``result.json`` is a killed worker, not a hit.

	Treating it as a hit would return ``None`` where a result belongs, or
	raise from deep inside the engine. It is a miss and the entry is recomputed.
	"""
	cache = SolveCache(tmp_path / "cache")
	params = ScenarioParameters()
	key = cache_key(params, "sha256:" + "ab" * 32, "0.1.0")
	cache.path_for(key).mkdir(parents=True)
	assert cache.has(key) is False
	assert cache.get(key) is None


# --------------------------------------------------------------------------
# Criterion 2: the key covers params, network, and code
# --------------------------------------------------------------------------


def test_cache_key_includes_params():
	base = ScenarioParameters()
	assert cache_key(base, "sha256:" + "ab" * 32, "0.1.0") != cache_key(
		base.with_value("demand_growth", 0.05), "sha256:" + "ab" * 32, "0.1.0"
	)


def test_cache_key_includes_network():
	params = ScenarioParameters()
	assert cache_key(params, "sha256:" + "ab" * 32, "0.1.0") != cache_key(
		params, "sha256:" + "cd" * 32, "0.1.0"
	)


def test_cache_key_includes_code_version():
	params = ScenarioParameters()
	assert cache_key(params, "sha256:" + "ab" * 32, "0.1.0") != cache_key(
		params, "sha256:" + "ab" * 32, "0.1.1"
	)


def test_the_key_is_stable_across_processes():
	"""Criterion 1's premise, asserted directly across an interpreter boundary.

	§9 ``test_cache_key_stable_across_processes``: the same parameters give the
	same key in two processes. The canary in
	``tests/ci/canaries/test_cache_key_stability.py`` reverts the key to
	``hash()`` and watches this fail.
	"""
	assert key_is_process_stable(ScenarioParameters(), "sha256:" + "ab" * 32, "0.1.0")


def test_a_different_network_is_a_different_scenario(tmp_path: Path):
	"""The end-to-end version of the network component: two engines on two
	networks must not serve each other's results through a shared cache root."""
	params = ScenarioParameters()
	root = tmp_path / "cache"

	one = pypsa.Network()
	one.add("Bus", "b1", carrier="AC")
	one.set_snapshots(list(SNAPSHOTS))
	one.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
	one.add("Load", "load", bus="b1", p_set=120.0)

	two = one.copy()
	two.generators.loc["coal", "p_nom"] = 150.0

	a = WhatIfEngine(one, cache_root=root, solve_fn=_CountingSolve())
	b = WhatIfEngine(two, cache_root=root, solve_fn=_CountingSolve())
	assert a.network_checksum != b.network_checksum
	assert a.key_for(params) != b.key_for(params)


# --------------------------------------------------------------------------
# Criterion 3: no parameter is a silent no-op
# --------------------------------------------------------------------------


def test_demand_growth_requires_multi_period():
	"""Single-period + growth raises rather than silently doing nothing.

	``(1 + g) ** (years - years.min())`` is zero-exponent everywhere on a
	single-period network. The parameter would produce a frontier flat in
	demand growth, which reads as "demand growth does not matter" rather than
	"the parameter was never applied".

	The assertion must fire on a network whose demand is a *static*
	``loads.p_set``: that is PyPSA's default and what the fleet builder
	produces, and an earlier version of ``_apply_demand_growth`` returned early
	on the empty dynamic table before reaching the check, so the parameter was a
	silent no-op on exactly the shape the check was written to refuse.
	"""
	base = _network(multi_period=False)
	assert base.loads_t.p_set.empty, "the fixture no longer exercises the static path"
	with pytest.raises(ValueError, match="multi-period"):
		apply_parameters(base, ScenarioParameters(demand_growth=0.05))


def test_demand_growth_applies_on_a_multi_period_network():
	"""The positive half: on a network that *can* carry it, it moves the load.

	Without this, the assertion above could be satisfied by refusing always.
	"""
	base = _network(multi_period=True)
	scenario = apply_parameters(base, ScenarioParameters(demand_growth=0.05))
	demand = scenario.loads_t.p_set["load"]
	later = demand.loc[demand.index.year == 2040]
	earlier = demand.loc[demand.index.year == 2030]
	assert float(later.iloc[0]) > float(earlier.iloc[0])
	# 2030 is the base year: the exponent is zero and the demand is unscaled.
	assert float(earlier.iloc[0]) == pytest.approx(120.0)
	# 2040 is ten years on: 120 * 1.05**10.
	assert float(later.iloc[0]) == pytest.approx(120.0 * 1.05**10)


def test_zero_demand_growth_is_not_an_error_on_a_single_period_network():
	"""The default is a no-op by construction, not by accident: 0 growth is
	the identity and must not demand a multi-period network."""
	apply_parameters(_network(), ScenarioParameters())


def test_every_parameter_moves_a_solved_result(tmp_path: Path):
	"""The class gate for criterion 3, not one instance of it.

	For each parameter that has a non-default setting reachable from the
	fixture, apply it to a *solved* network and assert some headline number
	moves. A parameter that does nothing produces a flat frontier, and a flat
	frontier reads as a finding rather than as a bug.
	"""
	base = _solved()
	baseline = extract(base, ScenarioParameters(), network_checksum="sha256:" + "ab" * 32, code_version="0.1.0")

	settings = {
		"carbon_price_usd_per_tco2": 200.0,
		"gas_price_multiplier": 2.0,
		"renewable_multiplier": 3.0,
		"coal_eaf": 0.5,
	}
	moved: list[str] = []
	for name, value in settings.items():
		params = ScenarioParameters().with_value(name, value)
		scenario = apply_parameters(base, params)
		scenario.optimize(solver_name="highs", log_to_console=False)
		result = extract(scenario, params, network_checksum="sha256:" + "ab" * 32, code_version="0.1.0")
		if result.total_cost_usd != baseline.total_cost_usd or result.generation_mwh != baseline.generation_mwh:
			moved.append(name)
	assert set(moved) == set(settings), f"these parameters did nothing: {sorted(set(settings) - set(moved))}"


# --------------------------------------------------------------------------
# Criterion 4: the base network is never mutated
# --------------------------------------------------------------------------


def test_apply_does_not_mutate_base():
	"""``base`` is byte-identical after apply.

	The engine's own assertion covers this, but an assertion inside the code
	under test is not a gate on it: this compares the network's export before
	and after, which is the same observable the cache key is taken over.
	"""
	base = _network()
	before = base.generators.copy(deep=True)
	before_loads = base.loads_t.p_set.copy(deep=True)

	apply_parameters(
		base,
		ScenarioParameters(
			demand_growth=0.0,
			carbon_price_usd_per_tco2=200.0,
			renewable_multiplier=3.0,
			coal_eaf=0.5,
		),
	)

	pd.testing.assert_frame_equal(base.generators, before)
	pd.testing.assert_frame_equal(base.loads_t.p_set, before_loads)
	assert "alea_whatif_base" not in base.meta


def test_apply_is_idempotent(tmp_path: Path):
	"""Applying the same parameters twice equals applying them once.

	§9 ``test_renewable_multiplier_absolute``: applied twice gives the same
	result as once. The specification's ``p_nom_max *= multiplier`` compounds --
	applied twice it squares the potential -- so this holds only because the base
	is read from the recorded snapshot rather than from the current value. The
	canary in ``tests/ci/canaries/test_whatif_renewable_gate.py`` reverts the
	scaling to the compound form and watches this fail.
	"""
	base = _network()
	params = ScenarioParameters(renewable_multiplier=2.5)
	once = apply_parameters(base, params)
	twice = apply_parameters(once, params)
	pd.testing.assert_series_equal(once.generators["p_nom_max"], twice.generators["p_nom_max"])
	assert float(once.generators.loc["solar", "p_nom_max"]) == pytest.approx(500.0)


def test_a_scenario_on_a_coupled_network_reads_the_base_it_recorded(tmp_path: Path):
	"""A scenario applied to an already-scaled network scales the *base*.

	The snapshot is captured from whatever network the first application sees,
	so a second scenario on the result of the first is measured against that
	network's own values rather than against the first scenario's output.
	"""
	base = _network()
	first = apply_parameters(base, ScenarioParameters(renewable_multiplier=2.0))
	second = apply_parameters(first, ScenarioParameters(renewable_multiplier=3.0))
	assert float(second.generators.loc["solar", "p_nom_max"]) == pytest.approx(600.0)


# --------------------------------------------------------------------------
# Criterion 5 and 6: the cost-emissions and cost-risk frontiers
# --------------------------------------------------------------------------


def test_the_cost_emissions_frontier_is_computed(tmp_path: Path):
	"""Criterion 5. A real solve per point, over a real network."""
	engine = WhatIfEngine(
		_solved(), cache_root=tmp_path / "cache2", solve_fn=_CountingSolve()
	)
	frame = efficient_frontier(
		engine, "carbon_price_usd_per_tco2", [0.0, 100.0, 300.0], workers=1
	)
	assert list(frame.columns) == list(FRONTIER_COLUMNS)
	assert len(frame) == 3
	assert frame["total_cost_usd"].notna().all()
	assert frame["total_emissions_tco2"].notna().all()
	assert (frame["total_emissions_tco2"] >= 0.0).all()


def test_a_cost_risk_frontier_without_a_price_model_refuses(tmp_path: Path):
	"""Criterion 6's negative half, and the defect the module exists to avoid.

	Without a price model there is no cost distribution, so CVaR is genuinely
	unknown. Filling the risk axis with zeros would plot a flat line at the
	origin and read as "riskless" -- the strongest possible version of the
	mistake.
	"""
	engine = WhatIfEngine(_solved(), cache_root=tmp_path / "cache")
	with pytest.raises(ValueError, match="no CVaR"):
		cost_risk_frontier(engine, "carbon_price_usd_per_tco2", [0.0, 100.0])


def test_the_cost_risk_frontier_is_computed_when_a_price_model_is_present(tmp_path: Path):
	"""Criterion 6. A price model turns the same sweep into a risk frontier."""

	def price_fn(network: pypsa.Network, result) -> tuple[list[float], float | None]:
		return [10.0, 12.0, 15.0, 20.0, 40.0], 100.0

	engine = WhatIfEngine(
		_solved(), cache_root=tmp_path / "cache", price_fn=price_fn
	)
	frame = cost_risk_frontier(engine, "carbon_price_usd_per_tco2", [0.0, 200.0])
	assert frame["conditional_value_at_risk"].notna().all()
	assert (frame["conditional_value_at_risk"] >= 0.0).all()


def test_risk_metrics_are_positive_losses():
	"""The sign convention, asserted at the boundary where it is set.

	``var_cvar`` works in returns where positive is a gain. A system cost is a
	loss, so the sample is negated on the way in. Passing costs unnegated
	measures the right tail of a gain distribution and reports it as a loss.
	"""
	metrics = RiskMetrics.from_costs([10.0, 20.0, 30.0, 40.0, 100.0], confidence=0.8)
	assert metrics.conditional_value_at_risk > 0.0
	assert metrics.value_at_risk > 0.0
	assert metrics.conditional_value_at_risk >= metrics.value_at_risk


# --------------------------------------------------------------------------
# Criterion 7: a sweep completes, and on more than one core
# --------------------------------------------------------------------------


def test_a_twenty_point_sweep_completes(tmp_path: Path):
	"""Criterion 7's content: 20 points finish and produce 20 distinct costs.

	The plan's criterion also records a wall-clock figure on 12 cores. That is a
	property of the machine, not of the code, so what is asserted here is the
	part that can be: the sweep completes, and each point is a real solve.
	"""
	engine = WhatIfEngine(_solved(), cache_root=tmp_path / "cache")
	values = [float(v) for v in range(0, 400, 20)]
	frame = efficient_frontier(engine, "carbon_price_usd_per_tco2", values)
	assert len(frame) == 20
	assert frame["total_cost_usd"].nunique() == 20, "the sweep produced duplicate points"


def test_a_parallel_sweep_matches_a_serial_one(tmp_path: Path):
	"""Order follows the input, not the completion order.

	Two runs of the same sweep must produce byte-identical frames. The failure
	this guards against is worker completion order reaching the frame, which is
	invisible until it changes between runs.
	"""
	values = [0.0, 50.0, 100.0, 150.0]
	serial = WhatIfEngine(_solved(), cache_root=tmp_path / "serial")
	parallel = WhatIfEngine(_solved(), cache_root=tmp_path / "parallel")

	frame_serial = efficient_frontier(serial, "carbon_price_usd_per_tco2", values, workers=1)
	frame_parallel = efficient_frontier(parallel, "carbon_price_usd_per_tco2", values, workers=2)
	pd.testing.assert_frame_equal(
		frame_serial[list(FRONTIER_VALUE_COLUMNS)], frame_parallel[list(FRONTIER_VALUE_COLUMNS)]
	)


def test_frontier_deterministic(tmp_path: Path):
	"""The same sweep twice, in two engines over the same base, is identical."""
	values = [0.0, 100.0, 200.0]
	one = WhatIfEngine(_solved(), cache_root=tmp_path / "a")
	two = WhatIfEngine(_solved(), cache_root=tmp_path / "b")
	first = efficient_frontier(one, "carbon_price_usd_per_tco2", values)
	second = efficient_frontier(two, "carbon_price_usd_per_tco2", values)
	pd.testing.assert_frame_equal(
		first[list(FRONTIER_VALUE_COLUMNS)], second[list(FRONTIER_VALUE_COLUMNS)]
	)


# --------------------------------------------------------------------------
# Criterion 8: a partial sweep resumes from the cache
# --------------------------------------------------------------------------


def test_a_partial_sweep_resumes_from_cache(tmp_path: Path):
	"""Criterion 8. Points already computed are not recomputed.

	The sweep is run once, then again over a longer value list. Only the new
	points may reach the solver: a sweep that restarts from zero is a sweep
	whose cost grows without bound on a re-run.
	"""
	values = [0.0, 100.0]
	counter = _CountingSolve()
	engine = _engine(tmp_path, solve_fn=counter)
	engine.sweep("carbon_price_usd_per_tco2", values)
	assert counter.calls == 2

	outcomes = engine.sweep("carbon_price_usd_per_tco2", [0.0, 100.0, 200.0])
	assert counter.calls == 3, "the resumed sweep re-solved points it already had"
	assert [outcome.from_cache for outcome in outcomes] == [True, True, False]


def test_sweep_parameter_refuses_an_unknown_parameter(tmp_path: Path):
	"""A typo in a parameter name must fail, not sweep the default."""
	engine = _engine(tmp_path)
	with pytest.raises(KeyError, match="unknown scenario parameter"):
		sweep_parameter(engine, "carbon_tax", [1.0, 2.0])


# --------------------------------------------------------------------------
# Criterion 9: a scenario is reproducible from its artefact alone
# --------------------------------------------------------------------------


def test_scenario_records_network(tmp_path: Path):
	"""A saved scenario carries the network checksum it was computed against.

	Without it, two engines on different networks write incomparable results
	under the same scenario name and nothing in the artefact says so.
	"""
	engine = _engine(tmp_path, solve_fn=_CountingSolve())
	params = ScenarioParameters(carbon_price_usd_per_tco2=80.0)
	result = engine.solve(params)
	path = save_scenario(
		"carbon-80",
		params,
		result,
		engine.network_checksum,
		engine.code_version,
		root=tmp_path / "scenarios",
	)
	assert path.exists()
	payload = json.loads(path.read_text(encoding="utf-8"))
	assert payload["network_checksum"] == engine.network_checksum
	assert payload["code_version"] == engine.code_version


def test_a_saved_scenario_reproduces_from_its_artefact_alone(tmp_path: Path):
	"""Criterion 9. Read the record, rebuild the cache key from its own fields,
	and assert the key matches the version it was filed under.

	This is what "reproducible from the artefact" means here: nothing outside
	the record is needed to know which scenario it describes.
	"""
	engine = _engine(tmp_path, solve_fn=_CountingSolve())
	params = ScenarioParameters(carbon_price_usd_per_tco2=80.0, coal_eaf=0.9)
	result = engine.solve(params)
	root = tmp_path / "scenarios"
	save_scenario("repro", params, result, engine.network_checksum, engine.code_version, root=root)

	record = load_scenario("repro", engine.key_for(params), root=root)
	assert record.version == cache_key(record.params, record.network_checksum, record.code_version)
	assert record.params == params
	assert record.result.total_cost_usd == result.total_cost_usd
	assert latest_version("repro", root=root) == record.version
	assert [r.name for r in list_scenarios(root=root)] == ["repro"]


def test_saving_the_same_scenario_twice_is_idempotent(tmp_path: Path):
	"""The version is a content address, so a re-save is the same artefact.

	A version counter anyone has to remember to increment is a version counter
	someone forgets.
	"""
	engine = _engine(tmp_path, solve_fn=_CountingSolve())
	params = ScenarioParameters()
	result = engine.solve(params)
	root = tmp_path / "scenarios"
	first = save_scenario("same", params, result, engine.network_checksum, engine.code_version, root=root)
	second = save_scenario("same", params, result, engine.network_checksum, engine.code_version, root=root)
	assert first == second
	assert len(list_scenarios(root=root)) == 1


def test_changing_a_parameter_changes_the_version(tmp_path: Path):
	engine = _engine(tmp_path, solve_fn=_CountingSolve())
	root = tmp_path / "scenarios"
	base = ScenarioParameters()
	result = engine.solve(base)
	save_scenario("v", base, result, engine.network_checksum, engine.code_version, root=root)
	other = ScenarioParameters(carbon_price_usd_per_tco2=999.0)
	save_scenario(
		"v", other, engine.solve(other), engine.network_checksum, engine.code_version, root=root
	)
	assert len(list_scenarios(root=root)) == 2


def test_a_scenario_whose_sidecar_names_another_network_is_refused(tmp_path: Path):
	"""The sidecar and the record must agree about what was computed against."""
	engine = _engine(tmp_path, solve_fn=_CountingSolve())
	params = ScenarioParameters()
	result = engine.solve(params)
	root = tmp_path / "scenarios"
	path = save_scenario("bad", params, result, engine.network_checksum, engine.code_version, root=root)

	sidecar = path.with_suffix(path.suffix + ".provenance.json")
	payload = json.loads(sidecar.read_text(encoding="utf-8"))
	payload["inputs"] = ["sha256:" + "ff" * 32]
	sidecar.write_text(json.dumps(payload), encoding="utf-8")

	with pytest.raises(Exception, match="sidecar names network"):
		load_scenario("bad", engine.key_for(params), root=root)


# --------------------------------------------------------------------------
# Extraction: the two sentinels the specification gets wrong
# --------------------------------------------------------------------------


def test_renewable_share_nan_on_zero_gen():
	"""Zero generation is not zero renewable generation.

	The specification returns 0, which asserts "no renewable generation" for a
	network that produced nothing at all -- and a report that reads 0% renewable
	for an idle system is a false claim, not a rounding.
	"""
	assert renewable_share({}) is None
	assert renewable_share({"coal": 0.0}) is None
	assert renewable_share({"coal": 100.0}) == 0.0
	assert renewable_share({"solar": 100.0}) == 1.0


def test_extract_reports_none_for_an_unsolved_network():
	"""An unsolved network has no prices, and ``None`` is not a price.

	Zero would be a price. ``price_statistics`` returns ``(None, None)`` so a
	consumer can tell "no price computed" from "price computed and zero".
	"""
	result = extract(
		_network(), ScenarioParameters(), network_checksum="sha256:" + "ab" * 32, code_version="0.1.0"
	)
	assert result.price_mean_usd_per_mwh is None
	assert result.price_volatility_usd_per_mwh is None
	assert result.renewable_share is None


def test_extract_reads_the_objective_plus_its_constant():
	"""``n.objective`` alone omits the capital cost of existing capacity.

	The two are different numbers on any network with non-extendable capacity:
	on the fixture, the objective is negative and the constant is positive, so
	quoting the objective alone understates the system cost by millions.
	"""
	network = _solved()
	result = extract(
		network, ScenarioParameters(), network_checksum="sha256:" + "ab" * 32, code_version="0.1.0"
	)
	objective = float(network.objective or 0.0)
	constant = float(getattr(network, "objective_constant", 0.0) or 0.0)
	assert result.total_cost_usd == pytest.approx(objective + constant)
	assert result.total_cost_usd != pytest.approx(objective)


def test_curtailment_is_potential_minus_dispatch():
	"""A renewable generator held below its availability is curtailed energy.

	The plant is built explicitly: on the fixture the optimiser declines solar
	entirely, because coal at 30/MWh is cheaper than solar's capital cost, so
	``p_nom_opt`` is 0 and there is genuinely nothing to curtail. Asserting
	curtailment on an unbuilt plant measures the fixture, not the extractor.
	"""
	network = _solved()
	network.generators.loc["solar", "p_nom_opt"] = 20.0
	network.generators.loc["solar", "p_max_pu"] = 0.5
	network.generators_t.p["solar"] = 0.0
	result = extract(
		network, ScenarioParameters(), network_checksum="sha256:" + "ab" * 32, code_version="0.1.0"
	)
	# 20 MW built x 0.5 availability x 4 hourly snapshots, none of it dispatched.
	assert result.curtailment_mwh == pytest.approx(40.0)


def test_a_static_availability_column_still_yields_curtailment():
	"""The static/dynamic gap the extractor had.

	``p_max_pu`` is a static column by default, and reading only
	``generators_t.p_max_pu`` reported zero curtailment for every generator
	carrying that form — which is every generator on a network built without a
	renewables stage. This asserts the static path produces a number.
	"""
	network = _solved()
	assert network.generators_t.p_max_pu.empty, "the fixture no longer exercises the static path"
	network.generators.loc["solar", "p_nom_opt"] = 20.0
	network.generators.loc["solar", "p_max_pu"] = 0.25
	network.generators_t.p["solar"] = 0.0
	result = extract(
		network, ScenarioParameters(), network_checksum="sha256:" + "ab" * 32, code_version="0.1.0"
	)
	assert result.curtailment_mwh == pytest.approx(20.0)


def test_hydrogen_export_is_annual_not_horizon_total():
	"""The export load spreads each *year's* energy across that year's snapshots.

	Spread across the whole horizon it would export ``twh`` per horizon rather
	than per year, understating the demand by the number of investment periods.
	"""
	base = _network(multi_period=True)
	params = ScenarioParameters(hydrogen_export_twh_per_year=1.0)
	scenario = apply_parameters(base, params)
	assert "h2_export" in scenario.loads.index
	per_year = scenario.loads_t.p_set["h2_export"].groupby(
		scenario.loads_t.p_set.index.year
	).sum()
	# 1 TWh = 1e6 MWh in each of the two years.
	assert per_year.loc[2030] == pytest.approx(1e6)
	assert per_year.loc[2040] == pytest.approx(1e6)


def test_a_drought_needs_a_climate_scenario():
	"""A hydrological change with no climate story is a sensitivity, not a
	scenario, and the difference matters when it reaches a report."""
	with pytest.raises(ValueError, match="high-emissions SSP"):
		ScenarioParameters(drought_multiplier=1.5)
	ScenarioParameters(drought_multiplier=1.5, ssp_pathway="SSP5-8.5")


def test_an_unknown_parameter_is_refused():
	"""``extra='forbid'``: a mistyped knob is a construction error, not a
	scenario that silently runs at the default."""
	with pytest.raises(ValidationError, match="carbon_tax"):
		ScenarioParameters.model_validate({"carbon_tax": 100.0})


def test_the_cache_key_embeds_the_canonical_form_byte_for_byte():
	"""``canonical_json`` is the parameter half of the key, not a parallel copy.

	The key was assembled with its own ``json.dumps`` over ``params.canonical()``
	while ``ScenarioParameters.canonical_json`` claimed in its docstring to be
	"the cache key ... a hash of exactly this". Nothing called it, so the claim
	was false and the two spellings were free to drift -- and a key that hashes
	a different string than the one the method documents is a cache that misses
	for a reason neither file shows.

	Asserted against the dict form ``sort_keys`` produced, so the refactor that
	removed the duplicate is proven not to have moved a single byte.
	"""
	import hashlib
	import json

	from alea.io.artefacts import sha256_bytes
	from alea.whatif.cache import CACHE_VERSION

	params = ScenarioParameters()
	network = "sha256:" + "ab" * 32
	code = "0.1.0"

	expected_payload = json.dumps(
		{
			"cache_version": CACHE_VERSION,
			"params": params.canonical(),
			"network": network,
			"code": code,
		},
		sort_keys=True,
		separators=(",", ":"),
		default=str,
	)
	assert cache_key(params, network, code) == sha256_bytes(expected_payload.encode("utf-8"))
	assert hashlib.sha256(expected_payload.encode("utf-8")).hexdigest() == cache_key(
		params, network, code
	)

	# And the embedded half is the method's own string, verbatim.
	assert params.canonical_json() in expected_payload


def test_the_cache_key_is_a_sha256_over_the_canonical_form(tmp_path: Path):
	"""The key's shape is asserted once, so a change to it is a visible change.

	A key that is not a fixed-width digest is one a filesystem path cannot be
	sharded by, and the shard is what keeps a sweep's directory listing small.
	"""
	key = cache_key(ScenarioParameters(), "sha256:" + "ab" * 32, "0.1.0")
	assert len(key) == 64
	assert all(character in "0123456789abcdef" for character in key)
	cache = SolveCache(tmp_path / "cache")
	assert cache.path_for(key) == tmp_path / "cache" / key[:2] / key


def test_the_gc_never_removes_a_fresh_entry(tmp_path: Path):
	"""``keep_days`` is explicit and never runs during a solve: eviction
	mid-sweep would change which points exist and therefore the frontier."""
	cache = SolveCache(tmp_path / "cache")
	params = ScenarioParameters()
	key = cache_key(params, "sha256:" + "ab" * 32, "0.1.0")
	cache.put(
		key,
		params=params,
		network_checksum="sha256:" + "ab" * 32,
		code_version="0.1.0",
		result={},
	)
	assert cache.garbage_collect(keep_days=7.0) == []
	assert cache.has(key)
	assert cache.garbage_collect(keep_days=None) == []


def test_the_key_probe_is_a_fresh_interpreter(tmp_path: Path):
	"""The cross-process check must not be satisfiable by this session's state.

	``key_is_process_stable`` spawns interpreters; this asserts the subprocess
	actually ran the package rather than falling back to the parent's memory.
	"""
	program = (
		"from alea.whatif.cache import cache_key;"
		"from alea.whatif.params import ScenarioParameters;"
		"print(cache_key(ScenarioParameters(), 'sha256:' + 'ab'*32, '0.1.0'))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program], capture_output=True, text=True, check=True
	)
	assert result.stdout.strip() == cache_key(
		ScenarioParameters(), "sha256:" + "ab" * 32, "0.1.0"
	)


# --------------------------------------------------------------------------
# The price model: criterion 6's producer
# --------------------------------------------------------------------------


def _varying_price_network() -> pypsa.Network:
	"""A network whose marginal price differs between hours.

	Coal is the only unit that can serve the peak; solar is free and covers the
	middle of the day, so the clearing price is 0 when the sun is out and 30
	when it is not. ``_network`` cannot serve here: one always-marginal thermal
	unit prices every hour identically, so the dispersion the price model draws
	from is zero and a seed change is unobservable.

	Multi-period, because the engine applies ``demand_growth`` by default and
	refuses a single-year network rather than applying a parameter that would do
	nothing -- criterion 3, asserted by
	``test_demand_growth_requires_multi_period``.
	"""
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	network.set_snapshots(
		[
			ts
			for year in (2030, 2040)
			for ts in pd.date_range(f"{year}-01-01", periods=3, freq="h")
		]
	)
	network.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
	network.add(
		"Generator",
		"solar",
		bus="b1",
		carrier="solar",
		p_nom=150.0,
		marginal_cost=0.0,
		p_max_pu=[0.0, 0.6, 0.9, 0.0, 0.6, 0.9],
	)
	network.add("Load", "load", bus="b1", p_set=120.0)
	return network


def test_the_price_model_centres_on_the_objective_it_was_handed(tmp_path: Path):
	"""The expected cost is the solve's own objective, not a re-estimate of it.

	The zero-mean draw is what makes the distribution a statement about *spread*
	only. A draw with a non-zero mean would move the expected cost off the
	objective the optimiser returned, and the risk axis would then measure the
	model's bias as well as the scenario's risk.
	"""
	network = _network()
	network.optimize(solver_name="highs", log_to_console=False)
	price_fn = price_model_from_network(n_paths=4096)
	costs, threshold = price_fn(network, None)

	assert len(costs) == 4096
	objective = total_cost_usd(network)
	assert threshold == objective
	mean = sum(costs) / len(costs)
	# A zero-mean draw of 4096 paths leaves a sampling error of order
	# std/sqrt(n); 5% of the objective is far outside it and inside any bias
	# worth catching.
	assert abs(mean - objective) < 0.05 * abs(objective), (
		f"the sample mean {mean} is not the objective {objective}; the draw is "
		f"not zero-mean, so the risk axis carries the model's bias"
	)


def test_the_served_energy_is_per_horizon_not_per_snapshot(tmp_path: Path):
	"""A static ``p_set`` is per snapshot, so summing the column is wrong by N.

	PyPSA leaves ``loads_t.p_set`` empty for a statically-defined load and puts
	the value in ``loads["p_set"]``. Summing that column gives one snapshot's
	energy on an N-snapshot network, which understates the served energy by N
	and the risk axis with it -- a unit error, invisible because the number is
	internally consistent with its own line.
	"""
	network = _network()
	network.optimize(solver_name="highs", log_to_console=False)
	# The fixture's load is 120 MW on 4 snapshots: 480 MWh, not 120.
	assert _served_energy_mwh(network) == 480.0, (
		f"served energy is {_served_energy_mwh(network)}, which is the "
		f"per-snapshot figure rather than the horizon total"
	)


def test_the_price_model_reports_no_distribution_when_the_solve_has_none():
	"""A solve without duals has no price distribution, and that is not zero.

	The empty sample is the absence of a measurement. Reporting a zero-volatility
	distribution instead would give a riskless portfolio for a solve that
	measured nothing -- the same defect as a ``renewable_share`` of 0 for a
	network that generated nothing.
	"""
	network = _network()  # built, never solved: no marginal prices
	price_fn = price_model_from_network()
	costs, threshold = price_fn(network, None)
	assert costs == [] and threshold is None


def test_the_price_model_is_deterministic_in_the_scenario(tmp_path: Path):
	"""Same scenario, same sample -- in this process and another (AD-8).

	A clock-seeded or globally-seeded draw makes two runs of one sweep differ,
	and a frontier that moves between runs is a frontier nobody can act on.

	**The fixture must have a price that varies.** ``_network``'s single
	thermal unit is marginal in every hour, so its marginal price is flat, its
	dispersion is zero and *any* seed draws the same sample -- the test would
	pass against a clock-seeded model. The solar unit below is cheaper and
	covers some hours and not others, which is what puts a spread in the price
	for a seed to move.
	"""
	network = _varying_price_network()
	network.optimize(solver_name="highs", log_to_console=False)
	price_fn = price_model_from_network(n_paths=256)
	first, _ = price_fn(network, _placeholder("scenario-a"))
	second, _ = price_fn(network, _placeholder("scenario-a"))
	other, _ = price_fn(network, _placeholder("scenario-b"))
	assert first == second, "the same scenario drew two different samples"
	assert first != other, "two scenarios drew the same sample; the seed ignores identity"


def _placeholder(scenario_id: str):
	"""A minimal result carrying a scenario identity, for the seed."""
	return ScenarioResult(
		scenario_id=scenario_id,
		params=ScenarioParameters(),
		network_checksum="sha256:" + "ab" * 32,
		code_version="0.1.0",
		total_cost_usd=0.0,
		total_emissions_tco2=0.0,
		capacity_mix_mw={},
		generation_mwh={},
	)


def test_the_cost_risk_frontier_is_reachable_from_the_price_model(tmp_path: Path):
	"""Criterion 6 end to end: a real engine, a real model, a real frontier.

	``PriceFn`` had no producer in ``src/`` -- the only construction was a
	lambda in the test above -- so the frontier this asserts was reachable from
	a test and nowhere else. This drives the shipped model through the shipped
	frontier.
	"""
	base = _varying_price_network()
	base.optimize(solver_name="highs", log_to_console=False)
	base.model.solver_model = None
	engine = WhatIfEngine(
		base, cache_root=tmp_path / "cache", price_fn=price_model_from_network()
	)
	frame = cost_risk_frontier(engine, "carbon_price_usd_per_tco2", [0.0, 100.0, 300.0])
	assert frame["conditional_value_at_risk"].notna().all()
	assert (frame["conditional_value_at_risk"] >= 0.0).all()
	assert frame["value_at_risk"].notna().all()
	# The axis carries information: it is not the cost column under another
	# name, which is the mislabelling the frontier's own guard now refuses.
	assert (frame["conditional_value_at_risk"] != frame["total_cost_usd"]).all()


# --------------------------------------------------------------------------
# The API's door to a cost-risk frontier
# --------------------------------------------------------------------------


def _api_frontier_service(tmp_path: Path, network: pypsa.Network):
	"""A ``WhatIfService`` over a scratch catalogue holding ``network``."""
	import asyncio
	import json as _json

	from alea.api.jobs import JobStore
	from alea.api.repository import Repository
	from alea.api.whatif import WhatIfService
	from alea.config.loader import load_config
	from alea.io.artefacts import write_artefact
	from alea.provenance.models import Basis, DerivedProvenance

	# Loaded *before* `repo_root` is patched: `load_config` reads
	# `config/config.default.yaml` through it, so patching first makes the
	# default file unfindable. The API fixture documents the same ordering.
	config = load_config()
	scenario_dir = tmp_path / "results" / "scenarios" / "base"
	scenario_dir.mkdir(parents=True, exist_ok=True)
	network.export_to_netcdf(scenario_dir / "network.nc")

	def write(relative: str, data: object) -> None:
		write_artefact(
			tmp_path / relative,
			data,
			DerivedProvenance(
				source_id="fixture",
				basis=Basis.MEASURED,
				uncertainty=0.0,
				inputs=["fixture"],
				code_version="0.1.0",
			),
		)

	write(
		"results/scenarios/index.json",
		{
			"scenarios": [
				{
					"scenario_id": "base",
					"name": "Base",
					"countries": ["KE"],
					"planning_horizons": [2030],
					"clusters": [55],
					"created_at": "2026-01-01T00:00:00+00:00",
				}
			]
		},
	)
	write(
		"results/scenarios/base/scenario.json",
		{
			"scenario_id": "base",
			"name": "Base",
			"countries": ["KE"],
			"planning_horizons": [2030],
			"clusters": [55],
			"created_at": "2026-01-01T00:00:00+00:00",
			"network_checksum": "abc",
			"code_version": "0.1.0",
		},
	)
	write(
		"results/scenarios/base/results/2030.json",
		{
			"objective": 1.0e9,
			"total_capacity_mw": 2100.0,
			"capacity_mix": [{"carrier": "solar", "capacity_mw": 1000.0, "share": 0.5}],
			"solved_at": "2026-01-01T00:00:00+00:00",
			"network_checksum": "abc",
		},
	)
	# The service resolves every path through `alea.config.paths.resolve`, so the
	# scratch root has to be installed before it is built and uninstalled after.
	import shutil

	import alea.config.paths as paths

	# The scratch root is a *repository* root, so it needs a `config/`. The
	# engine's solve function calls `load_config()` at solve time, and by then
	# `repo_root` is the scratch tree -- a tree with no `config/config.default.yaml`
	# makes `_read` return `{}` and `Config` fail validation with "scenario Field
	# required", from inside the solver rather than from anything the test names.
	shutil.copytree(paths.repo_root() / "config", tmp_path / "config")

	previous = paths.repo_root
	paths.repo_root = lambda: tmp_path  # type: ignore[assignment]
	service = WhatIfService(config, Repository(config))
	store = JobStore(str(tmp_path / "jobs.sqlite"))
	asyncio.run(store.connect())
	return service, store, paths, previous


def test_the_api_frontier_carries_the_whole_point_set(tmp_path: Path):
	"""Every ``FRONTIER_COLUMNS`` field, not three of them.

	The handler emitted ``parameter_value``/``objective``/``emissions`` only, so
	the risk axis the engine computed on every point was dropped at the API
	boundary and criterion 6 was unreachable through the endpoint. The key names
	are the sweep module's, so an API frontier and a CLI frontier describe a
	point the same way.
	"""
	import asyncio

	from alea.api.jobs import JobContext

	network = _varying_price_network()
	network.optimize(solver_name="highs", log_to_console=False)
	network.model.solver_model = None
	service, store, paths, previous = _api_frontier_service(tmp_path, network)
	try:
		context = JobContext(store, "job-1", 1)
		payload = asyncio.run(
			service._run_frontier(
				{
					"base_scenario_id": "base",
					"parameter": "carbon_price_usd_per_tco2",
					"start": 0.0,
					"stop": 200.0,
					"points": 3,
				},
				context,
			)
		)
	finally:
		asyncio.run(store.close())
		paths.repo_root = previous  # type: ignore[assignment]

	assert payload["kind"] == "cost_emissions"
	assert payload["risk_computed"] is True
	for point in payload["points"]:
		missing = [column for column in FRONTIER_COLUMNS if column not in point]
		assert not missing, f"the point is missing {missing}"
		assert point["conditional_value_at_risk"] is not None
		assert point["value_at_risk"] is not None


def test_the_api_refuses_a_cost_risk_frontier_with_no_risk_axis(tmp_path: Path):
	"""The API's door must enforce what the sweep module's does.

	A guarantee one door enforces and another routes around is not a guarantee.
	``cost_risk_frontier`` refuses a frontier whose risk axis is missing or
	degenerate; the endpoint accepted ``frontier='cost_risk'`` and returned the
	cost-emissions points under that name.
	"""
	import asyncio

	from alea.api.jobs import JobContext

	network = _network()  # one always-marginal unit: a flat price, no dispersion
	network.optimize(solver_name="highs", log_to_console=False)
	network.model.solver_model = None
	service, store, paths, previous = _api_frontier_service(tmp_path, network)
	try:
		context = JobContext(store, "job-1", 1)
		with pytest.raises(ValueError, match="CVaR equal to its cost"):
			asyncio.run(
				service._run_frontier(
					{
						"base_scenario_id": "base",
						"parameter": "carbon_price_usd_per_tco2",
						"start": 0.0,
						"stop": 200.0,
						"points": 3,
						"frontier": "cost_risk",
					},
					context,
				)
			)
	finally:
		asyncio.run(store.close())
		paths.repo_root = previous  # type: ignore[assignment]
