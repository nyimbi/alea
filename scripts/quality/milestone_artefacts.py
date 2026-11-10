# SPDX-License-Identifier: MIT
"""Write the milestone evidence this machine can honestly produce.

`14-roadmap.md` gates M1-M8 each name an artefact. Where the ground truth or
the input data is not on this machine the plan says what to do: "M2 records the
skip explicitly and the VIIRS model is **not** reported as validated". This
script does that, and it derives each skip reason from a probe of the tree
rather than asserting it: if the data a target needs is present, the script
refuses to write a skip and says which real producer to run instead. A skip
written beside the data it claims is missing is a false record.

It also measures the two benchmark operations whose kernels are local
(`minhash_1e6_documents`, `viirs_vza_baseline_1e9_pixels`) on the actual
hardware. It resolves no claim in `alea.quality.claims`: a skip is not a
reproduction, a refutation, or a withdrawal.

Usage: ``uv run python scripts/quality/milestone_artefacts.py [--no-bench]``
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from alea.config import paths
from alea.quality import service
from alea.quality.views import (
	VALIDATION_TARGETS,
	ValidationArtefact,
	ValidationStatus,
)

ROOT = paths.repo_root()


def _present(*patterns: str, under: str = "data/raw") -> list[str]:
	base = ROOT / under
	found: list[str] = []
	for pattern in patterns:
		found.extend(sorted(str(p.relative_to(ROOT)) for p in base.glob(pattern)))
	return found


# target key -> (what must exist, probe patterns, root, what the target needs)
NEEDS: dict[str, tuple[str, tuple[str, ...], str]] = {
	"viirs_detection": (
		"GridWatch Ghana sensor outage records and VIIRS DNB granules",
		("**/gridwatch*", "**/viirs*", "**/VNP46*"),
		"data/raw",
	),
	"weather_forecasting": (
		"labelled outage events with a weather feed (Ghana, Adrar)",
		("**/gridwatch*", "**/adrar*", "**/era5*"),
		"data/raw",
	),
	"kenya_expansion": (
		"a PyPSA-Earth Kenya network and the users.md case-study inputs",
		("*kenya*", "*KE*.nc", "*_KE_*"),
		"results/networks",
	),
	"kenya_demand": (
		"a built Kenya network and AFREC national totals",
		("*kenya*", "*KE*.nc", "afrec*"),
		"results/networks",
	),
	"loss_approximation": (
		"a built Kenya network to run AC power flow against the DC approximation",
		("*kenya*", "*KE*.nc"),
		"results/networks",
	),
	"south_africa_capture_prices": (
		"COMPASS South Africa capture-price series",
		("**/compass*",),
		"data/raw",
	),
	"malawi_tlens": (
		"the Malawi TLENS expert line ranking",
		("**/tlens*", "**/malawi*"),
		"data/raw",
	),
}


def _skip(target_key: str) -> ValidationArtefact:
	target = next(t for t in VALIDATION_TARGETS if t.key == target_key)
	needs, patterns, under = NEEDS[target_key]
	found = _present(*patterns, under=under)
	if found:
		raise SystemExit(
			f"{target_key}: {needs} appears to be present ({found[:3]}); run the real "
			f"producer instead of recording a skip"
		)
	return ValidationArtefact(
		target=target.key,
		ground_truth=target.ground_truth,
		status=ValidationStatus.SKIPPED,
		milestone=target.milestone,
		reason=(
			f"needs {needs}; probed {', '.join(patterns)} under {under}/ and found "
			f"nothing. Not validated: no figure for this target may be reported as "
			f"measured."
		),
	)


def _bench_minhash() -> None:
	from alea._core import kernels

	n = 1_000_000
	rng = np.random.default_rng(0)
	vocab = [f"w{i}" for i in range(5000)]
	idx = rng.integers(0, len(vocab), size=(n, 24))
	docs = [(f"d{i}", " ".join(vocab[j] for j in row)) for i, row in enumerate(idx)]
	# Ten percent near-duplicates, so the grouping path does work.
	for i in range(0, n, 10):
		docs[i] = (docs[i][0], docs[max(i - 1, 0)][1] + " x")
	start = time.perf_counter()
	groups = kernels.deduplicate(docs)
	seconds = time.perf_counter() - start
	artefact = service.benchmark_artefact(
		"minhash_1e6_documents",
		seconds,
		input_size={"documents": n, "words_per_document": 24, "groups": len(groups)},
		notes="synthetic documents, 10% near-duplicates; k=5, 128 permutations, threshold 0.7",
	)
	service.write_benchmark(artefact)
	print(f"minhash_1e6_documents: {seconds:.1f}s (ratio {artefact.ratio})")


def _bench_vza() -> None:
	from alea._core import kernels

	t, y, x = 365, 1000, 2740
	rng = np.random.default_rng(1)
	radiance = rng.gamma(2.0, 5.0, size=(t, y, x)).astype(np.float32)
	zenith = rng.uniform(0.0, 60.0, size=(t, y, x)).astype(np.float32)
	month = (np.arange(t) * 12 // t + 1).astype(np.uint8)
	start = time.perf_counter()
	out = kernels.vza_baseline(radiance, zenith, month)
	seconds = time.perf_counter() - start
	artefact = service.benchmark_artefact(
		"viirs_vza_baseline_1e9_pixels",
		seconds,
		input_size={"pixel_observations": t * y * x, "output_shape": list(out.shape)},
		notes="synthetic radiance and zenith, one year of daily frames",
	)
	service.write_benchmark(artefact)
	print(f"viirs_vza_baseline_1e9_pixels: {seconds:.1f}s (ratio {artefact.ratio})")


def main(argv: list[str]) -> int:
	for key in NEEDS:
		print(f"{key}: ", end="")
		print(service.write_validation(_skip(key)))
	benches: list[Callable[[], None]] = [] if "--no-bench" in argv else [_bench_minhash, _bench_vza]
	for bench in benches:
		bench()
	print("missing validation targets:", service.missing_validation_targets())
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
