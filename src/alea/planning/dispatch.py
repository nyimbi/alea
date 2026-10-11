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
from alea.planning.expansion import check_solver_available
from alea.provenance.models import Basis, DerivedProvenance

_log = get_logger(__name__)


class DispatchError(RuntimeError):
	"""The dispatch problem cannot be built or solved."""


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
		freeze_capacity(network)

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


def check_energy_balance(
	network: pypsa.Network,
	*,
	tolerance_share: float = 1e-4,
) -> dict[str, float]:
	"""Verify generation minus load minus losses is zero, per snapshot.

	A dispatch that does not balance means a load was attached to a bus the
	model does not contain, or a generator was added outside the network's
	component tables. Both produce an objective that looks fine.

	The tolerance is a share of load, not an absolute MWh: a continental network
	carries terawatt-hours and an absolute tolerance that suits Kenya is a
	division by zero for a small country.
	"""
	assert network is not None, "network must not be None"
	if not len(network.generators_t.p):
		raise DispatchError("network has no dispatch; solve it first")

	generation = float(network.generators_t.p.to_numpy().sum())
	load = float(network.loads_t.p_set.to_numpy().sum()) if len(network.loads_t.p_set) else 0.0
	losses = 0.0
	if len(network.lines_t.p0):
		losses = float(network.lines_t.p0.to_numpy().sum() + network.lines_t.p1.to_numpy().sum())
	unserved = float(network.generators_t.p.filter(like="load_shedding").to_numpy().sum()) if any(
		"load_shedding" in str(c) for c in network.generators_t.p.columns
	) else 0.0

	error = generation + losses - load
	scale = max(load, 1.0)
	if abs(error) / scale > tolerance_share:
		raise DispatchError(
			f"energy balance fails by {error:,.1f} MWh over {load:,.1f} MWh of "
			f"load ({100.0 * error / scale:.4f}%); a load is attached to a bus "
			f"the network does not contain"
		)

	curtailment = curtailment_mwh(network)
	available = generation + curtailment
	return {
		"generation_mwh": generation,
		"load_mwh": load,
		"error_mwh": error,
		"losses_mwh": losses,
		"curtailment_mwh": curtailment,
		"curtailment_share": curtailment / available if available > 0 else 0.0,
		"peak_mw": float(network.generators_t.p.to_numpy().sum(axis=1).max()) if len(network.generators_t.p) else 0.0,
		"unserved_mwh": unserved,
	}


def curtailment_mwh(network: pypsa.Network) -> float:
	"""Energy available from VRE that was not dispatched.

	Available output is capacity times the profile; dispatched output is what
	the solver chose. The difference is curtailment, and it is the number that
	tells a reader whether the network can absorb the renewables built on it.
	"""
	assert network is not None, "network must not be None"
	if not len(network.generators_t.p_max_pu):
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
	if not len(network.buses_t.marginal_price):
		raise DispatchError("network has no marginal prices; solve it first")
	return network.buses_t.marginal_price


def generation_by_carrier(network: pypsa.Network) -> pd.DataFrame:
	"""Dispatched energy by carrier and snapshot, MWh.

	Aggregated from generators to carriers because a report never wants
	per-generator output, and doing it at read time in every consumer is how two
	consumers come to disagree.
	"""
	assert network is not None, "network must not be None"
	if not len(network.generators_t.p):
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
