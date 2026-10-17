#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate a set of coupling fragments against every gate the loader skips.

The loader (`load_ingested`) carries the merge gates: schema, identity,
closure, the tautology guard, role consistency. It does not run the *physics*
gates a coupling batch must also survive before it is baked:

* the merged graph must propagate at its own declared defaults -- a cycle or
  a missing value is a load failure the merge report would never see;
* every equation must be dimensionally decidable (an equation whose units the
  walker cannot decide is an unexamined coupling, not a pass);
* a default scenario must report no blocking conflict -- a coupling whose
  own defaults violate it has coupled noise.

Usage:
	uv run python scripts/build/prg_coupler.py [directory...]

With no directory, validates `config/prg_ingest/`. Exit 0 only when every
fragment survives.

The batch authoring flow this serves: emit fragments from the family tables
into `config/prg_ingest/`, validate here, read the report, correct the
fragments, and only when this exits 0 bake into `config/prg.yaml` with
`yaml.safe_dump(sort_keys=False, width=100)` (the byte-exact format the
bake of 2026-10-17 established).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Batch 12 -- the financial core. Every equation carries its reference, its
# theory named, and the failure mode its description records. Couplings:
#
# weighted_average_cost_of_capital
#     A duplicate of `discount_rate` in the two-names-for-one-quantity class:
#     the shipped `wacc_definition` computes the blend and this node sits
#     beside it as an uncoupled placeholder. The equality makes the duplicate
#     derived rather than removing a reviewed id, and the unit override
#     (1/year, at the node's meaning) is what makes the equation decidable.
# regulatory_asset_base
#     The net regulated asset base is the fleet's capital less what the books
#     have already depreciated. Gross capital is the capacity-weighted fleet
#     capex (USD/kW over MW, scaled kW-per-MW and USD-per-USD-million);
#     `accumulated_depreciation_fraction` is the books' own accrual dial.
# regulatory_depreciation
#     Straight-line depreciation over the regulatory asset life (Ofwat/RAB
#     accounting; the UKRN guidance's revenue-requirement build-up).
# allowed_revenue_requirement
#     The rate-of-return revenue requirement: depreciation on RAB + the
#     allowed return on RAB, with the return read as the WACC the wacc
#     definition computes. This is the quantity a tariff must recover.
# cost_of_debt / cost_of_equity caps
#     The allowed returns regulate the components: a lender's rate cap and an
#     equity-return allowance bound what a scenario may assume. This is a
#     *constraint* coupling (relation leq), which is the register a
#     regulator's lever belongs in.
# applied_tariff
#     What the revenue cap does to the cost-recovery tariff: the cap sits in
#     (0.5, 2.0) on the cost-recovery tariff, so the applied tariff is the
#     recovery level scaled by it. `revenue_cap` reaches the engine through
#     this product instead of floating.
#
# Defaults moved: allowed_return_on_debt 0.08 -> 0.12 and
# allowed_return_on_equity 0.14 -> 0.18, because both caps were *below* the
# cost they cap at the shipped cost defaults (cost_of_debt 0.09,
# cost_of_equity 0.16): an allowed return a compliant component violates at
# default is a cap on nothing, and the shipped defaults then read as a
# regulated market whose own policy rate exceeds its cap.
# ---------------------------------------------------------------------------

BATCH12_NODES: dict[str, dict[str, object]] = {
	# Corrections to nodes the equations name. Bodies are complete: this is
	# Register 1, replace-with-correction.
	"weighted_average_cost_of_capital": {
		"unit": "1/year",
		"range": [0.0, 0.5],
		"role": "derived",
		"description": (
			"The market's blend of debt and equity, computed by wacc_definition "
			"a duplicate id for the quantity `discount_rate` computes, left as a "
			"free placeholder with no unit by the catalog expansion. Carried as "
			"an alias-equation to the derived form so the two ids serve one "
			"number and a scenario setting either reads a consistent blend."
		),
	},
	"allowed_return_on_debt": {
		"default": 0.12,
		"range": [0.02, 0.25],
		"description": (
			"The regulator's allowance for debt service, pre-tax. Was 0.08, "
			"below the commercial cost of debt it is meant to cap (0.09); an "
			"allowed return below market debt pricing closes every project in "
			"the jurisdiction and caps nothing. A 300 basis point spread over "
			"the policy rate is the level utility debt actually clears at."
		),
	},
	"allowed_return_on_equity": {
		"default": 0.18,
		"description": (
			"The regulator's allowed equity return for a transmission or "
			"distribution utility. Was 0.14, below the cost of equity the "
			"financial block carries (0.16), so the cap bound investments the "
			"utility's own financing terms refuse. 18% is an emerging-market "
			"utility's level; the range keeps 30% as the ceiling."
		),
	},
	"regulatory_asset_base": {
		"role": "derived",
		"description": (
			"The net regulated asset base: the fleet's gross capital less "
			"accumulated depreciation, computed from the fleet rather than "
			"declared. This is Ofwat's RAB line -- the base the allowed "
			"return is earned on -- and computing it is what ties the "
			"utility's accounts to the fleet the graph carries."
		),
	},
	"regulatory_depreciation": {
		"role": "derived",
		"description": (
			"Straight-line depreciation the regulator admits into the revenue "
			"requirement: the net asset base written down over the regulatory "
			"asset life. This is Ofwat's RAB depreciation line and the UKRN "
			"build-up's second term, computed from the base and the life "
			"rather than declared."
		),
	},
	"accumulated_depreciation_fraction": {
		"name": "Accumulated depreciation fraction",
		"description": (
			"The share of the fleet's gross capital the books have already "
			"depreciated, which is what stands between gross fleet capital and "
			"the net regulated asset base. 0.6 on the shipped fleet: a fleet "
			"whose assets are, on average, more than ten years into a 25-year "
			"life. Book-specific; the range admits a book that has not "
			"depreciated at all."
		),
		"category": "Cost",
		"type": "float",
		"unit": "1",
		"range": [0.0, 0.9],
		"default": 0.6,
		"role": "free",
		"determinism": "fixed",
		"priority": "P2",
		"status": "existing",
		"source": "Regulator's accounts (the RAB roll-forward)",
		"users": ["Regulators"],
	},
	"allowed_revenue_requirement": {
		"name": "Allowed revenue requirement",
		"description": (
			"Depreciation plus the allowed return on the asset base: the "
			"revenue the utility must recover for the regulator's accounts to "
			"balance. The tariff a cost-recovery regime sets is exactly this "
			"spread over the energy the fleet delivers, which is why the "
			"revenue cap's multiplier reads a tariff the recovery identity "
			"computes rather than a second cost build-up."
		),
		"category": "Cost",
		"type": "float",
		"unit": "USD million/year",
		"range": [0.0, 20000.0],
		"role": "derived",
		"determinism": "fixed",
		"priority": "P1",
		"status": "existing",
		"source": "UKRN cost of capital guidance (2023), revenue-requirement build-up",
		"users": ["Regulators"],
	},
	"applied_tariff_usd_per_mwh": {
		"name": "Applied tariff",
		"description": (
			"The tariff the utility actually charges: the cost-recovery level "
			"scaled by the revenue cap. The cap lives in [0.5, 2.0] around the "
			"recovery level, so a cap below 1 withholds part of the revenue "
			"requirement -- the regulatory instrument it is."
		),
		"category": "Market",
		"type": "float",
		"unit": "USD/MWh",
		"range": [0.0, 4000.0],
		"role": "derived",
		"determinism": "policy",
		"priority": "P1",
		"status": "existing",
		"source": "World Bank Regulation of Utilities handbook",
		"users": ["Regulators"],
	},
}

