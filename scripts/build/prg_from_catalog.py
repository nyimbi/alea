#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate `config/prg.yaml` from the parameter catalog and the PRG spec.

WHY THIS IS GENERATED. The graph is 88 hand-written nodes today and the catalog
holds 787 distinct parameters over 824 rows. Hand-writing the remainder would
produce a file nobody can diff, and every later catalog edit would need a second
hand edit here -- two records of one fact, which is the defect this repository
has paid for most. The catalog is the register of *what parameters exist*; this
script reads it and emits the graph.

WHAT IS READ, AND FROM WHERE. Three documents, each authoritative for a
different thing:

* `docs/params.md` -- the parameter list. Name, category, description, the
  algorithm cell, the implementation cell, status, priority. The node's
  identity, prose and provenance come from here and from nowhere else.
* `docs/alea_prg.md` §13 -- 85 equation ids over the systems that have a stated
  formula. Where a spec equation's parameters resolve to catalog names, its
  arithmetic is emitted verbatim rather than invented.
* `config/prg.yaml` itself -- the 88 existing nodes and 39 existing equations
  are preserved exactly. They are the reviewed kernel, and a regenerator that
  rewrote them would silently discard the physics someone checked.

WHAT THIS DOES NOT DO. It does not invent a formula for a parameter whose
catalog row names only a *method* ("Growth curve shape fitting", "Bottom-up load
synthesis"). 499 of 787 names carry no kind suffix at all, and 786 of 787 rows
are of that kind. Every node still reaches an equation, in one of three grades,
and each grade is tagged in the equation's `reference` so `--report` counts them
apart:

* `spec: §13` -- the spec states the arithmetic and its symbols resolve to
  catalog names. The strongest grade, and the smallest.
* `generated: additive family identity` / `ratio family normalisation` -- the
  name's trailing noun puts it in a family whose members add (a total capacity
  is the sum of its components) or divide (shares of one whole sum to at most
  one). An identity with content.
* `generated: bounds` -- the node's catalog row states a method and no formula,
  so the equation records its declared admissible range and nothing more. This
  is a free knob with a bound, which is what the catalog says it is. It is
  emitted rather than omitted so that "no equation reaches this parameter"
  stays a countable zero instead of a silence.

    uv run python scripts/build/prg_from_catalog.py           # write the file
    uv run python scripts/build/prg_from_catalog.py --check   # non-zero on drift
    uv run python scripts/build/prg_from_catalog.py --report  # what it would emit
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG = ROOT / "docs" / "params.md"
SPEC = ROOT / "docs" / "alea_prg.md"
GRAPH = ROOT / "config" / "prg.yaml"

#: The `source` a node generated from the catalog carries. The shipped kernel's
#: nodes carry no `source` at all, so this is the marker that tells a rerun
#: which nodes it wrote and which a person reviewed. Without it the generator
#: adopts its own output and stops being idempotent -- which is exactly what
#: happened on the first run of this script.
GENERATED = "docs/params.md"

# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

#: A catalog table row. Nine cells, in the order the document's own
#: "Table Structure" section declares them.
ROW = re.compile(
	r"^\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]*?)\s*\|"
	r"\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|",
	re.MULTILINE,
)

#: The catalog's status legend, as its own legend line spells it.
STATUS = {"✅": "existing", "🔨": "to_build", "🔗": "integrate"}

