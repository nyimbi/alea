# SPDX-License-Identifier: MIT
"""The aggregation kernel against a foreign implementation of the same problem.

`tests/reference/series.py` is the plan's differential reference for
`alea-series`, and it is honest about what it can and cannot prove: it
reimplements the *same* algorithm family (seeded medoid clustering over whole
periods) that the kernel uses, written by the same hand from the same
paragraphs. Two implementations that share an author and an algorithm agree
when they are both wrong in the same way — which is precisely how the loss
kernel shipped 333× wrong behind a differential suite that passed
([[alea-loss-kernel-unit-error]]).

`tsam` is the third-party implementation the architecture names and the Rust
crate *replaces* (`docs/plans/00-architecture.md:337`). It answers the same
question — which periods represent a year, and what does each stand for — from
an independent lineage, so agreement with it is evidence the reference suite
cannot produce on its own. That is the whole reason it is a test dependency
rather than dead weight in `pyproject.toml`.

WHY the comparison is on *properties* and not on cluster membership: tsam and
the kernel optimise different objectives. tsam assigns by Euclidean distance to
a cluster **mean** and reconstructs with that mean; the kernel assigns to a
**medoid** — a real historical period — because a decision-support artefact
that reports "period 7 of your year" must be able to point at period 7. Both
are legitimate; they do not select the same blocks, and a test demanding they
match would be testing that one of them is a copy of the other. What must agree
is the thing the platform actually promises: the exact-sum invariant, the
coverage, determinism, and the fact that a *better* reconstruction is not
available from the same class of construction.

WHY this is not a gate on tsam: nothing in `src/` imports tsam. The kernel is
the product; tsam is the witness.
"""

from __future__ import annotations

import importlib.metadata

import numpy as np
import pandas as pd
import pytest
import tsam

from alea._core import aggregate as kernel_aggregate
from tests.ci.test_planning_layer1 import _seasonal_year

# No skipif on tsam's presence. It is a direct dependency in `pyproject.toml`
# (`tsam>=4.0`), so a missing install fails at the import above and never
# reaches a marker — a skip here would be dead code that reads like graceful
# degradation and would silently retire the only independent witness this
# kernel has.
_PERIOD_LENGTH = 24


def _fixture_frame() -> pd.DataFrame:
	"""The seasonal year as tsam wants it: a datetime-indexed frame."""
	load, solar, snapshots = _seasonal_year()
	return pd.DataFrame({"load": load, "solar": solar}, index=snapshots)


def _tsam_aggregate(frame: pd.DataFrame, n_periods: int) -> tsam.AggregationResult:
	"""One tsam aggregation, pinned to the same period length the kernel takes."""
	return tsam.aggregate(
		frame, n_periods, period_duration=_PERIOD_LENGTH, numerical_tolerance=1e-9
	)


def _kernel_result(frame: pd.DataFrame, n_periods: int):
	"""The kernel's arrays for the same frame."""
	return kernel_aggregate(
		frame.to_numpy().astype(np.float32), n_periods, _PERIOD_LENGTH, 0
	)


def _tsam_network(frame: pd.DataFrame, n_periods: int):
	"""Build the network tsam's own output implies, on the seasonal fixture.

	The construction is the one the platform uses for the kernel: keep every
	timestep of each representative period, and weight each kept timestep by the
	periods its cluster stands for. The only difference from `aggregate_network`
	is where the periods and weights come from — tsam's clustering rather than
	the kernel's — so the two networks are comparable and the comparison
	isolates the selection, not the plumbing.

	`cluster_counts` is in periods, so each of the `_PERIOD_LENGTH` timesteps kept
	for cluster `k` carries a weight of `counts[k]` — the periods it stands for.
	The twenty-four hours of a kept period then contribute `24 × counts[k]`, and
	the total is `24 × 365 = 8760`. Reading `cluster_counts` as hours (it is
	`assignments` that is hourly) and dividing by 24 deflates every weight by
	576, which is how a units slip in the harness would read as a defect in the
	oracle.
	"""
	from tests.ci.test_planning_layer1 import _seasonal_network

	result = _tsam_aggregate(frame, n_periods)
	counts = result.cluster_counts
	representatives = result.cluster_representatives

	profiles: list[np.ndarray] = []
	weights: list[np.ndarray] = []
	for k in range(n_periods):
		block = representatives.loc[k].to_numpy()
		profiles.append(block)
		weights.append(np.full(_PERIOD_LENGTH, float(counts[k])))
	profile = np.concatenate(profiles)
	weight = np.concatenate(weights)
	assert weight.sum() == pytest.approx(8760.0), f"the oracle's weights sum to {weight.sum()}, not 8760"

	index = pd.date_range("2030-01-01", periods=len(profile), freq="h")
	network = _seasonal_network(
		frame["load"].to_numpy(), frame["solar"].to_numpy(), pd.DatetimeIndex(frame.index)
	)
	network.set_snapshots(index)  # type: ignore[arg-type]
	network.loads_t.p_set["load"] = pd.Series(profile[:, 0], index=index)
	network.generators_t.p_max_pu["solar"] = pd.Series(profile[:, 1], index=index)
	network.snapshot_weightings = pd.DataFrame(
		{column: weight for column in network.snapshot_weightings.columns}, index=index
	)
	return network


