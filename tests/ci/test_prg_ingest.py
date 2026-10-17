# SPDX-License-Identifier: MIT
"""The fragment loader, and the edge rule the specification stated but nobody ran.

WHAT THESE TESTS ARE FOR. ``docs/param_ingest.md`` specifies a landing site for
generated parameter batches and eight gates over what lands there. Two of the
eight had no implementation when the batches arrived, and one of those -- gate 6,
"both endpoints of every edge appear in the cited equation" -- was true of all 88
shipped edges and false of 26 of the 145 batch edges. So the tests come in two
groups:

1. **Does the loader do what the specification says?** It merges fragments onto
   the shipped document, refuses a duplicate id whose bodies differ, refuses one
   whose bodies agree, and reports every count rather than logging them. Each of
   those is a branch that a caller acts on, so each is pinned here.
2. **Does the graph refuse an edge the cited equation does not support?** This is
   the rule that was stated and unenforced. It is canaried against a graph that
   must be refused, because a gate that has never been watched failing is not a
   gate -- the whole reason gate 6 went missing is that nothing ever pointed it
   at an edge that should fail.

WHY THE FIXTURES ARE BUILT IN-TEST RATHER THAN LOADED FROM ``config/``. A test
that reads the shipped fragments passes when the fragments are correct and also
when the loader silently drops every one of them, because the shipped graph alone
is a valid graph. Every assertion here is against a document this file builds, so
a loader that returns the shipped graph unchanged fails all of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alea.prg.graph import (
	GraphError,
	IngestReport,
	ParameterGraph,
	_merge_fragments,
	default_ingest_dir,
	load_graph,
	load_ingested,
)
from alea.prg.service import check_scenario

# --------------------------------------------------------------------------
# A minimal shipped document and the fragments that correct it.
#
# Two nodes and one equation, which is the smallest document on which gate 6 can
# fail: an edge needs two endpoints and an equation to cite.
# --------------------------------------------------------------------------

SHIPPED_NODES: dict[str, dict[str, object]] = {
	"alpha": {
		"name": "Alpha",
		"category": "Test",
		"type": "float",
		"unit": "1",
		"range": [0.0, 1.0],
		"role": "derived",
		"determinism": "fixed",
		"source": "docs/params.md",
	},
	"beta": {
		"name": "Beta",
		"category": "Test",
		"type": "float",
		"unit": "1",
		"range": [0.0, 1.0],
		"default": 0.5,
		"role": "free",
		"determinism": "fixed",
		"source": "docs/params.md",
	},
	"gamma": {
		"name": "Gamma",
		"category": "Test",
		"type": "float",
		"unit": "1",
		"range": [0.0, 1.0],
		"default": 0.5,
		"role": "free",
		"determinism": "fixed",
		"source": "docs/params.md",
	},
}

SHIPPED: dict[str, object] = {
	"parameters": {
		"alpha": {
			"name": "Alpha",
			"category": "Test",
			"type": "float",
			"unit": "1",
			"range": [0.0, 1.0],
			# `alpha_from_beta` determines this, so it is `derived` and carries
			# no default. A fixture that got this wrong would fail for a reason
			# that has nothing to do with the rule under test.
			"role": "derived",
			"determinism": "fixed",
			"source": "docs/params.md",
		},
		"beta": {
			"name": "Beta",
			"category": "Test",
			"type": "float",
			"unit": "1",
			"range": [0.0, 1.0],
			"default": 0.5,
			"role": "free",
			"determinism": "fixed",
			"source": "docs/params.md",
		},
		# Declared, and in no equation. Gate 6 is about an edge to a parameter the
		# *equation* does not hold; an edge to a parameter the *document* does not
		# declare is a different rule with a different error, so a canary that
		# used an undeclared name would pass against a graph with no gate 6 at all.
		"gamma": {
			"name": "Gamma",
			"category": "Test",
			"type": "float",
			"unit": "1",
			"range": [0.0, 1.0],
			"default": 0.5,
			"role": "free",
			"determinism": "fixed",
			"source": "docs/params.md",
		},
	},
	"equations": {
		"alpha_from_beta": {
			"name": "Alpha from beta",
			"system": "reliability",
			"lhs": "alpha",
			"rhs": "beta",
			"relation": "eq",
			"parameters": ["beta"],
			"free_variables": ["beta"],
			"determined_variables": ["alpha"],
			"unit_check": False,
		}
	},
	"relationships": [
		{
			"source": "beta",
			"target": "alpha",
			"equation_id": "alpha_from_beta",
			"relationship": "functional",
			"strength": "hard",
		}
	],
	"cross_validation": [],
}


def _node(name: str, bounds: list[float]) -> dict[str, object]:
	return {
		"name": name,
		"category": "Test",
		"type": "float",
		"unit": "1",
		"range": bounds,
		"default": bounds[0],
		"role": "free",
		"determinism": "fixed",
		"source": "docs/param_batch0.md",
	}


def _write(directory: Path, name: str, document: object) -> Path:
	"""Write one fragment and return its path."""
	path = directory / name
	path.write_text(yaml.safe_dump(document, sort_keys=False))
	return path


def _merged(paths: list[Path]) -> tuple[ParameterGraph, IngestReport]:
	"""Merge fragments onto the in-test shipped document."""
	document, report = _merge_fragments(SHIPPED, paths)
	return ParameterGraph.from_mapping(document), report


# --------------------------------------------------------------------------
# Gate 6 -- the rule that was stated and never run.
# --------------------------------------------------------------------------


def test_an_edge_whose_endpoint_the_equation_does_not_hold_is_refused():
	"""The canary. This is the case 26 of the 145 batch edges were.

	`beta -> alpha` citing `alpha_from_beta` is sound: the equation's arithmetic
	names both. `alpha -> alpha` is not, and neither is any pair where one end
	sits outside the equation. Before this rule the graph accepted all of them,
	so a reader following an edge arrived at an equation that had never heard of
	one of the two parameters the edge was about.
	"""
	document = yaml.safe_load(yaml.safe_dump(SHIPPED))
	document["relationships"] = [
		{
			"source": "gamma",
			"target": "alpha",
			"equation_id": "alpha_from_beta",
			"relationship": "functional",
			"strength": "hard",
		}
	]
	with pytest.raises(GraphError) as exc:
		ParameterGraph.from_mapping(document)
	assert "gamma" in str(exc.value)
	assert "alpha_from_beta" in str(exc.value)


def test_an_edge_the_equation_supports_is_accepted():
	"""The control. Without it the canary above passes against a graph that
	refuses every edge, which is not the rule the specification states."""
	ParameterGraph.from_mapping(yaml.safe_load(yaml.safe_dump(SHIPPED)))


def test_both_endpoints_are_checked_not_only_the_source():
	"""A gate that reads one endpoint is the "one of two spellings" bug.

	An edge whose *target* is outside the equation is the same defect as one
	whose source is, and a check written against `edge.source` alone reports
	clean on half of them.
	"""
	document = yaml.safe_load(yaml.safe_dump(SHIPPED))
	document["relationships"] = [
		{
			"source": "beta",
			"target": "gamma",
			"equation_id": "alpha_from_beta",
			"relationship": "functional",
			"strength": "hard",
		}
	]
	with pytest.raises(GraphError):
		ParameterGraph.from_mapping(document)


# --------------------------------------------------------------------------
# The merge.
# --------------------------------------------------------------------------


def test_a_fragment_corrects_a_shipped_node(tmp_path: Path):
	"""Register 1 is "only nodes being added or corrected".

	The shipped 691 placeholder nodes exist to be corrected, so a fragment
	overwriting one is the register doing its job. An earlier version of this
	loader refused exactly that, which made every correction impossible -- the
	control existed and was never applied to the case it was written for.
	"""
	path = _write(
		tmp_path,
		"a.yaml",
		{
			"parameters": {
				"alpha": {**SHIPPED_NODES["alpha"], "range": [0.0, 0.9]},
			}
		},
	)
	graph, report = _merged([path])
	assert graph.nodes["alpha"].range == (0.0, 0.9)
	assert ("parameters", "alpha", "a.yaml") in report.corrected


def test_a_fragment_adds_a_node(tmp_path: Path):
	path = _write(
		tmp_path,
		"a.yaml",
		{
			"parameters": {
				"delta": {
					"name": "Delta",
					"category": "Test",
					"type": "float",
					"unit": "1",
					"range": [0.0, 1.0],
					"default": 0.5,
					"role": "free",
					"determinism": "fixed",
					"source": "docs/param_batch0.md",
				}
			}
		},
	)
	graph, report = _merged([path])
	assert "delta" in graph.nodes
	assert report.per_file["a.yaml"]["parameters"] == 1
	assert not report.corrected


def test_two_fragments_declaring_one_id_differently_are_refused(tmp_path: Path):
	"""Two agents disagreeing about a parameter, with no fact of the matter.

	Refused rather than last-wins: the file order is alphabetical, so last-wins
	resolves the disagreement by filename.
	"""
	a = _write(tmp_path, "a.yaml", {"parameters": {"gamma": _node("Gamma", [0.0, 1.0])}})
	b = _write(tmp_path, "b.yaml", {"parameters": {"gamma": _node("Gamma", [0.0, 2.0])}})
	graph, report = _merged([a, b])
	# Reported rather than raised: `load_ingested` returns the report beside the
	# graph so a caller has to read it, and `__bool__` is the one-line check.
	assert report.refused == (("gamma", "a.yaml", "b.yaml"),)
	assert not report
	# And the first body is what landed -- the duplicate did not overwrite it.
	assert graph.nodes["gamma"].range == (0.0, 1.0)


def test_two_fragments_declaring_one_id_identically_are_merged_silently(tmp_path: Path):
	"""Two batches that agree are not a conflict, and refusing them would make
	the loader unusable on a set generated by more than one pass."""
	a = _write(tmp_path, "a.yaml", {"parameters": {"gamma": _node("Gamma", [0.0, 1.0])}})
	b = _write(tmp_path, "b.yaml", {"parameters": {"gamma": _node("Gamma", [0.0, 1.0])}})
	graph, report = _merged([a, b])
	assert "gamma" in graph.nodes
	assert report.redundant == (("gamma", "b.yaml"),)
	assert not report.refused


def test_a_register_the_loader_does_not_read_is_reported_not_ignored(tmp_path: Path):
	"""A key nobody reads is a fragment claiming something the graph never
	receives. Silently dropping it is how a batch's whole section goes missing
	with the load reporting success."""
	path = _write(tmp_path, "a.yaml", {"provenance": {"agent": "x"}})
	_, report = _merged([path])
	assert ("a.yaml", "provenance") in report.unknown


def test_a_missing_directory_is_the_shipped_graph_not_an_error(tmp_path: Path):
	"""The state of a tree with no fragments generated yet."""
	_graph, report = load_ingested(tmp_path / "absent")
	assert not report.per_file


def test_the_report_is_false_only_when_nothing_was_lost():
	"""`__bool__` is the caller's one-line "is this load clean".

	A report that is always true is a report nobody reads.
	"""
	assert bool(IngestReport())
	assert not IngestReport(unknown=(("a.yaml", "provenance"),))
	assert not IngestReport(refused=(("gamma", "a.yaml", "b.yaml"),))


# --------------------------------------------------------------------------
# A bound equation -- a constant side, which `parse` used to refuse.
# --------------------------------------------------------------------------


def test_a_bound_equation_with_a_constant_side_loads():
	"""`sum(shares) <= 1.0` is a relation, and its ceiling is the point.

	The loader read each side's symbols with `parse`, which refuses any
	expression naming no parameter -- "a constant expression relates nothing
	and would pass every consistency check vacuously". That argument is about a
	*relation*, and it was being applied to a *side*, so every bound equation
	was refused at load: the right-hand side of a ceiling is a constant, by
	definition. The residual the solver builds, `(lhs) - (rhs)`, parsed and
	evaluated correctly the whole time, so the equation was expressible to
	every consumer except the checks guarding it.

	Asserted on the *outcome* rather than on the error text: the equation
	loads, it couples both operands, and the inequality evaluates to the right
	answer on either side of the bound.
	"""
	document = {
		"parameters": {
			"delta": _node("Delta", [0.0, 1.0]),
			"epsilon": _node("Epsilon", [0.0, 1.0]),
		},
		"equations": {
			"delta_plus_epsilon_bound": {
				"name": "Delta plus epsilon at most one",
				"system": "reliability",
				"lhs": "delta + epsilon",
				"rhs": "1.0",
				"relation": "leq",
				"parameters": ["delta", "epsilon"],
				"unit_check": False,
			}
		},
		"relationships": [],
		"cross_validation": [],
	}
	graph = ParameterGraph.from_mapping(document)
	equation = graph.equations["delta_plus_epsilon_bound"]

	# Both operands are coupled by the bound, so the register shrinks.
	assert "delta" not in graph.uncoupled()
	assert "epsilon" not in graph.uncoupled()

	# And the inequality means what it says, on both sides of the ceiling.
	assert graph._inequality_holds(equation, {"delta": 0.4, "epsilon": 0.5})
	assert not graph._inequality_holds(equation, {"delta": 0.6, "epsilon": 0.5})


def test_an_equation_that_is_constant_on_both_sides_is_still_refused():
	"""The vacuity guard moved, it did not go away.

	`parse`'s refusal protected against an equation that relates nothing. Once
	a constant *side* is legal, that protection has to be stated on the
	*combined* arithmetic -- otherwise `1.0 <= 2.0` would load as a relation
	that passes every consistency check and couples nothing.

	Canaried against the exact input the guard exists for, and the guard is
	asserted to *name* the defect: an assertion on `GraphError` alone would
	pass against the system-name check further down the same loader.
	"""
	document = {
		"parameters": {"delta": _node("Delta", [0.0, 1.0])},
		"equations": {
			"vacuous": {
				"name": "One at most two",
				"system": "reliability",
				"lhs": "1.0",
				"rhs": "2.0",
				"relation": "leq",
				"parameters": ["delta"],
				"unit_check": False,
			}
		},
		"relationships": [],
		"cross_validation": [],
	}
	with pytest.raises(GraphError, match="constant on both sides"):
		ParameterGraph.from_mapping(document)


def test_an_equation_that_relates_a_side_to_itself_is_refused():
	"""The second way a relation can relate nothing.

	The constant check above does not catch `x <= x`: both sides name a
	parameter, so the equation passes the vacuity guard, couples its node, and
	then holds at every value that node can take. The residual the solver builds
	is `(lhs) - (rhs)` -- identically zero -- so the constraint is dropped as
	trivially satisfied while the node still reads as reached in every coverage
	count.

	This is not hypothetical: `param_batch5.yaml` shipped
	`emissions_peak_constraint` as exactly `emissions_mtco2_per_year <=
	emissions_mtco2_per_year`, because its own repair rule had pruned the second
	operand rather than fixing the arithmetic.

	The guard is asserted to *name* the defect, and the same equation is asserted
	to load once the operand is corrected -- otherwise the test would pass
	against a guard that refuses every inequality.
	"""
	def document(rhs: str) -> dict:
		return {
			"parameters": {
				"delta": _node("Delta", [0.0, 1.0]),
				"epsilon": _node("Epsilon", [0.0, 1.0]),
			},
			"equations": {
				"peak": {
					"name": "Delta at most epsilon",
					"system": "reliability",
					"lhs": "delta",
					"rhs": rhs,
					"relation": "leq",
					"parameters": ["delta", "epsilon"],
					"unit_check": False,
				}
			},
			"relationships": [],
			"cross_validation": [],
		}

	with pytest.raises(GraphError, match="relates 'delta' to itself"):
		ParameterGraph.from_mapping(document("delta"))

	# The same equation with a distinct operand is not refused, so the guard is
	# scoped to the tautology rather than to the relation's shape.
	assert ParameterGraph.from_mapping(document("epsilon")).equations


def test_the_shipped_emissions_peak_equation_is_gone_rather_than_vacuous():
	"""A tautology standing in for a claim the graph cannot express.

	`emissions_peak_constraint` read `x <= x`. Its intended meaning
	(`docs/param_eqn_formula1.md:173`) is `CO2(y_peak) >= CO2(y) for all y` --
	a property of a trajectory indexed by year -- and the graph carries one
	annual scalar, so the claim has no encoding here. Re-pointing it at
	`emissions_peak_year` would compare MtCO2/year against years under the
	equation's own `unit_check`.

	The equation is removed, and this test pins that: it must not come back as a
	tautology, and `emissions_peak_year` must still be a *node* (the batch's own
	repair rule pruned it from the equation, and a later edit that pruned the
	node instead would look identical in the equation count).
	"""
	graph, _ = load_ingested(default_ingest_dir())
	assert "emissions_peak_constraint" not in graph.equations
	assert "emissions_peak_year" in graph.nodes
	assert graph.nodes["emissions_peak_year"].unit == "years"


def test_the_tautology_guard_refuses_the_shipped_batch_that_carried_one():
	"""Canary: plant the defect the guard exists for, in the file that had it.

	The in-test canary above builds a two-node fixture, which proves the guard
	fires on the *shape* but not that it would have caught the shipped instance.
	The two differ: `emissions_peak_constraint` carried `parameters:
	[emissions_mtco2_per_year]` and `system: carbon_trajectory`, so a guard that
	only compared `lhs` and `rhs` would pass it -- and the guard here does
	compare exactly that, but nothing yet proves it against the real fragment.

	The mutation is restored from the harness's in-memory bytes, never from
	`git checkout`, because the removal of this equation is uncommitted work in
	the same file.
	"""
	from tests.ci.canaries import REPO, planted, probe_exit_code

	fragment = REPO / "config" / "prg_ingest" / "param_batch5.yaml"
	node = (
		"tests/ci/test_prg_ingest.py"
		"::test_the_shipped_fragments_load_and_report_a_clean_merge"
	)
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)

	# Planted where the equation used to sit, immediately before its successor.
	shipped = "    priority: P1\n  reserve_margin_with_firm_vre:\n"
	broken = (
		"    priority: P1\n"
		"  emissions_peak_constraint:\n"
		"    name: Emissions peak constraint\n"
		"    system: carbon_trajectory\n"
		"    lhs: emissions_mtco2_per_year\n"
		"    rhs: emissions_mtco2_per_year\n"
		"    relation: leq\n"
		"    parameters:\n"
		"    - emissions_mtco2_per_year\n"
		"    tolerance: 1.0e-06\n"
		"    unit_check: true\n"
		"    solution_method: numeric\n"
		"    linearity: linear\n"
		"    priority: P2\n"
		"  reserve_margin_with_firm_vre:\n"
	)

	assert probe_exit_code(program) == 0, "the gate was already failing"
	with planted(fragment, shipped, broken):
		assert probe_exit_code(program) != 0, (
			"the shipped tautology loaded and the merge test passed; the guard "
			"does not reach the fragment the defect actually lived in"
		)
	assert probe_exit_code(program) == 0, "the gate did not recover"


# --------------------------------------------------------------------------
# The shipped fragments, which are the reason the loader exists.
# --------------------------------------------------------------------------


def test_the_shipped_fragments_load_and_report_a_clean_merge():
	"""The eight batches the originating agent returned, merged.

	This is the integration test the whole file is for. It asserts the merge is
	*clean* -- no refusals, nothing unknown -- and separately that it is not
	vacuous: the ingested graph is strictly larger than the shipped one. A
	loader that dropped every fragment would satisfy the first and fail the
	second, which is the failure mode that made the first assertion worthless
	on its own.
	"""
	directory = default_ingest_dir()
	if not directory.is_dir():  # pragma: no cover - a tree without fragments
		pytest.skip(f"{directory} does not exist")

	graph, report = load_ingested(directory)
	shipped = load_graph()
	assert report.refused == (), report.refused
	assert report.unknown == (), report.unknown
	assert len(graph.nodes) > len(shipped.nodes)
	assert len(graph.equations) > len(shipped.equations)
	assert len(graph.edges) > len(shipped.edges)


def test_the_ingested_graph_is_one_default_short_of_a_runnable_scenario():
	"""The batches re-typed 26 nodes to `bool`/`categorical` and gave no default.

	`docs/param_ingest.md:78` says a `default` is required for a free node, and
	the loader does not enforce it, so the omission loaded. The shipped graph had
	declared all 26 as `float` on the `(0, 1e6)` placeholder with `default:
	500000.0`, and re-typing them to `bool` dropped that placeholder -- which
	made `check_scenario` over any defaults-built value set raise `the parameter
	set is missing [...]`.

	This test pins the state after the repair, which is *not* a runnable graph:
	23 booleans now carry the value `docs/what-if.md` documents, and three nodes
	remain, each for its own reason. Asserting the three by name is the point --
	an assertion that the set is empty would fail today, and one that skips the
	check would let a *fourth* node join the list unremarked. The three:

	* `market_model`, `market_structure` -- categoricals. The model refuses a
	  scalar `default` on one (`_NON_SCALAR_TYPES`), and `propagate` coerces
	  every value with `float()`, so a categorical cannot carry a value through
	  this graph at all. `docs/what-if.md` documents `Single Buyer` for both.
	* `smart_metering_rollout` -- the three documents disagree about its type:
	  `param_batch1.md` a share with `default: 0.3`, `param_batch7.md` a bool,
	  `docs/param_eqn_formula1.md` a year-indexed count. No default can be
	  written until that is settled.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}

	absent = sorted(
		k
		for k, n in graph.nodes.items()
		if n.default is None and n.role.value != "derived"
	)
	assert absent == ["market_model", "market_structure", "smart_metering_rollout"], absent

	# The three are exactly what stops a defaults-built scenario, so the raise
	# names them and nothing else -- a fourth would be a new omission, not this
	# defect, and would change the message.
	with pytest.raises(GraphError) as caught:
		check_scenario(values, graph)
	assert "'market_model', 'market_structure', 'smart_metering_rollout'" in str(
		caught.value
	)

	# And every free *scalar* node is now supplied, so removing the three
	# non-scalars leaves a value set the graph can propagate.
	scalars = {
		k: v
		for k, v in values.items()
		if graph.nodes[k].type.value in {"float", "int", "bool"}
	}
	assert len(scalars) == len(values)




