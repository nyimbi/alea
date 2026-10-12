# SPDX-License-Identifier: MIT
"""Projections: layer results as the serving tables the API reads.

Each projection is a pure function from a layer result to a DataFrame, plus
``project``, which checks the frame against its declared schema and writes it
with provenance. The split is deliberate: the pure half is what a test exercises
without a pipeline, and ``project`` is what a stage calls.

**No projection has a stage yet.** `UNWIRED` in `alea.publish.views` names every
table that is declared and unproduced, with the reason. A stage would read the
layer's artefact at a conventional path and call the projection; what is missing
is that conventional path. `tlens`, `resilience` and `outage_validation` read
six inputs under `paths.processed` that nothing writes and no rule invokes, so a
projection stage for the loss or resilience tables would have nothing to read.
Writing the stage against an input no producer creates would move the gap, not
close it -- and it would read as closed, which is worse.

**Uncertainty travels with the table, and it must be stated.** The repository
refuses to serve a modelled, forecast or proxy number whose uncertainty is zero
(`repository._value`), because a modelled number presented as exact is how a
proxy becomes a published fact. A layer's own provenance often carries
``uncertainty=0.0`` -- the layer is recording *what it computed*, not how wrong
it might be -- so the projection states one. ``DEFAULT_UNCERTAINTY`` is the
honest placeholder for "modelled, and this projection has no better estimate";
a projection that knows better passes its own.

That refusal is not an obstacle to route around. Wiring the artefacts without
stating an uncertainty would turn every loss and resilience route into a 500,
which is a different failure from the empty page it serves today and no better.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from alea.io.artefacts import write_artefact
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance
from alea.publish.views import PUBLISHED_TABLES, SERVING_SCHEMAS, serving_schema

logger = get_logger(__name__)

DEFAULT_UNCERTAINTY = 0.5
"""Relative uncertainty for a modelled table with no better estimate.

