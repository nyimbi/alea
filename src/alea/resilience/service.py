# SPDX-License-Identifier: MIT
"""Layer 4c orchestration — resilience metrics as artefacts.

The stage records three things a bare index does not: the interruption
threshold, the basis of the customer denominator, and the count of events
excluded as reclosures. Without them a SAIDI figure is a number that cannot be
compared to anything, including another ALEA run at a different threshold
(07-layer4 §8).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from alea.config.models import Config
from alea.io.pipeline import BuildContext, stage, write_stage
from alea.logging import get_logger, new_run_id
from alea.provenance.models import Basis, DerivedProvenance
from alea.resilience.metrics import compute_metrics, customers_from_population
from alea.resilience.views import (
	InterruptionEvent,
	ResilienceConfig,
	ResilienceMetrics,
	ScenarioEns,
	ZoneCustomers,
)

logger = get_logger(__name__)


def _code_version() -> str:
	from alea import __version__

	return __version__


def _provenance(
	inputs: Sequence[str],
	parameters: dict[str, Any],
	*,
	source_id: str,
	notes: str,
	basis: Basis = Basis.PROXY,
	uncertainty: float = 0.0,
	uncertainty_basis: str = "",
) -> DerivedProvenance:
	return DerivedProvenance(
		source_id=source_id,
		inputs=list(inputs) or ["<none-recorded>"],
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters=parameters,
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis=uncertainty_basis,
		notes=notes,
	)


def events_from_frame(frame: pd.DataFrame) -> list[InterruptionEvent]:
	"""Build interruption events from a dataframe.

	Requires ``zone``, ``started_at`` and ``duration_minutes``; ``load_mw``,
	``customers_interrupted`` and ``cause`` are optional. A row missing a
	required column raises rather than defaulting the duration to zero, which
	would silently delete an interruption from every index.
	"""
	required = ("zone", "started_at", "duration_minutes")
	missing = [column for column in required if column not in frame.columns]
	if missing:
		raise KeyError(f"interruption frame lacks {missing}")
	events: list[InterruptionEvent] = []
	for row in frame.to_dict(orient="records"):
		events.append(
			InterruptionEvent(
				zone=str(row["zone"]),
				started_at=pd.Timestamp(row["started_at"]).to_pydatetime(),
				duration_minutes=float(row["duration_minutes"]),
				load_mw=float(row.get("load_mw", 0.0) or 0.0),
				customers_interrupted=(
					float(row["customers_interrupted"])
					if row.get("customers_interrupted") is not None
					else None
				),
				cause=str(row.get("cause", "") or ""),
			)
		)
	return events


def customers_from_frame(frame: pd.DataFrame, config: ResilienceConfig | None = None) -> dict[str, ZoneCustomers]:
	"""Build zone customer counts from a population table, as proxies.

	``frame`` needs ``zone`` and ``population``; a ``n_customers`` column, when
	present, is used directly and labelled measured — a metered count is not a
	proxy and must not be degraded to one.
	"""
	cfg = config or ResilienceConfig()
	if "zone" not in frame.columns:
		raise KeyError("population frame needs a 'zone' column")
	out: dict[str, ZoneCustomers] = {}
	for row in frame.to_dict(orient="records"):
		zone = str(row["zone"])
		if row.get("n_customers") is not None:
			out[zone] = ZoneCustomers(
				zone=zone,
				n_customers=float(row["n_customers"]),
				basis=Basis.MEASURED,
				source=str(row.get("source", "metered")),
			)
			continue
		if row.get("population") is None:
			raise KeyError(
				f"zone {zone!r} has neither n_customers nor population; a "
				f"resilience index needs a denominator and inventing one is the "
				f"defect AD-8 forbids"
			)
		out[zone] = customers_from_population(zone, float(row["population"]), cfg)
	return out


def scenarios_from_frame(frame: pd.DataFrame) -> list[ScenarioEns]:
	"""Build scenario ENS entries. Probabilities must sum to 1.0; the model
	validates that when EENS is computed."""
	required = ("name", "probability", "ens_mwh")
	missing = [column for column in required if column not in frame.columns]
	if missing:
		raise KeyError(f"scenario frame lacks {missing}")
	return [
		ScenarioEns(
			name=str(row["name"]),
			probability=float(row["probability"]),
			ens_mwh=float(row["ens_mwh"]),
		)
		for row in frame.to_dict(orient="records")
	]


def resilience_to_artefact(
	events: Sequence[InterruptionEvent],
	customers: dict[str, float] | dict[str, ZoneCustomers],
	out: str | Path,
	config: ResilienceConfig | None = None,
	*,
	scenarios: Sequence[ScenarioEns] | None = None,
	scenario: str = "",
	inputs: Sequence[str] | None = None,
) -> tuple[str, ResilienceMetrics]:
	"""Compute the metric set and write it with its thresholds and bases.

	The provenance carries ``basis`` and ``uncertainty`` from the customer
	denominator, so a proxy-derived index is a proxy all the way to a report
	(AD-6, gate ``test_saidi_proxy_flagged``).
	"""
	cfg = config or ResilienceConfig()
	metrics = compute_metrics(events, customers, cfg, scenarios=scenarios, scenario=scenario)
	provenance = _provenance(
		inputs if inputs is not None else [],
		{
			"interruption_threshold_minutes": cfg.interruption_threshold_minutes,
			"customers_basis": metrics.customers_basis.value,
			"customers_total": metrics.customers_total,
			"n_events": metrics.n_events,
			"n_events_below_threshold": metrics.n_events_below_threshold,
			"scenario": scenario,
		},
		source_id="resilience_metrics",
		notes=metrics.notes,
		basis=metrics.customers_basis,
		uncertainty=metrics.customers_uncertainty,
		uncertainty_basis=(
			"population-derived customer denominator"
			if metrics.customers_are_proxy
			else ""
		),
	)
	checksum = write_stage(
		Path(out), metrics.model_dump(mode="json"), provenance, format="json"
	)
	return checksum, metrics


def system_alerts_rows(serving: pd.DataFrame) -> tuple[list[dict[str, Any]], int]:
	"""The daily ``system_alerts`` section's rows, from the serving table.

	`reporting/daily.py`'s ``system_alerts`` declares
	``["Element", "State", "Basis"]`` and reads
	``outages/contingency/{date}.parquet``. The per-element rows already exist --
	``@stage("resilience_contingency")`` sweeps the solved network and writes
	``data/processed/resilience/contingency.parquet`` -- so this renames the
	serving columns to the section's rather than re-sweeping. A second sweep
	would be a second computation of the same numbers, and the two would drift
	the moment either shape changed.

	**Why the band is read and not recomputed.** ``severity`` is banded in
	`publish.service.project_resilience_contingency` against thresholds that are
	a parameter there. Re-banding here would be a second copy of the same
	thresholds, kept in step by hand.

	**Why a non-finite load shed is refused.** ``load_shed_mw`` is NaN for a
	branch whose every snapshot diverged, and every comparison against NaN is
	``False`` -- so the serving projection bands such a branch ``"low"``, which
	asserts *no impact* where the truth is *not computable*. That is the one
	band this reader cannot carry through: the section's ``State`` is a claim
	about the element, and "low" is a claim. The rows are dropped and counted,
	and the count reaches the artefact's provenance, so a sweep that diverged
	everywhere reports itself rather than a table of low-severity alerts.
	"""
	if not isinstance(serving, pd.DataFrame):
		raise ValueError("the contingency serving table must be a DataFrame")
	required = {"element_id", "load_shed_mw", "severity"}
	missing = sorted(required - set(serving.columns))
	if missing:
		raise ValueError(
			f"the contingency serving table carries {sorted(serving.columns)} and "
			f"the section needs {missing}; `RESILIENCE_CONTINGENCY` declares all "
			f"three, so an artefact without them was not written by the stage that "
			f"serves it"
		)
	rows: list[dict[str, Any]] = []
	uncomputable = 0
	for record in serving.to_dict("records"):
		shed = float(record["load_shed_mw"])
		if not math.isfinite(shed):
			uncomputable += 1
			continue
		rows.append(
			{
				"label": str(record["element_id"]),
				"value": shed,
				"unit": "MW",
				"state": str(record["severity"]),
			}
		)
	return rows, uncomputable


def system_alerts_to_artefact(
	serving: pd.DataFrame,
	out: str | Path,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
	"""Write the section's frame from the serving table, with its provenance.

	The frame is what ``_rows_for`` binds: ``label`` is the first column's
	identity, ``value``/``unit`` the primary, and ``state`` the *text* column the
	section declares a category -- which is why it is written as a string and not
	as the load shed under another name. ``unit`` is ``MW`` because the section
	declares no unit of its own and ``values_from_artefact`` therefore takes the
	row's.
	"""
	rows, uncomputable = system_alerts_rows(serving)
	frame = pd.DataFrame(rows, columns=["label", "value", "unit", "state"])
	provenance = _provenance(
		inputs if inputs is not None else [],
		{
			"n_elements": len(rows),
			"n_uncomputable": uncomputable,
			"source": "data/processed/resilience/contingency.parquet",
		},
		source_id="system_alerts",
		notes=(
			"per-element contingency states, renamed from the serving table's "
			"columns to the daily section's -- `element_id` to the label, "
			"`severity` to `state`. The band is read from the serving projection "
			"rather than recomputed, so one threshold set decides it. A row whose "
			"`load_shed_mw` is not finite is dropped and counted: every comparison "
			"against NaN is False, so the serving band calls such a branch `low`, "
			"and `low` is a claim about the element that the sweep did not make."
		),
		basis=Basis.MODELLED,
	)
	checksum = write_stage(Path(out), frame, provenance, format="parquet")
	return checksum, rows


@stage("system_alerts")
def _stage_system_alerts(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: the daily contingency section, from the serving table.

	Reads the path ``PUBLISHED_TABLES`` declares rather than re-sweeping the
	network, so the report and the API's contingency route cannot come to
	disagree about which elements are critical. A missing serving table raises:
	an empty alerts table reads as "no element is critical", which is a claim
	about the network, while the truth is that no sweep ran.
	"""
	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact, read_provenance, sha256_file
	from alea.io.pipeline import skip_if_current
	from alea.publish.views import PUBLISHED_TABLES

	# The path `PUBLISHED_TABLES` declares, under *this config's* processed
	# directory. Reading the register rather than spelling the path keeps one
	# source of truth for where the serving table lives; resolving it against the
	# config rather than the repository root keeps the stage honest under a
	# scratch tree, which is what every test of it runs in.
	published = Path(PUBLISHED_TABLES["resilience_contingency"])
	processed = resolve(config.paths.processed)
	source = processed / published.relative_to("data/processed")
	if not source.exists():
		raise ArtefactError(
			f"no contingency serving table at {source}; `system_alerts` reports the "
			f"per-element states the N-1 sweep found, and a table written without "
			f"one would say no element is critical"
		)

	# The serving table's own digest, so a re-sweep re-runs this stage. It is a
	# resolved input rather than a declared one for the same reason
	# `@stage("network_arrays")` resolves the newest network: the path is
	# `PUBLISHED_TABLES`'s and no rule can name it at parse time without
	# restating that register.
	digest = sha256_file(source)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="system_alerts", logger=context.logger)
	if existing is not None:
		return existing

	serving, _ = read_artefact(source)
	_, rows = system_alerts_to_artefact(serving, out, inputs=inputs)
	logger.info(
		"resilience.stage.system_alerts",
		elements=len(rows),
		source=str(source),
		out=str(out),
	)
	return read_provenance(out)


