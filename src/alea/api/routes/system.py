# SPDX-License-Identifier: MIT
"""System routes: health, version, jobs, runs, registry, key administration.

These are the routes that describe the service rather than its data. Three of
them are load-bearing for the plan's exit criteria:

* ``GET /jobs/{job_id}`` and ``GET /jobs/{job_id}/result`` are the poll half of
  the job pattern. ``result`` is a GET because it is a read, and it is the only
  way a caller learns a two-hour solve's answer.
* ``GET /health`` reports the state of the stores, so a deployment can tell a
  running API from one whose database did not open.
* The key-administration routes exist so that a key can be minted, listed and
  revoked through the API. The plaintext is returned once, by ``POST /keys``,
  and never again.
"""

from __future__ import annotations

import sys
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from alea import __version__
from alea.api.deps import InternalDep, PaginationDep, PublicDep, StateDep
from alea.api.jobs import JobNotFinished, JobNotFound
from alea.api.tiers import Tier
from alea.api.views import (
	ApiKeyCreatedOut,
	ApiKeyCreateRequest,
	ApiKeyOut,
	CountryOut,
	HealthOut,
	JobKind,
	JobState,
	JobStatusOut,
	Page,
	RunOut,
	TechnologyOut,
	VersionOut,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut, summary="Liveness and store state")
async def health(state: StateDep, principal: PublicDep) -> HealthOut:
	"""Report whether the service and the stores behind it are usable.

	Unauthenticated, so a supervisor can probe it. It is still rate-limited
	against the client address -- a health endpoint with no bound is a free
	denial-of-service vector.
	"""
	assert state is not None, "health needs application state"
	counts = await state.job_store.counts()
	database = "ok"
	try:
		await state.job_store.get("__probe__")
	except Exception:  # pragma: no cover - a store that cannot be read
		database = "unavailable"

	queued = counts.get(JobState.QUEUED.value, 0)
	running = counts.get(JobState.RUNNING.value, 0)
	return HealthOut(
		status="ok" if database == "ok" else "degraded",
		version=__version__,
		uptime_seconds=max(time.monotonic() - state.started_at, 0.0),
		database=database,  # type: ignore[arg-type]
		jobs_queued=queued,
		jobs_running=running,
	)


@router.get("/version", response_model=VersionOut, summary="What is running")
async def version(state: StateDep, principal: PublicDep) -> VersionOut:
	"""The application version and the API version it serves."""
	assert state is not None, "version needs application state"
	return VersionOut(
		name=state.config.api.title,
		version=__version__,
		api_version=state.config.api.version,
		python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
	)


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


@router.get("/jobs", response_model=Page[JobStatusOut], summary="List jobs")
async def list_jobs(
	state: StateDep,
	principal: InternalDep,
	page: PaginationDep,
	job_status: Annotated[JobState | None, Query(alias="status")] = None,
	kind: JobKind | None = None,
) -> Page[JobStatusOut]:
	"""Jobs, newest first.

	Internal tier: a job listing names the scenarios other principals are
	solving, which is not public information.
	"""
	assert state is not None, "list_jobs needs application state"
	jobs = await state.job_store.list(status=job_status, kind=kind, limit=page.limit)
	return Page[JobStatusOut](
		items=jobs, total=len(jobs), limit=page.limit, offset=page.offset
	)


@router.get("/jobs/{job_id}", response_model=JobStatusOut, summary="Job status")
async def job_status(state: StateDep, principal: PublicDep, job_id: str = Path(min_length=1)) -> JobStatusOut:
	"""A job's state, including whether it was interrupted.

	A caller polls this. ``status: interrupted`` means the worker died and the
	result will never appear; the caller should resubmit rather than keep
	polling, which is the distinction the store exists to make.
	"""
	assert state is not None, "job_status needs application state"
	try:
		return await state.job_store.require(job_id)
	except JobNotFound as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/result", summary="Job result")
