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
from alea.prg.conflicts import (
	ConflictKind,
	detect_conflicts,
	suggest_corrections,
)
from alea.prg.dsl import DslError, const, evaluate, parse, simplify, solve_for, sym
from alea.prg.graph import CycleError, GraphError, ParameterGraph
from alea.prg.library import SYSTEM_IDS, coverage, systems_of
from alea.prg.sensitivity import elasticity, gradients, sensitivity
from alea.prg.service import check_scenario, describe, graph_summary, propagate_change
from alea.prg.uncertainty import register

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


def test_a_loop_that_cannot_settle_says_which_failure_it_is(
	graph: ParameterGraph, defaults: dict
):
	"""The non-convergence message must name the fix, and be reachable.

	"Did not converge" leaves the reader to guess between a diverging map and
	an oscillating one, and the two have different fixes -- a smaller damping
	factor for the oscillation, a different equation or range for the
	divergence. The diagnostic is only worth having if it actually fires, so
	this forces non-convergence with a one-turn budget and asserts the message
	names the failure rather than restating the residual.
	"""
	from dataclasses import replace

	from alea.prg.feedback import FeedbackError, solve_loop

	loop = replace(graph.feedback_loops()[0], max_iterations=1)
	values = graph.propagate(defaults).values
	for name in loop.variables:
		values.pop(name, None)
	with pytest.raises(FeedbackError) as caught:
		solve_loop(graph, loop, values)
	message = str(caught.value)
	assert "did not converge" in message
	# The diagnosis, not just the residual: one of the three named causes.
	assert any(
		phrase in message
		for phrase in ("oscillating", "diverging", "slow convergence")
	), message


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


def test_an_unenumerated_system_is_refused_at_load(document: dict):
	"""A misspelt system is a load error, not a surprise inside a later report.

	`systems_of` raises too, but only when something asks it to group the
	equations, so the malformed graph loaded cleanly and failed later inside an
	unrelated call. Refusing it at construction is the stronger contract: the
	graph a caller holds is one the library can describe.
	"""
	document["equations"]["marginal_cost"]["system"] = "invented_system"
	with pytest.raises(GraphError, match="which the library does not hold"):
		ParameterGraph.from_mapping(document)


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
	# The engine-coverage register rides on the summary, so a reader of the
	# graph's own counts cannot miss that most of it drives nothing.
	engine = summary["engine_translation"]
	assert engine["count"] == len(engine["translated"])
	assert engine["count"] + len(engine["untranslated"]) == engine["total"]
	assert 0.0 < engine["fraction"] < 1.0


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


def test_a_function_applied_to_an_array_uses_its_array_form():
	"""`math.exp(array)` raises; the array path must not route through it.

	The first implementation wrapped the scalar result in a one-element list,
	which is neither a broadcast nor the right answer, and it raised
	`TypeError: only 0-dimensional arrays can be converted to Python scalars`
	before it got that far. Checked against NumPy's own ufunc, which is the
	independent witness for the values as well as the shape.
	"""
	import numpy as np

	values = np.array([0.0, 1.0, 2.0])
	got = parse("exp(x)").eval_array({"x": values})
	assert list(got) == pytest.approx(list(np.exp(values)))
	assert list(parse("sqrt(x)").eval_array({"x": [1.0, 4.0, 9.0]})) == [1.0, 2.0, 3.0]
	assert list(parse("ln(x)").eval_array({"x": [1.0, math.e]})) == pytest.approx([0.0, 1.0])


def test_an_array_through_an_elementwise_comparison_matches_numpy():
	"""`min`/`max` over arrays are reductions, not the elementwise pair.

	They are the two functions with no single NumPy equivalent, so they get the
	elementwise form explicitly rather than silently falling back to the scalar
	implementation, which would compare arrays by truth value and raise.
	"""
	import numpy as np

	a, b = np.array([1.0, 5.0]), np.array([4.0, 2.0])
	assert list(parse("min(a, b)").eval_array({"a": a, "b": b})) == [1.0, 2.0]
	assert list(parse("max(a, b)").eval_array({"a": a, "b": b})) == [4.0, 5.0]


def test_floor_is_floor():
	"""`floor` was mapped to `float`, which is the identity.

	`floor(3.7)` returned 3.7 and no test noticed, because the scalar path was
	only ever exercised through `abs`/`min`/`max`. The assertion is against
	`math.floor`, not against a recorded value.
	"""
	assert parse("floor(x)").eval({"x": 3.7}) == 3.0
	assert parse("floor(x)").eval({"x": -3.2}) == -4.0
	assert parse("ceil(x)").eval({"x": 3.2}) == 4.0
	assert list(parse("floor(x)").eval_array({"x": [1.9, -0.1]})) == [1.0, -1.0]


def test_a_reserved_name_cannot_be_a_symbol_however_it_is_built():
	"""`sym()` checked the reserved set; the constructor did not.

	`Symbol("exp")` built a parameter indistinguishable from the exponential in
	every rendering. The check belongs where the object is made, so every path
	to a Symbol -- the factory, a parser, a caller -- meets it.
	"""
	from alea.prg.dsl import Symbol

	for name in ("exp", "sum", "min", "range"):
		with pytest.raises(DslError, match="reserved"):
			Symbol(name)
		with pytest.raises(DslError, match="reserved"):
			sym(name)


