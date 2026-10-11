# SPDX-License-Identifier: MIT
"""Loss routes: decomposition, TLENS, mitigation.

Analyst tier throughout. A loss decomposition names where a utility's energy
goes, which is commercially sensitive: the split between technical and
non-technical loss is the difference between an engineering problem and a theft
problem, and it is not published casually.

Every figure is a :class:`ValueOut` with its basis. Loss statistics are the
place where a proxy is most likely to be mistaken for a measurement -- several
countries have no metered loss data at all and their TLENS figures are modelled
from regional averages -- so the basis is the field that carries the most
weight here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from alea.api.deps import AnalystDep, PaginationDep, StateDep
from alea.api.views import LossDecompositionOut, MitigationOptionOut, Page, TlensRowOut

router = APIRouter(prefix="/losses", tags=["losses"])


@router.get("/decompose", response_model=LossDecompositionOut, summary="Loss decomposition")
async def decompose(
	state: StateDep,
	principal: AnalystDep,
	country: str = Query(min_length=2, max_length=2),
	period_start: str | None = Query(default=None, description="ISO 8601 date."),
	period_end: str | None = Query(default=None, description="ISO 8601 date."),
) -> LossDecompositionOut:
	"""A country's losses split into their components.

	Returns a single object rather than a page: a decomposition is one result,
	and wrapping it in a page would invite a client to read ``items[0]`` and
	index-error on an empty one.
	"""
	assert state is not None, "decompose needs application state"
	result = state.repository.loss_decomposition(
		country=country, period_start=period_start, period_end=period_end
	)
	if result is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"no loss decomposition published for {country.upper()}",
		)
	return result


@router.get("/tlens", response_model=Page[TlensRowOut], summary="T&D loss statistics")
async def tlens(
	state: StateDep,
	principal: AnalystDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
	year: int | None = Query(default=None, ge=1990, le=2200),
) -> Page[TlensRowOut]:
	"""Transmission, distribution and collection losses by country-year."""
	assert state is not None, "tlens needs application state"
	rows = state.repository.tlens(country=country, year=year)
	window = rows[page.offset : page.offset + page.limit]
	return Page[TlensRowOut](items=window, total=len(rows), limit=page.limit, offset=page.offset)


@router.get("/mitigate", response_model=Page[MitigationOptionOut], summary="Loss mitigation options")
async def mitigate(
	state: StateDep,
	principal: AnalystDep,
	page: PaginationDep,
	country: str = Query(min_length=2, max_length=2),
) -> Page[MitigationOptionOut]:
	"""Interventions and their modelled effect on losses, best payback first."""
	assert state is not None, "mitigate needs application state"
	rows = state.repository.mitigation_options(country=country)
	window = rows[page.offset : page.offset + page.limit]
	return Page[MitigationOptionOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)
