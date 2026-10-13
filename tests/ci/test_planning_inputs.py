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

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact, write_artefact
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
from tests.ci.canaries import REPO, planted

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


def _config(tmp_path: Path, *, time_aggregation: int = 1) -> Config:
	"""A config whose processed lake is ``tmp_path``.

	Absolute, so `resolve` returns it unchanged and the reader's conventional
	paths land under the scratch tree rather than the repository's own
	``data/processed`` -- which is a different test's subject.
	"""
	overrides = [f"paths.processed={tmp_path}"]
	if time_aggregation > 1:
		overrides.append(f"solve.time_aggregation={time_aggregation}")
	return load_config(overrides=overrides)


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


# --------------------------------------------------------------------------
# The stage that disaggregates: what it refuses, and what it refuses to name
# --------------------------------------------------------------------------


def _write_national(tmp_path: Path, *, twh: float = 12.0, year: int = 2030) -> None:
	"""A `demand_national` artefact, at the path the stage reads by convention."""
	write_artefact(
		tmp_path / "demand_national.parquet",
		pd.DataFrame(
			{"country_iso": ["KE"], "year": [year], "demand_twh": [twh]}
		),
		_provenance("demand_national"),
		format="parquet",
	)


def test_demand_hourly_refuses_without_a_weight_table(tmp_path: Path):
	"""The refusal that replaced a fallback naming a source that does not exist.

	`build_demand_hourly` used to fall back to
	``_require_raw(config, context, "worldpop")`` when no weight table was
	passed. ``worldpop`` is in no register, so the call raised ``unknown
	source: worldpop; registered: ...`` -- a message about the source register
	for an operator whose actual problem is that they did not pass a table. The
	fallback read as a configured alternative and was an error path.

	The assertion is on the *message*, not just on the exception type: the
	operator's next move is to pass ``--set bus_weights=``, and a refusal that
	names the register instead sends them to the wrong file.
	"""
	from alea.io.pipeline import BuildContext
	from alea.io.stages import build_demand_hourly

	_write_national(tmp_path)
	out = tmp_path / "demand_hourly.parquet"
	context = BuildContext(out=out, inputs=["<fixture>"], parameters={})
	with pytest.raises(ArtefactError, match="no bus weight table"):
		build_demand_hourly(_config(tmp_path), out, context)


def test_demand_hourly_names_the_source_register_only_when_it_is_the_problem():
	"""The canary for the gate above: the old call raised a *different* error.

	Pinned so the distinction is on the record rather than in a commit message.
	`_require_raw` with an unregistered id raises ``KeyError``, not
	``ArtefactError`` -- so a test asserting only "it raises" would have passed
	against the broken branch. The gate asserts the message, which is the part
	that tells the operator what to do.
	"""
	from alea.io.pipeline import BuildContext
	from alea.io.stages import _require_raw

	context = BuildContext(out=Path("/tmp/x"), inputs=[], parameters={})
	with pytest.raises(KeyError, match="unknown source"):
		_require_raw(_config(Path("/tmp")), context, "worldpop")


# --------------------------------------------------------------------------
# The seam: the stage's own output, read by its own consumer
# --------------------------------------------------------------------------


def _write_fleet_export(tmp_path: Path, *, dated: bool = True) -> Path:
	"""A powerplantmatching export at the path the stage resolves by convention.

	Deliberately not a `fleet.parquet`: writing the *stage's* output by hand is
	what hid the break this section gates. The stage is the producer, so the
	gate runs it.
	"""
	raw = tmp_path / "raw" / "powerplantmatching" / "manual"
	raw.mkdir(parents=True, exist_ok=True)
	columns: dict[str, object] = {
		"plant_id": ["p0", "p1"],
		"name": ["plant 0", "plant 1"],
		"country_iso": ["KE", "KE"],
		"lat": [0.0, 0.0],
		"lon": [0.0, 0.1],
		"capacity_mw": [500.0, 500.0],
		"carrier": ["coal", "coal"],
	}
	if dated:
		# The export's own spellings, which are not the schema's: `Commissioned`
		# and `Lifetime`. The stage renames them, and that rename is the seam.
		columns["Commissioned"] = [1990, 1990]
		columns["Lifetime"] = [40, 40]
	pd.DataFrame(columns).to_parquet(raw / "powerplants.parquet")
	return raw.parent.parent


