# SPDX-License-Identifier: MIT
"""Layer 3 artefact schemas.

Every number Layer 3 produces is a value that will be quoted in a PPA term
sheet or a risk report, so the schemas carry the conditions that make the
number readable, not just the number. A clearing price is meaningless without
the demand it cleared against and the unserved energy that was priced at VoLL;
a capture price is meaningless without knowing whether the technology generated
at all; a PPA price is meaningless without the FX rate and the rate's date that
produced it.

``extra="forbid"`` is the same rule as everywhere else: a misspelled key in a
bid file is a column that silently disappears from a dispatch, and the dispatch
still sums to something plausible.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alea.provenance.models import Provenance

# Prices and quantities are finite. NaN and infinity are refused at the schema
# boundary: a NaN that reaches an artefact is a NaN that reaches a report, and
# every arithmetic operation downstream inherits it.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFinite = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
PositiveFinite = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class MarketModel(BaseModel):
	"""Base for every Layer 3 model."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		frozen=True,
	)


def _nan_to_none(value: float | None) -> float | None:
	"""Map NaN to ``None`` for a field whose absence is a real state.

	A capture price of NaN is "no observation", which JSON cannot express as a
	number. ``None`` is the artefact encoding of NaN and is never confused with
	zero, which is a specific and false claim. See ``market.capture``.
	"""
	if value is None:
		return None
	return None if math.isnan(value) else value


# --------------------------------------------------------------------------
# Clearing
# --------------------------------------------------------------------------


class Bid(MarketModel):
	"""One unit's offer into the stack.

	``marginal_cost_usd_per_mwh`` is carried alongside the bid price so a
	clearing result decomposes into what produced it: the bid is the strategic
	choice, the marginal cost is the physical one, and the gap between them is
	the finding.
	"""

	unit_id: str
	quantity_mw: NonNegativeFinite
	price_usd_per_mwh: FiniteFloat
	"""Offer price. May be negative: a curtailed unit or a must-run plant will
	pay to stay on, and refusing negative prices would silently drop it."""
	available: bool = True
	carrier: str | None = None
	zone_id: str = "national"
	marginal_cost_usd_per_mwh: FiniteFloat | None = None


class ClearingResult(MarketModel):
	"""The outcome of clearing one market against one demand.

	``unserved_mwh`` and ``shortage_price_usd_per_mwh`` are not diagnostics:
	a stack that could not meet demand cleared at VoLL, and reporting its
	clearing price without the shortfall is how a market model reports a price
	for a system that was in blackout.
	"""

	demand_mw: NonNegativeFinite
	clearing_price_usd_per_mwh: FiniteFloat
	dispatched: dict[str, float] = Field(default_factory=dict)
	"""``unit_id`` -> MW delivered."""
	unserved_mwh: NonNegativeFinite
	shortage_price_usd_per_mwh: NonNegativeFinite

	@model_validator(mode="after")
	def _dispatch_and_unserved_account_for_demand(self) -> ClearingResult:
		# Conservation: what was dispatched plus what was not served is the
		# demand. A result that does not balance is a result with a unit of
		# energy that appeared or vanished.
		total = sum(self.dispatched.values())
		accounted = total + self.unserved_mwh
		tolerance = 1e-6 * max(1.0, self.demand_mw)
		if abs(accounted - self.demand_mw) > tolerance:
			raise ValueError(
				f"dispatched ({total}) + unserved ({self.unserved_mwh}) = "
				f"{accounted}, which is not demand ({self.demand_mw})"
			)
		return self

	@property
	def total_dispatched_mw(self) -> float:
		return sum(self.dispatched.values())

	@property
	def demand_met(self) -> bool:
		return self.unserved_mwh <= 1e-9


class Interface(MarketModel):
	"""A transfer corridor between two zones."""

	from_zone: str
	to_zone: str
	limit_mw: PositiveFinite
	susceptance: PositiveFinite = 1.0
	"""Relative electrical stiffness of the corridor, for the DC power flow."""


class InterfaceFlow(MarketModel):
	"""A corridor's loading in a cleared solution."""

	from_zone: str
	to_zone: str
	flow_mw: FiniteFloat
	"""Signed: positive means power flows ``from_zone`` -> ``to_zone``."""
	limit_mw: PositiveFinite
	congested: bool

	@property
	def loading(self) -> float:
		"""Fraction of the corridor's limit used, in [0, inf)."""
		return abs(self.flow_mw) / self.limit_mw


