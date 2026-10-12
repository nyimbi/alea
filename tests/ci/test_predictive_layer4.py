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

import numpy as np
import pytest

from alea.losses.views import DECOMPOSITION_TOLERANCE, LossComponents
from alea.outages.validate import ValidationError, binarise, detection_metrics
from alea.outages.views import DetectionMetrics, ViirsConfig
from alea.provenance.models import Basis
from alea.resilience.metrics import compute_metrics, customers_from_population
from alea.resilience.views import (
	InterruptionEvent,
	ResilienceConfig,
	ZoneCustomers,
)

START = datetime(2030, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------
# Criterion 6: the loss decomposition sums to its total
# --------------------------------------------------------------------------


def test_the_decomposition_sums_to_its_total():
	"""The invariant the specification's hardcoded zero breaks."""
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


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
