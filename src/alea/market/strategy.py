# SPDX-License-Identifier: MIT
"""Strategic bidding.

The specification's example constructs a separate PPO policy per generator
agent: no training loop, no shared learning, no episode structure, and at
continental scale thousands of independent neural networks. It is also
non-deterministic, which AD-8 forbids for anything that feeds a published
number. That design is rejected here (06-layer3 §2.2, §4.3).

What replaces it is a **parametric strategy with an explicit markup function**.
The strategy is a small, auditable map from marginal cost to bid price, with a
conduct parameter whose endpoints are calibrated against known market outcomes.
The strategic question — what markup? — is separated from the mechanical one —
what price results? — and that separation is what makes a clearing result
interpretable.

Every strategy is reported *against* the competitive benchmark. A market result
without a competitive bid beside it cannot be read: nobody can tell whether a
price is the modelling or the finding.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from alea.market.views import MarketModel, NonNegativeFinite


class StrategyKind(StrEnum):
	"""How a unit chooses its bid price."""

	COMPETITIVE = "competitive"
	"""Bid at marginal cost. The benchmark every other strategy is read against."""
	MARKUP = "markup"
	"""Cost x (1 + m). A fixed fractional markup over cost."""
	SUPPLY_FUNCTION = "supply_function"
	"""Supply-function equilibrium. A conduct parameter alpha interpolates from
	competitive (alpha=0) toward monopoly (alpha=1)."""
	HEDGE = "hedge"
	"""Bid to protect a contracted forward position."""


class Strategy(MarketModel):
	"""A bidding rule. Deterministic: the same cost gives the same bid, always."""

	kind: StrategyKind
	markup: float = Field(default=0.0, ge=-1.0)
	"""Fractional markup over marginal cost. Only for ``MARKUP``. Bounded below
	by -1 so a bid cannot be negative-infinite; negative markups are permitted
	and mean bidding below cost, which a must-run unit does."""
	supply_function_alpha: float = Field(default=0.0, ge=0.0, le=1.0)
	"""Conduct parameter. 0 = competitive, 1 = monopoly. Only for
	``SUPPLY_FUNCTION``. Its endpoints are calibrated in a test against a
	Cournot benchmark; otherwise it is a knob with units of nothing."""
	contract_cover_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
	"""Fraction of capacity sold forward at a fixed price. Only for ``HEDGE``."""
	forward_price_usd_per_mwh: NonNegativeFinite | None = None
	"""For ``HEDGE``: the price the contracted volume is sold at, agreed before
	the spot clears. The contracted revenue is safe, so it lowers the effective
	cost of the uncontracted volume and the unit bids below marginal cost to
	stay dispatched. A HEDGE strategy without a forward price cannot be priced
	and is refused at construction."""

	@model_validator(mode="after")
	def _parameters_match_the_kind(self) -> Strategy:
		# A parameter set for a kind that does not read it is a strategy whose
		# author believes it does something. Failing at construction beats
		# discovering at hour five that the markup was ignored.
		if self.kind is StrategyKind.HEDGE and self.forward_price_usd_per_mwh is None:
			raise ValueError(
				"a HEDGE strategy needs forward_price_usd_per_mwh: without the "
				"price the contracted volume is sold at, the hedge cannot be "
				"priced and the field would be decorative"
			)
		return self

	def bid_price(self, marginal_cost_usd_per_mwh: float) -> float:
		"""Bid price for a unit with this marginal cost.

		Pure and deterministic. The competitive benchmark is the marginal cost,
		and every result is reported against it.
		"""
		assert marginal_cost_usd_per_mwh == marginal_cost_usd_per_mwh, "cost is NaN"

		match self.kind:
			case StrategyKind.COMPETITIVE:
				return marginal_cost_usd_per_mwh
			case StrategyKind.MARKUP:
				return marginal_cost_usd_per_mwh * (1.0 + self.markup)
			case StrategyKind.SUPPLY_FUNCTION:
				# The supply-function-equilibrium conduct parameter: a fraction
				# alpha of the way from competitive to the monopoly price. The
				# monopoly price is not known analytically at bid time, so alpha
				# is applied as a markup on cost and calibrated against a Cournot
				# benchmark in a test (06-layer3 §4.1).
				return marginal_cost_usd_per_mwh * (1.0 + self.supply_function_alpha)
			case StrategyKind.HEDGE:
				# The contracted volume earns the forward price regardless of
				# the spot outcome, so its revenue is already banked. What the
				# unit must still cover on the uncontracted volume is the cost
				# of the *whole* unit less that banked revenue: bidding at that
				# effective cost guarantees dispatch without giving away money
				# on the uncovered volume. With no cover the hedge is a no-op
				# and the bid is the marginal cost, as the field defaults imply.
				cover = self.contract_cover_fraction
				forward = self.forward_price_usd_per_mwh
				if cover <= 0.0 or forward is None:
					return marginal_cost_usd_per_mwh
				if cover >= 1.0:
					return 0.0
				return max(
					0.0,
					marginal_cost_usd_per_mwh - (cover / (1.0 - cover)) * forward,
				)
		raise ValueError(f"unhandled strategy kind: {self.kind}")  # pragma: no cover

	@classmethod
	def competitive(cls) -> Strategy:
		return cls(kind=StrategyKind.COMPETITIVE)

	@classmethod
	def from_markup(cls, markup: float) -> Strategy:
		return cls(kind=StrategyKind.MARKUP, markup=markup)

	@classmethod
	def from_conduct(cls, alpha: float) -> Strategy:
		return cls(kind=StrategyKind.SUPPLY_FUNCTION, supply_function_alpha=alpha)


def conduct_to_markup(alpha: float) -> float:
	"""The fractional markup a conduct parameter implies.

	Kept as a named function because it is the calibration surface: a test
	asserts alpha=0 reproduces the competitive price and alpha=1 reproduces the
	monopoly price on a synthetic network. If that test moves, this moves.
	"""
	assert 0.0 <= alpha <= 1.0, f"conduct parameter {alpha} outside [0, 1]"
	return float(alpha)


__all__ = [
	"Strategy",
	"StrategyKind",
	"conduct_to_markup",
]
