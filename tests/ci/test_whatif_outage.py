# SPDX-License-Identifier: MIT
"""Line outages as a what-if dimension.

WHY the central test is a *measurement* and not a shape check. The two ways to
take a line out on this stack look identical in the parameter set and produce
different networks: ``lines_t.active`` is accepted, stored, and never read by
the optimiser, so a scenario stated that way solves to the base case's cost and
reads as "this line does not matter". Nothing about the result's shape says so.
So the gate here solves a network with the line out and asserts the *dispatch
changed by the right amount* — a line carrying zero and the load served by
shedding — rather than asserting that a field was set.

WHY the islanding test asserts on the refusal and not on a solve error: the
engine's own failure for an island it cannot balance is ``SolveError`` reading
"an infeasible or unbounded scenario is a result about the scenario" — true,
and silent about which line stranded which bus. The engine's job is to say
which bus was stranded before that happens, and the gate pins the message's
content because a refusal that does not name the island is not the refusal this
exists to make.
"""

from __future__ import annotations

import pandas as pd
import pypsa
import pytest
from pydantic import ValidationError

from alea.whatif import (
	LineOutage,
	OutageError,
	OutageSet,
	ScenarioParameters,
	WhatIfEngine,
	apply_outages,
	islands_without_generation,
	outage_mask,
)