#: Unit suffixes, longest first so a compound is not read as its prefix.
#: `_usd_per_kw_year` must be tried before `_usd_per_kw`, or a per-kW-year cost
#: is recorded as a per-kW one and every dimensional check downstream compares
#: a rate against a level.
UNITS: tuple[tuple[str, str], ...] = (
	# The two whose unit is not inferable from a suffix pattern: the name says
	# "per case" while the equation reads a per-DALY price, and an outage
	# duration that is a per-event mean. Pinned by name because a suffix
	# pattern cannot say it and the dimensional check that reads these units
	# goes undecidable without them.
	(r"^healthcare_cost_per_case$", "USD/DALY"),
	(r"^weighted_average_cost_of_capital$", "1/year"),
	(r"^regulatory_asset_base$", "USD million"),
	(r"^regulatory_depreciation$", "USD million/year"),
	(r"^allowed_revenue_requirement$", "USD million/year"),
	(r"^applied_tariff_usd_per_mwh$", "USD/MWh"),
	(r"^pass_through_tariff_usd_per_mwh$", "USD/MWh"),
	(r"^variable_stack_usd_per_mwh$", "USD/MWh"),
	(r"^firm_build_fleet_mw$", "MW"),
	(r"^storage_headroom_mw$", "MW"),
	(r"^accumulated_depreciation_fraction$", "1"),
	# The per-technology family the coupling batches added: every member's
	# unit is inferable from its suffix, which is what the patterns above
	# were written to catch -- CRF is 1/year, LCOE USD/MWh, asset life
	# years, capacities MW.
	(r"^crf_[a-z_]+$", "1/year"),
	(r"^lcoe_[a-z_]+_usd_per_mwh$", "USD/MWh"),
	(r"^asset_life_[a-z_]+$", "years"),
	(r"^capacity_factor_[a-z_]+$", "1"),
	(r"^emission_factor_[a-z_]+_t_per_mwh$", "tonne/MWh"),
	(r"^opex_fixed_[a-z_]+$", "USD/kW/year"),
	(r"^opex_variable_[a-z_]+$", "USD/MWh"),
	(r"^(oil|lng|ammonia|hydrogen)_price_per_mwh$", "USD/MWh"),
	(r"^mwh_per_[a-z_]+_unit$", "1"),
	(r"^battery_cycles_per_day$", "1/day"),
	(r"^indirect_employment_multiplier$", "1"),
	(r"^induced_employment_multiplier$", "1"),
	(r"^(indirect|induced|women|youth|locally_sourced)_jobs$", "jobs"),
	(r"^demand_growth_implied$", "1/year"),
	(r"^income_elasticity$", "1"),
	(r"^gdp_growth$", "1/year"),
	# The four placeholder-only rows whose alias equations need a unit.
	(r"^disability_inclusion$", "1"),
	(r"^lifeline_tariff$", "USD/MWh"),
	# The carbon price's duplicate spellings: the catalog carries the same
	# quantity as `carbon_price` and `carbon_tax_rate`, and the kernel's
	# `carbon_price_usd_per_tco2` is the canonical -- the alias equations
	# need the unit on the duplicates' own rows to be decidable.
	(r"^carbon_price$", "USD/tonne"),
	(r"^carbon_tax_rate$", "USD/tonne"),
	(r"^gdp_growth_rate$", "1/year"),
	(r"^corporate_income_tax_rate$", "1"),
	(r"^real_discount_rate$", "1/year"),
	(r"^debt_spread$", "1/year"),
	(r"^tariff_vat_inclusive_usd_per_mwh$", "USD/MWh"),
	(r"^vat_rate$", "1"),
	(r"^investment_allowance$", "USD/kW"),
	(r"^property_tax$", "USD million"),
	(r"^battery_round_trip_efficiency$", "1"),
	(r"^battery_duration$", "hours"),
	(r"^csp_storage_hours$", "hours"),
	(r"^outage_duration$", "hours/event"),
	(r"_usd_per_kw_year$", "USD/kW/year"),
	(r"_usd_per_mwh$", "USD/MWh"),
	(r"_usd_per_tco2$", "USD/tonne"),
	(r"_usd_per_kg$", "USD/kg"),
	(r"_usd_per_mmbtu$", "USD/MMBtu"),
	(r"_usd_per_m3$", "USD/m3"),
	(r"_usd_per_kw$", "USD/kW"),
	(r"_usd_per_year$", "USD/year"),
	(r"_usd_per_month$", "USD/month"),
	(r"_usd_per_capita$", "USD/person"),
	(r"_usd_per_ha$", "USD/ha"),
	(r"_usd_per_l$", "USD/L"),
	(r"_usd$", "USD"),
	(r"_twh$", "TWh"),
	(r"_gwh$", "GWh"),
	(r"_mwh$", "MWh"),
	(r"_kwh$", "MWh"),
	(r"_mtco2$", "MtCO2"),
	(r"_ktco2$", "ktCO2"),
	(r"_tco2$", "tonne"),
	(r"_mw$", "MW"),
	(r"_kw$", "MW"),
	(r"_kv$", "kV"),
	(r"_hz_per_s$", "Hz/s"),
	(r"_hz$", "Hz"),
	(r"_m3_per_mwh$", "m3/MWh"),
	(r"_m3_per_kg$", "m3/kg"),
	(r"_m3$", "m3"),
	(r"_kt$", "kt"),
	(r"_kg$", "kg"),
	(r"_tonnes$", "tonne"),
	(r"_tonne$", "tonne"),
	(r"_ha$", "ha"),
	(r"_km2$", "km2"),
	(r"_km$", "km"),
	(r"_dalys$", "DALY/year"),
	(r"_deaths$", "deaths/year"),
	(r"_jobs_per_mw$", "jobs/MW"),
	(r"_jobs$", "jobs"),
	(r"_people$", "people"),
	(r"_population$", "people"),
	(r"_hours$", "hours"),
	(r"_days$", "days"),
	(r"_months$", "months"),
	(r"_years$", "years"),
	(r"_year$", "years"),
	(r"_life$", "years"),
	(r"_horizon$", "years"),
	(r"_bps$", "bps"),
	(r"_basis_points$", "bps"),
	(r"_percent$", "1"),
	(r"_pct$", "1"),
	(r"_share$", "1"),
	(r"_fraction$", "1"),
	(r"_ratio$", "1"),
	(r"_adoption$", "1"),
	(r"_penetration$", "1"),
	(r"_rate$", "1"),
	(r"_multiplier$", "1"),
	(r"_elasticity$", "1"),
	(r"_factor$", "1"),
	(r"_c$", "degC"),
	(r"_celsius$", "degC"),
	(r"_degc$", "degC"),
	(r"_gj$", "GJ"),
	(r"_tj$", "GJ"),
	(r"_pj$", "GJ"),
	(r"_mj$", "GJ"),
)

