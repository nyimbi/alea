# SPDX-License-Identifier: MIT
"""How much a derived parameter moves when an input moves.

WHY forward-mode differentiation over the topological order, and not finite
differences. The graph already knows the order in which parameters are
computed, and every equation is a differentiable expression, so the derivative
of a derived parameter with respect to an exogenous input is a chain of partial
derivatives along the path that computes it. That is exact. A difference
quotient would carry a truncation error that has to be tuned per parameter --
the right step for a capacity in MW is the wrong one for a capacity factor in
[0, 1] -- and the tuned step is exactly what makes a sensitivity report
irreproducible between two runs at different values.

WHY the implicit form for a loop, and not a re-solve. A loop variable is not
computed by a formula; it is the solution of a system ``F(z, x) = 0``. The
derivative is ``dz/dx = -(dF/dz)^-1 (dF/dx)``, a small linear solve over the
loop's own variables -- three of them in this library. Perturbing the input and
re-converging would give a number that depends on the solver's tolerance, and
the loop's tolerance is 1e-8: the difference quotient would be dominated by
solver noise for any step small enough to be local.

WHY sensitivity is not the same as `affects`. `affects` answers *whether* a
parameter reaches another; this answers *how much*, as a number. A report that
ranked corrections by `affects` would rank every lever equally, which is the
same as not ranking them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from alea.prg.dsl import DslError, Expr, parse

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"GradientTable",
	"Sensitivity",
	"elasticity",
	"gradients",
	"sensitivity",
	"sensitivity_table",
]


@dataclass(frozen=True)
class Sensitivity:
	"""One derived parameter's derivative with respect to each input."""

	parameter: str
	derivatives: dict[str, float]
	"""Input name -> ``d(parameter)/d(input)``, at the values given."""

	method: str
	"""``symbolic`` for a parameter computed by a chain of formulas,
	``implicit`` for a loop variable fixed by a system."""

	values: dict[str, float] = field(default_factory=dict)

	def largest(self, count: int = 5) -> list[tuple[str, float]]:
		"""The inputs this parameter is most sensitive to, by magnitude."""
		ranked = sorted(
			self.derivatives.items(), key=lambda kv: abs(kv[1]), reverse=True
		)
		return ranked[:count]

	def __str__(self) -> str:
		if not self.derivatives:
			return f"{self.parameter}: no settable input reaches it"
		top = ", ".join(f"{name} {value:+.4g}" for name, value in self.largest(4))
		return f"{self.parameter} ({self.method}): {top}"


@dataclass(frozen=True)
class GradientTable:
	"""``d(parameter)/d(input)`` for every derived parameter at one point.

	Computed in a single pass because the chain rule is shared: the gradient of
	a parameter is built from the gradients of the parameters it is computed
	from, so asking for one parameter's sensitivity and asking for all of them
	cost the same walk. Recomputing per parameter would repeat the whole
	topological sweep once per question.
	"""

	values: dict[str, float]
	table: dict[str, dict[str, float]]
	inputs: tuple[str, ...]
	loops: tuple[str, ...]

	def of(self, parameter: str) -> Sensitivity:
		derivatives = self.table.get(parameter)
		if derivatives is None:
			raise KeyError(
				f"{parameter!r} is not a derived parameter, so it has no "
				f"derivative; it is an input, and an input's derivative with "
				f"respect to itself is one"
			)
		# Inputs are seeded into the table so the chain rule can read their rows,
		# which means membership in `inputs` -- not absence from the table -- is
		# what identifies one. Testing absence here reported every input as
		# `symbolic`, which is the wrong method for a knob that computes nothing.
		if parameter in self.inputs:
			method = "input"
		elif parameter in self.loops:
			method = "implicit"
		else:
			method = "symbolic"
		return Sensitivity(
			parameter=parameter,
			derivatives=dict(derivatives),
			method=method,
			values=dict(self.values),
		)

	def matrix(self) -> dict[str, dict[str, float]]:
		"""The whole table, keyed by derived parameter then input."""
		return {name: dict(row) for name, row in self.table.items()}


def _residual(equation: Any) -> Expr:
	"""``lhs - rhs`` as an expression, the form implicit differentiation needs.

	An equation is stated as two sides that agree; a derivative needs the
	difference, because it is the difference that is held at zero. Reusing the
	equation's own text means the sensitivity is taken against the equation the
	engine solves, not against a rearrangement of it that could disagree.
	"""
	return parse(equation.lhs) - parse(equation.rhs)


