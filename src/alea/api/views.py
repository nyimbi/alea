# SPDX-License-Identifier: MIT
"""Request and response models.

Two rules run through every model here, and both are load-bearing.

**The API does not serve bare numbers** (11-layer8 §3.3). Every quantity is a
:class:`ValueOut` carrying its unit, its basis, and its uncertainty. An API that
returns ``{"capacity_mw": 2100}`` invites a dashboard that renders ``2100 MW``;
an API that returns the basis invites a dashboard that renders ``2100 MW ᵖ``. A
proxy estimate for Burundi and a metered value for Kenya must not be
indistinguishable by the time a reader sees them, and the only place that
distinction can be preserved is in the payload.

**Every model forbids extras.** A client that sends ``{"countrys": ["KE"]}`` is
told, rather than silently served the default country set.

The character limits in :data:`USSD_MAX_CHARS` and :data:`SMS_MAX_CHARS` are
constants, not conventions, because the gate that enforces them
(``test_ussd_never_truncates``) has to read the same number the formatter does.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alea.provenance.models import Basis, Licence
from alea.signals.models import CountryIso, Signal, SignalType

# The one place the adapter limits live. A USSD screen is 182 characters and an
# SMS is 160; a formatter that reads its limit from here cannot drift from the
# model that validates against it.
USSD_MAX_CHARS = 182
SMS_MAX_CHARS = 160

# A page larger than this is a client that will time out rather than one that
# wants the data. The cap is enforced in the pagination dependency.
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100

ValueBasis = Basis
"""How a number came to exist. Aliased from provenance so there is one enum."""


class ApiModel(BaseModel):
	"""Base for every request and response model."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)


class Page[ItemT: BaseModel](ApiModel):
	"""A bounded, ordered slice of a collection.

	``total`` is the count before the slice, so a client can decide whether to
	ask for the next page without fetching it. Offset pagination over an
	append-only table is stable because rows are never reordered or deleted.
	"""

	items: list[ItemT]
	total: int = Field(ge=0)
	limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
	offset: int = Field(ge=0)

	@property
	def has_more(self) -> bool:
		"""Whether a further page exists."""
		return self.offset + len(self.items) < self.total


# --------------------------------------------------------------------------
# The value contract
# --------------------------------------------------------------------------


class ValueOut(ApiModel):
	"""A number with its basis. The API does not serve bare numbers.

	The reporting layer's rule (09-layer6 §2) applies here too: a consumer that
	receives a number without its basis will publish it without its basis.
	"""

	value: float
	unit: str
	basis: ValueBasis
	uncertainty: float = Field(ge=0.0)
	source_id: str = ""

	@model_validator(mode="after")
	def _uncertainty_is_justified(self) -> ValueOut:
		# Non-zero uncertainty with no source is an uninterpretable number that
		# will be quoted in a report. A measured value may carry zero, but a
		# modelled or proxy one may not: those are never exact.
		if (
			self.basis in (ValueBasis.MODELLED, ValueBasis.PROXY, ValueBasis.FORECAST)
			and self.uncertainty <= 0.0
		):
			raise ValueError(
				f"basis={self.basis.value!r} requires uncertainty > 0; only a "
				f"measured value is exact"
			)
		return self

	@classmethod
	def measured(cls, value: float, unit: str, *, source_id: str = "") -> ValueOut:
		"""An exact, metered value."""
		return cls(value=value, unit=unit, basis=ValueBasis.MEASURED, uncertainty=0.0, source_id=source_id)

	@classmethod
	def modelled(
		cls, value: float, unit: str, uncertainty: float, *, source_id: str = ""
	) -> ValueOut:
		"""A value from a model, with the model's uncertainty."""
		return cls(
			value=value,
			unit=unit,
			basis=ValueBasis.MODELLED,
			uncertainty=uncertainty,
			source_id=source_id,
		)

	@classmethod
	def proxy(
		cls, value: float, unit: str, uncertainty: float, *, source_id: str = ""
	) -> ValueOut:
		"""A substitute for a datum that does not exist. Never exact."""
		return cls(
			value=value, unit=unit, basis=ValueBasis.PROXY, uncertainty=uncertainty, source_id=source_id
		)


class ProvenanceOut(ApiModel):
	"""Where a datum came from. Mirrors ``provenance.models.Provenance`` on the wire."""

	source_id: str
	source_url: str = ""
	retrieved_at: datetime
	checksum: str = ""
	licence: Licence = Licence.UNKNOWN
	basis: ValueBasis = ValueBasis.MEASURED
	uncertainty: float = Field(default=0.0, ge=0.0)
	uncertainty_basis: str = ""
	notes: str = ""