def _stage_config(tmp_path: Path) -> Config:
	"""A config whose raw and processed lakes are both under ``tmp_path``."""
	processed = tmp_path / "processed"
	processed.mkdir(parents=True, exist_ok=True)
	return load_config(
		overrides=[f"paths.raw={tmp_path / 'raw'}", f"paths.processed={processed}"]
	)


def test_the_fleet_stage_writes_what_its_consumer_reads(tmp_path: Path):
	"""The seam, end to end: `build_fleet` -> `build_network`.

	The stage wrote ``commission_year`` and no lifetime column; `FLEET.check`,
	which `attach_generators` runs as its first statement, requires
	``commissioning_year`` and ``lifetime_years``. So every `build_network` from
	a staged fleet raised ``SchemaError: fleet: missing required column(s)
	commissioning_year, lifetime_years`` -- the pipeline could not build a
	network from its own output at all.

	Nothing in the suite noticed, and the reason is the fixture shape this test
	exists to replace: `_write_fleet` above writes the *consumer's* spelling by
	hand, so the gate tested `attach_generators` against a frame the producer
	never writes. A gate over a hand-written input cannot see a producer that
	disagrees with it. This one runs the producer.
	"""
	from alea.io.pipeline import build_stage
	from alea.planning.service import build_network

	_write_fleet_export(tmp_path, dated=True)
	config = _stage_config(tmp_path)
	processed = tmp_path / "processed"

	# topology, the other artefact `build_network` reads.
	lon = [0.0, 0.1]
	write_artefact(
		processed / "topology.parquet",
		pd.DataFrame(
			{
				"line_id": ["l0"],
				"from_lon": lon[:-1],
				"from_lat": [0.0],
				"to_lon": lon[1:],
				"to_lat": [0.0],
				"voltage_kv": [400.0],
				"length_km": [11.0],
				"capacity_mva": [1000.0],
			}
		),
		_provenance("transmission_lines"),
		format="parquet",
	)

	build_stage("fleet", config, processed / "fleet.parquet")
	frame, _ = read_artefact(processed / "fleet.parquet")
	# The export's `Commissioned`/`Lifetime` reached the artefact under the
	# schema's names, which is the rename this test is about.
	assert frame["commissioning_year"].tolist() == [1990, 1990]
	assert frame["lifetime_years"].tolist() == [40, 40]

	network, report, _ = build_network(config)
	assert report.fleet["n_attached"] == 2, "the staged fleet did not attach"
	assert network.generators["build_year"].tolist() == [1990, 1990]
	assert network.generators["lifetime"].tolist() == [40.0, 40.0]


def test_an_undated_plant_is_commissioned_at_the_base_year(tmp_path: Path):
	"""The default, and why it is the base year rather than zero.

	An export that omits a vintage must still produce an ``int`` column -- the
	schema says ``int`` and `attach_generators` reads it with ``int(row[...])``,
	which raises on a NaN. Zero is the obvious sentinel and it is the wrong one:
	under `set_multi_period` a generator with ``build_year=0`` is retired decades
	before the first horizon, so the whole fleet would silently vanish from the
	expansion. The default is the scenario's own base year, and the count of
	rows that took it is recorded.
	"""
	from alea.io.artefacts import read_provenance
	from alea.io.pipeline import build_stage

	_write_fleet_export(tmp_path, dated=False)
	config = _stage_config(tmp_path)
	out = tmp_path / "processed" / "fleet.parquet"

	build_stage("fleet", config, out)
	frame, _ = read_artefact(out)
	assert frame["commissioning_year"].tolist() == [config.scenario.base_year] * 2
	assert frame["commissioning_year"].dtype.kind == "i", "the schema says int"
	assert frame["lifetime_years"].tolist() == [30, 30]

	provenance = read_provenance(out)
	parameters = provenance.parameters
	assert parameters["n_plants_undated"] == 2, (
		"a defaulted vintage is a convention, and an unrecorded one is a "
		"retirement date nobody can defend"
	)
	assert parameters["commissioning_year_default"] == config.scenario.base_year


