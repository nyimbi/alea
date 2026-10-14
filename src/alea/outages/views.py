# SPDX-License-Identifier: MIT
"""Models for Layer 4a — outage detection, forecasting, maintenance, ensemble.

Configuration and result models live here so that every parameter that
influences a published detection number is a typed field rather than a literal
buried in a function. The three VIIRS parameters in particular are recorded in
provenance: an outage-detection AUC without its VZA bin size, quantile and
threshold is not reproducible, and 07-layer4 §2.5 says so explicitly.

``PredictiveConfig`` is the root ``Config``'s ``predictive`` section, so a
parameter set in YAML reaches the detection path. This module imports only
``AleaConfig`` from the config package -- not ``alea.config.models`` -- because
the root model imports *this* module for the section's type, and importing the
parent back would close a cycle that resolves only when the import order happens
to define the name first.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, model_validator

from alea.config.base import AleaConfig
from alea.provenance.models import Basis


def _strictly_between_zero_and_one(value: float) -> float:
	if not 0.0 < value < 1.0:
		raise ValueError(f"must lie strictly in (0, 1), got {value}")
	return value


def _between_zero_and_one(value: float) -> float:
	if not 0.0 < value <= 1.0:
		raise ValueError(f"must lie in (0, 1], got {value}")
	return value


UnitInterval = Annotated[float, AfterValidator(_strictly_between_zero_and_one)]
"""A quantile or probability. 0 and 1 are excluded: both make a quantile
degenerate (the minimum or the maximum), which silently turns a robust
baseline into an extremum."""

Fraction = Annotated[float, AfterValidator(_between_zero_and_one)]


class ViirsConfig(AleaConfig):
	"""The three pinned detection parameters, plus the band selection.

	07-layer4 §2.1: "Three parameters, all config, all recorded."
	"""

	bin_size_deg: float = Field(default=5.0, gt=0.0, le=90.0)
	"""VZA bin width. The specification's 5 deg to 70 deg."""

	baseline_quantile: UnitInterval = 0.25
	"""First quartile, not the mean: robust to occasional bright events (lunar
	reflection, fires) while preserving sensitivity to darkening."""

	detection_threshold: Fraction = 0.6
	"""A pixel is flagged when radiance < threshold x baseline."""

	max_cloud_confidence: int = Field(default=0, ge=0, le=3)
	"""Ceiling on QF_Cloud_Mask bits 0-1. 0 keeps confident-clear only.

	The specification writes both ``& 0b11 == 0`` and ``& 0b11 != 0`` in
	different places. This field is the pinned answer: only ``00`` (confident
	clear) is safe, and cloudy pixels become NaN — *unknown*, not *lit* —
	because NaN and 0 aggregate differently. See 07-layer4 §2.2.
	"""

	radiance_band: str = "DNB_BRDF_Corrected_NTL"
	"""The observed, BRDF-corrected band. Never the gap-filled band, which
	interpolates across cloudy observations so a cloud reads as "no outage"."""

	min_observations: int = Field(default=1, ge=1)
	"""Observations a (pixel, bin, month) cell needs before its baseline is
	trusted. The kernel returns NaN for an empty cell regardless; this is the
	floor the Python layer asserts on so a one-observation "baseline" is
	visible rather than silently used."""


