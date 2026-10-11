# SPDX-License-Identifier: MIT
"""Temporal and spatial aggregation, and the harness that validates them.

Both levers are silent changes to the answer. Reducing 8760 hours to 12
representative periods, or 55 countries to 8 nodes, produces a solve that
completes and a capacity mix that is wrong by a few percent with nothing in the
output saying so.

The gate is the point of this module. A config selecting ``time_aggregation > 1``
is refused unless a validation artefact exists for that exact network *and*
records errors inside tolerance. The artefact is written by solving twice, which
is expensive, so it is written once per network and read many times.

A validation artefact that records an out-of-tolerance error is a failed gate,
not a passing one with a caveat. That is the difference between a gate and a
report: the config load refuses either way, and the artefact's numbers are what
tell the operator how far off the fast path is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pypsa
from pydantic import BaseModel, ConfigDict

from alea._core import aggregate as _kernel_aggregate
from alea._core import validate_aggregation as _kernel_validate
from alea.io.artefacts import artefact_exists, read_artefact, write_artefact
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

TOLERANCE_COST_PCT = 2.0
"""AD-9. Total system cost may move 2% under aggregation."""

TOLERANCE_MIX_PCT = 5.0
"""AD-9. The capacity mix, as L1 distance on shares, may move 5%."""


class AggregationError(ValueError):
	"""An aggregation cannot be built, or its validation does not hold."""


class AggregationValidation(BaseModel):
	"""The measured cost of aggregating one network.

	Every field is a measurement. There is no overall pass/fail boolean stored
	here, because ``passes`` is a function of the tolerances in force at read
	time and a stored boolean would freeze the answer to a question the reader
	may be asking differently.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	network_id: str
	n_periods: int
	period_length: int
	n_clusters: int
	tolerance_cost_pct: float = TOLERANCE_COST_PCT
	tolerance_mix_pct: float = TOLERANCE_MIX_PCT
	cost_error_pct: float
	capacity_mix_l1_error_pct: float
	emissions_error_pct: float
	peak_price_error_pct: float
	full_cost: float
	aggregated_cost: float
	n_snapshots_full: int
	n_snapshots_aggregated: int

	@property
	def passes(self) -> bool:
		return (
			abs(self.cost_error_pct) <= self.tolerance_cost_pct
			and abs(self.capacity_mix_l1_error_pct) <= self.tolerance_mix_pct
		)

	@property
	def speedup(self) -> float:
		"""Snapshots removed per snapshot kept. A number worth reporting."""
		if self.n_snapshots_aggregated == 0:
			return 0.0
		return self.n_snapshots_full / self.n_snapshots_aggregated


def network_id(network: pypsa.Network) -> str:
	"""A stable identity for a network's structure.

	Derived from bus and line names and capacities, not from the object or the
	file. Two networks built by different routes from the same data must share
	an id, or a validation artefact written for one is refused for the other and
	the operator re-runs an expensive validation for no reason.
	"""
	assert network is not None, "network must not be None"
	parts = [f"b:{b}" for b in sorted(str(x) for x in network.buses.index)]
	parts += [
		f"l:{row['bus0']}>{row['bus1']}:{float(row.get('s_nom', 0.0)):.3f}"
		for _, row in network.lines.sort_index().iterrows()
	]
	payload = "\n".join(parts).encode("utf-8")
	import hashlib

	return hashlib.sha256(payload).hexdigest()[:16]


def validation_path(network_id_value: str, root: str | Path = "results/aggregation") -> Path:
	"""Where a network's validation artefact lives."""
	assert network_id_value, "network id must not be empty"
	return Path(root) / f"{network_id_value}.json"


