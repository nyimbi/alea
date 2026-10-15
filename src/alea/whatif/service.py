# SPDX-License-Identifier: MIT
"""The what-if engine: parameter overlay, cache, re-solve.

WHY the engine owns no physics: every solve calls Layer 1's expansion, every
price calls Layer 3's market model. Layer 5's only job is to apply parameters,
cache the result, and orchestrate. That keeps the what-if engine testable with
a stub solver, which is what the cache gates need — a gate that asserts "the
second solve did not re-solve" must be able to count solves, and it can only do
that if solving is a seam the engine calls rather than a thing the engine is.

WHY the cache is keyed on a content hash and not ``hash()``: see
``alea.whatif.cache``. The whole point of this module is that a restart does
not re-solve, and a randomised key makes it re-solve everything while looking
like it did not.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pypsa

from alea import __version__
from alea.io.artefacts import sha256_file
from alea.logging import get_logger
from alea.prg.audit import (
	ScenarioAudit,
	audit_scenario_result,
	fleet_intensity_gap,
	reliability_gap,
)
from alea.whatif.apply import apply_parameters
from alea.whatif.cache import SolveCache, cache_key, solve_fingerprint
from alea.whatif.extract import extract
from alea.whatif.params import ScenarioParameters
from alea.whatif.views import RiskMetrics, ScenarioResult, SolveOutcome

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph
	from alea.whatif.outage import OutageSet

logger = get_logger(__name__)

SolveFn = Callable[..., Any]
"""How a network is solved.

