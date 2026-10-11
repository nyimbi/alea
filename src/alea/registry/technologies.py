# SPDX-License-Identifier: MIT
"""Technology registry.

Carrier names appear in the fleet dataset, the renewable config, the market
model, and every report. They are declared once here so a typo is caught at
load rather than producing a carrier with one plant in it.

The ``carrier`` values match PyPSA's conventional names, because the network
artefact is shared with PyPSA-Earth and a translation layer is a place for
errors to hide.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field


class Carrier(StrEnum):
	"""A generation or storage carrier."""

	# Dispatchable thermal
	COAL = "coal"
	GAS = "gas"
	OIL = "oil"
	NUCLEAR = "nuclear"
	BIOMASS = "biomass"
	WASTE = "waste"

	# Variable renewable
	SOLAR = "solar"
	SOLAR_CSP = "csp"
	ONWIND = "onwind"
	OFFWIND = "offwind"

	# Dispatchable renewable
	HYDRO = "hydro"
	ROR = "ror"
	PHS = "PHS"
	GEOTHERMAL = "geothermal"

	# Marine
	WAVE = "wave"
	TIDAL = "tidal"
	OTEC = "otec"

	# Coupling / storage
	H2 = "h2"
	ELECTROLYSIS = "electrolysis"
	BATTERY = "battery"
	HEAT_PUMP = "heat pump"
	THERMAL_STORAGE = "thermal storage"
	LOAD_SHEDDING = "load shedding"


class CarrierClass(StrEnum):
	"""What kind of thing a carrier is. Drives aggregation and reporting."""

	THERMAL = "thermal"
	VRE = "vre"
	DISPATCHABLE_RE = "dispatchable_re"
	STORAGE = "storage"
	COUPLING = "coupling"


class Technology(BaseModel):
	"""One carrier's properties."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	carrier: Carrier
	name: str
	klass: CarrierClass
	renewable: bool
	"""Whether the carrier counts toward a renewable share."""
	co2_t_per_mwh: float = Field(default=0.0, ge=0.0)
	"""Direct emissions intensity at generation. Zero for renewables."""
	variable: bool
	"""Whether output is weather-driven rather than dispatchable."""
	dispatchable: bool
	"""Whether the operator can choose the output."""
	has_fuel_cost: bool = False


_DEFAULTS: tuple[Technology, ...] = (
	Technology(
		carrier=Carrier.COAL,
		name="Coal",
		klass=CarrierClass.THERMAL,
		renewable=False,
		co2_t_per_mwh=0.95,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.GAS,
		name="Natural gas",
		klass=CarrierClass.THERMAL,
		renewable=False,
		co2_t_per_mwh=0.40,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.OIL,
		name="Oil",
		klass=CarrierClass.THERMAL,
		renewable=False,
		co2_t_per_mwh=0.75,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.NUCLEAR,
		name="Nuclear",
		klass=CarrierClass.THERMAL,
		renewable=False,
		co2_t_per_mwh=0.0,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.BIOMASS,
		name="Biomass",
		klass=CarrierClass.THERMAL,
		renewable=True,
		co2_t_per_mwh=0.0,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.WASTE,
		name="Waste to energy",
		klass=CarrierClass.THERMAL,
		renewable=True,
		co2_t_per_mwh=0.30,
		variable=False,
		dispatchable=True,
		has_fuel_cost=True,
	),
	Technology(
		carrier=Carrier.SOLAR,
		name="Solar PV",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.SOLAR_CSP,
		name="Concentrated solar power",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.ONWIND,
		name="Onshore wind",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.OFFWIND,
		name="Offshore wind",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.HYDRO,
		name="Reservoir hydro",
		klass=CarrierClass.DISPATCHABLE_RE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.ROR,
		name="Run-of-river hydro",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.PHS,
		name="Pumped hydro storage",
		klass=CarrierClass.STORAGE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.GEOTHERMAL,
		name="Geothermal",
		klass=CarrierClass.DISPATCHABLE_RE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.WAVE,
		name="Wave",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.TIDAL,
		name="Tidal",
		klass=CarrierClass.VRE,
		renewable=True,
		variable=True,
		dispatchable=False,
	),
	Technology(
		carrier=Carrier.OTEC,
		name="Ocean thermal",
		klass=CarrierClass.DISPATCHABLE_RE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.H2,
		name="Hydrogen",
		klass=CarrierClass.COUPLING,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.ELECTROLYSIS,
		name="Electrolysis",
		klass=CarrierClass.COUPLING,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.BATTERY,
		name="Battery",
		klass=CarrierClass.STORAGE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.HEAT_PUMP,
		name="Heat pump",
		klass=CarrierClass.COUPLING,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.THERMAL_STORAGE,
		name="Thermal storage",
		klass=CarrierClass.STORAGE,
		renewable=True,
		variable=False,
		dispatchable=True,
	),
	Technology(
		carrier=Carrier.LOAD_SHEDDING,
		name="Load shedding",
		klass=CarrierClass.COUPLING,
		renewable=False,
		variable=False,
		dispatchable=True,
	),
)

