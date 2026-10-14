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

	**The target moved, and that is the canary working.** It used to plant the
	removal of `week_ahead`'s entry, because `week_ahead` was the weekly cadence's
	unproduced required section. Closing the weekly gap removed that entry for
	real, so the canary now plants the removal of `outage_forecast`'s -- the daily
	cadence's, and the one the register still holds. A canary whose target no
	longer exists is a canary that never runs, which is why the `assert` below is
	load-bearing rather than defensive.
	"""
	target = (
		'\t\t"outage_forecast": (\n'
		'\t\t\t"Two gaps, and this entry named only the smaller one. It read "\n'
		'\t\t\t"\\"needs a rule, and a projection\\", which is the *shape* of the gap "\n'
		'\t\t\t"and not its size: `outages.forecast_to_artefact` writes "\n'
		'\t\t\t"`Forecaster.metrics` -- PR-AUC, recall at precision, the base rate "\n'
		'\t\t\t"-- which is a statement about the *model*, and the section asks for a "\n'
		'\t\t\t"probability per line. Nothing in the repository turns a fitted "\n'
		'\t\t\t"`Forecaster` into those rows: `predict_proba` exists and no caller "\n'
		'\t\t\t"reaches it, and the function has no caller at all. **The second gap "\n'
		'\t\t\t"is the interval.** The section declares "\n'
		'\t\t\t"`[\\"Line\\", \\"Probability\\", \\"Interval\\", \\"Basis\\"]` and "\n'
		'\t\t\t"`assemble.py` reads a band from `interval_low`/`interval_high`; "\n'
		'\t\t\t"`ForecastMetrics` has no interval field and the forecaster has no "\n'
		'\t\t\t"calibration function, so the band the module docstring promises "\n'
		'\t\t\t"(`a 12% forecast rendered as a fact`) has neither a producer nor a "\n'
		'\t\t\t"method. A rule over the current function would deliver metrics under "\n'
		'\t\t\t"a heading promising probabilities. So: a forward-prediction "\n'
		'\t\t\t"producer (the features are calendar plus lagged outage rate, both "\n'
		'\t\t\t"computable ahead of the horizon), an interval method that is a "\n'
		'\t\t\t"modelling decision to be made and recorded, a projection, and a rule."\n'
		"\t\t),\n"
	)
	assert target in PRODUCERS_PY.read_text(), (
		"the canary target moved; `outage_forecast` is no longer an `UNPRODUCED` "
		"entry in the form this canary expects, so the canary would be a no-op"
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

	The mutation is the minimal true-to-life edit -- one word, no structural
	change, every other gate still green -- which is exactly why it survived: an
	unchecked summary does not look like a defect, it looks like prose.

	**The planted word follows the register.** Closing the weekly gap moved the
	true count from three to two, so the mutation now plants *three* -- the
	number that was correct until the move. Planting the old direction (two, the
	number that used to be wrong) would plant the shipped value and the canary
	would pass against a gate that had stopped reading.
	"""
	target = "Two of the five are unproduced"
	replacement = "Three of the five are unproduced"
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
