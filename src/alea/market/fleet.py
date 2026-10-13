# SPDX-License-Identifier: MIT
"""The market fleet: a solved network's generators as bidding agents.

WHY this module is the piece the register was waiting for. `reporting/producers.py`
recorded the monthly market section's blocker as "no module builds a market fleet
from a solved network" -- `BiddingUnit` was constructed nowhere outside its own
tests, and `clear_scenario` was called by nothing but them. The clearing kernel,
the strategy, the agent wrapper and the schema all existed and were tested; what
did not exist was the *join* between Layer 1's network and Layer 3's market. That
join is here, and it is one function.

**What a unit's availability is, and why it is a parameter.** A merit-order
clearing happens at an instant: a unit offers what it can produce *then*. A VRE
unit's offer is its weather-driven output, which is a different number in every
snapshot, so a fleet is a per-snapshot object and ``snapshot`` names which one.
Omitting it gives the period-mean availability, which is the right fleet to clear
against period-mean demand and the wrong one to clear against a peak -- a
distinction the caller has to make, so it is an argument rather than a default
that quietly picks one.

**Load shedding is not a bidder.** A load-shedding carrier is how the model
represents unserved demand; its "marginal cost" is the value of lost load. Bidding
it into the stack would make the market clear at VoLL by construction and the
shortage would be invisible -- the stack would always appear to meet demand
because the generator standing in for *not* meeting it was in the stack. It is
excluded, and the shortfall is what ``ClearingResult.unserved_mwh`` reports.

**What is deliberately not in the fleet.** Storage units. A battery's bid is a
function of its state of charge and the prices on either side of the snapshot, so
it is not a price-taker in a single-period stack; including one as a generator at
its ``p_nom`` would offer energy it may not hold. The market's dispatch therefore
does not sum to the network's, and every artefact built from this fleet records
that in its provenance rather than leaving a reader to find it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from alea.logging import get_logger
from alea.market.agents import Agent, BiddingUnit
from alea.market.strategy import Strategy

if TYPE_CHECKING:  # pragma: no cover - the annotation only; pypsa costs 3.8s to import
	import pypsa

logger = get_logger(__name__)

LOAD_SHEDDING_CARRIERS = frozenset({"load shedding", "load_shedding", "load-shedding"})
"""Carriers that stand in for unserved demand rather than for a power station.

