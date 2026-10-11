# SPDX-License-Identifier: MIT
"""The Rust kernels, wrapped.

AD-2: this is the **only** place in the platform that imports the compiled
extension. Every other module calls these wrappers. The reason is that the
boundary is where shapes, dtypes and units are asserted, and a boundary with
many crossings is a boundary with many places to get it wrong.

Wrappers contain no algorithm. They validate, convert, call, and convert back.
If a wrapper is doing arithmetic, the arithmetic belongs in Rust.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

# `_rust` is a maturin-built extension (`alea._core._rust`), so it has no stub;
# pyright cannot resolve a symbol off it and reports the import itself. The
# module is real at runtime and `tests/ci/test_core_import.py` gates its
# surface, so the ignore is scoped to the static checker only.
from alea._core import _rust  # type: ignore[attr-defined]

# Re-export the extension's own version so an artefact can record which kernel
# build produced it without importing the private module.
__version__ = _rust.version()


class KernelError(RuntimeError):
	"""A kernel failed for a reason that is a property of the data."""


class KernelInputError(ValueError):
	"""A kernel was called with a shape, dtype, or range it cannot accept."""


def available() -> list[str]:
	"""The names of every kernel exposed by the compiled extension."""
	return sorted(name for name in dir(_rust) if not name.startswith("_"))


def _coerce(array: Any, dtype: Any, name: str) -> NDArray[Any]:
	"""Coerce to a C-contiguous array of the kernel's dtype.

	A non-contiguous view is copied rather than refused: a caller slicing a
	larger array along the wrong axis is common, and the copy is cheap next to
	the kernel. An array that is already correct is passed through untouched,
	which matters for a 10^9-element raster.

	Anything non-numeric is refused rather than silently cast, because
	`np.asarray(["a"], dtype=float)` raises a message about the string rather
	than about the argument the caller actually got wrong.
	"""
	try:
		out = np.ascontiguousarray(array, dtype=dtype)
	except (ValueError, TypeError) as exc:
		raise KernelInputError(f"{name}: cannot convert to {np.dtype(dtype)}: {exc}") from exc
	return out


def _f32(array: Any, name: str) -> NDArray[np.float32]:
	return _coerce(array, np.float32, name)


def _f64(array: Any, name: str) -> NDArray[np.float64]:
	return _coerce(array, np.float64, name)


def _u8(array: Any, name: str) -> NDArray[np.uint8]:
	return _coerce(array, np.uint8, name)


def _u32(array: Any, name: str) -> NDArray[np.uint32]:
	return _coerce(array, np.uint32, name)


def _u64(array: Any, name: str) -> NDArray[np.uint64]:
	return _coerce(array, np.uint64, name)


# --------------------------------------------------------------------------
# alea-rasters
# --------------------------------------------------------------------------


def vza_baseline(
	radiance: NDArray[np.float32],
	sensor_zenith: NDArray[np.float32],
	month: NDArray[np.uint8],
	bin_size_deg: float = 5.0,
	quantile: float = 0.25,
) -> NDArray[np.float32]:
	"""Per-(pixel, VZA bin, month) baseline radiance.

	`radiance` and `sensor_zenith` are `[time, y, x]`; `month` is `[time]` in
	1..=12. Returns `[12, n_bins, y, x]`, NaN where a bin had no observation.

	`radiance` must be the observed `DNB_BRDF_Corrected_NTL` band, never the
	gap-filled band: a gap-filled value where it was cloudy turns cloud into
	"no outage".
	"""
	return _rust.vza_baseline(
		_f32(radiance, "radiance"),
		_f32(sensor_zenith, "sensor_zenith"),
		_u8(month, "month"),
		float(bin_size_deg),
		float(quantile),
	)


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

	`cloud_bits` is `QF_Cloud_Mask`. Bits 0-1 are cloud confidence, and
	`max_cloud_confidence` is the ceiling: 0 keeps confident-clear only.

	Returns 1.0 flagged, 0.0 observed and clear, **NaN cloudy or unusable**.
	Cloud is "no information", not "reliable supply"; the two aggregate
	differently and collapsing them is how a detector reports outages wherever
	it is cloudy.
	"""
	return _rust.detect_outages(
		_f32(radiance, "radiance"),
		_f32(baseline, "baseline"),
		_u8(month, "month"),
		_f32(sensor_zenith, "sensor_zenith"),
		_u8(cloud_bits, "cloud_bits"),
		float(bin_size_deg),
		float(threshold),
		int(max_cloud_confidence),
	)


