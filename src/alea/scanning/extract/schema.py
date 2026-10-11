# SPDX-License-Identifier: MIT
"""Signal assembly and validation (10-layer7 §5.2).

This is where deterministic findings and the model's classification become a
``Signal``. The rule that governs everything here: **a field that fails
validation is dropped and the signal is flagged, not repaired by a second LLM
call.** A repair pass makes the extraction's error rate unmeasurable, because
the corrected value is indistinguishable from one the model got right.

Three specific guards, each against a named hazard:

* **Precedence.** A quantity the patterns found beats a quantity the model
  stated. The model classifies and summarises; the numbers a model acts on come
  from an inspectable rule. When a field *only* the model produced is kept, it
  is listed in ``ExtractionRecord.model_derived_fields`` so the difference is
  recorded rather than assumed away.
* **Evidence must be quoted from the document.** A model that cites a quote
  the document does not contain has fabricated its evidence, and a fabricated
  quote is worse than no quote because it reads as proof. Non-matching quotes
  are dropped and counted.
* **A coordinate is a pair.** ``Signal`` refuses half a coordinate itself; the
  assembler drops the pair rather than letting the constructor raise, so one bad
  field does not cost the whole signal.

**Note on ``outage_cause`` and severity.** ``SignalType.OUTAGE_CAUSE`` exists,
but ``Signal`` has no ``cause`` or ``severity`` field — the contract is fixed
and this layer must not extend it. The extracted cause and severity are
therefore carried in ``description`` and ``uncertainty_notes`` and in the
evidence quotes. A downstream consumer that wants a structured cause needs a
field added to ``Signal`` first, in the same commit that updates the story
detector (AD-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alea._uuid7 import uuid7str
from alea.logging import get_logger
from alea.registry import get_country
from alea.scanning.connectors.base import RawDocument
from alea.scanning.extract.deterministic import (
	DeterministicExtraction,
	guess_signal_type,
	looks_like_instruction,
)
from alea.scanning.extract.llm import PROMPT_VERSION
from alea.signals.models import OutageCause, OutageSeverity, Signal, SignalType, Technology

logger = get_logger(__name__)

#: Fields a model may produce that are *quantities a model acts on*. When one
#: of these is taken from the model rather than from a pattern, the record says
#: so. This is the list the "deterministic first" rule is enforced against.
_MODEL_DERIVED_QUANTITIES = ("capacity_mw", "investment_usd", "event_date")

_MAX_DESCRIPTION = 1200
_MAX_NOTE = 600
_MAX_QUOTE = 400
_MAX_QUOTES = 5

_VALID_TECHNOLOGY = {member.value for member in Technology}
_VALID_CAUSE = {member.value for member in OutageCause}
_VALID_SEVERITY = {member.value for member in OutageSeverity}
_VALID_SIGNAL_TYPE = {member.value for member in SignalType}


class ExtractionRecord(BaseModel):
	"""What produced a document's signals, and what was rejected producing them.

	Persisted alongside the signals so the extraction-accuracy loop (§6.3) can
	attribute a confirmed-versus-extracted difference to a model and prompt
	version, and so a dropped field is visible rather than merely absent.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	record_id: str = Field(default_factory=uuid7str)
	document_id: str
	source_name: str
	source_url: str
	model: str | None = None
	"""``None`` when the document was assembled from patterns alone."""
	prompt_version: str | None = None
	extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
	signal_ids: list[str] = Field(default_factory=list)
	dropped_fields: dict[str, str] = Field(default_factory=dict)
	"""Field name -> why it was dropped. A dropped capacity is a fact about the
	document; silently omitting it is a fact about nothing."""
	model_derived_fields: dict[str, str] = Field(default_factory=dict)
	"""Fields taken from the model because no pattern found them."""
	quotes_rejected: int = Field(default=0, ge=0)
	deterministic: dict[str, Any] = Field(default_factory=dict)
	notes: str = ""

	@property
	def had_rejections(self) -> bool:
		return bool(self.dropped_fields) or self.quotes_rejected > 0


