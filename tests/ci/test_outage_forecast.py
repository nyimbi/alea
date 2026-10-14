# SPDX-License-Identifier: MIT
"""The outage-forecast producer: the daily cadence's one required section.

`outage_forecast` was the last required section with no producer, and the
register recorded *two* gaps under it rather than one: nothing turned a fitted
`Forecaster` into a probability per zone, and no interval method existed at all.
This module pins both halves, because a producer that writes a probability
column with a zero-width band satisfies the *shape* the section declares while
reporting a certainty nobody measured.

Four things are pinned here, and each exists because the alternative is a
number that looks right:

* the register move -- the slug left `UNPRODUCED` and arrived in `PRODUCERS`
  and `PROJECTED`, with a rule and a dvc stage behind it;
* `zone_history_rows`, which is the reshape the forecaster needed and which
  preserves an unknown zone-hour as NaN rather than crediting it as calm;
* `forward_frame`, which continues the history's *own* cadence rather than
  assuming one, so a daily detector does not get an hourly horizon;
* `residual_band` and the producer's rows, including the leak that made the
  first smoke test report `pr_auc=1.0`.

The leak is the one worth reading: `flagged_fraction` is the column the label
was thresholded *from*, so a model handed it reads the answer, and the
empirical causality probe could not see it because it perturbed only the label.
`test_the_target_source_column_is_not_a_feature` is that defect pinned.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage
from alea.outages.service import predict_to_artefact, zone_history_rows
from alea.outages.views import PredictiveConfig, WeatherConfig
from alea.outages.weather import (
	METHOD_INTERVAL_RESIDUAL,
	LeakageError,
	assert_causal_features,
	audit_feature_names,
	build_features,
	feature_names,
	forward_frame,
	residual_band,
	train_forecaster,
)
from alea.provenance.models import Basis
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED

REPO = Path(__file__).resolve().parents[2]

ZONES = ("zone_0", "zone_1")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _history(
	periods: int = 240,
	*,
	freq: str = "h",
	zones: tuple[str, ...] = ZONES,
	seed: int = 0,
	nan_zone_hour: tuple[str, int] | None = None,
) -> pd.DataFrame:
	"""The detector's wide zone series: one column per zone, a timestamp index.

	The flagged fractions are drawn so both classes are present -- a frame with
	one class refuses to fit, which is its own test -- and the values straddle
	the 0.5 default threshold rather than sitting far from it.
	"""
	rng = np.random.default_rng(seed)
	stamps = pd.date_range("2030-01-01", periods=periods, freq=freq, tz="UTC")
	frame = pd.DataFrame({"timestamp": stamps})
	for zone in zones:
		frame[zone] = np.where(rng.random(periods) > 0.85, 0.8, 0.05)
	if nan_zone_hour is not None:
		zone, row = nan_zone_hour
		frame.loc[row, zone] = np.nan
	return frame


def _config(**weather: object) -> PredictiveConfig:
	return PredictiveConfig(weather=WeatherConfig(**weather))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The register: the slug moved, and both registers moved with it
# --------------------------------------------------------------------------


def test_the_section_left_the_unproduced_register():
	"""The daily cadence's required section now has a producer.

	Pinned as a set rather than a boolean, because "not in `UNPRODUCED`" alone
	is satisfied by a slug that is in neither register -- which is the state a
	half-finished move leaves and which the gates in
	`test_reporting_producers.py` catch only for sections they enumerate.
	"""
	assert "outage_forecast" not in UNPRODUCED, (
		"`outage_forecast` is back in `UNPRODUCED`; the daily cadence's required "
		"section has a producer, so the entry would be a claim about a gap that "
		"no longer exists"
	)
	assert PRODUCERS.get("outage_forecast") == "outages.service._stage_outage_forecast", (
		f"`PRODUCERS` names {PRODUCERS.get('outage_forecast')!r} for "
		f"`outage_forecast`; the producer is the stage in `outages/service.py`"
	)
	assert PROJECTED.get("outage_forecast") == "project_outage_forecast", (
		f"`PROJECTED` names {PROJECTED.get('outage_forecast')!r}; the daily "
		f"projection rule is what lands the section at its dated path"
	)


def test_the_stage_is_reachable_by_name():
	"""The producer is registered, not merely decorated.

	A `@stage`-decorated function is reachable only once its module is imported,
	and the registry's own history is a stage that was "written, decorated and
	unreachable". `build_stage` on an empty frame must get past the name lookup
	and fail on the *data* rather than on `unknown stage`.
	"""
	with pytest.raises(Exception) as caught:
		build_stage("outage_forecast", PredictiveConfig(), Path("/tmp/unused.parquet"))
	assert "unknown stage" not in str(caught.value), (
		"`outage_forecast` is not in the stage registry; the CLI would report "
		"`unknown stage` for a producer the register says exists"
	)


# --------------------------------------------------------------------------
# zone_history_rows: the reshape, and the NaN it must not spend
# --------------------------------------------------------------------------


def test_the_wide_zone_series_becomes_one_row_per_zone_hour():
	long = zone_history_rows(_history(periods=48))
	assert list(long.columns) == ["timestamp", "grid_zone", "flagged_fraction", "outage"], (
		f"the long frame's columns are {list(long.columns)}; the forecaster is "
		f"keyed on `grid_zone` and thresholds `flagged_fraction` into `outage`"
	)
	assert len(long) == 48 * len(ZONES), "every zone-hour must have a row"
	assert long["timestamp"].dt.tz is not None, (
		"the timestamps came back naive; the forward frame is built from them and "
		"a naive series concatenated with an aware one raises on the sort"
	)


def test_an_unknown_zone_hour_stays_unknown_rather_than_calm():
	"""No clear pixels is *no information*, and a zero would be a claim.

	`viirs.zone_series` returns NaN for a zone-hour it could not see, and its
	docstring says a consumer must treat it as no information. `>= threshold` on
	a NaN is False, so the naive thresholding turns "we could not see" into a
	confident "nothing happened" -- and the model then learns from a calm hour
	that was never observed.
	"""
	long = zone_history_rows(_history(periods=24, nan_zone_hour=("zone_0", 5)))
	row = long[(long["grid_zone"] == "zone_0") & (long["timestamp"] == long["timestamp"].iloc[5])]
	assert len(row) == 1
	assert np.isnan(row["flagged_fraction"].iloc[0]), "the fixture did not plant a NaN"
	assert np.isnan(row["outage"].iloc[0]), (
		"a zone-hour with no clear pixels became a numeric target; `>= threshold` "
		"on NaN is False, which is the substitution `zone_series` warns against"
	)


def test_the_threshold_is_the_configured_one():
	"""The target's threshold is a recorded decision, and it is read from config."""
	frame = _history(periods=24)
	frame["zone_0"] = 0.6  # above the 0.5 default, below a 0.7 threshold
	loose = zone_history_rows(frame, _config(zone_flagged_fraction=0.5))
	tight = zone_history_rows(frame, _config(zone_flagged_fraction=0.7))
	at = loose[loose["grid_zone"] == "zone_0"]["outage"].iloc[0]
	assert at == 1.0, "0.6 is at or above the 0.5 default and must be positive"
	at = tight[tight["grid_zone"] == "zone_0"]["outage"].iloc[0]
	assert at == 0.0, (
		"the threshold did not move with the config; `zone_flagged_fraction` is "
		"the recorded modelling decision and a hardcoded 0.5 would hide it"
	)


