# SPDX-License-Identifier: MIT
"""Canaries for the two wiring gates in `test_planning_inputs.py`.

Both gates assert that a config knob reaches the network the solver receives.
That is a different claim from the ones `test_planning_layer1_gates.py`
canaries -- those watch a *property* of a built network, these watch whether the
pipeline *does* the thing it declared. A knob that is validated, logged and
never applied is invisible to every property test, because the network it
produces is well-formed: it is simply at the wrong resolution, or carrying the
wrong series.

WHY each canary runs *the gate itself* in a fresh interpreter rather than
re-measuring the property: a proxy that re-implements the check is a canary of
the proxy, and it passes whether or not the gate can fail. WHY a subprocess at
all: the mutation is to a module the test session has already imported, so
patching the file on disk changes nothing that runs, and the canary would report
a blind gate that is only blind to its own patch.

Restoration is always from the file backup ``planted`` keeps, never with
``git checkout``: the canary's edit and the layer's own uncommitted work live in
the same file.
"""

from __future__ import annotations

import os
import subprocess
import sys

from tests.ci.canaries import REPO, planted

EXPANSION_PY = REPO / "src" / "alea" / "planning" / "expansion.py"
SERVICE_PY = REPO / "src" / "alea" / "planning" / "service.py"


def _gate(name: str) -> list[str]:
	"""The pytest invocation that runs one gate, in this repository."""
	return [
		sys.executable,
		"-m",
		"pytest",
		"-q",
		"-p",
		"no:randomly",
		f"tests/ci/test_planning_inputs.py::{name}",
	]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
	env = {**os.environ, "PYTHONPATH": str(REPO)}
	return subprocess.run(command, capture_output=True, text=True, check=False, env=env, cwd=str(REPO))


def _assert_gate_passes_clean(command: list[str]) -> None:
	"""The baseline. A canary over a gate that is already red proves nothing."""
	clean = _run(command)
	assert clean.returncode == 0, (
		f"the gate does not pass on the shipped tree, so the canary below would "
		f"prove nothing:\n{clean.stdout[-2000:]}"
	)


# --------------------------------------------------------------------------
# test_a_config_selecting_time_aggregation_reaches_a_reduced_network
# --------------------------------------------------------------------------

_GATE_APPLIED = "test_a_config_selecting_time_aggregation_reaches_a_reduced_network"


def test_the_reduction_gate_notices_an_aggregation_that_was_never_applied():
	"""Drop the reduction from the solve path and watch the gate notice.

	The gate is `test_a_config_selecting_time_aggregation_reaches_a_reduced_network`.
	The mutation is the defect the gate was written for: ``solve_scenario``
	passes the AD-9 gate and then solves the network it built, at full
	resolution. The config still says ``time_aggregation=6``, the log still says
	the aggregation was applied, and every investment period carries 24
	timesteps instead of 18.
	"""
	command = _gate(_GATE_APPLIED)
	_assert_gate_passes_clean(command)

	target = """		built = aggregate_network(
			built,
			n_periods=config.solve.time_aggregation,
			period_length=validation.period_length,
		)"""
	assert target in SERVICE_PY.read_text(), "canary target not found: the solve path does not reduce"
	with planted(SERVICE_PY, target, "\t\tpass  # canary: aggregation not applied"):
		mutated = _run(command)
	assert mutated.returncode != 0, (
		"the gate passed with the reduction removed, so it checks the gate rather "
		"than the effect"
	)
	assert "should keep" in mutated.stdout, (
		f"the gate failed for a reason other than the missing reduction:\n{mutated.stdout[-2000:]}"
	)

	assert _run(command).returncode == 0, "the canary leaked its mutation"


# --------------------------------------------------------------------------
# test_multi_period_repeats_the_network_series_rather_than_inventing_one
# --------------------------------------------------------------------------

_GATE_REPEATS = "test_multi_period_repeats_the_network_series_rather_than_inventing_one"


def test_the_multi_period_gate_notices_a_fabricated_year():
	"""Invent a January year per period and watch three of four carry nothing.

	The gate is
	`test_multi_period_repeats_the_network_series_rather_than_inventing_one`.
	The mutation is the pre-fix path in full: the builder constructs
	``horizon-01-01`` hours instead of repeating the network's own snapshots,
	and ``set_snapshots`` applies that index. The demand frame covers 2030 only,
	so the other three horizons align to no label and pypsa fills them with the
	static default -- zero load, and a capacity factor of 1.0 where the profile
	says 0.25. The solve still succeeds.
	"""
	command = _gate(_GATE_REPEATS)
	_assert_gate_passes_clean(command)

	# One `planted` call on one contiguous block, not two nested ones: `planted`
	# holds an exclusive ``flock`` on the file for the life of the context
	# manager, so a nested call on the same path blocks forever. The mutation is
	# the pre-fix body of ``set_multi_period`` -- a fabricated January year
	# applied by label -- which is one behaviour and so one replacement.
	target = """	expected = build_multi_period_snapshots(network, horizons, base_year=base_year)
	network.set_investment_periods(horizons)
	assert network.snapshots.equals(expected), (
		"pypsa built a different index than this module specifies: "
		f"{len(network.snapshots)} snapshots, expected {len(expected)}"
	)"""
	replacement = """	tuples: list[tuple[int, Any]] = []
	for horizon in horizons:
		start = pd.Timestamp(f"{horizon}-01-01 00:00:00")
		for h in range(len(network.snapshots)):
			tuples.append((horizon, start + pd.Timedelta(hours=h)))
	network.set_snapshots(pd.MultiIndex.from_tuples(tuples, names=["period", "timestep"]))"""
	assert target in EXPANSION_PY.read_text(), "canary target not found: the index is not repeated"

	with planted(EXPANSION_PY, target, replacement):
		mutated = _run(command)
	assert mutated.returncode != 0, (
		"the gate passed against a fabricated year, so it cannot tell a repeated "
		"series from an invented one"
	)
	assert "carries no load" in mutated.stdout, (
		f"the gate failed for a reason other than the emptied periods:\n{mutated.stdout[-2000:]}"
	)

	assert _run(command).returncode == 0, "the canary leaked its mutation"
