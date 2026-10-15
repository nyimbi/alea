# SPDX-License-Identifier: MIT
"""The PRG-to-engine translation layer, and the register of what it cannot carry.

WHAT THESE TESTS ARE FOR. The layer's headline number is how *little* it
translates: three of the graph's fifty-three settable parameters reach a
``ScenarioParameters`` knob. That number is the finding, and a test that only
checked the three work would let it drift -- add a fourth mapping and nothing
here would notice, remove one and nothing would either. So the count is
asserted as a literal, and the ratio direction is checked against the network
the engine actually scales.

WHY THE RATIO IS CHECKED BY APPLYING IT. ``fuel_price_usd_per_mwh`` is an
absolute price and ``gas_price_multiplier`` is a factor over the network's base
gas cost. A test that only asserted the arithmetic ``value / base`` would pass
on a factor computed from the wrong base, so the check runs the translated
parameters through ``apply_parameters`` and reads the marginal cost that lands
on the gas unit.
"""

from __future__ import annotations

import pandas as pd
import pypsa
import pytest

from alea.prg import load_graph
from alea.prg.graph import ParameterGraph
from alea.prg.translate import (
	TRANSLATIONS,
	coverage,
	from_scenario_parameters,
	to_scenario_parameters,
	translated,
	translations,
	untranslated,
)
from alea.whatif.apply import apply_parameters
from alea.whatif.params import ScenarioParameters


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph()


def _network(*, gas_cost: float = 40.0) -> pypsa.Network:
	"""A one-bus network with a gas unit, which the ratio mapping needs.

	The ratio translation divides by the base gas cost, so a fixture without a
	gas unit could not exercise it at all -- and a mapping never exercised is a
	mapping never checked.

	Multi-period, because ``apply_parameters`` refuses a single-period network:
	``demand_growth`` has a non-zero default and its exponent is zero everywhere
	on one year, so the engine refuses rather than applying a parameter that
	does nothing. A single-period fixture would test the translation against a
	network the engine will not scale.
	"""
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	network.set_snapshots(
		list(
			pd.DatetimeIndex(
				[
					ts
					for year in (2030, 2040)
					for ts in pd.date_range(f"{year}-01-01", periods=2, freq="h")
				]
			)
		)
	)
	network.add(
		"Generator", "gas", bus="b1", carrier="gas", p_nom=200.0,
		marginal_cost=gas_cost,
	)
	network.add(
		"Generator", "solar", bus="b1", carrier="solar", p_nom=20.0,
		p_nom_max=200.0, p_nom_extendable=True, capital_cost=50_000.0,
	)
	network.add("Load", "load", bus="b1", p_set=120.0)
	return network


# --------------------------------------------------------------------------
# The register
# --------------------------------------------------------------------------


def test_the_coverage_count_is_a_literal_and_matches_the_register(
	graph: ParameterGraph,
):
	"""Three of fifty-two, asserted rather than derived.

	Deriving the expected count from ``TRANSLATIONS`` would make this vacuous:
	it would pass on a layer that translated everything and on one that
	translated nothing. The literal is the claim; the register is the witness.

	The denominator moved 53 -> 52 when the three endogenous fleet nodes
	landed: they are chosen by the optimiser, so ``is_settable`` is False for
	them and they are not part of the surface the engine can be *driven* from.
	They are not missing from the register -- ``endogenous`` carries them, and
	``audit.fleet_parameters`` reads them back out of a solved result.
	"""
	cov = coverage(graph)
	assert cov["count"] == 3, cov
	assert cov["total"] == 52, cov
	assert cov["count"] + len(cov["untranslated"]) == cov["total"]
	assert set(cov["translated"]) | set(cov["untranslated"]) == {
		name for name in graph.nodes if graph.is_settable(name)
	}
	# The three that left the denominator, named where they went.
	assert len(cov["endogenous"]) == 3, cov["endogenous"]
	assert not (set(cov["endogenous"]) & set(cov["untranslated"]))


