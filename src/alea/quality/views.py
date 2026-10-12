# SPDX-License-Identifier: MIT
"""Validation and benchmark artefacts, with the hardware they ran on.

`12-quality.md` §5 and §9 state two rules that nothing in the tree enforced:

* **"Every validation writes an artefact. A validation result that exists only in
  a log line is a validation nobody can re-check."** (criterion 4)
* **"A performance claim without its hardware is not a claim."** (criterion 6)

Both are the same defect wearing two hats: a number that is asserted somewhere a
reader cannot reach, or that a reader cannot interpret. A benchmark that says
"2.1 s" without saying on how many cores is not a slow or fast result, it is an
uninterpretable one -- the plan's own targets are stated "on 12 cores", so a
measurement that does not record its core count cannot be compared to its own
target.

So there are two models here, and one register.

:class:`Hardware` is captured, not typed. Every field comes from the machine, so
a benchmark artefact cannot carry a core count someone remembered wrong.

:class:`ValidationArtefact` and :class:`BenchmarkArtefact` are the payloads the
stages write. The validation model requires a :class:`ValidationOutcome` and the
ground truth it was measured against; the benchmark model requires a
:class:`Hardware`, so a benchmark without its hardware is not constructible --
the rule is structural rather than a convention someone has to remember.

:data:`VALIDATION_TARGETS` is the register of the eight targets `12-quality.md`
§5 names, each with the milestone at which it resolves. A target is a *plan
promise*; a validation artefact is the evidence. The register is what lets a
check ask "does every promised target have an artefact?" instead of trusting a
directory listing to be complete.
"""

from __future__ import annotations

import os
import platform
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alea.provenance.models import Basis


class Hardware(BaseModel):
	"""The machine a measurement ran on.

	Captured from the running system rather than passed in. A benchmark artefact
	whose core count was typed by hand records what someone believed, and the
	belief is exactly what a later reader is trying to check.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	platform: str
	machine: str
	"""The CPU architecture, e.g. ``arm64``."""
	cpu_count: int = Field(ge=1)
	"""Logical cores, which is the unit the plan's targets are stated in."""
	cpu_count_physical: int = Field(default=0, ge=0)
	memory_bytes: int = Field(default=0, ge=0)
	python_version: str = ""
	captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

	@classmethod
	def capture(cls) -> Hardware:
		"""Read this machine's specification."""
		physical = 0
		try:  # POSIX; on macOS `sysctl -n hw.physicalcpu`
			out = subprocess.run(
				["sysctl", "-n", "hw.physicalcpu"],
				capture_output=True,
				text=True,
				check=False,
				timeout=5,
			)
			if out.returncode == 0:
				physical = int(out.stdout.strip())
		except (OSError, ValueError):
			physical = 0
		return cls(
			platform=platform.system(),
			machine=platform.machine(),
			cpu_count=os.cpu_count() or 1,
			cpu_count_physical=physical,
			memory_bytes=_memory_bytes(),
			python_version=platform.python_version(),
		)

	@property
	def describe(self) -> str:
		"""One line a report can print beside the number it qualifies."""
		return f"{self.cpu_count} cores ({self.machine}, {self.platform})"


def _memory_bytes() -> int:
	"""Total physical memory, or 0 when the platform will not say."""
	try:
		page_size = os.sysconf("SC_PAGE_SIZE")
		pages = os.sysconf("SC_PHYS_PAGES")
		if isinstance(page_size, int) and isinstance(pages, int):
			return page_size * pages
	except (ValueError, OSError, AttributeError):
		return 0
	return 0


class BenchmarkArtefact(BaseModel):
	"""One measured operation, with the hardware and the target it is judged by."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	operation: str
	"""The plan's operation name, e.g. ``minhash_1e6_documents``."""
	seconds: float = Field(ge=0.0)
	hardware: Hardware
	"""Required. A benchmark without its hardware is not a claim (12-quality §6.2)."""
	target_seconds: float | None = Field(default=None, gt=0.0)
	"""The plan's target for this operation, when it states one."""
	input_size: dict[str, Any] = Field(default_factory=dict)
	notes: str = ""

	@property
	def within_target(self) -> bool | None:
		"""Whether the measurement meets the plan's target, or None if none is stated."""
		if self.target_seconds is None:
			return None
		return self.seconds <= self.target_seconds

	@property
	def ratio(self) -> float | None:
		"""Measured over target. Above 1.0 is over budget."""
		if self.target_seconds is None or self.target_seconds == 0.0:
			return None
		return self.seconds / self.target_seconds


class ValidationStatus(StrEnum):
	"""How a validation target stands."""

	PASSED = "passed"
	FAILED = "failed"
	SKIPPED = "skipped"
	"""The ground truth was unavailable. Never conflated with passed: a model
	that could not be validated is not a validated model (07-layer4 §2.5)."""


