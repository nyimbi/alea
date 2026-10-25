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

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from alea.api.deps import AnalystDep, PublicDep
from alea.api.views import (
	CatalogReportOut,
	CatalogStatusJoinOut,
	CitationGapOut,
	CitationOut,
	CitationReportOut,
	ConflictOut,
	ConflictReportOut,
	ConflictRequest,
	ConsistencyReportOut,
	ConsistencyRequest,
	ConstraintReportOut,
	ConstraintRouteOut,
	CorrectionOut,
	CrossLayerQuantityOut,
	CrossLayerReportOut,
	CrossValidationFindingOut,
	CrossValidationReportOut,
	CrossValidationRuleOut,
	DependentOut,
	EngineTranslationOut,
	EquationCheckOut,
	EquationOut,
	FeedbackLoopOut,
	FeedbackReportOut,
	FeedbackSolveRequest,
	GraphEdgeOut,
	GraphOut,
	LoopResultOut,
	ParameterOut,
	PrgSummaryOut,
	PropagateRequest,
	PropagationOut,
	ResolutionOut,
	ResolveRequest,
	SensitivityOut,
	SensitivityRequest,
	TranslateOut,
	TranslateRequest,
	TranslateRouteOut,
	UncertaintyOut,
	UnitReportOut,
	ViolationOut,
)

if TYPE_CHECKING:
	from alea.prg.service import EquationRow

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


def _values(
	graph: Any, supplied: dict[str, float | str]
) -> dict[str, float | str]:
	"""Every node's default, with ``supplied`` laid over it.

	The convenience paths all need this and they all had it inline. Building it
	once means the routes cannot disagree about what a parameter set starts
	from -- and a route that forgot a node would propagate a set the graph
	refuses for a reason that is not the caller's.

	Refuses a key the graph does not declare. Without the check the key is
	simply dropped from the seeded set and the route answers a question about a
	different scenario than the one asked -- which is the silent-drop failure
	``translate.untranslated`` exists to count, one layer up.
	"""
	unknown = set(supplied) - set(graph.nodes)
	if unknown:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"{sorted(unknown)} are not parameters in the graph",
		)
	values = {
		name: node.default for name, node in graph.nodes.items() if node.default is not None
	}
	values.update(supplied)
	return values


def _parameter_out(graph: Any, name: str) -> ParameterOut:
	"""One node, with the couplings derived from the equations."""
	node = graph.nodes[name]
	equation = graph.determined_by(name)
	return ParameterOut(
		parameter_id=name,
		name=node.name,
		description=node.description,
		category=node.category,
		type=node.type.value,
		unit=node.unit or "",
		range=list(node.range) if node.range is not None else None,
		default=node.default,
		role=node.role.value,
		determinism=node.determinism.value,
		priority=node.priority.value,
		status=node.status,
		initial=node.initial,
		depends_on=list(graph.depends_on(name)),
		affects=list(graph.affects(name)),
		determined_by=equation.id if equation is not None else "",
	)


