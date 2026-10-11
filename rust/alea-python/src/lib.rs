// SPDX-License-Identifier: MIT
//! The ALEA PyO3 extension module.
//!
//! One crate re-exports all five kernels as one extension module, so
//! `import alea_core` gives the whole Rust surface. Five separate extension
//! modules would mean five wheels to build, ship and version.
//!
//! This crate contains **no algorithm**. It converts between NumPy arrays and
//! ndarray views, calls a kernel, and converts typed errors into Python
//! exceptions. Every wrapper asserts its shapes at entry, because the Python
//! side's most likely mistake is a transposed or mismatched array and the
//! kernel's own error message is clearer than a NumPy broadcast failure three
//! frames later.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::AleaError;
use numpy::{
	IntoPyArray, PyArray1, PyArray2, PyArray3, PyArray4, PyReadonlyArray1, PyReadonlyArray2,
	PyReadonlyArray3, PyReadonlyArray4,
};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

/// Convert an [`AleaError`] into the Python exception that fits it.
///
/// A shape mismatch is the caller's mistake and becomes `ValueError`; anything
/// else is a numerical or structural failure and becomes `RuntimeError`. The
/// distinction matters because the first is a bug in the call and the second is
/// a property of the data.
fn to_py_err(error: AleaError) -> PyErr {
	match error {
		AleaError::ShapeMismatch { .. }
		| AleaError::LengthMismatch { .. }
		| AleaError::OutOfRange { .. }
		| AleaError::IndexOutOfBounds { .. } => PyValueError::new_err(error.to_string()),
		_ => PyRuntimeError::new_err(error.to_string()),
	}
}

// --------------------------------------------------------------------------
// alea-rasters
// --------------------------------------------------------------------------

/// Per-(pixel, VZA bin, month) baseline radiance.
///
/// `radiance` and `sensor_zenith` are `[time, y, x]` float32. `month` is
/// `[time]` uint8 holding 1..=12. Returns `[12, n_bins, y, x]` float32 with NaN
/// where a bin had no observation.
#[pyfunction]
#[pyo3(signature = (radiance, sensor_zenith, month, bin_size_deg=5.0, quantile=0.25))]
fn vza_baseline<'py>(
	py: Python<'py>,
	radiance: PyReadonlyArray3<'py, f32>,
	sensor_zenith: PyReadonlyArray3<'py, f32>,
	month: PyReadonlyArray1<'py, u8>,
	bin_size_deg: f32,
	quantile: f32,
) -> PyResult<Bound<'py, PyArray4<f32>>> {
	let radiance = radiance.as_array();
	let sensor_zenith = sensor_zenith.as_array();
	let month = month.as_array();
	let result = py
		.allow_threads(|| {
			alea_rasters::vza_baseline(radiance, sensor_zenith, month, bin_size_deg, quantile)
		})
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Flag pixels below `threshold * baseline`.
///
/// `cloud_bits` is `QF_Cloud_Mask`; bits 0-1 are cloud confidence.
/// `max_cloud_confidence` of 0 keeps confident-clear only. Returns `[time, y, x]`
/// float32: 1.0 flagged, 0.0 observed and clear, NaN cloudy or unusable.
#[pyfunction]
#[pyo3(signature = (radiance, baseline, month, sensor_zenith, cloud_bits, bin_size_deg=5.0, threshold=0.6, max_cloud_confidence=0))]
#[allow(clippy::too_many_arguments)]
fn detect_outages<'py>(
	py: Python<'py>,
	radiance: PyReadonlyArray3<'py, f32>,
	baseline: PyReadonlyArray4<'py, f32>,
	month: PyReadonlyArray1<'py, u8>,
	sensor_zenith: PyReadonlyArray3<'py, f32>,
	cloud_bits: PyReadonlyArray3<'py, u8>,
	bin_size_deg: f32,
	threshold: f32,
	max_cloud_confidence: u8,
) -> PyResult<Bound<'py, PyArray3<f32>>> {
	let radiance = radiance.as_array();
	let baseline = baseline.as_array();
	let month = month.as_array();
	let sensor_zenith = sensor_zenith.as_array();
	let cloud_bits = cloud_bits.as_array();
	let result = py
		.allow_threads(|| {
			alea_rasters::detect_outages(
				radiance,
				baseline,
				month,
				sensor_zenith,
				cloud_bits,
				bin_size_deg,
				threshold,
				max_cloud_confidence,
			)
		})
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Fraction of clear pixels flagged, per (time, zone). NaN where a zone had no
/// clear pixels.
#[pyfunction]
fn aggregate_to_zones<'py>(
	py: Python<'py>,
	anomaly: PyReadonlyArray3<'py, f32>,
	zone_ids: PyReadonlyArray2<'py, u32>,
	n_zones: usize,
) -> PyResult<Bound<'py, PyArray2<f32>>> {
	let anomaly = anomaly.as_array();
	let zone_ids = zone_ids.as_array();
	let result = py
		.allow_threads(|| alea_rasters::aggregate_to_zones(anomaly, zone_ids, n_zones))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Block-sum a raster to a coarser grid, keeping partial edge blocks.
