# SPDX-License-Identifier: MIT
"""Canary for the extraction-accuracy gate: the machine/human split, and the artefact's location.

`test_a_machine_confirmation_is_not_human_evidence` asserts that a signal the
precision threshold auto-accepted is *not* counted as a human confirmation. The
defect it exists to catch is precise, and it is not a wrong number: it is a
feedback loop. `auto_accept_precisions` selects the auto-acceptance threshold
from `precision`, and the service records every auto-acceptance as a
confirmation under an `auto:`-prefixed analyst. Count those as human evidence
and the threshold starts accepting signals on the strength of signals it
accepted -- the reported precision rises as the threshold widens, which is the
opposite of a measurement.

The mutation is *disjoint* from what the predicate reads: it does not change the
numbers the test asserts (one human confirmation, one rejection, one machine
confirmation) nor the analyst string it plants. It removes the branch that
consults the analyst at all, which is exactly the state the tree was in before
the split existed -- `accuracy()` counted every confirmed version the same way.

`test_the_accuracy_artefact_lands_where_the_coverage_check_looks` carries the
other half of criterion 8, and it is the register's own defect class: a producer
that writes an artefact somewhere the coverage check does not look leaves
`extraction_accuracy` on the missing list while an artefact for it exists on
disk. Its canary moves the write to the default root, which is what a caller
that forgot the argument would do.

Both probes run in a subprocess, because each gate is a code path rather than a
value shape: the mutation is a source edit and the gate has to execute against
the mutated file in a fresh interpreter.
"""

from __future__ import annotations

import textwrap

from tests.ci.canaries import REPO, planted, probe

QUEUE_PY = REPO / "src" / "alea" / "scanning" / "review" / "queue.py"
SERVICE_PY = REPO / "src" / "alea" / "scanning" / "service.py"

#: One human confirmation, one human rejection, one machine confirmation. The
#: human precision is 1/2; counting the machine one makes it 2/3.
_PROBE = textwrap.dedent(
	"""
	import asyncio, tempfile, pathlib
	from alea.scanning.review.queue import ReviewQueue
	from alea.signals.models import Signal, SignalType

	def signal(index):
		return Signal(
			signal_type=SignalType.GENERATION_INVESTMENT,
			confidence=0.8,
			source_document_id=f"doc-{index}",
			source_url=f"https://example.org/{index}",
			source_name="example.org",
			country_iso="KE",
			capacity_mw=100.0,
			requires_review=True,
		)

	async def main():
		with tempfile.TemporaryDirectory() as tmp:
			queue = ReviewQueue(path=pathlib.Path(tmp) / "q.sqlite")
			ids = [(await queue.enqueue(signal(i))).signal_id for i in range(3)]
			await queue.confirm(ids[0], "alice")
			await queue.reject(ids[1], "bob", reason="not a plant")
			await queue.confirm(ids[2], "auto:precision-threshold", reason="threshold")
			report = await queue.accuracy()
			row = report.by_signal_type()["generation_investment"]
			print("SPLIT", row.confirmed, row.machine_confirmed, row.rejected,
				  row.sample_size, round(row.precision, 4))
			await queue.aclose()

	asyncio.run(main())
	"""
)


def _split() -> tuple[int, int, int, int, float]:
	completed = probe(_PROBE)
	assert completed.returncode == 0, completed.stderr
	lines = [line for line in completed.stdout.splitlines() if line.startswith("SPLIT")]
	assert lines, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	confirmed, machine, rejected, sample, precision = lines[-1].split()[1:]
	return int(confirmed), int(machine), int(rejected), int(sample), float(precision)


def test_the_accuracy_gate_notices_a_machine_confirmation_counted_as_human():
	"""Drop the analyst split and watch the human precision go wrong.

	The mutation replaces the `auto:` branch with the plain else, so every
	confirmation counts as human -- the pre-split behaviour. The gate's
	discriminator is `machine_confirmed == 1` and `precision == 0.5`, and the
	human/rejection counts are asserted first so the mutation cannot pass by
	moving those instead.
	"""
	confirmed, machine, rejected, sample, precision = _split()
	assert (confirmed, machine, rejected) == (1, 1, 1), (
		f"the probe's record is not the intended one before any mutation: "
		f"confirmed={confirmed} machine={machine} rejected={rejected}"
	)
	assert sample == 2 and precision == 0.5, (
		f"the human-only precision is not 1/2 before any mutation: "
		f"sample={sample} precision={precision}"
	)

	target = """			if row["action"] == "confirm":
				if str(row["analyst"]).startswith("auto:"):
					machine_confirmed.add(row["signal_id"])
				else:
					machine_confirmed.discard(row["signal_id"])"""
	replacement = """			if row["action"] == "confirm":
				machine_confirmed.discard(row["signal_id"])  # canary: split dropped"""

	with planted(QUEUE_PY, target, replacement):
		confirmed_after, machine_after, _, sample_after, precision_after = _split()
		assert machine_after == 0, (
			f"with the analyst split dropped a machine confirmation still reported "
			f"as machine ({machine_after}); the gate does not read the analyst"
		)
		assert confirmed_after == 2 and sample_after == 3, (
			f"the machine confirmation did not enter the human sample: "
			f"confirmed={confirmed_after} sample={sample_after}"
		)
		assert precision_after != 0.5, (
			f"the human precision did not move when the machine confirmation was "
			f"counted as human ({precision_after}); the gate is blind to the loop"
		)

	# Restored.
	confirmed, machine, rejected, sample, precision = _split()
	assert (confirmed, machine, rejected, sample, precision) == (1, 1, 1, 2, 0.5)


