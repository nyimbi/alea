# SPDX-License-Identifier: MIT
"""Heat: heat pumps, thermal storage, resistive backup.

COP is the parameter the sector turns on. A fixed COP of 3 is wrong in a way
that matters for a heating-dominated system: an air-source heat pump delivers
about 4.5 at a mild 10 °C and about 1.8 at a frosty -5 °C, and the hours when
heat demand peaks are exactly the hours when COP is lowest. Modelling that as a
constant overstates the pump's contribution precisely when the system needs it
most, and understates the peak electrical demand it creates.

So both paths exist and both are sourced. The constant is accepted -- the plan
permits it -- but it is recorded as a simplification in the view's notes and in
the artefact's provenance, never silently. The temperature-dependent path
computes COP from a Carnot fraction over an ambient series, which is the route
the plan calls the better one (05-layer2 §2.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from alea.config.models import SectorConfig
from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector._util import as_index, series_over, weighted_energy
from alea.sector.views import (
	CouplingView,
	EnergyBalance,
	Parameter,
	Sector,
	SectorBuild,
)

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

KELVIN_OFFSET = 273.15
"""Absolute zero in Celsius. Named so the conversion is not a bare 273.15."""

CARNOT_FORM = "COP = eta_carnot * T_sink / (T_sink - T_source)"
"""The temperature-dependent COP model.

