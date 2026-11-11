# SPDX-License-Identifier: MIT
"""Hourly solar and wind capacity factors per Kenyan bus (plan §5.1 step 4, interim).

The plan's source is an ERA5 cutout through atlite. That request is blocked
here while the CDS queue holds the West Africa jobs, so this builds from the
Open-Meteo historical archive (ERA5-derived reanalysis, hourly, point queries),
saved raw under docs/research/milestone-data/open-meteo-kenya/. The capacity
factors come from two generic conversion models, not atlite's turbine and panel
libraries, so they are a stand-in with stated physics:

* solar: cell temperature = T + 0.03 * GHI; efficiency loss 0.4 %/K above 25 C;
  performance ratio 0.86; CF = GHI/1000 * loss * PR, clipped to [0, 1].
* wind: 100 m wind speed through a cubic curve, cut-in 3, rated 12, cut-out 25 m/s.

Run: uv run python scripts/build/kenya_profiles.py [PROCESSED_DIR]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "docs/research/milestone-data/open-meteo-kenya"
YEAR = 2023
BATCH = 4
URL = (
	"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
	f"&start_date={YEAR}-01-01&end_date={YEAR}-12-31&hourly=wind_speed_100m,shortwave_radiation,temperature_2m"
	"&wind_speed_unit=ms&timezone=UTC"
)


def fetch(points: list[tuple[str, float, float]]) -> dict[str, dict[str, np.ndarray]]:
	RAW.mkdir(parents=True, exist_ok=True)
	out: dict[str, dict[str, np.ndarray]] = {}
	for i in range(0, len(points), BATCH):
		chunk = points[i : i + BATCH]
		cache = RAW / f"batch_{i // BATCH:03d}.json"
		if not cache.exists():
			url = URL.format(lat=",".join(f"{p[2]:.4f}" for p in chunk), lon=",".join(f"{p[1]:.4f}" for p in chunk))
			for attempt in range(8):
				try:
					req = urllib.request.Request(url, headers={"User-Agent": "alea-research/0.1"})
					body = urllib.request.urlopen(req, timeout=120).read()
					json.loads(body)
					cache.write_bytes(body)
					break
				except Exception:  # noqa: BLE001
					time.sleep(20 * (attempt + 1))
			else:
				raise SystemExit(f"batch {i // BATCH} failed after 8 attempts")
			time.sleep(2)
		data = json.loads(cache.read_text())
		data = data if isinstance(data, list) else [data]
		assert len(data) == len(chunk), f"batch {i // BATCH}: {len(data)} results for {len(chunk)} points"
		for (bus, _, _), d in zip(chunk, data, strict=True):
			out[bus] = {k: np.array(v, dtype=float) for k, v in d["hourly"].items() if k != "time"}
	return out


def solar_cf(ghi: np.ndarray, temp: np.ndarray) -> np.ndarray:
	cell = temp + 0.03 * ghi
	loss = 1.0 - 0.004 * np.maximum(cell - 25.0, 0.0)
	return np.clip(ghi / 1000.0 * loss * 0.86, 0.0, 1.0)


def wind_cf(v: np.ndarray, cut_in: float = 3.0, rated: float = 12.0, cut_out: float = 25.0) -> np.ndarray:
	cf = np.clip((v**3 - cut_in**3) / (rated**3 - cut_in**3), 0.0, 1.0)
	return np.where(v >= cut_out, 0.0, cf)


def main(argv: list[str]) -> int:
	warnings.filterwarnings("ignore")
	from alea.io.artefacts import write_artefact
	from alea.planning.topology import build_topology
	from alea.provenance.models import Basis, DerivedProvenance

	out = Path(argv[0]) if argv else ROOT / "data/processed"
	net, _, _ = build_topology(pd.read_parquet(out / "topology.parquet"), voltage_kv_min=66.0, snap_tolerance_m=500.0)
	points = [(str(b), float(r.lon), float(r.lat)) for b, r in net.buses[["lon", "lat"]].iterrows()]
	raw = fetch(points)
	idx = pd.date_range(f"{YEAR}-01-01", f"{YEAR}-12-31 23:00", freq="h")
	buses = [p[0] for p in points]
	assert all(len(raw[b]["wind_speed_100m"]) == len(idx) for b in buses), "hour count mismatch"
	assert all(np.isfinite(raw[b][k]).all() for b in buses for k in raw[b]), "NaN in the weather series"
	solar = np.stack([solar_cf(raw[b]["shortwave_radiation"], raw[b]["temperature_2m"]) for b in buses])
	wind = np.stack([wind_cf(raw[b]["wind_speed_100m"]) for b in buses])
	cube = xr.Dataset(
		{"capacity_factor": (("carrier", "bus", "time"), np.stack([solar, wind]).astype("float32"))},
		coords={"carrier": ["solar", "onwind"], "bus": buses, "time": idx.to_numpy()},
	)
	prov = DerivedProvenance(
		source_id="open-meteo-era5-kenya-2023",
		inputs=["sha256:open-meteo-archive:kenya-2023"],
		basis=Basis.PROXY,
		uncertainty=0.2,
		uncertainty_basis="generic conversion curves, not atlite turbine/panel models",
		parameters={"year": YEAR, "points": len(buses)},
		notes="Interim stand-in for an atlite ERA5 cutout; see scripts/build/kenya_profiles.py.",
	)
	write_artefact(out / "renewable_profiles.nc", cube, prov, format="netcdf")
	print(f"solar mean CF {solar.mean():.3f} (range of buses {solar.mean(1).min():.3f}-{solar.mean(1).max():.3f}); wind mean CF {wind.mean():.3f} (buses {wind.mean(1).min():.3f}-{wind.mean(1).max():.3f})")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
