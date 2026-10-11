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

from datetime import datetime, timedelta

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

		enqueued = 0
		auto_accepted = 0
		model = self.extractor.llm.config.model if self.extractor.llm is not None else None
		prompt_version = (
			self.extractor.llm.config.prompt_version if self.extractor.llm is not None else None
		)
		for signal, breakdown, decision in scored:
			await self.queue.enqueue(
				signal,
				priority=breakdown,
				corroborating_ids=corroboration_by_signal.get(signal.signal_id, []),
				model=model,
				prompt_version=prompt_version,
			)
			enqueued += 1
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
			pending_count=await self.queue.pending_count(),
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


def _dedup_groups(
	documents: list[RawDocument],
	kept: list[RawDocument],
	config: ScanningConfig,
) -> list[object]:
	"""Recompute the duplicate grouping for corroboration.

	Kept for callers that have only a document list and a config — the service
	path threads the report through ``ingest`` instead, because recomputing it
	would be a second kernel call whose result could differ if the seed ever
	diverged from the config's.
	"""
	from alea.scanning.ingest import deduplicate_documents

	if not documents:
		return []
	_, report = deduplicate_documents(
		documents,
		num_perm=config.dedup_num_perm,
		threshold=config.dedup_threshold,
		seed=config.dedup_seed,
	)
	return list(report.groups)


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
	"retention_report",
]