Deliberately large. A modelled loss figure whose error nobody has measured is
not a figure with a small error bar, and a projection that wrote ``0.0`` would
be claiming the model is exact -- which the repository refuses outright. Half is
a placeholder an operator can replace with a measured value; it is not a claim
that the number is half right.
"""


class PublishError(RuntimeError):
	"""A projection could not produce its table."""


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def _provenance(
	inputs: Sequence[str],
	parameters: Mapping[str, Any],
	*,
	source_id: str,
	notes: str,
	basis: Basis = Basis.MODELLED,
	uncertainty: float = DEFAULT_UNCERTAINTY,
	uncertainty_basis: str = "",
) -> DerivedProvenance:
	"""Provenance for a serving table.

	``inputs`` is never empty: an artefact whose traceability is a placeholder is
	the thing AD-6 exists to prevent, and ``DerivedProvenance`` refuses it. Where
	the upstream artefact carries a checksum it is passed through; where the
	projection is from an in-memory result the caller names what it came from.
	"""
	return DerivedProvenance(
		source_id=source_id,
		inputs=list(inputs) or ["<in-memory-layer-result>"],
		code_version=_code_version(),
		parameters=dict(parameters),
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis=uncertainty_basis
		or ("modelled, no measured error; placeholder uncertainty" if uncertainty > 0 else ""),
		notes=notes,
	)


def _code_version() -> str:
	from alea import __version__

	return __version__


# --------------------------------------------------------------------------
# Projections: layer result -> serving table
# --------------------------------------------------------------------------


def project_prices(
	prices: pd.DataFrame,
	*,
	countries: Mapping[str, str] | None = None,
) -> pd.DataFrame:
	"""A price series as ``(at, country_iso, price, unit)`` rows.

	``prices`` is ``(time, bus)`` -- the layer's marginal-price frame. A bus is
	not a country, so the projection needs the mapping and refuses without it:
	writing the bus name into ``country_iso`` would serve "Nairobi" where the
	model says ISO 3166-1 alpha-2, and a consumer filtering on ``KE`` would get
	nothing while the row sat there looking correct.
	"""
	assert isinstance(prices, pd.DataFrame), "prices must be a DataFrame"
	if prices.empty:
		return _empty("market_prices")
	if countries is None:
		raise PublishError(
			"project_prices needs a bus-to-country mapping; a marginal-price frame "
			"is per bus and country_iso is an ISO code, and writing one where the "
			"other belongs produces rows that filter to nothing"
		)
	missing = [str(bus) for bus in prices.columns if str(bus) not in countries]
	if missing:
		raise PublishError(
			f"{len(missing)} bus(es) have no country mapping, first: {missing[0]!r}; "
			f"a price row with no country is not servable"
		)
	long = prices.melt(ignore_index=False, var_name="bus", value_name="price").reset_index()
	long = long.rename(columns={long.columns[0]: "at"})
	# A comprehension rather than `Series.map(dict)`: `map` with a dict is a
	# lookup, but pandas-stubs types the argument as a callable, and the
	# `missing` check above already guarantees every value is a key.
	lookup = dict(countries)
	long["country_iso"] = [lookup[str(bus)] for bus in long["bus"]]
	long["unit"] = "USD/MWh"
	long = long.dropna(subset=["price"])
	return long.loc[:, ["at", "country_iso", "price", "unit"]].reset_index(drop=True)


def project_capture_rates(curve: Sequence[Any], *, technology: str) -> pd.DataFrame:
	"""A cannibalisation curve as capture-rate rows for one technology.

	``curve`` is a sequence of :class:`alea.market.views.CaptureCurvePoint`, whose
	``capture_rate`` is ``None`` where the carrier generated nothing. The row is
	written with a NaN rate rather than dropped: a gap in the curve is a finding,
	and a curve with its gaps removed reads as complete.

	The price is read as a declared attribute, not through a ``getattr`` with a
	``None`` default. The default was the defect: ``CaptureCurvePoint`` did not
	declare ``capture_price_usd_per_mwh``, so every row of the served table was
	NaN while the schema declared the column, the repository read it, and the
	route exposed it. A default that absorbs a missing field turns a rename into
	a silently empty column.
	"""
	assert technology, "a capture-rate row is per technology"
	if not curve:
		return _empty("market_capture_rates")
	rows = [
		{
			"technology": technology,
			"vre_penetration": float(point.vre_share),
			"capture_rate": _nan(point.capture_rate),
			"capture_price": _nan(point.capture_price_usd_per_mwh),
		}
		for point in curve
	]
	return pd.DataFrame(rows)


def project_ppa_benchmarks(benchmarks: Sequence[Any]) -> pd.DataFrame:
	"""PPA benchmarks as serving rows.

	``benchmark_source`` is the carrier's provenance source id, or a statement
	that the price is modelled. A benchmark with no stated source is a price a
	lender cannot check, and the column is what stops it being read as market
	data.
	"""
	if not benchmarks:
		return _empty("market_ppa_benchmarks")
	rows = []
	for benchmark in benchmarks:
		provenance = getattr(benchmark, "provenance", None)
		source = getattr(provenance, "source_id", "") if provenance is not None else ""
		rows.append(
			{
				"technology": str(benchmark.carrier),
				"country_iso": str(benchmark.country_iso),
				"ppa_price": float(benchmark.price_usd_per_mwh),
				"tenor_years": int(benchmark.tenor_years),
				"benchmark_source": source or "modelled capture price with credit and FX basis",
			}
		)
	return pd.DataFrame(rows)


def project_outage_forecast(
	probabilities: Mapping[str, float],
	*,
	country_iso: str,
	horizon_hours: int,
	issued_at: Any,
	model_version: str,
) -> pd.DataFrame:
	"""Zone probabilities as forecast rows.

	``probabilities`` maps a zone to its probability. The row keeps the
	probability as a number rather than a flag: a forecast that says "yes" and is
	60% right is worse than one that says 0.6 (09-layer6 §3.1).
	"""
	assert country_iso, "a forecast row names a country"
	assert horizon_hours > 0, "a horizon is a positive number of hours"
	if not probabilities:
		return _empty("outage_forecast")
	rows = [
		{
			"country_iso": country_iso,
			"grid_zone": str(zone),
			"probability": float(probability),
			"horizon_hours": int(horizon_hours),
			"issued_at": pd.Timestamp(issued_at),
			"model_version": model_version,
		}
		for zone, probability in probabilities.items()
	]
	return pd.DataFrame(rows)


def project_outage_history(events: Sequence[Any], *, country_iso: str) -> pd.DataFrame:
	"""Interruption events as history rows.

	Reuses the resilience layer's :class:`InterruptionEvent`, because an outage
	the history route serves and an outage SAIDI is computed from must be the
	same event. Two event models is two answers to "how long was the outage".
	"""
	assert country_iso, "a history row names a country"
	if not events:
		return _empty("outage_history")
	rows = [
		{
			"event_id": str(getattr(event, "event_id", "") or f"{event.zone}-{index}"),
			"country_iso": country_iso,
			"grid_zone": str(event.zone),
			"started_at": pd.Timestamp(event.started_at),
			"duration_minutes": float(event.duration_minutes),
			"customers_affected": float(getattr(event, "customers_interrupted", 0.0)),
			"cause": str(getattr(event, "cause", "") or "unknown"),
		}
		for index, event in enumerate(events)
	]
	return pd.DataFrame(rows)


def project_outage_validation(
	metrics: Any,
	*,
	country_iso: str,
	grid_zone: str,
	period_start: Any,
	period_end: Any,
) -> pd.DataFrame:
	"""Detection metrics as a validation row.

	The row is the one that keeps an ``[UNVERIFIED]`` accuracy figure from being
	published as established. ``auc`` is written with its ``sample_size`` beside
	it, because an AUC without the number of rows behind it is a number nobody
	can weigh.
	"""
	assert country_iso, "a validation row names a country"
	if metrics is None:
		return _empty("outage_validation")
	return pd.DataFrame(
		[
			{
				"country_iso": country_iso,
				"grid_zone": grid_zone,
				"period_start": pd.Timestamp(period_start),
				"period_end": pd.Timestamp(period_end),
				"auc": float(metrics.auc),
				"precision": float(metrics.precision),
				"recall": float(metrics.recall),
				"sample_size": int(metrics.n_total),
			}
		]
	)


def project_maintenance_predictions(
	predictions: Sequence[Mapping[str, Any]],
	*,
	model_version: str = "",
	window_days: int = 30,
) -> pd.DataFrame:
	"""Per-asset failure probabilities as prediction rows.

	``predictions`` is a sequence of ``{asset_id, asset_type, country_iso,
	failure_probability, recommended_action}``. A prediction is per asset; the
	layer's :class:`SurvivalSummary` is one hazard ratio per *feature*, which is a
	different object and is not a prediction for any asset. The caller supplies
	the per-asset rows because only it knows which assets were scored.
	"""
	if not predictions:
		return _empty("maintenance_predictions")
	rows = []
	for prediction in predictions:
		rows.append(
			{
				"asset_id": str(prediction["asset_id"]),
				"asset_type": str(prediction.get("asset_type", "unknown")),
				"country_iso": str(prediction.get("country_iso", "")),
				"failure_probability": float(prediction["failure_probability"]),
				"window_days": int(window_days),
				"recommended_action": str(prediction.get("recommended_action", "")),
				"model_version": model_version,
			}
		)
	return pd.DataFrame(rows)


def project_loss_decomposition(
	components: Any,
	*,
	country_iso: str,
	period_start: Any,
	period_end: Any,
) -> pd.DataFrame:
	"""A loss decomposition as one serving row.

	``components`` is :class:`alea.losses.views.LossComponents`, whose three parts
	sum to its total by construction. The parts are serialised into the row's
	``components`` JSON column with their shares, so a consumer reads the
	decomposition the model asserted rather than re-deriving one that might not
	sum.
	"""
	assert country_iso, "a decomposition is per country"
	if components is None:
		return _empty("losses_decomposition")
	shares = components.shares
	parts = [
		{
			"component": name,
			"loss": float(getattr(components, f"{name}_mwh")),
			"share": _nan(shares.get(name)),
		}
		for name in components.component_names()
	]
	return pd.DataFrame(
		[
			{
				"country_iso": country_iso,
				"period_start": pd.Timestamp(period_start),
				"period_end": pd.Timestamp(period_end),
				"total_loss": float(components.total_mwh),
				"components": json.dumps(parts),
			}
		]
	)


def project_loss_mitigation(results: Sequence[Any], *, country_iso: str) -> pd.DataFrame:
	"""Mitigation rankings as serving rows.

	``payback_years`` is ``None`` for an option whose savings are below the
	measurement floor, and is written as NaN rather than dropped or zeroed:
	``inf`` reads as "never", which is a different claim from "unmeasurable"
	(07-layer4 §7).
	"""
	assert country_iso, "mitigation options are per country"
	if not results:
		return _empty("losses_mitigation")
	rows = [
		{
			"country_iso": country_iso,
			"option": str(result.option),
			"loss_reduction": float(result.annual_loss_reduction_mwh),
			"capex": float(result.capex_usd),
			"payback_years": _nan(result.payback_years),
		}
		for result in results
	]
	return pd.DataFrame(rows)


def project_resilience_metrics(
	metrics: Any,
	*,
	country_iso: str,
	period: str = "",
) -> pd.DataFrame:
	"""The resilience metric set as long-form rows.

	:class:`ResilienceMetrics` is one wide record -- one row with a column per
	index. The serving table is long: one row per metric, because a consumer
	charting an index across countries wants to filter on ``metric``, and a wide
	table makes that a schema change per index added.

	``interruption_threshold_minutes`` is written as its own row. §8 makes the
	threshold config *because it changes the number*: two SAIDI figures at
	different thresholds are different quantities sharing a name, and a SAIDI row
	without its threshold is not comparable to any other.
	"""
	assert country_iso, "a resilience metric row names a country"
	if metrics is None:
		return _empty("resilience_metrics")
	entries: list[tuple[str, float, str]] = [
		("ENS", float(metrics.ens_mwh), "MWh"),
		("EENS", float(metrics.eens_mwh), "MWh"),
		("SAIDI", float(metrics.saidi_hours), "hours"),
		("SAIFI", float(metrics.saifi), "interruptions/customer"),
		("LNS", float(metrics.lns_mw), "MW"),
		("interruption_threshold", float(metrics.interruption_threshold_minutes), "minutes"),
		("customers_total", float(metrics.customers_total), "customers"),
	]
	rows = [
		{
			"metric": name,
			"country_iso": country_iso,
			"value": value,
			"unit": unit,
			"period": period,
		}
		for name, value, unit in entries
	]
	return pd.DataFrame(rows)


def project_resilience_contingency(
	results: Sequence[Any],
	*,
	country_iso: str,
	severity_thresholds: tuple[float, float] = (100.0, 10.0),
) -> pd.DataFrame:
	"""N-1 sweep results as per-element contingency rows.

	``results`` is a sequence of per-element records --
	``{element_id, element_type, load_shed_mw, overloaded_elements}``. The
	layer's :class:`ContingencySummary` is an *aggregate*: one worst-contingency
	index for the whole sweep, which names no element and is not a row any
	consumer can act on.

	``severity`` is banded here rather than in the layer because it is a
	presentation choice: the thresholds are a parameter, and a severity that
	lived in the model would be a threshold nobody could move.
	"""
	assert country_iso, "a contingency row names a country"
	if not results:
		return _empty("resilience_contingency")
	high, medium = severity_thresholds
	rows = []
	for result in results:
		shed = float(result["load_shed_mw"])
		severity = "high" if shed >= high else ("medium" if shed >= medium else "low")
		rows.append(
			{
				"element_id": str(result["element_id"]),
				"element_type": str(result.get("element_type", "line")),
				"country_iso": country_iso,
				"load_shed_mw": shed,
				"overloaded_elements": int(result.get("overloaded_elements", 0)),
				"severity": severity,
			}
		)
	return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def table_path(name: str, *, root: str | Path | None = None) -> Path:
	"""Where a projection's table is written.

	Read from :data:`alea.publish.views.PUBLISHED_TABLES`, which is also what the
	repository's path literals are checked against. A projection that computed its
	own path would write somewhere the API does not read and pass every test that
	only reads its return value.
	"""
	if name not in PUBLISHED_TABLES:
		raise KeyError(
			f"no published table {name!r}; declared: {', '.join(sorted(PUBLISHED_TABLES))}"
		)
	from alea.config.paths import resolve

	relative = PUBLISHED_TABLES[name]
	return resolve(relative) if root is None else Path(root) / relative


def project(
	name: str,
	frame: pd.DataFrame,
	out: str | Path,
	*,
	inputs: Sequence[str],
	parameters: Mapping[str, Any] | None = None,
	notes: str = "",
	basis: Basis = Basis.MODELLED,
	uncertainty: float = DEFAULT_UNCERTAINTY,
) -> tuple[str, pd.DataFrame]:
	"""Check ``frame`` against its schema and write it as a serving table.

	The schema check runs *before* the write, and it is the whole point of the
	package: a projection that dropped a column would otherwise write a table the
	repository reads as an empty page for that column, and a route serving zeros
	is a route that looks like it works.
	"""
	schema = serving_schema(name)
	checked = schema.check(frame, artefact=PUBLISHED_TABLES[name])
	provenance = _provenance(
		inputs,
		{**(parameters or {}), "rows": int(len(checked)), "columns": list(schema.names)},
		source_id=f"publish.{name}",
		notes=notes or f"{PUBLISHED_TABLES[name]} projected from the layer results",
		basis=basis,
		uncertainty=uncertainty,
	)
	checksum = write_artefact(Path(out), checked, provenance)
	logger.info("publish.written", table=name, rows=int(len(checked)), out=str(out))
	return checksum, checked


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _empty(name: str) -> pd.DataFrame:
	"""An empty frame carrying the schema's columns.

	Empty rather than absent: the repository serves an empty page for an absent
	artefact and for an empty one alike, and a written empty table records that
	the projection *ran* and found nothing -- which is a different fact from a
	projection that never ran.
	"""
	schema = SERVING_SCHEMAS[name]
	return pd.DataFrame({spec.name: pd.Series(dtype=_dtype(spec.dtype)) for spec in schema.columns})


def _dtype(dtype: str) -> str:
	return {"float": "float64", "int": "int64", "str": "object", "bool": "bool"}[dtype]


def _nan(value: Any) -> float:
	"""``value`` as a float, with ``None`` and non-finite values as NaN.

	A serving column is numeric; ``None`` in a float column is NaN by another
	name, and writing it as 0 would assert a measurement of zero where there is
	no measurement.
	"""
	if value is None:
		return float("nan")
	try:
		return float(value)
	except (TypeError, ValueError):
		return float("nan")


__all__ = [
	"DEFAULT_UNCERTAINTY",
	"PublishError",
	"project",
	"project_capture_rates",
	"project_loss_decomposition",
	"project_loss_mitigation",
	"project_maintenance_predictions",
	"project_outage_forecast",
	"project_outage_history",
	"project_outage_validation",
	"project_ppa_benchmarks",
	"project_prices",
	"project_resilience_contingency",
	"project_resilience_metrics",
	"table_path",
]
