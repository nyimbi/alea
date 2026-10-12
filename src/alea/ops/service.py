# SPDX-License-Identifier: MIT
"""Alerting, the review-queue restore drill, and the container digest gate.

Three operations `13-deployment.md` §9 asks for, each of which was previously a
table row with nothing behind it:

* **Criterion 6, "review queue restore tested."** §5.3 calls the review queue
	"the only irreplaceable operational state" -- analyst decisions exist nowhere
	else -- so a backup nobody has restored is a backup nobody knows works. The
	drill snapshots the live queue, *destroys it*, restores, and asserts the
	decisions survived. A restore that runs against an intact database proves
	nothing, which is why the drill deletes first.

* **Criterion 9, "base images pinned by digest."** §3.3: "a tag moves; a digest
	does not." The gate reads the Dockerfiles and refuses a `FROM` that names a
	tag without a digest. It is a text check rather than a build check on
	purpose: the defect is in the build config, it is visible there, and a build
	is not available on every machine that should be able to catch it.

* **Criterion 10, "alerting fires on a planted failure."** §6.3's table is a
	register in :mod:`alea.ops.views`; this module is the only way an alert is
	emitted, so every alert is written to a sink and can be asserted on.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alea.config.paths import resolve
from alea.logging import get_logger
from alea.ops.views import (
	Alert,
	AlertCondition,
	AlertRoute,
	Severity,
	severity_of,
)

_log = get_logger(__name__)

DEFAULT_ALERT_SINK = "results/ops/alerts.jsonl"


# --------------------------------------------------------------------------
# Alerting
# --------------------------------------------------------------------------


def raise_alert(
	condition: AlertCondition,
	summary: str,
	*,
	run_id: str = "",
	route: AlertRoute | None = None,
	context: dict[str, Any] | None = None,
	now: datetime | None = None,
) -> Alert:
	"""Record one firing and append it to the route's sink.

	The severity is read from the register, never passed in. A caller that
	could choose its own severity is a caller that could decide its own failure
	is a ticket, and the six severities in §6.3 are a decision that belongs to
	the plan rather than to the call site.

	An alert quieter than the route's floor is returned but not written, so a
	caller always learns what it raised while the stream stays at the volume the
	rota agreed to.
	"""
	assert summary, "an alert with no summary is a page with no cause"
	assert isinstance(condition, AlertCondition), f"not a condition: {condition!r}"
	active = route or AlertRoute(sink=DEFAULT_ALERT_SINK)
	alert = Alert(
		condition=condition,
		severity=severity_of(condition),
		summary=summary,
		run_id=run_id,
		raised_at=now or datetime.now(UTC),
		context=dict(context or {}),
	)
	if _carried(alert.severity, active.minimum_severity):
		_write_alert(alert, active.sink)
	_log.info(
		"ops.alert",
		condition=condition.value,
		severity=alert.severity.value,
		run_id=run_id,
		summary=summary,
	)
	return alert


def _carried(severity: Severity, floor: Severity) -> bool:
	"""Whether a route carries a severity.

	``PAGE`` outranks ``TICKET``, so the comparison is by rank rather than by
	string, where ``"ticket" < "page"`` would have been true by accident of
	alphabet and the floor would have meant its opposite.
	"""
	rank = {Severity.TICKET: 0, Severity.PAGE: 1}
	return rank[severity] >= rank[floor]


def _write_alert(alert: Alert, sink: str | Path) -> Path:
	target = resolve(sink)
	target.parent.mkdir(parents=True, exist_ok=True)
	line = json.dumps(alert.model_dump(mode="json"), sort_keys=True)
	with target.open("a", encoding="utf-8") as handle:
		handle.write(line + "\n")
	return target


def read_alerts(sink: str | Path | None = None) -> list[Alert]:
	"""Read back every alert a sink holds.

	The read half exists because criterion 10 is about *firing*, not about
	writing: a check that asserted on a mock would prove the call happened, and
	the plan's warning is that an unexercised path is not a path. This reads the
	bytes the process actually wrote.
	"""
	target = resolve(sink or DEFAULT_ALERT_SINK)
	if not target.is_file():
		return []
	alerts: list[Alert] = []
	for line in target.read_text(encoding="utf-8").splitlines():
		if line.strip():
			alerts.append(Alert.model_validate(json.loads(line)))
	return alerts


def pipeline_failed(
	attempts: int,
	*,
	run_id: str = "",
	route: AlertRoute | None = None,
	detail: str = "",
) -> Alert | None:
	"""Alert when a pipeline has exhausted its bounded retries.

	Returns ``None`` below the bound, because §4.2's "three attempts, then
	alert" means the first two failures are the retry policy working. Paging on
	attempt one is how a rota learns to ignore pages, which is the same failure
	mode as a gate everyone bypasses.
	"""
	assert attempts >= 0, f"attempts cannot be negative: {attempts}"
	if attempts < BOUNDED_ATTEMPTS:
		return None
	return raise_alert(
		AlertCondition.PIPELINE_FAILED,
		f"pipeline failed after {attempts} attempts",
		run_id=run_id,
		route=route,
		context={"attempts": attempts, "detail": detail},
	)


BOUNDED_ATTEMPTS = 3
"""§4.2: "An unbounded restart of a failing continental solve is a machine that
spins for a week. Three attempts, then alert." """


