# SPDX-License-Identifier: MIT
"""Loss-optimal line switching: the reference topology the decomposition needs.

`docs/plans/07-layer4-predictive.md` §6.2 names this kernel and nothing
implemented it: the topology-driven loss component is "the loss difference
between the current network and a loss-optimal topology (optimal line
switching), computed with the DC flow the crate already provides". Three
registers cite the same absence -- `reporting.producers.UNPRODUCED` for
``loss_decomposition`` and ``loss_statistics``, and `publish.views.UNWIRED` for
``data/processed/losses/decomposition.parquet`` -- and every one of them
describes the symptom rather than the cause. The symptom is a decomposition
that reads ``load driven == total`` for every network, because
``reference_network`` defaulted to the actual network and ``topology_network``
to the reference, so ``T - R`` was zero by construction.

**What "optimal" is earned over, and what it is not.** The search enumerates
every subset of branches of size at most ``LossConfig.switching_max_openings``,
up to ``switching_max_evaluations`` solves. At one opening, with a budget the
network fits, that is the *exact* loss-minimising single-switching topology and
``truncated`` is False. At two or more the enumeration is exhaustive in the same
sense but the budget binds quickly, and ``truncated`` records that rather than
letting a caller read a partial answer as an optimal one.

**An opening that islands the network is infeasible, not a crash.** Removing a
branch can disconnect a bus, which makes the susceptance matrix singular; the
kernel raises rather than returning a zero angle, because a zero angle reads as
"no flow" instead of "no path". An islanded topology serves nothing, so it
cannot be loss-optimal. It is counted in ``n_infeasible`` and skipped.

**Why the branch susceptance is zeroed and not only the matrix.** The standard
stamp subtracts a branch from B, and a branch that keeps its susceptance still
has ``branch_flows`` compute a flow across it from the bus angles. Measured on
the four-bus meshed fixture: stamping B alone leaves the out branch carrying
152.7 MW and charges the network 1.07 MW of loss on a line that is open. An
opened branch carries no flow, so its susceptance is zero *and* its stamp is
absent; :func:`open_branches` does both, and
`tests/ci/test_loss_switching.py` gates the phantom.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.losses.flow import Network, solve_snapshot, susceptance_matrix
from alea.losses.views import LossConfig, SwitchingResult

logger = get_logger(__name__)

_IMPROVEMENT_TOLERANCE = 1e-9
"""Relative floor below which a candidate is not an improvement.