class WeatherConfig(AleaConfig):
	"""Weather-driven outage forecasting."""

	month_encoding: Literal["cyclical", "hemisphere", "integer"] = "cyclical"
	"""How the month becomes a feature.

	``cyclical`` is ``sin(2*pi*m/12), cos(2*pi*m/12)`` and carries no
	hemisphere assumption — the correct default for a continent that straddles
	the equator. ``hemisphere`` derives a meteorological season from latitude.
	``integer`` is the specification's ``(month % 12 + 3) // 3``, which encodes
	a northern-hemisphere DJF/MAM/JJA/SON cycle and is backwards south of the
	equator; it is retained only so the defect is reproducible and canaried.
	"""

	outage_history_window_hours: int = Field(default=30 * 24, gt=0)
	"""Window for the lagged outage-rate feature. Lagged by one hour, never
	zero: without the shift the feature contains the hour it is predicting."""

	target_derived_columns: tuple[str, ...] = ("outage", "flagged_fraction")
	"""Columns the model must never see contemporaneously.

	``outage`` is the label, and every feature built from it carries
	``lag >= 1``.

	``flagged_fraction`` is the *detector's own fraction*, and the label is
	that fraction thresholded: ``outage == (flagged_fraction >=
	zone_flagged_fraction)``. A model handed the present hour's fraction does
	not forecast, it reads the answer -- and it reads it perfectly, because the
	threshold is deterministic. The empirical leak audit cannot see this on its
	own: it perturbs the *target* and re-checks the feature, and
	``flagged_fraction`` is invariant to a perturbation of ``outage``. So the
	leak passes every causality probe while the score goes to 1.0, which is the
	one shape of defect that looks like success. Declaring it here is what
	removes it, because :func:`~alea.outages.weather.feature_names` excludes
	this tuple from the model's inputs.

	This tuple had **zero callers** until 2026-10-14 -- it was a correct
	statement of the rule with nothing applying it, which is the register's own
	defect class (a declared control is not an applied one)."""

	scale_pos_weight: float = Field(default=10.0, gt=0.0)
	"""Class-imbalance correction. Used *alone*.

	The specification applies SMOTE **and** ``scale_pos_weight=10``, which
	double-corrects: the effective positive weight becomes roughly ten times
	what SMOTE alone gives. 07-layer4 §3.3 picks ``scale_pos_weight`` because
	SMOTE interpolates between real outages and manufactures physically
	impossible weather-feature combinations.
	"""

	scale_pos_weight_candidates: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 20.0)
	"""Weights tried when the weight is selected by cross-validated PR-AUC."""

	select_weight_by_cv: bool = True
	"""Whether to choose the weight by CV PR-AUC rather than use the literal."""

	validation_fraction: UnitInterval = 0.2
	"""Fraction of the *latest* time reserved for validation. Split by time,
	never randomly: a random split trains on the future and predicts the past."""

	recall_at_precision: Fraction = 0.5
	"""The operating precision at which recall is reported. With a ~1% positive
	rate, accuracy is a number a "no outage" model gets for free."""

	horizon_hours: int = Field(default=24, gt=0)
	"""How far ahead a forecast reaches, in hours.

	``spec4-base.md`` §18.1 declares the daily section "24-hour outage
	probability" and §18.2 the weekly one "7-day". The two are the same model at
	two horizons, so the horizon is a parameter of the run rather than a literal
	at each call site -- and it is recorded in provenance, because a probability
	without the interval it applies to is not a forecast.

	The horizon also decides how far the *issued* instant is from the last
	observation: the forward frame starts one step after the history ends, so a
	24-hour horizon is the 24 hours nobody has observed yet."""

	zone_flagged_fraction: Fraction = 0.5
	"""Flagged fraction of a zone's clear pixels at which the zone-hour counts as
	an outage. **A modelling decision, and this is where it is recorded.**

	The detector reports a *fraction*: the share of a zone's clear pixels whose
	radiance fell below the baseline threshold (``viirs.zone_series``). The
	literature thresholds at the pixel (radiance < 0.6 x baseline) and publishes
	the zone fraction as the outage measure; neither the specification nor the
	plans name a zone-level threshold, so a supervised target needs one chosen.
	Half is the reading that "most of the zone went dark" -- a lower value calls
	a single dark city block a zone outage, and the base rate that follows is
	then a statement about the threshold rather than about the grid.

	It is a field rather than a constant because it *is* the target definition:
	every metric in ``ForecastMetrics`` -- PR-AUC, recall, the base rate -- is
	conditional on it, and an operator who moves it has changed the quantity
	being predicted, not the model's quality."""

	interval_level: Fraction = 0.9
	"""Nominal coverage of the forecast band, as a quantile of held-out error.

	The band the daily section renders is the ``interval_level`` quantile of
	absolute error on the time-held-out validation split, per zone. That is a
	**residual band, not a calibrated predictive interval**: the register
	recorded that no calibration function exists, and this method is the
	documented substitute rather than a number chosen to look like one. A
	quantile of the model's own error is reproducible from the run and moves
	when the model does, which a fixed +/- width would not."""

	@model_validator(mode="after")
	def _no_synthetic_oversampling(self) -> WeatherConfig:
		# The guard the plan's gate test_class_imbalance_not_double_corrected
		# canaries. There is no SMOTE field to set — the refusal is structural,
		# which is stronger than a validator that a future edit could delete.
		if getattr(self, "use_smote", False):
			raise ValueError(
				"SMOTE must not be combined with scale_pos_weight: the two "
				"double-correct the same imbalance (07-layer4 §3.3)"
			)
		return self


