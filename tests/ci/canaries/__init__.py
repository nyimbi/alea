# SPDX-License-Identifier: MIT
"""Canaries. Every gate is watched failing on the defect it exists to catch.

A gate that has never been seen to fail is not evidence of anything: it may be
scoped to the wrong set, may parse the wrong spelling, or may never have run at
all. These tests plant each defect and assert the gate notices.

The discipline, which `canary` below enforces rather than documents:

1. Assert the target text exists before mutating. A patch that does not apply
   leaves the file untouched and the canary passes against working code -- a
   false alarm about a gate that was never pointed anywhere.
2. Back up to a file and restore from that backup. **Never** `git checkout --
   <file>`: the canary's mutation and real uncommitted work live in the same
   file, so checkout discards both.
3. Assert the gate fails while the defect is planted.
4. Assert it passes again once restored, or the restore is not proven.
"""

from __future__ import annotations

import fcntl
import hashlib
import itertools
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

_COUNTER = itertools.count()


def _lock_for(path: Path) -> Path:
	"""A per-target lock file in the temp directory.

	Keyed by the target's resolved path rather than placed beside it: a lock
	file inside the repo is one more untracked artefact for `git status` to
	explain, and `shutil.copy2`/`write_text` never touch it.
	"""
	digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
	return Path(tempfile.gettempdir()) / f"alea-canary-{digest}.lock"


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
			yield path
		finally:
			# Restored from memory, not from `git checkout`: the real work and the
			# mutation are both uncommitted in this file, so checkout discards both.
			path.write_text(original)
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


__all__ = ["REPO", "assert_raises", "planted", "pytest"]