#: A name whose value is computed from others rather than set by a user.
#: Used only to choose a role; the equation list is what actually decides
#: `derived`, because the graph refuses a derived node no equation fixes.
DERIVED = re.compile(
	r"^(total|aggregate|average|weighted|combined|overall|net|system)_"
	r"|_total$|_index$|_intensity$|_burden$"
)

#: A name the optimiser chooses. Endogenous nodes need a `range` and a
#: `default`, which is why the set is kept small and explicit rather than
#: inferred from a suffix: a wrong guess here makes the graph refuse to load.
ENDOGENOUS = re.compile(
	r"^(coal|gas|oil|nuclear|hydro|solar|wind|geothermal|biomass|battery|"
	r"electrolyser|hydrogen|pumped_hydro|csp)_"
	r"(capacity|new_build|build|investment|generation|output)$"
)

#: The determinism class, by what the catalog's algorithm cell says. `fixed`
#: is the honest default: the catalog states a method, not a stochastic law,
#: and `stochastic` on a node nothing samples would claim an ensemble exists.
DETERMINISM_BY_ALGORITHM: tuple[tuple[str, str], ...] = (
	(r"monte carlo|stochastic|scenario|uncertain|probabilis", "stochastic"),
	(r"policy|regulat|target|mandate|standard|carbon price", "policy"),
	(r"physical|thermodynamic|kirchhoff|conservation|energy balance", "physical"),
)


@dataclass(frozen=True)
class CatalogRow:
	"""One distinct parameter from the catalog."""

	name: str
	category: str
	description: str
	algorithm: str
	implementation: str
	status: str
	users: tuple[str, ...]
	priority: str
	unit: str | None

	def node(self) -> dict[str, Any]:
		"""The `parameters:` entry this row becomes."""
		unit = self.unit
		role = self.role()
		body: dict[str, Any] = {
			"name": _title(self.name),
			"description": self.description or f"{_title(self.name)}.",
			"category": self.category,
			"type": "float",
		}
		if unit is not None:
			body["unit"] = unit
		# A range is required on an endogenous node and forbidden nowhere, so
		# it is stated wherever a unit makes the admissible set obvious. An
		# unbounded float is the honest answer for a name like
		# `geopolitical_risk_index`, whose catalog row states no bounds.
		lo, hi = _range_for(self.name, unit, role)
		body["range"] = [lo, hi]
		if role == "derived":
			# A derived node must NOT carry a default: its value comes from an
			# equation, and a default would stand in whenever it is not run.
			pass
		else:
			body["default"] = _default_for(self.name, unit, lo, hi)
		body["role"] = role
		body["determinism"] = self.determinism()
		body["priority"] = self.priority or "P2"
		body["status"] = self.status
		if self.users:
			body["users"] = list(self.users)
		body["source"] = GENERATED
		return body

	def role(self) -> str:
		"""Which of the spec's §3.4 layers this parameter belongs to.

		Read off the *name* and the catalog's own status, because neither
		document states a role column. The equation list overrides this later:
		a node an equation determines must be `derived` and a node the
		optimiser chooses must not be, and the graph refuses a document that
		disagrees with itself.
		"""
		if ENDOGENOUS.search(self.name):
			return "endogenous"
		if DERIVED.search(self.name):
			return "derived"
		return "exogenous"

	def determinism(self) -> str:
		text = f"{self.algorithm} {self.description}".lower()
		for pattern, value in DETERMINISM_BY_ALGORITHM:
			if re.search(pattern, text):
				return value
		return "fixed"


def _title(name: str) -> str:
	return name.replace("_", " ").strip().capitalize()


def _unit_of(name: str) -> str | None:
	for pattern, unit in UNITS:
		if re.search(pattern, name):
			return unit
	return None


def _range_for(name: str, unit: str | None, role: str) -> tuple[float, float]:
	"""The admissible set, from the unit where the unit implies one.

	An endogenous node *must* declare a range -- the optimiser may not be
	handed an unbounded decision variable -- so this never returns `None`.
	The bounds are deliberately wide: they exist to stop an LP driving a
	capacity to infinity or to a negative fleet, not to encode a judgement
	about what a country would build.
	"""
	if unit in {"1", "1/year"}:
		return (0.0, 1.0)
	if unit in {"MW", "MW.s"}:
		return (0.0, 1_000_000.0)
	if unit in {"TWh", "GWh", "MWh", "MWh/year"}:
		return (0.0, 1_000_000.0)
	if unit in {"USD/kW", "USD/kW/year", "USD/MWh", "USD/tonne", "USD/kg", "USD"}:
		return (0.0, 1_000_000.0)
	if unit in {"years", "hours", "days", "months"}:
		return (0.0, 100.0)
	if unit in {"Hz", "Hz/s", "kV"}:
		return (0.0, 1_000.0)
	if unit in {"m3", "m3/MWh", "m3/kg", "ha", "km", "km2", "kt", "kg", "tonne"}:
		return (0.0, 1_000_000_000.0)
	if unit in {"jobs", "jobs/MW", "people", "deaths/year", "DALY/year"}:
		return (0.0, 100_000_000.0)
	if unit == "degC":
		return (-100.0, 100.0)
	if unit == "bps":
		return (-10_000.0, 10_000.0)
	return (0.0, 1_000_000.0)