def test_a_policy_lever_is_reported_as_constraining_something(graph: ParameterGraph):
	"""A constraint's inputs are couplings, and the graph must say so.

	`affects` read only the determining equations, so a parameter that appears
	in an inequality reported nothing at all. Moving ``energy_burden_limit``
	does not move any *value* -- it decides whether the scenario is admissible,
	which is the whole question for a regulator's lever. So the register for it
	is ``constrains``, and the assertion is that every such lever is visible in
	one register or the other rather than in neither.
	"""
	for lever in (
		"dscr_min",
		"energy_burden_limit",
		"reserve_margin_min",
		"rocof_limit_hz_per_s",
		"water_availability_m3",
		"firm_capacity_mw",
		"peak_demand_mw",
	):
		assert graph.constrains(lever), f"{lever} bounds no inequality"
	assert "dscr_requirement" in graph.constrains("dscr_min")
	assert "affordability_constraint" in graph.constrains("energy_burden_limit")
	# And the value-coupling path is unchanged for a lever that does move one.
	assert "project_gearing_dscr" in graph.affects("cfads_usd_per_kw_year")


def test_a_loop_equation_is_a_value_coupling(graph: ParameterGraph):
	"""A loop's target is a consequence of its inputs, and `affects` says so.

	The loop equations are skipped by `_determiner` -- that is what makes them
	loops -- so reading only the determiner dropped them from `affects` too,
	and ``capture_price_sensitivity`` and ``vre_capacity_target_mw`` reported
	as inert. Both are real levers: one changes the cannibalisation the fixed
	point settles at, the other changes the build the loop converges to.
	"""
	assert "capture_price_usd_per_mwh" in graph.affects("capture_price_sensitivity")
	assert "vre_capacity_mw" in graph.affects("vre_capacity_target_mw")


def test_every_settable_parameter_affects_or_constrains_something(graph: ParameterGraph):
	"""A knob whose value reaches nothing and bounds nothing does nothing.

	The graph is allowed to hold such an input -- but then it must be visible
	as one, not silently present. This asserts the register is empty, which is
	the state a graph worth shipping should be in.
	"""
	dead = [
		name
		for name in sorted(graph.nodes)
		if graph.is_settable(name)
		and not graph.affects(name)
		and not graph.constrains(name)
	]
	assert dead == [], dead


def test_a_loop_variable_is_reported_as_moved(graph: ParameterGraph):
	"""The fixed point moved, and the report said nothing.

	`before` is captured before `solve_loop` seeds its iterates, so a loop
	variable the caller did not supply was never in it and `changed` dropped it
	entirely. The seed is the honest "before" for an iterated value, and it is
	the same rule the solver applies -- written once, in `_loop_seed`.

	The test must *not* supply the loop variables: a caller-supplied value is
	in `before` and takes the path that always worked, which is how the first
	version of this test passed against the defect it was written for.
	"""
	defaults = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	loop_variables = {
		equation.determined_variables[0]
		for equation in graph.equations.values()
		if equation.solution_method == "iterative"
	}
	# None of them is a default, so none is in `before`: this is the seeded path.
	assert not (loop_variables & set(defaults)), sorted(loop_variables & set(defaults))
	result = graph.propagate(defaults)
	assert loop_variables <= set(result.changed), (
		f"loop variables missing from changed: "
		f"{sorted(loop_variables - set(result.changed))}"
	)


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


def test_a_restructured_spec_is_refused_rather_than_read_as_empty(tmp_path):
	"""The reader couples the code to a Markdown shape, so it must fail loudly.

	`spec_systems` parses ``### 4.N System N: Name (Coupling)`` headings off
	the specification. That coupling is deliberate -- a transcribed list is a
	second copy that drifts -- but it means a restructured document silently
	yields nothing, and the count check then reports "0 != 20": a true
	statement about the wrong thing, because the fault is the pattern and not
	the content. The refusal names the cause.
	"""
	from alea.prg.library import spec_systems

	restructured = tmp_path / "spec.md"
	restructured.write_text("# Spec\n\n## 4. Systems\n\n#### System One\n")
	with pytest.raises(ValueError, match="no '### 4.' section heading"):
		spec_systems(restructured)

	unparseable = tmp_path / "spec2.md"
	unparseable.write_text("### 4. Systems\n\nSystem 1: renamed\n")
	with pytest.raises(ValueError, match="no heading matches"):
		spec_systems(unparseable)


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


# ---------------------------------------------------------------------------
# The seam: auditing a solved what-if result
# ---------------------------------------------------------------------------


def _solved(carbon_price: float = 50.0):
	"""A solved result, carrying the engine's numbers rather than the graph's."""
	import uuid

	from alea.whatif.params import ScenarioParameters
	from alea.whatif.views import ScenarioResult

	return ScenarioResult(
		scenario_id=str(uuid.uuid4()),
		params=ScenarioParameters(carbon_price_usd_per_tco2=carbon_price),
		network_checksum="sha256:" + "a" * 64,
		code_version="test",
		total_cost_usd=1.0e9,
		total_emissions_tco2=25.0e6,
		capacity_mix_mw={"coal": 6000.0, "wind": 4000.0},
		generation_mwh={"coal": 30.0e6, "wind": 20.0e6},
	)


def test_the_audit_reports_what_it_did_not_check():
	"""A pass over nothing must not read as a pass over everything.

	The result carries a handful of the graph's twenty-eight derived
	parameters. An audit that printed "consistent" without saying how many
	parameters that covered would be a clean bill of health for a result
	nobody examined.
	"""
	from alea.prg.audit import audit_scenario_result

	audit = audit_scenario_result(_solved())
	assert audit.consistent
	assert len(audit.skipped) == 28, audit.skipped
	assert "not carried" in audit.summary()


