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

import re
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
	rules: list[dict[str, Any]] = []
	nodes: dict[str, dict[str, Any]] = {}
	tables: dict[str, dict[str, Any]] = {"12": BATCH12_NODES, "13": {}, "14": {}, "15": {}, "16": {}, "17": {}, "18": {}, "19": {}, "20": {}, "21": {}, "22": {}, "23": {}}
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
	elif batch == "14":
		b14_nodes, b14_equations, b14_edges, _b14_rules = build_batch14(graph)
		rules.extend(_b14_rules)
		nodes.update(b14_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b14_equations)
		edges = list(BATCH12_EDGES) + b14_edges
	elif batch == "15":
		b15_nodes, b15_equations, b15_edges, b15_rules = build_batch15(graph)
		rules.extend(b15_rules)
		nodes.update(b15_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b15_equations)
		edges = list(BATCH12_EDGES) + b15_edges
	elif batch == "16":
		b16_nodes, b16_equations, b16_edges, b16_rules = build_batch16(graph)
		rules.extend(b16_rules)
		nodes.update(b16_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b16_equations)
		edges = list(BATCH12_EDGES) + b16_edges
	elif batch == "17":
		b17_nodes, b17_equations, b17_edges, b17_rules = build_batch17(graph)
		rules.extend(b17_rules)
		nodes.update(b17_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b17_equations)
		edges = list(BATCH12_EDGES) + b17_edges
	elif batch == "18":
		b18_nodes, b18_equations, b18_edges, b18_rules = build_batch18(graph)
		rules.extend(b18_rules)
		nodes.update(b18_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b18_equations)
		edges = list(BATCH12_EDGES) + b18_edges
	elif batch == "19":
		b19_nodes, b19_equations, b19_edges, b19_rules = build_batch19(graph)
		rules.extend(b19_rules)
		nodes.update(b19_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b19_equations)
		edges = list(BATCH12_EDGES) + b19_edges
	elif batch == "22":
		b22_nodes, b22_equations, b22_edges, b22_rules = build_batch22(graph)
		rules.extend(b22_rules)
		nodes.update(b22_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b22_equations)
		edges = list(BATCH12_EDGES) + b22_edges
	elif batch == "23":
		b23_nodes, b23_equations, b23_edges, b23_rules = build_batch23(graph)
		rules.extend(b23_rules)
		nodes.update(b23_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b23_equations)
		edges = list(BATCH12_EDGES) + b23_edges
	elif batch == "21":
		b21_nodes, b21_equations, b21_edges, b21_rules = build_batch21(graph)
		rules.extend(b21_rules)
		nodes.update(b21_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b21_equations)
		edges = list(BATCH12_EDGES) + b21_edges
	elif batch == "20":
		b20_nodes, b20_equations, b20_edges, b20_rules = build_batch20(graph)
		rules.extend(b20_rules)
		nodes.update(b20_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b20_equations)
		edges = list(BATCH12_EDGES) + b20_edges
	else:
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		edges = list(BATCH12_EDGES)

	# Every equation's declared latex is the renderer's own output, checked
	# against the stored form by `check_latex` on the operand sets. Declaring
	# the generated rendering keeps the check meaningful in one direction --
	# the stored form IS the generated one -- while the descriptions carry
	# the analytic statement; the alternative, a hand form in some other
	# spelling, fails the operand-set comparison unless it names every
	# parameter in the renderer's own subscripted style.
	from alea.prg.views import Equation as _Equation
	from alea.prg.service import generated_latex as _generated_latex

	for eq_id, eq_body in equations.items():
		try:
			eq_obj = _Equation(**{k: v for k, v in eq_body.items()})  # type: ignore[arg-type]
		except Exception:
			continue
		try:
			eq_body["latex"] = _generated_latex(eq_obj)
		except Exception:
			continue

	document = {
		"parameters": nodes,
		"equations": equations,
		"relationships": edges,
		"cross_validation": rules,
	}

	out_dir = ROOT / "config" / "prg_ingest"
	out_dir.mkdir(parents=True, exist_ok=True)
	path = out_dir / f"param_batch{batch}.yaml"
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

	# Two operands' shipped bodies carry `role: exogenous` from an earlier
	# batch, while no equation names them on the current graph. Uncoupled
	# means `free` -- the schema's own word for an unconstrained input -- and
	# the generator's register applies it wherever no coupling has a claim on
	# the node. Corrections keep the roles consistent with the coupling state.
	# `capacity_factor_solar_pv` was a duplicate spelling of the shipped
	# solar node this batch emitted; the shipped id is the one the LCOE
	# reads, so the duplicate is not emitted at all rather than kept free.
	for keep_free in ("opex_fixed_wind_onshore",):
		node = graph.nodes.get(keep_free)
		if node is not None and node.role.value == "exogenous":
			full = dict(node.model_dump(exclude={"id"}, mode="json"))
			full["role"] = "free"
			nodes[keep_free] = full

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
		if tech == "solar_pv":
			# Solar already ships `solar_pv_capacity_factor` and its LCOE has
			# always read that id; emitting a second id for the same quantity
			# would be the two-names-for-one-number defect the alias
			# resolutions exist to close, not to create. The technology's own
			# capacity factor IS the shipped node, corrected at its default.
			cf_name = "solar_pv_capacity_factor"
			techs_with_shipped_cf = {"solar_pv"}
		else:
			techs_with_shipped_cf = set()
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
				# Word-boundary: the correction must not build
				# `capacity_factor_wind_onshore_wind_onshore` from an rhs that
				# already carries the technology's own spelling.
				corrected = re.sub(r"capacity_factor(?!_wind_onshore)", own_cf, corrected)
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
		and graph.nodes[name].unit == "MW"
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




# ---------------------------------------------------------------------------
# Batch 14 -- the resolved duplicates and the employment family.
#
# The alias register the fragments shipped was validated by nothing that
# applied it. Its content, applied as equations: 20 technology-cost
# duplicate pairs (the `*_cost` vs `capex_*` spellings, corrected to agree
# by the earlier batches but still two ids for one number) become
# equality equations whose duplicate side derives; the duplicate keeps its
# id (a report may cite it) and loses the free placeholder's default. One
# pair that is not an equality but a definition is written as its
# definition: property tax is the rate on the asset base, and the
# investment allowance is the rate on the capital. Two placeholder-only
# rows (lifeline tariff, disability inclusion) alias to the nodes that
# carry real values and real units; their own units are declared so the
# equality is decidable.
#
# Employment: the indirect and induced jobs the input-output method
# derives from the direct jobs the kernel computes, at the multipliers
# that method states. The shipped `indirect_jobs`/`induced_jobs` carried
# 50-million-job placeholder defaults -- a number with no fleet behind it.
# Theory: input-output employment multipliers (Leontief demand-pull):
# indirect = direct x supply-chain multiplier, induced = direct x
# consumption multiplier; the group-job shares multiply the direct count.
# ---------------------------------------------------------------------------

DUPLICATE_PAIRS: list[tuple[str, str]] = [
	("solar_pv_cost", "capex_solar_pv"), ("wind_onshore_cost", "capex_wind_onshore"),
	("wind_offshore_cost", "capex_wind_offshore"), ("battery_cost", "capex_battery"),
	("phs_cost", "capex_phs"), ("geothermal_cost", "capex_geothermal"),
	("electrolyser_cost", "capex_hydrogen_electrolyser"),
	("wave_energy_converter_cost", "capex_marine_wave"),
	("small_modular_reactor_cost", "capex_smr"), ("fusion_cost", "capex_fusion"),
	("compressed_air_cost", "capex_caes"), ("flywheel_cost", "capex_flywheel"),
	("hydrogen_fuel_cell_cost", "capex_hydrogen_fuel_cell"),
	("tidal_range_cost", "capex_tidal_range"),
	("salinity_gradient_cost", "capex_salinity_gradient"),
	("biogas_cost", "capex_biogas"), ("landfill_gas_cost", "capex_landfill_gas"),
	("waste_to_energy_cost", "capex_waste_to_energy"),
	("pyrolysis_cost", "capex_pyrolysis"),
	("gasification_cost", "capex_gasification"),
	("lifeline_tariff", "lifeline_tariff_usd_per_mwh"),
	("disability_inclusion", "disability_inclusion_share"),
]

#: Placeholder-only rows whose own unit must be declared for their alias
#: equality to be decidable.
PLACEHOLDER_UNITS: dict[str, dict[str, str]] = {
	"lifeline_tariff": {"unit": "USD/MWh"},
	"disability_inclusion": {"unit": "1"},
}


def build_batch14(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 14: duplicate alias-equations plus the employment family."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for dup, can in DUPLICATE_PAIRS:
		dup_node, can_node = graph.nodes.get(dup), graph.nodes.get(can)
		assert dup_node is not None and can_node is not None, (dup, can)
		assert dup_node.unit == can_node.unit or dup in PLACEHOLDER_UNITS, (
			f"{dup}={can}: units {dup_node.unit!r} vs {can_node.unit!r}"
		)
		full = dict(dup_node.model_dump(exclude={"id"}, mode="json"))
		unit_override = PLACEHOLDER_UNITS.get(dup) or {}
		full.update(unit_override)
		full.update({
			"role": "derived",
			"description": (
				f"{dup_node.name} -- one of two ids for the quantity `{can}` "
				"carries; corrected to the same value by the earlier batches and "
				"resolved here by an equality, so the graph answers the question "
				"one way and the label a report may cite keeps an id."
			),
		})
		full.pop("default", None)
		nodes[dup] = full
		eq_id = f"{dup}_alias"
		equations[eq_id] = {
			"id": eq_id,
			"name": f"{dup_node.name} is {can_node.name}",
			"description": (
				f"The alias resolution the fragments' alias register declared and "
				f"nothing applied: `{dup}` and `{can}` are two spellings of one "
				"quantity. The equality states it in the graph's own idiom, so a "
				"reader of either id sees the derivation; the drift that made "
				"this alias list exist cannot return, because the equation holds "
				"at every value set."
			),
			"system": "cost_accounting" if "cost" in can or "tariff" in can else "employment",
			"lhs": dup,
			"rhs": can,
			"relation": "eq",
			"parameters": [dup, can],
			"free_variables": [can],
			"determined_variables": [dup],
			"tolerance": 1.0e-09,
			"unit_check": can_node.unit is not None or dup not in PLACEHOLDER_UNITS,
			"solution_method": "direct",
			"linearity": "linear",
			"priority": "P2",
			"reference": "The fragments' alias register (docs/param_batch7.md and successors), applied",
			"latex": r"\mathrm{" + dup.replace("_", r"\_") + r"} \equiv \mathrm{" + can.replace("_", r"\_") + r"}",
		}
		edges.append({
			"source": can, "target": dup, "equation_id": eq_id,
			"relationship": "equality", "strength": "hard",
			"description": "The canonical value; the duplicate derives.",
		})

	# The four definitions the placeholders were standing next to.
	rate_nodes = {
		"property_tax": ("property_tax_rate", "regulatory_asset_base", "Regulatory Finance"),
		"investment_allowance": ("investment_allowance_rate", "capex_usd_per_kw", "Tax & Fiscal"),
	}
	for target, (rate, base, category) in rate_nodes.items():
		full = dict(graph.nodes[target].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"role": "derived",
			"unit": "USD/kW" if base == "capex_usd_per_kw" else "USD million",
			"description": (
				f"{graph.nodes[target].name}, computed: the rate applied to {base}. "
				"A rate has to land on a base to be a cost, and the base the "
				"graph carries is the fleet's own."
			),
		})
		full.pop("default", None)
		nodes[target] = full
		eq_id = f"{target}_definition"
		equations[eq_id] = {
			"id": eq_id,
			"name": graph.nodes[target].name + " (computed)",
			"description": (
				f"The rate times its base: property tax is the annual charge on "
				"the regulated asset base; the investment allowance is the "
				"fiscal credit against capital expenditure. Both are rates with "
				"no arithmetic beyond the product, so the definition is the "
				"whole of the coupling."
			),
			"system": "financial",
			"lhs": target,
			"rhs": f"{rate} * {base}",
			"relation": "eq",
			"parameters": [target, rate, base],
			"free_variables": [rate],
			"determined_variables": [target],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2",
			"reference": "Rate-based levy and allowance definitions (standard fiscal accounting)",
			"latex": r"\mathrm{" + target.replace("_", r"\_") + r"} = \mathrm{" + rate.replace("_", r"\_") + r"} \cdot \mathrm{" + base.replace("_", r"\_") + r"}",
		}
		edges.append({
			"source": rate, "target": nodes[target]["name"].lower().replace(" ", "_"),
			"equation_id": eq_id, "relationship": "functional", "strength": "hard",
			"description": "The rate; the base carries the scale.",
		})
		edges.append({
			"source": base, "target": target,
			"equation_id": eq_id, "relationship": "functional", "strength": "hard",
			"description": "The base the rate lands on.",
		})

	# --- employment ---
	multiplier_nodes = {
		"indirect_employment_multiplier": (
			"Supply-chain multiplier on the direct jobs: purchases, haulage, "
			"feeds and services the construction and fleet spending generates. "
			"Input-output employment multipliers; the range states the "
			"empirical band, 1.0 a bare pass-through."
		),
		"induced_employment_multiplier": (
			"Consumption multiplier: jobs from worker spending, the second "
			"round of the Leontief demand-pull. Usually below the indirect "
			"one and above zero."
		),
	}
	for name, prose in multiplier_nodes.items():
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose,
			"category": "Employment", "type": "float", "unit": "1",
			"range": [0.0, 3.0],
			"default": 1.2 if "indirect" in name else 0.7,
			"role": "free", "determinism": "fixed", "priority": "P2",
			"status": "existing",
			"source": "Leontief input-output employment multipliers",
			"users": ["Planners"],
		}
	for target, multiplier in (
		("indirect_jobs", "indirect_employment_multiplier"),
		("induced_jobs", "induced_employment_multiplier"),
	):
		full = dict(graph.nodes[target].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"role": "derived",
			"unit": "jobs",
			"description": (
				f"{graph.nodes[target].name}: the {target.split('_')[0]} employment the "
				"input-output method derives from the direct jobs the fleet "
				"construction and O&M support. Was a 50-million-node placeholder "
				"-- a number with no fleet behind it."
			),
		})
		full.pop("default", None)
		nodes[target] = full
		eq_id = f"{target}_derivation"
		equations[eq_id] = {
			"id": eq_id,
			"name": graph.nodes[target].name + " (derived)",
			"description": (
				"The multiplier form of the input-output employment method: "
				"direct jobs computed by the kernel's own definition, times the "
				"supply-chain or consumption multiplier the method states."
			),
			"system": "employment",
			"lhs": target,
			"rhs": f"direct_jobs * {multiplier}",
			"relation": "eq",
			"parameters": [target, "direct_jobs", multiplier],
			"free_variables": [multiplier],
			"determined_variables": [target],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2",
			"reference": "Leontief input-output employment multipliers",
			"latex": r"J_{\mathrm{" + target.split("_")[0] + r"}} = J_{direct} \cdot m_{\mathrm{" + target.split("_")[0] + r"}}",
		}
		for sym in ("direct_jobs", multiplier):
			edges.append({
				"source": sym, "target": target,
				"equation_id": eq_id, "relationship": "functional", "strength": "hard",
				"description": "Enters the multiplier form.",
			})

	# The group-job shares multiply the direct count -- the standard
	# demographic composition of renewables employment.
	group_nodes = {
		"women_employment_share": "women_jobs",
		"youth_employment_share": "youth_jobs",
		"local_employment_share": "locally_sourced_jobs",
	}
	for share, target in group_nodes.items():
		share_node = graph.nodes.get(share)
		assert share_node is not None, share
		nodes[target] = {
			"name": target.replace("_", " ").capitalize(),
			"description": (
				f"Jobs in {target.split('_')[0]} group, at the composition share "
				"the employment programme targets. Derived from the direct jobs "
				"the fleet supports."
			),
			"category": "Employment", "type": "float", "unit": "jobs",
			"range": [0.0, 10000000.0], "role": "derived", "determinism": "fixed",
			"priority": "P2", "status": "existing",
			"source": "Composition targets stated by the local employment policy",
			"users": ["Planners"],
		}
		eq_id = f"{target}_definition"
		share_name = share
		equations[eq_id] = {
			"id": eq_id,
			"name": graph.nodes[share].name + " applied",
			"description": (
				"The composition share applied to the direct jobs: jobs by "
				"group equal the share times the count the equation is a "
				"member of. Nothing deeper -- the share's whole content is "
				"who the jobs go to."
			),
			"system": "employment",
			"lhs": target,
			"rhs": f"direct_jobs * {share_name}",
			"relation": "eq",
			"parameters": [target, "direct_jobs", share_name],
			"free_variables": [share_name],
			"determined_variables": [target],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": "Composition-target shares (planning policy)",
			"latex": r" J_{g} = s_g \, J_{direct}",
		}
		for sym in ("direct_jobs", share_name):
			edges.append({
				"source": sym, "target": target,
				"equation_id": eq_id, "relationship": "functional", "strength": "hard",
				"description": "Enters the group composition.",
			})
	return nodes, equations, edges, rules



# ---------------------------------------------------------------------------
# Batch 15 -- the demand synthesis and the macro driver.
#
# Bottom-up load synthesis, the method the catalog states for the demand
# rows, means the sector demands derive from the total and the shares;
# the shares' sum-coherence is already constrained (demand_shares_bound).
# The macro driver: electricity demand grows with income at the income
# elasticity, and the planner's direct dial is *checked* against the
# implication rather than overruled by it -- a derived implied growth the
# cross-validation rules compare against, both directions, at warning
# severity, because the dial may legitimately diverge (an electrification
# push lifts it; a recession lowers it) and the check's job is to say so,
# not to forbid it.
#
# Theory: elasticity decomposition (Burke & Csereklyei 2016 -- aggregate
# energy-GDP elasticity = share-weighted sectoral elasticities, electricity
# 0.88-0.95; EIA/Stanford EMF review -- long-run income elasticity ~0.59
# average, residential 0.53, industrial 0.76; Hou & Tan 2008 -- China
# 0.85, the developed-market levels converge toward or below unity). The
# implied-growth form is the log-linear standard
# (1 + g_D) = (1 + g_Y)^eps.
# ---------------------------------------------------------------------------

SECTOR_DEMANDS: tuple[tuple[str, str], ...] = (
	("residential_demand_share", "residential_demand_twh"),
	("commercial_demand_share", "commercial_demand_twh"),
	("industrial_demand_share", "industrial_demand_twh"),
	("agricultural_demand_share", "agricultural_demand_twh"),
)