def test_the_ingested_graph_is_consistent_at_its_own_defaults():
	"""The whole batch set, evaluated at the defaults it declares.

	This is the assertion the other integration tests stop short of: the merge
	can be clean, the graph strictly larger, and the graph still *unevaluable*.
	It was -- `mtbf_from_failure_rate_definition` computed MTBF from a variable
	`availability_definition` computes from MTBF, so the derived subgraph was
	cyclic and every `check_scenario` raised `CycleError ... form a cycle and
	have no evaluation order`, at any value set. A clean merge was silent about
	it because a cycle is a property of the edges, not of the fragments.

	The value set supplies the three nodes no fragment gives a default (see the
	test above); everything else comes from the graph.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	values.update({"market_model": 1.0, "market_structure": 1.0, "smart_metering_rollout": 0.0})

	# Must not raise. A cycle raises here, and so does a missing node.
	result = graph.propagate(values)
	assert len(result.values) == len(graph.nodes)

	report = check_scenario(values, graph)
	assert report.violations == (), report.violations
	assert not report.excursions, report.excursions  # a mapping, empty when clean
	assert report.cross_validation.violations == (), report.cross_validation.violations


def test_a_derived_node_is_not_declared_out_of_range_at_its_own_default():
	"""Three derived nodes were, and each for a different reason.

	Pinned separately from the consistency test because the mechanism differs
	and a future batch could reintroduce any one of them without a cycle:

	* `fuel_diversity_index` -- the HHI divided by `total_capacity_mw` instead
	  of the sum of the seven fuels it indexes. Two parameters free to disagree;
	  at the shipped defaults they differ by 6.3x, giving 1 - 8.39 = -7.39.
	* `gearing_ratio` -- the range was `debt_fraction`'s [0, 0.95], but the node
	  is `debt_fraction / (1 - debt_fraction)`, whose image over that range is
	  [0, 19]. The default debt fraction of 0.7 gives 2.3333, which the declared
	  range refused.
	* `lole_hours_per_year` -- `exp(-10 * m)` at the default m = 0.15 gives a
	  LOLP of 0.2231, so 1954.6 h/yr against a declared ceiling of 500 and 81x
	  the 24 h/yr the batch's own `lole_exceeds_days` rule enforces.

	Each is asserted at the value the graph derives, so the test fails on the
	*arithmetic* and not only on the range: a range widened to hide a wrong
	value would still be caught by the expected magnitudes.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	values.update({"market_model": 1.0, "market_structure": 1.0, "smart_metering_rollout": 0.0})
	derived = graph.propagate(values).values

	# The HHI is over the seven named fuels, so their shares sum to 1 by
	# construction and the index is in [0, 1] for every value set.
	fuels = [
		"coal_capacity", "gas_capacity", "oil_capacity", "nuclear_capacity",
		"hydro_capacity", "solar_pv_capacity", "wind_onshore_capacity",
	]
	shares = [derived[f] for f in fuels]
	total = sum(shares)
	hhi = sum(s * s for s in shares) / (total * total)
	assert 0.0 <= hhi <= 1.0
	assert derived["fuel_diversity_index"] == pytest.approx(1.0 - hhi)
	assert 0.0 <= derived["fuel_diversity_index"] <= 1.0

	# The gearing ratio is the image of the debt fraction, so it is checked
	# against the fraction the graph actually carries rather than a literal.
	debt_fraction = derived["debt_fraction"]
	assert derived["gearing_ratio"] == pytest.approx(debt_fraction / (1.0 - debt_fraction))
	# Asserted against the node's own declared range, not against a literal:
	# the defect was the range, so a predicate that only read the value would
	# pass with the range restored to the debt fraction's bound. The range must
	# contain the image of the driver's range, of which this value is one point.
	node = graph.nodes["gearing_ratio"]
	assert node.range is not None
	assert node.range[0] <= derived["gearing_ratio"] <= node.range[1], (
		f"gearing_ratio {derived['gearing_ratio']} is outside its declared "
		f"range {node.range}"
	)
	driver = graph.nodes["debt_fraction"].range
	assert driver is not None
	assert node.range[1] >= driver[1] / (1.0 - driver[1]), (
		"the declared range does not cover the image of debt_fraction's range"
	)

	# The LOLP is pinned to the graph's own reliability rule: a margin at the
	# required minimum gives LOLE = 24 h/yr, one day per year.
	assert derived["lole_hours_per_year"] == pytest.approx(24.0)
	assert derived["lolp"] == pytest.approx(24.0 / 8760.0)


