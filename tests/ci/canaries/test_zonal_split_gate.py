# SPDX-License-Identifier: MIT
"""Canary: the zonal-split gate must be watched failing on the defect it catches.

``test_zonal_clearing_produces_congestion_on_a_congested_path`` is the gate on
Layer 3's exit criterion 2 (06-layer3 §10). It clears a three-zone path A-B-C
where both corridors bind and asserts the market splits into three distinct
prices and converges.

The defect it exists to catch: ``_split_area`` moved only the corridor's
``to_zone`` to the new area. On a *path* graph A-B-C, splitting at A-B left C
grouped with A, so C kept A's price even though the binding corridor separated
them. The next iteration then pinned B-C, re-split a two-zone area at a corridor
whose endpoints were no longer in the same area, and the iteration never
converged -- on the plan's own example, a corridor that binds.

The two computations are written out below so the canary asserts the difference
rather than trusting it: ``defective_split`` is the old one, and the module's own
``_split_area`` is the fix. Both run through the real ``clear_market_zonal`` via
monkeypatch, because a canary on a helper that is not the one the public entry
point calls proves nothing about the entry point.
"""

from __future__ import annotations

import numpy as np

from alea.market import clearing
from alea.market.clearing import clear_market_zonal
from alea.market.views import Bid, Interface

# A three-zone path, cheap at one end and dear at the other, so both corridors
# bind: the economic trade from A to C exceeds either corridor's limit.
_BIDS = {
	"A": [Bid(unit_id="a1", quantity_mw=200.0, price_usd_per_mwh=10.0, zone_id="A")],
	"B": [Bid(unit_id="b1", quantity_mw=200.0, price_usd_per_mwh=40.0, zone_id="B")],
	"C": [Bid(unit_id="c1", quantity_mw=200.0, price_usd_per_mwh=80.0, zone_id="C")],
}
_DEMAND = {"A": 50.0, "B": 100.0, "C": 150.0}
_INTERFACES = [
	Interface(from_zone="A", to_zone="B", limit_mw=60.0, susceptance=1.0),
	Interface(from_zone="B", to_zone="C", limit_mw=60.0, susceptance=1.0),
]
_VOLL = 10_000.0


def defective_split(areas, area_of, zone_ids, interfaces, interface, index):
	"""The defect: move only the ``to_zone``, not everything beyond it."""
	old_area = area_of[interface.from_zone]
	new_area = len(areas)
	areas.append(set())
	for zone in zone_ids:
		if area_of[zone] == old_area and zone != interface.from_zone and zone == interface.to_zone:
			area_of[zone] = new_area
	areas[old_area] = {z for z in zone_ids if area_of[z] == old_area}
	areas[new_area] = {z for z in zone_ids if area_of[z] == new_area}


def _clear(split) -> clearing.ZonalClearingResult:
	original = clearing._split_area
	clearing._split_area = split
	try:
		return clear_market_zonal(
			_BIDS, _DEMAND, _INTERFACES, value_of_lost_load_usd_per_mwh=_VOLL
		)
	finally:
		clearing._split_area = original


def test_the_gate_passes_on_the_fix():
	"""The gate's assertion, on the real code: three prices, converged."""
	result = _clear(clearing._split_area)
	prices = [result.zones[z].price_usd_per_mwh for z in ("A", "B", "C")]
	assert result.converged, "the fixed split does not converge"
	assert prices == [10.0, 40.0, 80.0], f"expected three distinct zonal prices, got {prices}"


def test_the_canary_is_watched_failing_on_the_defect():
	"""Canary proper. If this ever passes, the defect has returned and the gate is blind."""
	result = _clear(defective_split)
	# The gate is ``converged`` plus three distinct prices; the defect breaks both.
	assert not result.converged or len(
		{result.zones[z].price_usd_per_mwh for z in ("A", "B", "C")}
	) < 3, (
		"the old single-zone split now produces a split market; the canary no "
		"longer demonstrates the defect it exists to catch"
	)
	assert result.zones["C"].price_usd_per_mwh == result.zones["A"].price_usd_per_mwh, (
		"the defect no longer strands C with A; the canary is testing something else"
	)


def test_the_canary_target_still_exists():
	"""The helper the canary monkeypatches is still the one the entry point calls.

	A canary that patches a symbol nothing calls proves nothing about the gate.
	``clear_market_zonal`` calls the module attribute by name, so the patch above
	reaches it; this asserts the attribute is still there to be patched.
	"""
	assert hasattr(clearing, "_split_area"), "clearing._split_area is gone; the canary is a no-op"
	assert np.isfinite(_VOLL), "the fixture's VoLL must be finite for the clear to run"
