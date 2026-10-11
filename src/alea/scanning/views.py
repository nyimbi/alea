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


class ScanReport(BaseModel):
	"""The result of one full scan run.

	Carries the ingestion counts, the extraction counts, the queue depth, and
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
	pending_count: int = Field(ge=0)
	llm_calls: int = Field(ge=0)
	connector_health: list[dict[str, object]] = Field(default_factory=list)
	unhealthy: list[str] = Field(default_factory=list)
	"""Connectors whose last fetch was not ``ok`` or ``no_new``. A run that
	reports success while a scraper is broken is the failure this field exists
	to surface."""
	at: datetime = Field(default_factory=utcnow)

	@property
	def is_healthy(self) -> bool:
		return not self.unhealthy


__all__ = [
	"DedupGroup",
	"DedupReport",
	"IngestionReport",
	"PriorityBreakdown",
	"RetentionReport",
	"ScanReport",
]
