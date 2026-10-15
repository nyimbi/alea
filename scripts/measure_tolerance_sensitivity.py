#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure which equations report a violation for a 0.1% move in one parameter.

WHY THIS EXISTS. The specification's §24 assigns a tolerance by equation *type*
-- 1e-3 for an accounting identity, 1e-2 for an economic relationship or a
learning curve, 5e-2 for a health impact, 1e-1 for employment. The shipped
graph declares its own per equation and every one is at or below the spec's:
27 at 1e-9, six at 1e-8, six at 1e-6. This script measures what that
difference *does*, which is the only form the finding can take -- a table of
tolerances on each side is not itself a defect.

WHAT IT MEASURES. The graph's own defaults are propagated once, and then each
settable parameter is moved by ±0.1% and the set is re-checked **without
re-propagating**. That last word is the whole point: a propagation re-derives
every identity from its inputs, so the propagated path reports almost nothing.
The raw path is what a direct `consistency()` call reaches.

The residual tracks the perturbation -- a 0.1% move gives a ~1e-3 relative
residual -- so the number of violations is a fact about how many identities
depend on a moved parameter, not about numerical noise.

    python3 scripts/measure_tolerance_sensitivity.py
"""

from __future__ import annotations

import sys

from alea.prg import load_graph

STEP = 0.001
"""The perturbation, as a fraction. 0.1% is small enough to stay inside every
declared range and large enough to clear every declared tolerance by orders of
magnitude, so nothing here is a boundary effect."""

graph = load_graph()


def measure() -> dict[str, tuple[float, float]]:
	"""``equation_id -> (declared tolerance, worst relative residual)``."""
	base = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	settled = graph.propagate(base).values
	worst: dict[str, tuple[float, float]] = {}
	draws = 0
	for name in sorted(settled):
		if graph.node(name).default is None or not graph.is_settable(name):
			continue
		for factor in (1 + STEP, 1 - STEP):
			draws += 1
			probe = dict(settled)
			probe[name] = settled[name] * factor
			for violation in graph.consistency(probe):
				seen = worst.get(violation.equation_id)
				if seen is None or violation.relative > seen[1]:
					worst[violation.equation_id] = (
						violation.tolerance,
						violation.relative,
					)
	return {"__draws__": (float(draws), 0.0), **worst}  # type: ignore[dict-item]


if __name__ == "__main__":
	rows = measure()
	draws = int(rows.pop("__draws__")[0])
	print(f"draws: {draws}   equations reporting a violation: {len(rows)} of {len(graph.equations)}")
	print()
	for equation_id, (tolerance, relative) in sorted(
		rows.items(), key=lambda kv: -kv[1][1]
	):
		system = graph.equations[equation_id].system
		print(
			f"  {equation_id:34s} {system:18s} "
			f"declared={tolerance:.0e}  worst_rel={relative:.2e}"
		)
	sys.exit(0)