def report_not_delivered(
	report_id: str,
	cadence: str,
	channel: str,
	*,
	status: str,
	run_id: str = "",
	route: AlertRoute | None = None,
) -> Alert | None:
	"""Alert when a built report did not reach a channel.

	``status == "skipped"`` counts. §6.2: "a report that was generated but not
	delivered is a report that was not published" -- and a skip is the quietest
	way to not deliver, so treating it as success is exactly the silent failure
	the condition exists for.
	"""
	if status == "sent":
		return None
	return raise_alert(
		AlertCondition.REPORT_NOT_DELIVERED,
		f"{cadence} report {report_id} was not delivered over {channel} ({status})",
		run_id=run_id,
		route=route,
		context={"report_id": report_id, "cadence": cadence, "channel": channel, "status": status},
	)


def validation_skipped(
	target: str,
	reason: str,
	*,
	run_id: str = "",
	route: AlertRoute | None = None,
) -> Alert:
	"""Alert when a validation could not run for want of ground truth.

	A ticket, not a page -- but never a pass. The plan is explicit that the
	platform "must never report a model as validated when the ground truth was
	unavailable", and an unraised skip is indistinguishable from a validation
	that succeeded.
	"""
	assert reason, "a skip with no reason is a skip nobody can act on"
	return raise_alert(
		AlertCondition.VALIDATION_SKIPPED,
		f"validation of {target} was skipped: {reason}",
		run_id=run_id,
		route=route,
		context={"target": target, "reason": reason},
	)


# --------------------------------------------------------------------------
# Review queue restore drill (criterion 6)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RestoreDrill:
	"""What one restore drill observed.

	``rows_before`` and ``rows_after`` are both present because the drill's
	whole claim is that they are equal *across a destruction*. A drill that
	reported only the restored count cannot distinguish a restore from a
	database that was never touched.
	"""

	snapshot: Path
	rows_before: dict[str, int]
	rows_after: dict[str, int]
	destroyed: bool

	@property
	def survived(self) -> bool:
		return self.destroyed and self.rows_before == self.rows_after


def _table_counts(path: Path) -> dict[str, int]:
	"""Row counts for the two append-only tables, from the file itself."""
	connection = sqlite3.connect(path)
	try:
		counts: dict[str, int] = {}
		for table in ("signal_versions", "review_actions"):
			row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
			counts[table] = int(row[0])
		return counts
	finally:
		connection.close()


def snapshot_review_queue(
	queue_path: str | Path,
	snapshot_dir: str | Path,
	*,
	now: datetime | None = None,
) -> Path:
	"""Copy the review queue to a timestamped snapshot and verify the copy.

	``VACUUM INTO`` rather than a file copy. The queue runs in WAL mode, so the
	``.sqlite`` file alone is missing whatever is still in the write-ahead log --
	a file copy of a live WAL database is a snapshot that opens and has lost the
	most recent decisions, which is the one thing §5.3 says is irreplaceable.

	The copy is then opened and counted, so a snapshot that cannot be read is
	reported here rather than discovered during an incident.
	"""
	source = resolve(queue_path)
	assert source.is_file(), f"no review queue at {source}; refusing to snapshot nothing"
	stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
	directory = resolve(snapshot_dir)
	directory.mkdir(parents=True, exist_ok=True)
	target = directory / f"review-{stamp}.sqlite"
	if target.exists():
		target.unlink()

	# The destination must not exist for VACUUM INTO, hence the unlink above.
	connection = sqlite3.connect(source)
	try:
		connection.execute("VACUUM INTO ?", (str(target),))
	finally:
		connection.close()

	before = _table_counts(source)
	after = _table_counts(target)
	if before != after:
		raise RuntimeError(
			f"the snapshot does not match its source: {before} vs {after}. A "
			f"snapshot that silently loses rows is worse than no snapshot"
		)
	_log.info("ops.review_snapshot", source=str(source), snapshot=str(target), rows=before)
	return target


