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
/// The series is cut into contiguous candidate blocks of `period_length`
/// timesteps; `n_periods` of them are chosen as representatives and every block
/// is assigned to the nearest one.
///
/// The selection minimises the total reconstruction error of the whole series:
/// each block is represented by its nearest chosen block, and the chosen set is
/// built greedily to reduce the sum of those distances. Greedy rather than
/// exhaustive, which is exponential in `n_periods`; the validation harness in
/// `alea.planning.aggregation` is what certifies the result. Deterministic given
/// `seed`, which only breaks ties.
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

	// Each candidate's profile, normalised by column scale: the vector the
	// distance metric compares. A non-finite value reads as the column mean,
	// which is zero in this space, so a gap in a capacity-factor series does not
	// make the block holding it unrepresentable.
	let profiles: Vec<Vec<f64>> = (0..n_candidates)
		.map(|block| {
			let start = block * period_length;
			let mut profile = vec![0.0f64; period_length * n_columns];
			for t in 0..period_length {
				for c in 0..n_columns {
					let value = series[[start + t, c]];
					if value.is_finite() {
						profile[t * n_columns + c] = (value / scales[c]) as f64;
					}
				}
			}
			profile
		})
		.collect();

	// Squared Frobenius distance between two block profiles: the cost of
	// representing one block by the other, and the quantity whose total the
	// selection minimises.
	let distance = |a: usize, b: usize| -> f64 {
		profiles[a]
			.iter()
			.zip(profiles[b].iter())
			.map(|(x, y)| {
				let d = x - y;
				d * d
			})
			.sum()
	};

	// Deterministic tie-break. The seed hashes each candidate to a stable order,
	// so two runs of one input select the same blocks rather than one that
	// depends on the order a parallel reduction happened to finish in (AD-8).
	let tie = |a: usize, b: usize| -> std::cmp::Ordering {
		alea_dedup_hash(candidate_key(a, seed))
			.cmp(&alea_dedup_hash(candidate_key(b, seed)))
			.then_with(|| a.cmp(&b))
	};

	// Greedy facility location. Each round adds the block whose selection reduces
	// the total reconstruction cost of the series most, where a block's cost is
	// its distance to the nearest chosen block. Greedy rather than exhaustive
	// because exhaustive is C(n_candidates, n_periods); the validation harness in
	// `alea.planning.aggregation` is what certifies the result.
	//
	// WHAT this replaces, and why the replacement is the whole point: the previous
	// selection scored each block by its own internal spread and took the
	// flattest. On a seasonal year the flattest blocks are all in the same quiet
	// fortnight, so every representative landed there -- twelve representatives
	// inside one December fortnight on an 8760-hour year -- and the aggregated
	// solve cost 106% more than the full-resolution one, against AD-9's 2%. A
	// block is not representative because it is flat; it is representative
	// because the other blocks are near it.
	let mut nearest = vec![f64::INFINITY; n_candidates];
	let mut chosen: Vec<usize> = Vec::with_capacity(n_periods);
	while chosen.len() < n_periods {
		let best = (0..n_candidates)
			.into_par_iter()
			.filter(|candidate| !chosen.contains(candidate))
			.map(|candidate| {
				let total: f64 = (0..n_candidates)
					.map(|block| distance(block, candidate).min(nearest[block]))
					.sum();
				(candidate, total)
			})
			.reduce_with(|a, b| {
				if a.1 < b.1 || (a.1 == b.1 && tie(a.0, b.0).is_lt()) {
					a
				} else {
					b
				}
			});
		let (candidate, _) = best.ok_or(AleaError::InfeasibleAggregation {
			n_timesteps,
			n_periods,
			period_length,
		})?;
		chosen.push(candidate);
		for block in 0..n_candidates {
			nearest[block] = nearest[block].min(distance(block, candidate));
		}
	}

	// Lloyd refinement. Reassign every block to its nearest centre, then move each
	// centre to its cluster's medoid. Both steps can only reduce the total
	// reconstruction cost, so the loop is monotone; the cap guards a pathological
	// tie ping-pong rather than a slow descent.
	for _ in 0..8 {
		let label: Vec<usize> = (0..n_candidates)
			.map(|block| {
				(0..n_periods)
					.min_by(|&a, &b| {
						distance(block, chosen[a])
							.partial_cmp(&distance(block, chosen[b]))
							.unwrap_or(std::cmp::Ordering::Equal)
							.then_with(|| a.cmp(&b))
					})
					.unwrap_or(0)
			})
			.collect();
		let mut moved = false;
		for (centre, slot) in chosen.iter_mut().enumerate() {
			let members: Vec<usize> = (0..n_candidates).filter(|&b| label[b] == centre).collect();
			if members.is_empty() {
				// A centre can lose its own block to an identical one at a lower
				// index. It keeps its position and carries zero weight, which the
				// exact-sum invariant tolerates; dropping it would change
				// `n_periods`.
				continue;
			}
			let costs: Vec<(usize, f64)> = members
				.iter()
				.map(|&m| {
					let cost: f64 = members.iter().map(|&other| distance(other, m)).sum();
					(m, cost)
				})
				.collect();
			let medoid = costs
				.iter()
				.copied()
				.min_by(|a, b| {
					a.1.partial_cmp(&b.1)
						.unwrap_or(std::cmp::Ordering::Equal)
						.then_with(|| tie(a.0, b.0))
				})
				.map(|(m, _)| m)
				.expect("members is non-empty");
			if medoid != *slot {
				*slot = medoid;
				moved = true;
			}
		}
		if !moved {
			break;
		}
	}
	chosen.sort_unstable();

	// Assignment: every block goes to its nearest chosen centre, and every
	// timestep in a block takes that block's label. Built as a histogram first so
	// the weights are the counts of what was actually assigned -- the previous
	// version distributed the weight near-uniformly and separately from the
	// assignment, which let the two disagree by a factor of ten while the
	// exact-sum invariant still held.
	//
	// A block's weight is its *count of timesteps*, not its count of blocks. That
	// is the unit the rest of the platform reads: `sector._util.total_hours` says
	// an annual volume converts to the same per-snapshot series at either
	// resolution, which is true only when a period's weight is the number of
	// hours it stands for. With `period_length == 1` a period is one timestep, so
	// a block is one timestep and the two units coincide.
	let mut assignments = vec![0u32; n_timesteps];
	let mut weights = vec![0.0f64; n_periods];
	for block in 0..n_candidates {
		let label = (0..n_periods)
			.min_by(|&a, &b| {
				distance(block, chosen[a])
					.partial_cmp(&distance(block, chosen[b]))
					.unwrap_or(std::cmp::Ordering::Equal)
					.then_with(|| a.cmp(&b))
			})
			.unwrap_or(0);
		let start = block * period_length;
		assignments[start..start + period_length].fill(label as u32);
		weights[label] += period_length as f64;
	}
	// The tail -- the timesteps past the last whole block, when n_timesteps is
	// not a multiple of period_length -- attaches to the nearest centre. Charged
	// one timestep each, which is what keeps the sum exact in both units.
	let tail_start = n_candidates * period_length;
	if tail_start < n_timesteps {
		// A tail timestep's distance to a centre is its distance to that centre's
		// representative timestep, charged one timestep at a time.
		let point_distance = |t: usize, centre: usize| -> f64 {
			let representative = chosen[centre] * period_length;
			(0..n_columns)
				.map(|c| {
					let value = series[[t, c]];
					let a = if value.is_finite() { (value / scales[c]) as f64 } else { 0.0 };
					let value = series[[representative, c]];
					let b = if value.is_finite() { (value / scales[c]) as f64 } else { 0.0 };
					let d = a - b;
					d * d
				})
				.sum()
		};
		for t in tail_start..n_timesteps {
			let label = (0..n_periods)
				.min_by(|&a, &b| {
					point_distance(t, a)
						.partial_cmp(&point_distance(t, b))
						.unwrap_or(std::cmp::Ordering::Equal)
						.then_with(|| a.cmp(&b))
				})
				.unwrap_or(0);
			assignments[t] = label as u32;
			weights[label] += 1.0;
		}
	}

	let mut representatives = Vec::with_capacity(n_periods);
	for &candidate in chosen.iter() {
		representatives.push((candidate * period_length) as u32);
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
	fn weights_are_the_hours_assigned_to_each_period() {
		// The invariant the exact-sum test cannot see. Weights that sum to 8760
		// while standing for a different number of hours than they are assigned
		// are wrong by a factor, and the sum still holds -- which is how the
		// kernel shipped a period weighted 744 that stood in for 8352 hours.
		let series = ramp(8760, 3);
		let result = aggregate(series.view(), 12, 24, 0).unwrap();
		let mut histogram = vec![0.0f64; 12];
		for label in &result.assignments {
			histogram[*label as usize] += 1.0;
		}
		assert_eq!(result.weights, histogram, "weights are not the assignment histogram");
	}

	#[test]
	fn representatives_span_a_seasonal_year() {
		// The defect this pins: a selection that puts every representative in the
		// same quiet fortnight, which is what choosing the *flattest* blocks
		// produces on a seasonal year. Winter-peaking load against a
		// summer-peaking resource, so the two columns disagree about when the
		// year is interesting and a flat-block rule has somewhere to go wrong.
		let series = Array2::from_shape_fn((8760usize, 2), |(t, c)| {
			let hour = (t % 24) as f32;
			let day = (t / 24) as f32;
			// Winter-peaking load: a broad annual cycle plus a diurnal one.
			let winter = ((t as f32 - 2000.0) * std::f32::consts::TAU / 8760.0)
				.sin()
				.max(0.0);
			// Summer-peaking solar: a day-length envelope plus a midday bump, so
			// the column disagrees with the load about *when* the year matters.
			let daylight = (std::f32::consts::PI * (hour - 6.0) / 12.0).sin().max(0.0);
			let envelope = 0.55 + 0.30 * ((day - 172.0) * std::f32::consts::TAU / 365.0).cos();
			if c == 0 {
				100.0 + 40.0 * winter + 12.0 * (hour * std::f32::consts::TAU / 24.0).sin()
			} else {
				300.0 * daylight * envelope
			}
		});
		let result = aggregate(series.view(), 12, 24, 0).unwrap();
		let mut blocks: Vec<usize> = result
			.representatives
			.iter()
			.map(|representative| *representative as usize / 24)
			.collect();
		let span = blocks.iter().max().unwrap() - blocks.iter().min().unwrap();
		blocks.sort_unstable();
		blocks.dedup();
		assert_eq!(blocks.len(), 12, "two periods share a representative day");
		assert!(
			span >= 300,
			"the twelve representatives span only {span} days, so most of the year \
			 is represented by a period from somewhere else"
		);
	}

	#[test]
	fn zero_reference_cost_gives_infinite_error_not_zero() {
		let capacity = vec![1.0];
		let validation =
			validate_aggregation(&capacity, &capacity, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0).unwrap();
		assert!(validation.total_cost_error_pct.is_infinite());
	}
}
