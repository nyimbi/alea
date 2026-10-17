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

from alea.prg.conflicts import (
	Conflict,
	ConflictKind,
	ConflictReport,
	Correction,
	detect_conflicts,
	suggest_corrections,
)
from alea.prg.crossval import (
	CrossValidationFinding,
	CrossValidationReport,
	CrossValidationRule,
	Severity,
	evaluate_condition,
	parse_rule,
	rules_from_document,
	run_rules,
)
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
	IngestReport,
	ParameterGraph,
	PropagationResult,
	Violation,
	default_ingest_dir,
	default_prg_path,
	load_graph,
	load_ingested,
)
from alea.prg.sensitivity import (
	GradientTable,
	Sensitivity,
	elasticity,
	gradients,
	sensitivity,
	sensitivity_table,
)
from alea.prg.uncertainty import UncertaintyRegister, register
from alea.prg.units import (
	EquationCheck,
	UnitReport,
	check_equation,
	check_graph,
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
	"Conflict",
	"ConflictKind",
	"ConflictReport",
	"CrossValidationFinding",
	"CrossValidationReport",
	"CrossValidationRule",
	"Const",
	"Correction",
	"CycleError",
	"Determinism",
	"Direction",
	"DslError",
	"Equation",
	"Expr",
	"Expression",
	"Func",
	"GradientTable",
	"GraphError",
	"IngestReport",
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
	"Sensitivity",
	"Strength",
	"Subscript",
	"Sum",
	"Symbol",
	"Violation",
	"const",
	"default_ingest_dir",
	"default_prg_path",
	"detect_conflicts",
	"elasticity",
	"evaluate",
	"evaluate_array",
	"evaluate_condition",
	"gradients",
	"load_graph",
	"load_ingested",
	"parse",
	"parse_rule",
	"rules_from_document",
	"run_rules",
	"sensitivity",
	"sensitivity_table",
	"simplify",
	"solve_for",
	"suggest_corrections",
	"sym",
	"check_equation",
	"check_graph",
	"EquationCheck",
	"Severity",
	"UnitReport",
	"UncertaintyRegister",
	"register",
]