class ErrorOut(ApiModel):
	"""The body of every error response.

	``code`` is a stable machine-readable token; ``detail`` is for a human. A
	client branches on ``code``, never on the prose.
	"""

	code: str
	detail: str
	request_id: str = ""


# --------------------------------------------------------------------------
# Scenarios and results
# --------------------------------------------------------------------------


class ScenarioSummaryOut(ApiModel):
	"""One scenario in a listing."""

	scenario_id: str
	name: str
	countries: list[str]
	planning_horizons: list[int]
	clusters: list[int]
	created_at: datetime
	description: str = ""


class ScenarioOut(ScenarioSummaryOut):
	"""A scenario with its provenance and the network it was solved against."""

	network_checksum: str = ""
	code_version: str = ""
	provenance: ProvenanceOut | None = None


class CapacityRowOut(ApiModel):
	"""Installed capacity for one carrier at one horizon."""

	carrier: str
	capacity_mw: ValueOut
	share: ValueOut


class ScenarioResultOut(ApiModel):
	"""A solved scenario's result at one planning horizon.

	Values are read from the solved network artefact, so each carries the
	network's checksum in ``source_id``.
	"""

	scenario_id: str
	horizon: int
	objective: ValueOut
	total_capacity_mw: ValueOut
	capacity_mix: list[CapacityRowOut]
	network_checksum: str = ""
	solved_at: datetime | None = None


# --------------------------------------------------------------------------
# Market
# --------------------------------------------------------------------------


class PriceRowOut(ApiModel):
	"""A wholesale price for one interval."""

	at: datetime
	country_iso: CountryIso
	price: ValueOut


class CaptureRateRowOut(ApiModel):
	"""A technology's capture rate against VRE penetration.

	The capture-rate curve is the Layer 3 deliverable: it is what a developer
	prices a project against.
	"""

	technology: str
	vre_penetration: ValueOut
	capture_rate: ValueOut
	capture_price: ValueOut


class PpaBenchmarkRowOut(ApiModel):
	"""A power-purchase-agreement benchmark for one technology and country."""

	technology: str
	country_iso: CountryIso
	ppa_price: ValueOut
	tenor_years: int = Field(gt=0)
	benchmark_source: str


# --------------------------------------------------------------------------
# Outages
# --------------------------------------------------------------------------


class OutageForecastRowOut(ApiModel):
	"""The probability that one grid zone loses supply in the next horizon.

	``probability`` is a probability, not a binary (09-layer6 §3.1): a forecast
	that says "yes" and is 60% right is worse than one that says 0.6.
	"""

	country_iso: CountryIso
	grid_zone: str
	probability: ValueOut
	horizon_hours: int = Field(gt=0, le=168)
	issued_at: datetime
	model_version: str = ""


class OutageHistoryRowOut(ApiModel):
	"""A recorded outage event."""

	event_id: str
	country_iso: CountryIso
	grid_zone: str
	started_at: datetime
	duration_minutes: ValueOut
	customers_affected: ValueOut
	cause: str = "unknown"


class OutageValidationRowOut(ApiModel):
	"""Forecast-versus-observed accuracy for one grid zone.

	This is the row that keeps an ``[UNVERIFIED]`` accuracy figure from being
	published as established (AD-10, 00-architecture §9).
	"""

	country_iso: CountryIso
	grid_zone: str
	period_start: datetime
	period_end: datetime
	auc: ValueOut
	precision: ValueOut
	recall: ValueOut
	sample_size: int = Field(ge=0)


# --------------------------------------------------------------------------
# Maintenance
# --------------------------------------------------------------------------


class MaintenancePredictionRowOut(ApiModel):
	"""A predicted failure probability for one asset."""

	asset_id: str
	asset_type: str
	country_iso: CountryIso
	failure_probability: ValueOut
	window_days: int = Field(gt=0)
	recommended_action: str = ""
	model_version: str = ""


# --------------------------------------------------------------------------
# Losses
# --------------------------------------------------------------------------


class LossComponentOut(ApiModel):
	"""One component of a loss decomposition."""

	component: str
	loss: ValueOut
	share: ValueOut


class LossDecompositionOut(ApiModel):
	"""Technical and non-technical losses split into their components."""

	country_iso: CountryIso
	period_start: datetime
	period_end: datetime
	total_loss: ValueOut
	components: list[LossComponentOut]


