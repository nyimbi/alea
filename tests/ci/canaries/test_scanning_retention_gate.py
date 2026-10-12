# SPDX-License-Identifier: MIT
"""Canary for the retention gate: the report's arithmetic must reconcile.

``test_retention_policy_applied`` asserts the purge removes the right payloads.
``test_the_retention_report_counts_add_up`` asserts the *report* is arithmetically
honest: ``removed_payloads + kept_payloads`` equals the population the purge
started from.

That second property had a real defect. ``kept_payloads`` was computed by
re-counting with a **one-day** window while the purge used the configured one,
so a 90-day purge over three payloads reported ``kept_payloads=1`` — a
denominator from a different question than the numerator. The canary plants the
defect back and watches the gate's sum check fail, which is what makes the gate
evidence rather than a test that happens to pass on the fixed code.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

INGEST_PY = REPO / "src" / "alea" / "scanning" / "ingest.py"

_ARITHMETIC_PROBE = textwrap.dedent(
	"""
	import json, tempfile, pathlib
	from datetime import timedelta
	from alea.io.artefacts import utcnow
	from alea.scanning.ingest import purge_expired_raw

	def payload(root, source, checksum, *, age_days, now):
		d = root / source / checksum
		d.mkdir(parents=True)
		(d / "payload.bin").write_bytes(b"raw source text")
		(d / "provenance.json").write_text(
			json.dumps({"retrieved_at": (now - timedelta(days=age_days)).isoformat()}))

	now = utcnow()
	with tempfile.TemporaryDirectory() as tmp:
		root = pathlib.Path(tmp) / "raw"
		payload(root, "news", "expired", age_days=200, now=now)
		payload(root, "news", "fresh", age_days=30, now=now)
		payload(root, "news", "today", age_days=0, now=now)
		r = purge_expired_raw(root, retention_days=90, now=now, dry_run=True)
		print("REPORT", r.removed_payloads, r.kept_payloads)
	"""
)


def _report() -> tuple[int, int]:
	completed = subprocess.run(
		[sys.executable, "-c", _ARITHMETIC_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("REPORT ")]
	assert marked, f"the retention probe printed nothing:\n{completed.stdout}"
	_, removed, kept = marked[-1].split()
	return int(removed), int(kept)


def test_the_retention_gate_notices_a_mismatched_denominator():
	"""Restore the one-day-window denominator and watch the sum check fail.

	The mutation puts back the defect exactly as it was: ``kept_payloads``
	re-counted from ``expired_raw_payloads(retention_days=1)``, so the kept side
	is measured over a window that has nothing to do with the purge.
	"""
	removed, kept = _report()
	assert removed + kept == 3, (
		f"the report was already wrong before any mutation: removed {removed} + "
		f"kept {kept} != 3"
	)
	assert kept == 2

	# Restore the defect exactly as it was: the population re-counted with a
	# one-day window instead of the configured retention.
	target = "\tpopulation = raw_payload_count(root, source_ids=source_ids)"
	replacement = (
		"\tpopulation = len(\n"
		"\t\texpired_raw_payloads(root, retention_days=1, now=moment, source_ids=source_ids)\n"
		"\t)"
	)
	with planted(INGEST_PY, target, replacement):
		removed_after, kept_after = _report()
		assert removed_after + kept_after != 3, (
			f"with the mismatched denominator restored the report still reconciled: "
			f"removed {removed_after} + kept {kept_after} == 3; the gate does not "
			f"check the denominator"
		)
		assert kept_after == 1, (
			f"the planted denominator produced kept_payloads={kept_after}, not the "
			f"1-payload figure the historical defect reported"
		)

	# Restored.
	removed_restored, kept_restored = _report()
	assert removed_restored + kept_restored == 3
	assert kept_restored == 2
