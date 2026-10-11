# SPDX-License-Identifier: MIT
"""Result extraction from a solved network.

WHY this is a separate module from the engine: a result is a *value* — the
thing that is cached, persisted, and plotted. Building it in the engine would
make the engine's internal network the only thing that could produce it, and a
stored scenario could then only be re-derived by re-solving. Extraction as a
pure function over a solved network means a stored result can be checked
against a fresh solve without re-running the optimiser.

Units are in every field name. ``renewable_share`` is ``None`` when total
generation is zero, never 0 — the specification returns 0, which asserts "no
renewable generation" for a network that generated nothing at all.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea._uuid7 import uuid7str
from alea.registry.technologies import get_technology, is_known_carrier
from alea.whatif.params import ScenarioParameters
from alea.whatif.views import RiskMetrics, ScenarioResult, renewable_share

_LOAD_SHEDDING_CARRIERS = frozenset({"load shedding", "load_shedding", "load-shedding"})


def extract(
	network: pypsa.Network,
	params: ScenarioParameters,
	*,
	network_checksum: str,
	code_version: str,
	risk: RiskMetrics | None = None,
	basis_uncertainty: tuple[Any, float] | None = None,
) -> ScenarioResult:
	"""Summarise a solved network.

	``risk`` is passed in rather than computed here because the risk metrics
	need a distribution of costs, which Layer 3's market model produces; the
	what-if engine does not own that physics.
	"""
	assert isinstance(network, pypsa.Network)
	assert isinstance(params, ScenarioParameters)
	assert network_checksum, "a result that does not name its network is not reproducible"

	capacity_mix = _capacity_mix_mw(network)
	generation = _generation_mwh(network)
	unserved = _unserved_energy_mwh(network, generation)
	mean_price, volatility = _price_statistics(network)

	basis = basis_uncertainty[0] if basis_uncertainty else _default_basis()
	uncertainty = basis_uncertainty[1] if basis_uncertainty else 0.0

	result = ScenarioResult(
		scenario_id=uuid7str(),
		params=params,
		network_checksum=network_checksum,
		code_version=code_version,
		total_cost_usd=_total_cost_usd(network),
		total_emissions_tco2=_total_emissions_tco2(network, generation),
		capacity_mix_mw=capacity_mix,
		generation_mwh=generation,
		renewable_share=renewable_share(generation),
		unserved_energy_mwh=unserved,
		curtailment_mwh=_curtailment_mwh(network),
		price_mean_usd_per_mwh=mean_price,
		price_volatility_usd_per_mwh=volatility,
		risk=risk,
		basis=basis,
		uncertainty=uncertainty,
	)

	assert result.total_emissions_tco2 >= 0.0
	assert result.renewable_share is None or 0.0 <= result.renewable_share <= 1.0
	return result


# --------------------------------------------------------------------------
# Cost, emissions, capacity, generation
# --------------------------------------------------------------------------


def _total_cost_usd(network: pypsa.Network) -> float:
	"""The LP objective: total system cost over the horizon.

	``n.objective`` alone omits ``objective_constant`` — the capital cost of
	capacity that already exists — so quoting it understates the system cost of
	every network with non-extendable capacity. This is the same class as the
	sign defect in the risk metrics: a number that is internally consistent and
	answers a different question than the one asked.
	"""
	objective = float(network.objective) if network.objective is not None else 0.0
	constant = float(getattr(network, "objective_constant", 0.0) or 0.0)
	return objective + constant


def _total_emissions_tco2(network: pypsa.Network, generation_mwh: dict[str, float]) -> float:
	"""Direct CO2 from generation, using the registry's intensities.

	Computed from generation rather than from a PyPSA ``co2_emissions`` column
	because the fleet artefact carries carriers, not emissions, and the registry
	is the single place an intensity is declared.
	"""
	total = 0.0
	for carrier, mwh in generation_mwh.items():
		if mwh <= 0.0 or not is_known_carrier(carrier):
			continue
		total += mwh * get_technology(carrier).co2_t_per_mwh
	return max(0.0, total)


def _capacity_mix_mw(network: pypsa.Network) -> dict[str, float]:
	"""Carrier -> installed MW at the final horizon.

	Extendable capacity is the optimiser's ``p_nom_opt``; fixed capacity is
	``p_nom``. For a multi-period network ``p_nom_opt`` is the last period's
	value, which is the right one for "what did we build by 2060".
	"""
	generators = network.generators
	if len(generators) == 0:
		return {}

	capacity = _numeric(generators, "p_nom")
	if "p_nom_opt" in generators.columns:
		optimised = _numeric(generators, "p_nom_opt")
		extendable = _flags(generators, len(generators))
		capacity = np.where(extendable, optimised, capacity)

	mix: dict[str, float] = {}
	_accumulate(mix, generators, capacity)

	# Storage contributes to the mix as power capacity; a battery that can
	# deliver 100 MW is 100 MW of firm capacity in the peak.
	for table in ("storage_units",):
		frame = getattr(network, table, None)
		if frame is None or len(frame) == 0:
			continue
		storage: pd.DataFrame = frame
		values = _numeric(storage, "p_nom")
		if "p_nom_opt" in storage.columns:
			optimised = _numeric(storage, "p_nom_opt")
			extendable = _flags(storage, len(storage))
			values = np.where(extendable, optimised, values)
		_accumulate(mix, storage, values, default_carrier="battery")

	return dict(sorted((carrier, value) for carrier, value in mix.items() if value > 0.0))


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
	"""A numeric column as a float array, NaN-free.

	``pd.to_numeric`` returns a union type under PyPSA's stubs, so the result is
	coerced through ``np.asarray`` here rather than at each call site.
	"""
	converted = pd.to_numeric(frame[column], errors="coerce")
	values = np.asarray(converted, dtype=np.float64)
	return np.nan_to_num(values, nan=0.0)


def _flags(frame: pd.DataFrame, length: int) -> np.ndarray:
	"""A boolean column as a bool array, defaulting to False where absent."""
	if "p_nom_extendable" not in frame.columns:
		return np.zeros(length, dtype=bool)
	series = frame["p_nom_extendable"].fillna(False).astype(bool)
	return np.asarray(series, dtype=bool)


def _accumulate(
	mix: dict[str, float],
	frame: pd.DataFrame,
	values: np.ndarray,
	*,
	default_carrier: str = "",
) -> None:
	"""Add per-unit values into a carrier -> total map."""
	carriers = frame["carrier"].fillna(default_carrier).astype(str).to_numpy()
	for carrier, value in zip(carriers, values, strict=True):
		mix[str(carrier)] = mix.get(str(carrier), 0.0) + float(value)


def _generation_mwh(network: pypsa.Network) -> dict[str, float]:
	"""Carrier -> generated MWh over the horizon.

	Dispatch is taken from ``generators_t.p`` when a solve produced it, and
	falls back to ``p_set`` otherwise so that a network built but not solved
	still yields a coherent (zero-cost) summary rather than an empty one.
	"""
	generators = network.generators
	if generators.empty:
		return {}

	dynamic = getattr(network, "generators_t", None)
	dispatch = getattr(dynamic, "p", None) if dynamic is not None else None
	if dispatch is None or dispatch.empty:
		dispatch = generators[["p_set"]].T

	weights = network.snapshot_weightings.get("objective")
	by_carrier: dict[str, float] = {}
	for name in dispatch.columns:
		if name not in generators.index:
			continue
		carrier = str(generators.loc[name, "carrier"])
		series = dispatch[name].astype(float)
		energy = float(series.sum()) if weights is None else float((series * weights).sum())
		by_carrier[carrier] = by_carrier.get(carrier, 0.0) + energy
	return dict(sorted((carrier, value) for carrier, value in by_carrier.items() if value != 0.0))


def _unserved_energy_mwh(network: pypsa.Network, generation: dict[str, float]) -> float:
	"""Energy served by a load-shedding carrier.

	Load shedding is how the model represents unserved demand; a network
	without it reports zero, which is correct only if the solve was feasible
	without shedding.
	"""
	return max(
		0.0,
		sum(mwh for carrier, mwh in generation.items() if carrier.strip().lower() in _LOAD_SHEDDING_CARRIERS),
	)


def _curtailment_mwh(network: pypsa.Network) -> float:
	"""Available renewable energy that was not dispatched.

	Curtailment is potential minus dispatch, per renewable generator, weighted
	by the snapshot weights. A network with no ``p_max_pu`` potential recorded
	reports zero: there is nothing to compare dispatch against, and inventing a
	potential would be a fabricated number.
	"""
	generators = network.generators
	if generators.empty:
		return 0.0

	renewable = [
		name
		for name, carrier in generators["carrier"].items()
		if is_known_carrier(carrier) and get_technology(carrier).renewable
	]
	if not renewable:
		return 0.0

	dynamic = getattr(network, "generators_t", None)
	dispatch = getattr(dynamic, "p", None) if dynamic is not None else None
	p_max_pu = getattr(dynamic, "p_max_pu", None) if dynamic is not None else None
	if dispatch is None or dispatch.empty or p_max_pu is None or p_max_pu.empty:
		return 0.0

	weights = network.snapshot_weightings.get("objective")
	curtailed = 0.0
	for name in renewable:
		if name not in dispatch.columns or name not in p_max_pu.columns:
			continue
		capacity = float(generators.loc[name, "p_nom_opt"]) if "p_nom_opt" in generators.columns else float(
			generators.loc[name, "p_nom"]
		)
		potential = p_max_pu[name].astype(float) * capacity
		actual = dispatch[name].astype(float)
		excess = (potential - actual).clip(lower=0.0)
		curtailed += float(excess.sum()) if weights is None else float((excess * weights).sum())
	return max(0.0, curtailed)


def _price_statistics(network: pypsa.Network) -> tuple[float | None, float | None]:
	"""Mean and standard deviation of the wholesale price, or ``(None, None)``.

	``(None, None)`` when the solve produced no marginal prices — a network
	built but not solved, or one solved without duals. Zero would be a price,
	and it is not the price.
	"""
	prices = getattr(getattr(network, "buses_t", None), "marginal_price", None)
	if prices is None or prices.empty:
		return None, None

	values = prices.to_numpy(dtype=np.float64).ravel()
	values = values[np.isfinite(values)]
	if values.size == 0:
		return None, None
	return float(values.mean()), float(values.std(ddof=1) if values.size > 1 else 0.0)


def _default_basis() -> Any:
	from alea.provenance.models import Basis

	return Basis.MODELLED


__all__ = ["extract"]
