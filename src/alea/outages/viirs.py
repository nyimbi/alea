# SPDX-License-Identifier: MIT
"""VIIRS VNP46A2 nighttime-lights outage detection.

The detector asks a narrow question: *was a normally-lit pixel dark at this
observation?* It answers it with a per-(pixel, viewing-zenith-angle bin,
calendar month) first-quartile baseline and a threshold, both of which are
config and both of which travel in provenance.

Three specification defects are fixed here rather than inherited:

1. **Cloud polarity.** ``spec4-base.md`` writes ``& 0b11 != 0`` and
   ``spec4-data-collection.md`` writes ``& 0b11 == 0``. The correct reading is
   that bits 0-1 encode cloud confidence (00 confident clear .. 11 confident
   cloudy) and only 00 is safe. The kernel pins ``max_cloud_confidence=0``;
   this module passes the config value and refuses a wider ceiling by default.

2. **Cloud is *unknown*, not *lit*.** A cloudy pixel becomes NaN, never 0. NaN
   is excluded from a mean and 0 pulls it down, so collapsing the two makes the
   detector report outages wherever it is cloudy. The kernel returns NaN and
   ``stream_zones`` treats a zone-hour with no clear pixels as NaN, not zero.

3. **The gap-filled band.** Detection reads ``DNB_BRDF_Corrected_NTL``, the
   observed band. The gap-filled band interpolates across cloudy observations,
   so a cloud becomes a plausible radiance and the detector sees "no outage"
   exactly where it is blind. ``extract_tile`` refuses the gap-filled band and
   scans the dataset for it.

The Python layer streams granules: the detection pass holds one tile plus the
running zone series, never the archive. See 07-layer4 §2.4.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from alea._core import aggregate_to_zones, detect_outages, vza_baseline
from alea.logging import get_logger
from alea.outages.views import PredictiveConfig, ViirsConfig

logger = get_logger(__name__)

# Band names, pinned. VNP46A2 variable names.
RADIANCE_BAND = "DNB_BRDF_Corrected_NTL"
"""The observed, BRDF-corrected nighttime radiance, nW cm^-2 sr^-1."""

GAP_FILLED_BAND = "DNB_BRDF_Corrected_NTL_Gap_Filled"
"""Interpolated across cloudy observations. **Never** used for detection."""

CLOUD_MASK_BAND = "QF_Cloud_Mask"
SENSOR_ZENITH_BAND = "Sensor_Zenith"

MAX_CLOUD_CONFIDENCE = 0
"""Keep only confident-clear (bits 0-1 == 0b00).

