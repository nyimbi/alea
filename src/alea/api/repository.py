# SPDX-License-Identifier: MIT
"""The read seam between the API and the layers below it.

Layer 8 computes nothing (11-layer8 §1). Every route reads an artefact or calls
a service below, and this module is the one place that knows where those
artefacts live and what columns they carry. Keeping that knowledge here rather
than in the routes is what makes a route a five-line function and makes a change
to a lower layer's output a one-file change.

**Every read is optional.** A missing artefact returns ``None``, and the route
turns that into a 404 with a message naming the artefact that is absent. The
alternative -- raising a ``KeyError`` from a pandas column lookup -- reports a
missing dataset as a server fault, which sends the operator looking for a bug in
the wrong place. The platform is expected to run with partial data: Layer 3 may
have published prices while Layer 4 has published no forecast yet, and the API
must serve what exists.

**A scenario id is a path component, so it is validated as one.** An id is used
to build a filesystem path; an unvalidated one is a directory traversal. The
validator is on the model (:func:`_safe_token`) rather than at each call site,
because a call site that forgets is the one that matters.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from alea.api.views import (
	CapacityRowOut,
	CaptureRateRowOut,
	ContingencyRowOut,
	CountryOut,
	LossComponentOut,
	LossDecompositionOut,
	MaintenancePredictionRowOut,
	MitigationOptionOut,
	OutageForecastRowOut,
	OutageHistoryRowOut,
	OutageValidationRowOut,
	PpaBenchmarkRowOut,
	PriceRowOut,
	ProvenanceOut,
	ReportOut,
	ResilienceMetricOut,
	ScenarioOut,
	ScenarioResultOut,
	ScenarioSummaryOut,
	TlensRowOut,
	ValueOut,
)
from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError, artefact_exists, read_artefact, read_provenance
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance, Provenance

logger = get_logger(__name__)

SCENARIO_INDEX = "results/scenarios/index.json"
"""Where the scenario catalogue lives. One file, so a listing is one read."""

NETWORK_DIR = "results/networks"


class ArtefactUnavailable(Exception):
	"""A route asked for an artefact that has not been produced.

	Distinct from an I/O failure: this is the ordinary case of a layer that has
	not run yet, and the route answers 404 with the path, not 500.
	"""

	def __init__(self, path: str, *, what: str = "artefact") -> None:
		super().__init__(f"no {what} at {path}")
		self.path = path
		self.what = what


def _safe_token(value: str, *, field: str) -> str:
	"""Reject anything that is not safe to put in a filesystem path.

	``..`` and ``/`` in a scenario id are a directory traversal, and the id is
	used to build a path on every scenario route. The rule is an allow-list
	because a deny-list of traversal sequences is a list somebody eventually
	completes incompletely.
	"""
	assert value, f"{field} must not be empty"
	allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@-")
	bad = sorted({character for character in value if character not in allowed})
	if bad or ".." in value:
		raise ValueError(
			f"{field}={value!r} contains characters that are not path-safe: {bad or ['..']}"
		)
	return value


def _provenance_out(provenance: Provenance | DerivedProvenance) -> ProvenanceOut:
	assert provenance is not None, "cannot render provenance from nothing"
	return ProvenanceOut(
		source_id=provenance.source_id,
		source_url=provenance.source_url,
		retrieved_at=provenance.retrieved_at,
		checksum=provenance.checksum,
		licence=provenance.licence,
		basis=provenance.basis,
		uncertainty=provenance.uncertainty,
		uncertainty_basis=provenance.uncertainty_basis,
		notes=provenance.notes,
	)


def _value(
	row: Any,
	column: str,
	unit: str,
	provenance: Provenance | DerivedProvenance | None,
	*,
	default: float = 0.0,
) -> ValueOut:
	"""Build a :class:`ValueOut` from a row, falling back to the artefact's own basis.

	A published table carries a value per row; the basis and uncertainty belong to
	the artefact unless the row overrides them, because a table produced by one
	model run has one basis. A row that disagrees says so with
	``<column>_basis`` / ``<column>_uncertainty`` columns.
	"""
	assert column, "a value needs a column"
	value = _number(row, column, default)
	basis = Basis.MEASURED
	uncertainty = 0.0
	if provenance is not None:
		basis = provenance.basis
		uncertainty = provenance.uncertainty

	override_basis = _optional(row, f"{column}_basis")
	if isinstance(override_basis, str) and override_basis:
		basis = Basis(override_basis)
	override_uncertainty = _optional(row, f"{column}_uncertainty")
	if override_uncertainty is not None:
		uncertainty = float(override_uncertainty)

	# A modelled, forecast or proxy number is never exact. If the artefact's
	# provenance does not say how uncertain it is, the value is refused rather
	# than given an invented precision of zero -- which is how a proxy becomes a
	# published fact.
	if basis in (Basis.MODELLED, Basis.PROXY, Basis.FORECAST) and uncertainty <= 0.0:
		raise ArtefactError(
			f"{column}: basis={basis.value!r} with no uncertainty; an inexact "
			f"number must state how inexact, or it will be read as exact"
		)

	return ValueOut(
		value=value,
		unit=unit,
		basis=basis,
		uncertainty=uncertainty,
		source_id=provenance.source_id if provenance is not None else "",
	)


def _optional(row: Any, column: str) -> Any:
	"""A column's value, or ``None`` if the column is absent or null."""
	if isinstance(row, dict):
		return row.get(column)
	try:
		value = row[column]
	except (KeyError, IndexError):
		return None
	if value is None:
		return None
	try:
		if pd.isna(value):
			return None
	except (TypeError, ValueError):
		pass
	return value


