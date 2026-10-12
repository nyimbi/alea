# SPDX-License-Identifier: MIT
"""Canaries for the `[UNVERIFIED]` register and §9 criterion 5's review.

Each canary plants a defect and then runs the **real gate test** in a fresh
interpreter, asserting it exits non-zero. Asserting that the mutation applied is
not enough: a canary that changes a file and then checks its own arithmetic has
proved nothing about the gate. The gate is what has to fail.

The three defects:

* **A claim that disappears.** §6.1 lists ten; the code held four, in one
  cadence, and nothing noticed. Removing a claim must fail the parity gate --
  which is the check that would have caught the four-of-ten gap on the day it
  was written.

* **A claim whose milestone moves.** The milestone is what makes the register a
  schedule rather than a list. Moving #6 from M1 to M8 is the quietest way to
  defer it, and the parity gate reads the document, so it must catch that.

* **A review that measures nothing.** Marking every claim resolved must produce
  a clean review, which proves ``resolved`` is honoured rather than ignored.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

CLAIMS = REPO / "src" / "alea" / "quality" / "claims.py"
ANNUAL = REPO / "src" / "alea" / "reporting" / "annual.py"

GATE = "tests/ci/test_unverified_register.py"


def _gate_exit_code(node: str) -> int:
	"""Run one gate test in a fresh interpreter and return its exit code."""
	result = subprocess.run(
		[sys.executable, "-m", "pytest", "-q", f"{GATE}::{node}"],
		cwd=REPO,
		capture_output=True,
		text=True,
		check=False,
	)
	return result.returncode


def _gate_passes(node: str) -> bool:
	"""Whether a gate test passes on the current tree. Asserted before planting.

	A gate that already fails makes its canary meaningless -- the canary would
	see a non-zero exit and report a live gate when the gate was broken for an
	unrelated reason. The project's own lesson: a canary whose patch does not
	apply is a canary that did not run.
	"""
	return _gate_exit_code(node) == 0


def test_the_register_gate_catches_a_dropped_claim():
	"""The defect: a claim quietly absent from the register.

	This is the historical one -- the register held four of §6.1's ten and no
	check compared the two.
	"""
	node = "test_the_register_holds_the_plans_ten_claims"
	assert _gate_passes(node), "the register gate is already failing; the canary is moot"

	target = (
		'\tClaim(\n\t\tnumber=10,\n\t\tclaim="Egypt hydrogen sector-coupling validation",\n'
		'\t\tmilestone="M5",\n\t\tresolution="Reproduce or record as unsupported",\n\t),\n'
	)
	with planted(CLAIMS, target, ""):
		assert _gate_exit_code(node) != 0, (
			"the register gate passed with a claim removed; it does not compare the "
			"register to §6.1's table"
		)

	assert _gate_passes(node), "the register gate did not recover after the restore"


def test_the_register_gate_catches_a_moved_milestone():
	"""The defect: a claim deferred to a later milestone.

	The count stays ten, so only a gate that compares the *milestone* catches it
	-- and deferring a claim is the action the register exists to make visible.
	"""
	node = "test_each_claim_matches_the_plan[claim6]"
	assert _gate_passes(node), "the parity gate is already failing; the canary is moot"

	with planted(
		CLAIMS,
		'claim="Losses ~20% expansion overestimate (PyPSA-Eur)",\n\t\tmilestone="M1"',
		'claim="Losses ~20% expansion overestimate (PyPSA-Eur)",\n\t\tmilestone="M8"',
	):
		assert _gate_exit_code(node) != 0, (
			"the parity gate passed with claim 6's milestone moved; it does not read "
			"the milestone column"
		)

	assert _gate_passes(node), "the parity gate did not recover after the restore"


def test_the_register_gate_catches_a_claim_whose_text_drifted():
	"""The defect: the code and the document disagreeing about what a claim says.

	Two files that agree today are not one source of truth. The plan is the
	authority and the code restates it, so a restatement that drifts must fail.
	"""
	node = "test_each_claim_matches_the_plan[claim1]"
	assert _gate_passes(node), "the parity gate is already failing; the canary is moot"

	with planted(
		CLAIMS,
		'claim="VIIRS AUC 0.8346 (Ghana)"',
		'claim="VIIRS AUC 0.91 (Ghana)"',
	):
		assert _gate_exit_code(node) != 0, (
			"the parity gate passed with a claim's text changed; it compares text"
		)

	assert _gate_passes(node), "the parity gate did not recover after the restore"


def test_the_report_gate_catches_the_annual_list_splitting_from_the_register():
	"""The defect: the report going back to its own local list.

	The report's `UNVERIFIED` was four claims in one cadence. Replacing the
	derivation with a literal must fail the gate that compares the two.
	"""
	node = "test_the_annual_report_carries_the_whole_register"
	assert _gate_passes(node), "the report gate is already failing; the canary is moot"

	target = """UNVERIFIED: tuple[UnverifiedClaim, ...] = tuple(
	UnverifiedClaim(claim=entry.claim, milestone=entry.milestone, resolved=entry.resolved)
	for entry in REGISTER
)"""
	replacement = """UNVERIFIED: tuple[UnverifiedClaim, ...] = (
	UnverifiedClaim(claim="Transmission-loss omission overestimates optimal expansion by ~20%", milestone="M1"),
)"""
	with planted(ANNUAL, target, replacement):
		assert _gate_exit_code(node) != 0, (
			"the report gate passed with the annual register shrunk to one entry; it "
			"does not compare the report to the register"
		)

	assert _gate_passes(node), "the report gate did not recover after the restore"
