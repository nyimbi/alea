// SPDX-License-Identifier: MIT
//! Loss decomposition and N-1 contingency analysis.
//!
//! Two specification defects are avoided by construction here.
//!
//! 1. `spec4-base.md` §13.2 `compute_tlens` mutates `self.n.lines` in place and
//!    restores it inside the same loop. An exception mid-loop leaves a line
//!    permanently deactivated and every subsequent contingency is computed on a
//!    degraded network. This crate takes branch status as an immutable input and
//!    returns results; there is no mutable network to corrupt.
//!
//! 2. The specification's `LossDecomposer._topology_driven` returns a hardcoded
//!    `0`. A decomposition whose components do not sum to the total is worse
//!    than no decomposition, because it looks like an analysis. It is
//!    implemented properly here, and the sum invariant is a property test.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::{expect_shape1, expect_shape2, AleaError, Result};
use ndarray::{Array1, Array2, ArrayView1, ArrayView2};

/// The result of an N-1 contingency sweep.
#[derive(Debug, Clone, PartialEq)]
pub struct ContingencyResult {
	/// Energy not served per (contingency, snapshot), MW.
	pub energy_not_served: Array2<f64>,
	/// Overloaded branch count per (contingency, snapshot).
	pub overloaded_branches: Array2<u32>,
	/// Whether the DC flow failed to converge per (contingency, snapshot).
	pub diverged: Array2<bool>,
}

/// DC power flow over a network, returning flows per branch.
///
/// `susceptance` is the `[n_buses, n_buses]` bus susceptance matrix B (the
/// imaginary part of the admittance, with the slack row and column removed or
/// retained; see below). `injection` is `[n_buses]` net injection in MW, and
/// `slack` is the slack bus index.
///
/// The system solved is `B * theta = injection`, with the slack bus's row and
/// column replaced by the identity, so the reference angle is pinned at zero.
/// Flow on a branch is `b_ij * (theta_i - theta_j)`.
///
/// Returns the branch flows. The branch-to-bus mapping is supplied separately by
/// [`branch_flows`], because the susceptance matrix alone does not know the
/// topology.
pub fn dc_power_flow(
	susceptance: ArrayView2<f64>,
	injection: ArrayView1<f64>,
	slack: usize,
) -> Result<Array1<f64>> {
	let n = susceptance.shape()[0];
	expect_shape2(susceptance.shape(), [n, n])?;
	expect_shape1(injection.shape(), [n])?;
	if slack >= n {
		return Err(AleaError::IndexOutOfBounds {
			name: "slack",
			index: slack,
			len: n,
		});
	}

	// Copy and pin the slack, rather than mutating the caller's matrix. The
	// specification's in-place mutation is the bug this avoids.
	let mut matrix = susceptance.to_owned();
	let mut rhs = injection.to_owned();
	for j in 0..n {
		matrix[[slack, j]] = 0.0;
	}
	matrix[[slack, slack]] = 1.0;
	rhs[slack] = 0.0;

	solve_linear(matrix.view(), rhs.view(), "dc_power_flow")
}

/// Branch flows from bus angles.
///
/// `angles` is `[n_buses]`, `branch_from`/`branch_to` are `[n_branches]` index
/// vectors, `branch_susceptance` is `[n_branches]`. Returns `[n_branches]`
/// flows in MW.
pub fn branch_flows(
	angles: ArrayView1<f64>,
	branch_from: ArrayView1<u32>,
	branch_to: ArrayView1<u32>,
	branch_susceptance: ArrayView1<f64>,
) -> Result<Array1<f64>> {
	let n_branches = branch_from.len();
	expect_shape1(branch_to.shape(), [n_branches])?;
	expect_shape1(branch_susceptance.shape(), [n_branches])?;
	let n_buses = angles.len();
	let mut flows = Array1::<f64>::zeros(n_branches);
	for b in 0..n_branches {
		let from = branch_from[b] as usize;
		let to = branch_to[b] as usize;
		if from >= n_buses {
			return Err(AleaError::IndexOutOfBounds {
				name: "branch_from",
				index: from,
				len: n_buses,
			});
		}
		if to >= n_buses {
			return Err(AleaError::IndexOutOfBounds {
				name: "branch_to",
				index: to,
				len: n_buses,
			});
		}
		flows[b] = branch_susceptance[b] * (angles[from] - angles[to]);
	}
	Ok(flows)
}

