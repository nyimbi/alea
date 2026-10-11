# SPDX-License-Identifier: MIT
"""The run log, read back.

Every pipeline invocation generates a UUID7 run id, threaded through logs,
artefact provenance and report footers (00-architecture §8). That is what makes
"which run produced this number" answerable -- but only if something can be
asked the question. This reads the run log the CLI appends to and answers it.

The log is JSON Lines, one record per run, appended by the CLI's ``_run`` entry
and closed by its exit line. It is read here rather than queried from the
logging backend because the run id is also on every artefact's provenance, and a
join across two systems is more to go wrong than a join across one file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from alea.api.views import RunOut
from alea.config.models import Config
from alea.config.paths import resolve
from alea.logging import get_logger

logger = get_logger(__name__)

RUN_LOG = "results/runs.jsonl"


class RunLog:
	"""Reads pipeline run records."""

	def __init__(self, config: Config) -> None:
		assert config is not None, "the run log needs the loaded configuration"
		self.config = config
		self.path: Path = resolve(RUN_LOG)

	def get(self, run_id: str) -> RunOut | None:
		"""One run's record, or ``None``.

		The file is scanned rather than indexed. It is one line per pipeline
		invocation -- tens per day, not millions -- so an index would be a second
		thing to keep consistent for no measurable gain.
		"""
		assert run_id, "get needs a run id"
		if not self.path.exists():
			return None
		record: dict[str, object] | None = None
		with self.path.open("r", encoding="utf-8") as handle:
			for line in handle:
				line = line.strip()
				if not line:
					continue
				try:
					entry = json.loads(line)
				except json.JSONDecodeError:
					# A torn final line is what a crash looks like in an
					# append-only log. Skipping it is correct; failing the whole
					# read because of it would hide every earlier run.
					logger.warning("runs.malformed_line", path=str(self.path))
					continue
				if entry.get("run_id") == run_id:
					record = entry
		return _to_run(record) if record is not None else None

	def list(self, *, limit: int = 100) -> list[RunOut]:
		"""The most recent runs, newest first."""
		assert limit > 0, "limit must be positive"
		if not self.path.exists():
			return []
		records: list[dict[str, object]] = []
		with self.path.open("r", encoding="utf-8") as handle:
			for line in handle:
				line = line.strip()
				if not line:
					continue
				try:
					records.append(json.loads(line))
				except json.JSONDecodeError:
					continue
		return [_to_run(record) for record in records[-limit:]][::-1]


_STATUSES = ("running", "succeeded", "failed")
"""The three states a run record may carry. Anything else is coerced to running."""


def _timestamp(value: object) -> datetime | None:
	"""A run log timestamp, or ``None`` if it is absent or unparseable.

	The log is written by a different process and may be from an older format,
	so a bad timestamp is dropped rather than raised: a run whose start time
	cannot be parsed is still a run worth listing, and a 500 here would take out
	the whole listing for one malformed line.
	"""
	if not value:
		return None
	try:
		return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
	except ValueError:
		logger.warning("runs.unparseable_timestamp", value=str(value)[:40])
		return None


def _to_run(record: dict[str, Any]) -> RunOut:
	assert record is not None, "cannot build a run from nothing"
	status = str(record.get("status", "running"))
	if status not in _STATUSES:
		status = "running"
	return RunOut(
		run_id=str(record.get("run_id", "")),
		component=str(record.get("component", "")),
		started_at=_timestamp(record.get("started_at")) or datetime.fromtimestamp(0),
		finished_at=_timestamp(record.get("finished_at")),
		status=cast("Literal['running', 'succeeded', 'failed']", status),
		artefacts=[str(a) for a in record.get("artefacts", [])],
		detail=str(record.get("detail", "")),
	)


__all__ = ["RUN_LOG", "RunLog"]