class ZonalZoneResult(MarketModel):
	"""One zone's position in a zonal clearing.

	Separate from ``ClearingResult`` because a zone in a coupled market is not a
	closed market: an importing zone's generation is below its demand and the
	gap is a scheduled import, not unserved energy. Reporting that gap as
	"unserved" would call a healthy trade a blackout.
	"""

	zone_id: str
	demand_mw: NonNegativeFinite
	generation_mw: NonNegativeFinite
	net_import_mw: FiniteFloat
	"""Positive when the zone imports: ``demand - generation - unserved``. An
	unserved MWh is demand the zone's own generation and its scheduled imports
	failed to meet, so it sits on the demand side of the balance, not the supply
	side."""
	price_usd_per_mwh: FiniteFloat
	unserved_mwh: NonNegativeFinite
	dispatched: dict[str, float] = Field(default_factory=dict)

	@model_validator(mode="after")
	def _generation_and_imports_meet_demand(self) -> ZonalZoneResult:
		# demand = generation + net imports + unserved. Unserved energy is demand
		# that was not met, so it *adds* to the requirement; subtracting it would
		# let a zone in blackout look balanced and let the schema reject the
		# honest arithmetic. See ``market.clearing._zone_results``.
		balance = self.generation_mw + self.net_import_mw + self.unserved_mwh
		tolerance = 1e-6 * max(1.0, self.demand_mw)
		if abs(balance - self.demand_mw) > tolerance:
			raise ValueError(
				f"zone {self.zone_id}: generation ({self.generation_mw}) + imports "
				f"({self.net_import_mw}) + unserved ({self.unserved_mwh}) = {balance}, "
				f"not demand ({self.demand_mw})"
			)
		return self


class ZonalClearingResult(MarketModel):
	"""The outcome of clearing a market with internal transmission limits.

	Zones that a corridor couples tightly clear at one price; where a corridor
	binds, the zones split into distinct prices and the corridor is congested.
	The price difference across a congested corridor times its flow is the
	congestion rent.
	"""

	zones: dict[str, ZonalZoneResult]
	interfaces: list[InterfaceFlow] = Field(default_factory=list)
	system_price_usd_per_mwh: FiniteFloat | None
	"""The single price when no corridor binds; ``None`` when the market split."""
	congestion_rent_usd: NonNegativeFinite = 0.0
	converged: bool = True

	@property
	def congested_interfaces(self) -> list[InterfaceFlow]:
		return [i for i in self.interfaces if i.congested]

	@property
	def is_split(self) -> bool:
		"""Whether zonal prices differ, i.e. the market did not clear as one."""
		prices = {round(z.price_usd_per_mwh, 6) for z in self.zones.values()}
		return len(prices) > 1


# --------------------------------------------------------------------------
# Capture prices
# --------------------------------------------------------------------------


class CapturePrice(MarketModel):
	"""One technology's revenue-weighted realised price over a period.

	``capture_price_usd_per_mwh`` is ``None`` when the technology generated
	nothing in the period. That is the artefact encoding of NaN: the value is
	undefined, and writing 0 would assert the technology sold its output at
	zero, which drags every portfolio average down.
	"""

	carrier: str
	generation_mwh: NonNegativeFinite
	capture_price_usd_per_mwh: FiniteFloat | None
	time_weighted_price_usd_per_mwh: FiniteFloat | None
	capture_rate: FiniteFloat | None
	n_observations: int = Field(ge=0)
	period_start: datetime | None = None
	period_end: datetime | None = None

	@model_validator(mode="after")
	def _no_generation_has_no_capture_price(self) -> CapturePrice:
		if self.generation_mwh <= 0.0 and self.capture_price_usd_per_mwh is not None:
			raise ValueError(
				"a technology that generated nothing has no capture price; "
				f"got {self.capture_price_usd_per_mwh}"
			)
		return self

	@classmethod
	def from_float(
		cls,
		*,
		carrier: str,
		generation_mwh: float,
		capture_price_usd_per_mwh: float,
		time_weighted_price_usd_per_mwh: float,
		capture_rate: float,
		n_observations: int,
		period_start: datetime | None = None,
		period_end: datetime | None = None,
	) -> CapturePrice:
		"""Build from float results, mapping NaN to ``None`` on the way in."""
		return cls(
			carrier=carrier,
			generation_mwh=generation_mwh,
			capture_price_usd_per_mwh=_nan_to_none(capture_price_usd_per_mwh),
			time_weighted_price_usd_per_mwh=_nan_to_none(time_weighted_price_usd_per_mwh),
			capture_rate=_nan_to_none(capture_rate),
			n_observations=n_observations,
			period_start=period_start,
			period_end=period_end,
		)


