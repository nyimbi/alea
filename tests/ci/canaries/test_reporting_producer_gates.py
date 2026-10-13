# SPDX-License-Identifier: MIT
"""Canary for the required-section producer gates.

Three gates in `test_reporting_producers.py` are pinned rather than derived, and
each needs a canary that proves it can fail:

``test_a_required_section_with_no_producer_is_recorded`` was a tautology: it
built ``required & set(UNPRODUCED)`` and then asserted each member was in
``UNPRODUCED``, which is true by construction and cannot fail. It is now pinned
to a map of cadence to the one required section it cannot generate without.

``test_each_cadence_declares_exactly_one_required_section`` pins the shape
`UNPRODUCED`'s summary paraphrases. That summary said "four" where the measured
count is five, because it was retyped rather than derived -- so the gate that
makes the count structural needs the same proof as the map.

``test_the_market_entries_named_a_piece_that_has_now_arrived`` is the third, and
it is the one that *changed sides*. It used to pin ``_call_sites("BiddingUnit")
== 0`` -- the measurement that the fleet did not exist -- and closing that gap
made the assertion false, which is how the register shrinking is supposed to
work. The gate now pins the opposite: the fleet is constructed, and the module
that constructs it has a caller. The canary mutates the constructor call, so the
proof is about the new predicate rather than the old one.

``test_the_prose_count_of_unproduced_required_sections_matches_the_mapping`` is
the fourth, and it exists because the first two close the *shape* of the summary
without closing the summary itself. `UNPRODUCED`'s docstring said "Two of the
five are unproduced, so two cadences -- daily and annual" while `week_ahead` sat
in the mapping below it; the measured count was three. The map gates pin which
section belongs to which cadence and never read the number the prose reports, so
the sentence was free to describe a set it did not match -- the module's own
warning about unchecked summaries, drifted in the sentence making the warning.

**A canary is what proves a pinned assertion is a gate.** A pinned assertion is
only a check if a change to the thing it pins fails it. Each test below plants
the change its gate exists to notice and runs the real gate in a fresh
interpreter, because the mutations are source edits and the cadence modules are
imported at collection.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

PRODUCERS_PY = REPO / "src" / "alea" / "reporting" / "producers.py"
DAILY_PY = REPO / "src" / "alea" / "reporting" / "daily.py"

GATE_FILE = "tests/ci/test_reporting_producers.py"
UNPRODUCED_GATE = "test_a_required_section_with_no_producer_is_recorded"
SHAPE_GATE = "test_each_cadence_declares_exactly_one_required_section"
MISSING_PIECE_GATE = "test_the_market_entries_named_a_piece_that_has_now_arrived"
PROSE_COUNT_GATE = "test_the_prose_count_of_unproduced_required_sections_matches_the_mapping"
FLEET_PY = REPO / "src" / "alea" / "market" / "fleet.py"


def _gate_exit_code(test: str) -> int:
	"""Exit code of one gate in this module, run in a fresh interpreter.

	Through the shared `probe_exit_code`, which carries a timeout: a gate run
	that hangs used to hang its canary forever with the defect still planted in
	the source -- the 2026-10-13 leak, which left two mutated files in the tree.
	"""
	return probe_exit_code(
		"import sys, pytest; sys.exit(pytest.main([*sys.argv[1:]]))",
		GATE_FILE,
		"-q",
		"-x",
		"-k",
		test,
	)


def test_the_gate_catches_a_required_section_leaving_unproduced():
	"""The defect: a required section gains a producer and the map does not move.

	Deleting a required section's `UNPRODUCED` entry is exactly what closing its
	gap does -- the slug moves to `PRODUCERS` in the same change. If the pinned
	map is not updated with it, the gate must fail, or the map is documentation
	rather than a check. This plants the removal without the move.
	"""
	target = (
		'\t\t"week_ahead": (\n'
		'\t\t\t"A required weekly section with no producer at all: `planning/"\n'
		'\t\t\t"outlook/{date}.parquet` is declared by `reporting/weekly.py` and "\n'
		'\t\t\t"written by nothing. A required section whose artefact is absent "\n'
		'\t\t\t"raises `ReportDataError`, so the weekly report cannot currently be "\n'
		'\t\t\t"generated from the pipeline at all."\n'
		"\t\t),\n"
	)
	assert target in PRODUCERS_PY.read_text(), (
		"the canary target moved; `week_ahead` is no longer an `UNPRODUCED` entry "
		"in the form this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(UNPRODUCED_GATE) == 0, (
		"the required-producer gate does not pass on the shipped tree"
	)

	with planted(PRODUCERS_PY, target, ""):
		assert _gate_exit_code(UNPRODUCED_GATE) != 0, (
			"the gate passed with a required section removed from `UNPRODUCED` and "
			"the pinned map unchanged; it is derived from the register rather than "
			"checking it, so it cannot notice a cadence whose generatability moved"
		)

	assert _gate_exit_code(UNPRODUCED_GATE) == 0, "the restore was not proven"


def test_the_shape_gate_catches_a_cadence_gaining_a_second_required_section():
	"""The defect: the count the summary states stops matching the set.

	`UNPRODUCED`'s prose said four required sections and named four, dropping
	the daily cadence's -- and the count was retyped rather than derived, which
	is how it drifted. A second required section on the daily cadence is exactly
	the change that would make "one per cadence" false, so the gate that pins
	the shape must fail against it. Marking the optional `generation_mix`
	required is the minimal such change.
	"""
	target = '\t\tunit="MW",\n\t\ttable_title="Scheduled generation",\n'
	replacement = '\t\tunit="MW",\n\t\trequired=True,\n\t\ttable_title="Scheduled generation",\n'
	assert target in DAILY_PY.read_text(), (
		"the canary target moved; `generation_mix` is no longer the daily section "
		"this canary mutates, so the canary would be a no-op"
	)
	assert _gate_exit_code(SHAPE_GATE) == 0, "the shape gate does not pass on the shipped tree"

	with planted(DAILY_PY, target, replacement):
		assert _gate_exit_code(SHAPE_GATE) != 0, (
			"the shape gate passed with a cadence carrying two required sections; "
			"it cannot notice the change that makes the register's own count wrong"
		)

	assert _gate_exit_code(SHAPE_GATE) == 0, "the restore was not proven"


def test_the_missing_piece_gate_catches_the_fleet_losing_its_builder():
	"""The defect: the fleet module stays and nothing constructs a unit.

	The gate this canaries asserts that a `BiddingUnit` is constructed somewhere
	in `src/alea`, which is what distinguishes a fleet that is built from a
	module that exists. The mutation renames the *constructor call* to a name
	nothing defines, which is the shape of the defect the gate exists to notice:
	`market/fleet.py` still imports, still exports `build_fleet`, and still
	carries the string `BiddingUnit` in its body -- so a gate matching the
	*name* would pass. It matches the call shape, and the call is gone.

	The mutation is deliberately a superstring of the asserted text rather than
	an unrelated string: `BiddingUnitAlias(` contains `BiddingUnit`, and the
	predicate is ``\\bBiddingUnit\\s*\\(``. A canary that renamed it to something
	not containing the name would prove less -- it would pass even against a
	gate that matched a bare mention.
	"""
	target = "\t\t\tunit=BiddingUnit(\n"
	replacement = "\t\t\tunit=BiddingUnitAlias(\n"
	assert target in FLEET_PY.read_text(), (
		"the canary target moved; `fleet.py` no longer constructs a `BiddingUnit` "
		"in the form this canary expects, so the canary would be a no-op"
	)
	assert _gate_exit_code(MISSING_PIECE_GATE) == 0, (
		"the missing-piece gate does not pass on the shipped tree"
	)

	with planted(FLEET_PY, target, replacement):
		assert _gate_exit_code(MISSING_PIECE_GATE) != 0, (
			"the missing-piece gate passed with the fleet's only `BiddingUnit` "
			"construction renamed; it cannot notice the fleet losing its builder, "
			"so the two `PRODUCERS` entries would keep naming a producer that "
			"reads an empty fleet"
		)

	assert _gate_exit_code(MISSING_PIECE_GATE) == 0, "the restore was not proven"


def test_the_prose_count_gate_catches_a_summary_that_mislabels_the_set():
	"""The defect: the sentence states a count the mapping contradicts.

	The live instance, restored: `UNPRODUCED`'s docstring said "Two of the five
	are unproduced, so two cadences -- daily and annual" while `week_ahead` sat
	in the mapping below it. The map gates pin *which* section belongs to each
	cadence, so both passed; nothing read the number the prose reports, and the
	sentence described a set it did not match.

	The mutation puts the stale word back. It is the minimal true-to-life edit --
	one word, no structural change, every other gate still green -- which is
	exactly why it survived: an unchecked summary does not look like a defect,
	it looks like prose.
	"""
	target = "Three of the five are unproduced"
	replacement = "Two of the five are unproduced"
	assert target in PRODUCERS_PY.read_text(), (
		"the canary target moved; `UNPRODUCED`'s docstring no longer states the "
		"unproduced count in the form this canary expects, so the canary would be "
		"a no-op"
	)
	assert _gate_exit_code(PROSE_COUNT_GATE) == 0, (
		"the prose-count gate does not pass on the shipped tree"
	)

	with planted(PRODUCERS_PY, target, replacement):
		assert _gate_exit_code(PROSE_COUNT_GATE) != 0, (
			"the prose-count gate passed with the docstring saying two cadences "
			"cannot be generated while the mapping holds three; it is reading the "
			"prose rather than checking it against the set, so the summary stays "
			"free to describe a set it does not match"
		)

	assert _gate_exit_code(PROSE_COUNT_GATE) == 0, "the restore was not proven"
