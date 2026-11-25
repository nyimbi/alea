"""T2: the do-operator. Pin a derived name, cut its equation, recompute descendants."""

import math

import pytest

from alea.prg.graph import GraphError, ParameterGraph, load_graph


@pytest.fixture(scope="module")
def graph() -> ParameterGraph:
	return load_graph()


@pytest.fixture(scope="module")
def defaults(graph: ParameterGraph) -> dict:
	return {k: n.default for k, n in graph.nodes.items() if n.default is not None}


@pytest.fixture(scope="module")
def base(graph, defaults):
	return graph.propagate(defaults)


def _close(a: float, b: float) -> bool:
	return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def _descendants(graph, name: str) -> set[str]:
	seen: set[str] = set()
	stack = [name]
	while stack:
		for nxt in graph.affects(stack.pop()):
			if nxt not in seen:
				seen.add(nxt)
				stack.append(nxt)
	return seen


def test_pin_derived_node_holds_value_and_names_cut(graph, defaults, base):
	name = "additional_abatement_mtco2"
	assert not _close(base.values[name], 30.0)
	r = graph.intervene(defaults, {name: 30.0})
	assert r.values[name] == 30.0
	assert r.cut == ("additional_abatement_definition",)
	assert r.pinned == {name: 30.0}
	assert r.changed, "descendants must move"
	assert name not in r.changed


def test_descendants_move_and_non_descendants_do_not(graph, defaults, base):
	name = "additional_abatement_mtco2"
	r = graph.intervene(defaults, {name: 30.0})
	downstream = _descendants(graph, name)
	assert downstream, "probe needs a node with descendants"
	assert any(not _close(r.values[d], base.values[d]) for d in downstream if d in r.values and not isinstance(r.values[d], str))
	for k, v in base.values.items():
		if k in downstream or k == name or isinstance(v, str):
			continue
		assert _close(r.values[k], v), f"non-descendant {k} moved under do({name})"


def test_pure_function_does_not_mutate_graph(graph, defaults, base):
	before = dict(graph._determiner)
	graph.intervene(defaults, {"additional_abatement_mtco2": 30.0})
	assert graph._determiner == before
	again = graph.propagate(defaults)
	assert again.values == base.values


def test_range_check_applies_to_pinned_value(graph, defaults):
	low, high = graph.node("additional_abatement_mtco2").range
	with pytest.raises(Exception, match="outside its declared range"):
		graph.intervene(defaults, {"additional_abatement_mtco2": high + 1.0})


def test_unknown_name_is_refused(graph, defaults):
	with pytest.raises(GraphError, match="not parameters"):
		graph.intervene(defaults, {"no_such_parameter": 1.0})


def test_pinning_a_settable_input_cuts_nothing(graph, defaults):
	name = next(k for k in defaults if graph.is_settable(k) and isinstance(defaults[k], float))
	r = graph.intervene(defaults, {name: defaults[name]})
	assert r.cut == ()


@pytest.mark.parametrize(
	"name,equation",
	[
		("capture_price_usd_per_mwh", "capture_price_equation"),
		("vre_capacity_mw", "vre_build"),
		("vre_share", "vre_share_definition"),
		("equilibrium_demand_twh", "equilibrium_demand"),
		("regulated_tariff_usd_per_mwh", "tariff_cost_recovery"),
	],
)
def test_pin_inside_feedback_loop_breaks_it(graph, defaults, base, name, equation):
	pinned = base.values[name] * 1.1
	r = graph.intervene(defaults, {name: pinned})
	assert r.values[name] == pinned
	assert equation in r.cut
	loop_vars = [set(l.values) for l in r.loops]
	assert all(name not in lv for lv in loop_vars), "pinned variable left in a loop"
	# The surviving loop equations hold at the new point.
	for loop in graph.feedback_loops():
		if name not in loop.variables:
			continue
		for eq in loop.equations:
			if eq.determined_variables[0] == name:
				continue
			assert graph.consistency(r.values) is not None


def test_loop_pin_changes_the_other_loop_variables(graph, defaults, base):
	r = graph.intervene(defaults, {"vre_share": base.values["vre_share"] * 0.5})
	assert not _close(r.values["capture_price_usd_per_mwh"], base.values["capture_price_usd_per_mwh"])


def test_identity_pin_to_own_derived_value_changes_nothing(graph, defaults, base):
	derived = [n for n in graph.order() if not isinstance(base.values[n], str)]
	assert len(derived) >= 20
	step = max(1, len(derived) // 20)
	for n in derived[::step][:20]:
		r = graph.intervene(defaults, {n: base.values[n]})
		for k, v in base.values.items():
			if isinstance(v, str):
				assert r.values[k] == v
			else:
				assert _close(r.values[k], v), f"do({n}=own value) moved {k}"


@pytest.mark.parametrize("name", ["vre_share", "capture_price_usd_per_mwh", "equilibrium_demand_twh"])
def test_identity_pin_inside_loops(graph, defaults, base, name):
	r = graph.intervene(defaults, {name: base.values[name]})
	for k, v in base.values.items():
		if isinstance(v, str):
			continue
		assert math.isclose(r.values[k], v, rel_tol=1e-5, abs_tol=1e-6), k


def test_multi_determined_equation_cannot_be_half_cut(graph, defaults):
	multi = [e for e in graph.equations.values() if e.relation == "eq" and len(e.determined_variables) > 1]
	if not multi:
		pytest.skip("no equation in this graph fixes two variables")
	eq = multi[0]
	with pytest.raises(GraphError, match="Pin all of"):
		graph.intervene(defaults, {eq.determined_variables[0]: defaults.get(eq.determined_variables[0], 1.0)})
