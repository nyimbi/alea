# SPDX-License-Identifier: MIT
"""The bidding agent.

An agent is the *strategic* half of a unit: it holds a ``Strategy`` and turns a
unit's physical state (available capacity, marginal cost) into a ``Bid``. The
stack in ``market.clearing`` is the *mechanical* half and knows nothing about
strategy. Keeping the two apart is what lets a clearing price be decomposed
into "what the market did" and "what the bidders chose".

This is the replacement for the specification's PPO-per-generator design
(06-layer3 §2.2). It is a plain object with a pure ``bid`` method: same inputs,
same bid, every run (AD-8).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from alea.logging import get_logger
from alea.market.strategy import Strategy, StrategyKind
from alea.market.views import Bid, MarketModel, NonNegativeFinite

logger = get_logger(__name__)


class BiddingUnit(MarketModel):
	"""A unit as the market sees it: capacity, cost, availability.

	Availability is a fraction of nameplate, which is how a VRE unit enters a
	merit-order stack: its weather-driven output is the quantity it can offer,
	not a choice it makes.
	"""

	unit_id: str
	carrier: str
	capacity_mw: NonNegativeFinite
	marginal_cost_usd_per_mwh: float
	availability: float = Field(default=1.0, ge=0.0, le=1.0)
	zone_id: str = "national"

	@property
	def available_mw(self) -> float:
		return self.capacity_mw * self.availability


class Agent(MarketModel):
	"""One unit's bidding rule, bound to the unit it bids for."""

	unit: BiddingUnit
	strategy: Strategy = Field(default_factory=Strategy.competitive)

	def bid(self) -> Bid:
		"""The offer this agent places for its unit.

		A unit with no available output still places a zero-quantity bid so it
		appears in the stack: a unit that is absent is indistinguishable from a
		unit that does not exist, and the difference matters when a dispatch is
		reconciled against the fleet.
		"""
		available_mw = self.unit.available_mw
		price = self.strategy.bid_price(self.unit.marginal_cost_usd_per_mwh)
		return Bid(
			unit_id=self.unit.unit_id,
			quantity_mw=available_mw,
			price_usd_per_mwh=price,
			available=available_mw > 0.0,
			carrier=self.unit.carrier,
			zone_id=self.unit.zone_id,
			marginal_cost_usd_per_mwh=self.unit.marginal_cost_usd_per_mwh,
		)


def build_stack(agents: Sequence[Agent]) -> list[Bid]:
	"""Every agent's bid, in a deterministic order.

	Ordered by ``unit_id`` so the list is stable regardless of how the caller
	enumerated its fleet. The clearing stack re-sorts by price anyway; the point
	is that two runs given the same fleet produce the same list.
	"""
	assert agents, "no agents to build a stack from"
	bids = [agent.bid() for agent in sorted(agents, key=lambda a: a.unit.unit_id)]
	logger.info(
		"build_stack",
		units=len(bids),
		available=sum(1 for b in bids if b.available),
		capacity_mw=sum(b.quantity_mw for b in bids),
	)
	return bids


def markup_summary(agents: Sequence[Agent]) -> dict[str, float]:
	"""Mean bid markup over marginal cost, per strategy kind.

	The competitive benchmark, in one number. A clearing result is read against
	this: with every agent competitive the summary is zero and the clearing
	price *is* the merit-order price.
	"""
	by_kind: dict[str, list[float]] = {}
	for agent in agents:
		cost = agent.unit.marginal_cost_usd_per_mwh
		if cost <= 0.0:
			continue
		bid_price = agent.strategy.bid_price(cost)
		by_kind.setdefault(agent.strategy.kind.value, []).append(bid_price / cost - 1.0)
	return {kind: sum(values) / len(values) for kind, values in by_kind.items()}


__all__ = [
	"Agent",
	"BiddingUnit",
	"build_stack",
	"markup_summary",
	"StrategyKind",
]