BATCH12_EQUATIONS: list[dict[str, object]] = [
	{
		"id": "wacc_alias",
		"name": "WACC is the discount rate",
		"description": (
			"The catalog's WACC row and the financial block's discount rate are "
			"one quantity, so the duplicate derives from the computed one and "
			"the graph keeps a single blend. An equality between two ids for "
			"one number is the closure that keeps a scenario setting either "
			"name consistent; the alternative -- deprecating the id -- loses "
			"the label a report may cite."
		),
		"system": "financial",
		"lhs": "weighted_average_cost_of_capital",
		"rhs": "discount_rate",
		"relation": "eq",
		"parameters": ["weighted_average_cost_of_capital", "discount_rate"],
		"free_variables": ["discount_rate"],
		"determined_variables": ["weighted_average_cost_of_capital"],
		"tolerance": 1.0e-09,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "Standard WACC with the interest tax shield",
		"latex": r"\mathrm{WACC} = \mathrm{discount\_rate}",
	},
	{
		"id": "regulatory_asset_base_definition",
		"name": "Regulated asset base from the fleet",
		"description": (
			"Gross fleet capital less what the books have written down. The "
			"gross capital is the capacity-weighted capex; the 1000 converts "
			"kW-per-MW and the million converts USD. A fraction the regulator's "
			"roll-forward states, not one the model invents."
		),
		"system": "financial",
		"lhs": "regulatory_asset_base",
		"rhs": "capex_usd_per_kw * total_capacity_mw * (1 - accumulated_depreciation_fraction) / 1000",
		"relation": "eq",
		"parameters": [
			"regulatory_asset_base", "capex_usd_per_kw", "total_capacity_mw",
			"accumulated_depreciation_fraction",
		],
		"free_variables": [
			"capex_usd_per_kw", "total_capacity_mw", "accumulated_depreciation_fraction",
		],
		"determined_variables": ["regulatory_asset_base"],
		"tolerance": 1.0e-09,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "Ofwat PR24 Appendix 11, allowed return on capital",
		"latex": r"\mathrm{RAB} = \mathrm{capex} \cdot C_{MW} \cdot 10^3 \cdot (1 - d_{acc}) \, /\, 10^6",
	},
	{
		"id": "regulatory_depreciation_definition",
		"name": "Regulatory depreciation",
		"description": (
			"Straight-line write-down of the asset base over the regulatory "
			"asset life. The rate-of-return revenue requirement's first term; "
			"the second is the return on the base below."
		),
		"system": "financial",
		"lhs": "regulatory_depreciation",
		"rhs": "regulatory_asset_base / depreciation_life_by_asset",
		"relation": "eq",
		"parameters": ["regulatory_depreciation", "regulatory_asset_base", "depreciation_life_by_asset"],
		"free_variables": ["depreciation_life_by_asset"],
		"determined_variables": ["regulatory_depreciation"],
		"tolerance": 1.0e-09,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "Ofwat PR24 Appendix 11, allowed return on capital",
		"latex": "D_{reg} = \\mathrm{RAB} / L_{reg}",
	},
	{
		"id": "allowed_revenue_requirement_definition",
		"name": "Allowed revenue requirement",
		"description": (
			"Depreciation plus the allowed return on the base, with that "
			"return taken as the blend the financial block computes -- the "
			"vanilla regulatory WACC the UKRN guidance builds. A tariff that "
			"recovers less than this under-recovers the utility; the revenue "
			"cap and the applied tariff are the instruments around it."
		),
		"system": "financial",
		"lhs": "allowed_revenue_requirement",
		"rhs": "regulatory_depreciation + regulatory_asset_base * discount_rate",
		"relation": "eq",
		"parameters": [
			"allowed_revenue_requirement", "regulatory_depreciation",
			"regulatory_asset_base", "discount_rate",
		],
		"free_variables": ["regulatory_depreciation", "regulatory_asset_base"],
		"determined_variables": ["allowed_revenue_requirement"],
		"tolerance": 1.0e-09,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "UKRN cost of capital guidance (2023), §allowed returns",
		"latex": "R^* = D_{reg} + \\mathrm{RAB} \\cdot \\mathrm{WACC}",
	},
	{
		"id": "cost_of_debt_capped",
		"name": "Debt cost within the allowed return",
		"description": (
			"The regulator's debt allowance binds the commercial cost of debt "
			"the scenario may assume: a component priced above the allowed "
			"return is the pass-through the cap regime forbids, so a scenario "
			"carrying it is inadmissible rather than silently under-recovering."
		),
		"system": "financial",
		"lhs": "cost_of_debt",
		"rhs": "allowed_return_on_debt",
		"relation": "leq",
		"parameters": ["cost_of_debt", "allowed_return_on_debt"],
		"free_variables": ["cost_of_debt", "allowed_return_on_debt"],
		"tolerance": 1.0e-06,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "UKRN cost of capital guidance (2023), §overall framework",
		"latex": "K_d \\le A_d",
	},
	{
		"id": "cost_of_equity_capped",
		"name": "Equity cost within the allowed return",
		"description": (
			"The equity-return allowance binds the cost of equity: the "
			"CAPM-estimated return a project demands cannot exceed what the "
			"regulatory settlement awards."
		),
		"system": "financial",
		"lhs": "cost_of_equity",
		"rhs": "allowed_return_on_equity",
		"relation": "leq",
		"parameters": ["cost_of_equity", "allowed_return_on_equity"],
		"free_variables": ["cost_of_equity", "allowed_return_on_equity"],
		"tolerance": 1.0e-06,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "Ofwat PR24 Appendix 11, allowed return on capital",
		"latex": "K_e \\le A_e",
	},
	{
		"id": "applied_tariff_definition",
		"name": "Applied tariff under the cap",
		"description": (
			"The revenue cap's multiplier applied to the cost-recovery tariff. "
			"A cap below 1.0 withholds part of the revenue requirement -- the "
			"incentive instrument a price-control settlement actually sets -- "
			"and a cap above 1.0 is a premium the accounts must carry."
		),
		"system": "price_demand",
		"lhs": "applied_tariff_usd_per_mwh",
		"rhs": "regulated_tariff_usd_per_mwh * revenue_cap",
		"relation": "eq",
		"parameters": [
			"applied_tariff_usd_per_mwh", "regulated_tariff_usd_per_mwh", "revenue_cap",
		],
		"free_variables": ["revenue_cap"],
		"determined_variables": ["applied_tariff_usd_per_mwh"],
		"tolerance": 1.0e-09,
		"unit_check": True,
		"solution_method": "direct",
		"linearity": "linear",
		"priority": "P1",
		"reference": "World Bank Regulation of Utilities handbook, revenue caps",
		"latex": r"p_{applied} = p_{cr} \cdot x_{cap}",
	}
]

