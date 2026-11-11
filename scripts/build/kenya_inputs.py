# SPDX-License-Identifier: MIT
"""Kenya fleet and hourly demand artefacts for the Layer 1 build (plan §5.1).

Fleet: WRI Global Power Plant Database v1.3 (CC BY 4.0), KEN rows, archived under
docs/research/milestone-data/gppd/. It covers 23 plants; Kenya's installed
capacity per KNBS 2024 Economic Survey is 3,243.6 MW (2023), so coverage is
reported against that and not assumed.

Demand: national annual consumption 10,320.6 GWh (2023, KNBS 2024 Economic Survey
via Kenyan Wall Street), spread over buses by approximate 2019-census population
of the nearest large town, with a stylised hourly shape. Both the town
populations and the shape are modelling assumptions, not measurements; they are
written into the artefact's `notes` file next to the data.

Run: uv run python scripts/build/kenya_inputs.py [OUT_DIR]
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GPPD = ROOT / "docs/research/milestone-data/gppd/global_power_plant_database.csv"
CARRIER = {"Geothermal": "geothermal", "Hydro": "hydro", "Oil": "oil", "Solar": "solar", "Wind": "onwind"}
LIFETIME = {"geothermal": 30, "hydro": 60, "oil": 25, "solar": 25, "onwind": 25}
INSTALLED_MW_2023 = 3243.6
ANNUAL_GWH = 10320.6
YEAR = 2023
# (name, lon, lat, 2019-census county population; from memory, unverified)
TOWNS = [
	("Nairobi", 36.82, -1.29, 4_397_073), ("Mombasa", 39.67, -4.04, 1_208_333),
	("Kisumu", 34.76, -0.09, 1_155_574), ("Nakuru", 36.07, -0.30, 2_162_202),
	("Eldoret", 35.27, 0.51, 1_163_186), ("Thika", 37.07, -1.03, 2_417_735),
	("Machakos", 37.26, -1.52, 1_421_932), ("Meru", 37.65, 0.05, 1_545_714),
	("Kakamega", 34.75, 0.28, 1_867_579), ("Nyeri", 36.95, -0.42, 759_164),
	("Kisii", 34.77, -0.68, 1_266_860), ("Malindi", 40.12, -3.22, 1_453_787),
]


def fleet() -> pd.DataFrame:
	d = pd.read_csv(GPPD, low_memory=False)
	k = d[d.country == "KEN"].copy()
	out = pd.DataFrame(
		{
			"plant_id": k.gppd_idnr, "name": k.name, "carrier": k.primary_fuel.map(CARRIER),
			"capacity_mw": k.capacity_mw.astype(float), "lon": k.longitude, "lat": k.latitude,
			"commissioning_year": k.commissioning_year.fillna(2010).astype(int),
		}
	)
	out["lifetime_years"] = out.carrier.map(LIFETIME).astype(int)
	assert out.carrier.notna().all(), "unmapped fuel"
	return out.reset_index(drop=True)


def shape(index: pd.DatetimeIndex) -> np.ndarray:
	"""Stylised Kenyan load shape: evening peak ~19:00, morning shoulder, mild seasonality."""
	h = index.hour.to_numpy()
	daily = 0.72 + 0.12 * np.exp(-((h - 8) ** 2) / 8) + 0.46 * np.exp(-((h - 19) ** 2) / 5)
	season = 1.0 + 0.03 * np.cos(2 * np.pi * (index.dayofyear.to_numpy() - 45) / 365)
	weekend = np.where(index.dayofweek.to_numpy() >= 5, 0.93, 1.0)
	return daily * season * weekend


def demand(buses: pd.DataFrame) -> pd.DataFrame:
	idx = pd.date_range(f"{YEAR}-01-01", f"{YEAR}-12-31 23:00", freq="h")
	towns = pd.DataFrame(TOWNS, columns=["town", "lon", "lat", "pop"])
	dist = np.hypot(
		(buses.lon.to_numpy()[:, None] - towns.lon.to_numpy()[None]) * np.cos(np.radians(buses.lat.to_numpy()[:, None])),
		buses.lat.to_numpy()[:, None] - towns.lat.to_numpy()[None],
	)
	owner = dist.argmin(axis=1)
	weight = np.zeros(len(buses))
	for t in range(len(towns)):
		members = np.where(owner == t)[0]
		if len(members):
			weight[members] = towns["pop"][t] / len(members)
	weight /= weight.sum()
	s = shape(idx)
	total_mwh = ANNUAL_GWH * 1000.0
	national = s * total_mwh / s.sum()
	frame = pd.DataFrame(
		{
			"bus_id": np.repeat(buses.index.to_numpy(), len(idx)),
			"timestamp_utc": np.tile(idx.strftime("%Y-%m-%dT%H:%M:%S"), len(buses)),
			"demand_mw": (weight[:, None] * national[None, :]).ravel(),
		}
	)
	return frame


TECH_DATA = ROOT / "docs/research/milestone-data/technology-data"
COST_NAMES = {
	"solar": "solar", "onwind": "onwind", "hydro": "hydro", "ror": "ror", "gas": "OCGT",
	"coal": "coal", "oil": "oil", "nuclear": "nuclear", "biomass": "biomass",
}
EUR_USD = 1.14  # 2020 average, the technology-data currency year; a conversion assumption
"""Geothermal electricity has no capex row in technology-data (its `geothermal` rows are
heat), so it gets no cost and no expansion candidate."""


def costs() -> pd.DataFrame:
	rows = []
	for year in (2030, 2040, 2050):
		d = pd.read_csv(TECH_DATA / f"costs_{year}.csv")
		inv = d[d.parameter == "investment"].set_index("technology").value
		life = d[d.parameter == "lifetime"].set_index("technology").value
		for carrier, name in COST_NAMES.items():
			rows.append({"technology": carrier, "year": year, "capex_usd_per_kw": float(inv[name]) * EUR_USD, "lifetime_years": float(life[name])})
	return pd.DataFrame(rows)


def main(argv: list[str]) -> int:
	warnings.filterwarnings("ignore")
	from alea.io.artefacts import write_artefact
	from alea.planning.topology import build_topology
	from alea.provenance.models import Basis, DerivedProvenance

	def _prov(source_id: str, notes: str, basis: Basis, unc: float) -> DerivedProvenance:
		return DerivedProvenance(
			source_id=source_id, inputs=[f"sha256:{source_id}"], basis=basis, uncertainty=unc,
			uncertainty_basis=notes, parameters={"year": YEAR}, notes=notes,
		)

	out = Path(argv[0]) if argv else ROOT / "data/processed"
	topo = pd.read_parquet(out / "topology.parquet")
	net, _, _ = build_topology(topo, voltage_kv_min=66.0, snap_tolerance_m=500.0)
	f = fleet()
	write_artefact(out / "fleet.parquet", f, _prov("gppd-v1.3-kenya", "WRI GPPD v1.3 KEN rows; 2010 assumed where commissioning year is missing", Basis.MEASURED, 0.0))
	write_artefact(out / "costs.parquet", costs(), _prov("technology-data-2030-2050", "PyPSA technology-data investment rows, EUR->USD at 1.14", Basis.PROXY, 0.3))
	d = demand(net.buses[["lon", "lat"]])
	write_artefact(out / "demand_hourly.parquet", d, _prov("knbs-2023-demand-kenya", "10,320.6 GWh KNBS 2023 spread by approximate town population with a stylised hourly shape", Basis.PROXY, 0.25))
	total = f.capacity_mw.sum()
	peak = d.groupby("timestamp_utc").demand_mw.sum().max()
	print(f"fleet {len(f)} plants {total:.0f} MW = {100 * total / INSTALLED_MW_2023:.0f}% of {INSTALLED_MW_2023} MW installed")
	print(f"demand {len(net.buses)} buses, {d.demand_mw.sum() / 1e3:.1f} GWh, peak {peak:.0f} MW")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
