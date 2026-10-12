# SPDX-License-Identifier: MIT
"""Canary: `13-deployment.md` §5.2 -- a perturbed input must move the checksum.

This is the canary for ``test_a_perturbed_input_moves_the_checksum``, §9
criterion 4's gate. The plan states the canary in its own words rather than
describing one:

	**Gate:** a canary perturbs an input and asserts the checksum changes. A
	reproducibility gate that passes on a perturbed input is a gate that is not
	checking anything.

The distinction it draws is the whole reason this file exists. `topology` is
deterministic -- two runs over the same raw payload produce byte-identical
output -- and a test that only asserts *that* passes just as happily when the
artefact's checksum is a constant, because a constant is perfectly reproducible.
Reproducibility is the easy half. Sensitivity is the half that says the value
being compared is a function of the data, and only the pair means anything.

So the canary plants a checksum that does not cover the payload and asserts both
directions at once:

* the sensitivity gate fails, and
* the reproducibility gate **still passes** -- which is the defect the plan
  describes, reproduced rather than asserted.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

ARTEFACTS = REPO / "src" / "alea" / "io" / "artefacts.py"
GATE = "tests/ci/test_deployment_gates.py"

SENSITIVE = "test_a_perturbed_input_moves_the_checksum"
REPRODUCIBLE = "test_the_fixture_stage_reproduces_its_checksum"

# The artefact's checksum, in `write_artefact`. Replacing it with a constant is
# the smallest defect that makes the value independent of the payload -- and it
# is the exact shape the plan warns about, because a constant is reproducible.
TARGET = "\tchecksum = sha256_file(target)\n"
BLIND = '\tchecksum = "0" * 64\n'


def _gate_exit_code(node: str) -> int:
	"""Run one gate test in a fresh interpreter and return its exit code.

	A fresh process, not an in-process call: the mutation is to a source file
	`write_artefact` was already imported from, so a reload would be the only
	thing standing between the canary and a module that never saw the defect.
	"""
	result = subprocess.run(
		[sys.executable, "-m", "pytest", "-q", f"{GATE}::{node}"],
		cwd=REPO,
		capture_output=True,
		text=True,
		check=False,
	)
	return result.returncode


def test_the_sensitivity_gate_catches_a_checksum_that_ignores_its_payload():
	"""Plant a payload-independent checksum; the gate must notice.

	Both halves are asserted under the one mutation. If only the failure were
	asserted, a canary would not distinguish "the gate works" from "the gate is
	broken in some other way"; asserting that the reproducibility gate stays
	green is what pins the failure to the property the plan names.
	"""
	assert _gate_exit_code(SENSITIVE) == 0, (
		"the sensitivity gate is already failing on a clean tree; this canary "
		"could not attribute the failure it is about to cause"
	)
	assert _gate_exit_code(REPRODUCIBLE) == 0, (
		"the reproducibility gate is already failing; the second half of this "
		"canary would be unreadable"
	)

	with planted(ARTEFACTS, TARGET, BLIND):
		assert _gate_exit_code(SENSITIVE) != 0, (
			"the sensitivity gate passed with a checksum that does not cover the "
			"payload it names; perturbing an input did not move the value it "
			"compares"
		)
		assert _gate_exit_code(REPRODUCIBLE) == 0, (
			"the reproducibility gate failed too, so this mutation is not the "
			"defect §5.2 describes: a constant checksum is reproducible, and a "
			"reproducibility-only gate is exactly what the plan says is not "
			"checking anything"
		)

	# Restored by `planted`, and the gate must clear -- otherwise the canary
	# proves a gate can fail but not that it recovers.
	assert _gate_exit_code(SENSITIVE) == 0, (
		"the sensitivity gate did not recover after the restore"
	)