#: The declared edges, in the shipped register's own convention: source is
#: the determinant, target the quantity it moves or bounds. A coupling batch
#: declares its edges explicitly -- the loader synthesises nothing, and an
#: equation with no declared edge is one the edge register under-reports.
#: Every edge carries its prose, because that description is what a reader
#: of the GraphML export sees.
BATCH12_EDGES: list[dict[str, str]] = [
	{
		"source": "discount_rate", "target": "weighted_average_cost_of_capital",
		"equation_id": "wacc_alias", "relationship": "equality",
		"description": "One quantity, two ids: the catalog's WACC row derives from the blend the financial block computes.",
	},
	{
		"source": "capex_usd_per_kw", "target": "regulatory_asset_base",
		"equation_id": "regulatory_asset_base_definition", "relationship": "functional",
		"description": "Gross fleet capital enters the base the allowed return is earned on.",
	},
	{
		"source": "total_capacity_mw", "target": "regulatory_asset_base",
		"equation_id": "regulatory_asset_base_definition", "relationship": "functional",
		"description": "The fleet's size sets the scale of the capital in the accounts.",
	},
	{
		"source": "accumulated_depreciation_fraction", "target": "regulatory_asset_base",
		"equation_id": "regulatory_asset_base_definition", "relationship": "functional",
		"description": "What the books have written down between gross capital and the base.",
	},
	{
		"source": "regulatory_asset_base", "target": "regulatory_depreciation",
		"equation_id": "regulatory_depreciation_definition", "relationship": "equality",
		"description": "Straight-line write-down of the base over the regulatory asset life.",
	},
	{
		"source": "depreciation_life_by_asset", "target": "regulatory_depreciation",
		"equation_id": "regulatory_depreciation_definition", "relationship": "functional",
		"description": "A longer regulatory life spreads the base thinner over the years.",
	},
	{
		"source": "regulatory_depreciation", "target": "allowed_revenue_requirement",
		"equation_id": "allowed_revenue_requirement_definition", "relationship": "functional",
		"description": "Depreciation is the first term of the revenue requirement.",
	},
	{
		"source": "regulatory_asset_base", "target": "allowed_revenue_requirement",
		"equation_id": "allowed_revenue_requirement_definition", "relationship": "functional",
		"description": "The return is earned on the base, not on gross capital.",
	},
	{
		"source": "discount_rate", "target": "allowed_revenue_requirement",
		"equation_id": "allowed_revenue_requirement_definition", "relationship": "functional",
		"description": "The return rate is the blend the financial block computes.",
	},
	{
		"source": "allowed_return_on_debt", "target": "cost_of_debt",
		"equation_id": "cost_of_debt_capped", "relationship": "constraint",
		"description": "The allowance binds the debt rate a scenario may carry.",
	},
	{
		"source": "allowed_return_on_equity", "target": "cost_of_equity",
		"equation_id": "cost_of_equity_capped", "relationship": "constraint",
		"description": "The allowance binds the equity return a valuation may assume.",
	},
	{
		"source": "regulated_tariff_usd_per_mwh", "target": "applied_tariff_usd_per_mwh",
		"equation_id": "applied_tariff_definition", "relationship": "equality",
		"description": "The applied tariff is the recovery level in the absence of a cap.",
	},
	{
		"source": "revenue_cap", "target": "applied_tariff_usd_per_mwh",
		"equation_id": "applied_tariff_definition", "relationship": "functional",
		"description": "The cap scales the recovery level; below 1 it withholds part of it.",
	},
]


def validate(directory: Path) -> list[str]:
	"""Run the merge plus the three physics gates, and return the findings."""
	from alea.prg.conflicts import detect_conflicts
	from alea.prg.graph import load_graph, load_ingested
	from alea.prg.units import check_graph

	findings: list[str] = []

	graph, report = load_ingested(directory)
	# A `<stale-edge>` drop is the disposal a corrected equation's own
	# arithmetic legalises -- the merge reports it, and this flow treats it as
	# expected rather than as lost work. Everything else refused, unknown or
	# dropped is a finding.
	stale = [d for d in report.dropped if d[0] == "<stale-edge>"]
	other = [d for d in report.dropped if d[0] != "<stale-edge>"]
	if stale:
		for eq, _detail in [(d[1], d[2]) for d in stale[:6]]:
			print(f"  stale edge disposed (equation corrected): {eq}")
	if report.refused or report.unknown or other:
		for refused in report.refused[:8]:
			findings.append(f"merge refused: {refused}")
		for unknown in report.unknown[:8]:
			findings.append(f"merge unknown: {unknown}")
		for dropped in other[:8]:
			findings.append(f"merge dropped: {dropped}")
		if len(report.refused) > 8:
			findings.append(f"... {len(report.refused)} refusals in total")
		return findings

	# Propagation at the document's own defaults. This is the gate the
	# three derived-node defects of the earlier batches failed (a cycle, an
	# out-of-range image, a missing value) -- they loaded cleanly and were
	# unevaluable, so the load success means nothing without this.
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	propagation = graph.propagate(values)

	# The derived node's own gate: every computed value inside its range.
	# Read from the graph after the propagate: the graph records excursions
	# during it (settable values are refused at the door; these are the
	# equation's own answers landing outside their declared sets).
	out_of_range = sorted(graph.range_excursions())
	for name in out_of_range[:10]:
		findings.append(
			f"derived value out of range: {name} = "
			f"{propagation.values[name]!r} not in {graph.nodes[name].range}"
		)
	if len(out_of_range) > 10:
		findings.append(f"... {len(out_of_range)} excursions in total")

	# A default scenario must be consistent under the engine. A coupling
	# batch that ships a violation of an identity at its own defaults has
	# shipped an inconsistent graph, and the conflict report is the gate.
	# `supplied` must carry the level names too: the checker's own
	# under-determination question is asked about the supplied set as a
	# whole, and pre-filtering the strings re-creates the phantom
	# market_structure/market_model findings the narrowing fix removed.
	detect = detect_conflicts(graph, propagation.values, supplied=values)
	blockers = [c.subject for c in detect.conflicts if c.blocks]
	if blockers:
		findings.append(f"default scenario blocks: {blockers}")

	# Every equation must be decidable. An undecidable equation after a
	# coupling batch means the batch coupled a node with no unit or with a
	# unit the registry does not carry -- a coupling nobody can check.
	units = check_graph(graph)
	for check in units.undecidable[:10]:
		findings.append(f"unit-undecidable: {check.summary()}")

	shipped = load_graph()
	print(
		f"{directory.name or directory}: nodes {len(shipped.nodes)} -> {len(graph.nodes)}, "
		f"equations {len(shipped.equations)} -> {len(graph.equations)}, "
		f"edges {len(shipped.edges)} -> {len(graph.edges)}, "
		f"rules {len(shipped.rules)} -> {len(graph.rules)}"
	)
	before = len(shipped.uncoupled())
	after = len(graph.uncoupled())
	print(f"  uncoupled {before} -> {after}  (this batch couples {before - after})")
	return findings