A solve is an LU factorisation of a dense matrix, so two topologies whose losses
differ by 1e-15 differ by rounding rather than by physics. Taking such a
candidate would put a switching decision in a published report that the network
does not support."""


def switching_candidates(network: Network) -> NDArray[np.int64]:
	"""The branches whose opening could change a solve.

	A branch whose susceptance is already zero carries no flow, so opening it
	changes nothing and a search that offered it would report "opening this line
	reduces loss by 0.0 MW" for a line that is already out -- a finding about
	the candidate list presented as a finding about the network.
	"""
	susceptance = np.asarray(network.branch_susceptance, dtype=np.float64)
	eligible = np.flatnonzero(np.isfinite(susceptance) & (susceptance > 0.0))
	assert eligible.ndim == 1, f"candidates must be one-dimensional, got {eligible.shape}"
	return eligible.astype(np.int64)


def open_branches(network: Network, branches: object) -> Network:
	"""A new network with ``branches`` open: susceptance zeroed, matrix rebuilt.

	Returns the caller's network unchanged when nothing is opened, so a search
	that finds no improvement does not hand back a copy a reader might mistake
	for a different topology.
	"""
	opened = np.asarray(sorted({int(branch) for branch in branches}), dtype=np.int64)  # type: ignore[union-attr]
	if opened.size == 0:
		return network
	if opened.min() < 0 or opened.max() >= network.n_branches:
		raise IndexError(f"branch indices {opened.tolist()} outside [0, {network.n_branches})")
	branch_susceptance = network.branch_susceptance.copy()
	branch_susceptance[opened] = 0.0
	return Network(
		susceptance=susceptance_matrix(
			network.branch_from,
			network.branch_to,
			branch_susceptance,
			network.n_buses,
		),
		branch_from=network.branch_from,
		branch_to=network.branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=network.resistance_ohm,
		voltage_kv=network.voltage_kv,
		ratings_mw=network.ratings_mw,
		branch_names=network.branch_names,
	)


def _loss_at(network: Network, injection: NDArray[np.float64], config: LossConfig) -> float | None:
	"""The loss for one topology, or ``None`` when the topology cannot serve.

	``None`` rather than an infinity: an islanded topology has no loss to
	compare, and returning ``inf`` would let it sort as merely expensive when
	the honest statement is that it does not solve.
	"""
	try:
		value = solve_snapshot(network, injection, config).losses_mw
	except (RuntimeError, ValueError) as exc:
		logger.debug("losses.switching.infeasible", reason=str(exc))
		return None
	return value if math.isfinite(value) else None


def optimal_switching(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	config: LossConfig | None = None,
	*,
	search_dispatch_mw: NDArray[np.float64] | None = None,
) -> tuple[Network, SwitchingResult]:
	"""The loss-minimising switching topology, and the search that found it.

	``search_dispatch_mw`` is the dispatch the topology is chosen *at*. It
	defaults to the mean injection across the series -- the same reference
	:func:`alea.losses.decompose.measure` attributes against -- so the topology
	the reference case uses is chosen under the reference case's own loading
	rather than under the peak's.

	Returns the switched :class:`Network` and the :class:`SwitchingResult`. The
	network is the caller's own object when no opening improved on leaving every
	line in, which is a real answer: a network with no loss-reducing
	reconfiguration has ``topology_driven == 0`` because the topology is already
	optimal, not because nothing looked.
	"""
	cfg = config or LossConfig()
	dispatch = np.asarray(dispatch_mw, dtype=np.float64)
	if dispatch.ndim != 2 or dispatch.shape[1] != network.n_buses:
		raise ValueError(
			f"dispatch must be [n_snapshots, {network.n_buses}], got {dispatch.shape}"
		)
	if search_dispatch_mw is None:
		from alea.losses.decompose import reference_injection

		# The *vector*, not `flat_reference_dispatch`: the search solves one
		# snapshot, and the flat matrix is the same mean repeated -- which
		# `solve_snapshot` refuses as a wrong-shaped injection. Handing it the
		# matrix was the first spelling here, and it made every search report the
		# all-lines-in network as unsolvable.
		search = reference_injection(dispatch)
		searched_at = "flat_mean"
	else:
		search = np.asarray(search_dispatch_mw, dtype=np.float64)
		if search.shape != (network.n_buses,):
			raise ValueError(
				f"search dispatch must be ({network.n_buses},), got {search.shape}"
			)
		searched_at = "caller"

	baseline = _loss_at(network, search, cfg)
	if baseline is None:
		raise ValueError(
			"the all-lines-in network does not solve, so no switching topology can "
			"be compared against it; the dispatch and the network came from "
			"different solves or the network is already islanded"
		)

	candidates = switching_candidates(network)
	best_loss = baseline
	best: tuple[int, ...] = ()
	evaluated = 0
	infeasible = 0
	truncated = False

	if cfg.switching_max_openings > 0 and candidates.size:
		for size in range(1, cfg.switching_max_openings + 1):
			for combination in itertools.combinations(candidates.tolist(), size):
				if evaluated >= cfg.switching_max_evaluations:
					truncated = True
					break
				evaluated += 1
				loss = _loss_at(open_branches(network, combination), search, cfg)
				if loss is None:
					infeasible += 1
					continue
				if loss < best_loss - abs(best_loss) * _IMPROVEMENT_TOLERANCE - 1e-12:
					best_loss = loss
					best = combination
			if truncated:
				break

	result = SwitchingResult(
		opened=list(best),
		opened_names=[network.name_of(branch) for branch in best],
		reference_loss_mw=baseline,
		switched_loss_mw=best_loss,
		reduction_mw=baseline - best_loss,
		n_candidates=int(candidates.size),
		n_evaluated=evaluated,
		n_infeasible=infeasible,
		max_openings=cfg.switching_max_openings,
		truncated=truncated,
		search_dispatch=searched_at,
	)
	logger.info(
		"losses.switching",
		opened=result.opened_names,
		reduction_mw=result.reduction_mw,
		evaluated=evaluated,
		infeasible=infeasible,
		truncated=truncated,
	)
	return open_branches(network, best), result


__all__ = [
	"open_branches",
	"optimal_switching",
	"switching_candidates",
]
