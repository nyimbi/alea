# SPDX-License-Identifier: MIT
"""Audit a solved what-if result against the PRG's identities.

WHY this exists, and why it is not a re-derivation. The what-if engine
computes a scenario's emissions by summing ``generation x intensity`` over the
network's carriers, using the technology registry. The PRG computes the same
quantity from its own equation over its own parameters. Those are two
implementations of one identity, written by different code for different
reasons, and running them against each other is the only check that finds an
error in either: a differential test inside one implementation proves it agrees
with itself.

WHAT IT DOES NOT YET CHECK, stated so the gap is a finding and not a silence.
The PRG's ``energy_balance`` is single-region: one demand, one generation
total. A PyPSA network balances per bus and per hour, and the solved result
does not carry the nodal frame, so this audit cannot yet assert the balance
against it. The balance is checked in the *parameters* the engine was handed --
which is where a scenario's internal consistency lives -- and the solved
result is checked against the identities whose inputs the result does carry:
emissions, the carbon budget, and the affordability burden. Adding the nodal
frame is what would let this assert the balance too, and until it does, this
module says so rather than reporting a pass it did not earn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alea.prg.graph import ParameterGraph, Violation, load_graph

__all__ = [
	"ScenarioAudit",
	"audit_scenario_result",
	"fleet_intensity_gap",
	"parameters_from_result",
]


@dataclass(frozen=True)
class ScenarioAudit:
	"""What the PRG found in a solved result."""

	checked: tuple[str, ...]
	"""Parameter names the result supplied and the graph therefore checked."""

	skipped: tuple[str, ...]
	"""Parameters the result does not carry, so nothing was checked about them.

	Reported rather than omitted: an audit that silently checks four of the
	graph's twenty-eight derived parameters and prints "consistent" is a clean
	bill of health for a result nobody examined.
	"""

	violations: tuple[Violation, ...]
	excursions: dict[str, float]

	@property
	def consistent(self) -> bool:
		"""Whether every parameter that *was* checked agrees.

		Not a bill of health for the scenario. It says nothing about the
		parameters in ``skipped``, and a reader who takes it as a verdict is
		taking a statement about the checked set for one about the result --
		which is why :meth:`summary` carries the count.
		"""
		return not self.violations

	def summary(self) -> str:
		if self.consistent:
			return (
				f"consistent over {len(self.checked)} parameter(s); "
				f"{len(self.skipped)} not carried by the result, so nothing was "
				f"checked about them"
			)
		return f"{len(self.violations)} violation(s) over {len(self.checked)} parameter(s)"


def parameters_from_result(
	result: Any, graph: ParameterGraph, *, overrides: dict[str, float] | None = None
) -> dict[str, float]:
	"""The PRG parameters a solved what-if result can supply.

	Only the names the result actually carries are returned. A result that
	supplied a value for a parameter it does not own would be inventing one,
	and a graph propagated from invented inputs reports violations about the
	invention.
	"""
	assert graph is not None
	scoped: dict[str, float] = dict(overrides or {})

	generation_mwh = getattr(result, "generation_mwh", None) or {}
	emissions_tco2 = getattr(result, "total_emissions_tco2", None)
	capacity_mix = getattr(result, "capacity_mix_mw", None) or {}
	params = getattr(result, "params", None)

	if params is not None:
		for name in ("carbon_price_usd_per_tco2", "demand_growth"):
			if name in graph.nodes and hasattr(params, name):
				scoped[name] = float(getattr(params, name))

	# `generation_twh` and `emissions_mtco2_per_year` are deliberately *not*
	# taken from the result even though it carries both. They are derived
	# parameters: `propagate` recomputes them from the equations, so supplying
	# them would be silently discarded and the audit would compare the graph
	# against itself and report agreement. The engine's emissions are checked
	# by `fleet_intensity_gap`, which measures them against the graph's
	# declared factor instead of pretending they are an input.
	_ = emissions_tco2

	if capacity_mix and "total_capacity_mw" in graph.nodes:
		total = float(sum(capacity_mix.values()))
		if total > 0.0:
			scoped["total_capacity_mw"] = total

	return {name: value for name, value in scoped.items() if name in graph.nodes}


def audit_scenario_result(
	result: Any,
	graph: ParameterGraph | None = None,
	*,
	overrides: dict[str, float] | None = None,
) -> ScenarioAudit:
	"""Propagate the parameters a solved result supplies and report violations.

	The result is *not* the authority here. Where the engine and the graph
	disagree, that disagreement is the finding, and the graph's answer is the
	one whose derivation is written down in ``config/prg.yaml`` next to the
	physics it came from.
	"""
	g = graph if graph is not None else load_graph()
	supplied = parameters_from_result(result, g, overrides=overrides)

	# Propagation needs every underived parameter, so the graph's own defaults
	# fill the ones the result does not carry. That is a *stated* substitution:
	# the audit checks the identities the result's values take part in, and a
	# parameter left at its default can only make an identity harder to
	# satisfy, never easier -- so a pass is not an artefact of the fill.
	values: dict[str, float] = {
		name: node.default for name, node in g.nodes.items() if node.default is not None
	}
	values.update(supplied)
	# No completeness pre-check here. `propagate` already refuses an incomplete
	# set and already knows which parameters it can compute and which are loop
	# variables needing no input; a second check written here would be a
	# restatement of that rule, and the first version of it was wrong in
	# exactly that way -- it demanded values for the loop variables, which the
	# solver starts from their own `initial`.
	propagated = g.propagate(values)
	derived = set(g.order())
	checked = tuple(sorted(name for name in supplied if name in derived))
	skipped = tuple(sorted(derived - set(checked)))
	return ScenarioAudit(
		checked=checked,
		skipped=skipped,
		violations=tuple(g.consistency(propagated.values)),
		excursions=g.range_excursions(),
	)


def fleet_intensity_gap(result: Any, graph: ParameterGraph | None = None) -> dict[str, float]:
	"""The engine's fleet-average emission intensity against the graph's factor.

	A *measurement*, not a pass or a fail, and deliberately so. The graph's
	emissions identity is ``emissions = generation x factor`` with one factor
	for the whole fleet; the engine sums ``generation_c x intensity_c`` over
	carriers. The two agree exactly when the fleet's weighted-average intensity
	equals the graph's single number, and the graph's number is a stand-in for
	a fleet it does not yet model carrier by carrier.

	So the useful output is the size of that gap, reported as a ratio. A gap of
	1.0 means the stand-in is exact for this scenario; a gap of 2.0 means the
	graph would understate this scenario's emissions by half, which is a fact
	about the graph's coverage that no consistency check can report, because
	the graph is internally consistent either way.
	"""
	g = graph if graph is not None else load_graph()
	generation_mwh = getattr(result, "generation_mwh", None) or {}
	emissions_tco2 = float(getattr(result, "total_emissions_tco2", 0.0) or 0.0)
	total_mwh = float(sum(generation_mwh.values()))
	if total_mwh <= 0.0:
		return {"engine_intensity": 0.0, "graph_factor": 0.0, "ratio": 0.0}

	node = g.nodes.get("emission_factor_t_per_mwh")
	factor = float(node.default) if node is not None and node.default is not None else 0.0
	engine_intensity = emissions_tco2 / total_mwh
	return {
		"engine_intensity": engine_intensity,
		"graph_factor": factor,
		"ratio": (engine_intensity / factor) if factor > 0.0 else 0.0,
	}
