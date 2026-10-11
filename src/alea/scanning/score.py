# SPDX-License-Identifier: MIT
"""Priority scoring and the auto-acceptance decision (10-layer7 §5.3, §6.3).

Two separate things live here and they must not be confused:

**Priority** orders the review queue. It is a heuristic, it is allowed to be
wrong, and a wrong priority costs a reviewer five minutes.

**Auto-acceptance** decides whether a signal reaches a model without a human.
It is *not* allowed to be wrong, which is why the default is that nothing
auto-accepts and why a threshold alone is not enough: the plan requires a
**measured precision per signal type** before a type may auto-accept. A
threshold with no measurement is a guess about an extractor's error rate, and
the guess is made by the party that benefits from a low one.

The Mixtral "91% success rate" claim in the specification is ``[UNVERIFIED]``
and is measured at M3 against human review. It appears nowhere in this module
as a number, deliberately: the module takes a measured precision as an
argument and refuses to supply one.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from alea.io.artefacts import utcnow
from alea.logging import get_logger
from alea.registry import get_country
from alea.registry.countries import CompletenessTier
from alea.scanning.views import PriorityBreakdown
from alea.signals.models import Signal, SignalType

logger = get_logger(__name__)

#: How completely a country's data exists, as a fraction, for the priority
#: term. A CRITICAL country is one of the seven absent from the continental
#: datasets entirely; a signal about it is a signal about a country the model
#: knows least about, which is exactly where new information has the most
#: value. The mapping is a stated judgement, not a measurement, and it only
#: affects ordering — never auto-acceptance.
_COMPLETENESS_SCORE: dict[CompletenessTier, float] = {
	CompletenessTier.HIGH: 0.85,
	CompletenessTier.MEDIUM: 0.60,
	CompletenessTier.LOW: 0.35,
	CompletenessTier.CRITICAL: 0.15,
}

#: Source reliability, from spec4-data-collection §10's ``SOURCE_RELIABILITY``.
#: The values are the specification's and are unmeasured; they order the queue
#: and nothing else. A source not listed gets the neutral 0.5, because an
#: unlisted source scored low is a source nobody ever reviews.
SOURCE_RELIABILITY: dict[str, float] = {
	"worldbank_procurement": 0.95,
	"ifc_projects": 0.95,
	"institutional": 0.90,
	"nersa": 0.90,
	"afrec": 0.90,
	"nepad": 0.85,
	"rss_news": 0.65,
	"the_electricity_hub": 0.70,
	"esi_africa": 0.70,
	"energy_monitor": 0.75,
	"africa_energy_portal": 0.80,
	"x_recent_search": 0.30,
}
DEFAULT_SOURCE_RELIABILITY = 0.5

#: Signal-type impact, from spec4-data-collection §10. An investment changes a
#: capacity-expansion option; an outage fills in an outage history row. Both
#: matter, and not equally.
SIGNAL_TYPE_IMPACT: dict[str, float] = {
	SignalType.GENERATION_INVESTMENT.value: 0.90,
	SignalType.GENERATION_RETIREMENT.value: 0.90,
	SignalType.TRANSMISSION_INVESTMENT.value: 0.85,
	SignalType.POLICY_CHANGE.value: 0.85,
	SignalType.TENDER_RFP.value: 0.70,
	SignalType.FUEL_PRICE_CHANGE.value: 0.70,
	SignalType.DEMAND_SIGNAL.value: 0.60,
	SignalType.OUTAGE_EVENT.value: 0.55,
	SignalType.OUTAGE_CAUSE.value: 0.45,
	SignalType.CLIMATE_EVENT.value: 0.60,
}
DEFAULT_SIGNAL_TYPE_IMPACT = 0.5


class SignalTypePrecision(BaseModel):
	"""A measured precision for one signal type, with the sample it came from.

	``sample_size`` is required because precision without a sample is an
	anecdote: 100% of three signals is not a precision, and a threshold set on
	it would auto-accept the fourth.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	signal_type: SignalType
	precision: float = Field(ge=0.0, le=1.0)
	sample_size: int = Field(ge=1)
	measured_at: datetime = Field(default_factory=utcnow)
	source: str = ""
	"""Where the measurement came from, e.g. ``M3 review sample 2026-09``."""


class AutoAcceptDecision(BaseModel):
	"""Whether a signal may skip review, and the reason either way.

	The reason is returned in both directions. An auto-acceptance with no
	recorded justification is indistinguishable from a bug that stopped
	reviewing signals.
	"""

	model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

	auto_accepted: bool
	signal_type: SignalType
	reason: str
	threshold: float | None = None
	measured_precision: float | None = None


