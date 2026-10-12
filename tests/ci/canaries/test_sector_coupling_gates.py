# SPDX-License-Identifier: MIT
"""Canary for the sector-coupling stage's wiring gate.

`test_serving_sector_coupling.py`'s `test_the_stage_runs_and_writes_both_artefacts`
is the gate that proves `@stage("sector_coupling")` is reachable. It survived a
long time unrun because the stage's network resolution was broken in a way no
test could see -- nothing called it. The gate is only worth having if it fails
when the resolution breaks again, so this canary restores the exact defect:
``config.paths.results`` as the network path, which is the results *directory*.

**The canary runs the real gate in a fresh interpreter.** The mutation is a
source edit to `sector/service.py`, and the stage module is imported at
collection, so an in-process canary would assert against the module it already
holds rather than the one on disk.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

SECTOR_SERVICE_PY = REPO / "src" / "alea" / "sector" / "service.py"

GATE_FILE = "tests/ci/test_serving_sector_coupling.py"
RUNS_GATE = "test_the_stage_runs_and_writes_both_artefacts"
REFUSAL_GATE = "test_the_stage_refuses_when_every_sector_is_disabled"


def _gate_exit_code(test: str) -> int:
	"""Exit code of one gate in the module, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_runs_gate_catches_the_directory_as_a_network_path():
	"""The defect: the builder reads `paths.results`, which is a directory.

	This is the original bug. Restoring it must fail the gate, or the gate
	cannot tell a stage that resolves a solved network from one that hands
	``pypsa.Network`` a directory.
	"""
	target = (
		"\tnetwork_dir = resolve(context.parameters.get(\"network_dir\", NETWORK_DIR))\n"
		"\tnamed = context.parameters.get(\"network_path\")\n"
		"\tpath = Path(named) if named else _newest_network(network_dir)\n"
	)
	replacement = '\tpath = Path(config.paths.results)\n'
	assert target in SECTOR_SERVICE_PY.read_text(), (
		"the canary target moved; the stage no longer resolves its network where "
		"this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(RUNS_GATE) == 0, "the runs gate does not pass on the shipped tree"

	with planted(SECTOR_SERVICE_PY, target, replacement):
		assert _gate_exit_code(RUNS_GATE) != 0, (
			"the runs gate passed with the network path restored to "
			"`config.paths.results`, a directory; it cannot tell a stage that "
			"resolves a solved network from one that does not"
		)

	assert _gate_exit_code(RUNS_GATE) == 0, "the restore was not proven"


def test_the_refusal_gate_catches_a_silent_empty_coupling():
	"""The defect: an electricity-only network served as a coupled result.

	Removing the stage's own refusal leaves `write_coupling_artefact`'s bare
	assertion, which fires but says nothing about what turns a sector on. The
	gate asserts the message names the config flag, so removing the stage's guard
	must fail it.
	"""
	target = (
		"\tif not result.report.rows:\n"
		"\t\t# Every sector is off, so the coupling is a no-op on a copy of the base\n"
	)
	assert target in SECTOR_SERVICE_PY.read_text(), (
		"the canary target moved; the stage's no-assets guard is no longer where "
		"this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(REFUSAL_GATE) == 0, "the refusal gate does not pass on the shipped tree"

	with planted(SECTOR_SERVICE_PY, target, "\tif False:\n\t\t# disabled by the canary\n"):
		assert _gate_exit_code(REFUSAL_GATE) != 0, (
			"the refusal gate passed with the stage's own guard disabled; it "
			"cannot tell a refusal that names the flag from a bare assertion"
		)

	assert _gate_exit_code(REFUSAL_GATE) == 0, "the restore was not proven"
