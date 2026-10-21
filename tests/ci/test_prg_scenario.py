# SPDX-License-Identifier: MIT
"""The graph driving a real solve: `WhatIfEngine.solve_from_prg`.

WHAT THESE TESTS ARE FOR. `alea.prg.translate` was written, tested, and reachable
from nothing but its own test file. Its register -- "three of fifty-three
settable parameters reach a what-if knob" -- therefore described a route no
production caller walked, and the graph could not drive a solve at all. This
module is the gate for the route that closes that: a scenario stated in the
*graph's* names, translated onto the engine's knobs, solved, and audited against
the graph's own identities.

WHY THE SOLVES ARE REAL. A test that stubbed the solver would assert that the
translation produced the right ``ScenarioParameters`` object, which the
translation's own tests already do. What is new here is that the parameters reach
a network and change its answer, so the solves run HiGHS and the assertions read
the solved result. A stub would pass whether or not the engine ever applied what
it was handed.

WHY THE REFUSAL IS ASSERTED BEFORE THE SOLVE. The strict path's whole value is
that no solve happens for a parameter the engine cannot carry: a scenario whose
parameter is dropped solves, returns a plausible number, and answers a different
question. A test that only checked the ``ValueError`` would not notice a version
that solved first and raised after.
"""

from __future__ import annotations

import pandas as pd
import pypsa
import pytest

from alea.prg import load_graph
from alea.prg.graph import ParameterGraph
from alea.whatif.service import WhatIfEngine

# `demand_growth` is translated and carries a non-zero default, and the engine
# refuses to apply it on a single-period network -- its exponent is zero
# everywhere on one year. So the fixture is multi-period, as a real base is.
YEARS = (2030, 2040)

#: Firm capacity the graph's reserve margin admits. See `_network`.
FIRM_MW = 15_000.0

#: The carbon budget these tests state, in MtCO2 over the horizon.
#:
#: It is 300 rather than the 200 this module used until batch 33, because 200
#: stopped being feasible when `fit_capacity_bound` entered the bound set. That
#: inequality caps VRE at `fit_capacity_cap` (4,000 MW), so the least-emitting
#: dispatch the fleet can run still burns gas for every MW of load above 4,000:
#: 4,500 MW in 2030 and 8,582 MW in 2040, four snapshots each. The constraint's
#: own coefficient is 0.00438 Mt per MW per snapshot -- 0.4 tCO2/MWh, times
#: 8,760/8 to annualise, times `horizon_years` -- so the floor is
#: `4 x (4,500 + 8,582) x 0.00438 = 229.2` Mt. A 200 Mt budget asks the fleet to
#: emit less than its own cap allows it to, which is a correct refusal and not a
#: test of the route. 300 Mt sits above the floor and below the 369 Mt the fleet
#: emits unconstrained, so the budget still binds and the assertions still have
#: an effect to measure.
BUDGET_MTCO2 = 300.0


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph()


