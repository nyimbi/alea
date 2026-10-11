# SPDX-License-Identifier: MIT
"""The dashboard.

The plan's delivery-channel table (11-layer8 §5) says the web dashboard is "a
separate app, consumes API". This module is the exception that proves the rule,
and it is small on purpose.

**Why there is HTML here at all.** The dashboard could be a separate frontend
repository, and for a full product it should be. But the plan's own priority list
puts "web dashboard" first among the professional channels, and a dashboard that
exists only as a plan is a capability nobody can use. This is a single
server-rendered page that reads the same endpoints every other adapter reads --
through the same repository, in-process -- so it is an adapter over the API's
data path rather than a second one.

**What it is not.** It is not a JavaScript application, it has no state of its
own, and it computes nothing. Every number it renders came from the repository
with its basis and uncertainty attached, and it renders the basis marker, because
a dashboard that drops the marker is the exact failure the value contract exists
to prevent.

The page is a single self-contained document: no external CSS, no CDN, no build
step. A dashboard that needs a toolchain to render is a dashboard that is
unavailable when the toolchain is.
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from alea.api.deps import PublicDep, StateDep
from alea.api.views import Basis

router = APIRouter(tags=["dashboard"])

_BASIS_MARKER = {
	Basis.MEASURED: "",
	Basis.MODELLED: "ᵐ",
	Basis.PROXY: "ᵖ",
	Basis.FORECAST: "ᶠ",
}

_STYLE = """
:root { color-scheme: light dark; }
body { font: 15px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 2rem;
       max-width: 72rem; margin-inline: auto; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
h2 { font-size: 1rem; margin: 2rem 0 .5rem; text-transform: uppercase;
     letter-spacing: .06em; opacity: .7; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #8883; }
th { font-weight: 600; opacity: .7; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
sup { font-size: .7em; }
.empty { opacity: .6; font-style: italic; }
.meta { opacity: .6; font-size: .85rem; }
"""


def _marker(basis: Basis) -> str:
	"""The superscript that distinguishes a proxy from a measurement."""
	return _BASIS_MARKER.get(basis, "")


def _value(cell) -> str:
	"""Render one value with its marker and its uncertainty."""
	assert cell is not None, "cannot render no value"
	marker = _marker(cell.basis)
	uncertainty = (
		f" <span class='meta'>±{cell.uncertainty:.0%}</span>" if cell.uncertainty > 0 else ""
	)
	return f"<span class='num'>{cell.value:,.1f}</span> {escape(cell.unit)}{marker}{uncertainty}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
	assert len(headers) >= 1, "a table needs at least one column"
	if not rows:
		return "<p class='empty'>No data published yet.</p>"
	head = "".join(f"<th>{escape(h)}</th>" for h in headers)
	body = "".join(
		"<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
	)
	return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@router.get("/dashboard", response_class=HTMLResponse, summary="Operator dashboard")
async def dashboard(state: StateDep, principal: PublicDep) -> HTMLResponse:
	"""The operator dashboard: one page, every group's current state.

	Served at the public tier because it shows national-resolution figures only.
	The rows it renders are the same rows ``/outages/forecast`` and ``/prices``
	serve; the page is a view, not a data path.
	"""
	assert state is not None, "dashboard needs application state"
	country = state.config.scenario.countries[0] if state.config.scenario.countries else ""
	scenarios = state.repository.scenarios()
	forecasts = state.repository.outage_forecasts(country=country, horizon_hours=24) if country else []
	prices = state.repository.prices(country=country) if country else []
	reports = state.repository.reports("daily")[:5]
	counts = await state.job_store.counts()

	parts = [
		"<!doctype html><html lang='en'><head><meta charset='utf-8'>",
		"<meta name='viewport' content='width=device-width, initial-scale=1'>",
		f"<title>{escape(state.config.api.title)}</title><style>{_STYLE}</style></head><body>",
		f"<h1>{escape(state.config.api.title)}</h1>",
		f"<p class='meta'>Country {escape(country or 'unconfigured')} · "
		f"{len(scenarios)} scenarios · {counts.get('running', 0)} jobs running · "
		f"{counts.get('queued', 0)} queued</p>",
		"<h2>Outage risk, next 24h</h2>",
		_table(
			["Zone", "Probability", "Horizon"],
			[
				[
					escape(row.grid_zone),
					_value(row.probability),
					f"{row.horizon_hours} h",
				]
				for row in forecasts[:20]
			],
		),
		"<h2>Wholesale price</h2>",
		_table(
			["Interval", "Country", "Price"],
			[
				[escape(str(row.at)), escape(row.country_iso or ""), _value(row.price)]
				for row in prices[-20:]
			],
		),
		"<h2>Recent daily reports</h2>",
		_table(
			["Date", "Title", "Checksum"],
			[
				[
					escape(report.report_date),
					escape(report.title),
					f"<code>{escape(report.checksum[:12])}</code>",
				]
				for report in reports
			],
		),
		"<p class='meta'>Markers: ᵐ modelled · ᵖ proxy · ᶠ forecast. An unmarked "
		"value is measured. Values carry the uncertainty of the model that "
		"produced them; a proxy is not a measurement.</p>",
		"</body></html>",
	]
	return HTMLResponse("".join(parts))


__all__ = ["router"]
