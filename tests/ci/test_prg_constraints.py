# SPDX-License-Identifier: MIT
"""The equation-to-constraint half of the translation layer.

WHAT THESE TESTS ARE FOR. Of the library's 344 equations, 34 are
constraint-shaped and 21 of those bind (the batch-22 ``leq`` thresholds took
it from 24/16). The number is the finding, in both directions: a test
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
	"""Thirty-four of the library's 344 equations can constrain a solve.

	The denominator is the finding: 310 equations are identities, and folding
	them into the register would under-report what a solve is actually
	bound by. Pinned as a literal so a new inequality has to change this line
	to land. The counts moved 15/153/168 -> 24/182/206 when batch 20 landed:
	nine new inequalities, seven of them bound routes
	(``blended_finance_bound``, ``green_bond_bound``,
	``powertrain_stock_bound``, ``retraining_schedule_bound``,
	``steel_route_bound``, ``urban_heat_supply_bound``,
	``v2g_subset_bound``) and two post-solve checks
	(``carbon_finance_bound``, ``debt_mix_bound``) over derived finance
	and carbon-revenue shares. Batch 21 re-baked the graph to 222 equations:
	sixteen new equations, all identities. Batch 22 added 29 product
	identities and 10 ``leq`` thresholds, five of which bind
	(``cooking_clean_target_bound``, ``fpic_consent_bound``,
	``largest_loss_response_bound``, ``non_spinning_reserve_inside_margin``,
	``resettlement_share_bound``) and five of which are post-solve checks
	over derived results, so 24/198/222 -> 34/227/261. Batch 23's
	extensive-base layer added sixteen product identities and no inequality,
	so 34/227/261 -> 34/243/277. Batch 24's carbon-market layer added
	forty-three identities -- the carbon caps and volumes, the market shares
	against their bases, the subsidy and wheeling spends, the employment
	attainment ratios -- and no inequality, so 34/243/277 -> 34/286/320.
	Batch 25's gate-family coupling added thirteen more identities -- the
	insurance covers, the trade and sanctions costs, the permitted imports
	and transmission spend, the maintenance hours, the smart-metered
	population and the gated carbon volume -- and no inequality, so
	34/286/320 -> 34/299/333. Batch 26's adequacy-and-reserve layer added
	eleven more identities -- the reserve and regulation definitions, the
	spinning, non-spinning and planning-margin aliases, the SAIFI target
	alias, the voltage-support requirement, and the spare-capacity and
	transmission-loss-target definitions -- and no inequality, so
	34/299/333 -> 34/310/344. Batch 27's finance family added fourteen
	identities -- the four aliases, the project hurdle, the two microinsurance
	products, the ring-fenced asset, the transaction cost, the two risk
	charges, the premium pricing and its alias, the solvency capital, and the
	RAB roll-forward -- and one inequality, the LLCR covenant, so
	34/310/344 -> 35/324/359.

	Batches 28 to 34 took that to 64/461/525. The inequality count moved twice
	after batch 27, and neither move added a *bound* route: 35 -> 37 with
	batch 30, which stated two further thresholds, and 37 -> 64 with batches
	32 and 33, whose THRESHOLD class and unclassified remainder stated 22 and
	5 more. The bound count stayed at 34 throughout, which is the honest
	reading rather than a stall -- each new inequality is stated over a
	quantity the graph derives, so it is a post-solve check like the four
	batch 20 already carried, and ``test_the_bound_set_is_pinned_by_name``
	names the 21 that do bind. What grew is the register of what the graph
	*states*, not what the solve enforces.

	Per batch: 359 -> 417 (batch 28, +58 identities), -> 437 (batch 29, +20),
	-> 449 (batch 30, +10 identities and +2 thresholds), -> 477 (batch 31,
	+28), -> 499 (batch 32, +22 thresholds and no identity), -> 525 (batch
	33, +21 identities and +5 thresholds), unchanged for batch 34, which
	corrected one equation's body.

	525 -> 532 for batch 36, the whole move from one pack: six identity
	aliases and products from the contract and market layer, and one
	inequality, ``gate_closure_bound``. That bound is the first to join the
	*bound* set since batch 33, and it joins for the reason the classifier
	exists: both sides are declared quantities, so it reaches the optimiser
	rather than waiting for a post-solve check. The identity count is the
	total minus the inequalities and is asserted as such, so it cannot drift
	on its own.

	532 -> 539 for batch 37, the whole move from one pack: five equalities
	(two composites, two land aliases and the snapshot weight) and two
	inequalities (``temperature_target_bound`` and
	``rolling_horizon_window_bound``). Both bounds join the *bound* set,
	because both compare two declared quantities -- a warming against its
	ceiling, a look-ahead against the horizon -- and neither reads a node the
	graph derives. The two composite equalities are `unbound` post-solve
	checks for the opposite reason: their operands are declared dials the
	audit can evaluate but the network cannot supply as columns.

	539 -> 547 for batch 38: six equalities (four new fleet-level products
	over the retyped per-unit parameters, the settlement-risk security, and
	the age complement) and two inequalities
	(``workshop_capacity_workload_bound`` and ``loss_reduction_budget_bound``).
	Both bounds join the *bound* set: a workshop throughput against a
	maintenance workload and a spend against a budget are both declared
	quantities, so neither waits for a post-solve check. The six equalities
	are identities, which is why the identity count moves by six and the
	inequality count by two.

	547 -> 552 for batch 39: three equalities (two marine capex products and
	the solvency funds) and two inequalities (`ocgt_capex_ordering_bound` and
	`accumulation_exposure_bound`). Both bounds join the *bound* set -- every
	term is a settable scalar, so both reach the optimiser -- and the three
	equalities are identities, so the identity count moves by three and the
	inequality count by two.

	552 -> 553 for batch 40, and only one of the two is a new equation: the
	``remedy_period_bound`` inequality, which joins the *bound* set because
	both terms are settable scalars. The other body the batch corrected,
	``coal_price_per_mwh_definition``, was already in the identity class and
	stayed there, so the identity count is flat at 481 and the shaped count
	moves by exactly the one bound.

	553 -> 565 for batch 44, and all twelve are identities: the three
	fuel-energy definitions, the six pollutant totals, the fleet's
	concentration contribution, the total concentration, deaths and DALYs.
	Every one has a derived left-hand side and a right-hand side the graph
	supplies, so the identity count moves by twelve and the inequality count
	not at all.
	"""
	cov = coverage(graph)
	assert cov["constraint_shaped"] == 72
	assert cov["identities"] == 493
	assert cov["total"] == 565


def test_the_bound_set_is_pinned_by_name(graph: ParameterGraph):
	"""The thirty-four equations whose every term the network can supply.

	Six joined the original two when the generated batches were promoted --
	``reserve_margin_with_firm_vre`` is the firm-VRE variant of the original,
	``demand_shares_bound`` and the employment/CCS/electrification bounds are
	system inequalities over declared shares, and
	``retention_and_deductible_bound`` constrains the insurance module's own
	fractions. Seven more joined with
	batch 20 (``blended_finance_bound``, ``green_bond_bound``,
	``powertrain_stock_bound``, ``retraining_schedule_bound``,
	``steel_route_bound``, ``urban_heat_supply_bound``, ``v2g_subset_bound``),
	each over transport, steel, heat, V2G, retraining and finance shares the
	batch declares. Five more joined with batch 22's ``leq`` thresholds
	(``cooking_clean_target_bound``, ``fpic_consent_bound``,
	``largest_loss_response_bound``, ``non_spinning_reserve_inside_margin``,
	``resettlement_share_bound``). Each is added to a solve by
	``add_constraints`` generically, so the pin is the register of what
	constrains the build, spelled out, rather than a count.

	Thirteen more joined across batches 28 to 33, and all thirteen are
	*capacity* or *lead-time* bounds rather than share bounds: the storage
	and generation families the product remainder coupled
	(``compressed_air_capacity_bound``, ``fit_capacity_bound``,
	``flywheel_capacity_bound``, ``fusion_capacity_bound``,
	``gravity_storage_capacity_bound``, ``hydrogen_fuel_cell_capacity_bound``,
	``marine_otec_capacity_bound``, ``marine_tidal_capacity_bound``,
	``marine_wave_capacity_bound``, ``small_modular_reactor_capacity_bound``,
	``tidal_range_capacity_bound``) and two schedule bounds from the supply
	layer (``regulatory_lag_bound``, ``spare_parts_lead_time_bound``). Each
	compares a build variable or a declared horizon against another quantity
	the graph already carries, so every term is a network column or a settable
	scalar -- which is exactly the predicate the classifier tests, and why
	they moved the bound count while the 29 inequalities added alongside them
	did not. ``llcr_floor_bound`` is the counter-example worth keeping in
	view: batch 27's single inequality is stated over ``llcr_estimate``, which
	the graph derives, so it is a post-solve check and not in this list.

	``gate_closure_bound`` joined with batch 36 and is a *time* bound, not a
	capacity one: it compares the market's gate closure against the settlement
	period, both declared horizons. It is the first route in this list whose
	subject is a duration rather than a stock, which is worth naming because
	the classifier's predicate does not care -- it asks whether every term is
	a network column or a settable scalar, and both are.

	Two more joined with batch 38, and both are *workload* bounds rather than
	capacity or time ones: ``workshop_capacity_workload_bound`` puts a
	workshop's throughput above the fleet's maintenance events, and
	``loss_reduction_budget_bound`` puts loss-reduction spend below the
	line-upgrade budget. Neither bounded quantity is derived, which is the
	whole reason they bind -- the two sides are a dial and a declared limit,
	so the optimiser can hold them.

	Batch 39 added two more, and neither is a workload bound: one is an
	*ordering* between two capital costs (a peaker's capex per kW below the
	combined cycle's) and one is a *coverage* floor (an insurer's exposure
	above the loss it models at the 99.5th percentile). Both compare
	settable scalars, so both bind; the coverage floor is the one that
	required a retype, since `accumulation_risk` shipped dimensionless and
	the comparison was undecidable until it carried a currency.
	"""
	assert bound_routes(graph) == (
		"accumulation_exposure_bound",
		"blended_finance_bound",
		"carbon_budget_constraint",
		"compressed_air_capacity_bound",
		"cooking_clean_target_bound",
		"cost_of_equity_capped",
		"demand_shares_bound",
		"fit_capacity_bound",
		"flywheel_capacity_bound",
		"fpic_consent_bound",
		"fuel_ccs_adoption_bound",
		"fusion_capacity_bound",
		"gate_closure_bound",
		"gravity_storage_capacity_bound",
		"green_bond_bound",
		"hydrogen_fuel_cell_capacity_bound",
		"industrial_electrification_bound",
		"largest_loss_response_bound",
		"local_employment_targets_bound",
		"loss_reduction_budget_bound",
		"marine_otec_capacity_bound",
		"marine_tidal_capacity_bound",
		"marine_wave_capacity_bound",
		"non_spinning_reserve_inside_margin",
		"ocgt_capex_ordering_bound",
		"powertrain_stock_bound",
		"regulatory_lag_bound",
		"remedy_period_bound",
		"reserve_margin",
		"reserve_margin_with_firm_vre",
		"resettlement_share_bound",
		"retention_and_deductible_bound",
		"retraining_schedule_bound",
		"rolling_horizon_window_bound",
		"small_modular_reactor_capacity_bound",
		"spare_parts_lead_time_bound",
		"steel_route_bound",
		"temperature_target_bound",
		"tidal_range_capacity_bound",
		"urban_heat_supply_bound",
		"v2g_subset_bound",
		"workshop_capacity_workload_bound",
	)


def test_every_unbound_route_names_the_derived_quantity_it_cannot_read(
	graph: ParameterGraph,
):
	"""Each names a quantity the graph derives, so it is a post-solve check.

	The reason is the assertion. "Unbound" alone would be satisfied by a
	constraint that failed to build for any cause at all -- a typo in a symbol,
	a missing network column, a walker that gave up. Each route has to name the
	derived quantity it could not read, and that quantity has to actually be
	non-settable: a symbol the classifier could not find at all is a different
	defect wearing the same status.

	The four below are pinned by name because their *specific* unresolved set
	is the claim -- batch 20 wrote them and each has been re-read since.
	``water_availability_constraint`` changed its unresolved set from the two
	component flows to ``total_water_demand_m3`` when the constraint was
	rewritten to compare available supply against demand instead of comparing
	the demand flow against its own components, which restated the identity
	it was meant to test. The remaining twenty-six are covered by the
	universal predicate rather than enumerated, because a list that must grow
	with every threshold batch is a list that gets repinned without being
	read.
	"""
	expected = {
		"affordability_constraint": {"energy_burden"},
		"dscr_requirement": {"project_gearing_dscr"},
		"inertia_requirement": {"rocof_df_dt_hz_per_s"},
		"water_availability_constraint": {"total_water_demand_m3"},
	}
	by_id = {route.equation_id: route for route in routes(graph)}
	for equation_id, unresolved in expected.items():
		route = by_id[equation_id]
		assert route.status == "unbound", equation_id
		assert set(route.unresolved) == unresolved, equation_id
		# Every one of them is a *derived* node, which is the claim: not a
		# missing network column but a quantity with no column by construction.
		for name in unresolved:
			assert not graph.is_settable(name), (equation_id, name)

	# And the same claim, universally: whatever any unbound route names as
	# unresolved is a node the graph holds and does not let you set.
	unbound = [route for route in routes(graph) if route.status == "unbound"]
	assert len(unbound) == 30, [route.equation_id for route in unbound]
	for route in unbound:
		assert route.unresolved, route.equation_id
		for name in route.unresolved:
			assert name in graph.nodes, (route.equation_id, name)
			assert not graph.is_settable(name), (route.equation_id, name)


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
	constraints the optimiser must satisfy ``firm + vre * 0.35 >= 115`` and
	``firm + vre * 0.15 >= 115``, and with no firm capacity available the
	second is tighter: it builds 115 / 0.15 = 766.67 MW of solar.

	Both constraints bind, and that is the batch-43 finding made visible. The
	plain ``reserve_margin`` derates the variable fleet by its capacity
	factor, which is an annual energy ratio; ``reserve_margin_with_firm_vre``
	derates it by the capacity credit, which is the share reliably available
	at the peak. The credit is smaller, so its requirement is the one the
	build must meet, and the energy-ratio margin is satisfied as a
	consequence. Before batch 43 the two equations were byte-identical, so
	this test's expected 328.57 was the answer for either and a solver
	carrying "the firm-VRE margin" was carrying the energy-ratio one.
	"""
	params = {
		"reserve_margin_min": 0.15,
		"capacity_factor": 0.35,
		"vre_capacity_credit": 0.15,
	}

	baseline = _network(coal_marginal=100.0, coal_capital=1000.0)
	baseline.optimize(solver_name="highs", log_to_console=False)
	assert baseline.generators.at["solar", "p_nom_opt"] == pytest.approx(
		100.0, rel=1e-4
	)

	constrained, report = _solve(
		_network(coal_marginal=100.0, coal_capital=1000.0), params
	)
	assert "reserve_margin" in report.added
	assert "reserve_margin_with_firm_vre" in report.added
	assert constrained.generators.at["solar", "p_nom_opt"] == pytest.approx(
		115.0 / 0.15, rel=1e-4
	)
	# The energy-ratio margin is met, but by a build it did not set.
	assert constrained.generators.at["solar", "p_nom_opt"] > 115.0 / 0.35


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
