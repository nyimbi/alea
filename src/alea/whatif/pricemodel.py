# SPDX-License-Identifier: MIT
"""The engine's ``PriceFn``, built from a solved network's own price distribution.

WHY this module exists at all: ``WhatIfEngine`` takes a ``price_fn``, the
``cost_risk_frontier`` gate asserts a cost-risk frontier refuses without one,
and ``PriceFn`` had **no producer anywhere in ``src/``**. The only two
constructions of one were a lambda in the test that asserts the frontier works.
So criterion 6 -- the frontier that answers the investment question -- was
reachable from a test and from nothing else, which is the defect class this
repository keeps finding: declared, tested, exported, produced by nobody.

WHY the input is the network's own prices: ``ScenarioResult`` has carried
``price_mean_usd_per_mwh`` and ``price_volatility_usd_per_mwh`` since Layer 5
was written, ``extract`` fills both from the solved network's marginal prices,
and **nothing read either one**. A price model that invented a volatility would
leave that gap open and answer with a number no input produced. Here the two
fields are the model's only inputs, so the risk axis is a function of the solve
in front of it.

**What the dispersion is, exactly.** ``price_statistics`` takes the standard
deviation across the *flattened snapshot x bus* marginal-price matrix, so the
spread is cross-sectional within one solve -- the variation between an hour the
solar farm covers and an hour it does not. It is **not** a temporal volatility
of the price level, and it is not a forecast. The model's assumption is that the
price level in a bad year disperses about its mean by as much as the solved
hours disperse about theirs. That is a heuristic and it is stated here rather
than buried, because the alternative reading -- "this is the modelled volatility
of future prices" -- would make the risk axis look like a Layer 3 output when it
is a Layer 5 restatement of one solve's own spread. A single-snapshot network
has no dispersion at all, so its risk axis is degenerate; the frontier still
reports it and ``risk_computed`` still says the axis was populated.

WHY the cost model is the revenue identity and not a fitted curve: a system
whose wholesale price averages ``p`` and whose served energy is ``E`` carries a
cost that moves with ``p * E``. Perturbing the price by ``dp`` therefore moves
the cost by ``dp * E`` -- an identity, not an assumption about elasticities. The
zero-mean draw keeps the expected cost equal to the objective the optimiser
returned, so the distribution is centred on the solve rather than on a
re-estimate of it, and only its spread is modelled.

WHY the draw goes through Layer 3: the physics of a correlated draw with a
checked Cholesky factor is ``alea.market.risk``'s, and the tail kernel is
``RiskMetrics.from_costs``'. This module supplies the *model* -- one input, the
wholesale price level -- and calls Layer 3 for everything else. Re-implementing
the draw here would give two draws that agree today and disagree after one of
them is fixed.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from alea.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PRICE_PATHS = 512
"""Monte Carlo paths per solve.

