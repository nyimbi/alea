# SPDX-License-Identifier: MIT
"""Layer 3 — market simulation.

What an optimiser cannot answer: *what price* results from a given system, and
*what is that price worth* to a specific asset or contract.

The layer is a merit-order clearing engine with explicit strategic markups
(``clearing``, ``strategy``, ``agents``), the capture and cannibalisation
analysis built on it (``capture``), PPA benchmarks and bankability
(``ppa``, ``bankability``), fuel prices and marginal cost (``fuel``), and
portfolio risk over the Rust ``alea-risk`` kernel (``risk``).

Three defects in the specification's example are corrected here and are worth
naming once, where a reader meets the package:

* Capture price is NaN (``None`` in an artefact), not 0, when a technology
  generated nothing. A zero is a fabricated observation.
* VaR/CVaR are positive loss magnitudes, and ``CVaR >= VaR >= 0``.
* Every currency conversion records its rate and the rate's date.
"""

from alea.market.agents import Agent, BiddingUnit, build_stack, markup_summary
from alea.market.bankability import bankability, dscr, irr, npv
from alea.market.capture import (
	cannibalisation_curve,
	capture_by_technology,
	capture_price,
	capture_rate,
	portfolio_capture,
	time_weighted_price,
)
from alea.market.clearing import (
	clear_market,
	clear_market_series,
	clear_market_zonal,
	merit_order_stack,
)
from alea.market.fuel import (
	FUEL_PRICE_SOURCE_ID,
	fuel_price_series,
	marginal_cost,
	marginal_cost_table,
)
from alea.market.ppa import (
	fx_rate_from_config,
	ppa_benchmark,
	ppa_curve,
	tenor_capture_price,
	to_local,
)
from alea.market.risk import (
	checked_cholesky,
	correlated_shocks,
	exceedance,
	monte_carlo_risk,
	portfolio_risk,
	value_at_risk,
)
from alea.market.strategy import Strategy, StrategyKind, conduct_to_markup
from alea.market.views import (
	BankabilityResult,
	Bid,
	CaptureCurvePoint,
	CapturePrice,
	ClearingResult,
	FuelPriceSeries,
	FxRate,
	Interface,
	InterfaceFlow,
	MarginalCostComponents,
	PpaBenchmark,
	RiskResult,
	ZonalClearingResult,
)

__all__ = [
	"Agent",
	"BankabilityResult",
	"Bid",
	"BiddingUnit",
	"CaptureCurvePoint",
	"CapturePrice",
	"ClearingResult",
	"FUEL_PRICE_SOURCE_ID",
	"FuelPriceSeries",
	"FxRate",
	"Interface",
	"InterfaceFlow",
	"MarginalCostComponents",
	"PpaBenchmark",
	"RiskResult",
	"Strategy",
	"StrategyKind",
	"ZonalClearingResult",
	"bankability",
	"build_stack",
	"cannibalisation_curve",
	"capture_by_technology",
	"capture_price",
	"capture_rate",
	"checked_cholesky",
	"clear_market",
	"clear_market_series",
	"clear_market_zonal",
	"conduct_to_markup",
	"correlated_shocks",
	"dscr",
	"exceedance",
	"fuel_price_series",
	"fx_rate_from_config",
	"irr",
	"marginal_cost",
	"marginal_cost_table",
	"markup_summary",
	"merit_order_stack",
	"monte_carlo_risk",
	"npv",
	"portfolio_capture",
	"portfolio_risk",
	"ppa_benchmark",
	"ppa_curve",
	"tenor_capture_price",
	"time_weighted_price",
	"to_local",
	"value_at_risk",
]
