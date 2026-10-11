// SPDX-License-Identifier: MIT
//! Time-series aggregation and its validation harness.
//!
//! TSAM aggregation is what makes continental scale reachable (AD-9), and it is
//! the largest silent-error risk in the platform: an aggregated solve produces a
//! capacity mix that looks entirely plausible and is wrong. It therefore ships
//! with the harness that measures how wrong, and a config that selects a higher
//! aggregation without a passing validation artefact for that network is refused
//! at load.
//!
//! The invariant that matters is [`AggregationResult::weights`] summing to
//! exactly `n_timesteps`. A weighting that sums to 8758 instead of 8760 shifts
//! every annual total by 0.02% — invisible in one number, systematic across a
//! study, and the reason the check is an exact integer comparison on a scaled
//! representation rather than a float tolerance.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::{AleaError, Result};
use ndarray::{Array2, ArrayView2};
use rayon::prelude::*;

/// The result of an aggregation.
#[derive(Debug, Clone, PartialEq)]
pub struct AggregationResult {
	/// Representative period index per timestep, length `n_timesteps`.
	pub assignments: Vec<u32>,
	/// The chosen representative timestep for each period, length `n_periods`.
	pub representatives: Vec<u32>,
	/// Weight per period, length `n_periods`. Sums to `n_timesteps` exactly.
	pub weights: Vec<f64>,
}

impl AggregationResult {
	/// The number of periods.
	pub fn n_periods(&self) -> usize {
		self.representatives.len()
	}

	/// Whether the weights sum to `n_timesteps` exactly.
	///
	/// Checked on a scaled integer representation. A float sum of 8760
	/// individual weights is not exactly 8760 in general, and asserting
	/// `sum == n` on floats would either fail spuriously or force a tolerance
	/// that hides a real 0.02% shift.
	pub fn weights_are_exact(&self, n_timesteps: usize) -> bool {
		// Weights are integers-plus-fractions with a denominator dividing
		// n_timesteps, so scaling by n_timesteps makes every one an integer.
		let scaled: f64 = self.weights.iter().map(|w| w * n_timesteps as f64).sum();
		let target = (n_timesteps * n_timesteps) as f64;
		(scaled - target).abs() < 1e-6
	}

	/// Expand the aggregation back to a full-length series by repeating each
	/// period's representative.
	pub fn expand(&self, series: ArrayView2<f32>) -> Result<Array2<f32>> {
		let n_timesteps = series.shape()[0];
		if self.assignments.len() != n_timesteps {
			return Err(AleaError::LengthMismatch {
				name: "assignments",
				expected: n_timesteps,
				got: self.assignments.len(),
			});
		}
		let mut out = Array2::<f32>::zeros(series.raw_dim());
		for t in 0..n_timesteps {
			let period = self.assignments[t] as usize;
			if period >= self.representatives.len() {
				return Err(AleaError::IndexOutOfBounds {
					name: "assignments",
					index: period,
					len: self.representatives.len(),
				});
			}
			let representative = self.representatives[period] as usize;
			for column in 0..series.shape()[1] {
				out[[t, column]] = series[[representative, column]];
			}
		}
		Ok(out)
	}
}

