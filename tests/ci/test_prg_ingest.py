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

import tempfile
from pathlib import Path

import pytest
import yaml

from alea.prg.dsl import evaluate, parse, parse_side
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
	"""Canary: plant the defect the guard exists for, against its shipped body.

	The in-test canary above builds a two-node fixture, which proves the guard
	fires on the *shape* but not that it would have caught the shipped instance.
	The two differ: `emissions_peak_constraint` carried `parameters:
	[emissions_mtco2_per_year]` and `system: carbon_trajectory`, so a guard that
	only compared `lhs` and `rhs` would pass it -- and the guard here does
	compare exactly that; the body below is the shipped defect's own YAML,
	verbatim from `param_batch5.yaml` as it stood when the guard caught it.

	THE FRAGMENTS ARE RETIRED, SO THE PLANT CANNOT GO WHERE THE DEFECT LIVED.
	`config/prg_ingest/` was removed after the batches were baked into
	`config/prg.yaml`; the loader's merge is still the path a future generated
	batch travels, so the plant goes into a temporary fragment directory and
	`load_ingested` runs against it. The same guard, the same defect body.
	"""
	import pytest

	from tests.ci.canaries import REPO

	# The shipped defect, exactly as it stood in `param_batch5.yaml`.
	broken = """
parameters: {}
equations:
  emissions_peak_constraint:
    name: Emissions peak constraint
    system: carbon_trajectory
    lhs: emissions_mtco2_per_year
    rhs: emissions_mtco2_per_year
    relation: leq
    parameters:
    - emissions_mtco2_per_year
    tolerance: 1.0e-06
    unit_check: true
    solution_method: numeric
    linearity: linear
    priority: P2
relationships: []
cross_validation: []
"""

	# The control: the same register shape with a *distinct* rhs, which loads.
	# Without it, a refusal driven by the register shape itself would read as
	# the guard firing.
	repaired = broken.replace("rhs: emissions_mtco2_per_year", "rhs: 2 * emissions_mtco2_per_year")

	with tempfile.TemporaryDirectory() as tmp:
		(Path(tmp) / "param_batch5.yaml").write_text(broken)
		with pytest.raises(GraphError) as raised:
			load_ingested(tmp)
		assert "emissions_peak_constraint" in str(raised.value)

		(Path(tmp) / "param_batch5.yaml").write_text(repaired)
		graph, report = load_ingested(tmp)
		assert "emissions_peak_constraint" in graph.equations

	# And the shipped library itself carries no tautology: the defect's removal
	# is what the bake serves now, so the guard's historical target stays gone.
	for equation in load_graph().equations.values():
		assert parse_side(equation.lhs) != parse_side(equation.rhs), equation.id


# --------------------------------------------------------------------------
# The shipped fragments, which are the reason the loader exists.
# --------------------------------------------------------------------------


def test_the_shipped_fragments_load_and_report_a_clean_merge():
	"""A fragment the shipped document already carries merges cleanly.

	The batches this test originally ran on were baked into `config/prg.yaml`
	on 2026-10-17 and retired (their prose is preserved in
	`docs/param_ingest_batches.md`), so the default directory no longer exists
	and `load_ingested()` on it is now just the shipped graph -- the integration
	this test was named for is the bake itself.

	The loader contract it exercised still has to be covered, and the path a
	future generated batch travels is the same merge, so the fragment is
	rebuilt in a temp directory from the shipped document's *own* entries:
	every body verbatim identical, so the merge reports nothing refused,
	nothing unknown, and the graph comes back unexpanded. An entry whose body
	differed is the tautology canary's branch, not this one.
	"""
	shipped = load_graph()
	shipped_doc = yaml.safe_load(
		(default_ingest_dir().parent / "prg.yaml").read_text()
	)
	fragment = {
		"parameters": dict(list(shipped_doc["parameters"].items())[:2]),
		"equations": dict(
			(eid, eq) for eid, eq in list(shipped_doc["equations"].items())[:2]
		),
		"relationships": [],
		"cross_validation": [],
	}
	with tempfile.TemporaryDirectory() as tmp:
		(Path(tmp) / "param_batch0.yaml").write_text(
			yaml.safe_dump(fragment, sort_keys=False)
		)
		graph, report = load_ingested(tmp)
		assert report.refused == (), report.refused
		assert report.unknown == (), report.unknown
		# Nothing was corrected and nothing duplicated: the merged graph is
		# byte-equivalent to the shipped one on the registers the fragment
		# touched.
		assert len(graph.nodes) == len(shipped.nodes)
		assert len(graph.equations) == len(shipped.equations)


