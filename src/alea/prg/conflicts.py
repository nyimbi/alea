# SPDX-License-Identifier: MIT
"""Why a scenario is inconsistent, and what to move to fix it.

WHY this is a separate module from `graph.consistency`. ``consistency`` answers
*which equations fail* -- a residual against a tolerance, which is what a solver
and a test need. This answers *what a person should do about it*: which kind of
inconsistency it is, which input is responsible, and by how much it would have
to move. Those are different questions, and merging them would put a suggestion
in the path of the solver, which does not want one.

WHY the four kinds are distinguished rather than collapsed into "inconsistent".
They have different fixes and different owners. A *direct conflict* is one
person's number contradicting an equation, fixed by changing that number. An
*over-determined* set is two people setting the same coupled quantity, fixed by
deciding which one is authoritative. A *loop conflict* is a feedback system with
no fixed point at these inputs, fixed by widening a range or correcting the
formulation. An *out-of-range* derivation is the arithmetic producing a value
nobody would sign off, fixed by checking the inputs that produced it. A report
that says only "inconsistent" makes the reader work out which they have.

WHY corrections are ranked by elasticity and not by the raw derivative. The
derivative is not comparable across inputs with different units: a carbon price
in USD/tonne and a capacity factor in [0, 1] produce derivatives whose
magnitudes differ by orders for the same real-world importance, so a ranking on
the derivative ranks the units. The elasticity is dimensionless, which is what
makes the ranking mean something.

WHY the suggestion is a *direction and a magnitude*, not a new value to adopt.
The engine can compute that moving `tariff_usd_per_mwh` by +12 would close the
gap; it cannot know that the tariff is contractually fixed and the capacity
factor is the only lever actually available. Presenting the correction as a
number to accept would invite exactly that mistake, so it is presented as a
move, with its cost in units the reader can judge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from alea.prg.dsl import DslError
from alea.prg.graph import Violation

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"Conflict",
	"ConflictKind",
	"ConflictReport",
	"Correction",
	"detect_conflicts",
	"suggest_corrections",
]


class ConflictKind(StrEnum):
	"""What sort of inconsistency this is, because the fix differs by kind."""

	DIRECT = "direct"
	"""A set value contradicts an equation that fixes it."""

	OVER_DETERMINED = "over_determined"
	"""A value was set for a parameter the graph computes from others."""

	UNDER_DETERMINED = "under_determined"
	"""A parameter is needed and nothing supplies it."""

	LOOP = "loop"
	"""A feedback system has no fixed point at these inputs."""

	OUT_OF_RANGE = "out_of_range"
	"""The arithmetic produced a value outside the range declared for it."""


@dataclass(frozen=True)
class Correction:
	"""One input move that would reduce a conflict, and what it costs."""

	parameter: str
	delta: float
	"""How far to move it, in the parameter's own unit. Signed."""

	elasticity: float
	"""``(x/y)(dy/dx)``: the fractional move in the target per fractional move
	in the input. Dimensionless, which is what makes corrections comparable."""

	within_range: bool
	"""Whether the corrected value lands inside the parameter's declared range.

	A correction that leaves the range is not a correction: it trades an
	inconsistency for an out-of-range value, and the reader should see that
	rather than discover it on the next run.
	"""

	current: float = 0.0
	"""The value the move starts from, so ``relative_move`` is defined.

	Carried on the correction rather than looked up by the report, because the
	report holds no values: a caller that formatted a correction against a
	*different* point would print a percentage of a number the move was never
	computed from.
	"""

	@property
	def relative_move(self) -> float:
		"""The move as a fraction of the current value, for a report.

		Zero when the current value is zero, where a fraction is undefined
		rather than infinite: a correction from zero has no percentage form and
		reporting ``inf`` would read as a huge move rather than an absent ratio.
		"""
		return self.delta / self.current if self.current else 0.0

	def __str__(self) -> str:
		bound = "" if self.within_range else " (leaves its declared range)"
		return (
			f"{self.parameter} {self.delta:+.4g} "
			f"[elasticity {self.elasticity:+.3g}]{bound}"
		)

	def rank_key(self) -> tuple[float, float]:
		"""Least invasive first, as ``(relative move, absolute move)``.

		The relative move is the comparison that means something: a 0.2 move in
		an emission factor and an 82 USD/t move in a carbon price are the same
		real-world size if their parameters are, and ranking on the raw delta
		would put the first ahead of the second for no reason but its unit --
		the same mistake this module refuses when it ranks by elasticity rather
		than by derivative. A parameter sitting at zero has no relative move, so
		it sorts last rather than first.
		"""
		fraction = abs(self.relative_move) if self.current else float("inf")
		return (fraction, abs(self.delta))


