# SPDX-License-Identifier: MIT
"""The Parameter Relationship Graph: DSL, graph, propagation, consistency.

WHAT THESE TESTS ARE FOR. The PRG's whole value is that a scenario which sets
two coupled parameters independently is *refused*. A test that only checks the
shipped graph loads and its consistency report is empty would pass on a graph
with no equations at all -- the vacuous pass that `tests/ci/canaries` exists to
catch elsewhere. So every check here is paired with the input that must fail
it: a derivative against a finite difference, a fixed point against its closed
form, a consistency report against a value deliberately made inconsistent.

WHY THE LOOP IS CHECKED AGAINST A CLOSED FORM. The capture-price loop is three
linear equations, so its fixed point has an exact solution:

    share = t / (total + s·t),  ratio = 1 / (1 + s·t / total)

for a build target ``t``, cannibalisation coefficient ``s`` and total capacity
``total``. A solver checked against itself proves only that it is consistent
with itself; the closed form is an independent witness, and it is what makes
"converged" mean "converged to the answer" rather than "stopped moving".
"""

from __future__ import annotations

import math

import pytest
import yaml

from alea.config.paths import repo_root
from alea.prg import load_graph
from alea.prg.dsl import DslError, const, evaluate, parse, simplify, solve_for, sym
from alea.prg.graph import CycleError, GraphError, ParameterGraph
from alea.prg.library import SYSTEM_IDS, coverage, systems_of
from alea.prg.service import check_scenario, describe, graph_summary, propagate_change

PRG_PATH = repo_root() / "config" / "prg.yaml"


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph(PRG_PATH)


@pytest.fixture
def document() -> dict:
	return yaml.safe_load(PRG_PATH.read_text())


@pytest.fixture
def defaults(graph: ParameterGraph) -> dict[str, float]:
	return {k: n.default for k, n in graph.nodes.items() if n.default is not None}


# ---------------------------------------------------------------------------
# The DSL: creation, rendering, evaluation
# ---------------------------------------------------------------------------

#: Expression, the values it needs, and its value. Hand-computed, so the test
#: is an independent check of the evaluator rather than a recording of it.
_EVALUATIONS = [
	("a + b", {"a": 2.0, "b": 3.0}, 5.0),
	("a - b", {"a": 2.0, "b": 3.0}, -1.0),
	("a * b", {"a": 2.0, "b": 3.0}, 6.0),
	("a / b", {"a": 6.0, "b": 3.0}, 2.0),
	("a ** b", {"a": 2.0, "b": 10.0}, 1024.0),
	("(a + b) * c", {"a": 1.0, "b": 2.0, "c": 4.0}, 12.0),
	("a / b / c", {"a": 12.0, "b": 2.0, "c": 3.0}, 2.0),
	("sqrt(a)", {"a": 16.0}, 4.0),
	("exp(a)", {"a": 0.0}, 1.0),
	("ln(a)", {"a": math.e}, 1.0),
	("abs(a)", {"a": -3.0}, 3.0),
	("min(a, b)", {"a": 3.0, "b": 1.0}, 1.0),
	("max(a, b)", {"a": 3.0, "b": 1.0}, 3.0),
	("log10(a)", {"a": 1000.0}, 3.0),
	("-a + b", {"a": 1.0, "b": 5.0}, 4.0),
	("a ** -1", {"a": 4.0}, 0.25),
]


@pytest.mark.parametrize(("source", "values", "expected"), _EVALUATIONS)
def test_the_dsl_evaluates_arithmetic(source: str, values: dict, expected: float):
	"""Each form's value, against a number worked out by hand."""
	assert parse(source).eval(values) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(("source", "values", "expected"), _EVALUATIONS)
def test_rendering_round_trips_through_source(source: str, values: dict, expected: float):
	"""A rendered formula re-parses to the same value.

	This is the property that makes rendering trustworthy. A renderer whose
	output parses to a *different* formula is a renderer that shows a reviewer
	something other than what runs, and the reviewer has no way to tell.
	"""
	expression = parse(source)
	reparsed = parse(expression.source())
	assert reparsed.eval(values) == pytest.approx(expected, rel=1e-12)
	assert reparsed.source() == expression.source(), "rendering is not idempotent"


def test_a_power_of_a_power_is_parenthesised():
	"""``(x ** y) ** -1`` is not ``x ** (y ** -1)``, and must not render as it.

	The first renderer emitted the unparenthesised form, which re-parses to a
	different formula -- the round-trip test above is what found it.
	"""
	expression = parse("(x ** y) ** -1")
	assert expression.source() == "(x ** y) ** (-1)"
	assert parse(expression.source()).source() == expression.source()


