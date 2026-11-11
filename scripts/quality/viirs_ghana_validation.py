# SPDX-License-Identifier: MIT
"""Score the VIIRS outage detector against GridWatch Ghana for one year.

Writes the `viirs_detection` validation artefact (12-quality §5, AUC >= 0.80).
Inputs are the mirrors under docs/research/milestone-data/: VNP46A2 for the
observed radiance and cloud mask, VNP46A1 for the viewing zenith, GridWatch
parquet for the truth. Every deviation from 07-layer4 §2 is written into the
artefact's notes, because a number without the conditions that produced it is
the thing 07-layer4 §2.5 forbids.

Usage: viirs_ghana_validation.py YEAR [TILE]
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from alea.outages import gridwatch, viirs, viirs_h5
from alea.outages.validate import detection_metrics
from alea.outages.views import ViirsConfig
from alea.quality import service
from alea.quality.views import ValidationStatus

ROOT = Path(__file__).resolve().parents[2]
MIRRORS = ROOT / "docs/research/milestone-data"
PASS_AUC = 0.80
CLAIMED_AUC = 0.8346


def main(argv: list[str]) -> int:
	year = int(argv[0])
	tile_name = argv[1] if len(argv) > 1 else "h17v08"
	a2 = {viirs_h5.day_of(p): p for p in sorted((MIRRORS / "viirs-vnp46a2").glob(f"VNP46A2.A{year}*.{tile_name}.*.h5"))}
	a1 = {viirs_h5.day_of(p): p for p in sorted((MIRRORS / "viirs-vnp46a1").glob(f"VNP46A1.A{year}*.{tile_name}.*.h5"))}
	assert a2, f"no VNP46A2 granules for {year} {tile_name}"
	lat, lon = viirs_h5.axes(next(iter(a2.values())))
	days = [d.date() for d in sorted(a2)]
	print(f"{len(a2)} A2 days, {len(a1)} A1 days; reading GridWatch", flush=True)

	readings = gridwatch.read_window(MIRRORS / "gridwatch-ghana", days)
	nights = gridwatch.pixel_nights(readings, lat, lon)
	assert not nights.empty, "no GridWatch pixel-nights fall inside the tile"
	pixels = nights[["row", "col"]].drop_duplicates().reset_index(drop=True)
	print(f"{len(nights)} pixel-nights over {len(pixels)} pixels", flush=True)

	tile = viirs_h5.site_tile(list(a2.values()), a1, pixels["row"].to_numpy(), pixels["col"].to_numpy())
	config = ViirsConfig()
	baseline = viirs.build_baseline([tile], config)
	anomaly = viirs.detect_tile(tile, baseline, config)[:, :, 0]  # [time, pixel]

	day_index = {d: i for i, d in enumerate(days)}
	pixel_index = {(int(r), int(c)): i for i, (r, c) in enumerate(zip(pixels["row"], pixels["col"], strict=True))}
	score = np.array(
		[anomaly[day_index[pd.Timestamp(n).date()], pixel_index[(int(r), int(c))]]
		 for n, r, c in zip(nights["night"], nights["row"], nights["col"], strict=True)],
		dtype=float,
	)
	label = gridwatch.outage_label(nights["unpowered_fraction"].to_numpy())
	blind = float(np.isnan(score).mean())
	metrics = detection_metrics(score, label.astype(float), config)

	passed = metrics.auc >= PASS_AUC
	notes = (
		f"Ghana {year}, tile {tile_name}; {len(nights)} pixel-nights at {len(pixels)} pixels; "
		f"{blind:.1%} of pixel-nights blind (cloud/fill) and dropped. Truth: pixel-night outage = "
		f">=50% of reporting GridWatch readings unpowered, 00:00-03:00 UTC, >=5 readings. "
		f"Deviations from 07-layer4 §2: baseline built from the same single year it scores "
		f"(not 'all years'), so outage nights are in the baseline sample; cloud confidence read from "
		f"QF_Cloud_Mask bits 6-7 (the plan's bits 0-1 are day/night and land/water); the score is the "
		f"binary flag, so AUC is a balanced-accuracy-like quantity, not a ranking over a continuous score. "
		f"Claimed AUC {CLAIMED_AUC} (spec4-base §5.5) is not reproduced or refuted by this alone: "
		f"different year, tile coverage and truth definition. A1 days with a zenith: {len(a1)} of {len(a2)}."
	)
	artefact = service.validation_artefact(
		"viirs_detection",
		"GridWatch Ghana (nLine public bucket), VNP46A2/VNP46A1 v2",
		metrics={
			"auc": metrics.auc,
			"pr_auc": metrics.pr_auc,
			"precision": metrics.precision,
			"recall": metrics.recall,
			"f1": metrics.f1,
			"blind_fraction": blind,
		},
		base_rate=metrics.base_rate,
		status=ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
		notes=notes,
	)
	print(service.write_validation(artefact))
	print({k: round(v, 4) for k, v in artefact.metrics.items()}, "base_rate", round(metrics.base_rate, 4), artefact.status.value)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
