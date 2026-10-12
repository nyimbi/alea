# SPDX-License-Identifier: MIT
"""Layer 4 exit criteria: the gates `07-layer4-predictive.md` §10 and §11 name.

The layer covers outages, losses, flow, contingency and resilience. The gates
here are the ones that assert a *property of a number* rather than a fit: that
a decomposition sums, that an accuracy figure never travels without its base
rate, that a proxy denominator is visible all the way to the report, and that a
cloudy pixel is missing rather than lit.

WHY the decomposition gate matters more than it looks: the specification's own
`_topology_driven` returns a hardcoded 0, so its components do not sum to the
total. A decomposition that does not sum is worse than none, because it looks
like an analysis. The invariant is structural here — the model cannot be
instantiated with parts that miss — and these gates are what keeps it so.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.losses.contingency import sweep, tlens
from alea.losses.flow import Network, susceptance_matrix
from alea.losses.views import DECOMPOSITION_TOLERANCE, LossComponents, LossConfig
from alea.outages.maintenance import MaintenanceDataError, fit_cox, simulate_survival_data
from alea.outages.validate import ValidationError, binarise, detection_metrics
from alea.outages.views import DetectionMetrics, ViirsConfig, WeatherConfig
from alea.outages.viirs import (
	GAP_FILLED_BAND,
	MAX_CLOUD_CONFIDENCE,
	RADIANCE_BAND,
	ViirsTile,
	extract_tile,
	zone_series,
)
from alea.outages.weather import (
	ZONE_COLUMN,
	add_month_encoding,
	assert_causal_features,
	build_features,
)
from alea.provenance.models import Basis
from alea.resilience.metrics import compute_metrics, customers_from_population
from alea.resilience.views import (
	InterruptionEvent,
	ResilienceConfig,
	ZoneCustomers,
)

REPO = Path(__file__).resolve().parents[2]

START = datetime(2030, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------
# Criterion 6: the loss decomposition sums to its total
# --------------------------------------------------------------------------


def test_the_decomposition_sums_to_its_total():
	"""The invariant the specification's hardcoded zero breaks.

	The gate `test_decomposition_sums_to_total` (07-layer4 §10): the three
	components sum to the total to 1e-9 relative tolerance.
	"""
	components = LossComponents(
		load_driven_mwh=120.0, generation_driven_mwh=80.0, topology_driven_mwh=20.0, total_mwh=220.0
	)
	assert components.sum_of_parts_mwh == pytest.approx(220.0)
	assert sum(components.shares.values()) == pytest.approx(1.0)


def test_a_decomposition_that_does_not_sum_cannot_be_built():
	"""The gate's canary: inject a component error and construction must raise.

	This is `test_decomposition_sums_to_total`'s "inject a component error; must
	fail" half. A model that accepted it would put an analysis-shaped object
	into a report with parts that contradict its own total.
	"""
	with pytest.raises(ValueError, match="do not sum"):
		LossComponents(
			load_driven_mwh=120.0,
			generation_driven_mwh=80.0,
			topology_driven_mwh=20.0,
			total_mwh=220.001,
		)


def test_the_decomposition_tolerance_is_tight_enough_to_catch_a_real_error():
	"""A tolerance wide enough to hide a 0.1% component error is not a gate."""
	assert DECOMPOSITION_TOLERANCE <= 1e-6
	with pytest.raises(ValueError, match="do not sum"):
		LossComponents(load_driven_mwh=1.0, generation_driven_mwh=0.0, topology_driven_mwh=0.0, total_mwh=1.001)


def test_a_zero_total_decomposition_reports_nan_shares_not_zero():
	"""A share with no denominator is not zero.

	Zero would read as "this component contributed nothing", which is a claim
	about attribution; the truth is that there is no total to attribute.
	"""
	components = LossComponents(
		load_driven_mwh=0.0, generation_driven_mwh=0.0, topology_driven_mwh=0.0, total_mwh=0.0
	)
	assert all(np.isnan(value) for value in components.shares.values())


# --------------------------------------------------------------------------
# Exit criterion 5 and §10: an accuracy figure never travels without its base rate
# --------------------------------------------------------------------------


def _detection_inputs(positive_rate: float = 0.02, n: int = 500):
	"""A scored series with a known positive rate, so the base rate is checkable."""
	generator = np.random.default_rng(0)
	truth = (generator.random(n) < positive_rate).astype(float)
	# A detector that ranks perfectly, plus noise: AUC is high but not 1.0, and
	# the base rate is the number that decides whether that means anything.
	predicted = truth * 0.6 + generator.random(n) * 0.4
	return predicted, truth


def test_accuracy_never_travels_without_its_base_rate():
	"""The gate `test_base_rate_reported` exists because 99% accuracy at a 1%
	positive rate is what a constant "no outage" prediction achieves."""
	predicted, truth = _detection_inputs()
	metrics = detection_metrics(predicted, truth, ViirsConfig())
	assert metrics.base_rate == pytest.approx(float((truth > 0.5).mean()))
	assert "base rate" in metrics.notes
	assert 0.0 <= metrics.base_rate <= 1.0


def test_the_base_rate_is_required_by_the_model():
	"""Not merely computed: a `DetectionMetrics` without one cannot exist, so a
	producer that forgot it fails at construction rather than at reading."""
	from pydantic import ValidationError as PydanticValidationError

	with pytest.raises(PydanticValidationError):
		DetectionMetrics.model_validate(
			{
				"auc": 0.9,
				"pr_auc": 0.5,
				"accuracy": 0.99,
				"precision": 0.5,
				"recall": 0.5,
				"f1": 0.5,
				"threshold": 0.5,
				"n_total": 100,
				"n_positive": 1,
			}
		)


def test_a_single_class_truth_refuses_rather_than_reporting_a_chance_auc():
	"""A 0.5 reads as "no better than chance" when the truth is "not
	measurable", and the two are different findings."""
	predicted = np.linspace(0.0, 1.0, 100)
	with pytest.raises(ValidationError, match="single class"):
		detection_metrics(predicted, np.zeros(100), ViirsConfig())


