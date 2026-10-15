# SPDX-License-Identifier: MIT
"""Layer 7 — intelligence scanning.

Watches the African energy landscape continuously and produces ``Signal``
objects. It is the only layer that runs on a schedule shorter than a day, and
the only one whose input is the open internet — which is why two properties are
enforced here rather than stated:

* **The signal contract is the only boundary** (AD-3). Nothing but ``Signal``
  leaves this package.
* **Nothing reaches a model unreviewed.** ``requires_review`` defaults ``True``
  and :func:`alea.scanning.integrate.integrate` refuses a signal that still
  carries it. Auto-acceptance is off by default and, when switched on, requires
  a precision measured from the review record for the signal type in question.

Stages, in the order a run uses them: ``connectors`` → ``ingest`` →
``extract`` → ``score`` → ``review`` → ``integrate``. Each is separately
importable and separately testable; :class:`alea.scanning.service.ScanningService`
composes the first five.
"""

from alea.scanning.connectors import (
	Connector,
	FetchBlocked,
	FetchError,
	HttpFetcher,
	RateLimiter,
	RawDocument,
	ScrapeHealth,
	SourceCategory,
	make_document,
)
from alea.scanning.extract import (
	DeterministicExtraction,
	ExtractionConfig,
	ExtractionRecord,
	Extractor,
	LlmExtractor,
	assemble_signals,
)
from alea.scanning.ingest import (
	deduplicate_documents,
	detail_key,
	ingest,
	purge_expired_raw,
	shingles,
)
from alea.scanning.integrate import (
	Conflict,
	StagingError,
	UnreviewedSignalError,
	UpdateKind,
	UpdateProposal,
	integrate,
	load_staged_proposals,
	stage_proposal,
	stage_signals,
)
from alea.scanning.review import (
	ExtractionAccuracy,
	QueueError,
	ReviewAction,
	ReviewQueue,
	SignalStatus,
	SignalVersion,
)
from alea.scanning.score import (
	AutoAcceptDecision,
	SignalTypePrecision,
	compute_priority,
	decide_auto_accept,
	score_signals,
)
from alea.scanning.service import ScanningService, extraction_accuracy_artefact
from alea.scanning.views import (
	DedupGroup,
	DedupReport,
	IngestionReport,
	PriorityBreakdown,
	RetentionReport,
	ReviewBacklog,
	ScanReport,
)

__all__ = [
	"AutoAcceptDecision",
	"Conflict",
	"Connector",
	"DedupGroup",
	"DedupReport",
	"DeterministicExtraction",
	"ExtractionAccuracy",
	"ExtractionConfig",
	"ExtractionRecord",
	"Extractor",
	"extraction_accuracy_artefact",
	"FetchBlocked",
	"FetchError",
	"HttpFetcher",
	"IngestionReport",
	"LlmExtractor",
	"PriorityBreakdown",
	"QueueError",
	"RateLimiter",
	"RawDocument",
	"RetentionReport",
	"ReviewAction",
	"ReviewBacklog",
	"ReviewQueue",
	"ScanReport",
	"ScanningService",
	"ScrapeHealth",
	"SignalStatus",
	"SignalTypePrecision",
	"SignalVersion",
	"SourceCategory",
	"StagingError",
	"UnreviewedSignalError",
	"UpdateKind",
	"UpdateProposal",
	"assemble_signals",
	"compute_priority",
	"decide_auto_accept",
	"deduplicate_documents",
	"detail_key",
	"ingest",
	"integrate",
	"load_staged_proposals",
	"make_document",
	"purge_expired_raw",
	"score_signals",
	"shingles",
	"stage_proposal",
	"stage_signals",
]
