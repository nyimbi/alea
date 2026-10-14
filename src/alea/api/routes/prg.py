# SPDX-License-Identifier: MIT
"""Parameter relationship graph routes.

The PRG is a value: it loads from a YAML file, validates, and computes. Every
route here reads that value or runs a pure function over it, so none of them
touches the database or an artefact and none is enqueued as a job. That is the
opposite of the what-if routes, and deliberately: a what-if solve is two hours
of optimisation, and a sensitivity is a chain of derivatives along a
topological order. Serving the second as a job would be a lie about its cost.

The three POSTs take a body because they carry a parameter set -- the plan's
rule, applied mechanically: a GET takes scalars, a POST takes a body.

Every response carries the registers, not just the answer. ``/prg/summary``
reports how many equations the dimensional check could *not* decide, and
``/prg/conflicts`` reports what it examined. A client that renders a green
count from a check whose coverage shrank is reporting something the service
never claimed, and the only place to prevent that is in the payload.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from alea.api.deps import AnalystDep, PublicDep
from alea.api.views import (
	ConflictOut,
	ConflictReportOut,
	ConflictRequest,
	ConstraintReportOut,
	ConstraintRouteOut,
	CorrectionOut,
	CrossValidationFindingOut,
	CrossValidationReportOut,
	CrossValidationRuleOut,
	EngineTranslationOut,
	EquationCheckOut,
	EquationOut,
	PrgSummaryOut,
	SensitivityOut,
	SensitivityRequest,
	UncertaintyOut,
	UnitReportOut,
)

router = APIRouter(prefix="/prg", tags=["prg"])


def _graph():
	"""The graph, loaded fresh.

	Not cached: the file is small, loading it validates it, and a cached graph
	would serve a stale answer after the file changes -- the defect this whole
	module exists to avoid, one level up.
	"""
	from alea.prg import load_graph

	return load_graph()


def _check_out(check: Any) -> EquationCheckOut:
	return EquationCheckOut(
		equation_id=check.equation_id,
		decidable=check.decidable,
		consistent=check.consistent,
		lhs=check.lhs,
		rhs=check.rhs,
		detail=check.detail,
	)


def _constraints_out(report: dict[str, Any]) -> ConstraintReportOut:
	"""The constraint register, with every route's reason carried through.

	The reasons are not dropped for brevity: four of the six inequalities are
	unbound, and the *only* thing distinguishing "the graph derives this from a
	solved result, so the audit checks it after" from "this failed to build" is
	the text. A payload that served the status alone would leave a client
	guessing which.
	"""
	return ConstraintReportOut(
		bound=list(report["bound"]),
		unbound=list(report["unbound"]),
		count=report["count"],
		constraint_shaped=report["constraint_shaped"],
		identities=report["identities"],
		total=report["total"],
		fraction=report["fraction"],
		routes=[
			ConstraintRouteOut(
				equation_id=route["equation_id"],
				status=route["status"],
				reason=route["reason"],
				unresolved=list(route["unresolved"]),
				assumed=list(route["assumed"]),
			)
			for route in report["routes"]
		],
	)


def _unit_of(graph: Any, parameter: str) -> str:
	"""A parameter's recorded unit, for a number that carries it.

	``""`` when the parameter is not a node -- a conflict's subject can name an
	equation, whose two sides share a dimension rather than having a unit of
	their own. The empty string says "no unit recorded" rather than inventing
	one, which is the same choice ``ValueOut`` makes for a source it does not
	have.
	"""
	node = graph.nodes.get(parameter)
	return node.unit if node is not None and node.unit is not None else ""


@router.get("/summary", response_model=PrgSummaryOut, summary="The graph's counts and registers")
async def summary(principal: PublicDep) -> PrgSummaryOut:
	"""The graph's own counts, and the registers that qualify them.

	The registers are load-bearing: a client that reads only ``parameters``
	and ``equations`` will assume the engine is driven by all of them, and
	three of fifty-three settable parameters reach a what-if knob.
	"""
	from alea.prg.service import graph_summary

	report = graph_summary(_graph())
	engine = report["engine_translation"]
	units = report["units"]
	uncertainty = report["uncertainty"]
	return PrgSummaryOut(
		parameters=report["parameters"],
		equations=report["equations"],
		edges=report["edges"],
		derived=report["derived"],
		systems=report["systems"],
		systems_declared=report["systems_declared"],
		unmodelled_systems=report["unmodelled_systems"],
		feedback_loops=report["feedback_loops"],
		structure_issues=report["structure_issues"],
		cross_validation_rules=report["cross_validation_rules"],
		edge_strength=report["edge_strength"],
		engine_translation=EngineTranslationOut(**engine),
		constraints=_constraints_out(report["constraints"]),
		units=UnitReportOut(
			consistent=[_check_out(c) for c in units.consistent],
			inconsistent=[_check_out(c) for c in units.inconsistent],
			undecidable=[_check_out(c) for c in units.undecidable],
			summary=units.summary(),
		),
		uncertainty=UncertaintyOut(
			inputs=list(uncertainty.inputs),
			derived_stochastic=list(uncertainty.derived_stochastic),
			reachable=list(uncertainty.reachable),
			stochastic_edges=[list(edge) for edge in uncertainty.stochastic_edges],
			summary=uncertainty.summary(),
		),
	)


@router.get("/equations", response_model=list[EquationOut], summary="The equation library")
async def equations(
	principal: PublicDep,
	system: str | None = Query(default=None, min_length=1),
	as_: str = Query(default="unicode", alias="as", pattern="^(unicode|latex|source)$"),
) -> list[EquationOut]:
	"""Every equation, rendered in the requested notation."""
	from alea.prg.service import equation_report

	return [
		EquationOut(equation_id=equation_id, system=system_id, rendered=rendered)
		for equation_id, system_id, rendered in equation_report(
			_graph(), as_=as_, system=system
		)
	]


@router.post(
	"/conflicts",
	response_model=ConflictReportOut,
	summary="Why a parameter set is inconsistent, and what to move",
)
async def conflicts(principal: AnalystDep, request: ConflictRequest) -> ConflictReportOut:
	"""Detect conflicts in a parameter set and rank the corrections.

	A POST, not a GET: the parameter set is the body, and a set large enough to
	be useful is too large for a query string.
	"""
	from alea.prg.conflicts import detect_conflicts

	graph = _graph()
	unknown = set(request.set) - set(graph.nodes)
	if unknown:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"{sorted(unknown)} are not parameters in the graph",
		)
	values = {
		name: node.default
		for name, node in graph.nodes.items()
		if node.default is not None
	}
	values.update(request.set)
	propagated = graph.propagate(values)
	report = detect_conflicts(
		graph, propagated.values, supplied=request.set, rank=request.rank
	)
	return ConflictReportOut(
		conflicts=[
			ConflictOut(
				kind=str(conflict.kind),
				subject=conflict.subject,
				detail=conflict.detail,
				unit=_unit_of(graph, conflict.subject),
				residual=conflict.residual,
				tolerance=conflict.tolerance,
				strength=conflict.strength,
				blocks=conflict.blocks,
				corrections=[
					CorrectionOut(
						parameter=correction.parameter,
						unit=_unit_of(graph, correction.parameter),
						delta=correction.delta,
						elasticity=correction.elasticity,
						within_range=correction.within_range,
						current=correction.current,
						relative_move=correction.relative_move,
					)
					for correction in conflict.corrections
				],
			)
			for conflict in report.ranked()
		],
		checked=list(report.checked),
		consistent=report.consistent,
		summary=report.summary(),
	)


@router.post(
	"/sensitivity",
	response_model=SensitivityOut,
	summary="A derived parameter's derivatives at a point",
)
async def sensitivity(
	principal: AnalystDep, request: SensitivityRequest
) -> SensitivityOut:
	"""The derivatives of one derived parameter, at a parameter set.

	Exact forward-mode derivatives over the topological order, not finite
	differences: the truncation error of a difference quotient has to be tuned
	per parameter, and the tuning is what makes a sensitivity report
	irreproducible.
	"""
	from alea.prg.sensitivity import sensitivity as compute

	graph = _graph()
	if request.parameter not in graph.nodes:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{request.parameter!r} is not a parameter in the graph",
		)
	unknown = set(request.set) - set(graph.nodes)
	if unknown:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"{sorted(unknown)} are not parameters in the graph",
		)
	values = {
		name: node.default
		for name, node in graph.nodes.items()
		if node.default is not None
	}
	values.update(request.set)
	propagated = graph.propagate(values)
	row = compute(graph, request.parameter, propagated.values)
	largest = dict(row.largest(request.top))
	return SensitivityOut(
		parameter=row.parameter,
		method=row.method,
		value=propagated.values.get(request.parameter),
		derivatives=largest,
	)


@router.post(
	"/cross-validation",
	response_model=CrossValidationReportOut,
	summary="Rules that span more than one parameter, against a scenario",
)
async def cross_validation(
	principal: AnalystDep, request: ConflictRequest
) -> CrossValidationReportOut:
	"""Every declared cross-validation rule against a parameter set.

	Analyst-tier like the other POSTs: it takes a body and runs the graph, and
	the tier rule here is mechanical -- a GET takes scalars and is public, a
	POST takes a body and is analyst. What it answers is a policy question
	rather than an arithmetic one, which is why the payload carries the
	severity and the ``evaluated`` flag rather than a single verdict.
	"""
	graph = _graph()
	unknown = set(request.set) - set(graph.nodes)
	if unknown:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"{sorted(unknown)} are not parameters in the graph",
		)
	values = {
		name: node.default
		for name, node in graph.nodes.items()
		if node.default is not None
	}
	values.update(request.set)
	propagated = graph.propagate(values)
	report = graph.cross_validate(propagated.values)
	return CrossValidationReportOut(
		findings=[
			CrossValidationFindingOut(
				rule_id=finding.rule.id,
				severity=finding.severity.value,
				evaluated=finding.evaluated,
				message=finding.rule.message,
				suggestion=finding.rule.suggestion,
				detail=finding.detail,
			)
			for finding in report.findings
		],
		rules=[
			CrossValidationRuleOut(
				id=rule.id,
				condition=rule.condition,
				severity=rule.severity.value,
				message=rule.message,
				suggestion=rule.suggestion,
				parameters=sorted(rule.parameters),
			)
			for rule in report.rules
		],
		violations=len(report.violations),
		undecided=len(report.undecided),
		blocks=report.blocks,
		summary=report.summary(),
	)