#: Whether the coverage check can see the artefact the producer just wrote.
_COVERAGE_PROBE = textwrap.dedent(
	"""
	import asyncio, tempfile, pathlib
	from alea.quality import missing_validation_targets, validation_coverage
	from alea.scanning.review.queue import ReviewQueue
	from alea.scanning.service import extraction_accuracy_artefact
	from alea.signals.models import Signal, SignalType

	def signal(index):
		return Signal(
			signal_type=SignalType.GENERATION_INVESTMENT,
			confidence=0.8,
			source_document_id=f"doc-{index}",
			source_url=f"https://example.org/{index}",
			source_name="example.org",
			country_iso="KE",
			capacity_mw=100.0,
			requires_review=True,
		)

	async def main(tmp):
		queue = ReviewQueue(path=pathlib.Path(tmp) / "q.sqlite")
		version = await queue.enqueue(signal(0))
		await queue.confirm(version.signal_id, "alice")
		await queue.aclose()

	with tempfile.TemporaryDirectory() as tmp:
		asyncio.run(main(tmp))
		root = pathlib.Path(tmp) / "quality"
		extraction_accuracy_artefact(
			root / "scanning" / "extraction_accuracy.parquet",
			queue=ReviewQueue(path=pathlib.Path(tmp) / "q.sqlite"),
		)
		covered = "extraction_accuracy" in validation_coverage(root)
		print("COVERED", covered)
	"""
)


def test_the_coverage_canary_notices_an_artefact_written_somewhere_else():
	"""Write the artefact to the default root and watch coverage lose it.

	The mutation drops the caller's ``root`` and lets ``write_validation`` fall
	back to ``storage_root()`` -- the repository's ``results/quality``. That is
	what a caller who forgot the argument produces, and it is the register's own
	defect class: an artefact on disk that the check for artefacts cannot see.

	The probe writes under a temp directory, so the *unmutated* run finds the
	artefact in the temp root and the *mutated* one writes into the repo's
	results tree instead -- where ``validation_coverage(root)`` is not looking.
	"""
	completed = probe(_COVERAGE_PROBE)
	assert completed.returncode == 0, completed.stderr
	lines = [line for line in completed.stdout.splitlines() if line.startswith("COVERED")]
	assert lines, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	assert lines[-1].split()[-1] == "True", (
		"the coverage check cannot see the artefact before any mutation; the "
		"gate is not measuring what the canary mutates"
	)

	target = "\twritten = write_validation(artefact, root=_quality_root(out))"
	replacement = "\twritten = write_validation(artefact)  # canary: root dropped"

	try:
		with planted(SERVICE_PY, target, replacement):
			completed = probe(_COVERAGE_PROBE)
			assert completed.returncode == 0, completed.stderr
			after = [
				line for line in completed.stdout.splitlines() if line.startswith("COVERED")
			]
			assert after and after[-1].split()[-1] == "False", (
				f"with the root dropped the coverage check still found the artefact "
				f"({after[-1] if after else 'no output'}); the gate does not pin where "
				f"it is written"
			)
	finally:
		# The mutated run wrote into the repository's own results tree, because
		# that is where `storage_root()` points. It is gitignored, so `git
		# status` would not show it -- and a fabricated validation artefact left
		# there makes `missing_validation_targets()` report a target covered by
		# a measurement the canary invented. Cleaning up is not tidiness; it is
		# the difference between a canary and a forged result.
		_default = REPO / "results" / "quality" / "validation"
		for name in ("extraction_accuracy.json", "extraction_accuracy.json.provenance.json"):
			(_default / name).unlink(missing_ok=True)
		# `rmdir`, not a recursive delete: it refuses a non-empty directory, so a
		# real artefact another run wrote there is left alone rather than taken
		# with the canary's litter.
		_default.rmdir() if _default.is_dir() else None
