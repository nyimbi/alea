# SPDX-License-Identifier: MIT
"""Differential tests: compiled kernels against independent Python references.

Each test compares `alea._core.kernels` with `tests/reference/`, which was
written from the kernel contracts rather than transcribed from the Rust. Where
the two disagree, one of them is wrong — which is the whole point, because two
copies of one misreading agree with each other.

Shape of the suite per kernel: a hand-checkable case with an answer computed on
paper, a randomised case from a fixed seed, and the edge cases the wrapper
docstring names. Tolerances are float32 for the f32 kernels and float64 for the
f64 kernels.

Reference-only tests cover the kernels whose *grouping* depends on a hash family
the reference does not share (`minhash`, `deduplicate`); those assert properties
and invariants rather than values.

Every kernel has a reference, which is `03-rust-core.md` §9 criterion 3 and was
not true until `optimal_bands_rows` and `contingency_sweep` got one. Both had
been asserted structurally only, and both had a rule that a reader would get
wrong from the contract alone:

* `optimal_bands_rows` maximises the S-curve's *step* at the threshold, not the
  textbook MMDS midpoint rule. The two disagree on 34 of 45 sampled inputs, so a
  reference written from the textbook would have failed the differential test on
  the majority of them and the failure would have looked like a kernel bug.
* `contingency_sweep`'s `overloaded_branches` counts strict `flow > rating`, and
  the two solvers disagree when the exact flow lands within one ULP of the
  rating. The randomised case therefore draws ratings away from the flows it is
  compared against; a rating set *equal* to a flow is a coin flip between two
  correct implementations and is not a defect either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# `tests/reference/` is a test aid, not a package the build ships, so it is not
# on the pytest pythonpath (which points at `src`). Add it here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any

from reference import dedup as ref_dedup  # noqa: E402
from reference import losses as ref_losses  # noqa: E402
from reference import rasters as ref_rasters  # noqa: E402
from reference import risk as ref_risk  # noqa: E402
from reference import series as ref_series  # noqa: E402

from alea._core import kernels as K  # noqa: E402

F32 = dict(rtol=1e-5, atol=1e-6)
F64: dict[str, Any] = dict(rtol=1e-9, atol=1e-12)


def assert_equal(got, expected, **tol) -> None:
	"""Compare two arrays, treating matching NaN positions as equal.

	NaN is a value here, not a missing one: a cloudy pixel *is* NaN and the
	distinction from 0.0 is the semantic under test.
	"""
	got = np.asarray(got, dtype=np.float64)
	expected = np.asarray(expected, dtype=np.float64)
	assert got.shape == expected.shape, f"shape {got.shape} != {expected.shape}"
	assert np.array_equal(np.isnan(got), np.isnan(expected)), "NaN positions differ"
	mask = ~np.isnan(got)
	if mask.any():
		np.testing.assert_allclose(got[mask], expected[mask], **tol)


# --------------------------------------------------------------------------
# alea-rasters
# --------------------------------------------------------------------------


def test_vza_baseline_hand_checkable():
	# One pixel, four months of one month, VZA 0..3 all in bin 0 at 5 deg.
	radiance = np.array([[[1.0]], [[2.0]], [[3.0]], [[4.0]]], dtype=np.float32)
	vza = np.array([[[0.0]], [[1.0]], [[2.0]], [[3.0]]], dtype=np.float32)
	month = np.array([1, 1, 1, 1], dtype=np.uint8)
	expected = np.full((12, 18, 1, 1), np.nan, dtype=np.float32)
	# Linear-interpolation first quartile of [1, 2, 3, 4] is 1.75.
	expected[0, 0, 0, 0] = 1.75
	got = K.vza_baseline(radiance, vza, month, 5.0, 0.25)
	assert got.shape == (12, 18, 1, 1)
	assert_equal(got, expected, **F32)
	assert_equal(ref_rasters.vza_baseline(radiance, vza, month, 5.0, 0.25), expected, **F32)


def test_vza_baseline_randomised():
	rng = np.random.default_rng(20261011)
	radiance = rng.uniform(0.0, 10.0, (6, 3, 4)).astype(np.float32)
	vza = rng.uniform(0.0, 90.0, (6, 3, 4)).astype(np.float32)
	month = rng.integers(1, 13, 6).astype(np.uint8)
	got = K.vza_baseline(radiance, vza, month, 5.0, 0.25)
	want = ref_rasters.vza_baseline(radiance, vza, month, 5.0, 0.25)
	assert_equal(got, want, **F32)


def test_vza_baseline_n_bins_follows_bin_size():
	radiance = np.ones((1, 1, 1), dtype=np.float32)
	vza = np.zeros((1, 1, 1), dtype=np.float32)
	month = np.array([1], dtype=np.uint8)
	# n_bins = ceil(90 / bin_size): 18 at 5 deg, 45 at 2 deg, 9 at 10 deg.
	assert K.vza_baseline(radiance, vza, month, 5.0, 0.25).shape[1] == 18
	assert K.vza_baseline(radiance, vza, month, 2.0, 0.25).shape[1] == 45
	assert K.vza_baseline(radiance, vza, month, 10.0, 0.25).shape[1] == 9


def test_vza_baseline_edges():
	# Empty time axis: a valid shape, entirely NaN.
	empty = K.vza_baseline(
		np.zeros((0, 2, 2), dtype=np.float32),
		np.zeros((0, 2, 2), dtype=np.float32),
		np.zeros(0, dtype=np.uint8),
		5.0,
		0.25,
	)
	assert empty.shape == (12, 18, 2, 2)
	assert np.isnan(empty).all()
	# Single pixel.
	single = K.vza_baseline(
		np.ones((1, 1, 1), dtype=np.float32),
		np.zeros((1, 1, 1), dtype=np.float32),
		np.array([1], dtype=np.uint8),
		5.0,
		0.25,
	)
	assert single[0, 0, 0, 0] == 1.0
	# All-equal input: every quantile is the same value.
	flat = K.vza_baseline(
		np.full((4, 1, 1), 3.0, dtype=np.float32),
		np.zeros((4, 1, 1), dtype=np.float32),
		np.array([1, 1, 1, 1], dtype=np.uint8),
		5.0,
		0.25,
	)
	assert flat[0, 0, 0, 0] == 3.0


def test_detect_outages_hand_checkable():
	baseline = np.full((12, 18, 1, 1), 10.0, dtype=np.float32)
	radiance = np.array([[[5.0]], [[20.0]], [[7.0]]], dtype=np.float32)
	vza = np.zeros((3, 1, 1), dtype=np.float32)
	month = np.array([1, 1, 1], dtype=np.uint8)
	cloud = np.array([[[0]], [[0]], [[2]]], dtype=np.uint8)
	# threshold 0.6 * 10 = 6: 5 is flagged, 20 is not, the cloudy pixel is NaN.
	expected = np.array([[[1.0]], [[0.0]], [[np.nan]]], dtype=np.float32)
	got = K.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, 0)
	assert_equal(got, expected, **F32)
	assert_equal(
		ref_rasters.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, 0),
		expected,
		**F32,
	)


def test_detect_outages_cloud_is_nan_not_zero():
	"""The pinned semantic: cloud is "no information", so it is NaN, not 0.0."""
	baseline = np.full((12, 18, 1, 1), 10.0, dtype=np.float32)
	radiance = np.full((1, 1, 1), 5.0, dtype=np.float32)
	vza = np.zeros((1, 1, 1), dtype=np.float32)
	month = np.array([1], dtype=np.uint8)
	for confidence in (1, 2, 3):
		cloud = np.array([[[confidence]]], dtype=np.uint8)
		out = K.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, 0)
		assert np.isnan(out[0, 0, 0]), f"confidence {confidence} must be NaN, not 0.0"
	# Confident clear stays a real value.
	clear = K.detect_outages(
		radiance, baseline, month, vza, np.zeros((1, 1, 1), dtype=np.uint8), 5.0, 0.6, 0
	)
	assert clear[0, 0, 0] == 1.0


def test_detect_outages_cloud_ceiling():
	baseline = np.full((12, 18, 1, 1), 10.0, dtype=np.float32)
	radiance = np.full((3, 1, 1), 5.0, dtype=np.float32)
	vza = np.zeros((3, 1, 1), dtype=np.float32)
	month = np.array([1, 1, 1], dtype=np.uint8)
	cloud = np.array([[[0]], [[1]], [[2]]], dtype=np.uint8)
	# Ceiling 0 keeps confident-clear only; ceiling 1 also keeps probably-clear.
	assert_equal(
		K.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, 0),
		np.array([[[1.0]], [[np.nan]], [[np.nan]]]),
		**F32,
	)
	assert_equal(
		K.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, 1),
		np.array([[[1.0]], [[1.0]], [[np.nan]]]),
		**F32,
	)


def test_detect_outages_randomised():
	rng = np.random.default_rng(7)
	radiance = rng.uniform(0.0, 10.0, (6, 3, 4)).astype(np.float32)
	vza = rng.uniform(0.0, 90.0, (6, 3, 4)).astype(np.float32)
	month = rng.integers(1, 13, 6).astype(np.uint8)
	baseline = ref_rasters.vza_baseline(radiance, vza, month, 5.0, 0.25)
	cloud = rng.integers(0, 4, (6, 3, 4)).astype(np.uint8)
	for ceiling in (0, 1):
		got = K.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, ceiling)
		want = ref_rasters.detect_outages(radiance, baseline, month, vza, cloud, 5.0, 0.6, ceiling)
		assert_equal(got, want, **F32)


def test_aggregate_to_zones_hand_checkable():
	anomaly = np.array([[[1.0, 0.0], [np.nan, 1.0]]], dtype=np.float32)
	zone_ids = np.array([[0, 0], [1, 1]], dtype=np.uint32)
	# Zone 0: one flagged and one clear pixel -> 1/2 = 0.5. Zone 1: one clear
	# flagged pixel and one NaN -> 1/1 = 1.0.
	expected = np.array([[0.5, 1.0]], dtype=np.float32)
	assert_equal(K.aggregate_to_zones(anomaly, zone_ids, 2), expected, **F32)
	assert_equal(ref_rasters.aggregate_to_zones(anomaly, zone_ids, 2), expected, **F32)


def test_aggregate_to_zones_nan_where_no_clear_pixels():
	anomaly = np.array([[[np.nan, np.nan], [1.0, 1.0]]], dtype=np.float32)
	zone_ids = np.array([[0, 0], [1, 1]], dtype=np.uint32)
	out = K.aggregate_to_zones(anomaly, zone_ids, 2)
	assert np.isnan(out[0, 0])
	assert out[0, 1] == 1.0


def test_aggregate_to_zones_randomised_and_edges():
	rng = np.random.default_rng(11)
	anomaly = (rng.random((6, 3, 4)) > 0.5).astype(np.float32)
	anomaly[0, 0, 0] = np.nan
	zone_ids = rng.integers(0, 3, (3, 4)).astype(np.uint32)
	assert_equal(
		K.aggregate_to_zones(anomaly, zone_ids, 3),
		ref_rasters.aggregate_to_zones(anomaly, zone_ids, 3),
		**F32,
	)
	# Empty time axis.
	empty = K.aggregate_to_zones(
		np.zeros((0, 2, 2), dtype=np.float32), np.zeros((2, 2), dtype=np.uint32), 2
	)
	assert empty.shape == (0, 2)


def test_block_sum_hand_checkable():
	values = np.arange(1, 13, dtype=np.float64).reshape(3, 4)
	# 3x4 into 2x2 blocks, last row/col short: keep the partial sums.
	expected = np.array([[14.0, 22.0], [19.0, 23.0]])
	np.testing.assert_allclose(K.block_sum(values, 2), expected, **F64)
	np.testing.assert_allclose(ref_rasters.block_sum(values, 2), expected, **F64)


def test_block_sum_randomised_and_edges():
	rng = np.random.default_rng(19)
	values = rng.normal(size=(5, 7))
	for factor in (2, 3, 4, 5):
		np.testing.assert_allclose(
			K.block_sum(values, factor), ref_rasters.block_sum(values, factor), **F64
		)
	# Factor larger than the dimension: a single block, the whole array.
	np.testing.assert_allclose(K.block_sum(np.ones((3, 4)), 5), np.array([[12.0]]), **F64)


def test_normalise_weights_hand_checkable():
	values = np.array([[1.0, 2.0], [3.0, 4.0]])
	expected = np.array([[0.1, 0.2], [0.3, 0.4]])
	np.testing.assert_allclose(K.normalise_weights(values), expected, **F64)
	np.testing.assert_allclose(ref_rasters.normalise_weights(values), expected, **F64)


def test_normalise_weights_sums_to_one_and_edges():
	rng = np.random.default_rng(23)
	values = rng.uniform(1.0, 10.0, (4, 5))
	assert np.isclose(K.normalise_weights(values).sum(), 1.0, **F64)
	np.testing.assert_allclose(
		K.normalise_weights(values), ref_rasters.normalise_weights(values), **F64
	)
	# Single element.
	np.testing.assert_allclose(K.normalise_weights(np.array([[5.0]])), np.array([[1.0]]), **F64)
	# Nothing finite: refused, because a reduction over nothing is not zero.
	with pytest.raises(RuntimeError):
		K.normalise_weights(np.zeros((2, 2)))


def test_is_clear_matches_kernel_semantics():
	"""The reference's cloud predicate reproduces the kernel's keep/drop."""
	for bits in (0b00, 0b01, 0b10, 0b11, 0b11111100):
		for ceiling in (0, 1):
			# Compare against the kernel's own observable behaviour via detection.
			baseline = np.full((12, 18, 1, 1), 10.0, dtype=np.float32)
			out = K.detect_outages(
				np.full((1, 1, 1), 5.0, dtype=np.float32),
				baseline,
				np.array([1], dtype=np.uint8),
				np.zeros((1, 1, 1), dtype=np.float32),
				np.array([[[bits]]], dtype=np.uint8),
				5.0,
				0.6,
				ceiling,
			)
			kernel_kept = not np.isnan(out[0, 0, 0])
			assert kernel_kept == ref_rasters.is_clear(bits, ceiling)


# --------------------------------------------------------------------------
# alea-series
# --------------------------------------------------------------------------


def test_aggregate_exact_division_matches_reference():
	rng = np.random.default_rng(31)
	for n_timesteps, n_periods, period_length in [(12, 3, 4), (12, 4, 3), (8, 2, 4), (6, 2, 3)]:
		series = rng.normal(size=(n_timesteps, 3)).astype(np.float32)
		got = K.aggregate(series, n_periods, period_length, 0)
		want = ref_series.aggregate(series, n_periods, period_length, 0)
		for got_part, want_part in zip(got, want, strict=True):
			assert_equal(got_part, want_part, **F64)


def test_aggregate_weights_sum_exactly_to_n_timesteps():
	"""The invariant the plan pins (§5.2): exact, not approximate."""
	rng = np.random.default_rng(37)
	for n_timesteps, n_periods, period_length in [
		(8760, 12, 730),
		(8760, 24, 365),
		(12, 3, 4),
		(6, 2, 3),
		(10, 2, 2),
	]:
		series = rng.normal(size=(n_timesteps, 2)).astype(np.float32)
		_, _, weights = K.aggregate(series, n_periods, period_length, 0)
		assert int(weights.sum()) == n_timesteps
		# A near-miss would be a systematic bias, so assert the exact integer.
		assert weights.sum() == float(n_timesteps)


def test_aggregate_every_timestep_assigned_once():
	rng = np.random.default_rng(41)
	series = rng.normal(size=(10, 3)).astype(np.float32)
	assignments, representatives, weights = K.aggregate(series, 2, 2, 0)
	assert assignments.shape[0] == 10
	assert len(representatives) == 2
	assert len(weights) == 2
	assert int(assignments.min()) >= 0
	assert int(assignments.max()) < 2
	# The per-period split is a heuristic and need not equal the assignment
	# histogram, but the exact sum is invariant.
	assert int(weights.sum()) == 10


def test_aggregate_is_deterministic_for_a_seed():
	series = np.arange(12, dtype=np.float32).reshape(6, 2)
	first = K.aggregate(series, 3, 2, 12345)
	second = K.aggregate(series, 3, 2, 12345)
	for a, b in zip(first, second, strict=True):
		assert np.array_equal(a, b)


def test_load_duration_curve_hand_checkable():
	series = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]], dtype=np.float32)
	expected = np.array([[7.0, 8.0], [5.0, 6.0], [3.0, 4.0], [1.0, 2.0]], dtype=np.float32)
	assert_equal(K.load_duration_curve(series), expected, **F32)
	assert_equal(ref_series.load_duration_curve(series), expected, **F32)


def test_load_duration_curve_randomised():
	rng = np.random.default_rng(43)
	series = rng.normal(size=(20, 4)).astype(np.float32)
	got = K.load_duration_curve(series)
	want = ref_series.load_duration_curve(series)
	assert_equal(got, want, **F32)
	# Sorted descending in every column.
	assert (np.diff(got, axis=0) <= 1e-6).all()


def test_validate_aggregation_matches_reference():
	full_capacity = np.array([100.0, 50.0, 25.0])
	aggregated_capacity = np.array([110.0, 45.0, 25.0])
	args = (full_capacity, aggregated_capacity, 1000.0, 1020.0, 500.0, 505.0, 80.0, 82.0)
	got = K.validate_aggregation(*args)
	want = ref_series.validate_aggregation(*args)
	assert got.keys() == want.keys()
	for key in want:
		np.testing.assert_allclose(got[key], want[key], **F64)


def test_validate_aggregation_zero_error_when_identical():
	full_capacity = np.array([100.0, 50.0, 25.0])
	got = K.validate_aggregation(full_capacity, full_capacity, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
	for value in got.values():
		assert value == 0.0


# --------------------------------------------------------------------------
# alea-losses
# --------------------------------------------------------------------------


def test_dc_power_flow_hand_checkable():
	susceptance = np.array([[10.0, -5.0, -5.0], [-5.0, 10.0, -5.0], [-5.0, -5.0, 10.0]])
	injection = np.array([1.0, 0.0, -1.0])
	expected = np.array([0.0, -1.0 / 15.0, -2.0 / 15.0])
	got = K.dc_power_flow(susceptance, injection, 0)
	np.testing.assert_allclose(got, expected, **F64)
	np.testing.assert_allclose(ref_losses.dc_power_flow(susceptance, injection, 0), expected, **F64)
	# The slack angle is pinned to zero.
	assert got[0] == 0.0


def test_dc_power_flow_randomised_conserves_power():
	rng = np.random.default_rng(53)
	n = 6
	base = rng.normal(size=(n, n))
	susceptance = (base + base.T) / 2.0 + n * np.eye(n)
	injection = rng.normal(size=n)
	slack = 2
	got = K.dc_power_flow(susceptance, injection, slack)
	want = ref_losses.dc_power_flow(susceptance, injection, slack)
	np.testing.assert_allclose(got, want, **F64)
	# Power is conserved at every non-slack bus: (B theta)_i == P_i.
	product = susceptance @ got
	for i in range(n):
		if i != slack:
			np.testing.assert_allclose(product[i], injection[i], **F64)


def test_dc_power_flow_singular_system_raises():
	# Bus 1 is disconnected from the slack: the reduced system is singular.
	susceptance = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
	injection = np.array([1.0, 0.0, -1.0])
	with pytest.raises(RuntimeError):
		K.dc_power_flow(susceptance, injection, 0)


def test_branch_flows_hand_checkable():
	angles = np.array([0.0, -1.0 / 15.0, -2.0 / 15.0])
	branch_from = np.array([0, 1, 2], dtype=np.uint32)
	branch_to = np.array([1, 2, 0], dtype=np.uint32)
	branch_susceptance = np.array([5.0, 5.0, 5.0])
	expected = np.array([1.0 / 3.0, 1.0 / 3.0, -2.0 / 3.0])
	np.testing.assert_allclose(
		K.branch_flows(angles, branch_from, branch_to, branch_susceptance), expected, **F64
	)
	np.testing.assert_allclose(
		ref_losses.branch_flows(angles, branch_from, branch_to, branch_susceptance), expected, **F64
	)


def test_branch_flows_randomised():
	rng = np.random.default_rng(59)
	angles = rng.normal(size=5)
	branch_from = rng.integers(0, 5, 7).astype(np.uint32)
	branch_to = rng.integers(0, 5, 7).astype(np.uint32)
	branch_susceptance = rng.uniform(1.0, 10.0, 7)
	np.testing.assert_allclose(
		K.branch_flows(angles, branch_from, branch_to, branch_susceptance),
		ref_losses.branch_flows(angles, branch_from, branch_to, branch_susceptance),
		**F64,
	)


def test_decompose_losses_components_sum_to_total():
	"""The plan's §6.3 invariant, exact by construction in the reference."""
	cases = [
		(100.0, 90.0, 95.0, 98.0),
		(50.0, 20.0, 30.0, 40.0),
		(10.0, 10.0, 10.0, 10.0),
		(80.0, 100.0, 70.0, 90.0),
	]
	for actual, reference, load_only, topology_only in cases:
		got = K.decompose_losses(actual, reference, load_only, topology_only)
		want = ref_losses.decompose_losses(actual, reference, load_only, topology_only)
		for key in want:
			np.testing.assert_allclose(got[key], want[key], **F64)
		parts = got["load_driven"] + got["generation_driven"] + got["topology_driven"]
		np.testing.assert_allclose(parts, got["total"], **F64)


