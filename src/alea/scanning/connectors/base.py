# SPDX-License-Identifier: MIT
"""Connector primitives.

A connector retrieves and normalises; it never interprets (10-layer7 §3.1). The
reason is testability: a connector that classifies is a connector whose
classification cannot be checked against the extraction layer's, and the two
would silently disagree about what an outage is.

Three things here exist because their absence has a specific failure:

* ``RateLimiter`` — a connector that gets the platform's IP banned from a
  national procurement portal has removed a source permanently. The limit is
  declared per connector and enforced before every request.
* ``RobotsPolicy`` (inside ``HttpFetcher``) — scraping a portal that asked not
  to be scraped is a legal problem and an operational one.
* ``ScrapeHealth`` — a scraper that returns ``[]`` on a layout change is a
  scraper that has silently stopped working, and the difference between "no new
  documents" and "broken" must be in the return value, not in a log line nobody
  reads.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import (
	AsyncRetrying,
	retry_if_exception_type,
	stop_after_attempt,
	wait_exponential,
)

from alea.io.artefacts import sha256_bytes, utcnow
from alea.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = (
	"ALEA-IntelligenceScanner/0.1 (+https://github.com/alea-africa/alea; "
	"contact: scanning@alea.example)"
)
"""Identifies the project and a contact route.

An anonymous User-Agent is what gets a crawler blocked; naming the project is
the minimum a portal operator needs to decide whether to allow it.
"""


class SourceCategory(StrEnum):
	"""The five connector categories of 10-layer7 §3.2."""

	NEWS = "news"
	TENDER = "tender"
	SOCIAL = "social"
	INSTITUTIONAL = "institutional"
	FINANCE = "finance"


class FetchError(RuntimeError):
	"""A document could not be retrieved."""


class FetchBlocked(FetchError):
	"""robots.txt or a portal refusal stopped the request.

	Distinct from a transport error because it is not retryable: retrying a
	refusal is how a polite crawler becomes a banned one.
	"""


def document_identity_hash(
	source_name: str,
	url: str,
	title: str,
	published_at: datetime | None,
) -> str:
	"""The exact-dedup key of 10-layer7 §4.1.

	SHA-256 of ``(source_name, url, title, published_at)``. The unit separator
	keeps ``("ab", "c")`` and ``("a", "bc")`` from colliding, which a plain
	concatenation would allow.
	"""
	parts = [
		source_name,
		url,
		title,
		published_at.astimezone(UTC).isoformat() if published_at is not None else "",
	]
	return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawDocument:
	"""One retrieved document, before any interpretation."""

	document_id: str
	"""Content hash of (source, url, title, published)."""
	source_name: str
	source_url: str
	title: str
	text: str
	published_at: datetime | None
	retrieved_at: datetime
	content_hash: str
	"""sha256 of ``text``. Distinct from ``document_id``: two outlets
	publishing the same wire copy share a ``content_hash`` but not an identity."""
	metadata: dict[str, str] = field(default_factory=dict)

	@property
	def is_usable(self) -> bool:
		"""Whether there is text to extract from.

		A title-only document is common in RSS and extracting from it produces a
		signal whose evidence is the headline, which is not evidence.
		"""
		return bool(self.text.strip())


def make_document(
	*,
	source_name: str,
	url: str,
	title: str,
	text: str,
	published_at: datetime | None = None,
	retrieved_at: datetime | None = None,
	metadata: dict[str, Any] | None = None,
) -> RawDocument:
	"""Build a ``RawDocument`` with its two hashes computed.

	Every connector routes through here so ``document_id`` is computed one way.
	Two connectors computing it differently would defeat exact deduplication at
	the boundary, and the symptom — reprocessing the same article every run —
	would look like a scheduling bug.
	"""
	if published_at is not None and published_at.tzinfo is None:
		# A naive timestamp compared against an aware ``since`` raises at
		# comparison time, deep inside a fetch loop. Coercing here keeps the
		# whole package on one convention: aware UTC everywhere.
		published_at = published_at.replace(tzinfo=UTC)
	return RawDocument(
		document_id=document_identity_hash(source_name, url, title, published_at),
		source_name=source_name,
		source_url=url,
		title=title,
		text=text,
		published_at=published_at,
		retrieved_at=retrieved_at or utcnow(),
		content_hash=sha256_bytes(text.encode("utf-8")),
		metadata={str(k): str(v) for k, v in (metadata or {}).items()},
	)


class ScrapeHealth(BaseModel):
	"""A scraper's result must distinguish 'no new documents' from 'broken'."""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	source_name: str
	documents_found: int = Field(ge=0)
	selector_matches: int = Field(ge=0)
	"""Zero with documents on the page = broken."""
	status: Literal["ok", "no_new", "layout_changed", "blocked", "error"]
	checked_at: datetime = Field(default_factory=utcnow)
	detail: str = ""

	@property
	def is_healthy(self) -> bool:
		return self.status in ("ok", "no_new")