def test_every_translation_names_a_parameter_the_graph_actually_has(
	graph: ParameterGraph,
):
	"""A mapping onto a parameter that does not exist is a mapping onto nothing."""
	for translation in translations():
		assert translation.prg_parameter in graph.nodes, translation
		assert graph.is_settable(translation.prg_parameter), translation


def test_every_translation_names_an_engine_field_that_exists():
	"""``translations()`` validates the fields, so a rename breaks it loudly.

	Without the check the stale name raises at *use*, where it reads as "the
	engine cannot apply this" rather than "this mapping is wrong".
	"""
	fields = set(ScenarioParameters.model_fields)
	for translation in translations():
		assert translation.engine_field in fields, translation


def test_a_declared_field_the_engine_lacks_is_refused(monkeypatch):
	"""The validator is checked by planting a stale field, not assumed.

	A validator never watched rejecting is a validator whose behaviour is a
	guess. This plants a translation naming a field that does not exist and
	asserts ``translations()`` refuses it by name.
	"""
	import alea.prg.translate as module

	stale = module.Translation(
		prg_parameter="carbon_price_usd_per_tco2",
		engine_field="no_such_knob",
		kind="absolute",
		note="planted",
	)
	monkeypatch.setattr(module, "TRANSLATIONS", (*module.TRANSLATIONS, stale))
	with pytest.raises(ValueError, match="no_such_knob"):
		module.translations()


def test_the_untranslated_register_is_not_empty_and_says_why(
	graph: ParameterGraph,
):
	"""The register exists because most of the graph cannot reach the engine.

	An empty register would mean the two sets coincide, which they do not: the
	graph states what the accounts require and the engine states what a PyPSA
	network can be perturbed by.
	"""
	missing = untranslated(graph)
	assert len(missing) == 49, missing
	assert "voll_usd_per_mwh" in missing
	assert "capacity_factor" in missing
	# The fleet nodes are not in this register, and their absence is a fact
	# about them rather than about the engine: nothing a scenario *sets*
	# determines the fleet, because the solve does.
	assert "thermal_capacity_mw" not in missing
	assert "thermal_capacity_mw" in graph.endogenous()


# --------------------------------------------------------------------------
# The absolute direction
# --------------------------------------------------------------------------


def test_an_absolute_parameter_translates_one_for_one(graph: ParameterGraph):
	params = to_scenario_parameters(
		graph, {"carbon_price_usd_per_tco2": 120.0, "demand_growth": 0.05}
	)
	assert params.carbon_price_usd_per_tco2 == 120.0
	assert params.demand_growth == 0.05


def test_a_parameter_the_engine_cannot_carry_is_refused_by_name(
	graph: ParameterGraph,
):
	"""Strict mode names what it cannot carry rather than dropping it quietly.

	The quiet drop is the defect: the graph accepts the parameter, the engine
	never sees it, and the result looks like an answer to a question that was
	asked.
	"""
	with pytest.raises(ValueError, match="voll_usd_per_mwh"):
		to_scenario_parameters(graph, {"voll_usd_per_mwh": 9000.0})


def test_a_non_strict_translation_drops_the_parameter(graph: ParameterGraph):
	"""The non-strict path drops it, which is what the register documents."""
	params = to_scenario_parameters(
		graph,
		{"carbon_price_usd_per_tco2": 80.0, "voll_usd_per_mwh": 9000.0},
		strict=False,
	)
	assert params.carbon_price_usd_per_tco2 == 80.0
	assert not hasattr(params, "voll_usd_per_mwh")


def test_a_parameter_not_in_the_graph_is_ignored_rather_than_guessed(
	graph: ParameterGraph,
):
	params = to_scenario_parameters(graph, {"not_a_parameter": 1.0}, strict=False)
	assert params == ScenarioParameters()


