# SPDX-License-Identifier: MIT
"""Layer 3 orchestration.

The entry points a pipeline stage or the CLI calls. Each takes real objects,
produces a result, and writes it as a versioned artefact with provenance
(AD-4). Nothing here holds a live object across a boundary.

Two conventions are enforced at this seam because they are the ones that rot
silently:

* **Every currency conversion records the rate and the rate's date.** The
  ``PpaBenchmark`` schema will not accept a local-currency price without an
  ``FxRate``, and the rate carries its date. See ``market.ppa``.
* **Every artefact records the inputs it was built from.** A result that cannot
  name its inputs cannot be reproduced, and ``DerivedProvenance`` refuses to be
  constructed without them.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alea._uuid7 import uuid7str
from alea.io.artefacts import read_artefact, stage_is_current, write_artefact
from alea.logging import get_logger
from alea.market.agents import Agent, build_stack
from alea.market.capture import capture_by_technology
from alea.market.clearing import clear_market, clear_market_series, clear_market_zonal
from alea.market.fleet import build_fleet_series, fleet_energy_mwh, load_series
from alea.market.ppa import ppa_curve
from alea.market.risk import monte_carlo_risk, value_at_risk
from alea.market.strategy import Strategy
from alea.market.views import (
	ClearingResult,
	FxRate,
	Interface,
	PpaBenchmark,
	RiskResult,
)
from alea.provenance.models import Basis, DerivedProvenance, Licence

logger = get_logger(__name__)


def _derived(
	inputs: Sequence[str],
	*,
	parameters: dict[str, Any],
	notes: str,
	source_id: str,
) -> DerivedProvenance:
	"""Provenance for a Layer 3 artefact.

	Layer 3's outputs are modelled, not measured, so the basis is ``MODELLED``
	with zero uncertainty: the uncertainty is carried by the risk metrics, not
	folded into the price.
	"""
	return DerivedProvenance(
		source_id=source_id,
		basis=Basis.MODELLED,
		licence=Licence.UNKNOWN,
		uncertainty=0.0,
		inputs=list(inputs),
		parameters=parameters,
		notes=notes,
		run_id=uuid7str(),
	)


def clear_scenario(
	agents: Sequence[Agent],
	demand_mw: float,
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
	force: bool = False,
) -> ClearingResult:
	"""Clear one market from a fleet of agents and write the result.

	The competitive benchmark is written into the provenance parameters, so a
	clearing price in the artefact can always be read against the price the same
	fleet would have cleared at with no strategic markup.

	``force`` follows the pipeline's idempotence convention: a scenario already
	current for these inputs is read back rather than re-cleared, and ``force``
	re-clears and rewrites it. It is threaded here rather than left to the
	caller because a scenario that is current is *defined* by the inputs the
	artefact records, and that check belongs at the write path.
	"""
	assert agents, "no agents to clear a market from"
	if not force and inputs and stage_is_current(out, list(inputs)):
		existing, _ = read_artefact(out)
		logger.info("clear_scenario.skip", out=str(out))
		return ClearingResult.model_validate(existing)
	stack = build_stack(agents)
	result = clear_market(
		stack,
		demand_mw,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	if not result.demand_met:
		# Loud, because a clearing price from a short stack is a price for a
		# system in blackout, and it must never be quoted as an ordinary price.
		logger.warning(
			"market_short",
			demand_mw=demand_mw,
			unserved_mwh=result.unserved_mwh,
			clearing_price=result.clearing_price_usd_per_mwh,
		)
	provenance = _derived(
		inputs,
		parameters={
			"demand_mw": demand_mw,
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
			"units": len(stack),
			"competitive_clearing_price_usd_per_mwh": clear_market(
				[bid.model_copy(update={"price_usd_per_mwh": bid.marginal_cost_usd_per_mwh})
				 if bid.marginal_cost_usd_per_mwh is not None else bid
				 for bid in stack],
				demand_mw,
				value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
			).clearing_price_usd_per_mwh,
		},
		notes="uniform-price merit-order clearing",
		source_id="market.clearing",
	)
	write_artefact(out, result.model_dump(mode="json"), provenance, format="json")
	logger.info("clear_scenario", out=str(out), price=result.clearing_price_usd_per_mwh)
	return result


def clear_zonal_scenario(
	agents_by_zone: dict[str, Sequence[Agent]],
	demand_by_zone: dict[str, float],
	interfaces: Sequence[Interface],
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
) -> Any:
	"""Clear a zonal market with transmission limits and write the result.

	Congestion is the output that matters: when a corridor binds, the zones
	split into distinct prices and the corridor earns a rent. A single-price
	model cannot produce this.
	"""
	assert agents_by_zone, "no zones to clear"
	bids_by_zone = {zone: build_stack(list(agents)) for zone, agents in agents_by_zone.items()}
	result = clear_market_zonal(
		bids_by_zone,
		demand_by_zone,
		list(interfaces),
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	provenance = _derived(
		inputs,
		parameters={
			"zones": sorted(bids_by_zone),
			"interfaces": [i.model_dump(mode="json") for i in interfaces],
			"demand_by_zone": demand_by_zone,
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
		},
		notes="zonal clearing with DC corridor limits",
		source_id="market.clearing.zonal",
	)
	write_artefact(out, result.model_dump(mode="json"), provenance, format="json")
	logger.info(
		"clear_zonal_scenario",
		out=str(out),
		congested=len(result.congested_interfaces),
		converged=result.converged,
	)
	return result


def capture_scenario(
	generation_mw: pd.DataFrame,
	price_usd_per_mwh: pd.Series,
	out: str | Path,
	*,
	inputs: Sequence[str],
	period: str | None = None,
) -> dict[str, Any]:
	"""Capture prices per technology and write the result.

	Technologies that generated nothing carry ``null`` (the artefact encoding of
	NaN), never zero. See ``market.capture``. When ``period`` is a pandas offset
	alias each carrier maps to a list of per-period capture prices; otherwise
	there is a single period over the whole series.
	"""
	assert not generation_mw.empty, "no generation to compute capture prices from"
	captures = capture_by_technology(generation_mw, price_usd_per_mwh, period=period)
	payload = {
		carrier: [capture.model_dump(mode="json") for capture in periods]
		for carrier, periods in sorted(captures.items())
	}
	provenance = _derived(
		inputs,
		parameters={
			"period": period,
			"periods": max((len(p) for p in captures.values()), default=0),
			"snapshots": int(len(generation_mw)),
			"carriers": sorted(str(c) for c in generation_mw.columns),
			"no_generation_carriers": sorted(
				carrier
				for carrier, periods in captures.items()
				if all(p.capture_price_usd_per_mwh is None for p in periods)
			),
		},
		notes="revenue-weighted capture prices; NaN (null) where a carrier generated nothing",
		source_id="market.capture",
	)
	write_artefact(out, payload, provenance, format="json")
	logger.info("capture_scenario", out=str(out), carriers=len(payload))
	return payload


def ppa_scenario(
	country_iso: str,
	carrier: str,
	capture_by_year: dict[int, float],
	tenors: list[int],
	out: str | Path,
	*,
	inputs: Sequence[str],
	fx: FxRate | None = None,
	credit_spread_pct: float = 0.0,
	credit_source: str = "",
	fx_basis_pct: float = 0.0,
	fx_basis_source: str = "",
) -> dict[int, PpaBenchmark]:
	"""A PPA benchmark curve and write the result.

	When ``fx`` is supplied, every tenor's local-currency price records the rate
	and its date in the artefact. A curve with no ``fx`` is USD-only.
	"""
	assert tenors, "a PPA curve needs at least one tenor"
	curve = ppa_curve(
		country_iso,
		carrier,
		capture_by_year,
		tenors,
		credit_spread_pct=credit_spread_pct,
		credit_source=credit_source,
		fx_basis_pct=fx_basis_pct,
		fx_basis_source=fx_basis_source,
		fx=fx,
	)
	payload = {str(tenor): benchmark.model_dump(mode="json") for tenor, benchmark in sorted(curve.items())}
	provenance = _derived(
		inputs,
		parameters={
			"country_iso": country_iso,
			"carrier": carrier,
			"tenors": sorted(tenors),
			"fx_rate": fx.model_dump(mode="json") if fx is not None else None,
			"credit_spread_pct": credit_spread_pct,
			"fx_basis_pct": fx_basis_pct,
		},
		notes="PPA benchmark curve; every local-currency price records its FX rate and date",
		source_id="market.ppa",
	)
	write_artefact(out, payload, provenance, format="json")
	logger.info("ppa_scenario", out=str(out), tenors=len(payload))
	return curve


def risk_scenario(
	returns: np.ndarray,
	out: str | Path,
	*,
	inputs: Sequence[str],
	confidence: float = 0.95,
) -> RiskResult:
	"""VaR/CVaR over a loss sample and write the result.

	The returned magnitudes are losses: ``CVaR >= VaR >= 0``.
	"""
	result = value_at_risk(returns, confidence)
	provenance = _derived(
		inputs,
		parameters={"confidence": confidence, "n_paths": result.n_paths},
		notes="VaR/CVaR as positive loss magnitudes",
		source_id="market.risk",
	)
	write_artefact(out, result.model_dump(mode="json"), provenance, format="json")
	logger.info("risk_scenario", out=str(out), var=result.value_at_risk_usd)
	return result


def monte_carlo_scenario(
	means: np.ndarray,
	stds: np.ndarray,
	correlation: np.ndarray,
	model: Any,
	out: str | Path,
	*,
	inputs: Sequence[str],
	n_paths: int = 100_000,
	seed: int = 0,
	confidence: float = 0.95,
) -> RiskResult:
	"""Correlated Monte Carlo risk and write the result.

	The seed is recorded in the provenance so the paths can be regenerated
	exactly (AD-8).
	"""
	result = monte_carlo_risk(
		means,
		stds,
		correlation,
		model,
		n_paths=n_paths,
		seed=seed,
		confidence=confidence,
	)
	provenance = _derived(
		inputs,
		parameters={"n_paths": n_paths, "seed": seed, "confidence": confidence},
		notes="correlated Monte Carlo VaR/CVaR; Cholesky factor checked for positive-definiteness",
		source_id="market.risk.monte_carlo",
	)
	write_artefact(out, result.model_dump(mode="json"), provenance, format="json")
	logger.info("monte_carlo_scenario", out=str(out), seed=seed, cvar=result.conditional_value_at_risk_usd)
	return result


# --------------------------------------------------------------------------
# The two report sections
# --------------------------------------------------------------------------


def monthly_market_to_artefact(
	network: Any,
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
	value_of_lost_load_basis: str = "",
	strategy: Strategy | None = None,
) -> pd.DataFrame:
	"""Clear every snapshot and write the monthly market report's frame.

	The frame `reporting/monthly.py`'s ``market_report`` section reads, and the
	shape is decided by that section's declared columns --
	``["Carrier", "Volume", "Average price", "Basis"]``. Two of those are
	numeric, so `_rows_for` does *not* fall back to binding the primary into
	both: each row must carry a ``volume`` and an ``average_price`` column of its
	own, or the reader raises rather than printing the volume under "Average
	price".

	**One row per carrier, over the snapshots the network has.** ``volume`` is
	MWh dispatched and ``average_price`` is the volume-weighted price that
	carrier received -- the capture price, which is what a generator's revenue
	actually is. A simple mean of the clearing prices would answer a different
	question: it is the price a *buyer* at the wrong end of the dispatch paid.

	The clearing is per snapshot, because a fleet's availability is. A single
	clear at the period mean would produce one price for a month.
	"""
	assert value_of_lost_load_usd_per_mwh >= 0.0, "VoLL must be non-negative"
	fleets = build_fleet_series(network, strategy=strategy)
	if not fleets:
		raise ValueError(
			"the network has no generators, so there is no fleet to clear and no "
			"market to report. An empty frame would render as a month in which "
			"nothing was dispatched"
		)
	demand = load_series(network)
	weights = fleet_energy_mwh(network)

	results = clear_market_series(
		[build_stack(fleet) for fleet in fleets],
		demand,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	units = {agent.unit.unit_id: agent.unit.carrier for fleet in fleets for agent in fleet}

	# Carrier -> per-snapshot MWh and the revenue that MWh earned. Revenue is
	# dispatch x clearing price, so its ratio to the energy is the carrier's own
	# average price rather than the system's.
	energy: dict[str, np.ndarray] = {}
	revenue: dict[str, np.ndarray] = {}
	for hour, result in enumerate(results):
		price = result.clearing_price_usd_per_mwh
		weight = float(weights[hour]) if hour < weights.shape[0] else 1.0
		for unit_id, mw in result.dispatched.items():
			carrier = units.get(unit_id, unit_id)
			mwh = float(mw) * weight
			energy.setdefault(carrier, np.zeros(len(results), dtype=np.float64))[hour] += mwh
			revenue.setdefault(carrier, np.zeros(len(results), dtype=np.float64))[hour] += mwh * price

	rows: list[dict[str, Any]] = []
	for carrier in sorted(energy):
		mwh = float(np.nansum(energy[carrier]))
		earned = float(np.nansum(revenue[carrier]))
		# A carrier that dispatched nothing has no average price. NaN, never
		# zero: zero is a specific claim (it sold at nothing) that propagates
		# into every portfolio average -- the same rule `capture.capture_price`
		# applies, and the artefact encodes NaN as null.
		average = earned / mwh if mwh > 0.0 else float("nan")
		rows.append(
			{
				"label": carrier,
				"value": average,
				"unit": "USD/MWh",
				"volume": mwh,
				"average_price": average,
			}
		)

	unserved = float(sum(result.unserved_mwh for result in results))
	provenance = _derived(
		inputs,
		parameters={
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
			"value_of_lost_load_basis": value_of_lost_load_basis,
			"strategy": (strategy or Strategy.competitive()).kind.value,
			"snapshots": len(results),
			"carriers": len(rows),
			"unserved_mwh": unserved,
			"demand_mwh": float(np.nansum(demand * weights[: demand.shape[0]])),
		},
		notes=(
			"one row per carrier: `volume` is MWh dispatched over the network's "
			"snapshots and `average_price` is the volume-weighted price it received "
			"(its capture price), not the system mean. The clearing is per snapshot "
			"because a fleet's availability is. Unserved energy is recorded in the "
			"provenance: a clearing price from a short stack is a price for a system "
			"in blackout"
		),
		source_id="market.monthly",
	)
	from alea.io.pipeline import write_stage

	write_stage(Path(out), pd.DataFrame(rows, columns=["label", "value", "unit", "volume", "average_price"]), provenance, format="parquet")
	logger.info(
		"monthly_market_to_artefact",
		out=str(out),
		carriers=len(rows),
		snapshots=len(results),
		unserved_mwh=unserved,
	)
	return pd.DataFrame(rows)


def weekly_market_to_artefact(
	network: Any,
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
	value_of_lost_load_basis: str = "",
	strategy: Strategy | None = None,
) -> pd.DataFrame:
	"""Clear every snapshot and write the weekly market summary's frame.

	The frame `reporting/weekly.py`'s ``market_summary`` section reads, whose
	columns are ``["Carrier", "Volume", "Capture price", "Basis"]``. Two of
	those are numeric, so `_rows_for` binds each header to the row column
	*naming* it: ``Capture price`` normalises to ``captureprice`` and the reader
	**raises** against a row carrying only the monthly section's
	``average_price``. That is why this producer writes a column of its own
	rather than sharing `monthly_market_to_artefact`'s frame, and the two
	functions deliberately disagree about the column name.

	**The capture price is the quantity, not a renaming of the mean.** A
	carrier's capture price is the price it actually received, weighted by what
	it sold -- `market.capture.capture_price`, which is the kernel
	`reporting/producers.py` recorded as existing with no rule running it. A
	simple mean of the clearing prices would give every carrier the same number
	and the section's second column would carry no information. The two are
	equal only on a flat stack, which is the fixture that cannot tell them
	apart.

	**No ``period`` argument, and that is a decision rather than an omission.**
	``capture_by_technology`` buckets by a pandas offset alias when asked. The
	weekly section is one row per carrier over the week, so the whole series is
	one period; bucketing by ``"W"`` would return seven periods per carrier and
	the section declares no column for the week a row belongs to.
	"""
	assert value_of_lost_load_usd_per_mwh >= 0.0, "VoLL must be non-negative"
	fleets = build_fleet_series(network, strategy=strategy)
	if not fleets:
		raise ValueError(
			"the network has no generators, so there is no fleet to clear and no "
			"market to summarise. An empty frame would render as a week in which "
			"nothing was dispatched"
		)
	demand = load_series(network)
	weights = fleet_energy_mwh(network)

	results = clear_market_series(
		[build_stack(fleet) for fleet in fleets],
		demand,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	units = {agent.unit.unit_id: agent.unit.carrier for fleet in fleets for agent in fleet}
	carriers = sorted(set(units.values()))

	# ``(time, carrier)`` generation in MWh and the clearing price per snapshot,
	# which is the pair `capture_by_technology` weights against each other. The
	# weight turns a dispatch in MW into the energy it actually is: a snapshot
	# is one hour only on an hourly network.
	by_carrier = {carrier: np.zeros(len(results), dtype=np.float64) for carrier in carriers}
	price = np.zeros(len(results), dtype=np.float64)
	for hour, result in enumerate(results):
		price[hour] = result.clearing_price_usd_per_mwh
		weight = float(weights[hour]) if hour < weights.shape[0] else 1.0
		for unit_id, mw in result.dispatched.items():
			carrier = units.get(unit_id, unit_id)
			by_carrier.setdefault(carrier, np.zeros(len(results), dtype=np.float64))
			by_carrier[carrier][hour] += float(mw) * weight

	generation = pd.DataFrame(by_carrier, columns=carriers, dtype=np.float64)
	captures = capture_by_technology(generation, price)

	rows: list[dict[str, Any]] = []
	for carrier in carriers:
		# One period, because the call above asked for none. A carrier that
		# dispatched nothing has an *undefined* capture price and the kernel
		# returns NaN for it -- never zero, which would claim it sold at nothing
		# and drag every portfolio average toward it.
		point = captures[carrier][0]
		rows.append(
			{
				"label": carrier,
				"value": point.capture_price_usd_per_mwh,
				"unit": "USD/MWh",
				"volume": point.generation_mwh,
				"capture_price": point.capture_price_usd_per_mwh,
			}
		)

	unserved = float(sum(result.unserved_mwh for result in results))
	provenance = _derived(
		inputs,
		parameters={
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
			"value_of_lost_load_basis": value_of_lost_load_basis,
			"strategy": (strategy or Strategy.competitive()).kind.value,
			"snapshots": len(results),
			"carriers": len(rows),
			"unserved_mwh": unserved,
			"demand_mwh": float(np.nansum(demand * weights[: demand.shape[0]])),
			"capture_basis": "volume-weighted price received, not the system mean",
		},
		notes=(
			"one row per carrier: `volume` is MWh dispatched over the network's "
			"snapshots and `capture_price` is the volume-weighted price it received "
			"-- `market.capture.capture_price`, which is NaN rather than zero for a "
			"carrier that dispatched nothing. The clearing is per snapshot because a "
			"fleet's availability is. Unserved energy is recorded in the provenance: "
			"a clearing price from a short stack is a price for a system in blackout"
		),
		source_id="market.weekly",
	)
	from alea.io.pipeline import write_stage

	frame = pd.DataFrame(
		rows, columns=["label", "value", "unit", "volume", "capture_price"]
	)
	write_stage(Path(out), frame, provenance, format="parquet")
	logger.info(
		"weekly_market_to_artefact",
		out=str(out),
		carriers=len(rows),
		snapshots=len(results),
		unserved_mwh=unserved,
	)
	return frame


def quarterly_market_to_artefact(
	network: Any,
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
	value_of_lost_load_basis: str = "",
	strategy: Strategy | None = None,
	quarters: int = 4,
) -> pd.DataFrame:
	"""The quarterly price outlook's frame, from the clearing the run supports.

	The frame `reporting/quarterly.py`'s ``market_outlook`` reads, and its
	columns are ``["Quarter", "Price", "Basis"]`` -- exactly one numeric column,
	so ``_rows_for`` binds the primary directly and no extra is needed.

	**What the series is, and what it is not.** The section's prose says "the
	next four quarters, under the central scenario", and *no forecast model
	exists in this repository*: no demand forecast, no price forecast, and the
	plan's own exit criterion for Layer 3 is only "competitive strategy
	reproduces Layer 1 marginal prices". So this writes the clearing prices the
	solved network actually supports -- one per planning horizon the network
	carries -- labelled by the period they belong to, and records in the
	provenance that the series is *the solve's own horizons*, not a four-quarter
	projection.

	Writing four invented quarters would be the defect this whole layer exists
	to avoid: a number with a basis column and no model behind it. A shorter
	series that says what it is beats a longer one that does not.

	**One row per period, and the period is aggregated.** The section is titled by
	quarter, so a row's price has to be the price *of that quarter* -- and the
	first version of this wrote one row per *snapshot*, which for an hourly
	network is 8,760 rows all labelled with the same quarter and each holding a
	single hour's price. The label was a period and the number was an hour, which
	is the mismatch a basis column cannot repair. So the clearing is grouped by
	period and each row carries the demand-weighted mean of the clearing prices
	in it: the mean that answers "what did a MWh cost over this quarter", which is
	the question the column heading asks.
	"""
	fleets = build_fleet_series(network, strategy=strategy)
	if not fleets:
		raise ValueError("the network has no generators, so there is no price to report")
	demand = load_series(network)
	weights = fleet_energy_mwh(network)
	results = clear_market_series(
		[build_stack(fleet) for fleet in fleets],
		demand,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)

	# Period -> the energy-weighted price sum and the weight that earned it. A
	# period the network does not reach is absent rather than zero: a quarter
	# with no snapshots in it has no price, and a zero would read as a free one.
	periods = _periods_of(network, len(results), quarters=quarters)
	earned: dict[str, float] = {}
	weighted: dict[str, float] = {}
	for position, (period, result) in enumerate(zip(periods, results, strict=True)):
		weight = float(weights[position]) if position < weights.shape[0] else 1.0
		earned[period] = earned.get(period, 0.0) + result.clearing_price_usd_per_mwh * weight
		weighted[period] = weighted.get(period, 0.0) + weight

	rows: list[dict[str, Any]] = []
	for period in dict.fromkeys(periods):
		total = weighted[period]
		rows.append(
			{
				"label": period,
				"value": earned[period] / total if total > 0.0 else float("nan"),
				"unit": "USD/MWh",
			}
		)

	provenance = _derived(
		inputs,
		parameters={
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
			"value_of_lost_load_basis": value_of_lost_load_basis,
			"strategy": (strategy or Strategy.competitive()).kind.value,
			"periods": len(rows),
			"series_basis": "the solved network's own horizons, not a price forecast",
			"quarters_requested": quarters,
		},
		notes=(
			"clearing price per period the solved network supports. No price-forecast "
			"model exists in this repository, so this is the solve's own horizons "
			"rather than the four-quarter projection the section's prose describes; "
			"the provenance says so, and the series is short rather than invented"
		),
		source_id="market.outlook",
	)
	from alea.io.pipeline import write_stage

	write_stage(Path(out), pd.DataFrame(rows, columns=["label", "value", "unit"]), provenance, format="parquet")
	logger.info("quarterly_market_to_artefact", out=str(out), periods=len(rows))
	return pd.DataFrame(rows)


def daily_price_to_artefact(
	network: Any,
	out: str | Path,
	*,
	value_of_lost_load_usd_per_mwh: float,
	inputs: Sequence[str],
	value_of_lost_load_basis: str = "",
	strategy: Strategy | None = None,
	hours: int = 24,
) -> pd.DataFrame:
	"""The daily price section's frame, from the clearing the solve supports.

	The frame `reporting/daily.py`'s ``price_forecast`` reads, whose columns are
	``["Period", "Price", "Basis"]`` -- one numeric column, so ``_rows_for``
	binds the primary directly.

	**What the series is, and what it is not.** The section's prose says
	"day-ahead clearing price by hour, from the market model", and the market
	model is `clear_market_series` -- there is no price *forecast* in this
	repository, the same absence `quarterly_market_to_artefact` records for the
	outlook. So this writes the clearing prices the solved network's own
	snapshots produce, labelled by the hour they belong to, and the provenance
	says the series is the solve's horizons rather than a day-ahead forecast.
	Inventing a forecast would put a number under a basis column with no model
	behind it.

	**Why the hourly cap.** The section is titled by hour and a daily report
	covers one day, so a network carrying a year of snapshots would render 8,760
	rows under a heading that promises a day. ``hours`` bounds it, and the
	provenance records how many the network actually offered so a reader can see
	the series was cut rather than short.

	**One row per hour, and the price is that hour's.** Each snapshot is cleared
	once against the fleet available in it, which is what makes the row a price
	for that hour rather than a mean over a fleet that was mostly offline. A
	single clear at the period mean would produce one price for a day.
	"""
	assert value_of_lost_load_usd_per_mwh >= 0.0, "VoLL must be non-negative"
	fleets = build_fleet_series(network, strategy=strategy)
	if not fleets:
		raise ValueError(
			"the network has no generators, so there is no fleet to clear and no "
			"price to report. An empty frame would render as a day in which "
			"nothing cleared"
		)
	demand = load_series(network)
	results = clear_market_series(
		[build_stack(fleet) for fleet in fleets],
		demand,
		value_of_lost_load_usd_per_mwh=value_of_lost_load_usd_per_mwh,
	)
	snapshots = list(network.snapshots)

	rows: list[dict[str, Any]] = []
	for position, result in enumerate(results[:hours]):
		# A snapshot's own label, where the network states one. Numbering the
		# hours instead would put a period in the column that the index does not
		# name, which is the mismatch the quarterly docstring warns about.
		label = (
			f"{pd.Timestamp(snapshots[position][0] if isinstance(snapshots[position], tuple) else snapshots[position]):%Y-%m-%d %H:%M}"
			if position < len(snapshots)
			else f"h{position + 1}"
		)
		rows.append(
			{
				"label": label,
				"value": result.clearing_price_usd_per_mwh,
				"unit": "USD/MWh",
			}
		)

	provenance = _derived(
		inputs,
		parameters={
			"value_of_lost_load_usd_per_mwh": value_of_lost_load_usd_per_mwh,
			"value_of_lost_load_basis": value_of_lost_load_basis,
			"strategy": (strategy or Strategy.competitive()).kind.value,
			"hours": len(rows),
			"snapshots_available": len(snapshots),
			"series_basis": "the solved network's own snapshots, not a day-ahead forecast",
		},
		notes=(
			"clearing price per hour the solved network supports. No price-forecast "
			"model exists in this repository, so this is the solve's own snapshots "
			"rather than the day-ahead forecast the section's prose describes; the "
			"provenance says so, and the series is bounded rather than invented"
		),
		source_id="market.price_forecast",
	)
	from alea.io.pipeline import write_stage

	frame = pd.DataFrame(rows, columns=["label", "value", "unit"])
	write_stage(Path(out), frame, provenance, format="parquet")
	logger.info("daily_price_to_artefact", out=str(out), hours=len(rows))
	return frame


def _periods_of(network: Any, count: int, *, quarters: int) -> list[str]:
	"""Labels for ``count`` clearing prices, from the network's own snapshots.

	A multi-investment-period network's snapshots carry the horizon as the first
	level of their index, and that is the period a price belongs to. An
	hourly network carries a datetime, and the calendar quarter it falls in is
	the label. Anything else is numbered, because a label that claims a period
	the index does not state is a period invented at the render.
	"""
	snapshots = network.snapshots
	if len(snapshots) != count:
		return [f"Q{position + 1}" for position in range(count)]

	labels: list[str] = []
	for snapshot in snapshots:
		year, quarter = _year_and_quarter(snapshot)
		labels.append(f"{year}-Q{quarter}" if year is not None else str(snapshot))
	return labels


def _year_and_quarter(snapshot: Any) -> tuple[int | None, int]:
	"""The calendar year and quarter a snapshot belongs to, or ``(None, 0)``.

	A multi-index snapshot's first level is the investment period; a timestamp's
	own quarter is the second. Neither is guessed from a string when the object
	carries the fact.
	"""
	first = snapshot[0] if isinstance(snapshot, tuple) else snapshot
	if hasattr(first, "year") and hasattr(first, "month"):
		return int(first.year), (int(first.month) - 1) // 3 + 1
	if isinstance(first, (int, np.integer)):
		return int(first), 0
	return None, 0


__all__ = [
	"capture_scenario",
	"clear_scenario",
	"clear_zonal_scenario",
	"daily_price_to_artefact",
	"monte_carlo_scenario",
	"monthly_market_to_artefact",
	"ppa_scenario",
	"quarterly_market_to_artefact",
	"risk_scenario",
	"weekly_market_to_artefact",
]
