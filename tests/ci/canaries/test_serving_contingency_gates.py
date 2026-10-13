# SPDX-License-Identifier: MIT
"""Canaries for the gates in `tests/ci/test_serving_contingency.py`.

One gate here is about the *workflow*, not the physics:
``test_the_stage_is_idempotent_through_the_cli``. `02-data-pipeline.md` §4.1
asks every stage to check its output against a recorded manifest and exit
without work if unchanged, and the gate asserts that through the CLI -- the
only entry point the workflow has (AD-5).

**The gate runs as the real gate.** The canary shells out to
``pytest tests/ci/test_serving_contingency.py -k <name>`` in a fresh
interpreter. An inline probe that rebuilt the stage itself would assert the
canary's own reading and say nothing about whether the gate notices.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

PUBLISH_STAGES_PY = REPO / "src" / "alea" / "publish" / "stages.py"

GATE_FILE = "tests/ci/test_serving_contingency.py"


def _gate_exit_code(test: str) -> int:
	"""Exit code of the named gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_idempotency_gate_notices_a_stage_that_rebuilds():
	"""Remove the skip and watch the gate catch a rewritten artefact.

	The gate asserts the published file's mtime does not move between two
	identical CLI runs. This canary plants the defect -- ``skip_if_current``
	returning nothing, so every run re-sweeps and republishes -- which is the
	state every stage was in before the call existed.

	WHY the mtime and not a log line: the assertion this replaced read
	``"skip" in result.output``, which passed only because structlog's default
	factory wrote records to stdout. Moving records to stderr left that
	assertion reading an empty string, so it failed -- but it would have been
	equally blind to a *silent* rebuild had the line been absent for any other
	reason. An mtime is the effect the gate claims, and no log message can
	satisfy it.
	"""
	target = """	existing = skip_if_current(
		out, inputs, stage_name="resilience_contingency", logger=context.logger
	)
	if existing is not None:
		return existing"""
	assert target in PUBLISH_STAGES_PY.read_text(), "canary target not found: the skip is gone"
	old = target
	new = "\texisting = None"
	assert old in PUBLISH_STAGES_PY.read_text(), "canary target not found"
	assert _gate_exit_code("stage_is_idempotent_through_the_cli") == 0, (
		"the gate does not pass on the shipped tree, so the canary proves nothing"
	)
	with planted(PUBLISH_STAGES_PY, old, new):
		assert _gate_exit_code("stage_is_idempotent_through_the_cli") != 0, (
			"a stage that rebuilds against unchanged inputs still passed the gate, so "
			"the gate cannot tell a skip from a silent rewrite"
		)
	assert _gate_exit_code("stage_is_idempotent_through_the_cli") == 0, (
		"the restore was not proven"
	)
