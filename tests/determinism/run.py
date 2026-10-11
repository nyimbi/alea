# SPDX-License-Identifier: MIT
"""Build the determinism fixture and write its numbers to a directory.

CI runs this twice in two separate processes and diffs the two directories. The
fixture is synthetic and fixed so that the harness needs no downloaded data and
no network: a determinism check that depends on a live source is a check that
fails when the source is down, and the failure reads as nondeterminism.

What it exercises is every stage whose output a published number is derived
from -- topology, fleet attachment, demand, renewables, expansion under HiGHS,
two-level deduplication, and market clearing -- plus the three places the plan
already names as nondeterminism sites: a content hash (``_digest``), a seeded
MinHash (``minhash``), and a market-clearing tie-break (``clear_market``). Each
of the three writes a digest into the summary, so a regression in any of them
shows up as a line in the two-process ``diff -r`` rather than as a claim in this
docstring that nothing implements.

The diff is byte-level. ``json.dumps(sort_keys=True)`` is not decoration: an
unsorted dump of a dict whose insertion order varies makes two identical runs
differ, and the harness would then report a defect in the code under test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from alea._core.kernels import minhash
from alea.config.loader import load_config
from alea.market.clearing import clear_market
from alea.market.views import Bid
from alea.planning.demand import attach_loads, disaggregate_to_buses
from alea.planning.expansion import capacity_mix_table, loss_share, solve_expansion
from alea.planning.fleet import attach_generators
from alea.planning.renewables import attach_renewables
from alea.planning.schemas import DEMAND, FLEET, PROFILE, TOPOLOGY
from alea.planning.topology import build_topology
from alea.scanning.connectors.base import RawDocument, make_document
from alea.scanning.ingest import deduplicate_documents

ROOT = Path(__file__).resolve().parents[2]

# A four-substation Kenya-like grid. Fixed coordinates, fixed capacities, fixed
# hours -- nothing is drawn from a distribution, because a fixture that samples
# cannot distinguish "the code is deterministic" from "the sample agreed".
N_HOURS = 168
START = "2030-01-01"

# Coordinates in degrees; the topology builder projects them itself. L4 is a 33 kV
# line, below the 66 kV floor, so it is dropped -- the fixture exercises the drop
# path as well as the build path, and the count of dropped lines is asserted in
# the summary so a change to the floor shows up as a diff.
LINE_ROWS = pd.DataFrame(
	{
		"line_id": ["L1", "L2", "L3", "L4"],
		"from_lon": [36.8219, 39.6682, 35.2698, 36.8219],
		"from_lat": [-1.2921, -4.0435, -0.0917, -1.2921],
		"to_lon": [39.6682, 35.2698, 36.8219, 36.8300],
		"to_lat": [-4.0435, -0.0917, -1.2921, -1.2950],
		"voltage_kv": [400.0, 220.0, 132.0, 33.0],
		"length_km": [490.0, 330.0, 300.0, 1.0],
		"capacity_mva": [1200.0, 600.0, 300.0, 50.0],
	}
)

FLEET_ROWS = pd.DataFrame(
	{
		"plant_id": ["OLKARIA", "GITARU", "KIPEVU", "FARAWAY"],
		"name": ["Olkaria", "Gitaru", "Kipevu", "Faraway"],
		"carrier": ["geothermal", "geothermal", "oil", "solar"],
		"capacity_mw": [600.0, 400.0, 200.0, 50.0],
		"lon": [36.30, 36.15, 39.66, 41.85],
		"lat": [-0.35, -0.30, -4.04, 0.50],
		"commissioning_year": [1981, 1999, 1997, 2020],
		"lifetime_years": [30, 30, 30, 25],
	}
)


# A fixed corpus for the near-duplicate path. Two outlets carry the same wire
# copy (so their five-word shingles overlap heavily and MinHash groups them),
# and a third is unrelated. The grouping depends on the seeded kernel, so an
# unseeded MinHash -- or a set-ordered shingle stream -- reorders or regroups
# these across processes and the digest moves.
WIRE_COPY = (
	"Kenya Power announced a 100 MW geothermal expansion at Olkaria on "
	"2029-06-01, adding firm capacity to the national grid."
)
WIRE_REPEAT = (
	"Kenya Power announced a 100 MW geothermal expansion at Olkaria on "
	"2029-06-01, adding firm capacity to the national grid today."
)
UNRELATED = (
	"A solar developer signed a 20-year power purchase agreement for a 50 MW "
	"plant in northern Kenya, priced in USD."
)
# Two documents deliberately tie on the detail rule's first three terms --
# equal text length, equal entity count, equal publication -- so the group
# representative is decided by the lowest `document_id`, which is the term the
# specification omits and AD-8 names. If that term were dropped, the choice
# would fall to input order and the digest would move across processes.
TIE_A = "A 100 MW plant in Kenya reached commercial operation in 2029."
TIE_B = "A 100 MW plant in Kenya reached commercial operation in 2029."
TIE_WHEN = datetime(2029, 7, 1, tzinfo=UTC)

# A two-unit stack with an exact price tie, and demand that splits across it.
# The merit order must break the tie on `unit_id`, never on list order: the
# fixture lists BETA first, so a stack sorted on price alone keeps BETA ahead
# of ALPHA and dispatches 60 MW of BETA and 40 MW of ALPHA -- the same total at
# the same price, a different dispatch dict, a different digest. The tie is
# marginal on purpose: if both tied units cleared in full the dispatch would be
# identical whichever order they were taken in, and the fixture would assert
# nothing about the tie-break it exists to exercise.
BID_ROWS = [
	("U-BETA", 60.0, 60.0),
	("U-ALPHA", 60.0, 60.0),
]
DEMAND_MW = 100.0
VOLL_USD_PER_MWH = 2000.0


def _hours() -> pd.DatetimeIndex:
	return pd.date_range(START, periods=N_HOURS, freq="h")


def _corpus() -> list[RawDocument]:
	"""The fixed near-duplicate corpus, in a fixed order.

	Every field except ``retrieved_at`` is pinned, and ``retrieved_at`` is
	normalised by ``make_document`` to the same clock read, so ``document_id``
	-- the identity hash -- is a function of the text alone. The fixture does
	not call the network: a determinism check that depends on a live source
	fails when the source is down, and the failure reads as nondeterminism.
	"""

	def doc(source: str, url: str, title: str, text: str, published: datetime) -> RawDocument:
		return make_document(
			source_name=source,
			url=url,
			title=title,
			text=text,
			published_at=published,
			retrieved_at=TIE_WHEN,
		)

	when = datetime(2029, 6, 1, tzinfo=UTC)
	return [
		doc("wire", "https://example.test/a", "Olkaria expansion", WIRE_COPY, when),
		doc("news", "https://example.test/b", "Olkaria expansion reported", WIRE_REPEAT, when),
		doc("solar", "https://example.test/c", "Solar PPA signed", UNRELATED, when),
		doc("tie-a", "https://example.test/d", "Tie A", TIE_A, TIE_WHEN),
		doc("tie-b", "https://example.test/e", "Tie B", TIE_B, TIE_WHEN),
	]


def _minhash_digest(texts: list[str]) -> str:
	"""sha256 of the concatenated MinHash signatures of ``texts``.

	``minhash`` returns a ``uint64`` array; the seed is fixed at the call, so
	the signature is a function of the text and nothing else. An unseeded
	MinHash folds Python's per-process string hash in and this digest moves.
	"""
	signatures: list[NDArray[np.uint64]] = [minhash(text, seed=0) for text in texts]
	payload = b"".join(sig.tobytes() for sig in signatures)
	return hashlib.sha256(payload).hexdigest()[:32]


def _dedup_summary() -> dict[str, Any]:
	"""Run the two-level dedup path and reduce its report to stable numbers.

	The report's group membership and representative are read back, not just
	its counts: two runs that keep the same *number* of documents but keep
	different ones have a nondeterminism the counts would hide.
	"""
	kept, report = deduplicate_documents(_corpus())
	return {
		"input_count": int(report.input_count),
		"exact_duplicates": int(report.exact_duplicates),
		"near_duplicates": int(report.near_duplicates),
		"kept_ids": list(report.kept_ids),
		"group_representatives": [str(g.representative_id) for g in report.groups],
		"minhash_digest": _minhash_digest([doc.text for doc in kept]),
	}


def _clearing_summary() -> dict[str, Any]:
	"""Clear one market over a stack with a deliberate price tie."""
	bids = [
		Bid(unit_id=unit_id, quantity_mw=quantity, price_usd_per_mwh=price)
		for unit_id, price, quantity in BID_ROWS
	]
	result = clear_market(bids, DEMAND_MW, value_of_lost_load_usd_per_mwh=VOLL_USD_PER_MWH)
	return {
		"clearing_price_usd_per_mwh": round(float(result.clearing_price_usd_per_mwh), 10),
		"unserved_mwh": round(float(result.unserved_mwh), 10),
		# Sorted for the same reason the dump is: the dispatch dict's insertion
		# order follows the stack, and a diff must see the dispatch, not its
		# order.
		"dispatched": {
			str(unit_id): round(float(mw), 10)
			for unit_id, mw in sorted(result.dispatched.items())
		},
	}


def _load_frame(buses: list[str]) -> pd.DataFrame:
	"""Per-bus hourly demand in the ``demand`` schema's shape.

	``bus_id``/``load_mw``, not ``bus``/``demand_mw``: the schema is the
	interface the seam's artefacts arrive through, and a fixture that does not
	satisfy it tests a pipeline nobody runs.
	"""
	hours = _hours()
	shape = 1.0 + 0.25 * np.sin(np.arange(N_HOURS) * 2.0 * np.pi / 24.0)
	# Weighted across the first two buses; the national total is preserved
	# because the shares sum to one by construction.
	shares = [0.7, 0.3][: len(buses)] or [1.0]
	total = 1200.0 * shape
	frames = []
	for bus, share in zip(buses, shares, strict=False):
		frames.append(
			pd.DataFrame(
				{
					"bus_id": bus,
					"timestamp": hours.astype(str),
					"load_mw": total * share,
				}
			)
		)
	return pd.concat(frames, ignore_index=True)


def _profile_frame(buses: list[str]) -> pd.DataFrame:
	"""Per-bus capacity factors in the ``profile`` schema's shape."""
	hours = _hours()
	hour_of_day = np.arange(N_HOURS) % 24
	solar = np.clip(np.sin((hour_of_day - 6.0) * np.pi / 12.0), 0.0, None) * 0.80
	wind = 0.35 + 0.10 * np.sin(np.arange(N_HOURS) * 2.0 * np.pi / 72.0)
	frames = []
	for carrier, values in (("solar", solar), ("onwind", wind)):
		for bus in buses:
			frames.append(
				pd.DataFrame(
					{
						"bus_id": bus,
						"carrier": carrier,
						"timestamp": hours.astype(str),
						"capacity_factor": values,
					}
				)
			)
	return pd.concat(frames, ignore_index=True)