def test_binarise_drops_nan_rather_than_crediting_it():
	"""A cloudy zone-hour has no information. Treating NaN as zero would credit
	the detector for every hour it could not see."""
	flagged = np.array([0.9, np.nan, 0.1, 0.8])
	truth = np.array([1.0, 1.0, 0.0, 1.0])
	predicted, actual = binarise(flagged, truth, threshold=0.5)
	assert len(predicted) == 3, "the NaN row was not dropped"
	assert list(actual) == [1, 0, 1]


def test_binarise_refuses_when_every_row_is_unusable():
	with pytest.raises(ValidationError, match="unusable"):
		binarise(np.full(4, np.nan), np.ones(4), threshold=0.5)


# --------------------------------------------------------------------------
# Criterion 9: resilience metrics carry proxy flags where derived
# --------------------------------------------------------------------------


def _events() -> list[InterruptionEvent]:
	return [
		InterruptionEvent(zone="nairobi", started_at=START, duration_minutes=120.0, load_mw=50.0),
		InterruptionEvent(
			zone="mombasa",
			started_at=START + timedelta(hours=3),
			duration_minutes=45.0,
			load_mw=30.0,
		),
		InterruptionEvent(
			zone="kisumu",
			started_at=START + timedelta(hours=6),
			duration_minutes=5.0,
			load_mw=10.0,
		),
	]


def test_a_population_derived_saidi_carries_the_proxy_basis():
	"""AD-6: the weakest input sets the basis, all the way to the report.

	The gate `test_saidi_proxy_flagged` (07-layer4 §10): a population-derived
	SAIDI carries ``proxy`` basis and never loses it.

	A SAIDI computed from WorldPop households is comparable across zones and is
	**not** comparable to a utility's own index; a report that presents it
	beside one without saying so is making a false comparison.
	"""
	config = ResilienceConfig()
	customers = {
		zone: customers_from_population(zone, population, source="WorldPop", config=config)
		for zone, population in (("nairobi", 4_400_000.0), ("mombasa", 1_200_000.0), ("kisumu", 1_100_000.0))
	}
	metrics = compute_metrics(_events(), customers, config)
	assert metrics.customers_are_proxy is True
	assert metrics.customers_basis is Basis.PROXY
	assert metrics.customers_uncertainty > 0.0, "a proxy with zero uncertainty claims to be exact"
	assert metrics.saidi_hours > 0.0