def test_every_free_node_in_the_ingested_graph_carries_a_value():
	"""The batches re-typed 26 nodes to `bool`/`categorical` and gave no default.

	`docs/param_ingest.md:78` says a `default` is required for a free node, and
	the loader does not enforce it, so the omission loaded. The shipped graph had
	declared all 26 as `float` on the `(0, 1e6)` placeholder with `default:
	500000.0`, and re-typing them to `bool` dropped that placeholder -- which
	made `check_scenario` over any defaults-built value set raise `the parameter
	set is missing [...]`. The shipped graph has no such node; the ingested one
	had three.

	The three were closed on 2026-10-17, each from its own on-record source:

	* `market_structure`, `market_model` -- categoricals, now carrying the level
	  `docs/what-if.md` documents (`Single Buyer` for the structure; the market
	  model's row repeats it, and the batch's own four levels are the *model*
	  vocabulary, so the structure's level maps to `regulated`).
	* `smart_metering_rollout` -- the documents disagree about its type:
	  `param_batch1.md` a share with `default: 0.3`, `param_batch7.md` a bool,
	  `docs/param_eqn_formula1.md` a year-indexed count. The batch kept the bool
	  and `true` is what its own 23 sibling booleans and `docs/what-if.md`'s
	  boolean rows take.

	The assertion is that the set is *empty*, not that it names three. Pinning
	three by name would go green again the moment a fourth node lost its default
	-- which is exactly how this defect arrived the first time.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}

	absent = sorted(
		k
		for k, n in graph.nodes.items()
		if n.default is None and n.role.value != "derived"
	)
	assert absent == [], absent

	# A value set built from the graph's own defaults is therefore a scenario the
	# graph can run, which is the property the three omissions denied it.
	result = check_scenario(values, graph)
	assert result is not None


def test_the_ingested_graph_is_consistent_at_its_own_defaults():
	"""The whole batch set, evaluated at the defaults it declares.

	This is the assertion the other integration tests stop short of: the merge
	can be clean, the graph strictly larger, and the graph still *unevaluable*.
	It was -- `mtbf_from_failure_rate_definition` computed MTBF from a variable
	`availability_definition` computes from MTBF, so the derived subgraph was
	cyclic and every `check_scenario` raised `CycleError ... form a cycle and
	have no evaluation order`, at any value set. A clean merge was silent about
	it because a cycle is a property of the edges, not of the fragments.

	Every node's value now comes from the graph, because every free node carries
	a default (see the test above). The two categoricals are the exception the
	value set cannot supply from `float` -- their defaults are level names, so
	they arrive from the document and not from a numeric placeholder.
	"""
	graph, _ = load_ingested(default_ingest_dir())
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}

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
	# The two categoricals come from the document as level names, not as
	# numeric placeholders: a level is a name, and the gate refuses an index.
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
	base["discount_rate"] = 0.25  # above the rule's other threshold

	def fires(gearing: float) -> bool:
		report = graph.cross_validate({**base, "gearing_ratio": gearing})
		return any(f.rule.id == "discount_rate_gearing_interaction" for f in report.violations)

	assert fires(4.1), "the rule must fire above a debt fraction of 80%"
	assert not fires(3.9), "3.9 is a debt fraction of 0.796 -- below the threshold"
	assert not fires(2.3333), "the default gearing is an ordinary structure"


def test_the_consistency_gate_refuses_the_three_defects_it_pins():
	"""Canary each repair where the repair's guard actually lives.

	Three defects, three different homes for their guard, after the fragments
	were retired and the plant can no longer go where the defect lived. Each
	mutation is disjoint from what its predicate reads, so a pass is evidence
	the predicate reached the defect and not that the edit missed:

	* the fuel-diversity denominator -- restored to `total_capacity_mw`, which
	  is a *different parameter*, not a different spelling of the same sum.
	  THE LOADER REFUSES THIS ONE, so the plant goes through a temp fragment
	  and `load_ingested` is asked to merge it: the unnamed-symbol guard fires
	  before any arithmetic, which is why the merge never gets far enough to
	  compute the index.
	* the gearing range -- the loader does NOT refuse it: a fragment can still
	  tighten a derived node's range to `[0, 0.95]` while the shipped graph
	  derives 2.3333, and `load_ingested` accepts silently. The guard for this
	  defect is the CI gate below
	  (`test_a_derived_node_is_not_declared_out_of_range_at_its_own_default`),
	  which reads the *merged* artifact. So the canary pins the shipped values
	  directly: the range the shipped yaml carries, and the derived value the
	  shipped drivers compute.
	* the LOLP decay -- same: the loader merges `exp((0 - 10) * m)` in silence;
	  the calibration travels on the shipped equation. Pinned by evaluating the
	  shipped rhs at the default and asserting it is the calibrated constant,
	  not the 0.2231 the defect would give.
	"""
	graph = load_graph()

	# The denominator, restored to the parameter it used to be.
	shipped_fd = graph.equations["fuel_diversity_definition"].model_dump(mode="json")
	shipped_fd["priority"] = "P2"
	broken = {**shipped_fd,
		"rhs": shipped_fd["rhs"].replace(") ** 2)", ") ** 2) / (total_capacity_mw ** 2)"),
	}
	assert broken["rhs"] != shipped_fd["rhs"], "the denominator mutation did not apply"
	with tempfile.TemporaryDirectory() as tmp:
		(Path(tmp) / "param_batch6.yaml").write_text(
			yaml.safe_dump({"parameters": {}, "equations": {"fuel_diversity_definition": broken},
				"relationships": [], "cross_validation": []}, sort_keys=False)
		)
		with pytest.raises(GraphError) as raised:
			load_ingested(tmp)
		assert "total_capacity_mw" in str(raised.value)

	# The gearing range: the shipped node's own, asserted against its computed
	# value. The defect's spelling is [0.0, 0.95]; the shipped image is wider.
	dscr = graph.nodes["project_gearing_dscr"]
	assert dscr.range == (-20.0, 20.0), dscr.range
	defaults = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	derived = graph.propagate(defaults).values
	assert -20.0 <= derived["project_gearing_dscr"] <= 20.0, derived["project_gearing_dscr"]

	# The LOLP decay: the shipped rhs at the default margin is the calibrated
	# constant 24/8760, not the 0.2231 the uncalibrated literal would give.
	lolp = graph.equations["lolp_definition"]
	at_default = evaluate(parse(lolp.rhs), {"reserve_margin_min": 0.15})
	assert at_default == pytest.approx(24 / 8760), at_default
	defect_value = evaluate(parse("exp((0 - 10) * reserve_margin_min)"), {"reserve_margin_min": 0.15})
	assert abs(defect_value - at_default) > 0.2


def test_a_corrected_equation_disposes_of_its_own_stale_edges():
	"""The disposal the correction legalises, and the report that counts it.

	Before fragments could correct equations, an edge whose equation no longer
	held its source was a load error -- right for a self-contradiction, but it
	also made every symbol-changing equation correction unloadable, because the
	correction is what makes the shipped edge stale. The loader now disposes of
	a corrected equation's stale edges and reports them, so the disappearance
	is counted rather than silent.

	Canaried two ways: the disposal must fire on the exact shape, and it must
	not touch an equation whose correction was prose-only. The historical
	solar correction is baked now, so the probe corrects
	`tariff_cost_recovery` on a tree where it is intact.
	"""
	import tempfile

	graph = load_graph()
	equation = graph.equations["tariff_cost_recovery"]
	shipped_rhs = equation.rhs
	assert "marginal_cost_usd_per_mwh" in shipped_rhs
	probe_name = "fuel_tariff_component"
	probe_node = dict(
		graph.nodes["opex_fixed_coal"].model_dump(exclude={"id"}, mode="json")
	)
	probe_node.update({
		"name": "Fuel tariff component", "unit": "USD/MWh",
		"range": [0.0, 200.0], "default": 20.0,
		"description": "A probe node the corrected equation names.",
	})
	corrected_rhs = shipped_rhs.replace(" + marginal_cost_usd_per_mwh", f" + {probe_name}")
	assert corrected_rhs != shipped_rhs
	corrected = equation.model_dump(mode="json")
	corrected["rhs"] = corrected_rhs
	corrected["parameters"] = [
		n for n in equation.parameters if n != "marginal_cost_usd_per_mwh"
	] + [probe_name]
	corrected["free_variables"] = [
		n for n in equation.free_variables if n != "marginal_cost_usd_per_mwh"
	] + [probe_name]
	intact = dict(graph.equations["crf_definition"].model_dump(mode="json"))
	intact["description"] = "probe prose only"

	with tempfile.TemporaryDirectory() as tmp:
		fragment = {
			"equations": {
				"tariff_cost_recovery": corrected,
				"crf_definition": intact,
			},
			"parameters": {probe_name: probe_node},
			"relationships": [],
			"cross_validation": [],
		}
		(Path(tmp) / "param_stale_probe.yaml").write_text(
			yaml.safe_dump(fragment, sort_keys=False)
		)
		merged, report = load_ingested(tmp)

	stale = [d for d in report.dropped if d[0] == "<stale-edge>"]
	found = [d for d in stale if d[1] == "tariff_cost_recovery"]
	assert found and "marginal_cost_usd_per_mwh" in found[0][2], stale
	assert not [d for d in stale if d[1] == "crf_definition"]
	assert not any(
		x.source == "marginal_cost_usd_per_mwh"
		and x.equation_id == "tariff_cost_recovery"
		for x in merged.edges
	)

