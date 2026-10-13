# SPDX-License-Identifier: MIT
"""Canary for `test_no_blocker_claims_a_source_is_absent_when_the_register_holds_it`.

The gate exists because `climate_scenarios` recorded that "the register holds no
climate projection source" while `cmip6` sat in the register with a working
fetcher and this slug as its declared ``target``. Four entries in this register
have now named the wrong missing thing, so the gate is over the class.

**The first draft of the gate was itself the defect it was written for.** It
looked for a registered source id spelled inside the blocker and skipped any
blocker naming none -- which is every blocker that *denies* a source exists,
including the one being fixed. A gate whose trigger is the defect's own wording
passes over the defect, and the canary below is what makes that visible: the
planted text carries no source id at all, only the denial.

The mutation is disjoint from what the gate reads -- it removes the sentence
rather than rewording it, so the phrase the gate keys on is *absent* rather than
merely different.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

GATE = "tests/ci/test_reporting_producers.py"
TEST = "no_blocker_claims_a_source_is_absent_when_the_register_holds_it"

PRODUCERS = REPO / "src" / "alea" / "reporting" / "producers.py"

#: The planted replacement, completing the sentence the gate must reject. It
#: names no source id at all -- which is the shape of the original defect, and
#: the reason the gate's first draft passed over it.
PLANTED_FULL = (
	'"No climate projection source exists in the register and no code "\n'
	'\t\t\t"reads one; the section has neither a reader nor a writer."'
)
CURRENT_FULL = (
	'"A modelling gap, not a fetch one. `cmip6` is registered, its declared "\n'
	'\t\t\t"``target`` is this slug, and `alea.io.fetchers` fetches its ESGF "\n'
	'\t\t\t"dataset inventory -- so the source the entry above used to say was "\n'
	'\t\t\t"missing has been there all along. What does not exist is everything "\n'
	'\t\t\t"between that inventory and the section: a producer must name a "\n'
	'\t\t\t"dataset per scenario, download it (terabytes, which the fetcher\'s own "\n'
	'\t\t\t"docstring puts deliberately outside the pipeline), downscale it to "\n'
	'\t\t\t"the network\'s snapshots, and re-solve for each. The section\'s "\n'
	'\t\t\t"`Scenario`, `System cost` and `Reliability` columns come from the "\n'
	'\t\t\t"last step and nothing runs it."'
)


def _gate_exit_code() -> int:
	"""Exit code of the gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE, "-q", "-x", "-k", TEST],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_gate_rejects_a_denial_that_names_no_source():
	"""The shipped defect: a blocker denying a source the register holds.

	The planted sentence names no source id, which is exactly why the gate's
	first draft let it through. Keyed on the source's ``target``, it cannot.
	"""
	assert CURRENT_FULL in PRODUCERS.read_text(encoding="utf-8"), (
		"the canary target moved; a patch that does not apply is a canary that "
		"did not run"
	)
	with planted(PRODUCERS, CURRENT_FULL, PLANTED_FULL):
		code = _gate_exit_code()
	assert code != 0, (
		"a blocker denying a source that declares this section as its target did "
		"not fail the gate; this is the defect the gate was written for"
	)


def test_the_gate_accepts_the_shipped_blocker():
	"""The other direction, so the gate is not merely always-failing.

	A gate that fails on every input is one its operator disables. The shipped
	entry names the source and states the real gap, and must pass untouched.
	"""
	assert _gate_exit_code() == 0, (
		"the gate fails on the tree as shipped; it is refusing text that is "
		"correct, which is the failure mode that teaches people to bypass it"
	)