def _partials(expression: Expr, values: Mapping[str, float]) -> dict[str, float]:
	"""Every partial derivative of ``expression`` at ``values``.

	A partial that cannot be taken -- a ``min`` or a ``max`` in the equation --
	raises rather than being dropped, because a sensitivity report that
	silently omits one term is a report of a different equation.
	"""
	out: dict[str, float] = {}
	for name in sorted(expression.symbols):
		try:
			out[name] = float(expression.diff(name)._eval(values))
		except DslError as exc:
			raise DslError(
				f"cannot differentiate {expression.source()} with respect to "
				f"{name!r}: {exc}"
			) from exc
	return out


def gradients(
	graph: ParameterGraph, values: Mapping[str, float]
) -> GradientTable:
	"""``d(parameter)/d(input)`` for every derived parameter, in one pass.

	The chain rule over the graph's own topological order. Inputs are seeded
	with a unit derivative in themselves and zero elsewhere; each derived
	parameter then takes its gradient from the parameters its equation names.
	A loop variable is fixed by the implicit function theorem instead, because
	no formula computes it.
	"""
	settable = tuple(sorted(name for name in graph.nodes if graph.is_settable(name)))
	loop_variables = tuple(sorted(graph.computed() & set(_loop_names(graph))))
	table: dict[str, dict[str, float]] = {}

	# Seed the inputs. An input's derivative with respect to itself is one, and
	# to every other input zero -- so an input is not in `table` at all, and
	# `of()` says so rather than reporting a row of zeros that would read as
	# "this input reaches nothing".
	for name in settable:
		table[name] = {name: 1.0}

	order, waiting = graph.order(), set(graph._phases()[1])

	# A parameter that waits on a loop cannot be computed before the loop's
	# gradient is known, so the acyclic sweep is cut in the same two phases
	# `propagate` uses.
	for phase in (False, True):
		for parameter in order:
			if (parameter in waiting) is not phase:
				continue
			if parameter in loop_variables:
				continue
			equation = graph.determined_by(parameter)
			if equation is None:
				continue
			table[parameter] = _chain(equation, parameter, table, values, settable)

	for loop in graph.feedback_loops():
		for parameter, row in _loop_gradients(loop, values, settable).items():
			table[parameter] = row

	# A parameter that waited on the loop was skipped above only if it *is* a
	# loop variable; the rest were computed in the second phase with the loop
	# rows already present, so nothing is left dangling.
	return GradientTable(
		values=dict(values),
		table=table,
		inputs=settable,
		loops=loop_variables,
	)


def _loop_names(graph: ParameterGraph) -> set[str]:
	out: set[str] = set()
	for loop in graph.feedback_loops():
		out.update(loop.variables)
	return out


def _chain(
	equation: Any,
	parameter: str,
	table: dict[str, dict[str, float]],
	values: Mapping[str, float],
	settable: tuple[str, ...],
) -> dict[str, float]:
	"""One derived parameter's gradient, from the equation that fixes it.

	Implicit form: the equation is ``F = 0`` in ``parameter`` and the others,
	so ``d(parameter)/d(q) = -(dF/dq) / (dF/dparameter)`` for every other name
	``q`` the equation carries. Reading it this way means the parameter does
	not have to be alone on one side, which most of these equations do not
	guarantee.
	"""
	residual = _residual(equation)
	partials = _partials(residual, values)
	own = partials.get(parameter)
	if own is None or own == 0.0:
		# The parameter does not appear in its own determining equation, or
		# appears with a zero derivative. Either way the equation does not fix
		# it locally and the derivative is not defined by this route.
		raise DslError(
			f"{equation.id!r} determines {parameter!r} but its derivative with "
			f"respect to it is {own!r}; a determining equation must change when "
			f"the parameter it determines changes"
		)
	row: dict[str, float] = {name: 0.0 for name in settable}
	for other, partial in partials.items():
		if other == parameter:
			continue
		weight = -partial / own
		upstream = table.get(other)
		if upstream is None:
			continue
		for name, derivative in upstream.items():
			row[name] += weight * derivative
	return {name: value for name, value in row.items() if value != 0.0}