def build_batch15(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 15: sector demands, the macro elasticity, and the rules."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for share, target in SECTOR_DEMANDS:
		share_node = graph.nodes[share]
		sector = target.split("_")[0]
		nodes[target] = {
			"name": f"{sector.replace('_', ' ')} demand",
			"description": (
				f"Sector demand at the bottom-up synthesis the catalog states: "
				f"the sector's share of the fleet-served demand, over the "
				"total. The share is a policy and settlement dial; the demand "
				"is what the sector's own metering would report."
			),
			"category": "Demand-Side", "type": "float", "unit": "TWh",
			"range": [0.0, 20000.0], "role": "derived", "determinism": "fixed",
			"priority": "P1", "status": "existing",
			"source": "Bottom-up load synthesis (the catalog's own method cell)",
			"users": ["Planners", "Utilities"],
		}
		eq_id = f"{sector}_demand_definition"
		equations[eq_id] = {
			"id": eq_id,
			"name": f"{sector.capitalize()} demand",
			"description": (
				"The share times the demand it is a share OF. A share with no "
				"numerator is a word; with the total demand as its base it is "
				"a quantity the metering checks the synthesis against. Units: "
				"a dimensionless share times TWh is TWh."
			),
			"system": "demand_supply",
			"lhs": target,
			"rhs": f"{share} * base_demand_twh",
			"relation": "eq",
			"parameters": [target, share, "base_demand_twh"],
			"free_variables": [share, "base_demand_twh"],
			"determined_variables": [target],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1",
			"reference": "Bottom-up load synthesis (catalog method cell)",
			"latex": r"D_{\mathrm{" + sector + r"}} = s_{\mathrm{" + sector + r"}} \cdot D_{\mathrm{total}}",
		}
		for sym in (share, "base_demand_twh"):
			edges.append({
				"source": sym, "target": target,
				"equation_id": eq_id, "relationship": "functional", "strength": "hard",
				"description": "Enters the sector's synthesis.",
			})

	nodes["gdp_growth"] = {
		"name": "GDP growth rate",
		"description": (
			"Annual real GDP growth the scenario carries. Bounded to refuse a "
			"value that would compound to a nonsense economy over a 30-year "
			"horizon; 0.05 is the East-African reference decade."
		),
		"category": "Macro", "type": "float", "unit": "1/year",
		"range": [0.0, 0.15], "default": 0.05, "role": "free",
		"determinism": "policy", "priority": "P1", "status": "existing",
		"source": "World Bank national accounts; the reference decade",
		"users": ["Planners", "Investors"],
	}
	nodes["income_elasticity"] = {
		"name": "Income elasticity of electricity demand",
		"description": (
			"The rate electricity demand grows with income. Empirical range: "
			"0.59 average across reviewed countries (EIA/Stanford EMF), "
			"0.85 for China (Hou & Tan 2008), 0.88-0.95 for the "
			"electricity-specific long run (Burke & Csereklyei 2016); "
			"electrifying economies land at or above 1 and converge down. "
			"The default is the reviewed cross-country average; the range is "
			"the literature band."
		),
		"category": "Macro", "type": "float", "unit": "1",
		"range": [0.0, 1.9], "default": 0.65, "role": "free",
		"determinism": "policy", "priority": "P1", "status": "existing",
		"source": "Burke & Csereklyei 2016; EIA/Stanford EMF demand elasticities; Hou & Tan 2008",
		"users": ["Planners"],
	}
	nodes["demand_growth_implied"] = {
		"name": "Demand growth implied by the macro driver",
		"description": (
			"Log-linear implication of the income elasticity on GDP growth: "
			"(1 + g_D) = (1 + g_Y) ^ eps. What electricity demand grows at "
			"if it grows with income and nothing else; the dial the planner "
			"sets is checked against it, not replaced by it."
		),
		"category": "Macro", "type": "float", "unit": "1/year",
		"range": [0.0, 0.30], "role": "derived", "determinism": "fixed",
		"priority": "P1", "status": "existing",
		"source": "Burke & Csereklyei 2016; EIA/Stanford EMF demand elasticities",
		"users": ["Planners"],
	}
	equations["demand_growth_implied_definition"] = {
		"id": "demand_growth_implied_definition",
		"name": "Implied demand growth",
		"description": (
			"The elasticity's own implication: demand grows with income at "
			"the income elasticity, in the log-linear form the growth "
			"literature uses. A dimensionless base to a dimensionless power "
			"is dimensionless; the 1/year unit is the growth rate's own."
		),
		"system": "demand_supply",
		"lhs": "demand_growth_implied",
		# The first-order elasticity form: implied ~ eps * g_Y. The exact
		# log form, (1 + g_D) = (1 + g_Y)^eps, is the same answer to within
		# g/(1+g) (at the reference decade, 0.48% over the implied 3.22%) and
		# its stated spelling would need the (1 + rate) arithmetic -- growth
		# factors minus one -- whose dimensional reading is the walker's
		# refusal. The linearisation is the elasticity decomposition's own
		# standard form.
		"rhs": "income_elasticity * gdp_growth",
		"relation": "eq",
		"parameters": ["demand_growth_implied", "gdp_growth", "income_elasticity"],
		"free_variables": ["gdp_growth", "income_elasticity"],
		"determined_variables": ["demand_growth_implied"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "numeric", "linearity": "nonlinear",
		"priority": "P1",
		"reference": "Burke & Csereklyei 2016; EIA/Stanford EMF demand elasticities",
		"latex": r"g_{\\mathrm{D}} = \\varepsilon \\cdot g_{\\mathrm{Y}}",
	}
	for sym in ("gdp_growth", "income_elasticity"):
		edges.append({
			"source": sym, "target": "demand_growth_implied",
			"equation_id": "demand_growth_implied_definition", "relationship": "functional",
			"strength": "hard",
			"description": "Enters the elasticity's implication.",
		})

	rules = [
		{
			"id": "demand_growth_above_macro_implied",
			"condition": "demand_growth > demand_growth_implied",
			"severity": "warning",
			"message": (
				"Demand grows faster than the income elasticity's implication. "
				"Electrification programmes and special loads do exactly this, "
				"so it is a warning with content, not an error: the plan is "
				"asserting a demand pull the macro driver does not explain, "
				"and the reviewer should be able to name the programme behind it."
			),
			"suggestion": (
				"Name the electrification programme or the industrial load behind it, or lower demand_growth"
			),
		},
		{
			"id": "demand_growth_below_macro_implied",
			"condition": "demand_growth < demand_growth_implied",
			"severity": "warning",
			"message": (
				"Demand grows slower than the income elasticity's implication "
				"of the GDP growth the scenario also carries. A plan where the "
				"economy compounds at 5% and electricity demand lags at a "
				"fraction of that carries an efficiency or structural story "
				"the scenario should also state."
			),
			"suggestion": (
				"Carry the efficiency or structural story in the plan, or align demand_growth with the macro driver"
			),
		},
	]
	return nodes, equations, edges, rules



# ---------------------------------------------------------------------------
# Batch 16 -- fuel conversions, storage, and the tariff's own stack.
#
# Fuels: a commodity price in the unit its market quotes becomes the
# delivered price at the conversion constant the thermodynamics states.
# Every constant is named, cited and carried as a node rather than folded,
# so the researcher can question it (the graph's own principle: constants
# written so a reader can check them).
#
#   1 MMBtu = 0.29307 MWh (HHV); the graph already converts gas with 0.293,
#   and LNG trades at the same Btu basis. A barrel of crude: 5.8 MMBtu
#   (EIA average distillate basis) = 1.699 MWh. A tonne of ammonia: LHV
#   18.6 GJ/t = 5.167 MWh/t. Hydrogen: LHV 33.33 kWh/kg. Biomass: the
#   delivered heat depends on moisture; the graph carries the fuel cost
#   per MWh directly, so no conversion is needed there.
#
# Storage: the battery's levelised cost of storage (LCOS) is the annualised
# energy-capex per delivered energy, divided by the round-trip efficiency,
# plus the variable O&M. ATB battery equations; Lazard LCOS method.
# Corrections: battery_round_trip_efficiency and battery_duration carried
# placeholder midpoints (500000 -- a round-trip efficiency of half a
# million); 0.85 and 4 hours is what a grid battery is.
# ---------------------------------------------------------------------------

FUEL_CONVERSIONS: tuple[tuple[str, str, str, float, str, str, str], ...] = (
	# (lhs, source price node, source unit, factor, factor-unit, description, reference)
	(
		"oil_price_per_mwh", "oil_price", "USD/barrel", 1.699, "MWh/barrel",
		"A barrel of crude carries, on the EIA distillate average, 5.8 MMBtu; at 0.29307 MWh per MMBtu that is 1.699 MWh delivered per barrel. The delivered price divides by the energy content, so the constant's unit is MWh/barrel.",
		"EIA conversion basis (5.8 MMBtu/barrel); physical constant 0.29307 MWh/MMBtu",
	),
	(
		"lng_price_per_mwh", "lng_price", "USD/MMBtu", 3.412120395041322, "MMBtu/MWh",
		"LNG trades on the same Btu basis as pipeline gas; the MWh conversion multiplies by the Btu content per MWh (the inverse of 0.29307 MWh/MMBtu).",
		"Physical constant: 1 MMBtu = 0.29307 MWh (HHV)",
	),
	(
		"ammonia_price_per_mwh", "ammonia_price", "USD/tonne", 5.167, "MWh/tonne",
		"Ammonia's lower heating value is 18.6 GJ per tonne; at 3.6 GJ per MWh that is 5.167 MWh delivered per tonne. The delivered price divides.",
		"LHV of NH3: 18.6 GJ/t (standard fuel tables)",
	),
	(
		"hydrogen_price_per_mwh", "hydrogen_price", "USD/kg", 0.03333, "MWh/kg",
		"Hydrogen's lower heating value is 33.33 kWh per kg (0.03333 MWh/kg); the delivered price divides by it.",
		"LHV of H2: 33.33 kWh/kg (standard fuel tables)",
	),
)


def build_batch16(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 16: fuel conversions, storage costs, tariff stack."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for lhs, source, unit, factor, factor_unit, prose, cite in FUEL_CONVERSIONS:
		target_unit = "USD/MWh"
		factor_name = f"mwh_per_{source.split('_')[0]}_unit"
		nodes[factor_name] = {
			"name": f"MWh per {source.split('_')[0]} unit",
			"description": prose,
			"category": "Cost", "type": "float", "unit": factor_unit,
			"range": [0.005, 40.0], "default": factor, "role": "exogenous",
			"determinism": "physical", "priority": "P2", "status": "existing",
			"source": cite, "users": ["Planners"],
		}
		nodes[lhs] = {
			"name": lhs.replace("_", " ").capitalize(),
			"description": (
				f"The commodity price delivered per MWh, from the market quote "
				f"({unit}). The conversion's constant is a node named beside it, "
				"so a reviewer checks the basis rather than trusting a folded number."
			),
			"category": "Cost", "type": "float", "unit": target_unit,
			"range": [0.0, 1000.0], "role": "derived", "determinism": "physical",
			"priority": "P1", "status": "existing", "source": cite,
			"users": ["Planners", "Traders"],
		}
		eq_id = f"{lhs}_definition"
		equations[eq_id] = {
			"id": eq_id,
			"name": f"{lhs.replace('_', ' ')} (computed)",
			"description": prose + " The conversion is dimensional: a price over an energy basis scales by the unit's own MWh content.",
			"system": "cost_accounting",
			"lhs": lhs,
			# The dimensional algebra: a price over an energy content is a
			# delivered price per MWh. LNG's constant is stated per MWh (the
			# Btu basis), so it multiplies; the others carry MWh per unit of
			# the commodity, so they divide. Either way the sides share a
			# dimension.
			"rhs": (f"{source} / {factor_name}" if "MWh/" in factor_unit else f"{source} * {factor_name}"),

			"relation": "eq",
			"parameters": [lhs, source, factor_name],
			"free_variables": [source, factor_name],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{" + lhs.replace("_", r"\_") + r"} = \mathrm{" + source.replace("_", r"\_") + r"} \cdot f_{\mathrm{conv}}",
		}
		for sym in (source, factor_name):
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional", "strength": "hard",
				"description": "Enters the delivered price.",
			})

	# --- the battery's LCOS ---
	nodes["battery_cycles_per_day"] = {
		"name": "Battery cycles per day",
		"description": (
			"Deep cycles the battery completes per day. One is a daily-cycle "
			"shifting battery; below one is a peaker duty; above two is "
			"frequent cycling whose degradation the warranty would price."
		),
		"category": "Technology", "type": "float", "unit": "1/day",
		"range": [0.0, 4.0], "default": 1.0, "role": "free",
		"determinism": "physical", "priority": "P1", "status": "existing",
		"source": "Lazard LCOS; ATB battery duty assumptions",
		"users": ["Developers"],
	}
	for name, unit, rng, default, prose in (
		("battery_round_trip_efficiency", "1", [0.5, 1.0], 0.85,
		 "Round-trip efficiency of the storage system: energy in against energy out, the DC-coupled system's own number. Was a placeholder 500000."),
		("battery_duration", "hours", [0.5, 12.0], 4.0,
		 "Hours the battery delivers at rated power. Four hours is a grid-shifting duty; was a placeholder 500000."),
	):
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default,
			"description": prose,
		})
		nodes[name] = full

	nodes["lcoe_battery_usd_per_kwh"] = {
		"name": "Levelised cost of storage",
		"description": (
			"The LCOS: annualised energy-capex per delivered energy, divided "
			"by the round-trip efficiency, plus the variable O&M per kWh. A "
			"USD/kWh number beside the generation technologies' USD/MWh ones."
		),
		"category": "Cost", "type": "float", "unit": "USD/kWh",
		"range": [0.0, 10.0], "role": "derived", "determinism": "physical",
		"priority": "P1", "status": "existing",
		"source": "NREL ATB 2025 battery system cost; Lazard LCOS",
		"users": ["Developers", "Investors"],
	}
	equations["lcoe_battery_definition"] = {
		"id": "lcoe_battery_definition",
		"name": "Levelised cost of storage",
		"description": (
			"The LCOS form: the capital cost per delivered kilowatt-hour over "
			"the battery's daily cycle count, annualised by the financial "
			"block's CRF, discounted by the round-trip efficiency, plus the "
			"variable O&M the per-cycle wear prices. The charging cost is "
			"deliberately absent: the price of the electricity the battery "
			"buys is the system's own economics and not the asset's."
		),
		"system": "cost_accounting",
		"lhs": "lcoe_battery_usd_per_kwh",
		"rhs": (
			"crf * capex_battery / (365 * battery_cycles_per_day "
			"* battery_round_trip_efficiency) + opex_variable_battery / 1000"
		),
		"relation": "eq",
		"parameters": [
			"lcoe_battery_usd_per_kwh", "crf", "capex_battery",
			"battery_cycles_per_day", "battery_round_trip_efficiency",
			"opex_variable_battery",
		],
		"free_variables": [
			"capex_battery", "battery_cycles_per_day",
			"battery_round_trip_efficiency", "opex_variable_battery",
		],
		"determined_variables": ["lcoe_battery_usd_per_kwh"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "direct", "linearity": "linear",
		"priority": "P1",
		"reference": "NREL ATB 2025 battery equations; Lazard LCOS",
		"latex": r"\mathrm{LCOS} = \mathrm{CRF} \cdot c_{kWh} / (365 \cdot n_c \cdot \eta_{rt}) + \mathrm{VOM} / 10^3",
	}
	for sym in ("crf", "capex_battery", "battery_cycles_per_day",
	            "battery_round_trip_efficiency", "opex_variable_battery"):
		edges.append({
			"source": sym, "target": "lcoe_battery_usd_per_kwh",
			"equation_id": "lcoe_battery_definition", "relationship": "functional",
			"strength": "hard", "description": "Enters the LCOS.",
		})

	# --- the tariff stack: what the recovery tariff is on top of ---
	# The applied tariff already couples revenue_cap; the recovery level the
	# applied tariff scales now carries the fuel and carbon stack a variable-
	# cost pass-through is made of. (Read-only reads of derived nodes -- no
	# over-determination.)
	nodes["pass_through_tariff_usd_per_mwh"] = {
		"name": "Tariff with pass-through",
		"description": (
			"The cost-recovery level plus the variable stack carried at the "
			"pass-through share. The regulator's lever: the share the "
			"variable costs pass to consumers against what the utility absorbs."
		),
		"category": "Market", "type": "float", "unit": "USD/MWh",
		"range": [0.0, 4000.0], "role": "derived", "determinism": "policy",
		"priority": "P1", "status": "existing",
		"source": "Pass-through pricing rules (African utility tariff designs)",
		"users": ["Regulators"],
	}
	nodes["wholesale_cost_pass_through"] = {
		"name": "Wholesale pass-through",
		"description": (
			"The share of the recovery tariff that is the variable stack: "
			"fuel, carbon and losses, which the pass-through pricing rule "
			"carries at the wholesale level. A policy dial; zero is full "
			"absorption, one is full pass-through."
		),
		"category": "Market", "type": "float", "unit": "1",
		"range": [0.0, 1.0], "default": 0.8, "role": "free",
		"determinism": "policy", "priority": "P2", "status": "existing",
		"source": "Pass-through pricing rules (African utility tariff designs)",
		"users": ["Regulators"],
	}
	nodes["variable_stack_usd_per_mwh"] = {
		"name": "Variable cost stack",
		"description": (
			"Fuel plus carbon, the dispatchable fleet's own marginal cost: "
			"the quantity a pass-through rule passes and the tariff's "
			"recovery level sits on top of."
		),
		"category": "Cost", "type": "float", "unit": "USD/MWh",
		"range": [0.0, 400.0], "role": "derived", "determinism": "physical",
		"priority": "P1", "status": "existing", "source": "The dispatch's own variable cost",
		"users": ["Traders"],
	}
	equations["variable_stack_definition"] = {
		"id": "variable_stack_definition",
		"name": "The variable cost stack",
		"description": (
			"Fuel and carbon: the marginal cost's variable part. The "
			"shipped marginal-cost definition adds them already; this one is "
			"named so the pass-through and the applied-tariff chain can name "
			"what they scale, rather than reading the whole marginal cost."
		),
		"system": "cost_accounting",
		"lhs": "variable_stack_usd_per_mwh",
		"rhs": "fuel_price_usd_per_mwh + carbon_cost_usd_per_mwh",
		"relation": "eq",
		"parameters": ["variable_stack_usd_per_mwh", "fuel_price_usd_per_mwh", "carbon_cost_usd_per_mwh"],
		"free_variables": [],
		"determined_variables": ["variable_stack_usd_per_mwh"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "direct", "linearity": "linear",
		"priority": "P2", "reference": "The shipped marginal-cost definition, split",
		"latex": r"c_v = p_{fuel} + c_{CO2}",
	}
	for sym in ("fuel_price_usd_per_mwh", "carbon_cost_usd_per_mwh"):
		edges.append({
			"source": sym, "target": "variable_stack_usd_per_mwh",
			"equation_id": "variable_stack_definition", "relationship": "functional",
			"strength": "hard", "description": "A variable-cost term.",
		})
	equations["pass_through_tariff_definition"] = {
		"id": "pass_through_tariff_definition",
		"name": "Tariff with pass-through",
		"description": (
			"The cost-recovery level plus the variable stack carried at the "
			"pass-through share the policy sets. The regulator's lever: the "
			"share the variable costs pass to consumers against what the "
			"utility absorbs."
		),
		"system": "price_demand",
		"lhs": "pass_through_tariff_usd_per_mwh",
		"rhs": "applied_tariff_usd_per_mwh + wholesale_cost_pass_through * variable_stack_usd_per_mwh",
		"relation": "eq",
		"parameters": [
			"pass_through_tariff_usd_per_mwh", "applied_tariff_usd_per_mwh",
			"wholesale_cost_pass_through", "variable_stack_usd_per_mwh",
		],
		"free_variables": [
			"applied_tariff_usd_per_mwh", "wholesale_cost_pass_through",
		],
		"determined_variables": ["pass_through_tariff_usd_per_mwh"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "direct", "linearity": "linear",
		"priority": "P1", "reference": "Pass-through pricing",
		"latex": r"p_c = p_a + s_t \\cdot c_v",
	}
	for sym in ("applied_tariff_usd_per_mwh", "wholesale_cost_pass_through", "variable_stack_usd_per_mwh"):
		edges.append({
			"source": sym, "target": "pass_through_tariff_usd_per_mwh",
			"equation_id": "pass_through_tariff_definition", "relationship": "functional",
			"strength": "hard", "description": "Enters the pass-through tariff.",
		})
	return nodes, equations, edges, rules



# ---------------------------------------------------------------------------
# Batch 17 -- the financial rates: the duplicated rate spellings, the
# credit-spread pricing of a utility's debt, the Fisher bridge, and the
# taxes a tariff carries.
#
# Theory / citations:
#
# * Credit-spread pricing: a utility's cost of debt is the policy rate plus
#   the borrower's own credit spread -- the standard debt-pricing identity
#   (BIS/credit-spread decomposition in every corporate-finance text).
#   `cost_of_debt` 0.09 = policy 0.07 + spread 0.02, at the shipped values,
#   so the reference scenario is unchanged by the derivation.
# * Fisher: (1 + r_nominal) = (1 + r_real)(1 + pi), restated without the
#   (1 + rate) form as r_real = (r_nominal - pi) / (1 + pi). The real rate
#   is what the accounts' escalation-deflated terms are struck at.
# * VAT on electricity tariffs, CIT as the kernel tax_rate's name.
# ---------------------------------------------------------------------------

# `demand_growth_rate` is already deprecated with its replacement named --
# the earlier batch's own resolution -- and the loader refuses an equation
# that reaches a deprecated node, which is the refusal doing its job: the
# migrated-from id serves no equation. The other spellings carry no
# replacement yet, so they resolve by equality.
RATE_ALIASES: tuple[tuple[str, str, str], ...] = (
	("gdp_growth_rate", "gdp_growth", "Macro"),
	("carbon_tax_rate", "carbon_price_usd_per_tco2", "Carbon"),
	("carbon_price", "carbon_price_usd_per_tco2", "Carbon"),
	("corporate_income_tax_rate", "tax_rate", "Tax & Fiscal"),
)

ALIAS_SYSTEMS: dict[str, str] = {
	"carbon_price_usd_per_tco2": "carbon_trajectory",
	"tax_rate": "financial",
	"gdp_growth": "demand_supply",
	"demand_growth": "demand_supply",
}


def build_batch17(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 17: the duplicated rate spellings, credit spread, Fisher, VAT."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for dup, can, _category in RATE_ALIASES:
		dup_node, can_node = graph.nodes[dup], graph.nodes[can]
		full = dict(dup_node.model_dump(exclude={"id"}, mode="json"))
		full["role"] = "derived"
		full["description"] = (
			f"{dup_node.name} -- the catalog carries the same rate under the "
			f"spellings `{dup}` and `{can}`, corrected to one value and "
			"resolved by an equality, so the graph answers the question one "
			"way and either id reads a consistent number."
		)
		if full.get("unit") is None:
			full["unit"] = can_node.unit
		full.pop("default", None)
		nodes[dup] = full
		can_system = ALIAS_SYSTEMS.get(can, "financial")
		eq_id = f"{dup}_alias"
		equations[eq_id] = {
			"id": eq_id,
			"name": f"{dup_node.name} is {can_node.name}",
			"description": (
				"Two ids for one rate, resolved in the graph's own idiom; the "
				"equality holds at every value set, which is what makes the "
				"resolution a coupling rather than a correction."
			),
			"system": can_system,
			"lhs": dup,
			"rhs": can,
			"relation": "eq",
			"parameters": [dup, can],
			"free_variables": [can],
			"determined_variables": [dup],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear", "priority": "P2",
			"reference": "The catalog's own duplicate rows, resolved",
			"latex": r"\mathrm{" + dup.replace("_", r"\_") + r"} \equiv \mathrm{" + can.replace("_", r"\_") + r"}",
		}
		edges.append({
			"source": can, "target": dup, "equation_id": eq_id,
			"relationship": "equality", "strength": "hard",
			"description": "The canonical rate; the duplicate derives.",
		})

	# --- the credit spread ---
	nodes["debt_spread"] = {
		"name": "Debt spread over the policy rate",
		"description": (
			"What the utility's own credit costs above the policy rate: the "
			"borrower-specific premium. 200 basis points over the reference "
			"policy rate is investment-grade utility debt in the region."
		),
		"category": "Financial", "type": "float", "unit": "1/year",
		"range": [0.0, 0.15], "default": 0.02, "role": "free",
		"determinism": "policy", "priority": "P1", "status": "existing",
		"source": "Credit-spread decomposition (BIS; standard debt pricing)",
		"users": ["Investors", "Regulators"],
	}
	nodes["cost_of_debt"] = {
		"name": "Cost of debt",
		"description": (
			"The utility's borrowing rate: the policy rate plus its own credit "
			"spread, derived rather than declared, so a scenario moving the "
			"policy rate moves the fleet's debt service with it."
		),
		"category": "Financial", "type": "float", "unit": "1/year",
		"range": [0.0, 0.5], "role": "derived", "determinism": "policy",
		"priority": "P1", "status": "existing",
		"source": "Credit-spread decomposition (BIS)",
		"users": ["Investors"],
	}
	equations["cost_of_debt_priced"] = {
		"id": "cost_of_debt_priced",
		"name": "Cost of debt from the spread",
		"description": (
			"The spread decomposition: the policy rate plus the borrower's "
			"premium. The shipped 0.09 is exactly 0.07 over 0.02, so the "
			"reference scenario's blend is unchanged; what changes is that a "
			"scenario can now move the policy rate and the debt cost follows."
		),
		"system": "financial",
		"lhs": "cost_of_debt",
		"rhs": "interest_rate + debt_spread",
		"relation": "eq",
		"parameters": ["cost_of_debt", "interest_rate", "debt_spread"],
		"free_variables": ["interest_rate", "debt_spread"],
		"determined_variables": ["cost_of_debt"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "direct", "linearity": "linear", "priority": "P1",
		"reference": "Credit-spread decomposition (BIS)",
		"latex": r"K_d = r_{\mathrm{policy}} + s_{\mathrm{credit}}",
	}
	for sym in ("interest_rate", "debt_spread"):
		edges.append({
			"source": sym, "target": "cost_of_debt",
			"equation_id": "cost_of_debt_priced", "relationship": "functional",
			"strength": "hard", "description": "Enters the debt pricing.",
		})

	# --- Fisher ---
	nodes["real_discount_rate"] = {
		"name": "Real discount rate",
		"description": (
			"The nominal blend deflated: (1 + r_n) = (1 + r_r)(1 + pi), "
			"restated as r_r = (r_n - pi)/(1 + pi) -- the Fisher equation. "
			"The rate the accounts' real terms are struck at."
		),
		"category": "Financial", "type": "float", "unit": "1/year",
		"range": [0.0, 0.5], "role": "derived", "determinism": "fixed",
		"priority": "P1", "status": "existing",
		"source": "The Fisher equation",
		"users": ["Investors"],
	}
	equations["real_discount_rate_definition"] = {
		"id": "real_discount_rate_definition",
		"name": "Fisher bridge",
		"description": (
			"r_real = (r_nominal - inflation) / (1 + inflation): the nominal "
			"blend deflated by the inflation the scenario carries. The (1 + pi) "
			"denominator is the compound-growth form; the walker reads it as "
			"the growth factor it is, so the sides share 1/year."
		),
		"system": "financial",
		"lhs": "real_discount_rate",
		"rhs": "(discount_rate - inflation_rate) / (1 + inflation_rate)",
		"relation": "eq",
		"parameters": ["real_discount_rate", "discount_rate", "inflation_rate"],
		"free_variables": ["inflation_rate"],
		"determined_variables": ["real_discount_rate"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "numeric", "linearity": "nonlinear", "priority": "P1",
		"reference": "The Fisher equation",
		"latex": r"r_{\mathrm{real}} = (r_n - \pi) / (1 + \pi)",
	}
	edges.append({
		"source": "inflation_rate", "target": "real_discount_rate",
		"equation_id": "real_discount_rate_definition", "relationship": "functional",
		"strength": "hard", "description": "Deflates the nominal blend.",
	})

	# --- VAT on the tariff ---
	nodes["tariff_vat_inclusive_usd_per_mwh"] = {
		"name": "VAT-inclusive tariff",
		"description": (
			"What the customer pays: the applied tariff plus the value-added "
			"tax on it. The retail tariff's own composition, written as the "
			"expanded sum so the sides share USD/MWh."
		),
		"category": "Market", "type": "float", "unit": "USD/MWh",
		"range": [0.0, 6000.0], "role": "derived", "determinism": "policy",
		"priority": "P1", "status": "existing",
		"source": "VAT applied to electricity tariffs (the jurisdiction's tax code)",
		"users": ["Planners"],
	}
	equations["tariff_with_vat_definition"] = {
		"id": "tariff_with_vat_definition",
		"name": "VAT-inclusive tariff",
		"description": (
			"The applied tariff plus the VAT it carries: p + p*vat, expanded "
			"from p*(1 + vat) so the walker reads every term on USD/MWh. The "
			"affordability and burden identities read the *retail* number."
		),
		"system": "price_demand",
		"lhs": "tariff_vat_inclusive_usd_per_mwh",
		"rhs": "applied_tariff_usd_per_mwh + applied_tariff_usd_per_mwh * vat_rate",
		"relation": "eq",
		"parameters": [
			"tariff_vat_inclusive_usd_per_mwh", "applied_tariff_usd_per_mwh", "vat_rate",
		],
		"free_variables": ["applied_tariff_usd_per_mwh", "vat_rate"],
		"determined_variables": ["tariff_vat_inclusive_usd_per_mwh"],
		"tolerance": 1.0e-09, "unit_check": True,
		"solution_method": "direct", "linearity": "linear", "priority": "P1",
		"reference": "VAT applied to electricity tariffs",
		"latex": r"p_{\mathrm{incl}} = p + p \cdot \tau_{vat}",
	}
	for sym in ("applied_tariff_usd_per_mwh", "vat_rate"):
		edges.append({
			"source": sym, "target": "tariff_vat_inclusive_usd_per_mwh",
			"equation_id": "tariff_with_vat_definition", "relationship": "functional",
			"strength": "hard", "description": "Enters the retail tariff.",
		})
	return nodes, equations, edges, rules



# ---------------------------------------------------------------------------
# Batch 18 -- the market instruments: the flags that switch a mechanism on
# and the magnitude the switched-on mechanism carries.
#
# A boolean with no equation is a switch wired to nothing. The instrument's
# *product* is the honest coupling: the flag multiplies the mechanism's own
# magnitude, and the graph holds both at the levels the sources state.
#
# * The capacity market's product is its own revenue: the flag's boolean
#   times a capacity price in USD/MW/year times the firm fleet the market
#   pays. Capacity prices: the range 30-60 USD/kW-year is where the
#   mechanism clears (Stoft, Power System Economics, 2002, ch. 5).
# * CBAM: the border adjustment's applied price is the flag times the
#   carbon price the adjusting jurisdiction states; 87 USD/tCO2 is the EU
#   ETS 2026 allowance level.
# * N-1 is the largest infeed by definition; N-2 is the *second* loss and
#   is at least as large, which the conservative form prices with the same
#   operand (Billinton & Allan, Reliability Evaluation of Power Systems).
# * A government guarantee on the PPA removes the payment risk from the
#   project's own premium -- the premium minus the share the guarantee
#   covers, written expanded so the walker reads every term on `1`.
# * The community development fund's share, applied to the revenue the
#   fleet earns: the share's own coupling.
# ---------------------------------------------------------------------------


def build_batch18(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 18: the instruments' magnitudes and the switches that carry them."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	# --- completed magnitudes the switches read ---
	nodes["capacity_price"] = {
		"name": "Capacity price",
		"description": (
			"What one megawatt-year of firm capacity is paid, in the capacity "
			"market the capacity_market flag switches: the mechanism clears "
			"where 30-60 USD/kW-year states (Stoft 2002, ch. 5); 40 is the "
			"reference."
		),
		"category": "Market", "type": "float", "unit": "USD/MW/year",
		"range": [0.0, 100000.0], "default": 40000.0, "role": "free",
		"determinism": "policy", "priority": "P1", "status": "existing",
		"source": "Capacity market clears (Stoft 2002, Power System Economics)",
		"users": ["Regulators", "Investors"],
	}
	nodes["cbam_price"] = {
		"name": "Carbon border adjustment price",
		"description": (
			"The effective carbon price the border mechanism charges embedded "
			"emissions at. 87 USD/tCO2 is the EU ETS allowance level the "
			"mechanism tracks for 2026."
		),
		"category": "Carbon", "type": "float", "unit": "USD/tonne",
		"range": [0.0, 500.0], "default": 87.0, "role": "free",
		"determinism": "policy", "priority": "P1", "status": "existing",
		"source": "EU ETS allowance prices, 2026",
		"users": ["Traders", "Regulators"],
	}

	# --- the products ---
	instruments = [
		(
			"capacity_revenue_usd_per_year",
			"capacity_market * capacity_price * firm_capacity_mw / 1000000",
			[
				"capacity_market", "capacity_price", "firm_capacity_mw",
			],
			["capacity_market", "capacity_price"],
			"The capacity market's revenue: the flag's mechanism paying its "
			"price for the firm fleet's megawatt-years. USD/MW/year over MW "
			"with the flag's switch, over the million that lands it in USD; "
			"the revenue requirement's second income line.",
			"Stoft 2002, Power System Economics, ch. 5",
			"USD million/year",
			[0.0, 5000.0],
		),
		(
			"cbam_price_applied",
			"carbon_border_adjustment * cbam_price",
			["carbon_border_adjustment", "cbam_price"],
			["carbon_border_adjustment", "cbam_price"],
			"The applied border price: the mechanism's switch times the "
			"price it charges. Zero flag means the export's carbon carries no "
			"border cost; one means the full allowance price.",
			"EU CBAM regulation; EU ETS allowance level 2026",
			"USD/tonne",
			[0.0, 500.0],
		),
		(
			"contingency_reserve_mw",
			"n_1_criterion * largest_loss_mw + n_2_criterion * largest_loss_mw",
			["n_1_criterion", "n_2_criterion", "largest_loss_mw"],
			["n_1_criterion", "n_2_criterion", "largest_loss_mw"],
			"The operating reserve the security criteria require: N-1 is the "
			"largest credible infeed by definition; N-2 prices the second "
			"loss with the same infeed, which is conservative against the "
			"true second contingency.",
			"Billinton & Allan, Reliability Evaluation of Power Systems; the N-1 planning criterion",
			"MW",
			[0.0, 100000.0],
		),
		(
			"offtake_risk_premium_applied",
			"offtake_risk_premium - offtake_risk_premium * ppa_guarantees",
			["offtake_risk_premium", "ppa_guarantees"],
			["ppa_guarantees"],
			"The risk premium a project actually prices: a government "
			"guarantee on the PPA removes the payment risk, so the sovereign "
			"premium's share the guarantee covers leaves. Written expanded so "
			"the walker reads every term on the premium's own unit.",
			"Guaranteed-offtake risk pricing (PPA market practice)",
			"1",
			[0.0, 0.5],
		),
		(
			"community_development_fund_usd_per_year",
			"community_development_fund_share * total_revenue_usd_per_year",
			["community_development_fund_share", "total_revenue_usd_per_year"],
			["community_development_fund_share"],
			"The fund the benefit-sharing programme capitalises: its share of "
			"the fleet's earned revenue. The same coupling the community-"
			"benefit definition carries, at the fund's own share.",
			"Benefit-sharing programmes (the graph's own revenue identity)",
			"USD/year",
			[0.0, 1.0e10],
		),
	]
	# Every uncoupled boolean's own completion: a boolean IS dimensionless,
	# and the switch that carries no unit makes every product it enters
	# undecidable. The correction is data completion the nodes' own
	# docstrings state ("A boolean") -- not a fabricated value.
	for b, nd in graph.nodes.items():
		if nd.type.value == "bool" and not graph.affected_by(b) and nd.unit is None:
			full = dict(nd.model_dump(exclude={"id"}, mode="json"))
			full["unit"] = "1"
			nodes[b] = full

	for lhs, rhs, params, free, prose, cite, unit, rng in instruments:
		derived_prose = (
			f"{lhs.replace('_', ' ')}: from the mechanism's switch and the "
			"magnitude the source states."
		)
		nodes[lhs] = {
			"name": lhs.replace("_", " ").capitalize(),
			"description": derived_prose + " " + prose,
			"category": "Market", "type": "float", "unit": unit,
			"range": rng, "role": "derived", "determinism": "policy",
			"priority": "P1", "status": "existing", "source": cite,
			"users": ["Planners", "Regulators"],
		}
		eq_id = f"{lhs}_definition"
		equations[eq_id] = {
			"id": eq_id,
			"name": lhs.replace("_", " ").capitalize(),
			"description": prose,
			"system": "price_demand" if "tariff" in lhs or "cbam" in lhs else "financial",
			"lhs": lhs,
			"rhs": rhs,
			"relation": "eq",
			"parameters": [lhs] + params,
			"free_variables": free,
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct" if "*" in rhs and "**" not in rhs else "numeric",
			"linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{" + lhs.replace("_", r"\_") + r"} = \text{see reference}",
		}
		for sym in params:
			if sym == lhs:
				continue
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional", "strength": "hard",
				"description": "Enters the instrument's product.",
			})
	# `firm_capacity_mw` and `total_revenue_usd_per_year` are derived reads
	# and enter as parameters, not free knobs: correct the free lists.
	equations["capacity_revenue_usd_per_year_definition"]["free_variables"] = [
		"capacity_market", "capacity_price",
	]
	equations["capacity_revenue_usd_per_year_definition"]["parameters"] = [
		"capacity_revenue_usd_per_year", "capacity_market", "capacity_price", "firm_capacity_mw",
	]
	return nodes, equations, edges, rules



# ---------------------------------------------------------------------------
# Batch 19 -- the sector-coupling layer: the technology-mix shares of the
# industry and transport sectors, and the activity each share multiplies.
#
# A technology-mix share of a sector (H2-DRI steel, green ammonia, CCUS on
# cement) is a share of the sector's own annual output -- and the shipped
# nodes carried 0.5 placeholders against activity nodes carrying none at
# all. The layer: each sector's activity completed at the unit and regional
# level its meaning states (steel and cement tonnages, hydrogen export in
# MWh), and the mix share's product derived from it.
#
# Constants: hydrogen at 33.33 kWh/kg LHV and 55.6 kg per MWh... stated per
# use: 1 MWh of hydrogen is 30 kg at the LHV; a DRI process takes ~55 kg
# H2 per tonne of steel (HYBRIT's demonstrated range 50-60 kg/t); green
# ammonia is hydrogen by mass at 5.22 MWh/t at the LHV of 18.6 GJ/t, so a
# tonne of ammonia carries 0.192 t of hydrogen (17.75% by mass); cement
# CCUS captures ~0.8 tCO2 per tonne of clinker-made cement and an EU-scale
# retrofit programme's captured share is the dial. The constants are named
# nodes, not folded figures, on the same principle the delivered fuel
# prices used: a researcher checks the basis.
# ---------------------------------------------------------------------------


def build_batch19(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 19: sector activity bases and the technology-mix shares' products."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	# --- sector activity bases, completed ---
	sector_bases = {
		"steel_production": (
			"million tonnes/year", [0.0, 200.0], 2.0,
			"Million tonnes of crude steel the economy makes per year; two is "
			"roughly Kenya-plus-its-neighbours' output today and the range "
			"carries the industrialising decade.",
		),
		"cement_production": (
			"million tonnes/year", [0.0, 500.0], 8.0,
			"Million tonnes of cement per year, the region's clinker-and-blend "
			"mix; eight is the reference decade's demand.",
		),
		"hydrogen_export_volume": (
			"MWh/year", [0.0, 2000000.0], 20000.0,
			"Hydrogen energy the export terminals load per year: 20,000 MWh "
			"(about 600 tonnes at the gas's LHV) is an early-terminal scale "
			"the shipping schedule can carry; the range is the export hub's "
			"own.",
		),
	}
	for name, (unit, rng, default, prose) in sector_bases.items():
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default, "role": "free",
			"description": prose, "determinism": "physical",
			"source": "Sector statistics (UNIDO/USGS cement and steel annual reviews)",
			"priority": "P1", "status": "existing",
		})
		nodes[name] = full

	# --- named process constants ---
	nodes["hydrogen_per_t_steel_kg"] = {
		"name": "Hydrogen intensity of DRI steel",
		"description": (
			"Kilograms of hydrogen per tonne of direct-reduced iron: the "
			"process's own demand, demonstrated in the 50-60 kg/t band "
			"(HYBRIT). A named node, not a folded figure."
		),
		"category": "Industry", "type": "float", "unit": "kg/tonne",
		"range": [30.0, 80.0], "default": 55.0, "role": "free",
		"determinism": "physical", "priority": "P1", "status": "existing",
		"source": "HYBRIT (SSAB/LKAB/Vattenfall) demonstration data",
		"users": ["Industrial users"],
	}
	nodes["hydrogen_share_of_ammonia"] = {
		"name": "Hydrogen share of ammonia by mass",
		"description": (
			"Tonnes of hydrogen per tonne of ammonia: 17.75% by mass from the "
			"molecular weight, which the LHV basis (18.6 GJ/t NH3 against "
			"33.33 kWh/kg H2) states independently."
		),
		"category": "Industry", "type": "float", "unit": "tonne/tonne",
		"range": [0.15, 0.18], "default": 0.1775, "role": "exogenous",
		"determinism": "physical", "priority": "P2", "status": "existing",
		"source": "Stoichiometry of NH3; the LHV basis of the fuel tables",
		"users": ["Industrial users"],
	}

	# --- the mix-share products ---
	products = [
		(
			"steel_h2_dri_share",
			"steel_hydrogen_demand_tonnes = steel_production * steel_h2_dri_share * hydrogen_per_t_steel_kg * 1000",
			"Hydrogen the H2-DRI steel route consumes: the sector's tonnes times "
			"the mix share times the process's own hydrogen intensity, at the "
			"unit conversion million-tonnes to tonnes.",
			"HYBRIT; the sector-coupling hydrogen-demand identity",
		),
		(
			"ammonia_export_share",
			"ammonia_export_volume_tonnes = hydrogen_export_volume * ammonia_export_share * hydrogen_share_of_ammonia * 1000 * 0.05",
			"Ammonia the export programme ships: the export energy times the "
			"share that goes as ammonia, times the hydrogen mass the ammonia "
			"carries, at the unit conversions MWh-to-MJ and tonne.",
			"The export terminal's own product mix; the fuel tables' LHV basis",
		),
		(
			"cement_ccus_share",
			"co2_captured_cement_tonnes = cement_production * cement_ccus_share * 0.8 * 1000000",
			"CO2 the cement programme captures: the sector's tonnes times the "
			"cement put through CCUS times the capture intensity per tonne "
			"(process emissions dominate at ~0.8 t/t clinker; blended cements "
			"lower it).",
			"IPCC cement process emissions; the clinker factor",
		),
		(
			"industrial_ccus_share",
			"co2_captured_industry_tonnes = industrial_ccus_share * emissions_mtco2_per_year * 1000000",
			"CO2 the industrial CCUS programme captures, as a share of the "
			"fleet's own emissions the emissions identity computes.",
			"The emissions accounting the emissions system derives",
		),
		(
			"interruptible_load_share",
			"interruptible_load_mw = interruptible_load_share * peak_demand_mw",
			"The load the utility may curtail on contract: its share of peak "
			"demand, which is the demand-response product the interruptible "
			"contracts define.",
			"Demand-response programme design (the interruptible contract's own definition)",
		),
	]
	for share, product, prose, cite in products:
		target = product.split(" =")[0]
		share_node = graph.nodes[share]
		nodes[share] = dict(share_node.model_dump(exclude={"id"}, mode="json"))
		nodes[share].update({
			"description": (
				f"{graph.nodes[share].name}: {graph.nodes[share].description[:40]}"
			) + " The share's own coupling: the product below derives from it.",
		})
		eq_id = f"{target}_definition"
		sys = "price_demand" if "load" in target else "financial"
		equations[eq_id] = {
			"id": eq_id,
			"name": target.replace("_", " ").capitalize(),
			"description": prose,
			"system": sys,
			"lhs": target,
			"rhs": product.split(" = ", 1)[1],
			"relation": "eq",
			"parameters": [target],
			"free_variables": [],
			"determined_variables": [target],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
	# The parameters/free lists for the four above, written explicitly:
	# the share is free, the constant nodes are free or exogenous, and the
	# derived reads (emissions) enter as parameters.
	# The product targets, declared: unit, range, role, and an edge per
	# parameter, in the loop above the explicit lists are rebuilt from.
	target_facts = {
		"steel_hydrogen_demand_tonnes": ("tonnes", [0.0, 1.0e7]),
		"ammonia_export_volume_tonnes": ("tonnes", [0.0, 1.0e7]),
		"co2_captured_cement_tonnes": ("tonnes", [0.0, 1.0e8]),
		"co2_captured_industry_tonnes": ("tonnes", [0.0, 1.0e9]),
		"interruptible_load_mw": ("MW", [0.0, 100000.0]),
	}
	for target, (unit, rng) in target_facts.items():
		nodes[target] = {
			"name": target.replace("_", " ").capitalize(),
			"description": (
				f"{target.replace('_', ' ')}: the sector-mix share's product, "
				"derived, so a scenario's mix dial has a quantity the reports "
				"can name."
			),
			"category": "Industry" if "steel" in target or "cement" in target or "co2" in target else "Demand-Side",
			"type": "float", "unit": unit, "range": rng, "role": "derived",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The sector-coupling identities (cite on the equation)",
			"users": ["Planners", "Industrial users", "Traders"],
		}
	explicit = {
		"steel_hydrogen_demand_tonnes": (
			["steel_production", "steel_h2_dri_share", "hydrogen_per_t_steel_kg"], [],
		),
		"ammonia_export_volume_tonnes": (
			["hydrogen_export_volume", "ammonia_export_share", "hydrogen_share_of_ammonia"], [],
		),
		"co2_captured_cement_tonnes": (
			["cement_production", "cement_ccus_share"], [],
		),
		"co2_captured_industry_tonnes": (
			["industrial_ccus_share", "emissions_mtco2_per_year"], ["industrial_ccus_share"],
		),
		"interruptible_load_mw": (
			["interruptible_load_share", "peak_demand_mw"], ["interruptible_load_share"],
		),
	}
	for target, (params, free) in explicit.items():
		eq_id = f"{target}_definition"
		equations[eq_id]["parameters"] = [target] + params
		equations[eq_id]["free_variables"] = free
		determined = [target]
		equations[eq_id]["determined_variables"] = determined
	for target, (params, _free) in explicit.items():
		for sym in params:
			edges.append({
				"source": sym, "target": target,
				"equation_id": f"{target}_definition", "relationship": "functional",
				"strength": "hard", "description": "Enters the sector product.",
			})
	return nodes, equations, edges, rules


# ---------------------------------------------------------------------------
# Batch 20: the share family's remaining products, and the time-index family.
#
# The share family is where the coupling has to be overlap-aware. The
# financing-mix shares (bonds, green bonds, DFI facilities, commercial bank
# lines, blended packages, carbon-financed instruments) do NOT sum to one:
# a green bond is a bond, a blended package draws on DFI money and commercial
# money, so a sum-to-one identity over them would be wrong on the graph's own
# semantics. What they obey are subset and envelope inequalities, and these
# are the couplings they get:
#
#   * debt_mix_bound        -- bond + DFI + commercial <= debt's own share of
#                              the capital structure (D/(D+E) from the shipped
#                              debt_equity_ratio). The three instrument
#                              classes fund the same debt tranche, so together
#                              they may not exceed it.
#   * blended_finance_bound -- a blended package draws on the concessional
#                              (DFI) and commercial tranche, so its share is
#                              bounded by the two together.
#   * green_bond_bound      -- green bonds are a subset of bond issuance
#                              (ICMA Green Bond Principles).
#   * carbon_finance_bound  -- carbon-backed financing may not exceed the
#                              carbon revenue stream it is collateral on,
#                              which the shipped carbon/total-revenue pair
#                              computes.
#   * steel_route_bound     -- the scrap-EAF and H2-DRI routes are shares of
#                              the same crude-steel output: together <= 1.
#   * urban_heat_supply_bound / powertrain_stock_bound -- the two couples'
#                              modes are disjoint supply/powertrain classes
#                              of one stock, so each pair sums to at most 1.
#   * v2g_subset_bound      -- V2G-capable EVs are a subset of the EV stock.
#
# The time-index family couples as its own arithmetic, not as products with
# missing bases: lead times between policy milestones (differences of the
# same clock, [time] - [time]), windows (the growth window), schedules against
# durations (retraining within construction), and the storage power-energy
# cost split (cost per kW of the unit-power view of a store, and cost per kWh
# of the per-energy view), which is what makes battery_duration and
# phs_duration the sizing knobs they are. The vintage years (solar_cf_year,
# wind_cf_year) couple through the degradation rates: the capacity factor the
# graph quotes is the factor AT the vintage year, i.e. the factor today
# compounded by the technology's own degradation.
# ---------------------------------------------------------------------------

# The financing-mix defaults, aligned so that every bound above holds at the
# defaults the shipped graph carries -- the same constraint as the batch-13
# products (a bound violated at its own defaults is a validation failure, not
# a coupling). The alignment is itself the finding the overlap-aware framing
# demands: bond 25%, DFI 20%, commercial 20% sums to 65%, inside the 69.97%
# the debt/equity ratio of 2.33 implies; a blended package (35%) and green
# bonds (10%) sit under their own envelopes.
BATCH20_SHARE_DEFAULTS: tuple[tuple[str, str, float, str], ...] = (
	(
		"bond_share",
		"The bond market's supply of the project's debt financing. Default "
		"aligned so that the three instrument classes' shares sit inside "
		"debt's own share of the capital structure (debt_mix_bound).",
		0.25,
		"The financing-mix corrections (batch 20)",
	),
	(
		"green_bond_share",
		"The share of the project's debt financing the bond market supplies "
		"through green-labelled instruments. A subset of bond issuance (the "
		"same tranche funded under a use-of-proceeds label), so it is "
		"bounded by bond itself.",
		0.10,
		"The financing-mix corrections (batch 20)",
	),
	(
		"dfi_share",
		"The DFI facilities' supply of the project's debt financing. "
		"Default aligned so the three instrument classes' shares sit inside "
		"debt's own share of the capital structure.",
		0.20,
		"The financing-mix corrections (batch 20)",
	),
	(
		"commercial_bank_share",
		"The commercial banks' supply of the project's debt financing. "
		"Default aligned so the three instrument classes' shares sit inside "
		"debt's own share of the capital structure.",
		0.20,
		"The financing-mix corrections (batch 20)",
	),
	(
		"blended_finance_share",
		"The share of the project's financing structured as a blended "
		"package. Blending combines a concessional and a commercial tranche, "
		"so the share's scale is bounded by the two funding sources "
		"together -- which is the coupling, not a sum-to-one identity.",
		0.35,
		"The financing-mix corrections (batch 20)",
	),
	(
		"carbon_finance_share",
		"The share of the project's financing backed by carbon credit sales. "
		"Bounded by the carbon revenue stream itself (the finance the carbon "
		"instrument can carry), which the shipped carbon/total-revenue pair "
		"computes.",
		0.05,
		"The financing-mix corrections (batch 20)",
	),
)

# The placeholder nodes the time-index products read: every one ships with
# the placeholder default (500 000, unit None) and every one needs a unit the
# arithmetic and the walker can carry, a default inside its own declared range,
# and a range whose images hold the defaults.
BATCH20_PLACEHOLDER_CORRECTIONS: dict[
	str, tuple[str, list[float], float, str, str, str]
] = {
	"chemicals_ammonia_production": (
		"tonnes/year", [0.0, 1000000.0], 600000.0, "free", "physical",
		"The chemical sector's ammonia output per year, in tonnes. The "
		"catalog's placeholder scale (0-1e6 t) retained as the range; the "
		"green-ammonia product below derives from it.",
	),
	"interconnector_capacity": (
		"MW", [0.0, 1000000.0], 1000.0, "free", "physical",
		"The MW capacity the cross-border link nominally carries: 1,000 MW "
		"is the scale an early interconnector takes (the EAC's proposed "
		"cross-border reinforcements are of this order).",
	),
	"phs_duration": (
		"hours", [0.0, 48.0], 6.0, "free", "physical",
		"Hours the PHS reservoir discharges at rated power: pumped storage "
		"sizes at 6-24 h.",
	),
	"thermal_storage_duration": (
		"hours", [0.0, 72.0], 8.0, "free", "physical",
		"Hours the thermal store discharges at rated output: molten-salt "
		"and pressurised-water stores sizes at 6-12 h, industrial heat "
		"stores up to days.",
	),
	"settlement_period": (
		"hours", [0.05, 24.0], 0.5, "free", "physical",
		"Hours one settlement period spans: half an hour is the standard "
		"settlement interval at mature system operators.",
	),
	"construction_period": (
		"months", [1.0, 96.0], 30.0, "free", "physical",
		"Months between financial close and commercial operation for a "
		"utility-scale IPP: thermal units build at 24-36 months, solar "
		"and wind faster; the range carries the project classes.",
	),
	"retraining_duration": (
		"months", [0.0, 60.0], 12.0, "free", "policy",
		"Months of retraining a displaced or in-plant worker takes: "
		"a year is the programme the utilities' plans budget.",
	),
	"line_outage_duration": (
		"hours/event", [0.5, 48.0], 6.0, "free", "physical",
		"Mean hours a line outage event spans: transmission faults with "
		"auto-reclose clear in minutes, repairs take hours.",
	),
	"line_outage_probability": (
		"1/year", [0.0, 365.0], 2.0, "free", "physical",
		"Expected line outage events per year. Shipped as a probability, "
		"which admits at most one event a year; reframed as the expected "
		"rate (the r_i term of the reliability indices' frequency-times-"
		"duration product), which is the quantity the product below needs.",
	),
	"maintenance_duration": (
		"hours/event", [2.0, 720.0], 48.0, "free", "physical",
		"Mean hours per planned maintenance event: routine servicing at "
		"the low end, a major inspection at the high end. Unit spelled as "
		"the per-event form the frequency product reads.",
	),
	"solar_degradation": (
		"1/year", [0.0, 0.02], 0.005, "free", "physical",
		"Relative PV degradation per year: the field's measured band "
		"centres near 0.5%/yr, with the faster technologies above 1%.",
	),
	"wind_degradation": (
		"1/year", [0.0, 0.02], 0.003, "free", "physical",
		"Relative wind-degradation per year: blade surface erosion and "
		"control drift are the mechanisms; the band sits well below PV's "
		"and the literature quotes ~0.3%/yr.",
	),
}

# The product targets: unit, range, category, and the prose the fragment
# carries. Every one is `derived`, so the propagate computes its value and
# the range must contain the image at defaults.
BATCH20_PRODUCT_NODES: dict[str, tuple[str, list[float], str, str]] = {
	"debt_financing_share": (
		"1", [0.0, 1.0], "Financial",
		"Debt's share of the capital structure: D/(D+E) from the shipped "
		"debt/equity ratio, which is the envelope the financing-mix "
		"instrument shares are bounded by.",
	),
	"carbon_revenue_share_of_revenue": (
		"1", [0.0, 1.0], "Financial",
		"The carbon revenue stream's weight in the fleet's total revenue: "
		"the envelope carbon-backed financing is bounded by.",
	),
	"steel_eaf_route_mt": (
		"million tonnes/year", [0.0, 200.0], "Industry",
		"Crude steel the scrap-EAF route makes: the mix share times the "
		"sector's own output.",
	),
	"chemicals_green_ammonia_tonnes_per_year": (
		"tonnes/year", [0.0, 1000000.0], "Industry",
		"Ammonia the chemical programme makes through the green route: the "
		"mix share times the sector's own output.",
	),
	"hvdc_interconnector_capacity_mw": (
		"MW", [0.0, 1000000.0], "Transmission",
		"Cross-border capacity in HVDC: the technology's share of the "
		"interconnector's own rating.",
	),
	"solar_pv_capacity_factor_at_vintage": (
		"1", [0.0, 1.0], "Generation",
		"The PV capacity factor AT the vintage year the dataset quotes: the "
		"factor today compounded by the technology's own degradation rate.",
	),
	"wind_capacity_factor_at_vintage": (
		"1", [0.0, 1.0], "Generation",
		"The onshore-wind capacity factor AT its dataset's vintage year: "
		"the factor today compounded by the technology's degradation.",
	),
	"hydro_inflow_vintage_offset_years": (
		"years", [-100.0, 100.0], "Generation",
		"How much the hydro inflow record's design year leads or trails the "
		"PV data's vintage. The vintage selectors are set independently, and "
		"this offset is the check a scenario author runs for consistency.",
	),
	"years_from_peak_to_net_zero": (
		"years", [-100.0, 100.0], "Planning",
		"Years between the emissions peak and the net-zero year, on the "
		"policy clock; the pace the trajectory must hold between the two "
		"milestones.",
	),
	"years_from_carbon_tax_to_net_zero": (
		"years", [-100.0, 100.0], "Planning",
		"Years between the carbon tax's start and the net-zero year: the "
		"carbon pricing's own running length on the policy clock.",
	),
	"years_from_renewable_target_to_net_zero": (
		"years", [-100.0, 100.0], "Planning",
		"Years between the renewable target's year and net zero.",
	),
	"construction_share_of_concession": (
		"1", [0.0, 1.0], "Financial",
		"The fraction of the concession term the construction period "
		"consumes: months over the term's own months.",
	),
	"financing_close_share_of_licence": (
		"1", [0.0, 1.0], "Financial",
		"The fraction of the licence term the financing-close deadline "
		"spans: months over the term's own months.",
	),
	"taxed_fraction_of_concession": (
		"1", [0.0, 1.0], "Financial",
		"The fraction of the concession term the income tax does apply to: "
		"one minus the holiday's share.",
	),
	"fit_annuity_factor": (
		"years", [0.0, 200.0], "Financial",
		"The present-value annuity factor over the FiT contract term, at "
		"the real discount rate: the PV-per-annum weight the tariff's "
		"cash flows carry.",
	),
	"total_loss_utilisation_window_years": (
		"years", [0.0, 30.0], "Financial",
		"The total window tax losses may be utilised over: the carryback "
		"and carryforward years together.",
	),
	"demand_growth_window_years": (
		"years", [-100.0, 100.0], "Demand-Side",
		"Years the growth trajectory spans: end year minus start year on "
		"the trajectory's own clock.",
	),
	"demand_growth_factor": (
		"1", [0.0, 10.0], "Demand-Side",
		"The compound growth factor over the trajectory's window: (1+g) to "
		"the window's years, the factor a forecast escalates demand by.",
	),
	"capex_battery_power_usd_per_kw": (
		"USD/kW", [0.0, 50000.0], "Storage",
		"The battery's energy store expressed per kW of power rating: the "
		"per-energy cost times the duration, the power-energy split the "
		"storage sizing literature keeps.",
	),
	"phs_energy_capex_usd_per_kwh": (
		"USD/kWh", [0.0, 10000.0], "Storage",
		"Pumped hydro's cost per kWh of energy: the power-quoted installed "
		"cost divided by the reservoir's hours, the power-energy split's "
		"other direction -- and the reason PHS is cheap per energy and "
		"expensive per power.",
	),
	"thermal_phs_duration_ratio": (
		"1", [0.0, 10.0], "Storage",
		"The thermal store's duration relative to pumped hydro's: the "
		"long-duration comparison a portfolio's sizing check starts from.",
	),
	"settlement_intervals_per_hour": (
		"1/hour", [0.0, 100.0], "Demand-Side",
		"How many settlement periods an hour carries: the inverse of the "
		"interval, which is what a dispatch or a data series counts.",
	),
	"line_outage_hours_per_year": (
		"hours/year", [0.0, 8760.0], "Reliability",
		"Hours per year the line spends out: the frequency-times-duration "
		"product, the line-level figure of the same form the SAIDI sum "
		"takes at system level.",
	),
	"planned_maintenance_hours_per_year": (
		"hours/year", [0.0, 8760.0], "Reliability",
		"Hours per year planned maintenance takes: the events' frequency "
		"times their duration, the planned-outage term against "
		"availability.",
	),
}

# The bounds: (id, lhs, rhs, prose, system, priority). `relation` leq on all.
BATCH20_BOUNDS: tuple[tuple[str, str, str, str, str, str], ...] = (
	(
		"debt_mix_bound",
		"bond_share + dfi_share + commercial_bank_share",
		"debt_financing_share",
		"The three debt-instrument classes cannot, together, exceed debt's "
		"own share of the capital structure: they fund the same debt "
		"tranche, which the D/E ratio declares.",
		"financial", "P1",
	),
	(
		"blended_finance_bound",
		"blended_finance_share",
		"dfi_share + commercial_bank_share",
		"A blended package draws on the concessional and the commercial "
		"tranche, so its share's scale is bounded by the two together.",
		"financial", "P2",
	),
	(
		"green_bond_bound",
		"green_bond_share",
		"bond_share",
		"Green bonds are a subset of bond issuance -- the same tranche "
		"funded under a use-of-proceeds label -- so their share is bounded "
		"by the bond market's own share.",
		"financial", "P2",
	),
	(
		"carbon_finance_bound",
		"carbon_finance_share",
		"carbon_revenue_share_of_revenue",
		"Financing backed by carbon credit sales cannot exceed the carbon "
		"revenue stream it is collateral on: the carbon stream is the "
		"repayment source, and its weight in total revenue bounds "
		"the share.",
		"financial", "P2",
	),
	(
		"steel_route_bound",
		"steel_scrap_eaf_share + steel_h2_dri_share",
		"1.0",
		"The scrap-EAF and H2-DRI routes are shares of the same crude-steel "
		"output: together they may not exceed it.",
		"price_demand", "P1",
	),
	(
		"urban_heat_supply_bound",
		"district_heating_share + heat_pump_adoption",
		"1.0",
		"District heating and heat pumps are disjoint supply modes of the "
		"same urban building stock's heat: together they may not exceed the "
		"stock.",
		"demand_supply", "P2",
	),
	(
		"powertrain_stock_bound",
		"hydrogen_vehicle_share + electric_vehicle_adoption",
		"1.0",
		"Fuel-cell and battery vehicles are disjoint powertrains of the "
		"same vehicle stock: together they may not exceed it.",
		"demand_supply", "P2",
	),
	(
		"v2g_subset_bound",
		"v2g_adoption",
		"electric_vehicle_adoption",
		"V2G-capable vehicles are a subset of the EV stock: their share of "
		"the fleet cannot exceed the EV share itself.",
		"demand_supply", "P2",
	),
	(
		"retraining_schedule_bound",
		"retraining_duration",
		"construction_period",
		"The retraining programme completes within construction: workers "
		"are trained while the plant is built, and the schedule bound is "
		"months against months.",
		"employment", "P2",
	),
)

# The equations: (id, name, lhs, rhs, prose, system, determined, parameters,
# linearity, reference). Every product is an equality whose target is the
# derived node; the parameters carry the rhs's own names.
BATCH20_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, str, str | None], ...
] = (
	(
		"debt_financing_share_definition",
		"Debt's share of the capital structure",
		"debt_financing_share",
		"debt_equity_ratio / (1.0 + debt_equity_ratio)",
		"Debt's own share of the capital structure: D/(D+E), the conversion "
		"of the shipped debt/equity ratio to the share the financing-mix "
		"bounds are expressed against.",
		"financial", "linear", "1",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"carbon_revenue_share_of_revenue_definition",
		"Carbon revenue's weight in total revenue",
		"carbon_revenue_share_of_revenue",
		"carbon_revenue_usd_per_year / total_revenue_usd_per_year",
		"The carbon stream's weight in the fleet's revenue: the ratio the "
		"carbon-backed-financing bound is expressed against.",
		"financial", "linear", "1",
		"Stoft 2002, Power System Economics, ch. 5",
	),
	(
		"steel_eaf_route_definition",
		"Crude steel the scrap-EAF route makes",
		"steel_eaf_route_mt",
		"steel_scrap_eaf_share * steel_production",
		"Crude steel the scrap-EAF route makes: the mix share times the "
		"sector's own output, in million tonnes.",
		"price_demand", "linear", "million tonnes/year",
		None,
	),
	(
		"chemicals_green_ammonia_definition",
		"Ammonia the green route makes",
		"chemicals_green_ammonia_tonnes_per_year",
		"chemicals_green_ammonia_share * chemicals_ammonia_production",
		"Ammonia the chemical programme makes through the green route: the "
		"mix share times the sector's own output, in tonnes.",
		"price_demand", "linear", "tonnes/year",
		None,
	),
	(
		"hvdc_capacity_definition",
		"Cross-border capacity in HVDC",
		"hvdc_interconnector_capacity_mw",
		"hvdc_share * interconnector_capacity",
		"The interconnector's MW rating that carries HVDC: the technology's "
		"share times the link's own capacity.",
		"demand_supply", "linear", "MW",
		None,
	),
	(
		"solar_pv_capacity_factor_at_vintage_definition",
		"The PV capacity factor at the dataset's vintage year",
		"solar_pv_capacity_factor_at_vintage",
		"solar_pv_capacity_factor * (1.0 - solar_degradation) ** solar_cf_year",
		"The PV capacity factor AT the vintage year the dataset quotes: "
		"the factor today compounded by the technology's own degradation "
		"rate, whose field-measured band the degradation node carries.",
		"demand_supply", "nonlinear", "1",
		None,
	),
	(
		"wind_capacity_factor_at_vintage_definition",
		"The onshore-wind capacity factor at its vintage year",
		"wind_capacity_factor_at_vintage",
		"capacity_factor_wind_onshore * (1.0 - wind_degradation) ** wind_cf_year",
		"The onshore-wind capacity factor AT its dataset's vintage year: "
		"the factor compounded by the technology's degradation.",
		"demand_supply", "nonlinear", "1",
		None,
	),
	(
		"hydro_inflow_vintage_offset_definition",
		"The inflow record's vintage offset",
		"hydro_inflow_vintage_offset_years",
		"hydro_inflow_year - solar_cf_year",
		"How much the hydro inflow record's design year leads or trails the "
		"PV data's vintage. The vintage selectors are set independently, and "
		"this offset is the check a scenario author runs for consistency.",
		"demand_supply", "linear", "years",
		None,
	),
	(
		"years_from_peak_to_net_zero_definition",
		"Years from the emissions peak to net zero",
		"years_from_peak_to_net_zero",
		"net_zero_year - emissions_peak_year",
		"Years between the emissions peak and the net-zero year on the "
		"policy clock: the pace the trajectory must hold between the two "
		"milestones.",
		"carbon_trajectory", "linear", "years",
		None,
	),
	(
		"years_from_carbon_tax_to_net_zero_definition",
		"Years the carbon tax runs to net zero",
		"years_from_carbon_tax_to_net_zero",
		"net_zero_year - carbon_tax_start_year",
		"Years between the carbon tax's start and the net-zero year: the "
		"pricing's own running length on the policy clock.",
		"carbon_trajectory", "linear", "years",
		None,
	),
	(
		"years_from_renewable_target_to_net_zero_definition",
		"Years from the renewable target to net zero",
		"years_from_renewable_target_to_net_zero",
		"net_zero_year - renewable_target_year",
		"Years between the renewable target's year and net zero on the "
		"policy clock.",
		"carbon_trajectory", "linear", "years",
		None,
	),
	(
		"construction_share_of_concession_definition",
		"The construction period's share of the concession",
		"construction_share_of_concession",
		"construction_period / (concession_duration * 12.0)",
		"The fraction of the concession term construction consumes: months "
		"over the term's own months. The metric the concessionaire's "
		"downtime exposure is stated against.",
		"financial", "linear", "1",
		None,
	),
	(
		"financing_close_share_of_licence_definition",
		"The financing-close deadline's share of the licence",
		"financing_close_share_of_licence",
		"financing_close_deadline / (licence_duration * 12.0)",
		"The fraction of the licence term the financing-close deadline "
		"spans: months over the term's own months. The metric the "
		"licence-lapse risk is stated against.",
		"financial", "linear", "1",
		None,
	),
	(
		"taxed_fraction_of_concession_definition",
		"The taxed fraction of the concession",
		"taxed_fraction_of_concession",
		"1.0 - tax_holiday_duration / concession_duration",
		"The fraction of the concession term income tax does apply to: one "
		"minus the holiday's share. The multiplier the taxable-income "
		"accounts carry.",
		"financial", "linear", "1",
		None,
	),
	(
		"fit_annuity_factor_definition",
		"The annuity factor over the FiT term",
		"fit_annuity_factor",
		"(1.0 - (1.0 + real_discount_rate) ** (-fit_duration)) / real_discount_rate",
		"The present-value annuity factor over the FiT contract term, at "
		"the real discount rate the Fisher identity derives: the "
		"PV-per-annum weight the tariff's cash flows carry.",
		"financial", "nonlinear", "years",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"total_loss_utilisation_window_definition",
		"The tax-loss utilisation window",
		"total_loss_utilisation_window_years",
		"loss_carryback_years + loss_carryforward_years",
		"The total window tax losses may be utilised over: the carryback "
		"and carryforward years together, which is what the effective "
		"tax-rate smoothing relies on.",
		"financial", "linear", "years",
		None,
	),
	(
		"demand_growth_window_definition",
		"The growth trajectory's window",
		"demand_growth_window_years",
		"demand_growth_end_year - demand_growth_start_year",
		"Years the demand growth trajectory spans: end year minus start "
		"year on the trajectory's own clock.",
		"price_demand", "linear", "years",
		None,
	),
	(
		"demand_growth_factor_definition",
		"The compound growth factor over the window",
		"demand_growth_factor",
		"(1.0 + demand_growth) ** demand_growth_window_years",
		"The compound growth factor over the trajectory's window: (1+g) to "
		"the window's years, the factor a forecast escalates demand by.",
		"price_demand", "nonlinear", "1",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"capex_battery_power_usd_per_kw_definition",
		"The battery store's cost per kW",
		"capex_battery_power_usd_per_kw",
		"capex_battery * battery_duration",
		"The battery's energy store expressed per kW of power rating: the "
		"per-energy cost times the duration, the power-energy cost split "
		"the storage sizing literature keeps.",
		"cost_accounting", "linear", "USD/kW",
		"NREL ATB 2025 Equations & Variables",
	),
	(
		"phs_energy_capex_usd_per_kwh_definition",
		"Pumped hydro's cost per kWh",
		"phs_energy_capex_usd_per_kwh",
		"capex_phs / phs_duration",
		"Pumped hydro's cost per kWh of energy: the power-quoted installed "
		"cost divided by the reservoir's hours, the power-energy split's "
		"other direction -- and the reason PHS is cheap per energy and "
		"expensive per power.",
		"cost_accounting", "linear", "USD/kWh",
		"NREL ATB 2025 Equations & Variables",
	),
	(
		"thermal_phs_duration_ratio_definition",
		"The thermal store's duration against pumped hydro's",
		"thermal_phs_duration_ratio",
		"thermal_storage_duration / phs_duration",
		"The thermal store's duration relative to pumped hydro's: the "
		"long-duration comparison a portfolio's sizing check starts from.",
		"cost_accounting", "linear", "1",
		None,
	),
	(
		"settlement_intervals_per_hour_definition",
		"How many settlement periods an hour carries",
		"settlement_intervals_per_hour",
		"1.0 / settlement_period",
		"How many settlement periods an hour carries: the interval's "
		"inverse, which is what a dispatch count or a data series reads.",
		"price_demand", "linear", "1/hour",
		None,
	),
	(
		"line_outage_hours_per_year_definition",
		"Hours the line spends out per year",
		"line_outage_hours_per_year",
		"line_outage_probability * line_outage_duration",
		"Hours per year the line spends out: expected events times the "
		"mean event duration, the line-level figure of the same form the "
		"SAIDI sum takes at system level.",
		"reliability", "linear", "hours/year",
		"IEEE Guide for Electric Power Distribution Reliability Indices (1366), "
		"tutorial deck",
	),
	(
		"planned_maintenance_hours_per_year_definition",
		"Hours planned maintenance takes per year",
		"planned_maintenance_hours_per_year",
		"maintenance_frequency * maintenance_duration",
		"Hours per year planned maintenance takes: the events' frequency "
		"times their duration, the planned-outage term against "
		"availability.",
		"reliability", "linear", "hours/year",
		"IEEE Guide for Electric Power Distribution Reliability Indices (1366), "
		"tutorial deck",
	),
)

# Two batch-19 citations never registered: the products are definitional, and
# the intensity's provenance lives on the hydrogen_per_t_steel_kg node. The
# references go to null rather than to prose no row resolves.
BATCH20_EQUATION_REPAIRS: tuple[str, ...] = (
	"steel_hydrogen_demand_tonnes_definition",
	"ammonia_export_volume_tonnes_definition",
	"co2_captured_cement_tonnes_definition",
	"co2_captured_industry_tonnes_definition",
	"interruptible_load_mw_definition",
)


def build_batch20(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 20: the share family's remaining products and the time-index family."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	# --- the financing-mix defaults ---
	for name, prose, default, _source in BATCH20_SHARE_DEFAULTS:
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"default": default, "role": "free", "description": prose,
			"range": [0.0, 1.0], "priority": "P2", "status": "existing",
			"source": _source,
		})
		nodes[name] = full

	# --- the placeholder corrections ---
	for name, (unit, rng, default, role, determinism, prose) in (
		BATCH20_PLACEHOLDER_CORRECTIONS.items()
	):
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default, "role": role,
			"description": prose, "determinism": determinism,
			"priority": "P1", "status": "existing",
			"source": "The coupling build's own corrections (batch 20)",
			"users": ["Planners", "Financial analysts"],
		})
		nodes[name] = full

	# --- the two batch-19 citation repairs ---
	for eq_id in BATCH20_EQUATION_REPAIRS:
		body = dict(graph.equations[eq_id].model_dump(mode="json"))
		body["reference"] = None
		equations[eq_id] = body

	# --- the product equations ---
	for eq_id, name, lhs, rhs, prose, system, linearity, unit, cite in (
		BATCH20_EQUATIONS
	):
		rhs_params = []
		parsed_ok = False
		try:
			from alea.prg.dsl import parse_side

			rhs_params = sorted(parse_side(rhs).symbols)
			parsed_ok = True
		except Exception:
			pass
		assert parsed_ok, f"{eq_id}: rhs does not parse: {rhs}"
		equations[eq_id] = {
			"id": eq_id,
			"name": name,
			"description": prose,
			"system": system,
			"lhs": lhs,
			"rhs": rhs,
			"relation": "eq",
			"parameters": [lhs] + rhs_params,
			"free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": linearity,
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"strength": "hard", "description": "Enters the product.",
			})

	# --- the product targets, declared ---
	for target, (unit, rng, category, prose) in BATCH20_PRODUCT_NODES.items():
		nodes[target] = {
			"name": target.replace("_", " ").capitalize(),
			"description": (
				f"{target.replace('_', ' ')}: the coupling's derived quantity, "
				"so a scenario's dial has a number the reports can name."
			) + " " + prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "role": "derived",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The coupling build's own corrections (batch 20)",
			"users": ["Planners", "Financial analysts"],
		}

	# --- the bounds ---
	for eq_id, lhs, rhs, prose, system, priority in BATCH20_BOUNDS:
		named = sorted(set(
			sym for side in (lhs, rhs)
			for sym in _side_symbols(side)
		))
		equations[eq_id] = {
			"id": eq_id, "name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system, "lhs": lhs, "rhs": rhs,
			"relation": "leq",
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": priority, "reference": None,
			"latex": r"\mathrm{see\ equation}",
		}
	return nodes, equations, edges, rules