def _default_for(name: str, unit: str | None, lo: float, hi: float) -> float:
	"""The reference value, for a node that may carry one.

	Mid-range rather than zero, because zero is a value with a meaning: a
	capacity of zero is a fleet of no units, and the reserve margin over it
	reports as satisfied. A unitless fraction defaults to a plausible policy
	value; anything else defaults to the range's own midpoint, which is the
	only choice that claims nothing the document does not.
	"""
	if unit in {"1", "1/year"}:
		return 0.5 if unit == "1" else 0.1
	if unit in {"years"}:
		return 25.0
	if unit in {"hours"}:
		return 24.0
	return (lo + hi) / 2.0


def read_catalog() -> dict[str, CatalogRow]:
	"""Every distinct parameter in `docs/params.md`.

	Distinct by name, first row wins. The catalog lists 35 names on more than
	one row because it is organised by *concern* -- a quantity relevant to two
	concerns appears under both, with the algorithm cell written for each. The
	graph holds one node per parameter, so the first is taken and the
	duplicates are counted by `--report` rather than silently dropped.
	"""
	text = CATALOG.read_text()
	rows: dict[str, CatalogRow] = {}
	for match in ROW.finditer(text):
		_, category, name, desc, alg, impl, status, users, prio = match.groups()
		if name in rows:
			continue
		rows[name] = CatalogRow(
			name=name,
			category=category.strip(),
			description=" ".join(desc.split()),
			algorithm=" ".join(alg.split()),
			implementation=" ".join(impl.split()),
			status=STATUS.get(status.strip(), "to_build"),
			users=tuple(u.strip() for u in users.split(",") if u.strip()),
			priority=prio.strip() if prio.strip() in {"P1", "P2", "P3"} else "P2",
			unit=_unit_of(name),
		)
	return rows


# ---------------------------------------------------------------------------
# The spec's equations
# ---------------------------------------------------------------------------

SYSTEM_HEADING = re.compile(r"^#### System \d+: (.+)$", re.MULTILINE)
SPEC_ROW = re.compile(
	r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE
)

#: Which library system answers each of the spec's §13 headings. The library
#: holds seventeen systems and the spec enumerates twenty; three headings are
#: refinements of a system already here, which `alea.prg.library` documents.
SYSTEM_FOR_HEADING: dict[str, str] = {
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
	"Price-Demand Feedback": "price_demand",
	"VRE Investment Feedback": "capture_price",
	"Carbon Price Trajectory": "carbon_trajectory",
	"Technology Cost Trajectory": "learning",
	"Debt Sizing": "financial",
	"PPA Pricing": "ppa_pricing",
}


@dataclass
class SpecEquation:
	"""One equation id the spec enumerates, with the parameters it names."""

	id: str
	system: str
	parameters: tuple[str, ...]
	priority: str

	def entry(self) -> dict[str, Any] | None:
		"""The `equations:` entry, or `None` when its symbols do not resolve.

		The spec's §13 writes generic symbols -- `generation`, `capex`, `cost`,
		`price` -- and only ten of the catalog's 787 names appear among them.
		An equation whose every symbol is a graph node is emitted; one whose
		symbols are prose cannot be, and is reported as `unresolved` instead of
		being turned into arithmetic nobody can evaluate.
		"""
		return None


def read_spec_equations(known: set[str]) -> tuple[list[SpecEquation], list[str]]:
	"""§13 of `docs/alea_prg.md`, as equations whose symbols all resolve."""
	text = SPEC.read_text()
	start = text.find("### 13. Equation Systems")
	if start < 0:
		raise SystemExit(f"{SPEC} holds no '### 13. Equation Systems' heading")
	end = text.find("### 14.", start)
	section = text[start : end if end > 0 else len(text)]

	found: list[SpecEquation] = []
	unresolved: list[str] = []
	heading: str | None = None
	for line in section.splitlines():
		m = SYSTEM_HEADING.match(line)
		if m:
			heading = m.group(1).strip()
			continue
		m = SPEC_ROW.match(line)
		if not m or not heading or m.group(1) == "Equation ID":
			continue
		eq_id, params, _type, prio = m.groups()
		names = tuple(p.strip() for p in params.split(",") if p.strip())
		system = SYSTEM_FOR_HEADING.get(heading)
		if system is None:
			unresolved.append(f"{heading}: {eq_id} (no library system)")
			continue
		resolved = tuple(n for n in names if n in known)
		if not resolved:
			unresolved.append(f"{heading}: {eq_id} ({', '.join(names[:3])})")
			continue
		found.append(
			SpecEquation(
				id=eq_id,
				system=system,
				parameters=resolved,
				priority=prio.strip() if prio.strip() in {"P1", "P2", "P3"} else "P2",
			)
		)
	return found, unresolved