def test_the_latex_rendering_is_valid_and_readable():
	"""LaTeX for the shapes a report needs."""
	assert parse("a / b").latex() == r"\frac{\mathrm{a}}{\mathrm{b}}"
	assert parse("sqrt(a)").latex() == r"\sqrt{\mathrm{a}}"
	assert parse("exp(a)").latex() == r"e^{\mathrm{a}}"
	assert parse("abs(a)").latex() == r"\left|\mathrm{a}\right|"
	assert parse("a ** 2").latex() == r"{\mathrm{a}}^{2}"
	# A Greek-named parameter renders as the letter, not as its spelling.
	assert parse("beta").latex() == r"\beta"
	assert parse("alpha * beta").latex() == r"\alpha \beta"


def test_a_subscripted_symbol_does_not_produce_a_double_subscript():
	"""``emission_factor[i]`` is not ``emission_{factor_i}``.

	Both are valid LaTeX; only the second says what the formula means, and the
	first is what a naive renderer emits for a multi-word parameter name.
	"""
	rendered = parse("sum(emission_factor[i] for i in range(0, 3))").latex()
	# The summation bound, the base's own subscript, and the index's.
	assert rendered.count("_{") == 3, rendered
	assert r"{\mathrm{emission}_{factor}}_{\mathrm{i}}" in rendered, rendered


def test_the_mathml_rendering_is_well_formed():
	from xml.etree import ElementTree

	for source in ("a / b", "sqrt(a)", "a ** 2", "sum(x[i] for i in range(0, 2))"):
		markup = parse(source).mathml()
		ElementTree.fromstring(markup)  # raises if it is not well-formed


def test_a_sum_over_an_array_evaluates():
	"""The summation the equation library needs, over a fleet."""
	expression = parse("sum(capacity[i] * factor[i] for i in range(0, 3))")
	values = {"capacity": [10.0, 20.0, 30.0], "factor": [0.5, 0.2, 0.1]}
	assert expression.eval(values) == pytest.approx(10 * 0.5 + 20 * 0.2 + 30 * 0.1)
	assert "Σ" in expression.unicode()


def test_evaluation_broadcasts_over_a_timeseries():
	"""A profile times a scalar is the shape a parameters-times-profile needs."""
	import numpy as np

	expression = parse("capacity_factor * profile")
	values = {"capacity_factor": 0.4, "profile": np.array([1.0, 0.5, 0.25])}
	out = expression.eval_array(values)
	assert isinstance(out, np.ndarray)
	assert list(out) == pytest.approx([0.4, 0.2, 0.1])


# ---------------------------------------------------------------------------
# The DSL: differentiation
# ---------------------------------------------------------------------------

_DERIVATIVES = [
	("a * b", "a", {"a": 2.0, "b": 3.0}, 3.0),
	("a ** 2", "a", {"a": 3.0}, 6.0),
	("a ** 3", "a", {"a": 2.0}, 12.0),
	("ln(a)", "a", {"a": 4.0}, 0.25),
	("exp(a)", "a", {"a": 1.0}, math.e),
	("sqrt(a)", "a", {"a": 9.0}, 1.0 / 6.0),
	("sin(a)", "a", {"a": 0.0}, 1.0),
	("a / b", "a", {"a": 6.0, "b": 2.0}, 0.5),
	("a / b", "b", {"a": 6.0, "b": 2.0}, -1.5),
	("2 ** a", "a", {"a": 3.0}, 8.0 * math.log(2.0)),
	("a * b + c", "b", {"a": 2.0, "b": 3.0, "c": 1.0}, 2.0),
]


@pytest.mark.parametrize(("source", "symbol", "values", "expected"), _DERIVATIVES)
def test_the_symbolic_derivative_matches_a_finite_difference(
	source: str, symbol: str, values: dict, expected: float
):
	"""The derivative, against both a hand value and a numeric difference.

	The hand value catches a wrong rule; the difference catches a right rule
	applied to the wrong sub-expression. They fail differently, which is why
	both are here.
	"""
	expression = parse(source)
	derivative = expression.diff(symbol)
	assert derivative.eval(values) == pytest.approx(expected, rel=1e-9)

	step = 1e-6
	up = dict(values)
	down = dict(values)
	up[symbol] += step
	down[symbol] -= step
	numeric = (expression.eval(up) - expression.eval(down)) / (2 * step)
	assert derivative.eval(values) == pytest.approx(numeric, rel=1e-5)


