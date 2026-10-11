# SPDX-License-Identifier: MIT
"""The renewable portfolio: beyond solar and wind.

Two things about this module are deliberate and worth stating.

**Kenya first.** The plan's priority order is not the technology list's order
(05-layer2 §3): Kenya needs solar, wind, geothermal and hydro, and the remaining
four -- CSP, offshore wind, biomass, marine -- are continental-only. A complete
Kenya model with four technologies beats a partial continental model with nine,
so ``build_renewables`` records which of the four Kenya-critical technologies
are present and refuses a Kenya portfolio that is missing one. The other four
are built when a config asks for them and are never required.

**Geothermal is decisive and therefore separately validated.** The Kenya case
study turns on it: capping geothermal at 2 GW requires roughly 8 GW of extra
solar and about €600M/year more in system cost, so an error in Kenya's
geothermal potential is an error in Kenya's entire result. Per-field potential
is therefore cross-checked against KenGen's published capacity and against the
Geothermal Atlas for Africa, and the cross-check is an artefact with a
tolerance -- not a comment.

The capacity factors this module attaches come from the ingestion layer. What
it does here is refuse a profile that is missing, out of range, or unsourced,
because a renewable generator with a silently absent ``p_max_pu`` is a generator
that produces at rated power in every hour, and the model will build 40 GW of
it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from alea.config.models import Config
from alea.logging import get_logger
from alea.registry import Carrier, CarrierClass, get_technology
from alea.sector._util import as_index
from alea.sector.views import CouplingView, Parameter, Sector, SectorBuild

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

KENYA_CRITICAL: tuple[Carrier, ...] = (
	Carrier.SOLAR,
	Carrier.ONWIND,
	Carrier.GEOTHERMAL,
	Carrier.HYDRO,
)
"""The four technologies Kenya needs (05-layer2 §3).

A Kenya portfolio missing one of these is not a partial answer, it is a
different system: geothermal alone decides Kenya's least-cost expansion.
"""

CONTINENTAL_ONLY: tuple[Carrier, ...] = (
	Carrier.SOLAR_CSP,
	Carrier.OFFWIND,
	Carrier.BIOMASS,
	Carrier.WAVE,
)
"""Built after the Kenya path closes. Never required for Kenya."""

HYDRO_TYPES: tuple[Carrier, ...] = (Carrier.ROR, Carrier.HYDRO, Carrier.PHS)
"""Run-of-river, reservoir and pumped storage.

Pumped storage is the fourth hydro type in the plan's list and is modelled as a
``StorageUnit`` rather than a generator, because it is a store: it has no
inflow of its own and its entire energy comes from pumping.
"""


class ResourceQuality(StrEnum):
	"""How much to trust a technology's resource dataset (05-layer2 §3 table)."""

	GOOD = "good"
	MODERATE = "moderate"
	POOR = "poor"


QUALITY: dict[Carrier, ResourceQuality] = {
	Carrier.SOLAR: ResourceQuality.GOOD,
	Carrier.SOLAR_CSP: ResourceQuality.GOOD,
	Carrier.ONWIND: ResourceQuality.GOOD,
	Carrier.OFFWIND: ResourceQuality.GOOD,
	Carrier.GEOTHERMAL: ResourceQuality.MODERATE,
	Carrier.HYDRO: ResourceQuality.MODERATE,
	Carrier.ROR: ResourceQuality.MODERATE,
	Carrier.PHS: ResourceQuality.MODERATE,
	Carrier.BIOMASS: ResourceQuality.MODERATE,
	Carrier.WAVE: ResourceQuality.POOR,
	Carrier.TIDAL: ResourceQuality.POOR,
	Carrier.OTEC: ResourceQuality.POOR,
}
"""Per-technology data quality, from the plan's own table.

Carried on every view's notes so a report can say a wave result rests on a
sparse dataset without anyone having to remember which datasets those are.
"""


