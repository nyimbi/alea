# SPDX-License-Identifier: MIT
"""PPA benchmark curves.

A PPA curve gives a price for a given tenor, technology, and country. Three
adjustments are applied, and each is recorded in the artefact (06-layer3 §6):

* **Tenor** — the capture price over the contract term, not year one. A ten-year
  PPA is priced on the ten-year average, and using year one is the most common
  way a benchmark flatters a project.
* **Currency risk** — the local-currency vs USD spread, recorded as
  ``fx_basis_pct`` with its source.
* **Counterparty risk** — the sovereign/utility credit spread, recorded as
  ``credit_spread_pct`` with its source.

**Currency is the trap.** Every local-currency PPA price records the FX rate
*and the rate's date*. The project's own history includes a document that stated
a target in KES at one implied rate and converted USD at another, a 10%
self-contradiction no lint could see because each number was internally
consistent with its own line. ``FxRate`` makes the rate and its date
non-optional.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import numpy as np

from alea.logging import get_logger
from alea.market.views import FxRate, PpaBenchmark
from alea.provenance.models import Basis, Licence, Provenance

if TYPE_CHECKING:  # pragma: no cover - the annotation only
	from alea.config.models import CostsConfig

logger = get_logger(__name__)


def fx_rate_from_config(
	costs: CostsConfig,
	currency: str = "KES",
) -> FxRate:
	"""The configured USD rate for a currency, with its date.

	Only the currencies ``CostsConfig`` knows (EUR, KES) can be built from
	config. Any other currency needs a rate supplied directly, because a rate
	invented at the call site is the defect ``FxRate`` exists to prevent.
	"""
	assert currency, "a currency is required"
	key = currency.lower()
	if key == "kes":
		if costs.kes_usd is None or costs.kes_usd_date is None:
			raise ValueError(
				"KES/USD is not configured; set costs.kes_usd and costs.kes_usd_date "
				"(a rate without its date is not a rate)"
			)
		return FxRate(
			local_per_usd=costs.kes_usd,
			rate_date=costs.kes_usd_date,
			source="config.costs.kes_usd",
		)
	if key == "eur":
		if costs.eur_usd is None or costs.eur_usd_date is None:
			raise ValueError("EUR/USD is not configured; set costs.eur_usd and costs.eur_usd_date")
		# eur_usd is USD per EUR, so EUR per USD is its reciprocal.
		return FxRate(
			local_per_usd=1.0 / costs.eur_usd,
			rate_date=costs.eur_usd_date,
			source="config.costs.eur_usd",
		)
	raise ValueError(
		f"no configured rate for {currency}; supply an FxRate directly rather "
		f"than inventing one at the call site"
	)


def to_local(price_usd_per_mwh: float, fx: FxRate) -> float:
	"""Convert a USD/MWh price to local currency, using the recorded rate."""
	assert fx.local_per_usd > 0.0, "FX rate must be positive"
	return price_usd_per_mwh * fx.local_per_usd


def tenor_capture_price(
	capture_by_year: Mapping[int, float],
	*,
	tenor_years: int,
	start_year: int | None = None,
) -> float:
	"""The capture price over the contract term.

	Years whose capture price is undefined (NaN — the technology generated
	nothing) are dropped from the mean rather than counted as zero. If every
	year in the term is undefined, the tenor price is NaN: a PPA cannot be
	priced on no generation.
	"""
	assert tenor_years > 0, "tenor must be positive"
	years = sorted(capture_by_year)
	assert years, "no capture years to price a PPA from"
	first = start_year if start_year is not None else years[0]
	window = [capture_by_year[y] for y in years if first <= y < first + tenor_years]
	assert window, f"no capture prices in the {tenor_years}-year window from {first}"
	values = np.asarray(window, dtype=np.float64)
	finite = values[np.isfinite(values)]
	if finite.size == 0:
		return float("nan")
	return float(finite.mean())


def ppa_benchmark(
	country_iso: str,
	carrier: str,
	tenor_years: int,
	base_capture_price_usd_per_mwh: float,
	*,
	credit_spread_pct: float = 0.0,
	credit_source: str = "",
	fx_basis_pct: float = 0.0,
	fx_basis_source: str = "",
	fx: FxRate | None = None,
) -> PpaBenchmark:
	"""A PPA benchmark price for one technology, country, and tenor.

	The price is the capture price marked up by the counterparty credit spread
	and, when a local-currency price is wanted, by the FX basis. Both markups are
	fractions (0.02 = 2%). The USD price never carries the FX basis: the basis
	*is* the compensation for pricing in local currency.
	"""
	assert tenor_years > 0, "tenor must be positive"
	assert np.isfinite(base_capture_price_usd_per_mwh), "base capture price must be finite"

	price_usd = base_capture_price_usd_per_mwh * (1.0 + credit_spread_pct)
	price_local = to_local(price_usd, fx) * (1.0 + fx_basis_pct) if fx is not None else None

	provenance = Provenance(
		source_id=f"market.ppa.{carrier}",
		basis=Basis.MODELLED,
		licence=Licence.UNKNOWN,
		uncertainty=0.0,
		notes=(
			f"PPA benchmark: tenor {tenor_years}y, credit spread "
			f"{credit_spread_pct:+.4f} ({credit_source or 'none'}), FX basis "
			f"{fx_basis_pct:+.4f} ({fx_basis_source or 'none'})"
		),
	)

	benchmark = PpaBenchmark(
		country_iso=country_iso,
		carrier=carrier,
		tenor_years=tenor_years,
		base_capture_price_usd_per_mwh=base_capture_price_usd_per_mwh,
		credit_spread_pct=credit_spread_pct,
		credit_source=credit_source,
		fx_basis_pct=fx_basis_pct,
		fx_basis_source=fx_basis_source,
		fx=fx,
		price_usd_per_mwh=price_usd,
		price_local_per_mwh=price_local,
		provenance=provenance,
	)
	logger.info(
		"ppa_benchmark",
		country=country_iso,
		carrier=carrier,
		tenor_years=tenor_years,
		price_usd_per_mwh=round(price_usd, 2),
		price_local_per_mwh=None if price_local is None else round(price_local, 2),
		fx_rate_date=fx.rate_date if fx is not None else None,
	)
	return benchmark


def ppa_curve(
	country_iso: str,
	carrier: str,
	capture_by_year: Mapping[int, float],
	tenors: list[int],
	*,
	start_year: int | None = None,
	credit_spread_pct: float = 0.0,
	credit_source: str = "",
	fx_basis_pct: float = 0.0,
	fx_basis_source: str = "",
	fx: FxRate | None = None,
) -> dict[int, PpaBenchmark]:
	"""A benchmark per tenor, sharing one FX rate and its date.

	Sharing the rate across the curve is deliberate: a curve whose tenors were
	each converted at a different rate is not a curve, it is several unrelated
	numbers that happen to share an axis.
	"""
	assert tenors, "a PPA curve needs at least one tenor"
	curve: dict[int, PpaBenchmark] = {}
	for tenor in sorted(set(tenors)):
		base = tenor_capture_price(capture_by_year, tenor_years=tenor, start_year=start_year)
		if not np.isfinite(base):
			logger.warning("ppa_tenor_undefined", carrier=carrier, tenor_years=tenor)
			continue
		curve[tenor] = ppa_benchmark(
			country_iso,
			carrier,
			tenor,
			base,
			credit_spread_pct=credit_spread_pct,
			credit_source=credit_source,
			fx_basis_pct=fx_basis_pct,
			fx_basis_source=fx_basis_source,
			fx=fx,
		)
	return curve


__all__ = [
	"fx_rate_from_config",
	"ppa_benchmark",
	"ppa_curve",
	"tenor_capture_price",
	"to_local",
]