def _network(firm_mw: float = FIRM_MW) -> pypsa.Network:
	"""One bus, a gas unit and an extendable solar farm, at national scale.

	The gas unit is what the ratio translation needs: ``fuel_price_usd_per_mwh``
	is an absolute price the engine applies as a factor over the *base* gas cost,
	and a network with no gas unit has no base to divide by.

	**The capacities are the graph's own defaults, except for one.** The audit
	propagates the result's parameters through the graph, and the graph carries a
	feedback loop -- the capture-price loop, whose fixed point is the VRE share
	the build response justifies. That loop's root exists only for a fleet at
	national scale: at a few hundred MW the ``vre_share_definition`` equation has
	no root in its (0, 1) bracket, the loop raises, and the audit reports that it
	could not run. A fixture at test scale would therefore never exercise the
	audit at all -- it would exercise the failure path and look like coverage.

	**Why firm capacity is above the graph's default and everything else is not.**
	A PRG-driven solve runs under the graph's inequalities, and the reserve margin
	is one of them: ``firm + capacity_factor x VRE >= peak x (1 +
	reserve_margin_min)``. Demand grows at ``demand_growth``'s default 4% a year
	over the horizon, so the 2040 peak is ``8500 x 1.04^10`` = 12,582 MW and the
	requirement is 14,469 MW of firm-equivalent capacity. The graph's own
	``firm_capacity_mw`` default of 9,000 MW does not meet it -- a fleet of that
	size is one the graph rejects, which is a true statement about the graph's
	assumed system and not a test artefact. The fixture is therefore the smallest
	fleet the graph admits (15,000 MW, with 1,750 MW of firm-equivalent VRE),
	because a fixture the graph rejects would make every test here a test of the
	infeasibility path instead of the route.
	"""
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	snapshots = pd.DatetimeIndex(
		[
			ts
			for year in YEARS
			for ts in pd.date_range(f"{year}-01-01", periods=4, freq="h")
		]
	)
	network.set_snapshots(list(snapshots))
	network.add(
		"Generator", "gas", bus="b1", carrier="gas", p_nom=firm_mw, marginal_cost=40.0
	)
	network.add(
		"Generator",
		"solar",
		bus="b1",
		carrier="solar",
		p_nom=1000.0,
		p_nom_max=5000.0,
		p_nom_extendable=True,
		capital_cost=50_000.0,
	)
	network.add("Load", "load", bus="b1", p_set=8500.0)
	return network


def _engine(tmp_path, **kwargs) -> WhatIfEngine:
	return WhatIfEngine(_network(), cache_root=tmp_path / "cache", **kwargs)


# --------------------------------------------------------------------------
# The route exists, and the engine applies what the graph stated
# --------------------------------------------------------------------------


def test_the_graph_drives_a_solve_and_the_parameter_reaches_the_result(
	tmp_path, graph: ParameterGraph
) -> None:
	"""A carbon price set in the graph's name changes the solved objective.

	The assertion is on the *objective*, not on the parameter object: the
	translation's own tests already pin the object, and what this route adds is
	that the number reaches the optimiser. A carbon price raises every emitting
	carrier's marginal cost, so the objective must rise.

	WHY THIS ASSERTS ATTRIBUTES AND NOT ``isinstance(..., PrgSolve)``. The
	what-if canaries reload ``alea.whatif.service`` in-process to mutate a
	function and watch a gate fail, and a reload rebinds every class the module
	defines -- so a test module that captured ``PrgSolve`` at import time holds a
	*stale* class object and ``isinstance`` returns False for an instance built
	by the live module. That is an ordering dependence, not a defect in the
	route: it passed alone and failed in the full suite, which is the signature.
	The class identity is not what this test is about, and the attributes below
	are what ``PrgSolve`` promises; asserting the contract rather than the class
	object is both stronger and order-independent. The return *type* is still
	checked, through the live module rather than the import-time binding.
	"""
	engine = _engine(tmp_path)
	baseline = engine.solve_from_prg({}, graph=graph)
	priced = engine.solve_from_prg(
		{"carbon_price_usd_per_tco2": 200.0}, graph=graph, force=True
	)
	# Resolved at call time, so a reloaded `service` is the module this reads.
	import alea.whatif.service as live_service

	assert isinstance(priced, live_service.PrgSolve)
	assert priced.parameters.carbon_price_usd_per_tco2 == 200.0
	assert priced.result.total_cost_usd > baseline.result.total_cost_usd


