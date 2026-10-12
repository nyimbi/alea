# SPDX-License-Identifier: MIT
"""Artefact fixtures for Layer 6's five cadences.

Exit criterion 1 -- "all five cadences render end-to-end on fixtures" -- is a
fixture deliverable, not a production-data one. Every section a cadence
declares reads an artefact a lower layer owns, and no lower layer exists yet,
so without this module the integration test can only ever assert that the
cadences fail. The fixtures are real artefacts written through
``alea.io.artefacts.write_artefact`` with real provenance sidecars, not mocks:
a mocked reader would pass against a section that could never read a real
file, which is exactly the failure this criterion exists to catch.

The provenance is chosen to exercise the rule that governs the layer rather
than to look plausible. Each section's fixture carries the basis its report
should show -- measured, modelled, forecast, or proxy -- and a proxy carries
the 30% uncertainty a proxy actually has (``Provenance`` refuses a proxy with
zero uncertainty), which is what makes the precision gate (criterion 4)
checkable against a real artefact rather than a hand-built value.

The paths here mirror the ``artefact=`` patterns the cadence modules declare.
``sections_without_fixtures`` fails when a cadence gains a section this module
does not feed, so the fixture set cannot silently fall behind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from alea.io.artefacts import write_artefact
from alea.provenance.models import Basis, DerivedProvenance
from alea.reporting.schemas import ReportCadence, ReportDataError
from alea.reporting.service import cadence_specs

# The report date the integration test builds for. 2026-10-11 is a Saturday,
# so the weekly period ends Friday and every cadence's period arithmetic lands
# on a completed period.
AS_OF = date(2026, 10, 11)


@dataclass(frozen=True)
class FixtureValue:
	"""One row of a fixture artefact, with the basis it is meant to carry."""

	label: str
	value: float
	basis: Basis
	unit: str
	uncertainty: float = 0.0
	uncertainty_basis: str = ""


MEASURED = FixtureValue("Nairobi", 1200.0, Basis.MEASURED, "MW")
MODELLED = FixtureValue("Mombasa", 480.0, Basis.MODELLED, "MW", 0.1, "model RMSE")
FORECAST = FixtureValue("Kisumu", 310.0, Basis.FORECAST, "MW", 0.15, "ensemble spread")
# A proxy is never exact: Provenance refuses zero uncertainty on a proxy, and
# 30% is the uncertainty the plan's precision rule is written against.
PROXY = FixtureValue("Eldoret", 95.0, Basis.PROXY, "MW", 0.3, "nightlights proxy")

DEFAULT_ROWS: tuple[FixtureValue, ...] = (MEASURED, MODELLED, FORECAST, PROXY)


def _provenance(spec: FixtureValue, source_id: str) -> DerivedProvenance:
	"""A derived provenance carrying the fixture's chosen basis.

	``DerivedProvenance`` requires at least one input checksum, so the fixture
	records the source it stands in for rather than an empty list -- an
	artefact whose provenance claims no inputs is one ``write_artefact`` could
	not write at all.
	"""
	return DerivedProvenance(
		source_id=source_id,
		basis=spec.basis,
		uncertainty=spec.uncertainty,
		uncertainty_basis=spec.uncertainty_basis,
		notes=f"Layer 6 fixture for {spec.label}",
		inputs=[f"fixture:{source_id}"],
		run_id="00000000-0000-7000-8000-000000000000",
	)


#: Columns that carry no quantity: a section's first column is the row's
#: identity, and these three are metadata the reader derives from provenance.
NON_NUMERIC_COLUMNS = frozenset({"basis", "source", "interval", "ci"})


def declared_quantities(columns: list[str]) -> list[str]:
	"""A section's declared numeric column headers, in order.

	The first is the row's primary quantity -- the reader binds it to the
	artefact's ``value`` column -- and the rest are the row's other numbers,
	which the fixture must write or the reader has nothing to put in the column
	but a copy of the primary.
	"""
	return [
		column
		for position, column in enumerate(columns)
		if position > 0 and column.lower() not in NON_NUMERIC_COLUMNS
	]


def _frame(rows: tuple[FixtureValue, ...], columns: list[str] | None = None) -> pd.DataFrame:
	"""The rows as a frame, carrying every quantity the section declares.

	**Why the extras exist, and why they are the point of this module.** The
	frame used to hold one ``value`` column. Every section with more than one
	numeric column then had no second number to read, and the reader filled the
	extra columns with a copy of the first -- so ``["Line", "Peak loading",
	"Hours", "Basis"]`` printed the loading twice and ``["Country", "SAIDI",
	"SAIFI", "Basis"]`` printed SAIDI under SAIFI, in a published report, with
	every gate green. The fixture could not see it because it manufactured the
	shape the reader needed rather than the shape a producer writes.

	So when the section's columns are known the frame carries one column per
	declared quantity, named with the section's own header. The extras are the
	primary scaled by a distinct factor, which is the smallest change that
	makes a duplicated cell differ from a correct one -- a fixture whose extras
	equalled the primary would let the duplication back in unnoticed.
	"""
	frame: dict[str, list[object]] = {
		"label": [row.label for row in rows],
		"value": [row.value for row in rows],
		"unit": [row.unit for row in rows],
	}
	for offset, header in enumerate(declared_quantities(columns or []), start=2):
		frame[header] = [round(row.value * offset, 6) for row in rows]
	return pd.DataFrame(frame)


def write_fixture_artefact(
	path: str | Path,
	rows: tuple[FixtureValue, ...] = DEFAULT_ROWS,
	source_id: str = "reporting_fixture",
	columns: list[str] | None = None,
) -> Path:
	"""Write one fixture artefact plus its provenance sidecar.

	The section's basis is the *first* row's, because a report section reads
	one artefact's single provenance: an artefact carrying one proxy row is a
	proxy for the whole section under the weakest-basis rule. A caller that
	wants a measured-only section passes ``rows=(MEASURED,)``.

	``columns`` is the declaring section's column list. Passing it makes the
	frame carry every quantity the section reads, so a section with two numeric
	columns is fed a two-number row rather than a one-number row the reader
	would have to pad.
	"""
	assert rows, "a fixture artefact needs at least one row"
	target = Path(path)
	target.parent.mkdir(parents=True, exist_ok=True)
	write_artefact(target, _frame(rows, columns), _provenance(rows[0], source_id))
	return target


# --------------------------------------------------------------------------
# Per-cadence fixture sets, keyed by the artefact pattern a cadence declares
# --------------------------------------------------------------------------


def _day_stamp(cadence: ReportCadence) -> str:
	"""The date a cadence's artefact is stamped with.

	Every section pattern in all five cadence modules is ``.../{date}.parquet``,
	and ``assemble_context`` formats it with the cadence's ``period_end`` -- not
	the report's ``as_of``. So the fixture must carry the period end, and it
	asks the service for it rather than reimplementing the arithmetic. An
	earlier version of this helper computed a period end by hand and got it
	wrong for the weekly, quarterly and annual cadences at once; a fixture that
	guesses at the reader's rule fails the moment the rule is anything but
	"yesterday".
	"""
	from alea.reporting.schemas import period_for

	_, period_end = period_for(cadence, AS_OF)
	return f"{period_end:%Y-%m-%d}"


def _fixture_plan(cadence: ReportCadence) -> dict[str, tuple[FixtureValue, ...]]:
	"""The artefacts a cadence's sections declare, with the rows each carries."""
	stamp = _day_stamp(cadence)
	match cadence:
		case ReportCadence.DAILY:
			return {
				f"outages/forecast/{stamp}.parquet": DEFAULT_ROWS,
				f"weather/alerts/{stamp}.parquet": (MODELLED, FORECAST),
				f"planning/dispatch/{stamp}.parquet": DEFAULT_ROWS,
				f"market/prices/{stamp}.parquet": (MEASURED, FORECAST),
				f"outages/contingency/{stamp}.parquet": (MEASURED, MODELLED),
				f"outages/viirs/{stamp}.parquet": (PROXY,),
			}
		case ReportCadence.WEEKLY:
			return {
				f"planning/outlook/{stamp}.parquet": (FORECAST, MEASURED),
				f"market/summary/{stamp}.parquet": (MEASURED, MODELLED),
				f"weather/renewables/{stamp}.parquet": (MODELLED,),
				f"losses/decomposition/{stamp}.parquet": (PROXY, MEASURED),
				f"outages/critical/{stamp}.parquet": (MODELLED,),
				f"outages/events/{stamp}.parquet": (MEASURED,),
				f"outages/mitigation/{stamp}.parquet": (MEASURED,),
			}
		case ReportCadence.MONTHLY:
			return {
				f"market/monthly/{stamp}.parquet": (MEASURED, MODELLED),
				f"planning/capacity/{stamp}.parquet": (MEASURED,),
				f"planning/generation_monthly/{stamp}.parquet": (MEASURED, FORECAST),
				f"outages/reliability/{stamp}.parquet": (PROXY, MEASURED),
				f"losses/monthly/{stamp}.parquet": (PROXY,),
				f"resilience/monthly/{stamp}.parquet": (MODELLED,),
				f"scanning/policy/{stamp}.parquet": (MEASURED,),
			}
		case ReportCadence.QUARTERLY:
			return {
				f"market/outlook/{stamp}.parquet": (FORECAST, MODELLED),
				f"scanning/pipeline/{stamp}.parquet": (MODELLED,),
				f"whatif/frontier/{stamp}.parquet": (MODELLED,),
				f"weather/climate_risk/{stamp}.parquet": (PROXY, MODELLED),
				f"resilience/scorecard/{stamp}.parquet": (MEASURED, MODELLED),
			}
		case ReportCadence.ANNUAL:
			return {
				f"planning/continental/{stamp}.parquet": (PROXY, MEASURED),
				f"planning/investment/{stamp}.parquet": (MODELLED,),
				f"planning/cmp/{stamp}.parquet": (MODELLED,),
				f"market/afsem/{stamp}.parquet": (MEASURED,),
				f"sector/just_transition/{stamp}.parquet": (MODELLED,),
				f"weather/scenarios/{stamp}.parquet": (FORECAST,),
			}
	raise ReportDataError(f"no fixture plan for cadence {cadence!r}")


