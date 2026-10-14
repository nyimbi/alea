# SPDX-License-Identifier: MIT
"""Configuration models.

Every model here forbids extra keys. An unknown key is a typo, and a typo that
reaches a solve costs hours; failing at load costs a second and names the key.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from alea.config.base import AleaConfig
from alea.losses.views import LossConfig
from alea.market.views import MarketConfig
from alea.outages.views import PredictiveConfig
from alea.resilience.views import ResilienceConfig
from alea.signals.models import CountryIso
from alea.whatif.views import WhatIfConfig


class ScenarioConfig(AleaConfig):
	"""What to model."""

	countries: list[CountryIso] = Field(min_length=1)
	clusters: list[int] = Field(default_factory=lambda: [55], min_length=1)
	planning_horizons: list[int] = Field(
		default_factory=lambda: [2030, 2040, 2050, 2060], min_length=1
	)
	base_year: int = 2025
	# No `spatial_resolution_deg`. It was declared here, set in
	# config.default.yaml and in the continental scenario, documented as "0.01 deg
	# is the Ghana study's best value" -- and read by nothing. The number is the
	# specification's `aggregate_to_zones(anomaly, resolution="0.01_degree")`
	# (spec4-base §12.2), so it is a *detection* parameter and never belonged to a
	# scenario: the scenario's resolution is `clusters`, which the network builder
	# consumes. It is not wired to the detector either, because the resolution is
	# only meaningful against a geolocation -- a 0.01 deg cell is a position, not
	# a tile offset -- and no plan specifies how a granule is georeferenced. See
	# `io.stages._zones`, which states the same gap at the point of use.

	@model_validator(mode="after")
	def _countries_are_named(self) -> ScenarioConfig:
		# `CountryIso` is `str | None` because a *signal* may arrive without a
		# country. A scenario is the opposite: it exists to say what to model,
		# and one naming no country models nothing. Without this, `[null]`
		# validates and then crashes wherever the list is joined or looked up.
		missing = [i for i, iso in enumerate(self.countries) if iso is None]
		if missing:
			raise ValueError(
				f"scenario.countries has no country at index {missing[0]}; a "
				f"scenario must name the countries to model"
			)
		return self

	@model_validator(mode="after")
	def _horizons_ascend(self) -> ScenarioConfig:
		if self.planning_horizons != sorted(self.planning_horizons):
			raise ValueError(
				f"planning_horizons must be ascending, got {self.planning_horizons}"
			)
		if self.base_year >= self.planning_horizons[0]:
			raise ValueError(
				f"base_year ({self.base_year}) must precede the first horizon "
				f"({self.planning_horizons[0]})"
			)
		return self

	@model_validator(mode="after")
	def _clusters_ascend(self) -> ScenarioConfig:
		if self.clusters != sorted(self.clusters):
			raise ValueError(f"clusters must be ascending, got {self.clusters}")
		return self


class SolveConfig(AleaConfig):
	"""How to solve."""

	solver: Literal["highs", "gurobi", "cplex", "glpk"] = "highs"
	transmission_losses: bool = True
	"""Losses are modelled by default.

	The specification's own benchmark (PyPSA-Eur) found that neglecting losses
	overestimates optimal expansion by roughly 20%, and losses consume 15-25% of
	generated energy in many African systems. A default of ``False`` would mean
	every published capacity mix was wrong by default. See 04-layer1 §5.1.
	"""
	linearized_unit_commitment: bool = False
	multi_investment_periods: bool = True
	time_aggregation: int = Field(default=1, ge=1)
	"""TSAM representative periods. 1 means full hourly resolution.

	Any value above 1 requires a passing validation artefact for the network
	(AD-9); see ``alea.planning.aggregation``.
	"""
	solver_options: dict[str, Any] = Field(default_factory=dict)
	solver_timeout_s: int = Field(default=3600, gt=0)

	@model_validator(mode="after")
	def _commercial_solver_must_be_installed(self) -> SolveConfig:
		# Catching an absent solver here beats discovering it forty minutes into
		# a model build.
		if self.solver in ("gurobi", "cplex"):
			import importlib.util

			if importlib.util.find_spec(self.solver) is None:
				raise ValueError(
					f"solver={self.solver!r} selected but not installed; use "
					f"'highs' (MIT, bundled with pypsa) or install the solver"
				)
		return self


class RenewableConfig(AleaConfig):
	"""One renewable carrier's resource parameters."""

	enabled: bool = True
	cutout: str = "africa-era5"
	method: str = "pv"
	capacity_per_sqkm: float = Field(default=1.7, gt=0.0)
	resource_params: dict[str, Any] = Field(default_factory=dict)