def test_transmission_losses_hand_checkable():
	# Three-phase line: I_line = S / (sqrt(3) V), P_loss = 3 I^2 R.
	# 100 MW over 0.1 ohm at 220 kV: I = 100 / (sqrt(3)*220) kA = 0.2624 kA,
	# P = 3 * 0.2624^2 * 0.1 = 0.020661 MW. This equals S^2 R / V^2.
	flows = np.array([100.0])
	resistance = np.array([0.1])
	voltage = np.array([220.0])
	expected = 100.0**2 * 0.1 / 220.0**2
	np.testing.assert_allclose(K.transmission_losses(flows, resistance, voltage), expected, **F64)
	np.testing.assert_allclose(
		ref_losses.transmission_losses(flows, resistance, voltage), expected, **F64
	)


def test_transmission_losses_are_below_the_flow_they_carry():
	"""A line cannot lose more power than it carries.

	The invariant a wrong unit constant violates. The shipped kernel returned
	`S^2 R / V^2 * 1000 / 3` -- 333x the physical loss -- so a 3-bus fixture
	reported a loss fraction of 1.377, meaning 138% of generated energy lost in
	transmission. A differential test could not see it: the Python reference
	carried the same constant. This asserts a physical bound instead, which no
	shared misreading can satisfy.

	The check is against a *realistic* line, because the bound is a property of
	the network rather than of the formula: 100 MW over 10 ohm at 220 kV is
	0.21% loss, and any figure near or above the flow is a unit error.
	"""
	flows = np.array([100.0, 250.0, 40.0])
	resistance = np.array([10.0, 4.0, 25.0])
	voltage = np.array([220.0, 132.0, 400.0])
	losses = np.asarray(
		[
			K.transmission_losses(np.array([f]), np.array([r]), np.array([v]))
			for f, r, v in zip(flows, resistance, voltage, strict=True)
		]
	)
	assert np.all(losses > 0.0), f"a loss cannot be negative or zero: {losses}"
	assert np.all(losses < flows), (
		f"loss {losses} MW is at or above the flow {flows} MW it is carried on; "
		f"a unit constant is wrong"
	)
	# And the physical magnitude: 100 MW over 10 ohm at 220 kV is 0.21%.
	np.testing.assert_allclose(losses[0], 100.0**2 * 10.0 / 220.0**2, **F64)


