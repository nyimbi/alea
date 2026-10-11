# SPDX-License-Identifier: MIT
"""Transport: EV smart charging, V2G, hydrogen vehicles.

The fleet is modelled as one aggregate battery per bus, not one store per car.
An hourly national model does not need 400,000 vehicles to know that a fleet of
400,000 holds 24 GWh and can absorb 900 MW when plugged in; it needs those two
numbers and the fraction plugged in at each hour.

**V2G without a degradation cost is free storage.** The optimiser will discharge
the fleet to zero in every expensive hour and recharge it in every cheap one,
and the model will report that this is cheap. No real fleet does it, because
every cycle costs battery life. The degradation cost is what converts the
physical wear into a price the optimiser must pay, and it is required rather
than defaulted -- ``SectorConfig`` refuses ``v2g_enabled`` with a zero cost, and
so does this module. A default would defeat the point: the check exists to make
the number a decision, and a default is the opposite of a decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from alea.config.models import SectorConfig
from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector._util import annual_series, as_index, series_over, total_hours, twh_per_year_to_mwh
from alea.sector.views import CouplingView, Parameter, Sector, SectorBuild

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

DEGRADATION_SOURCE = "05-layer2 §2.3 (V2G degradation cost)"
"""The clause that makes the degradation cost mandatory."""


def _require_degradation(config: SectorConfig) -> float:
	"""The V2G degradation cost, or a refusal.

	Duplicated from ``SectorConfig._v2g_has_a_cost`` on purpose: a function that
	takes a bare float never constructs a ``SectorConfig``, so a caller could
	otherwise reach the network with free V2G and never touch the validator.
	"""
	if not config.v2g_enabled:
		return 0.0
	cost = config.v2g_degradation_usd_per_mwh
	if cost <= 0.0:
		raise ValueError(
			"v2g_enabled requires v2g_degradation_usd_per_mwh > 0; free storage "
			"is not a modelling result, the optimiser will use it without limit, "
			"and no real fleet provides it (05-layer2 §2.3)"
		)
	return cost


def ev_fleet_view(
	bus_ev: str,
	*,
	battery_capacity_mwh: float,
	name: str = "ev_fleet",
	initial_soc_frac: float = 0.5,
) -> CouplingView:
	"""The fleet's aggregate battery as a ``Store`` on a dedicated EV bus.

	The EV bus is deliberately not the electricity bus. A store directly on the
	electricity bus would let the fleet discharge into the grid with no
	conversion loss and no degradation charge -- which is V2G with none of its
	costs, arrived at by accident rather than by config.
	"""
	assert bus_ev, "the fleet store needs an EV bus"
	assert battery_capacity_mwh > 0.0, "fleet capacity must be positive"
	assert 0.0 <= initial_soc_frac <= 1.0, "initial state of charge must be in [0, 1]"

	view = CouplingView(
		asset="Store",
		name=name,
		sector=Sector.TRANSPORT,
		carrier=Carrier.BATTERY.value,
		bus0=bus_ev,
		attributes={
			"bus": bus_ev,
			"e_nom": float(battery_capacity_mwh),
			"e_nom_extendable": False,
			"e_initial": float(battery_capacity_mwh) * initial_soc_frac,
			"e_cyclic": False,
		},
		source="05-layer2 §2.3 (EV fleet as storage)",
		notes=(
			f"{battery_capacity_mwh:,.0f} MWh aggregate fleet battery; the "
			f"fleet is one store because an hourly national model needs its "
			f"capacity and availability, not its vehicle count"
		),
	)
	return view


def smart_charging_view(
	bus_electricity: str,
	bus_ev: str,
	*,
	charger_power_mw: float,
	charger_efficiency: float,
	charger_efficiency_source: str,
	availability: pd.Series,
	availability_source: str,
	name: str = "ev_charger",
) -> CouplingView:
	"""Grid-to-vehicle charging as a ``Link`` gated by an availability profile.

	``availability`` is the fraction of the fleet's rated charger power that is
	connected at each hour. It is the profile the plan requires for smart
	charging (05-layer2 §2.3), and it is what makes the load flexible rather
	than a flat block: a fleet is a load in the evening and storage at midday,
	and the difference is entirely in this series.
	"""
	assert bus_electricity and bus_ev, "charging needs both an electricity and an EV bus"
	assert charger_power_mw >= 0.0, "charger power must be non-negative"

	index = as_index(pd.DatetimeIndex(availability.index))
	profile = series_over(availability.to_numpy(), index, "p_max_pu")
	if not ((profile >= 0.0) & (profile <= 1.0)).all():
		raise ValueError(
			"availability is a fraction of rated charger power and must lie in "
			f"[0, 1]; got range [{profile.min()}, {profile.max()}]"
		)
	if not charger_efficiency_source.strip() or not availability_source.strip():
		raise ValueError(
			"charging requires both a charger-efficiency source and an "
			"availability-profile source"
		)

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.TRANSPORT,
		carrier=Carrier.BATTERY.value,
		bus0=bus_electricity,
		bus1=bus_ev,
		parameters={
			"efficiency": Parameter(
				value=charger_efficiency,
				unit="MWh_batt/MWh_el",
				source=charger_efficiency_source,
			),
			"p_max_pu": Parameter(
				value=float(profile.mean()),
				unit="fraction",
				source=availability_source,
				notes="Time series overrides this scalar.",
			),
		},
		attributes={
			"p_nom": float(charger_power_mw),
			"p_nom_extendable": False,
			"p_min_pu": 0.0,
		},
		time_series={"p_max_pu": profile.to_list()},
		source=availability_source,
		notes="Smart charging: unidirectional, availability-gated.",
	)
	assert len(view.time_series["p_max_pu"]) == len(index)
	return view


def v2g_view(
	bus_electricity: str,
	bus_ev: str,
	*,
	discharge_power_mw: float,
	inverter_efficiency: float,
	inverter_efficiency_source: str,
	degradation_usd_per_mwh: float,
	availability: pd.Series,
	availability_source: str,
	name: str = "ev_v2g",
) -> CouplingView:
	"""Vehicle-to-grid discharge as a ``Link`` carrying a degradation charge.

	The degradation cost lands on ``marginal_cost``, which PyPSA applies to the
	link's ``p0`` -- the energy drawn out of the fleet battery. That is the right
	base: battery wear scales with energy cycled through the cell, not with the
	energy delivered after inverter losses, so charging the cost on the output
	would understate it by the inverter efficiency.

	This function refuses a zero or negative degradation cost even though the
	config validator also does. A caller reaching this function directly has not
	constructed a ``SectorConfig``, and the guarantee has to hold at the point
	the asset is created or it does not hold.
	"""
	assert bus_electricity and bus_ev, "V2G needs both an electricity and an EV bus"
	assert discharge_power_mw >= 0.0, "discharge power must be non-negative"
	if degradation_usd_per_mwh <= 0.0:
		raise ValueError(
			f"V2G degradation cost must be > 0, got {degradation_usd_per_mwh}; "
			f"free storage is not a modelling result (05-layer2 §2.3)"
		)
	if not 0.0 < inverter_efficiency <= 1.0:
		raise ValueError(f"inverter efficiency must be in (0, 1], got {inverter_efficiency}")

	index = as_index(pd.DatetimeIndex(availability.index))
	profile = series_over(availability.to_numpy(), index, "p_max_pu")
	if not ((profile >= 0.0) & (profile <= 1.0)).all():
		raise ValueError("V2G availability must lie in [0, 1]")

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.TRANSPORT,
		carrier=Carrier.BATTERY.value,
		bus0=bus_ev,
		bus1=bus_electricity,
		parameters={
			"efficiency": Parameter(
				value=inverter_efficiency,
				unit="MWh_el/MWh_batt",
				source=inverter_efficiency_source,
			),
			"degradation_cost": Parameter(
				value=degradation_usd_per_mwh,
				unit="USD/MWh_batt",
				source=DEGRADATION_SOURCE,
				uncertainty=0.5,
				uncertainty_basis=(
					"battery degradation cost depends on chemistry, cycle depth "
					"and pack replacement price; published values span a factor "
					"of two"
				),
				notes="Charged on p0 (energy cycled through the cell).",
			),
			"p_max_pu": Parameter(
				value=float(profile.mean()),
				unit="fraction",
				source=availability_source,
				notes="Time series overrides this scalar.",
			),
		},
		attributes={
			"p_nom": float(discharge_power_mw),
			"p_nom_extendable": False,
			"p_min_pu": 0.0,
			"marginal_cost": float(degradation_usd_per_mwh),
		},
		time_series={"p_max_pu": profile.to_list()},
		source=DEGRADATION_SOURCE,
		notes=(
			f"Bidirectional: discharge constrained by a "
			f"{degradation_usd_per_mwh:g} USD/MWh degradation cost"
		),
	)
	assert view.parameters["degradation_cost"].value > 0.0
	return view


def ev_driving_load_view(
	bus_ev: str,
	*,
	annual_demand_mwh: float,
	consumption_mwh_per_km: float,
	consumption_source: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	profile: pd.Series | None = None,
	name: str = "ev_driving",
) -> CouplingView:
	"""Energy that leaves the fleet to drive, as a ``Load`` on the EV bus.

	Without this the fleet battery is pure storage: it charges and discharges
	and nothing is ever consumed, so the model can meet a V2G discharge
	obligation with a battery that never needs refilling. The driving load is
	what closes the fleet's energy account.

	``annual_demand_mwh`` is stated in energy because that is what the load
	places on the bus; ``consumption_mwh_per_km`` is carried as a parameter so
	the distance behind the energy stays visible and sourced. A caller holding a
	distance computes ``distance_km * consumption_mwh_per_km`` and passes both.
	"""
	assert bus_ev, "driving demand needs an EV bus"
	assert annual_demand_mwh >= 0.0, "demand must be non-negative"
	assert consumption_mwh_per_km > 0.0, "consumption must be positive"
	source = consumption_source.strip()
	if not source:
		raise ValueError("driving demand requires a consumption source")

	index = as_index(snapshots)
	hours = total_hours(index, weights)
	scaled_mwh = annual_demand_mwh * (hours / 8760.0)
	p_set = (
		annual_series(scaled_mwh, index, weights)
		if profile is None
		else series_over(profile.to_numpy(), index, "p_set")
	)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.TRANSPORT,
		carrier=Carrier.BATTERY.value,
		bus0=bus_ev,
		parameters={
			"specific_energy": Parameter(
				value=consumption_mwh_per_km,
				unit="MWh/km",
				source=source,
			)
		},
		attributes={"bus": bus_ev, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=f"{scaled_mwh:,.0f} MWh over the modelled horizon",
	)
	assert len(view.time_series["p_set"]) == len(index)
	return view


def h2_vehicle_demand_view(
	bus_hydrogen: str,
	*,
	annual_demand_twh: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	source: str = "05-layer2 §2.3 (hydrogen vehicles)",
	name: str = "h2_vehicles",
) -> CouplingView:
	"""Hydrogen vehicle fuelling as a ``Load`` on the H₂ bus.

	Hydrogen transport competes with electrified transport for the same journey,
	and the model can only show which wins if both are present. Leaving it out
	does not make it cheap, it makes it invisible.
	"""
	assert bus_hydrogen, "hydrogen vehicles need an H₂ bus"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	p_set = annual_series(twh_per_year_to_mwh(annual_demand_twh, hours), index, weights)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.TRANSPORT,
		carrier=Carrier.H2.value,
		bus0=bus_hydrogen,
		attributes={"bus": bus_hydrogen, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=f"{annual_demand_twh:g} TWh/year, flat profile (simplification recorded)",
	)
	return view


def build_transport(
	config: SectorConfig,
	*,
	bus_electricity: str,
	bus_ev: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	fleet_capacity_mwh: float = 0.0,
	charger_power_mw: float = 0.0,
	charger_efficiency: float = 0.92,
	charger_efficiency_source: str = "",
	availability: pd.Series | None = None,
	availability_source: str = "",
	driving_demand_mwh: float = 0.0,
	driving_consumption_mwh_per_km: float = 0.0,
	driving_demand_source: str = "",
	bus_hydrogen: str | None = None,
	h2_vehicle_demand_twh: float = 0.0,
) -> SectorBuild:
	"""The transport sector, as a set of views.

	V2G is added only when ``config.v2g_enabled``; when it is, the degradation
	cost comes from the config and is required to be positive. The fleet store
	and the driving load are added whenever a fleet is configured, because a
	fleet without a driving load is free storage under a different name.
	"""
	assert bus_electricity, "transport coupling needs an electricity bus"
	index = as_index(snapshots)

	if not (config.ev_smart_charging or config.v2g_enabled):
		return SectorBuild(
			sector=Sector.TRANSPORT,
			enabled=False,
			reason="sector.ev_smart_charging and sector.v2g_enabled are both false",
		)

	views: list[CouplingView] = []
	if fleet_capacity_mwh > 0.0:
		views.append(ev_fleet_view(bus_ev, battery_capacity_mwh=fleet_capacity_mwh))
	if availability is None or not availability_source.strip():
		raise ValueError(
			"transport coupling needs an availability profile and its source; a "
			"fleet modelled as always fully plugged in is a fleet that does not "
			"exist (05-layer2 §2.3)"
		)

	if config.ev_smart_charging:
		views.append(
			smart_charging_view(
				bus_electricity,
				bus_ev,
				charger_power_mw=charger_power_mw,
				charger_efficiency=charger_efficiency,
				charger_efficiency_source=charger_efficiency_source,
				availability=availability,
				availability_source=availability_source,
			)
		)
	if config.v2g_enabled:
		degradation = _require_degradation(config)
		views.append(
			v2g_view(
				bus_electricity,
				bus_ev,
				discharge_power_mw=charger_power_mw,
				inverter_efficiency=charger_efficiency,
				inverter_efficiency_source=charger_efficiency_source,
				degradation_usd_per_mwh=degradation,
				availability=availability,
				availability_source=availability_source,
			)
		)
	if driving_demand_mwh > 0.0:
		if not driving_demand_source.strip() or driving_consumption_mwh_per_km <= 0.0:
			raise ValueError(
				"a driving load requires both its consumption source and a "
				"consumption rate; the energy alone hides the distance behind it"
			)
		views.append(
			ev_driving_load_view(
				bus_ev,
				annual_demand_mwh=driving_demand_mwh,
				consumption_mwh_per_km=driving_consumption_mwh_per_km,
				consumption_source=driving_demand_source,
				snapshots=index,
				weights=weights,
			)
		)
	if bus_hydrogen is not None and h2_vehicle_demand_twh > 0.0:
		views.append(
			h2_vehicle_demand_view(
				bus_hydrogen,
				annual_demand_twh=h2_vehicle_demand_twh,
				snapshots=index,
				weights=weights,
			)
		)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.TRANSPORT, rows=rows, views=views, enabled=True)
	logger.info(
		"transport.built",
		assets=len(rows),
		v2g=config.v2g_enabled,
		degradation_usd_per_mwh=config.v2g_degradation_usd_per_mwh,
	)
	assert not config.v2g_enabled or config.v2g_degradation_usd_per_mwh > 0.0
	return build


def v2g_cycles(network: pypsa.Network, *, link: str, store: str) -> float:
	"""Equivalent full cycles the fleet performed through one V2G link.

	Reported alongside any V2G result because it is the number that tells a
	reader whether the model is describing a fleet or a battery. A result
	claiming large V2G revenue at four cycles per day is a result about a
	battery that happens to be shaped like a car.

	``store`` is named rather than inferred: taking whichever store happens to
	be first would silently report cycles per unit of the wrong capacity the
	moment a second store exists on the network.
	"""
	assert link in network.links.index, f"no link {link!r} in the network"
	assert store in network.stores.index, f"no store {store!r} in the network"
	if link not in network.links_t.p0.columns:
		raise ValueError(f"{link!r} was never dispatched; solve the network first")
	weights = network.snapshot_weightings["stores"].to_numpy(dtype=float)
	discharged = float((network.links_t.p0[link] * weights).to_numpy().sum())
	capacity = float(network.stores.loc[store, "e_nom"])
	if capacity <= 0.0:
		raise ValueError(f"store {store!r} has no energy capacity; cycles are undefined")
	cycles = discharged / capacity
	assert cycles >= -1e-9, "a V2G link cannot have discharged a negative energy"
	return cycles


__all__ = [
	"DEGRADATION_SOURCE",
	"build_transport",
	"ev_driving_load_view",
	"ev_fleet_view",
	"h2_vehicle_demand_view",
	"smart_charging_view",
	"v2g_cycles",
	"v2g_view",
]
