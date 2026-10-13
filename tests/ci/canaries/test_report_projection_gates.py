# SPDX-License-Identifier: MIT
"""Canaries for the projection registers and the workflow gate over them.

Three gates were added when `capacity_update`'s projection closed the gap that
`reporting/producers.py` had been describing rather than measuring, and each is
pinned rather than derived -- so each needs a canary that proves it can fail:

``test_the_projected_registers_partition_the_produced_sections`` pins that every
slug in ``PRODUCERS`` is in exactly one of ``PROJECTED``/``UNPROJECTED``. It
exists because ``PRODUCERS`` alone recorded a *function* and said nothing about
whether a report could open the section -- measured 2026-10-13, when the rule
exited 0 and `alea report monthly` exited 1 with ``ReportDataError: no
artefact``.

``test_every_projected_section_has_a_rule_and_a_dvc_stage`` pins that a
``PROJECTED`` entry names a rule both workflow files declare. That is the
register's claim about *delivery*, so a name with no rule behind it is the
original defect restated one level down.

``test_a_projection_writes_the_pattern_its_section_declares`` pins that the
rule's declared output is the section's own ``artefact`` pattern (it lives in
`test_orchestration_workflow.py`, and this file canaries it from here because the
canaries directory is where every gate's proof is collected). The defect it
exists for is the one that was measured: a producer writing
``data/processed/`` while the reader looked under ``results/``, which is a
section that renders in CI and is absent in production.

**Why the mutations are edits to the shipped files and not to the tests.** Each
gate reads source text -- the register, the rule files, `dvc.yaml` -- so planting
the defect in the artefact the gate reads is what proves the gate notices it. A
canary that mutated the assertion would prove only that the assertion can fail.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

PRODUCERS_PY = REPO / "src" / "alea" / "reporting" / "producers.py"
REPORTING_SMK = REPO / "rules" / "reporting.smk"

PRODUCER_GATE_FILE = "tests/ci/test_reporting_producers.py"
PARTITION_GATE = "test_the_projected_registers_partition_the_produced_sections"
DELIVERY_GATE = "test_every_projected_section_has_a_rule_and_a_dvc_stage"
WORKFLOW_GATE_FILE = "tests/ci/test_orchestration_workflow.py"
PATTERN_GATE = "test_a_projection_writes_the_pattern_its_section_declares"

#: The one `PROJECTED` entry, as it is spelled in the register. Both the
#: partition canary and the delivery canary mutate this line, in different ways:
#: deleting it is a produced section nobody has asked the delivery question
#: about, and renaming its rule is a projection claim with nothing behind it.
PROJECTED_ENTRY = '\t\t"capacity_update": "project_capacity_update",\n'


def _gate_exit_code(path: str, test: str) -> int:
	"""Exit code of one gate, run in a fresh interpreter.

	A subprocess because the mutations are source edits: `producers.py` is
	imported at collection, so an in-process canary would run the gate against
	the module as it was when pytest started.
	"""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", path, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_partition_gate_catches_a_produced_section_leaving_the_register():
	"""The defect: a slug in `PRODUCERS` and in neither projection register.

	That is the state the whole module was in before `capacity_update`'s
	projection: a producer named, a rule that exits 0, and a dated path nothing
	writes. Deleting the `PROJECTED` entry is exactly that state, so the gate
	must fail against it -- otherwise `PRODUCERS` keeps meaning "a function
	exists" and the register keeps overstating coverage.
	"""
	assert PROJECTED_ENTRY in PRODUCERS_PY.read_text(), (
		"the canary target moved; `capacity_update` is no longer a `PROJECTED` "
		"entry in the form this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(PRODUCER_GATE_FILE, PARTITION_GATE) == 0, (
		"the partition gate does not pass on the shipped tree"
	)

	with planted(PRODUCERS_PY, PROJECTED_ENTRY, ""):
		assert _gate_exit_code(PRODUCER_GATE_FILE, PARTITION_GATE) != 0, (
			"the partition gate passed with a produced section in neither "
			"projection register; it is derived from `PRODUCERS` rather than "
			"checking it, so it cannot notice a section whose delivery nobody "
			"has asked about"
		)

	assert _gate_exit_code(PRODUCER_GATE_FILE, PARTITION_GATE) == 0, (
		"the restore was not proven"
	)


def test_the_delivery_gate_catches_a_projected_entry_with_no_rule():
	"""The defect: the register says a projection runs and no rule declares it.

	Renaming the rule in the register rather than deleting the entry is the
	sharper mutation: the slug is still recorded as delivered, so only the claim
	about *what* delivers it is false. A gate that matched the slug, or that
	checked the register against itself, would pass. This one reads the rule
	files and `dvc.yaml`, which is why it must fail.
	"""
	assert PROJECTED_ENTRY in PRODUCERS_PY.read_text(), (
		"the canary target moved; the canary would be a no-op"
	)
	assert _gate_exit_code(PRODUCER_GATE_FILE, DELIVERY_GATE) == 0, (
		"the delivery gate does not pass on the shipped tree"
	)

	renamed = '\t\t"capacity_update": "project_capacity_update_renamed",\n'
	with planted(PRODUCERS_PY, PROJECTED_ENTRY, renamed):
		assert _gate_exit_code(PRODUCER_GATE_FILE, DELIVERY_GATE) != 0, (
			"the delivery gate passed with a `PROJECTED` entry naming a rule no "
			"`.smk` file declares; a name with no rule behind it is the original "
			"defect -- a function that exists and nothing that runs it"
		)

	assert _gate_exit_code(PRODUCER_GATE_FILE, DELIVERY_GATE) == 0, (
		"the restore was not proven"
	)


def test_the_workflow_gate_catches_a_rule_writing_the_wrong_directory():
	"""The defect: the rule's output is not the directory the section reads.

	The pattern the rule passes to `report_artefact` is the section's own
	``artefact`` string, and `report_artefact` turns it into the directory
	Snakemake tracks. Change the pattern and the projection writes a directory
	no reader opens -- which is the measured defect, one level down: the rule
	still runs, still exits 0, and the section is still absent.

	The mutation keeps the shape (`planning/<dir>/{date}.parquet`) and moves only
	the directory, because that is the change a careless edit makes and the one
	a gate matching "a pattern is present" would miss.
	"""
	target = 'report_artefact("monthly", "planning/capacity/{date}.parquet")'
	replacement = 'report_artefact("monthly", "planning/capacity_typo/{date}.parquet")'
	assert target in REPORTING_SMK.read_text(), (
		"the canary target moved; `rules/reporting.smk` no longer declares the "
		"capacity projection's output in the form this canary expects, so the "
		"canary would be a no-op"
	)
	assert _gate_exit_code(WORKFLOW_GATE_FILE, PATTERN_GATE) == 0, (
		"the workflow gate does not pass on the shipped tree"
	)

	with planted(REPORTING_SMK, target, replacement):
		assert _gate_exit_code(WORKFLOW_GATE_FILE, PATTERN_GATE) != 0, (
			"the workflow gate passed with the rule writing "
			"`planning/capacity_typo`, which no cadence declares and no report "
			"reads. A rule that exits 0 and lands its output where nothing looks "
			"is exactly the defect this gate exists to catch"
		)

	assert _gate_exit_code(WORKFLOW_GATE_FILE, PATTERN_GATE) == 0, (
		"the restore was not proven"
	)
