# SPDX-License-Identifier: MIT
"""The Parameter Relationship Graph: load, validate, order, propagate.

WHY the graph owns the topological order and the propagation together. A
determined parameter is computed from the parameters it depends on, so the
order it is computed in *is* the propagation. Splitting them into a
``topological`` module and a ``propagation`` module -- as the specification's
tree does -- means the sort and the walk can disagree about which edge is a
dependency, and the symptom of that disagreement is a derived parameter
computed from a stale value: a number that is wrong and plausible.

WHY a cycle is an error here and a solver there. The graph refuses a cycle among
*determined* parameters, because a derivation cycle has no order and therefore
no answer. The specification's fifteen feedback loops are a different object:
they are cycles among parameters where each turn of the loop re-evaluates an
equation against the previous turn's values. Those are not edges in this
graph's derived subgraph -- they are :class:`alea.prg.feedback.FeedbackLoop`
objects with a convergence criterion, and the distinction is what stops a
non-converging loop from being mistaken for a malformed graph.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pathlib import Path
from typing import Any

import yaml

from alea.config.paths import repo_root
from alea.prg.crossval import (
	CrossValidationReport,
	CrossValidationRule,
	rules_from_document,
)
from alea.prg.dsl import DslError, Expr, evaluate, parse, solve_for
from alea.prg.feedback import solve_loop
from alea.prg.views import (
	Equation,
	ParameterNode,
	RelationshipEdge,
	Role,
)

__all__ = [
	"CycleError",
	"GraphError",
	"ParameterGraph",
	"PropagationResult",
	"Violation",
	"default_prg_path",
	"load_graph",
]


class GraphError(ValueError):
	"""The graph is malformed: an edge or equation names what does not exist."""


class CycleError(GraphError):
	"""The derived subgraph has a cycle, so it has no evaluation order."""


@dataclass(frozen=True)
class Violation:
	"""One equation that does not hold at the current parameter values.

	``strength`` is the edge's, carried here so the *consumer* can decide what a
	failure costs. It is not a property of the arithmetic -- the residual is the
	residual -- but of the claim the equation was declared to make. An
	``informational`` equation is a reported correlation; failing it is a
	finding, not a contradiction, and a check that treated the two alike would
	gate on a number it was never asked to enforce.
	"""

	equation_id: str
	residual: float
	tolerance: float
	relative: float
	priority: str
	strength: str = "hard"

	@property
	def blocks(self) -> bool:
		"""Whether this failure contradicts the scenario rather than advising.

		Read from ``strength``, and the default is ``hard`` because a violation
		with no declared edge to read is one nothing softened.
		"""
		return self.strength != "informational"

	def __str__(self) -> str:
		tier = "" if self.strength == "hard" else f" [{self.strength}]"
		return (
			f"{self.equation_id} ({self.priority}{tier}): residual "
			f"{self.residual:.6g}, relative {self.relative:.3g} > tolerance "
			f"{self.tolerance:.3g}"
		)


@dataclass(frozen=True)
class PropagationResult:
	"""What a change did to the graph.

	``values`` is a fresh dict per propagation and no caller shares it with the
	graph, so mutating it is safe -- but it is a plain dict and not a mapping
	proxy, and it is not a *record*: the graph holds no reference to it, and
	re-running ``propagate`` recomputes from the input rather than from this.
	"""

	values: dict[str, float]
	changed: dict[str, float]
	"""Parameters whose value moved, and by how much.

	Includes the loop variables. A fixed point that moved is a change, and the
	"before" for one the caller did not supply is the seed the solver started
	from -- the same rule, read from :meth:`ParameterGraph._loop_seed`.
	"""

	order: tuple[str, ...]
	"""The derived parameters, in the order they were computed."""

	loops: tuple[Any, ...] = ()
	"""The feedback loops solved, with their iteration counts."""


def default_prg_path() -> Path:
	return repo_root() / "config" / "prg.yaml"


class ParameterGraph:
	"""An immutable graph over parameter nodes, equations and edges."""

	def __init__(
		self,
		nodes: Mapping[str, ParameterNode],
		equations: Mapping[str, Equation],
		edges: Iterable[RelationshipEdge],
		*,
		declared: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] | None = None,
		rules: Iterable[CrossValidationRule] = (),
	) -> None:
		self._nodes = dict(nodes)
		self._equations = dict(equations)
		self._edges = tuple(edges)
		#: The `depends_on` / `affects` lists the YAML declared, kept only so
		#: `structure_issues` can compare them against the edges. They are not
		#: the graph; the edges are.
		self._declared = dict(declared or {})
		#: The cross-validation rules the document declared, parsed once at
		#: load. Unlike the declared lists above, these are not a second record
		#: of something the edges say -- a rule relates parameters no equation
		#: couples, so nothing else in the graph can supply it.
		self._rules = tuple(rules)

		self._by_source: dict[str, list[RelationshipEdge]] = defaultdict(list)
		self._by_target: dict[str, list[RelationshipEdge]] = defaultdict(list)
		for edge in self._edges:
			self._by_source[edge.source].append(edge)
			self._by_target[edge.target].append(edge)

		#: equation id -> the strength the edges citing it declare.
		#:
		#: Every equation is cited by at least one edge, and the strength is a
		#: property of the *relationship* rather than of the arithmetic -- the
		#: same equation reached by a `hard` edge and by an `informational` one
		#: would mean two things. The graph refuses that rather than picking
		#: one: a strength that depends on which edge a caller happened to read
		#: is not a declared property. Checked at construction, so a document
		#: that disagrees with itself is a load error.
		self._strength: dict[str, str] = {}
		for edge in self._edges:
			declared_strength = self._strength.setdefault(
				edge.equation_id, edge.strength.value
			)
			if declared_strength != edge.strength.value:
				raise GraphError(
					f"{edge.equation_id!r} is cited by edges of two strengths "
					f"({declared_strength!r} and {edge.strength.value!r}); the "
					f"strength is a property of the equation and a reader taking "
					f"it from an edge would get whichever edge they read first"
				)

		#: equation id -> the equation, for a derived parameter. Built once.
		self._loop_variables: set[str] = {
			equation.determined_variables[0]
			for equation in self._equations.values()
			if equation.solution_method == "iterative" and equation.determined_variables
		}

		self._determiner: dict[str, Equation] = {}
		for equation in self._equations.values():
			if equation.solution_method == "iterative":
				# A loop, not a derivation. Its variable is a fixed point, and
				# the topological order has no place to put it -- which is the
				# whole reason the feedback solver exists.
				continue
			for target in equation.determined_variables:
				if target in self._determiner:
					raise GraphError(
						f"{target} is determined by both "
						f"{self._determiner[target].id!r} and {equation.id!r}; "
						f"two equations fixing one parameter is an "
						f"over-determined system, and the engine would pick one "
						f"by dictionary order"
					)
				self._determiner[target] = equation

		#: parameter -> the value the equation fixes, where that value is
		#: outside the parameter's declared range. Cleared at the top of every
		#: propagation: a finding left over from the previous scenario would be
		#: reported against this one, which is the stale-state bug the register
		#: exists to avoid rather than to commit.
		self._range_excursions: dict[str, float] = {}

		#: Memoised per-instance results. Declared here rather than via
		#: ``lru_cache`` on the methods, which would key the cache on ``self`` in
		#: a class-level table and keep every graph alive.
		self._loops_cache: tuple[Any, ...] | None = None
		self._phases_cache: tuple[tuple[str, ...], tuple[str, ...]] | None = None

		self._validate()

	# -- construction ---------------------------------------------------

	@classmethod
	def from_mapping(cls, document: Mapping[str, Any]) -> ParameterGraph:
		"""Build from the parsed contents of ``prg.yaml``."""
		raw_nodes = document.get("parameters") or {}
		raw_equations = document.get("equations") or {}
		raw_edges = document.get("relationships") or []
		if not raw_nodes:
			raise GraphError("the PRG document declares no parameters")
		if not raw_equations:
			raise GraphError(
				"the PRG document declares no equations; a graph of parameters "
				"with no relationships is a list, and every consistency check "
				"over it passes vacuously"
			)

		nodes: dict[str, ParameterNode] = {}
		declared: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
		for key, body in raw_nodes.items():
			payload = dict(body or {})
			payload.setdefault("id", key)
			if payload["id"] != key:
				raise GraphError(
					f"parameter {key!r} declares id {payload['id']!r}; the key is "
					f"the identity and a second spelling of it is a node two "
					f"readers will look for in two places"
				)
			# A list the file does not carry is not a declaration of `[]`:
			# comparing against it reports the whole graph as drifted.
			if "depends_on" in payload or "affects" in payload:
				declared[key] = (
					tuple(payload.pop("depends_on", ()) or ()),
					tuple(payload.pop("affects", ()) or ()),
				)
			payload.pop("depends_on", None)
			payload.pop("affects", None)
			# `equations` on the node is likewise a second record of what the
			# equation objects already say. Read it, check it, drop it.
			payload.pop("equations", None)
			# `validation_rules` is §19's per-parameter value rules -- "value
			# >= 0", "value <= 500" -- which are what `range` already states,
			# and the node model enforces `range` on every load. Dropping the
			# text loses nothing the graph does not already check; a rule that
			# is *not* expressible as a range would need a home, and none is
			# declared.
			payload.pop("validation_rules", None)
			# `cross_validation` is §25's multi-parameter rules, and it is NOT
			# a second record of anything: a rule relates parameters no
			# equation couples. It was popped here and discarded, which made a
			# declared rule a comment. It is read below, by
			# `rules_from_document`, from the raw document.
			payload.pop("cross_validation", None)
			nodes[key] = ParameterNode(**payload)

		equations: dict[str, Equation] = {}
		for key, body in raw_equations.items():
			payload = dict(body or {})
			payload.setdefault("id", key)
			equations[key] = Equation(**payload)

		edges = [RelationshipEdge(**edge) for edge in raw_edges]
		# Parsed here, at load, so a rule outside the condition grammar is a
		# load error rather than a surprise inside a check -- and so a rule
		# naming a parameter the graph does not hold is refused before a
		# scenario is ever validated against it.
		try:
			rules = rules_from_document(document)
		except DslError as exc:
			raise GraphError(f"cross-validation: {exc}") from exc
		return cls(nodes, equations, edges, declared=declared, rules=rules)

	@classmethod
	def from_yaml(cls, path: str | Path) -> ParameterGraph:
		text = Path(path).read_text()
		document = yaml.safe_load(text)
		if not isinstance(document, dict):
			raise GraphError(f"{path} does not hold a mapping at the top level")
		return cls.from_mapping(document)

	# -- accessors ------------------------------------------------------

	@property
	def nodes(self) -> dict[str, ParameterNode]:
		return dict(self._nodes)

	@property
	def equations(self) -> dict[str, Equation]:
		return dict(self._equations)

	@property
	def edges(self) -> tuple[RelationshipEdge, ...]:
		return self._edges

	@property
	def rules(self) -> tuple[CrossValidationRule, ...]:
		"""The cross-validation rules the document declared.

		Read off the graph rather than re-parsed per call, so the rule a report
		names is the rule that was validated at load. A caller that re-read the
		YAML would be checking a document that may have changed since.
		"""
		return self._rules

	def strength_of(self, equation_id: str) -> str:
		"""The strength the edges citing ``equation_id`` declare.

		``hard`` for an equation no edge cites, which is the conservative
		reading: an equation with no declared relationship behind it was not
		softened by anything.
		"""
		return self._strength.get(equation_id, "hard")

	def strength_counts(self) -> dict[str, int]:
		"""How many *equations* each strength tier covers.

		Counted by equation rather than by edge because the strength is a
		property of the equation once loaded -- the constructor refuses a
		document whose edges disagree about one. The register the summary
		carries, and the useful fact is the *shape*: a graph with no ``soft``
		equations has declared every relationship a contradiction, and one with
		no ``hard`` equations has declared none of them load-bearing.
		"""
		counts: dict[str, int] = {}
		for strength in self._strength.values():
			counts[strength] = counts.get(strength, 0) + 1
		return dict(sorted(counts.items()))

	def node(self, parameter: str) -> ParameterNode:
		try:
			return self._nodes[parameter]
		except KeyError as exc:
			raise GraphError(f"no parameter {parameter!r} in the graph") from exc

	def equation(self, equation_id: str) -> Equation:
		try:
			return self._equations[equation_id]
		except KeyError as exc:
			raise GraphError(f"no equation {equation_id!r} in the graph") from exc

	def is_settable(self, parameter: str) -> bool:
		"""Whether a user may set this parameter.

		False for a derived parameter and for a loop variable. This is the
		question the whole graph exists to answer: a user who sets a carbon
		price *and* the emissions it determines has set two coupled parameters
		independently, and the only correct response is to refuse rather than to
		pick one and recompute the other in silence.
		"""
		return (
			parameter not in self._determiner
			and parameter not in self._loop_variables
		)

	def edges_from(self, parameter: str) -> tuple[RelationshipEdge, ...]:
		"""The edges this parameter is the source of.

		The declared direction, not the arithmetic. ``affects`` answers "whose
		value moves"; this answers "what the graph says this feeds", which is
		the question a reader of a diagram is asking and the one the edge set
		was written to state.
		"""
		return tuple(self._by_source.get(parameter, ()))

	def edges_into(self, parameter: str) -> tuple[RelationshipEdge, ...]:
		"""The edges this parameter is the target of."""
		return tuple(self._by_target.get(parameter, ()))

	def constrains(self, parameter: str) -> tuple[str, ...]:
		"""The inequalities this parameter bounds, by equation id.

		A third relation, and it is not `affects`. Moving ``energy_burden_limit``
		changes no parameter's *value* -- ``energy_burden`` is what it is -- but
		it changes whether the scenario is admissible, which is the whole
		question for a regulator's lever. Folding it into `affects` would make
		that method mean two different things, and a caller reading "affects"
		to mean "moves the number" would be misled by the union.

		An inequality's edge set does not answer this: the edges are positional
		(the ``rhs`` computed into the ``lhs`` slot), so ``dscr_requirement``
		carries an edge from ``dscr_min`` to ``project_gearing_dscr`` even
		though ``dscr_min`` determines nothing. Reading the equation is what is
		true here.
		"""
		out: set[str] = set()
		for equation in self._equations.values():
			if equation.relation == "eq":
				continue
			if parameter in set(equation.parameters) | set(equation.free_variables):
				out.add(equation.id)
		return tuple(sorted(out))

	def computed(self) -> frozenset[str]:
		"""Every parameter the graph computes rather than accepts."""
		return frozenset(self._determiner) | self._loop_variables

	def determined_by(self, parameter: str) -> Equation | None:
		return self._determiner.get(parameter)

	def feedback_loops(self) -> tuple[Any, ...]:
		"""The loops the topological order cannot evaluate.

		Memoised on the instance, not with ``lru_cache``. A method decorator
		caches on ``self`` in a *class-level* table, so every graph ever built
		stays alive for as long as the cache holds it -- an instance-retention
		leak that a short-lived-graph workload turns into unbounded memory. The
		attribute cache dies with the graph, which is the lifetime the value
		has.
		"""
		if self._loops_cache is None:
			from alea.prg.feedback import detect_loops

			self._loops_cache = tuple(detect_loops(self))
		return self._loops_cache

	def depends_on(self, parameter: str) -> tuple[str, ...]:
		"""Parameters this one is computed from, by the determining equation.

		Derived from the *determining equation*, not from the declared
		``depends_on`` list and not from the edges. The edges carry a
		relationship and its direction; the equation carries the arithmetic, and
		the arithmetic is what propagation must follow.

		Deliberately excludes the loop equations, and that is not the blind spot
		:meth:`affects` had. ``order`` and ``_phases`` walk this to build a
		topological sequence, and a loop has no place in one -- the fixed point
		is solved separately and the parameters that wait on it are computed
		after. A loop variable therefore reports ``()`` here and its inputs are
		readable from the loop itself (:meth:`feedback_loops`). Reading the loop
		equations in would put a cycle back into the sort that exists to exclude
		it.
		"""
		equation = self._determiner.get(parameter)
		if equation is None:
			return ()
		others = set(equation.parameters) | set(equation.free_variables)
		return tuple(sorted(others - {parameter}))

	def affects(self, parameter: str) -> tuple[str, ...]:
		"""Parameters whose *value* this one moves, by the equations.

		Every equation that fixes a value, including the iterative ones. The
		determining equations alone are not enough: ``_determiner`` skips the
		loop equations -- that is what makes them loops -- so reading only it
		dropped ``capture_price_sensitivity`` and ``vre_capacity_target_mw``,
		both of which change what the fixed point settles at.

		Inequalities are deliberately *not* read here. They fix no value, so a
		parameter appearing in one moves no number; it changes whether the
		scenario is admissible, which is :meth:`constrains`. Folding the two
		together would make this method mean "moves the number or gates the
		scenario", and a caller who reads ``affects`` as "moves the number"
		would be misled. The declared relationships are on :meth:`edges_from`.
		"""
		out: set[str] = set()
		for equation in self._equations.values():
			if parameter not in set(equation.parameters) | set(
				equation.free_variables
			):
				continue
			out |= set(equation.determined_variables)
		out.discard(parameter)
		return tuple(sorted(out))

	def affected_by(self, parameters: Iterable[str]) -> tuple[str, ...]:
		"""Everything the values of ``parameters`` reach, transitively.

		:meth:`affects` is one hop, deliberately: it answers "which equations
		does this parameter appear in". A caller asking "what does changing
		this move" needs the closure, and computing it by hand is where the
		mistakes are -- the specification's incremental propagator marks dirty
		with ``networkx.descendants`` over the *declared* edge set, which is a
		different relation and disagrees with this one on 27 of the graph's 53
		settable parameters, missing members in both directions.

		It is not a closure over :meth:`depends_on` for the same reason
		:mod:`alea.prg.uncertainty` is not: ``depends_on`` skips the loop
		equations, so a walk over it stops at a feedback loop and omits
		everything downstream of the fixed point. ``affects`` includes them.

		A parameter already in ``parameters`` is not reported as affected by
		itself -- the caller knows what it set -- but it is still walked
		through, so its dependents are.
		"""
		assert parameters is not None, "affected_by needs parameters"
		seeds = set(parameters)
		reachable: set[str] = set()
		frontier = list(seeds)
		while frontier:
			current = frontier.pop()
			for dependent in self.affects(current):
				if dependent in reachable:
					continue
				reachable.add(dependent)
				frontier.append(dependent)
		return tuple(sorted(reachable - seeds))

	# -- validation -----------------------------------------------------

	def _validate(self) -> None:
		for edge in self._edges:
			if edge.source not in self._nodes:
				raise GraphError(
					f"edge {edge.source} -> {edge.target} names a source that is "
					f"not a parameter"
				)
			if edge.target not in self._nodes:
				raise GraphError(
					f"edge {edge.source} -> {edge.target} names a target that is "
					f"not a parameter"
				)
			if edge.equation_id not in self._equations:
				raise GraphError(
					f"edge {edge.source} -> {edge.target} cites equation "
					f"{edge.equation_id!r}, which the library does not hold"
				)

		for equation in self._equations.values():
			unknown = (set(equation.parameters) | set(equation.free_variables)) - set(
				self._nodes
			)
			if unknown:
				raise GraphError(
					f"equation {equation.id!r} names {sorted(unknown)}, which are "
					f"not parameters"
				)
			unknown_targets = set(equation.determined_variables) - set(self._nodes)
			if unknown_targets:
				raise GraphError(
					f"equation {equation.id!r} determines {sorted(unknown_targets)}, "
					f"which are not parameters"
				)
			# The arithmetic must name what the metadata claims, or the metadata
			# is decoration. Parsing here means a malformed equation is a load
			# error rather than a surprise inside a solve.
			try:
				named = parse(equation.lhs).symbols | parse(equation.rhs).symbols
			except DslError as exc:
				raise GraphError(f"equation {equation.id!r}: {exc}") from exc
			claimed = set(equation.parameters) | set(equation.free_variables) | set(
				equation.determined_variables
			)
			unnamed = named - claimed
			if unnamed:
				raise GraphError(
					f"equation {equation.id!r} uses {sorted(unnamed)} in its "
					f"arithmetic but does not list them in `parameters`, so the "
					f"graph cannot say which parameters it couples"
				)
			unused = claimed - named
			if unused:
				raise GraphError(
					f"equation {equation.id!r} lists {sorted(unused)} but its "
					f"arithmetic does not name them; a declared parameter that "
					f"does not appear is a coupling the graph would report and "
					f"the engine would never apply"
				)

		# An equation's `system` must name a system the library holds. Checked
		# here rather than where the system is first *read*: `systems_of` raises
		# too, but only when something asks it to group the equations, so a
		# graph with a misspelt system loaded cleanly and failed later inside an
		# unrelated report. A load error belongs at load.
		from alea.prg.library import SYSTEM_IDS

		for equation in self._equations.values():
			if equation.system not in SYSTEM_IDS:
				raise GraphError(
					f"equation {equation.id!r} names system {equation.system!r}, "
					f"which the library does not hold; known systems: "
					f"{sorted(SYSTEM_IDS)}"
				)

		for target in self._determiner:
			node = self._nodes[target]
			if node.role is not Role.DERIVED:
				raise GraphError(
					f"{target} is determined by "
					f"{self._determiner[target].id!r} but its role is "
					f"{node.role.value!r}; a parameter an equation fixes is "
					f"`derived`, and any other role lets a user set it and be "
					f"silently overruled"
				)

		# A rule naming a parameter the graph does not hold can never be
		# evaluated, so it is a rule that would report nothing forever while
		# reading as a check. Refused at load, for the same reason a misspelt
		# equation system is: a load error belongs at load.
		for rule in self._rules:
			unknown = rule.parameters - set(self._nodes)
			if unknown:
				raise GraphError(
					f"cross-validation rule {rule.id!r} names {sorted(unknown)}, "
					f"which are not parameters; a rule that can never be "
					f"evaluated is a check that never runs"
				)

	def structure_issues(self) -> list[str]:
		"""Disagreements between what the YAML declares and what the edges say.

		Not fatal -- the edges win, and propagation never reads the declared
		lists -- but reported, because a declared list that has drifted is a
		document that lies about the graph a reader is trying to understand.
		"""
		issues: list[str] = []
		for parameter, (depends, affects) in sorted(self._declared.items()):
			derived_depends = set(self.depends_on(parameter))
			derived_affects = set(self.affects(parameter))
			if set(depends) != derived_depends:
				issues.append(
					f"{parameter}.depends_on declares {sorted(depends)} but the "
					f"equations say {sorted(derived_depends)}"
				)
			if set(affects) != derived_affects:
				issues.append(
					f"{parameter}.affects declares {sorted(affects)} but the "
					f"equations say {sorted(derived_affects)}"
				)
		for parameter in sorted(set(self._determiner) | self._loop_variables):
			if self._nodes[parameter].range is None:
				issues.append(
					f"{parameter} is derived but declares no range; a derivation "
					f"is solved numerically and a solver without bounds finds "
					f"whichever root it meets first"
				)
		return issues

	# -- ordering -------------------------------------------------------

	def _phases(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
		"""The derived parameters, split by whether they follow a feedback loop.

		A parameter computed from a loop variable cannot be computed before the
		loop is solved, and the loop has no place in a topological order. So the
		order is cut in two: what is computable from the exogenous inputs alone,
		and what waits on the fixed point. ``propagate`` runs them either side
		of the solver, and a parameter in the wrong half would be computed from
		a pre-loop value.

		Memoised on the instance for the same reason as :meth:`feedback_loops`.
		"""
		if self._phases_cache is not None:
			return self._phases_cache
		ordered = self.order()
		waiting: set[str] = set()
		changed = True
		while changed:
			changed = False
			for parameter in ordered:
				if parameter in waiting:
					continue
				for dependency in self.depends_on(parameter):
					if dependency in self._loop_variables or dependency in waiting:
						waiting.add(parameter)
						changed = True
						break
		before = tuple(p for p in ordered if p not in waiting)
		after = tuple(p for p in ordered if p in waiting)
		self._phases_cache = (before, after)
		return self._phases_cache

	def order(self) -> tuple[str, ...]:
		"""Derived parameters in an order where each follows its inputs.

		Kahn's algorithm. A cycle is reported with its members rather than as
		"the graph has a cycle": the members are the finding, and naming them is
		the difference between a message someone can act on and one they cannot.
		"""
		derived = sorted(self._determiner)
		deps = {
			parameter: tuple(
				d for d in self.depends_on(parameter) if d in self._determiner
			)
			for parameter in derived
		}
		remaining = {parameter: set(deps[parameter]) for parameter in derived}
		ready = deque(p for p in derived if not remaining[p])
		out: list[str] = []
		while ready:
			parameter = ready.popleft()
			out.append(parameter)
			for candidate in derived:
				if parameter in remaining[candidate]:
					remaining[candidate].discard(parameter)
					if not remaining[candidate]:
						ready.append(candidate)
		if len(out) != len(derived):
			cyclic = sorted(p for p in derived if p not in set(out))
			raise CycleError(
				f"the derived parameters {cyclic} form a cycle and have no "
				f"evaluation order; if this is a feedback loop it belongs in the "
				f"feedback solver, where each turn re-evaluates against the "
				f"previous one"
			)
		return tuple(out)

	# -- propagation ----------------------------------------------------

	def propagate(
		self,
		values: Mapping[str, float],
		changed: Iterable[str] | None = None,
	) -> PropagationResult:
		"""Recompute every derived parameter from ``values``.

		``changed`` names the parameters the caller just set. It does not change
		the arithmetic -- every derived parameter is recomputed -- but it lets
		the result report *what moved*, which is what a user who edited one
		knob wants to see.

		A caller holding a previous result and a delta should reach for
		:meth:`propagate_incremental` instead: it recomputes the closure of what
		changed rather than the whole graph, which is 9x on this graph. This
		method stays the reference -- the one whose answer is checked against
		the incremental path, and the one to use when there is no previous
		result to build on.
		"""
		if changed is not None:
			unknown = set(changed) - set(self._nodes)
			if unknown:
				raise GraphError(
					f"propagate was told {sorted(unknown)} changed, which are not "
					f"parameters; a caller naming a parameter the graph does not "
					f"hold is a caller editing a different graph"
				)
		self._range_excursions.clear()
		scoped: dict[str, float] = {k: float(v) for k, v in values.items()}
		missing = set(self._nodes) - scoped.keys()
		underived_missing = {
			name
			for name in missing
			if name not in self._determiner and name not in self._loop_variables
		}
		if underived_missing:
			raise GraphError(
				f"the parameter set is missing {sorted(underived_missing)}; a "
				f"parameter that is not derived has no equation to compute it "
				f"from"
			)

		before = dict(scoped)
		computable, waits_on_loop = self._phases()
		for parameter in computable:
			scoped[parameter] = self._derive(parameter, scoped)

		# A loop's inputs may themselves be derived, so the loops are solved
		# after the first pass and the parameters that depend on the fixed
		# point are derived after them.
		loop_results = [solve_loop(self, loop, scoped) for loop in self.feedback_loops()]
		for parameter in waits_on_loop:
			scoped[parameter] = self._derive(parameter, scoped)

		computed = set(self._determiner) | self._loop_variables
		moved: dict[str, float] = {}
		for name, value in scoped.items():
			if name not in computed:
				continue
			# A loop variable has no value in `before` unless the caller
			# supplied one: `solve_loop` seeds it from the node's `initial` or
			# the midpoint of its range. Reading `before` alone therefore
			# dropped every loop variable from the report -- a caller asking
			# what a knob moved was not told the fixed point had moved at all.
			# The seed is the honest "before" for an iterated value.
			start = before.get(name)
			if start is None:
				start = self._loop_seed(name)
			if start is None:
				continue
			# Relative, so a solver's last-bit noise on a 2700 MW capacity is
			# not reported as a change. An absolute floor would call the same
			# noise a change on a capacity factor and not on a capacity.
			if abs(value - start) > 1e-12 * max(abs(value), 1.0):
				moved[name] = value - start
		return PropagationResult(
			values=scoped,
			changed=moved,
			order=self.order(),
			loops=tuple(loop_results),
		)

	def propagate_incremental(
		self,
		values: Mapping[str, float],
		previous: PropagationResult,
		changed: Iterable[str],
	) -> PropagationResult:
		"""Recompute only what ``changed`` reaches, reusing ``previous``.

		``propagate`` re-derives every determiner and re-solves every feedback
		loop, and the loop solver is two thirds of its cost: 1400 derivations
		per call on this graph, 7100 root-finds across fifty calls. A caller
		editing one knob pays for the whole graph. This recomputes the closure
		of what moved -- and skips a feedback loop entirely when nothing in the
		changed set reaches any of its members, which is where the saving is.

		WHY this is a separate method and not a cache. The docstring on
		:meth:`propagate` says "determining which are unaffected requires the
		same topological walk", and that is false: the walk is a 10-microsecond
		closure against a 4.2-millisecond full propagation, four hundred times
		cheaper. The claim was never measured. It is also the reason this takes
		``previous`` as an argument rather than holding a cache: a cached result
		keyed on values is a second source of truth that goes stale the moment
		the graph or the file changes, and the defect this module exists to
		prevent is a value that silently stands in for the equation. The caller
		holds the previous result and is responsible for knowing it is current.

		The arithmetic is identical to :meth:`propagate` -- the same determiner
		equations, the same loop solver, the same order -- so the result agrees
		with a full propagation to the loop solver's own tolerance. It is *not*
		bit-identical for a parameter downstream of a feedback loop, and the
		reason is worth stating: the solver starts from the values it is handed,
		so a warm start converges to the same fixed point within ``tolerance``
		rather than to the last bit the cold start happened to stop at. The
		measured worst case on this graph is 1.1e-8 relative, against a declared
		tolerance of 1e-8. ``tests/ci`` asserts agreement at that scale rather
		than at exactness, because a test demanding exactness here would be
		asserting something false about an iterative solver.
		"""
		assert previous is not None, "propagate_incremental needs the previous result"
		seeds = set(changed)
		unknown = seeds - set(self._nodes)
		if unknown:
			raise GraphError(
				f"propagate_incremental was told {sorted(unknown)} changed, which "
				f"are not parameters"
			)
		self._range_excursions.clear()
		# The previous result carries every derived value, and the caller's
		# `values` need only name what it set -- the same sparse contract
		# `propagate` accepts. Seeding from `previous` first is what lets an
		# undirtied derived parameter keep its value instead of going missing:
		# a caller who passes only the knobs they edited would otherwise leave
		# every carried-over parameter absent, and the next derivation that
		# reads one would fail on a parameter set that is complete in fact.
		scoped: dict[str, float] = {k: float(v) for k, v in previous.values.items()}
		scoped.update({k: float(v) for k, v in values.items()})
		before = dict(scoped)
		dirty = set(self.affected_by(seeds))

		computable, waits_on_loop = self._phases()
		for parameter in computable:
			if parameter in dirty:
				scoped[parameter] = self._derive(parameter, scoped)

		# A loop is skipped when nothing that changed reaches any of its
		# members: its fixed point is a function of its inputs, and if none of
		# them moved the fixed point did not either. Its members are then
		# carried over from the previous result, which is why that argument is
		# required rather than optional.
		loop_results = []
		for loop in self.feedback_loops():
			members = set(loop.variables)
			if members & dirty or members & seeds:
				loop_results.append(solve_loop(self, loop, scoped))
				continue
			for member in members:
				if member in previous.values:
					scoped[member] = previous.values[member]
			loop_results.append(None)
		for parameter in waits_on_loop:
			if parameter in dirty:
				scoped[parameter] = self._derive(parameter, scoped)

		computed = set(self._determiner) | set(self._loop_variables)
		moved: dict[str, float] = {}
		for name in computed:
			if name not in scoped:
				continue
			value = scoped[name]
			start = before.get(name)
			if start is None:
				start = previous.values.get(name)
			if start is None:
				start = self._loop_seed(name)
			if start is None:
				continue
			if abs(value - start) > 1e-12 * max(abs(value), 1.0):
				moved[name] = value - start
		return PropagationResult(
			values=scoped,
			changed=moved,
			order=self.order(),
			loops=tuple(r for r in loop_results if r is not None),
		)

	def _widen(
		self,
		residual: Expr,
		parameter: str,
		values: Mapping[str, float],
		bracket: tuple[float, float],
	) -> float | None:
		"""The equation's root, searching past ``bracket`` until it is found.

		Geometric widening outward from the declared range, doubling the
		half-width each turn: the cheapest way to reach a value off by orders of
		magnitude without stepping so far in one move that an intervening root
		is skipped.

		The guarantee is *a* root outside the admissible set, not necessarily
		the one nearest to it, and the difference matters for a non-monotonic
		equation -- a learning curve or a cannibalisation term with two roots
		can return the far one. For the equations in this library the residual
		is monotonic in the parameter it is solved for, so the first root found
		is the only one; an equation that is not must declare a bracket wide
		enough to contain its root rather than relying on this search. The
		excursion is recorded in ``_range_excursions`` either way, so a value
		fixed outside its declared range is a reported finding and not a silent
		one.
		"""
		low, high = bracket
		width = max(high - low, 1.0)
		for _ in range(32):
			low -= width
			high += width
			width *= 2.0
			try:
				return solve_for(residual, parameter, values, bracket=(low, high))
			except DslError:
				continue
		return None

	def _loop_seed(self, parameter: str) -> float | None:
		"""Where the solver starts ``parameter`` if the caller did not set it.

		The same rule :func:`alea.prg.feedback.solve_loop` applies, written once
		here so the "before" a propagation reports against is the iterate the
		solver actually began from. A second spelling of the rule would let the
		reported change and the solved change disagree by exactly the seed.
		"""
		node = self._nodes.get(parameter)
		if node is None:
			return None
		if node.initial is not None:
			return float(node.initial)
		if node.range is not None:
			low, high = node.range
			return 0.5 * (low + high)
		return None

	def _derive(self, parameter: str, values: Mapping[str, float]) -> float:
		equation = self._determiner[parameter]
		if equation.relation != "eq":
			raise GraphError(
				f"{parameter} is determined by {equation.id!r}, which is an "
				f"inequality; an inequality bounds a value and cannot fix one"
			)
		residual = parse(f"({equation.lhs}) - ({equation.rhs})")
		node = self.node(parameter)
		if node.range is None:
			raise GraphError(
				f"{parameter} is derived but declares no range, so the solver "
				f"has no bracket; declare the physical range on the node"
			)
		try:
			return solve_for(residual, parameter, values, bracket=node.range)
		except DslError as first:
			# A bracket miss is not the same thing as an unsolvable equation,
			# and conflating them turns a scenario that should be *reported*
			# into a traceback. `range` is the set the parameter is admissible
			# over; the solver's bracket is where the root might be. For a
			# ratio those are different sets -- a debt service coverage of 30 is
			# perfectly computable and outside any range a reviewer would sign
			# off -- so the bracket is widened until the root is found, and the
			# excursion is recorded as the finding it is. A bracket that still
			# has no root after widening is a genuinely unsolvable equation,
			# and that is an error.
			widened = self._widen(residual, parameter, values, node.range)
			if widened is None:
				raise GraphError(
					f"cannot derive {parameter} from {equation.id!r}: {first}"
				) from first
			self._range_excursions[parameter] = widened
			return widened

	# -- consistency ----------------------------------------------------

	def range_excursions(self) -> dict[str, float]:
		"""Derived parameters whose equation fixed a value outside their range.

		Read after a propagation. A value here is not a solver failure -- the
		equation was solved and this is its answer -- it is the answer landing
		outside the set the parameter is admissible over, which is a finding
		about the scenario.
		"""
		return dict(self._range_excursions)

	def consistency(
		self, values: Mapping[str, float], *, only: str | None = None
	) -> list[Violation]:
		"""Every equation that does not hold at ``values``.

		The residual is scaled by the magnitudes it relates before it is
		compared to the tolerance. An absolute tolerance cannot be right for a
		library whose equations relate a carbon price in USD/tonne to a cost in
		USD and a capacity factor in ``[0, 1]``: the same tolerance is
		impossibly tight for the first and infinitely loose for the second.
		"""
		violations: list[Violation] = []
		for parameter, value in sorted(self._range_excursions.items()):
			node = self._nodes[parameter]
			assert node.range is not None, parameter
			violations.append(
				Violation(
					equation_id=f"{parameter}_out_of_range",
					residual=value,
					tolerance=node.range[1] if value > node.range[1] else node.range[0],
					relative=float("inf"),
					priority=node.priority.value,
				)
			)
		for equation in self._equations.values():
			if only is not None and equation.system != only:
				continue
			strength = self._strength.get(equation.id, "hard")
			if equation.relation != "eq":
				# An inequality is a boundary. Reporting its residual as a
				# violation would flag a parameter sitting correctly inside its
				# bound, so the sign is what matters, not the magnitude.
				if not self._inequality_holds(equation, values):
					violations.append(
						Violation(
							equation_id=equation.id,
							residual=self._residual(equation, values),
							tolerance=equation.tolerance,
							relative=float("inf"),
							priority=equation.priority.value,
							strength=strength,
						)
					)
				continue
			residual = self._residual(equation, values)
			scale = self._scale(equation, values)
			relative = abs(residual) / scale if scale > 0 else abs(residual)
			if relative > equation.tolerance:
				violations.append(
					Violation(
						equation_id=equation.id,
						residual=residual,
						tolerance=equation.tolerance,
						relative=relative,
						priority=equation.priority.value,
						strength=strength,
					)
				)
		return violations

	def cross_validate(self, values: Mapping[str, float]) -> CrossValidationReport:
		"""Every declared cross-validation rule against ``values``.

		A separate pass from :meth:`consistency` because it answers a different
		question: ``consistency`` says which *equations* fail, and this says
		which declared *relationships between parameters* a scenario breaks --
		relationships no equation states, so no residual can report them. A
		graph with no rules returns an empty report and says so, rather than an
		empty finding list that reads as "everything holds".
		"""
		from alea.prg.crossval import run_rules

		return run_rules(self._rules, values, self)

	def _residual(self, equation: Equation, values: Mapping[str, float]) -> float:
		return evaluate(parse(equation.lhs), values) - evaluate(
			parse(equation.rhs), values
		)

	def _scale(self, equation: Equation, values: Mapping[str, float]) -> float:
		return max(
			1.0,
			abs(evaluate(parse(equation.lhs), values)),
			abs(evaluate(parse(equation.rhs), values)),
		)

	def _inequality_holds(
		self, equation: Equation, values: Mapping[str, float]
	) -> bool:
		residual = self._residual(equation, values)
		if equation.relation == "leq":
			return residual <= equation.tolerance
		return residual >= -equation.tolerance


def load_graph(path: str | Path | None = None) -> ParameterGraph:
	"""Load the shipped graph, or one at ``path``."""
	return ParameterGraph.from_yaml(path or default_prg_path())