@dataclass(frozen=True)
class Conflict:
	"""One inconsistency, with its kind and the inputs that could resolve it."""

	kind: ConflictKind
	subject: str
	"""The equation id, parameter name, or loop id this is about."""

	detail: str
	residual: float = 0.0
	tolerance: float = 0.0
	corrections: tuple[Correction, ...] = ()
	strength: str = "hard"
	"""The strength of the equation this came from, when it came from one.

	An arithmetic conflict inherits the strength of the edge that declared the
	equation. An input-level conflict -- over- and under-determination -- is a
	contradiction the scenario states about itself and has no edge to inherit
	from, so it stays ``hard``: nothing softened it.
	"""

	@property
	def blocks(self) -> bool:
		"""Whether this conflict invalidates the scenario rather than advising.

		``informational`` is the spec's "reported correlation": a scenario that
		breaks one is a finding worth printing and not a contradiction. Read
		here rather than at the print site, so the CLI, the API and the report
		all answer the same question the same way.
		"""
		return self.strength != "informational"

	def __str__(self) -> str:
		tier = "" if self.strength == "hard" else f" [{self.strength}]"
		head = f"{self.kind.value}{tier}: {self.subject} -- {self.detail}"
		if not self.corrections:
			return head
		ranked = "; ".join(str(correction) for correction in self.corrections[:3])
		return f"{head}\n    try: {ranked}"


@dataclass(frozen=True)
class ConflictReport:
	"""Everything wrong with a scenario, by kind, with ranked corrections."""

	conflicts: tuple[Conflict, ...]
	checked: tuple[str, ...]
	"""Derived parameters the scenario carried values for, so they were checked."""

	def of_kind(self, kind: ConflictKind) -> tuple[Conflict, ...]:
		return tuple(c for c in self.conflicts if c.kind is kind)

	@property
	def consistent(self) -> bool:
		"""Whether the scenario holds against every equation that *contradicts*.

		An ``informational`` conflict is excluded, and the exclusion is the
		point: the spec calls those reported correlations, and a check that
		called a broken correlation an inconsistency would gate on a number it
		was never asked to enforce. They remain in :attr:`conflicts`, so nothing
		is hidden -- :meth:`informational` names them and :attr:`blocks` is what
		a gate should read.
		"""
		return not any(conflict.blocks for conflict in self.conflicts)

	@property
	def blocks(self) -> bool:
		"""Whether any conflict should make a check exit non-zero."""
		return not self.consistent

	def informational(self) -> tuple[Conflict, ...]:
		"""The findings that advise rather than contradict."""
		return tuple(conflict for conflict in self.conflicts if not conflict.blocks)

	def summary(self) -> str:
		if self.consistent:
			tail = (
				f"; {len(self.conflicts)} informational finding(s)"
				if self.conflicts
				else ""
			)
			return (
				f"no conflicts over {len(self.checked)} checked parameter(s){tail}"
			)
		counts: dict[str, int] = {}
		for conflict in self.conflicts:
			counts[conflict.kind.value] = counts.get(conflict.kind.value, 0) + 1
		parts = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))
		return f"{len(self.conflicts)} conflict(s): {parts}"

	def ranked(self) -> tuple[Conflict, ...]:
		"""Most severe first: over-determination, then direct, loop, range.

		Ordered by how much of the scenario the conflict invalidates, not by
		residual size. An over-determined set means two of the scenario's own
		inputs disagree and every number downstream is suspect; an out-of-range
		derivation is one value nobody would sign off, with the rest sound.
		"""
		severity = {
			ConflictKind.OVER_DETERMINED: 0,
			ConflictKind.UNDER_DETERMINED: 1,
			ConflictKind.LOOP: 2,
			ConflictKind.DIRECT: 3,
			ConflictKind.OUT_OF_RANGE: 4,
		}
		return tuple(sorted(self.conflicts, key=lambda c: severity[c.kind]))