def aggregate_to_zones(
	anomaly: NDArray[np.float32],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
) -> NDArray[np.float32]:
	"""Fraction of clear pixels flagged, per (time, zone). NaN where no clear
	pixels."""
	return _rust.aggregate_to_zones(_f32(anomaly, "anomaly"), _u32(zone_ids, "zone_ids"), int(n_zones))


def block_sum(input: NDArray[np.float64], factor: int) -> NDArray[np.float64]:
	"""Block-sum a raster, keeping partial edge blocks.

	Dropping the remainder edge is how a coastal zone loses its population.
	"""
	return _rust.block_sum(_f64(input, "input"), int(factor))


def normalise_weights(input: NDArray[np.float64]) -> NDArray[np.float64]:
	"""Normalise a raster to sum to one, for use as a disaggregation weight."""
	return _rust.normalise_weights(_f64(input, "input"))


# --------------------------------------------------------------------------
# alea-dedup
# --------------------------------------------------------------------------


def minhash(text: str, k: int = 5, num_perm: int = 128, seed: int = 0) -> NDArray[np.uint64]:
	"""MinHash signature of a document.

	`seed` is required and has no default in the kernel: Python's string
	hashing is randomised per process, so an unseeded MinHash deduplicates
	differently on every run.
	"""
	return _rust.minhash(text, int(k), int(num_perm), int(seed))


def jaccard_estimate(a: NDArray[np.uint64], b: NDArray[np.uint64]) -> float:
	"""The Jaccard similarity two signatures estimate, or NaN if lengths differ."""
	return float(_rust.jaccard_estimate(_u64(a, "a"), _u64(b, "b")))


def deduplicate(
	documents: list[tuple[str, str]],
	k: int = 5,
	num_perm: int = 128,
	threshold: float = 0.7,
	seed: int = 0,
) -> list[list[str]]:
	"""Group near-duplicate documents.

	The first id in each group, in input order, is the representative: an
	official announcement ingested before a news report of it should be the one
	kept.
	"""
	return _rust.deduplicate(documents, int(k), int(num_perm), float(threshold), int(seed))


def optimal_bands_rows(threshold: float, num_perm: int) -> tuple[int, int]:
	"""The band and row counts LSH derives, whose product is `num_perm`."""
	return _rust.optimal_bands_rows(float(threshold), int(num_perm))


# --------------------------------------------------------------------------
# alea-series
# --------------------------------------------------------------------------


def aggregate(
	series: NDArray[np.float32],
	n_periods: int,
	period_length: int,
	seed: int = 0,
) -> tuple[NDArray[np.uint32], NDArray[np.uint32], NDArray[np.float64]]:
	"""Aggregate a series into representative periods.

	Returns `(assignments, representatives, weights)`. The weights sum to
	`n_timesteps` **exactly**; the kernel raises rather than returning a
	near-miss, because a weighting that sums to 8758 shifts every annual total
	by 0.02% and the shift is systematic across a study.
	"""
	return _rust.aggregate(_f32(series, "series"), int(n_periods), int(period_length), int(seed))


def load_duration_curve(series: NDArray[np.float32]) -> NDArray[np.float32]:
	"""Sorted-descending values per column."""
	return _rust.load_duration_curve(_f32(series, "series"))


def validate_aggregation(
	full_capacity: NDArray[np.float64],
	aggregated_capacity: NDArray[np.float64],
	full_cost: float,
	aggregated_cost: float,
	full_emissions: float,
	aggregated_emissions: float,
	full_peak_price: float,
	aggregated_peak_price: float,
) -> dict[str, float]:
	"""Compare an aggregated solve against a full-resolution one.

	AD-9's acceptance rule is applied by the caller; this returns the
	measurements.
	"""
	return dict(
		_rust.validate_aggregation(
			_f64(full_capacity, "full_capacity"),
			_f64(aggregated_capacity, "aggregated_capacity"),
			float(full_cost),
			float(aggregated_cost),
			float(full_emissions),
			float(aggregated_emissions),
			float(full_peak_price),
			float(aggregated_peak_price),
		)
	)


# --------------------------------------------------------------------------
# alea-losses
# --------------------------------------------------------------------------


def dc_power_flow(
	susceptance: NDArray[np.float64],
	injection: NDArray[np.float64],
	slack: int,
) -> NDArray[np.float64]:
	"""Bus angles from net injection, with the slack angle pinned to zero.

	A disconnected island makes the system singular and the kernel raises
	rather than returning a zero angle, which would read as "no flow" instead
	of "no path".
	"""
	return _rust.dc_power_flow(_f64(susceptance, "susceptance"), _f64(injection, "injection"), int(slack))