def test_a_name_that_is_not_a_graph_parameter_is_refused_by_strict(
	graph: ParameterGraph,
):
	"""A typo must not solve, which is the whole value of the default path.

	WHY THIS IS A DIFFERENT FINDING FROM AN UNCARRIED PARAMETER. ``voll_usd_per_mwh``
	is a graph parameter the engine has no knob for; a caller setting it asked for
	something real the engine cannot express. ``carbon_price_usd_per_ton`` is not a
	graph parameter at all, and the failure it causes is the quiet one the strict
	path exists to prevent: the translation ignores it, the engine solves, the
	objective looks like an answer, and the parameter the caller believed they set
	moved nothing.

	The messages are asserted apart, because sharing one would tell an author to
	widen the engine for a parameter that does not exist.
	"""
	with pytest.raises(ValueError, match="not graph parameters"):
		to_scenario_parameters(graph, {"carbon_price_usd_per_ton": 200.0})
	# The uncarried-but-real case keeps its own message.
	with pytest.raises(ValueError, match="the engine cannot carry"):
		to_scenario_parameters(graph, {"voll_usd_per_mwh": 9000.0})


def test_a_derived_parameter_is_refused_as_derived_not_as_a_typo(
	graph: ParameterGraph,
):
	"""A third finding, and the message has to be the third message.

	``lcoe_usd_per_mwh`` *is* a graph parameter -- the graph computes it -- so a
	refusal calling it "not a graph parameter" is false, and the fix it implies
	(spell-check it) is the wrong one. Setting a derived value changes nothing:
	``propagate`` overwrites it. Three classes of key reach no knob and each
	needs its own advice.
	"""
	assert "lcoe_usd_per_mwh" in graph.nodes
	assert not graph.is_settable("lcoe_usd_per_mwh")
	with pytest.raises(ValueError, match="the graph computes"):
		to_scenario_parameters(graph, {"lcoe_usd_per_mwh": 50.0})


def test_an_endogenous_parameter_is_refused_as_a_decision_not_as_derived(
	graph: ParameterGraph,
):
	"""The fourth finding, and the derived message is actively wrong for it.

	``thermal_capacity_mw`` is not settable, so a register built on
	``is_settable`` files it with the derived parameters -- and the derived
	refusal's advice, "set what determines it instead", is advice that cannot
	be followed: nothing a scenario sets determines what the optimiser chooses.
	The two are one boolean and two different sentences, which is why
	``graph.role`` exists rather than a second predicate over ``is_settable``.

	The refusal must name the *right* fix. A scenario that wants a different
	fleet moves what the solve is given -- the carbon price, the demand, the
	build target -- and the message says so.
	"""
	assert "thermal_capacity_mw" in graph.nodes
	assert not graph.is_settable("thermal_capacity_mw")
	with pytest.raises(ValueError, match="chosen by the optimisation"):
		to_scenario_parameters(graph, {"thermal_capacity_mw": 9000.0})
	# The derived message must not be what comes back: a caller reading "the
	# graph computes" would go looking for an equation to change.
	with pytest.raises(ValueError) as excinfo:
		to_scenario_parameters(graph, {"thermal_capacity_mw": 9000.0})
	assert "the graph computes" not in str(excinfo.value)


def test_a_typo_is_named_in_the_loose_register(graph: ParameterGraph):
	"""Loose drops it, and `untranslated()` cannot be the register that says so.

	``untranslated()`` enumerates the graph's own settable parameters, so a name
	that is not in the graph appears in neither it nor ``translated()`` -- a
	register filtered on it reports a typo as cleanly carried.
	"""
	from alea.prg.translate import translated, untranslated

	untranslated_names = set(untranslated(graph))
	assert "carbon_price_usd_per_ton" not in untranslated_names
	assert "carbon_price_usd_per_ton" not in set(translated(graph))
	# Loose still drops it without raising; the register that catches it is the
	# caller's, which is why `solve_from_prg` builds `dropped` from `translated`.
	params = to_scenario_parameters(graph, {"carbon_price_usd_per_ton": 200.0}, strict=False)
	assert params == ScenarioParameters()