class CaptureCurvePoint(MarketModel):
	"""One point on a cannibalisation curve."""

	vre_share: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
	capture_rate: FiniteFloat | None
	cannibalisation: FiniteFloat | None
	"""``1 - capture_rate``: the fraction of the time-weighted price a
	technology loses to its own and its peers' output."""


# --------------------------------------------------------------------------
# Fuel prices and marginal cost
# --------------------------------------------------------------------------


class FuelPriceSeries(MarketModel):
	"""A fuel price as a series, never a bare constant.

	Marginal cost is the largest single term in a thermal unit's bid, so a fuel
	price that is a constant is a hidden assumption that never changes with the
	scenario. This model forces the series and its provenance to travel with the
	number, so a marginal cost can always name the series and the year it used.
	"""

	fuel: str
	country_iso: str
	unit: str = "USD/MWh_fuel"
	"""Unit of the price. Thermal marginal cost divides by the unit's
	efficiency to reach USD/MWh of electricity."""
	prices: dict[int, NonNegativeFinite] = Field(min_length=1)
	"""``year`` -> price. Keyed by year so a study can select the year it models
	and fail loudly when the year is absent."""
	provenance: Provenance

	def price(self, year: int) -> float:
		"""The price for a year, raising when the year is not held.

		Falling back to the nearest year is how a study silently uses a 2019
		price in a 2030 scenario. The absence is a data gap and is reported.
		"""
		if year not in self.prices:
			raise KeyError(
				f"no {self.fuel} price for {self.country_iso} in {year}; "
				f"held years: {sorted(self.prices)}"
			)
		return self.prices[year]


class MarginalCostComponents(MarketModel):
	"""A unit's marginal cost, decomposed into the terms that produced it.

	``marginal_cost = fuel + carbon_price * co2_intensity + vom``. Recording the
	parts, and the fuel series and year behind the fuel term, is what lets a
	clearing price be decomposed into what produced it rather than asserted.
	"""

	carrier: str
	fuel_cost_usd_per_mwh: NonNegativeFinite
	carbon_cost_usd_per_mwh: NonNegativeFinite
	vom_usd_per_mwh: NonNegativeFinite
	total_usd_per_mwh: FiniteFloat

	fuel: str | None = None
	fuel_price_usd_per_mwh: FiniteFloat | None = None
	fuel_price_year: int | None = None
	fuel_price_source_id: str | None = None
	"""The series behind the fuel term. Present whenever the fuel term is
	non-zero, so the cost can be traced to a source."""
	efficiency: PositiveFinite = 1.0
	carbon_price_usd_per_t: NonNegativeFinite = 0.0
	co2_t_per_mwh: NonNegativeFinite = 0.0

	@model_validator(mode="after")
	def _total_is_the_sum_of_parts(self) -> MarginalCostComponents:
		# A decomposition whose parts do not sum to the total is worse than no
		# decomposition: it looks like an analysis.
		parts = (
			self.fuel_cost_usd_per_mwh
			+ self.carbon_cost_usd_per_mwh
			+ self.vom_usd_per_mwh
		)
		if abs(parts - self.total_usd_per_mwh) > 1e-6 * max(1.0, abs(self.total_usd_per_mwh)):
			raise ValueError(
				f"marginal cost parts sum to {parts}, not {self.total_usd_per_mwh}"
			)
		return self

	@model_validator(mode="after")
	def _fuel_term_names_its_series(self) -> MarginalCostComponents:
		if self.fuel_cost_usd_per_mwh > 0.0 and not self.fuel_price_source_id:
			raise ValueError(
				"a non-zero fuel cost must name the fuel price series it came "
				"from; an untraceable fuel cost is an assumption, not a datum"
			)
		return self


# --------------------------------------------------------------------------
# PPA benchmarks
# --------------------------------------------------------------------------


class FxRate(MarketModel):
	"""A currency conversion rate and the date it was quoted.

	A rate without its date is not a rate. The project's own history includes a
	document that converted $1M at 145 KES while stating its target in KES at a
	different implied rate: a 10% self-contradiction no lint could see, because
	each number was internally consistent with its own line.
	"""

	local_per_usd: PositiveFinite
	rate_date: str
	"""ISO 8601 date of the quote. Required, never defaulted."""
	source: str
	"""Where the rate came from, e.g. ``CBK`` or ``config.costs.kes_usd``."""