#[pyfunction]
fn block_sum<'py>(
	py: Python<'py>,
	input: PyReadonlyArray2<'py, f64>,
	factor: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
	let input = input.as_array();
	let result = py
		.allow_threads(|| alea_rasters::block_sum(input, factor))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Normalise a raster so it sums to one, for use as a disaggregation weight.
#[pyfunction]
fn normalise_weights<'py>(
	py: Python<'py>,
	input: PyReadonlyArray2<'py, f64>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
	let input = input.as_array();
	let result = py
		.allow_threads(|| alea_rasters::normalise_weights(input))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

// --------------------------------------------------------------------------
// alea-dedup
// --------------------------------------------------------------------------

/// MinHash signature of a document: `num_perm` u64 hashes over `k`-word
/// shingles. `seed` is required so the result is reproducible across processes.
#[pyfunction]
fn minhash<'py>(
	py: Python<'py>,
	text: &str,
	k: usize,
	num_perm: usize,
	seed: u64,
) -> PyResult<Bound<'py, PyArray1<u64>>> {
	let result = py
		.allow_threads(|| alea_dedup::minhash(text, k, num_perm, seed))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// The Jaccard similarity two signatures estimate, or NaN if lengths differ.
#[pyfunction]
fn jaccard_estimate(a: PyReadonlyArray1<'_, u64>, b: PyReadonlyArray1<'_, u64>) -> PyResult<f64> {
	Ok(alea_dedup::jaccard_estimate(a.as_slice()?, b.as_slice()?))
}

/// Deduplicate a corpus. `documents` is a list of `(id, text)` pairs; returns
/// groups of ids, the first in input order being the representative.
#[pyfunction]
#[pyo3(signature = (documents, k=5, num_perm=128, threshold=0.7, seed=0))]
fn deduplicate(
	py: Python<'_>,
	documents: Vec<(String, String)>,
	k: usize,
	num_perm: usize,
	threshold: f64,
	seed: u64,
) -> PyResult<Vec<Vec<String>>> {
	py.allow_threads(|| alea_dedup::deduplicate(&documents, k, num_perm, threshold, seed))
		.map_err(to_py_err)
}

/// The band and row counts LSH derives for a threshold and permutation count.
#[pyfunction]
fn optimal_bands_rows(threshold: f64, num_perm: usize) -> PyResult<(usize, usize)> {
	Ok(alea_dedup::optimal_bands_rows(threshold, num_perm))
}

// --------------------------------------------------------------------------
// alea-series
// --------------------------------------------------------------------------

/// Aggregate a series into representative periods.
///
/// Returns `(assignments, representatives, weights)`. The weights sum to
/// `n_timesteps` exactly; this raises rather than returning a near-miss.
#[pyfunction]
#[pyo3(signature = (series, n_periods, period_length, seed=0))]
fn aggregate<'py>(
	py: Python<'py>,
	series: PyReadonlyArray2<'py, f32>,
	n_periods: usize,
	period_length: usize,
	seed: u64,
) -> PyResult<(Bound<'py, PyArray1<u32>>, Bound<'py, PyArray1<u32>>, Bound<'py, PyArray1<f64>>)> {
	let series = series.as_array();
	let result = py
		.allow_threads(|| alea_series::aggregate(series, n_periods, period_length, seed))
		.map_err(to_py_err)?;
	Ok((
		result.assignments.into_pyarray(py),
		result.representatives.into_pyarray(py),
		result.weights.into_pyarray(py),
	))
}

/// Load-duration curve: sorted-descending values per column.
#[pyfunction]
fn load_duration_curve<'py>(
	py: Python<'py>,
	series: PyReadonlyArray2<'py, f32>,
) -> PyResult<Bound<'py, PyArray2<f32>>> {
	let series = series.as_array();
	let result = py
		.allow_threads(|| alea_series::load_duration_curve(series))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Compare an aggregated solve against a full-resolution one. Returns a dict of
