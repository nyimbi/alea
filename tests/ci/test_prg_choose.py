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


def _tomb_doc(rhs: str, determined=("old",), free=(), edge_target="old", lhs="old") -> dict:
	base = {"category": "demand_supply", "determinism": "fixed"}
	node = lambda i, **kw: {**base, "id": i, "name": i, "type": "float", "unit": "1", "range": [0.0, 10.0], **kw}  # noqa: E731
	return {
		"parameters": {
			"new": node("new", default=2.0, role="exogenous"),
			"old": node("old", role="derived", status="deprecated", deprecated_by="new"),
		},
		"equations": {
			"old_fwd": {
				"id": "old_fwd", "name": "old", "system": "demand_supply", "lhs": lhs, "rhs": rhs,
				"parameters": ["new"], "determined_variables": list(determined),
				"free_variables": list(free),
			}
		},
		"relationships": [],
	}


def test_a_tombstone_forwarded_to_its_successor_reports_the_successor():
	graph = ParameterGraph.from_mapping(_tomb_doc("new"))
	assert graph.uncoupled() == ()
	assert graph.propagate({"new": 7.0}).values["old"] == 7.0


def test_a_tombstone_read_by_another_equation_is_still_refused():
	doc = _tomb_doc("new")
	doc["parameters"]["z"] = {
		"category": "demand_supply", "determinism": "fixed", "id": "z", "name": "z",
		"type": "float", "unit": "1", "range": [0.0, 10.0], "role": "derived",
	}
	doc["equations"]["z_eq"] = {
		"id": "z_eq", "name": "z", "system": "demand_supply", "lhs": "z", "rhs": "old * 2.0",
		"parameters": ["old"], "determined_variables": ["z"],
	}
	with pytest.raises(GraphError, match="deprecated"):
		ParameterGraph.from_mapping(doc)


def test_a_tombstone_that_is_its_own_operand_is_not_a_forwarding_equation():
	with pytest.raises(GraphError, match="deprecated"):
		ParameterGraph.from_mapping(_tomb_doc("old + new"))


def test_an_inequality_on_a_tombstone_is_not_a_forwarding_equation():
	# The schema already refuses an inequality that *determines* a value, so the
	# only way an inequality reaches a tombstone is by reading it.
	doc = _tomb_doc("new", determined=())
	doc["equations"]["old_fwd"]["relation"] = "leq"
	doc["equations"]["old_fwd"]["parameters"] = ["new", "old"]
	doc["parameters"]["old"]["role"] = "free"
	with pytest.raises(GraphError, match="deprecated"):
		ParameterGraph.from_mapping(doc)


def test_a_tombstone_off_the_left_side_is_not_a_forwarding_equation():
	doc = _tomb_doc("new", lhs="2.0 * old")
	with pytest.raises(GraphError, match="deprecated"):
		ParameterGraph.from_mapping(doc)


def test_a_forwarding_equation_with_a_free_variable_is_refused():
	doc = _tomb_doc("new", free=("new",))
	with pytest.raises(GraphError, match="deprecated"):
		ParameterGraph.from_mapping(doc)
