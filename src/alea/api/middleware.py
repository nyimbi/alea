# SPDX-License-Identifier: MIT
"""Request identity, structured logging, and rate limiting.

Three cross-cutting concerns, in the order they matter.

**A request id on every response.** One pipeline run is traced by a run id
threaded through logs and artefact provenance (00-architecture §8); one HTTP
request is traced the same way, so a caller reporting a bad number can quote the
id and the operator can find the log line that produced it. An inbound
``X-Request-ID`` is honoured, so an id assigned by a gateway or a mobile client
survives into the API's logs.

**Rate limits are per key and per tier, and the numbers come back in the
headers.** A client that only learns it is over the limit by being refused
cannot back off; a client that sees ``X-RateLimit-Remaining: 0`` can slow down
before it is cut off. The limit itself is computed by the auth dependency, which
is the only place that knows the principal and its tier, and the header
middleware copies the result onto the response.

**The limiter is in-process and therefore per-worker.** That is a real limit: two
API processes behind a load balancer each allow the full rate. The alternative
is Redis, which the platform does not depend on anywhere else, and introducing a
new service for a counter is the trade the review queue also declined
(10-layer7 §6.1). It is recorded here rather than discovered under load.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from alea._uuid7 import uuid7str
from alea.logging import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
RATE_LIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
RATE_LIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"
RETRY_AFTER_HEADER = "Retry-After"

WINDOW_SECONDS = 60.0
"""The rate-limit window. One minute, matching ``rate_limit_per_minute``."""


class RateLimitExceeded(Exception):
	"""A caller has used its allowance.

	Carries the headers the response must bear, so the refusal and the
	successful responses describe the same limit in the same units.
	"""

	def __init__(self, limit: int, retry_after: int) -> None:
		assert limit > 0, "a limit must be positive"
		assert retry_after >= 0, "retry_after is a non-negative number of seconds"
		super().__init__(f"rate limit of {limit} requests per minute exceeded")
		self.limit = limit
		self.retry_after = retry_after
		self.headers = {
			RATE_LIMIT_LIMIT_HEADER: str(limit),
			RATE_LIMIT_REMAINING_HEADER: "0",
			RATE_LIMIT_RESET_HEADER: str(retry_after),
			RETRY_AFTER_HEADER: str(retry_after),
		}


class RateLimiter:
	"""A sliding-window counter, keyed by subject.

	Sliding rather than fixed-window because a fixed window lets a caller spend
	its whole allowance at 59.9 s and again at 60.1 s, which is double the
	intended rate at exactly the moment a burst is most damaging.
	"""

	def __init__(self, *, window_seconds: float = WINDOW_SECONDS, max_subjects: int = 100_000) -> None:
		assert window_seconds > 0, "a window must have positive length"
		assert max_subjects > 0, "the subject table must be bounded or it leaks"
		self.window_seconds = window_seconds
		self.max_subjects = max_subjects
		self._hits: dict[str, deque[float]] = defaultdict(deque)

	def check(self, subject: str, limit: int, *, now: float | None = None) -> tuple[bool, int, int]:
		"""Record a hit for ``subject`` and report ``(allowed, remaining, reset)``.

		``now`` is injectable so the test can advance the clock without sleeping.
		"""
		assert subject, "a rate limit needs a subject to count against"
		assert limit > 0, f"limit must be positive, got {limit}"
		moment = time.monotonic() if now is None else now
		window_start = moment - self.window_seconds

		hits = self._hits[subject]
		while hits and hits[0] <= window_start:
			hits.popleft()

		if len(hits) >= limit:
			reset = int(self.window_seconds - (moment - hits[0])) + 1
			return False, 0, max(reset, 1)

		hits.append(moment)
		if len(self._hits) > self.max_subjects:
			self._prune(window_start)
		reset = int(self.window_seconds - (moment - hits[0])) + 1
		return True, max(limit - len(hits), 0), max(reset, 1)

	def _prune(self, window_start: float) -> None:
		"""Drop subjects whose entire window has expired.

		Without this the table grows with the number of distinct callers and
		never shrinks -- a slow leak that only shows up in production.
		"""
		dead = [subject for subject, hits in self._hits.items() if not hits or hits[-1] <= window_start]
		for subject in dead:
			del self._hits[subject]

	def reset(self) -> None:
		"""Clear all counters. For tests and for a config reload."""
		self._hits.clear()


class RequestContextMiddleware(BaseHTTPMiddleware):
	"""Assigns a request id, binds it to the logs, and returns it in the headers."""

	def __init__(self, app, *, header: str = REQUEST_ID_HEADER) -> None:
		super().__init__(app)
		self.header = header

	async def dispatch(
		self, request: Request, call_next: RequestResponseEndpoint
	) -> Response:
		"""Run the request with an id in context, and echo the rate-limit headers."""
		assert request is not None, "dispatch called with no request"
		request_id = request.headers.get(self.header) or uuid7str()
		request.state.request_id = request_id
		structlog.contextvars.bind_contextvars(request_id=request_id)
		started = time.perf_counter()
		try:
			response = await call_next(request)
		except Exception:
			# Log the failure with the id before it propagates, so the id in the
			# caller's error body joins to a log line.
			elapsed_ms = (time.perf_counter() - started) * 1000
			logger.exception(
				"http.request.failed",
				method=request.method,
				path=request.url.path,
				elapsed_ms=round(elapsed_ms, 2),
			)
			raise
		finally:
			structlog.contextvars.unbind_contextvars("request_id")

		elapsed_ms = (time.perf_counter() - started) * 1000
		response.headers[self.header] = request_id
		# The limiter ran inside the auth dependency, which is downstream of
		# this middleware and upstream of the route, so its result is on state.
		for name, value in getattr(request.state, "rate_headers", {}).items():
			response.headers[name] = value
		logger.info(
			"http.request",
			method=request.method,
			path=request.url.path,
			status=response.status_code,
			elapsed_ms=round(elapsed_ms, 2),
		)
		return response


def client_subject(request: Request) -> str:
	"""The rate-limit subject for an unauthenticated request.

	The client address. Behind a proxy this is the proxy's address unless the
	deployment sets ``X-Forwarded-For``; the API does not trust that header by
	default because a caller can set it, and a spoofable rate-limit subject is a
	rate limit that can be bypassed one header at a time.
	"""
	assert request is not None, "client_subject called with no request"
	client = request.client
	return f"ip:{client.host}" if client is not None else "ip:unknown"


async def install_middleware(app, *, request_header: str = REQUEST_ID_HEADER) -> None:
	"""Add the context middleware. Kept as a function so the ordering is explicit."""
	assert app is not None, "install_middleware called with no application"
	app.add_middleware(RequestContextMiddleware, header=request_header)


MiddlewareFactory = Callable[[object], Awaitable[None]]


# --------------------------------------------------------------------------
# Response cache
# --------------------------------------------------------------------------

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS response_cache (
	cache_key     TEXT PRIMARY KEY,
	namespace     TEXT NOT NULL,
	checksum      TEXT NOT NULL,
	body          TEXT NOT NULL,
	stored_at     REAL NOT NULL,
	expires_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS response_cache_expiry ON response_cache (expires_at);
"""