# --------------------------------------------------------------------------
# The ratio direction
# --------------------------------------------------------------------------


def test_a_ratio_translation_without_a_network_is_refused(graph: ParameterGraph):
	"""There is no ratio without a base, and defaulting one applies nothing."""
	with pytest.raises(ValueError, match="needs the network"):
		to_scenario_parameters(graph, {"fuel_price_usd_per_mwh": 60.0})


def test_a_ratio_translation_needs_a_base_the_network_carries(
	graph: ParameterGraph,
):
	"""A network with no gas unit has no base gas cost to divide by."""
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	network.add("Generator", "solar", bus="b1", carrier="solar", p_nom=10.0)
	with pytest.raises(ValueError, match="no base level"):
		to_scenario_parameters(
			graph, {"fuel_price_usd_per_mwh": 60.0}, network
		)


def test_the_ratio_applies_the_prg_price_to_the_gas_unit(graph: ParameterGraph):
	"""The translated factor, run through the engine, lands the PRG price.

	The arithmetic check alone would pass on a factor computed from the wrong
	base; this applies it and reads the marginal cost that reaches the gas unit.
	"""
	network = _network(gas_cost=40.0)
	params = to_scenario_parameters(
		graph, {"fuel_price_usd_per_mwh": 60.0}, network
	)
	assert params.gas_price_multiplier == pytest.approx(60.0 / 40.0)

	applied = apply_parameters(network, params)
	assert applied.generators.loc["gas", "marginal_cost"] == pytest.approx(60.0)
	# And nothing else moved, so the factor did not leak onto the solar unit.
	assert applied.generators.loc["solar", "marginal_cost"] == 0.0


def test_the_ratio_reads_the_recorded_base_not_the_current_value(
	graph: ParameterGraph,
):
	"""Dividing by the current cost would compound across applications.

	``apply.py`` records the pre-scenario base for exactly this reason, and the
	translation reads the same record. Applying the translated parameters twice
	must give the same network as applying them once.
	"""
	network = _network(gas_cost=40.0)
	params = to_scenario_parameters(
		graph, {"fuel_price_usd_per_mwh": 60.0}, network
	)
	once = apply_parameters(network, params)
	twice = apply_parameters(once, params)
	assert twice.generators.loc["gas", "marginal_cost"] == pytest.approx(60.0)


# --------------------------------------------------------------------------
# The inverse direction
# --------------------------------------------------------------------------


def test_the_inverse_carries_the_absolute_parameters_back():
	"""``from_scenario_parameters`` is partial, and the partiality is the point.

	The engine's knobs no PRG parameter names -- ``coal_eaf``,
	``battery_cost_multiplier``, the SSP pathway -- have no route back, so the
	result is what the graph can speak to, not the scenario's whole set.
	"""
	params = ScenarioParameters(carbon_price_usd_per_tco2=95.0, coal_eaf=1.4)
	back = from_scenario_parameters(params)
	# `demand_growth` carries a default, so it is present whether or not the
	# caller set it; the point is that `coal_eaf` has no PRG name at all.
	assert back["carbon_price_usd_per_tco2"] == 95.0
	assert "coal_eaf" not in back
	assert set(back) <= {t.prg_parameter for t in TRANSLATIONS}


def test_a_ratio_mapping_is_not_reversed_because_it_cannot_be():
	"""A factor has no absolute value without the base it was formed against."""
	for translation in TRANSLATIONS:
		if translation.kind == "ratio":
			assert translation.prg_parameter not in from_scenario_parameters(
				ScenarioParameters(gas_price_multiplier=1.5)
			)


def test_the_translated_names_are_settable(graph: ParameterGraph):
	"""A translation naming a derived parameter would be a mapping onto a number
	the caller cannot set."""
	for name in translated(graph):
		assert graph.is_settable(name), name
