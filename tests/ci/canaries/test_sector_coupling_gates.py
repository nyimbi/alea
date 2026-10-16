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
COUPLING_PY = REPO / "src" / "alea" / "sector" / "coupling.py"

GATE_FILE = "tests/ci/test_serving_sector_coupling.py"
RUNS_GATE = "test_the_stage_runs_and_writes_both_artefacts"
REFUSAL_GATE = "test_the_stage_refuses_when_every_sector_is_disabled"


def _gate_exit_code(test: str, gate_file: str = GATE_FILE) -> int:
	"""Exit code of one gate in a module, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", gate_file, "-q", "-x", "-k", test],
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



# --------------------------------------------------------------------------
# 05-layer2 §7 criterion 7 -- all four Kenya technologies present
# --------------------------------------------------------------------------

KENYA_PORTFOLIO_FILE = "tests/ci/test_sector_units.py"
KENYA_PORTFOLIO_GATE = "test_all_four_kenya_sector_technologies_are_present"

#: The defect: a technology the config asked for never reaches the network.
#:
#: The gate asserts the four Kenya-critical carriers are on the *built network*,
#: so the mutation drops one between the builder and the network. `renewables:`
#: still names all four and the config check passes; the network carries three.
#: That is the defect a config-key check cannot see, and it is why the gate reads
#: `coupled.generators` rather than `config.renewables`.
_HYDRO_DROPPED = (
	"\t\tviews.extend(build.views)",
	"\t\tviews.extend(v for v in build.views if v.carrier != \"hydro\")",
)


def test_the_kenya_portfolio_gate_notices_a_technology_missing_from_the_network():
	"""`test_all_four_kenya_sector_technologies_are_present` must notice a drop.

	The mutation removes hydro after the builder and before ``apply_views``, so
	the coupled network is missing Kenya's fourth technology while the config
	still names it. The gate reads the network's own generators, so it fails;
	a gate reading the config keys would pass (05-layer2 §3, §7 criterion 7).
	"""
	old, new = _HYDRO_DROPPED
	assert old in COUPLING_PY.read_text(), (
		"the canary target moved; the coupling layer no longer extends its views "
		"where this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(KENYA_PORTFOLIO_GATE, KENYA_PORTFOLIO_FILE) == 0, "the gate does not pass on the shipped tree"

	with planted(COUPLING_PY, old, new):
		assert _gate_exit_code(KENYA_PORTFOLIO_GATE, KENYA_PORTFOLIO_FILE) != 0, (
			"the Kenya portfolio gate passed with hydro dropped from the coupled "
			"network; it cannot tell four technologies from three"
		)

	assert _gate_exit_code(KENYA_PORTFOLIO_GATE, KENYA_PORTFOLIO_FILE) == 0, "the restore was not proven"
