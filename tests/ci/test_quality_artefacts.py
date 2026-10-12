# SPDX-License-Identifier: MIT
"""`12-quality.md` §9 criteria 4 and 6: validation and benchmark artefacts.

Criterion 4 — "every validation target writes an artefact" — is a claim about a
*register*, not about a directory. A directory listing can only report the files
that exist; a target that never ran leaves nothing to miss. So the register of
eight targets `12-quality.md` §5 names is data here, and the check is whether
each has an artefact whose own ``target`` field names it.

Criterion 6 — "every benchmark records its hardware" — is enforced by the model
rather than by a check: :class:`BenchmarkArtefact` has a required ``hardware``
field, so a benchmark without one is not constructible. The tests below prove
both halves: the model refuses the omission, and the captured hardware is the
real machine rather than a placeholder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from alea.quality import (
	BENCHMARK_TARGET_CORES,
	VALIDATION_TARGETS,
	BenchmarkArtefact,
	Hardware,
	ValidationArtefact,
	ValidationStatus,
	benchmark_artefact,
	benchmark_targets,
	missing_validation_targets,
	validation_artefact,
	validation_coverage,
	write_benchmark,
	write_validation,
)


def test_the_validation_register_matches_the_plans_table():
	"""The eight targets of `12-quality.md` §5, by key.

	The register is the thing criterion 4 is checked against, so it has to be the
	plan's set. A register that quietly dropped a target would report complete
	coverage of a smaller promise.
	"""
	assert {t.key for t in VALIDATION_TARGETS} == {
		"viirs_detection",
		"weather_forecasting",
		"kenya_expansion",
		"kenya_demand",
		"south_africa_capture_prices",
		"malawi_tlens",
		"loss_approximation",
		"extraction_accuracy",
	}


def test_every_validation_target_names_its_ground_truth_and_milestone():
	for target in VALIDATION_TARGETS:
		assert target.ground_truth, f"{target.key} has no ground truth"
		assert target.milestone, f"{target.key} resolves at no milestone"


def test_a_validation_with_metrics_is_marked_passed():
	artefact = validation_artefact("kenya_demand", "AFREC national totals", metrics={"relative_error": 0.011})
	assert artefact.status is ValidationStatus.PASSED
	assert artefact.milestone == "M1", "the milestone did not come from the register"


def test_a_validation_with_a_reason_and_no_metrics_is_marked_skipped():
	artefact = validation_artefact(
		"viirs_detection", "GridWatch Ghana", reason="credentialed source unavailable"
	)
	assert artefact.status is ValidationStatus.SKIPPED
	assert artefact.reason


def test_a_validation_that_measured_nothing_and_says_nothing_is_refused():
	"""No metrics and no reason is a validation that did not happen."""
	with pytest.raises(ValueError, match="did not happen"):
		validation_artefact("kenya_demand", "AFREC national totals")


def test_an_accuracy_without_a_base_rate_is_refused():
	"""`07-layer4` §2.5: an accuracy without its prevalence cannot be read."""
	with pytest.raises(ValidationError, match="base rate"):
		validation_artefact("viirs_detection", "GridWatch", metrics={"auc": 0.83})


def test_an_accuracy_with_a_base_rate_is_accepted():
	artefact = validation_artefact(
		"viirs_detection", "GridWatch", metrics={"auc": 0.83}, base_rate=0.12
	)
	assert artefact.base_rate == 0.12


def test_a_pass_with_no_metrics_is_refused():
	"""A validation marked passed that measured nothing is the defect the rule names."""
	with pytest.raises(ValidationError, match="measured nothing"):
		ValidationArtefact(
			target="kenya_demand",
			ground_truth="AFREC",
			status=ValidationStatus.PASSED,
			metrics={},
		)


def test_a_skip_with_no_reason_is_refused():
	with pytest.raises(ValidationError, match="silent skip"):
		ValidationArtefact(
			target="kenya_demand",
			ground_truth="AFREC",
			status=ValidationStatus.SKIPPED,
		)


def test_a_validation_round_trips_through_a_written_artefact(tmp_path: Path):
	artefact = validation_artefact(
		"kenya_demand", "AFREC national totals", metrics={"relative_error": 0.011}, base_rate=0.5
	)
	write_validation(artefact, tmp_path)
	path = tmp_path / "validation" / "kenya_demand.json"
	assert path.exists()
	assert path.with_suffix(".json.provenance.json").exists(), "no provenance sidecar"
	payload = json.loads(path.read_text())
	assert payload["target"] == "kenya_demand"
	assert payload["metrics"]["relative_error"] == pytest.approx(0.011)


def test_coverage_reports_only_targets_with_an_artefact(tmp_path: Path):
	write_validation(validation_artefact("kenya_demand", "AFREC", metrics={"x": 1.0}), tmp_path)
	covered = validation_coverage(tmp_path)
	assert set(covered) == {"kenya_demand"}


def test_missing_targets_is_every_promised_target_minus_the_covered_ones(tmp_path: Path):
	write_validation(validation_artefact("kenya_demand", "AFREC", metrics={"x": 1.0}), tmp_path)
	missing = missing_validation_targets(tmp_path)
	assert "kenya_demand" not in missing
	assert set(missing) == {t.key for t in VALIDATION_TARGETS} - {"kenya_demand"}


def test_an_empty_tree_misses_every_target(tmp_path: Path):
	assert len(missing_validation_targets(tmp_path)) == len(VALIDATION_TARGETS)


def test_the_captured_hardware_is_this_machine():
	hardware = Hardware.capture()
	assert hardware.cpu_count >= 1
	assert hardware.machine, "the architecture is empty"
	assert hardware.platform, "the platform is empty"


def test_a_benchmark_without_hardware_is_not_constructible():
	"""Criterion 6 as a schema rule: the field is required, not conventional."""
	with pytest.raises(ValidationError):
		BenchmarkArtefact(operation="minhash_1e6_documents", seconds=12.5)  # type: ignore[call-arg]


def test_a_benchmark_carries_the_hardware_it_was_measured_on():
	artefact = benchmark_artefact("minhash_1e6_documents", 12.5)
	assert artefact.hardware.cpu_count >= 1
	assert "cores" in artefact.hardware.describe


def test_the_plan_targets_are_stated_in_seconds():
	targets = benchmark_targets()
	assert targets["minhash_1e6_documents"] == 30.0
	assert targets["daily_report_generation"] == 300.0
	assert all(value > 0 for value in targets.values())


def test_a_benchmark_on_too_few_cores_carries_no_target():
	"""A 12-core budget is not a budget for a 4-core run (`12-quality` §6.2)."""
	hardware = Hardware(
		platform="Test",
		machine="test",
		cpu_count=BENCHMARK_TARGET_CORES - 1,
	)
	artefact = BenchmarkArtefact(operation="minhash_1e6_documents", seconds=12.5, hardware=hardware)
	assert artefact.target_seconds is None
	assert artefact.within_target is None


def test_a_benchmark_under_its_target_is_within_target():
	hardware = Hardware(platform="Test", machine="test", cpu_count=BENCHMARK_TARGET_CORES)
	artefact = BenchmarkArtefact(
		operation="minhash_1e6_documents", seconds=12.5, hardware=hardware, target_seconds=30.0
	)
	assert artefact.within_target is True
	assert artefact.ratio == pytest.approx(12.5 / 30.0)


def test_a_benchmark_round_trips_through_a_written_artefact(tmp_path: Path):
	artefact = benchmark_artefact("kenya_cep_solve", 1234.5)
	write_benchmark(artefact, tmp_path)
	path = tmp_path / "benchmarks" / "kenya_cep_solve.json"
	payload = json.loads(path.read_text())
	assert payload["operation"] == "kenya_cep_solve"
	assert payload["hardware"]["cpu_count"] >= 1, "the written artefact lost its hardware"