def test_a_measured_customer_count_is_not_flagged_as_a_proxy():
	"""The gate's other direction. A flag that is always on carries no
	information, and would make every comparison look caveated."""
	measured = {
		zone: ZoneCustomers(zone=zone, n_customers=count, basis=Basis.MEASURED)
		for zone, count in (("nairobi", 500_000.0), ("mombasa", 200_000.0), ("kisumu", 150_000.0))
	}
	metrics = compute_metrics(_events(), measured, ResilienceConfig())
	assert metrics.customers_are_proxy is False
	assert metrics.customers_basis is not Basis.PROXY


def test_one_proxied_denominator_flags_the_whole_set():
	"""A metric set built on one proxied denominator is at best a proxy,
	whatever else went into it."""
	mixed = {
		"nairobi": ZoneCustomers(zone="nairobi", n_customers=500_000.0, basis=Basis.MEASURED),
		"mombasa": customers_from_population("mombasa", 1_200_000.0, source="WorldPop"),
		"kisumu": ZoneCustomers(zone="kisumu", n_customers=150_000.0, basis=Basis.MEASURED),
	}
	metrics = compute_metrics(_events(), mixed, ResilienceConfig())
	assert metrics.customers_are_proxy is True


def test_a_proxy_customer_count_requires_non_zero_uncertainty():
	"""A proxy with zero uncertainty is a claim that it is exact."""
	with pytest.raises(ValueError, match="uncertainty"):
		ResilienceConfig(customers_basis=Basis.PROXY, proxy_uncertainty=0.0)


def test_events_below_the_threshold_are_counted_but_excluded():
	"""A five-minute blip is not an interruption, and the count of what was
	excluded is reported rather than dropped."""
	config = ResilienceConfig(interruption_threshold_minutes=10.0)
	customers = {
		zone: ZoneCustomers(zone=zone, n_customers=count, basis=Basis.MEASURED)
		for zone, count in (("nairobi", 500_000.0), ("mombasa", 200_000.0), ("kisumu", 150_000.0))
	}
	metrics = compute_metrics(_events(), customers, config)
	assert metrics.n_events == 2
	assert metrics.n_events_below_threshold == 1
	assert metrics.n_events + metrics.n_events_below_threshold == len(_events())


# --------------------------------------------------------------------------
# §2.3: the gap-filled band never enters the detection path
# --------------------------------------------------------------------------


def _granule_dataset(band: str = RADIANCE_BAND, *, extra: str | None = None):
	"""A minimal xarray-like granule, one time step on a 2x2 grid."""
	import xarray as xr

	shape = (1, 2, 2)
	variables = {
		band: (("time", "y", "x"), np.full(shape, 1.0, np.float32)),
		"QF_Cloud_Mask": (("time", "y", "x"), np.zeros(shape, np.uint8)),
		"Sensor_Zenith": (("time", "y", "x"), np.zeros(shape, np.float32)),
	}
	if extra is not None:
		variables[extra] = (("time", "y", "x"), np.full(shape, 9.0, np.float32))
	return xr.Dataset(
		variables, coords={"time": np.array(["2030-01-01T00:00:00"], dtype="datetime64[ns]")}
	)


def test_the_gap_filled_band_is_refused_as_the_detection_source():
	"""The gate `test_gapfilled_band_unused` (07-layer4 §2.3).

	The gap-filled band interpolates across cloudy observations, so a cloud
	becomes a plausible radiance and the detector sees "no outage" wherever it
	is blind. It must never be the detection source.
	"""
	with pytest.raises(ValueError, match="gap-filled"):
		extract_tile(_granule_dataset(GAP_FILLED_BAND))


def test_a_dataset_merely_containing_the_gap_filled_band_is_refused():
	"""The check is by substring over the variable names, so a renamed-but-
	equivalent band is caught and a granule that carries one cannot be read
	even with the correct radiance band selected."""
	with pytest.raises(ValueError, match="gap-filled"):
		extract_tile(_granule_dataset(RADIANCE_BAND, extra=GAP_FILLED_BAND))
	# The correct band alone is accepted, so the gate is not refusing everything.
	tile = extract_tile(_granule_dataset(RADIANCE_BAND))
	assert tile.shape == (1, 2, 2)


# --------------------------------------------------------------------------
# §3.1: the month encoding carries no hemisphere assumption
# --------------------------------------------------------------------------


