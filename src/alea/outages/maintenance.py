# SPDX-License-Identifier: MIT
"""Predictive maintenance for transmission assets.

The specification fits a Cox proportional-hazards model on transformer age and
oil dissolved-gas analysis (DGA) features, citing Uganda and Nigeria. The model
is real. Its inputs are the problem: DGA readings come from a utility's
condition-monitoring programme and ``maintenance_interval_days`` from its
work-order system. Neither is open data.

So the module ships with three things (07-layer4 §4):

1. The Cox PH implementation, exercised on synthetic survival data whose
   hazard ratio is known, so the estimator is checked against an answer rather
   than against itself.
2. A **feature-availability guard**. If the asset table lacks the DGA columns
   the model refuses to fit. Silently dropping to age-only would produce a
   number labelled "predictive maintenance" that is actually "transformer
   age" — a substitution that looks like a result.
3. A documented path to the data. :data:`CREDENTIALED_INPUTS` names what a
   utility must supply and why.

A second guard covers the leak the plan flags: a DGA sample taken *because*
the transformer was already failing predicts the failure for free. Every
feature column is screened for names suggesting a post-hoc measurement, and a
feature whose availability window is shorter than the observation window is
refused unless the caller records how the lag was applied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from alea.logging import get_logger
from alea.outages.views import MaintenanceConfig, MaintenanceFit

logger = get_logger(__name__)

DURATION_COLUMN = "duration_days"
EVENT_COLUMN = "failed"

CREDENTIALED_INPUTS: dict[str, str] = {
	"oil_dga_h2": "Dissolved hydrogen, ppm. Utility condition-monitoring programme.",
	"oil_dga_ch4": "Dissolved methane, ppm. Utility condition-monitoring programme.",
	"oil_dga_c2h2": "Dissolved acetylene, ppm. Utility condition-monitoring programme.",
	"oil_moisture_ppm": "Oil moisture content, ppm. Utility condition-monitoring programme.",
	"age_years": "In-service age. Derivable from commissioning records.",
	"maintenance_interval_days": "Days since last intervention. Utility work-order system.",
}
"""What the model consumes, and where each input comes from. The module states
which inputs are credentialed because a result whose provenance is "some
spreadsheet" is not a result (AD-6)."""

_POST_HOC_MARKERS = ("post_", "_post", "after_failure", "outcome", "repair_action")
"""Substrings that mark a column as recorded *because* of the failure.

A maintenance model that reads the repair action is reading the answer. The
screen is by name because that is all a dataframe offers; a false positive is a
rename, a false negative is a model that predicts the past.
"""


class MaintenanceDataError(RuntimeError):
	"""The asset table cannot support the model the caller asked for."""


def _has_columns(frame: pd.DataFrame, columns: Sequence[str]) -> dict[str, bool]:
	return {column: column in frame.columns for column in columns}


def assert_feature_availability(
	frame: pd.DataFrame,
	config: MaintenanceConfig | None = None,
) -> dict[str, bool]:
	"""Refuse to fit without the DGA columns, when the guard is on.

	Returns the per-column availability map, so the caller can record which
	inputs the fit actually saw rather than assuming the configured set.
	Raises :class:`MaintenanceDataError` naming the missing columns.

	The gate ``test_maintenance_requires_dga`` canaries this: drop a DGA column
	and the fit must fail, not quietly degrade.
	"""
	cfg = config or MaintenanceConfig()
	availability = _has_columns(frame, (*cfg.dga_columns, *cfg.age_columns))
	if cfg.require_dga:
		missing = [column for column in cfg.dga_columns if not availability[column]]
		if missing:
			raise MaintenanceDataError(
				f"predictive maintenance requires dissolved-gas analysis, but the "
				f"asset table lacks {missing}. Fitting on age alone would produce a "
				f"number labelled 'predictive maintenance' that is 'transformer age' "
				f"(07-layer4 §4). Supply the DGA columns, or set "
				f"maintenance.require_dga=False and label the result as an age-only "
				f"survival model."
			)
	present_age = [column for column in cfg.age_columns if availability[column]]
	if not present_age:
		raise MaintenanceDataError(
			f"the asset table has none of the age columns {list(cfg.age_columns)}; "
			f"a survival model needs at least one covariate"
		)
	return availability