Modest on purpose. The engine calls this once per point of a sweep, and a
hundred-point frontier at 10^5 paths spends its whole runtime in the draw. 512
resolves the 95% tail to about one part in twenty, which is what a frontier
plots; the exact figure is recorded in the provenance either way.
"""


def price_model_from_network(
	*,
	n_paths: int = DEFAULT_PRICE_PATHS,
	confidence: float = 0.95,
) -> Any:
	"""A ``PriceFn`` over the solved network's own wholesale-price distribution.

	Returns ``(costs, threshold)``: a sample of total system costs, and the
	objective the optimiser returned as the threshold an exceedance probability
	is measured against. The engine turns the sample into ``RiskMetrics``; the
	risk kernel is not called here.

	Returns ``([], None)`` when the solve produced no marginal prices. The empty
	sample is the honest answer -- the engine reads it as "no price model" and
	the frontier as a refusal -- where a raise would turn "this solve cannot
	support a risk axis" into "this solve failed", and zero volatility would
	report a riskless portfolio for a solve that measured nothing.
	"""
	assert n_paths >= 2, f"a distribution needs at least two paths, got {n_paths}"

	def price_fn(network: Any, result: Any) -> tuple[list[float], float | None]:
		from alea.market.risk import checked_cholesky, correlated_shocks
		from alea.whatif.extract import price_statistics, total_cost_usd

		mean_price, std_price = price_statistics(network)
		if mean_price is None or std_price is None:
			logger.warning(
				"whatif.price_model.absent",
				reason="the solved network carries no marginal prices",
			)
			return [], None

		objective = total_cost_usd(network)
		energy_mwh = _served_energy_mwh(network)
		# The seed is derived from the scenario's own identity, so the same
		# scenario draws the same sample in this process and another (AD-8). A
		# clock- or global-RNG seed would make a frontier differ between two
		# runs of the same sweep, which is the determinism the layer promises.
		seed = _seed(result)

		# Layer 3's draw, at ``n_inputs = 1``: the one input is the wholesale
		# price level. The 1x1 factor is the identity correlation of a single
		# input, and going through the checked Cholesky rather than calling
		# numpy's RNG keeps the seeding convention Layer 3's -- a second draw
		# written here would agree with it today and diverge the first time
		# either is changed.
		factor = checked_cholesky(np.ones((1, 1), dtype=np.float64))
		shocks = correlated_shocks(factor, n_paths, seed=seed).ravel()
		prices = mean_price + shocks * std_price
		costs = objective + (prices - mean_price) * energy_mwh

		logger.info(
			"whatif.price_model",
			mean_price=round(mean_price, 6),
			std_price=round(std_price, 6),
			energy_mwh=round(energy_mwh, 3),
			n_paths=n_paths,
			seed=seed,
		)
		return [float(cost) for cost in costs], float(objective)

	price_fn.n_paths = n_paths  # type: ignore[attr-defined]
	price_fn.confidence = confidence  # type: ignore[attr-defined]
	return price_fn


def _served_energy_mwh(network: Any) -> float:
	"""Energy sold over the horizon, the multiplier in the revenue identity.

	Read from the load, not from generation: a system that curtailed half its
	output still sold the energy it served, and pricing the curtailed half would
	overstate how far a price move carries into the system cost.

	**A static ``p_set`` is per snapshot, not per horizon.** PyPSA puts a load
	defined with ``p_set=120.0`` in ``network.loads["p_set"]`` and leaves
	``loads_t.p_set`` empty, so summing the static column gives the energy of
	one snapshot. On a four-snapshot network that understates the served energy
	by 4x and the risk axis with it -- the same unit error the loss kernel
	carried, where a figure internally consistent with its own line answered a
	different question than the one asked. The snapshot count multiplies the
	static term and does not touch the dynamic one, which is already a series.
	"""
	loads = getattr(network, "loads", None)
	if loads is None or "p_set" not in loads.columns:
		return 0.0

	dynamic = getattr(getattr(network, "loads_t", None), "p_set", None)
	snapshots = len(network.snapshots)

	total = 0.0
	for name, row in loads.iterrows():
		static = float(row["p_set"] or 0.0)
		if dynamic is not None and name in dynamic.columns:
			# A load with a time series: the column already sums to its energy.
			total += float(np.nansum(dynamic[name].to_numpy(dtype=np.float64)))
		else:
			total += static * snapshots
	return float(total)


def _seed(result: Any) -> int:
	"""A deterministic seed from the scenario's identity.

	``ScenarioResult.scenario_id`` is the cache key the engine already computes
	over the parameters, the network checksum and the code version, so it
	separates two scenarios and repeats for one. Falls back to zero when the
	identity is absent rather than reaching for the clock.

	Hashed rather than parsed. The id is a UUID7 in a stored result
	(``0192abcd-ef01-...``) and a bare hex digest in the placeholder the engine
	hands its price model, so any scheme that reads it as one format raises on
	the other -- and a seed that raises takes the whole frontier with it. The
	digest is stable across processes, which is what AD-8 needs.
	"""
	token = str(getattr(result, "scenario_id", "") or "")
	if not token:
		return 0
	return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big")


__all__ = ["DEFAULT_PRICE_PATHS", "price_model_from_network"]
