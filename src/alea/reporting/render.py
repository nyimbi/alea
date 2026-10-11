# SPDX-License-Identifier: MIT
"""Rendering: context -> SVG charts -> HTML -> PDF, and the drift gate.

HTML is the source of truth; the PDF is a rendering of it. The PDF is not
byte-reproducible -- WeasyPrint stamps each file with its own metadata, so two
renders of an unchanged document differ by a few hundred bytes -- which is why
the drift gate covers the HTML only and asserts separately that every HTML has
a non-empty PDF beside it. A gate that diffs the PDFs fails forever on a clean
tree, and a gate that cannot pass is indistinguishable from no gate. See
09-layer6 §4 and 12-quality §3.4.

Matplotlib runs in the Agg backend and needs no display, so this module
imports it lazily: the drift gate and the HTML path must work in an
environment where the plotting stack is absent.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from alea.io.artefacts import sha256_file, utcnow
from alea.logging import get_logger
from alea.reporting.schemas import (
	MARKERS,
	ReportChart,
	ReportContext,
	ReportDataError,
	ReportTable,
	ReportValue,
)

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
REPORT_CSS = "report.css"

# A stable colour per basis, so a reader learns the mapping once. Measured is
# neutral ink; the others are distinguishable in greyscale as well as colour,
# because a printed report is a report.
BASIS_COLOURS: dict[str, str] = {
	"measured": "#1f2933",
	"modelled": "#2f6f9f",
	"proxy": "#b54708",
	"forecast": "#5b3f9e",
}


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


def _environment(templates: Path | None = None) -> Environment:
	"""A Jinja2 environment that refuses to render an undefined name.

	``StrictUndefined`` is not stylistic. A template that renders ``{{ value }}``
	for a missing ``value`` as an empty string produces a report with a blank
	where a number should be, and nobody notices until it is published.
	"""
	directory = templates or TEMPLATES_DIR
	if not directory.is_dir():
		raise ReportDataError(f"template directory {directory} does not exist")
	environment = Environment(
		loader=FileSystemLoader(str(directory)),
		undefined=StrictUndefined,
		autoescape=True,
		trim_blocks=True,
		lstrip_blocks=True,
		keep_trailing_newline=True,
	)
	environment.filters["report_number"] = lambda v: v.formatted if isinstance(v, ReportValue) else v
	environment.filters["marker"] = lambda v: v.marker if isinstance(v, ReportValue) else ""
	return environment


def template_name(cadence: str) -> str:
	"""The template file for a cadence."""
	return f"{cadence}.html.j2"


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------


def render_chart_svg(
	chart: ReportChart,
	table: ReportTable | None = None,
	*,
	width: float = 7.2,
	height: float = 3.2,
) -> str:
	"""Render a chart to SVG from the *table's* values.

	A chart is a view of the data, not a separate data path. If a table is
	passed, the chart plots the table's values, so the two cannot disagree --
	which is what prevents a report whose table and whose chart tell different
	stories.
	"""
	values = table.values if table is not None else chart.values
	if not values:
		raise ReportDataError(f"chart {chart.slug!r} has no values to plot")

	import matplotlib

	matplotlib.use("Agg")
	from matplotlib.figure import Figure

	labels = [value.label or f"row {index}" for index, value in enumerate(values)]
	numbers = [value.value for value in values]
	colours = [BASIS_COLOURS[value.basis.value] for value in values]

	figure = Figure(figsize=(width, height), layout="constrained")
	axes = figure.subplots()
	axes.bar(range(len(values)), numbers, color=colours)
	axes.set_xticks(range(len(values)))
	axes.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
	axes.set_ylabel(chart.unit or "value", fontsize=9)
	axes.set_title(chart.title, fontsize=10, loc="left")
	axes.spines[["top", "right"]].set_visible(False)
	return figure_to_svg(figure)


def figure_to_svg(figure: Any) -> str:
	"""Serialise a matplotlib figure to an SVG string with no variable content.

	Two sources of run-to-run variation are removed, both of which would make
	the HTML -- and therefore the drift gate over the HTML -- fail on a clean
	tree:

	* the generator comment, which carries the matplotlib version;
	* the element ids, which matplotlib derives from a per-figure random token
	  (``id="pb325479d75"``), so two renders of the same data differ.

	The ids are only referenced by ``url(#...)`` within the same document, so
	making them stable changes nothing about the picture and everything about
	whether the report can be diffed.
	"""
	from io import StringIO

	buffer = StringIO()
	figure.savefig(buffer, format="svg", metadata={"Date": None})
	svg = buffer.getvalue()
	svg = "\n".join(line for line in svg.splitlines() if not line.startswith("<!--"))
	# Both the patch ids (``p<hex>``) and the marker ids (``m<hex>``) carry the
	# per-figure random token; each is referenced only by a same-document
	# ``url(#...)`` or ``xlink:href``, so stabilising them changes the picture
	# not at all.
	return re.sub(r"\b[mp][0-9a-f]{6,}\b", "x00000000", svg)


def chart_svgs(context: ReportContext) -> dict[str, str]:
	"""Every chart in a context, keyed by ``section/chart`` slug."""
	out: dict[str, str] = {}
	for section in context.sections:
		for chart in section.charts:
			table = next((t for t in section.tables if t.slug == chart.slug), None)
			out[f"{section.slug}/{chart.slug}"] = render_chart_svg(chart, table)
	return out


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------


def render_html(
	context: ReportContext,
	*,
	templates: Path | None = None,
	template: str | None = None,
) -> str:
	"""Render a report context to HTML."""
	environment = _environment(templates)
	name = template or template_name(context.cadence.value)
	try:
		tmpl = environment.get_template(name)
	except TemplateNotFound as exc:
		raise ReportDataError(f"no template {name!r} in {templates or TEMPLATES_DIR}") from exc

	markup = tmpl.render(
		report=context,
		markers=MARKERS,
		basis_colours=BASIS_COLOURS,
		charts=chart_svgs(context),
		generated=utcnow(),
	)
	assert markup.strip(), f"template {name} rendered empty"
	return markup


def write_css(out_dir: Path, *, templates: Path | None = None) -> Path | None:
	"""Copy the stylesheet beside the HTML so the file is self-contained."""
	source = (templates or TEMPLATES_DIR) / REPORT_CSS
	if not source.exists():
		return None
	target = out_dir / REPORT_CSS
	target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
	return target


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def html_to_pdf(html: str, out: Path, *, base_url: str | Path | None = None) -> Path:
	"""Render HTML to PDF via WeasyPrint.

	WeasyPrint is imported here rather than at module scope: it pulls in a
	native stack that a container running only the HTML path does not need.
	"""
	from weasyprint import HTML

	out.parent.mkdir(parents=True, exist_ok=True)
	HTML(string=html, base_url=str(base_url) if base_url else None).write_pdf(str(out))
	return out


def render_report(
	template: str,
	context: ReportContext | dict[str, Any],
	out: Path,
	*,
	formats: tuple[str, ...] = ("html", "pdf"),
	templates: Path | None = None,
) -> dict[str, Path]:
	"""Render a report to HTML and PDF.

	HTML is the source of truth; PDF is a rendering of it. The PDF is not
	checksum-stable -- WeasyPrint stamps metadata -- so the *drift gate covers
	the HTML only* and asserts separately that each HTML has a non-empty PDF
	beside it. A gate that diffs the PDFs fails forever on a clean tree.
	"""
	if not isinstance(context, ReportContext):
		raise ReportDataError(
			f"render_report expects a ReportContext, got {type(context).__name__}; "
			f"a plain dict has not passed the bare-number gate"
		)
	if not formats:
		raise ReportDataError("no output formats requested")

	out.mkdir(parents=True, exist_ok=True)
	stem = out / (template or context.cadence.value)
	produced: dict[str, Path] = {}

	markup = render_html(context, templates=templates, template=template_name(context.cadence.value))
	if "html" in formats:
		html_path = stem.with_suffix(".html")
		html_path.write_text(markup, encoding="utf-8")
		write_css(out, templates=templates)
		produced["html"] = html_path
	if "pdf" in formats:
		pdf_path = stem.with_suffix(".pdf")
		html_to_pdf(markup, pdf_path, base_url=out)
		if not pdf_path.exists() or pdf_path.stat().st_size == 0:
			raise ReportDataError(f"{pdf_path}: WeasyPrint produced an empty PDF")
		produced["pdf"] = pdf_path

	logger.info(
		"report.rendered",
		report_id=context.report_id,
		cadence=context.cadence.value,
		formats=sorted(produced),
	)
	assert produced, "render_report produced nothing"
	return produced


def report_filename(cadence: str, as_of: date) -> str:
	"""The stem a report is written under, so a backfill does not overwrite."""
	return f"{cadence}-{as_of:%Y-%m-%d}"


# --------------------------------------------------------------------------
# Delivery records
# --------------------------------------------------------------------------


def write_delivery_record(directory: Path, record: Any) -> Path:
	"""Write one delivery record as a timestamped JSON file.

	Written here rather than in ``distribute`` so that a report rendered
	without a distribution channel still records the render: a report that was
	generated but not delivered is not a published report, and the platform
	must be able to say which it was. Records accumulate -- a resend does not
	erase the earlier attempt.
	"""
	directory.mkdir(parents=True, exist_ok=True)
	payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
	stamp = str(payload.get("sent_at", utcnow())).replace(":", "").replace("-", "")
	channel = payload.get("channel", "unknown")
	target = directory / f"{channel}-{stamp}.json"
	target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
	return target


# --------------------------------------------------------------------------
# Drift gate
# --------------------------------------------------------------------------


def html_checksums(root: str | Path, *, pattern: str = "**/*.html") -> dict[str, str]:
	"""sha256 of every HTML file under ``root``, keyed by relative path.

	Scoped to HTML by construction. The PDFs are stamped by the renderer and
	two renders of an unchanged document differ, so including them would make
	this function's result unstable and the gate that reads it unable to pass.
	"""
	base = Path(root)
	if not base.exists():
		raise ReportDataError(f"drift root {base} does not exist")
	return {
		str(path.relative_to(base)): sha256_file(path)
		for path in sorted(base.glob(pattern))
		if path.is_file()
	}


def missing_or_empty_pdfs(root: str | Path, *, pattern: str = "**/*.html") -> list[str]:
	"""HTML files with no non-empty PDF beside them.

	The separate assertion the drift gate needs: the HTML is diffed, and this
	checks the thing that actually matters about the PDF -- that it exists and
	has content.
	"""
	base = Path(root)
	if not base.exists():
		raise ReportDataError(f"drift root {base} does not exist")
	problems: list[str] = []
	for html in sorted(base.glob(pattern)):
		if not html.is_file():
			continue
		pdf = html.with_suffix(".pdf")
		if not pdf.exists() or pdf.stat().st_size == 0:
			problems.append(str(html.relative_to(base)))
	return problems


def drift_report(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
	"""The difference between two HTML checksum maps."""
	added = sorted(set(after) - set(before))
	removed = sorted(set(before) - set(after))
	changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
	return {"added": added, "removed": removed, "changed": changed}


def drift_is_clean(report: dict[str, list[str]]) -> bool:
	"""Whether a drift report shows no change."""
	return not any(report.values())


def fingerprint(items: Iterable[Any]) -> str:
	"""A stable digest of a JSON-serialisable iterable.

	Order-independent where the caller sorts first; used to compare two
	generation paths (scheduler vs. CLI) without diffing rendered bytes.
	"""
	payload = json.dumps(sorted(items, key=str), sort_keys=True, default=str)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_time(context: ReportContext) -> datetime:
	"""The moment a report was built, for the timing criterion."""
	return context.generated_at


__all__ = [
	"BASIS_COLOURS",
	"REPORT_CSS",
	"TEMPLATES_DIR",
	"build_time",
	"chart_svgs",
	"drift_is_clean",
	"drift_report",
	"figure_to_svg",
	"fingerprint",
	"html_checksums",
	"html_to_pdf",
	"missing_or_empty_pdfs",
	"render_chart_svg",
	"render_html",
	"render_report",
	"report_filename",
	"template_name",
	"write_css",
	"write_delivery_record",
]