class RateLimiter:
	"""A minimum-interval limiter, per connector.

	Minimum interval rather than a token bucket: the requirement is "no
	connector exceeds its declared rate" (10-layer7 §9), and a limiter that
	allows a burst of ``n`` and then sleeps cannot state that property. This one
	can, because every gap between successive requests is at least
	``1 / rate_per_second``.

	``history`` records the monotonic timestamp of each admitted request so the
	gate can measure the intervals instead of trusting the class.
	"""

	def __init__(self, rate_per_second: float) -> None:
		assert rate_per_second > 0.0, "a rate limit must be positive"
		self.rate_per_second = rate_per_second
		self._min_interval = 1.0 / rate_per_second
		self._last: float | None = None
		self._lock = asyncio.Lock()
		self.history: list[float] = []

	@property
	def min_interval(self) -> float:
		"""The smallest permitted gap between two requests, in seconds."""
		return self._min_interval

	def intervals(self) -> list[float]:
		"""The observed gaps between admitted requests.

		A caller asserting the gate compares ``min(intervals())`` against
		``min_interval``.
		"""
		return [b - a for a, b in zip(self.history, self.history[1:], strict=False)]

	async def acquire(self) -> None:
		"""Wait until the next request is permitted, then admit it."""
		async with self._lock:
			now = time.monotonic()
			if self._last is not None:
				wait = self._min_interval - (now - self._last)
				if wait > 0:
					await asyncio.sleep(wait)
					now = time.monotonic()
			self._last = now
			self.history.append(now)


class _RetryableStatus(Exception):
	"""A response the connector should retry: 429 and 5xx."""


class HttpFetcher:
	"""Rate-limited, robots-aware HTTP.

	Retries 429 and 5xx with exponential backoff; never retries a 4xx other
	than 429, because a 404 retried three times is three times the load for the
	same answer.
	"""

	def __init__(
		self,
		rate_limit_per_second: float,
		*,
		timeout_s: float = 30.0,
		max_retries: int = 3,
		user_agent: str = USER_AGENT,
		respect_robots: bool = True,
		client: httpx.AsyncClient | None = None,
	) -> None:
		assert rate_limit_per_second > 0.0
		assert max_retries >= 1
		self.limiter = RateLimiter(rate_limit_per_second)
		self.timeout_s = timeout_s
		self.max_retries = max_retries
		self.user_agent = user_agent
		self.respect_robots = respect_robots
		self._http = client
		self._owns_client = client is None
		self._robots: dict[str, RobotFileParser | None] = {}

	@property
	def rate_limit_per_second(self) -> float:
		return self.limiter.rate_per_second

	async def _client(self) -> httpx.AsyncClient:
		if self._http is None:
			self._http = httpx.AsyncClient(
				timeout=self.timeout_s,
				follow_redirects=True,
				headers={"User-Agent": self.user_agent},
			)
		return self._http

	async def aclose(self) -> None:
		"""Close the client, but only one this fetcher created.

		An injected client belongs to the caller (a test fixture, or a shared
		pool) and closing it would break the next connector to use it.
		"""
		if self._http is not None and self._owns_client:
			await self._http.aclose()
			self._http = None

	async def __aenter__(self) -> HttpFetcher:
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.aclose()

	# -- robots ----------------------------------------------------------

	async def _load_robots(self, origin: str) -> RobotFileParser | None:
		"""Fetch and parse ``origin/robots.txt``.

		``None`` means "no policy found, crawling permitted", which is the
		convention for a 404. A 401 or 403 is a refusal and becomes
		``Disallow: /``: a portal that answers "forbidden" to its own robots
		file is not inviting a crawler.
		"""
		url = f"{origin}/robots.txt"
		client = await self._client()
		try:
			await self.limiter.acquire()
			response = await client.get(url)
		except httpx.HTTPError as exc:
			logger.warning("robots_unavailable", url=url, error=str(exc))
			return None
		if response.status_code in (401, 403):
			parser = RobotFileParser()
			parser.parse(["User-agent: *", "Disallow: /"])
			return parser
		if response.status_code >= 400:
			return None
		parser = RobotFileParser()
		parser.parse(response.text.splitlines())
		return parser

	async def robots_allowed(self, url: str) -> bool:
		"""Whether ``url`` may be fetched under the host's robots.txt."""
		if not self.respect_robots:
			return True
		parts = urlparse(url)
		origin = f"{parts.scheme}://{parts.netloc}"
		if origin not in self._robots:
			self._robots[origin] = await self._load_robots(origin)
		parser = self._robots[origin]
		return True if parser is None else parser.can_fetch(self.user_agent, url)

	# -- requests --------------------------------------------------------

	async def get(
		self,
		url: str,
		*,
		params: dict[str, Any] | None = None,
		headers: dict[str, str] | None = None,
	) -> httpx.Response:
		"""GET with rate limiting, robots enforcement, and bounded retries."""
		assert url.startswith(("http://", "https://")), f"not an absolute URL: {url!r}"
		if not await self.robots_allowed(url):
			raise FetchBlocked(f"robots.txt disallows {url} for {self.user_agent}")
		client = await self._client()
		response: httpx.Response | None = None
		async for attempt in AsyncRetrying(
			stop=stop_after_attempt(self.max_retries),
			wait=wait_exponential(multiplier=0.5, max=8.0),
			retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
			reraise=True,
		):
			with attempt:
				# Inside the retry, not outside it: a retry is another request
				# and must be limited like any other.
				await self.limiter.acquire()
				response = await client.get(url, params=params, headers=headers)
				if response.status_code == 429 or response.status_code >= 500:
					raise _RetryableStatus(f"{response.status_code} from {url}")
				response.raise_for_status()
		assert response is not None, "tenacity returned without a response"
		return response

	async def get_text(self, url: str, **kwargs: Any) -> str:
		"""GET and decode, refusing a body that is not text."""
		response = await self.get(url, **kwargs)
		content_type = response.headers.get("content-type", "")
		if content_type and not any(
			t in content_type for t in ("text", "xml", "json", "rss", "atom")
		):
			raise FetchError(f"{url}: refusing content-type {content_type!r}")
		return response.text


