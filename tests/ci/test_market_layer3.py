# SPDX-License-Identifier: MIT
"""Layer 3 gates: the exit criteria of 06-layer3 §10 that nothing pinned.

Two halves. The first four tests are the defects commit 4785249 fixed: a
parameter or field that read as a capability and did nothing. A caller passing
``period="YE"`` got the whole series; a HEDGE strategy's forward price was never
read; ``clear_scenario`` accepted ``force`` and ignored it;
``fuel_price_from_config`` always returned ``None`` while sitting in ``__all__``.

The rest are the Layer 3 exit criteria (06-layer3 §10) that had no gate at all:
a hand-computed Kenya merit-order stack, zonal congestion on a congested
fixture, the competitive cross-check against Layer 1's marginal price, capture
prices for a Kenya solar/wind fixture, the analytic VaR cross-check, a
hand-computed bankability fixture, and the PPA FX-rate record. Each fails
without the behaviour it asserts; where a test could not be made to fail it says
so in its own docstring rather than counting as coverage.

Every test here reads a number the way a report would, and asserts the number,
not the shape of the call. A gate that only checks a function returned is a gate
on the function existing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.market import fuel
from alea.market.agents import Agent, BiddingUnit
from alea.market.bankability import bankability, irr, npv
from alea.market.capture import capture_by_technology
from alea.market.clearing import clear_market, clear_market_zonal
from alea.market.ppa import ppa_benchmark, tenor_capture_price
from alea.market.risk import normal_var_check, value_at_risk
from alea.market.service import clear_scenario
from alea.market.strategy import Strategy, StrategyKind
from alea.market.views import Bid, FxRate, Interface


def _two_year_solar() -> tuple[pd.DataFrame, pd.Series]:
	"""Two years, hourly. 2021 prices at 100, 2022 at 50; output doubles."""
	index = pd.date_range("2021-01-01", "2022-12-31 23:00", freq="h")
	price = pd.Series(np.where(index.year == 2021, 100.0, 50.0), index=index)
	generation = pd.DataFrame(
		{"solar": np.where(index.year == 2021, 10.0, 20.0)},
		index=index,
	)
	return generation, price


def test_capture_without_a_period_is_one_result_per_carrier():
	captures = capture_by_technology(*_two_year_solar())
	assert len(captures["solar"]) == 1
	assert captures["solar"][0].capture_price_usd_per_mwh is not None


def test_capture_with_a_period_resamples_within_each_period():
	"""The defect: ``period`` was accepted and never read."""
	generation, price = _two_year_solar()
	captures = capture_by_technology(generation, price, period="YE")

	solar = captures["solar"]
	assert len(solar) == 2, "period='YE' over two years must yield two periods"
	# Each period's capture is that period's constant price. If the resample
	# were a no-op the first entry would carry the whole-series blend and
	# neither number would land on its own year.
	assert solar[0].capture_price_usd_per_mwh == pytest.approx(100.0)
	assert solar[1].capture_price_usd_per_mwh == pytest.approx(50.0)
	assert solar[0].period_start is not None and solar[0].period_start.year == 2021
	assert solar[1].period_start is not None and solar[1].period_start.year == 2022
	# Generation is summed per period, not over the series.
	assert solar[0].generation_mwh == pytest.approx(10.0 * 8760)
	assert solar[1].generation_mwh == pytest.approx(20.0 * 8760)


def test_a_period_without_a_datetime_index_is_refused():
	generation, price = _two_year_solar()
	generation.index = pd.RangeIndex(len(generation))
	price.index = generation.index
	with pytest.raises(AssertionError, match="DatetimeIndex"):
		capture_by_technology(generation, price, period="YE")


# --------------------------------------------------------------------------
# strategy.HEDGE
# --------------------------------------------------------------------------


def test_a_hedge_needs_a_forward_price():
	"""A HEDGE with no forward price would leave the field decorative."""
	with pytest.raises(ValueError, match="forward_price_usd_per_mwh"):
		Strategy(kind=StrategyKind.HEDGE, contract_cover_fraction=0.5)


def test_a_hedge_with_no_cover_bids_marginal_cost():
	strategy = Strategy(
		kind=StrategyKind.HEDGE,
		contract_cover_fraction=0.0,
		forward_price_usd_per_mwh=30.0,
	)
	assert strategy.bid_price(40.0) == pytest.approx(40.0)


def test_the_forward_price_is_read_by_the_hedge_bid():
	"""The defect: ``benchmark_capture_price_usd_per_mwh`` was never read.

	Banked revenue on the covered volume lowers the effective cost of the
	uncovered volume: bid = cost - cover/(1-cover) * forward.
	"""
	cheap_forward = Strategy(
		kind=StrategyKind.HEDGE,
		contract_cover_fraction=0.5,
		forward_price_usd_per_mwh=20.0,
	)
	dear_forward = Strategy(
		kind=StrategyKind.HEDGE,
		contract_cover_fraction=0.5,
		forward_price_usd_per_mwh=35.0,
	)
	assert cheap_forward.bid_price(40.0) == pytest.approx(40.0 - 20.0)
	assert dear_forward.bid_price(40.0) == pytest.approx(40.0 - 35.0)
	# Same cost and cover, different forward price, different bid: the field is
	# load-bearing rather than present.
	assert cheap_forward.bid_price(40.0) != dear_forward.bid_price(40.0)


def test_a_hedge_bid_never_goes_negative():
	strategy = Strategy(
		kind=StrategyKind.HEDGE,
		contract_cover_fraction=0.5,
		forward_price_usd_per_mwh=100.0,
	)
	assert strategy.bid_price(10.0) == 0.0


def test_full_cover_bids_zero():
	strategy = Strategy(
		kind=StrategyKind.HEDGE,
		contract_cover_fraction=1.0,
		forward_price_usd_per_mwh=30.0,
	)
	assert strategy.bid_price(40.0) == 0.0


# --------------------------------------------------------------------------
# service.clear_scenario force
# --------------------------------------------------------------------------


def _fleet(cost: float) -> list[Agent]:
	return [
		Agent(
			unit=BiddingUnit(
				unit_id="u1",
				carrier="ccgt",
				capacity_mw=100.0,
				marginal_cost_usd_per_mwh=cost,
			),
		)
	]


def test_clear_scenario_force_reclears_a_current_artefact(tmp_path: Path):
	"""The defect: ``force`` was declared and never read.

	With the artefact current for the declared inputs, an unforced call returns
	the recorded clearing price even though the fleet changed; ``force=True``
	re-clears and returns the new one.
	"""
	out = tmp_path / "clearing.json"
	inputs = ["inputs:v1"]

	first = clear_scenario(
		_fleet(10.0),
		50.0,
		out,
		value_of_lost_load_usd_per_mwh=10_000.0,
		inputs=inputs,
	)
	assert first.clearing_price_usd_per_mwh == pytest.approx(10.0)

	# A different fleet under the same declared inputs. Without force the
	# artefact is current, so the recorded result stands.
	skipped = clear_scenario(
		_fleet(50.0),
		50.0,
		out,
		value_of_lost_load_usd_per_mwh=10_000.0,
		inputs=inputs,
	)
	assert skipped.clearing_price_usd_per_mwh == pytest.approx(10.0)

	forced = clear_scenario(
		_fleet(50.0),
		50.0,
		out,
		value_of_lost_load_usd_per_mwh=10_000.0,
		inputs=inputs,
		force=True,
	)
	assert forced.clearing_price_usd_per_mwh == pytest.approx(50.0)


# --------------------------------------------------------------------------
# fuel.fuel_price_from_config
# --------------------------------------------------------------------------


def test_the_fabricated_config_accessor_is_gone():
	"""The defect: a public accessor whose body was ``return None``."""
	assert "fuel_price_from_config" not in fuel.__all__
	assert not hasattr(fuel, "fuel_price_from_config")


def test_fuel_price_series_records_that_the_config_has_no_price():
	"""The absence is documented on the function that does carry prices."""
	doc = fuel.fuel_price_series.__doc__ or ""
	assert "no fuel price" in doc


# --------------------------------------------------------------------------
# ZonalZoneResult: a zone in blackout is not a zone with zero unserved energy
# --------------------------------------------------------------------------


def test_a_zone_in_blackout_satisfies_its_own_balance():
	"""``unserved_mwh`` is demand the zone could not meet, not a supply term.

	The validator used to require ``generation + net_import - unserved == demand``
	while ``_zone_results`` sets ``net_import = demand - generation - unserved``.
	Substituting the constructor into the check gives ``unserved == 0``, so the
	schema could not represent a zone in blackout at all -- and every fixture
	had ``unserved = 0``, which is why no test noticed.
	"""
	from alea.market.views import ZonalZoneResult

	# 40 MW of demand, 25 MW generated, 5 MW imported, 10 MW unserved.
	zone = ZonalZoneResult(
		zone_id="KE",
		demand_mw=40.0,
		generation_mw=25.0,
		net_import_mw=5.0,
		price_usd_per_mwh=90.0,
		unserved_mwh=10.0,
	)
	assert zone.unserved_mwh == 10.0


def test_a_zone_whose_unserved_energy_is_unaccounted_for_is_refused():
	"""The balance is still enforced; it is the sign that changed."""
	from alea.market.views import ZonalZoneResult

	with pytest.raises(ValueError, match="not demand"):
		ZonalZoneResult(
			zone_id="KE",
			demand_mw=40.0,
			generation_mw=25.0,
			net_import_mw=0.0,  # 25 + 0 + 10 = 35, not 40
			price_usd_per_mwh=90.0,
			unserved_mwh=10.0,
		)


# --------------------------------------------------------------------------
# Exit criterion 1: a hand-computed Kenya merit-order stack
# --------------------------------------------------------------------------


def test_kenya_merit_order_clearing_matches_a_hand_computed_stack():
	"""A five-unit Kenya-like stack, dispatched by hand.

	Stack (price, MW): geothermal 10/100, hydro 15/80, coal 40/150, gas 70/120,
	oil 120/60. Demand 260 MW. Merit order takes all of geothermal (100, cum
	100), all of hydro (80, cum 180), then 80 of coal (cum 260). The marginal
	unit is coal, so the uniform price is 40 and gas and oil are not dispatched.
	"""
	bids = [
		Bid(unit_id="geothermal", quantity_mw=100.0, price_usd_per_mwh=10.0),
		Bid(unit_id="hydro", quantity_mw=80.0, price_usd_per_mwh=15.0),
		Bid(unit_id="coal", quantity_mw=150.0, price_usd_per_mwh=40.0),
		Bid(unit_id="gas", quantity_mw=120.0, price_usd_per_mwh=70.0),
		Bid(unit_id="oil", quantity_mw=60.0, price_usd_per_mwh=120.0),
	]
	result = clear_market(bids, 260.0, value_of_lost_load_usd_per_mwh=10_000.0)

	assert result.clearing_price_usd_per_mwh == pytest.approx(40.0)
	assert result.dispatched == {
		"geothermal": pytest.approx(100.0),
		"hydro": pytest.approx(80.0),
		"coal": pytest.approx(80.0),
	}
	assert result.unserved_mwh == pytest.approx(0.0)
	assert result.demand_met


def test_a_short_stack_clears_at_voll_and_reports_the_shortfall():
	"""Exit criterion 1's other half: a stack that cannot meet demand.

	Removing 200 MW of capacity from a 260 MW demand leaves 60 MW unserved, and
	the price is VoLL, not the marginal bid -- the last MWh served cost VoLL to
	avoid shedding it. The clearing price of a short stack quoted without the
	shortfall is a price for a system in blackout.
	"""
	bids = [
		Bid(unit_id="geothermal", quantity_mw=100.0, price_usd_per_mwh=10.0),
		Bid(unit_id="hydro", quantity_mw=80.0, price_usd_per_mwh=15.0),
	]
	result = clear_market(bids, 260.0, value_of_lost_load_usd_per_mwh=10_000.0)

	assert result.unserved_mwh == pytest.approx(80.0)
	assert result.clearing_price_usd_per_mwh == pytest.approx(10_000.0)
	assert result.shortage_price_usd_per_mwh == pytest.approx(10_000.0)
	assert not result.demand_met


def test_a_price_tie_breaks_on_unit_id_not_list_order():
	"""AD-8: two units at the same price must dispatch the same way every run."""
	alpha = Bid(unit_id="U-ALPHA", quantity_mw=60.0, price_usd_per_mwh=50.0)
	beta = Bid(unit_id="U-BETA", quantity_mw=60.0, price_usd_per_mwh=50.0)
	# BETA listed first; demand 60 MW. The lexicographically smaller unit wins.
	result = clear_market([beta, alpha], 60.0, value_of_lost_load_usd_per_mwh=10_000.0)
	assert result.dispatched == {"U-ALPHA": pytest.approx(60.0)}


# --------------------------------------------------------------------------
# Exit criterion 2: zonal clearing produces congestion on a congested fixture
# --------------------------------------------------------------------------


def _three_zone_path() -> tuple[dict[str, list[Bid]], dict[str, float], list[Interface]]:
	"""A path A-B-C, cheap at one end and dear at the other.

	Both corridors have a 60 MW limit, so the economic trade from A to C exceeds
	either one and both bind. This is the fixture on which the old
	``_split_area`` failed to converge -- it stranded C with A.
	"""
	bids = {
		"A": [Bid(unit_id="a1", quantity_mw=200.0, price_usd_per_mwh=10.0, zone_id="A")],
		"B": [Bid(unit_id="b1", quantity_mw=200.0, price_usd_per_mwh=40.0, zone_id="B")],
		"C": [Bid(unit_id="c1", quantity_mw=200.0, price_usd_per_mwh=80.0, zone_id="C")],
	}
	demand = {"A": 50.0, "B": 100.0, "C": 150.0}
	interfaces = [
		Interface(from_zone="A", to_zone="B", limit_mw=60.0, susceptance=1.0),
		Interface(from_zone="B", to_zone="C", limit_mw=60.0, susceptance=1.0),
	]
	return bids, demand, interfaces


def test_zonal_clearing_produces_congestion_on_a_congested_path():
	"""Exit criterion 2. Both corridors bind; three zones, three prices."""
	bids, demand, interfaces = _three_zone_path()
	result = clear_market_zonal(
		bids, demand, interfaces, value_of_lost_load_usd_per_mwh=10_000.0
	)

	assert result.converged, "the split iteration did not converge on a path graph"
	assert result.is_split
	assert result.zones["A"].price_usd_per_mwh == pytest.approx(10.0)
	assert result.zones["B"].price_usd_per_mwh == pytest.approx(40.0)
	assert result.zones["C"].price_usd_per_mwh == pytest.approx(80.0)
	assert len(result.congested_interfaces) == 2
	# Each corridor carries exactly its limit, from the cheap end to the dear.
	for flow in result.interfaces:
		assert abs(flow.flow_mw) == pytest.approx(60.0)
	assert result.congestion_rent_usd > 0.0


def test_an_uncongested_zonal_market_clears_at_one_price():
	"""The control: ample corridors must not manufacture a split or a rent."""
	bids = {
		"A": [Bid(unit_id="a1", quantity_mw=100.0, price_usd_per_mwh=10.0, zone_id="A")],
		"B": [Bid(unit_id="b1", quantity_mw=100.0, price_usd_per_mwh=50.0, zone_id="B")],
	}
	result = clear_market_zonal(
		bids,
		{"A": 20.0, "B": 30.0},
		[Interface(from_zone="A", to_zone="B", limit_mw=500.0, susceptance=1.0)],
		value_of_lost_load_usd_per_mwh=10_000.0,
	)
	assert not result.is_split
	assert result.system_price_usd_per_mwh == pytest.approx(10.0)
	assert result.congestion_rent_usd == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Exit criterion 3: competitive strategy reproduces Layer 1's marginal price
# --------------------------------------------------------------------------


def test_a_competitive_clearing_reproduces_the_marginal_units_cost():
	"""Exit criterion 3, the integration gate, on a single-bus fixture.

	A merit-order stack clears at the marginal unit's bid. With every agent
	competitive the bid *is* the marginal cost, so the clearing price equals the
	marginal unit's cost -- the same number Layer 1's LP dual returns on the same
	dispatch (verified against pypsa in this repo's own probe: a 50 MW cheap
	unit, a 50 MW dear unit and 70 MW of load give an LMP of 30, the dear unit's
	marginal_cost). If the two disagreed, a price forecast built on the market
	layer would be measuring the discrepancy, not the market.

	The markup control is the point: with the same fleet marked up 50%, the
	clearing price moves, so the test is not passing on a coincidence.
	"""
	units = [
		BiddingUnit(unit_id="cheap", carrier="geothermal", capacity_mw=50.0, marginal_cost_usd_per_mwh=10.0),
		BiddingUnit(unit_id="dear", carrier="gas", capacity_mw=50.0, marginal_cost_usd_per_mwh=30.0),
	]
	competitive = [Agent(unit=unit) for unit in units]
	result = clear_market(
		[agent.bid() for agent in competitive], 70.0, value_of_lost_load_usd_per_mwh=10_000.0
	)
	assert result.clearing_price_usd_per_mwh == pytest.approx(30.0)

	marked_up = [
		Agent(unit=unit, strategy=Strategy.from_markup(0.5)) for unit in units
	]
	result_up = clear_market(
		[agent.bid() for agent in marked_up], 70.0, value_of_lost_load_usd_per_mwh=10_000.0
	)
	assert result_up.clearing_price_usd_per_mwh == pytest.approx(45.0)
	assert result_up.clearing_price_usd_per_mwh != result.clearing_price_usd_per_mwh


# --------------------------------------------------------------------------
# Exit criterion 4: capture prices for a Kenya solar/wind fixture
# --------------------------------------------------------------------------


def _kenya_solar_wind() -> tuple[pd.DataFrame, pd.Series]:
	"""Two days, hourly. Solar generates midday, wind overnight.

	The price peaks in the evening (19:00), so both VRE carriers generate off
	peak and both capture below the time-weighted price -- the cannibalisation
	the capture price exists to measure.
	"""
	index = pd.date_range("2030-01-01", periods=48, freq="h")
	hour = index.hour.to_numpy()
	price = pd.Series(20.0 + 40.0 * np.exp(-((hour - 19) ** 2) / 10.0), index=index)
	generation = pd.DataFrame(
		{
			"solar": np.where((hour >= 10) & (hour <= 15), 50.0, 0.0),
			"wind": np.where((hour >= 22) | (hour <= 5), 30.0, 0.0),
		},
		index=index,
	)
	return generation, price


def test_kenya_solar_and_wind_capture_prices_are_computed():
	"""Exit criterion 4. Both carriers generate, so both have a capture price."""
	generation, price = _kenya_solar_wind()
	captures = capture_by_technology(generation, price)

	assert set(captures) == {"solar", "wind"}
	time_weighted = captures["solar"][0].time_weighted_price_usd_per_mwh
	assert time_weighted is not None
	for carrier in ("solar", "wind"):
		point = captures[carrier][0]
		assert point.capture_price_usd_per_mwh is not None
		assert point.capture_rate is not None
		# Both generate off the evening peak, so both capture below the mean.
		assert point.capture_price_usd_per_mwh < time_weighted
		assert point.capture_rate < 1.0
	# Solar's output sits closer to the trough than wind's, so it captures less.
	solar_capture = captures["solar"][0].capture_price_usd_per_mwh
	wind_capture = captures["wind"][0].capture_price_usd_per_mwh
	assert solar_capture is not None and wind_capture is not None
	assert solar_capture < wind_capture


# --------------------------------------------------------------------------
# Exit criterion 7: VaR/CVaR on a normal sample matches 1.645 sigma at 95%
# --------------------------------------------------------------------------


def test_var_matches_the_analytic_normal_quantile():
	"""Exit criterion 7. A 200k-path standard normal must match 1.645 sigma.

	The sample is seeded, so the comparison is exact to a few parts in a
	thousand -- not a band wide enough to pass on anything.
	"""
	rng = np.random.default_rng(0)
	sigma = 1.0
	sample = rng.standard_normal(200_000) * sigma
	result = value_at_risk(-sample, 0.95)

	analytic = normal_var_check(sigma, 0.95)
	assert analytic == pytest.approx(1.6449, abs=1e-4)
	assert result.value_at_risk_usd == pytest.approx(analytic, rel=2e-3)
	# CVaR for a normal is sigma * phi(z_alpha) / (1 - alpha) ~ 2.0627 sigma.
	assert result.conditional_value_at_risk_usd == pytest.approx(2.0627, rel=5e-3)
	assert result.conditional_value_at_risk_usd >= result.value_at_risk_usd >= 0.0


def test_a_non_positive_definite_correlation_raises():
	"""The Cholesky check (06-layer3 §7.2). An unchecked factor returns NaNs."""
	from alea.market.risk import checked_cholesky

	# Pairwise correlations +0.99, +0.99 and -0.99 are not jointly realisable.
	bad = np.array(
		[
			[1.0, 0.99, 0.99],
			[0.99, 1.0, -0.99],
			[0.99, -0.99, 1.0],
		]
	)
	with pytest.raises(RuntimeError, match="positive-definite"):
		checked_cholesky(bad)


# --------------------------------------------------------------------------
# Exit criterion 8: bankability matches a hand-computed fixture
# --------------------------------------------------------------------------


def test_bankability_matches_a_hand_computed_fixture():
	"""Exit criterion 8. A -1000 outlay then 250/yr for five years.

	The project flows are the CFADS less the debt service, so the fixture is
	stated in CFADS and service and the flows are the difference:
	[-1000, 250, 250, 250, 250, 250]. The IRR solves 1000 = 250 * annuity(r, 5),
	so the annuity factor is 4.0 and r = 7.9308%. NPV at 8% is -1.8225.
	"""
	cfads = [-1000.0, 400.0, 400.0, 400.0, 400.0, 400.0]
	debt_service = [0.0, 150.0, 150.0, 150.0, 150.0, 150.0]
	project_flows = [-1000.0, 250.0, 250.0, 250.0, 250.0, 250.0]

	assert irr(project_flows) == pytest.approx(0.0793082612, rel=1e-6)
	assert npv(project_flows, 0.08) == pytest.approx(-1.8224907, rel=1e-6)

	result = bankability(cfads, debt_service, discount_rate=0.08)
	assert result.project_irr == pytest.approx(0.0793082612, rel=1e-6)
	assert result.npv_usd == pytest.approx(-1.8224907, rel=1e-6)
	assert result.years == 6
	# Period 0 has no debt service; the later periods cover at 400/150 = 2.667.
	assert result.min_dscr == pytest.approx(400.0 / 150.0)


def test_bankability_encodes_a_grace_period_ratio_as_none():
	"""A period with no debt service has no ratio, and JSON cannot carry ``inf``.

	``dscr`` returns ``inf`` for a fully-covered period with no service. The
	schema's ratios are finite, so an unencoded ``inf`` made a standard
	construction/grace period raise at construction -- a real schedule the model
	could not represent. The artefact encodes it as ``None``, the same rule
	capture prices follow for NaN.
	"""
	result = bankability([300.0, 300.0], [0.0, 100.0])
	assert result.dscr == [None, pytest.approx(3.0)]
	assert result.min_dscr == pytest.approx(3.0)
	# The JSON round-trip is the point: ``inf`` cannot survive it, ``None`` can.
	assert result.model_dump(mode="json")["dscr"] == [None, 3.0]


# --------------------------------------------------------------------------
# Exit criterion 10 / §6: every PPA price records its FX rate and date
# --------------------------------------------------------------------------


def test_a_ppa_price_records_its_fx_rate_and_date():
	"""The currency trap (06-layer3 §6). A local price without a rate is refused."""
	fx = FxRate(local_per_usd=145.0, rate_date="2026-01-15", source="CBK")
	benchmark = ppa_benchmark(
		"KE",
		"solar",
		10,
		50.0,
		fx=fx,
		fx_basis_pct=0.02,
		fx_basis_source="config.costs.kes_usd",
		credit_spread_pct=0.03,
		credit_source="sovereign CDS",
	)

	assert benchmark.fx is not None
	assert benchmark.fx.rate_date == "2026-01-15"
	assert benchmark.fx.local_per_usd == pytest.approx(145.0)
	# USD price carries the credit spread, never the FX basis.
	assert benchmark.price_usd_per_mwh == pytest.approx(50.0 * 1.03)
	# The local price is the USD price converted at the recorded rate, then the
	# FX basis applied: 51.5 * 145 * 1.02.
	assert benchmark.price_local_per_mwh == pytest.approx(51.5 * 145.0 * 1.02)

	# A local price with no rate cannot be built at all.
	with pytest.raises(ValueError, match="FX rate"):
		from alea.market.views import PpaBenchmark

		PpaBenchmark(
			country_iso="KE",
			carrier="solar",
			tenor_years=10,
			base_capture_price_usd_per_mwh=50.0,
			price_usd_per_mwh=50.0,
			price_local_per_mwh=7_000.0,  # no fx
		)


def test_a_ppa_tenor_averages_the_window_not_year_one():
	"""§6: a ten-year PPA is priced on the term, not on year one."""
	by_year = {2030: 100.0, 2031: 90.0, 2032: 80.0, 2033: 70.0}
	assert tenor_capture_price(by_year, tenor_years=2, start_year=2030) == pytest.approx(95.0)
	assert tenor_capture_price(by_year, tenor_years=4, start_year=2030) == pytest.approx(85.0)
	# A year whose capture is undefined is dropped, not counted as zero.
	assert tenor_capture_price(
		{2030: float("nan"), 2031: 90.0}, tenor_years=2, start_year=2030
	) == pytest.approx(90.0)