def write_fixture_set(cadence: ReportCadence, results_root: str | Path) -> list[Path]:
	"""Write every artefact one cadence's sections declare, under ``results_root``.

	Returns the paths written, so a caller can assert the set is non-empty and
	the report read all of it. The root is a test's ``tmp_path``: fixtures are
	written per run and never committed, because an artefact carrying a
	provenance sidecar is a build output, not source.
	"""
	root = Path(results_root)
	specs, _ = cadence_specs(cadence)
	stamp = _day_stamp(cadence)
	# Columns by resolved path, so each fixture carries exactly the quantities
	# its section declares. Resolved here rather than in the plan because the
	# plan names paths with a concrete date and the spec names them with a
	# template token; this is the one place both spellings are in hand. The
	# tokens are formatted exactly as `_artefact_path` formats them, so a
	# cadence that starts using ``{month}`` is covered rather than mis-keyed.
	columns_for = {
		spec.artefact.format(date=stamp, month=stamp[:7], year=stamp[:4]): list(spec.columns)
		for spec in specs
	}
	written = [
		write_fixture_artefact(root / relative, rows, columns=columns_for.get(relative))
		for relative, rows in _fixture_plan(cadence).items()
	]
	assert written, f"cadence {cadence.value} wrote no fixtures"
	return written