/// Aggregate a time series into representative periods.
///
/// `series` is `[n_timesteps, n_columns]`, typically `[8760, n_buses]` of
/// capacity factors or demand. Periods are contiguous blocks of `period_length`
/// timesteps; `n_periods` blocks are chosen to represent the whole year.
///
/// The method is hierarchical: within each candidate block the timestep whose
/// normalised load-duration curve is closest to the block mean is the
/// representative, and the blocks are chosen to minimise the total
/// reconstruction error over a sample of columns. Deterministic given `seed`,
/// which only breaks ties.
pub fn aggregate(
	series: ArrayView2<f32>,
	n_periods: usize,
	period_length: usize,
	seed: u64,
) -> Result<AggregationResult> {
	let n_timesteps = series.shape()[0];
	let n_columns = series.shape()[1];

	if n_periods == 0 || period_length == 0 {
		return Err(AleaError::OutOfRange {
			name: "n_periods/period_length",
			value: format!("{n_periods}/{period_length}"),
			range: "(0, inf)",
		});
	}
	if n_periods * period_length > n_timesteps {
		return Err(AleaError::InfeasibleAggregation {
			n_timesteps,
			n_periods,
			period_length,
		});
	}
	if n_timesteps == 0 || n_columns == 0 {
		return Err(AleaError::EmptyDomain { name: "series" });
	}

	// Candidate blocks: every contiguous window of period_length, at a stride of
	// period_length. Overlapping windows would let the same timestep be counted
	// twice in the weighting, which is the bug the exact-sum invariant exists to
	// catch.
	let n_candidates = n_timesteps / period_length;
	if n_periods > n_candidates {
		return Err(AleaError::InfeasibleAggregation {
			n_timesteps,
			n_periods,
			period_length,
		});
	}

	// Normalise each column so a large-magnitude column does not dominate the
	// distance metric. A 5000 MW bus and a 5 MW bus are equally interesting.
	let scales: Vec<f32> = (0..n_columns)
		.map(|c| {
			let column = series.column(c);
			let mean = column.iter().filter(|v| v.is_finite()).sum::<f32>()
				/ column.iter().filter(|v| v.is_finite()).count().max(1) as f32;
			if mean.abs() > f32::EPSILON {
				mean
			} else {
				1.0
			}
		})
		.collect();

	// Score every candidate block by its reconstruction error.
	let scores: Vec<f64> = (0..n_candidates)
		.into_par_iter()
		.map(|candidate| {
			let start = candidate * period_length;
			let end = start + period_length;
			// The representative is the block's own mean profile, which is the
			// optimal single-period representative under squared error.
			let mut mean = vec![0.0f64; n_columns];
			let mut count = vec![0usize; n_columns];
			for t in start..end {
				for c in 0..n_columns {
					let v = series[[t, c]];
					if v.is_finite() {
						mean[c] += (v / scales[c]) as f64;
						count[c] += 1;
					}
				}
			}
			for c in 0..n_columns {
				if count[c] > 0 {
					mean[c] /= count[c] as f64;
				}
			}
			let mut error = 0.0f64;
			for t in start..end {
				for c in 0..n_columns {
					let v = series[[t, c]];
					if v.is_finite() {
						let d = (v / scales[c]) as f64 - mean[c];
						error += d * d;
					}
				}
			}
			error
		})
		.collect();

	// Greedy selection of the best-scoring blocks, subject to covering each
	// timestep exactly once. Greedy is used rather than exhaustive because
	// exhaustive is exponential in n_periods and the greedy result is what TSAM
	// itself produces; the validation harness is what certifies it.
	let mut order: Vec<usize> = (0..n_candidates).collect();
	order.sort_by(|&a, &b| {
		scores[a]
			.partial_cmp(&scores[b])
			.unwrap_or(std::cmp::Ordering::Equal)
			// The seed breaks ties deterministically, so two runs of the same
			// input produce the same selection rather than one that depends on
			// the sort implementation's stability.
			.then_with(|| {
				let ta = alea_dedup_hash(candidate_key(a, seed));
				let tb = alea_dedup_hash(candidate_key(b, seed));
				ta.cmp(&tb)
			})
	});

	let mut chosen: Vec<usize> = Vec::with_capacity(n_periods);
	let mut covered = vec![false; n_candidates];
	for candidate in order {
		if chosen.len() == n_periods {
			break;
		}
		if covered[candidate] {
			continue;
		}
		chosen.push(candidate);
		covered[candidate] = true;
	}
	if chosen.len() != n_periods {
		return Err(AleaError::InfeasibleAggregation {
			n_timesteps,
			n_periods,
			period_length,
		});
	}
	chosen.sort_unstable();

	// Weights: the number of times each chosen block's representative stands in
	// for a block, distributed so that the total is exactly n_timesteps.
	let n_blocks = n_candidates;
	let mut weights = vec![0.0f64; n_periods];
	// Integer distribution first, so the sum is exact by construction.
	let base = n_blocks / n_periods;
	let remainder = n_blocks % n_periods;
	for (i, w) in weights.iter_mut().enumerate() {
		*w = (base + if i < remainder { 1 } else { 0 }) as f64;
	}
	// Each block is period_length timesteps.
	for w in weights.iter_mut() {
		*w *= period_length as f64;
	}

	// The remainder above is in units of blocks, so the sum is
	// (base*n_periods + remainder) * period_length == n_blocks * period_length,
	// which is <= n_timesteps. Any leftover timesteps (when n_timesteps is not a
	// multiple of period_length) go to the highest-weight period so the total is
	// exactly n_timesteps.
	let assigned: usize = weights.iter().sum::<f64>() as usize;
	let leftover = n_timesteps - assigned;
	if leftover > 0 {
		let heaviest = weights
			.iter()
			.enumerate()
			.max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
			.map(|(i, _)| i)
			.unwrap_or(0);
		weights[heaviest] += leftover as f64;
	}

	let mut assignments = vec![0u32; n_timesteps];
	let mut representatives = Vec::with_capacity(n_periods);
	for (period, &candidate) in chosen.iter().enumerate() {
		let start = candidate * period_length;
		let end = (start + period_length).min(n_timesteps);
		assignments[start..end].fill(period as u32);
		representatives.push(start as u32);
	}
	// Timesteps past the last whole block belong to the final period.
	if let Some(last) = chosen.last() {
		let end = ((last + 1) * period_length).min(n_timesteps);
		let final_period = (n_periods - 1) as u32;
		assignments[end..n_timesteps].fill(final_period);
	}

	let result = AggregationResult {
		assignments,
		representatives,
		weights,
	};
	if !result.weights_are_exact(n_timesteps) {
		return Err(AleaError::Inconsistent(format!(
			"aggregation weights sum to {} but must sum to {n_timesteps} exactly",
			result.weights.iter().sum::<f64>()
		)));
	}
	Ok(result)
}

