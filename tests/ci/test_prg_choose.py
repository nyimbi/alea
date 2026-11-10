"""`choose(selector, level=expr, ...)`: a categorical picks a branch."""

from __future__ import annotations

import pytest

from alea.prg.dsl import Choose, DslError, choices_in, parse
from alea.prg.graph import GraphError, ParameterGraph


def test_a_level_picks_its_branch_and_only_its_branch():
	e = parse("choose(mode, a=2.0 * x, b=5.0) * y")
	assert e.eval({"mode": "a", "x": 3.0, "y": 2.0}) == 12.0
	assert e.eval({"mode": "b", "x": 3.0, "y": 2.0}) == 10.0


def test_selector_is_a_symbol_and_levels_are_not():
	e = parse("choose(mode, a=x, b=y)")
	assert e.symbols == {"mode", "x", "y"}


def test_source_round_trips():
	e = parse("choose(mode, a=2.0 * x, b=5.0)")
	assert parse(e.source()) == e


def test_an_unlisted_level_raises_naming_the_levels():
	with pytest.raises(DslError, match="no branch for 'c'"):
		parse("choose(mode, a=1.0, b=2.0)").eval({"mode": "c"})


def test_a_numeric_selector_is_refused():
	with pytest.raises(DslError, match="needs a level name"):
		parse("choose(mode, a=1.0, b=2.0)").eval({"mode": 1.0})


def test_a_repeated_level_and_a_bare_call_are_refused():
	with pytest.raises(DslError):
		Choose("m", (("a", parse("x")), ("a", parse("y"))))
	with pytest.raises(DslError):
		parse("choose(mode)")
	with pytest.raises(DslError):
		parse("choose(2.0, a=1.0)")


def test_derivative_is_the_live_branchs_and_the_selector_has_none():
	e = parse("choose(mode, a=2.0 * x, b=5.0 * x)")
	assert e.diff("x").eval({"mode": "a", "x": 1.0}) == 2.0
	assert e.diff("x").eval({"mode": "b", "x": 1.0}) == 5.0
	with pytest.raises(DslError):
		e.diff("mode")


def test_choices_in_finds_a_nested_form():
	e = parse("x * (1.0 + choose(m, a=1.0, b=choose(n, c=2.0, d=3.0)))")
	assert [c.selector for c in choices_in(e)] == ["m", "n"]


def _doc(rhs: str, categories=("a", "b")) -> dict:
	base = {"category": "demand_supply", "determinism": "fixed"}
	return {
		"parameters": {
			"mode": {
				**base, "id": "mode", "name": "mode", "type": "categorical",
				"categories": list(categories), "default": categories[0],
				"role": "exogenous",
			},
			"x": {
				**base, "id": "x", "name": "x", "type": "float", "unit": "1",
				"default": 1.0, "range": [0.0, 10.0], "role": "exogenous",
			},
			"out": {
				**base, "id": "out", "name": "out", "type": "float", "unit": "1",
				"range": [0.0, 100.0], "role": "derived",
			},
		},
		"equations": {
			"out_eq": {
				"id": "out_eq", "name": "out", "system": "demand_supply",
				"lhs": "out", "rhs": rhs, "parameters": ["mode", "x"],
				"determined_variables": ["out"],
			}
		},
		"relationships": [],
	}


def test_the_graph_refuses_a_selector_that_is_not_categorical():
	doc = _doc("choose(x, a=1.0, b=2.0)")
	doc["equations"]["out_eq"]["parameters"] = ["x"]
	with pytest.raises(GraphError, match="not a categorical"):
		ParameterGraph.from_mapping(doc)


def test_the_graph_refuses_a_missing_or_invented_level():
	for rhs in ("choose(mode, a=1.0) * x", "choose(mode, a=1.0, b=2.0, c=3.0) * x"):
		with pytest.raises(GraphError, match="covers"):
			ParameterGraph.from_mapping(_doc(rhs))


def test_a_covering_choose_propagates_and_a_level_change_moves_the_result():
	graph = ParameterGraph.from_mapping(_doc("choose(mode, a=2.0, b=5.0) * x"))
	assert graph.propagate({"mode": "a", "x": 3.0}).values["out"] == 6.0
	moved = graph.propagate({"mode": "b", "x": 3.0})
	assert moved.values["out"] == 15.0
	assert "out" in moved.changed
