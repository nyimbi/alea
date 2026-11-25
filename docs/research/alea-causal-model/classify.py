"""Classify every equation of the PRG by what kind of claim it makes.

Run: uv run python docs/research/alea-causal-model/classify.py
Writes equation-classes.csv next to this file and prints the counts.

Two layers, kept apart on purpose:
  structure   computed from the equation's text (alias, inequality, lookup table,
              functional form, arithmetic). Sound by construction.
  claim       what the equation asserts. Hand-labelled for the 44 functional-form
              equations; NOT assigned to the 588 arithmetic ones, where syntax
              cannot tell an accounting identity from an assumed effect size.
"""
import csv
import re
from collections import Counter
from pathlib import Path

from alea.prg.graph import load_graph

FUN = re.compile(r"\b(exp|log|ln|sqrt|tanh|min|max|if|abs|pow)\s*\(|\*\*|\^")

CLAIM = [  # (id regex, claim class)
	(r"^crf_|^debt_service|^fit_annuity|^llcr|^nuclear_idc|^ppa_termination|^fuel_diversity|half_life|^grid_extension_completion", "definition"),
	(r"escalated|growth_factor|^ppa_indexed|^coal_fleet_remaining|^tariff_rebalancing|^exchange_rate_stress", "projection_assumption"),
	(r"learning|_at_vintage|^weibull|^lolp|^equilibrium_warming", "empirical_relation"),
	(r"^equilibrium_demand$", "behavioural"),
	(r"^line_surge", "physical_law"),
]


def structure(e) -> str:
	if e.relation != "eq":
		return "inequality"
	if e.id.endswith("_alias") or re.fullmatch(r"\s*[A-Za-z_]\w*\s*", e.rhs):
		return "alias"
	if "choose(" in e.rhs:
		return "lookup_table"
	return "functional_form" if FUN.search(e.rhs) else "arithmetic"


def main() -> None:
	g = load_graph()
	eqs = list(g.equations.values())
	loops = {e.id for l in g.feedback_loops() for e in l.equations}
	rows = []
	for e in eqs:
		s = structure(e)
		claim = ""
		if s == "functional_form":
			hits = [c for pat, c in CLAIM if re.search(pat, e.id)]
			assert len(hits) == 1, (e.id, hits)
			claim = hits[0]
		rows.append(dict(id=e.id, system=e.system, structure=s, claim=claim,
			in_feedback_loop=e.id in loops, has_reference=bool(e.reference)))
	out = Path(__file__).with_name("equation-classes.csv")
	with out.open("w", newline="") as f:
		w = csv.DictWriter(f, fieldnames=list(rows[0]))
		w.writeheader()
		w.writerows(rows)
	print(len(rows), Counter(r["structure"] for r in rows))
	print(Counter(r["claim"] for r in rows if r["structure"] == "functional_form"))
	print("in loops:", sum(r["in_feedback_loop"] for r in rows), "no reference:", sum(not r["has_reference"] for r in rows))


if __name__ == "__main__":
	main()
