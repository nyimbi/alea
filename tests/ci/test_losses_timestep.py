# SPDX-License-Identifier: MIT
"""Every ``*_mwh`` in Layer 4b is an MW sum until a timestep says otherwise.

The DC solve returns a loss in MW for one snapshot. The field names asserted
MWh anyway, and nothing recorded the hours a snapshot stood for, so a
15-minute or 3-hourly dispatch scaled every loss by 4 or by a third with no
record of it. ``LossConfig.snapshot_hours`` is that record, and these tests
pin the arithmetic at a resolution other than one hour -- at one hour the
conversion is invisible, which is exactly why the defect survived.
"""

from __future__ import annotations

import numpy as np
import pytest

from alea.losses.contingency import sweep, tlens
from alea.losses.decompose import measure
from alea.losses.flow import Network, solve_series
from alea.losses.mitigation import annual_savings_from_snapshots
from alea.losses.views import LossConfig


def _three_bus() -> Network:
	"""A two-branch line: bus 0 -- bus 1 -- bus 2, equal susceptance."""
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0])
	from alea.losses.flow import susceptance_matrix

	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([100.0, 100.0]),
		branch_names=("L0", "L1"),
	)


def _dispatch(n_snapshots: int = 4) -> np.ndarray:
	"""Injections that put real flow on both branches, repeated per snapshot.

	The load sits at bus 2 and the generation at bus 0, so removing **either**
	branch strands bus 2's 50 MW: the outage's energy not served is 50 MW per
	snapshot. A fixture whose ENS is zero cannot show whether the timestep
	reaches ENS at all, and an earlier version of this file used one.
	"""
	row = np.array([50.0, 0.0, -50.0])
	return np.tile(row, (n_snapshots, 1))


def test_snapshot_loss_is_a_power_not_an_energy():
	"""``solve_series`` returns MW; summing it is not an energy without hours."""
	network = _three_bus()
	losses, _ = solve_series(network, _dispatch())
	assert losses.shape == (4,)
	# Two hours per snapshot quadruples the energy the same series carries.
	hourly = float(np.sum(losses) * 1.0)
	three_hourly = float(np.sum(losses) * 3.0)
	assert three_hourly == pytest.approx(3.0 * hourly, rel=1e-9)


def test_annual_savings_scales_with_the_snapshot_length():
	"""The mitigation saving is an energy, so the timestep must reach it."""
	base = np.array([4.0, 4.0, 4.0, 4.0])
	after = np.array([1.0, 1.0, 1.0, 1.0])
	hourly, hourly_usd = annual_savings_from_snapshots(base, after, 100.0)
	quarterly, quarterly_usd = annual_savings_from_snapshots(
		base, after, 100.0, snapshot_hours=0.25
	)
	assert hourly == pytest.approx(12.0, rel=1e-9)
	assert quarterly == pytest.approx(3.0, rel=1e-9)
	# The price is per MWh, so the money follows the energy exactly.
	assert hourly_usd == pytest.approx(hourly * 100.0, rel=1e-9)
	assert quarterly_usd == pytest.approx(quarterly * 100.0, rel=1e-9)


def test_a_non_positive_snapshot_length_is_refused():
	with pytest.raises(AssertionError, match="snapshot_hours"):
		annual_savings_from_snapshots(
			np.array([1.0]), np.array([0.0]), 1.0, snapshot_hours=0.0
		)


def test_the_decomposition_energy_follows_the_timestep():
	"""The three components are energies and must scale together."""
	network = _three_bus()
	dispatch = _dispatch()
	hourly = measure(network, dispatch, LossConfig(snapshot_hours=1.0))
	half_hourly = measure(network, dispatch, LossConfig(snapshot_hours=0.5))
	assert half_hourly.actual_losses_mwh == pytest.approx(
		hourly.actual_losses_mwh * 0.5, rel=1e-9
	)
	assert half_hourly.reference_losses_mwh == pytest.approx(
		hourly.reference_losses_mwh * 0.5, rel=1e-9
	)


def test_energy_not_served_follows_the_timestep():
	"""ENS is the kernel's MW shortfall summed, so it needs the same factor."""
	network = _three_bus()
	injections = _dispatch()
	hourly = sweep(network, injections, LossConfig(snapshot_hours=1.0))
	two_hourly = sweep(network, injections, LossConfig(snapshot_hours=2.0))
	# The fixture's ENS is not zero -- 50 MW stranded at bus 2 for four
	# snapshots -- so this asserts a real product rather than 0 == 0.
	assert hourly.base_ens_mwh == 0.0
	assert hourly.ens_with_out(0) == pytest.approx(200.0, rel=1e-9)
	assert two_hourly.ens_with_out(0) == pytest.approx(hourly.ens_with_out(0) * 2.0, rel=1e-9)


def test_a_connected_base_case_strands_nothing():
	"""The base case has every branch in, so its ENS is exactly zero.

	This is the gate for a kernel defect found while building the fixture
	above: the Rust shortfall read an exactly-zero bus angle as "no finite
	angle", and bus 1 of this radial solves to exactly zero while carrying
	50 MW. A fully connected network therefore reported 50 MW of unserved
	energy in its own base case, and every TLENS ranking built on it was
	measured against a base that did not exist.
	"""
	network = _three_bus()
	hourly = sweep(network, _dispatch(), LossConfig(snapshot_hours=1.0))
	assert hourly.base_ens_mwh == 0.0


def test_the_tlens_ranking_is_invariant_to_the_timestep():
	"""A common factor cancels in a share, so the ranking must not move.

	This is the other half of the gate: the conversion must reach the energies
	without perturbing the ordering, because ``share`` is a ratio.
	"""
	network = _three_bus()
	injections = _dispatch()
	hourly = tlens(network, injections, LossConfig(snapshot_hours=1.0))
	three_hourly = tlens(network, injections, LossConfig(snapshot_hours=3.0))
	assert [e.branch_name for e in hourly.entries] == [
		e.branch_name for e in three_hourly.entries
	]
	for a, b in zip(hourly.entries, three_hourly.entries, strict=True):
		assert a.share == pytest.approx(b.share, rel=1e-9)
	assert three_hourly.total_ens_mwh == pytest.approx(
		hourly.total_ens_mwh * 3.0, rel=1e-9
	)
	# Not a vacuous ratio: the fixture's total ENS is real.
	assert hourly.total_ens_mwh > 0.0


def test_the_timestep_is_recorded_in_the_provenance():
	"""A conversion nothing records is a conversion nobody can audit."""
	from alea.losses.service import _network_parameters

	parameters = _network_parameters(_three_bus(), LossConfig(snapshot_hours=0.25))
	assert parameters["snapshot_hours"] == 0.25
