# SPDX-License-Identifier: MIT
"""Canary: `10-layer7-scanning.md` §3.2 -- a declared ``max_pages`` is walked.

This is the canary for ``test_max_pages_walks_every_page_it_promises``. The
defect it plants is the one that was live in the tree: ``max_pages`` is accepted
by ``TenderScraper.__init__`` and never read, so ``fetch`` issues exactly one
GET and returns one page's documents.

That defect is invisible from the returned value. The documents are real, the
status is ``ok``, and the health record counts them honestly -- a caller who
asked for ten pages receives the first and no signal that the other nine were
never requested. So the gate asserts the *requests*, and the canary mutates the
line that builds the URL.

The second assertion is the half that matters. A single-page crawl is
byte-identical under this mutation, because with ``max_pages=1`` the loop runs
once and the two spellings of the URL agree. A canary that only watched the
multi-page gate fail would not distinguish "the gate measures pagination" from
"the gate happens to fail for another reason"; asserting that the single-page
gate stays green pins the failure to the property being mutated.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

TENDER = REPO / "src" / "alea" / "scanning" / "connectors" / "tender.py"
GATE = "tests/ci/test_scanning_gates.py"

PAGED = "test_max_pages_walks_every_page_it_promises"
SINGLE = "test_single_page_behaviour_is_unchanged_by_the_pagination_declaration"

# The URL each page of the crawl is fetched from. Replacing it with the bare
# listing URL is the smallest defect that makes ``max_pages`` a no-op: every
# iteration re-reads page 1.
TARGET = "\t\t\turl = self._page_url(page)\n"
BLIND = "\t\t\turl = self._listing_url\n"


def _gate_exit_code(node: str) -> int:
	"""Run one gate in a fresh interpreter and return its exit code.

	A fresh process, not an in-process call: the mutation is to a source file
	whose module the canary has already imported, so only a new interpreter
	reads the planted defect rather than a cached one.
	"""
	result = subprocess.run(
		[sys.executable, "-m", "pytest", "-q", f"{GATE}::{node}"],
		cwd=REPO,
		capture_output=True,
		text=True,
		check=False,
	)
	return result.returncode


def test_the_pagination_gate_notices_a_crawl_that_rereads_its_first_page():
	"""Plant a URL that ignores the page index; the paged gate must notice."""
	assert _gate_exit_code(PAGED) == 0, (
		"the pagination gate is already failing on a clean tree; this canary "
		"could not attribute the failure it is about to cause"
	)
	assert _gate_exit_code(SINGLE) == 0, (
		"the single-page gate is already failing; the second half of this canary "
		"would be unreadable"
	)

	with planted(TENDER, TARGET, BLIND):
		assert _gate_exit_code(PAGED) != 0, (
			"the pagination gate passed with every page fetched from the listing "
			"URL; it does not measure which pages the crawl requested"
		)
		assert _gate_exit_code(SINGLE) == 0, (
			"the single-page gate failed too, so this mutation is not the defect "
			"described: a one-page crawl is identical either way, which is why a "
			"gate over the default path alone is the gate that checks nothing"
		)

	# Restored by `planted`, and the gate must clear -- otherwise the canary
	# proves a gate can fail but not that it recovers.
	assert _gate_exit_code(PAGED) == 0, "the pagination gate did not recover after the restore"
