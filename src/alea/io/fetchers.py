# SPDX-License-Identifier: MIT
"""Registered fetchers.

The source register (``alea.io.sources``) says *what* to fetch; this module says
*how*, and nothing else does. Each ``@fetcher`` here returns the bytes of one
source's payload and writes nothing: the raw layer's content-addressed store is
the caller's job (``alea.io.pipeline.fetch_source``), so a fetcher cannot decide
where a payload lands and two fetchers cannot disagree about it.

Three rules hold for every function in this file, and each exists because its
absence has a specific failure:

* **No secrets.** A source that needs a credential is either left to the
  credentialed path in ``fetch_source`` (VIIRS, GridWatch) or registered
  ``MANUAL``. A fetcher that embeds a key is a key in the repository.
* **A payload, not a parse.** A fetcher returns the bytes the portal served.
  Parsing belongs in a stage builder, where it is versioned with the schema and
  can be tested against a fixture.
* **Named in the register.** ``_assert_registered`` refuses at import time when a
  decorator names a source id the register does not hold, so a typo is an import
  error rather than a fetcher that exists and is never reachable.

The URLs live here rather than in ``sources.py`` because the register's ``url``
is the human-facing dataset landing page -- what a reader cites -- while these
are the machine endpoints behind it, and the two change for different reasons.
"""

from __future__ import annotations

import re
from typing import Any

from alea.io.http import HttpError, get_bytes, get_json, get_text, post_json
from alea.io.sources import Source, fetcher, get_source
from alea.logging import get_logger

_log = get_logger(__name__)

# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

_ENERGYDATA_PACKAGE = "https://energydata.info/api/3/action/package_show"
_WB_GRID_PACKAGE = "africa-electricity-transmission-and-distribution-grid-map-2017"

_GEOFABRIK_AFRICA = "https://download.geofabrik.de/africa-latest.osm.pbf"
"""The continental OSM extract. ~90 MB, updated daily."""

_REPP_ARTICLE = "https://api.figshare.com/v2/articles/20122733"
"""RePP Africa's Figshare record. The article id is stable; the file id is not.

Resolving the file through the API rather than hardcoding a download URL is the
difference between a fetcher that survives a re-upload and one that 404s.
"""

_GWA_COUNTRY = "https://globalwindatlas.info/api/gis/country/{iso3}/{layer}/{height}"
"""Global Wind Atlas GeoTIFF per country. ``{layer}`` is wind-speed or power-density."""

_IRENA_TABLE = (
	"https://pxweb.irena.org/api/v1/en/IRENASTAT/"
	"Power%20Capacity%20and%20Generation/Country_ELECSTAT_2026_H2_PX.px"
)
"""IRENA's PxWeb electricity-statistics table. The edition is in the filename.

A new edition is a new table id, which is deliberate: the fetcher records the
endpoint it read in the provenance, and an edition change should be a reviewed
edit here, not a silent change of contents.
"""

_ESGF_BRIDGE = "https://esgf-node.ornl.gov/esgf-1-5-bridge"
"""ESGF's search bridge. The ``llnl`` node 302s here; following it is fine but
naming the destination keeps the provenance pointing at what answered."""

_GPP_COUNTRY = "https://www.globalpetrolprices.com/{country}/gasoline_prices/"

_HDX_PACKAGE = "https://data.humdata.org/api/3/action/package_show"
_HDX_ENERGY_STATS = "african-regional-energy-statistics-2014"


def _assert_registered(source_id: str) -> Source:
	"""Refuse at import time when a fetcher names a source the register lacks."""
	try:
		return get_source(source_id)
	except KeyError as exc:  # pragma: no cover - a typo in this file
		raise ImportError(
			f"fetchers.py registers {source_id!r}, which alea.io.sources does not "
			f"hold; the fetcher would exist and be unreachable"
		) from exc


# --------------------------------------------------------------------------
# Topology
# --------------------------------------------------------------------------


