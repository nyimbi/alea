# SPDX-License-Identifier: MIT
"""Quality artefacts: validation evidence and benchmarks, with their hardware.

`12-quality.md` §5 requires every validation target to write an artefact and §6.2
requires every benchmark to record the machine it ran on. Neither was enforced;
this package is where both become structural rather than conventional.
"""

from __future__ import annotations

from alea.quality.claims import (
	MILESTONES,
	REGISTER,
	Claim,
	Review,
	due_at,
	milestone_of,
	review,
)
from alea.quality.layout import (
	ABSENT,
	ARCHITECTURE,
	SECTION_HEADING,
	DeclaredPath,
	LayoutGap,
	layout_gaps,
	parse_layout,
)
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
	"ABSENT",
	"ARCHITECTURE",
	"BENCHMARK_TARGET_CORES",
	"MILESTONES",
	"REGISTER",
	"SECTION_HEADING",
	"VALIDATION_KEYS",
	"VALIDATION_TARGETS",
	"BenchmarkArtefact",
	"Claim",
	"DeclaredPath",
	"Hardware",
	"LayoutGap",
	"Review",
	"ValidationArtefact",
	"ValidationStatus",
	"ValidationTarget",
	"benchmark_artefact",
	"benchmark_targets",
	"due_at",
	"layout_gaps",
	"milestone_of",
	"missing_validation_targets",
	"parse_layout",
	"review",
	"validation_artefact",
	"validation_coverage",
	"write_benchmark",
	"write_validation",
]