#: Builds the staged fleet in a **fresh interpreter** and reports what happened.
#:
#: A subprocess rather than an in-process call because `build_fleet` is already
#: bound in this process by the time the canary mutates its source: `planted`
#: rewrites the file and purges the `.pyc`, but `sys.modules` still holds the
#: module object the mutation never reached, so an in-process canary would
#: exercise the *correct* code and pass for the wrong reason.
_FLEET_PROGRAM = """
import sys
from pathlib import Path

from alea.config.loader import load_config
from alea.io.pipeline import build_stage

root = Path(sys.argv[1])
config = load_config(
    overrides=[f"paths.raw={root / 'raw'}", f"paths.processed={root / 'processed'}"]
)
try:
    build_stage("fleet", config, root / "processed" / "fleet-canary.parquet", force=True)
except Exception as exc:
    print(f"refused:{type(exc).__name__}:{exc}")
else:
    print("accepted")
"""


def _fleet_outcome(root: Path) -> str:
	"""``"accepted"`` or ``"refused:..."``, from a subprocess against the tree.

	The *last* line, not the whole of stdout: `build_stage` logs its summary to
	stdout before it returns or raises, so the marker is never the first line and
	a `startswith` over the whole capture would fail on a stage that worked.
	"""
	env = {**os.environ, "PYTHONPATH": str(REPO)}
	completed = subprocess.run(
		[sys.executable, "-c", _FLEET_PROGRAM, str(root)],
		capture_output=True,
		text=True,
		check=False,
		env=env,
		cwd=str(REPO),
	)
	assert completed.returncode == 0, completed.stderr
	lines = [line for line in completed.stdout.splitlines() if line.strip()]
	assert lines, f"the subprocess printed nothing; stderr: {completed.stderr}"
	return lines[-1].strip()


def test_the_stage_refuses_its_own_output_when_the_rename_is_lost(tmp_path: Path):
	"""The canary for the two gates above.

	Plants the exact defect that shipped -- the stage writing ``commission_year``
	while its consumer's schema requires ``commissioning_year`` -- and asserts
	the producer-side `FLEET.check` refuses it. The message is asserted, not just
	the exception type, because the message is what names the schema: without it
	"something raised" would pass against a stage failing for an unrelated
	reason.

	Blinding the check as well would need a second simultaneous mutation in the
	same file, and two nested `planted` calls deadlock -- `fcntl.flock` is held
	per open file description, so the same process blocks against itself. The
	message assertion pins `FLEET.check` as the refuser instead, which is what
	the blinding would have shown.
	"""
	stages = REPO / "src" / "alea" / "io" / "stages.py"
	shipped = '\tframe["commissioning_year"] = commissioned.fillna(default_year).astype(int)'
	lost = '\tframe["commission_year"] = commissioned.fillna(default_year).astype(int)'
	assert shipped in stages.read_text(), "canary target not found"

	_write_fleet_export(tmp_path, dated=True)
	_stage_config(tmp_path)

	assert _fleet_outcome(tmp_path).startswith("accepted"), (
		"the shipped stage refused its own output, so the canary below would "
		"pass for a reason unrelated to the rename"
	)

	with planted(stages, shipped, lost):
		outcome = _fleet_outcome(tmp_path)
		assert outcome.startswith("refused"), (
			"the stage wrote a column its consumer's schema does not require and "
			"nothing refused it; the producer-side check is not the gate it "
			"claims to be"
		)
		assert "missing required column" in outcome, (
			f"the refusal did not come from the schema check: {outcome}"
		)

	assert _fleet_outcome(tmp_path).startswith("accepted"), "the restore did not put it back"


# --------------------------------------------------------------------------
# The hourly series covers the horizon it claims to
# --------------------------------------------------------------------------


