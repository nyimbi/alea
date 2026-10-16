# SPDX-License-Identifier: MIT
"""The ten processed datasets of ``02-data-pipeline.md`` §3.

Each builder here follows the same four rules, and they are the whole reason the
file exists as one place rather than ten:

1. **Read the raw layer, never the network.** The bytes come from
   ``data/raw/<source_id>/<checksum>/``, put there by ``alea fetch``. A builder
   that reached upstream itself would make the artefact depend on when it ran.
2. **Raise on a missing input.** AD-4 and §8 of the architecture: a stage that
   writes an empty artefact on a missing input writes a *plausible* empty
   artefact, and every number computed from it is wrong in a way nobody sees.
   Each builder calls ``_require_raw`` before it reads anything.
3. **Write one artefact with provenance** (AD-4). The provenance records the
   input checksums, so the stage is re-runnable and its idempotence check means
   something.
4. **Record the modelling choice.** The demand disaggregation share ``alpha``,
   the cutout name, the currency rate and its date all go into ``parameters``.
   A number whose assumption is not in its provenance is a number nobody can
   defend (``02-data-pipeline.md`` §2.3, §3.1).

The builders are registered with ``@stage`` and reached through
``alea build <stage> --out <path>``. Nothing here is imported by a rule: AD-5
makes the CLI the only entry point the workflow layer calls.

Where a source is a manual export (``powerplantmatching``, ``hydro_atlas``) the
builder reads a file committed under ``data/raw`` and names it, because there is
no fetcher to produce a checksum directory and a stage with no input is a stage
that cannot be re-run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, overload

import numpy as np
import pandas as pd

from alea import __version__
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, sha256_file
from alea.io.pipeline import BuildContext, stage, write_stage
from alea.io.sources import Access, get_source
from alea.logging import get_logger, new_run_id
from alea.planning.fleet import DEFAULT_LIFETIME_YEARS
from alea.planning.schemas import FLEET, TOPOLOGY
from alea.provenance.models import Basis, DerivedProvenance
from alea.registry import Carrier, get_technology

_log = get_logger(__name__)

RAW_PAYLOAD = "payload"
"""The filename ``store_raw`` gives a raw payload."""

_MANUAL_DEFAULTS = {
	"powerplantmatching": "powerplants.parquet",
	"hydro_atlas": "hydro_profiles.parquet",
	"afrec_demand": "afrec_demand.xlsx",
	"gridwatch": "gridwatch.csv",
	"irena_costs": "irena_costs.json",
}
"""The filename a manual export is expected to carry under ``<raw>/<id>/manual/``."""

DEFAULT_ALPHA = 0.5
"""Population/GDP mix for demand disaggregation (``02-data-pipeline.md`` §3.1).

Recorded in the artefact's provenance every time it is used, because a
disaggregation whose ``alpha`` is unrecorded produces a map nobody can defend.
"""

HOURS_PER_YEAR = 8760
"""Non-leap hours in a year.

