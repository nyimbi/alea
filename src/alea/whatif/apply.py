# SPDX-License-Identifier: MIT
"""Network mutation from scenario parameters.

WHY this module keeps a base snapshot inside the network's ``meta``: the
specification's ``_apply`` scales ``p_nom_max`` in place with
``n.generators.loc[mask, "p_nom_max"] *= multiplier``. That is a *relative*
operation on an *absolute* quantity, so it compounds — applying the same
scenario twice doubles the potential, and applying it to a network that was
already scaled for a different reason multiplies the wrong base. The fix is to
record each unit's pre-scenario value once, in the network the scenario is
applied to, and always scale from that record. Re-applying a scenario is then
idempotent, which is what makes a sweep reproducible.

WHY the demand-growth assertion exists: ``(1 + g) ** (years - years.min())`` is
zero-exponent everywhere on a single-period network, so the parameter silently
does nothing. A parameter that does nothing produces a frontier flat in that
parameter, and a flat frontier reads as "demand growth does not matter" rather
than "the parameter was never applied". The assertion makes it loud.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger
from alea.registry.technologies import get_technology, is_known_carrier
from alea.whatif.params import ScenarioParameters

logger = get_logger(__name__)

_BASE_META_KEY = "alea_whatif_base"
"""Key under ``network.meta`` holding the pre-scenario values, as a JSON string.