def detect_conflicts(
	graph: ParameterGraph,
	values: Mapping[str, float | str],
	*,
	supplied: Mapping[str, float | str] | None = None,
	rank: int = 5,
) -> ConflictReport:
	"""Every inconsistency in ``values``, with ranked corrections.

	``supplied`` is what the caller *set*, which is what makes over- and
	under-determination detectable: the graph can compute a derived parameter
	from its inputs, so a value handed in for one is a second opinion about a
	quantity that already has one. Without it, only the arithmetic can be
	checked and the input-level conflicts are invisible.
	"""
	from alea.prg.feedback import FeedbackError

	# Every correction here is a *move* -- a delta divided by a derivative -- so
	# it is arithmetic and a level name has none. Narrowing once at the door is
	# what keeps that honest: a categorical is not a quantity the residual can
	# be reduced by, and the alternative -- letting a level name reach
	# `_corrections_for` -- is a TypeError naming neither the parameter nor the
	# reason. The set the graph hands over is the whole graph's, so the numeric
	# half is selected here rather than promised by the caller.
	numeric: dict[str, float] = {
		k: v for k, v in values.items() if not isinstance(v, str)
	}
	supplied_numeric: dict[str, float] | None = (
		None
		if supplied is None
		else {k: v for k, v in supplied.items() if not isinstance(v, str)}
	)
	values = numeric
	supplied = supplied_numeric

	conflicts: list[Conflict] = []

	# Over-determination first: a caller who set a derived parameter has
	# contradicted the graph's own computation, and every residual below may be
	# a consequence of that rather than an independent finding.
	if supplied:
		for name in sorted(set(supplied) & set(graph.computed())):
			equation = graph.determined_by(name)
			by = equation.id if equation is not None else "a feedback loop"
			conflicts.append(
				Conflict(
					kind=ConflictKind.OVER_DETERMINED,
					subject=name,
					detail=(
						f"set by the caller, but {by!r} computes it; the graph "
						f"recomputed it and the supplied value was discarded"
					),
					corrections=_corrections_for(
						graph, name, values, supplied[name], rank
					),
				)
			)
		missing = set(graph.nodes) - set(supplied)
		needed = {
			name
			for name in missing
			if name not in graph.computed()
		}
		for name in sorted(needed):
			conflicts.append(
				Conflict(
					kind=ConflictKind.UNDER_DETERMINED,
					subject=name,
					detail=(
						"needed to compute the graph and neither supplied nor "
						"derived; nothing in the scenario fixes it"
					),
				)
			)

	# The arithmetic. A residual above tolerance is a direct conflict: some
	# value in the scenario contradicts an equation.
	#
	# A *missing* input is not an arithmetic failure and must not be allowed to
	# raise here: the under-determination above has already named it, and an
	# exception from `consistency` would replace the finding with a traceback
	# and lose the parameter's name. So the DslError that says "this set does
	# not carry x" is caught, the arithmetic is skipped, and the report says so
	# rather than reporting a clean bill of health for equations it never ran.
	try:
		violations = graph.consistency(values)
	except FeedbackError as exc:
		conflicts.append(
			Conflict(
				kind=ConflictKind.LOOP,
				subject="feedback",
				detail=str(exc),
			)
		)
		violations = []
	except DslError as exc:
		# The complete gap, read from the symbol lists, and *not* the name in
		# the error: the DSL evaluator raises on the first symbol it cannot
		# resolve, so `_missing_from(exc)` reports a fact about the order the
		# equations happen to be stored in. That was invisible while the
		# document's equation order was hand-authored, and it surfaced the
		# moment the equations were sorted -- the same input, a different
		# finding, and the one it named (`energy_burden`) was not the one the
		# test that reads this branch was about. Naming every uncarried symbol
		# is stable under reordering, which is what makes it a fact about the
		# scenario.
		missing = graph.uncarried(values)
		derived = set(graph.computed())
		# A derived symbol is absent because the set was never propagated, not
		# because nothing supplies it -- a different finding with a different
		# fix. Only the genuinely unaccounted symbols are under-determination;
		# if the gap is entirely derived ones, the arithmetic failed for the
		# propagation reason and there is no input-level conflict to report.
		unaccounted = [name for name in missing if name not in derived]
		if unaccounted:
			for name in unaccounted:
				conflicts.append(
					Conflict(
						kind=ConflictKind.UNDER_DETERMINED,
						subject=name,
						detail=(
							"needed to compute the graph and neither supplied nor "
							"derived; nothing in the scenario fixes it"
						),
					)
				)
		else:
			# Every uncarried symbol is one the graph computes, so the set was
			# never propagated. That is not under-determination -- nothing needs
			# supplying -- and reporting it as thirty-three separate conflicts
			# would bury the input-level findings under a list of parameters the
			# graph is about to derive anyway. Filed as one conflict under
			# ``propagation``, which is the fix.
			conflicts.append(
				Conflict(
					kind=ConflictKind.UNDER_DETERMINED,
					subject="propagation",
					detail=(
						f"the arithmetic could not be checked: {exc}; all "
						f"{len(missing)} uncarried symbol(s) are computed by the "
						f"graph, so the set was not propagated before it was "
						f"checked rather than missing an input"
					),
				)
			)
		violations = []

	for violation in violations:
		kind, subject = _classify(violation)
		# An out-of-range derivation is named by a synthesised equation, and the
		# lever that fixes it is upstream of the parameter that went out of range,
		# not a participant of the synthesised equation -- so it is corrected the
		# way an over-determination is, against the parameter's own gradient.
		if kind is ConflictKind.OUT_OF_RANGE:
			computed = values.get(subject, 0.0)
			corrections = _corrections_for(
				graph, subject, values, computed + violation.residual, rank
			)
		elif kind is ConflictKind.DIRECT:
			corrections = _corrections_for_equation(graph, violation, values, rank)
		else:
			corrections = ()
		conflicts.append(
			Conflict(
				kind=kind,
				subject=subject,
				detail=str(violation),
				residual=violation.residual,
				tolerance=violation.tolerance,
				corrections=corrections,
				strength=violation.strength,
			)
		)

	checked = tuple(
		sorted(name for name in graph.computed() if name in values)
	)
	return ConflictReport(conflicts=tuple(conflicts), checked=checked)