The engine calls this rather than ``network.optimize`` so that the cache gates
can count invocations (``count_solves`` in the plan's test sketch) and so a
test can solve a fixture network with a stub.

``...`` rather than ``[pypsa.Network]`` because a constrained solve passes a
second argument, PyPSA's ``extra_functionality`` hook. A stub that takes only
the network is still valid and is called with one argument; the engine passes
the hook only when there is one, and raises a named error when the solve
function cannot accept it rather than dropping the constraints silently.
"""

PriceFn = Callable[[pypsa.Network, ScenarioResult], "tuple[list[float], float | None]"]
"""Layer 3's contribution: a cost distribution and an optional threshold.

Returns ``(costs, threshold)``. The engine turns those into
:class:`~alea.whatif.views.RiskMetrics`; it does not compute them, because the
risk physics is Layer 3's.
"""

DEFAULT_CODE_VERSION = __version__


class SolveError(RuntimeError):
	"""A solve that produced no feasible optimum.

	Raised rather than returned because the alternative is a result object: an
	infeasible network still has a ``ScenarioResult``'s shape, and every field
	of it would be read as a modelled quantity. A scenario the fleet cannot
	meet is an answer about the scenario, and it has to reach the caller as a
	failure rather than as a cost.
	"""


@dataclass(frozen=True)
class PrgSolve:
	"""A solve driven by the graph's parameters, with what the graph made of it.

	Four things travel together and none is derivable from the others:

	* ``outcome`` -- the solve, and whether the cache served it;
	* ``parameters`` -- the engine knobs the translation produced, so a caller
	  can see *what* was applied rather than what was asked for;
	* ``audit`` -- the graph's verdict on the solved result, with the count of
	  parameters the result did not carry;
	* ``dropped`` -- the parameters the caller set that reached no knob.

	``dropped`` is empty on the strict path, which is the default: the refusal
	happens inside the translation and no solve is attempted. It is non-empty
	only when the caller asked for ``strict=False``, and it is carried rather
	than logged because a dropped parameter is the difference between an answer
	to the question asked and an answer to a question the engine could express.
	"""

	outcome: SolveOutcome
	parameters: ScenarioParameters
	audit: ScenarioAudit
	intensity_gap: dict[str, float]
	reliability_gap: dict[str, float] = field(default_factory=dict)
	"""The engine's realised unserved fraction against the graph's standard.

	A second declared-versus-measured pair, and the same shape as
	``intensity_gap``: the graph states ``expected_unserved_fraction`` and
	nothing in the tree compared it against what the solve actually shed. It is
	defaulted rather than required so an existing caller constructing a
	``PrgSolve`` keeps working; :meth:`WhatIfEngine.solve_from_prg` always fills
	it.
	"""

	dropped: tuple[str, ...] = field(default=())
	constrained: bool = False
	"""Whether the solve ran under the graph's inequalities.

	``False`` when the caller asked for the plain solve (``constrain=False``) or
	when no inequality could bind. It travels with the result because a solved
	number carries no trace of the constraints it was solved under, and two
	results from one network -- one constrained, one not -- are otherwise
	indistinguishable in a report.
	"""

	constraint_terms: tuple[str, ...] = field(default=())
	"""The graph parameters the scenario moved that the constraints read.

	These are the parameters that reach no engine knob and reach the *solve*
	anyway, through an inequality. Naming them is what keeps them out of the
	``dropped`` register, where they would read as reaching nothing at the exact
	moment they reach the optimiser.
	"""

	@property
	def result(self) -> ScenarioResult:
		return self.outcome.result

	@property
	def consistent(self) -> bool:
		"""Whether the graph accepted the result over the parameters it carried.

		Not a verdict on the scenario: ``audit.consistent`` says nothing about the
		parameters in ``audit.skipped``, and a caller reading this as a bill of
		health is reading a statement about the checked set as one about the
		result. :meth:`summary` carries the counts for exactly that reason.
		"""
		return self.audit.consistent

	def summary(self) -> str:
		parts = [self.audit.summary()]
		if self.dropped:
			parts.append(
				f"{len(self.dropped)} parameter(s) reached no engine knob and were "
				f"dropped: {', '.join(self.dropped)}"
			)
		if self.outcome.from_cache:
			parts.append("served from cache")
		return "; ".join(parts)


def _default_graph() -> ParameterGraph:
	"""The shipped graph. Imported lazily so this module stays importable
	without the YAML file present, which a stub-solver cache test relies on."""
	from alea.prg import load_graph

	return load_graph()


class WhatIfEngine:
	"""Applies scenario parameters to a base network and caches the solve.

	One engine is one base network. The network's checksum is captured at
	construction and is part of every cache key and every stored result, so two
	engines on different networks can never serve each other's results.
	"""

	def __init__(
		self,
		base_network: str | Path | pypsa.Network,
		*,
		cache_root: str | Path | None = None,
		solve_fn: SolveFn | None = None,
		price_fn: PriceFn | None = None,
		code_version: str = DEFAULT_CODE_VERSION,
		risk_confidence: float = 0.95,
	) -> None:
		assert code_version, "a solve keyed without its code version is not reproducible"

		self._base = _load_network(base_network)
		self._base_source = str(base_network)
		self._network_checksum = _network_checksum(self._base, base_network)
		self._solve_fn = solve_fn or _default_solve
		self._price_fn = price_fn
		self._code_version = code_version
		self._risk_confidence = risk_confidence
		self._cache = SolveCache(cache_root) if cache_root is not None else None
		self._solve_count = 0

		logger.info(
			"whatif.engine",
			network=self._network_checksum[:12],
			code_version=code_version,
			cached=self._cache is not None,
		)

	# ------------------------------------------------------------------
	# Read-only properties
	# ------------------------------------------------------------------

	@property
	def network_checksum(self) -> str:
		"""Content hash of the base network. Part of every cache key."""
		return self._network_checksum

	@property
	def code_version(self) -> str:
		return self._code_version

	@property
	def solve_count(self) -> int:
		"""How many times this engine actually invoked the solver.

		The observable the cache gates assert on: two identical solves must
		leave this at 1, not 2.
		"""
		return self._solve_count

	@property
	def cache(self) -> SolveCache | None:
		return self._cache

	# ------------------------------------------------------------------
	# Solving
	# ------------------------------------------------------------------

	def key_for(
		self,
		params: ScenarioParameters,
		*,
		constraints: Mapping[str, Any] | None = None,
	) -> str:
		"""The cache key this parameter set would be filed under."""
		assert isinstance(params, ScenarioParameters)
		return cache_key(
			params, self._network_checksum, self._code_version, constraints=constraints
		)

	def solve(
		self,
		params: ScenarioParameters,
		*,
		force: bool = False,
		write_cache: bool = True,
		constraints: Mapping[str, Any] | None = None,
		hook: Callable[[pypsa.Network], None] | None = None,
	) -> ScenarioResult:
		"""Solve one scenario, serving from the cache when possible."""
		return self.solve_with_outcome(
			params, force=force, write_cache=write_cache, constraints=constraints, hook=hook
		).result

	def solve_with_outcome(
		self,
		params: ScenarioParameters,
		*,
		force: bool = False,
		write_cache: bool = True,
		constraints: Mapping[str, Any] | None = None,
		hook: Callable[[pypsa.Network], None] | None = None,
	) -> SolveOutcome:
		"""As :meth:`solve`, additionally reporting whether the cache served it.

		A sweep needs this: a point served from the cache must not be reported
		as a fresh computation, and the resumed-sweep gate asserts on it.

		``constraints`` and ``hook`` are the two halves of a constrained solve and
		travel together. ``constraints`` is the *record* of what the solve ran
		under -- it enters the cache key, so a constrained solve and an
		unconstrained one cannot serve each other's answers. ``hook`` is the
		callable PyPSA invokes to add them. Passing a record with no hook would
		key a solve on constraints that were never applied, which is the worst of
		the three states: the key says constrained, the answer is not.
		"""
		assert isinstance(params, ScenarioParameters)
		assert (constraints is None) == (hook is None), (
			"a constraint record and the hook that applies it travel together: "
			"one without the other keys a solve on constraints it did not run under"
		)
		key = self.key_for(params, constraints=constraints)

		if self._cache is not None and not force:
			cached = self._cache.get(key)
			if cached is not None:
				logger.info("whatif.cache.hit", key=key[:12], fingerprint=solve_fingerprint(
					params, self._network_checksum, self._code_version, constraints=constraints
				))
				return SolveOutcome(
					result=ScenarioResult.from_cache_payload(cached["result"]),
					cache_key=key,
					from_cache=True,
				)

		started = time.perf_counter()
		result = self._compute(params, key=key, hook=hook)
		elapsed = time.perf_counter() - started

		if self._cache is not None and write_cache:
			self._cache.put(
				key,
				params=params,
				network_checksum=self._network_checksum,
				code_version=self._code_version,
				result=result.to_cache_payload(),
				constraints=constraints,
			)

		logger.info("whatif.solve", key=key[:12], seconds=round(elapsed, 3), cost=result.total_cost_usd)
		return SolveOutcome(result=result, cache_key=key, from_cache=False, solve_seconds=elapsed)

	def _compute(
		self,
		params: ScenarioParameters,
		*,
		key: str,
		hook: Callable[[pypsa.Network], None] | None = None,
	) -> ScenarioResult:
		"""Apply, solve, extract. The uncached path."""
		network = apply_parameters(self._base, params)
		if hook is None:
			self._solve_fn(network)
		else:
			# The engine's solve function is handed the hook rather than the hook
			# being run around it: a caller that solved the network itself to add a
			# constraint would run a second, differently configured solve. The
			# solver seam takes an optional hook for exactly this, and one that
			# cannot accept it raises here rather than silently dropping the
			# constraints and returning an unconstrained answer.
			try:
				self._solve_fn(network, hook)
			except TypeError as exc:
				raise TypeError(
					"this engine's solve function does not accept the extra_functionality "
					"hook, so a constrained scenario cannot be solved through it; pass a "
					"solve function taking (network, extra_functionality)"
				) from exc
		self._solve_count += 1

		risk: RiskMetrics | None = None
		if self._price_fn is not None:
			costs, threshold = self._price_fn(
				network, _result_placeholder(params, self._network_checksum, self._code_version)
			)
			# An empty sample means the price model had no distribution to draw
			# from -- a solve without duals carries no marginal prices. That is
			# "risk not computed", which `risk is None` already says, and it is
			# not "risk is zero": `from_costs([])` raises, and a raise here would
			# fail a solve that is otherwise perfectly good because a *reporting*
			# axis is unavailable. The frontier's own refusal then names it.
			if costs:
				risk = RiskMetrics.from_costs(
					costs, confidence=self._risk_confidence, threshold=threshold
				)

		return extract(
			network,
			params,
			network_checksum=self._network_checksum,
			code_version=self._code_version,
			risk=risk,
		)

	# ------------------------------------------------------------------
	# Sweeps
	# ------------------------------------------------------------------

	def sweep(
		self,
		param_name: str,
		values: Sequence[float],
		template: ScenarioParameters | None = None,
	) -> list[SolveOutcome]:
		"""Solve one parameter across ``values``, in order.

		Serial and deterministic. A point that is already cached is served from
		the cache, so a sweep interrupted partway resumes rather than
		restarting; each point is cached independently and never evicted during
		the sweep (eviction mid-sweep would change which points exist and
		therefore the frontier).
		"""
		from alea.whatif.sweep import sweep_parameter

		return sweep_parameter(self, param_name, values, template or ScenarioParameters())

	# ------------------------------------------------------------------
	# PRG-driven scenarios
	# ------------------------------------------------------------------

	def solve_from_prg(
		self,
		values: Mapping[str, float],
		*,
		graph: ParameterGraph | None = None,
		strict: bool = True,
		force: bool = False,
		constrain: bool = True,
		outages: OutageSet | None = None,
	) -> PrgSolve:
		"""Solve a scenario stated in the graph's parameters, and audit it.

		WHY this method exists. ``alea.prg.translate`` was written, tested, and
		reachable from nothing: its two directions were called only by
		``tests/ci/test_prg_translate.py``, so the register it prints -- "three of
		fifty-three settable parameters reach a what-if knob" -- described a route
		no production caller walked. The graph could not drive a solve at all, and
		the number reported a capability that was, in the sense that matters, zero.
		This is that route: the caller states a scenario in the *graph's* names,
		the translation maps what it can onto the engine's knobs, and the result is
		audited against the graph's own identities.

		The network is in hand here, which is what makes the ratio direction
		possible at all -- ``fuel_price_usd_per_mwh`` is an absolute price the
		engine applies as a factor over the network's base gas cost, and there is
		no factor without the base. ``to_scenario_parameters`` refuses rather than
		defaulting the factor to 1.0, because a defaulted factor runs, reports the
		parameter as applied, and applies nothing.

		``strict`` is passed through and defaults to refusing: a scenario that sets
		a parameter the engine cannot carry is a scenario whose answer does not
		answer the question asked, and the refusal names the parameter. A caller
		who wants the drop can ask for it, and :class:`PrgSolve` then carries the
		register of what was dropped so the drop is not silent.

		WHY the constraint terms are exempt from that refusal. Four of the graph's
		settable parameters -- ``carbon_budget_mtco2``, ``horizon_years``,
		``capacity_factor``, ``reserve_margin_min`` -- reach no engine knob and
		are not *meant* to: they are the terms of the two inequalities the graph
		can bind, and the optimiser reads them when the constraint is added. A
		scenario that sets one is tightening a bound, which is a thing the graph
		is for. Refusing it as uncarriable would be the register's own defect
		inverted -- reporting a parameter as reaching nothing at the exact moment
		it reaches the solve -- so they are translated into the constraint record
		instead, and ``constrain=False`` is how a caller asks for the plain
		unconstrained solve.
		"""
		from alea.prg.constraints import bound_parameter_names, bound_routes, constraint_function
		from alea.prg.translate import to_scenario_parameters, translated

		g = graph if graph is not None else _default_graph()
		terms = set(bound_parameter_names(g))
		# The constraint terms are lifted out of `values` before the translation
		# sees them, because the translation's job is engine knobs and these are
		# not knobs. They are read back by the hook from the same `values`.
		constraint_values = (
			{name: float(value) for name, value in values.items() if name in terms}
			if constrain
			else {}
		)
		knob_values = {name: value for name, value in values.items() if name not in constraint_values}
		params = to_scenario_parameters(g, knob_values, self._base, strict=strict)
		if outages is not None:
			# Carried onto the parameters here rather than through `--set`, because
			# an outage is not a graph parameter: the graph states quantities and
			# equations, and a line outage is a topology change with no equation
			# behind it. Without this argument the field would be declared,
			# validated, applied by `apply_parameters`, and reachable from nothing
			# but a direct Python call -- the declared-is-not-produced class, on
			# the one parameter that models the spec's own headline scenario.
			params = params.with_value("outages", outages)
		# Everything the caller set that reached no knob and no constraint, which
		# is three findings under one register: a settable graph parameter the
		# engine has no knob for, a graph parameter the graph itself computes (so
		# `propagate` overwrites whatever is set), and a string that is not a
		# graph parameter at all. The last two are the ones that would otherwise
		# vanish -- `untranslated()` enumerates the graph's own settable
		# parameters, so it can name neither -- and a register filtered on it
		# would report a typo, or a derived value, as cleanly carried.
		reached = set(translated(g)) | set(constraint_values)
		dropped = tuple(sorted(name for name in values if name not in reached))
		hook = constraint_function(g, constraint_values) if constrain else None
		record: dict[str, Any] | None = None
		if constrain:
			# The record is the *defaults plus the scenario's overrides*, not the
			# overrides alone: two scenarios that override different subsets of a
			# constraint's terms would otherwise share a key while solving under
			# different bounds. It is what the hook will read, spelled the same
			# way, so the key describes the solve that actually ran.
			record = {
				name: constraint_values.get(
					name, g.nodes[name].default if name in g.nodes else None
				)
				for name in sorted(terms)
			}
			record["_equations"] = list(bound_routes(g))
		outcome = self.solve_with_outcome(
			params, force=force, constraints=record, hook=hook
		)
		audit = audit_scenario_result(outcome.result, g, overrides=dict(values))
		gap = fleet_intensity_gap(outcome.result, g)
		reliability = reliability_gap(outcome.result, g)
		logger.info(
			"whatif.prg.solved",
			cache_key=outcome.cache_key[:12],
			from_cache=outcome.from_cache,
			translated=len(values) - len(dropped),
			dropped=len(dropped),
			constrained=constrain,
			consistent=audit.consistent,
		)
		return PrgSolve(
			outcome=outcome,
			parameters=params,
			audit=audit,
			intensity_gap=gap,
			reliability_gap=reliability,
			dropped=dropped,
			constrained=constrain,
			constraint_terms=tuple(sorted(constraint_values)),
		)


# --------------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------------


def _load_network(source: str | Path | pypsa.Network) -> pypsa.Network:
	if isinstance(source, pypsa.Network):
		return source
	path = Path(source)
	if not path.exists():
		raise FileNotFoundError(f"no network at {path}")
	return pypsa.Network(str(path))


def _network_checksum(network: pypsa.Network, source: str | Path | pypsa.Network) -> str:
	"""The base network's content hash.

	For a network loaded from a file this is the file's hash, which is the
	artefact's own address and needs no re-derivation. For an in-memory network
	the hash is taken over the NetCDF export, which PyPSA writes
	deterministically — verified on this stack, so the same network gives the
	same checksum in a fresh process.
	"""
	if isinstance(source, str | Path):
		return sha256_file(Path(source))

	import hashlib
	import tempfile

	with tempfile.NamedTemporaryFile(suffix=".nc", delete=True) as handle:
		network.export_to_netcdf(handle.name)
		return hashlib.sha256(Path(handle.name).read_bytes()).hexdigest()


def _default_solve(network: pypsa.Network, extra_functionality: Any = None) -> Any:
	"""Solve with PyPSA's own optimiser, and refuse a non-optimal status.

	``extra_functionality`` is PyPSA's hook and is passed through rather than
	ignored: a constrained scenario solved by a function that dropped the hook
	would return an unconstrained answer under a key that says otherwise.

	WHY the status is checked here. ``network.optimize`` returns ``(status,
	condition)`` and leaves ``network.objective`` at whatever it was, so an
	infeasible solve is *not* an exception: it returns, ``extract`` reads an
	objective of zero or the objective constant, and the engine caches a result
	whose cost is a number no feasible dispatch produced. Layer 1's
	``solve_expansion`` already refuses this; the engine's own default did not,
	which was harmless only while nothing could make a what-if network
	infeasible. Constraints do exactly that -- a carbon budget or a reserve
	margin the fleet cannot meet is the ordinary way a scenario fails -- so the
	check belongs here now that the failure is reachable.
	"""
	status, condition = network.optimize(extra_functionality=extra_functionality)
	if status not in ("ok", "optimal", "Optimal"):
		raise SolveError(
			f"the optimiser returned status={status!r} ({condition}); an infeasible "
			f"or unbounded scenario is a result about the scenario, not a number, "
			f"and caching one would serve a cost no feasible dispatch produced"
		)
	return status, condition


def _result_placeholder(
	params: ScenarioParameters, network_checksum: str, code_version: str
) -> ScenarioResult:
	"""A minimal result carrying the scenario's identity.

	Layer 3's price model keys its own work on the scenario, so it is handed a
	result whose identity fields are already correct even though its summaries
	are not yet computed. The alternative — passing the solved network and the
	parameters separately — loses the link between a price and the scenario it
	belongs to.

	The identity fields are the scenario's *inputs* (parameters, network,
	code), not a fresh scenario id: a price attached to a random id could not
	be joined back to the result the engine is about to build.
	"""
	return ScenarioResult(
		scenario_id=cache_key(params, network_checksum, code_version),
		params=params,
		network_checksum=network_checksum,
		code_version=code_version,
		total_cost_usd=0.0,
		total_emissions_tco2=0.0,
		capacity_mix_mw={},
		generation_mwh={},
	)


__all__ = ["DEFAULT_CODE_VERSION", "PriceFn", "SolveFn", "WhatIfEngine"]