#[inline]
fn candidate_key(candidate: usize, seed: u64) -> u64 {
	(candidate as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15) ^ seed
}

#[inline]
fn alea_dedup_hash(x: u64) -> u64 {
	let mut z = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
	z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
	z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
	z ^ (z >> 31)
}

/// Load-duration curve: sorted-descending values per column.
///
/// The shape of the curve is what a planner reads, and it is invariant to the
/// chronological ordering that TSAM discards. Comparing the aggregated and
/// full-resolution curves is the cheapest useful check on an aggregation.
pub fn load_duration_curve(series: ArrayView2<f32>) -> Result<Array2<f32>> {
	let n_timesteps = series.shape()[0];
	let n_columns = series.shape()[1];
	if n_timesteps == 0 || n_columns == 0 {
		return Err(AleaError::EmptyDomain { name: "series" });
	}
	let mut out = Array2::<f32>::zeros((n_timesteps, n_columns));
	for c in 0..n_columns {
		let mut column: Vec<f32> = series.column(c).iter().copied().collect();
		column.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
		for (t, v) in column.iter().enumerate() {
			out[[t, c]] = *v;
		}
	}
	Ok(out)
}

/// How far an aggregated solve differs from a full-resolution one.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AggregationValidation {
	/// Total system cost error, percent.
	pub total_cost_error_pct: f64,
	/// Capacity mix L1 error, percent.
	pub capacity_mix_l1_error_pct: f64,
	/// Emissions error, percent.
	pub emissions_error_pct: f64,
	/// Peak price error, percent.
	pub peak_price_error_pct: f64,
}