class SectorConfig(AleaConfig):
	"""Sector coupling. Extends the electricity network; never replaces it."""

	enabled: bool = False

	hydrogen_enabled: bool = False
	electrolyser_efficiency_lhv: float = Field(default=0.65, gt=0.0, le=1.0)
	electrolyser_efficiency_source: str = ""
	hydrogen_export_twh_per_year: float = Field(default=0.0, ge=0.0)

	heat_pumps_enabled: bool = False
	heat_pump_cop: float = Field(default=3.0, gt=0.0)
	heat_pump_cop_source: str = ""

	ev_smart_charging: bool = False
	v2g_enabled: bool = False
	v2g_degradation_usd_per_mwh: float = Field(default=0.0, ge=0.0)

	industry_steel: bool = False
	industry_cement: bool = False
	industry_chemicals: bool = False

	@model_validator(mode="after")
	def _physical_parameters_are_sourced(self) -> SectorConfig:
		# An efficiency nobody can trace is how a hydrogen result becomes
		# indefensible. Every physical constant carries its source. See 05-layer2.
		missing: list[str] = []
		if self.hydrogen_enabled and not self.electrolyser_efficiency_source:
			missing.append("electrolyser_efficiency_source")
		if self.heat_pumps_enabled and not self.heat_pump_cop_source:
			missing.append("heat_pump_cop_source")
		if missing:
			raise ValueError(
				"physical parameters require a source so the result is "
				f"defensible; missing: {', '.join(missing)}"
			)
		return self

	@model_validator(mode="after")
	def _v2g_has_a_cost(self) -> SectorConfig:
		# V2G without a degradation cost is free storage, which the optimiser
		# will use without limit and which no real fleet provides.
		if self.v2g_enabled and self.v2g_degradation_usd_per_mwh <= 0.0:
			raise ValueError(
				"v2g_enabled requires v2g_degradation_usd_per_mwh > 0; "
				"free storage is not a modelling result"
			)
		return self


class CostsConfig(AleaConfig):
	"""Currency handling. Every conversion records its rate and the rate's date."""

	base_currency: str = "USD"
	eur_usd: float | None = Field(default=None, gt=0.0)
	eur_usd_date: str | None = None
	kes_usd: float | None = Field(default=None, gt=0.0)
	kes_usd_date: str | None = None

	@model_validator(mode="after")
	def _rates_carry_their_date(self) -> CostsConfig:
		# The project's own history includes a document that converted $1M at
		# 145 KES while stating its target in KES at a different implied rate: a
		# 10% self-contradiction invisible to every lint, because each number
		# was internally consistent with its own line. A rate without its date
		# is the same defect waiting to happen.
		for pair in (("eur_usd", "eur_usd_date"), ("kes_usd", "kes_usd_date")):
			rate, date = pair
			if getattr(self, rate) is not None and getattr(self, date) is None:
				raise ValueError(f"{rate} requires {date}: a rate without its date is not a rate")
		return self


