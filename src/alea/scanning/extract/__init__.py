# SPDX-License-Identifier: MIT
"""Extraction: deterministic patterns first, then a cached LLM (10-layer7 §5).

``Extractor`` is the stage facade. It runs the pattern extractors, asks the
model to classify, and assembles validated signals — in that order, because
the patterns must run first: they are what makes the numbers in the assembled
signal reproducible, and a model consulted first would have its numbers
silently preferred.
"""

from __future__ import annotations

from typing import Any

from alea.logging import get_logger
from alea.scanning.connectors.base import RawDocument
from alea.scanning.extract import deterministic as _deterministic
from alea.scanning.extract.deterministic import DeterministicExtraction
from alea.scanning.extract.llm import ExtractionConfig, LlmClient, LlmExtractor
from alea.scanning.extract.schema import ExtractionRecord, assemble_signals
from alea.signals.models import Signal

logger = get_logger(__name__)


class Extractor:
	"""Deterministic-first extraction with an optional LLM classification.

	``llm=None`` is a supported configuration, not a degraded one: with no model
	the extractor still produces pattern-only signals for documents whose text
	names a capacity or an investment, and the ``ExtractionRecord`` says the
	model was not consulted. A suite that needs determinism and no network runs
	in this mode.
	"""

	def __init__(
		self,
		*,
		config: ExtractionConfig | None = None,
		llm: LlmExtractor | None = None,
		client: LlmClient | None = None,
	) -> None:
		if llm is not None:
			self._llm = llm
		elif config is not None:
			self._llm = LlmExtractor(config, client=client)
		else:
			self._llm = None

	@property
	def llm(self) -> LlmExtractor | None:
		return self._llm

	@property
	def calls(self) -> int:
		"""Provider calls made. Two extractions of one document must add one."""
		return 0 if self._llm is None else self._llm.calls

	async def extract_document(
		self,
		document: RawDocument,
		*,
		corroborating_ids: list[str] | None = None,
	) -> tuple[list[Signal], ExtractionRecord]:
		"""Extract every signal one document supports."""
		assert document.document_id, "a document without an identity cannot be traced"
		patterns = _deterministic.extract(document.text)
		payload: dict[str, Any] = {}
		model: str | None = None
		if self._llm is not None and document.is_usable:
			payload, _response = await self._llm.extract_raw(
				document.text,
				title=document.title,
				source_name=document.source_name,
				url=document.source_url,
			)
			model = self._llm.config.model
		signals, record = assemble_signals(
			document,
			patterns,
			payload,
			model=model,
			corroborating_ids=corroborating_ids,
		)
		return signals, record

	async def extract_documents(
		self,
		documents: list[RawDocument],
		*,
		corroboration: dict[str, list[str]] | None = None,
	) -> tuple[list[Signal], list[ExtractionRecord]]:
		"""Extract a batch, returning signals and one record per document.

		Iteration is in ``document_id`` order so two runs over the same corpus
		produce the same signal order and therefore the same artefacts.
		"""
		signals: list[Signal] = []
		records: list[ExtractionRecord] = []
		for document in sorted(documents, key=lambda d: d.document_id):
			document_signals, record = await self.extract_document(
				document,
				corroborating_ids=(corroboration or {}).get(document.document_id),
			)
			signals.extend(document_signals)
			records.append(record)
		logger.info(
			"extraction_complete",
			documents=len(documents),
			signals=len(signals),
			llm_calls=self.calls,
		)
		return signals, records


__all__ = [
	"DeterministicExtraction",
	"ExtractionConfig",
	"ExtractionRecord",
	"Extractor",
	"LlmExtractor",
	"assemble_signals",
]