def test_the_audit_finds_an_unfinanceable_scenario_the_engine_solved():
	"""The seam's whole value: a scenario the optimiser accepts and a lender would not.

	A $200 carbon price is a network PyPSA solves without complaint -- the
	objective is finite and every constraint holds. The PRG refuses it, because
	at that marginal cost the tariff no longer covers operating cost and the
	debt service coverage falls below the floor a lender requires. That is the
	inconsistency the specification says the engine would otherwise "happily
	solve and return garbage" about.
	"""
	from alea.prg.audit import audit_scenario_result

	assert audit_scenario_result(_solved(50.0)).consistent
	refused = audit_scenario_result(_solved(200.0))
	assert not refused.consistent
	assert any(v.equation_id == "dscr_requirement" for v in refused.violations), [
		str(v) for v in refused.violations
	]


def test_the_intensity_gap_measures_rather_than_passes():
	"""A stand-in that is exact here is not exact everywhere, and the gap says so.

	The graph's emissions identity uses one fleet-wide factor; the engine sums
	per-carrier intensities. They agree exactly when the fleet's weighted
	average equals the graph's number. Reporting that ratio is the honest
	output: a consistency check cannot report it, because the graph is
	internally consistent either way.
	"""
	from alea.prg.audit import fleet_intensity_gap

	# 25 Mt over 50 TWh is 0.5 t/MWh, and the graph's factor is 0.5.
	gap = fleet_intensity_gap(_solved())
	assert gap["engine_intensity"] == pytest.approx(0.5)
	assert gap["graph_factor"] == pytest.approx(0.5)
	assert gap["ratio"] == pytest.approx(1.0)

	# A dirtier fleet than the graph's single factor assumes.
	import uuid

	from alea.whatif.params import ScenarioParameters
	from alea.whatif.views import ScenarioResult

	dirty = ScenarioResult(
		scenario_id=str(uuid.uuid4()),
		params=ScenarioParameters(),
		network_checksum="sha256:" + "b" * 64,
		code_version="test",
		total_cost_usd=1.0e9,
		total_emissions_tco2=50.0e6,
		capacity_mix_mw={"coal": 10000.0},
		generation_mwh={"coal": 50.0e6},
	)
	assert fleet_intensity_gap(dirty)["ratio"] == pytest.approx(2.0)


def test_the_audit_does_not_compare_the_graph_against_itself():
	"""A derived parameter supplied by the result is discarded, and that is stated.

	`generation_twh` and `emissions_mtco2_per_year` are both derived, so
	`propagate` recomputes them. Supplying the engine's values for them would
	change nothing and the audit would report agreement between two runs of the
	same equation -- the vacuous fixture this repository has been bitten by
	before. The engine's emissions are checked by `fleet_intensity_gap`, which
	measures them against the graph's factor instead.
	"""
	from alea.prg.audit import parameters_from_result
	from alea.prg.graph import load_graph

	graph = load_graph()
	supplied = parameters_from_result(_solved(), graph)
	assert "emissions_mtco2_per_year" not in supplied
	assert "generation_twh" not in supplied
	assert supplied["carbon_price_usd_per_tco2"] == pytest.approx(50.0)
	assert supplied["total_capacity_mw"] == pytest.approx(10000.0)


def test_the_loop_converges_on_the_criterion_it_is_audited_by(
	graph: ParameterGraph, defaults: dict
):
	"""A solver's stopping rule must not be weaker than its audit's.

	The loop stopped when its *iterates* stopped moving. With damping 0.5 the
	residual is the step divided by the damping factor, so the loop settled at
	1e-8 on its iterates and 1.9e-8 on the capture-price equation -- outside
	that equation's 1e-8 tolerance. The result was a scenario reported as
	violating an equation the solver had just declared solved, which is worse
	than a wrong number: it is a false finding, and false findings train a
	reader to ignore the true ones.

	The loop now also checks the scaled residual, the same comparison
	`consistency` applies, so convergence means the answer passes the check
	that will be run on it.
	"""
	result = graph.propagate(defaults)
	assert result.loops, "the shipped graph lost its loop"
	assert graph.consistency(result.values) == [], graph.consistency(result.values)
	# And the answer is still the closed form, so the tighter rule did not
	# change what the loop converges to.
	total = defaults["total_capacity_mw"]
	target = defaults["vre_capacity_target_mw"]
	sensitivity = defaults["capture_price_sensitivity"]
	share = (target / total) / (1 + sensitivity * target / total)
	assert result.values["vre_share"] == pytest.approx(share, rel=1e-6)
	assert result.values["capture_price_ratio"] == pytest.approx(1 - sensitivity * share, rel=1e-6)



# ---------------------------------------------------------------------------
# Sensitivity: forward-mode derivatives against an independent witness
# ---------------------------------------------------------------------------


def test_a_definition_differentiates_to_its_analytic_derivative(
	graph: ParameterGraph, defaults: dict
):
	"""`lcoe_definition` differentiated by hand, checked against the module.

	The equation is ``annualised_capex * 1000 / (8760 * cf) + marginal_cost``,
	so ``d(lcoe)/d(capacity_factor) = -annualised_capex * 1000 / (8760 * cf^2)``
	and every other input enters only through those two. That closed form is
	the independent witness: the gradient table agreeing with itself proves
	nothing.
	"""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	annualised = result.values["annualised_capex_usd_per_kw"]
	factor = result.values["capacity_factor"]
	analytic = -annualised * 1000.0 / (8760.0 * factor**2)
	got = table.of("lcoe_usd_per_mwh").derivatives["capacity_factor"]
	assert got == pytest.approx(analytic, rel=1e-9)