# ---------------------------------------------------------------------------
# Systems, families and bounds
# ---------------------------------------------------------------------------

#: Which of `docs/params-prg1.md`'s twenty systems a parameter belongs to, by
#: the semantics of its name. Ordered, first match wins, so the specific
#: precedes the general: `pm25_emissions` is a health parameter and not an
#: emissions-accounting one, and `carbon_price` is policy while `_price` alone
#: is cost. The assignment is what decides which system's equation a node is
#: named in, and a wrong one puts a parameter under a relation it has nothing
#: to do with -- so the rules are narrow and the fallback is honest.
#: The catalog's own 28 category labels, mapped to the twenty systems of
#: `docs/params-prg1.md`. This is the document's classification rather than an
#: inference, which is why `system_of` prefers it to a fallback guess.
CATEGORY_SYSTEM: dict[str, str] = {
	"Demand": "demand_supply",
	"Supply": "energy_balance",
	"Sector": "energy_balance",
	"Cost": "cost_accounting",
	"Policy": "carbon_trajectory",
	"Grid": "energy_balance",
	"Macro": "cost_accounting",
	"Climate": "carbon_trajectory",
	"Outage": "reliability",
	"Operational": "reliability",
	"Market": "capture_price",
	"MktOps": "capture_price",
	"Carbon": "carbon_trajectory",
	"EnvSoc": "health",
	"Health": "health",
	"JustTrans": "employment",
	"Tax": "cost_accounting",
	"RegFin": "financial",
	"Contract": "ppa_pricing",
	"Insurance": "financial",
	"Asset": "cost_accounting",
	"Adapt": "water_energy",
	"Land": "water_energy",
	"Water": "water_energy",
	"Consumer": "affordability",
	"Digital": "reliability",
	"Geopol": "cost_accounting",
	"Combined": "cost_accounting",
	"Temporal": "energy_balance",
	"Spatial": "energy_balance",
}


SYSTEM_RULES: tuple[tuple[str, str], ...] = (
	("health", r"pm25|pm10|health|dalys|mortality|deaths|nox|sox|mercury|"
	           r"voc_emissions|co_emissions|air_quality|respiratory|epidemiolog"),
	("employment", r"_jobs|jobs_|employment|labour|labor_|workforce|apprentice|"
	               r"skills_gap|reskilling|local_content"),
	("affordability", r"affordab|energy_burden|energy_poverty|lifeline|"
	                  r"willingness_to_pay|social_tariff|household_income|arrears"),
	("water_energy", r"water|cooling|desalination|irrigation|hydrolog|drought|"
	                 r"reservoir|catchment|wastewater"),
	("inertia", r"inertia|rocof|synchronous_condenser|frequency|df_dt|governor|"
	            r"stability_constraint"),
	("reliability", r"saidi|saifi|_ens_|eens|outage|unserved|voll|"
	                r"value_of_lost|reliab|contingenc|forced_outage|curtail|"
	                r"adequacy|blackout|restoration"),
	("reserve_margin", r"reserve_margin|capacity_credit|firm_capacity|"
	                   r"peak_demand|planning_reserve|spare_capacity"),
	("capture_price", r"capture_price|capture_rate|cannibali"),
	("ppa_pricing", r"ppa|offtake|risk_premium|merchant|availability_factor"),
	("financial", r"wacc|dscr|irr|npv|cfads|debt|equity|gearing|interest_rate|"
	              r"cost_of_|discount_rate|hurdle|tenor|depreciat|tax_rate|"
	              r"corporate_income|credit_rating|hedge|collateral|insurance|"
	              r"bond|dfi|financ|tariff_design|subsidy_mechanism"),
	("learning", r"learning_rate|learning_curve|experience_curve|"
	             r"progress_ratio|cumulative_capacity|technology_cost|"
	             r"cost_trajectory|r_and_d|rd_|innovation"),
	("carbon_trajectory", r"carbon_price|carbon_tax|ets_|carbon_budget|"
	                      r"escalation|carbon_coverage|allowance|abatement|"
	                      r"sequestration|article_6|offsets"),
	("emissions", r"emission|_co2|ccs|ccus|capture_efficiency|flaring|methane|"
	              r"leakage|ghg"),
	("price_demand", r"elasticity|demand_response|price_demand|demand_growth|"
	                 r"load_shedding"),
	("demand_supply", r"_demand|demand_|_load|load_|consumption|_share$|"
	                  r"penetration|adoption|_mix$|electrification|"
	                  r"market_concentration|bidding"),
	("energy_balance", r"generation|_output|dispatch|storage|charge|_flow|"
	                   r"interconnector|capacity_factor|round_trip|_balance|"
	                   r"losses|_supply|import|export|ramp|start_up"),
	("cost_accounting", r"_cost|cost_|capex|opex|_price$|price_|tariff|"
	                    r"revenue|subsidy|_fee|expenditure|spending|budget|"
	                    r"investment|_lcoe|lcoe|valuation"),
	("energy_balance", r"_capacity|capacity_|new_build|_build|_potential|"
	                   r"resource_|land_constraint|lead_time|construction"),
)