class Connector(ABC):
	"""A source of documents.

	Subclasses declare ``source_name``, ``category`` and
	``rate_limit_per_second``; the base owns the fetcher so no connector can
	forget to limit itself.
	"""

	def __init__(
		self,
		*,
		rate_limit_per_second: float,
		user_agent: str = USER_AGENT,
		respect_robots: bool = True,
		fetcher: HttpFetcher | None = None,
	) -> None:
		self._fetcher = fetcher or HttpFetcher(
			rate_limit_per_second,
			user_agent=user_agent,
			respect_robots=respect_robots,
		)
		if fetcher is not None:
			assert fetcher.rate_limit_per_second == rate_limit_per_second, (
				"an injected fetcher must carry the connector's declared rate limit"
			)
		self._last_health: ScrapeHealth | None = None

	@abstractmethod
	async def fetch(self, since: datetime) -> list[RawDocument]:
		"""Fetch documents published at or after ``since``."""

	@property
	@abstractmethod
	def source_name(self) -> str: ...

	@property
	@abstractmethod
	def category(self) -> SourceCategory: ...

	@property
	def rate_limit_per_second(self) -> float:
		"""The declared rate. Honoured by the base fetcher."""
		return self._fetcher.rate_limit_per_second

	@property
	def fetcher(self) -> HttpFetcher:
		return self._fetcher

	def health_check(self) -> ScrapeHealth:
		"""The last fetch's health.

		Returns ``no_new`` before any fetch has run rather than inventing an
		``ok``, because a connector that has never run is not a healthy one.
		"""
		if self._last_health is None:
			return ScrapeHealth(
				source_name=self.source_name,
				documents_found=0,
				selector_matches=0,
				status="no_new",
				detail="no fetch has run yet",
			)
		return self._last_health

	def _record_health(
		self,
		*,
		documents: int,
		selector_matches: int,
		status: Literal["ok", "no_new", "layout_changed", "blocked", "error"],
		detail: str = "",
	) -> ScrapeHealth:
		health = ScrapeHealth(
			source_name=self.source_name,
			documents_found=documents,
			selector_matches=selector_matches,
			status=status,
			detail=detail,
		)
		self._last_health = health
		return health

	async def aclose(self) -> None:
		await self._fetcher.aclose()

	async def __aenter__(self) -> Connector:
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.aclose()

	def _log_fetch(self, count: int, since: datetime) -> None:
		logger.info(
			"connector_fetch",
			source=self.source_name,
			category=self.category.value,
			documents=count,
			since=since.isoformat(),
		)


__all__ = [
	"USER_AGENT",
	"Connector",
	"FetchBlocked",
	"FetchError",
	"HttpFetcher",
	"RateLimiter",
	"RawDocument",
	"ScrapeHealth",
	"SourceCategory",
	"document_identity_hash",
	"make_document",
]