def _iso2_or_none(value: Any, dropped: dict[str, str]) -> str | None:
	"""Validate a country code against the platform's own registry.

	The registry check is the load-bearing part. ``Signal``'s validator accepts
	any two letters, so ``ZZ`` passes there and then routes a signal into a
	national model that does not exist. A code the platform does not model is
	dropped here and named in the record.
	"""
	if value in (None, ""):
		return None
	if not isinstance(value, str) or len(value) != 2 or not value.isalpha():
		dropped["country_iso"] = f"not an alpha-2 code: {value!r}"
		return None
	code = value.upper()
	try:
		get_country(code)
	except KeyError:
		dropped["country_iso"] = f"{code} is not a registered AU member state"
		return None
	return code


def _float_or_none(
	value: Any, field_name: str, dropped: dict[str, str], *, minimum: float | None = None
) -> float | None:
	"""Coerce to a float, refusing non-numbers and out-of-range values."""
	if value in (None, ""):
		return None
	if isinstance(value, bool):
		dropped[field_name] = f"boolean is not a number: {value!r}"
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		dropped[field_name] = f"not a number: {value!r}"
		return None
	if minimum is not None and number < minimum:
		# A negative capacity is the signature of an injected or hallucinated
		# value, and `Signal` refuses it. Dropping here names the field.
		dropped[field_name] = f"below minimum {minimum}: {number}"
		return None
	return number


def _coordinates(
	latitude: Any, longitude: Any, dropped: dict[str, str]
) -> tuple[float | None, float | None]:
	"""A coordinate pair, or nothing.

	``Signal`` raises on a half-pair, and a raise costs the whole signal. Here
	the pair is dropped instead, so a model that produced a latitude and no
	longitude costs one field rather than one signal.
	"""
	lat = _float_or_none(latitude, "latitude", dropped)
	lon = _float_or_none(longitude, "longitude", dropped)
	if lat is None and lon is None:
		return None, None
	if lat is None or lon is None:
		dropped["latitude"] = "half a coordinate pair; both were dropped"
		dropped.pop("longitude", None)
		return None, None
	if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
		dropped["latitude"] = f"out of range: ({lat}, {lon})"
		return None, None
	return lat, lon


def _datetime_or_none(value: Any, dropped: dict[str, str], field_name: str) -> datetime | None:
	"""Parse an ISO date or datetime, tolerating a trailing ``Z``."""
	if value in (None, ""):
		return None
	if isinstance(value, datetime):
		return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
	if not isinstance(value, str):
		dropped[field_name] = f"not a date string: {value!r}"
		return None
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		dropped[field_name] = f"unparseable date: {value!r}"
		return None
	return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _clean_quotes(
	quotes: Any, document_text: str, dropped: dict[str, str]
) -> tuple[list[str], int]:
	"""Keep only quotes that appear verbatim in the document.

	Comparison is whitespace-insensitive because a model normalising a line
	break is not fabricating; comparison on *content* is exact because a model
	changing a number inside a quote is. Returns the quotes and how many were
	rejected.
	"""
	if not isinstance(quotes, list):
		return [], 0
	normalised_document = " ".join(document_text.split()).lower()
	kept: list[str] = []
	rejected = 0
	for quote in quotes[:_MAX_QUOTES * 2]:
		if not isinstance(quote, str) or not quote.strip():
			continue
		candidate = quote.strip()[:_MAX_QUOTE]
		if " ".join(candidate.split()).lower() in normalised_document:
			if candidate not in kept:
				kept.append(candidate)
		else:
			rejected += 1
	if rejected:
		dropped["evidence_quotes"] = f"{rejected} quote(s) not found in the document"
	return kept[:_MAX_QUOTES], rejected


def _signal_type_or_none(value: Any, dropped: dict[str, str]) -> str | None:
	"""Validate the classification against the ``SignalType`` taxonomy."""
	if not isinstance(value, str):
		dropped["signal_type"] = f"not a string: {value!r}"
		return None
	normalised = value.strip().lower()
	if normalised not in _VALID_SIGNAL_TYPE:
		dropped["signal_type"] = f"not a known signal type: {value!r}"
		return None
	return normalised


