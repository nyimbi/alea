# SPDX-License-Identifier: MIT
"""What the PRG is asked to do: check a scenario, propagate a change, report.

WHY this is a thin layer over :class:`ParameterGraph` and not the graph itself.
The graph is a value: it loads, it validates, it computes. This module is where
a *question* is turned into graph operations -- "is this scenario consistent",
"what does this knob move", "which systems are not modelled" -- so the CLI, the
what-if engine and a test all ask the same question through the same function
rather than each assembling the operations slightly differently.

WHY ``explain`` renders rather than returns a dict. The equations are the
reason the PRG exists, and a caller that wants them wants them as LaTeX or as
Unicode text. Returning a structured object and leaving every caller to render
it is how two callers end up disagreeing about what an equation says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alea.prg.graph import ParameterGraph, Violation, load_graph
from alea.prg.library import SYSTEM_IDS, coverage, systems_of
from alea.prg.views import Equation

__all__ = [
	"ScenarioCheck",
	"check_scenario",
	"describe",
	"equation_report",
	"graph_summary",
	"propagate_change",
]


@dataclass(frozen=True)
class ScenarioCheck:
	"""The result of validating a parameter set."""

	consistent: bool
	violations: tuple[Violation, ...]
	unmodelled: tuple[str, ...]
	"""Systems the library does not cover, so their absence is not a pass."""

	def summary(self) -> str:
		if self.consistent and not self.unmodelled:
			return "consistent against every modelled system"
		parts: list[str] = []
		if self.violations:
			parts.append(f"{len(self.violations)} violation(s)")
		if self.unmodelled:
			parts.append(f"{len(self.unmodelled)} system(s) not modelled")
		return "; ".join(parts)


def _graph(graph: ParameterGraph | None) -> ParameterGraph:
	return graph if graph is not None else load_graph()


def graph_summary(graph: ParameterGraph | None = None) -> dict[str, Any]:
	"""Counts and the two registers that matter: loops and uncovered systems."""
	g = _graph(graph)
	by_system = systems_of(g.equations)
	return {
		"parameters": len(g.nodes),
		"equations": len(g.equations),
		"edges": len(g.edges),
		"systems": {
			system_id: len(equations)
			for system_id, equations in by_system.items()
			if equations
		},
		"systems_declared": len(SYSTEM_IDS),
		"unmodelled_systems": [entry.split(":")[0] for entry in coverage(g.equations)],
		"derived": len(g.order()),
		"feedback_loops": [str(loop) for loop in g.feedback_loops()],
		"structure_issues": g.structure_issues(),
	}


def check_scenario(
	values: dict[str, float], graph: ParameterGraph | None = None
) -> ScenarioCheck:
	"""Validate a parameter set, propagating the derived parameters first.

	The propagation is what makes this a check of the *scenario* rather than of
	the numbers handed in: a caller who sets an exogenous parameter and leaves
	the derived ones at their previous values would otherwise be told their
	scenario is inconsistent when the truth is that it has not been computed.
	"""
	g = _graph(graph)
	result = g.propagate(values)
	violations = g.consistency(result.values)
	return ScenarioCheck(
		consistent=not violations,
		violations=tuple(violations),
		unmodelled=tuple(coverage(g.equations)),
	)


def propagate_change(
	values: dict[str, float],
	changes: dict[str, float],
	graph: ParameterGraph | None = None,
) -> dict[str, Any]:
	"""Apply ``changes`` to ``values`` and report what moved."""
	g = _graph(graph)
	unknown = set(changes) - set(g.nodes)
	if unknown:
		raise ValueError(f"{sorted(unknown)} are not parameters in the graph")
	computed = sorted(name for name in changes if not g.is_settable(name))
	if computed:
		by: dict[str, str] = {}
		for name in computed:
			equation = g.determined_by(name)
			by[name] = equation.id if equation is not None else "a feedback loop"
		raise ValueError(
			f"{computed} are computed by the graph, not set: {by}. Setting a "
			f"computed parameter alongside the one it depends on is exactly the "
			f"inconsistency the PRG exists to refuse"
		)

	# The baseline is *propagated* before the change is applied, and the
	# difference is taken between two solved parameter sets. Diffing inside one
	# propagation cannot work: a derived parameter has no value before the
	# first pass, so it is never in `before` and every derived parameter reads
	# as unmoved -- which is the opposite of what a caller asking "what did
	# this knob move" wants to know.
	baseline = g.propagate(dict(values)).values
	scoped = dict(values)
	scoped.update(changes)
	result = g.propagate(scoped)
	moved = {
		name: result.values[name] - baseline[name]
		for name in result.values
		if name in baseline
		and abs(result.values[name] - baseline[name])
		> 1e-12 * max(abs(result.values[name]), 1.0)
	}
	return {
		"values": result.values,
		"changed": moved,
		"order": list(result.order),
		"loops": [
			{"loop": lr.loop, "iterations": lr.iterations, "change": lr.change}
			for lr in result.loops
		],
	}


def describe(equation: Equation, *, as_: str = "unicode") -> str:
	"""Render one equation.

	The relation is rendered too: an equation that is an inequality reads as a
	different claim from one that is an equality, and a report that prints both
	with ``=`` misstates half the library.
	"""
	from alea.prg.dsl import parse

	lhs, rhs = parse(equation.lhs), parse(equation.rhs)
	if as_ == "latex":
		join = {"leq": r" \leq ", "geq": r" \geq ", "eq": " = "}[equation.relation]
		return f"{lhs.latex()}{join}{rhs.latex()}"
	if as_ == "source":
		join = {"leq": " <= ", "geq": " >= ", "eq": " == "}[equation.relation]
		return f"{lhs.source()}{join}{rhs.source()}"
	join = {"leq": " ≤ ", "geq": " ≥ ", "eq": " = "}[equation.relation]
	return f"{lhs.unicode()}{join}{rhs.unicode()}"


def equation_report(
	graph: ParameterGraph | None = None,
	*,
	as_: str = "unicode",
	system: str | None = None,
) -> list[tuple[str, str, str]]:
	"""Every equation as ``(id, system, rendered)``, for a report or a listing."""
	g = _graph(graph)
	by_system = systems_of(g.equations)
	out: list[tuple[str, str, str]] = []
	for system_id, equations in by_system.items():
		if system is not None and system_id != system:
			continue
		for equation in equations:
			out.append((equation.id, system_id, describe(equation, as_=as_)))
	return out
