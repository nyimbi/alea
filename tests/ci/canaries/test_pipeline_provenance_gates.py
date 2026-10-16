# SPDX-License-Identifier: MIT
"""Canary: `02-data-pipeline.md` §6 criteria 5 and 7.

Both gates live in `tests/ci/test_pipeline_provenance.py` and both were written
because the exit-criteria cells that named them said "Provenance test" -- a
description, not a name -- so the register could not see them at all.

**Criterion 5, "every processed artefact has provenance with a checksum."**
``test_every_artefact_a_stage_writes_has_provenance_with_a_checksum`` enumerates
what a stage actually wrote. The defect it exists for was live: `build_topology`
writes a GeoJSON beside its Parquet and only the Parquet went through
`write_stage`, so `topology.geojson` sat on disk with no sidecar -- an artefact
`read_artefact` refuses. The canary removes the sidecar write and the gate must
fail, on the GeoJSON, which is the artefact the hardcoded list would have missed.

**Criterion 7, "CRITICAL-tier proxies carry `uncertainty_basis=\"proxy\"`".**
``test_a_critical_tier_national_total_carries_a_proxy_basis`` runs the shipped
`demand_national` stage over a Burundi export. The defect was live too: the
stage's notes claimed a CRITICAL-tier total is a proxy and no code branched on
the tier, so Burundi's total was written `basis=measured, uncertainty=0.0` --
a proxy published as a measurement. The canary blinds the tier branch and the
gate must fail.

**Why a probe.** Both mutations are source edits to `alea.io.stages`, which this
interpreter already holds. A reload would be the only thing standing between the
canary and a module that never saw the defect, so each gate is run by node id in
a fresh interpreter -- which also makes this a canary of the gate rather than of
a copy of it.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

STAGES = REPO / "src" / "alea" / "io" / "stages.py"

_GATE_5 = """
import sys
import pytest

sys.exit(pytest.main(["-q", "-p", "no:randomly",
    "tests/ci/test_pipeline_provenance.py"
    "::test_every_artefact_a_stage_writes_has_provenance_with_a_checksum"]))
"""

_GATE_7 = """
import sys
import pytest

sys.exit(pytest.main(["-q", "-p", "no:randomly",
    "tests/ci/test_pipeline_provenance.py"
    "::test_a_critical_tier_national_total_carries_a_proxy_basis"]))
"""


def test_the_geojson_sidecar_is_the_gate():
	"""Remove the GeoJSON's sidecar write; criterion 5's gate must fail.

	The mutation is the deletion of the `_write_provenance_sidecar(geojson_out,
	provenance)` line -- disjoint from what the gate looks for, which is a
	sidecar's existence, not the spelling of the call that writes it. A mutation
	that merely renamed the call would leave a sidecar standing and the gate
	would pass, proving nothing.
	"""
	target = "\t_write_provenance_sidecar(geojson_out, provenance)\n"
	assert target in STAGES.read_text(), "canary target not found: no GeoJSON sidecar write"

	assert probe_exit_code(_GATE_5) == 0, (
		"criterion 5's gate does not pass on the shipped tree, so the canary "
		"below would prove nothing about the sidecar"
	)

	with planted(STAGES, target, "\t# canary: the GeoJSON sidecar is not written\n"):
		assert probe_exit_code(_GATE_5) != 0, (
			"the gate passed with the GeoJSON's sidecar removed; it is not "
			"enumerating the artefacts the stage actually wrote, and an artefact "
			"no reader can verify would ship unnoticed"
		)

	# Restored: the gate passes again.
	assert probe_exit_code(_GATE_5) == 0, "the restore did not put the sidecar write back"


def test_the_tier_branch_is_the_gate():
	"""Blind the CRITICAL-tier branch; criterion 7's gate must fail.

	The mutation makes the `if proxy_countries:` branch unreachable, so a
	Burundi total is written `basis=measured` -- the shipped defect in its exact
	form. It is disjoint from what the gate asserts (the recorded basis), not a
	reword of it.
	"""
	target = '\tif proxy_countries:\n\t\tparameters["proxy_countries"] = proxy_countries\n'
	assert target in STAGES.read_text(), "canary target not found: no CRITICAL-tier branch"

	assert probe_exit_code(_GATE_7) == 0, (
		"criterion 7's gate does not pass on the shipped tree, so the canary "
		"below would prove nothing about the tier branch"
	)

	with planted(STAGES, target, '\tif False:  # canary: the tier branch disabled\n'):
		assert probe_exit_code(_GATE_7) != 0, (
			"the gate passed with the CRITICAL-tier branch disabled; a Burundi "
			"national total would be published as a measurement"
		)

	assert probe_exit_code(_GATE_7) == 0, "the restore did not put the tier branch back"
