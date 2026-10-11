# SPDX-License-Identifier: MIT
"""Scheduling.

Three requirements shape this module.

**Timezones are explicit.** ``CronTrigger(hour=6)`` uses the scheduler's
timezone, and a report "at 06:00 local" across 55 countries in five timezones
is meaningless without naming one. Reports are generated at the configured
timezone's 06:00, and the report prints the timezone it was generated in.

**A missed run is visible.** APScheduler's default ``misfire_grace_time`` can
silently drop a run if the process was down. It is set explicitly here, and a
dropped run writes a ``DeliveryResult(status="skipped")`` rather than leaving
a gap nobody sees.

**The scheduler is not the only way to run.** It calls the same
``build_report`` the CLI does, so a scheduled report and a backfilled one are
the same artefact. A scheduled-only report cannot be backfilled, and backfill
is what makes the monthly "actual versus forecast" comparison possible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from alea.config.models import Config
from alea.config.paths import resolve
from alea.logging import get_logger, new_run_id
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import BuildResult, build_report, record_delivery

logger = get_logger(__name__)

MISFIRE_GRACE_SECONDS = 3600
"""How late a run may start before APScheduler drops it.

One hour, set explicitly. The default can silently discard a run, which is
how a scheduled report stops arriving without anyone noticing.
"""

_CRON: dict[ReportCadence, dict[str, Any]] = {
	ReportCadence.DAILY: {"hour": None, "minute": 0},
	ReportCadence.WEEKLY: {"day_of_week": None, "hour": None, "minute": 0},
	ReportCadence.MONTHLY: {"day": 1, "hour": None, "minute": 0},
	ReportCadence.QUARTERLY: {"month": "1,4,7,10", "day": 1, "hour": None, "minute": 0},
	ReportCadence.ANNUAL: {"month": 1, "day": 1, "hour": None, "minute": 0},
}


def trigger_for(cadence: ReportCadence, config: Config) -> CronTrigger:
	"""The cron trigger for a cadence, in the configured timezone."""
	reporting = config.reporting
	spec = dict(_CRON[cadence])
	spec["hour"] = reporting.daily_hour
	spec["timezone"] = reporting.timezone
	if cadence is ReportCadence.WEEKLY:
		spec["day_of_week"] = reporting.weekly_day
	return CronTrigger(**spec)


def run_cadence(cadence: ReportCadence, config: Config, *, run_id: str = "") -> BuildResult:
	"""Build one cadence now. What the scheduler and the CLI both call.

	Identical inputs produce an identical report: the report id is derived
	from the cadence and the date rather than drawn at random, so a scheduled
	run and a manual run of the same period join on the same id.
	"""
	run_id = run_id or new_run_id()
	logger.info("schedule.run", cadence=cadence.value, run_id=run_id, tz=config.reporting.timezone)
	return build_report(cadence, config, run_id=run_id)


def build_scheduler(config: Config) -> BlockingScheduler:
	"""A blocking scheduler with one job per enabled cadence."""
	reporting = config.reporting
	if not reporting.enabled:
		raise ValueError("reporting.enabled is false; refusing to schedule reports that are off")

	scheduler = BlockingScheduler(
		timezone=reporting.timezone,
		job_defaults={
			"misfire_grace_time": MISFIRE_GRACE_SECONDS,
			"coalesce": True,
			"max_instances": 1,
		},
	)

	for cadence in ReportCadence:
		scheduler.add_job(
			run_cadence,
			trigger=trigger_for(cadence, config),
			args=[cadence, config],
			id=f"report-{cadence.value}",
			name=f"{cadence.value} report",
			replace_existing=True,
			misfire_grace_time=MISFIRE_GRACE_SECONDS,
		)
	logger.info(
		"scheduler.built",
		timezone=reporting.timezone,
		jobs=len(ReportCadence),
		misfire_grace_s=MISFIRE_GRACE_SECONDS,
	)
	return scheduler


def start(config: Config) -> None:
	"""Run the scheduler until interrupted."""
	scheduler = build_scheduler(config)
	try:
		scheduler.start()
	except (KeyboardInterrupt, SystemExit):  # pragma: no cover - interactive
		logger.info("scheduler.stopped")
		scheduler.shutdown(wait=False)


def backfill(
	cadence: ReportCadence,
	config: Config,
	start: date,
	end: date,
	*,
	delivery_dir: Path | None = None,
) -> list[BuildResult]:
	"""Generate every missed report in a date range.

	Each date is built through the same path the scheduler uses, so a
	backfilled report is the same artefact a scheduled run would have
	produced. A backfill records a ``skipped`` delivery per report by default:
	the report exists, but it was not sent when it was due, and the record
	says so rather than back-dating a delivery that never happened.
	"""
	if end < start:
		raise ValueError(f"backfill end {end} precedes start {start}")
	directory = delivery_dir or (resolve(config.paths.reports) / cadence.value / "deliveries")
	results: list[BuildResult] = []
	day = start
	while day <= end:
		result = build_report(cadence, config, date=day, deliver=False)
		record_delivery(
			"backfill",
			[],
			"skipped",
			report_id=result.report_id,
			cadence=cadence.value,
			detail=f"backfilled for {day:%Y-%m-%d}; not sent at the time it was due",
			artefacts=[str(p) for p in result.paths.values()],
			directory=directory,
		)
		results.append(result)
		day += _step(cadence)
	return results


def _step(cadence: ReportCadence) -> timedelta:
	if cadence is ReportCadence.DAILY:
		return timedelta(days=1)
	if cadence is ReportCadence.WEEKLY:
		return timedelta(days=7)
	if cadence is ReportCadence.MONTHLY:
		return timedelta(days=28)
	if cadence is ReportCadence.QUARTERLY:
		return timedelta(days=91)
	return timedelta(days=365)


def next_run(cadence: ReportCadence, config: Config, *, after: datetime | None = None) -> datetime:
	"""When a cadence next fires, so a missed run can be detected against it."""
	trigger = trigger_for(cadence, config)
	now = after or datetime.now(UTC)
	fire = trigger.get_next_fire_time(None, now)
	if fire is None:
		raise ValueError(f"cadence {cadence.value} has no next fire time")
	return fire


__all__ = [
	"MISFIRE_GRACE_SECONDS",
	"backfill",
	"build_scheduler",
	"next_run",
	"run_cadence",
	"start",
	"trigger_for",
]