def _summary_out(graph: Any) -> PrgSummaryOut:
	"""The summary payload, built from the service's register.

	Factored out because three routes serve it -- ``/summary``, ``/graph`` and
	the export -- and three copies of a 40-field construction is three places
	for the payload to drift from the register.
	"""
	from alea.prg.service import graph_summary

	report = graph_summary(graph)
	engine = report["engine_translation"]
	units = report["units"]
	uncertainty = report["uncertainty"]
	return PrgSummaryOut(
		parameters=report["parameters"],
		equations=report["equations"],
		edges=report["edges"],
		derived=report["derived"],
		endogenous=report["endogenous"],
		endogenous_parameters=report["endogenous_parameters"],
		exogenous=report["exogenous"],
		free=report["free"],
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
			# The three verdict lists exclude the declared exemptions: an
			# exempt equation's walk still runs, but its verdict is the
			# declaration's own reclassification, so counting it in both a
			# list and the exempt register would double-count it and the
			# payload's partition (consistent + inconsistent + undecidable +
			# exempt = equations) would not close. The summary string keeps
			# the walk's own counts; the lists are the payload's partition.
			consistent=[
				_check_out(c)
				for c in units.consistent
				if c.equation_id not in units.exempt
			],
			inconsistent=[
				_check_out(c)
				for c in units.inconsistent
				if c.equation_id not in units.exempt
			],
			undecidable=[
				_check_out(c)
				for c in units.undecidable
				if c.equation_id not in units.exempt
			],
			exempt=list(units.exempt),
			summary=units.summary(),
		),
		uncertainty=UncertaintyOut(
			inputs=list(uncertainty.inputs),
			derived_stochastic=list(uncertainty.derived_stochastic),
			reachable=list(uncertainty.reachable),
			stochastic_edges=[list(edge) for edge in uncertainty.stochastic_edges],
			summary=uncertainty.summary(),
		),
		linearity=report["linearity"],
		cross_layer=CrossLayerReportOut(
			compared=report["cross_layer"]["compared"],
			reason=report["cross_layer"]["reason"],
			disagreements=[
				CrossLayerQuantityOut(**row)
				for row in report["cross_layer"]["disagreements"]
			],
		),
		catalog=CatalogReportOut(
			readable=report["catalog"]["readable"],
			reason=report["catalog"]["reason"],
			title_count=report["catalog"]["title_count"],
			row_count=report["catalog"]["row_count"],
			distinct_names=report["catalog"]["distinct_names"],
			declared_total=report["catalog"]["declared_total"],
			status_join=[
				CatalogStatusJoinOut(**row) for row in report["catalog"]["status_join"]
			],
			status_disagreements=list(report["catalog"]["status_disagreements"]),
		),
	)


def _violation_out(graph: Any, violation: Any) -> ViolationOut:
	"""One violation, with its equation's system and the strength it carries."""
	equation = graph.equations.get(violation.equation_id)
	return ViolationOut(
		equation_id=violation.equation_id,
		system=equation.system if equation is not None else "",
		residual=violation.residual,
		tolerance=violation.tolerance,
		strength=violation.strength,
		blocks=violation.blocks,
		detail=str(violation),
		unevaluable=getattr(violation, "unevaluable", ""),
	)


@router.get("/summary", response_model=PrgSummaryOut, summary="The graph's counts and registers")
async def summary(principal: PublicDep) -> PrgSummaryOut:
	"""The graph's own counts, and the registers that qualify them.

	The registers are load-bearing: a client that reads only ``parameters``
	and ``equations`` will assume the engine is driven by all of them, and
	three of fifty-two settable parameters reach a what-if knob.
	"""
	return _summary_out(_graph())


@router.get(
	"/citations",
	response_model=CitationReportOut,
	summary="The works the library cites, and where the copies are",
)
async def citations(principal: PublicDep) -> CitationReportOut:
	"""Every citation the library makes, joined to the source register.

	The register is a door rather than only a gate because ``GET
	/prg/equations`` serves each equation's ``reference`` as prose, and prose
	cannot tell a citation naming a real work from one naming a work nobody
	archived. ``gaps`` is that difference.

	Does not 404 when the register is absent: ``sources/INDEX.md`` is a document
	a deployment may not ship, and an empty register with every citation
	reported unregistered is the honest answer -- the alternative is a route
	that fails for a reason the client cannot act on.
	"""
	from alea.provenance.citations import citation_report

	report = citation_report()
	return CitationReportOut(
		citations=[
			CitationOut(
				key=citation.key,
				work=citation.work,
				custodian=citation.custodian,
				year=citation.year,
				url=citation.url,
				licence=citation.licence,
				archived=citation.archived,
				cites=list(citation.cites),
			)
			for citation in report.citations
		],
		gaps=[
			CitationGapOut(kind=gap.kind, subject=gap.subject, detail=gap.detail)
			for gap in report.gaps
		],
		registered=report.registered,
		archived=len(report.archived),
		summary=report.summary(),
	)