class ScanningConfig(AleaConfig):
	"""Layer 7."""

	enabled: bool = False
	raw_text_retention_days: int = Field(default=90, ge=1)
	"""Retention for source document text.

	Social platforms restrict long-term storage of their content. The platform
	stores signal-level extractions with the source URL; raw text expires.
	"""
	dedup_threshold: float = Field(default=0.7, gt=0.0, lt=1.0)
	dedup_num_perm: int = Field(default=128, gt=0)
	dedup_seed: int = Field(default=0)
	"""Required, never defaulted to Python's randomised ``hash()``. See 10-layer7 §4.2."""
	llm_model: str = "claude-sonnet-5-5"
	llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
	llm_cache: bool = True
	auto_accept_threshold: float | None = Field(default=None, gt=0.0, le=1.0)
	"""Precision-gated auto-acceptance. ``None`` means every signal is reviewed.

	An extractor that is 91% right and auto-accepts is wrong 9% of the time,
	silently. A threshold is introduced only after a measured precision
	justifies it, per signal type.
	"""


class ReportingConfig(AleaConfig):
	"""Layer 6."""

	enabled: bool = False
	timezone: str = "UTC"
	email_enabled: bool = False
	smtp_host: str = ""
	smtp_port: int = Field(default=587, gt=0)
	smtp_user: str = ""
	email_from: str = ""
	daily_hour: int = Field(default=6, ge=0, le=23)
	weekly_day: str = "mon"
	pdf_enabled: bool = True

	@model_validator(mode="after")
	def _email_needs_configuration(self) -> ReportingConfig:
		# Validated at load, not at 06:00 when the report is due and the
		# KeyError surfaces with nobody watching.
		if self.email_enabled and not (self.smtp_host and self.email_from):
			raise ValueError(
				"email_enabled requires smtp_host and email_from; "
				"configuration is validated at load, not at send time"
			)
		return self


class ApiConfig(AleaConfig):
	"""Layer 8."""

	enabled: bool = False
	title: str = "ALEA API"
	version: str = "0.1.0"
	rate_limit_per_minute: int = Field(default=60, gt=0)
	job_store_path: str = "results/jobs.sqlite"
	cache_ttl_seconds: int = Field(default=3600, gt=0)
	"""The default response-cache lifetime, in seconds. §6's "1 hour".

	Applied to a cacheable response whose own lifetime is not declared below.
	This is the knob an operator turns to trade freshness against load without
	editing a route.
	"""
	cache_ttl_history_seconds: int = Field(default=86400, gt=0)
	"""Historical outages: §6's "1 day", because history changes only when new
	events are ingested."""
	cache_ttl_topology_seconds: int = Field(default=86400, gt=0)
	"""Topology: §6's "1 day", because the network changes on a rebuild."""


class PathsConfig(AleaConfig):
	"""Where things live. Relative to the repository root unless absolute."""

	raw: str = "data/raw"
	interim: str = "data/interim"
	processed: str = "data/processed"
	resources: str = "resources"
	results: str = "results"
	reports: str = "reports"
	models: str = "models"


class LoggingConfig(AleaConfig):
	level: str = "INFO"
	json_output: bool = False


