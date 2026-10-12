# SPDX-License-Identifier: MIT
"""Canaries for the two gates in `tests/ci/test_loading.py` a fixture can fool.

Both gates assert a quantity that a *plausible* implementation gets wrong in a
way that is invisible on the wrong fixture, so each is only evidence if it has
been watched failing on the defect it names.

* **Hours, not a snapshot count.** ``hours_at_or_above`` is the count times the
  snapshot length. The natural implementation -- and the one the section's
  "Hours" header invites -- is the count, and on an hourly series the two are
  the same number. The canary drops the multiplication and asserts the 15-minute
  gate notices.

* **No ratings is not no overloads.** A network whose every branch lacks an
  ``s_nom`` has no rating to divide by, and an empty ranking there publishes
  "nothing is overloaded" for a loading that was never measured. The canary
  removes the refusal and asserts the gate notices.

Both run in a fresh interpreter. The mutation is a source edit, and the kernel
is imported by the gate module at collection -- an in-process canary would
re-import nothing and assert against the module it already holds, which is the
vacuous-fixture failure `tests/ci/test_orchestration_registry.py` documents.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

FLOW = REPO / "src" / "alea" / "losses" / "flow.py"

GATE = "tests/ci/test_loading.py"

# The multiplication is the whole unit conversion. Removing it makes the field
# the snapshot count, which is correct on an hourly series and 4x too large on
# the 15-minute fixture the gate is written against.
HOURS_ANCHOR = "hours_at_or_above=float(at_or_above) * cfg.snapshot_hours,"
HOURS_PLANTED = "hours_at_or_above=float(at_or_above),"

# The refusal that keeps "no ratings to compare against" from reading as "no
# critical lines".
RATINGS_ANCHOR = "\tif not np.any(rated):\n\t\traise ValueError("
RATINGS_PLANTED = "\tif False:  # canary: the refusal removed\n\t\traise ValueError("


def _gate_exit_code(test: str) -> int:
	"""Exit code of one gate test, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_hours_gate_catches_a_snapshot_count():
	"""The shipped defect class: the count printed under a column headed "Hours".

	`planted` asserts the anchor is present before mutating, so a canary whose
	target has moved fails loudly instead of passing against untouched code.
	"""
	test = "the_hours_are_hours_and_not_a_snapshot_count"
	assert _gate_exit_code(test) == 0, f"{test} does not pass on the shipped tree"
	with planted(FLOW, HOURS_ANCHOR, HOURS_PLANTED):
		assert _gate_exit_code(test) != 0, (
			"a kernel returning the snapshot count where the field says hours "
			"still passed, so the unit trap is unguarded"
		)
	assert _gate_exit_code(test) == 0, "the restore was not proven"


def test_the_no_ratings_gate_catches_a_silent_empty_ranking():
	"""A network with nothing rated must not return an empty critical-line list."""
	test = "a_network_with_no_rated_branch_is_refused"
	assert _gate_exit_code(test) == 0, f"{test} does not pass on the shipped tree"
	with planted(FLOW, RATINGS_ANCHOR, RATINGS_PLANTED):
		assert _gate_exit_code(test) != 0, (
			"a network whose every branch lacks a rating returned an empty "
			"ranking instead of refusing, so 'no critical lines' and 'nothing "
			"to compare against' are the same finding"
		)
	assert _gate_exit_code(test) == 0, "the restore was not proven"