def branch_flows(
	angles: NDArray[np.float64],
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	branch_susceptance: NDArray[np.float64],
) -> NDArray[np.float64]:
	"""Branch flows in MW from bus angles."""
	return _rust.branch_flows(
		_f64(angles, "angles"),
		_u32(branch_from, "branch_from"),
		_u32(branch_to, "branch_to"),
		_f64(branch_susceptance, "branch_susceptance"),
	)


def contingency_sweep(
	susceptance: NDArray[np.float64],
	base_injection: NDArray[np.float64],
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	branch_susceptance: NDArray[np.float64],
	ratings: NDArray[np.float64],
	slack: int,
) -> dict[str, Any]:
	"""N-1 contingency sweep, one branch out at a time.

	Returns `energy_not_served`, `overloaded_branches` and `diverged`. The
	inputs are read-only throughout: a contingency that fails is recorded in
	`diverged` and the sweep continues, rather than leaving a branch
	deactivated for every later contingency.
	"""
	return dict(
		_rust.contingency_sweep(
			_f64(susceptance, "susceptance"),
			_f64(base_injection, "base_injection"),
			_u32(branch_from, "branch_from"),
			_u32(branch_to, "branch_to"),
			_f64(branch_susceptance, "branch_susceptance"),
			_f64(ratings, "ratings"),
			int(slack),
		)
	)


def decompose_losses(
	actual_losses: float,
	reference_losses: float,
	losses_with_actual_load_only: float,
	losses_with_actual_topology_only: float,
) -> dict[str, float]:
	"""Decompose losses into load-, generation- and topology-driven parts.

	The parts sum to the total by construction. A decomposition whose parts do
	not sum is worse than no decomposition, because it looks like an analysis.
	"""
	return dict(
		_rust.decompose_losses(
			float(actual_losses),
			float(reference_losses),
			float(losses_with_actual_load_only),
			float(losses_with_actual_topology_only),
		)
	)


def transmission_losses(
	flows: NDArray[np.float64],
	resistance: NDArray[np.float64],
	voltage_kv: NDArray[np.float64],
) -> float:
	"""Total transmission loss in MW. Scales with current squared."""
	return float(
		_rust.transmission_losses(
			_f64(flows, "flows"), _f64(resistance, "resistance"), _f64(voltage_kv, "voltage_kv")
		)
	)


# --------------------------------------------------------------------------
# alea-risk
# --------------------------------------------------------------------------


def var_cvar(returns: NDArray[np.float64], confidence: float = 0.95) -> tuple[float, float]:
	"""Value-at-Risk and Conditional VaR as **positive loss magnitudes**.

	The sign convention is the most common source of error in risk reporting:
	a negative VaR quoted as a loss flips the meaning of every number
	downstream. The kernel guarantees `CVaR >= VaR >= 0`.
	"""
	return _rust.var_cvar(_f64(returns, "returns"), float(confidence))


def cholesky(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
	"""The lower-triangular Cholesky factor.

	Raises naming the failing pivot when the matrix is not
	positive-definite, which a correlation matrix assembled from expert
	elicitation frequently is not.
	"""
	return _rust.cholesky(_f64(matrix, "matrix"))


def correlation_from_covariance(
	covariance: NDArray[np.float64], stds: NDArray[np.float64]
) -> NDArray[np.float64]:
	"""Correlation matrix from a covariance matrix and standard deviations."""
	return _rust.correlation_from_covariance(
		_f64(covariance, "covariance"), _f64(stds, "stds")
	)


def exceedance_probability(returns: NDArray[np.float64], threshold: float) -> float:
	"""The empirical probability that a loss exceeds a threshold."""
	return float(_rust.exceedance_probability(_f64(returns, "returns"), float(threshold)))


def portfolio_returns(
	returns: NDArray[np.float64], weights: NDArray[np.float64]
) -> NDArray[np.float64]:
	"""Portfolio return series from per-asset returns and weights.

	Weights are not normalised: a portfolio that is not fully invested is a
	real portfolio.
	"""
	return _rust.portfolio_returns(_f64(returns, "returns"), _f64(weights, "weights"))


__all__ = [
	"KernelError",
	"KernelInputError",
	"aggregate",
	"aggregate_to_zones",
	"available",
	"block_sum",
	"branch_flows",
	"cholesky",
	"contingency_sweep",
	"correlation_from_covariance",
	"dc_power_flow",
	"decompose_losses",
	"deduplicate",
	"detect_outages",
	"exceedance_probability",
	"jaccard_estimate",
	"load_duration_curve",
	"minhash",
	"normalise_weights",
	"optimal_bands_rows",
	"portfolio_returns",
	"transmission_losses",
	"validate_aggregation",
	"var_cvar",
	"vza_baseline",
]
