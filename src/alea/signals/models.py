# SPDX-License-Identifier: MIT
"""The signal contract.

A *signal* is one machine-readable claim extracted from one source document:
"a 100 MW solar plant reached financial close in Kenya on 2026-03-01". Signals
are the only thing the scanning layer hands to the analytical layers, so this
module is the interface between them and is deliberately narrow.

``spec4-data-collection.md`` defines ``Signal`` as the shared contract and
``spec4-ext.md``'s story detector consumes the same ``signal_type`` values, so
the taxonomy below is load-bearing for both. Do not add a member without
updating the story detector's newsworthiness rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
	AfterValidator,
	BaseModel,
	ConfigDict,
	Field,
	field_validator,
	model_validator,
)

from alea._uuid7 import uuid7str


class SignalType(StrEnum):
	"""What a signal claims. Values are the wire format; keep them snake_case."""

	OUTAGE_EVENT = "outage_event"
	OUTAGE_CAUSE = "outage_cause"
	GENERATION_INVESTMENT = "generation_investment"
	GENERATION_RETIREMENT = "generation_retirement"
	TRANSMISSION_INVESTMENT = "transmission_investment"
	POLICY_CHANGE = "policy_change"
	FUEL_PRICE_CHANGE = "fuel_price_change"
	TENDER_RFP = "tender_rfp"
	DEMAND_SIGNAL = "demand_signal"
	CLIMATE_EVENT = "climate_event"


class Technology(StrEnum):
	"""Generation technology a signal refers to, when it names one."""

	SOLAR = "solar"
	WIND = "wind"
	HYDRO = "hydro"
	GAS = "gas"
	COAL = "coal"
	GEOTHERMAL = "geothermal"
	BIOMASS = "biomass"
	NUCLEAR = "nuclear"
	BATTERY = "battery"


class OutageCause(StrEnum):
	"""Cause attributed to an outage, when a source attributes one."""

	WEATHER = "weather"
	VANDALISM = "vandalism"
	EQUIPMENT_FAILURE = "equipment_failure"
	LOAD_SHEDDING = "load_shedding"
	UNKNOWN = "unknown"


class OutageSeverity(StrEnum):
	MINOR = "minor"
	MODERATE = "moderate"
	WIDESPREAD = "widespread"


def _iso3166_alpha2(value: str | None) -> str | None:
	"""Reject anything that is not an ISO 3166-1 alpha-2 country code.

	A wrong country code is worse than a missing one: it silently routes a signal
	into the wrong national model. ``None`` stays ``None``.
	"""
	if value is None:
		return None
	if len(value) != 2 or not value.isalpha():
		raise ValueError(f"country_iso must be ISO 3166-1 alpha-2, got {value!r}")
	return value.upper()


CountryIso = Annotated[str | None, AfterValidator(_iso3166_alpha2)]


class Signal(BaseModel):
	"""One extracted claim, with its provenance.

	Every field that a downstream model might act on is optional, because a
	partially-extracted signal is still useful — but ``confidence`` and the
	provenance fields are required, so a signal can never be anonymous or
	unqualified. ``requires_review`` defaults to ``True``: nothing reaches a
	model without a human confirming it.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		use_enum_values=True,
	)

	signal_id: str = Field(default_factory=uuid7str)
	signal_type: SignalType
	confidence: float = Field(ge=0.0, le=1.0)
	source_document_id: str
	source_url: str
	source_name: str
	extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
	"""When the signal was extracted, always timezone-aware.

	Naive here would be worse than untidy: this value is written to SQLite as
	``isoformat()`` and compared as a string, and it is what a reviewer reads to
	decide whether a claim is current. A naive timestamp is silently local time,
	so the same extraction on two hosts sorts differently and an event dated
	"now" is off by the deployment's offset. ``datetime.now(UTC)`` rather than
	``alea.io.artefacts.utcnow`` so this contract module does not import the
	artefact store, which pulls in pandas and xarray."""

	country_iso: CountryIso = None
	region: str | None = None
	latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
	longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
	event_date: datetime | None = None

	capacity_mw: float | None = Field(default=None, ge=0.0)
	technology: Technology | None = None
	fuel_type: str | None = None
	investment_usd: float | None = Field(default=None, ge=0.0)

	description: str = ""
	evidence_quotes: list[str] = Field(default_factory=list)
	uncertainty_notes: str = ""
	requires_review: bool = True

	@model_validator(mode="after")
	def _coordinates_come_in_pairs(self) -> Signal:
		# A half-coordinate is the signature of a geocoder that failed halfway:
		# latitude without longitude cannot be mapped, and longitude without
		# latitude is the same defect from the other side. A field_validator on
		# either one cannot see the other, because fields validate in declaration
		# order and neither is populated when the first runs.
		if (self.latitude is None) != (self.longitude is None):
			raise ValueError(
				"latitude and longitude must be given together, got "
				f"latitude={self.latitude}, longitude={self.longitude}"
			)
		return self

	@field_validator("extracted_at")
	@classmethod
	def _extraction_time_is_timezone_aware(cls, v: datetime) -> datetime:
		# A caller-supplied naive timestamp is the same defect as the naive
		# default was, and it arrives from the API's own read path
		# (`datetime.fromisoformat` on a stored value). Refused rather than
		# assumed to be UTC: an assumption here is a silent offset everywhere
		# downstream.
		if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
			raise ValueError(
				f"extracted_at must be timezone-aware, got naive {v.isoformat()}"
			)
		return v

	@field_validator("confidence")
	@classmethod
	def _confidence_is_a_probability(cls, v: float) -> float:
		if not 0.0 <= v <= 1.0:
			raise ValueError(f"confidence must be in [0, 1], got {v}")
		return v

	@property
	def is_geolocated(self) -> bool:
		"""Whether the signal can be placed on a map."""
		return self.latitude is not None and self.longitude is not None

	@property
	def has_quantitative_payload(self) -> bool:
		"""Whether the signal carries a number a model can act on."""
		return any(
			x is not None
			for x in (self.capacity_mw, self.investment_usd, self.fuel_type)
		)


__all__ = [
	"Signal",
	"SignalType",
	"Technology",
	"OutageCause",
	"OutageSeverity",
	"CountryIso",
]
