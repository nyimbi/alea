# SPDX-License-Identifier: MIT
"""PRG models: parameter nodes, relationship edges, equations.

WHY the graph is *not* declared on the node. The specification's
``ParameterNode`` carries ``depends_on``, ``affects`` and ``equations`` lists
beside the edge set, so the same relationship is written twice -- once on the
node, once as an edge. Two records that agree today are not one source of
truth: the first change that adds an edge and forgets the node list leaves a
graph whose declared shape and actual shape differ, and the propagation engine
walks the *edges*, so it would propagate along a graph nobody described. So the
node holds only what is true of the parameter, the edge holds only what is true
of the relationship, and :meth:`ParameterGraph.structure_issues` asserts the
YAML's declared lists agree with the derived ones. That is the consistency
check the PRG exists to perform, applied to itself.

WHY ``unit`` is a string and not a Pint quantity. The unit is recorded as the
graph spells it -- ``MW.s``, ``m3``, ``MtCO2/year`` -- because it is read by
people, and the dimensional check in :mod:`alea.prg.units` normalises those
spellings to what Pint parses rather than asking the graph to spell them Pint's
way. A ``Quantity`` on the node would carry a scale the node does not have: a
parameter's unit is the dimension it lives in, and its value is a separate
field.

WHY the dimensional check lives in ``units.py`` and not here. An earlier
docstring in this module said there was no check because it "catches a class of
error this graph does not currently make". That was an assumption, and it was
false: the check finds seven equations whose two sides do not share a
dimension, including the emissions identity the carbon budget is built from.
``structure_issues`` still asserts the weaker thing -- that every parameter an
equation names carries a recorded unit -- which is a completeness check on the
metadata. The dimensional claim is now established, by ``units.check_graph``,
and this module no longer disclaims it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

#: A relation between two expressions. ``eq`` is the only one an equation can
#: be *solved* through; the inequalities are boundaries, and the propagation
#: engine treats them as slack rather than as a determination.
Relation = Literal["eq", "leq", "geq"]


class Role(StrEnum):
	"""What determines a parameter's value.

	``exogenous`` is set by the user or by data. ``endogenous`` is chosen by the
	optimiser. ``derived`` is computed from others by an equation, so it must
	not be set directly -- that is the whole point of the graph.
	``free`` is unconstrained within its range.
	"""

	EXOGENOUS = "exogenous"
	ENDOGENOUS = "endogenous"
	DERIVED = "derived"
	FREE = "free"


class Determinism(StrEnum):
	"""Why a value is what it is, which is not the same as who sets it."""

	FIXED = "fixed"
	STOCHASTIC = "stochastic"
	POLICY = "policy"
	PHYSICAL = "physical"


class ParameterType(StrEnum):
	FLOAT = "float"
	INT = "int"
	BOOL = "bool"
	CATEGORICAL = "categorical"
	TIMESERIES = "timeseries"
	SPATIAL = "spatial"


#: The types a scalar ``default``/``range`` cannot express. ``int`` and ``bool``
#: are scalars, so they are absent: an integer parameter's default is one number
#: and the range bounds it, which is exactly what this model carries.
_NON_SCALAR_TYPES: frozenset[ParameterType] = frozenset(
	{ParameterType.CATEGORICAL, ParameterType.TIMESERIES, ParameterType.SPATIAL}
)


class Priority(StrEnum):
	P1 = "P1"
	P2 = "P2"
	P3 = "P3"


class ParameterNode(BaseModel):
	"""One parameter. A node in the graph, and only that.

	The relationships this parameter takes part in are the edges whose source or
	target is ``id``. They are not repeated here; see the module docstring.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	id: str
	name: str
	description: str = ""
	category: str
	subcategory: str | None = None

	type: ParameterType
	unit: str | None = None
	range: tuple[float, float] | None = None
	default: float | None = None
	"""The value used when nothing else supplies one.

	Three roles read it three ways. For an *exogenous* node it is the value a
	scenario starts from. For an *endogenous* node it is the reference value
	used when no solve supplies the optimiser's own answer -- the graph's
	convenience paths build a value set from defaults, and a decision variable
	with no starting point makes every one of them unrunnable. A *derived*
	node must not carry one: its value comes from an equation, and a default is
	a value that would stand in whenever the equation is not run.
	"""

	initial: float | None = None
	"""Where a feedback loop starts iterating.

	Not a default. A default is the value used when nothing sets the parameter;
	a derived parameter has none, because its value comes from an equation. A
	*loop* variable has no equation that fixes it in one pass either -- it is a
	fixed point -- and the solver needs somewhere to start. Conflating the two
	would give a derived parameter a value that silently stands in for the
	equation whenever the equation is not run.
	"""

	role: Role
	determinism: Determinism

	source: str | None = None
	source_url: str | None = None
	users: tuple[str, ...] = ()
	priority: Priority = Priority.P2
	status: Literal["existing", "to_build", "integrate"] = "to_build"

	@model_validator(mode="after")
	def _range_contains_default(self) -> ParameterNode:
		# A default outside its own declared range is a contradiction the graph
		# can see and nothing else can: the value would be refused at
		# validation time and shipped as the starting point at the same time.
		if self.range is not None and self.default is not None:
			low, high = self.range
			if low > high:
				raise ValueError(f"{self.id}: range ({low}, {high}) is inverted")
			if not (low <= self.default <= high):
				raise ValueError(
					f"{self.id}: default {self.default} is outside its declared "
					f"range ({low}, {high})"
				)
		if self.role is Role.DERIVED and self.default is not None:
			raise ValueError(
				f"{self.id}: a derived parameter must not carry a default; its "
				f"value comes from an equation, and a default is a value that "
				f"would be used when the equation is not"
			)
		if self.role is Role.ENDOGENOUS and self.default is None:
			# The reference value, used when nothing else supplies one. A
			# `propagate` call takes a value set, and the graph's own
			# convenience paths build that set from defaults; an endogenous
			# node with none makes every one of them unrunnable, and the
			# alternative -- silently zero -- is a fleet of no units that the
			# reserve margin then reports as satisfied.
			raise ValueError(
				f"{self.id}: an endogenous parameter needs a `default` as its "
				f"reference value, used when no solve supplies one; a decision "
				f"variable with no starting point makes the graph unanswerable "
				f"and zero would read as a fleet of no units"
			)
		if self.role is Role.ENDOGENOUS and self.range is None:
			# The optimiser chooses this value, and a decision variable with no
			# bounds is one an LP may drive to infinity or to a negative
			# capacity -- both of which solve and neither of which is a fleet.
			# The range is the admissible set the graph states; for an
			# endogenous node it is also the only thing standing between the
			# solve and a nonsense optimum.
			raise ValueError(
				f"{self.id}: an endogenous parameter is chosen by the "
				f"optimiser, so it must declare the range the optimiser may "
				f"choose within; a decision variable with no bounds is one the "
				f"solve can drive anywhere"
			)
		if self.initial is not None:
			if self.role is not Role.DERIVED:
				raise ValueError(
					f"{self.id}: `initial` is where a feedback loop starts, and "
					f"{self.id} is {self.role.value} -- a value the user sets "
					f"needs no starting point"
				)
			if self.range is None:
				raise ValueError(
					f"{self.id}: `initial` needs a range to be checked against"
				)
			low, high = self.range
			if not (low <= self.initial <= high):
				raise ValueError(
					f"{self.id}: initial {self.initial} is outside its range "
					f"({low}, {high})"
				)
		if self.type in _NON_SCALAR_TYPES and (
			self.default is not None or self.range is not None
		):
			# A timeseries, a spatial field, or a categorical is not one number.
			# The scalar fields on this model cannot express one, and nothing
			# reads `type`, so a node declared `timeseries` with a scalar
			# `default` was accepted, propagated as a float, and reported as a
			# quantity -- the declared type constraining nothing. Refusing is
			# the whole of what the type field can do until something carries
			# the array; until then, `float` is the only type this model can
			# honestly accept, and a declaration that says otherwise is a
			# document that lies about the parameter.
			raise ValueError(
				f"{self.id}: type={self.type.value!r} cannot be carried by a "
				f"scalar `default` or `range`, and this model has no field for "
				f"the array; declare it `float` or leave the scalar fields unset"
			)
		return self


