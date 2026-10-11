# SPDX-License-Identifier: MIT
"""The source register.

Every datum enters through this module (02-data-pipeline §1). A layer that
downloads its own data is a layer whose inputs are unauditable.

Priority is by dependency, not by the specification's section order: the goal
is a solvable Kenya network from the fewest sources, then widen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache
from typing import Any

from alea.provenance.models import Basis, Licence


class Priority(IntEnum):
	"""Lower is fetched first. Dependency order, not section order."""

	CRITICAL_PATH = 1
	"""Enough for a first solvable Kenya network."""

	REFINEMENT = 2
	"""Replaces a crude source once the network builds."""

	EXPANSION = 3
	"""Needed for capacity expansion, not for dispatch."""

	SCENARIO = 4
	"""Scenario-only or cross-check."""


class Access(IntEnum):
	"""What a fetcher needs before it can run."""

	OPEN = 0
	"""Plain HTTP, no credentials."""

	CREDENTIALED = 1
	"""Needs a token in the environment; skips loudly without one."""

	MANUAL = 2
	"""A human runs an export once and commits the result. Never automated."""


@dataclass(frozen=True)
class Source:
	"""One registered input."""

	id: str
	name: str
	module: str
	"""The stage module that consumes it, e.g. ``planning/fleet``."""

	target: str
	"""The processed dataset it feeds."""

	priority: Priority
	access: Access
	licence: Licence
	basis: Basis
	"""How the datum should be labelled downstream."""

	url: str = ""
	credential_env: str = ""
	notes: str = ""
	unavailable: bool = False
	"""A source the pipeline cannot fetch is not a source (02-data-pipeline §1.2)."""


# The register. Order here is the specification's table order; ``Priority``
# carries the fetch order.
_SOURCES: tuple[Source, ...] = (
	Source(
		id="worldbank_grid_map",
		name="World Bank Africa transmission grid",
		module="planning/topology",
		target="topology",
		priority=Priority.CRITICAL_PATH,
		access=Access.OPEN,
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		url="https://energydata.info/dataset/africa-electricity-transmission-network",
		notes="Smallest complete topology source; enough for a first network.",
	),
	Source(
		id="powerplantmatching",
		name="powerplantmatching consolidated fleet",
		module="planning/fleet",
		target="fleet",
		priority=Priority.CRITICAL_PATH,
		access=Access.MANUAL,
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		url="https://github.com/PyPSA/powerplantmatching",
		notes=(
			"Live upstreams (OSM, GEM, IRENA, GEO, GPD) change without notice, so a "
			"per-run call is non-reproducible. Export once, commit the export, read "
			"the export. Refresh is a deliberate reviewed act."
		),
	),
	Source(
		id="afrec_demand",
		name="AFREC Africa Energy Database — national demand",
		module="planning/demand",
		target="demand_national",
		priority=Priority.CRITICAL_PATH,
		access=Access.MANUAL,
		licence=Licence.PROPRIETARY,
		basis=Basis.MEASURED,
		url="https://au-afrec.org/",
		notes="The denominator for everything downstream. Redistribution restricted.",
	),
	Source(
		id="era5_cutout",
		name="ERA5 reanalysis cutout",
		module="planning/renewables",
		target="renewable_profiles",
		priority=Priority.CRITICAL_PATH,
		access=Access.OPEN,
		licence=Licence.COPERNICUS,
		basis=Basis.MODELLED,
		url="https://cds.climate.copernicus.eu/",
		notes=(
			"Heaviest download (~tens of GB for Africa); gates solar and wind. "
			"atlite writes a .nc plus a .nc.aux sidecar and BOTH must be "
			"checksummed, or the cutout verifies and fails to open."
		),
	),
	Source(
		id="osm_africa",
		name="OpenStreetMap power infrastructure (Africa extract)",
		module="planning/topology",
		target="topology",
		priority=Priority.REFINEMENT,
		access=Access.OPEN,
		licence=Licence.ODBL,
		basis=Basis.MEASURED,
		url="https://download.geofabrik.de/africa.html",
		notes="Replaces World Bank lines once the network builds.",
	),
	Source(
		id="hydro_atlas",
		name="AfREP-Hydro atlas (Sterl et al.)",
		module="planning/hydro",
		target="hydro_profiles",
		priority=Priority.REFINEMENT,
		access=Access.MANUAL,
		licence=Licence.CC_BY_4_0,
		basis=Basis.MODELLED,
		url="https://zenodo.org/records/",
		notes=(
			"PLACEHOLDER LINK in the specification. Must be resolved to a concrete "
			"record before implementation; if it cannot be, the source is marked "
			"unavailable and the plan's dependency on it revisited. Seasonal "
			"averages; hourly requires downscaling against ERA5 runoff, and the "
			"downscaling method must be recorded."
		),
		unavailable=True,
	),
	Source(
		id="viirs_vnp46a2",
		name="VIIRS Black Marble VNP46A2 nighttime radiance",
		module="outages/viirs",
		target="outage_history",
		priority=Priority.CRITICAL_PATH,
		access=Access.CREDENTIALED,
		licence=Licence.CC0,
		basis=Basis.MEASURED,
		credential_env="EARTHDATA_TOKEN",
		url="https://ladsweb.modaps.eosdis.nasa.gov/",
		notes=(
			"Track B, independent of sources 1-6. A country-year is thousands of "
			"~100 MB granules: process streaming, store only extracted statistics "
			"plus granule checksums, never the archive."
		),
	),
	Source(
		id="gridwatch",
		name="GridWatch Ghana sensor network",
		module="outages/validate",
		target="outage_truth",
		priority=Priority.CRITICAL_PATH,
		access=Access.CREDENTIALED,
		licence=Licence.PROPRIETARY,
		basis=Basis.MEASURED,
		credential_env="GRIDWATCH_TOKEN",
		url="https://gridwatch.se/",
		notes=(
			"147 sensors, Greater Accra, 2019 to mid-2023. Without a token the "
			"validation stage skips with an explicit message and RECORDS THE SKIP "
			"in the artefact; it never reports a model as validated."
		),
	),
	Source(
		id="geothermal_atlas",
		name="African geothermal potential atlas",
		module="planning/geo",
		target="geothermal_potential",
		priority=Priority.EXPANSION,
		access=Access.OPEN,
		licence=Licence.CC_BY_4_0,
		basis=Basis.PROXY,
		url="https://data.humdata.org/",
	),
	Source(
		id="jrc_bioenergy",
		name="JRC bioenergy potential",
		module="planning/biomass",
		target="biomass_potential",
		priority=Priority.EXPANSION,
		access=Access.OPEN,
		licence=Licence.CC_BY_4_0,
		basis=Basis.PROXY,
		url="https://data.jrc.ec.europa.eu/",
	),
	Source(
		id="irena_costs",
		name="IRENA renewable cost database",
		module="planning/costs",
		target="costs",
		priority=Priority.EXPANSION,
		access=Access.MANUAL,
		licence=Licence.PROPRIETARY,
		basis=Basis.MEASURED,
		url="https://www.irena.org/Data",
	),
	Source(
		id="global_petrol_prices",
		name="Global Petrol Prices fuel prices",
		module="market/fuel",
		target="fuel_prices",
		priority=Priority.EXPANSION,
		access=Access.OPEN,
		licence=Licence.UNKNOWN,
		basis=Basis.MEASURED,
		url="https://www.globalpetrolprices.com/",
		notes="Feeds marginal cost, so its date matters: prices are a time series.",
	),
	Source(
		id="cmip6",
		name="CMIP6 climate projections",
		module="planning/climate",
		target="climate_scenarios",
		priority=Priority.SCENARIO,
		access=Access.OPEN,
		licence=Licence.COPERNICUS,
		basis=Basis.FORECAST,
		url="https://esgf-node.llnl.gov/projects/cmip6/",
	),
	Source(
		id="gwa_gsa",
		name="Global Wind Atlas / Global Solar Atlas",
		module="planning/renewables",
		target="resource_validation",
		priority=Priority.SCENARIO,
		access=Access.OPEN,
		licence=Licence.CC_BY_4_0,
		basis=Basis.MODELLED,
		url="https://globalwindatlas.info/",
		notes="Cross-check against ERA5-derived profiles, never a replacement.",
	),
	Source(
		id="repp_africa",
		name="Renewable Energy Performance Platform plant list",
		module="planning/fleet",
		target="fleet",
		priority=Priority.SCENARIO,
		access=Access.OPEN,
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		url="https://repp.africa/",
		notes="Validates powerplantmatching, does not replace it.",
	),
)


@lru_cache(maxsize=1)
def sources() -> dict[str, Source]:
	"""Every registered source, keyed by id."""
	return {source.id: source for source in _SOURCES}


def get_source(source_id: str) -> Source:
	"""Look up a source. Raises on an unknown id.

	A silent default here means a stage reads whichever source happens to be
	first, which is worse than failing.
	"""
	try:
		return sources()[source_id]
	except KeyError:
		known = ", ".join(sorted(sources()))
		raise KeyError(f"unknown source {source_id!r}; registered: {known}") from None


def by_priority(priority: Priority) -> list[Source]:
	"""Sources at a priority, in register order."""
	return [s for s in _SOURCES if s.priority is priority]


def fetchable() -> list[Source]:
	"""Sources the pipeline can actually retrieve, in fetch order."""
	return sorted(
		(s for s in _SOURCES if not s.unavailable),
		key=lambda s: (s.priority, s.id),
	)


def register() -> list[dict[str, Any]]:
	"""The register as plain data, for export and for the docs build."""
	return [
		{
			**{
				field: getattr(source, field)
				for field in (
					"id",
					"name",
					"module",
					"target",
					"url",
					"credential_env",
					"notes",
					"unavailable",
				)
			},
			"priority": int(source.priority),
			"priority_name": source.priority.name,
			"access": source.access.name,
			"licence": source.licence.value,
			"basis": source.basis.value,
		}
		for source in _SOURCES
	]


Fetcher = Callable[[Source], bytes]
"""A fetcher returns the raw payload. It never writes to the lake itself."""

_FETCHERS: dict[str, Fetcher] = {}


def fetcher(source_id: str) -> Callable[[Fetcher], Fetcher]:
	"""Register a fetcher for a source id."""

	def decorate(function: Fetcher) -> Fetcher:
		_FETCHERS[source_id] = function
		return function

	return decorate


def get_fetcher(source_id: str) -> Fetcher:
	"""The registered fetcher for a source. Raises when none is registered."""
	source = get_source(source_id)
	if source.unavailable:
		raise KeyError(
			f"{source_id!r} is registered as unavailable: {source.notes or 'no note'}"
		)
	if source.access is Access.MANUAL:
		raise KeyError(
			f"{source_id!r} is a manual export and has no automated fetcher; "
			f"run the export once and commit the result"
		)
	try:
		return _FETCHERS[source_id]
	except KeyError:
		raise KeyError(f"no fetcher registered for {source_id!r}") from None


def registered_fetchers() -> list[str]:
	"""Source ids with a fetcher. The register and this list may differ."""
	return sorted(_FETCHERS)


__all__ = [
	"Access",
	"Fetcher",
	"Priority",
	"Source",
	"by_priority",
	"fetchable",
	"get_fetcher",
	"get_source",
	"register",
	"registered_fetchers",
	"sources",
]
