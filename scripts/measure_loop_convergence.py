#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure the feedback loops' iteration counts with and without acceleration.

WHY THIS EXISTS. The specification's §37 prescribes Anderson acceleration (or
Aitken's delta-squared) for slow-converging loops, and on the graph's own
numbers both shipped loops *are* slow in the sense the spec means: 38 and 36
iterations at the defaults against a 200-iteration budget. Reading that, §37
looks like an obvious build. Measuring it says otherwise -- every accelerated
configuration is slower than the solver that already ships, and the smallest
history fails to converge at all.

WHAT IT MEASURES. The acceleration is applied where the spec's snippet applies
it: over the fixed-point map, by wrapping `solve_for` so the value returned to
the Gauss-Seidel sweep is an extrapolation of the last `m` iterates. The
baseline is the same solver with the wrapper absent, so the two runs differ in
exactly one thing.

THE SPEC'S SNIPPET DOES NOT RUN AS WRITTEN. `X = np.column_stack([x for x, _
in history])` over scalar iterates is a `(1, m)` row vector, so the extrapolant
comes back as a shape-`(1,)` array and `solve_for` raises `TypeError: only
0-dimensional arrays can be converted to Python scalars`. This script takes the
most favourable reading -- the scalar is extracted from that array -- so the
result is not an artefact of reading the snippet strictly. §37 is pseudocode
that was never executed.

WHY THE LOOPS ARE SEEDED THE WAY THEY ARE. A loop is solved cold against a
warm parameter set: the exogenous inputs come from one converged propagation,
and only the loop's own variables are reset to their declared starts. Starting
from the converged solution would make every configuration "converge" at turn
one and measure nothing, which is the fixture trap this script was rewritten
to avoid.

    python3 scripts/measure_loop_convergence.py
"""

from __future__ import annotations

import sys

import numpy as np

import alea.prg.feedback as fb
from alea.prg import load_graph

SCENARIOS: dict[str, dict[str, float] | None] = {
	"defaults": None,
	"carbon=1000": {"carbon_price_usd_per_tco2": 1000.0},
	"growth=0.15": {"demand_growth": 0.15},
	"low_capex": {"renewable_multiplier": 0.5},
}


def _seed(loop, warm: dict[str, float]) -> dict[str, float]:
	"""Loop variables at their declared start; every other parameter warm."""
	values = dict(warm)
	for name in loop.variables:
		node = graph.node(name)
		values[name] = (
			float(node.initial)
			if node.initial is not None
			else 0.5 * (node.range[0] + node.range[1])
		)
	return values


def _warm(scenario: dict[str, float] | None) -> dict[str, float]:
	base = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	base.update(scenario or {})
	return graph.propagate(base).values


def counts(scenario: dict[str, float] | None = None, *, m: int | None = None) -> dict:
	"""Iterations per loop, with Anderson of history ``m`` or plain Gauss-Seidel."""
	warm = _warm(scenario)
	original = fb.solve_for
	history: dict[str, list[tuple[float, float]]] = {}

	def accelerated(residual, target, values, bracket=None):
		raw = original(residual, target, values, bracket=bracket)
		if m is None:
			return raw
		seen = history.setdefault(target, [])
		seen.append((values[target], raw))
		del seen[:-m]
		if len(seen) < 2:
			return raw
		X = np.column_stack([x for x, _ in seen])
		G = np.column_stack([v for _, v in seen])
		R = G - X
		try:
			gamma = np.linalg.lstsq(R[:, :-1], R[:, -1], rcond=None)[0]
			step = (1 - gamma.sum()) * G[:, -1] + G[:, :-1] @ gamma
			return float(np.asarray(step).reshape(-1)[0])
		except np.linalg.LinAlgError:
			return raw

	if m is not None:
		fb.solve_for = accelerated
	try:
		out: dict[str, int] = {}
		for loop in graph.feedback_loops():
			short = loop.id.split("_")[1]
			out[short] = fb.solve_loop(graph, loop, _seed(loop, warm)).iterations
		return out
	except Exception as exc:  # noqa: BLE001 -- a failure to converge is a result
		return {loop.id.split("_")[1]: type(exc).__name__ for loop in graph.feedback_loops()}
	finally:
		fb.solve_for = original


graph = load_graph()

if __name__ == "__main__":
	print("Plain damped Gauss-Seidel (what ships):")
	for label, scenario in SCENARIOS.items():
		print(f"  {label:14s} {counts(scenario)}")
	print()
	print("Anderson acceleration, per spec §37:")
	for history_size in (2, 3, 5):
		print(f"  m={history_size}            {counts(m=history_size)}")
	sys.exit(0)
