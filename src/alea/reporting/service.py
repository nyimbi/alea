# SPDX-License-Identifier: MIT
"""Report assembly, rendering, and the drift gate.

This module computes nothing. It reads the artefacts a cadence's sections
declare, mints a :class:`ReportValue` for each row from the artefact's own
provenance, and hands the result to the renderer. A section whose artefact is
absent is either a hard failure (a required section) or a stated omission
printed in the report's warnings -- never a zero and never a neighbour's
value.

``build_report`` is the one entry point the CLI and the scheduler both call,
which is what makes the two paths produce the same report: a scheduled-only
report cannot be backfilled, and backfill is required for the "actual versus
forecast" comparison the monthly cadence makes.

**The artefact contract, stated once.** A section declares its columns as
headers -- ``["Line", "Peak loading", "Hours", "Basis"]`` -- and a producer
writes one row per element with a ``value`` column, a ``unit`` and a ``label``,
plus a column for every *other* quantity the section names. ``_rows_for`` binds
each numeric column to the quantity whose name it matches, so ``Hours`` reads
the artefact's ``hours`` column and not a copy of the loading. A section whose
column names a quantity the row does not carry raises rather than repeating the
primary into it: this is the one place the report can put a wrong number in a
cell that looks right, and before the binding existed it did, in fourteen of the
thirty-one declared sections.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from alea.config.models import Config, ReportingConfig
from alea.config.paths import resolve
from alea.logging import get_logger
from alea.reporting.assemble import values_from_artefact
from alea.reporting.render import (
	drift_is_clean,
	drift_report,
	html_checksums,
	missing_or_empty_pdfs,
	render_report,
	report_filename,
	write_delivery_record,
)
from alea.reporting.schemas import (
	DataWindow,
	ReportCadence,
	ReportChart,
	ReportContext,
	ReportDataError,
	ReportSection,
	ReportTable,
	ReportValue,
	UnverifiedClaim,
	_normalise_column,
	period_for,
)

logger = get_logger(__name__)

UNVERIFIED_TOKEN = "[UNVERIFIED]"
"""The literal that must never appear in a published report.

A figure is either confirmed or it is printed with its status; the token is
the marker of a figure someone pasted in from a document that had not checked
it. See 00-architecture §9 and 12-quality §6.
"""


class ConfigError(Exception):
	"""Configuration is unusable for reporting."""


@dataclass(frozen=True)
class SectionSpec:
	"""One section's declaration: what it is called and where its data lives."""

	slug: str
	title: str
	artefact: str
	unit: str = ""
	prose: str = ""
	columns: list[str] = field(default_factory=lambda: ["Item", "Value", "Basis"])
	categorical: tuple[str, ...] = ()
	"""Headers that name a *category* rather than a quantity.

	Empty for every section but two. `daily.py`'s ``system_alerts`` declares a
	``State`` and `weekly.py`'s ``mitigation`` a ``Status``, and both are bands
	-- ``"high"``/``"medium"``/``"low"``, ``"open"``/``"closed"`` -- which
	`publish.views.RESILIENCE_CONTINGENCY` types ``str``.

	**Why this is declared rather than inferred.** ``_rows_for`` binds every
	non-first column to a number, and it has one fallback: a section with
	exactly one numeric column takes the primary whatever the header is called.
	That fallback is load-bearing -- ``market_outlook`` declares
	``["Quarter", "Price", "Basis"]`` and its producer writes ``value``/``unit``
	with no ``price`` column -- so the reader cannot drop it. But it also means
	a section declaring a category and receiving a frame with no such column
	prints the *primary* under the category's header: measured, a contingency
	frame with no ``state`` column rendered its load shed under ``State``. A
	header alone cannot tell ``Price`` from ``Status``; only the section can say
	which it meant, so it does.
	"""
	table_title: str = ""
	chart: str = ""
	required: bool = False


@dataclass(frozen=True)
class DataWindowSpec:
	"""A source's coverage lag, declared by a cadence."""

	source_id: str
	lag_days: int = 0
	note: str = ""


