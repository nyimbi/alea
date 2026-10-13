# SPDX-License-Identifier: MIT
"""Landing a produced artefact where the report that reads it looks.

**The gap this closes.** `reporting/producers.py`'s ``PRODUCERS`` records the
*function* that writes a section's rows, and a stage writes them under
``paths.processed``. A section reads ``results/<dir>/{date}.parquet``
(:func:`alea.reporting.service.section_artefact_path`). Nothing bridged the two.

Both rule files that produce a section say the bridge exists and neither had
one: `rules/losses.smk`'s ``critical_lines`` -- *"the dated path under
``results/`` is the projection's ``--out`` and is not this rule's business --
one artefact, one path, and the report's date is the cadence's, not the
workflow's"* -- and `rules/reporting.smk` repeating it. There was no ``alea
project`` subcommand, no rule, and no test that a produced section can be read
by a report generated from the pipeline.

Measured 2026-10-13, running `rules/reporting.smk`'s exact command and then
`alea report monthly`: the build exits 0 and writes
``processed/capacity_update.parquet``, the section's dated path is absent, and
the report exits 1 with ``ReportDataError: Market report: no artefact at ...``.
Moving a slug from ``UNPRODUCED`` to ``PRODUCERS`` therefore recorded that a
function exists, not that a section is deliverable -- and 918 tests passed over
it because ``tests/fixtures/reporting`` writes every dated path by hand.

**Why a copy and not a re-render.** The stage's frame is the section's rows
already: one row per element with ``value``/``unit``/``label`` and a column per
other quantity the section names. Re-deriving them here would be a second
computation of the same numbers, and the two would drift the moment a stage's
shape changed -- so this module moves bytes and its provenance, and computes
nothing. ``alea.io.artefacts.copy_artefact`` was written for exactly this and
had no caller until now.

**Why the date comes from the cadence and not from the clock.** A daily report
generated at 06:00 covers *yesterday* (:func:`alea.reporting.schemas.period_for`),
so a projection stamped with the run date writes a file no report looks for --
and the failure is a silent absence, not an error. The caller passes the report
date and this module asks the cadence for its period end.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from alea.config.models import Config
from alea.io.artefacts import ArtefactError, copy_artefact, read_artefact
from alea.logging import get_logger
from alea.reporting.schemas import ReportCadence, period_for
from alea.reporting.service import SectionSpec, section_artefact_path, section_by_slug

logger = get_logger(__name__)


def project_section(
	cadence: ReportCadence | str,
	slug: str,
	source: str | Path,
	config: Config,
	*,
	as_of: date,
	period_end: bool = True,
) -> Path:
	"""Copy a produced artefact to the dated path its section reads.

	``as_of`` is the *report's* date. ``period_end`` resolves the cadence's own
	period from it, which is what the reader does: a weekly report dated Monday
	reads the period ending the previous Friday, and a projection that used the
	issue date would write a file the report never opens.

	The section is looked up by slug so the destination is the section's own
	declared ``artefact`` and never a path spelled here. A slug the cadence does
	not declare raises rather than writing somewhere plausible.

	The source is read before it is copied, so a file that is not an artefact --
	no provenance sidecar, or a payload the reader cannot parse -- fails here
	with the producer's path named, rather than at report time as a section that
	is mysteriously absent.
	"""
	assert source is not None, "source must not be None"
	assert slug, "slug must not be empty"
	kind = ReportCadence(cadence) if not isinstance(cadence, ReportCadence) else cadence
	spec = section_by_slug(kind, slug)
	origin = Path(source)
	if not origin.exists():
		raise ArtefactError(
			f"no artefact at {origin}; `{slug}` is projected from the file its "
			f"producer wrote, and nothing is there to move"
		)
	# Read before copying. `copy_artefact` moves a payload and its sidecar
	# together, and a payload with no sidecar is one `read_artefact` refuses --
	# which at report time is an absent section rather than a bad producer.
	payload, provenance = read_artefact(origin)
	_require_the_section_can_be_filled(origin, spec, payload)

	report_date = period_for(kind, as_of)[1] if period_end else as_of
	target = section_artefact_path(spec, config, report_date)
	if target.resolve() == origin.resolve():
		# Already where it belongs. Re-copying onto itself is harmless but the
		# `skip_if_current` idiom elsewhere in the pipeline means an operator can
		# reasonably point `--out` at the destination, and a silent no-op is a
		# better answer than a stat error.
		return target
	copy_artefact(origin, target)
	logger.info(
		"report.projected",
		section=slug,
		cadence=kind.value,
		report_date=str(report_date),
		rows=int(len(payload)) if hasattr(payload, "__len__") else 0,
		source=str(origin),
		out=str(target),
		basis=str(provenance.basis),
	)
	return target


def _normalise(column: str) -> str:
	"""The comparison key `_rows_for` binds a header with."""
	return "".join(character for character in column.lower() if character.isalnum())


def _is_numeric_column(column: str) -> bool:
	"""Whether a declared header names a quantity rather than a basis or label.

	The same rule `reporting/service.py`'s ``_numeric_columns`` applies, kept in
	step deliberately: this refusal must fire on exactly the columns the reader
	would bind, or it refuses artefacts the reader accepts -- and a gate that
	fails for reasons its operator cannot act on is one they learn to bypass.
	"""
	return column.lower() not in ("basis", "source", "interval", "ci")


def _require_the_section_can_be_filled(source: Path, spec: SectionSpec, payload: Any) -> None:
	"""Refuse to project an artefact the section's declared columns cannot be filled from.

	A projection moves bytes; it does not reshape them. But moving a frame that
	cannot satisfy the section's columns converts a producer-side problem into a
	reader-side one: `_rows_for` refuses a numeric column whose quantity the row
	does not carry -- correctly, since the alternative is printing one number
	under another's header -- so the *report* raises naming the section while the
	defect is in what the producer wrote.

	**This mirrors `_rows_for` rather than approximating it.** The first version
	required every numeric column to have a matching column in the payload, and
	that is *stricter* than the reader in two ways the reader allows: a column
	whose name matches the row's ``unit`` takes the primary, and a section with
	exactly one numeric column takes the primary whatever it is called. Both are
	real -- `market_outlook` declares ``["Quarter", "Price", "Basis"]``, one
	numeric column, and its producer writes ``value``/``unit`` and no ``price``
	column -- so the strict version refused an artefact `alea report quarterly`
	reads happily. A gate stricter than the thing it guards is one an operator
	routes around, which is the failure the docstring above names.

	The measured case for the refusal itself. `capacity_update` declares
	``["Carrier", "Capacity", "Change", "Basis"]``, two of them numeric, and the
	stage deliberately omits ``change`` when the directory holds a single solve
	(inventing a zero would assert capacity did not move). Projecting that frame
	makes `alea report monthly` raise inside `_rows_for`, which reads as a broken
	report. Refusing here names the missing quantity and the producer that owes
	it.
	"""
	if not isinstance(payload, pd.DataFrame) or payload.empty:
		raise ArtefactError(
			f"{source}: the payload is not a non-empty frame, so no section can be "
			f"filled from it. A projection moves rows; it does not invent them"
		)
	carried = {_normalise(str(column)) for column in payload.columns}
	numeric = [column for column in spec.columns[1:] if _is_numeric_column(column)]
	if len(numeric) == 1:
		# The reader's own fallback: with one numeric column the primary goes
		# there whatever the header is called, so there is nothing to refuse.
		return
	# The primary binds to a column naming the row's unit -- and the *section's*
	# declared unit wins where it has one, because that is what
	# `values_from_artefact` passes as `unit` and `_rows_for` compares against.
	# Reading the payload's unit unconditionally would be a third spelling of
	# the binding rule, and it would accept a frame the reader refuses.
	if spec.unit:
		units = {_normalise(spec.unit)}
	else:
		column = payload.get("unit")
		units = (
			{_normalise(str(unit)) for unit in column.dropna().unique()}
			if column is not None
			else set()
		)
	missing = [
		column
		for column in numeric
		if _normalise(column) not in carried and _normalise(column) not in units
	]
	if missing:
		raise ArtefactError(
			f"{source}: the section {spec.slug!r} declares {missing} and the "
			f"artefact carries {sorted(str(c) for c in payload.columns)}. Projecting "
			f"it would make the report raise inside `_rows_for` naming this "
			f"section, while the missing quantity is the producer's to write -- "
			f"either it writes it or the section's declaration drops it, and a copy "
			f"cannot decide that"
		)


def unprojected_sections(
	cadence: ReportCadence | str,
	config: Config,
	*,
	as_of: date,
) -> list[str]:
	"""The cadence's declared sections whose dated artefact is absent.

	The measurement the projection exists to move, and the one no test could
	make before it: ``PRODUCERS`` says a section has a writer, and this says
	whether a report can actually read one. Returned as slugs rather than a
	count so a caller can name what is missing.
	"""
	kind = ReportCadence(cadence) if not isinstance(cadence, ReportCadence) else cadence
	from alea.reporting.service import cadence_specs

	specs, _ = cadence_specs(kind)
	report_date = period_for(kind, as_of)[1]
	missing: list[str] = []
	for spec in specs:
		if not section_artefact_path(spec, config, report_date).exists():
			missing.append(spec.slug)
	return missing


__all__ = [
	"project_section",
	"unprojected_sections",
]
