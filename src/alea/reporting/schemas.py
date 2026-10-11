# SPDX-License-Identifier: MIT
"""Report schemas: what a report contains, and the rule that governs it.

A report may not contain a number whose provenance it cannot print. Every
number is a :class:`ReportValue`, and its ``basis`` is *derived* from the
provenance record rather than supplied beside it. That is deliberate: a
caller that could pass ``basis=MEASURED`` next to a proxy's provenance could
launder the proxy, which is exactly the defect this layer exists to prevent.
``ProvenanceRecord.basis`` already returns the weakest basis among the inputs,
so a single metered input cannot lift a modelled one.

``basis`` renders as a superscript marker. A report where a proxy estimate for
Burundi is indistinguishable from a metered value for Kenya is a report that
will be quoted incorrectly, and the person quoting it will not have been
careless. See 09-layer6 §2.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from alea._uuid7 import uuid7str
from alea.provenance.models import Basis, Provenance, ProvenanceRecord

# One enum, not two. The plan names this ``ValueBasis``; the provenance layer
# names it ``Basis``. A second enum with the same four members is a second
# place for them to drift, and the marker table below is keyed on the members.
ValueBasis = Basis

MEASURED_MARKER = ""
MODELLED_MARKER = "ᵐ"  # ᵐ
PROXY_MARKER = "ᵖ"  # ᵖ
FORECAST_MARKER = "ᶠ"  # ᶠ

MARKERS: dict[Basis, str] = {
	Basis.MEASURED: MEASURED_MARKER,
	Basis.MODELLED: MODELLED_MARKER,
	Basis.PROXY: PROXY_MARKER,
	Basis.FORECAST: FORECAST_MARKER,
}

EXACT_SIGNIFICANT_FIGURES = 6
"""Digits printed for a value whose uncertainty is exactly zero.

A count of outages is exact and prints in full; this is a ceiling, not a
target, and trailing zeros are trimmed.
"""

MAX_SIGNIFICANT_FIGURES = 6
"""No report prints more digits than this, whatever the uncertainty claims.

