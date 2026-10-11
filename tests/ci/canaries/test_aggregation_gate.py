# SPDX-License-Identifier: MIT
"""Canary: a time-aggregated solve must be refused without a passing validation.

AD-9. Time aggregation (TSAM) is an approximation, and the plan's exit criterion
is that Kenya's aggregated solve lands within 2% on cost and 5% on mix. Without
the gate, an aggregated run produces a capacity mix 8% off and reports it with
the same confidence as a full-resolution one.

Three ways the gate can fail open, and each gets an assertion:

* no validation artefact at all -> refuse (a missing measurement is not a pass);
* a validation measured at a *different* level -> refuse (the measurement does
  not transfer between levels);
* a validation that fails its tolerances -> refuse.
"""

from __future__ import annotations

from pathlib import Path

import pypsa
import pytest

from alea.planning.aggregation import (
	AggregationError,
	AggregationValidation,
	network_id,
	require_aggregation_validation,
	write_validation,
)
from tests.ci.canaries import assert_raises


def _network() -> pypsa.Network:
	network = pypsa.Network()
	network.add("Bus", "bus_00000", lon=36.8, lat=-1.29)
	network.add("Bus", "bus_00001", lon=39.6, lat=-4.04)
	network.add("Line", "L1", bus0="bus_00000", bus1="bus_00001", x=0.1, r=0.01, s_nom=100.0)
	return network


def _validation(network: pypsa.Network, *, n_periods: int, cost_error_pct: float, mix_error_pct: float) -> AggregationValidation:
	return AggregationValidation(
		network_id=network_id(network),
		n_periods=n_periods,
		period_length=168,
		n_clusters=1,
		cost_error_pct=cost_error_pct,
		capacity_mix_l1_error_pct=mix_error_pct,
		emissions_error_pct=0.0,
		peak_price_error_pct=0.0,
		full_cost=1.0e9,
		aggregated_cost=1.0e9 * (1.0 + cost_error_pct / 100.0),
		n_snapshots_full=8760,
		n_snapshots_aggregated=168 * n_periods,
	)


def test_a_missing_validation_is_refused(tmp_path: Path):
	network = _network()
	with pytest.raises(AggregationError, match="no validation artefact exists"):
		require_aggregation_validation(network, 12, root=tmp_path)


def test_a_passing_validation_is_accepted(tmp_path: Path):
	network = _network()
	write_validation(_validation(network, n_periods=12, cost_error_pct=0.5, mix_error_pct=1.0), root=tmp_path)
	assert require_aggregation_validation(network, 12, root=tmp_path).passes


def test_a_validation_measured_at_another_level_is_refused(tmp_path: Path):
	network = _network()
	write_validation(_validation(network, n_periods=24, cost_error_pct=0.5, mix_error_pct=1.0), root=tmp_path)
	with pytest.raises(AggregationError, match="does not transfer between levels"):
		require_aggregation_validation(network, 12, root=tmp_path)


def test_a_failing_validation_is_refused(tmp_path: Path):
	network = _network()
	# 8% cost error is the defect the plan names; the tolerance is 2%.
	write_validation(_validation(network, n_periods=12, cost_error_pct=8.0, mix_error_pct=3.0), root=tmp_path)
	with pytest.raises(AggregationError, match="FAILS"):
		require_aggregation_validation(network, 12, root=tmp_path)


def test_a_tolerance_boundary_is_enforced_exactly(tmp_path: Path):
	"""At the tolerance the validation passes; a hair over it does not.

	Boundary behaviour matters because an off-by-one in the comparison is
	invisible everywhere except here.
	"""
	network = _network()
	write_validation(_validation(network, n_periods=12, cost_error_pct=2.0, mix_error_pct=5.0), root=tmp_path)
	assert require_aggregation_validation(network, 12, root=tmp_path).passes

	write_validation(_validation(network, n_periods=12, cost_error_pct=2.0001, mix_error_pct=5.0), root=tmp_path)
	with pytest.raises(AggregationError, match="FAILS"):
		require_aggregation_validation(network, 12, root=tmp_path)


def test_the_gate_is_blind_without_the_missing_artefact_check(tmp_path: Path):
	"""Canary proper: if absence were treated as a pass, the gate fails open.

	`load_validation` returning `None` is the only thing standing between "no
	measurement" and "measured and fine". This asserts that the None branch is
	what refuses, by checking the gate's behaviour is not simply a tolerance
	test.
	"""
	network = _network()
	# No artefact, but a passing one would be accepted -- so the refusal above
	# comes from the absence check and not from something incidental.
	error = assert_raises(AggregationError, require_aggregation_validation, network, 12, root=tmp_path)
	assert "no validation artefact" in str(error)
	write_validation(_validation(network, n_periods=12, cost_error_pct=0.0, mix_error_pct=0.0), root=tmp_path)
	assert require_aggregation_validation(network, 12, root=tmp_path).passes