class GeothermalCrossCheck(BaseModel):
	"""Kenya's geothermal potential against two independent references.

	The gate (05-layer2 §6) is that the modelled potential sits within tolerance
	of KenGen's published figure. Both the modelled value and the published one
	are carried, plus the tolerance actually applied, because a cross-check that
	records only "passed" cannot be re-examined when the tolerance is questioned.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	modelled_mw: float = Field(gt=0.0)
	kenya_installed_mw: float
	"""KenGen's published installed capacity, MW.

	950 MW per ``spec/best1-renew.md`` §4.2 and ``spec/spec4-base.md`` §5. It is
	an *installed* figure and the modelled value is a *potential*, so this is a
	floor test: a potential below what is already built is wrong.
	"""
	atlas_potential_mw: float | None = None
	tolerance_frac: float = Field(default=0.25, gt=0.0, lt=1.0)
	source: str = ""
	notes: str = ""

	@model_validator(mode="after")
	def _crosscheck_is_sourced(self) -> GeothermalCrossCheck:
		if not self.source.strip():
			raise ValueError(
				"a cross-check without its reference source is an opinion; name "
				"KenGen's figure and the Geothermal Atlas"
			)
		return self

	@property
	def relative_error(self) -> float:
		"""Modelled potential against the atlas, as a signed fraction."""
		if self.atlas_potential_mw is None or self.atlas_potential_mw == 0.0:
			return 0.0
		return (self.modelled_mw - self.atlas_potential_mw) / self.atlas_potential_mw

	@property
	def within_tolerance(self) -> bool:
		"""Whether the potential passes both checks.

		The installed-capacity floor is not subject to tolerance: a modelled
		potential below what is already generating is wrong by definition, not
		by a margin.
		"""
		if self.modelled_mw < self.kenya_installed_mw:
			return False
		if self.atlas_potential_mw is None:
			return True
		return abs(self.relative_error) <= self.tolerance_frac

	def require(self) -> GeothermalCrossCheck:
		"""Raise unless the cross-check passes. The gate's assertion."""
		if not self.within_tolerance:
			atlas = (
				f"{self.atlas_potential_mw:,.0f} MW"
				if self.atlas_potential_mw is not None
				else "not supplied"
			)
			raise ValueError(
				f"geothermal potential {self.modelled_mw:,.0f} MW fails the Kenya "
				f"cross-check: installed {self.kenya_installed_mw:,.0f} MW, "
				f"atlas {atlas}, tolerance {self.tolerance_frac:.0%}, relative "
				f"error {self.relative_error:+.1%}. Kenya's whole result turns on "
				f"this number (05-layer2 §3.1)"
			)
		return self


def crosscheck_geothermal(
	*,
	modelled_mw: float,
	kenya_installed_mw: float = 950.0,
	atlas_potential_mw: float | None = None,
	tolerance_frac: float = 0.25,
) -> GeothermalCrossCheck:
	"""Cross-check Kenya's geothermal potential, as the artefact the gate needs.

	``kenya_installed_mw`` defaults to 950 MW because that is the figure the
	specification itself carries in two places; it is a parameter so the
	cross-check can be re-run when KenGen publishes a new one, and the source is
	recorded so the re-run is traceable to which figure it used.
	"""
	assert modelled_mw > 0.0, "modelled potential must be positive"
	assert kenya_installed_mw > 0.0, "installed capacity must be positive"
	return GeothermalCrossCheck(
		modelled_mw=modelled_mw,
		kenya_installed_mw=kenya_installed_mw,
		atlas_potential_mw=atlas_potential_mw,
		tolerance_frac=tolerance_frac,
		source=(
			"KenGen published installed capacity 950 MW "
			"(spec/best1-renew.md §4.2, spec/spec4-base.md §5); "
			"Geothermal Atlas for Africa per-field potential"
		),
		notes="05-layer2 §3.1: the Kenya case study turns on this number.",
	)