@router.get("/graph", response_model=GraphOut, summary="The whole graph")
async def graph_route(principal: PublicDep) -> GraphOut:
	"""Every parameter, every declared edge, every equation, and the registers.

	One payload rather than three routes a client has to join: a graph viewer
	needs all of it at once, and a client that fetched the nodes and then the
	edges would render a graph from two states of a file that can change
	between the calls.

	``edges`` is the *declared* relationship set. Propagation follows the
	equations, and on this document the two agree -- the graph refuses a
	document where an equation names what its ``parameters`` list does not. The
	declared set is what a reader draws; the equations are what the engine
	walks, and serving both lets a client see if they stop agreeing rather than
	inferring the coupling from whichever it happened to fetch.
	"""
	loaded = _graph()
	return GraphOut(
		parameters=[_parameter_out(loaded, name) for name in sorted(loaded.nodes)],
		edges=[
			GraphEdgeOut(
				source=edge.source,
				target=edge.target,
				equation_id=edge.equation_id,
				relationship=edge.relationship.value,
				direction=edge.direction.value,
				strength=edge.strength.value,
				description=edge.description,
			)
			for edge in loaded.edges
		],
		equations=[
			EquationOut(
				equation_id=row.equation_id,
				system=row.system,
				rendered=row.rendered,
				reference=row.reference,
			)
			for row in _equation_rows(loaded)
		],
		summary=_summary_out(loaded),
	)


@router.get(
	"/graph/export",
	summary="The graph as GraphML, for a viewer",
	response_class=Response,
)
async def graph_export(principal: PublicDep) -> Response:
	"""GraphML, because that is what a graph viewer reads.

	The spec names GraphML (§43) and the format matters: every viewer that
	would render this -- yEd, Gephi, Cytoscape -- reads GraphML and none of
	them reads this service's JSON. A route that served the JSON under an
	``export`` name would be an export in name only.

	Written by hand rather than through ``networkx``. ``networkx`` is a
	declared dependency and is used elsewhere in the tree, but the writer's
	output is a serialisation of *its* attribute model, and the keys here are
	typed -- ``range`` is a pair, ``users`` a tuple, neither of which GraphML's
	flat ``<data key=...>`` can hold without a convention. Emitting the
	elements directly is twenty lines and states the convention instead of
	inferring it from a library version.
	"""
	from xml.sax.saxutils import escape

	loaded = _graph()
	parts = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
		# The keys a viewer reads. Declared, because GraphML has no schema and
		# a `<data>` whose key is not declared is dropped by a conforming
		# reader -- an attribute that silently vanishes on import.
		'  <key id="name" for="node" attr.name="name" attr.type="string"/>',
		'  <key id="role" for="node" attr.name="role" attr.type="string"/>',
		'  <key id="unit" for="node" attr.name="unit" attr.type="string"/>',
		'  <key id="system" for="node" attr.name="system" attr.type="string"/>',
		'  <key id="relationship" for="edge" attr.name="relationship" attr.type="string"/>',
		'  <key id="strength" for="edge" attr.name="strength" attr.type="string"/>',
		'  <key id="equation" for="edge" attr.name="equation" attr.type="string"/>',
		'  <graph id="prg" edgedefault="directed">',
	]
	# Which system each parameter belongs to: the system of the equation that
	# determines it, which is the only place the graph records the association.
	# A settable parameter belongs to none, and the empty string says so rather
	# than inventing a system.
	system_of: dict[str, str] = {}
	for equation in loaded.equations.values():
		for target in equation.determined_variables:
			system_of[target] = equation.system
	for name in sorted(loaded.nodes):
		node = loaded.nodes[name]
		parts.append(f'    <node id="{escape(name)}">')
		parts.append(f'      <data key="name">{escape(node.name)}</data>')
		parts.append(f'      <data key="role">{node.role.value}</data>')
		parts.append(f'      <data key="unit">{escape(node.unit or "")}</data>')
		parts.append(f'      <data key="system">{system_of.get(name, "")}</data>')
		parts.append("    </node>")
	for index, edge in enumerate(loaded.edges):
		parts.append(f'    <edge id="e{index}" source="{escape(edge.source)}" '
			f'target="{escape(edge.target)}">')
		parts.append(
			f'      <data key="relationship">{edge.relationship.value}</data>'
		)
		parts.append(f'      <data key="strength">{edge.strength.value}</data>')
		parts.append(f'      <data key="equation">{escape(edge.equation_id)}</data>')
		parts.append("    </edge>")
	parts.append("  </graph>")
	parts.append("</graphml>")
	return Response(
		content="\n".join(parts) + "\n",
		media_type="application/graphml+xml",
		headers={"Content-Disposition": 'attachment; filename="prg.graphml"'},
	)


