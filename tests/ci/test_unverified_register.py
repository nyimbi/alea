# SPDX-License-Identifier: MIT
"""`12-quality.md` §6.1's `[UNVERIFIED]` register, and §9 criterion 5's review.

The criterion reads "the `[UNVERIFIED]` register is reviewed at every milestone",
and the plan's gate column says "Milestone checklist" -- which is to say there
was no mechanism, only a habit someone was meant to have. The cost is stated two
paragraphs above it: "a claim that stays in the codebase unverified past its
milestone is a claim that will be quoted."

Two things are checked here:

1. **The register is the plan's.** Ten claims, the plan's own numbering, the
   plan's own milestones. Parsed out of `12-quality.md` rather than restated,
   because a register that drifts from the document it claims to be is the
   defect the register exists to prevent. Note the plan's table uses an en dash
   and a euro sign; the code uses ASCII, so the comparison normalises
   punctuation rather than the words.

2. **The review finds what is due.** A claim past its milestone and unresolved
   must be reported; a resolved one must not. That is what turns the checklist
   into a check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from alea.quality import MILESTONES, REGISTER, review
from alea.quality.claims import due_at, milestone_of

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / "docs" / "plans" / "12-quality.md"

_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(M\d+)\s*\|\s*(.+?)\s*\|\s*$")


def _normalise(text: str) -> str:
	"""Fold the punctuation the plan's markdown uses and the code does not."""
	return (
		text.replace("–", "-")  # en dash in "5.6-6.4"
		.replace("→", "->")  # arrow in the geothermal claim
		.replace("€", "EUR")  # euro sign
		.replace("**", "")
		.strip()
	)


def _plan_rows() -> list[tuple[int, str, str, str]]:
	"""The plan's §6.1 table, parsed from the document."""
	text = PLAN.read_text(encoding="utf-8")
	section = text.split("### 6.1 The `[UNVERIFIED]` register", 1)[1].split("### 6.2", 1)[0]
	rows: list[tuple[int, str, str, str]] = []
	for line in section.splitlines():
		match = _ROW.match(line)
		if match:
			rows.append(
				(int(match.group(1)), _normalise(match.group(2)), match.group(3), _normalise(match.group(4)))
			)
	return rows


def test_the_register_holds_the_plans_ten_claims():
	"""§6.1 lists ten; the code held four, in one cadence, with no review."""
	rows = _plan_rows()
	assert len(rows) == 10, f"§6.1's table parsed as {len(rows)} rows, expected 10"
	assert len(REGISTER) == 10, f"the register holds {len(REGISTER)} claims, §6.1 lists 10"
	assert [c.number for c in REGISTER] == [r[0] for r in rows], (
		"the register's numbering differs from §6.1's table"
	)


@pytest.mark.parametrize("row", _plan_rows(), ids=lambda r: f"claim{r[0]}")
def test_each_claim_matches_the_plan(row: tuple[int, str, str, str]):
	"""Every claim's text, milestone and resolution come from the document.

	Parametrised so a drift names the claim rather than the table.
	"""
	number, claim, milestone, resolution = row
	entry = next((c for c in REGISTER if c.number == number), None)
	assert entry is not None, f"§6.1 lists claim {number} and the register does not"

	assert _normalise(entry.claim) == claim, (
		f"claim {number}'s text drifted from §6.1:\n  plan: {claim}\n  code: {entry.claim}"
	)
	assert entry.milestone == milestone, (
		f"claim {number} resolves at {milestone} in §6.1 and {entry.milestone} in the code"
	)
	assert _normalise(entry.resolution) == resolution, (
		f"claim {number}'s resolution drifted:\n  plan: {resolution}\n  code: {entry.resolution}"
	)


def test_every_milestone_is_one_the_roadmap_defines():
	"""A claim keyed to a milestone the roadmap does not have cannot be reviewed.

	`14-roadmap.md` §3 runs M0 to M9; a claim naming M10 would sit in the
	register forever, never due and never overdue.
	"""
	for claim in REGISTER:
		assert claim.milestone in MILESTONES, (
			f"claim {claim.number} names {claim.milestone}, which the roadmap does not define"
		)


def test_the_review_reports_a_claim_past_its_milestone():
	"""§9 criterion 5 as a gate: an unresolved claim at its milestone is due.

	M1 is where claims #6 and #9 resolve, so a review at M1 must name both. If
	the review returned nothing, the criterion would be "met" by a register
	nobody had touched -- which is the shape of a check that measures nothing.
	"""
	result = review("M1")
	assert not result.clean, "the review found nothing due at M1; it is measuring nothing"
	numbers = {c.number for c in result.due}
	assert {6, 9} <= numbers, f"M1 resolves claims 6 and 9; the review reported {sorted(numbers)}"
	assert result.overdue == (), "nothing is overdue at M1; the earliest milestones are M1"


def test_the_review_is_clean_before_any_milestone_is_due():
	"""The negative half. A review that reported everything due at M0 would make
	the gate useless in the other direction -- it would fail on a clean tree and
	be switched off."""
	assert review("M0").clean, "M0 resolves nothing, yet the review reports claims due"


def test_resolving_a_claim_removes_it_from_the_review():
	"""``resolved`` is what closes a claim, and the review must honour it.

	Without this, the register could only ever report every claim forever, which
	is a list rather than a review.
	"""
	due = {c.number for c in due_at("M2")}
	assert {1, 2, 3, 6, 9} <= due, f"M2 resolves claims 1, 2, 3 and M1's 6 and 9; got {sorted(due)}"

	after = {c.number for c in due_at("M2", resolved=(1, 2, 3, 6, 9))}
	assert not ({1, 2, 3, 6, 9} & after), (
		f"a resolved claim is still reported as due: {sorted(after)}"
	)


def test_a_claim_is_overdue_only_after_its_own_milestone():
	"""Due at M2 means M2 is when it must be done, not when it was late."""
	result = review("M2")
	overdue = {c.number for c in result.overdue}
	assert 6 in overdue and 9 in overdue, "M1's claims are overdue once M2 has arrived"
	assert not ({1, 2, 3} & overdue), "M2's own claims are due, not overdue, at M2"


def test_the_annual_report_carries_the_whole_register():
	"""The report and the gate must read one register, not two.

	The annual report's `UNVERIFIED` was a local constant holding four of the ten
	-- a register inside one cadence is a register no milestone can review, and
	two lists that agree today are not one source of truth.
	"""
	from alea.reporting.annual import UNVERIFIED

	assert len(UNVERIFIED) == len(REGISTER), (
		f"the annual report carries {len(UNVERIFIED)} claims and the register "
		f"{len(REGISTER)}; the report is not deriving from it"
	)
	assert {u.claim for u in UNVERIFIED} == {c.claim for c in REGISTER}


def test_milestone_of_is_the_lookup_the_cli_uses():
	"""A small function, checked because the CLI's review depends on it."""
	assert milestone_of(6) == "M1"
	with pytest.raises(KeyError):
		milestone_of(99)
