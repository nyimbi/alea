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
					//
					// The shortfall is the stranded *load*, not NaN. This is
					// the only path an island can take -- a detached bus has no
					// angle reference, so the solve is singular before any
					// angle exists. Leaving it NaN would hide the one number
					// the outage is worth, and every consumer that skips NaN
					// (as `SweepResult.base_ens_mwh` deliberately does) would
					// read the worst outages as no outage at all.
					diverged[[contingency, snapshot]] = true;
					ens[[contingency, snapshot]] = islanded_energy_not_served(
						branch_from.view(),
						branch_to.view(),
						injection,
						slack,
						out_branch,
					);
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

/// Union-find root, with path halving.
fn find_root(parent: &mut [usize], mut x: usize) -> usize {
	while parent[x] != x {
		parent[x] = parent[parent[x]];
		x = parent[x];
	}
	x
}

/// Energy not served by a branch outage that detaches part of the network.
///
/// A bus cut off from the slack has no angle reference, so the DC system is
/// singular and there are no angles to solve for. What remains is a local
/// balance: an island serves its own load only as far as its own generation
/// reaches, and `max(0, load - generation)` behind it is unserved. This is the
/// specification's `load - served` (`spec4-base.md` §13.2), evaluated on the
/// island rather than on the whole system.
///
/// The stranded set is found by **connectivity over the surviving branches**,
/// not by inspecting the angles. An earlier version read an exactly-zero angle
/// as "no finite angle" and summed the injections at those buses. Two things
/// were wrong with it. A bus whose solved angle is exactly zero is a healthy
/// bus, so a fully connected network reported unserved energy in its own base
/// case -- for the three-bus radial above, 50 MW of it. And a bus that really
/// islands makes the system singular before any angle is produced, so the test
/// could never fire on the case it was written for.
fn islanded_energy_not_served(
	branch_from: ArrayView1<u32>,
	branch_to: ArrayView1<u32>,
	injection: ArrayView1<f64>,
	slack: usize,
	out_branch: Option<usize>,
) -> f64 {
	let n_buses = injection.len();
	let mut parent: Vec<usize> = (0..n_buses).collect();
	for b in 0..branch_from.len() {
		if Some(b) == out_branch {
			continue;
		}
		let from = branch_from[b] as usize;
		let to = branch_to[b] as usize;
		if from >= n_buses || to >= n_buses {
			continue;
		}
		let root_from = find_root(&mut parent, from);
		let root_to = find_root(&mut parent, to);
		if root_from != root_to {
			parent[root_from] = root_to;
		}
	}

	let slack_root = find_root(&mut parent, slack);
	let mut load = vec![0.0f64; n_buses];
	let mut generation = vec![0.0f64; n_buses];
	for i in 0..n_buses {
		let root = find_root(&mut parent, i);
		if root == slack_root {
			continue;
		}
		if injection[i] > 0.0 {
			generation[root] += injection[i];
		} else {
			load[root] += -injection[i];
		}
	}

	// Each component root is visited once: the root is the only index that is
	// its own representative.
	let mut shortfall = 0.0f64;
	for i in 0..n_buses {
		let root = find_root(&mut parent, i);
		if root != i || root == slack_root {
			continue;
		}
		shortfall += (load[root] - generation[root]).max(0.0);
	}
	shortfall
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

	// Energy not served. A branch whose removal splits the network makes the DC
	// system singular, so that case never reaches here -- it is caught as
	// `Err` in the sweep, where the island's stranded load is measured. A
	// converging solve is a connected network and serves everything.
	let _ = total_flow;
	Ok((0.0, n_overloaded))
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
/// `flows` in MW, `resistance` in ohms, `voltage_kv` in kV. For a three-phase
/// line carrying apparent power `S` at line-to-line voltage `V`, the line
/// current is `I = S / (sqrt(3) V)` and the total copper loss is the per-phase
/// `I^2 R` summed over three phases, `3 I^2 R`.
///
/// ```text
/// P_loss = 3 * (S / (sqrt(3) V))^2 * R = S^2 * R / V^2
/// ```
///
/// **No unit conversion is needed.** With `S` in MW and `V` in kV the current
/// is in kA, and `1 kA^2 * ohm = 1 MW`, so `3 I^2 R` is already MW.
///
/// Three constants have been wrong here and only one is right:
///
/// * `I^2 R` with the line current -- a factor of 3 too small, because it
///   counts one phase instead of three.
/// * `I^2 R * 1000` -- the shipped form, 1000/3 = 333x too large. On a 3-bus
///   fixture it produced a loss fraction of 1.377: 138% of generated energy
///   lost in transmission, which is not a rounding question but an
///   impossibility.
/// * `3 I^2 R * 1000` -- 1000x too large, and the tempting repair: the `1000`
///   converts kW to MW only if the current is in amps, and here it is in kA.
///
/// A differential test cannot catch any of these: the Python reference carried
/// the same constant, so the two agreed with each other and disagreed with the
/// physics. The check that found it was pypsa's AC power flow on a line whose
/// loss is hand-computable (`07-layer4-predictive.md` §6.3), which is the one
/// place the plan allows a reference to depend on the physics.
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
		total += 3.0 * current_ka * current_ka * resistance[b];
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
	fn a_connected_base_case_serves_all_its_energy() {
		// The base case has every branch in, so nothing can be stranded. This
		// asserts the *value*: an earlier shortfall test read an exactly-zero
		// bus angle as "islanded", and bus 1 of this radial solves to -0.0
		// while carrying 50 MW, so the base case reported 50 MW unserved on a
		// network with no outage at all.
		let b = array![[1.0, -1.0, 0.0], [-1.0, 2.0, -1.0], [0.0, -1.0, 1.0]];
		let from = array![0u32, 1];
		let to = array![1u32, 2];
		let bs = array![1.0, 1.0];
		let ratings = array![1000.0, 1000.0];
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
		assert_eq!(result.energy_not_served[[0, 0]], 0.0);
	}

	#[test]
	fn an_islanded_island_reports_its_stranded_load() {
		// A four-bus chain 0-1-2-3 with generation at the slack (bus 0) and at
		// bus 2, and load at bus 3. Losing branch 2 detaches {3}, which has no
		// generation of its own: 30 MW of load is stranded and 30 is the
		// shortfall. Losing branch 1 detaches {2, 3}, which carries 20 MW of
		// generation against 30 MW of load, so 10 is stranded. Both outages
		// island a bus, so both make the DC system singular and are recorded in
		// `diverged` -- which is exactly why the shortfall cannot be read off
		// the angles.
		let b = array![
			[1.0, -1.0, 0.0, 0.0],
			[-1.0, 2.0, -1.0, 0.0],
			[0.0, -1.0, 2.0, -1.0],
			[0.0, 0.0, -1.0, 1.0],
		];
		let from = array![0u32, 1, 2];
		let to = array![1u32, 2, 3];
		let bs = array![1.0, 1.0, 1.0];
		let ratings = array![1000.0, 1000.0, 1000.0];
		let injections = Array2::from_shape_vec((1, 4), vec![0.0, 0.0, 20.0, -30.0]).unwrap();
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
		// Base case: everything is connected and served.
		assert_eq!(result.energy_not_served[[0, 0]], 0.0);
		// Branch 2 out: bus 3 alone, 30 MW of load and no generation.
		assert!(result.diverged[[3, 0]]);
		assert_eq!(result.energy_not_served[[3, 0]], 30.0);
		// Branch 1 out: buses 2 and 3, 30 MW of load against 20 MW of local
		// generation.
		assert!(result.diverged[[2, 0]]);
		assert_eq!(result.energy_not_served[[2, 0]], 10.0);
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
	fn transmission_losses_matches_the_three_phase_formula() {
		// A scaling-only test cannot see a wrong constant: it asserts
		// `f(2x) == 4 f(x)`, which holds for any multiple of the true loss.
		// This pins the *value*, from `P_loss = 3 I^2 R` with
		// `I = S / (sqrt(3) V)`, which reduces to `S^2 R / V^2`.
		//
		// 100 MW over 1 ohm at 100 kV: 100^2 * 1 / 100^2 = 1 MW. The shipped
		// form returned 1000/3 MW here -- 333x -- and reported a 3-bus fixture
		// losing 138% of its generation.
		let flows = array![100.0];
		let resistance = array![1.0];
		let voltage = array![100.0];
		let loss = transmission_losses(flows.view(), resistance.view(), voltage.view()).unwrap();
		assert!((loss - 1.0).abs() < 1e-9, "{loss} != 1.0 MW");
	}

	#[test]
	fn transmission_losses_never_exceeds_the_flow_on_a_realistic_line() {
		// The invariant that makes the bug impossible to reintroduce silently:
		// a line cannot lose more power than it carries. At 220 kV with a
		// realistic resistance the loss is a fraction of a percent, so any
		// loss above the flow itself is a unit error, not a network property.
		let flows = array![100.0];
		let resistance = array![10.0];
		let voltage = array![220.0];
		let loss = transmission_losses(flows.view(), resistance.view(), voltage.view()).unwrap();
		assert!(loss < 100.0, "loss {loss} MW exceeds the 100 MW flow");
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