class DeliveryResult(BaseModel):
	"""One delivery attempt.

	Every distribution writes one of these. A report that was generated but
	not delivered is a report that was not published, and the platform must be
	able to say which. ``skipped`` is a real outcome, not an error: a missed
	schedule run writes it so the gap is visible rather than silent.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	channel: str
	recipients: list[str] = Field(default_factory=list)
	sent_at: datetime
	status: Literal["sent", "failed", "skipped"]
	detail: str = ""
	report_id: str = ""
	cadence: str = ""
	artefacts: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class BuildResult:
	"""What one report build produced."""

	cadence: str
	report_id: str
	as_of: date
	context: ReportContext
	paths: dict[str, Path]
	deliveries: list[DeliveryResult]
	warnings: list[str]
	duration_seconds: float

	@property
	def path(self) -> Path:
		"""The HTML path, which is the report's source of truth."""
		return self.paths.get("html") or next(iter(self.paths.values()))

	@property
	def delivered(self) -> bool:
		return any(delivery.status == "sent" for delivery in self.deliveries)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def validate_reporting_config(config: Config) -> ReportingConfig:
	"""Check the reporting configuration before a report is due.

	The email channel's own model already fails at load when SMTP is
	incomplete (``ReportingConfig._email_needs_configuration``). This adds the
	check that cannot live in the model because it needs the filesystem: the
	reports root must be writable. Both run at load time, not at 06:00.
	"""
	reporting = config.reporting
	if reporting.enabled:
		root = resolve(config.paths.reports)
		root.mkdir(parents=True, exist_ok=True)
		if not root.is_dir():
			raise ConfigError(f"reports root {root} is not a directory")
	if reporting.email_enabled and not (reporting.smtp_host and reporting.email_from):
		raise ConfigError(
			"email_enabled requires smtp_host and email_from; configuration is "
			"validated at load, not at send time"
		)
	return reporting


def cadence_specs(cadence: ReportCadence) -> tuple[list[SectionSpec], list[DataWindowSpec]]:
	"""The sections and windows a cadence declares."""
	module = _cadence_module(cadence)
	return list(module.SECTIONS), list(module.WINDOWS)


def cadence_unverified(cadence: ReportCadence) -> list[UnverifiedClaim]:
	"""Unconfirmed figures a cadence carries. Only the annual report has any."""
	module = _cadence_module(cadence)
	return list(getattr(module, "UNVERIFIED", ()))


def _cadence_module(cadence: ReportCadence) -> Any:
	from alea.reporting import annual, daily, monthly, quarterly, weekly

	modules = {
		ReportCadence.DAILY: daily,
		ReportCadence.WEEKLY: weekly,
		ReportCadence.MONTHLY: monthly,
		ReportCadence.QUARTERLY: quarterly,
		ReportCadence.ANNUAL: annual,
	}
	return modules[cadence]


def _artefact_path(spec: SectionSpec, config: Config, as_of: date) -> Path:
	"""Resolve a section's artefact path for a report date.

	The template tokens ``{date}`` and ``{month}`` make a monthly section read
	the month-end artefact while a daily section reads the day's.
	"""
	return section_artefact_path(spec, config, as_of)


def section_artefact_path(spec: SectionSpec, config: Config, as_of: date) -> Path:
	"""Where a section's artefact lives for a report dated ``as_of``.

	Public because a *projection* has to write exactly here. This is the only
	place the template tokens are expanded, so a projection that formatted the
	path itself would be a second copy of the convention -- and the failure it
	produces is invisible from either side: the producer passes its own tests
	(it wrote the file it was told to), the reader reports the section absent
	(it looked where the section declares), and the register says the section
	is produced. Measured 2026-10-13: `capacity_update`'s rule wrote
	``data/processed/capacity_update.parquet``, the monthly section read
	``results/planning/capacity/{date}.parquet``, and `alea report monthly`
	exited 1 with ``ReportDataError: no artefact``.

	``as_of`` is the report's own date, not the day the projection ran, and for
	a section whose period ends before its issue date the caller wants the
	*period end* -- ``period_for(cadence, as_of)[1]``. The reader does the same
	substitution, which is why passing the report date here and there agrees.
	"""
	pattern = spec.artefact.format(
		date=f"{as_of:%Y-%m-%d}",
		month=f"{as_of:%Y-%m}",
		year=f"{as_of:%Y}",
	)
	return resolve(Path(config.paths.results) / pattern)


