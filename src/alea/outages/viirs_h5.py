# SPDX-License-Identifier: MIT
"""Read NASA Black Marble HDF5 granules into the detector's tile type.

VNP46A2 carries the observed BRDF-corrected radiance and the cloud mask but no
viewing geometry; VNP46A1 carries ``Sensor_Zenith``. The detector bins its
baseline by viewing zenith, so a tile is built from the A2 radiance and the A1
zenith of the same tile and day.

Layer names and the cloud-mask layout below were read from the granules
themselves (the ``Description`` attribute of ``QF_Cloud_Mask``), not from the
plan. The plan pins cloud confidence at bits 0-1; in the product those bits are
day/night and land/water, and confidence is bits 6-7. Reading bits 0-1 flags
every land-without-desert pixel (bit 1 set) as cloudy and the detector goes blind
over most of Ghana.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import h5py
import numpy as np
from numpy.typing import NDArray

from alea.outages.viirs import ViirsTile

GRID = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
RADIANCE_LAYER = "DNB_BRDF-Corrected_NTL"
GAP_FILLED_LAYER = "Gap_Filled_DNB_BRDF-Corrected_NTL"
CLOUD_LAYER = "QF_Cloud_Mask"
ZENITH_LAYER = "Sensor_Zenith"
QF_FILL = 65535
ZENITH_FILL = -32768
ZENITH_SCALE = 0.01

BLIND = 3
"""The confidence value the kernel treats as unusable at every ceiling."""


def decode_cloud_confidence(qf: NDArray[np.uint16]) -> NDArray[np.uint8]:
	"""Collapse ``QF_Cloud_Mask`` to the two-bit field the kernel reads.

	Bits 6-7 are the cloud detection result (00 confident clear .. 11 confident
	cloudy). Cloud shadow (bit 8), cirrus (bit 9), snow/ice (bit 10) and a fill
	value are folded to ``BLIND``: each is a pixel whose radiance says nothing
	about the lamps. Day (bit 0 set) is blind too; the daily product is a night
	product and a daytime value is not a nighttime radiance.
	"""
	qf = np.asarray(qf, dtype=np.uint16)
	confidence = ((qf >> 6) & 0b11).astype(np.uint8)
	blind = (qf == QF_FILL) | (((qf >> 8) & 0b111) != 0) | ((qf & 0b1) == 1)
	return np.where(blind, np.uint8(BLIND), confidence).astype(np.uint8)


def axes(path: str | Path) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
	"""(lat, lon) cell-centre axes of a granule."""
	with h5py.File(path, "r") as f:
		g = f[GRID]
		return np.asarray(g["lat"][:], dtype=float), np.asarray(g["lon"][:], dtype=float)


def read_pixels(
	a2_path: str | Path,
	rows: NDArray[np.int64],
	cols: NDArray[np.int64],
	*,
	a1_path: str | Path | None = None,
) -> tuple[NDArray[np.float32], NDArray[np.uint8], NDArray[np.float32]]:
	"""Radiance, decoded cloud confidence and zenith at the given pixels, one day.

	A pixel with no A1 granule for the day gets a NaN zenith, and the kernel
	treats a NaN zenith as unbinnable rather than guessing a bin.
	"""
	with h5py.File(a2_path, "r") as f:
		g = f[GRID]
		radiance = np.asarray(g[RADIANCE_LAYER][:], dtype=np.float32)[rows, cols]
		cloud = decode_cloud_confidence(np.asarray(g[CLOUD_LAYER][:])[rows, cols])
	radiance = np.where(radiance <= -999.0, np.nan, radiance).astype(np.float32)
	cloud = np.where(np.isnan(radiance), np.uint8(BLIND), cloud).astype(np.uint8)
	if a1_path is None:
		return radiance, cloud, np.full(radiance.shape, np.nan, dtype=np.float32)
	with h5py.File(a1_path, "r") as f:
		raw = np.asarray(f[GRID][ZENITH_LAYER][:])[rows, cols]
	zenith = np.where(raw == ZENITH_FILL, np.nan, raw.astype(np.float32) * ZENITH_SCALE).astype(np.float32)
	return radiance, cloud, zenith


def day_of(path: str | Path) -> datetime:
	"""UTC midnight of the granule's acquisition day, from its ``A<yyyyddd>`` name."""
	stem = Path(path).name.split(".")[1]
	return datetime.strptime(stem[1:], "%Y%j").replace(tzinfo=UTC)


def site_tile(
	a2_paths: Sequence[str | Path],
	a1_paths: dict[datetime, str | Path],
	rows: NDArray[np.int64],
	cols: NDArray[np.int64],
) -> ViirsTile:
	"""A ``[time, n_pixels, 1]`` tile over chosen pixels, one granule open at a time.

	The pixel axis is laid out as ``y`` with ``x`` of one so the compiled kernels
	run unchanged. Granules are visited in date order; a day without an A1 file
	has a NaN zenith for every pixel.
	"""
	ordered = sorted(a2_paths, key=day_of)
	days = [day_of(p) for p in ordered]
	radiance, cloud, zenith = [], [], []
	for path, day in zip(ordered, days, strict=True):
		r, c, z = read_pixels(path, rows, cols, a1_path=a1_paths.get(day))
		radiance.append(r)
		cloud.append(c)
		zenith.append(z)
	return ViirsTile(
		radiance=np.stack(radiance)[:, :, None],
		sensor_zenith=np.stack(zenith)[:, :, None],
		cloud_bits=np.stack(cloud)[:, :, None],
		month=np.asarray([d.month for d in days], dtype=np.uint8),
		timestamps=tuple(days),
	)
