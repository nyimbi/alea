# SPDX-License-Identifier: MIT
"""One entry point from a graph scenario to the engine's ``ScenarioParameters``.

Two callers need the same answer to "what does this scenario ask of the
engine": the what-if path (`WhatIfEngine.solve_from_prg`) and a plain solve. A
translation that lives in one of them is a translation the other does not
honour, so both call this.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from alea.whatif.params import ScenarioParameters

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = ["scenario_parameters"]


def scenario_parameters(
	values: Mapping[str, float],
	network: Any | None = None,
	*,
	graph: ParameterGraph | None = None,
	strict: bool = True,
	constrain: bool = True,
	base: ScenarioParameters | None = None,
) -> ScenarioParameters:
	"""The engine knobs a scenario stated in the graph's names sets.

	Constraint terms (the parameters the inequality hook reads) are lifted out
	first, as they are not knobs, unless ``constrain`` is False. Everything else
	goes through `to_scenario_parameters`, so ``strict`` refuses a parameter the
	engine cannot carry and a ratio mapping refuses without a ``network``.

	``base`` is the parameter set the overrides land on. The model's own
	defaults are not neutral (demand growth 4%, carbon price 50), so a caller
	that means "change only what I named" passes a neutral base.
	"""
	from alea.prg import load_graph
	from alea.prg.constraints import bound_parameter_names
	from alea.prg.translate import to_scenario_parameters

	g = graph if graph is not None else load_graph()
	terms = set(bound_parameter_names(g)) if constrain else set()
	knobs = {name: value for name, value in values.items() if name not in terms}
	return to_scenario_parameters(g, knobs, network, strict=strict, base=base)