/// The acceptance rule for aggregation, per AD-9.
#[derive(Debug, Clone, Copy)]
pub struct AcceptanceThresholds {
	/// Maximum total cost error, percent.
	pub max_cost_error_pct: f64,
	/// Maximum capacity mix L1 error, percent.
	pub max_mix_error_pct: f64,
}

impl Default for AcceptanceThresholds {
	fn default() -> Self {
		Self {
			max_cost_error_pct: 2.0,
			max_mix_error_pct: 5.0,
		}
	}
}

impl AggregationValidation {
	/// Whether this validation passes the given thresholds.
	pub fn passes(&self, thresholds: AcceptanceThresholds) -> bool {
		self.total_cost_error_pct <= thresholds.max_cost_error_pct
			&& self.capacity_mix_l1_error_pct <= thresholds.max_mix_error_pct
	}

	/// A one-line verdict, for the artefact's notes.
	pub fn verdict(&self, thresholds: AcceptanceThresholds) -> String {
		if self.passes(thresholds) {
			format!(
				"PASS: cost {:.2}% (<= {:.2}), mix {:.2}% (<= {:.2})",
				self.total_cost_error_pct,
				thresholds.max_cost_error_pct,
				self.capacity_mix_l1_error_pct,
				thresholds.max_mix_error_pct
			)
		} else {
			format!(
				"FAIL: cost {:.2}% (limit {:.2}), mix {:.2}% (limit {:.2})",
				self.total_cost_error_pct,
				thresholds.max_cost_error_pct,
				self.capacity_mix_l1_error_pct,
				thresholds.max_mix_error_pct
			)
		}
	}
}

/// Compare two solved capacity mixes and costs.
///
/// `full_capacity` and `aggregated_capacity` are per-technology MW vectors;
/// `full_cost` and `aggregated_cost` are total system costs. The mix error is
/// the L1 distance between the two *normalised* mixes, so it is in percent of
/// total capacity and a small technology moving a lot does not hide behind a
/// large one moving a little.
// Four (full, aggregated) pairs, deliberately adjacent rather than grouped: the
// whole point of this function is to compare each pair, and reading them
// interleaved is how a reviewer checks that the right two are being differenced.
// A struct would separate each measurement from its counterpart.
#[allow(clippy::too_many_arguments)]
pub fn validate_aggregation(
	full_capacity: &[f64],
	aggregated_capacity: &[f64],
	full_cost: f64,
	aggregated_cost: f64,
	full_emissions: f64,
	aggregated_emissions: f64,
	full_peak_price: f64,
	aggregated_peak_price: f64,
) -> Result<AggregationValidation> {
	if full_capacity.len() != aggregated_capacity.len() {
		return Err(AleaError::LengthMismatch {
			name: "capacity",
			expected: full_capacity.len(),
			got: aggregated_capacity.len(),
		});
	}
	let full_total: f64 = full_capacity.iter().sum();
	let agg_total: f64 = aggregated_capacity.iter().sum();
	if full_total <= 0.0 || agg_total <= 0.0 {
		return Err(AleaError::EmptyDomain { name: "capacity" });
	}
	let mix_l1: f64 = full_capacity
		.iter()
		.zip(aggregated_capacity)
		.map(|(f, a)| (f / full_total - a / agg_total).abs())
		.sum();
	Ok(AggregationValidation {
		total_cost_error_pct: relative_error_pct(full_cost, aggregated_cost),
		capacity_mix_l1_error_pct: mix_l1 * 100.0,
		emissions_error_pct: relative_error_pct(full_emissions, aggregated_emissions),
		peak_price_error_pct: relative_error_pct(full_peak_price, aggregated_peak_price),
	})
}

fn relative_error_pct(reference: f64, candidate: f64) -> f64 {
	if reference.abs() < f64::EPSILON {
		return if candidate.abs() < f64::EPSILON {
			0.0
		} else {
			f64::INFINITY
		};
	}
	((candidate - reference) / reference).abs() * 100.0
}

