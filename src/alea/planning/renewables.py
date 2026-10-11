# SPDX-License-Identifier: MIT
"""Renewable capacity factors per bus.

A capacity factor is a modelling output, not a measurement, and its value moves
10-20% with choices nobody writes down: turbine hub height and class, panel tilt
and tracking, spacing between rows. Those choices are parameters of this module
and they go into the artefact's provenance, because a capacity factor quoted
without its layout is a number with no meaning.

The range check is the other half. A capacity factor of 1.2 means the layout was
applied twice or the profile is already in MW; both are silent and both make the
model build renewable capacity that cannot exist.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger
from alea.planning.schemas import PROFILE, check_carriers
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

TURBINE_LAYOUT: dict[str, float] = {
	"turbine_class": 3.0,
	"hub_height_m": 100.0,
	"rotor_diameter_m": 150.0,
	"spacing_km": 1.0,
}
"""Onshore wind layout. Class 3 / 100 m hub / 150 m rotor is the current
mainstream machine; ``spacing_km`` sets the packable density."""

SOLAR_LAYOUT: dict[str, float] = {
	"panel_tilt_deg": 20.0,
	"tracking": 0.0,
	"row_spacing_ratio": 0.35,
}
"""Solar PV layout. Fixed 20-degree tilt with no tracking is the conservative
African utility-scale default; tracking raises the capacity factor and the
capital cost together."""

CF_MIN = 0.0
CF_MAX = 1.0


class RenewableError(ValueError):
	"""A renewable profile cannot be built or does not validate."""


@dataclass(frozen=True)
class CapacityFactorStats:
	"""Summary of one carrier's profile, for the artefact and the log."""

	carrier: str
	n_buses: int
	n_hours: int
	mean: float
	minimum: float
	maximum: float
	capacity_factor_annual: float

	def as_dict(self) -> dict[str, object]:
		return {
			"carrier": self.carrier,
			"n_buses": self.n_buses,
			"n_hours": self.n_hours,
			"mean": self.mean,
			"min": self.minimum,
			"max": self.maximum,
			"capacity_factor_annual": self.capacity_factor_annual,
		}


def validate_capacity_factors(
	profiles: pd.DataFrame,
	*,
	carrier: str = "",
	allow_nan: bool = False,
) -> CapacityFactorStats:
	"""Check every capacity factor is in [0, 1].

	NaN is refused by default. A NaN capacity factor propagates into the
	dispatch and turns a renewable generator's output into a missing value that
	the solver reads as zero -- a silent curtailment of the whole fleet at that
	bus. Where a profile legitimately has no value (a bus with no resource),
	``allow_nan`` says so explicitly and the NaNs are excluded from the stats.
	"""
	assert len(profiles) > 0, "no profiles to validate"
	values = profiles.to_numpy(dtype=float)
	n_nan = int(np.isnan(values).sum())
	if n_nan and not allow_nan:
		raise RenewableError(
			f"{carrier or 'profile'}: {n_nan} missing capacity factor(s); pass "
			f"allow_nan=True if the gap is intentional"
		)
	finite = values[np.isfinite(values)]
	if finite.size == 0:
		raise RenewableError(f"{carrier or 'profile'}: no finite capacity factors")
	lo, hi = float(finite.min()), float(finite.max())
	if lo < CF_MIN - 1e-9 or hi > CF_MAX + 1e-9:
		raise RenewableError(
			f"{carrier or 'profile'}: capacity factor out of [0, 1] "
			f"(min {lo:.4f}, max {hi:.4f}); a factor above 1 means the profile is "
			f"already in MW or the layout was applied twice"
		)
	stats = CapacityFactorStats(
		carrier=carrier,
		n_buses=int(profiles.shape[1]),
		n_hours=int(profiles.shape[0]),
		mean=float(finite.mean()),
		minimum=lo,
		maximum=hi,
		capacity_factor_annual=float(finite.mean()),
	)
	logger.info(
		"capacity_factors_validated",
		carrier=carrier,
		mean=stats.mean,
		min=lo,
		max=hi,
		nan=n_nan,
	)
	return stats


def capacity_factor_from_availability(
	availability: pd.DataFrame,
	*,
	capacity_per_sqkm: float,
	area_sqkm: float,
	installed_mw: float,
) -> pd.DataFrame:
	"""Convert a per-unit-of-area availability series into a capacity factor.

	``atlite``'s convertibles return output per unit of *area* given a layout.
	The conversion to a capacity factor needs the installed density, and doing
	it in the wrong direction is a factor-of-a-hundred error that still looks
	like a capacity factor. The check at the end is what catches it.
	"""
	assert capacity_per_sqkm > 0, "capacity density must be positive"
	assert area_sqkm > 0, "area must be positive"
	assert installed_mw > 0, "installed capacity must be positive"

	potential_mw = capacity_per_sqkm * area_sqkm
	if potential_mw <= 0:
		raise RenewableError("the layout yields no installable capacity")
	cf = availability.astype(float) * (installed_mw / potential_mw)
	# Clipping is deliberate and bounded: atlite rounds, and a 1e-9 overshoot is
	# not a modelling error. Anything larger is refused rather than clipped,
	# because clipping a real overshoot hides the unit error above.
	if float(cf.to_numpy().max()) > 1.0 + 1e-6 or float(cf.to_numpy().min()) < -1e-9:
		raise RenewableError(
			"converted capacity factor falls outside [0, 1]; check that "
			"capacity_per_sqkm and installed_mw are in the same units"
		)
	return cf.clip(lower=0.0, upper=1.0)