def build_aggregation(
	series: np.ndarray,
	n_periods: int,
	period_length: int,
	seed: int = 0,
) -> dict[str, Any]:
	"""Aggregate a ``[time, ...]`` array into representative periods.

	Delegates to the Rust kernel, which guarantees the weights sum to the number
	of timesteps exactly. The guarantee is the reason the kernel raises instead
	of returning a near-miss: a weighting that sums to 8758 shifts every annual
	total by 0.02%, systematically, across a whole study.
	"""
	assert series.ndim >= 1, "series must have a time axis"
	assert n_periods > 0, "n_periods must be positive"
	assert period_length > 0, "period_length must be positive"
	if n_periods * period_length > series.shape[0]:
		raise AggregationError(
			f"{n_periods} periods of {period_length} need "
			f"{n_periods * period_length} timesteps but the series has "
			f"{series.shape[0]}"
		)
	flat = series.reshape(series.shape[0], -1).astype(np.float32, copy=False)
	assignments, representatives, weights = _kernel_aggregate(flat, n_periods, period_length, seed)
	logger.info(
		"aggregated",
		n_periods=n_periods,
		period_length=period_length,
		timesteps=int(series.shape[0]),
	)
	return {
		"assignments": assignments,
		"representatives": representatives,
		"weights": weights,
		"shape": series.shape,
	}


def capacity_mix(network: pypsa.Network) -> dict[str, float]:
	"""Installed capacity by carrier, MW."""
	assert network is not None, "network must not be None"
	mix: dict[str, float] = {}
	for _, row in network.generators.iterrows():
		carrier = str(row["carrier"])
		p_nom = row.get("p_nom", 0.0)
		optimal = row.get("p_nom_opt", 0.0)
		value = float(optimal) if optimal and float(optimal) > 0 else float(p_nom or 0.0)
		mix[carrier] = mix.get(carrier, 0.0) + value
	for _, row in network.storage_units.iterrows():
		carrier = str(row["carrier"])
		optimal = row.get("p_nom_opt", 0.0)
		value = float(optimal) if optimal and float(optimal) > 0 else float(row.get("p_nom", 0.0) or 0.0)
		mix[carrier] = mix.get(carrier, 0.0) + value
	return mix


def mix_shares(mix: dict[str, float]) -> dict[str, float]:
	"""Normalise a capacity mix to shares summing to one."""
	total = sum(mix.values())
	if total <= 0:
		return {k: 0.0 for k in mix}
	return {k: v / total for k, v in mix.items()}


def l1_mix_distance(a: dict[str, float], b: dict[str, float]) -> float:
	"""L1 distance in percentage points between two capacity mixes.

	Expressed in percentage points, not as a fraction, because AD-9's 5% is a
	statement about shares and a fraction would make the tolerance 100x looser
	than it reads.
	"""
	assert a is not None and b is not None, "both mixes are required"
	sa, sb = mix_shares(a), mix_shares(b)
	carriers = set(sa) | set(sb)
	return 100.0 * sum(abs(sa.get(c, 0.0) - sb.get(c, 0.0)) for c in carriers)


def total_cost(network: pypsa.Network) -> float:
	"""The objective value of a solved network."""
	assert network is not None, "network must not be None"
	objective = getattr(network, "objective", None)
	if objective is None:
		raise AggregationError("network has no objective; solve it before comparing")
	return float(objective)


def total_emissions(network: pypsa.Network) -> float:
	"""Generation-weighted CO2 in tonnes, from the registry's intensities."""
	from alea.registry import Carrier, get_technology

	assert network is not None, "network must not be None"
	if not len(network.generators_t.p):
		raise AggregationError("network has no dispatch; solve it before comparing")
	total = 0.0
	for column in network.generators_t.p.columns:
		carrier = str(network.generators.at[column, "carrier"])
		try:
			intensity = get_technology(Carrier(carrier)).co2_t_per_mwh
		except (ValueError, KeyError):
			intensity = 0.0
		total += float(network.generators_t.p[column].sum()) * intensity
	return total


def peak_price(network: pypsa.Network) -> float:
	"""The highest marginal price across buses and snapshots."""
	assert network is not None, "network must not be None"
	if not len(network.buses_t.marginal_price):
		raise AggregationError("network has no marginal prices; solve it before comparing")
	return float(network.buses_t.marginal_price.to_numpy().max())