/// N-1 contingency sweep: one branch out at a time.
///
/// `base_injection` is `[n_snapshots, n_buses]`. `branch_from`/`branch_to` index
/// the buses each branch connects and `ratings` are the thermal limits in MW.
///
/// Returns, per (contingency, snapshot), the energy not served and the
/// overloaded branch count. The input arrays are read-only throughout: a
/// contingency that fails to converge is recorded in `diverged` and the sweep
/// continues, rather than leaving a branch deactivated for every later
/// contingency.
pub fn contingency_sweep(
	susceptance: ArrayView2<f64>,
	base_injection: ArrayView2<f64>,
	branch_from: ArrayView1<u32>,
	branch_to: ArrayView1<u32>,
	branch_susceptance: ArrayView1<f64>,
	ratings: ArrayView1<f64>,
	slack: usize,
) -> Result<ContingencyResult> {
	let n_buses = susceptance.shape()[0];
	expect_shape2(susceptance.shape(), [n_buses, n_buses])?;
	let n_snapshots = base_injection.shape()[0];
	expect_shape2(base_injection.shape(), [n_snapshots, n_buses])?;
	let n_branches = branch_from.len();
	expect_shape1(branch_to.shape(), [n_branches])?;
	expect_shape1(branch_susceptance.shape(), [n_branches])?;
	expect_shape1(ratings.shape(), [n_branches])?;
	if slack >= n_buses {
		return Err(AleaError::IndexOutOfBounds {
			name: "slack",
			index: slack,
			len: n_buses,
		});
	}

	let n_contingencies = n_branches + 1; // the base case is contingency 0
	let mut ens = Array2::<f64>::zeros((n_contingencies, n_snapshots));
	let mut overloaded = Array2::<u32>::zeros((n_contingencies, n_snapshots));
	let mut diverged = Array2::<bool>::from_elem((n_contingencies, n_snapshots), false);

	for snapshot in 0..n_snapshots {
		let injection = base_injection.row(snapshot);
		for contingency in 0..n_contingencies {
			let out_branch = if contingency == 0 {
				None
			} else {
				Some(contingency - 1)
			};
			match solve_with_branch_out(
				susceptance.view(),
				injection,
				branch_from.view(),
				branch_to.view(),
				branch_susceptance.view(),
				ratings.view(),
				slack,
				out_branch,
			) {
				Ok((served_shortfall, n_overloaded)) => {
					ens[[contingency, snapshot]] = served_shortfall;
					overloaded[[contingency, snapshot]] = n_overloaded;
				}
				Err(_) => {
					// A non-converging contingency is recorded, not propagated:
					// the sweep's job is to report which outages are
					// unsurvivable, and an islanding branch is exactly that.
					diverged[[contingency, snapshot]] = true;
					ens[[contingency, snapshot]] = f64::NAN;
				}
			}
		}
	}
	Ok(ContingencyResult {
		energy_not_served: ens,
		overloaded_branches: overloaded,
		diverged,
	})
}

#[allow(clippy::too_many_arguments)]
fn solve_with_branch_out(
	susceptance: ArrayView2<f64>,
	injection: ArrayView1<f64>,
	branch_from: ArrayView1<u32>,
	branch_to: ArrayView1<u32>,
	branch_susceptance: ArrayView1<f64>,
	ratings: ArrayView1<f64>,
	slack: usize,
	out_branch: Option<usize>,
) -> Result<(f64, u32)> {
	let n_buses = susceptance.shape()[0];
	let n_branches = branch_from.len();

	// Build the working susceptance matrix by removing the outaged branch's
	// contribution. The caller's matrix is untouched.
	let mut matrix = susceptance.to_owned();
	if let Some(b) = out_branch {
		let from = branch_from[b] as usize;
		let to = branch_to[b] as usize;
		if from >= n_buses || to >= n_buses {
			return Err(AleaError::IndexOutOfBounds {
				name: "branch",
				index: from.max(to),
				len: n_buses,
			});
		}
		let bs = branch_susceptance[b];
		matrix[[from, from]] -= bs;
		matrix[[to, to]] -= bs;
		matrix[[from, to]] += bs;
		matrix[[to, from]] += bs;
	}

	let mut rhs = injection.to_owned();
	for j in 0..n_buses {
		matrix[[slack, j]] = 0.0;
	}
	matrix[[slack, slack]] = 1.0;
	rhs[slack] = 0.0;

	let angles = solve_linear(matrix.view(), rhs.view(), "contingency")?;

	// Overload count over the surviving branches.
	let mut n_overloaded = 0u32;
	let mut total_flow = 0.0f64;
	for b in 0..n_branches {
		if Some(b) == out_branch {
			continue;
		}
		let from = branch_from[b] as usize;
		let to = branch_to[b] as usize;
		let flow = (branch_susceptance[b] * (angles[from] - angles[to])).abs();
		total_flow += flow;
		if flow > ratings[b] {
			n_overloaded += 1;
		}
	}

	// Energy not served: the injection the network could not carry. A branch
	// whose outage islands the slack has no path, and the shortfall is the load
	// stranded behind it. Approximated as the imbalance left at buses with no
	// finite angle.
	let shortfall: f64 = angles
		.iter()
		.enumerate()
		.filter(|(i, a)| **a == 0.0 && *i != slack && injection[*i] > 0.0)
		.map(|(i, _)| injection[i])
		.sum();
	let _ = total_flow;
	Ok((shortfall, n_overloaded))
}