def restore_review_queue(snapshot: str | Path, queue_path: str | Path) -> Path:
	"""Restore a snapshot over the live queue.

	Refuses a snapshot whose append-only tables cannot be counted: restoring an
	unreadable file over the only irreplaceable state in the platform is the
	one operation here that must fail closed.
	"""
	source = resolve(snapshot)
	assert source.is_file(), f"no snapshot at {source}"
	_table_counts(source)  # raises if the snapshot is not a readable queue

	target = resolve(queue_path)
	target.parent.mkdir(parents=True, exist_ok=True)
	# A WAL database is three files. Restoring the `.sqlite` alone leaves the
	# old `-wal` beside it, and SQLite will replay that stale log over the
	# restored database -- the restore appears to work and the data is the
	# pre-restore data.
	for suffix in ("-wal", "-shm"):
		stale = target.with_name(target.name + suffix)
		if stale.exists():
			stale.unlink()
	shutil.copy2(source, target)
	_log.info("ops.review_restore", snapshot=str(source), target=str(target))
	return target


def review_queue_restore_drill(
	queue_path: str | Path,
	*,
	work_dir: str | Path,
	now: datetime | None = None,
) -> RestoreDrill:
	"""Snapshot the queue, destroy it, restore it, and report what survived.

	The destruction is the point. A restore drill against an intact database
	passes whether or not the snapshot is any good, because the file it "restores"
	over was already correct. This removes the queue and its WAL companions
	before restoring, so the only rows that can be present afterwards came from
	the snapshot.
	"""
	live = resolve(queue_path)
	before = _table_counts(live)
	snapshot = snapshot_review_queue(live, work_dir, now=now)

	for suffix in ("", "-wal", "-shm"):
		victim = live.with_name(live.name + suffix)
		if victim.exists():
			victim.unlink()
	destroyed = not live.exists()

	restore_review_queue(snapshot, live)
	after = _table_counts(live)
	return RestoreDrill(
		snapshot=snapshot,
		rows_before=before,
		rows_after=after,
		destroyed=destroyed,
	)


# --------------------------------------------------------------------------
# Container digest gate (criterion 9)
# --------------------------------------------------------------------------


_FROM = re.compile(r"^\s*FROM\s+(?P<image>[^\s]+)(?:\s+AS\s+(?P<alias>\S+))?\s*$", re.IGNORECASE | re.MULTILINE)
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_STAGE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ImageReference:
	"""One ``FROM`` line, and whether it is pinned."""

	image: str
	line: int
	pinned: bool

	@property
	def is_stage_reference(self) -> bool:
		"""Whether this names an earlier stage rather than a registry image.

		``FROM build AS runtime`` is not an unpinned image; it is a reference to
		a stage in the same file, and flagging it would be the checker failing
		for a reason its operator cannot act on -- which is how a gate gets
		switched off.
		"""
		return _STAGE_REFERENCE.match(self.image) is not None and "/" not in self.image


def unpinned_images(dockerfile: str | Path) -> list[ImageReference]:
	"""Every ``FROM`` in a Dockerfile that names a tag instead of a digest."""
	path = Path(dockerfile)
	assert path.is_file(), f"no Dockerfile at {path}"
	text = path.read_text(encoding="utf-8")
	references: list[ImageReference] = []
	aliases: set[str] = set()
	for match in _FROM.finditer(text):
		image = match.group("image")
		line = text[: match.start()].count("\n") + 1
		reference = ImageReference(image=image, line=line, pinned=_DIGEST.search(image) is not None)
		if reference.is_stage_reference and image in aliases:
			continue
		if match.group("alias"):
			aliases.add(match.group("alias"))
		references.append(reference)
	return [r for r in references if not r.pinned]


__all__ = [
	"BOUNDED_ATTEMPTS",
	"DEFAULT_ALERT_SINK",
	"ImageReference",
	"RestoreDrill",
	"pipeline_failed",
	"raise_alert",
	"read_alerts",
	"report_not_delivered",
	"restore_review_queue",
	"review_queue_restore_drill",
	"snapshot_review_queue",
	"unpinned_images",
	"validation_skipped",
]