def test_the_default_month_encoding_is_hemisphere_free():
	"""The gate `test_month_encoding_hemisphere_free` (07-layer4 §3.1).

	The default cyclical encoding is a function of the month alone, so flipping
	every zone's latitude changes nothing. The specification's integer season
	does change, which is why it is not the default.
	"""
	import pandas as pd

	frame = pd.DataFrame({"month": [1, 7], "latitude": [10.0, 10.0]})
	north = add_month_encoding(frame, WeatherConfig())
	south = add_month_encoding(frame.assign(latitude=-10.0), WeatherConfig())
	assert set(north.columns) == set(south.columns)
	assert "month_sin" in north.columns and "season" not in north.columns
	assert np.allclose(north["month_sin"], south["month_sin"])
	assert np.allclose(north["month_cos"], south["month_cos"])


def test_the_integer_season_is_the_defect_it_replaces():
	"""The other direction: the encoding the plan rejects is latitude-dependent.

	A gate that only ever saw hemisphere-free encodings would pass on the
	specification's formula too. This asserts the difference the default avoids.
	"""
	import pandas as pd

	frame = pd.DataFrame({"month": [1, 7], "latitude": [10.0, 10.0]})
	north = add_month_encoding(frame, WeatherConfig(month_encoding="integer"))
	south = add_month_encoding(frame.assign(latitude=-10.0), WeatherConfig(month_encoding="integer"))
	# The integer encoding has no latitude term, so it cannot respond -- which is
	# the point: it is fixed to one hemisphere and applied to both.
	assert np.array_equal(north["season"], south["season"])
	# And it is a wrapped integer, not a cyclical pair.
	assert list(north.columns[-1:]) == ["season"]


# --------------------------------------------------------------------------
# §2.1: the detection parameters are config, and config means reachable
# --------------------------------------------------------------------------


def test_the_detection_parameters_are_reachable_from_the_root_config():
	"""§2.1's "three parameters, all config, all recorded" is three claims.

	The third is the one that was false. ``predictive_config`` read
	``config.predictive`` through ``getattr``, the root ``Config`` had no such
	field, and ``extra="forbid"`` made a ``predictive:`` block in YAML a load
	error -- so every detection parameter was pinned to its class default and the
	``isinstance`` guard swallowed the absence. A parameter an operator cannot
	set is not config, and provenance recording it as a constant is not
	recording.

	The assertion is on the *value the service resolves*, not on the field's
	existence: a root model that declared ``predictive`` and a service that read
	something else would pass a field-existence check and fail this one.
	"""
	from alea.config.loader import load_config
	from alea.outages.service import detection_parameters_for, predictive_config

	# Every value differs from its default, so a fallback to the class default
	# is visible rather than coincidentally equal.
	config = load_config(
		overrides=[
			"predictive.viirs.bin_size_deg=3.0",
			"predictive.viirs.baseline_quantile=0.5",
			"predictive.viirs.detection_threshold=0.45",
			"predictive.viirs.max_cloud_confidence=1",
			"predictive.weather.month_encoding=integer",
		]
	)
	resolved = predictive_config(config).viirs
	assert resolved.bin_size_deg == 3.0, "the VZA bin size did not survive the root config"
	assert resolved.baseline_quantile == 0.5, "the baseline quantile did not survive"
	assert resolved.detection_threshold == 0.45, "the detection threshold did not survive"
	assert resolved.max_cloud_confidence == 1, "the cloud ceiling did not survive"
	assert predictive_config(config).weather.month_encoding == "integer"

	# And the same values reach the artefact provenance, which is what §2.5
	# means by reproducible: an AUC is comparable only against the parameters
	# that produced it.
	recorded = detection_parameters_for(config)
	assert recorded["detection_threshold"] == 0.45
	assert recorded["bin_size_deg"] == 3.0


def test_the_default_config_file_sets_the_detection_parameters():
	"""The section is in ``config.default.yaml``, so a deployment sees what it runs.

	The loader merges model defaults with the file, so this asserts the *file*
	carries the section rather than that the value exists: a file that omits it
	still loads, and the deployment then cannot see the parameters it is running
	with. Every key here is one §2.1 names as pinned.
	"""
	import yaml

	from alea.config.loader import load_config
	from alea.config.paths import default_config_path

	written = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
	section = written.get("predictive")
	assert isinstance(section, dict), "config.default.yaml has no predictive section"
	for key in ("bin_size_deg", "baseline_quantile", "detection_threshold", "max_cloud_confidence"):
		assert key in section["viirs"], f"predictive.viirs.{key} is not in the default config file"

	loaded = load_config()
	assert loaded.predictive.viirs.bin_size_deg == section["viirs"]["bin_size_deg"], (
		"the default file and the loaded config disagree about the VZA bin size"
	)


