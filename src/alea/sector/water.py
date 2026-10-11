# SPDX-License-Identifier: MIT
"""Water: desalination as a flexible load, pumping, cooling constraints.

The water-energy nexus, from the energy side. Two facts drive the whole sector.

The first is that desalination is **dispatchable**: a reverse-osmosis plant can
run at part load, its product is storable in a tank, and its electricity demand
can therefore be moved to hours when power is cheap. Modelling it as a flat load
throws away the flexibility that makes it valuable, and modelling it as
infinitely flexible overstates it -- a plant has a minimum stable load below
which it cannot operate and a tank that fills up.

The second is that the specific energy of desalination is a **strong function of
feedwater salinity**. Seawater reverse osmosis costs 3-4 kWh/m³; brackish water
costs under 1. A single national figure applied to both is wrong by a factor of
four, and the error lands directly on the load. It is therefore a sourced
parameter with an explicit water type, not a constant.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector._util import annual_series, as_index, series_over, total_hours
from alea.sector.views import CouplingView, Parameter, Sector, SectorBuild

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

M3_PER_MWH_AT_1_KWH_PER_M3 = 1000.0
"""1000 m³ per MWh when the specific energy is 1 kWh/m³.

Named because the conversion between kWh/m³ (how the literature quotes specific
energy) and MWh/m³ (what the network needs) is exactly the kind of factor-of-1000
that survives review and changes a national water balance.
"""


class WaterType(StrEnum):
	"""Feedwater class. It is the dominant term in the specific energy."""

	SEAWATER = "seawater"
	BRACKISH = "brackish"
	REUSE = "reuse"


class CoolingType(StrEnum):
	"""How a thermal plant rejects heat, and therefore how much water it takes."""

	ONCE_THROUGH = "once-through"
	WET_TOWER = "wet-tower"
	DRY = "dry"


def desalination_view(
	bus_electricity: str,
	bus_water: str,
	*,
	water_type: WaterType,
	specific_energy_kwh_per_m3: float,
	specific_energy_source: str,
	capacity_m3_per_hour: float,
	minimum_load_fraction: float = 0.4,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "desalination",
) -> CouplingView:
	"""A desalination plant as a flexible ``Link`` with a minimum stable load.

	``minimum_load_fraction`` is what stops the optimiser from treating the plant
	as a perfectly flexible load. A reverse-osmosis train cannot run at 2% of
	rated output, and a model that lets it will schedule a thin sliver of
	production into every cheap hour and report a flexibility no plant provides.
	"""
	assert bus_electricity and bus_water, "desalination needs an electricity and a water bus"
	assert capacity_m3_per_hour > 0.0, "capacity must be positive"
	assert 0.0 <= minimum_load_fraction < 1.0, "minimum load fraction must be in [0, 1)"
	source = specific_energy_source.strip()
	if not source:
		raise ValueError(
			"desalination requires specific_energy_source; the specific energy "
			"is a function of feedwater salinity and varies by a factor of four "
			"across the three water types"
		)
	if specific_energy_kwh_per_m3 <= 0.0:
		raise ValueError(
			f"specific energy must be positive, got {specific_energy_kwh_per_m3}"
		)

	# The link's output is m³, its input is MWh, so its efficiency carries the
	# unit conversion. Doing it here rather than in a post-processing step keeps
	# the water bus in the same units as the product a utility actually reports.
	m3_per_mwh = M3_PER_MWH_AT_1_KWH_PER_M3 / specific_energy_kwh_per_m3

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.WATER,
		carrier="water",
		bus0=bus_electricity,
		bus1=bus_water,
		parameters={
			"efficiency": Parameter(
				value=m3_per_mwh,
				unit="m3/MWh_el",
				source=source,
				uncertainty=0.15,
				uncertainty_basis=(
					"plant-specific energy varies with membrane age, recovery "
					"ratio, temperature and pre-treatment"
				),
				notes=f"{specific_energy_kwh_per_m3:g} kWh/m3 for {water_type.value}",
			)
		},
		attributes={
			"p_nom": float(capacity_m3_per_hour),
			"p_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
			"p_min_pu": float(minimum_load_fraction),
		},
		source=source,
		notes=(
			f"{water_type.value} reverse osmosis; p_min_pu={minimum_load_fraction:g} "
			f"is the minimum stable load, without which the optimiser treats the "
			f"plant as perfectly flexible"
		),
	)
	assert view.parameters["efficiency"].value > 0.0
	return view


def water_storage_view(
	bus_water: str,
	*,
	e_nom_m3: float,
	standing_loss_per_hour: float = 0.0,
	standing_loss_source: str = "",
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "water_tank",
) -> CouplingView:
	"""Product water storage as a ``Store`` on the water bus.

	The tank is what makes desalination flexible in the first place: without
	somewhere to put the water, a plant's output must equal demand at every hour
	and the flexibility is nominal. A tank's loss is usually negligible but is
	still recorded, because a zero here is an assumption and not an absence.
	"""
	assert bus_water, "water storage needs a water bus"
	assert e_nom_m3 >= 0.0, "tank volume must be non-negative"
	assert 0.0 <= standing_loss_per_hour < 1.0, "standing loss must be in [0, 1)"

	parameters = {}
	if standing_loss_per_hour > 0.0:
		if not standing_loss_source.strip():
			raise ValueError("a non-zero standing loss requires its source")
		parameters["standing_loss"] = Parameter(
			value=standing_loss_per_hour,
			unit="per_hour",
			source=standing_loss_source,
		)

	view = CouplingView(
		asset="Store",
		name=name,
		sector=Sector.WATER,
		carrier="water",
		bus0=bus_water,
		parameters=parameters,
		attributes={
			"bus": bus_water,
			"e_nom": float(e_nom_m3),
			"e_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
		},
		source="05-layer2 §2.5 (product water storage)",
		notes="A tank is what makes the desalination load movable at all",
	)
	return view


def water_demand_view(
	bus_water: str,
	*,
	annual_demand_m3: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	profile: pd.Series | None = None,
	source: str = "05-layer2 §2.5 (municipal water demand)",
	name: str = "water_demand",
) -> CouplingView:
	"""Municipal and industrial water demand as a ``Load`` on the water bus."""
	assert bus_water, "water demand needs a water bus"
	assert annual_demand_m3 >= 0.0, "demand must be non-negative"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	scaled_m3 = annual_demand_m3 * (hours / 8760.0)
	p_set = (
		annual_series(scaled_m3, index, weights)
		if profile is None
		else series_over(profile.to_numpy(), index, "p_set")
	)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.WATER,
		carrier="water",
		bus0=bus_water,
		attributes={"bus": bus_water, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=f"{annual_demand_m3:,.0f} m3/year over the modelled horizon",
	)
	assert len(view.time_series["p_set"]) == len(index)
	return view


def pumping_view(
	bus_electricity: str,
	bus_water: str,
	*,
	head_m: float,
	efficiency: float,
	efficiency_source: str,
	capacity_m3_per_hour: float,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "water_pumping",
) -> CouplingView:
	"""Water conveyance pumping, as a ``Link`` from electricity to water.

	The hydraulic energy is computed from the head and the pump efficiency and
	converted to a specific energy, so the link's efficiency means the same
	thing as the desalination link's. Carrying the head instead of a bare
	specific energy keeps the physical reason for the number visible: a pumping
	load with a 400 m head is four times the energy of one with 100 m, and a
	table of specific energies hides that.
	"""
	assert bus_electricity and bus_water, "pumping needs an electricity and a water bus"
	assert head_m > 0.0, "head must be positive"
	assert 0.0 < efficiency <= 1.0, "pump efficiency must be in (0, 1]"
	assert capacity_m3_per_hour > 0.0, "capacity must be positive"
	source = efficiency_source.strip()
	if not source:
		raise ValueError("pumping requires an efficiency source")

	# Hydraulic power (W) = rho * g * Q * H. Per m³: rho*g*H joules, so the
	# specific energy in kWh/m³ is rho*g*H/3.6e6 / efficiency.
	gravity = 9.80665
	rho = 1000.0
	joules_per_m3 = rho * gravity * head_m
	specific_kwh_per_m3 = joules_per_m3 / 3.6e6 / efficiency
	m3_per_mwh = M3_PER_MWH_AT_1_KWH_PER_M3 / specific_kwh_per_m3

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.WATER,
		carrier="water",
		bus0=bus_electricity,
		bus1=bus_water,
		parameters={
			"efficiency": Parameter(
				value=m3_per_mwh,
				unit="m3/MWh_el",
				source=source,
				notes=(
					f"derived: {head_m:g} m head, rho=1000 kg/m3, g=9.80665 m/s2, "
					f"pump efficiency {efficiency:g} "
					f"-> {specific_kwh_per_m3:.3f} kWh/m3"
				),
			)
		},
		attributes={
			"p_nom": float(capacity_m3_per_hour),
			"p_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
			"p_min_pu": 0.0,
		},
		source=source,
		notes=f"Conveyance pumping against a {head_m:g} m head",
	)
	assert view.parameters["efficiency"].value > 0.0
	return view


def cooling_view(
	bus_electricity: str,
	bus_water: str,
	*,
	cooling_type: CoolingType,
	water_intensity_m3_per_mwh: float,
	water_intensity_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	name: str = "cooling",
) -> CouplingView:
	"""Thermal-plant cooling as a ``Link`` drawing water per unit generated.

	The link consumes water from the water bus at a rate fixed by the cooling
	type: a once-through plant withdraws far more than a wet tower but consumes
	little of it, while a dry plant consumes none and pays in efficiency instead
	(which belongs on the generator, not here).

	The intensity is a sourced parameter because the three cooling types differ
	by more than an order of magnitude, and a plant's cooling type is a design
	decision the model should not be allowed to make implicitly.
	"""
	assert bus_electricity and bus_water, "cooling needs an electricity and a water bus"
	assert p_nom >= 0.0, "capacity must be non-negative"
	source = water_intensity_source.strip()
	if not source:
		raise ValueError("cooling requires a water-intensity source")
	if water_intensity_m3_per_mwh < 0.0:
		raise ValueError("water intensity must be non-negative")

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.WATER,
		carrier="water",
		bus0=bus_water,
		bus1=bus_electricity,
		parameters={
			"efficiency": Parameter(
				value=water_intensity_m3_per_mwh,
				unit="m3/MWh_el",
				source=source,
				notes=f"{cooling_type.value} cooling",
			)
		},
		attributes={
			"p_nom": float(p_nom),
			"p_nom_extendable": bool(extendable),
			"p_min_pu": 0.0,
		},
		source=source,
		notes=(
			"Modelled as a water-to-electricity link so the constraint binds on "
			"generation; a dry-cooled plant's efficiency penalty is a property "
			"of the generator, not of this link"
		),
	)
	return view


def build_water(
	*,
	bus_electricity: str,
	bus_water: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	enabled: bool = False,
	water_type: WaterType = WaterType.SEAWATER,
	specific_energy_kwh_per_m3: float = 0.0,
	specific_energy_source: str = "",
	capacity_m3_per_hour: float = 0.0,
	minimum_load_fraction: float = 0.4,
	demand_m3_per_year: float = 0.0,
	demand_source: str = "",
	tank_m3: float = 0.0,
) -> SectorBuild:
	"""The water sector, as a set of views.

	Disabled by default. ``SectorConfig`` has no water switch -- the plan lists
	the sector but the config schema in 05-layer2 §4 does not carry it -- so the
	flag is a build argument rather than a config key, and a caller who wants
	the nexus modelled asks for it explicitly.
	"""
	assert bus_electricity, "water coupling needs an electricity bus"
	index = as_index(snapshots)

	if not enabled:
		return SectorBuild(
			sector=Sector.WATER,
			enabled=False,
			reason=(
				"water coupling is off; the sector has no key in SectorConfig and "
				"is requested explicitly at build time"
			),
		)
	if capacity_m3_per_hour <= 0.0:
		raise ValueError("the water sector needs a positive desalination capacity")
	if specific_energy_kwh_per_m3 <= 0.0:
		raise ValueError("the water sector needs a positive specific energy")

	views: list[CouplingView] = [
		desalination_view(
			bus_electricity,
			bus_water,
			water_type=water_type,
			specific_energy_kwh_per_m3=specific_energy_kwh_per_m3,
			specific_energy_source=specific_energy_source,
			capacity_m3_per_hour=capacity_m3_per_hour,
			minimum_load_fraction=minimum_load_fraction,
		)
	]
	if tank_m3 > 0.0:
		views.append(water_storage_view(bus_water, e_nom_m3=tank_m3))
	if demand_m3_per_year > 0.0:
		views.append(
			water_demand_view(
				bus_water,
				annual_demand_m3=demand_m3_per_year,
				snapshots=index,
				weights=weights,
				source=demand_source or "05-layer2 §2.5 (municipal water demand)",
			)
		)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.WATER, rows=rows, views=views, enabled=True)
	logger.info(
		"water.built",
		assets=len(rows),
		water_type=water_type.value,
		specific_energy_kwh_per_m3=specific_energy_kwh_per_m3,
	)
	assert build.rows, "an enabled water sector produced no assets"
	return build


def desalination_flexibility(
	network: pypsa.Network,
	*,
	link: str,
) -> dict[str, float]:
	"""How much the desalination load actually moved.

	The sector's entire justification is that this load is movable. If the
	plant's load duration curve is flat, either the flexibility is not being
	used or the minimum-load constraint has pinned it -- and the two have the
	same annual energy and completely different meanings. Reporting the load
	factor and the number of hours at minimum separates them.
	"""
	assert link in network.links.index, f"no link {link!r} in the network"
	if link not in network.links_t.p0.columns:
		raise ValueError(f"{link!r} was never dispatched; solve the network first")
	weights = network.snapshot_weightings["stores"].to_numpy(dtype=float)
	draw = (network.links_t.p0[link] * weights).to_numpy()
	rated = float(network.links.loc[link, "p_nom"])
	minimum = float(network.links.loc[link, "p_min_pu"]) * rated
	hours = float(weights.sum())
	mean = float(draw.sum() / hours) if hours > 0 else 0.0
	at_minimum = float(weights[draw <= minimum + 1e-6].sum())
	result = {
		"energy_mwh": float(draw.sum()),
		"mean_mw": mean,
		"peak_mw": float(draw.max()) if draw.size else 0.0,
		"load_factor": mean / rated if rated > 0 else 0.0,
		"hours_at_minimum": at_minimum,
	}
	assert 0.0 <= result["load_factor"] <= 1.0 + 1e-6, "load factor outside [0, 1]"
	return result


__all__ = [
	"M3_PER_MWH_AT_1_KWH_PER_M3",
	"CoolingType",
	"WaterType",
	"build_water",
	"cooling_view",
	"desalination_flexibility",
	"desalination_view",
	"pumping_view",
	"water_demand_view",
	"water_storage_view",
]