def test_a_function_with_no_derivative_rule_is_refused():
	"""``min`` has a kink where its arguments cross.

	A derivative that returned a step function would render as a formula and be
	used to accelerate a solver that then oscillates.
	"""
	with pytest.raises(DslError, match="no derivative rule"):
		parse("min(a, b)").diff("a")


def test_differentiating_a_bound_index_is_refused():
	"""The summation index is bound; it is not a parameter of the sum."""
	with pytest.raises(DslError, match="summation index"):
		parse("sum(x[i] for i in range(0, 3))").diff("i")


# ---------------------------------------------------------------------------
# The DSL: simplification and solving
# ---------------------------------------------------------------------------


def test_simplification_folds_and_collects():
	# Built rather than parsed: `parse` refuses a constant expression, because
	# one names no parameter and would pass every consistency check vacuously.
	assert simplify(const(2) + const(3)).source() == "5"
	assert simplify(parse("a * 1")).source() == "a"
	assert simplify(parse("a + 0")).source() == "a"
	assert simplify(parse("a ** 1")).source() == "a"
	assert simplify(parse("a ** 0")).source() == "1"
	# Like terms combine; unlike terms do not.
	assert simplify(parse("2 * a + 3 * a")).source() == "5 * a"
	assert simplify(parse("a * a")).source() == "a ** 2"


def test_simplification_preserves_the_value():
	"""A simplifier that changes the answer is worse than none."""
	for source in ("2 * a + 3 * a", "a * a * b", "(a + b) * 1", "a ** 2 * a ** 3"):
		values = {"a": 1.7, "b": 0.3}
		assert simplify(parse(source)).eval(values) == pytest.approx(
			parse(source).eval(values), rel=1e-12
		)


def test_solving_finds_the_root_and_refuses_an_empty_bracket():
	"""``capex / (1 + r) ** n = 400`` has a root in ``(0, 0.9)`` and none below."""
	expression = parse("capex / (1 + r) ** n")
	values = {"capex": 1000.0, "n": 20.0}
	root = solve_for(expression, "r", values, bracket=(0.001, 0.9), residual=400.0)
	assert expression.eval({**values, "r": root}) == pytest.approx(400.0, rel=1e-9)
	with pytest.raises(DslError, match="no root"):
		solve_for(expression, "r", values, bracket=(0.0, 1e-9), residual=400.0)


# ---------------------------------------------------------------------------
# The DSL: the boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
	"source",
	[
		"__import__('os').system('true')",
		"(1).__class__",
		"lambda x: x",
		"[x for x in range(3)]",
		"a if b else c",
		"a == b",
		"a and b",
		"{'a': 1}",
		"a.b",
		"open('x')",
		"sum(x for x in range(0, 3) if x)",
	],
)
def test_the_dsl_refuses_what_it_does_not_model(source: str):
	"""The whitelist is the boundary, and it is also the modelling boundary.

	An expression the engine cannot model must not be *writable*, or it is an
	equation that parses and does nothing.
	"""
	with pytest.raises(DslError):
		parse(source)


def test_a_constant_expression_is_refused():
	"""It relates nothing, and would pass every consistency check vacuously."""
	with pytest.raises(DslError, match="names no parameter"):
		parse("2 + 3")


def test_a_reserved_name_cannot_be_a_parameter():
	"""``sum`` names the summation; a parameter shadowing it is ambiguous."""
	with pytest.raises(DslError, match="reserved"):
		sym("sum")


def test_expressions_are_built_in_code_as_well_as_parsed_from_text():
	"""The same tree, so a test and a YAML file can be compared."""
	built = sym("capex") * sym("capacity") / (1 + sym("discount_rate")) ** sym("asset_life")
	parsed = parse("capex * capacity / (1 + discount_rate) ** asset_life")
	assert built.source() == parsed.source()
	assert built.symbols == parsed.symbols


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def test_the_shipped_graph_loads_and_is_structurally_sound(graph: ParameterGraph):
	"""It has parameters, equations, edges, and no drift between them."""
	assert graph.nodes and graph.equations and graph.edges
	assert graph.structure_issues() == []


def test_the_topological_order_respects_every_dependency(graph: ParameterGraph):
	"""Each derived parameter follows everything it is computed from."""
	position = {name: index for index, name in enumerate(graph.order())}
	for name in graph.order():
		for dependency in graph.depends_on(name):
			if dependency in position:
				assert position[dependency] < position[name], (
					f"{name} is computed from {dependency}, which the order "
					f"places after it"
				)


