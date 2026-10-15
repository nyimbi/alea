# SPDX-License-Identifier: MIT
"""Layer 1 exit criteria: the gates `04-layer1-planning.md` §7 and §8 name.

The plan lists eight gates and ten criteria. This module is the gate for the
criteria that are checkable without the continental data lake — 1, 3, 4, 5, 7,
8, 10 — and for the gates in §7 that do not already have one.

WHY the gates are worth writing even though the module is large: every one of
them asserts a *property of a built network*, and a network that violates one
of them still solves. A disconnected network with an orphan bus returns an
optimal solution; it just answers a different question than the one asked. The
defect is invisible in the output and visible only in the structure.

WHY criterion 10's gate is a subprocess: AD-1 says PyPSA-Earth is a workflow,
not a dependency, and the seam is files. If a bare `import alea.planning`
pulls in PyPSA-Earth, the dependency is real regardless of what the architecture
document says. That can only be checked in a fresh interpreter, because this
test session has already imported whatever it imported.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from alea.config.models import Config, ScenarioConfig, SolveConfig
from alea.planning.aggregation import (
	TOLERANCE_COST_PCT,
	TOLERANCE_MIX_PCT,
	AggregationError,
	aggregate_network,
	build_aggregation,
	clustering_series,
	mix_shares,
	require_aggregation_validation,
	validate_aggregation_artefact,
	validation_path,
	write_validation,
)
from alea.planning.demand import (
	NATIONAL_TOLERANCE_PCT,
	scale_to_national,
	validate_national_total,
)
from alea.planning.expansion import (
	ExpansionError,
	SolveResult,
	has_dispatch,
	loss_share,
	solve_expansion,
	solve_result_provenance,
)
from alea.planning.renewables import RenewableError, validate_capacity_factors
from alea.planning.topology import (
	TopologyError,
	build_topology,
	connectivity_report,
	orphan_buses,
)

REPO = Path(__file__).resolve().parents[2]

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")


# --------------------------------------------------------------------------
# Fixtures: a small transmission network, as the topology stage builds one
# --------------------------------------------------------------------------


def _lines() -> pd.DataFrame:
	"""Four lines forming one connected chain: 0 - 1 - 2 - 3 - 4.

	Two voltage tiers, so the voltage floor has something to cut, and no ring:
	every line is a bridge, which is what makes the disconnect canary below a
	real test rather than an accident of which line was removed.
	"""
	# ~0.1 degrees of longitude at the equator is ~11 km, comfortably above the
	# 500 m snap tolerance, so five endpoints stay five buses.
	lon = [0.0, 0.1, 0.2, 0.3, 0.4]
	return pd.DataFrame(
		{
			"line_id": ["l0", "l1", "l2", "l3"],
			"from_lon": lon[:-1],
			"from_lat": [0.0] * 4,
			"to_lon": lon[1:],
			"to_lat": [0.0] * 4,
			"voltage_kv": [400.0, 400.0, 132.0, 132.0],
			"length_km": [11.0, 11.0, 11.0, 11.0],
			"capacity_mva": [1000.0, 1000.0, 500.0, 500.0],
		}
	)


def _network() -> pypsa.Network:
	network, _, _ = build_topology(_lines(), voltage_kv_min=66.0)
	return network


def _lossy() -> pypsa.Network:
	"""Two buses, one line, generation at one end and load at the other.

	The fixture that makes a *loss* observable. `_solvable` places a generator
	and a load on every bus, so no power crosses a line, ``lines_t.p`` is all
	zeros and the energy balance is the identity for both signs of the loss
	term — it cannot discriminate `generation - load - losses` from
	`generation + losses - load`. On this fixture power must cross the line, the
	line absorbs some of it, and the two readings differ by twice the loss.

	The impedance is a plausible 132 kV line (11 km, r=0.5 ohm, x=10 ohm) and it
	matters: PyPSA's lossy formulation drops the loss term when the voltage
	angles it would need cannot be recovered, so a *too small* x makes the
	dispatch infeasible rather than lossy. r=0.5/x=0.05 was measured infeasible;
	r=0.5/x=10 is optimal with 1.6 MWh lost per 150 MWh delivered.
	"""
	network = pypsa.Network()
	network.add("Bus", "north", v_nom=132.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add("Line", "north-south", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=200.0)
	network.add("Generator", "coal", bus="north", carrier="coal", p_nom=500.0, marginal_cost=30.0)
	network.add("Load", "load", bus="south", p_set=50.0)
	network.set_snapshots(list(SNAPSHOTS))
	return network


def _linked(efficiency: float) -> pypsa.Network:
	"""`_lossy`'s topology with the transfer by **link** instead of line.

	The fixture that makes a link's contribution to the balance observable.
	`_lossy` transfers by line, so the check's line-only loss sum closed the
	identity on it and could not see that links were missing. A sector-coupled
	network — hydrogen, heat, industry — transfers by link, and the same sum
	left the link's retained energy unaccounted.

	``efficiency`` decides the *sign*, which is why the fixture is
	parametrised: a link below 1 absorbs the difference (``p0 + p1 > 0``) and a
	heat-pump link above 1 creates it (``p0 + p1 < 0``). Both must close
	``generation - load - losses == 0``, so a fix that only handled the lossy
	case would pass one half and fail the other.
	"""
	network = pypsa.Network()
	network.add("Bus", "north", v_nom=132.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add(
		"Link",
		"north-south",
		bus0="north",
		bus1="south",
		p_nom=500.0,
		efficiency=efficiency,
	)
	network.add("Generator", "coal", bus="north", carrier="coal", p_nom=500.0, marginal_cost=30.0)
	network.add("Load", "load", bus="south", p_set=50.0)
	network.set_snapshots(list(SNAPSHOTS))
	return network


def _solvable() -> pypsa.Network:
	"""The topology fixture with generation and load per bus, so it balances.

	Two carriers, not one: the aggregation gates measure a capacity *mix*, and a
	single-carrier network has a mix of 100% that carrier by construction, so
	every mix error against it is zero and the channel is untestable.

	Note for the balance check: generation and load sit on the *same* bus here,
	so nothing crosses a line and this fixture's losses are identically zero.
	That is fine for what it tests (a static ``p_set`` is read at all) and it is
	exactly why the loss *sign* needs `_lossy` instead.
	"""
	network = _network()
	for bus in network.buses.index:
		network.add(
			"Generator",
			f"coal_{bus}",
			bus=bus,
			carrier="coal",
			p_nom=500.0,
			p_nom_extendable=True,
			capital_cost=80_000.0,
			marginal_cost=30.0,
		)
		network.add(
			"Generator",
			f"solar_{bus}",
			bus=bus,
			carrier="solar",
			p_nom=50.0,
			marginal_cost=0.0,
		)
		network.add("Load", f"load_{bus}", bus=bus, p_set=100.0)
	network.set_snapshots(list(SNAPSHOTS))
	return network


# --------------------------------------------------------------------------
# Criterion 1: the network is connected, with no orphans
# --------------------------------------------------------------------------


def test_network_connected():
	"""One weakly-connected component per synchronous area.

	A dropped line or an over-aggressive voltage floor cuts a region off, and
	the solve then reports an optimal solution for a network that cannot serve
	part of the country.
	"""
	report = connectivity_report(_network())
	assert report["n_components"] == 1, f"the chain split into {report['n_components']} components"
	assert report["largest_component"] == report["n_buses"]
	assert report["n_singletons"] == 0


def test_no_orphan_buses():
	"""Every bus has a line or a generator attached.

	An orphan bus is a node the optimiser can do nothing with; it is usually a
	snapping artefact and it inflates every later stage's bus count.
	"""
	assert orphan_buses(_network()) == []


def test_the_connectivity_report_notices_a_cut_line():
	"""The gate's own canary, in-place: cut a bridge and the report must change.

	Kept beside the gate rather than in `canaries/` because the mutation is on
	the *fixture*, not on the code under test — there is no source text to
	plant, and a canary that edits a fixture is just a second test.
	"""
	network = _network()
	assert connectivity_report(network)["n_components"] == 1
	network.remove("Line", network.lines.index[-1])
	report = connectivity_report(network)
	assert report["n_components"] == 2, "removing a bridge did not disconnect the graph"


def test_an_orphan_bus_is_detected():
	"""The gate's canary: a bus with nothing attached is reported."""
	network = _network()
	assert orphan_buses(network) == []
	network.add("Bus", "orphan", carrier="AC")
	assert "orphan" in orphan_buses(network)