SNAPSHOTS = pd.date_range("2030-01-01", periods=6, freq="h")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _linked(*, shedding: bool = True, local_gen: bool = False) -> pypsa.Network:
	"""Two buses joined by one line: generation at ``a``, load at ``b``.

	``shedding`` adds the VoLL generator at ``b`` that the spec's own islanding
	model relies on (``docs/what-if-line-loss.md`` §2.3), and ``local_gen`` adds
	a real unit at ``b``. The three combinations are the three jurisdictions the
	islanding check has to tell apart: servable by shedding, servable by
	generation, and servable by nothing.

	Unsolved, because every test here applies an outage and then solves — and
	PyPSA refuses to copy a network that still holds its solver model.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	for bus in ("a", "b"):
		network.add("Bus", bus, carrier="AC")
	for carrier in ("gas", "load", "load shedding"):
		network.add("Carrier", carrier)
	network.add("Generator", "g", bus="a", carrier="gas", p_nom=200.0, marginal_cost=10.0)
	network.add("Load", "d", bus="b", p_set=50.0)
	network.add("Line", "L1", bus0="a", bus1="b", x=0.1, r=0.01, s_nom=100.0)
	if shedding:
		network.add(
			"Generator", "shed", bus="b", carrier="load shedding", p_nom=10_000.0, marginal_cost=9000.0
		)
	if local_gen:
		network.add("Generator", "local", bus="b", carrier="gas", p_nom=100.0, marginal_cost=50.0)
	return network


def _solved(network: pypsa.Network) -> pypsa.Network:
	network.optimize(solver_name="highs", log_to_console=False)
	network.model.solver_model = None
	return network


def _engine(tmp_path, network: pypsa.Network | None = None) -> WhatIfEngine:
	return WhatIfEngine(_solved(network or _linked()), cache_root=tmp_path / "cache")


# --------------------------------------------------------------------------
# The mechanism: a rating, not a status flag
# --------------------------------------------------------------------------


def test_a_windowed_outage_zeroes_the_line_for_exactly_that_window(tmp_path):
	"""The window is honoured per snapshot, and the load moves to shedding.

	This is the measurement that distinguishes the two spellings of an outage.
	``lines_t.active`` on this stack is stored and ignored, so the line would
	carry 50 MW on every snapshot and the scenario would be indistinguishable
	from the base case. Asserted on the dispatch rather than on the frame that
	was assigned, because the frame is the input and the dispatch is the fact.
	"""
	engine = _engine(tmp_path)
	window = OutageSet((LineOutage("L1", 0.0, "2030-01-01 02:00:00", "2030-01-01 04:00:00"),))
	network = _solved(_linked())
	apply_outages(network, window)
	network.optimize(solver_name="highs", log_to_console=False)

	flow = network.lines_t.p0["L1"].round(3).tolist()
	assert flow[:2] == [50.0, 50.0], f"the line was out before its window: {flow}"
	assert flow[2:5] == [0.0, 0.0, 0.0], f"the line carried load during its window: {flow}"
	assert flow[5] == 50.0, f"the line stayed out after its window: {flow}"

	served = network.generators_t.p["shed"].round(3).tolist()
	assert served[2:5] == [50.0, 50.0, 50.0], f"shedding did not pick up the island: {served}"

	# And the engine's own path agrees: the scenario costs strictly more than
	# the base case, because three hours of demand are served at VoLL.
	base = engine.solve(ScenarioParameters(demand_growth=0.0))
	out = engine.solve(ScenarioParameters(demand_growth=0.0, outages=window))
	assert out.total_cost_usd > base.total_cost_usd
	assert out.unserved_energy_mwh == pytest.approx(150.0), "3 hours x 50 MW"


def test_a_derate_is_the_same_mechanism_as_a_full_outage():
	"""``factor`` is the spec's ``line_capacity_factor``, and 0.5 carries half.

	A separate test from the outage one because the failure modes differ: a
	derate that was applied as a boolean would take the line out entirely and
	the island would be served by shedding, which the cost would show but a
	"was the line derated" assertion would not.
	"""
	network = _solved(_linked())
	apply_outages(network, OutageSet((LineOutage("L1", 0.5),)))
	network.optimize(solver_name="highs", log_to_console=False)

	# The line's rating is halved, and 50 MW still fits under 50 MVA -- so the
	# dispatch is unchanged and the *rating* is what moved. Asserted on the
	# rating the optimiser read, which is the quantity the factor scales.
	assert network.lines_t.s_max_pu["L1"].round(3).tolist() == [0.5] * 6


def test_an_outage_applied_twice_is_the_same_as_applied_once():
	"""Idempotent, so a resumed sweep cannot compound the derate.

	``apply.py`` records a base snapshot for exactly this reason on generators:
	a relative operation on an absolute quantity compounds. Here the base is
	the static column, which this module never writes, so the assignment is
	idempotent by construction — and the test is what keeps a later edit from
	turning the assignment into a multiplication.
	"""
	once = _linked()
	apply_outages(once, OutageSet((LineOutage("L1", 0.25),)))

	twice = _linked()
	apply_outages(twice, OutageSet((LineOutage("L1", 0.25),)))
	apply_outages(twice, OutageSet((LineOutage("L1", 0.25),)))

	pd.testing.assert_frame_equal(once.lines_t.s_max_pu, twice.lines_t.s_max_pu)
	assert once.lines_t.s_max_pu["L1"].iloc[0] == pytest.approx(0.25)


# --------------------------------------------------------------------------
# The refusals
# --------------------------------------------------------------------------


def test_an_island_with_no_generation_is_refused_by_name(tmp_path):
	"""The engine's anonymous infeasibility is replaced by one that names the bus.

	Without the check, this solve raises ``SolveError: the optimiser returned
	status='warning' (infeasible)`` from the engine's own default — no line, no
	bus. The gate asserts the refusal names the stranded bus, because a refusal
	that does not is the generic error with extra steps.
	"""
	engine = _engine(tmp_path, _linked(shedding=False))
	with pytest.raises(OutageError) as caught:
		engine.solve(ScenarioParameters(demand_growth=0.0, outages=OutageSet((LineOutage("L1"),))))
	message = str(caught.value)
	assert "L1" in message, f"the refusal does not name the line: {message}"
	assert "'b'" in message, f"the refusal does not name the stranded bus: {message}"


def test_an_island_served_by_shedding_is_not_refused(tmp_path):
	"""The spec's own islanding model must survive the check written for it.

	``docs/what-if-line-loss.md`` §2.3 measures islanding *through* load
	shedding: it is a VoLL generator, so the optimiser minimises unserved energy
	and the ENS is the answer. A check that treated shedding as "not
	generation" would refuse every island — forbidding the measurement and
	calling it validation. The canary for this is the same fixture with the
	shedding unit removed, which must refuse.
	"""
	engine = _engine(tmp_path, _linked(shedding=True))
	result = engine.solve(ScenarioParameters(demand_growth=0.0, outages=OutageSet((LineOutage("L1"),))))
	assert result.unserved_energy_mwh == pytest.approx(300.0), "6 hours x 50 MW stranded"

	# The jurisdiction is the *solver's* condition, not "is there shedding":
	# the same island with no shedding anywhere refuses.
	assert islands_without_generation(_linked(shedding=True), OutageSet((LineOutage("L1"),))) == []
	assert islands_without_generation(_linked(shedding=False), OutageSet((LineOutage("L1"),))) == [["b"]]


def test_an_island_with_local_generation_is_not_refused():
	"""A unit on the islanded bus is the other way the balance can close."""
	assert islands_without_generation(
		_linked(shedding=False, local_gen=True), OutageSet((LineOutage("L1"),))
	) == []


def test_a_windowed_outage_never_islands():
	"""A line that is out for part of the horizon still connects the buses.

	The check runs over the whole outage set, and a component computed over the
	union of all windows would report an island that exists for three hours as
	though it were permanent — refusing a scenario the spec asks for. Only a
	full-horizon, factor-zero outage removes the edge.
	"""
	window = OutageSet((LineOutage("L1", 0.0, "2030-01-01 02:00:00", "2030-01-01 04:00:00"),))
	assert islands_without_generation(_linked(shedding=False), window) == []


def test_an_outage_on_a_line_the_network_lacks_is_refused():
	"""A typo must not read as "the named line was lost"."""
	with pytest.raises(OutageError) as caught:
		apply_outages(_linked(), OutageSet((LineOutage("NOPE"),)))
	assert "NOPE" in str(caught.value)


def test_a_window_matching_no_snapshot_is_refused():
	"""The silent-no-op class: a mistyped date would solve as the base case."""
	with pytest.raises(OutageError) as caught:
		apply_outages(_linked(), OutageSet((LineOutage("L1", 0.0, "2040-01-01", "2040-02-01"),)))
	assert "matches none" in str(caught.value)


# --------------------------------------------------------------------------
# The value model
# --------------------------------------------------------------------------


def test_a_factor_of_one_is_the_baseline_of_a_sweep_not_a_refusal():
	"""``1.0`` is allowed: it is the frontier's own baseline point.

	The spec's outage frontier is line in / derated / out
	(``docs/what-if-line-loss.md`` §1.1), so refusing ``1.0`` would make that
	frontier unbuildable from one sweep. The refusal in this module is for a
	no-op the caller did *not* intend — a window matching no snapshot — which is
	the silent-no-op class, and this is not it.
	"""
	assert LineOutage("L1", 1.0).factor == 1.0

	network = _solved(_linked())
	apply_outages(network, OutageSet((LineOutage("L1", 1.0),)))
	network.optimize(solver_name="highs", log_to_console=False)
	assert network.lines_t.p0["L1"].round(3).tolist() == [50.0] * 6


def test_a_factor_above_one_is_refused_rather_than_clamped():
	"""A reinforcement is a different scenario, not a louder outage."""
	with pytest.raises(OutageError) as caught:
		LineOutage("L1", 1.5)
	assert "reinforcement" in str(caught.value)


def test_two_outages_on_one_line_are_refused():
	"""The second would overwrite the first, so the scenario depends on order."""
	with pytest.raises(OutageError) as caught:
		OutageSet((LineOutage("L1"), LineOutage("L1", 0.5)))
	assert "L1" in str(caught.value)


def test_an_inverted_window_is_refused():
	with pytest.raises(OutageError):
		LineOutage("L1", 0.0, "2030-06-15", "2030-06-01")


def test_the_outage_set_keys_independently_of_the_order_it_was_listed_in():
	"""Two spellings of one scenario must hash to one cache key.

	``canonical_json`` is hashed into the key, so an unordered serialisation
	would file one scenario under two keys depending on construction order —
	and the cache would miss for a reason neither file shows.
	"""
	first = ScenarioParameters(
		outages=[{"line": "L2", "factor": 0.5}, {"line": "L1"}],
	)
	second = ScenarioParameters(
		outages=OutageSet((LineOutage("L1"), LineOutage("L2", 0.5))),
	)
	assert first.canonical_json() == second.canonical_json()

	# And the canonical form is *flat*: a nested wrapper key would be a second
	# name that has to agree between the writer and any reader of a stored entry.
	assert isinstance(first.canonical()["outages"], list)
	assert first.canonical()["outages"][0]["line"] == "L1"

	# A stored payload read back is the same scenario.
	assert (
		ScenarioParameters.model_validate(second.canonical()).canonical_json()
		== second.canonical_json()
	)


def test_a_scenario_with_a_line_out_is_a_different_cache_key(tmp_path):
	"""The outage has to enter the key, or one solve serves the other.

	Two parameter sets differing only in an outage are two optimisations of one
	network, and a key that omitted this would serve whichever ran first to the
	other — the same failure the network checksum prevents, one level down.
	"""
	engine = _engine(tmp_path)
	base = ScenarioParameters(demand_growth=0.0)
	out = ScenarioParameters(demand_growth=0.0, outages=OutageSet((LineOutage("L1", 0.5),)))
	assert engine.key_for(base) != engine.key_for(out)


def test_the_default_scenario_carries_no_outages():
	"""The field is additive: an existing scenario is byte-for-byte unchanged."""
	assert ScenarioParameters().outages == OutageSet()
	assert not ScenarioParameters().outages
	assert ScenarioParameters().canonical()["outages"] == []
	assert ScenarioParameters().outages.summary() == "no line outages"


def test_an_outage_is_validated_from_a_mapping_or_a_record():
	"""The three forms that legitimately arrive: a value, a list, and mappings."""
	from_value = ScenarioParameters(outages=OutageSet((LineOutage("L1"),)))
	from_list = ScenarioParameters(outages=[LineOutage("L1")])
	from_dicts = ScenarioParameters(outages=[{"line": "L1"}])
	assert from_value.outages == from_list.outages == from_dicts.outages
	assert isinstance(from_dicts.outages, OutageSet)

	with pytest.raises(ValidationError):
		ScenarioParameters(outages=[{"line": "L1", "factor": 2.0}])


def test_a_multi_period_window_matches_on_the_timestamp_level():
	"""A window is stated in wall-clock time, not in the horizon's period index.

	A multi-period network's snapshots are ``(period, timestamp)``; matching the
	period level would make the caller know the horizon's internal numbering.
	"""
	network = pypsa.Network()
	index = pd.MultiIndex.from_product(
		[[2030, 2040], pd.date_range("2030-06-01", periods=3, freq="h")]
	)
	network.set_snapshots(index)
	network.add("Bus", "b1", carrier="AC")
	network.add("Line", "L1", bus0="b1", bus1="b1", x=0.1, r=0.01, s_nom=100.0)

	mask = outage_mask(network, LineOutage("L1", 0.0, "2030-06-01 01:00:00", "2030-06-01 01:00:00"))
	assert mask.tolist() == [False, True, False, False, True, False]


def test_an_iso_window_matches_the_space_separated_snapshot_labels():
	"""The spelling a user types is the ISO one, and it must match.

	Pandas labels a snapshot ``2030-06-01 01:00:00``; ISO-8601 -- the CLI's
	documented grammar, ``datetime``'s output, and what anyone writes by hand --
	uses ``T``. Compared as raw strings the two never match, and the failure is
	the *correct* window being refused as matching no snapshot, which reads as
	the feature being broken rather than as a typo. This test exists because
	every other window test here spells the bound the way the implementation
	happened to want; it was written after an end-to-end CLI run with
	``--outage L1@2030-01-01T01:00..2030-01-01T02:00`` refused a window that
	plainly matched two snapshots.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "b1", carrier="AC")
	network.add("Line", "L1", bus0="b1", bus1="b1", x=0.1, r=0.01, s_nom=100.0)

	iso = outage_mask(network, LineOutage("L1", 0.0, "2030-01-01T02:00", "2030-01-01T04:00"))
	spaced = outage_mask(network, LineOutage("L1", 0.0, "2030-01-01 02:00", "2030-01-01 04:00"))
	assert iso.tolist() == [False, False, True, True, True, False]
	assert iso.tolist() == spaced.tolist()


