# SPDX-License-Identifier: MIT
"""Source connectors (10-layer7 §3).

Five categories, one interface. A connector retrieves and normalises; it never
interprets. Everything downstream — deduplication, extraction, scoring — works
on ``RawDocument`` and knows nothing about where a document came from, which is
what makes a connector replaceable and testable in isolation.
"""

from alea.scanning.connectors.base import (
	USER_AGENT,
	Connector,
	FetchBlocked,
	FetchError,
	HttpFetcher,
	RateLimiter,
	RawDocument,
	ScrapeHealth,
	SourceCategory,
	document_identity_hash,
	make_document,
)
from alea.scanning.connectors.finance import (
	DEFAULT_FINANCE_FEEDS,
	FinanceFeedConnector,
	IfcProjectsConnector,
)
from alea.scanning.connectors.institutional import (
	DEFAULT_INSTITUTIONAL_FEEDS,
	GazetteConnector,
	InstitutionalFeedConnector,
)
from alea.scanning.connectors.news import (
	DEFAULT_NEWS_FEEDS,
	FeedConnector,
	NewsApiConnector,
	RSSNewsConnector,
)
from alea.scanning.connectors.social import (
	SOCIAL_TEXT_CAP,
	TEXT_RETENTION_NORMAL,
	TEXT_RETENTION_RESTRICTED,
	SocialConnector,
	x_recent_search,
)
from alea.scanning.connectors.tender import (
	ScraperCanary,
	SelectorSpec,
	TenderApiConnector,
	TenderScraper,
)


def default_connectors() -> list[Connector]:
	"""The connectors a scan runs with no further configuration.

	Only the ones whose feed list is a published constant. The connectors that
	need a credential or a site-specific selector are left out deliberately: a
	Gazette connector is built per country against that country's listing page,
	and a default that guessed a URL would fetch the wrong document and record
	it under a real gazette's name.

	The credential-gated ones are included when their credential is present, so
	a configured deployment scans more without a code change and an
	unconfigured one scans less rather than failing.
	"""
	import os

	connectors: list[Connector] = [
		RSSNewsConnector(),
		InstitutionalFeedConnector(),
		FinanceFeedConnector(),
		IfcProjectsConnector(),
	]
	if api_key := os.environ.get("NEWSAPI_KEY"):
		connectors.append(NewsApiConnector(api_key))
	if token := os.environ.get("X_BEARER_TOKEN"):
		connectors.append(x_recent_search("power outage Africa", api_token=token))
	return connectors


__all__ = [
	"DEFAULT_FINANCE_FEEDS",
	"DEFAULT_INSTITUTIONAL_FEEDS",
	"DEFAULT_NEWS_FEEDS",
	"SOCIAL_TEXT_CAP",
	"TEXT_RETENTION_NORMAL",
	"TEXT_RETENTION_RESTRICTED",
	"USER_AGENT",
	"Connector",
	"FeedConnector",
	"FetchBlocked",
	"FetchError",
	"FinanceFeedConnector",
	"GazetteConnector",
	"HttpFetcher",
	"IfcProjectsConnector",
	"InstitutionalFeedConnector",
	"NewsApiConnector",
	"RSSNewsConnector",
	"RateLimiter",
	"RawDocument",
	"ScrapeHealth",
	"ScraperCanary",
	"SelectorSpec",
	"SocialConnector",
	"SourceCategory",
	"TenderApiConnector",
	"TenderScraper",
	"document_identity_hash",
	"default_connectors",
	"make_document",
	"x_recent_search",
]
