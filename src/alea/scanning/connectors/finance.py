# SPDX-License-Identifier: MIT
"""Investment and finance connectors (10-layer7 §3.2, category 5).

Cadence: daily, rate limit 0.1 req/s.

IJGlobal, Africa Energy Portal and IFC announcements are the sources where a
generation-investment signal is most likely to be true and least likely to be
first. That asymmetry is why the category exists separately from news: a
finance announcement is a confirmation, and the priority score treats
corroboration as evidence rather than as noise.
"""

from __future__ import annotations

from datetime import UTC, datetime

from alea.scanning.connectors.base import (
	Connector,
	HttpFetcher,
	RawDocument,
	SourceCategory,
	make_document,
)
from alea.scanning.connectors.news import FeedConnector

#: Finance feeds. Africa Energy Portal is the only one of the three with a
#: stable machine-readable feed; the other two are carried as API endpoints by
#: ``IfcProjectsConnector`` below rather than as feeds that do not exist.
DEFAULT_FINANCE_FEEDS: dict[str, str] = {
	"africa_energy_portal": "https://africa-energy-portal.org/rss.xml",
}


class FinanceFeedConnector(FeedConnector):
	"""Investment and finance RSS/Atom at the 0.1 req/s floor."""

	def __init__(
		self,
		feeds: dict[str, str] | None = None,
		*,
		name: str = "finance_feeds",
		rate_limit_per_second: float = 0.1,
		fetcher: HttpFetcher | None = None,
	) -> None:
		super().__init__(
			feeds or DEFAULT_FINANCE_FEEDS,
			name=name,
			category=SourceCategory.FINANCE,
			rate_limit_per_second=rate_limit_per_second,
			fetcher=fetcher,
		)


class IfcProjectsConnector(Connector):
	"""IFC project disclosures, via the public project-search API.

	IFC's disclosure payload is the one place a financing figure is stated by
	the financier rather than by the borrower's press office, so the connector
	carries ``total_amount_usd`` through as metadata instead of letting the
	extraction layer infer an investment from prose.
	"""

	ENDPOINT = "https://disclosures.ifc.org/api/search"

	def __init__(
		self,
		*,
		region: str = "Africa",
		name: str = "ifc_projects",
		rate_limit_per_second: float = 0.1,
		fetcher: HttpFetcher | None = None,
	) -> None:
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._region = region
		self._name = name

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.FINANCE

	async def fetch(self, since: datetime) -> list[RawDocument]:
		assert since.tzinfo is not None, "since must be timezone-aware"
		response = await self.fetcher.get(
			self.ENDPOINT,
			params={"region": self._region, "rows": 100, "format": "json"},
		)
		payload = response.json()
		rows = payload.get("projects") or payload.get("results") or []
		documents: list[RawDocument] = []
		for row in rows:
			url = row.get("url") or row.get("project_url") or ""
			if not url:
				continue
			title = row.get("project_name") or row.get("name") or "IFC project"
			body = " ".join(
				str(row.get(key, ""))
				for key in ("project_name", "sector", "status", "description", "country")
			)
			documents.append(
				make_document(
					source_name=self._name,
					url=url,
					title=title,
					text=body.strip() or title,
					published_at=_parse_ifc_date(row.get("date") or row.get("approval_date")),
					metadata={
						"total_amount_usd": str(row.get("total_amount", "")),
						"country": str(row.get("country", "")),
						"provider": "ifc",
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


def _parse_ifc_date(value: str | None) -> datetime | None:
	if not value:
		return None
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return None
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=UTC)
	return parsed


__all__ = [
	"DEFAULT_FINANCE_FEEDS",
	"FinanceFeedConnector",
	"IfcProjectsConnector",
]