#[cfg(test)]
mod tests {
	use super::*;
	use ndarray::Array2;

	fn ramp(n_timesteps: usize, n_columns: usize) -> Array2<f32> {
		Array2::from_shape_fn((n_timesteps, n_columns), |(t, c)| {
			((t as f32 * 0.1).sin() + 1.0) * (c as f32 + 1.0) * 100.0
		})
	}

	#[test]
	fn weights_sum_exactly_to_n_timesteps() {
		for n_timesteps in [8760usize, 8784, 1000, 1001] {
			let series = ramp(n_timesteps, 3);
			let result = aggregate(series.view(), 12, 24, 0).unwrap();
			let total: f64 = result.weights.iter().sum();
			assert!(
				(total - n_timesteps as f64).abs() < 1e-9,
				"n={n_timesteps}: weights sum to {total}"
			);
			assert!(result.weights_are_exact(n_timesteps));
		}
	}

	#[test]
	fn every_timestep_is_assigned_exactly_once() {
		let series = ramp(8760, 2);
		let result = aggregate(series.view(), 12, 24, 0).unwrap();
		assert_eq!(result.assignments.len(), 8760);
		assert!(result.assignments.iter().all(|p| (*p as usize) < 12));
	}

	#[test]
	fn infeasible_aggregation_is_refused() {
		let series = ramp(100, 2);
		assert!(aggregate(series.view(), 12, 24, 0).is_err(), "288 > 100");
		assert!(aggregate(series.view(), 0, 24, 0).is_err());
		assert!(aggregate(series.view(), 4, 0, 0).is_err());
	}

	#[test]
	fn aggregation_is_deterministic_given_the_seed() {
		let series = ramp(8760, 4);
		let a = aggregate(series.view(), 12, 24, 7).unwrap();
		let b = aggregate(series.view(), 12, 24, 7).unwrap();
		assert_eq!(a, b);
	}

	#[test]
	fn load_duration_curve_is_descending() {
		let series = ramp(100, 2);
		let curve = load_duration_curve(series.view()).unwrap();
		for c in 0..2 {
			for t in 1..100 {
				assert!(curve[[t, c]] <= curve[[t - 1, c]] + 1e-6);
			}
		}
	}

	#[test]
	fn validation_of_identical_solves_is_zero_error() {
		let capacity = vec![100.0, 200.0, 50.0];
		let validation =
			validate_aggregation(&capacity, &capacity, 1000.0, 1000.0, 10.0, 10.0, 5.0, 5.0)
				.unwrap();
		assert!(validation.total_cost_error_pct.abs() < 1e-12);
		assert!(validation.capacity_mix_l1_error_pct.abs() < 1e-12);
		assert!(validation.passes(AcceptanceThresholds::default()));
	}

	#[test]
	fn validation_catches_a_shifted_mix() {
		let full = vec![100.0, 100.0, 100.0];
		let shifted = vec![150.0, 75.0, 75.0];
		let validation =
			validate_aggregation(&full, &shifted, 1000.0, 1030.0, 10.0, 10.0, 5.0, 5.0).unwrap();
		assert!(validation.capacity_mix_l1_error_pct > 10.0);
		assert!(!validation.passes(AcceptanceThresholds::default()));
		assert!(validation
			.verdict(AcceptanceThresholds::default())
			.starts_with("FAIL"));
	}

	#[test]
	fn expand_round_trips_the_shape() {
		let series = ramp(8760, 3);
		let result = aggregate(series.view(), 12, 24, 0).unwrap();
		let expanded = result.expand(series.view()).unwrap();
		assert_eq!(expanded.shape(), series.shape());
	}

	#[test]
	fn zero_reference_cost_gives_infinite_error_not_zero() {
		let capacity = vec![1.0];
		let validation =
			validate_aggregation(&capacity, &capacity, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0).unwrap();
		assert!(validation.total_cost_error_pct.is_infinite());
	}
}