def _write_hourly(tmp_path: Path, *, year: int) -> tuple[Path, pd.DataFrame]:
	"""Build ``demand_hourly`` for ``year`` and return the artefact and its frame."""
	from alea.io.pipeline import BuildContext
	from alea.io.stages import build_demand_hourly

	processed = tmp_path / "processed"
	processed.mkdir(parents=True, exist_ok=True)
	write_artefact(
		processed / "demand_national.parquet",
		pd.DataFrame({"country_iso": ["KE"], "year": [year], "demand_twh": [12.0]}),
		_provenance("demand_national"),
		format="parquet",
	)
	weights = tmp_path / "weights.csv"
	pd.DataFrame(
		{"bus_id": ["KE_0", "KE_1"], "population": [0.6, 0.4], "gdp": [0.7, 0.3]}
	).to_csv(weights, index=False)

	out = processed / "demand_hourly.parquet"
	config = load_config(
		overrides=[f"paths.raw={tmp_path / 'raw'}", f"paths.processed={processed}"]
	)
	context = BuildContext(
		out=out, inputs=["<fixture>"], parameters={"bus_weights": str(weights), "year": year}
	)
	build_demand_hourly(config, out, context)
	frame, _ = read_artefact(out)
	return out, frame


@pytest.mark.parametrize("year", [2030, 2040, 2050, 2060])
def test_demand_hourly_covers_horizon(tmp_path: Path, year: int):
	"""`02-data-pipeline.md` §4.2's ``test_demand_hourly_covers_horizon``.

	Every hour of the horizon year carries load, and no hour outside it does.
	The gate the plan names, and the one that would have caught a shipped
	defect: the series was a fixed ``HOURS_PER_YEAR`` (8760) hours from the
	first of January, so 2040 and 2060 -- leap years, and two of the four
	default horizons -- ended at 30 December 23:00 and carried no load for
	their last 24 hours. A network built on that series prices 8784 hours of
	system with 8760 hours of demand, and nothing about the answer looks wrong.

	Both directions are asserted. A series that only ever grows would pass a
	"no gaps" check while covering a year it was not asked for.
	"""
	_, frame = _write_hourly(tmp_path, year=year)
	covered = pd.DatetimeIndex(pd.to_datetime(frame["timestamp_utc"]).unique()).sort_values()
	expected = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h", tz="UTC")

	missing = expected.difference(covered)
	assert len(missing) == 0, (
		f"{len(missing)} hour(s) of {year} carry no demand, e.g. {list(missing[:3])}; "
		f"the series is a fixed hour count rather than the calendar year"
	)
	assert len(covered) == len(expected), (
		f"the series holds {len(covered)} hours for a year of {len(expected)}"
	)
	assert covered.min() == expected[0] and covered.max() == expected[-1], (
		f"the series spans {covered.min()} to {covered.max()}, not the year"
	)
	# Every bus, every hour: a gap on one bus alone is the same defect with a
	# smaller footprint, and `pivot_table` in `load_demand_profiles` fills it
	# with a NaN the solver reads as a zero load.
	per_bus = frame.groupby("bus_id")["timestamp_utc"].nunique()
	assert set(per_bus) == {len(expected)}, f"a bus does not cover the year: {per_bus.to_dict()}"
	assert not frame["demand_mw"].isna().any(), "the demand series has a NaN"


def test_a_leap_year_is_where_the_hour_count_gate_can_fail(tmp_path: Path):
	"""The canary for the gate above: it must be able to fail at all.

	``test_demand_hourly_covers_horizon`` passes for every non-leap horizon
	whether or not the stage uses a fixed hour count, so a canary that only
	exercised 2030 would prove nothing. This plants the shipped defect -- the
	fixed ``HOURS_PER_YEAR`` index -- and runs *the gate itself* in a fresh
	interpreter, asserting it exits non-zero. A subprocess because the mutation
	cannot reach an already-imported module, and the gate itself rather than a
	re-measurement of the hour count because a proxy that re-implements the
	check is a canary of the proxy.
	"""
	stages = REPO / "src" / "alea" / "io" / "stages.py"
	shipped = (
		'\t\tf"{year}-01-01 00:00", f"{year}-12-31 23:00", freq="h", tz="UTC", '
		'name="timestamp_utc"'
	)
	fixed = '\t\tf"{year}-01-01 00:00", periods=HOURS_PER_YEAR, freq="h", tz="UTC", name="timestamp_utc"'
	assert shipped in stages.read_text(), "canary target not found: the index is not the calendar year"

	env = {**os.environ, "PYTHONPATH": str(REPO)}
	gate = [
		sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
		"tests/ci/test_planning_inputs.py::test_demand_hourly_covers_horizon",
	]
	clean = subprocess.run(gate, capture_output=True, text=True, check=False, env=env, cwd=str(REPO))
	assert clean.returncode == 0, (
		f"the gate does not pass on the shipped tree, so the canary below would "
		f"prove nothing:\n{clean.stdout[-2000:]}"
	)

	with planted(stages, shipped, fixed):
		mutated = subprocess.run(
			gate, capture_output=True, text=True, check=False, env=env, cwd=str(REPO)
		)
	assert mutated.returncode != 0, (
		"the gate passed against a fixed 8760-hour index, so it cannot tell a "
		"covered leap year from a short one"
	)
	assert "carry no demand" in mutated.stdout, (
		f"the gate failed for a reason other than the missing hours:\n{mutated.stdout[-2000:]}"
	)


