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

WHY ``unit`` is a string and not a Pint quantity. The specification asks for
Pint. Pint is not a dependency of this repository, and adding one is a real
cost -- it changes the solve environment for a check that catches a class of
error this graph does not currently make. The unit is recorded so that a reader
and a later dimensional check have it, and :func:`ParameterGraph.structure_issues`
enforces the weaker property that *is* free: every equation's arithmetic is
over symbols whose recorded units are present, so a missing unit is a finding
rather than a silent dimensionless quantity.
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