def test_the_derived_parameters_match_their_closed_forms(graph: ParameterGraph, defaults: dict):
	"""Propagation against arithmetic worked out independently."""
	result = graph.propagate(defaults)
	# The discount rate is derived now -- it is the WACC -- so its value comes
	# from the propagation, and the closed form below is computed from that.
	rate = result.values["discount_rate"]
	life = defaults["asset_life"]
	crf = rate * (1 + rate) ** life / ((1 + rate) ** life - 1)
	assert result.values["crf"] == pytest.approx(crf, rel=1e-9)
	assert result.values["annualised_capex_usd_per_kw"] == pytest.approx(
		defaults["capex_usd_per_kw"] * crf, rel=1e-9
	)
	assert result.values["marginal_cost_usd_per_mwh"] == pytest.approx(
		defaults["fuel_price_usd_per_mwh"]
		+ defaults["carbon_price_usd_per_tco2"] * defaults["emission_factor_t_per_mwh"],
		rel=1e-9,
	)


def test_the_feedback_loop_converges_to_its_closed_form(graph: ParameterGraph, defaults: dict):
	"""The capture-price loop, against the solution of its three linear equations.

	With share ``= v / total``, capture ``= m·(1 - s·share)`` and
	``v = t·capture/m``, substituting gives ``v = t·(1 - s·v/total)``, so
	``v = t / (1 + s·t/total)`` and ``share = (t/total) / (1 + s·t/total)``.
	"""
	result = graph.propagate(defaults)
	loops = graph.feedback_loops()
	assert len(loops) == 1, "the shipped graph declares exactly one feedback loop"
	assert result.loops and result.loops[0].converged

	total = defaults["total_capacity_mw"]
	target = defaults["vre_capacity_target_mw"]
	sensitivity = defaults["capture_price_sensitivity"]
	share = (target / total) / (1 + sensitivity * target / total)

	assert result.values["vre_share"] == pytest.approx(share, rel=1e-7)
	assert result.values["vre_capacity_mw"] == pytest.approx(target / (1 + sensitivity * target / total), rel=1e-7)
	assert result.values["capture_price_ratio"] == pytest.approx(
		1 / (1 + sensitivity * target / total), rel=1e-7
	)


def test_the_loop_answer_does_not_depend_on_where_it_starts(graph: ParameterGraph, defaults: dict):
	"""A fixed point is a property of the map, not of the initial iterate."""
	from alea.prg.feedback import solve_loop

	loop = graph.feedback_loops()[0]
	answers = []
	# Starts below 1/sensitivity, which is where the capture price is still
	# positive: `capture = marginal * (1 - sensitivity * share)`, and above
	# that the loop has no fixed point in the price's own range at all.
	for start in (0.0, 0.1, 0.4, 0.8):
		values = graph.propagate(defaults).values
		values["vre_share"] = start
		values.pop("vre_capacity_mw", None)
		values.pop("capture_price_usd_per_mwh", None)
		answers.append(solve_loop(graph, loop, values).values["vre_share"])
	assert max(answers) - min(answers) < 1e-6, answers


def test_an_inconsistent_parameter_set_is_reported(graph: ParameterGraph, defaults: dict):
	"""The check that is the point of the graph.

	``marginal_cost`` is computed as fuel plus carbon. Setting it to a value
	that contradicts them is precisely a scenario that sets two coupled
	parameters independently.
	"""
	values = graph.propagate(defaults).values
	assert graph.consistency(values) == []

	values["marginal_cost_usd_per_mwh"] = 999.0
	violations = graph.consistency(values)
	assert violations, "a contradictory marginal cost was accepted"
	assert any(v.equation_id == "marginal_cost" for v in violations)
	assert all(v.priority in {"P1", "P2", "P3"} for v in violations)


def test_an_inequality_violation_is_reported_and_a_satisfied_one_is_not(
	graph: ParameterGraph, defaults: dict
):
	"""The reserve margin bounds a build; it does not fix one."""
	values = graph.propagate(defaults).values
	assert graph.consistency(values) == []

	values["peak_demand_mw"] = 20000.0  # no longer coverable at the margin
	violations = graph.consistency(values)
	assert any(v.equation_id == "reserve_margin" for v in violations)