def _classify(violation: Violation) -> tuple[ConflictKind, str]:
	"""Which kind of conflict a violation is.

	An out-of-range finding is named by its own equation id -- the graph
	synthesises ``<parameter>_out_of_range`` -- so it is recognised rather than
	inferred from the residual, which for a range excursion is the value itself
	and not a distance from anything.
	"""
	if violation.equation_id.endswith("_out_of_range"):
		return ConflictKind.OUT_OF_RANGE, violation.equation_id.removesuffix(
			"_out_of_range"
		)
	if violation.equation_id.startswith("loop_"):
		return ConflictKind.LOOP, violation.equation_id
	return ConflictKind.DIRECT, violation.equation_id


def _corrections_for(
	graph: ParameterGraph,
	parameter: str,
	values: Mapping[str, float],
	supplied: float,
	rank: int,
) -> tuple[Correction, ...]:
	"""Inputs that reach ``parameter``, with the move each needs to explain it.

	An over-determined parameter was recomputed, so there is no residual to
	close; the disagreement is ``supplied - computed``, and the useful
	information is which *input* the caller could have moved to make the
	graph's computation land on the number they supplied. That is
	``d(parameter)/d(input)`` read as a lever, which is why this needs the
	gradient table and not just ``affects``: ``affects`` says whether an input
	reaches the parameter, and a correction needs how far the reach carries.

	The move is ``(supplied - computed) / (d(parameter)/d(input))`` -- the input
	delta that would move the parameter onto the supplied value, to first order.
	An input with a vanishing derivative is dropped rather than reported with an
	infinite move.
	"""
	from alea.prg.sensitivity import gradients

	try:
		table = gradients(graph, values)
	except (DslError, ValueError):
		return ()
	computed = values.get(parameter)
	if computed is None:
		return ()
	gap = supplied - computed
	if gap == 0.0:
		# The caller's value already agrees with the computation; the conflict is
		# nominal (they set a derived parameter) and no move improves anything.
		return ()
	try:
		row = table.of(parameter).derivatives
	except (KeyError, DslError):
		return ()
	out: list[Correction] = []
	for name, derivative in row.items():
		if name == parameter or derivative == 0.0:
			continue
		if not graph.is_settable(name):
			continue
		delta = gap / derivative
		node = graph.node(name)
		current = values.get(name, 0.0)
		target = current + delta
		within = node.range is None or node.range[0] <= target <= node.range[1]
		out.append(
			Correction(
				parameter=name,
				delta=delta,
				elasticity=float(derivative * current / computed)
				if current and computed
				else float(derivative),
				within_range=within,
				current=current,
			)
		)
	return tuple(sorted(out, key=lambda c: c.rank_key())[:rank])


