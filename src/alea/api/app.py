# SPDX-License-Identifier: MIT
"""The FastAPI application factory.

``create_app(config)`` is the only entry point, and it takes the loaded
configuration rather than reading one: the CLI has already merged the default
file, the environment file, a scenario overlay and the command line, and a
factory that loaded its own config would silently serve a different one from the
process that started it.

**Everything durable is opened in the lifespan, not at import.** The stores are
files; a factory that opened them at import would make ``create_app`` fail in a
test that never sends a request, and would make the failure an import error
rather than a startup error. The lifespan also recovers abandoned jobs and
starts the worker, which is what makes a job submitted before a restart
reportable afterwards.

**No route computes** (11-layer8 §1). Routes read the repository or enqueue a
job. The worker that runs jobs is started here and lives outside the request
path, so a two-hour solve cannot block a request.

Route prefixes are ``/api/v1``. The version is in the path because the response
models are part of the contract and a change to them is a breaking change, which
is exactly what a version segment is for.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from alea import __version__
from alea.api import auth, jobs, signals
from alea.api.adapters import dashboard, sms, ussd, whatsapp
from alea.api.deps import ApiState
from alea.api.middleware import (
	CACHE_SCHEMA,
	CacheStore,
	RateLimiter,
	RequestContextMiddleware,
)
from alea.api.repository import ArtefactUnavailable, Repository
from alea.api.routes import ROUTERS
from alea.api.views import ErrorOut
from alea.api.whatif import WhatIfService
from alea.config.models import Config
from alea.io.artefacts import ArtefactError
from alea.logging import get_logger

logger = get_logger(__name__)

API_PREFIX = "/api/v1"

DESCRIPTION = """\
ALEA — African Light and Energy Analytics.

One API, many delivery adapters (AD-7). Every response is a pydantic model, and
**every quantity carries its basis**: a value is never served as a bare number,
so a consumer cannot render a proxy estimate as though it were a measurement.

