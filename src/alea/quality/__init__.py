# SPDX-License-Identifier: MIT
"""Quality artefacts: validation evidence and benchmarks, with their hardware.

`12-quality.md` §5 requires every validation target to write an artefact and §6.2
requires every benchmark to record the machine it ran on. Neither was enforced;
this package is where both become structural rather than conventional.
"""

from __future__ import annotations

from alea.quality.service import (
	benchmark_artefact,
	missing_validation_targets,
	validation_artefact,
	validation_coverage,
	write_benchmark,
	write_validation,
)
from alea.quality.views import (
	BENCHMARK_TARGET_CORES,
	VALIDATION_KEYS,
	VALIDATION_TARGETS,
	BenchmarkArtefact,
	Hardware,
	ValidationArtefact,
	ValidationStatus,
	ValidationTarget,
	benchmark_targets,
)

__all__ = [
	"BENCHMARK_TARGET_CORES",
	"VALIDATION_KEYS",
	"VALIDATION_TARGETS",
	"BenchmarkArtefact",
	"Hardware",
	"ValidationArtefact",
	"ValidationStatus",
	"ValidationTarget",
	"benchmark_artefact",
	"benchmark_targets",
	"missing_validation_targets",
	"validation_artefact",
	"validation_coverage",
	"write_benchmark",
	"write_validation",
]