def validate_aggregation_artefact(
	network: pypsa.Network,
	aggregated: pypsa.Network,
	*,
	n_periods: int,
	period_length: int,
	n_clusters: int = 1,
	tolerance_cost_pct: float = TOLERANCE_COST_PCT,
	tolerance_mix_pct: float = TOLERANCE_MIX_PCT,
) -> AggregationValidation:
	"""Compare an aggregated solve against a full-resolution one.

	Both networks must already be solved. The measurements come from the Rust
	kernel so that the definition of "cost error" is one implementation, shared
	with anything else that measures it.
	"""
	assert network is not None and aggregated is not None, "both networks are required"
	full_mix = capacity_mix(network)
	agg_mix = capacity_mix(aggregated)
	carriers = sorted(set(full_mix) | set(agg_mix))
	full_capacity = np.array([full_mix.get(c, 0.0) for c in carriers], dtype=np.float64)
	agg_capacity = np.array([agg_mix.get(c, 0.0) for c in carriers], dtype=np.float64)

	measurements = _kernel_validate(
		full_capacity,
		agg_capacity,
		total_cost(network),
		total_cost(aggregated),
		total_emissions(network),
		total_emissions(aggregated),
		peak_price(network),
		peak_price(aggregated),
	)

	validation = AggregationValidation(
		network_id=network_id(network),
		n_periods=n_periods,
		period_length=period_length,
		n_clusters=n_clusters,
		tolerance_cost_pct=tolerance_cost_pct,
		tolerance_mix_pct=tolerance_mix_pct,
		cost_error_pct=measurements["total_cost_error_pct"],
		capacity_mix_l1_error_pct=measurements["capacity_mix_l1_error_pct"],
		emissions_error_pct=measurements["emissions_error_pct"],
		peak_price_error_pct=measurements["peak_price_error_pct"],
		full_cost=total_cost(network),
		aggregated_cost=total_cost(aggregated),
		n_snapshots_full=len(network.snapshots),
		n_snapshots_aggregated=len(aggregated.snapshots),
	)
	logger.info(
		"aggregation_validated",
		network=validation.network_id,
		cost_error_pct=validation.cost_error_pct,
		mix_error_pct=validation.capacity_mix_l1_error_pct,
		passes=validation.passes,
	)
	return validation


def write_validation(
	validation: AggregationValidation,
	*,
	root: str | Path = "results/aggregation",
	inputs: list[str] | None = None,
) -> Path:
	"""Persist a validation artefact.

	Written even when it fails. A failing measurement on disk is how the
	operator learns the fast path is 8% off; refusing to write it leaves the
	config gate reporting "no artefact" instead of "artefact says 8%".
	"""
	assert validation is not None, "validation must not be None"
	path = validation_path(validation.network_id, root)
	provenance = DerivedProvenance(
		source_id="aggregation_validation",
		inputs=inputs or [f"sha256:network:{validation.network_id}"],
		basis=Basis.MODELLED,
		uncertainty=abs(validation.cost_error_pct) / 100.0,
		uncertainty_basis="measured cost error of the aggregated solve",
		parameters=validation.model_dump(),
		notes=(
			f"cost error {validation.cost_error_pct:.3f}%, mix error "
			f"{validation.capacity_mix_l1_error_pct:.3f}%; "
			f"{'within' if validation.passes else 'OUTSIDE'} tolerance"
		),
	)
	path.parent.mkdir(parents=True, exist_ok=True)
	write_artefact(path, validation.model_dump(), provenance, format="json")
	logger.info("aggregation_validation_written", path=str(path), passes=validation.passes)
	return path


def load_validation(
	network_id_value: str,
	*,
	root: str | Path = "results/aggregation",
) -> AggregationValidation | None:
	"""Read a network's validation artefact, or None if there is none.

	Returns None rather than raising: "no validation has been run" and "the
	validation failed" are different findings and the gate reports them
	differently.
	"""
	assert network_id_value, "network id must not be empty"
	path = validation_path(network_id_value, root)
	if not artefact_exists(path):
		return None
	payload, _ = read_artefact(path, verify=False)
	if isinstance(payload, str):
		payload = json.loads(payload)
	return AggregationValidation.model_validate(payload)


