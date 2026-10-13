# SPDX-License-Identifier: MIT
"""Multi-period capacity expansion.

Two settings in this module are defaults rather than choices, and both were
argued before they were set.

Losses are on. The specification's benchmark (PyPSA-Eur) found that neglecting
losses overestimates optimal expansion by roughly 20%, and losses consume 15-25%
of generated energy in many African systems. A default of off would mean every
capacity mix the platform publishes is wrong by default.

The solver is HiGHS. It is MIT-licensed, it is a direct dependency of pypsa 1.4
rather than an extra, and it handles the variable counts a single-country model
produces. A commercial solver is selected only when the config names it, and the
config validates at load that it is importable.

The investment-period structure is where the failures are. ``multi_investment_periods``
requires the snapshots to be a MultiIndex carrying a ``period`` level. Building
the network single-period and then asking for multi-period expansion fails
inside pypsa with an error about a missing level, forty minutes in. The snapshots
are therefore built here, once, from the config's horizons.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea.config.models import Config
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance

_log = get_logger(__name__)

class ExpansionError(RuntimeError):
	"""The expansion problem cannot be built or solved."""


@dataclass
class SolveResult:
	"""What a solve produced."""

	objective: float
	solver: str
	status: str
	seconds: float
	network: pypsa.Network
	investments: dict[str, float] = field(default_factory=dict)

	def as_dict(self) -> dict[str, Any]:
		return {
			"objective": self.objective,
			"solver": self.solver,
			"status": self.status,
			"seconds": self.seconds,
			"n_investments": len(self.investments),
		}


def build_multi_period_snapshots(
	network: pypsa.Network,
	horizons: list[int],
	*,
	base_year: int | None = None,
) -> pd.MultiIndex:
	"""Snapshots for a multi-period expansion, as a MultiIndex with a period level.

	Every period carries the network's *own* snapshots, repeated. This is
	``pypsa.Network.set_investment_periods``' rule, and the reason for it is
	that the alternative silently destroys the model.

	WHY this is not ``period_length`` fresh hours starting at each horizon: that
	is what this function used to build, and the snapshots it invented were
	January hours of years the artefacts do not cover. ``set_snapshots``
	reindexes every time series *by label*, so a demand frame holding 2030 found
	no 2040 label to align to and pypsa filled the whole period with the
	component's static default -- zero load and a capacity factor of 1.0 for
	three of the four default horizons. The model still solved, and it solved a
	continent whose demand and weather exist only in the 2030s. Nothing failed;
	the answer was just wrong by roughly a factor of four, which is the failure
	mode AD-9 exists to prevent and which no tolerance here would have caught.

	Repeating the real series is also what makes the reduction in
	``aggregation.py`` survive: ``time_aggregation`` reduces the *series* a
	network carries, and a builder that replaces that series with a synthetic
	year discards the reduction no matter what the gate measured.

	The snapshots must already be a plain ``DatetimeIndex``; a network already
	in multi-period form has nothing for this function to do and is refused
	rather than silently re-repeated.
	"""
	assert network is not None, "network must not be None"
	assert len(horizons) > 0, "at least one horizon is required"
	assert horizons == sorted(horizons), f"horizons must ascend, got {horizons}"
	if base_year is not None and base_year >= horizons[0]:
		raise ExpansionError(f"base_year ({base_year}) must precede the first horizon ({horizons[0]})")
	if isinstance(network.snapshots, pd.MultiIndex):
		raise ExpansionError(
			"network is already multi-period; `build_multi_period_snapshots` "
			"repeats a plain snapshot index and would nest the existing one"
		)
	timesteps = pd.DatetimeIndex(network.snapshots)
	tuples: list[tuple[int, Any]] = [
		(horizon, timestep) for horizon in horizons for timestep in timesteps
	]
	index = pd.MultiIndex.from_tuples(tuples, names=["period", "timestep"])
	assert len(index) == len(horizons) * len(timesteps), "snapshot count does not match the periods"
	return index


def set_multi_period(
	network: pypsa.Network,
	horizons: list[int],
	*,
	base_year: int | None = None,
) -> None:
	"""Put a network into multi-period form, in place.

	Weightings are computed from the horizon spacing. A model whose periods are
	weighted equally treats 2030-2040 as the same length of time as 2050-2060,
	which understates the later period's operating cost and biases investment
	early.

	The snapshots are repeated, not rebuilt -- see
	`build_multi_period_snapshots` for what rebuilding cost. The repeat is done
	by ``set_investment_periods`` rather than by ``set_snapshots``: both produce
	the same MultiIndex, but ``set_snapshots`` resets every snapshot weighting to
	1.0 while ``set_investment_periods`` carries the existing ones through. On an
	aggregated network those weightings are the whole content of the reduction
	(``w / period_length`` per kept timestep, summing to the year's hours), so
	the ``set_snapshots`` route would repeat the representative periods and then
	price each of them as a single hour -- a fast path that is fast because it
	threw the annual totals away.
	"""
	assert network is not None, "network must not be None"
	# The builder is the specification of the index and the assertion that the
	# input is plain; it runs before the mutation, so a network already in
	# multi-period form is refused with the input untouched.
	expected = build_multi_period_snapshots(network, horizons, base_year=base_year)
	network.set_investment_periods(horizons)
	assert network.snapshots.equals(expected), (
		"pypsa built a different index than this module specifies: "
		f"{len(network.snapshots)} snapshots, expected {len(expected)}"
	)

	weights: list[float] = []
	for i, horizon in enumerate(horizons):
		if i + 1 < len(horizons):
			span = horizons[i + 1] - horizon
		elif base_year is not None:
			span = horizon - base_year
		else:
			span = horizons[i] - horizons[i - 1] if i > 0 else 1
		weights.append(float(span))
	network.investment_period_weightings["years"] = weights
	# Social discount rate applied per period, expressed as a present-value
	# factor from the first period. Without it the model is indifferent between
	# spending now and in 2060, which is not a planning model.
	first = horizons[0]
	network.investment_period_weightings["objective"] = [
		1.0 / ((1.0 + DISCOUNT_RATE) ** (horizon - first)) for horizon in horizons
	]
	_log.info("multi_period_set", horizons=horizons, weights=weights)


DISCOUNT_RATE = 0.05
"""Real social discount rate for present-value weighting across periods."""


def check_solver_available(solver: str) -> None:
	"""Refuse a solver that is not importable, before a model is built.

	The config already checks the two commercial solvers at load. This repeats
	the check at the point of use because a network can also arrive from an
	artefact and be solved without a config in hand.
	"""
	assert solver, "solver name must not be empty"
	if solver in ("highs", "glpk"):
		import importlib.util

		module = "highspy" if solver == "highs" else "swiglpk"
		if importlib.util.find_spec(module) is None:
			raise ExpansionError(f"solver={solver!r} selected but {module} is not installed")
		return
	import importlib.util

	if importlib.util.find_spec(solver) is None:
		raise ExpansionError(
			f"solver={solver!r} selected but not installed; highs is MIT and "
			f"bundled with pypsa"
		)


def check_no_free_capacity(network: pypsa.Network) -> None:
	"""Refuse a network where capacity can be built for nothing.

	An extendable component with zero capital cost and zero marginal cost adds
	capacity without adding to the objective, so the optimiser builds it without
	limit and the objective is lower than any physical system could achieve. The
	symptom is an objective that is suspiciously round, or zero.

	This is the gate that catches it. It was written because it caught a real
	one: renewable profiles attached as extendable with no capital cost produced
	an 8 GW solar build at an objective of exactly 0.0, and nothing else in the
	pipeline objected.
	"""
	assert network is not None, "network must not be None"
	offenders: list[str] = []
	for component in ("generators", "storage_units", "stores", "links", "lines"):
		table = getattr(network, component, None)
		if table is None or not len(table):
			continue
		for column in ("p_nom_extendable", "s_nom_extendable", "e_nom_extendable"):
			if column not in table.columns:
				continue
			extendable = table[column].fillna(False).astype(bool)
			if not extendable.any():
				continue
			capital = table["capital_cost"].fillna(0.0).astype(float) if "capital_cost" in table.columns else pd.Series(0.0, index=table.index)
			marginal = table["marginal_cost"].fillna(0.0).astype(float) if "marginal_cost" in table.columns else pd.Series(0.0, index=table.index)
			free = extendable & (capital <= 0.0) & (marginal <= 0.0)
			offenders.extend(f"{component}:{name}" for name in table.index[free])
	if offenders:
		raise ExpansionError(
			f"{len(offenders)} extendable component(s) have no capital and no "
			f"marginal cost, e.g. {', '.join(sorted(offenders)[:5])}. Free "
			f"capacity is not a modelling result: the optimiser will build it "
			f"without limit and the objective will not price it."
		)


def solve_expansion(
	network: pypsa.Network,
	config: Config,
	*,
	horizons: list[int] | None = None,
	multi_period: bool | None = None,
	logger_: Any = None,
) -> SolveResult:
	"""Solve capacity expansion on a prepared network.

	``network`` must already carry loads, generators and renewable profiles. The
	snapshots are replaced when ``multi_period`` is on, because a network built
	from the seam's artefacts arrives single-period.
	"""
	assert network is not None, "network must not be None"
	assert len(network.buses) > 0, "network has no buses"
	assert len(network.generators) > 0 or len(network.storage_units) > 0, (
		"network has nothing to expand; attach a fleet or candidate generators first"
	)
	log = logger_ or _log

	solver = config.solve.solver
	check_solver_available(solver)
	check_no_free_capacity(network)

	periods = horizons if horizons is not None else list(config.scenario.planning_horizons)
	use_multi = config.solve.multi_investment_periods if multi_period is None else multi_period
	if use_multi and len(periods) > 1:
		set_multi_period(network, periods, base_year=config.scenario.base_year)
		network.generators["build_year"] = network.generators["build_year"].fillna(periods[0]).astype(int)

	options: dict[str, Any] = dict(config.solve.solver_options)
	options.setdefault("threads", 1)
	"""One thread.

	HiGHS is deterministic single-threaded and not necessarily deterministic
	multi-threaded: parallel branch-and-bound explores nodes in a race-dependent
	order and can return a different optimal solution among ties. AD-8 requires
	two solves to be byte-identical, and this is the cheapest way to have it.
	"""
	options.setdefault("random_seed", 0)
	options.setdefault("time_limit", float(config.solve.solver_timeout_s))

	start = time.perf_counter()
	try:
		status, condition = network.optimize(
			solver_name=solver,
			transmission_losses=config.solve.transmission_losses,
			linearized_unit_commitment=config.solve.linearized_unit_commitment,
			multi_investment_periods=use_multi and len(periods) > 1,
			solver_options=options,
			include_objective_constant=False,
		)
	except Exception as exc:  # noqa: BLE001 - the solver raises its own types
		raise ExpansionError(f"{solver} failed to solve: {exc}") from exc
	seconds = time.perf_counter() - start

	if status not in ("ok", "optimal", "Optimal"):
		raise ExpansionError(
			f"{solver} returned status={status!r} ({condition}); an infeasible or "
			f"unbounded expansion is a modelling result, not a crash, and the "
			f"caller must see it"
		)

	# The status check above rejects anything but optimal, so a solution exists.
	# pypsa types `objective` as `float | None` because an unsolved network has
	# none; this assertion is the runtime half of that guarantee.
	assert network.objective is not None, f"{solver} reported {status!r} but set no objective"
	objective = float(network.objective)
	result = SolveResult(
		objective=objective,
		solver=solver,
		status=str(status),
		seconds=seconds,
		network=network,
		investments=optimal_investments(network),
	)
	log.info(
		"expansion_solved",
		objective=objective,
		solver=solver,
		seconds=round(seconds, 2),
		losses=config.solve.transmission_losses,
		multi_period=use_multi,
	)
	return result


def optimal_investments(network: pypsa.Network) -> dict[str, float]:
	"""Capacity added by the solve, per component, MW or MWh.

	Only components whose optimal capacity exceeds their existing capacity.
	Reporting every extendable component would list a few thousand zeroes.
	"""
	assert network is not None, "network must not be None"
	out: dict[str, float] = {}
	for name, row in network.generators.iterrows():
		if not bool(row.get("p_nom_extendable", False)):
			continue
		existing = float(row.get("p_nom", 0.0) or 0.0)
		optimal = float(row.get("p_nom_opt", 0.0) or 0.0)
		if optimal > existing + 1e-6:
			out[str(name)] = optimal - existing
	for name, row in network.storage_units.iterrows():
		if not bool(row.get("p_nom_extendable", False)):
			continue
		existing = float(row.get("p_nom", 0.0) or 0.0)
		optimal = float(row.get("p_nom_opt", 0.0) or 0.0)
		if optimal > existing + 1e-6:
			out[str(name)] = optimal - existing
	return out


def solve_result_provenance(
	result: SolveResult,
	config: Config,
	*,
	inputs: list[str] | None = None,
) -> DerivedProvenance:
	"""Provenance for a solve.

	Every setting that could change the answer is recorded: the solver, whether
	losses were modelled, whether the model is multi-period, and the objective
	weighting. A solve result without them cannot be reproduced even with the
	same network, because the same network solved without losses gives a
	different expansion.
	"""
	assert result is not None, "result must not be None"
	return DerivedProvenance(
		source_id="capacity_expansion",
		inputs=inputs or ["sha256:network:input"],
		basis=Basis.MODELLED,
		uncertainty=0.0,
		parameters={
			**result.as_dict(),
			"transmission_losses": config.solve.transmission_losses,
			"multi_investment_periods": config.solve.multi_investment_periods,
			"linearized_unit_commitment": config.solve.linearized_unit_commitment,
			"solver_options": dict(config.solve.solver_options),
			"discount_rate": DISCOUNT_RATE,
			"horizons": list(config.scenario.planning_horizons),
			"currency": config.costs.base_currency,
		},
		notes=(
			f"Objective in {config.costs.base_currency}. Losses "
			f"{'modelled' if config.solve.transmission_losses else 'NEGLECTED'}; "
			f"neglecting losses overestimates expansion by roughly 20%."
		),
	)


def capacity_mix_table(network: pypsa.Network) -> pd.DataFrame:
	"""Installed capacity by carrier, MW, sorted descending.

	The one table every reader wants and the one every report quotes. Built here
	so that "installed capacity" means the same thing everywhere: existing
	capacity where a component is not extendable, optimal capacity where it is.
	"""
	assert network is not None, "network must not be None"
	rows: list[dict[str, Any]] = []
	for name, row in network.generators.iterrows():
		extendable = bool(row.get("p_nom_extendable", False))
		capacity = float(row.get("p_nom_opt", 0.0) or 0.0) if extendable else float(row.get("p_nom", 0.0) or 0.0)
		if capacity <= 0:
			continue
		rows.append(
			{
				"carrier": str(row["carrier"]),
				"capacity_mw": capacity,
				"extendable": extendable,
				"component": str(name),
			}
		)
	for name, row in network.storage_units.iterrows():
		extendable = bool(row.get("p_nom_extendable", False))
		capacity = float(row.get("p_nom_opt", 0.0) or 0.0) if extendable else float(row.get("p_nom", 0.0) or 0.0)
		if capacity <= 0:
			continue
		rows.append(
			{
				"carrier": str(row["carrier"]),
				"capacity_mw": capacity,
				"extendable": extendable,
				"component": str(name),
			}
		)
	frame = pd.DataFrame(rows)
	if frame.empty:
		return pd.DataFrame(columns=pd.Index(["carrier", "capacity_mw"], dtype="object"))
	grouped = frame.groupby("carrier", as_index=False)["capacity_mw"].sum()
	# The frame is built from `rows` with mixed dtypes (str/int/float/bool), so
	# pyright cannot match `sort_values` to a column-key overload. The column is
	# float by construction above.
	grouped = grouped.sort_values("capacity_mw", ascending=False)  # type: ignore[call-overload]
	return grouped.reset_index(drop=True)


def has_dispatch(network: pypsa.Network) -> bool:
	"""Whether a solve produced generator dispatch.

	``.empty`` and not ``len()``. A PyPSA dynamic table is indexed by snapshots
	and has one column per component, so an *unsolved* network of any size still
	reports one row per snapshot: ``len(n.generators_t.p)`` is 3 on a
	three-snapshot network that has never been optimised. Every guard written as
	``if not len(network.generators_t.p)`` therefore passed on exactly the input
	it was written to refuse, and the code then read an empty frame — a total of
	0.0, or a maximum over an empty axis. ``.empty`` is True when there are no
	*columns*, which is the property that means "nothing has been solved".

	The predicate lives here rather than in each caller because the same wrong
	guard appeared in nine places across this package, which is how a mistake
	becomes a convention.
	"""
	assert network is not None, "network must not be None"
	return not network.generators_t.p.empty


def loss_share(network: pypsa.Network) -> float:
	"""Transmission losses as a share of generation.

	A finding in its own right: the specification's benchmark says losses consume
	15-25% of generated energy in many African systems. If the Kenya model
	reproduces that range, the benchmark holds for African networks too; if it
	does not, the benchmark is wrong for them and that is worth publishing.
	"""
	assert network is not None, "network must not be None"
	if not has_dispatch(network):
		raise ExpansionError("network has no dispatch; solve it first")
	generation = float(network.generators_t.p.to_numpy().sum())
	if generation <= 0:
		return 0.0
	# pypsa's convention is that p1 carries the negative of the flow arriving at
	# bus1, so p0 + p1 is the loss and is **positive**. Measured against a
	# two-bus network with a known 1.294 MW loss before this was written; the
	# sign is not guessable from the names and getting it wrong makes every
	# published loss share negative.
	losses = (
		float(network.lines_t.p0.to_numpy().sum() + network.lines_t.p1.to_numpy().sum())
		if not network.lines_t.p0.empty
		else 0.0
	)
	return losses / generation


def annual_system_cost(network: pypsa.Network) -> float:
	"""Objective per year, for comparison with an annual figure.

	The objective of a multi-period model is a present value over all periods.
	Quoting it as an annual cost is a factor-of-decades error, so the division
	happens here, once, with the period weighting it needs.
	"""
	assert network is not None, "network must not be None"
	objective = getattr(network, "objective", None)
	if objective is None:
		raise ExpansionError("network has no objective; solve it first")
	years = network.investment_period_weightings.get("years")
	if years is None or len(years) == 0:
		return float(objective)
	total_years = float(np.sum(np.asarray(years, dtype=float)))
	if total_years <= 0:
		return float(objective)
	return float(objective) / total_years


__all__ = [
	"DISCOUNT_RATE",
	"ExpansionError",
	"SolveResult",
	"annual_system_cost",
	"build_multi_period_snapshots",
	"capacity_mix_table",
	"check_no_free_capacity",
	"check_solver_available",
	"has_dispatch",
	"loss_share",
	"optimal_investments",
	"set_multi_period",
	"solve_expansion",
	"solve_result_provenance",
]