def test_an_iso_date_only_bound_matches_that_whole_day():
	"""A date with no time is a valid ISO prefix, and a day is a window."""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "b1", carrier="AC")
	network.add("Line", "L1", bus0="b1", bus1="b1", x=0.1, r=0.01, s_nom=100.0)

	mask = outage_mask(network, LineOutage("L1", 0.0, "2030-01-01", "2030-01-01"))
	assert mask.tolist() == [True] * 6


# --------------------------------------------------------------------------
# The door: `alea whatif scenario --outage`
# --------------------------------------------------------------------------


def test_the_cli_parses_every_form_of_the_outage_grammar():
	"""The one route by which a user reaches an outage at all.

	Without this option the ``outages`` field would be declared, validated,
	applied by ``apply_parameters``, and reachable from nothing but a direct
	Python call -- the declared-is-not-produced class this module's whole
	existence is a defence against, recurring on the parameter that models the
	spec's headline scenario. So the grammar is gated at its four shapes.
	"""
	import typer

	from alea.cli import _parse_outages

	assert _parse_outages(None) is None, "no --outage must leave the default path untouched"

	whole = _parse_outages(["L1"])
	assert whole is not None
	assert whole.canonical() == [{"line": "L1", "factor": 0.0, "start": None, "end": None}]

	derate = _parse_outages(["L1:0.5"])
	assert derate is not None
	assert derate.canonical()[0]["factor"] == 0.5

	windowed = _parse_outages(["L1@2030-01-01T02:00..2030-01-01T05:00"])
	assert windowed is not None
	assert windowed.canonical() == [
		{"line": "L1", "factor": 0.0, "start": "2030-01-01T02:00", "end": "2030-01-01T05:00"}
	]

	both = _parse_outages(["L1:0.5@2030-01-01T02:00..2030-01-01T05:00"])
	assert both is not None
	assert both.canonical()[0] == {
		"line": "L1",
		"factor": 0.5,
		"start": "2030-01-01T02:00",
		"end": "2030-01-01T05:00",
	}

	# The `@`-before-`:` split, which is the one thing here that is not
	# arbitrary: an ISO timestamp contains colons, so splitting on `:` first
	# reads `L1@2030-01-01T02:00..2030-01-01T05:00` as line
	# `L1@2030-01-01T02` with factor `00..`. Asserted rather than assumed
	# because the whole windowed form depends on it.
	assert windowed.canonical()[0]["line"] == "L1"

	# Each refusal below is a distinct jurisdiction, and each is asserted by
	# the class it raises: a factor above 1 is a reinforcement rather than an
	# outage, a half-open window has unstated length, a non-numeric factor is
	# not a number, an inverted window matches no snapshot, and two records on
	# one line would make the scenario depend on the order they were listed in.
	for bad in (
		"",
		"L1:2.0",
		"L1@2030-01-01T02:00",
		"L1:abc",
		"L1@2030-01-01T05:00..2030-01-01T02:00",
	):
		with pytest.raises(typer.BadParameter):
			_parse_outages([bad])

	with pytest.raises(typer.BadParameter):
		_parse_outages(["L1", "L1:0.5"])
