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

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from alea.config import paths
from alea.prg.crossval import (
	CrossValidationReport,
	CrossValidationRule,
	rules_from_document,
)
from alea.prg.dsl import (
	DslError,
	Expr,
	evaluate,
	linearity_in,
	parse,
	parse_side,
	solve_affine,
	solve_for,
)
from alea.prg.feedback import solve_loop
from alea.prg.views import (
	Direction,
	Equation,
	ParameterNode,
	ParameterType,
	RelationshipEdge,
	Role,
)

__all__ = [
	"CycleError",
	"GraphError",
	"IngestReport",
	"ParameterGraph",
	"ParameterValue",
	"PropagationResult",
	"Violation",
	"default_ingest_dir",
	"default_prg_path",
	"load_graph",
	"load_ingested",
]


#: A parameter's value: a number for every numeric type, a level *name* for a
#: categorical.
#:
#: WHY THE VALUE SET IS NOT ``dict[str, float]``. A categorical's admissible set
#: is its ``categories`` list, and its value is one of those names. The engine
#: used to spell every value ``float`` and coerce with ``float(v)`` at the door,
#: which made a level name unrepresentable: the coercion raised, one frame away
#: from the document that was wrong, with a message naming neither the node nor
#: the field. A graph carrying one free categorical could therefore never be
#: propagated at all -- ``propagate`` refuses a set missing a settable
#: parameter, and no path could put the level into the set.
#:
#: The numeric types stay ``float`` even where the declared type is ``int`` or
#: ``bool``: every equation is arithmetic, an ``int`` is a ``float`` that
#: happens to be whole, and widening that would touch every derivation for no
#: gain. Only a categorical is not a number, and only it is spelled as one.
ParameterValue = float | str


class GraphError(ValueError):
	"""The graph is malformed: an edge or equation names what does not exist."""


def _numeric_only(values: Mapping[str, ParameterValue]) -> dict[str, float]:
	"""``values`` without its level names, for the loop solver.

	A feedback loop is iterated toward a fixed point by arithmetic, and the DSL
	has no operator that yields a level name, so no loop variable can be a
	categorical -- ``ParameterGraph._validate`` refuses a loop whose variable has
	no range, and ``_NON_SCALAR_TYPES`` refuses a range on a categorical, so the
	two cannot both hold. Dropping the names here is therefore lossless for the
	solver, and it keeps ``solve_loop``'s signature numeric rather than widening
	every subtraction inside it to a union that cannot occur.

	``solve_loop`` writes its iterates back into the mapping it is given, so the
	caller merges this projection into ``scoped`` afterwards -- otherwise the
	loop variables the solver just solved for would land in a copy and
	``scoped`` would carry the seeds instead of the fixed point.
	"""
	return {k: v for k, v in values.items() if not isinstance(v, str)}