def test_the_ratio_route_applies_an_absolute_fuel_price(
	tmp_path, graph: ParameterGraph
) -> None:
	"""``fuel_price_usd_per_mwh`` is absolute; the engine's knob is a factor.

	The translation needs the network, which is exactly why the route lives on
	the engine rather than in the translation module: there is no factor without
	the base the factor is over. The factor is asserted against the network's own
	base gas cost, which is 40 USD/MWh in the fixture.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"fuel_price_usd_per_mwh": 60.0}, graph=graph, force=True
	)
	assert solved.parameters.gas_price_multiplier == pytest.approx(60.0 / 40.0)


# --------------------------------------------------------------------------
# The refusal, and the register of what a loose run drops
# --------------------------------------------------------------------------


def test_a_parameter_the_engine_cannot_carry_is_refused_by_name(
	tmp_path, graph: ParameterGraph
) -> None:
	"""Strict is the default: the refusal names the parameter and no solve runs.

	``voll_usd_per_mwh`` is a settable graph parameter with no engine knob. The
	failure this guards against is the quiet one -- the graph accepts it, the
	engine never sees it, and the returned number looks like an answer.
	"""
	engine = _engine(tmp_path)
	with pytest.raises(ValueError, match="voll_usd_per_mwh"):
		engine.solve_from_prg({"voll_usd_per_mwh": 9000.0}, graph=graph)
	# The refusal happened *before* the solve: the engine's own solve counter is
	# the observable, and a version that solved and raised after would leave it
	# above zero.
	assert engine.solve_count == 0


def test_a_loose_run_drops_the_parameter_and_says_which(
	tmp_path, graph: ParameterGraph
) -> None:
	"""The drop is carried on the result, not logged and forgotten.

	A dropped parameter is the difference between an answer to the question asked
	and an answer to a question the engine could express, so it travels with the
	result and appears in the summary.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_price_usd_per_tco2": 80.0, "voll_usd_per_mwh": 9000.0},
		graph=graph,
		strict=False,
		force=True,
	)
	assert solved.parameters.carbon_price_usd_per_tco2 == 80.0
	assert solved.dropped == ("voll_usd_per_mwh",)
	assert "voll_usd_per_mwh" in solved.summary()


def test_a_fully_carried_scenario_drops_nothing(
	tmp_path, graph: ParameterGraph
) -> None:
	"""The register is empty when every parameter reached a knob.

	Without this the previous test would pass on an implementation that reported
	*every* parameter as dropped.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_price_usd_per_tco2": 80.0, "demand_growth": 0.05},
		graph=graph,
		force=True,
	)
	assert solved.dropped == ()


def test_a_typo_is_dropped_and_named_on_the_loose_path(
	tmp_path, graph: ParameterGraph
) -> None:
	"""A misspelt parameter is in the register, not silently carried.

	The register was filtered on ``untranslated()``, which enumerates the
	graph's *own* settable parameters -- so a name that is not in the graph
	appears in neither ``translated()`` nor ``untranslated()``, and the filter
	reported a typo as cleanly applied. The honest register is the complement of
	``translated()``: everything the caller set that reached no knob.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_price_usd_per_ton": 200.0, "carbon_price_usd_per_tco2": 80.0},
		graph=graph,
		strict=False,
		force=True,
	)
	assert solved.parameters.carbon_price_usd_per_tco2 == 80.0
	assert solved.dropped == ("carbon_price_usd_per_ton",)
	assert "carbon_price_usd_per_ton" in solved.summary()


# --------------------------------------------------------------------------
# The audit runs on the result the solve just produced
# --------------------------------------------------------------------------


def test_the_solved_result_is_audited_against_the_graph(
	tmp_path, graph: ParameterGraph
) -> None:
	"""The audit is on the payload, with the count of what it could not check.

	``audit.consistent`` alone would be a bill of health for a result the audit
	only partly examined, so the skipped count travels with it. A result the
	graph rejects must not read as consistent.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_price_usd_per_tco2": 50.0}, graph=graph, force=True
	)
	assert solved.audit.checked, "the audit checked nothing, so this is vacuous"
	# The summary states both sides: what was checked and what the result did not
	# carry. A summary naming only the first would read as a full pass.
	assert "not carried by the result" in solved.audit.summary()


def test_the_intensity_gap_is_measured_not_asserted(
	tmp_path, graph: ParameterGraph
) -> None:
	"""The engine's fleet intensity against the graph's single factor.

	The graph's emissions identity uses one fleet-wide factor and the engine sums
	per-carrier intensities, so the two agree only when the fleet's weighted
	average equals the graph's number. The useful output is the *size* of that
	gap, and it is carried on every solve.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_price_usd_per_tco2": 50.0}, graph=graph, force=True
	)
	gap = solved.intensity_gap
	assert set(gap) == {"engine_intensity", "graph_factor", "ratio"}
	assert gap["graph_factor"] > 0.0, "the graph declares no emission factor"
	assert gap["engine_intensity"] >= 0.0


