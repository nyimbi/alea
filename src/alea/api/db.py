# SPDX-License-Identifier: MIT
"""Async SQLite access, shared by the job store, the key store and the review queue.

The plan (11-layer8 §3.2, 10-layer7 §6.1) puts three things in SQLite: durable
jobs, API keys, and the signal review queue. All three are the same problem --
a small transactional record that must outlive the process -- so the connection
handling lives once, here, rather than three times with three sets of bugs.

``sqlite3`` is synchronous and this package is async throughout, so every
statement runs in a worker thread. A blocking call on the event loop would stall
every other request in flight, which is the same defect as calling a solver
inline (11-layer8 §2.3) one level down.

A connection is opened per operation rather than held. SQLite connection objects
are not thread-safe, and a pooled connection handed to ``asyncio.to_thread``
lands on an arbitrary worker thread. Opening a connection to a local file is
tens of microseconds; the correctness is worth more than the microseconds.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from alea.config.paths import resolve
from alea.logging import get_logger

logger = get_logger(__name__)

_ROW_FACTORY = sqlite3.Row


def _connect(path: Path) -> sqlite3.Connection:
	"""Open one short-lived connection with the pragmas this package needs.

	``busy_timeout`` is per connection, not per database, so it is set on every
	open. Without it a concurrent writer raises ``database is locked`` at the
	worst moment -- when a solve has just finished and the result is being
	written.
	"""
	connection = sqlite3.connect(path, timeout=5.0)
	connection.row_factory = _ROW_FACTORY
	connection.execute("PRAGMA busy_timeout = 5000")
	connection.execute("PRAGMA foreign_keys = ON")
	return connection


class AsyncDatabase:
	"""A SQLite database whose statements do not block the event loop.

	``schema`` is an idempotent DDL script (``CREATE TABLE IF NOT EXISTS ...``)
	run once at connect. Two of these against the same file is safe: the second
	sees the tables and changes nothing.
	"""

	def __init__(self, path: str | Path, *, schema: str = "", wal: bool = True) -> None:
		assert path, "a database needs a path"
		assert isinstance(schema, str), "schema must be DDL text"
		self.path = resolve(path)
		self._schema = schema
		self._wal = wal
		self._ready = False
		self._lock = asyncio.Lock()

	# -- lifecycle ---------------------------------------------------------

	async def connect(self) -> None:
		"""Create the parent directory, enable WAL, and apply the schema once."""
		assert not self._ready or self.path.exists(), "ready database has no file"
		async with self._lock:
			if self._ready:
				return
			self.path.parent.mkdir(parents=True, exist_ok=True)

			def _prepare() -> None:
				connection = _connect(self.path)
				try:
					if self._wal:
						# WAL lets a reader proceed while a writer holds the file.
						# The job store is read on every poll and written on every
						# heartbeat, so the two overlap constantly.
						connection.execute("PRAGMA journal_mode = WAL")
					if self._schema:
						connection.executescript(self._schema)
					connection.commit()
				finally:
					connection.close()

			await asyncio.to_thread(_prepare)
			self._ready = True
		logger.info("db.connect", path=str(self.path))
		assert self._ready, "connect returned without marking the database ready"

	async def close(self) -> None:
		"""Mark the database unusable. Connections are per-operation, so nothing to release."""
		self._ready = False

	def with_schema(self, extra: str) -> AsyncDatabase:
		"""Add DDL to be applied at connect. Returns ``self`` for chaining.

		Two concerns sharing one file (the job store and the response cache) each
		contribute their tables before the single connect. Applied before
		``connect`` only: adding DDL after the database is open would mean a
		table that exists in one process and not another.
		"""
		assert isinstance(extra, str), "schema additions are DDL text"
		if self._ready:
			raise RuntimeError("cannot add schema to an already-connected database")
		self._schema = f"{self._schema}\n{extra}"
		return self

	def _require_ready(self) -> None:
		if not self._ready:
			raise RuntimeError(
				f"database {self.path} used before connect(); the application "
				f"lifespan must await connect() first"
			)

	# -- statements --------------------------------------------------------

	async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
		"""Run one statement, returning the affected row count."""
		assert sql.strip(), "empty SQL"
		self._require_ready()

		def _run() -> int:
			connection = _connect(self.path)
			try:
				cursor = connection.execute(sql, params)
				connection.commit()
				return cursor.rowcount
			finally:
				connection.close()

		return await asyncio.to_thread(_run)

	async def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> int:
		"""Run one statement over many parameter tuples in a single transaction."""
		assert sql.strip(), "empty SQL"
		self._require_ready()
		if not rows:
			return 0

		def _run() -> int:
			connection = _connect(self.path)
			try:
				cursor = connection.executemany(sql, rows)
				connection.commit()
				return cursor.rowcount
			finally:
				connection.close()

		return await asyncio.to_thread(_run)

	async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
		"""Run a query and return the first row, or ``None``."""
		assert sql.strip(), "empty SQL"
		self._require_ready()

		def _run() -> sqlite3.Row | None:
			connection = _connect(self.path)
			try:
				return connection.execute(sql, params).fetchone()
			finally:
				connection.close()

		return await asyncio.to_thread(_run)

	async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
		"""Run a query and return every row."""
		assert sql.strip(), "empty SQL"
		self._require_ready()

		def _run() -> list[sqlite3.Row]:
			connection = _connect(self.path)
			try:
				return list(connection.execute(sql, params).fetchall())
			finally:
				connection.close()

		return await asyncio.to_thread(_run)

	async def execute_returning(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
		"""Run a mutating statement with a ``RETURNING`` clause and return its row.

		``UPDATE ... RETURNING`` is what makes claiming a job atomic: the
		sub-select and the state transition happen in one statement, so two
		workers cannot both claim the same row.
		"""
		assert "RETURNING" in sql.upper(), "execute_returning needs a RETURNING clause"
		self._require_ready()

		def _run() -> sqlite3.Row | None:
			connection = _connect(self.path)
			try:
				row = connection.execute(sql, params).fetchone()
				connection.commit()
				return row
			finally:
				connection.close()

		return await asyncio.to_thread(_run)


__all__ = ["AsyncDatabase"]
