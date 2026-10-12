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


#: The required section each cadence cannot generate without, while it has no
#: producer. Pinned rather than derived, because the derived form -- intersect
#: the required set with `UNPRODUCED` -- is a tautology: every slug in it is in
#: `UNPRODUCED` by construction, so the assertion cannot fail and would keep
#: passing if a cadence gained a second unproduced required section or lost its
#: only one. The map is what makes closing a gap, or opening one, move a test.
REQUIRED_WITHOUT_A_PRODUCER: dict[str, str] = {
	"daily": "outage_forecast",
	"weekly": "week_ahead",
	"monthly": "market_report",
	"quarterly": "market_outlook",
	"annual": "continental_outlook",
}
"""One per cadence, and that is the measured state: every cadence has exactly
one required section and none has a producer, so no cadence can be generated
from the pipeline. The first to close shrinks this map by one."""


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
