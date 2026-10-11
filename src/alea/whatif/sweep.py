# SPDX-License-Identifier: MIT
"""Parameter sweeps and efficient frontiers.

WHY two frontiers and not one: the specification plots cost against emissions,
which answers a policy question. The cost-risk frontier — cost against CVaR —
answers the investment question: whether a portfolio survives a bad year. A
lender asks the second, a regulator asks the first, and reporting either alone
as "the frontier" answers half the question while looking complete.

WHY the risk axis is allowed to be absent: a sweep run without Layer 3's price
model has no cost distribution, so CVaR is genuinely unknown. The frontier then
reports itself as a cost-emissions frontier rather than filling the risk column
with zeros, which would plot as a flat line at the origin and read as "riskless".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import pandas as pd

from alea.logging import get_logger
from alea.whatif.params import ScenarioParameters
from alea.whatif.views import FrontierPoint, SolveOutcome

if TYPE_CHECKING:
	from alea.whatif.service import WhatIfEngine

logger = get_logger(__name__)

FRONTIER_COLUMNS = (
	"param_name",
	"param_value",
	"total_cost_usd",
	"total_emissions_tco2",
	"renewable_share",
	"conditional_value_at_risk",
	"value_at_risk",
	"scenario_id",
	"cache_key",
	"from_cache",
)

FRONTIER_VALUE_COLUMNS = (
	"param_name",
	"param_value",
	"total_cost_usd",
	"total_emissions_tco2",
	"renewable_share",
	"conditional_value_at_risk",
	"value_at_risk",
	"cache_key",
)
"""The columns a determinism comparison covers.

