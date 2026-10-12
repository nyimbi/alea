# SPDX-License-Identifier: MIT
"""Bankability: DSCR, project IRR, equity IRR.

The inputs are Layer 3's price forecast and Layer 1's cost data; the calculation
is arithmetic. Because it is arithmetic it is easy to get subtly wrong, so it is
implemented plainly and checked against a hand-computed fixture rather than
hidden behind a financial library (06-layer3 §7.1). A DSCR computed by a black
box is a DSCR a lender cannot audit.

Definitions used, stated because they are not universal:

* **CFADS** — cash flow available for debt service, per period.
* **DSCR** — ``CFADS / debt_service``. Below 1.0 the project cannot meet its
  debt service from operating cash flow.
* **Project IRR** — the discount rate at which the project's unlevered cash
  flows have zero NPV.
* **Equity IRR** — the same for the equity cash flows (project cash flows after
  debt service, less equity drawdowns).

An IRR is undefined when the cash flows never change sign (all-positive or
all-negative): there is no rate at which NPV crosses zero. That is returned as
``None``, never as a fabricated number.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.market.views import BankabilityResult

logger = get_logger(__name__)


def npv(cashflows: Sequence[float] | NDArray[np.float64], rate: float) -> float:
	"""Net present value of a cash flow series, discounted from period 0.

	Period 0 is undiscounted. This matches the usual project-finance convention,
	where the first entry is the initial outlay.
	"""
	assert rate > -1.0, f"discount rate must exceed -100%, got {rate}"
	flows = np.asarray(cashflows, dtype=np.float64)
	if flows.size == 0:
		return 0.0
	periods = np.arange(flows.size, dtype=np.float64)
	return float(np.sum(flows / (1.0 + rate) ** periods))


def irr(cashflows: Sequence[float] | NDArray[np.float64], *, tolerance: float = 1e-9) -> float | None:
	"""Internal rate of return, or ``None`` when it is undefined.

	Found by bisection on NPV over a wide rate bracket, which is robust for the
	conventional single-sign-change cash flow and honest when the bracket holds
	no crossing. A cash flow series that never changes sign has no IRR, and
	returning a number there would be inventing one.
	"""
	flows = np.asarray(cashflows, dtype=np.float64)
	assert flows.size >= 2, "an IRR needs at least two periods"
	positive = np.any(flows > 0.0)
	negative = np.any(flows < 0.0)
	if not (positive and negative):
		return None

	low, high = -0.9999, 10.0
	f_low, f_high = npv(flows, low), npv(flows, high)
	if f_low * f_high > 0.0:
		# No sign change in the bracket: either no real root or the root is
		# outside the plausible range. Report undefined rather than clamp.
		return None
	for _ in range(200):
		mid = 0.5 * (low + high)
		f_mid = npv(flows, mid)
		if abs(f_mid) < tolerance:
			return float(mid)
		if f_low * f_mid < 0.0:
			high, f_high = mid, f_mid
		else:
			low, f_low = mid, f_mid
	return float(0.5 * (low + high))


def dscr(
	cfads: Sequence[float] | NDArray[np.float64],
	debt_service: Sequence[float] | NDArray[np.float64],
) -> list[float]:
	"""Debt service coverage ratio per period.

	Periods with zero debt service produce ``inf`` (fully covered by
	construction) rather than a divide-by-zero. A period with negative CFADS and
	zero debt service is undefined and produces NaN, which is the honest answer:
	there was no service to cover.
	"""
	cash = np.asarray(cfads, dtype=np.float64)
	service = np.asarray(debt_service, dtype=np.float64)
	assert cash.shape == service.shape, (
		f"CFADS {cash.shape} and debt service {service.shape} must align"
	)
	with np.errstate(divide="ignore", invalid="ignore"):
		ratio = np.where(service == 0.0, np.where(cash >= 0.0, np.inf, np.nan), cash / service)
	return [float(v) for v in ratio]


def bankability(
	cfads: Sequence[float],
	debt_service: Sequence[float],
	*,
	equity_cashflows: Sequence[float] | None = None,
	discount_rate: float = 0.08,
	currency: str = "USD",
) -> BankabilityResult:
	"""Assemble DSCR, project IRR, equity IRR, and NPV for one scenario.

	``cfads`` and ``debt_service`` are the project's operating cash flows and its
	debt repayments. ``equity_cashflows``, when given, are the equity holder's
	own flows (drawdowns negative, distributions positive); the equity IRR is
	computed from them, and falls back to the project flows when absent.
	"""
	cash = np.asarray(cfads, dtype=np.float64)
	service = np.asarray(debt_service, dtype=np.float64)
	assert cash.size == service.size, "CFADS and debt service must have equal length"
	assert cash.size >= 1, "at least one period is required"

	ratios = dscr(cash, service)
	finite_ratios = [r for r in ratios if np.isfinite(r)]
	project_flows = cash - service
	equity = np.asarray(equity_cashflows, dtype=np.float64) if equity_cashflows is not None else project_flows
	assert equity.size == cash.size, "equity cash flows must match the CFADS length"

	result = BankabilityResult(
		currency=currency,
		# ``inf`` is a covered period with no service to cover (a construction or
		# grace period); it is not a finite ratio and JSON cannot carry it, so it
		# is written as ``None``. ``min_dscr`` is computed from the finite ratios
		# only, because an infinite ratio never binds the minimum.
		dscr=[float(r) if np.isfinite(r) else None for r in ratios],
		min_dscr=min(finite_ratios) if finite_ratios else None,
		project_irr=irr(project_flows),
		equity_irr=irr(equity),
		npv_usd=npv(project_flows, discount_rate),
		discount_rate=discount_rate,
		years=int(cash.size),
	)
	logger.info(
		"bankability",
		years=result.years,
		min_dscr=result.min_dscr,
		project_irr=result.project_irr,
		equity_irr=result.equity_irr,
		npv_usd=round(result.npv_usd, 2),
	)
	return result


__all__ = [
	"bankability",
	"dscr",
	"irr",
	"npv",
]