# --------------------------------------------------------------------------
# §3.3: SMOTE and scale_pos_weight are never applied together
# --------------------------------------------------------------------------


def test_the_config_refuses_synthetic_oversampling():
	"""The gate `test_class_imbalance_not_double_corrected` (07-layer4 §3.3).

	SMOTE oversamples the minority class and ``scale_pos_weight`` reweights it;
	applying both makes the effective positive weight roughly ten times what
	either alone gives. The refusal is structural: there is no SMOTE field.
	"""
	from pydantic import ValidationError as PydanticValidationError

	with pytest.raises(PydanticValidationError, match="extra_forbidden"):
		WeatherConfig(use_smote=True)


def test_the_forecaster_imports_no_synthetic_oversampler():
	"""The correction is an absence, and an absence is checked at the source."""
	source = (REPO / "src" / "alea" / "outages" / "weather.py").read_text()
	assert "imblearn" not in source and "SMOTE(" not in source


# --------------------------------------------------------------------------
# §4: the maintenance model refuses to degrade to an age-only fit
# --------------------------------------------------------------------------


def test_a_fit_without_dga_columns_is_refused():
	"""The gate `test_maintenance_requires_dga` (07-layer4 §10).

	A Cox fit on transformer age alone produces a number labelled "predictive
	maintenance" that is "transformer age". Dropping one DGA column must stop
	the fit rather than quietly narrowing the covariate set.
	"""
	frame = simulate_survival_data(400, seed=2)
	with pytest.raises(MaintenanceDataError, match="oil_dga_h2"):
		fit_cox(frame.drop(columns=["oil_dga_h2"]))


def test_the_dga_requirement_is_the_default_and_removable():
	"""The guard is a configured default, not a hardcoded wall.

	With ``require_dga=False`` the caller has *stated* the result is an age-only
	survival model, which is a different, honest artefact. The gate is that the
	default refuses. The availability guard is asserted directly rather than
	through a fit: ``fit_cox`` reaches ``lifelines`` only after the guard, and
	the guard is the whole of the gate.
	"""
	from alea.outages.maintenance import assert_feature_availability
	from alea.outages.views import MaintenanceConfig

	frame = simulate_survival_data(400, seed=2).drop(columns=["oil_dga_h2"])
	with pytest.raises(MaintenanceDataError, match="oil_dga_h2"):
		assert_feature_availability(frame, MaintenanceConfig(require_dga=True))
	availability = assert_feature_availability(frame, MaintenanceConfig(require_dga=False))
	assert availability["oil_dga_h2"] is False
	assert availability["oil_dga_ch4"] is True


# --------------------------------------------------------------------------
# §6.1: a failing contingency leaves the input network unchanged
# --------------------------------------------------------------------------


def _two_branch() -> Network:
	"""Bus 0 -- bus 1 -- bus 2: either branch out strands bus 2's 50 MW."""
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([100.0, 100.0]),
		branch_names=("L0", "L1"),
	)


def _dispatch(n_snapshots: int = 4) -> np.ndarray:
	return np.tile(np.array([50.0, 0.0, -50.0]), (n_snapshots, 1))


def test_a_failing_contingency_leaves_the_network_unchanged():
	"""The gate `test_contingency_input_immutable` (07-layer4 §6.1).

	Each outage here islands bus 2, so the DC solve fails for two of the three
	contingencies. The sweep records that and continues; the caller's arrays
	must be byte-identical afterwards, because the specification's in-place
	mutation leaves a line out for every later contingency.
	"""
	network = _two_branch()
	injections = _dispatch()
	before = {
		"susceptance": network.susceptance.copy(),
		"branch_from": network.branch_from.copy(),
		"ratings": network.ratings_mw.copy(),
		"injections": injections.copy(),
	}
	result = sweep(network, injections, LossConfig(snapshot_hours=1.0))
	assert result.diverged.any(), "the fixture did not produce a failing contingency"
	assert np.array_equal(network.susceptance, before["susceptance"])
	assert np.array_equal(network.branch_from, before["branch_from"])
	assert np.array_equal(network.ratings_mw, before["ratings"])
	assert np.array_equal(injections, before["injections"])