def test_transmission_losses_randomised_and_scaling():
	rng = np.random.default_rng(61)
	flows = rng.uniform(-500.0, 500.0, 8)
	resistance = rng.uniform(0.01, 0.5, 8)
	voltage = rng.uniform(110.0, 400.0, 8)
	np.testing.assert_allclose(
		K.transmission_losses(flows, resistance, voltage),
		ref_losses.transmission_losses(flows, resistance, voltage),
		**F64,
	)
	# Doubling the flow quadruples the loss (current squared).
	single = K.transmission_losses(np.array([100.0]), np.array([0.1]), np.array([220.0]))
	doubled = K.transmission_losses(np.array([200.0]), np.array([0.1]), np.array([220.0]))
	np.testing.assert_allclose(doubled, 4.0 * single, **F64)


# --------------------------------------------------------------------------
# alea-risk
# --------------------------------------------------------------------------


def test_var_cvar_hand_checkable():
	returns = np.array([-5.0, -3.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0])
	# losses sorted descending: 5, 3, 1, 0, ... tail count floor(8*0.25)+1 = 3.
	# VaR is the largest tail loss (1.0), CVaR the tail mean (3.0).
	got = K.var_cvar(returns, 0.75)
	assert got == (1.0, 3.0)
	assert ref_risk.var_cvar(returns, 0.75) == (1.0, 3.0)