``from_cache`` and ``scenario_id`` are excluded deliberately. ``from_cache``
records how *this run* was served, which legitimately differs between a cold and
a warm sweep. ``scenario_id`` is a fresh UUID7 per solve, so it identifies a
solve instance rather than the scenario's content; a re-solve is a new instance
with identical values. The gate ``test_frontier_deterministic`` compares these
columns — the frontier's content — and the failure it guards against is worker
completion order, which must not reach the frame. Results already follow input
order, so a parallel sweep and a serial one agree column for column.
"""


def sweep_parameter(
	engine: WhatIfEngine,
	param_name: str,
	values: Sequence[float],
	template: ScenarioParameters | None = None,
	*,
	workers: int = 1,
	progress: Callable[[int, int], None] | None = None,
) -> list[SolveOutcome]:
	"""Solve one parameter across ``values``.

	Points are solved in the order given, so the returned list is aligned with
	``values`` and a frontier is a function of the sweep rather than of how the
	work happened to be scheduled. ``workers > 1`` parallelises with joblib;
	each worker writes its own content-addressed cache entry, so there is no
	lock contention and no shared mutable state.
	"""
	if param_name not in ScenarioParameters.model_fields:
		raise KeyError(
			f"unknown scenario parameter {param_name!r}; known: "
			f"{', '.join(ScenarioParameters.parameter_names())}"
		)
	assert len(values) > 0, "a sweep of zero points is not a sweep"

	base = template or ScenarioParameters()
	params_list = [base.with_value(param_name, value) for value in values]

	if workers > 1 and len(params_list) > 1:
		return _sweep_parallel(engine, params_list, workers, progress)

	outcomes: list[SolveOutcome] = []
	for index, params in enumerate(params_list, start=1):
		outcomes.append(engine.solve_with_outcome(params))
		if progress is not None:
			progress(index, len(params_list))
	return outcomes


def _sweep_parallel(
	engine: WhatIfEngine,
	params_list: list[ScenarioParameters],
	workers: int,
	progress: Callable[[int, int], None] | None,
) -> list[SolveOutcome]:
	"""Parallel sweep. Order of results follows ``params_list``, not completion.

	The sweep is deterministic because the result order is the input order, not
	the completion order: two runs of the same sweep produce byte-identical
	frames even though the workers finish in a different order.
	"""
	from joblib import Parallel, delayed

	def _solve_one(params: ScenarioParameters) -> SolveOutcome:
		# Each worker solves and writes its own content-addressed cache entry,
		# so there is no lock contention and no shared mutable state.
		return engine.solve_with_outcome(params)

	computed: list[Any] = list(
		Parallel(n_jobs=workers, prefer="processes")(
			delayed(_solve_one)(params) for params in params_list
		)
	)
	if progress is not None:
		progress(len(params_list), len(params_list))
	return [outcome for outcome in computed]


def efficient_frontier(
	engine: WhatIfEngine,
	param_name: str,
	values: Sequence[float],
	template: ScenarioParameters | None = None,
	*,
	workers: int = 1,
) -> pd.DataFrame:
	"""Sweep one parameter; return cost, emissions, renewable share and risk.

	Every point reports cost and risk together. Where the engine has no price
	model the risk columns are ``NaN`` — never 0 — so a consumer can tell "no
	risk computed" from "risk computed and zero".
	"""
	assert len(values) > 0, "a frontier needs at least one point"

	outcomes = sweep_parameter(engine, param_name, values, template, workers=workers)
	frame = pd.DataFrame(
		[
			_point(param_name, float(value), outcome)
			for value, outcome in zip(values, outcomes, strict=True)
		],
		columns=list(FRONTIER_COLUMNS),
	)
	frame = frame.sort_values(["param_value", "total_cost_usd"], kind="stable").reset_index(drop=True)

	logger.info(
		"whatif.frontier",
		param=param_name,
		points=len(frame),
		cost_risk=bool(frame["conditional_value_at_risk"].notna().all()),
	)
	return frame


def cost_risk_frontier(
	engine: WhatIfEngine,
	param_name: str,
	values: Sequence[float],
	template: ScenarioParameters | None = None,
	*,
	workers: int = 1,
) -> pd.DataFrame:
	"""The cost-risk frontier: cost against CVaR.

	Refuses rather than returning a frontier whose risk axis is missing. A
	cost-risk frontier without CVaR is the cost-emissions frontier with a
	better name, and naming it "risk" would be the strongest possible version
	of the defect this module exists to avoid.
	"""
	frame = efficient_frontier(engine, param_name, values, template, workers=workers)
	missing = frame["conditional_value_at_risk"].isna().to_numpy(dtype=bool)
	missing_count = int(missing.sum())
	if missing_count > 0:
		raise ValueError(
			f"{missing_count} of {len(frame)} points have no CVaR; a "
			f"cost-risk frontier needs a price model (price_fn) on the engine. "
			f"Use efficient_frontier() for the cost-emissions frontier instead."
		)
	return frame


def frontier_points(frame: pd.DataFrame) -> list[FrontierPoint]:
	"""Typed points from a frontier frame, for storage and reporting."""
	points: list[FrontierPoint] = []
	for record in frame.to_dict(orient="records"):
		points.append(
			FrontierPoint(
				param_name=str(record["param_name"]),
				param_value=float(record["param_value"]),
				total_cost_usd=float(record["total_cost_usd"]),
				total_emissions_tco2=float(record["total_emissions_tco2"]),
				renewable_share=_optional_float(record.get("renewable_share")),
				conditional_value_at_risk=_optional_float(record.get("conditional_value_at_risk")),
				value_at_risk=_optional_float(record.get("value_at_risk")),
				scenario_id=str(record.get("scenario_id", "")),
				cache_key=str(record.get("cache_key", "")),
				from_cache=bool(record.get("from_cache", False)),
			)
		)
	return points


def _point(param_name: str, value: float, outcome: SolveOutcome) -> dict[str, Any]:
	"""One frontier row. Risk is read off the result, never fabricated."""
	result = outcome.result
	risk = result.risk
	return {
		"param_name": param_name,
		"param_value": value,
		"total_cost_usd": result.total_cost_usd,
		"total_emissions_tco2": result.total_emissions_tco2,
		"renewable_share": result.renewable_share,
		"conditional_value_at_risk": None if risk is None else risk.conditional_value_at_risk,
		"value_at_risk": None if risk is None else risk.value_at_risk,
		"scenario_id": result.scenario_id,
		"cache_key": outcome.cache_key,
		"from_cache": outcome.from_cache,
	}


def _optional_float(value: Any) -> float | None:
	if value is None:
		return None
	if isinstance(value, float) and pd.isna(value):
		return None
	return float(value)


__all__ = [
	"FRONTIER_COLUMNS",
	"FRONTIER_VALUE_COLUMNS",
	"cost_risk_frontier",
	"efficient_frontier",
	"frontier_points",
	"sweep_parameter",
]
