# SPDX-License-Identifier: MIT
"""What-if routes. Every one of these returns a job, never an answer.

The specification's version runs ``engine.solve`` inline, for up to two hours,
blocking the event loop (11-layer8 §2.3). Here ``POST /whatif/solve`` submits a
job and returns 202 with a status URL; the caller polls ``/jobs/{id}``. The
solve happens in the worker, outside the request path, and its result survives a
restart because the job store is a file.

The three POSTs take a body because they carry a complex one -- that is the
plan's rule, applied mechanically: a GET takes scalars, a POST takes a body.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from alea.api.deps import AnalystDep, StateDep
from alea.api.views import (
	JobAcceptedOut,
	JobKind,
	JobState,
	WhatIfCompareRequest,
	WhatIfFrontierRequest,
	WhatIfSolveRequest,
)

router = APIRouter(prefix="/whatif", tags=["what-if"])


def _accepted(job_id: str, kind, job_status: JobState) -> JobAcceptedOut:
	assert job_id, "a job without an id cannot be polled"
	return JobAcceptedOut(
		job_id=job_id,
		kind=kind,
		status=job_status,
		status_url=f"/api/v1/jobs/{job_id}",
		result_url=f"/api/v1/jobs/{job_id}/result",
	)


@router.post(
	"/solve",
	response_model=JobAcceptedOut,
	status_code=status.HTTP_202_ACCEPTED,
	summary="Enqueue a what-if solve",
)
async def solve(
	state: StateDep, principal: AnalystDep, request: WhatIfSolveRequest
) -> JobAcceptedOut:
	"""Enqueue a what-if solve. Returns 202 and a status URL.

	A 202, not a 200: the answer does not exist yet and returning anything else
	would be a lie the client cannot detect.
	"""
	assert state is not None, "solve needs application state"
	job_id = await state.whatif.enqueue_solve(
		state.job_store, request, requested_by=principal.key_id
	)
	return _accepted(job_id, JobKind.WHATIF_SOLVE, JobState.QUEUED)


@router.post(
	"/frontier",
	response_model=JobAcceptedOut,
	status_code=status.HTTP_202_ACCEPTED,
	summary="Enqueue a frontier sweep",
)
async def frontier(
	state: StateDep, principal: AnalystDep, request: WhatIfFrontierRequest
) -> JobAcceptedOut:
	"""Enqueue a sweep of one parameter across a range."""
	assert state is not None, "frontier needs application state"
	job_id = await state.whatif.enqueue_frontier(
		state.job_store, request, requested_by=principal.key_id
	)
	return _accepted(job_id, JobKind.WHATIF_FRONTIER, JobState.QUEUED)


@router.post(
	"/compare",
	response_model=JobAcceptedOut,
	status_code=status.HTTP_202_ACCEPTED,
	summary="Enqueue a scenario comparison",
)
async def compare(
	state: StateDep, principal: AnalystDep, request: WhatIfCompareRequest
) -> JobAcceptedOut:
	"""Enqueue a comparison of two or more solved scenarios.

	Enqueued rather than computed inline because a comparison of scenarios that
	have not been solved must solve them, and the cost is not bounded by the
	number of scenarios in the request.
	"""
	assert state is not None, "compare needs application state"
	status_out = await state.job_store.submit(
		JobKind.WHATIF_COMPARE,
		request.model_dump(mode="json"),
		requested_by=principal.key_id,
	)
	return _accepted(status_out.job_id, JobKind.WHATIF_COMPARE, status_out.status)