The same three spellings `whatif.extract` excludes, kept as a public name here
because the fleet is where the exclusion is load-bearing: a unit that is a
*representation of a shortage* must not be a bidder in the stack that measures
the shortage.
"""


def build_fleet(
	network: pypsa.Network,
	*,
	strategy: Strategy | None = None,
	snapshot: Any = None,
	zone_id: str = "national",
	skip_carriers: frozenset[str] = LOAD_SHEDDING_CARRIERS,
) -> list[Agent]:
	"""Every dispatchable generator as a bidding agent, in a deterministic order.

	``snapshot`` selects the instant the fleet offers into. ``None`` means the
	period-mean availability, which is a different market from any single hour
	and is stated here rather than assumed by the caller.

	An empty network gives an empty fleet rather than raising: a network with no
	generators is a fact about the network, and the clearing that follows it
	reports the whole of demand as unserved, which is the true answer.
	"""
	generators = network.generators
	if len(generators) == 0:
		logger.info("build_fleet.empty")
		return []

	from alea.planning import balance

	rule = strategy if strategy is not None else Strategy.competitive()
	carriers = generators["carrier"].fillna("").astype(str)
	capacity = balance.generator_capacity_mw(generators)
	cost = _marginal_cost(generators)
	profile = balance.availability_frame(network, generators)
	offered = _offered_fraction(profile, snapshot)

	agents: list[Agent] = []
	skipped: list[str] = []
	for position, name in enumerate(generators.index):
		carrier = str(carriers.loc[name])
		if carrier.strip().lower() in skip_carriers:
			skipped.append(str(name))
			continue
		agents.append(
			Agent(
				unit=BiddingUnit(
					unit_id=str(name),
					carrier=carrier,
					capacity_mw=float(capacity[position]),
					marginal_cost_usd_per_mwh=float(cost[position]),
					availability=float(offered[position]),
					zone_id=zone_id,
				),
				strategy=rule,
			)
		)

	# Sorted by unit_id rather than left in the frame's order. `build_stack`
	# sorts again and the clearing stack sorts by price; the point is that two
	# runs given the same network produce the same list (AD-8), and a frame's
	# row order is not something this function can promise.
	agents.sort(key=lambda agent: agent.unit.unit_id)
	logger.info(
		"build_fleet",
		units=len(agents),
		skipped=len(skipped),
		capacity_mw=round(sum(agent.unit.capacity_mw for agent in agents), 6),
		snapshot=None if snapshot is None else str(snapshot),
	)
	assert all(agent.unit.capacity_mw >= 0.0 for agent in agents), "negative capacity in the fleet"
	return agents


def build_fleet_series(
	network: pypsa.Network,
	*,
	strategy: Strategy | None = None,
	zone_id: str = "national",
	skip_carriers: frozenset[str] = LOAD_SHEDDING_CARRIERS,
) -> list[list[Agent]]:
	"""One fleet per snapshot, in snapshot order.

	The form `market.clearing.clear_market_series` takes. A VRE unit offers its
	weather-driven output, so a fleet is a per-snapshot object and a series of
	clearings needs a series of fleets; building one fleet at the mean and
	reusing it would clear every hour of a day against the same average
	afternoon, which is a market that never saw a sunrise.
	"""
	generators = network.generators
	if len(generators) == 0:
		return []
	return [
		build_fleet(
			network,
			strategy=strategy,
			snapshot=snapshot,
			zone_id=zone_id,
			skip_carriers=skip_carriers,
		)
		for snapshot in network.snapshots
	]


def peak_snapshot(network: pypsa.Network) -> Any:
	"""The snapshot with the highest total load, ties broken by position.

	The peak is the instant a capacity market is usually cleared at, and naming
	it here rather than letting a caller take ``argmax`` of its own series keeps
	the tie-break -- first occurrence, never a dict or a numpy ordering -- in one
	place (AD-8).
	"""
	from alea.planning import balance

	values = balance.load_series(network)
	assert values.size > 0, "a network with no snapshots has no peak"
	return network.snapshots[int(np.argmax(values))]


def fleet_energy_mwh(network: pypsa.Network) -> np.ndarray:
	"""The weight each snapshot's MW carries, for turning a dispatch into energy.

	``snapshot_weightings.objective`` is the weight the network itself applies to
	a snapshot, which is 1.0 for an hourly network and is *not* one hour for an
	aggregated or multi-investment-period one. Multiplying a dispatch by 1.0
	instead would report every energy in a four-period network as if each
	snapshot were an hour of one year.
	"""
	weights = network.snapshot_weightings.get("objective")
	if weights is None:
		return np.ones(len(network.snapshots), dtype=np.float64)
	values = np.asarray(pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float), dtype=np.float64)
	return np.nan_to_num(values, nan=0.0)


# --------------------------------------------------------------------------
# Reading the network's own columns
# --------------------------------------------------------------------------
#
# ``_numeric``, ``_capacity_mw`` and ``_availability_frame`` used to live here.
# They are readers of a *network*, not of a market, and `planning/balance.py`
# needs all three -- so they moved down to Layer 1 and this module imports them
# under the private names its callers already use. Two copies of "what a
# generator's capacity is" is how a market and a balance come to disagree about
# the same plant; there is one copy now, and it is in the layer that owns the
# network.


def load_series(network: pypsa.Network) -> np.ndarray:
	"""Total load per snapshot, in MW. The Layer 1 reader, under this layer's name.

	`market/service.py` and the market tests import it from here, and it lives in
	`planning/balance.py` now -- so this delegates rather than copying. Two
	readers of the same column is how a market and a balance come to disagree
	about one network, which is the defect the move exists to prevent.

	**Why the import is inside the function.** `config.models` imports
	`market.views`, which imports this package, which imports this module -- and a
	module-level `from alea.planning import balance` would run
	`planning/__init__`, which imports `expansion`, which imports `config.models`
	*while it is still initialising*. The result is an ImportError at collection
	for every test in the suite. `market/stages.py` imports
	`planning.arrays` lazily for the same reason; this follows it.
	"""
	from alea.planning import balance

	return balance.load_series(network)


def _marginal_cost(generators: pd.DataFrame) -> np.ndarray:
	"""The network's own marginal cost per generator, USD/MWh.

	A network with no ``marginal_cost`` column is treated as zero-cost, which is
	what PyPSA does with an absent column and is stated here rather than
	inherited: a fleet whose costs are all zero clears at zero and the artefact
	says so through its provenance.

	This one stayed here when its neighbours moved to `planning/balance.py`: a
	marginal cost is what a *bidder* offers at, and nothing outside the market
	layer reads it.
	"""
	from alea.planning import balance

	if "marginal_cost" not in generators.columns:
		return np.zeros(len(generators), dtype=np.float64)
	return balance.numeric_column(generators, "marginal_cost")


def _offered_fraction(profile: pd.DataFrame, snapshot: Any) -> np.ndarray:
	"""Each generator's offered fraction of nameplate, at ``snapshot`` or on average.

	Clamped to [0, 1]: a ``p_max_pu`` above 1 is an over-planting assumption the
	schema refuses, and one below 0 is not a physical offer. A mean is taken over
	the snapshots the profile covers, which is the period-average fleet -- the
	right one to clear against average demand and stated in ``build_fleet``.
	"""
	if len(profile) == 0:
		return np.ones(profile.shape[1], dtype=np.float64)
	if snapshot is not None:
		if snapshot not in profile.index:
			raise KeyError(f"snapshot {snapshot!r} is not in the availability profile")
		values = np.asarray(profile.loc[snapshot].to_numpy(dtype=float), dtype=np.float64)
	else:
		values = np.asarray(profile.mean(axis=0).to_numpy(dtype=float), dtype=np.float64)
	return np.clip(np.nan_to_num(values, nan=0.0), 0.0, 1.0)


__all__ = [
	"LOAD_SHEDDING_CARRIERS",
	"build_fleet",
	"build_fleet_series",
	"fleet_energy_mwh",
	"load_series",
	"peak_snapshot",
]