class ValidationArtefact(BaseModel):
	"""The evidence for one validation target.

	Carries the ground truth by name *and* by checksum, so a reader can find what
	the claim was checked against and confirm the bytes have not moved since.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	target: str
	"""Registry key from :data:`VALIDATION_TARGETS`."""
	ground_truth: str
	ground_truth_checksum: str = ""
	status: ValidationStatus
	metrics: dict[str, float] = Field(default_factory=dict)
	base_rate: float | None = None
	"""Required whenever an accuracy-shaped metric is present. An accuracy
	without its base rate is a number that cannot be interpreted: 91% on a class
	that is 91% of the sample is no skill at all (07-layer4 §2.5)."""
	basis: Basis = Basis.MEASURED
	hardware: Hardware | None = None
	"""Present when the validation is also a measurement of cost."""
	milestone: str = ""
	reason: str = ""
	notes: str = ""

	_ACCURACY_KEYS = ("accuracy", "precision", "recall", "f1", "auc", "pr_auc", "roc_auc")

	@model_validator(mode="after")
	def _accuracy_carries_its_base_rate(self) -> ValidationArtefact:
		accuracy_shaped = [k for k in self.metrics if k.lower() in self._ACCURACY_KEYS]
		if accuracy_shaped and self.base_rate is None:
			raise ValueError(
				f"{self.target} reports {', '.join(sorted(accuracy_shaped))} with no "
				f"base rate; an accuracy without the prevalence it was measured on "
				f"cannot be read (07-layer4 §2.5)"
			)
		return self

	@model_validator(mode="after")
	def _a_pass_has_a_measurement(self) -> ValidationArtefact:
		if self.status is ValidationStatus.PASSED and not self.metrics:
			raise ValueError(
				f"{self.target} is marked passed with no metrics; a validation "
				f"that measured nothing cannot have passed"
			)
		return self

	@model_validator(mode="after")
	def _a_skip_states_why(self) -> ValidationArtefact:
		if self.status is ValidationStatus.SKIPPED and not self.reason:
			raise ValueError(f"{self.target} is skipped with no reason; a silent skip reads as a pass")
		return self


class ValidationTarget(BaseModel):
	"""One validation target the plan promises."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	key: str
	ground_truth: str
	milestone: str
	pass_condition: str


VALIDATION_TARGETS: tuple[ValidationTarget, ...] = (
	ValidationTarget(
		key="viirs_detection",
		ground_truth="GridWatch Ghana (147 sensors, 2019-2023)",
		milestone="M2",
		pass_condition="AUC >= 0.80",
	),
	ValidationTarget(
		key="weather_forecasting",
		ground_truth="Ghana + Adrar",
		milestone="M2",
		pass_condition="PR-AUC, base rate reported",
	),
	ValidationTarget(
		key="kenya_expansion",
		ground_truth="users.md case study",
		milestone="M1",
		pass_condition="Reproduce or record discrepancy",
	),
	ValidationTarget(
		key="kenya_demand",
		ground_truth="AFREC national totals",
		milestone="M1",
		pass_condition="Within 2%",
	),
	ValidationTarget(
		key="south_africa_capture_prices",
		ground_truth="COMPASS",
		milestone="M8",
		pass_condition="Compare, record differences",
	),
	ValidationTarget(
		key="malawi_tlens",
		ground_truth="Expert ranking",
		milestone="M4",
		pass_condition="Top-N match",
	),
	ValidationTarget(
		key="loss_approximation",
		ground_truth="AC power flow on Kenya",
		milestone="M1",
		pass_condition="DC vs AC error recorded",
	),
	ValidationTarget(
		key="extraction_accuracy",
		ground_truth="Human review sample",
		milestone="M3",
		pass_condition="Precision per signal type",
	),
)
"""The eight targets `12-quality.md` §5 names, verbatim from its table.

This is the register criterion 4 is checked against. A directory listing cannot
answer "does every target write an artefact?" -- it can only say which files
exist, and a target that writes nothing leaves no trace to miss.
"""

VALIDATION_KEYS: frozenset[str] = frozenset(t.key for t in VALIDATION_TARGETS)


def benchmark_targets() -> dict[str, float]:
	"""The plan's performance targets, in seconds, keyed by operation.

	`12-quality.md` §6.2 states each target "on 12 cores". The target is a
	property of the *workload on that hardware*, so a benchmark compares against
	it only when the recorded core count is at least the stated one; below it,
	the measurement is reported with its hardware and no verdict.
	"""
	return {
		"viirs_vza_baseline_1e9_pixels": 60.0,
		"minhash_1e6_documents": 30.0,
		"tlens_200_lines_8760_snapshots": 2 * 3600.0,
		"kenya_cep_solve": 30 * 60.0,
		"kenya_sector_coupled_solve": 2 * 3600.0,
		"daily_report_generation": 5 * 60.0,
	}


BENCHMARK_TARGET_CORES = 12
"""The core count the plan's targets are stated on (12-quality §6.2)."""


def storage_root() -> str:
	"""Where quality artefacts live, relative to the results root."""
	return "results/quality"


__all__ = [
	"BENCHMARK_TARGET_CORES",
	"VALIDATION_KEYS",
	"VALIDATION_TARGETS",
	"BenchmarkArtefact",
	"Hardware",
	"ValidationArtefact",
	"ValidationStatus",
	"ValidationTarget",
	"benchmark_targets",
	"storage_root",
]
