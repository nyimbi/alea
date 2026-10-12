# SPDX-License-Identifier: MIT
"""Canary: watch each `test_whatif_gc_cli.py` gate fail on the defect it catches.

Two gates, two defects, and they are the two ways this unit was wrong before it
was written.

* `test_the_cache_root_is_spelled_once` guards against the API re-spelling the
  solve-cache path. The original code built it as `f"{WHATIF_DIR}/solves"`, a
  literal that agreed with the constant the command needs -- so a gc pointed at
  the engine's directory and a gc pointed at nothing were the same command on
  the day it was written and different commands after the next edit. The canary
  restores the f-string.

* `test_the_gc_without_a_window_removes_nothing` guards the no-argument form.
  `garbage_collect(keep_days=None)` returns nothing; reading the missing window
  as "older than now" erases the cache, and the bare `alea whatif gc` is the
  invocation someone types to see what the command does. The canary plants that
  reading as a window of zero days, which is the same defect with a readable
  cutoff -- dropping the guard outright makes `None * 86400.0` raise instead,
  and a crash is not the failure mode being guarded.

**Both run the gate in a fresh interpreter.** The mutations are source edits to
`api/whatif.py` and `whatif/cache.py`, and `test_whatif_gc_cli.py` binds
`DEFAULT_CACHE_ROOT` and `SolveCache` at import, so an in-process canary would
assert against the modules it already holds rather than the ones on disk.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

API_WHATIF_PY = REPO / "src" / "alea" / "api" / "whatif.py"
CACHE_PY = REPO / "src" / "alea" / "whatif" / "cache.py"

GATE_FILE = "tests/ci/test_whatif_gc_cli.py"
SPELLED_ONCE_GATE = "test_the_cache_root_is_spelled_once"
NO_WINDOW_GATE = "test_the_gc_without_a_window_removes_nothing"


def _gate_exit_code(test: str) -> int:
	"""Exit code of one gate in the module, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_spelled_once_gate_catches_the_api_building_the_path():
	"""The defect: the API spells the cache root instead of importing it.

	Restoring `f"{WHATIF_DIR}/solves"` must fail the gate. If it does not, the
	gate cannot tell a command that reads the engine's constant from one that
	reads a string that happens to match it today -- which is the whole failure
	`DEFAULT_CACHE_ROOT` was introduced to prevent.
	"""
	target = "\t\tcache_root=resolve(DEFAULT_CACHE_ROOT),\n"
	replacement = '\t\tcache_root=resolve(f"{WHATIF_DIR}/solves"),\n'
	assert target in API_WHATIF_PY.read_text(), (
		"the canary target moved; the engine's cache root is no longer built where "
		"this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(SPELLED_ONCE_GATE) == 0, "the gate does not pass on the shipped tree"

	with planted(API_WHATIF_PY, target, replacement):
		assert _gate_exit_code(SPELLED_ONCE_GATE) != 0, (
			"the gate passed with the API building the solve-cache path from an "
			"f-string; it cannot tell an import of the shared constant from a "
			"second spelling of the same path"
		)

	assert _gate_exit_code(SPELLED_ONCE_GATE) == 0, "the restore was not proven"


def test_the_no_window_gate_catches_a_missing_window_read_as_now():
	"""The defect: `keep_days=None` treated as a window rather than as a guard.

	The planted form makes an absent window mean zero days, so every entry is
	past the cutoff and the bare command erases the cache. That is the failure
	the guard prevents, reproduced without the `TypeError` a deleted guard would
	raise -- a crash would fail the gate for a reason the gate is not about.
	"""
	# Two tabs: the guard is the first statement of a method body.
	target = "\t\tif keep_days is None:\n\t\t\treturn []\n"
	replacement = "\t\tkeep_days = 0.0 if keep_days is None else keep_days\n"
	assert target in CACHE_PY.read_text(), (
		"the canary target moved; `garbage_collect`'s no-window guard is no longer "
		"where this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(NO_WINDOW_GATE) == 0, "the gate does not pass on the shipped tree"

	with planted(CACHE_PY, target, replacement):
		assert _gate_exit_code(NO_WINDOW_GATE) != 0, (
			"the gate passed with an absent window read as a zero-day window, so the "
			"bare `alea whatif gc` erased the cache; the gate cannot tell a guard "
			"from a default"
		)

	assert _gate_exit_code(NO_WINDOW_GATE) == 0, "the restore was not proven"