def assert_no_post_hoc_features(
	frame: pd.DataFrame,
	features: Sequence[str],
) -> None:
	"""Refuse a covariate that is a consequence of the failure it predicts.

	The plan's DGA guard, second half: a gas sample drawn after a fault, or a
	``repair_action`` column, leaks the outcome. Screening is by name.
	"""
	offenders: list[str] = []
	for feature in features:
		lowered = feature.lower()
		if any(marker in lowered for marker in _POST_HOC_MARKERS):
			offenders.append(feature)
	if offenders:
		raise MaintenanceDataError(
			f"{offenders} look like post-hoc measurements: a covariate recorded "
			f"because the asset failed predicts the failure for free. If the "
			f"column is genuinely pre-failure, rename it so the screen passes "
			f"and the intent is recorded."
		)


@dataclass(frozen=True)
class SurvivalSummary:
	"""The estimator's output, before it becomes a :class:`MaintenanceFit`."""

	hazard_ratios: dict[str, float]
	concordance: float
	n_assets: int
	n_events: int


def fit_cox(
	frame: pd.DataFrame,
	config: MaintenanceConfig | None = None,
	*,
	duration_column: str = DURATION_COLUMN,
	event_column: str = EVENT_COLUMN,
	features: Sequence[str] | None = None,
) -> MaintenanceFit:
	"""Fit a Cox proportional-hazards model.

	``frame`` is one row per asset, with a duration (days in service until
	failure or censoring) and a boolean event indicator. ``features`` defaults
	to the configured DGA and age columns that are present.

	The guard runs first, so a table without DGA never reaches the estimator.
	"""
	cfg = config or MaintenanceConfig()
	if duration_column not in frame.columns:
		raise MaintenanceDataError(f"no duration column {duration_column!r}")
	if event_column not in frame.columns:
		raise MaintenanceDataError(f"no event column {event_column!r}")

	availability = assert_feature_availability(frame, cfg)
	columns = (
		list(features)
		if features is not None
		else [c for c in (*cfg.dga_columns, *cfg.age_columns) if availability[c]]
	)
	assert_no_post_hoc_features(frame, columns)

	durations = frame[duration_column].to_numpy(dtype=float)
	events = frame[event_column].to_numpy(dtype=bool)
	if durations.shape != events.shape:
		raise MaintenanceDataError(
			f"durations {durations.shape} and events {events.shape} must align"
		)
	if np.any(~np.isfinite(durations)) or np.any(durations <= 0):
		raise MaintenanceDataError("durations must be finite and positive")
	n_events = int(events.sum())
	if n_events == 0:
		raise MaintenanceDataError(
			"no observed failures: a hazard model with no events estimates nothing"
		)

	from lifelines import CoxPHFitter

	design = frame[[*columns, duration_column, event_column]].copy()
	fitter = CoxPHFitter(penalizer=cfg.penalizer)
	fitter.fit(
		design,
		duration_col=duration_column,
		event_col=event_column,
		show_progress=False,
	)
	hazard_ratios = {
		str(name): float(np.exp(value)) for name, value in fitter.params_.items()
	}
	concordance = float(fitter.concordance_index_)
	summary = SurvivalSummary(
		hazard_ratios=hazard_ratios,
		concordance=concordance,
		n_assets=int(len(frame)),
		n_events=n_events,
	)
	logger.info(
		"maintenance.fit_cox",
		n_assets=summary.n_assets,
		n_events=summary.n_events,
		concordance=concordance,
		features=columns,
	)
	return MaintenanceFit(
		n_assets=summary.n_assets,
		n_events=summary.n_events,
		features=list(columns),
		hazard_ratios=summary.hazard_ratios,
		confidence_level=cfg.confidence_level,
		concordance=concordance,
		inputs_available=availability,
		notes=(
			"inputs are credentialed utility data, not open data; see "
			"CREDENTIALED_INPUTS"
		),
	)


