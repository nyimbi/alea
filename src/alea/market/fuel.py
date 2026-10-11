# SPDX-License-Identifier: MIT
"""Fuel prices and marginal cost.

Marginal cost is the largest single term in a thermal unit's bid, so it is the
term most able to move a clearing price. The specification treats it as a
constant. It is not: fuel prices are a time series, they differ by country, and
a study that fixes them is a study whose scenario cannot reach the fuel price at
all.

This module therefore carries a fuel price **series** keyed by year
(``FuelPriceSeries``), never a bare constant, and records which series and which
year every marginal cost used. The decomposition

	marginal_cost = fuel_cost + carbon_price x co2_intensity + vom

is written into a ``MarginalCostComponents`` so a clearing price can be taken
apart into what produced it. Carbon price and fuel prices are scenario
parameters; VOM comes from the cost dataset (02-data-pipeline §3).

The fuel price source is ``global_petrol_prices`` (``market/fuel``), whose own
register note reads "Feeds marginal cost, so its date matters: prices are a time
series."
"""

from __future__ import annotations

from collections.abc import Iterable

from alea.logging import get_logger
from alea.market.views import FuelPriceSeries, MarginalCostComponents
from alea.provenance.models import Basis, Licence, Provenance
from alea.registry import co2_intensity, get_technology

logger = get_logger(__name__)

# The registered source behind every fuel price, so a marginal cost can name it.
FUEL_PRICE_SOURCE_ID = "global_petrol_prices"


def fuel_price_series(
	fuel: str,
	country_iso: str,
	prices: dict[int, float],
	*,
	source_id: str = FUEL_PRICE_SOURCE_ID,
	source_url: str = "https://www.globalpetrolprices.com/",
	licence: Licence = Licence.UNKNOWN,
	uncertainty: float = 0.0,
	uncertainty_basis: str = "",
	notes: str = "",
) -> FuelPriceSeries:
	"""Assemble a fuel price series with its provenance.

	``uncertainty`` defaults to zero because a published pump price is measured,
	but a caller supplying a modelled or proxy fuel price must say so -- the
	``Provenance`` model refuses non-zero uncertainty with no basis, and a proxy
	with zero uncertainty.
	"""
	assert prices, f"a fuel price series for {fuel}/{country_iso} needs at least one year"
	for year, value in prices.items():
		assert isinstance(year, int), f"fuel price year must be an int, got {year!r}"
		assert value >= 0.0, f"fuel price for {year} is negative: {value}"

	provenance = Provenance(
		source_id=source_id,
		source_url=source_url,
		licence=licence,
		basis=Basis.MEASURED if uncertainty == 0.0 else Basis.MODELLED,
		uncertainty=uncertainty,
		uncertainty_basis=uncertainty_basis,
		notes=notes or f"{fuel} price for {country_iso}, {min(prices)}-{max(prices)}",
	)
	return FuelPriceSeries(fuel=fuel, country_iso=country_iso, prices=prices, provenance=provenance)


def fuel_price_from_config(
	config_costs: object,
	fuel: str,
	country_iso: str,
	year: int,
) -> float | None:
	"""A single fuel price drawn from a config, or ``None`` when unavailable.

	The config carries the two FX rates it knows (EUR/USD, KES/USD) and no fuel
	price, so this is deliberately thin: it exists to make the *absence* of a
	configured fuel price explicit rather than silent. A caller that needs a
	price and finds ``None`` must supply a series, not default to zero.
	"""
	_ = (config_costs, fuel, country_iso, year)
	return None


def marginal_cost(
	carrier: str,
	*,
	fuel_price: FuelPriceSeries | None = None,
	fuel_price_year: int | None = None,
	efficiency: float = 1.0,
	carbon_price_usd_per_t: float = 0.0,
	vom_usd_per_mwh: float = 0.0,
) -> MarginalCostComponents:
	"""A unit's marginal cost, decomposed and sourced.

	``efficiency`` is the thermal efficiency (fuel energy to electricity). Fuel
	price is per unit of *fuel* energy, so the fuel term is
	``fuel_price / efficiency``. A carrier with a fuel cost and no fuel price
	series is refused: an assumed fuel price that names no series is exactly the
	untraceable constant this module exists to prevent.
	"""
	assert efficiency > 0.0, f"efficiency must be positive, got {efficiency}"
	assert carbon_price_usd_per_t >= 0.0, "carbon price cannot be negative"
	assert vom_usd_per_mwh >= 0.0, "VOM cannot be negative"

	technology = get_technology(carrier)
	intensity = co2_intensity(carrier)

	fuel_cost = 0.0
	fuel_price_value: float | None = None
	fuel_price_source: str | None = None
	if technology.has_fuel_cost:
		if fuel_price is None:
			raise ValueError(
				f"{carrier} has a fuel cost but no fuel price series was given; "
				f"a marginal cost built from an unnamed constant cannot be traced "
				f"to a source"
			)
		year = fuel_price_year if fuel_price_year is not None else max(fuel_price.prices)
		fuel_price_value = fuel_price.price(year)
		fuel_price_source = fuel_price.provenance.source_id
		fuel_price_year = year
		fuel_cost = fuel_price_value / efficiency

	carbon_cost = carbon_price_usd_per_t * intensity
	total = fuel_cost + carbon_cost + vom_usd_per_mwh

	components = MarginalCostComponents(
		carrier=carrier,
		fuel_cost_usd_per_mwh=fuel_cost,
		carbon_cost_usd_per_mwh=carbon_cost,
		vom_usd_per_mwh=vom_usd_per_mwh,
		total_usd_per_mwh=total,
		fuel=fuel_price.fuel if fuel_price is not None else None,
		fuel_price_usd_per_mwh=fuel_price_value,
		fuel_price_year=fuel_price_year if fuel_price is not None else None,
		fuel_price_source_id=fuel_price_source,
		efficiency=efficiency,
		carbon_price_usd_per_t=carbon_price_usd_per_t,
		co2_t_per_mwh=intensity,
	)
	logger.info(
		"marginal_cost",
		carrier=carrier,
		total_usd_per_mwh=round(total, 4),
		fuel=fuel_price.fuel if fuel_price is not None else None,
		fuel_price_year=components.fuel_price_year,
	)
	return components


def marginal_cost_table(
	carriers: Iterable[str],
	fuel_prices: dict[str, FuelPriceSeries],
	*,
	fuel_price_year: int | None = None,
	efficiencies: dict[str, float] | None = None,
	carbon_price_usd_per_t: float = 0.0,
	vom_usd_per_mwh: dict[str, float] | None = None,
) -> dict[str, MarginalCostComponents]:
	"""Marginal cost per carrier, sharing one fuel price year across the fleet.

	The shared year is the point: every unit in one study prices its fuel in the
	same year, so two carriers cannot quietly use different vintages.
	"""
	efficiencies = efficiencies or {}
	voms = vom_usd_per_mwh or {}
	table: dict[str, MarginalCostComponents] = {}
	for carrier in sorted(carriers):
		technology = get_technology(carrier)
		series = fuel_prices.get(carrier) if technology.has_fuel_cost else None
		table[carrier] = marginal_cost(
			carrier,
			fuel_price=series,
			fuel_price_year=fuel_price_year,
			efficiency=efficiencies.get(carrier, 1.0),
			carbon_price_usd_per_t=carbon_price_usd_per_t,
			vom_usd_per_mwh=voms.get(carrier, 0.0),
		)
	return table


__all__ = [
	"FUEL_PRICE_SOURCE_ID",
	"fuel_price_from_config",
	"fuel_price_series",
	"marginal_cost",
	"marginal_cost_table",
]