/// percentage errors.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn validate_aggregation<'py>(
	py: Python<'py>,
	full_capacity: PyReadonlyArray1<'py, f64>,
	aggregated_capacity: PyReadonlyArray1<'py, f64>,
	full_cost: f64,
	aggregated_cost: f64,
	full_emissions: f64,
	aggregated_emissions: f64,
	full_peak_price: f64,
	aggregated_peak_price: f64,
) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
	let full_capacity = full_capacity.as_slice()?;
	let aggregated_capacity = aggregated_capacity.as_slice()?;
	let validation = py
		.allow_threads(|| {
			alea_series::validate_aggregation(
				full_capacity,
				aggregated_capacity,
				full_cost,
				aggregated_cost,
				full_emissions,
				aggregated_emissions,
				full_peak_price,
				aggregated_peak_price,
			)
		})
		.map_err(to_py_err)?;
	let dict = pyo3::types::PyDict::new(py);
	dict.set_item("total_cost_error_pct", validation.total_cost_error_pct)?;
	dict.set_item("capacity_mix_l1_error_pct", validation.capacity_mix_l1_error_pct)?;
	dict.set_item("emissions_error_pct", validation.emissions_error_pct)?;
	dict.set_item("peak_price_error_pct", validation.peak_price_error_pct)?;
	Ok(dict)
}

// --------------------------------------------------------------------------
// alea-losses
// --------------------------------------------------------------------------

/// DC power flow: bus angles from net injection with the slack angle pinned.
#[pyfunction]
fn dc_power_flow<'py>(
	py: Python<'py>,
	susceptance: PyReadonlyArray2<'py, f64>,
	injection: PyReadonlyArray1<'py, f64>,
	slack: usize,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
	let susceptance = susceptance.as_array();
	let injection = injection.as_array();
	let result = py
		.allow_threads(|| alea_losses::dc_power_flow(susceptance, injection, slack))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Branch flows from bus angles.
#[pyfunction]
fn branch_flows<'py>(
	py: Python<'py>,
	angles: PyReadonlyArray1<'py, f64>,
	branch_from: PyReadonlyArray1<'py, u32>,
	branch_to: PyReadonlyArray1<'py, u32>,
	branch_susceptance: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
	let angles = angles.as_array();
	let branch_from = branch_from.as_array();
	let branch_to = branch_to.as_array();
	let branch_susceptance = branch_susceptance.as_array();
	let result = py
		.allow_threads(|| {
			alea_losses::branch_flows(angles, branch_from, branch_to, branch_susceptance)
		})
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// N-1 contingency sweep. Returns a dict of `energy_not_served`,
/// `overloaded_branches` and `diverged`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn contingency_sweep<'py>(
	py: Python<'py>,
	susceptance: PyReadonlyArray2<'py, f64>,
	base_injection: PyReadonlyArray2<'py, f64>,
	branch_from: PyReadonlyArray1<'py, u32>,
	branch_to: PyReadonlyArray1<'py, u32>,
	branch_susceptance: PyReadonlyArray1<'py, f64>,
	ratings: PyReadonlyArray1<'py, f64>,
	slack: usize,
) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
	let susceptance = susceptance.as_array();
	let base_injection = base_injection.as_array();
	let branch_from = branch_from.as_array();
	let branch_to = branch_to.as_array();
	let branch_susceptance = branch_susceptance.as_array();
	let ratings = ratings.as_array();
	let result = py
		.allow_threads(|| {
			alea_losses::contingency_sweep(
				susceptance,
				base_injection,
				branch_from,
				branch_to,
				branch_susceptance,
				ratings,
				slack,
			)
		})
		.map_err(to_py_err)?;
	let dict = pyo3::types::PyDict::new(py);
	dict.set_item("energy_not_served", result.energy_not_served.into_pyarray(py))?;
	dict.set_item("overloaded_branches", result.overloaded_branches.into_pyarray(py))?;
	dict.set_item("diverged", result.diverged.into_pyarray(py))?;
	Ok(dict)
}

/// Decompose losses into load-, generation- and topology-driven parts. The
/// parts sum to the total by construction.
#[pyfunction]
fn decompose_losses<'py>(
	py: Python<'py>,
	actual_losses: f64,
	reference_losses: f64,
	losses_with_actual_load_only: f64,
	losses_with_actual_topology_only: f64,
) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
	let decomposition = alea_losses::decompose_losses(
		actual_losses,
		reference_losses,
		losses_with_actual_load_only,
		losses_with_actual_topology_only,
	)
	.map_err(to_py_err)?;
	let dict = pyo3::types::PyDict::new(py);
	dict.set_item("load_driven", decomposition.load_driven)?;
	dict.set_item("generation_driven", decomposition.generation_driven)?;
	dict.set_item("topology_driven", decomposition.topology_driven)?;
	dict.set_item("total", decomposition.total)?;
	dict.set_item("sum_of_parts", decomposition.sum_of_parts())?;
	Ok(dict)
}