A measured value with a claimed 1e-9 relative uncertainty is a value whose
uncertainty is not credible; the report does not propagate that claim into
eight digits of false precision.
"""


class ReportCadence(StrEnum):
	"""The five report periods."""

	DAILY = "daily"
	WEEKLY = "weekly"
	MONTHLY = "monthly"
	QUARTERLY = "quarterly"
	ANNUAL = "annual"


class ReportDataError(Exception):
	"""A section's input is absent.

	Raised, never defaulted. A missing input that falls back to a neighbouring
	country's value, or to a zero, produces a published number with no basis in
	anything -- see 00-architecture §8.
	"""


def as_record(provenance: Provenance | ProvenanceRecord | Iterable[Provenance]) -> ProvenanceRecord:
	"""Normalise anything provenance-shaped into a ``ProvenanceRecord``.

	The record is the only input that carries the weakest-basis rule, so every
	``ReportValue`` is built through here.
	"""
	if isinstance(provenance, ProvenanceRecord):
		return provenance
	if isinstance(provenance, Provenance):
		return ProvenanceRecord(entries=[provenance])
	entries = list(provenance)
	if not entries:
		raise ReportDataError("a ReportValue needs at least one provenance entry")
	return ProvenanceRecord(entries=entries)


def significant_figures(uncertainty: float) -> int:
	"""Digits of a value that a relative uncertainty leaves standing.

	A ±30% estimate has its uncertainty in the leading digit, so one figure of
	it is information and the rest is noise. ``floor(-log10(u)) + 1`` gives 1
	figure at 30%, 2 at 10%, 3 at 1%. Rendering the noise as ``1,234 MW`` is a
	false precision claim that a reader will quote.
	"""
	if uncertainty <= 0.0:
		return EXACT_SIGNIFICANT_FIGURES
	if not math.isfinite(uncertainty):
		return 1
	digits = math.floor(-math.log10(uncertainty)) + 1
	return max(1, min(digits, MAX_SIGNIFICANT_FIGURES))


def format_number(value: float, significant: int) -> str:
	"""Format ``value`` to ``significant`` figures with thousands separators.

	Never scientific notation: a report read by a human at 06:00 should not
	require the reader to decode an exponent. Trailing fractional zeros are
	trimmed, because ``1,200.00`` for an exact 1200 claims hundredth-of-a-unit
	precision that nothing measured.
	"""
	if not math.isfinite(value):
		return "n/a"
	if value == 0:
		return "0"
	magnitude = math.floor(math.log10(abs(value)))
	decimals = max(0, significant - 1 - magnitude)
	rounded = round(value, decimals)
	text = f"{rounded:,.{decimals}f}"
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text


@dataclass(frozen=True, slots=True)
class ReportValue:
	"""One number in a report, with everything needed to read it.

	``interval`` carries a confidence interval where the number is a
	probability or a forecast -- a daily outage forecast that renders as a
	binary ("outage: yes") when the model produced 12% is a forecast rendered
	as a fact. ``None`` means the number is a point estimate.
	"""

	value: float
	unit: str
	provenance: Provenance | ProvenanceRecord | tuple[Provenance, ...]
	label: str = ""
	interval: tuple[float, float] | None = None
	"""Confidence interval as ``(low, high)``, in the value's own unit."""
	significant_figures: int | None = None
	"""Override the figure count derived from uncertainty. Rarely correct."""

	def __post_init__(self) -> None:
		if not math.isfinite(self.value):
			raise ReportDataError(
				f"{self.label or 'value'}: {self.value} is not finite; a NaN "
				f"reaching a template renders as 'nan' in a published report"
			)
		if self.interval is not None:
			low, high = self.interval
			if not (low <= self.value <= high):
				raise ReportDataError(
					f"{self.label or 'value'}: value {self.value} lies outside "
					f"its own interval [{low}, {high}]"
				)

	@property
	def record(self) -> ProvenanceRecord:
		"""The provenance record, normalised once."""
		return as_record(self.provenance)

	@property
	def basis(self) -> Basis:
		"""The weakest basis among the inputs. Derived, never supplied."""
		return self.record.basis

	@property
	def uncertainty(self) -> float:
		"""Relative uncertainty: the maximum of the parts."""
		return self.record.uncertainty

	@property
	def marker(self) -> str:
		"""The superscript marker for this value's basis."""
		return MARKERS[self.basis]

	@property
	def figures(self) -> int:
		if self.significant_figures is not None:
			return self.significant_figures
		return significant_figures(self.uncertainty)

	@property
	def formatted(self) -> str:
		"""The number, to the precision its uncertainty supports."""
		return format_number(self.value, self.figures)

	@property
	def marked(self) -> str:
		"""The number with its basis marker attached."""
		return f"{self.formatted}{self.marker}"

	@property
	def interval_text(self) -> str:
		"""The confidence interval as ``low-high``, or empty."""
		if self.interval is None:
			return ""
		low, high = self.interval
		return f"{format_number(low, self.figures)}-{format_number(high, self.figures)}"

	@property
	def tooltip(self) -> str:
		"""What the marker means, for a reader who hovers.

		The report prints this in full in its footer as well: a tooltip is not
		a disclosure, because a PDF has no hover.
		"""
		parts = [f"basis: {self.basis.value}"]
		if self.uncertainty > 0:
			parts.append(f"uncertainty: +/-{self.uncertainty:.0%}")
			if self.record.uncertainty_basis:
				parts.append(self.record.uncertainty_basis)
		sources = ", ".join(sorted({entry.source_id for entry in self.record.entries}))
		if sources:
			parts.append(f"sources: {sources}")
		return " | ".join(parts)


def format_value(value: ReportValue) -> str:
	"""Format a report value to the precision its uncertainty supports.

	A value with 30% relative uncertainty has one significant figure of
	information; rendering it as a 4-digit integer claims three more than
	exist. Report readers quote the digits they are given.
	"""
	if not isinstance(value, ReportValue):
		raise ReportDataError(
			f"format_value expects a ReportValue, got {type(value).__name__}; a "
			f"bare number in a report has no basis and cannot be printed"
		)
	return value.formatted


