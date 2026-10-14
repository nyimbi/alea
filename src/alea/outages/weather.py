# SPDX-License-Identifier: MIT
"""Weather-driven outage forecasting.

The specification's ``build_features`` is largely sound. Three defects are
corrected here, and each has a gate in 07-layer4 §10:

1. **Hemisphere.** ``season = (month % 12 + 3) // 3`` is a northern-hemisphere
   DJF/MAM/JJA/SON encoding. December maps to season 1, the same as January —
   right in Nairobi's north, backwards in Johannesburg's south, and Africa
   straddles the equator. The default here is the cyclical month encoding
   ``sin(2*pi*m/12), cos(2*pi*m/12)``, which carries no hemisphere assumption
   and which a tree model can actually use (it cannot extrapolate from a
   wrapped integer). A hemisphere-aware season is available as an explicit,
   latitude-parameterised option.

2. **Temporal leakage.** Every feature derived from the outage target is built
   through :func:`_lagged`, which refuses ``lag < 1``. Without the shift the
   feature contains the hour it predicts and the model reads the answer — the
   single most common way a time-series model reports a 99% AUC that evaporates
   in production. :func:`assert_causal_features` proves it empirically: build
   the features on a truncated frame, and the values on the shared rows must be
   unchanged. A forward-looking window changes them.

3. **Class imbalance.** The specification applies SMOTE **and**
   ``scale_pos_weight=10``, which double-corrects: the effective positive
   weight becomes roughly ten times what either alone gives. This module uses
   ``scale_pos_weight`` alone — SMOTE interpolates between real outages and
   manufactures physically impossible weather-feature combinations — and
   selects the weight by cross-validated PR-AUC. It reports PR-AUC, recall at a
   fixed precision, and the **base rate**. With a 1% positive rate, 99%
   accuracy is what a "no outage" model gets for free, so accuracy alone is
   never returned as a result.

Splitting is by time, never random: a random split trains on the future and
predicts the past, which inflates every metric and cannot be reproduced in
production.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.outages.views import ForecastMetrics, WeatherConfig

logger = get_logger(__name__)

TIME_COLUMN = "timestamp"
ZONE_COLUMN = "grid_zone"
TARGET_COLUMN = "outage"

CYCLICAL_FEATURES = ("month_sin", "month_cos")
"""Cyclical month encoding. Hemisphere-free by construction."""

HEMISPHERE_FEATURES = ("season_sin", "season_cos")
"""Season angle with the southern hemisphere shifted half a cycle. Requires a
latitude column; it is the documented, parameterised alternative to the
cyclical default."""

CALENDAR_FEATURES = ("hour_sin", "hour_cos", "day_of_year_sin", "day_of_year_cos")
LAGGED_FEATURES = ("outage_rate_lag", "outage_count_lag")
WEATHER_FEATURES = (
	"temperature_c",
	"wind_speed_ms",
	"precipitation_mm",
	"relative_humidity",
	"convective_available_potential_energy",
)


class LeakageError(RuntimeError):
	"""A feature at time *t* depends on information at or after *t*."""


# --------------------------------------------------------------------------
# Feature construction
# --------------------------------------------------------------------------


def _lagged(
	frame: pd.DataFrame,
	column: str,
	*,
	lag: int,
	window: int,
	group: str | None,
	statistic: str = "mean",
) -> pd.Series:
	"""A rolling statistic of ``column`` shifted so it never sees the present.

	``lag`` must be at least 1. This is structural rather than a convention: a
	feature that includes the current hour is the leak the whole module exists
	to prevent, and a keyword argument defaulting to ``lag=1`` would be one
	careless edit from ``lag=0``.
	"""
	if lag < 1:
		raise LeakageError(
			f"lag={lag} for {column!r}: a lagged feature must lag by at least one "
			f"step or it contains the value it predicts"
		)
	if statistic not in ("mean", "sum", "max", "min", "std"):
		raise ValueError(f"unknown statistic {statistic!r}")
	grouped = frame.groupby(group, sort=False)[column] if group else frame[column]
	shifted = grouped.shift(lag)

	def _roll(values: pd.Series) -> pd.Series:
		return getattr(values.rolling(window, min_periods=1), statistic)()

	return shifted.groupby(frame[group], sort=False).transform(_roll) if group else _roll(shifted)


def add_month_encoding(
	frame: pd.DataFrame,
	config: WeatherConfig,
	*,
	latitude_column: str | None = "latitude",
	month_column: str = "month",
) -> pd.DataFrame:
	"""Add month/season features according to ``config.month_encoding``.

	``cyclical`` is latitude-independent and is the default.
	``hemisphere`` shifts the seasonal angle by half a cycle south of the
	equator, using the per-row latitude. ``integer`` is the specification's
	formula, kept only so the defect is reproducible and canaried — it is
	documented here as wrong south of the equator rather than silently used.
	"""
	out = frame.copy()
	month = out[month_column].astype(int)
	if config.month_encoding == "cyclical":
		angle = 2 * np.pi * month / 12.0
		out["month_sin"] = np.sin(angle)
		out["month_cos"] = np.cos(angle)
	elif config.month_encoding == "hemisphere":
		if latitude_column not in out.columns:
			raise KeyError(
				f"month_encoding='hemisphere' needs a {latitude_column!r} column; "
				f"the seasonal angle is a function of where the zone is"
			)
		sign = np.sign(out[latitude_column].to_numpy(dtype=float)).astype(int)
		# Shift south of the equator by half a cycle. `sign < 0` is the only
		# branch, so a zone exactly on the equator takes the northern angle:
		# `np.sign(0.0)` is 0, not -1, and the season is not defined there
		# anyway. The caller should use the cyclical default, which is why it is
		# the default.
		shifted = np.where(sign < 0, (month.to_numpy() + 6 - 1) % 12 + 1, month.to_numpy())
		angle = 2 * np.pi * shifted / 12.0
		out["season_sin"] = np.sin(angle)
		out["season_cos"] = np.cos(angle)
	else:
		# The specification's formula. Correct north of the equator only.
		out["season"] = (month % 12 + 3) // 3
	return out


def add_calendar_features(frame: pd.DataFrame, *, time_column: str = TIME_COLUMN) -> pd.DataFrame:
	"""Hour-of-day and day-of-year as cyclical pairs.

	Outages have a diurnal and an annual rhythm; a raw integer hour tells a
	tree model that 23 and 0 are far apart when they are adjacent.
	"""
	out = frame.copy()
	time = pd.to_datetime(out[time_column], utc=True)
	out["hour_sin"] = np.sin(2 * np.pi * time.dt.hour / 24.0)
	out["hour_cos"] = np.cos(2 * np.pi * time.dt.hour / 24.0)
	day = time.dt.dayofyear
	out["day_of_year_sin"] = np.sin(2 * np.pi * day / 365.25)
	out["day_of_year_cos"] = np.cos(2 * np.pi * day / 365.25)
	if "month" not in out.columns:
		out["month"] = time.dt.month
	return out


def build_features(
	frame: pd.DataFrame,
	config: WeatherConfig | None = None,
	*,
	target_column: str = TARGET_COLUMN,
	group_column: str = ZONE_COLUMN,
	time_column: str = TIME_COLUMN,
) -> pd.DataFrame:
	"""Engineer the forecasting features.

	Returns a frame with the features added. Every column derived from
	``target_column`` is lagged by at least one step and named with a ``_lag``
	suffix, so the leak audit can recognise it.

	The frame must be sorted by ``group_column`` then ``time_column``: a
	rolling window over an unsorted frame computes over the wrong rows, and
	that failure is invisible in the output.
	"""
	cfg = config or WeatherConfig()
	if target_column not in frame.columns:
		raise KeyError(f"no target column {target_column!r} in {list(frame.columns)}")
	if time_column not in frame.columns:
		raise KeyError(f"no time column {time_column!r}")
	if not frame[time_column].is_monotonic_increasing:
		frame = frame.sort_values([group_column, time_column]).reset_index(drop=True)

	out = frame.copy()
	out = add_calendar_features(out, time_column=time_column)
	out = add_month_encoding(out, cfg)

	window = cfg.outage_history_window_hours
	out["outage_rate_lag"] = _lagged(
		out, target_column, lag=1, window=window, group=group_column, statistic="mean"
	)
	out["outage_count_lag"] = _lagged(
		out, target_column, lag=1, window=window, group=group_column, statistic="sum"
	)
	out["outage_max_lag"] = _lagged(
		out, target_column, lag=1, window=window, group=group_column, statistic="max"
	)

	logger.info(
		"weather.build_features",
		rows=int(len(out)),
		zones=int(out[group_column].nunique()) if group_column in out else 0,
		encoding=cfg.month_encoding,
		window_hours=window,
	)
	return out


def feature_names(
	frame: pd.DataFrame,
	*,
	exclude: Sequence[str] = (),
	config: WeatherConfig | None = None,
) -> list[str]:
	"""Model inputs: numeric, non-identifier, non-target columns.

	``config.target_derived_columns`` is excluded here rather than at each call
	site, because it is the one exclusion that must not be forgettable. The
	label's own source column (``flagged_fraction``) is numeric, is not named
	``outage``, and is therefore an ordinary-looking feature -- a caller who
	passes only ``exclude=(target_column,)`` gets a model that reads the answer
	and scores 1.0. Making the exclusion structural means a new caller cannot
	reintroduce it by forgetting.
	"""
	cfg = config or WeatherConfig()
	blocked = set(exclude) | set(cfg.target_derived_columns) | {TARGET_COLUMN, TIME_COLUMN, ZONE_COLUMN}
	names: list[str] = []
	for column in frame.columns:
		if column in blocked:
			continue
		if pd.api.types.is_numeric_dtype(frame[column]):
			names.append(column)
	return names


def forward_frame(
	history: pd.DataFrame,
	config: WeatherConfig | None = None,
	*,
	zone_column: str = ZONE_COLUMN,
	time_column: str = TIME_COLUMN,
) -> pd.DataFrame:
	"""The horizon nobody has observed, one row per zone per hour.

	**Why this is a construction and not a reindex.** The model's features are
	calendar plus the *lagged* outage rate, and both are computable ahead of the
	horizon: the calendar from the clock, the lag from the observed history. The
	rows for the next ``horizon_hours`` therefore need no future observation --
	which is the whole reason this forecast can exist, since the only outage
	source is a satellite that runs a day behind.

	The forward instants continue the history's own cadence rather than assuming
	one: VIIRS is daily and the specification's feature set is hourly, and a
	frame built on the wrong step would put the horizon in the past or spread it
	over the wrong span. The step is measured from the last two observations.

	``outage`` is present and NaN, and that is load-bearing rather than untidy:
	:func:`build_features` requires the target column to exist, and the lagged
	features on these rows read the *history's* tail. A NaN there is honest --
	these hours have no outcome yet -- and it is what keeps the same builder
	usable for training and for prediction instead of a second feature path that
	could drift from the first.
	"""
	cfg = config or WeatherConfig()
	missing = {time_column, zone_column} - set(history.columns)
	if missing:
		raise KeyError(f"history has no {sorted(missing)}")
	if history.empty:
		raise ValueError(
			"no outage history; a forecast from no observation is a prior wearing "
			"a model's name"
		)
	observed = pd.to_datetime(history[time_column], utc=True)
	if not observed.is_monotonic_increasing:
		history = history.sort_values([zone_column, time_column]).reset_index(drop=True)
		observed = pd.to_datetime(history[time_column], utc=True)

	# Numpy rather than `.iloc`, so the per-zone read is positional over an array
	# whose dtype is unambiguous. `history[column]` types as a union in the stubs,
	# and a union is exactly where a wrong read hides.
	stamps_all = observed.to_numpy()
	zone_all = history[zone_column].to_numpy()

	zones = sorted(history[zone_column].unique().tolist())
	per_zone: list[pd.Series] = []
	for zone in zones:
		stamps = np.sort(stamps_all[zone_all == zone])
		if len(stamps) < 2:
			raise ValueError(
				f"zone {zone!r} has {len(stamps)} observation(s); a cadence cannot "
				f"be measured from one, and a horizon guessed at the wrong step is "
				f"a forecast of the wrong hours"
			)
		step = pd.Timedelta(stamps[-1] - stamps[-2])
		if step <= pd.Timedelta(0):
			raise ValueError(
				f"zone {zone!r}'s observations are not increasing in time "
				f"(last step {step}); the cadence is undefined"
			)
		per_zone.append(
			pd.Series(pd.date_range(stamps[-1] + step, periods=cfg.horizon_hours, freq=step))
		)

	frame = pd.DataFrame(
		{
			time_column: pd.concat(per_zone, ignore_index=True),
			zone_column: np.repeat(zones, cfg.horizon_hours),
		}
	)
	frame[TARGET_COLUMN] = np.nan
	logger.info(
		"weather.forward_frame",
		zones=len(zones),
		horizon_hours=cfg.horizon_hours,
		step=str(per_zone[0].iloc[1] - per_zone[0].iloc[0]) if cfg.horizon_hours > 1 else "n/a",
	)
	return frame


def residual_band(
	forecaster: Forecaster,
	config: WeatherConfig | None = None,
	*,
	target_column: str = TARGET_COLUMN,
	group_column: str = ZONE_COLUMN,
) -> dict[str, tuple[float, float]]:
	"""A per-zone band, as the model's own held-out error at ``interval_level``.

	**This is a residual band, not a calibrated predictive interval**, and the
	difference is the reason this docstring exists. A calibrated interval is a
	statement that the outcome falls inside the band at the nominal rate, and
	producing one needs a calibration fit -- isotonic regression against held-out
	outcomes, or a quantile model. Neither is here. What is here is the
	``interval_level`` quantile of absolute error on the time-held-out
	validation split, which says: *on the data this model was checked against,
	this share of its errors were no larger than this.*

	Two consequences a reader must not have to infer. The band is **symmetric
	and clipped to [0, 1]**, because a probability has no room above one and a
	clipped bound is a statement about the model rather than about the outcome.
	And it is **not** a coverage guarantee out of sample: a model whose error
	grows on the forward frame will keep printing a band that was measured on
	the past. It is recorded in ``ForecastMetrics.interval_method`` in those
	words so the number travels with its meaning.

	The zones the validation split does not cover get the pooled quantile rather
	than a missing band: a zone with too few held-out rows to measure its own
	error is a zone whose band is uncertain, not absent, and dropping it would
	take the row out of a section that declares an interval for every zone.
	"""
	cfg = config or WeatherConfig()
	features = list(forecaster.features)
	if forecaster.validation is None:
		raise ValueError(
			"this forecaster carries no validation split, so a band cannot be "
			"measured on the data its metrics came from"
		)
	scored = forecaster.validation.dropna(subset=[target_column]).copy()
	if scored.empty:
		raise ValueError(
			"the validation split has no labelled rows; a band measured on nothing "
			"is not a band"
		)
	# `scored` is a fresh frame, so this assignment is not a view on the fitted
	# object's own split -- a band must not mutate the data its metrics came from.
	scored["_error"] = np.abs(
		scored[target_column].to_numpy(dtype=float)
		- forecaster.predict_proba(scored.loc[:, features])
	)
	pooled = float(np.quantile(scored["_error"].to_numpy(dtype=float), cfg.interval_level))
	band: dict[str, tuple[float, float]] = {}
	for zone, rows in scored.groupby(group_column, sort=False):
		width = (
			float(np.quantile(rows["_error"].to_numpy(dtype=float), cfg.interval_level))
			if len(rows) > 1
			else pooled
		)
		band[str(zone)] = (width, width)
	logger.info(
		"weather.residual_band",
		zones=len(band),
		pooled_width=pooled,
		level=cfg.interval_level,
		method=METHOD_INTERVAL_RESIDUAL,
	)
	return band


METHOD_INTERVAL_RESIDUAL = "residual_quantile"
"""``ForecastMetrics.interval_method`` for :func:`residual_band`.

