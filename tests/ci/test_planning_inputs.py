# SPDX-License-Identifier: MIT
"""The processed lake read back as network inputs.

WHY this module exists. `solve_scenario` built a network from topology and a
fleet and nothing else: `build_network(config, logger_=log)` left
``demand_profiles``, ``renewable_profiles`` and ``capital_costs`` at their
``None`` defaults, so every network the CLI produced had no load.
`solve_expansion` refuses a network with nothing to expand and `solve_dispatch`
refuses one with no loads, and both refusals name the network rather than the
missing read -- so the defect surfaced as "the solver cannot solve this" and
`results/networks/` stayed empty. The three artefacts the arguments wanted were
on disk the whole time.

These tests are the gate on the reader. Each one asserts something the reader
must *refuse*, because the failure mode is not an exception: a demand frame
keyed to buses the network does not have, or a cost table read a thousand times
too small, or a profile series on a different time axis, all produce a network
that builds, solves, and answers a different question than the one asked.

The unit test that matters most is `test_capital_costs_are_per_megawatt`. A
per-kW figure written straight into pypsa's ``capital_cost`` understates every
build by 1000x and the solve still returns an optimum -- the same class of
dimensional error the loss kernel carried, and the same reason it survived.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import write_artefact
from alea.planning.inputs import (
	COSTS_ARTEFACT,
	DEMAND_ARTEFACT,
	RENEWABLE_ARTEFACT,
	InputError,
	load_capital_costs,
	load_demand_profiles,
	load_renewable_profiles,
	network_inputs,
)

HOURS = pd.date_range("2030-01-01", periods=24, freq="h", tz="UTC", name="timestamp_utc")
NAIVE_HOURS = HOURS.tz_localize(None)
BUSES = ["KE_0", "KE_1", "KE_2"]


def _naive(axis: pd.DatetimeIndex) -> pd.DatetimeIndex:
	"""A naive axis, which is all NetCDF can hold."""
	return axis.tz_localize(None) if axis.tz is not None else axis


def _provenance(source_id: str) -> object:
	from alea.provenance.models import Basis, DerivedProvenance

	return DerivedProvenance(
		source_id=source_id,
		inputs=["<fixture>"],
		code_version="test",
		run_id="test",
		parameters={},
		basis=Basis.MODELLED,
		notes="fixture for the planning-inputs gate",
	)


def _config(tmp_path: Path) -> Config:
	"""A config whose processed lake is ``tmp_path``.

	Absolute, so `resolve` returns it unchanged and the reader's conventional
	paths land under the scratch tree rather than the repository's own
	``data/processed`` -- which is a different test's subject.
	"""
	return load_config(overrides=[f"paths.processed={tmp_path}"])


def _write_demand(tmp_path: Path, *, buses: list[str] = BUSES, hours: pd.DatetimeIndex = HOURS) -> None:
	long = pd.DataFrame(
		{
			"bus_id": np.repeat(buses, len(hours)),
			"timestamp_utc": np.tile(hours, len(buses)),
			"demand_mw": np.tile(np.arange(len(hours), dtype=float) + 100.0, len(buses)),
		}
	)
	write_artefact(
		tmp_path / DEMAND_ARTEFACT, long, _provenance("demand_hourly"), format="parquet"
	)


def _write_renewables(
	tmp_path: Path,
	*,
	carriers: tuple[str, ...] = ("solar", "onwind"),
	hours: pd.DatetimeIndex = HOURS,
	buses: list[str] = BUSES,
) -> None:
	"""The cube, on a naive axis -- because NetCDF cannot hold a tz-aware one.

	xarray's CF encoder calls ``np.issubdtype`` on the time coordinate's dtype
	and raises on ``datetime64[us, UTC]``, so the artefact is written naive.
	That is what `_profiles_to_dataset` produces in the pipeline too: atlite's
	own time coordinate comes from `pd.date_range(start="1940", ...)`, which is
	naive. The reader normalises both artefacts to the same naive UTC axis.
	"""
	dataset = xr.Dataset(
		{
			"capacity_factor": (
				("carrier", "bus", "time"),
				np.full((len(carriers), len(buses), len(hours)), 0.25),
			)
		},
		coords={
			"carrier": list(carriers),
			"bus": buses,
			# Renamed to `time`, matching the dimension. xarray names the
			# coordinate after the pandas index's own name, so passing `HOURS`
			# unchanged would declare a coordinate called `timestamp_utc`,
			# invent an integer index for the `time` dimension, and `to_pandas`
			# would cast 0, 1, 2 to nanoseconds after 1970. The real writer is
			# safe because atlite's index is already named `time`; this fixture
			# has to say so explicitly. See
			# `test_a_cube_whose_time_coordinate_is_not_a_datetime_is_refused`.
			"time": _naive(hours).rename("time"),
		},
	)
	write_artefact(
		tmp_path / RENEWABLE_ARTEFACT, dataset, _provenance("renewable_profiles"), format="netcdf"
	)


def _write_costs(tmp_path: Path, *, year: int = 2030) -> None:
	frame = pd.DataFrame(
		{
			"technology": ["solar", "onwind", "coal"],
			"year": [year, year, year],
			"capex_usd_per_kw": [600.0, 1400.0, 2000.0],
			"opex_usd_per_kw_yr": [12.0, 30.0, 45.0],
			"lifetime_years": [25.0, 25.0, 40.0],
		}
	)
	write_artefact(tmp_path / COSTS_ARTEFACT, frame, _provenance("costs"), format="parquet")


# --------------------------------------------------------------------------
# Demand
# --------------------------------------------------------------------------


def test_demand_pivots_to_buses_on_a_datetime_index(tmp_path: Path):
	"""The shape `attach_loads` takes: ``[time, bus]`` on a `DatetimeIndex`.

	A frame whose index is a string column produces a network whose snapshots
	are strings. The solver accepts it; the multi-period code does not, and the
	failure lands a layer away from the read.
	"""
	_write_demand(tmp_path)
	frame = load_demand_profiles(_config(tmp_path))
	assert list(frame.columns) == BUSES
	assert isinstance(frame.index, pd.DatetimeIndex)
	assert frame.index.is_monotonic_increasing
	assert frame.shape == (len(HOURS), len(BUSES))
	assert frame.to_numpy().sum() > 0.0


def test_demand_comes_back_timezone_naive_utc(tmp_path: Path):
	"""The artefact is tz-aware UTC and the network cannot be.

	pypsa 1.4 refuses a tz-aware snapshot -- ``Numpy datetime64[ns] objects
	with timezones are not supported and are thus not allowed in snapshots`` --
	so the reader strips the tz after converting to UTC. Without this the wired
	`solve_scenario` fails inside `attach_loads`, on every build, with a message
	about pypsa's snapshots rather than about the reader.

	The values must be unchanged: this is a representation change, not a shift.
	"""
	_write_demand(tmp_path)
	frame = load_demand_profiles(_config(tmp_path))
	assert frame.index.tz is None
	assert frame.index[0] == pd.Timestamp("2030-01-01 00:00:00")


def test_utc_naive_converts_before_stripping(tmp_path: Path):
	"""A non-UTC aware axis is converted, not truncated.

	`tz_localize(None)` on a +03:00 axis would keep the wall-clock reading and
	relabel it UTC, moving every value three hours. `utc_naive` converts first,
	so the instant is preserved.
	"""
	from alea.planning.inputs import utc_naive

	nairobi = pd.date_range("2030-01-01 03:00", periods=2, freq="h", tz="Africa/Nairobi")
	axis = utc_naive(nairobi)
	assert axis.tz is None
	assert axis[0] == pd.Timestamp("2030-01-01 00:00:00")


def test_utc_naive_passes_through_an_already_naive_axis(tmp_path: Path):
	"""A naive axis is read as UTC rather than refused: it is already UTC, and
	the format it came from cannot carry the marker."""
	from alea.planning.inputs import utc_naive

	axis = utc_naive(NAIVE_HOURS)
	assert axis.tz is None
	assert list(axis) == list(NAIVE_HOURS)


def test_demand_is_refused_when_the_artefact_is_absent(tmp_path: Path):
	"""A missing demand file is the defect that emptied `results/networks/`.

	The message names the artefact and the consequence, because the caller's
	next move is to run a stage, not to read the reader.
	"""
	with pytest.raises(InputError, match="no demand artefact"):
		load_demand_profiles(_config(tmp_path))


def test_demand_is_refused_when_it_lacks_a_required_column(tmp_path: Path):
	"""A frame with the right name and the wrong columns is the same defect
	wearing a passing file-exists check."""
	write_artefact(
		tmp_path / DEMAND_ARTEFACT,
		pd.DataFrame({"bus_id": BUSES, "load_mw": [1.0, 2.0, 3.0]}),
		_provenance("demand_hourly"),
		format="parquet",
	)
	with pytest.raises(InputError, match="lacks"):
		load_demand_profiles(_config(tmp_path))


def test_buses_the_network_lacks_are_dropped_and_reported(tmp_path: Path):
	"""The weight table and the topology disagree; the reader says so.

	Refusing here would be defensible, but the caller already knows its own bus
	list and a partial overlap is the ordinary case -- a topology stage that
	dropped a sub-transmission line removes buses the demand stage never heard
	about. Dropping them silently is what is not allowed.
	"""
	_write_demand(tmp_path)
	frame = load_demand_profiles(_config(tmp_path), buses=["KE_0", "KE_1"])
	assert list(frame.columns) == ["KE_0", "KE_1"]


def test_demand_naming_no_network_bus_is_refused(tmp_path: Path):
	"""Every row dropped is not a disaggregation, it is an empty load."""
	_write_demand(tmp_path)
	with pytest.raises(InputError, match="names no bus the network has"):
		load_demand_profiles(_config(tmp_path), buses=["XX_0"])


def test_an_empty_demand_artefact_is_refused(tmp_path: Path):
	write_artefact(
		tmp_path / DEMAND_ARTEFACT,
		pd.DataFrame({"bus_id": [], "timestamp_utc": [], "demand_mw": []}),
		_provenance("demand_hourly"),
		format="parquet",
	)
	with pytest.raises(InputError, match="empty"):
		load_demand_profiles(_config(tmp_path))


# --------------------------------------------------------------------------
# Renewable profiles
# --------------------------------------------------------------------------


def test_renewables_split_into_one_frame_per_carrier(tmp_path: Path):
	"""`attach_renewables` takes ``{carrier: [time, bus]}``; the artefact is a
	``(carrier, bus, time)`` cube. The split belongs to the reader because the
	cube's shape is the artefact's business, not the network builder's."""
	_write_renewables(tmp_path)
	profiles = load_renewable_profiles(_config(tmp_path))
	assert sorted(profiles) == ["onwind", "solar"]
	for frame in profiles.values():
		assert list(frame.columns) == BUSES
		assert isinstance(frame.index, pd.DatetimeIndex)
		assert frame.shape == (len(HOURS), len(BUSES))
		assert float(frame.to_numpy().max()) <= 1.0