@stage("resilience")
def _stage_resilience(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: resilience metrics from conventional processed paths.

	Reads an interruption-event table and a population table under
	``paths.processed``. A missing interruption table raises: an empty event
	list would produce every index as zero, which reads as perfect reliability
	rather than as absent data.
	"""
	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact

	processed = resolve(config.paths.processed)
	events_path = processed / "interruptions.parquet"
	population_path = processed / "zone_population.parquet"
	scenario_path = processed / "scenario_ens.parquet"

	if not events_path.exists():
		raise ArtefactError(
			f"no interruption events at {events_path}; every resilience index "
			f"would be zero, which reads as perfect reliability"
		)
	if not population_path.exists():
		raise ArtefactError(
			f"no zone population at {population_path}; the customer denominator "
			f"is required and inventing one is the defect AD-8 forbids"
		)

	event_frame, _ = read_artefact(events_path)
	population_frame, _ = read_artefact(population_path)
	events = events_from_frame(pd.DataFrame(event_frame))
	customers = customers_from_frame(pd.DataFrame(population_frame))
	scenarios = None
	if scenario_path.exists():
		scenarios = scenarios_from_frame(pd.DataFrame(read_artefact(scenario_path)[0]))

	# The configured section, not a bare `ResilienceConfig()`. §8 makes the
	# interruption threshold config precisely because it changes the number:
	# a 30-second reclosure is not an interruption, and two SAIDI figures at
	# different thresholds are different quantities sharing a name. Constructing
	# the defaults here made the threshold a constant the operator could not move
	# while the provenance recorded it as though it were the run's parameter.
	_, metrics = resilience_to_artefact(
		events,
		customers,
		out,
		config.resilience,
		scenarios=scenarios,
		inputs=context.inputs,
	)
	logger.info(
		"resilience.stage",
		ens_mwh=metrics.ens_mwh,
		saidi_hours=metrics.saidi_hours,
		customers_basis=metrics.customers_basis.value,
	)
	return _provenance(
		context.inputs,
		{
			"interruption_threshold_minutes": metrics.interruption_threshold_minutes,
			"customers_basis": metrics.customers_basis.value,
		},
		source_id="resilience_metrics",
		notes=metrics.notes,
		basis=metrics.customers_basis,
		uncertainty=metrics.customers_uncertainty,
		uncertainty_basis=(
			"population-derived customer denominator" if metrics.customers_are_proxy else ""
		),
	)


__all__ = [
	"customers_from_frame",
	"events_from_frame",
	"resilience_to_artefact",
	"scenarios_from_frame",
	"system_alerts_rows",
	"system_alerts_to_artefact",
]
