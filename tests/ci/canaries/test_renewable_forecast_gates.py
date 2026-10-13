# SPDX-License-Identifier: MIT
"""Canary for the stage register and the two workflow files that must agree.

Three gates in `test_orchestration_workflow.py` read a *literal copy* of the
workflow's own declarations -- ``STAGES`` mirrors the rule files, ``SUFFIXES``
mirrors `rules/common.smk`, ``PROJECTIONS``/``PROJECTION_PATTERNS`` mirror the
projection rules -- and a copy that drifts in step with the file it copies
agrees with itself while agreeing with nothing else. That is the failure the
``week_ahead`` suffix entry shipped: every gate in the file passed, and
`snakemake -n` exited on ``KeyError: 'market_summary'`` inside ``processed()``.

So the canaries here plant a defect in the *source of truth* and assert the
gate fails: a registered stage the workflow has no rule for, a stage whose
suffix `rules/common.smk` does not carry, and a projection whose pattern the
section does not declare. Each runs the gate as the real gate, in a fresh
interpreter, because every one of them imports a module and reads a file.

**The mutation must be disjoint from what the gate looks for.** Renaming a
stage to another name the workflow *also* declares leaves the gate satisfied --
a canary that is a superstring of the asserted text is a canary that did not
run. Each name planted below appears nowhere else in the tree.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

GATE = "tests/ci/test_orchestration_workflow.py"

ARRAYS = REPO / "src" / "alea" / "planning" / "arrays.py"
COMMON = REPO / "rules" / "common.smk"
REPORTING_SMK = REPO / "rules" / "reporting.smk"


def _gate_exit_code(test: str) -> int:
	"""Exit code of one named gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_gate_catches_a_registered_stage_with_no_rule():
	"""A ``@stage`` that registers and that no rule file declares.

	``test_every_registered_stage_is_a_rule_or_a_named_exception`` is the gate.
	The name planted is in neither ``STAGES`` nor the named exceptions, so the
	gate's two directions both miss it and it must fail on the registry.
	"""
	anchor = '@stage("renewable_forecast")\n'
	assert anchor in ARRAYS.read_text(encoding="utf-8"), (
		"the canary target moved; a patch that does not apply is a canary that "
		"did not run"
	)
	planted_stage = (
		'@stage("a_canary_stage_no_rule_declares")\n'
		"def _canary_stage(config, out, context):\n"
		'\t"""Canary: registers, has no rule, is in no named exception."""\n'
		"\treturn context.provenance\n"
		"\n\n"
		+ anchor
	)
	with planted(ARRAYS, anchor, planted_stage):
		code = _gate_exit_code("registered_stage_is_a_rule_or_a_named_exception")
	assert code != 0, (
		"a registered stage with no rule did not fail the gate; the gate cannot "
		"see the direction it was written for"
	)


def test_the_gate_catches_a_stage_missing_from_the_workflow_s_suffix_map():
	"""A suffix entry removed from `rules/common.smk` while the test's copy keeps it.

	This is the ``week_ahead``/``market_summary`` defect exactly, and the gate
	that catches it is ``test_the_workflow_parses`` -- the one that runs the
	parser rather than reading the text. The suffix removed belongs to a stage
	whose ``processed()`` call the workflow makes, so the parse raises
	``KeyError`` inside the helper.
	"""
	anchor = '\t"renewable_forecast": ".parquet",\n'
	assert anchor in COMMON.read_text(encoding="utf-8"), (
		"the canary target moved; a patch that does not apply is a canary that "
		"did not run"
	)
	with planted(COMMON, anchor, ""):
		code = _gate_exit_code("the_workflow_parses")
	assert code != 0, (
		"a suffix missing from `rules/common.smk` did not fail the parse gate; "
		"this is the defect that shipped, and every text-reading gate passed it"
	)


def test_the_gate_catches_a_projection_writing_a_path_no_section_declares():
	"""A projection rule whose ``report_artefact`` names a directory no section reads.

	``test_a_projection_writes_the_pattern_its_section_declares`` compares the
	rule's declared output against the section's own ``artefact`` string, so a
	directory that matches no section must fail it. The path planted is one no
	cadence declares -- ``weather/nowhere`` rather than ``weather/renewables``.
	"""
	anchor = 'report_artefact("weekly", "weather/renewables/{date}.parquet")'
	assert anchor in REPORTING_SMK.read_text(encoding="utf-8"), (
		"the canary target moved; a patch that does not apply is a canary that "
		"did not run"
	)
	with planted(
		REPORTING_SMK, anchor, 'report_artefact("weekly", "weather/nowhere/{date}.parquet")'
	):
		code = _gate_exit_code("a_projection_writes_the_pattern_its_section_declares")
	assert code != 0, (
		"a projection writing a directory no section declares did not fail the "
		"gate; the comparison is between two spellings that both moved"
	)
