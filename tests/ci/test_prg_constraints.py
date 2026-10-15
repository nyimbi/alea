# SPDX-License-Identifier: MIT
"""The equation-to-constraint half of the translation layer.

WHAT THESE TESTS ARE FOR. Of the library's 38 equations, six are inequalities
and two of those bind. The number is the finding, in both directions: a test
that only checked the two work would let a third appear unnoticed, and a test
that only checked the register would never learn whether the two constraints
actually move an optimiser. So the register is asserted as literals, and the
two bound equations are run through a real HiGHS solve and asserted on the
*decision variables they changed*.

WHY THE CONSTRAINT IS CHECKED BY SOLVING. ``reserve_margin`` is
``firm + vre * cf >= peak * (1 + margin)``. A test that asserted the linopy
expression was built would pass on a constraint added with the wrong sign, the
wrong side, or against the wrong generators. The check solves a fixture whose
cheapest feasible build violates the margin and reads ``p_nom_opt`` -- the
reserve margin's arithmetic is exact (115 / 0.35 = 328.57), so the assertion is
on a number the physics determines rather than on a shape.

WHY THE UNBOUND FOUR ARE ASSERTED AND NOT SKIPPED. Each names a quantity the
graph *derives* -- ``project_gearing_dscr``, ``rocof_df_dt_hz_per_s``,
``energy_burden``, ``cooling_water_demand_m3`` -- which only exists after a
solve. That is why they are post-solve checks and not constraints, and the
reason is the thing worth pinning: a future change that made one of them bind
by inventing a network column would be a modelling decision, and it should have
to change this test to land.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pypsa
import pytest

from alea.prg import load_graph
from alea.prg.constraints import (
	HOURS_PER_YEAR,
	SOURCES,
	add_constraints,
	bound_routes,
	coverage,
	routes,
)
from alea.prg.graph import ParameterGraph
from alea.registry.technologies import get_technology


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph()


def _network(
	*,
	coal_marginal: float = 0.01,
	coal_capital: float = 0.0,
	solar_capital: float = 1.0,
	load_mw: float = 100.0,
	fixed_coal: float = 0.0,
	fixed_solar: float = 0.0,
	hours: float = 2190.0,
) -> pypsa.Network:
	"""A two-generator, one-bus network that can carry both constraints.

	Four snapshots weighted at 2,190 hours each, so the modelled horizon is
	exactly 8,760 hours -- one year. That is what makes the carbon budget's
	annualisation a no-op here and lets the assertions be on the physics rather
	than on the conversion factor. The reserve margin does not care.

	Dispatch economics and the margin are kept on *separate* knobs, because a
	fixture where the cheap unit is also the one the margin wants cannot tell
	"the constraint moved the build" from "the objective did". So ``solar``
	always dispatches at zero marginal cost and ``coal``'s marginal cost is the
	only thing deciding who serves load: with ``coal_marginal`` high the
	baseline builds solar for the load alone, and with it near zero the
	baseline runs coal and the margin is the only reason to build anything.
	"""
	network = pypsa.Network()
	network.set_snapshots(pd.date_range("2030-01-01", periods=4, freq="h"))
	network.snapshot_weightings.loc[:, :] = hours
	network.add("Bus", "b1", carrier="AC")
	network.add(
		"Generator",
		"coal",
		bus="b1",
		carrier="coal",
		p_nom=fixed_coal,
		p_nom_extendable=fixed_coal == 0.0,
		marginal_cost=coal_marginal,
		capital_cost=coal_capital,
	)
	network.add(
		"Generator",
		"solar",
		bus="b1",
		carrier="solar",
		p_nom=fixed_solar,
		p_nom_extendable=fixed_solar == 0.0,
		marginal_cost=0.0,
		capital_cost=solar_capital,
	)
	network.add("Load", "load", bus="b1", p_set=load_mw)
	return network


def _solve(
	network: pypsa.Network, params: dict[str, float]
) -> tuple[pypsa.Network, Any]:
	"""Solve under the PRG's constraints, and hand back what was added.

	The report is returned rather than discarded because a test that only read
	``p_nom_opt`` would pass on a network where the constraint silently failed
	to build and the optimiser happened to land on the same number. The report
	is how a test says "this bound" as well as "this moved".
	"""
	report: list[Any] = []

	def extra_functionality(net: pypsa.Network, _snapshots: Any = None) -> None:
		report.append(add_constraints(net, params))

	network.optimize(
		extra_functionality=extra_functionality,
		solver_name="highs",
		log_to_console=False,
	)
	return network, report[0]


# --------------------------------------------------------------------------
# The register
# --------------------------------------------------------------------------


def test_the_constraint_shaped_equations_are_exactly_the_inequalities(
	graph: ParameterGraph,
):
	"""Six of the library's 38 equations can constrain a solve.

	The denominator is the finding: 32 equations are identities, and folding
	them into the register would report "2 of 38" for a library where the
	honest figure is 2 of 6. Pinned as a literal so a new inequality has to
	change this line to land. The identity count moved 31 -> 32 when
	``firm_capacity_definition`` landed: an equation that derives the firm
	fleet from the optimiser's own capacity decisions is a definition, not a
	seventh boundary.
	"""
	cov = coverage(graph)
	assert cov["constraint_shaped"] == 6
	assert cov["identities"] == 32
	assert cov["total"] == 38


def test_the_bound_set_is_pinned_by_name(graph: ParameterGraph):
	"""The two equations whose every term the network can supply."""
	assert bound_routes(graph) == ("carbon_budget_constraint", "reserve_margin")


def test_the_unbound_four_are_unbound_for_one_reason(graph: ParameterGraph):
	"""Each names a quantity the graph derives, so it is a post-solve check.

	The reason is the assertion. "Unbound" alone would be satisfied by a
	constraint that failed to build for any cause at all -- a typo in a symbol,
	a missing network column, a walker that gave up. Each route has to name the
	derived quantity it could not read.
	"""
	expected = {
		"affordability_constraint": {"energy_burden"},
		"dscr_requirement": {"project_gearing_dscr"},
		"inertia_requirement": {"rocof_df_dt_hz_per_s"},
		"water_availability_constraint": {
			"cooling_water_demand_m3",
			"hydrogen_water_demand_m3",
		},
	}
	by_id = {route.equation_id: route for route in routes(graph)}
	for equation_id, unresolved in expected.items():
		route = by_id[equation_id]
		assert route.status == "unbound", equation_id
		assert set(route.unresolved) == unresolved, equation_id
		# Every one of them is a *derived* node, which is the claim: not a
		# missing network column but a quantity with no column by construction.
		for name in unresolved:
			assert not graph.is_settable(name), name


def test_every_declared_source_names_a_real_symbol(graph: ParameterGraph):
	"""A source for a symbol the graph does not hold is a mapping gone stale.

	The same discipline ``translate.translations`` applies to engine fields: a
	declaration is checked against the model it names, so a rename breaks at
	the declaration rather than silently dropping a term from a constraint.
	"""
	for source in SOURCES:
		assert source.symbol in graph.nodes, source.symbol
		assert source.note, f"{source.symbol} has no stated assumption"


# --------------------------------------------------------------------------
# The constraints, against a real solve
# --------------------------------------------------------------------------


def test_the_reserve_margin_binds_and_moves_the_build():
	"""The margin forces firm capacity the cheapest build would not buy.

	With coal expensive to run, the unconstrained optimum builds solar for the
	load alone -- 100 MW, no more -- and the margin is violated. With the
	constraint the optimiser must satisfy ``firm + vre * 0.35 >= 115``, and
	with no firm capacity available it builds 115 / 0.35 = 328.57 MW of solar.
	The number is the physics, not a shape.
	"""
	params = {"reserve_margin_min": 0.15, "capacity_factor": 0.35}

	baseline = _network(coal_marginal=100.0, coal_capital=1000.0)
	baseline.optimize(solver_name="highs", log_to_console=False)
	assert baseline.generators.at["solar", "p_nom_opt"] == pytest.approx(
		100.0, rel=1e-4
	)

	constrained, report = _solve(
		_network(coal_marginal=100.0, coal_capital=1000.0), params
	)
	assert "reserve_margin" in report.added
	assert constrained.generators.at["solar", "p_nom_opt"] == pytest.approx(
		115.0 / 0.35, rel=1e-4
	)


def test_the_reserve_margin_counts_a_fixed_unit_as_a_constant():
	"""A non-extendable unit is data, and enters the constraint as a number.

	With 200 MW of fixed coal the margin is already met, so the optimiser
	builds solar only for the load -- 100 MW. A reader that treated the fixed
	unit as a decision variable would have left it free to shrink to zero and
	built 328.57 MW of solar instead. The two outcomes are far apart, which is
	what makes this a test.
	"""
	constrained, report = _solve(
		_network(fixed_coal=200.0, coal_marginal=100.0),
		{"reserve_margin_min": 0.15, "capacity_factor": 0.35},
	)
	assert "reserve_margin" in report.added
	assert constrained.generators.at["solar", "p_nom_opt"] == pytest.approx(
		100.0, rel=1e-4
	)
	# And the fixed unit stayed where it was put.
	assert constrained.generators.at["coal", "p_nom"] == pytest.approx(200.0)


def test_the_carbon_budget_binds_and_is_annualised():
	"""A tight budget caps emissions at the budget, exactly.

	Coal at 0.01 USD/MWh is cheap and dirty, solar at 1e6 USD/MW is clean and
	ruinous, so the unconstrained optimum runs coal and emits 0.83 Mt. With a
	0.5 Mt budget the optimiser has to build clean capacity, and the emissions
	land *on* the budget -- which is the assertion, because a constraint added
	with the wrong unit chain would land on a thousandth of it and still look
	like it bound.
	"""
	params = {"carbon_budget_mtco2": 0.5, "horizon_years": 1.0}
	network = _network(coal_marginal=0.01, coal_capital=0.0, solar_capital=1e6)
	constrained, report = _solve(network, params)
	assert "carbon_budget_constraint" in report.added

	dispatch = network.generators_t.p.sum() * 2190.0
	emissions_mt = sum(
		dispatch[name] * get_technology(network.generators.at[name, "carrier"]).co2_t_per_mwh
		for name in network.generators.index
	) / 1e6
	assert emissions_mt == pytest.approx(0.5, rel=1e-3)
	# And it built clean capacity to get there.
	assert network.generators.at["solar", "p_nom_opt"] > 0.0


def test_the_horizon_is_one_year_on_a_network_that_spans_one():
	"""The annualisation factor is 1 when the modelled hours are 8,760.

	The unit chain here is where this can go wrong by a factor of a thousand,
	and the fixture is built so that the honest conversion is the identity --
	which makes the emissions assertion above a test of the constraint rather
	than of the conversion. This pins the other end: the constant is the year
	the graph's own ``capacity_factor`` is defined against.
	"""
	assert HOURS_PER_YEAR == 8760.0


def test_the_carbon_budget_annualises_a_short_horizon():
	"""A two-hour network spends a two-hour slice of a per-year budget.

	The fixture above spans exactly 8,760 hours, so the annualisation factor
	there is 1 and a constraint that dropped it entirely would pass every
	assertion. That is not a hypothetical: removing the factor is the canary
	that *did not fail*, and it is why this test exists. A network modelling
	two hours must be allowed 2/8760 of the annual budget, so the same budget
	permits 4,380 times more emissions per modelled hour than on a full-year
	fixture -- and the coal unit, which the full-year fixture has to cap, here
	clears the budget untouched.

	The assertion is on the emissions the solve actually produces, not on the
	factor: a constraint that annualised twice, or not at all, lands somewhere
	other than the budget.
	"""
	# Two snapshots of one hour each: a 2-hour modelled horizon.
	network = _network(
		coal_marginal=0.01,
		coal_capital=0.0,
		solar_capital=1e6,
		hours=1.0,
	)
	network.set_snapshots(pd.date_range("2030-01-01", periods=2, freq="h"))
	network.snapshot_weightings.loc[:, :] = 1.0

	# A budget the full-year fixture had to respect, on a horizon 4,380x
	# shorter: the permitted emissions scale with the horizon, so this budget
	# no longer bites and the cheap dirty unit serves the load.
	_, report = _solve(network, {"carbon_budget_mtco2": 0.5, "horizon_years": 1.0})
	assert "carbon_budget_constraint" in report.added

	dispatch = network.generators_t.p.sum() * 1.0
	emissions_mt = sum(
		dispatch[name] * get_technology(network.generators.at[name, "carrier"]).co2_t_per_mwh
		for name in network.generators.index
	) / 1e6
	# Two hours at 100 MW of coal: 200 MWh * 0.95 t/MWh = 190 t = 0.00019 Mt,
	# well under the 0.5 Mt budget once it is pro-rated to the horizon. A
	# constraint that skipped the annualisation would have compared the raw
	# 0.00019 Mt figure against 0.5 directly and also passed -- which is why
	# the *binding* case below is the one that discriminates.
	assert emissions_mt < 0.5

	# Now the discriminating case: a budget small enough to bite on a 2-hour
	# horizon. Pro-rated, the permitted total is 0.5 * (2 / 8760) = 1.14e-4 Mt
	# = 114 t. Coal alone would emit 190 t, so the optimiser must back off.
	tight = _network(
		coal_marginal=0.01, coal_capital=0.0, solar_capital=1e6, hours=1.0
	)
	tight.set_snapshots(pd.date_range("2030-01-01", periods=2, freq="h"))
	tight.snapshot_weightings.loc[:, :] = 1.0
	_solve(tight, {"carbon_budget_mtco2": 0.000114, "horizon_years": 1.0})

	tight_dispatch = tight.generators_t.p.sum() * 1.0
	tight_mt = sum(
		tight_dispatch[name]
		* get_technology(tight.generators.at[name, "carrier"]).co2_t_per_mwh
		for name in tight.generators.index
	) / 1e6
	annualised = tight_mt * (HOURS_PER_YEAR / 2.0)
	assert annualised == pytest.approx(0.000114, rel=1e-2)


def test_a_fully_data_equation_is_refused_rather_than_added():
	"""A constraint with no decision variable in it is not a constraint.

	On a fleet with no extendable unit, ``Generator-p_nom`` is absent from the
	model and every term of the reserve margin folds to a number: 200 against
	115. Adding ``200 >= 115`` would put a row in the model that trivially
	holds -- and on a fleet that missed the margin it would make the model
	infeasible with nothing in the report to say the infeasibility came from a
	*checked* quantity rather than a decision. The route is returned as skipped
	instead, and the reason names the numbers.

	The carbon budget is *not* the example here, and that is the point: its
	emissions term reads ``Generator-p``, which exists on every network the
	optimiser builds, so it stays a constraint even on a fixed fleet.
	"""
	network = _network(fixed_coal=200.0, fixed_solar=10.0, coal_marginal=100.0)
	network.optimize.create_model()
	report = add_constraints(
		network, {"reserve_margin_min": 0.15, "capacity_factor": 0.35}
	)

	skipped = {route.equation_id: route for route in report.skipped}
	assert "reserve_margin" in skipped
	reason = skipped["reserve_margin"].reason
	assert "data" in reason
	# The numbers are in the reason, so a reader can see which side won without
	# re-deriving the arithmetic: 200 MW of fixed coal plus 10 MW of VRE
	# derated at 0.35 is 203.5, against a requirement of 100 * 1.15 = 115.
	assert "203.5" in reason
	assert "114.99" in reason
	# And the budget, which does name a dispatch variable, still bound.
	assert "carbon_budget_constraint" in report.added