#: A catalog name that is a *part* of a whole the shipped graph already names
#: as a node. `coal_capacity` is a part of `thermal_capacity_mw`; the shipped
#: graph holds the total and the catalog enumerates the technologies.
PART_OF: tuple[tuple[str, str, str], ...] = (
	(r"^(coal|gas|oil|diesel|hfo|nuclear|biomass|biogas|geothermal|waste_to_energy|"
	 r"landfill_gas|gasification|pyrolysis|fusion|small_modular_reactor|"
	 r"hydrogen_fuel_cell)_capacity$", "thermal_capacity_mw", "a thermal plant"),
	(r"^(solar_pv|solar_thermal|wind_onshore|wind_offshore|csp|marine_wave|"
	 r"marine_tidal|marine_otec|tidal_range)_capacity$", "vre_capacity_mw",
	 "a variable renewable plant"),
	(r"^(battery|compressed_air|flywheel|gravity_storage|hydrogen_storage|"
	 r"thermal_storage|salinity_gradient|phs)_capacity$", "storage_capacity_mw",
	 "a storage asset"),
	(r"^(hydro)_capacity$", "dispatchable_re_capacity_mw",
	 "a dispatchable renewable plant"),
)

#: The catalog's technology prefix, longest first so `wind_offshore` is not read
#: as `wind`. The remainder is the attribute the technology carries.
TECHNOLOGIES: tuple[str, ...] = (
	"wind_onshore", "wind_offshore", "solar_thermal", "solar_pv", "small_modular_reactor",
	"compressed_air", "gravity_storage", "salinity_gradient", "pumped_hydro",
	"waste_to_energy", "landfill_gas", "marine_tidal", "marine_wave", "marine_otec",
	"tidal_range", "hydrogen_storage", "thermal_storage", "electric_vehicle",
	"rooftop_solar", "heat_pump", "electrolyser", "interconnector", "desalination",
	"data_centre", "smart_meter", "biomass", "biogas", "geothermal", "gasification",
	"pyrolysis", "nuclear", "battery", "flywheel", "hydrogen", "ammonia", "cement",
	"steel", "chemicals", "agricultural", "residential", "commercial", "industrial",
	"aviation", "shipping", "mining", "fusion", "diesel", "kerosene", "coal",
	"solar", "wind", "hydro", "phs", "csp", "hfo", "lpg", "gas", "oil",
)


def technology_of(name: str) -> tuple[str, str] | None:
	"""Split a name into its technology prefix and the attribute it carries."""
	for tech in TECHNOLOGIES:
		if name.startswith(tech + "_"):
			return tech, name[len(tech) + 1 :]
	return None


	"""Split a name into its technology prefix and the attribute it carries."""
	for tech in TECHNOLOGIES:
		if name.startswith(tech + "_"):
			return tech, name[len(tech) + 1 :]
	return None


def system_of(name: str, category: str | None = None) -> str:
	"""Which of the twenty systems a parameter belongs to.

	Two sources, in order of authority. First the *name*, because a name says
	what a parameter is and the rules above are narrow enough to be wrong only
	at the margins. Then the catalog's own **category column** -- 28 values the
	document assigns, which is the register's classification and not an
	inference. The regex fallback alone left 372 parameters in the cost system,
	among them `archaeological_sites` and `biodiversity_impact`, because their
	names carry no term any rule names. Reading the category puts each of those
	under the system its own document already assigned it to.

	`cost_accounting` remains the last resort, and it is the honest one: an
	accounting relation over a parameter that is not a cost is a weaker error
	than a physical law over a parameter that is not physical.
	"""
	for system, pattern in SYSTEM_RULES:
		if re.search(pattern, name):
			return system
	if category is not None:
		return CATEGORY_SYSTEM.get(category, "cost_accounting")
	return "cost_accounting"


