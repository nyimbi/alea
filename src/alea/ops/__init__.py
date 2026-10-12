# SPDX-License-Identifier: MIT
"""Operations: alerting, the review-queue restore drill, and the digest gate.

`13-deployment.md` §6.3 lists six alert conditions and §9 makes three of them
exit criteria. This package is where the conditions become a register, where a
restore is actually exercised, and where a base image that names a tag instead
of a digest is refused.
"""

from __future__ import annotations

from alea.ops.service import (
	BOUNDED_ATTEMPTS,
	DEFAULT_ALERT_SINK,
	ImageReference,
	RestoreDrill,
	pipeline_failed,
	raise_alert,
	read_alerts,
	report_not_delivered,
	restore_review_queue,
	review_queue_restore_drill,
	snapshot_review_queue,
	unpinned_images,
	validation_skipped,
)
from alea.ops.views import (
	Alert,
	AlertCondition,
	AlertRoute,
	Severity,
	conditions,
	pages,
	severity_of,
)

__all__ = [
	"BOUNDED_ATTEMPTS",
	"DEFAULT_ALERT_SINK",
	"Alert",
	"AlertCondition",
	"AlertRoute",
	"ImageReference",
	"RestoreDrill",
	"Severity",
	"conditions",
	"pages",
	"pipeline_failed",
	"raise_alert",
	"read_alerts",
	"report_not_delivered",
	"restore_review_queue",
	"review_queue_restore_drill",
	"severity_of",
	"snapshot_review_queue",
	"unpinned_images",
	"validation_skipped",
]
