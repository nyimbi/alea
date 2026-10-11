# SPDX-License-Identifier: MIT
"""FastAPI dependencies: authentication, rate limiting, tier gates, pagination.

Every route takes its principal through :func:`principal_dependency`, which is
also where the rate limit is charged. That placement is deliberate: the limiter
needs the tier, the tier comes from the key, and the key is only verified once.
Charging the limit in the same dependency that authenticates means there is no
route that can authenticate without being counted -- a route that forgot to
depend on the limiter would be a route with no limit, and the gate that checks
rate limiting would pass over it.

The public system routes (``/health``, ``/version``) are the one exception. A
health check that requires a key cannot be probed by the thing that needs to
know whether the service is up, so those routes charge the limit against the
client address instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from alea.api.auth import AuthenticationError, AuthorizationError, Principal, require_tier
from alea.api.middleware import (
	RATE_LIMIT_LIMIT_HEADER,
	RATE_LIMIT_REMAINING_HEADER,
	RATE_LIMIT_RESET_HEADER,
	RETRY_AFTER_HEADER,
	CacheStore,
	RateLimiter,
	client_subject,
)
from alea.api.tiers import Tier, rate_multiplier
from alea.api.views import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

if TYPE_CHECKING:
	from alea.api.auth import ApiKeyStore
	from alea.api.jobs import JobStore, JobWorker
	from alea.api.repository import Repository
	from alea.api.signals import SignalStore
	from alea.api.whatif import WhatIfService
	from alea.config.models import Config

API_KEY_HEADER = "X-API-Key"


@dataclass
class ApiState:
	"""Everything a route needs from the application, resolved once.

	Held on ``app.state.api`` rather than passed as a global, so a test can build
	two applications with two stores and neither sees the other's.

	The fields are typed, not ``object``: an untyped field makes every route
	that touches a store a type error, and the fix people reach for is a
	``# type: ignore`` at the call site, which is how a real mismatch stops
	being reported. The imports are under ``TYPE_CHECKING`` because this module
	is imported by every route and the stores import nothing from here -- the
	annotation is all that is needed, and a runtime import would only add an
	import-order dependency to the one module everything depends on.
	"""

	config: Config
	key_store: ApiKeyStore
	job_store: JobStore
	signal_store: SignalStore
	repository: Repository
	limiter: RateLimiter
	cache: CacheStore
	worker: JobWorker
	whatif: WhatIfService
	started_at: float


def get_state(request: Request) -> ApiState:
	"""The application state, or a 503 if the lifespan never ran."""
	assert request is not None, "get_state called with no request"
	state = getattr(request.app.state, "api", None)
	if state is None:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="the API is not fully started; the stores are not connected",
		)
	return state


StateDep = Annotated[ApiState, Depends(get_state)]


async def _charge(state: ApiState, subject: str, limit: int, request: Request) -> None:
	"""Record a hit and set the rate-limit headers, or refuse with 429.

	The headers are set on every response, not only on the refusal, so a client
	can back off before it is cut off rather than only after.
	"""
	assert subject, "a rate limit needs a subject"
	assert limit > 0, "a rate limit must be positive"
	allowed, remaining, reset = state.limiter.check(subject, limit)
	headers = {
		RATE_LIMIT_LIMIT_HEADER: str(limit),
		RATE_LIMIT_REMAINING_HEADER: str(remaining),
		RATE_LIMIT_RESET_HEADER: str(reset),
	}
	request.state.rate_headers = headers
	if not allowed:
		headers[RETRY_AFTER_HEADER] = str(reset)
		raise HTTPException(
			status_code=status.HTTP_429_TOO_MANY_REQUESTS,
			detail=f"rate limit of {limit} requests per minute exceeded; retry in {reset}s",
			headers=headers,
		)


def _refusal(exc: AuthenticationError | AuthorizationError) -> HTTPException:
	"""Turn an auth failure into an ``HTTPException`` that keeps its code.

	The detail is a dict, not a string, because the error handler reads
	``code`` out of it: the plan requires a revoked key and an unknown key to
	be distinguishable, and a handler that only sees prose collapses them into
	one ``unauthorized``. Raising the exception with the code attached is what
	keeps the two failure modes apart all the way to the client.
	"""
	assert exc.code, "an auth failure must carry a code"
	return HTTPException(
		status_code=exc.status,
		detail={"code": exc.code, "detail": exc.detail},
		headers={"WWW-Authenticate": "ApiKey"},
	)


def principal_dependency(required: Tier = Tier.PUBLIC) -> Callable[..., object]:
	"""Build a dependency that authenticates, authorises and charges the limit.

	Returning a callable rather than using ``Depends(require_tier(...))`` inline
	keeps the closure's ``__name__`` stable, which is what FastAPI uses for the
	OpenAPI security scheme and what the route-inventory test reads.
	"""

	async def _dependency(
		request: Request,
		state: StateDep,
		x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
	) -> Principal:
		"""Authenticate the presented key, check the tier, charge the limit."""
		assert required is not None, "a tier requirement must be named"
		if not x_api_key:
			# No key: charge the anonymous limit against the address and refuse.
			# Charging before refusing is what stops an unauthenticated caller
			# from hammering the endpoint for free.
			await _charge(state, client_subject(request), state.config.api.rate_limit_per_minute, request)
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail=f"missing {API_KEY_HEADER} header",
				headers={"WWW-Authenticate": "ApiKey"},
			)
		try:
			principal = await state.key_store.authenticate(x_api_key)
		except AuthenticationError as exc:
			# Authentication failures count against the address, so a brute-force
			# attempt cannot probe key ids at line rate.
			await _charge(state, client_subject(request), state.config.api.rate_limit_per_minute, request)
			raise _refusal(exc) from exc

		limit = state.config.api.rate_limit_per_minute * rate_multiplier(principal.tier)
		await _charge(state, principal.rate_limit_subject, limit, request)
		try:
			return require_tier(required, principal)
		except AuthorizationError as exc:
			raise _refusal(exc) from exc

	_dependency.__name__ = f"principal_{required.value}"
	return _dependency


async def public_dependency(
	request: Request,
	state: StateDep,
	x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> Principal:
	"""An unauthenticated-allowed dependency for system routes.

	The limit is charged against the client address when no key is present, and
	against the key's own subject when one is. This is what lets ``/health`` be
	probed without a credential while still being bounded.
	"""
	assert request is not None, "public_dependency called with no request"
	if x_api_key:
		try:
			principal = await state.key_store.authenticate(x_api_key)
		except AuthenticationError as exc:
			await _charge(
				state, client_subject(request), state.config.api.rate_limit_per_minute, request
			)
			raise _refusal(exc) from exc
		limit = state.config.api.rate_limit_per_minute * rate_multiplier(principal.tier)
		await _charge(state, principal.rate_limit_subject, limit, request)
		return principal
	await _charge(state, client_subject(request), state.config.api.rate_limit_per_minute, request)
	return Principal(key_id="anonymous", name="anonymous", tier=Tier.PUBLIC)


@dataclass(frozen=True)
class Pagination:
	"""A validated page request."""

	limit: int
	offset: int


async def pagination(
	limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
	offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
	"""Bound a page request.

	The cap is not cosmetic: an unbounded ``limit`` is a client that will time
	out holding a connection, which costs the server more than the refusal.
	"""
	assert limit >= 1, "limit must be positive"
	assert offset >= 0, "offset must be non-negative"
	return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(pagination)]

PublicDep = Annotated[Principal, Depends(public_dependency)]
AnalystDep = Annotated[Principal, Depends(principal_dependency(Tier.ANALYST))]
RestrictedDep = Annotated[Principal, Depends(principal_dependency(Tier.RESTRICTED))]
InternalDep = Annotated[Principal, Depends(principal_dependency(Tier.INTERNAL))]

PublicKeyDep = Annotated[Principal, Depends(principal_dependency(Tier.PUBLIC))]


__all__ = [
	"API_KEY_HEADER",
	"AnalystDep",
	"ApiState",
	"InternalDep",
	"Pagination",
	"PaginationDep",
	"PublicDep",
	"PublicKeyDep",
	"RestrictedDep",
	"StateDep",
	"get_state",
	"pagination",
	"principal_dependency",
	"public_dependency",
]