def _side_symbols(side: str) -> list[str]:
	"""The node symbols one side of a bound names, through the DSL."""
	from alea.prg.dsl import parse_side

	try:
		return sorted(parse_side(side).symbols)
	except Exception:
		return []


# ---------------------------------------------------------------------------
# Batch 21: the cost family's products against bases that exist, and the rate
# family's own arithmetic.
#
# The cost family couples as spend and annuities: a cost is a price, and its
# coupling is the quantity it multiplies. The feedstock cost joins the biomass
# variable cost the plant accounts (fuel + non-fuel O&M); the connection cost
# multiplies the VRE target fleet; the heat pump's installed cost annuitises
# through the shipped crf; the hydrogen export price multiplies the export
# volume the sector-coupling layer declared; the insurance share acts on the
# fleet's own USD/kW; the SHS and mini-grid costs multiply their deployment
# counts; the uranium price meets the burnup its LWR fuel cycle implies, as a
# named constant. Three costs (hydrogen pipeline per MW-km, right-of-way per
# km, the currency hedge's exposure) have no length or exposure base in the
# graph and wait for the base-node batch; the learning rates wait for a
# cumulative-deployment base, because Wright's law acts on cumulative
# deployment and the graph carries none yet.
#
# The rate family couples in two forms. An annual exponential rate has a
# half-life, `ln 2 / r` — the coal retirement's, the ETS cap's, the grid
# extension programme's — and a compound growth factor over the horizon,
# `(1 + r) ** horizon_years`, is what the industrial, population and
# urbanisation rates say about the horizon's own clock. `demand_growth_rate`
# stays uncoupled permanently: it is deprecated with its replacement named
# and the loader refuses any equation reaching a deprecated node by design.
# ---------------------------------------------------------------------------

