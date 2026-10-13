# SPDX-License-Identifier: MIT
"""Every declared report section is produced by something, or is a named gap.

The Layer 8 defect one layer up. `alea.publish.views` holds four registers and a
bidirectional gate over its eleven serving tables, so a serving table with no
producer is a recorded fact. Layer 6 declared 31 sections across five cadences
and held no register at all, and the render tests pass anyway -- because
`tests/fixtures/reporting` writes every declared path by hand. A fixture that
manufactures a section's input cannot see that no layer produces it: the section
renders perfectly in CI and warns "no artefact at ..." in production.

These tests are the gate for the class, not for one section. The first asserts
the register covers every declared slug and nothing else, so a section that
gains a producer must move between the two mappings in the same change.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from alea.reporting.producers import PRODUCERS, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import cadence_specs

REPO = Path(__file__).resolve().parents[2]


def _declared_slugs() -> set[str]:
	"""Every section slug the five cadence modules declare."""
	slugs: set[str] = set()
	for cadence in ReportCadence:
		specs, _ = cadence_specs(cadence)
		slugs.update(spec.slug for spec in specs)
	return slugs


def test_the_two_registers_partition_the_declared_sections():
	"""Produced and unproduced are disjoint, and together are the whole set.

	The bidirectional half. A section that gains a producer must leave
	``UNPRODUCED`` and enter ``PRODUCERS``; one that loses a producer moves the
	other way. If only one moved, the register would overstate or understate the
	gap and this fails.
	"""
	declared = _declared_slugs()
	recorded = set(PRODUCERS) | set(UNPRODUCED)

	unrecorded = sorted(declared - recorded)
	assert not unrecorded, (
		f"{len(unrecorded)} declared report section(s) are in no register: "
		f"{unrecorded}. A section nothing produces renders in CI (the fixture "
		f"writes its path by hand) and warns 'no artefact' in production, which "
		f"is indistinguishable from a working section until a report is "
		f"generated from the pipeline. Record it in `UNPRODUCED` with the "
		f"measured blocker, or produce it and record it in `PRODUCERS`."
	)

	stale = sorted(recorded - declared)
	assert not stale, (
		f"the register names {len(stale)} section(s) no cadence declares: "
		f"{stale}. A renamed or removed section leaves a stale entry that makes "
		f"the gap look larger than it is."
	)

	overlap = sorted(set(PRODUCERS) & set(UNPRODUCED))
	assert not overlap, (
		f"{overlap} are recorded as both produced and unproduced; the two "
		f"registers must partition the set"
	)


def test_every_unproduced_section_names_a_blocker():
	"""An unproduced section with no reason is an omission in a register's clothes."""
	for slug, reason in UNPRODUCED.items():
		assert reason.strip(), f"{slug!r} has no recorded blocker"
		assert len(reason) > 80, (
			f"{slug!r} has a reason too short to name a blocker: {reason!r}. "
			f"'needs a rule' and 'needs a model that does not exist' are "
			f"different amounts of work, and the register's job is to say which."
		)


def test_every_producer_names_something_that_exists():
	"""A producer name is a claim, and the claim is checkable.

	Reads the source text rather than importing, because the point is to catch a
	name that no module defines -- importing the module it claims to live in
	would only tell us the module parses.
	"""
	source = "\n".join(
		path.read_text(encoding="utf-8")
		for path in (REPO / "src" / "alea").rglob("*.py")
	)
	for slug, producer in PRODUCERS.items():
		assert producer.strip(), f"{slug!r} names an empty producer"
		# The producer is spelled `module.function` or a bare function name.
		leaf = producer.rsplit(".", 1)[-1]
		assert re.search(rf"\bdef {re.escape(leaf)}\b", source), (
			f"{slug!r} names the producer {producer!r}, and no module in "
			f"`src/alea` defines `{leaf}`. A producer that does not exist is a "
			f"gap wearing a register's clothes."
		)


def _call_sites(name: str) -> int:
	"""Call-shaped references to ``name`` in `src/alea`, outside its own definition.

	A function the register names as the *missing piece* of a gap is not the
	same as one that is wired: `clear_scenario` is defined, exported and called
	by nothing but its own tests, so "the producer is a rule over a cleared
	scenario" named a thing that does not happen.

	Counting *mentions* would not measure that -- the name appears in `__all__`
	and in `logger.info("clear_scenario", ...)` event labels, and a logger's
	event name is not a call. So this counts lines where the name is followed by
	an open paren and is not the definition or the class statement: the shape a
	call or a construction has.
	"""
	pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
	count = 0
	for path in (REPO / "src" / "alea").rglob("*.py"):
		for line in path.read_text(encoding="utf-8").splitlines():
			if line.lstrip().startswith(("def ", "class ")):
				continue
			if pattern.search(line):
				count += 1
	return count