def test_var_cvar_are_positive_loss_magnitudes():
	"""The pinned sign convention: CVaR >= VaR, both loss magnitudes."""
	rng = np.random.default_rng(67)
	returns = rng.normal(size=5000)
	var, cvar = K.var_cvar(returns, 0.95)
	assert var >= 0.0
	assert cvar >= var
	# The reference agrees on the value.
	ref_var, ref_cvar = ref_risk.var_cvar(returns, 0.95)
	np.testing.assert_allclose((var, cvar), (ref_var, ref_cvar), **F64)


def test_var_cvar_randomised():
	rng = np.random.default_rng(71)
	for n in (7, 9, 10, 20, 101, 1000):
		for confidence in (0.5, 0.75, 0.8, 0.9, 0.95, 0.99):
			returns = rng.normal(size=n)
			got = K.var_cvar(returns, confidence)
			want = ref_risk.var_cvar(returns, confidence)
			np.testing.assert_allclose(got, want, **F64)


def test_var_cvar_all_gains_gives_negative_var():
	# A sample whose worst cases are gains has a negative VaR; the kernel does
	# not invent a floor.
	got = K.var_cvar(np.array([1.0, 2.0, 3.0, 4.0]), 0.75)
	assert got == ref_risk.var_cvar(np.array([1.0, 2.0, 3.0, 4.0]), 0.75)