def _loop_gradients(
	loop: Any,
	values: Mapping[str, float],
	settable: tuple[str, ...],
) -> dict[str, dict[str, float]]:
	"""``dz/dx`` for a loop's variables, by the implicit function theorem.

	``F(z, x) = 0`` gives ``J dz/dx = -dF/dx`` with ``J = dF/dz``. The system
	is solved rather than inverted: the loop is a contraction at its fixed
	point, so ``J`` is well-conditioned, but inverting it explicitly is both
	slower and less accurate than one solve per input.
	"""
	variables = tuple(loop.variables)
	residuals = [_residual(equation) for equation in loop.equations]
	rows: list[list[float]] = []
	for residual in residuals:
		partials = _partials(residual, values)
		rows.append([partials.get(name, 0.0) for name in variables])
	jacobian = np.asarray(rows, dtype=float)
	# The equations come in the loop's own order and so do the variables, but
	# the pairing is by `determined_variables`, not by position, so a loop whose
	# equations are not in variable order would build a transposed system. The
	# reorder is explicit for that reason.
	order = [variables.index(eq.determined_variables[0]) for eq in loop.equations]
	jacobian = jacobian[order] if len(set(order)) == len(order) else jacobian

	out: dict[str, dict[str, float]] = {}
	for name in settable:
		rhs = np.zeros(len(residuals), dtype=float)
		for index, residual in enumerate(residuals):
			partials = _partials(residual, values)
			rhs[index] = -partials.get(name, 0.0)
		if not np.any(rhs):
			out_target = np.zeros(len(variables))
		else:
			try:
				out_target = np.linalg.solve(jacobian, rhs)
			except np.linalg.LinAlgError:
				# A singular Jacobian at the fixed point means the loop is not
				# locally invertible there, so the derivative does not exist.
				# Reported as a zero row would be a lie; raising names it.
				raise DslError(
					f"the loop {loop} has a singular Jacobian at these values, "
					f"so its variables have no derivative with respect to "
					f"{name!r} here"
				) from None
		for variable, derivative in zip(variables, out_target, strict=True):
			out.setdefault(variable, {name: 0.0 for name in settable})[name] = float(
				derivative
			)
	return {
		variable: {n: v for n, v in row.items() if v != 0.0}
		for variable, row in out.items()
	}


def sensitivity(
	graph: ParameterGraph,
	parameter: str,
	values: Mapping[str, float],
	*,
	table: GradientTable | None = None,
) -> Sensitivity:
	"""One parameter's derivative with respect to every settable input.

	An input is its own unit derivative and zero elsewhere, and ``of`` reports
	that from the seeded row rather than this function special-casing it: two
	routes to the same answer is two answers to keep in step, and the earlier
	one here returned a row that dropped the zeros the table carries.
	"""
	gradient_table = table if table is not None else gradients(graph, values)
	return gradient_table.of(parameter)


def sensitivity_table(
	graph: ParameterGraph,
	values: Mapping[str, float],
	*,
	outputs: tuple[str, ...] | None = None,
) -> dict[str, dict[str, float]]:
	"""The gradient matrix, optionally restricted to ``outputs``."""
	table = gradients(graph, values)
	if outputs is None:
		return table.matrix()
	return {name: dict(table.table.get(name, {})) for name in outputs}


def elasticity(
	graph: ParameterGraph,
	parameter: str,
	values: Mapping[str, float],
	*,
	table: GradientTable | None = None,
) -> dict[str, float]:
	"""Dimensionless sensitivity: the percentage move per percentage move.

	``(x/y)(dy/dx)``. The derivative alone is not comparable across inputs with
	different units -- a carbon price in USD/tonne and a capacity factor in
	[0, 1] produce derivatives of wildly different magnitude for the same
	real-world importance -- and a ranking that mixes them ranks the units.
	"""
	gradient_table = table if table is not None else gradients(graph, values)
	row = sensitivity(graph, parameter, values, table=gradient_table)
	level = values.get(parameter)
	if level in (None, 0.0):
		raise ValueError(
			f"{parameter!r} has value {level!r}, so its elasticity is not "
			f"defined; an elasticity is a ratio and a zero denominator has none"
		)
	out: dict[str, float] = {}
	for name, derivative in row.derivatives.items():
		input_level = values.get(name)
		if input_level in (None, 0.0):
			continue
		out[name] = float(derivative * input_level / level)
	return out