def test_a_history_with_no_zone_columns_is_refused():
	"""The wrong frame is refused rather than reshaped into something plausible."""
	with pytest.raises(Exception) as caught:
		zone_history_rows(pd.DataFrame({"timestamp": [pd.Timestamp("2030-01-01", tz="UTC")]}))
	assert "zone_" in str(caught.value), (
		f"the refusal does not name what was missing: {caught.value}"
	)


# --------------------------------------------------------------------------
# forward_frame: the cadence is measured, not assumed
# --------------------------------------------------------------------------


def test_the_horizon_continues_the_historys_own_cadence():
	"""A daily detector gets a daily horizon, not an hourly one.

	The specification's feature set is hourly and VIIRS is daily, so a frame
	built on a hardcoded step puts the horizon either in the past or spread over
	the wrong span -- and both look like a plausible forecast.
	"""
	daily = forward_frame(zone_history_rows(_history(periods=10, freq="D")), _config().weather)
	per_zone = daily.groupby("grid_zone").size().unique()
	assert len(per_zone) == 1 and per_zone[0] == WeatherConfig().horizon_hours, (
		f"each zone must get `horizon_hours` rows; got {per_zone}"
	)
	# Per zone, not across the frame: both zones share the same instants, so a
	# diff over the whole frame alternates 0 and the step and its minimum is 0.
	steps = daily.groupby("grid_zone")["timestamp"].apply(
		lambda stamps: stamps.sort_values().diff().dropna().unique()
	)
	for zone, step in steps.items():
		assert list(step) == [pd.Timedelta(days=1)], (
			f"zone {zone}'s forward step is {list(step)} for a daily history; the "
			f"cadence was assumed rather than measured"
		)


