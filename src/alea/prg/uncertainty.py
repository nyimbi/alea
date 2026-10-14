# SPDX-License-Identifier: MIT
"""Which parameters are declared uncertain, and what that does not yet buy.

WHY this is a register and not a Monte Carlo. The graph marks 21 parameters
``determinism: stochastic`` and one edge ``relationship: stochastic``, and
nothing read either -- the "declared is not produced" defect, in the one place
where reading it wrongly is most expensive. The specification says a scenario's
inputs are uncertain and asks for an edge *type* to record it; it does not say
what distribution, what correlation, or what to report. Inventing a sampler
would put a fabricated confidence interval on a report, which is worse than the
silence it replaces: a reader cannot tell a modelled interval from a guessed
one.

So this module does the part that is *determined by what is written down*: it
names the uncertain inputs, computes which derived parameters are reachable
from them, and states -- as a finding, in the report -- that a point
sensitivity is a derivative at one point and not a distribution over the space.
That is what the declarations support, and the gap between it and a real
propagation is named rather than papered over.

WHY reachability is not the same as uncertainty. ``emissions_mtco2_per_year``
is computed from ``generation_twh``, which is computed from ``demand_growth``,
which is declared stochastic -- so it is *reachable* from an uncertain input.
Its own declaration says ``physical``, and that is not a contradiction: the
relation is an accounting identity that holds whatever the demand turns out to
be. Reachability says an input's uncertainty flows into the value; the node's
own ``determinism`` says what kind of relation fixes it. The two are reported
separately because collapsing them would either call every downstream physical
identity stochastic or pretend the uncertainty stops at the first equation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from alea.prg.views import Determinism, Relationship

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"UncertaintyRegister",
	"register",
]


@dataclass(frozen=True)
class UncertaintyRegister:
	"""What the graph declares uncertain, and what that reaches."""

	inputs: tuple[str, ...]
	"""Settable parameters declared ``stochastic``: the uncertain knobs."""

	derived_stochastic: tuple[str, ...]
	"""Derived parameters whose own relation is declared stochastic."""

	reachable: tuple[str, ...]
	"""Derived parameters an uncertain input can reach, transitively.

	Wider than ``derived_stochastic``, and deliberately: a physical identity
	downstream of an uncertain input is still a number whose value the
	uncertainty moved, even though the identity itself is exact.
	"""

	stochastic_edges: tuple[tuple[str, str, str], ...]
	"""``(source, target, equation_id)`` for each edge declared stochastic."""

	def summary(self) -> str:
		return (
			f"{len(self.inputs)} uncertain input(s) reach {len(self.reachable)} "
			f"derived parameter(s); {len(self.derived_stochastic)} of those are "
			f"stochastic by their own relation, and {len(self.stochastic_edges)} "
			f"edge(s) are declared stochastic. A sensitivity is a derivative at "
			f"one point, not a distribution over these."
		)


def register(graph: ParameterGraph) -> UncertaintyRegister:
	"""Read the graph's uncertainty declarations, and what they reach."""
	uncertain = {
		name
		for name, node in graph.nodes.items()
		if node.determinism is Determinism.STOCHASTIC
	}
	# "Derived" is everything a user cannot set, which is the determiner set
	# *plus* the loop variables. ``order()`` names only the former -- a loop has
	# no place in a topological order -- so filtering on it would drop the fixed
	# point itself and report a closure that reached past the loop while
	# omitting the loop's own members. The capture price is a loop variable, and
	# it is precisely a number the demand's uncertainty moves.
	derived = {name for name in graph.nodes if not graph.is_settable(name)}
	inputs = tuple(sorted(name for name in uncertain if graph.is_settable(name)))

	# Transitive closure over `affects`, which is the inverse of `depends_on`
	# *including* the loop equations. `depends_on` deliberately skips those --
	# a loop has no place in a topological order -- so a closure over it would
	# stop at the loop and miss everything downstream of the fixed point, which
	# is where the capture price and the VRE share live.
	reachable: set[str] = set()
	frontier = list(inputs)
	while frontier:
		current = frontier.pop()
		for dependent in graph.affects(current):
			if dependent in reachable:
				continue
			reachable.add(dependent)
			frontier.append(dependent)

	edges = tuple(
		sorted(
			(edge.source, edge.target, edge.equation_id)
			for edge in graph.edges
			if edge.relationship is Relationship.STOCHASTIC
		)
	)
	return UncertaintyRegister(
		inputs=inputs,
		derived_stochastic=tuple(sorted(uncertain & derived)),
		reachable=tuple(sorted(reachable & derived)),
		stochastic_edges=edges,
	)
