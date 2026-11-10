# SPDX-License-Identifier: MIT
"""GridWatch ground truth, reduced to the unit the VIIRS detector is scored on.

A GridWatch sensor sits in one household and reports ``is_powered`` every two
minutes. A VIIRS pixel is ~460 m across and sees one overpass a night, so the
comparable truth is *pixel-night*: of the sensors inside the pixel, what share
were unpowered during the overpass window. A single unplugged sensor is a
household event, not a pixel one, which is why the label is a share with a
stated threshold rather than "any sensor off".

``is_powered`` is read as recorded. Rows where it is null count as no reading,
not as powered: a silent sensor is not evidence of supply.
"""

from __future__ import annotations

import glob
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numpy.typing import NDArray

COLUMNS = ("site_id", "site_latitude", "site_longitude", "time", "is_powered")

OVERPASS_WINDOW_UTC = ("00:00", "03:00")
"""VIIRS crosses Ghana near 01:30 local, which is UTC there. The window is wide
enough to hold the overpass and narrow enough that it is still one night."""


def day_files(root: str | Path, day: date) -> list[str]:
	"""Partition files for one day. The partition key is a percent-encoded string."""
	pattern = f"{glob.escape(str(root))}/day={day:%Y-%m-%d}*/*.parquet"
	return sorted(glob.glob(pattern))


def read_window(
	root: str | Path,
	days: Sequence[date],
	*,
	window: tuple[str, str] = OVERPASS_WINDOW_UTC,
) -> pd.DataFrame:
	"""Readings inside the overpass window, one row per reading, for the given days."""
	frames: list[pd.DataFrame] = []
	for day in days:
		for path in day_files(root, day):
			frame = pq.read_table(path, columns=list(COLUMNS)).to_pandas()
			if frame.empty:
				continue
			times = pd.DatetimeIndex(frame["time"])
			frame = frame[(times.strftime("%H:%M") >= window[0]) & (times.strftime("%H:%M") < window[1])]
			if not frame.empty:
				frames.append(frame.assign(night=day))
	if not frames:
		return pd.DataFrame(columns=[*COLUMNS, "night"])
	return pd.concat(frames, ignore_index=True)


def nearest_index(axis: NDArray[np.float64], values: NDArray[np.float64]) -> NDArray[np.int64]:
	"""Index of the nearest axis cell, for an axis that is monotone either way."""
	axis = np.asarray(axis, dtype=float)
	values = np.asarray(values, dtype=float)
	order = np.argsort(axis)
	pos = np.searchsorted(axis[order], values)
	pos = np.clip(pos, 1, len(axis) - 1)
	left, right = axis[order][pos - 1], axis[order][pos]
	pick = np.where(np.abs(values - left) <= np.abs(right - values), pos - 1, pos)
	return order[pick].astype(np.int64)


def pixel_nights(
	readings: pd.DataFrame,
	lat_axis: NDArray[np.float64],
	lon_axis: NDArray[np.float64],
	*,
	min_readings: int = 5,
) -> pd.DataFrame:
	"""Aggregate readings to (night, row, col): sensors, readings, unpowered share.

	Sites outside the tile are dropped, not clamped to its edge: ``nearest_index``
	always returns a cell, so without the bounds test a sensor 50 km off the tile
	would be scored against the edge pixel.
	"""
	columns = ["night", "row", "col", "n_sites", "n_readings", "unpowered_fraction"]
	if readings.empty:
		return pd.DataFrame(columns=columns)
	frame = readings.dropna(subset=["is_powered", "site_latitude", "site_longitude"]).copy()
	half_lat = abs(float(lat_axis[1] - lat_axis[0])) / 2
	half_lon = abs(float(lon_axis[1] - lon_axis[0])) / 2
	inside = (
		(frame["site_latitude"] >= lat_axis.min() - half_lat)
		& (frame["site_latitude"] <= lat_axis.max() + half_lat)
		& (frame["site_longitude"] >= lon_axis.min() - half_lon)
		& (frame["site_longitude"] <= lon_axis.max() + half_lon)
	)
	frame = frame[inside]
	if frame.empty:
		return pd.DataFrame(columns=columns)
	frame["row"] = nearest_index(lat_axis, frame["site_latitude"].to_numpy())
	frame["col"] = nearest_index(lon_axis, frame["site_longitude"].to_numpy())
	frame["off"] = ~frame["is_powered"].astype(bool)
	grouped = frame.groupby(["night", "row", "col"]).agg(
		n_sites=("site_id", "nunique"), n_readings=("off", "size"), unpowered_fraction=("off", "mean")
	)
	out = grouped.reset_index()
	return out[out["n_readings"] >= min_readings].reset_index(drop=True)[columns]


def outage_label(unpowered_fraction: NDArray[np.float64], *, threshold: float = 0.5) -> NDArray[np.int64]:
	"""Pixel-night outage: at least ``threshold`` of reporting readings unpowered."""
	return (np.asarray(unpowered_fraction, dtype=float) >= threshold).astype(np.int64)