def section_by_slug(cadence: ReportCadence, slug: str) -> SectionSpec:
	"""One section's declaration, refused if the cadence no longer declares it.

	A projection needs the section's declared ``artefact``, ``unit`` and
	``columns``, and looking them up by a slug spelled in the caller is how a
	projection comes to write a path no section declares. Raising here rather
	than returning ``None`` keeps that a failure at the writer instead of an
	absent section at the reader.
	"""
	specs, _ = cadence_specs(cadence)
	by_slug = {spec.slug: spec for spec in specs}
	if slug not in by_slug:
		raise ReportDataError(
			f"the {cadence.value} cadence declares no section {slug!r}; it declares "
			f"{sorted(by_slug)}"
		)
	return by_slug[slug]


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def _section_from_spec(
	spec: SectionSpec,
	config: Config,
	as_of: date,
	warnings: list[str],
) -> ReportSection | None:
	"""Build one section, or return ``None`` and record why.

	A required section that is absent raises. An optional one that is absent
	produces a warning line and no section -- a report that silently omits a
	section is a report a reader trusts for coverage it does not have.
	"""
	path = _artefact_path(spec, config, as_of)
	if not path.exists():
		message = f"{spec.title}: no artefact at {path} for {as_of:%Y-%m-%d}"
		if spec.required:
			raise ReportDataError(message)
		warnings.append(message)
		logger.info("report.section.absent", section=spec.slug, path=str(path))
		return None

	try:
		values = values_from_artefact(path, unit=spec.unit)
	except ReportDataError as exc:
		message = f"{spec.title}: {exc}"
		if spec.required:
			raise ReportDataError(message) from exc
		warnings.append(message)
		return None

	if not values:
		message = f"{spec.title}: artefact at {path} holds no rows"
		if spec.required:
			raise ReportDataError(message)
		warnings.append(message)
		return None

	table = ReportTable(
		slug=spec.slug,
		title=spec.table_title or spec.title,
		columns=spec.columns,
		rows=_rows_for(values, spec.columns, slug=spec.slug, categorical=spec.categorical),
		unit=spec.unit,
	)
	charts: list[ReportChart] = []
	if spec.chart:
		charts.append(
			ReportChart(
				slug=spec.slug,
				title=spec.table_title or spec.title,
				values=values,
				unit=spec.unit,
				kind=spec.chart,
			)
		)
	return ReportSection(
		slug=spec.slug,
		title=spec.title,
		prose=spec.prose,
		values=values,
		tables=[table],
		charts=charts,
	)