# --------------------------------------------------------------------------
# Caching, which is Layer 5's whole reason to exist
# --------------------------------------------------------------------------


def test_the_same_scenario_twice_is_served_from_the_cache(
	tmp_path, graph: ParameterGraph
) -> None:
	"""A PRG-driven solve is cached like any other, and does not re-solve.

	The cache is keyed on the translated parameters, so the route inherits Layer
	5's reproducibility: a restart does not re-solve, and the second call reports
	that it was served rather than computed.
	"""
	engine = _engine(tmp_path)
	values = {"carbon_price_usd_per_tco2": 120.0}
	first = engine.solve_from_prg(values, graph=graph)
	second = engine.solve_from_prg(values, graph=graph)
	assert not first.outcome.from_cache
	assert second.outcome.from_cache
	assert engine.solve_count == 1
	assert second.result.total_cost_usd == first.result.total_cost_usd


# --------------------------------------------------------------------------
# The graph's inequalities reach the optimiser
# --------------------------------------------------------------------------


def test_a_constrained_solve_differs_from_an_unconstrained_one(
	tmp_path, graph: ParameterGraph
) -> None:
	"""The graph's inequalities bind, and the answer says it was solved under them.

	WHY THIS IS THE GATE FOR THE SECOND HALF OF PART X. ``constraints.py`` was in
	exactly the state ``translate.py`` was in: written, tested, and reached by no
	solve. ``constraint_function`` returns PyPSA's ``extra_functionality`` hook
	and nothing in ``src/`` called it, so the graph's two bindable inequalities
	-- the reserve margin and the carbon budget -- constrained no optimiser. The
	objective is the observable: an unconstrained solve and a constrained one of
	the same network are two different optimisations, and if they agree the
	constraint did not reach the model.
	"""
	engine = _engine(tmp_path)
	# The unconstrained side needs `strict=False`: with `constrain=False` the
	# budget is an ordinary parameter the engine has no knob for, and strict --
	# which is the default and is right -- refuses it. Asking for the plain solve
	# *of a scenario that states a budget* therefore means dropping the budget,
	# which is what `strict=False` says.
	constrained = engine.solve_from_prg({"carbon_budget_mtco2": BUDGET_MTCO2}, graph=graph, force=True)
	plain = engine.solve_from_prg(
		{"carbon_budget_mtco2": BUDGET_MTCO2}, graph=graph, constrain=False, strict=False, force=True
	)
	assert constrained.constrained
	assert not plain.constrained
	# The budget binds: the constrained solve must emit *less*. Asserting only
	# "the objective differs" would pass on a constraint that moved the answer
	# the wrong way, and asserting equality would pass on one that never reached
	# the model -- which is the defect this test exists for.
	assert constrained.result.total_emissions_tco2 < plain.result.total_emissions_tco2, (
		"the carbon budget constrained nothing: the constrained solve emitted no "
		"less than the unconstrained one"
	)
	assert plain.dropped == ("carbon_budget_mtco2",)


