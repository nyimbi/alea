# SPDX-License-Identifier: MIT
"""The equation library: the twenty systems, and what each one is for.

WHY the systems are enumerated here rather than inferred from the equations.
A system is a *claim about coverage* -- "energy balance is modelled", "the
financial identities are modelled" -- and a system inferred from whatever
equations happen to exist cannot state that a system is empty. The empty ones
are the finding: a PRG with no affordability equations is a PRG that will
happily accept a tariff no household can pay, and the register that says so is
worth more than the equations that exist.

Each system carries the layer of the model it belongs to and the source of its
relationships, so a reader can tell a Kirchhoff identity from a policy
constraint without opening the YAML.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from alea.config.paths import repo_root
from alea.prg.views import Equation

__all__ = [
	"SPEC_SYSTEM_COUNT",
	"SPEC_TO_SYSTEM",
	"SYSTEM_IDS",
	"SYSTEMS",
	"System",
	"coverage",
	"spec_systems",
	"systems_of",
	"unclaimed_spec_systems",
]


@dataclass(frozen=True)
class System:
	"""One of the equation systems ``params-prg1.md`` §2 defines."""

	id: str
	name: str
	#: Which class of coupling from ``params-prg1.md`` §2 this system states.
	coupling: str
	#: Why the system exists, in the terms a reviewer of the physics uses.
	purpose: str


#: The systems the PRG is specified to hold. The list is the specification's,
#: not the equations': an equation whose ``system`` is not here is a load error,
#: because a system nobody enumerated is a coupling nobody claimed.
SYSTEMS: tuple[System, ...] = (
	System(
		"energy_balance",
		"Energy Balance",
		"physical_law",
		"Generation, storage, flow and demand balance at every node and hour. "
		"A violation is a system that does not clear.",
	),
	System(
		"cost_accounting",
		"Cost Accounting",
		"accounting_identity",
		"Cost is capex plus opex plus fuel; LCOE and the capital recovery "
		"factor are definitions, not estimates.",
	),
	System(
		"emissions",
		"Emissions Accounting",
		"accounting_identity",
		"Emissions are generation times an emission factor; the carbon cost is "
		"those emissions times a price and a coverage share.",
	),
	System(
		"demand_supply",
		"Demand-Supply Equilibrium",
		"economic_relationship",
		"Clearing, elasticity and the surplus identities that make a price "
		"mean something.",
	),
	System(
		"financial",
		"Financial Identities",
		"accounting_identity",
		"WACC, CAPM, DSCR, LLCR and the debt-sizing inequality a lender "
		"actually applies.",
	),
	System(
		"learning",
		"Learning Curves",
		"economic_relationship",
		"Cost falls with cumulative deployment at a stated learning rate. The "
		"one system whose equations are non-linear in every parameter.",
	),
	System(
		"reserve_margin",
		"Reserve Margin",
		"technical_constraint",
		"Firm capacity against peak demand, with VRE derated by a capacity "
		"credit factor.",
	),
	System(
		"inertia",
		"System Inertia",
		"technical_constraint",
		"Synchronous inertia against the largest credible loss. Bounds the "
		"instantaneous renewable share.",
	),
	System(
		"capture_price",
		"Capture Price",
		"economic_relationship",
		"Cannibalisation: the more VRE on the system, the lower the price it "
		"receives, which is the feedback the PRG exists to make visible.",
	),
	System(
		"reliability",
		"Reliability",
		"economic_relationship",
		"Expected unserved energy and the value of lost load, which is the "
		"cost of the reliability a build buys.",
	),
	System(
		"carbon_trajectory",
		"Carbon Trajectory",
		"policy_constraint",
		"A cumulative budget over a horizon, and the price path that meets it.",
	),
	System(
		"affordability",
		"Affordability",
		"policy_constraint",
		"Tariff against household income. The system that stops a scenario "
		"being cost-optimal and socially impossible at once.",
	),
	System(
		"water_energy",
		"Water-Energy Nexus",
		"physical_law",
		"Cooling and hydrogen water demand against availability. A build that "
		"clears on cost can still be one the catchment cannot supply.",
	),
	System(
		"employment",
		"Employment",
		"accounting_identity",
		"Direct, indirect and induced jobs from capacity and generation. The "
		"system that makes a build programme a claim about people.",
	),
	System(
		"health",
		"Health Impact",
		"economic_relationship",
		"Premature deaths and DALYs from PM2.5, which is what the emissions "
		"system costs in lives rather than in dollars.",
	),
	System(
		"ppa_pricing",
		"PPA Pricing",
		"economic_relationship",
		"Contract price from cost, risk and availability. The price a project "
		"actually signs at, which is not its LCOE.",
	),
)


_BY_ID = {system.id: system for system in SYSTEMS}

#: The system identifiers, for a caller that needs the set and not the objects.
SYSTEM_IDS: frozenset[str] = frozenset(_BY_ID)

#: How many systems ``params-prg1.md`` §4 enumerates, as
#: ``### 4.N System N: Name`` headings.
#:
#: Deliberately a literal, and not ``len(spec_systems())``. This is the
#: *claim*; :func:`spec_systems` is the witness, and the test asserts the two
#: agree. Deriving the expected count from the document would make the check
#: vacuous -- it would pass on a document that enumerated twelve systems or
#: two hundred. A register that counts itself is not a register.
SPEC_SYSTEM_COUNT = 20


#: Which library system answers each of the specification's §4 headings.
#:
#: The specification enumerates twenty headings and this library holds
#: sixteen systems, and the difference is not an omission: four of the
#: specification's headings are refinements of a system already here. System 15
#: and 16 are the two halves of the capture-price loop; System 17 is the carbon
#: trajectory; System 18 is the learning curve; System 19 is debt sizing, which
#: is part of the financial identities. Recording the mapping rather than
#: forcing a one-to-one correspondence is what makes the coverage claim
#: checkable: every heading is claimed by a system, and a heading nobody claims
#: is a finding.
SPEC_TO_SYSTEM: dict[str, str] = {
	"Energy Balance": "energy_balance",
	"Cost Accounting": "cost_accounting",
	"Emissions Accounting": "emissions",
	"Demand-Supply Equilibrium": "demand_supply",
	"Financial Identities": "financial",
	"Learning Curves": "learning",
	"Reserve Margin": "reserve_margin",
	"Inertia Constraint": "inertia",
	"Water-Energy Nexus": "water_energy",
	"Capture Price": "capture_price",
	"Reliability Indices": "reliability",
	"Employment": "employment",
	"Health Impact": "health",
	"Affordability": "affordability",
	"Feedback Loop — Price-Demand": "capture_price",
	"Feedback Loop — VRE Investment": "capture_price",
	"Carbon Price Trajectory": "carbon_trajectory",
	"Technology Cost Trajectory": "learning",
	"Debt Sizing": "financial",
	"PPA Pricing": "ppa_pricing",
}


def unclaimed_spec_systems(path: Path | None = None) -> list[str]:
	"""Specification §4 headings no library system claims.

	A heading the specification enumerates and this library does not map is a
	system the platform was specified to model and does not. It is the same
	finding as an empty system, one level up: the register would otherwise
	report full coverage of a document it had quietly stopped reading.
	"""
	return sorted(set(spec_systems(path)) - set(SPEC_TO_SYSTEM))


def spec_systems(path: Path | None = None) -> dict[str, str]:
	"""The systems ``params-prg1.md`` §4 enumerates, as ``{name: coupling}``.

	Read from the document rather than transcribed, because a transcribed list
	is a second copy that drifts. The heading carries the name and the
	parenthetical carries the coupling class; both are what this library's
	``System`` records, so the comparison is between two records of the same
	thing and not between a record and a restatement of it.
	"""
	import re

	document = path or (repo_root() / "docs" / "params-prg1.md")
	text = document.read_text()
	# A restructured document that matches no heading returns an empty dict,
	# and the caller's count check then reports "0 != 20" -- a true statement
	# about the wrong thing, because the failure is the *pattern* and not the
	# document's content. Refusing here names the real cause.
	if "### 4." not in text:
		raise ValueError(
			f"{document} holds no '### 4.' section heading; `spec_systems` "
			f"reads the systems from that section and a document without it "
			f"cannot be checked against this library"
		)
	found: dict[str, str] = {}
	for match in re.finditer(
		r"^### 4\.\d+ System \d+: (?P<name>[^\n(]+?)(?: \((?P<coupling>[^)]*)\))?\s*$",
		text,
		flags=re.MULTILINE,
	):
		found[match.group("name").strip()] = (match.group("coupling") or "").strip()
	if not found:
		raise ValueError(
			f"{document} has a '### 4.' section but no heading matches "
			f"'### 4.N System N: Name (Coupling)'; the section was restructured "
			f"and this reader no longer parses it"
		)
	return found


def systems_of(equations: dict[str, Equation]) -> dict[str, tuple[Equation, ...]]:
	"""Group equations by system, in the specification's order."""
	grouped: dict[str, list[Equation]] = defaultdict(list)
	for equation in equations.values():
		if equation.system not in _BY_ID:
			raise ValueError(
				f"equation {equation.id!r} declares system "
				f"{equation.system!r}, which is not one of "
				f"{sorted(_BY_ID)}; an unenumerated system is a coupling "
				f"nobody has claimed, so nothing checks whether it is complete"
			)
		grouped[equation.system].append(equation)
	return {
		system.id: tuple(sorted(grouped.get(system.id, ()), key=lambda e: e.id))
		for system in SYSTEMS
	}


def coverage(equations: dict[str, Equation]) -> list[str]:
	"""The systems with no equations, as findings rather than as silence.

	A system with zero equations is not an error -- the library is built
	incrementally -- but it is the difference between "affordability is not
	modelled yet" and "affordability is modelled and nothing violates it",
	which read identically from a consistency report that lists no violations.
	"""
	return [
		f"{system.id}: {system.purpose}"
		for system in SYSTEMS
		if not any(e.system == system.id for e in equations.values())
	]
