# SPDX-License-Identifier: MIT
"""The `[UNVERIFIED]` register, and the milestone review that closes it.

`12-quality.md` §6.1 lists ten literature figures inherited from `spec/` when
web search was unavailable, each with the milestone at which it must be
reproduced or withdrawn. §9 criterion 5 asks that "the `[UNVERIFIED]` register
is reviewed at every milestone", and the plan states the cost of not doing it:

	A claim that stays in the codebase unverified past its milestone is a claim
	that will be quoted.

The register was in the code, but only as four entries inside the annual report
module -- four of the plan's ten, reachable from one cadence, with nothing
recording that any of them had been reviewed. A register that lives inside one
report is a register no milestone can review.

So the register moves here, where it is data rather than a report's local
constant, and :func:`review` answers the question §9 criterion 5 asks: which
claims are past their milestone and still unresolved. That is the difference
between a checklist someone is meant to consult and a check that fails when
nobody did.

The milestone order comes from `14-roadmap.md` §3 and is held as a sequence
rather than a date, because a milestone is reached when its gates pass, not when
a calendar says so -- the roadmap says as much: "it is a plan with checkable
gates, which means the estimate is falsifiable".
"""

from __future__ import annotations

from dataclasses import dataclass

MILESTONES: tuple[str, ...] = (
	"M0",
	"M1",
	"M2",
	"M3",
	"M4",
	"M5",
	"M6",
	"M7",
	"M8",
	"M9",
)
"""`14-roadmap.md` §3's milestones, in order.

A tuple rather than a date map: the roadmap's own position is that a milestone
is reached when its gates pass. Comparing a claim's milestone to the current one
is a comparison of *position*, and a calendar would make it a comparison of
elapsed time -- which is the estimate the roadmap explicitly says is not a
promise.
"""


@dataclass(frozen=True, slots=True)
class Claim:
	"""One literature figure, and what resolving it means.

	``resolution`` is the plan's own wording for the milestone action. It is not
	decoration: "reproduce or withdraw" and "measure precision vs. human review"
	are different pieces of work, and a reviewer reading the register at the
	milestone needs to know which one this claim needs.
	"""

	number: int
	claim: str
	milestone: str
	resolution: str
	resolved: bool = False
	"""Set when the claim has been reproduced, refuted, or withdrawn.

	Not settable by a report: a report *prints* the register, it does not decide
	what is true. The flag is edited by whoever does the work, and the review
	gate is what notices when nobody did.
	"""

	@property
	def milestone_index(self) -> int:
		"""Where this claim's milestone sits in the roadmap order."""
		if self.milestone not in MILESTONES:
			raise ValueError(
				f"claim {self.number} names milestone {self.milestone!r}, which "
				f"14-roadmap.md does not define; known: {', '.join(MILESTONES)}"
			)
		return MILESTONES.index(self.milestone)


REGISTER: tuple[Claim, ...] = (
	Claim(
		number=1,
		claim="VIIRS AUC 0.8346 (Ghana)",
		milestone="M2",
		resolution="Reproduce or withdraw",
	),
	Claim(
		number=2,
		claim="VIIRS 89.41% accuracy (Johannesburg)",
		milestone="M2",
		resolution="Reproduce or withdraw",
	),
	Claim(
		number=3,
		claim="Weather 99% accuracy (Adrar)",
		milestone="M2",
		resolution="Reproduce with base rate or withdraw",
	),
	Claim(
		number=4,
		claim="Maintenance 87%/64%/260% ROI (Nigeria)",
		milestone="M6",
		resolution="Reproduce from a stated cost model or withdraw",
	),
	Claim(
		number=5,
		claim="AMIRIS/ASSUME MAE 5.6-6.4 EUR/MWh",
		milestone="M8",
		resolution="Reproduce or withdraw",
	),
	Claim(
		number=6,
		claim="Losses ~20% expansion overestimate (PyPSA-Eur)",
		milestone="M1",
		resolution="Compute both ways on Kenya",
	),
	Claim(
		number=7,
		claim="Mixtral-8 91% outage flagging",
		milestone="M3",
		resolution="Measure precision vs. human review",
	),
	Claim(
		number=8,
		claim="Continental LOPF < 6 h on 128 cores",
		milestone="M7",
		resolution="Scale from local core-hours",
	),
	Claim(
		number=9,
		claim="Kenya geothermal 2 GW -> +8 GW solar, +EUR600M/yr",
		milestone="M1",
		resolution="Reproduce or record discrepancy",
	),
	Claim(
		number=10,
		claim="Egypt hydrogen sector-coupling validation",
		milestone="M5",
		resolution="Reproduce or record as unsupported",
	),
)
"""`12-quality.md` §6.1's ten claims, in the plan's own order and wording."""


def milestone_of(number: int) -> str:
	"""The milestone a claim must be resolved by."""
	for claim in REGISTER:
		if claim.number == number:
			return claim.milestone
	raise KeyError(f"no claim numbered {number} in the register")


def due_at(milestone: str, *, resolved: tuple[int, ...] = ()) -> list[Claim]:
	"""Claims whose milestone is ``milestone`` or earlier and that are unresolved.

	``resolved`` names the claim numbers that have been dealt with, so the
	review can be run against a set that differs from the module constant --
	which is what makes the gate checkable rather than a restatement of a
	hard-coded answer.
	"""
	if milestone not in MILESTONES:
		raise ValueError(f"unknown milestone {milestone!r}")
	position = MILESTONES.index(milestone)
	return [
		claim
		for claim in REGISTER
		if claim.milestone_index <= position and claim.number not in resolved
	]


@dataclass(frozen=True, slots=True)
class Review:
	"""What a milestone review found."""

	milestone: str
	due: tuple[Claim, ...]
	"""Claims past their milestone and unresolved."""

	@property
	def clean(self) -> bool:
		return not self.due

	@property
	def overdue(self) -> tuple[Claim, ...]:
		"""Claims whose own milestone has passed, not merely arrived."""
		position = MILESTONES.index(self.milestone)
		return tuple(c for c in self.due if c.milestone_index < position)


def review(milestone: str, *, resolved: tuple[int, ...] = ()) -> Review:
	"""Run §9 criterion 5's review for a milestone.

	Returns the claims that are past their milestone and still unresolved. An
	empty result is the criterion met; anything else is the "claim that will be
	quoted" the plan warns about.
	"""
	assert milestone in MILESTONES, f"unknown milestone {milestone!r}"
	return Review(milestone=milestone, due=tuple(due_at(milestone, resolved=resolved)))


__all__ = [
	"MILESTONES",
	"REGISTER",
	"Claim",
	"Review",
	"due_at",
	"milestone_of",
	"review",
]
