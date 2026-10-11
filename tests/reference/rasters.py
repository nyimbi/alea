# SPDX-License-Identifier: MIT
"""Reference implementation of the raster kernels (VIIRS and raster algebra).

Written from the contract in `alea._core.kernels` and `docs/plans/03-rust-core.md`
§3, as nested loops over small arrays. Not production code.

Pinned semantics encoded here, and why:

* **Cloud is NaN, not zero.** `detect_outages` returns NaN for a cloudy pixel,
  never 0.0. Cloud is "no information", and the docstring says collapsing it
  into "not an outage" is how a detector reports outages wherever it is cloudy.
* **Cloud confidence bits are 0-1 and are kept when `<= max_cloud_confidence`.**
  The plan's §3.4 warns the specification writes both `== 0` and `!= 0`; the
  pinned reading is that confidence 0 (`00`, confident clear) is kept and, with
  the default ceiling of 0, everything else is unusable.
* **The VZA bin is `floor(vza / bin_size_deg)`, in `[0, n_bins)`.** A negative
  sensor zenith is out of range and unusable; a value at or above
  `n_bins * bin_size_deg` clamps into the last bin.
* **`n_bins = ceil(90 / bin_size_deg)`.** With the default 5 deg that is 18.
* **The baseline is a quantile over observations in a bin.** Bins with no
  observation are NaN. NaN observations are skipped, not propagated.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

# The VIIRS sensor zenith range is 0..90 deg. The baseline's bin axis covers it.
MAX_ZENITH_DEG = 90.0


def _n_bins(bin_size_deg: float) -> int:
	"""Number of VZA bins covering [0, 90) at the given bin width."""
	if bin_size_deg <= 0:
		raise ValueError("bin_size_deg must be positive")
	return int(math.ceil(MAX_ZENITH_DEG / bin_size_deg))


def _bin_of(vza: float, bin_size_deg: float, n_bins: int) -> int | None:
	"""The bin a sensor zenith falls in, or None if it is unusable.

	Negative zeniths have no bin; zeniths past the last bin edge clamp into the
	last bin rather than being dropped.
	"""
	if not np.isfinite(vza) or vza < 0.0:
		return None
	idx = int(math.floor(vza / bin_size_deg))
	if idx >= n_bins:
		idx = n_bins - 1
	return idx


def _quantile_sorted(sorted_values: list[float], quantile: float) -> float:
	"""Linear-interpolation quantile over an already-sorted list."""
	n = len(sorted_values)
	if n == 0:
		return math.nan
	if n == 1:
		return sorted_values[0]
	pos = quantile * (n - 1)
	lo = int(math.floor(pos))
	hi = min(lo + 1, n - 1)
	frac = pos - lo
	return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def vza_baseline(
	radiance: NDArray[np.float32],
	sensor_zenith: NDArray[np.float32],
	month: NDArray[np.uint8],
	bin_size_deg: float = 5.0,
	quantile: float = 0.25,
) -> NDArray[np.float32]:
	"""Per-(pixel, VZA bin, month) baseline radiance.

	Returns `[12, n_bins, y, x]`, NaN where a bin had no observation.
	"""
	# Rebound to float64: the arithmetic below is float64 throughout. A fresh
	# name rather than reassigning the parameter, so the declared float32 (the
	# kernel's contract) stays visible and pyright does not read the widening as
	# a type error.
	radiance_f = np.asarray(radiance, dtype=np.float64)
	zenith_f = np.asarray(sensor_zenith, dtype=np.float64)
	month = np.asarray(month)
	n_time, ny, nx = radiance_f.shape
	n_bins = _n_bins(bin_size_deg)
	out = np.full((12, n_bins, ny, nx), np.nan, dtype=np.float64)

	# Collect the observations that fall in each (month, bin, pixel).
	buckets: dict[tuple[int, int, int, int], list[float]] = {}
	for t in range(n_time):
		m = int(month[t])
		if not 1 <= m <= 12:
			continue
		for y in range(ny):
			for x in range(nx):
				val = float(radiance_f[t, y, x])
				if not np.isfinite(val):
					continue
				b = _bin_of(float(zenith_f[t, y, x]), bin_size_deg, n_bins)
				if b is None:
					continue
				buckets.setdefault((m - 1, b, y, x), []).append(val)

	for (mi, b, y, x), values in buckets.items():
		values.sort()
		out[mi, b, y, x] = _quantile_sorted(values, quantile)
	return out.astype(np.float32)


def is_clear(cloud_bits: int, max_cloud_confidence: int) -> bool:
	"""Whether a `QF_Cloud_Mask` value counts as clear at the given ceiling.

	Bits 0-1 hold the confidence; 0 is confident clear. The ceiling is the
	largest confidence still treated as clear.
	"""
	return (int(cloud_bits) & 0b11) <= max_cloud_confidence


def detect_outages(
	radiance: NDArray[np.float32],
	baseline: NDArray[np.float32],
	month: NDArray[np.uint8],
	sensor_zenith: NDArray[np.float32],
	cloud_bits: NDArray[np.uint8],
	bin_size_deg: float = 5.0,
	threshold: float = 0.6,
	max_cloud_confidence: int = 0,
) -> NDArray[np.float32]:
	"""Flag pixels below `threshold * baseline`.

	Returns 1.0 flagged, 0.0 observed and clear, **NaN cloudy or unusable**.
	"""
	radiance_f = np.asarray(radiance, dtype=np.float64)
	baseline_f = np.asarray(baseline, dtype=np.float64)
	month = np.asarray(month)
	zenith_f = np.asarray(sensor_zenith, dtype=np.float64)
	cloud_bits = np.asarray(cloud_bits)
	n_time, ny, nx = radiance_f.shape
	n_bins = baseline_f.shape[1]
	out = np.full((n_time, ny, nx), np.nan, dtype=np.float64)

	for t in range(n_time):
		m = int(month[t])
		if not 1 <= m <= 12:
			continue
		for y in range(ny):
			for x in range(nx):
				# Unusable: cloudy, out-of-range zenith, or a missing input.
				if not is_clear(int(cloud_bits[t, y, x]), max_cloud_confidence):
					continue
				b = _bin_of(float(zenith_f[t, y, x]), bin_size_deg, n_bins)
				if b is None:
					continue
				rad = float(radiance_f[t, y, x])
				base = float(baseline_f[m - 1, b, y, x])
				if not (np.isfinite(rad) and np.isfinite(base)):
					continue
				out[t, y, x] = 1.0 if rad < threshold * base else 0.0
	return out.astype(np.float32)


def aggregate_to_zones(
	anomaly: NDArray[np.float32],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
) -> NDArray[np.float32]:
	"""Fraction of clear pixels flagged, per (time, zone).

	NaN where a zone had no clear pixels at that time. Only pixels whose anomaly
	is finite (clear, observed) enter the count, so the fraction's denominator
	is clear pixels, not all pixels.
	"""
	anomaly_f = np.asarray(anomaly, dtype=np.float64)
	zone_ids = np.asarray(zone_ids)
	n_time, ny, nx = anomaly_f.shape
	out = np.full((n_time, n_zones), np.nan, dtype=np.float64)
	for t in range(n_time):
		counts = [0] * n_zones
		flagged = [0] * n_zones
		for y in range(ny):
			for x in range(nx):
				val = float(anomaly_f[t, y, x])
				if not np.isfinite(val):
					continue
				z = int(zone_ids[y, x])
				if not 0 <= z < n_zones:
					continue
				counts[z] += 1
				if val > 0.5:  # flagged is exactly 1.0
					flagged[z] += 1
		for z in range(n_zones):
			if counts[z] > 0:
				out[t, z] = flagged[z] / counts[z]
	return out.astype(np.float32)


def block_sum(input: NDArray[np.float64], factor: int) -> NDArray[np.float64]:
	"""Block-sum a raster, keeping partial edge blocks.

	The output has `ceil(ny / factor)` rows and `ceil(nx / factor)` columns;
	the last block in each direction is short and its partial sum is kept.
	Dropping that remainder is how a coastal zone loses its population.
	"""
	input = np.asarray(input, dtype=np.float64)
	ny, nx = input.shape
	out_y = -(-ny // factor)  # ceil
	out_x = -(-nx // factor)
	out = np.zeros((out_y, out_x), dtype=np.float64)
	for oy in range(out_y):
		for ox in range(out_x):
			total = 0.0
			for i in range(oy * factor, min((oy + 1) * factor, ny)):
				for j in range(ox * factor, min((ox + 1) * factor, nx)):
					total += float(input[i, j])
			out[oy, ox] = total
	return out


def normalise_weights(input: NDArray[np.float64]) -> NDArray[np.float64]:
	"""Normalise a raster to sum to one.

	Non-finite entries are treated as zero weight (not as a NaN that poisons the
	whole normalisation); a raster with no finite value at all has nothing to
	normalise and raises, matching the kernel's refusal to call an empty
	reduction zero.
	"""
	input = np.asarray(input, dtype=np.float64)
	finite = np.isfinite(input)
	if not finite.any():
		raise ValueError("weights: no finite values")
	total = float(input[finite].sum())
	if total == 0.0:
		raise ValueError("weights: no finite values")
	out = np.where(finite, input, 0.0) / total
	return out