def test_the_horizon_starts_after_the_last_observation():
	history = zone_history_rows(_history(periods=10, freq="D"))
	forward = forward_frame(history, _config().weather)
	last = history.groupby("grid_zone")["timestamp"].max()
	for zone, rows in forward.groupby("grid_zone"):
		assert rows["timestamp"].min() > last[zone], (
			f"zone {zone}'s horizon starts at or before its last observation; a "
			f"forward row that is already observed is not a forecast"
		)


def test_the_forward_rows_carry_an_unlabelled_target():
	"""NaN is honest here, and it is what keeps one feature path for both uses.

	`build_features` requires the target column to exist, and the forward rows
	have no outcome yet. A zero would teach the model that the horizon is calm.
	"""
	forward = forward_frame(zone_history_rows(_history(periods=10, freq="D")), _config().weather)
	assert "outage" in forward.columns
	assert forward["outage"].isna().all(), (
		"the forward rows carry a numeric target; these hours have no outcome and "
		"a zero would be a claim about them"
	)


def test_a_zone_with_one_observation_cannot_have_its_cadence_measured():
	"""One point does not define a step, and a guessed step is the wrong hours."""
	frame = _history(periods=4)
	frame = pd.concat([frame, frame.iloc[[0]].assign(timestamp=frame["timestamp"].iloc[-1] + pd.Timedelta(days=1))])
	lone = frame[["timestamp", "zone_0"]].dropna().tail(1)
	with pytest.raises(ValueError) as caught:
		forward_frame(
			pd.DataFrame(
				{
					"timestamp": [lone["timestamp"].iloc[0]],
					"grid_zone": ["zone_0"],
					"outage": [0.0],
				}
			),
			_config().weather,
		)
	assert "cadence" in str(caught.value), (
		f"the refusal does not say the cadence is unmeasurable: {caught.value}"
	)


def test_an_empty_history_is_refused():
	with pytest.raises(ValueError):
		forward_frame(pd.DataFrame({"timestamp": [], "grid_zone": [], "outage": []}), _config().weather)


# --------------------------------------------------------------------------
# residual_band: a measured band, or a refusal
# --------------------------------------------------------------------------


def _fitted(periods: int = 240, **weather: object):
	cfg = _config(**weather)
	history = zone_history_rows(_history(periods=periods))
	return train_forecaster(history, cfg.weather, seed=0), cfg


def test_the_band_needs_a_validation_split_to_be_measured_on():
	"""A band and a calibrated interval print the same two numbers.

	The band is the quantile of absolute error on the split the metrics came
	from. Without that split there is nothing to measure, and a zero-width band
	would render as a certainty.
	"""
	forecaster, cfg = _fitted()
	stripped = forecaster.__class__(
		model=forecaster.model,
		features=forecaster.features,
		scale_pos_weight=forecaster.scale_pos_weight,
		metrics=forecaster.metrics,
		validation=None,
	)
	with pytest.raises(ValueError) as caught:
		residual_band(stripped, cfg.weather)
	assert "validation" in str(caught.value), (
		f"the refusal does not name the missing split: {caught.value}"
	)


def test_the_band_is_the_held_out_error_at_the_configured_level():
	"""The width moves with `interval_level`, and a wider level is a wider band."""
	narrow, cfg = _fitted(interval_level=0.5)
	wide, _ = _fitted(interval_level=0.95)
	narrow_band = residual_band(narrow, cfg.weather)
	wide_band = residual_band(wide, cfg.weather)
	assert set(narrow_band) == set(wide_band), "the two bands must cover the same zones"
	for zone in narrow_band:
		assert wide_band[zone][0] >= narrow_band[zone][0], (
			f"zone {zone}: the 0.95 band ({wide_band[zone][0]}) is narrower than the "
			f"0.5 band ({narrow_band[zone][0]}); the level is not reaching the quantile"
		)