def _rows_for(
	values: list[ReportValue],
	columns: list[str],
	*,
	slug: str = "",
	categorical: tuple[str, ...] = (),
) -> list[list[ReportValue | str]]:
	"""Lay values out against a section's declared columns.

	A section declares its columns as headers -- ``["Line", "Peak loading",
	"Hours", "Basis"]`` -- and each value is one row of the artefact. The label
	column takes the value's label; ``Basis`` takes its basis and ``Interval``
	its interval; a numeric column takes the quantity it *names*.

	**The name is the binding, and the refusal is the point.** This used to
	write the value into every numeric column, so ``Peak loading`` and ``Hours``
	both printed the loading, ``Demand``/``Renewable``/``Margin`` all printed
	the demand, and SAIDI printed under SAIFI. Fourteen of the thirty-one
	declared sections have more than one numeric column and every one of them
	was wrong, in a published report, silently -- nothing failed because the
	fixtures were written to feed exactly one value per row, which is the shape
	the reader needed rather than the shape a producer writes. A section whose
	numeric column names a quantity the value does not carry raises here rather
	than repeating the primary into it: a cell that repeats its neighbour is a
	number a reader will quote, and no downstream check can tell it from a real
	one.
	"""
	declared_categories = {
		_normalise_column(name) for name in (categorical or ())
	}
	rows: list[list[ReportValue | str]] = []
	for value in values:
		row: list[ReportValue | str] = []
		for position, column in enumerate(columns):
			lowered = column.lower()
			if lowered in ("basis", "source"):
				row.append(value.basis.value)
			elif lowered in ("interval", "ci"):
				row.append(value.interval_text)
			elif position == 0:
				# The first column is the row's identity, not one of its
				# quantities: a label, never a second copy of the value.
				row.append(value.label or value.formatted)
			else:
				extra = value.extra_for(column)
				if extra is not None:
					row.append(
						ReportValue(
							value=extra,
							unit=value.unit,
							provenance=value.provenance,
							label=column,
						)
					)
					continue
				# A *text* column, where the row carries one under this name.
				# `system_alerts` declares a `State` and `mitigation` a
				# `Status`; both are categories, and a category is a plain
				# string cell -- the template's `cell` macro prints a string
				# as-is and a `ReportValue` with its basis marker. Tried after
				# `extra_for` so a column carrying a number is read as one.
				category = value.category_for(column)
				if category is not None:
					row.append(category)
					continue
				# A header the section declares as a category, with no text in
				# the row to fill it. Refused rather than handed the primary:
				# the single-numeric-column fallback below would otherwise
				# print the row's quantity under a header promising a band,
				# which is the duplication defect `_rows_for` exists to stop,
				# one column type over.
				if _normalise_column(column) in declared_categories:
					raise ReportDataError(
						f"{slug or 'section'}: column {column!r} is declared a "
						f"category and this row carries no such text; the row "
						f"holds {[key for key, _ in value.categories] or 'no text columns'}. "
						f"A quantity printed under a category's header is a wrong "
						f"cell in a published report"
					)
				# The primary goes only where the column names it. A column
				# naming a quantity this row does not carry has no cell, and
				# inventing one is how the duplication above happened.
				if _normalise_column(column) == _normalise_column(value.unit) or (
					len(_numeric_columns(columns)) == 1
				):
					row.append(value)
					continue
				raise ReportDataError(
					f"{slug or 'section'}: column {column!r} names a quantity this "
					f"row does not carry; the row holds {value.unit!r} and "
					f"{[key for key, _ in value.extra] or 'nothing else'}. A cell "
					f"that repeats the primary into a column it does not belong to "
					f"is a wrong number in a published report"
				)
		rows.append(row)
	return rows


def _numeric_columns(columns: list[str]) -> list[str]:
	"""A section's columns that carry a quantity rather than a label or a basis."""
	return [
		column
		for column in columns[1:]
		if column.lower() not in ("basis", "source", "interval", "ci")
	]


def assemble_context(
	cadence: ReportCadence,
	config: Config,
	*,
	as_of: date | None = None,
	run_id: str = "",
) -> ReportContext:
	"""Assemble a cadence's context from the layers below.

	Raises :class:`ReportDataError` when a required section's input is absent.
	It never substitutes a value.
	"""
	as_of = as_of or datetime.now(UTC).date()
	period_start, period_end = period_for(cadence, as_of)
	specs, windows = cadence_specs(cadence)

	warnings: list[str] = []
	sections: list[ReportSection] = []
	for spec in specs:
		section = _section_from_spec(spec, config, period_end, warnings)
		if section is not None:
			sections.append(section)

	context = ReportContext(
		title=_title(cadence, config, as_of),
		cadence=cadence,
		as_of=as_of,
		period_start=period_start,
		period_end=period_end,
		generated_at=datetime.now(UTC),
		timezone=config.reporting.timezone,
		sections=sections,
		run_id=run_id,
		countries=[str(c) for c in config.scenario.countries],
		warnings=warnings,
		data_windows=[
			DataWindow(
				source_id=window.source_id,
				coverage_start=datetime.combine(period_start, datetime.min.time(), tzinfo=UTC)
				- timedelta(days=window.lag_days),
				coverage_end=datetime.combine(period_end, datetime.min.time(), tzinfo=UTC)
				- timedelta(days=window.lag_days),
				latency_hours=window.lag_days * 24.0,
				note=window.note,
			)
			for window in windows
		],
		unverified=cadence_unverified(cadence),
	)
	assert context.sections, "a report with no sections is not a report"
	return context


