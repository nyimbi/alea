# SPDX-License-Identifier: MIT
"""Compose the multi-energy network.

This module is where the additivity guarantee is enforced rather than asserted.
Every sector builder returns views; this module materialises them onto a copy of
the electricity network, and it records a digest of the base network before and
after. If the digest moved, ``CouplingReport`` refuses to be constructed -- so
the gate (``test_sector_is_additive``) is a property of the type, and a coupling
bug cannot be reported as a modelling difference because it cannot be reported
at all.

The digest is taken over the base network's own component tables, not over the
file, because a NetCDF export stamps metadata and two exports of an unchanged
network differ by a few hundred bytes (the same failure that made a collateral
drift gate unpassable elsewhere in this project). It covers every table the
coupling layer could reach -- buses, generators, links, stores, storage units,
loads, lines, transformers, snapshots -- so a mutation anywhere in the
electricity model shows up.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import pandas as pd

from alea.config.models import Config
from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector import heat, hydrogen, industry, transport, water
from alea.sector._util import as_index, weighted_energy
from alea.sector.views import (
	CouplingReport,
	CouplingView,
	LinkRow,
	MassBalance,
	SectorBuild,
)

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

BASE_COMPONENTS: tuple[str, ...] = (
	"buses",
	"generators",
	"links",
	"stores",
	"storage_units",
	"loads",
	"lines",
	"transformers",
	"shunt_impedances",
)
"""Every base table the coupling layer could reach.

A component absent from this tuple is a component whose mutation would go
undetected, which is why the list is explicit rather than derived from whatever
the network happens to carry.
"""

SECTOR_BUS_SUFFIX: dict[str, str] = {
	"hydrogen": "h2",
	"heat": "heat",
	"transport": "ev",
	"industry": "steel",
	"water": "water",
	"renewables": "elec",
}
"""The bus each sector attaches to, when the caller does not name one."""

MULTI_BUS_COMPONENTS: tuple[str, ...] = ("Link",)
"""Components whose buses are numbered ``bus0``..``bus3``.