def test_cholesky_hand_checkable():
	matrix = np.array([[4.0, 2.0], [2.0, 3.0]])
	expected = np.array([[2.0, 0.0], [1.0, np.sqrt(2.0)]])
	np.testing.assert_allclose(K.cholesky(matrix), expected, **F64)
	np.testing.assert_allclose(ref_risk.cholesky(matrix), expected, **F64)
	# L @ L.T reproduces the matrix.
	np.testing.assert_allclose(K.cholesky(matrix) @ K.cholesky(matrix).T, matrix, **F64)


def test_cholesky_rejects_non_positive_definite():
	with pytest.raises(RuntimeError):
		K.cholesky(np.array([[1.0, 2.0], [2.0, 1.0]]))
	with pytest.raises(ValueError):
		ref_risk.cholesky(np.array([[1.0, 2.0], [2.0, 1.0]]))


def test_cholesky_randomised():
	rng = np.random.default_rng(73)
	base = rng.normal(size=(4, 4))
	matrix = base @ base.T + 4.0 * np.eye(4)
	np.testing.assert_allclose(K.cholesky(matrix), ref_risk.cholesky(matrix), **F64)


def test_correlation_from_covariance_hand_checkable():
	covariance = np.array([[4.0, 2.0], [2.0, 9.0]])
	stds = np.array([2.0, 3.0])
	expected = np.array([[1.0, 1.0 / 3.0], [1.0 / 3.0, 1.0]])
	np.testing.assert_allclose(K.correlation_from_covariance(covariance, stds), expected, **F64)
	np.testing.assert_allclose(ref_risk.correlation_from_covariance(covariance, stds), expected, **F64)