def test_the_constraint_terms_are_not_reported_as_dropped(
	tmp_path, graph: ParameterGraph
) -> None:
	"""A parameter that reaches the solve through a constraint reached something.

	``carbon_budget_mtco2`` and ``reserve_margin_min`` are settable graph
	parameters with no engine knob, so the ``dropped`` register -- built as the
	complement of ``translated()`` -- would name them. They are not dropped:
	the optimiser reads them when the constraint is added. Reporting them as
	dropped is the register's own defect inverted, calling a parameter
	unreached at the moment it reaches the solve.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg(
		{"carbon_budget_mtco2": BUDGET_MTCO2, "reserve_margin_min": 0.2}, graph=graph, force=True
	)
	assert "carbon_budget_mtco2" not in solved.dropped
	assert "reserve_margin_min" not in solved.dropped
	assert set(solved.constraint_terms) == {"carbon_budget_mtco2", "reserve_margin_min"}


def test_the_constraint_terms_are_refused_on_a_strict_translation_no_longer(
	tmp_path, graph: ParameterGraph
) -> None:
	"""Strict does not refuse a constraint term: it is carriable, by the graph.

	Before the constraints were wired, ``--set carbon_budget_mtco2=20`` under the
	default strict path raised, because the parameter reaches no engine knob.
	The refusal was correct about the knob and wrong about the parameter: the
	graph carries it into the solve.
	"""
	engine = _engine(tmp_path)
	solved = engine.solve_from_prg({"carbon_budget_mtco2": BUDGET_MTCO2}, graph=graph, force=True)
	assert solved.dropped == ()
	assert solved.constrained


def test_a_constrained_and_unconstrained_solve_do_not_share_a_cache_key(
	tmp_path, graph: ParameterGraph
) -> None:
	"""Two different optimisations of one network must not share one entry.

	The key covers the parameters, the network and the code version. A
	constrained solve adds a fourth component -- the graph inequalities it ran
	under -- because the answer differs and a key that omitted it would serve
	whichever ran first to the other. This is the network-checksum failure one
	level up: the number looks right and answers a different question.
	"""
	engine = _engine(tmp_path)
	values = {"carbon_budget_mtco2": BUDGET_MTCO2}
	constrained = engine.solve_from_prg(values, graph=graph, force=True)
	plain = engine.solve_from_prg(values, graph=graph, constrain=False, strict=False, force=True)
	assert constrained.outcome.cache_key != plain.outcome.cache_key

	# And a second constrained call is served from the cache, so the extra key
	# component does not defeat caching.
	again = engine.solve_from_prg(values, graph=graph)
	assert again.outcome.from_cache
	assert again.outcome.cache_key == constrained.outcome.cache_key


def test_an_infeasible_constrained_scenario_is_refused_not_cached(
	tmp_path, graph: ParameterGraph
) -> None:
	"""A fleet the graph's reserve margin rejects raises; no result is cached.

	WHY THIS IS REACHABLE NOW AND WAS NOT BEFORE. ``network.optimize`` returns
	``(status, condition)`` and does not raise on infeasibility, so an engine
	that ignored the status would read a zero objective out of a network the
	solver refused and cache it -- a cost no feasible dispatch produced, wearing
	a solved result's shape. That path was dead while nothing could make a
	what-if network infeasible. The reserve margin does exactly that, and it is
	the ordinary way a scenario fails: a fleet smaller than the graph's own
	requirement.
	"""
	from alea.whatif.service import SolveError

	engine = WhatIfEngine(_network(firm_mw=9_000.0), cache_root=tmp_path / "cache")
	with pytest.raises(SolveError, match="infeasible"):
		engine.solve_from_prg({}, graph=graph, force=True)
	# Nothing was written: a cached infeasible scenario would be served forever.
	assert engine.cache is not None
	assert engine.cache.keys() == []


# --------------------------------------------------------------------------
# The command, which is the only entry point an operator has
# --------------------------------------------------------------------------


def _cli(tmp_path, *args: str):
	"""Run `alea whatif scenario` against a network exported to disk.

	The command takes a *path*, so the fixture's network is written out rather
	than passed in memory. Run through the runner rather than by calling
	`whatif_scenario`, because what is asserted is that the command is mounted
	and exits with the code it claims -- a command defined but never added to a
	mounted typer is unreachable from the shell, which is the same defect as the
	translation layer having no caller.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	network = tmp_path / "base.nc"
	if not network.exists():
		_network().export_to_netcdf(str(network))
	return CliRunner().invoke(app, ["whatif", "scenario", "--network", str(network), *args])


def test_the_scenario_command_is_reachable(tmp_path) -> None:
	"""`alea whatif scenario` exists, which is how the route is reached at all."""
	result = _cli(tmp_path, "--help")
	assert result.exit_code == 0, result.output
	assert "--set" in result.stdout
	assert "--loose" in result.stdout
	assert "--no-constrain" in result.stdout


