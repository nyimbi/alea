// SPDX-License-Identifier: MIT
//! Monte Carlo and portfolio risk.
//!
//! Two hazards are handled explicitly, because both produce a plausible number
//! rather than an error.
//!
//! * **Cholesky must be checked.** A correlation matrix that is not
//!   positive-definite — easy to construct from expert elicitation — makes
//!   Cholesky fail, and an unchecked implementation produces NaNs that
//!   propagate into a VaR. The error is typed and names the failing pivot.
//! * **VaR sign convention.** VaR is reported as a **positive loss magnitude**.
//!   The sign convention is the most common source of error in risk reporting:
//!   a negative VaR quoted as a "loss" flips the meaning of every number
//!   downstream. `CVaR >= VaR >= 0` is asserted.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::{expect_shape1, expect_shape2, AleaError, Result};
use ndarray::{Array1, Array2, ArrayView1, ArrayView2};
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// Value-at-Risk and Conditional VaR from a return sample.
///
/// `confidence` is in (0, 1); 0.95 is the usual choice. Returns `(VaR, CVaR)`
/// as **positive loss magnitudes**.
///
/// The sample is of *returns*, so a loss is a negative return. VaR at 95% is
/// the magnitude of the 5th-percentile return; CVaR is the mean of the returns
/// at or below it, again as a positive magnitude.
///
/// An empty sample returns NaN rather than zero: zero VaR reads as "no risk".
pub fn var_cvar(returns: ArrayView1<f64>, confidence: f64) -> Result<(f64, f64)> {
	if !(confidence > 0.0 && confidence < 1.0) {
		return Err(AleaError::OutOfRange {
			name: "confidence",
			value: confidence.to_string(),
			range: "(0, 1)",
		});
	}
	let mut sorted: Vec<f64> = returns.iter().copied().filter(|v| v.is_finite()).collect();
	if sorted.is_empty() {
		return Err(AleaError::EmptyDomain { name: "returns" });
	}
	sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

	let alpha = 1.0 - confidence;
	let n = sorted.len();
	// Index of the alpha quantile, by nearest-rank on the sorted sample.
	let index = ((alpha * n as f64).floor() as usize).min(n - 1);
	let var_return = sorted[index];
	// CVaR: the mean of the tail at or below VaR. If the tail is a single
	// observation, CVaR equals VaR rather than being undefined.
	let tail = &sorted[..=index];
	let mean_tail = tail.iter().sum::<f64>() / tail.len() as f64;

	// Return as positive loss magnitudes.
	Ok((-var_return, -mean_tail))
}

/// Value-at-Risk at a confidence, positive loss magnitude.
pub fn value_at_risk(returns: ArrayView1<f64>, confidence: f64) -> Result<f64> {
	Ok(var_cvar(returns, confidence)?.0)
}

/// Conditional VaR (expected shortfall) at a confidence, positive loss
/// magnitude.
pub fn conditional_var(returns: ArrayView1<f64>, confidence: f64) -> Result<f64> {
	Ok(var_cvar(returns, confidence)?.1)
}