@dataclass(frozen=True, slots=True)
class ReportTable:
	"""A table whose cells are report values or plain labels."""

	slug: str
	title: str
	columns: list[str]
	rows: list[list[ReportValue | str]]
	unit: str = ""
	note: str = ""

	def __post_init__(self) -> None:
		for index, row in enumerate(self.rows):
			if len(row) != len(self.columns):
				raise ReportDataError(
					f"table {self.slug!r} row {index} has {len(row)} cells for "
					f"{len(self.columns)} columns"
				)

	@property
	def values(self) -> list[ReportValue]:
		return [cell for row in self.rows for cell in row if isinstance(cell, ReportValue)]


@dataclass(frozen=True, slots=True)
class ReportChart:
	"""A chart, holding the same values its table holds.

	``values`` is the table's data, not a parallel copy: a chart rendered from
	a second path is how a report's chart and its table come to disagree. See
	09-layer6 §4.1.
	"""

	slug: str
	title: str
	values: list[ReportValue]
	unit: str = ""
	kind: str = "bar"
	"""``bar`` | ``line``."""


def chart_matches_table(chart: ReportChart, table: ReportTable) -> bool:
	"""Whether a chart plots exactly the values its table prints."""
	return [v.value for v in chart.values] == [v.value for v in table.values]


@dataclass(frozen=True, slots=True)
class DataWindow:
	"""The coverage window of an input, and how stale it is.

	A daily report saying "outages yesterday" when the satellite data is 24-48
	hours behind is reporting an incomplete picture as a complete one. The
	window is printed.
	"""

	source_id: str
	coverage_start: datetime
	coverage_end: datetime
	latency_hours: float = 0.0
	note: str = ""

	def describe(self) -> str:
		window = f"{self.coverage_start:%Y-%m-%d %H:%M} to {self.coverage_end:%Y-%m-%d %H:%M}"
		if self.latency_hours > 0:
			return f"{self.source_id}: {window} (publication latency {self.latency_hours:.0f} h)"
		return f"{self.source_id}: {window}"


@dataclass(frozen=True, slots=True)
class UnverifiedClaim:
	"""A literature benchmark not yet confirmed.

	AD-10's honesty rule: no ``[UNVERIFIED]`` figure appears in a published
	report. Either it is confirmed against a source, or it is printed with its
	status and the milestone at which it will be resolved.
	"""

	claim: str
	milestone: str = ""
	resolved: bool = False


@dataclass(frozen=True, slots=True)
class ReportSection:
	"""One headed block of a report."""

	slug: str
	title: str
	prose: str = ""
	values: list[ReportValue] = field(default_factory=list)
	tables: list[ReportTable] = field(default_factory=list)
	charts: list[ReportChart] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportContext:
	"""Everything a template renders, and nothing else.

	A template may only read from here, and every numeric field in here is a
	``ReportValue`` or is not a number at all. That is what makes the
	"no bare float reaches a template" gate checkable.
	"""

	title: str
	cadence: ReportCadence
	as_of: date
	period_start: date
	period_end: date
	generated_at: datetime
	timezone: str
	sections: list[ReportSection]
	report_id: str = field(default_factory=uuid7str)
	run_id: str = ""
	countries: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)
	data_windows: list[DataWindow] = field(default_factory=list)
	unverified: list[UnverifiedClaim] = field(default_factory=list)
	summary: str = ""

	@property
	def period_label(self) -> str:
		if self.period_start == self.period_end:
			return f"{self.period_start:%Y-%m-%d}"
		return f"{self.period_start:%Y-%m-%d} to {self.period_end:%Y-%m-%d}"

	@property
	def unresolved_unverified(self) -> list[UnverifiedClaim]:
		return [claim for claim in self.unverified if not claim.resolved]

	@property
	def values(self) -> list[ReportValue]:
		return [value for section in self.sections for value in section.values]

	@property
	def proxied_values(self) -> list[ReportValue]:
		"""Values whose basis is proxy. The report must distinguish these."""
		return [value for value in self.values if value.basis is Basis.PROXY]


