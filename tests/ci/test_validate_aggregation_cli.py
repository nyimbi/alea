# SPDX-License-Identifier: MIT
"""`alea validate aggregation`: the remedy the AD-9 gate's refusal names.

The gate's own error string says "Run `alea validate aggregation` first", and
`04-layer1-planning.md` §7 quotes the same string -- and the CLI had no `validate`
group at all. A gate whose remedy cannot be run is a gate whose failure has no
next step: the operator reads the refusal, finds no command by that name, and
either hand-writes an artefact or sets ``time_aggregation: 1`` and gives up the
tractability the whole layer exists for.

Two things are asserted, and they fail for different reasons.

**The command exists and records a measurement.** Asserted through the CLI
runner, not by importing the function: the defect was registration, and a
function defined but never mounted on a typer is unreachable from the shell --
which is the only entry point a Snakemake rule may use (AD-5).

**An unsolved network is refused.** Measuring an unsolved network compares two
zeros and reports a perfect aggregation, which is worse than no measurement: it
is a passing artefact for a network nobody solved, and the gate would accept it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pypsa
import pytest

from alea.planning.aggregation import (
	load_validation,
	network_id,
	require_aggregation_validation,
)
from tests.ci.test_planning_layer1 import _seasonal_network, _seasonal_year


def _solved_seasonal(tmp_path: Path) -> Path:
	"""A solved seasonal year on disk, which is what the command takes."""
	load, solar, snapshots = _seasonal_year()
	network = _seasonal_network(load, solar, snapshots)
	network.optimize(solver_name="highs", log_to_console=False)
	path = tmp_path / "seasonal.nc"
	network.export_to_netcdf(path)
	return path


def _validate(*args: str):
	from typer.testing import CliRunner

	from alea.cli import app

	return CliRunner().invoke(app, ["validate", "aggregation", *args])


def test_the_command_is_reachable() -> None:
	"""`alea validate aggregation` exists, which it did not before."""
	result = _validate("--help")
	assert result.exit_code == 0, result.output
	assert "--periods" in result.stdout
	assert "--period-length" in result.stdout


def test_the_command_records_a_measurement_the_gate_reads(tmp_path: Path) -> None:
	"""The artefact lands where `require_aggregation_validation` looks for it.

	The two ends have to meet: a validation written to one directory and read
	from another is a gate that reports "no artefact" for a network that was
	measured, and the operator re-runs an expensive measurement for no reason.
	So the command is run with the default root, and the gate is then asked
	whether it accepts the network -- which is the only assertion that proves
	the file is the one the gate reads.
	"""
	path = _solved_seasonal(tmp_path)
	out = tmp_path / "aggregation"

	result = _validate(
		"--network", str(path), "--periods", "12", "--period-length", "24", "--out", str(out)
	)
	assert result.exit_code == 0, result.output
	assert "cost error" in result.stdout, result.stdout

	# Read it back through the same loader the gate uses, by the same network id.
	solved = pypsa.Network(str(path))
	validation = load_validation(network_id(solved), root=out)
	assert validation is not None, "the command wrote no artefact the gate can read"
	assert validation.n_periods == 12
	assert validation.n_snapshots_full == 8760
	assert validation.n_snapshots_aggregated == 12 * 24
	assert validation.passes, (
		f"the aggregation the command measured is outside tolerance: cost "
		f"{validation.cost_error_pct:.2f}%, mix {validation.capacity_mix_l1_error_pct:.2f}%"
	)
	# And the gate itself accepts it, which is what makes the artefact useful.
	assert require_aggregation_validation(solved, 12, root=out).network_id == validation.network_id


def test_an_unsolved_network_is_refused(tmp_path: Path) -> None:
	"""Measuring an unsolved network would report a perfect aggregation.

	Both solves return the same objective (none), so the cost error is zero, the
	mix error is zero, and the artefact records a passing validation for a
	network nobody solved. That is the vacuous-fixture failure: a measurement
	that manufactures the shape the gate wants.
	"""
	load, solar, snapshots = _seasonal_year()
	unsolved = _seasonal_network(load, solar, snapshots)
	path = tmp_path / "unsolved.nc"
	unsolved.export_to_netcdf(path)

	result = _validate("--network", str(path), "--periods", "12", "--out", str(tmp_path / "agg"))
	assert result.exit_code != 0, "an unsolved network was measured and recorded"
	assert "not solved" in result.output, result.output
	assert not list((tmp_path / "agg").glob("*.json")), (
		"the command wrote an artefact for a network it refused to measure"
	)


def test_a_failing_measurement_is_still_written(tmp_path: Path) -> None:
	"""A measurement outside tolerance is recorded, and says so.

	`write_validation`'s own rule: a failing measurement on disk is how the
	operator learns the fast path is 8% off. Refusing to write it leaves the gate
	reporting "no artefact" instead of "artefact says 8%", which is a less useful
	finding and hides that a measurement was ever taken.

	The failing case is produced honestly -- twelve representatives for a year is
	too few to hold this seasonal shape inside 2% -- rather than by writing a
	fabricated artefact. The assertion is that the measurement *noticed*, which
	is also what proves the command is measuring rather than echoing a zero.
	"""
	path = _solved_seasonal(tmp_path)
	out = tmp_path / "aggregation"
	result = _validate(
		"--network", str(path), "--periods", "3", "--period-length", "24", "--out", str(out)
	)
	assert result.exit_code == 0, result.output

	solved = pypsa.Network(str(path))
	validation = load_validation(network_id(solved), root=out)
	assert validation is not None, "a failing measurement was not recorded"
	assert not validation.passes, (
		"3 representative days for a seasonal year passed AD-9's tolerance, which "
		f"means the measurement is not measuring: cost {validation.cost_error_pct:.2f}%, "
		f"mix {validation.capacity_mix_l1_error_pct:.2f}%"
	)
	assert "OUTSIDE tolerance" in result.output, result.output


def test_a_passthrough_aggregation_is_refused(tmp_path: Path) -> None:
	"""Periods that cover the whole series are refused, not measured as flawless.

	The bug this command shipped with for one test run: ``--period-length``
	defaulted to ``snapshots / periods``, and 8760 / 12 is 730, so twelve
	"periods" of 730 hours covered all 8760 hours. The aggregated network was the
	full-resolution one, both solves returned the same objective, and the
	artefact recorded a 0.00% cost error with the gate's blessing.

	A validation that cannot fail is worse than none: it is a passing artefact
	for an aggregation nobody performed.
	"""
	path = _solved_seasonal(tmp_path)
	out = tmp_path / "aggregation"
	result = _validate(
		"--network", str(path), "--periods", "12", "--period-length", "730", "--out", str(out)
	)
	assert result.exit_code != 0, "a passthrough aggregation was measured and accepted"
	assert "cover the whole" in result.output, result.output
	assert not list(out.glob("*.json")), "an artefact was written for a passthrough"


def test_the_recorded_artefact_carries_its_provenance(tmp_path: Path) -> None:
	"""The artefact is a provenance record, not a bare number (AD-6).

	A cost error with no record of which network, level and tolerances produced
	it is a number nobody can act on a year later. The provenance is a *sidecar*
	next to the payload, which is the shape `write_artefact` produces, so the
	reader has to follow it rather than expect it inline.
	"""
	path = _solved_seasonal(tmp_path)
	out = tmp_path / "aggregation"
	result = _validate(
		"--network", str(path), "--periods", "12", "--period-length", "24", "--out", str(out)
	)
	assert result.exit_code == 0, result.output

	payload_path = next(p for p in out.glob("*.json") if not p.name.endswith(".provenance.json"))
	sidecar = payload_path.with_suffix(payload_path.suffix + ".provenance.json")
	assert sidecar.exists(), f"no provenance sidecar beside {payload_path.name}"

	payload = json.loads(payload_path.read_text(encoding="utf-8"))
	assert payload["n_periods"] == 12, "the payload does not record the level it measured"
	provenance = json.loads(sidecar.read_text(encoding="utf-8"))
	parameters = provenance["parameters"]
	assert parameters["period_length"] == 24
	assert parameters["tolerance_cost_pct"] == pytest.approx(2.0)
	assert parameters["n_snapshots_full"] == 8760
	assert provenance["basis"] == "modelled", "a measured error is a modelled quantity"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