def test_correlation_from_covariance_randomised_and_edges():
	rng = np.random.default_rng(79)
	base = rng.normal(size=(3, 3))
	covariance = base @ base.T + np.eye(3)
	stds = np.sqrt(np.diag(covariance))
	got = K.correlation_from_covariance(covariance, stds)
	np.testing.assert_allclose(got, ref_risk.correlation_from_covariance(covariance, stds), **F64)
	np.testing.assert_allclose(np.diag(got), np.ones(3), **F64)
	# A zero standard deviation is refused.
	with pytest.raises(ValueError):
		K.correlation_from_covariance(np.eye(2), np.array([0.0, 1.0]))


def test_exceedance_probability_hand_checkable():
	returns = np.array([-1.0, -2.0, 3.0, 4.0])
	# losses 1, 2, -3, -4; strictly greater than 1.5 -> only the loss 2 -> 1/4.
	assert K.exceedance_probability(returns, 1.5) == 0.25
	assert ref_risk.exceedance_probability(returns, 1.5) == 0.25
	# The threshold is a magnitude: +3 and -3 give the same answer.
	assert K.exceedance_probability(returns, -1.5) == K.exceedance_probability(returns, 1.5)
	# Strict inequality: a loss exactly at the threshold does not count.
	assert K.exceedance_probability(np.array([-3.0]), 3.0) == 0.0


def test_exceedance_probability_randomised():
	rng = np.random.default_rng(83)
	returns = rng.normal(size=200)
	for threshold in (-1.0, 0.0, 0.5, 1.0, 2.0):
		np.testing.assert_allclose(
			K.exceedance_probability(returns, threshold),
			ref_risk.exceedance_probability(returns, threshold),
			**F64,
		)


def test_portfolio_returns_hand_checkable():
	returns = np.array([[0.01, 0.02], [0.03, 0.04], [0.05, 0.06]])
	weights = np.array([0.5, 0.5])
	expected = np.array([0.015, 0.035, 0.055])
	np.testing.assert_allclose(K.portfolio_returns(returns, weights), expected, **F64)
	np.testing.assert_allclose(ref_risk.portfolio_returns(returns, weights), expected, **F64)


def test_portfolio_returns_does_not_normalise_weights():
	returns = np.array([[0.01, 0.02], [0.03, 0.04]])
	weights = np.array([2.0, 0.5])
	expected = np.array([0.03, 0.08])
	np.testing.assert_allclose(K.portfolio_returns(returns, weights), expected, **F64)


def test_portfolio_returns_randomised():
	rng = np.random.default_rng(89)
	returns = rng.normal(size=(50, 4))
	weights = rng.uniform(-1.0, 2.0, 4)
	np.testing.assert_allclose(
		K.portfolio_returns(returns, weights), ref_risk.portfolio_returns(returns, weights), **F64
	)


# --------------------------------------------------------------------------
# alea-dedup
# --------------------------------------------------------------------------


def test_minhash_is_deterministic_for_a_seed():
	text = "the quick brown fox jumps over the lazy dog"
	first = K.minhash(text, 5, 64, 0)
	second = K.minhash(text, 5, 64, 0)
	assert np.array_equal(first, second)
	# A different seed gives a different signature.
	assert not np.array_equal(first, K.minhash(text, 5, 64, 1))