class TlensRowOut(ApiModel):
	"""Transmission and distribution loss statistics for a region-year."""

	country_iso: CountryIso
	year: int = Field(ge=1900, le=2200)
	transmission_loss_pct: ValueOut
	distribution_loss_pct: ValueOut
	collection_loss_pct: ValueOut
	basis_note: str = ""


class MitigationOptionOut(ApiModel):
	"""One intervention and its modelled effect on losses."""

	option: str
	loss_reduction: ValueOut
	capex: ValueOut
	payback_years: ValueOut


# --------------------------------------------------------------------------
# Resilience
# --------------------------------------------------------------------------


class ResilienceMetricOut(ApiModel):
	"""One resilience metric for a country."""

	metric: str
	country_iso: CountryIso
	value: ValueOut
	period: str


class ContingencyRowOut(ApiModel):
	"""The consequence of losing one network element."""

	element_id: str
	element_type: str
	load_shed_mw: ValueOut
	overloaded_elements: int = Field(ge=0)
	severity: str


# --------------------------------------------------------------------------
# Topology
# --------------------------------------------------------------------------


class TopologyLineOut(ApiModel):
	"""One transmission line as an endpoint pair.

	Endpoints rather than a geometry, because this is the table the network
	builder reads and the two must be the same artefact: a GIS that drew its own
	line between two buses would be drawing a network nobody solves. The
	GeoJSON the stage writes alongside carries the full path.
	"""

	line_id: str
	from_lon: float = Field(ge=-180.0, le=180.0)
	from_lat: float = Field(ge=-90.0, le=90.0)
	to_lon: float = Field(ge=-180.0, le=180.0)
	to_lat: float = Field(ge=-90.0, le=90.0)
	voltage_kv: ValueOut
	length_km: ValueOut
	capacity_mva: ValueOut


class TopologyOut(ApiModel):
	"""A transmission network, as its lines and the extent they cover.

	``bounds`` is the artefact's own bounding box, not one computed by the
	client: it is what the cutout stage takes its ERA5 extent from
	(``02-data-pipeline``), so a GIS and the weather pipeline must read the same
	rectangle or the profiles do not cover the lines they are attached to.
	"""

	checksum: str
	line_count: int = Field(ge=0)
	bounds: list[float] = Field(min_length=4, max_length=4)
	lines: list[TopologyLineOut]


# --------------------------------------------------------------------------
# What-if
# --------------------------------------------------------------------------


class ScenarioParametersIn(ApiModel):
	"""The levers a what-if scenario may pull.

	Every field is optional: a scenario is a delta against the base network, and
	an unset field means "leave it alone" rather than "zero".

	The field set is exactly ``alea.whatif.params.ScenarioParameters``'s, because
	these names are mapped straight onto the engine and a name the engine does not
	have is a lever the caller can pull that does nothing. The previous set here
	was invented alongside the API: it had no ``coal_eaf``, ``gas_price_multiplier``,
	``hydrogen_export_twh_per_year``, ``ssp_pathway`` or ``drought_multiplier``,
	and it had ``solar_capex_multiplier``, ``wind_capex_multiplier``,
	``transmission_expansion_multiplier`` and ``fuel_price_multiplier``, none of
	which the engine can apply. A request naming one of those validated, solved,
	and returned a result identical to the base scenario with no indication why.

	Names match the engine's rather than being translated, so a reader of either
	file sees the same lever. ``demand_growth`` is a fraction, not a percentage:
	the engine's own field is a fraction and a percent/fraction mismatch is a
	100x error that reads as a plausible number.
	"""

	demand_growth: float | None = Field(default=None, ge=-0.05, le=0.15)
	coal_eaf: float | None = Field(default=None, ge=0.0, le=2.0)
	carbon_price_usd_per_tco2: float | None = Field(default=None, ge=0.0, le=1000.0)
	gas_price_multiplier: float | None = Field(default=None, gt=0.0, le=10.0)
	renewable_multiplier: float | None = Field(default=None, gt=0.0, le=10.0)
	hydrogen_export_twh_per_year: float | None = Field(default=None, ge=0.0)
	battery_cost_multiplier: float | None = Field(default=None, gt=0.0, le=5.0)
	ssp_pathway: str | None = None
	drought_multiplier: float | None = Field(default=None, gt=0.0, le=3.0)

	@model_validator(mode="after")
	def _a_scenario_changes_something(self) -> ScenarioParametersIn:
		if all(value is None for value in self.model_dump().values()):
			raise ValueError("a what-if scenario with no parameters is not a scenario")
		return self

	@classmethod
	def one(cls, name: str, value: float) -> ScenarioParametersIn:
		"""One lever set, named. The frontier sweep's constructor.

		Deliberately not ``cls(**{name: value})``: unpacking a ``dict[str, float]``
		makes the type checker consider *every* field a candidate for a float,
		``ssp_pathway`` included, and a construct that can assign a float to a
		pathway string is one that eventually does. ``model_validate`` takes the
		mapping and the field's own validator rejects a bad value at the boundary.
		"""
		if name not in cls.model_fields:
			raise KeyError(
				f"unknown scenario parameter {name!r}; known: "
				f"{', '.join(sorted(cls.model_fields))}"
			)
		return cls.model_validate({name: value})

	def to_engine(self) -> Any:
		"""The engine's parameter value, with unset levers left at the default.

		The mapping is by name, so a field added here without a matching engine
		field is caught by the engine's own ``extra='forbid'`` rather than being
		ignored -- which is the failure this method replaces.
		"""
		from alea.whatif.params import ScenarioParameters

		set_values = {
			name: value
			for name, value in self.model_dump(exclude_none=True).items()
		}
		return ScenarioParameters.model_validate(set_values)


