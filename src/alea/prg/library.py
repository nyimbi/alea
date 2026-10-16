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
from typing import Any

from alea.config import paths
from alea.prg.views import Equation

__all__ = [
	"SPEC_EQUATION_COUNT",
	"SPEC_SYSTEM_COUNT",
	"SPEC_TO_SYSTEM",
	"SYSTEM_IDS",
	"SYSTEMS",
	"System",
	"coverage",
	"equation_coverage",
	"spec_equation_deficit",
	"spec_equations",
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
		"price_demand",
		"Price-Demand Feedback",
		"feedback",
		"A tariff and the demand it clears are a fixed point, not a chain: "
		"demand sets the price that sets the demand. The specification's "
		"System 15, and the loop the library did not hold until 2026-10-15 -- "
		"the capture-price loop is the VRE-investment one and answers a "
		"different question.",
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
#: seventeen systems, and the difference is not an omission: three of the
#: specification's headings are refinements of a system already here. System 16
#: is the capture-price loop; System 17 is the carbon trajectory; System 18 is
#: the learning curve; System 19 is debt sizing, which is part of the financial
#: identities. Recording the mapping rather than forcing a one-to-one
#: correspondence is what makes the coverage claim checkable: every heading is
#: claimed by a system, and a heading nobody claims is a finding.
#:
#: The heading *names* come from ``params-prg1.md`` §4, which spells System 15
#: and 16 as ``Feedback Loop — Price-Demand`` / ``— VRE Investment``. The
#: ``alea_prg.md`` §13 table calls the same two ``Price-Demand Feedback`` and
#: ``VRE Investment Feedback``. Both spellings are mapped, because a heading
#: the reader recognises under one document and not the other is a heading
#: reported unclaimed while it is in fact modelled -- a false finding, which is
#: worse than no finding at all.
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
	"Feedback Loop — Price-Demand": "price_demand",
	"Price-Demand Feedback": "price_demand",
	"Feedback Loop — VRE Investment": "capture_price",
	"VRE Investment Feedback": "capture_price",
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


#: How many equations ``alea_prg.md`` §13 enumerates per system, as ``### 13``
#: headings and ``| `id` |`` table rows.
#:
#: Deliberately literals, and not ``len(spec_equations())``. This is the
#: *claim*; :func:`spec_equations` is the witness, and the test asserts the two
#: agree. Deriving the expected count from the document would make the check
#: vacuous -- it would pass on a document that enumerated three equations or
#: three hundred. A register that counts itself is not a register.
#:
#: Keyed by the spec's own system *name* (§13 spells them ``Energy Balance``,
#: ``Price-Demand Feedback``), not by a library id, because the two documents
#: do not agree on ids and mapping the count through ``SPEC_TO_SYSTEM`` would
#: hide exactly the spelling drift this register exists to surface.
SPEC_EQUATION_COUNT: dict[str, int] = {
	"Energy Balance": 5,
	"Cost Accounting": 7,
	"Emissions Accounting": 5,
	"Demand-Supply Equilibrium": 5,
	"Financial Identities": 8,
	"Learning Curves": 4,
	"Reserve Margin": 4,
	"Inertia Constraint": 3,
	"Water-Energy Nexus": 4,
	"Capture Price": 4,
	"Reliability Indices": 6,
	"Employment": 4,
	"Health Impact": 3,
	"Affordability": 3,
	"Price-Demand Feedback": 3,
	"VRE Investment Feedback": 4,
	"Carbon Price Trajectory": 3,
	"Technology Cost Trajectory": 3,
	"Debt Sizing": 4,
	"PPA Pricing": 3,
}


def spec_equations(path: Path | None = None) -> dict[str, tuple[str, ...]]:
	"""The equation ids ``alea_prg.md`` §13 enumerates, as ``{system: ids}``.

	Read from the document rather than transcribed, for the same reason
	:func:`spec_systems` is: a transcribed list is a second copy that drifts.

	WHY this exists beside :func:`spec_systems`. The system-coverage register
	counted *headings*, and a heading is a claim about a system, not about its
	contents. The library held sixteen of the specification's twenty headings,
	mapped all twenty, and reported ``unclaimed_spec_systems() == []`` -- while
	nine of the specification's eighty-three distinct equations existed in the
	graph. A register whose predicate is one level coarser than the thing it
	measures reports clean about a document it is not reading. Counting the
	equations is what makes the deficit a number instead of a silence.

	``§13`` is the only section that carries the table; ``params-prg1.md`` §4
	enumerates the same twenty systems with prose and no equation ids, so a
	reader pointed at the wrong document would return an empty mapping and the
	caller would report "0 of 20 systems have equations" -- a true statement
	about the wrong thing. Refusing names the cause.
	"""
	import re

	document = path or (paths.repo_root() / "docs" / "alea_prg.md")
	text = document.read_text()
	marker = "### 13. Equation Systems"
	if marker not in text:
		raise ValueError(
			f"{document} holds no {marker!r} heading; `spec_equations` reads "
			f"the equation tables from that section and a document without it "
			f"cannot be checked against this library"
		)
	# Bounded at §14, so a later table of equation ids in another section is
	# not silently folded into this one's counts.
	start = text.index(marker)
	end = text.find("### 14.", start)
	section = text[start : end if end != -1 else len(text)]

	found: dict[str, list[str]] = {}
	current: str = ""
	for line in section.splitlines():
		heading = re.match(r"^#### System \d+: (?P<name>.+?)\s*$", line)
		if heading:
			current = heading.group("name")
			found[current] = []
			continue
		# A table row's first cell is the equation id, backticked. Anything
		# else -- the header row, the separator, prose -- is not an equation.
		row = re.match(r"^\| `(?P<id>[^`]+)` \|", line)
		if row and current:
			found[current].append(row.group("id"))
	if not found:
		raise ValueError(
			f"{document} has a {marker!r} section but no heading matches "
			f"'#### System N: Name'; the section was restructured and this "
			f"reader no longer parses it"
		)
	return {name: tuple(ids) for name, ids in found.items()}


def spec_equation_deficit(
	equations: dict[str, Equation], path: Path | None = None
) -> dict[str, dict[str, Any]]:
	"""Per specification system: equations enumerated, and the library's count.

	The register :func:`coverage` should always have been. ``coverage`` reports
	a system with *zero* equations, which catches a wholly unbuilt system and
	misses a system built to a fifth of its specification -- and the second is
	the common case here: Reliability is specified with six equations and holds
	two, Emissions five and one. Both read as "modelled" to a register that
	counts headings and as "not empty" to one that counts zeroes.

	WHY ``graph`` is the *mapped library system's* equation count and not the
	count of the specification's ids the library happens to use. Those two
	answer different questions and the second is a false finding here: the
	library implements what §13 calls ``capture_price`` as
	``capture_price_equation``, so an id-level count reports
	``Capture Price spec=4 graph=0`` about a system holding four equations.
	A register that enumerates one of the two ways to spell an equation is a
	register reporting a deficit that does not exist -- and a false finding
	costs more than a missing one, because it sends a reader to build something
	already there. ``ids_missing`` carries the id-level detail, where the
	strictness is a fact about naming rather than a claim about coverage.

	Returns one entry per system the specification enumerates, so a system
	present in the document and absent from the library reports
	``spec=6, graph=0`` rather than being omitted -- an omission in a coverage
	report is the failure it was written to catch.

	``shared_with`` names another specification heading that maps to the same
	library system, because the specification's twenty headings are seventeen
	systems: three are refinements of a system already here, so adding the
	``graph`` column across all twenty double-counts those three.
	"""
	enumerated = spec_equations(path)
	held = set(equations)
	by_system: dict[str, int] = defaultdict(int)
	for equation in equations.values():
		by_system[equation.system] += 1

	# Which specification headings share a library system, so the double-count
	# is stated rather than left for the reader to discover by adding.
	claimants: dict[str, list[str]] = defaultdict(list)
	for name in enumerated:
		system = SPEC_TO_SYSTEM.get(name)
		if system is not None:
			claimants[system].append(name)

	out: dict[str, dict[str, Any]] = {}
	for name, ids in sorted(enumerated.items()):
		system = SPEC_TO_SYSTEM.get(name)
		others = sorted(n for n in claimants.get(system or "", []) if n != name)
		out[name] = {
			"system": system,
			"spec": len(set(ids)),
			"graph": by_system.get(system or "", 0),
			"shared_with": others,
			"ids_implemented": tuple(i for i in ids if i in held),
			"ids_missing": tuple(i for i in ids if i not in held),
		}
	return out


def equation_coverage(
	equations: dict[str, Equation], path: Path | None = None
) -> list[str]:
	"""The specification's equation ids the graph does not implement.

	The list, not the count, because the count is a summary of this and a
	summary is what got the register into trouble: ``unclaimed_spec_systems``
	returned ``[]`` and the graph held nine of eighty-three equations. A finding
	list is checkable against the document; a boolean is not.

	An equation id is matched by *identity*, which is the specification's own
	id. That is deliberately strict: ``equilibrium_demand`` implements what §13
	calls ``elasticity_relationship``, and neither the graph nor this function
	claims the two are the same equation. Renaming the graph's equation to the
	spec's id is a separate decision about which spelling wins, and making it
	here would report a deficit as closed when only a label moved.
	"""
	enumerated = spec_equations(path)
	held = set(equations)
	return sorted(
		f"{name}: {equation_id}"
		for name, ids in enumerated.items()
		for equation_id in ids
		if equation_id not in held
	)


def spec_systems(path: Path | None = None) -> dict[str, str]:
	"""The systems ``params-prg1.md`` §4 enumerates, as ``{name: coupling}``.

	Read from the document rather than transcribed, because a transcribed list
	is a second copy that drifts. The heading carries the name and the
	parenthetical carries the coupling class; both are what this library's
	``System`` records, so the comparison is between two records of the same
	thing and not between a record and a restatement of it.
	"""
	import re

	document = path or (paths.repo_root() / "docs" / "params-prg1.md")
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
