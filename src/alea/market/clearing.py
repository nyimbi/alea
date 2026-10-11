# SPDX-License-Identifier: MIT
"""Merit-order market clearing.

The clearing engine is a **merit-order stack with explicit strategic markups**
(06-layer3 §3.1). It is deterministic, fast, and auditable, and it produces the
same clearing price as a uniform-price auction among the same bids. Agents
choose the bids; the stack clears them. This is deliberately *not* an agent
simulation: the plan rejects `mesa` (its example API is obsolete against mesa
2.x) and rejects per-agent reinforcement learning (non-deterministic and
unreproducible). See ``market.strategy`` for what replaces the bidding half.

Two correctness points the specification's own example gets wrong:

* The marginal unit must be dispatched at the *residual* demand remaining, not
  at ``min(capacity, total_demand)``. Using total demand caps every dispatched
  unit at the same number and can dispatch more than was asked for.
* When the stack cannot meet demand the shortfall is priced at the value of lost
  load and reported. A clearing price quoted from a stack that did not meet
  demand, without saying so, is a price for a system in blackout.

Ties break on ``unit_id`` lexicographically, never on list order. A tie broken
by list order is a tie broken by dict iteration, and that changes between runs
(AD-8).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from alea._core import branch_flows, dc_power_flow
from alea.logging import get_logger
from alea.market.views import (
	Bid,
	ClearingResult,
	Interface,
	InterfaceFlow,
	ZonalClearingResult,
	ZonalZoneResult,
)

logger = get_logger(__name__)


def merit_order_stack(bids: list[Bid]) -> list[Bid]:
	"""The dispatchable bids in merit order.

	Sorted by ``(price, unit_id)``. The second key is not decoration: ``sorted``
	on price alone leaves equal prices in input order, and input order comes
	from a dict or a dataframe index, both of which vary across runs.
	"""
	available = [b for b in bids if b.available]
	return sorted(available, key=lambda b: (b.price_usd_per_mwh, b.unit_id))


def clear_market(
	bids: list[Bid],
	demand_mw: float,
	*,
	value_of_lost_load_usd_per_mwh: float,
) -> ClearingResult:
	"""Uniform-price auction over a merit-order stack.

	The clearing price is the bid of the marginal (last) dispatched unit, which
	is the uniform-price rule. If the stack is short, the marginal price is VoLL
	and ``unserved_mwh`` records the shortfall.
	"""
	assert demand_mw >= 0.0, f"demand must be non-negative, got {demand_mw}"
	assert value_of_lost_load_usd_per_mwh >= 0.0, "VoLL must be non-negative"

	stack = merit_order_stack(bids)
	remaining = demand_mw
	dispatched: dict[str, float] = {}
	clearing_price = value_of_lost_load_usd_per_mwh

	for bid in stack:
		if remaining <= 0.0:
			break
		taken = min(bid.quantity_mw, remaining)
		dispatched[bid.unit_id] = taken
		remaining -= taken
		clearing_price = bid.price_usd_per_mwh

	unserved = max(remaining, 0.0)
	# A short stack clears at VoLL even if the marginal dispatched bid was
	# cheaper: the price of the last MWh served is what the buyer had to pay to
	# avoid shedding it.
	if unserved > 0.0:
		clearing_price = value_of_lost_load_usd_per_mwh

	result = ClearingResult(
		demand_mw=demand_mw,
		clearing_price_usd_per_mwh=clearing_price,
		dispatched=dispatched,
		unserved_mwh=unserved,
		shortage_price_usd_per_mwh=value_of_lost_load_usd_per_mwh if unserved > 0.0 else 0.0,
	)
	assert abs(result.total_dispatched_mw + result.unserved_mwh - demand_mw) < 1e-6 * max(
		1.0, demand_mw
	), "clearing does not conserve energy"
	return result


def clear_market_series(
	bids_by_hour: list[list[Bid]],
	demand_mw: NDArray[np.float64],
	*,
	value_of_lost_load_usd_per_mwh: float,
) -> list[ClearingResult]:
	"""Clear one market per hour.

	Each hour is an independent uniform-price auction. The stack may differ hour
	to hour (availability, hydro), so the bid lists are supplied per hour rather
	than reused.
	"""
	demand = np.asarray(demand_mw, dtype=np.float64)
	assert len(bids_by_hour) == demand.shape[0], (
		f"{len(bids_by_hour)} bid stacks for {demand.shape[0]} demand points"
	)
	results = [
		clear_market(
			stack,
			float(demand[hour]),
			value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
		)
		for hour, stack in enumerate(bids_by_hour)
	]
	logger.info(
		"clear_market_series",
		hours=len(results),
		mean_price=(
			float(np.mean([r.clearing_price_usd_per_mwh for r in results])) if results else 0.0
		),
		unserved_mwh=float(sum(r.unserved_mwh for r in results)),
	)
	return results


# --------------------------------------------------------------------------
# Zonal clearing
# --------------------------------------------------------------------------


@dataclass
class _AreaResult:
	"""One area's clearing, with dispatch attributed back to its zones.

	An area clears as a single market at a single price, so its bids are the
	union of its zones' bids. The dispatch is split back to the zone each unit
	belongs to, which is what lets a zone's net import be computed.
	"""

	price_usd_per_mwh: float
	dispatch_by_zone: dict[str, dict[str, float]]
	total_demand_mw: float
	unserved_mwh: float

	@property
	def total_generation_mw(self) -> float:
		return sum(mw for zone in self.dispatch_by_zone.values() for mw in zone.values())


def clear_market_zonal(
	bids_by_zone: dict[str, list[Bid]],
	demand_by_zone: dict[str, float],
	interfaces: list[Interface],
	*,
	value_of_lost_load_usd_per_mwh: float,
	max_iterations: int = 100,
	tolerance_mw: float = 1e-3,
) -> ZonalClearingResult:
	"""Clear a market with internal transmission limits, by market splitting.

	A single national market clears once; a power-pool market clears with
	corridors between zones. The method is **market splitting** with an explicit
	scheduled transfer per corridor:

	1. Partition the zones into price areas, starting with all zones as one area.
	2. Clear each area at a single price against its net demand (own demand
	   adjusted by the transfers scheduled into and out of it).
	3. Compute the corridor flows with a DC power flow over the zone graph.
	4. Where a corridor *within* an area is overloaded, split that area at it and
	   schedule the transfer at the corridor's limit — the overload means the
	   economic trade exceeds the limit, so the limit binds.
	5. Where a corridor *between* two areas is overloaded, schedule its transfer
	   at the limit too.
	6. Repeat until no corridor is overloaded.

	Why splitting rather than a per-zone clear: clearing each zone against its own
	demand in isolation assumes the zones never trade, so the cheap zone never
	exports and no corridor can bind. Congestion — the output that matters, and
	the one a single-price national model cannot produce — then cannot occur.

	The scheduled-transfer heuristic (set a binding corridor's transfer to its
	limit) is exact for a radial network and a good approximation otherwise; it is
	not a full market-coupling solver, and a meshed network with several mutually
	constraining corridors is beyond what this iteration guarantees.
	"""
	zone_ids = sorted(bids_by_zone)
	assert set(zone_ids) == set(demand_by_zone), (
		f"zones with bids {zone_ids} != zones with demand {sorted(demand_by_zone)}"
	)
	assert zone_ids, "no zones to clear"
	for interface in interfaces:
		assert interface.from_zone in bids_by_zone, f"unknown zone {interface.from_zone}"
		assert interface.to_zone in bids_by_zone, f"unknown zone {interface.to_zone}"

	demand = {z: float(demand_by_zone[z]) for z in zone_ids}
	bids = {z: list(bids_by_zone[z]) for z in zone_ids}

	# A scheduled transfer per corridor, in the Interface's from->to direction.
	# It shifts an area's net demand: the exporting area carries the transferred
	# energy, the importing area has it removed.
	transfer = [0.0] * len(interfaces)

	area_of: dict[str, int] = {z: 0 for z in zone_ids}
	areas: list[set[str]] = [set(zone_ids)]
	converged = False
	area_results: dict[int, _AreaResult] = {}
	flows = np.zeros(len(interfaces), dtype=np.float64)

	for _ in range(max_iterations):
		area_results = _clear_areas(
			areas,
			area_of,
			zone_ids,
			bids,
			demand,
			interfaces,
			transfer,
			value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
		)
		zone_generation = _zone_generation(zone_ids, area_of, area_results)
		flows = _solve_corridor_flows(zone_ids, zone_generation, demand, area_of, area_results, interfaces)

		overloaded = [
			k
			for k, interface in enumerate(interfaces)
			if abs(flows[k]) > interface.limit_mw + tolerance_mw
		]
		if not overloaded:
			converged = True
			break

		for k in overloaded:
			interface = interfaces[k]
			direction = 1.0 if flows[k] > 0.0 else -1.0
			if area_of[interface.from_zone] == area_of[interface.to_zone]:
				# Same area: the corridor is unconstrained inside it. Split the
				# area at this corridor and pin its transfer to the limit.
				_split_area(areas, area_of, zone_ids, interface)
			# The overload means the economic transfer exceeds the limit, so the
			# limit binds and the scheduled transfer sits at it.
			transfer[k] = direction * interface.limit_mw

	area_results = _clear_areas(
		areas,
		area_of,
		zone_ids,
		bids,
		demand,
		interfaces,
		transfer,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	zone_generation = _zone_generation(zone_ids, area_of, area_results)
	flows = _solve_corridor_flows(zone_ids, zone_generation, demand, area_of, area_results, interfaces)

	zones_out = _zone_results(zone_ids, area_of, area_results, demand)
	interfaces_out = [
		InterfaceFlow(
			from_zone=interface.from_zone,
			to_zone=interface.to_zone,
			flow_mw=float(flows[k]),
			limit_mw=interface.limit_mw,
			congested=abs(float(flows[k])) >= interface.limit_mw - tolerance_mw,
		)
		for k, interface in enumerate(interfaces)
	]

	prices = {z: zones_out[z].price_usd_per_mwh for z in zone_ids}
	system_price = (
		None if len({round(p, 6) for p in prices.values()}) > 1 else next(iter(prices.values()))
	)

	# Congestion rent: the price difference across a congested corridor times the
	# flow on it. It is what the corridor owner collects and is a real cost to the
	# market.
	rent = 0.0
	for flow in interfaces_out:
		if flow.congested:
			delta = prices[flow.from_zone] - prices[flow.to_zone]
			rent += abs(delta) * abs(flow.flow_mw)

	if not converged:
		logger.warning(
			"zonal_clearing_did_not_converge",
			zones=len(zone_ids),
			areas=len(areas),
			interfaces=len(interfaces),
			max_iterations=max_iterations,
		)

	return ZonalClearingResult(
		zones=zones_out,
		interfaces=interfaces_out,
		system_price_usd_per_mwh=system_price,
		congestion_rent_usd=rent,
		converged=converged,
	)


def _split_area(
	areas: list[set[str]],
	area_of: dict[str, int],
	zone_ids: list[str],
	interface: Interface,
) -> None:
	"""Split an area in two at a corridor, moving the ``to`` side to a new area.

	The ``to_zone`` side becomes a new area; the ``from_zone`` side keeps the old
	index. A zone whose area is neither endpoint is untouched.
	"""
	old_area = area_of[interface.from_zone]
	new_area = len(areas)
	areas.append(set())
	for zone in zone_ids:
		if area_of[zone] == old_area and zone != interface.from_zone and _same_side(
			zone, interface, area_of
		):
			area_of[zone] = new_area
	areas[old_area] = {z for z in zone_ids if area_of[z] == old_area}
	areas[new_area] = {z for z in zone_ids if area_of[z] == new_area}


def _same_side(zone: str, interface: Interface, area_of: dict[str, int]) -> bool:
	"""Whether a zone should follow the ``to_zone`` side of a split.

	Only the ``to_zone`` moves: the corridor is between two zones, and the split
	separates the ``to`` zone (and any zone already grouped with it) from the
	``from`` zone. This is the minimal split that resolves the overload.
	"""
	return zone == interface.to_zone


def _clear_areas(
	areas: list[set[str]],
	area_of: dict[str, int],
	zone_ids: list[str],
	bids: dict[str, list[Bid]],
	demand: dict[str, float],
	interfaces: list[Interface],
	transfer: list[float],
	*,
	value_of_lost_load_usd_per_mwh: float,
) -> dict[int, _AreaResult]:
	"""Clear every area, with its net demand adjusted by scheduled transfers."""
	results: dict[int, _AreaResult] = {}
	for index, area in enumerate(areas):
		if not area:
			continue
		net_demand = sum(demand[z] for z in area)
		for k, interface in enumerate(interfaces):
			if transfer[k] == 0.0:
				continue
			from_area = area_of[interface.from_zone]
			to_area = area_of[interface.to_zone]
			if from_area == index and to_area != index:
				net_demand += transfer[k]
			elif to_area == index and from_area != index:
				net_demand -= transfer[k]
		net_demand = max(net_demand, 0.0)
		results[index] = _clear_area(
			sorted(area),
			bids,
			net_demand,
			value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
		)
	return results


def _clear_area(
	area_zones: list[str],
	bids: dict[str, list[Bid]],
	net_demand_mw: float,
	*,
	value_of_lost_load_usd_per_mwh: float,
) -> _AreaResult:
	"""Clear one area's union of bids at a single price."""
	assert area_zones, "an area needs at least one zone"
	unit_zone = {bid.unit_id: zone for zone in area_zones for bid in bids[zone]}
	area_bids = [bid for zone in area_zones for bid in bids[zone]]
	result = clear_market(
		area_bids,
		net_demand_mw,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	dispatch_by_zone: dict[str, dict[str, float]] = {z: {} for z in area_zones}
	for unit_id, mw in result.dispatched.items():
		dispatch_by_zone[unit_zone[unit_id]][unit_id] = mw
	return _AreaResult(
		price_usd_per_mwh=result.clearing_price_usd_per_mwh,
		dispatch_by_zone=dispatch_by_zone,
		total_demand_mw=net_demand_mw,
		unserved_mwh=result.unserved_mwh,
	)


def _zone_generation(
	zone_ids: list[str],
	area_of: dict[str, int],
	area_results: dict[int, _AreaResult],
) -> dict[str, float]:
	"""Each zone's generation, read off its area's dispatch."""
	return {
		zone: sum(area_results[area_of[zone]].dispatch_by_zone.get(zone, {}).values())
		for zone in zone_ids
	}


def _zone_results(
	zone_ids: list[str],
	area_of: dict[str, int],
	area_results: dict[int, _AreaResult],
	demand: dict[str, float],
) -> dict[str, ZonalZoneResult]:
	"""Per-zone positions, with unserved energy shared pro rata within an area."""
	generation = _zone_generation(zone_ids, area_of, area_results)
	out: dict[str, ZonalZoneResult] = {}
	for zone in zone_ids:
		area = area_results[area_of[zone]]
		unserved = 0.0
		if area.unserved_mwh > 0.0 and area.total_demand_mw > 0.0:
			unserved = area.unserved_mwh * demand[zone] / area.total_demand_mw
		out[zone] = ZonalZoneResult(
			zone_id=zone,
			demand_mw=demand[zone],
			generation_mw=generation[zone],
			net_import_mw=demand[zone] - generation[zone] - unserved,
			price_usd_per_mwh=area.price_usd_per_mwh,
			unserved_mwh=unserved,
			dispatched=area.dispatch_by_zone.get(zone, {}),
		)
	return out


def _solve_corridor_flows(
	zone_ids: list[str],
	zone_generation: dict[str, float],
	demand: dict[str, float],
	area_of: dict[str, int],
	area_results: dict[int, _AreaResult],
	interfaces: list[Interface],
) -> NDArray[np.float64]:
	"""DC power flow over the zone graph, returning one flow per corridor.

	Net injection per zone is generation minus load, where load is the zone's own
	demand scaled by the fraction of its area's demand that was actually met (an
	area that shed load sheds it proportionally). The susceptance matrix is
	assembled from the corridors and the slack angle is pinned to the first zone.
	This is the linear DC approximation, the same model ``alea_losses`` uses.
	"""
	n = len(zone_ids)
	index = {z: i for i, z in enumerate(zone_ids)}
	if not interfaces:
		return np.zeros(0, dtype=np.float64)

	injection = np.zeros(n, dtype=np.float64)
	for zone in zone_ids:
		area = area_results[area_of[zone]]
		met_fraction = 1.0
		if area.total_demand_mw > 0.0 and area.unserved_mwh > 0.0:
			met_fraction = max(0.0, (area.total_demand_mw - area.unserved_mwh) / area.total_demand_mw)
		injection[index[zone]] = zone_generation[zone] - demand[zone] * met_fraction

	susceptance = np.zeros((n, n), dtype=np.float64)
	for interface in interfaces:
		i, j = index[interface.from_zone], index[interface.to_zone]
		b = interface.susceptance
		susceptance[i, i] += b
		susceptance[j, j] += b
		susceptance[i, j] -= b
		susceptance[j, i] -= b

	angles = dc_power_flow(susceptance, injection, 0)
	branch_from = np.array([index[i.from_zone] for i in interfaces], dtype=np.uint32)
	branch_to = np.array([index[i.to_zone] for i in interfaces], dtype=np.uint32)
	branch_susceptance = np.array([i.susceptance for i in interfaces], dtype=np.float64)
	return branch_flows(angles, branch_from, branch_to, branch_susceptance)


__all__ = [
	"clear_market",
	"clear_market_series",
	"clear_market_zonal",
	"merit_order_stack",
]
