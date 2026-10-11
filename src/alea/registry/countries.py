# SPDX-License-Identifier: MIT
"""Country and power-pool registry.

Generated from the *per-country tables* in ``spec/data-completeness.md``, not
from that file's summary table. The summary contradicts the body: it reports
HIGH 5 / MEDIUM 32 / LOW 7 while its own tables hold HIGH 6 / MEDIUM 34 /
LOW 8, and it lists Equatorial Guinea under MEDIUM where the table puts it in
LOW (and twice under LOW, which is where the miscount comes from).

The tables are one row per AU member state and sum to 55. A test asserts both
the total and the per-tier counts against this module.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field


class CompletenessTier(StrEnum):
	"""How much of the data a country needs actually exists."""

	HIGH = "high"
	MEDIUM = "medium"
	LOW = "low"
	CRITICAL = "critical"


class PowerPool(StrEnum):
	"""The regional pool a country's grid is (or would be) synchronised with."""

	COMELEC = "COMELEC"
	WAPP = "WAPP"
	CAPP = "CAPP"
	EAPP = "EAPP"
	SAPP = "SAPP"
	NONE = "none"


class Country(BaseModel):
	"""One AU member state."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	iso2: str  # a registry key: never None, unlike a signal's CountryIso
	iso3: str
	name: str
	power_pool: PowerPool
	completeness: CompletenessTier
	population: int | None = Field(default=None, ge=0)
	notes: str = ""

	@property
	def needs_proxy_data(self) -> bool:
		"""Whether this country is absent from the continental datasets.

		Seven countries are missing from GEP and the OASES continental dataset
		entirely; their values are proxies and carry ``basis='proxy'``
		provenance all the way to a report (AD-6).
		"""
		return self.completeness is CompletenessTier.CRITICAL


# ISO 3166-1 alpha-3, and population (2024 UN WPP estimates, rounded to
# thousands). Population is used for demand disaggregation weighting; where it
# is a proxy for a CRITICAL country the artefact says so.
_RAW: tuple[tuple[str, str, str, PowerPool, CompletenessTier, int], ...] = (
	# -- North Africa (COMELEC) -------------------------------------------
	("DZ", "DZA", "Algeria", PowerPool.COMELEC, CompletenessTier.MEDIUM, 46_164_000),
	("EG", "EGY", "Egypt", PowerPool.COMELEC, CompletenessTier.HIGH, 114_536_000),
	("LY", "LBY", "Libya", PowerPool.COMELEC, CompletenessTier.MEDIUM, 7_381_000),
	("MR", "MRT", "Mauritania", PowerPool.COMELEC, CompletenessTier.CRITICAL, 5_169_000),
	("MA", "MAR", "Morocco", PowerPool.COMELEC, CompletenessTier.HIGH, 38_081_000),
	("TN", "TUN", "Tunisia", PowerPool.COMELEC, CompletenessTier.MEDIUM, 12_277_000),
	# -- West Africa (WAPP) -----------------------------------------------
	("BJ", "BEN", "Benin", PowerPool.WAPP, CompletenessTier.MEDIUM, 14_111_000),
	("BF", "BFA", "Burkina Faso", PowerPool.WAPP, CompletenessTier.MEDIUM, 23_025_000),
	("CV", "CPV", "Cabo Verde", PowerPool.WAPP, CompletenessTier.CRITICAL, 524_000),
	("CI", "CIV", "Cote d'Ivoire", PowerPool.WAPP, CompletenessTier.MEDIUM, 31_934_000),
	("GM", "GMB", "Gambia", PowerPool.WAPP, CompletenessTier.MEDIUM, 2_759_000),
	("GH", "GHA", "Ghana", PowerPool.WAPP, CompletenessTier.HIGH, 34_428_000),
	("GN", "GIN", "Guinea", PowerPool.WAPP, CompletenessTier.MEDIUM, 14_755_000),
	("GW", "GNB", "Guinea-Bissau", PowerPool.WAPP, CompletenessTier.LOW, 2_201_000),
	("LR", "LBR", "Liberia", PowerPool.WAPP, CompletenessTier.MEDIUM, 5_613_000),
	("ML", "MLI", "Mali", PowerPool.WAPP, CompletenessTier.MEDIUM, 24_478_000),
	("NE", "NER", "Niger", PowerPool.WAPP, CompletenessTier.MEDIUM, 27_203_000),
	("NG", "NGA", "Nigeria", PowerPool.WAPP, CompletenessTier.HIGH, 232_679_000),
	("SN", "SEN", "Senegal", PowerPool.WAPP, CompletenessTier.MEDIUM, 18_501_000),
	("SL", "SLE", "Sierra Leone", PowerPool.WAPP, CompletenessTier.MEDIUM, 8_643_000),
	("TG", "TGO", "Togo", PowerPool.WAPP, CompletenessTier.MEDIUM, 9_515_000),
	# -- Central Africa (CAPP) --------------------------------------------
	("AO", "AGO", "Angola", PowerPool.SAPP, CompletenessTier.MEDIUM, 37_885_000),
	("BI", "BDI", "Burundi", PowerPool.EAPP, CompletenessTier.CRITICAL, 14_047_000),
	("CM", "CMR", "Cameroon", PowerPool.CAPP, CompletenessTier.MEDIUM, 29_124_000),
	("CF", "CAF", "Central African Republic", PowerPool.CAPP, CompletenessTier.LOW, 5_652_000),
	("TD", "TCD", "Chad", PowerPool.CAPP, CompletenessTier.LOW, 20_299_000),
	("CG", "COG", "Congo (Republic)", PowerPool.CAPP, CompletenessTier.MEDIUM, 6_332_000),
	("CD", "COD", "Congo (DRC)", PowerPool.SAPP, CompletenessTier.MEDIUM, 109_276_000),
	("GQ", "GNQ", "Equatorial Guinea", PowerPool.CAPP, CompletenessTier.LOW, 1_892_000),
	("GA", "GAB", "Gabon", PowerPool.CAPP, CompletenessTier.MEDIUM, 2_539_000),
	("ST", "STP", "Sao Tome and Principe", PowerPool.CAPP, CompletenessTier.CRITICAL, 235_000),
	# -- East Africa (EAPP) -----------------------------------------------
	("KM", "COM", "Comoros", PowerPool.NONE, CompletenessTier.CRITICAL, 852_000),
	("DJ", "DJI", "Djibouti", PowerPool.EAPP, CompletenessTier.CRITICAL, 1_169_000),
	("ER", "ERI", "Eritrea", PowerPool.EAPP, CompletenessTier.LOW, 3_536_000),
	("ET", "ETH", "Ethiopia", PowerPool.EAPP, CompletenessTier.MEDIUM, 132_060_000),
	("KE", "KEN", "Kenya", PowerPool.EAPP, CompletenessTier.HIGH, 56_433_000),
	("MG", "MDG", "Madagascar", PowerPool.SAPP, CompletenessTier.MEDIUM, 31_965_000),
	("MW", "MWI", "Malawi", PowerPool.SAPP, CompletenessTier.MEDIUM, 21_656_000),
	("MU", "MUS", "Mauritius", PowerPool.SAPP, CompletenessTier.MEDIUM, 1_302_000),
	("MZ", "MOZ", "Mozambique", PowerPool.SAPP, CompletenessTier.MEDIUM, 34_631_000),
	("RW", "RWA", "Rwanda", PowerPool.EAPP, CompletenessTier.MEDIUM, 14_257_000),
	("SC", "SYC", "Seychelles", PowerPool.NONE, CompletenessTier.CRITICAL, 108_000),
	("SO", "SOM", "Somalia", PowerPool.EAPP, CompletenessTier.LOW, 19_010_000),
	("SS", "SSD", "South Sudan", PowerPool.EAPP, CompletenessTier.LOW, 11_943_000),
	("SD", "SDN", "Sudan", PowerPool.EAPP, CompletenessTier.MEDIUM, 50_448_000),
	("TZ", "TZA", "Tanzania", PowerPool.EAPP, CompletenessTier.MEDIUM, 68_560_000),
	("UG", "UGA", "Uganda", PowerPool.EAPP, CompletenessTier.MEDIUM, 50_015_000),
	# -- Southern Africa (SAPP) -------------------------------------------
	("BW", "BWA", "Botswana", PowerPool.SAPP, CompletenessTier.MEDIUM, 2_521_000),
	("SZ", "SWZ", "Eswatini", PowerPool.SAPP, CompletenessTier.MEDIUM, 1_243_000),
	("LS", "LSO", "Lesotho", PowerPool.SAPP, CompletenessTier.MEDIUM, 2_337_000),
	("NA", "NAM", "Namibia", PowerPool.SAPP, CompletenessTier.MEDIUM, 3_030_000),
	("ZA", "ZAF", "South Africa", PowerPool.SAPP, CompletenessTier.HIGH, 64_007_000),
	("ZM", "ZMB", "Zambia", PowerPool.SAPP, CompletenessTier.MEDIUM, 21_314_000),
	("ZW", "ZWE", "Zimbabwe", PowerPool.SAPP, CompletenessTier.MEDIUM, 16_634_000),
	# -- Other AU member states -------------------------------------------
	("EH", "ESH", "Sahrawi Arab Democratic Republic", PowerPool.NONE, CompletenessTier.LOW, 591_000),
)

_NOTES: dict[str, str] = {
	"EH": "Status disputed; AFREC and World Bank Grid coverage only.",
	"CD": "Large hydro potential; grid topology sparse outside the Copperbelt.",
	"NG": "PyPSA-Earth validated by a 2060 net-zero study.",
	"KE": "The development target: HIGH completeness and the specification's case study.",
	"ZA": "The only country with published capture-price benchmarks (COMPASS).",
	"EG": "Listed under both North and East Africa in the source tables.",
	"BI": "Listed under both Central and East Africa in the source tables.",
	"AO": "CAPP member geographically; modelled with SAPP.",
	"MG": "Island grid; no synchronous interconnection.",
	"MU": "Island grid; no synchronous interconnection.",
	"CV": "Island grid; no synchronous interconnection.",
	"ST": "Island grid; no synchronous interconnection.",
	"KM": "Island grid; no synchronous interconnection.",
	"SC": "Island grid; no synchronous interconnection.",
}

AU_MEMBER_STATE_COUNT = 55


def _build() -> dict[str, Country]:
	countries: dict[str, Country] = {}
	for iso2, iso3, name, pool, tier, population in _RAW:
		if iso2 in countries:
			raise RuntimeError(f"duplicate country {iso2} in registry source")
		countries[iso2] = Country(
			iso2=iso2,
			iso3=iso3,
			name=name,
			power_pool=pool,
			completeness=tier,
			population=population,
			notes=_NOTES.get(iso2, ""),
		)
	if len(countries) != AU_MEMBER_STATE_COUNT:
		raise RuntimeError(
			f"registry holds {len(countries)} countries, expected "
			f"{AU_MEMBER_STATE_COUNT} AU member states"
		)
	return countries


@lru_cache(maxsize=1)
def registry() -> dict[str, Country]:
	"""Every AU member state, keyed by ISO 3166-1 alpha-2."""
	return _build()


def get_country(iso2: str) -> Country:
	"""Look up one country. Raises on an unknown code.

	A silent default here would route a signal or a dataset into the wrong
	national model, which is worse than failing.
	"""
	key = iso2.upper()
	try:
		return registry()[key]
	except KeyError:
		raise KeyError(f"{iso2!r} is not a registered AU member state") from None


def by_tier(tier: CompletenessTier) -> list[Country]:
	"""Countries at a completeness tier, sorted by ISO code."""
	return sorted(
		(c for c in registry().values() if c.completeness is tier),
		key=lambda c: c.iso2,
	)


def by_power_pool(pool: PowerPool) -> list[Country]:
	"""Countries in a power pool, sorted by ISO code."""
	return sorted(
		(c for c in registry().values() if c.power_pool is pool),
		key=lambda c: c.iso2,
	)


def tier_counts() -> dict[CompletenessTier, int]:
	"""Count per tier, from the tables."""
	counts = dict.fromkeys(CompletenessTier, 0)
	for country in registry().values():
		counts[country.completeness] += 1
	return counts


def proxy_countries() -> list[Country]:
	"""The seven countries absent from the continental datasets."""
	return by_tier(CompletenessTier.CRITICAL)


__all__ = [
	"AU_MEMBER_STATE_COUNT",
	"CompletenessTier",
	"Country",
	"PowerPool",
	"by_power_pool",
	"by_tier",
	"get_country",
	"proxy_countries",
	"registry",
	"tier_counts",
]
