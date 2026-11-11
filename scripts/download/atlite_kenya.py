# SPDX-License-Identifier: MIT
"""Prepare an atlite ERA5 cutout over Kenya for one year (plan §5.1 step 4).

Credentials come from CDSAPI_URL / CDSAPI_KEY (source `.env`). atlite issues one
CDS request per month and feature group, so a failure costs a month, and an
existing cutout file resumes rather than restarts.

Run: set -a; . ./.env; set +a; uv run --with atlite python scripts/download/atlite_kenya.py OUT.nc [YEAR]
"""

from __future__ import annotations

import sys
from pathlib import Path

import atlite

X = slice(33.5, 42.2)
Y = slice(-5.0, 5.6)


def main(argv: list[str]) -> int:
	out = Path(argv[0])
	year = argv[1] if len(argv) > 1 else "2023"
	out.parent.mkdir(parents=True, exist_ok=True)
	cutout = atlite.Cutout(path=str(out), module="era5", x=X, y=Y, time=year)
	cutout.prepare(features=["wind", "influx", "temperature"], show_progress=False, concurrent_requests=False)
	print(f"done: {out} {out.stat().st_size / 1e6:.0f} MB", flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
