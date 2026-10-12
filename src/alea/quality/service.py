# SPDX-License-Identifier: MIT
"""Writing validation and benchmark artefacts.

Two writers, one per rule in `12-quality.md` §5 and §6.2, plus the coverage
check that turns criterion 4 from a directory listing into a question with an
answer.

The writers take the *measurement* and produce the payload; they do not take a
path to a file that already holds one. That shape matters for the same reason
`write_artefact` writes the sidecar after the payload: a validation that is
recorded by copying a number a caller already formatted is a validation whose
provenance nobody can check.

Hardware is captured at write time, never accepted as an argument. A benchmark
artefact is evidence about a run on a machine, and a machine passed in as a
parameter is a machine someone remembered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alea.io.artefacts import write_artefact
from alea.io.pipeline import stage
from alea.logging import get_logger
from alea.provenance.models import DerivedProvenance
from alea.quality.views import (
	BENCHMARK_TARGET_CORES,
	VALIDATION_TARGETS,
	BenchmarkArtefact,
	Hardware,
	ValidationArtefact,
	ValidationStatus,
	benchmark_targets,
	storage_root,
)

_log = get_logger(__name__)


def validation_artefact(
	target: str,
	ground_truth: str,
	*,
	metrics: dict[str, float] | None = None,
	base_rate: float | None = None,
	ground_truth_checksum: str = "",
	status: ValidationStatus | None = None,
	reason: str = "",
	notes: str = "",
) -> ValidationArtefact:
	"""Build a validation artefact, inferring the status when it is not given.

	A target with metrics passed its measurement; a target with a reason and no
	metrics was skipped. Inferring rather than requiring the caller to state it
	removes the way this goes wrong: a caller who measured nothing but marked the
	status passed, which the model then refuses anyway -- better to make the
	correct status the path of least resistance.
	"""
	if status is None:
		if metrics:
			status = ValidationStatus.PASSED
		elif reason:
			status = ValidationStatus.SKIPPED
		else:
			raise ValueError(
				f"{target}: a validation with no metrics and no reason is a "
				f"validation that did not happen; say which"
			)
	milestone = next((t.milestone for t in VALIDATION_TARGETS if t.key == target), "")
	return ValidationArtefact(
		target=target,
		ground_truth=ground_truth,
		ground_truth_checksum=ground_truth_checksum,
		status=status,
		metrics=dict(metrics or {}),
		base_rate=base_rate,
		milestone=milestone,
		reason=reason,
		notes=notes,
	)


def benchmark_artefact(
	operation: str,
	seconds: float,
	*,
	input_size: dict[str, Any] | None = None,
	notes: str = "",
) -> BenchmarkArtefact:
	"""Build a benchmark artefact, capturing the hardware it is claimed on.

	The plan's targets are stated on 12 cores. A measurement on fewer cores is
	recorded with its hardware and no target, because comparing a 4-core run to a
	12-core budget is the comparison the plan's own wording forbids -- the target
	is a property of the workload *on that machine*.
	"""
	hardware = Hardware.capture()
	target = benchmark_targets().get(operation)
	if target is not None and hardware.cpu_count < BENCHMARK_TARGET_CORES:
		_log.warning(
			"quality.benchmark.below_target_cores",
			operation=operation,
			cores=hardware.cpu_count,
			required=BENCHMARK_TARGET_CORES,
		)
		target = None
	return BenchmarkArtefact(
		operation=operation,
		seconds=seconds,
		hardware=hardware,
		target_seconds=target,
		input_size=dict(input_size or {}),
		notes=notes,
	)


def write_validation(artefact: ValidationArtefact, root: str | Path | None = None) -> str:
	"""Write a validation artefact and return its checksum.

	``inputs`` carries the ground-truth checksum so the derived provenance is
	satisfiable and the result traces to the exact truth it was measured against.
	A validation whose ground truth has no checksum records the target name in
	its place, which is weaker but honest -- the alternative is an artefact that
	refuses to be written, and a target that therefore writes nothing.
	"""
	base = Path(root) if root is not None else Path(storage_root())
	target = base / "validation" / f"{artefact.target}.json"
	provenance = DerivedProvenance(
		source_id=f"validation:{artefact.target}",
		inputs=[artefact.ground_truth_checksum or f"ground-truth:{artefact.ground_truth}"],
		parameters={"target": artefact.target, "status": artefact.status.value},
		notes=artefact.notes or artefact.reason or f"validated against {artefact.ground_truth}",
		uncertainty=0.0,
	)
	return write_artefact(target, artefact.model_dump(mode="json"), provenance, format="json")


def write_benchmark(artefact: BenchmarkArtefact, root: str | Path | None = None) -> str:
	"""Write a benchmark artefact and return its checksum."""
	base = Path(root) if root is not None else Path(storage_root())
	target = base / "benchmarks" / f"{artefact.operation}.json"
	provenance = DerivedProvenance(
		source_id=f"benchmark:{artefact.operation}",
		inputs=[f"hardware:{artefact.hardware.describe}"],
		parameters={
			"operation": artefact.operation,
			"seconds": artefact.seconds,
			"cpu_count": artefact.hardware.cpu_count,
		},
		notes=artefact.notes or f"{artefact.operation} measured on {artefact.hardware.describe}",
		uncertainty=0.0,
	)
	return write_artefact(target, artefact.model_dump(mode="json"), provenance, format="json")


def validation_coverage(root: str | Path | None = None) -> dict[str, str]:
	"""Which validation targets have written an artefact, keyed by target.

	The answer to criterion 4. A target absent from the mapping wrote nothing,
	which is the state the plan calls out: "a validation result that exists only
	in a log line is a validation nobody can re-check".

	Reads the artefact's own ``target`` field rather than trusting the filename,
	so a file named for one target that records another is caught rather than
	counted twice.
	"""
	import json

	base = Path(root) if root is not None else Path(storage_root())
	directory = base / "validation"
	found: dict[str, str] = {}
	if not directory.is_dir():
		return found
	for path in sorted(directory.glob("*.json")):
		if path.name.endswith(".provenance.json"):
			continue
		try:
			payload = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, ValueError):
			continue
		target = payload.get("target")
		if isinstance(target, str) and target:
			found[target] = str(path)
	return found


def missing_validation_targets(root: str | Path | None = None) -> list[str]:
	"""Promised validation targets with no artefact on disk.

	The list criterion 4 requires to be empty before the criterion is met. Scoped
	to the register, not to the directory: the directory can only report what it
	holds, so a target that never ran is invisible to it.
	"""
	covered = validation_coverage(root)
	return [t.key for t in VALIDATION_TARGETS if t.key not in covered]


@stage("quality_validation")
def _stage_validation(_config: Any, out: Path, context: Any) -> DerivedProvenance:
	"""Stage: report validation coverage as an artefact.

	The coverage itself is a result worth versioning: it says which of the
	plan's validation targets have evidence and which do not, and that is the
	claim criterion 4 makes.
	"""
	covered = validation_coverage()
	missing = missing_validation_targets()
	payload = {
		"targets": [t.model_dump(mode="json") for t in VALIDATION_TARGETS],
		"covered": sorted(covered),
		"missing": missing,
		"complete": not missing,
	}
	provenance = DerivedProvenance(
		source_id="quality_validation_coverage",
		inputs=context.inputs or ["quality:validation-register"],
		parameters={"targets": len(VALIDATION_TARGETS), "covered": len(covered)},
		notes=(
			"every validation target writes an artefact (12-quality §9 criterion 4); "
			f"{len(missing)} target(s) have no artefact"
		),
		uncertainty=0.0,
	)
	write_artefact(out, payload, provenance, format="json")
	_log.info("quality.validation.coverage", covered=len(covered), missing=len(missing))
	return provenance


__all__ = [
	"benchmark_artefact",
	"missing_validation_targets",
	"validation_artefact",
	"validation_coverage",
	"write_benchmark",
	"write_validation",
]