def _capacity_factor_parameter(
	profile: pd.Series,
	*,
	source: str,
	layout_notes: str,
) -> Parameter:
	"""A capacity-factor series, validated and sourced.

	The layout is part of the parameter because ``atlite``'s convertibles return
	a capacity factor per unit of installed capacity *given a layout* -- turbine
	type, hub height, panel tilt, spacing -- and the layout moves the result by
	10-20% (04-layer1 §3.3). A capacity factor without its layout is a number
	that cannot be reproduced.
	"""
	values = profile.to_numpy()
	if values.size == 0:
		raise ValueError("a capacity factor series is empty")
	if not ((values >= 0.0) & (values <= 1.0)).all():
		raise ValueError(
			f"capacity factor outside [0, 1]: range "
			f"[{values.min():.3f}, {values.max():.3f}]"
		)
	if not source.strip():
		raise ValueError("a capacity factor requires its source")
	return Parameter(
		value=float(values.mean()),
		unit="fraction",
		source=source,
		notes=f"mean of the profile; time series overrides. Layout: {layout_notes}",
	)


def _renewable_generator(
	*,
	name: str,
	bus: str,
	carrier: Carrier,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str,
	layout_notes: str,
	p_nom: float,
	extendable: bool,
	capital_cost: float,
	marginal_cost: float,
	p_min_pu: float,
	p_min_pu_source: str,
	extra_attributes: dict[str, Any] | None = None,
	notes: str = "",
) -> CouplingView:
	"""One renewable generator, with its resource profile and its quality."""
	tech = get_technology(carrier.value)
	assert tech.klass in (
		CarrierClass.VRE,
		CarrierClass.DISPATCHABLE_RE,
		CarrierClass.THERMAL,
	), f"{carrier.value} is a {tech.klass} and is not a generator carrier"
	assert p_nom >= 0.0, "capacity must be non-negative"

	parameters: dict[str, Parameter] = {}
	time_series: dict[str, list[float]] = {}
	if capacity_factor is not None:
		parameters["p_max_pu"] = _capacity_factor_parameter(
			capacity_factor, source=capacity_factor_source, layout_notes=layout_notes
		)
		time_series["p_max_pu"] = capacity_factor.to_list()
	elif tech.variable:
		raise ValueError(
			f"{name}: {carrier.value} is a variable renewable and has no "
			f"capacity factor; a generator with no p_max_pu produces at rated "
			f"power in every hour and the model will build the maximum"
		)
	if p_min_pu > 0.0:
		if not p_min_pu_source.strip():
			raise ValueError(
				f"{name}: a minimum stable level requires its source; it is a "
				f"constraint on the resource, not a modelling preference"
			)
		parameters["p_min_pu"] = Parameter(
			value=p_min_pu,
			unit="fraction",
			source=p_min_pu_source,
		)

	quality = QUALITY.get(carrier, ResourceQuality.MODERATE)
	attributes: dict[str, Any] = {
		"bus": bus,
		"p_nom": float(p_nom),
		"p_nom_extendable": bool(extendable),
		"capital_cost": float(capital_cost),
		"marginal_cost": float(marginal_cost),
		"p_min_pu": float(p_min_pu),
	}
	if extra_attributes:
		attributes.update(extra_attributes)

	view = CouplingView(
		asset="Generator",
		name=name,
		sector=Sector.RENEWABLES,
		carrier=carrier.value,
		bus0=bus,
		parameters=parameters,
		attributes=attributes,
		time_series=time_series,
		source=capacity_factor_source or "05-layer2 §3 (renewable portfolio)",
		notes=f"Resource data quality: {quality.value}. {notes}".strip(),
	)
	return view


def solar_pv_view(
	bus: str,
	*,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str = "",
	layout_notes: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "solar_pv",
) -> CouplingView:
	"""Solar PV from Global Solar Atlas / ERA5-derived profiles."""
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.SOLAR,
		capacity_factor=capacity_factor,
		capacity_factor_source=capacity_factor_source,
		layout_notes=layout_notes,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
	)