/// Total transmission loss in MW from flows, resistances and voltages.
#[pyfunction]
fn transmission_losses(
	flows: PyReadonlyArray1<'_, f64>,
	resistance: PyReadonlyArray1<'_, f64>,
	voltage_kv: PyReadonlyArray1<'_, f64>,
) -> PyResult<f64> {
	alea_losses::transmission_losses(flows.as_array(), resistance.as_array(), voltage_kv.as_array())
		.map_err(to_py_err)
}

// --------------------------------------------------------------------------
// alea-risk
// --------------------------------------------------------------------------

/// VaR and CVaR as positive loss magnitudes.
#[pyfunction]
fn var_cvar(returns: PyReadonlyArray1<'_, f64>, confidence: f64) -> PyResult<(f64, f64)> {
	alea_risk::var_cvar(returns.as_array(), confidence).map_err(to_py_err)
}

/// The lower-triangular Cholesky factor, or an error naming the failing pivot.
#[pyfunction]
fn cholesky<'py>(
	py: Python<'py>,
	matrix: PyReadonlyArray2<'py, f64>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
	let matrix = matrix.as_array();
	let result = py
		.allow_threads(|| alea_risk::cholesky(matrix))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// Correlation matrix from a covariance matrix and standard deviations.
#[pyfunction]
fn correlation_from_covariance<'py>(
	py: Python<'py>,
	covariance: PyReadonlyArray2<'py, f64>,
	stds: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
	let covariance = covariance.as_array();
	let stds = stds.as_array();
	let result = py
		.allow_threads(|| alea_risk::correlation_from_covariance(covariance, stds))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// The empirical probability that a loss exceeds a threshold.
#[pyfunction]
fn exceedance_probability(
	returns: PyReadonlyArray1<'_, f64>,
	threshold: f64,
) -> PyResult<f64> {
	Ok(alea_risk::exceedance_probability(returns.as_array(), threshold))
}

/// Portfolio return series from per-asset returns and weights.
#[pyfunction]
fn portfolio_returns<'py>(
	py: Python<'py>,
	returns: PyReadonlyArray2<'py, f64>,
	weights: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
	let returns = returns.as_array();
	let weights = weights.as_array();
	let result = py
		.allow_threads(|| alea_risk::portfolio_returns(returns, weights))
		.map_err(to_py_err)?;
	Ok(result.into_pyarray(py))
}

/// The crate version, so an artefact can record which kernel built it.
#[pyfunction]
fn version() -> &'static str {
	alea_common::VERSION
}

/// The ALEA Rust kernels.
///
/// The module name must match the last segment of `module-name` in
/// `[tool.maturin]`, which is `alea._core._rust`. A mismatch builds a wheel
/// whose `PyInit_` symbol Python cannot find, and the failure surfaces as an
/// ImportError at the first import rather than at build time.
#[pymodule]
fn _rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
	m.add_function(wrap_pyfunction!(version, m)?)?;

	m.add_function(wrap_pyfunction!(vza_baseline, m)?)?;
	m.add_function(wrap_pyfunction!(detect_outages, m)?)?;
	m.add_function(wrap_pyfunction!(aggregate_to_zones, m)?)?;
	m.add_function(wrap_pyfunction!(block_sum, m)?)?;
	m.add_function(wrap_pyfunction!(normalise_weights, m)?)?;

	m.add_function(wrap_pyfunction!(minhash, m)?)?;
	m.add_function(wrap_pyfunction!(jaccard_estimate, m)?)?;
	m.add_function(wrap_pyfunction!(deduplicate, m)?)?;
	m.add_function(wrap_pyfunction!(optimal_bands_rows, m)?)?;

	m.add_function(wrap_pyfunction!(aggregate, m)?)?;
	m.add_function(wrap_pyfunction!(load_duration_curve, m)?)?;
	m.add_function(wrap_pyfunction!(validate_aggregation, m)?)?;

	m.add_function(wrap_pyfunction!(dc_power_flow, m)?)?;
	m.add_function(wrap_pyfunction!(branch_flows, m)?)?;
	m.add_function(wrap_pyfunction!(contingency_sweep, m)?)?;
	m.add_function(wrap_pyfunction!(decompose_losses, m)?)?;
	m.add_function(wrap_pyfunction!(transmission_losses, m)?)?;

	m.add_function(wrap_pyfunction!(var_cvar, m)?)?;
	m.add_function(wrap_pyfunction!(cholesky, m)?)?;
	m.add_function(wrap_pyfunction!(correlation_from_covariance, m)?)?;
	m.add_function(wrap_pyfunction!(exceedance_probability, m)?)?;
	m.add_function(wrap_pyfunction!(portfolio_returns, m)?)?;

	Ok(())
}