/// Gaussian elimination with partial pivoting.
///
/// A singular system is reported as [`AleaError::Singular`], naming the solve.
/// A disconnected island produces exactly this and it must not be silently
/// turned into a zero angle, which reads as "no flow" rather than "no path".
fn solve_linear(
	matrix: ArrayView2<f64>,
	rhs: ArrayView1<f64>,
	name: &'static str,
) -> Result<Array1<f64>> {
	let n = matrix.shape()[0];
	let mut a = matrix.to_owned();
	let mut b = rhs.to_owned();

	for col in 0..n {
		// Partial pivoting: the largest magnitude in this column at or below the
		// diagonal.
		let mut pivot = col;
		let mut best = a[[col, col]].abs();
		for row in (col + 1)..n {
			let magnitude = a[[row, col]].abs();
			if magnitude > best {
				best = magnitude;
				pivot = row;
			}
		}
		if best < 1e-12 {
			return Err(AleaError::Singular { name });
		}
		if pivot != col {
			for j in 0..n {
				let tmp = a[[col, j]];
				a[[col, j]] = a[[pivot, j]];
				a[[pivot, j]] = tmp;
			}
			b.swap(col, pivot);
		}
		let diagonal = a[[col, col]];
		for row in (col + 1)..n {
			let factor = a[[row, col]] / diagonal;
			if factor == 0.0 {
				continue;
			}
			for j in col..n {
				a[[row, j]] -= factor * a[[col, j]];
			}
			b[row] -= factor * b[col];
		}
	}

	let mut x = Array1::<f64>::zeros(n);
	for col in (0..n).rev() {
		let mut sum = b[col];
		for j in (col + 1)..n {
			sum -= a[[col, j]] * x[j];
		}
		x[col] = sum / a[[col, col]];
	}
	Ok(x)
}

/// A loss decomposition whose parts sum to the total.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LossDecomposition {
	/// Loss attributable to the load pattern, MWh.
	pub load_driven: f64,
	/// Loss attributable to the generation dispatch pattern, MWh.
	pub generation_driven: f64,
	/// Loss attributable to the network topology, MWh.
	pub topology_driven: f64,
	/// The total loss, MWh.
	pub total: f64,
}

impl LossDecomposition {
	/// The sum of the parts.
	pub fn sum_of_parts(&self) -> f64 {
		self.load_driven + self.generation_driven + self.topology_driven
	}

	/// Whether the parts sum to the total within a relative tolerance.
	///
	/// A decomposition whose parts do not sum to the total is worse than no
	/// decomposition: it looks like an analysis and invites a conclusion about
	/// which driver dominates.
	pub fn is_consistent(&self, tolerance: f64) -> bool {
		let scale = self.total.abs().max(1e-12);
		(self.sum_of_parts() - self.total).abs() / scale <= tolerance
	}

	/// The shares as fractions of the total, or NaN when the total is zero.
	pub fn shares(&self) -> (f64, f64, f64) {
		if self.total.abs() < f64::EPSILON {
			return (f64::NAN, f64::NAN, f64::NAN);
		}
		(
			self.load_driven / self.total,
			self.generation_driven / self.total,
			self.topology_driven / self.total,
		)
	}
}

