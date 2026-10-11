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