def emit(batch: str) -> int:
	"""Write the named batch's fragments to `config/prg_ingest/`.

	Node bodies are complete: read from the shipped graph, corrected by the
	batch's table, written whole. A sparse override in a fragment would
	replace the node and drop its untouched fields.
	"""
	from alea.prg.graph import load_graph

	graph = load_graph()
	nodes: dict[str, dict[str, Any]] = {}
	tables: dict[str, dict[str, Any]] = {"12": BATCH12_NODES, "13": {}}
	for name, correction in tables[batch].items():
		if name in graph.nodes:
			body = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
			body.update(correction)
			if correction.get("role") == "derived":
				body.pop("default", None)
			nodes[name] = body

		else:
			assert correction.get("default") is not None or correction.get(
				"role"
			) == "derived", (
				f"{name} is new and carries neither default nor derived role"
			)
			nodes[name] = dict(correction)

	if batch == "13":
		b13_nodes, b13_equations, b13_edges = build_batch13(graph)
		nodes.update(b13_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b13_equations)
		edges = list(BATCH12_EDGES) + b13_edges
	else:
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		edges = list(BATCH12_EDGES)

	out_dir = ROOT / "config"
	out_dir = ROOT / "config" / "prg_ingest"
	out_dir.mkdir(parents=True, exist_ok=True)
	path = out_dir / f"param_batch{batch}.yaml"
	document = {
		"parameters": nodes,
		"equations": equations,
		"relationships": edges,
		"cross_validation": [],
	}
	path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100))
	print(f"wrote {path} ({len(nodes)} nodes, {len(equations)} equations, {len(edges)} edges)")
	return 0


def main(argv: list[str] | None = None) -> int:
	args = list(argv or sys.argv[1:])
	if args and args[0].startswith("--emit"):
		return emit(args[0].removeprefix("--emit") or "12")
	dirs = [Path(a) for a in args]
	if not dirs:
		dirs = [ROOT / "config" / "prg_ingest"]
	total: list[str] = []
	for directory in dirs:
		if not directory.is_dir():
			print(f"{directory}: no such directory", file=sys.stderr)
			return 2
		total.extend(validate(directory))
	if total:
		print()
		for finding in total:
			print(f"FAIL {finding}")
		return 1
	print("\nall gates pass")
	return 0


# ---------------------------------------------------------------------------
# Batch 13 -- the technology cost layer: per-technology LCOE built from the
# fleet's own financial identities (capex, fixed/variable O&M, capacity
# factor, fuel, carbon), plus the fleet-capacity identity the optimiser's
# decision variables need as a constraint.
#
# Theory and references, by family member:
#
# * LCOE. The fixed-charge-annuity form the field standardises on:
#   LCOE = (FCR*CAPEX + FOM)/(CF*8760) + VOM + fuel + carbon, with
#   FCR = CRF x ProFinFactor and CRF the standard annuity. Implemented here
#   in the graph's own solved form: annualised_capex = capex*crf is already
#   the kernel's `annualised_capex` identity, so the technology equation
#   reads the kernel's crf rather than restating the annuity. Sources:
#   NREL ATB 2025 Equations & Variables; Short, Packey & Holt (1995),
#   NREL/TP-462-5173 (the FCR/CRF method's origin); EIA AEO LCOE
#   methodology. For thermal technology the fuel term is the heat rate
#   times the delivered fuel price; the graph carries fuel_cost_* (USD/MWh)
#   which IS that product at the fleet-level heat rate.
#   The two shipped VRE LCOE equations carried `opex_variable_battery` in
#   their numerators -- a battery cost inside a solar LCOE -- the known
#   open defect; both are corrected here and the battery's own cost enters
#   the battery LCOE, which is the plant it belongs to.
# * Battery LCOS. Annualised energy-capex per delivered energy, divided by
#   the round-trip efficiency, plus variable O&M. Sources: NREL ATB battery
#   system cost equations (storage kWh x $/kWh + power kW x $/kW); Lazard
#   LCOS method.
# * Fleet capacity identity. The optimiser's per-technology builds are
#   bounded by the fleet size they must sum within; an inequality over the
#   builds is the fleet-scale constraint the LP needs the per-tech variables
#   for, and it is what couples the endogenous capacities the equations
#   cannot read (an equation naming an endogenous node has no value to
#   evaluate; an inequality the LP carries does not need one).
# ---------------------------------------------------------------------------

