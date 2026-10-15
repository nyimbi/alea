# SPDX-License-Identifier: MIT
"""Single-period hourly dispatch.

Dispatch takes a solved (or fixed) capacity mix and asks how it operates hour by
hour. The difference from expansion is that nothing is extendable: capacity is
given, so the problem is a linear program in the operating variables and it
solves in seconds rather than hours.

Two things here are checks rather than modelling. The energy balance is verified
after the solve, because a dispatch that does not balance means a load was
attached to a bus the solver never saw. And the curtailment figure is reported,
because a model that curtails 40% of its solar is telling you something about
the network, not about the sun.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea.config.models import Config
from alea.logging import get_logger
from alea.planning.expansion import check_solver_available, has_dispatch
from alea.provenance.models import Basis, DerivedProvenance

_log = get_logger(__name__)


class DispatchError(RuntimeError):
	"""The dispatch problem cannot be built or solved."""


def _has_dispatchable_capacity(network: pypsa.Network) -> bool:
	"""Whether any generator, storage unit or link can serve load at all.

	Reads nominal capacity, not availability: a generator with ``p_nom`` of
	zero can serve nothing, and that is the state freezing leaves an unsolved
	network in. Lines are excluded deliberately -- a line with no ``s_nom``
	still carries what the buses inject, so a network of zero-capacity lines is
	degenerate but not undispatchable, while a network of zero-capacity
	generators cannot serve a single MW of load.
	"""
	assert network is not None, "network must not be None"
	for component in ("generators", "storage_units", "links"):
		table = getattr(network, component, None)
		if table is None or not len(table):
			continue
		for column in ("p_nom", "p_nom_opt"):
			if column in table.columns and float(table[column].astype(float).sum()) > 0.0:
				return True
	return False


@dataclass
class DispatchResult:
	"""What a dispatch produced, including the checks."""

	objective: float
	seconds: float
	total_generation_mwh: float
	total_load_mwh: float
	energy_balance_error_mwh: float
	curtailment_mwh: float
	curtailment_share: float
	peak_generation_mw: float
	unserved_energy_mwh: float

	def as_dict(self) -> dict[str, Any]:
		return {
			"objective": self.objective,
			"seconds": self.seconds,
			"total_generation_mwh": self.total_generation_mwh,
			"total_load_mwh": self.total_load_mwh,
			"energy_balance_error_mwh": self.energy_balance_error_mwh,
			"curtailment_mwh": self.curtailment_mwh,
			"curtailment_share": self.curtailment_share,
			"peak_generation_mw": self.peak_generation_mw,
			"unserved_energy_mwh": self.unserved_energy_mwh,
		}


def freeze_capacity(network: pypsa.Network) -> int:
	"""Turn every extendable component into a fixed one at its optimal size.

	Dispatch must not be allowed to build. Leaving a component extendable and
	solving without investment periods lets the optimiser add capacity at zero
	cost in the last period, which reads as a dispatch result and is an
	expansion one.

	Freezing reads ``p_nom_opt``, and on a network that was never solved that
	column is **0.0** -- PyPSA initialises it to zero rather than to ``nan``.
	So freezing an unsolved network does not preserve the capacity it declares,
	it discards it.

	That is usually harmless, and deliberately so: a network `build_network`
	produces is a supported dispatch input (`test_the_built_network_solves_a_
	dispatch` asserts it), and it carries its fixed fleet alongside extendable
	VRE at ``p_nom=0.0``, so freezing the VRE to zero is the identity on a
	network whose coal still serves the load. What is *not* harmless is the case
	where the extendable components are the only capacity there is: freezing
	then leaves a network with load and nothing to serve it, and the solve
	returns ``status='warning' (infeasible)`` -- an error that names the solver
	for a problem that is a missing solve. The refusal is conditioned on that
	consequence rather than on the mere presence of an extendable component.
	"""
	assert network is not None, "network must not be None"
	frozen = 0
	for component in ("generators", "storage_units", "stores", "links", "lines"):
		table = getattr(network, component, None)
		if table is None or not len(table):
			continue
		if "p_nom_extendable" in table.columns:
			extendable = table["p_nom_extendable"].astype(bool)
			if extendable.any():
				table.loc[extendable, "p_nom"] = table.loc[extendable, "p_nom_opt"]
				table.loc[extendable, "p_nom_extendable"] = False
				frozen += int(extendable.sum())
		if "s_nom_extendable" in table.columns:
			extendable = table["s_nom_extendable"].astype(bool)
			if extendable.any():
				table.loc[extendable, "s_nom"] = table.loc[extendable, "s_nom_opt"]
				table.loc[extendable, "s_nom_extendable"] = False
				frozen += int(extendable.sum())
		if "e_nom_extendable" in table.columns:
			extendable = table["e_nom_extendable"].astype(bool)
			if extendable.any():
				table.loc[extendable, "e_nom"] = table.loc[extendable, "e_nom_opt"]
				table.loc[extendable, "e_nom_extendable"] = False
				frozen += int(extendable.sum())
	_log.info("capacity_frozen", components=frozen)
	return frozen


def solve_dispatch(
	network: pypsa.Network,
	config: Config,
	*,
	freeze: bool = True,
) -> DispatchResult:
	"""Solve hourly dispatch on a network with fixed capacity."""
	assert network is not None, "network must not be None"
	assert len(network.buses) > 0, "network has no buses"
	assert len(network.loads) > 0, "network has no loads; there is nothing to dispatch against"
	if freeze:
		frozen = freeze_capacity(network)
		# Freezing an unsolved network discards the capacity it declared, because
		# ``p_nom_opt`` is 0.0 until a solve sets it. When the extendable
		# components were the only capacity, the result is a network with load
		# and nothing to serve it, and HiGHS then reports ``status='warning'
		# (infeasible)`` -- an error that names the solver for a problem that is
		# a missing solve. Checked here rather than inside `freeze_capacity`
		# because the predicate is "did freezing leave anything to generate
		# with", which is a fact about the network *after* the freeze.
		if frozen and not _has_dispatchable_capacity(network):
			raise DispatchError(
				f"freezing discarded all {frozen} extendable component(s): "
				"`p_nom_opt` is 0.0 on a network that has never been solved, so "
				"freezing deletes capacity rather than fixing it. Solve it first "
				"(`alea solve`), or give the input network fixed capacity."
			)

	solver = config.solve.solver
	check_solver_available(solver)
	options: dict[str, Any] = dict(config.solve.solver_options)
	options.setdefault("threads", 1)
	options.setdefault("random_seed", 0)
	options.setdefault("time_limit", float(config.solve.solver_timeout_s))

	start = time.perf_counter()
	try:
		status, condition = network.optimize(
			solver_name=solver,
			transmission_losses=config.solve.transmission_losses,
			linearized_unit_commitment=config.solve.linearized_unit_commitment,
			multi_investment_periods=False,
			solver_options=options,
			include_objective_constant=False,
		)
	except Exception as exc:  # noqa: BLE001
		raise DispatchError(f"{solver} failed to dispatch: {exc}") from exc
	seconds = time.perf_counter() - start
	if status not in ("ok", "optimal", "Optimal"):
		raise DispatchError(f"{solver} returned status={status!r} ({condition})")

	# `status` above is optimal, so a solution exists and the objective is set.
	# pypsa types it `float | None` because an unsolved network has neither, and
	# this assertion is also the runtime check that the two agree.
	assert network.objective is not None, f"{solver} reported {status!r} but set no objective"
	checks = check_energy_balance(network)
	result = DispatchResult(
		objective=float(network.objective),
		seconds=seconds,
		total_generation_mwh=checks["generation_mwh"],
		total_load_mwh=checks["load_mwh"],
		energy_balance_error_mwh=checks["error_mwh"],
		curtailment_mwh=checks["curtailment_mwh"],
		curtailment_share=checks["curtailment_share"],
		peak_generation_mw=checks["peak_mw"],
		unserved_energy_mwh=checks["unserved_mwh"],
	)
	_log.info(
		"dispatch_solved",
		objective=result.objective,
		seconds=round(seconds, 2),
		curtailment_share=round(result.curtailment_share, 4),
		balance_error_mwh=result.energy_balance_error_mwh,
	)
	return result


def balance_measurement(network: pypsa.Network) -> dict[str, float]:
	"""Measure the energy balance without refusing anything.

	Split out from :func:`check_energy_balance` so the residual can be *carried*
	on a solved result as well as *refused* at solve time. The two callers want
	different things from the same arithmetic: a solve that fails the balance is
	a bug and must stop, while a report should record how far off it was rather
	than say nothing because the number happened not to clear a threshold. A
	check with no caller measured nothing, which is why this exists.

	A dispatch that does not balance means a load was attached to a bus the
	model does not contain, or a generator was added outside the network's
	component tables. Both produce an objective that looks fine.
	"""
	assert network is not None, "network must not be None"
	if not has_dispatch(network):
		raise DispatchError("network has no dispatch; solve it first")

	generation = float(network.generators_t.p.to_numpy().sum())
	# A dynamic ``loads_t.p_set`` is already MW per snapshot, so its sum is MWh.
	# A static ``loads.p_set`` is a *power* held constant across the horizon, so
	# it has to be multiplied by the snapshot weights before it is comparable
	# with generation. Summing the static column instead understates demand by
	# the number of snapshots — which on a solved network looks like a
	# catastrophic energy-balance failure rather than a units error.
	if not network.loads_t.p_set.empty:
		load = float(network.loads_t.p_set.to_numpy().sum())
	else:
		weights = network.snapshot_weightings.get("objective")
		static = float(network.loads["p_set"].astype(float).sum())
		load = static * float(weights.sum()) if weights is not None else static * len(network.snapshots)
	# Branch flow into a branch is *consumed* by it, so ``p0 + p1`` is the energy
	# the branch absorbed, not the energy it delivered. It is a positive
	# quantity that must be **subtracted** to close the balance:
	# ``generation - load - losses == 0``. Measured on a two-bus network with
	# losses on, ``p0 + p1`` equals ``buses_t.p.sum()`` to 1e-9, which is the
	# injection the network retained — the same number.
	#
	# This line read ``generation + losses - load``, and the sign was invisible
	# for as long as every fixture had zero loss: on a lossless network both
	# readings are the identity. On a network that loses 1% of its load the
	# check then refused a correct dispatch by *twice* the loss. `solve_dispatch`
	# freezes a solve's capacity and re-optimises, and every network the CLI
	# builds carries losses, so the check refused exactly the dispatches it
	# existed to verify.
	#
	# **Links carry the same sign, and the first version of this sum omitted
	# them.** A link is a branch like a line and its two flows sum to what the
	# branch retained, with the sign following the efficiency: a 0.9 link
	# returns ``p0 + p1 > 0`` (it absorbed the difference) and a heat-pump link
	# with efficiency 3 returns ``p0 + p1 < 0`` (it created it). Both close the
	# same identity, so the term is one sum over both branch tables rather than
	# a line-only special case. Measured on a two-bus network transferring by
	# link: line-only left an 11.1% residual on a lossy link and 200% on a
	# COP-3 one, every one of them a *correct* dispatch refused. Sector-coupled
	# networks -- hydrogen, heat, industry -- transfer by link, which is to say
	# the check refused the majority of what this project builds.
	losses = 0.0
	for branch in (network.lines_t, network.links_t):
		p0, p1 = branch.get("p0"), branch.get("p1")
		if p0 is None or p1 is None or p0.empty:
			continue
		losses += float(p0.to_numpy().sum() + p1.to_numpy().sum())
	unserved = float(network.generators_t.p.filter(like="load_shedding").to_numpy().sum()) if any(
		"load_shedding" in str(c) for c in network.generators_t.p.columns
	) else 0.0

	error = generation - load - losses
	curtailment = curtailment_mwh(network)
	available = generation + curtailment
	return {
		"generation_mwh": generation,
		"load_mwh": load,
		"error_mwh": error,
		"losses_mwh": losses,
		"curtailment_mwh": curtailment,
		"curtailment_share": curtailment / available if available > 0 else 0.0,
		"peak_mw": float(network.generators_t.p.to_numpy().sum(axis=1).max()) if has_dispatch(network) else 0.0,
		"unserved_mwh": unserved,
	}


def check_energy_balance(
	network: pypsa.Network,
	*,
	tolerance_share: float = 1e-4,
) -> dict[str, float]:
	"""Verify generation minus load minus losses is zero, per snapshot.

	The refusal half of :func:`balance_measurement`: same arithmetic, and it
	raises rather than returning when the residual exceeds the tolerance.

	The tolerance is a share of load, not an absolute MWh: a continental network
	carries terawatt-hours and an absolute tolerance that suits Kenya is a
	division by zero for a small country.
	"""
	report = balance_measurement(network)
	error = report["error_mwh"]
	scale = max(report["load_mwh"], 1.0)
	if abs(error) / scale > tolerance_share:
		raise DispatchError(
			f"energy balance fails by {error:,.1f} MWh over {report['load_mwh']:,.1f} MWh of "
			f"load ({100.0 * error / scale:.4f}%); a load is attached to a bus "
			f"the network does not contain"
		)
	return report


def curtailment_mwh(network: pypsa.Network) -> float:
	"""Energy available from VRE that was not dispatched.

	Available output is capacity times the profile; dispatched output is what
	the solver chose. The difference is curtailment, and it is the number that
	tells a reader whether the network can absorb the renewables built on it.
	"""
	assert network is not None, "network must not be None"
	if network.generators_t.p_max_pu.empty:
		return 0.0
	total = 0.0
	for column in network.generators_t.p_max_pu.columns:
		if column not in network.generators_t.p.columns:
			continue
		capacity = float(network.generators.at[column, "p_nom_opt"]) if bool(
			network.generators.at[column, "p_nom_extendable"]
		) else float(network.generators.at[column, "p_nom"])
		available = network.generators_t.p_max_pu[column].to_numpy(dtype=float) * capacity
		dispatched = network.generators_t.p[column].to_numpy(dtype=float)
		total += float(np.clip(available - dispatched, 0.0, None).sum())
	return total


def marginal_prices(network: pypsa.Network) -> pd.DataFrame:
	"""Locational marginal prices, buses x snapshots, currency/MWh."""
	assert network is not None, "network must not be None"
	if network.buses_t.marginal_price.empty:
		raise DispatchError("network has no marginal prices; solve it first")
	return network.buses_t.marginal_price


def generation_by_carrier(network: pypsa.Network) -> pd.DataFrame:
	"""Dispatched energy by carrier and snapshot, MWh.

	Aggregated from generators to carriers because a report never wants
	per-generator output, and doing it at read time in every consumer is how two
	consumers come to disagree.
	"""
	assert network is not None, "network must not be None"
	if not has_dispatch(network):
		raise DispatchError("network has no dispatch; solve it first")
	frame = network.generators_t.p.copy()
	frame.columns = [str(network.generators.at[c, "carrier"]) for c in frame.columns]
	return frame.T.groupby(level=0).sum().T


def dispatch_provenance(
	result: DispatchResult,
	config: Config,
	*,
	inputs: list[str] | None = None,
) -> DerivedProvenance:
	"""Provenance for a dispatch."""
	assert result is not None, "result must not be None"
	return DerivedProvenance(
		source_id="dispatch",
		inputs=inputs or ["sha256:network:capacity"],
		basis=Basis.MODELLED,
		uncertainty=0.0,
		parameters={
			**result.as_dict(),
			"solver": config.solve.solver,
			"transmission_losses": config.solve.transmission_losses,
			"currency": config.costs.base_currency,
		},
		notes=(
			f"Dispatch on fixed capacity. Curtailment "
			f"{result.curtailment_share * 100:.2f}% of available renewable energy."
		),
	)


__all__ = [
	"DispatchError",
	"DispatchResult",
	"check_energy_balance",
	"curtailment_mwh",
	"dispatch_provenance",
	"freeze_capacity",
	"generation_by_carrier",
	"marginal_prices",
	"solve_dispatch",
]
