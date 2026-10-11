# SPDX-License-Identifier: MIT
"""The review record (10-layer7 §6.2).

The record is append-only, and that is enforced in three places rather than
asserted once:

1. ``ReviewAction`` is frozen, so an in-memory action cannot be edited.
2. The SQLite tables carry ``BEFORE UPDATE`` and ``BEFORE DELETE`` triggers
   that abort, so the property holds against a client that never loads this
   module.
3. An edit produces a **new signal version**, so the original extraction
   survives as a row. This is what makes "the model was updated because an
   analyst corrected the capacity from 100 MW to 1000 MW" auditable, and it is
   what allows the extraction layer's accuracy to be measured: the difference
   between extracted and confirmed *is* the error, and it is only visible if
   both are kept.

The specification's queue used ``json.dumps(signal.__dict__)``, which bypasses
pydantic on the way out. Here the stored payload is ``model_dump(mode="json")``
of a validated ``Signal``, and it is re-validated on read — a signal whose
fields drifted from its provenance would otherwise be a signal whose audit
trail is fiction.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from alea._uuid7 import uuid7str
from alea.io.artefacts import utcnow
from alea.signals.models import Signal


class ReviewActionName(StrEnum):
	"""What an analyst did."""

	CONFIRM = "confirm"
	REJECT = "reject"
	EDIT = "edit"
	MERGE = "merge"


class SignalStatus(StrEnum):
	"""The state a signal version carries.

	Status lives on the *version*, not on the signal: a signal is not
	"confirmed", a particular version of it is. That is what keeps the table
	append-only without losing the ability to answer "what is this signal's
	state" — the answer is the latest version's status.
	"""

	PENDING = "pending"
	CONFIRMED = "confirmed"
	REJECTED = "rejected"
	MERGED = "merged"
	SUPERSEDED = "superseded"
	"""An edit replaced this version without confirming or rejecting it."""


class ReviewAction(BaseModel):
	"""One analyst decision, frozen.

	``resulting_signal`` is the validated signal the decision produced. For a
	confirm it is the signal with ``requires_review=False``; for an edit it is
	the corrected signal; for a merge it is the surviving signal. Storing the
	whole signal rather than a diff means the version chain is readable without
	replaying every prior action, and a chain that must be replayed to be read
	is a chain that will be read wrongly.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True)

	action_id: str = Field(default_factory=uuid7str)
	signal_id: str
	analyst: str
	action: Literal["confirm", "reject", "edit", "merge"]
	edits: dict[str, Any] = Field(default_factory=dict)
	reason: str = ""
	at: datetime = Field(default_factory=utcnow)
	resulting_signal: Signal | None = None
	merged_signal_ids: list[str] = Field(default_factory=list)
	model: str | None = None
	"""The model that produced the extraction being reviewed.

	Recorded because "the extraction accuracy of model-v1" is a question the
	M3 measurement has to answer, and it cannot be answered from the signal
	alone — two models produce signals that look identical."""
	prompt_version: str | None = None


class SignalVersion(BaseModel):
	"""One row of the append-only signal table."""

	model_config = ConfigDict(extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True)

	signal_id: str
	version: int = Field(ge=1)
	status: SignalStatus
	signal: Signal
	priority: float = Field(default=0.0, ge=0.0)
	priority_components: dict[str, float] = Field(default_factory=dict)
	corroborating_ids: list[str] = Field(default_factory=list)
	parent_version: int | None = None
	document_id: str = ""
	model: str | None = None
	prompt_version: str | None = None
	created_at: datetime = Field(default_factory=utcnow)

	@property
	def is_pending(self) -> bool:
		return self.status is SignalStatus.PENDING


class AccuracyRow(BaseModel):
	"""One cell of the accuracy report.

	Declared before :class:`ExtractionAccuracy`, which holds a list of these:
	with ``from __future__ import annotations`` pydantic resolves the forward
	reference against the module namespace at class-build time, and a name
	defined further down the file is not there yet.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	dimension: Literal["signal_type", "source_name"]
	key: str
	extracted: int = Field(default=0, ge=0)
	confirmed: int = Field(default=0, ge=0)
	rejected: int = Field(default=0, ge=0)
	pending: int = Field(default=0, ge=0)
	edited: int = Field(default=0, ge=0)
	"""How many confirmations arrived with a correction attached.

	An edit is a confirmation the extractor got *wrong in a detail*, which is
	the difference between "the extractor found the wrong event" and "the
	extractor found the right event with the wrong capacity". Collapsing the two
	into one rejection rate hides which failure the layer has."""
	field_errors: dict[str, int] = Field(default_factory=dict)
	"""Field name -> how many confirmations corrected it."""

	@property
	def sample_size(self) -> int:
		"""Reviewed signals. Pending ones are not evidence either way."""
		return self.confirmed + self.rejected

	@property
	def precision(self) -> float:
		"""Confirmed over reviewed. Zero when nothing has been reviewed.

		Zero rather than 0.5: a caller that reads this without checking
		``sample_size`` gets a value that fails every threshold, which is the
		safe direction."""
		return self.confirmed / self.sample_size if self.sample_size else 0.0


class ExtractionAccuracy(BaseModel):
	"""Confirmed-versus-extracted differences, per signal type and per source.

	This is §6.3's feedback loop and it is the only honest basis for an
	auto-acceptance threshold. ``precision`` is confirmed over
	(confirmed + rejected) among *reviewed* signals; a type with no reviewed
	signals has no precision and is reported with ``sample_size=0`` rather than
	with a default, because a default precision is a fabricated measurement.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	rows: list[AccuracyRow] = Field(default_factory=list)
	at: datetime = Field(default_factory=utcnow)

	def by_signal_type(self) -> dict[str, AccuracyRow]:
		return {row.key: row for row in self.rows if row.dimension == "signal_type"}

	def by_source(self) -> dict[str, AccuracyRow]:
		return {row.key: row for row in self.rows if row.dimension == "source_name"}


__all__ = [
	"AccuracyRow",
	"ExtractionAccuracy",
	"ReviewAction",
	"ReviewActionName",
	"SignalStatus",
	"SignalVersion",
]
