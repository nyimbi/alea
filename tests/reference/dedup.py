# SPDX-License-Identifier: MIT
"""Reference implementation of the MinHash / LSH kernels.

Written from `alea._core.kernels` and `docs/plans/03-rust-core.md` §4. This is a
reimplementation of the datasketch algorithm, not a call to datasketch (plan
§4.3), and not a transcription of the Rust.

Pinned semantics encoded here, and why:

* **Shingles are `k` consecutive words, lowercased, over whitespace-split
  tokens, as a set.** Repeated shingles do not count twice, so `"a a a"` at
  `k=1` has the same signature as `"a"`.
* **An empty shingle set gives every position `u64::MAX`.** Two empty documents
  then collide (estimate 1.0), which is why the kernel groups them.
* **`jaccard_estimate` is the fraction of positions where the two signatures
  agree**, and NaN when the lengths differ. This is a property of the
  signatures passed in, so it is comparable against the kernel on the
  reference's own signatures.
* **`deduplicate` groups connected components** under `estimate >= threshold`,
  with the first id in input order as each group's representative.
* **`optimal_bands_rows` maximises the S-curve's separation**, not its midpoint.
  The rule is stated in the kernel's own comment: score each `bands * rows ==
  num_perm` split by `P(threshold) - P(threshold/2)`, where
  `P(s) = 1 - (1 - s^rows)^bands` is the probability a pair at similarity `s`
  shares a band, and take the maximum. Ties go to the first maximum found, which
  is the **smallest band count** — the loop runs upward and only a strict `>`
  displaces the incumbent.

  This is not the textbook rule, and the difference is worth stating because the
  two disagree on 34 of 45 sampled `(threshold, num_perm)` pairs. The usual
  MMDS criterion picks the split whose S-curve crosses 0.5 nearest the
  threshold; this kernel picks the one with the steepest step at it. Both are
  defensible and they are not the same function, so the reference implements the
  one the kernel implements rather than the one a reader would assume. A
  reference written from the textbook would fail the differential test on the
  majority of inputs and the failure would look like a kernel bug.

The hash family here is deliberately simple and documented: a 64-bit FNV-1a of
the shingle, permuted per position by a splitmix64 of `base + i*GOLDEN + seed`.
The kernel uses its own family, so the two signatures are **not** expected to
be equal position-for-position — only to satisfy the same properties. Tests
that compare against the kernel use documents that are either identical or
clearly unrelated, so both hash families agree on the grouping.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

_MASK64 = (1 << 64) - 1
_U64_MAX = _MASK64
_GOLDEN = 0x9E3779B97F4A7C15


def _splitmix64(x: int) -> int:
	"""The splitmix64 finalizer, over unsigned 64-bit integers."""
	x &= _MASK64
	x = (x + _GOLDEN) & _MASK64
	z = x
	z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
	z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
	return z ^ (z >> 31)


def _fnv1a64(data: bytes) -> int:
	"""64-bit FNV-1a of a byte string. Stable across processes and versions."""
	h = 0xCBF29CE484222325
	for byte in data:
		h ^= byte
		h = (h * 0x100000001B3) & _MASK64
	return h


def _shingles(text: str, k: int) -> set[str]:
	"""The set of `k`-word shingles, lowercased, whitespace-split."""
	tokens = text.lower().split()
	if k <= 0 or len(tokens) < k:
		return set()
	return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def minhash(text: str, k: int = 5, num_perm: int = 128, seed: int = 0) -> NDArray[np.uint64]:
	"""MinHash signature of a document.

	Returns `num_perm` unsigned 64-bit hashes; `u64::MAX` everywhere when the
	document has no shingle.
	"""
	shingle_set = _shingles(text, k)
	if not shingle_set:
		return np.full(num_perm, _U64_MAX, dtype=np.uint64)
	# Base hash per shingle, computed once.
	base_hashes = [_fnv1a64(s.encode("utf-8")) for s in shingle_set]
	signature = np.empty(num_perm, dtype=np.uint64)
	for i in range(num_perm):
		offset = (i * _GOLDEN + seed) & _MASK64
		best = _U64_MAX
		for base in base_hashes:
			value = _splitmix64(base + offset)
			if value < best:
				best = value
		signature[i] = best
	return signature


def jaccard_estimate(a: NDArray[np.uint64], b: NDArray[np.uint64]) -> float:
	"""The Jaccard similarity two signatures estimate, or NaN if lengths differ."""
	a = np.asarray(a)
	b = np.asarray(b)
	if a.shape[0] != b.shape[0]:
		return float("nan")
	if a.shape[0] == 0:
		return float("nan")
	agree = 0
	for i in range(a.shape[0]):
		if a[i] == b[i]:
			agree += 1
	return agree / a.shape[0]


def deduplicate(
	documents: list[tuple[str, str]],
	k: int = 5,
	num_perm: int = 128,
	threshold: float = 0.7,
	seed: int = 0,
) -> list[list[str]]:
	"""Group near-duplicate documents.

	Groups are the connected components of the graph whose edges join documents
	with `jaccard_estimate >= threshold`. The first id in each group, in input
	order, is the representative.
	"""
	signatures = [minhash(text, k, num_perm, seed) for _, text in documents]
	ids = [doc_id for doc_id, _ in documents]
	n = len(ids)

	parent = list(range(n))

	def find(x: int) -> int:
		while parent[x] != x:
			parent[x] = parent[parent[x]]
			x = parent[x]
		return x

	def union(x: int, y: int) -> None:
		rx, ry = find(x), find(y)
		if rx != ry:
			parent[ry] = rx

	for i in range(n):
		for j in range(i + 1, n):
			estimate = jaccard_estimate(signatures[i], signatures[j])
			if not np.isnan(estimate) and estimate >= threshold:
				union(i, j)

	groups: dict[int, list[str]] = {}
	order: list[int] = []
	for i in range(n):
		root = find(i)
		if root not in groups:
			groups[root] = []
			order.append(root)
		groups[root].append(ids[i])
	return [groups[root] for root in order]


def optimal_bands_rows(threshold: float, num_perm: int) -> tuple[int, int]:
	"""Band and row counts maximising the S-curve's step at `threshold`.

	Every split with `bands * rows == num_perm` is scored by
	`P(threshold) - P(threshold/2)` and the maximum wins; the search runs upward
	from `bands = 1` and displaces only on a strict improvement, so a tie leaves
	the smaller band count in place.

	`(1, num_perm)` is the starting incumbent rather than an initialised
	`-inf`, which matters when `num_perm` is prime: the only split is
	`(1, num_perm)` and it must be returned even though its score may be
	negative.
	"""
	if threshold <= 0.0 or threshold >= 1.0:
		raise ValueError("threshold must be in (0, 1)")
	if num_perm == 0:
		raise ValueError("num_perm must be positive")

	def collide(similarity: float, bands: int, rows: int) -> float:
		"""Probability a pair at `similarity` shares at least one band."""
		return 1.0 - (1.0 - similarity**rows) ** bands

	best = (1, num_perm)
	best_score = float("-inf")
	for bands in range(1, num_perm + 1):
		if num_perm % bands:
			continue
		rows = num_perm // bands
		score = collide(threshold, bands, rows) - collide(threshold * 0.5, bands, rows)
		if score > best_score:
			best_score = score
			best = (bands, rows)
	return best