def attach_renewables(
	network: pypsa.Network,
	profiles: dict[str, pd.DataFrame],
	*,
	capital_cost_usd_per_mw: dict[str, float] | None = None,
	extendable: bool = True,
	source_id: str = "renewable_profiles",
	allow_nan: bool = False,
) -> dict[str, CapacityFactorStats]:
	"""Attach per-bus capacity-factor profiles as generators with ``p_max_pu``.

	Each carrier gets one generator per bus with the profile in ``p_max_pu``.
	The profile is the weather; the capacity is the decision variable when
	``extendable``.

	``capital_cost_usd_per_mw`` is required whenever ``extendable`` is true, and
	that is not a convenience default. An extendable generator with no capital
	cost is free capacity: the optimiser builds it to whatever the network can
	absorb, the objective drops by the whole cost of the build, and the result
	looks like a solution. It is the same defect as V2G storage without a
	degradation cost, which ``SectorConfig`` already refuses for the same reason.
	"""
	assert len(profiles) > 0, "no profiles to attach"
	assert len(network.buses) > 0, "network has no buses"
	if extendable:
		costs = capital_cost_usd_per_mw or {}
		missing_cost = [c for c in profiles if c not in costs]
		if missing_cost:
			raise RenewableError(
				f"extendable renewable(s) {', '.join(missing_cost)} have no "
				f"capital cost; free capacity is not a modelling result. Pass "
				f"capital_cost_usd_per_mw, or extendable=False for a fixed fleet."
			)

	costs = capital_cost_usd_per_mw or {}
	bus_set = {str(b) for b in network.buses.index}
	stats: dict[str, CapacityFactorStats] = {}
	for carrier, frame in profiles.items():
		check_carriers(pd.DataFrame({"carrier": [carrier]}), "carrier", artefact=source_id)
		PROFILE.check(
			pd.DataFrame(
				{
					"bus_id": list(frame.columns),
					"carrier": carrier,
					"timestamp": str(frame.index[0]),
					"capacity_factor": 0.0,
				}
			),
			artefact=f"profile:{carrier}",
		)
		missing = [str(b) for b in frame.columns if str(b) not in bus_set]
		if missing:
			raise RenewableError(
				f"{carrier}: profiles reference {len(missing)} bus(es) not in the "
				f"network, e.g. {', '.join(missing[:5])}"
			)
		stats[carrier] = validate_capacity_factors(frame, carrier=carrier, allow_nan=allow_nan)

		if network.snapshots.empty or len(network.snapshots) != len(frame):
			network.set_snapshots(pd.DatetimeIndex(frame.index))  # type: ignore[arg-type]
		for bus in frame.columns:
			name = f"{carrier}_{bus}"
			network.add(
				"Generator",
				name,
				bus=str(bus),
				carrier=carrier,
				p_nom=0.0,
				p_nom_extendable=extendable,
				capital_cost=float(costs.get(carrier, 0.0)),
				p_max_pu=1.0,
			)
			network.generators_t.p_max_pu[name] = frame[bus].to_numpy(dtype=float)
	logger.info("renewables_attached", carriers=len(profiles), snapshots=len(network.snapshots))
	return stats


def renewable_provenance(
	stats: dict[str, CapacityFactorStats],
	*,
	source_id: str = "renewable_profiles",
	inputs: list[str] | None = None,
	cutout: str = "africa-era5",
) -> DerivedProvenance:
	"""Provenance for a renewable profile artefact.

	The layout parameters go in. A capacity factor is only reproducible if the
	machine and the panel are described, and "atlite default" is not a
	description.
	"""
	assert len(stats) > 0, "no stats to record"
	return DerivedProvenance(
		source_id=source_id,
		inputs=inputs or [f"sha256:{source_id}:profiles"],
		basis=Basis.MODELLED,
		uncertainty=0.15,
		uncertainty_basis=(
			"layout sensitivity: turbine class, hub height, tilt and tracking "
			"move the capacity factor by 10-20%"
		),
		parameters={
			"cutout": cutout,
			"turbine_layout": TURBINE_LAYOUT,
			"solar_layout": SOLAR_LAYOUT,
			"stats": {carrier: s.as_dict() for carrier, s in stats.items()},
		},
		notes=(
			"Capacity factors are modelled from reanalysis meteorology, not "
			"measured at site. The layout parameters above are the assumption."
		),
	)


def annual_capacity_factor(profile: pd.Series) -> float:
	"""Annual capacity factor from an hourly per-unit series."""
	assert len(profile) > 0, "empty profile"
	value = float(profile.mean())
	if not math.isfinite(value):
		raise RenewableError("profile has no finite mean")
	return value


def carrier_of(name: str) -> str:
	"""The carrier from a ``{carrier}_{bus}`` generator name.

	Splits on the first underscore only: bus names contain underscores and a
	naive split takes the bus name apart.
	"""
	assert name, "empty generator name"
	return name.split("_", 1)[0]


__all__ = [
	"CF_MAX",
	"CF_MIN",
	"SOLAR_LAYOUT",
	"TURBINE_LAYOUT",
	"CapacityFactorStats",
	"RenewableError",
	"annual_capacity_factor",
	"attach_renewables",
	"capacity_factor_from_availability",
	"carrier_of",
	"renewable_provenance",
	"validate_capacity_factors",
]