def _digest(frame: pd.DataFrame) -> str:
	"""A content hash of a frame's values, independent of column order.

	``hash()`` of a string is salted per process, so it is the exact defect the
	plan lists for ``WhatIfEngine._cache_key``. This uses sha256 over the
	values, sorted by name, which is stable across processes and interpreters.
	"""
	canonical = frame.reindex(sorted(frame.columns), axis=1)
	payload = canonical.to_csv(index=False, float_format="%.10g").encode()
	return hashlib.sha256(payload).hexdigest()[:32]


def _wide(frame: pd.DataFrame, value: str) -> pd.DataFrame:
	"""Pivot a long schema frame to (timestamp index, bus columns)."""
	pivot = frame.pivot_table(index="timestamp", columns="bus_id", values=value, aggfunc="sum")
	pivot.index = pd.DatetimeIndex(pivot.index)
	# Column labels are bus ids read from the input, so they are strings; the
	# stub types the pivot's columns as `Scalar`.
	return pivot.sort_index().rename(columns=str)


def build(out: Path) -> dict[str, Any]:
	"""Build the fixture end to end and write its numbers under ``out``."""
	assert N_HOURS > 0, "the fixture needs at least one hour"
	TOPOLOGY.check(LINE_ROWS, artefact="topology")
	FLEET.check(FLEET_ROWS, artefact="fleet")

	network, _topology_provenance, topology_report = build_topology(LINE_ROWS)
	attach_generators(network, FLEET_ROWS)

	buses = [str(b) for b in network.buses.index]
	# The two buses the load and the profiles serve. A three-bus network where
	# one bus carries nothing is realistic and exercises the solver's ability to
	# leave a bus alone.
	served = buses[:2]

	loads = _load_frame(served)
	DEMAND.check(loads, artefact="demand")
	profiles = _profile_frame(served)
	PROFILE.check(profiles, artefact="profile")

	national = _wide(loads, "load_mw").sum(axis=1)
	weights = {bus: 1.0 for bus in served}
	attach_loads(network, disaggregate_to_buses(national, weights))

	attach_renewables(
		network,
		{
			str(carrier): _wide(group, "capacity_factor")
			for carrier, group in profiles.groupby("carrier", sort=True)
		},
		capital_cost_usd_per_mw={"solar": 700_000.0, "onwind": 1_200_000.0},
	)

	config = load_config(ROOT / "config" / "config.default.yaml")
	result = solve_expansion(network, config, multi_period=False)

	mix = capacity_mix_table(network)
	summary = {
		"objective": round(float(result.objective), 6),
		"loss_share": round(float(loss_share(network)), 10),
		"n_buses": int(topology_report.n_buses),
		"n_lines": int(topology_report.n_lines),
		"n_dropped_low_voltage": int(topology_report.n_dropped_low_voltage),
		"n_self_loops": int(topology_report.n_self_loops),
		"mix": [
			{"carrier": str(row["carrier"]), "capacity_mw": round(float(row["capacity_mw"]), 6)}
			for _, row in mix.iterrows()
		],
		"mix_digest": _digest(mix),
		"fleet_digest": _digest(FLEET_ROWS),
		"load_digest": _digest(loads),
		"profile_digest": _digest(profiles),
		"generation_mwh": round(float(network.generators_t.p.to_numpy().sum()), 6),
		# The two paths this harness previously claimed to exercise and did
		# not. They are plain dicts here rather than digests so a divergence
		# names the field that moved, but the summary is hashed whole by the
		# byte-level `diff -r` either way.
		"dedup": _dedup_summary(),
		"clearing": _clearing_summary(),
	}

	out.mkdir(parents=True, exist_ok=True)
	(out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
	mix.to_csv(out / "capacity_mix.csv", index=False, float_format="%.10g")
	return summary


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--out", type=Path, required=True, help="Directory to write into.")
	args = parser.parse_args(argv)
	summary = build(args.out)
	print(json.dumps(summary, sort_keys=True))
	return 0


if __name__ == "__main__":  # pragma: no cover
	sys.exit(main())
