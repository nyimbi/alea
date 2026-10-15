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

import math
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


def check_cost_risk_axis(
	risk: Sequence[float | None],
	cost: Sequence[float],
) -> None:
	"""Raise unless a cost-risk frontier's risk axis is present *and* populated.

	**One predicate, two doors.** There are two ways to ask for a cost-risk
	frontier -- ``cost_risk_frontier`` below, and the API's ``_run_frontier`` --
	and a guarantee one door enforces and the other routes around is not a
	guarantee. The API door used to accept ``frontier='cost_risk'`` and return
	the cost-emissions points under that name; the fix is this shared check
	rather than a second copy of the same comparison, because two copies of a
	predicate agree today and diverge the first time either is edited.

	Two refusals, and the second is the one that took a defect to find:

	- **Absent.** A ``None`` or ``NaN`` CVaR is a sweep run without a price
	  model. Filling the column with zeros would plot as a flat line at the
	  origin and read as "riskless" for a solve that measured nothing.
	- **Uninformative.** A *present* axis is not a *populated* one. The price
	  model draws its dispersion from the solve's own marginal prices, so a
	  network whose price is the same in every hour has none to draw from and
	  every point comes back with ``CVaR == total_cost`` -- not NaN, and
	  carrying nothing. That frontier is the cost-emissions frontier with a
	  risk label, arriving by the one route the absence check cannot see.
	  Verified on this build: a flat-price fixture returns CVaR equal to the
	  objective on every point.

	The comparison is ``isclose`` with ``rtol=1e-9``, not ``==``: a
	zero-dispersion draw still leaves float noise of order 1e-11 on a cost of
	order 1e5, so an exact comparison reports "informative" on exactly the
	frontier this exists to refuse.
	"""
	assert len(risk) == len(cost), "a risk point and a cost point per frontier point"
	if not risk:
		raise ValueError("a cost-risk frontier with no points is not a frontier")

	absent = 0
	pairs: list[tuple[float, float]] = []
	for risk_value, cost_value in zip(risk, cost, strict=True):
		if risk_value is None:
			absent += 1
			continue
		number = float(risk_value)
		if math.isnan(number):
			absent += 1
			continue
		pairs.append((number, float(cost_value)))

	if absent:
		raise ValueError(
			f"{absent} of {len(risk)} points have no CVaR; a cost-risk frontier "
			f"needs a price model (price_fn) on the engine. Use "
			f"efficient_frontier() for the cost-emissions frontier instead."
		)
	if all(math.isclose(value, cost_value, rel_tol=1e-9, abs_tol=0.0) for value, cost_value in pairs):
		raise ValueError(
			f"every one of {len(pairs)} points has CVaR equal to its cost, so the "
			f"risk axis carries no information and this is the cost-emissions "
			f"frontier with a risk label. The engine's price model draws its "
			f"dispersion from the solved network's marginal prices, and this "
			f"network prices every hour the same. Use efficient_frontier() for "
			f"the cost-emissions frontier instead."
		)


def cost_risk_frontier(
	engine: WhatIfEngine,
	param_name: str,
	values: Sequence[float],
	template: ScenarioParameters | None = None,
	*,
	workers: int = 1,
) -> pd.DataFrame:
	"""The cost-risk frontier: cost against CVaR.

	Refuses rather than returning a frontier whose risk axis is missing or
	carries nothing. A cost-risk frontier without CVaR is the cost-emissions
	frontier with a better name, and naming it "risk" would be the strongest
	possible version of the defect this module exists to avoid. The refusal is
	``check_cost_risk_axis``, shared with the API door.
	"""
	frame = efficient_frontier(engine, param_name, values, template, workers=workers)
	check_cost_risk_axis(
		_optional_floats(frame["conditional_value_at_risk"].tolist()),
		[float(value) for value in frame["total_cost_usd"].tolist()],
	)
	return frame


def _optional_floats(values: Sequence[Any]) -> list[float | None]:
	"""A float column as ``float | None``, with ``NaN`` read as absent.

	``check_cost_risk_axis`` takes both doors' points, and the two spell
	"missing" differently -- the sweep frame carries ``NaN``, the API's payload
	carries ``None``. Normalising here keeps the shared predicate from having to
	know which door called it.
	"""
	return [None if value is None or pd.isna(value) else float(value) for value in values]


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
	"check_cost_risk_axis",
	"cost_risk_frontier",
	"efficient_frontier",
	"frontier_points",
	"sweep_parameter",
]
