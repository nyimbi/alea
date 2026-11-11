# SPDX-License-Identifier: MIT
"""Kenya transmission topology from the saved Overpass response (OSM, ODbL).

One row per OSM line way: endpoints are the way's first and last node, length is
the haversine sum along its geometry, voltage is the highest value in the tag.
Ways with no parsable voltage are dropped and counted, not guessed. Thermal
rating is left NaN: OSM carries none, and inventing one would be a number with
no source.

Run: uv run python scripts/build/kenya_topology.py [OUT.parquet]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs/research/milestone-data/osm-kenya/lines.json"


def haversine_km(lat: np.ndarray, lon: np.ndarray) -> float:
	la, lo = np.radians(lat), np.radians(lon)
	d = np.sin(np.diff(la) / 2) ** 2 + np.cos(la[:-1]) * np.cos(la[1:]) * np.sin(np.diff(lo) / 2) ** 2
	return float((2 * 6371.0088 * np.arcsin(np.sqrt(d))).sum())


def voltage_kv(tag: str) -> float | None:
	values = []
	for part in str(tag).split(";"):
		try:
			values.append(float(part.strip()) / 1000.0)
		except ValueError:
			continue
	return max(values) if values else None


def build(path: Path = SRC) -> tuple[pd.DataFrame, dict[str, int]]:
	rows, dropped = [], {"no_voltage": 0, "short_geometry": 0, "below_66kv": 0}
	for el in json.loads(path.read_text())["elements"]:
		geom = el.get("geometry") or []
		kv = voltage_kv(el.get("tags", {}).get("voltage", ""))
		if kv is None:
			dropped["no_voltage"] += 1
			continue
		if kv < 66.0:
			dropped["below_66kv"] += 1
			continue
		if len(geom) < 2:
			dropped["short_geometry"] += 1
			continue
		lat = np.array([p["lat"] for p in geom])
		lon = np.array([p["lon"] for p in geom])
		rows.append(
			{
				"line_id": f"osm-way-{el['id']}",
				"from_lon": lon[0], "from_lat": lat[0], "to_lon": lon[-1], "to_lat": lat[-1],
				"voltage_kv": kv, "length_km": haversine_km(lat, lon), "capacity_mva": np.nan,
			}
		)
	return pd.DataFrame(rows), dropped


def largest_component(frame: pd.DataFrame, snap_m: float = 500.0) -> tuple[pd.DataFrame, dict[str, int]]:
	"""Keep the lines of the biggest connected island, after the builder's own snapping.

	OSM leaves a handful of two-bus stubs unconnected to the main grid, and a
	network with several islands solves each as its own system: one with no
	generator is infeasible. The island count and the lines removed are returned
	so the loss is recorded, not silent. Sub-snap fragments (substation bays)
	collapse into self-loops in the builder and carry no connectivity, so they
	are dropped with it.
	"""
	import scipy.sparse as sp
	from scipy.sparse.csgraph import connected_components

	from alea.planning.topology import build_topology

	net, _, report = build_topology(frame, voltage_kv_min=66.0, snap_tolerance_m=snap_m)
	idx = {b: i for i, b in enumerate(net.buses.index)}
	a = [idx[b] for b in net.lines.bus0]
	b = [idx[b] for b in net.lines.bus1]
	graph = sp.coo_matrix(([1] * len(a), (a, b)), shape=(len(idx),) * 2)
	n_comp, label = connected_components(graph, directed=False)
	biggest = int(np.bincount(label).argmax())
	keep = {line for line, bus in zip(net.lines.index, net.lines.bus0, strict=True) if label[idx[bus]] == biggest}
	out = frame[frame.line_id.isin(keep)].reset_index(drop=True)
	return out, {"islands": int(n_comp), "lines_kept": len(out), "lines_removed": len(frame) - len(out), "self_loops": report.n_self_loops}


if __name__ == "__main__":
	frame, dropped = build()
	frame, island = largest_component(frame)
	dropped.update(island)
	out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/processed/topology.parquet"
	out.parent.mkdir(parents=True, exist_ok=True)
	from alea.io.artefacts import write_artefact
	from alea.provenance.models import Basis, DerivedProvenance

	write_artefact(
		out, frame,
		DerivedProvenance(
			source_id="osm-kenya-power-lines", inputs=["sha256:osm-overpass:kenya-lines"], basis=Basis.PROXY,
			uncertainty=0.15, uncertainty_basis="OSM completeness; voltage tag read as the highest listed",
			parameters={"voltage_floor_kv": 66, "dropped": {k: int(v) for k, v in dropped.items()}},
			notes="Largest connected component of OSM power=line ways at 66 kV and above (ODbL).",
		),
	)
	print(len(frame), "lines", dropped, f"{frame.length_km.sum():.0f} km", frame.voltage_kv.value_counts().to_dict())
