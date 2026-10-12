# SPDX-License-Identifier: MIT
"""The SQLite review queue (10-layer7 §6.1).

SQLite, not Redis. The specification reached for Redis (``zadd`` /
``zrevrange``) with ``json.dumps(signal.__dict__)``, and there are two problems
with that which a different store solves for free:

* ``__dict__`` bypasses pydantic on the way out, so the queue can hold a shape
  the contract does not describe.
* A signal whose fields are mutated in the queue is a signal whose provenance
  no longer matches its content, and nothing in Redis prevents the mutation.

SQLite is transactional, inspectable with the ``sqlite3`` CLI, and already
present in the standard library — introducing a service for a review queue is a
new thing to run for a small feature.

**Append-only is enforced by the database.** Both tables carry ``BEFORE UPDATE``
and ``BEFORE DELETE`` triggers that abort. A Python-level rule holds only for
code that goes through the Python API; the trigger holds for a migration
script, a maintenance query, and a reviewer with the sqlite3 prompt open.
``test_review_is_append_only`` canaries both the API path and the raw-SQL path.

Every method is ``async`` and runs its blocking sqlite call in a worker thread,
because the rest of the package is async and a synchronous call here would
block the event loop for every other connector mid-fetch.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from alea.config.paths import resolve
from alea.io.artefacts import utcnow
from alea.logging import get_logger
from alea.scanning.review.models import (
	AccuracyRow,
	ExtractionAccuracy,
	ReviewAction,
	SignalStatus,
	SignalVersion,
)
from alea.scanning.views import PriorityBreakdown
from alea.signals.models import Signal

logger = get_logger(__name__)

DEFAULT_QUEUE_PATH = "results/scanning/review.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_versions (
	signal_id TEXT NOT NULL,
	version INTEGER NOT NULL,
	status TEXT NOT NULL,
	signal_json TEXT NOT NULL,
	priority REAL NOT NULL DEFAULT 0.0,
	priority_components_json TEXT NOT NULL DEFAULT '{}',
	corroborating_ids_json TEXT NOT NULL DEFAULT '[]',
	parent_version INTEGER,
	document_id TEXT NOT NULL DEFAULT '',
	model TEXT,
	prompt_version TEXT,
	created_at TEXT NOT NULL,
	PRIMARY KEY (signal_id, version)
);

CREATE TABLE IF NOT EXISTS review_actions (
	action_id TEXT PRIMARY KEY,
	signal_id TEXT NOT NULL,
	resulting_version INTEGER NOT NULL,
	analyst TEXT NOT NULL,
	action TEXT NOT NULL,
	edits_json TEXT NOT NULL DEFAULT '{}',
	reason TEXT NOT NULL DEFAULT '',
	merged_signal_ids_json TEXT NOT NULL DEFAULT '[]',
	model TEXT,
	prompt_version TEXT,
	at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_versions_signal ON signal_versions (signal_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_actions_signal ON review_actions (signal_id, at);

-- Append-only. These are the enforcement, not a comment about it.
CREATE TRIGGER IF NOT EXISTS signal_versions_no_update
BEFORE UPDATE ON signal_versions
BEGIN
	SELECT RAISE(ABORT, 'signal_versions is append-only: record a new version');
END;

CREATE TRIGGER IF NOT EXISTS signal_versions_no_delete
BEFORE DELETE ON signal_versions
BEGIN
	SELECT RAISE(ABORT, 'signal_versions is append-only: rows are never deleted');
END;

CREATE TRIGGER IF NOT EXISTS review_actions_no_update
BEFORE UPDATE ON review_actions
BEGIN
	SELECT RAISE(ABORT, 'review_actions is append-only: a decision is never edited');
END;

CREATE TRIGGER IF NOT EXISTS review_actions_no_delete
BEFORE DELETE ON review_actions
BEGIN
	SELECT RAISE(ABORT, 'review_actions is append-only: a decision is never deleted');
END;

-- The queue is the latest version of every signal that is still pending.
CREATE VIEW IF NOT EXISTS pending_queue AS
SELECT v.signal_id, v.version, v.priority, v.created_at, v.signal_json, v.corroborating_ids_json
FROM signal_versions v
JOIN (
	SELECT signal_id, MAX(version) AS version FROM signal_versions GROUP BY signal_id
) latest
	ON v.signal_id = latest.signal_id AND v.version = latest.version
WHERE v.status = 'pending';
"""