def _title(cadence: ReportCadence, config: Config, as_of: date) -> str:
	label = {
		ReportCadence.DAILY: "Daily",
		ReportCadence.WEEKLY: "Weekly",
		ReportCadence.MONTHLY: "Monthly",
		ReportCadence.QUARTERLY: "Quarterly",
		ReportCadence.ANNUAL: "Annual",
	}[cadence]
	countries = ", ".join(str(c) for c in config.scenario.countries)
	return f"ALEA {label} Report — {countries}"


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def record_delivery(
	channel: str,
	recipients: list[str],
	status: Literal["sent", "failed", "skipped"],
	*,
	report_id: str = "",
	cadence: str = "",
	detail: str = "",
	artefacts: list[str] | None = None,
	directory: Path | None = None,
) -> DeliveryResult:
	"""Write a delivery record and return it.

	A delivery record is written for every outcome, including a skip. The
	record is the only thing that distinguishes "generated" from "delivered".
	"""
	result = DeliveryResult(
		channel=channel,
		recipients=recipients,
		sent_at=datetime.now(UTC),
		status=status,
		detail=detail,
		report_id=report_id,
		cadence=cadence,
		artefacts=artefacts or [],
	)
	if directory is not None:
		write_delivery_record(directory, result)
	logger.info(
		"report.delivery",
		channel=channel,
		status=status,
		recipients=len(recipients),
		report_id=report_id,
	)
	return result


def deliver_report(
	result: BuildResult,
	config: Config,
	*,
	delivery_dir: Path | None = None,
) -> list[DeliveryResult]:
	"""Deliver a built report over the configured channels.

	An email channel is the only channel the foundations configures. It is
	attempted only when ``email_enabled`` is set, and a failure is recorded as
	a failed delivery rather than raised -- a report that is built but whose
	send fails is still a report, and losing the artefact to an exception would
	hide the failure instead of recording it.
	"""
	reporting = validate_reporting_config(config)
	records: list[DeliveryResult] = []
	directory = delivery_dir or (result.path.parent / "deliveries")

	if reporting.email_enabled:
		records.append(_deliver_email(result, reporting, directory))
	else:
		records.append(
			record_delivery(
				"email",
				[],
				"skipped",
				report_id=result.report_id,
				cadence=result.cadence,
				detail="email_enabled is false; report generated but not sent",
				directory=directory,
			)
		)
	return records


