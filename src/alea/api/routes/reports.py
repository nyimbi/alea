# SPDX-License-Identifier: MIT
"""Report routes.

A dated report is immutable once generated (11-layer8 §6): it is a published
artefact, and the answer to "what did the daily report say on the 3rd" must not
change when a later run recomputes it. So the cache for a dated report is keyed
on the report artefact's own checksum and never expires -- a re-read is pure
cost, and a re-computation would be a falsification of the record.

A report's ``report_date`` is a path component and is validated by the
repository's path-safety check, for the same reason a scenario id is.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from alea.api.deps import PaginationDep, PublicDep, StateDep
from alea.api.views import Page, ReportOut

router = APIRouter(prefix="/reports", tags=["reports"])

CADENCES = ("daily", "weekly", "monthly", "quarterly", "annual")
"""The five cadences Layer 6 produces (09-layer6 §3)."""


@router.get("/{cadence}", response_model=Page[ReportOut], summary="Reports of one cadence")
async def list_reports(
	state: StateDep,
	principal: PublicDep,
	page: PaginationDep,
	cadence: str = Path(min_length=1),
) -> Page[ReportOut]:
	"""Reports of one cadence, newest first.

	An unknown cadence is a 422, not an empty page: a client asking for
	``/reports/dailly`` has a typo and telling them so is cheaper than letting
	them conclude no report exists.
	"""
	assert state is not None, "list_reports needs application state"
	if cadence not in CADENCES:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"unknown cadence {cadence!r}; known: {list(CADENCES)}",
		)
	reports = state.repository.reports(cadence)
	window = reports[page.offset : page.offset + page.limit]
	return Page[ReportOut](items=window, total=len(reports), limit=page.limit, offset=page.offset)


@router.get("/{cadence}/{report_date}", response_model=ReportOut, summary="One dated report")
async def get_report(
	state: StateDep,
	principal: PublicDep,
	cadence: str = Path(min_length=1),
	report_date: str = Path(min_length=4, description="ISO 8601 date, e.g. 2026-10-11."),
) -> ReportOut:
	"""One report's metadata and provenance, by cadence and date."""
	assert state is not None, "get_report needs application state"
	if cadence not in CADENCES:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"unknown cadence {cadence!r}; known: {list(CADENCES)}",
		)
	try:
		report = state.repository.report(cadence, report_date)
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
	if report is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"no {cadence} report for {report_date}",
		)
	return report