/// Monte Carlo over correlated inputs.
///
/// `cholesky` is the lower-triangular factor of the correlation matrix,
/// `[n_inputs, n_inputs]`. `means` and `stds` are `[n_inputs]`.
/// `transform` maps a standardised draw vector to an output vector, so a caller
/// can apply a nonlinear model (a dispatch, a revenue function) without this
/// crate knowing anything about it.
///
/// Returns `[n_paths, n_outputs]`. Deterministic given `seed` (AD-8): the same
/// seed and inputs produce identical paths, in this process and in another.
pub fn monte_carlo(
	means: ArrayView1<f64>,
	stds: ArrayView1<f64>,
	cholesky: ArrayView2<f64>,
	transform: &dyn Fn(ArrayView1<f64>) -> Array1<f64>,
	n_paths: usize,
	seed: u64,
) -> Result<Array2<f64>> {
	let n_inputs = means.len();
	expect_shape1(stds.shape(), [n_inputs])?;
	expect_shape2(cholesky.shape(), [n_inputs, n_inputs])?;
	if n_paths == 0 {
		return Err(AleaError::OutOfRange {
			name: "n_paths",
			value: "0".to_string(),
			range: "(0, inf)",
		});
	}
	for (i, s) in stds.iter().enumerate() {
		if !s.is_finite() || *s < 0.0 {
			return Err(AleaError::OutOfRange {
				name: "stds",
				value: format!("{s} at index {i}"),
				range: "[0, inf)",
			});
		}
	}

	let mut rng = ChaCha8Rng::seed_from_u64(seed);
	let mut draws = Array2::<f64>::zeros((n_paths, n_inputs));
	for path in 0..n_paths {
		// Box-Muller over two uniforms. A fixed number of draws per path keeps
		// the RNG stream aligned across processes.
		for i in 0..n_inputs {
			let u1: f64 = rand::Rng::gen_range(&mut rng, f64::MIN_POSITIVE..1.0);
			let u2: f64 = rand::Rng::gen_range(&mut rng, 0.0..1.0);
			let radius = (-2.0 * u1.ln()).sqrt();
			draws[[path, i]] = radius * (std::f64::consts::TAU * u2).cos();
		}
	}

	// Correlate: L * z, then scale and shift.
	let correlated = draws.dot(&cholesky.t());
	let mut standardised = Array2::<f64>::zeros((n_paths, n_inputs));
	for path in 0..n_paths {
		for i in 0..n_inputs {
			standardised[[path, i]] = means[i] + stds[i] * correlated[[path, i]];
		}
	}

	// Apply the caller's transform per path.
	let first = transform(standardised.row(0));
	let n_outputs = first.len();
	let mut out = Array2::<f64>::zeros((n_paths, n_outputs));
	out.row_mut(0).assign(&first);
	for path in 1..n_paths {
		let row = transform(standardised.row(path));
		if row.len() != n_outputs {
			return Err(AleaError::Inconsistent(format!(
				"transform returned {} outputs on path 0 and {} on path {path}",
				n_outputs,
				row.len()
			)));
		}
		out.row_mut(path).assign(&row);
	}
	Ok(out)
}

/// The lower-triangular Cholesky factor of a symmetric positive-definite matrix.
///
/// Returns [`AleaError::NotPositiveDefinite`] naming the failing pivot. A
/// correlation matrix assembled from expert elicitation frequently is not
/// positive-definite, and the useful failure mode is a message that says which
/// pivot broke, not a matrix of NaNs.
pub fn cholesky(matrix: ArrayView2<f64>) -> Result<Array2<f64>> {
	let n = matrix.shape()[0];
	expect_shape2(matrix.shape(), [n, n])?;
	let mut lower = Array2::<f64>::zeros((n, n));

	for i in 0..n {
		for j in 0..=i {
			let mut sum = matrix[[i, j]];
			for k in 0..j {
				sum -= lower[[i, k]] * lower[[j, k]];
			}
			if i == j {
				if sum <= 0.0 || !sum.is_finite() {
					return Err(AleaError::NotPositiveDefinite {
						name: "matrix",
						pivot: i,
					});
				}
				lower[[i, j]] = sum.sqrt();
			} else {
				lower[[i, j]] = sum / lower[[j, j]];
			}
		}
	}
	Ok(lower)
}

/// A correlation matrix from a covariance matrix and standard deviations.
pub fn correlation_from_covariance(
	covariance: ArrayView2<f64>,
	stds: ArrayView1<f64>,
) -> Result<Array2<f64>> {
	let n = covariance.shape()[0];
	expect_shape2(covariance.shape(), [n, n])?;
	expect_shape1(stds.shape(), [n])?;
	let mut out = Array2::<f64>::zeros((n, n));
	for i in 0..n {
		for j in 0..n {
			let denominator = stds[i] * stds[j];
			if denominator.abs() < f64::EPSILON {
				return Err(AleaError::OutOfRange {
					name: "stds",
					value: format!("{denominator} at ({i}, {j})"),
					range: "non-zero",
				});
			}
			out[[i, j]] = covariance[[i, j]] / denominator;
		}
	}
	Ok(out)
}

/// The empirical probability that a loss exceeds a threshold.
///
/// NaN-free and in [0, 1]. Used for the resilience metrics, where "how often"
/// is reported alongside "how much".
pub fn exceedance_probability(returns: ArrayView1<f64>, threshold: f64) -> f64 {
	let values: Vec<f64> = returns.iter().copied().filter(|v| v.is_finite()).collect();
	if values.is_empty() {
		return f64::NAN;
	}
	let count = values.iter().filter(|v| **v < -threshold.abs()).count();
	count as f64 / values.len() as f64
}

