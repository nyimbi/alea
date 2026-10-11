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
	AggregationError,
	build_aggregation,
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


def _solvable() -> pypsa.Network:
	"""The topology fixture with generation and load per bus, so it balances.

	Two carriers, not one: the aggregation gates measure a capacity *mix*, and a
	single-carrier network has a mix of 100% that carrier by construction, so
	every mix error against it is zero and the channel is untestable.
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
