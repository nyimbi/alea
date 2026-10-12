# SPDX-License-Identifier: MIT
"""Canary: `10-layer7-scanning.md` §2 -- ``extracted_at`` names one instant.

This is the canary for
``test_the_default_extraction_time_is_timezone_aware_utc`` and
``test_a_naive_extraction_time_is_refused_not_assumed_utc``, the pair that
guards the signal's extraction timestamp.

The defect was the default: ``Field(default_factory=datetime.now)``, naive, so
silently the host's local time. It is invisible in the obvious test -- a signal
built on a UTC host has the right *instant* -- which is why the gate asserts
awareness rather than the value. Two hosts in different zones sort the same
corpus differently, and the API writes this field to SQLite as ``isoformat()``
and orders rows by it as a string.

The canary plants the naive default back and watches the gate fail, then
asserts the second half: with the default naive, a caller-supplied *aware*
timestamp is still accepted. A gate that only caught the default would miss the
same defect arriving from ``datetime.fromisoformat`` on a stored row, which is
the path it actually travels.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

MODELS = REPO / "src" / "alea" / "signals" / "models.py"
GATE = "tests/ci/test_signal_contract.py"

AWARE = "test_the_default_extraction_time_is_timezone_aware_utc"
REFUSED = "test_a_naive_extraction_time_is_refused_not_assumed_utc"

# The naive default, exactly as it was found.
TARGET = "\textracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))\n"
BLIND = "\textracted_at: datetime = Field(default_factory=datetime.now)\n"


def _gate_exit_code(node: str) -> int:
	"""Run one gate in a fresh interpreter and return its exit code.

	A fresh process, not an in-process call: the mutation is to a source file
	whose module the canary has already imported, so only a new interpreter
	reads the planted default.
	"""
	result = subprocess.run(
		[sys.executable, "-m", "pytest", "-q", f"{GATE}::{node}"],
		cwd=REPO,
		capture_output=True,
		text=True,
		check=False,
	)
	return result.returncode


def test_the_timestamp_gate_notices_a_naive_default():
	"""Restore ``datetime.now`` as the default; the awareness gate must fail."""
	assert _gate_exit_code(AWARE) == 0, (
		"the awareness gate is already failing on a clean tree; this canary "
		"could not attribute the failure it is about to cause"
	)
	assert _gate_exit_code(REFUSED) == 0, (
		"the refusal gate is already failing; the second half of this canary "
		"would be unreadable"
	)

	with planted(MODELS, TARGET, BLIND):
		assert _gate_exit_code(AWARE) != 0, (
			"the awareness gate passed with a naive default; it does not measure "
			"what it names"
		)
		# The validator is a separate guard from the default, so the naive
		# default does not disable it. This is the half that says the two tests
		# cover two defects rather than one twice.
		assert _gate_exit_code(REFUSED) == 0, (
			"the refusal gate failed with only the default changed, so it is not "
			"testing the caller-supplied path independently"
		)

	# Restored by `planted`, and the gate must clear.
	assert _gate_exit_code(AWARE) == 0, "the awareness gate did not recover after the restore"