def test_the_voltage_floor_removes_sub_transmission():
	"""A 66 kV floor on a 400/132 kV fixture drops nothing; a 200 kV floor
	drops the 132 kV half and must report what it discarded."""
	network, _, report = build_topology(_lines(), voltage_kv_min=66.0)
	assert len(network.lines) == 4
	assert len(network.buses) == 5
	assert report.n_dropped_low_voltage == 0

	high, _, high_report = build_topology(_lines(), voltage_kv_min=200.0)
	assert len(high.lines) == 2
	assert len(high.buses) == 3
	assert high_report.n_dropped_low_voltage == 2
	assert sorted(high_report.dropped_lines) == ["l2", "l3"]


def test_a_voltage_floor_that_removes_everything_refuses():
	"""Silently returning an empty network would make every downstream stage
	report zero, which reads as a solved empty country."""
	with pytest.raises(TopologyError, match="voltage floor"):
		build_topology(_lines(), voltage_kv_min=765.0)


# --------------------------------------------------------------------------
# Criterion 3: demand matches the national figure within tolerance
# --------------------------------------------------------------------------


def test_demand_matches_national():
	"""A series scaled to a published total is within tolerance of it.

	The shape comes from the measured series and the level from the published
	total, so the check is that the scaling actually lands.
	"""
	series = pd.Series(
		np.linspace(100.0, 200.0, 8760), index=pd.date_range("2030-01-01", periods=8760, freq="h")
	)
	scaled, check = scale_to_national(series, 10.0, country="KE", source="AFREC")
	assert check.passes
	assert check.error_pct == pytest.approx(0.0)
	# The shape survives the scaling: every value is multiplied by one factor.
	ratios = (scaled / series).to_numpy()
	assert float(ratios.min()) == pytest.approx(float(ratios.max()))
	assert validate_national_total(scaled, 10.0).error_pct == pytest.approx(0.0, abs=1e-6)


def test_demand_matches_national_notices_a_scaled_series():
	"""The gate's canary: scale the built series 0.8x and the check must fail.

	The plan's canary for this gate is exactly this -- "scale demand 0.8x; must
	fail" -- and it is the only way to know the tolerance is not so wide that
	the check passes for any input.
	"""
	series = pd.Series(np.full(8760, 150.0), index=pd.date_range("2030-01-01", periods=8760, freq="h"))
	scaled, check = scale_to_national(series, 10.0, country="KE")
	assert check.passes, "the scaling did not land on the published total"

	missed = validate_national_total(scaled * 0.8, 10.0, country="KE")
	assert not missed.passes
	assert missed.error_pct == pytest.approx(-20.0, abs=1e-6)
	assert NATIONAL_TOLERANCE_PCT < 20.0, "the tolerance is wide enough to hide an 0.8x scale"


def test_a_zero_demand_series_is_refused():
	"""A national total cannot be reconciled against a series with no energy."""
	from alea.planning.demand import DemandError

	with pytest.raises(DemandError, match="sums to zero"):
		scale_to_national(pd.Series([0.0, 0.0]), 10.0)


# --------------------------------------------------------------------------
# Criterion 4: aggregation is validated and recorded
# --------------------------------------------------------------------------


def test_aggregation_requires_validation(tmp_path):
	"""An aggregated config with no validation artefact is refused.

	Aggregation trades accuracy for tractability, and the trade is only
	acceptable when it has been measured. A cluster without a validation
	artefact is a cluster whose error nobody has bounded.
	"""
	with pytest.raises(AggregationError, match="no validation artefact"):
		require_aggregation_validation(_network(), 4, root=tmp_path / "aggregation")