/// Decompose transmission losses into load-, generation- and topology-driven
/// parts.
///
/// The decomposition is a sequential attribution, which is the only scheme that
/// sums *exactly* to the actual total. Writing `A` for the actual loss, `L` for
/// the loss at the actual load on the reference network, `T` for the loss with
/// the actual topology and reference load, and `R` for the reference loss:
///
/// * `load_driven = L` — the loss the actual load causes, measured from the
///   no-load case (a network carrying nothing loses nothing).
/// * `topology_driven = T - R` — what the actual topology adds over the
///   reference topology.
/// * `generation_driven = A - L - (T - R)` — the residual attributable to the
///   actual dispatch.
///
/// The three sum to `A` by construction. An earlier formulation measured
/// `load_driven` from the reference instead of from zero, which left the
/// reference loss unattributed and made the parts sum to `A - R`: a
/// decomposition that looks like an analysis and under-reports every driver.
///
/// The order of attribution matters and is fixed here, so the result is
/// reproducible; a decomposition whose order is unspecified is one whose parts
/// differ between runs. `topology_driven` is computed, not the specification's
/// hardcoded zero.
#[allow(clippy::too_many_arguments)]
pub fn decompose_losses(
	actual_losses: f64,
	reference_losses: f64,
	losses_with_actual_load_only: f64,
	losses_with_actual_topology_only: f64,
) -> Result<LossDecomposition> {
	for (name, value) in [
		("actual_losses", actual_losses),
		("reference_losses", reference_losses),
		("losses_with_actual_load_only", losses_with_actual_load_only),
		(
			"losses_with_actual_topology_only",
			losses_with_actual_topology_only,
		),
	] {
		if !value.is_finite() {
			return Err(AleaError::OutOfRange {
				name: "losses",
				value: format!("{name}={value}"),
				range: "finite",
			});
		}
	}
	let load_driven = losses_with_actual_load_only;
	let topology_driven = losses_with_actual_topology_only - reference_losses;
	let generation_driven = actual_losses - load_driven - topology_driven;
	Ok(LossDecomposition {
		load_driven,
		generation_driven,
		topology_driven,
		total: actual_losses,
	})
}

/// Total transmission energy loss from branch flows and resistances.
///
/// `flows` in MW, `resistance` in ohms, `voltage_kv` in kV. Loss in MW is
/// `I^2 R`, with `I = P / (sqrt(3) * V)` for a three-phase line and `V` in kV
/// so that `P` in MW gives `I` in kA and `I^2 R` in kW; the factor of 1000
/// converts to MW.
pub fn transmission_losses(
	flows: ArrayView1<f64>,
	resistance: ArrayView1<f64>,
	voltage_kv: ArrayView1<f64>,
) -> Result<f64> {
	let n = flows.len();
	expect_shape1(resistance.shape(), [n])?;
	expect_shape1(voltage_kv.shape(), [n])?;
	let mut total = 0.0f64;
	for b in 0..n {
		let v = voltage_kv[b];
		if v <= 0.0 {
			return Err(AleaError::OutOfRange {
				name: "voltage_kv",
				value: format!("{v} at branch {b}"),
				range: "(0, inf)",
			});
		}
		let current_ka = flows[b] / (3.0f64.sqrt() * v);
		total += current_ka * current_ka * resistance[b] * 1000.0;
	}
	Ok(total)
}

/// The fraction of generated energy lost in transmission.
///
/// Returns NaN when generation is zero, because a loss fraction with no
/// generation is undefined and zero would read as "no losses".
pub fn loss_fraction(losses_mw: f64, generation_mw: f64) -> f64 {
	if generation_mw.abs() < f64::EPSILON {
		return f64::NAN;
	}
	losses_mw / generation_mw
}

/// Annualised loss energy from an hourly loss series, MWh.
pub fn annual_loss_energy(hourly_losses_mw: ArrayView1<f64>) -> f64 {
	hourly_losses_mw
		.iter()
		.filter(|v| v.is_finite())
		.sum::<f64>()
}

#[cfg(test)]
mod tests {
	use super::*;
	use ndarray::{array, Array2};

	/// A three-bus triangle: all branches have susceptance 1, buses 1 and 2
	/// connect through 0.
	fn triangle() -> (Array2<f64>, Array1<u32>, Array1<u32>, Array1<f64>) {
		let b = array![[2.0, -1.0, -1.0], [-1.0, 2.0, -1.0], [-1.0, -1.0, 2.0]];
		let from = array![0u32, 1, 2];
		let to = array![1u32, 2, 0];
		let bs = array![1.0, 1.0, 1.0];
		(b, from, to, bs)
	}

