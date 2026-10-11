# SPDX-License-Identifier: MIT
"""Integration: proposals, the refusal, and conflict detection (10-layer7 §7).

Three rules, and each is an enforcement rather than a statement:

**A scanning layer must not silently integrate a signal into a model.** Every
signal that has not been reviewed is refused, and ``requires_review`` defaults
``True`` — so the refusal is the enforcement point for the human-in-the-loop
principle, and a signal that reaches here unreviewed is a bug in the scanning
layer rather than an invitation to proceed. ``test_integrate_refuses_unreviewed``
canaries it.

**The updater applies signals, it does not re-solve.** A proposal is written to
``data/processed/`` staging with the signal's provenance attached, and the next
pipeline run picks it up. A signal that triggers a re-solve directly means the
model changes underneath a running report.

**A signal that contradicts an ingested dataset is not applied.** A news report
of a 500 MW plant where the fleet holds 200 MW is recorded as a conflict for
analyst resolution. Auto-applying a news figure over a curated dataset is how a
scanning layer degrades a model, and the degradation is invisible because the
news figure is the one that was *recently* checked.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from alea import __version__
from alea._uuid7 import uuid7str
from alea.io.artefacts import utcnow, write_artefact
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance, Licence
from alea.signals.models import Signal, SignalType

logger = get_logger(__name__)

DEFAULT_STAGING_ROOT = "data/processed/scanning/proposals"

#: The relative difference between a signal's figure and the dataset's at which
#: the two are treated as contradicting each other rather than as two
#: measurements of the same thing. 25% is a stated judgement: below it, a
#: difference is plausibly a rounding, a phase, or a unit convention; above it,
#: one of the two is wrong and a human has to say which.
DEFAULT_CONFLICT_TOLERANCE = 0.25


class UpdateKind(StrEnum):
	"""What a proposal asks the pipeline to do."""

	FLEET_ADD = "fleet_add"
	FLEET_RETIRE = "fleet_retire"
	TRANSMISSION_ADD = "transmission_add"
	POLICY_PARAMETER = "policy_parameter"
	FUEL_PRICE = "fuel_price"
	DEMAND_PROJECTION = "demand_projection"
	OUTAGE_HISTORY = "outage_history"
	TENDER_PIPELINE = "tender_pipeline"
	CLIMATE_RISK = "climate_risk"


#: Signal type -> the update it proposes. The table is the specification's
#: §7.1, extended with the three signal types the taxonomy has and that table
#: omits (``tender_rfp``, ``demand_signal``, ``climate_event`` are listed
#: there; ``outage_cause`` is not, and it maps to the same handler as
#: ``outage_event`` because a cause with no event has nothing to attach to).
_UPDATE_FOR_TYPE: dict[str, UpdateKind] = {
	SignalType.GENERATION_INVESTMENT.value: UpdateKind.FLEET_ADD,
	SignalType.GENERATION_RETIREMENT.value: UpdateKind.FLEET_RETIRE,
	SignalType.TRANSMISSION_INVESTMENT.value: UpdateKind.TRANSMISSION_ADD,
	SignalType.POLICY_CHANGE.value: UpdateKind.POLICY_PARAMETER,
	SignalType.FUEL_PRICE_CHANGE.value: UpdateKind.FUEL_PRICE,
	SignalType.DEMAND_SIGNAL.value: UpdateKind.DEMAND_PROJECTION,
	SignalType.OUTAGE_EVENT.value: UpdateKind.OUTAGE_HISTORY,
	SignalType.OUTAGE_CAUSE.value: UpdateKind.OUTAGE_HISTORY,
	SignalType.TENDER_RFP.value: UpdateKind.TENDER_PIPELINE,
	SignalType.CLIMATE_EVENT.value: UpdateKind.CLIMATE_RISK,
}

#: Fields a proposal needs before it can be staged, per update kind.
#: A fleet addition with no capacity is a proposal the pipeline cannot apply,
#: and finding that out at staging is finding it out before a human has
#: approved it — which is the cheapest possible moment.
_REQUIRED_FIELDS: dict[UpdateKind, tuple[str, ...]] = {
	UpdateKind.FLEET_ADD: ("capacity_mw",),
	UpdateKind.FLEET_RETIRE: (),
	UpdateKind.TRANSMISSION_ADD: (),
	UpdateKind.POLICY_PARAMETER: ("description",),
	UpdateKind.FUEL_PRICE: ("description",),
	UpdateKind.DEMAND_PROJECTION: ("capacity_mw",),
	UpdateKind.OUTAGE_HISTORY: (),
	UpdateKind.TENDER_PIPELINE: (),
	UpdateKind.CLIMATE_RISK: (),
}


class UnreviewedSignalError(ValueError):
	"""A signal reached integration without having been reviewed.

	A ``ValueError`` subclass so the plan's stated contract (§7.2) holds for a
	caller that catches ``ValueError``, while a caller that wants to distinguish
	this specific refusal can.
	"""


class StagingError(RuntimeError):
	"""A proposal could not be staged."""


class Conflict(BaseModel):
	"""A signal that contradicts an ingested dataset.

	Recorded, never applied. The two values are both kept because the resolution
	is a human decision: the dataset may be stale or the signal may be wrong,
	and the module has no basis for preferring either.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True)

	field: str
	signal_value: float
	existing_value: float
	relative_difference: float = Field(ge=0.0)
	tolerance: float = Field(gt=0.0)
	note: str = ""

	@classmethod
	def between(
		cls, field: str, signal_value: float, existing_value: float, *, tolerance: float
	) -> Conflict:
		"""Build a conflict, computing the relative difference against the dataset.

		The denominator is the existing (curated) value, not the signal's: the
		question is "how much would this signal move the model", and the model
		holds the existing value.
		"""
		assert tolerance > 0.0
		denominator = abs(existing_value) if existing_value else 1.0
		difference = abs(signal_value - existing_value) / denominator
		return cls(
			field=field,
			signal_value=signal_value,
			existing_value=existing_value,
			relative_difference=difference,
			tolerance=tolerance,
			note=(
				f"signal states {signal_value} where the dataset holds {existing_value} "
				f"({difference:.1%} apart, tolerance {tolerance:.0%})"
			),
		)