class PpaBenchmark(MarketModel):
	"""A PPA price for one technology, country, and tenor.

	Three adjustments are applied, each recorded: the tenor (capture price over
	the contract, not year one), the currency basis (local vs USD), and the
	counterparty credit spread. Every one is written into the artefact, because
	a PPA price nobody can decompose is a number a lender will not accept.
	"""

	country_iso: str
	carrier: str
	tenor_years: int = Field(gt=0)
	base_capture_price_usd_per_mwh: FiniteFloat
	credit_spread_pct: FiniteFloat = 0.0
	credit_source: str = ""
	fx_basis_pct: FiniteFloat = 0.0
	fx_basis_source: str = ""
	fx: FxRate | None = None
	price_usd_per_mwh: FiniteFloat
	price_local_per_mwh: FiniteFloat | None = None
	provenance: Provenance | None = None

	@model_validator(mode="after")
	def _local_price_records_its_rate(self) -> PpaBenchmark:
		# A local-currency price with no rate cannot be re-derived, and a rate
		# that is not carried is a conversion someone will redo differently.
		if self.price_local_per_mwh is not None and self.fx is None:
			raise ValueError(
				"a local-currency PPA price requires the FX rate and its date"
			)
		if self.fx_basis_pct != 0.0 and not self.fx_basis_source:
			raise ValueError("a non-zero fx_basis_pct requires fx_basis_source")
		if self.credit_spread_pct != 0.0 and not self.credit_source:
			raise ValueError("a non-zero credit_spread_pct requires credit_source")
		return self


# --------------------------------------------------------------------------
# Bankability
# --------------------------------------------------------------------------


class BankabilityResult(MarketModel):
	"""DSCR, project IRR, and equity IRR for one scenario."""

	currency: str = "USD"
	dscr: list[FiniteFloat | None] = Field(default_factory=list)
	"""Debt service coverage ratio, one per period. ``None`` where the ratio is
	undefined: a construction or grace period with no debt service has no ratio
	to report, and ``dscr`` returns ``inf`` there. The schema refuses infinity
	(``FiniteFloat``), so the artefact encodes it as ``None`` -- the same rule
	capture prices follow for NaN. Writing ``inf`` into a JSON artefact is not
	possible and raising on it made a standard grace period unrepresentable."""
	min_dscr: FiniteFloat | None = None
	project_irr: FiniteFloat | None = None
	equity_irr: FiniteFloat | None = None
	npv_usd: FiniteFloat
	"""Net present value of the project cash flows at the discount rate."""
	discount_rate: Annotated[float, Field(gt=-1.0, allow_inf_nan=False)] = 0.08
	years: int = Field(ge=0)


# --------------------------------------------------------------------------
# Risk
# --------------------------------------------------------------------------


class RiskResult(MarketModel):
	"""VaR and CVaR as **positive loss magnitudes**.

	The sign convention is the single most common source of error in risk
	reporting: a negative VaR quoted as a loss flips the meaning of every number
	downstream. The kernel guarantees ``CVaR >= VaR >= 0`` for a loss-tailed
	sample, and this model enforces it.
	"""

	confidence: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]
	value_at_risk_usd: NonNegativeFinite
	conditional_value_at_risk_usd: NonNegativeFinite
	expected_shortfall_usd: NonNegativeFinite | None = None
	"""Alias of CVaR, carried explicitly so a report that asks for "expected
	shortfall" reads the same number the kernel produced."""
	n_paths: int = Field(ge=0)
	threshold_usd: FiniteFloat | None = None
	exceedance_probability: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)] | None = None

	@model_validator(mode="after")
	def _loss_magnitudes_are_ordered(self) -> RiskResult:
		if self.conditional_value_at_risk_usd < self.value_at_risk_usd - 1e-9:
			raise ValueError(
				f"CVaR ({self.conditional_value_at_risk_usd}) must be >= VaR "
				f"({self.value_at_risk_usd}); a tail mean below the quantile is a "
				f"sign error"
			)
		return self


__all__ = [
	"BankabilityResult",
	"Bid",
	"CaptureCurvePoint",
	"CapturePrice",
	"ClearingResult",
	"FiniteFloat",
	"FuelPriceSeries",
	"FxRate",
	"Interface",
	"InterfaceFlow",
	"MarginalCostComponents",
	"MarketModel",
	"NonNegativeFinite",
	"PpaBenchmark",
	"PositiveFinite",
	"RiskResult",
	"ZonalClearingResult",
	"ZonalZoneResult",
]
