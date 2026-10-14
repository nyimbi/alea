# SPDX-License-Identifier: MIT
"""The Parameter Relationship Graph.

ALEA's parameters are not independent knobs. They are coupled by physical laws,
accounting identities, engineering limits, economic behaviour, policy and
feedback, and a scenario that sets two coupled parameters independently is a
scenario that solves and returns a contradiction. This package is the graph
that knows the couplings, the equation library that states them, and the
engines that validate a parameter set, propagate a change through it, and solve
the feedback loops the couplings contain.

    from alea.prg import load_graph

    graph = load_graph()
    result = graph.propagate({"carbon_price_usd_per_tco2": 120.0, ...})
    violations = graph.consistency(result.values)
"""

from __future__ import annotations

from alea.prg.dsl import (
	Add,
	Const,
	DslError,
	Expr,
	Expression,
	Func,
	Mul,
	Pow,
	Subscript,
	Sum,
	Symbol,
	const,
	evaluate,
	evaluate_array,
	parse,
	simplify,
	solve_for,
	sym,
)
from alea.prg.graph import (
	CycleError,
	GraphError,
	ParameterGraph,
	PropagationResult,
	Violation,
	default_prg_path,
	load_graph,
)
from alea.prg.views import (
	Determinism,
	Direction,
	Equation,
	ParameterNode,
	ParameterType,
	Priority,
	Relationship,
	RelationshipEdge,
	Role,
	Strength,
)

__all__ = [
	"Add",
	"Const",
	"CycleError",
	"Determinism",
	"Direction",
	"DslError",
	"Equation",
	"Expr",
	"Expression",
	"Func",
	"GraphError",
	"Mul",
	"ParameterGraph",
	"ParameterNode",
	"ParameterType",
	"Pow",
	"Priority",
	"PropagationResult",
	"Relationship",
	"RelationshipEdge",
	"Role",
	"Strength",
	"Subscript",
	"Sum",
	"Symbol",
	"Violation",
	"const",
	"default_prg_path",
	"evaluate",
	"evaluate_array",
	"load_graph",
	"parse",
	"simplify",
	"solve_for",
	"sym",
]