def _deliver_email(
	result: BuildResult,
	reporting: ReportingConfig,
	directory: Path,
) -> DeliveryResult:
	"""Send the report by email, or record why it was not sent."""
	import os
	import smtplib
	from email.message import EmailMessage

	password = os.environ.get("SMTP_PASSWORD", "")
	if not password:
		# Recorded, not raised: an unset password at 06:00 is a failed
		# delivery, and the record is what makes it visible. Refusing to run
		# at all would leave no trace of the attempt.
		return record_delivery(
			"email",
			[],
			"failed",
			report_id=result.report_id,
			cadence=result.cadence,
			detail="SMTP_PASSWORD is not set in the environment",
			directory=directory,
		)

	message = EmailMessage()
	message["From"] = reporting.email_from
	message["Subject"] = f"{result.context.title} — {result.context.period_label}"
	message.set_content(
		f"{result.context.title}\n"
		f"Period: {result.context.period_label}\n"
		f"Report id: {result.report_id}\n"
		f"Generated: {result.context.generated_at:%Y-%m-%d %H:%M:%SZ}\n"
	)
	if "html" in result.paths:
		message.add_alternative(result.paths["html"].read_text(encoding="utf-8"), subtype="html")
	if "pdf" in result.paths:
		pdf = result.paths["pdf"]
		message.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)

	recipients = [reporting.email_from]
	try:
		with smtplib.SMTP(reporting.smtp_host, reporting.smtp_port, timeout=30) as client:
			client.starttls()
			if reporting.smtp_user:
				client.login(reporting.smtp_user, password)
			client.send_message(message)
	except (OSError, smtplib.SMTPException) as exc:
		return record_delivery(
			"email",
			recipients,
			"failed",
			report_id=result.report_id,
			cadence=result.cadence,
			detail=f"{type(exc).__name__}: {exc}",
			directory=directory,
		)
	return record_delivery(
		"email",
		recipients,
		"sent",
		report_id=result.report_id,
		cadence=result.cadence,
		detail=f"{reporting.smtp_host}:{reporting.smtp_port}",
		directory=directory,
	)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def build_report(
	cadence: str | ReportCadence,
	config: Config,
	out: str | Path | None = None,
	*,
	date: str | date | None = None,
	run_id: str = "",
	deliver: bool = True,
	formats: tuple[str, ...] | None = None,
) -> BuildResult:
	"""Build, render, and deliver one report.

	The scheduler and the CLI both call this, so a scheduled report and a
	backfilled one are the same artefact. That is a requirement, not a
	convenience: the monthly comparison reads a stored forecast, and a
	forecast can only be stored by regenerating the month it was issued for.
	"""
	started = datetime.now(UTC)
	kind = ReportCadence(cadence)
	reporting = validate_reporting_config(config)
	as_of_date = _as_date(date)
	output_dir = resolve(out or Path(config.paths.reports) / kind.value)

	context = assemble_context(kind, config, as_of=as_of_date, run_id=run_id)
	context = replace(context, report_id=report_id_for(kind.value, as_of_date))
	resolved_formats = formats or (("html", "pdf") if reporting.pdf_enabled else ("html",))

	stem = report_filename(kind.value, as_of_date)
	paths = render_report(
		kind.value,
		context,
		output_dir,
		formats=resolved_formats,
	)
	paths = {fmt: _rename(path, stem) for fmt, path in paths.items()}

	built = BuildResult(
		cadence=kind.value,
		report_id=context.report_id,
		as_of=as_of_date,
		context=context,
		paths=paths,
		deliveries=[],
		warnings=list(context.warnings),
		duration_seconds=(datetime.now(UTC) - started).total_seconds(),
	)
	if deliver:
		deliveries = deliver_report(built, config)
		built = _replace_deliveries(built, deliveries)

	# The API's report routes read `reports/<cadence>/index.json` and the dated
	# `<date>.json` document beside it (`alea.api.repository.reports`). Nothing
	# wrote either, so every report listing returned `total: 0` while the HTML
	# and PDF sat in the same directory. The index is a plain JSON file rather
	# than an artefact: a provenance sidecar on an index that describes
	# artefacts would be circular.
	_publish_index(built, output_dir)

	logger.info(
		"report.built",
		cadence=kind.value,
		report_id=built.report_id,
		as_of=str(as_of_date),
		values=len(context.values),
		proxies=len(context.proxied_values),
		seconds=round(built.duration_seconds, 2),
	)
	return built