def test_a_zone_the_split_does_not_cover_gets_the_pooled_band():
	"""A zone with too few held-out rows has an uncertain band, not an absent one.

	Dropping it would take the row out of a section that declares an interval
	for every zone, and the section's `Interval` column would then be blank for
	exactly the zone a reader most needs to be cautious about.
	"""
	forecaster, cfg = _fitted()
	validation = forecaster.validation
	assert validation is not None
	# Leave one zone with a single held-out row: below the per-zone measurement
	# floor, so the pooled quantile is what it must get.
	lone = validation[validation["grid_zone"] == "zone_1"].head(1)
	reduced = validation[validation["grid_zone"] == "zone_0"]
	trimmed = forecaster.__class__(
		model=forecaster.model,
		features=forecaster.features,
		scale_pos_weight=forecaster.scale_pos_weight,
		metrics=forecaster.metrics,
		validation=pd.concat([reduced, lone], ignore_index=True),
	)
	band = residual_band(trimmed, cfg.weather)
	assert set(band) == {"zone_0", "zone_1"}, (
		f"the band covers {sorted(band)}; a zone with too few held-out rows must "
		f"fall back to the pooled quantile rather than leave the band absent"
	)
	assert band["zone_1"][0] > 0.0, "the fallback band is zero-width, which reads as certainty"


def test_the_band_does_not_mutate_the_split_it_was_measured_on():
	"""The metrics and the band must come from the same bytes.

	`residual_band` writes an error column into the frame it scores. If that
	frame is the fitted object's own split, the next reader of the validation
	set gets a column nobody documented -- and the object's state now depends on
	whether a band was ever computed from it.
	"""
	forecaster, cfg = _fitted()
	validation = forecaster.validation
	assert validation is not None
	before = list(validation.columns)
	residual_band(forecaster, cfg.weather)
	assert list(forecaster.validation.columns) == before, (
		"`residual_band` added a column to the forecaster's own validation split; "
		"it must score a copy"
	)


def test_the_method_is_named_rather_than_left_to_a_reader():
	"""A residual band is not a calibrated predictive interval, and says so."""
	assert METHOD_INTERVAL_RESIDUAL == "residual_quantile"


# --------------------------------------------------------------------------
# The leak: the label's own source column is not a feature
# --------------------------------------------------------------------------


def test_the_target_source_column_is_not_a_feature():
	"""`flagged_fraction` *is* the answer, thresholded.

	The first smoke test of this producer reported `pr_auc=1.0`, which is not a
	good forecast -- it is a model reading the label. `flagged_fraction` is
	numeric, is not named `outage`, and is therefore an ordinary-looking
	feature, while `outage == (flagged_fraction >= zone_flagged_fraction)`.

	The empirical causality audit could not catch it: the probe perturbs the
	*target* and re-checks the features, and the fraction is invariant to a
	perturbation of the label. So the leak passed every causality probe while
	the score went to 1.0.
	"""
	history = zone_history_rows(_history(periods=120))
	featured = build_features(history, WeatherConfig())
	names = feature_names(featured, config=WeatherConfig())
	assert "flagged_fraction" not in names, (
		"the target's own source column is in the feature set; the model reads "
		"the answer rather than forecasting it, and scores 1.0 for it"
	)
	assert "outage" not in names, "the label itself must not be a feature"


def test_the_declaration_is_what_excludes_it():
	"""The exclusion is structural, not a call-site argument.

	`target_derived_columns` had zero callers before this: a correct statement
	of the rule with nothing applying it. A caller passing only
	``exclude=(target_column,)`` -- which is what the producer did -- must still
	get the fraction excluded, or the next caller reintroduces the leak by
	forgetting.
	"""
	cfg = WeatherConfig(target_derived_columns=("outage",))
	history = zone_history_rows(_history(periods=60))
	featured = build_features(history, cfg)
	assert "flagged_fraction" in feature_names(featured, config=cfg), (
		"narrowing the declaration did not narrow the feature set, so the "
		"declaration is not what the exclusion reads"
	)
	assert "flagged_fraction" not in feature_names(featured, config=WeatherConfig())


