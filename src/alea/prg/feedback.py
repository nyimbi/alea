# SPDX-License-Identifier: MIT
"""The feedback solver: the loops the topological order cannot evaluate.

WHY loops are a separate object and not edges. A cycle among *derived*
parameters has no evaluation order, so the graph refuses it -- that refusal is
correct, because an equation system with no order has no answer. A feedback
loop is a different claim: it says the system is at a fixed point of a map, and
each turn of the loop re-evaluates an equation against the previous turn's
values. ``vre_capacity`` depends on ``capture_price``, which depends on
``vre_share``, which depends on ``vre_capacity`` -- and that is not a malformed
graph, it is the cannibalisation feedback ``params-prg1.md`` §2 class 6 names,
which converges to a build nobody wants to build more of.

The distinction is carried by ``solution_method``: an equation marked
``iterative`` is not a derivation, and the graph's topological order excludes
it. The loops are then found by strongly connected components over the
iterative equations, which makes the *number* of loops a measured fact rather
than a claim in a document.

WHY the convergence criterion is on the values and not on the residual. A loop
can sit at a residual below tolerance while its values oscillate around a limit
cycle of that amplitude, and reporting convergence there hands back a number
that is not a fixed point. The check is the change between successive turns,
which is the thing a limit cycle keeps large.

WHY THERE IS NO ACCELERATION, having tried it. Aitken's Δ² extrapolation was
implemented, gated on the sequence having settled, and vetted against the
declared ranges -- and it made the capture-price loop **2.2x slower** (84 turns
against 38), then drove the capacity to -61,694 MW. The reason is measurable
from the iteration: the capacity variable's map has a *negative* eigenvalue, so
its iterates alternate (3683, 3342, 3050, 2371, 3800) while the share and the
price converge monotonically. Δ² extrapolation assumes a real dominant
eigenvalue and amplifies the alternating component instead of damping it, which
is why the step kept having to be reverted and why it eventually left the
range. Plain damped relaxation cannot leave the range at all: each iterate is a
convex combination of the current value and a root the solver has already
bracketed, and both are inside it. An extrapolation that is slower and can
diverge is not an optimisation, and shipping it behind a heuristic that hides
that would be worse than shipping nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from alea.prg.dsl import DslError, Expr, evaluate, parse, parse_side, solve_for
from alea.prg.views import Equation

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"FeedbackError",
	"FeedbackLoop",
	"LoopResult",
	"detect_loops",
	"solve_loop",
]


class FeedbackError(RuntimeError):
	"""A loop did not converge, or cannot be evaluated."""


@dataclass(frozen=True)
class FeedbackLoop:
	"""A set of parameters that determine each other."""

	id: str
	variables: tuple[str, ...]
	equations: tuple[Equation, ...]
	tolerance: float = 1e-8
	max_iterations: int = 200
	damping: float = 0.5

	def __str__(self) -> str:
		return f"{self.id}({', '.join(self.variables)})"


@dataclass(frozen=True)
class LoopResult:
	"""What the solver did."""

	loop: str
	values: dict[str, float]
	iterations: int
	change: float
	converged: bool


def detect_loops(graph: ParameterGraph) -> tuple[FeedbackLoop, ...]:
	"""The loops among the graph's iterative equations.

	Tarjan's algorithm over the iterative equations' dependency graph, keeping
	single-node components: an iterative equation with no cycle is still
	iterated -- that is what ``solution_method="iterative"`` means -- and
	dropping it would leave its variable unset with nothing reporting why.
	"""
	iterative = {
		equation.determined_variables[0]: equation
		for equation in graph.equations.values()
		if equation.solution_method == "iterative" and equation.determined_variables
	}
	if not iterative:
		return ()

	edges: dict[str, set[str]] = {}
	for name, equation in iterative.items():
		named = set(equation.parameters) | set(equation.free_variables)
		# A dependency on an exogenous parameter is an input to the loop, not
		# part of its cycle.
		edges[name] = {other for other in named if other in iterative}

	loops: list[FeedbackLoop] = []
	for index, component in enumerate(_strongly_connected(edges)):
		members = tuple(sorted(component))
		equations = tuple(iterative[name] for name in members)
		loops.append(
			FeedbackLoop(
				id=f"loop_{index + 1}_" + "_".join(members[:2]),
				variables=members,
				equations=equations,
				tolerance=max(equation.tolerance for equation in equations),
			)
		)
	return tuple(loops)


def _strongly_connected(edges: dict[str, set[str]]) -> list[set[str]]:
	"""Tarjan's SCC, iteratively so a deep graph cannot overflow the stack.

	The recursive form is a function call per node; this keeps the same state
	on an explicit stack of ``(node, unvisited successors)`` frames. The
	invariant that makes the control flow readable: the frame on top of
	``work`` is the node currently being explored, and a frame is popped only
	once its ``pending`` list is empty -- at which point its ``low`` is final
	and is propagated to its parent, which is the frame now on top. The two
	``continue``s are the "descend, or resume the parent" steps and not loop
	restarts: neither consumes the frame, and the ``pending`` list shrinking by
	one per turn is what guarantees termination.
	"""
	index_of: dict[str, int] = {}
	low: dict[str, int] = {}
	on_stack: set[str] = set()
	stack: list[str] = []
	components: list[set[str]] = []
	counter = 0

	for root in edges:
		if root in index_of:
			continue
		index_of[root] = low[root] = counter
		counter += 1
		stack.append(root)
		on_stack.add(root)
		work: list[tuple[str, list[str]]] = [(root, sorted(edges[root]))]
		while work:
			node, pending = work[-1]
			if pending:
				child = pending.pop()
				if child not in index_of:
					index_of[child] = low[child] = counter
					counter += 1
					stack.append(child)
					on_stack.add(child)
					work.append((child, sorted(edges[child])))
				elif child in on_stack:
					low[node] = min(low[node], index_of[child])
				continue
			work.pop()
			if work:
				parent = work[-1][0]
				low[parent] = min(low[parent], low[node])
			if low[node] == index_of[node]:
				component: set[str] = set()
				while True:
					member = stack.pop()
					on_stack.discard(member)
					component.add(member)
					if member == node:
						break
				components.append(component)
	return components


def solve_loop(
	graph: ParameterGraph,
	loop: FeedbackLoop,
	values: dict[str, float],
) -> LoopResult:
	"""Iterate ``loop`` to a fixed point, mutating ``values`` in place.

	One Gauss-Seidel sweep per turn: each equation is solved for its own
	variable against the current values of the others, and the new value is
	written immediately, so the next equation in the turn sees it. Jacobi would
	need a second copy of the parameter set and converges no faster here.
	"""
	residuals = {
		equation.determined_variables[0]: _residual(equation)
		for equation in loop.equations
	}
	for name in loop.variables:
		if name in values:
			continue
		node = graph.node(name)
		if node.initial is not None:
			values[name] = float(node.initial)
		elif node.range is not None:
			# The midpoint of the declared range: a starting iterate, and the
			# only one available without a declaration. The solver is a
			# contraction, so where it starts changes how many turns it takes
			# and not what it converges to.
			low, high = node.range
			values[name] = 0.5 * (low + high)
		else:
			raise FeedbackError(
				f"{loop} solves for {name}, which has no value, no declared "
				f"initial and no range; the loop has nothing to iterate from"
			)

	change = float("inf")
	#: The last few steps per variable, so a loop that fails can say whether it
	#: failed by diverging or by oscillating. A damping factor too large for a
	#: map with a negative eigenvalue shows up as a step that alternates sign
	#: without shrinking, and the fix -- halve the damping -- is different from
	#: the fix for a diverging loop. Reporting only "did not converge" leaves
	#: the reader to guess which one they have.
	steps: dict[str, list[float]] = {name: [] for name in loop.variables}
	for turn in range(1, loop.max_iterations + 1):
		previous = {name: values[name] for name in loop.variables}
		for equation in loop.equations:
			target = equation.determined_variables[0]
			node = graph.node(target)
			if node.range is None:
				raise FeedbackError(
					f"{loop}: {target} is iterated but declares no range, so the "
					f"solver has no bracket"
				)
			try:
				solved = solve_for(
					residuals[target], target, values, bracket=node.range
				)
			except DslError as exc:
				raise FeedbackError(
					f"{loop}: cannot solve {equation.id!r} for {target}: {exc}"
				) from exc
			# Relaxation: the raw map can overshoot and oscillate between two
			# builds, neither of which is the fixed point.
			values[target] = values[target] + loop.damping * (solved - values[target])

		for name in loop.variables:
			steps[name].append(values[name] - previous[name])
			del steps[name][:-6]

		# Relative, not absolute. The loop mixes a capture price in USD/MWh
		# with a capacity in MW, and an absolute tolerance tight enough for the
		# first is 4e-12 relative on the second -- which is not convergence, it
		# is the floating-point floor. Scaling by each variable's own magnitude
		# is what `ParameterGraph.consistency` already does for the same reason.
		change = max(
			abs(values[name] - previous[name]) / max(abs(values[name]), 1.0)
			for name in loop.variables
		)
		# Two criteria, and the second is the one that matters. Iterates
		# stopping is not the equations holding: with damping the residual is
		# the step divided by the damping factor, so a loop that stops at 1e-8
		# on its iterates can sit at 2e-8 on the equation -- outside the
		# tolerance `consistency` checks it against, and reported as a violation
		# of an equation the solver considered solved. Converging on the
		# residual is converging on what the answer is *checked* by.
		if change <= loop.tolerance and _residuals_hold(graph, loop, values):
			return LoopResult(
				loop=loop.id,
				values={name: values[name] for name in loop.variables},
				iterations=turn,
				change=change,
				converged=True,
			)

	raise FeedbackError(
		f"{loop} did not converge in {loop.max_iterations} turns; the last "
		f"change was {change:.6g}, above {loop.tolerance:.3g}. "
		f"{_diagnose(steps, loop)}"
	)


def _diagnose(steps: Mapping[str, list[float]], loop: FeedbackLoop) -> str:
	"""Say which failure this is, because the two have different fixes.

	A step sequence that alternates in sign without shrinking is an
	oscillation -- a map with a negative eigenvalue and a damping factor too
	large for it, fixed by lowering the damping. A step sequence that grows is
	a divergence, fixed by bounding the range or by a different formulation.
	"Did not converge" alone leaves the reader to guess.
	"""
	for name, history in steps.items():
		signs = [s for s in history if s != 0.0]
		if len(signs) < 4:
			continue
		alternating = all(
			(a > 0) != (b > 0) for a, b in zip(signs, signs[1:], strict=False)
		)
		shrinking = abs(signs[-1]) < abs(signs[0])
		if alternating and not shrinking:
			return (
				f"{name} is oscillating: its steps alternate in sign without "
				f"shrinking. That is a contraction factor near -1, and the fix "
				f"is a smaller damping factor than {loop.damping} -- not a "
				f"wider range."
			)
		if not alternating and abs(signs[-1]) > abs(signs[0]):
			return (
				f"{name} is diverging: its steps grow. That is a contraction "
				f"factor above one at these values, and a smaller damping "
				f"factor will not fix it -- the equation or its range is wrong."
			)
	return (
		"the steps are neither growing nor alternating, so this is slow "
		"convergence rather than divergence: raise `max_iterations`."
	)


def _residual(equation: Equation) -> Expr:
	return parse(f"({equation.lhs}) - ({equation.rhs})")


def _residuals_hold(
	graph: ParameterGraph, loop: FeedbackLoop, values: Mapping[str, float]
) -> bool:
	"""Whether every equation of the loop holds at ``values``.

	The same scaled comparison ``ParameterGraph.consistency`` applies, so a
	loop that reports convergence is a loop whose answer passes the check that
	will be run on it. A solver whose stopping rule is weaker than its audit's
	produces answers that are reported as violations of equations it declared
	solved.
	"""
	for equation in loop.equations:
		residual = abs(evaluate(_residual(equation), values))
		scale = max(
			1.0,
			abs(evaluate(parse_side(equation.lhs), values)),
			abs(evaluate(parse_side(equation.rhs), values)),
		)
		if residual / scale > equation.tolerance:
			return False
	return True
