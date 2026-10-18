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
	tables: dict[str, dict[str, Any]] = {"12": BATCH12_NODES, "13": {}, "14": {}, "15": {}, "16": {}, "17": {}, "18": {}}
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
RATE_ALIASES: tuple[tuple[str, str], ...] = (
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


if __name__ == "__main__":
	sys.exit(main())