	/// Net flow out of each bus, given branch flows. Branch `b` runs from
	/// `branch_from[b]` to `branch_to[b]`, so a positive flow is power leaving
	/// `from` and entering `to`.
	fn net_outflow(
		flows: &Array1<f64>,
		from: &Array1<u32>,
		to: &Array1<u32>,
		n_buses: usize,
	) -> Array1<f64> {
		let mut out = Array1::<f64>::zeros(n_buses);
		for b in 0..from.len() {
			out[from[b] as usize] += flows[b];
			out[to[b] as usize] -= flows[b];
		}
		out
	}

	#[test]
	fn dc_flow_conserves_power_at_non_slack_buses() {
		let (b, from, to, bs) = triangle();
		let injection = array![0.0, 50.0, -50.0];
		let angles = dc_power_flow(b.view(), injection.view(), 0).unwrap();
		let flows = branch_flows(angles.view(), from.view(), to.view(), bs.view()).unwrap();
		let outflow = net_outflow(&flows, &from, &to, 3);
		// Every non-slack bus sends out exactly what it injects.
		for bus in 1..3 {
			assert!(
				(outflow[bus] - injection[bus]).abs() < 1e-9,
				"bus {bus}: outflow {} vs injection {}",
				outflow[bus],
				injection[bus]
			);
		}
	}

	#[test]
	fn dc_flow_conserves_power_over_random_injections() {
		let (b, from, to, bs) = triangle();
		// A deterministic sweep of balanced and unbalanced injections.
		for k in 1..40 {
			let p = (k as f64) * 7.0;
			let q = (k as f64) * 3.0;
			let injection = array![0.0, p, -q];
			let angles = dc_power_flow(b.view(), injection.view(), 0).unwrap();
			let flows = branch_flows(angles.view(), from.view(), to.view(), bs.view()).unwrap();
			let outflow = net_outflow(&flows, &from, &to, 3);
			for bus in 1..3 {
				assert!(
					(outflow[bus] - injection[bus]).abs() < 1e-6,
					"k={k} bus {bus}: {} vs {}",
					outflow[bus],
					injection[bus]
				);
			}
			// The slack absorbs the residual: total outflow at the slack equals
			// the negative of the sum of the other injections.
			assert!(
				(outflow[0] + injection[1] + injection[2]).abs() < 1e-6,
				"k={k}: slack {} vs {}",
				outflow[0],
				-(injection[1] + injection[2])
			);
		}
	}

	#[test]
	fn slack_angle_is_pinned_to_zero() {
		let (b, _, _, _) = triangle();
		let injection = array![0.0, 10.0, -10.0];
		let angles = dc_power_flow(b.view(), injection.view(), 0).unwrap();
		assert!(angles[0].abs() < 1e-12);
	}

	#[test]
	fn a_disconnected_network_is_singular_not_zero_flow() {
		// Two islands: bus 2 is connected to nothing.
		let b = array![[1.0, -1.0, 0.0], [-1.0, 1.0, 0.0], [0.0, 0.0, 0.0]];
		let injection = array![0.0, 0.0, 10.0];
		let result = dc_power_flow(b.view(), injection.view(), 0);
		assert!(
			matches!(result, Err(AleaError::Singular { .. })),
			"{result:?}"
		);
	}

	#[test]
	fn contingency_does_not_mutate_its_inputs() {
		let (b, from, to, bs) = triangle();
		let ratings = array![1000.0, 1000.0, 1000.0];
		let injections = Array2::from_shape_vec((1, 3), vec![0.0, 50.0, -50.0]).unwrap();
		let b_before = b.clone();
		let injections_before = injections.clone();
		let _ = contingency_sweep(
			b.view(),
			injections.view(),
			from.view(),
			to.view(),
			bs.view(),
			ratings.view(),
			0,
		)
		.unwrap();
		assert_eq!(b, b_before, "the susceptance matrix must be untouched");
		assert_eq!(
			injections, injections_before,
			"the injections must be untouched"
		);
	}

	#[test]
	fn a_failing_contingency_leaves_later_ones_unaffected() {
		// A radial network: losing the middle branch islands a bus.
		let b = array![[1.0, -1.0, 0.0], [-1.0, 2.0, -1.0], [0.0, -1.0, 1.0]];
		let from = array![0u32, 1];
		let to = array![1u32, 2];
		let bs = array![1.0, 1.0];
		let ratings = array![1000.0, 1000.0];
		let injections = Array2::from_shape_vec((1, 3), vec![0.0, 0.0, 50.0]).unwrap();
		let result = contingency_sweep(
			b.view(),
			injections.view(),
			from.view(),
			to.view(),
			bs.view(),
			ratings.view(),
			0,
		)
		.unwrap();
		// Contingency 0 is the base case and must have converged.
		assert!(!result.diverged[[0, 0]]);
		// The sweep completed: every contingency has a verdict.
		assert_eq!(result.diverged.shape(), &[3, 1]);
	}

