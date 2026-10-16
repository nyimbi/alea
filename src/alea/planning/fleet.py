# SPDX-License-Identifier: MIT
"""Generator fleet attachment.

Every plant attaches to its nearest bus, and the ones that cannot are reported
rather than moved. A plant attached to a bus 200 km away is not a small
approximation: it moves generation across the network's spatial structure and
hides the missing line that would have connected it. The count of unattached
plants is a data-quality finding, so it is a return value and an artefact field,
not a log line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger
from alea.planning.schemas import FLEET, check_carriers
from alea.planning.topology import METRES_PER_DEG_LAT, METRES_PER_DEG_LON_EQUATOR
from alea.provenance.models import Basis, DerivedProvenance
from alea.registry import Carrier, get_technology

logger = get_logger(__name__)

DEFAULT_LIFETIME_YEARS = 30
"""Applied where the source omits a lifetime, which most African plant registers do."""

DEFAULT_EFFICIENCY = 0.40
"""Thermal efficiency where the source has none. Recorded in provenance, because
a heat rate nobody measured is a cost nobody can defend."""

MARGINAL_COST_USD_PER_MWH: dict[str, float] = {
	"coal": 45.0,
	"gas": 65.0,
	"oil": 120.0,
	"nuclear": 12.0,
	"biomass": 55.0,
	"waste": 40.0,
	"geothermal": 8.0,
	"hydro": 3.0,
	"ror": 3.0,
	"solar": 1.0,
	"csp": 1.0,
	"onwind": 1.0,
	"offwind": 1.0,
}
"""Short-run marginal cost placeholders, USD/MWh.

Layer 3 replaces these with a fuel price series and a carbon price. They exist
here so a Layer 1 dispatch is not economically arbitrary; they are recorded in
provenance precisely because they are placeholders.
"""


FLEET_COVERAGE_TOLERANCE_PCT = 10.0
"""`02-data-pipeline.md` §6 criterion 2: the built fleet must cover > 90% of the
published national installed capacity. The tolerance is the complement of that
threshold, stated as a miss so it reads the same way as the demand analogue's."""


class FleetError(ValueError):
	"""The fleet cannot be attached to the network."""


@dataclass(frozen=True)
class FleetCoverage:
	"""A comparison of a built fleet against a published national capacity total.

	Carrier-level, not just a total. Two fleets can sum to the same megawatts
	with entirely different mixes, and the failure that matters -- a missing
	technology -- is invisible in the total while being the whole finding. The
	missing dictionary is therefore the point of the check, not a detail on it.
	"""

	country: str
	built_mw: float
	reference_mw: float
	coverage_pct: float
	tolerance_pct: float
	source: str
	missing_mw: dict[str, float] = field(default_factory=dict)
	excess_mw: dict[str, float] = field(default_factory=dict)

	@property
	def passes(self) -> bool:
		return self.coverage_pct >= 100.0 - self.tolerance_pct

	@property
	def missing_carriers(self) -> list[str]:
		return sorted(self.missing_mw)

	def as_dict(self) -> dict[str, object]:
		return {
			"country": self.country,
			"built_mw": self.built_mw,
			"reference_mw": self.reference_mw,
			"coverage_pct": self.coverage_pct,
			"tolerance_pct": self.tolerance_pct,
			"passes": self.passes,
			"source": self.source,
			"missing_mw": dict(self.missing_mw),
			"excess_mw": dict(self.excess_mw),
		}


@dataclass
class AttachmentReport:
	"""Which plants attached where, and which did not."""

	n_plants: int
	n_attached: int
	n_beyond_reach: int
	n_unknown_carrier: int
	max_attach_km: float
	unattached: list[dict[str, object]] = field(default_factory=list)
	carrier_mw: dict[str, float] = field(default_factory=dict)

	def as_dict(self) -> dict[str, object]:
		return {
			"n_plants": self.n_plants,
			"n_attached": self.n_attached,
			"n_beyond_reach": self.n_beyond_reach,
			"n_unknown_carrier": self.n_unknown_carrier,
			"max_attach_km": self.max_attach_km,
			"carrier_mw": dict(self.carrier_mw),
		}