def _coerce_value(graph: ParameterGraph, name: str, value: Any) -> ParameterValue:
	"""``value`` as the graph spells ``name``: a level name, or a number.

	A categorical keeps its string; everything else is coerced with ``float``,
	which is what the engine has always done and what ``bool``/``int`` need (a
	``True`` arriving from YAML becomes ``1.0``, and every equation is
	arithmetic over floats).

	WHY THIS IS A FUNCTION AND NOT AN INLINE ``float(v)``. There were four
	inline coercions -- ``propagate``, the two in ``propagate_incremental``, and
	the range check -- and a fix landing in one of four is the defect class this
	tree keeps finding. One helper means the rule is stated once: the *node's
	declared type* decides the spelling, not the caller and not the literal.

	A name the graph does not hold keeps the ``float`` attempt, so an unknown
	parameter still raises the coercion error it always did; naming an unknown
	parameter is caught by each caller's own membership check before this runs,
	and this is the backstop rather than the message.
	"""
	node = graph.nodes.get(name)
	if node is not None and node.type is ParameterType.CATEGORICAL:
		return str(value)
	return float(value)


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
	#: Why the equation has no value at these parameters, when it does not.
	#: Empty for an ordinary residual failure. A division by zero, a square
	#: root of a negative and an overflow are all "the equation does not hold
	#: here", but a reader who sees only a residual of infinity cannot tell
	#: that from a huge number, and the fix is different: this is a parameter
	#: the caller set to an edge of its own admissible range.
	unevaluable: str = ""

	@property
	def blocks(self) -> bool:
		"""Whether this failure contradicts the scenario rather than advising.

		Read from ``strength``, and the default is ``hard`` because a violation
		with no declared edge to read is one nothing softened.
		"""
		return self.strength != "informational"

	def __str__(self) -> str:
		tier = "" if self.strength == "hard" else f" [{self.strength}]"
		if self.unevaluable:
			return (
				f"{self.equation_id} ({self.priority}{tier}): cannot be "
				f"evaluated at these values -- {self.unevaluable}"
			)
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

	values: dict[str, ParameterValue]
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
	return paths.repo_root() / "config" / "prg.yaml"


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

		# The edge index, built from the *declared* direction rather than from
		# the source/target fields. `params-prg1.md` §3.3 makes direction a
		# first-class part of an edge -- "the PRG must encode causality" -- and
		# `Direction` offers three values, so indexing by `source` alone read a
		# `backward` edge as forward and made the field decorative. All 84 edges
		# in the shipped document are `forward`, which is why the defect was
		# invisible: a field no edge exercises is a field nothing tests.
		self._by_source: dict[str, list[RelationshipEdge]] = defaultdict(list)
		self._by_target: dict[str, list[RelationshipEdge]] = defaultdict(list)
		for edge in self._edges:
			# A `backward` edge states that the *target* determines the
			# source, so it belongs on the target's outgoing list. Reading the
			# fields and ignoring this is the same defect as a knob nothing
			# reads, one layer down: the declaration is present and inert.
			if edge.direction is Direction.FORWARD:
				self._by_source[edge.source].append(edge)
				self._by_target[edge.target].append(edge)
			elif edge.direction is Direction.BACKWARD:
				self._by_source[edge.target].append(edge)
				self._by_target[edge.source].append(edge)
			else:
				# Bidirectional: the spec's "capacity and dispatch are jointly
				# determined". Both endpoints are a source and a target, so the
				# edge appears on all four lists -- which is what makes
				# `edges_into` the mirror of `edges_from` for such a pair.
				self._by_source[edge.source].append(edge)
				self._by_source[edge.target].append(edge)
				self._by_target[edge.source].append(edge)
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

		#: Per parameter, whether the last solve for it was the exact affine
		#: path or the numeric search. This is the register the model's
		#: ``linearity`` field was meant to be and could not: it is measured
		#: from the formula at the moment of the solve rather than declared
		#: alongside it, so it cannot drift from the arithmetic. A parameter
		#: appearing here as numeric is one whose equation is genuinely not
		#: affine in it -- the case that needs a bracket, a bracket that can
		#: miss, and a widened search that can land on a second root.
		self._solve_paths: dict[str, bool] = {}

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

	@classmethod
	def from_fragments(
		cls, paths: Iterable[str | Path]
	) -> tuple[ParameterGraph, IngestReport]:
		"""Merge generated fragments onto the shipped graph, or refuse.

		WHY THIS EXISTS AT ALL. ``docs/param_ingest.md`` specifies
		``config/prg_ingest/`` as the landing site for generated batches --
		"the loader merges fragments and refuses a duplicate id whose bodies
		differ" -- and until this method there was no such loader, so the eight
		generated batches had no path into the graph. A specified location with
		no reader is the recurring defect of this tree, and the specification
		was the thing committing it.

		WHY IT MERGES ONTO THE SHIPPED DOCUMENT RATHER THAN REPLACING IT. A
		fragment states only what it adds or corrects. The shipped graph is the
		reviewed kernel; a fragment that had to restate all 869 nodes to add
		one would be a fragment nobody could review, and the one that omitted a
		node would silently delete it.

		WHY A DUPLICATE ID IS REFUSED RATHER THAN LAST-WINS. Two fragments
		declaring one id with different bodies is two agents disagreeing about
		a parameter, and there is no fact of the matter about which wrote
		later: the file order is alphabetical, so last-wins would resolve the
		disagreement by filename. An *identical* body is merged silently,
		because two batches that agree are not a conflict.

		The report is returned rather than logged because every count in it --
		the merged total, the duplicates refused, the entries dropped -- is a
		fact the caller has to act on, and a loader that printed them would let
		a caller load a document it did not know was degraded.
		"""
		shipped = yaml.safe_load(default_prg_path().read_text())
		if not isinstance(shipped, dict):
			raise GraphError(
				f"{default_prg_path()} does not hold a mapping at the top level"
			)
		document, report = _merge_fragments(shipped, paths)
		graph = cls.from_mapping(document)
		return graph, report

	def _deprecated_reach(self) -> None:
		"""Refuse an edge or an equation that reaches a deprecated node.

		WHY THIS IS A LOAD ERROR AND NOT A REPORT. ``status: deprecated`` on a
		node says the node should not be used, and the whole value of saying it
		is that something acts on it. A status nothing reads is a label, and a
		label on a node the graph still propagates through is worse than no
		label: a reader who sees it believes the graph has stopped using the
		parameter while every solve still does.

		The check is on the *reach*, not the declaration. A deprecated node
		with no edge and no equation naming it is a node nothing uses, which is
		exactly what deprecating it was meant to achieve -- so it stays in the
		document, and the alias register the fragment carries is how a caller
		finds its replacement. Removing it would lose the record that it ever
		existed, which is what a caller migrating a scenario needs.
		"""
		dead = {
			name
			for name, node in self._nodes.items()
			if node.status == "deprecated"
		}
		if not dead:
			return
		for edge in self._edges:
			for end, label in ((edge.source, "source"), (edge.target, "target")):
				if end in dead:
					raise GraphError(
						f"edge {edge.source} -> {edge.target} has a deprecated "
						f"{label} ({end}); the node's replacement is "
						f"{self._nodes[end].deprecated_by!r}"
					)
		for equation in self._equations.values():
			named = (
				*equation.parameters,
				*equation.free_variables,
				*equation.determined_variables,
			)
			for name in named:
				if name in dead:
					raise GraphError(
						f"equation {equation.id!r} names the deprecated "
						f"parameter {name!r}; its replacement is "
						f"{self._nodes[name].deprecated_by!r}"
					)

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
		# Iterate the *equations* and ask `strength_of` for each, rather than
		# iterating `_strength`. That dict is built from the edge list, so an
		# equation no edge cites has no entry in it -- while `strength_of` and
		# the propagation both default such an equation to `hard`. The two
		# readers disagreed by exactly the number of edge-less equations, and
		# the register is the one that was wrong: it reported 37 tiers over 38
		# equations, so a `hard` equation read as no equation at all.
		counts: dict[str, int] = {}
		for equation in self._equations.values():
			strength = self.strength_of(equation.id)
			counts[strength] = counts.get(strength, 0) + 1
		return dict(sorted(counts.items()))

	def linearity(self) -> dict[str, str]:
		"""Per determined variable, whether its equation is affine in it.

		Computed from the formulas, not read from the document. The model's
		``linearity`` field is declared per *equation* and no reading of the
		arithmetic reproduced the shipped column: classifying by the variable
		solved for, by any parameter's entry, by the worst entry, and by
		whether every parameter enters affinely gave four different sets of
		eight disagreements, disjoint from one another. A field no definition
		agrees with is not a hard classification, it is a hand-entered one.

		The question with an answer is per variable -- an equation is affine in
		the variable it solves for, or it is not, and that is what decides
		whether the solve is arithmetic or a bracketed search. So the register
		is keyed by variable.

		This is the *static* counterpart to :meth:`solve_paths`, which records
		what a particular propagation actually did. The two can disagree for a
		loop variable, whose equation is affine in it while the solve goes
		through the relaxation in ``feedback.solve_loop`` rather than
		:meth:`_derive`; the static answer is what the arithmetic says, and the
		recorded one is what ran.
		"""
		out: dict[str, str] = {}
		for equation in self._equations.values():
			if not equation.determined_variables:
				continue
			residual = parse(f"({equation.lhs}) - ({equation.rhs})")
			for variable in equation.determined_variables:
				out[variable] = linearity_in(residual, variable)
		return dict(sorted(out.items()))

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

		False for a derived parameter, for a loop variable, and for an
		endogenous one. This is the question the whole graph exists to answer: a
		user who sets a carbon price *and* the emissions it determines has set
		two coupled parameters independently, and the only correct response is
		to refuse rather than to pick one and recompute the other in silence.

		**An endogenous parameter is refused for the third reason, not the
		first.** A derived value is refused because an equation overwrites it;
		an endogenous value is refused because the *solve* determines it, and a
		user who sets a fleet capacity has stated an input where the graph
		states a decision. The two are one answer here and two different
		diagnoses, which is why :meth:`role` exists: a caller that needs to say
		*why* a knob was refused must not infer it from this boolean.

		**A deprecated parameter is refused for a fourth reason: it is not a
		knob any more.** The node is kept so a scenario that names it can be
		told what replaced it -- see :meth:`_refuse_out_of_range`, which raises
		on a supplied value rather than this predicate quietly returning False
		and letting the value stand. It is excluded here as well so that every
		register built on this predicate (the dead-knob count, the sensitivity
		inputs, the translation coverage) describes the graph a scenario can
		actually move, not the tombstones beside it. ``role`` still reports the
		role the node had, because that is a fact about the node and not a
		permission.
		"""
		return (
			parameter not in self._determiner
			and parameter not in self._loop_variables
			and self._nodes[parameter].role is not Role.ENDOGENOUS
			and self._nodes[parameter].status != "deprecated"
		)

	def role(self, parameter: str) -> Role:
		"""What determines this parameter, as the graph understands it.

		``is_settable`` answers "may the user move this"; this answers "who
		moves it instead", and the two are not the same question. A caller
		reporting *why* a parameter was refused -- the CLI's message, the
		translate layer's register -- needs the second, and reading it off
		``is_settable`` collapses "an equation computes it" into "the optimiser
		chooses it", which are different sentences to put in front of a user.
		"""
		return self._nodes[parameter].role

	def endogenous(self) -> tuple[str, ...]:
		"""The parameters the optimiser chooses, in name order.

		The middle layer of ``params-prg1.md`` §3.4's DAG. It is a method
		rather than a count in a docstring because the number that matters is
		the one the loaded graph carries, and a figure written into prose is a
		figure that drifts the first time a node is added.
		"""
		return tuple(
			sorted(name for name in self._nodes if self._nodes[name].role is Role.ENDOGENOUS)
		)

	def uncoupled(self) -> tuple[str, ...]:
		"""The parameters no equation names, in name order.

		The register behind the catalog's expansion from 88 nodes to 869. The
		catalog holds 787 parameters and states an algorithm for almost every
		one -- "Growth curve shape fitting", "Bottom-up load synthesis" -- and a
		*formula* for none: grepping the algorithm and description cells for an
		``=`` returns zero rows. So the 781 nodes the expansion added are knobs
		with a declared range and no arithmetic, and this method is how that is
		stated rather than implied.

		Why a method and not a count in a docstring: the number that matters is
		the one the loaded graph carries, and a figure written into prose drifts
		the first time a node is added. ``test_every_settable_parameter_affects_
		or_constrains_something`` asserts this register *equals* the set of
		settable parameters that reach nothing, so the two spellings of "does
		nothing" cannot drift apart -- one is derived from the equations and
		this one from the node's own role, and a disagreement between them is a
		document that lies about its own graph.

		A node here is ``Role.FREE``: the schema's own word for "unconstrained
		within its range". That is what a catalog row naming a method and no
		formula describes, and it is deliberately not ``exogenous`` -- an
		exogenous node is an input a scenario is expected to set, and nothing
		downstream of these 781 reads them, so calling them inputs would claim a
		consumer that does not exist.

		**A deprecated node is not filtered out here, and that is deliberate.**
		This register states a structural fact about the document -- no equation
		names this node -- and a tombstone satisfies it. Whether a node may be
		*set* is :meth:`is_settable`'s question, and that predicate does exclude
		tombstones. Every consumer that means "the live unread surface"
		subtracts them by status rather than trusting this method to have done
		it silently.

		No count is stated here on purpose. The docstring above makes the
		argument that a figure written into prose drifts the first time a node
		is added, and an earlier version of this paragraph then carried one --
		"three nodes carry the status at present", naming
		``cross_border_trading``, ``demand_growth_rate`` and
		``pm25_relative_risk_per_kt``. Batches 49 and 55 retired three more and
		the sentence went on asserting the old number.
		``test_every_settable_parameter_affects_or_constrains_something`` pins
		the set by name, so a further deprecation has to be written down there;
		this paragraph points at that pin instead of competing with it.

		**This register has a floor above zero, and it is structural.** Two
		classes of node cannot be named by an equation at all. A *categorical*
		carries a level name and a level has no arithmetic -- ``translate``
		says so at ``_graph_value``, ``audit`` refuses to put one in a ratio,
		and ``_NON_SCALAR_TYPES`` refuses a numeric default on one -- so all 41
		are here and none can leave. A *tombstone* must not be wired into an
		equation, since the point of retiring an id is that nothing computes
		from it. On the shipped graph that is 41 + 6 = 47 of 235.

		So "drive ``uncoupled()`` to zero" is not a reachable goal and a batch
		that states it as one will report failure forever. The reachable target
		is the numeric, live remainder -- 119 on the shipped graph -- and this
		paragraph exists because the count alone does not say which 47 are
		permanent. No figure here is load-bearing: they are the shipped graph's
		values and the classes are the claim.
		"""
		named = {
			name
			for equation in self._equations.values()
			for name in (
				*equation.parameters,
				*equation.free_variables,
				*equation.determined_variables,
			)
		}
		return tuple(sorted(set(self._nodes) - named))

	def edges_from(self, parameter: str) -> tuple[RelationshipEdge, ...]:
		"""The edges whose declared direction leaves this parameter.

		The declared direction, not the arithmetic. ``affects`` answers "whose
		value moves"; this answers "what the graph says this feeds", which is
		the question a reader of a diagram is asking and the one the edge set
		was written to state.

		"Leaves" and not "has as its ``source`` field": a ``backward`` edge
		states that its *target* determines its source, so it leaves the target.
		Reading the field instead made the direction inert -- see the index in
		the constructor for why that mattered.
		"""
		return tuple(self._by_source.get(parameter, ()))

	def edges_into(self, parameter: str) -> tuple[RelationshipEdge, ...]:
		"""The edges whose declared direction arrives at this parameter.

		The mirror of :meth:`edges_from`, and under the declared direction
		rather than the fields: a ``bidirectional`` edge appears on both, which
		is what the spec's jointly-determined pairs are.
		"""
		return tuple(self._by_target.get(parameter, ()))

	def rules_reading(self, parameter: str) -> tuple[str, ...]:
		"""The cross-validation rules whose condition reads this parameter.

		A rule is a fourth coupling, and not a fifth kind of the same thing
		`affects` and `constrains` already separate: it does not move a
		value and it does not bound the LP, it gates whether a scenario is
		*admissible* -- the regulator's lever's lever. A knob a rule reads is
		a knob the graph applies, and the uncoupled register would call a
		parameter whose only consumer is the admissibility check "floating",
		which is wrong in exactly the way counting only equations would be
		wrong the other way.

		Read from the parsed rules; the registry is built at load, so this is
		a scan of a small tuple, not a re-parse.
		"""
		return tuple(
			rule.id
			for rule in self._rules
			if parameter in rule.parameters
		)

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

	def uncarried(self, values: Mapping[str, ParameterValue]) -> tuple[str, ...]:
		"""Symbols the equations read that ``values`` does not carry, in name order.

		The complete answer to "what is this parameter set missing", and the
		reason it exists rather than the error :meth:`consistency` raises: the
		DSL evaluator raises on the *first* symbol it cannot resolve, so the
		name in that message is a fact about the order the equations happen to be
		stored in and not about the scenario. The same input against a graph
		whose equations are sorted differently reports a different missing
		parameter, which sends a caller to supply one symbol, then another.
		Reading the symbol lists gives the whole gap at once, and it does not
		move when the file is reordered.

		Every symbol, including the derived ones. A set that has not been
		propagated is missing exactly those, and that is the most common way to
		be incomplete -- so filtering them out here would report a set with
		thirty-three holes as carrying none. The caller separates them with
		:meth:`computed`; this method's job is to be complete, not to classify.
		"""
		carried = set(values)
		needed: set[str] = set()
		for equation in self._equations.values():
			for symbol in (*equation.parameters, *equation.free_variables):
				if symbol not in carried:
					needed.add(symbol)
		return tuple(sorted(needed))

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
		self._deprecated_reach()
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

		# Gate 6 of `docs/param_ingest.md`: both endpoints of every edge must
		# appear in the symbols of the equation it cites. The spec states it as
		# a rule and `docs/param_ingest.md` says the loader enforces it, and
		# nothing did -- which is why 26 of one batch set's 145 edges cite an
		# equation that does not hold them. The check is cheap here because the
		# arithmetic is parsed below for a different reason; it is done first so
		# the failure names the edge rather than the equation.
		for edge in self._edges:
			equation = self._equations[edge.equation_id]
			try:
				held = parse_side(equation.lhs).symbols | parse_side(equation.rhs).symbols
			except DslError:
				# The malformed-arithmetic error is raised by the loop below,
				# with the equation's own id. Reporting it here as well would
				# name the edge for a defect that is the equation's.
				continue
			for end, label in ((edge.source, "source"), (edge.target, "target")):
				if end not in held:
					raise GraphError(
						f"edge {edge.source} -> {edge.target} names {end!r} as "
						f"its {label}, and {edge.equation_id!r} does not hold "
						f"it; an edge is a claim about a coupling the equation "
						f"states, and this one claims a coupling that is not in "
						f"the arithmetic"
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
			#
			# Each side is parsed with `parse_side`, not `parse`, because a bound
			# equation's right-hand side is legitimately a constant --
			# `sum(demand shares) <= 1.0` is a relation between four parameters
			# and a ceiling, and `parse`'s "names no parameter" refusal is an
			# argument about a *relation*, not about one side of one. The vacuity
			# it was protecting against is asserted below on the combined
			# arithmetic, which is where it can actually be stated.
			try:
				lhs = parse_side(equation.lhs)
				rhs = parse_side(equation.rhs)
			except DslError as exc:
				raise GraphError(f"equation {equation.id!r}: {exc}") from exc
			named = lhs.symbols | rhs.symbols
			if not named:
				raise GraphError(
					f"equation {equation.id!r} is constant on both sides "
					f"({equation.lhs!r} {equation.relation} {equation.rhs!r}); a "
					f"relation naming no parameter relates nothing and would pass "
					f"every consistency check vacuously"
				)
			# A relation between an expression and itself is the other way a
			# relation can relate nothing, and the constant check above does not
			# catch it: `x <= x` names a parameter on both sides, so it passes
			# the vacuity guard, couples a node, and then holds at every value
			# the node can take. The solver builds the residual `(lhs) - (rhs)`,
			# which is identically zero, so the constraint is dropped as
			# trivially satisfied and the equation's only effect is to make a
			# node look reached. `Expr` equality is structural, so this catches
			# `x <= x` however each side is spelled -- but only after the two
			# are parsed, and a relation whose sides simplify to each other
			# (`x + 0 <= x`) is still a relation between distinct formulas. Say
			# what the equation was probably meant to be, because a tautology is
			# nearly always a mis-typed operand rather than an intended claim.
			if lhs == rhs:
				raise GraphError(
					f"equation {equation.id!r} relates {equation.lhs!r} to itself "
					f"({equation.lhs!r} {equation.relation} {equation.rhs!r}); the "
					f"residual is identically zero, so the equation couples "
					f"{sorted(named)} without constraining them and would read as "
					f"a reached node in every coverage count"
				)
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

		# An endogenous parameter is chosen by the optimiser, and the graph
		# must not also claim to compute it: `_determiner` would then overwrite
		# the optimiser's own answer with a closed form, and the two would agree
		# only while the closed form happened to be the optimum. The roles are
		# exclusive for that reason, and the check is here rather than in the
		# node model because only the graph knows what the equations say.
		conflicting = sorted(
			name
			for name in self._nodes
			if self._nodes[name].role is Role.ENDOGENOUS
			and (name in self._determiner or name in self._loop_variables)
		)
		if conflicting:
			raise GraphError(
				f"{conflicting} are endogenous but an equation also fixes them; "
				f"a value the optimiser chooses is not one the graph computes, "
				f"and propagating the closed form over the optimum would replace "
				f"the solved fleet with an arithmetic one"
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
		values: Mapping[str, ParameterValue],
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
		self._solve_paths.clear()
		scoped: dict[str, ParameterValue] = {
			k: _coerce_value(self, k, v) for k, v in values.items()
		}
		# Before any arithmetic: a value outside its declared range is refused
		# here rather than propagated and reported. The whole mapping is
		# checked, not a caller-supplied subset, because `propagate` cannot tell
		# the two apart -- the convenience paths pass every default. It does not
		# need to: a default outside its own range never reaches this method,
		# since `ParameterNode._range_contains_default` refuses the document at
		# load. So the only value that can trip this is one a caller chose.
		self._refuse_out_of_range(scoped)
		missing = set(self._nodes) - scoped.keys()
		# An endogenous parameter is not *missing* when a caller omits it: no
		# arithmetic can supply it and no user is required to, because the
		# solve determines it. Requiring a value for one would make every
		# propagation over a graph carrying a fleet fail for a reason that is
		# not a defect -- and the alternative, defaulting it, would propagate a
		# fleet the optimiser never chose.
		underived_missing = {
			name
			for name in missing
			if name not in self._determiner
			and name not in self._loop_variables
			and self._nodes[name].role is not Role.ENDOGENOUS
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
		loop_results = []
		for loop in self.feedback_loops():
			# The solver's own mapping is numeric and its iterates are written
			# into the mapping it is handed, so it gets a projection and the
			# solved values are merged back. Passing `scoped` itself would work
			# only while no level name is in it, which is not a property this
			# graph promises.
			numeric = _numeric_only(scoped)
			loop_results.append(solve_loop(self, loop, numeric))
			scoped.update(numeric)
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
			# A categorical's value is a level name and has no arithmetic. It
			# cannot reach here -- `computed` is the derived parameters and the
			# loop variables, an equation is arithmetic and so produces no level
			# name, and a loop variable is iterated toward a fixed point -- but
			# the guard is stated rather than inferred, because the day a level
			# name reaches this subtraction is the day it raises a TypeError
			# naming neither the parameter nor the reason.
			if isinstance(value, str) or isinstance(start, str):
				if value != start:
					# A *changed level* is a change a caller asked about, and
					# dropping it silently is the defect `changed` exists to
					# prevent. It has no magnitude, so it is reported with one:
					# a level move is a unit step, not a measured delta.
					moved[name] = 1.0
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
		values: Mapping[str, ParameterValue],
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
		self._solve_paths.clear()
		# The previous result carries every derived value, and the caller's
		# `values` need only name what it set -- the same sparse contract
		# `propagate` accepts. Seeding from `previous` first is what lets an
		# undirtied derived parameter keep its value instead of going missing:
		# a caller who passes only the knobs they edited would otherwise leave
		# every carried-over parameter absent, and the next derivation that
		# reads one would fail on a parameter set that is complete in fact.
		scoped: dict[str, ParameterValue] = {
			k: _coerce_value(self, k, v) for k, v in previous.values.items()
		}
		scoped.update({k: _coerce_value(self, k, v) for k, v in values.items()})
		# The same refusal `propagate` makes, at the same door. `values` is
		# checked rather than `scoped`: `scoped` is seeded from `previous`, whose
		# values have already been through this, so checking it again would
		# re-refuse a set that was admitted -- and on the sparse contract this
		# method documents, `values` is exactly what the caller is setting.
		self._refuse_out_of_range(
			{k: _coerce_value(self, k, v) for k, v in values.items()}
		)
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
				numeric = _numeric_only(scoped)
				loop_results.append(solve_loop(self, loop, numeric))
				scoped.update(numeric)
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
			# The same level-name guard the full propagation carries, for the
			# same reason: a level has no arithmetic, and the report must still
			# name a level that moved rather than drop it in silence.
			if isinstance(value, str) or isinstance(start, str):
				if value != start:
					moved[name] = 1.0
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
		values: Mapping[str, ParameterValue],
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

	def _derive(self, parameter: str, values: Mapping[str, ParameterValue]) -> float:
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
		# A denominator the caller set to zero is a *finding about the
		# scenario*, and the arithmetic raises `DslError` for it -- which the
		# two branches below catch only after the exact solve has already
		# raised. The affine path is tried first and it is the one a division
		# fails on, so the wrap belongs around it: without this, the
		# `solve_for` handler below never sees the fault and the message names
		# no equation.
		try:
			exact = self._solve_affine(residual, parameter, values)
		except DslError as exc:
			raise GraphError(
				f"cannot derive {parameter} from {equation.id!r}: {exc}"
			) from exc
		if exact is not None:
			# An affine residual has one root and it is arithmetic, so there is
			# no bracket to miss and no second root to land on. Every equation
			# in the shipped library is affine in the variable it solves for --
			# checked, not assumed -- which makes this the path every
			# propagation actually takes and the numeric search the fallback.
			#
			# This is also what the model's ``linearity`` field was for and
			# could not deliver: it was a hand-entered label on the equation,
			# four defensible readings of the formulas disagreed with it on
			# four disjoint sets of eight, and nothing read it. The fact that
			# decides the solve is per *variable*, and it is computed here.
			self._note_linearity(parameter, exact_affine=True)
			# An answer outside the declared range is a finding whether or not
			# a bracket was searched to find it. The register used to be
			# written only by `_widen`, which made "left its range" and "the
			# numeric search had to leave the bracket to find it" the same
			# fact -- two things that coincide only while every solve is
			# numeric. Comparing the answer against the range here is what
			# keeps the finding when the solve stops needing a bracket.
			self._note_excursion(parameter, exact, node.range)
			return exact
		self._note_linearity(parameter, exact_affine=False)
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

	def _solve_affine(
		self, residual: Expr, parameter: str, values: Mapping[str, ParameterValue]
	) -> float | None:
		"""The root of an affine residual, or ``None`` if it is not affine.

		For ``a * p + b == 0`` the root is ``-b / a``, and there is exactly one
		of it. That matters beyond speed: :func:`solve_for` needs a bracket, a
		bracket can fail to contain the root, and the widening search that
		recovers from that can land on a *second* root when the residual is
		non-monotonic -- which is why ``_widen`` carries a caveat about
		learning curves. An affine residual has no second root to land on.

		Delegates to :func:`alea.prg.dsl.solve_affine` so the loop solver in
		``alea.prg.feedback`` takes the identical path rather than a second
		implementation of it.
		"""
		return solve_affine(residual, parameter, values)

	def _note_linearity(self, parameter: str, *, exact_affine: bool) -> None:
		"""Record which solve path fixed ``parameter``."""
		self._solve_paths[parameter] = exact_affine

	def _note_excursion(
		self, parameter: str, value: float, admissible: tuple[float, float]
	) -> None:
		"""Record ``value`` if it falls outside the parameter's declared range.

		The finding is "the equation's answer is outside the set the parameter
		is admissible over", and it is a property of the *answer*. It used to be
		recorded only where the numeric search had to widen its bracket to find
		one, which is a different fact that happens to imply this one: a root
		outside the range is necessarily outside a bracket that starts as the
		range. That implication runs one way, so recording the excursion at the
		widening meant an exact solve -- which never has a bracket to widen --
		reported nothing, and a scenario that fixed an inadmissible value went
		silent the moment the solve got better.

		A non-finite value is not an excursion and is not recorded as one: it is
		a failed solve, and reporting it here would file an arithmetic fault
		under a scenario finding.
		"""
		low, high = admissible
		if not math.isfinite(value):
			return
		if value < low or value > high:
			self._range_excursions[parameter] = value

	def _refuse_out_of_range(self, values: Mapping[str, ParameterValue]) -> None:
		"""Refuse a caller-supplied value outside the node's declared range.

		The declared range was read in three places and enforced in none of them
		for a value the *caller* supplied: it brackets the solver for a derived
		parameter, it filters the corrections the conflict detector proposes,
		and ``ParameterNode._range_contains_default`` checks it against the
		node's own default -- which is the only caller-side check, and it runs on
		the document rather than on a scenario. So ``propagate`` accepted
		``capacity_factor=999`` against a declared ``(0.05, 0.7)`` and returned
		it as the scenario's value.

		That is a defect in the direction that hides: the graph reports the
		parameter as set, every downstream identity that does not read it holds,
		and ``range_excursions`` -- which reports exactly this finding for a
		*derived* parameter -- stays empty because it is written from
		:meth:`_note_excursion`, and a settable node has no equation to derive
		it. The register that exists to report inadmissible values was
		structurally blind to the class the caller controls.

		The refusal is at the door and not at the read, because a parameter set
		is propagated many times and a set that is inadmissible when it enters
		is inadmissible throughout; refusing at the read would re-raise on every
		derivation that touches it, and the message would name whichever
		equation happened to ask first rather than the value that is wrong.

		**A deprecated node is refused here too, and for a stronger reason.**
		``_deprecated_reach`` refuses an edge or an equation that names one, and
		the batch that deprecates a node writes that its id is kept "so a
		scenario that names it fails loudly". Nothing made it fail: the node is
		not a determiner, not a loop variable and not endogenous, so
		``is_settable`` said yes and ``propagate`` accepted it, computed nothing
		from it, and returned it as the scenario's value. A caller who renamed a
		knob in a config and got a silent no-op is the exact failure the
		deprecation existed to prevent, and it was the one case the reach check
		could not see -- a *value*, not an edge. The refusal names the
		replacement, which is the whole content of ``deprecated_by``.

		The test is *differs from the default*, not *is present*, because
		``propagate`` is handed every default including the deprecated nodes'
		own and cannot tell that from a caller setting it. The two are not
		distinguishable and do not need to be: a caller who sets a knob to the
		value it already holds has set nothing, deprecated or not, and a refusal
		on presence alone would make every propagation over this graph fail.

		Every key in ``values`` is checked rather than a caller-supplied subset,
		and the method does not need to distinguish them: a node whose *default*
		is outside its range never reaches a propagation, because
		``ParameterNode._range_contains_default`` refuses the document at load.
		So a value that trips this is one a caller chose, whichever mapping it
		arrived in.

		Only *settable* nodes are checked, and the boundary is the point of the
		method rather than a convenience. A derived node's value is the graph's
		own output, and it already has a channel: :meth:`_note_excursion` files
		an equation whose answer lands outside the range under
		:meth:`range_excursions`, which ``check_scenario`` surfaces as a
		scenario finding. Refusing it here would override that channel with a
		refusal -- and worse, it would refuse the graph *its own result*: the
		incremental contract is ``propagate_incremental(values, previous, ...)``
		with ``values`` carrying ``previous``'s derived values, so a run in
		which one equation lands outside its range would leave every later call
		seeded from that result unable to propagate at all. A gate that a
		correct graph cannot satisfy is not a gate. The first draft of this
		method checked every key and did exactly that, on
		``reliability_cost_usd`` at 1.096e12 against a declared 1e12 ceiling.
		"""
		for name, value in sorted(values.items()):
			node = self._nodes.get(name)
			if node is None:
				continue
			if node.status == "deprecated":
				if value != node.default:
					raise GraphError(
						f"{name} is deprecated and was replaced by "
						f"{node.deprecated_by!r}; setting it computes nothing, so "
						f"a scenario that names it is a scenario with a no-op in "
						f"it"
					)
				continue
			if not self.is_settable(name):
				continue
			if node.type is ParameterType.CATEGORICAL:
				# A categorical's admissible set is its `categories` list, not a
				# numeric range, so the `node.range is None` test this method
				# used to open with skipped exactly the class whose admissible
				# set the caller controls most directly -- and `propagate`
				# accepted ``market_structure='nonsense'`` in silence, which is
				# the same defect the docstring above describes, one class over.
				# The comparison is against the names, not their positions: an
				# index would repoint at a different level the moment anyone
				# reorders `categories`, a change no reviewer reads as semantic.
				if value not in node.categories:
					raise GraphError(
						f"{name}={value!r} is not one of the levels the graph "
						f"declares for it ({list(node.categories)}); a categorical's "
						f"admissible set is its `categories` list, so this scenario "
						f"states a level that does not exist"
					)
				continue
			if node.range is None:
				continue
			if isinstance(value, str):
				# A level name, which is admissible only against `categories` --
				# the check `ParameterNode._range_contains_default` makes at load
				# and which `ParameterNode._string_default_names_a_level` makes
				# for the document. A node that is `categorical` and carries a
				# *range* is refused at load by `_NON_SCALAR_TYPES`, so reaching
				# here with a string and a range means the node is not a
				# categorical at all, and a string is not a value it admits.
				raise GraphError(
					f"{name}={value!r} is a string and the graph declares a numeric "
					f"range ({node.range[0]}, {node.range[1]}) for it; a level name "
					f"is admissible only on a `categorical` node, whose admissible "
					f"set is its `categories` list"
				)
			low, high = node.range
			if not math.isfinite(value):
				# Not an excursion, for the reason :meth:`_note_excursion`
				# gives: a non-finite value is a failed arithmetic, and filing
				# it here would report an arithmetic fault as a scenario
				# finding. ``propagate`` raises on it where the solve fails.
				continue
			if value < low or value > high:
				raise GraphError(
					f"{name}={value} is outside the range ({low}, {high}) the graph "
					f"declares for it, so the scenario states a value the parameter "
					f"is not admissible over. Widen the node's range in "
					f"config/prg.yaml if the admissible set is wrong, rather than "
					f"setting a value the graph cannot report"
				)

	# -- consistency ----------------------------------------------------

	def range_excursions(self) -> dict[str, float]:
		"""Derived parameters whose equation fixed a value outside their range.

		Read after a propagation. A value here is not a solver failure -- the
		equation was solved and this is its answer -- it is the answer landing
		outside the set the parameter is admissible over, which is a finding
		about the scenario.
		"""
		return dict(self._range_excursions)

	def solve_paths(self) -> dict[str, str]:
		"""Which solve fixed each derived parameter in the last propagation.

		``"affine"`` when the residual was linear in the parameter and the root
		was arithmetic; ``"numeric"`` when it was not and the bracket search
		ran. Read after a propagation.

		This is the *measured* replacement for the model's declared
		``linearity`` field. That field could not be reconciled with the
		formulas under any of four readings, was read by no code, and had
		already drifted from the document it was copied from. This register
		cannot drift: it is written by the branch that took the solve, so a
		parameter reported ``affine`` is one whose root was ``-b / a``.

		A ``"numeric"`` entry is the finding worth acting on. It is the only
		case where the answer came from a bracket that could have missed, and
		the shipped library has none -- every equation in it is affine in the
		variable it solves for. The register exists so that the first equation
		that is not says so at the solve, rather than sitting behind a
		hand-entered label a reader has to trust.
		"""
		return {
			parameter: ("affine" if exact else "numeric")
			for parameter, exact in sorted(self._solve_paths.items())
		}

	def consistency(
		self, values: Mapping[str, ParameterValue], *, only: str | None = None
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
			# An equation with no value at these parameters does not hold, and
			# this method's contract is to *return* every equation that fails
			# rather than to raise. A denominator a caller set to the floor of
			# its own declared range used to escape from here as a
			# `ZeroDivisionError` -- an `ArithmeticError`, so not caught by any
			# of this package's `except DslError` handlers -- which turned a
			# reportable scenario into a traceback. `relative` is infinite
			# because the fault is a domain error and not a magnitude: there is
			# no residual to compare against a tolerance.
			try:
				if equation.relation != "eq":
					# An inequality is a boundary. Reporting its residual as a
					# violation would flag a parameter sitting correctly inside its
					# bound, so the sign is what matters, not the magnitude.
					holds = self._inequality_holds(equation, values)
					residual = 0.0 if holds else self._residual(equation, values)
					relative = float("inf")
					failed = not holds
				else:
					residual = self._residual(equation, values)
					scale = self._scale(equation, values)
					relative = abs(residual) / scale if scale > 0 else abs(residual)
					failed = relative > equation.tolerance
			except DslError as exc:
				violations.append(
					Violation(
						equation_id=equation.id,
						residual=float("inf"),
						tolerance=equation.tolerance,
						relative=float("inf"),
						priority=equation.priority.value,
						strength=strength,
						unevaluable=str(exc),
					)
				)
				continue
			if failed:
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

	def cross_validate(self, values: Mapping[str, ParameterValue]) -> CrossValidationReport:
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

	def _residual(self, equation: Equation, values: Mapping[str, ParameterValue]) -> float:
		return evaluate(parse_side(equation.lhs), values) - evaluate(
			parse_side(equation.rhs), values
		)

	def _scale(self, equation: Equation, values: Mapping[str, ParameterValue]) -> float:
		return max(
			1.0,
			abs(evaluate(parse_side(equation.lhs), values)),
			abs(evaluate(parse_side(equation.rhs), values)),
		)

	def _inequality_holds(
		self, equation: Equation, values: Mapping[str, ParameterValue]
	) -> bool:
		residual = self._residual(equation, values)
		if equation.relation == "leq":
			return residual <= equation.tolerance
		return residual >= -equation.tolerance


#: The four registers a fragment may declare. Anything else is refused rather
#: than ignored: a fragment whose key nothing reads is a batch that believes it
#: contributed something, and the loader is the only place that can say it did
#: not.
_FRAGMENT_REGISTERS = (
	"parameters",
	"equations",
	"relationships",
	"cross_validation",
	"aliases",
)


@dataclass(frozen=True)
class IngestReport:
	"""What a fragment merge did, entry by entry.

	Every field is a count the caller has to act on, which is why this is
	returned rather than printed. ``refused`` and ``unknown`` in particular are
	not warnings: the first is two batches disagreeing about a parameter, and
	the second is a fragment key this loader does not read. A loader that
	logged either and returned a graph would hand the caller a document it did
	not know was degraded -- the clean-bill-of-health failure the rest of this
	module is built to avoid.
	"""

	#: fragment path -> how many entries of each register it contributed.
	per_file: dict[str, dict[str, int]] = field(default_factory=dict)
	#: ``(id, first file, second file)`` for every id two fragments declared
	#: with differing bodies. Refused, never merged.
	refused: tuple[tuple[str, str, str], ...] = ()
	#: ``(file, key)`` for every top-level key this loader does not read.
	unknown: tuple[tuple[str, str], ...] = ()
	#: ``(id, file)`` for entries an *identical* body declared twice. Merged,
	#: because two batches that agree are not a conflict.
	redundant: tuple[tuple[str, str], ...] = ()
	#: ``(register, id, file)`` for every shipped entry a fragment replaced.
	#: Not a defect -- correcting a node is what Register 1 is for -- but the
	#: count is the review surface: a batch that corrects 219 nodes and
	#: reports none is one whose diff nobody can see.
	corrected: tuple[tuple[str, str, str], ...] = ()
	#: ``(id, file, why)`` for entries dropped before the merge: a node whose
	#: body is not a mapping, an equation with no arithmetic.
	dropped: tuple[tuple[str, str, str], ...] = ()
	#: Totals after the merge, so a caller can see the register grow.
	counts: dict[str, int] = field(default_factory=dict)

	def __bool__(self) -> bool:
		"""False when the merge lost or refused nothing."""
		return not (self.refused or self.unknown or self.dropped)

	def summary(self) -> str:
		lines = [
			f"fragments: {len(self.per_file)}",
			"  " + "  ".join(f"{k}={v}" for k, v in sorted(self.counts.items())),
		]
		for label, rows in (
			("REFUSED (duplicate id, bodies differ)", self.refused),
			("UNKNOWN register", self.unknown),
			("DROPPED", self.dropped),
		):
			if rows:
				lines.append(f"  {label}: {len(rows)}")
				for row in rows[:8]:
					lines.append(f"    {' | '.join(str(r) for r in row)}")
				if len(rows) > 8:
					lines.append(f"    ... {len(rows)} total")
		if self.redundant:
			lines.append(f"  redundant (identical body twice): {len(self.redundant)}")
		if self.corrected:
			by_file: dict[str, int] = {}
			for _register, _identifier, path in self.corrected:
				by_file[path] = by_file.get(path, 0) + 1
			lines.append(
				f"  shipped entries corrected: {len(self.corrected)}  "
				+ "  ".join(f"{k}={v}" for k, v in sorted(by_file.items()))
			)
		return "\n".join(lines)


def default_ingest_dir() -> Path:
	return paths.repo_root() / "config" / "prg_ingest"


def _parse_side_for_stale(equation: Mapping[str, Any]) -> list[str]:
	"""Every symbol the equation's own arithmetic names, left to right.

	`parse_side` is called bare rather than through the loader's own
	equation walk, so a side that fails to parse answers "not judged" with an
	empty list and the edge is kept: a stale-edge claim requires an equation
	whose arithmetic can be read.
	"""
	named: list[str] = []
	from alea.prg.dsl import parse_side

	for side in (equation.get("lhs"), equation.get("rhs")):
		try:
			expr = parse_side(str(side))
		except Exception:
			continue
		for symbol in sorted(expr.symbols):
			if symbol not in named:
				named.append(symbol)
	return named


def _merge_fragments(
	shipped: Mapping[str, Any], paths: Iterable[str | Path]
) -> tuple[dict[str, Any], IngestReport]:
	"""Merge generated fragments onto a shipped document.

	The document is not mutated: a caller that merges twice from one parse
	gets the same answer, and a refused merge leaves the shipped mapping
	exactly as it was found.
	"""
	document: dict[str, Any] = {
		"parameters": dict(shipped.get("parameters") or {}),
		"equations": dict(shipped.get("equations") or {}),
		"relationships": list(shipped.get("relationships") or []),
		"cross_validation": list(shipped.get("cross_validation") or []),
	}
	# `(register, id) -> (body, file)` for every entry a *fragment* has
	# claimed. The shipped document is deliberately absent from this table:
	# Register 1 is "only nodes being added or corrected", so a fragment
	# overwriting a shipped node is the register doing its job, and refusing
	# it would make the 691 placeholder nodes uncorrectable. A duplicate is
	# two *fragments* disagreeing, which is the case with no fact of the
	# matter -- the file order is alphabetical, so resolving it by order would
	# resolve it by filename.
	seen: dict[tuple[str, str], tuple[Any, str]] = {}
	#: Every shipped entry a fragment replaced, so the correction is counted
	#: rather than silent. A batch that corrects 219 nodes and reports none is
	#: a batch whose review cannot see what it changed.
	corrected: list[tuple[str, str, str]] = []
	shipped_bodies: dict[tuple[str, str], Any] = {}
	for register in ("parameters", "equations"):
		for key, body in document[register].items():
			shipped_bodies[(register, key)] = body
	for register in ("cross_validation", "relationships"):
		for item in document[register]:
			# Same dedupe as the registers above: a re-shipped identical rule
			# or edge is redundant, not a second record of one coupling -- the
			# first bake appended fragment relationships onto a document that
			# already carried them, and the graph then held two records of
			# every coupling (569 edges over the same 382 claims).
			shipped_bodies[
				(register, str(item.get("id") or f"{item.get('source')}->{item.get('target')}"))
			] = item

	per_file: dict[str, dict[str, int]] = {}
	refused: list[tuple[str, str, str]] = []
	unknown: list[tuple[str, str]] = []
	redundant: list[tuple[str, str]] = []
	dropped: list[tuple[str, str, str]] = []
	aliases: dict[str, str] = {}

	for path in paths:
		path = Path(path)
		raw = yaml.safe_load(path.read_text())
		if not isinstance(raw, dict):
			dropped.append((path.name, "<document>", "not a mapping at the top level"))
			continue
		counts: dict[str, int] = {}
		for key in raw:
			if key not in _FRAGMENT_REGISTERS:
				unknown.append((path.name, str(key)))

		for register in ("parameters", "equations"):
			body_map = raw.get(register) or {}
			if not isinstance(body_map, dict):
				dropped.append(
					(path.name, register, f"{type(body_map).__name__}, not a mapping")
				)
				continue
			for entry_id, body in body_map.items():
				if not isinstance(body, dict):
					dropped.append(
						(path.name, str(entry_id), f"body is {type(body).__name__}")
					)
					continue
				prior = seen.get((register, entry_id))
				if prior is not None:
					if prior[0] != body:
						refused.append((str(entry_id), prior[1], path.name))
					else:
						redundant.append((str(entry_id), path.name))
					continue
				seen[(register, entry_id)] = (body, path.name)
				old = shipped_bodies.get((register, entry_id))
				if old is not None and old != body:
					corrected.append((register, str(entry_id), path.name))
				document[register][entry_id] = dict(body)
				counts[register] = counts.get(register, 0) + 1

		for register in ("relationships", "cross_validation"):
			items = raw.get(register) or []
			if not isinstance(items, list):
				dropped.append(
					(path.name, register, f"{type(items).__name__}, not a list")
				)
				continue
			for item in items:
				if not isinstance(item, dict):
					dropped.append(
						(path.name, register, f"item is {type(item).__name__}")
					)
					continue
				key = item.get("id") or f"{item.get('source')}->{item.get('target')}"
				prior = seen.get((register, str(key)))
				if prior is not None:
					if prior[0] != item:
						refused.append((str(key), prior[1], path.name))
					else:
						redundant.append((str(key), path.name))
					continue
				shipped_item = shipped_bodies.get((register, str(key)))
				if shipped_item is not None:
					# A rule or edge re-shipped identically is redundant; one
					# that differs is a correction, which replaces the shipped
					# entry of the same key and is counted. Without this both
					# bakes would append, and the document would carry two
					# records of one coupling.
					if shipped_item == item:
						redundant.append((str(key), path.name))
						continue
					corrected.append((register, str(key), path.name))
					if register == "cross_validation":
						document[register] = [
							r for r in document[register] if str(r.get("id")) != str(key)
						]
					else:
						document[register] = [
							r
							for r in document[register]
							if str(r.get("id") or f"{r.get('source')}->{r.get('target')}") != str(key)
						]
				seen[(register, str(key))] = (item, path.name)
				document[register].append(dict(item))
				counts[register] = counts.get(register, 0) + 1

		alias_map = raw.get("aliases") or {}
		if isinstance(alias_map, dict):
			for old, new in alias_map.items():
				aliases[str(old)] = str(new)
			counts["aliases"] = counts.get("aliases", 0) + len(alias_map)
		per_file[path.name] = counts

	# A deprecated node's replacement must exist, and the alias register is
	# where a fragment states the mapping. Checked here rather than in the
	# node validator, which cannot see the rest of the document.
	known = set(document["parameters"])
	for old, new in aliases.items():
		if old not in known:
			dropped.append(("<aliases>", old, "alias for a parameter not declared"))
		elif new not in known:
			dropped.append(("<aliases>", old, f"replacement {new!r} is not declared"))
		elif (
			isinstance(body := document["parameters"].get(old), dict)
			and body.get("deprecated_by") not in (None, new)
		):
			refused.append(
				(old, "<alias register>", f"deprecated_by={body.get('deprecated_by')!r}")
			)

	# An edge whose equation no longer holds its source is a stale claim. The
	# loader used to refuse such an edge outright, which was right for the
	# shipped document -- a self-contradiction a reader should be told about
	# -- but wrong after a fragment *corrects* the equation: the correction
	# is the very thing that makes the shipped edge stale, and refusing it
	# would make symbol-changing equation corrections impossible to load.
	# A corrected equation's stale edges are therefore dropped here, and
	# named, so the disappearance is counted rather than silent.
	corrected_equations = {
		key for register, key, _file in corrected if register == "equations"
	}
	stale_edges: list[tuple[str, str, str]] = []
	if corrected_equations:
		kept: list[dict[str, Any]] = []
		for item in document["relationships"]:
			equation_id = str(item.get("equation_id") or "")
			equation = document["equations"].get(equation_id)
			if equation is None or equation_id not in corrected_equations:
				kept.append(item)
				continue
			# Stale is about the *arithmetic*, not the declared lists: the
			# declared lists are exactly what a correcting fragment may not
			# have touched, and an edge judged against them would stay live
			# while every reader of the rhs would call it gone.
			named = set(_parse_side_for_stale(equation))  # type: ignore[name-defined]
			source = str(item.get("source") or "")
			if source in named:
				kept.append(item)
			else:
				stale_edges.append(
					(equation_id, item.get("source") or "", item.get("target") or "")
				)
		document["relationships"] = kept
	dropped.extend(("<stale-edge>", eq, f"{src} -> {tgt}") for eq, src, tgt in stale_edges)

	report = IngestReport(
		per_file=per_file,
		refused=tuple(refused),
		unknown=tuple(unknown),
		redundant=tuple(redundant),
		corrected=tuple(corrected),
		dropped=tuple(dropped),
		counts={k: len(v) for k, v in document.items()},
	)
	return document, report


def load_ingested(
	directory: str | Path | None = None,
) -> tuple[ParameterGraph, IngestReport]:
	"""Load the shipped graph with every fragment in ``directory`` merged on.

	The default directory is ``config/prg_ingest/``, the location
	``docs/param_ingest.md`` names. Fragments are read in sorted filename
	order so the merge is deterministic -- the order matters only for which
	fragment a refusal *names first*, never for the result, because a
	duplicate whose bodies differ is refused rather than resolved by order.

	A directory that does not exist is not an error: it is the state of a tree
	with no fragments generated yet, and the answer is the shipped graph.
	"""
	directory = Path(directory) if directory is not None else default_ingest_dir()
	paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
	return ParameterGraph.from_fragments(paths)


#: ``(resolved path, mtime_ns, size) -> graph`` for the last document loaded.
#:
#: One entry, not a dict keyed by path. The workload is a long-lived API
#: serving one shipped graph, and a per-path table would grow without bound on
#: a service where every caller may name a different file -- the same
#: instance-retention leak ``ParameterGraph.feedback_loops`` avoids by caching
#: on the instance rather than in a class-level table.
_LOAD_CACHE: tuple[tuple[str, int, int], ParameterGraph] | None = None


def load_graph(path: str | Path | None = None) -> ParameterGraph:
	"""Load the shipped graph, or one at ``path``.

	Memoised on the *document's identity* -- its resolved path, mtime and size
	-- rather than on the path alone.

	WHY THIS IS CACHED, measured rather than assumed. Parsing the YAML is 73 ms
	and constructing the graph from the parsed mapping is 2 ms, so the cost is
	the parse and not the validation. The specification's §30 proposes a
	*propagation* cache keyed on a hash of the relevant parameter values; that
	caches the cheap half -- a full propagation is 6.5 ms and an incremental one
	6.1 ms, because the feedback-loop solve dominates both -- while every API
	request still paid the 73 ms parse. Caching the parse is what the workload
	actually asks for.

	WHY IT CANNOT SERVE A STALE ANSWER. The key is the file's mtime and size,
	not its path, so editing ``prg.yaml`` in place -- the case the previous
	"not cached, the file is small" comment was protecting against -- changes
	the key and the next call reloads. A rewrite that preserved both mtime and
	size would be served from the cache, which is why the size is in the key
	and not just the timestamp; that is the same identity check ``make`` uses,
	and it is honest about its limit rather than claiming content addressing it
	does not do.

	Callers who need to observe a change that preserves both can pass a path
	that resolves differently, or call :meth:`ParameterGraph.from_yaml`
	directly.
	"""
	global _LOAD_CACHE
	resolved = Path(path) if path is not None else default_prg_path()
	try:
		stat = resolved.stat()
		key = (str(resolved.resolve()), stat.st_mtime_ns, stat.st_size)
	except OSError:
		# A path that does not exist is `from_yaml`'s error to raise, with its
		# own message. Caching a failure here would report a missing file as a
		# cache miss forever.
		return ParameterGraph.from_yaml(resolved)
	if _LOAD_CACHE is not None and _LOAD_CACHE[0] == key:
		return _LOAD_CACHE[1]
	graph = ParameterGraph.from_yaml(resolved)
	_LOAD_CACHE = (key, graph)
	return graph