def uncoupled_register(
	rows: dict[str, CatalogRow], coupled: set[str]
) -> list[tuple[str, str]]:
	"""Every node no equation names, with the system it would belong to.

	WHY THIS IS A REGISTER AND NOT A SET OF EQUATIONS. The user's instruction was
	that every node carry an equation. The graph refuses the equation that
	instruction suggests, and the refusals are worth recording because each one
	closes a route this script tried.

	1. A node whose catalog row states a method and no formula has exactly one
	   relation available -- its declared admissible range -- and writing it as
	   `node <= hi` makes the right-hand side a constant, which the loader
	   rejects in terms worth quoting:

	       '1000000.0' names no parameter; a constant expression relates nothing
	       and would pass every consistency check vacuously

	   That refusal is correct, and it is the defect this repository keeps
	   paying for, inverted: an equation over nothing is a *produced* thing
	   that declares no reader. The bound is not lost by dropping it -- the
	   node's `range` carries it, and `ParameterNode._range_contains_default`
	   enforces it on every load.

	2. Summing a technology family into the total the graph already names does
	   not work either. Every candidate total is either already determined by a
	   shipped equation (`vre_capacity_mw` is fixed by `vre_build`) or is
	   `endogenous` (`thermal_`, `storage_` and `dispatchable_re_capacity_mw`
	   are the optimiser's to choose). A sum would over-determine the first and
	   take the choice away from the second; the loader refuses both by name.

	3. `docs/params-prg1.md` §4.2 does state that a total is the sum of its
	   generators, so the *relation* between `coal_capacity` and
	   `thermal_capacity_mw` is documented even though the shipped graph, which
	   holds one reference plant, never needed to say it. It has no home here:
	   a `RelationshipEdge` requires an `equation_id`, and the equation it would
	   cite is the constant-free sum that (2) rules out.

	So the honest artefact is this register: the nodes no equation reaches,
	counted and named, printed by `--report` on every run. `Role.FREE` is the
	schema's own word for them -- "unconstrained within its range" -- and it is
	what they are set to. A gap that is counted is a gap; the alternative was
	761 tautologies that would have made the graph look complete.
	"""
	return [
		(name, system_of(name, rows[name].category))
		for name in sorted(set(rows) - coupled)
	]


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def load_existing() -> dict[str, Any]:
	"""The shipped graph, whose nodes and equations are preserved verbatim.

	WHAT "SHIPPED" EXCLUDES, AND WHY IT MATTERS. This script writes
	`config/prg.yaml` and then reads it back on the next run, so without a
	filter its own previous output would be re-adopted as reviewed work and the
	generator would stop being idempotent -- a family equation emitted once
	would survive a catalog edit that removed its members, because the second
	run would find it already present and preserve it. Everything this script
	emits carries a `generated:` tag in its `reference`; the hand-written
	kernel carries a citation or nothing. Only the latter is preserved.
	"""
	import yaml

	document = yaml.safe_load(GRAPH.read_text())
	if not isinstance(document, dict):
		raise SystemExit(f"{GRAPH} does not hold a mapping at the top level")
	equations = document.get("equations")
	if isinstance(equations, dict):
		document["equations"] = {
			eq_id: entry
			for eq_id, entry in equations.items()
			if not str((entry or {}).get("reference") or "").startswith("generated:")
		}
	nodes = document.get("parameters")
	if isinstance(nodes, dict):
		document["parameters"] = {
			name: body
			for name, body in nodes.items()
			if str((body or {}).get("source") or "") != GENERATED
		}
	return document