A JSON string rather than a nested dict because ``meta`` is written to the
NetCDF global attributes, where only scalars and strings are portable.
"""

_HYDROGEN_EXPORT_CARRIER = "h2"
_TWH_TO_MWH = 1e6


def apply_parameters(base: pypsa.Network, params: ScenarioParameters) -> pypsa.Network:
	"""Return a scenario network. ``base`` is never modified.

	Every scaling reads its base value from the snapshot recorded in
	``network.meta`` (captured from ``base`` on first application), so applying
	the same parameters twice gives the same network as applying them once.
	"""
	assert isinstance(params, ScenarioParameters)
	assert isinstance(base, pypsa.Network)

	before = _network_fingerprint(base)
	network = base.copy()
	_ensure_base_snapshot(network)
	snapshot = _read_base_snapshot(network)

	_apply_demand_growth(network, params)
	_apply_carbon_price(network, params, snapshot)
	_apply_fuel_and_capex_multipliers(network, params, snapshot)
	_apply_renewable_potential(network, params, snapshot)
	_apply_availability_multipliers(network, params, snapshot)
	_apply_hydrogen_export(network, params)

	after = _network_fingerprint(base)
	assert before == after, "apply_parameters mutated the base network"
	assert network is not base
	logger.info(
		"whatif.apply",
		changed=params.changed_from(ScenarioParameters()),
		generators=len(network.generators),
	)
	return network


# --------------------------------------------------------------------------
# Base snapshot
# --------------------------------------------------------------------------


def _ensure_base_snapshot(network: pypsa.Network) -> None:
	"""Record pre-scenario values if this network has none.

	Called on the *copy*, so the base network's ``meta`` is never touched and
	``base`` stays byte-identical.
	"""
	if _BASE_META_KEY in network.meta:
		return
	network.meta[_BASE_META_KEY] = json.dumps(_capture(network), sort_keys=True, default=str)


def _capture(network: pypsa.Network) -> dict[str, Any]:
	"""The values a scenario scales, as they are before any scenario."""
	generators = network.generators
	dynamic = getattr(network, "generators_t", None)
	p_max_pu_dynamic = getattr(dynamic, "p_max_pu", None) if dynamic is not None else None

	captured: dict[str, Any] = {
		"p_nom_max": _series_to_dict(generators.get("p_nom_max")),
		"capital_cost": _series_to_dict(generators.get("capital_cost")),
		"marginal_cost": _series_to_dict(generators.get("marginal_cost")),
		"p_max_pu_static": _series_to_dict(generators.get("p_max_pu")),
		"p_max_pu_dynamic": {},
	}
	if p_max_pu_dynamic is not None and not p_max_pu_dynamic.empty:
		captured["p_max_pu_dynamic"] = {
			str(column): _series_to_dict(p_max_pu_dynamic[column])
			for column in p_max_pu_dynamic.columns
		}
	return captured


def _read_base_snapshot(network: pypsa.Network) -> dict[str, Any]:
	raw = network.meta.get(_BASE_META_KEY, "{}")
	return json.loads(raw) if isinstance(raw, str) else raw


def _series_to_dict(series: pd.Series | None) -> dict[str, float]:
	if series is None:
		return {}
	return {str(name): float(value) for name, value in series.items() if pd.notna(value)}


def _restore(series: pd.Series, base: dict[str, float]) -> pd.Series:
	"""A series whose values are the recorded base where one exists."""
	out = series.astype(float).copy()
	for name in out.index:
		key = str(name)
		if key in base:
			out.loc[name] = base[key]
	return out


# --------------------------------------------------------------------------
# Individual parameters
# --------------------------------------------------------------------------


def _apply_demand_growth(network: pypsa.Network, params: ScenarioParameters) -> None:
	"""Scale every load by ``(1 + g) ** (year - first_year)``."""
	if params.demand_growth == 0.0:
		return
	if network.loads.empty or network.loads_t.p_set.empty:
		return

	years = _snapshot_years(network)
	distinct = sorted(set(years.tolist()))
	if len(distinct) < 2:
		raise ValueError(
			f"demand_growth={params.demand_growth} requires a multi-period "
			f"network; this network has {len(distinct)} distinct year(s) "
			f"({distinct}), so the growth exponent is zero everywhere and the "
			f"parameter would silently do nothing"
		)

	factors = (1.0 + params.demand_growth) ** (years - distinct[0])
	network.loads_t.p_set = network.loads_t.p_set.mul(
		pd.Series(factors, index=network.loads_t.p_set.index), axis=0
	)


def _apply_carbon_price(
	network: pypsa.Network, params: ScenarioParameters, snapshot: dict[str, Any]
) -> None:
	"""Add ``carbon_price * intensity`` to each emitting carrier's marginal cost.

	Additive on the *base* marginal cost, never on the current one, so two
	applications do not stack the carbon price.
	"""
	if params.carbon_price_usd_per_tco2 == 0.0:
		return

	generators = network.generators
	if generators.empty:
		return
	base = snapshot.get("marginal_cost", {})
	restored = _restore(generators["marginal_cost"], base)

	surcharge = np.zeros(len(generators), dtype=np.float64)
	for position, carrier in enumerate(generators["carrier"].tolist()):
		if not is_known_carrier(carrier):
			continue
		intensity = get_technology(carrier).co2_t_per_mwh
		surcharge[position] = intensity * params.carbon_price_usd_per_tco2
	network.generators["marginal_cost"] = restored.to_numpy() + surcharge


def _apply_fuel_and_capex_multipliers(
	network: pypsa.Network, params: ScenarioParameters, snapshot: dict[str, Any]
) -> None:
	"""Gas marginal cost and battery capital cost, from their base values."""
	generators = network.generators
	if generators.empty:
		return

	carriers = generators["carrier"].fillna("").astype(str).str.lower()

	if params.gas_price_multiplier != 1.0:
		mask = carriers == "gas"
		if mask.any():
			base = _restore(generators["marginal_cost"], snapshot.get("marginal_cost", {}))
			scaled = base.where(~mask, base * params.gas_price_multiplier)
			network.generators["marginal_cost"] = scaled

	if params.battery_cost_multiplier != 1.0:
		mask = carriers == "battery"
		if mask.any():
			base = _restore(generators["capital_cost"], snapshot.get("capital_cost", {}))
			scaled = base.where(~mask, base * params.battery_cost_multiplier)
			network.generators["capital_cost"] = scaled


def _apply_renewable_potential(
	network: pypsa.Network, params: ScenarioParameters, snapshot: dict[str, Any]
) -> None:
	"""Scale buildable renewable potential from its recorded base.

	The gate ``test_renewable_multiplier_absolute`` applies the same parameters
	twice and asserts the result equals a single application. That holds because
	the base ``p_nom_max`` is read from the snapshot, not from the current value.
	"""
	if params.renewable_multiplier == 1.0:
		return

	generators = network.generators
	if generators.empty:
		return

	mask = np.array(
		[
			is_known_carrier(carrier) and get_technology(carrier).renewable
			for carrier in generators["carrier"].fillna("").tolist()
		],
		dtype=bool,
	)
	if not mask.any():
		return

	base = _restore(generators["p_nom_max"], snapshot.get("p_nom_max", {}))
	scaled = base.where(~pd.Series(mask, index=generators.index), base * params.renewable_multiplier)
	network.generators["p_nom_max"] = scaled


def _apply_availability_multipliers(
	network: pypsa.Network, params: ScenarioParameters, snapshot: dict[str, Any]
) -> None:
	"""Coal availability and drought, applied to ``p_max_pu`` from its base.

	``coal_eaf`` scales each unit's own base availability (a multiplier), and
	``drought_multiplier`` divides hydro availability, so a drier year produces
	less energy from the same installed capacity.
	"""
	generators = network.generators
	if generators.empty:
		return

	carriers = generators["carrier"].fillna("").astype(str).str.lower()
	coal = params.coal_eaf != 1.0
	hydro = params.drought_multiplier != 1.0
	if not (coal or hydro):
		return

	dynamic = getattr(network, "generators_t", None)
	p_max_pu = getattr(dynamic, "p_max_pu", None) if dynamic is not None else None

	def factor_for(carrier: str) -> float:
		if carrier == "coal" and coal:
			return params.coal_eaf
		if carrier in ("hydro", "ror") and hydro:
			return 1.0 / params.drought_multiplier
		return 1.0

	if p_max_pu is not None and not p_max_pu.empty:
		base_dynamic = snapshot.get("p_max_pu_dynamic", {})
		updated = p_max_pu.copy()
		for column in updated.columns:
			carrier = str(generators.loc[column, "carrier"]).lower() if column in generators.index else ""
			factor = factor_for(carrier)
			if factor == 1.0:
				continue
			base = base_dynamic.get(str(column))
			column_base = _restore(updated[column], base) if base else updated[column].astype(float)
			updated[column] = column_base * factor
		network.generators_t.p_max_pu = updated
		return

	base_static = snapshot.get("p_max_pu_static", {})
	if base_static:
		restored = _restore(generators["p_max_pu"], base_static)
		factors = pd.Series(
			[factor_for(carrier) for carrier in carriers.tolist()], index=generators.index
		)
		network.generators["p_max_pu"] = restored * factors
		return

	# No snapshot of p_max_pu: the network carried none, so the effective
	# availability was the implicit 1.0. Scale from that.
	factors = pd.Series(
		[factor_for(carrier) for carrier in carriers.tolist()], index=generators.index
	)
	network.generators["p_max_pu"] = factors


def _apply_hydrogen_export(network: pypsa.Network, params: ScenarioParameters) -> None:
	"""Add a hydrogen export load sized in TWh/year.

	The load is spread across each year's snapshots so every year exports
	exactly the stated energy. A total spread across the whole horizon would
	export ``twh`` per horizon rather than per year, understating the demand by
	the number of investment periods.
	"""
	if params.hydrogen_export_twh_per_year <= 0.0:
		return

	years = _snapshot_years(network)
	annual_mwh = params.hydrogen_export_twh_per_year * _TWH_TO_MWH
	values = np.array(
		[annual_mwh / max(1, int((years == year).sum())) for year in years],
		dtype=np.float64,
	)

	bus = _export_bus(network)
	name = "h2_export"
	if name not in network.loads.index:
		network.add("Load", name, bus=bus, carrier=_HYDROGEN_EXPORT_CARRIER)
	network.loads_t.p_set[name] = values


def _export_bus(network: pypsa.Network) -> str:
	"""A bus to attach the export load to.

	The carrier's own bus if the sector layer created one, otherwise the first
	AC bus. Failing loudly beats attaching hydrogen demand to a bus that does
	not exist, which the optimiser would report as an empty network.
	"""
	if "h2" in network.buses.index:
		return "h2"
	ac = [name for name, carrier in network.buses["carrier"].items() if carrier == "AC"]
	if ac:
		return ac[0]
	if len(network.buses) == 0:
		raise ValueError("cannot add a hydrogen export load to a network with no buses")
	return str(network.buses.index[0])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _snapshot_years(network: pypsa.Network) -> np.ndarray:
	"""The year of each snapshot, whether the index is multi-period or flat."""
	snapshots = network.snapshots
	if snapshots.nlevels > 1:
		return np.asarray(snapshots.get_level_values(0), dtype=np.int64)
	index = pd.DatetimeIndex(snapshots)
	return np.asarray(index.to_series().dt.year.to_numpy(), dtype=np.int64)


def _network_fingerprint(network: pypsa.Network) -> str:
	"""A hash of the static tables, for the immutability assertion.

	Not the NetCDF export: that is slower than the mutation it guards, and the
	gate ``test_apply_does_not_mutate_base`` only needs to detect a change to
	the tables a scenario touches.
	"""
	import hashlib

	digest = hashlib.sha256()
	for table in ("generators", "loads", "buses", "storage_units", "links"):
		frame = getattr(network, table, None)
		if frame is None or frame.empty:
			continue
		digest.update(table.encode("utf-8"))
		hashed = pd.util.hash_pandas_object(frame.sort_index(), index=True)  # type: ignore[reportAttributeAccessIssue]
		digest.update(np.asarray(hashed, dtype=np.uint64).tobytes())
	return digest.hexdigest()


__all__ = ["apply_parameters"]