def test_the_command_gates_on_a_violation(tmp_path) -> None:
	"""A result the graph rejects exits non-zero, the way `prg check` does.

	A command that prints a violation and exits 0 is one a script cannot gate on,
	and the exit code is the only signal a caller has. The $200 carbon price is
	the scenario the audit refuses -- the tariff stops covering debt service --
	and it is a network HiGHS solves without complaint, which is exactly the case
	the seam exists to catch.
	"""
	result = _cli(tmp_path, "--set", "carbon_price_usd_per_tco2=200")
	assert result.exit_code == 1, result.output
	assert "solved: objective=" in result.stdout


def test_the_command_refuses_a_parameter_the_engine_cannot_carry(tmp_path) -> None:
	"""Strict is the default, and the refusal names the parameter.

	Exit 2, not 1: the two failures are different -- one is a scenario the graph
	rejects after solving, the other is a scenario that was never solved. A
	caller distinguishing them is distinguishing "the answer is bad" from "there
	is no answer".
	"""
	result = _cli(tmp_path, "--set", "voll_usd_per_mwh=9000")
	assert result.exit_code == 2, result.output
	assert "voll_usd_per_mwh" in result.output
	assert "solved:" not in result.stdout, "the refusal came after a solve"


def test_the_command_solves_under_the_graphs_inequalities(tmp_path) -> None:
	"""The budget reaches the optimiser through the command, not just the API.

	The flag defaults to constrained, so the operator gets the graph's
	inequalities without asking. `--no-constrain` is the escape, and the two runs
	of the same stated budget must differ -- if they agree, the constraint never
	reached the model through this door.
	"""
	constrained = _cli(tmp_path, "--set", f"carbon_budget_mtco2={BUDGET_MTCO2}")
	assert constrained.exit_code in (0, 1), constrained.output
	plain = _cli(tmp_path, "--set", f"carbon_budget_mtco2={BUDGET_MTCO2}", "--no-constrain", "--loose")
	assert plain.exit_code in (0, 1), plain.output
	assert constrained.stdout != plain.stdout, (
		"the constrained and unconstrained runs printed the same thing, so the "
		"graph's inequality reached nothing through the command"
	)


def test_the_command_prints_both_declared_versus_measured_gaps(tmp_path) -> None:
	"""The solve reports what the graph declares and what the fleet did.

	`intensity_gap` was computed and carried on `PrgSolve` and printed by
	nothing, and the reliability gap did not exist: `expected_unserved_fraction`
	was read by its own equation and by no reader. Both are the same defect --
	a measurement the graph makes available and no door shows -- so both lines
	are asserted at the command, which is the only entry point an operator has.
	"""
	result = _cli(tmp_path, "--set", "carbon_price_usd_per_tco2=60")
	assert result.exit_code in (0, 1), result.output
	assert "fleet intensity" in result.stdout, result.stdout
	assert "against the graph's" in result.stdout
	assert "unserved" in result.stdout, result.stdout
	assert "of demand against the graph's standard" in result.stdout


def test_the_command_exits_three_on_an_infeasible_scenario(tmp_path) -> None:
	"""A fleet the graph's reserve margin rejects exits 3, not 1 or 2.

	Three failures, three codes: 2 is a scenario never solved, 1 is a scenario
	solved and refused by the graph, 3 is a scenario the fleet cannot meet. The
	last is the one a constrained solve newly makes reachable -- a 9 GW fleet
	cannot cover a grown peak -- and a command that reported it as a solved cost
	would hand back a number no feasible dispatch produced.
	"""
	small = tmp_path / "small.nc"
	_network(firm_mw=9_000.0).export_to_netcdf(str(small))
	from typer.testing import CliRunner

	from alea.cli import app

	result = CliRunner().invoke(
		app, ["whatif", "scenario", "--network", str(small)]
	)
	assert result.exit_code == 3, result.output
	assert "infeasible" in result.output.lower()
	assert "solved:" not in result.stdout
