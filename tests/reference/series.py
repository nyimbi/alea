# SPDX-License-Identifier: MIT
"""Reference implementation of the series kernels (TSAM aggregation).

Written from `alea._core.kernels` and `docs/plans/03-rust-core.md` §5.

Pinned semantics encoded here, and why:

* **`sum(weights) == n_timesteps` exactly.** The plan's §5.2 makes this the
  invariant that matters: a weighting summing to 8758 instead of 8760 shifts
  every annual total by 0.02%, invisibly and systematically. The reference
  carries integer weights and asserts the sum before returning.
* **Every timestep is assigned exactly once.** `assignments` has one entry per
  timestep, each in `[0, n_periods)`.
* **When `n_periods * period_length == n_timesteps`, the assignment is
  contiguous blocks of `period_length`.** This is the case the kernel defines
  exactly and the case the differential test uses. `representatives[p]` is the
  first timestep of block `p` and every weight is `period_length`, which is
  what makes the exact-sum invariant hold by construction.
* **The general case** (unequal division) is a seeded heuristic in the kernel:
  the reference below reimplements the same *shape* of algorithm (seeded
  k-means++ over period medoids, nearest-medoid assignment, weights as the
  timestep counts of the assigned periods) but its exact cluster membership is
  not guaranteed to match a particular kernel build. Differential tests
  therefore exercise the exact-division case for values and assert only the
  invariants (exact sum, coverage, determinism) for the general case.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _period_medoids(series: NDArray[np.float64], period_length: int) -> tuple[NDArray[np.float64], list[list[int]]]:
	"""Split the series into whole periods; return each period's medoid row.

	A period's medoid is the timestep whose distance to the period's mean
	profile is smallest — the representative period, not the mean of it.
	"""
	n_timesteps = series.shape[0]
	n_periods = n_timesteps // period_length
	medoids = []
	members: list[list[int]] = []
	for p in range(n_periods):
		idx = list(range(p * period_length, (p + 1) * period_length))
		members.append(idx)
		block = series[idx]
		mean_profile = block.mean(axis=0)
		best = min(idx, key=lambda t: float(np.sum((series[t] - mean_profile) ** 2)))
		medoids.append(series[best])
	return np.asarray(medoids, dtype=np.float64), members


def _kmeans_plus_plus(
	medoids: NDArray[np.float64], n_periods: int, seed: int
) -> list[int]:
	"""Seeded k-means++ seeding over period medoids.

	The seed is threaded through a `default_rng`, never the global RNG: AD-8
	requires identical seeds to give identical aggregation across processes.
	"""
	rng = np.random.default_rng(seed)
	n = medoids.shape[0]
	first = int(rng.integers(0, n))
	chosen = [first]
	closest = np.sum((medoids - medoids[first]) ** 2, axis=1)
	while len(chosen) < min(n_periods, n):
		total = float(closest.sum())
		if total <= 0.0:
			# All remaining periods coincide with a centre; take the next one.
			for i in range(n):
				if i not in chosen:
					chosen.append(i)
					break
			closest = np.minimum(closest, np.sum((medoids - medoids[chosen[-1]]) ** 2, axis=1))
			continue
		target = rng.random() * total
		cumulative = 0.0
		pick = chosen[-1]
		for i in range(n):
			cumulative += float(closest[i])
			if cumulative >= target:
				pick = i
				break
		if pick in chosen:
			for i in range(n):
				if i not in chosen:
					pick = i
					break
		chosen.append(pick)
		closest = np.minimum(closest, np.sum((medoids - medoids[pick]) ** 2, axis=1))
	return chosen


def aggregate(
	series: NDArray[np.float32],
	n_periods: int,
	period_length: int,
	seed: int = 0,
) -> tuple[NDArray[np.uint32], NDArray[np.uint32], NDArray[np.float64]]:
	"""Aggregate a series into representative periods.

	Returns `(assignments, representatives, weights)` with weights summing to
	`n_timesteps` exactly.
	"""
	# Rebound to a float64 view: the arithmetic below is float64 throughout, and
	# a float32 accumulator would round the weights this function exists to
	# prove are exact. The declared parameter type is the *kernel's* contract
	# (it takes float32); the reference widens on entry.
	values = np.asarray(series, dtype=np.float64)
	n_timesteps = values.shape[0]
	if n_timesteps == 0:
		return (
			np.zeros(0, dtype=np.uint32),
			np.zeros(0, dtype=np.uint32),
			np.zeros(0, dtype=np.float64),
		)
	if n_periods * period_length == n_timesteps:
		# Exact division: contiguous blocks, the case the kernel pins.
		assignments = np.repeat(np.arange(n_periods, dtype=np.uint32), period_length)
		representatives = (np.arange(n_periods, dtype=np.uint32) * period_length).astype(np.uint32)
		weights = np.full(n_periods, float(period_length), dtype=np.float64)
		assert int(weights.sum()) == n_timesteps
		return assignments, representatives, weights

	# Unequal division: seeded medoid clustering over whole periods.
	medoids, members = _period_medoids(values, period_length)
	n_whole = medoids.shape[0]
	centres = _kmeans_plus_plus(medoids, n_periods, seed)
	period_to_rep = []
	for p in range(n_whole):
		best = min(centres, key=lambda c: float(np.sum((medoids[p] - medoids[c]) ** 2)))
		period_to_rep.append(best)

	# Every chosen centre is a representative period; its first timestep is the
	# representative index. The label is the position of the centre in the
	# medoid list, so a centre that ends up with no period still yields a
	# representative (its weight is then zero and the tail may fill it).
	reps_first = [members[c][0] for c in centres]
	assignments = np.zeros(n_timesteps, dtype=np.uint32)
	weights = np.zeros(len(centres), dtype=np.float64)
	for p in range(n_whole):
		label = centres.index(period_to_rep[p])
		for t in members[p]:
			assignments[t] = label
		weights[label] += float(len(members[p]))

	# The tail timesteps that do not form a whole period attach to the nearest
	# representative, preserving the exact sum.
	tail = list(range(n_whole * period_length, n_timesteps))
	for t in tail:
		best = min(
			range(len(reps_first)),
			key=lambda k: float(np.sum((values[t] - values[reps_first[k]]) ** 2)),
		)
		assignments[t] = best
		weights[best] += 1.0

	representatives = np.asarray(reps_first, dtype=np.uint32)
	assert len(representatives) == n_periods
	assert int(weights.sum()) == n_timesteps
	assert len(assignments) == n_timesteps
	return assignments, representatives, weights


def load_duration_curve(series: NDArray[np.float32]) -> NDArray[np.float32]:
	"""Sorted-descending values per column."""
	values = np.asarray(series, dtype=np.float64)
	n_cols = values.shape[1]
	out = np.empty_like(values, dtype=np.float64)
	for c in range(n_cols):
		column = sorted((float(v) for v in values[:, c]), reverse=True)
		out[:, c] = column
	return out.astype(np.float32)


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

	The four errors are percentages relative to the full-resolution value. The
	capacity-mix error is the L1 distance between the two capacity mixes
	(each normalised to sum one) as a percentage; the other three are relative
	differences. A zero denominator contributes a zero error rather than a NaN,
	matching the kernel.
	"""

	def rel(agg: float, full: float) -> float:
		if full == 0.0:
			return 0.0
		return abs(agg - full) / abs(full) * 100.0

	full_capacity = np.asarray(full_capacity, dtype=np.float64)
	aggregated_capacity = np.asarray(aggregated_capacity, dtype=np.float64)
	full_total = float(full_capacity.sum())
	agg_total = float(aggregated_capacity.sum())
	if full_total == 0.0 or agg_total == 0.0:
		capacity_error = 0.0
	else:
		l1 = float(np.abs(full_capacity / full_total - aggregated_capacity / agg_total).sum())
		capacity_error = l1 * 100.0
	return {
		"total_cost_error_pct": rel(aggregated_cost, full_cost),
		"capacity_mix_l1_error_pct": capacity_error,
		"emissions_error_pct": rel(aggregated_emissions, full_emissions),
		"peak_price_error_pct": rel(aggregated_peak_price, full_peak_price),
	}