def csp_view(
	bus: str,
	*,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str = "",
	layout_notes: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "csp",
) -> CouplingView:
	"""Concentrating solar power, from Global Solar Atlas DNI.

	Continental-only: Kenya has no CSP in the plan's priority set, and a CSP
	block in a Kenya config is a modelling choice the config has to make
	explicitly.
	"""
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.SOLAR_CSP,
		capacity_factor=capacity_factor,
		capacity_factor_source=capacity_factor_source,
		layout_notes=layout_notes,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes="Continental-only technology (05-layer2 §3).",
	)


def onshore_wind_view(
	bus: str,
	*,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str = "",
	layout_notes: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "onwind",
) -> CouplingView:
	"""Onshore wind from Global Wind Atlas 3.0."""
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.ONWIND,
		capacity_factor=capacity_factor,
		capacity_factor_source=capacity_factor_source,
		layout_notes=layout_notes,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
	)


def offshore_wind_view(
	bus: str,
	*,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str = "",
	layout_notes: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "offwind",
) -> CouplingView:
	"""Offshore wind, sited against GEBCO bathymetry.

	Continental-only, and for Kenya irrelevant: the country is landlocked in the
	sense that matters, which is that it has no shelf shallow enough to build on
	at the scale that would change its mix.
	"""
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.OFFWIND,
		capacity_factor=capacity_factor,
		capacity_factor_source=capacity_factor_source,
		layout_notes=layout_notes,
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes="Continental-only technology (05-layer2 §3).",
	)


def geothermal_view(
	bus: str,
	*,
	potential_mw: float,
	potential_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	minimum_stable_fraction: float = 0.0,
	minimum_stable_source: str = "",
	name: str = "geothermal",
) -> CouplingView:
	"""Geothermal, Kenya's decisive technology (05-layer2 §3.1).

	Geothermal is not a variable renewable: it produces at a stable output with
	a ramp limit and a minimum stable level, and it is modelled as a dispatchable
	generator with ``p_max_pu`` fixed at 1.0. ``potential_mw`` caps it, and the
	cap is the number the whole Kenya result turns on -- so it is carried on the
	view as a sourced parameter even though PyPSA does not use it directly.
	"""
	assert potential_mw > 0.0, "geothermal potential must be positive"
	assert 0.0 <= minimum_stable_fraction < 1.0, "minimum stable fraction must be in [0, 1)"
	source = potential_source.strip()
	if not source:
		raise ValueError(
			"geothermal requires a potential source; Kenya's least-cost "
			"expansion is geothermal, so an unsourced potential is an unsourced "
			"national result (05-layer2 §3.1)"
		)

	view = _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.GEOTHERMAL,
		capacity_factor=None,
		capacity_factor_source="",
		layout_notes="dispatchable; no weather dependence",
		p_nom=p_nom if p_nom > 0.0 else potential_mw,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=minimum_stable_fraction,
		p_min_pu_source=minimum_stable_source,
		notes=(
			f"Potential capped at {potential_mw:,.0f} MW. Baseload with ramp "
			f"limits; the cross-check artefact is in renewables.crosscheck_geothermal"
		),
	)
	# The potential is a physical resource parameter, so it is recorded as one.
	view = view.model_copy(
		update={
			"parameters": {
				**view.parameters,
				"potential": Parameter(
					value=potential_mw,
					unit="MW",
					source=source,
					uncertainty=0.25,
					uncertainty_basis=(
						"per-field potential depends on reservoir temperature, "
						"permeability and drilling success, none of which is "
						"measured at depth"
					),
				),
			}
		}
	)
	assert view.parameters["potential"].source == source
	return view