class WhatIfSolveRequest(ApiModel):
	"""A request to solve one what-if scenario. Answered with a job, never inline."""

	base_scenario_id: str
	parameters: ScenarioParametersIn
	name: str = ""


class WhatIfCompareRequest(ApiModel):
	"""A request to compare two or more scenarios at one horizon."""

	scenario_ids: list[str] = Field(min_length=2, max_length=10)
	horizon: int = Field(ge=2000, le=2200)


class WhatIfFrontierRequest(ApiModel):
	"""A request to sweep one parameter across a range.

	``points`` is capped because a frontier of a thousand solves is a job nobody
	will wait for and a cost nobody approved.
	"""

	base_scenario_id: str
	parameter: Literal[
		"carbon_price_usd_per_tco2",
		"demand_growth",
		"renewable_multiplier",
		"gas_price_multiplier",
		"coal_eaf",
		"battery_cost_multiplier",
		"drought_multiplier",
		"hydrogen_export_twh_per_year",
	]
	"""Numeric levers only. ``ssp_pathway`` is a category, and a frontier axis
	interpolated between ``SSP2-4.5`` and ``SSP5-8.5`` is not a pathway -- the
	sweep would either crash on the first point or, worse, coerce a midpoint
	into a string that names no scenario."""

	start: float
	stop: float
	points: int = Field(default=10, ge=2, le=100)


class JobKind(StrEnum):
	"""What a job runs. The worker dispatches on this value."""

	WHATIF_SOLVE = "whatif.solve"
	WHATIF_FRONTIER = "whatif.frontier"
	WHATIF_COMPARE = "whatif.compare"
	SCENARIO_BUILD = "scenario.build"


class JobState(StrEnum):
	"""Where a job is in its life.

	``INTERRUPTED`` is the state a job takes when the process that was running it
	died. It is distinct from ``FAILED`` because a job that was interrupted may
	be safe to retry, and distinct from ``RUNNING`` because a job in ``RUNNING``
	whose heartbeat has stopped is exactly the state that must not be reported as
	still working.
	"""

	QUEUED = "queued"
	RUNNING = "running"
	SUCCEEDED = "succeeded"
	FAILED = "failed"
	INTERRUPTED = "interrupted"


TERMINAL_JOB_STATES = frozenset({JobState.SUCCEEDED, JobState.FAILED, JobState.INTERRUPTED})


class JobAcceptedOut(ApiModel):
	"""The 202 body: a job id and where to watch it."""

	job_id: str
	kind: JobKind
	status: JobState
	status_url: str
	result_url: str


class JobStatusOut(ApiModel):
	"""A job's current state."""

	job_id: str
	kind: JobKind
	status: JobState
	created_at: datetime
	updated_at: datetime
	progress: float = Field(default=0.0, ge=0.0, le=1.0)
	attempts: int = Field(default=0, ge=0)
	result_url: str | None = None
	error: str | None = None
	requested_by: str = ""

	@property
	def is_terminal(self) -> bool:
		"""Whether the job has stopped for good."""
		return JobState(self.status) in TERMINAL_JOB_STATES


