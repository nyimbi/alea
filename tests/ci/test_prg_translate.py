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

from pathlib import Path

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
	"""Three of nine hundred and thirty-five, asserted rather than derived.

	Deriving the expected count from ``TRANSLATIONS`` would make this vacuous:
	it would pass on a layer that translated everything and on one that
	translated nothing. The literal is the claim; the register is the witness.

	The numerator is the finding and it has not moved. The denominator went
	52 -> 833 when the catalog's 787 parameters became nodes, and 833 -> 886
	when the generated batches were promoted: 53 more settable knobs with
	defaults, none of which the engine can be driven from. That is the honest
	state of the seam between the document and PyPSA, and pinning only the
	denominator would have hidden it -- two expansions grew the register by
	834 and the translated count by zero.

	911 -> 913 when batch 19's sector-coupling layer added two exogenous
	hydrogen knobs (``hydrogen_per_t_steel_kg``, ``hydrogen_share_of_ammonia``);
	batch 20's re-bake moved nothing settable. 913 -> 914 when batch 21 added
	one settable knob, ``uranium_burnup_lb_per_mwh`` (nuclear fuel layer), and
	it landed untranslated like its 885 siblings -- of batch 21's seventeen new
	parameters only this one carries a default.

	914 -> 922 when batch 22 (the compliance register) added eight settable
	base nodes: ``population_total``, ``distribution_feeders_total``,
	``pm25_annual_mean_ug_per_m3``, ``project_pipeline_count``,
	``scada_telemetry_sites``, ``river_mean_annual_flow_m3_per_s``,
	``distribution_network_km`` and ``audit_accounts_per_year``. All eight
	landed untranslated, so the numerator stayed at three while the
	denominator grew by eight -- the same one-sided growth the earlier batches
	showed.

	922 -> 935 when batch 23 (the extensive bases) added fifteen settable
	knobs and made two existing ones derived. The fifteen:
	``persons_per_household``, ``transmission_line_length_km``,
	``interconnector_route_km``, ``hydrogen_pipeline_length_km``,
	``connections_per_year``, ``passenger_kilometres_per_year``,
	``land_area_hectares``, ``energy_poverty_line_mwh_per_household``,
	``energy_poor_consumption_mwh_per_year`` and the six cumulative
	installation/reference nodes (three pairs: solar PV, battery,
	electrolyser). The two that left the denominator are
	``energy_poverty_gap`` and ``regulated_tariff_rate``, both retyped to
	``derived`` with an equation that computes them. All fifteen landed
	untranslated, so the numerator stayed at three while the denominator grew
	by thirteen.

	935 -> 926 when batch 24 retyped nine nodes from ``free`` to ``derived``
	and created no settable knob: ``carbon_tax_coverage``, ``social_tariff``,
	``ets_cap``, ``auction_volume``, ``carbon_credit_volumes``,
	``article_6_credits``, ``carbon_budget``, ``price_cap`` and
	``market_concentration`` each gained an equation that computes them, so
	the denominator fell by nine and the numerator stayed at three. Every one
	of batch 24's seventy-six remaining new parameters arrived derived, which
	is why the denominator moved down rather than up.

	926 -> 926 when batch 25 landed. It created no settable knob and derived
	none: the nine placeholders it retyped (the insurance, trade, sanctions
	and upgrade-budget nodes) stayed ``free``, gaining a unit, a range and a
	real default rather than an equation, and all thirteen of its new
	parameters arrived derived. So the denominator and the numerator are both
	unchanged, and the register's gap is the same 923 it was.

	926 -> 920 when batch 26 landed. The adequacy-and-reserve layer made ten
	placeholders derived -- ``grid_reliability_saifi``, ``non_spinning_reserve``,
	``planning_reserve_margin``, ``regulation_down_requirement``,
	``regulation_up_requirement``, ``reserve_margin``, ``spare_capacity``,
	``spinning_reserve``, ``spinning_reserve_requirement`` and
	``voltage_support_requirement`` -- each gaining an equation that computes
	it, and created four new settable knobs (the ``spinning_reserve_share``,
	``regulation_up_share``, ``regulation_down_share`` and
	``voltage_support_share`` dimensionless shares). Ten left the denominator
	and four entered it, a net six, and all four landed untranslated like
	their 913 siblings, so the numerator stayed at three. The register's gap
	fell 923 to 917, by the same net six.

	918 and 915 when batch 27 landed. The finance family made nine
	placeholders derived (``debt_service_coverage_ratio``,
	``insurance_premiums``, ``interest_rate_debt``, ``maladaptation_risk``,
	``project_irr_hurdle``, ``rab_roll_forward``, ``solvency_capital``,
	``transaction_costs`` and the three risk premiums) and created ten new
	settable knobs (``aal_usd_million``, ``pml_99_5_usd_million``,
	``expense_loading``, ``capital_loading``, ``profit_margin``,
	``sovereign_risk_premium``, ``debt_tenor`` and the three retyped
	shares). Nine left the denominator and ten entered it, a net one, so the
	denominator fell 920 to 918 -- and the numerator stayed at three, so the
	register's gap fell 917 to 915.

	The eighteen the engine cannot carry are still outside the denominator:
	they are chosen by the optimiser, so ``is_settable`` is False for them.
	They are not missing from the register -- ``endogenous`` carries them, and
	``audit.fleet_parameters`` reads them back out of a solved result.
	"""
	cov = coverage(graph)
	assert cov["count"] == 3, cov
	assert cov["total"] == 918, cov
	assert cov["count"] + len(cov["untranslated"]) == cov["total"]
	assert set(cov["translated"]) | set(cov["untranslated"]) == {
		name for name in graph.nodes if graph.is_settable(name)
	}
	# The nineteen that left the denominator, named where they went.
	assert len(cov["endogenous"]) == 19, cov["endogenous"]
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

	The literal is the denominator's partner, so the reason it moved is the
	one above: batch 26 made ten reserve placeholders derived and created
	four untranslated shares, a net six, taking the register 923 to 917. Batch
	27 then made nine finance placeholders derived and added ten settable
	knobs, a net one, taking it 917 to 915. The numerator stayed at three, so
	the gap and the denominator fell together.
	"""
	missing = untranslated(graph)
	assert len(missing) == 915, missing
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

	The refusal must name the *right* fix, and every lever it names must
	actually reach a solve. The message offered "the build target" until
	2026-10-15, when the levers were derived from the translation table and the
	constraint register instead: ``vre_capacity_target_mw`` reaches neither an
	engine knob nor an inequality, so it was a lever a reader would pull and see
	nothing move. The assertion below is the property, not the prose -- it
	checks each name the message offers against the two sets that decide it, so
	a lever that stops reaching a solve fails here rather than in a reader's
	scenario.
	"""
	from alea.prg.constraints import bound_parameter_names
	from alea.prg.translate import translated

	assert "thermal_capacity_mw" in graph.nodes
	assert not graph.is_settable("thermal_capacity_mw")
	with pytest.raises(ValueError, match="chosen by the optimisation") as excinfo:
		to_scenario_parameters(graph, {"thermal_capacity_mw": 9000.0})
	message = str(excinfo.value)
	# The derived message must not be what comes back: a caller reading "the
	# graph computes" would go looking for an equation to change.
	assert "the graph computes" not in message

	# The lever list must *equal* the set that reaches a solve, not merely
	# contain names from it. A membership check cannot see the defect this
	# guards: the original message said "the build target", which is prose and
	# matches no parameter name at all, so a gate asking "is every name in the
	# message a real lever" passes on an empty list. Pinning equality fails on
	# prose *and* on a stale hand-written list, which is the shape both bugs
	# took. Canaried by restoring the prose text: the assertion below fails.
	reaches = set(translated(graph)) | set(bound_parameter_names(graph))
	tail = message.split("given -- ", 1)[-1]
	assert tail != message, "the refusal no longer names the levers it offers"
	assert tail.split(" -- ", 1)[0] == ", ".join(sorted(reaches)), (
		"the refusal's lever list is not the set that reaches a solve; a lever "
		"written by hand drifts from the register the moment a route is added "
		"or removed"
	)
	assert "build target" not in message, (
		"the build target reaches no solve, so offering it sends a reader to a "
		"lever that moves nothing"
	)


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


