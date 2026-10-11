# SPDX-License-Identifier: MIT
"""Bus and line topology from transmission line geometries.

The load-bearing parameter is the snap tolerance. Too small and a substation
shared by five lines becomes five buses with no connection between them; too
large and two distinct substations merge into one, shortening every path through
the region. Both failures produce a network that solves cleanly and is wrong.

The clustering here is a union-find over a spatial hash whose cell size *equals*
the tolerance, so a point within tolerance is in the same cell or one of the
eight around it. Snapping to a fixed grid instead -- rounding coordinates -- is
the version of this that looks right and is not: two points a metre apart on
opposite sides of a cell boundary stay separate, and two points nine hundred
metres apart inside one cell merge. The grid is the bug that looks like a
tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger
from alea.planning.schemas import TOPOLOGY
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

METRES_PER_DEG_LAT = 110_574.0
"""Meridional length of one degree. Near-constant, so it is not latitude-corrected."""

METRES_PER_DEG_LON_EQUATOR = 111_320.0

X_OHM_PER_KM = 0.4
"""Typical overhead-line series reactance at transmission voltage.

A placeholder with a name. The line-rating source (02-data-pipeline) replaces it
with per-circuit values; until then every network built here records this
constant in its provenance, so a reader can see the assumption rather than
inherit it silently.
"""

R_OHM_PER_KM = 0.08
"""Typical overhead-line series resistance. Same status as ``X_OHM_PER_KM``."""

MVA_PER_KV = 1.8
"""Thermal rating per kV of nominal voltage: 400 MVA at 220 kV, 720 MVA at 400 kV."""


class TopologyError(ValueError):
	"""The lines cannot form a usable network."""


@dataclass
class TopologyReport:
	"""What construction did, including what it discarded."""

	n_buses: int
	n_lines: int
	n_dropped_low_voltage: int
	n_self_loops: int
	snap_tolerance_m: float
	voltage_kv_min: float
	dropped_lines: list[str] = field(default_factory=list)
	self_loop_lines: list[str] = field(default_factory=list)

	def as_dict(self) -> dict[str, object]:
		return {
			"n_buses": self.n_buses,
			"n_lines": self.n_lines,
			"n_dropped_low_voltage": self.n_dropped_low_voltage,
			"n_self_loops": self.n_self_loops,
			"snap_tolerance_m": self.snap_tolerance_m,
			"voltage_kv_min": self.voltage_kv_min,
		}


def metres_per_deg_lon(latitude_deg: float) -> float:
	"""Longitude scale at a latitude.

	At 500 m tolerance the equirectangular approximation is exact to well within
	the tolerance itself, so no geodesic library is warranted here.
	"""
	return METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(latitude_deg))


def distance_m(lon0: float, lat0: float, lon1: float, lat1: float) -> float:
	"""Local planar distance in metres between two lon/lat points."""
	mid_lat = 0.5 * (lat0 + lat1)
	dx = (lon1 - lon0) * metres_per_deg_lon(mid_lat)
	dy = (lat1 - lat0) * METRES_PER_DEG_LAT
	return math.hypot(dx, dy)


class _UnionFind:
	"""Disjoint set with path compression and union by size.

	Iterative throughout: a recursive find on a 50,000-endpoint chain exceeds
	Python's default recursion limit and the failure surfaces as a
	RecursionError in a function nobody suspects.
	"""

	def __init__(self, n: int) -> None:
		self._parent = list(range(n))
		self._size = [1] * n

	def find(self, i: int) -> int:
		root = i
		while self._parent[root] != root:
			root = self._parent[root]
		while self._parent[i] != root:
			self._parent[i], i = root, self._parent[i]
		return root

	def union(self, a: int, b: int) -> None:
		ra, rb = self.find(a), self.find(b)
		if ra == rb:
			return
		if self._size[ra] < self._size[rb]:
			ra, rb = rb, ra
		self._parent[rb] = ra
		self._size[ra] += self._size[rb]


def cluster_points(
	lon: np.ndarray,
	lat: np.ndarray,
	tolerance_m: float,
) -> np.ndarray:
	"""Assign each point to a cluster of points within ``tolerance_m``.

	Returns cluster labels that are the *smallest input index* in each cluster,
	which makes the labelling independent of dictionary iteration order and
	therefore reproducible across runs (AD-8).
	"""
	assert tolerance_m > 0, "tolerance must be positive"
	assert len(lon) == len(lat), "lon and lat must be the same length"
	n = len(lon)
	if n == 0:
		return np.zeros(0, dtype=np.int64)

	uf = _UnionFind(n)
	# Cell size is the tolerance, so any point within tolerance is in this cell
	# or one of the eight neighbours. A cell keyed on floor(coord / cell) needs
	# no sorted traversal to be correct.
	cell = tolerance_m
	buckets: dict[tuple[int, int], list[int]] = {}
	cell_of: list[tuple[int, int]] = []
	for i in range(n):
		key = (int(math.floor(lon[i] * metres_per_deg_lon(lat[i]) / cell)), int(math.floor(lat[i] * METRES_PER_DEG_LAT / cell)))
		cell_of.append(key)
		buckets.setdefault(key, []).append(i)

	for i in range(n):
		ci, cj = cell_of[i]
		for di in (-1, 0, 1):
			for dj in (-1, 0, 1):
				for j in buckets.get((ci + di, cj + dj), ()):
					if j <= i:
						continue
					if distance_m(lon[i], lat[i], lon[j], lat[j]) <= tolerance_m:
						uf.union(i, j)

	roots = [uf.find(i) for i in range(n)]
	# Relabel to the smallest member index. Sorting the members rather than
	# taking the first encountered keeps the label stable.
	smallest: dict[int, int] = {}
	for i in range(n):
		r = roots[i]
		if r not in smallest or i < smallest[r]:
			smallest[r] = i
	return np.array([smallest[roots[i]] for i in range(n)], dtype=np.int64)


def build_topology(
	lines: gpd.GeoDataFrame | pd.DataFrame,
	*,
	voltage_kv_min: float = 66.0,
	snap_tolerance_m: float = 500.0,
	source_id: str = "transmission_lines",
) -> tuple[pypsa.Network, DerivedProvenance, TopologyReport]:
	"""Build bus/line topology from transmission line geometries.

	``lines`` carries the ``topology`` schema's columns, either as attributes or
	as the endpoints of a LineString geometry. Buses are placed at line
	endpoints; endpoints within ``snap_tolerance_m`` are one bus. Lines below
	``voltage_kv_min`` are dropped: sub-transmission is not part of a national
	planning model and including it multiplies bus count for no analytical gain.
	"""
	assert voltage_kv_min > 0, "voltage floor must be positive"
	assert snap_tolerance_m > 0, "snap tolerance must be positive"

	frame = _endpoints(lines)
	TOPOLOGY.check(frame, artefact="topology")

	frame = frame.loc[frame["voltage_kv"] >= voltage_kv_min].copy()
	n_dropped = int(len(_endpoints(lines)) - len(frame))

	if frame.empty:
		raise TopologyError(
			f"no lines at or above {voltage_kv_min} kV; the voltage floor is "
			f"removing the whole network"
		)

	# Endpoints are clustered together, not per line: that is what makes a
	# substation shared by five lines one bus instead of five.
	lon = np.concatenate([frame["from_lon"].to_numpy(dtype=float), frame["to_lon"].to_numpy(dtype=float)])
	lat = np.concatenate([frame["from_lat"].to_numpy(dtype=float), frame["to_lat"].to_numpy(dtype=float)])
	labels = cluster_points(lon, lat, snap_tolerance_m)

	n_lines = len(frame)
	from_label = labels[:n_lines]
	to_label = labels[n_lines:]

	network = pypsa.Network()
	network.name = "alea-topology"

	bus_names = {int(label): f"bus_{int(label):05d}" for label in np.unique(labels)}
	bus_lon: dict[int, float] = {}
	bus_lat: dict[int, float] = {}
	for label in np.unique(labels):
		members = np.flatnonzero(labels == label)
		bus_lon[int(label)] = float(np.mean(lon[members]))
		bus_lat[int(label)] = float(np.mean(lat[members]))
		network.add(
			"Bus",
			bus_names[int(label)],
			carrier="AC",
			lon=bus_lon[int(label)],
			lat=bus_lat[int(label)],
		)

	# The highest voltage touching a bus is its nominal voltage: a 400 kV
	# substation is a 400 kV bus even though a 132 kV line also lands on it.
	bus_voltage: dict[int, float] = {}
	for i in range(n_lines):
		v = float(frame["voltage_kv"].iloc[i])
		for label in (int(from_label[i]), int(to_label[i])):
			bus_voltage[label] = max(bus_voltage.get(label, 0.0), v)
	for label, v in bus_voltage.items():
		network.buses.at[bus_names[label], "v_nom"] = v

	self_loops: list[str] = []
	for i in range(n_lines):
		a, b = int(from_label[i]), int(to_label[i])
		line_id = str(frame["line_id"].iloc[i])
		if a == b:
			# Both endpoints snapped to one bus: the line connects nothing and
			# PyPSA rejects it. Reported rather than dropped quietly, because a
			# cluster of them means the tolerance has merged a substation pair.
			self_loops.append(line_id)
			continue
		length_km = float(frame["length_km"].iloc[i])
		if not math.isfinite(length_km) or length_km <= 0.0:
			length_km = distance_m(
				float(frame["from_lon"].iloc[i]),
				float(frame["from_lat"].iloc[i]),
				float(frame["to_lon"].iloc[i]),
				float(frame["to_lat"].iloc[i]),
			) / 1000.0
		rating = frame["capacity_mva"].iloc[i]
		if rating is None or not math.isfinite(float(rating)) or float(rating) <= 0.0:
			rating = float(frame["voltage_kv"].iloc[i]) * MVA_PER_KV
		network.add(
			"Line",
			line_id,
			bus0=bus_names[a],
			bus1=bus_names[b],
			x=X_OHM_PER_KM * length_km,
			r=R_OHM_PER_KM * length_km,
			b=0.0,
			s_nom=float(rating),
			length=length_km,
			v_nom=float(frame["voltage_kv"].iloc[i]),
			carrier="AC",
		)

	report = TopologyReport(
		n_buses=len(network.buses),
		n_lines=len(network.lines),
		n_dropped_low_voltage=n_dropped,
		n_self_loops=len(self_loops),
		snap_tolerance_m=snap_tolerance_m,
		voltage_kv_min=voltage_kv_min,
		dropped_lines=[str(x) for x in _endpoints(lines).loc[
			_endpoints(lines)["voltage_kv"] < voltage_kv_min, "line_id"
		]],
		self_loop_lines=self_loops,
	)

	provenance = DerivedProvenance(
		source_id=source_id,
		inputs=[f"sha256:{source_id}:topology"],
		basis=Basis.MEASURED,
		uncertainty=0.0,
		parameters={
			"snap_tolerance_m": snap_tolerance_m,
			"voltage_kv_min": voltage_kv_min,
			"x_ohm_per_km": X_OHM_PER_KM,
			"r_ohm_per_km": R_OHM_PER_KM,
			"mva_per_kv": MVA_PER_KV,
			"n_buses": report.n_buses,
			"n_lines": report.n_lines,
			"n_self_loops": report.n_self_loops,
			"n_dropped_low_voltage": report.n_dropped_low_voltage,
		},
		notes=(
			"Electrical parameters are typical overhead-line values, not "
			"per-circuit measurements; see alea.planning.topology constants."
		),
	)
	logger.info(
		"topology_built",
		buses=report.n_buses,
		lines=report.n_lines,
		dropped=report.n_dropped_low_voltage,
		self_loops=report.n_self_loops,
	)
	return network, provenance, report


def _endpoints(lines: gpd.GeoDataFrame | pd.DataFrame) -> pd.DataFrame:
	"""Flatten line geometries into the endpoint columns the schema declares.

	A GeoDataFrame carrying LineStrings is the seam's natural output, so the
	endpoints are extracted here rather than required from the producer.
	"""
	assert lines is not None, "lines must not be None"
	if isinstance(lines, gpd.GeoDataFrame) and "geometry" in lines.columns:
		frame = pd.DataFrame(lines.drop(columns="geometry"))
		geoms = lines.geometry
		frame["from_lon"] = geoms.apply(lambda g: float(g.coords[0][0]) if g is not None else np.nan)
		frame["from_lat"] = geoms.apply(lambda g: float(g.coords[0][1]) if g is not None else np.nan)
		frame["to_lon"] = geoms.apply(lambda g: float(g.coords[-1][0]) if g is not None else np.nan)
		frame["to_lat"] = geoms.apply(lambda g: float(g.coords[-1][1]) if g is not None else np.nan)
		return frame.reset_index(drop=True)
	return pd.DataFrame(lines).reset_index(drop=True)


def connectivity_report(network: pypsa.Network) -> dict[str, int]:
	"""Weakly-connected components of the bus/line graph.

	A national network is one component per synchronous area. More components
	than that means lines were dropped or the voltage floor cut a region off.
	"""
	assert network is not None, "network must not be None"
	import networkx as nx

	graph = nx.Graph()
	graph.add_nodes_from(str(b) for b in network.buses.index)
	for _, row in network.lines.iterrows():
		graph.add_edge(str(row["bus0"]), str(row["bus1"]))
	components = list(nx.connected_components(graph))
	sizes = sorted((len(c) for c in components), reverse=True)
	return {
		"n_components": len(components),
		"largest_component": sizes[0] if sizes else 0,
		"n_buses": len(network.buses),
		"n_singletons": sum(1 for s in sizes if s == 1),
	}


def orphan_buses(network: pypsa.Network) -> list[str]:
	"""Buses with no line, generator, load or storage attached.

	An orphan bus is a node the optimiser can do nothing with. It is usually a
	snapping artefact, and it inflates the bus count every later stage reports.
	"""
	assert network is not None, "network must not be None"
	attached: set[str] = set()
	for _, row in network.lines.iterrows():
		attached.add(str(row["bus0"]))
		attached.add(str(row["bus1"]))
	for component, column in (("generators", "bus"), ("loads", "bus"), ("storage_units", "bus"), ("stores", "bus")):
		table = getattr(network, component)
		if len(table):
			attached.update(str(b) for b in table[column])
	return sorted(str(b) for b in network.buses.index if str(b) not in attached)


__all__ = [
	"METRES_PER_DEG_LAT",
	"R_OHM_PER_KM",
	"X_OHM_PER_KM",
	"TopologyError",
	"TopologyReport",
	"build_topology",
	"cluster_points",
	"connectivity_report",
	"distance_m",
	"metres_per_deg_lon",
	"orphan_buses",
]
