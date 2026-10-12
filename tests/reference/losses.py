# SPDX-License-Identifier: MIT
"""Reference implementation of the loss kernels (DC flow, decomposition).

Written from `alea._core.kernels` and `docs/plans/03-rust-core.md` §6. Not
production code.

Pinned semantics encoded here, and why:

* **The slack angle is pinned to zero**, and the slack row and column are
  removed before solving `B theta = P`. A singular reduced system (a
  disconnected island) is an error, not a zero angle: a zero angle reads as
  "no flow" instead of "no path" (plan §6).
* **Branch flow is `b * (theta_from - theta_to)`**, positive from `from` to
  `to`.
* **The loss decomposition sums to the total by construction.** The plan's
  §6.3 invariant is `load_driven + generation_driven + topology_driven ==
  total`. The reference assigns `load_driven` the load-only losses,
  `topology_driven` the topology-only losses net of the reference, and
  `generation_driven` the remainder — so the sum is exact by definition rather
  than by luck.
* **Transmission loss scales with current squared, over a three-phase line.**
  With flows in MW and line-to-line voltages in kV, `I = flow * 1000 / V` amps
  is the apparent current; the three-phase real loss is `R * I^2 / 3` watts,
  so `P_loss = R * I^2 / 3000` MW, summed over branches. Dividing by three is
  what the naive single-phase `R * I^2 / 1000` omits, and it is the difference
  between a loss figure and three times one.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def dc_power_flow(
	susceptance: NDArray[np.float64],
	injection: NDArray[np.float64],
	slack: int,
) -> NDArray[np.float64]:
	"""Bus angles from net injection, with the slack angle pinned to zero.

	Raises on a singular reduced system, matching the kernel's refusal to
	return a zero angle for a network with no path.
	"""
	susceptance = np.asarray(susceptance, dtype=np.float64)
	injection = np.asarray(injection, dtype=np.float64)
	n = injection.shape[0]
	others = [i for i in range(n) if i != slack]
	reduced_b = susceptance[np.ix_(others, others)]
	reduced_p = injection[others]
	# numpy.linalg raises LinAlgError on a singular matrix; a disconnected
	# island makes the reduced system singular, exactly the case to surface.
	angles_other = np.linalg.solve(reduced_b, reduced_p)
	angles = np.zeros(n, dtype=np.float64)
	for k, i in enumerate(others):
		angles[i] = angles_other[k]
	return angles


def branch_flows(
	angles: NDArray[np.float64],
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	branch_susceptance: NDArray[np.float64],
) -> NDArray[np.float64]:
	"""Branch flows in MW from bus angles, `b * (theta_from - theta_to)`."""
	angles = np.asarray(angles, dtype=np.float64)
	branch_from = np.asarray(branch_from)
	branch_to = np.asarray(branch_to)
	branch_susceptance = np.asarray(branch_susceptance, dtype=np.float64)
	n_branches = branch_from.shape[0]
	out = np.empty(n_branches, dtype=np.float64)
	for e in range(n_branches):
		i = int(branch_from[e])
		j = int(branch_to[e])
		out[e] = branch_susceptance[e] * (angles[i] - angles[j])
	return out


def decompose_losses(
	actual_losses: float,
	reference_losses: float,
	losses_with_actual_load_only: float,
	losses_with_actual_topology_only: float,
) -> dict[str, float]:
	"""Decompose losses into load-, generation- and topology-driven parts.

	The parts sum to `actual_losses` by construction: the load and topology
	parts are the single-change losses, and the generation part is whatever
	remains.
	"""
	load_driven = float(losses_with_actual_load_only)
	topology_driven = float(losses_with_actual_topology_only) - float(reference_losses)
	generation_driven = float(actual_losses) - load_driven - topology_driven
	total = float(actual_losses)
	parts = load_driven + generation_driven + topology_driven
	return {
		"load_driven": load_driven,
		"generation_driven": generation_driven,
		"topology_driven": topology_driven,
		"total": total,
		"sum_of_parts": parts,
	}


def transmission_losses(
	flows: NDArray[np.float64],
	resistance: NDArray[np.float64],
	voltage_kv: NDArray[np.float64],
) -> float:
	"""Total transmission loss in MW, `sum(R * (flow*1000/V)^2 / 3000)`."""
	flows = np.asarray(flows, dtype=np.float64)
	resistance = np.asarray(resistance, dtype=np.float64)
	voltage_kv = np.asarray(voltage_kv, dtype=np.float64)
	total = 0.0
	for e in range(flows.shape[0]):
		current = flows[e] * 1000.0 / voltage_kv[e]
		total += resistance[e] * current * current / 3000.0
	return float(total)


def _solve_linear(matrix: NDArray[np.float64], rhs: NDArray[np.float64]) -> NDArray[np.float64]:
	"""Gaussian elimination with partial pivoting; a singular system raises.

	The kernel reports a singular system as an error rather than a zero angle,
	because a zero angle reads as "no flow" when the truth is "no path". The
	reference surfaces the same condition, via `numpy.linalg.solve` raising
	`LinAlgError`, so a differential test sees both refuse the same input.
	"""
	solution = np.linalg.solve(np.asarray(matrix, dtype=np.float64), np.asarray(rhs, dtype=np.float64))
	return np.asarray(solution, dtype=np.float64)


def _islanded_energy_not_served(
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	injection: NDArray[np.float64],
	slack: int,
	out_branch: int | None,
) -> float:
	"""Load behind a branch outage that detaches part of the network.

	The stranded set is found by **connectivity over the surviving branches**,
	never by inspecting the angles. A bus whose solved angle is exactly zero is
	a healthy bus, so an angle-based test reports unserved energy in a fully
	connected network's own base case; and a genuinely islanded bus makes the
	system singular before any angle exists, so the test could never fire on the
	case it was written for. Both failures are in the kernel's own history and
	the comment there records them.

	An island serves its own load only as far as its own generation reaches, so
	the shortfall is `max(0, load - generation)` summed over the components that
	do not contain the slack.
	"""
	n_buses = injection.shape[0]
	parent = list(range(n_buses))

	def find(x: int) -> int:
		while parent[x] != x:
			parent[x] = parent[parent[x]]
			x = parent[x]
		return x

	for e in range(branch_from.shape[0]):
		if out_branch is not None and e == out_branch:
			continue
		i, j = int(branch_from[e]), int(branch_to[e])
		if i >= n_buses or j >= n_buses:
			continue
		ri, rj = find(i), find(j)
		if ri != rj:
			parent[ri] = rj

	slack_root = find(slack)
	load = np.zeros(n_buses, dtype=np.float64)
	generation = np.zeros(n_buses, dtype=np.float64)
	for i in range(n_buses):
		root = find(i)
		if root == slack_root:
			continue
		# Positive injection is generation, everything else is load. The kernel
		# writes this as an if/else over `> 0.0`, so an exactly-zero injection
		# lands on the load side and contributes nothing either way.
		if injection[i] > 0.0:
			generation[root] += injection[i]
		else:
			load[root] += -injection[i]

	shortfall = 0.0
	for i in range(n_buses):
		root = find(i)
		# Each component root is visited once: the root is the only index that
		# is its own representative.
		if root != i or root == slack_root:
			continue
		shortfall += max(load[root] - generation[root], 0.0)
	return float(shortfall)


def contingency_sweep(
	susceptance: NDArray[np.float64],
	base_injection: NDArray[np.float64],
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	branch_susceptance: NDArray[np.float64],
	ratings: NDArray[np.float64],
	slack: int,
) -> dict[str, NDArray]:
	"""N-1 contingency sweep, one branch out at a time.

	Returns `energy_not_served` `[n_branches + 1, n_snapshots]`, row 0 being the
	base case, plus `overloaded_branches` (uint32) and `diverged` (bool) of the
	same shape.

	Three semantics are pinned here because each is a defect the kernel's own
	comments record:

	* **The caller's arrays are never mutated.** The outaged branch's
	  contribution is removed from a *copy* of the susceptance matrix. The
	  specification's `compute_tlens` deactivates a line in place and restores it
	  inside the same loop, so an exception mid-loop leaves a line permanently
	  out and every later contingency is computed on a degraded network.
	* **A non-converging contingency is recorded, not propagated.** It sets
	  `diverged`, carries the island's stranded load in `energy_not_served`, and
	  leaves `overloaded_branches` at 0. The sweep's job is to report which
	  outages are unsurvivable, and an islanding branch is exactly that. NaN
	  would be worse than zero here: every consumer that skips NaN reads the
	  worst outages as no outage at all.
	* **A converging solve serves everything, so its `energy_not_served` is 0.**
	  Only the singular path produces a non-zero figure.
	"""
	susceptance = np.asarray(susceptance, dtype=np.float64)
	base_injection = np.asarray(base_injection, dtype=np.float64)
	branch_from = np.asarray(branch_from)
	branch_to = np.asarray(branch_to)
	branch_susceptance = np.asarray(branch_susceptance, dtype=np.float64)
	ratings = np.asarray(ratings, dtype=np.float64)

	n_snapshots = base_injection.shape[0]
	n_branches = branch_from.shape[0]
	n_contingencies = n_branches + 1

	ens = np.zeros((n_contingencies, n_snapshots), dtype=np.float64)
	overloaded = np.zeros((n_contingencies, n_snapshots), dtype=np.uint32)
	diverged = np.zeros((n_contingencies, n_snapshots), dtype=bool)

	for snapshot in range(n_snapshots):
		injection = base_injection[snapshot]
		for contingency in range(n_contingencies):
			out_branch = None if contingency == 0 else contingency - 1

			matrix = susceptance.copy()
			if out_branch is not None:
				i, j = int(branch_from[out_branch]), int(branch_to[out_branch])
				b = branch_susceptance[out_branch]
				matrix[i, i] -= b
				matrix[j, j] -= b
				matrix[i, j] += b
				matrix[j, i] += b

			rhs = injection.astype(np.float64).copy()
			# The slack row is replaced by the identity and its RHS zeroed, which
			# pins the reference angle at zero.
			matrix[slack, :] = 0.0
			matrix[slack, slack] = 1.0
			rhs[slack] = 0.0

			try:
				angles = _solve_linear(matrix, rhs)
			except np.linalg.LinAlgError:
				diverged[contingency, snapshot] = True
				ens[contingency, snapshot] = _islanded_energy_not_served(
					branch_from, branch_to, injection, slack, out_branch
				)
				continue

			n_over = 0
			for e in range(n_branches):
				if out_branch is not None and e == out_branch:
					continue
				flow = abs(branch_susceptance[e] * (angles[int(branch_from[e])] - angles[int(branch_to[e])]))
				if flow > ratings[e]:
					n_over += 1
			overloaded[contingency, snapshot] = n_over

	return {
		"energy_not_served": ens,
		"overloaded_branches": overloaded,
		"diverged": diverged,
	}
