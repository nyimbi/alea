# SPDX-License-Identifier: MIT
"""Canary for `test_the_default_target_reaches_every_wired_section`.

The gate asserts that every section which is both produced and projected has a
path from `rule all` to its *projection* -- that the default target delivers it,
not merely that a rule could. It exists because seven sections satisfied every
register in the tree while no default target ran them: `PRODUCERS` named a
producer, `PROJECTED` named a projection, `snakemake <stage>` built either, and
`snakemake all` built neither, so `alea report weekly` raised "no artefact" on a
tree that read as fully wired. `week_ahead` was among them and is the weekly
cadence's only `required=True` section, so that cadence could not be generated
at all.

**Why the mutation is a Snakefile edit.** The gate reads the resolved DAG, and
the DAG is built from the Snakefile. Planting the defect in the file the gate
reads is what proves the gate notices it; mutating the assertion would prove
only that an assertion can fail.

**Why the mutation removes the projection and not the build.** The first version
of the gate accepted either half, and this canary is how that was found: removing
`processed("week_ahead")` while the projection stayed passed, because a
projection pulls its build as an input and the section is still delivered. The
predicate was narrowed to the projection, which is the half that actually fails
to deliver. Removing the *projection* is therefore the mutation that must fail,
and removing the build is a mutation that must **not** -- both are asserted here,
because a gate that failed on the harmless one would be scoped to the wrong
half of the pair.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

SNAKEFILE = REPO / "Snakefile"
GATE_FILE = "tests/ci/test_orchestration_workflow.py"
GATE = "test_the_default_target_reaches_every_wired_section"

#: `week_ahead`'s two entries in `rule all`, as they are spelled. The gate's
#: subject, and the section whose absence made the weekly report unbuildable.
BUILD = '\t\tprocessed("week_ahead"),\n'
DELIVERY = '\t\treport_artefact("weekly", "planning/outlook/{date}.parquet"),\n'


def _gate_exit_code() -> int:
	"""Exit code of the gate, run in a fresh interpreter.

	A subprocess because the mutation is a source edit: the gate shells out to
	`snakemake`, which reads the Snakefile from disk, so an in-process run would
	be reading whatever the parent imported.
	"""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", GATE],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_reachability_gate_catches_a_wired_section_with_no_delivery():
	"""The defect: the projection is in no default target.

	Every register still says the section is produced and delivered, and
	`snakemake project_week_ahead` still builds it -- but the default target
	never runs it, so a fresh `snakemake all` leaves the dated path absent and
	`alea report weekly` raises.
	"""
	assert DELIVERY in SNAKEFILE.read_text(), (
		"the canary target moved; `week_ahead`'s projection is no longer in "
		"`rule all` in the form this canary expects, so the canary would be a "
		"no-op"
	)
	assert _gate_exit_code() == 0, "the reachability gate does not pass on the shipped tree"

	with planted(SNAKEFILE, DELIVERY, ""):
		assert _gate_exit_code() != 0, (
			"the reachability gate passed with `week_ahead`'s projection removed "
			"from `rule all`; it is reading the section's presence rather than "
			"the delivery's reachability, so it cannot notice the defect it "
			"exists for"
		)

	assert _gate_exit_code() == 0, "the restore was not proven"


def test_the_reachability_gate_accepts_a_build_with_no_separate_entry():
	"""The harmless mutation: the build is gone and the projection remains.

	A projection declares its stage's processed artefact as an input, so
	Snakemake pulls the build through it and the section is still delivered.
	The gate must *not* fail here -- a predicate that demanded both halves would
	be scoped wider than the defect, and the pressure that creates is to add the
	line back to silence a check rather than because anything was broken.

	This half is what narrowed the gate's predicate from "either half" to "the
	projection", and it is asserted so the narrowing cannot be undone silently.
	"""
	assert BUILD in SNAKEFILE.read_text(), (
		"the canary target moved; `week_ahead`'s build is no longer in `rule "
		"all`, so the canary would be a no-op"
	)

	with planted(SNAKEFILE, BUILD, ""):
		assert _gate_exit_code() == 0, (
			"the reachability gate failed with only the build removed; the "
			"projection still pulls it as an input, so the section is still "
			"delivered and a failure here means the gate is scoped to the "
			"harmless half of the pair"
		)

	assert _gate_exit_code() == 0, "the restore was not proven"