# Carrier names as they appear in upstream datasets. powerplantmatching emits
# its own vocabulary ("Hard Coal", "Natural Gas", "Wind", "Hydro"), and a
# fleet that fails to map is a fleet whose capacity silently disappears.
_ALIASES: dict[str, Carrier] = {
	"hard coal": Carrier.COAL,
	"lignite": Carrier.COAL,
	"coal": Carrier.COAL,
	"natural gas": Carrier.GAS,
	"gas": Carrier.GAS,
	"ccgt": Carrier.GAS,
	"ocgt": Carrier.GAS,
	"oil": Carrier.OIL,
	"diesel": Carrier.OIL,
	"heavy fuel oil": Carrier.OIL,
	"hfo": Carrier.OIL,
	"nuclear": Carrier.NUCLEAR,
	"biomass": Carrier.BIOMASS,
	"bioenergy": Carrier.BIOMASS,
	"waste": Carrier.WASTE,
	"solar": Carrier.SOLAR,
	"solar pv": Carrier.SOLAR,
	"pv": Carrier.SOLAR,
	"photovoltaic": Carrier.SOLAR,
	"csp": Carrier.SOLAR_CSP,
	"concentrated solar power": Carrier.SOLAR_CSP,
	"wind": Carrier.ONWIND,
	"onwind": Carrier.ONWIND,
	"onshore wind": Carrier.ONWIND,
	"offwind": Carrier.OFFWIND,
	"offshore wind": Carrier.OFFWIND,
	"hydro": Carrier.HYDRO,
	"hydroelectric": Carrier.HYDRO,
	"reservoir": Carrier.HYDRO,
	"ror": Carrier.ROR,
	"run-of-river": Carrier.ROR,
	"run of river": Carrier.ROR,
	"phs": Carrier.PHS,
	"pumped storage": Carrier.PHS,
	"pumped hydro": Carrier.PHS,
	"geothermal": Carrier.GEOTHERMAL,
	"wave": Carrier.WAVE,
	"tidal": Carrier.TIDAL,
	"otec": Carrier.OTEC,
	"ocean thermal": Carrier.OTEC,
	"h2": Carrier.H2,
	"hydrogen": Carrier.H2,
	"electrolysis": Carrier.ELECTROLYSIS,
	"battery": Carrier.BATTERY,
	"li-ion": Carrier.BATTERY,
	"bess": Carrier.BATTERY,
	"heat pump": Carrier.HEAT_PUMP,
	"thermal storage": Carrier.THERMAL_STORAGE,
	"load shedding": Carrier.LOAD_SHEDDING,
}


@lru_cache(maxsize=1)
def technologies() -> dict[Carrier, Technology]:
	"""Every registered technology, keyed by carrier."""
	return {tech.carrier: tech for tech in _DEFAULTS}


def get_technology(carrier: str) -> Technology:
	"""Look up a technology by carrier name or upstream alias.

	Raises on an unknown carrier. A fleet row with an unmapped carrier is a
	plant whose capacity vanishes from the model while the total still looks
	plausible, so this refuses rather than defaulting.
	"""
	key = carrier.strip().lower()
	if key in _ALIASES:
		return technologies()[_ALIASES[key]]
	for tech in technologies().values():
		if tech.carrier.value == key or tech.name.lower() == key:
			return tech
	known = ", ".join(sorted(_ALIASES))
	raise KeyError(f"unknown carrier {carrier!r}; known aliases: {known}")


def is_known_carrier(carrier: str) -> bool:
	"""Whether a carrier name or alias maps to a technology."""
	try:
		get_technology(carrier)
	except KeyError:
		return False
	return True


def renewable_carriers() -> list[Carrier]:
	"""Carriers that count toward a renewable share."""
	return sorted(
		(t.carrier for t in technologies().values() if t.renewable),
		key=lambda c: c.value,
	)


def storage_carriers() -> list[Carrier]:
	"""Carriers that store energy rather than generate it."""
	return sorted(
		(t.carrier for t in technologies().values() if t.klass is CarrierClass.STORAGE),
		key=lambda c: c.value,
	)


def co2_intensity(carrier: str) -> float:
	"""Direct CO2 intensity in tCO2/MWh, or raise on an unknown carrier."""
	return get_technology(carrier).co2_t_per_mwh


__all__ = [
	"Carrier",
	"CarrierClass",
	"Technology",
	"co2_intensity",
	"get_technology",
	"is_known_carrier",
	"renewable_carriers",
	"storage_carriers",
	"technologies",
]