def _publish_index(built: BuildResult, output_dir: Path) -> None:
	"""Write the dated document and update ``index.json`` for this cadence.

	The API reads these; a report a dashboard cannot list is a report nobody
	reads. ``checksum`` is the HTML's own hash, so a client can tell whether the
	rendered file changed without downloading it, and ``formats`` is what was
	actually written rather than what was requested -- a PDF that failed to
	render must not be advertised.
	"""
	import json

	formats = sorted(built.paths)
	document = {
		"cadence": built.cadence,
		"report_date": built.as_of.isoformat(),
		"title": f"{built.cadence.capitalize()} report {built.as_of.isoformat()}",
		"generated_at": datetime.now(UTC).isoformat(),
		"checksum": _file_checksum(built.path),
		"formats": formats,
		"report_id": built.report_id,
		"warnings": list(built.warnings),
	}
	output_dir.mkdir(parents=True, exist_ok=True)
	(output_dir / f"{built.as_of.isoformat()}.json").write_text(
		json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
	)

	index_path = output_dir / "index.json"
	entries: list[dict[str, Any]] = []
	if index_path.exists():
		existing = json.loads(index_path.read_text(encoding="utf-8"))
		if isinstance(existing, dict) and isinstance(existing.get("reports"), list):
			entries = [e for e in existing["reports"] if isinstance(e, dict)]
	# Re-rendering one date replaces its entry: the index lists reports, not
	# render runs, and two entries for one date would make the listing show the
	# same report twice.
	entries = [e for e in entries if e.get("report_date") != document["report_date"]]
	entries.append(document)
	entries.sort(key=lambda e: str(e.get("report_date", "")), reverse=True)
	index_path.write_text(
		json.dumps({"reports": entries}, indent=2, sort_keys=True), encoding="utf-8"
	)


def _file_checksum(path: Path) -> str:
	"""sha256 of a rendered file, or ``""`` when it is not there."""
	if not path.exists():
		return ""
	return hashlib.sha256(path.read_bytes()).hexdigest()


def _rename(path: Path, stem: str) -> Path:
	"""Give a rendered file its dated stem.

	The dated name is the artefact: a backfill must not overwrite the report
	of another date, and the drift gate hashes the dated files and nothing
	else. No undated alias is written, because a second copy of the same
	report under a second name is a second thing for the gate to drift over.
	"""
	target = path.with_name(f"{stem}{path.suffix}")
	if target != path:
		path.replace(target)
	return target


def _as_date(value: str | date | None) -> date:
	if value is None:
		return datetime.now(UTC).date()
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	try:
		return date.fromisoformat(value)
	except ValueError as exc:
		raise ReportDataError(f"unparseable report date {value!r}; expected ISO 8601") from exc


def _replace_deliveries(result: BuildResult, deliveries: list[DeliveryResult]) -> BuildResult:
	return replace(result, deliveries=deliveries)


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------


def find_unverified_token(context: ReportContext, rendered_html: str = "") -> list[str]:
	"""Occurrences of the ``[UNVERIFIED]`` token in a report's text.

	The gate that keeps AD-10's honesty rule enforceable. The token is
	searched for in the rendered HTML and in every string field of the
	context, because a report can carry it in prose as easily as in a table.
	"""
	found: list[str] = []
	if UNVERIFIED_TOKEN in rendered_html:
		found.append("rendered HTML")
	for section in context.sections:
		if UNVERIFIED_TOKEN in section.prose:
			found.append(f"section {section.slug} prose")
		for note in section.notes:
			if UNVERIFIED_TOKEN in note:
				found.append(f"section {section.slug} note")
		for table in section.tables:
			for row in table.rows:
				for cell in row:
					if isinstance(cell, str) and UNVERIFIED_TOKEN in cell:
						found.append(f"table {table.slug}")
	for warning in context.warnings:
		if UNVERIFIED_TOKEN in warning:
			found.append("warnings")
	return found


