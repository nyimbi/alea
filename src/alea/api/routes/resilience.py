# SPDX-License-Identifier: MIT
"""Resilience routes: metrics and N-1 contingency.

Analyst tier. A contingency result names the network elements whose loss sheds
the most load, which is a list of the system's weakest points; it is the single
most security-sensitive dataset the platform produces.

``contingency`` orders by load shed descending, because the operator reading it
wants the worst case first and a list ordered by element id buries it.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from alea.api.deps import AnalystDep, PaginationDep, StateDep
from alea.api.views import ContingencyRowOut, Page, ResilienceMetricOut

router = APIRouter(prefix="/resilience", tags=["resilience"])


@router.get("/metrics", response_model=Page[ResilienceMetricOut], summary="Resilience metrics")
async def metrics(
	state: StateDep,
	principal: AnalystDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[ResilienceMetricOut]:
	"""Resilience metrics by country."""
	assert state is not None, "metrics needs application state"
	rows = state.repository.resilience_metrics(country=country)
	window = rows[page.offset : page.offset + page.limit]
	return Page[ResilienceMetricOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)


@router.get("/contingency", response_model=Page[ContingencyRowOut], summary="N-1 contingency results")
async def contingency(
	state: StateDep,
	principal: AnalystDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[ContingencyRowOut]:
	"""The consequence of losing each network element, worst first."""
	assert state is not None, "contingency needs application state"
	rows = state.repository.contingency(country=country)
	window = rows[page.offset : page.offset + page.limit]
	return Page[ContingencyRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)