def nearest_bus(
	bus_lon: np.ndarray,
	bus_lat: np.ndarray,
	lon: float,
	lat: float,
) -> tuple[int, float]:
	"""Index of the nearest bus and its distance in km.

	Brute force. A continental network is a few thousand buses and a fleet is a
	few thousand plants, so this is a few million distance evaluations -- under a
	second, and it removes a spatial-index dependency whose failure mode
	(silently dropping a plant outside its bounding box) is worse than the cost.
	"""
	assert len(bus_lon) == len(bus_lat), "bus coordinates must be paired"
	assert len(bus_lon) > 0, "no buses to attach to"
	dlon = (bus_lon - lon) * np.cos(np.radians(0.5 * (bus_lat + lat))) * (METRES_PER_DEG_LON_EQUATOR / 1000.0)
	dlat = (bus_lat - lat) * (METRES_PER_DEG_LAT / 1000.0)
	d = np.sqrt(dlon * dlon + dlat * dlat)
	i = int(np.argmin(d))
	return i, float(d[i])


def attach_generators(
	network: pypsa.Network,
	fleet: pd.DataFrame,
	*,
	max_attach_km: float = 50.0,
	source_id: str = "power_plants",
	strict_carriers: bool = False,
) -> AttachmentReport:
	"""Attach each plant to its nearest bus.

	A plant further than ``max_attach_km`` from any bus is reported, not
	silently attached. ``strict_carriers`` refuses an unknown carrier outright;
the default records it and skips the plant, because a continental fleet scrape
routinely contains one new carrier and failing the whole build on it is the
wrong trade.
	"""
	assert max_attach_km > 0, "max_attach_km must be positive"
	assert len(network.buses) > 0, "network has no buses to attach a fleet to"

	FLEET.check(fleet, artefact="fleet")
	if strict_carriers:
		check_carriers(fleet, "carrier", artefact="fleet")

	known = {c.value for c in Carrier}
	bus_names = [str(b) for b in network.buses.index]
	bus_lon = network.buses["lon"].to_numpy(dtype=float)
	bus_lat = network.buses["lat"].to_numpy(dtype=float)

	unattached: list[dict[str, object]] = []
	carrier_mw: dict[str, float] = {}
	n_attached = 0
	n_unknown = 0

	for _, row in fleet.iterrows():
		carrier = str(row["carrier"])
		capacity = float(row["capacity_mw"])
		if not math.isfinite(capacity) or capacity <= 0.0:
			# A zero-capacity plant is a register artefact, not a plant.
			continue
		if carrier not in known:
			n_unknown += 1
			unattached.append(
				{
					"plant_id": str(row["plant_id"]),
					"reason": "unknown_carrier",
					"carrier": carrier,
					"capacity_mw": capacity,
				}
			)
			continue

		idx, km = nearest_bus(bus_lon, bus_lat, float(row["lon"]), float(row["lat"]))
		if km > max_attach_km:
			unattached.append(
				{
					"plant_id": str(row["plant_id"]),
					"reason": "beyond_reach",
					"nearest_bus": bus_names[idx],
					"distance_km": round(km, 2),
					"capacity_mw": capacity,
				}
			)
			continue

		technology = get_technology(Carrier(carrier))
		year = int(row["commissioning_year"])
		lifetime = int(row["lifetime_years"]) if pd.notna(row["lifetime_years"]) else DEFAULT_LIFETIME_YEARS
		name = f"{row['plant_id']}"
		network.add(
			"Generator",
			name,
			bus=bus_names[idx],
			carrier=carrier,
			p_nom=capacity,
			build_year=year,
			lifetime=lifetime,
			p_nom_extendable=False,
			marginal_cost=MARGINAL_COST_USD_PER_MWH.get(carrier, 0.0),
			efficiency=1.0 if technology.renewable else DEFAULT_EFFICIENCY,
			committable=False,
		)
		n_attached += 1
		carrier_mw[carrier] = carrier_mw.get(carrier, 0.0) + capacity

	report = AttachmentReport(
		n_plants=int(len(fleet)),
		n_attached=n_attached,
		n_beyond_reach=sum(1 for u in unattached if u["reason"] == "beyond_reach"),
		n_unknown_carrier=n_unknown,
		max_attach_km=max_attach_km,
		unattached=unattached,
		carrier_mw=carrier_mw,
	)
	logger.info(
		"fleet_attached",
		plants=report.n_plants,
		attached=n_attached,
		beyond_reach=report.n_beyond_reach,
		unknown_carrier=n_unknown,
	)
	return report


