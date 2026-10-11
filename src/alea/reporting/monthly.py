# SPDX-License-Identifier: MIT
"""Monthly report, generated on the 1st at 06:00 local.

Two things this cadence must get right. The "actual versus forecast" section
compares this month's outturn against the forecast issued for it -- which
means the forecast must have been stored as an artefact at issue time, keyed
by issue date. A report that compares actuals against a forecast it did not
keep is comparing against a reconstruction, and a reconstruction is written
with hindsight.

The second is the reliability statistics. SAIDI and SAIFI for a country absent
from the continental datasets are proxies, and they render beside metered
figures with the proxy marker so the comparison is not silently false.
"""

from __future__ import annotations

from alea.reporting.service import DataWindowSpec, SectionSpec

CADENCE = "monthly"

SECTIONS: tuple[SectionSpec, ...] = (
	SectionSpec(
		slug="market_report",
		title="Market report",
		prose="Monthly clearing outcomes, price duration, and capture price by carrier.",
		artefact="market/monthly/{date}.parquet",
		unit="USD/MWh",
		table_title="Monthly market outcome",
		columns=["Carrier", "Volume", "Average price", "Basis"],
		required=True,
	),
	SectionSpec(
		slug="capacity_update",
		title="Capacity update",
		prose="Installed capacity by carrier at month end, and the change since the previous month.",
		artefact="planning/capacity/{date}.parquet",
		unit="MW",
		table_title="Installed capacity",
		columns=["Carrier", "Capacity", "Change", "Basis"],
	),
	SectionSpec(
		slug="generation_actual_vs_forecast",
		title="Generation: actual versus forecast",
		prose=(
			"Outturn generation against the forecast issued for this month. The "
			"forecast is the artefact written at issue time, not a re-run; a "
			"reconstruction is not a forecast."
		),
		artefact="planning/generation_monthly/{date}.parquet",
		unit="GWh",
		table_title="Actual against forecast",
		columns=["Carrier", "Actual", "Forecast", "Error", "Basis"],
	),
	SectionSpec(
		slug="outage_statistics",
		title="Outage statistics (SAIDI / SAIFI)",
		prose=(
			"Reliability indices for the month. A proxy index is derived from a "
			"regional or modelled estimate where the national utility does not "
			"publish one, and it is not comparable to a metered index."
		),
		artefact="outages/reliability/{date}.parquet",
		unit="index",
		table_title="Reliability by country",
		columns=["Country", "SAIDI", "SAIFI", "Basis"],
	),
	SectionSpec(
		slug="loss_statistics",
		title="Loss statistics",
		prose="Monthly loss share by component and the trend against the previous twelve months.",
		artefact="losses/monthly/{date}.parquet",
		unit="%",
		table_title="Losses this month",
		columns=["Component", "Loss share", "Basis"],
	),
	SectionSpec(
		slug="resilience_metrics",
		title="Resilience metrics",
		prose="Exceedance probability and recovery indicators from the resilience layer.",
		artefact="resilience/monthly/{date}.parquet",
		unit="",
		table_title="Resilience indicators",
		columns=["Indicator", "Value", "Basis"],
	),
	SectionSpec(
		slug="policy_tracker",
		title="Policy tracker",
		prose="Policy and regulatory changes recorded by the scanning layer this month.",
		artefact="scanning/policy/{date}.parquet",
		unit="",
		table_title="Policy changes",
		columns=["Country", "Change", "Basis"],
	),
)

WINDOWS: tuple[DataWindowSpec, ...] = (
	DataWindowSpec(
		source_id="viirs_nightlights",
		lag_days=1,
		note="Reliability indices derived from satellite outage detection lag the month end.",
	),
)

__all__ = ["CADENCE", "SECTIONS", "WINDOWS"]