def check_report_gates(context: ReportContext, rendered_html: str = "") -> list[str]:
	"""Every checkable report invariant, as a list of failures.

	Returns an empty list when the report passes. The checks are the ones the
	plan names for this layer: no bare number, proxy values marked, precision
	respecting uncertainty, chart and table agreeing, and no unverified figure.
	"""
	from alea.reporting.schemas import (
		chart_table_disagreements,
		find_bare_numbers,
		repeated_table_cells,
	)

	problems: list[str] = []
	bare = find_bare_numbers(context)
	if bare:
		problems.append(f"bare numbers in context: {', '.join(bare[:5])}")
	problems.extend(chart_table_disagreements(context))
	problems.extend(repeated_table_cells(context))
	problems.extend(f"unverified figure: {where}" for where in find_unverified_token(context, rendered_html))

	for value in context.values:
		if value.basis.value != "measured" and not value.marker:
			problems.append(f"{value.label or 'value'}: basis {value.basis.value} has no marker")
		if value.uncertainty > 0 and value.figures > 2 and value.basis.value == "proxy":
			problems.append(
				f"{value.label or 'value'}: proxy with {value.uncertainty:.0%} "
				f"uncertainty renders {value.figures} significant figures"
			)
		if rendered_html and value.basis.value == "proxy" and (
			value.formatted not in rendered_html or value.marker not in rendered_html
		):
			# The HTML keeps the number and the marker in separate elements, so
			# the check is that both are present for this value, not that the
			# concatenation appears.
			problems.append(f"{value.label or 'value'}: proxy value not rendered with its marker")
	return problems


def drift_gate(
	root: str | Path,
	*,
	before: dict[str, str] | None = None,
	pattern: str = "**/*.html",
) -> dict[str, Any]:
	"""The report drift gate, scoped to HTML.

	Scoped to ``**/*.html`` under ``root``. The PDFs are written by a renderer
	that stamps each file with its own metadata, so two renders of an
	unchanged document differ by bytes and a gate that diffed them could never
	pass. The PDFs get the separate assertion that matters about them: each
	HTML has a non-empty PDF beside it.
	"""
	after = html_checksums(root, pattern=pattern)
	missing = missing_or_empty_pdfs(root, pattern=pattern)
	report = drift_report(before, after) if before is not None else {"added": [], "removed": [], "changed": []}
	return {
		"checksums": after,
		"drift": report,
		"drift_clean": drift_is_clean(report),
		"missing_pdfs": missing,
		"ok": drift_is_clean(report) and not missing,
	}


def report_id_for(cadence: str, as_of: date) -> str:
	"""A deterministic report id for a cadence and date.

	Deterministic rather than random so two generation paths produce the same
	id, which is what ``test_scheduled_matches_manual`` compares. The plan's
	UUID7 rule is for entity ids; a report id that changes on every run cannot
	be the key a delivery record joins on.
	"""
	digest = hashlib.sha256(f"{cadence}:{as_of:%Y-%m-%d}".encode()).hexdigest()
	# Shape it as a UUID so it is indistinguishable from a UUID7 in a record.
	return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def assert_no_unverified(rendered_html: str, context: ReportContext) -> None:
	"""Raise if a published report carries an unverified figure."""
	found = find_unverified_token(context, rendered_html)
	if found:
		raise ReportDataError(
			f"published report carries {UNVERIFIED_TOKEN} in: {', '.join(found)}; "
			f"a figure is either confirmed or printed with its status"
		)


def assert_drift_scope(pattern: str = "**/*.html") -> None:
	"""Assert the drift gate's jurisdiction is HTML and nothing else.

	The gate exists to catch a change to a rendered report. A pattern that
	also matches the PDFs would make it unstable, because the PDFs are stamped
	with render metadata; a pattern that matches nothing would make it vacuous.
	This is the check that the pattern it is called with owns exactly the HTML.
	"""
	if not pattern.endswith(".html"):
		raise ReportDataError(
			f"the drift gate is scoped to HTML only; pattern {pattern!r} would "
			f"cover files whose bytes are not reproducible"
		)


__all__ = [
	"UNVERIFIED_TOKEN",
	"BuildResult",
	"ConfigError",
	"DataWindowSpec",
	"DeliveryResult",
	"SectionSpec",
	"assert_drift_scope",
	"assert_no_unverified",
	"assemble_context",
	"build_report",
	"cadence_specs",
	"cadence_unverified",
	"check_report_gates",
	"deliver_report",
	"drift_gate",
	"find_unverified_token",
	"record_delivery",
	"report_id_for",
	"section_artefact_path",
	"section_by_slug",
	"validate_reporting_config",
]