@router.get("/parameters", response_model=list[ParameterOut], summary="Every parameter")
async def parameters(
	principal: PublicDep,
	category: str | None = Query(default=None, min_length=1),
	role: str | None = Query(default=None, pattern="^(exogenous|endogenous|derived|free)$"),
) -> list[ParameterOut]:
	"""Every parameter node, optionally filtered.

	The filters are the two a client actually wants: by category, because the
	graph is browsed that way, and by role, because "what can I set" is the
	first question anyone asks of a parameter graph and the answer is a role.
	"""
	loaded = _graph()
	names = sorted(loaded.nodes)
	if category is not None:
		names = [n for n in names if loaded.nodes[n].category == category]
	if role is not None:
		names = [n for n in names if loaded.nodes[n].role.value == role]
	return [_parameter_out(loaded, name) for name in names]


@router.get(
	"/parameters/{parameter_id}",
	response_model=ParameterOut,
	summary="One parameter",
)
async def parameter(principal: PublicDep, parameter_id: str) -> ParameterOut:
	"""One parameter node, by id."""
	loaded = _graph()
	if parameter_id not in loaded.nodes:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{parameter_id!r} is not a parameter in the graph",
		)
	return _parameter_out(loaded, parameter_id)


@router.get(
	"/parameters/{parameter_id}/dependents",
	response_model=list[DependentOut],
	summary="What a parameter moves, transitively",
)
async def dependents(
	principal: PublicDep,
	parameter_id: str,
	direct_only: bool = Query(default=False),
) -> list[DependentOut]:
	"""Everything downstream of a parameter, ordered by distance.

	The closure, not one hop: a caller asking "what does this knob move" wants
	everything, and the one-hop answer -- which the ``affects`` field on
	``/parameters/{id}`` already carries -- is a different question. ``distance``
	is the hop count, so the client can order a re-check by how directly it is
	implicated rather than alphabetically.

	``direct_only`` narrows it to the one-hop set, which is what a client
	drawing an immediate-neighbourhood view wants; without the flag it gets the
	closure, which is what a client deciding what to re-verify wants.
	"""
	loaded = _graph()
	if parameter_id not in loaded.nodes:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{parameter_id!r} is not a parameter in the graph",
		)
	direct = set(loaded.affects(parameter_id))
	distance: dict[str, int] = {name: 1 for name in direct}
	frontier = sorted(direct)
	while frontier:
		current = frontier.pop()
		for dependent in loaded.affects(current):
			if dependent in distance or dependent == parameter_id:
				continue
			distance[dependent] = distance[current] + 1
			frontier.append(dependent)
	if direct_only:
		distance = {name: 1 for name in direct}
	return [
		DependentOut(parameter_id=name, distance=hop, direct=hop == 1)
		for name, hop in sorted(distance.items(), key=lambda kv: (kv[1], kv[0]))
	]


@router.get(
	"/equations/{equation_id}",
	response_model=EquationOut,
	summary="One equation",
)
async def equation(
	principal: PublicDep,
	equation_id: str,
	as_: str = Query(default="unicode", alias="as", pattern="^(unicode|latex|source)$"),
) -> EquationOut:
	"""One equation, rendered."""
	from alea.prg.service import describe

	loaded = _graph()
	if equation_id not in loaded.equations:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{equation_id!r} is not an equation in the graph",
		)
	found = loaded.equations[equation_id]
	return EquationOut(
		equation_id=equation_id,
		system=found.system,
		rendered=describe(found, as_=as_),
		reference=found.reference,
	)


