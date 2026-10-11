# SPDX-License-Identifier: MIT
"""Hydrogen: electrolysis, storage, export, industrial demand.

The efficiency figure is the whole sector's load-bearing assumption. An
electrolyser spans 60-70% LHV and system efficiency is lower than stack
efficiency, so a hydrogen result is only as defensible as the citation behind
its efficiency. ``SectorConfig`` already refuses ``hydrogen_enabled`` without
``electrolyser_efficiency_source``; this module refuses it again at the point
of use, because a caller that builds an electrolyser without a config is a
caller that would otherwise bypass the validator.

No default efficiency is offered. A default of 0.7 that nobody can trace is
precisely the failure the plan names (05-layer2 §2.1), and a default is worse
than a missing value because it produces an answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from alea._core import kernels
from alea.config.models import SectorConfig
from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector._util import (
	H2_LHV_MWH_PER_KG,
	annual_series,
	as_index,
	total_hours,
	twh_per_year_to_mwh,
	weighted_energy,
)
from alea.sector.views import (
	CouplingView,
	LinkRow,
	MassBalance,
	Parameter,
	Sector,
	SectorBuild,
)

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

ELECTROLYSIS_SOURCE = "05-layer2 §2.1"
"""The plan clause that fixes the electrolyser's representation."""


def _require_efficiency(config: SectorConfig) -> tuple[float, str]:
	"""The electrolyser efficiency and its source, or a refusal.

	Duplicated deliberately from ``SectorConfig._physical_parameters_are_sourced``:
	that validator runs when a ``SectorConfig`` is constructed, and a function
	that accepts a bare float would never construct one.
	"""
	efficiency = config.electrolyser_efficiency_lhv
	source = config.electrolyser_efficiency_source.strip()
	if not source:
		raise ValueError(
			"electrolysis requires electrolyser_efficiency_source; an "
			"electrolyser efficiency nobody can trace is how a hydrogen result "
			"becomes indefensible (05-layer2 §2.1)"
		)
	if not 0.0 < efficiency <= 1.0:
		raise ValueError(f"electrolyser_efficiency_lhv must be in (0, 1], got {efficiency}")
	return efficiency, source


def electrolysis_view(
	bus_electricity: str,
	bus_hydrogen: str,
	*,
	efficiency_lhv: float,
	efficiency_source: str,
	p_nom: float,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "electrolysis",
) -> CouplingView:
	"""An electrolyser as a ``Link`` from the electricity bus to the H₂ bus.

	The link's ``efficiency`` is the LHV efficiency, so its output is in
	MWh(H₂, LHV) and the H₂ bus carries energy, not mass. Mass is converted only
	at the point a mass is actually required -- an export contract in kg or a
	vehicle tank -- which keeps one unit convention across the network instead
	of two.
	"""
	assert bus_electricity, "electrolysis needs an electricity bus"
	assert bus_hydrogen, "electrolysis needs a hydrogen bus"
	assert p_nom >= 0.0, "p_nom must be non-negative"

	source = efficiency_source.strip()
	if not source:
		raise ValueError("electrolysis requires efficiency_source")
	if not 0.0 < efficiency_lhv <= 1.0:
		raise ValueError(f"efficiency_lhv must be in (0, 1], got {efficiency_lhv}")

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.HYDROGEN,
		carrier=Carrier.ELECTROLYSIS.value,
		bus0=bus_electricity,
		bus1=bus_hydrogen,
		parameters={
			"efficiency": Parameter(
				value=efficiency_lhv,
				unit="MWh_H2/MWh_el",
				source=source,
				uncertainty=0.05,
				uncertainty_basis=(
					"IRENA 2024 electrolyser survey spans 60-70% LHV; the "
					"midpoint is uncertain by roughly a third of that range"
				),
			)
		},
		attributes={
			"p_nom": float(p_nom),
			"p_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
			"p_min_pu": 0.0,
		},
		source=source,
		notes="Electrolyser is a flexible load: p_min_pu=0 lets it follow VRE.",
	)
	assert view.asset == "Link"
	return view


def storage_view(
	bus_hydrogen: str,
	*,
	e_nom: float,
	standing_loss_per_hour: float,
	standing_loss_source: str,
	extendable: bool = False,
	capital_cost: float = 0.0,
	name: str = "h2_storage",
	cavern: bool = False,
) -> CouplingView:
	"""Hydrogen storage as a ``Store`` on the H₂ bus.

	``standing_loss_per_hour`` is a physical parameter and is sourced. A salt
	cavern loses on the order of 0.1%/day; a pressurised vessel loses far less
	but costs far more. Setting it to zero makes storage free in the only way
	that matters over a year, and the optimiser will then hold a season's
	production in a cavern it would never build.
	"""
	assert bus_hydrogen, "storage needs a hydrogen bus"
	assert e_nom >= 0.0, "e_nom must be non-negative"
	assert 0.0 <= standing_loss_per_hour < 1.0, "standing loss must be in [0, 1)"

	source = standing_loss_source.strip()
	if not source:
		raise ValueError(
			"hydrogen storage requires standing_loss_source; an unsourced "
			"standing loss is an unsourced seasonality assumption"
		)

	view = CouplingView(
		asset="Store",
		name=name,
		sector=Sector.HYDROGEN,
		carrier=Carrier.H2.value,
		bus0=bus_hydrogen,
		parameters={
			"standing_loss": Parameter(
				value=standing_loss_per_hour,
				unit="per_hour",
				source=source,
				uncertainty=0.5,
				uncertainty_basis=(
					"cavern cycling losses depend on geology and cycle frequency; "
					"published figures vary by a factor of two"
				),
			)
		},
		attributes={
			"bus": bus_hydrogen,
			"e_nom": float(e_nom),
			"e_nom_extendable": bool(extendable),
			"capital_cost": float(capital_cost),
			"e_cyclic": False,
		},
		source=source,
		notes="Salt cavern" if cavern else "Pressurised vessel",
	)
	assert view.asset == "Store"
	return view


