# SPDX-License-Identifier: MIT
"""Canaries. Every gate is watched failing on the defect it exists to catch.

A gate that has never been seen to fail is not evidence of anything: it may be
scoped to the wrong set, may parse the wrong spelling, or may never have run at
all. These tests plant each defect and assert the gate notices.

The discipline, which `planted` below enforces rather than documents:

1. Assert the target text exists before mutating. A patch that does not apply
   leaves the file untouched and the canary passes against working code -- a
   false alarm about a gate that was never pointed anywhere.
2. Restore from the bytes read under a per-file lock. **Never** `git checkout --
   <file>`: the canary's mutation and real uncommitted work live in the same
   file, so checkout discards both.
3. Purge the `.pyc` on both sides of the mutation. A same-length mutation
   restored within one mtime tick leaves a cache CPython still trusts, so the
   next interpreter runs the *defect* against a source that reads correctly.
4. Assert the gate fails while the defect is planted.
5. Assert it passes again once restored, or the restore is not proven.
6. Interrupt the body if it outlives `_HOLD_SECONDS`. Guards 1-5 all assume the
   body *returns*; a hang breaks that assumption and is the one failure that
   survives the process, because the mutation is still on disk when it dies.

All of the guards beyond the first are here because each was a live bug:
the leak of 2026-10-12, the stale-bytecode failure that made a clean tree
look broken, and the hang of 2026-10-13 that left two planted defects in the
tree for hours.
"""

from __future__ import annotations

import fcntl
import hashlib
import itertools
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

_COUNTER = itertools.count()

#: How long a canary may hold a mutation before the harness interrupts it.
#:
#: A canary that hangs is worse than a canary that fails, and the difference is
#: the *tree*. The mutation is on disk for the whole body, so a body that never
#: returns leaves the defect planted -- and the next process to read that file
#: takes the defect for the original and restores *to* it. The leak then
#: outlives the process that caused it, and every later canary fails for a
#: reason unrelated to any gate.
#:
#: Measured 2026-10-13: a probe subprocess deadlocked in `libarrow`'s
#: thread-pool destructor during interpreter exit, `subprocess.run` had no
#: timeout, and `assemble.py` and `integrate.py` were both found hours later
#: holding planted mutations -- `interval=None` where the band was read, and
#: `> 1e9` where a tolerance was. The second is worth reading twice: it blinds
#: the conflict detector, so the three tests that failed looked like another
#: workstream's bug rather than this harness's.
#:
#: Generous, because a legitimate body runs pytest in a subprocess. Override
#: with `ALEA_CANARY_TIMEOUT`; `0` disables the deadline.
_HOLD_SECONDS = float(os.environ.get("ALEA_CANARY_TIMEOUT", "300"))


class CanaryTimeout(TimeoutError):
	"""A canary body outlived its deadline and was interrupted.

	A distinct type rather than a bare `TimeoutError` so a test can tell the
	harness's own deadline from a timeout the body raised itself.
	"""


@contextmanager
def _hold_deadline(seconds: float, path: Path) -> Iterator[None]:
	"""Interrupt a canary body that holds ``path`` longer than ``seconds``.

	The interrupt is what makes the restore reachable. Without it a hung body
	never unwinds, so `planted`'s `finally` never runs and the mutation stays --
	and because `subprocess.run` kills its child on any exception, the hung probe
	is reaped on the way out rather than left behind.

	**Main thread only.** `signal.signal` refuses elsewhere, and
	`test_two_canaries_on_one_file_do_not_see_each_other` drives `planted` from
	worker threads deliberately. A worker that hangs does not corrupt anything
	on its own: the session is what is stuck, and that is already visible.
	"""
	if seconds <= 0 or threading.current_thread() is not threading.main_thread():
		yield
		return

	def fire(signum: int, frame: object) -> None:
		del signum, frame  # the handler ignores both; the deadline is the message
		raise CanaryTimeout(
			f"the canary body held a mutation on {path.name} for more than "
			f"{seconds:.0f}s and was interrupted; the restore still ran, so the "
			f"tree is clean and this is a failure rather than a leak"
		)

	previous = signal.signal(signal.SIGALRM, fire)
	# `setitimer` rather than `alarm`: sub-second deadlines are expressible, and
	# it is the same timer, so a nested `planted` cannot leave a stray one armed
	# past its block.
	signal.setitimer(signal.ITIMER_REAL, seconds)
	try:
		yield
	finally:
		signal.setitimer(signal.ITIMER_REAL, 0)
		signal.signal(signal.SIGALRM, previous)


