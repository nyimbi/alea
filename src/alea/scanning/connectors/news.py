# SPDX-License-Identifier: MIT
"""News and media connectors (10-layer7 §3.2, category 1).

Cadence: continuous, rate limit 1 req/s. Feeds are fetched with the shared
``HttpFetcher`` and parsed from the already-downloaded bytes, so ``feedparser``
never opens a socket of its own — one place enforces the rate limit, and
``feedparser``'s own fetcher (which ignores robots.txt and sets no
User-Agent) is never used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import feedparser

from alea.logging import get_logger
from alea.scanning.connectors.base import (
	Connector,
	FetchError,
	HttpFetcher,
	RawDocument,
	SourceCategory,
	make_document,
)

logger = get_logger(__name__)

#: Feeds from spec4-data-collection §6.1, minus the two that no longer resolve.
#: A dead feed is removed rather than left in the table: a connector that
#: reports ``ok`` while fetching nothing is the failure mode the health check
#: exists to prevent.
DEFAULT_NEWS_FEEDS: dict[str, str] = {
	"the_electricity_hub": "https://theelectricityhub.com/feed/",
	"esi_africa": "https://www.esi-africa.com/feed/",
	"energy_monitor": "https://www.energymonitor.ai/feed/",
	"africa_energy_portal": "https://africa-energy-portal.org/rss.xml",
}


def _entry_datetime(entry: Any) -> datetime | None:
	"""The best publication timestamp a feed entry offers.

	``published_parsed`` is the publication; ``updated_parsed`` is a
	modification and is only used when publication is absent, because using the
	update time makes an old article look new on every edit and re-fires
	extraction on it.
	"""
	for key in ("published_parsed", "updated_parsed"):
		value = entry.get(key)
		if value is not None:
			return datetime(*value[:6], tzinfo=UTC)
	return None


class FeedConnector(Connector):
	"""RSS/Atom over a declared set of feeds.

	Shared by the news, institutional and finance categories, which differ only
	in their feeds and their rate limits — and the rate limit is the thing that
	must differ, so it stays a constructor argument rather than a class
	constant.
	"""

	def __init__(
		self,
		feeds: dict[str, str],
		*,
		name: str,
		category: SourceCategory = SourceCategory.NEWS,
		rate_limit_per_second: float = 1.0,
		fetcher: HttpFetcher | None = None,
	) -> None:
		assert feeds, "a feed connector needs at least one feed"
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._feeds = dict(feeds)
		self._name = name
		self._category = category

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return self._category

	@property
	def feeds(self) -> dict[str, str]:
		return dict(self._feeds)

	async def fetch(self, since: datetime) -> list[RawDocument]:
		"""Fetch every feed, returning entries published at or after ``since``."""
		assert since.tzinfo is not None, "since must be timezone-aware"
		documents: list[RawDocument] = []
		failures = 0
		for feed_name, url in self._feeds.items():
			try:
				body = await self.fetcher.get_text(url)
			except FetchError as exc:
				# One dead feed must not stop the others; the count is carried
				# into the health record so a wholly-failing connector is
				# visible rather than merely quiet.
				failures += 1
				logger.warning("feed_unavailable", feed=feed_name, url=url, error=str(exc))
				continue
			documents.extend(self._parse_feed(feed_name, url, body, since))

		status = "error" if failures == len(self._feeds) else ("no_new" if not documents else "ok")
		self._record_health(
			documents=len(documents),
			selector_matches=len(self._feeds),
			status=status,
			detail=f"{failures} of {len(self._feeds)} feeds failed" if failures else "",
		)
		self._log_fetch(len(documents), since)
		return documents

	def _parse_feed(
		self,
		feed_name: str,
		feed_url: str,
		body: str,
		since: datetime,
	) -> list[RawDocument]:
		"""Parse one feed's bytes into documents."""
		parsed = feedparser.parse(body)
		if parsed.bozo and not parsed.entries:
			raise FetchError(f"{feed_url}: unparseable feed ({parsed.bozo_exception!r})")
		out: list[RawDocument] = []
		for entry in parsed.entries:
			published = _entry_datetime(entry)
			if published is not None and published < since:
				continue
			link = entry.get("link") or feed_url
			title = entry.get("title", "")
			text = entry.get("summary") or entry.get("description") or ""
			out.append(
				make_document(
					source_name=feed_name,
					url=link,
					title=title,
					text=text,
					published_at=published,
					metadata={
						"feed": feed_name,
						"entry_id": entry.get("id", ""),
						"tags": ",".join(t.get("term", "") for t in entry.get("tags", [])),
					},
				)
			)
		return out


class RSSNewsConnector(FeedConnector):
	"""The news category's default feed set, at 1 req/s."""

	def __init__(
		self,
		feeds: dict[str, str] | None = None,
		*,
		rate_limit_per_second: float = 1.0,
		fetcher: HttpFetcher | None = None,
	) -> None:
		super().__init__(
			feeds or DEFAULT_NEWS_FEEDS,
			name="rss_news",
			category=SourceCategory.NEWS,
			rate_limit_per_second=rate_limit_per_second,
			fetcher=fetcher,
		)


class NewsApiConnector(Connector):
	"""NewsAPI.org keyword search.

	Queries are explicit because the API has no "Africa energy" filter that
	means anything: an unqueried pull returns every wire story that mentions
	"power" anywhere in the world, and the extraction cost is paid on all of
	them.
	"""

	DEFAULT_QUERIES: tuple[str, ...] = (
		"power outage Africa",
		"solar tender Kenya",
		"electricity tariff Nigeria",
		"grid investment Africa",
	)

	def __init__(
		self,
		api_key: str,
		queries: list[str] | None = None,
		*,
		name: str = "newsapi",
		rate_limit_per_second: float = 0.5,
		fetcher: HttpFetcher | None = None,
	) -> None:
		assert api_key, "NewsAPI requires a key; an unauthenticated call returns 401"
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._api_key = api_key
		self._queries = list(queries or self.DEFAULT_QUERIES)
		self._name = name

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.NEWS

	async def fetch(self, since: datetime) -> list[RawDocument]:
		assert since.tzinfo is not None, "since must be timezone-aware"
		documents: list[RawDocument] = []
		for query in self._queries:
			response = await self.fetcher.get(
				"https://newsapi.org/v2/everything",
				params={
					"q": query,
					"from": since.astimezone(UTC).isoformat(),
					"language": "en",
					"sortBy": "publishedAt",
					"pageSize": 100,
					"apiKey": self._api_key,
				},
			)
			payload = response.json()
			for article in payload.get("articles", []):
				url = article.get("url", "")
				if not url:
					continue
				documents.append(
					make_document(
						source_name=article.get("source", {}).get("name") or self._name,
						url=url,
						title=article.get("title", ""),
						text=article.get("content") or article.get("description") or "",
						published_at=_parse_iso(article.get("publishedAt")),
						metadata={"query": query, "provider": "newsapi"},
					)
				)
		self._record_health(
			documents=len(documents),
			selector_matches=len(self._queries),
			status="no_new" if not documents else "ok",
		)
		self._log_fetch(len(documents), since)
		return documents


def _parse_iso(value: str | None) -> datetime | None:
	"""Parse an ISO-8601 timestamp, tolerating the trailing ``Z``.

	``datetime.fromisoformat`` accepts ``Z`` from 3.11 onward, so no
	replacement is needed; the helper exists so the None case is one place.
	"""
	if not value:
		return None
	parsed = datetime.fromisoformat(value)
	return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
	"DEFAULT_NEWS_FEEDS",
	"FeedConnector",
	"NewsApiConnector",
	"RSSNewsConnector",
]