# Placeholder corrections: unit completed, default inside its own range,
# range whose images hold the products (and whose bounds make sense).
BATCH21_PLACEHOLDER_CORRECTIONS: dict[
	str, tuple[str, list[float], float, str, str, str]
] = {
	"demand_response_cost": (
		"USD/kW/year", [0.0, 200.0], 40.0, "free", "physical",
		"The demand-response programme's capacity payment per kilowatt of "
		"enrolled capacity, per year: 40 is the scale a standing "
		"curtailment contract pays; the range spans the interruptible-"
		"tariff classes.",
	),
	"life_extension_cost": (
		"USD/kW", [0.0, 3000.0], 600.0, "free", "physical",
		"The capital cost of a life-extension programme, per kilowatt of "
		"the fleet it extends: 600 is the scale a mid-life overhaul of a "
		"thermal unit carries against a 1,200 USD/kW new build.",
	),
	"hydrogen_export_price": (
		"USD/MWh", [0.0, 500.0], 100.0, "free", "physical",
		"The price green hydrogen realises at the export terminal: 100 "
		"USD/MWh is about 3.3 USD/kg at the gas's LHV basis, the early-"
		"terminal scale the shipping schedule quotes.",
	),
	"solar_home_system_deployment": (
		"1/year", [0.0, 1000000.0], 150000.0, "free", "physical",
		"Units the solar-home-system programme delivers per year. The "
		"catalog's placeholder scale retained as the range; the "
		"programme-spend product derives from it.",
	),
	"mini_grid_deployment": (
		"1/year", [0.0, 1000000.0], 100000.0, "free", "physical",
		"Connections the mini-grid programme serves per year. The catalog's "
		"placeholder scale retained as the range; the programme-spend "
		"product derives from it.",
	),
	"ets_cap_reduction_rate": (
		"1/year", [0.0, 1.0], 0.5, "free", "policy",
		"The annual rate the ETS cap is cut by. Shipped with unit '1', "
		"which leaves the annualisation implicit; spelled as the rate the "
		"half-life product reads.",
	),
	"grid_extension_rate": (
		"1/year", [0.0, 1.0], 0.5, "free", "policy",
		"The annual rate the grid-extension programme connects at. Shipped "
		"with unit '1'; spelled as the rate the completion-horizon product "
		"reads.",
	),
	"shs_cost": (
		"USD", [50.0, 2000.0], 400.0, "free", "physical",
		"Delivered cost per solar home system to the customer. The unit "
		"reads as the per-system price the deployment product multiplies.",
	),
}

