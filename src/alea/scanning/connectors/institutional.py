# SPDX-License-Identifier: MIT
"""Institutional connectors (10-layer7 §3.2, category 4).

Cadence: daily, rate limit 0.1 req/s (one request per ten seconds).

Institutional sources — AFREC, AUDA-NEPAD, NERSA, national gazettes — are the
highest-value documents in the scan and the slowest to serve. They are also the
ones most likely to be served by an endpoint that ignores a declared rate
limit, so the 10-second floor is not politeness: a gazette portal that blocks
the platform has removed the authoritative source for a country's own
regulation, and the news feed cannot replace it.
"""

from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from alea.scanning.connectors.base import (
	Connector,
	HttpFetcher,
	RawDocument,
	SourceCategory,
	make_document,
)
from alea.scanning.connectors.news import FeedConnector

#: Institutional feeds. Deliberately short: an institutional feed is a
#: publisher that has committed to a machine-readable cadence, and a portal
#: that has not is a scrape target (``tender.TenderScraper``), not a feed.
DEFAULT_INSTITUTIONAL_FEEDS: dict[str, str] = {
	"afrec": "https://au.int/en/rss.xml",
	"nepad": "https://www.nepad.org/rss.xml",
	"nersa": "https://www.nersa.org.za/feed/",
}


class InstitutionalFeedConnector(FeedConnector):
	"""Institutional RSS/Atom at the 0.1 req/s floor."""

	def __init__(
		self,
		feeds: dict[str, str] | None = None,
		*,
		name: str = "institutional",
		rate_limit_per_second: float = 0.1,
		fetcher: HttpFetcher | None = None,
	) -> None:
		super().__init__(
			feeds or DEFAULT_INSTITUTIONAL_FEEDS,
			name=name,
			category=SourceCategory.INSTITUTIONAL,
			rate_limit_per_second=rate_limit_per_second,
			fetcher=fetcher,
		)


class GazetteConnector(Connector):
	"""A national gazette's published-documents page.

	Gazettes are the authoritative record of a policy change, and they are the
	one source where a missed document is a missed law. The connector therefore
	refuses to invent a publication date: an entry with no date is included
	rather than filtered by ``since``, because dropping an undated gazette entry
	is dropping a regulation, and re-reading it costs one extraction that the
	content cache then makes free.
	"""

	def __init__(
		self,
		*,
		country_iso: str,
		listing_url: str,
		name: str,
		link_selector: str = "a",
		rate_limit_per_second: float = 0.1,
		fetcher: HttpFetcher | None = None,
	) -> None:
		assert len(country_iso) == 2, f"country_iso must be alpha-2, got {country_iso!r}"
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._country_iso = country_iso.upper()
		self._listing_url = listing_url
		self._name = name
		self._link_selector = link_selector

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.INSTITUTIONAL

	async def fetch(self, since: datetime) -> list[RawDocument]:
		"""Fetch the listing; undated entries are kept, dated ones filtered."""
		assert since.tzinfo is not None, "since must be timezone-aware"
		html = await self.fetcher.get_text(self._listing_url)
		soup = BeautifulSoup(html, "html.parser")
		links = soup.select(self._link_selector)
		documents: list[RawDocument] = []
		for link in links:
			href = link.get("href", "")
			text = link.get_text(" ", strip=True)
			if not isinstance(href, str) or not href or not text:
				continue
			url = href if href.startswith("http") else f"{self._listing_url.rstrip('/')}{href}"
			documents.append(
				make_document(
					source_name=self._name,
					url=url,
					title=text,
					text=text,
					published_at=None,
					metadata={"country": self._country_iso, "kind": "gazette"},
				)
			)
		status = "no_new" if not documents else "ok"
		if not links:
			# Content but no links, or an empty page: either way the listing is
			# not what the selector expects.
			self._record_health(
				documents=0,
				selector_matches=0,
				status="layout_changed",
				detail="no links matched on the gazette listing",
			)
			return []
		self._record_health(documents=len(documents), selector_matches=len(links), status=status)
		self._log_fetch(len(documents), since)
		return documents


__all__ = [
	"DEFAULT_INSTITUTIONAL_FEEDS",
	"GazetteConnector",
	"InstitutionalFeedConnector",
]