# --------------------------------------------------------------------------
# The aggregation the config selects is the aggregation that runs
# --------------------------------------------------------------------------


def _aggregation_fixture(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, time_aggregation: int = 6
) -> Config:
	"""A lake, a config selecting ``time_aggregation``, and its AD-9 measurement.

	The validation is measured here the way the CLI measures it -- both
	networks solved, then compared -- and written where `solve_scenario` looks
	for it. That path is cwd-relative, so the fixture also moves the working
	directory into the scratch tree; without that the gate would read the
	repository's own ``results/aggregation`` and the test would pass or fail on
	whatever a previous run left there.

	Returns the config. The caller drives the solve; this only arranges the
	inputs, so that a test asserting on the solve cannot accidentally be
	asserting on the arrangement.
	"""
	from alea.planning.aggregation import (
		aggregate_network,
		validate_aggregation_artefact,
		write_validation,
	)
	from alea.planning.service import build_network

	buses = _write_topology(tmp_path)
	_write_fleet(tmp_path, buses)
	_write_demand(tmp_path, buses=buses)
	_write_renewables(tmp_path, buses=buses)
	_write_costs(tmp_path)
	config = _config(tmp_path, time_aggregation=time_aggregation)

	demand, profiles, costs = network_inputs(config, buses=buses)
	full, _, _ = build_network(
		config, demand_profiles=demand, renewable_profiles=profiles, capital_costs=costs
	)
	# The fixture year is 24 hours, so the reduction is coarse. Six periods of
	# three hours leaves a six-hour tail, which exercises the general case --
	# where the kernel's selection is a heuristic rather than the exact-division
	# identity -- rather than a case that cannot fail.
	n_periods, period_length = time_aggregation, _REDUCED_PERIOD_HOURS
	assert n_periods * period_length < len(full.snapshots), "the fixture is too short to reduce"

	reduced = aggregate_network(full, n_periods=n_periods, period_length=period_length)
	reduced.optimize(solver_name="highs", log_to_console=False)
	full.optimize(solver_name="highs", log_to_console=False)
	validation = validate_aggregation_artefact(
		full, reduced, n_periods=n_periods, period_length=period_length
	)
	assert validation.passes, (
		f"the fixture does not clear AD-9, so the solve below is refused by the "
		f"gate rather than reaching the reduction: cost "
		f"{validation.cost_error_pct:.3f}%, mix "
		f"{validation.capacity_mix_l1_error_pct:.3f}%"
	)

	monkeypatch.chdir(tmp_path)
	write_validation(validation, root="results/aggregation", inputs=["sha256:network:fixture"])
	return config


_REDUCED_PERIOD_HOURS = 3
"""Timesteps per representative period, for the 24-hour fixture year."""


def _timesteps_per_period(network) -> dict[int, int]:
	"""How many snapshots each investment period kept."""
	periods = network.snapshots.get_level_values(0)
	return {int(p): int((periods == p).sum()) for p in dict.fromkeys(periods)}