class UpdateProposal(BaseModel):
	"""A model update a confirmed signal asks for.

	Carries the signal's provenance and its uncertainty, because a proposal that
	reaches the pipeline without them is a number with no history (AD-6).
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	proposal_id: str = Field(default_factory=uuid7str)
	signal_id: str
	signal_type: SignalType
	kind: UpdateKind
	status: Literal["staged", "conflict", "refused"]
	payload: dict[str, Any] = Field(default_factory=dict)
	confidence: float = Field(ge=0.0, le=1.0)
	uncertainty: float = Field(ge=0.0)
	uncertainty_basis: str
	country_iso: str | None = None
	source_document_id: str
	source_url: str
	source_name: str
	signal_extracted_at: datetime
	corroborating_ids: list[str] = Field(default_factory=list)
	conflicts: list[Conflict] = Field(default_factory=list)
	reason: str = ""
	at: datetime = Field(default_factory=utcnow)
	staged_path: str | None = None

	@property
	def is_applicable(self) -> bool:
		"""Whether the pipeline should apply this on its next run."""
		return self.status == "staged"


def _payload_for(signal: Signal) -> dict[str, Any]:
	"""The fields a pipeline stage needs, taken from the signal.

	Only fields the signal actually carries are included: a payload with
	``capacity_mw: null`` invites the consumer to treat the null as a value.
	"""
	candidates: dict[str, Any] = {
		"country_iso": signal.country_iso,
		"region": signal.region,
		"latitude": signal.latitude,
		"longitude": signal.longitude,
		"event_date": signal.event_date.isoformat() if signal.event_date else None,
		"capacity_mw": signal.capacity_mw,
		"technology": signal.technology,
		"fuel_type": signal.fuel_type,
		"investment_usd": signal.investment_usd,
		"description": signal.description,
	}
	return {key: value for key, value in candidates.items() if value not in (None, "")}


def integrate(
	signal: Signal,
	*,
	known_values: dict[str, float] | None = None,
	tolerance: float = DEFAULT_CONFLICT_TOLERANCE,
	corroborating_ids: list[str] | None = None,
) -> UpdateProposal:
	"""Turn a confirmed signal into a model-update proposal.

	Refuses any signal that has not been through review. ``requires_review``
	defaults True and this function is the enforcement point: a signal that
	reaches here unreviewed is a bug in the scanning layer, and integrating it
	silently would make the human-in-the-loop principle decorative.

	``known_values`` is the curated dataset's figures for the fields this signal
	carries — ``{"capacity_mw": 200.0}``, say. A signal that differs from one by
	more than ``tolerance`` returns a proposal with ``status="conflict"`` and is
	not staged.
	"""
	assert signal.confidence is not None
	if signal.requires_review:
		raise UnreviewedSignalError(
			f"signal {signal.signal_id} has not been reviewed; "
			f"the scanning layer must not reach the model directly"
		)

	signal_type = SignalType(signal.signal_type)
	kind = _UPDATE_FOR_TYPE.get(signal_type.value)
	if kind is None:  # pragma: no cover - every SignalType member is mapped
		return UpdateProposal(
			signal_id=signal.signal_id,
			signal_type=signal_type,
			kind=UpdateKind.POLICY_PARAMETER,
			status="refused",
			confidence=signal.confidence,
			uncertainty=1.0 - signal.confidence,
			uncertainty_basis="1 - extraction confidence",
			country_iso=signal.country_iso,
			source_document_id=signal.source_document_id,
			source_url=signal.source_url,
			source_name=signal.source_name,
			signal_extracted_at=signal.extracted_at,
			reason=f"no update handler is defined for signal type {signal_type.value}",
		)

	payload = _payload_for(signal)
	missing = [field for field in _REQUIRED_FIELDS[kind] if field not in payload]
	if missing:
		return UpdateProposal(
			signal_id=signal.signal_id,
			signal_type=signal_type,
			kind=kind,
			status="refused",
			payload=payload,
			confidence=signal.confidence,
			uncertainty=1.0 - signal.confidence,
			uncertainty_basis="1 - extraction confidence",
			country_iso=signal.country_iso,
			source_document_id=signal.source_document_id,
			source_url=signal.source_url,
			source_name=signal.source_name,
			signal_extracted_at=signal.extracted_at,
			reason=f"{kind.value} requires {', '.join(missing)}; the signal does not carry it",
		)

	conflicts: list[Conflict] = []
	for field, existing in sorted((known_values or {}).items()):
		candidate = payload.get(field)
		if not isinstance(candidate, int | float) or isinstance(candidate, bool):
			continue
		conflict = Conflict.between(field, float(candidate), float(existing), tolerance=tolerance)
		if conflict.relative_difference > tolerance:
			conflicts.append(conflict)

	status: Literal["staged", "conflict", "refused"] = "conflict" if conflicts else "staged"
	reason = (
		"; ".join(conflict.note for conflict in conflicts)
		if conflicts
		else "confirmed signal; staged for the next pipeline run"
	)
	proposal = UpdateProposal(
		signal_id=signal.signal_id,
		signal_type=signal_type,
		kind=kind,
		status=status,
		payload=payload,
		confidence=signal.confidence,
		uncertainty=1.0 - signal.confidence,
		uncertainty_basis="1 - extraction confidence",
		country_iso=signal.country_iso,
		source_document_id=signal.source_document_id,
		source_url=signal.source_url,
		source_name=signal.source_name,
		signal_extracted_at=signal.extracted_at,
		corroborating_ids=sorted(corroborating_ids or []),
		conflicts=conflicts,
		reason=reason,
	)
	logger.info(
		"proposal_built",
		signal_id=signal.signal_id[:12],
		kind=kind.value,
		status=status,
		conflicts=len(conflicts),
	)
	return proposal


def stage_proposal(
	proposal: UpdateProposal,
	*,
	root: str | Path = DEFAULT_STAGING_ROOT,
) -> Path:
	"""Write a proposal to the staging area with its provenance.

	Refuses a proposal that is not ``staged``: writing a conflict or a refusal
	into the staging directory would put it in front of a pipeline run that
	applies everything it finds there.

	The provenance records the signal's source document as the input checksum,
	so a proposal on disk traces to the exact document that produced it.
	"""
	if proposal.status != "staged":
		raise StagingError(
			f"proposal {proposal.proposal_id} has status {proposal.status!r}; only a "
			f"staged proposal is written, or the pipeline would apply a conflict"
		)
	target = Path(root) / f"{proposal.kind.value}_{proposal.proposal_id}.json"
	provenance = DerivedProvenance(
		source_id=f"scanning_{proposal.source_name}",
		source_url=proposal.source_url,
		retrieved_at=proposal.at,
		licence=Licence.UNKNOWN,
		uncertainty=proposal.uncertainty,
		uncertainty_basis=proposal.uncertainty_basis,
		# A signal is a claim, not a measurement of the fleet. Marking it
		# MEASURED would let a news figure look like a metered one all the way
		# to a report (AD-6).
		basis=Basis.FORECAST,
		notes=f"scanning signal {proposal.signal_id}; {proposal.reason}",
		inputs=[proposal.source_document_id],
		code_version=__version__,
		parameters={
			"kind": proposal.kind.value,
			"signal_type": str(proposal.signal_type),
			"confidence": proposal.confidence,
			"corroborating_ids": proposal.corroborating_ids,
		},
	)
	write_artefact(target, proposal.model_dump(mode="json"), provenance, format="json")
	logger.info(
		"proposal_staged",
		proposal_id=proposal.proposal_id[:12],
		kind=proposal.kind.value,
		path=str(target),
	)
	return target


def stage_signals(
	signals: list[Signal],
	*,
	known_values: dict[str, dict[str, float]] | None = None,
	root: str | Path = DEFAULT_STAGING_ROOT,
	tolerance: float = DEFAULT_CONFLICT_TOLERANCE,
) -> list[UpdateProposal]:
	"""Integrate and stage a batch of confirmed signals.

	``known_values`` maps ``signal_id -> {field: value}`` from the curated
	dataset, so one call can resolve each signal against the plant, line or
	parameter it concerns.

	An unreviewed signal raises rather than being skipped: a batch containing
	one is a batch produced by a broken caller, and skipping it would hide the
	bug behind a smaller proposal list.
	"""
	proposals: list[UpdateProposal] = []
	for signal in sorted(signals, key=lambda s: s.signal_id):
		proposal = integrate(
			signal,
			known_values=(known_values or {}).get(signal.signal_id),
			tolerance=tolerance,
		)
		if proposal.is_applicable:
			proposal = proposal.model_copy(update={"staged_path": str(stage_proposal(proposal, root=root))})
		proposals.append(proposal)
	logger.info(
		"batch_integrated",
		signals=len(signals),
		staged=sum(1 for p in proposals if p.is_applicable),
		conflicts=sum(1 for p in proposals if p.status == "conflict"),
		refused=sum(1 for p in proposals if p.status == "refused"),
	)
	return proposals


def load_staged_proposals(root: str | Path = DEFAULT_STAGING_ROOT) -> list[UpdateProposal]:
	"""Read every staged proposal, oldest first.

	This is what the pipeline's scanning stage calls. Ordering by proposal id is
	ordering by creation time, because the id is UUID7.
	"""
	from alea.config.paths import resolve

	directory = resolve(root)
	if not directory.exists():
		return []
	out: list[UpdateProposal] = []
	for path in sorted(directory.glob("*.json")):
		if path.name.endswith(".provenance.json"):
			continue
		try:
			out.append(UpdateProposal.model_validate(json.loads(path.read_text(encoding="utf-8"))))
		except (json.JSONDecodeError, ValueError) as exc:
			logger.error("proposal_unreadable", path=str(path), error=str(exc))
	return out


__all__ = [
	"DEFAULT_CONFLICT_TOLERANCE",
	"DEFAULT_STAGING_ROOT",
	"Conflict",
	"StagingError",
	"UnreviewedSignalError",
	"UpdateKind",
	"UpdateProposal",
	"integrate",
	"load_staged_proposals",
	"stage_proposal",
	"stage_signals",
]