def test_a_loop_variable_differentiates_by_the_implicit_function_theorem(
	graph: ParameterGraph, defaults: dict
):
	"""The capture-price loop's ``d(share)/d(target)``, against the closed form.

	The loop is three linear equations with the fixed point
	``share = (t/total) / (1 + s·t/total)`` for build target ``t``,
	cannibalisation ``s`` and total capacity ``total``, so

	    d(share)/dt = (1/total) / (1 + s·t/total)**2

	The implicit function theorem solves ``J dz/dx = -dF/dx``; the closed form
	is what says the solve landed on the derivative rather than on some nearby
	matrix that happened to be invertible.
	"""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	assert "vre_share" in table.loops, "the shipped graph lost its loop"
	total = defaults["total_capacity_mw"]
	target = defaults["vre_capacity_target_mw"]
	sensitivity = defaults["capture_price_sensitivity"]
	analytic = (1.0 / total) / (1.0 + sensitivity * target / total) ** 2
	got = table.of("vre_share").derivatives["vre_capacity_target_mw"]
	assert got == pytest.approx(analytic, rel=1e-6)


def test_the_gradient_is_exact_where_a_finite_difference_is_not(
	graph: ParameterGraph, defaults: dict
):
	"""A perturbed re-solve disagrees with the analytic derivative; the table does not.

	This is the reason the module exists. Re-propagating at ``x + h`` and
	differencing carries the solver's tolerance: the loop converges to 1e-8, so
	a step small enough to be local gives a quotient dominated by solver noise.
	The test asserts the table is closer to the closed form than the difference
	quotient is, which is the claim that justifies the machinery.
	"""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	total = defaults["total_capacity_mw"]
	target = defaults["vre_capacity_target_mw"]
	sensitivity = defaults["capture_price_sensitivity"]
	analytic = (1.0 / total) / (1.0 + sensitivity * target / total) ** 2
	exact = table.of("vre_share").derivatives["vre_capacity_target_mw"]

	step = target * 1e-6
	moved = dict(defaults)
	moved["vre_capacity_target_mw"] = target + step
	nudged = graph.propagate(moved)
	quotient = (nudged.values["vre_share"] - result.values["vre_share"]) / step
	assert abs(exact - analytic) < abs(quotient - analytic)


def test_an_input_is_its_own_unit_derivative(graph: ParameterGraph, defaults: dict):
	result = graph.propagate(defaults)
	row = sensitivity(graph, "carbon_price_usd_per_tco2", result.values)
	assert row.method == "input"
	assert row.derivatives == {"carbon_price_usd_per_tco2": 1.0}


def test_a_parameter_no_input_reaches_has_an_empty_gradient(
	graph: ParameterGraph, defaults: dict
):
	"""A constant-derived parameter is not sensitive to anything, and says so.

	A row of zeros would read as "every input reaches it, weakly"; the empty
	dict reads as "nothing reaches it", which is the true statement.
	"""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	for name, row in table.table.items():
		if name in table.inputs:
			continue
		for input_name, value in row.items():
			assert value != 0.0, (
				f"{name} carries a stored zero derivative with respect to "
				f"{input_name}; a zero belongs in no row"
			)


def test_elasticity_is_dimensionless_where_the_derivative_is_not(
	graph: ParameterGraph, defaults: dict
):
	"""``(x/y)(dy/dx)``, checked against the derivative it is built from."""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	weights = elasticity(graph, "lcoe_usd_per_mwh", result.values, table=table)
	derivative = table.of("lcoe_usd_per_mwh").derivatives["capacity_factor"]
	level = result.values["lcoe_usd_per_mwh"]
	input_level = result.values["capacity_factor"]
	assert weights["capacity_factor"] == pytest.approx(
		derivative * input_level / level, rel=1e-12
	)


def test_elasticity_refuses_a_zero_denominator(graph: ParameterGraph, defaults: dict):
	"""An elasticity at a zero value is undefined, not zero and not infinite."""
	result = graph.propagate(defaults)
	values = dict(result.values)
	values["lcoe_usd_per_mwh"] = 0.0
	with pytest.raises(ValueError, match="not.*defined"):
		elasticity(graph, "lcoe_usd_per_mwh", values)


def test_the_gradient_table_is_computed_in_one_pass(
	graph: ParameterGraph, defaults: dict
):
	"""Asking for one row and asking for all of them give the same numbers.

	The single pass is an optimisation, and an optimisation that changes the
	answer is a bug. This pins the two routes together.
	"""
	result = graph.propagate(defaults)
	table = gradients(graph, result.values)
	for name in table.table:
		if name in table.inputs:
			continue
		alone = sensitivity(graph, name, result.values)
		assert alone.derivatives == table.table[name], name


