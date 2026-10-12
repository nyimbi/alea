# SPDX-License-Identifier: MIT
"""The eviction path for the what-if solve cache, and the one path it reads.

`08-layer5-whatif.md` §2.4: the cache is content-addressed and therefore never
*invalidated*, so old entries leave only through an explicit
`alea whatif gc --keep-days N`, "never by age-based eviction during a run,
because eviction during a sweep changes which scenarios are computed and
therefore the frontier".

Two things are asserted here, and they fail for different reasons.

**The command exists and evicts what it says.** `SolveCache.garbage_collect`
was written and documented as CLI-driven, the plan names the command, and the
CLI had no `whatif` group: the method was reachable only by importing it, which
AD-5 forbids the workflow layer from doing and which no operator does by hand.
A cache with no eviction path grows without bound, so the rule that eviction
must not happen during a run is only enforceable while there is somewhere else
for it to happen.

**`--keep-days` omitted removes nothing.** That guard is the reason the
no-argument form is safe to run: a missing window read as "older than now" is
"remove everything", and a maintenance command whose bare invocation is the
destructive one is a command someone runs by accident. It is asserted through
the CLI rather than against the method, because the method's guard and the
command's default are two different lines.

**The command reads where the engine writes.** `alea.api.whatif` built its
engine's cache root from `f"{WHATIF_DIR}/solves"` while the CLI needed a literal
of its own -- two spellings of one path, which agree until one is edited. The
failure that produces is quiet in the worst direction: a gc pointed at a
directory nothing writes removes nothing, prints ``removed 0``, and reads as a
cache that was already clean. `DEFAULT_CACHE_ROOT` is the single spelling, and
`test_the_cli_reads_the_root_the_engine_writes` proves the two ends meet by
putting an entry through the constant and watching the command count it.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from alea.whatif.cache import DEFAULT_CACHE_ROOT, SolveCache, cache_key
from alea.whatif.params import ScenarioParameters

NETWORK = "sha256:" + "ab" * 32
CODE = "0.1.0"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
	"""A scratch repository root, so the command's default cache root is here.

	`whatif_gc` resolves its default through `config.paths.resolve`, which asks
	`repo_root()`. Without the redirect the command would collect from the real
	`results/whatif/solves` -- the tree this session is working in. `repo_root`
	is `lru_cache`d and the cache is cleared on both sides, or a later test in
	the same interpreter inherits this root.
	"""
	from alea.config.paths import repo_root

	(tmp_path / "pyproject.toml").write_text("[project]\nname='scratch'\n", encoding="utf-8")
	monkeypatch.setenv("ALEA_ROOT", str(tmp_path))
	repo_root.cache_clear()
	yield tmp_path
	repo_root.cache_clear()


def _entry(cache: SolveCache, *, age_days: float, tag: str = "ab") -> str:
	"""Put one complete entry and back-date it, returning its key.

	`garbage_collect` reads the *entry directory's* mtime, not `result.json`'s,
	so that is what is set. `put` writes through a temp file and renames, which
	touches the directory; the utime has to come after, or the write's own
	timestamp is what the collection sees.
	"""
	params = ScenarioParameters(carbon_price_usd_per_tco2=float(len(tag)))
	key = cache_key(params, "sha256:" + tag * 32, CODE)
	cache.put(key, params=params, network_checksum="sha256:" + tag * 32, code_version=CODE, result={})
	stamp = time.time() - age_days * 86400.0
	os.utime(cache.path_for(key), (stamp, stamp))
	return key


def _gc(*args: str):
	from typer.testing import CliRunner

	from alea.cli import app

	return CliRunner().invoke(app, ["whatif", "gc", *args])


def test_the_gc_command_is_reachable() -> None:
	"""The CLI exposes `whatif gc`, which it did not before.

	Asserted through the runner rather than by importing `whatif_gc`, because the
	defect was registration and not the function body: a command defined but
	never added to a mounted typer is unreachable from the shell, which is the
	only entry point a rule may use (AD-5).
	"""
	result = _gc("--help")
	assert result.exit_code == 0, result.output
	assert "--keep-days" in result.stdout
	assert "--dry-run" in result.stdout


def test_the_cli_reads_the_root_the_engine_writes(root: Path) -> None:
	"""The command and the engine resolve one path, spelled once.

	The entry is filed through `DEFAULT_CACHE_ROOT` -- the constant the API's
	engine builder passes to `WhatIfEngine` -- and the command is run with no
	`--cache-root`, so it resolves the same constant. The count it prints is the
	evidence the two ends meet: `removed 0 of 1` says it found the entry the
	engine wrote, and `of 0` says it is looking somewhere else.
	"""
	cache = SolveCache(root / DEFAULT_CACHE_ROOT)
	_entry(cache, age_days=0.0)

	result = _gc()
	assert result.exit_code == 0, result.output
	assert f"of 1 entries under {cache.root}" in result.stdout, (
		"the command did not see the entry the engine's cache root holds: "
		f"{result.stdout.strip()}"
	)


def _path_literals(source: str) -> list[str]:
	"""Every string constant in the module that names the cache's ``solves`` segment.

	Read from the AST rather than grepped: the module's prose discusses solves
	constantly -- "every solve calls Layer 1's expansion", "the engine solves or
	raises" -- and a substring check over the whole file matches those and fails
	on a tree that is correct. What is being asserted is that no *string* the
	code can pass to `resolve` carries the path.
	"""
	import ast

	found = []
	for node in ast.walk(ast.parse(source)):
		if isinstance(node, ast.Constant) and isinstance(node.value, str):
			segments = node.value.replace("\\", "/").split("/")
			if "solves" in segments:
				found.append(node.value)
	return found


def test_the_cache_root_is_spelled_once() -> None:
	"""`alea.api.whatif` imports the constant instead of building the path.

	Two spellings that agree today are two things that can disagree, and the
	disagreement is silent: the gc reports an empty cache. So the API module must
	not carry the path itself -- not as a literal, not as an f-string over
	`WHATIF_DIR`. The second assertion pins that the constant still denotes the
	path `WHATIF_DIR` implies, so the import is a consolidation and not a
	re-pointing of the engine at a directory nothing collects.
	"""
	from alea.api import whatif as api_whatif

	source = Path(api_whatif.__file__).read_text(encoding="utf-8")
	assert "DEFAULT_CACHE_ROOT" in source, "the API builds its cache root without the constant"
	assert not _path_literals(source), (
		"alea/api/whatif.py spells the solve-cache path itself, so the constant is "
		"not the single spelling `alea whatif gc` reads; the constant exists so the "
		f"two cannot drift apart: {_path_literals(source)}"
	)
	assert f"{api_whatif.WHATIF_DIR}/solves" == DEFAULT_CACHE_ROOT, (
		f"DEFAULT_CACHE_ROOT={DEFAULT_CACHE_ROOT!r} no longer matches WHATIF_DIR="
		f"{api_whatif.WHATIF_DIR!r}; the command now collects somewhere the engine "
		"does not write"
	)


def test_the_gc_removes_only_entries_past_the_window(root: Path) -> None:
	"""A stale entry goes, a fresh one stays.

	The positive half of the gate. Without it the guard test below passes for a
	command that removes nothing ever -- which is what a `garbage_collect` whose
	cutoff is inverted would do, and it would read as a clean cache.
	"""
	cache = SolveCache(root / DEFAULT_CACHE_ROOT)
	stale = _entry(cache, age_days=3.0, tag="ab")
	fresh = _entry(cache, age_days=0.0, tag="cd")

	result = _gc("--keep-days", "1")
	assert result.exit_code == 0, result.output
	assert "removed 1 of 2" in result.stdout, result.stdout
	assert stale[:12] in result.stdout, "the command did not name the entry it removed"
	assert not cache.has(stale), "the stale entry survived a window it is past"
	assert cache.has(fresh), "the command removed an entry inside the window"


def test_the_gc_without_a_window_removes_nothing(root: Path) -> None:
	"""`--keep-days` omitted is a no-op, and the command says so.

	The guard. An omitted window that reads as "older than now" erases the whole
	cache, and the bare invocation is the one someone types to see what the
	command does. Asserted with two entries both well past any plausible window,
	so a default that is merely *short* still fails here.
	"""
	cache = SolveCache(root / DEFAULT_CACHE_ROOT)
	keys = [_entry(cache, age_days=400.0, tag="ab"), _entry(cache, age_days=900.0, tag="cd")]

	result = _gc()
	assert result.exit_code == 0, result.output
	assert "removed 0 of 2" in result.stdout, result.stdout
	assert "nothing was removed" in result.output, (
		"the command removed nothing without a window but did not say why; the "
		f"silence reads as a cache that was already clean: {result.output.strip()}"
	)
	assert all(cache.has(key) for key in keys), "an entry was removed with no window given"


def test_the_gc_dry_run_removes_nothing(root: Path) -> None:
	"""`--dry-run` reports the same set and removes none of it.

	The command is the only eviction path and it is irreversible, so the
	rehearsal has to be honest: it must name the entry it would remove, which is
	what distinguishes it from a run that found nothing.
	"""
	cache = SolveCache(root / DEFAULT_CACHE_ROOT)
	stale = _entry(cache, age_days=3.0)

	result = _gc("--keep-days", "1", "--dry-run")
	assert result.exit_code == 0, result.output
	assert "would remove 1 of 1" in result.stdout, result.stdout
	assert stale[:12] in result.stdout, "the dry run did not name what it would remove"
	assert cache.has(stale), "the dry run removed the entry it only reported"
