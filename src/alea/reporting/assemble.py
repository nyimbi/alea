# SPDX-License-Identifier: MIT
"""Report data assembly.

Layer 6 computes nothing. Every number in a report comes from an artefact a
layer below wrote, and carries that artefact's provenance. This module is the
only place report values are minted from artefacts, so it is the only place
the weakest-basis rule can be bypassed -- which is why it has exactly one
entry point, :func:`value_from_artefact`, and no arithmetic beyond a lookup.

An artefact that is absent raises. It does not fall back to a default and it
does not use a neighbouring country's value (00-architecture §8). A section
whose source layer has not run is a section the report omits with a stated
reason, not a section that prints a zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

from alea.io.artefacts import ArtefactError, read_artefact
from alea.provenance.models import Basis, DerivedProvenance, Provenance
from alea.reporting.schemas import ReportDataError, ReportValue

# Columns every layer artefact that feeds a report carries. The layer below
# owns the schema; these are the minimum a report can read without inventing
# meaning.
VALUE_COLUMN = "value"
UNIT_COLUMN = "unit"
LABEL_COLUMN = "label"

#: The interval columns a layer artefact carries when its value is a forecast
#: or a probability. Both must be present on a row for the interval to be read:
#: half an interval is not an interval, and a one-sided bound rendered as
#: ``low-high`` would print a range whose other end is a different number's.
INTERVAL_LOW_COLUMN = "interval_low"
INTERVAL_HIGH_COLUMN = "interval_high"


def provenance_of(record: DerivedProvenance) -> DerivedProvenance:
	"""The provenance a report value inherits from its artefact.

	Passed through unchanged. A report does not downgrade a modelled value to
	measured and does not upgrade a proxy to modelled; the whole chain depends
	on this being the artefact's own record.
	"""
	return record


def value_from_artefact(
	path: str | Path,
	*,
	label: str = "",
	unit: str | None = None,
	row: int = 0,
	column: str = VALUE_COLUMN,
) -> ReportValue:
	"""Mint one report value from one row of one artefact.

	The provenance is the artefact's sidecar, so the value's basis is the
	weakest basis among everything that produced the artefact.
	"""
	target = Path(path)
	try:
		data, provenance = read_artefact(target)
	except ArtefactError as exc:
		raise ReportDataError(f"{target}: {exc}") from exc

	if not isinstance(data, pd.DataFrame):
		raise ReportDataError(
			f"{target}: report inputs are tabular; got {type(data).__name__}"
		)
	if column not in data.columns:
		raise ReportDataError(
			f"{target}: no column {column!r}; columns are {sorted(data.columns)}"
		)
	if not 0 <= row < len(data):
		raise ReportDataError(f"{target}: row {row} of {len(data)}")

	raw = data[column].iloc[row]
	resolved_unit = unit or (str(data[UNIT_COLUMN].iloc[row]) if UNIT_COLUMN in data.columns else "")
	resolved_label = label or (
		str(data[LABEL_COLUMN].iloc[row]) if LABEL_COLUMN in data.columns else ""
	)
	return ReportValue(
		value=float(raw),
		unit=resolved_unit,
		provenance=provenance,
		label=resolved_label,
	)


def values_from_artefact(
	path: str | Path,
	*,
	unit: str | None = None,
	column: str = VALUE_COLUMN,
) -> list[ReportValue]:
	"""Mint one report value per row of an artefact."""
	target = Path(path)
	try:
		data, provenance = read_artefact(target)
	except ArtefactError as exc:
		raise ReportDataError(f"{target}: {exc}") from exc
	if not isinstance(data, pd.DataFrame):
		raise ReportDataError(f"{target}: report inputs are tabular")
	if column not in data.columns:
		raise ReportDataError(f"{target}: no column {column!r}")

	values = data[column].to_list()
	units = (
		data[UNIT_COLUMN].to_list() if UNIT_COLUMN in data.columns else [""] * len(data)
	)
	labels = (
		data[LABEL_COLUMN].to_list() if LABEL_COLUMN in data.columns else [""] * len(data)
	)
	# Every other numeric column travels with the row, keyed by the artefact's
	# own name for it. A section that declares two numeric columns reads two
	# numbers from one row, and dropping the second here is what left the reader
	# with nothing to put in the column but a copy of the first -- see
	# `_rows_for` for the duplication that caused and the refusal that replaced
	# it. `value` is the primary because the column is named `value`; the rest
	# are the row's other quantities, not a hierarchy.
	others = [
		name
		for name in data.columns
		if name not in (column, UNIT_COLUMN, LABEL_COLUMN)
		and name not in (INTERVAL_LOW_COLUMN, INTERVAL_HIGH_COLUMN)
		and is_numeric_dtype(data[name])
	]
	# The confidence interval, where the row carries one. `daily.py`'s
	# `outage_forecast` section declares an `Interval` column and its own
	# docstring says a 12% probability renders with its band; nothing read the
	# band out of the artefact, so the column rendered empty in every published
	# daily report. `_rows_for` writes `value.interval_text` into that column,
	# and `interval_text` is empty unless `interval` is set here -- the read
	# path is the only place a ReportValue is minted from an artefact, so this
	# is the only place it could be set.
	has_interval = INTERVAL_LOW_COLUMN in data.columns and INTERVAL_HIGH_COLUMN in data.columns
	return [
		ReportValue(
			value=float(raw),
			unit=unit or str(row_unit),
			provenance=provenance,
			label=str(row_label),
			interval=(
				(float(data[INTERVAL_LOW_COLUMN].iloc[position]),
				 float(data[INTERVAL_HIGH_COLUMN].iloc[position]))
				if has_interval
				and pd.notna(data[INTERVAL_LOW_COLUMN].iloc[position])
				and pd.notna(data[INTERVAL_HIGH_COLUMN].iloc[position])
				else None
			),
			extra=tuple(
				(name, float(data[name].iloc[position]))
				for name in others
				if pd.notna(data[name].iloc[position])
			),
		)
		for position, (raw, row_unit, row_label) in enumerate(
			zip(values, units, labels, strict=True)
		)
	]


def constant_value(
	value: float,
	unit: str,
	*,
	label: str = "",
	source_id: str = "hand_entered",
	uncertainty: float = 0.0,
	uncertainty_basis: str = "",
	basis: Basis = Basis.MEASURED,
	notes: str = "",
) -> ReportValue:
	"""A report value not read from an artefact.

	Permitted only for a value the report itself defines -- a threshold, a
	period length -- never for a datum a lower layer owns. The ``source_id``
	makes the hand-entry visible in the footer's provenance list, so a constant
	in a report is not mistaken for a measurement.
	"""
	if uncertainty > 0 and not uncertainty_basis:
		raise ReportDataError(
			f"{label or source_id}: non-zero uncertainty requires uncertainty_basis"
		)
	if basis is Basis.PROXY and uncertainty <= 0:
		raise ReportDataError(f"{label or source_id}: a proxy is not exact")
	return ReportValue(
		value=value,
		unit=unit,
		provenance=Provenance(
			source_id=source_id,
			basis=basis,
			uncertainty=uncertainty,
			uncertainty_basis=uncertainty_basis,
			notes=notes,
		),
		label=label,
	)


def optional_artefact(path: str | Path) -> Path | None:
	"""The path if its payload and sidecar are both present, else ``None``.

	Used for sections that are genuinely optional (a policy tracker with no
	entries this month). The caller decides what absence means and states it in
	the report; this function never substitutes a value.
	"""
	target = Path(path)
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	return target if target.exists() and sidecar.exists() else None


def section_warning(section: str, reason: str) -> str:
	"""A one-line statement of why a section is absent or partial.

	Printed in the report's warnings block. A report that silently omits a
	section is a report a reader trusts for coverage it does not have.
	"""
	return f"{section}: {reason}"


def as_mapping(values: dict[str, ReportValue]) -> dict[str, Any]:
	"""A context fragment, for a caller assembling one by hand in a test."""
	return dict(values)


__all__ = [
	"LABEL_COLUMN",
	"UNIT_COLUMN",
	"VALUE_COLUMN",
	"as_mapping",
	"constant_value",
	"optional_artefact",
	"provenance_of",
	"section_warning",
	"value_from_artefact",
	"values_from_artefact",
]