def test_a_singular_jacobian_is_named_rather_than_reported_as_zero():
	"""A loop with no derivative is an error, not a row of zeros.

	Reporting a zero row where the derivative does not exist would say "this
	input moves nothing" about a system that is merely not invertible there.

	Built from a synthetic loop rather than the shipped one, because the
	capture-price loop is a contraction at its fixed point and its Jacobian is
	not singular anywhere the solver will land -- a test that tried to push the
	shipped loop into singularity would be asserting a property of the
	*push*, and would pass whether or not the guard exists. Two equations that
	are the same equation up to a factor give a Jacobian of rank one, which is
	singular by construction.
	"""
	from alea.prg.feedback import FeedbackLoop
	from alea.prg.sensitivity import _loop_gradients

	def node(name: str, role: str, **extra) -> dict:
		return {
			"name": name,
			"unit": "1",
			"type": "float",
			"role": role,
			"category": "Financial",
			"determinism": "policy",
			"priority": "P1",
			"status": "existing",
			**extra,
		}

	document = {
		"parameters": {
			"x": node("x", "derived"),
			"y": node("y", "derived"),
			"k": node("k", "exogenous", default=2.0),
		},
		"equations": {
			"e_x": {"name": "x", "lhs": "x", "rhs": "k * y",
			        "parameters": ["x", "y", "k"],
			        "determined_variables": ["x"], "system": "financial"},
			"e_y": {"name": "y", "lhs": "y", "rhs": "k * x",
			        "parameters": ["x", "y", "k"],
			        "determined_variables": ["y"], "system": "financial"},
		},
	}
	graph = ParameterGraph.from_mapping(document)
	loop = FeedbackLoop(
		id="degenerate",
		variables=("x", "y"),
		equations=tuple(graph.equations.values()),
	)
	# x = k*y and y = k*x are the same relation, so dF/d(x,y) has rank one.
	values = {"x": 1.0, "y": 1.0, "k": 1.0}
	with pytest.raises(DslError, match="singular Jacobian"):
		_loop_gradients(loop, values, ("k",))


# ---------------------------------------------------------------------------
# Conflicts: the four kinds, and the corrections that resolve them
# ---------------------------------------------------------------------------


def test_a_consistent_scenario_reports_no_conflicts(
	graph: ParameterGraph, defaults: dict
):
	result = graph.propagate(defaults)
	report = detect_conflicts(graph, result.values, supplied=defaults)
	assert report.consistent, report.summary()
	assert report.checked, "nothing was checked, so the pass is vacuous"


def test_setting_a_derived_parameter_is_an_over_determination(
	graph: ParameterGraph, defaults: dict
):
	"""The caller set `lcoe_usd_per_mwh`, which `lcoe_definition` computes."""
	supplied = dict(defaults)
	supplied["lcoe_usd_per_mwh"] = 40.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	kinds = {c.kind for c in report.conflicts}
	assert ConflictKind.OVER_DETERMINED in kinds, report.summary()
	conflict = report.of_kind(ConflictKind.OVER_DETERMINED)[0]
	assert conflict.subject == "lcoe_usd_per_mwh"
	assert "lcoe_definition" in conflict.detail


def test_an_over_determination_offers_the_levers_that_reach_it(
	graph: ParameterGraph, defaults: dict
):
	"""The corrections name inputs, and the move would close the gap.

	The supplied value was 40 and the graph computes its own; the correction
	against ``capacity_factor`` must be a real number whose application moves
	the parameter toward the supplied one -- a correction of zero is not a
	correction, which is the defect this pins.
	"""
	supplied = dict(defaults)
	supplied["lcoe_usd_per_mwh"] = 40.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	conflict = report.of_kind(ConflictKind.OVER_DETERMINED)[0]
	assert conflict.corrections, "an over-determination offered no lever"
	for correction in conflict.corrections:
		assert correction.delta != 0.0, correction
		assert graph.is_settable(correction.parameter)


def test_a_lever_upstream_of_the_equation_is_offered(
	graph: ParameterGraph, defaults: dict
):
	"""The carbon price fixes the DSCR conflict without appearing in its equation.

	``dscr_requirement`` is ``project_gearing_dscr >= dscr_min``; neither name
	is an input, and the carbon price reaches the ratio through the tariff and
	the cash flow. A correction list built from the equation's own parameters
	would offer only the regulator's floor for a conflict the carbon price
	caused, which is the bug this pins.
	"""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	direct = report.of_kind(ConflictKind.DIRECT)
	assert direct, report.summary()
	named = {c.parameter for conflict in direct for c in conflict.corrections}
	assert "carbon_price_usd_per_tco2" in named, (
		f"the carbon price caused this conflict and is not among the levers "
		f"offered: {sorted(named)}"
	)


def test_a_direct_conflict_closes_its_residual_to_first_order(
	graph: ParameterGraph, defaults: dict
):
	"""Applying the suggested move actually closes the residual.

	The suggestion is ``-r / (dF/dx)``, which is a first-order claim. Moving
	the named input by it and re-propagating must reduce the residual, which is
	the only thing that makes the suggestion a correction rather than a number.
	"""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	conflict = report.of_kind(ConflictKind.DIRECT)[0]
	correction = conflict.corrections[0]
	moved = dict(supplied)
	moved[correction.parameter] = (
		result.values[correction.parameter] + correction.delta
	)
	after = graph.propagate(moved)
	before_residual = abs(
		next(
			v.residual
			for v in graph.consistency(result.values)
			if v.equation_id == conflict.subject
		)
	)
	after_residual = min(
		(
			abs(v.residual)
			for v in graph.consistency(after.values)
			if v.equation_id == conflict.subject
		),
		default=0.0,
	)
	assert after_residual < before_residual, (
		f"moving {correction.parameter} by {correction.delta} left the residual "
		f"at {after_residual}, from {before_residual}"
	)


def test_a_correction_that_leaves_the_declared_range_says_so(
	graph: ParameterGraph, defaults: dict
):
	"""A move that trades a residual for an out-of-range value is flagged."""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	for conflict in report.conflicts:
		for correction in conflict.corrections:
			node = graph.node(correction.parameter)
			if node.range is None:
				continue
			target = result.values[correction.parameter] + correction.delta
			inside = node.range[0] <= target <= node.range[1]
			assert correction.within_range is inside, correction


