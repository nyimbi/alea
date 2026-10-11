# SPDX-License-Identifier: MIT
"""Quarterly report.

The investment pipeline and the scenario update are both forward-looking, so
this cadence carries a higher proportion of forecast values than any other
short of the annual report. The scenario update exists to show how the range
moved, which requires the previous quarter's scenarios to have been retained
as artefacts -- the same retention requirement the monthly comparison has.
"""

from __future__ import annotations

from alea.reporting.service import DataWindowSpec, SectionSpec

CADENCE = "quarterly"

SECTIONS: tuple[SectionSpec, ...] = (
	SectionSpec(
		slug="market_outlook",
		title="Market outlook",
		prose="Clearing and capture-price outlook for the next four quarters, under the central scenario.",
		artefact="market/outlook/{date}.parquet",
		unit="USD/MWh",
		table_title="Price outlook",
		columns=["Quarter", "Price", "Basis"],
		required=True,
	),
	SectionSpec(
		slug="investment_pipeline",
		title="Investment pipeline",
		prose="Committed and proposed generation and transmission projects, by stage and by country.",
		artefact="scanning/pipeline/{date}.parquet",
		unit="MW",
		table_title="Pipeline by stage",
		columns=["Stage", "Capacity", "Basis"],
	),
	SectionSpec(
		slug="scenario_update",
		title="Scenario update",
		prose="Capacity and cost ranges across the scenario set, and how they moved since the previous quarter.",
		artefact="whatif/frontier/{date}.parquet",
		unit="MW",
		table_title="Scenario range",
		columns=["Scenario", "Capacity", "Cost", "Basis"],
	),
	SectionSpec(
		slug="climate_risk",
		title="Climate risk",
		prose="Projected change in hydro inflow and cooling demand, and the resulting exposure by country.",
		artefact="weather/climate_risk/{date}.parquet",
		unit="%",
		table_title="Climate exposure",
		columns=["Country", "Inflow change", "Demand change", "Basis"],
	),
	SectionSpec(
		slug="resilience_scorecard",
		title="Resilience scorecard",
		prose="Resilience indicators against their targets, with the trend over the last four quarters.",
		artefact="resilience/scorecard/{date}.parquet",
		unit="",
		table_title="Scorecard",
		columns=["Indicator", "Value", "Target", "Basis"],
	),
)

WINDOWS: tuple[DataWindowSpec, ...] = ()

__all__ = ["CADENCE", "SECTIONS", "WINDOWS"]
