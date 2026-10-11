# SPDX-License-Identifier: MIT
"""The durable job store.

A capacity-expansion solve runs for minutes to hours. Three things follow, and
all three are the specification's defects being corrected rather than papered
over (11-layer8 §2.3, §3.2):

**No route blocks on a solve.** A route enqueues a job and returns 202 with a
status URL. The worker that runs jobs lives outside the request path, so a
two-hour solve does not hold a request, a connection, or the event loop.

**The store is SQLite, not a dict.** A job that dies with the process is a job
whose result the caller never learns, and a two-hour solve that fails silently is
worse than one that fails loudly. The record survives a restart because it is a
file.

**A job that was running when the process died is reported as interrupted.** This
is the part that is easy to get wrong: a row left in ``running`` after its worker
died reads as "still working" forever, and the caller polls a corpse. Each worker
registers a heartbeat; startup recovery interrupts every running job whose owner
has no fresh heartbeat. A job is therefore either genuinely running, or visibly
not.

Claiming is one ``UPDATE ... RETURNING`` statement. Two workers cannot claim the
same job because the selection and the transition are a single atomic statement,
not a read followed by a write.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from alea._uuid7 import uuid7str
from alea.api.db import AsyncDatabase
from alea.api.views import JobKind, JobState, JobStatusOut
from alea.io.artefacts import utcnow
from alea.logging import get_logger

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 10.0
"""How often a running job refreshes its liveness."""

STALE_AFTER_SECONDS = 60.0
"""How long without a heartbeat a worker is presumed dead.

Six heartbeat intervals: long enough that a garbage-collection pause or a
loaded machine does not falsely interrupt a healthy job, short enough that a
caller is not left polling for minutes after a crash.
"""

JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
	job_id        TEXT PRIMARY KEY,
	kind          TEXT NOT NULL,
	status        TEXT NOT NULL,
	request       TEXT NOT NULL,
	result        TEXT,
	error         TEXT,
	progress      REAL NOT NULL DEFAULT 0.0,
	attempts      INTEGER NOT NULL DEFAULT 0,
	requested_by  TEXT NOT NULL DEFAULT '',
	created_at    TEXT NOT NULL,
	updated_at    TEXT NOT NULL,
	started_at    TEXT,
	finished_at   TEXT,
	heartbeat_at  TEXT,
	lease_owner   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, job_id);
CREATE INDEX IF NOT EXISTS jobs_kind ON jobs (kind);

-- One row per worker process. The heartbeat here, not on the job, is what lets
-- startup recovery tell a job whose worker is alive from one whose worker died.
CREATE TABLE IF NOT EXISTS job_workers (
	worker_id     TEXT PRIMARY KEY,
	started_at    TEXT NOT NULL,
	heartbeat_at  TEXT NOT NULL,
	host          TEXT NOT NULL DEFAULT ''
);
"""

TERMINAL = (JobState.SUCCEEDED.value, JobState.FAILED.value, JobState.INTERRUPTED.value)

JobHandler = Callable[[dict[str, Any], "JobContext"], Awaitable[dict[str, Any]]]
"""Runs one job. Receives the stored request and a context, returns the result."""


class JobNotFound(Exception):
	"""No job with that id."""


class JobNotFinished(Exception):
	"""A result was requested for a job that has not succeeded."""

	def __init__(self, job_id: str, status: JobState) -> None:
		super().__init__(f"job {job_id} is {status.value}, not succeeded")
		self.job_id = job_id
		self.status = status


class JobContext:
	"""Handed to a handler so it can report progress and check for cancellation."""

	def __init__(self, store: JobStore, job_id: str, attempt: int) -> None:
		assert job_id, "a job context needs a job id"
		assert attempt >= 1, "an attempt is one-based"
		self._store = store
		self.job_id = job_id
		self.attempt = attempt

	async def progress(self, fraction: float) -> None:
		"""Report how far along the job is, in [0, 1]."""
		assert 0.0 <= fraction <= 1.0, f"progress must be in [0, 1], got {fraction}"
		await self._store.set_progress(self.job_id, fraction)