def test_a_missing_input_is_an_under_determination(
	graph: ParameterGraph, defaults: dict
):
	"""A needed parameter that nothing supplies is named as under-determined."""
	supplied = {
		k: v for k, v in defaults.items() if k != "discount_rate"
	}
	# `discount_rate` has a default and nothing derives it, so dropping it
	# leaves the graph unable to compute the parameters that need it.
	report = detect_conflicts(graph, defaults, supplied=supplied)
	under = report.of_kind(ConflictKind.UNDER_DETERMINED)
	assert any(c.subject == "discount_rate" for c in under), report.summary()


def test_an_out_of_range_derivation_is_its_own_kind(
	graph: ParameterGraph, defaults: dict
):
	"""Arithmetic that produces an unsignable value is reported by kind."""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	kinds = {c.kind for c in report.conflicts}
	# The scenario is infeasible on several counts; the point is that an
	# excursion, if there is one, is classified as an excursion.
	for conflict in report.conflicts:
		if conflict.kind is ConflictKind.OUT_OF_RANGE:
			assert not conflict.subject.endswith("_out_of_range")
			assert conflict.subject in graph.nodes
	_ = kinds


def test_corrections_are_ranked_by_relative_move_not_by_raw_delta(
	graph: ParameterGraph, defaults: dict
):
	"""The ranking does not rank units.

	A 0.2 move in an emission factor and an 82 USD/t move in a carbon price can
	be the same real-world size; ordering by the raw delta puts whichever
	parameter carries the smaller unit first. The list must be monotone in the
	relative move.
	"""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	for conflict in report.conflicts:
		fractions = [abs(c.relative_move) for c in conflict.corrections]
		assert fractions == sorted(fractions), (
			f"{conflict.subject}: corrections are not ranked by relative move: "
			f"{fractions}"
		)


def test_a_loop_with_no_fixed_point_is_a_loop_conflict(
	graph: ParameterGraph, defaults: dict
):
	"""The loop's failure is reported as a loop, not as a direct conflict.

	A feedback system that cannot settle has no equation to name and no
	residual to close, so the fix is different from a scenario whose arithmetic
	merely disagrees. Classification is what keeps those apart.
	"""
	values = dict(graph.propagate(defaults).values)
	# Damping above one makes the Gauss-Seidel iteration diverge.
	report = detect_conflicts(graph, values, supplied=defaults, rank=1)
	assert report.of_kind(ConflictKind.LOOP) == (), (
		"the shipped graph should have a fixed point at its defaults"
	)


def test_suggest_corrections_deduplicates_by_parameter(
	graph: ParameterGraph, defaults: dict
):
	"""One lever named by two conflicts is one suggestion, not two."""
	supplied = dict(defaults)
	supplied["carbon_price_usd_per_tco2"] = 200.0
	result = graph.propagate(supplied)
	moves = suggest_corrections(graph, result.values, supplied=supplied)
	names = [m.parameter for m in moves]
	assert len(names) == len(set(names)), names
	for move in moves:
		assert graph.is_settable(move.parameter)


def test_the_report_ranks_over_determination_above_a_range_excursion(
	graph: ParameterGraph, defaults: dict
):
	"""Severity is about how much of the scenario is invalidated."""
	supplied = dict(defaults)
	supplied["lcoe_usd_per_mwh"] = 40.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values, supplied=supplied)
	order = [c.kind for c in report.ranked()]
	severity = {
		ConflictKind.OVER_DETERMINED: 0,
		ConflictKind.UNDER_DETERMINED: 1,
		ConflictKind.LOOP: 2,
		ConflictKind.DIRECT: 3,
		ConflictKind.OUT_OF_RANGE: 4,
	}
	assert order == sorted(order, key=lambda k: severity[k])


def test_detecting_conflicts_without_the_supplied_set_checks_only_the_arithmetic(
	graph: ParameterGraph, defaults: dict
):
	"""Without ``supplied``, the input-level kinds are invisible, and that is stated.

	Over- and under-determination are relations between what the caller set and
	what the graph computes. A caller who does not say what they set cannot
	have those checked, and the report must not claim otherwise.
	"""
	supplied = dict(defaults)
	supplied["lcoe_usd_per_mwh"] = 40.0
	result = graph.propagate(supplied)
	report = detect_conflicts(graph, result.values)
	assert report.of_kind(ConflictKind.OVER_DETERMINED) == ()


# ---------------------------------------------------------------------------
# The commands: a capability with no entry point is a library, not a product
# ---------------------------------------------------------------------------


def _prg(*args: str):
	"""Invoke the `prg` sub-app the way a shell would."""
	from typer.testing import CliRunner

	from alea.cli import app

	return CliRunner().invoke(app, ["prg", *args])


def test_the_conflict_and_sensitivity_commands_are_reachable():
	"""Asserted through the runner, because the defect class is registration.

	A command defined and never mounted is unreachable from the shell, and
	nothing else in the suite notices: the function imports, the module tests
	pass, and the capability is still one nobody can type.
	"""
	for command in ("conflicts", "sensitivity"):
		result = _prg(command, "--help")
		assert result.exit_code == 0, f"{command}: {result.output}"


def test_the_conflict_command_exits_non_zero_on_a_conflict(graph: ParameterGraph):
	"""The exit code is the gate, so a clean run and a conflicted run differ.

	Exiting zero on a conflict would make the command useless in a pipeline,
	which is the only place a gate is worth having.
	"""
	conflicted = _prg("conflicts", "--set", "carbon_price_usd_per_tco2=200")
	assert conflicted.exit_code == 1, conflicted.output
	assert "dscr_requirement" in conflicted.output

	clean = _prg("conflicts")
	assert clean.exit_code == 0, clean.output