class WhatIfResultOut(ApiModel):
	"""The result of one what-if solve."""

	job_id: str
	scenario_id: str
	name: str
	objective: ValueOut
	total_capacity_mw: ValueOut
	capacity_mix: list[CapacityRowOut]
	emissions: ValueOut
	parameters: ScenarioParametersIn
	network_checksum: str
	result_checksum: str


class FrontierPointOut(ApiModel):
	"""One point on an efficient frontier."""

	parameter_value: float
	objective: ValueOut
	emissions: ValueOut


class WhatIfFrontierOut(ApiModel):
	"""A swept frontier: the trade-off curve, not a single answer."""

	job_id: str
	parameter: str
	points: list[FrontierPointOut]


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


class ReportOut(ApiModel):
	"""A generated report and where its artefact lives."""

	cadence: str
	report_date: str
	title: str
	generated_at: datetime
	checksum: str = ""
	formats: list[str] = Field(default_factory=list)
	provenance: ProvenanceOut | None = None


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------


class SignalReviewRequest(ApiModel):
	"""An analyst's decision on one extracted signal.

	An edit produces a new signal version, never a mutation (10-layer7 §6.2), so
	the original extraction stays readable and the extraction error stays
	measurable.
	"""

	signal_id: str = Field(min_length=1)
	action: Literal["confirm", "reject", "edit", "merge"]
	analyst: str = Field(min_length=1)
	edits: dict[str, Any] = Field(default_factory=dict)
	reason: str = ""

	@model_validator(mode="after")
	def _edits_require_an_edit(self) -> SignalReviewRequest:
		if self.action != "edit" and self.edits:
			raise ValueError(
				f"action={self.action!r} cannot carry edits; only an edit produces "
				f"a new signal version"
			)
		return self


class ReviewActionOut(ApiModel):
	"""The append-only record of one review decision."""

	action_id: str
	signal_id: str
	analyst: str
	action: str
	edits: dict[str, Any] = Field(default_factory=dict)
	reason: str = ""
	at: datetime


class SignalSummaryOut(ApiModel):
	"""A signal in a listing, without its evidence quotes."""

	signal_id: str
	signal_type: SignalType
	confidence: float = Field(ge=0.0, le=1.0)
	country_iso: CountryIso
	source_name: str
	source_url: str
	extracted_at: datetime
	requires_review: bool


def _extracted_quantity(signal: Signal, field: str, unit: str) -> ValueOut | None:
	"""A signal's extracted quantity as a :class:`ValueOut`, or ``None``.

	The uncertainty is ``1 - confidence``: a claim the extractor was 80% sure
	of is a number that is 20% in doubt, and stating that is the whole point of
	carrying the basis. It is never zero for a present value -- the contract
	refuses a modelled number with no uncertainty -- because an extraction is
	never exact, however confident the extractor was.
	"""
	value = getattr(signal, field, None)
	if value is None:
		return None
	uncertainty = min(max(1.0 - float(signal.confidence), 1e-6), 1.0)
	return ValueOut(
		value=float(value),
		unit=unit,
		basis=ValueBasis.MODELLED,
		uncertainty=uncertainty,
		source_id=signal.signal_id,
	)


class SignalOut(SignalSummaryOut):
	"""A full signal, with its evidence and its quantitative payload.

	``capacity_mw`` and ``investment_usd`` are :class:`ValueOut`, not bare
	floats. A signal is an *extracted* claim -- a language model or a regex read
	it out of a document -- so the number is by construction unconfirmed, and
	serving it as ``{"capacity_mw": 2100}`` lets a consumer render ``2100 MW``
	as though an analyst had checked it. The value contract (11-layer8 §3.3)
	applies here exactly as it does to a solved capacity mix: the basis travels
	with the number. A signal's quantity is modelled with the extraction's own
	confidence as its uncertainty, which is the honest statement of how much the
	number can be trusted before review.
	"""

	description: str = ""
	capacity_mw: ValueOut | None = None
	investment_usd: ValueOut | None = None
	technology: str | None = None
	evidence_quotes: list[str] = Field(default_factory=list)
	uncertainty_notes: str = ""

	@classmethod
	def from_signal(cls, signal: Signal) -> SignalOut:
		"""Project the scanning layer's contract onto the wire model."""
		assert signal.signal_id, "a signal without an id cannot be served"
		return cls(
			signal_id=signal.signal_id,
			signal_type=signal.signal_type,
			confidence=signal.confidence,
			country_iso=signal.country_iso,
			source_name=signal.source_name,
			source_url=signal.source_url,
			extracted_at=signal.extracted_at,
			requires_review=signal.requires_review,
			description=signal.description,
			capacity_mw=_extracted_quantity(signal, "capacity_mw", "MW"),
			investment_usd=_extracted_quantity(signal, "investment_usd", "USD"),
			technology=signal.technology,
			evidence_quotes=list(signal.evidence_quotes),
			uncertainty_notes=signal.uncertainty_notes,
		)


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