def cache_key(namespace: str, *, checksum: str, params: dict[str, object]) -> str:
	"""A deterministic cache key over the endpoint, the artefact and the parameters.

	The checksum is the part the specification omits and the part that matters:
	a key built from the URL alone serves a result computed against a previous
	network, which is the same defect as Layer 5's ``hash()``-based key
	(00-architecture AD-8, 08-layer5 §2.2). Two requests for the same endpoint
	with the same parameters against different networks must miss.

	Canonical JSON with sorted keys and no reliance on ``hash()``, so the key is
	identical in two processes (``PYTHONHASHSEED`` does not enter into it).
	"""
	assert namespace, "a cache key needs a namespace"
	assert checksum, (
		"a cache key without an artefact checksum serves a result computed "
		"against a network that may since have changed"
	)
	import hashlib
	import json

	canonical = json.dumps(
		{"namespace": namespace, "checksum": checksum, "params": params},
		sort_keys=True,
		separators=(",", ":"),
		default=str,
	)
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CacheStore:
	"""A durable response cache, keyed by endpoint, checksum and parameters.

	Durable rather than in-memory because the expensive responses are the ones
	worth keeping across a restart, and because a per-worker cache multiplies
	the miss rate by the number of workers.
	"""

	def __init__(self, database) -> None:
		assert database is not None, "a cache needs a database"
		self._database = database

	async def get(self, key: str, *, now: float | None = None) -> dict[str, object] | None:
		"""A cached body, or ``None`` if absent or expired."""
		assert key, "get needs a cache key"
		import json
		import time

		moment = time.time() if now is None else now
		row = await self._database.fetchone(
			"SELECT body, expires_at FROM response_cache WHERE cache_key = ?", (key,)
		)
		if row is None:
			return None
		if float(row["expires_at"]) <= moment:
			# Expired rows are left for the sweeper rather than deleted on read:
			# a read is on the hot path and a delete here would take a write lock
			# for every cache miss.
			return None
		return json.loads(row["body"])

	async def put(
		self,
		key: str,
		namespace: str,
		checksum: str,
		body: dict[str, object],
		*,
		ttl_seconds: float,
		now: float | None = None,
	) -> None:
		"""Store a body under a key with a time-to-live."""
		assert key and namespace, "a cache entry needs a key and a namespace"
		assert ttl_seconds > 0, f"ttl must be positive, got {ttl_seconds}"
		import json
		import time

		moment = time.time() if now is None else now
		await self._database.execute(
			"""
			INSERT INTO response_cache (cache_key, namespace, checksum, body, stored_at, expires_at)
			VALUES (?, ?, ?, ?, ?, ?)
			ON CONFLICT(cache_key) DO UPDATE SET
				body = excluded.body,
				stored_at = excluded.stored_at,
				expires_at = excluded.expires_at
			""",
			(key, namespace, checksum, json.dumps(body, sort_keys=True), moment, moment + ttl_seconds),
		)

	async def sweep(self, *, now: float | None = None) -> int:
		"""Delete expired entries. Returns how many were removed."""
		import time

		moment = time.time() if now is None else now
		return await self._database.execute(
			"DELETE FROM response_cache WHERE expires_at <= ?", (moment,)
		)

	async def clear(self, *, namespace: str | None = None) -> int:
		"""Drop entries, optionally only one namespace's."""
		if namespace is None:
			return await self._database.execute("DELETE FROM response_cache")
		return await self._database.execute(
			"DELETE FROM response_cache WHERE namespace = ?", (namespace,)
		)


__all__ = [
	"RATE_LIMIT_LIMIT_HEADER",
	"RATE_LIMIT_REMAINING_HEADER",
	"RATE_LIMIT_RESET_HEADER",
	"REQUEST_ID_HEADER",
	"RETRY_AFTER_HEADER",
	"WINDOW_SECONDS",
	"MiddlewareFactory",
	"RateLimitExceeded",
	"RateLimiter",
	"RequestContextMiddleware",
	"client_subject",
	"install_middleware",
]