def hydro_ror_view(
	bus: str,
	*,
	inflow_profile: pd.Series | None,
	inflow_source: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "hydro_ror",
) -> CouplingView:
	"""Run-of-river hydro: variable, driven by the inflow profile.

	Seasonal, not weather-driven in the hourly sense, and the plan's own table
	rates its dataset moderate. The profile is what carries that seasonality, so
	an RoR plant without one is a plant that runs at rated output all year.
	"""
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.ROR,
		capacity_factor=inflow_profile,
		capacity_factor_source=inflow_source,
		layout_notes="inflow-driven; seasonal availability profile",
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes="African Hydropower Atlas seasonal profile.",
	)


def hydro_reservoir_view(
	bus: str,
	*,
	inflow_profile: pd.Series | None,
	inflow_source: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	energy_to_power_hours: float = 0.0,
	energy_to_power_source: str = "",
	name: str = "hydro_reservoir",
) -> CouplingView:
	"""Reservoir hydro as a dispatchable generator over a seasonal inflow.

	Modelled as a generator with a curtailment-capable profile rather than as a
	store. The reservoir's inter-seasonal storage is real and is not modelled
	here: doing it properly needs an energy budget that constrains total annual
	generation, and a model that gives a reservoir hourly flexibility without
	that budget will drain it every dry season. ``energy_to_power_hours`` is
	carried so the assumption is visible, and its absence is recorded rather
	than silently ignored.
	"""
	view = _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.HYDRO,
		capacity_factor=inflow_profile,
		capacity_factor_source=inflow_source,
		layout_notes="dispatchable over a seasonal inflow profile",
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes=(
			"Inter-seasonal reservoir storage is NOT modelled; the inflow "
			"profile is the whole constraint. See 04-layer1 §3 for the seasonal "
			"budget that would be needed."
		),
	)
	if energy_to_power_hours > 0.0:
		if not energy_to_power_source.strip():
			raise ValueError("an energy-to-power ratio requires its source")
		view = view.model_copy(
			update={
				"parameters": {
					**view.parameters,
					"energy_to_power": Parameter(
						value=energy_to_power_hours,
						unit="h",
						source=energy_to_power_source,
					),
				}
			}
		)
	return view


def hydro_phs_view(
	bus: str,
	*,
	p_nom: float = 0.0,
	max_hours: float,
	max_hours_source: str,
	round_trip_efficiency: float,
	round_trip_source: str,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "hydro_phs",
) -> CouplingView:
	"""Pumped hydro storage as a ``StorageUnit``.

	The round-trip efficiency is the parameter that decides whether PHS is a
	store or a loss: at 0.75 a pumped store returns three quarters of what it
	takes, and a model with 1.0 has built a perpetual motion machine that will
	cycle at every price difference however small.
	"""
	assert p_nom >= 0.0, "capacity must be non-negative"
	assert max_hours > 0.0, "energy-to-power hours must be positive"
	if not 0.0 < round_trip_efficiency <= 1.0:
		raise ValueError(f"round-trip efficiency must be in (0, 1], got {round_trip_efficiency}")
	if not round_trip_source.strip():
		raise ValueError("PHS requires a round-trip-efficiency source")
	if not max_hours_source.strip():
		raise ValueError("PHS requires an energy-to-power source")

	per_direction = round_trip_efficiency**0.5
	view = CouplingView(
		asset="StorageUnit",
		name=name,
		sector=Sector.RENEWABLES,
		carrier=Carrier.PHS.value,
		bus0=bus,
		parameters={
			"efficiency_store": Parameter(
				value=per_direction,
				unit="fraction",
				source=round_trip_source,
				notes=f"sqrt of the {round_trip_efficiency:g} round-trip efficiency",
			),
			"efficiency_dispatch": Parameter(
				value=per_direction,
				unit="fraction",
				source=round_trip_source,
				notes=f"sqrt of the {round_trip_efficiency:g} round-trip efficiency",
			),
		},
		attributes={
			"bus": bus,
			"p_nom": float(p_nom),
			"p_nom_extendable": bool(extendable),
			"max_hours": float(max_hours),
			"capital_cost": float(capital_cost),
		},
		source=round_trip_source,
		notes=(
			f"{max_hours:g} h at rated power; round-trip efficiency split "
			f"evenly between store and dispatch, which is the PyPSA convention"
		),
	)
	assert view.parameters["efficiency_store"].value > 0.0
	return view