def test_the_name_check_refuses_the_label_source_by_name():
	"""A feature *named* `flagged_fraction` is refused, not only one named `outage`.

	The name check is the cheap half and it is scoped to the whole declared set
	rather than the label alone, because the expensive half -- the causality
	probe -- cannot see the fraction. This is the path a caller takes when it
	hands `audit_feature_names` a list it built itself, bypassing
	`feature_names`; the exclusion there is the other half of the same control.
	"""
	with pytest.raises(LeakageError) as caught:
		audit_feature_names(["hour_sin", "flagged_fraction"], target_column="outage")
	assert "flagged_fraction" in str(caught.value), (
		f"the refusal does not name the offending column: {caught.value}"
	)


def test_the_producer_audits_the_features_it_fits_on(tmp_path: Path):
	"""The end-to-end path: whatever the producer fits on has passed the audit.

	`audit_no_temporal_leakage` is only a gate if something calls it on the
	frame the model actually sees. The producer builds its features through
	`feature_names`, and this pins that the fitted feature list is disjoint from
	the declared target-derived set -- which is the property the leak violated.
	"""
	_, _, forecaster = predict_to_artefact(
		_history(periods=120), tmp_path / "outage_forecast.parquet", _config()
	)
	declared = set(WeatherConfig().target_derived_columns)
	assert not declared & set(forecaster.features), (
		f"the fitted model reads {sorted(declared & set(forecaster.features))}, "
		f"which the label is derived from; `pr_auc` would be a statement about "
		f"the model's ability to read, not to forecast"
	)


def test_the_widened_probe_catches_a_leak_through_the_fraction():
	"""The probe sees a source column only if it perturbs it.

	A contemporaneous read of the fraction is invisible to a probe over the
	label, which is the exact blind spot the leak lived in. Both halves are
	asserted, because the *first* is the finding: the label-only probe passes on
	a defect the widened one catches, so the widening is what closes it rather
	than the probe having been adequate all along.
	"""
	history = zone_history_rows(_history(periods=60))

	def leaky(frame: pd.DataFrame) -> pd.DataFrame:
		return frame.assign(ff_now=frame["flagged_fraction"])

	# The blind spot, stated: perturbing the label leaves the fraction alone, so
	# this passes on a feature that reads the present hour.
	assert_causal_features(
		leaky,
		history,
		["ff_now"],
		target_column="outage",
		group_column="grid_zone",
		perturb_columns=["outage"],
	)
	with pytest.raises(LeakageError):
		assert_causal_features(
			leaky,
			history,
			["ff_now"],
			target_column="outage",
			group_column="grid_zone",
			perturb_columns=["outage", "flagged_fraction"],
		)


def test_the_fitted_model_does_not_score_perfectly_on_a_random_target():
	"""The end of the leak: a model that reads the answer scores 1.0.

	The fraction is drawn independently of anything predictive in this fixture,
	so a PR-AUC at or near 1.0 can only come from the model seeing the label's
	own source. The assertion is deliberately loose -- the point is the
	*difference* between reading the answer and not -- and it is stated as a
	ceiling rather than an exact value because the honest score on a random
	target is not reproducible across backends.
	"""
	forecaster, _ = _fitted(periods=240)
	assert forecaster.metrics.pr_auc < 0.95, (
		f"pr_auc is {forecaster.metrics.pr_auc} on a target drawn independently of "
		f"the features; a score that high means the model is reading the answer, "
		f"not forecasting it"
	)


# --------------------------------------------------------------------------
# The producer: the section's own frame, and its provenance
# --------------------------------------------------------------------------