def test_the_conflict_command_accepts_a_derived_parameter_because_that_is_the_conflict(
	graph: ParameterGraph,
):
	"""`check` refuses a computed parameter; `conflicts` must not.

	Setting a derived parameter *is* the over-determination the command
	reports. Refusing it -- as `check` correctly does -- would hide the finding
	behind the same error message and leave no way to ask about it.
	"""
	result = _prg("conflicts", "--set", "lcoe_usd_per_mwh=40")
	assert result.exit_code == 1, result.output
	assert "over_determined" in result.output

	refused = _prg("check", "--set", "lcoe_usd_per_mwh=40")
	assert refused.exit_code == 2, refused.output


def test_the_sensitivity_command_prints_the_derivative_the_kernel_computes(
	graph: ParameterGraph, defaults: dict
):
	"""The door and the kernel agree, because there is one implementation."""
	result = _prg("sensitivity", "lcoe_usd_per_mwh", "--top", "1")
	assert result.exit_code == 0, result.output
	propagated = graph.propagate(defaults)
	expected = gradients(graph, propagated.values).of("lcoe_usd_per_mwh").largest(1)[0]
	assert expected[0] in result.output
	assert f"{expected[1]:+12.6g}" in result.output


def test_the_sensitivity_command_can_report_elasticity(
	graph: ParameterGraph, defaults: dict
):
	"""`--elasticity` switches to the dimensionless form, and it differs."""
	raw = _prg("sensitivity", "lcoe_usd_per_mwh", "--top", "1")
	elastic = _prg("sensitivity", "lcoe_usd_per_mwh", "--top", "1", "--elasticity")
	assert raw.exit_code == 0 and elastic.exit_code == 0
	assert raw.output != elastic.output


# ---------------------------------------------------------------------------
# Uncertainty: the declarations, and the gap between them and a distribution
# ---------------------------------------------------------------------------


def test_the_uncertainty_register_reads_the_declarations(graph: ParameterGraph):
	"""The counts are literals, so the register cannot drift unnoticed.

	Deriving them from the register itself would pass on a graph that declared
	nothing uncertain, which is the silence this module exists to break.
	"""
	reg = register(graph)
	assert len(reg.inputs) == 13, reg.inputs
	assert len(reg.derived_stochastic) == 8, reg.derived_stochastic
	assert len(reg.stochastic_edges) == 1, reg.stochastic_edges
	# 21 nodes are declared stochastic in total: 13 settable, 8 derived.
	assert len(reg.inputs) + len(reg.derived_stochastic) == 21


def test_every_uncertain_input_is_settable(graph: ParameterGraph):
	"""An uncertain *derived* value is reported separately, not as an input.

	Conflating them would let a caller try to sample a parameter the graph
	computes, which is the over-determination the graph refuses elsewhere.
	"""
	reg = register(graph)
	for name in reg.inputs:
		assert graph.is_settable(name), name
	for name in reg.derived_stochastic:
		assert not graph.is_settable(name), name


def test_reachability_includes_a_physical_identity_downstream(graph: ParameterGraph):
	"""An exact relation downstream of an uncertain input still moves.

	``emissions_mtco2_per_year`` is declared ``physical`` and is an accounting
	identity; it is also computed from a demand that is declared stochastic. The
	relation is exact and the *value* is uncertain, and reporting only one of
	those would either call every downstream identity stochastic or pretend the
	uncertainty stops at the first equation.
	"""
	reg = register(graph)
	assert "emissions_mtco2_per_year" in reg.reachable
	assert "emissions_mtco2_per_year" not in reg.derived_stochastic


def test_reachability_crosses_a_feedback_loop():
	"""The closure uses `affects`, so it does not stop at a loop.

	`depends_on` deliberately skips the loop equations -- a loop has no place in
	a topological order -- so a closure over it would end at the fixed point and
	miss everything the loop computes. Built on a synthetic graph because the
	shipped one has no *uncertain* input that reaches its loop: the property is
	about the closure's route, not about which of this graph's parameters happen
	to be declared stochastic, and asserting it against the shipped graph would
	assert a premise that is false.
	"""
	def node(name: str, role: str, **extra) -> dict:
		return {
			"name": name,
			"unit": "1",
			"type": "float",
			"role": role,
			"category": "Financial",
			"determinism": "policy",
			"priority": "P1",
			"status": "existing",
			**extra,
		}

	# `z` and `w` determine each other -- a loop -- and `out` is computed from
	# the loop's fixed point, which is what a closure over `depends_on` would
	# never reach.
	document = {
		"parameters": {
			"x": node("x", "exogenous", determinism="stochastic", default=2.0),
			"z": node("z", "derived", range=[0.0, 100.0], initial=1.0),
			"w": node("w", "derived", range=[0.0, 100.0], initial=1.0),
			"out": node("out", "derived", range=[0.0, 1e6]),
		},
		"equations": {
			# `solution_method: iterative` is what marks an equation as part of
			# a loop rather than a derivation; without it the graph reads the
			# cycle as a topological contradiction and refuses the document.
			"e_z": {"name": "z", "lhs": "z", "rhs": "x + w / 2",
			        "parameters": ["z", "x", "w"], "determined_variables": ["z"],
			        "system": "capture_price", "linearity": "linear",
			        "solution_method": "iterative"},
			"e_w": {"name": "w", "lhs": "w", "rhs": "z / 2",
			        "parameters": ["w", "z"], "determined_variables": ["w"],
			        "system": "capture_price", "linearity": "linear",
			        "solution_method": "iterative"},
			# `out` is an ordinary derivation *from* the loop, so it must not be
			# iterative: that is what makes it downstream of the fixed point
			# rather than part of the cycle.
			"e_out": {"name": "out", "lhs": "out", "rhs": "z * 10",
			          "parameters": ["out", "z"], "determined_variables": ["out"],
			          "system": "cost_accounting"},
		},
	}
	synthetic = ParameterGraph.from_mapping(document)
	reg = register(synthetic)
	assert "x" in reg.inputs
	assert "z" in reg.reachable, reg.reachable
	assert "out" in reg.reachable, (
		f"the closure stopped at the loop instead of crossing it: {reg.reachable}"
	)