class ApiKeyCreateRequest(ApiModel):
	"""An administrator's request to mint a key."""

	name: str = Field(min_length=1, max_length=200)
	tier: str = "public"
	expires_at: datetime | None = None


class ApiKeyCreatedOut(ApiModel):
	"""The one and only time a key's plaintext is visible.

	The key is returned here and stored hashed; if it is lost it is revoked and
	reissued, because nothing can recover it. This is the whole point of hashing
	at rest (11-layer8 §4.2).
	"""

	key_id: str
	key: str
	name: str
	tier: str
	created_at: datetime
	expires_at: datetime | None = None


class ApiKeyOut(ApiModel):
	"""A key's metadata. Never its material."""

	key_id: str
	name: str
	tier: str
	created_at: datetime
	expires_at: datetime | None = None
	revoked: bool
	last_used_at: datetime | None = None


# --------------------------------------------------------------------------
# Registry and system
# --------------------------------------------------------------------------


class CountryOut(ApiModel):
	"""One AU member state.

	``population`` stays a plain count. It is reference metadata read from the
	registry, which records no basis or uncertainty for it, and wrapping it in a
	:class:`ValueOut` would force an uncertainty to be invented -- the exact
	fabrication the value contract exists to prevent. The contract applies to
	the quantities the platform measures and models (see ``test_values_carry_basis``).
	"""

	iso2: str
	iso3: str
	name: str
	power_pool: str
	completeness: str
	population: int | None = None
	needs_proxy_data: bool = False
	notes: str = ""


class TechnologyOut(ApiModel):
	"""One generation, storage or conversion technology.

	``co2_intensity_t_per_mwh`` likewise stays a plain number for the same
	reason: the registry holds a bare literature value with no basis recorded.
	"""

	carrier: str
	name: str
	carrier_class: str
	renewable: bool = False
	storage: bool = False
	co2_intensity_t_per_mwh: float | None = None


class HealthOut(ApiModel):
	"""Liveness and the state of the stores the API depends on."""

	status: Literal["ok", "degraded"]
	version: str
	uptime_seconds: float = Field(ge=0.0)
	database: Literal["ok", "unavailable"]
	jobs_queued: int = Field(ge=0)
	jobs_running: int = Field(ge=0)


class VersionOut(ApiModel):
	"""What is running."""

	name: str
	version: str
	api_version: str
	python: str


class RunOut(ApiModel):
	"""One pipeline run, as recorded in the run log.

	The run id is threaded through logs, artefact provenance and report footers
	(00-architecture §8), which is what makes "which run produced this number"
	answerable. This endpoint reads that join back out.
	"""

	run_id: str
	component: str
	started_at: datetime
	finished_at: datetime | None = None
	status: Literal["running", "succeeded", "failed"]
	artefacts: list[str] = Field(default_factory=list)
	detail: str = ""


# --------------------------------------------------------------------------
# Delivery adapters
# --------------------------------------------------------------------------


class UssdRequest(ApiModel):
	"""One USSD turn from a telco aggregator.

	``text`` is the concatenated user input for the session: empty on the first
	turn, ``"1"`` after the user pressed 1, ``"1*2"`` after a second choice.
	"""

	session_id: str = Field(min_length=1)
	phone_number: str = Field(min_length=1)
	service_code: str = ""
	text: str = ""


class UssdResponse(ApiModel):
	"""One USSD screen. Hard-bounded at :data:`USSD_MAX_CHARS`."""

	text: str = Field(max_length=USSD_MAX_CHARS)
	end_session: bool = False

	@model_validator(mode="after")
	def _screen_fits(self) -> UssdResponse:
		if len(self.text) > USSD_MAX_CHARS:
			raise ValueError(
				f"USSD text is {len(self.text)} characters, limit {USSD_MAX_CHARS}; "
				f"truncation is not acceptable, select fewer rows instead"
			)
		return self