@router.post(
	"/consistency/check",
	response_model=ConsistencyReportOut,
	summary="Whether a parameter set holds",
)
async def consistency_check(
	principal: AnalystDep, request: ConsistencyRequest
) -> ConsistencyReportOut:
	"""Validate a parameter set, propagating the derived values first.

	The propagation is what makes this a check of the *scenario*: a caller who
	sets an exogenous parameter and leaves the derived ones unset would
	otherwise be told the set is inconsistent when the truth is that it has not
	been computed.
	"""
	from alea.prg.service import check_scenario

	loaded = _graph()
	check = check_scenario(_values(loaded, request.set), loaded)
	return ConsistencyReportOut(
		consistent=check.consistent,
		violations=[_violation_out(loaded, v) for v in check.violations],
		unmodelled=list(check.unmodelled),
		excursions=dict(check.excursions),
		checked=len(loaded.equations) - len(check.unmodelled),
		summary=check.summary(),
	)


@router.get(
	"/consistency/report",
	response_model=ConsistencyReportOut,
	summary="The shipped default scenario, checked",
)
async def consistency_report(principal: PublicDep) -> ConsistencyReportOut:
	"""The graph's own defaults, propagated and checked against every equation.

	The specification calls this "get last consistency report", which presumes
	a per-caller session holding the previous check. There is none: this service
	keeps no per-user state, and a route that returned a baseline under a
	"last" name would be reporting something other than what it says. So this
	answers the question the name is *for* -- "is the scenario the graph ships
	consistent, before I change anything?" -- and the name is the spec's.

	Useful on its own: a client that fetches this first knows whether a
	violation it later sees came from its own parameters or was already there.

	WHY ``_values(loaded, {})`` AND NOT ``{}``. ``check_scenario`` validates a
	*complete* set -- it propagates first, and a propagation needs a value for
	every underived parameter. Handed the empty dict it refused with "missing
	53 parameters", so this route could not answer at all: every call was a
	422 naming the graph's own defaults as missing inputs. Seeding them is the
	whole of what "the shipped default scenario" means, and the same seeding
	the check route already does for a caller's partial set.
	"""
	from alea.prg.service import check_scenario

	loaded = _graph()
	check = check_scenario(_values(loaded, {}), loaded)
	return ConsistencyReportOut(
		consistent=check.consistent,
		violations=[_violation_out(loaded, v) for v in check.violations],
		unmodelled=list(check.unmodelled),
		excursions=dict(check.excursions),
		checked=len(loaded.equations) - len(check.unmodelled),
		summary=check.summary(),
	)


@router.post(
	"/propagate",
	response_model=PropagationOut,
	summary="Apply a change and report what moved",
)
async def propagate(principal: AnalystDep, request: PropagateRequest) -> PropagationOut:
	"""Apply ``changes`` to ``set`` and report every parameter that moved.

	``changes`` may name only settable parameters. A change to a derived one is
	refused by name: setting a computed parameter alongside the one it depends
	on is exactly the inconsistency the graph exists to refuse, and silently
	overwriting it would answer a question about a scenario nobody described.
	"""
	from alea.prg.service import propagate_change

	loaded = _graph()
	if not request.changes:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="`changes` is empty; a propagation with nothing to propagate "
			"would report the parameter set back unchanged",
		)
	try:
		report = propagate_change(_values(loaded, request.set), request.changes, loaded)
	except ValueError as exc:
		# The graph's own refusal, carried as a 422 rather than a 500: it is a
		# statement about the request, and its message names the equation that
		# computes each parameter the caller tried to set.
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
		) from exc
	return PropagationOut(
		values=report["values"],
		changed=report["changed"],
		order=list(report["order"]),
		loops=[
			LoopResultOut(
				loop=entry["loop"],
				iterations=entry["iterations"],
				change=entry["change"],
				converged=entry["converged"],
			)
			for entry in report["loops"]
		],
	)


