# SPDX-License-Identifier: MIT
"""Layer 3 defects that were declared in a signature and never reached the body.

Four of them, each the same shape: a parameter or field that reads as a
capability and does nothing. A caller passing ``period="YE"`` got the whole
series; a HEDGE strategy's forward price was never read; ``clear_scenario``
accepted ``force`` and ignored it; ``fuel_price_from_config`` always returned
``None`` while sitting in ``__all__``.

Each test below fails against the pre-fix code, so none of them is a test of the
shape "the function exists".
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.market import fuel
from alea.market.agents import Agent, BiddingUnit
from alea.market.capture import capture_by_technology
from alea.market.service import clear_scenario
from alea.market.strategy import Strategy, StrategyKind


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