def export_view(
	bus_hydrogen: str,
	*,
	volume_twh_per_year: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	name: str = "h2_export",
) -> CouplingView:
	"""A port export obligation as a fixed ``Load`` on the H₂ bus.

	The volume is annual and the network is not, so the obligation is scaled to
	the modelled horizon. A 100 TWh/year contract modelled on a two-week
	representative period is a load of ``100e6 / 8760`` MW for the hours that
	period represents -- not 100 TWh crammed into two weeks, which would be a
	demand no system could meet and would read as "hydrogen export is
	infeasible".
	"""
	assert bus_hydrogen, "export needs a hydrogen bus"
	assert volume_twh_per_year >= 0.0, "export volume must be non-negative"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	obligation_mwh = twh_per_year_to_mwh(volume_twh_per_year, hours)
	p_set = annual_series(obligation_mwh, index, weights)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.HYDROGEN,
		carrier=Carrier.H2.value,
		bus0=bus_hydrogen,
		attributes={"bus": bus_hydrogen, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source="05-layer2 §2.1 (export at a port bus)",
		notes=(
			f"{volume_twh_per_year:g} TWh/year over {hours:g} modelled hours "
			f"= {obligation_mwh:,.0f} MWh"
		),
	)
	assert view.time_series["p_set"], "export must carry a series, not a scalar"
	return view


def demand_view(
	bus_hydrogen: str,
	*,
	annual_demand_twh: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	source: str,
	name: str = "h2_industry",
	flat: bool = True,
) -> CouplingView:
	"""Industrial hydrogen demand (ammonia/methanol feedstock) as a ``Load``.

	``flat`` is stated rather than assumed: a flat industrial load is a
	simplification, and the plan requires simplifications to be recorded. A
	caller with a real load shape passes ``flat=False`` and supplies it through
	the returned view's ``time_series``.
	"""
	assert bus_hydrogen, "demand needs a hydrogen bus"
	assert annual_demand_twh >= 0.0, "demand must be non-negative"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	demand_mwh = twh_per_year_to_mwh(annual_demand_twh, hours)
	p_set = annual_series(demand_mwh, index, weights)
	if not flat:
		raise NotImplementedError(
			"a shaped industrial load needs a measured profile; supply it via "
			"the returned view rather than requesting an invented one"
		)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.HYDROGEN,
		carrier=Carrier.H2.value,
		bus0=bus_hydrogen,
		attributes={"bus": bus_hydrogen, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=f"{annual_demand_twh:g} TWh/year, flat profile (simplification recorded)",
	)
	assert len(view.time_series["p_set"]) == len(index)
	return view


def build_hydrogen(
	config: SectorConfig,
	*,
	bus_electricity: str,
	bus_hydrogen: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	electrolyser_p_nom: float = 0.0,
	storage_e_nom: float = 0.0,
	standing_loss_per_hour: float = 0.0,
	standing_loss_source: str = "",
	industry_demand_twh: float = 0.0,
) -> SectorBuild:
	"""The hydrogen sector, as a set of views.

	Storage is built only when a capacity is given. A zero-capacity store is not
	a smaller store, it is a constraint that hydrogen cannot be held at all, and
	silently adding one would make an export obligation infeasible for a reason
	that appears nowhere in the configuration.
	"""
	assert bus_electricity, "hydrogen coupling needs an electricity bus"
	index = as_index(snapshots)

	if not config.hydrogen_enabled:
		return SectorBuild(
			sector=Sector.HYDROGEN,
			enabled=False,
			reason="sector.hydrogen_enabled is false",
		)

	efficiency, efficiency_source = _require_efficiency(config)
	views: list[CouplingView] = [
		electrolysis_view(
			bus_electricity,
			bus_hydrogen,
			efficiency_lhv=efficiency,
			efficiency_source=efficiency_source,
			p_nom=electrolyser_p_nom,
			extendable=electrolyser_p_nom <= 0.0,
		)
	]

	if storage_e_nom > 0.0:
		views.append(
			storage_view(
				bus_hydrogen,
				e_nom=storage_e_nom,
				standing_loss_per_hour=standing_loss_per_hour,
				standing_loss_source=standing_loss_source or efficiency_source,
			)
		)
	if config.hydrogen_export_twh_per_year > 0.0:
		views.append(
			export_view(
				bus_hydrogen,
				volume_twh_per_year=config.hydrogen_export_twh_per_year,
				snapshots=index,
				weights=weights,
			)
		)
	if industry_demand_twh > 0.0:
		views.append(
			demand_view(
				bus_hydrogen,
				annual_demand_twh=industry_demand_twh,
				snapshots=index,
				weights=weights,
				source=ELECTROLYSIS_SOURCE,
			)
		)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.HYDROGEN, rows=rows, views=views, enabled=True)
	logger.info(
		"hydrogen.built",
		assets=len(rows),
		efficiency_lhv=efficiency,
		efficiency_source=efficiency_source,
		export_twh=config.hydrogen_export_twh_per_year,
	)
	assert all(row.parameter_sources for row in rows if row.values.get("efficiency"))
	return build