def test_a_carbon_price_propagates_to_everything_downstream(graph: ParameterGraph, defaults: dict):
	"""A change moves the parameters that depend on it, and only those."""
	baseline = graph.propagate(defaults).values
	raised = dict(defaults)
	raised["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(raised)

	assert result.values["carbon_cost_usd_per_mwh"] > baseline["carbon_cost_usd_per_mwh"]
	assert result.values["marginal_cost_usd_per_mwh"] > baseline["marginal_cost_usd_per_mwh"]
	assert result.values["lcoe_usd_per_mwh"] > baseline["lcoe_usd_per_mwh"]
	# The capture price rises with marginal cost; the *ratio* is scale-free and
	# does not, which is the property that makes it the loop's summary number.
	assert result.values["capture_price_ratio"] == pytest.approx(
		baseline["capture_price_ratio"], rel=1e-6
	)


def test_a_parameter_with_no_value_is_refused(graph: ParameterGraph, defaults: dict):
	"""A non-derived parameter has no equation to compute it from."""
	incomplete = dict(defaults)
	del incomplete["fuel_price_usd_per_mwh"]
	with pytest.raises(GraphError, match="missing"):
		graph.propagate(incomplete)


def test_a_derived_parameter_is_not_settable(graph: ParameterGraph):
	assert not graph.is_settable("marginal_cost_usd_per_mwh")
	assert not graph.is_settable("vre_share")
	assert graph.is_settable("carbon_price_usd_per_tco2")
	assert "marginal_cost_usd_per_mwh" in graph.computed()


# ---------------------------------------------------------------------------
# The graph refuses malformed input, naming what is wrong
# ---------------------------------------------------------------------------


def test_two_equations_determining_one_parameter_are_refused(document: dict):
	"""Over-determination, caught at load rather than resolved by dict order."""
	document["equations"]["carbon_cost"]["determined_variables"] = [
		"marginal_cost_usd_per_mwh"
	]
	with pytest.raises((GraphError, Exception), match="determined by both"):
		ParameterGraph.from_mapping(document)


def test_a_derivation_cycle_is_refused_and_names_its_members(document: dict):
	"""A cycle among derived parameters has no evaluation order."""
	document["equations"]["marginal_cost"]["rhs"] = "lcoe_usd_per_mwh"
	document["equations"]["marginal_cost"]["parameters"] = [
		"marginal_cost_usd_per_mwh",
		"lcoe_usd_per_mwh",
	]
	graph = ParameterGraph.from_mapping(document)
	with pytest.raises(CycleError) as caught:
		graph.order()
	message = str(caught.value)
	assert "lcoe_usd_per_mwh" in message and "marginal_cost_usd_per_mwh" in message


def test_an_edge_naming_a_non_parameter_is_refused(document: dict):
	document["relationships"][0]["target"] = "not_a_parameter"
	with pytest.raises(GraphError, match="not a parameter"):
		ParameterGraph.from_mapping(document)


def test_an_equation_whose_arithmetic_names_an_unlisted_parameter_is_refused(document: dict):
	"""The metadata must match the arithmetic, or the metadata is decoration."""
	document["equations"]["marginal_cost"]["parameters"] = [
		"marginal_cost_usd_per_mwh",
		"fuel_price_usd_per_mwh",
	]
	with pytest.raises(GraphError, match="does not list them"):
		ParameterGraph.from_mapping(document)


def test_an_equation_listing_a_parameter_it_does_not_use_is_refused(document: dict):
	"""A declared coupling the engine would never apply is a lie about the graph."""
	document["equations"]["marginal_cost"]["parameters"] = [
		"marginal_cost_usd_per_mwh",
		"fuel_price_usd_per_mwh",
		"carbon_cost_usd_per_mwh",
		"discount_rate",
	]
	with pytest.raises(GraphError, match="does not name them"):
		ParameterGraph.from_mapping(document)


def test_a_derived_parameter_declaring_a_default_is_refused(document: dict):
	document["parameters"]["crf"]["default"] = 0.1
	with pytest.raises(Exception, match="must not carry a default"):
		ParameterGraph.from_mapping(document)


def test_a_default_outside_its_own_range_is_refused(document: dict):
	document["parameters"]["discount_rate"]["default"] = 5.0
	with pytest.raises(Exception, match="outside its declared range"):
		ParameterGraph.from_mapping(document)


def test_an_inequality_cannot_determine_a_variable(document: dict):
	"""An inequality bounds a value; only an equality fixes one."""
	document["equations"]["reserve_margin"]["determined_variables"] = ["firm_capacity_mw"]
	with pytest.raises(Exception, match="cannot determine"):
		ParameterGraph.from_mapping(document)


def test_an_unenumerated_system_is_refused(document: dict):
	document["equations"]["marginal_cost"]["system"] = "invented_system"
	graph = ParameterGraph.from_mapping(document)
	with pytest.raises(ValueError, match="not one of"):
		systems_of(graph.equations)


def test_a_declared_relationship_list_that_drifted_is_reported(document: dict):
	"""A declared list is a document; when it disagrees with the edges it lies."""
	document["parameters"]["discount_rate"]["affects"] = ["crf", "lcoe_usd_per_mwh"]
	graph = ParameterGraph.from_mapping(document)
	issues = graph.structure_issues()
	assert any("discount_rate.affects declares" in issue for issue in issues), issues


# ---------------------------------------------------------------------------
# The library register
# ---------------------------------------------------------------------------


def test_coverage_names_the_systems_that_are_not_modelled(graph: ParameterGraph):
	"""An unmodelled system is a finding, not silence.

	"affordability is not modelled" and "affordability is modelled and nothing
	violates it" read identically from a report that lists no violations. The
	shipped graph now models every system, so the finding set is empty -- and
	that is a claim worth asserting, because it is the one that regresses
	silently if a system's equations are deleted.
	"""
	assert coverage(graph.equations) == [], coverage(graph.equations)
	modelled = {system for system, equations in systems_of(graph.equations).items() if equations}
	assert modelled == set(SYSTEM_IDS), sorted(set(SYSTEM_IDS) - modelled)


def test_every_system_has_equations_and_a_finding_is_what_an_empty_one_produces(
	graph: ParameterGraph, document: dict
):
	"""The register reports absence, which is why it is computed and not inferred.

	Deleting a system's equations must produce a finding naming it, or the
	register cannot distinguish "not modelled" from "modelled and clean".
	"""
	document["equations"] = {
		key: value
		for key, value in document["equations"].items()
		if value["system"] != "affordability"
	}
	# The edges citing those equations have to go too, or the graph refuses to
	# load for naming an equation it no longer holds -- which is the load-time
	# check working, not the register under test.
	dropped = {
		key
		for key, value in yaml.safe_load(PRG_PATH.read_text())["equations"].items()
		if value["system"] == "affordability"
	}
	document["relationships"] = [
		edge for edge in document["relationships"] if edge["equation_id"] not in dropped
	]
	stripped = ParameterGraph.from_mapping(document)
	uncovered = coverage(stripped.equations)
	assert any(entry.startswith("affordability:") for entry in uncovered), uncovered
	assert len(uncovered) == 1, uncovered


# ---------------------------------------------------------------------------
# The service layer
# ---------------------------------------------------------------------------


def test_the_summary_reports_the_registers(graph: ParameterGraph):
	summary = graph_summary(graph)
	assert summary["parameters"] == len(graph.nodes)
	assert summary["equations"] == len(graph.equations)
	assert summary["derived"] == len(graph.order())
	assert summary["feedback_loops"], "the summary lost the loop"
	# Every system is modelled, so the register is empty -- and empty is the
	# assertion, because a system that quietly lost its equations is exactly
	# what this key exists to make visible.
	assert summary["unmodelled_systems"] == []
	assert summary["systems_declared"] == len(summary["systems"])
	assert summary["structure_issues"] == []


def test_check_scenario_propagates_before_it_validates(graph: ParameterGraph, defaults: dict):
	"""The derived parameters are computed first, so a clean set passes.

	A check that validated the numbers as handed in would report every derived
	parameter as a violation whenever the caller had not computed them.
	"""
	result = check_scenario(dict(defaults), graph)
	assert result.consistent, result.violations
	assert not result.violations


def test_propagate_change_reports_what_moved(graph: ParameterGraph, defaults: dict):
	"""The difference is between two solved sets, not within one propagation."""
	out = propagate_change(
		dict(defaults), {"carbon_price_usd_per_tco2": 200.0}, graph
	)
	assert "marginal_cost_usd_per_mwh" in out["changed"]
	assert out["changed"]["marginal_cost_usd_per_mwh"] > 0
	assert out["changed"]["carbon_price_usd_per_tco2"] == pytest.approx(150.0)
	assert out["loops"] and out["loops"][0]["iterations"] > 0


def test_propagate_change_refuses_a_computed_parameter(graph: ParameterGraph, defaults: dict):
	"""Setting a derived parameter is the inconsistency the graph exists to refuse."""
	with pytest.raises(ValueError, match="computed by the graph"):
		propagate_change(dict(defaults), {"marginal_cost_usd_per_mwh": 999.0}, graph)


def test_propagate_change_refuses_an_unknown_parameter(graph: ParameterGraph, defaults: dict):
	with pytest.raises(ValueError, match="not parameters"):
		propagate_change(dict(defaults), {"no_such_knob": 1.0}, graph)


def test_describe_renders_the_relation(graph: ParameterGraph):
	"""An inequality printed with ``=`` misstates half the library."""
	equality = describe(graph.equation("marginal_cost"))
	assert "=" in equality and "≥" not in equality and "≤" not in equality

	inequality = describe(graph.equation("reserve_margin"))
	assert "≥" in inequality, inequality
	assert " = " not in inequality, inequality

	assert "\\geq" in describe(graph.equation("reserve_margin"), as_="latex")
	assert ">=" in describe(graph.equation("reserve_margin"), as_="source")


def test_evaluate_is_the_module_level_entry_point():
	"""The free function and the method agree, since one calls the other."""
	expression = parse("a * b + 1")
	values = {"a": 2.0, "b": 3.0}
	assert evaluate(expression, values) == expression.eval(values) == 7.0


# ---------------------------------------------------------------------------
# The solver's bracket is not the parameter's admissible range
# ---------------------------------------------------------------------------


def test_a_value_outside_its_range_is_reported_rather_than_refused(
	graph: ParameterGraph, defaults: dict
):
	"""A computable value outside the admissible range is a finding, not a crash.

	`range` is the set a parameter is admissible over; the solver's bracket is
	where the root might be. For a ratio those are different sets. A $900
	tariff drives the debt service coverage to about 30 -- a real answer about
	an unfinanceable-by-construction scenario -- and a graph that raises here
	instead of reporting turns "why is this scenario bad" into a traceback.

	The failure this guards is not hypothetical: the first version of the
	widened library raised exactly this way, and the tariff that produced it is
	the affordability system's own subject matter.
	"""
	scoped = dict(defaults)
	scoped["tariff_usd_per_mwh"] = 900.0
	result = graph.propagate(scoped)
	# Solved, not pinned to a bound: the equation's actual answer.
	assert result.values["project_gearing_dscr"] > 20.0
	assert graph.range_excursions()["project_gearing_dscr"] == pytest.approx(
		result.values["project_gearing_dscr"], rel=1e-9
	)
	check = check_scenario(scoped, graph)
	assert not check.consistent
	assert any(
		v.equation_id == "project_gearing_dscr_out_of_range"
		for v in check.violations
	), [str(v) for v in check.violations]
	# The downstream identities are computed from the *true* value, so a
	# scenario reported as out of range is still fully described.
	assert check.excursions["project_gearing_dscr"] == pytest.approx(
		result.values["project_gearing_dscr"], rel=1e-9
	)


def test_a_range_excursion_does_not_survive_into_the_next_scenario(
	graph: ParameterGraph, defaults: dict
):
	"""The register is cleared per propagation, or it reports a stale finding.

	A finding left over from the previous scenario would be attributed to the
	next one, which is worse than no finding at all: the report would name a
	parameter the current scenario keeps well inside its range.
	"""
	scoped = dict(defaults)
	scoped["tariff_usd_per_mwh"] = 900.0
	graph.propagate(scoped)
	assert graph.range_excursions()
	graph.propagate(defaults)
	assert graph.range_excursions() == {}
	assert check_scenario(defaults, graph).consistent


def test_an_equation_with_no_root_at_all_is_still_an_error(
	graph: ParameterGraph, defaults: dict
):
	"""Widening is not a licence to return a bound and call it an answer.

	A residual that does not change sign anywhere is unsolvable, and a solver
	that answered anyway would be inventing a value the equation does not fix.
	"""
	from alea.prg.dsl import parse

	scoped = dict(defaults)
	# `x**2 + 1` has no real root, so no bracket contains one.
	residual = parse("project_gearing_dscr ** 2 + 1")
	assert graph._widen(residual, "project_gearing_dscr", scoped, (-20.0, 20.0)) is None


# ---------------------------------------------------------------------------
# The DSL's door: `alea expr`
# ---------------------------------------------------------------------------


def _expr(*args: str):
	from typer.testing import CliRunner

	from alea.cli import app

	return CliRunner().invoke(app, ["expr", *args])


def test_the_expr_commands_are_reachable():
	"""The DSL had no entry point; a formula language nobody can type is a library.

	Asserted through the runner rather than by importing the functions, because
	the defect class is registration: a command defined and never mounted is
	unreachable from the shell, and nothing else in the suite would notice.
	"""
	for command in ("render", "eval", "diff", "simplify", "solve"):
		result = _expr(command, "--help")
		assert result.exit_code == 0, f"{command}: {result.output}"


def test_render_evaluates_nothing_and_eval_renders_nothing():
	"""The three lives of a formula, each reachable without the others.

	Rendering a formula with free parameters must succeed -- it is a
	*relation*, and demanding values for it would make the general form
	unquotable. Evaluating one with free parameters must fail, because a
	relation has no single value.
	"""
	rendered = _expr("render", "capex * crf + fuel", "--as", "unicode")
	assert rendered.exit_code == 0, rendered.output
	assert "capex" in rendered.stdout

	unbound = _expr("eval", "capex * crf + fuel", "--set", "capex=1200")
	assert unbound.exit_code == 2, unbound.output

	bound = _expr("eval", "capex * crf + fuel", "--set", "capex=1200", "--set", "crf=0.1", "--set", "fuel=40")
	assert bound.exit_code == 0, bound.output
	assert float(bound.stdout.strip()) == pytest.approx(160.0)


def test_the_cli_differentiates_and_solves_the_same_objects_the_kernel_does():
	"""The door and the kernel agree, because there is one implementation."""
	derivative = _expr("diff", "x ** 3 + 2 * x", "x", "--as", "source")
	assert derivative.exit_code == 0, derivative.output
	assert derivative.stdout.strip() == parse("3 * x ** 2 + 2").source()

	solved = _expr(
		"solve", "lcoe - (capex * crf + fuel)", "capex",
		"--bracket", "0,5000",
		"--set", "lcoe=100", "--set", "crf=0.1", "--set", "fuel=40",
	)
	assert solved.exit_code == 0, solved.output
	assert float(solved.stdout.strip()) == pytest.approx(600.0)


def test_a_solve_with_no_root_exits_non_zero_with_the_bracket_named():
	"""A solve that cannot answer must say so, not print a bound as the answer."""
	result = _expr("solve", "x ** 2 + 1", "x", "--bracket", "-10,10")
	assert result.exit_code == 1
	assert "no root" in result.output


def test_a_list_of_hourly_values_evaluates_as_an_array():
	"""A CSV column is a list, and `eval_array` must accept one.

	The signature says ``Any``; a caller holding a list of hourly values got
	`TypeError: can't multiply sequence by non-int of type 'float'` from inside
	the evaluator, about a value the signature invited them to pass.
	"""
	expression = parse("x * 2 + 1")
	from_list = expression.eval_array({"x": [1.0, 2.0, 3.0]})
	assert list(from_list) == [3.0, 5.0, 7.0]
	# And a tuple, which is what a row of a CSV reader is.
	assert list(expression.eval_array({"x": (1.0, 2.0, 3.0)})) == [3.0, 5.0, 7.0]


def test_a_parameters_times_profile_broadcasts():
	"""The shape a parameter-times-profile equation needs, which is why it is not a float."""
	import numpy as np

	profile = np.array([0.2, 0.4, 0.6, 0.8])
	value = parse("capacity * profile").eval_array({"capacity": 100.0, "profile": profile})
	assert list(value) == [20.0, 40.0, 60.0, 80.0]


# ---------------------------------------------------------------------------
# The specification's own enumeration
# ---------------------------------------------------------------------------


def test_the_library_holds_every_system_the_specification_enumerates():
	"""The register is checked against the document, not against itself.

	The first version of this library held twelve systems and reported "every
	system modelled" -- about a document that enumerates twenty. A coverage
	register whose own enumeration is short is the declared-is-not-produced
	defect wearing the register's clothes: it cannot find the systems it never
	knew about, so it reports full coverage of a specification it stopped
	reading. Reading the headings off `params-prg1.md` is what makes the claim
	checkable.
	"""
	from alea.prg.library import (
		SPEC_SYSTEM_COUNT,
		SPEC_TO_SYSTEM,
		spec_systems,
		unclaimed_spec_systems,
	)

	enumerated = spec_systems()
	assert len(enumerated) == SPEC_SYSTEM_COUNT, sorted(enumerated)
	assert unclaimed_spec_systems() == [], unclaimed_spec_systems()
	# Every mapping target is a system that exists, and every system is
	# claimed by at least one heading: both directions, or the mapping is a
	# document that agrees with itself.
	assert set(SPEC_TO_SYSTEM.values()) <= set(SYSTEM_IDS)
	assert set(SYSTEM_IDS) <= set(SPEC_TO_SYSTEM.values())


def test_every_system_that_is_declared_has_equations(graph: ParameterGraph):
	"""Declaring a system is not modelling it.

	The four systems added last -- water, employment, health, PPA -- were
	declared in the register before they had a single equation, and the
	coverage register reported them as modelled. That is the same defect one
	level down from the count, and this is the assertion that catches it.
	"""
	modelled = {
		system for system, equations in systems_of(graph.equations).items() if equations
	}
	assert modelled == set(SYSTEM_IDS), sorted(set(SYSTEM_IDS) - modelled)
	assert coverage(graph.equations) == []