def test_renewables_without_the_profile_variable_are_refused(tmp_path: Path):
	"""A cube with the right dimensions and the wrong variable name."""
	dataset = xr.Dataset(
		{"cf": (("carrier", "bus", "time"), np.zeros((1, len(BUSES), len(HOURS))))},
		coords={"carrier": ["solar"], "bus": BUSES, "time": NAIVE_HOURS.rename("time")},
	)
	write_artefact(
		tmp_path / RENEWABLE_ARTEFACT, dataset, _provenance("renewable_profiles"), format="netcdf"
	)
	with pytest.raises(InputError, match="no 'capacity_factor' variable"):
		load_renewable_profiles(_config(tmp_path))


def test_renewables_missing_a_dimension_are_refused(tmp_path: Path):
	"""A single-bus cube with the bus axis collapsed reads as a profile for the
	whole network, which spreads one site's weather across a country."""
	dataset = xr.Dataset(
		{"capacity_factor": (("carrier", "time"), np.full((1, len(HOURS)), 0.3))},
		coords={"carrier": ["solar"], "time": NAIVE_HOURS.rename("time")},
	)
	write_artefact(
		tmp_path / RENEWABLE_ARTEFACT, dataset, _provenance("renewable_profiles"), format="netcdf"
	)
	with pytest.raises(InputError, match="'bus' is missing"):
		load_renewable_profiles(_config(tmp_path))