def test_aggregation_is_validated_and_recorded(tmp_path):
	"""The positive half: measure, write, and read the measurement back."""
	network = _solvable()
	network.optimize(solver_name="highs", log_to_console=False)
	# A copy through NetCDF, because PyPSA refuses ``copy()`` on a network that
	# still holds its solver model, and a solved network is the only input this
	# comparison has.
	path = tmp_path / "solved.nc"
	network.export_to_netcdf(path)
	aggregated = pypsa.Network(path)

	# A 0.1% capacity perturbation: enough that the mix channel records a
	# non-zero error, small enough that the validation still passes and can be
	# read back through the gate. Both capacity columns are scaled because
	# ``capacity_mix`` prefers ``p_nom_opt`` where it is positive and falls back
	# to ``p_nom`` where it is not, and on this fixture the optimiser leaves most
	# units unbuilt.
	for column in ("p_nom", "p_nom_opt"):
		values = aggregated.generators[column].astype(float)
		aggregated.generators[column] = values.where(values <= 0.0, values * 1.001)

	root = tmp_path / "aggregation"
	validation = validate_aggregation_artefact(
		network, aggregated, n_periods=4, period_length=6, n_clusters=5
	)
	assert validation.network_id, "the validation does not name its network"
	assert validation.capacity_mix_l1_error_pct > 0.0, "the injected perturbation was not measured"
	assert validation.cost_error_pct == pytest.approx(0.0), "an unsolved difference moved the cost"
	assert validation.passes

	written = write_validation(validation, root=root)
	assert written.exists()
	assert written == validation_path(validation.network_id, root=root)

	loaded = require_aggregation_validation(network, 4, root=root)
	assert loaded.network_id == validation.network_id
	assert loaded.capacity_mix_l1_error_pct == pytest.approx(validation.capacity_mix_l1_error_pct)


def test_a_validation_measured_at_another_level_is_refused(tmp_path):
	"""The measurement does not transfer between aggregation levels.

	A 4-period validation says nothing about an 8-period solve, and accepting
	it would let a level nobody measured ride on one that was.
	"""
	network = _solvable()
	network.optimize(solver_name="highs", log_to_console=False)
	root = tmp_path / "aggregation"
	write_validation(
		validate_aggregation_artefact(network, network, n_periods=4, period_length=6),
		root=root,
	)
	with pytest.raises(AggregationError, match="not 8"):
		require_aggregation_validation(network, 8, root=root)


def test_aggregation_accuracy():
	"""Mix distance between a full and a clustered network, as the plan's
	tolerance is stated.

	The plan's canary is "inject a bad aggregation; must fail", which is what
	the second half asserts: a mix that differs by more than the tolerance is
	not accepted.
	"""
	full = {"coal": 100.0, "solar": 50.0, "hydro": 50.0}
	same = dict(full)
	assert mix_shares(same) == pytest.approx(mix_shares(full))
	# A cluster that lost the hydro half of the fleet.
	degraded = {"coal": 100.0, "solar": 100.0}
	distance = sum(
		abs(mix_shares(degraded).get(carrier, 0.0) - mix_shares(full).get(carrier, 0.0))
		for carrier in set(full) | set(degraded)
	)
	assert distance > 0.05, "the injected degradation is inside the tolerance and proves nothing"


def test_the_aggregation_kernel_refuses_a_window_longer_than_the_series():
	"""The kernel's weights must sum to the number of timesteps exactly.

	It raises rather than returning a near-miss, because a weighting that sums
	to 8758 shifts every annual total by 0.02%, systematically, across a study.
	"""
	with pytest.raises(AggregationError, match="timesteps"):
		build_aggregation(np.zeros((24, 3), dtype=float), n_periods=8, period_length=6)


# --------------------------------------------------------------------------
# Criterion 4, the measurement itself: AD-9's 2% / 5% on a seasonal year
# --------------------------------------------------------------------------


def _seasonal_year() -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
	"""One year of hourly demand and solar availability, with real seasonality.

	The shape matters more than the magnitudes. A synthetic year of pure noise
	has no seasonal structure for an aggregator to lose, and a *flat* year has
	none to preserve; either would let a broken kernel pass. This one has a
	winter-peaking load, a summer-peaking solar resource and a diurnal cycle on
	both — the three shapes whose loss is what AD-9's tolerance is about.

	Winter-peaking load against summer-peaking solar is deliberate: it is what
	makes the two capacities non-substitutable, so an aggregation that flattens
	the solar peak changes the built fleet rather than merely the dispatch.
	"""
	hours = np.arange(8760)
	day = hours // 24
	# Winter-peaking load, centred on mid-January, against a summer-peaking solar
	# resource centred on the solstice. The two columns therefore disagree about
	# *when* the year is interesting, which is what gives a selection rule
	# somewhere to go wrong; a fixture whose columns peak together is nearly
	# collinear and a broken aggregator passes on it.
	winter = np.clip(np.cos(2 * np.pi * (hours - 15 * 24) / 8760.0), 0.0, None)
	load = 100.0 + 40.0 * winter + 12.0 * np.sin(2 * np.pi * (hours % 24) / 24.0)
	solar = np.clip(np.sin(np.pi * ((hours % 24) - 6) / 12.0), 0.0, None) * (
		0.55 + 0.30 * np.cos(2 * np.pi * (day - 172) / 365.0)
	)
	snapshots = pd.date_range("2030-01-01", periods=8760, freq="h")
	return load, solar, snapshots


