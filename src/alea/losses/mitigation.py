# SPDX-License-Identifier: MIT
"""Ranking loss-mitigation options.

The specification's ``MitigationRanker.evaluate_option`` computes

```python
'opex_savings_USD_year': loss_reduction * 8760 * option['price_USD_MWh'],
```

which treats a **single-snapshot** loss reduction as representative of all 8760
hours. It is not: losses scale with current squared and vary with load and
dispatch, so a snapshot's reduction is one sample from a distribution that may
be nothing like the annual mean. A single-snapshot payback is a number with no
error bar that will be believed (07-layer4 §7.1).

The correct computation applies the option to **all** snapshots and sums the
per-snapshot reduction. :func:`evaluate_option` does that, and
:func:`annual_savings_from_snapshots` exists so a caller who already has the
per-snapshot series does not re-solve.

The second correction: ``payback = capex / annual_savings`` returns ``inf`` for
zero savings, which sorts to the bottom but reads in a report as "never" when it
may mean "savings below measurement resolution". A zero-saving option reports
``payback_years=None`` with a note, never ``inf``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.losses.flow import Network, solve_series
from alea.losses.views import LossConfig, MitigationOption, MitigationResult

logger = get_logger(__name__)


def apply_option(
	network: Network,
	option: MitigationOption,
	config: LossConfig | None = None,
) -> Network:
	"""A new network with the option's edits applied.

	Returns a **copy**: the caller's network is never mutated, for the same
	reason the contingency sweep takes branch status as an immutable input. An
	option that edits the network in place is an option whose effect leaks into
	the next option evaluated.
	"""
	cfg = config or LossConfig()
	touched = (
		np.asarray(option.branches, dtype=int)
		if option.branches
		else np.arange(network.n_branches)
	)
	if touched.size and (touched.min() < 0 or touched.max() >= network.n_branches):
		raise IndexError(
			f"option {option.name!r} names branches outside [0, {network.n_branches})"
		)
	resistance = network.resistance_ohm.copy()
	susceptance = network.branch_susceptance.copy()
	voltage = network.voltage_kv.copy()
	if option.resistance_scale != 1.0:
		resistance[touched] *= option.resistance_scale
	if option.voltage_scale != 1.0:
		voltage[touched] *= option.voltage_scale
	if option.added_susceptance_pu > 0.0:
		# A parallel circuit adds susceptance, which raises the branch's share
		# of flow and lowers its resistance-to-reactance ratio; only the
		# susceptance term is modelled, because the DC approximation has no
		# voltage magnitude to change.
		susceptance[touched] += option.added_susceptance_pu
	_ = cfg
	return Network(
		susceptance=_rebuild_susceptance(network, susceptance),
		branch_from=network.branch_from,
		branch_to=network.branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=resistance,
		voltage_kv=voltage,
		ratings_mw=network.ratings_mw,
		branch_names=network.branch_names,
	)


def _rebuild_susceptance(
	network: Network, branch_susceptance: NDArray[np.float64]
) -> NDArray[np.float64]:
	from alea.losses.flow import susceptance_matrix

	return susceptance_matrix(
		network.branch_from, network.branch_to, branch_susceptance, network.n_buses
	)


def annual_savings_from_snapshots(
	base_losses_mwh: NDArray[np.float64],
	option_losses_mwh: NDArray[np.float64],
	price_usd_per_mwh: NDArray[np.float64] | float,
) -> tuple[float, float]:
	"""Sum the per-snapshot loss reduction times that snapshot's price.

	Returns ``(annual_loss_reduction_mwh, annual_savings_usd)``. ``price`` may
	be a scalar or a per-snapshot series — a flat price is a special case of the
	series, and a price that varies by hour (a market price, or a time-of-use
	tariff) must be applied per snapshot or the saving is measured against the
	wrong hour.
	"""
	base = np.asarray(base_losses_mwh, dtype=float)
	after = np.asarray(option_losses_mwh, dtype=float)
	if base.shape != after.shape:
		raise ValueError(f"base {base.shape} and option {after.shape} must align")
	price = np.asarray(price_usd_per_mwh, dtype=float)
	if price.ndim == 0:
		price = np.full(base.shape, float(price), dtype=float)
	if price.shape != base.shape:
		raise ValueError(f"price {price.shape} must be scalar or match {base.shape}")
	reduction = base - after
	return float(np.sum(reduction)), float(np.sum(reduction * price))


def evaluate_option(
	network: Network,
	injections_mw: NDArray[np.float64],
	option: MitigationOption,
	config: LossConfig | None = None,
	*,
	price_usd_per_mwh: NDArray[np.float64] | float | None = None,
) -> MitigationResult:
	"""Compute an option's benefit over the whole hourly series.

	``annual_savings_usd`` is the sum of per-snapshot reductions, never
	``loss_reduction x 8760 x price``. The payback is ``None`` when savings fall
	below the measurement floor, which reports "unmeasurable" rather than the
	``inf`` that reads as "never".
	"""
	cfg = config or LossConfig()
	injections = np.asarray(injections_mw, dtype=np.float64)
	if injections.ndim != 2 or injections.shape[1] != network.n_buses:
		raise ValueError(
			f"injections must be [n_snapshots, {network.n_buses}], got {injections.shape}"
		)
	price = (
		cfg.price_usd_per_mwh if price_usd_per_mwh is None else price_usd_per_mwh
	)

	base_losses, _ = solve_series(network, injections, cfg)
	modified = apply_option(network, option, cfg)
	option_losses, _ = solve_series(modified, injections, cfg)

	reduction_mwh, savings_usd = annual_savings_from_snapshots(
		base_losses, option_losses, price
	)
	if savings_usd < cfg.min_savings_usd_per_year:
		payback: float | None = None
		notes = (
			f"annual savings {savings_usd:.4f} USD are below the measurement "
			f"floor {cfg.min_savings_usd_per_year}; payback is unmeasurable, not "
			f"infinite (07-layer4 §7.2)"
		)
	elif option.capex_usd <= 0.0:
		payback = 0.0
		notes = "no capex; the option pays back immediately"
	else:
		payback = option.capex_usd / savings_usd
		notes = "payback from the summed hourly reduction, not a single snapshot"

	result = MitigationResult(
		option=option.name,
		kind=option.kind,
		capex_usd=option.capex_usd,
		annual_loss_reduction_mwh=reduction_mwh,
		annual_savings_usd=savings_usd,
		payback_years=payback,
		n_snapshots=int(injections.shape[0]),
		notes=notes,
	)
	logger.info(
		"losses.evaluate_option",
		option=option.name,
		reduction_mwh=reduction_mwh,
		savings_usd=savings_usd,
		payback_years=payback,
	)
	return result


def rank_options(
	network: Network,
	injections_mw: NDArray[np.float64],
	options: Sequence[MitigationOption],
	config: LossConfig | None = None,
	*,
	price_usd_per_mwh: NDArray[np.float64] | float | None = None,
) -> list[MitigationResult]:
	"""Evaluate and rank options by payback.

	Unmeasurable options (``payback_years is None``) sort last, behind every
	option with a real payback — an unmeasurable option is not "better than
	everything" the way ``inf`` would place it. The order is deterministic:
	payback ascending, then name ascending, so two runs agree (AD-8).
	"""
	results = [
		evaluate_option(network, injections_mw, option, config, price_usd_per_mwh=price_usd_per_mwh)
		for option in options
	]
	results.sort(
		key=lambda result: (
			result.payback_years is None,
			result.payback_years if result.payback_years is not None else 0.0,
			result.option,
		)
	)
	return results


def rank_payload(results: Sequence[MitigationResult]) -> list[dict[str, object]]:
	"""The ranking as a JSON-ready payload for an artefact."""
	return [result.model_dump(mode="json") for result in results]


__all__ = [
	"annual_savings_from_snapshots",
	"apply_option",
	"evaluate_option",
	"rank_options",
	"rank_payload",
]
