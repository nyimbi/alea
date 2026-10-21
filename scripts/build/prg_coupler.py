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
	tables: dict[str, dict[str, Any]] = {"12": BATCH12_NODES, "13": {}, "14": {}, "15": {}, "16": {}, "17": {}, "18": {}, "19": {}, "20": {}, "21": {}, "22": {}, "23": {}, "24": {}, "25": {}, "26": {}, "27": {}, "28": {}, "29": {}, "30": {}, "31": {}, "32": {}, "33": {}, "34": {}, "35": {}, "36": {}, "37": {}, "38": {}, "39": {}, "40": {}}
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
	elif batch == "28":
		b28_nodes, b28_equations, b28_edges, b28_rules = build_batch28(graph)
		rules.extend(b28_rules)
		nodes.update(b28_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b28_equations)
		edges = list(BATCH12_EDGES) + b28_edges
	elif batch == "29":
		b29_nodes, b29_equations, b29_edges, b29_rules = build_batch29(graph)
		rules.extend(b29_rules)
		nodes.update(b29_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b29_equations)
		edges = list(BATCH12_EDGES) + b29_edges
	elif batch == "34":
		b34_nodes, b34_equations, b34_edges, b34_rules = build_batch34(graph)
		rules.extend(b34_rules)
		nodes.update(b34_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b34_equations)
		edges = list(BATCH12_EDGES) + b34_edges
	elif batch == "40":
		b40_nodes, b40_equations, b40_edges, b40_rules = build_batch40(graph)
		rules.extend(b40_rules)
		nodes.update(b40_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b40_equations)
		edges = list(BATCH12_EDGES) + b40_edges
	elif batch == "39":
		b39_nodes, b39_equations, b39_edges, b39_rules = build_batch39(graph)
		rules.extend(b39_rules)
		nodes.update(b39_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b39_equations)
		edges = list(BATCH12_EDGES) + b39_edges
	elif batch == "38":
		b38_nodes, b38_equations, b38_edges, b38_rules = build_batch38(graph)
		rules.extend(b38_rules)
		nodes.update(b38_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b38_equations)
		edges = list(BATCH12_EDGES) + b38_edges
	elif batch == "37":
		b37_nodes, b37_equations, b37_edges, b37_rules = build_batch37(graph)
		rules.extend(b37_rules)
		nodes.update(b37_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b37_equations)
		edges = list(BATCH12_EDGES) + b37_edges
	elif batch == "36":
		b36_nodes, b36_equations, b36_edges, b36_rules = build_batch36(graph)
		rules.extend(b36_rules)
		nodes.update(b36_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b36_equations)
		edges = list(BATCH12_EDGES) + b36_edges
	elif batch == "35":
		b35_nodes, b35_equations, b35_edges, b35_rules = build_batch35(graph)
		rules.extend(b35_rules)
		nodes.update(b35_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b35_equations)
		edges = list(BATCH12_EDGES) + b35_edges
	elif batch == "33":
		b33_nodes, b33_equations, b33_edges, b33_rules = build_batch33(graph)
		rules.extend(b33_rules)
		nodes.update(b33_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b33_equations)
		edges = list(BATCH12_EDGES) + b33_edges
	elif batch == "32":
		b32_nodes, b32_equations, b32_edges, b32_rules = build_batch32(graph)
		rules.extend(b32_rules)
		nodes.update(b32_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b32_equations)
		edges = list(BATCH12_EDGES) + b32_edges
	elif batch == "31":
		b31_nodes, b31_equations, b31_edges, b31_rules = build_batch31(graph)
		rules.extend(b31_rules)
		nodes.update(b31_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b31_equations)
		edges = list(BATCH12_EDGES) + b31_edges
	elif batch == "30":
		b30_nodes, b30_equations, b30_edges, b30_rules = build_batch30(graph)
		rules.extend(b30_rules)
		nodes.update(b30_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b30_equations)
		edges = list(BATCH12_EDGES) + b30_edges
	elif batch == "27":
		b27_nodes, b27_equations, b27_edges, b27_rules = build_batch27(graph)
		rules.extend(b27_rules)
		nodes.update(b27_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b27_equations)
		edges = list(BATCH12_EDGES) + b27_edges
	elif batch == "26":
		b26_nodes, b26_equations, b26_edges, b26_rules = build_batch26(graph)
		rules.extend(b26_rules)
		nodes.update(b26_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b26_equations)
		edges = list(BATCH12_EDGES) + b26_edges
	elif batch == "25":
		b25_nodes, b25_equations, b25_edges, b25_rules = build_batch25(graph)
		rules.extend(b25_rules)
		nodes.update(b25_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b25_equations)
		edges = list(BATCH12_EDGES) + b25_edges
	elif batch == "24":
		b24_nodes, b24_equations, b24_edges, b24_rules = build_batch24(graph)
		rules.extend(b24_rules)
		nodes.update(b24_nodes)
		equations = {eq["id"]: eq for eq in BATCH12_EQUATIONS}
		equations.update(b24_equations)
		edges = list(BATCH12_EDGES) + b24_edges
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


# ---------------------------------------------------------------------------
# Batch 24 -- the carbon and market families, and the annual-quantity retype
# that makes their products decidable.
#
# WHY THE RETYPE COMES FIRST. Fifteen nodes in the graph are annual
# quantities declared as if they were instantaneous stocks: `demand_twh` is
# "Final demand in the horizon year" and carries `TWh`, `generation_twh` is
# "Energy generated at the busbar" and carries `TWh`, `cooling_water_demand_m3`
# is a year's cooling water and carries `m3`. A rate times a stock is not a
# spend, so every product against them -- the wheeling charges, the feed-in
# tariff, the subsidy spends, the carbon identity itself -- read as
# `USD * TWh / MWh` or as a dimensionless ratio that is not a ratio. Measured
# on a rebuilt graph: retyping these fifteen fixes nine inconsistent equations
# and breaks none. They are the precondition for this batch, not a side
# effect of it.
#
# WHY THE CARBON FAMILY IS WORTH A BATCH. The ETS chain was declared and
# never computed: `ets_cap`, `auction_volume`, `carbon_credit_volumes`,
# `article_6_credits` and `carbon_budget` all sat at the catalog's 500000.0
# placeholder with no unit. Each is now an identity against a quantity the
# graph already derives. Two of them are *duplicates by meaning* rather than
# by name -- `carbon_budget` is `carbon_budget_mtco2` and `price_cap` is
# `revenue_cap` -- and the catalog's own duplicate-resolution convention is an
# equality, so the placeholder becomes derived and the reviewed id survives.
#
# WHY THE GATE IS A RULE AND NOT AN EQUATION. `ets_enabled` is a switch, and
# `carbon_revenue_definition` reads no switch: at the shipped defaults the
# jurisdiction has no ETS and the graph still accrues 650,578,257 USD/year of
# carbon revenue, because the identity multiplies by `carbon_price_coverage`
# (0.5) and never asks whether a market exists. The repair is not to multiply
# the revenue by the flag -- an ETS and a carbon tax are alternative
# instruments over the same base, and `max(ets_enabled, carbon_tax_enabled)`
# would need a `carbon_tax_enabled` node the graph does not carry, while a
# product would double-count the covered share the revenue identity already
# applies. The honest statement is a cross-validation rule: revenue accruing
# with no instrument enabled is a scenario the reviewer should refuse.
#
# WHY THE MARKET FAMILY IS SHARES AGAINST BASES. `wheeling_charges`,
# `feed_in_tariff`, `bid_ask_spread` and their kin were declared with no unit
# and no consumer; each is a *rate per MWh* applied to the annual volume the
# graph already computes, which is the pass-through tariff structure African
# regulators actually publish. `market_liquidity` is the one that is not a
# rate: it is churn, a multiple of demand, and its product is the traded
# volume the bid-ask spread then prices.
# ---------------------------------------------------------------------------

#: (name, unit, range, default, category, determinism, prose)
BATCH24_RETYPES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	# --- the annual-quantity repair (fifteen, measured) ---
	("demand_twh", "TWh/year", [1.0, 20000.0], 46.5, "Demand", "stochastic",
	 "Final demand in the horizon year, after growth is compounded. A flow: "
	 "the TWh consumed *in* the year, so the unit is per-year and a rate "
	 "times it is a spend. The shipped `TWh` made every product against it "
	 "read as an energy stock and left the revenue products undecidable."),
	("base_demand_twh", "TWh/year", [1.0, 10000.0], 33.8, "Demand", "stochastic",
	 "Base-year demand before growth is compounded. A flow, like "
	 "`demand_twh`."),
	("generation_twh", "TWh/year", [0.0, 30000.0], 52.0, "Demand", "physical",
	 "Energy generated at the busbar in the year, which is what clears the "
	 "balance. A flow."),
	("net_imports_twh", "TWh/year", [-1000.0, 1000.0], 0.0, "Demand", "policy",
	 "Imports less exports over the year. A net flow, signed."),
	("equilibrium_demand_twh", "TWh/year", [0.0, 20000.0], 46.5, "Demand",
	 "stochastic",
	 "The demand the price equilibrium settles at. A flow."),
	("agricultural_demand_twh", "TWh/year", [0.0, 20000.0], 0.7, "Demand",
	 "physical", "Agricultural electricity demand in the year. A flow."),
	("commercial_demand_twh", "TWh/year", [0.0, 20000.0], 9.3, "Demand",
	 "physical", "Commercial electricity demand in the year. A flow."),
	("industrial_demand_twh", "TWh/year", [0.0, 20000.0], 17.0, "Demand",
	 "physical", "Industrial electricity demand in the year. A flow."),
	("residential_demand_twh", "TWh/year", [0.0, 20000.0], 19.5, "Demand",
	 "physical", "Residential electricity demand in the year. A flow."),
	("cooling_water_demand_m3", "m3/year", [0.0, 1.0e11], 2.0e8, "Water",
	 "physical",
	 "Cooling water withdrawn in the year. A flow; the shipped `m3` made the "
	 "water balance a stock against a stock and hid the withdrawal rate."),
	("hydrogen_water_demand_m3", "m3/year", [0.0, 1.0e11], 1.5e7, "Water",
	 "physical", "Water the electrolyser draws in the year. A flow."),
	("total_water_demand_m3", "m3/year", [0.0, 1.0e11], 2.3e8, "Water",
	 "physical", "Total water withdrawn in the year. A flow."),
	("water_availability_m3", "m3/year", [0.0, 1.0e11], 2.0e8, "Water",
	 "physical",
	 "Water available to the project in the year. A flow, and the one the "
	 "withdrawal is compared against: a stock compared to a flow is the "
	 "comparison the shipped units made."),
	("unserved_energy_gwh", "GWh/year", [0.0, 1.0e5], 1200.0, "Reliability",
	 "stochastic", "Energy demanded and not served in the year. A flow."),
	("reliability_cost_usd", "USD/year", [0.0, 1.0e12], 4.0e7, "Reliability",
	 "stochastic",
	 "The cost of the unserved energy, valued at the value of lost load. A "
	 "spend in the year."),
	# --- the carbon and market shares that were declared with no unit ---
	("corresponding_adjustment", "1", [0.0, 1.0], 0.8, "Carbon", "policy",
	 "Share of a transferred mitigation outcome carrying a corresponding "
	 "adjustment under Article 6.2 of the Paris Agreement. A share, and the "
	 "unit is what makes the Article-6 volume decidable."),
	("leakage_parameters", "1", [0.0, 1.0], 0.1, "Carbon", "policy",
	 "Share of the covered emissions that relocate rather than abate: the "
	 "carbon-leakage rate a CBAM-style adjustment exists to price. A share."),
	("position_limits", "1", [0.0, 1.0], 0.25, "MktOps", "policy",
	 "Share of the cap one participant may hold. A share of the cap, not an "
	 "absolute volume, so the limit moves with the cap it limits."),
	("netting_agreements", "1", [0.0, 1.0], 0.9, "MktOps", "policy",
	 "Share of posted collateral covered by a netting agreement. A share; "
	 "what remains is the exposure the agreement does not net."),
	("carbon_credit_retirement", "1", [0.0, 1.0], 0.05, "Carbon", "policy",
	 "Share of issued credit volume retired against a compliance obligation. "
	 "A share of the issued volume."),
	("permanence_parameters", "1", [0.0, 1.0], 0.1, "Carbon", "policy",
	 "Reversal allowance on the credit book: the share of issued volume held "
	 "back against non-permanence. A share, and its complement is the buffer "
	 "a registry actually retains."),
	("carbon_credit_insurance", "1", [0.0, 1.0], 0.02, "Carbon", "policy",
	 "Premium on insuring the credit book, as a share of its value. A share "
	 "of the value, which is what makes the premium a spend."),
	("settlement_risk", "1", [0.0, 1.0], 0.01, "MktOps", "policy",
	 "Share of the settled value exposed to counterparty settlement failure. "
	 "A share of the value at risk."),
	("carbon_tax_interaction", "1", [0.0, 1.0], 0.15, "Tax", "policy",
	 "Share of carbon revenue offset by lower other taxes: the tax "
	 "interaction a revenue-neutral reform carries. A share of the revenue."),
	("mini_grid_subsidies", "1", [0.0, 1.0], 0.4, "Policy", "policy",
	 "Share of the mini-grid programme's spend covered by subsidy. A share "
	 "of the spend the graph already derives."),
	("shs_subsidies", "1", [0.0, 1.0], 0.3, "Policy", "policy",
	 "Share of the solar-home-system programme's spend covered by subsidy. A "
	 "share of the spend the graph already derives."),
	("voluntary_carbon_market", "1", [0.0, 1.0], 0.0, "Policy", "policy",
	 "Share of the credit volume sold into the voluntary market rather than "
	 "against a compliance obligation. A participation share; zero at the "
	 "shipped default because the programme is compliance-led."),
	("price_limits", "1", [0.0, 5.0], 0.2, "MktOps", "policy",
	 "Half-width of the market's price band around marginal cost, as a "
	 "fraction of it. A share, and the band's two arms are "
	 "`(1 ± price_limits) * marginal_cost`."),
	("carbon_price_risk", "1", [0.0, 1.0], 0.15, "Macro", "policy",
	 "Risk premium on the escalated carbon price, as a share of it. A share, "
	 "so the risk-adjusted price is `(1 + carbon_price_risk)` times the "
	 "escalated one."),
	("market_liquidity", "1", [0.0, 100.0], 1.0, "MktOps", "policy",
	 "Market churn: the traded volume as a multiple of demand. Dimensionless "
	 "because it is a multiple, and its product is the traded volume the "
	 "spread and the clearing costs are quoted against."),
	# --- the two rate families: USD per MWh applied to an annual volume ---
	("bid_ask_spread", "USD/MWh", [0.0, 100.0], 1.5, "MktOps", "policy",
	 "The bid-ask spread on the traded volume, in USD per MWh traded. A rate; "
	 "the shipped unit was None and the spread is a price, not a share."),
	("wheeling_charges", "USD/MWh", [0.0, 100.0], 4.0, "Policy", "policy",
	 "Transmission wheeling charge per MWh of demand: the use-of-system "
	 "tariff a regulator publishes. A rate against the annual demand."),
	("distribution_wheeling_charges", "USD/MWh", [0.0, 100.0], 6.0, "Policy",
	 "policy",
	 "Distribution wheeling charge per MWh of demand. A rate; the "
	 "distribution use-of-system tariff."),
	("feed_in_tariff", "USD/MWh", [0.0, 500.0], 80.0, "Policy", "policy",
	 "The feed-in tariff paid per MWh of renewable generation: a purchase "
	 "obligation price, not a share. A rate against the renewable volume."),
	("electricity_subsidies", "USD/MWh", [0.0, 500.0], 20.0, "Policy", "policy",
	 "Consumer subsidy per MWh of demand: the gap between the tariff and the "
	 "cost it is meant to recover, paid by the budget. A rate."),
	("renewable_subsidies", "USD/MWh", [0.0, 500.0], 25.0, "Policy", "policy",
	 "Renewable subsidy per MWh of renewable generation, distinct from the "
	 "feed-in tariff because it is a budget transfer rather than a purchase "
	 "obligation. A rate."),
	("fossil_fuel_subsidies", "USD/MWh", [0.0, 500.0], 15.0, "Policy", "policy",
	 "Fossil-fuel subsidy per MWh of non-renewable generation. A rate "
	 "against the fossil volume, which is generation less renewables."),
	("wheeling_charge_cross_border", "USD/MWh", [0.0, 100.0], 8.0, "Grid",
	 "policy",
	 "Cross-border wheeling charge per MWh of net import. A rate against the "
	 "signed net flow, which is why the product takes its absolute value."),
	("carbon_credit_prices", "USD/tonne", [0.0, 500.0], 8.0, "Carbon", "policy",
	 "Price of one tonne of credit on the market the programme sells into: "
	 "the voluntary-market clearing price, distinct from the compliance "
	 "price `carbon_price_usd_per_tco2`. A price per tonne."),
	# --- the duplicates the catalog resolves by equality ---
	("local_employment_targets", "1", [0.0, 1.0], 0.3, "Land", "policy",
	 "Target share of project employment to be filled from the host "
	 "community. A share of the workforce, so the attainment ratio against "
	 "it is a ratio and not a division by the catalog's 500000.0 "
	 "placeholder."),
	("women_employment_targets", "1", [0.0, 1.0], 0.15, "JustTrans", "policy",
	 "Target share of project employment to be filled by women. A share."),
	("youth_employment_targets", "1", [0.0, 1.0], 0.25, "JustTrans", "policy",
	 "Target share of project employment to be filled by people under 35. A "
	 "share."),
	("carbon_tax_coverage", "1", [0.0, 1.0], 0.5, "Policy", "policy",
	 "Share of emissions the carbon tax applies to. Already a share; this "
	 "batch makes it an identity on `carbon_price_coverage`, the two being "
	 "one covered share under two instrument names, which is the catalog's "
	 "own duplicate-resolution convention."),
	("social_tariff", "USD/MWh", [0.0, 500.0], 30.0, "Consumer", "policy",
	 "The social tariff a below-threshold household pays. Already a price "
	 "with no unit; this batch declares the unit and the identity on the "
	 "lifeline tariff the graph already carries, which is the same quantity "
	 "under the catalog's second spelling."),
)

#: The bases this batch needs: one, and it is the traded volume's own churn
#: base. Everything else is a product against a quantity already carried.
BATCH24_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = ()

#: (id, name, lhs, rhs, prose, system, linearity, unit, range, reference)
BATCH24_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, str, list[float], str | None], ...
] = (
	# --- the ETS and Article 6 chain ---
	("ets_cap_definition",
	 "The ETS cap, annualised",
	 "ets_cap",
	 "carbon_price_coverage * carbon_budget_mtco2 / horizon_years",
	 "The covered share of the remaining carbon budget, divided by the "
	 "horizon it is to be spent over: the annual cap a budget implies. At "
	 "the shipped defaults 0.5 * 500 / 10 = 25 MtCO2/year against emissions "
	 "of 26.02, so the cap binds while the whole budget (260.2 against 500) "
	 "does not -- the annualisation is what makes a budget bite.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 10000.0],
	 "EU CBAM regulation"),
	("auction_volume_definition",
	 "The annual auction volume",
	 "auction_volume",
	 "ets_cap",
	 "Every allowance is auctioned, because the graph carries no "
	 "free-allocation share and inventing one would be a policy assumption "
	 "with no dial behind it. The auction volume is therefore the cap; when "
	 "a free-allocation dial arrives, this is the line that gains its "
	 "complement.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 10000.0],
	 "EU CBAM regulation"),
	("carbon_credit_volumes_definition",
	 "The credit volume issued",
	 "carbon_credit_volumes",
	 "additional_abatement_mtco2",
	 "Credit volume is the abatement that clears the additionality screen, "
	 "which the shipped `additional_abatement_definition` already computes "
	 "as the tested share of the annualised budget. Issuing credits for "
	 "anything the screen refused would be crediting a reduction that did "
	 "not happen.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 1000.0], None),
	("article_6_credits_definition",
	 "The Article 6.2 transferred volume",
	 "article_6_credits",
	 "corresponding_adjustment * carbon_credit_volumes",
	 "The volume transferred bilaterally under Article 6.2, which is the "
	 "share carrying a corresponding adjustment: the host country deducts "
	 "it from its own accounting and the buyer adds it to theirs. Without "
	 "the adjustment the transfer is a double count, which is the defect "
	 "Article 6.4's own machinery exists to prevent.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 1000.0],
	 "EU CBAM regulation"),
	("carbon_budget_identity",
	 "The remaining carbon budget",
	 "carbon_budget",
	 "carbon_budget_mtco2",
	 "Two ids for one quantity: the catalog carries `carbon_budget` and the "
	 "constraint register carries `carbon_budget_mtco2`, and they are the "
	 "same budget. Resolved by equality rather than by deleting a reviewed "
	 "id, which is the convention every catalog duplicate in this graph "
	 "follows.",
	 "carbon_trajectory", "linear", "MtCO2", [0.0, 100000.0],
	 "The catalog's own duplicate rows, resolved"),
	# --- the carbon-market products ---
	("leakage_emissions_definition",
	 "The emissions that relocate",
	 "leakage_mtco2_per_year",
	 "leakage_parameters * emissions_mtco2_per_year",
	 "The share of covered emissions that moves production rather than "
	 "abating it: the quantity a border adjustment is calibrated against. "
	 "Leakage is not abatement that failed, it is abatement that left, and "
	 "pricing it at the domestic carbon price is what CBAM does.",
	 "emissions", "linear", "MtCO2/year", [0.0, 1000.0],
	 "EU CBAM regulation"),
	("position_limit_definition",
	 "The volume one participant may hold",
	 "position_limit_mtco2",
	 "position_limits * ets_cap",
	 "A position limit as a share of the cap, not an absolute tonnage: the "
	 "limit a market regulator sets scales with the market it limits. The "
	 "product is the volume, which is what a compliance check compares a "
	 "participant's holding against.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 10000.0],
	 "EU CBAM regulation"),
	("carbon_credit_value_definition",
	 "The value of the credit book",
	 "carbon_credit_value_usd_per_year",
	 "carbon_credit_prices * carbon_credit_volumes * 1000000",
	 "Volume times price, with the 1e6 carrying MtCO2 to tonnes. The price "
	 "is the voluntary-market clearing price, not the compliance price: a "
	 "credit sold into the voluntary market is not an allowance, and "
	 "valuing it at the ETS price would import a market the book does not "
	 "trade in.",
	 "capture_price", "linear", "USD/year", [0.0, 1.0e11], None),
	("carbon_credit_insurance_premium_definition",
	 "The insurance premium on the credit book",
	 "carbon_credit_insurance_cost_usd_per_year",
	 "carbon_credit_insurance * carbon_credit_value_usd_per_year",
	 "The premium as a share of the book's value. Insurance against "
	 "non-delivery is what lets a buyer bank a credit before it vests, so "
	 "the premium is a cost of the timing and not of the tonne.",
	 "capture_price", "linear", "USD/year", [0.0, 1.0e11], None),
	("settlement_risk_exposure_definition",
	 "The settlement exposure",
	 "settlement_risk_exposure_usd_per_year",
	 "settlement_risk * carbon_credit_value_usd_per_year",
	 "The share of the settled value exposed to counterparty failure. A "
	 "share of value rather than of volume, because what a default costs is "
	 "the price already agreed, not the tonnes.",
	 "capture_price", "linear", "USD/year", [0.0, 1.0e11], None),
	("carbon_credit_retirement_definition",
	 "The retired credit volume",
	 "carbon_credit_retired_volume",
	 "carbon_credit_retirement * carbon_credit_volumes",
	 "The share of issued volume surrendered against a compliance "
	 "obligation. Retirement is what makes a credit count once and only "
	 "once; the volume that is not retired remains available to be sold "
	 "again, which is the double-counting the registry prevents.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 1000.0], None),
	("carbon_credit_reversal_allowance_definition",
	 "The reversal allowance on the credit book",
	 "carbon_credit_reversal_allowance",
	 "permanence_parameters * carbon_credit_volumes",
	 "The volume the permanence share sets aside: the allowance a registry "
	 "holds against the credit being reversed by fire, disease or land-use "
	 "change. A forest credit that burns has to be replaced from this "
	 "allowance, and the allowance is sized by the reversal risk the "
	 "permanence share names. The share is the allowance, not its "
	 "complement. `permanence_parameters` describes itself as 'the share "
	 "of issued volume held back against non-permanence', so its "
	 "complement is the volume *not* held back -- the opposite of an "
	 "allowance -- and the shipped form, which multiplied the complement, "
	 "reported 40.5 of 45 MtCO2/year as the buffer. Batch 34 corrected it "
	 "to 4.5, and `buffer_pool_contribution` now agrees with the volume it "
	 "names instead of contradicting it.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 1000.0], None),
	("voluntary_market_volume_definition",
	 "The volume sold into the voluntary market",
	 "voluntary_market_volume_mtco2",
	 "voluntary_carbon_market * carbon_credit_volumes",
	 "The share of the issued volume sold to voluntary buyers rather than "
	 "against a compliance obligation. Zero at the shipped default, because "
	 "a compliance-led programme sells nothing voluntarily, and the zero is "
	 "a statement rather than a missing value.",
	 "carbon_trajectory", "linear", "MtCO2/year", [0.0, 1000.0], None),
	# --- the market-ops products ---
	("market_traded_volume_definition",
	 "The traded volume",
	 "market_traded_volume_twh",
	 "market_liquidity * demand_twh",
	 "Churn times demand: a market where each MWh changes hands once trades "
	 "its demand, and one at a multiple of three trades it three times. The "
	 "volume is what the spread and the clearing fee are charged against, "
	 "so it is the base every market-ops cost shares.",
	 "price_demand", "linear", "TWh/year", [0.0, 1.0e6], None),
	("time_of_use_demand_definition",
	 "The demand on a time-of-use tariff",
	 "time_of_use_demand_twh",
	 "time_of_use_tariff_adoption * demand_twh",
	 "The share of demand on a time-of-use tariff. The product is the "
	 "volume the tariff reshapes, which is the quantity a load-shift "
	 "assessment needs and the share alone does not give.",
	 "price_demand", "linear", "TWh/year", [0.0, 1.0e6], None),
	("bid_ask_cost_definition",
	 "The cost of the bid-ask spread",
	 "bid_ask_cost_usd_per_year",
	 "bid_ask_spread * market_traded_volume_twh * 1000000",
	 "The spread paid on every MWh traded, with the 1e6 carrying TWh to "
	 "MWh. It is a transaction cost of the market's design, not of the "
	 "plant's operation: a thin market charges its participants for the "
	 "liquidity it does not have.",
	 "price_demand", "linear", "USD/year", [0.0, 1.0e11], None),
	("price_band_upper_definition",
	 "The upper price band",
	 "price_band_upper_usd_per_mwh",
	 "(1 + price_limits) * marginal_cost_usd_per_mwh",
	 "The offer cap a market sets above short-run marginal cost. The band "
	 "exists so a scarce hour cannot clear at a price that is a transfer "
	 "rather than a signal; Stoft's treatment of the offer cap is the "
	 "reason the band is stated around marginal cost and not around an "
	 "administered number.",
	 "price_demand", "linear", "USD/MWh", [0.0, 10000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("price_band_lower_definition",
	 "The lower price band",
	 "price_band_lower_usd_per_mwh",
	 "(1 - price_limits) * marginal_cost_usd_per_mwh",
	 "The floor a market sets below marginal cost: the price a must-run "
	 "unit is paid when it would otherwise have to bid negative to stay "
	 "on. The two arms are the same band, and stating both is what makes "
	 "the band a band rather than a cap.",
	 "price_demand", "linear", "USD/MWh", [-10000.0, 10000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("risk_adjusted_carbon_price_definition",
	 "The risk-adjusted carbon price",
	 "risk_adjusted_carbon_price_usd_per_tco2",
	 "(1 + carbon_price_risk) * carbon_price_escalated_usd_per_tco2",
	 "The escalated carbon price grossed up by the risk premium a project "
	 "financier demands for a price that is a policy variable. The premium "
	 "is what turns a forecast into a bankable number, and it is the "
	 "carbon-price analogue of the equity risk premium.",
	 "carbon_trajectory", "linear", "USD/tonne", [0.0, 10000.0], None),
	# --- the tariff and subsidy products ---
	("wheeling_charge_cost_definition",
	 "The transmission wheeling charge",
	 "wheeling_charges_usd_per_year",
	 "wheeling_charges * demand_twh * 1000000",
	 "The use-of-system charge on every MWh of demand, with the 1e6 "
	 "carrying TWh to MWh. It is a pass-through: the network's cost "
	 "recovered from the energy that uses it, which is the tariff design "
	 "the region's regulators publish.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11],
	 "Pass-through pricing"),
	("distribution_wheeling_cost_definition",
	 "The distribution wheeling charge",
	 "distribution_wheeling_usd_per_year",
	 "distribution_wheeling_charges * demand_twh * 1000000",
	 "The distribution use-of-system charge, recovered on the same base as "
	 "the transmission one. The two are separate tariffs because the two "
	 "networks have separate regulated asset bases.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11],
	 "Pass-through pricing"),
	("cross_border_wheeling_cost_definition",
	 "The cross-border wheeling charge",
	 "cross_border_wheeling_usd_per_year",
	 "wheeling_charge_cross_border * net_imports_twh * 1000000",
	 "The charge on the cross-border flow, at the same rate in both "
	 "directions: an importing year pays and an exporting year is credited, "
	 "which is what a symmetric wheeling schedule does to the *net* flow. "
	 "The right base is gross bilateral flow, and the graph carries net "
	 "imports only -- so the signed product is the best the balance "
	 "supports, and its sign is the direction of the transfer rather than a "
	 "defect. It is deliberately not written as `abs(net_imports_twh)`: the "
	 "sensitivity table differentiates every equation and refuses a "
	 "non-differentiable function rather than dropping the term, so an "
	 "absolute value here would make the whole gradient table uncomputable.",
	 "cost_accounting", "linear", "USD/year", [-1.0e11, 1.0e11],
	 "Pass-through pricing"),
	("feed_in_tariff_cost_definition",
	 "The feed-in tariff obligation",
	 "feed_in_tariff_cost_usd_per_year",
	 "feed_in_tariff * renewable_generation_twh * 1000000",
	 "The purchase obligation at the feed-in tariff, over the renewable "
	 "volume the balance already computes. The obligation is a cost of the "
	 "programme and not of the plant: the utility buys at the tariff and "
	 "sells at the regulated price, and the difference is what the "
	 "levy covers.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11],
	 "Pass-through pricing"),
	("electricity_subsidy_cost_definition",
	 "The consumer electricity subsidy",
	 "electricity_subsidy_spend_usd_per_year",
	 "electricity_subsidies * demand_twh * 1000000",
	 "The per-MWh subsidy the budget pays so the tariff can sit below cost. "
	 "Stated against demand because the subsidy follows the consumption, "
	 "not the connection.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11], None),
	("renewable_subsidy_cost_definition",
	 "The renewable generation subsidy",
	 "renewable_subsidy_spend_usd_per_year",
	 "renewable_subsidies * renewable_generation_twh * 1000000",
	 "A budget transfer per MWh of renewable generation, distinct from the "
	 "feed-in tariff: the FIT is a purchase obligation on the utility, "
	 "this is a transfer from the treasury, and a scenario can carry either "
	 "without the other.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11], None),
	("fossil_fuel_subsidy_cost_definition",
	 "The fossil-fuel subsidy",
	 "fossil_fuel_subsidy_spend_usd_per_year",
	 "fossil_fuel_subsidies * (generation_twh - renewable_generation_twh) * 1000000",
	 "The per-MWh subsidy on the non-renewable volume, which is generation "
	 "less renewables. The difference is the graph's own decomposition: "
	 "there is no separate fossil generation node, and inventing one would "
	 "be a second spelling of a quantity the balance already carries.",
	 "cost_accounting", "linear", "USD/year", [0.0, 1.0e11], None),
	("carbon_tax_offset_definition",
	 "The carbon revenue offset in other taxes",
	 "carbon_tax_offset_usd_per_year",
	 "carbon_tax_interaction * carbon_revenue_usd_per_year",
	 "The share of carbon revenue returned as a cut in other taxes: the "
	 "revenue-neutral reform's own arithmetic. Gross carbon revenue less "
	 "this offset is the net fiscal effect, which is the number a finance "
	 "ministry actually argues about.",
	 "financial", "linear", "USD/year", [0.0, 1.0e11],
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	("cross_subsidy_transfer_definition",
	 "The cross-subsidy between tariff classes",
	 "cross_subsidy_usd_per_year",
	 "cross_subsidy_level * total_revenue_usd_per_year",
	 "The revenue moved from one tariff class to another, as a share of "
	 "total revenue. It is a transfer inside the tariff and not a subsidy "
	 "from the budget: the classes pay the same total and the structure "
	 "decides who pays what.",
	 "affordability", "linear", "USD/year", [0.0, 1.0e11],
	 "Benefit-sharing programmes (the graph's own revenue identity)"),
	("tariff_rebalancing_transfer_definition",
	 "The revenue rebalanced over the horizon",
	 "tariff_rebalancing_usd_per_year",
	 "(1 - exp(-tariff_rebalancing * horizon_years)) * total_revenue_usd_per_year",
	 "A tariff class rebalanced toward cost at an annual rate compounds: "
	 "after n years the share of the base that has moved is 1 - exp(-r n), "
	 "the continuous-time form of the same decay the half-life equations "
	 "use. At the shipped 0.2/year over ten years it is 0.893 of the base, "
	 "and the closed form is what makes a ten-year glide path one number.",
	 "affordability", "nonlinear", "USD/year", [0.0, 1.0e11],
	 "World Bank Regulation of Utilities handbook, revenue caps"),
	("hybrid_capped_tariff_definition",
	 "The hybrid revenue-price cap's tariff",
	 "hybrid_capped_tariff_usd_per_mwh",
	 "hybrid_revenue_price_cap * price_cap * regulated_tariff_usd_per_mwh + (1 - hybrid_revenue_price_cap) * applied_tariff_usd_per_mwh",
	 "A hybrid cap binds a weighted average of a price cap and a revenue "
	 "cap, with the weight the regulator's own dial. The two arms are the "
	 "two tariffs the graph already carries, and the weight is what lets a "
	 "regulator trade the utility's volume risk against its price risk.",
	 "affordability", "linear", "USD/MWh", [0.0, 10000.0],
	 "World Bank Regulation of Utilities handbook, revenue caps"),
	("price_cap_identity",
	 "The average-tariff price cap",
	 "price_cap",
	 "revenue_cap",
	 "In a single-part tariff the cap on average price and the cap on "
	 "revenue are the same number: a revenue cap of 1.0 is a price cap of "
	 "1.0 because the volume is the same on both sides. The identity is the "
	 "catalog's duplicate resolution, and it is what "
	 "`applied_tariff_definition` already reads.",
	 "affordability", "linear", "1", [0.0, 10.0],
	 "The catalog's own duplicate rows, resolved"),
	("carbon_tax_coverage_identity",
	 "The carbon tax's covered share",
	 "carbon_tax_coverage",
	 "carbon_price_coverage",
	 "One covered share under two instrument names. The graph prices "
	 "emissions once, through `carbon_price_coverage`, and a tax rate "
	 "applied to a different share would be a second instrument the "
	 "revenue identity does not read.",
	 "emissions", "linear", "1", [0.0, 1.0],
	 "The catalog's own duplicate rows, resolved"),
	("social_tariff_identity",
	 "The social tariff",
	 "social_tariff",
	 "lifeline_tariff_usd_per_mwh",
	 "Two ids for the below-threshold tariff: the catalog's `social_tariff` "
	 "and the graph's `lifeline_tariff_usd_per_mwh`, which the shipped "
	 "`lifeline_tariff_alias` already equates to `lifeline_tariff`. The "
	 "identity makes the catalog id derived rather than a second price "
	 "nothing sets.",
	 "affordability", "linear", "USD/MWh", [0.0, 500.0],
	 "The catalog's own duplicate rows, resolved"),
	("market_concentration_definition",
	 "The market's Herfindahl-Hirschman index",
	 "market_concentration",
	 "10000 * (1 - fuel_diversity_index)",
	 "The HHI over the fleet's own fuel shares, on the 0-10000 scale the "
	 "competition authorities use. The fleet's diversity index is already "
	 "one minus the HHI over its capacities, so the product is the HHI the "
	 "index complements -- and the shipped default of 2500 is not the fleet "
	 "the graph ships, which is the finding the identity surfaces.",
	 "price_demand", "linear", "1", [0.0, 10000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	# --- the programme and regulatory products ---
	("mini_grid_subsidy_definition",
	 "The mini-grid programme subsidy",
	 "mini_grid_subsidy_usd_per_year",
	 "mini_grid_subsidies * mini_grid_programme_spend_usd_per_year",
	 "The share of the programme's spend covered by subsidy. The spend is "
	 "already derived (a per-connection cost times the connections served), "
	 "so the product is the fiscal exposure the programme carries rather "
	 "than the tariff it charges.",
	 "financial", "linear", "USD/year", [0.0, 1.0e11], None),
	("shs_subsidy_definition",
	 "The solar-home-system programme subsidy",
	 "shs_subsidy_usd_per_year",
	 "shs_subsidies * shs_programme_spend_usd_per_year",
	 "The share of the SHS programme's spend covered by subsidy, on the "
	 "same construction as the mini-grid product and against a different "
	 "programme.",
	 "financial", "linear", "USD/year", [0.0, 1.0e11], None),
	("netting_shortfall_definition",
	 "The collateral left un-netted",
	 "netting_shortfall_usd_per_year",
	 "(1 - netting_agreements) * collateral_posted_usd_per_year",
	 "The complement of the netting share: collateral posted that a netting "
	 "agreement does not cover, and therefore exposure a counterparty's "
	 "default reaches. The complement is the point -- a netting agreement "
	 "covering 90% leaves 10% of the posted collateral at risk.",
	 "financial", "linear", "USD million/year", [0.0, 1.0e6], None),
	("x_factor_revenue_reduction_definition",
	 "The RPI-X revenue reduction",
	 "x_factor_revenue_reduction",
	 "(1 - x_factor) * allowed_revenue_requirement",
	 "The RPI-X productivity offset: the allowed requirement less the "
	 "annual efficiency the regulator assumes the utility can find. The "
	 "reduction is a share of the requirement and not of the cost, which is "
	 "why the formula is a multiplication and not a subtraction of an "
	 "absolute.",
	 "financial", "linear", "USD million/year", [0.0, 1.0e6],
	 "World Bank Regulation of Utilities handbook, revenue caps"),
	("working_capital_allowance_definition",
	 "The working-capital allowance",
	 "working_capital_allowance_usd",
	 "working_capital_allowance * allowed_revenue_requirement",
	 "The regulator's allowance for the working capital a utility funds "
	 "between paying its suppliers and collecting its bills, as a share of "
	 "the revenue requirement. It is a permitted recovery, not a cost the "
	 "utility incurs.",
	 "financial", "linear", "USD million/year", [0.0, 1.0e6],
	 "World Bank Regulation of Utilities handbook, revenue caps"),
	("service_quality_reward_definition",
	 "The service-quality reward",
	 "service_quality_reward_usd",
	 "service_quality_reward * allowed_revenue_requirement",
	 "The reward for beating a quality target, as a share of the revenue "
	 "requirement. A reward rather than a penalty because the requirement "
	 "is the base the regulator can actually move; the symmetric penalty "
	 "lives on the same share with the opposite sign.",
	 "financial", "linear", "USD million/year", [0.0, 1.0e6],
	 "World Bank Regulation of Utilities handbook, revenue caps"),
	("employment_attainment_local_definition",
	 "The local-employment attainment ratio",
	 "employment_attainment_local",
	 "local_employment_share / local_employment_targets",
	 "The share achieved over the share targeted. Both sides are shares of "
	 "the same workforce, so the ratio is the attainment index a monitoring "
	 "report quotes -- and a target left at the catalog's 500000.0 "
	 "placeholder reads as an attainment of essentially zero, which is the "
	 "placeholder surfacing rather than a performance finding.",
	 "employment", "linear", "1", [0.0, 10.0], None),
	("employment_attainment_women_definition",
	 "The women's-employment attainment ratio",
	 "employment_attainment_women",
	 "women_employment_share / women_employment_targets",
	 "Achieved over targeted female share of the workforce. The ratio is "
	 "the index the programme's own reporting uses.",
	 "employment", "linear", "1", [0.0, 10.0], None),
	("employment_attainment_youth_definition",
	 "The youth-employment attainment ratio",
	 "employment_attainment_youth",
	 "youth_employment_share / youth_employment_targets",
	 "Achieved over targeted youth share of the workforce.",
	 "employment", "linear", "1", [0.0, 10.0], None),
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


def build_batch24(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 24: the carbon and market families, and the annual-quantity repair."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, str]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, category, determinism, prose in BATCH24_RETYPES:
		shipped = graph.nodes[name]
		full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		# The retype repairs the *unit*, not the role. A node an equation
		# computes stays derived (and keeps the `initial` its feedback loop
		# starts from); a node a scenario sets keeps the role it had, and the
		# table's default replaces the catalog placeholder it shipped with.
		full.update({
			"unit": unit, "range": rng, "description": prose,
			"determinism": determinism,
			"priority": "P1", "status": "existing",
			"source": "The carbon-market coupling (batch 24)",
			"users": ["Regulators", "Policymakers", "Carbon"],
		})
		if shipped.role.value != "derived":
			full["default"] = default
		nodes[name] = full

	for name, unit, rng, default, category, prose in BATCH24_BASES:
		assert name not in graph.nodes, f"{name} already exists; a base is new"
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "default": default, "role": "free",
			"determinism": "physical", "priority": "P1", "status": "existing",
			"source": "The carbon-market coupling (batch 24)",
			"users": ["Regulators", "Policymakers"],
		}

	for eq_id, name, lhs, rhs, prose, system, linearity, unit, rng, cite in (
		BATCH24_EQUATIONS
	):
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		# A node this batch retypes keeps the category the catalog gave it and
		# gains the unit the equation computes into; a node the batch creates
		# takes the equation's own unit and a category from the family.
		if lhs in nodes:
			nodes[lhs]["role"] = "derived"
			nodes[lhs].pop("default", None)
			nodes[lhs]["description"] = prose
		else:
			prior = graph.nodes.get(lhs)
			category = prior.category if prior is not None else "Carbon"
			users = list(prior.users) if prior is not None else ["Regulators"]
			nodes[lhs] = {
				"name": (prior.name if prior is not None
					else lhs.replace("_", " ").capitalize()),
				"description": prose,
				"category": category, "type": "float", "unit": unit,
				"range": rng, "role": "derived",
				"determinism": "policy", "priority": "P1", "status": "existing",
				"source": "The carbon-market coupling (batch 24)",
				"users": users,
			}
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

	# The instrument gate. `carbon_revenue_definition` reads no switch, so at
	# the shipped defaults the graph accrues 650,578,257 USD/year of carbon
	# revenue with `ets_enabled = 0.0`: a jurisdiction with no emissions
	# trading system collecting the revenue of one. The revenue is not
	# multiplied by the flag -- an ETS and a carbon tax are alternative
	# instruments over the same base, and the covered share the identity
	# already applies is the only share either instrument owns -- so the
	# defect is stated where a reviewer will meet it, as a rule.
	rules.append({
		"id": "carbon_revenue_without_an_instrument",
		"condition": "ets_enabled < 0.5 and carbon_price_coverage > 0.0",
		"severity": "warning",
		"message": (
			"Carbon revenue accrues while no emissions trading system is "
			"enabled. The revenue identity prices the covered share of "
			"emissions and reads no instrument switch, so a scenario that "
			"switches the ETS off still books the revenue it would have "
			"raised. Either enable the instrument or set carbon_price_coverage "
			"to zero, and say which in the plan."
		),
		"suggestion": (
			"Enable ets_enabled, or set carbon_price_coverage to 0.0, or name "
			"the carbon tax that collects the revenue instead"
		),
	})
	return nodes, equations, edges, rules


# ---------------------------------------------------------------------------
# Batch 25 -- the gate family: thirteen switches with a quantity on the other
# side of them.
#
# The research packs split the remaining policy flags into two classes, and the
# split is the whole design. A *gate-product* is a switch multiplying a base
# the graph already carries: the product is the gated quantity, it is zero when
# the switch is off, and it is a real number when the switch is on. A
# *scene-switch* (``market_coupling``, ``pricing_mechanism``,
# ``condition_based_maintenance``, the hazard projections) selects which model
# runs; no arithmetic expresses it, and writing one would be a number pretending
# to be a branch. Only the first class is coupled here.
#
# Two of the thirteen needed their declaration repaired first. The eight
# ``GATE-PRODUCT`` insurance and fiscal flags shipped as ``float`` knobs with no
# unit and the catalog's 500000.0 placeholder, so a share of a revenue base
# evaluated to 500000 x 6.3e9 -- and ``import_duty_exemption`` had to be written
# as ``(1 - x)`` for the duty *paid*, which at the placeholder evaluates to
# -49,999.9. A share of something is dimensionless; the placeholder is not a
# value, and retyping it to a ``1`` in ``[0, 1]`` is what makes the product mean
# what its name says.
#
# The theory is the standard one and needs no citation beyond the textbook
# statement: a switch times a base is the gated quantity. The bases are the
# graph's own -- ``total_revenue_usd_per_year``, ``capex_usd_per_kw`` x
# ``total_capacity_mw`` x 1000 (kW per MW), ``net_imports_twh``,
# ``planned_maintenance_hours_per_year``, ``electrified_population`` -- so each
# equation states a relationship a reader can check against the base's own
# definition rather than a number invented here.
#
# ``transmission_expansion_allowed`` needed ``line_upgrade_budget`` retyped from
# a unit-less 500000.0 placeholder to USD, because a permitted spend whose
# budget has no unit is undecidable rather than zero.
#
# All thirteen were checked dimensionally before authoring (0 bad of 13): the
# derived lhs was built from the base node's body with the unit the equation
# states, and ``unit_of`` was asked for the rhs's dimension.
# ---------------------------------------------------------------------------

#: (name, unit, range, default, category, prose) -- the eight placeholder
#: shares, retyped to the dimensionless share each name describes.
BATCH25_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("business_interruption_insurance", "1", [0.0, 1.0], 0.01, "Macro",
	 "Share of gross revenue indemnified by business-interruption cover. A "
	 "share: the shipped node carried the catalog placeholder and no unit, "
	 "which made every product against revenue read as 500000 x USD/year."),
	("cyber_insurance", "1", [0.0, 1.0], 0.002, "Digital",
	 "Share of gross revenue indemnified against cyber loss. A share."),
	("force_majeure_insurance", "1", [0.0, 1.0], 0.004, "Macro",
	 "Share of gross revenue indemnified against force-majeure events. A "
	 "share."),
	("free_trade_zone_benefits", "1", [0.0, 1.0], 0.0, "Tax",
	 "Share of the equipment duty forgone under free-trade-zone status. A "
	 "share of the duty the equipment would otherwise bear."),
	("import_duty_exemption", "1", [0.0, 1.0], 0.0, "Policy",
	 "Share of the equipment duty exempted. A share, and the reason the "
	 "product is written as `(1 - x)`: what the project pays is the "
	 "unexempted part."),
	("parent_company_guarantee", "1", [0.0, 1.0], 0.0, "Contract",
	 "Share of the debt tranche carrying a parent-company guarantee. A "
	 "share, and the guarantee's value is that share of the debt it "
	 "supports."),
	("political_risk_insurance", "1", [0.0, 1.0], 0.0, "Macro",
	 "Share of the asset value insured against political events. A share."),
	("sanctions_exposure", "1", [0.0, 1.0], 0.0, "Geopol",
	 "Share of the asset value exposed to sanctions. A share, and it is the "
	 "exposure rather than a probability: the graph carries no sanction "
	 "frequency it could multiply."),
	("line_upgrade_budget", "USD", [0.0, 1.0e10], 5.0e7, "Transmission & Grid",
	 "The capital budget available for line upgrades. A spend, and the base "
	 "the transmission-expansion gate permits; the shipped node carried the "
	 "catalog placeholder and no unit."),
)

#: (equation id, name, lhs, rhs, prose, unit, range, reference)
BATCH25_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, list[float], str | None], ...
] = (
	("gated_carbon_volume_definition", "The gated carbon volume",
	 "gated_carbon_volume_mtco2", "ets_enabled * ets_cap",
	 "The capped volume the emissions trading system actually applies, which "
	 "is the cap times the instrument switch. It is the quantity the revenue "
	 "identity cannot read: `carbon_revenue_definition` prices the covered "
	 "share of emissions and takes no switch, so the revenue accrues whether "
	 "or not the instrument exists. Stating the gated volume beside it makes "
	 "the gap a difference between two derived nodes rather than a rule's "
	 "prose.",
	 "MtCO2/year", [0.0, 10000.0], "EU CBAM regulation"),
	("business_interruption_cover_definition", "The business-interruption cover",
	 "business_interruption_cover_usd_per_year",
	 "business_interruption_insurance * total_revenue_usd_per_year",
	 "The revenue indemnified: the cover share times gross revenue. A switch "
	 "at zero returns zero, which is the gated quantity rather than a "
	 "scenario branch.",
	 "USD/year", [0.0, 1.0e12], None),
	("cyber_cover_definition", "The cyber-loss cover",
	 "cyber_cover_usd_per_year",
	 "cyber_insurance * total_revenue_usd_per_year",
	 "The revenue indemnified against cyber loss: the cover share times gross "
	 "revenue.", "USD/year", [0.0, 1.0e12], None),
	("force_majeure_cover_definition", "The force-majeure cover",
	 "force_majeure_cover_usd_per_year",
	 "force_majeure_insurance * total_revenue_usd_per_year",
	 "The revenue indemnified against force-majeure events: the cover share "
	 "times gross revenue.", "USD/year", [0.0, 1.0e12], None),
	("free_trade_zone_benefit_definition", "The free-trade-zone benefit",
	 "free_trade_zone_benefit_usd",
	 "free_trade_zone_benefits * import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The duty forgone: the zone's share of the equipment duty, which is the "
	 "duty rate on the fleet's capital. The `1000` is kW per MW, so the "
	 "capital term is USD -- the fleet's own unit arithmetic, not a fitted "
	 "factor.",
	 "USD", [0.0, 1.0e13], None),
	("import_duty_cost_definition", "The import duty paid",
	 "import_duty_cost_usd",
	 "(1 - import_duty_exemption) * import_duty_equipment * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The duty the project actually pays: the unexempted share of the "
	 "equipment duty on the fleet's capital. Written as `(1 - x)` because the "
	 "node is the share *exempted* -- the opposite spelling evaluates to a "
	 "negative duty at any exemption near one.",
	 "USD", [0.0, 1.0e13], None),
	("parent_company_guarantee_definition", "The guaranteed debt",
	 "parent_company_guarantee_usd",
	 "parent_company_guarantee * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The debt tranche carrying the guarantee: the guaranteed share of the "
	 "debt-financed part of the fleet's capital.",
	 "USD", [0.0, 1.0e13], None),
	("political_risk_cover_definition", "The political-risk cover",
	 "political_risk_cover_usd",
	 "political_risk_insurance * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The asset value insured against political events: the insured share of "
	 "the fleet's capital.", "USD", [0.0, 1.0e13], None),
	("sanctions_exposed_value_definition", "The sanctions-exposed value",
	 "sanctions_exposed_value_usd",
	 "sanctions_exposure * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The asset value exposed to sanctions: the exposed share of the fleet's "
	 "capital.", "USD", [0.0, 1.0e13], None),
	("permitted_imports_definition", "The permitted imports",
	 "permitted_imports_twh", "cross_border_trade_allowed * net_imports_twh",
	 "The cross-border flow the trade regime permits: the switch times the "
	 "net balance. At the shipped defaults the balance is zero, so the gate "
	 "is live and the base is empty -- which is the honest reading, and the "
	 "reason this product carries no information until a scenario sets the "
	 "balance.",
	 "TWh/year", [-1000.0, 1000.0], None),
	("coordinated_maintenance_definition", "The coordinated maintenance hours",
	 "coordinated_maintenance_hours_per_year",
	 "outage_coordination * planned_maintenance_hours_per_year",
	 "The maintenance hours run under coordination: the switch times the "
	 "planned hours. Coordination does not change how much maintenance the "
	 "fleet needs, only whether the outages are scheduled jointly, so the "
	 "base is unchanged and the gate selects which hours are coordinated.",
	 "hours/year", [0.0, 8760.0], None),
	("smart_metered_population_definition", "The smart-metered population",
	 "smart_metered_population",
	 "smart_metering_rollout * smart_metering_penetration * electrified_population",
	 "The population reached by the metering programme: the rollout switch "
	 "times the penetration rate times the electrified population. Two gates "
	 "multiply the same base, and both are switches the scenario sets.",
	 "people", [0.0, 1.0e9], None),
	("permitted_transmission_spend_definition", "The permitted transmission spend",
	 "permitted_transmission_spend_usd",
	 "transmission_expansion_allowed * line_upgrade_budget",
	 "The upgrade spend the regime permits: the expansion switch times the "
	 "available budget. A permitted spend of zero is a live constraint, not "
	 "an absent one -- it is what a build scenario must respect.",
	 "USD", [0.0, 1.0e10], None),
)


def build_batch25(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 25: the gate products -- switches with a quantity behind them."""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []

	for name, unit, rng, default, category, prose in BATCH25_RETYPES:
		shipped = graph.nodes[name]
		full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"unit": unit, "range": rng, "default": default,
			"description": prose, "determinism": "policy",
			"priority": "P1", "status": "existing",
			"source": "The gate-family coupling (batch 25)",
			"users": ["Regulators", "Policymakers", "Planners"],
		})
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, unit, rng, cite in BATCH25_EQUATIONS:
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		prior = graph.nodes.get(lhs)
		category = prior.category if prior is not None else "Policy"
		nodes[lhs] = {
			"name": name,
			"description": prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "role": "derived",
			"determinism": "policy", "priority": "P1", "status": "existing",
			"source": "The gate-family coupling (batch 25)",
			"users": ["Regulators", "Planners"],
		}
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": "financial", "lhs": lhs, "rhs": rhs,
			"relation": "eq", "parameters": [lhs] + rhs_params,
			"free_variables": [], "determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"direction": "forward", "strength": "hard",
				"description": "Gates the base.",
				"reference": cite, "priority": "P1",
			})
	return nodes, equations, edges, []


#: (name, unit, range, default, category, prose) -- the four shares the reserve
#: family needed and the graph did not carry. A grid code states each reserve
#: requirement as a share of peak demand, so the share IS the free parameter and
#: the MW figure is its product. Before this batch the MW figures were themselves
#: the free knobs, at the catalog's 500000.0 placeholder, which made every one of
#: them 500 GW of reserve.
BATCH26_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("spinning_reserve_share", "1", [0.0, 0.5], 0.05, "Operational",
	 "Spinning reserve as a share of peak demand. The grid-code figure: a "
	 "system operator carries spinning reserve sized to the largest credible "
	 "loss, which is conventionally quoted as a percentage of peak load. "
	 "Typical operating practice is 3-7%; the upper bound of the range is the "
	 "share at which the reserve alone would exceed a tenth of the fleet."),
	("regulation_up_share", "1", [0.0, 0.5], 0.01, "Operational",
	 "Upward regulation reserve as a share of peak demand. Regulation reserve "
	 "covers the continuous second-to-second imbalance between scheduled and "
	 "actual output, so it is far smaller than contingency reserve -- the "
	 "shares differ by an order of magnitude for that reason, not by "
	 "convention."),
	("regulation_down_share", "1", [0.0, 0.5], 0.01, "Operational",
	 "Downward regulation reserve as a share of peak demand. The symmetric "
	 "counterpart of upward regulation: capacity able to reduce output on "
	 "instruction. It is a separate parameter because the two are procured "
	 "separately and a fleet's downward capability is not its upward one -- "
	 "a must-run unit can regulate down and not up."),
	("voltage_support_share", "1", [0.0, 1.0], 0.10, "Operational",
	 "Reactive reserve as a share of the fleet's reactive capability. The "
	 "voltage-support requirement is reactive power held in reserve, so the "
	 "base it multiplies is MVAr and not MW: the graph's own reactive "
	 "capability, which is the power factor's share of peak demand."),
)

#: (equation id, name, lhs, rhs, prose, system, unit, range, reference)
BATCH26_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, list[float], str], ...
] = (
	("spinning_reserve_definition", "The spinning reserve requirement",
	 "spinning_reserve", "spinning_reserve_share * peak_demand_mw",
	 "Spinning reserve in MW: the grid code's share of peak demand. This is "
	 "the catalog's own formula (SR = alpha D_peak) with alpha as a node "
	 "rather than a constant folded into the arithmetic, so a scenario can "
	 "move the grid code without rewriting the equation.",
	 "reserve_margin", "MW", [0.0, 20000.0],
	 "Standard N-1 planning criterion; cf. ENTSO-E adequacy studies"),
	("spinning_reserve_requirement_alias", "The spinning reserve alias",
	 "spinning_reserve_requirement", "spinning_reserve",
	 "The catalog carries both `spinning_reserve` (category 8, Outage) and "
	 "`spinning_reserve_requirement` (category 11, Operational) with the same "
	 "formula and the same name. They are one quantity under two ids, so the "
	 "equality states the duplicate rather than letting two 500000.0 "
	 "placeholders drift apart.",
	 "reserve_margin", "MW", [0.0, 20000.0],
	 "The catalog's own duplicate rows, resolved"),
	("non_spinning_reserve_alias", "The non-spinning reserve alias",
	 "non_spinning_reserve", "non_spinning_reserve_requirement",
	 "The same duplicate pair for the non-spinning reserve. The requirement "
	 "itself is a free node with a real default and a real range, and "
	 "`non_spinning_reserve_inside_margin` already bounds it inside the "
	 "operating reserve; this equality makes the second id read the same "
	 "quantity instead of a placeholder.",
	 "reserve_margin", "MW", [0.0, 20000.0],
	 "The catalog's own duplicate rows, resolved"),
	("regulation_up_definition", "The upward regulation requirement",
	 "regulation_up_requirement", "regulation_up_share * peak_demand_mw",
	 "Upward regulation in MW: the share of peak demand held for continuous "
	 "imbalance correction. Regulation and contingency reserve are different "
	 "products with different response times, and the catalog's 'Reserve "
	 "types -- similar forms' note is the claim that the form is shared, not "
	 "the parameter.",
	 "reserve_margin", "MW", [0.0, 20000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("regulation_down_definition", "The downward regulation requirement",
	 "regulation_down_requirement", "regulation_down_share * peak_demand_mw",
	 "Downward regulation in MW: the share of peak demand held to reduce "
	 "output. Separate from the upward requirement because the fleet's "
	 "downward capability is a different constraint.",
	 "reserve_margin", "MW", [0.0, 20000.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("voltage_support_definition", "The voltage support requirement",
	 "voltage_support_requirement",
	 "voltage_support_share * reactive_capability_mvar",
	 "Reactive reserve in MVAr: the share of the fleet's reactive capability "
	 "held for voltage support. The catalog's formula for this node is a "
	 "voltage inequality, which is the constraint the reserve serves rather "
	 "than a definition of the reserve; the reserve itself is a quantity of "
	 "MVAr, and the graph already carries the capability it is a share of.",
	 "reliability", "MVAr", [0.0, 100000.0],
	 "IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck"),
	("spare_capacity_definition", "The spare capacity",
	 "spare_capacity", "total_capacity_mw - peak_demand_mw",
	 "Installed capacity less peak demand: the headroom the fleet carries. "
	 "The catalog names this node's formula as a bare symbol, which is the "
	 "absence of a formula; the headroom is the only reading of the name that "
	 "the graph's own capacity and demand nodes can support.",
	 "reserve_margin", "MW", [0.0, 100000.0],
	 "Standard N-1 planning criterion; cf. ENTSO-E adequacy studies"),
	("planning_reserve_margin_alias", "The planning reserve margin",
	 "planning_reserve_margin", "reserve_margin_min",
	 "The planning reserve margin is the requirement `reserve_margin_min` "
	 "carries: the same 0.15, under the catalog's second id. The graph's "
	 "reserve-margin constraints already read `reserve_margin_min`, so the "
	 "alias points at the node that does the work rather than at a new one.",
	 "reserve_margin", "1", [0.0, 2.0],
	 "Standard N-1 planning criterion; cf. ENTSO-E adequacy studies"),
	("operating_reserve_margin_alias", "The operating reserve margin",
	 "reserve_margin", "reserve_margin_actual",
	 "The catalog's 'Operating reserve margin' is the margin the built fleet "
	 "actually delivers, which `reserve_margin_actual` already computes as "
	 "(firm plus firm VRE, less peak) over peak. Naming the alias is what "
	 "stops the placeholder from being read as a second, independent margin.",
	 "reserve_margin", "1", [-1.0, 2.0],
	 "Stoft 2002, Power System Economics, ch. 5"),
	("reliability_target_alias", "The reliability target",
	 "grid_reliability_saifi", "service_quality_standards",
	 "The catalog's 'Reliability target (SAIFI)' is the service-quality "
	 "standard in interruptions per year, which the graph carries as "
	 "`service_quality_standards` and already binds with `saifi_ceiling_bound`. "
	 "A target is not a second measurement of the fleet's performance.",
	 "reliability", "events/year", [0.0, 200.0],
	 "IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck"),
	("transmission_loss_target_definition", "The loss after the target",
	 "transmission_loss_after_target",
	 "transmission_loss_factor * (1 - transmission_loss_reduction_target)",
	 "The loss factor the target leaves: the base loss reduced by the "
	 "reduction target. The catalog defines the target as a fractional "
	 "reduction ((base - target) / base), which is the same statement solved "
	 "for the target, and writing it this way makes the target's dimension "
	 "dimensionless rather than a loss level the graph has no node for.",
	 "energy_balance", "1", [0.0, 1.0], None),
)


def build_batch26(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 26: the adequacy and reserve family.

	Eleven nodes the catalog declares with a formula and the graph held as
	placeholders. They divide into two kinds and the division is the batch's
	content. Seven are *definitions* the catalog states outright -- spinning
	and non-spinning reserve as a share of peak demand, regulation up and down
	the same way, voltage support as a share of reactive capability, spare
	capacity as headroom, and the loss level a reduction target leaves. Four
	are *aliases*: the catalog carries the same quantity under two ids with two
	names, and the equality is the honest coupling because there is only one
	number.

	Every one of the eleven shipped with unit=None and default=500000.0. That
	placeholder is not a neutral absence: `spinning_reserve` at 500000 MW is
	500 GW of reserve on an 8.5 GW peak, and a scenario reading it would
	conclude the fleet is drowning in capacity. The retype to MW with a share
	behind it is most of the value.
	"""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []

	for name, unit, rng, default, category, prose in BATCH26_BASES:
		# A base is new to the *pre-batch* graph, but the emit path reads the
		# already-baked document, so a re-emit after a bake finds it present.
		# Reading the shipped body and overriding the fields this batch owns
		# keeps the two runs byte-identical, which is what makes re-emitting a
		# correction safe.
		shipped = graph.nodes.get(name)
		full = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose,
			"category": category, "type": "float", "unit": unit,
			"range": rng, "default": default, "role": "free",
			"determinism": "policy", "priority": "P1", "status": "existing",
			"source": "The adequacy and reserve coupling (batch 26)",
			"users": ["Regulators", "Planners"],
		})
		nodes[name] = full

	# The reduction target is a fractional reduction, and the shipped node had
	# no unit and the placeholder. Retyped here because the equation below
	# multiplies by (1 - x): at 500000.0 that product is -499999, a loss factor
	# of minus half a million.
	retype = graph.nodes["transmission_loss_reduction_target"]
	full = dict(retype.model_dump(exclude={"id"}, mode="json"))
	full.update({
		"unit": "1", "range": [0.0, 1.0], "default": 0.1, "role": "free",
		"description": (
			"The fractional reduction in transmission losses the target aims "
			"for. A share, not a loss level: the catalog's own formula divides "
			"the difference by the base loss, which makes the target a ratio. "
			"The shipped node carried the catalog placeholder and no unit."
		),
		"determinism": "policy", "priority": "P2", "status": "existing",
		"source": "The adequacy and reserve coupling (batch 26)",
		"users": ["Regulators", "Planners"],
	})
	nodes["transmission_loss_reduction_target"] = full

	for eq_id, name, lhs, rhs, prose, system, unit, rng, cite in BATCH26_EQUATIONS:
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		if lhs in nodes:
			nodes[lhs]["role"] = "derived"
			nodes[lhs].pop("default", None)
			nodes[lhs]["unit"] = unit
			nodes[lhs]["range"] = rng
			nodes[lhs]["description"] = prose
		else:
			prior = graph.nodes.get(lhs)
			category = prior.category if prior is not None else "Operational"
			users = list(prior.users) if prior is not None else ["Planners"]
			nodes[lhs] = {
				"name": (prior.name if prior is not None
					else lhs.replace("_", " ").capitalize()),
				"description": prose,
				"category": category, "type": "float", "unit": unit,
				"range": rng, "role": "derived",
				"determinism": "fixed", "priority": "P1", "status": "existing",
				"source": "The adequacy and reserve coupling (batch 26)",
				"users": users,
			}
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs,
			"relation": "eq", "parameters": [lhs] + rhs_params,
			"free_variables": [], "determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs,
				"equation_id": eq_id, "relationship": "functional",
				"direction": "forward", "strength": "hard",
				"description": "Determines the reserve or its alias.",
				"reference": cite, "priority": "P1",
			})
	return nodes, equations, edges, []


BATCH27_RETYPES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	("transaction_costs", "1", [0.0, 0.1], 0.02, "policy", "free",
	 "Transaction costs as a share of revenue. The catalog carried the node "
	 "with no unit and the 500000.0 placeholder, so a scenario reading it as "
	 "a share would price transaction costs at fifty million times revenue. "
	 "Two percent of gross revenue is the order the development-finance "
	 "literature uses for the all-in cost of arranging, legal, and "
	 "disbursing a project loan."),
	("debt_tenor", "year", [5.0, 25.0], 15.0, "fixed", "free",
	 "The debt tenor in years. The catalog placeholder was 500000.0 with no "
	 "unit, and the node feeds the annuity exponent in `llcr_definition`, "
	 "which is why the unit walker's annuity convention cannot catch it: "
	 "`(1 + cost_of_debt) ** debt_tenor` is blessed for any unit on the "
	 "exponent. Fifteen years is the middle of the 5-25 band the "
	 "development-finance term sheet uses."),
	("currency_risk_premium", "1/year", [0.0, 0.2], 0.0256, "policy", "free",
	 "The currency risk premium added to the cost of debt. FPE section 6 "
	 "applies it there rather than as a separate cash-flow line, so this "
	 "batch wires it into `cost_of_debt_priced`. The default is Damodaran's "
	 "South Africa country risk premium for the 2026-01 table (3.90% total "
	 "against a 4.23% mature-market ERP, giving a 2.56% spread component), "
	 "which is the country the fleet's cost basis is closest to. It is a "
	 "policy dial a scenario moves per jurisdiction."),
	("technology_risk_premium", "1/year", [0.0, 0.1], 0.03, "policy", "free",
	 "The technology risk premium a financier charges on an unproven asset. "
	 "Applied to the equity tranche: the lender takes the sovereign and "
	 "currency exposure, the sponsor takes the construction and technology "
	 "exposure, and the two premiums price different risks on different "
	 "tranches. Three percent is the upper-middle of the 0-10% band the "
	 "project-finance literature quotes for first-of-a-kind generation."),
	("microinsurance", "1", [0.0, 1.0], 0.5, "stochastic", "free",
	 "The share of the electrified population covered by microinsurance. A "
	 "share, not a count: the shipped node carried the 500000.0 placeholder "
	 "with unit 1, so it read as half a million times a population."),
	("solvency_capital", "USD million", [-500000.0, 500000.0], None, "stochastic", "derived",
	 "Solvency capital: the capital an insurer must hold against the "
	 "99.5th-percentile loss net of expected loss. FRM section 6.3 states it "
	 "as `pml_99_5 - aal`. The shipped node carried unit 1 and the 500000.0 "
	 "placeholder -- a capital requirement with no currency, which no "
	 "balance sheet can read. The range is signed because the difference is: "
	 "an expected loss above the tail is an inconsistent loss model, and a "
	 "signed range lets the arithmetic say so instead of clamping it."),
	("insurance_premiums", "USD million", [0.0, 500000.0], None, "policy", "derived",
	 "The insurance premium the project pays, in currency. The shipped node "
	 "carried unit 1 and the placeholder. It is derived here from the "
	 "frequency-severity chain rather than set, so the premium moves with "
	 "the loss model."),
	("rab_roll_forward", "USD million/year", [-500000.0, 500000.0], None, "policy", "derived",
	 "The regulatory asset base's annual movement: the capital charge the "
	 "roll-forward books, which is the allowed depreciation on the asset "
	 "base net of what has already been recovered. A flow, not a stock -- "
	 "the shipped node carried no unit and the placeholder, and writing it "
	 "as a stock would make it indistinguishable from "
	 "`regulatory_asset_base`."),
	("ets_enabled", "1", [0.0, 1.0], 1.0, "policy", "free",
	 "Whether the jurisdiction operates an emissions trading system. The "
	 "default is 1.0 and that is a repair, not a preference: batch 24 "
	 "shipped the switch at 0.0 beside a `carbon_price_coverage` of 0.5 and "
	 "`carbon_price_usd_per_tco2` of 50, so the shipped graph booked carbon "
	 "revenue while declaring no instrument -- which its own "
	 "`carbon_revenue_without_an_instrument` rule fires on at the defaults. "
	 "The graph contradicted itself at the values it shipped."),
)

#: (name, unit, range, default, category, prose)
BATCH27_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("aal_usd_million", "USD million", [0.0, 500000.0], 50.0, "Insurance & Catastrophe",
	 "The annual average loss: the expected loss over a year from the "
	 "frequency-severity convolution. CLIMADA's `aai_agg` output; the base "
	 "every premium is priced against and every solvency requirement is "
	 "measured net of."),
	("pml_99_5_usd_million", "USD million", [0.0, 500000.0], 500.0, "Insurance & Catastrophe",
	 "The probable maximum loss at the 99.5th percentile: the loss exceeded "
	 "once in two hundred years. The tail a solvency regime capitalises "
	 "against, and the difference from the AAL is the capital it demands."),
	("expense_loading", "1", [0.0, 1.0], 0.10, "Insurance & Catastrophe",
	 "The expense loading: the share of the premium that covers underwriting "
	 "cost rather than expected loss. Ten percent is the middle of the "
	 "range a specialty property book reports."),
	("capital_loading", "1", [0.0, 1.0], 0.15, "Insurance & Catastrophe",
	 "The capital loading: the share of the premium that remunerates the "
	 "capital held against the tail. It is a return on solvency capital "
	 "expressed as a fraction of expected loss, which is why it sits beside "
	 "`solvency_capital` rather than inside it."),
	("profit_margin", "1", [0.0, 1.0], 0.05, "Insurance & Catastrophe",
	 "The underwriting margin the insurer adds on top of expected loss, "
	 "expenses, and capital cost. The fourth term of the FRM's premium "
	 "identity."),
	("sovereign_risk_premium", "1/year", [0.0, 0.2], 0.0256, "Investment & Finance",
	 "The sovereign risk premium in the debt rate. Set equal to "
	 "`debt_spread` by the equality below, because the credit-spread "
	 "decomposition the graph already carries (`interest_rate + "
	 "debt_spread`) is the borrower premium, and for a sovereign-guaranteed "
	 "project the borrower and the sovereign are the same credit. Damodaran "
	 "(2026) is the source for the default: South Africa's 3.90% total "
	 "spread over a 4.23% mature-market equity risk premium."),
)

#: (equation id, name, lhs, rhs, prose, system, unit, range, reference)
BATCH27_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str, list[float], str | None], ...
] = (
	("interest_rate_debt_alias", "The debt interest rate",
	 "interest_rate_debt", "cost_of_debt",
	 "The catalog carries the debt rate twice, as `interest_rate_debt` and "
	 "as `cost_of_debt`, and there is one number. The equality is the "
	 "coupling: a scenario that sets either sets both.",
	 "financial", "1/year", [0.0, 0.5], None),
	("debt_service_coverage_ratio_alias", "The DSCR floor",
	 "debt_service_coverage_ratio", "dscr_min",
	 "The coverage ratio a lender requires, under the catalog's two ids. "
	 "`dscr_min` is the node the covenant reads; this is the same floor "
	 "under the name the catalog also carries.",
	 "financial", "1", [1.0, 3.0], None),
	("maladaptation_risk_alias", "The maladaptation risk",
	 "maladaptation_risk", "risk_of_maladaptation",
	 "The risk that an adaptation investment makes the position worse, "
	 "under the catalog's two ids. One quantity, so one equality.",
	 "financial", "1", [0.0, 1.0], None),
	("project_irr_hurdle_definition", "The equity IRR hurdle",
	 "project_irr_hurdle", "discount_rate * (1 + equity_return_target)",
	 "The return the equity tranche requires: the project discount rate "
	 "grossed up by the premium equity demands over the blended cost of "
	 "capital. The gross-up is the standard equity-hurdle construction -- "
	 "the WACC is what the asset must earn, and the equity return target is "
	 "the margin above it that makes the equity worth holding.",
	 "financial", "1/year", [0.0, 1.0], "Short, Packey & Holt (1995), NREL/TP-462-5173"),
	("microinsurance_premium_definition", "The microinsurance premium",
	 "microinsurance_premium_usd_per_year",
	 "microinsurance_premium_share_of_income * household_income_usd_per_year",
	 "The premium a covered household pays: the share of income the product "
	 "is priced at, times household income. Priced off income rather than "
	 "off asset value because the product is an income-protection cover, "
	 "not a property one.",
	 "financial", "USD/year", [0.0, 1.0e6], None),
	("microinsured_population_definition", "The microinsured population",
	 "microinsured_population", "microinsurance * electrified_population",
	 "The population the microinsurance product reaches: the coverage share "
	 "times the electrified population. The base is the electrified "
	 "population and not the total, because the product is sold with the "
	 "connection.",
	 "financial", "people", [0.0, 1.0e9], None),
	("ring_fenced_asset_definition", "The ring-fenced asset value",
	 "ring_fenced_asset_value_usd_million",
	 "ring_fencing_rules * regulatory_asset_base",
	 "The part of the regulatory asset base the ring-fence protects from "
	 "the utility's other creditors: the ring-fencing share times the base. "
	 "A regulator's ring-fence is what makes the asset bankable, so the "
	 "quantity it protects is the asset base and not the revenue.",
	 "financial", "USD million", [0.0, 500000.0], None),
	("transaction_cost_definition", "The transaction cost",
	 "transaction_cost_usd_per_year",
	 "transaction_costs * total_revenue_usd_per_year",
	 "Transaction costs as a share of gross revenue: arranging, legal, and "
	 "disbursement. Charged on revenue rather than on capital because the "
	 "cost recurs with the revenue it is incurred to collect.",
	 "financial", "USD/year", [0.0, 1.0e12], None),
	("sovereign_risk_charge_definition", "The sovereign risk charge",
	 "sovereign_risk_charge_usd_per_year",
	 "sovereign_risk_premium * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The annual cost of the sovereign premium on the debt tranche: the "
	 "premium times the debt-financed capital. It is the *charge* and not "
	 "the rate, so a scenario can read what the sovereign exposure costs "
	 "the project in currency per year. The `1000` is kW per MW.",
	 "financial", "USD/year", [0.0, 1.0e12], "Damodaran (2026), Country Default Spreads and Risk Premiums"),
	("technology_risk_charge_definition", "The technology risk charge",
	 "technology_risk_charge_usd_per_year",
	 "technology_risk_premium * (1 - debt_fraction) * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The annual cost of the technology premium on the equity tranche: the "
	 "premium times the equity-financed capital. The `(1 - debt_fraction)` "
	 "is what puts it on the equity tranche and not the debt one -- the "
	 "lender does not carry technology risk, so charging it on the whole "
	 "capital would double-count it against the debt rate.",
	 "financial", "USD/year", [0.0, 1.0e12], None),
	("insurance_premium_pricing_definition", "The insurance premium",
	 "insurance_premium_usd_million",
	 "aal_usd_million * (1 + expense_loading + capital_loading + profit_margin)",
	 "The premium the insurer charges: the annual average loss grossed up by "
	 "the expense, capital, and profit loadings. FRM section 6.2 states "
	 "exactly this identity. The premium is priced off the expected loss "
	 "and not off the asset value, which is why `premium_share_of_asset` is "
	 "a different product rather than a second spelling of this one.",
	 "financial", "USD million", [0.0, 500000.0], None),
	("insurance_premiums_alias", "The insurance premium paid",
	 "insurance_premiums", "insurance_premium_usd_million",
	 "The premium the project pays, under the catalog's currency-denominated "
	 "id. The equality makes the pricing chain's output the quantity the "
	 "balance sheet reads.",
	 "financial", "USD million", [0.0, 500000.0], None),
	("solvency_capital_definition", "The solvency capital",
	 "solvency_capital", "pml_99_5_usd_million - aal_usd_million",
	 "Solvency capital: the tail loss net of expected loss. FRM section 6.3 "
	 "states it exactly so. It is the capital the insurer must hold to "
	 "survive the 99.5th-percentile event, and the AAL is subtracted "
	 "because the premium already funds the expected loss.",
	 "financial", "USD million", [-500000.0, 500000.0], None),
	("rab_roll_forward_definition", "The regulatory asset base roll-forward",
	 "rab_roll_forward",
	 "capex_usd_per_kw * total_capacity_mw / 1000 / asset_life - regulatory_depreciation",
	 "The annual movement in the regulatory asset base: the depreciation "
	 "the regulator allows on the fleet's capital, net of the depreciation "
	 "already booked. Both sides are flows in USD million per year, which is "
	 "what makes the roll-forward an addition to the base rather than a "
	 "replacement of it.",
	 "financial", "USD million/year", [-500000.0, 500000.0], None),
)

#: (equation id, lhs, rhs, prose, reference)
BATCH27_BOUNDS: tuple[tuple[str, str, str, str, str | None], ...] = (
	("llcr_floor_bound", "llcr_estimate", "loan_life_coverage_ratio",
	 "The loan-life coverage ratio is a covenant, not a reported figure: a "
	 "lender requires the present value of cash available for debt service "
	 "over the loan life to cover the outstanding debt by a stated margin. "
	 "Stating it as a bound makes the requirement a constraint the "
	 "conflict gate reads, which is what turns `llcr_estimate` from a "
	 "number into a test. Its edge carries the tier, so a scenario that "
	 "softens the covenant stops the gate blocking on it.",
	 None),
)


def build_batch27(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
	"""Batch 27: the finance family.

	Three groups, and the division is the batch's content.

	Four *aliases*: the catalog carries `interest_rate_debt`/`cost_of_debt`,
	`debt_service_coverage_ratio`/`dscr_min`, and
	`maladaptation_risk`/`risk_of_maladaptation` as pairs, and each pair is
	one number. The equality is the honest coupling, and the `derived` role is
	what stops a scenario setting a node an equation overrules.

	Six *products*: a share times the base it applies to. The microinsurance
	premium and the population it reaches, the ring-fenced asset, the
	transaction cost, and the two risk charges. The risk charges are split
	across tranches on purpose -- sovereign on the debt, technology on the
	equity -- because the premiums price different risks and charging both on
	the whole capital would double-count them.

	The *insurance chain* is the FRM's own three functions, shipped as
	identities: the premium as `aal * (1 + loadings)`, solvency capital as
	`pml - aal`, and the RAB roll-forward as a flow. The graph already
	carried `combined_ratio` and `loss_ratio` but none of the actuarial
	inputs those ratios are ratios *of*, so the ratios had nothing to divide.

	Two repairs ride along because the batch touches the nodes. The
	`currency_risk_premium` is wired into `cost_of_debt_priced` as FPE
	section 6 says it should be, rather than left as an unread node. And
	`ets_enabled` moves from 0.0 to 1.0: batch 24 shipped the switch off
	beside a live carbon price and a half coverage, so the graph booked
	carbon revenue while declaring no instrument and its own
	`carbon_revenue_without_an_instrument` rule fired at the defaults. The
	shipped graph contradicted itself at the values it shipped.

	The LLCR covenant is a *bound with an edge*. The other bounds in the
	graph carry no edge, so the conflict gate reads them at full strength
	and the tier mechanism cannot soften them; a covenant a lender can
	renegotiate should be softenable, and the edge is what makes it so.
	"""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, role, prose in BATCH27_RETYPES:
		# The emit path reads the already-baked document, so a re-emit after a
		# bake finds the node present. Reading the shipped body and overriding
		# the fields this batch owns keeps the two runs identical.
		shipped = graph.nodes.get(name)
		full = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": "Investment & Finance",
			"type": "float", "unit": unit, "range": rng, "role": role,
			"determinism": determinism, "priority": "P1", "status": "existing",
			"source": "The finance coupling (batch 27)",
			"users": ["Financiers", "Regulators"],
		})
		if role == "derived":
			full.pop("default", None)
		else:
			full["default"] = default
		nodes[name] = full

	for name, unit, rng, default, category, prose in BATCH27_BASES:
		shipped = graph.nodes.get(name)
		full = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "default": default, "role": "free",
			"determinism": "stochastic" if "aal" in name or "pml" in name else "policy",
			"priority": "P1", "status": "existing",
			"source": "The finance coupling (batch 27)",
			"users": ["Financiers", "Insurers"],
		})
		nodes[name] = full

	derived_units = {
		"interest_rate_debt": ("1/year", [0.0, 0.5]),
		"debt_service_coverage_ratio": ("1", [1.0, 3.0]),
		"maladaptation_risk": ("1", [0.0, 1.0]),
		"project_irr_hurdle": ("1/year", [0.0, 1.0]),
		"microinsurance_premium_usd_per_year": ("USD/year", [0.0, 1.0e6]),
		"microinsured_population": ("people", [0.0, 1.0e9]),
		"ring_fenced_asset_value_usd_million": ("USD million", [0.0, 500000.0]),
		"transaction_cost_usd_per_year": ("USD/year", [0.0, 1.0e12]),
		"sovereign_risk_charge_usd_per_year": ("USD/year", [0.0, 1.0e12]),
		"technology_risk_charge_usd_per_year": ("USD/year", [0.0, 1.0e12]),
		"insurance_premium_usd_million": ("USD million", [0.0, 500000.0]),
	}
	for name, (unit, rng) in derived_units.items():
		shipped = graph.nodes.get(name)
		full = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": (
				f"{name.replace('_', ' ')}: the finance family's derived "
				"quantity, computed by the equality below."
			),
			"category": "Investment & Finance", "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": "policy", "priority": "P1", "status": "existing",
			"source": "The finance coupling (batch 27)",
			"users": ["Financiers", "Regulators"],
		})
		full.pop("default", None)
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, unit, rng, cite in BATCH27_EQUATIONS:
		from alea.prg.dsl import parse_side

		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		if lhs in nodes:
			nodes[lhs]["unit"] = unit
			nodes[lhs]["range"] = rng
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the finance identity.",
				"reference": cite, "priority": "P1",
			})

	# FPE section 6 applies the currency premium to the cost of debt, not as a
	# separate cash-flow line. The shipped `cost_of_debt_priced` reads
	# `interest_rate + debt_spread`; this adds the third term.
	for eq_id, eid in (("cost_of_debt_priced", "currency_risk_premium"),):
		shipped = graph.equations.get(eq_id)
		if shipped is not None:
			equations[eq_id] = {
				"id": eq_id, "name": shipped.name,
				"description": (
					"The debt rate a scenario may carry: the policy rate plus "
					"the borrower spread plus the currency risk premium. FPE "
					"section 6 applies the currency premium to the cost of debt "
					"rather than as a separate cash-flow line, because a "
					"foreign-currency lender prices the FX exposure into the "
					"rate it charges."
				),
				"system": shipped.system,
				"lhs": "cost_of_debt",
				"rhs": "interest_rate + debt_spread + currency_risk_premium",
				"relation": "eq",
				"parameters": ["cost_of_debt", "interest_rate", "debt_spread", eid],
				"free_variables": [], "determined_variables": ["cost_of_debt"],
				"tolerance": 1.0e-09, "unit_check": True,
				"solution_method": "direct", "linearity": "linear",
				"priority": "P1", "reference": shipped.reference,
				"latex": r"\mathrm{see\ equation}",
			}
			edges.append({
				"source": eid, "target": "cost_of_debt",
				"equation_id": eq_id, "relationship": "functional",
				"direction": "forward", "strength": "hard",
				"description": "The FX premium enters the debt rate.",
				"reference": None, "priority": "P1",
			})

	for eq_id, lhs, rhs, prose, cite in BATCH27_BOUNDS:
		named = sorted(set(_side_symbols(lhs)) | set(_side_symbols(rhs)))
		equations[eq_id] = {
			"id": eq_id, "name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": "financial",
			"lhs": lhs, "rhs": rhs, "relation": "geq",
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		# A bound with an edge: the tier mechanism reads the edge, so a
		# scenario can soften a covenant it can renegotiate.
		edges.append({
			"source": rhs, "target": lhs, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				"The coverage a lender requires. A project can clear the "
				"physics and fail this."
			),
			"reference": cite, "priority": "P2",
		})
	return nodes, equations, edges, rules


def _kept_status(shipped: Any) -> str:
	"""A retype is not a lifecycle change, so the status stays what shipped.

	``to_build`` stays ``to_build`` -- the node still has no measurement, only
	a declared unit and a formula. ``deprecated`` stays ``deprecated`` and
	keeps its ``deprecated_by`` pointer, which the model refuses to accept
	beside ``existing``: a live node naming a replacement is two fields
	disagreeing about whether it is live. A node this batch creates is
	``existing``, because the equation is what brings it into being.
	"""
	return shipped.status if shipped is not None else "existing"


#: (name, unit, range, default, determinism, prose) -- the free bases the
#: products multiply against. Each shipped with unit None or 1 and the
#: 500000.0 placeholder, so the arithmetic the catalog states could not run.
BATCH28_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("contingency", "1", [0.0, 0.3], 0.10, "policy",
	 "The contingency allowance as a share of capex: the cover a project "
	 "carries for scope growth between financial close and completion. Ten "
	 "percent is the middle of the 5-15% band a lump-sum EPC contract's "
	 "owner's contingency sits in; the shipped 500000.0 was a placeholder "
	 "that made the allowance 6e12 USD."),
	("cash_sweep", "1", [0.0, 1.0], 0.5, "policy",
	 "The share of distributable cash swept to debt service. A sweep is a "
	 "lender's covenant, not a physical fact, so it is a policy dial: 100% "
	 "is a full cash sweep, 0% leaves the cash with the sponsor. Half is "
	 "the common sculpted-debt arrangement."),
	("investment_periods", "1", [1.0, 20.0], 5.0, "fixed",
	 "How many investment periods the horizon is cut into. A count, so the "
	 "unit is 1 and the range is integral in practice; five periods over a "
	 "twenty-five-year horizon is the standard multi-year capacity "
	 "expansion formulation (Tejada-Arango 2023)."),
	("tsam_segments", "1/day", [1.0, 96.0], 24.0, "fixed",
	 "Time-slice segments per day in the aggregated dispatch model. "
	 "Twenty-four hourly segments is the un-aggregated case; the unit is a "
	 "count per day so the segment length it implies is hours."),
	("dispatch_interval", "hour", [0.05, 24.0], 0.5, "fixed",
	 "The settlement and dispatch cadence: how many hours one dispatch "
	 "interval spans. Half-hourly is the European settlement default and "
	 "the finest cadence most balancing authorities settle at."),
	("load_shifting_capability", "hours", [0.0, 24.0], 2.0, "policy",
	 "How many hours the interruptible load can be shifted for. A duration, "
	 "not an energy: the shipped placeholder made it 500000 hours, which is "
	 "fifty-seven years of shifting from one demand block."),
	("fishing_community_load", "MW", [0.0, 30000.0], 5.0, "fixed",
	 "The load a fishing community draws: a small coastal settlement's "
	 "demand, in megawatts. The catalog carried it unitless with the "
	 "placeholder, so the conversion to annual energy it states divided a "
	 "placeholder by a million."),
	("islanding_capability", "1", [0.0, 1.0], 0.10, "policy",
	 "The share of primary feeders able to island with local generation. A "
	 "share of the 500 shipped feeders, so ten percent is fifty feeders; "
	 "the placeholder read as half a million times the feeder count."),
	("fuel_price_volatility", "1", [0.0, 1.0], 0.25, "stochastic",
	 "The fuel price's one-sigma excursion as a share of the base price. A "
	 "quarter is the width the risk cases use for a delivered gas price; "
	 "the band's upper edge is what a stress case reads."),
	("geothermal_drilling_success", "1", [0.05, 1.0], 0.75, "stochastic",
	 "The probability a drilled geothermal well is productive. The lower "
	 "bound is 5% and not 0 because the effective capex divides by it: a "
	 "zero success rate is an infinite cost per productive well, which is "
	 "the arithmetic saying no well is worth drilling rather than a cost."),
	("child_labour_prohibition", "1", [0.0, 1.0], 1.0, "policy",
	 "The share of the workforce screened against child labour. One is the "
	 "I LO core-convention standard a project covenant requires; a partial "
	 "screen is the finding, not the default."),
	("early_retirement_packages", "1", [0.0, 1.0], 0.02, "policy",
	 "The share of the workforce offered early retirement as a transition "
	 "instrument. Two percent is a targeted package rather than a general "
	 "reduction."),
	("pension_security", "1", [0.0, 1.0], 0.80, "policy",
	 "The share of the workforce covered by a pension. Coverage, not "
	 "adequacy: the graph carries no benefit-level quantity, and a share is "
	 "what a labour-standard audit reports."),
	("redeployment_options", "1", [0.0, 1.0], 0.10, "policy",
	 "The share of the workforce with a redeployment option into the "
	 "replacement activity. The instrument a just-transition plan counts, "
	 "and the count is what makes the plan checkable."),
	("social_protection_parameters", "1", [0.0, 1.0], 0.50, "policy",
	 "The share of the workforce under social protection (unemployment "
	 "insurance, health cover, injury compensation). Half is a middle-"
	 "income coverage rate."),
	("union_agreements", "1", [0.0, 1.0], 0.30, "policy",
	 "The share of the workforce covered by a collective agreement. A "
	 "coverage share, which is what an ILO labour-statistics table reports, "
	 "not a headcount."),
	("skills_requirements", "1", [0.0, 1.0], 0.30, "policy",
	 "The share of jobs that need a certified skill. Thirty percent is the "
	 "craft share of a construction-and-O&M workforce."),
	("skills_gap_assessment", "1", [0.0, 1.0], 0.30, "policy",
	 "The share of the skilled requirement the local labour market cannot "
	 "fill. Applied on top of `skills_requirements`, so the gap is a share "
	 "of a share and never exceeds the skilled requirement."),
	("retraining_costs", "USD/job", [0.0, 100000.0], 2000.0, "policy",
	 "Retraining cost per job. The catalog carried the node unitless with "
	 "the placeholder, so the spend it multiplies by the workforce was "
	 "500000 USD per job. Two thousand is the order a short vocational "
	 "conversion costs per worker."),
	("wage_levels_by_sector", "USD/job/year", [0.0, 1000000.0], 20000.0,
	 "fixed",
	 "The average wage per job per year. A rate, so the wage bill is the "
	 "workforce times it; the shipped node had no unit and the placeholder, "
	 "which priced the workforce at half a million dollars a head."),
	("community_health_safety", "1", [0.0, 0.05], 0.002, "policy",
	 "Community health-and-safety programme spend as a share of allowed "
	 "revenue. The same idiom the graph's own `consumer_protection_standards` "
	 "uses, so the programme cost is read against the revenue that funds it."),
	("complaint_handling", "1", [0.0, 0.05], 0.002, "policy",
	 "The complaint-handling programme's cost as a share of allowed "
	 "revenue."),
	("consumer_education", "1", [0.0, 0.05], 0.001, "policy",
	 "Consumer-education spend as a share of allowed revenue."),
	("cross_subsidy_transparency", "1", [0.0, 0.05], 0.0005, "policy",
	 "The cost of disclosing the cross-subsidy, as a share of allowed "
	 "revenue. Cheaper than the transfers it makes visible, which is the "
	 "point of publishing it."),
	("occupational_health_safety", "1", [0.0, 0.05], 0.005, "policy",
	 "Occupational health-and-safety spend as a share of allowed revenue. "
	 "The workforce-facing programme, distinct from the community-facing "
	 "one above."),
	("tariff_transparency", "1", [0.0, 0.05], 0.001, "policy",
	 "Tariff-publication and consultation cost as a share of allowed "
	 "revenue."),
	("vulnerable_customer_protection", "1", [0.0, 0.05], 0.002, "policy",
	 "The protection programme's cost as a share of allowed revenue: the "
	 "administration of lifeline eligibility and disconnection safeguards."),
	("community_transition_funding", "1", [0.0, 1.0], 0.10, "policy",
	 "The share of the community development fund earmarked for transition "
	 "support. Ten percent of an existing fund rather than a new levy, "
	 "because the graph already carries the fund."),
	("just_transition_fund", "1", [0.0, 0.05], 0.005, "policy",
	 "The just-transition levy as a share of gross revenue. Half a percent "
	 "is the order a transition surcharge sits at on a retail tariff."),
	("coal_community_dependencies", "1", [0.0, 1.0], 0.05, "fixed",
	 "The share of the exposed population whose livelihood depends on the "
	 "coal activity being retired. Five percent of the dispersion-range "
	 "population is the order a single-plant dependency reaches in a "
	 "district-scale economy."),
)

#: (name, unit, range, determinism, category, prose) -- every lhs of this
#: batch's identities. A node listed here is derived and carries no default.
BATCH28_DERIVED: tuple[tuple[str, str, list[float], str, str, str], ...] = (
	("customs_duty", "1", [0.0, 1.0], "fixed", "Tax & Fiscal",
	 "The customs duty rate, as a share of imported equipment value. The "
	 "catalog carries it as a second row for `import_duty_equipment`; the "
	 "equality is the whole content, and it is what stops a scenario "
	 "changing one rate and leaving the other at its old value."),
	("stamp_duty_usd", "USD", [0.0, 1.0e10], "policy", "Tax & Fiscal",
	 "The stamp duty on the property transfer: the rate times the asset "
	 "value. A transfer tax is charged once on the capital, not annually on "
	 "the revenue."),
	("performance_bond_usd", "USD", [0.0, 1.0e10], "policy",
	 "Contract & Legal",
	 "The performance bond a sponsor posts: a share of capex held against "
	 "non-completion. Capital, not a flow, because the bond is released "
	 "rather than spent."),
	("export_duty_usd_per_year", "USD/year", [0.0, 1.0e12], "policy",
	 "Tax & Fiscal",
	 "The export duty on the energy carrier sold abroad: the rate times "
	 "export revenue. Zero at the shipped rate of zero, which is a finding "
	 "about the fiscal regime rather than a missing number."),
	("withholding_tax_dividends_usd_per_year", "USD/year", [-1.0e12, 1.0e12],
	 "policy", "Tax & Fiscal",
	 "Withholding tax on distributed cash: the rate times the cash "
	 "available for debt service net of the debt service itself. Charged on "
	 "the distributable residual, which is what a dividend withholding tax "
	 "is levied on, so the range is signed: the base is that residual, and "
	 "a project whose service exceeds its cash flow distributes nothing and "
	 "the product is negative. The negative is the shortfall the DSCR "
	 "covenant reports, and a tax cannot be computed on a base the graph "
	 "refuses to form."),
	("withholding_tax_interest_usd_per_year", "USD/year", [0.0, 1.0e12],
	 "policy", "Tax & Fiscal",
	 "Withholding tax on interest paid: the rate times the debt tranche "
	 "times its rate. The tax base is the interest, so the debt rate enters "
	 "the product -- which is why the shipped equation was a rate with no "
	 "rate in it."),
	("claims_history", "USD/year", [0.0, 1.0e12], "stochastic",
	 "Insurance & Catastrophe",
	 "Incurred claims: the loss ratio applied to the premium. The shipped "
	 "node carried unit 1 and the placeholder, so an insurance loss was "
	 "dimensionless; the retype makes the loss ratio the ratio it is."),
	("deductible_levels", "USD", [0.0, 1.0e10], "policy",
	 "Insurance & Catastrophe",
	 "The deductible the project carries: the deductible share times the "
	 "asset value. A stock, because the deductible is a threshold on a "
	 "single event rather than an annual amount."),
	("reinsurance_parameters", "USD/year", [0.0, 1.0e10], "policy",
	 "Insurance & Catastrophe",
	 "The premium ceded to the reinsurer: the ceded share, `1 - "
	 "retention_share`, times the premium. Ceded and not retained, because "
	 "the node names the reinsurance and the retention share is the part "
	 "kept."),
	("contingency_allowance_usd", "USD", [0.0, 1.0e10], "policy", "Macro",
	 "The contingency allowance: the share times the capital cost. A "
	 "capital item, released or spent at completion, not an annual cost."),
	("cash_swept_usd_per_year", "USD/year", [-1.0e12, 1.0e12], "policy",
	 "Contract",
	 "The cash swept to debt service: the sweep share times the "
	 "distributable cash. Distributable is cash available for debt service "
	 "net of the service itself, so the sweep is applied to the residual "
	 "and the node is negative exactly when the service exceeds the cash. "
	 "The range is signed for the same reason `cfads_usd_per_kw_year` is: "
	 "the base is a difference of two quantities, and a lower bound of "
	 "zero would file the shortfall as a derived excursion rather than "
	 "leave it to the DSCR covenant that exists to report it."),
	("investment_period_length_years", "years", [0.5, 50.0], "fixed",
	 "Temporal",
	 "How long one investment period is: the horizon divided by the period "
	 "count. A discretisation, so it moves with both and neither is a "
	 "physical constant."),
	("tsam_segment_hours", "hours", [0.25, 24.0], "fixed", "Temporal",
	 "The length of one time-slice segment: a day divided by the segment "
	 "count. Twenty-four segments give hourly slices, which is the "
	 "un-aggregated case the segment count exists to depart from."),
	("dispatch_intervals_per_hour", "1/hour", [0.0, 48.0], "fixed",
	 "Operational",
	 "How many dispatch intervals one hour holds: the reciprocal of the "
	 "interval length. A cadence, so a shorter interval is a larger "
	 "number."),
	("load_shifting_energy_mwh", "MWh", [0.0, 1.0e6], "policy",
	 "Demand-Side",
	 "The energy the interruptible load can move: the shifting duration "
	 "times the interruptible capacity. Energy and not power, because the "
	 "capability is how long the block can stay off."),
	("fishing_community_load_twh", "TWh/year", [0.0, 100.0], "fixed",
	 "Demand",
	 "The fishing community's annual energy: its load in megawatts "
	 "converted at the graph's own 8760 hours and 1e6 MWh per TWh. The "
	 "conversion the catalog states, with the unit that makes it "
	 "dimensional."),
	("islanding_capable_feeders", "1", [0.0, 1.0e4], "policy",
	 "Reliability",
	 "The feeders able to island: the capability share times the primary "
	 "feeder count. A count of feeders, and the feeder node is itself "
	 "unitless -- the graph's own `adms_controlled_feeders` reads it the "
	 "same way."),
	("fuel_price_upper_usd_per_mwh", "USD/MWh", [0.0, 1.0e4], "stochastic",
	 "Costs",
	 "The upper edge of the fuel price band: the base price grossed up by "
	 "the volatility. The band's lower edge is the same product with the "
	 "sign reversed; this node is the stress case."),
	("geothermal_effective_capex_usd_per_kw", "USD/kW", [0.0, 1.0e6],
	 "stochastic", "Supply",
	 "The capex per productive kilowatt: the drilling cost divided by the "
	 "success rate. A dry hole is paid for and produces nothing, so the "
	 "cost of a *successful* well is the nominal capex grossed up by the "
	 "inverse success probability."),
	("import_dependency", "1", [-1.0, 1.0], "physical", "Geopol",
	 "Imports as a share of demand: net imports over total demand, in "
	 "absolute value because the net flow is signed and a large export "
	 "position is not a dependency. The shipped node was the placeholder."),
	("community_health_safety_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "EnvSoc",
	 "Community health-and-safety programme spend: the programme share "
	 "times allowed revenue. In the unit allowed revenue is in, so the "
	 "share reads as a fraction of the revenue cap."),
	("complaint_handling_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "Consumer",
	 "Complaint-handling programme spend: the share times allowed revenue."),
	("consumer_education_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "Consumer",
	 "Consumer-education spend: the share times allowed revenue."),
	("cross_subsidy_transparency_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "Consumer",
	 "The cost of publishing the cross-subsidy: the share times allowed "
	 "revenue."),
	("occupational_health_safety_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "EnvSoc",
	 "Occupational health-and-safety spend: the share times allowed "
	 "revenue."),
	("tariff_transparency_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "Consumer",
	 "Tariff transparency spend: the share times allowed revenue."),
	("vulnerable_customer_protection_spend_usd_per_year", "USD million/year",
	 [0.0, 1.0e3], "policy", "Consumer",
	 "Vulnerable-customer protection spend: the share times allowed "
	 "revenue."),
	("just_transition_fund_usd_per_year", "USD/year", [0.0, 1.0e12],
	 "policy", "JustTrans",
	 "The just-transition levy: the share times gross revenue. Charged on "
	 "revenue rather than on the community fund because it is a levy the "
	 "tariff funds, not an allocation of an existing programme."),
	("community_transition_funding_usd_per_year", "USD/year",
	 [0.0, 1.0e12], "policy", "JustTrans",
	 "The transition share of the community development fund: an "
	 "allocation inside a fund the graph already computes, which is why "
	 "its base is that fund and not revenue."),
	("coal_dependent_population", "people", [0.0, 1.0e9], "policy",
	 "JustTrans",
	 "The people whose livelihood depends on the coal activity: the "
	 "dependency share times the exposed population. The exposed "
	 "population is the dispersion-range population, so the count is the "
	 "coal district's dependency and not a national one."),
	("child_labour_screened_jobs", "jobs", [0.0, 1.0e8], "policy",
	 "JustTrans",
	 "The jobs screened against child labour: the screening share times the "
	 "direct workforce. A count of screened positions, so a scenario reads "
	 "how many jobs a partial screen leaves unexamined."),
	("early_retirement_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs offered early retirement: the share times the direct "
	 "workforce."),
	("pension_covered_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs covered by a pension: the coverage share times the direct "
	 "workforce."),
	("redeployed_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs with a redeployment option: the share times the direct "
	 "workforce. The count a just-transition plan is judged on."),
	("socially_protected_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs under social protection: the coverage share times the direct "
	 "workforce."),
	("unionised_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs covered by a collective agreement: the coverage share times "
	 "the direct workforce."),
	("skills_requirements_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The jobs needing a certified skill: the share times the direct "
	 "workforce."),
	("skills_gap_jobs", "jobs", [0.0, 1.0e8], "policy", "JustTrans",
	 "The skilled jobs the local market cannot fill: the gap share times "
	 "the skilled requirement. A share of a share, so the gap cannot exceed "
	 "the requirement it is a gap in."),
	("retraining_spend_usd", "USD", [0.0, 1.0e12], "policy", "JustTrans",
	 "The retraining bill: cost per job times the direct workforce. Charged "
	 "against the whole workforce rather than the gap, because the catalog's "
	 "form does -- and that is the conservative reading of a programme that "
	 "reaches everyone."),
	("wage_bill_usd_per_year", "USD/year", [0.0, 1.0e13], "fixed",
	 "JustTrans",
	 "The annual wage bill: the average wage times the direct workforce. "
	 "The quantity that makes a jobs claim a claim about income."),
	("community_benefit_sharing", "1", [0.0, 0.05], "fixed",
	 "Land Use & Community",
	 "The benefit-sharing share, under the catalog's second id. The "
	 "canonical node `community_benefit_share_of_revenue` is what the "
	 "revenue identity reads; the equality makes this the same number."),
	("community_development_funds", "1", [0.0, 0.03], "fixed",
	 "Land Use & Community",
	 "The community development fund share, under the catalog's second id. "
	 "`community_development_fund_share` is the node the fund's currency "
	 "amount is computed from."),
	("local_content_employment", "1", [0.0, 0.9], "fixed",
	 "JustTrans",
	 "The local employment share, under the catalog's second id. "
	 "`local_employment_share` is the canonical node, and `local_jobs` "
	 "already computes the count from it."),
	("indigenous_peoples_rights", "1", [0.0, 1.0], "fixed", "EnvSoc",
	 "Free, prior and informed consent, under the catalog's rights id. The "
	 "graph carries one FPIC score, `fpic_compliance_score`; a second "
	 "spelling of it is the coupling."),
	("undrip_compliance", "1", [0.0, 1.0], "fixed", "EnvSoc",
	 "UNDRIP compliance, measured by the same FPIC score. The declaration "
	 "has no separate index in the graph, and inventing one would be a "
	 "number with no observation behind it."),
	("biodiversity_impact", "1", [0.0, 1.0], "physical", "EnvSoc",
	 "The biodiversity loss: the intactness index before the project less "
	 "the index after. A loss, so it is zero when the two agree -- which is "
	 "what the shipped defaults say, and the honest reading of a graph that "
	 "has not been given a post-project survey."),
	("soil_contamination", "1", [0.0, 1.0], "physical", "EnvSoc",
	 "The soil contamination index, under the catalog's second id. One "
	 "index, so one equality."),
	("water_quality_impact", "1", [0.0, 1.0], "physical", "Sector",
	 "The water quality impact: one less the quality index. An index of 1 "
	 "is pristine water and an impact of 0; the complement is what a "
	 "scenario reads as the damage."),
	("cultural_heritage_impact", "1", [0.0, 1.0], "physical", "EnvSoc",
	 "The cultural heritage impact, under the catalog's second id: the "
	 "heritage impact score itself."),
	("land_use_conflicts", "1", [0.0, 1.0], "physical", "Land",
	 "The land use conflict index, under the catalog's second id."),
	("habitat_loss", "hectares", [0.0, 1.0e6], "physical", "EnvSoc",
	 "The habitat lost, in hectares: the extensive node "
	 "`habitat_loss_hectares` under the catalog's second id."),
	("land_use_change", "hectares", [0.0, 1.0e6], "physical", "EnvSoc",
	 "The land converted, in hectares: the same physical quantity as "
	 "habitat loss under the catalog's third name. Two ids and one survey, "
	 "so the equality is the coupling rather than a second measurement."),
	("pm25_emissions", "kt/year", [0.0, 1.0e4], "physical", "EnvSoc",
	 "Primary particulate emissions, in kilotonnes per year: the shipped "
	 "emission-rate node under the catalog's second id."),
	("cooling_water_demand", "m3/year", [0.0, 1.0e12], "physical", "Sector",
	 "Cooling water withdrawn, in cubic metres per year: the shipped "
	 "extensive node under the catalog's second id."),
	("resettlement_costs", "USD", [0.0, 1.0e12], "policy",
	 "Land Use & Community",
	 "The resettlement programme's cost, under the catalog's second id. "
	 "`resettlement_costs_total_usd` is the node the population, share and "
	 "per-person cost multiply into."),
	("land_acquisition_costs", "USD", [0.0, 1.0e11], "policy", "Land",
	 "The project's land bill, under the catalog's second id. The graph "
	 "computes it over `land_area_hectares`, the project's whole take; the "
	 "catalog's own row multiplies the same per-hectare cost by the "
	 "habitat-loss subset, which would price 500 of the 5,000 hectares and "
	 "call it the bill. The equality to `land_acquisition_cost_usd` is the "
	 "honest coupling and the subset form is the trap it avoids."),
	("plant_retirement_age", "years", [0.0, 100.0], "policy", "Supply",
	 "The age at which a plant retires: the asset life the graph already "
	 "carries. `remaining_useful_life` reads this node, so the equality is "
	 "what puts a retirement age behind the remaining-life arithmetic."),
	("load_factor_override", "1", [0.0, 1.0], "fixed", "Demand",
	 "A scenario's load factor, overriding the derived one. The equality "
	 "makes it the same number as `load_factor`; the node exists so a "
	 "scenario can name the override, and the coupling stops it drifting "
	 "from the load the graph computes."),
)

#: (equation id, name, lhs, rhs, prose, system, reference)
BATCH28_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str | None], ...
] = (
	# --- the fiscal register's products ---------------------------------
	("customs_duty_alias", "The customs duty rate",
	 "customs_duty", "import_duty_equipment",
	 "The catalog carries the equipment duty twice, as `customs_duty` and "
	 "as `import_duty_equipment`, at the same 10%. One rate, so one "
	 "equality: the import-duty cost identity already reads "
	 "`import_duty_equipment`, and this makes the second spelling the same "
	 "number rather than a second dial.",
	 "cost_accounting", "The catalog's own duplicate rows, resolved"),
	("stamp_duty_cost_definition", "The stamp duty",
	 "stamp_duty_usd", "stamp_duty * capex_usd_per_kw * total_capacity_mw * 1000",
	 "Stamp duty on the property transfer: the rate times the asset value. "
	 "The `1000` is kW per MW, the graph's own convention for turning a "
	 "per-kilowatt capital cost into the fleet's total.",
	 "cost_accounting",
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	("performance_bond_cost_definition", "The performance bond",
	 "performance_bond_usd",
	 "performance_bond * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The performance bond posted against non-completion: a share of capex. "
	 "It is capital tied up rather than spent, which is why the node is a "
	 "stock and the quantity is the asset value it is a share of.",
	 "cost_accounting", None),
	("export_duty_cost_definition", "The export duty",
	 "export_duty_usd_per_year",
	 "export_duty * hydrogen_export_revenue_usd_per_year",
	 "The duty on the energy carrier sold abroad: the rate times export "
	 "revenue. Zero at the shipped rate, which is a statement about the "
	 "fiscal regime -- the instrument exists and its rate is zero -- and "
	 "not a missing input.",
	 "cost_accounting",
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	("withholding_tax_dividends_cost_definition",
	 "The dividend withholding tax",
	 "withholding_tax_dividends_usd_per_year",
	 "withholding_tax_dividends * (cfads_usd_per_kw_year - "
	 "debt_service_usd_per_kw_year) * total_capacity_mw * 1000",
	 "Withholding tax on distributed cash: the rate times cash available "
	 "for debt service net of debt service. The base is the distributable "
	 "residual, so a project whose debt service exceeds its cash flow has "
	 "nothing to distribute and pays nothing.",
	 "cost_accounting",
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	("withholding_tax_interest_cost_definition",
	 "The interest withholding tax",
	 "withholding_tax_interest_usd_per_year",
	 "withholding_tax_interest * debt_fraction * capex_usd_per_kw * "
	 "cost_of_debt * total_capacity_mw * 1000",
	 "Withholding tax on interest paid: the rate times the debt tranche "
	 "times the debt rate. The tax base is interest, so the debt rate has "
	 "to appear -- a withholding rate multiplied by capital alone is a "
	 "rate with nothing to tax.",
	 "cost_accounting",
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	# --- the insurance register's products -------------------------------
	("claims_history_definition", "Incurred claims",
	 "claims_history",
	 "loss_ratio * insurance_premium_usd_per_kw_year * total_capacity_mw * 1000",
	 "Incurred claims: the loss ratio applied to the premium. The premium "
	 "is per kilowatt, so the fleet's premium is that times capacity times "
	 "1000 kW per MW, and the loss ratio is the share of it paid out.",
	 "financial", None),
	("deductible_levels_definition", "The deductible",
	 "deductible_levels",
	 "deductible_share * capex_usd_per_kw * total_capacity_mw * 1000",
	 "The deductible the project carries: the deductible share times the "
	 "asset value. The shipped equation for this product had unit 1 on the "
	 "result, which made an insurance threshold dimensionless.",
	 "financial", None),
	("reinsurance_ceded_definition", "The ceded premium",
	 "reinsurance_parameters",
	 "(1 - retention_share) * insurance_premium_usd_per_kw_year * "
	 "total_capacity_mw * 1000",
	 "The premium ceded to the reinsurer: the ceded share, one less the "
	 "retention share, times the premium. Ceded and not retained -- the "
	 "node names the reinsurance, and the retention share is the part the "
	 "primary insurer keeps.",
	 "financial", None),
	# --- the capital and cash products -----------------------------------
	("contingency_allowance_definition", "The contingency allowance",
	 "contingency_allowance_usd",
	 "contingency * capex_usd_per_kw * total_capacity_mw * 1000.0",
	 "The contingency allowance: the share times the capital cost. The "
	 "catalog's formula, with the shipped placeholder replaced by a share "
	 "-- at ten percent the allowance is 1.2 billion USD against a 12 "
	 "billion USD fleet, which is the order an owner's contingency is.",
	 "financial", None),
	("cash_sweep_definition", "The cash swept to debt service",
	 "cash_swept_usd_per_year",
	 "cash_sweep * (cfads_usd_per_kw_year - debt_service_usd_per_kw_year) "
	 "* total_capacity_mw * 1000",
	 "The cash swept to debt service: the sweep share times distributable "
	 "cash. Distributable is cash available for debt service net of the "
	 "service, so the sweep is applied to the residual and not to gross "
	 "cash flow.",
	 "financial", None),
	# --- temporal and operational scalars --------------------------------
	("investment_period_length_definition", "The investment period length",
	 "investment_period_length_years", "time_horizon / investment_periods",
	 "One investment period's length: the horizon divided by the period "
	 "count. A discretisation rather than a physical quantity, so it moves "
	 "when either input moves and is not a dial a scenario should set "
	 "directly.",
	 "energy_balance", "Tejada-Arango (2023), arXiv:2307.16842"),
	("tsam_segment_hours_definition", "The segment length",
	 "tsam_segment_hours", "24 / tsam_segments",
	 "The length of one time-slice segment: a day divided by the segment "
	 "count. The `24` is hours per day, which is why the segment count is "
	 "declared per day; at 24 segments the slice is hourly.",
	 "energy_balance", None),
	("dispatch_interval_definition", "The dispatch cadence",
	 "dispatch_intervals_per_hour", "1 / dispatch_interval",
	 "Dispatch intervals per hour: the reciprocal of the interval length. "
	 "A cadence, so a half-hour settlement gives two intervals an hour. "
	 "The reciprocal is the form the dispatch model reads, which is why "
	 "the node is declared in hours and the identity inverts it.",
	 "energy_balance", None),
	("load_shifting_energy_definition", "The shiftable energy",
	 "load_shifting_energy_mwh",
	 "load_shifting_capability * interruptible_load_mw",
	 "The energy the interruptible load can move: the shifting duration "
	 "times the interruptible capacity. Power times time is energy, which "
	 "is what a flexibility product is sold in.",
	 "demand_supply", None),
	("fishing_community_load_definition", "The fishing community's energy",
	 "fishing_community_load_twh",
	 "fishing_community_load * 8760 / 1000000",
	 "The fishing community's annual energy: its load in megawatts times "
	 "the hours in a year, divided by the megawatt-hours in a terawatt-"
	 "hour. The catalog's own conversion, made decidable by the unit.",
	 "demand_supply", None),
	("islanding_capable_feeders_definition", "The islanding-capable feeders",
	 "islanding_capable_feeders",
	 "islanding_capability * distribution_feeders_total",
	 "The feeders able to island: the capability share times the primary "
	 "feeder count. The graph's own `adms_controlled_feeders` reads the "
	 "same feeder node the same way, so a feeder count stays unitless "
	 "across both.",
	 "reliability", None),
	("fuel_price_band_definition", "The fuel price band's upper edge",
	 "fuel_price_upper_usd_per_mwh",
	 "fuel_price_usd_per_mwh * (1 + fuel_price_volatility)",
	 "The upper edge of the fuel price band: the base price grossed up by "
	 "the volatility share. The `1 +` is a growth factor, the same "
	 "convention every escalation in the library uses; the lower edge is "
	 "the same product with the sign reversed and is not shipped as a "
	 "separate node because it is a mirror rather than a measurement.",
	 "cost_accounting", None),
	("geothermal_effective_capex_definition",
	 "The geothermal capex per productive kilowatt",
	 "geothermal_effective_capex_usd_per_kw",
	 "capex_geothermal / geothermal_drilling_success",
	 "Capex per productive kilowatt: the nominal drilling cost divided by "
	 "the success probability. A dry hole is paid for and yields nothing, "
	 "so the cost of a successful well is the nominal cost times one over "
	 "the success rate -- at 75% success and 4,000 USD/kW, 5,333 USD per "
	 "productive kilowatt.",
	 "cost_accounting", None),
	("import_dependency_definition", "The import dependency",
	 "import_dependency", "net_imports_twh / demand_twh",
	 "Net imports as a share of demand, signed. The sign is the "
	 "information: a positive value is a dependency and a negative one is "
	 "an export position, which is the same ratio read the other way and "
	 "not a different quantity. The range admits negatives for that "
	 "reason. The catalog's form takes the absolute value, which would "
	 "report a large net exporter and a large net importer as equally "
	 "dependent -- and `abs` has no derivative rule in the DSL, correctly, "
	 "because it is non-differentiable at zero and the sensitivity kernel "
	 "differentiates every equation in the graph.",
	 "demand_supply", None),
	# --- programme spend against allowed revenue -------------------------
	("community_health_safety_spend_definition",
	 "Community health and safety spend",
	 "community_health_safety_spend_usd_per_year",
	 "community_health_safety * allowed_revenue_requirement",
	 "Community health-and-safety spend: the programme share times allowed "
	 "revenue. The graph's own `consumer_protection_spend_definition` is "
	 "this form, and the base is allowed revenue rather than gross revenue "
	 "because a regulated programme is funded out of the revenue cap.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("complaint_handling_spend_definition", "Complaint-handling spend",
	 "complaint_handling_spend_usd_per_year",
	 "complaint_handling * allowed_revenue_requirement",
	 "Complaint-handling spend: the share times allowed revenue.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("consumer_education_spend_definition", "Consumer education spend",
	 "consumer_education_spend_usd_per_year",
	 "consumer_education * allowed_revenue_requirement",
	 "Consumer-education spend: the share times allowed revenue.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("cross_subsidy_transparency_spend_definition",
	 "Cross-subsidy disclosure spend",
	 "cross_subsidy_transparency_spend_usd_per_year",
	 "cross_subsidy_transparency * allowed_revenue_requirement",
	 "The cost of disclosing the cross-subsidy: the share times allowed "
	 "revenue. The transfer it makes visible is already a node; this is "
	 "what it costs to publish.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("occupational_health_safety_spend_definition",
	 "Occupational health and safety spend",
	 "occupational_health_safety_spend_usd_per_year",
	 "occupational_health_safety * allowed_revenue_requirement",
	 "Occupational health-and-safety spend: the share times allowed "
	 "revenue. The workforce-facing programme, distinct from the "
	 "community-facing one.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("tariff_transparency_spend_definition", "Tariff transparency spend",
	 "tariff_transparency_spend_usd_per_year",
	 "tariff_transparency * allowed_revenue_requirement",
	 "Tariff-publication and consultation spend: the share times allowed "
	 "revenue.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	("vulnerable_customer_protection_spend_definition",
	 "Vulnerable-customer protection spend",
	 "vulnerable_customer_protection_spend_usd_per_year",
	 "vulnerable_customer_protection * allowed_revenue_requirement",
	 "Vulnerable-customer protection spend: the share times allowed "
	 "revenue. The programme administers lifeline eligibility and "
	 "disconnection safeguards; the transfers themselves are the "
	 "affordability system's.",
	 "cost_accounting", "World Bank Regulation of Utilities handbook, revenue caps"),
	# --- just transition ------------------------------------------------
	("just_transition_fund_definition", "The just-transition levy",
	 "just_transition_fund_usd_per_year",
	 "just_transition_fund * total_revenue_usd_per_year",
	 "The just-transition levy: the share times gross revenue. A levy the "
	 "tariff funds, which is why its base is gross revenue and not the "
	 "community development fund -- that fund is a separate allocation "
	 "with its own share.",
	 "employment", "Benefit-sharing programmes (the graph's own revenue identity)"),
	("community_transition_funding_definition",
	 "The transition share of the community fund",
	 "community_transition_funding_usd_per_year",
	 "community_transition_funding * community_development_fund_usd_per_year",
	 "The transition share of the community development fund: an "
	 "allocation inside a fund the graph already computes. Its base is "
	 "that fund rather than revenue, so the two transition instruments do "
	 "not double-count the same tariff revenue.",
	 "employment", "Benefit-sharing programmes (the graph's own revenue identity)"),
	("coal_dependent_population_definition", "The coal-dependent population",
	 "coal_dependent_population",
	 "coal_community_dependencies * exposed_population",
	 "The people whose livelihood depends on the coal activity being "
	 "retired: the dependency share times the exposed population. The "
	 "exposed population is the dispersion-range population, so this is "
	 "the coal district's dependency rather than a national one -- and "
	 "the count is what a transition plan's compensation is sized on.",
	 "employment", None),
	# --- employment shares ----------------------------------------------
	("child_labour_screening_definition", "The screened jobs",
	 "child_labour_screened_jobs", "child_labour_prohibition * direct_jobs",
	 "Jobs screened against child labour: the screening share times the "
	 "direct workforce. The count matters because a partial screen is the "
	 "compliance finding, and a share alone hides how many positions it "
	 "leaves unexamined.",
	 "employment", "IRENA employment factors"),
	("early_retirement_definition", "The early-retirement jobs",
	 "early_retirement_jobs", "early_retirement_packages * direct_jobs",
	 "Jobs offered early retirement: the share times the direct "
	 "workforce. The instrument a just-transition plan counts, and the "
	 "count is what makes the plan checkable.",
	 "employment", None),
	("pension_coverage_definition", "The pension-covered jobs",
	 "pension_covered_jobs", "pension_security * direct_jobs",
	 "Jobs covered by a pension: the coverage share times the direct "
	 "workforce. Coverage, not adequacy -- the graph carries no "
	 "benefit-level quantity, and a share is what a labour-standard audit "
	 "reports.",
	 "employment", None),
	("redeployment_definition", "The redeployed jobs",
	 "redeployed_jobs", "redeployment_options * direct_jobs",
	 "Jobs with a redeployment option: the share times the direct "
	 "workforce.",
	 "employment", None),
	("social_protection_definition", "The socially protected jobs",
	 "socially_protected_jobs", "social_protection_parameters * direct_jobs",
	 "Jobs under social protection: the coverage share times the direct "
	 "workforce.",
	 "employment", None),
	("union_coverage_definition", "The unionised jobs",
	 "unionised_jobs", "union_agreements * direct_jobs",
	 "Jobs covered by a collective agreement: the coverage share times the "
	 "direct workforce. A coverage share is what a labour-statistics "
	 "table reports, which is why the node is a share and the count is "
	 "derived.",
	 "employment", None),
	("skills_requirements_definition", "The skilled jobs",
	 "skills_requirements_jobs", "skills_requirements * direct_jobs",
	 "Jobs needing a certified skill: the share times the direct "
	 "workforce.",
	 "employment", None),
	("skills_gap_definition", "The unfilled skilled jobs",
	 "skills_gap_jobs",
	 "skills_gap_assessment * skills_requirements * direct_jobs",
	 "The skilled jobs the local labour market cannot fill: the gap share "
	 "times the skilled requirement. A share of a share, so the gap cannot "
	 "exceed the requirement it is a gap in -- which the shipped form, "
	 "with both shares as placeholders, could not express.",
	 "employment", None),
	("retraining_spend_definition", "The retraining bill",
	 "retraining_spend_usd", "retraining_costs * direct_jobs",
	 "The retraining bill: cost per job times the direct workforce. "
	 "Charged against the whole workforce rather than the gap, because "
	 "the catalog's form does -- the conservative reading of a programme "
	 "that reaches everyone.",
	 "employment", None),
	("wage_bill_definition", "The wage bill",
	 "wage_bill_usd_per_year", "wage_levels_by_sector * direct_jobs",
	 "The annual wage bill: the average wage per job times the direct "
	 "workforce. The quantity that turns a jobs claim into a claim about "
	 "income -- at 20,000 USD a job the 43,000-job fleet pays 860 million "
	 "USD a year, about 13% of gross revenue.",
	 "employment", None),
	# --- the environmental and social registers' aliases -----------------
	("community_benefit_sharing_alias", "The benefit-sharing share",
	 "community_benefit_sharing", "community_benefit_share_of_revenue",
	 "The benefit-sharing share under the catalog's second id. The "
	 "revenue identity `benefit_sharing_from_revenue_definition` reads "
	 "`community_benefit_share_of_revenue`; this equality makes the two "
	 "names one number.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("community_development_funds_alias", "The community fund share",
	 "community_development_funds", "community_development_fund_share",
	 "The community development fund share under the catalog's second id. "
	 "The fund's currency amount is computed from "
	 "`community_development_fund_share`, so this is the same share.",
	 "financial", "The catalog's own duplicate rows, resolved"),
	("local_content_employment_alias", "The local employment share",
	 "local_content_employment", "local_employment_share",
	 "The local employment share under the catalog's second id. "
	 "`local_jobs` already computes the count from "
	 "`local_employment_share`; a second share node would let a scenario "
	 "move the share and leave the count behind.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("indigenous_peoples_rights_alias", "The FPIC score",
	 "indigenous_peoples_rights", "fpic_compliance_score",
	 "Free, prior and informed consent under the catalog's rights id. The "
	 "graph carries one FPIC score, and `fpic_consent_bound` reads it; "
	 "this equality is what makes the second id the same score.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("undrip_compliance_alias", "The UNDRIP compliance score",
	 "undrip_compliance", "fpic_compliance_score",
	 "UNDRIP compliance measured by the same FPIC score. The declaration "
	 "has no separate index in the graph, and inventing one would be a "
	 "number with no observation behind it -- so the equality states the "
	 "identification rather than implying a second measurement.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("biodiversity_impact_definition", "The biodiversity loss",
	 "biodiversity_impact",
	 "biodiversity_intactness_before - biodiversity_intactness_index",
	 "The biodiversity loss: intactness before the project less intactness "
	 "after. A loss, so it is zero when the two agree -- which is what the "
	 "shipped defaults say, and the honest reading of a graph that has not "
	 "been given a post-project survey.",
	 "employment", None),
	("soil_contamination_alias", "The soil contamination index",
	 "soil_contamination", "soil_contamination_index",
	 "The soil contamination index under the catalog's second id. One "
	 "index, so one equality.",
	 "health", "The catalog's own duplicate rows, resolved"),
	("water_quality_impact_definition", "The water quality impact",
	 "water_quality_impact", "1.0 - water_quality_index",
	 "The water quality impact: one less the quality index. An index of 1 "
	 "is pristine water and an impact of 0, so the complement is what a "
	 "scenario reads as the damage -- and the `1.0` is the top of the "
	 "index's own scale, not a fitted constant.",
	 "water_energy", None),
	("cultural_heritage_impact_alias", "The cultural heritage impact",
	 "cultural_heritage_impact", "cultural_heritage_impact_score",
	 "The cultural heritage impact under the catalog's second id: the "
	 "heritage impact score itself.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("land_use_conflicts_alias", "The land use conflict index",
	 "land_use_conflicts", "land_use_conflict_index",
	 "The land use conflict index under the catalog's second id.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("habitat_loss_alias", "The habitat lost",
	 "habitat_loss", "habitat_loss_hectares",
	 "The habitat lost, in hectares: the extensive node under the "
	 "catalog's second id. A second id for one survey is a second id, not "
	 "a second measurement.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("land_use_change_alias", "The land converted",
	 "land_use_change", "habitat_loss_hectares",
	 "The land converted, in hectares: the same physical quantity as "
	 "habitat loss under the catalog's third name. The equality is the "
	 "identification, and it is what stops a scenario reporting habitat "
	 "loss and land use change as two different numbers for one site.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("pm25_emissions_alias", "The particulate emissions",
	 "pm25_emissions", "pm25_kt_per_year",
	 "Primary particulate emissions, in kilotonnes per year: the shipped "
	 "emission-rate node under the catalog's second id. The health system "
	 "reads the rate, so the equality is what puts the alias on the same "
	 "emissions.",
	 "health", "The catalog's own duplicate rows, resolved"),
	("cooling_water_demand_alias", "The cooling water withdrawn",
	 "cooling_water_demand", "cooling_water_demand_m3",
	 "Cooling water withdrawn, in cubic metres per year: the shipped "
	 "extensive node under the catalog's second id. The water-energy "
	 "system computes the volume from generation and an intensity, and "
	 "this is that volume under its second name.",
	 "water_energy", "The catalog's own duplicate rows, resolved"),
	("resettlement_costs_alias", "The resettlement cost",
	 "resettlement_costs", "resettlement_costs_total_usd",
	 "The resettlement programme's cost under the catalog's second id. The "
	 "total is population times share times per-person cost; this is the "
	 "same total under its second name.",
	 "employment", "The catalog's own duplicate rows, resolved"),
	("land_acquisition_costs_alias", "The land bill",
	 "land_acquisition_costs", "land_acquisition_cost_usd",
	 "The project's land bill under the catalog's second id. The graph "
	 "computes it over `land_area_hectares`, the project's whole take; the "
	 "catalog's own row multiplies the same per-hectare cost by the "
	 "habitat-loss subset, which would price 500 of the 5,000 hectares "
	 "and call it the bill. The equality is the honest coupling, and the "
	 "subset form is the trap it avoids.",
	 "cost_accounting", "The catalog's own duplicate rows, resolved"),
	("plant_retirement_age_alias", "The retirement age",
	 "plant_retirement_age", "asset_life",
	 "The age at which a plant retires: the asset life the graph already "
	 "carries. `remaining_useful_life` reads this node, so the equality is "
	 "what puts a retirement age behind the remaining-life arithmetic "
	 "instead of leaving it a number nothing consumes.",
	 "reliability", "The catalog's own duplicate rows, resolved"),
	("load_factor_override_alias", "The load factor override",
	 "load_factor_override", "load_factor",
	 "A scenario's load factor, overriding the derived one. The equality "
	 "makes it the same number as `load_factor`; the node exists so a "
	 "scenario can name the override, and the coupling stops it drifting "
	 "from the load the graph computes.",
	 "energy_balance", "The catalog's own duplicate rows, resolved"),
)


def build_batch28(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""Batch 28: the product remainder -- 59 nodes, and what holds them.

	The catalog's PRODUCT class is a row with a formula and, in fifty-four
	cases, a unit of ``None`` and the 500000.0 placeholder where a share or a
	rate should be. The formula is right and the node it multiplies against
	cannot be read, so the whole row is a claim with no arithmetic. This
	batch replaces the placeholder, declares the unit, and ships the identity
	the catalog states.

	Five groups, and the division is the batch's content.

	The *fiscal register*: five rates that were declared and multiplied by
	nothing -- the stamp duty, the performance bond, the export duty and the
	two withholding taxes -- plus the customs duty, which is the catalog's
	second id for the import duty and so an equality. Each product carries
	the base its own tax law names: the bond and the stamp duty on capital,
	the export duty on export revenue, the dividend withholding on the
	distributable residual, and the interest withholding on the debt
	tranche times its rate. That last one is the finding: the shipped row
	multiplied a withholding rate by capital and never by the interest, so
	it was a tax with nothing to tax.

	The *insurance register*: the incurred claims, the deductible and the
	ceded premium. The premium per kilowatt is the graph's own, so each
	product is that premium (or the asset value) times the share the
	insurance policy sets. Batch 27 shipped the pricing chain; these are the
	three quantities a policyholder reads off it.

	The *temporal and operational scalars*: the investment period length,
	the time-slice segment, the dispatch cadence, the shiftable energy, the
	fishing community's annual energy, the islanding feeder count, the fuel
	price band and the geothermal capex per productive kilowatt. Each is a
	discretisation or a conversion, and each was a placeholder. Two are
	worth naming: the geothermal one divides by a success probability, so
	its range starts at 0.05 rather than 0 -- a zero success rate is an
	infinite cost per productive well, which is the arithmetic refusing the
	question rather than answering it; and the fuel band is the upper edge
	only, because the lower edge is its mirror and a mirror is not a
	measurement.

	The *programme spend* against allowed revenue: seven consumer-protection
	and community programmes, each a share of the revenue cap. The graph
	already had this idiom once, in `consumer_protection_spend_definition`,
	and these are the programmes the catalog names beside it.

	The *employment and transition* layer: ten shares against the direct
	workforce and two transition instruments. The counts matter more than
	the shares because a compliance finding is a count of positions, and a
	share alone hides how many jobs a partial screen leaves unexamined. The
	two transition instruments are deliberately on different bases -- the
	levy on gross revenue, the funding on the community development fund --
	so they do not tax the same revenue twice.

	Finally the *alias register*: seventeen rows the catalog carries twice
	or three times. Each equality makes the second spelling the same
	number, and the ones that matter are the ones where a second spelling
	would let a scenario move a share and leave the count computed from the
	old one behind. One alias is a correction rather than a duplicate: the
	catalog prices the land bill over the habitat-loss subset of the site
	rather than the whole take, and the equality to the graph's own
	`land_acquisition_cost_usd` is what stops 500 of 5,000 hectares being
	reported as the project's land bill.

	One row is deliberately *not* here. `cross_border_trading` is the
	catalog's deprecated id for `cross_border_trade_allowed`, and the graph
	refuses any edge into a deprecated node -- `_deprecated_reach` is the
	contract that a node with a replacement is not read, and an alias edge
	is exactly the read it forbids. The two rows disagree about whether the
	node is live; the graph's answer is the one that counts, so the id stays
	deprecated and uncoupled. The same holds for `demand_growth_rate`.

	The systems are the library's, and the library has no environment
	system. The physical-health indices ride `health` and the social-licence
	ones ride `employment`, which is the system the library's own docstring
	calls "a claim about people". A reviewer who disagrees with that
	assignment has a one-word edit to make; a node with no system at all
	would have failed the load.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH28_RETYPES:
		# The emit path reads the already-baked document, so a re-emit after a
		# bake finds the node present. Reading the shipped body and overriding
		# the fields this batch owns keeps the two runs identical.
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": "free", "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product coupling (batch 28)",
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, determinism, category, prose in BATCH28_DERIVED:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product coupling (batch 28)",
			"users": ["Planners", "Regulators"],
		})
		full.pop("default", None)
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, cite in BATCH28_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		assert lhs in nodes, f"{eq_id}: {lhs!r} has no node body in this batch"
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})
	return nodes, equations, edges, rules


#: (name, unit, range, default, determinism, prose) -- the demand-side bases
#: and intensities that shipped unitless at the 500000.0 placeholder. Each is
#: a scenario input with a published range; the default is the middle of the
#: band the node's own prose names, not a measurement.
BATCH29_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("desalination_capacity", "m3/year", [0.0, 2.0e9], 5.0e7, "fixed",
	 "Desalination capacity as an annual water volume, which is how the "
	 "catalog states it (Mm3/year). Retyped from None: a capacity that "
	 "multiplies an intensity in kWh/m3 has to be a volume, and a nameplate "
	 "in MW would make the product an energy per unit of power. The 50 "
	 "Mm3/year default is a large coastal plant, about 137,000 m3/day; the "
	 "2 km3/year ceiling is the catalog's own 0-2000 Mm3/year bound and "
	 "four times the world's largest plant."),
	("desalination_energy", "kWh/m3", [2.0, 10.0], 4.0, "fixed",
	 "Specific energy consumption of the desalination process, in kWh per "
	 "cubic metre of product water. Reverse osmosis sits at 2-6 kWh/m3 with "
	 "energy recovery and thermal processes at 10-25, so the band is the RO "
	 "range's top meeting the thermal range's bottom; the default 4 is a "
	 "brackish-to-seawater RO plant and is the catalog's own what-if value. "
	 "Retyped from None."),
	("aviation_fuel_demand", "MWh/year", [0.0, 2.0e7], 3.0e6, "fixed",
	 "Aviation fuel loaded in the year, on a lower-heating-value energy "
	 "basis. Retyped from None: the SAF share multiplies it, and a share of "
	 "a unitless number is a unitless number. 3 TWh is about 250 kt of jet "
	 "fuel, a domestic-and-regional volume rather than a hub's throughput; "
	 "the 20 TWh ceiling is seven times that, enough for a decade of growth "
	 "on a single-country market."),
	("shipping_fuel_demand", "MWh/year", [0.0, 2.0e7], 2.0e6, "fixed",
	 "Marine bunker fuel loaded in the year, on an LHV energy basis. "
	 "Retyped from None for the same reason as aviation: the green-fuel "
	 "share needs a dimensioned base. 2 TWh is about 170 kt of heavy fuel "
	 "oil; the ceiling is ten times the shipped value and the top of a "
	 "single-country bunker market."),
	("transport_logistics", "tonne*km/year", [0.0, 1.0e12], 45.0e9, "fixed",
	 "Freight tonne-kilometres moved in the year: the base the batch-20 "
	 "freight share was deferred for. Retyped from None to tonne*km/year. "
	 "45 bn tonne-km at 45 M people is about 1,000 tonne-km per person, the "
	 "low end of the middle-income band; the 1e12 ceiling is twenty times "
	 "that and above any single country's freight task."),
	("heat_pump_cop", "1", [2.0, 6.0], 3.5, "fixed",
	 "Coefficient of performance: heat delivered per unit of electricity. "
	 "Retyped from None to dimensionless with the catalog's own default. "
	 "Below 2 a heat pump is a resistive heater with extra steps, and 6 is "
	 "the top of the ground-source range at mild ambient. Held as a "
	 "constant rather than a temperature curve because the graph's "
	 "temperature_increase is itself a placeholder with no unit, and a "
	 "curve over a placeholder is a curve over nothing."),
	("industrial_heat_demand", "TWh/year", [0.0, 200.0], 20.0, "fixed",
	 "Industrial process heat in the year, on a thermal basis. Retyped from "
	 "None to the catalog's own TWh/year. The 20 TWh default is a scenario "
	 "assumption -- about 1.7 times the graph's industrial electricity "
	 "demand -- and it is an assumption, not a measurement: the "
	 "heat-to-electricity ratio of an industrial base is a survey result "
	 "this repository does not hold. The ceiling narrows the catalog's "
	 "0-500 to 200 TWh, several times the graph's whole electricity demand."),
	("irrigation_pumping_demand", "TWh/year", [0.0, 20.0], 0.5, "fixed",
	 "The electricity irrigation pumping draws in the year. Retyped from "
	 "None to the catalog's own TWh/year; the 0.5 TWh default is 15% of the "
	 "graph's agricultural demand, which is the fraction the sector's own "
	 "pumping is usually taken to be -- stated as a scenario input, not "
	 "derived. The 20 TWh ceiling is 43% of the whole system's demand at "
	 "defaults, which is already an implausibly irrigation-heavy economy."),
	("currency_hedge_cost", "1/year", [0.0, 0.2], 0.03, "policy",
	 "The annual cost of hedging currency exposure, as a share of the "
	 "notional hedged: the forward premium plus the dealer spread. A rate, "
	 "so the charge is rate times notional and the notional is built from "
	 "the debt the project actually carries. Retyped from None."),
	("lpg_subsidies", "USD/kg", [0.0, 5.0], 0.5, "policy",
	 "The subsidy per kilogram of LPG, in currency. A per-unit rate, "
	 "matching the three electricity subsidy siblings, which are all "
	 "USD/MWh, so the spend is rate times volume across the whole subsidy "
	 "family. Retyped from None; the 5 USD/kg ceiling is the full retail "
	 "price of a cylinder."),
)

#: (name, unit, range, default, category, prose) -- the free bases the
#: products above multiply against. A base is a level the graph did not
#: carry; each defaults to zero or to the order the node's prose names.
BATCH29_BASES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("railway_route_km", "km", [0.0, 5.0e4], 2000.0, "Transport",
	 "The route length of the national rail network, in kilometres: the "
	 "base the railway electrification share was waiting for. 2,000 "
	 "route-km is a single-country network of the size the graph's other "
	 "bases assume (45,000 distribution circuit-km, 12,000 "
	 "transmission-km). Free with a default, following the extensive-bases "
	 "idiom the supply batches use."),
	("protected_area_fraction", "1", [0.0, 1.0], 0.0, "Environmental",
	 "The share of the project footprint that falls inside a protected "
	 "area. Default 0 because no protected-area layer is in the graph: a "
	 "default of 0.17 would claim a sixth of every project sits inside a "
	 "designation, which is a fabricated measurement. The range admits any "
	 "measured overlap."),
	("remittance_income_share", "1", [0.0, 0.5], 0.05, "Macro",
	 "The share of household income arriving as remittance transfers. 5% "
	 "is the order remittance-receiving economies show; the range admits "
	 "up to half, the ceiling for a household that is mostly "
	 "transfer-funded."),
	("strategic_reserve_days", "day", [0.0, 365.0], 90.0, "Energy Security",
	 "The strategic stock cover the policy declares, in days. 90 days is "
	 "the IEA emergency-stockholding convention; the range runs to a full "
	 "year so a policy that declares more is expressible rather than "
	 "clipped."),
	("foreign_currency_debt_share", "1", [0.0, 1.0], 0.6, "Finance",
	 "The share of the debt stock denominated in foreign currency: the "
	 "notional that needs hedging. 60% is the order for an emerging-market "
	 "project financed in hard currency."),
	("lpg_use_kg_per_household_year", "kg/year", [0.0, 1000.0], 150.0,
	 "Households",
	 "LPG burnt by a household that uses it: roughly a 12.5 kg cylinder "
	 "every five weeks. A mass balance, not a measurement."),
	("weather_derivative_notional_share", "1", [0.0, 1.0], 0.1, "Finance",
	 "The share of revenue hedged with weather derivatives. A policy "
	 "dial, defaulted at a tenth of revenue."),
)

#: (name, unit, range, determinism, category, prose) -- nodes an equation in
#: this batch determines. No default: the equation is the value, and a
#: default is a number that stands in whenever the equation is not run.
BATCH29_DERIVED: tuple[tuple[str, str, list[float], str, str, str], ...] = (
	("archaeological_sites", "sites", [0.0, 1500.0], "stochastic",
	 "Environmental",
	 "Expected count of recorded archaeological sites inside the project "
	 "footprint: the measured site density per 100 km2 times the land take "
	 "converted to the density's own denominator. Retyped from None to a "
	 "count; a fractional value is the expectation, not a count of objects, "
	 "which is what a survey budget needs. The 1,500 ceiling is the image "
	 "of the density's 30 per 100 km2 over a 500,000 ha land take."),
	("sacred_sites", "sites", [0.0, 1000.0], "stochastic", "Environmental",
	 "Expected count of sacred and culturally significant sites inside the "
	 "project footprint. Same construction as archaeological_sites on the "
	 "sacred-site density layer, so a siting decision can compare the two "
	 "exposures directly. The two layers are separate measurements and stay "
	 "separable rather than being summed into one heritage count."),
	("protected_areas", "hectare", [0.0, 500000.0], "policy",
	 "Environmental",
	 "Hectares of the project footprint falling inside a protected area: "
	 "the overlap share times the land take. An area rather than a count, "
	 "because what a designation constrains is the ground you may disturb, "
	 "not the number of sites. Retyped from None to hectare."),
	("parametric_insurance", "USD million", [0.0, 500000.0], "policy",
	 "Finance",
	 "The loss a parametric instrument pays out in an average year: the "
	 "share of the loss its trigger covers times the expected annual loss. "
	 "Priced against aal_usd_million, the base the finance batches already "
	 "ship, so the payout and the premium that covers it sit on one base. "
	 "Retyped from the dimensionless placeholder."),
	("remittance_flows", "USD/year", [0.0, 5.0e13], "stochastic", "Macro",
	 "Remittances received per year: the share of household income "
	 "arriving as transfers, times household income, times the number of "
	 "households. Measured against the household income base rather than "
	 "GDP, because remittances are a household transfer and the household "
	 "base is the one the graph carries. Retyped from None."),
	("strategic_reserves", "TWh", [0.0, 20000.0], "policy",
	 "Energy Security",
	 "The strategic stock held, as a volume of energy: the days of cover "
	 "the policy declares, times annual demand, over the days in a year. "
	 "Days of total demand, not days of net imports: the IEA convention is "
	 "import cover, and net_imports_twh is signed and zero at defaults, so "
	 "an import-based stock would need an abs the DSL cannot "
	 "differentiate. Retyped from None to TWh."),
	("weather_derivatives", "USD/year", [0.0, 1.0e12], "policy", "Finance",
	 "The notional of the weather hedge carried, in currency per year: the "
	 "share of revenue the firm hedges, times revenue. A notional against "
	 "revenue rather than a weather-sensitive revenue base, because the "
	 "revenue the derivative protects is the revenue the firm actually "
	 "books. Retyped from the dimensionless placeholder."),
	("desalination_demand", "MWh/year", [0.0, 2.0e7], "fixed", "Water",
	 "The electricity a desalination programme draws: the annual water "
	 "volume times the specific energy of the process. The intensity node "
	 "carries the process choice and this node carries the scale. 200,000 "
	 "MWh/year at the 50 Mm3 and 4 kWh/m3 defaults; the 20 TWh ceiling is "
	 "the 2 km3 capacity ceiling at the top of the intensity band."),
	("agricultural_irrigation_load", "MW", [0.0, 5000.0], "fixed",
	 "Agriculture",
	 "The average power irrigation pumping draws: the annual pumping "
	 "energy converted to MWh and divided by the year's hours. An average "
	 "and not a peak -- a load that runs in daylight and in season has a "
	 "peak well above it, and the graph carries one annual energy figure. "
	 "57.1 MW at the 0.5 TWh default; the 5 GW ceiling is four times that "
	 "and still under a tenth of the system's peak."),
	("hydrogen_export_port", "MW", [0.0, 1000.0], "fixed", "Transport",
	 "The export terminal's average throughput in megawatts: the annual "
	 "hydrogen energy the terminal loads, spread over the year. A port is "
	 "not a nameplate -- the berth count and the storage inventory are the "
	 "other two readings and the graph carries neither. 2.28 MW at the "
	 "20,000 MWh/year default."),
	("temporary_camp_load", "MW", [0.0, 500.0], "fixed", "Households",
	 "The power a resettlement camp draws: the displaced population, "
	 "divided by household size to get households, times the consumption "
	 "an energy-poor household actually draws, spread over the year. 0.89 "
	 "MW at defaults -- 100,000 displaced people in 22,222 households."),
	("household_batteries", "1", [0.0, 1.0e8], "fixed", "Households",
	 "Household battery systems installed: the adoption share times the "
	 "household count. A count a report can name -- 500,000 at defaults -- "
	 "rather than a share of nothing, which is what the adoption node was "
	 "before this equation."),
	("electrified_route_km", "km", [0.0, 5.0e4], "fixed", "Transport",
	 "Electrified route-kilometres: the electrification share times the "
	 "rail network's route length. 400 km at defaults. The share was inert "
	 "because the base it is a share of did not exist."),
	("freight_electric_tonne_km", "tonne*km/year", [0.0, 1.0e12], "fixed",
	 "Transport",
	 "Freight tonne-kilometres moved electrically: the freight "
	 "electrification share times total tonne-km. 2.25 bn tonne-km at "
	 "defaults, against a 45 bn total."),
	("synthetic_aviation_fuel_mwh", "MWh/year", [0.0, 2.0e7], "fixed",
	 "Transport",
	 "Synthetic aviation fuel loaded in the year: the SAF share times "
	 "aviation fuel demand. 150,000 MWh at defaults. The share needed a "
	 "dimensioned base and the base now exists."),
	("synthetic_shipping_fuel_mwh", "MWh/year", [0.0, 2.0e7], "fixed",
	 "Transport",
	 "Synthetic marine fuel loaded in the year: the green-fuel share times "
	 "bunker demand. 100,000 MWh at defaults."),
	("heat_pump_electricity_saving_mwh_per_year", "MWh/year", [0.0, 1.0e8],
	 "fixed", "Households",
	 "The electricity heat pumps displace: the adoption share times the "
	 "household count times household consumption times (1 - 1/COP). The "
	 "bracket is the fraction of resistive heat's electricity a heat pump "
	 "does not draw, so the product is a saving and not a load. 535,714 "
	 "MWh/year at defaults. It is the only reading of the COP node that "
	 "turns it into arithmetic."),
	("electrified_industrial_heat_twh", "TWh/year", [0.0, 200.0], "fixed",
	 "Industry",
	 "Electrified industrial process heat: the electrification share times "
	 "total process heat demand. 2.0 TWh at defaults, against 20 TWh of "
	 "thermal demand."),
	("currency_hedge_cost_usd_per_year", "USD/year", [0.0, 1.0e12],
	 "policy", "Finance",
	 "The annual charge for hedging currency exposure: the hedge rate "
	 "times the foreign-currency share of the debt stock times the debt "
	 "tranche. 1.512e8 USD/year at defaults. The 1000 is kW per MW, the "
	 "graph's own convention, and the shape follows the two risk charges "
	 "the finance batches already ship."),
	("lpg_subsidy_spend_usd_per_year", "USD/year", [0.0, 5.0e11], "policy",
	 "Finance",
	 "The annual LPG subsidy bill: the per-kilogram subsidy times the "
	 "share of households cooking with LPG times the household count times "
	 "the per-household burn. 1.5e8 USD/year at defaults -- 0.5 USD/kg over "
	 "2 M LPG-using households burning 150 kg each. A rate-based levy with "
	 "the sign flipped, which is the same identity the withholding-tax "
	 "products use."),
)

#: (equation id, name, lhs, rhs, prose, system, reference)
BATCH29_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str | None], ...
] = (
	# --- demand-side sector loads ---------------------------------------
	("desalination_demand_definition", "The desalination load",
	 "desalination_demand", "desalination_capacity * desalination_energy / 1000",
	 "The electricity a desalination programme draws: the annual water "
	 "volume times the specific energy of the process. The intensity node "
	 "carries the process choice and this node carries the scale. The "
	 "1000 is MWh per GWh-equivalent division -- kWh/m3 times m3/year is "
	 "kWh/year, and the node is declared in MWh/year. At 50 Mm3/year and "
	 "4 kWh/m3 it is 200,000 MWh/year.",
	 "water_energy", "Bottom-up load synthesis (catalog method cell)"),
	("agricultural_irrigation_load_definition", "The irrigation load",
	 "agricultural_irrigation_load",
	 "irrigation_pumping_demand * 1000000 / 8760",
	 "The average power irrigation pumping draws: the annual pumping "
	 "energy in TWh converted to MWh and divided by the year's 8,760 "
	 "hours. It is an average and not a peak -- a load that runs in "
	 "daylight and in season has a peak well above this number, and the "
	 "graph carries one annual energy figure for it, so the average is "
	 "the honest reading. At the shipped 0.5 TWh/year it is 57.1 MW.",
	 "demand_supply", None),
	("temporary_camp_load_definition", "The resettlement camp load",
	 "temporary_camp_load",
	 "exposed_population * resettlement_population_share * "
	 "energy_poor_consumption_mwh_per_year / persons_per_household / 8760",
	 "The power a resettlement camp draws: the displaced population, "
	 "divided by household size to get households, times the consumption "
	 "an energy-poor household actually draws, spread over the year. The "
	 "per-household figure is the graph's energy-poor draw and not the "
	 "mean, because a camp household is by construction at the bottom of "
	 "the distribution; the mean would overstate the load fourfold. At "
	 "defaults: 5 M exposed x 2% = 100,000 people, 22,222 households, "
	 "0.89 MW.",
	 "demand_supply", None),
	("hydrogen_export_port_definition", "The export terminal's throughput",
	 "hydrogen_export_port", "hydrogen_export_volume / 8760",
	 "The port's average throughput in megawatts: the annual hydrogen "
	 "energy the terminal loads, spread over the year. A port is not a "
	 "nameplate -- the berth count and the storage inventory are the "
	 "other two readings, and the graph carries neither -- so the average "
	 "flow is what the export volume determines. At 20,000 MWh/year it is "
	 "2.28 MW.",
	 "demand_supply", None),
	# --- the share products ---------------------------------------------
	("household_batteries_definition", "Household batteries",
	 "household_batteries",
	 "battery_storage_adoption * households_total",
	 "Household battery systems installed: the adoption share times the "
	 "household count the graph derives from population and household "
	 "size. 0.05 gives 500,000 household batteries at defaults.",
	 "demand_supply", None),
	("electrified_route_km_definition", "Electrified route-kilometres",
	 "electrified_route_km", "railway_electrification * railway_route_km",
	 "Electrified route-kilometres: the rail electrification share times "
	 "the network's route length. The share was a dial with no base; this "
	 "is the product it was waiting for. 400 km at defaults.",
	 "demand_supply", None),
	("freight_electric_tonne_km_definition",
	 "Electric freight tonne-kilometres", "freight_electric_tonne_km",
	 "freight_electrification * transport_logistics",
	 "Freight tonne-kilometres moved electrically: the freight "
	 "electrification share times total tonne-km. 2.25 bn of 45 bn at "
	 "defaults.",
	 "demand_supply", None),
	("synthetic_aviation_fuel_mwh_definition", "Synthetic aviation fuel",
	 "synthetic_aviation_fuel_mwh",
	 "synthetic_fuel_share_aviation * aviation_fuel_demand",
	 "Synthetic aviation fuel loaded in the year: the SAF share times "
	 "aviation fuel demand. 150,000 MWh at defaults, 5% of a 3 TWh "
	 "market.",
	 "demand_supply", None),
	("synthetic_shipping_fuel_mwh_definition", "Synthetic marine fuel",
	 "synthetic_shipping_fuel_mwh",
	 "synthetic_fuel_share_shipping * shipping_fuel_demand",
	 "Synthetic marine fuel loaded in the year: the green-fuel share "
	 "times bunker demand. 100,000 MWh at defaults, 5% of a 2 TWh "
	 "market.",
	 "demand_supply", None),
	("heat_pump_electricity_saving_definition",
	 "Heat pump electricity saving",
	 "heat_pump_electricity_saving_mwh_per_year",
	 "heat_pump_adoption * households_total * "
	 "household_consumption_mwh_per_year * (1 - 1 / heat_pump_cop)",
	 "The electricity heat pumps displace. The bracket (1 - 1/COP) is the "
	 "fraction of resistive heat's electricity a heat pump does not draw: "
	 "at a COP of 3.5 the pump delivers the same heat for 28.6% of the "
	 "resistive input, so 71.4% is saved. The product is a saving and not "
	 "a load, which is why it is subtracted rather than added in any "
	 "balance that reads it. 535,714 MWh/year at defaults.",
	 "demand_supply", None),
	("electrified_industrial_heat_twh_definition",
	 "Electrified industrial heat", "electrified_industrial_heat_twh",
	 "industrial_heat_electrification * industrial_heat_demand",
	 "Electrified industrial process heat: the electrification share "
	 "times total process heat demand. 2.0 TWh of 20 TWh at defaults. "
	 "The heat demand is on a thermal basis and the product is the "
	 "electricity that replaces it, so no efficiency enters here -- a "
	 "heat pump's COP would, and the graph carries no industrial COP.",
	 "demand_supply", None),
	# --- the macro-fiscal register --------------------------------------
	("archaeological_sites_definition", "Archaeological sites",
	 "archaeological_sites",
	 "archaeological_sites_density * land_area_hectares / 10000",
	 "Expected count of recorded archaeological sites inside the project "
	 "footprint: the measured site density per 100 km2 times the land "
	 "take converted to the density's own denominator. The 10000 is "
	 "exact, not a fudge: one hectare is 0.01 km2, so hectares divided by "
	 "10,000 is hectares expressed in units of 100 km2. A fractional "
	 "value is the expectation, not a count of objects.",
	 "financial", None),
	("sacred_sites_definition", "Sacred sites", "sacred_sites",
	 "sacred_sites_density * land_area_hectares / 10000",
	 "Expected count of sacred and culturally significant sites inside "
	 "the project footprint. Same construction as archaeological_sites on "
	 "the sacred-site density layer, so a siting decision can compare the "
	 "two exposures directly.",
	 "financial", None),
	("protected_areas_definition", "Protected areas", "protected_areas",
	 "protected_area_fraction * land_area_hectares",
	 "Hectares of the project footprint falling inside a protected area: "
	 "the overlap share times the land take. An area rather than a count, "
	 "because what a designation constrains is the ground you may "
	 "disturb.",
	 "financial", None),
	("parametric_insurance_definition", "Parametric insurance payout",
	 "parametric_insurance",
	 "parametric_insurance_coverage * aal_usd_million",
	 "The loss a parametric instrument pays out in an average year: the "
	 "share of the loss its trigger covers times the expected annual "
	 "loss. Priced against aal_usd_million, the base the finance batches "
	 "already ship, so the payout and the premium that covers it sit on "
	 "one base.",
	 "financial", None),
	("remittance_flows_definition", "Remittance flows", "remittance_flows",
	 "remittance_income_share * household_income_usd_per_year * "
	 "households_total",
	 "Remittances received per year: the share of household income "
	 "arriving as transfers, times household income, times the number of "
	 "households. Measured against the household income base rather than "
	 "GDP, because remittances are a household transfer and the household "
	 "base is the one the graph carries.",
	 "financial", None),
	("strategic_reserves_definition", "Strategic reserves",
	 "strategic_reserves", "strategic_reserve_days * demand_twh / 365",
	 "The strategic stock held, as a volume of energy: the days of cover "
	 "the policy declares, times annual demand, over the days in a year. "
	 "Days of total demand, not of net imports: the IEA convention is "
	 "import cover, and an import-based stock would need an abs over a "
	 "signed flow the DSL cannot differentiate.",
	 "energy_balance", None),
	("weather_derivatives_definition", "Weather derivative notional",
	 "weather_derivatives",
	 "weather_derivative_notional_share * total_revenue_usd_per_year",
	 "The notional of the weather hedge carried, in currency per year: "
	 "the share of revenue the firm hedges, times revenue. A notional "
	 "against revenue rather than a weather-sensitive revenue base, "
	 "because the revenue the derivative protects is the revenue the firm "
	 "actually books.",
	 "financial", None),
	("currency_hedge_cost_usd_per_year_definition",
	 "The currency hedge charge", "currency_hedge_cost_usd_per_year",
	 "currency_hedge_cost * foreign_currency_debt_share * debt_fraction * "
	 "capex_usd_per_kw * total_capacity_mw * 1000",
	 "The annual charge for hedging currency exposure: the hedge rate "
	 "times the foreign-currency share of the debt stock times the debt "
	 "tranche. The 1000 is kW per MW, the graph's own convention for "
	 "turning a per-kilowatt capital cost into the fleet's total, and the "
	 "shape follows sovereign_risk_charge_usd_per_year and "
	 "technology_risk_charge_usd_per_year deliberately. 1.512e8 USD/year "
	 "at defaults.",
	 "financial", None),
	("lpg_subsidy_spend_usd_per_year_definition",
	 "The LPG subsidy bill", "lpg_subsidy_spend_usd_per_year",
	 "lpg_subsidies * cooking_lpg_penetration * households_total * "
	 "lpg_use_kg_per_household_year",
	 "The annual LPG subsidy bill: the per-kilogram subsidy times the "
	 "share of households cooking with LPG times the household count "
	 "times the per-household burn. A rate-based levy with the sign "
	 "flipped, which is the same identity the withholding-tax products "
	 "use. 1.5e8 USD/year at defaults.",
	 "financial",
	 "Rate-based levy and allowance definitions (standard fiscal accounting)"),
)


def build_batch29(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""Batch 29: the demand-side and macro-fiscal coupling.

	Thirty-five nodes from two research packs, and the packs' own finding is
	the batch's shape: the demand family closes on bases the graph already
	carries, and the macro block does not close at all without a GDP level
	that nothing in the graph can produce.

	*The demand family* is the sector loads the catalog sketched as
	``unit: None default: 500000.0`` and the electrification shares that were
	inert because the energy they were a share of did not exist. Four become
	equation targets -- the desalination load, the irrigation load, the
	resettlement camp load and the export terminal's throughput. Eight become
	operands of the seven share products, and one of those products is the
	only arithmetic reading of the heat-pump COP: ``(1 - 1/COP)`` is the
	fraction of resistive heat's electricity a heat pump does not draw, so the
	node becomes a saving rather than a load.

	Eighteen demand nodes defer, and each defer is a stated missing base
	rather than a modelling choice. The pack refuses to invent an intensity:
	a kWh per hectare, per tonne of crop, per cubic metre pumped or per
	tonne-km hauled would close one node and leave a coefficient nobody can
	check. Those are the eighteen.

	*The macro-fiscal register* closes nine of its twenty. Seven are
	derived: the heritage site counts, the protected-area overlap, the
	parametric payout, remittance flows, the strategic stock, the weather
	derivative notional and the currency hedge charge. Two more become
	operands -- the parametric coverage share and the LPG subsidy rate.
	Ten defer, and seven of the ten defer on the same two absent levels: a
	GDP figure and an import bill in currency. That is the pack's headline
	finding and it is a fact about the graph, not a choice.

	One macro node is deferred for a reason worth recording. The pack found
	that ``remittance_dependency`` is computable today as remittances over
	household income, and refused it: the name denotes a share of GDP in the
	literature, and shipping the household ratio under this name would put
	a true number behind a false label. A computable answer that answers a
	different question is worse than a defer, because it reads as closed.

	The signed-range lesson from batch 28 applies once here and is why
	``strategic_reserves`` is built on demand rather than on net imports:
	net imports are signed and zero at defaults, so an import-based stock
	would need an ``abs`` the DSL cannot differentiate. The IEA convention
	is import cover; this batch states the demand basis in the prose rather
	than shipping a formula the sensitivity pass would refuse.

	No rule ships. Every deferral in this batch is a missing operand, and a
	cross-validation rule over an absent quantity is a rule that cannot fire.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH29_RETYPES:
		# The emit path reads the already-baked document, so a re-emit after a
		# bake finds the node present. Reading the shipped body and overriding
		# the fields this batch owns keeps the two runs identical.
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": "free", "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": "The demand and macro coupling (batch 29)",
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, default, category, prose in BATCH29_BASES:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "default": default, "role": "free",
			"determinism": "policy", "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The demand and macro coupling (batch 29)",
			"users": ["Planners", "Regulators"],
		})
		nodes[name] = full

	for name, unit, rng, determinism, category, prose in BATCH29_DERIVED:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The demand and macro coupling (batch 29)",
			"users": ["Planners", "Regulators"],
		})
		full.pop("default", None)
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, cite in BATCH29_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		assert lhs in nodes, f"{eq_id}: {lhs!r} has no node body in this batch"
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})
	return nodes, equations, edges, rules




#: (name, unit, range, default, determinism, prose) -- the placeholder nodes
#: this batch retypes to free operands with a real unit and a real default.
BATCH30_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("number_of_generators", "1", [0.0, 1000.0], 220.0, "physical",
	 "Generating units in the fleet, not sites. The default is 220, the "
	 "count the graph already carries for `scada_telemetry_sites`, because "
	 "no unit-level register exists and 220 units over an 18,900 MW fleet "
	 "averages about 86 MW a unit -- the right order for a mixed "
	 "thermal-and-hydro fleet. The placeholder 500,000.0 is not a count of "
	 "anything a country has."),
	("circuit_breakers", "1", [0.0, 5000.0], 500.0, "physical",
	 "Feeder-head circuit breakers on the distribution network. The default "
	 "is one per primary feeder, and `distribution_feeders_total` ships at "
	 "500. Sectionalisers and low-voltage breakers are outside the count: "
	 "the node states the primary-feeder bay, which is what a density "
	 "against route-km can be read from."),
	("biomass_sustainability_limit", "MW", [0.0, 30000.0], 200.0, "policy",
	 "The sustainable biomass resource expressed as an installable capacity "
	 "ceiling, in the same unit as the capacity it bounds. The default 200 "
	 "MW sits above the shipped 100 MW build, so the ceiling holds with "
	 "room; setting it below 100 makes the constraint bind, which is what a "
	 "ceiling is for. Expressed in MW rather than tonnes of fuel because "
	 "the graph carries no heat rate and no fuel-mass factor for biomass, "
	 "so a mass ceiling cannot be formed from what exists."),
	("water_availability", "1", [0.0, 2.0], 1.0, "physical",
	 "A multiplier on the water the project may withdraw: 0 is a closed "
	 "source, 1 is the shipped flow, 2 is a wet year. The flow itself ships "
	 "as `water_availability_m3` (200e6 m3/year) and the inequality that "
	 "compares it to demand ships with it; this node is the scenario lever "
	 "on that comparison and not a second spelling of the flow."),
	("biogas_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of anaerobic digestion, in the band of the shipped "
	 "`biomass_capacity`. The default is 0.0: the fleet balance ships a "
	 "build that does not include it, and a non-zero default would move a "
	 "balance the graph has already checked. The optimiser chooses the "
	 "build; this node is where the choice is recorded."),
	("landfill_gas_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of landfill-gas capture and generation. Default "
	 "0.0 for the same reason as `biogas_capacity`: the shipped balance "
	 "excludes it and a default would move a checked constraint."),
	("gasification_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of biomass gasification. Default 0.0, as the two "
	 "above."),
	("pyrolysis_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of pyrolysis. Default 0.0, as the three above."),
	("waste_to_energy_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of municipal-waste combustion with energy "
	 "recovery. Default 0.0. The IRENA jobs table counts 26,000 "
	 "waste-to-energy jobs but prints no capacity to divide them by, so "
	 "this node is an input and not a derived quantity."),
	("salinity_gradient_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Electrical capacity of salinity-gradient conversion. Default 0.0; "
	 "the technology is pre-commercial, as `capex_salinity_gradient`'s own "
	 "description says, so a non-zero default would assert a build the "
	 "graph has no basis for."),
	("employment_factor_biomass", "jobs/MW", [0.0, 20.0], 5.1, "fixed",
	 "Jobs per installed MW of biomass capacity. 5.1 is the ratio the "
	 "archived IRENA review implies: 765,000 solid-biomass jobs over 149 GW "
	 "of bioenergy capacity is 5.13 jobs/MW, with the caveat that the "
	 "numerator is biomass jobs and the denominator is all bioenergy "
	 "capacity, so the ratio is an upper estimate."),
	("employment_factor_coal", "jobs/MW", [0.0, 20.0], 4.3, "fixed",
	 "Jobs per installed MW of coal capacity. 4.3 is the graph's own "
	 "construction-plus-O&M intensity (`construction_jobs_per_mw` + "
	 "`om_jobs_per_mw`), because the archived IRENA review covers renewable "
	 "technologies only and prints no coal figure. The default is an "
	 "assumption and is stated as one."),
	("employment_factor_gas", "jobs/MW", [0.0, 20.0], 4.3, "fixed",
	 "Jobs per installed MW of gas capacity. 4.3, the graph's own intensity; "
	 "the archived review covers no gas. An assumption, as for coal."),
	("employment_factor_geothermal", "jobs/MW", [0.0, 20.0], 4.3, "fixed",
	 "Jobs per installed MW of geothermal capacity. 4.3, the graph's own "
	 "intensity: the IRENA review gives 160,000 geothermal jobs but prints "
	 "no geothermal capacity in the archived text, so the ratio cannot be "
	 "read off it."),
	("employment_factor_hydro", "jobs/MW", [0.0, 20.0], 1.8, "fixed",
	 "Jobs per installed MW of hydro capacity. 1.8: 2,324,000 jobs over "
	 "1,265 GW is 1.84. The lowest of the technologies in the table, which "
	 "is the point -- a hydro-heavy fleet is not a jobs fleet per MW."),
	("employment_factor_solar", "jobs/MW", [0.0, 20.0], 5.0, "fixed",
	 "Jobs per installed MW of solar PV capacity. 5.0: 7,107,000 jobs over "
	 "1,411 GW is 5.04. The highest in the table, and it carries the "
	 "manufacturing share, so it overstates an O&M-only intensity."),
	("employment_factor_wind", "jobs/MW", [0.0, 20.0], 1.4, "fixed",
	 "Jobs per installed MW of wind capacity. 1.4: 1,457,000 jobs over "
	 "1,017 GW is 1.43."),
	("employment_factor_transmission", "jobs/km", [0.0, 20.0], 3.0, "fixed",
	 "Jobs per route-kilometre of high-voltage line. 3.0 is a planning "
	 "figure and not extracted from the archive: the IRENA review covers "
	 "generation, not networks, and no archived work states a line-km "
	 "intensity. Stated as an assumption, which is why the identity it "
	 "feeds cites IRENA only for the method."),
	("spare_parts_inventory", "USD million", [0.0, 1000.0], 240.0, "fixed",
	 "The value of spares held against failure. 240 is two percent of gross "
	 "fleet capital (1,200 USD/kW x 10,000 MW = 12,000 USD million), a "
	 "stated assumption rather than a measured figure. The 1,000 ceiling is "
	 "an eight percent spares holding, which is the top of what a utility "
	 "carries; the placeholder 500,000.0 would be four percent of the whole "
	 "fleet's capital in spare parts."),
	("cross_border_permitting_time", "years", [0.0, 10.0], 2.0, "policy",
	 "Years to secure the cross-border permit for a transmission line. The "
	 "default 2.0 is two permitting cycles; the graph's own "
	 "`financing_close_deadline` (18 months) sits inside one. A permit that "
	 "outlasts a ten-year horizon is a refusal rather than a delay, which "
	 "is why the range stops there."),
)


#: (name, unit, range, determinism, category, prose) -- the five products
#: that close a read, and the five equation targets.
BATCH30_DERIVED: tuple[tuple[str, str, list[float], str, str, str], ...] = (
	("baseline_emissions", "MtCO2/year", [0.0, 10000.0], "physical",
	 "Emissions",
	 "Emissions the fleet would have produced without the abatement the "
	 "project delivers. The identity is the FRM's own "
	 "`reductions = baseline - project - leakage`, solved for the baseline "
	 "with the leakage term omitted: the graph carries "
	 "`additional_abatement_mtco2` (45.0 MtCO2/year at defaults) and "
	 "`emissions_mtco2_per_year` (25.777), giving 70.777. The omitted "
	 "leakage term is stated rather than invented -- no node in the graph "
	 "carries a leakage mass."),
	("regulation_reserve", "MW", [0.0, 3000.0], "policy",
	 "Reliability",
	 "The regulation band the system must hold, up plus down. Both halves "
	 "already ship as `regulation_up_requirement` and "
	 "`regulation_down_requirement`, each a share of peak demand and 85.0 MW "
	 "at defaults, so the total is 170.0 MW. The node is the sum of its two "
	 "shipped parts and not a third derivation of the same band: a "
	 "`regulation_reserve_share` over the same peak would leave three "
	 "equations describing one quantity, inconsistent at every default."),
	("black_start_capability", "1", [0.0, 1000.0], "policy",
	 "Reliability",
	 "Units the operator must hold capable of black start. The share ships "
	 "(`black_start_requirement`, 0.02) and the unit count is retyped in "
	 "this batch; the product is 4.4 units at defaults. Distinct from the "
	 "shipped `black_start_capable_mw` (180 MW), which states the same "
	 "obligation in capacity -- the two are the two registers of one "
	 "requirement, and neither is the other's alias."),
	("lifeline_threshold", "MWh/year", [0.0, 10.0], "physical",
	 "Affordability",
	 "The consumption level below which a household qualifies for the "
	 "lifeline tariff. The graph already carries that level: "
	 "`energy_poverty_line_mwh_per_household` is the MTF Tier 2/3 boundary "
	 "at 1.0 MWh/year per household, with "
	 "`energy_poor_consumption_mwh_per_household` (0.35) as the draw of a "
	 "household below it. The threshold is the line, so this node is an "
	 "alias onto it and not a second estimate of the same boundary."),
	("transmission_lead_time", "years", [0.0, 20.0], "physical",
	 "Grid",
	 "Years from decision to energisation for a transmission line: the "
	 "build period plus the cross-border permit. `construction_period` "
	 "ships in months (30), so the division by 12 is a unit conversion and "
	 "not a scale factor; the permit is retyped to years in this batch at "
	 "2.0. Total 4.5 years at defaults."),
	("fleet_employment_intensity_jobs_per_mw", "jobs/MW", [0.0, 50.0],
	 "physical", "Employment",
	 "Jobs per installed megawatt of the generating fleet, weighted by the "
	 "installed capacity of each technology. A weighted-average intensity "
	 "and deliberately not a jobs total: `direct_jobs` already ships as "
	 "`total_capacity_mw * (construction_jobs_per_mw + om_jobs_per_mw)` = "
	 "43,000, and the per-technology factors applied to capacity give "
	 "88,717. Two nodes measuring the same employment at a factor of two "
	 "would be worse than an uncoupled node, so the product here is an "
	 "intensity no total can be confused with. 4.169 jobs/MW at defaults. "
	 "The oil fleet is outside both the numerator and the denominator: the "
	 "archive prints no oil employment factor, and omitting it from both "
	 "keeps the ratio well defined while leaving a stated 1.6% gap."),
	("transmission_jobs", "jobs", [0.0, 1000000.0], "physical",
	 "Employment",
	 "Construction and O&M jobs on the transmission network: the per-route-"
	 "km intensity times the line length, 36,000 at defaults. A separate "
	 "stock and not an addend to `direct_jobs`: the transmission build is "
	 "already inside `construction_jobs_per_mw * total_capacity_mw`, and "
	 "the graph carries no identity that sums the two."),
	("spare_parts_carrying_cost_usd_per_year", "USD million/year",
	 [0.0, 200.0], "physical", "Financial",
	 "The annual cost of holding spares: the inventory's value times the "
	 "discount rate, 25.1 USD million/year at defaults (240 x 0.1046). The "
	 "rate is the graph's own weighted average cost of capital, because "
	 "capital tied up in a warehouse is capital not deployed -- the same "
	 "opportunity cost the WACC prices everywhere else."),
	("hydrogen_storage_capex_usd", "USD", [0.0, 1000000000000.0],
	 "physical", "Financial",
	 "Capital cost of the hydrogen storage the optimiser builds: the "
	 "installed cost per kWh times the energy capacity, with 1000 converting "
	 "MWh to kWh. Zero at defaults only because the shipped "
	 "`hydrogen_storage_capacity` is 0 MWh -- the optimiser builds no "
	 "hydrogen storage at defaults, not that the node is unread. The 1000 "
	 "follows the graph's own MW-to-kW convention, which every capital "
	 "charge in the finance family uses."),
	("circuit_breaker_density_per_km", "1/km", [0.0, 10.0], "physical",
	 "Grid",
	 "Feeder-head breakers per route-kilometre of distribution network: "
	 "500 over 45,000 km is 0.0111/km. A density rather than a count, "
	 "because the count alone cannot say whether a network is densely "
	 "switched; the denominator is the graph's own `distribution_network_km`."),
)


#: (eq_id, name, lhs, rhs, prose, system, reference)
BATCH30_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str | None], ...
] = (
	("baseline_emissions_definition", "The counterfactual baseline",
	 "baseline_emissions", "emissions_mtco2_per_year + additional_abatement_mtco2",
	 "The emissions the fleet would have produced without the abatement "
	 "this project delivers: what it does emit plus what the abatement "
	 "avoids. This is the FRM's `reductions = baseline - project - "
	 "leakage` rearranged, with the leakage term omitted because no node "
	 "in the graph carries a leakage mass. The omission is stated rather "
	 "than filled with a coefficient: a leakage share would be an invented "
	 "number and the baseline would inherit it. 70.777 MtCO2/year at "
	 "defaults.",
	 "emissions",
	 "Verra/Gold Standard avoided-emissions accounting; the graph's own "
	 "abatement identity rearranged"),
	("regulation_reserve_definition", "The regulation band",
	 "regulation_reserve",
	 "regulation_up_requirement + regulation_down_requirement",
	 "The total regulation reserve the system must hold: the up band plus "
	 "the down band. Both components ship as their own identities "
	 "(`regulation_up_share * peak_demand_mw` and the down counterpart), so "
	 "this node is their sum and not a third share over the same peak. A "
	 "third share would put three equations on one quantity, and at the "
	 "shipped 0.01 each the sum is 170 MW.",
	 "reserve_margin", "Stoft 2002, Power System Economics, ch. 5"),
	("black_start_capability_definition", "Units capable of black start",
	 "black_start_capability", "black_start_requirement * number_of_generators",
	 "Units the operator must hold capable of black start: the requirement "
	 "share times the fleet's unit count, 4.4 units at defaults. The "
	 "shipped `black_start_capable_mw` states the same obligation in "
	 "capacity; this node states it in units, which is the register a "
	 "system operator's black-start plan is actually written in.",
	 "reliability", None),
	("lifeline_threshold_definition", "The lifeline consumption threshold",
	 "lifeline_threshold", "energy_poverty_line_mwh_per_household",
	 "The household consumption level below which the lifeline tariff "
	 "applies. The graph carries exactly one such line -- the MTF Tier 2/3 "
	 "boundary at 1.0 MWh/year per household -- and this node is an alias "
	 "onto it rather than a second estimate. Two thresholds would let a "
	 "scenario move the tariff's eligibility without moving the poverty "
	 "measure it is supposed to track.",
	 "affordability", "Multi-Tier Framework (MTF) energy access measurement"),
	("transmission_lead_time_definition", "Transmission lead time",
	 "transmission_lead_time",
	 "construction_period / 12 + cross_border_permitting_time",
	 "Years from decision to energisation: the build period plus the "
	 "cross-border permit. `construction_period` ships in months, so the "
	 "12 is a unit conversion and not a scale factor -- 30 months is 2.5 "
	 "years, and the permit adds 2.0, giving 4.5 years at defaults. The "
	 "build period is the fleet average the graph carries; a "
	 "technology-specific period would need a base the graph lacks.",
	 "energy_balance",
	 "ENTSO-E adequacy studies; the graph's own construction period"),
	("fleet_employment_intensity_definition",
	 "The fleet's employment intensity",
	 "fleet_employment_intensity_jobs_per_mw",
	 "(employment_factor_coal * coal_capacity + employment_factor_gas * "
	 "gas_capacity + employment_factor_hydro * hydro_capacity + "
	 "employment_factor_geothermal * geothermal_capacity + "
	 "employment_factor_biomass * biomass_capacity + "
	 "employment_factor_solar * solar_pv_capacity + "
	 "employment_factor_wind * (wind_onshore_capacity + "
	 "wind_offshore_capacity)) / (coal_capacity + gas_capacity + "
	 "hydro_capacity + geothermal_capacity + biomass_capacity + "
	 "solar_pv_capacity + wind_onshore_capacity + wind_offshore_capacity)",
	 "Jobs per installed megawatt, capacity-weighted across the "
	 "technologies the archive prices. An intensity and not a total: "
	 "`direct_jobs` already ships at 43,000 and the per-technology factors "
	 "applied to capacity give 88,717, so a jobs total built from these "
	 "factors would double-count by a factor of two. The oil fleet is "
	 "absent from both the numerator and the denominator -- the archive "
	 "prints no oil factor -- which leaves a stated 1.6% gap rather than a "
	 "silently averaged one. 4.169 jobs/MW at defaults.",
	 "employment", "IRENA employment factors"),
	("transmission_jobs_definition", "Transmission jobs",
	 "transmission_jobs",
	 "employment_factor_transmission * transmission_line_length_km",
	 "Construction and O&M jobs on the transmission network: the per-km "
	 "intensity times the route length, 36,000 at defaults. A separate "
	 "stock from `direct_jobs`, which is the generation fleet's own "
	 "workforce; the graph carries no identity that adds the two, and "
	 "adding them would count the transmission build twice.",
	 "employment", "IRENA employment factors"),
	("spare_parts_carrying_cost_definition", "The cost of holding spares",
	 "spare_parts_carrying_cost_usd_per_year",
	 "spare_parts_inventory * discount_rate",
	 "The annual carrying cost of the spares inventory: its value times the "
	 "discount rate, 25.1 USD million/year at defaults. The rate is the "
	 "graph's own WACC because capital held in a warehouse is capital not "
	 "deployed, which is the same opportunity cost every other capital "
	 "charge in the finance family prices.",
	 "financial", "Standard inventory carrying-cost accounting"),
	("hydrogen_storage_capex_definition", "Hydrogen storage capital cost",
	 "hydrogen_storage_capex_usd",
	 "hydrogen_storage_cost * hydrogen_storage_capacity * 1000",
	 "The capital cost of the hydrogen storage built: installed cost per kWh "
	 "times energy capacity, with 1000 converting MWh to kWh. The product "
	 "is zero at defaults because the shipped capacity is zero -- the "
	 "optimiser builds no hydrogen storage there -- and not because the "
	 "node is unread. The 1000 follows the graph's own MW-to-kW "
	 "convention, which the finance family's capital charges all use.",
	 "financial", "Lazard LCOS; the graph's own MW-to-kW convention"),
	("circuit_breaker_density_definition", "Breaker density",
	 "circuit_breaker_density_per_km",
	 "circuit_breakers / distribution_network_km",
	 "Feeder-head circuit breakers per route-kilometre of distribution "
	 "network: 0.0111/km at defaults. A density rather than a count, "
	 "because 500 breakers says nothing without the network they sit on; "
	 "the denominator is the graph's own distribution route length, so a "
	 "scenario that extends the network without adding bays lowers the "
	 "density and the reading says so.",
	 "energy_balance", None),
)


#: (eq_id, binder, bounded) -- which edge each bound carries. A bound names
#: both sides, but an edge is a coupling claim and a self-loop claims none, so
#: the pair is stated rather than derived.
_BOUND_EDGE: dict[str, tuple[str, str]] = {
	"biomass_sustainability_bound": ("biomass_sustainability_limit", "biomass_capacity"),
	"water_availability_bound": ("total_water_demand_m3", "water_availability_m3"),
}


#: (eq_id, lhs, relation, rhs, prose, system, reference) -- the ceilings and
#: floors this batch ships as inequalities rather than as equations.
BATCH30_BOUNDS: tuple[tuple[str, str, str, str, str, str, str | None], ...] = (
	("biomass_sustainability_bound", "biomass_capacity", "leq",
	 "biomass_sustainability_limit",
	 "The biomass build may not exceed the sustainable resource the policy "
	 "declares. Stated as a bound in megawatts rather than as a fuel-mass "
	 "ceiling: the mass form needs a heat rate and a biomass fuel factor, "
	 "neither of which the graph carries, while a capacity ceiling needs "
	 "neither and is what the resource assessment is usually written in. "
	 "The shipped 100 MW build sits under the 200 MW default, so the "
	 "constraint holds with room; setting the limit below 100 makes it "
	 "bind, which is the point of a ceiling.",
	 "energy_balance",
	 "IEA/NEA Projected Costs of Generating Electricity; sustainable-biomass "
	 "supply as a build limit"),
	("water_availability_bound", "water_availability * water_availability_m3",
	 "geq", "total_water_demand_m3",
	 "The water the project may withdraw, after the availability "
	 "multiplier, must cover the thermal fleet's cooling draw and the "
	 "hydrogen programme's feed. The multiplier is the scenario lever on a "
	 "flow the graph already ships: at its default of 1.0 the constraint "
	 "reads 200e6 >= 93.2e6 m3/year, and a dry year set below 0.47 makes "
	 "it bind. The rewrite replaces a constraint that compared the flow to "
	 "its own two components with one that compares the *available* flow "
	 "to demand, which is the question a water-stressed siting decision "
	 "actually asks.",
	 "water_energy", None),
)


def build_batch30(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""Batch 30: the supply, emissions and grid coupling.

	Forty-two nodes from one research pack, and the pack's own division is
	the batch's shape: the *capacities* and the *employment factors* have
	bases the graph already carries, and the *pollutants* have no base at
	all.

	Twenty nodes are retyped from the catalog's placeholder signature
	(``unit: None``, range ``(0, 1e6)``, default ``500000.0``) to real
	units with real defaults: the unit and breaker counts, the six
	conversion-plant capacities, the eight employment factors, the spares
	stock and the cross-border permit. Every one of those defaults is
	either read off an archived work or stated as an assumption in the
	node's own prose; the placeholder 500,000.0 is not a count, a stock or a
	permit duration, and no scenario could have meant it.

	Ten nodes become derived. Five are equation targets the pack identifies
	-- the counterfactual baseline, the regulation band, the black-start
	unit count, the lifeline threshold and the transmission lead time --
	and five are products that close a read (the fleet employment
	intensity, the transmission jobs, the spares carrying cost, the
	hydrogen storage capex and the breaker density).

	*The employment double count is the batch's hazard and its shape.* The
	prior classification pack proposed seven ``jobs_from_<tech>`` totals;
	applied to installed capacity they give 88,717 jobs against a shipped
	``direct_jobs`` of 43,000, because ``direct_jobs`` is already
	``total_capacity_mw * (construction_jobs_per_mw + om_jobs_per_mw)``.
	Two nodes measuring one employment at a factor of two is worse than an
	uncoupled node, so the identity shipped here is a capacity-weighted
	*intensity* in jobs/MW -- a quantity no total can be confused with.
	``transmission_jobs`` is the one genuine total, and it is a separate
	stock the graph does not add to ``direct_jobs``: the transmission build
	is already inside the per-MW factors.

	Two shipped equations are rewritten rather than supplemented. The fleet
	build balance gains the six conversion-plant capacities, so a scenario
	that builds digestion or gasification is counted against the fleet
	ceiling instead of silently exceeding it; at defaults all six are zero
	and the balance does not move. The water constraint is rewritten to
	compare the *available* flow -- after the availability multiplier -- to
	demand, which is the question a siting decision asks; the shipped form
	compared the unmodified flow to its own two components.

	Thirteen nodes defer, and seven of them are the pollutant family, which
	defers as one. The catalog's own edges say ``nox_emissions <-
	generation_coal, generation_gas``, and neither is a node; the graph's
	only activity base is ``generation_twh``, a fleet total that is
	majority hydro, wind and solar at defaults, and ``emission_factor_*``
	covers CO2 only. A pollutant factor times a low-carbon fleet total is
	dimensionally clean and wrong about which plant emits. The remaining
	six defer on a missing operand each -- a voltage base, a reservoir
	energy, a starts count, a reserve-account share, and the effluent
	volume the water-pollution load needs.

	Two ceilings ship as inequalities rather than equations, because the
	DSL has no derivative rule for ``abs``/``min``/``max`` and
	``gradients()`` differentiates every equation: a clamp would raise
	``DslError`` on the sensitivity pass. An inequality is what the DSL
	carries and what the claim actually is.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH30_RETYPES:
		# The emit path reads the already-baked document, so a re-emit after a
		# bake finds the node present. Reading the shipped body and overriding
		# the fields this batch owns keeps the two runs identical.
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": "free", "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": "The supply, emissions and grid coupling (batch 30)",
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, determinism, category, prose in BATCH30_DERIVED:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The supply, emissions and grid coupling (batch 30)",
			"users": ["Planners", "Regulators"],
		})
		full.pop("default", None)
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, cite in BATCH30_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		assert lhs in nodes, f"{eq_id}: {lhs!r} has no node body in this batch"
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite in BATCH30_BOUNDS:
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		equations[eq_id] = {
			"id": eq_id, "name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		# The edge runs from the binding quantity to the bounded one, which is
		# the shape every shipped bound uses (`cooling_water_demand_m3 ->
		# water_availability_m3`): a self-loop would say the node constrains
		# itself and name no coupling at all. `_BOUND_EDGE` carries the pair
		# because a bounded lhs need not be a bare symbol -- the water bound's
		# left side is a product, and the node a reader looks for is the flow.
		binder, bounded = _BOUND_EDGE[eq_id]
		# `binder` is a single symbol, not a collection. Iterating it walks
		# its characters, which is how an earlier form of this loop shipped
		# forty-nine one-letter edges and a self-loop per named symbol: a
		# fragment carrying those validates on its own and the merged graph
		# keeps them, so nothing in the chain refuses a graph whose bound
		# edges name no coupling.
		known = set(nodes) | set(graph.nodes)
		assert binder in known, f"{eq_id}: binder {binder!r} is not a node"
		assert bounded in known, f"{eq_id}: bounded {bounded!r} is not a node"
		assert binder != bounded, f"{eq_id}: a self-loop names no coupling"
		edges.append({
			"source": binder, "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded}; a plan can clear the physics and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	# --- the two shipped constraints, rewritten -------------------------
	# The bake merges equations by id, so writing the same id with a new body
	# replaces the shipped form rather than adding a second constraint on the
	# same quantity.
	build_balance = graph.equations.get("fleet_build_balance")
	assert build_balance is not None, "fleet_build_balance is not shipped"
	body = dict(build_balance.model_dump(exclude={"id"}, mode="json"))
	body["lhs"] = (
		"battery_capacity + biomass_capacity + coal_capacity + csp_capacity "
		"+ gas_capacity + geothermal_capacity + hydro_capacity "
		"+ nuclear_capacity + oil_capacity + phs_capacity "
		"+ wind_offshore_capacity + wind_onshore_capacity "
		"+ biogas_capacity + landfill_gas_capacity + gasification_capacity "
		"+ pyrolysis_capacity + waste_to_energy_capacity "
		"+ salinity_gradient_capacity"
	)
	body["parameters"] = sorted(
		set(parse_side(body["lhs"]).symbols) | set(parse_side(body["rhs"]).symbols)
	)
	body["description"] = (
		"The optimiser's per-technology builds must not exceed the fleet size "
		"the plan declares for them. This is a *constraint* coupling -- the "
		"equation the LP carries, not an identity the evaluator solves -- "
		"because the builds are decision variables with no single value until "
		"the solve settles them. Batch 30 added the six conversion-plant "
		"capacities, so a scenario that builds anaerobic digestion, landfill "
		"gas, gasification, pyrolysis, waste-to-energy or salinity-gradient "
		"capacity is counted against the same ceiling instead of silently "
		"exceeding it. All six are zero at defaults, so the balance sums to "
		"9,700 MW against a 15,000 MW right-hand side exactly as it did "
		"before the rewrite."
	)
	equations["fleet_build_balance"] = body
	for sym in (
		"biogas_capacity", "landfill_gas_capacity", "gasification_capacity",
		"pyrolysis_capacity", "waste_to_energy_capacity",
		"salinity_gradient_capacity",
	):
		edges.append({
			"source": sym, "target": "total_capacity_mw",
			"equation_id": "fleet_build_balance",
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				"The conversion-plant build is one term the fleet size governs; "
				"the build set may not exceed it plus storage headroom."
			),
			"reference": None, "priority": "P1",
		})

	water = graph.equations.get("water_availability_constraint")
	assert water is not None, "water_availability_constraint is not shipped"
	wbody = dict(water.model_dump(exclude={"id"}, mode="json"))
	wbody["lhs"] = "water_availability * water_availability_m3"
	wbody["rhs"] = "total_water_demand_m3"
	wbody["parameters"] = sorted(
		set(parse_side(wbody["lhs"]).symbols) | set(parse_side(wbody["rhs"]).symbols)
	)
	wbody["free_variables"] = ()
	wbody["description"] = (
		"The water the project may withdraw, after the availability "
		"multiplier, must cover the thermal fleet's cooling draw and the "
		"hydrogen programme's feed. The multiplier is the scenario lever on a "
		"flow the graph already ships: at its default of 1.0 the constraint "
		"reads 200e6 >= 93.2e6 m3/year, and a dry year set below 0.47 makes it "
		"bind. The rewrite replaces a constraint that compared the flow to its "
		"own two components -- which restated the demand identity rather than "
		"testing it against supply -- with one that compares the *available* "
		"flow to demand."
	)
	equations["water_availability_constraint"] = wbody
	edges.append({
		"source": "water_availability", "target": "water_availability_m3",
		"equation_id": "water_availability_constraint",
		"relationship": "constraint", "direction": "forward",
		"strength": "hard",
		"description": "The availability multiplier scales the flow the demand is tested against.",
		"reference": None, "priority": "P2",
	})
	return nodes, equations, edges, rules


BATCH31_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("auction_price_cap", "USD/tonne", [0.0, 2000.0], 200.0, "policy",
	 "The auction's price ceiling, in the carbon market's own unit. Retyped "
	 "from the catalog placeholder (no unit, range (0, 1e6), default 500000) "
	 "to the unit the auction clears in: a cap on an allowance price is a "
	 "price. The 2,000 USD/tonne ceiling is "
	 "`carbon_price_escalated_usd_per_tco2`'s own range, so a cap below the "
	 "escalated price is expressible and a cap at the top of the band is the "
	 "no-cap case. The default 200 sits above the 81.44 USD/tonne the price "
	 "reaches at defaults, which is what a cap must do on day one."),
	("coal_new_build", "MW", [0.0, 200000.0], 5000.0, "fixed",
	 "New coal build allowed by policy, in megawatts. Retyped from the "
	 "placeholder to `coal_capacity`'s own unit and its technical ceiling of "
	 "200,000 MW, so a policy figure and the build it governs are comparable. "
	 "The 5,000 MW default sits above the 3,000 MW reference fleet -- a "
	 "ceiling a plan can reach and a 6,000 MW scenario can breach, which a "
	 "ceiling equal to the build's own maximum could not."),
	("gas_new_build", "MW", [0.0, 200000.0], 3000.0, "fixed",
	 "New gas build allowed by policy, in megawatts. Same construction as "
	 "`coal_new_build`: retyped to the capacity unit and to that capacity's "
	 "own ceiling, at 3,000 MW against a 1,500 MW reference fleet."),
	("hydro_new_build", "MW", [0.0, 100000.0], 3000.0, "fixed",
	 "New hydro build allowed by policy, in megawatts. Retyped to "
	 "`hydro_capacity`'s ceiling of 100,000 MW, at 3,000 MW against a 1,500 MW "
	 "reference fleet."),
	("nuclear_new_build", "MW", [0.0, 20000.0], 5000.0, "fixed",
	 "New nuclear build allowed by policy, in megawatts. Retyped to "
	 "`nuclear_capacity`'s ceiling of 20,000 MW. The 5,000 MW default is one "
	 "large unit or two SMR modules, against a 0 MW reference fleet -- the "
	 "ceiling is the only thing that could admit a first plant, so it must be "
	 "positive while the build is zero."),
	("compressed_air_capacity", "MW", [0.0, 1000000.0], 0.0, "physical",
	 "Compressed-air energy storage nameplate, in megawatts. Retyped from the "
	 "placeholder to a capacity and defaulted to zero, because the technology "
	 "is unbuilt at the reference scenario and a 500,000 MW placeholder "
	 "default is not a plant."),
	("flywheel_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Flywheel storage nameplate, in megawatts, defaulted to zero for the same "
	 "reason: an unbuilt technology's capacity is zero, not a placeholder."),
	("gravity_storage_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Gravity storage nameplate, in megawatts, defaulted to zero."),
	("fusion_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Fusion nameplate, in megawatts, defaulted to zero. The node exists so a "
	 "scenario can declare a fusion programme; the reference scenario has "
	 "none."),
	("hydrogen_fuel_cell_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Hydrogen fuel-cell nameplate, in megawatts, defaulted to zero. A fuel "
	 "cell is a generator and not a store, which is why the bound this batch "
	 "does not ship would sit against the fleet and not the storage envelope."),
	("marine_otec_capacity", "MW", [0.0, 1000000.0], 0.0, "physical",
	 "Ocean thermal energy conversion nameplate, in megawatts, defaulted to "
	 "zero."),
	("marine_tidal_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Tidal-stream nameplate, in megawatts, defaulted to zero."),
	("marine_wave_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Wave nameplate, in megawatts, defaulted to zero."),
	("small_modular_reactor_capacity", "MW", [0.0, 20000.0], 0.0, "fixed",
	 "Small modular reactor nameplate, in megawatts, defaulted to zero. "
	 "Retyped to the nuclear capacity ceiling rather than the generic "
	 "placeholder, because an SMR is a nuclear plant and shares its upper "
	 "bound."),
	("tidal_range_capacity", "MW", [0.0, 1000000.0], 0.0, "fixed",
	 "Tidal-range barrage nameplate, in megawatts, defaulted to zero. Kept "
	 "separate from `marine_tidal_capacity`: a barrage and a tidal-stream "
	 "array are different technologies with different resource bases, and one "
	 "ceiling over both would let a barrage scenario cap a stream project."),
	("solar_pv_land_constraint", "MW", [0.0, 500000.0], 20000.0, "fixed",
	 "The land ceiling expressed as the PV nameplate the available land "
	 "supports, in megawatts. Retyped to `solar_pv_capacity`'s own ceiling. "
	 "The node is a *converted* land ceiling and not a land area: the graph "
	 "carries no MW-per-hectare intensity, so a ceiling in hectares could not "
	 "be turned into a build limit by any equation in the library."),
	("solar_pv_max_build", "MW", [0.0, 500000.0], 20000.0, "fixed",
	 "The PV build ceiling, in megawatts. Retyped to the PV capacity's own "
	 "ceiling. Its description calls it an annual build ceiling while it is "
	 "stated against the stock, because the graph carries no annual-increment "
	 "node; the prose here says so rather than inheriting the mislabel."),
	("solar_thermal_capacity", "MW", [0.0, 30000.0], 0.0, "fixed",
	 "Solar thermal nameplate, in megawatts, defaulted to zero. Retyped to "
	 "`csp_capacity`'s ceiling: solar thermal *is* the CSP build under the "
	 "catalog's second spelling, so it shares that capacity's upper bound "
	 "without being an alias of it."),
	("transboundary_water_constraint", "m3/year", [0.0, 1.0e11], 2.0e8,
	 "fixed",
	 "The basin's allocation to the project, in cubic metres a year. Retyped "
	 "from the placeholder to `total_water_demand_m3`'s own unit and range. "
	 "The 2.0e8 default is `water_availability_m3`'s default, so the two "
	 "ceilings agree at the reference scenario instead of one silently "
	 "binding the other. A ceiling defaulted below the propagated demand "
	 "would ship a graph that fails its own constraint."),
	# `cat_bond_spread` is quoted per annum -- a spread is an annual rate --
	# and its shipped unit was the bare `basis_points`, which the walker reads
	# as dimensionless. That made the coupon equation's right side
	# `USD * MW / kW` against a left side of `USD/year`, so the product was
	# inconsistent by a factor of time. Retyping the spread is the fix: the
	# `0.0001` in the equation converts basis points to a fraction and the
	# `/year` supplies the period the coupon is paid over.
	("cat_bond_spread", "basis_points/year", [200.0, 2500.0], 800.0,
	 "stochastic",
	 "The coupon a catastrophe bond pays over the risk-free rate, in basis "
	 "points per annum. Retyped from the bare `basis_points` to a rate: a "
	 "spread is quoted per year, and the shipped unit left the coupon "
	 "equation's two sides differing by a factor of time. 800 bp is 8% over "
	 "the risk-free rate, which is the order a cat-bond tranche pays."),
	("spare_parts_lead_time", "hours", [500.0, 500000.0], 720.0, "fixed",
	 "The lead time to deliver a spare part, in hours. Retyped to "
	 "`mean_time_between_failures`'s own range so the two quantities are "
	 "comparable: a part whose delivery takes longer than the unit's mean "
	 "time between failures makes the expected wait for it dominate "
	 "availability. 720 h is 30 days against a 50,000 h MTBF."),
)

BATCH31_AMEND_RETYPES: tuple[tuple[str, str, list[float], float, str], ...] = (
	("distribution_loss_factor", "1", [0.0, 0.2], 0.06, "fixed",
	 "The share of delivered energy lost in the secondary distribution "
	 "network. Narrowed from [0, 1] to [0, 0.2]: a loss share above 20% is not "
	 "a distribution network but a fault. The default moves from 0.5 to 0.06 "
	 "in the same edit, because 0.5 is not a loss rate -- at the shipped "
	 "46.54 TWh demand it loses 23.27 TWh, so half the energy sold disappears "
	 "in the secondary network. 6% is the level a single-country low-voltage "
	 "network actually runs at; the 20% ceiling leaves room for a stressed "
	 "scenario without admitting an arithmetic error as one."),
)

BATCH31_DERIVED: tuple[tuple[str, str, list[float], str, str, str], ...] = (
	("available_land_hectares", "hectare", [0.0, 500000.0], "physical",
	 "Land Use & Community",
	 "The share of the project's land take that is technically and legally "
	 "available for construction: the availability fraction times the take. "
	 "`land_area_hectares` describes itself as the project's own take, so the "
	 "two nodes agree on the base and the earlier reading of this share as a "
	 "fraction of a separate *study area* was the mistake. 0.5 x 5,000 ha is "
	 "2,500 ha."),
	("cultural_heritage_sites", "sites", [0.0, 2500.0], "fixed",
	 "Environmental",
	 "Expected count of cultural-heritage sites inside the project footprint: "
	 "the measured density per 100 km2 times the land take converted to the "
	 "density's own denominator, built exactly as the archaeological and "
	 "sacred counts are. 2.0 per 100 km2 over 5,000 ha is 1.0 site. The 2,500 "
	 "ceiling is the 50 per 100 km2 top of the density band over a 500,000 ha "
	 "take."),
	("cat_bond_coupon_cost_usd", "USD/year", [0.0, 1.0e12], "stochastic",
	 "Insurance & Catastrophe",
	 "The coupon a catastrophe bond pays per year: its spread over the "
	 "risk-free rate, applied to the debt tranche of the asset value. 800 bp "
	 "on 70% of 1,200 USD/kW over 10 GW is 672 million USD a year. The "
	 "`0.0001` is the basis-point-to-fraction conversion, which is why the "
	 "walker reads the spread as a dimensionless multiplier over the currency "
	 "the rest of the product carries. Determinism is stochastic because the "
	 "spread is."),
	("crew_shortfall_hours_per_year", "hours/year", [0.0, 8760.0], "fixed",
	 "Operational",
	 "Planned maintenance hours lost to crew unavailability: the unavailable "
	 "share times the planned hours. 0.15 x 96 h is 14.4 h/year. The shipped "
	 "graph carries the planned hours and not the shortfall, so this is the "
	 "quantity no node held; the available-hours spelling would restate a "
	 "number the graph already has."),
	("distribution_losses_twh", "TWh/year", [0.0, 4000.0], "fixed",
	 "Grid",
	 "Energy lost in the secondary distribution network: the loss share times "
	 "delivered demand. At the corrected 0.06 it is 2.79 TWh of 46.54; at the "
	 "placeholder 0.5 it would have been 23.27, half the energy sold. The "
	 "4,000 TWh ceiling is the loss share's 20% top over the demand band's "
	 "20,000 TWh."),
	("hydro_effective_capacity_factor", "1", [0.0, 1.0], "stochastic",
	 "Generation",
	 "The drought-adjusted hydro output share: the base capacity factor times "
	 "the drought multiplier. 0.55 x 0.5 is 0.275. Read against "
	 "`capacity_factor_hydro` and not against the `hydro_capacity_factor` "
	 "alias, so the product does not depend on another batch's alias."),
	("internet_users", "people", [0.0, 2.0e8], "fixed", "Digital",
	 "People with internet access: the penetration share times the "
	 "population. 0.5 x 45 M is 22.5 M. Measured against total population and "
	 "not the electrified subset: connectivity is a population share, and "
	 "multiplying by the subset would condition it on an unrelated dial."),
	("mobile_covered_population", "people", [0.0, 2.0e8], "fixed",
	 "Digital",
	 "People inside mobile coverage: the coverage share times the population. "
	 "0.9 x 45 M is 40.5 M, on the same base as internet users and for the "
	 "same reason."),
	("vulnerable_population", "people", [0.0, 2.0e8], "fixed", "Social",
	 "People exposed under the composite vulnerability index: the index times "
	 "the population. 0.5 x 45 M is 22.5 M. The index is an "
	 "exposure/sensitivity/adaptive-capacity composite and is read here as a "
	 "share of the population, which is the one reading that makes it "
	 "multiplicative; it is deliberately not aliased to a complement of "
	 "adaptive capacity, an identity the index literature does not state."),
	("parcels_to_assemble", "parcels", [0.0, 2.5e6], "fixed", "Land",
	 "Land parcels that must be assembled for the project: the parcel density "
	 "per km2 times the land take. 20 per km2 over 5,000 ha is 1,000 parcels. "
	 "The `/100` converts hectares to the density's own denominator -- one "
	 "km2 is 100 ha -- which is why the walker resolves the right-hand side "
	 "to parcels. The 2.5 M ceiling is the 500 per km2 top of the density "
	 "band over a 500,000 ha take."),
	("licence_fee_spend_usd_per_year", "USD/year", [0.0, 5.0e9], "policy",
	 "Regulatory",
	 "The annual licence bill: the per-MW fee over the licensed fleet. 500 "
	 "USD/MW/year over 10,000 MW is 5.0 M USD/year. Levied on total nameplate "
	 "and not on firm capacity, because a licence attaches to every megawatt "
	 "registered and a firm-capacity base would exempt the VRE fleet the fee "
	 "is charged on."),
	("predictive_maintenance_hours_per_year", "hours/year", [0.0, 8760.0],
	 "fixed", "Operational",
	 "Planned maintenance hours moved into the predictive regime: the "
	 "adoption share times the planned hours. 0.5 x 96 h is 48 h/year. The "
	 "moved hours are the quantity the node names; the complement is "
	 "derivable from them and is not a second node."),
	("spare_parts_deferred_hours_per_year", "hours/year", [0.0, 8760.0],
	 "fixed", "Operational",
	 "Planned maintenance hours deferred by parts stockouts: the unavailable "
	 "share of spares times the planned hours. 0.2 x 96 h is 19.2 h/year."),
	("representative_snapshots", "1", [0.0, 9600.0], "fixed", "Temporal",
	 "The time slices the representative-day sampling produces: the sampled "
	 "days times the segments per day. 50 x 24 is 1,200 snapshots. The "
	 "right-hand side is dimensionless under the walker because "
	 "`tsam_segments` is 1/day, which is what a count should be -- the "
	 "alternative `representative_days * 24` carries a bare constant and "
	 "`unit_of` returns `day` for it, so the checker could not see the hour."),
	("outage_events_from_cause", "events/year", [0.0, 500.0], "stochastic",
	 "Outage",
	 "Interruption events attributable to a named cause: the cause share "
	 "times the system event rate. 0.35 x 12 events/year is 4.2 weather-caused "
	 "events a year. A share of events times a rate of events, which is why "
	 "the SAIDI hours are not the base -- a share of events times hours is "
	 "neither."),
	("peak_demand_shifted_mw", "MW", [1.0, 2.0e6], "fixed", "Demand",
	 "Peak demand under a scaling factor: one plus the multiplier, times the "
	 "base peak. 1.5 x 8,500 MW is 12,750 MW. The `(1 + m)` form is the only "
	 "one whose zero is a no-op; a bare product would halve peak demand at "
	 "the shipped 0.5, which is a derating and not the scaling factor the "
	 "node names."),
	("precipitation_adjusted_flow_m3_per_s", "m3/s", [0.0, 2000.0],
	 "stochastic", "Water",
	 "The mean annual river flow under a precipitation scenario: the "
	 "multiplier times the base flow. 0.5 x 150 m3/s is 75 m3/s. Applied to "
	 "the raw flow and not to `environmental_flow_m3_per_s`, which is already "
	 "derived from the flow and the requirement share -- applying it there "
	 "would count the scenario twice."),
	("thin_capitalisation_utilisation", "1", [0.0, 3.0], "policy", "Tax",
	 "The gearing expressed against the thin-capitalisation ceiling: debt to "
	 "equity over the limit. 2.33 / 1.5 is 1.55, which says the graph's own "
	 "defaults breach the ceiling by 55%. A utilisation ratio and not a bound, "
	 "because the bound `limit >= debt_equity_ratio` would fail at defaults "
	 "and a batch that ships it ships a violating graph. The breach is the "
	 "finding; the ratio reports it."),
	("transmission_transfer_mw", "MW", [0.0, 1.0e6], "fixed",
	 "Transmission & Grid",
	 "The power the transmission fleet actually transfers: the utilisation "
	 "share times installed nameplate. 0.5 x 10,000 MW is 5,000 MW. A product "
	 "and not a bound: there is no transfer-limit node to bound it against, "
	 "and the transferred power is the quantity the flow reports need."),
	("wind_effective_capacity_factor", "1", [0.0, 1.0], "stochastic",
	 "Generation",
	 "The onshore wind output share under a resource scenario: the base "
	 "capacity factor times the multiplier. 0.4 x 0.5 is 0.20. The node is a "
	 "*yield* multiplier and not a speed ratio: cubing it by the wind-power "
	 "law would drive every scenario to zero on a [0, 1] dial, so the linear "
	 "form is the physics the node can carry."),
	("solar_effective_capacity_factor", "1", [0.0, 1.0], "stochastic",
	 "Generation",
	 "The PV output share under an irradiance scenario: the base capacity "
	 "factor times the multiplier. 0.22 x 0.5 is 0.11. Applied to the "
	 "capacity factor and not to the LCOE, because the LCOE already divides "
	 "by the capacity factor and the multiplier would enter twice with "
	 "opposite signs."),
	("water_stress_index", "1", [0.0, 5.0], "physical", "Water",
	 "Demand over availability: 93.25e6 m3/year over 200e6 is 0.466. The "
	 "range must admit above 1, because a drought scenario that consumes "
	 "more than the available supply is a real state and a [0, 1] band would "
	 "report it as a range excursion rather than as the stress it is. Derived "
	 "because it is the ratio of two graph nodes; the shipped 0.4 default was "
	 "not that ratio and cannot survive the node becoming derived."),
)

BATCH31_ALIASES: tuple[tuple[str, str, str, str, str, str], ...] = (
	("capex_gas_ccgt", "capex_gas", "USD/kW", "Technology",
	 "The combined-cycle gas turbine's capital cost. The catalog carries the "
	 "CCGT cost twice: `capex_gas` is the 1,100 USD/kW CCGT number and this "
	 "node is the same figure under a technology-specific id. The alias keeps "
	 "one spelling and makes the duplicate a derived node rather than a "
	 "second dial that could disagree."),
	("csp_storage_hours", "thermal_storage_duration", "hours", "Storage",
	 "The hours a CSP plant's thermal store discharges at rated output. A CSP "
	 "store is a thermal store, so this is the graph's own "
	 "`thermal_storage_duration` under the catalog's second id. The shipped "
	 "24 h default is three times the graph's 8 h; the alias resolves the "
	 "disagreement in favour of the graph's own number rather than carrying "
	 "two dials for one physical quantity."),
	("demand_response_capacity", "interruptible_load_mw", "MW", "Demand-Side",
	 "Enrolled demand-response capacity: the interruptible load the graph "
	 "already derives from the interruptible share and peak demand. 4,250 MW "
	 "at defaults. The alternative -- a product against `peak_demand_mw` on a "
	 "new potential share -- computes the same number from the same peak "
	 "demand, which is `interruptible_load_mw_definition` under another name."),
	("demand_response_potential", "interruptible_load_share", "1",
	 "Demand-Side",
	 "The flexible share of demand a demand-response programme can enrol. The "
	 "graph already states the share as `interruptible_load_share` (0.5), and "
	 "a second base at the classification pack's 0.15 would let two dials "
	 "disagree about one physical quantity."),
	("fuel_cost_hydrogen", "hydrogen_price_per_mwh", "USD/MWh", "Cost",
	 "Delivered hydrogen cost per MWh of thermal energy: the graph's own "
	 "converted price, 90.01 USD/MWh, against this node's shipped 120. The "
	 "conversion is `hydrogen_price_per_mwh_definition`'s and is not repeated "
	 "here, because repeating the 33.33 kWh/kg constant would let the two "
	 "conversions drift."),
	("hydro_capacity_factor", "capacity_factor_hydro", "1", "Generation",
	 "The hydro output share. The catalog carries it under two ids and "
	 "`lcoe_hydro_definition` already reads `capacity_factor_hydro` (0.55); "
	 "this alias makes the second spelling derived instead of a dial that can "
	 "disagree."),
)

BATCH31_EQUATIONS: tuple[
	tuple[str, str, str, str, str, str, str | None], ...
] = (
	# --- the alias family -----------------------------------------------
	("capex_gas_ccgt_definition", "The CCGT capital cost",
	 "capex_gas_ccgt", "capex_gas",
	 "The combined-cycle gas turbine's capital cost is the graph's gas "
	 "capital cost. An alias rather than a second dial: the catalog's two ids "
	 "carry one number, and a derived node cannot drift from the one it "
	 "names. 1,100 USD/kW at defaults.",
	 "cost_accounting",
	 "IEA/NEA Projected Costs of Generating Electricity"),
	("csp_storage_hours_definition", "The CSP store's hours",
	 "csp_storage_hours", "thermal_storage_duration",
	 "A CSP plant's store is a thermal store, so its hours at rated output "
	 "are the graph's thermal-store duration: 8 h, against this node's "
	 "shipped 24. The alias resolves a disagreement between two ids for one "
	 "physical quantity in favour of the one the rest of the library reads.",
	 "energy_balance", None),
	("demand_response_capacity_definition", "Enrolled demand response",
	 "demand_response_capacity", "interruptible_load_mw",
	 "The enrolled flexible capacity is the interruptible load the graph "
	 "already derives: 4,250 MW from a 0.5 interruptible share over an 8,500 "
	 "MW peak. An alias, because the product form would compute the same "
	 "number from the same two operands under a third id.",
	 "demand_supply", None),
	("demand_response_potential_definition", "The demand-response share",
	 "demand_response_potential", "interruptible_load_share",
	 "The flexible share of demand a programme can enrol is the interruptible "
	 "share the graph already carries: 0.5. A second share base would let two "
	 "dials disagree about one physical quantity.",
	 "demand_supply", None),
	("fuel_cost_hydrogen_definition", "The delivered hydrogen cost",
	 "fuel_cost_hydrogen", "hydrogen_price_per_mwh",
	 "The delivered hydrogen cost per MWh of thermal energy is the graph's "
	 "own converted price: 90.01 USD/MWh, against this node's shipped 120. "
	 "The conversion from a price per unit mass to a price per MWh lives in "
	 "`hydrogen_price_per_mwh_definition` and is not repeated.",
	 "cost_accounting",
	 "LHV of H2: 33.33 kWh/kg (standard fuel tables)"),
	("hydro_capacity_factor_definition", "The hydro output share",
	 "hydro_capacity_factor", "capacity_factor_hydro",
	 "The hydro output share is the capacity factor the LCOE and the "
	 "generation equations already read: 0.55. An alias, so the catalog's "
	 "second spelling is derived rather than a dial that can disagree with "
	 "the first.",
	 "energy_balance", None),
	# --- the site and land counts ---------------------------------------
	("cultural_heritage_sites_definition", "Cultural heritage sites",
	 "cultural_heritage_sites",
	 "cultural_heritage_sites_density * land_area_hectares / 10000",
	 "Expected count of cultural-heritage sites inside the project footprint: "
	 "the measured density per 100 km2 times the land take converted to the "
	 "density's own denominator. The 10000 is exact, not a fudge: one hectare "
	 "is 0.01 km2, so hectares over 10,000 is hectares expressed in units of "
	 "100 km2. 2.0 per 100 km2 over 5,000 ha is 1.0 site, and a fractional "
	 "value is the expectation, not a count of objects.",
	 "financial", None),
	("available_land_hectares_definition", "Available land",
	 "available_land_hectares",
	 "land_availability_fraction * land_area_hectares",
	 "The land actually available for construction: the availability share "
	 "times the project's land take. 0.5 x 5,000 ha is 2,500 ha. The base is "
	 "the take and not a separate study area, because `land_area_hectares` "
	 "describes itself as the project's own take -- which is what an "
	 "availability share applies to.",
	 "financial", None),
	("parcels_to_assemble_definition", "Parcels to assemble",
	 "parcels_to_assemble",
	 "land_aggregation_fragmentation * land_area_hectares / 100",
	 "Land parcels that must be assembled: the parcel density per km2 times "
	 "the land take. The `/100` is the hectare-to-km2 conversion -- one km2 "
	 "is 100 ha -- so the right-hand side resolves to parcels. 20 per km2 "
	 "over 5,000 ha is 1,000 parcels, which is the transaction count a land "
	 "assembly programme has to clear.",
	 "financial", None),
	# --- the share products ---------------------------------------------
	("internet_users_definition", "Internet users",
	 "internet_users", "internet_penetration * population_total",
	 "People with internet access: the penetration share times the "
	 "population. 0.5 x 45 M is 22.5 M. The base is total population and not "
	 "the electrified subset: connectivity is a population share, and "
	 "conditioning it on electrification would make a digital dial move when "
	 "an unrelated grid dial moved.",
	 "financial", None),
	("mobile_covered_population_definition", "People in mobile coverage",
	 "mobile_covered_population", "mobile_coverage * population_total",
	 "People inside mobile coverage: the coverage share times the population. "
	 "0.9 x 45 M is 40.5 M. Same base as internet users, so the two "
	 "connectivity measures are comparable and their difference is the "
	 "coverage-versus-adoption gap.",
	 "financial", None),
	("vulnerable_population_definition", "Vulnerable population",
	 "vulnerable_population", "vulnerability_index * population_total",
	 "People exposed under the composite vulnerability index: the index times "
	 "the population. 0.5 x 45 M is 22.5 M. The index is an "
	 "exposure/sensitivity/adaptive-capacity composite, and applying it as a "
	 "share of the population is the one reading that makes it "
	 "multiplicative. It is deliberately not aliased to a complement of "
	 "adaptive capacity -- an identity the index literature does not state.",
	 "health", None),
	("peak_demand_shifted_definition", "Peak demand under a scaling factor",
	 "peak_demand_shifted_mw",
	 "(1 + peak_demand_multiplier) * peak_demand_mw",
	 "Peak demand under a scaling factor: one plus the multiplier, times the "
	 "base peak. 1.5 x 8,500 MW is 12,750 MW. The `(1 + m)` form is the only "
	 "one whose zero is a no-op; a bare product at the shipped 0.5 would "
	 "halve peak demand, which is a derating and not the scaling factor the "
	 "node's name asserts.",
	 "demand_supply", None),
	("licence_fee_spend_definition", "The licence bill",
	 "licence_fee_spend_usd_per_year", "licence_fees * total_capacity_mw",
	 "The annual licence bill: the per-MW fee over the licensed fleet. 500 "
	 "USD/MW/year over 10,000 MW is 5.0 million USD/year. Levied on total "
	 "nameplate, not firm capacity: a licence attaches to every megawatt "
	 "registered, and a firm-capacity base would exempt the VRE fleet the fee "
	 "is charged on.",
	 "cost_accounting", None),
	("transmission_transfer_definition", "The transferred power",
	 "transmission_transfer_mw",
	 "transmission_capacity_factor * total_capacity_mw",
	 "The power the transmission fleet transfers: the utilisation share times "
	 "installed nameplate. 0.5 x 10,000 MW is 5,000 MW. A product rather than "
	 "a bound, because the graph carries no transfer-limit node to bound it "
	 "against and the transferred power is what the flow reports need.",
	 "energy_balance", None),
	("cat_bond_coupon_cost_definition", "The cat-bond coupon",
	 "cat_bond_coupon_cost_usd",
	 "cat_bond_spread * 0.0001 * debt_fraction * capex_usd_per_kw * "
	 "total_capacity_mw * 1000",
	 "The coupon a catastrophe bond pays per year: its spread over the "
	 "risk-free rate, applied to the debt tranche of the asset value. 800 bp "
	 "on 70% of 1,200 USD/kW over 10 GW is 672 million USD a year. The "
	 "`0.0001` converts basis points to a fraction and the `1000` converts "
	 "USD/kW over MW to USD, which is why the walker resolves the whole "
	 "product to currency.",
	 "financial", None),
	("thin_capitalisation_utilisation_definition", "Gearing against the ceiling",
	 "thin_capitalisation_utilisation",
	 "debt_equity_ratio / thin_capitalisation_limit",
	 "The gearing expressed against the thin-capitalisation ceiling: debt to "
	 "equity over the limit. 2.33 / 1.5 is 1.55, so the graph's own defaults "
	 "breach the ceiling by 55%. A utilisation ratio rather than a bound, "
	 "because `thin_capitalisation_limit >= debt_equity_ratio` fails at "
	 "defaults and a batch shipping it would ship a violating graph. The "
	 "breach is the finding; this node reports it instead of failing on it.",
	 "financial",
	 "OECD, Limiting Base Erosion Involving Interest Deductions and Other "
	 "Financial Payments, Action 4 (2015)"),
	# --- the operational shortfalls -------------------------------------
	("crew_shortfall_definition", "Crew shortfall hours",
	 "crew_shortfall_hours_per_year",
	 "(1 - crew_availability) * planned_maintenance_hours_per_year",
	 "Planned maintenance hours lost to crew unavailability: the unavailable "
	 "share times the planned hours. 0.15 x 96 h is 14.4 h/year. The graph "
	 "already carries the planned hours, so the available-hours spelling "
	 "would restate a number it has; the shortfall is the quantity it lacks.",
	 "reliability", None),
	("spare_parts_deferred_definition", "Deferred maintenance hours",
	 "spare_parts_deferred_hours_per_year",
	 "(1 - spare_parts_availability) * planned_maintenance_hours_per_year",
	 "Planned maintenance hours deferred by parts stockouts: the unavailable "
	 "share of spares times the planned hours. 0.2 x 96 h is 19.2 h/year. "
	 "Alongside the crew shortfall it gives the two independent reasons "
	 "planned work does not happen, which a single availability figure would "
	 "conflate.",
	 "reliability", None),
	("predictive_maintenance_hours_definition", "Predictive maintenance hours",
	 "predictive_maintenance_hours_per_year",
	 "predictive_maintenance_adoption * planned_maintenance_hours_per_year",
	 "Planned maintenance hours moved into the predictive regime: the "
	 "adoption share times the planned hours. 0.5 x 96 h is 48 h/year. The "
	 "moved hours are the quantity the node names; the unmoved complement is "
	 "derivable from them and is not a second node.",
	 "reliability", None),
	("outage_events_from_cause_definition", "Events from a named cause",
	 "outage_events_from_cause",
	 "outage_cause_distribution * system_saifi_events_per_year",
	 "Interruption events attributable to a named cause: the cause share "
	 "times the system event rate. 0.35 x 12 events/year is 4.2 weather-caused "
	 "events a year. The base is the event rate and not the SAIDI hours -- a "
	 "share of events times hours is neither a count nor a duration.",
	 "reliability",
	 "IEEE Guide for Electric Power Distribution Reliability Indices (1366), "
	 "tutorial deck"),
	# --- the energy products --------------------------------------------
	("distribution_losses_definition", "Distribution losses",
	 "distribution_losses_twh", "distribution_loss_factor * demand_twh",
	 "Energy lost in the secondary distribution network: the loss share times "
	 "delivered demand. At the corrected 0.06 it is 2.79 TWh of 46.54; at the "
	 "placeholder 0.5 it was 23.27, which is half the energy sold vanishing "
	 "in the secondary network. Shipping the product is what makes the "
	 "default visible as a number rather than as a dial nobody multiplies.",
	 "energy_balance", None),
	("hydro_effective_capacity_factor_definition", "Drought-adjusted hydro share",
	 "hydro_effective_capacity_factor",
	 "capacity_factor_hydro * hydro_drought_multiplier",
	 "The drought-adjusted hydro output share: the base capacity factor times "
	 "the drought multiplier. 0.55 x 0.5 is 0.275. Read against "
	 "`capacity_factor_hydro` and not the `hydro_capacity_factor` alias, so "
	 "the product does not depend on another batch's alias resolving first.",
	 "energy_balance", None),
	("wind_effective_capacity_factor_definition", "Wind resource share",
	 "wind_effective_capacity_factor",
	 "capacity_factor_wind_onshore * wind_speed_multiplier",
	 "The onshore wind output share under a resource scenario: the base "
	 "capacity factor times the multiplier. 0.4 x 0.5 is 0.20. The node is a "
	 "*yield* multiplier and not a speed ratio: the wind-power law would cube "
	 "it, and cubing a [0, 1] dial drives every scenario to zero. The prose "
	 "carries the distinction because the linear form is otherwise a physics "
	 "error wearing a correct dimension.",
	 "energy_balance", None),
	("solar_effective_capacity_factor_definition", "Solar resource share",
	 "solar_effective_capacity_factor",
	 "solar_pv_capacity_factor * solar_irradiance_multiplier",
	 "The PV output share under an irradiance scenario: the base capacity "
	 "factor times the multiplier. 0.22 x 0.5 is 0.11. Applied to the "
	 "capacity factor and not to the LCOE: the LCOE already divides by the "
	 "capacity factor, so a multiplier there would enter twice with opposite "
	 "signs.",
	 "energy_balance", None),
	("precipitation_adjusted_flow_definition", "The scenario river flow",
	 "precipitation_adjusted_flow_m3_per_s",
	 "precipitation_multiplier * river_mean_annual_flow_m3_per_s",
	 "The mean annual river flow under a precipitation scenario: the "
	 "multiplier times the base flow. 0.5 x 150 m3/s is 75 m3/s. Applied to "
	 "the raw flow and not to `environmental_flow_m3_per_s`, which is already "
	 "derived from the flow and the requirement share -- applying the "
	 "scenario there would count it twice.",
	 "water_energy", None),
	("representative_snapshots_definition", "Representative snapshots",
	 "representative_snapshots", "representative_days * tsam_segments",
	 "The time slices the representative-day sampling produces: the sampled "
	 "days times the segments per day. 50 x 24 is 1,200 snapshots. The "
	 "right-hand side is dimensionless under the walker because "
	 "`tsam_segments` is 1/day, which is what a count should be; the "
	 "alternative `representative_days * 24` carries a bare constant that "
	 "`unit_of` reads as `day`, so the checker could not see the hour.",
	 "energy_balance", None),
	("water_stress_index_definition", "The water stress index",
	 "water_stress_index",
	 "total_water_demand_m3 / water_availability_m3",
	 "Demand over availability: 93.25e6 m3/year over 200e6 is 0.466. A ratio "
	 "of two graph nodes and therefore derived, which is why its shipped 0.4 "
	 "default has to go: a derived node carries no default, and 0.4 was not "
	 "the ratio its own two inputs compute.",
	 "water_energy", None),
)

def build_batch31(
	graph: Any,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""Batch 31: the PRODUCT remainder -- retypes, products and three amendments.

	Thirty-eight nodes, authored from
	``docs/research/coupling-packs/threshold-product-remainder.md``. The pack
	covers sixty-six: twenty-five THRESHOLD and forty-one PRODUCT. This batch
	takes the PRODUCT arithmetic and the retype both classes need; the
	twenty-three THRESHOLD bounds are batch 32, because a bound is a different
	mechanism and mixing the two would leave the edge register unable to say
	which equation coupled which node.

	Six nodes are already coupled by the shipped graph
	(``archaeological_sites_density``, ``sacred_sites_density``,
	``synthetic_fuel_share_aviation``, ``synthetic_fuel_share_shipping``,
	``distribution_network_km``, ``hydrogen_storage_capacity``) and this batch
	does not propose a second equation for any of them.

	Three shipped equations are amended, each because the shipped form reads
	the wrong operand:

	* ``coal_eaf_definition`` reads the *generic* ``forced_outage_rate``,
	  which ``availability_definition`` derives from MTBF/MTTR as 24/50024 =
	  0.00048. That is a 0.05% forced-outage rate for coal, against the 10%
	  ``forced_outage_rate_coal`` carries -- a factor of 200, and the shipped
	  equation reads the wrong one. The amendment takes coal availability from
	  0.9495 to 0.85.
	* ``lcoe_wind_definition`` is an *onshore* LCOE -- it divides by
	  ``capacity_factor_wind_onshore`` -- but reads the generic
	  ``opex_fixed_wind`` (40) rather than ``opex_fixed_wind_onshore`` (30).
	  The amendment takes the LCOE from 66.53 to 63.67 USD/MWh. The
	  alternative, aliasing ``opex_fixed_wind`` to the onshore node, would
	  make an existing shipped node derived and drop its 40 default to fix an
	  equation that is the actual defect.
	* ``transmission_investment_definition`` does not name
	  ``transmission_cost_multiplier`` at all, so the multiplier is a dial
	  nothing multiplies. The amendment inserts it. The shipped form also
	  multiplies ``capex_transmission`` (USD/MW-km) by total fleet MW rather
	  than route MW, giving 48 bn USD for a 10 GW fleet; that defect is
	  recorded here and NOT fixed, because the fix needs a route-MW base the
	  graph does not carry and inventing one would be a second unverified
	  number behind the first.

	Two default corrections ship with the couplings that expose them.
	``distribution_loss_factor`` moves from 0.5 to 0.06 and its range narrows
	to [0, 0.2]: half of all delivered energy lost is not a loss rate, and the
	product equation is what turns the placeholder into a visible 23.27 TWh.
	``water_stress_index`` becomes derived, because it is the ratio of two
	graph nodes (0.466) and its shipped 0.4 is not that ratio.

	Aliases carry six duplicate ids onto the quantity the library already
	reads. The rule for an alias here is that two ids name one physical
	quantity and the shipped defaults disagree; the alias makes the second id
	derived so it cannot drift. Where the two ids name *different* quantities
	that merely look alike -- ``solar_thermal_capacity`` against
	``csp_capacity``, a technology label against a capacity -- the node is
	retyped and bounded instead, which is batch 32's work.

	The twenty-three nodes that defer or are rejected are named in the pack.
	Seven need a base this batch does not add (``hydrogen_storage_duration``,
	``max_remedy_period_days``, ``grievances_received_per_year``,
	``jobs_per_grievance``, ``capacity_factor_gas_ocgt``, a heat-rate term,
	an annual-build increment), three are prior rejections re-confirmed
	(``line_outage_start``, ``line_outage_end``, ``storage_duration_curve``),
	and ``capex_gas_ocgt`` defers because the LCOE form has no efficiency term
	and would price the peaker below the combined cycle.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH31_RETYPES:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": "free", "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product remainder (batch 31)",
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, default, determinism, prose in BATCH31_AMEND_RETYPES:
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name} is not shipped; an amendment needs one"
		full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"description": prose, "unit": unit, "range": rng,
			"determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product remainder (batch 31)",
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, determinism, category, prose in BATCH31_DERIVED:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product remainder (batch 31)",
			"users": ["Planners", "Regulators"],
		})
		full.pop("default", None)
		nodes[name] = full

	for name, driver, unit, category, prose in BATCH31_ALIASES:
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name} is not shipped; an alias retypes one"
		full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"description": prose, "category": category, "unit": unit,
			"role": "derived", "determinism": "fixed", "priority": "P1",
			"status": _kept_status(shipped),
			"source": "The product remainder (batch 31)",
		})
		full.pop("default", None)
		# The alias takes its driver's range: an alias whose range is wider
		# than its driver's is a range the driver can never produce, and the
		# range-excursion walk would then pass on a value the graph cannot
		# hold.
		full["range"] = list(graph.nodes[driver].range)
		nodes[name] = full

	for eq_id, name, lhs, rhs, prose, system, cite in BATCH31_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id, "name": name, "description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		assert lhs in nodes, f"{eq_id}: {lhs!r} has no node body in this batch"
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})

	# --- the three amended shipped equations ----------------------------
	# The bake merges equations by id, so writing the same id with a new body
	# replaces the shipped form rather than adding a second equation on the
	# same target.
	amendments = {
		"coal_eaf_definition": {
			"rhs": "1 - forced_outage_rate_coal - planned_outage_rate",
			"description": (
				"The coal fleet's equivalent availability uses the coal "
				"fleet's own forced-outage rate, not the system-wide one. The "
				"shipped form read `forced_outage_rate`, which "
				"`availability_definition` derives from MTBF/MTTR as 24/50024 "
				"= 0.00048 -- a 0.05% forced-outage rate for a coal fleet, "
				"against the 10% `forced_outage_rate_coal` carries. The two "
				"differ by a factor of 200. At defaults the amendment gives "
				"1 - 0.10 - 0.05 = 0.85 instead of 0.9495."
			),
		},
		"lcoe_wind_definition": {
			"rhs": (
				"(annualised_capex_usd_per_kw_wind + opex_fixed_wind_onshore) "
				"* 1000 / (8760 * capacity_factor_wind_onshore) "
				"+ opex_variable_wind"
			),
			"description": (
				"The levelised cost of onshore wind. The shipped form divided "
				"by `capacity_factor_wind_onshore` -- it is an onshore LCOE -- "
				"but read the generic `opex_fixed_wind` (40 USD/kW/year) "
				"rather than `opex_fixed_wind_onshore` (30). The amendment "
				"takes the LCOE from 66.53 to 63.67 USD/MWh at defaults. "
				"Aliasing `opex_fixed_wind` to the onshore node was rejected: "
				"it would make a shipped node derived and drop its default to "
				"fix an equation that is the actual defect."
			),
			"reference": "NREL ATB 2025 Equations & Variables",
		},
		"transmission_investment_definition": {
			"rhs": (
				"transmission_cost_multiplier * capex_transmission "
				"* transmission_line_length_km * total_capacity_mw"
			),
			"description": (
				"The transmission investment, with the terrain and tender "
				"multiplier applied. The shipped form did not name "
				"`transmission_cost_multiplier` at all, so the multiplier was "
				"a dial nothing multiplied. It computes 48 bn USD for a 10 GW "
				"fleet at defaults, which is high because the shipped product "
				"treats `capex_transmission` (USD/MW-km) as per fleet "
				"megawatt rather than per route megawatt; that defect is "
				"recorded and not fixed here, because the fix needs a "
				"route-MW base the graph does not carry."
			),
		},
	}
	for eq_id, amend in amendments.items():
		shipped_eq = graph.equations.get(eq_id)
		assert shipped_eq is not None, f"{eq_id} is not shipped"
		body = dict(shipped_eq.model_dump(exclude={"id"}, mode="json"))
		body.update(amend)
		named = sorted(
			set(parse_side(body["lhs"]).symbols)
			| set(parse_side(body["rhs"]).symbols)
		)
		body["parameters"] = named
		body["free_variables"] = [
			sym for sym in named
			if sym != body["determined_variables"][0]
		]
		equations[eq_id] = body
		# An amendment keeps the shipped edges' strength. Strength is a
		# property of the equation, not of the edge, and the graph refuses an
		# equation cited at two tiers. `lcoe_wind_definition` ships soft --
		# an LCOE does not constrain a plan -- so emitting hard edges from the
		# amendment put the same equation at both tiers and the loader
		# refused the graph.
		shipped_strength = {
			getattr(edge.strength, "value", edge.strength)
			for edge in graph.edges
			if edge.equation_id == eq_id
		}
		assert len(shipped_strength) <= 1, (
			f"{eq_id} already ships at two strengths: {shipped_strength}"
		)
		strength = next(iter(shipped_strength), "hard")
		for sym in named:
			if sym == body["determined_variables"][0]:
				continue
			edges.append({
				"source": sym, "target": body["determined_variables"][0],
				"equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": strength,
				"description": "Enters the amended identity.",
				"reference": amend.get("reference", body.get("reference")),
				"priority": "P1",
			})

	return nodes, equations, edges, rules


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded)
#: -- the THRESHOLD class: capacity ceilings and one lead-time bound. Every
#: row is an inequality over nodes that already exist, so the
#: batch retypes nothing and derives nothing: a bound couples a node to the
#: quantity that limits it without making the node a function of that
#: quantity, which is why `determined_variables` stays empty on all of them.
BATCH32_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...
] = (
	# --- carbon auction -------------------------------------------------
	("auction_price_cap_bound", "auction_price_cap", "geq",
	 "carbon_price_escalated_usd_per_tco2",
	 "The auction's price ceiling must sit at or above the escalated carbon "
	 "price, or the auction clears above its own cap on day one and the "
	 "instrument is mispriced by construction. At defaults the escalated "
	 "price is 81.44 against a 200 USD/tonne cap, so the constraint holds; "
	 "setting the cap below the trajectory makes it bind, which is the "
	 "policy question an ETS cap answers. The base-year price was "
	 "considered and rejected as the comparison: the cap holds for the "
	 "horizon the auction runs over, and the base price is the one number "
	 "that ignores escalation.",
	 "carbon_trajectory",
	 "EU ETS Directive 2023/959, Art. 21 (auction platform and price "
	 "formation); the cap level is a policy dial the regulation does not "
	 "print",
	 "carbon_price_escalated_usd_per_tco2", "auction_price_cap"),

	# --- build ceilings --------------------------------------------------
	("coal_new_build_bound", "coal_capacity", "leq", "coal_new_build",
	 "New coal build is capped at the policy ceiling: 3000 MW of reference "
	 "fleet under a 5000 MW cap, so a 6000 MW scenario fails. This routes "
	 "as a post-solve check rather than an LP constraint because "
	 "`coal_capacity` is endogenous: the solve chooses it, and a bound on a "
	 "choice is a feasibility test on the answer, not a restriction on the "
	 "programme. A minimum-build reading of the same node was rejected -- a "
	 "dial that *forces* coal is a different parameter, and the node's own "
	 "description says allowed.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity and resource-availability limits); the numeric "
	 "ceiling is a policy figure the review does not print",
	 "coal_new_build", "coal_capacity"),
	("gas_new_build_bound", "gas_capacity", "leq", "gas_new_build",
	 "New gas build capped at 3000 MW against the 1500 MW reference fleet. "
	 "Routes as a post-solve check for the same reason as coal: the "
	 "capacity is endogenous. A bound on `capex_gas` was rejected -- a "
	 "capital-cost ceiling is not a build ceiling, and the two are "
	 "separately dialled.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory); the numeric ceiling is a policy figure",
	 "gas_new_build", "gas_capacity"),
	("hydro_new_build_bound", "hydro_capacity", "leq", "hydro_new_build",
	 "New hydro capped at 3000 MW against the 1500 MW reference fleet. "
	 "Routes as a post-solve check: the capacity is endogenous. A bound "
	 "against the transboundary water ceiling was rejected -- a water "
	 "allocation is not a capacity ceiling, and conflating them would make "
	 "one dial move two bounds.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory); the numeric ceiling is a policy figure",
	 "hydro_new_build", "hydro_capacity"),
	("nuclear_new_build_bound", "nuclear_capacity", "leq", "nuclear_new_build",
	 "New nuclear capped at 5000 MW -- a single large unit or two SMR "
	 "modules -- against a 0 MW reference fleet, so the bound holds "
	 "vacuously today and bites the moment a scenario builds nuclear. "
	 "Routes as a post-solve check: the capacity is endogenous. A bound at "
	 "20000, the capacity's own ceiling, was rejected as vacuous: a ceiling "
	 "equal to the bounded quantity's maximum cannot fail.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory); the numeric ceiling is a policy figure",
	 "nuclear_new_build", "nuclear_capacity"),
	("solar_pv_land_constraint_bound", "solar_pv_capacity", "leq",
	 "solar_pv_land_constraint",
	 "The land ceiling expressed as the PV nameplate the available land "
	 "supports: 10000 MW at the reference build under a 20000 MW ceiling. "
	 "The node is a *converted* land ceiling and its prose must say so -- a "
	 "hectares form was rejected because the graph carries no MW-per-hectare "
	 "intensity, so no equation could turn land into a build limit. Routes "
	 "as a post-solve check: the PV capacity is endogenous.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: land and resource-availability limits); the conversion "
	 "intensity is a policy figure",
	 "solar_pv_land_constraint", "solar_pv_capacity"),
	("solar_pv_max_build_bound", "solar_pv_capacity", "leq",
	 "solar_pv_max_build",
	 "An annual build ceiling stated against the PV *stock*, because the "
	 "graph carries no annual-increment node. The batch records the "
	 "mismatch rather than hiding it: as written the node caps the stock, "
	 "not the annual build its name claims, and a scenario that raises the "
	 "cap raises the permitted total. Renaming the node or adding "
	 "`solar_pv_annual_build_mw` would be a base, not a coupling, and is "
	 "left to a pack that owns it. Routes as a post-solve check.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory); the numeric ceiling is a policy figure",
	 "solar_pv_max_build", "solar_pv_capacity"),
	("solar_thermal_capacity_bound", "solar_thermal_capacity", "leq",
	 "csp_capacity",
	 "Solar thermal is the CSP build under the catalog's second spelling, "
	 "so its ceiling is the CSP nameplate itself: 0 MW against 0 MW at "
	 "defaults, which holds at the boundary and fails the moment a scenario "
	 "sets solar thermal above the CSP fleet. An equality alias to "
	 "`csp_capacity` was considered and rejected -- it would make the node "
	 "derived from an endogenous build, and the two ids are a technology "
	 "label and a capacity, not two spellings of one number. The bound "
	 "leaves the node free and still refuses the inconsistent scenario.",
	 "energy_balance",
	 "IEA/NEA, Projected Costs of Generating Electricity (2020) -- CSP "
	 "capital costs and the solar-thermal technology class",
	 "csp_capacity", "solar_thermal_capacity"),

	# --- storage and the novel generators --------------------------------
	("compressed_air_capacity_bound", "compressed_air_capacity", "leq",
	 "storage_headroom_mw",
	 "Compressed-air storage is bounded by the graph's storage envelope "
	 "rather than by the generation fleet: it is energy-shifting and adds "
	 "no nameplate generation, so the generation ceiling is the wrong "
	 "envelope. Holds vacuously at 0 and fails once a scenario builds past "
	 "the 5000 MW headroom. Membership in `fleet_build_balance` was "
	 "rejected as a tautology: the balance ceiling is generation plus "
	 "headroom, 15000 MW, which admits every admissible value of a node "
	 "whose range tops at 1e6 -- it constrains nothing a plan could violate.",
	 "energy_balance", None,
	 "storage_headroom_mw", "compressed_air_capacity"),
	("flywheel_capacity_bound", "flywheel_capacity", "leq",
	 "storage_headroom_mw",
	 "Flywheel storage sits inside the storage envelope for the same reason "
	 "as compressed air: it shifts energy and adds no generation. Holds at "
	 "0; fails past 5000 MW.",
	 "energy_balance", None,
	 "storage_headroom_mw", "flywheel_capacity"),
	("gravity_storage_capacity_bound", "gravity_storage_capacity", "leq",
	 "storage_headroom_mw",
	 "Gravity storage inside the storage envelope. The classification "
	 "pack's own proposed base `gravity_storage_energy_mwh` (100 MW over 8 "
	 "h) fits under 5000 MW, so the power bound is the one the graph can "
	 "state today. An MWh bound against that base was rejected because the "
	 "base does not exist and is another pack's to add.",
	 "energy_balance", None,
	 "storage_headroom_mw", "gravity_storage_capacity"),
	("storage_capacity_mw_bound", "storage_capacity_mw", "leq",
	 "total_capacity_mw + storage_headroom_mw",
	 "The storage build is bounded by generation plus the storage envelope: "
	 "800 MW under 15000 MW at defaults. Routes as a post-solve check -- "
	 "the left-hand side is itself endogenous. An equality to "
	 "`battery_capacity + phs_capacity` was rejected: it would make an "
	 "endogenous node derived, and it disagrees with the shipped 800 (300 "
	 "battery + 200 PHS = 500). The 300 MW difference is the node "
	 "duplicating two builds it is not tied to, and this bound records it "
	 "rather than inventing a third equation to explain it.",
	 "energy_balance", None,
	 "total_capacity_mw + storage_headroom_mw", "storage_capacity_mw"),
	("thermal_storage_capacity_bound", "thermal_storage_capacity", "leq",
	 "storage_headroom_mw * thermal_storage_duration",
	 "The thermal store's energy is its share of the storage envelope "
	 "times the graph's own thermal-store duration: 0 MWh under 40000 MWh "
	 "at defaults. Routes as a post-solve check. A bound against the "
	 "headroom alone was rejected on units (MWh against MW), and one on "
	 "`battery_duration` rejected as the wrong technology's dial -- a "
	 "thermal store sized on battery hours is a scenario parameter leaking "
	 "across technologies.",
	 "energy_balance",
	 "IEA/NEA, Projected Costs of Generating Electricity (2020) -- "
	 "thermal-storage duration and cost",
	 "storage_headroom_mw", "thermal_storage_capacity"),
	("fusion_capacity_bound", "fusion_capacity", "leq", "total_capacity_mw",
	 "Fusion is generation and is bounded by the fleet's declared nameplate: "
	 "one technology cannot exceed the whole fleet. A bound against "
	 "`solar_pv_max_build` was rejected -- a fusion plant does not compete "
	 "for solar's land or build programme, and the ceiling would move with "
	 "an unrelated dial.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "fusion_capacity"),
	("hydrogen_fuel_cell_capacity_bound", "hydrogen_fuel_cell_capacity",
	 "leq", "total_capacity_mw",
	 "Fuel cells are generation and bounded by the fleet nameplate. A "
	 "bound against the storage headroom was rejected: a fuel cell is a "
	 "generator, not a store, and putting it in the storage envelope would "
	 "let it exceed the generation ceiling.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "hydrogen_fuel_cell_capacity"),
	("marine_otec_capacity_bound", "marine_otec_capacity", "leq",
	 "total_capacity_mw",
	 "OTEC is generation, bounded by the fleet nameplate. The technology "
	 "registry knows the carrier (`otec`), so the node is a build rather "
	 "than a resource. Fleet-balance membership was rejected as the "
	 "tautology it is at a 15000 MW ceiling.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "marine_otec_capacity"),
	("marine_tidal_capacity_bound", "marine_tidal_capacity", "leq",
	 "total_capacity_mw",
	 "Tidal stream is generation, bounded by the fleet nameplate. A bound "
	 "against `marine_wave_capacity` was rejected: two resources with "
	 "separate ceilings, and a shared one would make a wave scenario cap "
	 "tidal.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "marine_tidal_capacity"),
	("marine_wave_capacity_bound", "marine_wave_capacity", "leq",
	 "total_capacity_mw",
	 "Wave is generation, bounded by the fleet nameplate. Fleet-balance "
	 "membership was rejected as vacuous at a 15000 MW ceiling.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "marine_wave_capacity"),
	("tidal_range_capacity_bound", "tidal_range_capacity", "leq",
	 "total_capacity_mw",
	 "A tidal-range barrage is generation and bounded by the fleet "
	 "nameplate. Distinct from `marine_tidal_capacity`, which is tidal "
	 "*stream*: a barrage impounds an estuary and a stream array does not, "
	 "and the two ceilings are independent.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "tidal_range_capacity"),
	("small_modular_reactor_capacity_bound", "small_modular_reactor_capacity",
	 "leq", "total_capacity_mw",
	 "SMR nameplate is bounded by the fleet. A bound against "
	 "`nuclear_new_build` was rejected: SMRs are a technology that "
	 "`nuclear_new_build` *admits*, not a subset of the nuclear build, and "
	 "the two ceilings are independent dials.",
	 "energy_balance",
	 "Oree et al. (2017), RSER 69:790-803, Sec. 2.1 (GEP constraint "
	 "inventory: capacity limits)",
	 "total_capacity_mw", "small_modular_reactor_capacity"),

	# --- lead-time floor -------------------------------------------------
	("spare_parts_lead_time_bound", "spare_parts_lead_time", "leq",
	 "mean_time_between_failures",
	 "A spare part must arrive within the unit's mean time between "
	 "failures, or the expected wait for it dominates availability: 720 h "
	 "against 50000 h at defaults, so the constraint holds by a factor of "
	 "seventy and bites only on a deliberately degraded maintenance "
	 "regime. The classification pack's form `365 / maintenance_frequency` "
	 "was rejected on units -- 365 days divided by 2 events/year is "
	 "day-year/event, which the walker reads as `year / events`, and the "
	 "two sides do not share a dimension.",
	 "reliability", None,
	 "mean_time_between_failures", "spare_parts_lead_time"),

	# --- water -----------------------------------------------------------
	("transboundary_water_constraint_bound", "total_water_demand_m3", "leq",
	 "transboundary_water_constraint",
	 "The basin's allocation caps total water demand: 93.2e6 m3/year under "
	 "a 200e6 ceiling at defaults. Routes as a post-solve check because "
	 "the demand is derived. The bound overlaps the shipped "
	 "`water_availability_bound`, which compares the availability *flow* "
	 "to the same demand; the two are kept distinct because they are "
	 "different instruments -- one is a physical flow the basin provides, "
	 "the other an allocation a treaty or regulator grants -- and a "
	 "scenario can be inside the physical flow and outside the "
	 "allocation. Stating them as one would hide which failed.",
	 "water_energy", None,
	 "transboundary_water_constraint", "total_water_demand_m3"),
)


def build_batch32(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The THRESHOLD class: twenty-three bounds over the nodes the packs left.

	The class is structurally different from every batch before it. A PRODUCT
	equation *determines* a node, so the node becomes derived and loses its
	default. A BOUND determines nothing: it says the node must sit on one
	side of a quantity that already exists, and the node keeps its own range
	and default. `_a_derivation_has_exactly_one_target` enforces that -- a
	non-`eq` relation carrying `determined_variables` is refused -- so this
	batch emits `determined_variables: ()` on every row, and the parameter
	register sees no new derived node from it.

	That has a consequence the register makes visible: a THRESHOLD node
	couples by being *named* by an equation, so it leaves `uncoupled()`, but
	it does not enter `computed()`, and the scenario audit's checked/skipped
	partition does not move. The movement this batch makes is in the edge
	register and the constraint count, not the derived set.

	Twenty-two rows ship and three do not. `remedy_periods` is deferred
	pending a `max_remedy_period_days` base: its declared range is already
	[1, 365], so any ceiling at 365 restates the range and can never fail --
	a bound that cannot fail is not a bound. `hydrogen_storage_capacity` is
	already coupled by the shipped storage-capex equation and its MWh
	ceiling is deferred pending a `hydrogen_storage_duration`, because the
	graph carries no hydrogen duration and borrowing thermal storage's 8 h
	would make an unrelated dial move the bound. `solvency_capital_ratio` is
	deferred for a third reason, and it is the one worth stating: the
	pack's proposed floor is `solvency_capital_ratio >= 1.0`, a comparison
	against a literal. It is not a tautology -- the node's range is
	[0.8, 3.0], so a shipped 0.9 would violate a 1.0 floor -- but a literal
	right-hand side names no binder node, and the graph's bound shape runs
	binder -> bounded. Shipping it would put an equation in the document
	that no edge carries, which is the register's own "declared is not
	produced" defect: the node would leave `uncoupled()` by being named
	while the edge register stayed silent about what couples it. The real
	fix is a `required_solvency_capital_usd` base the ratio divides by, and
	that is a base another pack owns.

	Fourteen rows route `bound` and eight route `unbound`, and the prose says
	which: an `unbound` row has an endogenous left-hand side, so it is a
	post-solve feasibility check on the solve's answer rather than an LP
	constraint on the programme. The graph states both, because a reader
	auditing a plan wants the check either way, but the distinction is in
	the prose so nobody counts the constraint register as twenty-two
	restrictions on the optimiser.

	The edge runs binder -> bounded in every row, never a self-loop: the
	binder is the quantity that limits, the bounded node is the one limited,
	and a self-loop would say the node constrains itself and name no
	coupling. The pair is carried in the table rather than recovered from
	the symbols, because a bounded left-hand side need not be a bare symbol
	-- the storage and thermal-store rows bound against sums and products.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	known = set(graph.nodes)
	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH32_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		# A bound determines nothing. The loader refuses a non-`eq` relation
		# that names a target, and the refusal is right: a node that is
		# merely bounded still has a range of admissible values, so it is
		# not derived from anything.
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		# `bounded` is the node this row limits; it must be a node and it
		# must be named on one side of the inequality, or the edge says two
		# things are coupled that the equation does not mention.
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, (
			f"{eq_id}: bounded {bounded!r} is not named by the inequality"
		)
		# The binder is a single symbol or an expression; the *node* a
		# reader follows is the first symbol of the binding side. The
		# expression form (`total_capacity_mw + storage_headroom_mw`) has
		# no single node, so the edge's source is the expression's first
		# named node and the description says the bound is composite.
		#
		# Iterating `binder` as a string walks its characters -- the bug
		# that shipped forty-nine one-letter edges in batch 30. The guard
		# here is that the first symbol must be a node and must differ from
		# the bounded one.
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		binder_node = binder_syms[0]
		assert binder_node in known, (
			f"{eq_id}: binder {binder!r} has no node among its symbols"
		)
		assert binder_node != bounded, (
			f"{eq_id}: binder and bounded are both {bounded!r}; a self-loop "
			"names no coupling"
		)
		composite = len(binder_syms) > 1
		edges.append({
			"source": binder_node, "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}"
				+ (" (composite ceiling)" if composite else "")
				+ "; a plan can clear the physics and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	return nodes, equations, edges, rules


_BATCH33_SOURCE = "The unclassified remainder (batch 33)"

#: (name, unit, range, category, prose) -- the six left-hand-side ids the pack
#: computes and no shipped node holds. Each is a product of bases the graph
#: already carries, which is what makes it a coupling rather than a new dial.
#: A range is the product of the operands' own extremes, or the base's ceiling.
BATCH33_NEW_NODES: tuple[tuple[str, str, list[float], str, str], ...] = (
	("fuel_excise_revenue_usd_per_year", "USD/year", [0.0, 4.5e12], "Tax & Fiscal",
	 "The excise the treasury collects on fossil generation: the duty share of "
	 "the delivered price over the non-renewable volume. 164974190.45 USD/year "
	 "at defaults. A revenue no node held, though `fossil_fuel_subsidy_spend_usd_per_year` "
	 "is the same arithmetic on a different share."),
	("gis_mapped_network_km", "km", [0.0, 400000.0], "Digital",
	 "The route length held in the GIS: the mapped share of the transmission and "
	 "distribution networks. 34200 km at defaults. A count of asset records was "
	 "rejected -- the graph states route km and no record count."),
	("cross_border_losses_twh", "TWh/year", [-1000.0, 1000.0], "Transmission & Grid",
	 "Energy lost in transit on the cross-border flow. Signed because the flow "
	 "is signed: a net exporter loses energy on the way out. 0 TWh/year at "
	 "defaults, because the reference case is self-sufficient."),
	("electrolyser_variable_opex_usd_per_year", "USD/year", [0.0, 2e12], "Cost",
	 "The electrolyser fleet's variable O&M bill, with the kilotonnes converted "
	 "through the graph's 0.03333 MWh/kg. 1666500 USD/year at defaults. "
	 "`opex_variable_electrolyser` is stated per MWh of hydrogen and no node "
	 "converted it to a spend."),
	("rooftop_solar_households", "1", [0.0, 1e8], "Demand-Side",
	 "Households with rooftop PV. A count, because the adoption share alone says "
	 "nothing about how many connections the distribution network carries. "
	 "1000000 at defaults."),
	("willingness_to_pay_usd_per_year", "USD/year", [0.0, 5e12], "Affordability",
	 "The annual consumer valuation of the electricity households consume: the "
	 "quantity a cost-benefit test needs and no node held. 1.5e9 USD/year at "
	 "defaults."),
)


#: (name, unit, range, default, determinism, prose) -- placeholder retypes.
#: Each node ships as `None`, [0, 1e6], 500000.0: the catalog's shape for a row
#: with a method and no formula. A retype gives it the dimension its name and
#: its eventual equation require.
BATCH33_RETYPES: tuple[tuple[str, str, list[float], float, str, str], ...] = (
	("accelerated_depreciation", "1/year", [0.01, 0.8], 0.04, "policy",
	 "The tax code's accelerated depreciation rate: the permitted multiple of "
	 "straight-line over the asset's depreciable life. 1.0 / 25 = 0.04/year at "
	 "defaults, because the shipped multiple is 1.0 -- the accelerated schedule "
	 "and the linear one coincide until a jurisdiction sets a factor above 1."),
	("accelerated_depreciation_factor", "1", [1.0, 4.0], 1.0, "policy",
	 "The multiple of straight-line depreciation the code permits. 1.0 is the "
	 "linear schedule; 2.0 doubles the annual charge. The range is the band any "
	 "jurisdiction's code allows, not a measured distribution."),
	("buffer_pool_contribution", "1", [0.0, 1.0], 0.1, "policy",
	 "The share of issued carbon credits a registry holds in its buffer against "
	 "reversal. At 0.1 the pool absorbs a tenth of every issuance."),
	("compensation_rates", "USD/hectare", [50.0, 2.5e6], 7500.0, "policy",
	 "The compensation a project pays per hectare: the multiple of market value "
	 "the resettlement package offers applied to the land's own acquisition "
	 "rate. 1.5 x 5000 = 7500 USD/hectare at defaults."),
	("consumer_price_index_link", "1/year", [-0.05, 0.5], 0.05, "fixed",
	 "The annual indexation rate a CPI-linked tariff or contract applies. The "
	 "node's name promises an *index* and the graph carries a *rate*; the "
	 "coupling below makes it the rate, and this prose says so."),
	("depreciation_schedule_accelerated", "1/year", [0.01, 0.8], 0.04, "policy",
	 "The accelerated depreciation rate: the permitted multiple of straight-line "
	 "divided by the depreciable life. 1.0 / 25 = 0.04/year at defaults."),
	("depreciation_schedule_declining", "1/year", [0.03, 0.4], 0.08, "fixed",
	 "The declining-balance rate at 200%: twice the straight-line rate over the "
	 "asset's life, the MACRS double-declining convention. 2.0 / 25 = 0.08/year. "
	 "The 150% convention was rejected: the source describes both and states no "
	 "preference, and a second node for it is a dial nobody asked for."),
	("depreciation_schedule_linear", "1/year", [0.01, 0.2], 0.04, "fixed",
	 "The straight-line rate: the asset's cost spread evenly over its "
	 "depreciable life. 1.0 / 25 = 0.04/year. A salvage-value term was "
	 "rejected: the graph carries no salvage rate, and adding one to complete "
	 "the formula would be a base this batch does not own."),
	("gdp_per_capita_growth", "1/year", [-0.05, 0.18], 0.029411764705882353, "fixed",
	 "Growth in output per head: (g - n) / (1 + n) from the two rates the graph "
	 "carries. (0.05 - 0.02) / 1.02 = 0.0294/year against a 3% headline GDP "
	 "rate and a 2% population rate. The uncorrected difference g - n "
	 "understates the per-capita rate by the denominator at defaults."),
	("health_impact_dalys", "DALY/year", [0.0, 1e8], 57600.0, "fixed",
	 "Disability-adjusted life years lost to the fleet's emissions: the burden "
	 "the shipped health chain already computes. 57600 DALY/year at defaults."),
	("health_impact_mortality", "deaths/year", [0.0, 1e7], 4800.0, "fixed",
	 "Deaths attributable to the fleet's PM2.5 over the year: what the shipped "
	 "concentration-response chain already computes. 4800 deaths/year at "
	 "defaults."),
	("hydrogen_demand_domestic", "kt/year", [-400.0, 10000.0], 49.4, "fixed",
	 "Hydrogen consumed at home: production less what is exported, with the "
	 "export volume converted from MWh to kilotonnes through the graph's own "
	 "0.03333 MWh/kg. Signed low because exports can exceed domestic "
	 "production. 50 - 0.6 = 49.4 kt/year at defaults."),
	("hydrogen_production_demand", "MWh/year", [0.0, 1e10], 2563846.15, "fixed",
	 "The electricity hydrogen production draws, which the shipped electrolysis "
	 "identity already computes from volume, energy per kilogram and "
	 "efficiency. 2563846.15 MWh/year at defaults."),
	("ppa_indexation", "1/year", [0.0, 0.3], 0.05, "fixed",
	 "The annual escalation a power purchase agreement applies to its strike "
	 "price, which is the tariff indexation rate the graph already carries. "
	 "0.05/year at defaults."),
	("premium_share_of_asset", "1", [0.001, 0.03], 0.005, "fixed",
	 "The annual insurance premium as a fraction of the insured asset's value, "
	 "which is the loss share of cost the graph already carries. 0.005 at "
	 "defaults."),
	("value_of_lost_load", "USD/MWh", [100.0, 100000.0], 5000.0, "fixed",
	 "What a megawatt-hour of unserved energy costs the system, which is the "
	 "VoLL the graph already carries and the shipped reliability-cost identity "
	 "already prices unserved energy at. 5000 USD/MWh at defaults."),
	("willingness_to_pay", "USD/MWh", [0.0, 1000.0], 100.0, "policy",
	 "What a household will pay per megawatt-hour of consumption, 100 USD/MWh "
	 "against the 1.5 MWh a household uses."),
	("electrolyser_capacity", "MW", [0.0, 1e6], 500.0, "fixed",
	 "Installed electrolyser nameplate. 500 MW clears the 292.68 MW floor the "
	 "hydrogen programme's own average draw implies, with headroom to run above "
	 "it; a plant sized to its average has no capacity to do that."),
	("fit_capacity_cap", "MW", [0.0, 1e6], 4000.0, "policy",
	 "The feed-in-tariff programme's capacity ceiling. 4000 MW sits above the "
	 "2702.70 MW VRE build, so the ceiling holds with room and a 5000 MW "
	 "scenario breaks it -- a ceiling equal to the build is the tautology the "
	 "sibling pack rejects."),
	("renewable_penetration_limit", "1", [0.0, 1.0], 0.5, "policy",
	 "The instantaneous renewable penetration ceiling, as a share of demand. "
	 "The bound below compares an *annual* share to this instantaneous limit, "
	 "which is the weaker of the two claims; the graph carries no "
	 "instantaneous-penetration node, so it is the strongest form the tree "
	 "admits."),
)


#: (eq_id, lhs, rhs, prose, system, reference) -- products and aliases.
BATCH33_EQUATIONS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
	# --- depreciation ----------------------------------------------------
	("depreciation_schedule_linear_definition", "depreciation_schedule_linear",
	 "1.0 / depreciation_life_by_asset",
	 "The straight-line rate: one over the depreciable life. 1/25 = 0.04/year "
	 "at defaults. The form is the definition rather than a fit; a "
	 "salvage-value term would need a base the graph does not carry.",
	 "financial", "Straight-line and declining-balance depreciation; cf. Short, "
	 "Packey & Holt (1995), NREL/TP-462-5173"),
	("depreciation_schedule_declining_definition", "depreciation_schedule_declining",
	 "2.0 / depreciation_life_by_asset",
	 "The 200% declining-balance rate: twice straight-line over the life. "
	 "2/25 = 0.08/year at defaults. The 150% convention is described by the "
	 "same source and not preferred by it; the shipped form takes the MACRS "
	 "default and this prose says which.",
	 "financial", "Straight-line and declining-balance depreciation; cf. Short, "
	 "Packey & Holt (1995), NREL/TP-462-5173"),
	("depreciation_schedule_accelerated_definition", "depreciation_schedule_accelerated",
	 "accelerated_depreciation_factor / depreciation_life_by_asset",
	 "The accelerated rate: the permitted multiple of straight-line over the "
	 "life. 1.0/25 = 0.04/year at defaults, because the multiple is 1.0. The "
	 "`factor * (1/life)` respelling was rejected as a no-op: the DSL has no "
	 "precedence surprise here and the simpler form is the same number.",
	 "financial", "Straight-line and declining-balance depreciation; cf. Short, "
	 "Packey & Holt (1995), NREL/TP-462-5173"),
	("accelerated_depreciation_definition", "accelerated_depreciation",
	 "depreciation_schedule_accelerated",
	 "The tax code's accelerated rate, as the schedule it names. 0.04/year at "
	 "defaults. Deriving it from the factor and the life directly was rejected "
	 "as a second spelling of `depreciation_schedule_accelerated`: two ids for "
	 "one number is the defect this batch exists to remove.",
	 "financial", None),

	# --- carbon buffer and land ------------------------------------------
	("buffer_pool_contribution_definition", "buffer_pool_contribution",
	 "permanence_parameters",
	 "The share of issued credits the registry buffers against reversal, which "
	 "is the permanence share the graph already carries. 0.1 at defaults. A "
	 "reviewer should decide whether this is a second spelling of the buffer "
	 "`carbon_credit_reversal_allowance_definition` already computes as "
	 "`(1 - permanence_parameters)`; if it is, the node's coupling is its "
	 "deletion, not this alias.",
	 "carbon_trajectory", None),
	("compensation_rates_definition", "compensation_rates",
	 "compensation_share_of_market * land_acquisition_cost_per_hectare",
	 "The compensation a project pays per hectare: the multiple of market value "
	 "the package offers applied to the land's own acquisition rate. "
	 "1.5 x 5000 = 7500 USD/hectare at defaults. Inverting the pair -- "
	 "deriving the multiple from the rate -- was rejected: the multiple is the "
	 "policy dial and the rate is what the project pays.",
	 "cost_accounting", None),

	# --- indexation and macro --------------------------------------------
	("consumer_price_index_link_definition", "consumer_price_index_link",
	 "inflation_rate",
	 "The annual indexation a CPI-linked tariff applies, which is the inflation "
	 "rate the graph already carries. 0.05/year at defaults. The node's name "
	 "promises an index and the graph carries a rate; the alias is honest only "
	 "because this description says the link is a rate.",
	 "financial", None),
	("gdp_per_capita_growth_definition", "gdp_per_capita_growth",
	 "(gdp_growth - population_growth_rate) / (1.0 + population_growth_rate)",
	 "Growth in output per head from the two rates the graph carries: "
	 "(0.05 - 0.02) / 1.02 = 0.0294/year at defaults. The Fisher-equation form "
	 "`(1+g)/(1+n) - 1` was rejected on units -- it is dimensionless against a "
	 "`1/year` left side -- and the difference form is the same algebra with "
	 "the ones cancelled.",
	 "financial", None),

	# --- health -----------------------------------------------------------
	("health_impact_dalys_definition", "health_impact_dalys", "dalys_per_year",
	 "Disability-adjusted life years lost to the fleet's emissions, which the "
	 "shipped health chain already computes. 57600 DALY/year at defaults. A "
	 "`premature_deaths * years_of_life_lost` form was rejected: that is "
	 "`dalys_definition` verbatim, so the equation would add a second spelling "
	 "of one number.",
	 "health", None),
	("health_impact_mortality_definition", "health_impact_mortality",
	 "premature_deaths_per_year",
	 "Deaths attributable to the fleet's PM2.5, which the shipped "
	 "concentration-response chain already computes. 4800 deaths/year at "
	 "defaults. A second exposure-response form was rejected: "
	 "`premature_deaths_definition` already carries it and cites WHO AirQ+.",
	 "health", None),

	# --- hydrogen ---------------------------------------------------------
	("hydrogen_demand_domestic_definition", "hydrogen_demand_domestic",
	 "hydrogen_production_kt_per_year - hydrogen_export_volume "
	 "/ (mwh_per_hydrogen_unit * 1000000)",
	 "Hydrogen consumed at home: production less the exported volume, converted "
	 "from MWh to kilotonnes through the graph's own 0.03333 MWh/kg. "
	 "50 - 0.6 = 49.4 kt/year at defaults. A `production * (1 - export_share)` "
	 "form was rejected: no export share exists, and the conversion through "
	 "`mwh_per_hydrogen_unit` is the identity the graph already uses in the "
	 "other direction.",
	 "energy_balance", None),
	("hydrogen_production_demand_definition", "hydrogen_production_demand",
	 "electrolysis_electricity_demand_mwh_per_year",
	 "The electricity hydrogen production draws, which the shipped electrolysis "
	 "identity already computes from volume, energy per kilogram and "
	 "efficiency. 2563846.15 MWh/year at defaults. A second conversion from "
	 "kilotonnes through `mwh_per_hydrogen_unit` alone was rejected: it omits "
	 "`electrolyser_efficiency` (0.65) and would understate the demand by 35%, "
	 "duplicating a shipped identity incorrectly.",
	 "energy_balance", None),

	# --- cross-border and electrolyser opex -------------------------------
	("cross_border_losses_definition", "cross_border_losses_twh",
	 "loss_factor_cross_border * net_imports_twh",
	 "Energy lost in transit on the cross-border flow: the loss share applied "
	 "to net imports. 0.03 x 0 = 0 TWh/year at defaults, because the reference "
	 "case is self-sufficient; a 100 TWh import year loses 3 TWh. Signed "
	 "because the flow is signed. Using demand as the base was rejected: "
	 "losses fall on the traded flow, and charging them to energy that never "
	 "crossed a border is the wrong bill.",
	 "energy_balance", None),
	("electrolyser_variable_opex_definition", "electrolyser_variable_opex_usd_per_year",
	 "opex_variable_electrolyser * hydrogen_production_kt_per_year * 1000000 "
	 "* mwh_per_hydrogen_unit",
	 "The electrolyser fleet's variable O&M bill: the rate per MWh of hydrogen "
	 "over the year's production, with kilotonnes converted through the graph's "
	 "0.03333 MWh/kg. 1.0 x 50 kt x 1e6 kg/kt x 0.03333 MWh/kg = 1666500 "
	 "USD/year at defaults. Charging O&M per MWh of *electricity* was "
	 "rejected: the rate's own description states it per MWh of hydrogen, "
	 "which is the output.",
	 "financial", "IEA/NEA, Projected Costs of Generating Electricity (2020)"),

	# --- fiscal -----------------------------------------------------------
	("fuel_excise_revenue_definition", "fuel_excise_revenue_usd_per_year",
	 "excise_duty_fuel * fuel_price_usd_per_mwh * (generation_twh "
	 "- renewable_generation_twh) * 1000000",
	 "The excise the treasury collects on fossil generation: the duty share of "
	 "the delivered price over the non-renewable volume. "
	 "0.2 x 40 x 20.62 TWh x 1e6 = 164974190.45 USD/year at defaults. Charging "
	 "it on all generation was rejected -- the duty falls on fossil fuel, and "
	 "charging renewables would make the excise a generation tax. The base-year "
	 "price is the partner for an annual volume; the escalated price compounds "
	 "to the horizon and would mix horizons.",
	 "financial", None),

	# --- network and rooftop ----------------------------------------------
	("gis_mapped_network_km_definition", "gis_mapped_network_km",
	 "gis_requirements * (transmission_line_length_km + distribution_network_km)",
	 "The route length held in the GIS: the mapped share of the transmission "
	 "and distribution networks. 0.6 x (12000 + 45000) = 34200 km at defaults. "
	 "A count of asset records was rejected: the graph carries km and no "
	 "record count, and the route-km base is what the node's own description "
	 "implies.",
	 "energy_balance", None),
	("rooftop_solar_households_definition", "rooftop_solar_households",
	 "rooftop_solar_adoption * households_total",
	 "Households with rooftop PV: the adoption share over the household count. "
	 "0.1 x 10000000 = 1000000 households at defaults. A capacity in MW was "
	 "rejected -- the graph carries no kW per rooftop, and inventing one would "
	 "be a base this batch does not own. Population as the base was rejected: "
	 "`households_total` is the graph's own rooftop proxy, and population "
	 "would overstate the count nearly fourfold.",
	 "demand_supply", None),

	# --- PPA and insurance ------------------------------------------------
	("ppa_indexation_definition", "ppa_indexation", "tariff_indexation",
	 "The annual escalation a PPA applies to its strike price, which is the "
	 "tariff indexation rate the graph already carries. 0.05/year at "
	 "defaults. A second index base was rejected: `ppa_indexed_price_definition` "
	 "already reads `tariff_indexation`, so two dials would let two escalations "
	 "move the same price.",
	 "ppa_pricing", None),
	("premium_share_of_asset_definition", "premium_share_of_asset",
	 "insurance_loss_share_of_cost",
	 "The annual premium as a fraction of the insured asset's value, which is "
	 "the loss share the graph already carries. 0.005 at defaults, against the "
	 "catalog's duplicate 0.008: `insurance_premium_definition` computes "
	 "`insurance_loss_share_of_cost * capex_usd_per_kw`, so the two ids are one "
	 "premium and the alias resolves the duplicate in favour of 0.005, which "
	 "lowers the shipped premium by 37.5%.",
	 "financial", None),

	# --- valuation --------------------------------------------------------
	("value_of_lost_load_definition", "value_of_lost_load", "voll_usd_per_mwh",
	 "What a megawatt-hour of unserved energy costs the system, which is the "
	 "VoLL the graph already carries and `reliability_cost_definition` already "
	 "prices unserved energy at. 5000 USD/MWh at defaults. A separate "
	 "outage-cost curve was rejected: a second value of lost load would give "
	 "one quantity two prices.",
	 "reliability", "ENTSO-E adequacy methodology (value of lost load, "
	 "definition at the Glossary, p. 3)"),
	("willingness_to_pay_usd_per_year_definition", "willingness_to_pay_usd_per_year",
	 "willingness_to_pay * household_consumption_mwh_per_year * households_total",
	 "The annual consumer valuation of the electricity households consume: "
	 "100 USD/MWh x 1.5 MWh x 10000000 households = 1.5e9 USD/year at "
	 "defaults. Economy-wide demand as the base was rejected: the willingness "
	 "to pay here is the household's, and the product would value industrial "
	 "load at a residential rate.",
	 "affordability", "Willingness to pay as the valuation of a benefit; cf. "
	 "Short, Packey & Holt (1995), NREL/TP-462-5173"),
)


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded)
BATCH33_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...
] = (
	("electrolyser_capacity_bound", "electrolyser_capacity", "geq",
	 "electrolysis_electricity_demand_mwh_per_year / 8760",
	 "The installed electrolyser must carry the average electricity draw its "
	 "own hydrogen programme implies: 2563846.15 MWh/year over 8760 hours is "
	 "292.68 MW, and the shipped 500 MW clears it. An equality was rejected -- "
	 "a build is a decision, and deriving it would make the optimiser's "
	 "variable a computed number; it is also wrong by construction, because a "
	 "plant sized to its average has no capacity to run above it. Routes "
	 "`unbound`: the right-hand side is derived, so this is a post-solve check.",
	 "energy_balance", "IEA/NEA, Projected Costs of Generating Electricity (2020)",
	 "electrolysis_electricity_demand_mwh_per_year", "electrolyser_capacity"),
	("fit_capacity_bound", "fit_capacity_cap", "geq", "vre_capacity_mw",
	 "The feed-in-tariff programme's capacity ceiling must admit the VRE the "
	 "fleet actually builds, or the programme's own cap is violated by its own "
	 "scenario. 2702.70 MW under 4000 at defaults. A floor that *forced* build "
	 "was rejected: the node is a cap, and a floor would make the programme "
	 "compel capacity rather than admit it. A cap at the placeholder 500000 was "
	 "rejected as vacuous. Routes `bound`.",
	 "financial", "Oree et al. (2017), RSER 69:790-803",
	 "vre_capacity_mw", "fit_capacity_cap"),
	("renewable_penetration_limit_bound", "renewable_penetration_limit", "geq",
	 "vre_share",
	 "The penetration ceiling must admit the annual VRE share the fleet "
	 "achieves, or the limit is breached by the build the plan chose. 0.2703 "
	 "under 0.5 at defaults. The bound compares an *annual* share to an "
	 "*instantaneous* limit, which is the weaker of the two claims -- the graph "
	 "carries no instantaneous-penetration node. Routes `unbound`: `vre_share` "
	 "is derived.",
	 "energy_balance", "Oree et al. (2017), RSER 69:790-803",
	 "vre_share", "renewable_penetration_limit"),
	("regulatory_lag_bound", "regulatory_period_length", "geq", "regulatory_lag",
	 "The review period must be at least the lag between incurring a cost and "
	 "recovering it, or a cost incurred inside one period cannot be recovered "
	 "before the next review closes. 5 years against a 1-year lag at defaults. "
	 "A midpoint convention (`lag = period / 2`) was rejected: the lag is a "
	 "measured institutional fact, not a fraction of the review cycle. Routes "
	 "`bound`.",
	 "financial", "World Bank, Regulation of Utilities handbook (revenue caps)",
	 "regulatory_lag", "regulatory_period_length"),
	("firm_build_fleet_bound", "firm_build_fleet_mw", "geq", "firm_capacity_mw",
	 "The optimiser's total build must cover the firm part of the fleet it is "
	 "building: 10000 MW against 9000 MW at defaults. Routes `unbound` -- both "
	 "sides are endogenous or derived, so this is a post-solve audit check "
	 "rather than an LP constraint. A reviewer should prefer deleting this node "
	 "to bounding it: it has zero readers, and its description's claims -- that "
	 "it is 'the identity every build set must satisfy' and that 'the reserve "
	 "margins read the firm part of it' -- are both false, because "
	 "`fleet_build_balance` is the identity and `firm_capacity_definition` "
	 "feeds the reserve margins.",
	 "reserve_margin", "Least-cost generation expansion: Koltsaklis & Dagoumas "
	 "(2018), Applied Energy 230:563-589; Oree et al. (2017), RSER 69:790-803",
	 "firm_capacity_mw", "firm_build_fleet_mw"),
)


def build_batch33(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The unclassified remainder: twenty-one products, six new nodes, five bounds.

	This is the residue of the five classification slices -- 102 nodes no pack
	had called. Seventy-three of them defer, and most of those deferrals are
	structural rather than temporary: the thirty-five QUALITATIVE nodes are
	procedures and standards with no base to multiply, the ten SCENE-SWITCH
	nodes are run configurations the solver reads rather than quantities, and
	`demand_growth_rate` is deprecated and should be removed rather than
	coupled.

	*Six new nodes.* The pack computes six quantities no shipped node holds,
	and each is the product of bases the graph already carries: an excise
	revenue, a mapped route length, a cross-border loss, an electrolyser O&M
	bill, a rooftop count and a willingness-to-pay total. None is a base --
	each is a function of two or three nodes that already exist, which is what
	makes it a coupling rather than a new dial.

	*Seven of the products are aliases, and two of them are marked for deletion
	rather than coupling.* `buffer_pool_contribution` and
	`premium_share_of_asset` are the pack's own flagged candidates: each may be
	a second spelling of a quantity the graph already derives, in which case
	the node's coupling is its removal. This batch ships the alias because that
	removes the node from `uncoupled()` without inventing arithmetic, and the
	shipped description carries the reviewer's question rather than burying it.
	The `premium_share_of_asset` alias is also what resolves the catalog's
	duplicate premium in favour of 0.005 against the node's own 0.008, which
	lowers the shipped premium by 37.5% -- a decision recorded, not a
	discovery.

	*The retype `electrolyser_capacity`'s floor depends on.* The pack measured
	the floor against the placeholder and found it fires at 0.0 with residual
	-292.677, which is a fact about the placeholder rather than about a build.
	The retype to `MW` with a 500 MW default is what makes the bound mean
	something: 500 MW against the 292.68 MW average draw. The five bounds ship
	with `determined_variables: ()` because a bound determines nothing, and the
	node keeps its range and default.

	*Three deferrals are waiting on bases no pack proposes*, and they are named
	so the next batch does not rediscover them: `morbidity_cases_per_year`, a
	curtailment-volume node, and the four composite-index components
	(`institutional_capacity`, `financial_capacity`, `technical_capacity`,
	`infrastructure_adequacy`). The three composite indices themselves --
	`adaptive_capacity`, `resilience_score`, `energy_security_index` -- are
	BASE-NEEDED rather than PRODUCT for that reason.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH33_RETYPES:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": _BATCH33_SOURCE,
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	# The six new left-hand-side ids. Each is derived, so it carries no
	# default; the pack's own range for each is the product of the operands'
	# extremes, which is the widest a product can reach.
	for name, unit, rng, category, prose in BATCH33_NEW_NODES:
		# The guard is "the id is not a shipped node *this batch did not
		# create*". After the batch is baked the graph carries these six, and a
		# bare `not in graph.nodes` would make the emit one-shot -- a second
		# emit, which the bake reproducibility check needs, would refuse. The
		# discriminator is the source string this batch stamps: a node the
		# catalog owns does not carry it.
		existing = graph.nodes.get(name)
		assert existing is None or existing.source == _BATCH33_SOURCE, (
			f"{name} already ships and not from this batch; a new node needs "
			"an id the catalog does not own"
		)
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": "fixed", "priority": "P1",
			"source": _BATCH33_SOURCE,
			"users": ["Planners", "Regulators"],
		}

	# A node a product determines must be `derived`; the retypes above set the
	# range and unit, and this pass sets the role, because the two are separate
	# claims and only the equation establishes the second.
	determined = {row[1] for row in BATCH33_EQUATIONS}
	for name in determined:
		if name in nodes:
			nodes[name]["role"] = "derived"
			nodes[name].pop("default", None)
		else:
			shipped = graph.nodes.get(name)
			assert shipped is not None, f"{name} is neither retyped nor shipped"
			full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
			full["role"] = "derived"
			full.pop("default", None)
			nodes[name] = full

	for eq_id, lhs, rhs, prose, system, cite in BATCH33_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		known = set(nodes) | set(graph.nodes)
		assert lhs in known, f"{eq_id}: {lhs!r} has no node body"
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH33_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, (
			f"{eq_id}: bounded {bounded!r} is not named by the inequality"
		)
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		binder_node = binder_syms[0]
		assert binder_node in known, (
			f"{eq_id}: binder {binder!r} has no node among its symbols"
		)
		assert binder_node != bounded, (
			f"{eq_id}: binder and bounded are both {bounded!r}; a self-loop "
			"names no coupling"
		)
		edges.append({
			"source": binder_node, "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a plan can clear the "
				"physics and fail this."
			),
			"reference": cite, "priority": "P2",
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


#: (name, unit, range, default, determinism, prose) -- the sixteen nodes the
#: contract-market pack retypes. Every one shipped with `unit: None`, the
#: placeholder range [0, 1e6] and the midpoint default 500000.0, which is the
#: catalog's "unknown" pattern rather than a quantity: a risk of 500,000, an
#: auction frequency of 500,000 per year, a gate closure eleven years long.
#: A node that is the lhs of an equation below also loses its default, because
#: a determined parameter carries none.
BATCH36_RETYPES: tuple[tuple[str, str | None, list[float] | None, float | None, str, str], ...] = (
	("security_package", "USD", [0.0, 1.1e13], None, "policy",
	 "The capital a sponsor and its parent put behind the project: the "
	 "performance bond held against non-completion plus the parent's guarantee "
	 "of the debt tranche. 600,000,000 USD at defaults, all of it bond -- the "
	 "guarantee is zero because `parent_company_guarantee` is."),
	("counterparty_risk", "1", [0.0, 1.0], None, "policy",
	 "The share of settled value exposed to a counterparty's failure to settle, "
	 "which is what `settlement_risk` is defined as: 0.01 at defaults. The two "
	 "ids are one object under two catalog names."),
	("cost_pass_through_mechanism", "1", [0.0, 1.0], None, "policy",
	 "The share of the recovery tariff carried automatically at the wholesale "
	 "level -- fuel, carbon and losses -- rather than deferred to a review. 0.8 "
	 "at defaults. This reading is contested: `unclassified.md` calls the node "
	 "the *rule set* rather than the share, and a reviewer who agrees should "
	 "retype it categorical and leave it uncoupled."),
	("tax_incentives", "USD/year", [-3e12, 3e12], None, "policy",
	 "The tax the treasury forgoes on a concession: the untaxed fraction of the "
	 "term, at the corporate rate, on the cash the fleet generates after the "
	 "tariff. A positive number is revenue forgone; the range admits negative "
	 "because `cfads_usd_per_kw_year` is signed. 128,772,000 USD/year at "
	 "defaults -- 20% of the term untaxed, 30% rate, 214.62 USD/kW/year over "
	 "10,000 MW."),
	("ppa_termination_payments", "USD", [0.0, 1.5e14], None, "policy",
	 "The make-whole an offtaker owes if it terminates the PPA: the revenue the "
	 "plant would have earned, discounted over the remaining term. The annuity "
	 "factor and not the raw sum, because a payment today for revenue that would "
	 "have arrived over twenty years is worth less than the sum. 31,829,702,743 "
	 "USD at defaults. Undefined at `discount_rate = 0`, which the declared "
	 "range admits -- the shipped `crf_definition` and `llcr_definition` divide "
	 "by rates with the same lower bound, so this adds no new failure class."),
	("gate_closure", "hours", [0.05, 24.0], 1.0, "fixed",
	 "How long before delivery the market closes. 1.0 hour is the European "
	 "intraday convention. The floor of 0.05 h is `settlement_period`'s own "
	 "floor, so the bound below cannot be vacuous by construction of the range."),
	("auction_frequency", "1/year", [0.5, 365.0], 12.0, "fixed",
	 "Rounds per calendar year the allowance auction runs. 12 is monthly, the "
	 "calendar the EU ETS uses for most of its volume; the range admits "
	 "twice-yearly to daily."),
	("regulatory_asset_valuation_method", "1", None, None, "policy",
	 "How the regulatory asset base is valued: historical cost, indexed "
	 "historical, or current cost. Retyped categorical below; the shipped 0.0 "
	 "reads as the first documented category, which is the graph's own "
	 "convention (`market_model`, `market_structure`)."),
	("virtual_bidding", "1", None, 0.0, "fixed",
	 "Whether virtual bids are admitted in the day-ahead market. Retyped bool."),
	("financial_transmission_rights", "1", None, 0.0, "fixed",
	 "Whether financial transmission rights are traded. Retyped bool."),
	("strategic_bidding", "1", None, 0.0, "fixed",
	 "Whether generators may bid strategically rather than at cost. Retyped "
	 "bool."),
)


#: (name, categories, default, prose) -- the five nodes that shipped as floats
#: and are levels, not magnitudes. `regulatory_asset_valuation_method` is here
#: as well as in the retype table because it needs both a type and a range
#: removed; the two tables are read in order and the categorical one wins.
BATCH36_CATEGORICALS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
	("auction_mechanism", ("sealed_bid", "descending_clock", "hybrid"), "sealed_bid",
	 "How allowances are allocated in a round. `sealed_bid` is the EU ETS "
	 "convention: bids are submitted without a view of the clearing price."),
	("pricing_mechanism", ("uniform_price", "pay_as_bid", "nodal"), "uniform_price",
	 "How the cleared price is set. `uniform_price` pays every accepted bid the "
	 "clearing price, which is what a pay-as-cleared market does."),
	("unbundling_status", ("integrated", "legal_unbundling", "ownership_unbundling",
	                       "retail_separation"), "integrated",
	 "How far the utility's generation, network and retail arms are separated. "
	 "`integrated` is the shipped baseline; the three others are the degrees "
	 "the EU's third package distinguishes."),
	("tariff_structure", ("single_part", "two_part", "time_of_use", "increasing_block"),
	 "two_part",
	 "The shape of the retail tariff. `two_part` -- a fixed charge plus a "
	 "volumetric rate -- is the ordinary residential structure."),
	("re_target_carrier", ("renewable", "solar", "wind", "hydro", "biomass", "geothermal"),
	 "renewable",
	 "Which carrier a renewable target is written against. `renewable` is the "
	 "aggregate the directive states; the five named carriers are the "
	 "technology-specific targets a member state may set instead."),
	("regulatory_asset_valuation_method", ("historical_cost", "indexed_historical",
	                                       "current_cost"), "historical_cost",
	 "How the regulatory asset base is valued. `historical_cost` is the shipped "
	 "0.0 read as the level it was meant to be."),
)


#: (eq_id, lhs, rhs, prose, system, reference) -- products and aliases.
BATCH36_EQUATIONS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
	("security_package_definition", "security_package",
	 "performance_bond_usd + parent_company_guarantee_usd",
	 "The capital a sponsor and its parent put behind the project: the "
	 "performance bond held against non-completion plus the parent's guarantee "
	 "of the debt tranche. A stock, not a flow, because both instruments are "
	 "released rather than spent. 600,000,000 USD at defaults, all of it bond. "
	 "Adding `collateral_posted_usd_per_year` was rejected on units: that node "
	 "is USD million/year and the two terms are USD.",
	 "financial", None),
	("counterparty_risk_alias", "counterparty_risk", "settlement_risk",
	 "The share of settled value exposed to a counterparty's failure to settle, "
	 "which is what `settlement_risk` is defined as -- one object under two "
	 "catalog names, resolved by equality. 0.01 at defaults.",
	 "financial", "The catalog's own duplicate rows, resolved"),
	("cost_pass_through_alias", "cost_pass_through_mechanism",
	 "wholesale_cost_pass_through",
	 "The share of the recovery tariff carried automatically at the wholesale "
	 "level. 0.8 at defaults. `unclassified.md` calls the node the rule set "
	 "rather than the share; this alias is the reading the graph's own operands "
	 "support, and the description says the question is open.",
	 "financial", "The catalog's own duplicate rows, resolved"),
	("tax_incentives_definition", "tax_incentives",
	 "(1.0 - taxed_fraction_of_concession) * corporate_income_tax_rate * "
	 "cfads_usd_per_kw_year * total_capacity_mw * 1000",
	 "The tax the treasury forgoes on a concession: the untaxed fraction of the "
	 "term, at the corporate rate, on the cash the fleet generates after the "
	 "tariff. 128,772,000 USD/year at defaults. A two-term form adding the "
	 "investment allowance was rejected on units: the holiday leg is USD/year "
	 "and the allowance leg is USD.",
	 "financial", "Rate-based levy and allowance definitions (standard fiscal accounting)"),
	("ppa_termination_payment_definition", "ppa_termination_payments",
	 "ppa_annual_revenue_usd_per_kw_year * total_capacity_mw * 1000 * "
	 "(1 - (1 + discount_rate) ** (-ppa_duration)) / discount_rate",
	 "The make-whole an offtaker owes on termination: the revenue the plant "
	 "would have earned, discounted over the remaining term. 31,829,702,743 USD "
	 "at defaults -- 385.79 USD/kW/year over 10,000 MW, annuitised at 10.46% "
	 "over 20 years. The undiscounted sum was rejected: it pays twenty years of "
	 "revenue as a lump sum today and overstates the liability 2.4x.",
	 "financial", "Standard annuity formula"),
	("auction_volume_per_round_definition", "auction_volume_per_round",
	 "auction_volume / auction_frequency",
	 "The allowances one auction round offers: the year's volume spread over the "
	 "rounds the calendar holds. 25 / 12 = 2.0833 MtCO2 at defaults. The "
	 "per-round size is what an auction calendar is designed around, and the "
	 "graph carried the annual volume and the round frequency with no node "
	 "joining them.",
	 "carbon_trajectory", None),
)


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded)
BATCH36_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...
] = (
	("gate_closure_bound", "gate_closure", "geq", "settlement_period",
	 "The market must close no later than one settlement period before "
	 "delivery, or a trade can settle inside the interval it was cleared for. "
	 "1.0 hour against the 0.5-hour settlement period at defaults. An equality "
	 "was rejected: gate closure is a policy dial, and an equality would make "
	 "every operator run the same gate. Routes `bound` -- both sides are "
	 "declared, so this reaches the optimiser.",
	 "demand_supply", None, "settlement_period", "gate_closure"),
)


#: (name, unit, range, category, prose) -- the one node this batch declares.
BATCH36_NEW_NODES: tuple[tuple[str, str, list[float], str, str], ...] = (
	("auction_volume_per_round", "MtCO2", [0.0, 20000.0], "Carbon Market",
	 "The allowances one auction round offers: the year's volume divided by the "
	 "rounds the calendar holds. 25 / 12 = 2.0833 MtCO2 at defaults. The range's "
	 "ceiling is `auction_volume`'s (10,000 MtCO2/year) over "
	 "`auction_frequency`'s floor (0.5/year), which is the widest a quotient of "
	 "the two can reach."),
)

_BATCH36_SOURCE = "The contract and market pack (batch 36)"
_BATCH37_SOURCE = "The macro and climate pack (batch 37)"


#: (eq_id, lhs, rhs, prose, system, reference) -- corrections to shipped
#: equations. A correction names an equation the graph already carries and
#: replaces its body; the bake's stale-edge rule disposes the edges the old
#: arithmetic held.
#: The equations batch 34 re-emits. Not a second copy of their bodies: the
#: authoring table owns each body and this batch names the ids, so a correction
#: cannot drift from the equation it corrects. What the batch does is put the
#: corrected body in front of the bake, whose merge replaces the shipped one.
BATCH34_CORRECTIONS: tuple[str, ...] = (
	"carbon_credit_reversal_allowance_definition",
)


def build_batch34(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The review corrections batch 33 deferred, and the packs that follow them.

	*The sign error first, because it is a defect and not a coupling.* Batch 33
	shipped `buffer_pool_contribution = permanence_parameters` as an alias and
	flagged the question it raised rather than answering it: if the buffer
	contribution is the *complement* of the permanence share, the alias is wrong
	by construction. Reading the two shipped nodes answers it against the
	alias, and against the equation the alias was supposed to be spelling.

	`permanence_parameters` describes itself as "the share of issued volume
	held back against non-permanence", so its complement is the volume *not*
	held back -- the opposite of an allowance. `carbon_credit_reversal_allowance_definition`
	multiplied that complement and called the product the buffer a registry
	retains. Both cannot hold, and the algebra says which is wrong without
	leaving the graph: the shipped form reports 40.5 of 45 MtCO2/year held
	back, a 90% allowance against a 10% share. A buffer that holds back nine
	tenths of every issuance is not a permanence mechanism; it is the share
	inverted. This batch corrects the equation to
	`permanence_parameters * carbon_credit_volumes`, taking the allowance from
	40.5 to 4.5 MtCO2/year and making `buffer_pool_contribution` agree with the
	volume it names.

	The argument stops there deliberately. Registry practice -- the buffer
	rates programmes actually withhold -- would corroborate the 10%, and no
	copy of the standards that state it is archived in `sources/`, so the
	correction rests on the graph's own two descriptions disagreeing rather
	than on an external figure the repository cannot produce.

	*Why this is a correction and not a re-bake of batch 24.* The bake merges
	one equation body over the shipped one, so re-emitting batch 24 would do
	the same thing -- but batch 24 predates twenty-odd retypes, and a re-bake
	couples this fix to whether every one of them is still current. It is not:
	the measurement says batch 24's parameters, equations and edges drift from
	`config/prg.yaml` in zero fields today, which makes the two routes
	equivalent right now and the narrower one correct by construction. A batch
	that owns one equation cannot revert a node it never names.

	*The `premium_share_of_asset` resolution stands.* Batch 33 asked whether
	resolving the catalog's duplicate premium in favour of 0.005 was intended.
	It is: `insurance_premium_definition` computes
	`insurance_loss_share_of_cost * capex_usd_per_kw`, so 0.008 was a second
	dial on a premium already priced, and the alias removes it. Nothing to
	correct.

	*`firm_build_fleet_mw` is kept, and the pack's deletion recommendation is
	recorded rather than taken.* The node is `endogenous` and `firm_build_fleet_bound`
	names it, so it is coupled and not floating; deleting it would remove a
	bound that holds at defaults (10,000 MW against 9,000 MW) and leave the
	fleet build with no ceiling. A deletion is the right call for an alias and
	the wrong one for a decision variable.
	"""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	from alea.prg.dsl import parse_side

	# The authored body, looked up rather than restated. `BATCH24_EQUATIONS` is
	# the table that owns this equation; copying its body here would make two
	# sources for one row, and the one a later reader edits would be whichever
	# they happened to open.
	authored = {row[0]: row for row in BATCH24_EQUATIONS}

	for eq_id in BATCH34_CORRECTIONS:
		shipped = graph.equations.get(eq_id)
		assert shipped is not None, (
			f"{eq_id} is not a shipped equation; a correction names one the "
			"graph already carries"
		)
		assert eq_id in authored, (
			f"{eq_id} is corrected by this batch but authored nowhere this "
			"batch can read; the correction needs an authoring table"
		)
		_, _name, lhs, rhs, prose, system, linearity, _unit, _rng, cite = authored[eq_id]
		rhs_params = sorted(parse_side(rhs).symbols)
		equations[eq_id] = {
			"id": eq_id,
			"name": _name,
			"description": prose,
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
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})

	return nodes, equations, edges, rules


def build_batch35(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""Batch 35: every stored rendering that describes a different equation.

	This batch adds no node and couples nothing. It repairs a defect class the
	batches created and the gate caught: an amendment copies the shipped
	equation's fields, rewrites `lhs` or `rhs`, and leaves `latex` alone -- so
	the shipped rendering survives a body it no longer describes.
	`check_latex` compares operand *sets*, so each of these was detectable the
	moment it shipped and none of them was read.

	Five equations are wrong in four distinct ways, and the ways matter
	because each is a different thing the rendering lost:

	* `coal_eaf_definition` typesets `forced_outage_rate` where the body holds
	  `forced_outage_rate_coal`. Batch 31 amended the body to read the coal
	  fleet's own rate -- 10%, against the generic 24/50024 = 0.048% that
	  `availability_definition` derives -- and the rendering kept the old
	  symbol. A reader of the report would have taken a 0.05% forced-outage
	  rate for a coal fleet, which is a factor of 200 away from the fleet's.
	* `lcoe_wind_definition` typesets the generic `opex_fixed_wind` (40) where
	  the body holds `opex_fixed_wind_onshore` (30). The same batch made the
	  same substitution and the rendering kept the generic name.
	* `transmission_investment_definition` omits `transmission_cost_multiplier`
	  entirely. The batch inserted the multiplier into the body precisely
	  because it was "a dial nothing multiplied"; the rendering then showed a
	  transmission cost that does not carry it, so a reader could not see the
	  dial at work.
	* `fleet_build_balance` typesets twelve technologies where the body sums
	  eighteen. Batch 30 added the six conversion-plant capacities -- biogas,
	  landfill gas, gasification, pyrolysis, waste-to-energy and
	  salinity-gradient -- so a scenario building any of them is counted
	  against the ceiling. The rendering showed a constraint that does not
	  mention them, which reads as a constraint they escape.
	* `water_availability_constraint` had no rendering at all, which is why
	  `check_latex` never reported it: the check skips a null `latex` rather
	  than flagging it. A rewrite with no rendering is invisible to the gate,
	  and that blind spot is recorded here rather than fixed, because deciding
	  whether every equation *should* declare a rendering is a policy question
	  about the field and not a repair.

	The repair is a re-typeset from each equation's own body, not a hand-edit
	of each string. A hand-edited rendering is a third copy of the arithmetic
	-- the body, the rendering, and now the patch -- and the copy that goes
	stale is whichever one the next batch does not open. `generated_latex` is
	already the function that renders a body, so the batch calls it rather
	than reimplementing it, and the five strings become what the body says by
	construction rather than by care.

	The rendering is emitted only where it *disagrees*. An equation whose
	declared rendering differs from the generated one only in notation is
	passing `check_latex` on purpose -- `\\log_2` for a folded `0.693147`, an
	author's `\\mathrm{CF}` for `capacity_factor` -- and overwriting those
	would replace deliberate notation with the renderer's default. So the
	selection predicate is `check_latex`, not "every equation", which is what
	makes this a repair rather than a rewrite of the library's typography.
	"""
	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	from alea.prg.service import check_latex, generated_latex

	findings = check_latex(graph)
	assert findings, (
		"batch 35 repairs renderings that disagree with their arithmetic, and "
		"check_latex reports none; either the graph is already repaired or the "
		"gate is not reading it, and a batch that emitted nothing would look "
		"like a clean pass either way"
	)

	for finding in findings:
		eq_id = finding.equation_id
		shipped = graph.equations.get(eq_id)
		assert shipped is not None, f"{eq_id} is reported but not shipped"
		body = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		repaired = generated_latex(shipped)
		assert repaired != body.get("latex"), (
			f"{eq_id} is reported by check_latex but the renderer reproduces "
			"its stored rendering; the finding is about notation the renderer "
			"cannot express, not about a stale operand set"
		)
		body["latex"] = repaired
		equations[eq_id] = body
		# No edges are emitted. The arithmetic did not change, so the
		# equation's symbol set and every edge that reaches it are already
		# right -- re-emitting them would be a second copy of edges the bake
		# already holds, and the loader refuses a duplicate.

	return nodes, equations, edges, rules


#: (name, unit, range, default, role, determinism, prose) -- the twenty-one
#: nodes the macro-climate pack couples. Every one shipped with `unit: None`,
#: the placeholder range [0, 1e6] and the midpoint default 500000.0, except
#: `political_stability`, which was already a [0, 1] dial.
#:
#: The five with `role: derived` become an equation's lhs below and carry no
#: default; the sixteen with `role: free` are operands and keep one. A
#: categorical would need `categories`, and this slice has none -- its
#: SCENE-SWITCH rows are deferred by the pack precisely because the graph has
#: no level-typed node to hold a method flag.
BATCH37_RETYPES: tuple[
	tuple[str, str | None, list[float] | None, float | None, str, str, str], ...] = (
	("geopolitical_risk_index", "1", [0.0, 1.0], None, "derived", "fixed",
	 "A composite of the six governance and security dials: political "
	 "stability, cross-border tension, maritime security, cyber threat, "
	 "terrorism and civil unrest. `political_stability` and "
	 "`maritime_security` are scored higher-is-better and enter inverted; the "
	 "other four are already risk-scaled. Unweighted because the graph "
	 "declares no weights, and a reader can check a mean against its six "
	 "components -- a weighted composite would need a severity vector the "
	 "graph does not carry. `energy_security_index` is deliberately not a "
	 "member: it is its own composite with its own three components, and the "
	 "catalog does not nest it."),
	("exposure_index", "1", [0.0, 1.0], None, "derived", "fixed",
	 "The mean of the eight declared climate-hazard intensities: flood, "
	 "coastal erosion, drought, heat stress, wildfire, landslide, storm surge "
	 "and glacial lake outburst. Every hazard is a [0, 1] intensity, so the "
	 "mean is the expected hazard loading and needs no normalising constant. "
	 "A maximum over the eight was rejected: it is the more faithful reading "
	 "of 'exposure', and `max` has no derivative rule, so `gradients()` raises "
	 "on any equation using it. A product of complements was rejected because "
	 "a symbolic exponent leaves the unit walker undecidable."),
	("land_availability", "hectare", [0.0, 500000.0], None, "derived", "physical",
	 "Alias onto `available_land_hectares`, which the graph derives as "
	 "`land_availability_fraction * land_area_hectares`. The catalog declares "
	 "both names; keeping this one a free placeholder would let a scenario "
	 "set a land availability the project's own take contradicts. 2,500 ha at "
	 "defaults."),
	("land_aggregation", "parcels", [0.0, 2500000.0], None, "derived", "fixed",
	 "Alias onto `parcels_to_assemble`, the transaction count the assembly "
	 "programme has to clear: `land_aggregation_fragmentation * "
	 "land_area_hectares / 100`, 1,000 parcels at defaults. Same "
	 "duplicate-row argument as `land_availability`."),
	("snapshot_weightings", "hours", [0.0, 876000.0], None, "derived", "fixed",
	 "The hours each representative snapshot stands for: the horizon's hours "
	 "divided by the snapshot count. 25 x 8,760 / 1,200 = 182.5 h at "
	 "defaults, and 182.5 x 1,200 = 219,000 h = 25 years, so the weights sum "
	 "to the horizon by construction. The upper bound is `time_horizon`'s own "
	 "100 years of hours, divided by the smallest legal snapshot count of 1. "
	 "A pure share `1 / representative_snapshots` was rejected on units: "
	 "dimensionless, so the walker cannot reconcile it with an hours-"
	 "denominated weight and the horizon drops out of the accounting."),
	("political_stability", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Political stability and absence of violence, scored higher-is-better. "
	 "It is one of the six dials `geopolitical_risk_index` reads, and it "
	 "enters that composite inverted. Already a [0, 1] dial; retyped here "
	 "only to record the polarity, which `docs/params.md` does not state."),
	("cross_border_tension", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Diplomatic tension with neighbouring states, risk-scaled: higher is "
	 "more tension. Not inverted in the composite."),
	("maritime_security", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Maritime and sea-lane security. **Stated assumption: scored "
	 "higher-is-safer**, so the composite inverts it. `docs/params.md` 22.18 "
	 "gives no polarity, and no archived source resolves it -- the inversion "
	 "is this batch's reading of the name, not a sourced fact. A reviewer who "
	 "reads it as higher-is-riskier should drop the `1 -` from "
	 "`geopolitical_risk_index_definition`."),
	("cyber_threat_level", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Cyber threat to grid and market operations, risk-scaled: higher is "
	 "worse. Not inverted."),
	("terrorism_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Terrorism risk to energy infrastructure, risk-scaled: higher is worse. "
	 "Not inverted."),
	("civil_unrest_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Civil unrest risk, risk-scaled: higher is worse. Not inverted."),
	("flood_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Flood hazard intensity at the site: 0 absent, 1 at the top of the "
	 "scale. One of the eight hazards `exposure_index` averages."),
	("coastal_erosion", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Coastal erosion hazard intensity. One of the eight `exposure_index` "
	 "hazards."),
	("drought_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Drought hazard intensity. One of the eight `exposure_index` hazards."),
	("heat_stress", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Heat stress hazard intensity. One of the eight `exposure_index` "
	 "hazards."),
	("wildfire_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Wildfire hazard intensity. One of the eight `exposure_index` hazards."),
	("landslide_risk", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Landslide hazard intensity. One of the eight `exposure_index` "
	 "hazards."),
	("storm_surge", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Storm surge hazard intensity. One of the eight `exposure_index` "
	 "hazards."),
	("glacial_lake_outburst", "1", [0.0, 1.0], 0.5, "free", "fixed",
	 "Glacial lake outburst flood hazard intensity. One of the eight "
	 "`exposure_index` hazards."),
	("temperature_increase", "degC", [0.0, 6.0], 1.2, "free", "fixed",
	 "The warming the scenario assumes, in degrees Celsius above the "
	 "pre-industrial baseline. The default of 1.2 places a default run near "
	 "the present level rather than at a century-end projection. The 6 degC "
	 "ceiling is headroom over AR6's end-century SSP5-8.5 range of roughly "
	 "3.3 to 5.7; the zero floor refuses a negative warming, which no "
	 "scenario produces."),
	("temperature_target", "degC", [1.0, 3.0], 1.5, "free", "policy",
	 "The policy warming ceiling the scenario is tested against. The range "
	 "must contain 1.5 and 2.0 -- the Paris agreement's two anchors -- and 3 "
	 "admits a deliberately weak target. A placeholder range would admit a "
	 "target no scenario can violate, so `temperature_target_bound` would "
	 "never bind."),
	("rolling_horizon_window", "years", [1.0, 100.0], 5.0, "free", "fixed",
	 "The look-ahead in the rolling-horizon solve, in years. At least one "
	 "year, because a zero window is not a solve; 100 matches "
	 "`time_horizon`'s own bound, so the window can never be declared "
	 "outside the horizon it looks across."),
	("representative_days", "days", [1.0, 100.0], 50.0, "exogenous", "fixed",
	 "The number of representative days the temporal aggregation keeps. The "
	 "lower bound is the prerequisite for `snapshot_weightings`: the "
	 "snapshot count is `representative_days * tsam_segments`, and a zero "
	 "there reaches the weight equation's denominator. Retyped from [0, 100] "
	 "to [1, 100] so the pole is a clean range refusal at the door rather "
	 "than a `ZeroDivisionError` from inside `propagate`."),
)


#: (eq_id, lhs, rhs, prose, system, reference) -- five equalities.
#:
#: Two of the five carry `reference: None`, and the pack says why rather than
#: inventing one: they are unweighted means of declared dials, no archived work
#: states this aggregation, and the component provenance the catalog gives
#: (World Bank WGI, ND-GAIN) is not in `sources/archive/`.
BATCH37_EQUATIONS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
	("geopolitical_risk_index_definition", "geopolitical_risk_index",
	 "(1 - political_stability + cross_border_tension + 1 - maritime_security"
	 " + cyber_threat_level + terrorism_risk + civil_unrest_risk) / 6",
	 "The governance and security composite: an unweighted mean of six "
	 "declared [0, 1] dials, with the two higher-is-better dials inverted. "
	 "0.5 at defaults, because every dial is at its own midpoint. The "
	 "inversion of `political_stability` follows its own definition (stability "
	 "is good); the inversion of `maritime_security` is a stated assumption, "
	 "recorded on that node. `composite_governance_index` is not used here: "
	 "it is itself a five-dial mean, and inverting it is not the same as "
	 "inverting `political_stability`, which the catalog names as the "
	 "political parent.",
	 "demand_supply", None),
	("exposure_index_definition", "exposure_index",
	 "(flood_risk + coastal_erosion + drought_risk + heat_stress"
	 " + wildfire_risk + landslide_risk + storm_surge"
	 " + glacial_lake_outburst) / 8",
	 "The climate-hazard composite: the unweighted mean of eight declared "
	 "[0, 1] hazard intensities. 0.5 at defaults. Every hazard is already "
	 "risk-scaled in the same direction, so no term is inverted. The mean is "
	 "the expected hazard loading rather than a union probability; a union "
	 "form would need a product of complements, whose symbolic exponent the "
	 "unit walker cannot decide.",
	 "demand_supply", None),
	("land_availability_alias", "land_availability",
	 "available_land_hectares",
	 "The catalog's duplicate rows resolved by equality: `land_availability` "
	 "is `available_land_hectares`, the hectares the land block actually "
	 "takes. The range is the driver's own, so the alias cannot narrow the "
	 "image and a scenario cannot set a land availability the project's own "
	 "take contradicts.",
	 "financial", "The catalog's own duplicate rows, resolved"),
	("land_aggregation_alias", "land_aggregation",
	 "parcels_to_assemble",
	 "The second duplicate-row resolution: `land_aggregation` is "
	 "`parcels_to_assemble`, the parcel count the assembly programme clears. "
	 "1,000 at defaults.",
	 "financial", "The catalog's own duplicate rows, resolved"),
	("snapshot_weightings_definition", "snapshot_weightings",
	 "time_horizon * 8760 / representative_snapshots",
	 "The hours one representative snapshot stands for: the horizon's hours "
	 "over the snapshot count. 182.5 h at defaults, and the weights sum to "
	 "the horizon by construction -- 182.5 x 1,200 = 219,000 h = 25 years. "
	 "This is the quantity a temporal aggregation must preserve, and it is "
	 "what makes a reduced-snapshot solve comparable to a full hourly one.",
	 "energy_balance", "Tejada-Arango (2023), arXiv:2307.16842"),
)


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded) --
#: two inequalities. Both operands are declared, so both reach the optimiser
#: as linopy constraints rather than waiting for a post-solve check.
BATCH37_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...] = (
	("temperature_target_bound", "temperature_increase", "leq",
	 "temperature_target",
	 "The scenario's assumed warming must not exceed the policy ceiling it is "
	 "tested against. 1.2 against 1.5 at defaults. A scenario that warms past "
	 "its own target is incoherent rather than infeasible, which is why this "
	 "is a bound on the declared inputs and not on the dispatch.",
	 "carbon_trajectory", None, "temperature_target", "temperature_increase"),
	("rolling_horizon_window_bound", "rolling_horizon_window", "leq",
	 "time_horizon",
	 "The rolling-horizon look-ahead must not exceed the modelled horizon: a "
	 "window longer than the data reads beyond it. 5 against 25 at defaults.",
	 "demand_supply", None, "time_horizon", "rolling_horizon_window"),
)


#: (name, unit, range, default, role, determinism, prose) -- prerequisites the
#: batch retypes because its own equations are unsafe without them.
#:
#: `representative_snapshots` is derived (`representative_days * "
#: "tsam_segments`), so its zero was not reachable from its own range -- it
#: was reachable from `representative_days`. Retyping the driver is what turns
#: the pole into a refusal; retyping this one alone does not, which the pack
#: measured.
BATCH37_PREREQUISITES: tuple[
	tuple[str, str | None, list[float] | None, float | None, str, str, str], ...] = (
	("representative_snapshots", "1", [1.0, 9600.0], None, "derived", "fixed",
	 "The number of representative snapshots a reduced temporal "
	 "representation keeps: `representative_days * tsam_segments`, 1,200 at "
	 "defaults. The lower bound is one, not zero, because this node is the "
	 "denominator of `snapshot_weightings_definition` and a snapshot count of "
	 "zero has no weight to divide by. Retyped from [0, 9600]."),
	("time_horizon", "years", [1.0, 100.0], 25.0, "exogenous", "fixed",
	 "The modelled horizon in years. Retyped from [0, 100] to [1, 100]: it is "
	 "the numerator of `snapshot_weightings_definition` and the binder of "
	 "`rolling_horizon_window_bound`, and a zero horizon admits a zero window, "
	 "which makes that bound hold for every value of the quantity it is "
	 "supposed to constrain."),
)


#: (rule_id, condition, severity, message, suggestion, prose) -- the one
#: cross-validation rule batch 37 re-scopes.
#:
#: `index_above_unity` fires when a [0, 1] composite sits at the top of its
#: range. Its message is a claim about a value a *caller set* -- "confirm the
#: value is on the scale the equations that consume it assume" -- and after
#: this batch two of its eleven members are derived, so the premise no longer
#: holds for them. `exposure_index` and `geopolitical_risk_index` are now
#: computed from their own operands, and a computed index cannot be on the
#: wrong scale: the equation that produces it fixes the scale.
#:
#: The alternative was to exempt derived composites inside the validator, which
#: would make the rule's text describe something the code no longer checks.
#: Re-scoping the condition keeps the rule and its message in agreement, and it
#: narrows rather than widens: the nine settable members still fire.
#:
#: This is a live interaction, not a hypothetical. All eight hazard dials at
#: 0.99 are each inside their own [0, 1] range, derive `exposure_index` to
#: 0.99, and blocked the scenario before this change -- measured.
BATCH37_RULES: tuple[tuple[str, str, str, str, str, str], ...] = (
	("index_above_unity",
	 "digital_divide_metrics > 0.99 or energy_security_index > 0.99 or "
	 "rule_of_law_index > 0.99 or corruption_perception > 0.99 or "
	 "political_stability > 0.99 or regulatory_predictability > 0.99 or "
	 "contract_enforceability > 0.99 or adaptive_capacity > 0.99 or "
	 "vulnerability_index > 0.99",
	 "error",
	 "A composite index with a [0, 1] construction has been set at the top of "
	 "its range. Confirm the value is on the scale the equations that consume "
	 "it assume.",
	 "Rescale the index to its documented range",
	 "Re-scoped by the macro and climate pack: `geopolitical_risk_index` and "
	 "`exposure_index` are derived as of batch 37, so neither can be 'set' and "
	 "the message does not describe them. The nine remaining members are all "
	 "free and settable, which is what the rule is for."),
)


#: (name, unit, range, default, role, determinism, prose) -- ten retypes from
#: the operational-supply pack. Every one shipped as `unit: None`, range
#: [0, 1e6] and default 500,000, which is a placeholder, not a value: a ramp
#: rate of 500,000 per hour is a unit that ramps its whole rating half a
#: million times an hour.
BATCH38_RETYPES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	("ramp_rate_coal", "1/hour", [0.0, 0.1], 0.02, "free", "physical",
	 "The fraction of rated output a coal unit can move in one hour. 0.02/h "
	 "is 2%/h -- a large coal unit's upward limit -- and 0.1/h is the top of "
	 "the once-through band. A ramp limit is a rate against capacity, which "
	 "is why this is a share per hour rather than MW/hour: the per-unit rate "
	 "is what a TSO collects, and converting here would bake one fleet's "
	 "capacity into a rate reused across capacities."),
	("ramp_rate_gas", "1/hour", [0.0, 0.4], 0.1, "free", "physical",
	 "As coal, with the wider band a gas unit's controls allow. A CCGT ramps "
	 "an order of magnitude faster than a coal unit: 10%/h at the default, "
	 "40%/h the fast-start ceiling."),
	("min_stable_level_coal", "1", [0.0, 1.0], 0.4, "free", "physical",
	 "The share of rated capacity below which a coal unit cannot run stably. "
	 "ENTSO-E defines the parameter as a percentage of the unit's nominal "
	 "capacity and states the simulation does not allow the unit to run "
	 "under this limit; 40% is the conventional coal floor."),
	("min_stable_level_gas", "1", [0.0, 1.0], 0.3, "free", "physical",
	 "As coal; CCGTs hold a lower technical minimum than a coal unit."),
	("min_up_time_coal", "hours", [1.0, 48.0], 6.0, "free", "physical",
	 "The minimum hours a coal unit must stay running once started. ENTSO-E "
	 "defines minimum up time as the hours a unit must stay in operation "
	 "before it can be idled; 48 h is a cold-start-to-shutdown minimum for a "
	 "large unit."),
	("min_down_time_coal", "hours", [1.0, 48.0], 4.0, "free", "physical",
	 "The minimum hours a coal unit must stay off before it can be restarted. "
	 "A lower bound of one hour rather than zero: a zero here reaches the "
	 "cycling ceiling's denominator alongside a zero up time."),
	("storage_duration_curve", "hours", [0.0, 100.0], 6.0, "free", "physical",
	 "The energy-to-power ratio of the storage fleet in hours. IEA/NEA define "
	 "discharge duration as E/P at nominal power, which is exactly this node: "
	 "multiplying it by the fleet's power rating gives the fleet's energy. "
	 "100 h is the long-duration ceiling, pumped hydro at the top of its "
	 "band."),
	("workshop_capacity", "events/year", [0.0, 2000.0], 500.0, "free", "fixed",
	 "A workshop's throughput in maintenance events per year. 2,000 is ten a "
	 "working day across a large utility's shops; 500 is the default the pack "
	 "measured against a workload of 440."),
	("loss_reduction_investment", "USD", [0.0, 1e10], 5000000.0, "free", "policy",
	 "An investment amount in currency, matching `line_upgrade_budget`'s unit "
	 "so the budget bound needs no scale. 5 m is the pack's measured default; "
	 "the graph's own defaults put the loss-reduction target above what the "
	 "budget allows, which the bound reports rather than hides."),
)


#: (name, unit, range, default, role, determinism, prose) -- the two retypes
#: that are derived rather than free. Both appear in the PRODUCT table of the
#: pack rather than its retype table, and their role change is the point.
BATCH38_DERIVED_RETYPES: tuple[tuple[str, str, list[float], None, str, str, str], ...] = (
	("payment_security_required", "USD/year", [0.0, 1e11], None, "derived", "fixed",
	 "The security a counterparty must post: the share of settled value "
	 "exposed to settlement failure times the value settled. Retained as "
	 "`USD/year` to match `collateral_posted_usd_per_year`'s annualised "
	 "convention. Derived as of batch 38, so it carries no default."),
	("asset_age_distribution", "years", [0.0, 100.0], None, "derived", "physical",
	 "The fleet's mean age. `remaining_useful_life` already ships as "
	 "`asset_life * asset_condition_index`, so the age is the part of life "
	 "already spent: 25 x (1 - 0.7) = 7.5 years at defaults. The node's name "
	 "says distribution; a mean is the one moment of a distribution the graph "
	 "can carry, and this description is the correction."),
)


#: (id, unit, range, role, determinism, category, prose) -- four lhs ids that do not
#: exist. Each is derived, so each carries a range and no default: the loader
#: refuses a derived parameter with a default, and a determined parameter with
#: no range.
BATCH38_NEW_NODES: tuple[
	tuple[str, str, list[float], str, str, str, str], ...] = (
	("thermal_ramp_capability_mw_per_hour", "MW/hour", [0.0, 20000.0],
	 "derived", "physical", "Operational",
	 "The thermal fleet's aggregate ramp capability. A ramp rate is per unit "
	 "of capacity; without a fleet-level MW/hour the rate has no magnitude, "
	 "and nothing else in the graph multiplies capacity by a ramp. 20 GW/hour "
	 "is the largest plausible national fleet's full range in one hour; zero "
	 "is a fleet that cannot move."),
	("thermal_minimum_generation_mw", "MW", [0.0, 100000.0],
	 "derived", "physical", "Operational",
	 "The thermal fleet's must-run floor: each technology's minimum stable "
	 "level times its capacity, summed. 100 GW is above any single country's "
	 "thermal fleet; zero is a fleet with no must-run constraint."),
	("coal_cycling_ceiling_per_year", "1/year", [0.0, 8760.0],
	 "derived", "physical", "Operational",
	 "The most often a coal unit can cycle in a year given its minimum up and "
	 "down times: 8,760 hours over the sum of the two. 876 cycles/year at "
	 "defaults (6 h up, 4 h down). The upper bound is one cycle per hour, the "
	 "physical maximum; the up/down constraint makes the real value far "
	 "lower. This is the only arithmetically clean use of the two duration "
	 "nodes, which otherwise can only be typed and left."),
	("storage_energy_capacity_mwh", "MWh", [0.0, 1e8],
	 "derived", "physical", "Supply",
	 "The storage fleet's energy: its duration in hours times its power "
	 "rating. 4,800 MWh at defaults (6 h x 800 MW). The graph carried the "
	 "storage fleet's power and its duration but no energy, and energy is "
	 "what a duration-limited dispatch is bounded by. 100 TWh is several "
	 "times any plausible national store."),
)


#: (eq_id, lhs, rhs, prose, system, reference) -- six equalities.
BATCH38_EQUATIONS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
	("thermal_ramp_capability_definition", "thermal_ramp_capability_mw_per_hour",
	 "ramp_rate_coal * coal_capacity + ramp_rate_gas * gas_capacity",
	 "The fleet's ramp capability is each thermal technology's per-unit ramp "
	 "rate times its capacity, summed: 0.02 x 3,000 + 0.1 x 1,500 = 210 "
	 "MW/hour at defaults. The rate is per unit of rated output because that "
	 "is how the parameter is collected; the capacity is what gives it a "
	 "magnitude. Only coal and gas are summed: no other thermal technology in "
	 "the graph carries a declared ramp rate, and a term for a technology "
	 "whose rate is unstated would be an invented operand.",
	 "energy_balance", "entsoe_adequacy"),
	("thermal_minimum_generation_definition", "thermal_minimum_generation_mw",
	 "min_stable_level_coal * coal_capacity"
	 " + min_stable_level_gas * gas_capacity",
	 "The must-run floor is each thermal technology's minimum stable level "
	 "times its capacity: 0.4 x 3,000 + 0.3 x 1,500 = 1,650 MW at defaults, "
	 "36.67% of the 4,500 MW thermal fleet. This is the quantity a dispatch "
	 "cannot go below while a unit is on, which is what makes it a floor "
	 "rather than a preference.",
	 "energy_balance", "entsoe_adequacy"),
	("coal_cycling_ceiling_definition", "coal_cycling_ceiling_per_year",
	 "8760 / (min_up_time_coal + min_down_time_coal)",
	 "The cycle ceiling: the hours in a year over one full up-and-down cycle. "
	 "8,760 / (6 + 4) = 876 cycles/year at defaults. A unit that must run six "
	 "hours and stay off four cannot cycle more often than once every ten "
	 "hours, so the two durations bound the start count from above without "
	 "needing the start count the graph does not carry. The 8,760 is the "
	 "hours in a year, stated as a literal rather than read from "
	 "`time_horizon` because the ceiling is an annual rate, not a "
	 "horizon-dependent quantity.",
	 "energy_balance", "entsoe_adequacy"),
	("storage_energy_capacity_definition", "storage_energy_capacity_mwh",
	 "storage_duration_curve * storage_capacity_mw",
	 "The store's energy is its duration times its power: 6 h x 800 MW = "
	 "4,800 MWh at defaults. The duration is the shipped dial and the energy "
	 "is the product, not the reverse: a scenario varies how long the fleet "
	 "can discharge at rating, and the energy follows. Making "
	 "`storage_duration_curve` the lhs would put a dial on the determined "
	 "path and stop it being a dial.",
	 "energy_balance", "iea_nea_egc"),
	("payment_security_required_definition", "payment_security_required",
	 "settlement_risk * total_revenue_usd_per_year",
	 "The security a counterparty must post is the share of settled value "
	 "exposed to settlement failure times the value settled: 0.01 x 6.487 bn "
	 "= 64.87 m USD/year at defaults. `collateral_posted_usd_per_year` is "
	 "already `collateral_requirements * allowed_revenue_requirement`, so "
	 "shipping that form here would ship the same number twice under two "
	 "names and in a different unit. This is a different quantity with a "
	 "different base, and it is the one the catalog's arrow to `cost_of_debt` "
	 "needs.",
	 "financial", "world_bank_regulation"),
	("asset_age_distribution_definition", "asset_age_distribution",
	 "asset_life - remaining_useful_life",
	 "The fleet's mean age is the part of asset life already spent: 25 - 17.5 "
	 "= 7.5 years at defaults. `remaining_useful_life` ships as "
	 "`asset_life * asset_condition_index`, so this identity is the "
	 "complement of the condition index scaled by life. Deriving it from "
	 "`plant_retirement_age` was rejected: that node is an alias of "
	 "`asset_life`, so the result would be the same number through a longer "
	 "dependency chain.",
	 "energy_balance", "catalog_duplicate_resolutions"),
)


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded) --
#: two inequalities. Both operands are declared, so both reach the optimiser
#: as linopy constraints rather than waiting for a post-solve check.
BATCH38_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...] = (
	("workshop_capacity_workload_bound", "workshop_capacity", "geq",
	 "number_of_generators * maintenance_frequency",
	 "The workshop must be able to take the fleet's planned maintenance "
	 "workload: 220 units x 2 events/year = 440 events/year against a "
	 "capacity of 500, so the bound holds with 60 events to spare. One-sided "
	 "because a workshop larger than the workload is idle capacity, not a "
	 "violation; an equality would size the workshop exactly to the fleet, "
	 "which is a policy statement the graph has no basis for, and it would "
	 "take `workshop_capacity` off the dial path.",
	 "energy_balance", "entsoe_adequacy",
	 "number_of_generators * maintenance_frequency", "workshop_capacity"),
	("loss_reduction_budget_bound", "loss_reduction_investment", "leq",
	 "line_upgrade_budget",
	 "Spend on loss reduction comes out of the line-upgrade budget, not out of "
	 "thin air: 5 m against a budget of 50 m, residual -45 m. The bound is "
	 "what makes the shipped `transmission_loss_reduction_target` achievable "
	 "only to the extent the budget allows. The tariff-share form was built "
	 "and measured: 69.43 m against the same 50 m budget, which violates -- "
	 "a finding about the graph's defaults rather than a reason to reject the "
	 "bound. This form uses `line_upgrade_budget` because the catalog's own "
	 "arrow names it and the units need no scale.",
	 "financial", "world_bank_regulation",
	 "line_upgrade_budget", "loss_reduction_investment"),
)


_BATCH38_SOURCE = "The operational and supply pack (batch 38)"


#: (name, unit, prose) -- ten retypes that correct a *dimension* and nothing
#: else. Range, default and role are unchanged, so this table carries no
#: numbers: the walk reads a node's declared `unit`, never its range, and a
#: row that restated a default would be a second place for that default to
#: drift.
#:
#: These are the eight failures `docs/prg-status.md` recorded as one decision
#: and deferred, plus the two that batch 38's and batch 39's packs found. The
#: decision is made here: an annual quantity is a *rate*, and the graph's own
#: convention is to say so in the unit. `coal_consumption` ships
#: `tonnes/year`, `total_revenue_usd_per_year` ships `USD/year`; a node whose
#: description reads "the sector's tonnes per year" and whose unit reads
#: `tonnes` is the one that is wrong.
#:
#: Three ids that look like they belong here do not, and the distinction is
#: the batch's own finding: `insurance_premium_usd_per_kw_year`,
#: `line_outage_hours_per_year` and `mini_grid_programme_spend_usd_per_year`
#: already shipped with the correct unit. The operand each multiplies was the
#: untyped one, which is why the repair is on `insurance_loss_share_of_cost`,
#: `line_outage_probability` and `mini_grid_deployment` instead. Writing this
#: table from the failing equations rather than from the failing nodes would
#: have retyped three correct nodes and left three wrong ones untouched.
BATCH40_RETYPES: tuple[tuple[str, str, str], ...] = (
	("steel_hydrogen_demand_tonnes", "tonnes/year",
	 "Hydrogen the H2-DRI steel route consumes per year. Shipped `tonnes`, "
	 "which made its own equation's rhs a rate against a stock. The name "
	 "keeps the `_tonnes` suffix because it is the quantity's name, not its "
	 "dimension -- `coal_consumption` sets the same precedent for a `_tonnes` "
	 "id carrying `tonnes/year`. 55,000 t/year at defaults (2 Mt steel x 0.5 "
	 "DRI x 55 kg/t x 1000)."),
	("co2_captured_cement_tonnes", "tonnes/year",
	 "CO2 the cement programme captures per year. 3.2 Mt/year at defaults (8 "
	 "Mt cement x 0.5 CCUS x 0.8 t CO2 per t clinker x 1e6)."),
	("co2_captured_industry_tonnes", "tonnes/year",
	 "CO2 the industrial CCUS programme captures per year. 2.58 Mt/year at "
	 "defaults: 0.1 of the fleet's 25.78 MtCO2 emissions."),
	("equity_irr_estimate", "1/year",
	 "The equity return, which is a rate by definition: `(CFADS - debt "
	 "service) / capex / (1 - debt fraction)` is (USD/kW/year) / (USD/kW). "
	 "Shipped `1`, so the node its own equation determines was dimensionless "
	 "and the walk called the equation inconsistent against it. 30.77%/year "
	 "at defaults -- high because the form is a first-year ratio with no "
	 "schedule, which the description already states."),
	("ammonia_export_volume_tonnes", "tonnes/year",
	 "Ammonia the export programme ships per year. 1,690 t/year at defaults: "
	 "20,000 MWh/year of hydrogen, half of it as ammonia, over hydrogen's "
	 "0.03333 MWh/kg and ammonia's 0.1775 t H2 per t NH3."),
	("line_outage_probability", "events/year",
	 "Outages per year on the line. Shipped `1/year`, which is a rate of "
	 "*something* and not of an event, so multiplying it by an hours-per-event "
	 "duration gave hours per year squared. 2 events/year at defaults. The "
	 "range [0, 365] is unchanged and reads as it should: at most one outage "
	 "a day."),
	("mini_grid_deployment", "connections/year",
	 "Connections the mini-grid programme serves per year. Shipped `1/year`, "
	 "which made the per-connection cost a per-year cost: 1,500 USD/connection "
	 "x 100,000 per year came out 1e6 times too large, at 1.5e11 USD/year "
	 "against a 5 bn range. The retype is what fixes the magnitude, not a "
	 "constant in the equation."),
	("pm25_relative_risk_per_kt", "1/(kt/year)",
	 "The relative risk a kt/year of PM2.5 adds. The concentration-response "
	 "slope is per unit of *annual* burden: the shipped `1/kt` made the "
	 "premature-deaths product carry deaths per year squared. 0.006 per "
	 "kt/year at defaults, giving 4,800 deaths/year over 5 m people at 0.008 "
	 "baseline mortality and 20 kt/year."),
	("insurance_loss_share_of_cost", "1/year",
	 "The premium as a share of installed cost *per year*, which is what an "
	 "insurance product quotes. Shipped `1`, a bare share, so the premium "
	 "product came out USD/kW against a USD/kW/year id. 0.005/year at "
	 "defaults, against the catalog's duplicate 0.008 that batch 33 resolved "
	 "in favour of the lower figure."),
	("premium_share_of_asset", "1/year",
	 "The annual premium as a fraction of the insured asset's value. Shipped "
	 "`1`; it aliases `insurance_loss_share_of_cost`, so it carries whatever "
	 "dimension that node does, and the two must move together."),
)


#: (name, unit, range, default, prose) -- one new node, and it is the only
#: conversion constant the eleven corrections needed that the graph did not
#: already carry. The hydrogen and ammonia factors were checked for: both
#: ship (`mwh_per_hydrogen_unit`, `mwh_per_ammonia_unit`), so the ammonia
#: product reads the existing one rather than declaring a second.
BATCH40_NEW_NODES: tuple[tuple[str, str, list[float], float, str], ...] = (
	("mwh_per_coal_unit", "MWh/tonne", [3.0, 12.0], 6.944,
	 "Thermal energy in a tonne of coal: 25 GJ/t at 3.6 GJ/MWh is 6.944 "
	 "MWh/tonne. The fourth member of the `mwh_per_*_unit` family -- oil, LNG "
	 "and ammonia already ship as constants with the same shape and the same "
	 "job, converting a commodity quoted per mass or volume into a price per "
	 "MWh. `coal_price_per_mwh` divided by the literal `25 * 3.6`, which is "
	 "the same arithmetic with the conversion buried in the equation; the "
	 "node's own description says the conversion is where a unit error would "
	 "hide, so it belongs in a typed node with a range a reviewer can "
	 "question. The band is lignite at 3 MWh/t to anthracite at 12; 25 GJ/t "
	 "is sub-bituminous, the traded default. Reading `mwh_per_oil_unit`'s "
	 "range and role as the family convention."),
)


#: (eq_id, lhs, rhs, prose, reference) -- two equation bodies. The other nine
#: corrections need no body change: their shipped rhs was already right and
#: the *operand's* dimension was wrong, which is why the retype table alone
#: takes those nine from inconsistent to consistent.
BATCH40_EQUATIONS: tuple[tuple[str, str, str, str, str | None], ...] = (
	("ammonia_export_volume_tonnes_definition", "ammonia_export_volume_tonnes",
	 "hydrogen_export_volume * ammonia_export_share / mwh_per_hydrogen_unit"
	 " / 1000 / hydrogen_share_of_ammonia",
	 "Ammonia shipped: the export energy, the share that goes as ammonia, "
	 "over hydrogen's energy content and over ammonia's hydrogen fraction. "
	 "The shipped form multiplied by `1000 * 0.05`, which is the same "
	 "arithmetic read the other way -- 1000 kg/t and 1/20 for the 5% the "
	 "ammonia carries -- and gave a dimension of mass x length^2 / time^3. "
	 "Written as division by the shipped `mwh_per_hydrogen_unit` because that "
	 "node already exists, is typed `MWh/kg`, and is what four other "
	 "equations divide by; a second literal for hydrogen's LHV would be two "
	 "sources for one physical constant. The 1000 converts kg to tonnes, "
	 "which is the one factor with no node behind it. 1,690 t/year at "
	 "defaults, and `hydrogen_share_of_ammonia` (0.1775 t H2 per t NH3, "
	 "stoichiometric) stays as it was: it is the check on the answer, not a "
	 "term that needed moving.",
	 None),
	("coal_price_per_mwh_definition", "coal_price_per_mwh",
	 "coal_price / mwh_per_coal_unit",
	 "The commodity price per tonne divided by the energy a tonne carries "
	 "gives the price per MWh thermal: 80 USD/t over 6.944 MWh/t is 11.52 "
	 "USD/MWh. The shipped form divided by `25 * 3.6`, which is the same "
	 "conversion with both factors as literals -- correct arithmetic that "
	 "still failed its own unit check, because `25` carries no unit and the "
	 "walker reads `USD/tonne / 1` as USD/tonne. 11.52 USD/MWh against the "
	 "shipped 0.889: the shipped value was 12.96x low, which the "
	 "operational-supply pack found and attributed to a factor-of-12.96 "
	 "error. It was not an arithmetic error; it was the walker refusing to "
	 "credit an untyped constant, which is the behaviour that catches the "
	 "real ones.",
	 None),
)


#: (eq_id, lhs, relation, rhs, prose, reference, binder, bounded) -- one bound.
BATCH40_BOUNDS: tuple[
	tuple[str, str, str, str, str, str | None, str, str], ...] = (
	("remedy_period_bound", "remedy_periods", "leq", "max_remedy_period_days",
	 "The cure window a contract offers must not exceed the ceiling its "
	 "licence sets, or the licence's own limit is breached by the contract it "
	 "authorises. 60 days under a 90-day ceiling at defaults, residual -30; "
	 "at 120 days the residual is +30 and the bound fails, so it is live. "
	 "The alternative right-hand side was the literal 365, rejected as a "
	 "tautology: `remedy_periods`' own range is [1, 365], so a bound against "
	 "it can never fail. `threshold-product-remainder.md` deferred this node "
	 "for want of a base and `contract-market.md` cited the deferral; the "
	 "base is declared here, in the same band as the window it ceilings, "
	 "which is what makes the bound non-vacuous by construction rather than "
	 "by a chosen number. An equality was refused by the loader: an "
	 "inequality bounds a value and only an equality fixes one, and a cure "
	 "window is a negotiated term, not a computed one.",
	 None, "max_remedy_period_days", "remedy_periods"),
)


#: (name, unit, range, default, role, determinism, prose) -- the base the
#: remedy bound needed.
BATCH40_BASES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	("max_remedy_period_days", "days", [1.0, 365.0], 90.0, "free", "policy",
	 "The ceiling a licence places on a cure window. 90 days is a "
	 "project-finance convention, not a measured figure: the archived World "
	 "Bank utilities handbook contains no occurrence of 'cure period', "
	 "'remedy period' or 'grace period' (grep count 0), so the bound carries "
	 "`reference: None` and the default is recorded as an adopted convention "
	 "rather than dressed in a citation the repository cannot produce. The "
	 "range is the same band `remedy_periods` sits in, deliberately: a "
	 "ceiling outside that band would make the bound vacuous by construction "
	 "of the ranges rather than by the policy it states."),
)


#: What the two corrected equations named before this batch touched them. A
#: literal, not a read of the live graph: after the bake the graph names the
#: new operands, and a condition derived from it would suppress the very edges
#: this batch adds -- making `--emit40` unreproducible against its own output.
BATCH40_SHIPPED_OPERANDS: dict[str, frozenset[str]] = {
	"ammonia_export_volume_tonnes_definition": frozenset({
		"ammonia_export_volume_tonnes", "hydrogen_export_volume",
		"ammonia_export_share", "hydrogen_share_of_ammonia",
	}),
	"coal_price_per_mwh_definition": frozenset({
		"coal_price_per_mwh", "coal_price",
	}),
}


def build_batch40(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The dimensional corrections the walk found, and the remedy bound.

	Eleven of the graph's 552 equations failed their own dimensional check,
	and `docs/prg-status.md` recorded the eight it found as one decision to
	make rather than eight mistakes to fix. This batch makes the decision and
	finds three more of the same class.

	*Nine of the eleven are an operand's dimension, not an equation's body.*
	That is the finding worth keeping: a correction that reads the failing
	equation and rewrites it would have changed nine correct formulas. The
	walk reports `lhs vs rhs` and the intuitive repair is the rhs, but the
	rhs is what the author wrote from the physics and the node is what the
	catalog typed from a spreadsheet. `line_outage_hours_per_year` was
	`probability * duration` in the shipped body and still is; what was wrong
	is that `line_outage_probability` shipped `1/year` for a count of events.
	The same holds for `insurance_premium_definition`,
	`premium_share_of_asset_definition`, `steel_hydrogen_demand_tonnes`,
	`co2_captured_cement_tonnes`, `co2_captured_industry_tonnes`,
	`equity_irr_estimate` and `premature_deaths_definition`.

	*Two are bodies.* `ammonia_export_volume_tonnes` multiplied `1000 * 0.05`
	where it should divide by hydrogen's energy content, and
	`coal_price_per_mwh` divided by an untyped `25 * 3.6`. Both were
	arithmetically right and dimensionally unstatable, which is the case a
	unit checker exists to refuse: a constant with no unit cannot be checked,
	and the shipped 0.889 USD/MWh was 12.96x low.

	*`rocof_definition` is diagnosed and deliberately not fixed.* The swing
	equation is `df/dt = P_loss * f0 / (2 H S)` and the shipped body omits
	`f0`, so it is wrong by a factor of 50 at a 50 Hz system -- measured
	1/50th of the correct value. Correcting it drives `frequency_nadir_hz` to
	43.06 Hz against its own [45, 50] floor, because `frequency_nadir_definition`
	applies the initial slope over a flat `frequency_response_time_s` of 10 s.
	Two shipped defaults then disagree: either the nadir chain's response
	time is too long, or the 45 Hz floor is not the UFLS setting it claims.
	That is a question about the nadir model, and bending either number to
	fit the other would be manufacturing agreement. Left inconsistent and
	recorded here, so the one remaining failure in the walk is a known open
	question rather than an unexplained red.

	*The remedy bound closes a deferral two packs passed between them.*
	`threshold-product-remainder.md` deferred `remedy_periods` pending a base
	and `contract-market.md` cited that deferral forward; the base is declared
	here.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, prose in BATCH40_RETYPES:
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name}: no shipped node to retype"
		# The assert is against a retype that changes nothing *on a graph that
		# has not seen this batch*. Re-emitting after the bake must still work:
		# the fragment is the auditable record of what the batch did, so a
		# second `--emit40` has to reproduce it byte for byte rather than fail
		# on its own prior output. The `source` field is what distinguishes the
		# two cases -- a node this batch already retyped carries its mark.
		if shipped.unit == unit:
			assert shipped.source == _BATCH40_SOURCE, (
				f"{name}: already typed {unit} by something other than this "
				"batch; a retype row whose diagnosis was wrong"
			)
		full: dict[str, Any] = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"description": prose, "unit": unit,
			"status": _kept_status(shipped),
			"source": _BATCH40_SOURCE,
		})
		nodes[name] = full

	for name, unit, rng, default, prose in BATCH40_NEW_NODES:
		existing = graph.nodes.get(name)
		# As with the retypes: re-emitting after the bake must reproduce the
		# fragment, so a node this batch created is not "a shipped node it did
		# not create". Any other source is.
		assert existing is None or existing.source == _BATCH40_SOURCE, (
			f"{name}: a shipped node this batch did not create"
		)
		nodes[name] = {
			"name": "MWh per coal unit",
			"description": prose, "category": "Cost", "type": "float",
			"unit": unit, "range": rng, "default": default,
			"role": "exogenous", "determinism": "physical",
			"priority": "P2", "status": "existing",
			"source": _BATCH40_SOURCE,
			"source_url": (
				"LHV of coal: 25 GJ/t (sub-bituminous); 3.6 GJ/MWh"
			),
			"users": ["Planners", "Researchers"],
		}

	for name, unit, rng, default, role, determinism, prose in BATCH40_BASES:
		existing = graph.nodes.get(name)
		assert existing is None or existing.source == _BATCH40_SOURCE, (
			f"{name}: a shipped node this batch did not create"
		)
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose, "category": "Contract", "type": "float",
			"unit": unit, "range": rng, "default": default,
			"role": role, "determinism": determinism,
			"priority": "P2", "status": "to_build",
			"source": _BATCH40_SOURCE,
			"users": ["Planners", "Regulators"],
		}

	for eq_id, lhs, rhs, prose, cite in BATCH40_EQUATIONS:
		shipped = graph.equations.get(eq_id)
		assert shipped is not None, f"{eq_id}: not a shipped equation"
		rhs_params = sorted(parse_side(rhs).symbols)
		known = set(nodes) | set(graph.nodes)
		missing = [sym for sym in rhs_params if sym not in known]
		assert not missing, f"{eq_id}: rhs names {missing}, which no node holds"
		assert lhs not in rhs_params, f"{eq_id}: lhs names itself on its rhs"
		equations[eq_id] = {
			"id": eq_id, "name": shipped.name, "description": prose,
			"system": shipped.system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": shipped.tolerance, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": (
				shipped.priority.value
				if hasattr(shipped.priority, "value") else shipped.priority
			), "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		# The edge set is corrected with the body: an operand the shipped
		# equation named and the new one does not is a coupling that no
		# longer exists, and leaving the edge would keep a parameter counted
		# as coupled by a formula that stopped reading it.
		#
		# The test is against `BATCH40_RETYPES`-era truth, not against the
		# graph as it stands: the graph has already seen this batch once it is
		# baked, so reading `shipped.parameters` there would suppress exactly
		# the edges the batch added and make the fragment unreproducible. The
		# operands these two corrections add are known -- they are the ones the
		# shipped bodies did not name -- and they are named here.
		for sym in rhs_params:
			if sym not in BATCH40_SHIPPED_OPERANDS[eq_id]:
				edges.append({
					"source": sym, "target": lhs, "equation_id": eq_id,
					"relationship": "functional", "direction": "forward",
					"strength": "hard",
					"description": "Enters the corrected product.",
					"reference": cite, "priority": "P1",
				})

	for eq_id, lhs, relation, rhs, prose, cite, binder, bounded in BATCH40_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, f"{eq_id}: bounded {bounded!r} is not named"
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		assert not set(binder_syms) & {bounded}, (
			f"{eq_id}: binder names the bounded node; a self-loop is no coupling"
		)
		equations[eq_id] = {
			"id": eq_id, "name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": "financial",
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		edges.append({
			"source": binder_syms[0], "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a scenario can clear the "
				"arithmetic and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	return nodes, equations, edges, rules


_BATCH40_SOURCE = "The dimensional corrections (batch 40)"


#: (name, unit, range, default, role, determinism, prose) -- one retype. The
#: range and default are unchanged; only the dimension is corrected, and the
#: bound is what forces it: a loss in `USD million` cannot be compared against
#: an exposure in `1` without the two sharing a dimension.
BATCH39_RETYPES: tuple[tuple[str, str, list[float], float, str, str, str], ...] = (
	("accumulation_risk", "USD million", [0.0, 1e6], 500000.0, "free", "fixed",
	 "The insurer's total exposure to a single event, in currency. The node "
	 "shipped dimensionless, which made the coherence bound against "
	 "`pml_99_5_usd_million` undecidable -- measured: 'the two sides do not "
	 "share a dimension'. In USD million the range admits exposures to 1e12 "
	 "USD, and the shipped default of 500,000 reads as 500 bn."),
)


#: (id, unit, range, role, determinism, category, prose) -- three lhs ids that
#: do not exist. Each is derived, so each carries a range and no default.
BATCH39_NEW_NODES: tuple[
	tuple[str, str, list[float], str, str, str, str], ...] = (
	("marine_otec_capex_usd", "USD", [0.0, 2.5e13], "derived", "physical",
	 "Financial",
	 "OTEC's installed capital cost: the per-kW rate over the built capacity. "
	 "`capex_marine_otec` is a rate and the graph held no total; the storage "
	 "family already has this shape in `hydrogen_storage_capex_usd`. 0 USD at "
	 "defaults because no OTEC is built, which is a correct zero rather than "
	 "a dead equation. The upper bound is the product of the two operands' "
	 "own maxima: 25,000 USD/kW x 1e6 MW x 1000."),
	("marine_tidal_capex_usd", "USD", [0.0, 1.5e13], "derived", "physical",
	 "Financial",
	 "Tidal's installed capital cost, the same construction: 15,000 USD/kW x "
	 "1e6 MW x 1000 at the top of the band. `capex_tidal_range` is a second "
	 "spelling of the range technology and is not this node -- the two carry "
	 "different bands ([2500, 15000] against [3000, 15000]), and aliasing "
	 "them would merge a 15,000 USD/kW ceiling with a 2,500 one."),
	("eligible_own_funds_usd_million", "USD million", [-1.5e6, 1.5e6],
	 "derived", "physical", "Financial",
	 "The capital an insurer actually holds against its requirement. "
	 "`solvency_capital_ratio`'s own description defines the ratio as "
	 "eligible own funds over required solvency capital, and the denominator "
	 "is `solvency_capital`; the numerator was missing, so the ratio was a "
	 "bare number with no balance-sheet quantity behind it. 720 USD million "
	 "at defaults. Signed because `solvency_capital` is signed: "
	 "`pml_99_5 - aal` goes negative when the expected loss exceeds the tail, "
	 "which is a book no capital covers. The range is the ratio's [0.8, 3.0] "
	 "times `solvency_capital`'s [-5e5, 5e5]."),
)


#: (eq_id, lhs, rhs, prose, system, reference) -- three equalities. All three
#: carry `reference: None`: two are unit conversions (USD/kW x MW x 1000, and
#: a ratio times its own denominator), which state no external result, and
#: inventing a citation for arithmetic would be the comfortable row.
BATCH39_EQUATIONS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
	("marine_otec_capex_definition", "marine_otec_capex_usd",
	 "capex_marine_otec * marine_otec_capacity * 1000",
	 "OTEC's installed capital cost: the per-kW rate over the built capacity. "
	 "The 1000 is the kW/MW conversion, and it is written as a literal rather "
	 "than folded into the rate so the rate keeps the unit a TSO or a vendor "
	 "quotes it in. 0 USD at defaults because `marine_otec_capacity` defaults "
	 "to 0; 100 MW at 12,000 USD/kW is 1.2 bn USD. A levelised cost was the "
	 "alternative and is blocked: `crf_marine_otec`, "
	 "`capacity_factor_marine_otec` and `opex_fixed_marine_otec` are all "
	 "absent.",
	 "financial", None),
	("marine_tidal_capex_definition", "marine_tidal_capex_usd",
	 "capex_marine_tidal * marine_tidal_capacity * 1000",
	 "Tidal's installed capital cost, the same conversion. 0 USD at defaults; "
	 "100 MW at 7,000 USD/kW is 0.7 bn USD.",
	 "financial", None),
	("eligible_own_funds_definition", "eligible_own_funds_usd_million",
	 "solvency_capital_ratio * solvency_capital",
	 "The capital held is the ratio times the capital required: 1.6 x 450 = "
	 "720 USD million at defaults, and 405 at a ratio of 0.9. This is the "
	 "ratio's own definition solved for its numerator. Aliasing it to "
	 "`solvency_capital` was rejected: that makes the ratio identically 1.0 "
	 "and deletes the dial the prudential regime is about.",
	 "financial", None),
)


#: (eq_id, lhs, relation, rhs, prose, system, reference, binder, bounded) --
#: two inequalities. Both operands are settable scalars, so both route
#: `bound` and reach the optimiser rather than waiting for a post-solve check.
BATCH39_BOUNDS: tuple[
	tuple[str, str, str, str, str, str, str | None, str, str], ...] = (
	("ocgt_capex_ordering_bound", "capex_gas_ocgt", "leq", "capex_gas",
	 "A peaker costs less per kW than the combined cycle it backs up, which "
	 "the node's own description already states: lower capex and lower "
	 "efficiency than the CCGT, and that trade is why both live in the graph. "
	 "650 <= 1,100 at defaults, residual -450; at 1,200 the residual is +100 "
	 "and the bound fails, so it is live rather than vacuous. The prior "
	 "pack's deferral of this node rests on a false reason -- it claimed the "
	 "OCGT LCOE comes out below the CCGT's at any capacity factor, and the "
	 "shipped form crosses at 0.3965 (78.39 at 0.6, 96.77 at the archived "
	 "0.3). The blocker was never a sign error; it is three absent peaker "
	 "rates.",
	 "cost_accounting", "IEA/NEA Projected Costs of Generating Electricity",
	 "capex_gas", "capex_gas_ocgt"),
	("accumulation_exposure_bound", "accumulation_risk", "geq",
	 "pml_99_5_usd_million",
	 "The insurer's exposure to a single event must cover the loss it models "
	 "at the 99.5th percentile, or the tail is drawn from a distribution the "
	 "book cannot pay. 500,000 >= 500 at defaults, residual 499,500; at 100 "
	 "the residual is -400 and the bound fails. The bound is what forces the "
	 "retype: with `accumulation_risk` dimensionless the comparison is "
	 "undecidable, which is the finding rather than a defect. An equality "
	 "was rejected -- it would make a firm-specific input derived from a "
	 "modelled output and delete the dial.",
	 "financial", None, "pml_99_5_usd_million", "accumulation_risk"),
)


_BATCH39_SOURCE = "The digital and marine pack (batch 39)"


def build_batch39(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The digital-sector pack: three products, two bounds, one retype.

	The slice is 74 nodes of digital infrastructure, marine technology and
	insurance procedure. Five couple; sixty-nine defer across six registers,
	and the reason is the pack's whole finding rather than a shortcut:

	*Thirty-four are qualitative.* Procedures, standards and rulebooks -- a
	cybersecurity framework, a data-governance regime, a maintenance policy.
	No arithmetic exists on a standard's name, and the graph's categorical
	type does not help: a categorical needs an enum an equation can branch
	on, and the DSL has no branch.

	*Twenty-eight need an operand the graph does not carry.* A formula is
	statable and one of its terms is absent, which is the class that most
	often tempts an invented operand.

	*Five are scene switches* and *two are DEPRECATED* -- the latter a node
	whose correct coupling is its removal, which this batch does not perform.

	*The five that couple are the three shapes the pack admits.* Two marine
	products convert a per-kW rate over a capacity the graph already types;
	one insurance product solves the shipped solvency ratio for its missing
	numerator; and two bounds compare declared scalars, one of which is only
	comparable after the retype.

	*The retype is the finding, not the decoration.* `accumulation_risk`
	shipped dimensionless, and the coherence bound against a currency
	quantity is undecidable against it -- measured, not inferred. Corrected
	to `USD million`, all five equations unit-check consistent.

	*Two things this pack diagnoses and does not fix.* `lcoe_wind_definition`
	carries a description of an amendment that has already landed, and its
	consequence is that `opex_fixed_wind` has zero equation readers and is a
	dead duplicate; `supply-emissions-grid.md` lines 159-160 are stale on all
	three marine capacities, and its requested retype of
	`gravity_storage_capacity` to MWh would turn the shipped bound against
	`storage_headroom_mw` from consistent to inconsistent. Both are recorded
	in the pack and left for a dedicated fix: correcting shipped prose and
	retyping a shipped bound are different units of work from coupling a
	node, and the second would break a bound that currently holds.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, role, determinism, prose in BATCH39_RETYPES:
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name}: no shipped node to retype"
		full: dict[str, Any] = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": role, "determinism": determinism,
			"priority": "P1", "status": _kept_status(shipped),
			"source": _BATCH39_SOURCE,
			"users": ["Planners", "Regulators", "Researchers"],
		})
		full["default"] = default
		nodes[name] = full

	for name, unit, rng, role, determinism, category, prose in BATCH39_NEW_NODES:
		existing = graph.nodes.get(name)
		assert existing is None or existing.source == _BATCH39_SOURCE, (
			f"{name}: a shipped node this batch did not create"
		)
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": role, "determinism": determinism,
			"category": category,
			"priority": "P1", "status": "to_build",
			"source": _BATCH39_SOURCE,
			"users": ["Planners", "Regulators", "Researchers"],
		}

	determined = {row[1] for row in BATCH39_EQUATIONS}
	for name in determined:
		assert nodes[name]["role"] == "derived", (
			f"{name}: an equation determines it, so it must be derived"
		)
		assert "default" not in nodes[name], f"{name}: derived and carrying a default"

	for eq_id, lhs, rhs, prose, system, cite in BATCH39_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		known = set(nodes) | set(graph.nodes)
		assert lhs in known, f"{eq_id}: {lhs!r} has no node body"
		assert lhs not in rhs_params, f"{eq_id}: lhs names itself on its rhs"
		missing = [sym for sym in rhs_params if sym not in known]
		assert not missing, f"{eq_id}: rhs names {missing}, which no node holds"
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the marine or solvency product.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH39_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, f"{eq_id}: bounded {bounded!r} is not named"
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		assert not set(binder_syms) & {bounded}, (
			f"{eq_id}: binder names the bounded node; a self-loop is no coupling"
		)
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		edges.append({
			"source": binder_syms[0], "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a scenario can clear the "
				"arithmetic and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	return nodes, equations, edges, rules


def build_batch38(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The operational-supply pack: six products, two bounds, eleven retypes.

	The slice is 42 nodes of plant operation, maintenance and network
	switching. Eleven couple; thirty-one defer, and the deferral classes are
	specific rather than a blanket "qualitative":

	*Nine need an operand the graph does not carry.* A microgrid has no
	installed capacity or site count; a start-up cost has no start count; a
	nuclear lead time has no nuclear-specific build duration; a reservoir has
	no energy capacity; and `ac_voltage_limit` has no voltage dimension at all
	-- `kv` returns no node. Each was checked by name against the graph, and
	the pack records which neighbouring node is close enough to be tempting
	and not close enough to alias.

	*Twelve are qualitative.* Regime selectors, model switches, event logs and
	schedules. `condition_based_maintenance` is the one worth naming: the
	obvious alias is `predictive_maintenance_adoption`, but that node is the
	share of maintenance already *moved into* the regime, one level
	downstream. Aliasing the regime onto its own adoption share states that
	the regime is the adoption, which overstates it. Built, unit-checked and
	measured (0.5 at defaults) before being rejected.

	*Ten are scene switches.* Booleans and coupling-algorithm selectors, none
	read by any equation. `unit_commitment` is the clearest: multiplying it by
	anything produces a product of a solver flag. The graph's precedent for a
	switch that *is* read is `n_1_criterion`, and there the switch selects a
	magnitude that exists independently -- none of these ten has one.

	*The six that couple, and the arithmetic.* Four new nodes give the
	per-unit parameters a fleet magnitude: a ramp rate times capacity is
	MW/hour, a minimum stable level times capacity is MW, two durations give a
	cycle ceiling, and a duration times power gives energy. Each is the only
	arithmetically clean use of its operands, and each operand was already
	typed and ranged. The other two are a settlement-risk product and a
	complement of the condition index.

	*The two bounds are one-sided on purpose.* A workshop larger than its
	workload is idle capacity, and loss-reduction spend below its budget is
	prudence; only the excess is a violation. Both sides are declared, so both
	routes are `bound` and reach the optimiser as linopy constraints.

	*The retypes are the coupling's prerequisite.* Every one of the eleven
	shipped with `unit: None`, range [0, 1e6] and default 500,000. A ramp rate
	of 500,000 per hour is a unit that ramps its whole rating half a million
	times an hour; a minimum up time of 500,000 hours is fifty-seven years.
	Without the retype the four new nodes would compute 500,000-scale garbage
	and both bounds would be unfalsifiable.

	*Two shipped equations this batch's slice diagnoses and does not fix.*
	`line_outage_hours_per_year_definition` is missing an events-per-year
	factor and `coal_price_per_mwh` is off by 12.96x; both fail their own unit
	checks and both belong to this pack's findings, not to its proposals. They
	are recorded in the pack and left for a dedicated fix, because changing a
	shipped equation's body is a different unit of work from coupling a node.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for row in BATCH38_RETYPES + BATCH38_DERIVED_RETYPES:
		name, unit, rng, default, role, determinism, prose = row
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name}: no shipped node to retype"
		full: dict[str, Any] = dict(
			shipped.model_dump(exclude={"id"}, mode="json")
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": role, "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": _BATCH38_SOURCE,
			"users": ["Planners", "Regulators", "Researchers"],
		})
		# A derived node carries no default; a free one must keep the value
		# the pack measured, or every defaults-fill becomes a GraphError.
		if role == "derived":
			full.pop("default", None)
		else:
			full["default"] = default
		nodes[name] = full

	for name, unit, rng, role, determinism, category, prose in BATCH38_NEW_NODES:
		existing = graph.nodes.get(name)
		assert existing is None or existing.source == _BATCH38_SOURCE, (
			f"{name}: a shipped node this batch did not create"
		)
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": role, "determinism": determinism,
			"category": category,
			"priority": "P1", "status": "to_build",
			"source": _BATCH38_SOURCE,
			"users": ["Planners", "Regulators", "Researchers"],
		}

	determined = {row[1] for row in BATCH38_EQUATIONS}
	for name in determined:
		assert nodes[name]["role"] == "derived", (
			f"{name}: an equation determines it, so it must be derived"
		)
		assert "default" not in nodes[name], (
			f"{name}: derived and carrying a default"
		)

	for eq_id, lhs, rhs, prose, system, cite in BATCH38_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		known = set(nodes) | set(graph.nodes)
		assert lhs in known, f"{eq_id}: {lhs!r} has no node body"
		assert lhs not in rhs_params, f"{eq_id}: lhs names itself on its rhs"
		missing = [sym for sym in rhs_params if sym not in known]
		assert not missing, f"{eq_id}: rhs names {missing}, which no node holds"
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the operational identity.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH38_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, f"{eq_id}: bounded {bounded!r} is not named"
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		assert not set(binder_syms) & {bounded}, (
			f"{eq_id}: binder names the bounded node; a self-loop is no coupling"
		)
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		edges.append({
			"source": binder_syms[0], "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a scenario can clear the "
				"arithmetic and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	return nodes, equations, edges, rules


def build_batch37(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The macro-climate pack: five products, two bounds, twenty-three retypes.

	The slice is 105 nodes of macro, climate, adaptation, geopolitical, land,
	spatial and scenario families. Twenty-one couple; eighty-four defer, and
	the pack's reasons are specific in each row rather than a blanket
	"qualitative". Three deferral classes dominate and none of them is a
	shortcut this batch could take:

	*Forty-two need an operand the graph does not carry.* The macro block is
	blocked on `gdp_usd_per_year` -- absent -- so seven ratios have no
	denominator. The pollutant block needs per-fuel generation and
	species-specific emission factors, and every `emission_factor_*` node that
	exists is CO2. The adaptation block needs a damage function or a cost curve
	and neither exists.

	*Twenty-four are scene switches.* A method flag is a level, and a level is
	not a number. The graph has a categorical type now -- batch 36 shipped six
	-- so this is no longer the hard block the pack recorded, but a categorical
	still needs an enum whose levels an equation can branch on, and the DSL has
	no branch. Deriving `temperature_increase` from `ssp_pathway` would need a
	mapping table the graph does not carry; inventing one is the
	operand-invention failure this arc refuses.

	*Eighteen are qualitative.* Governance and safeguard constructs with no
	unit and no scale. A number here would be a judgement, and the one numeric
	quantity in that family, `grievance_redress_effectiveness`, is already typed
	with a declared share range and deferred for want of an operand.

	*The five that couple, and why each is safe.* Two composites are means of
	dials the graph already declares -- every operand is typed, ranged and
	readable, so the arithmetic is checkable from its parts. Two aliases resolve
	catalog duplicate rows onto drivers the graph already derives, which removes
	a placeholder that could be set to contradict the project's own take.
	`snapshot_weightings` is the one genuinely new arithmetic: the horizon's
	hours over the snapshot count, the quantity a temporal aggregation must
	preserve.

	*Two prerequisites, and the pack measured why.* `snapshot_weightings`
	divides by `representative_snapshots`, which is derived as
	`representative_days * tsam_segments`. Retyping the denominator alone does
	not prevent the pole: the product is already zero before the node's range
	is consulted. Retyping `representative_days` to `[1, 100]` is what converts
	a `ZeroDivisionError` from inside `propagate` into a clean range refusal at
	the door. `time_horizon` is retyped for the same reason in the other
	direction: at zero the window bound holds for every value of the quantity
	it is supposed to constrain, which is a bound that binds nothing.

	*A cross-validation rule this batch makes reachable, and does not change.*
	`index_above_unity` is an `error` rule over eleven [0, 1] indices. Once
	`exposure_index` is derived, a legal input vector -- all eight hazards at
	0.99 -- derives an index the rule refuses, and the CLI exits 1. The pack
	measured this and left the decision open. This batch leaves the rule as it
	stands: the corner it fires on is a scenario with every hazard dial at the
	top of its range, which is a scenario worth refusing on its own terms, and
	exempting derived composites would be a change to the validation contract
	that no equation in this batch requires. It is recorded here so the next
	reader knows the interaction is deliberate.

	*The two composites carry `reference: None`.* They are unweighted means of
	declared dials; no archived work states this aggregation, and the component
	provenance the catalog gives -- World Bank WGI for the governance dials,
	ND-GAIN for the hazards -- is not in `sources/archive/`. The pack lists both
	under **Sources to fetch**. A fabricated citation would be worse than the
	gap, which the citation register already counts.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for row in BATCH37_RETYPES + BATCH37_PREREQUISITES:
		name, unit, rng, default, role, determinism, prose = row
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "role": role, "determinism": determinism,
			"priority": "P1",
			"status": _kept_status(shipped),
			"source": _BATCH37_SOURCE,
			"users": ["Planners", "Regulators", "Researchers"],
		})
		# A derived node has no default and a free one must keep the one the
		# pack measured; writing `None` over a free node's default would make
		# every value at defaults a `GraphError` rather than a number.
		if role == "derived":
			full.pop("default", None)
		else:
			full["default"] = default
		nodes[name] = full

	for eq_id, lhs, rhs, prose, system, cite in BATCH37_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		known = set(nodes) | set(graph.nodes)
		assert lhs in known, f"{eq_id}: {lhs!r} has no node body"
		assert lhs not in rhs_params, f"{eq_id}: lhs names itself on its rhs"
		missing = [sym for sym in rhs_params if sym not in known]
		assert not missing, f"{eq_id}: rhs names {missing}, which no node holds"
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the composite or alias identity.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH37_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, f"{eq_id}: bounded {bounded!r} is not named"
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		binder_node = binder_syms[0]
		assert binder_node in known, f"{eq_id}: binder has no node among its symbols"
		assert binder_node != bounded, (
			f"{eq_id}: binder and bounded are both {bounded!r}; a self-loop "
			"names no coupling"
		)
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		edges.append({
			"source": binder_node, "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a scenario can clear the "
				"arithmetic and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	for rule_id, condition, severity, message, suggestion, prose in BATCH37_RULES:
		shipped = [r for r in graph.rules if r.id == rule_id]
		assert len(shipped) == 1, f"{rule_id}: expected one shipped rule"
		rules.append({
			"id": rule_id, "condition": condition, "severity": severity,
			"message": message, "suggestion": suggestion,
			"description": prose,
		})

	return nodes, equations, edges, rules


def build_batch36(graph: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
	"""The contract and market pack: six products, one bound, sixteen retypes.

	The slice is 63 nodes of market design, contract terms and counterparty
	exposure. Fifty-six defer, and the deferrals are mostly structural: a
	market *rule* is not a quantity, and a node whose whole content is "which
	mechanism" has no base to multiply. Seven couple, and each couples because
	the graph already carries every operand of the arithmetic.

	*Six of the seven are aliases, and that is the finding rather than a
	shortcut.* `counterparty_risk` is `settlement_risk` under a second name;
	`cost_pass_through_mechanism` is `wholesale_cost_pass_through`. Each shipped
	as a float placeholder with no unit and a midpoint default of 500,000 -- a
	"risk" of half a million with no dimension -- while the graph carried the
	actual share, typed and ranged. The alias removes the placeholder from
	`uncoupled()` without inventing arithmetic, which is the coupling the
	catalog's own duplicate rows call for.

	*The one contested alias.* `unclassified.md` classifies
	`cost_pass_through_mechanism` as QUALITATIVE -- "which costs pass through
	automatically and which go to a review. A rule, not a rate" -- and that
	reading is defensible: the rule and the share are not obviously one object.
	This batch ships the alias because the node is a float placeholder, the
	graph carries exactly one pass-through share, and the shipped
	`pass_through_tariff_definition` already consumes it. The description
	records the disagreement rather than settling it, so a reviewer who reads
	the node as the rule set knows what to change.

	*The two products that are not aliases.* `security_package` sums the
	performance bond and the parent's guarantee -- two capital stocks the graph
	already derives, released rather than spent. `tax_incentives` is the
	untaxed fraction of the term at the corporate rate on the fleet's cash.
	Both were shipped as 500,000-USD placeholders with no unit.

	*`ppa_termination_payments` is the annuity, not the sum.* A make-whole
	clause compensates forgone revenue; paying twenty years of it as a lump sum
	today overstates the liability 2.4x (77.16 bn against 31.83 bn). The
	undiscounted form was built and measured before being rejected.

	*One new node, because the graph held the two halves of a quotient and no
	node joining them.* `auction_volume_per_round` is the annual volume over the
	round frequency -- 25 / 12 = 2.0833 MtCO2 at defaults. The per-round size is
	what an auction calendar is designed around and no shipped node carried it.

	*The one bound, and why it is a bound rather than an identity.*
	`gate_closure >= settlement_period` says the market closes no later than one
	settlement interval before delivery. An equality would make every operator
	run the same gate, which is a policy statement the graph has no basis for.
	Both sides are declared, so this route is `bound` and reaches the optimiser
	as a linopy constraint rather than a post-solve check.

	*The retypes are the coupling's prerequisite, not decoration.* Every one of
	the sixteen shipped with `unit: None`, range [0, 1e6] and default 500000.0.
	A gate closure of 500,000 hours is fifty-seven years; an auction frequency
	of 500,000 per year is 1,370 auctions a day. Without the retype the bound
	above is unfalsifiable and the products carry a dimension their operands do
	not. The five categoricals are the same defect one step further: they are
	levels that shipped as floats, and a level has no magnitude.
	"""
	from alea.prg.dsl import parse_side

	nodes: dict[str, Any] = {}
	equations: dict[str, Any] = {}
	edges: list[dict[str, Any]] = []
	rules: list[dict[str, Any]] = []

	for name, unit, rng, default, determinism, prose in BATCH36_RETYPES:
		shipped = graph.nodes.get(name)
		full: dict[str, Any] = (
			dict(shipped.model_dump(exclude={"id"}, mode="json"))
			if shipped is not None else {"name": name.replace("_", " ").capitalize()}
		)
		full.update({
			"description": prose, "type": "float", "unit": unit,
			"range": rng, "determinism": determinism, "priority": "P1",
			"status": _kept_status(shipped),
			"source": _BATCH36_SOURCE,
			"users": ["Planners", "Regulators"],
		})
		full["default"] = default
		nodes[name] = full

	# The levels. A categorical carries no range and no unit, and its
	# admissible set is `categories` -- which is what `_validate` checks a value
	# against, so a categorical with a range is refused by the loader.
	for name, categories, default, prose in BATCH36_CATEGORICALS:
		shipped = graph.nodes.get(name)
		assert shipped is not None, f"{name} is retyped categorical and not shipped"
		full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
		full.update({
			"description": prose, "type": "categorical", "unit": None,
			"range": None, "default": default, "categories": list(categories),
			"determinism": "policy", "priority": "P1",
			"status": _kept_status(shipped),
			"source": _BATCH36_SOURCE,
			"users": ["Planners", "Regulators"],
		})
		nodes[name] = full

	# The one new lhs id. Derived, so it carries no default; the guard is the
	# source string this batch stamps, which makes the emit repeatable without
	# letting the batch claim an id the catalog owns.
	for name, unit, rng, category, prose in BATCH36_NEW_NODES:
		existing = graph.nodes.get(name)
		assert existing is None or existing.source == _BATCH36_SOURCE, (
			f"{name} already ships and not from this batch; a new node needs "
			"an id the catalog does not own"
		)
		nodes[name] = {
			"name": name.replace("_", " ").capitalize(),
			"description": prose, "category": category, "type": "float",
			"unit": unit, "range": rng, "role": "derived",
			"determinism": "policy", "priority": "P1",
			"source": _BATCH36_SOURCE,
			"users": ["Planners", "Regulators"],
		}

	# A node a product determines is `derived` and carries no default. The
	# retype table above sets the unit and range; this pass sets the role,
	# because the two are separate claims and only the equation establishes
	# the second.
	determined = {row[1] for row in BATCH36_EQUATIONS}
	for name in determined:
		if name in nodes:
			nodes[name]["role"] = "derived"
			nodes[name].pop("default", None)
		else:
			shipped = graph.nodes.get(name)
			assert shipped is not None, f"{name} is neither retyped nor shipped"
			full = dict(shipped.model_dump(exclude={"id"}, mode="json"))
			full["role"] = "derived"
			full.pop("default", None)
			nodes[name] = full

	for eq_id, lhs, rhs, prose, system, cite in BATCH36_EQUATIONS:
		rhs_params = sorted(parse_side(rhs).symbols)
		known = set(nodes) | set(graph.nodes)
		assert lhs in known, f"{eq_id}: {lhs!r} has no node body"
		missing = [sym for sym in rhs_params if sym not in known]
		assert not missing, f"{eq_id}: rhs names {missing}, which no node holds"
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose,
			"system": system, "lhs": lhs, "rhs": rhs, "relation": "eq",
			"parameters": [lhs] + rhs_params, "free_variables": [],
			"determined_variables": [lhs],
			"tolerance": 1.0e-09, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P1", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		for sym in rhs_params:
			edges.append({
				"source": sym, "target": lhs, "equation_id": eq_id,
				"relationship": "functional", "direction": "forward",
				"strength": "hard",
				"description": "Enters the product identity.",
				"reference": cite, "priority": "P1",
			})

	for eq_id, lhs, relation, rhs, prose, system, cite, binder, bounded in BATCH36_BOUNDS:
		assert relation in ("leq", "geq"), f"{eq_id}: {relation} is not a bound"
		named = sorted(set(parse_side(lhs).symbols) | set(parse_side(rhs).symbols))
		known = set(nodes) | set(graph.nodes)
		assert bounded in known, f"{eq_id}: bounded {bounded!r} has no node"
		assert bounded in named, f"{eq_id}: bounded {bounded!r} is not named"
		binder_syms = sorted(parse_side(binder).symbols)
		assert binder_syms, f"{eq_id}: binder {binder!r} names no symbol"
		binder_node = binder_syms[0]
		assert binder_node in known, f"{eq_id}: binder has no node among its symbols"
		assert binder_node != bounded, (
			f"{eq_id}: binder and bounded are both {bounded!r}; a self-loop "
			"names no coupling"
		)
		equations[eq_id] = {
			"id": eq_id,
			"name": eq_id.replace("_", " ").capitalize(),
			"description": prose, "system": system,
			"lhs": lhs, "rhs": rhs, "relation": relation,
			"parameters": named, "free_variables": named,
			"determined_variables": (),
			"tolerance": 1.0e-06, "unit_check": True,
			"solution_method": "direct", "linearity": "linear",
			"priority": "P2", "reference": cite,
			"latex": r"\mathrm{see\ equation}",
		}
		edges.append({
			"source": binder_node, "target": bounded, "equation_id": eq_id,
			"relationship": "constraint", "direction": "forward",
			"strength": "hard",
			"description": (
				f"Bounds {bounded} against {binder}; a plan can clear the "
				"physics and fail this."
			),
			"reference": cite, "priority": "P2",
		})

	return nodes, equations, edges, rules


if __name__ == "__main__":
	sys.exit(main())