#: (name, capex, opex_fixed, opex_variable, capacity_factor, fuel, emission_factor)
#: Values are the node defaults; every new node gets the unit its meaning
#: states. The cited levels: NREL ATB 2025 baselines, IEA/NEA Projected
#: Costs 2020 for the thermal fleet, IRENA Renewable Power Generation Costs
#: in 2022 for the VRE/geothermal fleet (archived in sources/), adjusted
#: to the single-country East-African setting the product serves.
TECHS: dict[str, dict[str, Any]] = {
	"solar_pv": {
		"capex": "capex_solar_pv", "opex_fixed": ("opex_fixed_solar", 9.0),
		"opex_variable": ("opex_variable_solar", 0.5),
		"emission_factor": None,
		"capacity_factor": 0.22,
	},
	"wind_onshore": {
		"capex": "capex_wind_onshore", "opex_fixed": ("opex_fixed_wind_onshore", 30.0),
		"opex_variable": ("opex_variable_wind", 3.0),
		"emission_factor": None,
		"capacity_factor": 0.40,
	},
	"wind_offshore": {
		"capex": "capex_wind_offshore", "opex_fixed": ("opex_fixed_wind_offshore", 80.0),
		"opex_variable": None, "emission_factor": None,
		"capacity_factor": 0.42,
	},
	"geothermal": {
		"capex": "capex_geothermal", "opex_fixed": ("opex_fixed_geothermal", 130.0),
		"opex_variable": ("opex_variable_geothermal", 1.0),
		"emission_factor": 0.03, "capacity_factor": 0.85, "life": 30.0,
	},
	"hydro": {
		"capex": "capex_hydro", "opex_fixed": ("opex_fixed_hydro", 22.0),
		"opex_variable": ("opex_variable_hydro", 0.5),
		"emission_factor": 0.01, "capacity_factor": 0.55, "life": 50.0,
	},
	"biomass": {
		"capex": "capex_biomass", "opex_fixed": ("opex_fixed_biomass", 65.0),
		"opex_variable": ("opex_variable_biomass", 5.0),
		"fuel": "fuel_cost_biomass",
		"emission_factor": 0.04, "capacity_factor": 0.70, "life": 25.0,
	},
	"csp": {
		"capex": "capex_csp", "opex_fixed": ("opex_fixed_csp", 95.0),
		"opex_variable": ("opex_variable_csp", 2.0),
		"emission_factor": None, "capacity_factor": 0.38, "life": 30.0,
	},
	"coal": {
		"capex": "capex_coal", "opex_fixed": "opex_fixed_coal",
		"opex_variable": ("opex_variable_coal", 4.5),
		"fuel": "fuel_cost_coal",
		"emission_factor": 0.92, "capacity_factor": 0.75, "life": 40.0,
	},
	"gas": {
		"capex": ("capex_gas", 1100.0),
		"opex_fixed": "opex_fixed_gas",
		"opex_variable": ("opex_variable_gas", 2.5),
		"fuel": "fuel_cost_gas",
		"emission_factor": 0.45, "capacity_factor": 0.60, "life": 30.0,
	},
	"nuclear": {
		"capex": "capex_nuclear", "opex_fixed": ("opex_fixed_nuclear", 95.0),
		"opex_variable": ("opex_variable_nuclear", 2.0),
		"fuel": "fuel_cost_nuclear",
		"emission_factor": 0.006, "capacity_factor": 0.90, "life": 60.0,
	},
	"oil": {
		"capex": ("capex_oil", 800.0), "opex_fixed": ("opex_fixed_oil", 25.0),
		"opex_variable": ("opex_variable_oil", 6.0),
		"fuel": "fuel_cost_oil",
		"emission_factor": 0.78, "capacity_factor": 0.15, "life": 25.0,
	},
}