def biomass_view(
	bus: str,
	*,
	fuel_cost_usd_per_mwh: float,
	fuel_cost_source: str,
	efficiency: float,
	efficiency_source: str,
	potential_mw: float,
	potential_source: str,
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "biomass",
) -> CouplingView:
	"""Biomass conversion as a dispatchable generator.

	Biomass is dispatchable, so it needs no capacity factor, but it does have a
	fuel cost and a fuel supply ceiling -- and the ceiling is the binding
	constraint in almost every African biomass study. Both are sourced: a
	biomass plant with no fuel limit is a plant that runs at full output all
	year and competes with nothing.
	"""
	assert potential_mw > 0.0, "biomass potential must be positive"
	if not fuel_cost_source.strip() or not potential_source.strip():
		raise ValueError("biomass requires both a fuel-cost source and a potential source")

	view = _renewable_generator(
		name=name,
		bus=bus,
		carrier=Carrier.BIOMASS,
		capacity_factor=None,
		capacity_factor_source="",
		layout_notes="dispatchable; fuel-limited",
		p_nom=p_nom if p_nom > 0.0 else potential_mw,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=fuel_cost_usd_per_mwh,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes=(
			f"Fuel-limited to {potential_mw:,.0f} MW; conversion efficiency "
			f"{efficiency:g} ({efficiency_source})"
		),
	)
	view = view.model_copy(
		update={
			"parameters": {
				**view.parameters,
				"efficiency": Parameter(
					value=efficiency,
					unit="MWh_out/MWh_fuel",
					source=efficiency_source,
				),
				"potential": Parameter(
					value=potential_mw,
					unit="MW",
					source=potential_source,
				),
				"fuel_cost": Parameter(
					value=fuel_cost_usd_per_mwh,
					unit="USD/MWh_fuel",
					source=fuel_cost_source,
				),
			}
		}
	)
	assert view.parameters["efficiency"].value == efficiency
	return view


def marine_view(
	bus: str,
	*,
	carrier: Carrier,
	capacity_factor: pd.Series | None,
	capacity_factor_source: str = "",
	p_nom: float = 0.0,
	extendable: bool = True,
	capital_cost: float = 0.0,
	name: str = "marine",
) -> CouplingView:
	"""Wave, tidal or ocean-thermal, from the Global Wave Statistics dataset.

	The plan rates marine resource data *poor* and sparse (05-layer2 §3). The
	quality tag travels on the view so a marine result is never reported with
	the same confidence as a solar one.
	"""
	if carrier not in (Carrier.WAVE, Carrier.TIDAL, Carrier.OTEC):
		raise ValueError(f"{carrier.value} is not a marine carrier")
	return _renewable_generator(
		name=name,
		bus=bus,
		carrier=carrier,
		capacity_factor=capacity_factor,
		capacity_factor_source=capacity_factor_source,
		layout_notes="sparse and poorly sampled; treat with caution",
		p_nom=p_nom,
		extendable=extendable,
		capital_cost=capital_cost,
		marginal_cost=0.0,
		p_min_pu=0.0,
		p_min_pu_source="",
		notes="Continental-only, poor resource data (05-layer2 §3).",
	)


