# SPDX-License-Identifier: MIT
"""Industry: steel, cement, chemicals.

These are the largest single modelling assumptions in Layer 2. Whether Kenyan
steel is decarbonised by hydrogen direct reduction, by scrap electric-arc
furnace, or not at all depends on scrap availability, ore quality, gas price and
industrial policy -- none of which this platform decides. What it can do is make
the assumption explicit and sourced, so a result is a consequence of a stated
pathway rather than of a number that appeared in a table.

Every link therefore carries two sources: one for the conversion efficiency,
one for the pathway itself. The pathway source is the more important of the two
-- an efficiency that is 3% wrong changes the answer, but a pathway that is the
wrong pathway changes the question.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from alea.config.models import SectorConfig
from alea.logging import get_logger
from alea.registry import Carrier
from alea.sector._util import annual_series, as_index, total_hours, twh_per_year_to_mwh
from alea.sector.views import CouplingView, Parameter, Sector, SectorBuild

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

STEEL_H2_DRI = "H2-DRI"
STEEL_SCRAP_EAF = "scrap-EAF"
CEMENT_CCUS = "cement-CCUS"
AMMONIA = "green-ammonia"
METHANOL = "green-methanol"

PATHWAY_SOURCE_REQUIRED = (
	"an industrial pathway is contested and country-specific; the link records "
	"the source of the pathway, not only of its efficiency (05-layer2 §2.4)"
)


def _industrial_link(
	*,
	name: str,
	bus0: str,
	bus1: str,
	carrier: str,
	efficiency: float,
	efficiency_unit: str,
	efficiency_source: str,
	pathway_source: str,
	p_nom: float,
	extendable: bool,
	capital_cost: float = 0.0,
	bus2: str = "",
	efficiency2: float | None = None,
	efficiency2_unit: str = "",
	efficiency2_source: str = "",
	notes: str = "",
) -> CouplingView:
	"""One industrial conversion process, with its pathway named and sourced.

	The optional second output carries the co-product -- the CO₂ stream a
	cement plant captures, or the heat a DRI shaft rejects. Leaving it out would
	be simpler and would also mean the model cannot see that CCUS has a cost and
	an energy penalty, only that a plant produces the same cement.
	"""
	assert name, "an industrial link needs a name"
	assert bus0 and bus1, "an industrial link needs both an input and an output bus"
	if not pathway_source.strip():
		raise ValueError(f"{name}: {PATHWAY_SOURCE_REQUIRED}")
	if not efficiency_source.strip():
		raise ValueError(f"{name}: the conversion efficiency requires its own source")
	if not 0.0 < efficiency <= 1.0:
		raise ValueError(f"{name}: efficiency must be in (0, 1], got {efficiency}")
	if not extendable and p_nom <= 0.0:
		raise ValueError(
			f"{name}: a non-extendable link with p_nom={p_nom} can carry no flow, "
			f"so the product it delivers is unreachable and the model is "
			f"infeasible the moment anything demands it. Give it a capacity, or "
			f"make it extendable."
		)

	parameters = {
		"efficiency": Parameter(
			value=efficiency,
			unit=efficiency_unit,
			source=efficiency_source,
			uncertainty=0.1,
			uncertainty_basis=(
				"industrial conversion efficiencies vary with plant vintage, "
				"feedstock quality and process integration"
			),
		)
	}
	attributes: dict[str, object] = {
		"p_nom": float(p_nom),
		"p_nom_extendable": bool(extendable),
		"capital_cost": float(capital_cost),
		"p_min_pu": 0.0,
	}
	if bus2 and efficiency2 is not None:
		attributes["bus2"] = bus2
		parameters["efficiency2"] = Parameter(
			value=efficiency2,
			unit=efficiency2_unit or "MWh_out/MWh_in",
			source=efficiency2_source or efficiency_source,
		)

	view = CouplingView(
		asset="Link",
		name=name,
		sector=Sector.INDUSTRY,
		carrier=carrier,
		bus0=bus0,
		bus1=bus1,
		bus2=bus2,
		parameters=parameters,
		attributes=attributes,
		source=pathway_source,
		notes=notes,
	)
	assert view.parameters["efficiency"].source == efficiency_source
	return view


def steel_h2_dri_view(
	bus_electricity: str,
	bus_hydrogen: str,
	bus_steel: str,
	*,
	efficiency: float,
	efficiency_source: str,
	pathway_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "steel_h2_dri",
) -> CouplingView:
	"""Hydrogen direct-reduced iron, then electric-arc furnace.

	The link takes electricity and hydrogen and delivers crude steel. Splitting
	the shaft and the furnace into two links would be more faithful and would
	also double the variable count for a distinction the model cannot use: the
	shaft's off-gas is not modelled, so the intermediate iron bus carries no
	decision.

	``efficiency`` is MWh(steel)/MWh(hydrogen), excluding the electricity the
	furnace consumes -- which is why the link also draws from the electricity
	bus. A caller that wants the full chain quotes both.
	"""
	view = _industrial_link(
		name=name,
		bus0=bus_hydrogen,
		bus1=bus_steel,
		carrier="steel",
		efficiency=efficiency,
		efficiency_unit="MWh_steel/MWh_H2",
		efficiency_source=efficiency_source,
		pathway_source=pathway_source,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		notes=(
			f"Hydrogen DRI route ({STEEL_H2_DRI}); electricity for the EAF is a "
			f"separate draw on {bus_electricity}, which is why the pathway's "
			f"power demand is visible to the network"
		),
	)
	return view


def steel_scrap_eaf_view(
	bus_electricity: str,
	bus_steel: str,
	*,
	efficiency: float,
	efficiency_source: str,
	pathway_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "steel_scrap_eaf",
) -> CouplingView:
	"""Scrap electric-arc furnace: electricity to steel, no hydrogen.

	This route competes with hydrogen DRI for the same steel demand, and the
	model should be able to choose between them. Whether it *can* depends on
	scrap availability, which is a constraint this link does not carry -- so the
	pathway source is where a reader finds the ceiling that was assumed.
	"""
	return _industrial_link(
		name=name,
		bus0=bus_electricity,
		bus1=bus_steel,
		carrier="steel",
		efficiency=efficiency,
		efficiency_unit="MWh_steel/MWh_el",
		efficiency_source=efficiency_source,
		pathway_source=pathway_source,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		notes=f"Scrap EAF route ({STEEL_SCRAP_EAF})",
	)


def cement_ccus_view(
	bus_electricity: str,
	bus_heat: str,
	bus_cement: str,
	bus_co2: str,
	*,
	efficiency: float,
	efficiency_source: str,
	capture_rate: float,
	capture_source: str,
	pathway_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "cement_ccus",
) -> CouplingView:
	"""Cement with carbon capture, as a two-output link.

	``capture_rate`` is the fraction of process CO₂ that is captured rather than
	vented, and it is the parameter the whole pathway turns on: at 90% capture
	the plant is nearly decarbonised, at 50% it is not, and the difference is a
	capture-rate number that a report will quote without qualification. It is
	sourced separately from the efficiency because it is a different kind of
	claim about a different part of the plant.
	"""
	assert bus_co2, "cement CCUS needs a CO2 bus for the captured stream"
	if not 0.0 <= capture_rate <= 1.0:
		raise ValueError(f"capture_rate must be in [0, 1], got {capture_rate}")
	if not capture_source.strip():
		raise ValueError("capture_rate requires its own source, separate from the efficiency")

	view = _industrial_link(
		name=name,
		bus0=bus_electricity,
		bus1=bus_cement,
		bus2=bus_co2,
		carrier="cement",
		efficiency=efficiency,
		efficiency_unit="t_cement/MWh_el",
		efficiency_source=efficiency_source,
		efficiency2=capture_rate,
		efficiency2_unit="t_CO2/t_CO2_process",
		efficiency2_source=capture_source,
		pathway_source=pathway_source,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		notes=(
			f"Cement with CCUS ({CEMENT_CCUS}); heat for calcination is drawn "
			f"from {bus_heat}, and the capture energy penalty is in the "
			f"electricity efficiency rather than hidden in the capture rate"
		),
	)
	return view


def ammonia_view(
	bus_electricity: str,
	bus_hydrogen: str,
	bus_ammonia: str,
	*,
	efficiency: float,
	efficiency_source: str,
	pathway_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "green_ammonia",
) -> CouplingView:
	"""Green ammonia: hydrogen plus electricity (air separation, synthesis).

	The Haber-Bosch loop is the electricity draw; the hydrogen is the feedstock.
	Modelling ammonia as a hydrogen load alone would understate its power demand
	by the air-separation energy, which is the single largest parasitic load in
	a green ammonia plant.
	"""
	return _industrial_link(
		name=name,
		bus0=bus_hydrogen,
		bus1=bus_ammonia,
		carrier="ammonia",
		efficiency=efficiency,
		efficiency_unit="MWh_NH3/MWh_H2",
		efficiency_source=efficiency_source,
		pathway_source=pathway_source,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		notes=f"Green ammonia ({AMMONIA}); Haber-Bosch power drawn from {bus_electricity}",
	)


def methanol_view(
	bus_electricity: str,
	bus_hydrogen: str,
	bus_co2: str,
	bus_methanol: str,
	*,
	efficiency: float,
	efficiency_source: str,
	pathway_source: str,
	co2_per_mwh_meoh: float,
	co2_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "green_methanol",
) -> CouplingView:
	"""Green methanol: hydrogen plus captured CO₂.

	The CO₂ is an input, not an output, so it is drawn on ``bus2`` with a
	*negative* efficiency -- PyPSA treats ``bus2`` as an output port and a
	negative coefficient flips the sign of the flow, which is the only way a
	link can have two inputs. A methanol pathway with no CO₂ source in the model
	is a pathway that silently assumes the CO₂ is free and unlimited, which is
	the assumption most likely to be wrong, so the stoichiometric demand is a
	required, sourced parameter rather than an optional one.
	"""
	if co2_per_mwh_meoh <= 0.0:
		raise ValueError(
			"methanol consumes CO2; co2_per_mwh_meoh must be positive, or the "
			"pathway has silently assumed the CO2 is free"
		)
	if not co2_source.strip():
		raise ValueError("the CO2 demand of methanol needs its own source")
	assert bus_co2, "methanol needs a CO2 bus to draw from"

	view = _industrial_link(
		name=name,
		bus0=bus_hydrogen,
		bus1=bus_methanol,
		bus2=bus_co2,
		carrier="methanol",
		efficiency=efficiency,
		efficiency_unit="MWh_MeOH/MWh_H2",
		efficiency_source=efficiency_source,
		pathway_source=pathway_source,
		efficiency2=-co2_per_mwh_meoh,
		efficiency2_unit="t_CO2/MWh_MeOH",
		efficiency2_source=co2_source,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		notes=(
			f"Green methanol ({METHANOL}); CO2 drawn from {bus_co2} at "
			f"{co2_per_mwh_meoh:g} t/MWh (negative efficiency2), synthesis "
			f"power from {bus_electricity}"
		),
	)
	assert view.parameters["efficiency2"].value < 0.0, "CO2 is an input, not a co-product"
	return view


def co2_storage_view(
	bus_co2: str,
	*,
	source: str,
	e_nom: float = 0.0,
	extendable: bool = True,
	name: str = "co2_sequestration",
) -> CouplingView:
	"""Permanent storage for captured CO₂.

	The cement plant's captured stream is a *co-product*: a link that delivers
	both cement and CO₂ puts a positive flow on the CO₂ bus, and a bus with no
	sink cannot balance, so the plant is forced to zero and the whole network is
	infeasible. That failure is invisible in the static tables and appears only
	as a solver "infeasible" with no named cause, which is why the sink is built
	here rather than left to the caller.

	A store is the right sink: the CO₂ goes in and stays in. It is also the
	counterpart of a methanol link, which would draw the same stream back out as
	a feedstock -- so a caller that builds methanol should size this store's
	``e_nom`` or leave it extendable, and the two then trade against each other
	on one CO₂ balance.
	"""
	assert bus_co2, "CO2 storage needs a CO2 bus"
	assert source.strip(), "CO2 storage is a pathway assumption and needs a source"
	view = CouplingView(
		asset="Store",
		name=name,
		sector=Sector.INDUSTRY,
		carrier="co2",
		bus0=bus_co2,
		attributes={
			"bus": bus_co2,
			"e_nom": float(e_nom),
			"e_nom_extendable": bool(extendable),
			"e_cyclic": False,
		},
		source=source,
		notes=(
			"Captured CO2 is sequestered, not vented: this store is the sink that "
			"makes the cement plant's co-product balance"
		),
	)
	assert view.asset == "Store"
	return view


def industrial_demand_view(
	bus: str,
	*,
	annual_output_kt: float,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	source: str,
	carrier: str,
	name: str,
	energy_per_kt_mwh: float = 0.0,
) -> CouplingView:
	"""An industrial product demand as a ``Load``.

	Industrial demand is flat to within a few percent -- a steel mill does not
	shut down for the weekend in a national model -- so a flat profile is a good
	approximation here in a way it is not for heat. The output is stated in
	kilotonnes because that is the unit the pathway's efficiency is quoted
	against, and converting it to energy before the link would lose the product
	altogether.
	"""
	assert bus, "industrial demand needs a bus"
	assert annual_output_kt >= 0.0, "output must be non-negative"
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	scaled_kt = annual_output_kt * (hours / 8760.0)
	p_set = annual_series(scaled_kt, index, weights)

	parameters = {}
	if energy_per_kt_mwh > 0.0:
		parameters["specific_energy"] = Parameter(
			value=energy_per_kt_mwh,
			unit="MWh/kt",
			source=source,
		)

	view = CouplingView(
		asset="Load",
		name=name,
		sector=Sector.INDUSTRY,
		carrier=carrier,
		bus0=bus,
		parameters=parameters,
		attributes={"bus": bus, "p_set": float(p_set.iloc[0]) if len(p_set) else 0.0},
		time_series={"p_set": p_set.to_list()},
		source=source,
		notes=f"{annual_output_kt:g} kt/year of {carrier}, flat profile",
	)
	return view


def build_industry(
	config: SectorConfig,
	*,
	bus_electricity: str,
	bus_heat: str,
	bus_hydrogen: str,
	bus_steel: str,
	bus_cement: str,
	bus_co2: str,
	bus_chemicals: str,
	snapshots: pd.DatetimeIndex,
	weights: list[float] | None = None,
	steel_output_kt: float = 0.0,
	cement_output_kt: float = 0.0,
	chemicals_output_kt: float = 0.0,
	steel_h2_dri_efficiency: float = 0.0,
	steel_scrap_eaf_efficiency: float = 0.0,
	cement_efficiency: float = 0.0,
	cement_capture_rate: float = 0.0,
	chemicals_efficiency: float = 0.0,
	efficiency_source: str = "",
	pathway_source: str = "",
	capture_source: str = "",
	co2_storage_e_nom: float = 0.0,
	co2_storage_extendable: bool = True,
) -> SectorBuild:
	"""The industry sector, as a set of views.

	Each of the three industries is built independently, so a config with steel
	and chemicals but not cement produces exactly those two -- and the sector is
	disabled only when all three are off. Anything else would make the config
	key that turns on one industry turn off the others.
	"""
	assert bus_electricity, "industry coupling needs an electricity bus"
	index = as_index(snapshots)

	if not (config.industry_steel or config.industry_cement or config.industry_chemicals):
		return SectorBuild(
			sector=Sector.INDUSTRY,
			enabled=False,
			reason=(
				"sector.industry_steel, industry_cement and industry_chemicals "
				"are all false"
			),
		)
	if not pathway_source.strip():
		raise ValueError(f"the industry sector requires a pathway source; {PATHWAY_SOURCE_REQUIRED}")
	if not efficiency_source.strip():
		raise ValueError("the industry sector requires an efficiency source")

	views: list[CouplingView] = []
	if config.industry_steel:
		if steel_output_kt <= 0.0:
			raise ValueError("industry_steel is enabled but steel_output_kt is not positive")
		if steel_h2_dri_efficiency > 0.0:
			views.append(
				steel_h2_dri_view(
					bus_electricity,
					bus_hydrogen,
					bus_steel,
					efficiency=steel_h2_dri_efficiency,
					efficiency_source=efficiency_source,
					pathway_source=pathway_source,
				)
			)
		if steel_scrap_eaf_efficiency > 0.0:
			views.append(
				steel_scrap_eaf_view(
					bus_electricity,
					bus_steel,
					efficiency=steel_scrap_eaf_efficiency,
					efficiency_source=efficiency_source,
					pathway_source=pathway_source,
				)
			)
		views.append(
			industrial_demand_view(
				bus_steel,
				annual_output_kt=steel_output_kt,
				snapshots=index,
				weights=weights,
				source=pathway_source,
				carrier="steel",
				name="steel_demand",
			)
		)

	if config.industry_cement:
		if cement_output_kt <= 0.0:
			raise ValueError("industry_cement is enabled but cement_output_kt is not positive")
		if cement_efficiency <= 0.0:
			raise ValueError("industry_cement requires a positive cement_efficiency")
		if not capture_source.strip():
			raise ValueError("industry_cement requires a capture source")
		views.append(
			cement_ccus_view(
				bus_electricity,
				bus_heat,
				bus_cement,
				bus_co2,
				efficiency=cement_efficiency,
				efficiency_source=efficiency_source,
				capture_rate=cement_capture_rate,
				capture_source=capture_source,
				pathway_source=pathway_source,
			)
		)
		views.append(
			industrial_demand_view(
				bus_cement,
				annual_output_kt=cement_output_kt,
				snapshots=index,
				weights=weights,
				source=pathway_source,
				carrier="cement",
				name="cement_demand",
			)
		)
		# The captured CO2 is a co-product on bus_co2. Without a sink that bus
		# cannot balance and the cement link is pinned to zero, so the store is
		# built whenever the capture stream is -- see co2_storage_view.
		if cement_capture_rate > 0.0:
			views.append(
				co2_storage_view(
					bus_co2,
					source=capture_source or pathway_source,
					e_nom=co2_storage_e_nom,
					extendable=co2_storage_extendable,
				)
			)

	if config.industry_chemicals:
		if chemicals_output_kt <= 0.0:
			raise ValueError(
				"industry_chemicals is enabled but chemicals_output_kt is not positive"
			)
		if chemicals_efficiency <= 0.0:
			raise ValueError("industry_chemicals requires a positive chemicals_efficiency")
		views.append(
			ammonia_view(
				bus_electricity,
				bus_hydrogen,
				bus_chemicals,
				efficiency=chemicals_efficiency,
				efficiency_source=efficiency_source,
				pathway_source=pathway_source,
			)
		)
		views.append(
			industrial_demand_view(
				bus_chemicals,
				annual_output_kt=chemicals_output_kt,
				snapshots=index,
				weights=weights,
				source=pathway_source,
				carrier="ammonia",
				name="chemicals_demand",
			)
		)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.INDUSTRY, rows=rows, views=views, enabled=True)
	logger.info(
		"industry.built",
		assets=len(rows),
		steel=config.industry_steel,
		cement=config.industry_cement,
		chemicals=config.industry_chemicals,
	)
	assert all(row.source for row in rows), "every industrial link carries a pathway source"
	return build


__all__ = [
	"AMMONIA",
	"CEMENT_CCUS",
	"METHANOL",
	"PATHWAY_SOURCE_REQUIRED",
	"STEEL_H2_DRI",
	"STEEL_SCRAP_EAF",
	"ammonia_view",
	"build_industry",
	"cement_ccus_view",
	"industrial_demand_view",
	"methanol_view",
	"steel_h2_dri_view",
	"steel_scrap_eaf_view",
]