_LATEST = """
SELECT v.* FROM signal_versions v
JOIN (SELECT signal_id, MAX(version) AS version FROM signal_versions GROUP BY signal_id) latest
	ON v.signal_id = latest.signal_id AND v.version = latest.version
"""


class QueueError(RuntimeError):
	"""The queue refused an operation."""


class ReviewQueue:
	"""An append-only, transactional review queue."""

	def __init__(self, path: str | Path | None = None) -> None:
		self.path = resolve(path or DEFAULT_QUEUE_PATH)
		self.path.parent.mkdir(parents=True, exist_ok=True)
		self._connection: sqlite3.Connection | None = None
		self._lock = asyncio.Lock()

	# -- connection ------------------------------------------------------

	def _connect(self) -> sqlite3.Connection:
		"""Open and migrate the database. Synchronous; callers use ``to_thread``."""
		if self._connection is None:
			connection = sqlite3.connect(self.path, check_same_thread=False)
			connection.row_factory = sqlite3.Row
			# WAL lets a dashboard read while the pipeline writes; the foreign
			# key pragma is off by default in SQLite and the schema relies on
			# the triggers rather than on cascades, so it is not enabled.
			connection.execute("PRAGMA journal_mode=WAL")
			connection.execute("PRAGMA synchronous=NORMAL")
			connection.executescript(_SCHEMA)
			connection.commit()
			self._connection = connection
		return self._connection

	def _execute(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
		connection = self._connect()
		cursor = connection.execute(sql, tuple(params))
		rows = cursor.fetchall()
		connection.commit()
		return list(rows)

	def _execute_many(self, statements: list[tuple[str, tuple[Any, ...]]]) -> None:
		"""Run several statements in one transaction.

		Used where two writes must both land or neither: recording a decision
		without the version it produced would leave an action pointing at a
		version that does not exist.
		"""
		connection = self._connect()
		try:
			connection.execute("BEGIN")
			for sql, params in statements:
				connection.execute(sql, params)
			connection.commit()
		except Exception:
			connection.rollback()
			raise

	async def _run(self, function: Any, *args: Any) -> Any:
		"""Run a blocking queue operation off the event loop, serialised."""
		async with self._lock:
			return await asyncio.to_thread(function, *args)

	async def aclose(self) -> None:
		if self._connection is not None:
			await asyncio.to_thread(self._connection.close)
			self._connection = None

	async def __aenter__(self) -> ReviewQueue:
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.aclose()

	# -- rows <-> models -------------------------------------------------

	@staticmethod
	def _row_to_version(row: sqlite3.Row) -> SignalVersion:
		"""Rebuild a version, re-validating the signal on the way out.

		Re-validation is the point of storing JSON of a validated model rather
		than a dict: a row written by an older schema, or edited outside this
		module, fails here rather than propagating a shape the contract does
		not describe.
		"""
		return SignalVersion(
			signal_id=row["signal_id"],
			version=int(row["version"]),
			status=SignalStatus(row["status"]),
			signal=Signal.model_validate(json.loads(row["signal_json"])),
			priority=float(row["priority"]),
			priority_components=json.loads(row["priority_components_json"]),
			corroborating_ids=json.loads(row["corroborating_ids_json"]),
			parent_version=row["parent_version"],
			document_id=row["document_id"],
			model=row["model"],
			prompt_version=row["prompt_version"],
			created_at=datetime.fromisoformat(row["created_at"]),
		)

	@staticmethod
	def _row_to_action(row: sqlite3.Row) -> ReviewAction:
		return ReviewAction(
			action_id=row["action_id"],
			signal_id=row["signal_id"],
			analyst=row["analyst"],
			action=row["action"],
			edits=json.loads(row["edits_json"]),
			reason=row["reason"],
			at=datetime.fromisoformat(row["at"]),
			merged_signal_ids=json.loads(row["merged_signal_ids_json"]),
			model=row["model"],
			prompt_version=row["prompt_version"],
		)

	@staticmethod
	def _version_params(
		*,
		signal: Signal,
		version: int,
		status: SignalStatus,
		priority: float,
		components: dict[str, float],
		corroborating_ids: list[str],
		parent_version: int | None,
		document_id: str,
		model: str | None,
		prompt_version: str | None,
		at: datetime,
	) -> tuple[Any, ...]:
		return (
			signal.signal_id,
			version,
			status.value,
			signal.model_dump_json(),
			priority,
			json.dumps(components, sort_keys=True),
			json.dumps(sorted(corroborating_ids)),
			parent_version,
			document_id,
			model,
			prompt_version,
			at.isoformat(),
		)

	_INSERT_VERSION = """
	INSERT INTO signal_versions (
		signal_id, version, status, signal_json, priority, priority_components_json,
		corroborating_ids_json, parent_version, document_id, model, prompt_version, created_at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	"""

	_INSERT_ACTION = """
	INSERT INTO review_actions (
		action_id, signal_id, resulting_version, analyst, action, edits_json, reason,
		merged_signal_ids_json, model, prompt_version, at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	"""

	# -- writes ----------------------------------------------------------

	async def enqueue(
		self,
		signal: Signal,
		*,
		priority: float | PriorityBreakdown = 0.0,
		corroborating_ids: list[str] | None = None,
		model: str | None = None,
		prompt_version: str | None = None,
	) -> SignalVersion:
		"""Add a signal to the queue as version 1, pending.

		Idempotent on ``signal_id``: re-enqueueing a signal that is already
		present returns the existing version rather than raising or creating a
		second version. A pipeline re-run must not duplicate a queue entry, and
		a raise here would make a re-run fail on work it already did.
		"""
		assert signal.signal_id, "a signal without an id cannot be queued"
		breakdown = (
			priority
			if isinstance(priority, PriorityBreakdown)
			else PriorityBreakdown.from_components({"total": float(priority)})
		)
		existing = await self.latest(signal.signal_id)
		if existing is not None:
			logger.debug("enqueue_noop", signal_id=signal.signal_id[:12], version=existing.version)
			return existing

		version = SignalVersion(
			signal_id=signal.signal_id,
			version=1,
			status=SignalStatus.PENDING,
			signal=signal,
			priority=breakdown.total,
			priority_components=breakdown.components,
			corroborating_ids=sorted(corroborating_ids or []),
			parent_version=None,
			document_id=signal.source_document_id,
			created_at=utcnow(),
		)
		params = self._version_params(
			signal=version.signal,
			version=version.version,
			status=version.status,
			priority=version.priority,
			components=version.priority_components,
			corroborating_ids=version.corroborating_ids,
			parent_version=None,
			document_id=version.document_id,
			model=model,
			prompt_version=prompt_version,
			at=version.created_at,
		)
		await self._run(self._execute, self._INSERT_VERSION, params)
		logger.info(
			"signal_enqueued",
			signal_id=signal.signal_id[:12],
			signal_type=signal.signal_type,
			priority=round(version.priority, 2),
		)
		return version

	async def enqueue_many(
		self,
		entries: list[tuple[Signal, PriorityBreakdown, list[str]]],
		*,
		model: str | None = None,
		prompt_version: str | None = None,
	) -> list[SignalVersion]:
		"""Enqueue a scored batch in one transaction, skipping signals present.

		One transaction rather than a loop of ``enqueue`` calls, and the
		difference is not speed. A scan enqueues a batch and then reports what
		it enqueued; a loop that fails on entry 40 of 60 leaves 39 rows written
		and no report, so the next run re-extracts everything and the caller
		never learns the first batch half-landed. Here either the batch is in
		the queue or none of it is, and the count in ``ScanReport`` is the count
		that committed.

		Idempotence is preserved: a signal already present keeps its existing
		version and is returned unchanged, so a re-run adds nothing.
		"""
		assert isinstance(entries, list)
		versions: list[SignalVersion] = []
		statements: list[tuple[str, tuple[Any, ...]]] = []
		at = utcnow()
		for signal, breakdown, corroborating in entries:
			assert signal.signal_id, "a signal without an id cannot be queued"
			existing = await self.latest(signal.signal_id)
			if existing is not None:
				logger.debug(
					"enqueue_noop", signal_id=signal.signal_id[:12], version=existing.version
				)
				versions.append(existing)
				continue
			version = SignalVersion(
				signal_id=signal.signal_id,
				version=1,
				status=SignalStatus.PENDING,
				signal=signal,
				priority=breakdown.total,
				priority_components=breakdown.components,
				corroborating_ids=sorted(corroborating),
				parent_version=None,
				document_id=signal.source_document_id,
				created_at=at,
			)
			statements.append(
				(
					self._INSERT_VERSION,
					self._version_params(
						signal=signal,
						version=1,
						status=SignalStatus.PENDING,
						priority=breakdown.total,
						components=breakdown.components,
						corroborating_ids=sorted(corroborating),
						parent_version=None,
						document_id=signal.source_document_id,
						model=model,
						prompt_version=prompt_version,
						at=at,
					),
				)
			)
			versions.append(version)

		if statements:
			await self._run(self._execute_many, statements)
			logger.info(
				"signals_enqueued",
				count=len(statements),
				already_present=len(entries) - len(statements),
			)
		return versions

	async def confirm(
		self,
		signal_id: str,
		analyst: str,
		*,
		edits: dict[str, Any] | None = None,
		reason: str = "",
	) -> tuple[SignalVersion, ReviewAction]:
		"""Confirm a signal, optionally with corrections.

		The result is a new version whose ``requires_review`` is ``False``, which
		is what releases it to the integration stage. The original version stays.
		"""
		return await self._record(
			signal_id,
			analyst,
			action="edit" if edits else "confirm",
			edits=edits or {},
			reason=reason,
			status=SignalStatus.CONFIRMED,
			requires_review=False,
		)

	async def reject(
		self,
		signal_id: str,
		analyst: str,
		*,
		reason: str = "",
	) -> tuple[SignalVersion, ReviewAction]:
		"""Reject a signal as a false positive."""
		if not reason.strip():
			raise QueueError(
				f"rejecting {signal_id} requires a reason; a rejection with no "
				f"reason cannot feed the accuracy report"
			)
		return await self._record(
			signal_id,
			analyst,
			action="reject",
			edits={},
			reason=reason,
			status=SignalStatus.REJECTED,
			requires_review=True,
		)

	async def edit(
		self,
		signal_id: str,
		analyst: str,
		*,
		edits: dict[str, Any],
		reason: str = "",
	) -> tuple[SignalVersion, ReviewAction]:
		"""Correct a signal without confirming it.

		The corrected version goes back to the queue as pending: an analyst who
		fixed a capacity may not be the analyst who vouches for the event.
		"""
		if not edits:
			raise QueueError(f"edit of {signal_id} requires at least one field")
		return await self._record(
			signal_id,
			analyst,
			action="edit",
			edits=edits,
			reason=reason,
			status=SignalStatus.PENDING,
			requires_review=True,
		)

	async def merge(
		self,
		signal_id: str,
		other_signal_ids: list[str],
		analyst: str,
		*,
		reason: str = "",
	) -> tuple[SignalVersion, list[SignalVersion], ReviewAction]:
		"""Merge signals about the same event into the survivor.

		The survivor is confirmed with the merged ids attached as
		corroboration, and each merged-away signal gets a ``merged`` version so
		it leaves the queue without being deleted.
		"""
		if not other_signal_ids:
			raise QueueError("merge requires at least one other signal id")
		primary, action = await self._record(
			signal_id,
			analyst,
			action="merge",
			edits={},
			reason=reason,
			status=SignalStatus.CONFIRMED,
			requires_review=False,
			merged_signal_ids=sorted(set(other_signal_ids)),
			extra_corroboration=sorted(set(other_signal_ids)),
		)
		merged: list[SignalVersion] = []
		for other_id in sorted(set(other_signal_ids)):
			version, _ = await self._record(
				other_id,
				analyst,
				action="merge",
				edits={},
				reason=f"merged into {signal_id}",
				status=SignalStatus.MERGED,
				requires_review=True,
				allow_absent_action=True,
			)
			merged.append(version)
		return primary, merged, action

	async def _record(
		self,
		signal_id: str,
		analyst: str,
		*,
		action: str,
		edits: dict[str, Any],
		reason: str,
		status: SignalStatus,
		requires_review: bool,
		merged_signal_ids: list[str] | None = None,
		extra_corroboration: list[str] | None = None,
		allow_absent_action: bool = False,
	) -> tuple[SignalVersion, ReviewAction]:
		"""Append one decision and the version it produced, in one transaction."""
		if not analyst.strip():
			raise QueueError("a review decision must name the analyst")
		current = await self.latest(signal_id)
		if current is None:
			raise QueueError(f"no signal {signal_id} in the queue")

		updated_signal = _apply_edits(current.signal, edits)
		updated_signal = updated_signal.model_copy(update={"requires_review": requires_review})
		corroborating = sorted(
			set(current.corroborating_ids) | set(extra_corroboration or [])
		)
		now = utcnow()
		new_version = SignalVersion(
			signal_id=signal_id,
			version=current.version + 1,
			status=status,
			signal=updated_signal,
			priority=current.priority,
			priority_components=current.priority_components,
			corroborating_ids=corroborating,
			parent_version=current.version,
			document_id=current.document_id,
			model=current.model,
			prompt_version=current.prompt_version,
			created_at=now,
		)
		review_action = ReviewAction(
			signal_id=signal_id,
			analyst=analyst,
			action=action,  # type: ignore[arg-type]
			edits=edits,
			reason=reason,
			at=now,
			resulting_signal=updated_signal,
			merged_signal_ids=merged_signal_ids or [],
			model=current.model,
			prompt_version=current.prompt_version,
		)
		statements = [
			(
				self._INSERT_VERSION,
				self._version_params(
					signal=updated_signal,
					version=new_version.version,
					status=status,
					priority=new_version.priority,
					components=new_version.priority_components,
					corroborating_ids=corroborating,
					parent_version=current.version,
					document_id=new_version.document_id,
					model=current.model,
					prompt_version=current.prompt_version,
					at=now,
				),
			),
			(
				self._INSERT_ACTION,
				(
					review_action.action_id,
					review_action.signal_id,
					new_version.version,
					review_action.analyst,
					review_action.action,
					json.dumps(review_action.edits, sort_keys=True, default=str),
					review_action.reason,
					json.dumps(review_action.merged_signal_ids),
					review_action.model,
					review_action.prompt_version,
					review_action.at.isoformat(),
				),
			),
		]
		await self._run(self._execute_many, statements)
		logger.info(
			"review_recorded",
			signal_id=signal_id[:12],
			action=action,
			status=status.value,
			version=new_version.version,
			analyst=analyst,
		)
		return new_version, review_action

	# -- reads -----------------------------------------------------------

	async def latest(self, signal_id: str) -> SignalVersion | None:
		"""The most recent version of a signal, or ``None``."""
		rows = await self._run(
			self._execute,
			"SELECT * FROM signal_versions WHERE signal_id = ? ORDER BY version DESC LIMIT 1",
			(signal_id,),
		)
		return self._row_to_version(rows[0]) if rows else None

	async def history(self, signal_id: str) -> list[SignalVersion]:
		"""Every version of a signal, oldest first.

		The chain is the audit trail: an edit is visible as a version, not as a
		mutation, which is what makes the extraction error measurable.
		"""
		rows = await self._run(
			self._execute,
			"SELECT * FROM signal_versions WHERE signal_id = ? ORDER BY version ASC",
			(signal_id,),
		)
		return [self._row_to_version(row) for row in rows]

	async def pending(self, limit: int = 50, offset: int = 0) -> list[SignalVersion]:
		"""Highest-priority pending signals.

		Ordered by descending priority, then oldest first: two signals of equal
		priority should be reviewed in the order they arrived, or the older one
		starves.
		"""
		assert limit > 0, "a limit of zero asks for nothing"
		rows = await self._run(
			self._execute,
			"SELECT * FROM signal_versions WHERE (signal_id, version) IN ("
			"  SELECT signal_id, MAX(version) FROM signal_versions GROUP BY signal_id"
			") AND status = 'pending' "
			"ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?",
			(limit, offset),
		)
		return [self._row_to_version(row) for row in rows]

	async def pending_count(self) -> int:
		rows = await self._run(
			self._execute,
			"SELECT COUNT(*) AS n FROM signal_versions WHERE (signal_id, version) IN ("
			"  SELECT signal_id, MAX(version) FROM signal_versions GROUP BY signal_id"
			") AND status = 'pending'",
		)
		return int(rows[0]["n"])

	async def oldest_pending_at(self) -> datetime | None:
		"""When the oldest pending signal entered the queue.

		A queue depth without an age is a metric that cannot distinguish "busy
		day" from "nobody has reviewed anything for a week".
		"""
		rows = await self._run(
			self._execute,
			"SELECT MIN(created_at) AS oldest FROM signal_versions WHERE (signal_id, version) IN ("
			"  SELECT signal_id, MAX(version) FROM signal_versions GROUP BY signal_id"
			") AND status = 'pending'",
		)
		oldest = rows[0]["oldest"] if rows else None
		return datetime.fromisoformat(oldest) if oldest else None

	async def actions(self, signal_id: str | None = None) -> list[ReviewAction]:
		"""Every recorded decision, optionally for one signal."""
		if signal_id is None:
			rows = await self._run(
				self._execute, "SELECT * FROM review_actions ORDER BY at ASC"
			)
		else:
			rows = await self._run(
				self._execute,
				"SELECT * FROM review_actions WHERE signal_id = ? ORDER BY at ASC",
				(signal_id,),
			)
		return [self._row_to_action(row) for row in rows]

	async def confirmed_signals(self) -> list[Signal]:
		"""Signals whose latest version is confirmed.

		These are the only signals the integration stage will accept, and
		``requires_review`` on each is ``False`` by construction.
		"""
		rows = await self._run(
			self._execute,
			f"{_LATEST} WHERE v.status = 'confirmed' ORDER BY v.signal_id",
		)
		return [self._row_to_version(row).signal for row in rows]

	async def accuracy(self) -> ExtractionAccuracy:
		"""Extraction accuracy per signal type and per source (§6.3).

		Computed from the latest version of every signal plus the recorded
		edits, so a confirmed signal that was corrected counts as confirmed
		*and* contributes its corrected fields to ``field_errors``.
		"""
		versions = [
			self._row_to_version(row)
			for row in await self._run(self._execute, f"{_LATEST} ORDER BY v.signal_id")
		]
		action_rows = await self._run(
			self._execute,
			"SELECT signal_id, action, edits_json FROM review_actions",
		)
		edits_by_signal: dict[str, list[dict[str, Any]]] = {}
		for row in action_rows:
			if row["action"] in ("confirm", "edit") and row["edits_json"] not in ("{}", ""):
				edits_by_signal.setdefault(row["signal_id"], []).append(json.loads(row["edits_json"]))

		by_type: dict[str, AccuracyRow] = {}
		by_source: dict[str, AccuracyRow] = {}
		for version in versions:
			for dimension, key, bucket in (
				("signal_type", str(version.signal.signal_type), by_type),
				("source_name", version.signal.source_name, by_source),
			):
				row = bucket.get(key) or AccuracyRow(dimension=dimension, key=key)  # type: ignore[arg-type]
				row = row.model_copy(
					update={
						"extracted": row.extracted + 1,
						"confirmed": row.confirmed
						+ (1 if version.status is SignalStatus.CONFIRMED else 0),
						"rejected": row.rejected
						+ (1 if version.status is SignalStatus.REJECTED else 0),
						"pending": row.pending
						+ (1 if version.status is SignalStatus.PENDING else 0),
					}
				)
				bucket[key] = row

		for signal_id, edits_list in sorted(edits_by_signal.items()):
			latest = next((v for v in versions if v.signal_id == signal_id), None)
			if latest is None or latest.status is not SignalStatus.CONFIRMED:
				continue
			fields = sorted({field for edits in edits_list for field in edits})
			for key, bucket in (
				(str(latest.signal.signal_type), by_type),
				(latest.signal.source_name, by_source),
			):
				row = bucket.get(key)
				if row is None:
					continue
				counts = dict(row.field_errors)
				for field in fields:
					counts[field] = counts.get(field, 0) + 1
				bucket[key] = row.model_copy(
					update={"edited": row.edited + 1, "field_errors": counts}
				)

		rows = sorted(by_type.values(), key=lambda r: r.key) + sorted(
			by_source.values(), key=lambda r: r.key
		)
		return ExtractionAccuracy(rows=rows)

	async def auto_accept_precisions(
		self, *, min_sample_size: int = 30
	) -> dict[str, Any]:
		"""Measured precision per signal type, ready for ``decide_auto_accept``.

		This is the only sanctioned source of a ``SignalTypePrecision``: it
		reads a measurement out of the review record rather than letting a
		threshold be configured against a guessed number.
		"""
		from alea.scanning.score import SignalTypePrecision

		report = await self.accuracy()
		out: dict[str, SignalTypePrecision] = {}
		for key, row in report.by_signal_type().items():
			if row.sample_size < min_sample_size:
				continue
			out[key] = SignalTypePrecision(
				signal_type=row.key,  # type: ignore[arg-type]
				precision=row.precision,
				sample_size=row.sample_size,
				source=f"review record, {row.sample_size} reviewed signals",
			)
		return out


def _apply_edits(signal: Signal, edits: dict[str, Any]) -> Signal:
	"""Apply an analyst's corrections to a signal, re-validating.

	Unlike an extraction field, an analyst's edit is *not* silently dropped when
	it fails validation: a human typed it, and a human can be told. The
	``ValidationError`` propagates with the field named.

	An edit cannot change ``signal_id`` or the provenance fields. Letting an
	edit move ``source_url`` would let a confirmation launder a signal into a
	different document's provenance, which is the audit trail the queue exists
	to preserve.
	"""
	assert signal.signal_id, "an edit needs a signal to edit"
	immutable = {"signal_id", "source_document_id", "source_url", "extracted_at"}
	illegal = sorted(immutable & set(edits))
	if illegal:
		raise QueueError(
			f"an edit may not change {', '.join(illegal)}; provenance is not editable"
		)
	if not edits:
		return signal
	payload = signal.model_dump()
	payload.update(edits)
	try:
		return Signal.model_validate(payload)
	except ValidationError as exc:
		first = exc.errors()[0]
		field = first.get("loc", ("?",))[0]
		raise QueueError(f"edit rejected on field {field!r}: {first['msg']}") from exc


__all__ = [
	"DEFAULT_QUEUE_PATH",
	"QueueError",
	"ReviewQueue",
]
