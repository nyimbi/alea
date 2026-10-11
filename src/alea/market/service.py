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
from alea.io.artefacts import write_artefact
from alea.logging import get_logger
from alea.market.agents import Agent, build_stack
from alea.market.capture import capture_by_technology
from alea.market.clearing import clear_market, clear_market_zonal
from alea.market.ppa import ppa_curve
from alea.market.risk import monte_carlo_risk, value_at_risk
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
	"""
	assert agents, "no agents to clear a market from"
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
) -> dict[str, Any]:
	"""Capture prices per technology and write the result.

	Technologies that generated nothing carry ``null`` (the artefact encoding of
	NaN), never zero. See ``market.capture``.
	"""
	assert not generation_mw.empty, "no generation to compute capture prices from"
	captures = capture_by_technology(generation_mw, price_usd_per_mwh)
	payload = {
		carrier: capture.model_dump(mode="json") for carrier, capture in sorted(captures.items())
	}
	provenance = _derived(
		inputs,
		parameters={
			"periods": int(len(generation_mw)),
			"carriers": sorted(str(c) for c in generation_mw.columns),
			"no_generation_carriers": sorted(
				c for c, capture in captures.items() if capture.capture_price_usd_per_mwh is None
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


__all__ = [
	"capture_scenario",
	"clear_scenario",
	"clear_zonal_scenario",
	"monte_carlo_scenario",
	"ppa_scenario",
	"risk_scenario",
]
