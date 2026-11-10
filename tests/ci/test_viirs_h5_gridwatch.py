"""Black Marble HDF5 reading and GridWatch pixel-night truth, on real files."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from alea.outages import gridwatch, viirs_h5

N = 6
LAT = 10.0 - (np.arange(N) + 0.5) * (10.0 / N)  # descending, like the product
LON = -10.0 + (np.arange(N) + 0.5) * (10.0 / N)


def _granule(path: Path, *, radiance=None, qf=None, zenith=None) -> Path:
	with h5py.File(path, "w") as f:
		g = f.create_group(viirs_h5.GRID)
		if radiance is not None:
			g.create_dataset(viirs_h5.RADIANCE_LAYER, data=radiance.astype(np.float32))
		if qf is not None:
			g.create_dataset(viirs_h5.CLOUD_LAYER, data=qf.astype(np.uint16))
		if zenith is not None:
			g.create_dataset(viirs_h5.ZENITH_LAYER, data=zenith.astype(np.int16))
		g.create_dataset("lat", data=LAT)
		g.create_dataset("lon", data=LON)
	return path


def _qf(night=True, land=0b001, conf=0, shadow=0, cirrus=0, snow=0) -> int:
	return (0 if night else 1) | (land << 1) | (conf << 6) | (shadow << 8) | (cirrus << 9) | (snow << 10)


def test_land_without_desert_at_night_is_clear_not_blind():
	# Bit 1 is set for "land no desert". Reading bits 0-1 as cloud confidence made
	# this pixel cloudy; bits 6-7 are the confidence and here they say clear.
	qf = np.array([_qf(land=0b001, conf=0)], dtype=np.uint16)
	assert qf[0] & 0b11 != 0
	assert viirs_h5.decode_cloud_confidence(qf)[0] == 0


def test_cloud_confidence_levels_come_from_bits_6_and_7():
	qf = np.array([_qf(conf=c) for c in (0, 1, 2, 3)], dtype=np.uint16)
	assert viirs_h5.decode_cloud_confidence(qf).tolist() == [0, 1, 2, 3]


def test_shadow_cirrus_snow_day_and_fill_are_blind_whatever_the_confidence():
	cases = [_qf(shadow=1), _qf(cirrus=1), _qf(snow=1), _qf(night=False), viirs_h5.QF_FILL]
	out = viirs_h5.decode_cloud_confidence(np.array(cases, dtype=np.uint16))
	assert out.tolist() == [viirs_h5.BLIND] * 5


def test_each_blinding_bit_is_independent_of_the_others():
	clear = _qf()
	assert viirs_h5.decode_cloud_confidence(np.array([clear], dtype=np.uint16))[0] == 0
	for kw in ({"shadow": 1}, {"cirrus": 1}, {"snow": 1}):
		assert viirs_h5.decode_cloud_confidence(np.array([_qf(**kw)], dtype=np.uint16))[0] == 3


def test_a_fill_radiance_is_nan_and_blind(tmp_path: Path):
	rad = np.full((N, N), 5.0)
	rad[1, 2] = -999.9
	qf = np.full((N, N), _qf())
	path = _granule(tmp_path / "VNP46A2.A2022001.h17v08.002.x.h5", radiance=rad, qf=qf)
	r, c, z = viirs_h5.read_pixels(path, np.array([1, 0]), np.array([2, 0]))
	assert np.isnan(r[0]) and c[0] == viirs_h5.BLIND
	assert r[1] == 5.0 and c[1] == 0
	assert np.isnan(z).all()


def test_zenith_is_scaled_and_its_fill_is_nan(tmp_path: Path):
	rad = np.full((N, N), 5.0)
	qf = np.full((N, N), _qf())
	zen = np.full((N, N), 2500)
	zen[0, 0] = viirs_h5.ZENITH_FILL
	a2 = _granule(tmp_path / "a2.h5", radiance=rad, qf=qf)
	a1 = _granule(tmp_path / "a1.h5", zenith=zen)
	_, _, z = viirs_h5.read_pixels(a2, np.array([0, 1]), np.array([0, 1]), a1_path=a1)
	assert np.isnan(z[0]) and abs(z[1] - 25.0) < 1e-4


def test_a_site_tile_is_time_ordered_and_marks_a_missing_a1_day(tmp_path: Path):
	paths = []
	for doy, value in ((3, 3.0), (1, 1.0), (2, 2.0)):
		paths.append(
			_granule(
				tmp_path / f"VNP46A2.A2022{doy:03d}.h17v08.002.x.h5",
				radiance=np.full((N, N), value),
				qf=np.full((N, N), _qf()),
			)
		)
	a1 = {
		datetime(2022, 1, 1, tzinfo=UTC): _granule(tmp_path / "a1.h5", zenith=np.full((N, N), 1000))
	}
	rows, cols = np.array([0, 1, 2]), np.array([0, 1, 2])
	tile = viirs_h5.site_tile(paths, a1, rows, cols)
	assert tile.shape == (3, 3, 1)
	assert tile.radiance[:, 0, 0].tolist() == [1.0, 2.0, 3.0]
	assert tile.month.tolist() == [1, 1, 1]
	assert abs(tile.sensor_zenith[0, 0, 0] - 10.0) < 1e-4
	assert np.isnan(tile.sensor_zenith[1:]).all()


def test_nearest_index_handles_a_descending_axis():
	assert gridwatch.nearest_index(LAT, np.array([LAT[0], LAT[-1], LAT[2] + 0.01])).tolist() == [0, N - 1, 2]


def _readings(rows: list[tuple[int, float, float, str, object]]) -> pd.DataFrame:
	return pd.DataFrame(rows, columns=["site_id", "site_latitude", "site_longitude", "time", "is_powered"]).assign(
		night=date(2022, 1, 1), time=lambda d: pd.to_datetime(d["time"])
	)


def test_pixel_night_share_counts_only_reporting_readings_and_ignores_nulls():
	lat, lon = float(LAT[2]), float(LON[3])
	rows = [(1, lat, lon, "2022-01-01 01:00:00", False)] * 6 + [(2, lat, lon, "2022-01-01 01:00:00", True)] * 2
	rows += [(2, lat, lon, "2022-01-01 01:00:00", None)] * 50
	out = gridwatch.pixel_nights(_readings(rows), LAT, LON)
	assert len(out) == 1
	row = out.iloc[0]
	assert (row.row, row.col, row.n_sites, row.n_readings) == (2, 3, 2, 8)
	assert abs(row.unpowered_fraction - 0.75) < 1e-12


def test_a_site_outside_the_tile_is_dropped_not_clamped_to_the_edge():
	far = [(1, 40.0, 40.0, "2022-01-01 01:00:00", False)] * 10
	assert gridwatch.pixel_nights(_readings(far), LAT, LON).empty


def test_a_pixel_night_with_too_few_readings_is_dropped():
	few = [(1, float(LAT[0]), float(LON[0]), "2022-01-01 01:00:00", False)] * 4
	assert gridwatch.pixel_nights(_readings(few), LAT, LON, min_readings=5).empty


def test_the_outage_label_is_a_threshold_on_the_share():
	assert gridwatch.outage_label(np.array([0.0, 0.49, 0.5, 1.0])).tolist() == [0, 0, 1, 1]


def test_read_window_keeps_only_the_overpass_hours_of_the_named_days(tmp_path: Path):
	for day, hour in ((date(2022, 1, 1), 1), (date(2022, 1, 1), 12), (date(2022, 1, 2), 1)):
		d = tmp_path / f"day={day:%Y-%m-%d} 00%3A00%3A00"
		d.mkdir(exist_ok=True)
		table = pa.table(
			{
				"site_id": [1],
				"site_latitude": [5.6],
				"site_longitude": [-0.2],
				"time": [pd.Timestamp(f"{day} {hour:02d}:00:00")],
				"is_powered": [True],
			}
		)
		pq.write_table(table, d / f"part-{hour}.parquet")
	out = gridwatch.read_window(tmp_path, [date(2022, 1, 1)])
	assert len(out) == 1 and pd.Timestamp(out.time.iloc[0]).hour == 1