def test_the_market_entries_named_a_piece_that_has_now_arrived():
	"""The claim these entries made was checkable, and it has been discharged.

	The `market_report` entry said the missing piece was *the fleet*, not the
	rule: "no module builds a market fleet from a solved network, so
	`clear_scenario` has no caller and `BiddingUnit` is constructed nowhere
	outside tests". That was measured, and it was right. `market/fleet.py` is
	that module now and `market/stages.py` runs it, so the count moved -- and
	the move is the prompt this gate exists to give.

	The two assertions below are the *inverse* of the ones they replace. Before,
	they pinned zero call sites and the entry's prose; a fleet builder is
	exactly what makes them non-zero, so pinning zero now would fail on the
	shipped tree. What they check instead is that the piece is genuinely wired
	and not merely written: a `BiddingUnit` constructed in a module no stage
	imports is the same defect one level down, and `build_fleet_series` having a
	caller in `market/service.py` is what distinguishes the two.

	This pins the measurement, not the wording. When the *next* entry's blocker
	is closed, this fails again, which is the prompt to rewrite it -- the same
	discipline as the required-section map.
	"""
	assert "market_report" not in UNPRODUCED, (
		"`market_report` is back in `UNPRODUCED` after being produced; a section "
		"that lost its producer is a cadence that can no longer be generated, and "
		"this gate must say which piece went missing again rather than passing"
	)
	assert _call_sites("BiddingUnit") > 0, (
		"no module in `src/alea` constructs a `BiddingUnit`, so the market fleet "
		"the entries named as the missing piece is not being built -- and the two "
		"slugs in `PRODUCERS` would be naming a producer that reads an empty fleet"
	)
	assert _call_sites("build_fleet_series") > 0, (
		"`build_fleet_series` has no caller in `src/alea`, so `market/fleet.py` "
		"exists and nothing runs it. The monthly and quarterly producers clear "
		"`build_fleet_series`'s output; a fleet module with no caller is the "
		"written-but-unwired shape this register exists to tell apart from a "
		"produced section"
	)


#: The required section each cadence cannot generate without, while it has no
#: producer. Pinned rather than derived, because the derived form -- intersect
#: the required set with `UNPRODUCED` -- is a tautology: every slug in it is in
#: `UNPRODUCED` by construction, so the assertion cannot fail and would keep
#: passing if a cadence gained a second unproduced required section or lost its
#: only one. The map is what makes closing a gap, or opening one, move a test.
REQUIRED_WITHOUT_A_PRODUCER: dict[str, str] = {
	"daily": "outage_forecast",
	"weekly": "week_ahead",
	"annual": "continental_outlook",
}
"""One per cadence that cannot be generated from the pipeline, and that is the
measured state: three of the five cadences have a required section with no
producer. The map started with all five and lost two in one change -- the
monthly and quarterly sections, whose shared blocker was the market fleet.

A cadence whose required section *has* a producer is absent from this map rather
than mapped to `None`: the assertion below compares against `.get(cadence)`, so
absence is the state that means "generatable", and an entry saying so would be a
second way to spell the same thing."""


@pytest.mark.parametrize("cadence", list(ReportCadence), ids=lambda c: c.value)
def test_each_cadence_declares_exactly_one_required_section(cadence: ReportCadence):
	"""The structural fact the register's prose paraphrases, pinned as a check.

	`UNPRODUCED`'s module docstring said "Four sections are `required=True`" and
	named four, dropping the daily cadence's `outage_forecast` -- so it also said
	"four of the five cadences cannot be generated" where the measured state is
	five of five. The prose is a *summary of this set*, and a summary that is not
	checked drifts the way that one did. This pins the shape the summary rests
	on: exactly one required section per cadence, so "one per cadence" is a fact
	a reader can rely on and the count is `len(ReportCadence)`, not a number
	someone retypes.
	"""
	specs, _ = cadence_specs(cadence)
	required = [spec.slug for spec in specs if spec.required]
	assert len(required) == 1, (
		f"{cadence.value} declares {len(required)} required sections ({required}); "
		f"the register's summary and the pinned required-section map both assume "
		f"exactly one per cadence. A cadence with two is a cadence whose "
		f"generatability depends on both, and a cadence with none is one the "
		f"summary overstates."
	)


@pytest.mark.parametrize("cadence", list(ReportCadence), ids=lambda c: c.value)
def test_a_required_section_with_no_producer_is_recorded(cadence: ReportCadence):
	"""A required section that is absent raises; that must not be a surprise.

	A required section's artefact being missing is a hard `ReportDataError`, not
	a warning -- so a cadence whose required section has no producer cannot be
	generated from the pipeline at all. The pinned map states which section that
	is per cadence, so this fails when the set changes in either direction: a
	cadence that gains a second unproduced required section is a cadence further
	from generating, and one that gains a producer is a line to delete.
	"""
	specs, _ = cadence_specs(cadence)
	required = {spec.slug for spec in specs if spec.required}
	unproduced = sorted(required & set(UNPRODUCED))

	expected = REQUIRED_WITHOUT_A_PRODUCER.get(cadence.value)
	assert unproduced == ([expected] if expected else []), (
		f"{cadence.value}'s required-and-unproduced set is {unproduced}, and the "
		f"pinned register says {expected!r}. A section that gained a producer "
		f"moves out of `UNPRODUCED` and this map must drop it; a required section "
		f"that lost its producer is a cadence that can no longer be generated, "
		f"and the map must gain it."
	)
