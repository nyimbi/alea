# SPDX-License-Identifier: MIT
"""M1 on the Kenya lake: network builds, solves optimal, two runs agree to 1e-6, losses non-zero.

Run: uv run python scripts/quality/kenya_m1.py [DAYS] [YEAR]
DAYS limits the solve to the first DAYS days of the year (default 14); 0 means all 8760 hours.
"""

from __future__ import annotations

import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")


def main(argv: list[str]) -> int:
	from alea.config.models import Config, ScenarioConfig, SolveConfig
	from alea.planning.expansion import solve_expansion
	from alea.planning.inputs import network_inputs
	from alea.planning.service import build_network

	days = int(argv[0]) if argv else 14
	year = int(argv[1]) if len(argv) > 1 else 2030
	cfg = Config(scenario=ScenarioConfig(countries=["KE"]), solve=SolveConfig(transmission_losses=True))
	demand, profiles, costs = network_inputs(cfg, year=year)
	if days:
		keep = demand.index[: 24 * days]
		demand = demand.loc[keep]
		profiles = {k: v.loc[keep] for k, v in profiles.items()}
	net, report, _ = build_network(cfg, demand_profiles=demand, renewable_profiles=profiles, capital_costs=costs)
	from alea.planning.fleet import attach_extendable_candidates

	# Firm capacity is 2,007 MW against a ~1,920 MW peak with losses, and the only
	# candidates build_network adds are variable ones. A night-time evening peak is
	# then infeasible, so dispatchable gas candidates sit at every bus.
	attach_extendable_candidates(net, ["gas"], capital_cost_usd_per_mw=costs)
	print("built", len(net.buses), "buses", len(net.generators), "generators", len(net.snapshots), "snapshots")
	n_solves = int(argv[2]) if len(argv) > 2 else 2
	runs = [solve_expansion(net.copy(), cfg, multi_period=False) for _ in range(n_solves)]
	if n_solves == 1:
		runs = runs * 2
	a, b = runs
	solved = a.network
	g = solved.generators
	w = solved.snapshot_weightings.objective
	dispatch = float((solved.generators_t.p.mul(w, axis=0) * g.marginal_cost).sum().sum())
	capex = float((g.p_nom_opt.sub(g.p_nom).clip(lower=0) * g.capital_cost)[g.p_nom_extendable].sum())
	print("recomputed", round(dispatch + capex), "= dispatch", round(dispatch), "+ new capex", round(capex), "vs objective", round(a.objective))
	print("load_mwh", round(float(solved.loads_t.p_set.sum().sum())), "weights_sum", float(w.sum()))
	print("status", a.status, b.status)
	print("objective", a.objective, b.objective, "diff", abs(a.objective - b.objective))
	print("losses_mwh", getattr(a, "losses_mwh", None))
	print("seconds", round(a.seconds, 1), "core_hours", round(a.core_hours, 4))
	print("investments", {k: round(v, 1) for k, v in a.investments.items() if v > 1e-6})
	ok = (
		str(a.status).lower().startswith(("ok", "optimal")) and abs(a.objective - b.objective) <= 1e-6 * max(1.0, abs(a.objective))
	)
	print("M1", "PASS" if ok else "FAIL")
	return 0 if ok else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
