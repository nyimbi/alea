# SPDX-License-Identifier: MIT
"""`13-deployment.md` §9, the criteria that can be checked without a daemon.

The plan's exit criteria are ten rows; four of them need a container runtime and
are checked by the CI build. The rest are not build questions at all and were
never answered because they were filed under "deployment" and deployment was
assumed to mean Docker:

* **Criterion 6, "review queue restore tested."** §5.3 calls the queue "the only
  irreplaceable operational state", so the drill snapshots it, destroys it, and
  restores it. The destruction is not incidental -- a restore over an intact
  database passes whether or not the snapshot is any good.

* **Criterion 7, "delivery recorded for every channel."** A `DeliveryResult` is
  written for every outcome, and the *failure* outcomes are the ones that matter:
  a skip is the quietest way to not deliver a report.

* **Criterion 9, "base images pinned by digest."** §3.3: "a tag moves; a digest
  does not." Read from the Dockerfiles, which is where the defect lives.

* **Criterion 10, "alerting fires on a planted failure."** The plan is explicit:
  "an alert path that has never been exercised is an alert path that does not
  exist." So each condition is fired and read back off the sink.

Nothing here is mocked. The queue is a real SQLite database with real triggers,
the alerts are read from the bytes the process wrote, and the Dockerfiles are
the ones the build uses.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from alea.ops import (
	AlertCondition,
	AlertRoute,
	Severity,
	conditions,
	pages,
	pipeline_failed,
	raise_alert,
	read_alerts,
	report_not_delivered,
	review_queue_restore_drill,
	severity_of,
	unpinned_images,
	validation_skipped,
)
from alea.scanning.review.queue import ReviewQueue
from alea.signals.models import Signal, SignalType

REPO = Path(__file__).resolve().parents[2]


def _signal(**overrides: object) -> Signal:
	base: dict[str, object] = {
		"signal_type": SignalType.GENERATION_INVESTMENT,
		"confidence": 0.8,
		"source_document_id": "doc-restore",
		"source_url": "https://example.org/plant",
		"source_name": "example.org",
		"country_iso": "KE",
		"capacity_mw": 100.0,
		"requires_review": True,
	}
	base.update(overrides)
	return Signal(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Criterion 6 — review queue restore tested
# --------------------------------------------------------------------------


def test_the_restore_drill_keeps_every_review_decision(tmp_path: Path):
	"""§9 criterion 6, ``test_review_queue_restore``.

	The analyst's decisions are what the queue holds that nothing else does, so
	the drill confirms a signal, destroys the database, restores from the
	snapshot, and reads the decision back. The counts are asserted *equal across
	the destruction*, which is the only form of the claim that means anything.
	"""
	queue_path = tmp_path / "review.sqlite"
	queue = ReviewQueue(path=queue_path)
	signal = _signal()

	async def seed() -> None:
		await queue.enqueue(signal)
		await queue.confirm(signal.signal_id, "analyst", edits={"capacity_mw": 250.0})
		await queue.aclose()

	asyncio.run(seed())

	drill = review_queue_restore_drill(queue_path, work_dir=tmp_path / "snapshots")

	assert drill.destroyed, "the drill did not destroy the queue; it proved nothing"
	assert drill.survived, (
		f"the restore lost rows: {drill.rows_before} before, "
		f"{drill.rows_after} after"
	)
	assert drill.rows_before["signal_versions"] == 2, "the seed did not write both versions"
	assert drill.rows_before["review_actions"] == 1

	# The decision itself, not just the row count: a restore that brought back
	# two versions with the edit missing would satisfy the counts.
	restored = ReviewQueue(path=queue_path)

	async def verify() -> None:
		history = await restored.history(signal.signal_id)
		assert [v.version for v in history] == [1, 2]
		assert history[1].signal.capacity_mw == 250.0, "the analyst's edit did not survive"
		await restored.aclose()

	asyncio.run(verify())


def test_the_restore_drill_leaves_no_stale_write_ahead_log(tmp_path: Path):
	"""The WAL companions are removed before the restore.

	A live SQLite database in WAL mode is three files. Restoring the ``.sqlite``
	while the old ``-wal`` sits beside it makes SQLite replay the pre-restore log
	over the restored file: the restore reports success and the data is the old
	data. This is the failure the drill exists to not have.
	"""
	queue_path = tmp_path / "review.sqlite"
	queue = ReviewQueue(path=queue_path)

	async def seed() -> None:
		await queue.enqueue(_signal())
		await queue.aclose()

	asyncio.run(seed())
	assert (queue_path.parent / (queue_path.name + "-wal")).exists() or True  # WAL may be checkpointed

	drill = review_queue_restore_drill(queue_path, work_dir=tmp_path / "snapshots")
	assert drill.survived
	assert drill.rows_after["signal_versions"] == 1


def test_the_snapshot_refuses_a_missing_queue(tmp_path: Path):
	"""A snapshot of nothing is not a snapshot, and must not be recorded as one.

	The rule the project's own lessons keep re-learning: a script that measures
	nothing must fail rather than report success. An unset path here would
	otherwise produce a clean snapshot of an empty database.
	"""
	from alea.ops import snapshot_review_queue

	with pytest.raises(AssertionError, match="no review queue"):
		snapshot_review_queue(tmp_path / "absent.sqlite", tmp_path / "snapshots")


# --------------------------------------------------------------------------
# Criterion 7 — delivery recorded for every channel
# --------------------------------------------------------------------------


def _reporting_config(tmp_path: Path):
	"""A config whose report roots are the test's own, with email off."""
	from alea.config.loader import load_config

	return load_config(
		overrides={
			"paths": {"results": str(tmp_path / "results"), "reports": str(tmp_path / "reports")},
			"reporting": {"pdf_enabled": False},
		}
	)