Every other component this layer builds -- ``Load``, ``Store``, ``Generator``,
``StorageUnit`` -- has a single ``bus``, and its builder already puts the
attachment bus there. Injecting a ``bus0`` column onto one of those makes PyPSA
warn that the attribute belongs to another component and then read the all-NaN
column as a bus name, so the consistency check reports every such component as
attached to an undefined bus. The list is explicit so a component added later
is a deliberate choice, not an accident of the injection loop.
"""


def _component(network: pypsa.Network, name: str) -> Any | None:
	"""A component store by either its plural key or its singular name.

	``name in network.components`` is deprecated in PyPSA 1.4 and raises a
	``DeprecationWarning`` -- which this project turns into an error -- so
	membership is tested against ``keys()``.

	The two spellings matter: ``network.components`` is keyed ``"links"`` while
	a view's ``asset`` is ``"Link"``, and a lookup that accepts only one of them
	reports a component the network carries as unknown.
	"""
	# `.keys()` is required, not stylistic: `ComponentsStore.__contains__` raises
	# DeprecationWarning, and this project's pytest config turns warnings into
	# errors, so `name in network.components` would fail the test rather than
	# answer the question. SIM118 wants the bare `in`; the bare `in` is a raise.
	if name in network.components.keys():  # noqa: SIM118
		return network.components[name]
	for key in network.components.keys():  # noqa: SIM118
		if network.components[key].name == name:
			return network.components[key]
	return None


def base_digest(network: pypsa.Network) -> str:
	"""A content digest of the base electricity network.

	Deterministic by construction: the tables are sorted before hashing, so two
	runs that added the same components in a different order hash identically,
	and pandas' hashing is a hash of values rather than of ``repr`` (AD-8).

	Only the *base* tables are covered. The coupled network's own assets are
	excluded because they are the thing being added; the question this answers is
	whether the electricity model changed, not whether the coupling did.
	"""
	assert network is not None, "a digest needs a network"
	digest = hashlib.sha256()
	for name in sorted(BASE_COMPONENTS):
		component = _component(network, name)
		if component is None:
			continue
		static = component.static
		digest.update(name.encode())
		if static.empty:
			digest.update(b"empty")
			continue
		ordered = static.sort_index()
		digest.update(
			pd.util.hash_pandas_object(ordered, index=True).to_numpy().tobytes()
		)
		digest.update("|".join(str(column) for column in ordered.columns).encode())
		dynamic = component.dynamic
		for key in sorted(dynamic):
			frame = dynamic[key]
			if frame is None or getattr(frame, "empty", True):
				continue
			digest.update(key.encode())
			digest.update(
				pd.util.hash_pandas_object(
					frame.sort_index().sort_index(axis=1), index=True
				)
				.to_numpy()
				.tobytes()
			)
	digest.update("|".join(str(s) for s in network.snapshots).encode())
	return digest.hexdigest()


def apply_view(network: pypsa.Network, view: CouplingView) -> None:
	"""Materialise one view onto the network.

	Every physical parameter lands on the network's static table under the column
	the view named, and every parameter's source lands in a parallel ``*_source``
	column. The sources travel with the network rather than only in the artefact,
	because a solved network is the thing a reader opens, and a number whose
	source is in a different file is a number whose source will be lost.

	Time series are attached through the component's dynamic frame, keyed by the
	column they override, and are length-checked against the network's snapshots
	before they are written -- a mismatched series is otherwise reindexed to
	NaNs and becomes an empty constraint rather than an error.
	"""
	assert network is not None, "apply_view needs a network"
	component = _component(network, view.asset)
	if component is None:
		raise ValueError(f"unknown component {view.asset!r}")
	if view.name in component.static.index:
		raise ValueError(
			f"{view.asset} {view.name!r} already exists on the network; adding it "
			f"twice would silently replace the base model's asset of that name"
		)

	attributes: dict[str, Any] = dict(view.attributes)
	attributes.update(view.physical)
	# The bus fields are top-level on the view rather than in ``attributes``, so
	# they are injected here -- but only for a component that has them. A Load
	# carries its single bus in ``bus``; adding a ``bus0`` column to it makes
	# PyPSA warn that the attribute belongs to another component, and then its
	# consistency check reads the all-NaN column as a bus name and reports every
	# load as attached to an undefined bus. Omitting the injection for Links is
	# the worse failure of the two: PyPSA accepts a link with no buses and only
	# fails at solve time, in a message that names the link and not the code that
	# built it.
	if view.asset in MULTI_BUS_COMPONENTS:
		for column in ("bus0", "bus1", "bus2", "bus3"):
			bus = getattr(view, column)
			if bus:
				attributes[column] = bus
	for column, source in view.parameter_sources.items():
		attributes[f"{column}_source"] = source

	# Buses, carriers and the sector's own provenance id are stored so the
	# network is self-describing: a solved NetCDF opened without the artefact
	# still says where each efficiency came from.
	attributes["sector"] = view.sector.value
	attributes["provenance_id"] = view.provenance_id

	for column, series in view.time_series.items():
		if len(series) != len(network.snapshots):
			raise ValueError(
				f"{view.name!r}.{column}: {len(series)} values for "
				f"{len(network.snapshots)} snapshots; PyPSA would reindex the "
				f"mismatch to NaN and the constraint would vanish"
			)

	network.add(view.asset, view.name, **attributes)

	for column, series in view.time_series.items():
		component.dynamic[column][view.name] = pd.Series(
			series, index=network.snapshots, dtype=float
		)
	assert view.name in component.static.index


def apply_views(network: pypsa.Network, views: Iterable[CouplingView]) -> int:
	"""Materialise a sequence of views. Returns how many were added."""
	added = 0
	for view in views:
		apply_view(network, view)
		added += 1
	assert added >= 0
	return added


def views_from_rows(rows: Iterable[LinkRow]) -> list[CouplingView]:
	"""Reconstruct views from artefact rows.

	The inverse of ``CouplingView.as_row``, and lossy in exactly one place: a row
	does not carry the per-snapshot series, so a reconstructed view whose
	``time_series_keys`` is non-empty has its scalar in ``values`` and no series.
	The function logs that loudly rather than returning a view that looks
	complete. ``couple`` does not use this path -- it keeps the views a sector
	builder returned -- so the loss only bites a caller rebuilding a network from
	an artefact, which is exactly when it should be told.
	"""
	from alea.sector.views import Parameter

	materialised = list(rows)
	out: list[CouplingView] = []
	for row in materialised:
		parameters = {
			key: Parameter(value=float(value), unit="", source=row.parameter_sources[key])
			for key, value in row.values.items()
			if key in row.parameter_sources and isinstance(value, int | float)
		}
		attributes = {
			key: value for key, value in row.values.items() if key not in parameters
		}
		if row.time_series_keys:
			logger.warning(
				"coupling.rows_are_lossy",
				name=row.name,
				columns=row.time_series_keys,
				reason="per-snapshot series live on the network, not in the row",
			)
		out.append(
			CouplingView(
				asset=row.asset,
				name=row.name,
				sector=row.sector,
				carrier=row.carrier,
				bus0=row.bus0,
				bus1=row.bus1,
				bus2=row.bus2,
				bus3=row.bus3,
				parameters=parameters,
				attributes=attributes,
				source=row.source,
				provenance_id=row.provenance_id,
				notes=row.notes,
			)
		)
	assert len(out) == len(materialised), "a row was dropped in reconstruction"
	return out


def sector_buses(prefix: str, *, electricity_bus: str | None = None) -> dict[str, str]:
	"""The bus names a coupled network needs, keyed by sector.

	``prefix`` names the node so a multi-country network gets one set of sector
	buses per node rather than one set for the continent -- which would connect
	Mombasa's hydrogen to Lagos's.

	``electricity_bus`` is the bus every sector couples to. It is passed in
	rather than constructed, because a node whose electricity bus is
	``KE_Mombasa`` has no bus called ``KE_Mombasa_elec`` and a constructed name
	would silently become a new, disconnected bus.
	"""
	assert prefix, "a bus prefix is required"
	buses = {sector: f"{prefix}_{suffix}" for sector, suffix in SECTOR_BUS_SUFFIX.items()}
	if electricity_bus is not None:
		buses["renewables"] = electricity_bus
	return buses


def add_sector_buses(
	network: pypsa.Network,
	prefix: str | None = None,
	*,
	electricity_bus: str | None = None,
) -> dict[str, str]:
	"""Add the sector buses. Idempotent: an existing bus is left alone.

	The electricity bus is never created here. It belongs to Layer 1, and
	inventing one when the network has none would give the coupling layer a
	disconnected island to attach to and no error to show for it.
	"""
	if electricity_bus is None:
		electricity_bus = _electricity_bus_name(network)
	if prefix is None:
		prefix = electricity_bus.rsplit("_", 1)[0] if "_" in electricity_bus else electricity_bus

	buses = sector_buses(prefix, electricity_bus=electricity_bus)
	carriers = {
		"hydrogen": Carrier.H2.value,
		"heat": Carrier.HEAT_PUMP.value,
		"transport": Carrier.BATTERY.value,
		"industry": "steel",
		"water": "water",
		"renewables": "AC",
	}
	for sector, bus in buses.items():
		if bus in network.buses.index:
			continue
		network.add("Bus", bus, carrier=carriers[sector])
	assert all(bus in network.buses.index for bus in buses.values()), "a sector bus is missing"
	return buses


def _electricity_bus_name(network: pypsa.Network) -> str:
	"""The network's electricity bus, or a refusal.

	One AC bus is the single-node case and is unambiguous. Several means the
	network is already spatially resolved and the caller must say which node it
	is coupling -- picking one silently would attach every sector to whichever
	bus happened to sort first.
	"""
	assert network is not None, "a bus lookup needs a network"
	ac = [
		bus
		for bus in network.buses.index
		if str(network.buses.loc[bus, "carrier"]).upper() == "AC"
	]
	if len(ac) == 1:
		return str(ac[0])
	if not ac:
		raise ValueError(
			"the network has no AC bus; sector coupling extends an electricity "
			"network and needs one to attach to"
		)
	raise ValueError(
		f"the network has {len(ac)} AC buses ({', '.join(sorted(ac)[:5])}...); "
		f"name the node to couple via buses= or bus_prefix="
	)


def couple(
	config: Config,
	network: pypsa.Network,
	*,
	buses: dict[str, str] | None = None,
	snapshots: pd.DatetimeIndex | None = None,
	weights: list[float] | None = None,
	water_enabled: bool = False,
	**sector_options: Any,
) -> tuple[pypsa.Network, CouplingReport]:
	"""Extend an electricity network with the sectors a config enables.

	The base network is copied, never mutated in place. That is not defensive
	programming: the electricity-only result is the fallback the plan names, and
	a coupling layer that modified the network it was handed would destroy the
	comparison the structural gate depends on.

	Returns the coupled network and the report. The report refuses to exist if
	the base digest moved, so the additivity check cannot be skipped by a caller
	that forgets to look.
	"""
	assert network is not None, "couple needs a base network"
	assert config is not None, "couple needs a config"
	# `network.snapshots` is a `DatetimeIndex | Index | MultiIndex` union; the
	# MultiIndex arm is what pyright objects to, and a coupled network is never
	# multi-period (that is a planning-layer concern), so the DatetimeIndex arm
	# is the one that holds here.
	index = as_index(snapshots if snapshots is not None else network.snapshots)  # type: ignore[arg-type]
	if not index.equals(pd.DatetimeIndex(network.snapshots)):
		raise ValueError(
			"the supplied snapshots differ from the network's; sector series are "
			"aligned on the network index and a mismatch would be reindexed to NaN"
		)

	before = base_digest(network)
	coupled = network.copy()

	requested_prefix = sector_options.pop("bus_prefix", None)
	if buses is not None:
		sector_bus = dict(buses)
		if "renewables" not in sector_bus:
			raise ValueError(
				"a buses mapping must name the electricity bus under 'renewables'; "
				"every sector couples there and a missing key would attach them "
				"to nothing"
			)
		electricity = sector_bus["renewables"]
		prefix = requested_prefix or _prefix_of(electricity)
	else:
		electricity = _electricity_bus_name(coupled)
		prefix = requested_prefix or _prefix_of(electricity)
		sector_bus = add_sector_buses(coupled, prefix, electricity_bus=electricity)

	builds: list[SectorBuild] = []
	builds.append(
		hydrogen.build_hydrogen(
			config.sector,
			bus_electricity=electricity,
			bus_hydrogen=sector_bus["hydrogen"],
			snapshots=index,
			weights=weights,
			**_subset(sector_options, "hydrogen"),
		)
	)
	builds.append(
		heat.build_heat(
			config.sector,
			bus_electricity=electricity,
			bus_heat=sector_bus["heat"],
			snapshots=index,
			weights=weights,
			**_subset(sector_options, "heat"),
		)
	)
	builds.append(
		transport.build_transport(
			config.sector,
			bus_electricity=electricity,
			bus_ev=sector_bus["transport"],
			snapshots=index,
			weights=weights,
			**_subset(sector_options, "transport"),
		)
	)
	builds.append(
		industry.build_industry(
			config.sector,
			bus_electricity=electricity,
			bus_heat=sector_bus["heat"],
			bus_hydrogen=sector_bus["hydrogen"],
			bus_steel=f"{prefix}_steel",
			bus_cement=f"{prefix}_cement",
			bus_co2=f"{prefix}_co2",
			bus_chemicals=f"{prefix}_chemicals",
			snapshots=index,
			weights=weights,
			**_subset(sector_options, "industry"),
		)
	)
	builds.append(
		water.build_water(
			bus_electricity=electricity,
			bus_water=sector_bus["water"],
			snapshots=index,
			weights=weights,
			enabled=water_enabled,
			**_subset(sector_options, "water"),
		)
	)

	rows: list[LinkRow] = []
	views: list[CouplingView] = []
	for build in builds:
		for row in build.rows:
			_ensure_bus(coupled, row)
			rows.append(row)
		views.extend(build.views)
		logger.info(
			"sector.applied",
			sector=build.sector.value,
			assets=len(build.rows),
			enabled=build.enabled,
			reason=build.reason,
		)

	if len(views) != len(rows):
		raise ValueError(
			f"{len(rows)} rows from {len(views)} views; every asset must have "
			f"both, or a series-bearing view was dropped and its sector would be "
			f"built without the profile that defines it"
		)
	apply_views(coupled, views)

	after = base_digest(network)
	report = CouplingReport(
		builds=builds,
		base_digest_before=before,
		base_digest_after=after,
		rows=rows,
	)
	logger.info(
		"coupling.done",
		sectors=[sector.value for sector in report.sectors],
		assets=len(rows),
		base_unchanged=report.base_unchanged,
	)
	assert report.base_unchanged, "the coupling layer mutated the base network"
	return coupled, report


def _subset(options: dict[str, Any], sector: str) -> dict[str, Any]:
	"""The options a sector builder accepts, from a flat or nested mapping."""
	nested = options.get(sector)
	if isinstance(nested, dict):
		return dict(nested)
	return {}






def _prefix_of(electricity_bus: str) -> str:
	"""The node prefix a sector bus name is built from.

	``KE_elec`` -> ``KE``; a bare ``elec`` stays itself, because a network whose
	electricity bus is simply ``elec`` is a single-node network and its sector
	buses read better as ``h2`` than as ``elec_h2``.
	"""
	if not electricity_bus:
		raise ValueError("an electricity bus name is required to derive a prefix")
	return electricity_bus.rsplit("_", 1)[0] if "_" in electricity_bus else electricity_bus


def _ensure_bus(network: pypsa.Network, row: LinkRow) -> None:
	"""Create any bus a row refers to that the network does not yet carry.

	A row that names a bus nobody created is a link attached to nothing, and
	PyPSA raises on it deep inside ``add`` with a message about the component
	rather than about the missing bus. Creating the bus here with a carrier
	derived from the sector keeps the failure surface small.
	"""
	for column in ("bus", "bus0", "bus1", "bus2", "bus3"):
		bus = row.values.get(column) if column == "bus" else getattr(row, column)
		if not bus or bus in network.buses.index:
			continue
		network.add("Bus", str(bus), carrier=row.carrier)


def generic_balance(
	network: pypsa.Network,
	*,
	bus: str,
	carrier: str = "",
	tolerance_frac: float = 1e-4,
) -> MassBalance:
	"""Conservation across any bus, without a carrier-specific balance.

	The sign convention is uniform across every port: a link's ``p_port`` is
	positive when the port draws from its bus, so the flow *into* the bus is
	``-p_port`` for ``bus0`` and ``bus1``-``bus3`` alike. Summing that over every
	component attached to the bus gives the net inflow, which must be zero at
	every snapshot.

	This exists because a gate that checks only the carriers someone wrote a
	balance for is a gate with a hole in it (the plan's rule). Hydrogen and heat
	have specialised balances whose terms mean something specific; everything
	else -- steel, cement, chemicals, water -- is swept by this one.
	"""
	assert bus, "a balance needs a bus"
	weights = network.snapshot_weightings["stores"].to_numpy(dtype=float)

	produced = 0.0
	consumed = 0.0
	if len(network.generators) and "p" in network.generators_t:
		gens = network.generators[network.generators["bus"] == bus].index
		if len(gens):
			produced += weighted_energy(network.generators_t.p[gens], weights)
	if len(network.loads) and "p" in network.loads_t:
		loads = network.loads[network.loads["bus"] == bus].index
		if len(loads):
			consumed += weighted_energy(network.loads_t.p[loads], weights)
	if len(network.storage_units) and "p" in network.storage_units_t:
		units = network.storage_units[network.storage_units["bus"] == bus].index
		if len(units):
			# StorageUnit p > 0 is discharge, i.e. energy into the bus.
			produced += weighted_energy(network.storage_units_t.p[units], weights)

	# Every link port attached to this bus. Port 1 is the primary output and must
	# be included -- omitting it (the loop once ran over "", "2", "3") reports
	# every product bus as consuming with nothing producing, which reads as a
	# huge imbalance rather than as the missing term it is.
	if len(network.links):
		link_in = 0.0
		for port in ("", "1", "2", "3"):
			bus_column = f"bus{port}" if port else "bus0"
			flow_column = f"p{port}" if port else "p0"
			if bus_column not in network.links.columns:
				continue
			if flow_column not in network.links_t:
				continue
			links = network.links[network.links[bus_column] == bus].index
			if len(links):
				link_in += -weighted_energy(network.links_t[flow_column][links], weights)
		if link_in >= 0.0:
			produced += link_in
		else:
			consumed += -link_in

	storage_delta = 0.0
	if len(network.stores) and "e" in network.stores_t:
		stores = network.stores[network.stores["bus"] == bus].index
		if len(stores):
			energy = network.stores_t.e[stores]
			storage_delta = float((energy.iloc[-1] - energy.iloc[0]).sum())

	residual = produced - consumed - storage_delta
	return MassBalance(
		carrier=carrier or str(bus),
		produced_mwh=produced,
		consumed_mwh=consumed,
		storage_delta_mwh=storage_delta,
		exported_mwh=0.0,
		residual_mwh=residual,
		tolerance_mwh=max(abs(produced) * tolerance_frac, 1e-6),
	)


def energy_balance_report(
	network: pypsa.Network,
	*,
	buses: dict[str, str],
) -> dict[str, Any]:
	"""Per-carrier energy balances for the coupled network.

	Hydrogen and heat have their own specialised balances because their terms
	mean something specific. Everything else is swept by ``generic_balance``, so
	a carrier nobody wrote a balance for is still checked: the gate says *every*
	carrier balances, and a balance implemented only for the carriers someone
	remembered is a gate with a hole in it.
	"""
	assert buses, "a balance report needs the sector buses"
	out: dict[str, Any] = {}
	for name, bus in buses.items():
		if bus not in network.buses.index:
			continue
		if name == "hydrogen":
			balance = hydrogen.h2_mass_balance(network, bus_hydrogen=bus)
		elif name == "heat":
			balance = heat.heat_energy_balance(network, bus_heat=bus)
		else:
			balance = generic_balance(network, bus=bus, carrier=name)
		out[name] = {
			"carrier": balance.carrier,
			"produced_mwh": balance.produced_mwh,
			"consumed_mwh": balance.consumed_mwh,
			"storage_delta_mwh": balance.storage_delta_mwh,
			"exported_mwh": balance.exported_mwh,
			"residual_mwh": balance.residual_mwh,
			"closes": balance.closes,
		}
	return out


__all__ = [
	"BASE_COMPONENTS",
	"SECTOR_BUS_SUFFIX",
	"add_sector_buses",
	"apply_view",
	"apply_views",
	"base_digest",
	"couple",
	"energy_balance_report",
	"generic_balance",
	"sector_buses",
	"views_from_rows",
]