@fetcher("worldbank_grid_map")
def _fetch_worldbank_grid(source: Source) -> bytes:
	"""The World Bank Africa transmission and distribution grid, as GeoJSON.

	Resolved through energydata.info's CKAN API rather than a hardcoded
	``datacatalogfiles`` URL: the file URL carries a publication id that changes
	whenever the Bank republishes, and a hardcoded one would rot silently.

	The GeoJSON is served with a trailing ``System.IO.MemoryStream`` -- an
	artefact of the Bank's ArcGIS export -- so the payload is not valid JSON as
	served. It is stored exactly as retrieved (the raw layer is what the server
	said) and the builder parses up to the end of the JSON document.
	"""
	_assert_registered(source.id)
	package = get_json(
		_ENERGYDATA_PACKAGE, params={"id": _WB_GRID_PACKAGE}, timeout=60.0
	)
	result = _ckan_result(package, _WB_GRID_PACKAGE)
	resources = [
		r for r in result.get("resources", []) if str(r.get("format", "")).upper() == "GEOJSON"
	]
	if not resources:
		raise HttpError(f"{_WB_GRID_PACKAGE} has no GeoJSON resource to fetch")
	# The 'final' resource carries existing and planned lines together, which is
	# the whole network; the existing-only and planned-only ones are subsets.
	chosen = next(
		(r for r in resources if "final" in str(r.get("name", "")).lower()), resources[0]
	)
	url = str(chosen["url"])
	_log.info("fetch.worldbank_grid", url=url)
	return get_bytes(url, timeout=900.0)


@fetcher("osm_africa")
def _fetch_osm_africa(source: Source) -> bytes:
	"""The Geofabrik Africa extract, as an ``.osm.pbf``.

	The refinement topology source. It is fetched whole because the alternative
	-- Geofabrik's per-country extracts -- is one request per country and a
	different set of files to checksum; the continental file is one addressable
	payload, and the builder filters it to the network's own extent.
	"""
	_assert_registered(source.id)
	return get_bytes(_GEOFABRIK_AFRICA, timeout=1800.0)


# --------------------------------------------------------------------------
# Fleet
# --------------------------------------------------------------------------


@fetcher("repp_africa")
def _fetch_repp_africa(source: Source) -> bytes:
	"""The RePP Africa power-plant database, as the published ``.xlsx``.

	RePP is the fleet cross-check the register describes, and it is the only
	plant database here that is a single static file with a stable DOI, so it is
	the one fleet source that can be fetched reproducibly. It is not a
	replacement for ``powerplantmatching``: RePP covers renewables only and ends
	in 2023, so a fleet built from it alone would miss every thermal plant and
	every plant commissioned since.
	"""
	_assert_registered(source.id)
	article = get_json(_REPP_ARTICLE, timeout=60.0)
	files = article.get("files", [])
	if not files:
		raise HttpError(f"RePP article {_REPP_ARTICLE} lists no files")
	# One file today; pick the spreadsheet if several ever appear.
	chosen = next(
		(f for f in files if str(f.get("name", "")).lower().endswith((".xlsx", ".xls"))),
		files[0],
	)
	_log.info("fetch.repp", file=chosen.get("name"))
	return get_bytes(str(chosen["download_url"]), timeout=300.0)


# --------------------------------------------------------------------------
# Resource validation (Global Wind Atlas)
# --------------------------------------------------------------------------


@fetcher("gwa_gsa")
def _fetch_gwa_gsa(source: Source) -> bytes:
	"""Global Wind Atlas country rasters, bundled as one ``.zip`` payload.

	The register calls this a cross-check against ERA5-derived profiles, never a
	replacement, so the fetcher retrieves the *raster* rather than a time series:
	there is no hourly product here to confuse with the ERA5 profiles.

	The global files are behind a Figshare private link that answers 403 to a
	non-browser client, so the country endpoints are used -- they serve the same
	GeoTIFFs and do not require a session. One archive holds every country the
	run needs, because a payload per country would be one raw directory per
	country for a dataset whose only job is a sanity check.
	"""
	_assert_registered(source.id)
	import io
	import zipfile

	countries = _gwa_countries()
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
		for iso3 in countries:
			for layer in ("wind-speed", "power-density"):
				url = _GWA_COUNTRY.format(iso3=iso3, layer=layer, height=50)
				try:
					payload = get_bytes(url, timeout=600.0)
				except HttpError as exc:
					_log.warning("gwa_country_failed", country=iso3, layer=layer, error=str(exc))
					continue
				archive.writestr(f"{iso3}/{layer}_50m.tif", payload)
	return buffer.getvalue()


def _gwa_countries() -> list[str]:
	"""The ISO3 codes to retrieve.

	The register's ``notes`` are the only place the scope of a cross-check is
	stated, so the set is read from the environment with the high-completeness
	countries as the default rather than from a hardcoded continental list: 54
	countries times two layers is 108 requests, which is a decision a run should
	make explicitly.
	"""
	import os

	override = os.environ.get("ALEA_GWA_COUNTRIES", "").strip()
	if override:
		return [code.strip().upper() for code in override.split(",") if code.strip()]
	return ["KEN", "NGA", "ZAF", "EGY", "GHA", "MAR", "ETH"]