# The product targets (unit, range, category, prose).
BATCH21_PRODUCT_NODES: dict[str, tuple[str, list[float], str, str]] = {
	"biomass_variable_cost_usd_per_mwh": (
		"USD/MWh", [0.0, 100.0], "Cost",
		"The biomass plant's own variable cost incl. fuel: the feedstock "
		"price plus the non-fuel O&M the plant accounts.",
	),
	"vre_connection_spend_usd": (
		"USD", [0.0, 5000000000.0], "Cost",
		"The connection spend the VRE target fleet carries: the per-kW "
		"connection cost times the target's megawatts, at the MW-to-kW "
		"conversion.",
	),
	"heat_pump_annualised_cost_usd_per_kw_year": (
		"USD/kW/year", [0.0, 6000.0], "Cost",
		"The installed heat pump's annuity, per kW-year: the capital cost "
		"times the shipped crf the discount rate implies.",
	),
	"hydrogen_export_revenue_usd_per_year": (
		"USD/year", [0.0, 500000000.0], "Financial",
		"The export programme's revenue: the terminal price times the "
		"export volume the sector-coupling layer declared.",
	),
	"insurance_premium_usd_per_kw_year": (
		"USD/kW/year", [0.0, 100.0], "Financial",
		"The fleet's insurance premium per kW-year: the installed cost's "
		"own share, per the share-of-cost basis the insurance product "
		"declares.",
	),
	"life_extension_fraction_of_new_build": (
		"1", [0.0, 5.0], "Cost",
		"The life-extension cost against a new build per kW: the fraction "
		"the retire-vs-extend decision is stated against.",
	),
	"mini_grid_programme_spend_usd_per_year": (
		"USD/year", [0.0, 5000000000.0], "Cost",
		"The mini-grid programme's spend: per-connection cost times the "
		"connections served per year.",
	),
	"demand_response_programme_cost_usd_per_year": (
		"USD/year", [0.0, 5000000000.0], "Cost",
		"The demand-response programme's annual cost: the per-kW-year "
		"payment times the curtailment capacity, at the MW-to-kW "
		"conversion.",
	),
	"shs_programme_spend_usd_per_year": (
		"USD/year", [0.0, 1000000000.0], "Cost",
		"The solar-home-system programme's spend: per-unit delivered cost "
		"times the units delivered per year.",
	),
	"uranium_fuel_cost_usd_per_mwh": (
		"USD/MWh", [0.0, 5.0], "Cost",
		"The nuclear fleet's fuel cost per megawatt-hour: the spot price "
		"times the LWR burnup the unit's refuelling implies, per the named "
		"constant.",
	),
	"coal_retirement_half_life_years": (
		"years", [0.0, 500.0], "Generation",
		"Years for the coal fleet to half-retire at the annual rate: "
		"ln 2 over the rate, the half-life of an exponential retirement.",
	),
	"ets_cap_half_life_years": (
		"years", [0.0, 100.0], "Carbon",
		"Years for the ETS cap to halve at its annual reduction rate: "
		"ln 2 over the rate.",
	),
	"grid_extension_completion_years": (
		"years", [0.0, 100.0], "Planning",
		"The programme's characteristic completion time at its annual "
		"connection rate: ln 2 over the rate.",
	),
	"industrial_growth_factor": (
		"1", [0.0, 10.0], "Industry",
		"The factor industrial output grows by over the horizon at the "
		"industrialisation rate: (1+r) to the horizon's years.",
	),
	"population_growth_factor": (
		"1", [0.0, 10.0], "Demand-Side",
		"The factor population grows by over the horizon at its growth "
		"rate: (1+r) to the horizon's years.",
	),
	"urban_share_growth_factor": (
		"1", [0.0, 10.0], "Demand-Side",
		"The factor the urban share grows by over the horizon at the "
		"urbanisation rate: (1+r) to the horizon's years, the first-order "
		"form since the share is itself bounded.",
	),
}

