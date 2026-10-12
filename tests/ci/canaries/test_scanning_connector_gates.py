# SPDX-License-Identifier: MIT
"""Canaries for the connector gates: rate limiting and layout change.

Both gates are asserted in ``tests/ci/test_scanning_gates.py``. A gate is only
evidence once it has been watched failing on the defect it exists to catch, and
these are the two defects:

* ``test_connector_rate_limit`` — the limiter is bypassed. The defect is real:
  a retry is another request, so ``await self.limiter.acquire()`` belongs
  *inside* the retry block, not above it. Moved out, a 429 storm admits as many
  requests as the server returns errors and the declared rate means nothing.
* ``test_scraper_layout_canary`` — a page with content and zero selector matches
  is reported as a quiet day rather than a layout change. The whole point of
  ``layout_changed`` is that ``[]`` has two meanings, and this canary is the one
  that keeps the two from collapsing back into one.

Each runs its probe in a **subprocess**: the mutation is read fresh from disk by
an interpreter that never saw the original, and no reloaded module is left
behind for the tests that follow. ``planted`` asserts the target is present
before writing and restores from a file backup afterwards.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

BASE_PY = REPO / "src" / "alea" / "scanning" / "connectors" / "base.py"
TENDER_PY = REPO / "src" / "alea" / "scanning" / "connectors" / "tender.py"


# --------------------------------------------------------------------------
# Gate: test_connector_rate_limit
# --------------------------------------------------------------------------

# The rate-limit probe: three feeds at 50/s. It prints the smallest observed
# gap and the declared interval; a bypassed limiter makes the smallest gap
# collapse toward zero. Run in a subprocess so the mutated module is fresh.
_RATE_PROBE = textwrap.dedent(
	"""
	import asyncio, httpx, textwrap
	from alea.scanning.connectors import HttpFetcher, RSSNewsConnector
	from datetime import UTC, datetime

	FEED = '<rss version="2.0"><channel><item><title>t</title>' \\
	       '<link>https://ex.org/a</link><description>Kenya added 100 MW.</description>' \\
	       '<pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'

	def handler(request):
		return httpx.Response(200, text=FEED, headers={'content-type': 'application/rss+xml'})

	async def main():
		rate = 50.0
		fetcher = HttpFetcher(rate, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), respect_robots=False)
		connector = RSSNewsConnector(
			feeds={'a': 'https://ex.org/1', 'b': 'https://ex.org/2', 'c': 'https://ex.org/3'},
			rate_limit_per_second=rate, fetcher=fetcher,
		)
		await connector.fetch(datetime(2026, 1, 1, tzinfo=UTC))
		gaps = fetcher.limiter.intervals()
		interval = fetcher.limiter.min_interval
		print('GAPS', len(fetcher.limiter.history), min(gaps) if gaps else -1.0, interval)

	asyncio.run(main())
	"""
)


def _rate_probe() -> tuple[int, float, float]:
	completed = subprocess.run(
		[sys.executable, "-c", _RATE_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("GAPS ")]
	assert marked, f"the rate probe printed nothing:\n{completed.stdout}"
	_, count, smallest, interval = marked[-1].split()
	return int(count), float(smallest), float(interval)


def test_the_rate_limit_gate_notices_a_bypassed_limiter():
	"""Remove the limiter call and watch the smallest gap collapse below the interval.

	The mutation moves the single ``await self.limiter.acquire()`` in ``get`` to
	a comment, so the connector makes three requests with no spacing. The gate
	asserts ``min(gaps) >= min_interval``; with the call gone, the gaps are the
	wall-clock cost of three in-process round trips, which is below the 20 ms
	interval the 50/s rate declares.
	"""
	count, smallest, interval = _rate_probe()
	assert count == 3, f"the probe fetched {count} documents, not three"
	assert smallest >= interval, (
		f"the limiter was already bypassed before any mutation: smallest gap "
		f"{smallest:.6f}s < interval {interval:.6f}s"
	)

	target = "\t\t\t\tawait self.limiter.acquire()"
	with planted(BASE_PY, target, "\t\t\t\tpass  # limiter removed by canary"):
		_, smallest_after, interval_after = _rate_probe()
		assert interval_after == interval, "the declared interval changed with the mutation"
		assert smallest_after < interval_after, (
			f"with the limiter call removed the smallest gap stayed at "
			f"{smallest_after:.6f}s; the gate does not measure the limiter"
		)

	# Restored: the smallest gap is above the interval again.
	_, smallest_restored, interval_restored = _rate_probe()
	assert smallest_restored >= interval_restored


# --------------------------------------------------------------------------
# Gate: test_scraper_layout_canary
# --------------------------------------------------------------------------

_LAYOUT_PROBE = textwrap.dedent(
	"""
	import asyncio, httpx
	from datetime import UTC, datetime
	from alea.scanning.connectors import HttpFetcher, TenderScraper
	from alea.scanning.connectors.tender import SelectorSpec

	PAGE = '<html><body><p>Maintenance in progress</p></body></html>'

	def handler(request):
		return httpx.Response(200, text=PAGE, headers={'content-type': 'text/html'})

	async def main():
		fetcher = HttpFetcher(0.2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), respect_robots=False)
		connector = TenderScraper(
			name='egp', listing_url='https://egp.example/list',
			spec=SelectorSpec(item='li.row', title='a', link='a'), fetcher=fetcher,
		)
		docs = await connector.fetch(datetime(2026, 1, 1, tzinfo=UTC))
		print('HEALTH', len(docs), connector.health_check().status)

	asyncio.run(main())
	"""
)


def _layout_probe() -> tuple[int, str]:
	completed = subprocess.run(
		[sys.executable, "-c", _LAYOUT_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("HEALTH ")]
	assert marked, f"the layout probe printed nothing:\n{completed.stdout}"
	_, count, status = marked[-1].split()
	return int(count), status


def test_the_layout_gate_notices_a_page_with_content_and_no_matches():
	"""Collapse ``layout_changed`` into ``no_new`` and watch the gate catch it.

	The mutation makes the zero-match branch report ``no_new`` — a page that
	returned content but matched nothing is then indistinguishable from a feed
	that had no new items, which is precisely the failure the gate exists to
	prevent. The canary is the report's own status string, so it proves the gate
	reads the field the defect corrupts.
	"""
	count, status = _layout_probe()
	assert (count, status) == (0, "layout_changed"), (
		f"the layout branch was already wrong before any mutation: {count} docs, "
		f"status {status!r}"
	)

	target = '\t\t\t\tstatus="layout_changed",\n\t\t\t\tdetail="listing page returned content but no selector matched",'
	replacement = '\t\t\t\tstatus="no_new",\n\t\t\t\tdetail="listing page returned content but no selector matched",'
	with planted(TENDER_PY, target, replacement):
		_, status_after = _layout_probe()
		assert status_after == "no_new", (
			f"with the branch flipped the status was {status_after!r}; the gate does "
			f"not read the field the defect corrupts"
		)

	# Restored.
	_, status_restored = _layout_probe()
	assert status_restored == "layout_changed"