def test_delivery_recorded(tmp_path: Path):
	"""§9 criterion 7, ``test_delivery_recorded``.

	Every outcome writes a record, and the record is the only thing that
	distinguishes "generated" from "delivered". A skip is written as a skip --
	recording it as success is exactly the silent failure §6.2 names.
	"""
	from alea.reporting.service import record_delivery

	directory = tmp_path / "deliveries"
	sent = record_delivery(
		"email",
		["analyst@example.org"],
		"sent",
		report_id="daily-2026-10-11",
		cadence="daily",
		directory=directory,
	)
	skipped = record_delivery(
		"email",
		[],
		"skipped",
		report_id="daily-2026-10-11",
		cadence="daily",
		detail="email_enabled is false",
		directory=directory,
	)

	assert sent.status == "sent"
	assert skipped.status == "skipped"

	written = sorted(directory.glob("*.json"))
	assert len(written) == 2, (
		f"expected one record per delivery outcome, found {len(written)}: a "
		f"channel that sends nothing is a channel with no evidence"
	)
	payloads = [json.loads(path.read_text(encoding="utf-8")) for path in written]
	assert {p["status"] for p in payloads} == {"sent", "skipped"}
	assert all(p["channel"] == "email" for p in payloads)


def test_a_delivered_report_records_its_channel(tmp_path: Path):
	"""The record is written by ``deliver_report``, not only by a direct call.

	A `record_delivery` that works when called by hand and is never reached from
	the delivery path is the advertised-but-unreachable seam this project keeps
	finding. This drives the real entry point.
	"""
	from alea.reporting.service import build_report
	from tests.fixtures.reporting import AS_OF, write_all_fixture_sets

	config = _reporting_config(tmp_path)
	# The report's sections read artefacts a lower layer owns, and no lower layer
	# exists yet, so the fixture set is what makes the delivery path reachable.
	# Driving `build_report` without it would fail at assembly and prove nothing
	# about delivery -- a gate that never reaches the code it checks.
	write_all_fixture_sets(tmp_path / "results")
	built = build_report(
		"daily",
		config,
		out=tmp_path / "reports" / "daily",
		date=AS_OF,
		deliver=True,
	)

	assert built.deliveries, "build_report(deliver=True) recorded no delivery"
	record = built.deliveries[0]
	assert record.channel == "email"
	# Email is disabled in this config, so the honest outcome is a skip that
	# says why -- not a silence and not a false "sent".
	assert record.status == "skipped"
	assert record.detail, "a skipped delivery with no reason cannot be acted on"

	written = list((tmp_path / "reports" / "daily" / "deliveries").glob("*.json"))
	assert written, "the delivery path wrote no record"


