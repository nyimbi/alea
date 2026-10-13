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


def test_the_harness_purges_bytecode_on_both_sides_of_a_mutation(tmp_path: Path) -> None:
	"""The defect: a same-length mutation whose `.pyc` outlives the restore.

	CPython invalidates a cached `.pyc` on the source's (mtime, size). A mutation
	and its restore that are the same length and land in the same mtime tick
	leave a cache that still matches, so the next interpreter loads the *defect*
	from a source file that reads correctly.

	`extra="forbid"` -> `extra="ignore"` is that shape, six bytes to six bytes,
	and on 2026-10-12 it made three `test_config_rejects_typo.py` tests fail on a
	clean tree with `models.py` plainly saying `forbid`.

	A scratch module rather than a real one: the harness's own tests must not be
	able to leave a stale cache in the package, which is the failure they exist
	to catch.
	"""
	import py_compile

	module = tmp_path / "subject_module.py"
	module.write_text("VALUE = 'forbid'\n")
	# A real `.pyc`, as an import would leave behind.
	compiled = py_compile.compile(str(module), doraise=True)
	assert compiled is not None, "py_compile reported success without a path"
	cached = Path(compiled)
	assert cached.is_file(), "no bytecode was produced to invalidate"

	with planted(module, "'forbid'", "'ignore'"):
		assert not cached.exists(), "the mutation did not purge the stale bytecode"

	# And the restore purges too, so the tree ends with the cache the source
	# deserves rather than the one the mutation left.
	assert not cached.exists(), "the restore left the mutation's bytecode trusted"
	assert module.read_text() == "VALUE = 'forbid'\n"


def test_the_harness_interrupts_a_body_that_holds_a_mutation_too_long(
	target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""The defect: a body that never returns, holding the mutation forever.

	The one failure the other four guards cannot catch, because all of them
	assume the body returns. A hang leaves the defect planted past the life of
	the process, and the *next* process reads that defect as the original and
	restores to it -- so the leak outlives its cause. Measured 2026-10-13: a
	probe deadlocked in `libarrow`'s thread-pool destructor during exit,
	`subprocess.run` had no timeout, and `assemble.py` and `integrate.py` were
	found hours later still carrying planted mutations.

	The deadline is driven down rather than waited out, and the body blocks on
	an `Event` rather than sleeping, so the test costs the interrupt latency and
	not the deadline.
	"""
	import tests.ci.canaries as harness

	monkeypatch.setattr(harness, "_HOLD_SECONDS", 0.5)
	blocked = threading.Event()
	interrupted: list[type[BaseException]] = []

	with (
		pytest.raises(harness.CanaryTimeout, match="held a mutation"),
		planted(target, "line two", "line TWO"),
	):
		try:
			blocked.wait(timeout=30)
		except BaseException as exc:  # noqa: BLE001 - recorded, re-raised below
			interrupted.append(type(exc))
			raise

	assert interrupted == [harness.CanaryTimeout], (
		"the deadline raised nothing the body could see, so the body would have "
		"held the mutation until the process died"
	)
	assert target.read_text() == ORIGINAL, (
		"a hung canary left the tree mutated; the interrupt must make the "
		"`finally` reachable, or the leak outlives the process"
	)
	assert not list(target.parent.glob("*.canary-backup")), (
		"a hung canary left its backup behind, which is what a later run would "
		"read as the original"
	)


def test_the_harness_deadline_is_disabled_in_a_worker_thread(
	target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""`signal.signal` refuses outside the main thread, so the deadline must not arm there.

	`test_two_canaries_on_one_file_do_not_see_each_other` drives `planted` from
	worker threads on purpose, and a `ValueError: signal only works in main
	thread` there would be the harness breaking the one test that proves its
	lock works. A worker that hangs does not corrupt the tree on its own -- the
	session is stuck, which is already visible -- so the deadline stands down.
	"""
	import tests.ci.canaries as harness

	monkeypatch.setattr(harness, "_HOLD_SECONDS", 0.5)
	seen: list[str] = []

	def worker() -> None:
		try:
			with planted(target, "line two", "line TWO"):
				seen.append(target.read_text())
		except BaseException as exc:  # noqa: BLE001 - reported below
			seen.append(f"raised {type(exc).__name__}: {exc}")

	thread = threading.Thread(target=worker)
	thread.start()
	thread.join(timeout=10)

	assert seen == ["line one\nline TWO\nline three\n"], (
		f"the deadline broke `planted` in a worker thread: {seen}"
	)
	assert target.read_text() == ORIGINAL


def test_leaked_mutations_finds_a_backup_a_dead_canary_left(tmp_path: Path) -> None:
	"""A backup on disk is a live defect, and the check must see one.

	`planted` unlinks its backup in the same `finally` that restores, so a
	backup that survives means the restore never ran -- and the file beside it
	is mutated. This is the detector for the state the 2026-10-13 hang left the
	tree in; scoped to a temporary tree here because the point is the *finding*,
	not the repo's current contents.
	"""
	from tests.ci.canaries import leaked_mutations

	assert leaked_mutations([tmp_path]) == [], "an empty tree reported a leak"

	stranded = tmp_path / "src" / "assemble.py.1234.0.canary-backup"
	stranded.parent.mkdir(parents=True)
	stranded.write_text("the original bytes\n")
	(tmp_path / "src" / "assemble.py").write_text("the planted defect\n")

	assert leaked_mutations([tmp_path]) == [stranded], (
		"a stranded backup went unnoticed, so the mutated file beside it would be "
		"read as the original by the next run"
	)


def test_the_repository_holds_no_leaked_mutation() -> None:
	"""The live check: no canary run has left a defect planted in this tree.

	Pinned as a gate rather than a one-off because the failure is silent and
	self-perpetuating -- a leaked mutation is not a red test, it is a *green*
	test over corrupted source, and the three `test_scanning_gates.py` conflict
	tests failed for hours on 2026-10-13 under a `tolerance` the harness had
	replaced with `1e9`.
	"""
	from tests.ci.canaries import leaked_mutations

	found = leaked_mutations()
	assert not found, (
		"a canary run left mutations planted in the tree; each backup names the "
		"file whose current contents are a *defect*, not the original:\n  "
		+ "\n  ".join(str(path) for path in found)
		+ "\nRestore each from its backup before trusting any test result."
	)