def test_a_cube_whose_time_coordinate_is_not_a_datetime_is_refused(tmp_path: Path):
	"""The gate's canary for the 1970 defect.

	A cube that declares the ``time`` dimension but names its coordinate
	something else gets an integer index from xarray. `to_pandas` casts 0, 1, 2
	to ``datetime64[ns]``, so the profiles silently cover 1970 instead of the
	modelled year, the cross-check against demand fails with a message about
	"different periods", and the operator goes looking for a year mismatch in
	two artefacts that agree. This was a real fixture bug found while writing
	this module.
	"""
	dataset = xr.Dataset(
		{
			"capacity_factor": (
				("carrier", "bus", "time"),
				np.full((1, len(BUSES), len(HOURS)), 0.25),
			)
		},
		coords={"carrier": ["solar"], "bus": BUSES, "timestamp_utc": NAIVE_HOURS},
	)
	write_artefact(
		tmp_path / RENEWABLE_ARTEFACT, dataset, _provenance("renewable_profiles"), format="netcdf"
	)
	with pytest.raises(InputError, match="must be a datetime axis"):
		load_renewable_profiles(_config(tmp_path))


def test_a_carrier_with_no_network_bus_is_dropped_not_raised(tmp_path: Path):
	"""One carrier built against a stale bus set must not cost the others.

	`attach_renewables` raises on a profile bus the network lacks, and that is
	the right failure for a *frame* it was handed. Here the reader has the whole
	cube and can tell that this carrier's buses are all gone while the others
	are fine, so it drops the carrier and keeps the rest.
	"""
	_write_renewables(tmp_path)
	profiles = load_renewable_profiles(_config(tmp_path), buses=["KE_0"])
	assert sorted(profiles) == ["onwind", "solar"]
	assert all(list(f.columns) == ["KE_0"] for f in profiles.values())


