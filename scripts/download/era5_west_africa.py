# SPDX-License-Identifier: MIT
"""Download ERA5 single-level hourly fields for West Africa, one request per year.

Credentials come from CDSAPI_URL / CDSAPI_KEY (source `.env`). The request is the
one supplied for the weather_forecasting target (2m temperature and the
instantaneous large-scale precipitation fraction, 2019-2024, area N16 W-12 S3.5
E8.25), split by year so each request stays under the CDS cost limit and a
failure costs one year, not six. Existing files are skipped.

Run: uv run --with cdsapi python scripts/download/era5_west_africa.py OUT_DIR
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cdsapi

DATASET = "reanalysis-era5-single-levels"
VARIABLES = ["2m_temperature", "instantaneous_large_scale_surface_precipitation_fraction"]
AREA = [16, -12, 3.5, 8.25]


def _one(args: tuple[int, Path]) -> str:
	year, out = args
	dest = out / f"era5_west_africa_{year}.zip"
	if dest.exists() and dest.stat().st_size > 0:
		return f"{year}: present"
	request = {
		"product_type": ["reanalysis"],
		"variable": VARIABLES,
		"year": [str(year)],
		"month": [f"{m:02d}" for m in range(1, 13)],
		"day": [f"{d:02d}" for d in range(1, 32)],
		"time": [f"{h:02d}:00" for h in range(24)],
		"data_format": "grib",
		"download_format": "zip",
		"area": AREA,
	}
	tmp = dest.with_suffix(".part")
	cdsapi.Client(quiet=True).retrieve(DATASET, request).download(str(tmp))
	tmp.replace(dest)
	return f"{year}: {dest.stat().st_size / 1e6:.1f} MB"


def main(argv: list[str]) -> int:
	out = Path(argv[0])
	out.mkdir(parents=True, exist_ok=True)
	with ThreadPoolExecutor(2) as pool:
		for line in pool.map(_one, [(y, out) for y in range(2019, 2025)]):
			print(line, flush=True)
	print("done", flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