def _corrections_for_equation(
	graph: ParameterGraph,
	violation: Violation,
	values: Mapping[str, float],
	rank: int,
) -> tuple[Correction, ...]:
	"""Which inputs to move to close an equation's residual, and by how much.

	For ``F = 0`` with residual ``r``, moving input ``x`` by ``-r / (dF/dx)``
	closes it to first order. ``dF/dx`` is the *total* derivative, chained
	through the gradient table, so an input that reaches the equation through a
	derived parameter is offered too: the carbon price moves
	``dscr_requirement`` because it moves the tariff, and a correction list that
	named only ``dscr_min`` would offer the regulator's floor for a conflict the
	carbon price caused.

	The move is reported in ``x``'s own unit, and flagged when it would leave
	``x``'s declared range, because a correction that trades a residual for an
	out-of-range value is not a correction.
	"""
	from alea.prg.dsl import parse_side
	from alea.prg.sensitivity import gradients

	equation = graph.equations.get(violation.equation_id)
	if equation is None:
		return ()
	try:
		residual_expr = parse_side(equation.lhs) - parse_side(equation.rhs)
		table = gradients(graph, values)
	except (DslError, ValueError):
		return ()

	# The equation's own names are the *direct* participants; a name that is not
	# an input is a derived parameter whose own gradient carries the inputs that
	# reach it. The two sets together are every settable input that moves this
	# residual, which is what `dF/dx` has to be taken against.
	names = sorted(set(equation.parameters) | set(equation.free_variables))
	moves: list[Correction] = []
	for name in names:
		try:
			partial = float(residual_expr.diff(name)._eval(values))
		except DslError:
			continue
		if partial == 0.0:
			continue
		if graph.is_settable(name):
			levers = {name: 1.0}
		else:
			row = table.table.get(name)
			if not row:
				continue
			levers = {input_: derivative for input_, derivative in row.items()}
		for lever, chain in levers.items():
			# The chain rule: dF/d(lever) = (dF/dname)(dname/dlever). A lever that
			# appears both directly and through a derived name is summed, because
			# both routes carry the residual.
			slope = partial * chain
			if slope == 0.0:
				continue
			delta = -violation.residual / slope
			node = graph.node(lever)
			current = values.get(lever, 0.0)
			target = current + delta
			within = node.range is None or node.range[0] <= target <= node.range[1]
			weight = (
				float(slope * current / values[violation.equation_id])
				if current and values.get(violation.equation_id)
				else float(slope)
			)
			moves.append(
				Correction(
					parameter=lever,
					delta=delta,
					elasticity=weight,
					within_range=within,
					current=current,
				)
			)
	# A lever reached by two routes is one lever, and the route needing the
	# smaller move is the one to report: two entries would read as two options.
	best: dict[str, Correction] = {}
	for move in moves:
		held = best.get(move.parameter)
		if held is None or move.rank_key() < held.rank_key():
			best[move.parameter] = move
	# Ranked by the smallest move that closes the residual, which is the least
	# invasive correction: a lever that closes it with a 1% change is a better
	# suggestion than one that needs 40%, whatever their elasticities.
	return tuple(sorted(best.values(), key=lambda c: c.rank_key())[:rank])


def suggest_corrections(
	graph: ParameterGraph,
	values: Mapping[str, float],
	*,
	supplied: Mapping[str, float] | None = None,
	rank: int = 5,
) -> tuple[Correction, ...]:
	"""Every input move that would reduce some conflict, best first.

	Flattened across conflicts and deduplicated by parameter, keeping the
	largest move named for it: two conflicts naming the same lever are two
	reasons to move it, and reporting it twice would read as two levers.
	"""
	report = detect_conflicts(graph, values, supplied=supplied, rank=rank)
	best: dict[str, Correction] = {}
	for conflict in report.conflicts:
		for correction in conflict.corrections:
			current = best.get(correction.parameter)
			if current is None or abs(correction.delta) > abs(current.delta):
				best[correction.parameter] = correction
	return tuple(
		sorted(best.values(), key=lambda c: (abs(c.delta), -abs(c.elasticity)))
	)
