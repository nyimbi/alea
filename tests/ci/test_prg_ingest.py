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