def test_the_oracle_is_the_one_the_architecture_names():
	"""A version guard, because the API moved between majors and a silent skip lies.

	`tsam.TimeSeriesAggregation` — the API every tutorial and every older
	internal note uses — does not exist in 4.x. A test written against it would
	error at import, and a test written against a guessed shape would silently
	compare nothing. So assert the surface this module actually calls is the
	one installed, and assert the version is at least the floor `pyproject.toml`
	declares.
	"""
	assert hasattr(tsam, "aggregate"), "tsam 4.x exposes `aggregate`, not `TimeSeriesAggregation`"
	major = int(importlib.metadata.version("tsam").split(".")[0])
	assert major >= 4, f"pyproject declares tsam>=4.0; found {importlib.metadata.version('tsam')}"


def test_the_oracle_reads_the_same_year_the_gates_read():
	"""Fixture validity, for the same reason the kernel canary has one.

	If tsam were fed a different year than the kernel — a different length, a
	different index — every agreement below would be agreement about nothing.
	"""
	frame = _fixture_frame()
	load, solar, snapshots = _seasonal_year()
	assert len(frame) == 8760 == len(load)
	assert frame.index.equals(snapshots)
	assert np.allclose(frame["load"].to_numpy(), load)
	assert np.allclose(frame["solar"].to_numpy(), solar)


def test_both_implementations_agree_the_weights_are_the_hours_of_a_year():
	"""The plan's §5.2 invariant, checked against a foreign implementation.

	`sum(weights) == n_timesteps` exactly is the invariant `03-rust-core.md`
	calls the one that matters, and the kernel asserts it internally — which is
	a kernel checked against itself. tsam's `cluster_counts` is the same
	quantity arrived at independently: how many periods each cluster stands for.
	Both must account for the whole year.

	The units differ and the test states them rather than converting silently:
	the kernel's weights are in **hours** (`sum == 8760`), tsam's
	`cluster_counts` are in **periods** (`sum == 365` for a day-length period).
	Reading one as the other is a factor of `period_length` — the same
	units error that has bitten this repository before, so it is named here.
	"""
	frame = _fixture_frame()
	for n_periods in (12, 24, 48):
		_, _, weights = _kernel_result(frame, n_periods)
		assert int(weights.sum()) == 8760, f"kernel weights sum to {weights.sum()} at {n_periods} periods"

		result = _tsam_aggregate(frame, n_periods)
		counts = np.asarray(list(result.cluster_counts.values()), dtype=float)
		assert counts.sum() == pytest.approx(365.0), (
			f"tsam cluster_counts sum to {counts.sum()} at {n_periods} periods, "
			"which is periods and not hours"
		)
		assert counts.sum() * _PERIOD_LENGTH == pytest.approx(8760.0), (
			"the two implementations disagree about how many hours the year has"
		)
		assignments = result.assignments["cluster_idx"].to_numpy()
		assert len(assignments) == 8760
		assert len(set(assignments.tolist())) == n_periods