# --------------------------------------------------------------------------
# Period arithmetic
# --------------------------------------------------------------------------


def period_for(cadence: ReportCadence, as_of: date) -> tuple[date, date]:
	"""The window a cadence reports on, ending the day before ``as_of``.

	A daily report generated at 06:00 covers yesterday, because today has not
	happened yet. Each longer cadence covers the most recent completed period
	for the same reason.
	"""
	match cadence:
		case ReportCadence.DAILY:
			return as_of - timedelta(days=1), as_of - timedelta(days=1)
		case ReportCadence.WEEKLY:
			end = as_of - timedelta(days=1)
			return end - timedelta(days=6), end
		case ReportCadence.MONTHLY:
			first_of_this_month = as_of.replace(day=1)
			end = first_of_this_month - timedelta(days=1)
			return end.replace(day=1), end
		case ReportCadence.QUARTERLY:
			month = 3 * ((as_of.month - 1) // 3) + 1
			this_quarter = date(as_of.year, month, 1)
			end = this_quarter - timedelta(days=1)
			return date(end.year, 3 * ((end.month - 1) // 3) + 1, 1), end
		case ReportCadence.ANNUAL:
			end = date(as_of.year - 1, 12, 31)
			return date(as_of.year - 1, 1, 1), end
	raise ReportDataError(f"unknown cadence {cadence!r}")


# --------------------------------------------------------------------------
# Gates support
# --------------------------------------------------------------------------


def find_bare_numbers(node: Any, path: str = "context") -> list[str]:
	"""Paths to numbers in a context that are not ``ReportValue``.

	The gate for "no bare float reaches a template". A float in the context is
	a number the template will print with no basis marker and no provenance,
	which is the failure this layer exists to prevent. Datetime and date
	objects are not numbers; ``ReportValue`` is where numbers are allowed.
	"""
	found: list[str] = []
	if isinstance(node, ReportValue):
		return found
	# A coverage window is not a report value: its numbers describe what the
	# data covers and how late it is, and a template reaches them only through
	# ``describe()``, which formats them into prose. Dates are not numbers.
	if isinstance(node, (DataWindow, datetime, date, bool)):
		return found
	if isinstance(node, (int, float)):
		found.append(path)
	elif isinstance(node, Mapping):
		for key, value in node.items():
			found.extend(find_bare_numbers(value, f"{path}.{key}"))
	elif isinstance(node, (list, tuple, set)):
		for index, value in enumerate(node):
			found.extend(find_bare_numbers(value, f"{path}[{index}]"))
	elif dataclasses.is_dataclass(node) and not isinstance(node, type):
		for info in dataclasses.fields(node):
			found.extend(find_bare_numbers(getattr(node, info.name), f"{path}.{info.name}"))
	return found


def chart_table_disagreements(context: ReportContext) -> list[str]:
	"""Sections whose chart does not plot its table's values."""
	problems: list[str] = []
	for section in context.sections:
		for chart in section.charts:
			table = next((t for t in section.tables if t.slug == chart.slug), None)
			if table is None:
				continue
			if not chart_matches_table(chart, table):
				problems.append(f"{section.slug}/{chart.slug}: chart and table disagree")
	return problems


__all__ = [
	"EXACT_SIGNIFICANT_FIGURES",
	"FORECAST_MARKER",
	"MARKERS",
	"MAX_SIGNIFICANT_FIGURES",
	"MEASURED_MARKER",
	"MODELLED_MARKER",
	"PROXY_MARKER",
	"DataWindow",
	"ReportCadence",
	"ReportChart",
	"ReportContext",
	"ReportDataError",
	"ReportSection",
	"ReportTable",
	"ReportValue",
	"UnverifiedClaim",
	"ValueBasis",
	"as_record",
	"chart_matches_table",
	"chart_table_disagreements",
	"find_bare_numbers",
	"format_number",
	"format_value",
	"period_for",
	"significant_figures",
]