class SmsResponse(ApiModel):
	"""One SMS. Hard-bounded at :data:`SMS_MAX_CHARS`."""

	text: str = Field(max_length=SMS_MAX_CHARS)
	link: str = ""

	@model_validator(mode="after")
	def _message_fits(self) -> SmsResponse:
		if len(self.text) > SMS_MAX_CHARS:
			raise ValueError(
				f"SMS text is {len(self.text)} characters, limit {SMS_MAX_CHARS}"
			)
		return self


class DeliveryResultOut(ApiModel):
	"""The record of one adapter delivery (09-layer6 §5)."""

	channel: str
	recipients: list[str]
	sent_at: datetime
	status: Literal["sent", "failed", "skipped"]
	detail: str = ""


# Re-exported for route signatures that annotate a bounded query parameter.
PageSize = Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)]


# --------------------------------------------------------------------------
# The parameter relationship graph
# --------------------------------------------------------------------------


class PrgSummaryOut(ApiModel):
	"""The graph's own counts, and the registers that qualify them.

	The registers are the point, not the counts: a client that sees only
	``parameters`` and ``equations`` will assume the engine is driven by all of
	them. ``engine_translation`` says how many settable parameters reach a
	what-if knob, ``units`` says how many equations the dimensional check could
	decide, and ``uncertainty`` says what the stochastic declarations reach.
	"""

	parameters: int = Field(ge=0)
	equations: int = Field(ge=0)
	edges: int = Field(ge=0)
	derived: int = Field(ge=0)
	systems: dict[str, int]
	systems_declared: int = Field(ge=0)
	unmodelled_systems: list[str]
	feedback_loops: list[str]
	structure_issues: list[str]
	cross_validation_rules: list[str]
	engine_translation: EngineTranslationOut
	units: UnitReportOut
	uncertainty: UncertaintyOut


class EngineTranslationOut(ApiModel):
	"""How much of the graph reaches a what-if knob. Three of fifty-three.

	``engine_unreached`` is the other direction and a different finding: an
	engine knob no PRG parameter names is a lever a scenario can pull that the
	graph never sees, so a result solved from one cannot be audited against the
	graph's identities. A payload carrying only ``count``/``total`` would let a
	client render the coverage as a single number and miss that.
	"""

	translated: list[str]
	untranslated: list[str]
	engine_unreached: list[str]
	count: int = Field(ge=0)
	total: int = Field(ge=0)
	fraction: float = Field(ge=0.0, le=1.0)


class UnitReportOut(ApiModel):
	"""The dimensional check: which equations are consistent, which are not."""

	consistent: list[EquationCheckOut]
	inconsistent: list[EquationCheckOut]
	undecidable: list[EquationCheckOut]
	summary: str


class EquationCheckOut(ApiModel):
	"""One equation's dimensional verdict.

	``decidable`` is carried alongside ``consistent`` because the two are
	different claims: an equation the walker could not decide is not a pass,
	and a client that rendered it as one would be reporting a green the check
	never gave.
	"""

	equation_id: str
	decidable: bool
	consistent: bool
	lhs: str
	rhs: str
	detail: str


class UncertaintyOut(ApiModel):
	"""What the graph declares uncertain, and what that reaches."""

	inputs: list[str]
	derived_stochastic: list[str]
	reachable: list[str]
	stochastic_edges: list[list[str]]
	summary: str


class EquationOut(ApiModel):
	"""One equation, rendered."""

	equation_id: str
	system: str
	rendered: str


class ConflictOut(ApiModel):
	"""One inconsistency, with the corrections that would resolve it.

	``residual`` and ``tolerance`` are in the units of the violating equation's
	two sides -- which share a dimension, or the equation would be flagged by
	the dimensional check -- so ``unit`` names it. A residual without its unit
	is the bare number the value contract forbids.
	"""

	kind: str
	subject: str
	detail: str
	unit: str
	residual: float
	tolerance: float
	corrections: list[CorrectionOut]


class CorrectionOut(ApiModel):
	"""A move that would resolve a conflict.

	``relative_move`` is the number to rank on: a 0.2 move in an emission
	factor and an 82 USD/t move in a carbon price can be the same real-world
	size, and ordering by ``delta`` orders by the unit. ``unit`` is the
	parameter's, so ``delta`` and ``current`` are interpretable.
	"""

	parameter: str
	unit: str
	delta: float
	elasticity: float
	within_range: bool
	current: float
	relative_move: float


