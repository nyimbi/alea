# SPDX-License-Identifier: MIT
"""Daily report, generated for 06:00 local.

The hazard particular to this cadence is latency. VIIRS outage detection runs
a day or more behind, so a report that says "outages yesterday" while the
satellite data covers the day before is reporting an incomplete picture as a
complete one. Every section that reads a lagging source declares its window,
and the template prints the window above the numbers.

The 24-hour outage forecast is a probability, not a binary. It renders with
its confidence interval, because "outage: yes" for a 12% forecast is a
forecast rendered as a fact.
"""

from __future__ import annotations

from alea.reporting.service import DataWindowSpec, SectionSpec

CADENCE = "daily"

# Severity threshold for a weather alert. Config in the plan; recorded here as
# a hand-entered constant so the report can print where the number came from.
SEVERITY_THRESHOLD = 3

SECTIONS: tuple[SectionSpec, ...] = (
	SectionSpec(
		slug="outage_forecast",
		title="Outage forecast (24 h)",
		prose=(
			"Probability of an outage on each monitored line over the next 24 "
			"hours. A probability is not a prediction of an event; the interval "
			"is the model's 90% band."
		),
		artefact="outages/forecast/{date}.parquet",
		unit="probability",
		table_title="Outage probability by line",
		columns=["Line", "Probability", "Interval", "Basis"],
		required=True,
	),
	SectionSpec(
		slug="weather_alerts",
		title="Weather alerts",
		prose=(
			f"Forecast weather exceeding severity {SEVERITY_THRESHOLD} on the "
			"ERA5 grid. The threshold is a configuration value, not a physical "
			"constant, and a different threshold changes the list."
		),
		artefact="weather/alerts/{date}.parquet",
		unit="severity index",
		table_title="Alerts above threshold",
		columns=["Region", "Severity", "Basis"],
	),
	SectionSpec(
		slug="generation_mix",
		title="Generation mix (day-ahead)",
		prose="Scheduled generation by carrier for the day ahead, from the dispatch model.",
		artefact="planning/dispatch/{date}.parquet",
		unit="MW",
		table_title="Scheduled generation",
		columns=["Carrier", "Output", "Basis"],
	),
	SectionSpec(
		slug="price_forecast",
		title="Price forecast",
		prose="Day-ahead clearing price by hour, from the market model.",
		artefact="market/prices/{date}.parquet",
		unit="USD/MWh",
		table_title="Clearing price",
		columns=["Period", "Price", "Basis"],
	),
	SectionSpec(
		slug="system_alerts",
		title="System alerts",
		prose="Contingency states and reserve shortfalls identified by the contingency analysis.",
		artefact="outages/contingency/{date}.parquet",
		unit="",
		table_title="Active contingencies",
		columns=["Element", "State", "Basis"],
		# `State` is the severity band, not a number: `publish.views.
		# RESILIENCE_CONTINGENCY` types it `str` and
		# `project_resilience_contingency` bands each element into
		# "high"/"medium"/"low". Declared here because a header alone cannot
		# say so -- the reader's single-numeric-column fallback would otherwise
		# print the element's load shed under it.
		categorical=("State",),
	),
	SectionSpec(
		slug="outage_summary",
		title="Outage summary (yesterday)",
		prose=(
			"Outages detected by VIIRS over the previous night. The satellite "
			"overpass runs behind real time, so this section covers the window "
			"stated below and not the calendar day."
		),
		artefact="outages/viirs/{date}.parquet",
		unit="count",
		table_title="Detected outages",
		columns=["Region", "Outages", "Basis"],
	),
)

WINDOWS: tuple[DataWindowSpec, ...] = (
	DataWindowSpec(
		source_id="viirs_nightlights",
		lag_days=1,
		note=(
			"VIIRS night-lights are published a day or more after the overpass; "
			"the outage summary lags the report date by this much."
		),
	),
	DataWindowSpec(
		source_id="era5_forecast",
		lag_days=0,
		note="ERA5 forecast is available for the report date.",
	),
)

__all__ = ["CADENCE", "SECTIONS", "SEVERITY_THRESHOLD", "WINDOWS"]
