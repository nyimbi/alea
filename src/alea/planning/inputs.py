# SPDX-License-Identifier: MIT
"""The processed lake as network inputs.

`build_network` takes demand profiles, renewable profiles and capital costs as
arguments. Nothing ever passed them: `solve_scenario` called
``build_network(config, logger_=log)`` and every argument defaulted to ``None``,
so every network the CLI built carried topology and a fleet and **no load**.
`solve_expansion` refuses a network with nothing to expand and `solve_dispatch`
refuses one with no loads, so the load-free network was unsolvable by
construction -- and `results/networks/` was empty for that reason, not because
the solver was missing.

The three artefacts the arguments wanted were on disk the whole time.
`demand_hourly`, `renewable_profiles` and `costs` are registered stages with
rules in the workflow; what was absent was the step that reads them back. This
module is that step, and it is deliberately the only place that knows the
conventional path of each: a second reader would be a second convention.

**Why this is not the stage layer.** These functions are not `@stage`
builders. A stage writes a versioned artefact; these read three and hand them to
a network builder, and their output is an in-memory `pypsa.Network`, not a file.
AD-4 is satisfied by the artefacts they read, each of which already carries its
own provenance.

**Units, stated once.** `demand_hourly` is MW per bus per hour, wide here as
``[time, bus]``. `renewable_profiles` is a capacity factor in [0, 1], per
carrier. `costs` is USD per kW in the artefact and USD per MW here, because
pypsa's `capital_cost` is per MW and a per-kW figure written straight into it
understates every build by a factor of 1000 -- the same class of unit error the
loss kernel carried.

**Time, stated once.** Both frames come back on a timezone-naive UTC axis, via
`utc_naive`. The artefacts are UTC-aware per `02-data-pipeline.md` §2.2 and the
network cannot be: pypsa refuses a tz-aware snapshot, and xarray cannot write
one to NetCDF at all. The conversion is here because this is the only module
that reads both artefacts, so it is the only place that can do it once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import artefact_exists, read_artefact
from alea.logging import get_logger

logger = get_logger(__name__)

#: The conventional path of each input under ``paths.processed``. Named here
#: rather than at each call site so the demand builder and the demand reader
#: cannot come to disagree about where the file is.
DEMAND_ARTEFACT = "demand_hourly.parquet"
RENEWABLE_ARTEFACT = "renewable_profiles.nc"
COSTS_ARTEFACT = "costs.parquet"

#: The capacity-factor variable `_profiles_to_dataset` names.
PROFILE_VARIABLE = "capacity_factor"

#: The name both frames' index carries. The pivot names it after the demand
#: column and the NetCDF cube names it after its `time` dimension, and
#: `DatetimeIndex.equals` compares names as well as values -- so without this
#: the cross-check below refuses two axes that hold the same hours.
SNAPSHOT_INDEX_NAME = "timestamp_utc"


class InputError(RuntimeError):
	"""A processed artefact the network needs is absent or malformed."""


def _processed(config: Config, root: str | Path | None) -> Path:
	"""The processed lake root, from the config unless one is given."""
	return Path(root) if root is not None else resolve(config.paths.processed)


def _as_float(value: Any) -> float:
	"""A cost cell as a float, or NaN if it is not one.

	NaN rather than an exception because a missing cost is a row the caller
	should drop, not a reason to refuse the whole table -- but a cost that is
	present and unreadable is a different thing from an absent one, and it is
	NaN here so the caller's filter treats both the same way it treats an
	explicitly blank cell.
	"""
	try:
		return float(value)
	except (TypeError, ValueError):
		return float("nan")


def utc_naive(index: Any) -> pd.DatetimeIndex:
	"""A time axis as timezone-naive UTC, which is what a network can hold.

	`02-data-pipeline.md` §2.2 requires every artefact timestamp to be UTC and
	timezone-aware, and the demand artefact is. The network cannot be: pypsa
	refuses a tz-aware snapshot outright --

	    ValueError: Numpy datetime64[ns] objects with timezones are not
	    supported and are thus not allowed in snapshots

	-- so the conversion has to happen somewhere, and this is the only place
	that reads both artefacts and hands them to a builder. The alternative,
	converting at each `set_snapshots` call, puts the same three lines in three
	modules and lets one of them be forgotten.

	The NetCDF artefact is naive for a harder reason: xarray's CF encoder calls
	``np.issubdtype(dtype, np.datetime64)`` on a tz-aware coordinate and raises
	``TypeError: Cannot interpret 'datetime64[us, UTC]' as a data type``. The
	format cannot store one, so a tz-aware time axis in a NetCDF artefact is
	not a convention that was violated, it is one that cannot be met.

	Naive input is read as UTC rather than refused. It is already UTC -- that
	is what the format forces -- and a reader that demanded the tz on a value
	that cannot carry it would refuse every profile artefact in the repository.
	"""
	assert index is not None, "index must not be None"
	axis = pd.DatetimeIndex(index)
	if axis.tz is not None:
		axis = axis.tz_convert("UTC").tz_localize(None)
	# The name is part of the axis: `DatetimeIndex.equals` compares it, so two
	# indexes holding the same instants under different names are not equal, and
	# the cross-check in `network_inputs` would refuse a correct pair.
	axis = axis.rename(SNAPSHOT_INDEX_NAME)
	return axis


def load_demand_profiles(
	config: Config,
	*,
	root: str | Path | None = None,
	buses: list[str] | None = None,
) -> pd.DataFrame:
	"""`demand_hourly` as a ``[time, bus]`` frame of MW.

	``buses`` restricts the frame to the buses the network actually has. A
	demand series keyed to a bus the network lacks is refused by `attach_loads`
	with a message naming the buses, which is the right failure -- but the
	caller that built the network already knows its own bus list, and filtering
	here turns "the weight table and the topology disagree" into a warning about
	the rows dropped rather than a crash after a solve's worth of work.

	The index is a `DatetimeIndex` because it becomes the network's snapshot
	axis: `attach_loads` sets the snapshots from it, and a frame whose index is
	a string column produces a network whose snapshots are strings, which the
	solver accepts and the multi-period code does not. It is timezone-naive UTC
	-- see `utc_naive` for why the artefact is not and the network cannot be.
	"""
	path = _processed(config, root) / DEMAND_ARTEFACT
	if not artefact_exists(path):
		raise InputError(
			f"no demand artefact at {path}; build `demand_hourly` first. A network "
			f"built without it has generation and topology and no load, which is "
			f"unsolvable and reads as a modelling result"
		)
	payload, _ = read_artefact(path, verify=False)
	frame = payload if isinstance(payload, pd.DataFrame) else pd.DataFrame(payload)
	required = {"bus_id", "timestamp_utc", "demand_mw"}
	missing = sorted(required - set(frame.columns))
	if missing:
		raise InputError(
			f"{path} lacks {missing}; it holds {', '.join(str(c) for c in frame.columns)}"
		)
	if frame.empty:
		raise InputError(f"{path} is empty; an empty demand series is not a demand series")

	wide = frame.pivot_table(
		index="timestamp_utc", columns="bus_id", values="demand_mw", aggfunc="sum"
	)
	wide.index = utc_naive(wide.index)
	# Column labels are bus ids read from the file, so they are strings; the
	# pivot's stub types them as `Scalar`.
	wide = wide.sort_index().rename(columns=str)

	if buses is not None:
		known = {str(bus) for bus in buses}
		dropped = [str(c) for c in wide.columns if str(c) not in known]
		if dropped:
			logger.warning(
				"demand.buses_not_in_network",
				count=len(dropped),
				examples=dropped[:5],
			)
			wide = wide.loc[:, [c for c in wide.columns if str(c) in known]]
		if wide.shape[1] == 0:
			raise InputError(
				f"{path} names no bus the network has ({len(dropped)} dropped, e.g. "
				f"{dropped[:5]}); the weight table and the topology disagree about "
				f"bus identity, and attaching nothing is not a disaggregation"
			)
	logger.info("demand.loaded", buses=int(wide.shape[1]), hours=int(wide.shape[0]))
	return wide


def load_renewable_profiles(
	config: Config,
	*,
	root: str | Path | None = None,
	buses: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
	"""`renewable_profiles` as ``{carrier: [time, bus]}`` capacity factors.

	The artefact is ``(carrier, bus, time) -> capacity_factor``; `attach_renewables`
	wants one frame per carrier. The split is here rather than there because the
	dataset's shape is the artefact's business, not the network builder's.
	"""
	path = _processed(config, root) / RENEWABLE_ARTEFACT
	if not artefact_exists(path):
		raise InputError(
			f"no renewable profile artefact at {path}; build `renewable_profiles` "
			f"first. A network with no profiles cannot expand into renewables, and "
			f"a solve without them reports a fossil-only mix as least-cost"
		)
	dataset, _ = read_artefact(path, verify=False)
	if PROFILE_VARIABLE not in dataset:
		raise InputError(
			f"{path} holds {sorted(dataset.data_vars)}; no {PROFILE_VARIABLE!r} variable"
		)
	array = dataset[PROFILE_VARIABLE]
	for dimension in ("carrier", "bus", "time"):
		if dimension not in array.dims:
			raise InputError(
				f"{path}: {PROFILE_VARIABLE!r} has dims {array.dims}; "
				f"{dimension!r} is missing"
			)
	# The `time` axis must be a datetime coordinate, not the integer index xarray
	# invents when a dimension has no coordinate. Without this check a cube whose
	# coordinate is named something else (a writer that kept the pandas index
	# name, say) reads as 0, 1, 2, ... and `to_pandas` casts those integers to
	# `datetime64[ns]` -- so every hour becomes a nanosecond after 1970, the
	# profiles silently cover 1970 instead of the modelled year, and nothing
	# downstream raises. That is the same silent-wrong shape as the tz bug above.
	time_coord = array.coords.get("time")
	if time_coord is None or not np.issubdtype(time_coord.dtype, np.datetime64):
		raise InputError(
			f"{path}: the 'time' dimension has "
			f"{'no coordinate' if time_coord is None else f'a {time_coord.dtype} coordinate'}"
			f"; it must be a datetime axis. An integer time index is read as "
			f"nanoseconds since 1970 and dates every profile to 1970"
		)

	known = {str(bus) for bus in buses} if buses is not None else None
	profiles: dict[str, pd.DataFrame] = {}
	for carrier in [str(c) for c in array.coords["carrier"].to_numpy()]:
		block = array.sel(carrier=carrier).transpose("time", "bus").to_pandas()
		if isinstance(block, pd.Series):  # one bus yields a Series, not a frame
			block = block.to_frame()
		block.columns = [str(c) for c in block.columns]
		block.index = utc_naive(block.index)
		block = block.sort_index().astype(float)
		if known is not None:
			kept = [c for c in block.columns if c in known]
			if not kept:
				logger.warning("renewables.carrier_has_no_network_bus", carrier=carrier)
				continue
			block = block.loc[:, kept]
		profiles[carrier] = block
	if not profiles:
		raise InputError(
			f"{path} yielded no carrier with a bus the network has; the profile "
			f"artefact was built against a different bus set"
		)
	logger.info("renewables.loaded", carriers=sorted(profiles))
	return profiles


def load_capital_costs(
	config: Config,
	*,
	root: str | Path | None = None,
	year: int | None = None,
) -> dict[str, float]:
	"""`costs` as ``{carrier: USD per MW}``, for the expansion model.

	pypsa's ``capital_cost`` is per MW of installed capacity, and the artefact
	is per kW, so the factor of 1000 is the whole reason this function exists as
	a named unit conversion rather than a multiplication at the call site.

	``year`` selects the cost year; the default is the scenario's first planning
	horizon, because a cost from a year the model does not solve is a number the
	objective cannot defend. A technology absent for that year is omitted rather
	than defaulted to zero: zero capital cost is free capacity, which
	`solve_expansion` refuses and which would otherwise be refused with a
	message about the network rather than about the missing cost row.
	"""
	path = _processed(config, root) / COSTS_ARTEFACT
	if not artefact_exists(path):
		raise InputError(
			f"no cost artefact at {path}; build `costs` first. Without it an "
			f"extendable generator has no capital cost, and the expansion model "
			f"builds free capacity"
		)
	payload, _ = read_artefact(path, verify=False)
	frame = payload if isinstance(payload, pd.DataFrame) else pd.DataFrame(payload)
	required = {"technology", "year", "capex_usd_per_kw"}
	missing = sorted(required - set(frame.columns))
	if missing:
		raise InputError(
			f"{path} lacks {missing}; it holds {', '.join(str(c) for c in frame.columns)}"
		)
	wanted = int(year if year is not None else min(config.scenario.planning_horizons))
	available = sorted({int(y) for y in frame["year"].dropna().unique()})
	if not available:
		raise InputError(f"{path} holds no cost year")
	# The nearest year at or before the requested one, so a model built for 2030
	# against a 2025 cost table uses 2025 rather than silently using 2040.
	eligible = [y for y in available if y <= wanted] or available
	selected = max(eligible)
	# Annotated because a boolean `.loc` is typed as a union of frame and
	# series, and every column access on the union widens to a scalar.
	rows: pd.DataFrame = frame.loc[frame["year"] == selected]
	technologies = [str(t) for t in rows["technology"].tolist()]
	capex_values = [_as_float(v) for v in rows["capex_usd_per_kw"].tolist()]
	costs = {
		technology: capex * 1000.0
		for technology, capex in zip(technologies, capex_values, strict=True)
		if capex == capex and capex > 0.0  # NaN is not equal to itself
	}
	if not costs:
		raise InputError(
			f"{path} has no positive capital cost for {selected}; the years it "
			f"holds are {available}"
		)
	logger.info("costs.loaded", year=selected, technologies=sorted(costs))
	return costs


def network_inputs(
	config: Config,
	*,
	root: str | Path | None = None,
	buses: list[str] | None = None,
	year: int | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, float]]:
	"""The three inputs `build_network` takes, read from the lake together.

	One call rather than three at the call site, because the three are always
	wanted together and a caller that fetched two of them would build a network
	whose provenance claims inputs it never read.
	"""
	demand = load_demand_profiles(config, root=root, buses=buses)
	profiles = load_renewable_profiles(config, root=root, buses=buses)
	costs = load_capital_costs(config, root=root, year=year)

	# The two series must share a time axis. `attach_loads` sets the network's
	# snapshots from the demand index and `attach_renewables` resets them from
	# the profiles', so a mismatch does not raise -- the second call silently
	# re-indexes the network and every load attached against the first axis
	# becomes a load at the wrong hour. That is a dispatch that balances and is
	# wrong, which is the worst kind of wrong here.
	#
	# Both axes are already `utc_naive` at this point, so this compares the same
	# clock the network will see. Comparing the raw artefacts would refuse a
	# demand frame and a profile cube that agree in UTC but differ in whether
	# the tz is carried, which is every real pair.
	for carrier, frame in sorted(profiles.items()):
		if not frame.index.equals(demand.index):
			raise InputError(
				f"{carrier} profiles cover {len(frame)} hours and demand covers "
				f"{len(demand)}; the two artefacts were built for different "
				f"periods. Rebuilding one against the other's year is the fix; "
				f"attaching them re-indexes the network and misplaces every load"
			)
	return demand, profiles, costs


def describe(frame: Any) -> dict[str, Any]:
	"""A frame's shape, for a provenance parameter dict."""
	if isinstance(frame, pd.DataFrame):
		return {"rows": int(frame.shape[0]), "columns": int(frame.shape[1])}
	return {}


__all__ = [
	"COSTS_ARTEFACT",
	"DEMAND_ARTEFACT",
	"InputError",
	"RENEWABLE_ARTEFACT",
	"describe",
	"load_capital_costs",
	"load_demand_profiles",
	"load_renewable_profiles",
	"network_inputs",
	"utc_naive",
]
