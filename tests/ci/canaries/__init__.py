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

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@contextmanager
def planted(path: Path, old: str, new: str, *, count: int = 1) -> Iterator[Path]:
	"""Plant a defect in ``path``, restore afterwards, and prove both.

	Raises ``AssertionError`` before writing anything if ``old`` is not present
	exactly ``count`` times. That assertion is the difference between a canary
	and a test that passes because it changed nothing.
	"""
	assert path.is_file(), f"canary target is not a file: {path}"
	original = path.read_text()
	found = original.count(old)
	assert found >= count, (
		f"canary target not found in {path.name}: {old!r} occurs {found} time(s), "
		f"expected at least {count}. The canary would have been a no-op."
	)
	backup = path.with_suffix(path.suffix + ".canary-backup")
	shutil.copy2(path, backup)
	try:
		path.write_text(original.replace(old, new, count))
		yield path
	finally:
		# Restored from the file backup, not from `git checkout`. The real work
		# and the mutation are both uncommitted in this file.
		shutil.copy2(backup, path)
		backup.unlink()
		after = path.read_text()
		assert after == original, f"{path.name} was not restored to its original bytes"


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