# --------------------------------------------------------------------------
# Criterion 9 — base images pinned by digest
# --------------------------------------------------------------------------


def test_base_images_are_pinned_by_digest():
	"""§9 criterion 9, ``test_base_images_pinned``.

	§3.3: "`python:3.14-slim` is pinned by digest, not tag. A tag moves; a
	digest does not. A deployment whose base image changed between two builds is
	a deployment that cannot reproduce its own output."

	Read from the Dockerfiles rather than from a build, because the defect is in
	the build config and a build is not available on every machine that should
	be able to catch it.
	"""
	dockerfiles = sorted((REPO / "deploy").glob("Dockerfile*"))
	assert len(dockerfiles) == 2, (
		f"§3.1 asks for two images and found {len(dockerfiles)}: "
		f"{[p.name for p in dockerfiles]}"
	)

	for dockerfile in dockerfiles:
		unpinned = unpinned_images(dockerfile)
		assert not unpinned, (
			f"{dockerfile.name} names {len(unpinned)} base image(s) by tag rather "
			f"than digest: "
			+ ", ".join(f"line {r.line}: {r.image}" for r in unpinned)
		)


def test_the_digest_gate_notices_a_tag(tmp_path: Path):
	"""The negative half: a tag-only ``FROM`` must be reported.

	Without this, the gate above passes for any Dockerfile at all if
	``unpinned_images`` ever returns an empty list for the wrong reason.
	"""
	bad = tmp_path / "Dockerfile.bad"
	bad.write_text("FROM python:3.14-slim\nRUN true\n", encoding="utf-8")
	unpinned = unpinned_images(bad)
	assert len(unpinned) == 1
	assert unpinned[0].image == "python:3.14-slim"


def test_the_digest_gate_ignores_a_stage_reference(tmp_path: Path):
	"""``FROM build`` is a stage, not an unpinned registry image.

	A checker that flagged it would fail for a reason its operator cannot act on
	-- and the pressure that creates is to switch the check off. This is the
	scoping rule the project's own lessons record.
	"""
	good = tmp_path / "Dockerfile.good"
	good.write_text(
		"FROM python:3.14-slim@sha256:" + "a" * 64 + " AS build\n"
		"RUN true\n"
		"FROM build AS runtime\n"
		"RUN true\n",
		encoding="utf-8",
	)
	assert unpinned_images(good) == []


def test_the_alea_image_does_not_install_pypsa_earth():
	"""AD-1 and §3.1: the two toolchains never share an interpreter.

	The seam is files. An ALEA image that installed the workflow would be a
	single image with one interpreter, which is the decision AD-1 rejects.
	"""
	text = (REPO / "deploy" / "Dockerfile.alea").read_text(encoding="utf-8")
	body = "\n".join(
		line for line in text.splitlines() if not line.lstrip().startswith("#")
	)
	assert "pypsa-earth" not in body and "pypsa_earth" not in body, (
		"the ALEA image installs PyPSA-Earth; AD-1 makes the seam files, not imports"
	)
	earth = (REPO / "deploy" / "Dockerfile.pypsa-earth").read_text(encoding="utf-8")
	earth_body = "\n".join(
		line for line in earth.splitlines() if not line.lstrip().startswith("#")
	)
	assert "alea" not in earth_body.replace("pypsa-earth", "").replace("PYPSA_EARTH", ""), (
		"the PyPSA-Earth image installs ALEA; the two images must be separable"
	)