def fleet_provenance(
	report: AttachmentReport,
	*,
	source_id: str = "power_plants",
	inputs: list[str] | None = None,
) -> DerivedProvenance:
	"""Provenance for the attached fleet.

	The unattached list goes into the parameters, not a log. A report that
	quotes a national capacity total is quoting a total that excludes every
	plant this function could not place, and the reader is entitled to see how
	many that was.
	"""
	assert report is not None, "report must not be None"
	return DerivedProvenance(
		source_id=source_id,
		inputs=inputs or [f"sha256:{source_id}:fleet"],
		basis=Basis.MEASURED,
		uncertainty=0.0,
		parameters={
			**report.as_dict(),
			"marginal_cost_usd_per_mwh": MARGINAL_COST_USD_PER_MWH,
			"default_efficiency": DEFAULT_EFFICIENCY,
			"default_lifetime_years": DEFAULT_LIFETIME_YEARS,
		},
		notes=(
			"Marginal costs are placeholders pending Layer 3's fuel price series. "
			f"{report.n_beyond_reach} plant(s) beyond reach and "
			f"{report.n_unknown_carrier} with an unknown carrier are excluded "
			"from the attached fleet."
		),
	)


def validate_fleet_coverage(
	carrier_mw: dict[str, float],
	reference_mw: dict[str, float] | float,
	*,
	country: str = "",
	source: str = "",
	tolerance_pct: float = FLEET_COVERAGE_TOLERANCE_PCT,
) -> FleetCoverage:
	"""Compare a built fleet against a published national capacity total.

	``02-data-pipeline.md`` §6 calls this "the one to watch", and the reason is
	arithmetic rather than taste: a fleet covering 60% of national capacity
	produces a capacity mix that looks plausible and is wrong, because the
	optimiser expands into the hole the missing plants left. Nothing downstream
	can see it -- the network solves, the balance closes, the mix is a mix.

	``reference_mw`` is either a national total in MW, or a mapping of carrier
	to MW. The mapping form is the one that names what is missing; the scalar
	form answers only "how much", so it reports a total miss with no carriers.
	Both are accepted because a source may publish only the aggregate, and
	refusing that would leave the check unrunnable against a real total.

	Raises nothing. As with ``validate_national_total``, the caller decides: a
	10% miss on a fleet whose export is known to omit distributed solar is a
	different finding from one that omits a 300 MW geothermal field.
	"""
	if not carrier_mw:
		raise FleetError(
			"the built fleet holds no capacity; a national total cannot be "
			"reconciled against a fleet with nothing in it"
		)
	if isinstance(reference_mw, dict):
		assert reference_mw, "the reference capacity mapping is empty"
		reference_total = float(sum(reference_mw.values()))
		reference_by_carrier = {str(k): float(v) for k, v in reference_mw.items()}
	else:
		reference_total = float(reference_mw)
		reference_by_carrier = {}
	if reference_total <= 0.0:
		raise FleetError("the reference capacity total is not positive")

	built_total = float(sum(carrier_mw.values()))
	if built_total <= 0.0:
		raise FleetError(
			"the built fleet holds no capacity; a national total cannot be "
			"reconciled against a fleet with nothing in it"
		)

	# Per-carrier only where the reference is per-carrier. Deriving a carrier
	# breakdown from a scalar reference would invent a mix the source never
	# stated, which is the defect this check exists to catch, one level up.
	missing: dict[str, float] = {}
	excess: dict[str, float] = {}
	if reference_by_carrier:
		built_by_carrier = {str(k): float(v) for k, v in carrier_mw.items()}
		for carrier, wanted in reference_by_carrier.items():
			gap = wanted - built_by_carrier.get(carrier, 0.0)
			if gap > 0.0:
				missing[carrier] = gap
			elif gap < 0.0:
				excess[carrier] = -gap
		for carrier, have in built_by_carrier.items():
			if carrier not in reference_by_carrier:
				excess[carrier] = have

	coverage_pct = 100.0 * built_total / reference_total
	return FleetCoverage(
		country=country,
		built_mw=built_total,
		reference_mw=reference_total,
		coverage_pct=coverage_pct,
		tolerance_pct=tolerance_pct,
		source=source,
		missing_mw=missing,
		excess_mw=excess,
	)


