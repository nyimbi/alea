# SPDX-License-Identifier: MIT
"""Canary for the capture-rate stage's idempotence gate.

`test_serving_capture_rates.py`'s `test_the_stage_skips_a_second_run_on_the_same_network`
is `02-data-pipeline.md` §4.2's `test_stage_idempotent`, applied to the one
publish stage that resolves its own input. It takes no declared ``--input`` from
its rule, so `build_stage`'s central check can never fire and the stage must
call `skip_if_current` with the digest it read. A stage that omits that call
re-solves and rewrites on every `alea build` -- the defect the pipeline module
documents as "every `alea build` rebuilt" -- and a single run cannot see it.

**The canary runs the real gate in a fresh interpreter.** The mutation is a
source edit to `publish/stages.py`, and the stage module is imported at
collection, so an in-process canary would assert against the module it already
holds rather than the one on disk.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

PUBLISH_STAGES_PY = REPO / "src" / "alea" / "publish" / "stages.py"

GATE_FILE = "tests/ci/test_serving_capture_rates.py"
GATE_TEST = "test_the_stage_skips_a_second_run_on_the_same_network"


def _gate_exit_code() -> int:
	"""Exit code of the idempotence gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", GATE_TEST],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_idempotence_gate_catches_a_stage_that_never_skips():
	"""The defect: the stage rebuilds every run because it never checks.

	Removing the `skip_if_current` call is exactly the defect the gate exists to
	catch -- a self-resolving stage that re-solves on every invocation. The gate
	must fail against it, or it is a test that would pass on a stage that does no
	idempotence work at all.
	"""
	target = (
		"\texisting = skip_if_current(out, inputs, stage_name=\"market_capture_rates\", "
		"logger=context.logger)\n"
		"\tif existing is not None:\n"
		"\t\treturn existing\n"
	)
	assert target in PUBLISH_STAGES_PY.read_text(), (
		"the canary target moved; the capture-rate stage no longer calls "
		"`skip_if_current` where this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code() == 0, "the idempotence gate does not pass on the shipped tree"

	with planted(PUBLISH_STAGES_PY, target, ""):
		assert _gate_exit_code() != 0, (
			"the idempotence gate passed with the stage's skip check removed; it "
			"cannot tell a stage that skips from one that re-solves every run"
		)

	assert _gate_exit_code() == 0, "the restore was not proven"