#: Runs a probe's source and leaves through `os._exit`, skipping interpreter
#: shutdown.
#:
#: A probe ends by raising `SystemExit`, and `SystemExit` does not exit -- it
#: unwinds to the top and *then* the interpreter tears down: atexit hooks,
#: daemon threads joined, and `libarrow`'s thread-pool destructor, which
#: deadlocks on this platform. The probe's own output has already been written
#: by then, so the symptom is a `subprocess.TimeoutExpired` on a probe that
#: plainly succeeded, and the canary that owns it fails while every gate it
#: exercises is fine.
#:
#: Measured twice: 2026-10-13, where `subprocess.run` had no timeout and the
#: hang left two mutations on disk for hours (see `_HOLD_SECONDS`), and
#: 2026-10-14, where the timeout turned the same hang into a spurious failure of
#: `test_the_category_gate_notices_a_band_that_never_reaches_the_value` -- the
#: probe printed its expected `REFUSED ReportDataError` and then sat in
#: shutdown for 120s. The timeout is what made the second occurrence legible
#: rather than a leak; this wrapper is what stops it happening at all.
#:
#: `sys.argv` is deliberately **not** rewritten. Probe bodies are written
#: against the `python -c` layout (`sys.argv[1]` for the first extra argument,
#: `sys.argv[1:]` for the pytest pass-through), so shifting it by one would
#: silently retarget every argument-passing probe.
#:
#: Flushing before `os._exit` is not optional: `os._exit` does not flush stdio,
#: and the canaries assert on the probe's stdout.
_EXIT_WRAPPER = """\
import os, sys, traceback
_src = os.environ.pop("ALEA_CANARY_PROGRAM")
_code = 0
try:
    exec(compile(_src, "<canary>", "exec"), {"__name__": "__main__"})
except SystemExit as _exc:
    if _exc.code is None:
        _code = 0
    elif isinstance(_exc.code, int):
        _code = _exc.code
    else:
        print(_exc.code, file=sys.stderr)
        _code = 1
except BaseException:
    traceback.print_exc()
    _code = 1
sys.stdout.flush()
sys.stderr.flush()
os._exit(_code)
"""