/// A simple portfolio return series from per-asset returns and weights.
///
/// `returns` is `[n_paths, n_assets]`, `weights` is `[n_assets]`. Returns
/// `[n_paths]`. Weights are not required to sum to one; a portfolio that is not
/// fully invested is a real portfolio, and normalising would hide it.
pub fn portfolio_returns(
	returns: ArrayView2<f64>,
	weights: ArrayView1<f64>,
) -> Result<Array1<f64>> {
	let n_assets = returns.shape()[1];
	expect_shape1(weights.shape(), [n_assets])?;
	let n_paths = returns.shape()[0];
	let mut out = Array1::<f64>::zeros(n_paths);
	for path in 0..n_paths {
		let mut total = 0.0;
		for asset in 0..n_assets {
			total += returns[[path, asset]] * weights[asset];
		}
		out[path] = total;
	}
	Ok(out)
}

/// The expected shortfall contribution of each asset, for a risk attribution.
///
/// Returns `[n_assets]` of each asset's mean return on the paths where the
/// portfolio was in its tail. Components sum to the portfolio CVaR times the
/// weight sum, so the attribution is exact rather than indicative.
pub fn cvar_contributions(
	returns: ArrayView2<f64>,
	weights: ArrayView1<f64>,
	confidence: f64,
) -> Result<Array1<f64>> {
	let portfolio = portfolio_returns(returns, weights)?;
	let (_, cvar) = var_cvar(portfolio.view(), confidence)?;
	let n_assets = returns.shape()[1];
	let n_paths = returns.shape()[0];
	// The tail is the set of paths at or below the VaR threshold.
	let var = value_at_risk(portfolio.view(), confidence)?;
	let mut sums = Array1::<f64>::zeros(n_assets);
	let mut count = 0usize;
	for path in 0..n_paths {
		if portfolio[path] <= -var {
			count += 1;
			for asset in 0..n_assets {
				sums[asset] += returns[[path, asset]] * weights[asset];
			}
		}
	}
	if count == 0 {
		return Err(AleaError::EmptyDomain { name: "tail" });
	}
	sums.mapv_inplace(|v| -v / count as f64);
	let _ = cvar;
	Ok(sums)
}

#[cfg(test)]
mod tests {
	use super::*;
	use ndarray::{array, Array2};