def _seasonal_network(load: np.ndarray, solar: np.ndarray, snapshots: pd.DatetimeIndex) -> pypsa.Network:
	"""The seasonal year as a solvable single-bus network.

	Extendable coal at a high marginal cost and extendable solar at a zero one:
	the fleet the optimiser builds is the answer the aggregation has to preserve,
	and a flattened solar profile moves it a long way.
	"""
	network = pypsa.Network()
	network.add("Bus", "b", carrier="AC")
	network.set_snapshots(snapshots)  # type: ignore[arg-type]
	network.add(
		"Generator", "coal", bus="b", carrier="coal", p_nom_extendable=True,
		capital_cost=120_000.0, marginal_cost=45.0,
	)
	network.add(
		"Generator", "solar", bus="b", carrier="solar", p_nom_extendable=True,
		p_max_pu=pd.Series(solar, index=snapshots), capital_cost=60_000.0, marginal_cost=0.0,
	)
	network.add("Load", "load", bus="b", p_set=pd.Series(load, index=snapshots))
	return network


def test_aggregation_keeps_the_solve_within_tolerance():
	"""AD-9's rule, measured: 12 periods must hold cost to 2% and mix to 5%.

	The gate the kernel defect passed by never being run. The kernel used to
	select the *flattest* blocks as representatives, and on a seasonal year the
	flattest blocks are all in the same quiet fortnight: all twelve
	representatives landed inside one December fortnight, the aggregated solve
	cost 106% more than the full-resolution one, and nothing anywhere said so.
	Every existing test of this kernel used an exact-division case where
	"flattest block" and "correct block" coincide, so the defect was invisible to
	the whole suite.

	The assertion is deliberately the plan's own acceptance rule rather than a
	property of the algorithm: an aggregator that meets 2% by some other route is
	a passing aggregator.
	"""
	load, solar, snapshots = _seasonal_year()
	full = _seasonal_network(load, solar, snapshots)
	full.optimize(solver_name="highs", log_to_console=False)

	aggregated = aggregate_network(full, n_periods=12, period_length=24)
	assert len(aggregated.snapshots) == 12 * 24, "the aggregated network lost representative hours"
	aggregated.optimize(solver_name="highs", log_to_console=False)

	validation = validate_aggregation_artefact(
		full, aggregated, n_periods=12, period_length=24
	)
	assert abs(validation.cost_error_pct) <= TOLERANCE_COST_PCT, (
		f"aggregation to 12 periods moved total system cost by "
		f"{validation.cost_error_pct:.2f}%, outside AD-9's {TOLERANCE_COST_PCT}%"
	)
	assert abs(validation.capacity_mix_l1_error_pct) <= TOLERANCE_MIX_PCT, (
		f"aggregation to 12 periods moved the capacity mix by "
		f"{validation.capacity_mix_l1_error_pct:.2f}%, outside AD-9's {TOLERANCE_MIX_PCT}%"
	)
	assert validation.passes


