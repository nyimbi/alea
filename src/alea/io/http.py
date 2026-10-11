# SPDX-License-Identifier: MIT
"""The HTTP client every fetcher uses.

One client, so that three things are true of every retrieval rather than of the
fetchers that remembered them:

* **A named User-Agent.** An anonymous client is what gets a project blocked
  from a national data portal, and the block is permanent in practice.
* **A bounded body.** ``max_bytes`` refuses a response that is larger than the
  caller expected instead of filling a disk. Several of these endpoints answer a
  bad path with a multi-megabyte HTML error page.
* **An offline switch.** ``ALEA_OFFLINE=1`` makes every request raise. The test
  suite must not touch the network, and a convention that lives only in a
  fixture's docstring is a convention the next test file does not inherit.

Retries are bounded and only on transport errors and 5xx: a 404 from a data
portal is an answer, not a transient failure, and retrying it wastes the rate
limit a later call needs.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from alea.logging import get_logger

_log = get_logger(__name__)

USER_AGENT = "ALEA/0.1 (+https://github.com/nyimbi/alea)"
"""Identifies the project. A portal operator needs this to allow the traffic."""

DEFAULT_TIMEOUT_S = 120.0
"""Generous: the ERA5 and GWA rasters are tens of megabytes on a slow link."""

DEFAULT_MAX_BYTES = 512 * 1024 * 1024
"""Half a gigabyte. Above this a fetch is a mistake, not a download."""


class HttpError(RuntimeError):
	"""A request could not be completed, or answered with something unusable."""


def offline() -> bool:
	"""Whether the environment forbids network access.

	Read at call time rather than cached: a test that sets the variable inside
	the process must take effect for the next call, and a module-level constant
	would have been read before the test ran.
	"""
	return os.environ.get("ALEA_OFFLINE", "").strip() not in ("", "0", "false", "False")


def _client(timeout: float) -> httpx.Client:
	return httpx.Client(
		timeout=timeout,
		follow_redirects=True,
		headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
	)


def _request(
	method: str,
	url: str,
	*,
	params: dict[str, Any] | None = None,
	headers: dict[str, str] | None = None,
	content: bytes | None = None,
	timeout: float = DEFAULT_TIMEOUT_S,
	max_bytes: int = DEFAULT_MAX_BYTES,
) -> bytes:
	"""One request, with the offline guard, bounded retries, and a size ceiling.

	The size ceiling is enforced while streaming, not from ``Content-Length``:
	a portal that lies about the length, or omits it, would otherwise defeat the
	only check standing between a typo and a full disk.
	"""
	if offline():
		raise HttpError(
			f"ALEA_OFFLINE is set; refusing to {method} {url}. Unset it to fetch."
		)
	if not url.startswith(("http://", "https://")):
		raise HttpError(f"not an absolute URL: {url!r}")

	last_error: Exception | None = None
	for attempt in range(3):
		try:
			with (
				_client(timeout) as client,
				client.stream(
					method, url, params=params, headers=headers, content=content
				) as response,
			):
				if response.status_code >= 500 or response.status_code == 429:
					response.read()
					raise HttpError(f"{response.status_code} from {url}")
				if response.status_code >= 400:
					response.read()
					raise _Permanent(f"{response.status_code} from {url}")
				chunks: list[bytes] = []
				total = 0
				for chunk in response.iter_bytes():
					total += len(chunk)
					if total > max_bytes:
						raise _Permanent(
							f"{url} exceeded the {max_bytes} byte ceiling; the "
							f"endpoint answered with more than it should"
						)
					chunks.append(chunk)
				return b"".join(chunks)
		except _Permanent:
			raise
		except (httpx.TransportError, HttpError) as exc:
			last_error = exc
			_log.warning("http_retry", url=url, attempt=attempt + 1, error=str(exc))
	raise HttpError(f"{method} {url} failed after 3 attempts: {last_error}")


class _Permanent(Exception):
	"""A 4xx or an oversized body. Retrying either is a waste of the rate limit."""


def get_bytes(
	url: str,
	*,
	params: dict[str, Any] | None = None,
	headers: dict[str, str] | None = None,
	timeout: float = DEFAULT_TIMEOUT_S,
	max_bytes: int = DEFAULT_MAX_BYTES,
) -> bytes:
	"""GET a URL and return its body."""
	return _request(
		"GET", url, params=params, headers=headers, timeout=timeout, max_bytes=max_bytes
	)


def get_text(
	url: str,
	*,
	encoding: str = "utf-8",
	params: dict[str, Any] | None = None,
	headers: dict[str, str] | None = None,
	timeout: float = DEFAULT_TIMEOUT_S,
	max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
	"""GET a URL and decode it. The portal decides nothing about the encoding."""
	return get_bytes(
		url, params=params, headers=headers, timeout=timeout, max_bytes=max_bytes
	).decode(encoding, errors="replace")


def get_json(
	url: str,
	*,
	params: dict[str, Any] | None = None,
	headers: dict[str, str] | None = None,
	timeout: float = DEFAULT_TIMEOUT_S,
	max_bytes: int = DEFAULT_MAX_BYTES,
) -> Any:
	"""GET a URL and parse the body as JSON.

	Parsing here rather than at each call site, because a portal that answers
	``200`` with an HTML error page produces a ``JSONDecodeError`` that says
	nothing about which endpoint did it.
	"""
	payload = get_bytes(
		url, params=params, headers=headers, timeout=timeout, max_bytes=max_bytes
	)
	try:
		return json.loads(payload)
	except json.JSONDecodeError as exc:
		raise HttpError(
			f"{url} answered {len(payload)} bytes that are not JSON ({exc}); "
			f"first 120 bytes: {payload[:120]!r}"
		) from exc


def post_json(
	url: str,
	payload: Any,
	*,
	headers: dict[str, str] | None = None,
	timeout: float = DEFAULT_TIMEOUT_S,
	max_bytes: int = DEFAULT_MAX_BYTES,
) -> Any:
	"""POST a JSON body and parse the JSON response.

	The PxWeb statistical APIs take their whole query in the body and answer
	``200`` with an HTML error page when the query is malformed, so the parse
	error is turned into one that names the endpoint.
	"""
	body = json.dumps(payload).encode("utf-8")
	sent = {"Content-Type": "application/json", **(headers or {})}
	response = _request(
		"POST", url, headers=sent, content=body, timeout=timeout, max_bytes=max_bytes
	)
	try:
		return json.loads(response)
	except json.JSONDecodeError as exc:
		raise HttpError(
			f"POST {url} answered {len(response)} bytes that are not JSON ({exc})"
		) from exc


__all__ = [
	"DEFAULT_MAX_BYTES",
	"DEFAULT_TIMEOUT_S",
	"USER_AGENT",
	"HttpError",
	"get_bytes",
	"get_json",
	"get_text",
	"offline",
	"post_json",
]
