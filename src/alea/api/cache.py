# SPDX-License-Identifier: MIT
"""Read-through caching for the endpoints the plan names as cacheable.

The rule (11-layer8 §6): a cache key includes the artefact checksum, not just
the endpoint. A key over the URL alone serves a result computed against a
previous network, which is the same defect as Layer 5's ``hash()``-based key.

Two kinds of entry, distinguished by how they are keyed.

**Derived responses** (prices, forecasts) are cached under
``endpoint + input checksum + parameters`` with a TTL, because the input can
change under them.

**Immutable responses** (a dated report) are cached under
``endpoint + artefact checksum`` and never expire, because a dated report is a
published artefact: it cannot change, and re-reading it is pure cost. The TTL
for those is set to a century, which is a long way of writing "never" in a
store whose only eviction is expiry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from alea.api.middleware import cache_key
from alea.logging import get_logger

logger = get_logger(__name__)

NEVER_EXPIRES_SECONDS = 100 * 365 * 24 * 3600
"""A dated artefact does not change. One century is the plan's "never"."""


async def read_through[ModelT: BaseModel](
	state: Any,
	*,
	namespace: str,
	checksum: str,
	params: dict[str, Any],
	ttl_seconds: float,
	producer: Callable[[], Awaitable[list[ModelT]]],
	from_payload: Callable[[dict[str, Any]], ModelT],
) -> list[ModelT]:
	"""Return a cached list, or produce, cache and return it.

	``checksum`` is required, not optional: a caller that cannot name the
	artefact version it is about to read has no business caching the answer, and
	making the argument mandatory is what forces that to be true at the call
	site rather than in a comment.
	"""
	assert namespace, "a cache namespace is required"
	assert checksum, "a cache key must include the input artefact's checksum"
	assert ttl_seconds > 0, f"ttl must be positive, got {ttl_seconds}"

	key = cache_key(namespace, checksum=checksum, params=params)
	cached = await state.cache.get(key)
	if cached is not None:
		logger.debug("cache.hit", namespace=namespace, key=key[:12])
		items = cached.get("items", [])
		return [from_payload(item) for item in items]

	produced = await producer()
	await state.cache.put(
		key,
		namespace,
		checksum,
		{"items": [item.model_dump(mode="json") for item in produced]},
		ttl_seconds=ttl_seconds,
	)
	return produced


__all__ = ["NEVER_EXPIRES_SECONDS", "read_through"]
