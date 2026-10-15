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

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from alea.prg import constraints, translate
from alea.prg.crossval import CrossValidationReport
from alea.prg.graph import ParameterGraph, Violation, load_graph
from alea.prg.library import SYSTEM_IDS, coverage, systems_of
from alea.prg.uncertainty import register as uncertainty_register
from alea.prg.units import check_graph as check_units
from alea.prg.views import Equation, Role

__all__ = [
	"EquationRow",
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

	excursions: dict[str, float] = field(default_factory=dict)
	"""Derived values the equations fixed outside their declared range."""

	cross_validation: CrossValidationReport | None = None
	"""The cross-validation rules the scenario breaks, if any were declared.

	``None`` when the graph declares no rules, which is a different fact from
	an empty report: "no rule was violated" and "no rule was checked" read
	identically in a finding list, and the caller needs to tell them apart.
	"""

	def summary(self) -> str:
		parts: list[str] = []
		if self.consistent and not self.unmodelled:
			parts.append("consistent against every modelled system")
		else:
			if self.violations:
				parts.append(f"{len(self.violations)} violation(s)")
			if self.unmodelled:
				parts.append(f"{len(self.unmodelled)} system(s) not modelled")
		# The cross-validation line is appended whether or not the equation
		# check passed: a scenario can satisfy every equation and still break a
		# rule no equation states, and a summary that reported only the first
		# would call that consistent.
		if self.cross_validation is not None:
			parts.append(self.cross_validation.summary())
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
		# ``computed`` and not ``order``. The field is the derived half of the
		# role partition -- it sits beside ``endogenous``, and the two together
		# are "not settable" -- so it has to count the nodes carrying the
		# derived role. ``order`` is the topological *sequence*, and a sequence
		# has no place for a feedback loop: its five loop variables are
		# deliberately absent from it. Counting them out made the summary state
		# 28 derived against 52 exogenous and 3 endogenous, which sums to 83 of
		# the 88 parameters it reports in the same payload. A client cannot
		# reconcile that, and the missing five are exactly the loop variables.
		"derived": len(g.computed()),
		# The middle layer of the spec's §3.4 DAG -- what the optimiser chooses.
		# Reported beside `derived` because the two are the halves of "not
		# settable", and a summary that named only the derived count would leave
		# a reader believing the graph states a decision where it states none.
		# That was the state until this field existed: `Role.ENDOGENOUS` was
		# declared, exported, and carried by no node, so the graph could only
		# say "an equation fixes this" or "you set this" -- and a fleet is
		# neither.
		"endogenous": len(g.endogenous()),
		"endogenous_parameters": list(g.endogenous()),
		"feedback_loops": [str(loop) for loop in g.feedback_loops()],
		"structure_issues": g.structure_issues(),
		# The cross-validation rules the document declares. Reported as a count
		# and their ids, because a summary that listed only the graph's own
		# counts would leave a reader assuming the rules were checked -- and
		# until now a declared rule was silently discarded at load, so the
		# number is new information rather than a restatement.
		"cross_validation_rules": [rule.id for rule in g.rules],
		# The edge strengths the document declares, counted by tier. The spec
		# gives every relationship a strength -- hard, soft, informational --
		# and until now nothing read the field, so a declaration that
		# distinguished a contradiction from a reported correlation was
		# decoration. The register is what makes the tiers visible: a graph
		# whose `soft` count is zero has declared every equation a
		# contradiction, which is a claim about the model and not a default.
		"edge_strength": g.strength_counts(),
		# How much of the graph the what-if engine can be driven from. A
		# summary that reported only the graph's own counts would leave the
		# reader assuming the engine uses all of it; the fraction is the
		# finding, and it is three of fifty-two.
		"engine_translation": translate.coverage(g),
		# The other half of the translation layer, and a different finding: of
		# the six equations that could constrain a solve, two bind and four are
		# post-solve checks. The denominator is the six inequalities, not the
		# 38 equations -- an identity is a definition the graph evaluates, and
		# counting it here would report the register as "2 of 38".
		"constraints": constraints.coverage(g),
		# What the graph declares uncertain, and how far that reaches. The
		# register is the honest substitute for a Monte Carlo the spec never
		# specified: it names the inputs and the reach, and says in the same
		# breath that a sensitivity is a point derivative, not a distribution.
		"uncertainty": uncertainty_register(g),
		# The dimensional check's own coverage. An equation the walker cannot
		# decide is not a pass, so the summary carries the counts rather than a
		# boolean: "31 of 38 consistent" is a fact a reader can weigh, and
		# "consistent" would be a claim the check does not make.
		"units": check_units(g),
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
	# An `informational` equation is a reported correlation, so failing it is a
	# finding rather than a contradiction -- the spec's own reading of the
	# tier. It stays in `violations`, which is the record, and is excluded from
	# `consistent`, which is the gate. A scenario that breaks one is reported
	# and does not fail a check.
	blocking = tuple(v for v in violations if v.blocks)
	# Cross-validation runs on the *propagated* values, not the supplied ones:
	# a rule naming a derived parameter -- "if lcoe > X and tariff < Y" -- is
	# about the computed scenario, and checking it against a set that never
	# carried that parameter would report the rule as undecided.
	rules = g.rules
	return ScenarioCheck(
		consistent=not blocking,
		violations=tuple(violations),
		unmodelled=tuple(coverage(g.equations)),
		excursions=g.range_excursions(),
		cross_validation=g.cross_validate(result.values) if rules else None,
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
			if g.role(name) is Role.ENDOGENOUS:
				# The optimiser chooses it, so "computed by <equation>" would be
				# a false diagnosis and the advice it implies -- set what this
				# depends on -- is advice that cannot be followed.
				by[name] = "the optimisation, not the graph"
				continue
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
	baseline = g.propagate(dict(values))
	scoped = dict(values)
	scoped.update(changes)
	# The delta is propagated incrementally from the baseline: only the closure
	# of the changed knobs is re-derived, and the feedback loop is skipped
	# unless something that changed reaches it. Measured 9x on this graph, and
	# the result agrees with a full propagation to the loop solver's tolerance
	# -- which `tests/ci` asserts rather than assumes.
	result = g.propagate_incremental(scoped, baseline, changes)
	moved = {
		name: result.values[name] - baseline.values[name]
		for name in result.values
		if name in baseline.values
		and abs(result.values[name] - baseline.values[name])
		> 1e-12 * max(abs(result.values[name]), 1.0)
	}
	return {
		"values": result.values,
		"changed": moved,
		"order": list(result.order),
		# `converged` is carried even though a propagation that failed to
		# converge raises rather than returning: a caller reading the payload
		# cannot tell "the loop settled" from "this field was not populated"
		# when the key is simply absent, and the whole point of reporting the
		# iteration at all is that a loop which settled in four turns and one
		# that needed 180 are different findings.
		"loops": [
			{
				"loop": lr.loop,
				"iterations": lr.iterations,
				"change": lr.change,
				"converged": lr.converged,
			}
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


class EquationRow(NamedTuple):
	"""One equation as a report line: identity, system, rendering, citation.

	A ``NamedTuple`` rather than a fourth element on the tuple this function
	used to return. Three callers unpack it positionally, and a four-element
	plain tuple would have made every one of them raise ``ValueError: too many
	values to unpack`` -- loud, which is the good failure, but it is also the
	reason the field could not simply be appended: a caller that *ignored* the
	extra element by slicing (``row[:3]``) would have dropped the citation in
	silence, and a citation nothing reads is the defect this field exists to
	close. Named access also means a consumer added later cannot confuse the
	rendering for the reference by position.
	"""

	equation_id: str
	system: str
	rendered: str
	reference: str | None = None
	"""The equation's declared citation, or ``None`` when it declares none.

	Carried as ``None`` rather than an empty string because the two are
	different findings: nine of the thirty-nine equations cite a source, and a
	report that rendered the other thirty with a blank citation column would
	read as thirty missing citations rather than thirty equations whose
	provenance is the document itself.
	"""


def equation_report(
	graph: ParameterGraph | None = None,
	*,
	as_: str = "unicode",
	system: str | None = None,
) -> list[EquationRow]:
	"""Every equation as an :class:`EquationRow`, for a report or a listing.

	The citation is carried because the graph declares one on nine equations
	and, until this field existed, nothing read it: ``reference`` was parsed,
	validated and reachable from no door, so a reader of the equation library
	could not see that ``lcoe_definition`` cites IEA/NEA while
	``tariff_cost_recovery`` cites average-cost pricing. A declared field with
	no reader is the recurring defect in this tree, and the fix is a reader --
	this one.
	"""
	g = _graph(graph)
	by_system = systems_of(g.equations)
	out: list[EquationRow] = []
	for system_id, equations in by_system.items():
		if system is not None and system_id != system:
			continue
		for equation in equations:
			out.append(
				EquationRow(
					equation.id,
					system_id,
					describe(equation, as_=as_),
					equation.reference,
				)
			)
	return out