def test_the_producer_writes_the_sections_frame(tmp_path: Path):
	"""One row per zone, in the shape `assemble.values_from_artefact` binds.

	The section declares `["Zone", "Probability", "Interval", "Basis"]`; the
	producer supplies `label`/`value`/`unit` and an interval, and the assembler
	mints the `ReportValue`s that fill the other two columns.
	"""
	_, frame, _ = predict_to_artefact(
		_history(periods=240), tmp_path / "outage_forecast.parquet", _config()
	)
	assert list(frame.columns) == [
		"label",
		"value",
		"unit",
		"interval_low",
		"interval_high",
		"peak_probability",
	], f"the frame's columns are {list(frame.columns)}"
	assert len(frame) == len(ZONES), (
		f"{len(frame)} rows for {len(ZONES)} zones; the section's unit is a zone "
		f"and a per-zone-hour frame would multiply it by the horizon"
	)
	assert set(frame["unit"]) == {"probability"}
	assert frame["value"].between(0.0, 1.0).all(), "a probability left [0, 1]"
	assert (frame["interval_low"] <= frame["value"]).all()
	assert (frame["value"] <= frame["interval_high"]).all(), (
		"a row's interval does not contain its own probability"
	)
	assert (frame["peak_probability"] >= frame["value"]).all(), (
		"the peak over the horizon is below the horizon's mean, which cannot be"
	)


def test_the_producer_records_that_the_band_is_not_calibrated(tmp_path: Path):
	"""The number travels with its meaning, in the artefact and not only in code.

	A band and a calibrated interval print the same two numbers, and the
	difference is whether the stated coverage holds out of sample. A consumer
	reading the parquet has no access to this module's docstrings.
	"""
	path = tmp_path / "outage_forecast.parquet"
	predict_to_artefact(_history(periods=240), path, _config())
	_, provenance = read_artefact(path)
	assert provenance.basis == Basis.FORECAST, (
		f"the section's basis is {provenance.basis}; this is a forecast, and the "
		f"report renders the basis beside the number"
	)
	assert provenance.parameters["interval_method"] == METHOD_INTERVAL_RESIDUAL
	assert provenance.parameters["interval_level"] == WeatherConfig().interval_level
	assert provenance.parameters["zone_flagged_fraction"] == WeatherConfig().zone_flagged_fraction
	assert "NOT a calibrated predictive interval" in provenance.notes, (
		"the provenance does not carry the distinction; a reader of the artefact "
		"would take the band for a coverage guarantee"
	)
	assert "horizon_hours" in provenance.parameters


def test_a_history_with_one_target_class_is_refused(tmp_path: Path):
	"""A classifier cannot be fitted on one class, and the base rate is not a result."""
	calm = _history(periods=120)
	for zone in ZONES:
		calm[zone] = 0.01  # below the threshold, everywhere
	with pytest.raises(Exception) as caught:
		predict_to_artefact(calm, tmp_path / "out.parquet", _config())
	assert "constant" in str(caught.value) or "one class" in str(caught.value), (
		f"the refusal does not say the target is single-class: {caught.value}"
	)


def test_the_horizon_rows_are_the_forward_ones_and_not_a_positional_slice(tmp_path: Path):
	"""`build_features` re-sorts, so a positional slice mixes observed and forward.

	The concatenation of history and horizon is never monotonic in time, so the
	builder sorts by (zone, time) and interleaves the two. A slice taken at
	`len(history)` therefore takes a mixture of observed and unobserved hours
	and calls the result a forecast -- which is what the first version did.
	"""
	history = _history(periods=120)
	_, frame, forecaster = predict_to_artefact(history, tmp_path / "out.parquet", _config())
	long = zone_history_rows(history, _config())
	horizon = _config().weather.horizon_hours
	stacked = build_features(
		pd.concat(
			[long, forward_frame(long, _config().weather)], ignore_index=True
		),
		_config().weather,
	)
	last = long.groupby("grid_zone")["timestamp"].max()
	forward_rows = stacked[stacked["timestamp"] > stacked["grid_zone"].map(last)]
	assert len(forward_rows) == horizon * len(ZONES), (
		f"{len(forward_rows)} forward rows for {len(ZONES)} zones at a "
		f"{horizon}-hour horizon"
	)
	assert len(frame) == len(ZONES)
	assert forecaster.metrics.n_validation > 0, "the metrics carry no held-out rows"


def test_the_stage_writes_an_artefact_a_reader_can_verify(tmp_path: Path):
	"""The checksum is checked on read, so the bytes are the ones written."""
	path = tmp_path / "outage_forecast.parquet"
	predict_to_artefact(_history(periods=240), path, _config())
	payload, _ = read_artefact(path)
	assert len(payload) == len(ZONES)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