def test_minhash_reference_properties():
	"""Properties the reference must satisfy, independent of the hash family."""
	text = "the quick brown fox jumps over the lazy dog"
	assert np.array_equal(ref_dedup.minhash(text, 5, 64, 0), ref_dedup.minhash(text, 5, 64, 0))
	assert not np.array_equal(ref_dedup.minhash(text, 5, 64, 0), ref_dedup.minhash(text, 5, 64, 1))
	# Case-insensitive and whitespace-insensitive, as the shingling is defined.
	assert np.array_equal(
		ref_dedup.minhash("ABC", 1, 32, 0), ref_dedup.minhash("abc", 1, 32, 0)
	)
	assert np.array_equal(
		ref_dedup.minhash("a b", 1, 32, 0), ref_dedup.minhash("  a   b  ", 1, 32, 0)
	)
	# Empty document: every position is the sentinel, so two empty documents
	# collide.
	assert np.array_equal(
		ref_dedup.minhash("", 3, 16, 0), np.array([2**64 - 1] * 16, dtype=np.uint64)
	)


def test_minhash_kernel_identical_documents_collide():
	text = "identical documents always collide"
	assert np.array_equal(K.minhash(text, 5, 128, 0), K.minhash(text, 5, 128, 0))
	assert K.jaccard_estimate(K.minhash(text, 5, 128, 0), K.minhash(text, 5, 128, 0)) == 1.0


def test_jaccard_estimate_hand_checkable():
	a = np.array([1, 2, 3, 4], dtype=np.uint64)
	b = np.array([1, 2, 3, 4], dtype=np.uint64)
	assert K.jaccard_estimate(a, b) == 1.0
	c = np.array([1, 2, 9, 4], dtype=np.uint64)
	assert K.jaccard_estimate(a, c) == 0.75
	# Different lengths are NaN, not an error.
	assert np.isnan(K.jaccard_estimate(a, a[:2]))


def test_jaccard_estimate_reference_matches_kernel_on_shared_signatures():
	# The estimate is a property of the signatures, so both must agree when fed
	# the same input.
	rng = np.random.default_rng(97)
	a = rng.integers(0, 1000, 64).astype(np.uint64)
	b = rng.integers(0, 1000, 64).astype(np.uint64)
	np.testing.assert_allclose(K.jaccard_estimate(a, b), ref_dedup.jaccard_estimate(a, b), **F64)
	assert np.isnan(ref_dedup.jaccard_estimate(a, a[:10]))


def test_deduplicate_groups_identical_and_keeps_first_id():
	documents = [
		("first", "the quick brown fox jumps over the lazy dog"),
		("second", "the quick brown fox jumps over the lazy dog"),
		("third", "a completely different sentence about energy systems"),
	]
	got = K.deduplicate(documents, 5, 128, 0.7, 0)
	want = ref_dedup.deduplicate(documents, 5, 128, 0.7, 0)
	assert got == want
	# The representative is the first id in input order.
	assert got[0] == ["first", "second"]


def test_deduplicate_splits_unrelated_documents():
	documents = [
		("a", "completely different sentence about energy systems in kenya"),
		("b", "unrelated text concerning tariffs and regulation"),
	]
	got = K.deduplicate(documents, 5, 128, 0.7, 0)
	assert got == [["a"], ["b"]]
	assert got == ref_dedup.deduplicate(documents, 5, 128, 0.7, 0)


def test_deduplicate_empty_documents_group():
	documents = [("e", ""), ("f", "")]
	assert K.deduplicate(documents, 3, 32, 0.5, 0) == [["e", "f"]]
	assert ref_dedup.deduplicate(documents, 3, 32, 0.5, 0) == [["e", "f"]]


def test_deduplicate_empty_input():
	assert K.deduplicate([], 3, 32, 0.5, 0) == []


def test_deduplicate_is_deterministic():
	documents = [
		("d1", "alpha beta gamma delta epsilon zeta"),
		("d2", "alpha beta gamma delta epsilon zeta"),
		("d3", "one two three four five six seven"),
	]
	first = K.deduplicate(documents, 3, 64, 0.5, 42)
	second = K.deduplicate(documents, 3, 64, 0.5, 42)
	assert first == second


def test_optimal_bands_rows_matches_reference():
	"""Every split is scored by the S-curve's step, not its midpoint.

	`num_perm = 1` and prime `num_perm` are included deliberately: the only
	split is `(1, num_perm)`, and a reference that initialised its best score to
	`0.0` rather than `-inf` would return nothing for them, since the step at a
	threshold of 0.9 is negative.
	"""
	for threshold in (0.3, 0.5, 0.7, 0.75, 0.8, 0.9, 0.95, 0.99):
		for num_perm in (1, 2, 3, 7, 16, 32, 64, 128, 256, 1000):
			got = K.optimal_bands_rows(threshold, num_perm)
			expected = ref_dedup.optimal_bands_rows(threshold, num_perm)
			assert got == expected, (
				f"threshold={threshold} num_perm={num_perm}: kernel {got} != reference {expected}"
			)


def test_optimal_bands_rows_product_is_num_perm():
	"""The structural contract, asserted alongside the values above."""
	for threshold in (0.5, 0.7, 0.8, 0.9):
		for num_perm in (64, 128, 256):
			bands, rows = K.optimal_bands_rows(threshold, num_perm)
			assert bands > 0 and rows > 0
			assert bands * rows == num_perm