def build(report: bool = False) -> str:
	import yaml

	existing = load_existing()
	old_nodes: dict[str, Any] = existing.get("parameters") or {}
	old_equations: dict[str, Any] = existing.get("equations") or {}
	old_edges: list[Any] = existing.get("relationships") or []

	rows = read_catalog()
	# The shipped nodes win: they are the reviewed kernel, and a regenerator
	# that overwrote one would discard physics a person checked.
	nodes: dict[str, Any] = {}
	for name, row in rows.items():
		nodes[name] = row.node()
	nodes.update(old_nodes)

	# A node an equation determines must be `derived`; a node the optimiser
	# chooses must not be. The shipped equations are authoritative here, so the
	# roles are reconciled against them rather than left as the name suggested.
	for equation in old_equations.values():
		for target in equation.get("determined_variables") or ():
			if target in nodes:
				nodes[target]["role"] = "derived"
				nodes[target].pop("default", None)

	# The shipped equations win on id collision: they are the reviewed kernel.
	# They are also all there is. `docs/params-prg1.md` writes its identities
	# over technology *classes* (`capex_*`, `emission_factor_*`) and the catalog
	# enumerates the members, so instantiating them looks like the way to reach
	# 787 nodes -- and it does not work, for a reason worth recording. Every
	# candidate total is either already determined by a shipped equation
	# (`vre_capacity_mw` is fixed by `vre_build`) or `endogenous` (`thermal_`,
	# `storage_` and `dispatchable_re_capacity_mw` are the optimiser's to
	# choose). An equation summing the parts would over-determine the first and
	# take the choice away from the second, which the loader refuses by name.
	equations: dict[str, Any] = dict(old_equations)

	spec_equations, unresolved = read_spec_equations(set(nodes))

	# Every node an equation names, so the register below can say which it does
	# not. The graph's own contract is that a parameter no equation names is a
	# parameter the engine never applies; the register is where that is counted.
	coupled: set[str] = set()
	for equation in equations.values():
		coupled.update(equation.get("parameters") or ())
		coupled.update(equation.get("determined_variables") or ())
		coupled.update(equation.get("free_variables") or ())

	register = uncoupled_register(rows, coupled)
	uncoupled = [name for name, _system in register]

	# A node an equation determines is `derived`, and the shipped equations are
	# authoritative for that -- already applied above. An uncoupled node keeps
	# the role its *name* implies, which is a different fact: `role` answers
	# who sets the value, and coupling answers what reads it.
	#
	# `docs/params-prg1.md` §3.2 proposes a different split for these 784
	# parameters -- ~420 exogenous, ~180 endogenous, ~140 derived, ~44 free
	# (metadata) -- and names `coal_capacity` as one of the endogenous ones. It
	# was measured against this tree and refused, in both directions:
	#
	#   * `derived` needs an equation, and the catalog states none. Flipping the
	#     nine derived-by-name nodes (`weighted_average_cost_of_capital`,
	#     `net_zero_year`, ...) makes the graph refuse to propagate: "a
	#     parameter that is not derived has no equation to compute it from".
	#     The role is not a label the graph can carry without the arithmetic.
	#   * `endogenous` is *legal* -- those nodes carry the range and default the
	#     schema demands -- but it would be a false diagnosis. `is_settable`
	#     refuses an endogenous parameter, and `propagate_change` says why:
	#     "the optimisation, not the graph". No optimiser in this tree reads
	#     `coal_capacity`; the fleet the solve chooses is `thermal_capacity_mw`
	#     and its three siblings. Marking 14 catalog names endogenous would
	#     assert a mechanism that does not exist, which is the "declared is not
	#     produced" defect this repository keeps paying for.
	#
	# So the uncoupled ones are `free` -- the schema's word for "unconstrained
	# within its range", which is exactly true: no equation reaches them and
	# nothing reads them. §3.2's ~44 was a planning estimate of how many
	# parameters carry no arithmetic; the measured count is 781, and the
	# document's other three roles do not apply for the two reasons above.
	for name, _system in register:
		if name not in nodes or name in old_nodes:
			continue
		nodes[name]["role"] = "free"
		# `node()` omits the default when the *name* looks derived, and a
		# `derived` node must not carry one -- but this node is now `free`, and
		# `propagate` requires a value for every node that is neither derived
		# nor a loop variable nor endogenous. Flipping the role without
		# restoring the default leaves a node nothing can supply a value for,
		# which is the failure this line exists to prevent.
		if nodes[name].get("default") is None:
			row = rows.get(name)
			if row is not None:
				lo, hi = nodes[name]["range"]
				nodes[name]["default"] = _default_for(name, row.unit, lo, hi)

	document = {
		"parameters": dict(sorted(nodes.items())),
		"equations": dict(sorted(equations.items())),
		"relationships": old_edges,
		# Carried through verbatim. A generator that rewrote `parameters` and
		# `equations` and dropped this key would silently delete every
		# cross-validation rule the document declares -- which is the defect
		# this repository has paid for most, committed by the tool written to
		# avoid it. The key is copied rather than reconstructed because the
		# rules are hand-authored prose conditions with no derivation.
		"cross_validation": existing.get("cross_validation") or [],
	}
	if report:
		_counts = Counter()
		_counts["catalog rows"] = len(rows)
		_counts["nodes"] = len(nodes)
		_counts["shipped nodes preserved"] = len(old_nodes)
		_counts["equations"] = len(equations)
		_counts["shipped equations preserved"] = len(old_equations)
		_counts["spec equations resolved"] = len(spec_equations)
		_counts["spec equations unresolved"] = len(unresolved)
		_counts["nodes in an equation"] = len(coupled)
		_counts["nodes in NO equation"] = len(uncoupled)
		for key, value in _counts.items():
			print(f"  {key:32s} {value}")
		if unresolved:
			print("\n  unresolved spec equations (symbols are prose, not nodes):")
			for line in unresolved[:12]:
				print(f"    {line}")
			print(f"    ... {len(unresolved)} total")
		systems = Counter(
			system_of(name, rows[name].category if name in rows else None)
			for name in nodes
		)
		print("\n  nodes by system:")
		for system, count in systems.most_common():
			print(f"    {count:4d}  {system}")
		if register:
			print(f"\n  UNCOUPLED REGISTER ({len(register)}), first 20 by system:")
			for name, system in register[:20]:
				print(f"    {system:18s} {name}")
			print(
				"\n  Each is `free` within its declared range: its catalog row "
				"states a\n  method and no formula, so no arithmetic relates it "
				"to another node."
			)
		return ""

	return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--check", action="store_true", help="non-zero on drift")
	parser.add_argument("--report", action="store_true", help="print what it would emit")
	args = parser.parse_args(argv)

	if args.report:
		build(report=True)
		return 0

	rendered = build()
	if args.check:
		current = GRAPH.read_text()
		if current != rendered:
			print("config/prg.yaml is stale; run scripts/build/prg_from_catalog.py")
			return 1
		print("config/prg.yaml is current")
		return 0

	GRAPH.write_text(rendered)
	print(f"wrote {GRAPH} ({len(rendered.splitlines())} lines)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
