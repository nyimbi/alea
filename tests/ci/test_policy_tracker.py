# SPDX-License-Identifier: MIT
"""The monthly policy tracker: the producer, the stage, and the round trip.

`policy_tracker` is the scanning layer's one report section, and the register
recorded its blocker as "the section reads a path the design does not write".
The first half of that is a *feature*: `scanning.integrate` writes proposals to
a review queue rather than to a dated artefact, because a proposal is not a fact
until a human accepts it. What the entry missed is that the confirmed set is
readable -- `ReviewQueue.confirmed_signals()` returns exactly the signals a
human, or a recorded auto-acceptance, has accepted.

**The line this module exists to hold.** A tracker built from the *staging
directory* would publish unreviewed claims as policy changes, and it would look
identical in a report: the same country rows, the same counts, a bigger number.
So the assertion that matters is not "the section rendered" but "a pending
signal is not in it". `test_a_pending_signal_is_not_a_policy_change` is that
assertion, and it is the one a producer reading proposals would fail.

**Why the country is the row and not the change.** The section declares
``["Country", "Change", "Basis"]`` -- one numeric column, so `_rows_for` binds
the primary directly. A signal naming no country is counted under
``"unspecified"`` rather than dropped: dropping it would make the tracker's
total disagree with the queue's confirmed count for a reason no reader could
see, which is the "declared is not produced" failure in its counting form.

The last test is the only one that discharges the register's claim: the frame is
projected, a monthly report is generated, and the section is read back out of
it.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from alea.config.paths import resolve
from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage, registered_stages
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from alea.scanning.review import ReviewQueue
from alea.scanning.service import policy_tracker_to_artefact
from alea.signals.models import Signal, SignalType
from tests.ci.test_market_report_sections import _config

ISSUE_DATE = date(2030, 1, 15)
PERIOD_END = date(2029, 12, 31)


def _signal(
	*,
	country: str | None,
	description: str,
	signal_id: str,
	kind: SignalType = SignalType.POLICY_CHANGE,
) -> Signal:
	"""One extracted claim, as the extractor would hand it to the queue."""
	return Signal(
		signal_id=signal_id,
		signal_type=kind,
		confidence=0.9,
		source_document_id=f"doc-{signal_id}",
		source_url=f"https://example.invalid/{signal_id}",
		source_name="test-feed",
		country_iso=country,
		description=description,
	)


def _queue(tmp_path: Path) -> ReviewQueue:
	"""A queue where the *stage* looks for one, so no test writes the shared one.

	The location is load-bearing rather than convenient: ``_config`` points
	``paths.results`` at ``tmp_path``, and `build_policy_tracker` resolves the
	queue under it. A queue at ``tmp_path / "review.sqlite"`` would leave the
	stage reading a file nothing wrote, and the round-trip test would fail for
	a reason that has nothing to do with the section.
	"""
	return ReviewQueue(tmp_path / "results" / "scanning" / "review.sqlite")


def _confirmed(queue: ReviewQueue, signals: list[Signal]) -> None:
	"""Enqueue then confirm, which is the only path to the tracker's input.

	Confirmation is done through the queue's own `confirm`, not by writing a
	status, because the point of the producer is that it reads what the review
	workflow produced. A fixture that wrote ``status='confirmed'`` directly would
	test a query against a shape the workflow never creates.
	"""

	async def _run() -> None:
		from alea.scanning.score import score_signals

		scored = score_signals(signals, corroboration={s.signal_id: 0 for s in signals})
		await queue.enqueue_many([(signal, breakdown, []) for signal, breakdown, _ in scored])
		for signal, _breakdown, _decision in scored:
			await queue.confirm(signal.signal_id, "analyst:test", reason="reviewed")
		await queue.aclose()

	asyncio.run(_run())


def test_the_stage_is_registered():
	"""A `@stage` in a module `_REGISTRATION_MODULES` omits registers nothing."""
	assert "policy_tracker" in registered_stages(), (
		"`policy_tracker` did not register; `alea.scanning.service` is missing from "
		"`_REGISTRATION_MODULES`, so the stage is written, decorated and unreachable"
	)


def test_the_frame_carries_the_columns_the_section_declares(tmp_path: Path):
	"""One row per country, with the section's own two columns.

	``["Country", "Change", "Basis"]`` -- one numeric column, so the reader
	binds the primary into ``Change`` and the row needs no extras.
	"""
	queue = _queue(tmp_path)
	_confirmed(
		queue,
		[
			_signal(country="KE", description="Feed-in tariff revised", signal_id="s1"),
			_signal(country="KE", description="Licensing fee waived", signal_id="s2"),
			_signal(country="NG", description="Fuel subsidy withdrawn", signal_id="s3"),
		],
	)

	out = tmp_path / "policy_tracker.parquet"
	frame = policy_tracker_to_artefact(out, queue=queue)

	assert list(frame.columns) == ["label", "value", "unit"]
	counts = dict(zip(frame["label"], frame["value"], strict=True))
	assert counts == {"KE": 2.0, "NG": 1.0}, (
		f"the tracker counted {counts}; two Kenyan and one Nigerian policy change "
		f"were confirmed, so a different tally means the grouping or the filter is wrong"
	)


def test_a_pending_signal_is_not_a_policy_change(tmp_path: Path):
	"""The line the whole design rests on, asserted on the numbers.

	A proposal awaiting review is not a fact. A producer that read
	`data/processed/scanning/proposals/` instead of the confirmed set would
	publish it as a policy change, and the report would look identical -- same
	rows, same shape, a bigger count. Distinctness is the check that catches it.
	"""

	async def _enqueue_only() -> None:
		from alea.scanning.score import score_signals

		pending = _signal(country="TZ", description="Draft policy circulated", signal_id="p1")
		scored = score_signals([pending], corroboration={"p1": 0})
		await queue.enqueue_many([(s, b, []) for s, b, _ in scored])
		await queue.aclose()

	queue = _queue(tmp_path)
	_confirmed(queue, [_signal(country="KE", description="Tariff revised", signal_id="c1")])
	asyncio.run(_enqueue_only())

	frame = policy_tracker_to_artefact(tmp_path / "x.parquet", queue=queue)
	counts = dict(zip(frame["label"], frame["value"], strict=True))

	assert "TZ" not in counts, (
		f"an unreviewed signal reached the tracker: {counts}. A proposal is not a "
		f"fact, and a tracker that counts one publishes a claim no human accepted"
	)
	assert counts == {"KE": 1.0}, f"the confirmed count is wrong: {counts}"


def test_a_signal_with_no_country_is_counted_not_dropped(tmp_path: Path):
	"""A continental policy change is still a change.

	Dropping it would make the tracker's total disagree with the queue's
	confirmed count for a reason no reader could see -- the counting form of
	"declared is not produced".
	"""
	queue = _queue(tmp_path)
	_confirmed(
		queue,
		[
			_signal(country="KE", description="Tariff revised", signal_id="k1"),
			_signal(country=None, description="Continental framework adopted", signal_id="r1"),
		],
	)

	frame = policy_tracker_to_artefact(tmp_path / "x.parquet", queue=queue)
	counts = dict(zip(frame["label"], frame["value"], strict=True))

	assert counts == {"KE": 1.0, "unspecified": 1.0}, (
		f"a signal naming no country was {counts}; it must be counted under "
		f"'unspecified' rather than dropped, or the tracker's total silently "
		f"disagrees with the review queue"
	)


def test_a_non_policy_signal_is_not_a_policy_change(tmp_path: Path):
	"""The queue holds every signal type; the section asks for one.

	A generation-investment signal confirmed this month is not a regulatory
	change, and counting it would make the tracker a total of the queue rather
	than a tracker of policy.
	"""
	queue = _queue(tmp_path)
	_confirmed(
		queue,
		[
			_signal(country="KE", description="Tariff revised", signal_id="p1"),
			_signal(
				country="KE",
				description="200 MW solar park approved",
				signal_id="g1",
				kind=SignalType.GENERATION_INVESTMENT,
			),
		],
	)

	frame = policy_tracker_to_artefact(tmp_path / "x.parquet", queue=queue)
	counts = dict(zip(frame["label"], frame["value"], strict=True))

	assert counts == {"KE": 1.0}, (
		f"the tracker counted {counts}; one policy change and one investment were "
		f"confirmed, so a tally of two means the signal type filter is not applied"
	)


def test_the_register_moved_with_the_producer():
	"""A slug in `PRODUCERS` is a claim, and closing the gap moves two registers."""
	assert PRODUCERS["policy_tracker"] == "scanning.service.policy_tracker_to_artefact"
	assert PROJECTED["policy_tracker"] == "project_policy_tracker"
	assert "policy_tracker" not in UNPRODUCED


def test_the_section_leaves_the_missing_list_and_renders(tmp_path: Path):
	"""The round trip, asserted on the measurement the register entry is about.

	`policy_tracker` is optional to the monthly cadence, so its absence warned
	rather than raised -- which is why it stayed missing through every green
	suite while the register carried it. So the first assertion is
	`unprojected_sections`: the slug must *leave* the missing list, which is
	the claim closing the entry actually makes. The second is the rendered
	table, because an artefact at the declared path that the reader cannot bind
	would move the first measurement and leave the report just as empty.
	"""
	from alea.reporting.projection import project_section, unprojected_sections
	from alea.reporting.service import _section_from_spec, section_by_slug

	config = _config(tmp_path)
	queue = _queue(tmp_path)
	_confirmed(
		queue,
		[
			_signal(country="KE", description="Tariff revised", signal_id="r1"),
			_signal(country="NG", description="Subsidy withdrawn", signal_id="r2"),
		],
	)

	before = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "policy_tracker" in before, (
		f"the fixture already has a projected policy_tracker, so it cannot show "
		f"the projection closing the gap: {before}"
	)

	stage_out = resolve(config.paths.processed) / "policy_tracker.parquet"
	build_stage("policy_tracker", config, stage_out, parameters={})
	frame, _ = read_artefact(stage_out)
	assert len(frame) == 2, f"the stage wrote {len(frame)} rows, not two"

	project_section(ReportCadence.MONTHLY, "policy_tracker", stage_out, config, as_of=ISSUE_DATE)

	after = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "policy_tracker" not in after, (
		f"the section is still unprojected after its artefact was written: {after}"
	)

	spec = section_by_slug(ReportCadence.MONTHLY, "policy_tracker")
	warnings: list[str] = []
	rendered = _section_from_spec(spec, config, PERIOD_END, warnings)
	assert rendered is not None, (
		f"the section did not assemble from the artefact it declares: {warnings}"
	)
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one"
	)
	table = rendered.tables[0]
	assert table.columns == ["Country", "Change", "Basis"], (
		f"the table's headers are {table.columns}, not the section's declared columns"
	)
	assert len(table.rows) == 2, f"the section rendered {len(table.rows)} rows, not two"