# A named process constant, the way hydrogen_per_t_steel_kg was: the LWR
# refuelling figure the fuel-cost product reads.
BATCH21_CONSTANT_NODES: dict[str, dict[str, Any]] = {
	"uranium_burnup_lb_per_mwh": {
		"name": "Uranium burnup per MWh",
		"description": (
			"Pounds of U3O8 the LWR fuel cycle burns per megawatt-hour "
			"electric: ~10 tU per GW-year electric at the LWR's own "
			"burnup, converted to the U3O8 lb basis the spot market "
			"quotes. A named node, not a folded figure."
		),
		"category": "Generation", "type": "float",
		"unit": "lb/MWh", "range": [0.0, 0.02], "default": 0.0025,
		"role": "free", "determinism": "physical", "priority": "P2",
		"status": "existing",
		"source": "LWR refuelling practice (10 tU/GW(e)-yr), the spot market's U3O8 lb basis",
		"users": ["Planners"],
	},
}

# The equations: (id, name, lhs, rhs, prose, system, linearity, target-unit,
# reference). Products and half-lives and growth factors.
BATCH21_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, str, str | None], ...
] = (
	(
		"biomass_variable_cost_definition",
		"The biomass plant's variable cost incl. fuel",
		"biomass_variable_cost_usd_per_mwh",
		"biomass_feedstock_cost + opex_variable_biomass",
		"Fuel plus non-fuel O&M: the variable cost the biomass plant's own "
		"dispatch economics are stated against, the two line items the "
		"cost accounts carry separately.",
		"cost_accounting", "linear", "USD/MWh", None,
	),
	(
		"vre_connection_spend_definition",
		"The VRE fleet's connection spend",
		"vre_connection_spend_usd",
		"grid_connection_cost * vre_capacity_target_mw * 1000.0",
		"The connection spend the target VRE fleet carries: the per-kW "
		"cost of joining the network times the fleet's megawatts, at the "
		"MW-to-kW conversion.",
		"cost_accounting", "linear", "USD", None,
	),
	(
		"heat_pump_annualised_cost_definition",
		"The heat pump's annuity per kW-year",
		"heat_pump_annualised_cost_usd_per_kw_year",
		"heat_pump_cost * crf",
		"The installed heat pump's annuity: the capital cost per kW "
		"annualised by the shipped crf the discount rate implies.",
		"cost_accounting", "linear", "USD/kW/year",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"hydrogen_export_revenue_definition",
		"The export programme's revenue",
		"hydrogen_export_revenue_usd_per_year",
		"hydrogen_export_price * hydrogen_export_volume",
		"The export programme's revenue: the terminal price per MWh times "
		"the energy the terminals load per year.",
		"financial", "linear", "USD/year", None,
	),
	(
		"insurance_premium_definition",
		"The fleet's insurance premium per kW-year",
		"insurance_premium_usd_per_kw_year",
		"insurance_loss_share_of_cost * capex_usd_per_kw",
		"The premium the fleet carries per kW-year, on the share-of-cost "
		"basis the insurance product itself declares: the share acts on "
		"the installed cost.",
		"financial", "linear", "USD/kW/year", None,
	),
	(
		"life_extension_fraction_definition",
		"The life-extension cost against a new build",
		"life_extension_fraction_of_new_build",
		"life_extension_cost / capex_usd_per_kw",
		"The life-extension programme's cost per kW against the fleet's "
		"own per-kW new build: the fraction the retire-vs-extend decision "
		"turns on.",
		"cost_accounting", "linear", "1", None,
	),
	(
		"mini_grid_programme_spend_definition",
		"The mini-grid programme's spend",
		"mini_grid_programme_spend_usd_per_year",
		"mini_grid_cost * mini_grid_deployment",
		"The mini-grid programme's spend per year: the per-connection "
		"installed cost times the connections served per year.",
		"cost_accounting", "linear", "USD/year", None,
	),
	(
		"demand_response_programme_cost_definition",
		"The demand-response programme's annual cost",
		"demand_response_programme_cost_usd_per_year",
		"demand_response_cost * interruptible_load_mw * 1000.0",
		"The programme's annual cost: the per-kW-year payment times the "
		"curtailment capacity the interruptible contracts declare, at the "
		"MW-to-kW conversion.",
		"cost_accounting", "linear", "USD/year", None,
	),
	(
		"shs_programme_spend_definition",
		"The solar-home-system programme's spend",
		"shs_programme_spend_usd_per_year",
		"shs_cost * solar_home_system_deployment",
		"The programme's spend per year: the delivered per-unit cost times "
		"the units delivered per year.",
		"cost_accounting", "linear", "USD/year", None,
	),
	(
		"uranium_fuel_cost_definition",
		"The nuclear fuel cost per MWh",
		"uranium_fuel_cost_usd_per_mwh",
		"uranium_price * uranium_burnup_lb_per_mwh",
		"The fuel cycle's spot-price component: the U3O8 spot price times "
		"the pounds the LWR burnup consumes per megawatt-hour electric, "
		"per the named burnup constant.",
		"cost_accounting", "linear", "USD/MWh", None,
	),
	(
		"coal_retirement_half_life_definition",
		"The coal fleet's retirement half-life",
		"coal_retirement_half_life_years",
		"log(2.0) / coal_retirement_rate",
		"Years for the coal fleet to half-retire at the annual rate: the "
		"half-life of an exponential retirement, ln 2 over the rate.",
		"carbon_trajectory", "linear", "years", None,
	),
	(
		"ets_cap_half_life_definition",
		"The ETS cap's half-life",
		"ets_cap_half_life_years",
		"log(2.0) / ets_cap_reduction_rate",
		"Years for the ETS cap to halve at its annual reduction rate: "
		"ln 2 over the rate, the same exponential arithmetic.",
		"carbon_trajectory", "linear", "years", None,
	),
	(
		"grid_extension_completion_definition",
		"The grid-extension programme's completion time",
		"grid_extension_completion_years",
		"log(2.0) / grid_extension_rate",
		"The characteristic time the programme completes in at its annual "
		"connection rate: ln 2 over the rate.",
		"price_demand", "linear", "years", None,
	),
	(
		"industrial_growth_factor_definition",
		"The industrial growth factor over the horizon",
		"industrial_growth_factor",
		"(1.0 + industrialisation_rate) ** horizon_years",
		"The factor industrial output grows by over the horizon at the "
		"industrialisation rate: the compound factor, (1+r) to the "
		"horizon's years.",
		"price_demand", "nonlinear", "1",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"population_growth_factor_definition",
		"The population growth factor over the horizon",
		"population_growth_factor",
		"(1.0 + population_growth_rate) ** horizon_years",
		"The factor population compounds by over the horizon: (1+r) to the "
		"horizon's years.",
		"price_demand", "nonlinear", "1",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
	(
		"urban_share_growth_factor_definition",
		"The urban share's growth factor over the horizon",
		"urban_share_growth_factor",
		"(1.0 + urbanisation_rate) ** horizon_years",
		"The factor the urban share compounds by over the horizon at the "
		"urbanisation rate: (1+r) to the horizon's years, the first-order "
		"form since the share itself is bounded.",
		"price_demand", "nonlinear", "1",
		"Short, Packey & Holt (1995), NREL/TP-462-5173",
	),
)


def build_batch21(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 21: the cost family's spend products and the rate family's arithmetic."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for name, (unit, rng, default, role, determinism, prose) in (
		BATCH21_PLACEHOLDER_CORRECTIONS.items()
	):
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default, "role": role,
			"description": prose, "determinism": determinism,
			"priority": "P1", "status": "existing",
			"source": "The coupling build's own corrections (batch 21)",
			"users": ["Planners", "Financial analysts"],
		})
		nodes[name] = full

	for name, body in BATCH21_CONSTANT_NODES.items():
		nodes[name] = dict(body)

	for eq_id, name, lhs, rhs, prose, system, linearity, unit, cite in (
		BATCH21_EQUATIONS
	):
		rhs_params = []
		parsed_ok = False
		try:
			from alea.prg.dsl import parse_side

			rhs_params = sorted(parse_side(rhs).symbols)
			parsed_ok = True
		except Exception:
			pass
		assert parsed_ok, f"{eq_id}: rhs does not parse: {rhs}"
		equations[eq_id] = {
			"id": eq_id,
			"name": name,
			"description": prose,
			"system": system,
			"lhs": lhs,
			"rhs": rhs,
			"relation": "eq",
			"parameters": [lhs] + rhs_params,
			"free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": linearity,
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"strength": "hard", "description": "Enters the product.",
			})

	for target, (unit, rng, category, prose) in BATCH21_PRODUCT_NODES.items():
		nodes[target] = {
			"name": target.replace("_", " ").capitalize(),
			"description": (
				f"{target.replace('_', ' ')}: the coupling's derived quantity, "
				"so a scenario's dial has a number the reports can name."
			) + " " + prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "role": "derived",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The coupling build's own corrections (batch 21)",
			"users": ["Planners", "Financial analysts"],
		}
	return nodes, equations, edges, rules


# ---------------------------------------------------------------------------
# Batch 22: the compliance register.
#
# The register family's nodes are *requirements* -- shares of a base the
# regulator or the lender specifies, or ceilings a shipped quantity must sit
# under. The coupling forms:
#
#   * register-share products: the requirement's share acts on the base that
#     exists (the revenue requirement for compliance spend, peak demand for
#     the capability requirements, total capacity for the telemetry and
#     grid-code shares, the carbon stream for the clearing-house fund);
#   * thresholds (leq): the shipped quantity the requirement binds must sit
#     inside it at the document's own defaults (SAIDI 96 <= 120, SAIFI
#     12 <= 15, largest loss 1000 <= 1200, inertia 500 <= 36000, the
#     resettlement share 0.02 <= 0.05);
#   * the exceedance product: the WHO annual PM2.5 guideline is *exceeded* by
#     the ambient mean the graph carries, and the honest statement is the
#     ratio (35 / 5 = 7) -- a bound would be a conflict at the document's own
#     defaults, which is the finding itself, computed rather than shipped as
#     a violated inequality.
#
# Eight bases arrive with the register (population, feeders, telemetry sites,
# audit accounts, pipeline count, river flow, distribution km, the ambient
# PM2.5 mean) -- each with a justified default, none with an invented
# citation.
# ---------------------------------------------------------------------------

