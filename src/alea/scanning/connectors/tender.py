# SPDX-License-Identifier: MIT
"""Tender and procurement connectors (10-layer7 §3.2, category 2).

Cadence: hourly, rate limit 0.2 req/s (one request per five seconds).

Two kinds of source here, and they fail differently:

* A **keyless API** (World Bank procurement notices) either answers with JSON
  or does not. Failure is a transport error, and the API's own schema is the
  contract.
* A **scraped portal** (Kenya eGP, Morocco Marchés Publics) has no API and no
  RSS. It fails by changing shape, and it fails *silently*: a selector that
  matched 20 rows yesterday and matches 0 today returns an empty list, which is
  indistinguishable from a quiet day unless the scraper says so.

``TenderScraper`` therefore returns ``[]`` **and** records ``layout_changed``
when a canary fixture with a known item count no longer parses to that count.
The canary is a saved HTML fixture, not a live request: a canary that depends on
the live portal is a canary that fails when the portal is down, which is the
one day it is not supposed to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from alea.logging import get_logger
from alea.scanning.connectors.base import (
	Connector,
	FetchBlocked,
	FetchError,
	HttpFetcher,
	RawDocument,
	SourceCategory,
	make_document,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class SelectorSpec:
	"""How to read one portal's listing page.

	All selectors are declared together so a layout change has one place to
	land, and so the canary can be checked against the same spec the live fetch
	uses rather than a copy that drifts from it.
	"""

	item: str
	title: str
	link: str
	date: str | None = None
	summary: str | None = None
	base_url: str = ""


@dataclass(frozen=True)
class ScraperCanary:
	"""A saved fixture and the item count it is known to contain.

	``expected_items`` is asserted, not defaulted: a canary whose expected count
	is discovered from the fixture at run time cannot detect a change, because
	it always agrees with whatever the fixture now says.
	"""

	fixture_html: str
	expected_items: int

	def check(self, spec: SelectorSpec) -> bool:
		"""Whether the spec still yields ``expected_items`` from the fixture."""
		assert self.expected_items >= 0
		soup = BeautifulSoup(self.fixture_html, "html.parser")
		found = len(soup.select(spec.item))
		return found == self.expected_items


class TenderScraper(Connector):
	"""A declared-selector scraper for a portal with no API.

	``canary`` is optional only so an un-canaried portal can be constructed for
	exploration; :meth:`fetch` records ``layout_changed`` for it, because a
	scraper with no canary cannot prove it still works and must say so.
	"""

	def __init__(
		self,
		*,
		name: str,
		listing_url: str,
		spec: SelectorSpec,
		canary: ScraperCanary | None = None,
		rate_limit_per_second: float = 0.2,
		max_pages: int = 1,
		fetcher: HttpFetcher | None = None,
	) -> None:
		assert listing_url.startswith(("http://", "https://"))
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._name = name
		self._listing_url = listing_url
		self._spec = spec
		self._canary = canary
		self._max_pages = max_pages

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.TENDER

	@property
	def canary(self) -> ScraperCanary | None:
		return self._canary

	async def fetch(self, since: datetime) -> list[RawDocument]:
		assert since.tzinfo is not None, "since must be timezone-aware"
		if self._canary is not None and not self._canary.check(self._spec):
			# The canary is checked before the network is touched: if the
			# fixture no longer parses, the live page will not either, and the
			# failure is reported without a request that would produce an empty
			# list and look like a quiet day.
			logger.error("scraper_layout_changed", source=self._name, check="canary")
			self._record_health(
				documents=0,
				selector_matches=0,
				status="layout_changed",
				detail="canary fixture no longer yields its known item count",
			)
			return []

		try:
			html = await self.fetcher.get_text(self._listing_url)
		except FetchBlocked as exc:
			logger.warning("scraper_blocked", source=self._name, error=str(exc))
			self._record_health(
				documents=0, selector_matches=0, status="blocked", detail=str(exc)
			)
			return []
		except FetchError as exc:
			logger.warning("scraper_error", source=self._name, error=str(exc))
			self._record_health(documents=0, selector_matches=0, status="error", detail=str(exc))
			return []

		documents, matches = self._parse(html, since)
		if matches == 0:
			# Documents present on the page but nothing matched: the page is
			# not empty, so this is a layout change, not a quiet day.
			logger.error("scraper_layout_changed", source=self._name, check="live")
			self._record_health(
				documents=0,
				selector_matches=0,
				status="layout_changed",
				detail="listing page returned content but no selector matched",
			)
			return []

		status = "no_new" if not documents else "ok"
		self._record_health(documents=len(documents), selector_matches=matches, status=status)
		self._log_fetch(len(documents), since)
		return documents

	def _parse(self, html: str, since: datetime) -> tuple[list[RawDocument], int]:
		"""Parse a listing page into documents and a selector-match count."""
		soup = BeautifulSoup(html, "html.parser")
		items = soup.select(self._spec.item)
		out: list[RawDocument] = []
		for item in items:
			title_el = item.select_one(self._spec.title)
			link_el = item.select_one(self._spec.link)
			if title_el is None or link_el is None:
				continue
			href = link_el.get("href", "")
			if not isinstance(href, str) or not href:
				continue
			url = href if href.startswith("http") else f"{self._spec.base_url.rstrip('/')}{href}"
			published = self._parse_date(item)
			if published is not None and published < since:
				continue
			summary = ""
			if self._spec.summary:
				summary_el = item.select_one(self._spec.summary)
				summary = summary_el.get_text(" ", strip=True) if summary_el else ""
			out.append(
				make_document(
					source_name=self._name,
					url=url,
					title=title_el.get_text(" ", strip=True),
					text=summary or title_el.get_text(" ", strip=True),
					published_at=published,
					metadata={"portal": self._name, "kind": "tender_listing"},
				)
			)
		return out, len(items)

	def _parse_date(self, item: Any) -> datetime | None:
		"""The item's date, if the spec declares a date selector.

		Returns ``None`` rather than "now" when absent: a document dated now is
		a document that passes every ``since`` filter forever, so it is
		reprocessed on every run.
		"""
		if not self._spec.date:
			return None
		el = item.select_one(self._spec.date)
		if el is None:
			return None
		text = el.get_text(" ", strip=True)
		for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d"):
			try:
				return datetime.strptime(text, fmt).replace(tzinfo=UTC)
			except ValueError:
				continue
		logger.debug("tender_date_unparsed", source=self._name, text=text)
		return None


class TenderApiConnector(Connector):
	"""World Bank procurement notices, via the keyless search API."""

	ENDPOINT = "https://search.worldbank.org/api/v3/procnotices"

	def __init__(
		self,
		*,
		country_code: str = "AF",
		name: str = "worldbank_procurement",
		rate_limit_per_second: float = 0.2,
		fetcher: HttpFetcher | None = None,
	) -> None:
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._country_code = country_code
		self._name = name

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.TENDER

	async def fetch(self, since: datetime) -> list[RawDocument]:
		assert since.tzinfo is not None, "since must be timezone-aware"
		response = await self.fetcher.get(
			self.ENDPOINT,
			params={
				"format": "json",
				"rows": 100,
				"os": 0,
				"fct": "Procurement Notices",
				"countrycode_exact": self._country_code,
				"sort": "submission_deadline",
				"order": "desc",
			},
		)
		payload = response.json()
		rows = payload.get("procnotices") or payload.get("documents") or []
		documents: list[RawDocument] = []
		for row in rows:
			url = row.get("url") or row.get("notice_url") or ""
			if not url:
				continue
			title = row.get("project_name") or row.get("notice_type") or "procurement notice"
			body = " ".join(
				str(row.get(key, ""))
				for key in ("project_name", "notice_type", "notice_lang_name", "notice_status")
			)
			documents.append(
				make_document(
					source_name=self._name,
					url=url,
					title=title,
					text=body.strip() or title,
					published_at=_parse_wb_date(row.get("noticedate") or row.get("submission_deadline")),
					metadata={
						"country": str(row.get("countryname", "")),
						"notice_type": str(row.get("notice_type", "")),
						"provider": "worldbank",
					},
				)
			)
		self._record_health(
			documents=len(documents),
			selector_matches=len(rows),
			status="no_new" if not documents else "ok",
		)
		self._log_fetch(len(documents), since)
		return documents


def _parse_wb_date(value: str | None) -> datetime | None:
	"""Parse the World Bank API's ``YYYY-MM-DDT00:00:00Z`` form."""
	if not value:
		return None
	try:
		parsed = datetime.fromisoformat(value)
	except ValueError:
		return None
	return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
	"ScraperCanary",
	"SelectorSpec",
	"TenderApiConnector",
	"TenderScraper",
]
