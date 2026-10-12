# SPDX-License-Identifier: MIT
"""Canary for the required-section producer gates.

Two gates in `test_reporting_producers.py` are pinned rather than derived, and
each needs a canary that proves it can fail:

``test_a_required_section_with_no_producer_is_recorded`` was a tautology: it
built ``required & set(UNPRODUCED)`` and then asserted each member was in
``UNPRODUCED``, which is true by construction and cannot fail. It is now pinned
to a map of cadence to the one required section it cannot generate without.

``test_each_cadence_declares_exactly_one_required_section`` pins the shape
`UNPRODUCED`'s summary paraphrases. That summary said "four" where the measured
count is five, because it was retyped rather than derived -- so the gate that
makes the count structural needs the same proof as the map.

**A canary is what proves a pinned assertion is a gate.** A pinned assertion is
only a check if a change to the thing it pins fails it. Each test below plants
the change its gate exists to notice and runs the real gate in a fresh
interpreter, because the mutations are source edits and the cadence modules are
imported at collection.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

PRODUCERS_PY = REPO / "src" / "alea" / "reporting" / "producers.py"
DAILY_PY = REPO / "src" / "alea" / "reporting" / "daily.py"

GATE_FILE = "tests/ci/test_reporting_producers.py"
UNPRODUCED_GATE = "test_a_required_section_with_no_producer_is_recorded"
SHAPE_GATE = "test_each_cadence_declares_exactly_one_required_section"


def _gate_exit_code(test: str) -> int:
	"""Exit code of one gate in this module, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
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
	assert _gate_exit_code(UNPRODUCED_GATE) == 0, (
		"the required-producer gate does not pass on the shipped tree"
	)

	with planted(PRODUCERS_PY, target, ""):
		assert _gate_exit_code(UNPRODUCED_GATE) != 0, (
			"the gate passed with a required section removed from `UNPRODUCED` and "
			"the pinned map unchanged; it is derived from the register rather than "
			"checking it, so it cannot notice a cadence whose generatability moved"
		)

	assert _gate_exit_code(UNPRODUCED_GATE) == 0, "the restore was not proven"


def test_the_shape_gate_catches_a_cadence_gaining_a_second_required_section():
	"""The defect: the count the summary states stops matching the set.

	`UNPRODUCED`'s prose said four required sections and named four, dropping
	the daily cadence's -- and the count was retyped rather than derived, which
	is how it drifted. A second required section on the daily cadence is exactly
	the change that would make "one per cadence" false, so the gate that pins
	the shape must fail against it. Marking the optional `generation_mix`
	required is the minimal such change.
	"""
	target = '\t\tunit="MW",\n\t\ttable_title="Scheduled generation",\n'
	replacement = '\t\tunit="MW",\n\t\trequired=True,\n\t\ttable_title="Scheduled generation",\n'
	assert target in DAILY_PY.read_text(), (
		"the canary target moved; `generation_mix` is no longer the daily section "
		"this canary mutates, so the canary would be a no-op"
	)
	assert _gate_exit_code(SHAPE_GATE) == 0, "the shape gate does not pass on the shipped tree"

	with planted(DAILY_PY, target, replacement):
		assert _gate_exit_code(SHAPE_GATE) != 0, (
			"the shape gate passed with a cadence carrying two required sections; "
			"it cannot notice the change that makes the register's own count wrong"
		)

	assert _gate_exit_code(SHAPE_GATE) == 0, "the restore was not proven"
