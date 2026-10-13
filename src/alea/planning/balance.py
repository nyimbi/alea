# SPDX-License-Identifier: MIT
"""The week-ahead balance: what the network expects, and what it can meet it with.

WHY this module exists, and why it is here rather than in Layer 3.
`reporting/weekly.py` declares ``week_ahead`` as its only ``required=True``
section, so the weekly report raises without it -- and nothing produced
``planning/outlook/{date}.parquet``. The blocker `reporting/producers.py`
recorded was "no producer at all", and that was exact.

The three quantities the section names -- demand, renewable availability, and
reserve margin -- are all *network* facts, not market ones. Each already had a
reader, and every one of them lived in `market/fleet.py`, one layer up: a
planning function that reached for them would invert the layering the whole
architecture rests on (`00-architecture.md` §2). So the readers moved down to
here, where the network is, and `market/fleet.py` imports them. Two copies of
"what a generator's capacity is" is the defect class this repository spends the
most prose on; the fix is one copy in the right layer.

**A balance is not a dispatch.** This computes what the network *could* meet the
week with, from ``p_max_pu`` and nameplate capacity, and what it *expects* to
face, from ``loads_t.p_set``. Neither needs a solve: an outlook is a statement
about capability, and requiring a dispatch would make the section's answer depend
on an operating decision the outlook exists to inform. Capacity is read the way
every other reader reads it -- ``p_nom_opt`` where a component is extendable --
so on a *solved* network this is the built system, and the stage reads a solved
network for exactly that reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from alea.logging import get_logger
from alea.registry import Carrier, CarrierClass, get_technology

if TYPE_CHECKING:  # pragma: no cover - the annotation only; pypsa costs 3.8s to import
	import pypsa

logger = get_logger(__name__)


class BalanceError(ValueError):
	"""A network cannot be expressed as a week-ahead balance.

	``ValueError`` rather than ``RuntimeError`` because that is what these
	readers raised where they lived before (`market/fleet.py`), and the market
	layer's own callers catch on it: the class moved down a layer without
	changing the exception a caller sees.
	"""


def load_series(network: pypsa.Network) -> np.ndarray:
	"""Total load per snapshot, in MW, aligned to ``network.snapshots``.

	A load's ``p_set`` may be a static column or a dynamic profile, and a network
	built without a demand stage carries the static form -- the same trap
	`whatif.extract._availability` records for ``p_max_pu``. Reading only the
	dynamic table reports zero demand for such a network, and a market cleared
	against zero demand has no price at all.
	"""
	loads = getattr(network, "loads", None)
	if loads is None or len(loads) == 0:
		raise BalanceError("the network carries no loads, so there is no demand to balance")

	snapshots = network.snapshots
	total = pd.Series(0.0, index=snapshots, dtype=float)
	dynamic = getattr(getattr(network, "loads_t", None), "p_set", None)
	static = numeric_column(loads, "p_set") if "p_set" in loads.columns else np.zeros(len(loads))
	named = {str(name): float(static[position]) for position, name in enumerate(loads.index)}

	for name in loads.index:
		if dynamic is not None and not dynamic.empty and name in dynamic.columns:
			series = pd.to_numeric(dynamic[name], errors="coerce")
		else:
			series = pd.Series(named[str(name)], index=snapshots, dtype=float)
		total = total.add(series.reindex(snapshots).fillna(0.0), fill_value=0.0)

	values = np.asarray(total.to_numpy(dtype=float), dtype=np.float64)
	assert values.shape[0] == len(snapshots), "the load series does not align with the snapshots"
	return np.nan_to_num(values, nan=0.0)


def numeric_column(frame: pd.DataFrame, column: str, *, fill: float = 0.0) -> np.ndarray:
	"""A numeric column as a NaN-free float array.

	``pd.to_numeric`` returns a union type under pandas' stubs, so the result is
	coerced through ``np.asarray`` in one place rather than at each call site.
	``fill`` is what a NaN becomes: zero for a capacity or a cost, which an
	absent number must not invent, and 1.0 for an availability, where NaN is
	PyPSA's own spelling of "unconstrained".
	"""
	converted = pd.to_numeric(frame[column], errors="coerce")
	values = np.asarray(converted.to_numpy(dtype=float), dtype=np.float64)
	return np.nan_to_num(values, nan=fill)


def generator_capacity_mw(generators: pd.DataFrame) -> np.ndarray:
	"""Nameplate MW per generator: the optimiser's build where it chose one.

	An extendable generator's capacity is ``p_nom_opt`` -- the value the solve
	chose -- and a fixed one's is ``p_nom``. Reading ``p_nom`` for an extendable
	unit reports the capacity *before* the expansion the network is the answer
	to, which is a market for a system that was never built.
	"""
	capacity = numeric_column(generators, "p_nom")
	if "p_nom_opt" in generators.columns:
		optimised = numeric_column(generators, "p_nom_opt")
		extendable = (
			np.asarray(generators["p_nom_extendable"].fillna(False).astype(bool), dtype=bool)
			if "p_nom_extendable" in generators.columns
			else np.zeros(len(generators), dtype=bool)
		)
		capacity = np.where(extendable, optimised, capacity)
	return capacity


def availability_frame(network: pypsa.Network, generators: pd.DataFrame) -> pd.DataFrame:
	"""Per-snapshot availability per generator, dynamic per unit where present.

	**Precedence is per generator, not per network.** ``p_max_pu`` has two homes
	in PyPSA: the static column on ``generators`` and the ``generators_t`` time
	series, and a network can carry both at once -- a renewables stage writes a
	series for the solar units and leaves the thermal ones on their static
	column. Choosing between them for the *whole* table is what this function did
	first, and it was wrong in the way that is hardest to see: with a dynamic
	table present, a generator that had none was reindexed in at ``0.0``, so coal
	offered nothing, never entered the stack, and the market cleared at the value
	of lost load with the system in blackout -- a plausible-looking price for a
	system that is not short.

	So a generator with a dynamic column is read from it, and a generator without
	one is read from its static ``p_max_pu``, defaulting to 1.0 when the column is
	absent. The two readings exist for the reasons they always did: a network
	built without a renewables stage carries only the static form, and reading
	only the dynamic table gives every unit an availability of NaN.
	"""
	snapshots = network.snapshots
	dynamic = getattr(getattr(network, "generators_t", None), "p_max_pu", None)
	static = (
		numeric_column(generators, "p_max_pu", fill=1.0)
		if "p_max_pu" in generators.columns
		else np.ones(len(generators), dtype=np.float64)
	)

	columns: dict[str, np.ndarray] = {}
	for position, name in enumerate(generators.index):
		key = str(name)
		if dynamic is not None and not dynamic.empty and name in dynamic.columns:
			series = pd.to_numeric(dynamic[name], errors="coerce")
			values = series.reindex(snapshots).to_numpy(dtype=float)
			columns[key] = np.nan_to_num(values, nan=0.0)
		else:
			# A unit with no series offers its static fraction at every snapshot.
			columns[key] = np.full(len(snapshots), float(static[position]), dtype=np.float64)

	return pd.DataFrame(columns, index=snapshots, dtype=float)


def _snapshot_times(snapshots: Any) -> pd.DatetimeIndex:
	"""Each snapshot as a timestamp, from either of PyPSA's two index shapes.

	A single-investment-period network indexes snapshots by a ``DatetimeIndex``;
	a multi-period one indexes by ``(period, timestep)`` tuples. ``market.service``
	already resolves the tuple by taking element zero, and this keeps that one
	convention in one place rather than letting a second reader guess.
	"""
	values = [
		pd.Timestamp(str(entry[0] if isinstance(entry, tuple) else entry)) for entry in snapshots
	]
	return pd.DatetimeIndex(values)


def _classify(carriers: list[str]) -> tuple[list[CarrierClass | None], np.ndarray, np.ndarray]:
	"""Each carrier's registry class, and the two masks the balance needs.

	Returns ``(kinds, renewable, firm)``: the class per generator, whether it is
	variable-renewable, and whether it counts toward the capacity the margin is
	measured against.

	**Read from the registry, not from a list here.** A carrier set spelled out
	in this module would be a second source of truth for "what a VRE is", and the
	one thing this repository knows about two spellings of a fact is that they
	drift -- `01-foundations` and `02-data-pipeline` both say so, and the loss
	kernel's unit error is the measured instance. `get_technology` is the
	registry's own lookup, cached, and `registry/technologies.py` owns the
	classes.

	**An unknown carrier counts as firm.** A network's fleet table is an ingested
	artefact, not a closed set, and refusing the whole balance for one unmapped
	row would trade a wrong number for no number. Firm is the conservative
	reading: it cannot flatter the margin by calling an unknown plant
	weather-driven, and an unknown carrier that *is* weather-driven overstates
	the margin rather than hiding a shortfall.

	**Load shedding is excluded from firm capacity.** A load-shedding unit is how
	the model represents *unserved* demand, so counting it as available capacity
	reports a system that always meets its load -- because the generator standing
	in for not meeting it was in the total. The same exclusion `market/fleet.py`
	makes when it refuses to bid one into the stack, and for the same reason.
	"""
	kinds: list[CarrierClass | None] = []
	for carrier in carriers:
		try:
			kinds.append(get_technology(carrier).klass)
		except KeyError:
			logger.info("balance.unknown_carrier", carrier=carrier)
			kinds.append(None)

	renewable = np.array([kind is CarrierClass.VRE for kind in kinds], dtype=bool)
	firm = np.array(
		[
			not (kind is CarrierClass.COUPLING and _is_shedding(carrier))
			for kind, carrier in zip(kinds, carriers, strict=True)
		],
		dtype=bool,
	)
	return kinds, renewable, firm


def _horizon_days(
	snapshots: Any,
	*,
	days: int,
	start: str | None,
) -> tuple[list[pd.Timestamp], pd.DatetimeIndex]:
	"""The days a bounded horizon covers, and each snapshot's own day.

	Shared by `week_ahead_rows` and `renewable_forecast_rows`, because both
	render a bounded window under a heading that promises one, and a second
	spelling of "which snapshots are in the week" is the drift this repository's
	registers are mostly about. Returns the selected days *and* the normalised
	snapshot index, because a caller needs to mask the second by the first.

	**``start`` is localised to the snapshots' own zone before it is compared.**
	A caller writing ``start="2031-01-01"`` means a calendar date, and pandas
	will not compare a naive Timestamp against an aware index -- it raises
	``TypeError: Cannot compare tz-naive and tz-aware timestamps`` from inside
	the comparison, which is a crash where the caller wanted either a window or
	a refusal naming the horizon. The network's own zone is the only reading of
	a bare date that is not an invention.
	"""
	day_of = _snapshot_times(snapshots).normalize()
	first = (
		pd.Timestamp(start).normalize().tz_localize(day_of.tz)
		if start is not None and pd.Timestamp(start).tz is None
		else (pd.Timestamp(start).normalize() if start is not None else day_of[0])
	)
	selected = [day for day in sorted(set(day_of)) if day >= first][:days]
	if not selected:
		raise BalanceError(
			f"no snapshot falls on or after {first:%Y-%m-%d}; the network's horizon is "
			f"{day_of[0]:%Y-%m-%d} to {day_of[-1]:%Y-%m-%d}"
		)
	return selected, day_of


def week_ahead_rows(
	network: pypsa.Network,
	*,
	days: int = 7,
	start: str | None = None,
) -> pd.DataFrame:
	"""The week-ahead balance, one row per day, in the section's own columns.

	`reporting/weekly.py`'s ``week_ahead`` reads ``planning/outlook/{date}.parquet``
	with columns ``["Day", "Demand", "Renewable", "Margin", "Basis"]``. Three of
	those are numeric, so ``_rows_for`` binds each header to a column of the row
	naming it and never falls back to the primary: a row carrying only a demand
	raises rather than printing the demand under "Renewable". Hence a column per
	quantity, named for its header.

	**What each number is, because a margin with no stated definition is a number
	a reader will assume.** Demand is the day's mean load; Renewable is the mean
	available output of the *variable* renewables -- the carriers the registry
	classes as VRE, which are exactly the weather-driven ones; Margin is the mean
	total available output minus the mean demand. So the row satisfies
	``Margin == firm_available + Renewable - Demand`` and a reader can check it,
	which is the property that makes the three columns one table rather than
	three series.

	**Why means, and not the peak.** A reserve margin is often quoted at the
	daily peak, and that reading was rejected for a measured reason: on a
	solar-heavy system the peak is in the evening, so a peak-snapshot "Renewable"
	column is zero in every row and the section's own second column would read as
	a broken series. A week-ahead outlook is an operational table, and an
	operational day is an average power -- the same choice `generation_mix_rows`
	makes for the daily mix, and for the same reason.

	**Load shedding is excluded from capacity.** A load-shedding unit is how the
	model represents *unserved* demand, so counting it as available capacity would
	report a system that always meets its load because the generator standing in
	for not meeting it was in the total. It is excluded, and a network that is
	short shows a negative margin -- which is the true statement.

	``days`` bounds the horizon and ``start`` chooses where it begins. A network
	whose snapshots cover a year would otherwise render 8,760 rows under a heading
	that promises a week.
	"""
	assert network is not None, "network must not be None"
	if days <= 0:
		raise BalanceError(f"a week-ahead balance of {days} days is empty by construction")

	snapshots = network.snapshots
	if len(snapshots) == 0:
		raise BalanceError("the network has no snapshots, so there is no week to look ahead to")
	generators = network.generators
	if len(generators) == 0:
		raise BalanceError(
			"the network has no generators, so every day's margin would be the whole "
			"of demand and the table would report a blackout as a capacity shortfall "
			"rather than as a network with nothing in it"
		)

	demand = load_series(network)
	capacity = generator_capacity_mw(generators)
	available = availability_frame(network, generators).to_numpy(dtype=float) * capacity
	assert available.shape == (len(snapshots), len(generators)), (
		"the availability matrix does not align with the snapshots and generators"
	)

	carriers = [str(value) for value in generators["carrier"]]
	_kinds, renewable, firm = _classify(carriers)

	selected, day_of = _horizon_days(snapshots, days=days, start=start)

	demand_rows: list[float] = []
	renewable_rows: list[float] = []
	margin_rows: list[float] = []
	for day in selected:
		mask = np.asarray(day_of == day, dtype=bool)
		demand_mw = float(demand[mask].mean())
		renewable_mw = float(available[np.ix_(mask, renewable)].sum(axis=1).mean())
		available_mw = float(available[np.ix_(mask, firm)].sum(axis=1).mean())
		demand_rows.append(demand_mw)
		renewable_rows.append(renewable_mw)
		margin_rows.append(available_mw - demand_mw)

	frame = pd.DataFrame(
		{
			"label": [f"{day:%Y-%m-%d}" for day in selected],
			"value": demand_rows,
			"unit": ["MW"] * len(selected),
			"demand": demand_rows,
			"renewable": renewable_rows,
			"margin": margin_rows,
		}
	)
	logger.info(
		"balance.week_ahead",
		days=int(len(frame)),
		first=str(selected[0]),
		last=str(selected[-1]),
		generators=int(len(generators)),
		renewable_generators=int(renewable.sum()),
	)
	return frame


def renewable_forecast_rows(
	network: pypsa.Network,
	*,
	days: int = 7,
	start: str | None = None,
) -> pd.DataFrame:
	"""The week's capacity factors, one row per variable-renewable carrier.

	`reporting/weekly.py`'s ``renewable_forecast`` reads
	``weather/renewables/{date}.parquet`` with columns ``["Technology",
	"Capacity factor", "Basis"]``. One numeric column, so ``_rows_for`` binds
	the primary directly and the row needs no extras.

	**The source is the network's own ``p_max_pu``, and the basis is
	``modelled``.** The section's prose says "from the weather model", and that
	is exactly what these are: `planning.renewables.attach_renewable_profiles`
	attaches the atlite-derived per-bus capacity factor as each generator's
	``p_max_pu``, so reading it back is reading the weather model's output
	without re-running it. The register recorded the blocker as "a *forecast* is
	a different quantity from a *profile*", and that is right about the
	distinction and wrong about the consequence: `week_ahead` shipped the same
	call one section over -- a modelled profile is what this repository has, and
	calling it a forecast in the prose while recording ``modelled`` in the
	provenance is the honest form. A genuine NWP-driven forecast would be a new
	model, not a rewiring.

	**One row per carrier, not per bus.** The section's first column is
	"Technology" and its unit is a capacity factor, so the row is a carrier and
	the number is that carrier's fleet-wide factor. It is the mean over the
	carrier's generators weighted by *nameplate capacity*, not the mean of the
	per-unit factors: a carrier with one 500 MW unit and twenty 5 MW units has
	one capacity factor, and an unweighted mean would report the small units'
	weather as though it were the fleet's.

	**A carrier with no capacity is excluded, not reported as zero.** A
	generator whose ``p_nom`` is zero has no capacity factor -- the quotient is
	undefined, and ``0.0`` would render as a technology that produces nothing
	rather than one that is not built.
	"""
	assert network is not None, "network must not be None"
	if days <= 0:
		raise BalanceError(f"a renewable forecast of {days} days is empty by construction")

	snapshots = network.snapshots
	if len(snapshots) == 0:
		raise BalanceError("the network has no snapshots, so there is no week to look ahead to")
	generators = network.generators
	if len(generators) == 0:
		raise BalanceError(
			"the network has no generators, so there is no carrier to report a "
			"capacity factor for"
		)

	carriers = [str(value) for value in generators["carrier"]]
	_kinds, renewable, _firm = _classify(carriers)
	if not renewable.any():
		raise BalanceError(
			"the network has no variable-renewable generator; a renewable forecast "
			"with no renewable carrier is an empty table under a heading that "
			"promises one. The registry classes carriers, and none of this "
			f"network's ({sorted(set(carriers))}) is VRE"
		)

	capacity = generator_capacity_mw(generators)
	available = availability_frame(network, generators).to_numpy(dtype=float)
	assert available.shape == (len(snapshots), len(generators)), (
		"the availability matrix does not align with the snapshots and generators"
	)

	selected, day_of = _horizon_days(snapshots, days=days, start=start)
	# Positions rather than a boolean mask: `np.ix_` takes index arrays, and a
	# boolean one there is the shape pyright rejects and numpy would broadcast
	# as a mask over the wrong axis.
	hours = np.flatnonzero(np.isin(day_of.to_numpy(), np.asarray(selected)))

	rows: list[dict[str, Any]] = []
	variable = sorted(
		{carrier for carrier, is_vre in zip(carriers, renewable, strict=True) if is_vre}
	)
	for carrier in variable:
		columns = [
			position
			for position, (name, is_vre) in enumerate(zip(carriers, renewable, strict=True))
			if is_vre and name == carrier
		]
		built = np.array(
			[position for position in columns if capacity[position] > 0.0], dtype=np.intp
		)
		if built.size == 0:
			logger.info("balance.renewable_forecast.no_capacity", carrier=carrier)
			continue
		weights = capacity[built]
		# Per snapshot, the fleet-wide factor: the capacity-weighted mean of the
		# per-unit factors. `available` is already a fraction of nameplate, so
		# the weighting is the same arithmetic as a system-wide capacity factor.
		factors = available[np.ix_(hours, built)] @ weights / float(weights.sum())
		rows.append(
			{
				"label": carrier,
				"value": float(factors.mean()),
				"unit": "capacity factor",
				"n_generators": float(built.size),
				"capacity_mw": float(weights.sum()),
			}
		)

	if not rows:
		raise BalanceError(
			"every variable-renewable carrier in this network has zero nameplate "
			"capacity, so no capacity factor is defined; reporting 0.0 would render "
			"as a technology that produces nothing rather than one that is not built"
		)

	frame = pd.DataFrame(rows, columns=["label", "value", "unit", "n_generators", "capacity_mw"])
	logger.info(
		"balance.renewable_forecast",
		carriers=int(len(frame)),
		days=int(len(selected)),
		first=str(selected[0]),
		last=str(selected[-1]),
	)
	return frame


def _is_shedding(carrier: str) -> bool:
	"""Whether a carrier is the model's stand-in for unserved demand."""
	try:
		return get_technology(carrier).carrier is Carrier.LOAD_SHEDDING
	except KeyError:
		return False


__all__ = [
	"BalanceError",
	"availability_frame",
	"generator_capacity_mw",
	"load_series",
	"renewable_forecast_rows",
	"numeric_column",
	"week_ahead_rows",
]