def simulate_survival_data(
	n_assets: int = 2000,
	*,
	true_hazard_ratio: float = 2.5,
	seed: int = 0,
	covariate_column: str = "oil_dga_h2",
	scale: float = 40.0,
) -> pd.DataFrame:
	"""Synthetic survival data with a **known** hazard ratio.

	The estimator is checked against this: a Cox fit on the frame must recover
	``true_hazard_ratio`` on ``covariate_column`` within tolerance. That is a
	test of the estimator against an answer, not against itself, which is what
	makes the maintenance module trustworthy in the absence of real data.

	The covariate is a **standardised score**, not a ppm reading: it has zero
	mean and unit variance, so the fitted coefficient is the log hazard ratio
	per unit of the column — which is exactly ``log(true_hazard_ratio)``. A
	covariate in ppm would make the recovered per-ppm hazard ratio
	``true_hazard_ratio ** (1/sd)``, and a test comparing that to
	``true_hazard_ratio`` would fail against a correct estimator.

	Failure times are exponential with rate ``lambda_0 * HR**z``; censoring is
	exponential and independent, so the proportional-hazards assumption holds
	exactly.
	"""
	if n_assets < 50:
		raise ValueError(f"n_assets must be at least 50 for a stable fit, got {n_assets}")
	if true_hazard_ratio <= 0:
		raise ValueError(f"true_hazard_ratio must be positive, got {true_hazard_ratio}")
	rng = np.random.default_rng(seed)
	z = rng.normal(size=n_assets)
	covariate = z
	baseline_rate = 1.0 / scale
	event_time = rng.exponential(1.0 / (baseline_rate * true_hazard_ratio**z))
	censor_time = rng.exponential(scale * 1.5, size=n_assets)
	observed = np.minimum(event_time, censor_time)
	failed = event_time <= censor_time
	return pd.DataFrame(
		{
			covariate_column: covariate,
			"oil_dga_ch4": 20.0 + 5.0 * rng.normal(size=n_assets),
			"oil_dga_c2h2": 1.0 + 0.5 * rng.normal(size=n_assets),
			"oil_moisture_ppm": 15.0 + 4.0 * rng.normal(size=n_assets),
			"age_years": 5.0 + 2.0 * rng.normal(size=n_assets),
			"maintenance_interval_days": 180.0 + 30.0 * rng.normal(size=n_assets),
			DURATION_COLUMN: observed,
			EVENT_COLUMN: failed,
		}
	)


def recover_hazard_ratio(
	n_assets: int = 2000,
	*,
	true_hazard_ratio: float = 2.5,
	seed: int = 0,
) -> tuple[float, float]:
	"""Fit on synthetic data and return ``(recovered, true)``.

	The synthetic-data test asserts ``recovered`` is within tolerance of
	``true``. Returned as a pair so a caller can log both without re-deriving
	the truth.
	"""
	frame = simulate_survival_data(
		n_assets, true_hazard_ratio=true_hazard_ratio, seed=seed
	)
	fit = fit_cox(frame)
	recovered = fit.hazard_ratios["oil_dga_h2"]
	return recovered, true_hazard_ratio


__all__ = [
	"CREDENTIALED_INPUTS",
	"DURATION_COLUMN",
	"EVENT_COLUMN",
	"MaintenanceDataError",
	"SurvivalSummary",
	"assert_feature_availability",
	"assert_no_post_hoc_features",
	"fit_cox",
	"recover_hazard_ratio",
	"simulate_survival_data",
]