async def job_result(state: StateDep, principal: PublicDep, job_id: str = Path(min_length=1)) -> dict:
	"""A succeeded job's result.

	A GET, because it is a read of an already-computed answer -- the plan's rule
	that a GET takes no body is about the request, not the response. Asking for
	the result of an unfinished job is a 409, not a 404: the job exists and the
	caller should keep polling.
	"""
	assert state is not None, "job_result needs application state"
	try:
		return await state.job_store.result(job_id)
	except JobNotFound as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
	except JobNotFinished as exc:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"job {exc.job_id} is {exc.status.value}; poll its status until it succeeds",
		) from exc


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=RunOut, summary="One pipeline run")
async def run_detail(
	state: StateDep, principal: PublicDep, run_id: str = Path(min_length=1)
) -> RunOut:
	"""What one pipeline run did.

	Reads the run log the pipeline writes. The run id is the join key between a
	published number and the run that produced it (00-architecture §8), so this
	endpoint is how that join is answered without shell access to the log.
	"""
	assert state is not None, "run_detail needs application state"
	from alea.api.runs import RunLog

	log = RunLog(state.config)
	record = log.get(run_id)
	if record is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"no run {run_id}; the run log holds no record of it",
		)
	return record


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


@router.get("/countries", response_model=Page[CountryOut], summary="The country registry")
async def countries(state: StateDep, principal: PublicDep, page: PaginationDep) -> Page[CountryOut]:
	"""Every AU member state, with its completeness tier and power pool."""
	assert state is not None, "countries needs application state"
	all_countries = state.repository.countries()
	window = all_countries[page.offset : page.offset + page.limit]
	return Page[CountryOut](
		items=window, total=len(all_countries), limit=page.limit, offset=page.offset
	)


@router.get("/technologies", response_model=Page[TechnologyOut], summary="The technology registry")
async def technologies(
	state: StateDep, principal: PublicDep, page: PaginationDep
) -> Page[TechnologyOut]:
	"""Every registered carrier, with its class and CO2 intensity."""
	assert state is not None, "technologies needs application state"
	out: list[TechnologyOut] = []
	for carrier, technology, intensity, renewable, storage in state.repository.technologies():
		out.append(
			TechnologyOut(
				carrier=carrier.value,
				name=technology.name,
				carrier_class=technology.klass.value,
				renewable=carrier.value in renewable,
				storage=carrier.value in storage,
				co2_intensity_t_per_mwh=intensity,
			)
		)
	window = out[page.offset : page.offset + page.limit]
	return Page[TechnologyOut](
		items=window, total=len(out), limit=page.limit, offset=page.offset
	)


# --------------------------------------------------------------------------
# Key administration
# --------------------------------------------------------------------------


@router.post(
	"/keys",
	response_model=ApiKeyCreatedOut,
	status_code=status.HTTP_201_CREATED,
	summary="Mint an API key",
)
async def create_key(
	state: StateDep, principal: InternalDep, request: ApiKeyCreateRequest
) -> ApiKeyCreatedOut:
	"""Mint a key and return its plaintext, once.

	The plaintext is never stored and never retrievable. If it is lost, the key
	is revoked and reissued -- which is the whole point of hashing at rest
	(11-layer8 §4.2).
	"""
	assert state is not None, "create_key needs application state"
	try:
		tier = Tier(request.tier)
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"unknown tier {request.tier!r}; known: {[t.value for t in Tier]}",
		) from exc
	metadata, presented = await state.key_store.create(
		request.name, tier, expires_at=request.expires_at
	)
	return ApiKeyCreatedOut(
		key_id=metadata.key_id,
		key=presented,
		name=metadata.name,
		tier=metadata.tier,
		created_at=metadata.created_at,
		expires_at=metadata.expires_at,
	)


@router.get("/keys", response_model=list[ApiKeyOut], summary="List API keys")
async def list_keys(
	state: StateDep,
	principal: InternalDep,
	include_revoked: bool = Query(default=True, description="Include revoked keys."),
	tier: str | None = Query(default=None),
) -> list[ApiKeyOut]:
	"""Key metadata. Never key material.

	Revoked keys are listed by default: the operator asking "was this key
	revoked?" is the reason this endpoint exists, and a listing that hides the
	answer is a listing that hides the answer.
	"""
	assert state is not None, "list_keys needs application state"
	parsed = Tier(tier) if tier else None
	return await state.key_store.list(tier=parsed, include_revoked=include_revoked)


@router.delete(
	"/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke an API key"
)
async def revoke_key(state: StateDep, principal: InternalDep, key_id: str = Path(min_length=1)) -> Response:
	"""Revoke a key. The row is kept, so a revoked key stays distinguishable.

	Deleting the row would make a revoked key indistinguishable from one that
	never existed, which is the failure the plan names and the gate tests.
	"""
	assert state is not None, "revoke_key needs application state"
	changed = await state.key_store.revoke(key_id)
	if not changed:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"no active key {key_id}; it does not exist or is already revoked",
		)
	return Response(status_code=status.HTTP_204_NO_CONTENT)