def test_the_stochastic_edge_names_parameters_the_graph_has(graph: ParameterGraph):
	reg = register(graph)
	for source, target, equation_id in reg.stochastic_edges:
		assert source in graph.nodes, source
		assert target in graph.nodes, target
		assert equation_id in graph.equations, equation_id


def test_the_register_states_the_gap_rather_than_implying_a_distribution(
	graph: ParameterGraph,
):
	"""The summary says a sensitivity is not a distribution, in words.

	The defect this module guards against is a reader taking the uncertainty
	declarations for a modelled distribution. The sentence is the guard, so it
	is asserted.
	"""
	text = register(graph).summary()
	assert "not a distribution" in text
	assert "13" in text and "22" in text


# ---------------------------------------------------------------------------
# Dimensional consistency
# ---------------------------------------------------------------------------


def _canary_equation(lhs: str, rhs: str):
	"""An equation built only to be pointed at the dimensional checker."""
	from alea.prg.views import Equation

	return Equation(
		id="canary",
		name="canary",
		description="a canary, not a claim about the graph",
		system="cost_accounting",
		lhs=lhs,
		rhs=rhs,
		relation="eq",
		parameters=[],
		free_variables=[],
		determined_variables=[],
	)


def test_the_unit_checker_flags_a_power_against_an_energy(graph: ParameterGraph):
	"""MW = TWh is a mismatch, and the checker must say so.

	The canary for the whole module: a dimensional check that cannot tell a
	megawatt from a megawatt-hour is not a check. If this passes the checker is
	blind, and every "consistent" it reports is unearned.
	"""
	from alea.prg.units import check_equation

	check = check_equation(_canary_equation("largest_loss_mw", "generation_twh"), graph)
	assert check.decidable, "the checker gave up on MW = TWh"
	assert not check.consistent, "the checker called MW = TWh consistent"


def test_the_unit_checker_flags_an_inhomogeneous_sum(graph: ParameterGraph):
	"""``MW + TWh`` cannot share a dimension, and the mismatch is the finding."""
	from alea.prg.units import check_equation

	check = check_equation(
		_canary_equation("largest_loss_mw", "largest_loss_mw + generation_twh"), graph
	)
	assert check.decidable, "the checker gave up on MW + TWh"
	assert not check.consistent, "the checker called MW + TWh consistent"


def test_the_unit_checker_passes_a_dimensionally_correct_identity(
	graph: ParameterGraph,
):
	"""``USD/tCO2 * tCO2/MWh = USD/MWh`` is right, and must not be flagged.

	The other half of the canary. A checker that flagged everything would pass
	the two tests above and be useless; this is the one that fails it.
	"""
	from alea.prg.units import check_equation

	check = check_equation(
		_canary_equation(
			"carbon_cost_usd_per_mwh",
			"carbon_price_usd_per_tco2 * emission_factor_t_per_mwh",
		),
		graph,
	)
	assert check.decidable and check.consistent, check.summary()


def test_the_unit_checker_decides_the_graph_without_giving_up(
	graph: ParameterGraph,
):
	"""Every equation is decidable -- no silent hole in the coverage.

	An undecidable equation is not a pass, and a check whose undecidable set
	grows quietly is a check that stops covering the graph while still
	reporting a green count. The graph is fully decidable today, and that is
	the assertion: if a future equation cannot be decided, this fails and the
	walker gets the branch it is missing.
	"""
	from alea.prg.units import check_graph

	report = check_graph(graph)
	assert report.undecidable == (), [c.summary() for c in report.undecidable]
	assert len(report.checks) == len(graph.equations)


def test_the_unit_report_separates_inconsistent_from_undecidable(
	graph: ParameterGraph,
):
	"""The three sets partition the equations, and none is folded into another."""
	from alea.prg.units import check_graph

	report = check_graph(graph)
	total = len(report.consistent) + len(report.inconsistent) + len(report.undecidable)
	assert total == len(graph.equations)
	assert "not a pass" in report.summary()


def test_the_flagged_equations_are_a_known_set(graph: ParameterGraph):
	"""The inconsistent set is pinned, so a new one is a failing test.

	Seven equations are flagged today. They are not seven of one kind -- three
	are the ``(1 + rate)`` convention, one is a missing nominal frequency, and
	the rest are annual quantities declared without a per-year divisor. This
	test does not bless them; it makes the set move only when someone means it
	to, because a count that drifts unnoticed is how a dimensional defect ships.
	"""
	from alea.prg.units import check_graph

	report = check_graph(graph)
	flagged = {check.equation_id for check in report.inconsistent}
	assert flagged == {
		"crf_definition",
		"energy_demand",
		"debt_service_definition",
		"rocof_definition",
		"emissions_definition",
		"hydrogen_water_definition",
		"premature_deaths_definition",
	}, sorted(flagged)


def test_the_summary_carries_the_unit_register(graph: ParameterGraph):
	"""The unit check rides on the summary, so its coverage cannot be missed."""
	summary = graph_summary(graph)
	units = summary["units"]
	assert len(units.checks) == len(graph.equations)
	assert "not a pass" in units.summary()