_BUILDERS: dict[str, str] = {
	"solar": "solar_pv_view",
	"solar_pv": "solar_pv_view",
	"csp": "csp_view",
	"onwind": "onshore_wind_view",
	"onshore_wind": "onshore_wind_view",
	"offwind": "offshore_wind_view",
	"offshore_wind": "offshore_wind_view",
	"geothermal": "geothermal_view",
	"hydro": "hydro_reservoir_view",
	"reservoir": "hydro_reservoir_view",
	"ror": "hydro_ror_view",
	"phs": "hydro_phs_view",
	"biomass": "biomass_view",
	"wave": "marine_view",
	"tidal": "marine_view",
	"otec": "marine_view",
}
"""Config carrier name to the function that builds it."""


def build_renewables(
	config: Config,
	*,
	bus: str,
	snapshots: pd.DatetimeIndex,
	capacity_factors: dict[str, pd.Series] | None = None,
	capacity_factor_sources: dict[str, str] | None = None,
	layout_notes: dict[str, str] | None = None,
	require_kenya_portfolio: bool = True,
	**technology_kwargs: Any,
) -> SectorBuild:
	"""Build the renewable portfolio a config asks for.

	``capacity_factors`` maps carrier name to its profile, and the profiles come
	from the ingestion layer rather than from here. A carrier enabled in the
	config with no profile is refused for a variable technology and built
	without one for a dispatchable one -- the distinction the technology
	registry already carries.

	``require_kenya_portfolio`` is the plan's priority order made checkable: a
	Kenya config must carry all four of solar, wind, geothermal and hydro, and a
	partial portfolio is refused rather than reported as a complete model with
	one technology missing.
	"""
	assert bus, "the renewable portfolio needs a bus"
	index = as_index(snapshots)
	if not config.renewables:
		return SectorBuild(
			sector=Sector.RENEWABLES,
			enabled=False,
			reason="no carriers are enabled under config.renewables",
		)

	profiles = capacity_factors or {}
	sources = capacity_factor_sources or {}
	layouts = layout_notes or {}
	views: list[CouplingView] = []
	built: set[Carrier] = set()

	for carrier_name, renewable in sorted(config.renewables.items()):
		if not renewable.enabled:
			continue
		builder_name = _BUILDERS.get(carrier_name.strip().lower())
		if builder_name is None:
			raise KeyError(
				f"config.renewables names {carrier_name!r}, which has no builder; "
				f"known: {', '.join(sorted(_BUILDERS))}"
			)
		builder = globals()[builder_name]
		carrier = get_technology(carrier_name).carrier
		profile = profiles.get(carrier_name) or profiles.get(carrier.value)
		source = sources.get(carrier_name) or sources.get(carrier.value, "")
		layout = layouts.get(carrier_name) or layouts.get(carrier.value, "")
		kwargs = _kwargs_for(builder_name, technology_kwargs, carrier_name)

		if builder_name in ("hydro_ror_view", "hydro_reservoir_view"):
			kwargs["inflow_profile"] = profile
			kwargs["inflow_source"] = source
			kwargs["layout_notes"] = layout
		elif builder_name == "marine_view":
			kwargs["carrier"] = carrier
			kwargs["capacity_factor"] = profile
			kwargs["capacity_factor_source"] = source
		else:
			kwargs["capacity_factor"] = profile
			kwargs["capacity_factor_source"] = source
			kwargs["layout_notes"] = layout

		views.append(builder(bus, **kwargs))
		built.add(carrier)
		logger.info(
			"renewables.carrier",
			carrier=carrier.value,
			quality=QUALITY.get(carrier, ResourceQuality.MODERATE).value,
			has_profile=profile is not None,
		)

	if require_kenya_portfolio:
		present = set(built)
		if Carrier.ROR in present:
			present.add(Carrier.HYDRO)
		missing = [carrier.value for carrier in KENYA_CRITICAL if carrier not in present]
		if missing:
			raise ValueError(
				f"the Kenya portfolio is missing {', '.join(missing)}; Kenya needs "
				f"solar, wind, geothermal and hydro, and a partial portfolio is a "
				f"different system rather than a smaller one (05-layer2 §3)"
			)

	rows = [view.as_row() for view in views]
	build = SectorBuild(sector=Sector.RENEWABLES, rows=rows, views=views, enabled=True)
	logger.info("renewables.built", assets=len(rows), carriers=len(built))
	assert rows, "an enabled renewable portfolio produced no generators"
	return build


