# SPDX-License-Identifier: MIT
"""Canary for the review-backlog gate: the age, and the ceiling's comparison.

`test_the_backlog_reports_the_age_a_depth_alone_cannot` asserts that two queues
with the *same depth* and different histories report different ages, and
`test_the_ceiling_is_breached_at_the_limit_not_past_it` pins §16's "< 100
pending" to `>=`.

Two mutations, each the historical defect rather than a different one:

* **The age is dropped.** ``oldest_pending_at`` and ``pending_count`` were both
  written, both correct, and read by nothing -- so the metric the spec's §14
  asks for ("review queue depth **and** oldest pending signal") was half
  measured and wholly unreported. Returning ``None`` for the age is exactly
  that state: the depth is right and the history is gone.

* **The comparison is off by one.** §16's target is "*less than* 100 pending at
  any time", so the breach is at 100 and not at 101. ``>`` is the plausible
  wrong reading, and a gate that asserted only one side of the boundary would
  pass for either.

Both probes run in a subprocess so the mutated module is read fresh. The
mutation is *disjoint* from what the predicate looks for in each case: the age
mutation removes the value rather than changing it, and the comparison mutation
moves the boundary rather than the number under test.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

QUEUE_PY = REPO / "src" / "alea" / "scanning" / "review" / "queue.py"
VIEWS_PY = REPO / "src" / "alea" / "scanning" / "views.py"

#: Two queues, same depth, different ages; then the boundary.
_AGE_PROBE = textwrap.dedent(
	"""
	import sqlite3, tempfile, pathlib, asyncio
	from datetime import timedelta
	from alea.io.artefacts import utcnow
	from alea.scanning.review.queue import ReviewQueue
	from alea.signals.models import Signal, SignalType

	def signal(index):
		return Signal(
			signal_type=SignalType.GENERATION_INVESTMENT,
			confidence=0.8,
			source_document_id=f"doc-{index}",
			source_url="https://example.org/plant",
			source_name="example.org",
			country_iso="KE",
			capacity_mw=100.0,
			requires_review=True,
		)

	async def main():
		with tempfile.TemporaryDirectory() as tmp:
			fresh = ReviewQueue(path=pathlib.Path(tmp) / "fresh.sqlite")
			stale = ReviewQueue(path=pathlib.Path(tmp) / "stale.sqlite")
			for q in (fresh, stale):
				for i in range(3):
					await q.enqueue(signal(i))
			now = utcnow()
			conn = sqlite3.connect(stale.path)
			conn.execute("DROP TRIGGER IF EXISTS signal_versions_no_update")
			conn.execute("UPDATE signal_versions SET created_at = ?",
						 ((now - timedelta(days=7)).isoformat(),))
			conn.commit()
			conn.close()
			f = await fresh.backlog(now=now)
			s = await stale.backlog(now=now)
			print("BACKLOG", f.pending, f.oldest_age_hours, s.pending, s.oldest_age_hours)
			await fresh.aclose()
			await stale.aclose()

	asyncio.run(main())
	"""
)

_BOUNDARY_PROBE = textwrap.dedent(
	"""
	from alea.scanning.views import ReviewBacklog
	print("BOUNDARY", ReviewBacklog(pending=99).breaches(100),
		  ReviewBacklog(pending=100).breaches(100),
		  ReviewBacklog(pending=101).breaches(100))
	"""
)


def _run(probe: str, marker: str) -> list[str]:
	completed = subprocess.run(
		[sys.executable, "-c", probe], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
	assert marked, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	return marked[-1].split()[1:]


def test_the_backlog_gate_notices_a_depth_with_no_age():
	"""Drop the age and watch the two-queue assertion go red.

	The mutation returns ``None`` for the age, which is the state the tree was
	in before: ``oldest_pending_at`` existed and nothing reported it. The gate's
	discriminator is that the *stale* queue's age exceeds six days while the
	fresh one's does not, so a ``None`` age fails it -- and the two queues having
	equal depth is asserted first, so the mutation cannot pass by making the
	depths differ instead.
	"""
	fresh_pending, fresh_age, stale_pending, stale_age = _run(_AGE_PROBE, "BACKLOG")
	assert fresh_pending == stale_pending == "3", (
		f"the probe's two queues are not the same depth ({fresh_pending} vs "
		f"{stale_pending}), so the age is not what is being measured"
	)
	assert fresh_age != "None" and stale_age != "None"
	assert float(stale_age) > 24.0 * 6, f"the stale queue reported {stale_age} h"

	# Restore the defect: the age reported as absent, which is what "written and
	# read by nothing" amounts to from a caller's side.
	target = "\t\t\tage_hours = max((moment - oldest).total_seconds() / 3600.0, 0.0)"
	replacement = "\t\t\tage_hours = None  # canary: age dropped"
	with planted(QUEUE_PY, target, replacement):
		_, _, _, stale_age_after = _run(_AGE_PROBE, "BACKLOG")
		assert stale_age_after == "None", (
			f"with the age dropped the backlog still reported {stale_age_after}; "
			f"the gate does not read the age"
		)

	# Restored.
	fresh_pending, fresh_age, stale_pending, stale_age = _run(_AGE_PROBE, "BACKLOG")
	assert float(stale_age) > 24.0 * 6


def test_the_ceiling_gate_notices_the_boundary_moved():
	"""Move the breach to 101 and watch the boundary assertion go red.

	§16's target is "*less than* 100", so 100 is already outside it. The
	mutation swaps ``>=`` for ``>``, which is the plausible wrong reading and is
	*disjoint* from the literals the gate asserts -- the gate names 99, 100 and
	101, and the mutation moves the comparison rather than any of those numbers.
	"""
	inside, at_limit, over = _run(_BOUNDARY_PROBE, "BOUNDARY")
	assert (inside, at_limit, over) == ("False", "True", "True"), (
		f"the boundary was already wrong before any mutation: 99 -> {inside}, "
		f"100 -> {at_limit}, 101 -> {over}"
	)

	target = "\t\treturn self.pending >= limit"
	replacement = "\t\treturn self.pending > limit  # canary: boundary moved past the limit"
	with planted(VIEWS_PY, target, replacement):
		_, at_limit_after, _ = _run(_BOUNDARY_PROBE, "BOUNDARY")
		assert at_limit_after == "False", (
			f"with the boundary moved to 'past the limit' a depth of exactly 100 "
			f"still breached ({at_limit_after}); the gate does not pin the boundary"
		)

	# Restored.
	inside, at_limit, over = _run(_BOUNDARY_PROBE, "BOUNDARY")
	assert (inside, at_limit, over) == ("False", "True", "True")
