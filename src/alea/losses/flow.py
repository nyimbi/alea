# SPDX-License-Identifier: MIT
"""DC power flow and transmission-loss measurement.

A thin wrapper over the ``alea-losses`` kernel. The wrapper's job is to hold the
units straight and to assert the shapes, because the kernel takes arrays and
knows nothing about bus names.

Units, stated once because a function returning ``float`` whose doc does not say
MW or MWh is a bug waiting for a report:

* ``susceptance`` — the bus susceptance matrix B, per unit.
* ``injection_mw`` — net injection at each bus, MW.
* ``flows_mw`` — branch flows, MW.
* ``resistance_ohm`` — branch resistance, ohms.
* ``voltage_kv`` — nominal voltage, kV.
* losses — MW, from ``I^2 R`` with ``I = P / (sqrt(3) V)``.

The DC approximation is checked against an AC solve on the Kenya fixture
(07-layer4 §6.3); the reference implementation is the one place in the platform
that may depend on pypsa's AC power flow, because it is checking ALEA's
approximation against the physics rather than reproducing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from alea._core import branch_flows, dc_power_flow, transmission_losses
from alea.logging import get_logger
from alea.losses.views import FlowResult, LoadingEntry, LoadingRanking, LossConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class Network:
	"""The arrays a DC solve needs, with the names kept alongside.

	Held as arrays rather than as a pypsa Network because the boundary is the
	artefact, not the object (AD-2): the kernel takes arrays and returns arrays,
	and a wrapper that passes a live network across it has thrown the advantage
	away.
	"""

	susceptance: NDArray[np.float64]
	"""``[n_buses, n_buses]`` bus susceptance matrix, per unit."""

	branch_from: NDArray[np.uint32]
	branch_to: NDArray[np.uint32]
	branch_susceptance: NDArray[np.float64]
	resistance_ohm: NDArray[np.float64]
	voltage_kv: NDArray[np.float64]
	ratings_mw: NDArray[np.float64]
	branch_names: tuple[str, ...] = ()

	def __post_init__(self) -> None:
		n_buses = self.susceptance.shape[0]
		if self.susceptance.shape != (n_buses, n_buses):
			raise ValueError(f"susceptance must be square, got {self.susceptance.shape}")
		n_branches = self.branch_from.shape[0]
		for name in (
			"branch_to",
			"branch_susceptance",
			"resistance_ohm",
			"voltage_kv",
			"ratings_mw",
		):
			value = getattr(self, name)
			if value.shape != (n_branches,):
				raise ValueError(f"{name} must be ({n_branches},), got {value.shape}")
		if self.branch_from.max(initial=0) >= n_buses or self.branch_to.max(initial=0) >= n_buses:
			raise ValueError(f"a branch indexes a bus >= {n_buses}")
		if self.branch_names and len(self.branch_names) != n_branches:
			raise ValueError(
				f"{len(self.branch_names)} branch names for {n_branches} branches"
			)

	@property
	def n_buses(self) -> int:
		return int(self.susceptance.shape[0])

	@property
	def n_branches(self) -> int:
		return int(self.branch_from.shape[0])

	def name_of(self, branch: int) -> str:
		"""A branch's name, or its index as a string."""
		if 0 <= branch < len(self.branch_names):
			return self.branch_names[branch]
		return f"branch_{branch}"

	def branch_index(self, name: str) -> int:
		"""The index of a named branch. Raises when the name is unknown."""
		try:
			return self.branch_names.index(name)
		except ValueError:
			raise KeyError(f"no branch named {name!r}") from None


