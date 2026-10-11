# SPDX-License-Identifier: MIT
"""N-1 contingency sweep and TLENS.

TLENS — Transmission Lines' contribution to Energy Not Supplied — is, for each
branch, the increase in ENS when that branch is out. It is where the Rust crate
is decisive: 200 lines x 8760 snapshots is 1.75M independent DC solves per year
analysed, hours in Python and minutes in Rust with rayon (07-layer4 §6.4).

The specification's ``compute_tlens`` mutates ``self.n.lines`` in place and
restores it inside the same loop:

```python
self.n.lines.loc[line, "active"] = False
self.n.lines.lpf(snapshot)
...
self.n.lines.loc[line, "active"] = True   # never reached if lpf raises
```

An exception mid-loop leaves the line permanently deactivated and every
*subsequent* contingency is computed on a network that is progressively losing
lines. The results look plausible and describe a network that no longer exists.
The kernel takes branch status as an immutable input and returns results; there
is no mutable network to corrupt. :func:`sweep` re-reads the input arrays after
the call and asserts they are unchanged — the plan's gate
``test_contingency_input_immutable`` canaries exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from alea._core import contingency_sweep
from alea.logging import get_logger
from alea.losses.flow import Network
from alea.losses.views import ContingencySummary, LossConfig, TlensEntry, TlensRanking

logger = get_logger(__name__)


@dataclass(frozen=True)
class SweepResult:
	"""The kernel's sweep output, with the axes named.

	Axis 0 is the contingency (index 0 is the base case, all lines in; index
	``b + 1`` is branch ``b`` out) and axis 1 is the snapshot.
	"""

	energy_not_served_mwh: NDArray[np.float64]
	overloaded_branches: NDArray[np.uint32]
	diverged: NDArray[np.bool_]
	branch_names: tuple[str, ...]

	@property
	def n_contingencies(self) -> int:
		return int(self.energy_not_served_mwh.shape[0])

	@property
	def n_snapshots(self) -> int:
		return int(self.energy_not_served_mwh.shape[1])

	@property
	def base_ens_mwh(self) -> float:
		"""ENS in the base case, summing over snapshots.

		NaN where the base case did not converge is skipped rather than
		propagated: a diverged snapshot contributes no measurable base ENS, and
		turning it into zero would understate the total.
		"""
		base = self.energy_not_served_mwh[0]
		return float(np.nansum(base))

	def ens_with_out(self, branch: int) -> float:
		"""ENS summed over snapshots with one branch out."""
		return float(np.nansum(self.energy_not_served_mwh[branch + 1]))


def sweep(
	network: Network,
	injections_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> SweepResult:
	"""Run the N-1 sweep over a branch table and a snapshot series.

	``injections_mw`` is ``[n_snapshots, n_buses]``. The inputs are asserted
	unchanged after the call: a kernel that mutated its inputs would corrupt
	every later contingency, and the assertion is the canary for that
	regression.
	"""
	cfg = config or LossConfig()
	injections = np.asarray(injections_mw, dtype=np.float64)
	if injections.ndim != 2 or injections.shape[1] != network.n_buses:
		raise ValueError(
			f"injections must be [n_snapshots, {network.n_buses}], got {injections.shape}"
		)
	if cfg.slack_bus >= network.n_buses:
		raise ValueError(f"slack_bus {cfg.slack_bus} outside a {network.n_buses}-bus network")

	before = {
		"susceptance": network.susceptance.copy(),
		"branch_from": network.branch_from.copy(),
		"branch_to": network.branch_to.copy(),
		"branch_susceptance": network.branch_susceptance.copy(),
		"ratings": network.ratings_mw.copy(),
		"injections": injections.copy(),
	}

	raw = contingency_sweep(
		network.susceptance,
		injections,
		network.branch_from,
		network.branch_to,
		network.branch_susceptance,
		network.ratings_mw,
		cfg.slack_bus,
	)
	result = SweepResult(
		energy_not_served_mwh=np.asarray(raw["energy_not_served"], dtype=np.float64),
		overloaded_branches=np.asarray(raw["overloaded_branches"], dtype=np.uint32),
		diverged=np.asarray(raw["diverged"], dtype=bool),
		branch_names=network.branch_names,
	)

	# The gate: the sweep is a pure function of its inputs. A failing
	# contingency is recorded in `diverged` and the sweep continues, so the
	# caller's network must be byte-identical afterwards.
	for name, original in before.items():
		current = {
			"susceptance": network.susceptance,
			"branch_from": network.branch_from,
			"branch_to": network.branch_to,
			"branch_susceptance": network.branch_susceptance,
			"ratings": network.ratings_mw,
			"injections": injections,
		}[name]
		if not np.array_equal(current, original):
			raise RuntimeError(
				f"contingency_sweep mutated its input {name!r}; a mutated input "
				f"corrupts every later contingency (07-layer4 §6.1)"
			)
	logger.info(
		"losses.sweep",
		contingencies=result.n_contingencies,
		snapshots=result.n_snapshots,
		base_ens_mwh=result.base_ens_mwh,
		diverged_fraction=float(result.diverged.mean()),
	)
	return result


def tlens(
	network: Network,
	injections_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> TlensRanking:
	"""Rank branches by their contribution to energy not supplied.

	The ranking is deterministic (AD-8): entries sort by ENS increase descending
	and, on ties, by branch index ascending, so two runs of the same network
	produce the same order regardless of how the sort happened to break ties.

	A branch whose outages **all** diverge has no measurable ENS — the solve
	found no path, which is a more severe finding than a large ENS, not a
	smaller one. Such branches are ranked by the fraction of diverged snapshots
	so they sort to the top rather than to the bottom.
	"""
	cfg = config or LossConfig()
	result = sweep(network, injections_mw, cfg)
	base = result.base_ens_mwh
	entries: list[TlensEntry] = []
	for branch in range(network.n_branches):
		with_out = result.ens_with_out(branch)
		increase = with_out - base
		diverged = int(result.diverged[branch + 1].sum())
		if diverged == result.n_snapshots:
			# No finite ENS to compare; keep the increase as NaN so the ranking
			# can order these branches by severity rather than by a spurious
			# zero.
			increase = float("nan")
		entries.append(
			TlensEntry(
				branch=branch,
				branch_name=network.name_of(branch),
				from_bus=int(network.branch_from[branch]),
				to_bus=int(network.branch_to[branch]),
				ens_with_out_mwh=with_out,
				ens_increase_mwh=increase,
				diverged_snapshots=diverged,
				overloaded_snapshots=int(result.overloaded_branches[branch + 1].sum()),
			)
		)

	def sort_key(entry: TlensEntry) -> tuple[float, float, int]:
		# Diverged branches first (by diverged fraction), then finite increases
		# descending, then branch index ascending for a stable tie-break.
		diverged_fraction = entry.diverged_snapshots / max(result.n_snapshots, 1)
		finite = entry.ens_increase_mwh if np.isfinite(entry.ens_increase_mwh) else -np.inf
		return (-diverged_fraction, -finite, entry.branch)

	entries.sort(key=sort_key)
	finite_total = float(
		np.nansum([entry.ens_increase_mwh for entry in entries if np.isfinite(entry.ens_increase_mwh)])
	)
	ranked: list[TlensEntry] = []
	for entry in entries:
		share = (
			entry.ens_increase_mwh / finite_total
			if np.isfinite(entry.ens_increase_mwh) and finite_total > 0
			else 0.0
		)
		ranked.append(entry.model_copy(update={"share": float(share)}))

	ranking = TlensRanking(
		entries=ranked,
		base_ens_mwh=base,
		n_snapshots=result.n_snapshots,
		n_branches=network.n_branches,
		total_ens_mwh=finite_total,
		parameters={
			"slack_bus": cfg.slack_bus,
			"n_snapshots": result.n_snapshots,
			"n_branches": network.n_branches,
		},
	)
	logger.info(
		"losses.tlens",
		branches=network.n_branches,
		total_ens_mwh=finite_total,
		worst=ranking.entries[0].branch_name if ranking.entries else "",
	)
	return ranking


def summary(
	network: Network,
	injections_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> ContingencySummary:
	"""A compact N-1 summary for an artefact sidecar."""
	cfg = config or LossConfig()
	result = sweep(network, injections_mw, cfg)
	ens_by_contingency = np.nansum(result.energy_not_served_mwh, axis=1)
	worst = int(np.argmax(ens_by_contingency))
	return ContingencySummary(
		n_contingencies=result.n_contingencies,
		n_snapshots=result.n_snapshots,
		base_ens_mwh=float(ens_by_contingency[0]),
		worst_contingency=worst,
		worst_ens_mwh=float(ens_by_contingency[worst]),
		diverged_fraction=float(result.diverged.mean()),
		overloaded_fraction=float((result.overloaded_branches > 0).mean()),
		parameters={"slack_bus": cfg.slack_bus},
	)


def tlens_payload(ranking: TlensRanking) -> dict[str, Any]:
	"""The ranking as a JSON-ready payload for an artefact."""
	return {
		"base_ens_mwh": ranking.base_ens_mwh,
		"total_ens_mwh": ranking.total_ens_mwh,
		"n_snapshots": ranking.n_snapshots,
		"n_branches": ranking.n_branches,
		"parameters": ranking.parameters,
		"entries": [entry.model_dump(mode="json") for entry in ranking.entries],
	}


__all__ = [
	"SweepResult",
	"summary",
	"sweep",
	"tlens",
	"tlens_payload",
]