class JobStore:
	"""A durable, restart-surviving queue of long-running work."""

	def __init__(
		self,
		path: str,
		*,
		heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
		stale_after: float = STALE_AFTER_SECONDS,
		database: AsyncDatabase | None = None,
	) -> None:
		assert path, "a job store needs a path"
		assert stale_after > heartbeat_interval > 0, (
			"a worker must be presumed dead strictly after it would next heartbeat, "
			f"got stale_after={stale_after}, interval={heartbeat_interval}"
		)
		self._database = database or AsyncDatabase(path, schema=JOB_SCHEMA)
		self.path = self._database.path
		self.heartbeat_interval = heartbeat_interval
		self.stale_after = stale_after
		self.worker_id = uuid7str()

	@property
	def database(self) -> AsyncDatabase:
		return self._database

	# -- lifecycle ---------------------------------------------------------

	async def connect(self) -> None:
		"""Open the database, register this worker, and recover abandoned jobs."""
		await self._database.connect()
		await self._register_worker()
		await self.recover()

	async def close(self) -> None:
		"""Deregister this worker and release the database handle."""
		try:
			await self._database.execute(
				"DELETE FROM job_workers WHERE worker_id = ?", (self.worker_id,)
			)
		except Exception as exc:  # pragma: no cover - shutdown best effort
			logger.warning("jobs.worker.deregister_failed", error=str(exc))
		await self._database.close()

	async def _register_worker(self) -> None:
		import socket

		await self._database.execute(
			"""
			INSERT INTO job_workers (worker_id, started_at, heartbeat_at, host)
			VALUES (?, ?, ?, ?)
			""",
			(self.worker_id, utcnow().isoformat(), utcnow().isoformat(), socket.gethostname()),
		)

	async def recover(self) -> int:
		"""Interrupt jobs whose worker is gone, and reap dead worker rows.

		Called at startup. A job left in ``running`` by a process that no longer
		exists must not be reported as still working -- that is the difference
		between a caller learning their solve died and a caller polling forever.

		Returns the number of jobs interrupted.
		"""
		cutoff = (utcnow() - timedelta(seconds=self.stale_after)).isoformat()
		now = utcnow().isoformat()

		interrupted = await self._database.execute(
			"""
			UPDATE jobs
			SET status = ?, finished_at = ?, updated_at = ?, error = COALESCE(
					error,
					'the worker running this job stopped heartbeating and is presumed dead'
				)
			WHERE status = ?
			  AND (lease_owner IS NULL OR lease_owner NOT IN (
					SELECT worker_id FROM job_workers WHERE heartbeat_at > ?
				))
			""",
			(JobState.INTERRUPTED.value, now, now, JobState.RUNNING.value, cutoff),
		)
		if interrupted:
			logger.warning("jobs.recovered.interrupted", count=interrupted)
		reaped = await self._database.execute(
			"DELETE FROM job_workers WHERE heartbeat_at <= ?", (cutoff,)
		)
		if reaped:
			logger.info("jobs.recovered.workers_reaped", count=reaped)
		return interrupted

	# -- submission --------------------------------------------------------

	async def submit(
		self,
		kind: JobKind,
		request: dict[str, Any],
		*,
		requested_by: str = "",
	) -> JobStatusOut:
		"""Enqueue a job. Returns immediately; the work happens elsewhere."""
		assert isinstance(kind, JobKind), f"kind must be a JobKind, got {type(kind).__name__}"
		assert isinstance(request, dict), "a job request is a JSON object"
		job_id = uuid7str()
		now = utcnow().isoformat()
		await self._database.execute(
			"""
			INSERT INTO jobs
				(job_id, kind, status, request, requested_by, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			(
				job_id,
				kind.value,
				JobState.QUEUED.value,
				json.dumps(request, sort_keys=True),
				requested_by,
				now,
				now,
			),
		)
		logger.info("jobs.submitted", job_id=job_id, kind=kind.value, requested_by=requested_by)
		status = await self.get(job_id)
		assert status is not None, "a job just submitted must be readable"
		return status

	# -- claiming ----------------------------------------------------------

	async def claim(self) -> tuple[str, JobKind, dict[str, Any], JobContext] | None:
		"""Atomically claim the oldest queued job, or return ``None``.

		The sub-select picks a candidate and the surrounding UPDATE transitions
		it in the same statement, so two workers racing cannot both win. A
		read-then-write would let both see ``queued`` and both start solving.
		"""
		now = utcnow().isoformat()
		row = await self._database.execute_returning(
			"""
			UPDATE jobs
			SET status = ?,
				lease_owner = ?,
				attempts = attempts + 1,
				started_at = COALESCE(started_at, ?),
				heartbeat_at = ?,
				updated_at = ?
			WHERE job_id = (
				SELECT job_id FROM jobs WHERE status = ? ORDER BY job_id LIMIT 1
			)
			RETURNING *
			""",
			(
				JobState.RUNNING.value,
				self.worker_id,
				now,
				now,
				now,
				JobState.QUEUED.value,
			),
		)
		if row is None:
			return None
		job_id = row["job_id"]
		kind = JobKind(row["kind"])
		request = json.loads(row["request"])
		context = JobContext(self, job_id, int(row["attempts"]))
		logger.info("jobs.claimed", job_id=job_id, kind=kind.value, attempt=row["attempts"])
		return job_id, kind, request, context

	# -- progress and liveness --------------------------------------------

	async def heartbeat(self, job_id: str) -> None:
		"""Refresh a running job's liveness. A no-op once the job is terminal."""
		now = utcnow().isoformat()
		await self._database.execute(
			"""
			UPDATE jobs SET heartbeat_at = ?, updated_at = ?
			WHERE job_id = ? AND status = ?
			""",
			(now, now, job_id, JobState.RUNNING.value),
		)

	async def set_progress(self, job_id: str, fraction: float) -> None:
		"""Record progress and, in the same write, refresh liveness."""
		assert 0.0 <= fraction <= 1.0, f"progress must be in [0, 1], got {fraction}"
		now = utcnow().isoformat()
		await self._database.execute(
			"""
			UPDATE jobs SET progress = ?, heartbeat_at = ?, updated_at = ?
			WHERE job_id = ? AND status = ?
			""",
			(fraction, now, now, job_id, JobState.RUNNING.value),
		)

	async def refresh_worker(self) -> None:
		"""Refresh this worker's own liveness, independent of any job."""
		await self._database.execute(
			"UPDATE job_workers SET heartbeat_at = ? WHERE worker_id = ?",
			(utcnow().isoformat(), self.worker_id),
		)

	# -- completion --------------------------------------------------------

	async def succeed(self, job_id: str, result: dict[str, Any]) -> None:
		"""Mark a job succeeded and store its result."""
		assert isinstance(result, dict), "a job result is a JSON object"
		now = utcnow().isoformat()
		changed = await self._database.execute(
			"""
			UPDATE jobs
			SET status = ?, result = ?, progress = 1.0, error = NULL,
				finished_at = ?, updated_at = ?, heartbeat_at = ?
			WHERE job_id = ?
			""",
			(JobState.SUCCEEDED.value, json.dumps(result, sort_keys=True), now, now, now, job_id),
		)
		if not changed:
			raise JobNotFound(f"no job {job_id} to complete")
		logger.info("jobs.succeeded", job_id=job_id)

	async def fail(self, job_id: str, error: str) -> None:
		"""Mark a job failed with the reason it failed."""
		assert error, "a failure must carry its reason, or it cannot be acted on"
		now = utcnow().isoformat()
		changed = await self._database.execute(
			"""
			UPDATE jobs
			SET status = ?, error = ?, finished_at = ?, updated_at = ?, heartbeat_at = ?
			WHERE job_id = ?
			""",
			(JobState.FAILED.value, error, now, now, now, job_id),
		)
		if not changed:
			raise JobNotFound(f"no job {job_id} to fail")
		logger.error("jobs.failed", job_id=job_id, error=error)

	async def requeue(self, job_id: str) -> None:
		"""Return an interrupted job to the queue, if it may be retried."""
		assert job_id, "requeue needs a job id"
		now = utcnow().isoformat()
		await self._database.execute(
			"""
			UPDATE jobs
			SET status = ?, lease_owner = NULL, heartbeat_at = NULL, updated_at = ?
			WHERE job_id = ? AND status = ?
			""",
			(JobState.QUEUED.value, now, job_id, JobState.INTERRUPTED.value),
		)
		logger.info("jobs.requeued", job_id=job_id)

	# -- reads -------------------------------------------------------------

	async def get(self, job_id: str) -> JobStatusOut | None:
		"""A job's current state, or ``None``."""
		assert job_id, "get needs a job id"
		row = await self._database.fetchone("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
		return _row_to_status(row) if row is not None else None

	async def require(self, job_id: str) -> JobStatusOut:
		"""A job's state, raising if it does not exist."""
		status = await self.get(job_id)
		if status is None:
			raise JobNotFound(f"no job {job_id}")
		return status

	async def result(self, job_id: str) -> dict[str, Any]:
		"""A succeeded job's result. Raises if the job is missing or unfinished."""
		assert job_id, "result needs a job id"
		row = await self._database.fetchone(
			"SELECT status, result FROM jobs WHERE job_id = ?", (job_id,)
		)
		if row is None:
			raise JobNotFound(f"no job {job_id}")
		state = JobState(row["status"])
		if state is not JobState.SUCCEEDED:
			raise JobNotFinished(job_id, state)
		if row["result"] is None:
			# A succeeded job with no result is a contradiction in the store; it
			# is worth its own error rather than returning an empty dict that a
			# caller renders as a zero.
			raise JobNotFinished(job_id, JobState.QUEUED)
		return json.loads(row["result"])

	async def list(
		self, *, status: JobState | None = None, kind: JobKind | None = None, limit: int = 100
	) -> list[JobStatusOut]:
		"""Jobs, newest first, optionally filtered."""
		assert limit > 0, "limit must be positive"
		sql = "SELECT * FROM jobs"
		clauses: list[str] = []
		params: list[str] = []
		if status is not None:
			clauses.append("status = ?")
			params.append(status.value)
		if kind is not None:
			clauses.append("kind = ?")
			params.append(kind.value)
		if clauses:
			sql += " WHERE " + " AND ".join(clauses)
		sql += " ORDER BY job_id DESC LIMIT ?"
		params.append(str(limit))
		rows = await self._database.fetchall(sql, tuple(params))
		return [_row_to_status(row) for row in rows]

	async def counts(self) -> dict[str, int]:
		"""How many jobs are in each state. Read by the health endpoint."""
		rows = await self._database.fetchall("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
		counts = {state.value: 0 for state in JobState}
		for row in rows:
			counts[row["status"]] = int(row["n"])
		return counts

	async def purge_finished(self, *, older_than_days: int = 30) -> int:
		"""Delete finished jobs older than a retention window.

		Terminal rows accumulate forever otherwise. Interrupted jobs are kept
		longer than the window only because they are terminal too -- a caller
		who never collected a result has had the retention period to do so.
		"""
		assert older_than_days > 0, "retention must be positive"
		cutoff = (utcnow() - timedelta(days=older_than_days)).isoformat()
		deleted = await self._database.execute(
			"""
			DELETE FROM jobs
			WHERE status IN (?, ?, ?) AND COALESCE(finished_at, updated_at) < ?
			""",
			(JobState.SUCCEEDED.value, JobState.FAILED.value, JobState.INTERRUPTED.value, cutoff),
		)
		if deleted:
			logger.info("jobs.purged", count=deleted, older_than_days=older_than_days)
		return deleted


def _row_to_status(row) -> JobStatusOut:
	assert row is not None, "cannot build a job status from no row"
	return JobStatusOut(
		job_id=row["job_id"],
		kind=JobKind(row["kind"]),
		status=JobState(row["status"]),
		created_at=datetime.fromisoformat(row["created_at"]),
		updated_at=datetime.fromisoformat(row["updated_at"]),
		progress=float(row["progress"]),
		attempts=int(row["attempts"]),
		error=row["error"],
		requested_by=row["requested_by"],
	)


# --------------------------------------------------------------------------
# The worker
# --------------------------------------------------------------------------


class JobWorker:
	"""Runs jobs outside the request path.

	One worker per process. It claims at most one job at a time, because the
	jobs it runs are CPU-bound solves: running two concurrently on the same
	machine makes both slower and neither finishes sooner.
	"""

	def __init__(
		self,
		store: JobStore,
		*,
		poll_interval: float = 1.0,
		on_start: Callable[[], None] | None = None,
	) -> None:
		assert poll_interval > 0, "a worker must not spin"
		self.store = store
		self.poll_interval = poll_interval
		self._handlers: dict[JobKind, JobHandler] = {}
		self._task: asyncio.Task[None] | None = None
		self._stopping = asyncio.Event()
		self._on_start = on_start

	def register(self, kind: JobKind, handler: JobHandler) -> None:
		"""Bind a handler to a job kind.

		A duplicate registration is an error: two handlers for one kind means
		whichever ran last silently wins, which is a bug that hides until the
		wrong one runs in production.
		"""
		assert isinstance(kind, JobKind), f"kind must be a JobKind, got {type(kind).__name__}"
		if kind in self._handlers:
			raise ValueError(f"a handler is already registered for {kind.value}")
		self._handlers[kind] = handler

	@property
	def registered_kinds(self) -> list[str]:
		"""Job kinds this worker can run."""
		return sorted(kind.value for kind in self._handlers)

	async def start(self) -> None:
		"""Begin the claim loop in the background."""
		assert self._task is None, "worker already started"
		if self._on_start is not None:
			self._on_start()
		self._stopping.clear()
		self._task = asyncio.create_task(self._run(), name="alea-job-worker")
		logger.info("jobs.worker.started", worker_id=self.store.worker_id, kinds=self.registered_kinds)

	async def stop(self) -> None:
		"""Stop after the current job, without abandoning it mid-flight."""
		self._stopping.set()
		if self._task is not None:
			self._task.cancel()
			# Awaiting the cancelled task is what makes shutdown ordered; the
			# CancelledError it raises is the expected outcome, not a failure.
			with contextlib.suppress(asyncio.CancelledError):
				await self._task
			self._task = None
		logger.info("jobs.worker.stopped", worker_id=self.store.worker_id)

	async def _run(self) -> None:
		"""Claim and run jobs until stopped, refreshing liveness while idle."""
		while not self._stopping.is_set():
			try:
				await self.store.refresh_worker()
				claimed = await self.store.claim()
			except asyncio.CancelledError:
				raise
			except Exception as exc:  # a broken store must not kill the worker
				logger.error("jobs.worker.claim_failed", error=str(exc))
				await asyncio.sleep(self.poll_interval)
				continue

			if claimed is None:
				# Waiting on the stop event rather than sleeping means a shutdown
				# interrupts the idle poll immediately instead of after the full
				# interval. The timeout is the ordinary case.
				with contextlib.suppress(TimeoutError):
					await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
				continue

			job_id, kind, request, context = claimed
			await self._run_one(job_id, kind, request, context)

	async def _run_one(
		self, job_id: str, kind: JobKind, request: dict[str, Any], context: JobContext
	) -> None:
		"""Run one job, keeping its liveness fresh and recording how it ended."""
		handler = self._handlers.get(kind)
		if handler is None:
			await self.store.fail(
				job_id, f"no handler registered for {kind.value}; registered: {self.registered_kinds}"
			)
			return

		heartbeat = asyncio.create_task(self._heartbeat_loop(job_id))
		try:
			result = await handler(request, context)
			await self.store.succeed(job_id, result)
		except asyncio.CancelledError:
			# Shutdown while a job was in flight. The job is left ``running``
			# with a heartbeat that will go stale, so recovery reports it as
			# interrupted rather than losing it.
			logger.warning("jobs.worker.cancelled_mid_job", job_id=job_id)
			raise
		except Exception as exc:
			logger.exception("jobs.worker.handler_failed", job_id=job_id, kind=kind.value)
			await self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
		finally:
			heartbeat.cancel()
			# The heartbeat task is cancelled here and may already have failed
			# on its own; either way it is finished and its outcome is not the
			# job's outcome, which was recorded above.
			with contextlib.suppress(asyncio.CancelledError, Exception):
				await heartbeat

	async def _heartbeat_loop(self, job_id: str) -> None:
		"""Refresh a running job's liveness until cancelled."""
		while True:
			await asyncio.sleep(self.store.heartbeat_interval)
			try:
				await self.store.heartbeat(job_id)
			except Exception as exc:  # pragma: no cover - liveness best effort
				logger.warning("jobs.worker.heartbeat_failed", job_id=job_id, error=str(exc))


__all__ = [
	"HEARTBEAT_INTERVAL_SECONDS",
	"JOB_SCHEMA",
	"STALE_AFTER_SECONDS",
	"JobContext",
	"JobHandler",
	"JobNotFinished",
	"JobNotFound",
	"JobStore",
	"JobWorker",
]