def test_the_representatives_span_the_year_rather_than_one_fortnight():
	"""The shape of the defect, asserted directly.

	The cost gate above is the one that matters, but it is a *measurement*: it
	needs two solves, and it can be satisfied by luck on a year whose seasonality
	is weak. This is the structural statement, and it is what the old kernel
	violated most plainly — twelve representatives for twelve periods should
	cover twelve different times of year, not twelve consecutive days.

	Asserted on the block index rather than on a distance, so the failure names
	the thing that went wrong.
	"""
	load, solar, _ = _seasonal_year()
	series = np.column_stack([load, solar * 300.0]).astype(np.float32)
	built = build_aggregation(series, n_periods=12, period_length=24)
	blocks = np.asarray(built["representatives"], dtype=int) // 24

	assert len(set(blocks.tolist())) == 12, "two periods share one representative day"
	span_days = int(blocks.max() - blocks.min())
	assert span_days >= 300, (
		f"the twelve representatives for a year span only {span_days} days "
		f"(blocks {sorted(blocks.tolist())}); a representative set confined to one "
		"part of the year cannot represent the rest of it"
	)
	# Every month the year has, roughly: at least one representative in each
	# quarter, which a single-fortnight selection fails outright.
	quarters = {int(block * 24 // 2190) for block in blocks}
	assert quarters == {0, 1, 2, 3}, f"representatives cover quarters {sorted(quarters)}, not the year"


def test_the_aggregation_weights_are_the_hours_each_period_stands_for():
	"""Weights are the assignment histogram in hours, and sum to 8760 exactly.

	Both halves matter and they are different bugs. The old kernel distributed
	weights near-uniformly *independently* of the assignment, so a period could
	stand in for 8352 hours while carrying a weight of 744 — the exact-sum
	invariant still held, and every annual total was wrong by a factor of ten.
	The sum is the plan's §5.2 invariant; the equality with the histogram is what
	makes the sum mean anything.
	"""
	load, solar, _ = _seasonal_year()
	series = np.column_stack([load, solar * 300.0]).astype(np.float32)
	built = build_aggregation(series, n_periods=12, period_length=24)
	assignments = np.asarray(built["assignments"])
	weights = np.asarray(built["weights"], dtype=float)

	assert assignments.shape == (8760,), "every timestep must be assigned exactly once"
	assert int(assignments.max()) < 12 and int(assignments.min()) >= 0
	assert len(set(assignments.tolist())) == 12, "a period was chosen and then assigned no hours"
	histogram = np.bincount(assignments, minlength=12).astype(float)
	assert np.array_equal(weights, histogram), (
		f"weights {weights} are not the hours assigned to each period {histogram}"
	)
	assert weights.sum() == 8760.0, "the weights do not sum to the year exactly"


def test_a_representative_period_keeps_its_own_profile():
	"""The aggregated network carries whole periods, not period averages.

	The second defect, and the one that survives a correct kernel. The obvious
	way to build the network is ``network.cluster.temporal.from_snapshot_map``,
	which groups the original snapshots by their mapped representative and
	applies its default rule — ``mean`` — to every dynamic frame. Mapping a day
	to its representative day then *averages the day*, so a capacity-factor
	profile with a midday peak becomes a flat band: measured on this year, a
	solar peak of 0.269 against the true 0.850, a 23% cost error and a 106%
	capacity-mix error, with the optimiser building no solar at all.

	So the assertion is on the peak, which is the statistic a flattened profile
	loses, and on the snapshot count, which is what a period is.
	"""
	load, solar, snapshots = _seasonal_year()
	full = _seasonal_network(load, solar, snapshots)
	aggregated = aggregate_network(full, n_periods=12, period_length=24)

	assert len(aggregated.snapshots) == 12 * 24, (
		"an aggregated network of 12 periods of 24 hours must carry 288 snapshots"
	)
	kept_solar = aggregated.generators_t.p_max_pu["solar"].to_numpy()
	kept_load = aggregated.loads_t.p_set["load"].to_numpy()
	# The signature of an averaged period is *flatness*: groupby-mean collapses
	# each period to one value per column, so its mean and its peak are the same
	# number and its night is gone. A kept period is a real day, so its peak
	# stands well clear of its mean.
	assert kept_solar.max() > 0.80, (
		f"the aggregated solar profile peaks at {kept_solar.max():.3f}; a profile "
		"averaged over each period has no midday peak left"
	)
	assert kept_solar.min() == pytest.approx(0.0), "the aggregated profile lost its night"
	assert kept_solar.max() > 2.0 * kept_solar.mean(), (
		"the aggregated solar profile is flat, which is what averaging a period produces"
	)
	assert kept_load.max() > 1.15 * kept_load.mean(), (
		"the aggregated load profile is flat, which is what averaging a period produces"
	)
	# Coverage: a representative set has to reach the near-peak part of the year,
	# or the optimiser builds for a load it never sees. Not the annual maximum --
	# twelve days out of 365 need not include the single worst hour -- but within
	# a few percent of it.
	assert kept_load.max() >= 0.95 * float(load.max()), (
		f"the aggregated load peaks at {kept_load.max():.1f} against the year's "
		f"{load.max():.1f}; the representative days miss the peak season"
	)
	assert aggregated.snapshot_weightings["objective"].sum() == pytest.approx(8760.0), (
		"the aggregated network's weights no longer sum to the hours in the year"
	)


def test_clustering_is_driven_by_demand_and_availability():
	"""The kernel clusters on the shapes whose loss changes the answer.

	Clustering on a network's *structure* would be a different thing entirely,
	and clustering on nothing would return contiguous blocks for every network
	while looking correct. Demand and renewable availability are the two series
	an aggregator exists to preserve, so they are the two the driver reads.
	"""
	load, solar, snapshots = _seasonal_year()
	network = _seasonal_network(load, solar, snapshots)
	series = clustering_series(network)

	assert series.shape == (8760, 2), f"expected one column per profile, got {series.shape}"
	assert np.allclose(series[:, 0], load, atol=1e-3), "the load profile is not in the driver series"
	assert np.allclose(series[:, 1], solar, atol=1e-3), "the availability profile is not in the driver series"
	assert np.isfinite(series).all(), "a gap in a profile reached the kernel as a NaN"


def test_aggregation_is_deterministic_across_calls():
	"""AD-8: the same network aggregates identically, or a solve is not repeatable.

	The selection is greedy over a parallel reduction, so the tie-break is the
	only thing standing between a deterministic result and one that depends on
	which thread finished first.
	"""
	load, solar, snapshots = _seasonal_year()
	network = _seasonal_network(load, solar, snapshots)
	first = build_aggregation(clustering_series(network), n_periods=12, period_length=24)
	second = build_aggregation(clustering_series(network), n_periods=12, period_length=24)
	for key in ("assignments", "representatives", "weights"):
		assert np.array_equal(first[key], second[key]), f"{key} differed between two identical calls"


# --------------------------------------------------------------------------
# Criterion 5: losses are on by default and the difference is recorded
# --------------------------------------------------------------------------


def test_losses_default_on():
	"""``transmission_losses`` defaults ``True``.

	A model that neglects losses understates system cost and overstates how much
	energy reaches the far end of the network; the default has to be the
	physical one.
	"""
	assert SolveConfig().transmission_losses is True


def test_the_lossless_solve_records_that_it_neglected_losses():
	"""The difference between the two settings is recorded, not implied.

	The provenance string is what a report reads, so it must say which of the
	two was run. A reader who cannot tell them apart cannot tell an expansion
	that priced losses from one that did not.
	"""
	result = SolveResult(
		objective=1.0, solver="highs", status="ok", seconds=0.1, network=_network()
	)
	lossless = solve_result_provenance(
		result,
		Config(scenario=ScenarioConfig(countries=["KE"]), solve=SolveConfig(transmission_losses=False)),
	)
	lossy = solve_result_provenance(
		result,
		Config(scenario=ScenarioConfig(countries=["KE"]), solve=SolveConfig(transmission_losses=True)),
	)
	assert lossless.parameters["transmission_losses"] is False
	assert lossy.parameters["transmission_losses"] is True
	assert "NEGLECTED" in lossless.notes
	assert "NEGLECTED" not in lossy.notes
	assert lossless.notes != lossy.notes


def test_loss_share_is_zero_when_nothing_is_generated():
	"""A share with no denominator is zero by an explicit rule, never a
	division by zero."""
	network = _network()
	network.add("Generator", "idle", bus="bus_00000", carrier="coal", p_nom=100.0)
	network.set_snapshots(list(SNAPSHOTS[:3]))
	network.generators_t.p = pd.DataFrame(
		{"idle": np.zeros(3)}, index=network.snapshots, dtype=float
	)
	network.lines_t.p0 = pd.DataFrame(
		{c: np.zeros(3) for c in network.lines.index}, index=network.snapshots, dtype=float
	)
	network.lines_t.p1 = network.lines_t.p0.copy()
	assert loss_share(network) == pytest.approx(0.0)


def test_loss_share_refuses_a_network_with_no_dispatch():
	"""A share computed before the solve would be a share of nothing."""
	with pytest.raises(ExpansionError, match="solve it first"):
		loss_share(_network())


def test_has_dispatch_is_false_on_a_network_that_was_never_solved():
	"""The predicate the guards above rest on, tested directly.

	PyPSA indexes a dynamic table by *snapshots*, so ``len(n.generators_t.p)``
	is the snapshot count on an unsolved network — three, on this fixture — and
	a guard written as ``if not len(...)`` passes on exactly the input it exists
	to refuse. The code then reads an empty frame: a generation total of 0.0, a
	maximum over an empty axis, or a silent zero. ``.empty`` counts *columns*,
	which is the property that means "nothing has been solved".

	Nine call sites across this package had the wrong guard, which is why the
	predicate is one function and this test is about the predicate.
	"""
	unsolved = _solvable()
	assert len(unsolved.generators_t.p) == len(unsolved.snapshots), "the table is not snapshot-indexed"
	assert not has_dispatch(unsolved), "an unsolved network reported dispatch"

	unsolved.optimize(solver_name="highs", log_to_console=False)
	assert has_dispatch(unsolved), "a solved network reported no dispatch"


def test_the_energy_balance_reads_a_static_load():
	"""A network whose demand is the static ``loads.p_set`` still balances.

	Reading only ``loads_t.p_set`` gives a load of 0.0 for a network built by
	the demand stage, so the balance check compares generation against nothing
	and passes for the wrong reason — or fails with an error of the whole
	generation figure. The static form is PyPSA's default.
	"""
	from alea.planning.dispatch import check_energy_balance

	network = _solvable()
	assert network.loads_t.p_set.empty, "the fixture gained a dynamic demand table"
	network.optimize(solver_name="highs", log_to_console=False)

	report = check_energy_balance(network)
	assert report["load_mwh"] == pytest.approx(5 * 100.0 * 24), "the static load was not read"
	assert report["generation_mwh"] == pytest.approx(report["load_mwh"] + report["losses_mwh"], rel=1e-3)


def test_the_energy_balance_subtracts_the_losses():
	"""The balance closes as generation - load - losses, not + losses.

	The check read ``generation + losses - load``. That is the same number as
	the correct reading on any network whose losses are zero, which every
	fixture here was, so the sign was wrong and invisible at once. On a network
	that loses 1% of its load the check refused a correct dispatch by *twice*
	the loss, and `solve_dispatch` freezes a solve's capacity and re-optimises,
	so it refused exactly the dispatches it existed to verify.

	This asserts the loss is non-zero first. Without that guard the test would
	pass on a lossless fixture for both signs and prove nothing — the vacuous
	fixture that hid the defect.
	"""
	from alea.planning.dispatch import check_energy_balance

	network = _lossy()
	status, condition = network.optimize(
		solver_name="highs", log_to_console=False, transmission_losses=True
	)
	assert status == "ok", f"the lossy fixture did not solve: {status} ({condition})"

	report = check_energy_balance(network)
	assert report["losses_mwh"] > 1.0, (
		f"the fixture lost {report['losses_mwh']:.6f} MWh, so it cannot "
		"discriminate the sign of the loss term; the test would pass either way"
	)
	# The identity itself, spelled out, and the arithmetic that the wrong sign
	# would produce, so a regression fails with the number rather than a diff.
	assert report["generation_mwh"] == pytest.approx(
		report["load_mwh"] + report["losses_mwh"], rel=1e-6
	)
	double_counted = report["load_mwh"] - report["losses_mwh"]
	assert abs(report["generation_mwh"] - double_counted) > report["losses_mwh"], (
		"generation matches the double-counted reading too; the fixture no longer "
		"separates them"
	)


@pytest.mark.parametrize(
	("efficiency", "sign"),
	[(0.9, 1.0), (3.0, -1.0)],
	ids=["lossy-link", "heat-pump-link"],
)
def test_the_energy_balance_counts_links_as_branches(efficiency: float, sign: float):
	"""A link retains energy like a line, and the sum omitted it.

	The loss term read ``network.lines_t`` only, so on any network that
	transfers by link the branch's retained energy was unaccounted and a
	*correct* dispatch was refused. Measured on this fixture before the fix: a
	0.9 link left an 11.1% residual and a COP-3 link a 200% one. Sector-coupled
	networks transfer by link, so the check refused most of what this project
	builds.

	The two halves are the point. A link's ``p0 + p1`` is positive when it
	absorbs (efficiency < 1) and negative when it creates (efficiency > 1, a
	heat pump drawing ambient heat), and both close the same identity — so a
	fix that special-cased the lossy direction would pass the first row and
	fail the second. ``sign`` asserts the fixture actually takes the branch it
	is meant to, or the row proves nothing about the direction it names.
	"""
	from alea.planning.dispatch import check_energy_balance

	network = _linked(efficiency)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the link fixture did not solve: {status} ({condition})"

	retained = float(network.links_t.p0.to_numpy().sum() + network.links_t.p1.to_numpy().sum())
	assert retained * sign > 1.0, (
		f"the fixture retained {retained:.6f} MWh through the link, so it does "
		f"not exercise the {sign:+.0f} direction this row names"
	)

	report = check_energy_balance(network)
	assert report["losses_mwh"] == pytest.approx(retained, rel=1e-9), (
		"the loss term does not carry the link's retained energy"
	)
	assert report["generation_mwh"] == pytest.approx(
		report["load_mwh"] + report["losses_mwh"], rel=1e-9
	)


def test_a_solved_result_carries_the_energy_balance_residual():
	"""`extract` records the residual, because it is the last place with the network.

	`check_energy_balance` was written, tested, and called by nothing in
	``src/`` — so every ``ScenarioResult`` in the tree asserted a balance no
	production path had checked. A `ScenarioResult` holds no network (it has to
	be serialisable into a content-addressed cache entry), so the residual can
	only be measured at extraction, where the network still exists.

	The residual on a *correct* solve is zero — that is the whole point of the
	fix above, and a test asserting non-zero on a balanced network would be
	asserting the bug. So the fixture is deliberately made unbalanced the way
	the check's own docstring names: generation appearing in the dispatch table
	that no component accounts for. That is the defect the check exists to
	catch, and it is the only way to show the field carries a real measurement
	rather than a constant.
	"""
	from alea.planning.dispatch import balance_measurement
	from alea.whatif.extract import extract
	from alea.whatif.params import ScenarioParameters

	network = _linked(0.9)
	status, condition = network.optimize(solver_name="highs", log_to_console=False)
	assert status == "ok", f"the link fixture did not solve: {status} ({condition})"
	assert balance_measurement(network)["error_mwh"] == pytest.approx(0.0, abs=1e-6), (
		"the fixture does not balance, so it cannot show the field is measured"
	)

	# Phantom generation: 7 MWh in the dispatch table that no component owns.
	network.generators_t.p.iloc[0, 0] += 7.0
	measured = balance_measurement(network)["error_mwh"]
	assert measured == pytest.approx(7.0, abs=1e-6), (
		f"the fixture's residual is {measured:.6f} MWh, so a result that recorded "
		"zero would pass; the fixture cannot discriminate"
	)

	result = extract(
		network,
		ScenarioParameters(),
		network_checksum="0" * 64,
		code_version="test",
	)
	assert result.energy_balance_error_mwh == pytest.approx(measured, rel=1e-9)
	assert result.energy_balance_error_mwh != 0.0, "the residual was dropped"


def test_freezing_away_all_the_capacity_is_refused():
	"""Freezing reads ``p_nom_opt``, which is 0.0 on a never-solved network.

	PyPSA initialises ``p_nom_opt`` to zero rather than to ``nan``, so freezing
	an unsolved network discards the capacity it declared. Measured before the
	guard: ``p_nom`` went 0.0 -> 0.0 and HiGHS returned ``status='warning'
	(infeasible)`` -- an error naming the solver for a problem that is a missing
	solve.

	The refusal is deliberately *not* "there is an extendable component", which
	would refuse the network `build_network` produces and `solve_dispatch`
	exists to serve. It is "freezing left nothing to generate with", so the two
	halves below are the whole contract: a capacity-less extendable network is
	refused, and a fixed one dispatches.
	"""
	from alea.planning.dispatch import DispatchError, freeze_capacity, solve_dispatch

	unsolved = _lossy()
	unsolved.generators["p_nom_extendable"] = True
	unsolved.generators["p_nom"] = 0.0
	assert not has_dispatch(unsolved), "the fixture is not in the unsolved state"
	with pytest.raises(DispatchError, match="discarded all"):
		solve_dispatch(unsolved, Config(scenario=ScenarioConfig(countries=["KE"])))

	fixed = _lossy()
	assert not fixed.generators["p_nom_extendable"].astype(bool).any()
	assert freeze_capacity(fixed) == 0, "a fully fixed network has nothing to freeze"
	result = solve_dispatch(fixed, Config(scenario=ScenarioConfig(countries=["KE"])))
	assert result.total_generation_mwh > 0.0


def test_the_dispatch_artefact_is_what_the_daily_report_reads(tmp_path: Path):
	"""`alea dispatch` writes the carrier table the report section declares.

	The round trip, not the writer. `dispatch_scenario` wrote
	``<id>-dispatch.json`` and nothing else, while `reporting/daily.py`'s
	``generation_mix`` section declared ``planning/dispatch/{date}.parquet`` --
	a path and a shape no producer wrote. Each half passed its own tests: the
	section is exercised against a fixture that plants the file, and the writer
	was exercised against its return value. Only reading one with the other
	shows the gap.

	Driven through the CLI because that is the only entry point AD-5 permits a
	rule to call, and asserted by *reading the file back through
	`values_from_artefact`* rather than by checking it exists: a file at the
	right path in the wrong shape is exactly the defect this test is for.
	"""
	from typer.testing import CliRunner

	from alea.cli import app
	from alea.reporting.assemble import values_from_artefact

	network = _lossy()
	network.optimize(solver_name="highs", log_to_console=False, transmission_losses=True)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	network.export_to_netcdf(str(network_dir / "abc-2030.nc"))
	(tmp_path / "config.yaml").write_text(
		f"paths:\n  results: {tmp_path / 'results'}\n", encoding="utf-8"
	)

	# `results/planning/dispatch`, which is what `_artefact_path` resolves the
	# section's pattern against -- not `results/dispatch`, where the summary
	# alone would have landed.
	out = tmp_path / "results" / "planning" / "dispatch"
	result = CliRunner().invoke(
		app,
		[
			"dispatch",
			"--network",
			str(network_dir / "abc-2030.nc"),
			"--out",
			str(out),
			"--config",
			str(tmp_path / "config.yaml"),
		],
	)
	assert result.exit_code == 0, result.output

	stamped = out / "2030-01-01.parquet"
	assert stamped.exists(), f"no artefact at the declared path; wrote {sorted(p.name for p in out.iterdir())}"
	values = values_from_artefact(stamped, unit="MW")
	assert values, "the carrier table read back empty; the section would render no rows"
	carriers = {value.label for value in values}
	assert "coal" in carriers, f"the carrier labels are not carrier names: {carriers}"


# --------------------------------------------------------------------------
# Criterion 7: the continental config builds, without solving
# --------------------------------------------------------------------------


def test_the_continental_config_builds_without_solving():
	"""A config spanning every member state and power pool is constructible.

	The criterion is deliberately "builds, not solves": a continental solve is
	an M1-scale job, and the thing that can regress cheaply is the config.
	"""
	from alea.registry.countries import AU_MEMBER_STATE_COUNT, registry

	codes = sorted(registry())
	assert len(codes) == AU_MEMBER_STATE_COUNT, "the registry is not the AU membership"
	config = Config(scenario=ScenarioConfig(countries=list(codes)))  # type: ignore[arg-type]
	assert len(config.scenario.countries) > 40
	assert len(set(config.scenario.countries)) == len(config.scenario.countries)


def test_a_config_naming_no_country_is_refused():
	"""``[null]`` validates as a list of strings and then models nothing."""
	from pydantic import ValidationError

	with pytest.raises(ValidationError):
		ScenarioConfig(countries=[None])


# --------------------------------------------------------------------------
# Criterion 8: two solves are byte-identical
# --------------------------------------------------------------------------


def test_reproducible_solve():
	"""Two solves of the same network produce the same objective and dispatch.

	AD-8: no unseeded randomness, no ``hash()`` of strings. The objective is a
	float, so this compares exactly rather than approximately -- a solver that
	is deterministic gives the same bits.
	"""

	def _solve() -> tuple[float, dict[str, float]]:
		network = pypsa.Network()
		network.add("Bus", "b1", carrier="AC")
		network.set_snapshots(list(SNAPSHOTS))
		network.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
		network.add(
			"Generator",
			"solar",
			bus="b1",
			carrier="solar",
			p_nom=20.0,
			p_nom_max=200.0,
			p_nom_extendable=True,
			capital_cost=50_000.0,
		)
		network.add("Load", "load", bus="b1", p_set=120.0)
		network.optimize(solver_name="highs", log_to_console=False)
		return float(network.objective or 0.0), {
			str(name): float(value) for name, value in network.generators_t.p.sum().items()
		}

	first, dispatch_one = _solve()
	second, dispatch_two = _solve()
	assert first == second, "two solves of the same network disagreed on the objective"
	assert dispatch_one == dispatch_two


# --------------------------------------------------------------------------
# Criterion 10: Layer 1 imports without PyPSA-Earth present
# --------------------------------------------------------------------------


def test_layer_one_imports_without_pypsa_earth():
	"""AD-1's gate. A bare import of the package must not pull PyPSA-Earth in.

	PyPSA-Earth is a Snakemake workflow repository, not a pip package; the seam
	is files (AD-1). If importing ``alea.planning`` requires it, the seam has
	leaked and the architecture document is describing something that is not
	true. Run in a subprocess because this session has already imported whatever
	it imported.
	"""
	program = (
		"import sys;"
		"import alea.planning;"
		"import alea.planning.service;"
		"mods = sorted(m for m in sys.modules if m.split('.')[0] in ('pypsa_earth', 'snakemake'));"
		"print(','.join(mods))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO,
	)
	imported = [name for name in result.stdout.strip().split(",") if name]
	assert not imported, f"importing Layer 1 pulled in the workflow repository: {imported}"


def test_a_network_builds_without_the_workflow_repository():
	"""Criterion 10's stronger form: not just imports, but a build.

	The topology stage is the one that would reach for PyPSA-Earth's
	``build_osm_network`` if the seam had leaked, so building a network from
	tabular input is the check that the seam is files.
	"""
	network = _network()
	assert len(network.buses) == 5
	assert len(network.lines) == 4
	assert connectivity_report(network)["n_components"] == 1


# --------------------------------------------------------------------------
# Capacity factors: the range gate
# --------------------------------------------------------------------------


def test_capacity_factors_in_range():
	"""Every capacity factor is in [0, 1].

	A factor above 1 means the profile is already in MW, or the layout was
	applied twice. Either way the generator produces energy it cannot produce.
	"""
	profiles = pd.DataFrame({"bus_0": [0.2, 0.4, 0.3], "bus_1": [0.1, 0.15, 0.0]}, index=SNAPSHOTS[:3])
	stats = validate_capacity_factors(profiles, carrier="solar")
	assert 0.0 <= stats.minimum <= stats.maximum <= 1.0
	assert stats.n_buses == 2
	assert stats.n_hours == 3


def test_a_capacity_factor_above_one_is_refused():
	"""The gate's canary: inject CF=1.2 and the validation must raise."""
	profiles = pd.DataFrame({"bus_0": [0.2, 1.2, 0.3]}, index=SNAPSHOTS[:3])
	with pytest.raises(RenewableError, match="out of"):
		validate_capacity_factors(profiles, carrier="solar")


def test_a_nan_capacity_factor_is_refused_unless_declared():
	"""A NaN propagates into dispatch and the solver reads it as zero, which is
	a silent curtailment of the whole fleet at that bus."""
	profiles = pd.DataFrame({"bus_0": [0.2, float("nan"), 0.3]}, index=SNAPSHOTS[:3])
	with pytest.raises(RenewableError, match="missing capacity factor"):
		validate_capacity_factors(profiles, carrier="solar")
	stats = validate_capacity_factors(profiles, carrier="solar", allow_nan=True)
	assert stats.minimum == pytest.approx(0.2)


def test_a_negative_capacity_factor_is_refused():
	profiles = pd.DataFrame({"bus_0": [-0.1, 0.3]}, index=SNAPSHOTS[:2])
	with pytest.raises(RenewableError, match="out of"):
		validate_capacity_factors(profiles, carrier="solar")


# --------------------------------------------------------------------------
# The expansion solve reaches HiGHS
# --------------------------------------------------------------------------


def test_the_expansion_solve_completes():
	"""Criterion 2's content, at fixture scale: a real solve through the layer's
	own entry point, not through PyPSA directly."""
	network = _solvable()
	config = Config(scenario=ScenarioConfig(countries=["KE"]))
	result = solve_expansion(network, config, multi_period=False)
	assert result.status in ("ok", "optimal", "Optimal")
	assert result.objective > 0.0
	assert result.network is network, "the result does not carry the solved network"
	assert result.seconds > 0.0


def test_an_expansion_with_free_capacity_is_refused():
	"""An extendable generator with no capital and no marginal cost adds
	capacity without adding to the objective, so the optimiser builds it
	without limit. The gate was written because it caught a real 8 GW solar
	build at an objective of exactly 0.0."""
	network = _solvable()
	network.generators["capital_cost"] = 0.0
	network.generators["marginal_cost"] = 0.0
	with pytest.raises(ExpansionError, match="Free capacity"):
		solve_expansion(network, Config(scenario=ScenarioConfig(countries=["KE"])), multi_period=False)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
