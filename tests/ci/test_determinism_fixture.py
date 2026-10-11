# SPDX-License-Identifier: MIT
"""The determinism fixture must exercise the paths its docstring claims.

`tests/determinism/run.py` shipped for a while claiming to cover "a content
hash, a seeded MinHash, and a market-clearing tie-break" while its `build()`
called none of the last two. Rust core exit-criterion 8 and Layer 7 criterion 3
("dedup deterministic across processes") rested on that claim, and a docstring
is not a gate: nothing failed when the coverage was absent, so nothing stopped
it from staying absent.

These tests read the summary `build()` returns and assert the dedup and market
digests are in it. They are the gate on the gate -- a future edit that drops
either path from `build()` fails here rather than silently narrowing what the
two-process diff watches.

They call `build()` once and assert on its return value, not on the written
files: `scripts/determinism.py` already owns the byte-level cross-process diff,
and duplicating it here would be a second definition of the same check.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from alea._core.kernels import minhash
from tests.determinism import run as det


def _summary(tmp_path: Path) -> dict:
	return det.build(tmp_path / "fixture")


def test_the_summary_carries_a_dedup_digest(tmp_path: Path) -> None:
	"""The MinHash/dedup path is in the summary, and the digest is real."""
	summary = _summary(tmp_path)
	assert "dedup" in summary, (
		"build() no longer writes a dedup section; the harness's docstring claims "
		"to cover a seeded MinHash and no longer does"
	)
	dedup = summary["dedup"]
	digest = dedup["minhash_digest"]
	assert isinstance(digest, str) and len(digest) == 32, (
		f"the minhash digest is not a 32-hex-char content hash: {digest!r}"
	)
	# Recompute the digest from the kept texts, independently of `build()`'s own
	# call, so a placeholder string cannot satisfy this test.
	expected = hashlib.sha256(
		b"".join(minhash(text, seed=0).tobytes() for text in _kept_texts())
	).hexdigest()[:32]
	assert digest == expected, "the digest is not the sha256 of the kept MinHash signatures"


def test_the_dedup_path_actually_groups(tmp_path: Path) -> None:
	"""The corpus produces a near-duplicate group, not a trivial pass-through.

	A fixture that fed the kernel one document per group would exercise the
	code path while asserting nothing about grouping; the counts are asserted
	so a corpus edit that stops producing duplicates is caught.
	"""
	dedup = _summary(tmp_path)["dedup"]
	assert dedup["near_duplicates"] >= 1, (
		"the fixed corpus produced no near-duplicate group, so the MinHash path "
		"ran but grouped nothing"
	)
	assert dedup["kept_ids"] == sorted(dedup["kept_ids"]), (
		"kept_ids is not sorted; the dedup stage's deterministic output order regressed"
	)


def test_the_summary_carries_a_market_clearing_result(tmp_path: Path) -> None:
	"""The market-clearing path is in the summary, with the tie-break applied."""
	summary = _summary(tmp_path)
	assert "clearing" in summary, (
		"build() no longer writes a clearing section; the harness's docstring "
		"claims to cover a market-clearing tie-break and no longer does"
	)
	clearing = summary["clearing"]
	assert "clearing_price_usd_per_mwh" in clearing and "dispatched" in clearing
	dispatched = clearing["dispatched"]
	# The two tied units are U-ALPHA and U-BETA at the same price; the fixture
	# lists BETA first and demand splits across them. `merit_order_stack` breaks
	# the tie on `unit_id`, so ALPHA takes the larger share. If the tie broke on
	# list order instead, BETA would take it and this flips.
	assert dispatched["U-ALPHA"] > dispatched["U-BETA"], (
		f"the price tie was not broken on unit_id: dispatch is {dispatched}"
	)


def _kept_texts() -> list[str]:
	"""The texts `build()`'s dedup section hashes, recomputed from the corpus.

	`build()` digests the *kept* documents' texts. This reproduces that set
	independently: run the corpus through the same dedup and take the kept
	documents. If `build()` hashed something else -- the input corpus, say --
	the digests would differ and the first test would fail.
	"""
	kept, _report = det.deduplicate_documents(det._corpus())
	return [doc.text for doc in kept]