@router.post(
	"/conflicts/resolve",
	response_model=list[ResolutionOut],
	summary="Apply the highest-ranked corrections",
)
async def conflicts_resolve(
	principal: AnalystDep, request: ResolveRequest
) -> list[ResolutionOut]:
	"""Detect conflicts, apply the top corrections, and report the set after each.

	One correction per conflict by default, and the correction is the one the
	ranking put first -- which is ranked by ``relative_move``, so it is the
	smallest real-world change that would clear the residual. Not the *only*
	correction: the report carries the alternatives, and ``rank`` raises how
	many are offered.

	The resolved set is re-propagated and re-checked after each correction
	rather than once at the end, because corrections interact. A single final
	set would hide a correction that undid an earlier one, and the caller
	stepping through a resolution is exactly the caller who needs to see that.
	"""
	from alea.prg.conflicts import detect_conflicts

	loaded = _graph()
	values = _values(loaded, request.set)
	report = detect_conflicts(loaded, loaded.propagate(values).values, supplied=request.set)
	out: list[ResolutionOut] = []
	for conflict in report.ranked():
		# The first correction that *stays inside its declared range*, not
		# simply the first. The ranking is by relative move, so on this graph
		# the smallest proportional correction to an over-determined
		# ``marginal_cost`` is a negative fuel price: the residual is large
		# against a 300 USD/MWh range, so every candidate leaves it, and
		# applying ``corrections[0]`` blindly resolves one contradiction by
		# producing a scenario the graph then refuses -- a fix that trades one
		# violation for another. The detector records ``within_range`` on each
		# candidate; this is the reader that has to act on it.
		applied = next(
			(c for c in conflict.corrections if c.within_range),
			None,
		)
		if applied is None:
			out.append(
				ResolutionOut(
					conflict=_conflict_out(loaded, conflict),
					applied=None,
					resolved=False,
					values_after={},
				)
			)
			continue
		# The corrected value goes through the same range check the conflict
		# detector already ran: a correction outside the parameter's declared
		# range would resolve this equation by producing a scenario the graph
		# refuses, which is a fix that trades one violation for another.
		moved = dict(values)
		moved[applied.parameter] = applied.current + applied.delta
		after = loaded.propagate(moved)
		out.append(
			ResolutionOut(
				conflict=_conflict_out(loaded, conflict),
				applied=CorrectionOut(
					parameter=applied.parameter,
					unit=_unit_of(loaded, applied.parameter),
					delta=applied.delta,
					elasticity=applied.elasticity,
					within_range=applied.within_range,
					current=applied.current,
					relative_move=applied.relative_move,
				),
				resolved=not loaded.consistency(after.values),
				values_after=after.values,
			)
		)
	return out


@router.post(
	"/feedback/solve",
	response_model=FeedbackReportOut,
	summary="Solve the feedback loops",
)
async def feedback_solve(
	principal: AnalystDep, request: FeedbackSolveRequest
) -> FeedbackReportOut:
	"""Solve every feedback loop at a parameter set, and report the iteration.

	``iterations`` and ``change`` are carried per loop because "it converged"
	alone is not a result a reader can weigh: a loop that settled in four turns
	and one that needed 180 both report success, and only one of them is close
	to not settling at all.
	"""
	from alea.prg.feedback import FeedbackError

	loaded = _graph()
	values = _values(loaded, request.set)
	try:
		result = loaded.propagate(values)
	except (FeedbackError, ValueError) as exc:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
		) from exc
	by_id = {loop.id: loop for loop in loaded.feedback_loops()}
	return FeedbackReportOut(
		loops=[
			FeedbackLoopOut(
				loop=solved.loop,
				variables=list(by_id[solved.loop].variables) if solved.loop in by_id else [],
				equations=(
					[equation.id for equation in by_id[solved.loop].equations]
					if solved.loop in by_id
					else []
				),
				converged=solved.converged,
				iterations=solved.iterations,
				change=solved.change,
				values=dict(solved.values),
			)
			for solved in result.loops
		],
		values=result.values,
	)


