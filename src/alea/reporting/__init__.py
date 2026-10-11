# SPDX-License-Identifier: MIT
"""Layer 6: periodic reporting.

The platform's visible surface, and the layer with the highest cost of being
wrong: it is where a modelling error becomes a published claim.

The rule that governs it is one sentence. **A report may not contain a number
whose provenance it cannot print.** Every number is a ``ReportValue`` whose
basis is derived from the provenance record of the artefact it came from --
``ProvenanceRecord.basis`` returns the weakest basis among the inputs, so one
measured input cannot launder a proxied one -- and the template renders that
basis as a superscript marker. A proxy estimate for Burundi is visibly
distinct from a metered value for Kenya, which is the entire point of the
``Basis`` enum reaching this far down the stack.

``build_report`` is the one entry point. The CLI and the scheduler both call
it, so a scheduled report and a backfilled one are the same artefact.
"""

from __future__ import annotations

from alea.reporting.assemble import (
	constant_value,
	optional_artefact,
	value_from_artefact,
	values_from_artefact,
)
from alea.reporting.render import (
	drift_is_clean,
	drift_report,
	html_checksums,
	missing_or_empty_pdfs,
	render_html,
	render_report,
	report_filename,
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
	ValueBasis,
	format_value,
	period_for,
)
from alea.reporting.service import (
	UNVERIFIED_TOKEN,
	BuildResult,
	DeliveryResult,
	assemble_context,
	assert_no_unverified,
	build_report,
	cadence_specs,
	check_report_gates,
	deliver_report,
	drift_gate,
	record_delivery,
	validate_reporting_config,
)

__all__ = [
	"UNVERIFIED_TOKEN",
	"BuildResult",
	"DataWindow",
	"DeliveryResult",
	"ReportCadence",
	"ReportChart",
	"ReportContext",
	"ReportDataError",
	"ReportSection",
	"ReportTable",
	"ReportValue",
	"UnverifiedClaim",
	"ValueBasis",
	"assert_no_unverified",
	"assemble_context",
	"build_report",
	"cadence_specs",
	"check_report_gates",
	"constant_value",
	"deliver_report",
	"drift_gate",
	"drift_is_clean",
	"drift_report",
	"format_value",
	"html_checksums",
	"missing_or_empty_pdfs",
	"optional_artefact",
	"period_for",
	"record_delivery",
	"render_html",
	"render_report",
	"report_filename",
	"validate_reporting_config",
	"value_from_artefact",
	"values_from_artefact",
]