class MaintenanceConfig(AleaConfig):
	"""Predictive maintenance (Cox PH)."""

	require_dga: bool = True
	"""Refuse to fit without dissolved-gas columns.

	A maintenance model fitted on transformer age alone produces a number
	labelled "predictive maintenance" that is actually "transformer age". The
	guard makes the substitution impossible rather than undocumented.
	"""

	dga_columns: tuple[str, ...] = (
		"oil_dga_h2",
		"oil_dga_ch4",
		"oil_dga_c2h2",
		"oil_moisture_ppm",
	)
	"""Dissolved-gas analysis features. Utility condition-monitoring data, not
	open data: credentialed inputs, and the module states which."""

	age_columns: tuple[str, ...] = ("age_years", "maintenance_interval_days")
	penalizer: float = Field(default=0.01, ge=0.0)
	"""Ridge penalty on the Cox partial likelihood, guarding separation when
	covariates outnumber events. Kept mild: on the log-likelihood scale 0.1
	shrinks a well-identified hazard ratio by ~17% (2.5 -> 2.08 on the
	synthetic recovery frame), which is a bias the module would then report as
	a finding. 0.01 recovers the truth to ~3% while still damping separation."""

	confidence_level: Fraction = 0.95


class EnsembleConfig(AleaConfig):
	"""Combination of satellite, weather and maintenance signals."""

	method: Literal["brier_weighted"] = "brier_weighted"
	"""Calibrated weighted average, weights chosen by Brier score.

	Not a stacked classifier: a stacker needs labelled data in the overlap of
	all three modalities, and maintenance covers almost nowhere while VIIRS and
	weather cover everywhere (07-layer4 §5)."""

	calibrate: bool = True
	"""Isotonic-calibrate each component before combining. An uncalibrated
	probability averaged with calibrated ones is dominated by the miscalibrated
	one."""

	min_weight: float = Field(default=0.0, ge=0.0)


class PredictiveConfig(AleaConfig):
	"""Layer 4a root: everything an outage result is a function of."""

	viirs: ViirsConfig = Field(default_factory=ViirsConfig)
	weather: WeatherConfig = Field(default_factory=WeatherConfig)
	maintenance: MaintenanceConfig = Field(default_factory=MaintenanceConfig)
	ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)

	def parameters(self) -> dict[str, Any]:
		"""The config as a flat parameter map, for artefact provenance."""
		return {
			"viirs.bin_size_deg": self.viirs.bin_size_deg,
			"viirs.baseline_quantile": self.viirs.baseline_quantile,
			"viirs.detection_threshold": self.viirs.detection_threshold,
			"viirs.max_cloud_confidence": self.viirs.max_cloud_confidence,
			"viirs.radiance_band": self.viirs.radiance_band,
			"weather.month_encoding": self.weather.month_encoding,
			"weather.scale_pos_weight": self.weather.scale_pos_weight,
			"weather.outage_history_window_hours": self.weather.outage_history_window_hours,
			"weather.horizon_hours": self.weather.horizon_hours,
			"weather.zone_flagged_fraction": self.weather.zone_flagged_fraction,
			"weather.interval_level": self.weather.interval_level,
			"maintenance.require_dga": self.maintenance.require_dga,
			"ensemble.method": self.ensemble.method,
		}


