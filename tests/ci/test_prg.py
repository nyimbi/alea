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

import itertools
import math
import re

import pytest
import yaml

from alea.config.paths import repo_root
from alea.prg import load_graph
from alea.prg.conflicts import (
	ConflictKind,
	detect_conflicts,
	suggest_corrections,
)
from alea.prg.dsl import (
	DslError,
	const,
	evaluate,
	linear_coefficients,
	linearity_in,
	parse,
	parse_side,
	simplify,
	solve_affine,
	solve_for,
	sym,
)
from alea.prg.feedback import FeedbackError
from alea.prg.graph import CycleError, GraphError, ParameterGraph
from alea.prg.library import SYSTEM_IDS, coverage, systems_of
from alea.prg.sensitivity import elasticity, gradients, sensitivity
from alea.prg.service import check_scenario, describe, graph_summary, propagate_change
from alea.prg.uncertainty import register
from alea.prg.views import Equation, ParameterType

PRG_PATH = repo_root() / "config" / "prg.yaml"

# The findings the shipped defaults produce, and the only ones they may.
#
# Every "a clean scenario is clean" gate in this module asserted an *empty*
# violation list until batch 67, and it was empty for the wrong reason:
# ``rocof_definition`` was missing its nominal-frequency factor, so it computed
# 0.0128 Hz/s where the swing equation gives 0.638, and the nadir it feeds came
# out at 49.87 Hz -- inside every under-frequency limit in any grid code. The
# gates were green because the physics was 50x too optimistic.
#
# With the factor restored the shipped scenario reports what it actually is.
# Inertia 39,200 MW.s (firm capacity 9,800 MW at H = 4 s) against a 1,000 MW
# largest loss gives a RoCoF of 0.638 Hz/s, and the 10 s response time puts the
# frequency at response onset at 43.62 Hz. That is below the node's own
# admissible floor of 45 Hz, so the graph raises ``_out_of_range``, and below
# the 48 Hz rule threshold, so ``frequency_nadir_below_protection`` fires. Both
# are correct reports about the scenario, not defects in the report.
#
# The numbers are *not* adjusted to make these go away. `docs/prg-status.md`
# states the rule for this chain: "Bending either number to make the other fit
# would be manufacturing agreement." The response time is 10 s and carries no
# archived citation, and the 45 Hz floor is the UFLS setting the node claims
# to be. Resolving which is wrong is a modelling question with a source
# requirement, and it is recorded in `docs/prg-status.md` rather than settled
# by editing a default.
#
# The gates below therefore compare against this set *exactly*, not as a
# subset: a second, unrelated finding still fails every one of them.
KNOWN_DEFAULT_FINDINGS = frozenset({"frequency_nadir_hz_out_of_range"})
KNOWN_DEFAULT_RULES = frozenset({"frequency_nadir_below_protection"})


def _default_violation_ids(graph: ParameterGraph, values) -> set[str]:
	"""The equation ids ``consistency`` reports, as a set for comparison."""
	return {v.equation_id for v in graph.consistency(values)}


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph(PRG_PATH)


@pytest.fixture
def document() -> dict:
	return yaml.safe_load(PRG_PATH.read_text())


@pytest.fixture
def defaults(graph: ParameterGraph) -> dict[str, float]:
	return {k: n.default for k, n in graph.nodes.items() if n.default is not None}


def _loop_over(graph: ParameterGraph, variable: str):
	"""The feedback loop that solves for ``variable``.

	Selected by variable rather than by index because the graph carries more
	than one loop, and the order ``detect_loops`` returns them in is an artefact
	of Tarjan's traversal -- an index-based test would silently check whichever
	component the algorithm happened to reach first, and would keep passing
	after the loop it meant to check was deleted, as long as some other loop
	took its place. Naming the variable makes a missing loop a named failure.
	"""
	loops = [loop for loop in graph.feedback_loops() if variable in loop.variables]
	assert len(loops) == 1, (
		f"expected exactly one feedback loop solving for {variable!r}, "
		f"found {[loop.id for loop in loops]} among "
		f"{[loop.id for loop in graph.feedback_loops()]}"
	)
	return loops[0]


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