Long-running work is enqueued, never executed inline. `POST /whatif/solve`
returns 202 with a job id; poll `GET /jobs/{job_id}` and read
`GET /jobs/{job_id}/result` when it succeeds. A job that was interrupted by a
restart reports `interrupted`, so a caller learns its solve died rather than
polling a corpse.
"""


def _cors_origins() -> list[str]:
	"""Allowed browser origins, from ``ALEA_API_CORS_ORIGINS``.

	Empty by default. An API authenticated by a header key is not protected from
	a browser by CORS, and a wildcard would let any page on the internet call it
	with a key it has scraped from a client. The embeddable-widget channel
	(11-layer8 §5) names its origins here.
	"""
	raw = os.environ.get("ALEA_API_CORS_ORIGINS", "")
	return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(config: Config) -> FastAPI:
	"""Build the API application for a loaded configuration.

	The returned application is fully constructed but its stores are not yet
	open: the lifespan connects them on startup and closes them on shutdown.
	"""
	assert config is not None, "create_app needs the loaded configuration"
	assert config.api is not None, "the configuration carries no api section"

	job_store = jobs.JobStore(config.api.job_store_path)
	key_store = auth.ApiKeyStore(auth.key_store_path(config.api.job_store_path))
	signal_store = signals.SignalStore(config.api.job_store_path)
	# The response cache shares the job store's file: both are small bookkeeping
	# tables, and one file is one thing to back up and one lock to reason about.
	cache = CacheStore(job_store.database.with_schema(CACHE_SCHEMA))

	repository = Repository(config)
	whatif = WhatIfService(config, repository)
	worker = jobs.JobWorker(job_store)
	whatif.register(worker)

	@asynccontextmanager
	async def lifespan(app: FastAPI) -> AsyncIterator[None]:
		"""Open the stores, recover abandoned jobs, run the worker, then unwind."""
		await job_store.connect()
		await key_store.connect()
		await signal_store.connect()
		await key_store.bootstrap_from_env()

		app.state.api = ApiState(
			config=config,
			key_store=key_store,
			job_store=job_store,
			signal_store=signal_store,
			repository=repository,
			limiter=RateLimiter(),
			cache=cache,
			worker=worker,
			whatif=whatif,
			started_at=time.monotonic(),
		)
		await worker.start()
		logger.info(
			"api.started",
			version=__version__,
			title=config.api.title,
			job_store=str(job_store.path),
			job_handlers=worker.registered_kinds,
		)
		try:
			yield
		finally:
			await worker.stop()
			await signal_store.close()
			await key_store.close()
			await job_store.close()
			logger.info("api.stopped")

	app = FastAPI(
		title=config.api.title,
		version=config.api.version,
		description=DESCRIPTION,
		lifespan=lifespan,
		docs_url="/docs",
		redoc_url="/redoc",
		openapi_url="/openapi.json",
	)

	app.add_middleware(RequestContextMiddleware)
	origins = _cors_origins()
	if origins:
		app.add_middleware(
			CORSMiddleware,
			allow_origins=origins,
			allow_credentials=False,
			allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
			allow_headers=["X-API-Key", "X-Request-ID", "Content-Type"],
			expose_headers=[
				"X-Request-ID",
				"X-RateLimit-Limit",
				"X-RateLimit-Remaining",
				"X-RateLimit-Reset",
				"Retry-After",
			],
		)

	_install_error_handlers(app)

	for router in ROUTERS:
		app.include_router(router, prefix=API_PREFIX)
	for adapter in (ussd.router, sms.router, whatsapp.router, dashboard.router):
		app.include_router(adapter, prefix=API_PREFIX)

	@app.get("/", include_in_schema=False)
	async def root() -> RedirectResponse:
		"""Send a bare visitor to the documentation."""
		return RedirectResponse(url="/docs")

	# The inventory is read through the unwrap, not off app.routes: FastAPI wraps
	# an included router in a class whose own ``path`` is None, so counting
	# ``app.routes`` entries reports the wrappers and undercounts the routes by
	# everything the routers carry (11-layer8 §9). assert_inventory canaries the
	# walk against a route known to exist before the total is trusted, and then
	# checks that every route module in the package actually reached the app --
	# a router left out of ROUTERS is otherwise invisible.
	from alea.api.inventory import assert_every_router_mounted, assert_inventory

	assert_inventory(app)
	assert_every_router_mounted(app, prefix=API_PREFIX)
	return app


def _install_error_handlers(app: FastAPI) -> None:
	"""Map the domain's exceptions onto HTTP statuses with stable codes.

	Every handler returns :class:`ErrorOut`, so a client branches on ``code``
	rather than on prose. A missing artefact is a 404 naming the artefact, not a
	500: the ordinary state of a young deployment is that a layer has not
	published yet, and reporting that as a server fault sends an operator looking
	for a bug in the wrong place.
	"""

	@app.exception_handler(RequestValidationError)
	async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
		return _error(422, "validation_error", _validation_detail(exc), request)

	@app.exception_handler(StarletteHTTPException)
	async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
		# Routes raise HTTPException with a ``detail`` that may be a string or a
		# dict. Normalising it here is what keeps the error body the same shape
		# everywhere, so a client reads ``code`` rather than guessing whether it
		# got a route's error or the framework's.
		detail = exc.detail
		if isinstance(detail, dict):
			code = str(detail.get("code", "error"))
			message = str(detail.get("detail", detail))
		else:
			code = _code_for_status(exc.status_code)
			message = str(detail)
		response = _error(exc.status_code, code, message, request)
		for name, value in (exc.headers or {}).items():
			response.headers[name] = value
		return response

	@app.exception_handler(ArtefactUnavailable)
	async def _unavailable(request: Request, exc: ArtefactUnavailable) -> JSONResponse:
		return _error(404, "artefact_unavailable", str(exc), request)

	@app.exception_handler(ArtefactError)
	async def _artefact_error(request: Request, exc: ArtefactError) -> JSONResponse:
		return _error(500, "artefact_error", str(exc), request)

	@app.exception_handler(auth.AuthenticationError)
	async def _auth_error(request: Request, exc: auth.AuthenticationError) -> JSONResponse:
		return _error(exc.status, exc.code, exc.detail, request)

	@app.exception_handler(auth.AuthorizationError)
	async def _authz_error(request: Request, exc: auth.AuthorizationError) -> JSONResponse:
		return _error(exc.status, exc.code, exc.detail, request)

	@app.exception_handler(jobs.JobNotFound)
	async def _job_not_found(request: Request, exc: jobs.JobNotFound) -> JSONResponse:
		return _error(404, "job_not_found", str(exc), request)

	@app.exception_handler(signals.SignalNotFound)
	async def _signal_not_found(request: Request, exc: signals.SignalNotFound) -> JSONResponse:
		return _error(404, "signal_not_found", str(exc), request)

	@app.exception_handler(ValueError)
	async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
		# A ValueError reaching a handler is a rejected input -- an unsafe path
		# component, a horizon a scenario has no result for. It is the caller's
		# problem, so it is a 422 and not a 500.
		return _error(422, "invalid_request", str(exc), request)


_STATUS_CODES: dict[int, str] = {
	400: "bad_request",
	401: "unauthorized",
	403: "forbidden",
	404: "not_found",
	405: "method_not_allowed",
	409: "conflict",
	413: "payload_too_large",
	422: "unprocessable_entity",
	429: "rate_limited",
	500: "internal_error",
	503: "service_unavailable",
}


def _code_for_status(status_code: int) -> str:
	"""The stable code for a status a route raised without naming one."""
	return _STATUS_CODES.get(status_code, "error")


def _validation_detail(exc: RequestValidationError) -> str:
	"""A one-line summary of a validation failure, naming the offending fields."""
	problems = []
	for error in exc.errors()[:8]:
		location = ".".join(str(part) for part in error.get("loc", ()))
		problems.append(f"{location}: {error.get('msg', 'invalid')}")
	return "; ".join(problems) or "the request did not validate"


def _error(status_code: int, code: str, detail: str, request: Request) -> JSONResponse:
	assert code, "an error must carry a machine-readable code"
	request_id = getattr(request.state, "request_id", "")
	return JSONResponse(
		status_code=status_code,
		content=ErrorOut(code=code, detail=detail, request_id=request_id).model_dump(mode="json"),
		headers={"X-Request-ID": request_id} if request_id else None,
	)


__all__ = ["API_PREFIX", "DESCRIPTION", "create_app"]