A real heat pump achieves a fraction of the Carnot limit. The fraction is a
technology property, so it is a sourced parameter rather than a constant baked
into this module -- the same rule as the electrolyser efficiency.
"""


def cop_from_temperature(
	ambient_c: pd.Series,
	*,
	sink_temperature_c: float,
	carnot_fraction: float,
	sink_source: str,
	carnot_fraction_source: str,
	floor: float = 1.0,
) -> pd.Series:
	"""COP as a time series, from an ambient temperature series.

	``floor`` is not cosmetic. As ambient approaches the sink temperature the
	Carnot expression diverges, and above it the pump cannot heat at all; an
	unclamped series puts a COP of 40 into the network for the mildest hour of
	the year, which the optimiser will find and use to generate heat for free.
	The floor keeps the model physical at the warm end.
	"""
	index = as_index(pd.DatetimeIndex(ambient_c.index))
	ambient = series_over(ambient_c.to_numpy(), index, "ambient_c")
	if not sink_source.strip() or not carnot_fraction_source.strip():
		raise ValueError(
			"a temperature-dependent COP needs both a sink-temperature source "
			"and a Carnot-fraction source"
		)
	if not 0.0 < carnot_fraction <= 1.0:
		raise ValueError(f"carnot_fraction must be in (0, 1], got {carnot_fraction}")
	if floor <= 0.0:
		raise ValueError(f"COP floor must be positive, got {floor}")

	t_source = ambient + KELVIN_OFFSET
	t_sink = sink_temperature_c + KELVIN_OFFSET
	lift = t_sink - t_source
	# A lift at or below zero is a pump that cannot heat: the floor applies.
	cop = np.where(lift > 0.0, carnot_fraction * t_sink / np.maximum(lift, 1e-9), floor)
	out = pd.Series(np.maximum(cop, floor), index=index, name="cop", dtype=np.float64)
	assert (out >= floor).all(), "COP below its floor"
	return out


def heat_pump_view(
	bus_electricity: str,
	bus_heat: str,
	*,
	cop: float,
	cop_source: str,
	p_nom: float,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "heat_pump",
) -> CouplingView:
	"""A heat pump as a ``Link`` with a fixed COP.

	The view records the simplification in ``notes`` so it reaches the artefact:
	a reader comparing a constant-COP run against a temperature-dependent one
	must be able to see which was which without reading the config that produced
	it.
	"""
	assert bus_electricity, "a heat pump needs an electricity bus"
	assert bus_heat, "a heat pump needs a heat bus"
	assert cop > 0.0, "COP must be positive"

	source = cop_source.strip()
	if not source:
		raise ValueError(
			"heat_pumps_enabled requires heat_pump_cop_source; a COP nobody can "
			"trace is an untraceable claim about the system's efficiency "
			"(05-layer2 §2.2)"
		)

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.HEAT,
		carrier=Carrier.HEAT_PUMP.value,
		bus0=bus_electricity,
		bus1=bus_heat,
		parameters={
			"efficiency": Parameter(
				value=cop,
				unit="MWh_th/MWh_el",
				source=source,
				notes=CARNOT_FORM,
			)
		},
		attributes={
			"p_nom": float(p_nom),
			"p_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
		},
		source=source,
		notes=(
			"Fixed COP: a simplification (05-layer2 §2.2). A temperature-dependent "
			"COP is the better model; use heat_pump_view_from_temperature."
		),
	)
	assert view.parameters["efficiency"].value == cop
	return view


def heat_pump_view_from_temperature(
	bus_electricity: str,
	bus_heat: str,
	*,
	ambient_c: pd.Series,
	sink_temperature_c: float,
	carnot_fraction: float,
	sink_source: str,
	carnot_fraction_source: str,
	p_nom: float,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "heat_pump",
) -> CouplingView:
	"""A heat pump whose COP follows an ambient temperature series.

	The static ``efficiency`` is the series mean, which is what PyPSA uses when
	the time series is absent (an aggregated snapshot set that dropped the
	series, for instance). The series is the model; the scalar is the fallback,
	and both come from the same two sources.
	"""
	cop = cop_from_temperature(
		ambient_c,
		sink_temperature_c=sink_temperature_c,
		carnot_fraction=carnot_fraction,
		sink_source=sink_source,
		carnot_fraction_source=carnot_fraction_source,
	)
	view = heat_pump_view(
		bus_electricity,
		bus_heat,
		cop=float(cop.mean()),
		cop_source=f"{CARNOT_FORM}; {carnot_fraction_source}",
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		name=name,
	)
	view = view.model_copy(
		update={
			"time_series": {"efficiency": cop.to_list()},
			"notes": (
				f"COP time series from ambient temperature, sink "
				f"{sink_temperature_c:g} °C, Carnot fraction {carnot_fraction:g} "
				f"(05-layer2 §2.2)"
			),
		}
	)
	logger.info(
		"heat.cop_series",
		mean=round(float(cop.mean()), 3),
		minimum=round(float(cop.min()), 3),
		maximum=round(float(cop.max()), 3),
	)
	assert len(view.time_series["efficiency"]) == len(cop)
	return view


def thermal_storage_view(
	bus_heat: str,
	*,
	e_nom: float,
	standing_loss_per_hour: float,
	standing_loss_source: str,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "thermal_storage",
) -> CouplingView:
	"""Thermal storage as a ``Store`` with a standing loss.

	A hot-water tank loses heat whether or not it is used, and that loss is what
	makes it a store rather than a battery. Without it the optimiser fills the
	tank in summer and draws on it in winter, which no tank does.
	"""
	assert bus_heat, "thermal storage needs a heat bus"
	assert e_nom >= 0.0, "e_nom must be non-negative"
	assert 0.0 <= standing_loss_per_hour < 1.0, "standing loss must be in [0, 1)"

	source = standing_loss_source.strip()
	if not source:
		raise ValueError("thermal storage requires standing_loss_source")

	view = CouplingView(
		asset="Store",
		name=name,
		sector=Sector.HEAT,
		carrier=Carrier.THERMAL_STORAGE.value,
		bus0=bus_heat,
		parameters={
			"standing_loss": Parameter(
				value=standing_loss_per_hour,
				unit="per_hour",
				source=source,
				uncertainty=0.5,
				uncertainty_basis=(
					"tank loss depends on insulation standard and ambient "
					"temperature, which vary by a factor of two in practice"
				),
			)
		},
		attributes={
			"bus": bus_heat,
			"e_nom": float(e_nom),
			"e_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
		},
		source=source,
	)
	assert view.parameters["standing_loss"].value == standing_loss_per_hour
	return view


def resistive_backup_view(
	bus_electricity: str,
	bus_heat: str,
	*,
	p_nom: float,
	source: str = "05-layer2 §2.2 (resistive backup)",
	name: str = "resistive_backup",
) -> CouplingView:
	"""Resistive heating as a ``Link`` at unit efficiency.

	Efficiency 1.0 here is a definition, not an empirical claim: resistive heat
	is the conversion of electricity to heat by definition. It is still recorded
	as a sourced parameter, because a downstream reader cannot tell a definition
	from an assumption unless the source says which it is.
	"""
	assert bus_electricity and bus_heat, "resistive backup needs both buses"
	assert p_nom >= 0.0, "p_nom must be non-negative"

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.HEAT,
		carrier=Carrier.HEAT_PUMP.value,
		bus0=bus_electricity,
		bus1=bus_heat,
		parameters={
			"efficiency": Parameter(
				value=1.0,
				unit="MWh_th/MWh_el",
				source=source,
				notes="Definitional: resistive heat is 1:1 by construction.",
			)
		},
		attributes={"p_nom": float(p_nom), "p_nom_extendable": False},
		source=source,
		notes="Backup only: it exists to cover the hours the pump cannot.",
	)
	return view


def heat_demand_view(
	bus_heat: str,
	*,
	annual_demand_twh: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	source: str,
	profile: pd.Series | None = None,
	name: str = "heat_demand",
) -> CouplingView:
	"""Heat demand as a fixed ``Load``.

	Heat demand is strongly seasonal and a flat profile is a poor model of it,
	so a caller with a shape should pass one. Without a shape the load is flat
	and the view's notes say so -- a flat heat load understates peak heat demand
	and therefore understates the pump capacity the system needs.
	"""
	from alea.sector._util import annual_series, total_hours, twh_per_year_to_mwh

	assert bus_heat, "heat demand needs a heat bus"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	demand_mwh = twh_per_year_to_mwh(annual_demand_twh, hours)

	if profile is None:
		p_set = annual_series(demand_mwh, index, weights)
		notes = f"{annual_demand_twh:g} TWh/year, flat (a poor model of seasonality)"
	else:
		p_set = series_over(profile.to_numpy(), index, "p_set")
		notes = f"{annual_demand_twh:g} TWh/year, shaped profile"

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.HEAT,
		carrier=Carrier.HEAT_PUMP.value,
		bus0=bus_heat,
		attributes={"bus": bus_heat, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=notes,
	)
	assert len(view.time_series["p_set"]) == len(index)
	return view


def build_heat(
	config: SectorConfig,
	*,
	bus_electricity: str,
	bus_heat: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	heat_pump_p_nom: float = 0.0,
	ambient_c: pd.Series | None = None,
	sink_temperature_c: float = 55.0,
	carnot_fraction: float = 0.45,
	storage_e_nom: float = 0.0,
	standing_loss_per_hour: float = 0.0,
	standing_loss_source: str = "",
	demand_twh: float = 0.0,
	demand_source: str = "",
) -> SectorBuild:
	"""The heat sector, as a set of views.

	``ambient_c`` selects the temperature-dependent COP path. Passing it is the
	recommendation (05-layer2 §2.2); omitting it falls back to the config's
	constant COP and the view records that as a simplification.
	"""
	assert bus_electricity, "heat coupling needs an electricity bus"
	index = as_index(snapshots)

	if not config.heat_pumps_enabled:
		return SectorBuild(
			sector=Sector.HEAT,
			enabled=False,
			reason="sector.heat_pumps_enabled is false",
		)

	if ambient_c is not None:
		pump = heat_pump_view_from_temperature(
			bus_electricity,
			bus_heat,
			ambient_c=ambient_c,
			sink_temperature_c=sink_temperature_c,
			carnot_fraction=carnot_fraction,
			sink_source=f"flow temperature {sink_temperature_c:g} °C, 05-layer2 §2.2",
			carnot_fraction_source=config.heat_pump_cop_source,
			p_nom=heat_pump_p_nom,
			extendable=heat_pump_p_nom <= 0.0,
		)
	else:
		pump = heat_pump_view(
			bus_electricity,
			bus_heat,
			cop=config.heat_pump_cop,
			cop_source=config.heat_pump_cop_source,
			p_nom=heat_pump_p_nom,
			extendable=heat_pump_p_nom <= 0.0,
		)

	views: list[CouplingView] = [
		pump,
		resistive_backup_view(bus_electricity, bus_heat, p_nom=heat_pump_p_nom),
	]
	if storage_e_nom > 0.0:
		views.append(
			thermal_storage_view(
				bus_heat,
				e_nom=storage_e_nom,
				standing_loss_per_hour=standing_loss_per_hour,
				standing_loss_source=standing_loss_source or config.heat_pump_cop_source,
			)
		)
	if demand_twh > 0.0:
		views.append(
			heat_demand_view(
				bus_heat,
				annual_demand_twh=demand_twh,
				snapshots=index,
				weights=weights,
				source=demand_source or config.heat_pump_cop_source,
			)
		)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.HEAT, rows=rows, views=views, enabled=True)
	logger.info(
		"heat.built",
		assets=len(rows),
		temperature_dependent=ambient_c is not None,
	)
	assert all(row.parameter_sources.get("efficiency") for row in rows if row.asset == "Link")
	return build


def heat_energy_balance(
	network: pypsa.Network,
	*,
	bus_heat: str,
	tolerance_frac: float = 1e-4,
) -> EnergyBalance:
	"""Conservation of heat across the heat bus.

	Heat is produced and consumed entirely inside the modelled system, so the
	export term is structurally zero -- and it is stated as zero rather than
	omitted, because a balance that quietly drops a term is indistinguishable
	from one where the term is genuinely absent.
	"""
	assert bus_heat, "balance needs a heat bus"
	weights = network.snapshot_weightings["stores"].to_numpy(dtype=float)

	produced = 0.0
	if len(network.links) and "p1" in network.links_t:
		to_bus = network.links[network.links["bus1"] == bus_heat].index
		if len(to_bus):
			# p1 is negative on injection into bus1, so heat delivered is -p1.
			produced -= weighted_energy(network.links_t.p1[to_bus], weights)

	consumed = 0.0
	if len(network.loads) and "p" in network.loads_t:
		loads = network.loads[network.loads["bus"] == bus_heat].index
		if len(loads):
			consumed = weighted_energy(network.loads_t.p[loads], weights)
	if len(network.links) and "p0" in network.links_t:
		from_bus = network.links[network.links["bus0"] == bus_heat].index
		if len(from_bus):
			consumed += weighted_energy(network.links_t.p0[from_bus], weights)

	storage_delta = 0.0
	if len(network.stores) and "p" in network.stores_t:
		stores = network.stores[network.stores["bus"] == bus_heat].index
		if len(stores):
			# Store p > 0 is discharge, so the sign is flipped to keep
			# ``storage_delta`` as net energy into storage. The energy-level
			# difference (``e.iloc[-1] - e.iloc[0]``) is not used: for a store
			# with a non-zero initial level it counts the starting stock as if it
			# had been charged during the horizon and the balance misses by it.
			storage_delta -= weighted_energy(network.stores_t.p[stores], weights)
	if len(network.storage_units) and "p" in network.storage_units_t:
		units = network.storage_units[network.storage_units["bus"] == bus_heat].index
		if len(units):
			storage_delta -= weighted_energy(network.storage_units_t.p[units], weights)

	residual = produced - consumed - storage_delta
	balance = EnergyBalance(
		carrier=Carrier.HEAT_PUMP.value,
		produced_mwh=produced,
		consumed_mwh=consumed,
		storage_delta_mwh=storage_delta,
		exported_mwh=0.0,
		residual_mwh=residual,
		tolerance_mwh=max(abs(produced) * tolerance_frac, 1e-6),
	)
	assert balance.exported_mwh == 0.0, "heat has no export term"
	return balance


__all__ = [
	"CARNOT_FORM",
	"KELVIN_OFFSET",
	"build_heat",
	"cop_from_temperature",
	"heat_demand_view",
	"heat_energy_balance",
	"heat_pump_view",
	"heat_pump_view_from_temperature",
	"resistive_backup_view",
	"thermal_storage_view",
]