# ---------------------------------------------------------------------------
# The cross-layer register
# ---------------------------------------------------------------------------


def test_every_cross_layer_entry_resolves_on_both_sides():
	"""A rename in either file must break the register, not empty it.

	The register is declared rather than derived because no mechanical join
	exists -- the two files name the same quantity differently, and a fuzzy
	join on shared tokens matches dozens of unrelated nodes. The cost of a
	declared list is that it can go stale silently, and this is the check that
	prevents it: an entry whose ``config_path`` or ``prg_parameter`` no longer
	resolves is a register that has quietly stopped watching what it claims to
	watch. Asserted per entry and by name, so the failure says which one.
	"""
	from alea.prg.translate import (
		CROSS_LAYER_QUANTITIES,
		_dig,
		_graph_value,
		_read_default_config,
	)

	# The same reader the register uses, so the test asserts what the register
	# actually compares rather than a differently-shaped view of it.
	config = _read_default_config()
	assert config is not None, "config/config.default.yaml is not readable"
	graph = load_graph()
	for entry in CROSS_LAYER_QUANTITIES:
		value = _dig(config, entry.config_path)
		assert value is not None, (
			f"{entry.config_path!r} does not resolve in config.default.yaml; the "
			f"register is watching a path that no longer exists"
		)
		assert isinstance(value, (int, float)), (
			f"{entry.config_path!r} resolved to {type(value).__name__}, not a "
			f"number; the register compares values and cannot compare this"
		)
		if not entry.prg_parameter:
			# The empty column is a deliberate state -- the quantity has no
			# graph node -- and it must stay deliberate. If a node with this
			# name appears, the entry should name it rather than keep claiming
			# the graph cannot speak to the quantity.
			continue
		assert entry.prg_parameter in graph.nodes, (
			f"{entry.prg_parameter!r} is not a node; the register names a graph "
			f"parameter that no longer exists"
		)
		assert _graph_value(entry.prg_parameter) is not None, (
			f"{entry.prg_parameter!r} declares no default, so the register has "
			f"nothing to compare the config value against"
		)
		assert graph.node(entry.prg_parameter).unit == entry.unit, (
			f"{entry.prg_parameter!r} is in "
			f"{graph.node(entry.prg_parameter).unit!r} and the register says "
			f"{entry.unit!r}; a name match with a unit mismatch is a different "
			f"finding and must not pass as agreement"
		)


