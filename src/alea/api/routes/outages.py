# SPDX-License-Identifier: MIT
"""Outage routes: forecast, history, validation.

``/outages/forecast`` is the endpoint the USSD and SMS adapters read, so its
rows are ordered by probability descending. That ordering is what lets the
adapters select "the top N zones" as a prefix of this list and state how many
were omitted -- a complete message at its own resolution, rather than a
truncated one (11-layer8 §5.1).

``/outages/validate`` serves forecast-versus-observed accuracy. It exists so
that the plan's ``[UNVERIFIED]`` accuracy figures can be replaced by measured
ones; until it returns rows, no accuracy figure may be published as established.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from alea.api.cache import read_through
from alea.api.deps import AnalystDep, PaginationDep, PublicDep, StateDep
from alea.api.views import (
	OutageForecastRowOut,
	OutageHistoryRowOut,
	OutageValidationRowOut,
	Page,
)

router = APIRouter(prefix="/outages", tags=["outages"])

FORECAST_ARTEFACT = "data/processed/outages/forecast.parquet"
HISTORY_ARTEFACT = "data/processed/outages/history.parquet"
VALIDATION_ARTEFACT = "data/processed/outages/validation.parquet"

FORECAST_TTL_SECONDS = 3600.0
"""An outage forecast is good for an hour; after that the weather has moved."""

HISTORY_TTL_SECONDS = 86400.0
"""History changes only when new events are ingested, so a day is safe."""


@router.get("/forecast", response_model=Page[OutageForecastRowOut], summary="Outage forecast")
async def forecast(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	country: str = Query(min_length=2, max_length=2, description="ISO 3166-1 alpha-2."),
	grid_zone: str | None = Query(default=None, min_length=1),
	horizon_hours: int = Query(default=24, ge=1, le=168),
) -> Page[OutageForecastRowOut]:
	"""The probability each grid zone loses supply in the next ``horizon_hours``.

	Scalar query parameters, not a request body. The specification's version of
	this route takes a Pydantic model as a GET parameter, which does not bind as
	written (11-layer8 §2.1).
	"""
	assert state is not None, "forecast needs application state"
	checksum = state.repository.checksum(FORECAST_ARTEFACT)
	if checksum is None:
		return Page[OutageForecastRowOut](items=[], total=0, limit=page.limit, offset=page.offset)

	rows = await read_through(
		state,
		namespace="outages.forecast",
		checksum=checksum,
		params={"country": country.upper(), "grid_zone": grid_zone, "horizon_hours": horizon_hours},
		ttl_seconds=FORECAST_TTL_SECONDS,
		producer=lambda: _produce_forecast(state, country, grid_zone, horizon_hours),
		from_payload=OutageForecastRowOut.model_validate,
	)
	window = rows[page.offset : page.offset + page.limit]
	return Page[OutageForecastRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)


async def _produce_forecast(
	state, country: str, grid_zone: str | None, horizon_hours: int
) -> list[OutageForecastRowOut]:
	assert country, "a forecast is per country"
	return state.repository.outage_forecasts(
		country=country, grid_zone=grid_zone, horizon_hours=horizon_hours
	)


@router.get("/history", response_model=Page[OutageHistoryRowOut], summary="Outage history")
async def history(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
	grid_zone: str | None = Query(default=None, min_length=1),
) -> Page[OutageHistoryRowOut]:
	"""Recorded outage events, most recent first."""
	assert state is not None, "history needs application state"
	checksum = state.repository.checksum(HISTORY_ARTEFACT)
	if checksum is None:
		return Page[OutageHistoryRowOut](items=[], total=0, limit=page.limit, offset=page.offset)

	rows = await read_through(
		state,
		namespace="outages.history",
		checksum=checksum,
		params={"country": country.upper() if country else None, "grid_zone": grid_zone},
		ttl_seconds=HISTORY_TTL_SECONDS,
		producer=lambda: _produce_history(state, country, grid_zone),
		from_payload=OutageHistoryRowOut.model_validate,
	)
	window = rows[page.offset : page.offset + page.limit]
	return Page[OutageHistoryRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)


async def _produce_history(state, country: str | None, grid_zone: str | None) -> list[OutageHistoryRowOut]:
	return state.repository.outage_history(country=country, grid_zone=grid_zone)


@router.get("/validate", response_model=Page[OutageValidationRowOut], summary="Forecast accuracy")
async def validate(
	state: StateDep,
	principal: AnalystDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[OutageValidationRowOut]:
	"""Forecast-versus-observed accuracy, by zone and period.

	Analyst tier: these are the rows that decide whether an accuracy figure may
	be published, and they are read by people who will act on them.
	"""
	assert state is not None, "validate needs application state"
	all_rows = state.repository.outage_validation(country=country)
	window = all_rows[page.offset : page.offset + page.limit]
	return Page[OutageValidationRowOut](
		items=window, total=len(all_rows), limit=page.limit, offset=page.offset
	)