def test_the_kernel_is_near_optimal_among_the_selections_it_can_make():
	"""The kernel against an exhaustive search of its own hypothesis class.

	WHY this is not a comparison of the kernel's error to tsam's: tsam's
	representative is the cluster **mean**, and the mean is the minimiser of
	squared reconstruction error by construction — so no medoid-based method can
	ever beat it on that metric, and asserting otherwise would be asserting a
	theorem false. Measured, the gap is 31× at 12 periods and grows with
	`n_periods` (102×, 365×), all of it the mean-versus-medoid difference and
	none of it a defect. What *can* be checked is whether the kernel finds a
	good selection within the class it restricts itself to: representatives
	that are real periods of the year.

	So this runs a 15-restart k-medoids over the same 365 candidate days, in the
	kernel's own column-normalised space, and asserts the kernel is close to the
	best selection that search finds. A kernel that scored far above it would be
	leaving reconstruction error on the table — the failure mode the flattest-
	block defect was, where the selection was not merely suboptimal but in the
	wrong part of the year.

	The bar is `1.30`, measured against 1.01/0.97/0.84 for the shipped kernel
	and 363× for the pre-fix contiguous-block rule, so it separates the two
	without being a coin-flip on tie-breaking.
	"""
	frame = _fixture_frame()
	values = frame.to_numpy().astype(np.float64)
	days = values.reshape(len(values) // _PERIOD_LENGTH, _PERIOD_LENGTH, values.shape[1])
	normalised = days / values.mean(axis=0)
	distance = ((normalised[:, None] - normalised[None, :]) ** 2).sum(axis=(2, 3))
	np.fill_diagonal(distance, 0.0)

	def objective(centres: np.ndarray) -> float:
		labels = distance[:, centres].argmin(axis=1)
		return float(distance[np.arange(len(days)), centres[labels]].sum())

	def best_medoids(n_periods: int, restarts: int = 15) -> float:
		best = np.inf
		for restart in range(restarts):
			centres = np.random.default_rng(restart).choice(len(days), n_periods, replace=False)
			for _ in range(60):
				labels = distance[:, centres].argmin(axis=1)
				moved = centres.copy()
				for k in range(n_periods):
					members = np.flatnonzero(labels == k)
					if members.size:
						moved[k] = members[np.argmin(distance[np.ix_(members, members)].sum(axis=1))]
				if np.array_equal(moved, centres):
					break
				centres = moved
			best = min(best, objective(centres))
		return best

	for n_periods in (12, 24, 48):
		_, representatives, _ = _kernel_result(frame, n_periods)
		kernel_centres = np.asarray(representatives, dtype=int) // _PERIOD_LENGTH
		kernel_objective = objective(kernel_centres)

		reference = best_medoids(n_periods)
		assert reference > 0.0, "the reference search found a perfect selection, so the fixture is degenerate"
		ratio = kernel_objective / reference
		assert ratio <= 1.30, (
			f"at {n_periods} periods the kernel's selection scores {ratio:.2f}× the best "
			f"medoid selection a 15-restart search finds ({kernel_objective:.1f} against "
			f"{reference:.1f}) in its own normalised space"
		)


def test_both_constructions_meet_ad_9s_acceptance_rule_on_the_same_year():
	"""The gate that matters, measured on the shipped kernel and on the oracle.

	Reconstruction error is a proxy; AD-9's rule is the product requirement, and
	`03-rust-core.md` §5.3 says the honest response to a fixture that cannot meet
	it is to record the achievable number, not to relax the gate. Both
	constructions are put through the real network and the real solve, and both
	must pass — which is what makes the medoid-versus-mean difference a design
	choice rather than a defect.
	"""
	from alea.planning.aggregation import (
		aggregate_network,
		validate_aggregation_artefact,
	)
	from tests.ci.test_planning_layer1 import _seasonal_network

	load, solar, snapshots = _seasonal_year()
	full = _seasonal_network(load, solar, snapshots)
	full.optimize(solver_name="highs", log_to_console=False)

	frame = _fixture_frame()
	for n_periods in (12, 24):
		aggregated = aggregate_network(full, n_periods=n_periods, period_length=_PERIOD_LENGTH)
		aggregated.optimize(solver_name="highs", log_to_console=False)
		kernel = validate_aggregation_artefact(
			full, aggregated, n_periods=n_periods, period_length=_PERIOD_LENGTH
		)
		assert kernel.passes, (
			f"the shipped kernel's own construction fails AD-9 at {n_periods} periods: "
			f"cost {kernel.cost_error_pct:.3f}%, mix {kernel.capacity_mix_l1_error_pct:.3f}%"
		)

		oracle = _tsam_network(frame, n_periods)
		oracle.optimize(solver_name="highs", log_to_console=False)
		measured = validate_aggregation_artefact(
			full, oracle, n_periods=n_periods, period_length=_PERIOD_LENGTH
		)
		assert measured.passes, (
			f"the foreign implementation fails AD-9 at {n_periods} periods, so the "
			f"tolerance is not attainable on this fixture: cost {measured.cost_error_pct:.3f}%, "
			f"mix {measured.capacity_mix_l1_error_pct:.3f}%"
		)


def test_the_representative_periods_are_real_periods_of_the_year():
	"""The property that makes the kernel's answer reportable, and tsam's not.

	The kernel's representative is the first timestep of a block that exists in
	the input series, so an operator can be told which part of the year stands
	for which. tsam's representative is a cluster mean, which is a period the
	year never had. That is a deliberate design difference, not a defect, and it
	is asserted here so the difference is a decision on the record rather than
	something a future refactor discovers by accident.

	Checked as membership: every representative names a block whose first
	timestep lies inside the year, and the reconstructed series equals the
	verbatim slice of the year at that block — not a mean, not an interpolation.
	The oracle's own representatives are asserted *not* to have this property
	for at least one cluster on this fixture, which is what makes the difference
	a measured fact rather than a claim in a docstring.
	"""
	frame = _fixture_frame()
	values = frame.to_numpy()
	n_blocks = len(values) // _PERIOD_LENGTH

	for n_periods in (12, 24, 48):
		assignments, representatives, _ = _kernel_result(frame, n_periods)
		blocks = np.asarray(representatives, dtype=int) // _PERIOD_LENGTH
		assert len(set(blocks.tolist())) == n_periods, "two representatives name the same block"
		assert int(blocks.min()) >= 0 and int(blocks.max()) < n_blocks, (
			"a representative names a block outside the year"
		)

		# Every reconstructed timestep is a verbatim hour of the source year.
		rebuilt = values[np.asarray(representatives, dtype=int)[np.asarray(assignments, dtype=int)]]
		assert rebuilt.shape == values.shape
		verbatim = np.isin(rebuilt[:, 0], values[:, 0]) & np.isin(rebuilt[:, 1], values[:, 1])
		assert verbatim.mean() > 0.95, (
			"the kernel's reconstruction is mostly not verbatim source hours, so its "
			"representatives are not real periods"
		)

		# The oracle, by contrast, reconstructs from cluster means: at least one
		# of its representative values is a value the year never contained.
		result = _tsam_aggregate(frame, n_periods)
		tsam_values = result.cluster_representatives.to_numpy()
		absent = ~np.isin(tsam_values[:, 0], values[:, 0])
		assert absent.any(), (
			"tsam's representatives are all verbatim hours, so the medoid-versus-mean "
			"distinction this test documents does not hold on this fixture"
		)


def test_the_kernel_is_deterministic_where_the_oracle_is_merely_repeatable():
	"""AD-8, against an implementation that makes no such promise.

	two processes given one seed must produce one aggregation. tsam happens to
	be repeatable in-process, but determinism across seeds and processes is not
	its contract; it is the kernel's. Assert the kernel's, and assert the oracle
	is stable enough to be a witness at all.
	"""
	frame = _fixture_frame()

	first = _kernel_result(frame, 12)
	second = _kernel_result(frame, 12)
	assert np.array_equal(first[0], second[0]), "assignments differ between two identical calls"
	assert np.array_equal(first[1], second[1]), "representatives differ between two identical calls"
	assert np.array_equal(first[2], second[2]), "weights differ between two identical calls"

	# A different seed may move the selection, but must not move the invariant.
	_, _, weights = kernel_aggregate(frame.to_numpy().astype(np.float32), 12, _PERIOD_LENGTH, 7)
	assert int(weights.sum()) == 8760

	assignments = _tsam_aggregate(frame, 12).assignments["cluster_idx"].to_numpy()
	again = _tsam_aggregate(frame, 12).assignments["cluster_idx"].to_numpy()
	assert np.array_equal(assignments, again), "the oracle is not repeatable, so it cannot witness anything"


def test_neither_implementation_puts_every_representative_in_one_fortnight():
	"""The shape of the defect that was live, checked on both sides.

	The kernel used to score each block by its own internal spread and take the
	flattest, which on a seasonal year put all twelve representatives inside one
	December fortnight and cost +106% against AD-9's 2%. The foreign
	implementation never had that bug, so its span is the sanity check that the
	*question* is answerable — a fixture where even tsam clustered into one
	fortnight would be a fixture with no seasonality to preserve.
	"""
	frame = _fixture_frame()
	day = np.arange(8760) // 24

	for n_periods in (12, 24):
		_, representatives, _ = _kernel_result(frame, n_periods)
		blocks = np.asarray(representatives, dtype=int) // _PERIOD_LENGTH
		span = int(blocks.max() - blocks.min())
		assert span >= 300, f"kernel representatives span only {span} days at {n_periods} periods"

		result = _tsam_aggregate(frame, n_periods)
		assignments = result.assignments["cluster_idx"].to_numpy()
		chosen = np.array(
			[
				int(day[assignments == k][0])
				for k in sorted(set(assignments.tolist()))
				if (assignments == k).any()
			]
		)
		assert int(chosen.max() - chosen.min()) >= 300, (
			"the oracle clustered the year into one part of it, so the fixture has no seasonality"
		)


def test_the_tolerances_are_the_plans_and_not_a_local_weakening():
	"""AD-9's numbers, read from the module that enforces them.

	`03-rust-core.md` §5.3 fixes 2% cost and 5% mix, and says the honest
	response to a fixture that cannot meet them is to record the achievable
	number, not to relax the gate silently. This asserts the constants are
	still the plan's, so a future edit that widens them has to widen them here
	too and say so.
	"""
	from alea.planning.aggregation import TOLERANCE_COST_PCT, TOLERANCE_MIX_PCT

	assert TOLERANCE_COST_PCT == 2.0, f"AD-9's cost tolerance is 2%, found {TOLERANCE_COST_PCT}"
	assert TOLERANCE_MIX_PCT == 5.0, f"AD-9's mix tolerance is 5%, found {TOLERANCE_MIX_PCT}"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