A slug rather than a sentence so a consumer can branch on it, and a constant
rather than a literal at the call site so the writer and the reader name the
same method -- the register's own lesson about a claim spelled twice."""


# --------------------------------------------------------------------------
# Leakage audit
# --------------------------------------------------------------------------


def audit_feature_names(
	features: Sequence[str],
	*,
	target_column: str = TARGET_COLUMN,
	config: WeatherConfig | None = None,
) -> None:
	"""Refuse a feature that is a target-derived column.

	The cheapest half of the leak check: ``outage`` used directly as a feature
	is the defect, and its name says so. It checks the whole declared set and
	not just ``target_column``, because the expensive half -- the empirical
	causality probe -- is blind to ``flagged_fraction``: perturbing the label
	does not change the fraction the label was thresholded from.
	"""
	cfg = config or WeatherConfig()
	offenders = [name for name in features if name in set(cfg.target_derived_columns) | {target_column}]
	if offenders:
		raise LeakageError(
			f"{offenders} are target-derived columns used as features; "
			f"`flagged_fraction` is the fraction the label was thresholded from, "
			f"so a model given it reads the answer rather than forecasting it"
		)


def assert_causal_features(
	builder: Callable[[pd.DataFrame], pd.DataFrame],
	frame: pd.DataFrame,
	features: Sequence[str],
	*,
	target_column: str = TARGET_COLUMN,
	group_column: str = ZONE_COLUMN,
	probes_per_group: int = 3,
	perturb_columns: Sequence[str] | None = None,
) -> None:
	"""Prove every feature at time *t* is a function of strictly earlier values.

	The probe perturbs a source column at one row and rebuilds, then asserts
	that no feature at that row **or any earlier row** changed. Perturbing row
	*c* can legitimately change features only at rows after *c*, because those
	are the rows that read *c* as history. A feature at row ``r <= c`` that
	changes reads the value at *c* — the present (*r == c*) or the future
	(*r < c*).

	Truncating the tail instead would catch only the forward-looking half: a
	contemporaneous leak, the ``shift(0)`` case the plan's gate targets, reads
	its own row and survives any truncation of rows after it. Perturbation
	catches both, which is why it is the probe used here.

	**``perturb_columns`` defaults to the target and must include every column
	the target is derived from.** The probe works by changing an input and
	watching a feature follow; it can only see a leak through a column it
	perturbs. ``flagged_fraction`` is the label's own source — ``outage ==
	(flagged_fraction >= threshold)`` — so a probe that perturbs only ``outage``
	leaves the fraction untouched, every feature reads as causal, and the model
	that consumes the fraction scores 1.0. The caller passes the declared set
	(``WeatherConfig.target_derived_columns``) rather than the label alone,
	which is what closes the class instead of the one instance.

	``probes_per_group`` rows per zone are perturbed, spread through the series
	so a leak confined to part of it is exercised.
	"""
	if probes_per_group < 1:
		raise ValueError(f"probes_per_group must be positive, got {probes_per_group}")
	sources = list(perturb_columns) if perturb_columns else [target_column]
	if target_column not in sources:
		sources.insert(0, target_column)
	missing = [name for name in sources if name not in frame.columns]
	if missing:
		raise KeyError(f"no column {missing} to perturb")
	non_numeric = [
		name for name in sources if not pd.api.types.is_numeric_dtype(frame[name])
	]
	if non_numeric:
		raise LeakageError(
			f"the causality probe perturbs {non_numeric}, which must be numeric; a "
			f"non-numeric column cannot be perturbed"
		)
	full = builder(frame)
	if list(full.columns) != list(builder(frame).columns):
		raise LeakageError("the feature builder is not deterministic in its columns")

	# A sentinel distinct from every observed value, so the perturbation always
	# changes the source and a leak cannot hide behind a coincidental equality.
	values = frame[target_column].to_numpy(dtype=float)
	sentinel = float(np.nanmax(values)) + 1.0
	if not np.isfinite(sentinel):
		raise LeakageError("the target has no finite values to perturb from")

	groups = (
		[frame.index[frame[group_column] == zone].to_numpy() for zone in frame[group_column].unique()]
		if group_column in frame.columns
		else [frame.index.to_numpy()]
	)
	positions = {index: position for position, index in enumerate(frame.index)}
	checked = 0
	for members in groups:
		if len(members) < 3:
			continue
		chosen = np.unique(
			np.linspace(len(members) // 4, len(members) - 2, probes_per_group).astype(int)
		)
		for offset in chosen:
			probe_index = members[int(offset)]
			cut = positions[probe_index]
			for source in sources:
				perturbed = frame.copy()
				perturbed.loc[probe_index, source] = sentinel
				rebuilt = builder(perturbed)
				for name in features:
					if name not in full.columns or name not in rebuilt.columns:
						continue
					before = full[name].to_numpy(dtype=float)[: cut + 1]
					after = rebuilt[name].to_numpy(dtype=float)[: cut + 1]
					both_nan = np.isnan(before) & np.isnan(after)
					close = np.isclose(before, after, rtol=1e-9, atol=1e-9) | both_nan
					if not close.all():
						row = int(np.argmax(~close))
						raise LeakageError(
							f"feature {name!r} at row {row} changes when {source!r} at "
							f"row {cut} is perturbed ({before[row]!r} -> {after[row]!r}): "
							f"it reads information at or after its own timestamp. A "
							f"feature that includes the present hour is the leak this "
							f"module exists to prevent (07-layer4 §3.2)"
						)
			checked += 1
	if checked == 0:
		raise LeakageError(
			"no row was probeable: every group has fewer than three rows, so the "
			"audit proves nothing"
		)


def audit_no_temporal_leakage(
	frame: pd.DataFrame,
	config: WeatherConfig | None = None,
	*,
	target_column: str = TARGET_COLUMN,
	group_column: str = ZONE_COLUMN,
	time_column: str = TIME_COLUMN,
) -> None:
	"""Both halves of the leak check, on a frame that already has features.

	Name check plus the empirical causality check. Raises
	:class:`LeakageError` on either.
	"""
	cfg = config or WeatherConfig()
	features = feature_names(frame, config=cfg)
	audit_feature_names(features, target_column=target_column, config=cfg)

	def builder(part: pd.DataFrame) -> pd.DataFrame:
		return build_features(
			part,
			cfg,
			target_column=target_column,
			group_column=group_column,
			time_column=time_column,
		)

	# Every column the target is derived from, and not the target alone: the
	# label's own source column is the one a probe over `outage` cannot see.
	assert_causal_features(
		builder,
		frame,
		features,
		target_column=target_column,
		group_column=group_column,
		perturb_columns=[
			name for name in cfg.target_derived_columns if name in frame.columns
		],
	)


# --------------------------------------------------------------------------
# Splitting, weighting, metrics
# --------------------------------------------------------------------------


def time_split(
	frame: pd.DataFrame,
	config: WeatherConfig | None = None,
	*,
	time_column: str = TIME_COLUMN,
) -> tuple[pd.DataFrame, pd.DataFrame]:
	"""Split into train and validation by time, never randomly.

	The validation set is the latest ``validation_fraction`` of the timeline,
	so the model is always evaluated on the future relative to its training
	data — the condition it will actually meet in production.
	"""
	cfg = config or WeatherConfig()
	if not frame[time_column].is_monotonic_increasing:
		frame = frame.sort_values(time_column).reset_index(drop=True)
	cut = int(len(frame) * (1.0 - cfg.validation_fraction))
	if cut <= 0 or cut >= len(frame):
		raise ValueError(
			f"a {cfg.validation_fraction} validation fraction leaves no rows on "
			f"one side of a {len(frame)}-row frame"
		)
	train, validation = frame.iloc[:cut], frame.iloc[cut:]
	if train[time_column].max() > validation[time_column].min():
		raise LeakageError("train extends past validation; the split is not by time")
	return train.reset_index(drop=True), validation.reset_index(drop=True)


def _metrics(y_true: NDArray[Any], y_score: NDArray[np.float64]) -> dict[str, float]:
	from sklearn.metrics import (
		average_precision_score,
		brier_score_loss,
		roc_auc_score,
	)

	y = np.asarray(y_true, dtype=int)
	if y.min() == y.max():
		# A single-class validation set has no ranking metric. NaN is the
		# honest answer; 0.5 would read as "no better than chance" when the
		# truth is "not measurable".
		return {"pr_auc": float("nan"), "auc": float("nan"), "brier": float("nan")}
	return {
		"pr_auc": float(average_precision_score(y, y_score)),
		"auc": float(roc_auc_score(y, y_score)),
		"brier": float(brier_score_loss(y, y_score)),
	}


def recall_at_precision(
	y_true: NDArray[Any], y_score: NDArray[np.float64], precision: float
) -> tuple[float, float]:
	"""The recall achievable at or above a target precision.

	Returns ``(recall, achieved_precision)``. The highest-recall threshold whose
	precision is at least ``precision``; ``(0.0, nan)`` when none reaches it,
	which says "this model cannot operate at that precision" rather than
	reporting a flattering number at a lower one.
	"""
	y = np.asarray(y_true, dtype=int)
	order = np.argsort(-np.asarray(y_score, dtype=float))
	y = y[order]
	if y.sum() == 0:
		return 0.0, float("nan")
	tp = np.cumsum(y)
	flagged = np.arange(1, len(y) + 1)
	precisions = tp / flagged
	recalls = tp / y.sum()
	ok = np.nonzero(precisions >= precision)[0]
	if ok.size == 0:
		return 0.0, float("nan")
	best = ok[-1]
	return float(recalls[best]), float(precisions[best])


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------


@dataclass
class Forecaster:
	"""A fitted outage forecaster and the provenance of how it was fitted."""

	model: Any
	features: list[str]
	scale_pos_weight: float
	metrics: ForecastMetrics
	backend: str = ""
	notes: list[str] = field(default_factory=list)
	validation: pd.DataFrame | None = None
	"""The time-held-out split the metrics were measured on, kept on the object.

	Kept here rather than handed to whoever wants a band, because a band
	measured on a *different* split than the metrics is two answers to "how
	wrong is this model" that would be quoted side by side. ``None`` only for a
	forecaster assembled by hand -- :func:`train_forecaster` always sets it."""

	def predict_proba(self, frame: pd.DataFrame) -> NDArray[np.float64]:
		"""Positive-class probability for each row."""
		matrix = frame[self.features].to_numpy(dtype=float)
		if not hasattr(self.model, "predict_proba"):
			raise TypeError(f"{type(self.model).__name__} has no predict_proba")
		return np.asarray(self.model.predict_proba(matrix)[:, 1], dtype=np.float64)


def _make_classifier(
	weight: float,
	*,
	seed: int,
	backend: str,
) -> tuple[Any, str]:
	"""A gradient-boosted classifier with ``scale_pos_weight`` set.

	LightGBM or XGBoost where available — the specification's choice and the
	one that handles the tabular feature set well — falling back to scikit-learn
	so the module is usable in an environment that has neither. SMOTE is
	deliberately absent: combining it with ``scale_pos_weight`` is the
	double-correction the plan forbids.
	"""
	if backend in ("auto", "lightgbm"):
		try:
			from lightgbm import LGBMClassifier

			return (
				LGBMClassifier(
					n_estimators=300,
					learning_rate=0.05,
					num_leaves=31,
					scale_pos_weight=weight,
					random_state=seed,
					n_jobs=-1,
					verbose=-1,
				),
				"lightgbm",
			)
		except ImportError:
			if backend == "lightgbm":
				raise
	if backend in ("auto", "xgboost"):
		try:
			from xgboost import XGBClassifier

			return (
				XGBClassifier(
					n_estimators=300,
					learning_rate=0.05,
					max_depth=5,
					scale_pos_weight=weight,
					random_state=seed,
					n_jobs=-1,
					eval_metric="logloss",
				),
				"xgboost",
			)
		except ImportError:
			if backend == "xgboost":
				raise
	from sklearn.ensemble import HistGradientBoostingClassifier

	# HistGradientBoosting has no scale_pos_weight, so the weight is applied by
	# sample_weight at fit time instead. Same correction, different mechanism.
	return (
		HistGradientBoostingClassifier(
			max_iter=300, learning_rate=0.05, random_state=seed
		),
		"sklearn",
	)


def _fit(
	model: Any,
	backend: str,
	matrix: NDArray[np.float64],
	y: NDArray[Any],
	weight: float,
) -> Any:
	if backend == "sklearn":
		# The fallback reweights by sample_weight, which is scale_pos_weight's
		# effect expressed per row rather than per class.
		sample_weight = np.where(np.asarray(y) == 1, weight, 1.0)
		model.fit(matrix, y, sample_weight=sample_weight)
	else:
		model.fit(matrix, y)
	return model


def train_forecaster(
	frame: pd.DataFrame,
	config: WeatherConfig | None = None,
	*,
	target_column: str = TARGET_COLUMN,
	time_column: str = TIME_COLUMN,
	seed: int = 0,
	backend: str = "auto",
) -> Forecaster:
	"""Fit the outage forecaster and return it with its metrics.

	The metrics carry the base rate, PR-AUC, and recall at the configured
	precision. Accuracy is retained only so the specification's headline can be
	reproduced beside the base rate that explains it.

	**Rows with no outcome are dropped before the split, and the features are
	built before they are dropped.** The two halves are one decision. A zone-hour
	with no clear pixels is *unknown* (``viirs.zone_series``), so its target is
	NaN and it is not a training row -- a classifier handed one raises rather
	than guessing, and a zero substituted for it would teach the model that an
	unobserved hour was calm. But dropping it *before* ``build_features`` would
	shift every later lag in that zone by a step, because the rolling window is
	computed over the rows the frame still has: the feature would silently mean
	"the last n observations" instead of "the last n hours". So the lags are
	built on the full series and the unlabelled rows leave afterwards, carrying
	the history they contributed.
	"""
	cfg = config or WeatherConfig()
	if seed is None:
		raise ValueError(
			"a forecaster needs an explicit seed; an unseeded model is not "
			"reproducible (AD-8)"
		)
	featured = build_features(
		frame, cfg, target_column=target_column, time_column=time_column
	)
	labelled = int(featured[target_column].notna().sum())
	if labelled < len(featured):
		logger.info(
			"weather.train.dropping_unlabelled",
			dropped=int(len(featured) - labelled),
			kept=labelled,
		)
	featured = featured.dropna(subset=[target_column]).reset_index(drop=True)
	if featured.empty:
		raise ValueError(
			f"no row carries a {target_column!r} outcome; a model fitted on no "
			f"labelled observation reports a prior, not a forecast"
		)
	features = feature_names(featured, exclude=(target_column,), config=cfg)
	audit_feature_names(features, target_column=target_column, config=cfg)

	train, validation = time_split(featured, cfg, time_column=time_column)
	base_rate = float(validation[target_column].mean())

	weight = cfg.scale_pos_weight
	chosen: list[str] = []
	if cfg.select_weight_by_cv:
		weight, chosen = _select_weight(
			train, features, target_column, cfg, seed=seed, backend=backend
		)

	model, resolved = _make_classifier(weight, seed=seed, backend=backend)
	matrix = train[features].to_numpy(dtype=float)
	_fit(model, resolved, matrix, train[target_column].to_numpy(), weight)

	scores = _metrics(validation[target_column].to_numpy(), _predict(model, resolved, validation, features))
	recall, achieved = recall_at_precision(
		validation[target_column].to_numpy(),
		_predict(model, resolved, validation, features),
		cfg.recall_at_precision,
	)
	predictions = (
		_predict(model, resolved, validation, features) >= 0.5
	).astype(int)
	accuracy = float((predictions == validation[target_column].to_numpy()).mean())

	metrics = ForecastMetrics(
		pr_auc=scores["pr_auc"],
		auc=scores["auc"],
		base_rate=base_rate,
		recall_at_precision=recall,
		operating_precision=achieved if np.isfinite(achieved) else 0.0,
		brier=scores["brier"],
		scale_pos_weight=weight,
		n_train=int(len(train)),
		n_validation=int(len(validation)),
		positive_rate_train=float(train[target_column].mean()),
		positive_rate_validation=base_rate,
		accuracy=accuracy,
		features=features,
		notes=(
			f"base rate {base_rate:.4f}; accuracy alone is meaningless at this "
			f"rate (07-layer4 §3.3). "
			+ (f"weight chosen by CV from {cfg.scale_pos_weight_candidates}." if chosen else "")
		),
	)
	logger.info(
		"weather.train",
		backend=resolved,
		pr_auc=metrics.pr_auc,
		auc=metrics.auc,
		base_rate=base_rate,
		scale_pos_weight=weight,
		n_train=metrics.n_train,
		n_validation=metrics.n_validation,
	)
	return Forecaster(
		model=model,
		features=features,
		scale_pos_weight=weight,
		metrics=metrics,
		backend=resolved,
		notes=chosen,
		validation=validation,
	)


def _predict(
	model: Any, backend: str, frame: pd.DataFrame, features: Sequence[str]
) -> NDArray[np.float64]:
	matrix = frame[list(features)].to_numpy(dtype=float)
	return np.asarray(model.predict_proba(matrix)[:, 1], dtype=np.float64)


def _select_weight(
	train: pd.DataFrame,
	features: Sequence[str],
	target_column: str,
	cfg: WeatherConfig,
	*,
	seed: int,
	backend: str,
) -> tuple[float, list[str]]:
	"""Choose ``scale_pos_weight`` by cross-validated PR-AUC, by time folds.

	The folds are contiguous time blocks, not a shuffled KFold: a shuffled fold
	trains on the future inside every split. The fold count is capped so a small
	training set still gets at least one usable split.
	"""
	n_folds = min(3, max(2, len(train) // 200))
	edges = np.linspace(0, len(train), n_folds + 1).astype(int)
	notes: list[str] = []
	best_weight = cfg.scale_pos_weight
	best_score = -np.inf
	for weight in cfg.scale_pos_weight_candidates:
		scores: list[float] = []
		for fold in range(n_folds - 1):
			fit_rows = train.iloc[edges[fold] : edges[fold + 1]]
			eval_rows = train.iloc[edges[fold + 1] : edges[fold + 2]]
			if fit_rows[target_column].nunique() < 2 or eval_rows[target_column].nunique() < 2:
				continue
			model, resolved = _make_classifier(weight, seed=seed, backend=backend)
			_fit(
				model,
				resolved,
				fit_rows[list(features)].to_numpy(dtype=float),
				fit_rows[target_column].to_numpy(),
				weight,
			)
			score = _metrics(
				eval_rows[target_column].to_numpy(), _predict(model, resolved, eval_rows, features)
			)["pr_auc"]
			if np.isfinite(score):
				scores.append(score)
		if not scores:
			continue
		mean_score = float(np.mean(scores))
		notes.append(f"weight={weight}: cv_pr_auc={mean_score:.4f} ({len(scores)} folds)")
		if mean_score > best_score:
			best_score, best_weight = mean_score, weight
	if best_score == -np.inf:
		notes.append(
			f"no fold had both classes; falling back to the configured "
			f"scale_pos_weight={cfg.scale_pos_weight}"
		)
		return cfg.scale_pos_weight, notes
	logger.info("weather.select_weight", weight=best_weight, cv_pr_auc=best_score)
	return best_weight, notes


__all__ = [
	"CALENDAR_FEATURES",
	"CYCLICAL_FEATURES",
	"Forecaster",
	"HEMISPHERE_FEATURES",
	"LAGGED_FEATURES",
	"LeakageError",
	"METHOD_INTERVAL_RESIDUAL",
	"TARGET_COLUMN",
	"TIME_COLUMN",
	"WEATHER_FEATURES",
	"ZONE_COLUMN",
	"add_calendar_features",
	"add_month_encoding",
	"assert_causal_features",
	"audit_feature_names",
	"audit_no_temporal_leakage",
	"build_features",
	"feature_names",
	"forward_frame",
	"recall_at_precision",
	"residual_band",
	"time_split",
	"train_forecaster",
]
