# SPDX-License-Identifier: MIT
"""Canary for the required-section producer gate.

`test_reporting_producers.py`'s `test_a_required_section_with_no_producer_is_recorded`
was a tautology: it built ``required & set(UNPRODUCED)`` and then asserted each
member was in ``UNPRODUCED``, which is true by construction and cannot fail. It
is now pinned to a map of cadence to the one required section it cannot generate
without, so the gate moves when a gap closes or opens.

**The canary is what proves the rewrite.** A pinned assertion is only a gate if
a change to the thing it pins fails it. This plants the change the gate exists
to notice -- a required section leaving `UNPRODUCED` without the map following
-- and runs the real gate in a fresh interpreter, because the mutation is a
source edit and the register is imported at collection.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

PRODUCERS_PY = REPO / "src" / "alea" / "reporting" / "producers.py"

GATE_FILE = "tests/ci/test_reporting_producers.py"
GATE_TEST = "test_a_required_section_with_no_producer_is_recorded"


def _gate_exit_code() -> int:
	"""Exit code of the required-producer gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", GATE_TEST],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_gate_catches_a_required_section_leaving_unproduced():
	"""The defect: a required section gains a producer and the map does not move.

	Deleting a required section's `UNPRODUCED` entry is exactly what closing its
	gap does -- the slug moves to `PRODUCERS` in the same change. If the pinned
	map is not updated with it, the gate must fail, or the map is documentation
	rather than a check. This plants the removal without the move.
	"""
	target = (
		'\t\t"week_ahead": (\n'
		'\t\t\t"A required weekly section with no producer at all: `planning/"\n'
		'\t\t\t"outlook/{date}.parquet` is declared by `reporting/weekly.py` and "\n'
		'\t\t\t"written by nothing. A required section whose artefact is absent "\n'
		'\t\t\t"raises `ReportDataError`, so the weekly report cannot currently be "\n'
		'\t\t\t"generated from the pipeline at all."\n'
		"\t\t),\n"
	)
	assert target in PRODUCERS_PY.read_text(), (
		"the canary target moved; `week_ahead` is no longer an `UNPRODUCED` entry "
		"in the form this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code() == 0, "the required-producer gate does not pass on the shipped tree"

	with planted(PRODUCERS_PY, target, ""):
		assert _gate_exit_code() != 0, (
			"the gate passed with a required section removed from `UNPRODUCED` and "
			"the pinned map unchanged; it is derived from the register rather than "
			"checking it, so it cannot notice a cadence whose generatability moved"
		)

	assert _gate_exit_code() == 0, "the restore was not proven"