def test_the_volll_disagreement_is_reported_rather_than_hidden():
	"""The live half: the shipped values differ by 2.5x and the register says so.

	Both numbers are correct on their own line -- the config's 2,000 is the
	figure the determinism job has used since it was written, and the graph's
	5,000 is a `to_build` node nothing sources -- which is exactly why no check
	in the tree noticed. This asserts the register reports it, and pins the
	ratio, so a change to either number has to move this test with it rather
	than silently closing (or widening) the gap.
	"""
	from alea.prg.translate import _read_default_config, cross_layer_disagreements

	# The register's own reader: `load_config()` validates the whole deployment
	# config, and a comparison of two numbers in two files needs neither.
	config = _read_default_config()
	assert config is not None, "config/config.default.yaml is not readable"
	disagreements = cross_layer_disagreements()
	named = {entry.prg_parameter for entry in disagreements}
	assert "voll_usd_per_mwh" in named, (
		"the VoLL disagreement is no longer reported; either the two values "
		"now agree (move this test and the status entry together) or the "
		f"register went blind. Reported: {sorted(named)}"
	)
	config_value = config["market"]["value_of_lost_load_usd_per_mwh"]
	graph_value = load_graph().node("voll_usd_per_mwh").default
	assert config_value == 2000.0, config_value
	assert graph_value == 5000.0, graph_value
	# The `== 5000.0` above narrows for a reader but not for pyright, and the
	# division below needs the narrowed type.
	assert graph_value is not None
	assert graph_value / config_value == pytest.approx(2.5)