def probe(program: str, *args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
	"""Run a snippet against the tree on disk, with the repo importable.

	The shared runner for canaries whose gate is a *code path* rather than a
	value shape: the mutation is a source edit, so the gate has to execute in a
	fresh interpreter that reads the mutated file. `tests` is not part of the
	installed package, hence the `PYTHONPATH`.

	The timeout is not optional and not decoration. A probe that never returns
	used to hang its canary forever with the defect still planted -- see
	`_HOLD_SECONDS` -- and a killed probe reports as a failure rather than as a
	hang, which is the difference between a five-second diagnosis and an hour.

	The program is passed through the environment rather than as the `-c`
	argument, because the argument slot is what `_EXIT_WRAPPER` occupies. The
	child's `sys.argv` is therefore identical to what `python -c program *args`
	would have produced, which is the layout the probe bodies assume.
	"""
	env = {**os.environ, "PYTHONPATH": str(REPO), "ALEA_CANARY_PROGRAM": program}
	return subprocess.run(
		[sys.executable, "-c", _EXIT_WRAPPER, *args],
		capture_output=True,
		text=True,
		check=False,
		env=env,
		cwd=str(REPO),
		timeout=timeout,
	)


def probe_exit_code(program: str, *args: str, timeout: float = 120.0) -> int:
	"""`probe`, reduced to the exit code a canary asserts on."""
	return probe(program, *args, timeout=timeout).returncode


def leaked_mutations(roots: Sequence[Path] | None = None) -> list[Path]:
	"""Backup files a previous canary run left behind, which mean a live defect.

	`planted` writes its backup beside the target and unlinks it in the same
	`finally` that restores, so a backup on disk is a canary that did not finish
	-- a killed process, or a hang from before `_HOLD_SECONDS` existed. The file
	beside it is *mutated*, and the next run would read that mutation as the
	original.

	Scoped to the trees canary targets live in rather than the whole repo: a
	recursive walk of `REPO` reaches `.venv` and the cutouts, and a check that
	costs a minute is a check people skip.
	"""
	scan = roots if roots is not None else (REPO / "src", REPO / "tests", REPO / "rules")
	found: list[Path] = []
	for root in scan:
		if root.is_dir():
			found.extend(sorted(root.rglob("*.canary-backup")))
	return found


def _lock_for(path: Path) -> Path:
	"""A per-target lock file in the temp directory.

	Keyed by the target's resolved path rather than placed beside it: a lock
	file inside the repo is one more untracked artefact for `git status` to
	explain, and `shutil.copy2`/`write_text` never touch it.
	"""
	digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
	return Path(tempfile.gettempdir()) / f"alea-canary-{digest}.lock"


def _invalidate_bytecode(path: Path) -> None:
	"""Drop the `.pyc` a mutation would leave trusted.

	CPython invalidates a cached `.pyc` on the source's (mtime, size). A canary
	whose mutation and restore are the **same length** and land in the **same
	mtime tick** therefore produces a `.pyc` that still matches after the restore
	-- and the next interpreter loads the *mutated* bytecode from a source file
	that reads correctly. `extra="forbid"` -> `extra="ignore"` is exactly that:
	six bytes to six bytes.

	It is invisible in the source and only shows up as a test that fails on a
	clean tree for no reason anyone can find by reading the file -- on
	2026-10-12 it made three `test_config_rejects_typo.py` tests fail while
	`models.py` plainly said `forbid`, and the module's own `model_config` said
	`ignore`.

	Both directions are purged: the mutation's `.pyc` before it is trusted, and
	the restore's, so the tree ends with the cache the source deserves.
	"""
	cache = path.parent / "__pycache__"
	if not cache.is_dir():
		return
	for cached in cache.glob(f"{path.stem}.*.pyc"):
		cached.unlink(missing_ok=True)


@contextmanager
def planted(path: Path, old: str, new: str, *, count: int = 1) -> Iterator[Path]:
	"""Plant a defect in ``path``, restore afterwards, and prove both.

	Raises ``AssertionError`` before writing anything if ``old`` is not present
	exactly ``count`` times. That assertion is the difference between a canary
	and a test that passes because it changed nothing.

	Two guards make a leaked mutation impossible rather than unlikely, because a
	leaked mutation is the worst failure this helper can have: it does not fail
	a test, it silently corrupts the source tree the rest of the suite reads.

	* **The mutation is serialised per file.** Two pytest processes canary the
	  same source at once -- that is the normal case when an agent and a session
	  share a tree -- and without a lock the second process reads the first's
	  planted defect as its own "original" and restores *to the defect*. On
	  2026-10-12 exactly that left `if False:  # canary` in `market/clearing.py`
	  and an unchecked `np.linalg.cholesky` in `market/risk.py`, and the next
	  run's canaries then failed for a reason unrelated to any gate.

	* **The restore is from the bytes read under the lock**, not from the backup
	  file, so it cannot fail for want of a file. The backup is for the case
	  there is no `finally` at all -- the process is killed mid-canary.

	* **The body has a deadline.** A body that never returns never unwinds, so
	  the `finally` never runs and the mutation stays on disk for the next
	  process to read as the original. `_HOLD_SECONDS` interrupts it, which
	  makes the restore reachable and turns a hang into a failure. This is the
	  guard the other three cannot provide: they all assume the body returns.
	"""
	assert path.is_file(), f"canary target is not a file: {path}"
	backup = path.with_suffix(f"{path.suffix}.{os.getpid()}.{next(_COUNTER)}.canary-backup")
	with open(_lock_for(path), "w") as lock:
		fcntl.flock(lock, fcntl.LOCK_EX)
		original = path.read_text()
		found = original.count(old)
		assert found >= count, (
			f"canary target not found in {path.name}: {old!r} occurs {found} time(s), "
			f"expected at least {count}. The canary would have been a no-op."
		)
		shutil.copy2(path, backup)
		try:
			path.write_text(original.replace(old, new, count))
			_invalidate_bytecode(path)
			with _hold_deadline(_HOLD_SECONDS, path):
				yield path
		finally:
			# Restored from memory, not from `git checkout`: the real work and the
			# mutation are both uncommitted in this file, so checkout discards both.
			path.write_text(original)
			_invalidate_bytecode(path)
			backup.unlink(missing_ok=True)
			assert path.read_text() == original, f"{path.name} was not restored to its original bytes"


def assert_raises(exception: type[BaseException], call, *args, **kwargs) -> BaseException:
	"""Call and return the exception, failing with a useful message if none raised."""
	try:
		call(*args, **kwargs)
	except exception as exc:  # noqa: BLE001 - the canary asserts on the type
		return exc
	except BaseException as exc:  # noqa: BLE001
		raise AssertionError(f"expected {exception.__name__}, got {type(exc).__name__}: {exc}") from exc
	raise AssertionError(
		f"{exception.__name__} was not raised: the gate is blind to the defect "
		f"this canary just planted"
	)


__all__ = [
	"REPO",
	"CanaryTimeout",
	"assert_raises",
	"leaked_mutations",
	"planted",
	"probe",
	"probe_exit_code",
	"pytest",
]