def require_aggregation_validation(
	network: pypsa.Network,
	n_periods: int,
	*,
	root: str | Path = "results/aggregation",
) -> AggregationValidation:
	"""Refuse an aggregated solve that has not been measured (AD-9).

	The single most important gate in Layer 1. Aggregation without measurement
	is how a platform reports a capacity mix that is 8% off and cannot say so.
	"""
	assert n_periods > 1, "this gate only applies above full resolution"
	identifier = network_id(network)
	validation = load_validation(identifier, root=root)
	if validation is None:
		raise AggregationError(
			f"time_aggregation={n_periods} selected for network {identifier!r} "
			f"but no validation artefact exists. Run `alea validate aggregation` "
			f"first."
		)
	if validation.n_periods != n_periods:
		raise AggregationError(
			f"validation for network {identifier!r} was measured at "
			f"time_aggregation={validation.n_periods}, not {n_periods}; the "
			f"measurement does not transfer between levels"
		)
	if not validation.passes:
		raise AggregationError(
			f"validation for network {identifier!r} FAILS: cost error "
			f"{validation.cost_error_pct:.3f}% (tolerance "
			f"{validation.tolerance_cost_pct}%), mix error "
			f"{validation.capacity_mix_l1_error_pct:.3f}% (tolerance "
			f"{validation.tolerance_mix_pct}%). Aggregation at this level is not "
			f"usable for this network."
		)
	return validation


def cluster_buses(
	network: pypsa.Network,
	n_clusters: int,
	*,
	seed: int = 0,
	features: tuple[str, ...] = ("lon", "lat"),
) -> dict[str, str]:
	"""Assign each bus to one of ``n_clusters`` spatial clusters.

	Returns bus -> cluster label. k-means on bus coordinates with a fixed seed;
	the label is the index of the nearest centroid, ordered by longitude so the
	numbering is geographic and stable rather than arbitrary.
	"""
	assert n_clusters >= 1, "n_clusters must be at least 1"
	assert len(network.buses) >= n_clusters, (
		f"{n_clusters} clusters requested for {len(network.buses)} buses"
	)
	from sklearn.cluster import KMeans

	assert all(f in network.buses.columns for f in features), (
		f"bus table lacks feature(s) {[f for f in features if f not in network.buses.columns]}"
	)
	points = network.buses[list(features)].to_numpy(dtype=float)
	km = KMeans(n_clusters=n_clusters, random_state=seed, n_init="auto")
	labels = km.fit_predict(points)
	order = np.argsort(km.cluster_centers_[:, 0])
	remap = {int(old): int(new) for new, old in enumerate(order)}
	return {str(bus): f"cluster_{remap[int(labels[i])]:03d}" for i, bus in enumerate(network.buses.index)}


def cluster_provenance(
	mapping: dict[str, str],
	*,
	n_clusters: int,
	seed: int,
	inputs: list[str] | None = None,
) -> DerivedProvenance:
	"""Provenance for a spatial clustering."""
	assert len(mapping) > 0, "empty clustering"
	return DerivedProvenance(
		source_id="spatial_clustering",
		inputs=inputs or ["sha256:network:topology"],
		basis=Basis.MODELLED,
		uncertainty=0.05,
		uncertainty_basis="spatial aggregation changes locational prices and line loading",
		parameters={
			"n_clusters": n_clusters,
			"seed": seed,
			"n_buses": len(mapping),
			"mapping": mapping,
		},
		notes="k-means on bus coordinates; clusters are a spatial approximation, not synchronous areas.",
	)


__all__ = [
	"TOLERANCE_COST_PCT",
	"TOLERANCE_MIX_PCT",
	"AggregationError",
	"AggregationValidation",
	"build_aggregation",
	"capacity_mix",
	"cluster_buses",
	"cluster_provenance",
	"l1_mix_distance",
	"load_validation",
	"mix_shares",
	"network_id",
	"peak_price",
	"require_aggregation_validation",
	"total_cost",
	"total_emissions",
	"validate_aggregation_artefact",
	"validation_path",
	"write_validation",
]