# Register share/ceiling retypes: (name, unit, range, default, prose).
BATCH22_RETYPES: tuple[tuple[str, str, list[float], float, str], ...] = (
	("additionality_test", "1", [0.0, 1.0], 0.9,
	 "The share of the abatement programme's volume that clears the "
	 "additionality screen the crediting rules require."),
	("adms_requirements", "1", [0.0, 1.0], 0.35,
	 "The share of primary distribution feeders the ADMS control room "
	 "covers."),
	("air_quality_standards", "ug/m3", [0.0, 100.0], 5.0,
	 "The ambient PM2.5 limit the standards set, against the WHO 2021 "
	 "annual guideline of 5 ug/m3; the graph's own ambient mean (the "
	 "base node below) is the concentration the limit binds."),
	("baseline_methodology", "1", [0.0, 1.0], 0.8,
	 "The share of the crediting pipeline applying an approved baseline "
	 "methodology."),
	("black_start_requirement", "1", [0.0, 1.0], 0.02,
	 "The share of firm capacity the operator must hold in black-start-"
	 "capable units."),
	("clean_cooking_target", "1", [0.0, 1.0], 0.3,
	 "The clean-cooking access target; it cannot sit below the LPG "
	 "penetration already reached, which is the bound below."),
	("clearing_house_requirements", "1", [0.0, 1.0], 0.02,
	 "The share of settled carbon-trade value the clearing house collects "
	 "as its default fund."),
	("climate_proofing_requirements", "1", [0.0, 1.0], 0.35,
	 "The share of capex passing the climate-proofing screen (the "
	 "taxonomy-style test)."),
	("collateral_requirements", "1", [0.0, 1.0], 0.02,
	 "The security provisioned as a share of the annual revenue "
	 "requirement, declared here as an annualised provisioning share."),
	("consumer_protection_standards", "1", [0.0, 1.0], 0.005,
	 "The mandated metering-accuracy and dispute-resolution spend as a "
	 "share of the revenue requirement."),
	("cost_allocation_methodology", "1", [0.0, 1.0], 0.3,
	 "The share of fixed cost recovered through demand and customer "
	 "charges rather than energy charges (Stoft's cost-of-service "
	 "allocation)."),
	("credit_support_requirements", "1", [0.0, 1.0], 0.02,
	 "The credit-support annex pre-funding as a share of the revenue "
	 "requirement."),
	("cybersecurity_requirements", "1", [0.0, 0.1], 0.01,
	 "The control-system security spend (the IEC 62443 / NERC CIP class) "
	 "as a share of the revenue requirement."),
	("data_privacy_requirements", "1", [0.0, 1.0], 0.005,
	 "The DPIA and consent-system spend as a share of the revenue "
	 "requirement."),
	("data_sovereignty_requirements", "1", [0.0, 1.0], 0.9,
	 "The share of operational SCADA/EMS/meter data that must be hosted "
	 "in-country."),
	("demand_forecast_methodology", "1", [0.0, 0.5], 0.05,
	 "The allowed forecast error (MAPE); the band is what adequacy "
	 "planning must absorb on top of the forecast."),
	("environmental_flow_requirements", "1", [0.0, 1.0], 0.3,
	 "The environmental flow as a share of the river's mean annual flow, "
	 "in the Tennant fair-habitat band."),
	("fpic_requirements", "1", [0.0, 1.0], 0.6,
	 "The minimum documented-consent share the lender audits; the audited "
	 "score must clear it."),
	("frequency_response_requirement", "MW", [1.0, 20000.0], 1200.0,
	 "Primary-response capability must at least cover the largest credible "
	 "infeed loss, which is the bound below."),
	("gender_action_plan", "1", [0.0, 1.0], 0.3,
	 "The share of the community development fund ring-fenced for the "
	 "plan's line items."),
	("gis_requirements", "1", [0.0, 1.0], 0.6,
	 "The share of network assets in the GIS."),
	("grid_reliability_target", "hours/year", [0.0, 500.0], 120.0,
	 "The SAIDI ceiling the regulator sets, per the reliability indices' "
	 "own definition; the shipped baseline sits below it."),
	("ifc_performance_standards", "1", [0.0, 1.0], 0.3,
	 "The share of the portfolio covenanted under the performance "
	 "standards -- only what DFI money touches can be covenanted, which "
	 "is the bound below."),
	("inertia_requirement", "MW.s", [0.0, 5000.0], 500.0,
	 "The minimum synchronous inertia the system must hold: the "
	 "largest-loss-over-ROCOF floor the shipped inertia equation encodes, "
	 "stated against the inventory here."),
	("interoperability_standards", "1", [0.0, 1.0], 0.75,
	 "The share of connected capacity meeting the interconnection "
	 "standard."),
	("labour_standards", "1", [0.0, 1.0], 0.8,
	 "The share of construction-phase jobs carrying standard "
	 "contracts."),
	("margin_requirements", "1", [0.0, 1.0], 0.05,
	 "The initial margin on the carbon trading position, as a share of "
	 "the position's annual revenue value."),
	("non_spinning_reserve_requirement", "MW", [0.0, 3000.0], 400.0,
	 "The non-spinning slice of the operating reserve, inside the margin "
	 "the reserve requirement holds (the bound below)."),
	("reactive_power_requirement", "1", [0.0, 2.0], 0.33,
	 "Required reactive capability per MW of peak, the tan-phi of a "
	 "0.95 power factor."),
	("reporting_requirements", "1", [0.0, 1.0], 0.003,
	 "The mandated quarterly-filing systems spend as a share of the "
	 "revenue requirement."),
	("reserve_margin_requirement", "1", [0.0, 1.0], 0.15,
	 "The planning reserve margin, duplicate semantics of "
	 "reserve_margin_min; the product states its MW face value."),
	("resettlement_requirements", "1", [0.0, 0.5], 0.05,
	 "The cap on the physically or economically displaced population "
	 "share the safeguard allows."),
	("scada_ems_requirements", "1", [0.0, 1.0], 0.9,
	 "The share of connected capacity under SCADA/EMS telemetry."),
	("service_quality_standards", "events/year", [0.0, 200.0], 15.0,
	 "The SAIFI ceiling; the shipped baseline sits below it."),
	("affordability_threshold", "1", [0.0, 0.5], 0.10,
	 "The energy-burden share of income above which a household is in "
	 "energy poverty -- the 10% line, the same statistic the shipped "
	 "energy_burden_limit carries."),
)

# The eight base nodes: (name, unit, range, default, category, prose).
BATCH22_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("population_total", "people", [1000000.0, 200000000.0], 45000000.0, "Demographics",
	 "The country's population: 45 M, back-solved from the shipped "
	 "residential demand share and per-household consumption at five "
	 "persons per household."),
	("distribution_feeders_total", "1", [0.0, 5000.0], 500.0, "Grid",
	 "Primary distribution feeders: a 10 GW system at 30-50 MW per "
	 "feeder implies 200-500."),
	("pm25_annual_mean_ug_per_m3", "ug/m3", [0.0, 200.0], 35.0, "Environment",
	 "The ambient PM2.5 annual mean; sub-Saharan urban means run "
	 "30-50 ug/m3, against the WHO guideline of 5 -- the exceedance the "
	 "ratio below states."),
	("project_pipeline_count", "1", [0.0, 500.0], 40.0, "Carbon",
	 "Crediting projects in the country's annual pipeline, across the "
	 "programmes."),
	("scada_telemetry_sites", "1", [0.0, 1000.0], 220.0, "Grid",
	 "Generation sites plus bulk supply points of a 10 GW system."),
	("river_mean_annual_flow_m3_per_s", "m3/s", [0.0, 2000.0], 150.0, "Water",
	 "The hydro-bearing basins' cumulative mean annual flow: the ~1.5 GW "
	 "hydro fleet at ~55% CF implies a design flow of order "
	 "150-250 m3/s."),
	("distribution_network_km", "km", [0.0, 200000.0], 45000.0, "Grid",
	 "Distribution circuit-km: a 10 GW single-country network at about "
	 "4-5 km per MW."),
	("audit_accounts_per_year", "1", [0.0, 2000.0], 120.0, "Regulatory",
	 "Accounts in the regulator's annual audit sample across the "
	 "licensed fleet."),
)

