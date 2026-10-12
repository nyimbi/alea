# SPDX-License-Identifier: MIT
"""Alerting contracts: the conditions, the severities, and the delivery of one.

`13-deployment.md` §6.3 is a table of six conditions, each with a severity, and
the plan's own note on criterion 10:

	A skipped validation is a ticket, not a silent pass. The platform must never
	report a model as validated when the ground truth was unavailable.

The table is the specification. What was missing is the mechanism, and the
mechanism has one property the table does not state: **an alert path that has
never been exercised is an alert path that does not exist.** So the condition
register is data here rather than a branch someone writes at the call site, the
route is a value that can be pointed at a sink in a test, and
``alea.ops.service.raise_alert`` is the only way an alert is emitted.

:class:`AlertCondition` is the register: the six conditions, their severities,
and the ``page`` flag that separates the two. A severity is not decoration --
:func:`pages` is what an on-call rota reads, and a condition added without a
severity is a condition nobody is told about.

:class:`Alert` is one firing. It carries the condition, a human summary, the
run id that raised it, and whatever context the condition needs. It is written
as an artefact like everything else, so a page that fired last Tuesday can be
re-read rather than remembered.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from alea._uuid7 import uuid7str


class Severity(StrEnum):
	"""How loud an alert is.

	``PAGE`` wakes someone. ``TICKET`` does not, and the difference is the whole
	reason severity exists: a connector whose layout changed is a job for the
	next working day, and paging for it is how a rota learns to ignore pages.
	"""

	PAGE = "page"
	TICKET = "ticket"


class AlertCondition(StrEnum):
	"""The six conditions of `13-deployment.md` §6.3."""

	PIPELINE_FAILED = "pipeline_failed"
	"""Pipeline failed after bounded retries. Three attempts, then alert."""

	REPORT_NOT_DELIVERED = "report_not_delivered"
	"""A scheduled report was generated but not delivered."""

	ARTEFACT_CHECKSUM_MISMATCH = "artefact_checksum_mismatch"
	"""An artefact's content does not hash to its recorded checksum."""

	CONNECTOR_LAYOUT_CHANGED = "connector_layout_changed"
	"""A source's page or payload shape moved under its scraper."""

	VALIDATION_SKIPPED = "validation_skipped"
	"""Ground truth was unavailable, so a validation did not run.

	This is the plan's "a skipped validation is a ticket, not a silent pass".
	It is a ticket because the model is not wrong, it is unmeasured -- and the
	danger is that an unmeasured model is reported as a validated one.
	"""

	DETERMINISM_FAILED = "determinism_failed"
	"""The two-process determinism job produced differing output."""


_REGISTER: dict[AlertCondition, Severity] = {
	AlertCondition.PIPELINE_FAILED: Severity.PAGE,
	AlertCondition.REPORT_NOT_DELIVERED: Severity.PAGE,
	AlertCondition.ARTEFACT_CHECKSUM_MISMATCH: Severity.PAGE,
	AlertCondition.CONNECTOR_LAYOUT_CHANGED: Severity.TICKET,
	AlertCondition.VALIDATION_SKIPPED: Severity.TICKET,
	AlertCondition.DETERMINISM_FAILED: Severity.PAGE,
}
"""Severity per condition, from §6.3's table.

A dict rather than a branch: the table is the specification and a reader
comparing the two should see the same six rows in the same order.
"""


def severity_of(condition: AlertCondition) -> Severity:
	"""The severity §6.3 assigns to a condition."""
	assert isinstance(condition, AlertCondition), f"not a condition: {condition!r}"
	return _REGISTER[condition]


def pages(condition: AlertCondition) -> bool:
	"""Whether this condition wakes someone."""
	return severity_of(condition) is Severity.PAGE


def conditions() -> list[AlertCondition]:
	"""Every condition the register knows, in table order."""
	return list(_REGISTER)


class Alert(BaseModel):
	"""One firing of one condition.

	``run_id`` is not optional. An alert that cannot be joined to the run that
	raised it is an alert whose cause is a separate investigation, and
	`00-architecture.md` §8 makes the run id the join key everywhere else.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	alert_id: str = Field(default_factory=uuid7str)
	condition: AlertCondition
	severity: Severity
	summary: str
	run_id: str = ""
	raised_at: datetime
	context: dict[str, Any] = Field(default_factory=dict)

	@property
	def wakes_someone(self) -> bool:
		return self.severity is Severity.PAGE


class AlertRoute(BaseModel):
	"""Where an alert goes.

	A route is a value, not a module-level constant, so a test can point it at a
	file and watch the alert arrive. ``sink`` is a path rather than a URL
	because the always-on node has no pager integration in the foundations and
	a JSON-lines file is what a log shipper already reads -- the plan's §6.2
	says structured JSON in production, and this is the same decision applied to
	the alert stream.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	sink: str = "results/ops/alerts.jsonl"
	"""Where fired alerts are appended, one JSON object per line."""

	minimum_severity: Severity = Severity.TICKET
	"""The quietest alert this route carries.

	Default ``TICKET``, so a condition added to the register reaches the stream
	without anyone editing the route. A route that defaulted to ``PAGE`` would
	silently drop the tickets, and a dropped ticket is a validation skip that
	nobody ever reads.
	"""


__all__ = [
	"Alert",
	"AlertCondition",
	"AlertRoute",
	"Severity",
	"conditions",
	"pages",
	"severity_of",
]
