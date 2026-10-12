# SPDX-License-Identifier: MIT
"""Canary for `test_every_registered_stage_is_a_rule_or_a_named_exception`.

The gate exists because `test_every_stage_has_a_snakemake_rule` checks one
direction only: the eleven declared stages have rules. Nothing checked the
converse, so a builder could register, be reachable from `alea build`, and be
run by no rule -- which is indistinguishable from a working stage when you read
the registry.

Five stages were in exactly that state. The canary plants a sixth: a `@stage`
decorator in a module `_REGISTRATION_MODULES` already imports, so it registers
and is in neither the workflow's stage list nor the named exceptions.

**The gate runs as the real gate**, in a fresh interpreter. The registry is
populated by decorators at import, so a canary that read `_BUILDERS` in-process
after importing the module itself would be asserting its own import -- the
vacuous fixture `tests/ci/test_orchestration_registry.py` documents at length.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

# A module already in `_REGISTRATION_MODULES`, so a decorator added here
# registers without touching the import list -- which is what makes the canary
# about the *gate* and not about `_REGISTRATION_MODULES`.
QUALITY_SERVICE = REPO / "src" / "alea" / "quality" / "service.py"

GATE = "tests/ci/test_orchestration_workflow.py"
TEST = "registered_stage_is_a_rule_or_a_named_exception"

ANCHOR = '@stage("quality_validation")\n'
PLANTED = (
	'@stage("a_stage_with_no_rule")\n'
	"def _canary_stage(config, out, context):\n"
	'\t"""Canary: registers, has no rule, is in no named exception."""\n'
	"\treturn context.provenance\n"
	"\n\n"
	'@stage("quality_validation")\n'
)


def _gate_exit_code() -> int:
	"""Exit code of the named gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE, "-q", "-x", "-k", TEST],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_gate_catches_a_registered_stage_no_rule_runs():
	"""The shipped defect: a stage the registry holds and the workflow ignores.

	The gate must fail on it. A stage that registers and is run by nothing is a
	builder nobody invokes, and the registry cannot tell it from one a rule
	drives -- which is the whole reason the gate reads the registry and the rule
	files together.
	"""
	assert ANCHOR in QUALITY_SERVICE.read_text(encoding="utf-8"), (
		f"canary target not found in {QUALITY_SERVICE.name}: {ANCHOR!r}. The gate "
		f"may already be reading a source that has moved, in which case this "
		f"canary is a no-op that reports a blind gate."
	)
	assert _gate_exit_code() == 0, f"{TEST} does not pass on the shipped tree"
	with planted(QUALITY_SERVICE, ANCHOR, PLANTED):
		assert _gate_exit_code() != 0, (
			"a stage that registers with no rule and no named exception still "
			"passed, so a builder the workflow never runs is invisible"
		)
	assert _gate_exit_code() == 0, "the restore was not proven"
