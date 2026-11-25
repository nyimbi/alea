"""T1: propagate never silently drops or ignores an input.

One dimension varies per negative test so each predicate has its own canary:
the unknown-name test supplies a legal value, the differs test supplies a known
name, the endogenous test supplies a value that differs from its default.
"""

import pytest

from alea.prg.graph import GraphError, ParameterGraph, load_graph
from alea.prg.views import Role


@pytest.fixture(scope="module")
def graph() -> ParameterGraph:
	return load_graph()


@pytest.fixture(scope="module")
def defaults(graph: ParameterGraph) -> dict:
	return {k: n.default for k, n in graph.nodes.items() if n.default is not None}


def test_unknown_name_is_refused_with_a_suggestion(graph, defaults):
	with pytest.raises(GraphError) as exc:
		graph.propagate({**defaults, "additional_abatement_mtco": 1.0})
	assert "additional_abatement_mtco" in str(exc.value)
	assert "additional_abatement_mtco2" in str(exc.value), "no closest-name suggestion"


def test_unknown_name_with_no_close_match_is_still_refused(graph, defaults):
	with pytest.raises(GraphError, match="no_such_param_xyz"):
		graph.propagate({**defaults, "no_such_param_xyz": 1.0})


def test_derived_value_that_differs_is_refused_naming_all_four_facts(graph, defaults):
	derived = graph.propagate(defaults).values["additional_abatement_mtco2"]
	with pytest.raises(GraphError) as exc:
		graph.propagate({**defaults, "additional_abatement_mtco2": 30.0})
	msg = str(exc.value)
	assert "additional_abatement_mtco2" in msg
	assert "30" in msg
	assert f"{derived:g}" in msg
	assert "additional_abatement_definition" in msg


def test_derived_value_that_equals_the_result_is_accepted(graph, defaults):
	full = graph.propagate(defaults).values
	again = graph.propagate({**defaults, **full})
	assert again.values["additional_abatement_mtco2"] == full["additional_abatement_mtco2"]


def test_every_derived_value_fed_back_is_accepted(graph, defaults):
	"""The convenience paths pass the whole previous result back in."""
	full = graph.propagate(defaults).values
	graph.propagate({**defaults, **full})


def test_every_offender_is_listed_not_just_the_first(graph, defaults):
	with pytest.raises(GraphError) as exc:
		graph.propagate(
			{**defaults, "additional_abatement_mtco2": 30.0, "no_such_param_xyz": 1.0}
		)
	msg = str(exc.value)
	assert "additional_abatement_mtco2" in msg and "no_such_param_xyz" in msg


def test_door_refuses_an_endogenous_knob_but_the_graph_takes_a_solved_fleet(graph, defaults):
	"""The post-solve audit supplies the optimiser's fleet as data; a user may not set it."""
	from alea.prg.service import propagate_change

	name = next(k for k, n in graph.nodes.items() if n.role is Role.ENDOGENOUS and isinstance(n.default, float))
	with pytest.raises(ValueError, match="optimisation"):
		propagate_change(defaults, {name: defaults[name] + 1.0}, graph)
	graph.propagate({**defaults, name: defaults[name] + 1.0})


def test_endogenous_default_is_accepted(graph, defaults):
	graph.propagate(defaults)


def test_incremental_refuses_the_same_things(graph, defaults):
	base = graph.propagate(defaults)
	with pytest.raises(GraphError, match="no_such_param_xyz"):
		graph.propagate_incremental({"no_such_param_xyz": 1.0}, base, set())
	with pytest.raises(GraphError, match="additional_abatement_definition"):
		graph.propagate_incremental({"additional_abatement_mtco2": 30.0}, base, set())


def test_intervene_is_not_refused_for_what_it_pins(graph, defaults):
	r = graph.intervene(defaults, {"additional_abatement_mtco2": 30.0})
	assert r.values["additional_abatement_mtco2"] == 30.0


def test_config_all_is_a_literal_that_matches_the_lazy_table():
	import alea.config as config

	assert sorted(config.__all__) == sorted(config._LAZY)
	assert config.__all__ == sorted(config.__all__)
