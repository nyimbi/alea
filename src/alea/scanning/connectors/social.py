# SPDX-License-Identifier: MIT
"""Social media connectors (10-layer7 §3.3).

The retention policy lives here, at the boundary, not in the pipeline.

X's API terms restrict redistribution and storage of content. The platform
stores **signal-level extractions with the source URL**, not the post text, and
raw text expires after ``scanning.raw_text_retention_days`` (default 90). A
connector that hands the pipeline a post body and trusts the pipeline to expire
it has put the legal exposure in a place where one forgotten call leaks it, so
the body is truncated to a bounded prefix here and the expiry is enforced in
``scanning.ingest`` against the same number.

``text_is_retainable`` is the switch: a connector built with
``retain_text=False`` emits documents whose ``text`` is the extraction-relevant
excerpt only, and the pipeline is told so via the ``text_retention`` metadata
key. The full text is never written to the data lake in that mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alea.logging import get_logger
from alea.scanning.connectors.base import (
	Connector,
	HttpFetcher,
	RawDocument,
	SourceCategory,
	make_document,
)

logger = get_logger(__name__)

#: The longest prefix of a social post that is retained for extraction.
#: X's own character limits sit well inside this; the cap exists so a
#: pasted article in a post does not become a 40 kB raw-text liability.
SOCIAL_TEXT_CAP = 1200

#: Told to the pipeline via document metadata, so retention is decided by what
#: the document *is* rather than by which connector produced it.
TEXT_RETENTION_RESTRICTED = "restricted"
TEXT_RETENTION_NORMAL = "normal"


class SocialConnector(Connector):
	"""A social-platform API connector.

	The platform-specific query and payload shape are injected as callables so
	this class owns the one thing that is legally and operationally uniform —
	retention — and the platform specifics stay in one small function each.

	``extract_posts`` receives the API's decoded JSON and returns a list of
	dicts with ``id``, ``text``, ``created_at``, ``url`` and optional
	``author``/``place``.
	"""

	def __init__(
		self,
		*,
		name: str,
		endpoint: str,
		params: dict[str, Any],
		extract_posts: Any,
		api_token: str = "",
		retain_text: bool = False,
		rate_limit_per_second: float = 0.2,
		fetcher: HttpFetcher | None = None,
	) -> None:
		assert endpoint.startswith(("http://", "https://")), "social endpoints are absolute"
		super().__init__(rate_limit_per_second=rate_limit_per_second, fetcher=fetcher)
		self._name = name
		self._endpoint = endpoint
		self._params = dict(params)
		self._extract_posts = extract_posts
		self._api_token = api_token
		self._retain_text = retain_text

	@property
	def source_name(self) -> str:
		return self._name

	@property
	def category(self) -> SourceCategory:
		return SourceCategory.SOCIAL

	@property
	def retain_text(self) -> bool:
		return self._retain_text

	async def fetch(self, since: datetime) -> list[RawDocument]:
		assert since.tzinfo is not None, "since must be timezone-aware"
		headers = {"Authorization": f"Bearer {self._api_token}"} if self._api_token else {}
		params = {**self._params, "start_time": since.astimezone(UTC).isoformat()}
		response = await self.fetcher.get(self._endpoint, params=params, headers=headers)
		posts = self._extract_posts(response.json())

		documents: list[RawDocument] = []
		for post in posts:
			body = str(post.get("text", ""))
			# Truncate before the document exists, so the full post never
			# reaches a hashing function, a log line, or the data lake.
			excerpt = body[:SOCIAL_TEXT_CAP]
			documents.append(
				make_document(
					source_name=self._name,
					url=str(post.get("url", "")),
					title=excerpt[:120],
					text=excerpt,
					published_at=post.get("created_at"),
					metadata={
						"post_id": str(post.get("id", "")),
						"author": str(post.get("author", "")),
						"place": str(post.get("place", "")),
						"text_retention": (
							TEXT_RETENTION_NORMAL if self._retain_text else TEXT_RETENTION_RESTRICTED
						),
						"truncated": str(len(body) > SOCIAL_TEXT_CAP).lower(),
					},
				)
			)
		self._record_health(
			documents=len(documents),
			selector_matches=len(posts),
			status="no_new" if not documents else "ok",
		)
		self._log_fetch(len(documents), since)
		return documents


def x_recent_search(
	query: str,
	*,
	api_token: str,
	max_results: int = 100,
	rate_limit_per_second: float = 0.2,
	fetcher: HttpFetcher | None = None,
) -> SocialConnector:
	"""X (Twitter) recent-search connector.

	The endpoint is the v2 recent-search API. ``extract_posts`` is a closure
	rather than a method so the platform's payload shape has exactly one place
	to change when it changes — and it will change, because every social API
	does.
	"""

	def extract(payload: dict[str, Any]) -> list[dict[str, Any]]:
		out: list[dict[str, Any]] = []
		for item in payload.get("data", []):
			post_id = str(item.get("id", ""))
			out.append(
				{
					"id": post_id,
					"text": item.get("text", ""),
					"created_at": _parse_created(item.get("created_at")),
					"url": f"https://x.com/i/web/status/{post_id}",
					"author": item.get("author_id", ""),
				}
			)
		return out

	return SocialConnector(
		name="x_recent_search",
		endpoint="https://api.x.com/2/tweets/search/recent",
		params={
			"query": query,
			"max_results": max_results,
			"tweet.fields": "created_at,author_id,geo",
		},
		extract_posts=extract,
		api_token=api_token,
		retain_text=False,
		rate_limit_per_second=rate_limit_per_second,
		fetcher=fetcher,
	)


def _parse_created(value: str | None) -> datetime | None:
	if not value:
		return None
	parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
	"SOCIAL_TEXT_CAP",
	"TEXT_RETENTION_NORMAL",
	"TEXT_RETENTION_RESTRICTED",
	"SocialConnector",
	"x_recent_search",
]