def _technology_or_none(value: Any, dropped: dict[str, str]) -> str | None:
	if value in (None, ""):
		return None
	if not isinstance(value, str):
		dropped["technology"] = f"not a string: {value!r}"
		return None
	normalised = value.strip().lower()
	if normalised not in _VALID_TECHNOLOGY:
		dropped["technology"] = f"not a known technology: {value!r}"
		return None
	return normalised


def _confidence(value: Any, dropped: dict[str, str]) -> float:
	"""The model's confidence, clamped into the unit interval.

	Clamping rather than dropping: a confidence of 1.2 is a formatting error
	and the extraction behind it may be fine, whereas dropping the field would
	leave a required field unset.
	"""
	number = _float_or_none(value, "confidence", dropped)
	if number is None:
		dropped.pop("confidence", None)
		return 0.5
	return min(max(number, 0.0), 1.0)


def assemble_signals(
	document: RawDocument,
	deterministic: DeterministicExtraction,
	payload: dict[str, Any],
	*,
	model: str | None = None,
	prompt_version: str | None = PROMPT_VERSION,
	corroborating_ids: list[str] | None = None,
) -> tuple[list[Signal], ExtractionRecord]:
	"""Turn one document's findings into validated ``Signal`` objects.

	``payload`` is the model's parsed response (``{"signals": [...]}``); it may
	be empty, which is the deterministic-only path. Every candidate is validated
	field by field, and the record carries what was dropped.
	"""
	assert document.document_id, "a signal must trace to a document"
	raw_signals = payload.get("signals") if isinstance(payload, dict) else None
	if not isinstance(raw_signals, list):
		raw_signals = []

	signals: list[Signal] = []
	dropped: dict[str, str] = {}
	model_derived: dict[str, str] = {}
	quotes_rejected = 0
	synthesised = False

	if not raw_signals and deterministic_has_content(deterministic):
		# The deterministic-only path: no model was configured (or it found
		# nothing), and the patterns did. A capacity extracted by an
		# inspectable rule is exactly the value a model may act on, so it is
		# not discarded for want of a classification. The signal is marked
		# model-derived only in the sense that its *type* is a keyword guess,
		# and the record says so.
		candidate = _candidate_from_patterns(document, deterministic)
		if candidate is not None:
			raw_signals = [candidate]
			synthesised = True

	for candidate in raw_signals:
		if not isinstance(candidate, dict):
			continue
		signal, candidate_dropped, candidate_model, rejected = _assemble_one(
			document, deterministic, candidate
		)
		dropped.update(candidate_dropped)
		model_derived.update(candidate_model)
		quotes_rejected += rejected
		if signal is not None:
			signals.append(signal)

	notes = "; ".join(deterministic.notes)
	if payload.get("_error"):
		notes = "; ".join(filter(None, [notes, f"model response: {payload['_error']}"]))
	if synthesised:
		notes = "; ".join(filter(None, [notes, "signal assembled from patterns only (no model)"]))
	if not signals and not raw_signals:
		notes = "; ".join(filter(None, [notes, "no signal extracted"]))

	record = ExtractionRecord(
		document_id=document.document_id,
		source_name=document.source_name,
		source_url=document.source_url,
		model=model,
		prompt_version=prompt_version if model else None,
		signal_ids=[s.signal_id for s in signals],
		dropped_fields=dict(sorted(dropped.items())),
		model_derived_fields=dict(sorted(model_derived.items())),
		quotes_rejected=quotes_rejected,
		deterministic={
			"capacities_mw": [q.value for q in deterministic.capacities_mw],
			"investments_usd": [q.value for q in deterministic.investments_usd],
			"other_currency_amounts": deterministic.other_currency_amounts,
			"dates": [d.isoformat() for d in deterministic.dates],
			"countries": deterministic.countries,
			"technologies": deterministic.technologies,
			"causes": deterministic.causes,
			"severities": deterministic.severities,
			"ambiguous_dates": deterministic.ambiguous_dates,
			"instruction_sentences": deterministic.instruction_sentences,
		},
		notes=notes,
	)
	logger.info(
		"signals_assembled",
		document_id=document.document_id[:12],
		signals=len(signals),
		dropped=len(dropped),
		quotes_rejected=quotes_rejected,
	)
	return signals, record