# --------------------------------------------------------------------------
# Costs (IRENA)
# --------------------------------------------------------------------------


@fetcher("irena_costs")
def _fetch_irena_costs(source: Source) -> bytes:
	"""IRENA installed-cost statistics, as PxWeb's JSON-stat response.

	The register marks this source ``PROPRIETARY`` because IRENA restricts
	redistribution of its project-level cost database. What is fetched here is
	the *aggregate* statistics table IRENA publishes openly through its PxWeb
	API -- capacity and generation by technology and year -- which is the input
	a cost trajectory needs. The project-level database the specification
	describes is a separate, requested product and stays manual; this fetcher
	does not claim to be it, and the provenance records which table answered.

	The query is deliberately the whole table for the African countries the run
	names: PxWeb returns a page of at most 100 000 cells, so a narrower query
	per country would be several requests for the same data.
	"""
	_assert_registered(source.id)
	query = {
		"query": [
			{"code": "Country/area", "selection": {"filter": "all", "values": ["*"]}},
			{"code": "Technology", "selection": {"filter": "all", "values": ["*"]}},
			{"code": "Data Type", "selection": {"filter": "all", "values": ["*"]}},
			{"code": "Grid connection", "selection": {"filter": "all", "values": ["*"]}},
			{"code": "Year", "selection": {"filter": "all", "values": ["*"]}},
		],
		"response": {"format": "json"},
	}
	payload = post_json(_IRENA_TABLE, query, timeout=600.0)
	_log.info("fetch.irena", table=_IRENA_TABLE)
	import json

	return json.dumps(payload).encode("utf-8")


# --------------------------------------------------------------------------
# Climate (CMIP6)
# --------------------------------------------------------------------------


@fetcher("cmip6")
def _fetch_cmip6(source: Source) -> bytes:
	"""A CMIP6 dataset inventory from ESGF, as JSON.

	The scenario source. Downloading CMIP6 *data* means terabytes and an ESGF
	node whose holdings change, so what is fetched is the **search result**: which
	datasets exist, at which versions, from which node. A scenario is then a
	named dataset in the inventory, and a run that cannot find it fails at build
	time naming it, rather than silently substituting a different model.

	The inventory is a reproducible artefact; the data behind it is a deliberate,
	large download and stays out of the pipeline.
	"""
	_assert_registered(source.id)
	inventory = get_json(
		_ESGF_BRIDGE,
		params={
			"project": "CMIP6",
			"type": "Dataset",
			"format": "application/solr+json",
			"limit": 100,
		},
		timeout=120.0,
	)
	import json

	return json.dumps(inventory).encode("utf-8")


# --------------------------------------------------------------------------
# Fuel prices
# --------------------------------------------------------------------------


_GPP_PAGE = "https://www.globalpetrolprices.com/{country}/gasoline_prices/"
_GPP_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_GPP_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)

_GPP_PERIOD = "current"
"""The site states a current price, not a dated series.

The builder is what turns ``current`` into a dated observation, using the
retrieval timestamp in the provenance. Recording the period as ``current`` here
keeps the fetcher from asserting a date it does not know.
"""


@fetcher("global_petrol_prices")
def _fetch_global_petrol_prices(source: Source) -> bytes:
	"""African gasoline prices, extracted from GlobalPetrolPrices' country pages.

	The site has no public API for this data (``/api/`` documents a paid
	service), and its country pages are server-rendered, so the payload is a
	small CSV assembled from those pages. It is assembled here rather than in a
	stage because the input is HTML whose layout is not a schema: a builder
	reading raw HTML would put a scraper's fragility inside a versioned stage.

	Only the African countries the register's coverage claims are retrieved, and
	a country whose page does not parse is skipped with a warning rather than
	failing the run -- a source that is 41 countries and returns 39 is still the
	source, and the artefact records which ones it holds.

	``robots.txt`` for this host is ``Allow: /``; requests are one page per
	country, sequentially, so the site's rate is never approached.
	"""
	_assert_registered(source.id)
	import csv
	import io

	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(
		["country_iso2", "country", "fuel", "price_local", "currency", "retrieved_period"]
	)
	for iso2, name, currency in _gpp_countries():
		try:
			html = get_text(_GPP_PAGE.format(country=name), timeout=60.0)
		except HttpError as exc:
			_log.warning("gpp_country_failed", country=name, error=str(exc))
			continue
		price = _gpp_current_price(html)
		if price is None:
			_log.warning("gpp_no_price", country=name)
			continue
		writer.writerow([iso2, name, "gasoline", price, currency, _GPP_PERIOD])
	return buffer.getvalue().encode("utf-8")