def h2_mass_balance(
	network: pypsa.Network,
	*,
	bus_hydrogen: str,
	export_loads: list[str] | None = None,
	tolerance_frac: float = 1e-4,
) -> MassBalance:
	"""Conservation of hydrogen across the H₂ bus.

	``produced`` is what electrolysers and any H₂ generator delivered to the bus;
	``consumed`` is what loads took; ``storage_delta`` is net energy into stores;
	``exported`` is the subset of load that left the system. Every term is read
	from the solved network rather than recomputed, so the balance measures the
	solve and not the model that produced it.

	The unit is MWh(LHV). A mass balance in kg is the same equation divided by
	the LHV, so stating it in energy loses nothing and avoids a second constant
	appearing in the accounting.
	"""
	assert bus_hydrogen, "balance needs a hydrogen bus"
	weights = network.snapshot_weightings["stores"].to_numpy(dtype=float)
	export_names = set(export_loads or [])

	produced = 0.0
	if len(network.links) and "p1" in network.links_t:
		to_bus = network.links[network.links["bus1"] == bus_hydrogen].index
		if len(to_bus):
			# A link's p1 is negative when it injects into bus1 (established by
			# solving a probe network), so the energy delivered is -p1. Summing
			# p1 directly reports production as a negative quantity and the
			# balance closes on a sign error that looks like a large residual.
			produced -= weighted_energy(network.links_t.p1[to_bus], weights)
	if len(network.generators) and "p" in network.generators_t:
		gens = network.generators[network.generators["bus"] == bus_hydrogen].index
		if len(gens):
			produced += weighted_energy(network.generators_t.p[gens], weights)

	consumed = 0.0
	exported = 0.0
	if len(network.loads) and "p" in network.loads_t:
		loads = network.loads[network.loads["bus"] == bus_hydrogen].index
		if len(loads):
			consumed = weighted_energy(network.loads_t.p[loads], weights)
			exports = [name for name in loads if name in export_names]
			if exports:
				exported = weighted_energy(network.loads_t.p[exports], weights)
	if len(network.links) and "p0" in network.links_t:
		from_bus = network.links[network.links["bus0"] == bus_hydrogen].index
		if len(from_bus):
			consumed += weighted_energy(network.links_t.p0[from_bus], weights)

	storage_delta = 0.0
	if len(network.stores) and "e" in network.stores_t:
		stores = network.stores[network.stores["bus"] == bus_hydrogen].index
		if len(stores):
			energy = network.stores_t.e[stores]
			# Net energy *into* the store over the horizon, an energy already, so
			# no snapshot weighting applies to it.
			storage_delta = float((energy.iloc[-1] - energy.iloc[0]).sum())
	if len(network.storage_units) and "p" in network.storage_units_t:
		units = network.storage_units[network.storage_units["bus"] == bus_hydrogen].index
		if len(units):
			# Positive p is discharge, i.e. energy out of the store, so the sign
			# is flipped to keep storage_delta as energy into storage.
			storage_delta -= weighted_energy(network.storage_units_t.p[units], weights)

	residual = produced - consumed - storage_delta - exported
	tolerance = max(abs(produced) * tolerance_frac, 1e-6)
	balance = MassBalance(
		carrier=Carrier.H2.value,
		produced_mwh=produced,
		consumed_mwh=consumed,
		storage_delta_mwh=storage_delta,
		exported_mwh=exported,
		residual_mwh=residual,
		tolerance_mwh=tolerance,
	)
	logger.info(
		"hydrogen.balance",
		produced_mwh=round(produced, 3),
		consumed_mwh=round(consumed, 3),
		residual_mwh=round(residual, 6),
		closes=balance.closes,
	)
	return balance


def h2_kg_to_mwh(kg: float) -> float:
	"""Mass to LHV energy, for an export contract written in kg."""
	assert kg >= 0.0, "mass must be non-negative"
	return float(kg) * H2_LHV_MWH_PER_KG


__all__ = [
	"ELECTROLYSIS_SOURCE",
	"build_hydrogen",
	"demand_view",
	"electrolysis_view",
	"export_view",
	"h2_kg_to_mwh",
	"h2_mass_balance",
	"storage_view",
]
