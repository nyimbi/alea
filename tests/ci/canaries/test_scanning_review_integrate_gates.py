# SPDX-License-Identifier: MIT
"""Canaries for the review and integration gates.

* ``test_review_is_append_only`` — the queue's tables carry ``BEFORE UPDATE`` and
  ``BEFORE DELETE`` triggers. Drop one and an edit mutates the stored extraction
  in place, which destroys the difference between what was extracted and what
  was confirmed — the measurement the accuracy report is built from. The canary
  removes the ``signal_versions`` update trigger and watches a raw ``UPDATE``
  succeed where the gate expects ``IntegrityError``.
* ``test_integrate_refuses_unreviewed`` — ``integrate`` refuses a signal whose
  ``requires_review`` is set. Remove the guard and an unreviewed machine
  extraction is staged into the pipeline, which is the one thing the layer
  exists to prevent. The canary removes the raise and watches the gate's
  ``pytest.raises`` miss.
* ``test_signal_conflict_not_autoresolved`` — a figure more than ``tolerance``
  from the dataset is recorded as a conflict, not applied. The canary widens the
  comparison to ``>=`` a value that is never exceeded, and watches a 150%
  divergence stage as if it agreed.

All probes run in a subprocess so the mutated module is read fresh.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

QUEUE_PY = REPO / "src" / "alea" / "scanning" / "review" / "queue.py"
INTEGRATE_PY = REPO / "src" / "alea" / "scanning" / "integrate.py"

_APPEND_ONLY_PROBE = textwrap.dedent(
	"""
	import asyncio, sqlite3, tempfile, pathlib
	from alea.scanning.review import ReviewQueue
	from alea.signals.models import Signal, SignalType

	def signal():
		return Signal(signal_type=SignalType.GENERATION_INVESTMENT, confidence=0.8,
			source_document_id="d", source_url="https://e.org/p", source_name="e.org",
			country_iso="KE", capacity_mw=100.0, requires_review=True)

	async def main():
		with tempfile.TemporaryDirectory() as d:
			q = ReviewQueue(path=pathlib.Path(d) / "q.sqlite")
			s = signal()
			await q.enqueue(s)
			await q.confirm(s.signal_id, "analyst")
			await q.aclose()
			con = sqlite3.connect(pathlib.Path(d) / "q.sqlite")
			try:
				con.execute("UPDATE signal_versions SET priority = 999")
				print("RESULT updated")
			except sqlite3.IntegrityError:
				print("RESULT refused")
			finally:
				con.close()

	asyncio.run(main())
	"""
)


def _append_only_result() -> str:
	completed = subprocess.run(
		[sys.executable, "-c", _APPEND_ONLY_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
	assert marked, f"the append-only probe printed nothing:\n{completed.stdout}"
	return marked[-1].split()[1]


def test_the_append_only_gate_notices_a_dropped_trigger():
	"""Drop the update trigger and watch a raw UPDATE succeed."""
	assert _append_only_result() == "refused", "the trigger was already missing"

	# The trigger is a whole statement; replacing its body with a no-op SELECT
	# keeps the DDL valid while making it stop aborting.
	target = (
		"CREATE TRIGGER IF NOT EXISTS signal_versions_no_update\n"
		"BEFORE UPDATE ON signal_versions\n"
		"BEGIN\n"
		"\tSELECT RAISE(ABORT, 'signal_versions is append-only: record a new version');\n"
		"END;"
	)
	replacement = (
		"CREATE TRIGGER IF NOT EXISTS signal_versions_no_update\n"
		"BEFORE UPDATE ON signal_versions\n"
		"BEGIN\n"
		"\tSELECT 1;\n"
		"END;"
	)
	with planted(QUEUE_PY, target, replacement):
		assert _append_only_result() == "updated", (
			"with the trigger neutralised the UPDATE was still refused; the gate "
			"does not depend on the trigger"
		)

	# Restored.
	assert _append_only_result() == "refused"


_REFUSAL_PROBE = textwrap.dedent(
	"""
	from alea.scanning.integrate import integrate, UnreviewedSignalError
	from alea.signals.models import Signal, SignalType

	s = Signal(signal_type=SignalType.GENERATION_INVESTMENT, confidence=0.8,
		source_document_id="d", source_url="https://e.org/p", source_name="e.org",
		country_iso="KE", capacity_mw=100.0, requires_review=True)
	try:
		integrate(s)
		print("RESULT integrated")
	except UnreviewedSignalError:
		print("RESULT refused")
	"""
)


def _refusal_result() -> str:
	completed = subprocess.run(
		[sys.executable, "-c", _REFUSAL_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
	assert marked, f"the refusal probe printed nothing:\n{completed.stdout}"
	return marked[-1].split()[1]


def test_the_integrate_refusal_gate_notices_a_removed_guard():
	"""Remove the unreviewed guard and watch an unreviewed signal integrate."""
	assert _refusal_result() == "refused", "the guard was already missing"

	target = '\tif signal.requires_review:\n\t\traise UnreviewedSignalError('
	replacement = '\tif False:\n\t\traise UnreviewedSignalError('
	with planted(INTEGRATE_PY, target, replacement):
		assert _refusal_result() == "integrated", (
			"with the guard removed the unreviewed signal was still refused; the "
			"gate does not depend on the guard"
		)

	# Restored.
	assert _refusal_result() == "refused"


_CONFLICT_PROBE = textwrap.dedent(
	"""
	from alea.scanning.integrate import integrate
	from alea.signals.models import Signal, SignalType

	s = Signal(signal_type=SignalType.GENERATION_INVESTMENT, confidence=0.8,
		source_document_id="d", source_url="https://e.org/p", source_name="e.org",
		country_iso="KE", capacity_mw=500.0, requires_review=False)
	p = integrate(s, known_values={"capacity_mw": 200.0})
	print("RESULT", p.status)
	"""
)


def _conflict_result() -> str:
	completed = subprocess.run(
		[sys.executable, "-c", _CONFLICT_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
	assert marked, f"the conflict probe printed nothing:\n{completed.stdout}"
	return marked[-1].split()[1]


def test_the_conflict_gate_notices_an_autoresolved_divergence():
	"""Neutralise the conflict test and watch a 150% divergence stage as agreement."""
	assert _conflict_result() == "conflict", "the conflict test was already neutralised"

	target = "\t\tif conflict.relative_difference > tolerance:"
	replacement = "\t\tif conflict.relative_difference > 1e9:"
	with planted(INTEGRATE_PY, target, replacement):
		assert _conflict_result() == "staged", (
			"with the conflict test neutralised the divergence was still recorded; "
			"the gate does not depend on the comparison"
		)

	# Restored.
	assert _conflict_result() == "conflict"