def solve_snapshot(
	network: Network,
	injection_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> FlowResult:
	"""One DC solve: bus angles, branch flows, and transmission losses.

	The slack bus is taken from the config, so the reference angle is a recorded
	parameter rather than whatever the kernel's default happens to be.
	"""
	cfg = config or LossConfig()
	injection = np.asarray(injection_mw, dtype=np.float64)
	if injection.shape != (network.n_buses,):
		raise ValueError(
			f"injection must be ({network.n_buses},), got {injection.shape}"
		)
	if cfg.slack_bus >= network.n_buses:
		raise ValueError(
			f"slack_bus {cfg.slack_bus} is outside a {network.n_buses}-bus network"
		)

	angles = dc_power_flow(network.susceptance, injection, cfg.slack_bus)
	flows = branch_flows(
		angles, network.branch_from, network.branch_to, network.branch_susceptance
	)
	losses = transmission_losses(flows, network.resistance_ohm, network.voltage_kv)
	generation = float(injection[injection > 0].sum())
	fraction = losses / generation if generation > 0 else float("nan")

	assert angles.shape == (network.n_buses,)
	assert flows.shape == (network.n_branches,)
	assert losses >= 0.0, f"transmission losses cannot be negative, got {losses}"
	return FlowResult(
		angles_rad=[float(value) for value in angles],
		flows_mw=[float(value) for value in flows],
		losses_mw=float(losses),
		loss_fraction=float(fraction),
		slack_bus=cfg.slack_bus,
		n_buses=network.n_buses,
		n_branches=network.n_branches,
	)


def solve_series(
	network: Network,
	injections_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
	"""Solve every snapshot, returning ``(losses_mw, loss_fraction)`` per snapshot.

	Losses are computed per snapshot from that snapshot's flows. This is what
	makes the mitigation ranking honest: a loss reduction summed over the actual
	hourly series, not one snapshot multiplied by 8760 (07-layer4 §7.1).

	The values are **MW**, not MWh: one DC solve yields the loss at an instant.
	Converting to energy is the caller's job, and it needs
	``LossConfig.snapshot_hours`` to do it.
	"""
	cfg = config or LossConfig()
	matrix = np.asarray(injections_mw, dtype=np.float64)
	if matrix.ndim != 2 or matrix.shape[1] != network.n_buses:
		raise ValueError(
			f"injections must be [n_snapshots, {network.n_buses}], got {matrix.shape}"
		)
	losses = np.zeros(matrix.shape[0], dtype=np.float64)
	fractions = np.zeros(matrix.shape[0], dtype=np.float64)
	for index in range(matrix.shape[0]):
		result = solve_snapshot(network, matrix[index], cfg)
		losses[index] = result.losses_mw
		fractions[index] = result.loss_fraction
	assert losses.shape == (matrix.shape[0],)
	return losses, fractions


def loading_series(
	network: Network,
	injections_mw: NDArray[np.float64],
	config: LossConfig | None = None,
	*,
	threshold: float = 1.0,
) -> LoadingRanking:
	"""Branch loading against each branch's own rating, over a snapshot series.

	``|p0| / s_nom`` per branch per snapshot, which is the kernel the
	``critical_lines`` report section's blocker named: the section asks for each
	line's peak loading and the hours it spent at or above rating, and neither
	the TLENS ranking (unserved energy and overload *counts*) nor the market
	layer's ``CorridorResult.loading`` (a cleared corridor) is that quantity.

	**Why this is a kernel and not a projection.** The network arrays carry
	``ratings_mw`` and the dispatch carries the injections, so the two inputs
	exist -- but nothing computes the ratio. Deriving it in the report would put
	a DC solve in Layer 6, which computes nothing; deriving it in the projection
	would give the API and the report two implementations of one number.

	**The unit trap, and the fixture that discriminates it.** ``hours_at_or_above``
	is hours, so it is the snapshot *count* times ``LossConfig.snapshot_hours``.
	For an hourly series the count and the hours are the same integer and a test
	written on one cannot tell a correct implementation from the count. The
	caller's resolution is what makes them differ.

	**A branch with no rating is not a branch loaded at zero.** ``ratings_mw``
	defaults to ``inf`` for a line whose ``s_nom`` is absent
	(``alea.planning.arrays``), and ``x / inf`` is 0.0 -- which would print a
	critical-line table saying every unrated line sits at 0% loading. Those
	branches are excluded from the ranking and counted in ``n_unrated``; a
	network with *no* rated branch raises, because an empty ranking there would
	read as "nothing is overloaded".
	"""
	cfg = config or LossConfig()
	matrix = np.asarray(injections_mw, dtype=np.float64)
	if matrix.ndim != 2 or matrix.shape[1] != network.n_buses:
		raise ValueError(
			f"injections must be [n_snapshots, {network.n_buses}], got {matrix.shape}"
		)
	if threshold <= 0.0:
		raise ValueError(f"threshold must be positive, got {threshold}")

	ratings = network.ratings_mw
	rated = np.isfinite(ratings) & (ratings > 0.0)
	if not np.any(rated):
		raise ValueError(
			f"no branch carries a finite positive rating; every one of the "
			f"{network.n_branches} branches has s_nom absent, infinite or zero. A "
			f"loading is |p0| / s_nom and there is no s_nom to divide by -- an "
			f"empty critical-line list here would read as 'nothing is overloaded'"
		)
	if np.any(ratings[np.isfinite(ratings)] <= 0.0):
		bad = np.flatnonzero(np.isfinite(ratings) & (ratings <= 0.0))
		raise ValueError(
			f"branches {bad.tolist()} carry a non-positive rating; a branch that "
			f"can carry nothing is a data error, not an infinite loading"
		)

	# One solve per snapshot, accumulated into a [n_snapshots, n_branches] flow
	# matrix. Looping branches outside would re-solve the network once per
	# branch, which is n_branches times the work for the same answer.
	flows = np.full((matrix.shape[0], network.n_branches), np.nan, dtype=np.float64)
	for index in range(matrix.shape[0]):
		flows[index] = solve_snapshot(network, matrix[index], cfg).flows_mw

	loading = np.abs(flows) / np.where(rated, ratings, np.nan)
	finite = np.isfinite(loading)
	entries: list[LoadingEntry] = []
	for branch in range(network.n_branches):
		if not rated[branch]:
			continue
		column = loading[:, branch]
		usable = column[finite[:, branch]]
		diverged = int(matrix.shape[0] - usable.size)
		peak = float(np.max(usable)) if usable.size else float("nan")
		at_or_above = int(np.count_nonzero(usable >= threshold))
		entries.append(
			LoadingEntry(
				branch=branch,
				branch_name=network.name_of(branch),
				from_bus=int(network.branch_from[branch]),
				to_bus=int(network.branch_to[branch]),
				peak_loading=peak,
				hours_at_or_above=float(at_or_above) * cfg.snapshot_hours,
				peak_flow_mw=float(peak * ratings[branch]) if np.isfinite(peak) else float("nan"),
				rating_mw=float(ratings[branch]),
				snapshots_at_or_above=at_or_above,
				diverged_snapshots=diverged,
			)
		)

	entries.sort(key=lambda entry: (-entry.peak_loading, entry.branch))
	ranking = LoadingRanking(
		entries=[entry for entry in entries if entry.peak_loading >= threshold],
		n_snapshots=int(matrix.shape[0]),
		n_branches=network.n_branches,
		n_rated=int(np.count_nonzero(rated)),
		threshold=threshold,
		parameters={
			"slack_bus": cfg.slack_bus,
			"snapshot_hours": cfg.snapshot_hours,
			"n_snapshots": int(matrix.shape[0]),
			"threshold": threshold,
		},
	)
	logger.info(
		"losses.loading",
		branches=network.n_branches,
		rated=ranking.n_rated,
		above=len(ranking.entries),
		worst=ranking.worst_loading,
	)
	return ranking


def losses_with_branch_out(
	network: Network,
	injection_mw: NDArray[np.float64],
	branch: int,
	config: LossConfig | None = None,
) -> float:
	"""Transmission loss with one branch removed from the susceptance matrix.

	The outaged branch's contribution is subtracted from B by the standard
	stamp ``B_ii -= b, B_jj -= b, B_ij += b, B_ji += b``, on a **copy**. The
	caller's network is untouched: the specification's in-place mutation is the
	bug the Rust crate exists to avoid (07-layer4 §6.1), and re-deriving it here
	would reintroduce it in Python.
	"""
	cfg = config or LossConfig()
	if not 0 <= branch < network.n_branches:
		raise IndexError(f"branch {branch} outside [0, {network.n_branches})")
	susceptance = network.susceptance.copy()
	from_bus = int(network.branch_from[branch])
	to_bus = int(network.branch_to[branch])
	value = float(network.branch_susceptance[branch])
	susceptance[from_bus, from_bus] -= value
	susceptance[to_bus, to_bus] -= value
	susceptance[from_bus, to_bus] += value
	susceptance[to_bus, from_bus] += value

	outaged = Network(
		susceptance=susceptance,
		branch_from=network.branch_from,
		branch_to=network.branch_to,
		branch_susceptance=network.branch_susceptance,
		resistance_ohm=network.resistance_ohm,
		voltage_kv=network.voltage_kv,
		ratings_mw=network.ratings_mw,
		branch_names=network.branch_names,
	)
	return solve_snapshot(outaged, injection_mw, cfg).losses_mw


def susceptance_matrix(
	branch_from: NDArray[np.uint32],
	branch_to: NDArray[np.uint32],
	branch_susceptance: NDArray[np.float64],
	n_buses: int,
) -> NDArray[np.float64]:
	"""Assemble the bus susceptance matrix from the branch list.

	``B[i, i] += b`` for each branch, ``B[i, j] -= b`` across it. Kept here
	rather than in Rust because it is O(n_branches) and runs once per network,
	not once per snapshot.
	"""
	matrix = np.zeros((n_buses, n_buses), dtype=np.float64)
	for index in range(branch_from.shape[0]):
		i = int(branch_from[index])
		j = int(branch_to[index])
		value = float(branch_susceptance[index])
		matrix[i, i] += value
		matrix[j, j] += value
		matrix[i, j] -= value
		matrix[j, i] -= value
	return matrix


def network_from_tables(
	buses: Any,
	branches: Any,
	*,
	from_column: str = "bus0",
	to_column: str = "bus1",
	susceptance_column: str = "susceptance_pu",
	resistance_column: str = "resistance_ohm",
	voltage_column: str = "voltage_kv",
	rating_column: str = "rating_mw",
	name_column: str = "name",
) -> Network:
	"""Build a :class:`Network` from a bus index and a branch table.

	``buses`` is a sequence of bus identifiers; ``branches`` is a dataframe whose
	``from_column`` and ``to_column`` name buses. A branch naming an unknown bus
	raises rather than being dropped, because a dropped branch is a silently
	different network.

	Every default below is a network property, not a solver policy, so there is
	no ``config`` parameter: one was accepted here and read nowhere, which made
	it a knob a caller would set and a reader would believe.
	"""
	import pandas as pd

	bus_list = [str(value) for value in buses]
	index = {name: position for position, name in enumerate(bus_list)}
	frame = pd.DataFrame(branches)
	for column in (from_column, to_column):
		if column not in frame.columns:
			raise KeyError(f"branch table has no {column!r} column: {list(frame.columns)}")
	unknown = set(frame[from_column].astype(str)) | set(frame[to_column].astype(str))
	unknown -= set(index)
	if unknown:
		raise KeyError(f"branches reference unknown buses: {sorted(unknown)}")

	def column_or(default: float, name: str) -> NDArray[np.float64]:
		if name in frame.columns:
			return frame[name].to_numpy(dtype=float)
		return np.full(len(frame), default, dtype=np.float64)

	def bus_indices(name: str) -> NDArray[np.uint32]:
		"""Positional bus indices for one branch column, as uint32.

		The lookup is written as a comprehension rather than `Series.map(index)`:
		`map` with a dict is a lookup, but pandas-stubs types the argument as a
		callable. The unknown-bus check above guarantees every value is a key, so
		a KeyError here would mean that check was bypassed.
		"""
		return np.asarray([index[str(value)] for value in frame[name]], dtype=np.uint32)

	susceptance = column_or(0.0, susceptance_column)
	if np.any(susceptance == 0.0):
		raise ValueError(
			f"{susceptance_column} has zero entries; a branch with no susceptance "
			f"carries no flow and does not belong in the network"
		)
	return Network(
		susceptance=susceptance_matrix(
			bus_indices(from_column),
			bus_indices(to_column),
			susceptance,
			len(bus_list),
		),
		branch_from=bus_indices(from_column),
		branch_to=bus_indices(to_column),
		branch_susceptance=susceptance,
		resistance_ohm=column_or(0.01, resistance_column),
		voltage_kv=column_or(132.0, voltage_column),
		ratings_mw=column_or(np.inf, rating_column),
		branch_names=tuple(
			frame[name_column].astype(str).tolist() if name_column in frame.columns else ()
		),
	)


__all__ = [
	"Network",
	"loading_series",
	"losses_with_branch_out",
	"network_from_tables",
	"solve_series",
	"solve_snapshot",
	"susceptance_matrix",
]