def write_all_fixture_sets(results_root: str | Path) -> dict[ReportCadence, list[Path]]:
	"""Write all five cadences' fixture sets under one results root.

	The sets do not collide: the daily and weekly sets share a date but write
	different directory trees, and the longer cadences write period-end dates.
	"""
	return {cadence: write_fixture_set(cadence, results_root) for cadence in ReportCadence}


def declared_artefacts(cadence: ReportCadence, as_of: date) -> list[str]:
	"""Every ``artefact=`` pattern a cadence declares, resolved to a path string.

	Resolved against the cadence's ``period_end`` for ``as_of``, which is the
	date the reader will format the pattern with.
	"""
	from alea.reporting.schemas import period_for

	_, period_end = period_for(cadence, as_of)
	specs, _ = cadence_specs(cadence)
	return [
		spec.artefact.format(
			date=f"{period_end:%Y-%m-%d}",
			month=f"{period_end:%Y-%m}",
			year=f"{period_end:%Y}",
		)
		for spec in specs
	]


def sections_without_fixtures(cadence: ReportCadence, as_of: date = AS_OF) -> list[str]:
	"""Declared section patterns this module's fixture plan does not cover.

	The check that keeps the fixture set honest: a cadence that gains a section
	whose artefact nothing writes would otherwise fail only at render time, and
	only for the cadence someone happened to run. Compares on the filename
	stem, so a new section that reuses an existing path is not falsely reported
	as uncovered.
	"""
	planned = {Path(relative).name for relative in _fixture_plan(cadence)}
	return sorted(
		pattern for pattern in declared_artefacts(cadence, as_of) if Path(pattern).name not in planned
	)


def fixture_provenance_at(results_root: str | Path, relative: str) -> datetime:
	"""The ``retrieved_at`` of a written fixture's provenance sidecar.

	Used to assert the fixture is a real artefact with a real sidecar rather
	than a payload written by hand.
	"""
	sidecar = Path(results_root) / f"{relative}.provenance.json"
	return datetime.fromisoformat(
		json.loads(sidecar.read_text(encoding="utf-8"))["retrieved_at"]
	).astimezone(UTC)


__all__ = [
	"AS_OF",
	"DEFAULT_ROWS",
	"FORECAST",
	"FixtureValue",
	"MEASURED",
	"MODELLED",
	"PROXY",
	"declared_artefacts",
	"fixture_provenance_at",
	"sections_without_fixtures",
	"write_all_fixture_sets",
	"write_fixture_artefact",
	"write_fixture_set",
]