def deterministic_has_content(deterministic: DeterministicExtraction) -> bool:
	"""Whether the patterns found anything a signal could be built from.

	A country mention alone is not enough: a document that names Kenya and
	states no quantity is a document the patterns cannot turn into a claim, and
	synthesising a signal from it would fill the queue with geographic
	coincidences.
	"""
	return bool(
		deterministic.capacities_mw
		or deterministic.investments_usd
		or deterministic.dates
		or deterministic.causes
	)


def _candidate_from_patterns(
	document: RawDocument, deterministic: DeterministicExtraction
) -> dict[str, Any] | None:
	"""A candidate built from the patterns alone, for the no-model path.

	The type is a keyword guess and is the only part of the candidate the model
	would have supplied; every quantity comes from a pattern. If no keyword
	matches and there is no capacity or investment to imply one, no candidate is
	returned — a signal whose type was invented is a signal nobody can attribute
	to a rule.
	"""
	has_capacity = bool(deterministic.capacities_mw)
	has_investment = bool(deterministic.investments_usd)
	signal_type = guess_signal_type(
		f"{document.title}\n{document.text}",
		has_capacity=has_capacity,
		has_investment=has_investment,
	)
	if signal_type is None:
		return None
	quote = ""
	for key in ("capacity_mw", "investments_usd", "country_iso"):
		sentences = deterministic.evidence.get(key)
		if sentences:
			quote = sentences[0]
			break
	return {
		"signal_type": signal_type,
		# A pattern-only signal is genuinely less certain than a classified
		# one: the quantities are trustworthy, the type is a guess.
		"confidence": 0.4,
		"description": document.title[: _MAX_DESCRIPTION] or document.text[:200],
		"evidence_quotes": [quote] if quote else [],
		"uncertainty_notes": "assembled from pattern matches without a model; type is a keyword guess",
		"_quote": quote,
	}