def attach_extendable_candidates(
	network: pypsa.Network,
	carriers: list[str],
	*,
	capital_cost_usd_per_mw: dict[str, float],
	bus_names: list[str] | None = None,
) -> int:
	"""Add one extendable generator per (carrier, bus) for capacity expansion.

	Capacity expansion needs a candidate at every bus it might build at, which
	is the whole point of a spatially resolved model. Adding one candidate per
	carrier instead would make the model continental-uniform and its answer
	would be a single number.
	"""
	assert len(carriers) > 0, "no candidate carriers"
	assert len(network.buses) > 0, "no buses"
	missing = [c for c in carriers if c not in capital_cost_usd_per_mw]
	if missing:
		raise FleetError(f"no capital cost for candidate carrier(s) {', '.join(missing)}")

	known = {c.value for c in Carrier}
	unknown = [c for c in carriers if c not in known]
	if unknown:
		raise FleetError(f"unknown candidate carrier(s) {', '.join(unknown)}")

	# A variable renewable candidate added here would have no ``p_max_pu``, so
	# the optimiser would treat it as a plant that generates at nameplate every
	# hour of the year. That is a solar farm with a capacity factor of 1.0 and it
	# makes renewables look free. VRE candidates come from ``attach_renewables``,
	# which carries the profile.
	variable = [c for c in carriers if get_technology(Carrier(c)).variable]
	if variable:
		raise FleetError(
			f"variable renewable(s) {', '.join(variable)} cannot be added as "
			f"bare candidates: without a capacity-factor profile they generate at "
			f"nameplate every hour. Use alea.planning.renewables.attach_renewables."
		)

	targets = bus_names if bus_names is not None else [str(b) for b in network.buses.index]
	added = 0
	for bus in targets:
		for carrier in carriers:
			technology = get_technology(Carrier(carrier))
			network.add(
				"Generator",
				f"cand_{carrier}_{bus}",
				bus=bus,
				carrier=carrier,
				p_nom=0.0,
				p_nom_extendable=True,
				capital_cost=float(capital_cost_usd_per_mw[carrier]),
				marginal_cost=MARGINAL_COST_USD_PER_MWH.get(carrier, 0.0),
				efficiency=1.0 if technology.renewable else DEFAULT_EFFICIENCY,
			)
			added += 1
	logger.info("candidates_added", count=added, carriers=len(carriers), buses=len(targets))
	return added


__all__ = [
	"DEFAULT_EFFICIENCY",
	"DEFAULT_LIFETIME_YEARS",
	"FLEET_COVERAGE_TOLERANCE_PCT",
	"MARGINAL_COST_USD_PER_MWH",
	"AttachmentReport",
	"FleetCoverage",
	"FleetError",
	"attach_extendable_candidates",
	"attach_generators",
	"fleet_provenance",
	"nearest_bus",
	"validate_fleet_coverage",
]
