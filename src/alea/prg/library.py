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

from alea.prg.views import Equation

__all__ = [
	"SYSTEM_IDS",
	"SYSTEMS",
	"System",
	"coverage",
	"systems_of",
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
)


_BY_ID = {system.id: system for system in SYSTEMS}

#: The system identifiers, for a caller that needs the set and not the objects.
SYSTEM_IDS: frozenset[str] = frozenset(_BY_ID)


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