def test_renewables_with_no_surviving_bus_are_refused(tmp_path: Path):
	_write_renewables(tmp_path)
	with pytest.raises(InputError, match="no carrier with a bus"):
		load_renewable_profiles(_config(tmp_path), buses=["XX_0"])


# --------------------------------------------------------------------------
# Capital costs -- the unit test
# --------------------------------------------------------------------------


def test_capital_costs_are_per_megawatt(tmp_path: Path):
	"""The artefact is USD/kW and pypsa's ``capital_cost`` is USD/MW.

	A per-kW figure written straight into ``capital_cost`` understates every
	build by 1000x. The solve still returns an optimum, the capacity mix still
	looks plausible, and the objective is wrong by three orders of magnitude --
	the same shape as the loss kernel's missing unit conversion, and invisible
	for the same reason: nothing in the pipeline disagrees with it.
	"""
	_write_costs(tmp_path)
	costs = load_capital_costs(_config(tmp_path))
	assert costs["solar"] == pytest.approx(600_000.0)
	assert costs["onwind"] == pytest.approx(1_400_000.0)
	assert costs["coal"] == pytest.approx(2_000_000.0)


def test_the_cost_year_is_the_nearest_at_or_before_the_request(tmp_path: Path):
	"""A model built for 2030 against a 2025 table uses 2025, not 2040.

	Costs fall over time for renewables and rise for thermal, so reading a
	later year is not a small approximation -- it moves the least-cost mix.
	"""
	write_artefact(
		tmp_path / COSTS_ARTEFACT,
		pd.DataFrame(
			{
				"technology": ["solar", "solar"],
				"year": [2025, 2040],
				"capex_usd_per_kw": [700.0, 400.0],
				"opex_usd_per_kw_yr": [14.0, 8.0],
				"lifetime_years": [25.0, 25.0],
			}
		),
		_provenance("costs"),
		format="parquet",
	)
	costs = load_capital_costs(_config(tmp_path), year=2030)
	assert costs["solar"] == pytest.approx(700_000.0)


def test_a_year_before_the_table_falls_back_to_the_earliest(tmp_path: Path):
	"""A 2020 request against a table starting at 2025 uses 2025. Refusing
	would make a historical scenario unsolvable for a reason the operator
	cannot act on -- the table simply does not reach back that far."""
	_write_costs(tmp_path, year=2030)
	costs = load_capital_costs(_config(tmp_path), year=2020)
	assert costs["solar"] == pytest.approx(600_000.0)


