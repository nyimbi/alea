# SPDX-License-Identifier: MIT
"""The Layer 7 service: one entry point for a scan run (10-layer7 §8).

``ScanningService`` composes the stages — fetch, ingest, extract, score,
enqueue — and is what a scheduler or the CLI calls. The stages are separately
importable and separately testable; this class owns only the ordering and the
counts.

Two things it deliberately does **not** do:

* It does not integrate. Integration requires a human decision, and a service
  that runs on a schedule must not be able to make one.
* It does not auto-accept unless ``scanning.auto_accept_threshold`` is set
  *and* the queue has a measured precision for the signal type. With the
  default config, every signal it enqueues is pending.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from alea.config.models import Config, ScanningConfig
from alea.io.artefacts import utcnow
from alea.logging import get_logger
from alea.scanning.connectors.base import Connector, RawDocument
from alea.scanning.extract import Extractor
from alea.scanning.extract.llm import ExtractionConfig
from alea.scanning.ingest import ingest
from alea.scanning.review import ReviewQueue
from alea.scanning.score import SignalTypePrecision, decide_auto_accept, score_signals
from alea.scanning.views import ScanReport

logger = get_logger(__name__)

#: How far back a run looks when the caller does not say. A day is the longest
#: cadence in the connector table, so a run at any cadence sees everything the
#: previous run could have missed without re-fetching a week of feeds.
DEFAULT_LOOKBACK = timedelta(days=1)


class ScanningService:
	"""One scan run over a set of connectors."""

	def __init__(
		self,
		connectors: list[Connector],
		*,
		config: Config | None = None,
		scanning_config: ScanningConfig | None = None,
		queue: ReviewQueue | None = None,
		extractor: Extractor | None = None,
		llm_client: object | None = None,
	) -> None:
		if scanning_config is None and config is not None:
			scanning_config = config.scanning
		self.scanning = scanning_config or ScanningConfig()
		self.connectors = list(connectors)
		self.queue = queue or ReviewQueue()
		if extractor is not None:
			self.extractor = extractor
		else:
			try:
				self.extractor = Extractor(
					config=ExtractionConfig(
						model=self.scanning.llm_model,
						temperature=self.scanning.llm_temperature,
						seed=self.scanning.dedup_seed,
						cache=self.scanning.llm_cache,
					),
					client=llm_client,  # type: ignore[arg-type]
				)
			except ValueError as exc:
				# No chat-completions endpoint configured. The deterministic
				# extractors still run and still produce signals for documents
				# that name a capacity or an investment, so a scan without a
				# model degrades rather than refusing to start. Refusing here
				# would make the whole scanning layer depend on an env var that
				# only the classification stage needs.
				logger.warning("llm_unavailable_deterministic_only", error=str(exc))
				self.extractor = Extractor()

	async def fetch_all(self, since: datetime) -> list[RawDocument]:
		"""Fetch from every connector, isolating failures.

		A connector that raises must not stop the run: a dead RSS host would
		otherwise mean no tenders are scanned either. The failure is recorded in
		the connector's health, which the report carries.
		"""
		assert since.tzinfo is not None, "since must be timezone-aware"
		documents: list[RawDocument] = []
		for connector in self.connectors:
			try:
				documents.extend(await connector.fetch(since))
			except Exception as exc:  # noqa: BLE001 - one bad source must not stop the scan
				logger.error(
					"connector_failed",
					source=connector.source_name,
					error=str(exc),
					error_type=type(exc).__name__,
				)
		return documents

	def connector_health(self) -> list[dict[str, object]]:
		return [connector.health_check().model_dump(mode="json") for connector in self.connectors]

	def unhealthy_sources(self) -> list[str]:
		"""Connectors whose last fetch was neither ``ok`` nor ``no_new``."""
		return [
			connector.source_name
			for connector in self.connectors
			if not connector.health_check().is_healthy
		]

	async def run(
		self,
		*,
		since: datetime | None = None,
		lookback: timedelta = DEFAULT_LOOKBACK,
	) -> ScanReport:
		"""Fetch, deduplicate, extract, score, and enqueue. Returns a report."""
		moment = utcnow()
		window_start = since or (moment - lookback)
		logger.info("scan_start", since=window_start.isoformat(), connectors=len(self.connectors))

		documents = await self.fetch_all(window_start)
		kept, _ingestion, dedup = ingest(
			documents,
			num_perm=self.scanning.dedup_num_perm,
			threshold=self.scanning.dedup_threshold,
			seed=self.scanning.dedup_seed,
			connector_health=self.connector_health(),
		)

		# Corroboration is carried from the duplicate groups: a document kept
		# over three near-duplicates is a signal carried by four sources.
		corroboration_by_document = {
			group.representative_id: group.corroborating_ids for group in dedup.groups
		}

		signals, records = await self.extractor.extract_documents(
			kept, corroboration=corroboration_by_document
		)

		# The queue stores the corroborating *document* ids against the signal
		# they produced, so a reviewer sees which other outlets carried it.
		document_of_signal = {
			signal.signal_id: signal.source_document_id for signal in signals
		}
		corroboration_by_signal = {
			signal_id: corroboration_by_document.get(document_id, [])
			for signal_id, document_id in document_of_signal.items()
		}
		corroboration_counts = {
			signal_id: len(ids) for signal_id, ids in corroboration_by_signal.items()
		}

		precisions = await self._measured_precisions()
		scored = score_signals(
			signals,
			corroboration=corroboration_counts,
			threshold=self.scanning.auto_accept_threshold,
			precision_by_type=precisions,
		)

		auto_accepted = 0
		model = self.extractor.llm.config.model if self.extractor.llm is not None else None
		prompt_version = (
			self.extractor.llm.config.prompt_version if self.extractor.llm is not None else None
		)
		# One transaction for the batch, so the count below is the count that
		# committed. A per-signal loop that fails at entry 40 of 60 leaves 39
		# rows written and no report, and the next run re-extracts everything
		# without anyone learning the first batch half-landed.
		queued = await self.queue.enqueue_many(
			[
				(signal, breakdown, corroboration_by_signal.get(signal.signal_id, []))
				for signal, breakdown, _decision in scored
			],
			model=model,
			prompt_version=prompt_version,
		)
		enqueued = len(queued)
		for signal, _breakdown, decision in scored:
			if decision.auto_accepted:
				# An auto-acceptance is still a recorded decision: it appends a
				# confirmed version naming the machine as the analyst, so the
				# accuracy report can separate a machine confirmation from a
				# human one and the audit trail has no gap.
				await self.queue.confirm(
					signal.signal_id,
					"auto:precision-threshold",
					reason=decision.reason,
				)
				auto_accepted += 1

		report = ScanReport(
			since=window_start,
			documents_fetched=len(documents),
			documents_kept=len(kept),
			signals_extracted=len(signals),
			signals_enqueued=enqueued,
			signals_auto_accepted=auto_accepted,
			backlog=await self.queue.backlog(),
			review_queue_limit=self.scanning.review_queue_limit,
			llm_calls=self.extractor.calls,
			connector_health=self.connector_health(),
			unhealthy=self.unhealthy_sources(),
		)
		logger.info(
			"scan_complete",
			fetched=report.documents_fetched,
			kept=report.documents_kept,
			signals=report.signals_extracted,
			enqueued=report.signals_enqueued,
			auto_accepted=report.signals_auto_accepted,
			# The backlog goes to the log as well as to the report. The log is
			# what an operator reads at 03:00 when the dashboard is the thing
			# that is down, and a depth that appears only in an artefact is a
			# depth nobody sees while the pipeline is running.
			pending=report.backlog.pending,
			oldest_pending_hours=report.backlog.oldest_age_hours,
			backlog_over_limit=report.backlog.breaches(report.review_queue_limit),
			unhealthy=report.unhealthy,
			extraction_records=len(records),
		)
		return report

	async def _measured_precisions(self) -> dict[str, SignalTypePrecision]:
		"""Precisions measured from the review record, or nothing.

		Returns an empty map when no threshold is configured, so the common
		(default) path does not pay for the accuracy query.
		"""
		if self.scanning.auto_accept_threshold is None:
			return {}
		return await self.queue.auto_accept_precisions()

	async def aclose(self) -> None:
		"""Close connectors and the queue."""
		for connector in self.connectors:
			await connector.aclose()
		await self.queue.aclose()

	async def __aenter__(self) -> ScanningService:
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.aclose()


def policy_tracker_to_artefact(
	out: str | Path,
	*,
	queue: ReviewQueue | None = None,
	country: str | None = None,
) -> pd.DataFrame:
	"""Write the monthly policy tracker's frame from confirmed policy signals.

	The frame `reporting/monthly.py`'s ``policy_tracker`` reads, whose columns
	are ``["Country", "Change", "Basis"]``. One numeric column, so `_rows_for`
	binds the primary directly and the row needs no extras -- the section is a
	count per country.

	**Which signals count, and why that is the whole design.** The register
	recorded this section as reading "a path the design does not write", and the
	half of that which is true is important: `scanning.integrate` stages a
	*proposal* to `data/processed/scanning/proposals/`, and a proposal is not a
	fact. Only a signal whose latest version a human (or the precision-threshold
	auto-acceptance, which appends a recorded decision naming the machine as the
	analyst) has confirmed reaches ``ReviewQueue.confirmed_signals()``. So this
	reads the queue's confirmed set and never the staging directory: a tracker
	built from proposals would publish unreviewed claims as policy changes.

	**The count is of confirmed changes, and a country is the row.** A signal
	with no ``country_iso`` is counted under ``"unspecified"`` rather than
	dropped: a regional or continental policy change is still a change, and
	dropping it would make the tracker's total disagree with the queue's
	confirmed count for a reason no reader could see.

	**The basis is FORECAST, not MEASURED.** A confirmed policy signal is a
	claim someone read in a document, and it reaches a report through the
	queue's own provenance. Calling it measured would let a news figure look
	like a metered one at the point a reader trusts it most.

	**The input is the queue's own checksum, and this function records it.**
	The artefact derives from a review queue rather than from a file a stage
	produced, so the queue is what it must name -- "which reviewed signals was
	this count built from" is the question a reader asks of a tracker six
	months later. `DerivedProvenance` refuses an empty input list and is right
	to. It is read here rather than taken as an argument because the caller
	that forgot was the pipeline's own stage, which passed ``[]`` whenever the
	queue did not exist yet and so raised on every run against a fresh tree.
	"""
	from collections import Counter

	from alea.io.artefacts import sha256_file
	from alea.io.pipeline import write_stage
	from alea.provenance.models import Basis, DerivedProvenance, Licence
	from alea.signals.models import SignalType

	review = queue or ReviewQueue()

	async def _confirmed() -> list[Any]:
		try:
			return await review.confirmed_signals()
		finally:
			if queue is None:
				await review.aclose()

	signals = asyncio.run(_confirmed())

	# Checksummed *after* the read, because the first connection is what
	# creates the file. Hashing first would record ``absent`` for a queue that
	# now exists, and the bytes the count was built from are the ones to name.
	# A queue that is still absent was never created, which means nothing was
	# ever enqueued: an empty confirmed set, not an error.
	inputs = (
		[f"sha256:{sha256_file(review.path)}"]
		if review.path.exists()
		else [f"absent:{review.path}"]
	)
	policies = [
		signal
		for signal in signals
		if str(signal.signal_type) == SignalType.POLICY_CHANGE.value
		and (country is None or signal.country_iso == country)
	]

	counts: Counter[str] = Counter()
	for signal in policies:
		counts[str(signal.country_iso or "unspecified")] += 1

	rows = [
		{"label": name, "value": float(total), "unit": "count"}
		for name, total in sorted(counts.items())
	]
	provenance = DerivedProvenance(
		source_id="scanning_policy_tracker",
		retrieved_at=utcnow(),
		licence=Licence.UNKNOWN,
		basis=Basis.FORECAST,
		uncertainty=0.0,
		uncertainty_basis="",
		notes=(
			"confirmed policy-change signals only; a proposal still awaiting "
			"review is not a fact and is not counted. The count is per country, "
			"with a signal naming none counted as 'unspecified'"
		),
		inputs=inputs,
		parameters={"confirmed_signals": len(signals), "policy_signals": len(policies)},
	)
	frame = pd.DataFrame(rows, columns=["label", "value", "unit"])
	write_stage(Path(out), frame, provenance, format="parquet")
	logger.info(
		"policy_tracker_to_artefact",
		out=str(out),
		countries=len(rows),
		policies=len(policies),
	)
	return frame


def extraction_accuracy_artefact(
	out: str | Path,
	*,
	queue: ReviewQueue | None = None,
) -> pd.DataFrame:
	"""Write the M3 extraction-accuracy validation artefact from the review record.

	`10-layer7-scanning.md` §10 criterion 8 is "extraction accuracy measured per
	signal type", and `12-quality.md` §5 registers the target as
	``extraction_accuracy`` with the ground truth "human review sample" and the
	pass condition "precision per signal type". `ReviewQueue.accuracy()` computes
	exactly that and was called by nothing in ``src/`` -- so the target had no
	artefact, ``missing_validation_targets()`` named it missing, and criterion 4
	("every validation target writes an artefact") was unmet by one.

	**The ground truth is the review record, and it is measured against humans
	only.** An auto-accepted signal is excluded from the precision and reported
	separately. The auto-acceptance threshold is *chosen* from this precision, so
	a measurement that counted machine confirmations would let the threshold
	accept signals on the strength of signals it had already accepted -- a loop
	that reports rising accuracy as it widens. ``machine_confirmed`` travels in
	the artefact so a reader can see how much of the queue a machine cleared.

	**A type with no human-reviewed signals is skipped, not passed.** Its
	precision is unmeasurable, and reporting it as 0.0 would read as a
	measurement that failed; reporting it as passed would be a fabricated
	result. It is named in ``skipped`` with its own reason, and the artefact's
	own validators refuse the alternatives: a ``passed`` status with no metrics
	does not construct, and an accuracy metric with no ``base_rate`` does not
	either. The base rate is the share of reviewed signals a human confirmed,
	which is the prevalence an accuracy has to be read against.

	**``basis`` is MEASURED and ``inputs`` names the queue's checksum.** The
	measurement is of a real review record, not a projection -- and the bytes it
	was taken from are what a reader re-checking it six months later needs.
	"""
	from alea.io.artefacts import sha256_file
	from alea.quality import ValidationStatus, validation_artefact, write_validation

	review = queue or ReviewQueue()

	async def _measure() -> Any:
		try:
			return await review.accuracy()
		finally:
			if queue is None:
				await review.aclose()

	report = asyncio.run(_measure())

	# Checksummed after the read, because the first connection is what creates
	# the file. A queue that is still absent was never created, which means
	# nothing was ever enqueued: an empty measurement, not an error.
	queue_input = (
		f"sha256:{sha256_file(review.path)}"
		if review.path.exists()
		else f"absent:{review.path}"
	)

	metrics: dict[str, float] = {}
	per_type: dict[str, dict[str, Any]] = {}
	skipped: list[str] = []
	reviewed = 0
	human_confirmed = 0
	machine = 0
	for key, row in sorted(report.by_signal_type().items()):
		machine += row.machine_confirmed
		if row.sample_size == 0:
			skipped.append(key)
			continue
		reviewed += row.sample_size
		human_confirmed += row.confirmed
		metrics[f"precision__{key}"] = row.precision
		per_type[key] = {
			"precision": row.precision,
			"sample_size": row.sample_size,
			"confirmed": row.confirmed,
			"rejected": row.rejected,
			"edited": row.edited,
			"machine_confirmed": row.machine_confirmed,
			"field_errors": row.field_errors,
		}

	# The base rate is over reviewed signals only, so it is the prevalence the
	# precision was measured against and not the prevalence of the queue.
	base_rate = human_confirmed / reviewed if reviewed else None

	if not metrics:
		# No human has reviewed anything yet. The target is skipped with its
		# reason rather than passed or failed: M3 is a measurement against a
		# labelled sample, and there is no sample.
		artefact = validation_artefact(
			"extraction_accuracy",
			"Human review sample",
			status=ValidationStatus.SKIPPED,
			reason=(
				f"no human-reviewed signals in the queue: "
				f"{len(report.rows)} extraction row(s) across "
				f"{len(report.by_signal_type())} signal type(s), none confirmed or "
				f"rejected by a human ({machine} machine confirmation(s) excluded, "
				f"which is not evidence)"
			),
			notes="M3 is measured against a labelled human sample; none exists yet",
		)
	else:
		artefact = validation_artefact(
			"extraction_accuracy",
			"Human review sample",
			metrics=metrics,
			base_rate=base_rate,
			notes=(
				f"{reviewed} human-reviewed signal(s) across {len(metrics)} signal "
				f"type(s); {len(skipped)} type(s) skipped with no human review; "
				f"{machine} machine confirmation(s) excluded from the precision"
			),
		)

	written = write_validation(artefact, root=_quality_root(out))

	# The per-type detail and the skipped set go beside the validation artefact
	# as a frame, because the validation model carries flat metrics only and the
	# sample sizes, the field errors and the machine count are what make a
	# precision arguable. A precision with no sample size is a number nobody can
	# weigh.
	from alea.io.pipeline import write_stage
	from alea.provenance.models import Basis, DerivedProvenance, Licence

	provenance = DerivedProvenance(
		source_id="scanning_extraction_accuracy",
		retrieved_at=utcnow(),
		licence=Licence.UNKNOWN,
		basis=Basis.MEASURED,
		uncertainty=0.0,
		uncertainty_basis="",
		notes=(
			"precision per signal type over human-reviewed signals only; machine "
			"auto-acceptances are counted separately and excluded from the "
			"measurement. Types with no human review are absent rather than zero"
		),
		inputs=[queue_input],
		parameters={
			"reviewed": reviewed,
			"machine_confirmed": machine,
			"types_measured": len(metrics),
			"types_skipped": len(skipped),
			"base_rate": base_rate if base_rate is not None else -1.0,
		},
	)
	rows = [
		{
			"label": key,
			"value": float(detail["precision"]),
			"unit": "precision",
			"sample_size": float(detail["sample_size"]),
			"confirmed": float(detail["confirmed"]),
			"rejected": float(detail["rejected"]),
			"edited": float(detail["edited"]),
			"machine_confirmed": float(detail["machine_confirmed"]),
		}
		for key, detail in per_type.items()
	]
	frame = pd.DataFrame(
		rows,
		columns=[
			"label",
			"value",
			"unit",
			"sample_size",
			"confirmed",
			"rejected",
			"edited",
			"machine_confirmed",
		],
	)
	write_stage(Path(out), frame, provenance, format="parquet")
	logger.info(
		"extraction_accuracy_artefact",
		out=str(out),
		validation=written,
		reviewed=reviewed,
		types_measured=len(metrics),
		types_skipped=len(skipped),
		machine_confirmed=machine,
	)
	return frame


def _quality_root(out: str | Path) -> Path:
	"""The quality storage root implied by an artefact output path.

	``write_validation`` appends ``validation/<target>.json`` to its root, so a
	caller that names the stage's own output path needs the part above it. The
	stage writes ``results/quality/scanning/extraction_accuracy.parquet``, which
	makes ``results/quality`` the root; taking the grandparent is derived from
	that path rather than from ``storage_root()``, which would be a second answer
	to where quality artefacts live.

	Resolved first, because the configured ``paths.results`` is relative to the
	repository root: ``Path("results").parent.parent`` is ``.``, which is not a
	quality root at all, and the assert below is what catches that rather than
	letting the artefact land where the coverage check does not look.
	"""
	from alea.config.paths import resolve

	root = resolve(out).parent.parent
	assert root.name == "quality", (
		f"{out} is not under a quality root; write_validation would place the "
		f"artefact somewhere the coverage check does not look"
	)
	return root


def retention_report(*, config: Config, dry_run: bool = True) -> object:
	"""Apply the raw-text retention policy from a config.

	Kept here rather than in ``ingest`` so a caller that has a ``Config`` does
	not have to know which field holds the retention window.
	"""
	from alea.scanning.ingest import purge_expired_raw

	return purge_expired_raw(
		retention_days=config.scanning.raw_text_retention_days, dry_run=dry_run
	)


__all__ = [
	"DEFAULT_LOOKBACK",
	"ScanningService",
	"decide_auto_accept",
	"policy_tracker_to_artefact",
	"retention_report",
]
