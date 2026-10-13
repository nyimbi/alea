# SPDX-License-Identifier: MIT
"""Canary: watch the AD-9 accuracy gates fail on the defects they were written for.

Two defects, one gate each, and both were live:

**The kernel chose the flattest blocks.** `aggregate` scored every candidate
period by its own internal spread and took the lowest scorers as
representatives. On a seasonal year the flattest blocks are all in the same
quiet fortnight, so all twelve representatives landed inside one December
fortnight, and the aggregated solve cost **106%** more than the full-resolution
one against AD-9's 2%. Every existing test of the kernel used an exact-division
case, where "flattest block" and "contiguous block" happen to coincide, so the
whole suite was blind to it.

**Nothing built an aggregated network at all.** `build_aggregation` returned the
kernel's arrays and had no caller, so the AD-9 gate guarded a path no solve ever
took. The obvious construction, `network.cluster.temporal.from_snapshot_map`,
groups the original snapshots by their mapped representative and applies its
default rule — ``mean`` — to every dynamic frame, which *averages the
representative period*: a solar profile with a midday peak becomes a flat band,
and the optimiser builds no solar. Measured: 23% cost error, 106% mix error.

The canary for the second cannot be a source mutation, because the mutation is
the *absence* of a function. It plants the averaged construction in place of the
representative-period one and watches the profile gate fail, which is the
honest form of "this gate would have caught the code we almost wrote".

WHY the kernel canary needs a fresh interpreter and a rebuild: the defect is in
Rust. Patching `lib.rs` changes nothing the installed extension runs, so a
canary written as a source mutation would pass against the compiled defect —
exactly the false alarm `planted`'s first guard exists to prevent. The canary
therefore asserts the *observable* shape instead: it builds the network the way
the old kernel's output would have built it (twelve consecutive blocks) and
watches the gate fail. The kernel's own regression is pinned by the Rust unit
tests in `rust/alea-series/src/lib.rs`, which run against the source.

Restoration is `planted`'s, from bytes read under the lock, never `git checkout`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from alea.planning.aggregation import aggregate_network
from tests.ci.canaries import REPO, planted
from tests.ci.test_planning_layer1 import _seasonal_network, _seasonal_year

AGGREGATION_PY = REPO / "src" / "alea" / "planning" / "aggregation.py"
CLI_PY = REPO / "src" / "alea" / "cli.py"
LAYER1_TEST_PY = REPO / "tests" / "ci" / "test_planning_layer1.py"
VALIDATE_CLI_TEST_PY = REPO / "tests" / "ci" / "test_validate_aggregation_cli.py"

# The old kernel's representative choice, as a selection: twelve consecutive
# blocks. Not a mutation -- a stand-in for what the kernel returned, so the
# network-building path can be watched failing on it.
_CONTIGUOUS_REPRESENTATIVES = (
	'\tchosen = np.asarray(built["representatives"], dtype=int) // period_length'
)

_TAKE_THE_FIRST_TWELVE_BLOCKS = "\tchosen = np.arange(n_periods)"


def _run_gate(gate: str, *, module: Path | None = None) -> subprocess.CompletedProcess[str]:
	"""Run one gate by name in a **fresh interpreter**.

	The plant is a source mutation, and this test session has already imported
	`alea.planning.aggregation` -- so calling the gate in-process would run the
	module as it was at import time and the canary would report a blind gate that
	is only blind to its own patch. A child process reads the mutated source.
	The gate is addressed as ``<module>::<name>`` so pytest imports the module it
	needs and nothing of this session's.
	"""
	target = module or LAYER1_TEST_PY
	env = {**os.environ, "PYTHONPATH": str(REPO)}
	return subprocess.run(
		[sys.executable, "-m", "pytest", f"{target}::{gate}", "-q", "--no-header", "-p", "no:cacheprovider"],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
		env=env,
	)


def _assert_gate_passes(gate: str, *, module: Path | None = None) -> None:
	result = _run_gate(gate, module=module)
	assert result.returncode == 0, f"{gate} does not pass on the shipped code:\n{result.stdout[-2000:]}"


def _assert_gate_fails(gate: str, *, match: str, module: Path | None = None) -> None:
	result = _run_gate(gate, module=module)
	assert result.returncode != 0, f"{gate} passed while the defect was planted:\n{result.stdout[-2000:]}"
	assert match in result.stdout, (
		f"{gate} failed, but not for the reason the canary planted: expected {match!r} "
		f"in the output:\n{result.stdout[-2000:]}"
	)


def test_the_accuracy_gate_notices_a_selection_confined_to_one_fortnight():
	"""Plant the old kernel's choice and watch the 2% gate fail.

	The gate is `test_aggregation_keeps_the_solve_within_tolerance`. Twelve
	consecutive blocks is what the flattest-block rule produced on a seasonal
	year, and it is the whole defect: measured through this plant, the aggregated
	solve moves total system cost by 13.7%, which is seven times AD-9's tolerance.

	The assertion is not merely "it failed" but *how* it failed: a plant that
	failed for an unrelated reason (a crash, a shape error) would prove nothing
	about the gate, so the canary reads the failure message.
	"""
	gate = "test_aggregation_keeps_the_solve_within_tolerance"
	_assert_gate_passes(gate)

	with planted(AGGREGATION_PY, _CONTIGUOUS_REPRESENTATIVES, _TAKE_THE_FIRST_TWELVE_BLOCKS):
		_assert_gate_fails(gate, match="outside AD-9's 2.0%")

	# Restored: the gate holds again.
	_assert_gate_passes(gate)


def test_the_representative_span_gate_notices_a_clustered_selection():
	"""The structural half, and it fails for the same shape of defect.

	`test_the_representatives_span_the_year_rather_than_one_fortnight` reads the
	kernel's own output rather than a solve, so it catches the selection defect
	without needing two LP solves to disagree. The plant is on the *test's* own
	selection line rather than on the kernel, because the kernel is Rust and a
	Python source mutation cannot reach it: what is being asserted is that the
	gate's span comparison is what refuses a clustered set.
	"""
	gate = "test_the_representatives_span_the_year_rather_than_one_fortnight"
	_assert_gate_passes(gate)

	old = '\tblocks = np.asarray(built["representatives"], dtype=int) // 24'
	with planted(LAYER1_TEST_PY, old, "\tblocks = np.arange(12)"):
		_assert_gate_fails(gate, match="span only")

	_assert_gate_passes(gate)


def test_the_profile_gate_notices_a_period_that_was_averaged():
	"""Plant the averaging construction and watch the profile gate fail.

	The gate is `test_a_representative_period_keeps_its_own_profile`, and the
	defect is the one that survives a correct kernel: building the aggregated
	network through `from_snapshot_map`, whose default rule averages each period
	to a flat profile. The plant selects one timestep per period instead of the
	whole period, which is what averaging collapses to -- one value per period,
	no diurnal shape left.
	"""
	gate = "test_a_representative_period_keeps_its_own_profile"
	_assert_gate_passes(gate)

	positions = (
		"\tpositions = np.concatenate(\n"
		"\t\t[np.arange(block * period_length, (block + 1) * period_length) for block in chosen]\n"
		"\t)"
	)
	with planted(AGGREGATION_PY, positions, "\tpositions = np.asarray(chosen, dtype=int) * period_length"):
		_assert_gate_fails(gate, match="snapshots")

	_assert_gate_passes(gate)


def test_the_validate_command_notices_a_passthrough_aggregation():
	"""Plant the passthrough default and watch the command accept a flawless zero.

	The gate is `test_a_passthrough_aggregation_is_refused`, and this is the
	defect the command actually shipped with: ``--period-length`` defaulted to
	``snapshots / periods``, 8760 / 12 is 730, and twelve periods of 730 hours is
	the whole year. The "aggregated" network was the full-resolution one, both
	solves returned the same objective, and the recorded artefact said 0.00% --
	a passing validation for an aggregation nobody performed.

	The plant removes the guard rather than changing the default, so the canary
	proves the guard is what refuses and not some incidental property of the
	fixture.
	"""
	gate = "test_a_passthrough_aggregation_is_refused"
	_assert_gate_passes(gate, module=VALIDATE_CLI_TEST_PY)

	guard = (
		"\t\tif periods * length >= len(solved.snapshots):\n"
		'\t\t\ttyper.secho(\n'
		'\t\t\t\tf"{periods} periods of {length} hours cover the whole "\n'
	)
	assert guard in CLI_PY.read_text(encoding="utf-8"), "the passthrough guard is not where the canary expects it"
	with planted(CLI_PY, guard, "\t\tif False:\n\t\t\ttyper.secho(\n"):
		_assert_gate_fails(gate, match="passthrough aggregation was measured", module=VALIDATE_CLI_TEST_PY)

	_assert_gate_passes(gate, module=VALIDATE_CLI_TEST_PY)


def test_the_gate_is_measuring_the_year_it_claims_to():
	"""A canary on the fixture, because a vacuous one passes for the wrong reason.

	The seasonal fixture is what makes the accuracy gate meaningful. If the year
	were flat, or the two profiles collinear, a broken selection would pass --
	which is the "fixture manufactured the shape the code needed" failure this
	repository has been bitten by before. So assert the fixture has the structure
	the gate depends on: a real seasonal swing, a real diurnal swing, and two
	columns that disagree about which part of the year is interesting.
	"""
	load, solar, snapshots = _seasonal_year()
	assert load.max() / load.min() > 1.2, "the load fixture has no seasonal swing"
	assert load.max() - load.min() > 20.0, "the load fixture's range is too narrow to lose"
	assert solar.max() > 0.8 and solar.min() == pytest.approx(0.0), (
		"the solar fixture has no peak and no night"
	)
	# The load peaks in winter and the solar in summer, which is what gives the
	# selection somewhere to go wrong. Compared on the same days, so the diurnal
	# cycle cancels and only the seasonal envelope is read.
	winter = np.isin(np.arange(8760) // 24, np.arange(0, 60))
	summer = np.isin(np.arange(8760) // 24, np.arange(160, 220))
	assert load[winter].mean() > load[summer].mean() + 10.0, "the load fixture does not peak in winter"
	assert solar[summer].mean() > solar[winter].mean() + 0.05, "the solar fixture does not peak in summer"

	# And the aggregated network really is the reduced one, not a passthrough.
	network = _seasonal_network(load, solar, snapshots)
	aggregated = aggregate_network(network, n_periods=12, period_length=24)
	assert len(aggregated.snapshots) == 288 < len(network.snapshots)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))