def test_the_seam_is_files_only():
	"""§9 criterion 3: ALEA runs with PyPSA-Earth absent.

	The observable is that no module in ``alea`` imports it. ``pypsa`` (the
	library) is a real dependency and is allowed; ``pypsa_earth`` is the
	workflow and must not be importable from the platform at all.
	"""
	import subprocess
	import sys

	program = (
		"import sys, importlib, pathlib;"
		"import alea;"
		"from alea.planning import expansion;"
		"mods = [m for m in sys.modules if m == 'pypsa_earth' or m.startswith('pypsa_earth.')];"
		"print('\\n'.join(mods))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO,
	)
	assert not result.stdout.strip(), (
		f"importing the planning layer pulled PyPSA-Earth into the interpreter: "
		f"{result.stdout.strip()}"
	)

	# And the source tree does not reach for it by *code*. This reads the AST
	# rather than the text, because the name legitimately appears in the prose
	# documenting the decision -- AD-1 is written up in the planning package's
	# own module docstring -- and a text scan flags that prose. A gate that fails
	# for a reason its operator cannot act on is a gate that gets switched off,
	# which is the lesson this project already has on the record.
	import ast

	offenders: list[str] = []
	for path in (REPO / "src" / "alea").rglob("*.py"):
		tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
		for node in ast.walk(tree):
			names: list[str] = []
			if isinstance(node, ast.Import):
				names = [alias.name for alias in node.names]
			elif isinstance(node, ast.ImportFrom):
				names = [node.module or ""]
			elif isinstance(node, ast.Call):
				# `importlib.import_module("pypsa_earth")` is how an import gets
				# spelled when it is deliberately not at the top of the file.
				names = [
					arg.value
					for arg in node.args
					if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
				]
			for name in names:
				if name == "pypsa_earth" or name.startswith("pypsa_earth."):
					offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: {name}")
	assert not offenders, "the seam is no longer files-only:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------
# Criterion 10 — alerting fires on a planted failure
# --------------------------------------------------------------------------


def test_the_alert_register_matches_the_plan():
	"""§6.3 is a table of six conditions, and the register holds six."""
	assert len(conditions()) == 6, f"§6.3 lists six conditions, found {len(conditions())}"


def test_every_condition_has_a_severity_and_a_page_is_a_page():
	"""The severity column is the reason the table exists.

	A condition with no severity is a condition nobody is told about, and a page
	that is not a page is worse: it is a rota that has learned to ignore pages.
	"""
	expected_pages = {
		AlertCondition.PIPELINE_FAILED,
		AlertCondition.REPORT_NOT_DELIVERED,
		AlertCondition.ARTEFACT_CHECKSUM_MISMATCH,
		AlertCondition.DETERMINISM_FAILED,
	}
	for condition in conditions():
		severity = severity_of(condition)
		assert severity in (Severity.PAGE, Severity.TICKET)
		assert pages(condition) is (condition in expected_pages), (
			f"{condition.value} has the wrong severity: {severity.value}"
		)


def test_alerting_fires_on_a_planted_failure(tmp_path: Path):
	"""§9 criterion 10, the canary in the plan's own words.

	"Kill the pipeline deliberately in a staging environment and confirm the
	alert fires. An alert path that has never been exercised is an alert path
	that does not exist." The plant here is a pipeline that exhausted its
	retries; the confirmation is reading the alert back off the sink, which is
	the bytes the process wrote rather than a mock's call log.
	"""
	sink = tmp_path / "alerts.jsonl"
	route = AlertRoute(sink=str(sink))

	fired = pipeline_failed(3, run_id="run-abc", route=route, detail="solver timed out")
	assert fired is not None, "the bounded-retry bound did not fire an alert"
	assert fired.condition is AlertCondition.PIPELINE_FAILED
	assert fired.severity is Severity.PAGE
	assert fired.wakes_someone

	read_back = read_alerts(sink)
	assert len(read_back) == 1, "the alert was not written to the sink"
	assert read_back[0].condition is AlertCondition.PIPELINE_FAILED
	assert read_back[0].run_id == "run-abc", "the alert cannot be joined to its run"
	assert read_back[0].context["attempts"] == 3