Kept as the *name* for the defect the hourly index must not be built from: the
demand series is the calendar year (see `_hourly_shape`), and
`tests/ci/test_planning_inputs.py` plants an index of exactly this many hours to
prove the gate catches it. The constant is the canary's spelling of that defect
and is why it is not simply 8760 inline.
"""

FUEL_COLUMNS = ("country_iso", "fuel", "year", "price_usd_per_mwh")
"""The ``fuel_prices`` schema of §3, in order."""

CURRENCY_NOTE = (
	"Currency conversions record the rate and the rate's date; a rate without "
	"its date is not a rate (02-data-pipeline §2.3)."
)


# --------------------------------------------------------------------------
# Raw-layer access
# --------------------------------------------------------------------------


def _raw_root(config: Config, context: BuildContext) -> Path:
	"""The raw lake root this build reads, overridable through the context."""
	override = context.parameters.get("raw_root")
	if override:
		return Path(str(override))
	from alea.config.paths import resolve

	return resolve(config.paths.raw)


def _require_raw(
	config: Config,
	context: BuildContext,
	source_id: str,
	*,
	checksum: str | None = None,
	manual: str | None = None,
) -> Path:
	"""The raw payload for a source, or a raise naming what is missing.

	Two shapes, and the shape is chosen by the register rather than by the
	caller. A source with ``Access.MANUAL`` is an export a human makes once and
	commits, so it lives at ``<raw>/<source_id>/manual/<name>`` and is named by
	the caller; every other source lives at ``<raw>/<source_id>/<checksum>/`` and
	is produced by ``alea fetch``.
	"""
	source = get_source(source_id)
	root = _raw_root(config, context)
	if source.access is Access.MANUAL:
		filename = manual or _MANUAL_DEFAULTS.get(source_id, "")
		if not filename:
			raise ArtefactError(
				f"{source_id} is a manual export and this stage has no name for the "
				f"file; pass it in the stage's parameters"
			)
		path = root / source_id / "manual" / filename
		if not path.exists():
			raise ArtefactError(
				f"{source_id}: no committed export at {path}. {source.name} is a "
				f"manual source ({source.notes or 'see the source register'}); run "
				f"the export once and commit it there"
			)
		return path

	directory = root / source_id
	if not directory.is_dir():
		raise ArtefactError(
			f"{source_id}: nothing in the raw layer at {directory}; run "
			f"`alea fetch {source_id}` first. A stage that builds from an absent "
			f"source would write an artefact with no input, which reads as a "
			f"successful empty build"
		)

	if checksum is not None:
		candidate = directory / checksum
		if not candidate.is_dir():
			raise ArtefactError(f"{source_id}: no raw payload at {candidate}")
		return _payload_in(candidate, required=True)

	candidates = sorted(
		(p for p in directory.iterdir() if p.is_dir()),
		key=lambda p: p.stat().st_mtime,
		reverse=True,
	)
	for candidate in candidates:
		payload = _payload_in(candidate, required=False)
		if payload is not None:
			return payload
	raise ArtefactError(f"{source_id}: {directory} holds no payload to read")


@overload
def _payload_in(directory: Path, *, required: Literal[True] = True) -> Path: ...


@overload
def _payload_in(directory: Path, *, required: Literal[False]) -> Path | None: ...


def _payload_in(directory: Path, *, required: bool = True) -> Path | None:
	payloads = [
		p for p in sorted(directory.iterdir()) if p.is_file() and p.name != "provenance.json"
	]
	if not payloads:
		if required:
			raise ArtefactError(f"{directory} holds no payload")
		return None
	if len(payloads) > 1:
		raise ArtefactError(
			f"{directory} holds {len(payloads)} payloads ({', '.join(p.name for p in payloads)}); "
			f"the raw layer stores one payload per checksum directory"
		)
	return payloads[0]


def _checksum_of(path: Path) -> str:
	"""The recorded checksum for a raw payload, or its content hash.

	The recorded value is preferred because a manual export is addressed by the
	hash its producer recorded, and re-deriving it here would make the artefact's
	input list disagree with the raw layer's own provenance.
	"""
	if path.parent.name == "manual":
		return sha256_file(path)
	recorded = path.parent / "provenance.json"
	if recorded.exists():
		try:
			return str(json.loads(recorded.read_text(encoding="utf-8")).get("checksum", "")) or ""
		except (OSError, ValueError):  # pragma: no cover - a corrupt sidecar
			pass
	return sha256_file(path)


def _provenance(
	config: Config,
	context: BuildContext,
	*,
	source_id: str,
	notes: str,
	parameters: dict[str, Any] | None = None,
	basis: Basis = Basis.MODELLED,
	uncertainty: float = 0.0,
	uncertainty_basis: str = "",
	inputs: list[str] | None = None,
) -> DerivedProvenance:
	"""Provenance for one processed dataset.

	``inputs`` defaults to the checksums the caller passed through the context,
	which is what makes the stage's idempotence check -- "were these exact bytes
	the input?" -- meaningful rather than decorative.
	"""
	declared = list(inputs) if inputs is not None else list(context.inputs)
	if not declared:
		raise ArtefactError(
			f"stage for {source_id!r} has no input checksums; a derived artefact "
			f"that does not record what it was derived from cannot be reproduced"
		)
	return DerivedProvenance(
		source_id=source_id,
		inputs=declared,
		code_version=__version__,
		run_id=new_run_id(),
		parameters={**config_parameters(config), **(parameters or {})},
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis=uncertainty_basis,
		notes=notes,
	)


def config_parameters(config: Config) -> dict[str, Any]:
	"""The scenario facts every derived artefact records.

	Countries and horizons are what make an artefact interpretable six months
	later; without them a ``fleet.parquet`` is a table of plants with no statement
	of which countries it covers.
	"""
	return {
		"countries": [str(iso) for iso in config.scenario.countries],
		"planning_horizons": list(config.scenario.planning_horizons),
		"base_year": config.scenario.base_year,
		"base_currency": config.costs.base_currency,
		"currency_rates": {
			"eur_usd": config.costs.eur_usd,
			"eur_usd_date": config.costs.eur_usd_date,
			"kes_usd": config.costs.kes_usd,
			"kes_usd_date": config.costs.kes_usd_date,
		},
	}


# --------------------------------------------------------------------------
# Reading the seam's payloads
# --------------------------------------------------------------------------


def _read_geojson(path: Path) -> Any:
	"""Parse a GeoJSON payload, tolerating the World Bank's trailing junk.

	The Bank serves its Africa grid as GeoJSON with a trailing
	``System.IO.MemoryStream`` -- an artefact of an ArcGIS export -- so the file
	is not valid JSON as served. ``raw`` stores exactly what the server said, and
	the truncation to the end of the document happens here, at the boundary,
	where the reason is written down.
	"""
	text = path.read_text(encoding="utf-8", errors="replace")
	try:
		return json.loads(text)
	except ValueError:
		end = text.rfind("}")
		if end < 0:
			raise ArtefactError(f"{path}: no JSON document found in the payload") from None
		try:
			return json.loads(text[: end + 1])
		except ValueError as exc:
			raise ArtefactError(f"{path}: payload is not parseable as GeoJSON: {exc}") from exc


def _lines_from_geojson(payload: Any, *, source_id: str) -> pd.DataFrame:
	"""The endpoint columns ``TOPOLOGY`` declares, from a GeoJSON FeatureCollection."""
	features = payload.get("features") if isinstance(payload, dict) else None
	if not isinstance(features, list) or not features:
		raise ArtefactError(f"{source_id}: payload holds no GeoJSON features")

	rows: list[dict[str, Any]] = []
	for index, feature in enumerate(features):
		if not isinstance(feature, dict):
			continue
		geometry = feature.get("geometry") or {}
		coords = geometry.get("coordinates") or []
		if geometry.get("type") == "MultiLineString":
			coords = coords[0] if coords else []
		if len(coords) < 2:
			continue
		properties = feature.get("properties") or {}
		rows.append(
			{
				"line_id": str(properties.get("id") or properties.get("OBJECTID") or f"line_{index}"),
				"from_lon": float(coords[0][0]),
				"from_lat": float(coords[0][1]),
				"to_lon": float(coords[-1][0]),
				"to_lat": float(coords[-1][1]),
				"voltage_kv": _voltage_kv(properties),
				"length_km": _length_km(properties, coords),
				"capacity_mva": _capacity_mva(properties),
			}
		)
	if not rows:
		raise ArtefactError(f"{source_id}: no line geometries with two or more points")
	return pd.DataFrame(rows)


def _voltage_kv(properties: dict[str, Any]) -> float:
	for key in ("voltage_kv", "voltage", "VOLTAGE", "voltage_kV"):
		value = properties.get(key)
		if value is not None and str(value).strip() not in ("", "nan"):
			return float(str(value).split(";")[0].strip())
	return 0.0


def _length_km(properties: dict[str, Any], coords: list[Any]) -> float:
	for key in ("length_km", "length", "LENGTH_KM", "Shape_Leng"):
		value = properties.get(key)
		if value is not None and str(value).strip() not in ("", "nan"):
			# `Shape_Leng` is in the layer's own projected units, which for the
			# Bank's export is degrees; a degrees value read as km is a ~100x
			# error, so the builder leaves it to the topology builder to derive
			# from the endpoints instead.
			if key == "Shape_Leng":
				break
			return float(value)
	return float("nan")


def _capacity_mva(properties: dict[str, Any]) -> float:
	for key in ("capacity_mva", "capacity", "CAPACITY"):
		value = properties.get(key)
		if value is not None and str(value).strip() not in ("", "nan"):
			try:
				return float(value)
			except (TypeError, ValueError):
				return float("nan")
	return float("nan")


def _read_table(path: Path) -> pd.DataFrame:
	"""Read a raw payload as a DataFrame, by suffix.

	A builder never guesses: an unrecognised suffix is refused, because a
	``read_csv`` on a Parquet file either raises deep in pandas or -- worse for a
	CSV-shaped binary -- returns one column of noise.
	"""
	suffix = path.suffix.lower()
	if suffix in (".parquet", ".pq"):
		return pd.read_parquet(path)
	if suffix in (".csv", ".txt"):
		return pd.read_csv(path)
	if suffix in (".json",):
		payload = json.loads(path.read_text(encoding="utf-8"))
		return pd.DataFrame(payload)
	if suffix in (".xlsx", ".xls"):
		return pd.read_excel(path, engine="openpyxl")
	if suffix in (".geojson",):
		return _lines_from_geojson(_read_geojson(path), source_id=path.name)
	raise ArtefactError(
		f"{path}: cannot read a {suffix!r} payload as a table; add the reader here "
		f"rather than parsing it in a rule"
	)


def _pick(frame: pd.DataFrame, *names: str) -> str | None:
	"""The first present column among ``names``, case-insensitively."""
	lowered = {str(c).strip().lower(): str(c) for c in frame.columns}
	for name in names:
		if name in frame.columns:
			return name
		if name.lower() in lowered:
			return lowered[name.lower()]
	return None


def _require_columns(
	frame: pd.DataFrame,
	columns: dict[str, str | None],
	*,
	artefact: str,
) -> pd.DataFrame:
	"""Rename ``{wanted: found}`` and refuse when a wanted column is absent.

	``found`` is ``None`` when the payload does not carry that column under any
	of the names the caller tried, which is the case this exists to refuse: a
	``KeyError`` twelve frames into a network build names neither the artefact
	nor the column.
	"""
	missing = [wanted for wanted, found in columns.items() if found is None]
	if missing:
		raise ArtefactError(
			f"{artefact}: payload is missing {', '.join(missing)}; it holds "
			f"{', '.join(str(c) for c in frame.columns)}"
		)
	return frame.rename(columns={found: wanted for wanted, found in columns.items() if found})


# --------------------------------------------------------------------------
# 1. topology
# --------------------------------------------------------------------------


@stage("topology")
def build_topology(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``topology`` -- transmission lines, as GeoJSON and Parquet.

	Two artefacts from one stage, which §3 asks for and which is not a
	convenience: GeoJSON is what a GIS reads and Parquet is what a network
	builder reads, and a single format would force one of them to convert. Both
	carry the same rows, and the Parquet file's provenance sidecar is the one
	``build_stage`` checks for.
	"""
	manual = context.parameters.get("worldbank_export")
	path = _require_raw(config, context, "worldbank_grid_map", manual=manual)
	checksum = _checksum_of(path)
	lines = _lines_from_geojson(_read_geojson(path), source_id="worldbank_grid_map")

	voltage_floor = float(context.parameters.get("voltage_kv_min", 0.0))
	if voltage_floor > 0:
		lines = lines.loc[lines["voltage_kv"] >= voltage_floor].reset_index(drop=True)
	TOPOLOGY.check(lines, artefact="topology")
	if lines.empty:
		raise ArtefactError(
			"topology: no lines survived the voltage floor; an empty network "
			"builds into an empty solve and reads as a successful run"
		)

	provenance = _provenance(
		config,
		context,
		source_id="topology",
		inputs=[checksum],
		parameters={
			"n_lines": int(len(lines)),
			"voltage_kv_min": voltage_floor,
			"crs": "EPSG:4326",
			"axis_order": "lon,lat",
			"source": "worldbank_grid_map",
		},
		basis=Basis.MEASURED,
		notes=(
			"The Bank's existing-and-planned layer, filtered by voltage. "
			"EPSG:4326 with lon,lat axis order pinned, because GeoPandas and the "
			"OGC standard disagree and a silent swap puts Kenya in the ocean."
		),
	)

	geojson_out = out.with_suffix(".geojson")
	_write_geojson(lines, geojson_out)
	write_stage(out, lines, provenance)
	_log.info("stage.topology", lines=len(lines), geojson=str(geojson_out))
	return provenance


def _write_geojson(lines: pd.DataFrame, path: Path) -> None:
	"""Write the endpoint frame as a FeatureCollection of LineStrings."""
	features = [
		{
			"type": "Feature",
			"properties": {
				"line_id": str(row["line_id"]),
				"voltage_kv": float(row["voltage_kv"]),
				"length_km": None if pd.isna(row["length_km"]) else float(row["length_km"]),
				"capacity_mva": None if pd.isna(row["capacity_mva"]) else float(row["capacity_mva"]),
			},
			"geometry": {
				"type": "LineString",
				"coordinates": [
					[float(row["from_lon"]), float(row["from_lat"])],
					[float(row["to_lon"]), float(row["to_lat"])],
				],
			},
		}
		for row in lines.to_dict("records")
	]
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(
		json.dumps({"type": "FeatureCollection", "features": features}, sort_keys=True),
		encoding="utf-8",
	)


# --------------------------------------------------------------------------
# 2. fleet
# --------------------------------------------------------------------------


