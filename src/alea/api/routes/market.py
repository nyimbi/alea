# SPDX-License-Identifier: MIT
"""Market routes: prices, capture rates, PPA benchmarks.

The capture-rate curve is the Layer 3 deliverable -- it is what a developer
prices a project against -- so it is served with its VRE penetration on every
row. A capture rate without the penetration it was measured at is a number with
no meaning: the same technology captures 95% of the price at 5% VRE share and
60% at 40%, and the curve is the point.

Prices and capture rates are cached with a one-hour TTL against the input
artefact's checksum (11-layer8 §6). PPA benchmarks are cached the same way; they
change when the benchmark dataset is refreshed, which is rare but is exactly the
event a URL-only cache key would miss.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from alea.api.cache import read_through
from alea.api.deps import PaginationDep, PublicDep, StateDep
from alea.api.views import CaptureRateRowOut, Page, PpaBenchmarkRowOut, PriceRowOut

router = APIRouter(tags=["market"])

PRICES_ARTEFACT = "data/processed/market/prices.parquet"
CAPTURE_ARTEFACT = "data/processed/market/capture_rates.parquet"
PPA_ARTEFACT = "data/processed/market/ppa_benchmarks.parquet"

MARKET_TTL_SECONDS = 3600.0


@router.get("/prices", response_model=Page[PriceRowOut], summary="Wholesale prices")
async def prices(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[PriceRowOut]:
	"""Wholesale prices, optionally for one country.

	Cached for an hour against the price artefact's checksum: national prices
	move with the market and a day-old price is a wrong price.
	"""
	assert state is not None, "prices needs application state"
	checksum = state.repository.checksum(PRICES_ARTEFACT)
	if checksum is None:
		return Page[PriceRowOut](items=[], total=0, limit=page.limit, offset=page.offset)

	rows = await read_through(
		state,
		namespace="market.prices",
		checksum=checksum,
		params={"country": country},
		ttl_seconds=MARKET_TTL_SECONDS,
		producer=lambda: _produce(state, country),
		from_payload=PriceRowOut.model_validate,
	)
	window = rows[page.offset : page.offset + page.limit]
	return Page[PriceRowOut](items=window, total=len(rows), limit=page.limit, offset=page.offset)


async def _produce(state, country: str | None) -> list[PriceRowOut]:
	assert state is not None, "a producer needs application state"
	return state.repository.prices(country=country)


@router.get("/capture-rates", response_model=Page[CaptureRateRowOut], summary="Capture-rate curves")
async def capture_rates(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	technology: str | None = Query(default=None, min_length=1),
) -> Page[CaptureRateRowOut]:
	"""Capture rate against VRE penetration, the curve a developer prices against."""
	assert state is not None, "capture_rates needs application state"
	checksum = state.repository.checksum(CAPTURE_ARTEFACT)
	if checksum is None:
		return Page[CaptureRateRowOut](items=[], total=0, limit=page.limit, offset=page.offset)

	rows = await read_through(
		state,
		namespace="market.capture",
		checksum=checksum,
		params={"technology": technology},
		ttl_seconds=MARKET_TTL_SECONDS,
		producer=lambda: _produce_capture(state, technology),
		from_payload=CaptureRateRowOut.model_validate,
	)
	window = rows[page.offset : page.offset + page.limit]
	return Page[CaptureRateRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)


async def _produce_capture(state, technology: str | None) -> list[CaptureRateRowOut]:
	assert state is not None, "a producer needs application state"
	return state.repository.capture_rates(technology=technology)


@router.get("/ppa-benchmarks", response_model=Page[PpaBenchmarkRowOut], summary="PPA benchmarks")
async def ppa_benchmarks(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[PpaBenchmarkRowOut]:
	"""Power-purchase-agreement benchmarks by technology and country."""
	assert state is not None, "ppa_benchmarks needs application state"
	checksum = state.repository.checksum(PPA_ARTEFACT)
	if checksum is None:
		return Page[PpaBenchmarkRowOut](items=[], total=0, limit=page.limit, offset=page.offset)

	rows = await read_through(
		state,
		namespace="market.ppa",
		checksum=checksum,
		params={"country": country},
		ttl_seconds=MARKET_TTL_SECONDS,
		producer=lambda: _produce_ppa(state, country),
		from_payload=PpaBenchmarkRowOut.model_validate,
	)
	window = rows[page.offset : page.offset + page.limit]
	return Page[PpaBenchmarkRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)


async def _produce_ppa(state, country: str | None) -> list[PpaBenchmarkRowOut]:
	assert state is not None, "a producer needs application state"
	return state.repository.ppa_benchmarks(country=country)