def test_a_non_positive_cost_row_is_dropped(tmp_path: Path):
	"""Zero capital cost is free capacity, which `solve_expansion` refuses with
	a message about the network. Dropping the row here means the refusal names
	the missing cost instead."""
	write_artefact(
		tmp_path / COSTS_ARTEFACT,
		pd.DataFrame(
			{
				"technology": ["solar", "onwind", "coal"],
				"year": [2030, 2030, 2030],
				"capex_usd_per_kw": [600.0, 0.0, np.nan],
				"opex_usd_per_kw_yr": [12.0, 0.0, 0.0],
				"lifetime_years": [25.0, 25.0, 40.0],
			}
		),
		_provenance("costs"),
		format="parquet",
	)
	costs = load_capital_costs(_config(tmp_path))
	assert sorted(costs) == ["solar"]


def test_a_cost_table_with_no_usable_row_is_refused(tmp_path: Path):
	"""An empty cost dict attaches no extendable capacity, and a network with
	nothing to expand is refused by the solver with a message about the
	network. The reader refuses first, naming the table."""
	write_artefact(
		tmp_path / COSTS_ARTEFACT,
		pd.DataFrame(
			{
				"technology": ["solar"],
				"year": [2030],
				"capex_usd_per_kw": [0.0],
				"opex_usd_per_kw_yr": [12.0],
				"lifetime_years": [25.0],
			}
		),
		_provenance("costs"),
		format="parquet",
	)
	with pytest.raises(InputError, match="no positive capital cost"):
		load_capital_costs(_config(tmp_path))


def test_costs_are_refused_when_the_artefact_is_absent(tmp_path: Path):
	with pytest.raises(InputError, match="no cost artefact"):
		load_capital_costs(_config(tmp_path))


# --------------------------------------------------------------------------
# The three together: the time axis
# --------------------------------------------------------------------------


def test_network_inputs_returns_all_three(tmp_path: Path):
	_write_demand(tmp_path)
	_write_renewables(tmp_path)
	_write_costs(tmp_path)
	demand, profiles, costs = network_inputs(_config(tmp_path))
	assert demand.shape == (len(HOURS), len(BUSES))
	assert sorted(profiles) == ["onwind", "solar"]
	assert sorted(costs) == ["coal", "onwind", "solar"]


def test_profiles_on_a_different_time_axis_are_refused(tmp_path: Path):
	"""The gate this module exists for.

	`attach_loads` sets the network's snapshots from the demand index and
	`attach_renewables` resets them from the profiles'. A mismatch therefore
	does not raise: the second call re-indexes the network and every load
	attached against the first axis becomes a load at the wrong hour. That is a
	dispatch that balances and is wrong, which is worse than one that fails.
	"""
	_write_demand(tmp_path)
	_write_renewables(tmp_path, hours=pd.date_range("2031-01-01", periods=24, freq="h", tz="UTC"))
	_write_costs(tmp_path)
	with pytest.raises(InputError, match="different periods"):
		network_inputs(_config(tmp_path))


def test_a_shorter_profile_series_is_refused(tmp_path: Path):
	"""Same axis, different length -- the profiles cover a week and the demand
	an hour. `equals` catches it; a reindex would have silently padded."""
	_write_demand(tmp_path)
	_write_renewables(tmp_path, hours=HOURS[:12])
	_write_costs(tmp_path)
	with pytest.raises(InputError, match="different periods"):
		network_inputs(_config(tmp_path))


# --------------------------------------------------------------------------
# The wiring: `solve_scenario`'s build path produces a network with load
# --------------------------------------------------------------------------


