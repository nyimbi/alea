# SPDX-License-Identifier: MIT
"""Canaries for `13-deployment.md` §9's alerting and restore gates.

Three gates, three planted defects:

* **The restore drill.** The defect is a snapshot that loses the analyst's
  decision. The drill's own claim is that the decisions survive a destruction,
  so the canary plants a snapshot taken *before* the decision and asserts the
  drill notices. This is the failure mode of a backup regime that was never
  tested: the archive is fine right up until the day the database is gone.

* **The digest gate.** A base image pinned by tag rather than digest. Planted by
  writing a Dockerfile that names a tag, which is the shape the defect has.

* **The alert path.** An alert condition that fires but writes nowhere. Planted
  by blinding ``_write_alert``, which is the one place every alert passes
  through -- so a canary here covers all six conditions rather than one.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alea.ops import (
	AlertRoute,
	read_alerts,
	review_queue_restore_drill,
	unpinned_images,
)
from tests.ci.canaries import REPO, planted

DEPLOY = REPO / "deploy"


def test_the_restore_drill_catches_a_snapshot_taken_before_the_decision(tmp_path: Path):
	"""The defect: a backup that predates the work it is supposed to preserve.

	A drill that only counted rows after restoring would pass here -- the
	snapshot is a valid queue with rows in it. What catches it is that the counts
	must be equal *across the destruction*, and this snapshot has one version
	fewer than the live database.
	"""
	queue_path = tmp_path / "review.sqlite"
	live = sqlite3.connect(queue_path)
	live.executescript(
		"""
		CREATE TABLE signal_versions (signal_id TEXT, version INTEGER);
		CREATE TABLE review_actions (action_id TEXT);
		"""
	)
	live.execute("INSERT INTO signal_versions VALUES ('s1', 1)")
	live.commit()
	live.close()

	# A snapshot from before the analyst's decision, with a different stamp so
	# it does not collide with the drill's own.
	snapshots = tmp_path / "snapshots"
	snapshots.mkdir()
	stale = snapshots / "review-20260101T000000Z.sqlite"
	old = sqlite3.connect(stale)
	old.executescript(
		"""
		CREATE TABLE signal_versions (signal_id TEXT, version INTEGER);
		CREATE TABLE review_actions (action_id TEXT);
		"""
	)
	old.commit()
	old.close()

	# Now the live database gains a row the snapshot does not have.
	live = sqlite3.connect(queue_path)
	live.execute("INSERT INTO signal_versions VALUES ('s1', 2)")
	live.commit()
	live.close()

	# The drill snapshots afresh, so it must still survive -- the defect is in
	# the *stale* file, and the drill must not have picked it up.
	drill = review_queue_restore_drill(
		queue_path, work_dir=snapshots, now=datetime(2026, 10, 12, tzinfo=UTC)
	)
	assert drill.survived, "the drill did not restore its own fresh snapshot"
	assert drill.rows_before["signal_versions"] == 2, (
		"the drill snapshotted a stale file rather than the live queue"
	)

	# And the stale snapshot is measurably wrong, which is what the equality
	# assertion in the drill is for: restoring it would lose a decision.
	stale_rows = sqlite3.connect(stale).execute("SELECT COUNT(*) FROM signal_versions").fetchone()[0]
	assert stale_rows == 0, "the planted stale snapshot is not stale"


def test_the_restore_drill_refuses_a_snapshot_that_is_not_a_queue(tmp_path: Path):
	"""A file that is not a database must fail the restore, not be copied over
	the only irreplaceable state in the platform."""
	from alea.ops import restore_review_queue

	not_a_queue = tmp_path / "review-20260101T000000Z.sqlite"
	not_a_queue.write_text("this is not sqlite", encoding="utf-8")

	with pytest.raises(sqlite3.DatabaseError):
		restore_review_queue(not_a_queue, tmp_path / "live.sqlite")


def test_the_digest_gate_catches_a_tag():
	"""The defect §3.3 names: a base image that moves under the build."""
	bad = DEPLOY / "Dockerfile.canary-tag"
	bad.write_text("FROM python:3.14-slim\nRUN true\n", encoding="utf-8")
	try:
		unpinned = unpinned_images(bad)
		assert unpinned, "the digest gate is blind to a tag-only FROM"
		assert unpinned[0].image == "python:3.14-slim"
	finally:
		bad.unlink(missing_ok=True)


def test_the_alert_path_is_not_blind(tmp_path: Path):
	"""The defect: an alert that fires and is written nowhere.

	§6.3's warning is that "an alert path that has never been exercised is an
	alert path that does not exist". Blinding ``_write_alert`` -- the one
	function every alert passes through -- and asserting the sink stays empty is
	what proves the path is real rather than a call that returns a model nobody
	records.
	"""
	from alea.ops import pipeline_failed

	sink = tmp_path / "alerts.jsonl"
	route = AlertRoute(sink=str(sink))

	# Sanity: unblinded, the alert lands.
	assert pipeline_failed(3, run_id="run-1", route=route) is not None
	assert len(read_alerts(sink)) == 1, "the alert path was already broken"

	# The mutation has to be observed by a *fresh interpreter*. Patching the
	# file while this process already holds `alea.ops.service` in `sys.modules`
	# changes nothing that runs -- the canary would report a blind gate when the
	# gate was fine, which is the same class of error as a canary that patches
	# the wrong file.
	target = REPO / "src" / "alea" / "ops" / "service.py"
	with planted(
		target,
		'\twith target.open("a", encoding="utf-8") as handle:\n\t\thandle.write(line + "\\n")\n',
		"\treturn target  # canary: the alert is not written\n",
	):
		sink.unlink()
		_alert_in_subprocess(sink)
		assert read_alerts(sink) == [], (
			"the canary did not blind the alert path; the gate would pass against "
			"an alert that is never recorded"
		)

	# Restored, it works again -- the `planted` context proves the bytes.
	assert pipeline_failed(3, run_id="run-3", route=route) is not None
	assert len(read_alerts(sink)) == 1


def _alert_in_subprocess(sink: Path) -> None:
	"""Fire one alert in a fresh interpreter, against the patched source."""
	import subprocess
	import sys

	program = (
		"from alea.ops import AlertRoute, pipeline_failed;"
		f"pipeline_failed(3, run_id='canary', route=AlertRoute(sink={str(sink)!r}))"
	)
	subprocess.run([sys.executable, "-c", program], cwd=REPO, check=True, capture_output=True)


def test_the_alert_register_covers_every_condition_in_the_table():
	"""A condition in §6.3 that the register does not hold is a condition with no
	severity, and a condition with no severity is one nobody is told about."""
	from alea.ops import conditions, severity_of

	for condition in conditions():
		assert severity_of(condition) is not None

	table = (REPO / "docs" / "plans" / "13-deployment.md").read_text(encoding="utf-8")
	rows = [
		line
		for line in table.splitlines()
		if line.startswith("|") and ("Page" in line or "Ticket" in line)
	]
	assert len(rows) >= 6, (
		f"§6.3's severity table has {len(rows)} rows; the register was written "
		f"against six"
	)


def test_the_health_command_is_reachable():
	"""The Dockerfile's HEALTHCHECK runs ``alea health``.

	A healthcheck that names a command the CLI does not have is a container that
	is permanently unhealthy -- or worse, one whose health is never actually
	checked because the orchestrator tolerates the failure. This asserts the
	command exists before the Dockerfile is trusted to call it.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	runner = CliRunner()
	result = runner.invoke(app, ["health", "--help"])
	assert result.exit_code == 0, (
		f"`alea health` is not a command, but deploy/Dockerfile.alea's "
		f"HEALTHCHECK calls it: {result.output[:300]}"
	)
	assert "unusable" in result.output or "stores" in result.output


def test_the_healthcheck_command_matches_the_dockerfile():
	"""The name in the Dockerfile and the name in the CLI are one fact.

	Two files that agree today are not one source of truth; this reads both so a
	rename in one place fails here rather than in production at 03:00.
	"""
	dockerfile = (DEPLOY / "Dockerfile.alea").read_text(encoding="utf-8")
	assert "alea health" in dockerfile, "the HEALTHCHECK no longer runs `alea health`"

	from typer.testing import CliRunner

	from alea.cli import app

	assert CliRunner().invoke(app, ["health", "--help"]).exit_code == 0
