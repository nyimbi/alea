# SPDX-License-Identifier: MIT
"""Content-addressed cache for re-solve results.

WHY this module exists at all, given Python ships a ``hash()``: because
``hash()`` of a string is randomised per interpreter (``PYTHONHASHSEED``). The
specification's cache key is ``hash(tuple(sorted(params.__dict__.items())))``,
which differs between processes, so the cache never hits across a restart and
every re-solve is a full solve. Worse, the defect is invisible: the
reproducibility test the specification pairs with it clears the cache and
compares two *fresh* solves, so it passes without ever exercising the cache.

The key here is a sha256 of the canonical parameter serialisation, which is a
function of the values alone. It covers three things, and each is necessary:

* the parameters — omit them and the cache returns the wrong scenario;
* the network checksum — omit it and the cache returns a result computed
  against a different network, which is the failure that makes a scenario
  engine untrustworthy because the number looks right;
* the code version — omit it and a fix ships while the cache keeps serving the
  old, wrong result.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from alea.io.artefacts import sha256_bytes, utcnow
from alea.whatif.params import ScenarioParameters

CACHE_VERSION = "1"
"""Bump when the cache entry layout changes, so old entries stop being read."""


def cache_key(
	params: ScenarioParameters,
	network_checksum: str,
	code_version: str,
) -> str:
	"""The content-addressed key for one solve.

	Deterministic across processes and machines: it is a sha256 over a sorted,
	compact JSON document, with no ``hash()`` and no dependence on iteration
	order. The plan's ``test_cache_key_stable_across_processes`` gate exists
	precisely because the obvious implementation is not.
	"""
	assert isinstance(params, ScenarioParameters)
	assert network_checksum, "a solve keyed without its network checksum is not reproducible"
	assert code_version, "a solve keyed without its code version is not reproducible"

	payload = json.dumps(
		{
			"cache_version": CACHE_VERSION,
			"params": params.canonical(),
			"network": network_checksum,
			"code": code_version,
		},
		sort_keys=True,
		separators=(",", ":"),
		default=str,
	)
	return sha256_bytes(payload.encode("utf-8"))


class SolveCache:
	"""A directory of content-addressed solve results.

	Entries are keyed by :func:`cache_key`. There is no invalidation: a changed
	network or a changed parameter produces a *new* key, so an old entry is
	simply unreachable rather than wrong. Eviction is explicit
	(:meth:`garbage_collect`) and never happens during a run, because evicting
	mid-sweep changes which scenarios are computed and therefore the frontier.
	"""

	def __init__(self, root: str | Path) -> None:
		self._root = Path(root)

	@property
	def root(self) -> Path:
		return self._root

	def path_for(self, key: str) -> Path:
		"""Where the entry for ``key`` lives. Sharded by prefix to keep
		directory listings small when a sweep writes thousands of entries."""
		assert len(key) == 64, f"a cache key is a sha256 hex digest, got {key!r}"
		return self._root / key[:2] / key

	def has(self, key: str) -> bool:
		"""Whether a complete entry for ``key`` exists.

		A directory without its ``result.json`` is a torn write from a killed
		worker and counts as a miss, not a hit.
		"""
		return (self.path_for(key) / "result.json").exists()

	def get(self, key: str) -> dict[str, Any] | None:
		"""The cached payload for ``key``, or ``None`` on a miss."""
		entry = self.path_for(key) / "result.json"
		if not entry.exists():
			return None
		payload = json.loads(entry.read_text(encoding="utf-8"))
		if payload.get("cache_version") != CACHE_VERSION:
			# Written by a different layout. Treat as a miss rather than
			# guessing at the shape.
			return None
		return payload

	def put(
		self,
		key: str,
		*,
		params: ScenarioParameters,
		network_checksum: str,
		code_version: str,
		result: dict[str, Any],
		extra: dict[str, Any] | None = None,
	) -> Path:
		"""Write one entry.

		The write is atomic: a worker killed mid-write leaves no ``result.json``,
		so the entry reads as a miss and the next run recomputes it. Writing in
		place would leave a truncated file that parses as a valid entry with
		missing fields.
		"""
		assert key == cache_key(params, network_checksum, code_version), (
			"the key does not match the payload it is filed under"
		)
		directory = self.path_for(key)
		directory.mkdir(parents=True, exist_ok=True)

		payload: dict[str, Any] = {
			"cache_version": CACHE_VERSION,
			"key": key,
			"params": params.canonical(),
			"network_checksum": network_checksum,
			"code_version": code_version,
			"result": result,
			"written_at": utcnow().isoformat(),
		}
		if extra:
			payload.update(extra)

		temporary = directory / "result.json.tmp"
		temporary.write_text(
			json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
		)
		temporary.replace(directory / "result.json")
		return directory

	def keys(self) -> list[str]:
		"""Every complete key held, sorted. Sorted because a cache listing that
		depends on filesystem enumeration order is not reproducible (AD-8)."""
		if not self._root.is_dir():
			return []
		return sorted(
			entry.name
			for shard in self._root.iterdir()
			if shard.is_dir()
			for entry in shard.iterdir()
			if (entry / "result.json").exists()
		)

	def garbage_collect(self, *, keep_days: float | None = None, dry_run: bool = False) -> list[str]:
		"""Remove entries older than ``keep_days``. Returns the keys removed.

		Explicit and CLI-driven (``alea whatif gc``). Never called from a solve
		or a sweep: eviction during a sweep would change which scenarios are
		computed and therefore the frontier, which is a reproducibility failure
		wearing a housekeeping costume.
		"""
		assert keep_days is None or keep_days >= 0, keep_days
		if keep_days is None:
			return []

		cutoff = utcnow().timestamp() - keep_days * 86400.0
		removed: list[str] = []
		for key in self.keys():
			directory = self.path_for(key)
			if directory.stat().st_mtime >= cutoff:
				continue
			removed.append(key)
			if dry_run:
				continue
			for child in directory.iterdir():
				child.unlink()
			directory.rmdir()
		return sorted(removed)


def solve_fingerprint(params: ScenarioParameters, network_checksum: str, code_version: str) -> str:
	"""A short human-facing label for a solve. Not a key; for logs and tables."""
	return cache_key(params, network_checksum, code_version)[:12]


def key_is_process_stable(
	params: ScenarioParameters,
	network_checksum: str,
	code_version: str,
	*,
	python: str | None = None,
	hash_seeds: tuple[str, ...] = ("1", "4242"),
) -> bool:
	"""Whether the key for these inputs is identical in fresh interpreters.

	WHY this ships in the package rather than living only in a test: the defect
	it detects is *invisible in-process*. A test that computes the key twice in
	one interpreter passes against the broken ``hash()`` key, so the check has
	no value unless it crosses a process boundary — and a check that must be
	written a particular way is one that will be written the easy way and pass
	for the wrong reason. Each interpreter is given a different
	``PYTHONHASHSEED``, which is what makes the string-hash defect reproduce.

	Returns ``True`` when every interpreter agrees. The plan's
	``test_cache_key_stable_across_processes`` asserts this; its canary reverts
	:func:`cache_key` to ``hash(tuple(sorted(...)))`` and this returns ``False``.
	"""
	import subprocess
	import sys

	executable = python or sys.executable
	script = (
		"import json, sys;"
		"from alea.whatif.cache import cache_key;"
		"from alea.whatif.params import ScenarioParameters;"
		"print(cache_key(ScenarioParameters.model_validate(json.loads(sys.argv[1])),"
		" sys.argv[2], sys.argv[3]))"
	)
	expected = cache_key(params, network_checksum, code_version)
	payload = json.dumps(params.canonical(), sort_keys=True)

	for seed in hash_seeds:
		result = subprocess.run(
			[executable, "-c", script, payload, network_checksum, code_version],
			capture_output=True,
			text=True,
			env={**os.environ, "PYTHONHASHSEED": seed},
			check=False,
		)
		if result.returncode != 0:
			raise RuntimeError(
				f"the key probe failed under PYTHONHASHSEED={seed}: {result.stderr.strip()}"
			)
		if result.stdout.strip() != expected:
			return False
	return True


__all__ = [
	"CACHE_VERSION",
	"SolveCache",
	"cache_key",
	"key_is_process_stable",
	"solve_fingerprint",
]