class ConflictReportOut(ApiModel):
	"""The conflicts in a parameter set, ranked, and what was examined."""

	conflicts: list[ConflictOut]
	checked: list[str]
	consistent: bool
	summary: str


class SensitivityOut(ApiModel):
	"""A derived parameter's derivatives with respect to its inputs.

	``method`` says how the row was produced -- ``input``, ``symbolic``, or
	``implicit`` for a loop variable solved through the implicit function
	theorem -- because a reader weighing the numbers needs to know which.
	"""

	parameter: str
	method: str
	value: float | None
	derivatives: dict[str, float]


class SensitivityRequest(ApiModel):
	"""A parameter set to differentiate at, with optional overrides."""

	parameter: str
	set: dict[str, float] = Field(default_factory=dict)
	top: int = Field(default=10, ge=1, le=100)


class ConflictRequest(ApiModel):
	"""A parameter set to check for conflicts.

	``set`` may name a derived parameter -- unlike ``prg check`` -- because
	setting one is exactly the over-determination this endpoint reports.
	"""

	set: dict[str, float] = Field(default_factory=dict)
	rank: int = Field(default=3, ge=1, le=20)


class CrossValidationRuleOut(ApiModel):
	"""One declared rule: the condition as written, and what it means."""

	id: str
	condition: str
	severity: str
	message: str
	suggestion: str
	parameters: list[str]


class CrossValidationFindingOut(ApiModel):
	"""One rule's verdict.

	``evaluated`` is carried alongside the finding because the two are
	different claims: a rule the scenario did not carry the parameters to run
	is not a pass, and a client that rendered it as one would be reporting a
	green the check never gave. ``detail`` says why when it is ``False``.
	"""

	rule_id: str
	severity: str
	evaluated: bool
	message: str
	suggestion: str
	detail: str


class CrossValidationReportOut(ApiModel):
	"""The cross-validation verdicts, with the denominator."""

	findings: list[CrossValidationFindingOut]
	rules: list[CrossValidationRuleOut]
	violations: int = Field(ge=0)
	undecided: int = Field(ge=0)
	blocks: bool
	"""Whether an ``error``-severity rule was violated, which is the gate."""

	summary: str


__all__ = [
	"DEFAULT_PAGE_SIZE",
	"MAX_PAGE_SIZE",
	"SMS_MAX_CHARS",
	"TERMINAL_JOB_STATES",
	"USSD_MAX_CHARS",
	"ApiKeyCreateRequest",
	"ApiKeyCreatedOut",
	"ApiKeyOut",
	"ApiModel",
	"CapacityRowOut",
	"CaptureRateRowOut",
	"ContingencyRowOut",
	"CountryOut",
	"DeliveryResultOut",
	"ErrorOut",
	"FrontierPointOut",
	"HealthOut",
	"JobAcceptedOut",
	"JobKind",
	"JobState",
	"JobStatusOut",
	"LossComponentOut",
	"LossDecompositionOut",
	"MaintenancePredictionRowOut",
	"MitigationOptionOut",
	"OutageForecastRowOut",
	"OutageHistoryRowOut",
	"OutageValidationRowOut",
	"Page",
	"PageSize",
	"PpaBenchmarkRowOut",
	"PriceRowOut",
	"ProvenanceOut",
	"ReportOut",
	"ResilienceMetricOut",
	"ReviewActionOut",
	"RunOut",
	"ScenarioOut",
	"ScenarioParametersIn",
	"ScenarioResultOut",
	"ScenarioSummaryOut",
	"SignalOut",
	"SignalReviewRequest",
	"SignalSummaryOut",
	"SmsResponse",
	"TechnologyOut",
	"TlensRowOut",
	"TopologyLineOut",
	"TopologyOut",
	"UssdRequest",
	"UssdResponse",
	"ValueBasis",
	"ValueOut",
	"VersionOut",
	"WhatIfCompareRequest",
	"WhatIfFrontierOut",
	"WhatIfFrontierRequest",
	"WhatIfResultOut",
	"WhatIfSolveRequest",
	"ConflictOut",
	"ConflictReportOut",
	"ConflictRequest",
	"CorrectionOut",
	"CrossValidationFindingOut",
	"CrossValidationReportOut",
	"CrossValidationRuleOut",
	"EngineTranslationOut",
	"EquationCheckOut",
	"EquationOut",
	"PrgSummaryOut",
	"SensitivityOut",
	"SensitivityRequest",
	"UncertaintyOut",
	"UnitReportOut",
]