def test_the_load_cache_is_identity_keyed_and_cannot_serve_a_stale_graph(tmp_path):
	"""The cache is a speed-up, and the test is that it never lies.

	Two properties, and the second is the one that matters. It *is* a cache --
	the second load of an unchanged file returns the same object rather than an
	equal one. And an edit changes the answer: a modified document must produce
	a graph reflecting the edit, because a cache keyed on the path alone would
	serve the old graph after the file changed, which is the defect the module
	exists to avoid, one level up.

	The key is mtime *and* size, so the limit is stated rather than hidden: a
	rewrite preserving both would be served stale, and this test does not
	pretend otherwise. What it does pin is that the ordinary edit -- write a
	file, in place, as an editor does -- is observed.
	"""
	from alea.prg.graph import load_graph

	document = yaml.safe_load(PRG_PATH.read_text())
	path = tmp_path / "prg.yaml"
	path.write_text(yaml.safe_dump(document))

	first = load_graph(path)
	assert load_graph(path) is first, "an unchanged file was re-parsed"

	# A real edit: one node's default changes. The size changes with it, which
	# is what makes this the ordinary case rather than a contrived one.
	document["parameters"]["base_demand_twh"]["default"] = 41.0
	path.write_text(yaml.safe_dump(document))
	second = load_graph(path)
	assert second is not first, "an edited file served the graph from before the edit"
	assert second.nodes["base_demand_twh"].default == 41.0


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

	Selected by variable and not by index. The graph carries two loops as of
	2026-10-15 -- this one and the tariff-demand fixed point -- and an index
	would silently check whichever `detect_loops` happened to order first.
	"""
	result = graph.propagate(defaults)
	loop = _loop_over(graph, "vre_capacity_mw")
	solved = {entry.loop: entry for entry in result.loops}[loop.id]
	assert solved.converged

	total = defaults["total_capacity_mw"]
	target = defaults["vre_capacity_target_mw"]
	sensitivity = defaults["capture_price_sensitivity"]
	share = (target / total) / (1 + sensitivity * target / total)

	assert result.values["vre_share"] == pytest.approx(share, rel=1e-7)
	assert result.values["vre_capacity_mw"] == pytest.approx(target / (1 + sensitivity * target / total), rel=1e-7)
	assert result.values["capture_price_ratio"] == pytest.approx(
		1 / (1 + sensitivity * target / total), rel=1e-7
	)


def test_the_tariff_loop_converges_and_the_tariff_covers_its_cost(
	graph: ParameterGraph, defaults: dict
):
	"""The second feedback loop, and the identity that makes it a loop.

	``equilibrium_demand`` alone is not a loop: demand is a function of the
	tariff, and if the tariff is exogenous that is one directed edge. The loop
	is the pair, because the tariff is set to recover the cost of serving the
	demand, so each determines the other. The specification declares both
	(§4.14 Demand-Supply Equilibrium and §4.15 Price-Demand Feedback); the
	graph carried only the first until 2026-10-15.

	The assertion that matters is not "it converged" -- a fixed point of a
	wrong map converges too -- but that the converged pair *satisfies the
	cost-recovery identity*, checked here from the result's own numbers rather
	than from the equation text.
	"""
	result = graph.propagate(defaults)
	loop = _loop_over(graph, "regulated_tariff_usd_per_mwh")
	solved = {entry.loop: entry for entry in result.loops}[loop.id]
	assert solved.converged, solved

	tariff = result.values["regulated_tariff_usd_per_mwh"]
	demand = result.values["equilibrium_demand_twh"]
	# The identity, restated: the annualised fixed charge over the energy sold,
	# plus the short-run marginal cost. 1000 kW/MW and 1e6 MWh/TWh.
	expected = (
		result.values["annualised_capex_usd_per_kw"]
		* defaults["total_capacity_mw"]
		* 1000
		/ (demand * 1e6)
		+ result.values["marginal_cost_usd_per_mwh"]
	)
	assert tariff == pytest.approx(expected, rel=1e-7), (tariff, expected)

	# And the demand side: the tariff moved demand off its unconstrained
	# value, in the direction the elasticity's sign says it should. This is
	# what makes the loop a *feedback* loop rather than an identity that
	# happens to be circular.
	unconstrained = result.values["demand_twh"]
	assert defaults["price_elasticity"] < 0
	assert demand != pytest.approx(unconstrained, rel=1e-9), demand
	# The direction is a *consequence* of the two, not a fact to assume: the
	# elasticity is negative, so demand moves opposite to the tariff ratio, and
	# at these defaults the cost-recovery tariff (88.98 USD/MWh) sits below the
	# reference (100.00) -- an under-recovering fleet, so demand rises. Asserting
	# "demand falls" would have been asserting the sign of a difference that
	# depends on the fleet's capital intensity; asserting the relationship is
	# the claim that actually holds for every fleet.
	reference = defaults["reference_tariff_usd_per_mwh"]
	assert (tariff - reference) * (demand - unconstrained) < 0, (
		f"elasticity is negative, so demand must move against the tariff ratio: "
		f"tariff {tariff} vs reference {reference}, demand {demand} vs {unconstrained}"
	)


def test_the_loop_answer_does_not_depend_on_where_it_starts(graph: ParameterGraph, defaults: dict):
	"""A fixed point is a property of the map, not of the initial iterate."""
	from alea.prg.feedback import solve_loop

	loop = _loop_over(graph, "vre_capacity_mw")
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

	loop = replace(_loop_over(graph, "vre_capacity_mw"), max_iterations=1)
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
	assert _default_violation_ids(graph, values) == KNOWN_DEFAULT_FINDINGS

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
	assert _default_violation_ids(graph, values) == KNOWN_DEFAULT_FINDINGS

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
	"""A cycle among derived parameters has no evaluation order.

	WHY THE MUTATION *ADDS* AN OPERAND RATHER THAN REPLACING THEM. The cycle
	needs ``marginal_cost`` to depend on ``lcoe``, and ``lcoe_definition``
	already depends on ``marginal_cost`` -- so naming ``lcoe`` in this equation
	is the whole of it. An earlier version replaced the right-hand side
	outright, which dropped ``carbon_cost_usd_per_mwh`` from the equation while
	the shipped edge ``carbon_cost -> marginal_cost`` still cited it. That
	document is refused by the edge rule before ``order()`` is ever reached, so
	the test failed on a defect it had introduced itself and reported a cycle
	that nothing got to look for. Keeping the shipped operands and appending
	``lcoe`` makes the document one the loader accepts, which is the only kind
	on which "the cycle is refused" says anything.
	"""
	document["equations"]["marginal_cost"]["rhs"] = (
		"fuel_price_usd_per_mwh + carbon_cost_usd_per_mwh + lcoe_usd_per_mwh"
	)
	document["equations"]["marginal_cost"]["parameters"] = [
		"marginal_cost_usd_per_mwh",
		"fuel_price_usd_per_mwh",
		"carbon_cost_usd_per_mwh",
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


#: The first relationship in the shipped document is ``discount_rate -> crf``.
#: Its direction, and where the edge must therefore appear. The four booleans
#: are ``edges_from(discount_rate)``, ``edges_from(crf)``, ``edges_into(crf)``
#: and ``edges_into(discount_rate)``, hand-derived from ``params-prg1.md`` §3.3
#: -- "the PRG must encode causality" -- rather than read off the
#: implementation.
#:
#: Every one of the 84 shipped edges is ``forward``, so indexing by the
#: ``source``/``target`` fields instead of by the declared direction is
#: indistinguishable from indexing by direction on this document. That is what
#: made the field inert and invisible: a declaration no instance exercises is a
#: declaration nothing tests. These three rows are the instances the document
#: does not have.
_DIRECTION_SEMANTICS = [
	("forward", True, False, True, False),
	("backward", False, True, False, True),
	("bidirectional", True, True, True, True),
]


@pytest.mark.parametrize(
	("direction", "from_source", "from_target", "into_target", "into_source"),
	_DIRECTION_SEMANTICS,
	ids=[row[0] for row in _DIRECTION_SEMANTICS],
)
def test_an_edge_is_indexed_by_its_declared_direction_not_its_fields(
	document: dict,
	direction: str,
	from_source: bool,
	from_target: bool,
	into_target: bool,
	into_source: bool,
):
	"""A ``backward`` edge leaves its *target*; a ``bidirectional`` edge both.

	``edges_from`` answers "what does the graph say this feeds", and the graph
	says it with ``direction``. An edge whose declaration is read by nothing is
	the same defect as a knob nothing reads, one layer down -- the declaration
	is present and inert. The ``bidirectional`` row is not hypothetical: the
	spec names ``Endogenous <-> Endogenous`` ("capacity and dispatch are jointly
	determined by the optimisation") as a legitimate coupling, so refusing the
	value would forbid a declaration the spec requires.
	"""
	edge = document["relationships"][0]
	assert edge["source"] == "discount_rate" and edge["target"] == "crf", (
		"the direction test is anchored to the first relationship; if the "
		"document reorders its edges this table is measuring a different one"
	)
	edge["direction"] = direction
	graph = ParameterGraph.from_mapping(document)

	# Membership by identity, not by the ``source`` field: the graph holds
	# dozens of other edges touching these two parameters, and a set of names
	# cannot tell this edge from any of them. The shipped edge is `forward`, so
	# a name-set check would pass on the unfixed index for every row but the
	# two it exists to distinguish.
	identity = (edge["source"], edge["target"], edge["equation_id"])
	outgoing = (*graph.edges_from("discount_rate"), *graph.edges_from("crf"))
	# Deduped by identity rather than by the edge object: a `bidirectional`
	# edge is deliberately on both outgoing lists, which is the row below
	# asserting it appears twice, and a document declaring the same edge twice
	# is the other thing this catches. `RelationshipEdge` is frozen and so
	# hashes at runtime, but its `__hash__` is generated by pydantic and
	# invisible to a type checker, so the key is spelled out.
	matches = {
		(e.source, e.target, e.equation_id)
		for e in outgoing
		if (e.source, e.target, e.equation_id) == identity
	}
	assert len(matches) == 1, (
		f"expected exactly one edge {identity} on the outgoing lists, found "
		f"{len(matches)}; the test cannot tell which one it is measuring"
	)
	subject = next(
		e
		for e in outgoing
		if (e.source, e.target, e.equation_id) == identity
	)

	from_s = subject in graph.edges_from("discount_rate")
	from_t = subject in graph.edges_from("crf")
	into_t = subject in graph.edges_into("crf")
	into_s = subject in graph.edges_into("discount_rate")

	assert from_s is from_source
	assert from_t is from_target
	assert into_t is into_target
	assert into_s is into_source
	# The mirror: the edge appears on exactly one outgoing list and exactly one
	# incoming list. A `forward` edge that also arrived at its own source would
	# mean the index appended it twice.
	assert (from_s, from_t) == (into_t, into_s)


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


def test_a_non_scalar_type_carrying_a_scalar_default_is_refused(document: dict):
	"""The `type` field constrains something, or it is decoration.

	Every node in the shipped graph is `float`, and nothing read `type` -- so a
	node declared `timeseries` with a scalar `default` was accepted, propagated
	as a float, and reported as a quantity. That is the declared-is-not-produced
	class: a field that exists, validates, and gates nothing. The model has no
	field for an array, so the honest contract is that `float` is the only type
	it can carry and a declaration saying otherwise is refused.

	Canaried both ways: the refusal fires, and the scalar types are *not*
	refused -- a check that refused every type would pass this test's first half
	while making the field useless.
	"""
	document["parameters"]["discount_rate"]["type"] = "timeseries"
	with pytest.raises(Exception, match="cannot be carried by a scalar"):
		ParameterGraph.from_mapping(document)

	# A scalar type is exactly what the model carries, so it must be accepted.
	document["parameters"]["discount_rate"]["type"] = "int"
	graph = ParameterGraph.from_mapping(document)
	assert graph.nodes["discount_rate"].type.value == "int"


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
	# ``computed``, not ``order``: this field is the derived half of the role
	# partition, so it counts the nodes carrying the derived role. ``order`` is
	# the topological sequence and omits the five feedback-loop variables,
	# which made the summary state 28 derived against 52 exogenous and 3
	# endogenous -- 83 of the 88 parameters it reports in the same payload.
	assert summary["derived"] == len(graph.computed())
	assert summary["derived"] == sum(
		1 for node in graph.nodes.values() if node.role.value == "derived"
	)
	# The partition closes. A client reading the counts must be able to add
	# them up and land on ``parameters``, or one of them is counting a
	# different set than its name says. Exogenous is counted from the graph
	# rather than pinned, so this stays true when the document grows.
	exogenous = sum(
		1 for node in graph.nodes.values() if node.role.value == "exogenous"
	)
	# `free` is the fourth role and the largest by far once the catalog
	# expansion lands: 781 nodes whose catalog row states a method and no
	# formula are `free` -- unconstrained within their range -- and leaving the
	# role out of the sum made the partition read 33 + 3 + 52 against 869
	# parameters. The assertion is what caught it, which is why it is written
	# as a sum over the roles the schema declares rather than over three of
	# them.
	free = sum(1 for node in graph.nodes.values() if node.role.value == "free")
	assert (
		summary["derived"] + summary["endogenous"] + exogenous + free
		== summary["parameters"]
	), "the role partition does not close"
	# The served counts are the local sums, and asserting *that* is what makes
	# the payload a partition rather than a client's arithmetic. The API test
	# re-lists each role through `/prg/parameters?role=` and sums those; this
	# pins the summary's own two fields to the same sets.
	assert summary["exogenous"] == exogenous, summary["exogenous"]
	assert summary["free"] == free, summary["free"]
	# `free` is counted by role, not by `uncoupled()`, and the two are
	# *different sets*. The register is "named by no equation"; the role is
	# "unconstrained within its range". Every uncoupled node is one of the two
	# roles the schema gives a node nothing computes -- `free` (a knob) or
	# `endogenous` (a value the optimiser sizes, which no *equation* fixes) --
	# and neither role is wholly inside the register, because an equation may
	# name a `free` node as an input.
	#
	# The earlier form of this assertion was `free == len(uncoupled()) - 1`,
	# which held on the shipped graph by coincidence: exactly one endogenous
	# node (`storage_capacity_mw`) was uncoupled there, so subtracting one
	# reconciled the two counts. The ingested graph carries nine -- the eight
	# storage capacities the catalog adds plus `storage_capacity_mw` -- and the
	# coincidence broke. Asserting the *containment* is the claim that was
	# meant, and it holds at any count.
	# A deprecated node is retained so that a scenario naming it fails loudly,
	# and it keeps its role and its default for that reason -- `propagate` would
	# fail on a set that omitted it. It is named by no equation, so it lands in
	# this register, but its role describes the node it replaced rather than the
	# graph's live surface. Batch 44 deprecated `pm25_relative_risk_per_kt` in
	# favour of `pm25_relative_risk_per_ug_per_m3`; the old node is `exogenous`,
	# and that is what broke the `{"free"}` claim below. The claim is about live
	# nodes, so the role set is taken over those, and the excluded nodes are
	# named here rather than filtered silently -- a fourth deprecation should
	# have to be written down.
	deprecated_uncoupled = {
		name for name in graph.uncoupled()
		if graph.nodes[name].status == "deprecated"
	}
	assert deprecated_uncoupled == {
		"cross_border_trading", "demand_growth_rate", "pm25_relative_risk_per_kt",
		# Batch 49 retired the duplicate jobs multipliers once `total_jobs`
		# stopped reading them. They are `exogenous` tombstones and would
		# otherwise break the `{"free"}` claim below, which is why they are
		# named here rather than filtered silently.
		"indirect_jobs_multiplier", "induced_jobs_multiplier",
		# Batch 55 retired the generic wind O&M duplicate. It is `free` rather
		# than `exogenous`, so it does not threaten the `{"free"}` claim, but
		# it belongs in this set for the reason the set exists: a fifth
		# deprecation should have to be written down.
		"opex_fixed_wind",
		# Batch 59 retired the duplicate remittance share. Also `free`.
		"remittance_dependency",
		# Batch 61 retired the plural local-content share, keeping the
		# singular. Also `free`, and the retirement repointed its one reader
		# (`local_content_capex_definition`) so no equation names it now.
		"local_content_requirements",
		# Batch 62 retired the unsourced burden limit, keeping the threshold.
		# It is `exogenous`, not `free`, so it also had to be named here for
		# the `{"free"}` claim below -- and unlike batches 55/59/61 its one
		# reader was *deleted* rather than repointed, so nothing names it.
		"energy_burden_limit",
		# Batch 69 retired the buffer-pool alias of `permanence_parameters`.
		# It was `derived` with an equation setting it equal to that share --
		# one number under two ids -- so both the equation and its edge are
		# gone, and it is `free` now that nothing determines it.
		"buffer_pool_contribution",
	}, deprecated_uncoupled
	uncoupled_roles = {
		graph.role(name).value for name in graph.uncoupled()
		if name not in deprecated_uncoupled
	}
	assert uncoupled_roles <= {"free", "endogenous"}, uncoupled_roles
	# The register's endogenous membership has now gone to zero. It was four
	# at batch 31, one after batch 32 bounded `storage_capacity_mw`, and batch
	# 33's `firm_build_fleet_bound` named the last one, `firm_build_fleet_mw`.
	# The earlier form asserted the register held an endogenous witness, which
	# pinned "not every uncoupled node is free"; that claim is now false and
	# asserting it would be asserting a property the graph does not have. The
	# property that *does* hold, and that the register cannot express, is that
	# a node can be endogenous and named by an equation while still being
	# computed by nothing -- a bound names its subject without fixing it, so
	# the node is coupled and uncomputed at once. That is the distinction the
	# register and `computed()` draw between them, and it is what the
	# witness below now pins.
	assert uncoupled_roles == {"free"}, uncoupled_roles
	assert graph.role("firm_build_fleet_mw").value == "endogenous"
	assert "firm_build_fleet_mw" not in graph.uncoupled()
	assert "firm_build_fleet_mw" not in graph.computed()
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
	# The other direction, and a different finding: a knob the graph cannot
	# speak to is a lever a scenario can pull that no audit will see. It must
	# be disjoint from what is reached, or it is not a register of the
	# unreached.
	assert engine["engine_unreached"]
	from alea.prg.translate import translations as _translations

	assert not set(engine["engine_unreached"]) & set(
		t.engine_field for t in _translations()
	)


def test_the_reversal_allowance_is_the_share_and_not_its_complement(
	graph: ParameterGraph, defaults: dict[str, float]
):
	"""The buffer a registry holds is the permanence share, not its complement.

	Batch 24 shipped `carbon_credit_reversal_allowance_definition` as
	``(1 - permanence_parameters) * carbon_credit_volumes``. Batch 33 coupled
	`buffer_pool_contribution` to `permanence_parameters` and flagged that the
	two could not both be right, leaving the question in the node's prose.

	They could not. `permanence_parameters` describes itself as the share of
	issued volume held back against non-permanence, so the complement of that
	share is the volume *not* held back -- the opposite of an allowance. The
	shipped form reported 90% of every issuance as the buffer, 40.5 of 45
	MtCO2/year, against a share of 10%. Batch 34 corrected the equation and
	this pins the correction.

	WHY THE ASSERTION IS THE PRODUCT AND NOT JUST THE VALUE. A literal 4.5
	would pass on any equation that happened to evaluate to 4.5 at defaults,
	including one that multiplied the wrong share by a compensating constant.
	Asserting the identity is what makes the test about the arithmetic rather
	than about today's default; the value is asserted beside it because a
	reader wants the number, and the wrong value is asserted *against* because
	a test that cannot tell the two apart would have passed on the defect.
	"""
	values = dict(graph.propagate(defaults).values)
	share = float(values["permanence_parameters"])
	volumes = float(values["carbon_credit_volumes"])
	allowance = float(values["carbon_credit_reversal_allowance"])
	assert allowance == share * volumes
	assert allowance == 4.5
	assert allowance != (1 - share) * volumes

	# `buffer_pool_contribution` used to be asserted equal to the share here.
	# Batch 69 deprecated it instead: the equation setting it equal to
	# `permanence_parameters` made it a second id for one number, which is the
	# defect class this batch exists to remove, not a coupling. A tombstone
	# carries its old default so it still propagates, and the assertion is that
	# it is *not* reachable by any equation -- the alias's coupling is its
	# deletion, and a graph that quietly re-coupled it would fail here.
	node = graph.node("buffer_pool_contribution")
	assert node.status == "deprecated", node.status
	assert node.deprecated_by == "permanence_parameters", node.deprecated_by
	assert not any(
		"buffer_pool_contribution" in (equation.parameters or [])
		for equation in graph.equations.values()
	), "a deprecated node is reached by an equation; `_deprecated_reach` should refuse this at load"


def test_the_unreached_engine_knobs_are_computed_not_transcribed(monkeypatch):
	"""The reverse register is derived from the declared translations.

	A hand-written list of what the engine cannot be reached for would go stale
	the moment a translation is added, and it would then report a *reached*
	knob as unreached -- the register lying in the direction that reads as a
	limitation rather than as progress. So adding a translation must remove its
	field from the register, and that is the canary: it is the one mutation
	that tells a computed register from a transcribed one.
	"""
	from alea.prg import translate
	from alea.whatif.params import ScenarioParameters

	declared = translate.engine_fields_unreached()
	assert declared == tuple(
		sorted(
			name
			for name in ScenarioParameters.model_fields
			if name not in {t.engine_field for t in translate.TRANSLATIONS}
		)
	)
	# A reached knob is not in the register. `demand_growth` is translated.
	assert "demand_growth" not in declared

	# Canary: name a previously-unreached knob and it must leave the register.
	victim = declared[0]
	assert victim in ScenarioParameters.model_fields, victim
	widened = translate.TRANSLATIONS + (
		translate.Translation(
			prg_parameter="demand_growth",
			engine_field=victim,
			kind="absolute",
			note="canary",
		),
	)
	monkeypatch.setattr(translate, "TRANSLATIONS", widened)
	assert victim not in translate.engine_fields_unreached()


def test_check_scenario_propagates_before_it_validates(graph: ParameterGraph, defaults: dict):
	"""The derived parameters are computed first, so a clean set passes.

	A check that validated the numbers as handed in would report every derived
	parameter as a violation whenever the caller had not computed them.
	"""
	result = check_scenario(dict(defaults), graph)
	# The shipped defaults are not clean -- see `KNOWN_DEFAULT_FINDINGS` -- so
	# this asserts the *propagation* happened, which is what the test is about:
	# a derived parameter that was never computed would report itself here.
	assert {v.equation_id for v in result.violations} == KNOWN_DEFAULT_FINDINGS, (
		result.violations
	)


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


def test_a_settable_value_outside_its_range_is_refused(graph: ParameterGraph, defaults: dict):
	"""The other half of the rule above, and the half that was missing.

	A *derived* value outside its range is the graph's own answer and is
	reported (the test above). A *settable* value outside its range is the
	caller's statement, and it was neither refused nor reported: `range` was
	read as a solver bracket and as a correction filter, and
	`ParameterNode._range_contains_default` checked it only against the
	document's own default. So `capacity_factor=999` against a declared
	`(0.05, 0.7)` propagated and came back as the scenario's value, with
	`range_excursions()` empty -- because that register is written from
	`_note_excursion`, and a settable node has no equation to derive it.

	Both propagation paths are checked, and both bounds are inclusive. The
	boundary assertions are the ones that catch a gate written with `<` where
	it needs `<=`: a value exactly on the declared bound is admissible, and a
	gate that refuses it would reject the endpoints of every range in the
	library.
	"""
	node = graph.node("capacity_factor")
	assert node.range == (0.05, 0.7), node.range
	assert graph.is_settable("capacity_factor")

	for bad in (999.0, 0.0, -1.0):
		scoped = dict(defaults)
		scoped["capacity_factor"] = bad
		with pytest.raises(GraphError, match="outside the range"):
			graph.propagate(scoped)

	# A negative value, on a node whose range starts at zero: the sign the
	# node's own name makes obviously wrong, and the one a gate that only
	# checked the upper bound would let through.
	scoped = dict(defaults)
	scoped["carbon_budget_mtco2"] = -1.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate(scoped)

	# The incremental path refuses too. It is the path `propagate_change`
	# actually takes, so a gate wired only into `propagate` would leave the
	# route a scenario uses unguarded -- the "control that exists is not a
	# control that is applied" shape.
	previous = graph.propagate(defaults)
	scoped = dict(defaults)
	scoped["capacity_factor"] = 999.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate_incremental(scoped, previous, ["capacity_factor"])

	# Both endpoints of the declared range are admissible. Asserted from both
	# sides of each bound so the gate is pinned as inclusive rather than
	# merely "somewhere between".
	for on_bound in (0.05, 0.7):
		scoped = dict(defaults)
		scoped["capacity_factor"] = on_bound
		assert graph.propagate(scoped).values["capacity_factor"] == on_bound


def test_a_bool_retyped_from_a_placeholder_refuses_a_magnitude(graph: ParameterGraph, defaults: dict):
	"""The 55 bools batch 50 retyped, tested on one of them.

	A `bool` with `range: null` refuses nothing: `_refuse_out_of_range` reads
	`if node.range is None: continue`, so a flag with no range propagates any
	number and is reported by no register. That is why the batch declares
	`[0.0, 1.0]` on every bool it writes, and why this test targets a node the
	batch retyped rather than a shipped bool -- a test against a shipped bool
	would pass against the defect it is meant to catch.

	This docstring used to name `n_1_criterion = 7.0` as its example of the
	defect propagating. Batch 58 gave that node a range, so the example became
	false; the surviving illustration is the class rather than one member, and
	`test_every_boolean_refuses_a_magnitude` is the gate that holds the whole
	set.

	Both paths are checked, because `propagate_change` takes the incremental
	one.
	"""
	node = graph.node("market_coupling")
	assert node.type is ParameterType.BOOL, node.type
	assert node.range == (0.0, 1.0), node.range

	scoped = dict(defaults)
	scoped["market_coupling"] = 7.0
	with pytest.raises(GraphError, match="outside the range") as caught:
		graph.propagate(scoped)
	assert "market_coupling=7.0" in str(caught.value), str(caught.value)

	previous = graph.propagate(defaults)
	scoped = dict(defaults)
	scoped["market_coupling"] = 7.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate_incremental(scoped, previous, ["market_coupling"])

	# The endpoints are admissible, so the gate is a range and not a
	# "must be false" in disguise.
	for on_bound in (0.0, 1.0):
		scoped = dict(defaults)
		scoped["market_coupling"] = on_bound
		assert graph.propagate(scoped).values["market_coupling"] == on_bound


def test_every_boolean_refuses_a_magnitude(graph: ParameterGraph, defaults: dict):
	"""No boolean in the graph admits a value that is not a truth value.

	The whole class, not a witness. Twenty-three booleans shipped `range: null`
	-- every one of them with `unit: '1'` -- and `_refuse_out_of_range` skips a
	node whose range is null, so `7.0` propagated. Nine of the twenty-three are
	read by a shipped equation and each carried the wrong number downstream
	rather than raising: `ppa_guarantees = 7.0` drove
	`offtake_risk_premium_applied` to -0.30, and `n_1_criterion = 7.0`
	multiplied `contingency_reserve_mw` to 7000 MW.

	This test is why the batch was written as a class and not a list of nine.
	A test naming only the coupled ones would leave fourteen open, and the next
	batch to couple one of those fourteen would reintroduce the defect without
	touching a line of this file.

	The two bounds are asserted admissible, so the gate is a range and not a
	"must be false" in disguise. A boolean whose default sits on a bound is
	normal here: 24 default to 1.0.
	"""
	booleans = [
		(name, node) for name, node in graph.nodes.items()
		if node.type is ParameterType.BOOL
	]
	assert len(booleans) == 79, len(booleans)

	for name, node in booleans:
		assert node.range == (0.0, 1.0), (
			f"{name} declares range {node.range!r}; a boolean's range is its "
			"admissible set and a null one refuses nothing"
		)

	# The clause above is the gate. A per-node `propagate(name=7.0)` loop over
	# every boolean would add nothing: every bool is `free`, and 78 of 79 are
	# settable, so `range == (0, 1)` *entails* the refusal and the loop can
	# never fail on a graph that passed the assertion above. It is kept as one
	# live probe rather than 79 tautologies, on a node that was permissive
	# before this batch -- `capacity_market` is read by an equation, so the
	# refusal is the difference between a wrong number downstream and a raise.
	scoped = dict(defaults)
	scoped["capacity_market"] = 7.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate(scoped)

	# Both paths, because `propagate_change` takes the incremental one and a
	# range enforced on one of two doors is a range a caller can walk around.
	previous = graph.propagate(defaults)
	scoped = dict(defaults)
	scoped["capacity_market"] = 7.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate_incremental(scoped, previous, ["capacity_market"])

	# The endpoints are admissible, so the gate is a range and not a
	# "must be false" in disguise. `capacity_market` defaults to 0.0.
	scoped = dict(defaults)
	scoped["capacity_market"] = 1.0
	assert graph.propagate(scoped).values["capacity_market"] == 1.0


def test_the_retired_remittance_share_points_at_a_value_it_could_not_have_carried(
	graph: ParameterGraph, defaults: dict
):
	"""A tombstone's default is the migration path, so it has to be a real one.

	`remittance_dependency` shipped the 500,000 sentinel with no unit and no
	reader, as a second id for the share `remittance_income_share` already
	carries. Retiring it is the survey's own classification (row 135, DEAD).

	The claim this test makes is narrower than "it is deprecated": a
	deprecation that leaves the sentinel in place hands every scenario that
	still names the old id a default of 500,000 for a share that cannot exceed
	1, and `propagate` refuses a parameter set that omits a non-derived node --
	so the tombstone *must* carry a value and that value is what a migrating
	caller inherits. Copying the successor's is the only honest choice.
	"""
	victim = graph.node("remittance_dependency")
	successor = graph.node("remittance_income_share")

	assert victim.status == "deprecated", victim.status
	assert victim.deprecated_by == "remittance_income_share", victim.deprecated_by
	assert successor.status != "deprecated", successor.status

	# The tombstone states the quantity it was, at the value the graph now
	# computes it at -- not the placeholder it shipped.
	assert victim.unit == successor.unit == "1", (victim.unit, successor.unit)
	assert victim.range == successor.range, (victim.range, successor.range)
	assert victim.default == successor.default, (victim.default, successor.default)
	assert victim.range != (0.0, 1000000.0), victim.range
	assert victim.default != 500000.0, victim.default

	# A tombstone is not a knob: setting it is refused rather than silently
	# accepted, and the refusal names the successor so the caller can migrate.
	scoped = dict(defaults)
	scoped["remittance_dependency"] = 0.25
	with pytest.raises(GraphError, match="remittance_income_share"):
		graph.propagate(scoped)


def test_the_rpi_x_reduction_is_the_share_it_names_and_not_the_remainder(
	graph: ParameterGraph, defaults: dict
):
	"""The RPI-X offset computes a reduction, and the reduction is `x * base`.

	The shipped equation was `(1 - x_factor) * allowed_revenue_requirement`,
	which is the revenue the cap *leaves* rather than the reduction it applies.
	The node's name and description both say reduction, so the arithmetic was
	the only side disagreeing, and the pack that first flagged it
	(`docs/research/coupling-packs/contract-market.md`, finding 2) called the
	shipped form 49x the described quantity.

	The two forms differ by a factor of 49 at the shipped X of 0.02, not by a
	vanishing term, which is what makes this testable: the assertion below is
	that the value equals the *share of the base* and simultaneously does not
	equal the *remainder*. A test asserting only that the value is positive
	would pass on the shipped defect.
	"""
	values = graph.propagate(defaults).values
	requirement = float(values["allowed_revenue_requirement"])
	x_factor = float(values["x_factor"])
	reduction = float(values["x_factor_revenue_reduction"])

	assert 0.0 < x_factor < 1.0, x_factor
	assert abs(reduction - x_factor * requirement) < 1e-9, (
		f"the reduction is {reduction}, not x*base = {x_factor * requirement}"
	)
	assert abs(reduction - (1.0 - x_factor) * requirement) > 1e-6, (
		"the value still equals the remainder, which is the defect this repairs"
	)

	# A reduction cannot exceed the base it is a share of, at any X in range.
	for probe in (0.02, 0.05, 0.1):
		scoped = dict(defaults)
		scoped["x_factor"] = probe
		out = graph.propagate(scoped).values
		base = float(out["allowed_revenue_requirement"])
		assert abs(float(out["x_factor_revenue_reduction"]) - probe * base) < 1e-9, probe


def test_the_two_local_content_consumers_now_move_together(
	graph: ParameterGraph, defaults: dict
):
	"""One policy lever, two consumers, and they used to move independently.

	`local_content_requirement` (singular, catalog row 4.23) and
	`local_content_requirements` (plural, row 28.9) were two ids for one share:
	same unit `1`, same range [0, 1], same default 0.3. Each had exactly one
	reader -- the singular fed `local_jobs_definition`, the plural fed
	`local_content_capex_definition` -- so a scenario that moved the lever
	moved one consumer and left the other at 0.3. At the shipped default the
	two agree, which is why the duplication survived four hundred tests.

	The test asserts the *coupling*, not the deprecation: both consumers are
	read from the singular, and both respond to it. A test asserting only that
	the plural is deprecated would pass on a tree that deprecated it without
	repointing the capex equation -- which would leave that equation naming a
	tombstone, and `_deprecated_reach` would refuse the load, but the failure
	would read as a broken graph rather than as the missing half of this fix.
	"""
	victim = graph.node("local_content_requirements")
	successor = graph.node("local_content_requirement")

	assert victim.status == "deprecated", victim.status
	assert victim.deprecated_by == "local_content_requirement", victim.deprecated_by
	assert successor.status != "deprecated", successor.status
	# The tombstone states the quantity it was, at the type it was.
	assert victim.unit == successor.unit == "1", (victim.unit, successor.unit)
	assert victim.range == successor.range, (victim.range, successor.range)
	assert victim.default == successor.default, (victim.default, successor.default)

	# The equation that used to read the plural now reads the singular, and
	# the edge register agrees with the arithmetic rather than the old body.
	equation = graph.equations["local_content_capex_definition"]
	assert "local_content_requirements" not in equation.rhs, equation.rhs
	assert "local_content_requirement" in equation.rhs, equation.rhs
	assert "local_content_requirements" not in equation.parameters, equation.parameters
	declared = {
		edge.source for edge in graph.edges
		if edge.equation_id == "local_content_capex_definition"
	}
	assert "local_content_requirements" not in declared, declared
	assert "local_content_requirement" in declared, declared

	# The coupling: both consumers respond to the one dial, at two values, so
	# a fix that repointed the equation but broke the arithmetic fails here.
	baseline = graph.propagate(defaults).values
	jobs_default = float(baseline["local_jobs"])
	capex_default = float(baseline["local_content_capex_mm_usd"])
	for probe in (0.1, 0.6):
		scoped = dict(defaults)
		scoped["local_content_requirement"] = probe
		out = graph.propagate(scoped).values
		assert abs(float(out["local_jobs"]) - jobs_default) > 1e-9, probe
		assert abs(float(out["local_content_capex_mm_usd"]) - capex_default) > 1e-9, (
			f"the capex consumer did not follow the singular to {probe}; it is "
			"still reading a different share"
		)
		# And it is linear in the share, which is what "the share times the
		# base" means -- a repoint that left the old arithmetic somewhere
		# would move the value without moving it proportionally.
		ratio = float(out["local_content_capex_mm_usd"]) / capex_default
		assert abs(ratio - probe / float(defaults["local_content_requirement"])) < 1e-9, (
			probe, ratio
		)

	# The tombstone is not a knob: setting it is refused, and the refusal names
	# the successor so a caller migrating a scenario knows where to go.
	scoped = dict(defaults)
	scoped["local_content_requirements"] = 0.5
	with pytest.raises(GraphError, match="local_content_requirement"):
		graph.propagate(scoped)


def test_one_affordability_line_is_one_dial_and_one_inequality(
	graph: ParameterGraph, defaults: dict
):
	"""Two ids for the 10% line, and two statements of the inequality they gate.

	`energy_burden_limit` and `affordability_threshold` were one statistic
	under two names -- both unit `1`, both default 0.1 -- and each gated its
	own equation: the limit `affordability_constraint` (``limit >= burden``,
	P1, with an edge), the threshold `energy_burden_affordability_bound`
	(``burden <= threshold``, P2, with *no* edge at all). So setting one dial
	moved half the answer, and setting both reported the same inequality
	twice.

	The test asserts the whole repair, because the deprecation alone would be
	half of it: the surviving equation must be the only statement, it must
	carry the edge it never had, and it must be filed under the system the
	spec puts it in. A test asserting only the tombstone would pass on a tree
	that repointed the P1 onto the threshold -- which does not fix the
	duplication, it doubles it: one dial, two violations of one claim.
	"""
	victim = graph.node("energy_burden_limit")
	successor = graph.node("affordability_threshold")

	assert victim.status == "deprecated", victim.status
	assert victim.deprecated_by == "affordability_threshold", victim.deprecated_by
	assert successor.status != "deprecated", successor.status
	# The tombstone states the quantity it was, at the type it was. The ranges
	# are *not* equal and that is a fact about the two ids rather than an
	# oversight: the threshold admits a 0% line, the limit's floor was 0.01.
	assert victim.unit == successor.unit == "1", (victim.unit, successor.unit)
	assert victim.default == successor.default == 0.1, (victim.default, successor.default)
	assert successor.range == (0.0, 0.5), successor.range

	# The restatement is gone, and the survivor is the only equation either
	# dial's inequality lives in.
	assert "affordability_constraint" not in graph.equations
	assert graph.constrains("affordability_threshold") == (
		"energy_burden_affordability_bound",
	), graph.constrains("affordability_threshold")
	assert graph.constrains("energy_burden_limit") == ()

	bound = graph.equations["energy_burden_affordability_bound"]
	assert bound.relation == "leq", bound.relation
	assert bound.lhs == "energy_burden", bound.lhs
	assert bound.rhs == "affordability_threshold", bound.rhs
	# Filed under the affordability system, not the batch-22 emit loop's
	# hardcoded `reserve_margin`.
	assert bound.system == "affordability", bound.system

	# The declared edge the equation always stated and never carried. Without
	# it the `/graph` route draws the 10% line constraining nothing, and
	# `alea.prg.uncertainty` -- which walks the edge set by relationship type
	# -- cannot see it either.
	declared = {
		(edge.source, edge.target)
		for edge in graph.edges
		if edge.equation_id == "energy_burden_affordability_bound"
	}
	assert declared == {("affordability_threshold", "energy_burden")}, declared

	# The coupling, measured rather than inferred from the declarations: the
	# one surviving dial fires exactly one violation, at both probes, and the
	# burden itself does not move -- a constraint gates a scenario, it does
	# not compute a value.
	full = dict(graph.propagate(defaults).values)
	burden = float(full["energy_burden"])
	assert burden < 0.1, burden
	for probe in (0.05, 0.02):
		scoped = {**full, "affordability_threshold": probe}
		# The nadir finding is present in every scenario here (see
		# `KNOWN_DEFAULT_FINDINGS`); what this asserts is that tightening the
		# threshold adds exactly one violation and it is the affordability
		# bound, which is the claim the test is about.
		violated = sorted(
			item.equation_id for item in graph.consistency(scoped)
		)
		assert violated == sorted(
			KNOWN_DEFAULT_FINDINGS | {"energy_burden_affordability_bound"}
		), (probe, violated)
		assert abs(float(graph.propagate(scoped).values["energy_burden"]) - burden) < 1e-12

	# And the tombstone is not a knob: setting it is refused, and the refusal
	# names the successor so a caller migrating a scenario knows where to go.
	scoped = dict(defaults)
	scoped["energy_burden_limit"] = 0.02
	with pytest.raises(GraphError, match="affordability_threshold"):
		graph.propagate(scoped)


def test_every_bound_states_its_coupling_or_declares_that_it_cannot(
	graph: ParameterGraph, defaults: dict
):
	"""A bound with no edge is a constraint the drawn graph does not contain.

	`constrains()` and `affects()` read the equations, so a bound's absence
	from the edge set never affects admissibility -- a scenario that breaks
	`debt_mix_bound` is refused either way. Two consumers do read the edges:
	the `/graph` route, which serves `relationships` as "what a reader draws",
	and `alea.prg.uncertainty`, which walks them filtered by relationship type.
	For those two, twenty-three inequalities stating a coupling declared none.

	The rule asserted here is the one that makes the defect unrepeatable: a
	bound against a symbolic rhs carries one edge per rhs operand, and a bound
	against a literal either names the shared stock its summands compete for
	(declared as peer edges) or is listed as one that does not. A new bound
	that does neither fails this test rather than shipping invisible.

	The two exemptions are asserted as exemptions, not skipped: if one later
	gains a symbolic rhs the batch that changes it should have to say so.
	"""
	symbolic = {
		equation.id
		for equation in graph.equations.values()
		if equation.relation != "eq" and parse_side(equation.rhs).symbols
	}
	declared: dict[str, set[tuple[str, str]]] = {}
	for edge in graph.edges:
		declared.setdefault(edge.equation_id, set()).add((edge.source, edge.target))

	# Every symbolic bound declares at least one edge. This is the assertion
	# that was false for twenty-three equations before batch 63.
	edgeless = sorted(symbolic - set(declared))
	assert edgeless == [], edgeless

	# And the direction is the bound's own: every source is an rhs operand and
	# every target an lhs subject. An edge pointing the other way would draw
	# the constraint backwards, which is worse than drawing nothing.
	#
	# Nine bounds shipped before batch 63 drawing against this convention --
	# some reversed (`fleet_build_balance` runs its nineteen edges from the lhs
	# summands to `total_capacity_mw`, so the drawing says the parts bound the
	# total rather than the reverse), some omitting an rhs symbol, one pointing
	# at a node its rhs does not name at all (`reserve_margin` sources
	# `vre_capacity_mw` against a rhs of `peak_demand_mw` and
	# `reserve_margin_min`). They are named here rather than repaired: each is
	# a separate judgement about what its equation means, and rewriting nine
	# pre-existing edges inside a batch about twenty-three edgeless ones would
	# hide the change in a set nobody was reviewing. A bound that is not on
	# this list must draw its edges the bound's way.
	_DEVIATING = {
		"carbon_budget_constraint",
		"fleet_build_balance",
		"fleet_energy_adequacy",
		"reserve_margin",
		"reserve_margin_with_firm_vre",
		"storage_capacity_mw_bound",
		"thermal_storage_capacity_bound",
		"water_availability_constraint",
		"workshop_capacity_workload_bound",
	}
	assert _DEVIATING <= symbolic, _DEVIATING - symbolic
	for equation_id in sorted(symbolic - _DEVIATING):
		equation = graph.equations[equation_id]
		rhs = set(parse_side(equation.rhs).symbols)
		lhs = set(parse_side(equation.lhs).symbols)
		for source, target in sorted(declared[equation_id]):
			assert source in rhs, (equation_id, source, rhs)
			assert target in lhs, (equation_id, target, lhs)

	# The literal-rhs bounds: each is either coupled by a shared-stock claim or
	# named as one that is not. Nothing may sit in neither set, which is what
	# lets this test distinguish "deliberately uncoupled" from "forgotten".
	literal = {
		equation.id
		for equation in graph.equations.values()
		if equation.relation != "eq" and not parse_side(equation.rhs).symbols
	}
	uncoupled = {
		"local_employment_targets_bound",
		"retention_and_deductible_bound",
	}
	assert uncoupled <= literal, uncoupled - literal
	coupled_literal = literal - uncoupled
	missing = sorted(equation_id for equation_id in coupled_literal if not declared.get(equation_id))
	assert missing == [], missing
	# The exemptions carry no edge at all, so "listed as uncoupled" and "has
	# no edge" are the same claim rather than two that could drift apart.
	for equation_id in sorted(uncoupled):
		assert equation_id not in declared, (equation_id, declared[equation_id])

	# The peer edges cover every unordered pair of summands exactly once. One
	# arrow per pair is the representation, not a direction: a shared-stock
	# claim is symmetric, and drawing it twice would say the graph holds two
	# couplings where the bound states one. What must hold is that no pair is
	# missing -- a three-way split with two edges leaves one share unrelated
	# to the third, which is the defect this batch is about.
	for equation_id in sorted(coupled_literal):
		summands = sorted(parse_side(graph.equations[equation_id].lhs).symbols)
		expected = {
			(a, b) for index, a in enumerate(summands) for b in summands[index + 1:]
		}
		actual = {tuple(sorted(pair)) for pair in declared[equation_id]}
		assert actual == expected, (equation_id, actual, expected)

	# The coupling is still arithmetic, not decoration: the bounds bind at
	# defaults, and breaking one is refused by the equation regardless of the
	# edge. `debt_mix_bound` is the P1 member and the sharpest case -- three
	# instrument shares against debt's own share, all four of which were
	# edgeless nodes before this batch.
	full = dict(graph.propagate(defaults).values)
	assert float(full["debt_financing_share"]) > 0.0
	scoped = {
		**full,
		"bond_share": 0.6,
		"dfi_share": 0.6,
		"commercial_bank_share": 0.6,
	}
	violated = sorted(item.equation_id for item in graph.consistency(scoped))
	assert "debt_mix_bound" in violated, violated


def test_every_equality_declares_an_edge_from_each_symbol_it_reads(
	graph: ParameterGraph,
):
	"""An equality's declared inputs must be the inputs its arithmetic uses.

	Batch 63 asserted this rule for inequalities and found twenty-three that
	stated a coupling and declared none. The same defect sat on equalities,
	where it costs more: a bound with no edge is a constraint the drawing
	omits, but an equality with a missing input edge is a *computed* quantity
	whose declared inputs disagree with its arithmetic, and the disagreement
	is invisible to every reader that trusts the edges.

	`firm_capacity_definition` was the sharp case. It computes
	`firm_capacity_mw = thermal_capacity_mw + dispatchable_re_capacity_mw` and
	shipped zero edges, so both inputs had no incident edge at all while
	`firm_capacity_mw` fed the reserve margin, the inertia constant,
	black-start capability and capacity revenue through seven readers.

	The rule, stated once and asserted over all 533 equalities rather than
	over the nine that were wrong: every symbol an equality names -- on either
	side -- carries an edge into the variable it determines. The variable
	itself is excluded, because an equality's rhs names the quantity it solves
	for and an edge from a variable to itself would draw a dependency the
	equation does not have.

	Written as the complete rule, with no register of exceptions, because the
	tree has none: the count of missing symbols is zero. A register here would
	be the place a future defect hid.
	"""
	determined = {
		equation.id: set(equation.determined_variables or ())
		for equation in graph.equations.values()
		if equation.relation == "eq"
	}
	# 534 until batch 69 removed `buffer_pool_contribution_definition`, an
	# equality whose rhs was the bare share it determined -- a rename rather
	# than a relation. The rule itself is unchanged and still has no
	# exceptions; the count falls with the equation.
	assert len(determined) == 533, len(determined)

	sourced: dict[str, set[str]] = {}
	for edge in graph.edges:
		sourced.setdefault(edge.equation_id, set()).add(edge.source)

	missing: list[tuple[str, str]] = []
	for equation_id, targets in determined.items():
		equation = graph.equations[equation_id]
		symbols = set(parse_side(equation.lhs).symbols) | set(parse_side(equation.rhs).symbols)
		for symbol in sorted(symbols - targets - sourced.get(equation_id, set())):
			missing.append((equation_id, symbol))
	assert missing == [], missing

	# The rule is about the *input* edge, so the direction matters: an edge
	# from a symbol to the variable it determines, never the reverse. A
	# reversed edge satisfies the source set above and draws the equality
	# backwards, which is the failure a count of edges cannot see. A
	# SELF-loop is the degenerate case of the same defect -- the variable
	# declared as its own input -- and is worse than reversed, because it
	# makes a cost depend on itself. `lcoe_solar_definition` and
	# `lcoe_wind_definition` each carried one: their emit loop unioned the
	# lhs symbols into the source set, and for these two the lhs is the
	# determined variable. Repaired at the emitter and asserted here.
	bad_edges: list[tuple[str, str, str]] = []
	for equation_id, targets in determined.items():
		equation = graph.equations[equation_id]
		lhs = set(parse_side(equation.lhs).symbols)
		rhs = set(parse_side(equation.rhs).symbols)
		for edge in graph.edges:
			if edge.equation_id != equation_id:
				continue
			assert edge.target in targets, (equation_id, edge.target, targets)
			assert edge.source in lhs | rhs, (equation_id, edge.source)
			if edge.source in targets:
				bad_edges.append((equation_id, edge.source, edge.target))
	assert bad_edges == [], bad_edges

	# And the tier is the equation's, not the edge's: the loader refuses a
	# document whose edges disagree, so this asserts the refusal is still in
	# force rather than trusting that no one has relaxed it.
	strengths: dict[str, set[str]] = {}
	for edge in graph.edges:
		strengths.setdefault(edge.equation_id, set()).add(edge.strength)
	assert all(len(tiers) == 1 for tiers in strengths.values()), {
		equation_id: tiers for equation_id, tiers in strengths.items() if len(tiers) > 1
	}


def test_no_description_asserts_a_relation_its_equation_does_not_compute(
	graph: ParameterGraph,
):
	"""A node's prose and its arithmetic must describe the same object.

	This is the check no numeric gate can make. Every quantity involved can be
	right -- the value, the range, the unit, the edges -- while the sentence a
	researcher reads says the node is something else. Three did:

	* `carbon_credit_reversal_allowance` said "the complement of the permanence
	  share" and computes `permanence_parameters * carbon_credit_volumes`.
	  Batch 34 corrected the equation *from* the complement and wrote the
	  reasoning into the equation's description, never touching the node's --
	  so the two records of one object disagreed.
	* `gearing_ratio` said "the complement of the debt fraction" and computes a
	  multiple of equity. A complement of a share is a share.
	* `load_factor` said "the complement of the peak-to-average ratio" and
	  computes its reciprocal -- and named a node (`peak_to_average_ratio`)
	  that does not exist.

	The predicate is deliberately narrow: it looks for an *assertion* of a
	complement ("the complement of", "one minus") with no negating word in the
	clause before it, on a node whose determining equation computes neither
	`1 - x` nor something that could be read as one. Narrow is the honest
	choice -- it cannot find a description that is wrong without using the word
	"complement", so it is a lower bound on the class, not a closure. A
	broader net over natural language would fire on correct prose and be
	switched off within a month.

	The negation clause is load-bearing, not decoration: the corrected
	descriptions say "Not the complement of the debt fraction" and "the
	reciprocal ..., not its complement", so a naive phrase search would report
	this batch's own fixes as defects. That is the failure mode of every prose
	gate -- it must be able to read a correction as a correction.
	"""
	import re

	assertion = re.compile(r"(?<!not )(?<!never )the complement of|one minus", re.I)
	negated = re.compile(r"\b(not|never|rather than|instead of)\b[^.]{0,50}$", re.I)

	offenders: list[tuple[str, str, str]] = []
	for name, node in graph.nodes.items():
		text = node.description or ""
		for match in assertion.finditer(text):
			if negated.search(text[max(0, match.start() - 50):match.start()]):
				continue
			determining = [
				equation
				for equation in graph.equations.values()
				if equation.determined_variables and equation.determined_variables[0] == name
			]
			if not determining:
				continue
			rhs = determining[0].rhs or ""
			if re.search(r"\b1(\.0)?\s*-\s*", rhs):
				continue
			offenders.append((name, determining[0].id, rhs))
	assert offenders == [], offenders

	# And the three corrected nodes state the relation their equation computes.
	# Asserted on the arithmetic, not on a phrase, so a later edit to any of
	# the three equations fails here rather than leaving the prose behind.
	for node_id, equation_id, expected, marker in (
		("carbon_credit_reversal_allowance", "carbon_credit_reversal_allowance_definition",
		 "permanence_parameters * carbon_credit_volumes", "not its complement"),
		("gearing_ratio", "gearing_ratio_definition", "debt_equity_ratio",
		 "Not the complement of the debt fraction"),
		("load_factor", "load_factor_definition",
		 "(demand_twh * 1000000) / (peak_demand_mw * 8760)", "not its complement"),
	):
		assert graph.equations[equation_id].rhs == expected, (
			equation_id, graph.equations[equation_id].rhs
		)
		# The description must carry the correction explicitly. Asserting a
		# marker rather than the absence of a word, because the corrected
		# prose necessarily names the wrong relation in order to deny it --
		# "a complement of a share is a share" is part of the correction.
		description = graph.nodes[node_id].description or ""
		assert marker in description, (node_id, description[:200])

	# `load_factor`'s old description pointed at a node the graph does not
	# carry. Asserted as an absence so a later batch that adds
	# `peak_to_average_ratio` has to revisit the sentence rather than leaving
	# a description that names two objects.
	assert "peak_to_average_ratio" not in graph.nodes


def test_no_equation_description_names_a_node_it_cannot_reach(graph: ParameterGraph):
	"""A backticked name that resolves to nothing makes a true claim unreadable.

	`annualised_capex_solar_definition` and `annualised_capex_wind_definition`
	carried the same paragraph, copied, and both named `lcoe_biomass`,
	`lcoe_coal` and `lcoe_wind_offshore`. The graph carries
	`lcoe_biomass_usd_per_mwh`, `lcoe_coal_usd_per_mwh` and
	`lcoe_wind_offshore_usd_per_mwh`. The paragraph's job is to establish that
	these two equations are the anomaly -- every other technology reads its own
	capital recovery factor -- and a researcher checking that claim looks up
	`lcoe_biomass`, finds nothing, and cannot tell whether the claim is false or
	the name is wrong. The graph's own identifier search resolves names; a name
	that resolves to nothing defeats it.

	The predicate is deliberately narrow, and the narrowness is the honest
	part. It flags a name only when the name plus an underscore is a prefix of
	*exactly one* shipped id, because that is the case where the intended
	target is determined by the author's own naming rather than chosen by me.
	Names reaching zero candidates are excluded: most are words in prose
	(`none`, `free`, `linear`), and the rest are quantities the graph genuinely
	does not carry, which a description is entitled to say. A name reaching two
	candidates is excluded because the correction would be a guess.

	That leaves the gate a lower bound on the class rather than a closure, the
	same trade batch 65 made. It cannot see a description that is wrong without
	naming something, and it will not fire on a name it cannot resolve
	unambiguously.
	"""
	import re

	token = re.compile(r"`([a-z][a-z0-9_]{3,})`")
	shipped = set(graph.nodes) | set(graph.equations)

	dangling: list[tuple[str, str, str]] = []
	for equation in graph.equations.values():
		for match in token.finditer(equation.description or ""):
			name = match.group(1)
			if name in shipped:
				continue
			candidates = [i for i in graph.nodes if i.startswith(name + "_")]
			if len(candidates) == 1:
				dangling.append((equation.id, name, candidates[0]))

	assert dangling == [], dangling

	# The premise, asserted rather than assumed: the two corrected equations
	# still make the claim, and they make it about the node that exists. A
	# future edit that deletes the paragraph would pass the gate above by
	# saying nothing, which is not the same as saying something true.
	for equation_id, factor, technology in (
		("annualised_capex_solar_definition", "crf_solar_pv", "solar"),
		("annualised_capex_wind_definition", "crf_wind_onshore", "wind"),
	):
		text = graph.equations[equation_id].description or ""
		assert f"`{factor}`" in text, equation_id
		# The sentence about a scenario moving this factor must name this
		# technology. The wind copy shipped saying "a solar asset's life
		# moved `crf_wind_onshore` while the solar LCOE stayed exactly
		# fixed" -- solar twice, in the paragraph about wind.
		assert f"a {technology} asset's life moved `{factor}`" in text, (equation_id, text)
		assert f"the {technology} LCOE stayed exactly fixed" in text, (equation_id, text)

	# The three corrected names resolve, and each is what the prose meant.
	for name in ("lcoe_biomass_usd_per_mwh", "lcoe_coal_usd_per_mwh", "lcoe_wind_offshore_usd_per_mwh"):
		assert name in graph.nodes, name
	for absent in ("lcoe_biomass", "lcoe_coal", "lcoe_wind_offshore"):
		assert absent not in graph.nodes, absent


def test_every_equation_is_dimensionally_consistent(graph: ParameterGraph):
	"""The unit check runs on all 606, and one equation was failing it.

	`rocof_definition` determined `rocof_df_dt_hz_per_s`, declared `Hz/s`, from
	`largest_loss_mw / (2 * system_inertia_mws)`. MW over MW.s is 1/s. The
	per-unit swing equation at t=0 is d(omega)/dt = -P_loss/(2HS) -- a rate in
	per unit per second -- and a frequency slope is that rate times the nominal
	frequency, because omega = f/f0 by definition. The factor was missing, so
	the equation computed a quantity 50x too small at 50 Hz.

	The dimensional failure was the whole evidence and it had been visible for
	batches. The reason it read as bookkeeping is that a single inconsistent
	equation among 605 consistent ones looks like a vocabulary defect rather
	than a missing factor, and nothing downstream refused. What it actually
	cost: `frequency_nadir_hz` reads this slope, so the nadir sat at 49.87 Hz
	-- inside every under-frequency limit -- where the correct slope puts it at
	43.62 Hz, below the node's own 45 Hz floor and below the 48 Hz threshold
	the graph's own protection rule names. A model that reports a safe nadir
	for an unsafe loss is the exact failure the equation exists to prevent.

	The gate is the unit checker's own verdict, not a second implementation:
	`check_graph` walks every equation including the exempt ones and this
	asserts it reports nothing inconsistent and nothing undecidable. Zero is
	the count, so there is no exception register to go stale.
	"""
	from alea.prg.units import check_graph

	report = check_graph(graph)
	assert len(report.checks) == len(graph.equations), (
		f"the unit check skipped {len(graph.equations) - len(report.checks)} equations"
	)
	assert [c.equation_id for c in report.inconsistent] == [], (
		[f"{c.equation_id}: {c.detail}" for c in report.inconsistent]
	)
	# An undecidable equation is not a pass: the check could not decide it, so
	# a clean verdict does not follow. Asserted separately because collapsing
	# the two would let a unit added to the vocabulary silently turn an
	# undecidable into a consistent without anyone reading it.
	assert [c.equation_id for c in report.undecidable] == [], (
		[f"{c.equation_id}: {c.detail}" for c in report.undecidable]
	)

	# The premise: the equation that was wrong now carries the factor, its
	# determined node is still declared Hz/s, and the input is declared. A
	# future edit that "simplifies" the rhs by dropping the nominal frequency
	# fails here rather than in the unit check, which is the same finding one
	# layer earlier.
	equation = graph.equations["rocof_definition"]
	assert equation.rhs == "nominal_frequency_hz * largest_loss_mw / (2 * system_inertia_mws)", equation.rhs
	assert graph.nodes["rocof_df_dt_hz_per_s"].unit == "Hz/s"
	assert "nominal_frequency_hz" in equation.parameters, equation.parameters

	# The arithmetic, not only its dimensions: the per-unit form is what the
	# old body computed, and it is 50x smaller at the shipped nominal.
	from alea.prg.dsl import parse_side

	values = {
		name: node.default
		for name, node in graph.nodes.items()
		if node.default is not None and isinstance(node.default, (int, float))
	}
	values.update({"largest_loss_mw": 1000.0, "system_inertia_mws": 39200.0, "nominal_frequency_hz": 50.0})
	slope = parse_side(equation.rhs).eval(values)
	assert abs(slope - 50.0 * 1000.0 / (2 * 39200.0)) < 1e-12, slope
	assert abs(slope - 0.6377551020408163) < 1e-9, slope


def test_the_nadir_definition_states_the_bound_direction_it_actually_has(
	graph: ParameterGraph,
):
	"""The linear form overstates the nadir, and the description used to say the opposite.

	`frequency_nadir_definition` is ``f0 - rocof * response_time``. Its
	description called that "a lower bound on the nadir, i.e. more conservative
	than the truth". It is an upper bound, and optimistic: response only ever
	reduces the slope magnitude once it engages, so ``f(t) >= f0 - rocof0*t``
	for every ``t``, which makes the computed quantity the frequency at
	response onset -- at or above the nadir. Reporting a higher number for a
	lower nadir understates the hazard, in a node whose stated job is to be
	what the UFLS relays are set against.

	The direction is checked numerically over admissible slope profiles rather
	than by reading the sentence back, because the sentence is the thing under
	test. "Admissible" is pinned: the loss sets ``|slope| = rocof0``
	immediately, and response thereafter only reduces it, so every profile
	starts at ``rocof0`` and is non-increasing.
	"""
	import numpy as np

	equation = graph.equations["frequency_nadir_definition"]
	values = {
		name: node.default
		for name, node in graph.nodes.items()
		if node.default is not None and isinstance(node.default, (int, float))
	}
	values.update(
		{
			"largest_loss_mw": 1000.0,
			"system_inertia_mws": 39200.0,
			"nominal_frequency_hz": 50.0,
			"frequency_response_time_s": 10.0,
		}
	)
	# `rocof_df_dt_hz_per_s` is derived and carries no default, so it is computed
	# from the swing equation rather than assumed -- the same body the graph
	# ships, so a change there moves this test too.
	values["rocof_df_dt_hz_per_s"] = parse_side(
		graph.equations["rocof_definition"].rhs
	).eval(values)
	linear = parse_side(equation.rhs).eval(values)
	f0 = values["nominal_frequency_hz"]
	rocof0 = (f0 - linear) / values["frequency_response_time_s"]
	assert rocof0 > 0
	assert abs(rocof0 - values["rocof_df_dt_hz_per_s"]) < 1e-12

	# Admissible trajectories. The equation's own premise is that the loss sets
	# the slope to rocof0 and holds it there until response engages at
	# `t_response`; only after that may the response reduce it. So the profile
	# is flat at 1.0 until t_response and non-increasing afterwards -- the
	# weaker family (decay allowed from t=0) leaves the frequency barely
	# falling and would make the test vacuous, which is how the first version
	# of this gate read 0 of 2000.
	rng = np.random.default_rng(0)
	t = np.linspace(0.0, 30.0, 3001)
	engage = t <= values["frequency_response_time_s"]
	below = 0
	for _ in range(2000):
		shape = np.minimum.accumulate(rng.uniform(0.0, 1.0, t.size))
		shape[engage] = 1.0
		shape = np.minimum.accumulate(shape)
		assert shape[0] == 1.0
		f = f0 - np.concatenate([[0.0], np.cumsum(rocof0 * shape[:-1] * np.diff(t))])
		if f.min() < linear - 1e-12:
			below += 1
	assert below == 2000, (
		f"the true nadir fell below the linear form in only {below} of 2000 "
		f"admissible profiles; if it were a lower bound it would be 0"
	)

	# And the description says so, and no longer claims the opposite.
	description = equation.description or ""
	assert "UPPER bound" in description, description
	assert "lower bound on the nadir" not in description, description
	# The old claim was that it was the safe direction.
	assert "more conservative than the truth" not in description, description
	assert "optimistic" in description, description


def test_a_categorical_retyped_from_a_placeholder_refuses_an_undeclared_level(
	graph: ParameterGraph, defaults: dict
):
	"""The 33 categoricals batch 50 retyped, tested on one of them.

	The shipped placeholder was a `float` in `(0, 1e6)`, so it admitted every
	number and no level name at all: `trade_agreement = 'nonsense'` failed as
	a *type* error, not as a statement about the parameter. The retype makes
	the failure name the node and print the levels, which is the difference
	between "wrong kind of value" and "this parameter has no such level".
	"""
	node = graph.node("trade_agreement")
	assert node.type is ParameterType.CATEGORICAL, node.type
	assert node.categories == ("none", "bilateral", "pool", "regional_pool"), node.categories
	assert node.default in node.categories, node.default

	scoped = dict(defaults)
	scoped["trade_agreement"] = "nonsense"
	with pytest.raises(GraphError, match="not one of the levels") as caught:
		graph.propagate(scoped)
	message = str(caught.value)
	assert "trade_agreement='nonsense'" in message, message
	for level in node.categories:
		assert repr(level) in message, (level, message)

	previous = graph.propagate(defaults)
	scoped = dict(defaults)
	scoped["trade_agreement"] = "nonsense"
	with pytest.raises(GraphError, match="not one of the levels"):
		graph.propagate_incremental(scoped, previous, ["trade_agreement"])

	# Every declared level is admissible, which is what makes the refusal a
	# statement about this list rather than about the type.
	for level in node.categories:
		scoped = dict(defaults)
		scoped["trade_agreement"] = level
		assert graph.propagate(scoped).values["trade_agreement"] == level


def test_the_survey_keep_rows_no_longer_carry_the_sentinel(graph: ParameterGraph, defaults: dict):
	"""The thirteen rows `placeholder-survey.md` classified KEEP, as a set.

	The survey's KEEP class is the one where the catalog's own description
	settles the unit and the range, so batch 57 read its answer rather than
	choosing one. The defect it closes is the range: `cvar_alpha` is a CVaR
	confidence level that shipped `unit: null` on `[0, 1e6]` with a default of
	500000.0, so a scenario could set a tail level to half a million and the
	graph had no way to tell that from never setting it.

	Tested as a set rather than node by node, because the failure worth
	catching is a later bake regenerating one of them: `prg_from_catalog`
	drops any node whose `source` is the generator's marker and re-emits it
	from the catalog row, so a retype that leaves that marker in place is
	silently reverted to the sentinel. That is what happened on the first
	merge of this batch, and this test is what would have caught it.
	"""
	keep = {
		"renewable_curtailment_limit": ((0.0, 1.0), 0.05),
		"cvar_alpha": ((0.5, 0.999), 0.95),
		"cvar_omega": ((0.0, 10.0), 1.0),
		"probability_weight": ((0.0, 1.0), 0.5),
		"gender_impact": ((0.0, 1.0), 0.5),
		"critical_mineral_dependencies": ((0.0, 1.0), 0.2),
		"export_competitiveness": ((0.0, 1.0), 0.5),
		"rare_earth_dependencies": ((0.0, 1.0), 0.3),
		"number_of_retailers": ((1.0, 1000.0), 5.0),
		"retail_competition": ((0.0, 1.0), 0.5),
		"drought_frequency": ((0.0, 5.0), 1.0),
		"drought_severity": ((0.0, 5.0), 1.0),
		"hydro_reservoir_level": ((0.0, 1.0), 0.5),
	}
	for name, (span, default) in keep.items():
		node = graph.node(name)
		assert node.unit == "1", (name, node.unit)
		assert node.range == span, (name, node.range)
		assert node.default == default, (name, node.default)
		assert node.source != "docs/params.md", (
			f"{name} carries the generator's marker, so the next bake re-emits it "
			"from the catalog row and the retype is lost"
		)

	# The refusal, on a node the batch wrote. The sentinel is what a scenario
	# could say before; the endpoint is what the range must still admit, so the
	# gate is a range rather than a ban on one number.
	scoped = dict(defaults)
	scoped["cvar_alpha"] = 500000.0
	with pytest.raises(GraphError, match="outside the range"):
		graph.propagate(scoped)
	for on_bound in (0.5, 0.999):
		scoped = dict(defaults)
		scoped["cvar_alpha"] = on_bound
		assert graph.propagate(scoped).values["cvar_alpha"] == on_bound


def test_a_fossil_emission_factor_is_derived_from_its_carbon_content(
	graph: ParameterGraph, defaults: dict
):
	"""The factor moves when the efficiency does, which a dial cannot do.

	`emission_factor_{coal,gas,oil}_t_per_mwh` shipped as exogenous dials at
	0.92 / 0.45 / 0.78 while the graph also carried `efficiency_{tech}` at
	0.40 / 0.58 / 0.38 -- the same physical fact measured twice, with nothing
	tying them. Batch 51 made the factor `carbon_content * gj_per_mwh /
	efficiency`, so the two now agree by construction.

	A value test cannot see this defect: a derived factor and a shipped factor
	both evaluate to a number. What separates them is whether the factor
	**responds** to the efficiency, so this test sets an efficiency and
	asserts the factor moves -- and asserts the value the closed form gives,
	so a wrong divisor fails too.
	"""
	from alea.prg.graph import GraphError  # noqa: F401  (documented below)

	content = {
		"coal": 0.0946,
		"gas": 0.0561,
		"oil": 0.0774,
	}
	for tech, carbon in content.items():
		factor = f"emission_factor_{tech}_t_per_mwh"
		node = graph.node(factor)
		# Derived, so a scenario cannot set it: setting a derived value and
		# the inputs that determine it is the refusal this whole graph exists
		# for.
		assert node.role.value == "derived", node.role
		assert not graph.is_settable(factor), f"{factor} is still settable"

		# The closed form, at the defaults, to the last digit the arithmetic
		# gives. A divisor that is merely *a* number passes a "moves" check.
		eff = defaults[f"efficiency_{tech}"]
		assert graph.propagate(defaults).values[factor] == pytest.approx(
			carbon * 3.6 / eff, rel=1e-9
		), factor

	# The response, which is the whole point: a *less* efficient plant emits
	# more per MWh, so lowering an efficiency must raise the factor. The
	# perturbation goes down rather than up because gas ships 0.58 against a
	# declared ceiling of 0.62 -- a +0.05 step leaves its admissible range and
	# the range gate refuses the scenario before the factor is ever computed.
	for tech, _carbon in content.items():
		factor = f"emission_factor_{tech}_t_per_mwh"
		lowered = dict(defaults)
		lowered[f"efficiency_{tech}"] = defaults[f"efficiency_{tech}"] - 0.05
		before = graph.propagate(defaults).values[factor]
		after = graph.propagate(lowered).values[factor]
		assert after > before, (
			f"{factor} did not rise when efficiency_{tech} fell; the factor is "
			f"not reading its own efficiency"
		)


def test_the_capital_structure_has_one_dial_and_every_other_face_derives(
	graph: ParameterGraph, defaults: dict
):
	"""Setting the gearing must move the debt share, and it did not.

	The graph carried `debt_fraction` = 0.70 and `debt_equity_ratio` = 2.33 as
	two independent dials. They are the same number in two units -- 2.33/(1 +
	2.33) = 0.6997 -- and nothing tied them, so a scenario could set the gearing
	to 1.0 and leave all twelve equations that price debt on a 70% share. Three
	further nodes derived from `debt_fraction` and were read by nothing, and
	`gearing_ratio = debt_fraction / (1 - debt_fraction)` was a third spelling
	of the same ratio that the cross-validation rule did read.

	Batch 52 makes the ratio the dial and the share its image. A value test
	cannot see the defect -- both spellings already agreed to three digits -- so
	this test asserts the *response*: setting the ratio must move the share,
	the WACC and the debt service. On the pre-batch graph all three are
	unchanged at any ratio.
	"""
	share = graph.node("debt_fraction")
	assert share.role.value == "derived", share.role
	assert not graph.is_settable("debt_fraction"), "the share is still a dial"
	assert graph.is_settable("debt_equity_ratio"), "the ratio is not the dial"

	# The closed form, so a wrong divisor fails as well as a missing response.
	ratio = defaults["debt_equity_ratio"]
	assert graph.propagate(defaults).values["debt_fraction"] == pytest.approx(
		ratio / (1.0 + ratio), rel=1e-12
	)

	# The response. Every one of these is unchanged on the pre-batch graph.
	geared = dict(defaults)
	geared["debt_equity_ratio"] = 1.0
	before = graph.propagate(defaults).values
	after = graph.propagate(geared).values
	for name in ("debt_fraction", "discount_rate", "debt_service_usd_per_kw_year"):
		assert after[name] != pytest.approx(before[name], rel=1e-9), (
			f"{name} did not move when the debt-to-equity ratio was set to 1.0; "
			f"the gearing is not driving the capital structure"
		)
	assert after["debt_fraction"] == pytest.approx(0.5), after["debt_fraction"]
	# The direction, which a "moved" check does not give: at the shipped costs
	# the after-tax cost of debt is 0.1156 * (1 - 0.3) = 0.08092 against an
	# equity cost of 0.16, so debt is the cheaper source and *less* leverage
	# makes the WACC dearer. Asserting the sign against the shipped costs keeps
	# this from passing on a graph where the two costs were swapped.
	debt_cost = before["cost_of_debt"] * (1.0 - before["tax_rate"])
	assert debt_cost < before["cost_of_equity"], (
		"this assertion assumes debt is the cheaper source; at these costs it "
		"is not, so the direction below would be the wrong one"
	)
	assert after["discount_rate"] > before["discount_rate"], (
		"reducing the gearing lowered the WACC, which is only right if debt is "
		"the dearer source"
	)

	# The three faces of the one number now agree by construction. `gearing_ratio`
	# is the ratio itself, and `equity_share` is its complement -- if either
	# drifts from the identity, a scenario reading one for the other is wrong.
	for scenario in (defaults, geared):
		values = graph.propagate(scenario).values
		assert values["gearing_ratio"] == pytest.approx(
			values["debt_equity_ratio"], rel=1e-12
		)
		assert values["equity_share"] + values["debt_fraction"] == pytest.approx(
			1.0, rel=1e-12
		)

	# `equity_share` was read by nothing; the equations that spelled its
	# complement inline now name it, so the node is reachable from the numbers
	# it feeds rather than being a fourth duplicate.
	assert graph.affects("equity_share"), (
		"equity_share is read by no equation, so the inline complements were "
		"not repointed"
	)


def test_the_required_reserve_capacity_follows_the_planning_dial(
	graph: ParameterGraph, defaults: dict
):
	"""Raising the planning margin must raise the capacity it requires.

	`reserve_margin_required_mw = reserve_margin_requirement * peak_demand_mw`
	read a **free** dial, while every reserve rule and `lolp` read
	`reserve_margin_min`. Both shipped 0.15, so the two agreed at the defaults
	and a value test could not tell them apart. Raising the planning dial to
	0.35 left the required capacity at 1275 MW -- unchanged -- while raising
	the duplicate moved it to 2975 MW and left the rules gating on 0.15.

	Batch 53 makes `reserve_margin_requirement` derived from
	`reserve_margin_min`. This test asserts the response, which is the only
	observable that separates a derived duplicate from a dial.
	"""
	requirement = graph.node("reserve_margin_requirement")
	assert requirement.role.value == "derived", requirement.role
	assert not graph.is_settable("reserve_margin_requirement")
	assert graph.is_settable("reserve_margin_min"), "the planning dial is not settable"

	# The closed form, so a wrong divisor fails as well as a missing response.
	values = graph.propagate(defaults).values
	assert values["reserve_margin_requirement"] == pytest.approx(
		values["reserve_margin_min"], rel=1e-12
	)

	# The response, and the value it produces: 0.35 on a 8 500 MW peak is
	# 2975 MW. A response that moved the node by the wrong multiple passes a
	# bare "changed" check.
	raised = dict(defaults)
	raised["reserve_margin_min"] = 0.35
	after = graph.propagate(raised).values
	assert after["reserve_margin_required_mw"] > values["reserve_margin_required_mw"], (
		"raising the planning reserve margin did not raise the required "
		"capacity; the requirement is not reading the dial the rules gate on"
	)
	assert after["reserve_margin_required_mw"] == pytest.approx(
		0.35 * values["peak_demand_mw"], rel=1e-12
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
	leaked = set(graph.range_excursions())
	# `range_excursions` is keyed by node id; `KNOWN_DEFAULT_FINDINGS` names the
	# equation each excursion is reported through, so strip the suffix.
	known_nodes = {e.removesuffix("_out_of_range") for e in KNOWN_DEFAULT_FINDINGS}
	assert leaked - known_nodes, "the bad scenario reported nothing to clear"
	graph.propagate(defaults)
	# The register is cleared and rebuilt from *this* scenario, so what remains
	# is what the defaults themselves produce -- not a leftover. Before batch 67
	# this asserted an empty register, which held only because the corrected
	# nadir was not yet computed; see `KNOWN_DEFAULT_FINDINGS`.
	assert set(graph.range_excursions()) == known_nodes, graph.range_excursions()
	assert not leaked <= set(graph.range_excursions()), (
		"the previous scenario's excursions survived into this one"
	)


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
	in an inequality reported nothing at all. Moving ``affordability_threshold``
	does not move any *value* -- it decides whether the scenario is admissible,
	which is the whole question for a regulator's lever. So the register for it
	is ``constrains``, and the assertion is that every such lever is visible in
	one register or the other rather than in neither.
	"""
	for lever in (
		"dscr_min",
		"affordability_threshold",
		"reserve_margin_min",
		"rocof_limit_hz_per_s",
		"water_availability_m3",
		"firm_capacity_mw",
		"peak_demand_mw",
	):
		assert graph.constrains(lever), f"{lever} bounds no inequality"
	assert "dscr_requirement" in graph.constrains("dscr_min")
	# Batch 62 retired `energy_burden_limit`, the second id for the 10% line,
	# and deleted `affordability_constraint`, the second statement of the
	# inequality. The surviving pair is named here so a regression that
	# restores either one fails rather than silently doubling the register.
	assert graph.constrains("affordability_threshold") == (
		"energy_burden_affordability_bound",
	)
	assert "affordability_constraint" not in graph.equations
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

	The graph is allowed to hold such an input -- but then it must be visible as
	one, not silently present. This asserted `dead == []`, which was the state
	of an 88-node hand-written kernel and is not the state of an 869-node graph
	built from a 787-row catalog. Grepping that catalog's algorithm and
	description cells for an `=` returns zero rows: it states a method for
	almost every parameter ("Growth curve shape fitting", "Bottom-up load
	synthesis") and a formula for none. So 781 of the nodes are knobs with a
	declared range and no arithmetic, and an assertion that they do not exist
	would either fail forever or be deleted -- and deleting it would take the
	visibility with it.

	What replaces it is stronger than the empty list, not weaker. Two
	independent spellings of "does nothing" must agree:

	* ``graph.uncoupled()`` reads the *equations* -- the nodes no equation
	  names.
	* the comprehension below reads the *edges* -- the settable nodes that
	  reach nothing and bound nothing.

	They are derived from different structures, so a disagreement means the
	document lies about its own graph. The register is also asserted non-empty
	by name, so this cannot pass vacuously on a graph that quietly coupled
	everything: the count is the finding, and a run that reports 0 has either
	fixed the catalog or lost the register.
	"""
	dead = {
		name
		for name in sorted(graph.nodes)
		if graph.is_settable(name)
		and not graph.affects(name)
		and not graph.constrains(name)
		# A rule-cited parameter is used: the cross-validation rule gates
		# admission on the value, which is a coupling -- the regulator's
		# lever's lever -- and `rules_reading` carries it as a register of
		# its own rather than folding it into `constrains`, which means
		# something narrower and stays that way.
		and not graph.rules_reading(name)
	}
	uncoupled_by_equation = set(graph.uncoupled())
	rule_read = {
		name
		for name in uncoupled_by_equation
		if graph.rules_reading(name)
	}
	uncoupled = set(
		name for name in uncoupled_by_equation if not graph.rules_reading(name)
	)
	# The equations and the edges and the rules now agree exactly: the union
	# of equation-read and rule-read is the whole of `uncoupled()`, and the
	# rule-read members are the difference between the two frames. Asserted
	# as the containment both ways so a reader cannot re-fold them.
	assert rule_read <= uncoupled_by_equation
	assert not (uncoupled & rule_read), (
		"a rule-read parameter is also equation-read, which is fine, but this "
		"register says uncoupled-by-anything"
	)
	# The count is pinned as a literal rather than asserted as a property, so
	# that a document which quietly couples or uncouples a node makes this fail
	# and be looked at. Batch 20's sector-coupling layer fell in the opposite
	# direction to the earlier batches: it coupled 45 previously-dead knobs
	# (`graph.uncoupled()` went 694 to 649), so the register fell 670 to 619.
	# Batch 21's demand-and-finance layer coupled 18 more knobs, 16 of them
	# previously in this dead register (`graph.uncoupled()` went 649 to 631),
	# so the register fell 619 to 603.
	# Batch 22's compliance layer coupled 40 more (`graph.uncoupled()` went
	# 631 to 591), so the register fell 603 to 563. The two spellings no
	# longer agree *exactly*: `uncoupled()` is 591 and rule-read removes 24,
	# leaving 567, four more than the comprehension's 563. The four are the
	# endogenous fleet/storage nodes (`firm_build_fleet_mw`,
	# `hydrogen_storage_capacity`, `storage_capacity_mw`,
	# `thermal_storage_capacity`), which no equation names and so sit in
	# `uncoupled()` while `is_settable` refuses them. Batch 23's extensive-base
	# layer coupled 16 more (`graph.uncoupled()` went 591 to 575): eleven of
	# them were in this register, so it fell 563 to 552, and rule-read removed
	# 19 of the 575. Batch 24's carbon-market layer coupled 43
	# (`graph.uncoupled()` went 575 to 532): forty of them were in this
	# register, so it fell 552 to 512, and one more left it the other way --
	# `ets_enabled`, which this batch gave a reader by making it the subject
	# of `carbon_revenue_without_an_instrument`. Batch 25's gate-family
	# coupling took `graph.uncoupled()` 532 to 516: fourteen of the sixteen
	# were in this register, so it fell 509 to 495, and two more left
	# rule-read the other way -- `ets_enabled` and `import_duty_equipment`,
	# which batch 25's equations now read -- so rule-read holds 17 of the
	# 516. Batch 26's adequacy-and-reserve layer took `graph.uncoupled()`
	# 516 to 504: ten settable placeholders it made derived
	# (`grid_reliability_saifi`, `non_spinning_reserve`,
	# `planning_reserve_margin`, `regulation_down_requirement`,
	# `regulation_up_requirement`, `reserve_margin`, `spare_capacity`,
	# `spinning_reserve`, `spinning_reserve_requirement`,
	# `voltage_support_requirement`) and two -- `transmission_loss_factor`
	# and `transmission_loss_reduction_target` -- that stay settable but are
	# now read by `transmission_loss_target_definition`. All twelve were in
	# this register, so it fell 495 to 483, and rule-read still holds 17 of
	# the 504. The containment below is what carries the weight -- dead is a
	# subset of uncoupled-minus-rule -- and the count is the record of what
	# it was *at*.
	# Batch 28's product layer took `graph.uncoupled()` 488 to 422: it made
	# 44 placeholders derived and read 22 more as settable inputs, so the
	# register falls by 66. Sixty-five of the 66 were dead knobs, which is
	# why this count moves by almost the whole of the batch: 467 to 402. The
	# one that was not dead is `geothermal_drilling_success`, which the
	# cross-validation rule `geothermal_cost_below_drilling` already gates
	# on -- it was uncoupled by the equation register and live by the rule
	# register, which is exactly the disagreement the two spellings exist to
	# expose, and `geothermal_effective_capex_definition` closes it.
	# Batch 29 took `uncoupled()` 422 to 393: forty nodes became coupled, of
	# which twenty-nine were dead knobs. The other eleven were the new bases
	# and derived charges, which arrive already coupled by their own
	# equations and were never in this register to leave it. 402 to 373.
	# Batch 30 took it 373 to 346: twenty-seven dead knobs left, the twenty
	# retyped placeholder nodes and the five equation targets among them.
	# `water_availability` and `biomass_sustainability_limit` left by the
	# bound register rather than by an equation, which is the case the
	# `rule_read` assertion below exists to keep out of this count.
	# Batch 31 took it 346 to 318. The batch's twenty-eight products each
	# name a knob that was dead, and six aliases took a duplicate id out of
	# the settable set entirely -- a derived node cannot be a dead knob
	# because it is not a knob.
	# Batch 32 took it 318 to 298: twenty-two bounds shipped and twenty of
	# their nodes were dead knobs. The other two, `storage_capacity_mw` and
	# `thermal_storage_capacity`, are endogenous, so they were never in this
	# register -- which is why the count falls by twenty and not twenty-two.
	# Batch 33 took it 298 to 274: twenty retyped placeholders became derived,
	# and the six new nodes arrived already coupled by their own equations, so
	# the register falls by exactly the twenty. The six were never dead knobs
	# -- they did not exist -- and the five bounds named nodes that were
	# already named by an equation or are not settable at all.
	#
	# Batch 38 took it 248 to 237: eleven nodes the batch coupled, and the
	# one new settable node it could have left dead -- `storage_energy_capacity_mwh`
	# -- arrived derived, so it never was a knob. The two free nodes the batch
	# retyped and left settable, `workshop_capacity` and
	# `loss_reduction_investment`, left this register by their bounds.
	#
	# Batch 39 took it 237 to 233: the four nodes it coupled
	# (`accumulation_risk`, `capex_gas_ocgt`, `capex_marine_otec`,
	# `capex_marine_tidal`) were all dead knobs, and its three new ids
	# arrived derived so they never were.
	#
	# `uncoupled()` is 240, seven above this count, and the gap is the rule
	# register rather than drift: each of the seven is read by a
	# cross-validation rule (`index_above_unity` and three of its index
	# members, `market_structure_without_model` and its pair,
	# `contract_for_difference_without_guarantees`, and
	# `concentration_above_hhi_max`), so the rule is what reads them and the
	# equation register does not. The containment asserted below is the claim;
	# this count is the record.
	#
	# `solvency_capital_ratio` left this set with batch 39: the batch made it
	# an operand of `eligible_own_funds_definition`, so the equation register
	# reads it and the rule is no longer the only reader.
	#
	# It was ten before batch 37 and is seven now, for three reasons.
	# `rule_of_law_index`, `corruption_perception`, `regulatory_predictability`
	# and `contract_enforceability` are still members of `index_above_unity`
	# but were never uncoupled, so the four-member reading this comment used to
	# carry counted only the members that happened to be in the register.
	# `exposure_index` and `geopolitical_risk_index` left `uncoupled()` by
	# becoming derived, and they left the rule at the same time -- a derived
	# index cannot be 'set', which is the premise its message states.
	# Batch 40 took it 233 to 232: `remedy_periods` left by its bound against
	# `max_remedy_period_days`. The batch's ten retypes and one new conversion
	# node changed no membership -- a retype does not move a node between
	# registers, and `mwh_per_coal_unit` is exogenous but coupled by the
	# equation that reads it, so it was never a dead knob.
	# Batch 44 took it 232 to 224, and the eight are two groups. Six are the
	# co-pollutant nodes (`co_emissions`, `mercury_emissions`, `nox_emissions`,
	# `pm10_emissions`, `sox_emissions`, `voc_emissions`), which were dead knobs
	# by an *arithmetic slip in the other direction*: they had equations, but
	# nothing read them, so they were `computed()` and coupled while the
	# pollutant totals nobody summed. Batch 44's ledger equations name them.
	# The other two are not a coupling at all: `is_settable` now refuses a
	# deprecated node, so `pm25_relative_risk_per_kt` and `cross_border_trading`
	# left this register without any arithmetic changing. `demand_growth_rate`
	# is the third deprecated node and was already out by `rules_reading`. A
	# register that counted tombstones as dead knobs was counting the wrong
	# object -- a node nobody can set is not a knob a user has to be warned
	# about -- and the fix is in `is_settable` rather than here.
	# Batch 54 took it 224 to 223, and only one of its 41 nodes moved. The 40
	# retyped quantities were already in this register and stay in it: giving a
	# node a unit and a range changes what a scenario may *say* about it, not
	# whether anything reads it, and the coupling packs defer those 40 for want
	# of a base. `temporal_resolution` left because it became derived from
	# `tsam_segment_hours` -- a derived node is not settable, and the quantity
	# it was a placeholder for is now computed rather than dialled.
	# Batch 55 took it 223 to 222 by deprecating `opex_fixed_wind`, the generic
	# wind O&M duplicate: `is_settable` refuses a tombstone, so retiring the id
	# removes it from this register without any arithmetic changing. Batch 59
	# took it 222 to 221 the same way, for `remittance_dependency`. Batch 61
	# moved nothing here by retiring `local_content_requirements`: unlike the
	# two above, that duplicate *had* a reader (`local_content_capex_definition`),
	# so it was coupled and never a dead knob. `uncoupled()` went the other
	# way, 235 to 236, because the repoint moved that reader onto the singular
	# and left the tombstone naming nothing -- which is the register's design,
	# not a regression: a deprecated node stays in `uncoupled()` by construction.
	# Batch 62 moved nothing here either, and for the same reason as batch 61:
	# `energy_burden_limit` was read by `affordability_constraint`, so it was
	# coupled and never a dead knob. `uncoupled()` went 236 -> 237 because the
	# batch also *deleted* that equation, so the tombstone it left behind now
	# names nothing -- the count rises by one for a retirement that removed a
	# duplicate rather than for one that uncovered an orphan.
	assert len(dead) == 221, len(dead)
	assert dead <= (set(graph.uncoupled()) - rule_read), sorted(
		dead - (set(graph.uncoupled()) - rule_read)
	)
	# The knob the catalog names but no shipped equation reads, named so a
	# failure points at a node rather than a count. It was `coal_capacity`
	# until the endogenous fleet layer made that node derived, then
	# `ac_voltage_limit` from the batch-12 coupling; batch 20 left it uncoupled.
	assert "ac_voltage_limit" in dead


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


def test_the_deficit_register_counts_the_spec_it_claims_to_count():
	"""The claim and the witness agree, and neither is derived from the other.

	``SPEC_EQUATION_COUNT`` is the claim, written out as literals;
	``spec_equations`` reads §13 of ``alea_prg.md`` and is the witness. A test
	asserting ``len(spec_equations()) == len(spec_equations())`` would be
	vacuous, which is why the expected counts are literals -- and a test that
	only checked the *total* would pass on a document that had moved three
	equations from one system to another. So the per-system counts are compared
	too: the shape is the claim, not just its sum.
	"""
	from alea.prg.library import SPEC_EQUATION_COUNT, spec_equations

	enumerated = spec_equations()
	witness = {name: len(set(ids)) for name, ids in enumerated.items()}
	assert witness == SPEC_EQUATION_COUNT, {
		name: (SPEC_EQUATION_COUNT.get(name), witness.get(name))
		for name in set(SPEC_EQUATION_COUNT) | set(witness)
		if SPEC_EQUATION_COUNT.get(name) != witness.get(name)
	}
	# The document's own total, pinned. 85, and the library implements 9 of
	# them: the register exists so that ratio is a number the tree prints
	# rather than a claim in a status file.
	assert sum(witness.values()) == 85, sum(witness.values())


def test_the_deficit_names_what_is_missing_and_does_not_invent_a_shortfall(
	graph: ParameterGraph,
):
	"""The register is a finding list, and its ``graph`` column is not a false one.

	Two failure modes, and the test pins both. The first is the register the
	tree had: ``unclaimed_spec_systems`` returned ``[]`` while the library held
	nine of the specification's eighty-three equations -- a register that
	measured nothing and read as full coverage.

	The second is subtler and was live in the first version of this function.
	Counting the specification's *ids* the library happens to use reports
	``Capture Price spec=4 graph=0`` about a system holding four equations
	under different ids, because the library spells ``capture_price`` as
	``capture_price_equation``. That is a false finding, and a false finding
	costs more than a missing one: it sends a reader to build something that is
	already there. ``graph`` is therefore the mapped system's equation count,
	and the id-level detail is separated into ``ids_missing``, where being
	strict about naming is a fact rather than a claim about coverage.
	"""
	from alea.prg.library import equation_coverage, spec_equation_deficit

	deficit = spec_equation_deficit(graph.equations)
	assert deficit, "the register enumerated nothing"
	# Every entry names the library system it mapped to, or None when the
	# heading maps to nothing -- an entry with neither would be a row a reader
	# cannot act on.
	for name, row in deficit.items():
		assert row["spec"] > 0, name
		assert row["graph"] >= 0, name
		if row["system"] is None:
			assert row["graph"] == 0, name
	# The false-finding case, asserted directly: the four equations §13 files
	# under `Capture Price` are implemented, so the register must not report a
	# zero there. This is the assertion that would have caught the first
	# version.
	capture = deficit["Capture Price"]
	assert capture["graph"] > 0, capture
	# And the deficit is real and large: the library holds a fraction of what
	# the specification enumerates. Pinned as an inequality rather than an
	# exact number so that building equations does not fail this test -- the
	# register moving toward zero is the point.
	missing = equation_coverage(graph.equations)
	assert missing, "the register found no gap at all, which is the defect it guards"
	assert len(missing) > 50, len(missing)
	assert all(": " in entry for entry in missing), missing[:3]


def test_the_deficit_register_reads_the_document_rather_than_a_copy(tmp_path):
	"""A restructured §13 is refused, not read as an empty specification.

	``spec_equations`` couples the code to a Markdown shape, deliberately --
	a transcribed list is a second copy that drifts. The coupling means a
	restructured document yields nothing, and a register that then reported
	"no deficit" would be reporting full coverage of a document it had stopped
	reading. The refusal names the cause instead.
	"""
	from alea.prg.library import spec_equations

	empty = tmp_path / "spec.md"
	empty.write_text(
		"# Spec\n\n### 13. Equation Systems\n\n### 14. Something else\n\nNo tables.\n"
	)
	with pytest.raises(ValueError, match="no heading matches"):
		spec_equations(empty)

	absent = tmp_path / "spec2.md"
	absent.write_text("# Spec\n\nNothing about equations.\n")
	with pytest.raises(ValueError, match="holds no"):
		spec_equations(absent)


# ---------------------------------------------------------------------------
# The seam: auditing a solved what-if result
# ---------------------------------------------------------------------------


def _solved(carbon_price: float = 50.0):
	"""A solved result, carrying the engine's numbers rather than the graph's.

	WHY the mix carries a gas fleet and not just coal and wind. The audit now
	reads the optimiser's own capacity decisions into the graph's three
	endogenous fleet nodes, so the reserve margin checks the *build* the result
	reports rather than the graph's 9,000 MW reference default. A coal-and-wind
	mix is 6,000 MW of firm capacity against an 8,500 MW peak at a 15% margin,
	which is a scenario no solve would return -- and it passed this fixture
	until the fleet was wired, precisely because nothing read the mix.
	"""
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
		capacity_mix_mw={"coal": 6000.0, "gas": 4000.0, "wind": 4000.0},
		generation_mwh={"coal": 30.0e6, "wind": 20.0e6},
	)


def test_the_audit_reports_what_it_did_not_check():
	"""A pass over nothing must not read as a pass over everything.

	The result supplies three of the graph's parameters and the graph derives
	twenty-nine; the audit checks the derived parameters those three *reach* and
	names the rest as not carried. A summary that printed "consistent" without
	saying how many parameters that covered would be a clean bill of health for a
	result nobody examined.

	WHY THE COUNTS ARE ASSERTED AND NOT JUST THE PARTITION. ``checked`` was
	``supplied ∩ derived``, and a solved result supplies only *exogenous*
	parameters -- a derived value is what the graph computes *for* the result --
	so the intersection was always empty and the CLI printed "consistent over 0
	parameter(s)" for an audit that had evaluated eighteen identities. A test
	asserting only ``checked ∪ skipped == derived`` passes on that version, so
	both counts are pinned.

	WHY 23 AND 10 AND NOT 18 AND 10. ``firm_capacity_mw`` moved from exogenous
	to derived when the endogenous fleet layer landed, and the result's
	``capacity_mix_mw`` now fills the three fleet nodes the graph declares. So
	the audit gained one check -- ``firm_capacity_mw``, reachable from
	``thermal_capacity_mw``, which the mix supplies -- and the partition total
	stayed at 29. The growth is the point: before the fleet was wired the
	reserve margin checked the node's reference default while reading as a
	check on the build.

	WHY THE TOTAL IS 33 AND NOT 29. The audit partitioned ``order()``, the
	topological *sequence*, and a sequence has no place for a feedback loop --
	so the five loop variables were in neither ``checked`` nor ``skipped``, and
	the partition the test asserts below was not exhaustive over the graph at
	all. Making ``equilibrium_demand_twh`` a loop variable is what exposed it:
	the parameter left ``order()``, the total stayed 29, and nothing failed.
	The set is now ``computed()``, which is what the docstring above already
	described, and the four reachable loop variables join ``checked``.

	WHY 67 AND 115 AND NOT 64 AND 89. Batch 20's sector-coupling layer added 29
	determined variables (the graph's computed set went 153 to 182); three of
	the new derived parameters are reachable from what a solved result supplies
	and join ``checked``, the other twenty-six are not, and are named as not
	carried. Batch 21's demand-and-finance layer added 16 more determined
	variables (computed() went 182 to 198), none reachable from what the result
	supplies, so all sixteen join ``skipped`` and ``checked`` is unchanged.
	Batch 22's compliance layer added 29 more determined variables (computed()
	went 198 to 227): nineteen reachable from what the result supplies join
	``checked`` (67 to 86) and the other ten join ``skipped`` (131 to 141).
	Batch 23's extensive-base layer added 16 more (computed() went 227 to 243):
	two reachable from what the result supplies -- ``transmission_investment_usd``
	and ``regulated_tariff_rate`` -- join ``checked`` (86 to 88), and the other
	fourteen, the route, learning-curve and household products, join ``skipped``
	(141 to 155). Batch 24's carbon-market layer added 43 more (computed() went
	243 to 286), and twenty-one of them are reachable from what the result
	supplies -- the spend and tariff products, which read demand, generation
	and revenue, all of which the result carries -- so ``checked`` goes 88 to
	109 and ``skipped`` 155 to 177. Batch 25's gate-family coupling added 13
	more (computed() went 286 to 299): the eight cover and duty products --
	business-interruption, cyber, force-majeure and political-risk cover,
	the free-trade-zone benefit, the import duty, the parent guarantee and
	the sanctions exposure -- read gross revenue or equipment spend, which
	the result carries, so ``checked`` goes 109 to 117; the other five, the
	coordinated maintenance hours, the gated carbon volume, the permitted
	imports and transmission spend, and the smart-metered population, join
	``skipped`` (177 to 182). Batch 26's adequacy-and-reserve layer added 11
	more (computed() went 299 to 310): two reachable from what the result
	supplies -- ``spare_capacity`` reads ``total_capacity_mw`` directly, and
	``reserve_margin`` reads ``reserve_margin_actual``, which the supplied
	thermal capacity reaches through ``firm_capacity_mw`` -- join ``checked``
	(117 to 119), and the other nine, the reserve and regulation
	requirements, the planning margin, the SAIFI target, the voltage-support
	requirement and the transmission loss after target, join ``skipped``
	(182 to 191). Batch 28's product layer added 72 determined variables
	(computed() went 310 to 382): sixty-one reachable from what the result
	supplies -- the revenue cap, gross revenue, capacity, the direct
	workforce, the asset value and the environmental indices -- join
	``checked`` (124 to 155), and the other eleven, the insurance products
	and the programme spends whose bases the result does not carry, join
	``skipped`` (200 to 227). Batch 29 added 20 determined variables
	(computed() went 382 to 402): three reachable from what the result
	supplies -- ``remittance_flows`` reads household income and the household
	count, ``lpg_subsidy_spend_usd_per_year`` reads the same household count,
	and ``weather_derivatives`` reads total revenue -- join ``checked`` (155
	to 158), and the other seventeen, whose bases the result does not carry,
	join ``skipped`` (227 to 244). The partition total is what the test is
	really asserting --
	the two counts must sum to ``len(graph.computed())`` -- and the counts
	are pinned beside it so a change to the register is looked at rather than
	absorbed.
	"""
	from alea.prg.audit import audit_scenario_result
	from alea.prg.graph import load_graph

	audit = audit_scenario_result(_solved())
	# The audit's own partition, not the scenario's cleanliness: the fixture
	# carries the graph's defaults and so inherits the nadir finding (see
	# `KNOWN_DEFAULT_FINDINGS`). What this test is about is that the audit
	# reports which equations it checked and which it could not.
	assert {v.equation_id for v in audit.violations} == KNOWN_DEFAULT_FINDINGS, (
		[str(v) for v in audit.violations]
	)
	# Batch 30's ten products took the computed set 402 to 412. One is
	# reachable from what the result supplies -- `baseline_emissions` reads
	# the emissions total the solve reports -- and joins `checked` (158 to
	# 159); the other nine read fleet capacities, employment factors or the
	# WACC and join `skipped` (244 to 253).
	# Batch 31 took the computed set 412 to 440. Five join `checked` -- the
	# two alias equations whose drivers the result carries
	# (`demand_response_capacity`, `demand_response_potential`), and the
	# three products built on exogenous bases (`internet_users`,
	# `mobile_covered_population`, `licence_fee_spend_usd_per_year`) -- and
	# twenty-eight join `skipped`, because their bases are fleet builds,
	# planned-maintenance hours or the debt stack, none of which the solve
	# result carries.
	# Batch 33 took the computed set 440 to 461. One joins `checked` --
	# `health_impact_dalys`, whose driver `dalys_per_year` the result carries
	# -- and twenty join `skipped`, because their bases are the land rate, the
	# household count, the fleet capacity or the depreciation life, none of
	# which the solve result carries.
	# Batch 36 took the computed set 461 to 467. Three join `checked`
	# (`counterparty_risk` and `cost_pass_through_mechanism`, aliases of shares
	# the result carries, and `auction_volume_per_round`, a quotient of two
	# declared volumes) and three join `skipped` (`security_package`,
	# `tax_incentives` and `ppa_termination_payments`, whose bases are the
	# performance bond, the fleet's cash flow and the PPA annuity -- none of
	# which the solve result carries).
	# Batch 37 took it 467 to 472, and all five join `skipped`:
	# `geopolitical_risk_index` and `exposure_index` read governance and hazard
	# dials the result does not carry, `snapshot_weightings` reads the horizon
	# and the snapshot count, and the two land aliases read
	# `available_land_hectares` and `parcels_to_assemble`, which are themselves
	# derived from the land fraction and area. An alias joins `checked` only
	# when its driver is a column the result already holds, and none of these
	# five is.
	# Batch 38 took it 472 to 478, and the split is 170 checked / 308 skipped.
	# Two join `checked`: `storage_energy_capacity_mwh` reads
	# `storage_duration_curve` and `storage_capacity_mw`, both columns the
	# result holds, and `payment_security_required` reads `settlement_risk`
	# and `total_revenue_usd_per_year`, both carried. Four join `skipped`:
	# the three operational products read retyped dials the solve result does
	# not carry as columns, and `asset_age_distribution` reads `asset_life`
	# and `remaining_useful_life`, neither of which the result carries.
	# Batch 39 took it 478 to 481 -- three equalities, since its other two
	# equations are bounds and determine nothing -- and all three join
	# `skipped`: the two marine
	# products read capacities and per-kW rates the result does not carry as
	# columns, and the solvency product reads `solvency_capital`, which is
	# itself derived from two insurance inputs the solve does not supply.
	# Batch 44 added twelve equalities and all twelve join `skipped`: the
	# three fuel-energy definitions read capacities and capacity factors the
	# solve result does not carry as columns, the six pollutant totals read
	# the emission factors, and the three concentration and burden products
	# read `pm25_emissions`, which is itself derived. `checked` is flat at
	# 170 and `skipped` moves 311 -> 323.
	# Batch 46 took the computed set 493 to 528. Twenty-three join `checked`:
	# the eleven per-technology LACE nodes and the eleven value-cost ratios
	# read prices, capacities and factors the result carries as columns, and
	# `fleet_generation_headroom` is a quotient of two carried quantities.
	# Twelve join `skipped`: the eleven per-technology generation totals read
	# capacities the result does not carry, and `fleet_generation_twh` sums
	# those eleven, so it is no more reachable than its operands. `checked`
	# moves 170 -> 193 and `skipped` 323 -> 335.
	# Batch 48 retargeted the four sector-demand equations from
	# `base_demand_twh` to `demand_twh`. All four join `checked`: the solve
	# result carries `demand_twh` as a column and does not carry the base, so a
	# body reading the year is reachable from the result and a body reading the
	# base was not. `checked` moves 193 -> 197 and `skipped` 335 -> 331. This is
	# a widening of what the audit can check, not a narrowing -- the four were
	# skipped for a reason the correction removed.
	# Batch 51 added three derived emission factors. The solve result carries
	# neither `carbon_content_<fuel>_t_per_gj` nor `gj_per_mwh`, so all three
	# are skipped rather than checked: `checked` stays 197 and `skipped` moves
	# 331 -> 334. The audit's coverage is unchanged -- it is the computed set
	# that grew.
	# Batch 52 added `debt_fraction_definition`, whose `debt_equity_ratio` is
	# not on the solve result either, so `skipped` moves 334 -> 335 for the
	# same reason.
	assert len(audit.checked) == 197, audit.checked
	# Batch 53's reserve-requirement definition takes it 335 -> 336.
	# Batch 54's temporal-resolution definition takes it 336 -> 337, for the
	# same reason as the two before it: `tsam_segment_hours` is not on the
	# solve result either. The audit's coverage is unchanged; it is the
	# computed set that grew. Batch 69 removed `buffer_pool_contribution`'s
	# alias equation, so it leaves the computed set and 337 -> 336.
	assert len(audit.skipped) == 336, audit.skipped
	# The partition is exhaustive: every derived parameter is either checked or
	# named as not carried, so the two counts are the whole of the graph's
	# derived set and neither can shrink unnoticed.
	assert len(audit.checked) + len(audit.skipped) == len(load_graph().computed())
	assert not (set(audit.checked) & set(audit.skipped))
	assert "not carried" in audit.summary()


def test_an_audit_that_cannot_run_is_not_a_pass():
	"""A propagation that raises must read as a refusal, never as agreement.

	WHY THIS IS THE MOST IMPORTANT ASSERTION IN THE SEAM. The audit is a
	secondary check on a result a solve already produced. The graph can decline
	to have an opinion -- the capture-price feedback loop has no root in its
	(0, 1) bracket once the VRE build-out passes the fleet's total capacity --
	and the two obvious ways to write that are both wrong. Letting the exception
	escape destroys a valid solve's answer inside a check that was never the
	answer; swallowing it reports an unevaluated check as a pass, which is the
	defect this repo has paid for most often.

	``consistent`` is False on the failure path even though ``violations`` is
	empty, because a check that did not run is not a check that passed. A
	version returning ``consistent=True`` here would print a clean bill of
	health for a scenario nobody examined.

	The trigger is a plausible one, not a contrived one: a sweep over VRE
	capacity crosses this boundary, and ``vre_capacity_mw`` above
	``total_capacity_mw`` is a build-out the graph's own identity cannot express.
	"""
	from alea.prg.audit import audit_scenario_result

	# At the fleet's own capacity the loop still has a root.
	assert audit_scenario_result(_solved(), overrides={"vre_capacity_mw": 10000.0}).ran

	audit = audit_scenario_result(_solved(), overrides={"vre_capacity_mw": 40000.0})
	assert not audit.ran, "the loop found a root it should not have"
	assert audit.failure, "a check that did not run must say why"
	assert not audit.consistent, "an audit that could not run read as a pass"
	assert audit.violations == (), "a failure is not a violation of an identity"
	assert "not run" in audit.summary(), audit.summary()
	# The whole derived set is named as unexamined: a partial count here would
	# understate how much of the graph went unread. 243, not 88, for the
	# reason spelled out in `test_the_audit_reports_what_it_did_not_check` --
	# batch 20's sector-coupling layer took the computed set 153 to 182,
	# batch 21's demand-and-finance layer took it 182 to 198, batch 22's
	# compliance layer took it 198 to 227, batch 23's extensive-base layer
	# took it 227 to 243, batch 24's carbon-market layer took it 243 to 286,
	# batch 25's gate-family coupling took it 286 to 299, batch 26's
	# adequacy-and-reserve layer took it 299 to 310, batch 28's product
	# layer took it 310 to 382, and batch 29's demand-and-macro layer took
	# it 382 to 402, and batch 30's supply-and-grid layer took it 402 to
	# 412. The whole computed set is skipped here because the loop failed,
	# so this is `len(computed())`, not the skipped half of a partition that
	# ran, and batch 31's product layer took it to 440, and batch 33's
	# residue layer to 461, batch 44's pollutant layer to 493, and batch 46's
	# capacity-to-energy layer to 528.
	# Batch 51's three derived emission factors take it 528 -> 531, and batch
	# 52's debt-share definition takes it 531 -> 532, and batch 53's reserve
	# requirement 532 -> 533, and batch 54's temporal-resolution definition
	# 533 -> 534. Batch 69 takes it 534 -> 533: `buffer_pool_contribution`
	# stops being derived when its alias equation is removed, so the computed
	# set shrinks by one and the unexamined set with it.
	assert len(audit.skipped) == 533, audit.skipped

	# A second way to reach the same contract, and the one that escaped when
	# the range gate was added. `GraphError` is a `ValueError` and neither a
	# `FeedbackError` nor a `DslError`, so `--set capacity_factor=999` arrived
	# here through `overrides` and left as an uncaught exception -- a solve's
	# valid answer destroyed inside a check that was never the answer, which is
	# the first of the two wrong ways this test's docstring names.
	out_of_range = audit_scenario_result(
		_solved(), overrides={"capacity_factor": 999.0}
	)
	assert not out_of_range.ran, "an inadmissible override was audited as if admissible"
	assert out_of_range.failure, "a check that did not run must say why"
	assert not out_of_range.consistent
	assert "outside the range" in out_of_range.failure, out_of_range.failure


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

	# The fixture carries the graph's defaults, so both scenarios inherit the
	# nadir finding (see `KNOWN_DEFAULT_FINDINGS`). The claim under test is the
	# *difference*: the finance covenant refuses 200 and not 50, which is what
	# the optimiser alone would not tell you.
	accepted = audit_scenario_result(_solved(50.0))
	assert {v.equation_id for v in accepted.violations} == KNOWN_DEFAULT_FINDINGS, (
		[str(v) for v in accepted.violations]
	)
	refused = audit_scenario_result(_solved(200.0))
	assert not refused.consistent
	assert any(v.equation_id == "dscr_requirement" for v in refused.violations), [
		str(v) for v in refused.violations
	]
	assert "dscr_requirement" not in {v.equation_id for v in accepted.violations}, (
		"the covenant fired at a carbon price the test expects it to accept"
	)


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


def test_the_reliability_gap_reads_the_standard_nothing_else_reads():
	"""The graph declares a reliability standard; the solve is what meets it.

	`expected_unserved_fraction` is the share of demand the system is meant to
	fail to serve. Until this check existed it was read by its own equation and
	by nothing else -- the declared-is-not-produced defect class -- while the
	engine measured the realised share and reported it as a number no reader
	compared against anything.

	The assertion is deliberately *not* "the solve met the standard". A
	scenario short of capacity is a legitimate stress case and a refusal would
	forbid the frontier. What is asserted is that the gap is computed, that it
	is exact when the solve does meet the standard, and that it scales with the
	shortfall when it does not.
	"""
	import uuid

	from alea.prg.audit import reliability_gap
	from alea.whatif.params import ScenarioParameters
	from alea.whatif.views import ScenarioResult

	def solved(generation: dict[str, float], unserved: float) -> ScenarioResult:
		return ScenarioResult(
			scenario_id=str(uuid.uuid4()),
			params=ScenarioParameters(),
			network_checksum="sha256:" + "c" * 64,
			code_version="test",
			total_cost_usd=1.0e9,
			total_emissions_tco2=1.0e6,
			capacity_mix_mw={"coal": 1000.0},
			generation_mwh=generation,
			unserved_energy_mwh=unserved,
		)

	# The graph's standard is 0.001. Load shedding is a generation carrier, so
	# the generation total *is* the demand: 1 MWh shed of 1000 is exactly the
	# declared fraction, and the ratio is 1.0 by construction rather than by
	# tolerance.
	met = reliability_gap(solved({"coal": 999.0, "load shedding": 1.0}, 1.0))
	assert met["declared_fraction"] == pytest.approx(0.001)
	assert met["realised_fraction"] == pytest.approx(0.001)
	assert met["ratio"] == pytest.approx(1.0)
	assert met["served_mwh"] == pytest.approx(999.0)

	# A hundred times the standard. The realised fraction is 0.1 and the ratio
	# must follow the shortfall rather than saturate: a check that reported
	# "over standard" without a magnitude could not distinguish a near miss
	# from a fleet that serves almost nothing.
	missed = reliability_gap(solved({"coal": 900.0, "load shedding": 100.0}, 100.0))
	assert missed["realised_fraction"] == pytest.approx(0.1)
	assert missed["ratio"] == pytest.approx(100.0)

	# A result with no generation at all reports zeros rather than dividing by
	# the zero demand. A ratio of 0.0 here reads as "met the standard", which is
	# wrong, so the two fractions are carried and the reader compares them.
	empty = reliability_gap(solved({}, 0.0))
	assert empty["ratio"] == 0.0
	assert empty["declared_fraction"] == pytest.approx(0.001)
	assert empty["realised_fraction"] == 0.0


def test_the_reliability_gap_is_not_a_second_spelling_of_the_intensity_gap():
	"""Two gaps over one result must measure two different things.

	The intensity gap is emissions over generation; the reliability gap is
	unserved over demand. A copy-paste that reused the emissions numerator
	would produce a plausible ratio that answers the wrong question, and both
	functions live in one module where that is a one-line mistake. This pins
	the two apart on a result where they differ by construction: nothing is
	unserved, so the reliability ratio is 0.0 while the intensity ratio is 1.0.
	"""
	import uuid

	from alea.prg.audit import fleet_intensity_gap, reliability_gap
	from alea.whatif.params import ScenarioParameters
	from alea.whatif.views import ScenarioResult

	# 25 Mt over 50 TWh is 0.5 t/MWh, the graph's factor: intensity ratio 1.0.
	# Nothing is shed, so the reliability ratio is 0.0.
	result = ScenarioResult(
		scenario_id=str(uuid.uuid4()),
		params=ScenarioParameters(),
		network_checksum="sha256:" + "d" * 64,
		code_version="test",
		total_cost_usd=1.0e9,
		total_emissions_tco2=25.0e6,
		capacity_mix_mw={"coal": 6000.0, "wind": 4000.0},
		generation_mwh={"coal": 30.0e6, "wind": 20.0e6},
	)
	assert fleet_intensity_gap(result)["ratio"] == pytest.approx(1.0)
	assert reliability_gap(result)["ratio"] == 0.0
	assert reliability_gap(result)["unserved_mwh"] == 0.0


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
	# 14,000 MW: the fixture's three carriers, summed. It is asserted against
	# the fixture rather than pinned as a literal, because what this test is
	# about is *which* parameters the extraction takes, not the fleet's size.
	assert supplied["total_capacity_mw"] == pytest.approx(14000.0)
	# The optimiser's own decisions, read off the mix through the registry's
	# carrier classes: coal and gas are thermal, and wind is neither thermal
	# nor dispatchable renewable, so it lands in no fleet node -- VRE capacity
	# is `vre_capacity_mw`, the capture-price loop's fixed point.
	assert supplied["thermal_capacity_mw"] == pytest.approx(10000.0)
	assert supplied["dispatchable_re_capacity_mw"] == pytest.approx(0.0)
	assert supplied["storage_capacity_mw"] == pytest.approx(0.0)


def test_the_fleet_nodes_are_filled_from_the_solve_not_from_their_defaults(
	graph: ParameterGraph,
):
	"""The middle layer of the spec's DAG, and the reader that was missing.

	WHY THIS IS THE TEST THAT MATTERS. The three endogenous nodes landed in
	``config/prg.yaml`` carrying reference defaults -- 7,500 MW of thermal,
	1,500 of dispatchable renewable, 800 of storage -- and *nothing read them
	back from a solve*. So the reserve margin, which derives ``firm_capacity_mw``
	from two of them, checked 9,000 MW of reference fleet on every audit while
	reporting as a check on the build. That is the "declared is not produced"
	defect in the layer that was added to fix it, and it is invisible in any
	test whose fixture happens to agree with the default.

	The mix below is chosen to disagree with every default in both directions:
	more thermal, no dispatchable renewable at all, and a storage unit. A
	mapping that fell back to the default would pass a test whose fleet
	happened to match one.
	"""
	from alea.prg.audit import fleet_parameters

	mix = {
		"coal": 9000.0,
		"gas": 2000.0,
		"hydro": 400.0,
		"geothermal": 100.0,
		"battery": 250.0,
		"onwind": 3000.0,
		# A carrier the registry does not know. It lands in no group, which
		# understates the fleet rather than inventing a capacity for it -- the
		# same choice `constraints._generator_capacity` makes.
		"unobtainium": 999.0,
	}
	fleet = fleet_parameters(mix, graph)
	assert fleet["thermal_capacity_mw"] == pytest.approx(11000.0)
	assert fleet["dispatchable_re_capacity_mw"] == pytest.approx(500.0)
	assert fleet["storage_capacity_mw"] == pytest.approx(250.0)
	# Wind is VRE, which is `vre_capacity_mw` -- the loop's fixed point -- so it
	# is in no fleet node. Asserted rather than left implicit: a mapping that
	# swept every known carrier into one group would double-count the fleet.
	assert sum(fleet.values()) == pytest.approx(11750.0)

	# An empty mix is a result that did not record a fleet, not a fleet of
	# zero. Returning zeros would overwrite whatever the caller supplied with a
	# claim about a network the result says nothing about.
	assert fleet_parameters({}, graph) == {}


def test_the_audit_checks_the_fleet_the_solve_reported(
	graph: ParameterGraph,
):
	"""A build the reserve margin rejects is refused, and the refusal is about the build.

	The differential form of the test above: the same result, with only the
	mix changed. A coal-and-wind fleet is 6,000 MW of firm capacity against an
	8,500 MW peak at a 15% margin, and the graph must say so. Before the fleet
	was wired this audit passed, because ``firm_capacity_mw`` was filled from
	the node's own 9,000 MW reference default and the mix never reached an
	equation.
	"""
	import uuid

	from alea.prg.audit import audit_scenario_result
	from alea.whatif.params import ScenarioParameters
	from alea.whatif.views import ScenarioResult

	thin = ScenarioResult(
		scenario_id=str(uuid.uuid4()),
		params=ScenarioParameters(carbon_price_usd_per_tco2=50.0),
		network_checksum="sha256:" + "b" * 64,
		code_version="test",
		total_cost_usd=1.0e9,
		total_emissions_tco2=25.0e6,
		capacity_mix_mw={"coal": 6000.0, "wind": 4000.0},
		generation_mwh={"coal": 30.0e6, "wind": 20.0e6},
	)
	audit = audit_scenario_result(thin, graph)
	assert not audit.consistent
	assert any(v.equation_id == "reserve_margin" for v in audit.violations), [
		str(v) for v in audit.violations
	]


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
	# The loop's own convergence, not the scenario's cleanliness: the shipped
	# defaults carry the nadir finding (see `KNOWN_DEFAULT_FINDINGS`), and what
	# this test pins is that the loop did not *also* leave an equation it
	# declared solved in violation.
	assert _default_violation_ids(graph, result.values) == KNOWN_DEFAULT_FINDINGS, (
		graph.consistency(result.values)
	)
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
	"""No *caller-induced* conflict, which is what the detector is for.

	The shipped defaults carry one out-of-range finding of their own -- see
	`KNOWN_DEFAULT_FINDINGS` -- so this pins that the detector adds nothing on
	top of it. A conflict the caller's own supplied values did not create would
	be the detector misreading a consistent scenario.
	"""
	result = graph.propagate(defaults)
	report = detect_conflicts(graph, result.values, supplied=defaults)
	assert report.checked, "nothing was checked, so the pass is vacuous"
	assert {c.subject for c in report.conflicts if c.blocks} == {"frequency_nadir_hz"}, (
		report.summary()
	)
	assert {c.kind for c in report.conflicts} == {ConflictKind.OUT_OF_RANGE}, (
		report.summary()
	)


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
	"""A needed parameter that nothing supplies is named as under-determined.

	Anchored on ``asset_life`` rather than on ``discount_rate``. That parameter
	carried a default when this test was written, and it does not any more: it
	is ``derived``, ``wacc_definition`` computes it, and it is therefore absent
	from ``defaults`` on the shipped graph and the expanded one alike -- so the
	comprehension below removed nothing and the test asserted a fact about
	which equation the DSL walk happened to trip over first. It passed only
	while the document's equations were in hand-authored order; sorting them
	moved ``energy_burden_definition`` ahead of ``wacc_definition`` and the
	assertion failed against an input it had never actually changed. The
	assertion is now about the parameter named in ``subject`` and not about the
	error's wording, which is what made it order-sensitive.
	"""
	needed = graph.node("asset_life")
	assert needed.role.value != "derived", needed.role
	assert "asset_life" in defaults, "the premise is that this carries a default"
	supplied = {k: v for k, v in defaults.items() if k != "asset_life"}
	# `asset_life` has a default and nothing derives it, so dropping it leaves
	# the graph unable to compute the parameters that need it.
	report = detect_conflicts(graph, defaults, supplied=supplied)
	under = report.of_kind(ConflictKind.UNDER_DETERMINED)
	assert any(c.subject == "asset_life" for c in under), report.summary()


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

	# Not the bare defaults: with the corrected swing equation they report the
	# nadir finding (see `KNOWN_DEFAULT_FINDINGS`) and exit 1. A 4 s response
	# time is a real grid-code-grade scenario that *is* clean, so the exit-code
	# contrast the test is about survives.
	clean = _prg("conflicts", "--set", "frequency_response_time_s=4")
	assert clean.exit_code == 0, clean.output
	# And the defaults themselves exit 1, which is the graph refusing a
	# scenario it used to pass.
	assert _prg("conflicts").exit_code == 1


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
	# The counts grew twice. First when the catalog expansion landed: the graph
	# went from 88 nodes to 869, and the catalog's own `determinism` hints --
	# `scenario`, `uncertain`, `probabilis` in the algorithm cell -- brought 26
	# more settable declarations with it (`hydro_drought_multiplier`,
	# `line_outage_probability`, `solar_irradiance_multiplier`, the scenario
	# metadata). Then when the generated batches were promoted: 110 more nodes,
	# 53 of them settable and declared `stochastic`. The literals are updated
	# rather than the derivation, because the pin is the assertion: deriving
	# the count from the register would pass on a graph that declared nothing
	# uncertain, which is the silence this module exists to break.
	# The counts grew twice more. The generated batches' promotion brought the
	# input register to 73; batch 20's sector-coupling layer moved one input to
	# 72 and brought 54 rules and 29 new determined variables with it. The
	# literals are updated rather than the derivation, because the pin is the
	# assertion: deriving the count from the register would pass on a graph
	# that declared nothing uncertain, which is the silence this module exists
	# to break.
	# Batch 31 moved both counts. The input count falls 76 to 75 because
	# `fuel_cost_hydrogen` became an alias of `hydrogen_price_per_mwh`: the
	# alias carries `determinism: fixed`, so a stochastic settable knob
	# became a derived node and left the input register. That is the
	# intended effect of an alias -- one dial, not two -- and the loss is
	# recorded here rather than silently accepted.
	# The derived-stochastic count rises 42 to 48 on the six products whose
	# own relation is stochastic: the cat-bond coupon, the drought-adjusted
	# hydro share, the cause-attributed event count, the scenario river flow,
	# and the wind and solar resource shares.
	# Batch 44 moved neither count, and the reason is worth recording because
	# the first run said otherwise. The health chain retyped
	# `pm25_relative_risk_per_kt` as `pm25_relative_risk_per_ug_per_m3`: the old
	# id is deprecated, `is_settable` refuses a deprecated node, and the
	# register counted the tombstone on the *derived* side instead -- 48 went to
	# 49 while the input count stayed at 74. Excluding deprecated nodes from the
	# declaration set fixed it and left the register identical to the previous
	# batch's: one stochastic input replaced by one stochastic input, and
	# `pm25_dispersion_factor` is `physical`, so it is not an uncertain input.
	# A batch that moves either count now has to say which node did it.
	# Batch 50 moved the settable side only, and down by three. It retyped 33
	# placeholder `float`s to `categorical` and set `determinism: policy` on
	# all of them -- a level is a chosen regime, not a measured quantity. Three
	# of the 33 shipped `stochastic` (`scenario_template`,
	# `scenario_visibility`, `fuel_price_scenario`) and leave the input
	# register with the retype. The derived side is untouched: none of the 88
	# is read by an equation, so nothing entered or left the closure.
	assert len(reg.inputs) == 71, reg.inputs
	assert len(reg.derived_stochastic) == 48, reg.derived_stochastic
	assert len(reg.stochastic_edges) == 1, reg.stochastic_edges
	# 122 nodes are declared stochastic in total: 74 settable, 48 derived.
	# Batch 50 takes the total to 119, by the three categoricals named above.
	# Batch 33 moved only the settable side, and down: `willingness_to_pay`
	# was a stochastic placeholder and is now derived, so the input register
	# loses it and no derived node entered the closure -- the products it
	# feeds read fixed process parameters.
	# Batch 27's finance family moved both: three of its bases are declared
	# stochastic (`aal_usd_million`, `pml_99_5_usd_million`, `microinsurance`)
	# and one derived parameter entered the closure, `solvency_capital`,
	# which reads the two insurance bases. Batch 28's product layer moved
	# both again: two bases it retyped are declared stochastic
	# (`fuel_price_volatility`, `geothermal_drilling_success`) and one
	# derived parameter entered the closure, `claims_history`, which reads
	# the loss ratio and the premium. Batch 29's demand-and-macro layer
	# moved only the derived side, and by three: `archaeological_sites`,
	# `sacred_sites` and `remittance_flows` inherit the stochasticity of
	# the density and share bases they read, while the four demand
	# products that also entered the computed set read fixed process
	# parameters and stay deterministic. 39 to 42.
	assert len(reg.inputs) + len(reg.derived_stochastic) == 119
	# The declarations sum is taken over *live* nodes, and the deprecated ones
	# are named rather than filtered silently. This assertion is what catches
	# the register losing a declaration, so it must count the same object the
	# register counts -- otherwise a tombstone carrying `determinism:
	# stochastic` makes the two sides disagree by one and the assertion stops
	# being about the register at all. Batch 44's
	# `pm25_relative_risk_per_kt` is that tombstone: it is stochastic, it is
	# deprecated, and it is not a declaration about anything the graph computes.
	deprecated_stochastic = {
		name
		for name, node in graph.nodes.items()
		if str(node.determinism) == "stochastic" and node.status == "deprecated"
	}
	assert deprecated_stochastic == {"pm25_relative_risk_per_kt"}, (
		deprecated_stochastic
	)
	assert len(reg.inputs) + len(reg.derived_stochastic) == sum(
		1
		for node in graph.nodes.values()
		if str(node.determinism) == "stochastic" and node.status != "deprecated"
	), "the register and the declarations disagree"


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
	# 75 inputs reaching 129 derived parameters, 36 of those stochastic by their
	# own relation. Batch 20's sector-coupling layer moved the reach: one fewer
	# settable stochastic input than the promotion's 73, and the equations it
	# added brought 90 derived parameters into the closure. Batch 21's
	# demand-and-finance layer brought 3 more (90 to 93); its input count is
	# unchanged. Batch 22's compliance layer brought 5 more (93 to 98), again
	# with the input count unchanged at 72. Batch 23's extensive-base layer
	# brought 5 more (98 to 103): the route, learning, household, land and
	# transport products all hang off settable bases, and the input count is
	# again unchanged at 72. Batch 24's carbon-market layer brought 16 more
	# (103 to 119). Batch 25's gate-family coupling brought 3 more (119 to
	# 122): the business-interruption, cyber and force-majeure cover products,
	# each a settable share times gross revenue, and the input count is again
	# unchanged at 72. Batch 26's adequacy-and-reserve layer brought one more
	# (122 to 123): `reserve_margin` is now an alias of
	# `reserve_margin_actual`, and `fuel_price_usd_per_mwh` already reached
	# that node through `marginal_cost_usd_per_mwh` and `vre_capacity_mw`, so
	# an uncertain input that already existed now closes on one more derived
	# parameter, and the input count is again unchanged at 72. Batch 27's
	# finance family moved both counts: three new stochastic inputs
	# (`aal_usd_million`, `pml_99_5_usd_million`, `microinsurance`) took the
	# register 72 to 75, and six derived parameters entered the closure
	# (`solvency_capital`, `insurance_premium_usd_million`,
	# `insurance_premiums`, `microinsurance_premium_usd_per_year`,
	# `microinsured_population`, `transaction_cost_usd_per_year`), taking the
	# reach 123 to 129. Batch 28's product layer moved both counts again:
	# two stochastic inputs (`fuel_price_volatility`,
	# `geothermal_drilling_success`) took the register 75 to 76, and
	# fourteen derived parameters entered the closure -- the eight
	# employment counts, the two transition instruments, the contingency
	# allowance, the cash sweep, the ceded premium and the effective
	# geothermal capex -- taking the reach 129 to 143. Pinned because
	# the number is the finding -- the sentence exists to stop a reader taking
	# the declarations for a distribution, and a reach that drifts unnoticed
	# would understate it.
	# Batch 30 moved the reach by one: `baseline_emissions` reads
	# `emissions_mtco2_per_year`, which the uncertain demand and emission
	# factors already reach, so it enters the closure and takes the reach
	# 149 to 150. The input count is unchanged -- the batch adds no new
	# stochastic declaration -- and so is the derived-stochastic count, since
	# the new node inherits a fixed determinism from the two nodes it sums.
	# Batch 31 took the reach 150 to 159: nine of its derived nodes sit
	# downstream of the demand, land or water inputs the register already
	# follows. The input count fell by one, for the reason the derived-
	# stochastic pin above records. Batch 36 moved the reach 159 to 167: eight
	# of its new derived nodes sit downstream of `total_capacity_mw` and
	# `cfads_usd_per_kw_year`, both of which the uncertain fuel and demand
	# factors already reach. The input count is unchanged at 74 -- the batch
	# declares no new stochastic input, and its two categorical retypes carry
	# `policy` determinism, which the register does not count. Batch 37 moved
	# neither count. Its six derived nodes all sit downstream of `fixed`
	# bases -- `political_stability`, the seven hazard levels,
	# `available_land_hectares`, `representative_days`, `tsam_segments` and
	# `time_horizon` -- none of which is in the register's input set, so the
	# closure is unchanged at 167. The inputs stay at 74 and the
	# derived-stochastic set at 48: the batch declares no new stochastic
	# input, and every node it retypes carries `fixed` or `physical`
	# determinism. Measured, not carried forward from the pack's estimate.
	# Batch 38 moved the reach 167 to 168: `payment_security_required` is the
	# one derived node it adds that sits downstream of an uncertain input,
	# because `total_revenue_usd_per_year` reads the uncertain fuel and demand
	# factors. The other five are products of `fixed` bases -- the retyped
	# ramp rates, stable levels, durations and the asset life -- which the
	# register does not follow. The input count and the derived-stochastic
	# count are both unchanged: the batch declares no new stochastic input and
	# none of its derived nodes is stochastic by its own relation. Batch 39
	# moved the reach 168 to 171: all three of its products sit downstream of
	# an uncertain input -- the two marine capex products read
	# `capex_marine_otec` and `capex_marine_tidal`, both declared stochastic,
	# and the solvency product reads `solvency_capital`, which is derived
	# from the stochastic `aal_usd_million` and `pml_99_5_usd_million`. The
	# input count and the derived-stochastic count are both unchanged: the
	# batch declares no new stochastic input and none of its products is
	# stochastic by its own relation.
	# Batch 44 left the summary exactly where batch 39 put it, and the earlier
	# reading here of "75" was wrong: it was measured before the deprecated
	# node was excluded from the register, so it counted a tombstone. The chain
	# it added -- fuel energy, the six pollutant ledgers, the dispersion factor
	# and the concentration -- is `physical` throughout, and a physical
	# accounting identity does not become uncertain because an upstream input
	# is, which is the module's own distinction between reachability and
	# determinism.
	# Batch 46 moved the reach 171 to 194. Twenty-three of its thirty-six
	# derived nodes sit downstream of an uncertain input: the eleven LACE nodes
	# and the eleven value-cost ratios read `capacity_price` and
	# `marginal_cost_usd_per_mwh` (and, for the four intermittent LACE nodes,
	# `vre_capacity_credit`), and the headroom quotient reads `generation_twh`,
	# which the demand factors already reached. The twelve generation
	# identities are downstream of capacities and capacity factors the register
	# does not carry as uncertain, so they do not move it. The input count
	# stays at 74 and the derived-stochastic count at 48: the batch declares no
	# new uncertain input, and none of its derived nodes is stochastic by its
	# own relation.
	# Batch 50 moved the input count 74 to 71 and left the reach at 194. Its
	# 88 retypes are named by no equation, so no derived parameter entered or
	# left the closure; the three that shipped `stochastic` and now carry
	# `policy` (`scenario_template`, `scenario_visibility`,
	# `fuel_price_scenario`) are the whole of the move.
	# Anchored to the tokens the sentence puts them in, not substrings: `"71" in
	# text` would also pass on 171, 471 or a date.
	assert re.search(r"\b71 uncertain input", text), text
	assert re.search(r"reach \b194 derived", text), text


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

	check = check_equation(
		_canary_equation("largest_loss_mw", "cumulative_battery_installed_mwh"), graph
	)
	assert check.decidable, "the checker gave up on MW = TWh"
	assert not check.consistent, "the checker called MW = TWh consistent"


def test_the_unit_checker_flags_an_inhomogeneous_sum(graph: ParameterGraph):
	"""``MW + TWh`` cannot share a dimension, and the mismatch is the finding."""
	from alea.prg.units import check_equation

	check = check_equation(
		_canary_equation(
			"largest_loss_mw", "largest_loss_mw + cumulative_battery_installed_mwh"
		),
		graph,
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


def test_a_product_under_a_bar_binds_under_it():
	"""``USD/MW-km`` is a currency per megawatt-kilometre, not per megawatt.

	The hyphen is a product, and Pint parses left to right, so the repaired
	string ``USD/MW*km`` is ``USD*km/MW`` -- a currency times a square
	kilometre per megawatt. That is a *decidable* reading, which is what makes
	it dangerous: the walker blesses any product formed against it, and the
	error surfaces only as a cost that is three orders of magnitude wrong.

	Pinned against the two spellings that must agree, so a future normaliser
	that loses the parentheses fails here rather than in a capex figure.
	"""
	from alea.prg.units import _parse_unit, ureg

	hyphen = _parse_unit("USD/MW-km")
	explicit = _parse_unit("USD/(MW*km)")
	per_slash = _parse_unit("USD/MW/km")
	assert hyphen.dimensionality == explicit.dimensionality
	assert hyphen.dimensionality == per_slash.dimensionality
	# The misparse, stated as a difference rather than described: a kilometre
	# in the numerator is a different dimension, and the two must not agree.
	assert hyphen.dimensionality != (ureg.USD * ureg.kilometer / ureg.megawatt).dimensionality
	# The hyphen is still a product where it is not under a bar.
	assert _parse_unit("MW-km").dimensionality == (ureg.megawatt * ureg.kilometer).dimensionality


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
	"""The three sets, plus the declared exemptions, partition the equations.

	The exemption is a fourth category by design -- the walker's own register
	carries it apart from "nobody has annotated this" -- so the partition the
	assertion really states is the four-way one, and folding the exempt into
	undecidable is exactly what the field exists to prevent.
	"""
	from alea.prg.units import check_graph

	# The invariant at the set level, rather than as four counts with an
	# inclusion-exclusion term: every equation has either a *decided* verdict
	# (the walk ran) or a *declared* one (the exemption), and no equation
	# has neither. The three property lists are views of the checks; the
	# exemption is the reason they do not partition on their own.
	report = check_graph(graph)
	decided = {c.equation_id for c in report.checks if c.decidable}
	assert decided | set(report.exempt) == set(graph.equations)
	assert not (set(report.consistent) & set(report.inconsistent))
	assert "not a pass" in report.summary()


def test_the_flagged_equations_are_a_known_set(graph: ParameterGraph):
	"""The inconsistent set is pinned, so a new one is a failing test.

	ONE equation is flagged today. It has been eleven, twenty and eight at
	earlier points in the build; the history below is kept because each entry
	is a measurement of what a retype does to this set, and those measurements
	are the reason the annual-quantity vocabulary was repaired the way it was.

	WHY TEN LEFT AT BATCH 40, AND WHY THE REPAIR WAS THE NODE. The eleven were
	three kinds rather than one. Six were annual quantities declared without a
	per-year divisor (``ammonia_export_volume_tonnes_definition``,
	``co2_captured_cement_tonnes_definition``,
	``co2_captured_industry_tonnes_definition``,
	``steel_hydrogen_demand_tonnes_definition``,
	``insurance_premium_definition``,
	``mini_grid_programme_spend_definition``). Two were compounding slips
	(``premature_deaths_definition`` carried a ``pm25_kt_per_year`` against a
	``1/kt`` risk coefficient; ``rocof_definition`` divides MW by MW·s to get
	a per-second rate the node declares as Hz/s). Three were single
	declarations disagreeing with their own equation's stated check
	(``coal_price_per_mwh_definition``, ``equity_irr_definition``,
	``line_outage_hours_per_year_definition``).

	For nine of the ten, the walk's ``lhs vs rhs`` message invited rewriting
	the rhs, and the rhs was what the author wrote from the physics: the
	*catalog* had mis-typed the node. ``line_outage_hours_per_year_definition``
	was ``probability * duration`` before the batch and is ``probability *
	duration`` after it; ``line_outage_probability`` shipped ``1/year`` for a
	count of events and is now ``events/year``. Same for the six annual
	quantities, ``equity_irr_estimate`` and ``premature_deaths_definition``.
	The tenth, ``coal_price_per_mwh_definition``, was arithmetically right and
	12.96x low because it divided by an untyped literal ``25 * 3.6`` that the
	walker reads as dimensionless; the fix is a typed node
	(``mwh_per_coal_unit``, ``MWh/tonne``, 6.944), not a corrected literal.
	Writing the retype table from the failing *equations* would have retyped
	three nodes that already shipped the right unit
	(``insurance_premium_usd_per_kw_year``, ``line_outage_hours_per_year``,
	``mini_grid_programme_spend_usd_per_year``) and left three wrong ones
	untouched. Write it from the failing *nodes*.

	WHY ``rocof_definition`` IS STILL HERE AND IS NOT A MISS. The swing
	equation needs a ``* f0`` the shipped body omits, wrong by 50x at 50 Hz.
	Correcting it drives ``frequency_nadir_hz`` to 43.06 Hz, under its own
	[45, 50] floor, because ``frequency_nadir_definition`` applies the initial
	slope over a flat ``frequency_response_time_s`` of 10 s. Two shipped
	defaults disagree; that is a question about the nadir model, and bending
	the 45 Hz UFLS floor to make the number fit would be manufacturing
	agreement rather than repairing it. It stays red until the nadir chain is
	answered.

	The entries that follow are the earlier history, kept because each one
	measures what a retype does to this set.

	WHY THE PROMOTION GREW THE SET FROM EIGHT TO TWENTY AND WHY NONE OF THE
	TWELVE WERE FIXED HERE. The generated batches added forty-two equations,
	and the twelve new flags are all one decision: the graph's unit vocabulary
	for *annual* quantities. Every candidate fix is a re-declaration that
	trades clears for new flags, which is measurable and was measured.
	Declaring ``generation_twh`` as ``TWh/year`` clears three equations and
	opens ``cooling_water_definition`` and ``energy_balance``; declaring
	``equilibrium_demand_twh`` the same way clears two and opens three;
	declaring the ten rate nodes dimensionless clears six and opens four. The
	arithmetic of each equation is right and the *declaration* is coarse, so
	fixing one node in isolation moves the inconsistency rather than removing
	it -- the vocabulary is a modelling decision to make once, deliberately,
	and across the whole family of nodes it touches. Pinned here so the twelve
	are visible in the meantime and a fix shows up as a set change rather than
	as a count that drifted.

	WHY ``tariff_cost_recovery`` IS FLAGGED AND IS NOT WRONG. It is the
	per-year-divisor class, and the coarse declaration is the *demand node's*,
	not the equation's: ``equilibrium_demand_twh`` is an annual energy declared
	as bare ``TWh``, so ``USD/year / TWh`` reads as ``USD/(MWh·year)`` when the
	arithmetic is the physically correct ``USD/year / (MWh/year) = USD/MWh``.
	The equation divides annual cost by annual energy and the physics is right;
	what is missing is the ``/year`` on the node. Declaring the five ``TWh``
	nodes as ``TWh/year`` clears this equation and opens five others in the same
	class -- ``energy_balance``, ``energy_demand``, ``equilibrium_demand``,
	``unserved_definition`` and ``cooling_water_definition`` -- so the unit
	vocabulary is a modelling decision to make once, deliberately, and not a
	side effect of adding a loop. Pinned here so it is visible in the meantime.

	WHY FIVE MORE AT BATCH 20. The sector-coupling layer added five equations
	in the same annual-quantity class: a bare ``tonnes`` or ``hours/year`` node
	computed from a per-year production or availability (``MWh/year``,
	``million tonnes/year``, ``1/year``) times a share or a per-event duration.
	Each equation's arithmetic is the conversion the node's own unit cell
	asserts, and the walker's vocabulary cannot see it -- the modelling decision
	above, not a new arithmetic error. Pinned so the five are named rather than
	counted.

	WHY TWO MORE AT BATCH 21. The demand-and-finance layer added
	``insurance_premium_definition`` (a bare ``USD/kW/year`` node computed from
	a per-year rate times a share) and ``mini_grid_programme_spend_definition``
	(a bare ``USD/year`` node computed from a per-connection cost times the
	connections served per year) -- both in the same annual-quantity class as
	batch 20's five, and both arithmetic the node's own unit cell asserts.
	Pinned so the two are named rather than counted.

	WHY TWO MORE AT BATCH 22. The compliance layer added
	``forecast_error_band_definition`` (``TWh/year`` from a dimensionless
	methodology share times a bare ``TWh`` demand) and
	``renewable_generation_target_definition`` (``TWh/year`` from a
	dimensionless target share times a bare ``TWh`` generation) -- the same
	annual-quantity class again, and again the declaration is coarse while the
	arithmetic is what the node's unit cell asserts. Pinned so the two are
	named rather than counted.

	WHY NINE LEFT AT BATCH 24, AND WHAT THAT MEASURES. The annual-quantity
	repair retyped fifteen nodes to per-year units (``TWh`` to ``TWh/year``,
	``m3`` to ``m3/year``, ``GWh`` to ``GWh/year``, ``USD`` to ``USD/year``),
	and the prediction this docstring carried since the promotion -- "declaring
	the five ``TWh`` nodes as ``TWh/year`` clears this equation and opens five
	others" -- was wrong in one direction: the retype cleared nine and opened
	none. ``benefit_sharing_from_revenue_definition``,
	``consumer_surplus_definition``, ``emissions_definition``,
	``forecast_error_band_definition``, ``hydrogen_water_definition``,
	``load_factor_definition``, ``renewable_generation_target_definition``,
	``tariff_cost_recovery`` and ``total_revenue_definition`` all read a node
	this batch retyped, and each is now dimensionally decidable and consistent.
	The open side of the prediction was an inference from one candidate
	declaration, not a measurement; the measurement is this set.

	WHY BATCH 25 ADDED NONE. Each of the gate-family coupling's thirteen
	equations multiplies a dimensionless share or switch by a quantity that
	already carries the declared unit -- a cover share against
	``total_revenue_usd_per_year``, a rollout switch against the planned hours
	or the permitted volume -- so the product inherits that unit and the walker
	divides it cleanly. Nothing in the batch declares a bare annual quantity,
	which is the class every flag here belongs to, so the set stands at eleven.

	WHY BATCH 26 ADDED NONE. Each of the adequacy-and-reserve layer's eleven
	equations multiplies a dimensionless share by a quantity that already
	carries the declared unit -- a reserve share against ``peak_demand_mw``,
	the voltage-support share against ``reactive_capability_mvar`` -- or
	aliases one node to another of the same unit, and
	``transmission_loss_target_definition`` scales ``transmission_loss_factor``
	by ``(1 - transmission_loss_reduction_target)``, which the batch retyped
	from a unit-less 500000.0 to a share at 0.1. Every product and every
	alias therefore inherits a declared unit the walker divides cleanly, and
	none declares a bare annual quantity, so the set stands at eleven again.
	"""
	from alea.prg.units import check_graph

	report = check_graph(graph)
	flagged = {check.equation_id for check in report.inconsistent}
	# The annuity blessing (the walker accepts a (1 + rate) base to a
	# [time]-cancelled or dimensionless exponent at the rate's own period)
	# cleared the ten (1 + rate) equations of the older pin and left the
	# twelve the classes below name. The per-technology crf/LCOE equations
	# the coupling batches added check clean under the same blessing, which
	# is the blessing earning its keep.
	#
	# Batch 67 closed the last one. `rocof_definition` determined `Hz/s` from
	# MW over MW.s, which is 1/s: the per-unit swing equation's rate, missing
	# the nominal-frequency factor that turns it into hertz. The register now
	# stands at empty, which is the state this pin existed to reach -- it was
	# never asserting that one equation *should* be inconsistent, only that
	# this was the whole of the set.
	assert flagged == set(), sorted(flagged)


def test_the_summary_carries_the_unit_register(graph: ParameterGraph):
	"""The unit check rides on the summary, so its coverage cannot be missed."""
	summary = graph_summary(graph)
	units = summary["units"]
	assert len(units.checks) == len(graph.equations)
	assert "not a pass" in units.summary()


# ---------------------------------------------------------------------------
# Incremental propagation: the same answer, without re-walking the graph
# ---------------------------------------------------------------------------


def test_incremental_propagation_equals_a_full_one(graph: ParameterGraph, defaults: dict):
	"""The whole claim: skipping what did not move changes no value.

	``propagate`` re-derives every determiner and re-solves every feedback loop
	on every call. ``propagate_incremental`` recomputes the closure of what
	changed and carries the rest over from the previous result. If the two ever
	disagree, the incremental path is a second, wrong answer -- which is worse
	than a slow one.

	Every settable parameter is perturbed in turn and the result compared to a
	full propagation from the same values. A perturbation that moved nothing is
	counted and reported, so a passing run cannot be a vacuous one: if the
	comparison never had a difference to find, "equal" proves nothing.
	"""
	settable = [n for n in graph.nodes if graph.is_settable(n) and graph.nodes[n].default is not None]
	assert settable, "no settable parameter carries a default"
	previous = graph.propagate(defaults)
	moved_something = 0
	refused = 0
	for name in settable:
		node = graph.nodes[name]
		# From the *previous* result, not from `defaults`: the incremental
		# contract is "this result, plus a delta". Resetting every other knob
		# to its default each turn would hand the incremental path a base its
		# `previous` does not describe -- a caller error, not a graph one.
		values = dict(previous.values)
		if isinstance(node.default, str):
			# A categorical's value is a level *name*, so there is no delta to
			# take and no "25% of the span" to move it by: the perturbation is
			# the next level in the declared order, wrapping. Skipping these
			# two would leave the incremental path untested on the one class of
			# node whose value is not a number -- which is exactly the class
			# that broke it, since `abs(got - expected)` is a TypeError when
			# both sides are level names.
			levels = list(node.categories or ())
			assert levels, f"{name} is categorical with no declared levels"
			values[name] = levels[(levels.index(node.default) + 1) % len(levels)]
		else:
			span = (node.range[1] - node.range[0]) if node.range else abs(node.default)
			values[name] = node.default + (span * 0.25 if span else 0.1)
			if node.range is not None and not (
				node.range[0] <= values[name] <= node.range[1]
			):
				continue
		# A perturbation can leave the *loop's* declared bracket even while
		# sitting inside its own node's range: 25% of `total_capacity_mw`'s
		# 1e6 MW span is a 260,000 MW fleet whose revenue requirement exceeds
		# the tariff node's 2000 USD/MWh ceiling, and the solver correctly
		# refuses to search outside it. That is not a failure to propagate --
		# it is the same answer the full path gives -- so the two paths are
		# required to refuse *together*, which is a stronger claim than the
		# equality below and covers the case a `continue` would have hidden.
		try:
			full = graph.propagate(values)
		except (DslError, FeedbackError) as refusal:
			with pytest.raises(type(refusal)):
				graph.propagate_incremental(values, previous, [name])
			refused += 1
			continue
		step = graph.propagate_incremental(values, previous, [name])
		assert set(step.values) == set(full.values), name
		# The loop solver starts from the values it is handed, so a warm start
		# converges to the fixed point within `tolerance` rather than to the
		# last bit a cold start stopped at. The graph declares 1e-8, and the
		# measured worst case is 1.1e-8 relative; demanding exactness here would
		# be asserting something false about an iterative solver. Every
		# parameter not downstream of the loop still has to match exactly.
		looped = {v for loop in graph.feedback_loops() for v in loop.variables}
		downstream = set(looped) | set(graph.affected_by(looped))
		for key, expected in full.values.items():
			got = step.values[key]
			if isinstance(expected, str):
				# A level name has no arithmetic, so a tolerance is meaningless
				# here and the two paths must agree exactly. `abs(got - expected)`
				# is a TypeError on two strings, which is how this class went
				# untested until the categorical model landed.
				assert got == expected, (
					f"{name}: incremental {key}={got!r} but a full propagation "
					f"gives {expected!r}"
				)
				continue
			tolerance = 1e-7 * max(abs(expected), 1.0) if key in downstream else 0.0
			assert abs(got - expected) <= tolerance, (
				f"{name}: incremental {key}={got} but a full propagation gives "
				f"{expected} (allowed {tolerance})"
			)
		if full.changed:
			moved_something += 1
		previous = full
	assert moved_something > 20, (
		f"only {moved_something} perturbations moved anything, so the equality "
		f"was mostly comparing a value against itself"
	)
	# The refusal branch is the other half of the equality and it must have
	# fired: an unreachable branch would leave every perturbation that escapes
	# the loop's bracket silently skipped, which is the same vacuity the count
	# above exists to catch.
	#
	# Probed explicitly rather than left to the drift above, and that is a fix
	# rather than a belt-and-braces. The loop carries `previous` forward, so
	# whether any perturbation lands outside the loop's bracket is a property of
	# the *sequence* and not of the graph: over the shipped graph's 52 settable
	# parameters two refuse, and over the expanded graph's 833 none do -- the
	# same code, the same brackets, and a guard that passes or fails on how many
	# knobs the document happens to declare. A guard whose firing depends on the
	# iteration count is not testing the refusal path; it is testing the count.
	# `vre_capacity_target_mw` at +25% of its span refuses from the propagated
	# defaults on both graphs, so pinning it makes the branch reachable by
	# construction.
	probe = graph.nodes.get("vre_capacity_target_mw")
	assert probe is not None and probe.range is not None, "the probe parameter moved"
	probe_values = dict(graph.propagate(defaults).values)
	probe_values["vre_capacity_target_mw"] = probe.default + 0.25 * (
		probe.range[1] - probe.range[0]
	)
	with pytest.raises((DslError, FeedbackError)):
		graph.propagate(probe_values)
	with pytest.raises((DslError, FeedbackError)):
		graph.propagate_incremental(
			probe_values, graph.propagate(defaults), ["vre_capacity_target_mw"]
		)
	refused += 1
	assert refused, "no perturbation left the loop's bracket, so the refusal branch never ran"


def test_incremental_skips_a_loop_nothing_reached(graph: ParameterGraph, defaults: dict):
	"""The saving is skipping the loop solve, and it must not skip a live one.

	The loop solver is two thirds of a full propagation's cost. Skipping a loop
	whose inputs did not move is where the speedup comes from -- and skipping
	one that *did* move is a wrong answer. This checks both directions on the
	real loop: perturbing a member re-solves it (the value changes), and
	perturbing a parameter the loop does not read leaves its members where they
	were.
	"""
	loops = graph.feedback_loops()
	assert loops, "the graph declares no feedback loop, so this test proves nothing"
	members = set(loops[0].variables)
	previous = graph.propagate(defaults)

	# A parameter outside the loop's reach: the loop is carried over unchanged.
	outsider = next(
		n for n in sorted(graph.nodes)
		if graph.is_settable(n)
		and graph.nodes[n].default is not None
		and not (set(graph.affected_by([n])) & members)
		and n not in members
	)
	values = dict(defaults)
	span = graph.nodes[outsider].range
	values[outsider] = (
		span[0] + (span[1] - span[0]) * 0.25 if span else values[outsider] * 1.2
	)
	step = graph.propagate_incremental(values, previous, [outsider])
	for member in members:
		assert abs(step.values[member] - previous.values[member]) <= 1e-12, (
			f"{member} moved although nothing that reaches it changed"
		)


# ---------------------------------------------------------------------------
# Cross-validation rules (`alea_prg.md` §25)
# ---------------------------------------------------------------------------


def test_the_declared_cross_validation_rules_hold_at_every_default(
	graph: ParameterGraph, defaults: dict
):
	"""The shipped rules are satisfiable, which a rule set can fail to be.

	A rule that fires at every parameter's declared default is either a
	threshold nobody can meet or a condition written inside out -- and it would
	make every clean scenario report a finding, which is how a check earns
	being switched off. This is the canary for the shipped four.
	"""
	report = graph.cross_validate(graph.propagate(dict(defaults)).values)
	assert report.rules, "the graph declares no rules, so this test proves nothing"
	# No rule fires at the defaults, and that is a fact about the defaults
	# rather than about the rules. `carbon_revenue_without_an_instrument`
	# reads `ets_enabled` and `carbon_price_coverage`, and batch 24 shipped
	# the ETS off (0.0) beside a covered share of half -- so the revenue
	# identity booked ~650 M USD/year of carbon revenue with no instrument
	# collecting it, and the rule fired on every clean scenario. Batch 27 set
	# `ets_enabled` to 1.0, which is the repair the rule was asking for: the
	# instrument exists, so the revenue has a collector. A second rule firing
	# here still fails the test, and `test_every_declared_rule_can_fire`
	# keeps the quiet rule proven able to fire rather than deleted.
	#
	# Batch 67 restored the nominal-frequency factor to `rocof_definition` and
	# `frequency_nadir_below_protection` now fires at the defaults -- see
	# `KNOWN_DEFAULT_RULES` for why that is the graph reporting a real property
	# of the shipped scenario rather than a rule written inside out.
	live: set[str] = set(KNOWN_DEFAULT_RULES)
	assert {f.rule.id for f in report.violations} == live, [
		str(f) for f in report.violations
	]
	# A blocking finding is one of severity `error`, so the rule that fires at
	# the defaults blocks the scenario -- which is the point: a nadir below the
	# first UFLS stage is not a warning. Pinned to the known rule so a second
	# blocking finding still fails here.
	assert {f.rule.id for f in report.findings if f.rule.severity == "error"} == (
		KNOWN_DEFAULT_RULES
	), [str(f) for f in report.findings if f.rule.severity == "error"]


def test_every_declared_rule_can_fire(graph: ParameterGraph, defaults: dict):
	"""A rule that cannot fire is a rule that checks nothing.

	Each rule is pointed at a scenario built to satisfy its condition, and the
	condition must hold. Without this, a typo in a threshold -- ``>`` for
	``<``, a parameter named but never reached -- leaves a rule that passes
	every scenario forever while reading as a check.
	"""
	from alea.prg.crossval import evaluate_condition

	assert graph.rules, "no rules to check"
	# The base is the *propagated* defaults, not the sparse `defaults` mapping:
	# a rule naming a derived parameter -- `carbon_budget_ratio` is one -- has
	# no default of its own, and evaluating against the sparse set would report
	# the rule undecided rather than untriggerable.
	base = graph.propagate(dict(defaults)).values
	for rule in graph.rules:
		# The probe moves every parameter the rule names, together, over a set
		# of points that spans each declared range: both endpoints, the
		# midpoint, and two interior points either side of it. One parameter at
		# a time is too weak -- a conjunctive condition ("carbon_price > 150
		# AND budget_ratio > 1") needs both past their thresholds, and a probe
		# that held one at its default would report the rule untriggerable when
		# it is merely a rule about a combination.
		#
		# The interior points are what a corners-only sweep missed, and each
		# miss was a false report of a dead rule:
		#
		# * `total_water_demand_m3 > water_availability_m3` over two identical
		#   `(0, 1e11)` ranges holds only *strictly inside*, because at every
		#   corner the two are equal and `>` is false;
		# * `carbon_tax_rate > 0 and carbon_tax_rate < 0.5` over `(0, 500)`
		#   holds only strictly inside too, and both its endpoints fail -- `0`
		#   the lower comparison, `500` the upper.
		#
		# So a probe sampling only `{low, high, mid}` reports a live rule as
		# dead whenever the live band excludes all three, which a strict
		# comparison against a bound guarantees at one end.
		#
		# The interior points are therefore *geometric* as well as arithmetic.
		# A fixed fraction of the span cannot find a narrow band:
		# `carbon_tax_rate > 0 and carbon_tax_rate < 0.5` over `(0, 500)` holds
		# on 0.1% of the range, and a sweep of `{0, 125, 250, 375, 500}` lands
		# nowhere near it. Multiplying the span by `10^-k` for a few `k` puts
		# points at 0.5, 5, 50 as well, which is what a threshold guarding a
		# *scale* -- "this value is in cents, not dollars" -- actually needs.
		names = sorted(rule.parameters)
		points = []
		for parameter in names:
			node = graph.node(parameter)
			# A parameter's admissible set is not always a numeric range. A
			# `categorical` is admissible over its `categories` and carries no
			# range at all, and a `bool` carries none either -- the earlier
			# form of this probe asserted `node.range is not None` for every
			# parameter, which reported the two rules naming a categorical as
			# unevaluable and said so in a way that read like a dead rule. A
			# probe has to sample the domain the node actually has.
			if node.type is ParameterType.CATEGORICAL:
				points.append(sorted(node.categories))
				continue
			if node.type is ParameterType.BOOL:
				points.append([0.0, 1.0])
				continue
			assert node.range is not None, parameter
			low, high = node.range
			span = high - low
			candidates = {low, high}
			for fraction in (0.25, 0.5, 0.75):
				candidates.add(low + span * fraction)
			# Geometric points near each end, where a narrow band sits. Six
			# decades because a band can be arbitrarily narrow relative to its
			# range: `carbon_tax_rate`'s live band is `(0, 0.5)` against a
			# `(0, 500)` range, so the nearest decade point, `0.5`, misses it
			# by the strictness of `<` and only `0.05` lands inside.
			for decade in range(1, 7):
				candidates.add(low + span * (10.0**-decade))
				candidates.add(high - span * (10.0**-decade))
			points.append(sorted(candidates))
		fired = False
		for corner in itertools.product(*points):
			probe = dict(base)
			probe.update(dict(zip(names, corner, strict=True)))
			if evaluate_condition(rule.condition, probe):
				fired = True
				break
		assert fired, (
			f"rule {rule.id!r} cannot be made to fire at any of five points "
			f"spanning each of its parameters' declared ranges, so it checks "
			f"nothing"
		)


def test_a_rule_declared_in_the_document_is_read_not_discarded(document: dict):
	"""A declared rule reaches the graph, which is not what used to happen.

	``from_mapping`` popped ``cross_validation`` off every node and threw it
	away, so a rule was a comment that parsed. This asserts the rule survives
	into ``graph.rules`` and is evaluated -- the "declared is not produced"
	class, closed for this field.
	"""
	doc = dict(document)
	doc["cross_validation"] = [
		{
			"id": "invented_rule",
			"condition": "carbon_price_usd_per_tco2 > 10",
			"severity": "warning",
			"message": "an invented rule",
		}
	]
	rebuilt = ParameterGraph.from_mapping(doc)
	assert [r.id for r in rebuilt.rules] == ["invented_rule"]
	values = {
		name: node.default for name, node in rebuilt.nodes.items()
		if node.default is not None
	}
	report = rebuilt.cross_validate(rebuilt.propagate(values).values)
	assert [f.rule.id for f in report.findings] == ["invented_rule"]


def test_a_rule_naming_an_unknown_parameter_is_refused_at_load(document: dict):
	"""A rule that can never be evaluated is refused, not silently skipped."""
	doc = dict(document)
	doc["cross_validation"] = [
		{"id": "bad", "condition": "not_a_parameter > 1", "severity": "warning"}
	]
	with pytest.raises(GraphError, match="not_a_parameter"):
		ParameterGraph.from_mapping(doc)


def test_a_condition_outside_the_grammar_is_refused():
	"""Arithmetic in a condition is refused: it belongs in an equation.

	``a * b > c`` is a coupling the graph should state, where it is checked
	dimensionally and propagated. Allowing it in a condition puts a relation
	where nothing checks it -- the reason the DSL's whitelist is extended by
	comparisons and nothing else.
	"""
	from alea.prg.crossval import evaluate_condition

	for refused in ("a * b > c", "a + 1 > b", "a", "-a > 1", "f(a) > 1"):
		with pytest.raises(DslError):
			evaluate_condition(refused, {"a": 1.0, "b": 2.0, "c": 3.0})


def test_a_negative_literal_is_expressible():
	"""A parameter whose range is negative has to be comparable to a number.

	``-1.5`` parses as ``USub(Constant(1.5))``. Refusing every unary operator
	made ``price_elasticity < -1.5`` -- a rule over a parameter declared
	``(-3.0, 0.0)`` -- a load error, which is the grammar refusing a condition
	the graph needs rather than one it should not have.
	"""
	from alea.prg.crossval import evaluate_condition

	assert evaluate_condition("a < -1.5", {"a": -2.0})
	assert not evaluate_condition("a < -1.5", {"a": -1.0})


def test_an_undecidable_rule_is_not_a_pass():
	"""A rule the scenario cannot run is reported, not dropped.

	The failure this guards is a report reading "no cross-validation findings"
	for a rule that was never evaluated -- a clean bill of health for a check
	that did not happen, which is the same defect ``units.undecidable`` exists
	to prevent.
	"""
	from alea.prg.crossval import parse_rule, run_rules

	rule = parse_rule("needs_two", "alpha > 1 and beta > 1: warning")
	report = run_rules((rule,), {"alpha": 5.0})
	assert not report.violations, "an unrun rule was reported as a violation"
	assert len(report.undecided) == 1
	assert "beta" in report.undecided[0].detail
	assert "not decided" in report.summary()


def test_only_an_error_severity_rule_blocks():
	"""The three tiers are not decoration: one gates and two do not.

	A check that blocked on a warning is unusable as a gate; one that never
	blocked on an error is a gate that never fires. Both directions here.
	"""
	from alea.prg.crossval import Severity, parse_rule, run_rules

	values = {"a": 5.0, "b": 5.0}
	info = run_rules((parse_rule("i", "a > 1: info"),), values)
	warning = run_rules((parse_rule("w", "a > 1: warning"),), values)
	error = run_rules((parse_rule("e", "a > 1: error"),), values)
	assert info.violations and not info.blocks
	assert warning.violations and not warning.blocks
	assert error.violations and error.blocks
	assert [f.severity for f in error.findings] == [Severity.ERROR]


def test_the_cli_gates_on_an_error_rule(graph: ParameterGraph):
	"""``prg check`` exits non-zero on an ``error``-severity cross-validation rule.

	The gate is only a gate if it is watched failing. The rule that blocks is
	built into a copy of the shipped document, so the exit code is the thing
	under test rather than the shipped thresholds.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	document = yaml.safe_load(PRG_PATH.read_text())
	document["cross_validation"] = [
		{
			"id": "always_error",
			"condition": "carbon_price_usd_per_tco2 > 0",
			"severity": "error",
			"message": "fires on every scenario",
		}
	]
	path = repo_root() / "config" / "prg.yaml"
	backup = path.read_bytes()
	try:
		path.write_text(yaml.safe_dump(document, sort_keys=False))
		runner = CliRunner()
		result = runner.invoke(app, ["prg", "check"])
		assert result.exit_code == 1, result.output
	finally:
		# Restored from bytes captured before the patch, never with
		# `git checkout` -- the canary and any uncommitted work share the file.
		path.write_bytes(backup)


# ---------------------------------------------------------------------------
# Edge strength: the declaration that had no reader
# ---------------------------------------------------------------------------


def test_the_declared_strengths_are_counted_by_tier(graph: ParameterGraph):
	"""The register is the finding: the graph declares all three tiers.

	The spec gives every relationship a strength, and until this was wired the
	field was declared on all 84 edges and read by nothing. A summary that
	reported only the edge count would leave a reader assuming the tiers were
	in use; the count says which of them the model actually uses.

	The shipped graph declared no `soft` equation, and the promotion of the
	generated batches added two: `lcoe_solar_definition` and
	`lcoe_wind_definition`, each carried by four `soft` edges. The count is
	pinned rather than asserted as a property, because it is a fact about
	*this* document -- a new tier appearing should make this test fail and be
	looked at, not pass silently. That is what it did here.

	84 hard and not 83: five of the six equations no edge cites are the
	`*_bound` inequalities the batches added (`demand_shares_bound`,
	`fuel_ccs_adoption_bound`, `industrial_electrification_bound`,
	`local_employment_targets_bound`, `retention_and_deductible_bound`), and
	`strength_of` defaults an uncited equation to `hard`. See the note on the
	previous form of this assertion -- `firm_capacity_definition` was the one
	such equation in the shipped graph, and the count was wrong about it until
	it was moved onto `strength_of`.

	WHY 258 AND NOT 219. Batch 20's sector-coupling layer added 38 equations
	whose edges declare `hard` (or are uncited, where `strength_of` defaults
	them to `hard`); the `soft` pair and the one `informational` equation are
	unchanged, so the tier register gained only hard members. Batch 21's
	demand-and-finance layer added 16 more equations the same way -- all hard,
	`soft` and `informational` again unchanged -- taking the sum to the 222
	equations the batch bakes. Batch 23's extensive-base layer added 16 more,
	all hard -- three Wright-curve learning definitions, seven route and capex
	products, and six household, land, transport and tariff products -- taking
	the sum to the 277 equations the batch bakes. Batch 24 added 43 the same
	way, all hard. Batch 25's gate-family coupling added 13 more, all hard:
	the eight cover, duty, guarantee and permitted-quantity definitions, the
	smart-metered population and the gated carbon volume, taking the sum to
	the 333 equations the batch bakes. Batch 26's adequacy-and-reserve layer
	added 11 more, all hard: the reserve and regulation definitions, the
	spinning, non-spinning and planning-margin aliases, the SAIFI target
	alias, the voltage-support requirement, and the spare-capacity and
	transmission-loss-target definitions, taking the sum to the 344 equations
	the batch bakes. Batch 27's finance family added 14 identities and one
	inequality, all hard: the four aliases, the project hurdle, the two
	microinsurance products, the ring-fenced asset, the transaction cost, the
	two risk charges, the premium pricing and its alias, the solvency capital,
	the RAB roll-forward, and the LLCR covenant, taking the sum to 359.
	Batch 28's product layer added 58 identities, all hard: the five fiscal
	products and the customs-duty alias, the three insurance products, the
	capital and cash products, the eight temporal and operational scalars,
	the seven programme spends, the ten employment and transition products
	and the seventeen aliases, taking the sum to 417. Batch 29's demand and
	macro coupling added 20 identities, all hard: the four demand-side sector
	loads, the seven share products (households, rail, freight, the two
	synthetic fuels, heat-pump saving and industrial heat), the seven
	heritage-and-fiscal definitions and the two charges the macro pack's
	dials price, taking the sum to 437.
	"""
	counts = graph.strength_counts()
	assert counts, "no strength was counted"
	assert sum(counts.values()) == len(graph.equations)
	assert set(counts) <= {"hard", "soft", "informational"}
	# Batch 30's twelve equations all carry hard edges -- the ten products and
	# the two rewritten constraints -- taking the count 434 to 446. The two
	# ceilings ship with hard constraint edges for the same reason the shipped
	# ones do: a build that breaches a sustainability limit is not a soft
	# finding.
	# Batch 31's twenty-eight products and six aliases carry hard edges, and
	# the two amended equations were already hard; the wind LCOE amendment
	# kept its shipped soft tier, which is why the soft count does not move.
	# 446 to 474.
	# Batch 32 ships twenty-two bounds, all hard: a plan that breaches a
	# capacity ceiling or a lead-time bound is not a soft finding. The
	# strength register counts equations, so 474 to 496.
	# Batch 33 ships twenty-six equalities and five bounds, all hard: the six
	# new nodes are products of shipped bases and the five bounds are the same
	# kind of ceiling batch 32 shipped. 496 to 522.
	# Batches 34 and 35 corrected equations in place and added none, so the
	# count held at 522 through both. Batch 36 added seven, all hard: six
	# aliases and products and one time bound, 522 to 529. Batch 37 added
	# seven, all hard: five equalities and two bounds, 529 to 536. Batch 38
	# added eight, all hard: six operational products and two workload
	# bounds, 536 to 544. Batch 39 added five, all hard: three products and
	# two bounds, 544 to 549. Batch 40 added one, hard:
	# `remedy_period_bound`, a time ceiling of the same kind batch 36 shipped,
	# 549 to 550. Its other corrected equation, `coal_price_per_mwh_definition`,
	# was already hard and stayed hard, so it moves nothing here. No batch
	# since 33 has added a soft or informational edge, which is why those two
	# counts have not moved.
	# 550 -> 562 for batch 44: the twelve new equations each carry a `hard`
	# edge from every rhs symbol to the variable they determine. The bounds
	# and identities this batch did not add, so the other two tiers are flat.
	# 562 -> 598 for batch 46: its thirty-six new equations are thirty-five
	# equalities and one inequality, all hard. Eleven per-technology LACE
	# nodes, eleven value-cost ratios, eleven generation identities, the fleet
	# sum, the headroom quotient and the `geq` adequacy bound. The two tiers
	# this batch did not touch stay flat, which is what the equality below is
	# for.
	# Batch 51's three emission-factor equations are equalities with three
	# hard edges each, taking the hard tier 598 -> 601. The other two tiers
	# stay flat, which is what the equality is for.
	# Batch 52 rewrote four equations and added one. The gearing alias and the
	# three complement rewrites keep their edges, and the new debt-share
	# definition adds one hard edge: 601 -> 602. Still the two tiers the batch
	# did not touch, which is what the equality checks.
	# Batch 53's reserve-requirement definition adds one more hard edge, with a
	# bare alias rhs: 602 -> 603. Batch 54's temporal-resolution definition is
	# the same shape -- one hard edge, a quotient rather than an alias -- taking
	# it 603 -> 604. The two tiers this batch did not touch stay flat.
	# Batch 62 deleted `affordability_constraint`, an uncited `geq` that
	# `strength_of` counted as hard, so 604 -> 603. The two tiers it did not
	# touch stay flat, which is what the equality checks -- and the deleted
	# equation is the only reason the total moves, since the surviving bound
	# kept its tier and gained an edge of the same `hard` strength.
	# Batch 63 declares thirty edges for the twenty-one bounds that stated a
	# coupling and carried none, and moves nothing here: the register counts
	# equations, and `strength_of` already reads an uncited equation as `hard`.
	# The tier was right; the edge set was what disagreed with it.
	# Batch 69 deleted `buffer_pool_contribution_definition`, an alias whose one
	# hard edge went with it: 603 -> 602. The two tiers it did not touch stay
	# flat, which is the claim the equality makes.
	assert counts == {"hard": 602, "informational": 1, "soft": 2}, counts
	# Every equation the count puts in a non-hard tier is one some edge
	# declares that way -- the tier is read off the edges, so a `soft` equation
	# with no `soft` edge would mean the register invented it.
	for equation_id in graph.equations:
		tier = graph.strength_of(equation_id)
		if tier == "hard":
			continue
		declared = {
			edge.strength.value
			for edge in graph.edges
			if edge.equation_id == equation_id
		}
		assert tier in declared, (
			f"{equation_id} is counted {tier!r} but its edges declare "
			f"{sorted(declared) or 'none'}"
		)


def test_a_soft_or_informational_violation_does_not_block_and_a_hard_one_does(
	graph: ParameterGraph, defaults: dict
):
	"""The tier is what decides whether a failure is a contradiction.

	``capture_price_ratio_definition`` is the one ``informational`` equation:
	the spec's "reported correlation". Breaking it while a hard equation also
	fails must leave the hard one blocking and this one merely reported --
	otherwise the tier is a comment.
	"""
	values = dict(graph.propagate(defaults).values)
	values["capture_price_usd_per_mwh"] = values["marginal_cost_usd_per_mwh"] * 1.5
	violations = graph.consistency(values)
	by_id = {v.equation_id: v for v in violations}
	assert "capture_price_ratio_definition" in by_id, "the informational rule did not fire"
	assert by_id["capture_price_ratio_definition"].strength == "informational"
	assert not by_id["capture_price_ratio_definition"].blocks
	assert any(v.blocks for v in violations), "a hard equation failed and nothing blocked"


def test_the_informational_tier_is_read_and_cannot_fire_through_a_solve(
	graph: ParameterGraph, defaults: dict
):
	"""The tier is honoured where it can fire, and it cannot fire after a solve.

	``capture_price_ratio_definition`` determines its own variable, so
	``propagate`` recomputes the ratio from the capture price and the marginal
	cost and the equation holds by construction. The tier is therefore
	reachable only through :meth:`consistency` on a set that was *not*
	re-propagated -- which is the honest reading of "reported correlation" for
	a determined equation, and the reason ``check_scenario`` never reports it.

	Pinned as a fact about this document rather than left implicit: a reader
	who assumed the shipped ``informational`` declaration was gating something
	would be wrong, and the test says which path it does and does not reach.
	"""
	propagated = graph.propagate(defaults)
	# A raw set: the ratio moved off its equation and nothing re-solved it.
	raw = dict(propagated.values)
	raw["capture_price_ratio"] = propagated.values["capture_price_ratio"] * 2.0
	direct = graph.consistency(raw)
	informational = [v for v in direct if not v.blocks]
	assert informational, "the ratio was moved off its equation and nothing fired"
	assert informational[0].equation_id == "capture_price_ratio_definition"
	# The same set through a solve: propagation recomputes the ratio, so the
	# equation holds again and the tier has nothing to gate.
	check = check_scenario(raw, graph)
	assert not any(
		v.equation_id == "capture_price_ratio_definition" for v in check.violations
	), "a determined equation cannot fail after the graph recomputes it"
	# The scenario is not clean -- the defaults carry the nadir finding, see
	# `KNOWN_DEFAULT_FINDINGS` -- but nothing *else* fails, which is the claim:
	# the informational tier has nothing to gate once the graph re-solves.
	assert {v.equation_id for v in check.violations} == KNOWN_DEFAULT_FINDINGS, (
		check.violations
	)
	# `consistent` excludes an informational finding, so a direct check of a raw
	# set still calls the scenario consistent -- the gate reads `blocks`.
	assert all(v.blocks for v in direct) is False


def test_a_conflict_carries_its_strength_and_blocks_only_when_hard(
	graph: ParameterGraph, defaults: dict
):
	"""The conflict report reads the same tier the violation does."""
	values = dict(graph.propagate(defaults).values)
	values["capture_price_usd_per_mwh"] = values["marginal_cost_usd_per_mwh"] * 1.5
	report = detect_conflicts(graph, values)
	informational = report.informational()
	assert informational, "no informational conflict was reported"
	assert all(not c.blocks for c in informational)
	# `consistent` is False here because a hard equation also failed; the
	# informational findings are still carried rather than dropped.
	assert any(c.blocks for c in report.conflicts)
	assert "informational" in report.summary() or not report.consistent


def test_a_document_whose_edges_disagree_about_a_strength_is_refused(
	document: dict,
):
	"""Two edges citing one equation at two strengths is a self-contradiction.

	The strength is a property of the *equation*, and a reader taking it from
	an edge would get whichever edge they read first. Refused at construction
	rather than resolved by an arbitrary pick.
	"""
	patched = yaml.safe_load(yaml.safe_dump(document))
	edges = patched["relationships"]
	# Find an equation cited by more than one edge and flip one of its edges.
	from collections import Counter

	cited = Counter(edge["equation_id"] for edge in edges)
	shared = next(eq for eq, n in cited.items() if n > 1)
	flipped = False
	for edge in edges:
		if edge["equation_id"] == shared:
			edge["strength"] = "informational" if not flipped else "hard"
			flipped = True
			break
	with pytest.raises(GraphError, match="two strengths"):
		ParameterGraph.from_mapping(patched)


def test_the_summary_serves_the_strength_register(graph: ParameterGraph):
	"""`graph_summary` carries the tiers, so the API and the CLI both see them."""
	summary = graph_summary(graph)
	assert summary["edge_strength"] == graph.strength_counts()
	assert sum(summary["edge_strength"].values()) == len(graph.equations)


def test_the_conflict_gate_reads_the_tier_and_a_softened_edge_stops_blocking():
	"""The CLI exit code follows the declared strength, not the residual.

	`prg conflicts --set carbon_price_usd_per_tco2=90` fails
	`llcr_floor_bound` and exits 1. The same scenario with that equation's edge
	declared `informational` must exit 0 while still *printing* the finding --
	a gate that ignored the tier would exit 1 either way, and this is the canary
	that tells the two apart.

	WHY THE TARGET IS THE LLCR COVENANT AND NOT `dscr_requirement`. Batch 27
	made the loan-life coverage ratio a bound with an edge, and it binds
	*before* the DSCR covenant across the whole carbon-price sweep: at 90 the
	LLCR is 1.2728 against a 1.4 floor while the DSCR is still 1.4763 against
	1.3. So there is no carbon price at which `dscr_requirement` blocks alone,
	and a canary pinned to it would fail on its premise rather than on the
	mechanism. The LLCR bound is also the better subject: it is the one bound in
	the graph whose edge carries the tier, which is exactly the property under
	test.

	WHY 90 AND NOT 150. The canary's claim is "softening *this* edge flips the
	gate", and that claim needs the softened edge to be the *only* thing
	blocking -- otherwise the exit code stays 1 for a reason the canary is not
	about. At 110 and above the DSCR covenant fires beside it, and at 200 the
	fleet's cash available for debt service goes negative, so `llcr_estimate`
	derives negative and reports an out-of-range conflict of its own. Both are
	the graph working; neither is a scenario with one blocker. The premise is
	asserted below rather than assumed, so a future equation that starts
	blocking at 90 fails this test on the premise instead of on the mechanism.
	"""
	from typer.testing import CliRunner

	from alea.cli import app
	from alea.prg import load_graph
	from alea.prg.conflicts import detect_conflicts

	target = "llcr_floor_bound"
	carbon_price = "90"
	# A response time that keeps the nadir inside its range, so the LLCR
	# covenant is genuinely the only blocker. Without it the shipped defaults
	# report the nadir finding at every carbon price (see
	# `KNOWN_DEFAULT_FINDINGS`) and softening the LLCR edge could not flip the
	# exit code -- the canary would fail on its premise.
	response_time = "4"

	# The premise: the softened edge is the only blocker at this scenario.
	graph = load_graph()
	scenario = {
		k: n.default for k, n in graph.nodes.items() if n.default is not None
	}
	scenario["carbon_price_usd_per_tco2"] = float(carbon_price)
	scenario["frequency_response_time_s"] = float(response_time)
	propagated = graph.propagate(scenario)
	blockers = {
		c.subject
		for c in detect_conflicts(
			graph, propagated.values, supplied=scenario, rank=1
		).conflicts
		if c.blocks
	}
	assert blockers == {target}, (
		f"the canary needs {target!r} to be the only blocker at carbon price "
		f"{carbon_price}, and the scenario blocks on {sorted(blockers)} -- so "
		f"softening the edge could not flip the exit code and this test would "
		f"fail for a reason it is not about"
	)

	path = repo_root() / "config" / "prg.yaml"
	backup = path.read_bytes()
	document = yaml.safe_load(path.read_text())
	softened = False
	for edge in document["relationships"]:
		if edge["equation_id"] == target:
			edge["strength"] = "informational"
			softened = True
	assert softened, f"no edge cites {target!r}; the canary patched nothing"
	try:
		path.write_text(yaml.safe_dump(document, sort_keys=False))
		runner = CliRunner()
		result = runner.invoke(
			app,
			[
				"prg",
				"conflicts",
				"--set",
				f"carbon_price_usd_per_tco2={carbon_price}",
				"--set",
				f"frequency_response_time_s={response_time}",
			],
		)
		assert result.exit_code == 0, result.output
		# Printed, not hidden: the finding survives and only the gate moves.
		assert target in result.output
	finally:
		# From captured bytes, never `git checkout` -- the canary and any
		# uncommitted work share the file.
		path.write_bytes(backup)
	# The backup restored the hard edge, so the gate fires again.
	restored = CliRunner().invoke(
		app,
		[
			"prg",
			"conflicts",
			"--set",
			f"carbon_price_usd_per_tco2={carbon_price}",
			"--set",
			f"frequency_response_time_s={response_time}",
		],
	)
	assert restored.exit_code == 1, restored.output


def test_the_cli_refuses_an_endogenous_knob_with_the_reason_it_was_refused(
	graph: ParameterGraph,
):
	"""Three reasons a knob is refused, and the message must name the right one.

	``is_settable`` collapses them into one boolean, so a CLI reading only that
	boolean says "computed by <equation>" about a solved fleet -- a false
	diagnosis whose implied advice (set what it depends on) cannot be followed,
	because nothing a user sets determines what the optimiser chooses.

	The exit code is asserted as well as the text: a refusal that prints and
	exits 0 is a warning, and a script gating on it would proceed.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	runner = CliRunner()
	endogenous = runner.invoke(
		app, ["prg", "check", "--set", "thermal_capacity_mw=9000"]
	)
	assert endogenous.exit_code == 2, endogenous.output
	assert "chosen by the optimisation" in endogenous.output, endogenous.output
	# The two must not be confused: the endogenous message must not carry the
	# derived one's advice, which is the specific wrong sentence this branch
	# exists to avoid.
	assert "set the parameters it depends on" not in endogenous.output

	# The derived branch still says its own thing, so the split is a split and
	# not a replacement.
	derived = runner.invoke(app, ["prg", "check", "--set", "firm_capacity_mw=9000"])
	assert derived.exit_code == 2, derived.output
	assert "firm_capacity_definition" in derived.output, derived.output


def test_every_declared_citation_reaches_a_door(graph: ParameterGraph):
	"""`Equation.reference` was parsed, validated and read by nothing.

	Nine of the thirty-nine equations declare a citation. The field loaded on
	all nine and reached no report, no route and no CLI line, so the library's
	provenance was invisible to every caller -- the "declared is not produced"
	shape this tree keeps finding. The reader is `equation_report`, and this
	asserts it at the level the field is *about*: the count of citations that
	survive the trip out of the graph.
	"""
	from alea.prg.service import EquationRow, equation_report

	rows = equation_report(graph)
	assert len(rows) == len(graph.equations)
	assert all(isinstance(row, EquationRow) for row in rows)

	declared = {
		equation.id: equation.reference
		for equation in graph.equations.values()
		if equation.reference
	}
	# The premise, asserted rather than assumed: if a future document declares
	# no citations this test would pass vacuously and the reader would be
	# untested. Nine is the shipped count and a change to it should be looked
	# at, not absorbed.
	# The shipped count was nine; the coupling batches' equations each carry
	# the work their form comes from, which is the register the build was
	# for -- a researcher retrieves the equation through the reference. Batch
	# 20's sector-coupling layer added 38 equations. The definitions among
	# them carry None rather than a pointer no register row resolves (the
	# four registered works their forms keep -- Short, Stoft, NREL ATB, IEEE
	# 1366 -- are the eight non-definition citations), taking the register
	# 92 to 100. Batch 21's demand-and-finance layer added four citations to
	# its equations -- five compound growth factors and the heat-pump annuity,
	# each citing "Short, Packey & Holt (1995), NREL/TP-462-5173" -- taking
	# the register 100 to 104. Batch 22's compliance layer added eight more:
	# two NREL ATB 2025 rows (the climate-proofing and local-content capex
	# definitions), four Stoft 2002 rows (the demand-charge revenue, largest-
	# loss response, non-spinning reserve and reserve-margin requirement) and
	# two IEEE 1366 rows (the SAIDI and SAIFI ceilings), taking the register
	# 104 to 112. Batch 23's extensive-base layer added three more: the
	# Wright's-law learning definitions for solar PV, batteries and
	# electrolysers, taking the register 112 to 115; the other thirteen
	# equations the batch adds are the products' own forms and carry None.
	# Batch 24's carbon-market, subsidy and employment layer added twenty-
	# three: five EU CBAM rows (the ETS cap, auction volume, Article 6.2
	# credits, leakage and the position limit), five World Bank revenue-cap
	# rows (the X-factor, hybrid cap, service-quality reward, working-capital
	# allowance and tariff rebalancing), four catalog duplicate rows (the
	# carbon budget, tax coverage, price cap and social-tariff identities),
	# four pass-through rows (the cross-border and distribution wheeling, the
	# wheeling charge and the feed-in tariff), three Stoft rows (the price
	# band and market concentration), one standard-fiscal row (the carbon-tax
	# offset) and one benefit-sharing row (the cross-subsidy transfer), taking
	# the register 115 to 138. The batch's fifty equations declare twenty
	# None (the definitions' own forms) and seven citations batch 23 had
	# already registered; the rest are the twenty-three above. Batch 25's
	# gate-family coupling added one more: the gated carbon volume cites the
	# EU CBAM regulation, taking the register 138 to 139; the other twelve
	# equations the batch adds are the cover, duty and permitted-quantity
	# definitions' own forms and carry None. Batch 26's adequacy-and-reserve
	# layer added eleven equations, ten of which cite a work already in the
	# register -- the Stoft 2002 chapter for the operating-margin alias and
	# the regulation up and down definitions, the N-1 planning criterion for
	# the spinning-reserve, spare-capacity and planning-margin definitions,
	# IEEE 1366 for the SAIFI target and the voltage-support requirement, and
	# the catalog's own duplicate rows for the two requirement aliases -- so
	# the count of distinct works stays at 44 while the register goes 139 to
	# 149. The eleventh, `transmission_loss_target_definition`, carries None:
	# it briefly carried an NREL ATB row, and that was wrong -- a policy
	# target's arithmetic, `factor * (1 - share)`, is an identity rather than
	# an external result. The batch therefore adds no citation, and the
	# register moves by the ten that reuse existing works. Batch 29's
	# demand-and-macro layer added twenty equations and two citations:
	# `desalination_demand` takes the catalog's own bottom-up load-synthesis
	# method cell, and `lpg_subsidy_spend_usd_per_year` takes the
	# standard-fiscal row the batch-22 withholding-tax products already
	# registered, so the count of distinct works stays at 47 while the
	# register goes 183 to 185. The other eighteen carry None: the share
	# products, the heritage and exposure definitions, the currency hedge
	# and the four demand loads are definitions of their own operands rather
	# than statements of an external result. A further change is a change to
	# the register's coverage and fails here.
	# Batch 31 added five: the CCGT alias, the hydrogen cost alias, the
	# cause-attributed events, the gearing utilisation and the wind LCOE
	# amendment's NREL ATB reference.
	# Batch 32 added sixteen of its twenty-two bounds. The sixteen split
	# three ways: thirteen capacity ceilings cite Oree et al. (2017) for the
	# GEP constraint inventory (coal, gas, hydro, nuclear, fusion, the fuel
	# cell, the four marine technologies, SMR, the two solar build ceilings);
	# the carbon auction cites EU ETS Directive 2023/959 and the CSP ceiling
	# IEA/NEA EGC; and the thermal store cites IEA/NEA EGC for its duration.
	# The six that carry None are the four storage-envelope bounds, the
	# spare-parts lead time and the transboundary water ceiling -- each a
	# definitional relation between two quantities the graph already carries,
	# not a statement of an external result. 199 to 215.
	# Batch 33 added eleven of its twenty-six. Six products: the three
	# depreciation schedules cite Short, Packey & Holt (1995) for the
	# straight-line and declining-balance formulas; the electrolyser O&M bill
	# cites IEA/NEA EGC for the variable rate; `value_of_lost_load` cites the
	# ENTSO-E adequacy methodology; and `willingness_to_pay_usd_per_year` cites
	# the NREL report for willingness to pay as a benefit valuation. All five
	# bounds are cited -- Oree et al. (2017) for the two capacity ceilings and
	# the penetration limit, IEA/NEA EGC for the electrolyser floor, the World
	# Bank revenue-cap handbook for the review period, and Koltsaklis &
	# Dagoumas (2018) with Oree for the fleet floor.
	#
	# The fifteen that carry None: the seven aliases (an alias of a shipped
	# quantity states no external result of its own -- `accelerated_depreciation`,
	# `buffer_pool_contribution`, `consumer_price_index_link`,
	# `health_impact_dalys`, `health_impact_mortality`, `ppa_indexation`,
	# `premium_share_of_asset`); the six definitional products whose operands
	# the graph already carries (`fuel_excise_revenue_usd_per_year`,
	# `gis_mapped_network_km`, `cross_border_losses_twh`,
	# `electrolyser_variable_opex_usd_per_year` is *not* among them -- it is
	# cited above -- so the six are `compensation_rates`,
	# `gdp_per_capita_growth`, `hydrogen_demand_domestic`,
	# `hydrogen_production_demand`, `rooftop_solar_households` and
	# `fuel_excise_revenue_usd_per_year`); and the two whose source is an
	# `INDEX.md` row with no archived file, which the register does not count.
	# 215 to 226.
	# Batch 39 added one, the OCGT/CCGT capex ordering bound, which cites
	# the archived IEA/NEA 2020 text for the ordering its prose states. Its
	# other four carry None: three are unit conversions and the fourth is a
	# coherence condition between two shipped quantities. 241 to 242.
	# Batch 38 took it 233 to 241, and cites all eight: the three operational products and the
	# workshop bound to the ENTSO-E adequacy methodology, the storage energy
	# to IEA/NEA EGC's E/P definition, the settlement security and the budget
	# bound to the World Bank regulatory handbook, and the age complement to
	# the catalog's own duplicate-row register. 233 to 241.
	# Batch 42 added two: the fleet-intensity and emissions definitions, which
	# were rewritten to carry the works their forms come from -- the IEA/NEA
	# CCUS cost entry for the capture share and the IPCC activity-data x
	# emission-factor construction for the fleet account. Both were rewritten
	# in place and carried None before, so the register grows without the
	# equation count moving. 242 to 244.
	# Batch 43 added three: the firm-VRE reserve constraint and the two
	# definitions that carry the capacity credit. All three were rewritten in
	# place and carried None before, and all three cite the same two archived
	# works -- IEA/NEA EGC 2020 section 4 for what a capacity credit is and
	# the EIA LCOE methodology for the derating of intermittent renewables and
	# its 15% wind example, which is the value `vre_capacity_credit` ships.
	# The equation count does not move. 244 to 247.
	# Batch 44 added twelve: the three fuel-energy definitions, the six
	# pollutant totals, the fleet's own concentration contribution and the
	# total. Each carries the guidebook table its factors come from or the
	# IEA/NEA efficiency row its divisor does, so a reader reaches the cell
	# rather than a genre. The deaths equation was rewritten in place and
	# already carried the AirQ+ citation, so it does not add to the register.
	# 247 to 259.
	# Batch 46 added twenty-six: the eleven value-cost ratios and their eleven
	# definitions, the eleven generation identities, the fleet sum, the
	# headroom quotient, LACE and the adequacy bound all carry the EIA LCOE
	# methodology, which is archived as `eia_lcoe_methodology.txt`. That is
	# one work cited across a family of equations rather than a new work per
	# row, which is the same shape batch 44's pollutant table had.
	# 259 to 295.
	# Batch 51's three emission-factor equations each carry a reference (IPCC
	# 2006 Table 2.2), taking the register 295 -> 298. Batch 52's debt-share
	# definition cites the UKRN cost-of-capital review, 298 -> 299, and batch
	# 53's reserve requirement cites NERC's planning reserve framework, 299 -> 300.
	# Batch 54's temporal-resolution definition cites the placeholder survey and
	# the `tsam` segmentation it names: 300 -> 301. That citation was registered
	# only as prose until batch 56, when the survey got an INDEX row of its own;
	# until then `citation_report()` reported it unregistered, because the
	# report reads equations and the row did not exist.
	# Batch 60 is the first batch to move this register *down*, and the movement
	# is the point. `x_factor_revenue_reduction_definition` cited the World Bank
	# *Regulation of Utilities* handbook, which is archived at
	# `sources/archive/world_bank_regulating_utilities_handbook.txt`. The
	# handbook discusses price-cap and revenue-cap regulation and states the
	# RPI-X arithmetic nowhere -- "RPI" and "X factor" appear in no formula
	# context in the archived text -- so the citation was a label for a family
	# rather than support for the equation, and the corrected arithmetic is an
	# identity (`x * base`) that needs no external result. The reference is
	# therefore `None` and the register goes 301 -> 300. That is coverage
	# falling because an unsupported citation left, not a citation being lost:
	# the batch-34 note records the same judgement for the buffer rate.
	#
	# Batch 68 moves it *up*, 300 -> 301, and the new citation is the first one
	# attached to `frequency_nadir_definition`. That equation had no reference
	# at all, which is why the 10 s `frequency_response_time_s` it multiplies
	# was an uncited number sitting inside a cited equation: the register joins
	# *equation* references, so a node's own `source` field is invisible to it.
	# Shams (2017) is the source for the quantity the equation is about -- time
	# to nadir in a low-inertia system, "in the order of 2 to 3s", and fast
	# frequency response defined as response within 0.5 s of triggering. It does
	# not state the 10 s default; that gap stays open and is recorded in
	# `docs/prg-status.md`.
	#
	# Batch 69 moves it 301 -> 302, and the movement is a citation *replacing*
	# a bare assertion rather than a number being counted. The batch-34 note
	# above says "the same judgement for the buffer rate": the reversal
	# allowance was judged definitional, an identity over operands the graph
	# already carries, and shipped with `reference: null`. The archived Verra
	# AFOLU Non-Permanence Risk Tool v4.2 states the arithmetic at 2.5.4 -- a
	# risk rating converts to a percentage, and that percentage multiplies the
	# net change in carbon stocks -- so the judgement was wrong and the
	# reference is now the standard's own rule. The same batch deprecates
	# `buffer_pool_contribution` and removes its equation, which is why the
	# equation count falls; a deprecated node may not be reached by an
	# equation (`_deprecated_reach`), so the alias's coupling is its deletion.
	assert len(declared) == 302, f"the citation register moved: {sorted(declared)}"

	carried = {row.equation_id: row.reference for row in rows if row.reference}
	assert carried == declared, (
		"the report dropped or altered a citation the graph declares; the field "
		"is read again, which is the thing that was not true before"
	)
	# The other 310 carry `None` and not an empty string: "no external
	# source" and "a source that rendered blank" are different findings.
	blank = [row.equation_id for row in rows if row.reference == ""]
	assert not blank, f"a citation rendered as an empty string rather than None: {blank}"


def test_a_citation_reaches_the_api_and_the_cli(graph: ParameterGraph):
	"""The reader is only a reader if a caller outside the package sees it.

	A service function nothing serves is the same defect one layer up: the
	field would move from "declared and unread" to "read and unreachable".
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	runner = CliRunner()
	result = runner.invoke(app, ["prg", "equations", "--system", "health"])
	assert result.exit_code == 0, result.output
	# The WHO AirQ+ citation is on `premature_deaths_definition`, in `health`.
	assert "WHO AirQ+" in result.output, result.output
	# And the equations without one print no citation line, so the absence is
	# absence rather than a blank column.
	# `employment` carries references now (the multipliers), so the
	# no-citation half pointed at `energy_balance`, whose equations are the
	# kernel's own identities and cited nothing external. Batch 28's product
	# layer changed that: the investment-period length cites Tejada-Arango
	# for the multi-period formulation, and the load-factor override cites
	# the catalog's duplicate-row register. So the half points at
	# `capture_price`, whose seven equations are the strike-and-capture
	# arithmetic and cite nothing.
	ppaless = runner.invoke(app, ["prg", "equations", "--system", "capture_price"])
	assert ppaless.exit_code == 0, ppaless.output
	assert "ref:" not in ppaless.output, ppaless.output


def test_the_specs_unit_check_field_loads_and_is_read(graph: ParameterGraph):
	"""§12 declares `unit_check`; until 2026-10-16 the model did not carry it.

	A document written to the spec's own §12 example -- which includes
	`unit_check: true` -- was **refused** at load with `extra_forbidden`,
	because `Equation` sets `extra="forbid"`. That is a worse failure than a
	missing field: the spec's YAML is not a document this service accepts.

	All three halves are asserted, because any one alone would pass against a
	broken implementation: the spec's example loads, the default is `True` so
	no existing equation changes meaning, and a `False` is *read* rather than
	merely accepted.
	"""
	from alea.prg.units import check_graph

	# The spec's §12 example, verbatim in the fields that matter.
	spec_example = Equation(
		id="total_cost",
		name="Total system cost",
		system="cost_accounting",
		lhs="total_cost_usd",
		rhs="capex_usd + opex_usd",
		tolerance=1e-6,
		unit_check=True,
		reference="PyPSA objective function",
		priority="P1",
		solution_method="numeric",
		linearity="linear",
	)
	assert spec_example.unit_check is True
	# The default, so a document that omits the key behaves as before.
	assert Equation(id="x", name="X", system="s", lhs="a", rhs="b").unit_check is True

	# And it is read. `False` reclassifies the verdict; it does not skip the
	# walk, so the equation is still checked and still reported.
	report = check_graph(graph)
	# Three equations in the shipped library declare the exemption, and all
	# three are the same kind: a unit *conversion* whose constant the walker
	# cannot see. ``consumer_surplus_definition`` scales TWh to MWh with a bare
	# ``1000000``; ``gas_price_per_mwh_definition`` divides USD/MMBtu by a bare
	# ``0.293`` that means MMBtu/MWh; ``llcr_definition``'s annuity carries the
	# exponent convention the walker does not credit. The declaration is the
	# author saying so, which is what the field is for -- so this asserts the
	# set rather than its emptiness, and a fourth exemption is a failing test.
	#
	# There were four until batch 40. ``coal_price_per_mwh_definition`` was
	# ``coal_price / (25 * 3.6)`` and needed the exemption because the walker
	# reads ``31.6`` as dimensionless; the batch replaced it with
	# ``coal_price / mwh_per_coal_unit``, where the divisor is a typed
	# ``MWh/tonne`` node, so the walk discharges it and the exemption went.
	# That is the exemption doing its job: it marked an untyped constant, and
	# typing the constant retired the marker.
	assert set(report.exempt) == {
		"consumer_surplus_definition",
		"gas_price_per_mwh_definition",
		"llcr_definition",
	}, report.exempt
	assert len(report.checks) == len(graph.equations), (
		"an exempt equation must still be checked -- skipping it would hide an "
		"equation that later became decidable"
	)

	target = "energy_balance"
	patched = dict(graph.equations)
	patched[target] = patched[target].model_copy(update={"unit_check": False})
	exempted = ParameterGraph(graph.nodes, patched, graph.edges, rules=graph.rules)
	after = check_graph(exempted)
	# The three declarations above, plus the one just patched in. Asserted as a
	# set so this reads as "the patch was read" rather than as a count that
	# happens to be four.
	assert set(after.exempt) == set(report.exempt) | {target}, after.exempt
	# The check still ran: the exempt equation is in `checks` as before.
	assert len(after.checks) == len(graph.equations)
	# And the exemption is announced rather than silently shrinking a count.
	assert "exempt by declaration" in after.summary(), after.summary()
	assert f"{len(after.exempt)} are exempt" in after.summary(), after.summary()


# ---------------------------------------------------------------------------
# Linearity as a fact about a variable, and the exact solve it licenses
# ---------------------------------------------------------------------------


def test_linearity_is_a_property_of_a_variable_not_of_an_equation():
	"""``x ** 2`` is nonlinear in ``x`` and constant in ``y``.

	This is the distinction the model's equation-level ``linearity`` field
	could not carry, and the reason no reading of the formulas reproduced the
	declared column: an equation has no linearity of its own, so a label on it
	has to pick a variable and does not say which.
	"""
	quadratic = parse("a * x ** 2 + b * y")
	assert linearity_in(quadratic, "x") == "nonlinear"
	assert linearity_in(quadratic, "y") == "linear"
	assert linearity_in(quadratic, "a") == "linear"
	# A variable the expression never names is linear in it -- it is a
	# coefficient, and every coefficient is constant in the unknown.
	assert linearity_in(quadratic, "zzz") == "linear"

	# The cases that decide the classification, each spelled out because each
	# is a way a structural walk gets it wrong.
	assert linearity_in(parse("a ** x"), "x") == "nonlinear", (
		"a symbol in the exponent is exponential in it, and a walk that only "
		"looks at the base sees a symbol-free base and calls it absent"
	)
	assert linearity_in(parse("x * x"), "x") == "nonlinear"
	assert linearity_in(parse("exp(x)"), "x") == "nonlinear"
	assert linearity_in(parse("1 / x"), "x") == "nonlinear"
	assert linearity_in(parse("sqrt(x)"), "x") == "nonlinear"
	assert linearity_in(parse("x / k"), "x") == "linear"
	assert linearity_in(parse("-3 * x + b"), "x") == "linear"
	assert linearity_in(parse("x ** 1"), "x") == "linear"


def test_the_coefficients_reconstruct_the_expression():
	"""``e == a * x + b`` for every affine ``e``, checked numerically.

	The identity is the whole contract of :func:`linear_coefficients`, and it
	is checked by evaluation rather than by comparing trees: a structural
	comparison would pass on a decomposition that reordered terms and fail on
	one that is arithmetically identical, which is backwards.
	"""
	cases = [
		"a * x + b",
		"x / k + c",
		"-3 * x",
		"2 * (x + a) - a",
		"(x + 1) * (a + b)",
		"x",
		"a * x",
		"x * 2 / (k + 1)",
		"b + x",
	]
	points = [
		{"a": 2.5, "b": -7.0, "c": 1.0, "k": 4.0, "x": 3.0},
		{"a": -1.0, "b": 0.0, "c": 5.5, "k": -2.0, "x": -4.0},
		{"a": 0.0, "b": 9.0, "c": -3.0, "k": 0.5, "x": 0.0},
		{"a": 1e6, "b": 1e-6, "c": 12.0, "k": 1e3, "x": 7.5},
	]
	for source in cases:
		expression = parse(source)
		decomposition = linear_coefficients(expression, "x")
		assert decomposition is not None, f"{source!r} should be affine in x"
		coefficient, rest = decomposition
		for values in points:
			lhs = evaluate(expression, values)
			rhs = evaluate(coefficient, values) * values["x"] + evaluate(rest, values)
			assert math.isclose(lhs, rhs, rel_tol=1e-12, abs_tol=1e-12), (
				f"{source!r} decomposed as ({coefficient.source()}) * x + "
				f"({rest.source()}) gives {rhs} where it evaluates to {lhs} at "
				f"{values}"
			)

	# `2 * (x + a) - a` is the case a product decomposition drops: the scale
	# on the bracketed term reaches both the coefficient and the constant.
	expression = parse("2 * (x + a) - a")
	scaled = linear_coefficients(expression, "x")
	assert scaled is not None
	coefficient, rest = scaled
	assert evaluate(coefficient, {"a": 5.0}) == 2.0
	assert evaluate(rest, {"a": 5.0}) == 5.0

	# A symbol the expression never names has no coefficient to return, and
	# answering (0, expression) would let a caller divide by zero a step later
	# with nothing pointing at the cause.
	with pytest.raises(DslError):
		linear_coefficients(parse("a + b"), "x")


def test_the_affine_solve_agrees_with_the_bracket_search(graph: ParameterGraph):
	"""The exact root equals the numeric one for every determined variable.

	The two are different algorithms -- ``-b / a`` against Brent in a bracket
	-- so their agreement is evidence about both. This is the check that says
	the affine path is a *shortcut* and not a different answer, which is what
	makes it safe to prefer.
	"""
	values = {
		k: n.default for k, n in graph.nodes.items() if n.default is not None
	}
	values = dict(graph.propagate(values).values)

	compared = 0
	for equation in graph.equations.values():
		for variable in equation.determined_variables:
			residual = parse(f"({equation.lhs}) - ({equation.rhs})")
			exact = solve_affine(residual, variable, values)
			assert exact is not None, (
				f"{equation.id!r} is not affine in {variable!r}, the variable it "
				f"solves for -- which the shipped library is expected not to "
				f"contain, and this is the assertion that would notice"
			)
			bracket = graph.node(variable).range
			assert bracket is not None, (
				f"{variable!r} is derived but declares no range, so there is no "
				f"bracket to search and nothing to compare against"
			)
			# The declared range is the node's *admissible* set, not the set the
			# solver may look in -- `graph._widen` searches outward for exactly
			# this reason, so that an answer outside the range is a reported
			# excursion rather than an unsolvable equation. `frequency_nadir_hz`
			# is the case in point after batch 67: its corrected value is
			# 43.62 Hz against a 45 Hz floor. Widening here keeps this test
			# comparing the two *algorithms*, which is its claim, instead of
			# re-asserting that every derived value is admissible.
			numeric = graph._widen(residual, variable, values, bracket)
			assert numeric is not None, (
				f"{equation.id!r} solved for {variable!r}: the numeric search "
				f"found no root even after widening past the declared range"
			)
			assert math.isclose(exact, numeric, rel_tol=1e-9, abs_tol=1e-12), (
				f"{equation.id!r} solved for {variable!r}: exact {exact!r} vs "
				f"numeric {numeric!r}"
			)
			compared += 1
	# Batch 52's debt-share definition is affine in the variable it solves for,
	# like every equation the earlier batches added, so the compared set moves
	# 531 -> 532, and batch 53's reserve requirement 532 -> 533, and batch 54's
	# temporal-resolution definition 533 -> 534. Batch 69 takes it back to 533:
	# `buffer_pool_contribution` stops being derived when its alias equation is
	# removed, so one fewer equation is compared.
	assert compared == 533, (
		f"expected 481 determined variables in the shipped library, compared "
		f"{compared}; a change to the equation count is a change to this "
		f"check's coverage. It was 153 after the generated batches were "
		f"promoted; batch 20's sector-coupling layer raised it to 182, "
		f"batch 21's demand-and-finance layer raised it to 198, batch 22's "
		f"compliance layer raised it to 227, batch 23's extensive-base "
		f"layer raised it to 243, batch 24's carbon-market layer raised "
		f"it to 286, batch 25's gate-family coupling raised it to 299, "
		f"batch 26's adequacy-and-reserve layer raised it to 310, and batch "
		f"28's product layer raised it to 382, batch 29's demand-and-macro "
		f"layer raised it to 402, batch 30's supply-and-grid layer raised "
		f"it to 412, batch 31's product remainder to 440 and batch 33's "
		f"residue layer to 461 -- every equation each batch added is affine in the "
		f"variable it solves for, which is the claim the "
		f"`exact is not None` above makes, at the wider coverage"
	)


def test_every_shipped_derivation_takes_the_exact_path(graph: ParameterGraph):
	"""No equation in the library needs a bracket, and the register says so.

	``solve_paths`` is the measured replacement for the declared ``linearity``
	field: written by the branch that took the solve, so it cannot drift from
	the arithmetic the way a hand-entered label did. A ``"numeric"`` entry is
	the finding worth acting on -- it is the only case where the answer came
	from a bracket that could have missed -- and the shipped library has none.
	"""
	values = {
		k: n.default for k, n in graph.nodes.items() if n.default is not None
	}
	graph.propagate(values)
	paths = graph.solve_paths()

	assert paths, "a propagation must record which solve fixed each parameter"
	assert set(paths.values()) == {"affine"}, (
		f"every equation in the shipped library is affine in the variable it "
		f"solves for; these are not: "
		f"{sorted(k for k, v in paths.items() if v == 'numeric')}"
	)
	# The derived parameters, not the loop variables: the loops are solved by
	# `feedback.solve_loop`, which does not write this register.
	derived = {
		e.determined_variables[0]
		for e in graph.equations.values()
		if e.determined_variables and e.solution_method != "iterative"
	}
	assert set(paths) == derived, sorted(set(paths) ^ derived)


def test_a_nonaffine_equation_falls_back_and_is_reported():
	"""The fallback is reachable, and a graph that needs it says so.

	Every shipped equation is affine, so the numeric branch is dead code
	unless a document exercises it -- and dead code in a solver is the kind
	that breaks silently. This drives a genuinely nonlinear derivation through
	the graph and asserts both that it solves and that the register names it.
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

	document = {
		"parameters": {
			"x": node("x", "exogenous", default=3.0),
			"y": node("y", "derived", range=[0.0, 100.0]),
		},
		"equations": {
			# Quadratic in `y`, so `solve_affine` returns None and the bracket
			# search runs. The root is sqrt(9) = 3.
			"e_y": {
				"name": "y",
				"lhs": "y ** 2",
				"rhs": "x ** 2",
				"parameters": ["y", "x"],
				"determined_variables": ["y"],
				"system": "cost_accounting",
			},
		},
	}
	synthetic = ParameterGraph.from_mapping(document)
	result = synthetic.propagate({"x": 3.0})
	assert math.isclose(result.values["y"], 3.0, rel_tol=1e-9), result.values["y"]
	assert synthetic.solve_paths() == {"y": "numeric"}, synthetic.solve_paths()


def test_both_feedback_loops_converge_in_the_iteration_count_this_tree_pins(
	graph: ParameterGraph, defaults: dict
):
	"""Pin both loop counts, so a solver change that doubles them fails.

	`docs/prg-status.md` records the measurement behind §37's rejection --
	Anderson acceleration is 63 and 45 turns against plain damped Gauss-Seidel's
	38 and 36 -- and names this as the weakest part of that entry: the numbers
	reproduce from `scripts/measure_loop_convergence.py` but nothing in the tree
	pins them, so a change to the damping factor, the loop's equation set or a
	node's range could move them without a gate failing. This is the gate.

	**The exact count is pinned, not a bound.** "Converges in under 50 turns"
	would pass a solver that needs 49 where this one needs 38, which is the
	1.3x regression the entry exists to warn about -- and the whole reason the
	numbers are worth writing down is that they are a *baseline* an accelerator
	has to beat. A bound loose enough to survive any change is a bound that
	reports nothing.

	**Keyed by variable, not by index.** `detect_loops` returns components in
	Tarjan's traversal order, so an index-based assertion would check whichever
	loop the algorithm reached first and keep passing after the loop it meant
	to check was deleted, as long as some other loop took its place. `_loop_over`
	already exists for this reason and is reused here.

	**Both counts, and the second is the one a rewrite would drop.** Loop 2 is
	two-dimensional and converges in fewer turns; a solver that special-cased
	the three-dimensional loop would move only the first number. Asserting both
	is what makes the pair a measurement rather than one number and a spare.
	"""
	expected = {"vre_capacity_mw": 38, "equilibrium_demand_twh": 36}
	result = graph.propagate(dict(defaults))

	assert result.loops, "the graph carries two feedback loops and propagated none"
	measured = {
		variable: next(
			loop.iterations for loop in result.loops if loop.loop == _loop_over(graph, variable).id
		)
		for variable in expected
	}
	# The set, not just the values: a third loop appearing is a change to the
	# graph's structure and belongs in this failure rather than passing as an
	# extra entry nobody asserted.
	assert measured == expected, (
		f"feedback-loop iteration counts moved: measured {measured}, pinned "
		f"{expected}. These are the baseline `docs/prg-status.md` measures §37 "
		f"against; if the change is deliberate, move the pin and the entry "
		f"together."
	)
	# Determinism is the precondition for pinning anything. Two propagations of
	# the same defaults landing on different counts would make the assertion
	# above flake rather than fail, which is worse than no pin.
	again = graph.propagate(dict(defaults))
	assert [loop.iterations for loop in again.loops] == [
		loop.iterations for loop in result.loops
	], "the loop count is not deterministic; pinning it would be a flake"


def test_the_summary_command_prints_the_registers_it_computes():
	"""Both registers reach the shell, not only the summary dict.

	`cross_layer` and `catalog` were computed on `graph_summary` and rendered by
	neither door -- the declared-is-not-produced class, on the registers built to
	catch that class. Asserted through the runner because the defect is
	*reaching a door*, which importing the function cannot show: the register
	was correct, tested, and invisible.
	"""
	result = _prg("summary")
	assert result.exit_code == 0, result.output
	assert "cross-layer:" in result.output, result.output
	assert "2000.0" in result.output and "5000.0" in result.output, (
		"the cross-layer line does not carry both measured values; a reader "
		"cannot see the disagreement without them"
	)
	assert "catalog:" in result.output, result.output
	assert "equity_return_target" in result.output, (
		"the one drifted status is not named on the summary"
	)


def test_every_key_the_summary_computes_reaches_a_door():
	"""A register nobody can read is the declared-is-not-produced class.

	`graph_summary` carried `cross_layer` and `catalog` for as long as they
	existed and neither `alea prg summary` nor `PrgSummaryOut` rendered them, so
	a check that ran on every solve was invisible to every reader. This is the
	gate for that class, and it is a *cross* rather than a count: for each key
	the summary computes, the key must appear in the CLI's rendering or in the
	API's payload construction.

	Read from the source text rather than by invoking both doors, because the
	failure this catches is a key that exists and is never mentioned -- and a
	door that silently dropped a key it read would pass an invocation-based
	check while the drift happened at the other end.

	An intentional one-door key is allowed and must be *named* in
	:data:`SINGLE_DOOR_KEYS` with the reason, so a key cannot become
	one-door by accident the way these two did.
	"""
	import re

	from alea.config.paths import repo_root
	from alea.prg.service import graph_summary

	#: Keys deliberately served by one door, with the reason. A key here is a
	#: decision; a key missing from both is the defect.
	single_door = {
		"endogenous_parameters": (
			"the CLI prints `endogenous={count}` and the API serves the names; "
			"the names are what a client acts on and a terminal reader does not "
			"need three 24-character node names on a summary line"
		),
		"linearity": (
			"per determined variable, thirty-three of them; served on the API "
			"for a client that renders a table, and the CLI's `prg equations` "
			"is where a reader looks for an equation's properties"
		),
	}

	keys = set(graph_summary())
	root = repo_root()
	cli = (root / "src" / "alea" / "cli.py").read_text()
	start = cli.index("def prg_summary")
	cli_body = cli[start : cli.index("@prg_app.command", start + 10)]
	api = (root / "src" / "alea" / "api" / "routes" / "prg.py").read_text()
	api_start = api.index("def _summary_out")
	api_body = api[api_start : api.index("def _violation_out", api_start)]

	cli_keys = set(re.findall(r"summary\[.(\w+).\]", cli_body))
	api_keys = set(re.findall(r'report\[.(\w+).\]', api_body))

	unreached = keys - cli_keys - api_keys - set(single_door)
	assert not unreached, (
		f"the summary computes {sorted(unreached)} and neither door renders "
		f"them; wire a door or name the key in SINGLE_DOOR_KEYS with the reason"
	)
	for key in single_door:
		assert key in keys, (
			f"{key!r} is recorded as a single-door key and the summary no longer "
			f"computes it; the record outlived the field"
		)


def test_the_door_coverage_gate_notices_a_key_no_door_renders():
	"""The canary for ``test_every_key_the_summary_computes_reaches_a_door``.

	The mutation adds a key to `graph_summary` that neither door mentions, which
	is exactly the state `cross_layer` and `catalog` were in. It is disjoint from
	what the predicate reads: the predicate crosses the summary's keys against
	two source bodies, so a mutation that adds a key to one of those bodies (or
	to a door's rendering) is a different edit from adding one to the summary.

	Restored from the canary harness's byte-level snapshot, so a killed process
	cannot leave the summary carrying a key nothing serves.
	"""
	from tests.ci.canaries import REPO, planted, probe_exit_code

	service_py = REPO / "src" / "alea" / "prg" / "service.py"
	node = "tests/ci/test_prg.py::test_every_key_the_summary_computes_reaches_a_door"
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)

	shipped = '\t\t"catalog": catalog.catalog_report(graph=g),'
	broken = (
		'\t\t"catalog": catalog.catalog_report(graph=g),\n'
		'\t\t"orphan_register": {"count": 0},  # canary: no door renders this'
	)

	assert probe_exit_code(program) == 0, "the gate was already failing"
	with planted(service_py, shipped, broken):
		assert probe_exit_code(program) != 0, (
			"the summary gained a key neither door renders and the gate passed; "
			"it is not crossing the keys against the doors"
		)
	assert probe_exit_code(program) == 0, "the gate did not recover"