@router.post(
	"/translate",
	response_model=TranslateOut,
	summary="The engine parameters a scenario reaches",
)
async def translate(principal: AnalystDep, request: TranslateRequest) -> TranslateOut:
	"""Translate a parameter set into what-if knobs, and name what did not go.

	The ``untranslated`` list is the point of the route. Three of the graph's
	fifty-two settable parameters reach a knob; a client that received only
	``parameters`` would believe the whole scenario reached the engine, and a
	scenario that sets one of the other forty-nine solves as though it had not
	been set. The register is what makes that countable.

	``ratio`` translations need a network and this route has none, so they are
	reported as untranslated rather than raising. A route that refused the whole
	call because one parameter needs a network would be unusable for the common
	case -- a caller checking which knobs a scenario reaches before it has
	solved anything.
	"""
	from alea.prg import translate as layer

	loaded = _graph()
	values = _values(loaded, request.set)
	routes: list[TranslateRouteOut] = []
	translated: dict[str, float] = {}
	skipped: list[str] = []
	for translation in layer.translations():
		if translation.prg_parameter not in values:
			continue
		if translation.kind != "absolute":
			# No network here, so the ratio cannot be formed. Named rather than
			# dropped: the difference between "the engine cannot carry this" and
			# "this route has no network to divide by" is the difference between
			# a modelling gap and an API limitation -- which is why this goes to
			# ``deferred`` and not into ``untranslated``. Merging the two made
			# the payload contradict its own ``coverage``: the coverage is
			# computed from the graph and counts ``fuel_price_usd_per_mwh`` as
			# reaching a knob, while the merged list named the same parameter as
			# reaching none.
			skipped.append(translation.prg_parameter)
			continue
		routes.append(
			TranslateRouteOut(
				parameter=translation.prg_parameter,
				engine_field=translation.engine_field,
				kind=translation.kind,
				reason=translation.note,
			)
		)
		translated[translation.engine_field] = float(values[translation.prg_parameter])
	return TranslateOut(
		parameters=translated,
		routes=routes,
		untranslated=list(layer.untranslated(loaded)),
		deferred=sorted(set(skipped)),
		coverage=EngineTranslationOut(**layer.coverage(loaded)),
	)


def _equation_rows(graph: Any) -> list[EquationRow]:
	"""One row per equation, in the library's order."""
	from alea.prg.service import equation_report

	return equation_report(graph)


def _conflict_out(graph: Any, conflict: Any) -> ConflictOut:
	"""One conflict, with the unit its residual is in and its corrections."""
	return ConflictOut(
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


@router.get("/equations", response_model=list[EquationOut], summary="The equation library")
async def equations(
	principal: PublicDep,
	system: str | None = Query(default=None, min_length=1),
	as_: str = Query(default="unicode", alias="as", pattern="^(unicode|latex|source)$"),
) -> list[EquationOut]:
	"""Every equation, rendered in the requested notation."""
	from alea.prg.service import equation_report

	return [
		EquationOut(
			equation_id=row.equation_id,
			system=row.system,
			rendered=row.rendered,
			reference=row.reference,
		)
		for row in equation_report(_graph(), as_=as_, system=system)
	]


@router.post(
	"/conflicts",
	response_model=ConflictReportOut,
	summary="Why a parameter set is inconsistent, and what to move",
)
@router.post(
	"/conflicts/detect",
	response_model=ConflictReportOut,
	include_in_schema=False,
)
async def conflicts(principal: AnalystDep, request: ConflictRequest) -> ConflictReportOut:
	"""Detect conflicts in a parameter set and rank the corrections.

	A POST, not a GET: the parameter set is the body, and a set large enough to
	be useful is too large for a query string.

	Served at two paths, and the second is not vanity. The specification's §43
	table names ``/conflicts/detect``; the route was built as ``/conflicts``,
	which reads better beside ``/conflicts/resolve``. A client written to the
	published table would 404 on a service that answers the same question at
	the other spelling, and a 404 on a documented endpoint is indistinguishable
	from a missing feature. Both are served, the spec's spelling is the alias
	(``include_in_schema=False`` so the OpenAPI document names one path per
	operation rather than two), and the SDK calls the canonical one.
	"""
	from alea.prg.conflicts import detect_conflicts

	graph = _graph()
	propagated = graph.propagate(_values(graph, request.set))
	report = detect_conflicts(
		graph, propagated.values, supplied=request.set, rank=request.rank
	)
	return ConflictReportOut(
		conflicts=[_conflict_out(graph, conflict) for conflict in report.ranked()],
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
	propagated = graph.propagate(_values(graph, request.set))
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
	propagated = graph.propagate(_values(graph, request.set))
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