def test_the_gearing_rule_threshold_is_a_multiple_not_a_fraction():
	"""The rule's message said "80%" and its condition tested the fraction.

	`gearing_ratio` is a multiple of equity, so 80% debt is a multiple of 4.0,
	not 0.8. With the old threshold the rule fired at a debt fraction of 0.444
	-- an ordinary capital structure -- while claiming to flag 80%. This canaries
	both sides of the corrected threshold: it must fire above 4.0 and stay silent
	at 3.9, so a threshold that drifted back to a fraction reading fails here.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	base = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	base.update({"market_model": 1.0, "market_structure": 1.0, "smart_metering_rollout": 0.0})
	base["discount_rate"] = 0.25  # above the rule's other threshold

	def fires(gearing: float) -> bool:
		report = graph.cross_validate({**base, "gearing_ratio": gearing})
		return any(f.rule.id == "discount_rate_gearing_interaction" for f in report.violations)

	assert fires(4.1), "the rule must fire above a debt fraction of 80%"
	assert not fires(3.9), "3.9 is a debt fraction of 0.796 -- below the threshold"
	assert not fires(2.3333), "the default gearing is an ordinary structure"


def test_the_consistency_gate_refuses_the_three_defects_it_pins():
	"""Canary each repair by planting the defect back into its own fragment.

	Three mutations, each disjoint from what its predicate reads, so a pass is
	evidence the predicate reached the fragment and not that the edit missed:

	* the fuel-diversity denominator -- restored to `total_capacity_mw`, which
	  is a *different parameter*, not a different spelling of the same sum;
	* the gearing range -- restored to `[0, 0.95]`, a bound the derived value
	  2.3333 exceeds;
	* the LOLP decay -- restored to the literal 10, whose value at m = 0.15 is
	  0.2231 rather than the calibrated 24/8760.

	Each is planted one at a time and the gate re-run, so a mutation that fails
	to apply cannot pass for a predicate that works. The file is restored from
	the harness's in-memory bytes under a lock.
	"""
	from tests.ci.canaries import REPO, planted, probe_exit_code

	node = "tests/ci/test_prg_ingest.py::test_a_derived_node_is_not_declared_out_of_range_at_its_own_default"
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)
	assert probe_exit_code(program) == 0, "the gate was already failing"

	fragment6 = REPO / "config" / "prg_ingest" / "param_batch6.yaml"
	fragment0 = REPO / "config" / "prg_ingest" / "param_batch0.yaml"

	# The denominator, restored to the parameter it used to be.
	denom_ok = "      ** 2)\n    relation: eq\n    parameters:\n    - coal_capacity"
	denom_bad = "      ** 2) / (total_capacity_mw ** 2)\n    relation: eq\n    parameters:\n    - coal_capacity"
	with planted(fragment6, denom_ok, denom_bad):
		assert probe_exit_code(program) != 0, "the fuel-diversity denominator is unguarded"

	# The gearing range, restored to the debt fraction's bound.
	range_ok = "    - 0.0\n    - 19.0\n    role: derived"
	range_bad = "    - 0.0\n    - 0.95\n    role: derived"
	with planted(fragment0, range_ok, range_bad):
		assert probe_exit_code(program) != 0, "the gearing range is unguarded"

	# The decay constant, restored to the uncalibrated literal.
	decay_ok = "    rhs: (24 / 8760) ** (reserve_margin_min / 0.15)"
	decay_bad = "    rhs: exp((0 - 10) * reserve_margin_min)"
	with planted(fragment6, decay_ok, decay_bad):
		assert probe_exit_code(program) != 0, "the LOLP calibration is unguarded"

	assert probe_exit_code(program) == 0, "the gate did not recover"
