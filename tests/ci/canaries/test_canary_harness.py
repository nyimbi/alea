# SPDX-License-Identifier: MIT
"""Canaries for the canary harness itself.

Every gate in this repository is trusted because a canary was watched failing on
a planted defect. That makes `planted` the root of the trust tree, and it had
never been pointed at a defect of its own -- the same gap it exists to catch,
one level up.

The harness has two ways to lie, and both were live on 2026-10-12:

* **A patch that does not apply.** If the target text is absent, the mutation is
  a no-op, the gate passes against untouched code, and the canary reports a
  working gate. `planted` asserts the target exists, and this file watches that
  assertion fire.

* **A restore that does not restore.** Two pytest processes canarying one file
  share a fixed backup path, so the second clobbers the first's backup, the
  first's restore fails, and its planted defect stays in the source. That is not
  a failed test -- it is a corrupted tree that makes every later canary fail for
  a reason unrelated to any gate. It left `if False:  # canary` in
  `market/clearing.py` and an unchecked `np.linalg.cholesky` in `market/risk.py`,
  and the fix is the lock and the in-memory restore this file now checks.

The concurrency test is the important one. It is also the one that cannot be
written as a single `planted` call, so it drives threads directly.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from tests.ci.canaries import planted

WORKERS = 3
"""How many canaries contend for the file. Must equal the barrier's parties, or
every worker times out at the barrier and the concurrency test never runs -- which
is how this test first passed its own guard: three threads waiting on a barrier of
four all raised `BrokenBarrierError`, and the assertion that caught it was the one
checking the workers' own errors."""

ORIGINAL = "line one\nline two\nline three\n"


class _BodyRan(Exception):
	"""Raised by a guard body that should never have executed.

	A distinct type, not `AssertionError`: the harness refuses by asserting, so a
	body raising `AssertionError` would be caught by `pytest.raises(AssertionError)`
	and the test would pass because the body ran rather than because the harness
	refused. The instrument has to be able to tell those apart.
	"""


@pytest.fixture()
def target(tmp_path: Path) -> Path:
	"""A scratch file for the harness to mutate.

	A real file in `tmp_path` rather than a source file: the harness's own tests
	must not be able to corrupt the tree they run against if the harness is
	broken. Testing a mutation helper against a source file is how the source
	file gets mutated.
	"""
	scratch = tmp_path / "subject.txt"
	scratch.write_text(ORIGINAL)
	return scratch


def test_the_harness_refuses_a_target_that_is_absent(target: Path):
	"""The defect: a patch whose target text is not in the file.

	This is the "canary whose patch does not apply is a canary that did not run"
	failure. It must raise *before* writing, or the file is left modified by a
	canary that proved nothing.
	"""
	with (
		pytest.raises(AssertionError, match="canary target not found"),
		planted(target, "text that is not there", "replacement"),
	):
		raise _BodyRan("the harness did not refuse a patch that does not apply")

	assert target.read_text() == ORIGINAL, "the harness wrote before it refused"


def test_the_harness_refuses_a_target_that_is_not_a_file(tmp_path: Path):
	"""A canary pointed at a missing path is a canary pointed at nothing."""
	with (
		pytest.raises(AssertionError, match="not a file"),
		planted(tmp_path / "absent.txt", "a", "b"),
	):
		raise _BodyRan("the harness accepted a path that is not a file")


def test_the_harness_honours_the_occurrence_count(target: Path):
	"""``count`` guards against a patch landing on the wrong site.

	A defect class that occurs twice must not be patched once and reported as
	covered -- the second occurrence is the one that stays live.
	"""
	target.write_text("x\nx\n")
	with (
		pytest.raises(AssertionError, match="occurs 2 time"),
		planted(target, "x", "y", count=3),
	):
		raise _BodyRan("the harness ignored the occurrence count")

	with planted(target, "x", "y", count=2):
		assert target.read_text() == "y\ny\n"

	assert target.read_text() == "x\nx\n", "the restore did not run"


def test_the_harness_restores_after_the_body_raises(target: Path):
	"""The restore is a `finally`, so a canary that fails mid-body still cleans up.

	Without this, the first failing canary leaves its defect planted and every
	later canary in the session inherits it.
	"""
	with pytest.raises(RuntimeError, match="boom"), planted(target, "line two", "line TWO"):
		assert target.read_text() == "line one\nline TWO\nline three\n"
		raise RuntimeError("boom")

	assert target.read_text() == ORIGINAL, "a failed canary left the tree mutated"


def test_the_harness_restores_to_the_bytes_it_read(target: Path):
	"""The restore is from the bytes read under the lock, not from a backup file.

	Restoring from a *file* means the restore can fail for want of that file --
	which is exactly what happened when two processes shared one backup path.
	Deleting the backup mid-body must therefore not affect the restore.
	"""
	with planted(target, "line two", "line TWO"):
		for leftover in target.parent.glob("*.canary-backup"):
			leftover.unlink()

	assert target.read_text() == ORIGINAL, (
		"the restore depended on the backup file surviving the body"
	)


def test_two_canaries_on_one_file_do_not_see_each_other(target: Path):
	"""The defect: concurrent writers to one file sharing a backup path.

	Reproduces the 2026-10-12 leak. Each thread plants a *distinct* defect and
	asserts that, while it holds the file, it sees only its own mutation. Without
	the lock the second thread reads the first's defect as its "original" and
	restores to the defect, so the file ends the run corrupted -- and every
	canary after it fails for a reason unrelated to any gate.
	"""
	original = target.read_text()
	errors: list[str] = []
	barrier = threading.Barrier(WORKERS)

	def worker(index: int) -> None:
		try:
			barrier.wait(timeout=5)
			with planted(target, "line two", f"line {index}"):
				observed = target.read_text()
				expected = original.replace("line two", f"line {index}")
				if observed != expected:
					errors.append(f"worker {index} saw {observed!r}, expected {expected!r}")
		except Exception as exc:  # noqa: BLE001 - reported below
			errors.append(f"worker {index} raised {type(exc).__name__}: {exc}")

	threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, WORKERS + 1)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(timeout=10)

	assert not errors, "concurrent canaries interfered:\n  " + "\n  ".join(errors)
	assert target.read_text() == original, "the tree was left mutated after concurrent canaries"
	assert not list(target.parent.glob("*.canary-backup")), "a backup was left behind"