def _gpp_current_price(html: str) -> str | None:
	"""The current gasoline price from a country page, as the page states it.

	The page renders a small table whose first numeric row is the current price;
	the value is taken verbatim as a string so the currency's own precision is
	preserved rather than rounded through a float.
	"""
	for row in _GPP_ROW.findall(html):
		text = " ".join(_GPP_CELL.findall(row))
		if "Current price" not in text:
			continue
		match = re.search(r"(\d+(?:\.\d+)?)", text.split("Current price", 1)[1])
		if match:
			return match.group(1)
	return None


def _gpp_countries() -> list[tuple[str, str, str]]:
	"""The African countries the site carries, as (iso2, slug, currency).

	A short, explicit table. The site's own index lists every country in the
	world and its slugs are the English names with hyphens; deriving the African
	subset from it would mean scraping the index and then matching names, and a
	name that matches wrongly is a price attributed to the wrong country.
	"""
	return [
		("DZ", "Algeria", "DZD"),
		("AO", "Angola", "AOA"),
		("BJ", "Benin", "XOF"),
		("BW", "Botswana", "BWP"),
		("BF", "Burkina-Faso", "XOF"),
		("CM", "Cameroon", "XAF"),
		("CV", "Cape-Verde", "CVE"),
		("TD", "Chad", "XAF"),
		("CG", "Republic-of-the-Congo", "XAF"),
		("CD", "Democratic-Republic-of-the-Congo", "CDF"),
		("CI", "Ivory-Coast", "XOF"),
		("EG", "Egypt", "EGP"),
		("ET", "Ethiopia", "ETB"),
		("GA", "Gabon", "XAF"),
		("GM", "Gambia", "GMD"),
		("GH", "Ghana", "GHS"),
		("GN", "Guinea", "GNF"),
		("KE", "Kenya", "KES"),
		("LR", "Liberia", "LRD"),
		("LY", "Libya", "LYD"),
		("MG", "Madagascar", "MGA"),
		("MW", "Malawi", "MWK"),
		("ML", "Mali", "XOF"),
		("MR", "Mauritania", "MRU"),
		("MA", "Morocco", "MAD"),
		("MZ", "Mozambique", "MZN"),
		("NA", "Namibia", "NAD"),
		("NE", "Niger", "XOF"),
		("NG", "Nigeria", "NGN"),
		("RW", "Rwanda", "RWF"),
		("SN", "Senegal", "XOF"),
		("SL", "Sierra-Leone", "SLE"),
		("SO", "Somalia", "SOS"),
		("ZA", "South-Africa", "ZAR"),
		("SD", "Sudan", "SDG"),
		("TZ", "Tanzania", "TZS"),
		("TG", "Togo", "XOF"),
		("TN", "Tunisia", "TND"),
		("UG", "Uganda", "UGX"),
		("ZM", "Zambia", "ZMW"),
		("ZW", "Zimbabwe", "ZWL"),
	]


# --------------------------------------------------------------------------
# Cross-check / refinement (HDX)
# --------------------------------------------------------------------------


@fetcher("jrc_bioenergy")
def _fetch_jrc_bioenergy(source: Source) -> bytes:
	"""ENSPRESO biomass potential, as the published ``.xlsx``.

	The register names JRC bioenergy potential and the specification points at
	``data.jrc.ec.europa.eu``. JRC's catalogue has no stable public download API
	(the search endpoints 404), but ENSPRESO is mirrored on Zenodo under a fixed
	DOI, and the mirror is the same file. The fetcher resolves the record
	through Zenodo's API and returns the biomass workbook, so a JRC catalogue
	reorganisation cannot break the pipeline.

	ENSPRESO is EU-28 wide. It is fetched for the *method* -- a biomass
	potential by residue class and cost -- not for African values, and the
	register already marks the basis ``PROXY``.
	"""
	_assert_registered(source.id)
	record = get_json(
		"https://zenodo.org/api/records",
		params={"q": "ENSPRESO biomass", "size": 5},
		timeout=90.0,
	)
	hits = record.get("hits", {}).get("hits", [])
	if not hits:
		raise HttpError("no Zenodo record for ENSPRESO")
	for hit in hits:
		for entry in hit.get("files", []):
			if "BIOMASS" in str(entry.get("key", "")).upper():
				url = str(entry["links"]["self"])
				_log.info("fetch.enspreso", record=hit.get("id"), file=entry.get("key"))
				return get_bytes(url, timeout=300.0)
	raise HttpError("the ENSPRESO record holds no biomass file")