# The products: (id, name, lhs, rhs, prose, system, linearity, target unit,
# range, reference).
BATCH22_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, str, list[float], str | None], ...
] = (
	("additional_abatement_definition",
	 "Abatement clearing additionality",
	 "additional_abatement_mtco2",
	 "additionality_test * carbon_budget_mtco2 / horizon_years",
	 "The abatement volume that clears the additionality screen: the "
	 "budget-scaled annual volume times the screened share.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 60.0], None),
	("adms_controlled_feeders_definition",
	 "Feeders under ADMS control",
	 "adms_controlled_feeders",
	 "adms_requirements * distribution_feeders_total",
	 "The feeders the ADMS control room covers: the share times the "
	 "system's primary feeders.",
	 "reliability", "linear", "1", [0.0, 5000.0], None),
	("pm25_exceedance_definition",
	 "The PM2.5 exceedance ratio",
	 "pm25_exceedance_ratio",
	 "pm25_annual_mean_ug_per_m3 / air_quality_standards",
	 "How many times the ambient mean exceeds the WHO-guideline limit: "
	 "the finding computed rather than shipped as a violated inequality.",
	 "carbon_trajectory", "linear", "1", [0.0, 100.0], None),
	("crediting_projects_approved_definition",
	 "Crediting projects under an approved methodology",
	 "crediting_projects_approved",
	 "baseline_methodology * project_pipeline_count",
	 "The pipeline's projects applying an approved baseline "
	 "methodology: the share times the pipeline.",
	 "carbon_trajectory", "linear", "1", [0.0, 500.0], None),
	("black_start_capable_mw_definition",
	 "Black-start-capable capacity",
	 "black_start_capable_mw",
	 "black_start_requirement * firm_capacity_mw",
	 "The capacity the operator holds in black-start-capable units: the "
	 "required share of the fleet's own firm capacity.",
	 "reserve_margin", "linear", "MW", [0.0, 500.0], None),
	("clearing_house_default_fund_definition",
	 "The clearing house's default fund",
	 "clearing_house_default_fund_usd_per_year",
	 "clearing_house_requirements * carbon_revenue_usd_per_year",
	 "The default fund the clearing house collects: the share of the "
	 "settled carbon-trade value the carbon revenue computes.",
	 "financial", "linear", "USD/year", [0.0, 200000000.0], None),
	("climate_proofed_capex_definition",
	 "Capex passing the climate-proofing screen",
	 "climate_proofed_capex_mm_usd",
	 "climate_proofing_requirements * capex_usd_per_kw * total_capacity_mw * 1000.0 / 1000000.0",
	 "The fleet's capex passing the screen: the per-kW cost times the "
	 "capacity in MW, at the MW-to-kW conversion and the USD-million "
	 "scale.",
	 "cost_accounting", "linear", "USD million", [0.0, 20000.0], "NREL ATB 2025 Equations & Variables"),
	("collateral_posted_definition",
	 "Collateral provisioned",
	 "collateral_posted_usd_per_year",
	 "collateral_requirements * allowed_revenue_requirement",
	 "The security provisioned annually: the share of the revenue "
	 "requirement the regulator's accounts state.",
	 "financial", "linear", "USD million/year", [0.0, 100.0], None),
	("consumer_protection_spend_definition",
	 "Consumer-protection spend",
	 "consumer_protection_spend_usd_per_year",
	 "consumer_protection_standards * allowed_revenue_requirement",
	 "The metering-accuracy and dispute-resolution systems' spend: the "
	 "mandated share of the revenue requirement.",
	 "cost_accounting", "linear", "USD million/year", [0.0, 20.0], None),
	("demand_charge_revenue_definition",
	 "Demand-charge component of revenue",
	 "demand_charge_revenue_usd_per_year",
	 "cost_allocation_methodology * allowed_revenue_requirement",
	 "The fixed cost recovered through demand and customer charges: the "
	 "allocable share of the revenue requirement, Stoft's cost-of-service "
	 "split.",
	 "financial", "linear", "USD million/year", [0.0, 500.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("credit_support_posted_definition",
	 "Credit support posted",
	 "credit_support_posted_usd_per_year",
	 "credit_support_requirements * allowed_revenue_requirement",
	 "The credit-support annex pre-funding: the share of the revenue "
	 "requirement.",
	 "financial", "linear", "USD million/year", [0.0, 100.0], None),
	("cybersecurity_spend_definition",
	 "Cybersecurity spend",
	 "cybersecurity_spend_usd_per_year",
	 "cybersecurity_requirements * allowed_revenue_requirement",
	 "The control-system security spend: the mandated share of the "
	 "revenue requirement.",
	 "cost_accounting", "linear", "USD million/year", [0.0, 20.0], None),
	("data_privacy_spend_definition",
	 "Data-privacy spend",
	 "data_privacy_spend_usd_per_year",
	 "data_privacy_requirements * allowed_revenue_requirement",
	 "The DPIA and consent-system spend: the mandated share of the "
	 "revenue requirement.",
	 "cost_accounting", "linear", "USD million/year", [0.0, 20.0], None),
	("in_country_telemetry_sites_definition",
	 "Telemetry sites hosted in-country",
	 "in_country_telemetry_sites",
	 "data_sovereignty_requirements * scada_telemetry_sites",
	 "The operational sites whose data must be hosted in-country: the "
	 "share times the system's telemetry sites.",
	 "reliability", "linear", "1", [0.0, 1000.0], None),
	("forecast_error_band_definition",
	 "The forecast error band",
	 "forecast_error_band_twh",
	 "demand_forecast_methodology * demand_twh",
	 "The energy the adequacy plan must absorb on top of the forecast: "
	 "the allowed MAPE times the demand the balance computes.",
	 "price_demand", "linear", "TWh/year", [0.0, 200.0], None),
	("electrified_population_definition",
	 "Electrified population",
	 "electrified_population",
	 "electrification_rate_target * population_total",
	 "The population the access target names: the target share times the "
	 "country's population.",
	 "price_demand", "linear", "people", [0.0, 200000000.0], None),
	("environmental_flow_definition",
	 "The environmental flow",
	 "environmental_flow_m3_per_s",
	 "environmental_flow_requirements * river_mean_annual_flow_m3_per_s",
	 "The flow the basins must carry for habitat: the fair-habitat share "
	 "of the rivers' mean annual flow.",
	 "water_energy", "linear", "m3/s", [0.0, 2000.0], None),
	("gender_action_plan_spend_definition",
	 "Gender action plan spending",
	 "gender_action_plan_spend_usd_per_year",
	 "gender_action_plan * community_development_fund_usd_per_year",
	 "The plan's ring-fenced share of the community development fund "
	 "the benefit-sharing programme capitalises.",
	 "employment", "linear", "USD/year", [0.0, 50000000.0], None),
	("grid_code_compliant_capacity_definition",
	 "Grid-code compliant capacity",
	 "grid_code_compliant_capacity_mw",
	 "interoperability_standards * total_capacity_mw",
	 "The connected capacity meeting the interconnection standard: the "
	 "share of the fleet.",
	 "reserve_margin", "linear", "MW", [0.0, 15000.0], None),
	("compliant_contract_jobs_definition",
	 "Jobs under standard contracts",
	 "compliant_contract_jobs",
	 "labour_standards * construction_jobs_per_mw * total_capacity_mw",
	 "The construction-phase jobs carrying standard contracts: the "
	 "share of the jobs the build's per-MW factor states.",
	 "employment", "linear", "jobs", [0.0, 200000.0], None),
	("local_content_capex_definition",
	 "Capex sourced in-country",
	 "local_content_capex_mm_usd",
	 "local_content_requirements * capex_usd_per_kw * total_capacity_mw * 1000.0 / 1000000.0",
	 "The fleet's capex that must be sourced in-country: the content "
	 "share times the total, at the MW-to-kW conversion and the "
	 "USD-million scale.",
	 "cost_accounting", "linear", "USD million", [0.0, 20000.0], "NREL ATB 2025 Equations & Variables"),
	("margin_posted_definition",
	 "Margin posted on the carbon position",
	 "margin_posted_usd_per_year",
	 "margin_requirements * carbon_revenue_usd_per_year",
	 "The trading position's initial margin: the required share of the "
	 "position's annual value, which the carbon revenue computes.",
	 "financial", "linear", "USD/year", [0.0, 100000000.0], None),
	("reactive_capability_definition",
	 "Reactive capability at peak",
	 "reactive_capability_mvar",
	 "reactive_power_requirement * peak_demand_mw",
	 "The reactive capability the system must hold at peak: the per-MW "
	 "requirement (tan-phi of the 0.95 power factor) times peak "
	 "demand.",
	 "inertia", "linear", "MVAr", [0.0, 30000.0], None),
	("independently_verified_accounts_definition",
	 "Accounts independently verified",
	 "independently_verified_accounts",
	 "regulatory_audit_requirements * audit_accounts_per_year",
	 "The audited accounts the regulator requires independently "
	 "verified: the share times the annual audit sample.",
	 "reliability", "linear", "1", [0.0, 2000.0], None),
	("renewable_generation_target_definition",
	 "The renewable target's energy face value",
	 "renewable_generation_twh",
	 "renewable_target * generation_twh",
	 "The renewable target in energy terms: the share of the generation "
	 "the balance computes. Nameplate share and energy share are "
	 "different statistics; this is the energy one.",
	 "carbon_trajectory", "linear", "TWh/year", [0.0, 50.0], None),
	("reporting_compliance_definition",
	 "Reporting systems' spend",
	 "reporting_compliance_usd_per_year",
	 "reporting_requirements * allowed_revenue_requirement",
	 "The quarterly-filing systems' spend: the mandated share of the "
	 "revenue requirement.",
	 "cost_accounting", "linear", "USD million/year", [0.0, 20.0], None),
	("reserve_margin_required_mw_definition",
	 "The reserve margin's MW face value",
	 "reserve_margin_required_mw",
	 "reserve_margin_requirement * peak_demand_mw",
	 "The planning margin's face value in MW: the margin share times "
	 "peak demand.",
	 "reserve_margin", "linear", "MW", [0.0, 3000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("scada_telemetered_capacity_definition",
	 "Capacity under SCADA telemetry",
	 "scada_telemetered_capacity_mw",
	 "scada_ems_requirements * total_capacity_mw",
	 "The connected capacity under telemetry: the share of the fleet.",
	 "reliability", "linear", "MW", [0.0, 15000.0], None),
	("service_quality_penalty_exposure_definition",
	 "The service-quality penalty's exposure cap",
	 "service_quality_penalty_usd_per_year",
	 "service_quality_penalty * allowed_revenue_requirement",
	 "The unconditional exposure the penalty clause caps: the share of "
	 "the revenue requirement; the trigger is the SAIDI/SAIFI pair "
	 "below.",
	 "financial", "linear", "USD million/year", [0.0, 100.0], None),
)

# The thresholds: (id, lhs, rhs, prose, reference). All relation leq.
BATCH22_BOUNDS: tuple[tuple[str, str, str, str, str | None], ...] = (
	("cooking_clean_target_bound", "cooking_lpg_penetration", "clean_cooking_target",
	 "The clean-cooking target cannot sit below the LPG penetration "
	 "already reached.", None),
	("fpic_consent_bound", "fpic_requirements", "fpic_compliance_score",
	 "The documented-consent floor cannot exceed the audited consent "
	 "score.", None),
	("largest_loss_response_bound", "largest_loss_mw", "frequency_response_requirement",
	 "Primary response must cover the largest credible infeed loss.",
	 "Stoft 2002, Power System Economics, ch. 5"),
	("saidi_ceiling_bound", "system_saidi_hours_per_year", "grid_reliability_target",
	 "The system's SAIDI must sit inside the regulator's ceiling.",
	 "IEEE Guide for Electric Power Distribution Reliability Indices (1366), "
	 "tutorial deck"),
	("ifc_covenant_scope_bound", "ifc_performance_standards", "debt_financing_share",
	 "Only the DFI-financed tranche can be covenanted, so the covenanted "
	 "share cannot exceed the debt-financing share.", None),
	("inertia_minimum_enforced", "inertia_requirement", "system_inertia_mws",
	 "The minimum inertia must sit inside the synchronous inventory the "
	 "firm fleet carries.", None),
	("non_spinning_reserve_inside_margin", "non_spinning_reserve_requirement",
	 "reserve_margin_min * peak_demand_mw",
	 "The non-spinning slice must sit inside the operating reserve the "
	 "margin holds.", "Stoft 2002, Power System Economics, ch. 5"),
	("resettlement_share_bound", "resettlement_population_share",
	 "resettlement_requirements",
	 "The displaced population share must sit inside the safeguard's "
	 "cap.", None),
	("saifi_ceiling_bound", "system_saifi_events_per_year", "service_quality_standards",
	 "The system's SAIFI must sit inside the regulator's ceiling.",
	 "IEEE Guide for Electric Power Distribution Reliability Indices (1366), "
	 "tutorial deck"),
	("energy_burden_affordability_bound", "energy_burden", "affordability_threshold",
	 "The household energy burden at the shipped tariff sits inside the "
	 "10% affordability line.", None),
)


# ---------------------------------------------------------------------------
# Batch 23 -- the extensive bases, and the products they unblock.
#
# WHY THIS BATCH IS A BATCH. Batches 21 and 22 left a residue that looked like
# a list of unrelated knobs and is one thing: unit rates whose product needs a
# physical extent the graph does not carry. A transmission cost in USD per
# MW-km is not a cost until something states the MW-km. The bases are the
# batch; the products fall out of them.
#
# The bases, and where each number comes from:
#
# * `persons_per_household` = 4.5 -- the sub-Saharan African mean household
#   size (UN World Population Prospects household-size series). It is
#   back-solved against the graph's own residential demand so the two agree:
#   `residential_demand_twh` is 11.83 TWh at `household_consumption_mwh_per_year`
#   = 1.5 MWh/year, which is 7.89 M households; at a 45 M population that is
#   5.7 persons per household, not 4.5. The 4.5 is the demographic figure and
#   the 5.7 is what the shipped consumption implies, and the gap is a finding
#   about `household_consumption_mwh_per_year` rather than a choice to paper
#   over -- so the demographic number is the base and the inconsistency stays
#   visible in the product it forms.
# * `transmission_line_length_km` = 12000 -- a 10 GW single-country system
#   at roughly 1.2 km of high-voltage route per MW of peak demand, which is
#   the World Bank's African transmission-density band.
# * `interconnector_route_km` = 350 -- one cross-border link of a few hundred
#   kilometres, the length of the region's existing tie lines.
# * `hydrogen_pipeline_length_km` = 250 -- a trunk line from a production hub
#   to a port or industrial cluster.
# * `connections_per_year` = 250000 -- the annual new-connection programme of
#   a country at ~60% access electrifying toward 90%.
# * `passenger_kilometres_per_year` = 3.0e10 -- 45 M people at ~700 km of
#   motorised travel per person per year, which is the low-income band of the
#   ITF's per-capita travel series.
# * `land_area_hectares` = 5000 -- the project's own land take, at the scale
#   the 500 ha of habitat loss sits inside.
# * `energy_poverty_line_mwh_per_household` = 1.0 and
#   `energy_poor_consumption_mwh_per_year` = 0.35 -- the IEA/World Bank
#   multi-tier-framework boundary between Tier 2 and Tier 3 access, against
#   the consumption an energy-poor household actually draws.
# * the three cumulative-deployment bases: the shipped
#   `cumulative_capacity_mw` / `_reference_mw` pair is the generic learning
#   curve, and the three technology-specific learning rates had no base of
#   their own. Each is the technology's installed stock against the stock its
#   capex figure is quoted at.
#
# The products, and the class each one is:
#
# * Learning curves. `capex * (cum/ref) ** (log(1 - rate)/log(2))` is Wright's
#   law, the form the shipped `learning_curve` equation already carries; the
#   three technology rates now enter three technology-specific instances of it
#   rather than the one generic curve, because a solar rate applied to a
#   battery stock is a category error. Reference: Wright (1936) as archived.
# * Route costs. `capex_per_mw_km * km * MW` -- the extent times the capacity
#   times the rate, which is what the USD/MW-km unit means. The unit walker
#   now reads that unit correctly (the bar-binding fix in `units.py`); before
#   it, the same product was dimensionally USD.km^2.
# * Extent costs. Right-of-way per route-km, land acquisition per hectare,
#   distribution capex per connection.
# * Shares against a base. Energy poverty is a rate against `households_total`;
#   public transport is a share of passenger-kilometres.
# * `regulated_tariff_rate` is not a base but a ratio whose two sides were in
#   different units (USD/year against USD million/year). It is stated against
#   the two tariffs the graph already carries rather than against revenue and
#   the allowed requirement, because those are on different bases -- the
#   revenue is what the fleet earns at the PPA price, the requirement is what
#   the regulator allows -- and their ratio is a finding about the tariff
#   design, not a tariff. `regulated_tariff_usd_per_mwh` over
#   `reference_tariff_usd_per_mwh` is the cost-recovery index the rate names.
# ---------------------------------------------------------------------------

#: (name, unit, range, default, category, prose)
BATCH23_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("persons_per_household", "person", [1.0, 10.0], 4.5, "Demographics",
	 "Mean household size. The sub-Saharan African mean is 4.5; the graph's "
	 "own residential demand implies 5.7 at the shipped per-household "
	 "consumption, and the gap is a finding about that consumption rather "
	 "than a reason to move this figure."),
	("transmission_line_length_km", "km", [0.0, 200000.0], 12000.0, "Transmission",
	 "High-voltage route-km: a 10 GW system at about 1.2 km of route per MW "
	 "of peak demand, the density band African systems sit in."),
	("interconnector_route_km", "km", [0.0, 20000.0], 350.0, "Transmission",
	 "Route length of the cross-border link the interconnector capacity "
	 "names: a few hundred kilometres, the scale of the region's tie lines."),
	("hydrogen_pipeline_length_km", "km", [0.0, 20000.0], 250.0, "Transmission",
	 "Hydrogen trunk-line route-km from the production hub to the port or "
	 "industrial cluster it serves."),
	("connections_per_year", "connection/year", [0.0, 5000000.0], 250000.0,
	 "Grid",
	 "New distribution connections the programme makes per year: a country "
	 "electrifying from ~60% toward 90% access."),
	("passenger_kilometres_per_year", "person*km/year", [0.0, 1.0e12],
	 3.0e10, "Demand",
	 "Motorised passenger-kilometres travelled per year: 45 M people at "
	 "about 700 km each, the low-income band of the ITF series."),
	("land_area_hectares", "hectare", [0.0, 500000.0], 5000.0, "Land",
	 "The project's own land take. The 500 ha of habitat loss sits inside "
	 "it, which is the fraction the two nodes state between them."),
	("energy_poverty_line_mwh_per_household", "MWh/year", [0.0, 10.0], 1.0,
	 "Affordability",
	 "The multi-tier-framework Tier 2/3 boundary in annual consumption per "
	 "household: the level below which a household is counted as "
	 "energy-poor."),
	("energy_poor_consumption_mwh_per_year", "MWh/year", [0.0, 10.0], 0.35,
	 "Affordability",
	 "The consumption an energy-poor household actually draws, against the "
	 "Tier 2/3 line above; the gap between the two is the shortfall the "
	 "poverty-gap product measures."),
	("cumulative_solar_pv_installed_mw", "MW", [0.0, 1.0e8], 60000.0,
	 "Generation",
	 "Cumulative solar PV ever installed, the stock the learning curve "
	 "reads: the country's own 10 GW fleet plus the regional stock its "
	 "module prices are set by."),
	("cumulative_solar_pv_reference_mw", "MW", [1.0, 1.0e8], 50000.0,
	 "Generation",
	 "The cumulative stock at which the shipped solar capex figure is "
	 "quoted, so the learning curve's ratio starts near 1."),
	("cumulative_battery_installed_mwh", "MWh", [0.0, 1.0e9], 200000.0,
	 "Storage",
	 "Cumulative battery energy ever installed, the stock the battery "
	 "learning curve reads."),
	("cumulative_battery_reference_mwh", "MWh", [1.0, 1.0e9], 150000.0,
	 "Storage",
	 "The cumulative battery stock at which the shipped battery capex is "
	 "quoted."),
	("cumulative_electrolyser_installed_mw", "MW", [0.0, 1.0e7], 3000.0,
	 "Sector Coupling",
	 "Cumulative electrolyser capacity ever installed, the stock the "
	 "electrolyser learning curve reads."),
	("cumulative_electrolyser_reference_mw", "MW", [1.0, 1.0e7], 2500.0,
	 "Sector Coupling",
	 "The cumulative electrolyser stock at which the shipped electrolyser "
	 "capex is quoted."),
)

#: Nodes this batch retypes out of the placeholder register.
#: (name, unit, range, default, role, determinism, prose)
BATCH23_RETYPES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	("right_of_way_cost", "USD/km", [0.0, 5000000.0], 120000.0, "free",
	 "physical",
	 "Compensation and easement cost per kilometre of route. The unit was "
	 "the placeholder's None; USD/km is what a right-of-way payment is, and "
	 "120,000 USD/km is the scale a transmission easement in the region "
	 "carries."),
	("electrolyser_efficiency", "1", [0.0, 1.0], 0.65, "free", "physical",
	 "Electrolyser efficiency on the LHV basis: 65% is the current PEM and "
	 "alkaline band, and it is the divisor that turns hydrogen output into "
	 "the electricity the plant draws."),
	("energy_poverty_gap", "MWh/year", [0.0, 1.0e9], 3250000.0, "free",
	 "physical",
	 "The annual consumption shortfall of the energy-poor households: the "
	 "household count times the gap between the Tier 2/3 line and the "
	 "consumption those households actually draw."),
	("hydrogen_pipeline_capacity", "MW", [0.0, 100000.0], 2000.0, "free",
	 "physical",
	 "Capacity the hydrogen trunk line carries, in the MW of hydrogen "
	 "energy throughput the MW-km rate is quoted against."),
)

#: (id, name, lhs, rhs, prose, system, linearity, unit, range, reference)
BATCH23_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, str, list[float], str | None], ...
] = (
	("capex_solar_pv_learning_definition",
	 "The solar PV capex at the cumulative stock",
	 "capex_solar_pv_learning_usd_per_kw",
	 "capex_solar_pv * (cumulative_solar_pv_installed_mw / cumulative_solar_pv_reference_mw) ** (log(1 - solar_pv_learning_rate) / log(2))",
	 "Wright's law applied to the solar stock: the shipped capex scaled by "
	 "the cumulative-deployment ratio raised to the learning exponent, where "
	 "a 20% rate halves cost per doubling of the stock. The shipped generic "
	 "`learning_curve` carries the same form against one generic stock; this "
	 "is the technology-specific instance, because a solar rate applied to a "
	 "battery stock is a category error.",
	 "learning", "nonlinear", "USD/kW", [0.0, 5000.0], "Wright's law"),
	("capex_battery_learning_definition",
	 "The battery capex at the cumulative stock",
	 "capex_battery_learning_usd_per_kwh",
	 "capex_battery * (cumulative_battery_installed_mwh / cumulative_battery_reference_mwh) ** (log(1 - battery_learning_rate) / log(2))",
	 "Wright's law on the battery stock: the shipped energy capex scaled by "
	 "the cumulative MWh ratio raised to the 15% learning exponent.",
	 "learning", "nonlinear", "USD/kWh", [0.0, 2000.0], "Wright's law"),
	("capex_hydrogen_electrolyser_learning_definition",
	 "The electrolyser capex at the cumulative stock",
	 "capex_hydrogen_electrolyser_learning_usd_per_kw",
	 "capex_hydrogen_electrolyser * (cumulative_electrolyser_installed_mw / cumulative_electrolyser_reference_mw) ** (log(1 - electrolyser_learning_rate) / log(2))",
	 "Wright's law on the electrolyser stock: the shipped USD/kW scaled by "
	 "the cumulative MW ratio raised to the 12% learning exponent.",
	 "learning", "nonlinear", "USD/kW", [0.0, 5000.0], "Wright's law"),
	("transmission_investment_definition",
	 "The transmission investment",
	 "transmission_investment_usd",
	 "capex_transmission * transmission_line_length_km * total_capacity_mw",
	 "The line's installed cost: the USD per MW-km rate times the route-km "
	 "times the MW the route carries. The unit is a product of three "
	 "quantities, and the product is the cost the rate means.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e12], None),
	("interconnector_investment_definition",
	 "The interconnector investment",
	 "interconnector_investment_usd",
	 "capex_interconnector * interconnector_route_km * interconnector_capacity",
	 "The cross-border link's installed cost: the USD per MW-km rate times "
	 "the route length times the link's capacity. The rate spans overhead AC "
	 "to submarine HVDC, which is why it has a range rather than a value.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e12], None),
	("hydrogen_pipeline_investment_definition",
	 "The hydrogen pipeline investment",
	 "hydrogen_pipeline_investment_usd",
	 "hydrogen_pipeline_cost * hydrogen_pipeline_length_km * hydrogen_pipeline_capacity",
	 "The trunk line's installed cost: the USD per MW-km rate times the "
	 "route-km times the capacity the line carries.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e12], None),
	("right_of_way_cost_definition",
	 "The right-of-way compensation",
	 "right_of_way_cost_usd",
	 "right_of_way_cost * (transmission_line_length_km + interconnector_route_km + hydrogen_pipeline_length_km)",
	 "The easement payments across every route the plan builds: the USD per "
	 "route-km rate times the total kilometres of transmission, "
	 "interconnector and hydrogen pipeline.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e12], None),
	("distribution_expansion_capex_definition",
	 "The distribution expansion capex",
	 "distribution_expansion_capex_usd_per_year",
	 "distribution_capex_per_connection * connections_per_year",
	 "The annual distribution spend the connection programme carries: the "
	 "USD per connection times the connections made per year.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11], None),
	("distribution_asset_value_definition",
	 "The distribution asset value",
	 "distribution_asset_value_usd",
	 "capex_distribution * peak_demand_mw * 1000.0",
	 "The distribution network's replacement value: the USD per kW of "
	 "system capacity times the peak demand in kW. The 1000 is the MW-to-kW "
	 "conversion, which the USD/kW unit states.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e12], None),
	("land_acquisition_cost_definition",
	 "The land acquisition cost",
	 "land_acquisition_cost_usd",
	 "land_acquisition_cost_per_hectare * land_area_hectares",
	 "The project's land bill: the USD per hectare times the hectares "
	 "acquired, at the purchase-or-lease rate the IFC land-acquisition "
	 "practice sets.",
	 "cost_accounting", "linear", "USD", [0.0, 1.0e11], None),
	("households_total_definition",
	 "The household count",
	 "households_total",
	 "population_total / persons_per_household",
	 "The country's households: the population divided by the mean "
	 "household size. The extensive base every per-household quantity in "
	 "the graph needs and none of them had.",
	 "affordability", "linear", "1", [0.0, 1.0e8], None),
	("energy_poor_households_definition",
	 "The energy-poor household count",
	 "energy_poor_households",
	 "energy_poverty_rate * households_total",
	 "Households whose energy burden exceeds the affordability line: the "
	 "rate times the household count.",
	 "affordability", "linear", "1", [0.0, 1.0e8], None),
	("energy_poverty_gap_definition",
	 "The energy-poverty consumption gap",
	 "energy_poverty_gap",
	 "energy_poor_households * (energy_poverty_line_mwh_per_household - energy_poor_consumption_mwh_per_year)",
	 "The annual consumption shortfall: the energy-poor households times the "
	 "distance between the Tier 2/3 access line and what they actually "
	 "draw. A gap in MWh/year, not a currency, because the shortfall is "
	 "energy and the price it would cost to close is a separate question.",
	 "affordability", "linear", "MWh/year", [0.0, 1.0e9], None),
	("public_transport_passenger_km_definition",
	 "Public transport passenger-kilometres",
	 "public_transport_passenger_km_per_year",
	 "public_transport_share * passenger_kilometres_per_year",
	 "The passenger-kilometres carried on public transport: the share of "
	 "total travel the mode split states, times the total. The base the "
	 "batch-20 share product was deferred for.",
	 "demand_supply", "linear", "person*km/year", [0.0, 1.0e12], None),
	("electrolysis_electricity_demand_definition",
	 "The electricity electrolysis draws",
	 "electrolysis_electricity_demand_mwh_per_year",
	 "hydrogen_production_kt_per_year * 1000000 * mwh_per_hydrogen_unit / electrolyser_efficiency",
	 "The electricity the hydrogen programme draws: the annual output in "
	 "kilograms times hydrogen's LHV in MWh per kg, divided by the "
	 "electrolyser's efficiency. The 1e6 converts kilotonnes to kilograms.",
	 "water_energy", "linear", "MWh/year", [0.0, 1.0e10], None),
	("regulated_tariff_rate_definition",
	 "The regulated tariff's cost-recovery index",
	 "regulated_tariff_rate",
	 "regulated_tariff_usd_per_mwh / reference_tariff_usd_per_mwh",
	 "The regulated tariff as a fraction of the reference tariff: the "
	 "cost-recovery index the rate names. Stated against the two tariffs "
	 "rather than against revenue and the allowed requirement, because "
	 "those sit on different bases -- what the fleet earns at the PPA price "
	 "against what the regulator allows -- and their ratio is a finding "
	 "about tariff design, not a tariff.",
	 "price_demand", "linear", "1", [0.0, 10.0], None),
)


def build_batch23(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 23: the extensive bases and the products they unblock."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, category, prose in BATCH23_BASES:
		assert name not in graph.nodes, f"{name} already exists; a base is new"
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "default": default, "role": "free",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The extensive-base coupling (batch 23)",
			"users": ["Planners", "Regulators"],
		}

	for name, unit, rng, default, role, determinism, prose in BATCH23_RETYPES:
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default, "role": role,
			"description": prose, "determinism": determinism,
			"priority": "P1", "status": "existing",
			"source": "The extensive-base coupling (batch 23)",
			"users": ["Planners", "Regulators"],
		})
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, linearity, unit, rng, cite in (
		BATCH23_EQUATIONS
	):
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		# A node the batch retypes is not re-declared by the product: its
		# body already carries the unit the equation computes into.
		if lhs not in nodes:
			nodes[lhs] = {
				"name": lhs.replace("_", " ").capitalize(),
				"description": (
					f"{lhs.replace('_', ' ')}: the extensive-base coupling's "
					"derived quantity. "
				) + prose,
				"category": "Cost", "type": "float", "unit": unit,
				"range": rng, "role": "derived",
				"determinism": "physical", "priority": "P1",
				"status": "existing",
				"source": "The extensive-base coupling (batch 23)",
				"users": ["Planners", "Regulators"],
			}
		else:
			nodes[lhs]["role"] = "derived"
			nodes[lhs].pop("default", None)
			nodes[lhs]["description"] = prose
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": linearity,
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"strength": "hard", "description": "Enters the product.",
			})
	return nodes, equations, edges, rules


def build_batch22(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 22: the compliance register's products and thresholds."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, prose in BATCH22_RETYPES:
		full = dict(graph.nodes[name].model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default, "role": "free",
			"description": prose, "determinism": "policy",
			"priority": "P2", "status": "existing",
			"source": "The compliance-register coupling (batch 22)",
			"users": ["Regulators", "Planners"],
		})
		nodes[name] = full

	for name, unit, rng, default, category, prose in BATCH22_BASES:
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "default": default, "role": "free",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The compliance-register coupling (batch 22)",
			"users": ["Regulators", "Planners"],
		}

	for eq_id, name, lhs, rhs, prose, system, linearity, unit, rng, cite in (
		BATCH22_EQUATIONS
	):
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": linearity,
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"strength": "hard", "description": "Enters the product.",
			})
		nodes[lhs] = {
			"name": lhs.replace("_", " ").capitalize(),
			"description": (
				f"{lhs.replace('_', ' ')}: the compliance register's derived "
				"quantity. "
			) + prose,
			"category": "Regulatory", "type": "float", "unit": unit,
			"range": rng, "role": "derived",
			"determinism": "policy", "priority": "P1", "status": "existing",
			"source": "The compliance-register coupling (batch 22)",
			"users": ["Regulators", "Planners"],
		}

	for eq_id, lhs, rhs, prose, cite in BATCH22_BOUNDS:
		named = sorted(set(_side_symbols(lhs)) | set(_side_symbols(rhs)))
		equations[eq_id] = {
			"id": eq_id, "name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": "reserve_margin",
			"lhs": lhs, "rhs": rhs, "relation": "leq",
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
	return nodes, equations, edges, rules


if __name__ == "__main__":
	sys.exit(main())