def build_batch13(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
	"""The technology LCOE family: nodes, equations and edges, generated.

	Every operand the table names that the graph does not carry is emitted
	here with the level and the unit its meaning states.
	"""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []

	def declare_node(name: str, body: dict[str, Any]) -> None:
		if name in graph.nodes:
			full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
			for key, value in body.items():
				if value is not None and key != "default":
					full[key] = value
				elif value is not None and key == "default" and full.get("role") != "derived":
					full[key] = value
			if full.get("role") == "derived":
				full.pop("default", None)
			nodes[name] = full
		else:
			complete = {
				"name": name.replace("_", " ").capitalize(),
				"description": "",
				"category": "Cost",
				"type": "float",
				"unit": None,
				"range": None,
				"role": "exogenous",
				"determinism": "fixed",
				"priority": "P2",
				"status": "existing",
				"source": None,
				"users": ["Planners"],
			}
			complete.update(body)
			nodes[name] = complete

	TECH_COST_SOURCE = (
		"NREL ATB 2025; IEA/NEA Projected Costs of Generating Electricity 2020; "
		"IRENA Renewable Power Generation Costs in 2022"
	)

	# The technology's own capacity factor at the regional level. The shipped
	# solar node carried a 0.5 placeholder -- half the sky, the midpoint of an
	# unknown range, not a capacity factor -- and a utility PV plant in the
	# single-country setting produces at about 0.22 of its rated capacity
	# (NREL ATB 2025 global baselines, adjusted to the regional resource).
	declare_node("solar_pv_capacity_factor", {
		"default": 0.22,
		"description": "Utility PV annual net output over rated capacity, at the regional resource level. Was a 0.5 placeholder: the midpoint of a range nobody declared, not a capacity factor any plant produces. NREL ATB 2025 global baseline is 0.16-0.24 across regions; this setting takes 0.22.",
	})

	for tech, row in TECHS.items():
		tech_prose = tech.replace("_", " ")
		capex = row["capex"]
		fixed = row.get("opex_fixed")
		variable = row.get("opex_variable")
		fuel = row.get("fuel")
		emission = row.get("emission_factor")
		life = float(row.get("life", 25.0))  # type: ignore[arg-type]
		cf_default = row["capacity_factor"]

		# --- operand nodes, each at the unit and level its meaning states ---
		if isinstance(capex, tuple):
			capex_name, capex_default = capex
			declare_node(capex_name, {
				"description": (
					f"Overnight capital cost of {tech_prose} capacity; the level is "
					"the installed-cost literature's, at the regional adjustment the "
					"single-country setting carries."
				),
				"category": "Cost", "unit": "USD/kW", "range": [100.0, 15000.0],
				"default": capex_default, "role": "exogenous", "determinism": "physical",
				"priority": "P1", "source": TECH_COST_SOURCE, "users": ["Developers"],
			})
		else:
			capex_name = capex
		life_name = f"asset_life_{tech}"
		declare_node(life_name, {
			"description": (
				f"Economic life of {tech_prose} assets, over which the capital charge "
				"annualises; a longer life is a smaller annuity at the same discount rate."
			),
			"category": "Cost", "unit": "years", "range": [5.0, 80.0],
			"default": life, "role": "exogenous", "determinism": "fixed",
			"priority": "P2", "source": "NREL ATB 2025 economic lifetime by technology",
			"users": ["Investors"],
		})
		if isinstance(fixed, str):
			fixed_name, fixed_default = fixed, None  # type: ignore[misc]
		else:
			fixed_name, fixed_default = fixed  # type: ignore[misc]
			declare_node(fixed_name, {
				"description": (
					f"Fixed operations and maintenance for {tech_prose}: the per-kilowatt "
					"annual cost of staff, inspection and scheduled overhaul, paid whether "
					"or not the plant runs."
				),
				"category": "Cost", "unit": "USD/kW/year", "range": [0.0, 400.0],
				"default": fixed_default, "role": "exogenous", "determinism": "physical",
				"priority": "P1", "source": TECH_COST_SOURCE, "users": ["Operators"],
			})
		variable_name = None
		if variable is not None:
			if isinstance(variable, str):
				variable_name = variable
			else:
				variable_name, variable_default = variable
				declare_node(variable_name, {
					"description": (
						f"Variable O&M for {tech_prose}: wear and consumables paid per "
						"megawatt-hour produced, the cost that runs with the energy."
					),
					"category": "Cost", "unit": "USD/MWh", "range": [0.0, 20.0],
					"default": variable_default, "role": "exogenous", "determinism": "physical",
					"priority": "P2", "source": TECH_COST_SOURCE, "users": ["Operators"],
				})
		cf_name = f"capacity_factor_{tech}"
		declare_node(cf_name, {
			"description": (
				f"Annual net output over rated capacity for {tech_prose}, in the "
				"single-country setting: solar and wind carry the regional climate and "
				"resource levels, thermal carries the plant's own duty."
			),
			"category": "Technology", "unit": "1", "range": [0.0, 1.0],
			"default": cf_default, "role": "exogenous", "determinism": "physical",
			"priority": "P1", "source": "NREL ATB 2025 capacity factors, adjusted to the regional resource",
			"users": ["Planners"],
		})
		ef_name = None
		if emission is not None:
			ef_name = f"emission_factor_{tech}_t_per_mwh"
			declare_node(ef_name, {
				"description": (
					f"CO2 per megawatt-hour for {tech_prose}: stack factor from the fuel's "
					"carbon content; lifecycle additions folded in for the low-carbon "
					"technologies, whose stack term is zero."
				),
				"category": "Technology", "unit": "tonne/MWh", "range": [0.0, 1.5],
				"default": emission, "role": "exogenous", "determinism": "physical",
				"priority": "P1", "source": "IPCC lifecycle emission factors, 2014; fuel carbon contents",
				"users": ["Regulators"],
			})

		# --- the technology's own capital recovery factor ---
		declare_node(f"crf_{tech}", {
			"description": (
				f"Capital recovery factor at the fleet discount rate over the {tech_prose} "
				"asset life: the annual charge per unit of capital. Same formula as the "
				"kernel's fleet crf, per technology, because a 60-year nuclear life and "
				"a 25-year PV life discount differently."
			),
			"category": "Cost", "unit": "1/year", "range": [0.001, 1.0],
			"role": "derived", "determinism": "fixed", "priority": "P2",
			"status": "existing", "source": "Standard annuity formula",
			"users": ["Investors"],
		})
		equations[f"crf_{tech}_definition"] = {
			"id": f"crf_{tech}_definition",
			"name": f"CRF ({' '.join(tech_prose.split())})",
			"description": (
				"The standard annuity: a constant annual charge whose present value equals "
				"one unit of capital over this technology's life, at the fleet discount "
				"rate. Reference: the CRF row in sources/INDEX.md; NREL ATB 2025 states "
				"the same form."
			),
			"system": "financial",
			"lhs": f"crf_{tech}",
			"rhs": (
				f"discount_rate * (1 + discount_rate) ** {life_name} / ((1 + discount_rate) ** {life_name} - 1)"
			),
			"relation": "eq",
			"parameters": [f"crf_{tech}", "discount_rate", life_name],
			"free_variables": ["discount_rate", life_name],
			"determined_variables": [f"crf_{tech}"],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "numeric", "linearity": "nonlinear",
			"priority": "P2", "reference": "Standard annuity formula",
			"latex": r"\mathrm{CRF}_{tech} = r(1+r)^L / ((1+r)^L - 1)",
		}
		for sym in ("discount_rate", life_name):
			edges.append({
				"source": sym, "target": f"crf_{tech}",
				"equation_id": f"crf_{tech}_definition", "relationship": "functional",
				"description": "Enters the annuity whose yearly charge carries the capital.",
			})

		# --- the technology's own LCOE ---
		# The two VRE technologies' LCOE equations already ship, with a corrected
		# defect in them: their ids are the shipped ones so this batch *replaces*
		# rather than duplicates, and their targets keep the names a scenario
		# reader already knows.
		shipped_lcoe = {
			"solar_pv": ("lcoe_solar_definition", "lcoe_solar_usd_per_mwh"),
			"wind_onshore": ("lcoe_wind_definition", "lcoe_wind_usd_per_mwh"),
		}
		eq_id, lhs = shipped_lcoe.get(
			tech, (f"lcoe_{tech}_definition", f"lcoe_{tech}_usd_per_mwh")
		)
		if tech in shipped_lcoe:
			# The shipped equations already route through the per-technology
			# annualised capex the kernel derives (capex * crf, per tech) --
			# a reviewed chain this correction does not restructure. The two
			# defects the confound review named are corrected here and only
			# here: the battery variable-O&M term -- a battery cost inside a
			# generation technology's LCOE -- leaves, replaced by the
			# technology's own variable O&M; and the onshore wind equation
			# stops reading the fleet-average capacity factor, which was
			# 0.35 for a resource whose stated level is 0.40, and reads the
			# technology's own instead.
			shipped = shipped_lcoe[tech]
			own_vom = variable_name or ""
			own_cf = cf_name
			shipped_rhs = graph.equations[shipped[0]].rhs  # type: ignore[union-attr]
			corrected = shipped_rhs.replace("opex_variable_battery", own_vom)
			if tech == "wind_onshore":
				# The fleet-average capacity factor leaves the arithmetic and
				# the technology's own level enters it -- registered in the
				# equation's declared lists below, like every other symbol.
				corrected = corrected.replace("capacity_factor", own_cf)
			equations[shipped[0]] = dict(graph.equations[shipped[0]].model_dump(mode="json"))
			equations[shipped[0]]["rhs"] = corrected
			# The declared lists are the corrected arithmetic's: the battery
			# name leaves `parameters` with the term itself, and a declared
			# parameter the arithmetic never names is the engine-never-applies
			# finding the loader refuses.
			# The declared lists are the corrected arithmetic's own closure:
			# every symbol the sides name is a parameter, the determined ones
			# stay determined, and everything else is free. Reconciling the
			# lists here rather than hand-diffing keeps the correction total
			# for any symbol the arithmetic gains or loses.
			from alea.prg.dsl import parse_side

			shipped_body = equations[shipped[0]]
			named = set(parse_side(str(shipped_body["lhs"])).symbols)
			named |= set(parse_side(str(shipped_body["rhs"])).symbols)
			determined = set(shipped_body["determined_variables"])
			shipped_body["determined_variables"] = sorted(determined & named)
			shipped_body["free_variables"] = sorted(named - determined)
			shipped_body["parameters"] = sorted(named)
			equations[shipped[0]]["description"] = (
				equations[shipped[0]]["description"] or ""
			).replace(
				"the shipped graph does not carry one",
				"the technology's own variable O&M, at the level the cost literature states",
			)
			equations[shipped[0]]["description"] += (
				" Corrected from its predecessor, which carried opex_variable_battery "
				"in a generation technology's numerator -- a battery cost inside a "
				"plant with no battery; the battery's cost now belongs to the "
				"battery's own LCOE."
			)
			# The edges a corrected equation carries are the *arithmetic's*
			# own closure, not the table's operand names: the shipped chain
			# routes through the derived annualised-capex nodes, so the
			# corrected symbol set is what the corrected sides parse to,
			# and an edge for a symbol the equation no longer reads is a
			# stale claim by definition.
			for sym in sorted(
				set(parse_side(str(corrected)).symbols)
				| set(parse_side(str(lhs)).symbols)
			):
				edges.append({
					"source": sym, "target": lhs,
					"equation_id": eq_id, "relationship": "functional", "strength": "soft",
					"description": "Enters the technology's levelised cost.",
				})
			tech = ""  # the generic builder below does not run for these two
			continue

		terms = [f"({capex_name} * crf_{tech} + {fixed_name}) * 1000 / (8760 * {cf_name})"]
		free = [capex_name, fixed_name, cf_name]
		if variable_name is not None:
			terms.append(variable_name)
			free.append(variable_name)
		if fuel is not None:
			terms.append(str(fuel))
			free.append(str(fuel))
		if ef_name is not None:
			terms.append(f"{ef_name} * carbon_price_usd_per_tco2")
			free += [ef_name, "carbon_price_usd_per_tco2"]
		# The per-tech crf the arithmetic reads is determined by its own
		# equation: a parameter of this one, not a free knob of it.
		free.append(f"crf_{tech}")
		declare_node(lhs, {
			"description": (
				f"{tech_prose.capitalize()} levelised cost, from its own capex, O&M, "
				"capacity factor, fuel and carbon terms."
			),
			"category": "Cost", "unit": "USD/MWh", "range": [0.0, 500.0],
			"role": "derived", "determinism": "physical", "priority": "P1",
			"status": "existing", "source": TECH_COST_SOURCE, "users": ["Planners", "Investors"],
		})
		confound_note = (
			" This equation's predecessor carried opex_variable_battery in its numerator, "
			"a battery cost inside a generation technology's LCOE; corrected here -- the "
			"battery's cost is carried by the battery's own LCOE, which is the plant it is."
			if tech in ("solar_pv", "wind_onshore") else ""
		)
		equations[eq_id] = {
			"id": eq_id,
			"name": f"LCOE ({tech_prose})",
			"description": (
				f"{tech_prose.capitalize()} levelised cost in the fixed-charge-annuity form the field "
				"standardises on: the annualised capital charge over the energy the plant actually "
				"produces, plus fixed and variable O&M, the fuel the fleet's heat rate prices, and "
				"the stack's carbon at carbon_price. Dimensional check: a USD/kW/year rate over an "
				"hours/year denominator with a dimensionless capacity factor is USD/MWh, and every "
				"per-MWh term shares it." + confound_note
			),
			"system": "cost_accounting",
			"lhs": lhs,
			"rhs": " + ".join(terms),
			"relation": "eq",
			"parameters": [lhs] + free,
			"free_variables": free,
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1",
			"reference": "NREL ATB 2025 Equations & Variables; Short, Packey & Holt (1995), NREL/TP-462-5173; EIA AEO LCOE methodology",
			"latex": r"\mathrm{LCOE}_{t} = ((\mathrm{capex}_t \\cdot \\mathrm{CRF}_t + \\mathrm{FOM}_t) \\cdot 10^3) / (8760 \\cdot \\mathrm{CF}_t) + \\mathrm{VOM}_t + \\mathrm{fuel}_t + e_t \\cdot p_{\\mathrm{CO2}}",
		}
		# The two shipped VRE LCOE equations are replaced here, and the
		# shipped document already declares their edges at a soft strength.
		# A fragment cannot re-declare an existing (source, target, equation)
		# triple to a different body -- the merge refuses the disagreement --
		# so the corrected equations keep the shipped strength at validation
		# time, and the bake upgrades it to hard as a named correction. What
		# the shipped strength was the hedge of -- a substituted variable-O&M
		# term -- is gone from the equation; the strength rides on this
		# declaration until the bake carries the correction.
		strength = "soft" if tech in shipped_lcoe else "hard"
		for sym in free:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"strength": strength,
				"description": "Enters the technology's levelised cost.",
			})

		# The two shipped VRE LCOE equations are *replaced* here, so the
		# fragment must also re-declare the shipped edges that cite them: an
		# equation cited by edges of two strengths is refused. The shipped
		# strength was soft -- the hedge of the substitution the equation's
		# own description apologises for -- and the corrected identity is a
		# physical one, so the re-declaration carries hard. The shipped
		# `opex_variable_battery` edges for these two ids stay in the shipped
		# document (a fragment cannot remove an entry); the bake drops them,
		# named, because their claim -- a battery cost entering a solar or
		# wind LCOE -- is exactly the confound this correction removes.
	# --- the reference build, corrected to the regional fleet ---
	# The shipped endogenous defaults were placeholder midpoints (a nuclear
	# fleet of 500,000 MW against a 10,000 MW plan) and sum to four times the
	# fleet total they belong to, which is what makes the fleet balance a
	# constraint that blocks its own reference scenario. The reference build
	# is the single-country fleet's actual scale: hydro and geothermal lead,
	# thermal fills, the un-built technologies read zero until built.
	REFERENCE_BUILDS: dict[str, float] = {
		"coal_capacity": 3000.0, "gas_capacity": 1500.0, "oil_capacity": 300.0,
		"nuclear_capacity": 0.0, "hydro_capacity": 1500.0, "geothermal_capacity": 800.0,
		"biomass_capacity": 100.0, "wind_onshore_capacity": 2000.0,
		"wind_offshore_capacity": 0.0, "csp_capacity": 0.0, "battery_capacity": 300.0,
		"phs_capacity": 200.0, "hydrogen_storage_capacity": 0.0,
		"thermal_storage_capacity": 0.0,
	}
	for build_name, build_default in REFERENCE_BUILDS.items():
		node = graph.nodes.get(build_name)
		assert node is not None and node.role.value == "endogenous", build_name
		full = dict(node.model_dump(exclude={"id"}, mode="json"))
		full["default"] = build_default
		nodes[build_name] = full

	# --- the un-built technologies' reference data ---
	# Twelve technologies carry unit=None and a placeholder default of
	# 500000 MW: the catalog's mid-point-of-unknown-range pattern, applied to
	# decision variables. A fusion plant of half a million megawatts is not a
	# reference value; zero is. The units are MW (MWh for the storages), the
	# ranges are the technology's own plausible build band, and the default
	# is the honest one -- not deployed -- until a source states otherwise.
	UNBUILT_TECHS: dict[str, tuple[str, str, str]] = {
		"fusion_capacity": ("MW", "unbuilt", "0.0"),
		"small_modular_reactor_capacity": ("MW", "unbuilt", "0.0"),
		"tidal_range_capacity": ("MW", "unbuilt", "0.0"),
		"salinity_gradient_capacity": ("MW", "unbuilt", "0.0"),
		"flywheel_capacity": ("MW", "unbuilt", "0.0"),
		"compressed_air_capacity": ("MW", "unbuilt", "0.0"),
		"hydrogen_fuel_cell_capacity": ("MW", "unbuilt", "0.0"),
		"electrolyser_capacity": ("MW", "unbuilt", "0.0"),
		"biogas_capacity": ("MW", "unbuilt", "0.0"),
		"landfill_gas_capacity": ("MW", "unbuilt", "0.0"),
		"waste_to_energy_capacity": ("MW", "unbuilt", "0.0"),
		"gasification_capacity": ("MW", "unbuilt", "0.0"),
		"pyrolysis_capacity": ("MW", "unbuilt", "0.0"),
	}
	for tech_name, (unit, _why, default) in UNBUILT_TECHS.items():
		node = graph.nodes.get(tech_name)
		if node is None:
			continue
		prose = tech_name.replace("_", " ")
		full = dict(node.model_dump(exclude={"id"}, mode="json"))
		full["unit"] = unit
		full["range"] = [0.0, 1000.0]
		full["default"] = 0.0
		full["description"] = (
			f"Installed {prose} capacity in the reference build, at zero: the technology is "
			"not deployed in the single-country setting today, and a placeholder midpoint "
			"of an unknown range is not a reference build."
		)
		nodes[tech_name] = full

	# --- the fleet's capacity identity, as a constraint over the builds ---
	# An endogenous node is one the optimiser chooses, so it has no value at
	# propagation time and no *equation* can read it -- but the LP an
	# inequality rides on has it as a decision variable, which is the
	# coupling the fleet's own identity carries.
	# The builds the balance constrains are the *leaf* technologies: an
	# endogenous node an equation already reads is an aggregate the fleet's
	# other identities carry (firm capacity reads `thermal_capacity_mw`), and
	# an aggregate in this sum would double-count its own members.
	already_read = set()
	for eq in graph.equations.values():
		already_read.update(eq.parameters)
	builds = sorted(
		name for name, node in graph.nodes.items()
		if node.role.value == "endogenous"
		and name.endswith(("_capacity", "_capacity_mw"))
		and not graph.affected_by(name)
		and not name in (
			# The fleet's own aggregates: the solve's chosen groups. They are
			# read by the fleet's identities (firm_capacity reads
			# thermal_capacity_mw), so they are not the floating leaves this
			# constraint exists for -- and their values are already built into
			# the members they aggregate, so they must not enter this sum.
			"thermal_capacity_mw", "dispatchable_re_capacity_mw",
			"storage_capacity_mw", "solar_pv_capacity", "firm_capacity_mw",
		)
	)
	nodes["firm_build_fleet_mw"] = {
		"name": "Fleet build total",
		"description": (
			"Sum of the optimiser's per-technology builds. Not a decision the "
			"graph computes in propagation -- the technologies' variables are "
			"the LP's -- but the identity every build set must satisfy is "
			"declared here, and the reserve margins read the firm part of it."
		),
		"category": "Supply", "type": "float", "unit": "MW",
		"range": [0.0, 2000000.0], "default": 10000.0,
		"role": "endogenous", "determinism": "physical",
		"priority": "P1", "status": "existing",
		"source": "The optimiser's own capacity decisions",
		"users": ["Planners"],
	}
	equations["fleet_build_balance"] = {
		"id": "fleet_build_balance",
		"name": "The build set within the fleet",
		"description": (
			"The optimiser's per-technology builds must not exceed the fleet "
			"size the plan declares for them. This is a *constraint* coupling "
			"-- the equation the LP carries, not an identity the evaluator "
			"solves -- because the builds are decision variables with no "
			"single value until the solve settles them."
		),
		"system": "reserve_margin",
		"lhs": " + ".join(builds),
		"rhs": "total_capacity_mw + storage_headroom_mw",
		"relation": "leq",
		"parameters": builds + ["total_capacity_mw", "storage_headroom_mw"],
		"free_variables": ["total_capacity_mw", "storage_headroom_mw"],
		"tolerance": 1.0e-06, "unit_check": True,
		"solution_method": "direct", "linearity": "linear",
		"priority": "P1",
		"reference": "Least-cost generation expansion: Koltsaklis & Dagoumas (2018), Applied Energy 230:563-589",
		"latex": r"\\sum_t C_t \\le C_{total} + H_{storage}",
	}
	nodes["storage_headroom_mw"] = {
		"name": "Storage build headroom",
		"description": (
			"How far the storage builds may exceed the generation fleet's "
			"declared size: storage is energy-shifting, not generation, so a "
			"plan can carry battery plus pumped hydro without the fleet's "
			"nameplate growing by the same amount."
		),
		"category": "Supply", "type": "float", "unit": "MW",
		"range": [0.0, 500000.0], "default": 5000.0, "role": "free",
		"determinism": "policy", "priority": "P2", "status": "existing",
		"source": "Planning policy; the storage allowance a capacity plan grants",
		"users": ["Planners"],
	}
	for build in builds:
		edges.append({
			"source": build, "target": "total_capacity_mw",
			"equation_id": "fleet_build_balance", "relationship": "constraint",
			"description": "The build is one term the fleet size governs; the build set may not exceed it plus storage headroom.",
		})
	edges.append({
		"source": "storage_headroom_mw", "target": "total_capacity_mw",
		"equation_id": "fleet_build_balance", "relationship": "constraint",
		"description": "The storage allowance widens the fleet ceiling for energy-shifting builds.",
	})
	return nodes, equations, edges



if __name__ == "__main__":
	sys.exit(main())