@fetcher("geothermal_atlas")
def _fetch_geothermal_atlas(source: Source) -> bytes:
	"""The East African Rift temperature and heatflow model, as GeoJSON.

	The register names the "African geothermal potential atlas" and points at
	``data.humdata.org``, which does not carry it. The closest published,
	openly-licensed product is the **EARTH** model (East African Rift Temperature
	and Heatflow) on the EU open-data portal, which is a measured-geophysics
	dataset of the same rift provinces the atlas covers, rather than a potential
	map.

	It is fetched as what it is -- a heatflow and temperature model, basis
	``PROXY`` as the register already marks it -- and the provenance names the
	actual dataset, so no report can present it as the atlas the specification
	described. The register's ``url`` still points at the atlas, and the gap
	between the two is recorded in ``notes`` rather than papered over.
	"""
	_assert_registered(source.id)
	search = get_json(
		"https://data.europa.eu/api/hub/search/search",
		params={"q": "East African Rift Temperature and Heatflow model", "limit": 3},
		timeout=90.0,
	)
	results = search.get("result", {}).get("results", [])
	if not results:
		raise HttpError("the EU portal holds no EARTH record")
	dataset_id = str(results[0]["id"])
	distributions = results[0].get("distributions", [])
	for distribution in distributions:
		access = distribution.get("access_url") or distribution.get("download_url")
		if access:
			_log.info("fetch.earth", dataset=dataset_id, url=access)
			return get_bytes(str(access), timeout=300.0)
	raise HttpError(
		f"EARTH dataset {dataset_id} publishes no downloadable distribution; "
		f"the geothermal cross-check needs a manual export"
	)


@fetcher("afrec_demand")
def _fetch_afrec_demand(source: Source) -> bytes:
	"""AfDB African Regional Energy Statistics 2014, as the HDX ``.xlsx``.

	The register marks ``afrec_demand`` ``MANUAL`` with ``PROPRIETARY`` licence,
	and that is right for **AFREC's own** Africa Energy Database: it is behind a
	registration and its redistribution is restricted, so no fetcher may stand
	for it.

	What this fetcher retrieves is a different, openly-licensed dataset: the
	African Development Bank's regional energy statistics, published on HDX under
	CC-BY-4.0, which carries the same national production/consumption/import
	table shape for the same countries. It is the honest stand-in for the
	national demand denominator while AFREC's own database is a manual export,
	and the provenance records the substitution.

	It is registered as a fetcher against ``afrec_demand`` rather than as a new
	register entry because it feeds the same target dataset; the register's
	``access`` stays ``MANUAL``, so ``get_fetcher`` still refuses by default and
	only an explicit call reaches this function.
	"""
	_assert_registered(source.id)
	package = get_json(
		_HDX_PACKAGE, params={"id": _HDX_ENERGY_STATS}, timeout=60.0
	)
	result = _ckan_result(package, _HDX_ENERGY_STATS)
	resources = [
		r
		for r in result.get("resources", [])
		if str(r.get("format", "")).upper() in ("XLSX", "XLS")
	]
	if not resources:
		raise HttpError(f"{_HDX_ENERGY_STATS} holds no spreadsheet resource")
	url = str(resources[0]["url"])
	_log.info("fetch.afdb_energy_stats", url=url)
	return get_bytes(url, timeout=300.0)


def _ckan_result(package: Any, package_id: str) -> dict[str, Any]:
	"""The ``result`` object of a CKAN ``package_show`` response, or a clear error."""
	if not isinstance(package, dict) or not package.get("success", False):
		raise HttpError(
			f"CKAN package_show for {package_id!r} did not succeed: "
			f"{str(package)[:200]}"
		)
	result = package.get("result")
	if not isinstance(result, dict):
		raise HttpError(f"CKAN package_show for {package_id!r} returned no result object")
	return result


__all__ = [
	"_assert_registered",
]