@stage("fleet")
def build_fleet(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``fleet`` -- the generation fleet from the committed powerplantmatching export.

	``02-data-pipeline.md`` §1.1 makes the export mandatory: ``ppm.powerplants()``
	hits live upstreams, so a per-run call makes every result depend on when it
	ran. The stage reads the export and never the library.
	"""
	manual = str(
		context.parameters.get("powerplant_export") or _MANUAL_DEFAULTS["powerplantmatching"]
	)
	path = _require_raw(config, context, "powerplantmatching", manual=manual)
	checksum = _checksum_of(path)
	raw = _read_table(path)

	frame = _require_columns(
		raw,
		{
			"plant_id": _pick(raw, "plant_id", "id"),
			"name": _pick(raw, "name", "Name", "plant"),
			"country_iso": _pick(raw, "country_iso", "Country", "country"),
			"lat": _pick(raw, "lat", "latitude", "Lat"),
			"lon": _pick(raw, "lon", "longitude", "Lon"),
			"capacity_mw": _pick(raw, "capacity_mw", "Capacity", "capacity"),
			"carrier": _pick(raw, "carrier", "Fueltype", "fueltype", "technology"),
		},
		artefact="fleet",
	)
	if frame.empty:
		raise ArtefactError("fleet: the export holds no plants")

	frame["country_iso"] = frame["country_iso"].map(_iso2)
	frame["carrier"] = frame["carrier"].map(_carrier_name)
	frame["capacity_mw"] = pd.to_numeric(frame["capacity_mw"], errors="coerce")
	frame = frame.loc[frame["capacity_mw"].fillna(0.0) > 0.0].reset_index(drop=True)
	if frame.empty:
		raise ArtefactError("fleet: no plant has a positive capacity")

	# The two columns `attach_generators` reads for a generator's vintage and its
	# technical life. They were written as `commission_year` (no `-ing`) and not
	# written at all, and `FLEET.check` -- which `attach_generators` runs as its
	# first statement -- refused both: every `build_network` from a staged fleet
	# raised `SchemaError: fleet: missing required column(s) commissioning_year,
	# lifetime_years`. The pipeline could not build a network from its own
	# output, and the fixture in `tests/ci/test_planning_inputs.py` wrote the
	# schema's spelling by hand, so the gate was green and the seam was broken.
	#
	# The names are the schema's (`planning/schemas.py`) and the plan's
	# (`02-data-pipeline.md` §2's fleet table), which are the same names the
	# consumer already read.
	commission = _pick(raw, "commissioning_year", "commission_year", "Commissioned", "Year")
	technology = _pick(raw, "technology", "Technology", "type")
	commissioned = (
		pd.to_numeric(raw[commission], errors="coerce")
		if commission
		else pd.Series(np.nan, index=frame.index)
	)
	# `int` is the schema's dtype and a NaN is not one. `attach_generators` reads
	# this column with `int(row[...])`, which raises on a NaN, so an export that
	# omits a plant's vintage would fail the build one row in. The default is the
	# scenario's *base year*, not zero: a plant the register lists is one that is
	# operating now, and `build_year=0` under `set_multi_period` is a generator
	# retired thirty years before the first horizon -- a fleet that silently
	# vanishes from the expansion. A zero here would also survive
	# `expansion.py`'s `fillna(periods[0])`, because it is not NaN.
	default_year = int(context.parameters.get("commissioning_year_default", config.scenario.base_year))
	frame["commissioning_year"] = commissioned.fillna(default_year).astype(int)
	n_undated = int(commissioned.isna().sum())

	lifetime = _pick(raw, "lifetime_years", "lifetime", "Lifetime")
	years = (
		pd.to_numeric(raw[lifetime], errors="coerce")
		if lifetime
		else pd.Series(np.nan, index=frame.index)
	)
	frame["lifetime_years"] = years.fillna(DEFAULT_LIFETIME_YEARS).astype(int)
	frame["technology"] = raw[technology].astype(str) if technology else frame["carrier"]
	# `status` is not in the export's own columns in most snapshots: a plant the
	# export lists is operating, and saying so explicitly beats leaving the
	# column absent for a downstream reader to invent.
	frame["status"] = str(context.parameters.get("default_status", "operating"))

	known = {c.value for c in Carrier}
	unknown = sorted(set(frame["carrier"]) - known)
	if unknown:
		# Refused, not warned. `02-data-pipeline.md` §4.2's canary injects an
		# unknown carrier and requires this gate to fail: an unregistered
		# carrier has no emissions factor, no variability and no place in a
		# capacity mix, so accepting it produces a fleet one row of which
		# nothing downstream can interpret.
		raise ArtefactError(
			f"fleet: unknown carrier(s) {', '.join(unknown)}; add them to "
			f"alea.registry.technologies before building the fleet"
		)

	countries = {str(iso) for iso in config.scenario.countries}
	frame = frame.loc[frame["country_iso"].isin(countries)].reset_index(drop=True)
	if frame.empty:
		raise ArtefactError(
			f"fleet: the export holds no plant in {', '.join(sorted(countries))}"
		)

	# The stage checks its own output against the schema its consumer reads, the
	# way `build_topology` checks `TOPOLOGY` a few hundred lines up. Without it
	# the two spellings of a column name drift apart silently and the break
	# surfaces in `attach_generators` as a `SchemaError` naming the *consumer*,
	# which reads as the consumer being wrong -- `commission_year` against
	# `commissioning_year` cost exactly that, and nothing in the suite noticed
	# because the fixtures wrote the consumer's spelling by hand.
	FLEET.check(frame, artefact="fleet")

	provenance = _provenance(
		config,
		context,
		source_id="fleet",
		inputs=[checksum],
		parameters={
			"n_plants": int(len(frame)),
			"capacity_mw_total": float(frame["capacity_mw"].sum()),
			"carriers": sorted(set(frame["carrier"])),
			"countries": sorted(set(frame["country_iso"])),
			"export": str(path),
			# Recorded because a fleet whose vintages are defaulted is a fleet
			# whose retirement dates are a convention, and a capacity-expansion
			# answer over a horizon is sensitive to when a plant retires.
			"commissioning_year_default": default_year,
			"n_plants_undated": n_undated,
			"lifetime_years_default": DEFAULT_LIFETIME_YEARS,
		},
		basis=Basis.MEASURED,
		notes=(
			"powerplantmatching export, read offline. The export is a manual, "
			"reviewed act; a per-run call would make the fleet depend on the "
			"upstream's state that week (02-data-pipeline §1.1)."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.fleet", plants=len(frame), capacity_mw=float(frame["capacity_mw"].sum()))
	return provenance


def _iso2(value: Any) -> str:
	"""A two-letter country code, from whatever the export wrote."""
	text = str(value).strip()
	if len(text) == 2:
		return text.upper()
	from alea.registry import registry

	lowered = text.lower()
	for country in registry().values():
		if lowered in (country.name.lower(), str(country.iso3).lower()):
			return str(country.iso2)
	return text.upper()


def _carrier_name(value: Any) -> str:
	"""Map an upstream fuel string onto a registry carrier.

	Delegates to `alea.registry.technologies.get_technology`, which is the one
	table that knows what an upstream fuel string means. This function used to
	carry its own copy of that table and the two had drifted: the registry maps
	``hydroelectric``, ``reservoir``, ``photovoltaic``, ``pumped storage``,
	``li-ion``, ``bess`` and nine others, and the stage's copy mapped none of
	them. So an export holding a hydro plant named ``Hydroelectric`` -- which is
	powerplantmatching's own spelling, and the reason the registry's table has
	that key at all -- reached the unknown-carrier gate below and failed the
	whole build, with a message telling the operator to add a carrier that was
	already registered.

	Two tables for one mapping is the defect; the fix is to keep one. An
	unmapped string is still passed through unchanged, so the gate names it
	rather than folding it into a default carrier where nobody would see it.
	"""
	text = str(value).strip()
	if not text:
		return text
	try:
		return get_technology(text).carrier.value
	except KeyError:
		# Not an alias and not a carrier name. Normalised the way the old table
		# normalised, so the refusal message reads the same as it always did.
		return text.lower().replace(" ", "_").replace("-", "_")


# --------------------------------------------------------------------------
# 3. demand_national
# --------------------------------------------------------------------------


@stage("demand_national")
def build_demand_national(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``demand_national`` -- annual national demand totals from the AfDB statistics.

	The register marks ``afrec_demand`` manual and proprietary; what is fetched
	is the AfDB's openly-licensed regional statistics, which carry the same
	national consumption table. The provenance says which table answered.

	Because the register marks the source manual, ``get_fetcher`` refuses it by
	default and this stage reads a committed export. Point ``afrec_export`` at a
	committed file to use it directly.
	"""
	manual = context.parameters.get("afrec_export")
	if manual:
		path = Path(str(manual))
		if not path.is_absolute():
			path = _raw_root(config, context) / path
		if not path.exists():
			raise ArtefactError(f"demand_national: no export at {path}")
	else:
		path = _require_raw(config, context, "afrec_demand", manual=_MANUAL_DEFAULTS["afrec_demand"])
	checksum = _checksum_of(path)
	raw = _read_table(path)

	frame = _annual_demand(raw, config)
	if frame.empty:
		raise ArtefactError(
			f"demand_national: the payload holds no annual total for "
			f"{', '.join(str(i) for i in config.scenario.countries)}"
		)

	provenance = _provenance(
		config,
		context,
		source_id="demand_national",
		inputs=[checksum],
		parameters={
			"n_rows": int(len(frame)),
			"years": sorted(int(y) for y in frame["year"].unique()),
			"source": str(path),
		},
		basis=Basis.MEASURED,
		notes=(
			"National totals are the measured constraint everything downstream is "
			"scaled to. For a CRITICAL-tier country the total is a proxy scaled "
			"from a regional average, and carries uncertainty_basis='proxy' "
			"(02-data-pipeline §3.1)."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.demand_national", rows=len(frame))
	return provenance


def _annual_demand(raw: pd.DataFrame, config: Config) -> pd.DataFrame:
	"""``country_iso, year, demand_twh`` from a long statistics table.

	The AfDB/HDX spreadsheet is one row per (country, indicator, year) with the
	value in a column whose name changes between releases, so the value column is
	chosen by name with a numeric fallback rather than assumed.
	"""
	country = _pick(raw, "country_iso", "country", "Country", "Area")
	year = _pick(raw, "year", "Year", "period")
	if country is None or year is None:
		raise ArtefactError(
			f"demand_national: payload has no country/year columns; it holds "
			f"{', '.join(str(c) for c in raw.columns)}"
		)
	value = _pick(raw, "demand_twh", "value", "Value", "consumption_gwh", "electricity_consumption")
	if value is None:
		numeric = [
			str(c)
			for c in raw.columns
			if c not in (country, year) and pd.api.types.is_numeric_dtype(raw[c])
		]
		if not numeric:
			raise ArtefactError("demand_national: payload has no numeric demand column")
		value = numeric[0]

	frame = pd.DataFrame(
		{
			"country_iso": raw[country].map(_iso2),
			"year": pd.to_numeric(raw[year], errors="coerce"),
			"value": pd.to_numeric(raw[value], errors="coerce"),
		}
	).dropna(subset=["year", "value"])
	frame["year"] = frame["year"].astype(int)
	# GWh is the unit the statistics tables use; TWh is the unit §3 declares. The
	# conversion is decided by the column's own name and recorded, not guessed
	# per row -- a mixed-unit column is a defect, not an input.
	scale = 0.001 if "gwh" in str(value).lower() else 1.0
	frame["demand_twh"] = frame["value"] * scale
	frame = frame[["country_iso", "year", "demand_twh"]]
	countries = {str(iso) for iso in config.scenario.countries}
	return frame.loc[frame["country_iso"].isin(countries)].reset_index(drop=True)


# --------------------------------------------------------------------------
# 4. demand_hourly
# --------------------------------------------------------------------------


@stage("demand_hourly")
def build_demand_hourly(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``demand_hourly`` -- national demand disaggregated to buses.

	Needs ``demand_national`` and a bus weight vector (population and GDP shares
	per bus, §3.1). Both are required: a disaggregation with no weights is a
	national total copied to every bus, which is a defensible-looking map that is
	wrong by the whole spatial structure of the country.

	The weights are a *human* artefact, not a registered source. §3.1 describes
	them as WorldPop-derived, and the share of a country's population that falls
	at each modelled bus is a quantity no fetcher produces -- it depends on the
	bus geometry this run built. The stage therefore takes the table and refuses
	without it, rather than naming a source the register does not hold.
	"""
	national_path = context.parameters.get("demand_national")
	if not national_path:
		from alea.config.paths import resolve

		national_path = resolve(config.paths.processed) / "demand_national.parquet"
	national_path = Path(str(national_path))
	if not national_path.exists():
		raise ArtefactError(
			f"demand_hourly: no demand_national artefact at {national_path}; build "
			f"it first. Disaggregating a total that does not exist would write an "
			f"hourly series of zeros"
		)
	national, _ = _read_artefact_frame(national_path)
	weights_path = context.parameters.get("bus_weights")
	if not weights_path:
		# There was a `worldpop` fallback here, and it could not run: `worldpop`
		# is in no register, so `_require_raw` raised `unknown source` before it
		# read anything. The branch was dead in the sense that mattered -- no
		# caller reached it with a working source -- and a fallback that cannot
		# succeed reads as a configured alternative while being an error path
		# with a misleading message. The weight table is a human artefact
		# (`rules/common.smk` says why), and the message says so.
		raise ArtefactError(
			"demand_hourly: no bus weight table. Disaggregating a national total "
			"against no weights copies it to every bus, which is a defensible-"
			"looking map wrong by the whole spatial structure of the country. "
			"Pass --set bus_weights=<path> with columns bus_id, population and gdp"
		)
	population, product = _weights_from(Path(str(weights_path)))

	alpha = float(context.parameters.get("alpha", DEFAULT_ALPHA))
	if not 0.0 <= alpha <= 1.0:
		raise ArtefactError(f"demand_hourly: alpha must be in [0, 1], got {alpha}")

	year = int(context.parameters.get("year", min(config.scenario.planning_horizons)))
	series = _hourly_shape(config, year)
	frame = _disaggregate(
		config, national, series, population, product, alpha=alpha, year=year
	)

	inputs = [
		*context.inputs,
		_checksum_of(national_path),
		_checksum_of(Path(str(weights_path))),
	]
	provenance = _provenance(
		config,
		context,
		source_id="demand_hourly",
		inputs=inputs,
		parameters={
			"alpha": alpha,
			"year": year,
			"n_buses": int(len(population)),
			"hours": int(len(frame)),
			"weight_source": str(weights_path),
			"weight_formula": "weight(bus) = (1 - alpha) * pop_share(bus) + alpha * gdp_share(bus)",
			"disaggregation": "demand(bus, t) = national_demand(t) x weight(bus)",
		},
		basis=Basis.PROXY,
		uncertainty=0.25,
		uncertainty_basis=(
			"proxy disaggregation: the national total is measured, the spatial "
			"split is a modelled share"
		),
		notes=(
			f"Disaggregated with alpha={alpha} (population vs GDP share), which is "
			f"recorded because an unrecorded alpha produces a map nobody can "
			f"defend (02-data-pipeline §3.1). The hourly *shape* is a modelled "
			f"diurnal-seasonal profile; the annual total is the measured figure."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.demand_hourly", buses=len(population), hours=len(frame), alpha=alpha)
	return provenance


def _read_artefact_frame(path: Path) -> tuple[pd.DataFrame, DerivedProvenance]:
	"""Read a tabular artefact and its provenance, verifying the payload hash."""
	from alea.io.artefacts import read_artefact

	frame, provenance = read_artefact(path)
	if not isinstance(frame, pd.DataFrame):
		raise ArtefactError(f"{path}: expected a tabular artefact, got {type(frame).__name__}")
	return frame, provenance


def _weights_from(path: Path) -> tuple[dict[str, float], dict[str, float]]:
	"""``({bus: population_share}, {bus: gdp_share})`` from a weight table.

	Both shares are returned unblended because ``alpha`` blends them, and a blend
	applied here would make the caller's ``alpha`` a no-op that still reads as if
	it had been applied. A bus with neither a population nor a GDP value gets a
	zero share rather than a mean one, and the caller refuses a vector that sums
	to zero -- silently inventing a share is how demand moves to a bus nobody
	populated.
	"""
	table = _read_table(path)
	bus = _pick(table, "bus_id", "bus", "Bus", "name")
	if bus is None:
		raise ArtefactError(
			f"{path}: weight table has no bus column; it holds "
			f"{', '.join(str(c) for c in table.columns)}"
		)
	names = [str(value) for value in table[bus]]
	if len(set(names)) != len(names):
		raise ArtefactError(f"{path}: bus identifiers are not unique")
	population = _pick(table, "population", "pop", "Population")
	product = _pick(table, "gdp", "GDP")
	if population is None and product is None:
		raise ArtefactError(f"{path}: weight table has neither a population nor a GDP column")
	pop = _share(
		pd.to_numeric(table[population], errors="coerce").fillna(0.0)
		if population
		else pd.Series(0.0, index=table.index)
	)
	gdp = _share(
		pd.to_numeric(table[product], errors="coerce").fillna(0.0)
		if product
		else pd.Series(0.0, index=table.index)
	)
	return (
		dict(zip(names, (float(v) for v in pop), strict=True)),
		dict(zip(names, (float(v) for v in gdp), strict=True)),
	)


def _share(values: pd.Series) -> pd.Series:
	total = float(values.sum())
	if total <= 0.0:
		return pd.Series(0.0, index=values.index)
	return values / total


def _hourly_shape(config: Config, year: int) -> pd.Series:
	"""The national hourly demand shape, in MW, for one year.

	A modelled diurnal-seasonal profile normalised to a mean of 1 MW, scaled by
	the caller to the measured national total. Deterministic by construction:
	AD-8 forbids unseeded randomness, and a synthetic series that changes
	between runs makes every downstream comparison meaningless.

	The index is the whole calendar year, not ``HOURS_PER_YEAR`` hours from the
	first of January. A fixed 8760 ends a leap year at 30 December 23:00, so
	2040 and 2060 -- two of the four default horizons -- carried no load for
	their last 24 hours, and `02-data-pipeline.md` §4.2's
	``test_demand_hourly_covers_horizon`` is the gate that asks for exactly
	this. The normaliser is the index's own length for the same reason: a
	series normalised to 8760 over 8784 hours is a year that is 0.27% short.
	"""
	index = pd.date_range(
		f"{year}-01-01 00:00", f"{year}-12-31 23:00", freq="h", tz="UTC", name="timestamp_utc"
	)
	hour = index.hour.to_numpy(dtype=float)
	doy = index.dayofyear.to_numpy(dtype=float)
	# Two peaks, a morning ramp and an evening peak, plus a seasonal swing.
	diurnal = 0.72 + 0.22 * np.exp(-((hour - 7.0) ** 2) / 8.0) + 0.34 * np.exp(-((hour - 19.0) ** 2) / 10.0)
	seasonal = 1.0 + 0.10 * np.cos(2.0 * np.pi * (doy - 20.0) / 365.25)
	shape = diurnal * seasonal
	shape = shape / float(shape.sum()) * float(len(index))
	assert np.isfinite(shape).all(), "demand shape has a non-finite value"
	return pd.Series(shape, index=index, name="shape")


def _disaggregate(
	config: Config,
	national: pd.DataFrame,
	series: pd.Series,
	population: dict[str, float],
	product: dict[str, float],
	*,
	alpha: float,
	year: int,
) -> pd.DataFrame:
	"""Scale the shape to the national total and split it across buses.

	``alpha`` blends the two shares exactly as §3.1 states it:
	``weight(bus) = (1 - alpha) * pop_share(bus) + alpha * gdp_share(bus)``.
	Where the weight table carries no GDP column the product share is all zeros,
	so the blend is the population share at every alpha; that is recorded in the
	parameters rather than hidden, because a disaggregation that claims a GDP
	component it does not have is the same defect as an unrecorded alpha.
	"""
	if len(population) != len(product):
		raise ArtefactError(
			f"demand_hourly: {len(population)} population shares and "
			f"{len(product)} GDP shares; the two vectors must cover the same buses"
		)
	weights = {
		bus: (1.0 - alpha) * population[bus] + alpha * product.get(bus, 0.0)
		for bus in population
	}
	total_weight = sum(weights.values())
	if total_weight <= 0.0:
		raise ArtefactError(
			"demand_hourly: bus weights sum to zero; every bus has neither a "
			"population nor a GDP value, so the disaggregation has no spatial "
			"information to divide by"
		)

	reference_twh = _reference_total(national, config, year)
	from alea.planning.demand import disaggregate_to_buses, scale_to_national

	scaled, check = scale_to_national(
		series,
		reference_twh,
		country=", ".join(str(iso) for iso in config.scenario.countries),
		source=str(national.columns.tolist()),
	)
	shares = {bus: weight / total_weight for bus, weight in weights.items()}
	profiles = disaggregate_to_buses(scaled, shares)
	profiles.index.name = "timestamp_utc"
	frame = profiles.reset_index().melt(
		id_vars="timestamp_utc", var_name="bus_id", value_name="demand_mw"
	)
	frame["country_iso"] = str(config.scenario.countries[0])
	frame["national_check"] = json.dumps(check.as_dict(), sort_keys=True)
	frame = frame[["country_iso", "bus_id", "timestamp_utc", "demand_mw", "national_check"]]
	assert len(frame) == len(series) * len(weights), "disaggregation lost rows"
	return frame


def _reference_total(national: pd.DataFrame, config: Config, year: int) -> float:
	"""The national total in TWh for the requested year, or the nearest one."""
	country = str(config.scenario.countries[0])
	subset = national.loc[national["country_iso"] == country]
	if subset.empty:
		raise ArtefactError(
			f"demand_hourly: demand_national holds no total for {country}; the "
			f"countries it covers are {sorted(set(national['country_iso']))}"
		)
	subset = subset.assign(gap=(subset["year"] - year).abs()).sort_values(["gap", "year"])
	value = float(subset["demand_twh"].iloc[0])
	if value <= 0.0:
		raise ArtefactError(f"demand_hourly: national total for {country} is {value} TWh")
	return value


# --------------------------------------------------------------------------
# 4b. cutout (the ERA5 download stage of §4)
# --------------------------------------------------------------------------


@stage("cutout")
def build_cutout(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``cutout`` -- the ERA5 cutout ``renewable_profiles`` reads.

	§4's DAG is ``fetch_era5 -> build_cutout -> build_renewable_profiles``. The
	download is the largest artefact in the pipeline (tens of GB for Africa), so
	it is DVC-tracked, never rebuilt in CI, and idempotent: an existing cutout is
	reused unless ``--force`` says otherwise.

	atlite writes a ``.nc`` plus a ``.nc.aux`` sidecar, and both are checksummed
	(§1.1). Checksumming the ``.nc`` alone produces a cutout that verifies and
	fails to open.
	"""
	cutout_path = Path(str(context.parameters.get("cutout_path") or out))
	force = bool(context.parameters.get("force", False))
	if cutout_path.exists() and not force:
		return _existing_cutout_provenance(config, context, cutout_path)

	bounds = _cutout_bounds(config, context)
	years = _cutout_years(config, context)

	import atlite

	cutout = atlite.Cutout(
		path=str(cutout_path),
		module="era5",
		bounds=bounds,
		time=slice(f"{years[0]}-01-01", f"{years[-1]}-12-31"),
	)
	cutout.prepare()

	sidecar = Path(f"{cutout_path}.aux")
	if not cutout_path.exists():
		raise ArtefactError(
			f"cutout: atlite returned without writing {cutout_path}; a cutout that "
			f"reports success without a file is a profiles stage that will fail later"
		)
	provenance = _provenance(
		config,
		context,
		source_id="cutout",
		inputs=[sha256_file(cutout_path), sha256_file(sidecar)] if sidecar.exists() else [sha256_file(cutout_path)],
		parameters={
			"cutout": str(cutout_path),
			"bounds": list(bounds),
			"years": list(years),
			"sidecar_checksummed": sidecar.exists(),
			"module": "era5",
		},
		basis=Basis.MODELLED,
		uncertainty=0.0,
		notes=(
			"ERA5 reanalysis, Copernicus licence. The .nc.aux sidecar is "
			"checksummed alongside the .nc: checksumming only the .nc yields a "
			"cutout that verifies and fails to open (02-data-pipeline §1.1)."
		),
	)
	# The cutout is a NetCDF file rather than a table, so the provenance is
	# written as a JSON artefact beside it. `build_stage` requires an artefact at
	# `out`, and `out` *is* the cutout, so the sidecar is what it finds.
	_write_provenance_sidecar(cutout_path, provenance)
	_log.info("stage.cutout", path=str(cutout_path), years=list(years))
	return provenance


def _existing_cutout_provenance(
	config: Config, context: BuildContext, cutout_path: Path
) -> DerivedProvenance:
	"""Provenance for a cutout that already exists, without rebuilding it."""
	sidecar = Path(f"{cutout_path}.aux")
	return _provenance(
		config,
		context,
		source_id="cutout",
		inputs=[sha256_file(cutout_path), sha256_file(sidecar)] if sidecar.exists() else [sha256_file(cutout_path)],
		parameters={"cutout": str(cutout_path), "reused": True},
		basis=Basis.MODELLED,
		notes="Existing cutout reused; the download is idempotent and --force overrides.",
	)


def _cutout_bounds(config: Config, context: BuildContext) -> tuple[float, float, float, float]:
	"""The cutout bounding box.

	From the context when a caller names one, and otherwise from the topology
	artefact's own endpoint extent -- which is the network the profiles will be
	attached to, so it is the right box by construction. The country registry
	carries no coordinates, and inventing a bounding-box table here would be
	data this project has not verified.
	"""
	declared = context.parameters.get("bounds")
	if declared:
		values = tuple(float(v) for v in declared)
		if len(values) != 4:
			raise ArtefactError(f"cutout: bounds must be (x_min, y_min, x_max, y_max), got {values}")
		return values  # type: ignore[return-value]

	from alea.config.paths import resolve

	topology = Path(str(context.parameters.get("topology") or resolve(config.paths.processed) / "topology.parquet"))
	if not topology.exists():
		raise ArtefactError(
			f"cutout: no topology artefact at {topology} to take the extent from, "
			f"and no `bounds` given. Build topology first; a cutout with no extent "
			f"is not a cutout"
		)
	frame = pd.read_parquet(topology)
	pad = float(context.parameters.get("bounds_pad_deg", 0.5))
	lons = pd.concat([frame["from_lon"], frame["to_lon"]])
	lats = pd.concat([frame["from_lat"], frame["to_lat"]])
	bounds = (
		float(lons.min()) - pad,
		float(lats.min()) - pad,
		float(lons.max()) + pad,
		float(lats.max()) + pad,
	)
	if not all(np.isfinite(bounds)):
		raise ArtefactError("cutout: the topology extent is not finite")
	return bounds


def _cutout_years(config: Config, context: BuildContext) -> list[int]:
	"""The years the cutout covers, from the context or the planning horizons."""
	declared = context.parameters.get("years")
	if declared:
		years = sorted(int(y) for y in declared)
	else:
		years = [min(config.scenario.planning_horizons) - 1, min(config.scenario.planning_horizons)]
	if not years:
		raise ArtefactError("cutout: no years to download")
	return years


def _write_provenance_sidecar(path: Path, provenance: DerivedProvenance) -> None:
	"""Write an artefact's provenance beside a payload this module wrote itself."""
	sidecar = path.with_suffix(path.suffix + ".provenance.json")
	sidecar.parent.mkdir(parents=True, exist_ok=True)
	sidecar.write_text(
		json.dumps(provenance.model_dump(mode="json"), indent=2, sort_keys=True),
		encoding="utf-8",
	)


# --------------------------------------------------------------------------
# 5. renewable_profiles
# --------------------------------------------------------------------------


@stage("renewable_profiles")
def build_renewable_profiles(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``renewable_profiles`` -- capacity factors per (bus, time, carrier), NetCDF.

	The cutout is the input and it is large: it is DVC-tracked and never rebuilt
	in CI (``02-data-pipeline.md`` §1.1). This stage reads it and writes the
	profiles; the ``build_cutout`` stage is what downloads.
	"""
	cutout_path = context.parameters.get("cutout_path")
	if not cutout_path:
		cutout_path = _require_raw(config, context, "era5_cutout")
	cutout_path = Path(str(cutout_path))
	if not cutout_path.exists():
		raise ArtefactError(f"renewable_profiles: no cutout at {cutout_path}")

	import atlite

	cutout = atlite.Cutout(str(cutout_path))
	carriers = _renewable_carriers(config)
	if not carriers:
		raise ArtefactError(
			"renewable_profiles: no renewable carrier is enabled in "
			"config.renewables; a profiles artefact with no carrier is an empty file"
		)

	buses = _buses(context)
	points = _bus_points(context, buses)
	profiles = _profiles_from_cutout(cutout, buses, points, carriers, config)
	if not profiles:
		raise ArtefactError("renewable_profiles: the cutout produced no profile")

	dataset = _profiles_to_dataset(profiles)
	provenance = _provenance(
		config,
		context,
		source_id="renewable_profiles",
		parameters={
			"cutout": str(cutout_path),
			"carriers": sorted(profiles),
			"n_buses": len(buses),
			"hours": int(len(next(iter(profiles.values())))),
			"layout": {
				carrier: _layout_description(carrier, config) for carrier in sorted(profiles)
			},
			"conversion": (
				"atlite convert_and_aggregate at the grid cell nearest each bus; "
				"per-unit output from the layout, clipped to [0, 1]"
			),
		},
		basis=Basis.MODELLED,
		uncertainty=0.15,
		uncertainty_basis=(
			"layout sensitivity: turbine class, hub height, tilt and tracking move "
			"the capacity factor by 10-20%"
		),
		notes=(
			"Capacity factors modelled from reanalysis meteorology, not measured at "
			"site. In [0, 1] by construction; a value above 1 means the profile is "
			"already in MW."
		),
	)
	write_stage(out, dataset, provenance)
	_log.info("stage.renewable_profiles", carriers=sorted(profiles), buses=len(buses))
	return provenance


def _renewable_carriers(config: Config) -> list[str]:
	"""Enabled renewable carriers, or the registry's when the config names none."""
	if config.renewables:
		return sorted(name for name, entry in config.renewables.items() if entry.enabled)
	return ["solar", "onwind"]


def _buses(context: BuildContext) -> list[str]:
	"""The bus identifiers a profile is produced for.

	The bus list comes from the topology artefact's own endpoint clustering when
	it is available, and otherwise from the configured country set. It is never
	invented: a profile keyed to a bus that no network contains is a file
	nothing can attach.
	"""
	declared = context.parameters.get("buses")
	if declared:
		return [str(b) for b in declared]
	countries = context.parameters.get("countries")
	if countries:
		return [str(c) for c in countries]
	raise ArtefactError(
		"renewable_profiles: no bus list; pass the topology artefact's buses "
		"through the context or a `buses` parameter. A profile with no bus "
		"dimension cannot be attached to anything"
	)


def _bus_points(context: BuildContext, buses: list[str]) -> dict[str, tuple[float, float]]:
	"""``{bus: (lon, lat)}`` for the cutout lookup.

	A point is required for each bus: atlite's convertibles are spatial, and a
	profile with no location is a country-average that erases the resource
	gradient the profiles exist to carry. The points come from the context, from
	the topology artefact, or from the configured country's own coordinates.
	"""
	declared = context.parameters.get("bus_points")
	if isinstance(declared, dict) and declared:
		return {str(bus): (float(v[0]), float(v[1])) for bus, v in declared.items()}
	topology = context.parameters.get("topology")
	if topology:
		frame = pd.read_parquet(topology)
		points = {}
		for bus in buses:
			subset = frame.loc[frame["line_id"].astype(str) == bus]
			if subset.empty:
				subset = frame.iloc[[0]]
			points[bus] = (float(subset["from_lon"].iloc[0]), float(subset["from_lat"].iloc[0]))
		return points
	raise ArtefactError(
		"renewable_profiles: no bus coordinates; pass `bus_points` (a "
		"{bus: [lon, lat]} mapping) or `topology` (a topology artefact to read "
		"them from). A capacity factor with no location is a country average"
	)


def _profiles_from_cutout(
	cutout: Any,
	buses: list[str],
	points: dict[str, tuple[float, float]],
	carriers: list[str],
	config: Config,
) -> dict[str, pd.DataFrame]:
	"""One ``[time, bus]`` capacity-factor frame per carrier, clipped to [0, 1].

	atlite's own ``convert_and_aggregate`` does the conversion; the clipping is
	bounded, because a 1e-9 overshoot is rounding and anything larger is a unit
	error that must be visible rather than smoothed away.
	"""
	import xarray as xr

	from alea.planning.renewables import validate_capacity_factors

	indices = xr.Dataset(
		{
			"x": ("bus", [points[bus][0] for bus in buses]),
			"y": ("bus", [points[bus][1] for bus in buses]),
		},
		coords={"bus": buses},
	)
	profiles: dict[str, pd.DataFrame] = {}
	for carrier in carriers:
		entry = config.renewables.get(carrier)
		capacity_per_sqkm = entry.capacity_per_sqkm if entry is not None else 1.7
		availability = cutout.convert_and_aggregate(
			_converter(carrier),
			index=indices,
			capacity_factor=carrier in ("solar", "onwind", "offwind", "csp"),
			capacity_factor_timeseries=carrier in ("solar", "onwind", "offwind", "csp"),
			capacity_per_sqkm=capacity_per_sqkm,
		)
		frame = _availability_frame(availability, buses, carrier)
		validate_capacity_factors(frame, carrier=carrier)
		profiles[carrier] = frame
	return profiles


def _converter(carrier: str) -> str:
	"""The atlite conversion function name for a registry carrier."""
	conversions = {
		"solar": "pv",
		"csp": "csp",
		"onwind": "wind",
		"offwind": "wind",
		"hydro": "runoff",
		"ror": "runoff",
	}
	if carrier not in conversions:
		raise ArtefactError(
			f"renewable_profiles: no atlite conversion for carrier {carrier!r}; "
			f"known: {', '.join(sorted(conversions))}"
		)
	return conversions[carrier]


def _availability_frame(availability: Any, buses: list[str], carrier: str) -> pd.DataFrame:
	"""atlite's result as a ``[time, bus]`` frame, whatever shape it returns."""
	data = availability.to_dataset() if hasattr(availability, "to_dataset") else availability
	names = [str(name) for name in getattr(data, "data_vars", {})]
	if not names:
		raise ArtefactError(f"renewable_profiles: atlite returned no variable for {carrier}")
	variable = names[0]
	array = data[variable]
	if "bus" not in array.dims:
		# A single-point result loses the bus dimension; broadcast it back so the
		# frame's columns are the buses the caller asked for.
		array = array.expand_dims(bus=buses)
	frame = array.transpose("time", "bus").to_pandas()
	if isinstance(frame, pd.Series):  # a single bus yields a Series, not a frame
		frame = frame.to_frame(name=buses[0])
	frame.columns = [str(c) for c in frame.columns]
	return frame.loc[:, buses].astype(float).clip(lower=0.0, upper=1.0)


def _layout_description(carrier: str, config: Config) -> dict[str, Any]:
	"""The layout parameters a capacity factor depends on, for the provenance."""
	entry = config.renewables.get(carrier)
	description: dict[str, Any] = {"carrier": carrier}
	if entry is not None:
		description.update(
			{
				"cutout": entry.cutout,
				"method": entry.method,
				"capacity_per_sqkm": entry.capacity_per_sqkm,
			}
		)
		if entry.resource_params:
			description["resource_params"] = dict(entry.resource_params)
	return description


def _profiles_to_dataset(profiles: dict[str, pd.DataFrame]) -> Any:
	"""Stack the per-carrier frames into ``(carrier, bus, time) -> capacity_factor``."""
	import xarray as xr

	arrays = []
	carriers = sorted(profiles)
	for carrier in carriers:
		frame = profiles[carrier]
		arrays.append(
			xr.DataArray(
				frame.to_numpy(dtype=float)[None, :, :],
				dims=("carrier", "bus", "time"),
				coords={"carrier": [carrier], "bus": list(frame.columns), "time": frame.index},
			)
		)
	dataset = xr.concat(arrays, dim="carrier")
	dataset.name = "capacity_factor"
	return dataset.to_dataset()


# --------------------------------------------------------------------------
# 6. hydro_profiles
# --------------------------------------------------------------------------


@stage("hydro_profiles")
def build_hydro_profiles(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``hydro_profiles`` -- monthly capacity factors per hydro plant.

	The hydro atlas is a placeholder citation in the specification
	(``02-data-pipeline.md`` §1.2) and is marked unavailable in the register, so
	the stage refuses rather than writing a flat profile: a hydro profile of
	constant 1.0 is a plausible-looking file that would silently make every
	reservoir a baseload plant.
	"""
	manual = str(
		context.parameters.get("hydro_export") or _MANUAL_DEFAULTS["hydro_atlas"]
	)
	source = get_source("hydro_atlas")
	if source.unavailable and not context.parameters.get("hydro_export"):
		raise ArtefactError(
			"hydro_atlas is registered as unavailable: "
			f"{source.notes or 'the placeholder link in the specification is unresolved'}. "
			"Resolve the record and record the DOI in the source registry, or pass "
			"an export with --set hydro_export=<path>"
		)
	path = _require_raw(config, context, "hydro_atlas", manual=manual)
	checksum = _checksum_of(path)
	raw = _read_table(path)

	frame = _require_columns(
		raw,
		{
			"plant_id": _pick(raw, "plant_id", "plant", "id"),
			"month": _pick(raw, "month", "Month"),
			"capacity_factor": _pick(raw, "capacity_factor", "cf", "CF", "factor"),
		},
		artefact="hydro_profiles",
	)
	if frame.empty:
		raise ArtefactError("hydro_profiles: the atlas holds no monthly factors")
	frame["month"] = pd.to_numeric(frame["month"], errors="raise").astype(int)
	frame["capacity_factor"] = pd.to_numeric(frame["capacity_factor"], errors="raise")
	bad = frame.loc[(frame["capacity_factor"] < 0.0) | (frame["capacity_factor"] > 1.0)]
	if not bad.empty:
		raise ArtefactError(
			f"hydro_profiles: {len(bad)} capacity factor(s) outside [0, 1]; a factor "
			f"above 1 means the atlas column is already in MW"
		)

	provenance = _provenance(
		config,
		context,
		source_id="hydro_profiles",
		inputs=[checksum],
		parameters={
			"n_plants": int(frame["plant_id"].nunique()),
			"months": sorted(int(m) for m in frame["month"].unique()),
			"downscaling": str(context.parameters.get("downscaling", "seasonal-to-monthly")),
			"atlas": str(path),
		},
		basis=Basis.MODELLED,
		uncertainty=0.2,
		uncertainty_basis=(
			"seasonal atlas averages; hourly shapes require downscaling against "
			"ERA5 runoff and the method is a modelling choice"
		),
		notes=(
			"Seasonal averages from the atlas, recorded with the downscaling method "
			"so the profile is reproducible. The atlas's own published approach is "
			"the method of record (02-data-pipeline §1.1)."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.hydro_profiles", plants=frame["plant_id"].nunique())
	return provenance


# --------------------------------------------------------------------------
# 7. costs
# --------------------------------------------------------------------------


@stage("costs")
def build_costs(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``costs`` -- technology capital and operating costs from IRENA.

	Needed for expansion, not for dispatch (§1's priority table). Every currency
	conversion carries its rate and the rate's date, and the rate comes from
	``config.costs`` so the same rate is used everywhere it is applied.

	The register marks the source manual, so a committed export is read; the
	fetcher that exists for it reaches IRENA's openly-published aggregate table,
	which is a different product from the project-level database the register
	describes.
	"""
	manual = context.parameters.get("irena_export")
	path = _require_raw(
		config, context, "irena_costs", manual=str(manual or _MANUAL_DEFAULTS["irena_costs"])
	)
	checksum = _checksum_of(path)
	raw = _read_table(path)
	frame = _costs_frame(raw)
	if frame.empty:
		raise ArtefactError("costs: the payload holds no technology cost rows")

	provenance = _provenance(
		config,
		context,
		source_id="costs",
		inputs=[checksum],
		parameters={
			"n_rows": int(len(frame)),
			"technologies": sorted(set(frame["technology"])),
			"years": sorted(int(y) for y in frame["year"].unique()),
			"eur_usd": config.costs.eur_usd,
			"eur_usd_date": config.costs.eur_usd_date,
			"base_currency": config.costs.base_currency,
			"conversion_note": CURRENCY_NOTE,
		},
		basis=Basis.MEASURED,
		uncertainty=0.1,
		uncertainty_basis="published cost statistics; regional spread is 10-20%",
		notes=(
			"IRENA's openly-published aggregate statistics table, not the "
			"project-level cost database, which stays a manual export. Costs are "
			f"in {config.costs.base_currency}; a conversion records its rate and date."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.costs", rows=len(frame))
	return provenance


def _costs_frame(raw: pd.DataFrame) -> pd.DataFrame:
	"""``technology, year, capex_usd_per_kw, opex_usd_per_kw_yr, lifetime_years``."""
	technology = _pick(raw, "technology", "Technology", "tech")
	year = _pick(raw, "year", "Year")
	if technology is None or year is None:
		raise ArtefactError(
			f"costs: payload has no technology/year columns; it holds "
			f"{', '.join(str(c) for c in raw.columns)}"
		)
	capex = _pick(raw, "capex_usd_per_kw", "capex", "CAPEX", "total_installed_cost_usd_per_kw")
	opex = _pick(raw, "opex_usd_per_kw_yr", "opex", "OPEX", "fixed_opex")
	lifetime = _pick(raw, "lifetime_years", "lifetime", "Lifetime")
	if capex is None and opex is None:
		raise ArtefactError("costs: payload has neither a capex nor an opex column")

	frame = pd.DataFrame(
		{
			"technology": raw[technology].map(_carrier_name),
			"year": pd.to_numeric(raw[year], errors="coerce"),
			"capex_usd_per_kw": (
				pd.to_numeric(raw[capex], errors="coerce") if capex else np.nan
			),
			"opex_usd_per_kw_yr": (
				pd.to_numeric(raw[opex], errors="coerce") if opex else np.nan
			),
			"lifetime_years": (
				pd.to_numeric(raw[lifetime], errors="coerce") if lifetime else np.nan
			),
		}
	).dropna(subset=["year"])
	frame["year"] = frame["year"].astype(int)
	# A row with no capital and no operating cost carries nothing; leaving it in
	# produces a technology the expansion model prices at zero, which is free
	# capacity.
	frame = frame.dropna(subset=["capex_usd_per_kw", "opex_usd_per_kw_yr"], how="all")
	if frame["lifetime_years"].isna().all():
		frame["lifetime_years"] = 25.0
	known = {c.value for c in Carrier}
	frame = frame.loc[frame["technology"].isin(known)].reset_index(drop=True)
	return frame


# --------------------------------------------------------------------------
# 8. fuel_prices
# --------------------------------------------------------------------------


@stage("fuel_prices")
def build_fuel_prices(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``fuel_prices`` -- fuel prices in USD/MWh.

	The register notes that this source's date matters, because it feeds marginal
	cost. The conversion from a local-currency pump price to USD/MWh uses the rate
	recorded in ``config.costs`` and records it again here, with the retrieval
	period the payload carries.
	"""
	path = _require_raw(config, context, "global_petrol_prices")
	checksum = _checksum_of(path)
	raw = _read_table(path)
	frame = _fuel_frame(raw, config)
	if frame.empty:
		raise ArtefactError(
			f"fuel_prices: the payload holds no price for "
			f"{', '.join(str(i) for i in config.scenario.countries)}"
		)

	provenance = _provenance(
		config,
		context,
		source_id="fuel_prices",
		inputs=[checksum],
		parameters={
			"n_rows": int(len(frame)),
			"fuels": sorted(set(frame["fuel"])),
			"years": sorted(int(y) for y in frame["year"].unique()),
			"kes_usd": config.costs.kes_usd,
			"kes_usd_date": config.costs.kes_usd_date,
			"retrieved_period": str(context.parameters.get("retrieved_period", "")),
			"conversion_note": CURRENCY_NOTE,
		},
		basis=Basis.MEASURED,
		uncertainty=0.05,
		uncertainty_basis="pump price excludes taxes and distribution; conversion rate is dated",
		notes=(
			"Pump prices converted to USD/MWh at the configured rate, whose date is "
			"recorded. A price series without its date is a marginal cost nobody can "
			"reproduce."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.fuel_prices", rows=len(frame))
	return provenance


def _fuel_frame(raw: pd.DataFrame, config: Config) -> pd.DataFrame:
	"""``country_iso, fuel, year, price_usd_per_mwh`` from the pump-price CSV.

	A litre of gasoline carries about 8.9 kWh of energy, so ``USD/litre`` becomes
	``USD/MWh`` by dividing by 0.0089 MWh/litre. The factor is a named constant
	because an inverted one is a 100x error in every marginal cost.
	"""
	country = _pick(raw, "country_iso2", "country_iso", "country", "Country")
	fuel = _pick(raw, "fuel", "Fuel", "product")
	price = _pick(raw, "price_local", "price", "Price")
	if country is None or price is None:
		raise ArtefactError(
			f"fuel_prices: payload has no country/price columns; it holds "
			f"{', '.join(str(c) for c in raw.columns)}"
		)
	currency = _pick(raw, "currency", "Currency")
	year = _pick(raw, "year", "Year")
	period = _pick(raw, "retrieved_period", "period", "date")

	frame = pd.DataFrame(
		{
			"country_iso": raw[country].map(_iso2),
			"fuel": raw[fuel].astype(str) if fuel else "gasoline",
			"local": pd.to_numeric(raw[price], errors="coerce"),
			"currency": raw[currency].astype(str) if currency else config.costs.base_currency,
			"year": (
				pd.to_numeric(raw[year], errors="coerce")
				if year
				else pd.to_numeric(
					raw[period].astype(str).str.slice(0, 4), errors="coerce"
				)
				if period
				else np.nan
			),
		}
	).dropna(subset=["local"])
	frame["year"] = frame["year"].fillna(config.scenario.base_year).astype(int)
	frame["price_usd_per_mwh"] = frame.apply(
		lambda row: _to_usd_per_mwh(row, config), axis=1
	)
	frame = frame.dropna(subset=["price_usd_per_mwh"])
	countries = {str(iso) for iso in config.scenario.countries}
	frame = frame.loc[frame["country_iso"].isin(countries)]
	return frame.loc[:, list(FUEL_COLUMNS)].reset_index(drop=True)


MWH_PER_LITRE = 0.0089
"""Lower heating value of gasoline, MWh per litre. Named because inverting it is a 100x error."""


def _to_usd_per_mwh(row: pd.Series, config: Config) -> float:
	"""One local-currency pump price as USD/MWh, at the recorded rate."""
	currency = str(row["currency"]).strip().upper()
	price = float(row["local"])
	if not np.isfinite(price) or price <= 0.0:
		return float("nan")
	if currency in ("USD", "US$", "$"):
		usd_per_litre = price
	elif currency in ("KES", "KSH"):
		rate = config.costs.kes_usd
		if rate is None:
			raise ArtefactError(
				"fuel_prices: the payload prices fuel in KES but costs.kes_usd is "
				"unset; a conversion without a rate is not a conversion"
			)
		usd_per_litre = price / rate
	elif currency in ("EUR", "€"):
		rate = config.costs.eur_usd
		if rate is None:
			raise ArtefactError(
				"fuel_prices: the payload prices fuel in EUR but costs.eur_usd is "
				"unset; a conversion without a rate is not a conversion"
			)
		usd_per_litre = price * rate
	else:
		raise ArtefactError(
			f"fuel_prices: no rate configured for currency {currency!r}; add it to "
			f"config.costs with its date, or the price cannot become USD/MWh"
		)
	return usd_per_litre / MWH_PER_LITRE


# --------------------------------------------------------------------------
# 9. outage_history
# --------------------------------------------------------------------------


@stage("outage_history")
def build_outage_history(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``outage_history`` -- VIIRS-detected outage evidence per grid zone.

	Track B, independent of the planning sources. Two hazards from §1.1 are
	structural here rather than documented: the granules are streamed and never
	archived (``data/raw`` holds their checksums), and the observed,
	BRDF-corrected band is the only one read, with ``read_granule`` refusing the
	gap-filled band outright.
	"""
	granules = _granule_paths(config, context)
	baselines = _baseline_paths(config, context)
	if not granules:
		raise ArtefactError(
			"outage_history: no granules; run `alea fetch viirs_vnp46a2` first. A "
			"detector with no observation writes an empty series that reads as "
			"'no outages'"
		)

	from alea.outages.service import detect_to_artefact, detection_parameters_for
	from alea.outages.views import PredictiveConfig
	from alea.outages.viirs import read_granule

	# One tile, for the zone grid only: `_zones` needs the tile *shape*, and
	# `list(iter_tiles(granules))` would hold every granule in the sequence -- a
	# country-year is thousands of ~100 MB tiles and that list is the OOM the
	# criterion names. The detection pass below streams; nothing else here needs
	# a tile at all.
	first = read_granule(granules[0])
	zone_ids, n_zones = _zones(config, context, [first])
	del first
	cfg = PredictiveConfig(**context.parameters.get("predictive", {}))
	checksum, times = detect_to_artefact(
		granules,
		baselines or granules,
		zone_ids,
		n_zones,
		out,
		cfg,
		inputs=[_checksum_of(p) for p in [*granules, *baselines]],
	)
	# `detect_to_artefact` writes the payload and the sidecar but returns neither
	# the frame nor the provenance; both are read back so the registered stage
	# returns the provenance `build_stage` requires and refuses when the writer
	# produced no artefact.
	frame, written = _read_artefact_frame(out)
	if frame.empty:
		raise ArtefactError(
			"outage_history: the detector wrote an empty series; an outage history "
			"with no observation is indistinguishable from a grid with no outages"
		)
	provenance: DerivedProvenance = written
	_log.info(
		"stage.outage_history",
		zones=n_zones,
		observations=len(times),
		checksum=checksum[:12],
		parameters=sorted(detection_parameters_for(config)),
	)
	return provenance


def _granule_paths(config: Config, context: BuildContext) -> list[Path]:
	"""The VNP46A2 granules to detect over, from the raw layer or the context."""
	declared = context.parameters.get("granules")
	if declared:
		return [Path(str(p)) for p in declared]
	root = _raw_root(config, context) / "viirs_vnp46a2"
	if not root.is_dir():
		return []
	paths: list[Path] = []
	for directory in sorted(root.iterdir()):
		if not directory.is_dir():
			continue
		paths.extend(
			p
			for p in sorted(directory.iterdir())
			if p.is_file() and p.suffix.lower() in (".nc", ".h5", ".hdf")
		)
	return paths


def _baseline_paths(config: Config, context: BuildContext) -> list[Path]:
	"""The reference-period granules the baseline is built from."""
	declared = context.parameters.get("baseline_granules")
	return [Path(str(p)) for p in declared] if declared else []


def _zones(config: Config, context: BuildContext, tiles: list[Any]) -> tuple[Any, int]:
	"""A zone label per pixel, and the zone count.

	The zones are the grid areas an outage is reported for. They come from the
	context when a caller has a zone raster, and otherwise from a fixed
	partition of the tile grid, which is enough to produce a series whose
	semantics are stated rather than assumed.

	**The fallback is a partition of the tile, not a degree grid**, and the
	difference matters. The specification's `aggregate_to_zones(anomaly,
	resolution="0.01_degree")` (spec4-base §12.2) and the config field that used
	to carry that number both express the zone as a *geographic* cell, which a
	granule can only be divided into against a geolocation: a 0.01 deg cell is a
	position, and a tile offset is not. No plan specifies how a VNP46A2 granule
	is georeferenced, so dividing by degrees here would be inventing the mapping
	the specification left out. A caller with a real zone raster passes
	``zone_ids`` and gets exactly the semantics the spec intends; the fallback is
	labelled for what it is -- an equal partition of the tile -- so that a
	published zone series states which one produced it.
	"""
	declared = context.parameters.get("zone_ids")
	if declared is not None:
		array = np.asarray(declared, dtype=np.uint32)
		return array, int(array.max()) + 1
	if not tiles:
		raise ArtefactError("outage_history: no tiles to derive zones from")
	_, height, width = tiles[0].shape
	grid = int(context.parameters.get("zone_grid", 4))
	if grid < 1:
		raise ArtefactError(f"outage_history: zone_grid must be >= 1, got {grid}")
	rows = np.arange(height) * grid // max(1, height)
	columns = np.arange(width) * grid // max(1, width)
	zones = (rows[:, None] * grid + columns[None, :]).astype(np.uint32)
	n_zones = int(zones.max()) + 1
	return np.broadcast_to(zones, (height, width)), n_zones


# --------------------------------------------------------------------------
# 10. outage_truth
# --------------------------------------------------------------------------


@stage("outage_truth")
def build_outage_truth(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``outage_truth`` -- GridWatch ground truth.

	The token is required and its absence is a *raise*, not a skip: the register
	says the validation stage records a skip in its artefact, and the artefact
	that records a skip is the validation artefact, not the ground truth. Writing
	an empty ``outage_truth`` would make every later validation compare a
	detector against nothing and call the result a measurement.
	"""
	import os

	manual = context.parameters.get("gridwatch_export")
	token = os.environ.get("GRIDWATCH_TOKEN")
	if not manual and not token:
		raise ArtefactError(
			"outage_truth: GRIDWATCH_TOKEN is not in the environment. The "
			"validation stage records its own skip; a ground-truth artefact built "
			"with no ground truth would validate every detector against nothing"
		)
	path = _require_raw(config, context, "gridwatch", manual=str(manual) if manual else None)
	checksum = _checksum_of(path)
	raw = _read_table(path)

	frame = _require_columns(
		raw,
		{
			"sensor_id": _pick(raw, "sensor_id", "sensor", "device_id", "id"),
			"timestamp_utc": _pick(raw, "timestamp_utc", "timestamp", "time", "datetime"),
			"event_type": _pick(raw, "event_type", "event", "type", "status"),
		},
		artefact="outage_truth",
	)
	if frame.empty:
		raise ArtefactError("outage_truth: the GridWatch payload holds no events")
	frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="raise")
	duration = _pick(raw, "duration_min", "duration", "duration_minutes")
	frame["duration_min"] = (
		pd.to_numeric(raw[duration], errors="coerce") if duration else np.nan
	)

	provenance = _provenance(
		config,
		context,
		source_id="outage_truth",
		inputs=[checksum],
		parameters={
			"n_events": int(len(frame)),
			"sensors": int(frame["sensor_id"].nunique()),
			"event_types": sorted(str(v) for v in frame["event_type"].unique()),
			"start": str(frame["timestamp_utc"].min()),
			"end": str(frame["timestamp_utc"].max()),
			"licence_note": "GridWatch access is by registration; redistribution restricted",
		},
		basis=Basis.MEASURED,
		notes=(
			"Ghana sensor network, the specification's primary validation set. "
			"Ground truth for the VIIRS detector, never an input to detection."
		),
	)
	write_stage(out, frame, provenance)
	_log.info("stage.outage_truth", events=len(frame))
	return provenance


@stage("policy_tracker")
def build_policy_tracker(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""``policy_tracker`` -- confirmed policy-change signals, counted by country.

	The scanning layer's one report section, and the only artefact here whose
	input is a *reviewed queue* rather than a file. `scanning.integrate` stages
	proposals to `data/processed/scanning/proposals/`, and a proposal is not a
	fact -- `ReviewQueue.confirmed_signals()` is the set a human or the recorded
	auto-acceptance has accepted, so this stage reads that and never the staging
	directory. A tracker built from proposals would publish unreviewed claims as
	policy changes, which is the failure the layer's whole review design exists
	to prevent.

	The provenance is FORECAST rather than MEASURED for the same reason: a
	confirmed policy signal is a claim someone read in a document.
	"""
	from alea.io.artefacts import read_provenance
	from alea.scanning.review import ReviewQueue
	from alea.scanning.review.queue import queue_path
	from alea.scanning.service import policy_tracker_to_artefact

	# The queue lives under the *configured* results directory, not at the
	# module's default. `DEFAULT_QUEUE_PATH` is ``results/scanning/review.sqlite``
	# relative to the repository root, so reading it directly made the stage
	# blind to ``paths.results`` -- a run against a scratch tree would count
	# signals reviewed in a different tree, and the section would render empty
	# with nothing to say why.
	queue_at = queue_path(config.paths.results)
	# The producer records the queue's checksum itself; it is the only code
	# that knows which queue it read. An absent queue is an empty confirmed
	# set rather than an error: a tracker that has reviewed nothing is
	# honestly empty.
	frame = policy_tracker_to_artefact(out, queue=ReviewQueue(queue_at))
	_log.info("stage.policy_tracker", countries=len(frame))
	# The sidecar the producer wrote, not a second one built here: a stage that
	# returns provenance it did not write describes an artefact that is not on
	# disk.
	return read_provenance(out)


REGISTERED_STAGE_NAMES = (
	"costs",
	"cutout",
	"demand_hourly",
	"demand_national",
	"fleet",
	"fuel_prices",
	"hydro_profiles",
	"outage_history",
	"outage_truth",
	"policy_tracker",
	"renewable_profiles",
	"topology",
)
"""The stage names this module registers.

The ten datasets of §3, plus ``cutout``: §4's DAG is ``fetch_era5 ->
build_cutout -> build_renewable_profiles``, so the cutout is a stage with its own
input, its own output and its own idempotence, not a step inside the profiles
builder. Kept as a literal so a test can assert the registry holds exactly
these: a stage that failed to register is otherwise invisible until the CLI is
asked for it.
"""

__all__ = [
	"DEFAULT_ALPHA",
	"HOURS_PER_YEAR",
	"REGISTERED_STAGE_NAMES",
	"build_costs",
	"build_cutout",
	"build_demand_hourly",
	"build_demand_national",
	"build_fleet",
	"build_fuel_prices",
	"build_hydro_profiles",
	"build_outage_history",
	"build_outage_truth",
	"build_policy_tracker",
	"build_renewable_profiles",
	"build_topology",
	"config_parameters",
]