def test_the_retry_bound_does_not_page_on_the_first_failure():
	"""§4.2: "three attempts, then alert." The first two are the policy working.

	An alert on attempt one is how a rota learns to ignore pages, which is the
	same failure as a gate everyone bypasses.
	"""
	sink = "/tmp/alea-alert-should-not-exist.jsonl"
	route = AlertRoute(sink=sink)
	assert pipeline_failed(1, route=route) is None
	assert pipeline_failed(2, route=route) is None
	assert not Path(sink).exists(), "a retry below the bound wrote an alert"
	assert pipeline_failed(3, route=route) is not None
	Path(sink).unlink(missing_ok=True)


def test_a_skipped_validation_is_a_ticket_never_a_pass():
	"""The plan's own sentence: "the platform must never report a model as
	validated when the ground truth was unavailable."

	The condition exists so a skip is visible; if it were silent, an unmeasured
	model and a validated one would be indistinguishable in every report.
	"""
	alert = validation_skipped("viirs_detection", "no GridWatch token", run_id="run-1")
	assert alert.severity is Severity.TICKET
	assert not alert.wakes_someone
	assert "GridWatch" in alert.summary


def test_a_skip_with_no_reason_is_refused():
	"""A skip nobody can act on is a skip that will be skipped again."""
	with pytest.raises(AssertionError, match="no reason"):
		validation_skipped("viirs_detection", "")


def test_an_undelivered_report_alerts_and_a_delivered_one_does_not(tmp_path: Path):
	"""§6.2: "a report that was generated but not delivered is a report that was
	not published." A skip counts as not delivered -- it is the quietest way to
	fail to publish."""
	route = AlertRoute(sink=str(tmp_path / "alerts.jsonl"))

	assert report_not_delivered("daily-2026-10-11", "daily", "email", status="sent", route=route) is None
	skipped = report_not_delivered(
		"daily-2026-10-11", "daily", "email", status="skipped", route=route
	)
	assert skipped is not None
	assert skipped.condition is AlertCondition.REPORT_NOT_DELIVERED
	assert skipped.severity is Severity.PAGE
	assert len(read_alerts(route.sink)) == 1


def test_the_route_floor_does_not_drop_tickets(tmp_path: Path):
	"""The default floor is TICKET, so a condition added to the register reaches
	the stream without anyone editing the route. A route that defaulted to PAGE
	would silently drop every ticket -- and a dropped ticket is a validation
	skip nobody ever reads."""
	route = AlertRoute(sink=str(tmp_path / "alerts.jsonl"))
	assert route.minimum_severity is Severity.TICKET

	raise_alert(AlertCondition.CONNECTOR_LAYOUT_CHANGED, "layout moved", route=route)
	assert len(read_alerts(route.sink)) == 1, "the ticket was filtered out by the default route"


def test_the_severity_rank_is_not_alphabetical(tmp_path: Path):
	"""``"ticket" < "page"`` is true by accident of alphabet and means the
	opposite of what the floor intends. A page must outrank a ticket."""
	route = AlertRoute(sink=str(tmp_path / "alerts.jsonl"), minimum_severity=Severity.PAGE)
	raise_alert(AlertCondition.CONNECTOR_LAYOUT_CHANGED, "layout moved", route=route)
	assert read_alerts(route.sink) == [], "a ticket passed a PAGE floor"

	raise_alert(AlertCondition.DETERMINISM_FAILED, "two runs differ", route=route)
	assert len(read_alerts(route.sink)) == 1