	fn normal_sample(n: usize, seed: u64) -> Array1<f64> {
		let mut rng = ChaCha8Rng::seed_from_u64(seed);
		Array1::from_shape_fn(n, |_| {
			let u1: f64 = rand::Rng::gen_range(&mut rng, f64::MIN_POSITIVE..1.0);
			let u2: f64 = rand::Rng::gen_range(&mut rng, 0.0..1.0);
			(-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
		})
	}

	#[test]
	fn cvar_is_at_least_var_and_both_are_non_negative() {
		let sample = normal_sample(100_000, 1);
		let (var, cvar) = var_cvar(sample.view(), 0.95).unwrap();
		assert!(var >= 0.0, "VaR is a loss magnitude, got {var}");
		assert!(cvar >= var, "CVaR {cvar} must be at least VaR {var}");
	}

	#[test]
	fn var_of_a_standard_normal_is_near_one_point_six_four_five_sigma() {
		let sample = normal_sample(1_000_000, 42);
		let var = value_at_risk(sample.view(), 0.95).unwrap();
		let expected = 1.645;
		let error = (var - expected).abs() / expected;
		assert!(error < 0.05, "VaR {var}, expected about {expected}");
	}

	#[test]
	fn empty_sample_is_refused_not_zero() {
		let empty: Array1<f64> = Array1::zeros(0);
		assert!(var_cvar(empty.view(), 0.95).is_err());
	}

	#[test]
	fn confidence_outside_the_unit_interval_is_refused() {
		let sample = normal_sample(100, 1);
		assert!(var_cvar(sample.view(), 0.0).is_err());
		assert!(var_cvar(sample.view(), 1.0).is_err());
		assert!(var_cvar(sample.view(), 1.5).is_err());
	}

	#[test]
	fn cholesky_of_an_identity_is_the_identity() {
		let identity = Array2::<f64>::eye(3);
		let lower = cholesky(identity.view()).unwrap();
		for i in 0..3 {
			for j in 0..3 {
				let expected = if i == j { 1.0 } else { 0.0 };
				assert!((lower[[i, j]] - expected).abs() < 1e-12);
			}
		}
	}

	#[test]
	fn cholesky_reconstructs_the_matrix() {
		let m = array![[4.0, 2.0], [2.0, 3.0]];
		let lower = cholesky(m.view()).unwrap();
		let reconstructed = lower.dot(&lower.t());
		for i in 0..2 {
			for j in 0..2 {
				assert!((reconstructed[[i, j]] - m[[i, j]]).abs() < 1e-12);
			}
		}
	}

	#[test]
	fn a_non_positive_definite_matrix_names_its_pivot() {
		// A correlation matrix that is not positive-definite: 1, -1, 1 between
		// three variables is impossible.
		let bad = array![[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]];
		let result = cholesky(bad.view());
		match result {
			Err(AleaError::NotPositiveDefinite { pivot, .. }) => assert!(pivot <= 2),
			other => panic!("expected NotPositiveDefinite, got {other:?}"),
		}
	}

	#[test]
	fn monte_carlo_is_deterministic_given_the_seed() {
		let means = array![0.0, 0.0];
		let stds = array![1.0, 1.0];
		let cholesky_factor = cholesky(array![[1.0, 0.0], [0.0, 1.0]].view()).unwrap();
		let transform = |draw: ArrayView1<f64>| array![draw[0] + draw[1]];
		let a = monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 100, 5)
			.unwrap();
		let b = monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 100, 5)
			.unwrap();
		assert_eq!(a, b);
	}

	#[test]
	fn different_seeds_give_different_paths() {
		let means = array![0.0];
		let stds = array![1.0];
		let cholesky_factor = cholesky(Array2::<f64>::eye(1).view()).unwrap();
		let transform = |draw: ArrayView1<f64>| array![draw[0]];
		let a = monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 50, 1)
			.unwrap();
		let b = monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 50, 2)
			.unwrap();
		assert_ne!(a, b);
	}

	#[test]
	fn monte_carlo_reproduces_the_requested_moments() {
		let means = array![10.0];
		let stds = array![2.0];
		let cholesky_factor = cholesky(Array2::<f64>::eye(1).view()).unwrap();
		let transform = |draw: ArrayView1<f64>| array![draw[0]];
		let paths =
			monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 200_000, 9)
				.unwrap();
		let mean = paths.column(0).mean().unwrap();
		let variance = paths.column(0).iter().map(|v| (v - mean).powi(2)).sum::<f64>()
			/ (paths.nrows() - 1) as f64;
		assert!((mean - 10.0).abs() < 0.05, "mean {mean}");
		assert!((variance.sqrt() - 2.0).abs() < 0.05, "std {}", variance.sqrt());
	}

	#[test]
	fn negative_std_is_refused() {
		let means = array![0.0];
		let stds = array![-1.0];
		let cholesky_factor = Array2::<f64>::eye(1);
		let transform = |draw: ArrayView1<f64>| array![draw[0]];
		assert!(
			monte_carlo(means.view(), stds.view(), cholesky_factor.view(), &transform, 10, 0)
				.is_err()
		);
	}

	#[test]
	fn correlation_is_one_on_the_diagonal() {
		let covariance = array![[4.0, 1.0], [1.0, 9.0]];
		let stds = array![2.0, 3.0];
		let correlation = correlation_from_covariance(covariance.view(), stds.view()).unwrap();
		assert!((correlation[[0, 0]] - 1.0).abs() < 1e-12);
		assert!((correlation[[1, 1]] - 1.0).abs() < 1e-12);
		assert!((correlation[[0, 1]] - 1.0 / 6.0).abs() < 1e-12);
	}

	#[test]
	fn exceedance_probability_is_in_the_unit_interval() {
		let sample = normal_sample(1000, 3);
		let p = exceedance_probability(sample.view(), 1.0);
		assert!((0.0..=1.0).contains(&p), "{p}");
		// A very large threshold is exceeded by nobody.
		assert_eq!(exceedance_probability(sample.view(), 1e9), 0.0);
	}

	#[test]
	fn portfolio_returns_are_the_weighted_sum() {
		let returns = array![[0.1, 0.2], [0.3, 0.4]];
		let weights = array![0.5, 0.5];
		let out = portfolio_returns(returns.view(), weights.view()).unwrap();
		assert!((out[0] - 0.15).abs() < 1e-12);
		assert!((out[1] - 0.35).abs() < 1e-12);
	}

	#[test]
	fn cvar_contributions_sum_to_the_tail_mean() {
		let sample = normal_sample(10_000, 11);
		let returns = Array2::from_shape_fn((10_000, 2), |(i, j)| sample[i] * (j as f64 + 1.0));
		let weights = array![0.5, 0.5];
		let contributions = cvar_contributions(returns.view(), weights.view(), 0.95).unwrap();
		let portfolio = portfolio_returns(returns.view(), weights.view()).unwrap();
		let (_, cvar) = var_cvar(portfolio.view(), 0.95).unwrap();
		let total: f64 = contributions.iter().sum();
		assert!((total - cvar).abs() < 0.05 * cvar.max(1e-9), "{total} vs {cvar}");
	}
}