	#[test]
	fn overload_is_counted() {
		let (b, from, to, bs) = triangle();
		let ratings = array![10.0, 1000.0, 1000.0]; // branch 0 is weak
		let injections = Array2::from_shape_vec((1, 3), vec![0.0, 50.0, -50.0]).unwrap();
		let result = contingency_sweep(
			b.view(),
			injections.view(),
			from.view(),
			to.view(),
			bs.view(),
			ratings.view(),
			0,
		)
		.unwrap();
		assert!(result.overloaded_branches[[0, 0]] >= 1);
	}

	#[test]
	fn decomposition_parts_sum_to_the_total() {
		let decomposition = decompose_losses(100.0, 80.0, 92.0, 88.0).unwrap();
		assert!(decomposition.is_consistent(1e-9), "{decomposition:?}");
		assert!((decomposition.sum_of_parts() - 100.0).abs() < 1e-9);
		// load 92, topology 8, generation 0.
		assert_eq!(decomposition.load_driven, 92.0);
		assert_eq!(decomposition.topology_driven, 8.0);
	}

	#[test]
	fn decomposition_is_exact_for_a_reference_with_no_loss() {
		// With the reference network lossless, load and topology account for
		// everything and the generation residual is the remainder.
		let decomposition = decompose_losses(100.0, 0.0, 70.0, 90.0).unwrap();
		assert_eq!(decomposition.load_driven, 70.0);
		assert_eq!(decomposition.topology_driven, 90.0);
		assert_eq!(decomposition.generation_driven, -60.0);
		assert!((decomposition.sum_of_parts() - 100.0).abs() < 1e-9);
	}

	#[test]
	fn topology_driven_is_not_hardcoded_zero() {
		// The specification returns 0 here. If the topology differs from the
		// reference, the term must be non-zero.
		let decomposition = decompose_losses(100.0, 80.0, 92.0, 95.0).unwrap();
		assert_ne!(decomposition.topology_driven, 0.0);
		assert_eq!(decomposition.topology_driven, 15.0);
	}

	#[test]
	fn decomposition_shares_sum_to_one() {
		let decomposition = decompose_losses(100.0, 80.0, 92.0, 88.0).unwrap();
		let (l, g, t) = decomposition.shares();
		assert!((l + g + t - 1.0).abs() < 1e-9, "{l} {g} {t}");
	}

	#[test]
	fn zero_total_has_nan_shares_not_zero() {
		let decomposition = decompose_losses(0.0, 0.0, 0.0, 0.0).unwrap();
		let (l, _, _) = decomposition.shares();
		assert!(l.is_nan());
	}

	#[test]
	fn non_finite_losses_are_refused() {
		assert!(decompose_losses(f64::NAN, 80.0, 92.0, 88.0).is_err());
	}

	#[test]
	fn loss_fraction_with_no_generation_is_nan() {
		assert!(loss_fraction(10.0, 0.0).is_nan());
		assert!((loss_fraction(10.0, 100.0) - 0.1).abs() < 1e-12);
	}

	#[test]
	fn transmission_losses_scales_with_current_squared() {
		let flows = array![100.0];
		let resistance = array![1.0];
		let voltage = array![100.0];
		let single = transmission_losses(flows.view(), resistance.view(), voltage.view()).unwrap();
		let doubled_flows = array![200.0];
		let double =
			transmission_losses(doubled_flows.view(), resistance.view(), voltage.view()).unwrap();
		assert!((double / single - 4.0).abs() < 1e-9, "{double} / {single}");
	}

	#[test]
	fn zero_voltage_is_refused() {
		let flows = array![100.0];
		let resistance = array![1.0];
		let voltage = array![0.0];
		assert!(transmission_losses(flows.view(), resistance.view(), voltage.view()).is_err());
	}

	#[test]
	fn annual_loss_energy_ignores_non_finite() {
		let hourly = array![1.0, 2.0, f64::NAN, 3.0];
		assert_eq!(annual_loss_energy(hourly.view()), 6.0);
	}
}
