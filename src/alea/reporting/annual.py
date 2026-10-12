# SPDX-License-Identifier: MIT
"""Annual report.

This is the report that gets cited, so it carries the fullest provenance and
the most prominent handling of unconfirmed figures. Every literature benchmark
inherited from ``spec/`` that is still unverified at this point is either
resolved against a source or printed with its status and the milestone at
which it will be resolved. It is never printed as though it were established.

The ``UNVERIFIED`` list below is derived from :data:`alea.quality.claims.REGISTER`,
which is where the ten claims of `12-quality.md` §6.1 live. It was a local
constant here holding four of the ten, reachable only from this cadence, with
nothing recording that any had been reviewed -- a register inside one report is
a register no milestone can review. Deriving it means the annual report prints
the whole register and the milestone gate reads the same ten entries.
"""

from __future__ import annotations

from alea.quality.claims import REGISTER
from alea.reporting.schemas import UnverifiedClaim
from alea.reporting.service import DataWindowSpec, SectionSpec

CADENCE = "annual"

SECTIONS: tuple[SectionSpec, ...] = (
	SectionSpec(
		slug="continental_outlook",
		title="Continental outlook",
		prose=(
			"Capacity, generation, and cost across all 55 AU member states under "
			"the central scenario. Values for the seven countries absent from "
			"the continental datasets are proxies and are marked as such in "
			"every row they appear in."
		),
		artefact="planning/continental/{date}.parquet",
		unit="MW",
		table_title="Continental capacity by power pool",
		columns=["Power pool", "Capacity", "Basis"],
		required=True,
	),
	SectionSpec(
		slug="investment_requirements",
		title="Investment requirements",
		prose="Capital requirement to 2060 by decade and by technology, and the gap against committed finance.",
		artefact="planning/investment/{date}.parquet",
		unit="USD",
		table_title="Investment requirement",
		columns=["Decade", "Requirement", "Committed", "Gap", "Basis"],
	),
	SectionSpec(
		slug="cmp_alignment",
		title="Continental Master Plan alignment",
		prose="How the modelled expansion compares with the Continental Master Plan's own generation and interconnection targets.",
		artefact="planning/cmp/{date}.parquet",
		unit="MW",
		table_title="Alignment against CMP targets",
		columns=["Element", "Modelled", "CMP target", "Basis"],
	),
	SectionSpec(
		slug="afsem_progress",
		title="AfSEM progress",
		prose="Progress against the African Single Electricity Market indicators, by power pool.",
		artefact="market/afsem/{date}.parquet",
		unit="",
		table_title="AfSEM indicators",
		columns=["Indicator", "Value", "Target", "Basis"],
	),
	SectionSpec(
		slug="just_transition",
		title="Just transition",
		prose="Employment and access indicators associated with the transition pathway.",
		artefact="sector/just_transition/{date}.parquet",
		unit="",
		table_title="Transition indicators",
		columns=["Indicator", "Value", "Basis"],
	),
	SectionSpec(
		slug="climate_scenarios",
		title="Climate scenarios",
		prose="System cost and reliability under the climate scenarios, with the range across the ensemble.",
		artefact="weather/scenarios/{date}.parquet",
		unit="USD",
		table_title="Cost under climate scenarios",
		columns=["Scenario", "System cost", "Reliability", "Basis"],
	),
)

# Literature benchmarks inherited from spec/ and not confirmed at planning
# time (web search was unavailable). Each carries the milestone at which it
# must be confirmed. An unresolved entry is printed in the report's unverified
# block; it is never printed as an established result.
UNVERIFIED: tuple[UnverifiedClaim, ...] = tuple(
	UnverifiedClaim(claim=entry.claim, milestone=entry.milestone, resolved=entry.resolved)
	for entry in REGISTER
)
"""Every claim in `12-quality.md` §6.1, derived rather than restated.

Ten entries, not four: the four that were here were the subset this cadence's
author had in mind, and a register that lives in one report is a register the
other nine claims are absent from. A resolved entry is one confirmed against a
source; an unresolved one appears in the report's unverified block, never in its
tables.
"""

WINDOWS: tuple[DataWindowSpec, ...] = ()

__all__ = ["CADENCE", "SECTIONS", "UNVERIFIED", "WINDOWS"]