def test_a_register_that_cannot_run_says_so_rather_than_reporting_agreement(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	"""An unreadable config is not an agreement, and the payload distinguishes them.

	Several tests build a scratch repo root holding only `prg.yaml`. The first
	version of this register called `load_config()` and those tests raised
	`ValidationError: scenario / Field required` -- a real coupling, since the
	register compares two numbers in two files and needs neither validated.
	Reading the file fixed that. This pins the other half: a missing file must
	produce `compared: false` with a reason, because an empty disagreement list
	and a register that never ran are byte-identical JSON otherwise, and only
	one of them is good news.
	"""
	import alea.config.paths as paths
	from alea.prg.translate import cross_layer_report

	monkeypatch.setattr(paths, "config_dir", lambda: tmp_path)
	report = cross_layer_report()
	assert report["compared"] is False, report
	assert report["reason"], "an unavailable register must name why"
	assert report["disagreements"] == []


def test_a_quantity_that_agrees_is_not_reported():
	"""The register must not report agreement as disagreement.

	A check that flagged every declared entry would be indistinguishable from
	one that flagged the differing ones, and a reader would learn to ignore it.
	Exercised through the *function* with an injected pair, not by asserting
	arithmetic in the test body: `abs(2000.0 - 2000.0) <= 1e-12` passes against
	a version of `cross_layer_disagreements` that returns every entry, which is
	the predicate this test exists to pin.
	"""
	from alea.prg.translate import (
		CROSS_LAYER_QUANTITIES,
		_read_default_config,
		cross_layer_disagreements,
	)

	config = _read_default_config()
	assert config is not None, "config/config.default.yaml is not readable"
	entry = CROSS_LAYER_QUANTITIES[0]
	assert entry.prg_parameter == "voll_usd_per_mwh", entry

	# The shipped pair disagrees, so it is reported.
	reported = cross_layer_disagreements(
		(entry,), config=config, graph_values={"voll_usd_per_mwh": 5000.0}
	)
	assert reported == (entry,)

	# The same entry with the graph side moved onto the config value is not.
	agreed = cross_layer_disagreements(
		(entry,),
		config=config,
		graph_values={
			"voll_usd_per_mwh": config["market"]["value_of_lost_load_usd_per_mwh"]
		},
	)
	assert agreed == (), (
		"the register reported an entry whose two sides hold the same value; a "
		"check that flags agreement is one a reader learns to ignore"
	)

	# And a side that does not resolve is skipped rather than reported: an
	# unresolvable entry is a broken register, which its own test catches, and
	# filing it here would mix that with a genuine disagreement.
	absent = cross_layer_disagreements(
		(entry,), config=config, graph_values={"voll_usd_per_mwh": None}
	)
	assert absent == ()


def test_every_cross_layer_note_quotes_the_values_the_payload_holds():
	"""A register's prose is a claim, and a claim nothing checks is one that drifts.

	Every `note` in the register states its pair in words -- "config is 2000.0
	and the graph is 5000.0", "a 2.5x disagreement" -- and until this test the
	payload carried the sentence and neither number. Move either side and the
	register keeps asserting the old figure, because no reader parses a
	sentence: the same class as the loss kernel's 333x unit error and the
	`interim` config key, where a declaration is right on its own line and
	nothing compares the lines.

	So the payload now carries `config_value`, `graph_value` and `ratio`, and
	this gate requires the note to *name* both measured values. The check is
	positive rather than a blocklist: rejecting a set of forbidden numbers would
	pass when the note quotes a third figure neither side holds, which is the
	subset predicate this project has already shipped once.
	"""
	import re

	from alea.prg.translate import cross_layer_report

	report = cross_layer_report()
	assert report["compared"] is True, report["reason"]
	assert report["disagreements"], (
		"the register reports no disagreement; either the layers now agree or it "
		"went blind, and this test cannot tell the difference from here"
	)
	for row in report["disagreements"]:
		for side, value in (
			("config", row["config_value"]),
			("graph", row["graph_value"]),
		):
			assert value is not None, (
				f"{row['config_path']} reported as a disagreement with no "
				f"{side} value; the note describes a number the payload lacks"
			)
			# An exact token, not a substring: `"2000" in note` passes against
			# `12000.0`, which is the substring-checking failure this project
			# has shipped more than once. The lookarounds pin the whole number.
			token = re.escape(f"{float(value)}")
			assert re.search(rf"(?<![\d.]){token}(?![\d.])", row["note"]), (
				f"the {side} value is {value!r} and the note does not name it as "
				f"a whole number: {row['note']!r}. The register's prose has "
				f"drifted from the measurement it describes."
			)


def test_the_ratio_is_derived_from_the_two_measured_values():
	"""`ratio` is arithmetic on the pair, not a third transcribed number."""
	from alea.prg.translate import _ratio

	assert _ratio(2000.0, 5000.0) == pytest.approx(2.5)
	assert _ratio(4.0, 2.0) == pytest.approx(0.5)
	# A zero config value is a legitimate declaration -- a quantity a
	# deployment switched off -- and the ratio is undefined while the
	# disagreement is not, so it is None rather than an infinity.
	assert _ratio(0.0, 5000.0) is None
	assert _ratio(None, 5000.0) is None
	assert _ratio(2000.0, None) is None
	assert _ratio("not a number", 5000.0) is None


def test_the_note_drift_gate_notices_a_note_that_quotes_the_wrong_figure():
	"""The canary for ``test_every_cross_layer_note_quotes_the_values_the_payload_holds``.

	The mutation changes the note's *prose* from 5000.0 to a figure neither side
	holds. That is disjoint from what the predicate looks for: the predicate
	reads the payload's measured pair and asks whether the sentence names it, so
	a mutation on the sentence is the one class it must catch and the class no
	other check in the tree can see.

	Restored from the canary harness's own byte-level snapshot, so a killed
	process cannot leave the register asserting a number nothing measured.
	"""
	from tests.ci.canaries import REPO, planted, probe_exit_code

	translate_py = REPO / "src" / "alea" / "prg" / "translate.py"
	node = (
		"tests/ci/test_prg_translate.py::"
		"test_every_cross_layer_note_quotes_the_values_the_payload_holds"
	)
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)

	shipped = "disagree: config is 2000.0 and the graph is 5000.0"
	broken = "disagree: config is 2000.0 and the graph is 4500.0"

	assert probe_exit_code(program) == 0, "the gate was already failing"
	with planted(translate_py, shipped, broken):
		assert probe_exit_code(program) != 0, (
			"the note quoted 4500.0 for a side the payload measures at 5000.0 and "
			"the gate passed; it is not reading the sentence"
		)
	assert probe_exit_code(program) == 0, "the gate did not recover"