Bits 0-1 of ``QF_Cloud_Mask`` encode cloud confidence: 00 confident clear, 01
probably clear, 10 probably cloudy, 11 confident cloudy. The specification
writes both ``== 0`` and ``!= 0``; this constant is the pinned answer, and the
kernel takes it as an argument so a caller cannot drift from it without saying
so. See 07-layer4 §2.2.
"""

# The angular range the VZA bins span. 07-layer4 §2.1 says "5 deg bins to 70
# deg", but the compiled kernel bins over 0..90 deg (`n_bins = ceil(90 /
# bin_size)`, alea-rasters lib.rs) and is the authority the Python layer must
# agree with: a bin count that disagrees makes every baseline lookup read the
# wrong cell. The discrepancy is recorded here rather than papered over, and
# `n_vza_bins` derives the count the kernel will actually produce.
VZA_MAX_DEG = 90.0
N_MONTHS = 12


@dataclass(frozen=True)
class ViirsTile:
	"""One granule, extracted to the bands the detector uses.

	Holding the arrays rather than the dataset is what makes the pass streaming:
	a caller opens a granule, extracts a tile, detects, and drops the dataset,
	so the working set is one tile rather than a country-year of granules.
	"""

	radiance: NDArray[np.float32]
	"""``[time, y, x]`` observed BRDF-corrected radiance."""

	sensor_zenith: NDArray[np.float32]
	"""``[time, y, x]`` viewing zenith angle, degrees."""

	cloud_bits: NDArray[np.uint8]
	"""``[time, y, x]`` ``QF_Cloud_Mask``."""

	month: NDArray[np.uint8]
	"""``[time]`` calendar month, 1..12."""

	timestamps: tuple[datetime, ...]
	"""``[time]`` observation instants, UTC. Provenance, not a feature."""

	@property
	def shape(self) -> tuple[int, int, int]:
		return self.radiance.shape

	def __post_init__(self) -> None:
		if self.radiance.shape != self.sensor_zenith.shape:
			raise ValueError(
				f"radiance {self.radiance.shape} and sensor_zenith "
				f"{self.sensor_zenith.shape} must have the same shape"
			)
		if self.radiance.shape != self.cloud_bits.shape:
			raise ValueError(
				f"radiance {self.radiance.shape} and cloud_bits "
				f"{self.cloud_bits.shape} must have the same shape"
			)
		if self.month.shape != (self.radiance.shape[0],):
			raise ValueError(
				f"month must be [time] = ({self.radiance.shape[0]},), got {self.month.shape}"
			)
		if len(self.timestamps) != self.radiance.shape[0]:
			raise ValueError(
				f"{len(self.timestamps)} timestamps for {self.radiance.shape[0]} "
				f"time steps"
			)
		if self.month.size and (self.month.min() < 1 or self.month.max() > N_MONTHS):
			raise ValueError(f"month must be 1..12, got [{self.month.min()}, {self.month.max()}]")


def n_vza_bins(bin_size_deg: float) -> int:
	"""How many VZA bins a bin size produces, matching the kernel exactly.

	``ceil(90 / bin_size)``, so a partial final bin is kept rather than dropped.
	Dropping the remainder is how a detector loses the high-zenith pixels that
	are most likely to be misread. The value must equal the kernel's own
	``n_bins`` or every baseline lookup indexes the wrong cell; a test asserts
	the two agree on the returned shape.
	"""
	if bin_size_deg <= 0:
		raise ValueError(f"bin_size_deg must be positive, got {bin_size_deg}")
	return int(np.ceil(VZA_MAX_DEG / bin_size_deg))


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def _variable_names(dataset: Any) -> list[str]:
	return [str(name) for name in dataset.data_vars]


def assert_no_gap_filled_band(names: Iterable[str]) -> None:
	"""Refuse a detection path that has a gap-filled band in it.

	07-layer4 §2.3: "A test asserts the gap-filled band name appears nowhere in
	the detection path." The check is by substring so a renamed-but-equivalent
	band (``..._gapfilled``, ``..._gap_filled``) is still caught.
	"""
	offenders = [name for name in names if "gap" in name.lower() and "fill" in name.lower()]
	if offenders:
		raise ValueError(
			f"detection must not read the gap-filled band: {offenders}. It "
			f"interpolates across cloudy observations, so a cloud reads as a "
			f"plausible radiance and the detector sees 'no outage' where it is "
			f"blind (07-layer4 §2.3)"
		)


def extract_tile(
	dataset: Any,
	*,
	band: str = RADIANCE_BAND,
	cloud_band: str = CLOUD_MASK_BAND,
	zenith_band: str = SENSOR_ZENITH_BAND,
	time_dim: str = "time",
) -> ViirsTile:
	"""Pull the detection bands out of an open VNP46A2 dataset.

	``dataset`` is any xarray-like object exposing ``data_vars`` and
	``__getitem__`` returning something with ``.values``; the granule is read
	here and released by the caller, which is what keeps the pass streaming.
	"""
	names = _variable_names(dataset)
	assert_no_gap_filled_band(names)
	if band == GAP_FILLED_BAND:
		raise ValueError(
			f"{GAP_FILLED_BAND!r} is the gap-filled band and must never be the "
			f"detection source; use {RADIANCE_BAND!r}"
		)
	for required in (band, cloud_band, zenith_band):
		if required not in names:
			raise KeyError(f"dataset has no variable {required!r}; it holds {names}")

	radiance = np.ascontiguousarray(dataset[band].values, dtype=np.float32)
	zenith = np.ascontiguousarray(dataset[zenith_band].values, dtype=np.float32)
	cloud = np.ascontiguousarray(dataset[cloud_band].values, dtype=np.uint8)
	if radiance.ndim != 3:
		raise ValueError(f"radiance must be [time, y, x], got shape {radiance.shape}")

	time = dataset[time_dim].values if time_dim in getattr(dataset, "coords", {}) else None
	months = _months_from_time(time, radiance.shape[0])
	timestamps = _timestamps_from_time(time, radiance.shape[0])

	return ViirsTile(
		radiance=radiance,
		sensor_zenith=zenith,
		cloud_bits=cloud,
		month=months,
		timestamps=timestamps,
	)


def _months_from_time(time: Any, n: int) -> NDArray[np.uint8]:
	"""Calendar months from a coordinate, or a single-month fallback.

	A missing time coordinate is not silently month-1: the baseline is binned
	by month, so a wrong month biases every baseline. The fallback is a
	single-month tile only when there is exactly one step, and otherwise
	raises.
	"""
	if time is None:
		if n == 1:
			return np.array([1], dtype=np.uint8)
		raise ValueError(
			"a tile with more than one time step needs a time coordinate to "
			"derive its months; the baseline is binned by month"
		)
	array = np.asarray(time)
	months = np.array(
		[(getattr(value, "month", None) or _month_from_iso(value)) for value in array],
		dtype=np.uint8,
	)
	if months.shape != (n,):
		raise ValueError(f"derived {months.shape} months for {n} time steps")
	return months


def _month_from_iso(value: Any) -> int:
	text = str(value)
	return int(text[5:7])


def _timestamps_from_time(time: Any, n: int) -> tuple[datetime, ...]:
	if time is None:
		raise ValueError(
			"a VIIRS tile needs observation instants: a detection result whose "
			"times are unknown cannot be joined to ground truth"
		)
	from datetime import UTC

	out: list[datetime] = []
	for value in np.asarray(time):
		stamp = value if isinstance(value, datetime) else _parse_datetime(value)
		if stamp.tzinfo is None:
			stamp = stamp.replace(tzinfo=UTC)
		out.append(stamp)
	if len(out) != n:
		raise ValueError(f"{len(out)} timestamps for {n} time steps")
	return tuple(out)


def _parse_datetime(value: Any) -> datetime:
	import pandas as pd

	return pd.Timestamp(value).to_pydatetime()


def read_granule(path: str | Path, *, band: str = RADIANCE_BAND) -> ViirsTile:
	"""Open one NetCDF granule, extract the detection bands, release the file.

	Deliberately eager: the dataset is opened, read, and closed inside the call
	so that a caller iterating thousands of granules never accumulates open
	file handles.
	"""
	import xarray as xr

	with xr.open_dataset(path) as dataset:
		tile = extract_tile(dataset, band=band)
	# Force the arrays out of the lazily-opened file before it closes.
	return ViirsTile(
		radiance=tile.radiance.copy(),
		sensor_zenith=tile.sensor_zenith.copy(),
		cloud_bits=tile.cloud_bits.copy(),
		month=tile.month.copy(),
		timestamps=tile.timestamps,
	)


def iter_tiles(paths: Iterable[str | Path], *, band: str = RADIANCE_BAND) -> Iterator[ViirsTile]:
	"""Yield tiles one granule at a time. The streaming entry point."""
	for path in paths:
		yield read_granule(path, band=band)


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


def build_baseline(
	tiles: Sequence[ViirsTile],
	config: ViirsConfig | None = None,
) -> NDArray[np.float32]:
	"""Per-(month, VZA bin, y, x) first-quartile baseline.

	``tiles`` are stacked along time, so they must share a (y, x) grid — the
	same tile geometry over the baseline reference period. Returns
	``[12, n_bins, y, x]``, NaN where a (pixel, bin, month) cell had no
	observation.

	Memory is the stack, not the archive: the caller decides how many granules
	form the reference period. Building the baseline over a decade of daily
	granules in one call is not what this is for — per 03-rust-core §3.2 the
	baseline is computed once and reused across detection runs, so a
	representative reference period is the intended input.
	"""
	assert len(tiles) > 0, "a baseline needs at least one tile"
	cfg = config or ViirsConfig()
	grid = tiles[0].shape[1:]
	for index, tile in enumerate(tiles):
		if tile.shape[1:] != grid:
			raise ValueError(
				f"tile {index} has grid {tile.shape[1:]}, expected {grid}; a "
				f"baseline is per tile geometry and cannot mix grids"
			)

	radiance = np.concatenate([tile.radiance for tile in tiles], axis=0)
	zenith = np.concatenate([tile.sensor_zenith for tile in tiles], axis=0)
	month = np.concatenate([tile.month for tile in tiles], axis=0)

	baseline = vza_baseline(
		radiance,
		zenith,
		month,
		bin_size_deg=cfg.bin_size_deg,
		quantile=cfg.baseline_quantile,
	)
	assert baseline.shape == (N_MONTHS, n_vza_bins(cfg.bin_size_deg), *grid), (
		f"kernel returned {baseline.shape} for grid {grid}"
	)
	logger.info(
		"viirs.baseline",
		tiles=len(tiles),
		observations=int(radiance.shape[0]),
		grid=grid,
		quantile=cfg.baseline_quantile,
		bin_size_deg=cfg.bin_size_deg,
	)
	return baseline


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def detect_tile(
	tile: ViirsTile,
	baseline: NDArray[np.float32],
	config: ViirsConfig | None = None,
) -> NDArray[np.float32]:
	"""Per-observation anomaly for one tile: 1.0 flagged, 0.0 clear, NaN blind.

	The kernel is the authority on cloud semantics; this wrapper asserts the
	ceiling is the pinned one and passes the config through.
	"""
	cfg = config or ViirsConfig()
	# The baseline is [12, n_bins, y, x], so its spatial grid is the last two
	# axes, not everything after the month axis.
	if baseline.shape[2:] != tile.shape[1:]:
		raise ValueError(
			f"baseline grid {baseline.shape[2:]} does not match tile grid "
			f"{tile.shape[1:]}; a baseline from another tile geometry is a "
			f"different baseline"
		)
	expected = (N_MONTHS, n_vza_bins(cfg.bin_size_deg), *tile.shape[1:])
	if baseline.shape != expected:
		raise ValueError(
			f"baseline shape {baseline.shape} does not match the kernel's "
			f"{expected} for this bin size; the Python bin count and the kernel "
			f"disagree and every lookup would index the wrong cell"
		)
	if cfg.max_cloud_confidence != MAX_CLOUD_CONFIDENCE:
		# Not refused outright — the ceiling is config — but a wider ceiling
		# admits probably-cloudy pixels, which is the defect the plan pins
		# against, so it must be visible in the log.
		logger.warning(
			"viirs.wide_cloud_ceiling",
			max_cloud_confidence=cfg.max_cloud_confidence,
			pinned=MAX_CLOUD_CONFIDENCE,
		)

	anomaly = detect_outages(
		tile.radiance,
		baseline,
		tile.month,
		tile.sensor_zenith,
		tile.cloud_bits,
		bin_size_deg=cfg.bin_size_deg,
		threshold=cfg.detection_threshold,
		max_cloud_confidence=cfg.max_cloud_confidence,
	)
	assert anomaly.shape == tile.shape, f"kernel returned {anomaly.shape} for {tile.shape}"
	return anomaly


def zone_series(
	tile: ViirsTile,
	anomaly: NDArray[np.float32],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
) -> NDArray[np.float32]:
	"""Flagged *fraction of clear pixels* per (time, zone) for one tile.

	The denominator is clear pixels, not all pixels: a zone-hour that was
	entirely cloudy returns NaN, which a consumer must treat as "no
	information". Dividing by all pixels would make a cloudy hour read as a
	calm one.
	"""
	assert zone_ids.shape == tile.shape[1:], (
		f"zone_ids {zone_ids.shape} must match the tile grid {tile.shape[1:]}"
	)
	series = aggregate_to_zones(anomaly, zone_ids, n_zones)
	assert series.shape == (tile.shape[0], n_zones), (
		f"kernel returned {series.shape} for ({tile.shape[0]}, {n_zones})"
	)
	return series


def stream_zones(
	paths: Iterable[str | Path],
	baseline: NDArray[np.float32],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
	config: ViirsConfig | None = None,
) -> tuple[NDArray[np.float32], list[datetime]]:
	"""Detect across a granule sequence, returning ``[time, n_zones]``.

	The working set is one tile plus the growing zone series; the granules are
	read and released one at a time. Rows are ordered by the sequence the
	caller supplies, and their instants are returned so a result can be joined
	to ground truth.
	"""
	cfg = config or ViirsConfig()
	rows: list[NDArray[np.float32]] = []
	times: list[datetime] = []
	for path in paths:
		tile = read_granule(path, band=cfg.radiance_band)
		anomaly = detect_tile(tile, baseline, cfg)
		rows.append(zone_series(tile, anomaly, zone_ids, n_zones))
		times.extend(tile.timestamps)

	if not rows:
		raise ValueError("no granules supplied; an empty detection run is not a result")
	series = np.concatenate(rows, axis=0)
	assert series.shape == (len(times), n_zones)
	logger.info("viirs.stream_zones", granules=len(rows), steps=series.shape[0], zones=n_zones)
	return series, times


def detect_tiles(
	tiles: Sequence[ViirsTile],
	baseline: NDArray[np.float32],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
	config: ViirsConfig | None = None,
) -> tuple[NDArray[np.float32], list[datetime]]:
	"""In-memory equivalent of :func:`stream_zones`, for a bounded tile set.

	Used where the tiles are already held (a fixture, a single-granule test);
	the streaming path is the one that scales.
	"""
	cfg = config or ViirsConfig()
	if not tiles:
		raise ValueError("no tiles supplied")
	rows = [
		zone_series(tile, detect_tile(tile, baseline, cfg), zone_ids, n_zones) for tile in tiles
	]
	times = [stamp for tile in tiles for stamp in tile.timestamps]
	return np.concatenate(rows, axis=0), times


def zone_ids_from_labels(labels: NDArray[Any], *, background: int = 0) -> NDArray[np.uint32]:
	"""Convert a label raster to contiguous zone indices, reserving 0.

	Zone 0 is reserved for "outside every zone" and is excluded from the
	aggregation by giving it index 0 — the kernel counts zone 0 like any other,
	so a caller that wants a masked zone passes ``n_zones`` one larger than the
	labels and ignores column 0. Keeping the convention here means every caller
	shares it.
	"""
	array = np.asarray(labels)
	if array.ndim != 2:
		raise ValueError(f"labels must be [y, x], got shape {array.shape}")
	out = np.zeros(array.shape, dtype=np.uint32)
	mask = array != background
	unique = np.unique(array[mask])
	lookup = {value: index + 1 for index, value in enumerate(unique.tolist())}
	if mask.any():
		out[mask] = np.vectorize(lookup.__getitem__)(array[mask]).astype(np.uint32)
	return out


def detection_parameters(config: ViirsConfig | None = None) -> dict[str, Any]:
	"""The parameters an outage result is a function of, for provenance."""
	cfg = config or ViirsConfig()
	return {
		"bin_size_deg": cfg.bin_size_deg,
		"baseline_quantile": cfg.baseline_quantile,
		"detection_threshold": cfg.detection_threshold,
		"max_cloud_confidence": cfg.max_cloud_confidence,
		"radiance_band": cfg.radiance_band,
		"n_vza_bins": n_vza_bins(cfg.bin_size_deg),
	}


def parameters_from_config(config: PredictiveConfig) -> dict[str, Any]:
	"""Every Layer-4a parameter, flattened for an artefact sidecar."""
	return config.parameters()


__all__ = [
	"CLOUD_MASK_BAND",
	"GAP_FILLED_BAND",
	"MAX_CLOUD_CONFIDENCE",
	"RADIANCE_BAND",
	"SENSOR_ZENITH_BAND",
	"VZA_MAX_DEG",
	"ViirsTile",
	"assert_no_gap_filled_band",
	"build_baseline",
	"detect_tile",
	"detect_tiles",
	"detection_parameters",
	"extract_tile",
	"iter_tiles",
	"n_vza_bins",
	"parameters_from_config",
	"read_granule",
	"stream_zones",
	"zone_ids_from_labels",
	"zone_series",
]