def _kwargs_for(
	builder_name: str,
	technology_kwargs: dict[str, Any],
	carrier_name: str,
) -> dict[str, Any]:
	"""The keyword arguments for one carrier's builder.

	Per-carrier kwargs are passed either under the carrier's own name or flat,
	so a caller can configure one technology without configuring all of them.
	"""
	nested = technology_kwargs.get(carrier_name)
	if isinstance(nested, dict):
		return dict(nested)
	flat_keys = {
		"solar_pv_view": ("p_nom", "extendable", "capital_cost", "name"),
		"csp_view": ("p_nom", "extendable", "capital_cost", "name"),
		"onshore_wind_view": ("p_nom", "extendable", "capital_cost", "name"),
		"offshore_wind_view": ("p_nom", "extendable", "capital_cost", "name"),
		"geothermal_view": (
			"potential_mw",
			"potential_source",
			"p_nom",
			"extendable",
			"capital_cost",
			"minimum_stable_fraction",
			"minimum_stable_source",
			"name",
		),
		"hydro_ror_view": ("p_nom", "extendable", "capital_cost", "name"),
		"hydro_reservoir_view": (
			"p_nom",
			"extendable",
			"capital_cost",
			"energy_to_power_hours",
			"energy_to_power_source",
			"name",
		),
		"hydro_phs_view": (
			"p_nom",
			"max_hours",
			"max_hours_source",
			"round_trip_efficiency",
			"round_trip_source",
			"extendable",
			"capital_cost",
			"name",
		),
		"biomass_view": (
			"fuel_cost_usd_per_mwh",
			"fuel_cost_source",
			"efficiency",
			"efficiency_source",
			"potential_mw",
			"potential_source",
			"p_nom",
			"extendable",
			"capital_cost",
			"name",
		),
		"marine_view": ("p_nom", "extendable", "capital_cost", "name"),
	}
	allowed = flat_keys.get(builder_name, ("p_nom", "extendable", "capital_cost", "name"))
	return {key: value for key, value in technology_kwargs.items() if key in allowed}


def kenya_portfolio_gate(rows: list[Any], *, carriers: list[str] | None = None) -> None:
	"""Assert the four Kenya-critical technologies are present. Raises otherwise.

	Split from ``build_renewables`` so it can be run against a network or an
	artefact that was built elsewhere: the gate is about the portfolio, not
	about the function that produced it.
	"""
	present = {carrier.strip().lower() for carrier in (carriers or [row.carrier for row in rows])}
	# Run-of-river is the same resource as reservoir hydro: a portfolio with RoR
	# and no reservoir has not dropped hydropower, it has modelled it differently.
	if Carrier.ROR.value in present:
		present.add(Carrier.HYDRO.value)
	missing = [carrier.value for carrier in KENYA_CRITICAL if carrier.value not in present]
	if missing:
		raise ValueError(
			f"Kenya portfolio gate failed; missing {', '.join(missing)} (05-layer2 §3)"
		)


__all__ = [
	"CONTINENTAL_ONLY",
	"HYDRO_TYPES",
	"KENYA_CRITICAL",
	"QUALITY",
	"GeothermalCrossCheck",
	"ResourceQuality",
	"biomass_view",
	"build_renewables",
	"crosscheck_geothermal",
	"csp_view",
	"geothermal_view",
	"hydro_phs_view",
	"hydro_reservoir_view",
	"hydro_ror_view",
	"kenya_portfolio_gate",
	"marine_view",
	"offshore_wind_view",
	"onshore_wind_view",
	"solar_pv_view",
]