def _assemble_one(
	document: RawDocument,
	deterministic: DeterministicExtraction,
	candidate: dict[str, Any],
) -> tuple[Signal | None, dict[str, str], dict[str, str], int]:
	"""Validate one candidate into a ``Signal``.

	Returns the signal (or ``None`` if it could not be built), the dropped
	fields, the model-derived fields, and the rejected-quote count.
	"""
	dropped: dict[str, str] = {}
	model_derived: dict[str, str] = {}

	signal_type = _signal_type_or_none(candidate.get("signal_type"), dropped)
	if signal_type is None:
		# Without a valid type there is no signal; the record says why.
		return None, dropped, model_derived, 0

	latitude, longitude = _coordinates(
		candidate.get("latitude"), candidate.get("longitude"), dropped
	)

	# -- quantities: deterministic first ---------------------------------
	capacity = deterministic.capacities_mw[0].value if deterministic.capacities_mw else None
	if capacity is None:
		capacity = _float_or_none(candidate.get("capacity_mw"), "capacity_mw", dropped, minimum=0.0)
		if capacity is not None:
			model_derived["capacity_mw"] = "no capacity pattern matched; value is the model's"

	investment = deterministic.investments_usd[0].value if deterministic.investments_usd else None
	if investment is None:
		investment = _float_or_none(
			candidate.get("investment_usd"), "investment_usd", dropped, minimum=0.0
		)
		if investment is not None:
			model_derived["investment_usd"] = "no USD amount pattern matched; value is the model's"

	event_date = deterministic.dates[0] if deterministic.dates else None
	if event_date is None:
		event_date = _datetime_or_none(candidate.get("event_date"), dropped, "event_date")
		if event_date is not None:
			model_derived["event_date"] = "no date pattern matched; value is the model's"

	country = _iso2_or_none(candidate.get("country_iso"), dropped)
	if country is None and deterministic.countries:
		# A country the model omitted is filled from the pattern match, and the
		# fill is recorded because it is the model's classification that is
		# being supplemented, not its numbers.
		country = deterministic.countries[0]
		model_derived["country_iso"] = "model named no valid country; taken from pattern match"

	technology = _technology_or_none(candidate.get("technology"), dropped)
	if technology is None and deterministic.technologies:
		technology = deterministic.technologies[0]

	# Evidence ordering: the pattern-derived sentences come first, because they
	# are the sentences the extracted numbers came from. A model's own quotes
	# follow, and a quote taken from a sentence addressed to the extraction
	# machinery goes last — it is still shown to the reviewer, since hiding it
	# would hide the attack, but it does not lead the list.
	pattern_quotes: list[str] = []
	for _key, sentences in deterministic.evidence.items():
		for sentence in sentences:
			if sentence and sentence not in pattern_quotes:
				pattern_quotes.append(sentence[:_MAX_QUOTE])
	model_quotes, rejected = _clean_quotes(candidate.get("evidence_quotes"), document.text, dropped)
	ordered = pattern_quotes + [q for q in model_quotes if q not in pattern_quotes]
	quotes = [q for q in ordered if not looks_like_instruction(q)]
	quotes += [q for q in ordered if looks_like_instruction(q) and q not in quotes]
	quotes = quotes[:_MAX_QUOTES]
	if not quotes and candidate.get("_quote"):
		# The deterministic-only path supplies the sentence its number came
		# from, and that sentence is by construction a substring of the
		# document, so it does not go through the quote check above.
		quotes = [str(candidate["_quote"])[: _MAX_QUOTE]]

	description = str(candidate.get("description") or "")[:_MAX_DESCRIPTION]
	notes_parts = [str(candidate.get("uncertainty_notes") or "")[:_MAX_NOTE]]
	notes_parts.extend(deterministic.notes)
	if candidate.get("cause"):
		cause = str(candidate["cause"]).strip().lower()
		notes_parts.append(
			f"cause={cause}" if cause in _VALID_CAUSE else f"cause (unrecognised)={cause}"
		)
	if candidate.get("severity"):
		severity = str(candidate["severity"]).strip().lower()
		notes_parts.append(
			f"severity={severity}" if severity in _VALID_SEVERITY else f"severity (unrecognised)={severity}"
		)
	if model_derived:
		notes_parts.append(
			"model-derived (no pattern): " + ", ".join(sorted(model_derived))
		)
	if dropped:
		notes_parts.append("dropped: " + ", ".join(sorted(dropped)))
	uncertainty_notes = "; ".join(part for part in notes_parts if part)[:_MAX_NOTE * 2]

	payload: dict[str, Any] = {
		"signal_type": signal_type,
		"confidence": _confidence(candidate.get("confidence"), dropped),
		"source_document_id": document.document_id,
		"source_url": document.source_url,
		"source_name": document.source_name,
		"country_iso": country,
		"region": (str(candidate["region"])[:200] if candidate.get("region") else None),
		"latitude": latitude,
		"longitude": longitude,
		"event_date": event_date,
		"capacity_mw": capacity,
		"technology": technology,
		"fuel_type": (str(candidate["fuel_type"])[:100] if candidate.get("fuel_type") else None),
		"investment_usd": investment,
		"description": description,
		"evidence_quotes": quotes,
		"uncertainty_notes": uncertainty_notes,
		# Never false here. Auto-acceptance is decided in `score` against a
		# measured precision, and the extractor is not the place that decides it.
		"requires_review": True,
	}

	try:
		signal = Signal.model_validate(payload)
	except ValidationError as exc:
		# A field that survives every guard above and still fails the contract
		# is a gap in the guards. Drop the offending fields, retry once, and
		# record the drop — a silent failure here would lose the signal and the
		# reason for it.
		offending = {
			str(error["loc"][0])
			for error in exc.errors()
			if error.get("loc") and str(error["loc"][0]) in payload
		}
		for field_name in offending:
			dropped[field_name] = f"rejected by Signal: {exc.errors()[0]['msg']}"
			payload[field_name] = None if field_name != "evidence_quotes" else []
		logger.warning(
			"signal_validation_retry",
			document_id=document.document_id[:12],
			fields=sorted(offending),
		)
		try:
			signal = Signal.model_validate(payload)
		except ValidationError as second:
			logger.error(
				"signal_dropped",
				document_id=document.document_id[:12],
				error=str(second.errors()[:2]),
			)
			return None, dropped, model_derived, rejected

	return signal, dropped, model_derived, rejected


__all__ = [
	"ExtractionRecord",
	"assemble_signals",
	"deterministic_has_content",
]
