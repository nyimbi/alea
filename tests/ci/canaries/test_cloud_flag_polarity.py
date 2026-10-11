# SPDX-License-Identifier: MIT
"""Canary: the cloud mask must be read as a *rejection*, not an admission.

VIIRS `QF_Cloud_Mask` carries cloud confidence in bits 0-1: 0 confident clear,
1 probably clear, 2 probably cloudy, 3 confident cloudy. `max_cloud_confidence`
is a ceiling -- a pixel is usable when its confidence is *at or below* it.

Inverted, the detector keeps cloudy pixels and discards clear ones: it reports
outages wherever it is cloudy and misses every real one. The output is still an
array of plausible numbers, which is what makes this worth a canary.

The gate is stated at `detect_outages`, the exported surface, not at the
internal `is_clear`. `is_clear` is not reachable from Python, so a canary
written against it would test a function no caller uses.

**No rebuild.** An earlier version mutated `lib.rs` and ran `maturin develop`.
That is unsafe: a process that dies between the mutation and the restoring
rebuild leaves an inverted kernel in the virtualenv, and every test afterwards
runs against it while looking normal. The gate's sensitivity is instead tested
against inverted predicates written in Python.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from tests.ci.canaries import REPO, assert_raises

LIB_RS = REPO / "rust" / "alea-rasters" / "src" / "lib.rs"

CONFIDENT_CLEAR, PROBABLY_CLEAR, PROBABLY_CLOUDY, CONFIDENT_CLOUDY = 0, 1, 2, 3


def usable(cloud_bits: int, ceiling: int) -> bool:
	"""The required semantics, written out so the gate has something to assert."""
	return (cloud_bits & 0b11) <= ceiling


def assert_cloud_semantics(predicate: Callable[[int, int], bool]) -> None:
	"""The gate: properties that must hold whatever the implementation.

	Each property catches a different way of being wrong:

	* a confident-clear pixel is usable at any usable ceiling;
	* a cloudy pixel is usable at none of them -- the polarity inversion;
	* the ceiling is a ceiling, so raising it admits the next band and no more.
	"""
	for ceiling in (0, 1):
		assert predicate(CONFIDENT_CLEAR, ceiling) is True, (
			f"confident-clear rejected at ceiling {ceiling}: clear sky is being "
			f"discarded as cloud"
		)
		for cloudy in (PROBABLY_CLOUDY, CONFIDENT_CLOUDY):
			assert predicate(cloudy, ceiling) is False, (
				f"cloud confidence {cloudy} admitted at ceiling {ceiling}: the "
				f"detector will flag outages wherever it is cloudy"
			)
	assert predicate(PROBABLY_CLEAR, 0) is False, "ceiling 0 must keep confident-clear only"
	assert predicate(PROBABLY_CLEAR, 1) is True, "ceiling 1 must additionally keep probably-clear"


def _inverted(cloud_bits: int, ceiling: int) -> bool:
	"""The defect: `>=` where `<=` belongs."""
	return (cloud_bits & 0b11) >= ceiling


def test_the_gate_accepts_the_correct_semantics():
	assert_cloud_semantics(usable)


def test_the_gate_rejects_the_polarity_inversion():
	"""Canary proper. If this passes, the gate is blind to the inversion."""
	error = assert_raises(AssertionError, assert_cloud_semantics, _inverted)
	assert "cloud" in str(error).lower()


def test_the_gate_rejects_dropping_clear_pixels():
	"""The other direction: keeping clouds is not the only way to be wrong."""

	def drops_clear(cloud_bits: int, ceiling: int) -> bool:
		return (cloud_bits & 0b11) < ceiling

	assert_raises(AssertionError, assert_cloud_semantics, drops_clear)


def _raster(cloud_bits: list[int]) -> dict[str, np.ndarray]:
	"""A one-pixel-per-confidence raster, all else held equal.

	Radiance is set well below any plausible baseline so every pixel would be
	flagged if the cloud mask did not intervene -- which is what makes the test
	about the mask rather than about the threshold.
	"""
	n = len(cloud_bits)
	return {
		"radiance": np.full((1, 1, n), 0.01, dtype=np.float32),
		# Baseline is [month, VZA bin, y, x]: 12 months, 12 five-degree bins,
		# and the spatial axes match radiance so a pixel's own baseline applies.
		"baseline": np.full((12, 12, 1, n), 1.0, dtype=np.float32),
		"month": np.array([1], dtype=np.uint8),
		"sensor_zenith": np.zeros((1, 1, n), dtype=np.float32),
		"cloud_bits": np.array(cloud_bits, dtype=np.uint8).reshape(1, 1, n),
	}


def test_the_shipped_kernel_reads_the_mask_as_a_ceiling():
	"""The assertion that matters: the real kernel, through the same properties."""
	core = pytest.importorskip("alea._core", reason="alea._core is not built")

	# `detect_outages` is the exported surface; `is_clear` is Rust-internal.
	# A cloudy pixel is NaN -- unusable -- and a clear one is 0.0 or 1.0.
	out = np.asarray(
		core.detect_outages(
			**_raster([CONFIDENT_CLEAR, PROBABLY_CLEAR, PROBABLY_CLOUDY, CONFIDENT_CLOUDY]),
			max_cloud_confidence=1,
		)
	).reshape(-1)
	assert not np.isnan(out[0]), "a confident-clear pixel was treated as unusable"
	assert not np.isnan(out[1]), "a probably-clear pixel was treated as unusable at ceiling 1"
	assert np.isnan(out[2]), "a probably-cloudy pixel was used: the mask is inverted"
	assert np.isnan(out[3]), "a confident-cloudy pixel was used: the mask is inverted"
	# Clear pixels below the threshold are flagged; that is the detector working.
	assert out[0] == 1.0 and out[1] == 1.0


def test_the_ceiling_is_a_ceiling():
	core = pytest.importorskip("alea._core", reason="alea._core is not built")
	out = np.asarray(
		core.detect_outages(**_raster([PROBABLY_CLEAR]), max_cloud_confidence=0)
	).reshape(-1)
	assert np.isnan(out[0]), "ceiling 0 must reject probably-clear, keeping confident-clear only"


def test_the_kernel_source_uses_the_correct_comparison():
	"""A source-level check, so an inversion is named even when the extension is absent."""
	source = LIB_RS.read_text()
	assert "confidence <= max_cloud_confidence" in source, (
		"the cloud-confidence comparison in the Rust kernel is not the expected "
		"`<=`; check for an inverted polarity"
	)