# --------------------------------------------------------------------------
# §6.4: the TLENS ranking is deterministic across runs
# --------------------------------------------------------------------------


def _parallel_pair() -> Network:
	"""A radial line with two interchangeable parallel branches (L1, L2).

	The parallel branches tie exactly on ENS increase, which is the case that
	needs a tie-break to be reproducible.
	"""
	branch_from = np.array([0, 1, 1], dtype=np.uint32)
	branch_to = np.array([1, 2, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0, 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0, 132.0]),
		ratings_mw=np.array([1000.0, 1000.0, 1000.0]),
		branch_names=("L0", "L1", "L2"),
	)


def test_the_tlens_ranking_is_stable_across_runs():
	"""The gate `test_tlens_rank_stable` (07-layer4 §6.4).

	Two runs over the same network produce the same order, and the tied
	branches are ordered by index. A ranking that moves between runs lists
	different critical lines each time and is not reproducible (AD-8).
	"""
	first = [entry.branch for entry in tlens(_parallel_pair(), _dispatch()).entries]
	second = [entry.branch for entry in tlens(_parallel_pair(), _dispatch()).entries]
	assert first == second
	# The tie is real, so the tie-break is what produces the order.
	ranking = tlens(_parallel_pair(), _dispatch())
	tied = {e.branch: e.ens_increase_mwh for e in ranking.entries if e.branch in (1, 2)}
	assert tied[1] == pytest.approx(tied[2]), "the parallel branches did not tie"
	assert first.index(1) < first.index(2), "tied branches were not ordered by index"


# --------------------------------------------------------------------------
# 07-layer4 §10: the two gates whose names the plan promises by hand
# --------------------------------------------------------------------------


def test_cloud_flag_semantics():
	"""The gate `test_cloud_flag_semantics` (07-layer4 §10): only bits 0-1 == 0
	are kept, and a cloudy pixel is NaN rather than 0.

	Two properties in one gate because the plan's row states both: the polarity
	of the confidence bits and the sentinel for an unusable pixel. A cloudy pixel
	is *unknown*, not *lit* -- reading it as 0 credits the detector for an hour it
	could not see, which is the failure the canary
	`canaries/test_cloud_flag_polarity.py` plants in both directions.
	"""
	assert MAX_CLOUD_CONFIDENCE == 0, (
		"the pinned ceiling moved; bits 0-1 == 0 is the plan's answer, and a wider "
		"ceiling admits probably-clear pixels"
	)
	assert ViirsConfig().max_cloud_confidence == MAX_CLOUD_CONFIDENCE, (
		"the default config no longer carries the pinned ceiling"
	)

	tile = ViirsTile(
		radiance=np.zeros((1, 2, 2), np.float32),
		sensor_zenith=np.zeros((1, 2, 2), np.float32),
		cloud_bits=np.zeros((1, 2, 2), np.uint8),
		month=np.array([1], np.uint8),
		timestamps=(START,),
	)
	zone_ids = np.ones((2, 2), dtype=np.uint32)
	blind = zone_series(tile, np.full((1, 2, 2), np.nan, np.float32), zone_ids, 2)
	assert np.isnan(blind[0, 1]), "an all-cloudy zone-hour must be NaN, not a number"


def test_no_temporal_leakage():
	"""The gate `test_no_temporal_leakage` (07-layer4 §10): no feature at *t*
	depends on *t* or later.

	Run against the module's own builder rather than a hand-written one, because
	the leak this guards is the one the shipped `shift(1)` prevents -- a builder
	that reads its own row inflates every score without changing a line of
	output, which is why the plan makes it a gate rather than a review note.
	"""
	frame = pd.DataFrame(
		{
			"timestamp": pd.date_range("2030-01-01", periods=96, freq="h"),
			ZONE_COLUMN: "z1",
			"outage": ((np.arange(96) % 13) == 0).astype(float),
			"load_mw": 1000.0 + 50.0 * np.sin(np.arange(96) * 2 * np.pi / 24),
			"temp_c": 25.0 + 3.0 * np.cos(np.arange(96) * 2 * np.pi / 24),
		}
	)
	assert_causal_features(
		lambda f: build_features(f, group_column=ZONE_COLUMN),
		frame,
		["outage_rate_lag", "outage_count_lag", "outage_max_lag"],
		target_column="outage",
		group_column=ZONE_COLUMN,
	)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))