def test_a_config_selecting_time_aggregation_reaches_a_reduced_network(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	"""AD-9's gate guards a fast path, so the fast path has to exist.

	The defect this closes: `solve_scenario` called
	``require_aggregation_validation`` when ``time_aggregation > 1`` and then
	solved the full-resolution network anyway. The gate was real, the config
	knob was real, the measurement was real, and the reduction was never
	applied -- so a run configured for representative periods spent the full
	8760-hour solve and reported it as aggregated. Every test passed, because
	every test checked the gate rather than the effect.

	WHY this drives `solve_scenario` rather than calling `aggregate_network`:
	the first version of this test called the aggregation itself and asserted on
	its own call's result, so replacing the solve path's aggregation with
	``pass`` left it green. A test that reimplements the step it is testing
	cannot fail when the step is removed -- it only proves the function it just
	called works, which was never in doubt.

	The assertion is the effect: the network the solver receives keeps
	``time_aggregation * period_length`` timesteps per investment period instead
	of the full year, and their weights still sum to the year's hours. A build
	that skips the aggregation fails the first, and one that reduces by
	averaging periods rather than selecting them fails the second.
	"""
	from alea.planning.service import solve_scenario

	config = _aggregation_fixture(tmp_path, monkeypatch)
	result = solve_scenario(config, out=tmp_path / "networks", publish=False)
	solved = result.network

	assert isinstance(solved.snapshots, pd.MultiIndex), (
		"the default config is multi-period, so the solved network's snapshots "
		"carry a period level"
	)
	kept = _timesteps_per_period(solved)
	expected = config.solve.time_aggregation * _REDUCED_PERIOD_HOURS
	assert set(kept.values()) == {expected}, (
		f"every investment period should keep {expected} timesteps under "
		f"time_aggregation={config.solve.time_aggregation}; the solve kept {kept}"
	)

	# AD-9's invariant: the reduction selects periods, it does not shorten the
	# year. A weighting that sums to fewer hours than the year has understates
	# every annual total, systematically, across a whole study.
	year_hours = float(len(HOURS))
	for period in kept:
		weight = float(solved.snapshot_weightings["generators"].loc[period].sum())
		assert weight == pytest.approx(year_hours), (
			f"investment period {period} carries {weight} hours of weight, not "
			f"the year's {year_hours}; the reduction lost the annual totals"
		)


def test_multi_period_repeats_the_network_series_rather_than_inventing_one(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	"""A planning model spans the horizons; every one of them must carry the data.

	The defect this closes: `set_multi_period` built its snapshots as
	``period_length`` fresh hours from each horizon's first of January, then
	``set_snapshots`` reindexed every time series *by label*. The demand frame
	covered 2030 only, so the other three periods aligned to nothing and pypsa
	filled them with the component's static default -- zero load, and a capacity
	factor of 1.0 where the profile said 0.25. Three of the four default
	horizons modelled a continent with no demand and perpetual perfect weather.
	Nothing raised; the objective was simply wrong.

	PyPSA's own rule is the fix, and it is the one this asserts: a multi-period
	network repeats the snapshots it already has. The check is on the *data*
	rather than the index, because the index was always well-formed -- it was
	the series behind it that emptied.
	"""
	from alea.planning.service import solve_scenario

	config = _aggregation_fixture(tmp_path, monkeypatch)
	result = solve_scenario(config, out=tmp_path / "networks", publish=False)
	solved = result.network
	periods = [int(p) for p in solved.investment_periods]
	assert len(periods) == len(config.scenario.planning_horizons), (
		f"the solve produced {periods} from horizons "
		f"{config.scenario.planning_horizons}"
	)

	demand = solved.loads_t.p_set.iloc[:, 0]
	capacity_factor = solved.generators_t.p_max_pu.iloc[:, 0]
	for period in periods:
		load = float(demand.loc[period].sum())
		assert load > 0.0, (
			f"investment period {period} carries no load at all; the series was "
			f"reindexed onto labels it does not have and pypsa filled it with the "
			f"static default"
		)
		mean_cf = float(capacity_factor.loc[period].mean())
		assert mean_cf == pytest.approx(float(capacity_factor.loc[periods[0]].mean())), (
			f"investment period {period} has a mean capacity factor of {mean_cf}, "
			f"not the profile's own; a 1.0 here is a period with no weather"
		)