# --------------------------------------------------------------------------
# alea-losses: contingency sweep
# --------------------------------------------------------------------------


def test_contingency_sweep_shape_and_no_escalation():
	susceptance = np.array([[10.0, -5.0, -5.0], [-5.0, 10.0, -5.0], [-5.0, -5.0, 10.0]])
	base_injection = np.array([[1.0, 0.0, -1.0], [2.0, 0.0, -2.0]])
	branch_from = np.array([0, 1, 2], dtype=np.uint32)
	branch_to = np.array([1, 2, 0], dtype=np.uint32)
	branch_susceptance = np.array([5.0, 5.0, 5.0])
	ratings = np.array([1000.0, 1000.0, 1000.0])
	result = K.contingency_sweep(
		susceptance, base_injection, branch_from, branch_to, branch_susceptance, ratings, 0
	)
	# One row per branch plus the base case, one column per snapshot.
	assert result["energy_not_served"].shape == (4, 2)
	assert result["overloaded_branches"].shape == (4, 2)
	assert result["diverged"].shape == (4, 2)
	# With generous ratings nothing is overloaded and nothing diverges.
	assert not result["diverged"].any()
	assert (result["overloaded_branches"] == 0).all()


def test_contingency_sweep_inputs_are_untouched():
	"""The plan's §6.2: a failed contingency must not corrupt the network."""
	susceptance = np.array([[10.0, -5.0], [-5.0, 5.0]])
	base_injection = np.array([[1.0, -1.0]])
	branch_from = np.array([0], dtype=np.uint32)
	branch_to = np.array([1], dtype=np.uint32)
	branch_susceptance = np.array([5.0])
	ratings = np.array([10.0])
	before = susceptance.copy()
	K.contingency_sweep(
		susceptance, base_injection, branch_from, branch_to, branch_susceptance, ratings, 0
	)
	np.testing.assert_array_equal(susceptance, before)


def test_contingency_sweep_hand_checkable_island():
	"""A radial chain: losing the far branch strands the load behind it.

	`0 - 1 - 2` with 50 MW of load at bus 2 and slack bus 0. Removing branch
	`(1, 2)` detaches bus 2, so the DC system is singular before any angle
	exists and the island's stranded load is what the sweep must report.
	Removing `(0, 1)` strands buses 1 and 2 together, which is the same 50 MW:
	generation at those buses is zero either way.
	"""
	susceptance = np.array([[1.0, -1.0, 0.0], [-1.0, 2.0, -1.0], [0.0, -1.0, 1.0]])
	base_injection = np.array([[50.0, 0.0, -50.0]])
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([1.0, 1.0])
	ratings = np.array([1000.0, 1000.0])
	result = K.contingency_sweep(
		susceptance, base_injection, branch_from, branch_to, branch_susceptance, ratings, 0
	)
	# Row 0 is the base case and serves everything.
	assert result["energy_not_served"][0, 0] == pytest.approx(0.0)
	assert not result["diverged"][0, 0]
	# Both single outages island a bus; neither carries a NaN.
	assert result["diverged"][1:, 0].all()
	np.testing.assert_allclose(result["energy_not_served"][1:, 0], [50.0, 50.0])
	assert not np.isnan(result["energy_not_served"]).any()
	# An islanding contingency reports no overload count -- there are no angles
	# to compute a flow from, and 0 is the honest figure rather than a guess.
	assert (result["overloaded_branches"][1:, 0] == 0).all()


def test_contingency_sweep_matches_reference_on_a_generic_network():
	"""Values, not just structure, on networks whose ratings are off the flows.

	The ratings are drawn away from the flows deliberately. `overloaded` counts
	strict `flow > rating`, and when a rating lands within one ULP of a flow the
	kernel's own Gaussian elimination and LAPACK disagree about which side of
	the comparison the exact value falls on -- `1.0000000000000002 > 1.0` in one
	and not the other. That is a boundary where two correct implementations
	differ, so it is not a defect and not something to pin.
	"""
	generator = np.random.default_rng(7)
	compared = 0
	for _ in range(120):
		n_buses = int(generator.integers(2, 7))
		raw = generator.normal(size=(n_buses, n_buses))
		susceptance = (raw + raw.T) / 2 + np.eye(n_buses) * n_buses
		n_branches = int(generator.integers(1, max(2, n_buses)))
		branch_from = generator.integers(0, n_buses, size=n_branches).astype(np.uint32)
		branch_to = generator.integers(0, n_buses, size=n_branches).astype(np.uint32)
		branch_susceptance = generator.uniform(0.5, 5.0, size=n_branches)
		ratings = generator.uniform(0.05, 50.0, size=n_branches)
		base_injection = generator.normal(size=(2, n_buses)) * 10.0

		got = K.contingency_sweep(
			susceptance, base_injection, branch_from, branch_to, branch_susceptance, ratings, 0
		)
		expected = ref_losses.contingency_sweep(
			susceptance, base_injection, branch_from, branch_to, branch_susceptance, ratings, 0
		)
		compared += 1
		np.testing.assert_allclose(
			got["energy_not_served"], expected["energy_not_served"], rtol=1e-9, atol=1e-12
		)
		np.testing.assert_array_equal(got["overloaded_branches"], expected["overloaded_branches"])
		np.testing.assert_array_equal(got["diverged"], expected["diverged"])
	assert compared == 120
