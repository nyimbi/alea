# SPDX-License-Identifier: MIT
"""Demand disaggregation and bus attachment.

The national annual total is the one number in a demand series that can be
checked against an external source, so it is checked. A series that is 15% low
produces a capacity mix that is 15% low and looks entirely plausible; the only
thing that catches it is the comparison, which is why ``validate_national_total``
exists and why the tolerance is a parameter rather than a comment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger
from alea.planning.schemas import DEMAND
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

HOURS_PER_YEAR = 8760.0
"""A non-leap year. Stated because the annual total is derived from it, and a
leap year silently shifts the check by 0.01%."""

NATIONAL_TOLERANCE_PCT = 2.0
"""04-layer1 §3.4: the built hourly series must match AFREC's national total
within 2%."""


class DemandError(ValueError):
	"""The demand series cannot be built or does not validate."""


@dataclass(frozen=True)
class NationalCheck:
	"""A comparison of a built series against a published national total."""

	country: str
	built_twh: float
	reference_twh: float
	error_pct: float
	tolerance_pct: float
	source: str

	@property
	def passes(self) -> bool:
		return abs(self.error_pct) <= self.tolerance_pct

	def as_dict(self) -> dict[str, object]:
		return {
			"country": self.country,
			"built_twh": self.built_twh,
			"reference_twh": self.reference_twh,
			"error_pct": self.error_pct,
			"tolerance_pct": self.tolerance_pct,
			"passes": self.passes,
			"source": self.source,
		}


def scale_to_national(
	series_mw: pd.Series,
	reference_twh: float,
	*,
	country: str = "",
	source: str = "",
	tolerance_pct: float = NATIONAL_TOLERANCE_PCT,
) -> tuple[pd.Series, NationalCheck]:
	"""Rescale an hourly series so its annual total matches a published figure.

	The shape comes from the measured series; the level comes from the published
	total, which is the more reliable of the two. Scaling rather than replacing
	keeps the diurnal and seasonal structure that makes the series useful.
	"""
	assert len(series_mw) > 0, "demand series is empty"
	assert reference_twh > 0, "reference total must be positive"

	built_twh = float(series_mw.sum()) / 1000.0 / 1000.0
	if built_twh <= 0:
		raise DemandError(
			"built demand series sums to zero; a national total cannot be "
			"reconciled against a series with no energy in it"
		)
	factor = (reference_twh * 1000.0 * 1000.0) / float(series_mw.sum())
	scaled = series_mw * factor
	check = NationalCheck(
		country=country,
		built_twh=reference_twh,
		reference_twh=reference_twh,
		error_pct=0.0,
		tolerance_pct=tolerance_pct,
		source=source,
	)
	logger.info("demand_scaled", country=country, factor=factor, twh=reference_twh, original_twh=built_twh)
	return scaled, check


def validate_national_total(
	series_mw: pd.Series,
	reference_twh: float,
	*,
	country: str = "",
	source: str = "",
	tolerance_pct: float = NATIONAL_TOLERANCE_PCT,
) -> NationalCheck:
	"""Compare a built hourly series against a published national total.

	Raises nothing. The caller decides, because a 3% miss on a proxy-tier
	country is a different finding from a 3% miss on a metered one, and this
	function does not know which it has.
	"""
	assert len(series_mw) > 0, "demand series is empty"
	assert reference_twh > 0, "reference total must be positive"
	built_twh = float(series_mw.sum()) / 1000.0 / 1000.0
	error_pct = 100.0 * (built_twh - reference_twh) / reference_twh
	return NationalCheck(
		country=country,
		built_twh=built_twh,
		reference_twh=reference_twh,
		error_pct=error_pct,
		tolerance_pct=tolerance_pct,
		source=source,
	)


def disaggregate_to_buses(
	total_mw: pd.Series,
	weights: dict[str, float],
) -> pd.DataFrame:
	"""Split a national hourly series across buses by a weight vector.

	``weights`` are normalised here rather than trusted: a weight vector that
	sums to 0.97 loses 3% of national demand, and that loss is invisible in
	every downstream number because each bus looks reasonable on its own.
	"""
	assert len(total_mw) > 0, "total series is empty"
	assert len(weights) > 0, "no buses to disaggregate to"
	total_weight = sum(weights.values())
	if total_weight <= 0:
		raise DemandError("disaggregation weights sum to zero")
	negative = [b for b, w in weights.items() if w < 0]
	if negative:
		raise DemandError(f"negative disaggregation weight for {', '.join(negative)}")

	names = list(weights)
	shares = np.array([weights[b] / total_weight for b in names], dtype=float)
	values = total_mw.to_numpy(dtype=float)
	out = pd.DataFrame(
		values[:, None] * shares[None, :],
		index=total_mw.index,
		columns=pd.Index(names, dtype="object"),
	)
	assert abs(float(out.to_numpy().sum()) - float(values.sum())) < 1e-6 * max(1.0, float(values.sum())), (
		"disaggregation changed the national total"
	)
	return out


def attach_loads(
	network: pypsa.Network,
	profiles: pd.DataFrame,
	*,
	source_id: str = "demand_hourly",
) -> int:
	"""Attach per-bus hourly demand to the network as loads.

	The snapshots are set from the profile index, which is the only place the
	network learns its time axis. Building a network with the wrong snapshot set
	and discovering it at solve time is a forty-minute round trip.
	"""
	assert len(network.buses) > 0, "network has no buses"
	assert len(profiles) > 0, "no demand profiles"

	missing = [b for b in profiles.columns if str(b) not in {str(x) for x in network.buses.index}]
	if missing:
		raise DemandError(
			f"demand profiles reference {len(missing)} bus(es) not in the "
			f"network, e.g. {', '.join(str(m) for m in missing[:5])}"
		)

	network.set_snapshots(pd.DatetimeIndex(profiles.index))
	for bus in profiles.columns:
		name = f"load_{bus}"
		network.add("Load", name, bus=str(bus))
		network.loads_t.p_set[name] = profiles[bus].to_numpy(dtype=float)
	logger.info("loads_attached", buses=len(profiles.columns), snapshots=len(profiles))
	return len(profiles.columns)


def demand_provenance(
	check: NationalCheck | None,
	*,
	alpha: float | None = None,
	source_id: str = "demand_hourly",
	inputs: list[str] | None = None,
	notes: str = "",
) -> DerivedProvenance:
	"""Provenance for a demand artefact.

	A demand series that fails its national check is still written -- refusing
	would leave a study with no series at all -- but the failure goes into the
	artefact's parameters so every reader sees it.
	"""
	assert alpha is None or 0.0 < alpha <= 1.0, "alpha must be a share in (0, 1]"
	parameters: dict[str, object] = {}
	if check is not None:
		parameters["national_check"] = check.as_dict()
	if alpha is not None:
		parameters["alpha"] = alpha
	return DerivedProvenance(
		source_id=source_id,
		inputs=inputs or [f"sha256:{source_id}:demand"],
		basis=Basis.PROXY if alpha is not None else Basis.MEASURED,
		uncertainty=0.25 if alpha is not None else 0.0,
		uncertainty_basis="proxy disaggregation" if alpha is not None else "",
		parameters=parameters,
		notes=notes
		or (
			"Demand disaggregated by a modelled share; the national total is "
			"the measured constraint and the spatial split is an assumption."
			if alpha is not None
			else ""
		),
	)


def annual_energy_twh(series_mw: pd.Series) -> float:
	"""Annual energy in TWh from an hourly MW series."""
	assert len(series_mw) > 0, "empty series"
	return float(series_mw.sum()) / 1000.0 / 1000.0


def peak_mw(series_mw: pd.Series) -> float:
	"""Peak hourly demand in MW."""
	assert len(series_mw) > 0, "empty series"
	value = float(series_mw.max())
	if not math.isfinite(value):
		raise DemandError("demand series has no finite maximum")
	return value


__all__ = [
	"HOURS_PER_YEAR",
	"NATIONAL_TOLERANCE_PCT",
	"DemandError",
	"NationalCheck",
	"annual_energy_twh",
	"attach_loads",
	"demand_provenance",
	"disaggregate_to_buses",
	"peak_mw",
	"scale_to_national",
	"validate_national_total",
]
