# SPDX-License-Identifier: MIT
"""Models shared across the scanning stages.

Only the shapes that cross a stage boundary live here. Extraction's own output
is ``Signal`` (the AD-3 contract) and review's own records are in
``review/models.py``; putting either of those here would blur the boundary the
package exists to keep sharp.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from alea._uuid7 import uuid7str
from alea.io.artefacts import utcnow


class DedupGroup(BaseModel):
	"""One near-duplicate group and the document kept from it.

	``representative_id`` is the kept document; every other member is a
	corroborating source. The kernel returns the *first* member in input order
	as its representative, which is a determinism guarantee and not a quality
	one — the kept document is chosen by :func:`alea.scanning.ingest.detail_key`
	and is frequently not the kernel's first.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	group_id: str
	representative_id: str
	member_ids: list[str] = Field(min_length=1)
	corroborating_ids: list[str] = Field(default_factory=list)

	@property
	def size(self) -> int:
		return len(self.member_ids)

	@property
	def corroboration_count(self) -> int:
		"""How many *other* sources carried the same event.

		Feeds the priority score (§5) and is evidence a reviewer needs: a claim
		carried by four outlets is a different claim from one carried by one.
		"""
		return len(self.corroborating_ids)


class DedupReport(BaseModel):
	"""The result of two-level deduplication."""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	report_id: str = Field(default_factory=uuid7str)
	input_count: int = Field(ge=0)
	exact_duplicates: int = Field(ge=0)
	near_duplicates: int = Field(ge=0)
	groups: list[DedupGroup] = Field(default_factory=list)
	kept_ids: list[str] = Field(default_factory=list)
	seed: int
	threshold: float
	at: datetime = Field(default_factory=utcnow)

	@property
	def kept_count(self) -> int:
		return len(self.kept_ids)


class IngestionReport(BaseModel):
	"""What one ingestion run did."""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	run_id: str = Field(default_factory=uuid7str)
	input_count: int = Field(ge=0)
	exact_duplicates: int = Field(ge=0)
	near_duplicates: int = Field(ge=0)
	kept_count: int = Field(ge=0)
	source_counts: dict[str, int] = Field(default_factory=dict)
	connector_health: list[dict[str, object]] = Field(default_factory=list)
	at: datetime = Field(default_factory=utcnow)


class RetentionReport(BaseModel):
	"""What one raw-text purge removed."""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	root: str
	retention_days: int = Field(ge=1)
	cutoff: datetime
	removed_payloads: int = Field(ge=0)
	removed_bytes: int = Field(ge=0)
	kept_payloads: int = Field(ge=0)
	at: datetime = Field(default_factory=utcnow)


class PriorityBreakdown(BaseModel):
	"""A signal's priority, with the contribution of each factor.

	A total with no breakdown is a number nobody can argue with and nobody can
	audit. The components are stored with the signal's queue row so a reviewer
	asking "why is this at the top" gets the arithmetic.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	total: float = Field(ge=0.0)
	components: dict[str, float] = Field(default_factory=dict)

	@classmethod
	def from_components(cls, components: dict[str, float]) -> PriorityBreakdown:
		"""Build a breakdown whose total is the clamped sum of its parts."""
		return cls(total=min(sum(components.values()), 100.0), components=dict(components))


class ReviewBacklog(BaseModel):
	"""The review queue's depth, and the age of the oldest entry in it.

	Both numbers, because neither answers the question alone. The method that
	reads the age says why in its own docstring: "a queue depth without an age
	is a metric that cannot distinguish 'busy day' from 'nobody has reviewed
	anything for a week'". Forty pending is healthy on a Monday and a stalled
	pipeline in the third week, and the depth is the same integer either way.

	``oldest_age_hours`` is derived here rather than at each door so that two
	readers cannot compute it against different clocks. It is ``None`` with no
	pending entries, which is not the same as zero: an empty queue has no age,
	and reporting ``0.0`` would render as "oldest entry is brand new".
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	pending: int = Field(ge=0)
	oldest_pending_at: datetime | None = None
	oldest_age_hours: float | None = Field(default=None, ge=0.0)

	def breaches(self, limit: int) -> bool:
		"""Whether the depth breaks a declared ceiling.

		``>=`` and not ``>``: the KPI's target is "*less than* 100 pending at
		any time" (``spec4-data-collection.md`` §16), so a depth of exactly the
		limit is already outside it. The limit is an argument rather than a
		field because the queue is policy-free and the ceiling is the
		configuration's -- a store that carried its own threshold would answer
		a question nobody asked it.
		"""
		assert limit >= 1, "a ceiling below one pending is not a ceiling"
		return self.pending >= limit


class ScanReport(BaseModel):
	"""The result of one full scan run.

	Carries the ingestion counts, the extraction counts, the queue backlog, and
	every connector's health, because the health dashboard (spec4 §14) has to
	answer "did we find nothing, or did the scanner break" from one artefact
	and not by correlating three logs.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	run_id: str = Field(default_factory=uuid7str)
	since: datetime
	documents_fetched: int = Field(ge=0)
	documents_kept: int = Field(ge=0)
	signals_extracted: int = Field(ge=0)
	signals_enqueued: int = Field(ge=0)
	signals_auto_accepted: int = Field(ge=0)
	backlog: ReviewBacklog
	"""The review queue at the end of the run: depth and oldest entry.

	This replaces a bare ``pending_count``, which was written on every run and
	read by nothing -- and which could not have been read usefully, because a
	depth alone is the number the class above exists to make interpretable.
	"""
	review_queue_limit: int = Field(ge=1)
	"""The depth the KPI allows, carried beside the depth that was measured.

	A report that prints a number without the ceiling it is judged against
	makes the reader look the ceiling up somewhere else, and the two drift the
	moment either moves. ``spec4-data-collection.md`` §16 is where the value
	comes from.
	"""
	llm_calls: int = Field(ge=0)
	connector_health: list[dict[str, object]] = Field(default_factory=list)
	unhealthy: list[str] = Field(default_factory=list)
	"""Connectors whose last fetch was not ``ok`` or ``no_new``. A run that
	reports success while a scraper is broken is the failure this field exists
	to surface."""
	at: datetime = Field(default_factory=utcnow)

	@property
	def is_healthy(self) -> bool:
		"""Whether the run found a problem worth surfacing.

		A backlog over the KPI's ceiling is included. A scan that fetched and
		enqueued correctly while the queue is 300 deep is not a healthy
		pipeline -- it is a pipeline whose review bottleneck has become the
		constraint, which is the risk ``spec4-data-collection.md`` names in its
		own register ("the human review queue becomes the bottleneck rather
		than the safety net"). ``unhealthy`` alone would report it as healthy.
		"""
		return not self.unhealthy and not self.backlog.breaches(self.review_queue_limit)


__all__ = [
	"DedupGroup",
	"DedupReport",
	"IngestionReport",
	"PriorityBreakdown",
	"RetentionReport",
	"ReviewBacklog",
	"ScanReport",
]