class Config(AleaConfig):
	"""The root configuration.

	Composed of one model per concern. Deep-merged from default file, an
	environment file, a scenario overlay, and CLI overrides, in that order of
	increasing precedence (see ``alea.config.loader``).
	"""

	scenario: ScenarioConfig
	solve: SolveConfig = Field(default_factory=SolveConfig)
	sector: SectorConfig = Field(default_factory=SectorConfig)
	costs: CostsConfig = Field(default_factory=CostsConfig)
	scanning: ScanningConfig = Field(default_factory=ScanningConfig)
	reporting: ReportingConfig = Field(default_factory=ReportingConfig)
	api: ApiConfig = Field(default_factory=ApiConfig)
	paths: PathsConfig = Field(default_factory=PathsConfig)
	logging: LoggingConfig = Field(default_factory=LoggingConfig)
	renewables: dict[str, RenewableConfig] = Field(default_factory=dict)
	predictive: PredictiveConfig = Field(default_factory=PredictiveConfig)
	"""Layer 4a: outage detection, forecasting, maintenance, ensemble.

	``alea.outages.service.predictive_config`` reads this section through
	``getattr`` and falls back to the class defaults when it is absent -- which
	it always was, because the root model had no such field and ``extra="forbid"``
	made a ``predictive:`` block in YAML a load error rather than a setting. Every
	detection parameter was therefore pinned to its default and an operator could
	not move one: the VZA bin size, the baseline quantile, the detection
	threshold and the cloud ceiling were config in name only. 07-layer4 §2.1
	states the opposite -- "three parameters, all config, all recorded" -- and a
	parameter nobody can set is a parameter the provenance records as a constant.
	"""

	losses: LossConfig = Field(default_factory=LossConfig)
	"""Layer 4b: loss decomposition, DC flow, TLENS, mitigation ranking.

	§7 makes the payback the thing that matters -- "a single-snapshot payback is
	a number with no error bar that will be believed" -- and the price it divides
	by was unreachable, so every published payback used the default
	``price_usd_per_mwh = 0.0``. A payback of zero capex over zero savings is
	``NaN``, which §7 requires be *reported* with a note; the field's absence
	made that the only reachable outcome. ``snapshot_hours`` is the same defect
	with a sharper edge: it is the factor that keeps a MW loss from being printed
	as MWh, and a caller could not set it.
	"""

	resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
	"""Layer 4c: ENS, EENS, SAIDI, SAIFI.

	§8 is explicit that the interruption threshold "is config, recorded, and
	reported with the metric", because two SAIDI figures at different thresholds
	are different quantities sharing a name. The threshold, the household size
	and the electrification rate all defaulted, so the recorded threshold was a
	constant and the SAIDI the platform published could not be matched to a
	utility's own number even in principle.
	"""

	whatif: WhatIfConfig = Field(default_factory=WhatIfConfig)
	"""Layer 5: which parameter the quarterly `scenario_update` sweeps.

	``reporting/quarterly.py``'s ``scenario_update`` section is a range across a
	scenario set, and which set is a choice, not a constant. The sweep had no
	home: `alea.whatif` could run one from a call and the API could write one to
	a caller's path, but nothing named the parameter a *report* is over, so the
	section was unproduced and no config key could change that. The parameter
	value is validated against `ScenarioParameters` at load, because a typo
	there is otherwise a `KeyError` several minutes into a sweep.
	"""

	market: MarketConfig = Field(default_factory=MarketConfig)
	"""Layer 3: the value of lost load.

	The one market parameter no layer produces. `market.clearing` prices a
	shortfall at this rate, so it decides the clearing price of every hour the
	system sheds load -- and it had no home at all: no config key, no field on
	any model, and no value in `spec/` or `docs/plans/`. The only figure in the
	tree was the determinism job's, which is where the default comes from.
	Without this field a `market:` block in YAML is a load error under
	``extra="forbid"``, so the rate a run cleared at could not be set, recorded
	or changed.
	"""

	@model_validator(mode="after")
	def _aggregation_needs_a_single_network(self) -> Config:
		# Time aggregation above 1 is only meaningful once a network exists and
		# has been validated at that level. The check that an artefact exists
		# lives in alea.planning.aggregation, because it needs the filesystem;
		# this validator catches the configuration that could never be valid.
		if self.solve.time_aggregation > 1 and len(self.scenario.planning_horizons) < 1:
			raise ValueError("time_aggregation > 1 requires at least one planning horizon")
		return self


CountryList = Annotated[list[CountryIso], Field(min_length=1)]

__all__ = [
	"AleaConfig",
	"ApiConfig",
	"Config",
	"CostsConfig",
	"LoggingConfig",
	"MarketConfig",
	"PathsConfig",
	"PredictiveConfig",
	"RenewableConfig",
	"ReportingConfig",
	"ScenarioConfig",
	"ScanningConfig",
	"SectorConfig",
	"SolveConfig",
]
