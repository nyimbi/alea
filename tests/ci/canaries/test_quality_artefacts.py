# SPDX-License-Identifier: MIT
"""Canary: a benchmark artefact without its hardware must be refused.

`12-quality.md` §6.2 — "a performance claim without its hardware is not a
claim". The gate is the required ``hardware`` field on
:class:`~alea.quality.views.BenchmarkArtefact`, and this canary watches it work:
it constructs the artefact the way a caller would if the field were optional and
asserts the model refuses.

The validation half is the same shape: an accuracy-shaped metric with no base
rate is refused, because 91% on a class that is 91% of the sample is no skill at
all. Both are watched failing here, which is what makes them gates rather than
documentation.

The defect is planted by *building the bad object*, not by mutating a file: the
rule lives in a pydantic validator, so the only way to violate it is to try to
construct the thing it forbids. A file-mutation canary would be mutating the
validator itself, which proves the validator was removed, not that it fires.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from alea.quality import (
	VALIDATION_TARGETS,
	BenchmarkArtefact,
	Hardware,
	ValidationArtefact,
	ValidationStatus,
	validation_artefact,
	validation_coverage,
	write_validation,
)


def test_the_benchmark_gate_refuses_an_artefact_with_no_hardware():
	"""The defect: a benchmark recorded without the machine it ran on."""
	with pytest.raises(ValidationError) as excinfo:
		BenchmarkArtefact(operation="minhash_1e6_documents", seconds=12.5)  # type: ignore[call-arg]
	assert "hardware" in str(excinfo.value), (
		"the model refused the artefact but not for the missing hardware: "
		f"{excinfo.value}"
	)


def test_the_benchmark_gate_accepts_one_with_hardware():
	"""The other half: the rule must not refuse a correct artefact."""
	artefact = BenchmarkArtefact(
		operation="minhash_1e6_documents",
		seconds=12.5,
		hardware=Hardware(platform="Test", machine="test", cpu_count=12),
	)
	assert artefact.hardware.cpu_count == 12


def test_the_base_rate_gate_refuses_an_accuracy_with_no_prevalence():
	"""The defect: an AUC reported without the base rate that interprets it."""
	with pytest.raises(ValidationError) as excinfo:
		ValidationArtefact(
			target="viirs_detection",
			ground_truth="GridWatch",
			status=ValidationStatus.PASSED,
			metrics={"auc": 0.83},
		)
	assert "base rate" in str(excinfo.value)


def test_the_base_rate_gate_accepts_an_accuracy_with_its_prevalence():
	artefact = ValidationArtefact(
		target="viirs_detection",
		ground_truth="GridWatch",
		status=ValidationStatus.PASSED,
		metrics={"auc": 0.83},
		base_rate=0.12,
	)
	assert artefact.base_rate == 0.12


def test_the_coverage_gate_notices_a_target_that_wrote_nothing(tmp_path: Path):
	"""Criterion 4 as a gate: a promised target with no artefact is visible.

	The mutation is a *deletion*: a target's artefact is removed and the coverage
	check must report the target missing. If it read the directory without the
	register, an empty tree would report complete coverage of nothing.
	"""
	write_validation(validation_artefact("kenya_demand", "AFREC", metrics={"x": 1.0}), tmp_path)
	assert set(validation_coverage(tmp_path)) == {"kenya_demand"}

	# Remove the artefact and its sidecar: the target must fall back to missing.
	for path in (tmp_path / "validation").glob("kenya_demand.json*"):
		path.unlink()
	assert validation_coverage(tmp_path) == {}

	# And the register still knows the target exists, which is the difference
	# between "wrote nothing" and "was never promised".
	assert any(t.key == "kenya_demand" for t in VALIDATION_TARGETS)


def test_the_coverage_gate_reads_the_target_field_not_the_filename(tmp_path: Path):
	"""A file named for one target that records another must not count twice.

	The filename is not evidence; the artefact's own ``target`` field is. A check
	that trusted the name would pass on a mislabelled file.
	"""
	artefact = validation_artefact("kenya_demand", "AFREC", metrics={"x": 1.0})
	write_validation(artefact, tmp_path)
	path = tmp_path / "validation" / "kenya_demand.json"
	path.rename(tmp_path / "validation" / "viirs_detection.json")
	covered = validation_coverage(tmp_path)
	assert "kenya_demand" in covered, "coverage trusted the filename over the payload"
	assert "viirs_detection" not in covered