def compute_priority(
	signal: Signal,
	*,
	corroboration_count: int = 0,
	context: dict[str, float] | None = None,
) -> PriorityBreakdown:
	"""Priority in [0, 100], with the contribution of each factor.

	Factors and weights are the specification's (§10). ``corroboration_count``
	is the number of *other* sources that carried the same event, from the
	ingestion report's duplicate groups.
	"""
	assert signal.confidence is not None, "a signal always carries a confidence"
	assert corroboration_count >= 0
	extras = context or {}

	completeness = extras.get("data_completeness")
	if completeness is None:
		completeness = _completeness_for(signal.country_iso)

	reliability = extras.get(
		"source_reliability", SOURCE_RELIABILITY.get(signal.source_name, DEFAULT_SOURCE_RELIABILITY)
	)
	impact = extras.get(
		"signal_type_impact", SIGNAL_TYPE_IMPACT.get(signal.signal_type, DEFAULT_SIGNAL_TYPE_IMPACT)
	)

	components = {
		"confidence": signal.confidence * 30.0,
		"source_reliability": reliability * 20.0,
		"signal_type_impact": impact * 25.0,
		"data_gap": (1.0 - completeness) * 15.0,
		# A first report of an event outranks a corroborating one: the reviewer
		# has already seen the event if they have seen the other reports.
		"novelty": (1.0 / (1.0 + corroboration_count)) * 10.0,
	}
	breakdown = PriorityBreakdown.from_components(components)
	logger.debug(
		"priority_computed",
		signal_id=signal.signal_id[:12],
		total=breakdown.total,
		corroboration=corroboration_count,
	)
	return breakdown


def _completeness_for(country_iso: str | None) -> float:
	"""How complete a country's data is, as a fraction.

	A signal with no country cannot be attributed to a national model, so it
	gets the neutral 0.5 rather than the maximum: rewarding a missing field
	would push every country-less signal to the top of the queue.
	"""
	if not country_iso:
		return 0.5
	try:
		return _COMPLETENESS_SCORE[get_country(country_iso).completeness]
	except KeyError:
		return 0.5


def decide_auto_accept(
	signal: Signal,
	*,
	threshold: float | None,
	precision_by_type: dict[str, SignalTypePrecision] | None = None,
	min_sample_size: int = 30,
) -> AutoAcceptDecision:
	"""Whether a signal may skip review.

	Four conditions, all required:

	1. A threshold is configured. The default is ``None``, which means every
	   signal is reviewed.
	2. A precision has been measured for *this* signal type. A threshold
	   measured on outage events says nothing about investment announcements.
	3. The measurement has at least ``min_sample_size`` observations.
	4. The measured precision meets the threshold.

	Anything else returns ``auto_accepted=False`` with the reason. Refusing is
	the safe direction: a false refusal costs a review, and a false acceptance
	puts an unverified number into a model.
	"""
	assert threshold is None or 0.0 < threshold <= 1.0
	signal_type = SignalType(signal.signal_type)

	if threshold is None:
		return AutoAcceptDecision(
			auto_accepted=False,
			signal_type=signal_type,
			reason="auto_accept_threshold is not configured; every signal is reviewed",
		)

	measurement = (precision_by_type or {}).get(signal_type.value)
	if measurement is None:
		return AutoAcceptDecision(
			auto_accepted=False,
			signal_type=signal_type,
			reason=(
				f"no measured precision for {signal_type.value}; a threshold is only "
				f"applied to a signal type whose precision has been measured"
			),
			threshold=threshold,
		)

	if measurement.sample_size < min_sample_size:
		return AutoAcceptDecision(
			auto_accepted=False,
			signal_type=signal_type,
			reason=(
				f"precision sample for {signal_type.value} is {measurement.sample_size}, "
				f"below the required {min_sample_size}"
			),
			threshold=threshold,
			measured_precision=measurement.precision,
		)

	if measurement.precision < threshold:
		return AutoAcceptDecision(
			auto_accepted=False,
			signal_type=signal_type,
			reason=(
				f"measured precision {measurement.precision:.3f} for {signal_type.value} "
				f"is below the threshold {threshold:.3f}"
			),
			threshold=threshold,
			measured_precision=measurement.precision,
		)

	return AutoAcceptDecision(
		auto_accepted=True,
		signal_type=signal_type,
		reason=(
			f"measured precision {measurement.precision:.3f} on {measurement.sample_size} "
			f"observations meets the threshold {threshold:.3f}"
		),
		threshold=threshold,
		measured_precision=measurement.precision,
	)


def score_signals(
	signals: list[Signal],
	*,
	corroboration: dict[str, int] | None = None,
	threshold: float | None = None,
	precision_by_type: dict[str, SignalTypePrecision] | None = None,
) -> list[tuple[Signal, PriorityBreakdown, AutoAcceptDecision]]:
	"""Score a batch, in a deterministic order.

	Ordered by descending priority then signal id, so the queue's presentation
	order is reproducible and the "oldest pending signal" metric means
	something.
	"""
	scored = [
		(
			signal,
			compute_priority(signal, corroboration_count=(corroboration or {}).get(signal.signal_id, 0)),
			decide_auto_accept(signal, threshold=threshold, precision_by_type=precision_by_type),
		)
		for signal in signals
	]
	scored.sort(key=lambda item: (-item[1].total, item[0].signal_id))
	return scored


__all__ = [
	"DEFAULT_SIGNAL_TYPE_IMPACT",
	"DEFAULT_SOURCE_RELIABILITY",
	"SIGNAL_TYPE_IMPACT",
	"SOURCE_RELIABILITY",
	"AutoAcceptDecision",
	"SignalTypePrecision",
	"compute_priority",
	"decide_auto_accept",
	"score_signals",
]