def _number(row: Any, column: str, default: float = 0.0) -> float:
	"""A required numeric column."""
	value = _optional(row, column)
	if value is None:
		return default
	return float(value)


def _text(row: Any, column: str, default: str = "") -> str:
	value = _optional(row, column)
	return default if value is None else str(value)


def _moment(row: Any, column: str) -> datetime:
	"""A required timestamp column.

	``pd.Timestamp`` is kept for its parser -- it accepts the ISO strings, epoch
	seconds and ``datetime`` objects the artefacts carry, which ``datetime``
	alone does not -- but its return type is ``datetime | NaTType``, and ``NaT``
	is a missing value, not a moment. Converting through ``to_pydatetime``
	yields a real ``datetime`` or raises for an unparseable value, and the cast
	states the invariant the artefacts are written under: a required timestamp
	column holds a timestamp.
	"""
	value = _optional(row, column)
	if value is None:
		raise ArtefactError(f"{column}: a required timestamp is missing")
	return cast("datetime", pd.Timestamp(value).to_pydatetime())


class Repository:
	"""Reads the artefacts the layers below have produced."""

	def __init__(self, config: Config) -> None:
		assert config is not None, "the repository needs the loaded configuration"
		self.config = config

	# -- low-level reads ---------------------------------------------------

	def _table(self, relative: str) -> tuple[pd.DataFrame, DerivedProvenance] | None:
		"""Read a tabular artefact, or ``None`` if it has not been produced."""
		path = resolve(relative)
		if not artefact_exists(path):
			return None
		try:
			data, provenance = read_artefact(path)
		except ArtefactError as exc:
			# A present-but-unreadable artefact is a real fault, not a missing
			# one, and swallowing it would serve a stale or empty answer.
			logger.error("repository.read_failed", path=str(path), error=str(exc))
			raise
		if not isinstance(data, pd.DataFrame):
			raise ArtefactError(f"{path}: expected a table, got {type(data).__name__}")
		return data, provenance

	def _document(self, relative: str) -> tuple[dict[str, Any], DerivedProvenance] | None:
		"""Read a JSON artefact, or ``None`` if it has not been produced."""
		path = resolve(relative)
		if not artefact_exists(path):
			return None
		data, provenance = read_artefact(path)
		if not isinstance(data, dict):
			raise ArtefactError(f"{path}: expected an object, got {type(data).__name__}")
		return data, provenance

	def _plain_json(self, relative: str) -> dict[str, Any] | None:
		"""Read a JSON file that is not an artefact (no sidecar, no checksum).

		Used for indexes the API maintains itself, where a provenance sidecar
		would be circular -- the index describes artefacts, it is not one.
		"""
		path = resolve(relative)
		if not path.exists():
			return None
		return json.loads(path.read_text(encoding="utf-8"))

	def checksum(self, relative: str) -> str | None:
		"""The recorded checksum of an artefact, for a cache key.

		``None`` when the artefact is absent, which the caller turns into a
		refusal to cache rather than a cache key that ignores the input.
		"""
		path = resolve(relative)
		if not artefact_exists(path):
			return None
		try:
			return read_provenance(path).checksum
		except ArtefactError:
			return None

	# -- scenarios ---------------------------------------------------------

	def _scenario_dir(self, scenario_id: str) -> str:
		token = _safe_token(scenario_id, field="scenario_id")
		return f"results/scenarios/{token}"

	def scenarios(self) -> list[ScenarioSummaryOut]:
		"""Every scenario in the catalogue, newest first."""
		index = self._plain_json(SCENARIO_INDEX)
		if index is None:
			return []
		entries = index.get("scenarios", [])
		if not isinstance(entries, list):
			raise ArtefactError(f"{SCENARIO_INDEX}: 'scenarios' must be a list")
		out: list[ScenarioSummaryOut] = []
		for entry in entries:
			out.append(self._summary_from_document(entry))
		out.sort(key=lambda summary: summary.created_at, reverse=True)
		return out

	def scenario(self, scenario_id: str) -> ScenarioOut | None:
		"""One scenario's metadata, or ``None``."""
		document = self._document(f"{self._scenario_dir(scenario_id)}/scenario.json")
		if document is None:
			return None
		data, provenance = document
		summary = self._summary_from_document(data)
		return ScenarioOut(
			**summary.model_dump(),
			network_checksum=_text(data, "network_checksum"),
			code_version=_text(data, "code_version"),
			provenance=_provenance_out(provenance),
		)

	def _summary_from_document(self, data: dict[str, Any]) -> ScenarioSummaryOut:
		assert isinstance(data, dict), "a scenario summary is an object"
		scenario_id = _text(data, "scenario_id") or _text(data, "name")
		if not scenario_id:
			raise ArtefactError("a scenario entry has neither scenario_id nor name")
		_safe_token(scenario_id, field="scenario_id")
		created = _text(data, "created_at")
		if not created:
			raise ArtefactError(f"scenario {scenario_id} has no created_at")
		return ScenarioSummaryOut(
			scenario_id=scenario_id,
			name=_text(data, "name", scenario_id),
			countries=[str(c) for c in data.get("countries", [])],
			planning_horizons=[int(h) for h in data.get("planning_horizons", [])],
			clusters=[int(c) for c in data.get("clusters", [])],
			created_at=cast("datetime", pd.Timestamp(created).to_pydatetime()),
			description=_text(data, "description"),
		)

	def scenario_result(self, scenario_id: str, horizon: int) -> ScenarioResultOut | None:
		"""A scenario's solved result at one horizon, or ``None``."""
		assert horizon > 0, f"horizon must be a year, got {horizon}"
		directory = self._scenario_dir(scenario_id)
		document = self._document(f"{directory}/results/{horizon}.json")
		if document is None:
			return None
		data, provenance = document
		mix = [
			CapacityRowOut(
				carrier=str(row.get("carrier", "")),
				capacity_mw=_value(row, "capacity_mw", "MW", provenance),
				share=_value(row, "share", "fraction", provenance),
			)
			for row in data.get("capacity_mix", [])
		]
		return ScenarioResultOut(
			scenario_id=scenario_id,
			horizon=horizon,
			objective=_value(data, "objective", "USD", provenance),
			total_capacity_mw=_value(data, "total_capacity_mw", "MW", provenance),
			capacity_mix=mix,
			network_checksum=_text(data, "network_checksum"),
			solved_at=cast("datetime", pd.Timestamp(data["solved_at"]).to_pydatetime())
			if data.get("solved_at")
			else None,
		)

	def scenario_result_checksum(self, scenario_id: str, horizon: int) -> str | None:
		"""The checksum of a solved result, for a cache key."""
		return self.checksum(f"{self._scenario_dir(scenario_id)}/results/{horizon}.json")

	def scenario_network_path(self, scenario_id: str) -> Path | None:
		"""The base network a what-if solve varies, or ``None`` when absent.

		The catalogue publishes the network beside the record
		(``alea.planning.catalogue``), because a scenario that records a network
		checksum and no network is a scenario whose base cannot be re-solved.
		Returned as a path rather than a loaded network: Layer 5's engine takes a
		path, and loading a network to hand it on would put a live object across
		the seam AD-4 forbids.
		"""
		path = resolve(f"{self._scenario_dir(scenario_id)}/network.nc")
		return path if path.exists() else None

	# -- market ------------------------------------------------------------

	def prices(self, *, country: str | None = None) -> list[PriceRowOut]:
		"""Wholesale prices, optionally for one country."""
		read = self._table("data/processed/market/prices.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		return [
			PriceRowOut(
				at=_moment(row, "at"),
				country_iso=_text(row, "country_iso") or None,
				price=_value(row, "price", _text(row, "unit", "USD/MWh"), provenance),
			)
			for _, row in rows.iterrows()
		]

	def capture_rates(self, *, technology: str | None = None) -> list[CaptureRateRowOut]:
		"""Capture-rate curves, optionally for one technology."""
		read = self._table("data/processed/market/capture_rates.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, technology=technology)
		return [
			CaptureRateRowOut(
				technology=_text(row, "technology"),
				vre_penetration=_value(row, "vre_penetration", "fraction", provenance),
				capture_rate=_value(row, "capture_rate", "fraction", provenance),
				capture_price=_value(row, "capture_price", "USD/MWh", provenance),
			)
			for _, row in rows.iterrows()
		]

	def ppa_benchmarks(self, *, country: str | None = None) -> list[PpaBenchmarkRowOut]:
		"""PPA benchmarks, optionally for one country."""
		read = self._table("data/processed/market/ppa_benchmarks.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		return [
			PpaBenchmarkRowOut(
				technology=_text(row, "technology"),
				country_iso=_text(row, "country_iso") or None,
				ppa_price=_value(row, "ppa_price", "USD/MWh", provenance),
				tenor_years=int(_number(row, "tenor_years", 1)),
				benchmark_source=_text(row, "benchmark_source", "unspecified"),
			)
			for _, row in rows.iterrows()
		]

	# -- outages -----------------------------------------------------------

	def outage_forecasts(
		self, *, country: str | None = None, grid_zone: str | None = None, horizon_hours: int = 24
	) -> list[OutageForecastRowOut]:
		"""Outage forecasts for the requested horizon, most probable first."""
		read = self._table("data/processed/outages/forecast.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country, grid_zone=grid_zone)
		if "horizon_hours" in frame.columns:
			rows = rows[rows["horizon_hours"] == horizon_hours]
		out = [
			OutageForecastRowOut(
				country_iso=_text(row, "country_iso") or None,
				grid_zone=_text(row, "grid_zone"),
				probability=_value(row, "probability", "probability", provenance),
				horizon_hours=int(_number(row, "horizon_hours", horizon_hours)),
				issued_at=_moment(row, "issued_at"),
				model_version=_text(row, "model_version"),
			)
			for _, row in rows.iterrows()
		]
		# Ordered by probability descending so the USSD adapter's "top N" is a
		# prefix of this list and both adapters agree on which zones matter.
		out.sort(key=lambda forecast: forecast.probability.value, reverse=True)
		return out

	def outage_history(
		self, *, country: str | None = None, grid_zone: str | None = None
	) -> list[OutageHistoryRowOut]:
		"""Recorded outage events, most recent first."""
		read = self._table("data/processed/outages/history.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country, grid_zone=grid_zone)
		out = [
			OutageHistoryRowOut(
				event_id=_text(row, "event_id"),
				country_iso=_text(row, "country_iso") or None,
				grid_zone=_text(row, "grid_zone"),
				started_at=_moment(row, "started_at"),
				duration_minutes=_value(row, "duration_minutes", "minutes", provenance),
				customers_affected=_value(row, "customers_affected", "customers", provenance),
				cause=_text(row, "cause", "unknown"),
			)
			for _, row in rows.iterrows()
		]
		out.sort(key=lambda event: event.started_at, reverse=True)
		return out

	def outage_validation(self, *, country: str | None = None) -> list[OutageValidationRowOut]:
		"""Forecast-versus-observed accuracy. The rows that qualify an accuracy claim."""
		read = self._table("data/processed/outages/validation.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		return [
			OutageValidationRowOut(
				country_iso=_text(row, "country_iso") or None,
				grid_zone=_text(row, "grid_zone"),
				period_start=_moment(row, "period_start"),
				period_end=_moment(row, "period_end"),
				auc=_value(row, "auc", "AUC", provenance),
				precision=_value(row, "precision", "fraction", provenance),
				recall=_value(row, "recall", "fraction", provenance),
				sample_size=int(_number(row, "sample_size", 0)),
			)
			for _, row in rows.iterrows()
		]

	def maintenance_predictions(
		self, *, country: str | None = None, asset_type: str | None = None
	) -> list[MaintenancePredictionRowOut]:
		"""Predicted failures, most probable first."""
		read = self._table("data/processed/maintenance/predictions.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country, asset_type=asset_type)
		out = [
			MaintenancePredictionRowOut(
				asset_id=_text(row, "asset_id"),
				asset_type=_text(row, "asset_type"),
				country_iso=_text(row, "country_iso") or None,
				failure_probability=_value(row, "failure_probability", "probability", provenance),
				window_days=int(_number(row, "window_days", 30)),
				recommended_action=_text(row, "recommended_action"),
				model_version=_text(row, "model_version"),
			)
			for _, row in rows.iterrows()
		]
		out.sort(key=lambda prediction: prediction.failure_probability.value, reverse=True)
		return out

	# -- losses ------------------------------------------------------------

	def loss_decomposition(
		self, *, country: str, period_start: str | None = None, period_end: str | None = None
	) -> LossDecompositionOut | None:
		"""A country's loss decomposition, or ``None``.

		``period_start``/``period_end`` select among the decompositions published
		for that country. The route advertised both from the day it was written
		and this method read neither: it took ``rows.iloc[0]`` and returned
		whichever row happened to sort first, so a caller asking for 2020 got a
		2023 period with a 200 and nothing saying the period was ignored. A
		filter that names a period and returns another is worse than no filter.

		A period with no published decomposition returns ``None``, which the route
		turns into a 404 naming the country -- the same answer as a country with
		nothing published, because from the caller's side they are the same fact.
		"""
		assert country, "a loss decomposition is per country"
		read = self._table("data/processed/losses/decomposition.parquet")
		if read is None:
			return None
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		if rows.empty:
			return None
		if period_start is not None or period_end is not None:
			rows = _within_period(rows, period_start=period_start, period_end=period_end)
			if rows.empty:
				return None
		row = rows.iloc[0]
		components = [
			LossComponentOut(
				component=_text(component, "component"),
				loss=_value(component, "loss", "MWh", provenance),
				share=_value(component, "share", "fraction", provenance),
			)
			for _, component in _nested(row, "components")
		]
		return LossDecompositionOut(
			country_iso=country,
			period_start=_moment(row, "period_start"),
			period_end=_moment(row, "period_end"),
			total_loss=_value(row, "total_loss", "MWh", provenance),
			components=components,
		)

	def tlens(self, *, country: str | None = None, year: int | None = None) -> list[TlensRowOut]:
		"""T&D loss statistics by country-year."""
		read = self._table("data/processed/losses/tlens.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		if year is not None and "year" in frame.columns:
			rows = rows[rows["year"] == year]
		return [
			TlensRowOut(
				country_iso=_text(row, "country_iso") or None,
				year=int(_number(row, "year", 0)),
				transmission_loss_pct=_value(row, "transmission_loss_pct", "%", provenance),
				distribution_loss_pct=_value(row, "distribution_loss_pct", "%", provenance),
				collection_loss_pct=_value(row, "collection_loss_pct", "%", provenance),
				basis_note=_text(row, "basis_note"),
			)
			for _, row in rows.iterrows()
		]

	def mitigation_options(self, *, country: str) -> list[MitigationOptionOut]:
		"""Loss-mitigation interventions, best payback first."""
		assert country, "mitigation options are per country"
		read = self._table("data/processed/losses/mitigation.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		out = [
			MitigationOptionOut(
				option=_text(row, "option"),
				loss_reduction=_value(row, "loss_reduction", "MWh", provenance),
				capex=_value(row, "capex", "USD", provenance),
				payback_years=_value(row, "payback_years", "years", provenance),
			)
			for _, row in rows.iterrows()
		]
		out.sort(key=lambda option: option.payback_years.value)
		return out

	# -- resilience --------------------------------------------------------

	def resilience_metrics(self, *, country: str | None = None) -> list[ResilienceMetricOut]:
		"""Resilience metrics by country."""
		read = self._table("data/processed/resilience/metrics.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		return [
			ResilienceMetricOut(
				metric=_text(row, "metric"),
				country_iso=_text(row, "country_iso") or None,
				value=_value(row, "value", _text(row, "unit", "index"), provenance),
				period=_text(row, "period"),
			)
			for _, row in rows.iterrows()
		]

	def contingency(self, *, country: str | None = None) -> list[ContingencyRowOut]:
		"""N-1 contingency results, worst first."""
		read = self._table("data/processed/resilience/contingency.parquet")
		if read is None:
			return []
		frame, provenance = read
		rows = _filter(frame, country_iso=country)
		out = [
			ContingencyRowOut(
				element_id=_text(row, "element_id"),
				element_type=_text(row, "element_type"),
				load_shed_mw=_value(row, "load_shed_mw", "MW", provenance),
				overloaded_elements=int(_number(row, "overloaded_elements", 0)),
				severity=_text(row, "severity", "unknown"),
			)
			for _, row in rows.iterrows()
		]
		out.sort(key=lambda contingency: contingency.load_shed_mw.value, reverse=True)
		return out

	# -- reports -----------------------------------------------------------

	def reports(self, cadence: str) -> list[ReportOut]:
		"""Reports of one cadence, newest first."""
		assert cadence, "a cadence is required"
		index = self._plain_json(f"reports/{cadence}/index.json")
		if index is None:
			return []
		entries = index.get("reports", [])
		out = [self._report_from_document(cadence, entry) for entry in entries]
		out.sort(key=lambda report: report.report_date, reverse=True)
		return out

	def report(self, cadence: str, report_date: str) -> ReportOut | None:
		"""One dated report, or ``None``."""
		document = self._document(f"reports/{cadence}/{report_date}.json")
		if document is None:
			return None
		data, provenance = document
		report = self._report_from_document(cadence, data)
		return report.model_copy(update={"provenance": _provenance_out(provenance)})

	def _report_from_document(self, cadence: str, data: dict[str, Any]) -> ReportOut:
		assert isinstance(data, dict), "a report entry is an object"
		report_date = _text(data, "report_date") or _text(data, "date")
		if not report_date:
			raise ArtefactError(f"a {cadence} report entry has no report_date")
		return ReportOut(
			cadence=_text(data, "cadence", cadence),
			report_date=report_date,
			title=_text(data, "title", f"{cadence} report {report_date}"),
			generated_at=cast(
				"datetime",
				pd.Timestamp(
					data.get("generated_at") or data.get("created_at") or report_date
				).to_pydatetime(),
			),
			checksum=_text(data, "checksum"),
			formats=[str(f) for f in data.get("formats", [])],
		)

	# -- registry ----------------------------------------------------------

	def countries(self) -> list[CountryOut]:
		"""Every AU member state."""
		from alea.registry import registry

		return [
			CountryOut(
				iso2=country.iso2 or "",
				iso3=country.iso3,
				name=country.name,
				power_pool=country.power_pool.value,
				completeness=country.completeness.value,
				population=country.population,
				needs_proxy_data=country.needs_proxy_data,
				notes=country.notes,
			)
			for country in registry().values()
		]

	def technologies(self) -> list:
		"""Every registered technology."""
		from alea.registry import co2_intensity, renewable_carriers, storage_carriers, technologies

		renewable = {carrier.value for carrier in renewable_carriers()}
		storage = {carrier.value for carrier in storage_carriers()}
		out = []
		for carrier, technology in technologies().items():
			try:
				intensity = co2_intensity(carrier)
			except (KeyError, ValueError):
				intensity = None
			out.append((carrier, technology, intensity, renewable, storage))
		return out


# --------------------------------------------------------------------------
# Frame helpers
# --------------------------------------------------------------------------


def _filter(frame: pd.DataFrame, **conditions: str | None) -> pd.DataFrame:
	"""Rows matching every non-``None`` condition.

	A condition on a column the frame does not carry is ignored rather than
	raising: an older artefact without the column is served for what it does
	have, and the caller sees the unfiltered set rather than a 500.
	"""
	assert frame is not None, "cannot filter no frame"
	rows: pd.DataFrame = frame
	for column, value in conditions.items():
		if value is None:
			continue
		if column not in rows.columns:
			continue
		# Boolean-masking a DataFrame always yields a DataFrame, but pandas'
		# stubs type ``__getitem__`` to return the union of everything it can
		# return, so the annotation has to say which branch this is.
		rows = cast("pd.DataFrame", rows[rows[column].astype(str).str.upper() == str(value).upper()])
	return rows


def _within_period(
	rows: pd.DataFrame, *, period_start: str | None, period_end: str | None
) -> pd.DataFrame:
	"""Rows whose period overlaps ``[period_start, period_end]``.

	Overlap, not containment: a decomposition published for calendar 2023
	overlaps a request for ``2023-06-01..2023-06-30``, and a containment test
	would drop it and report that no decomposition exists for a period squarely
	inside one. An unparseable bound is a caller error and raises rather than
	being dropped -- silently ignoring it is the defect this function replaces.

	A frame with no ``period_start`` column cannot be filtered, and returning
	it unfiltered would be the original defect wearing a guard; the caller gets
	every row and no way to tell. That case raises.
	"""
	for column in ("period_start", "period_end"):
		if column not in rows.columns:
			raise ArtefactError(
				f"a period was requested but the decomposition artefact has no "
				f"{column!r} column, so the filter cannot be applied"
			)
	starts = pd.to_datetime(rows["period_start"], errors="raise")
	ends = pd.to_datetime(rows["period_end"], errors="raise")
	selected = pd.Series(True, index=rows.index)
	if period_start is not None:
		selected &= ends >= pd.Timestamp(period_start)
	if period_end is not None:
		selected &= starts <= pd.Timestamp(period_end)
	return cast("pd.DataFrame", rows[selected])


def _nested(row: Any, column: str) -> list[dict[str, Any]]:
	"""A column holding a list of objects, or an empty list."""
	value = _optional(row, column)
	if value is None:
		return []
	if isinstance(value, str):
		value = json.loads(value)
	if isinstance(value, list):
		return [item for item in value if isinstance(item, dict)]
	return []


__all__ = ["NETWORK_DIR", "SCENARIO_INDEX", "ArtefactUnavailable", "Repository"]
