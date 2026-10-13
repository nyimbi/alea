# SPDX-License-Identifier: MIT
"""Weekly report, generated Monday 06:00 local.

The week-ahead view is where the loss decomposition appears, and losses are
the number most likely to be quoted without its basis: a system loss figure is
frequently a proxy derived from a national total rather than a measurement of
any particular feeder. The decomposition section therefore prints its basis
per line rather than once for the table.
"""

from __future__ import annotations

from alea.reporting.service import DataWindowSpec, SectionSpec

CADENCE = "weekly"

SECTIONS: tuple[SectionSpec, ...] = (
	SectionSpec(
		slug="week_ahead",
		title="Week-ahead outlook",
		prose=(
			"Expected demand, renewable availability, and reserve margin for "
			"the coming week. These are forecasts and carry forecast markers."
		),
		artefact="planning/outlook/{date}.parquet",
		unit="MW",
		table_title="Week-ahead balance",
		columns=["Day", "Demand", "Renewable", "Margin", "Basis"],
		required=True,
	),
	SectionSpec(
		slug="market_summary",
		title="Market summary",
		prose="Cleared volumes and average prices over the week, with the capture price by carrier.",
		artefact="market/summary/{date}.parquet",
		unit="USD/MWh",
		table_title="Market outcome",
		columns=["Carrier", "Volume", "Capture price", "Basis"],
	),
	SectionSpec(
		slug="renewable_forecast",
		title="Renewable forecast",
		prose="Capacity factors by technology for the week, from the weather model.",
		artefact="weather/renewables/{date}.parquet",
		unit="capacity factor",
		table_title="Capacity factors",
		columns=["Technology", "Capacity factor", "Basis"],
	),
	SectionSpec(
		slug="loss_decomposition",
		title="Loss decomposition",
		prose=(
			"Transmission and distribution losses split by cause. Where a "
			"component is inferred from a system total rather than measured on "
			"the network, it is a proxy and is marked as one."
		),
		artefact="losses/decomposition/{date}.parquet",
		unit="%",
		table_title="Losses by component",
		columns=["Component", "Share of input", "Basis"],
	),
	SectionSpec(
		slug="critical_lines",
		title="Critical-line watch",
		prose="Lines loaded above their rating in the dispatch, and the hours at which it happens.",
		artefact="outages/critical/{date}.parquet",
		unit="loading",
		table_title="Lines at or above rating",
		columns=["Line", "Peak loading", "Hours", "Basis"],
	),
	SectionSpec(
		slug="outage_events",
		title="Outage events",
		prose="Detected outage events and their causes where a cause was recorded.",
		artefact="outages/events/{date}.parquet",
		unit="count",
		table_title="Events this week",
		columns=["Cause", "Events", "Basis"],
	),
	SectionSpec(
		slug="mitigation",
		title="Mitigation update",
		prose="Status of measures opened against the events above.",
		artefact="outages/mitigation/{date}.parquet",
		unit="",
		table_title="Open measures",
		columns=["Measure", "Status", "Basis"],
		# `Status` is a band -- open/closed -- not a quantity, on the same
		# footing as `system_alerts`'s `State`. See `SectionSpec.categorical`.
		categorical=("Status",),
	),
)

WINDOWS: tuple[DataWindowSpec, ...] = (
	DataWindowSpec(
		source_id="viirs_nightlights",
		lag_days=1,
		note="Outage detection lags the overpass by at least a day.",
	),
)

__all__ = ["CADENCE", "SECTIONS", "WINDOWS"]