class DetectionMetrics(AleaConfig):
	"""Detection quality. ``base_rate`` is required, not optional.

	The gate ``test_base_rate_reported`` (07-layer4 §10) exists because a 99%
	accuracy claim without its base rate is not a result: with a 1% positive
	rate, "no outage" scores 99% accuracy for free.
	"""

	auc: float
	pr_auc: float
	accuracy: float
	base_rate: float = Field(ge=0.0, le=1.0)
	precision: float = Field(ge=0.0, le=1.0)
	recall: float = Field(ge=0.0, le=1.0)
	f1: float = Field(ge=0.0, le=1.0)
	threshold: float
	n_total: int = Field(ge=0)
	n_positive: int = Field(ge=0)
	parameters: dict[str, Any] = Field(default_factory=dict)
	"""The detection parameters that produced these numbers. A metric without
	them cannot be reproduced or compared against another run."""
	basis: Basis = Basis.MODELLED
	notes: str = ""


class ForecastMetrics(AleaConfig):
	"""Forecast quality, reported as ranking metrics plus the base rate."""

	pr_auc: float
	auc: float
	base_rate: float = Field(ge=0.0, le=1.0)
	recall_at_precision: float = Field(ge=0.0, le=1.0)
	operating_precision: float = Field(ge=0.0, le=1.0)
	brier: float = Field(ge=0.0)
	scale_pos_weight: float
	n_train: int = Field(ge=0)
	n_validation: int = Field(ge=0)
	positive_rate_train: float = Field(ge=0.0, le=1.0)
	positive_rate_validation: float = Field(ge=0.0, le=1.0)
	accuracy: float
	"""Retained only so the specification's headline can be reproduced beside
	the base rate that explains it. Never report it alone."""
	features: list[str] = Field(default_factory=list)
	interval_level: float = Field(default=0.0, ge=0.0, le=1.0)
	"""Nominal coverage of the band the forecast rows carry. Zero means the run
	produced no band -- which is the state every run before this field existed
	was in, and the state the daily section rendered as an empty `Interval`
	column rather than as an error."""
	interval_method: str = ""
	"""How the band was derived. A level without its method is not reproducible:
	"the 90th percentile of absolute error on the held-out split" and "a
	calibrated predictive interval at 90%" are different objects that would
	print the same number."""
	notes: str = ""


class ValidationOutcome(AleaConfig):
	"""The result of a ground-truth comparison, including an explicit skip.

	07-layer4 §2.5: if GridWatch is unavailable the validation stage skips with
	a recorded message; it does **not** report a model as validated. ``skipped``
	makes that state representable instead of inferring it from a missing file.
	"""

	skipped: bool = False
	reason: str = ""
	ground_truth: str = ""
	metrics: DetectionMetrics | None = None

	@model_validator(mode="after")
	def _skip_states_why(self) -> ValidationOutcome:
		if self.skipped and not self.reason:
			raise ValueError("a skipped validation must record why it skipped")
		if not self.skipped and self.metrics is None:
			raise ValueError(
				"a validation that did not skip must carry metrics; reporting "
				"'validated' with no measurement is the failure this guards"
			)
		return self


class EnsembleResult(AleaConfig):
	"""The combined probability plus the modalities that produced it."""

	probability: list[float]
	weights: dict[str, float]
	modalities: list[str]
	"""Which components were available. If maintenance is absent its weight is
	zero and it is not in this list, so a consumer can see the ensemble is
	two-modality rather than silently assuming three."""
	brier: float | None = None


class MaintenanceFit(AleaConfig):
	"""A fitted Cox model's summary. Hazard ratios are per covariate."""

	model: str = "coxph"
	n_assets: int = Field(ge=0)
	n_events: int = Field(ge=0)
	features: list[str]
	hazard_ratios: dict[str, float]
	confidence_level: float
	concordance: float | None = None
	notes: str = ""
	inputs_available: dict[str, bool] = Field(default_factory=dict)


__all__ = [
	"DetectionMetrics",
	"EnsembleConfig",
	"EnsembleResult",
	"ForecastMetrics",
	"Fraction",
	"MaintenanceConfig",
	"MaintenanceFit",
	"PredictiveConfig",
	"UnitInterval",
	"ValidationOutcome",
	"ViirsConfig",
	"WeatherConfig",
]