class Relationship(StrEnum):
	"""The seven classes of coupling ``params-prg1.md`` §2 names."""

	EQUALITY = "equality"
	INEQUALITY = "inequality"
	FUNCTIONAL = "functional"
	CONSTRAINT = "constraint"
	FEEDBACK = "feedback"
	TEMPORAL = "temporal"
	STOCHASTIC = "stochastic"


class Direction(StrEnum):
	FORWARD = "forward"
	BACKWARD = "backward"
	BIDIRECTIONAL = "bidirectional"


class Strength(StrEnum):
	"""How a violation should be treated.

	``hard`` is a contradiction. ``soft`` is a warning. ``informational`` is
	recorded and never blocks -- the spec's cross-validation hints are this.
	"""

	HARD = "hard"
	SOFT = "soft"
	INFORMATIONAL = "informational"


class RelationshipEdge(BaseModel):
	"""A directed relationship between two parameters, via one equation."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	source: str
	target: str
	equation_id: str
	relationship: Relationship
	direction: Direction = Direction.FORWARD
	strength: Strength = Strength.HARD
	description: str = ""
	reference: str | None = None
	priority: Priority = Priority.P1


class Equation(BaseModel):
	"""One equation of the library.

	``lhs`` and ``rhs`` are DSL source strings, parsed by
	:mod:`alea.prg.dsl`. They are kept as text rather than as a parsed tree so
	the YAML a human edits and the object the engine runs are the same artefact
	-- a library whose stored form is a serialised AST cannot be reviewed by the
	person who owns the physics.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	id: str
	name: str
	description: str = ""
	system: str

	lhs: str
	rhs: str
	relation: Relation = "eq"

	parameters: tuple[str, ...] = ()
	free_variables: tuple[str, ...] = ()
	determined_variables: tuple[str, ...] = ()

	tolerance: float = 1e-6
	reference: str | None = None
	priority: Priority = Priority.P1

	solution_method: Literal["direct", "iterative", "symbolic", "numeric"] = "numeric"
	linearity: Literal["linear", "nonlinear", "mixed"] = "linear"

	@model_validator(mode="after")
	def _a_derivation_has_exactly_one_target(self) -> Equation:
		# A determination is only meaningful for an equality: an inequality
		# bounds a value, it does not fix it, so an equation that both declares
		# a determined variable and is an inequality is a claim the engine
		# cannot honour. Refusing it here is cheaper than a propagation that
		# silently picks a boundary and calls it the answer.
		if self.relation != "eq" and self.determined_variables:
			raise ValueError(
				f"{self.id}: relation {self.relation!r} cannot determine "
				f"{list(self.determined_variables)}; an inequality bounds a "
				f"value, and only an equality fixes one"
			)
		if len(self.determined_variables) > 1:
			raise ValueError(
				f"{self.id}: determines {len(self.determined_variables)} "
				f"variables {list(self.determined_variables)}; one equation "
				f"determines one unknown, and a second target makes the system "
				f"under-determined in a way that reads as over-determined"
			)
		if self.tolerance <= 0:
			raise ValueError(f"{self.id}: tolerance must be positive")
		return self


__all__ = [
	"Determinism",
	"Direction",
	"Equation",
	"ParameterNode",
	"ParameterType",
	"Priority",
	"Relation",
	"Relationship",
	"RelationshipEdge",
	"Role",
	"Strength",
]
