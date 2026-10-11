# SPDX-License-Identifier: MIT
"""Signal routes: list, read, review.

Restricted tier. A signal is an unconfirmed extraction from a source document,
and a list of them is a list of claims nobody has checked; serving that at the
public tier would let an unverified extraction circulate as a finding.

``POST /signals/review`` records an analyst's decision. The decision is
append-only (10-layer7 §6.2), so this endpoint is the one place the platform's
human-in-the-loop principle is enforced from outside: a signal that reaches the
integration stage unreviewed is refused there, and this is how it stops being
unreviewed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from alea.api.deps import PaginationDep, RestrictedDep, StateDep
from alea.api.signals import SignalNotFound
from alea.api.views import Page, ReviewActionOut, SignalOut, SignalReviewRequest, SignalSummaryOut
from alea.signals.models import SignalType

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=Page[SignalSummaryOut], summary="List signals")
async def list_signals(
	state: StateDep,
	principal: RestrictedDep,
	page: PaginationDep,
	signal_type: Annotated[SignalType | None, Query()] = None,
	country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
	requires_review: Annotated[bool | None, Query()] = None,
	since: Annotated[datetime | None, Query(description="ISO 8601; extracted at or after.")] = None,
) -> Page[SignalSummaryOut]:
	"""Signals matching the filters, newest first."""
	assert state is not None, "list_signals needs application state"
	items, total = await state.signal_store.list(
		signal_type=signal_type,
		country=country,
		requires_review=requires_review,
		since=since,
		limit=page.limit,
		offset=page.offset,
	)
	return Page[SignalSummaryOut](
		items=items, total=total, limit=page.limit, offset=page.offset
	)


@router.get("/{signal_id}", response_model=SignalOut, summary="One signal")
async def get_signal(
	state: StateDep, principal: RestrictedDep, signal_id: str = Path(min_length=1)
) -> SignalOut:
	"""A full signal, with its evidence quotes and its quantitative payload."""
	assert state is not None, "get_signal needs application state"
	try:
		return await state.signal_store.require(signal_id)
	except SignalNotFound as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
	"/{signal_id}/actions", response_model=list[ReviewActionOut], summary="A signal's review history"
)
async def signal_actions(
	state: StateDep, principal: RestrictedDep, signal_id: str = Path(min_length=1)
) -> list[ReviewActionOut]:
	"""The append-only review history of one signal, oldest first.

	This is what makes "the model changed because an analyst corrected the
	capacity" auditable, and it is the record the extraction-accuracy feedback
	loop reads (10-layer7 §6.3).
	"""
	assert state is not None, "signal_actions needs application state"
	return await state.signal_store.actions(signal_id)


@router.post(
	"/review",
	response_model=ReviewActionOut,
	status_code=status.HTTP_201_CREATED,
	summary="Record a review decision",
)
async def review_signal(
	state: StateDep, principal: RestrictedDep, request: SignalReviewRequest
) -> ReviewActionOut:
	"""Confirm, reject, edit or merge one signal.

	A POST with a body, because a review carries structured edits and an
	analyst's name. ``signal_id`` is in the body rather than the path because
	the decision is about the signal, not a sub-resource of it, and a review is
	never a read.
	"""
	assert state is not None, "review_signal needs application state"
	try:
		return await state.signal_store.review(request.signal_id, request)
	except SignalNotFound as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
	"/{signal_id}/review",
	response_model=ReviewActionOut,
	status_code=status.HTTP_201_CREATED,
	summary="Record a review decision on one signal",
)
async def review_one_signal(
	state: StateDep,
	principal: RestrictedDep,
	request: SignalReviewRequest,
	signal_id: str = Path(min_length=1),
) -> ReviewActionOut:
	"""The same decision, with the signal named in the path.

	Both spellings exist because a client batching decisions wants the body form
	and a client acting on a screen wants the path form, and neither is wrong.
	"""
	assert state is not None, "review_one_signal needs application state"
	try:
		return await state.signal_store.review(signal_id, request)
	except SignalNotFound as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
