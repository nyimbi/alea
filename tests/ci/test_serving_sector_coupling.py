# SPDX-License-Identifier: MIT
"""`sector_coupling` is wired: a solved network in, a coupled artefact out.

WHY this module exists. `@stage("sector_coupling")` was registered and
unrunnable. Its builder read ``getattr(context, "network_path", None) or
config.paths.results``, and both arms were wrong: a `BuildContext` carries
``parameters`` and has no ``network_path`` attribute, so the first arm was always
``None``; and ``config.paths.results`` is the results *directory*, so the
fallback handed ``pypsa.Network`` a directory. `STAGES_WITHOUT_RULES` recorded
the gap as "its input is a solved scenario, so the rule depends on a solve the
workflow does not yet sequence" -- but the workflow sequences one:
`rules/losses.smk` declares ``provided("solved_network", NETWORKS)`` for the
same input, and `--set network_dir=` is how a rule points a stage at it.

**The test that matters is that the stage runs.** A registered builder with no
caller is a stage in name only, and the defect above survived because nothing
ever invoked it. So the first test here solves a network, runs the stage through
`build_stage` -- the CLI's own path, not the builder directly -- and asserts the
artefact and the coupled network exist.

**The second is the refusal, because it is the default path.** The shipped
config has ``sector.enabled: false`` and every sector flag false, so the
coupling produces no assets and `write_coupling_artefact` refuses. That refusal
is why the stage is not in `rule all` (a default clone's `snakemake all` would
fail), and it must name what turns a sector on rather than reading as a bare
assertion.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import build_stage, registered_stages

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")


def _solved_network(directory: Path) -> Path:
	"""A solved two-carrier network at the path a rule's `--set network_dir` names."""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "grid", v_nom=220.0, carrier="AC")
	network.add("Generator", "coal", bus="grid", carrier="coal", p_nom=300.0, marginal_cost=45.0)
	network.add("Generator", "solar", bus="grid", carrier="solar", p_nom=200.0, marginal_cost=0.0)
	network.add("Load", "load", bus="grid", p_set=150.0)
	profile = np.zeros(len(SNAPSHOTS))
	profile[12:16] = 1.0
	network.generators_t.p_max_pu = pd.DataFrame({"solar": profile}, index=network.snapshots)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the fixture network did not solve: {status} ({condition})"

	directory.mkdir(parents=True, exist_ok=True)
	path = directory / "abc123-2030.nc"
	network.export_to_netcdf(str(path))
	return path


def _config(tmp_path: Path, *, hydrogen: bool = True) -> Config:
	overrides = [
		f"paths.processed={tmp_path / 'processed'}",
		f"paths.results={tmp_path / 'results'}",
	]
	if hydrogen:
		# A physical constant with no source is refused by `SectorConfig`, and
		# rightly: an efficiency nobody can trace is an indefensible result.
		overrides += [
			"sector.enabled=true",
			"sector.hydrogen_enabled=true",
			"sector.electrolyser_efficiency_source=probe fixture",
		]
	return load_config(overrides=overrides)


def test_the_stage_runs_and_writes_both_artefacts(tmp_path: Path):
	"""End to end through `build_stage`, the path the CLI and a rule both take.

	The builder is invoked through the registry rather than called directly,
	because the defect this closes was that *nothing* called it: a direct call
	would prove the function works while the stage stays unreachable.
	"""
	network_dir = tmp_path / "results" / "networks"
	_solved_network(network_dir)
	config = _config(tmp_path)
	out = tmp_path / "processed" / "sector_coupling.json"

	result = build_stage(
		"sector_coupling", config, out, parameters={"network_dir": str(network_dir)}
	)

	assert result.path.exists(), "the stage wrote no coupling artefact"
	payload, provenance = read_artefact(out)
	assert payload["assets"], "the coupling artefact carries no assets"
	assert provenance.parameters["sectors"] == ["hydrogen"], (
		"the artefact's recorded sectors are not the one the config enabled"
	)
	assert provenance.inputs, "a derived artefact must record the network it read"

	coupled = out.with_suffix(".coupled.nc")
	assert coupled.exists(), (
		"the coupled network is written beside the artefact for Layer 1 to solve, "
		"and `write_coupling_artefact`'s caller must leave it on disk"
	)
	assert pypsa.Network(str(coupled)).buses.index.isin(["grid"]).any(), (
		"the coupled network does not carry the base network's bus"
	)


def test_the_stage_records_the_network_it_resolved(tmp_path: Path):
	"""The resolved digest is an input, as in `network_arrays`.

	The solved network's filename is a content hash, so a rule cannot declare it;
	the stage resolves the newest and must record what it resolved, or a second
	run's idempotence check compares against an empty list and the stage re-runs
	forever.
	"""
	network_dir = tmp_path / "results" / "networks"
	path = _solved_network(network_dir)
	config = _config(tmp_path)
	out = tmp_path / "processed" / "sector_coupling.json"

	build_stage("sector_coupling", config, out, parameters={"network_dir": str(network_dir)})
	_, provenance = read_artefact(out)

	from alea.io.artefacts import sha256_file

	assert sha256_file(path) in provenance.inputs, (
		"the stage did not record the digest of the network it read, so its "
		"idempotence check cannot tell a rerun on the same solve from a rerun on "
		"a different one"
	)


def test_the_stage_refuses_when_every_sector_is_disabled(tmp_path: Path):
	"""The default config's path, and it must say what turns a sector on.

	With no sector enabled the coupling is a no-op on a copy of the base network,
	and an artefact asserting a coupled result for an electricity-only network
	would be false. The refusal is also why this stage is not in `rule all`: a
	default clone would fail the default target. The message names the flags.
	"""
	network_dir = tmp_path / "results" / "networks"
	_solved_network(network_dir)
	config = _config(tmp_path, hydrogen=False)
	out = tmp_path / "processed" / "sector_coupling.json"

	with pytest.raises(ArtefactError, match="no assets"):
		build_stage("sector_coupling", config, out, parameters={"network_dir": str(network_dir)})

	with pytest.raises(ArtefactError, match="sector.enabled"):
		build_stage("sector_coupling", config, out, parameters={"network_dir": str(network_dir)})


def test_the_register_moved_with_the_wiring():
	"""Wiring the stage moves it out of the no-rule register.

	`STAGES_WITHOUT_RULES` names stages that are registered and run by nothing.
	This one now has a rule, so the two sets must not both name it -- the
	bidirectional half, asserted here because the register's own gate reads the
	Snakemake text rather than the reason.
	"""
	from tests.ci.test_orchestration_workflow import STAGES, STAGES_WITHOUT_RULES

	assert "sector_coupling" in registered_stages(), "the stage is no longer registered"
	assert "sector_coupling" in STAGES, "the stage has a rule and is not in the declared set"
	assert "sector_coupling" not in STAGES_WITHOUT_RULES, (
		"the stage has a rule and is still recorded as one that runs nothing"
	)
