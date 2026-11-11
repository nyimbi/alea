"""M1's second and third clauses: two solves agree, losses are non-zero, cost is in core-hours."""

from __future__ import annotations

import pandas as pd
import pypsa

from alea.config.models import Config, ScenarioConfig, SolveConfig
from alea.planning.dispatch import check_energy_balance
from alea.planning.expansion import solve_expansion

CONFIG = Config(scenario=ScenarioConfig(countries=["KE"]))


def _expandable(extra_gen: bool = False) -> pypsa.Network:
	n = pypsa.Network()
	n.add("Bus", "north", v_nom=132.0)
	n.add("Bus", "south", v_nom=132.0)
	n.add("Line", "ns", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=200.0)
	n.add("Generator", "coal", bus="north", carrier="coal", p_nom_extendable=True, capital_cost=80_000.0, marginal_cost=30.0)
	if extra_gen:
		n.add("Generator", "gas", bus="south", carrier="gas", p_nom_extendable=True, capital_cost=60_000.0, marginal_cost=90.0)
	n.add("Load", "load", bus="south", p_set=50.0)
	n.set_snapshots(list(pd.date_range("2030-01-01", periods=24, freq="h")))
	return n


def test_two_solves_of_the_same_network_agree_exactly():
	a = solve_expansion(_expandable(True), CONFIG)
	b = solve_expansion(_expandable(True), CONFIG)
	assert a.objective == b.objective
	assert a.investments == b.investments


def test_losses_are_non_zero_and_a_lossless_solve_is_cheaper():
	lossy = solve_expansion(_expandable(), CONFIG)
	assert check_energy_balance(lossy.network)["losses_mwh"] > 1.0
	lossless = solve_expansion(
		_expandable(), Config(scenario=ScenarioConfig(countries=["KE"]), solve=SolveConfig(transmission_losses=False)),
		multi_period=False,
	)
	assert lossless.objective < lossy.objective


def test_core_hours_is_wall_time_times_threads():
	r = solve_expansion(_expandable(), CONFIG)
	assert r.threads == 1 and r.seconds > 0
	assert r.core_hours == r.seconds / 3600.0
	assert r.as_dict()["core_hours"] == r.core_hours
	r.threads = 12
	assert r.core_hours == r.seconds * 12 / 3600.0