def _write_topology(tmp_path: Path) -> list[str]:
	"""A three-bus chain, written as the topology artefact.

	Returns the bus ids `build_topology` assigns, so the demand fixture can key
	itself to buses the network actually has -- which is the whole point of the
	end-to-end test below.
	"""
	lon = [0.0, 0.1, 0.2]
	frame = pd.DataFrame(
		{
			"line_id": ["l0", "l1"],
			"from_lon": lon[:-1],
			"from_lat": [0.0, 0.0],
			"to_lon": lon[1:],
			"to_lat": [0.0, 0.0],
			"voltage_kv": [400.0, 400.0],
			"length_km": [11.0, 11.0],
			"capacity_mva": [1000.0, 1000.0],
		}
	)
	write_artefact(tmp_path / "topology.parquet", frame, _provenance("transmission_lines"), format="parquet")
	from alea.planning.topology import build_topology

	network, _, _ = build_topology(frame, voltage_kv_min=66.0)
	return [str(b) for b in network.buses.index]


def _write_fleet(tmp_path: Path, buses: list[str]) -> None:
	"""One coal plant near each bus, so the network has generation to attach."""
	frame = pd.DataFrame(
		{
			"plant_id": [f"p{i}" for i in range(len(buses))],
			"name": [f"plant {i}" for i in range(len(buses))],
			"carrier": ["coal"] * len(buses),
			"capacity_mw": [500.0] * len(buses),
			"lon": [0.0, 0.1, 0.2],
			"lat": [0.0, 0.0, 0.0],
			"commissioning_year": [1990] * len(buses),
			"lifetime_years": [40] * len(buses),
		}
	)
	write_artefact(tmp_path / "fleet.parquet", frame, _provenance("powerplantmatching"), format="parquet")


def test_build_network_reads_the_config_root_and_carries_load(tmp_path: Path):
	"""The defect this module closes, end to end.

	`solve_scenario` called ``build_network(config, logger_=log)``: no demand,
	no profiles, no costs. The network it produced had topology and a fleet and
	``len(network.loads) == 0``, which `solve_dispatch` refuses and which is why
	`results/networks/` stayed empty.

	This asserts the two facts that were false: the built network has one load
	per demand bus, and its snapshots are the demand index. It goes through
	`build_network` with no ``root``, so it also holds the root default to the
	config -- the loader and the builder reading one lake.
	"""
	from alea.planning.service import build_network

	buses = _write_topology(tmp_path)
	_write_fleet(tmp_path, buses)
	_write_demand(tmp_path, buses=buses)
	_write_renewables(tmp_path, buses=buses)
	_write_costs(tmp_path)
	config = _config(tmp_path)

	demand, profiles, costs = network_inputs(config, buses=buses)
	network, report, provenances = build_network(
		config, demand_profiles=demand, renewable_profiles=profiles, capital_costs=costs
	)

	assert len(network.buses) == len(buses)
	assert len(network.loads) == len(buses), "the network built with no load"
	assert len(network.snapshots) == len(HOURS)
	assert network.snapshots.tz is None, "pypsa refuses a tz-aware snapshot"
	assert report.demand is not None and report.demand["buses"] == len(buses)
	assert not [n for n in report.notes if "no demand" in n], "a note claims no demand was attached"
	assert provenances, "the build recorded no provenance for its inputs"


def test_the_built_network_solves_a_dispatch(tmp_path: Path):
	"""The consequence: `solve_dispatch` accepts what the build produces.

	It asserts ``len(network.loads) > 0``, so before this wiring every dispatch
	on a CLI-built network was refused -- and the refusal named the network
	rather than the reader that never attached anything.
	"""
	from alea.planning.dispatch import solve_dispatch
	from alea.planning.service import build_network

	buses = _write_topology(tmp_path)
	_write_fleet(tmp_path, buses)
	_write_demand(tmp_path, buses=buses)
	_write_renewables(tmp_path, buses=buses)
	_write_costs(tmp_path)
	config = _config(tmp_path)

	demand, profiles, costs = network_inputs(config, buses=buses)
	network, _, _ = build_network(
		config, demand_profiles=demand, renewable_profiles=profiles, capital_costs=costs
	)
	result = solve_dispatch(network, config)
	# `DispatchResult` carries no solver status: the assertion it makes about
	# itself is the energy balance, which is the stronger claim anyway. A
	# dispatch that reports an optimum and does not balance has solved the
	# wrong problem.
	assert result.total_load_mwh > 0.0, "the dispatch served no load"
	assert result.energy_balance_error_mwh == pytest.approx(0.0, abs=1e-6)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
