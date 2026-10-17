# SPDX-License-Identifier: MIT
"""The half of the translation layer that turns PRG inequalities into
constraints the optimiser solves under.

WHY this is separate from :mod:`alea.prg.translate`. That module moves a
*parameter* into an engine knob: the graph states a carbon price, the engine
has a carbon price, the two are the same quantity and the translation is
arithmetic. This module moves an *equation* into a constraint: the graph states
that firm capacity plus derated VRE must cover peak demand with a margin, and
the engine has no column for that at all -- the relation between the inequality
and the optimiser's variables exists only in a person's head. The two are
different problems and the register of the first (49 of 52 parameters reach no
knob) says nothing about the register of the second.

WHY the output is a register and not a list of constraints. Of the 38 equations
the library holds, six are inequalities. Two of them -- the reserve margin and
the carbon budget -- have every term the network can supply, and those become
real linopy constraints. The other four are stated over quantities the graph
*derives* (``project_gearing_dscr``, ``rocof_df_dt_hz_per_s``, ``energy_burden``,
``cooling_water_demand_m3``), and a derived quantity is one the graph can only
evaluate from a solved result. Those four are post-solve checks, not
constraints: the graph runs them in :mod:`alea.prg.audit` against what the solve
produced. Writing them as constraints would require inventing the network
column they read, and a constraint built on an invented term binds the build to
a number no fleet has.

WHY a symbol is read from a *declared* source and never inferred. Nothing in
the graph records "``firm_capacity_mw`` is the summed nameplate of the
dispatchable fleet". Inferring it from the name would map it onto whatever
quantity shares the most characters, which is right by accident or wrong by
accident and gives no way to tell which. :data:`SOURCES` states each mapping
where a reviewer of the physics can read it, and the note on each says what the
mapping assumes -- because a constraint is only as good as the assumption
behind its terms.

WHY the fallback for an undeclared symbol is narrow and recorded. A symbol with
no network source that the graph marks settable *and* carries a scalar default
is read from the parameter set, and the route records that it was ``assumed``.
That distinction is the whole difference between "the reserve margin is
computed from this network's fleet" and "the reserve margin is computed from
9,000 MW, the node's stand-in for a system of unknown size". ``peak_demand_mw``
is *also* a settable scalar with a default, which is why it carries a declared
source: without it the fallback would silently swallow one of the two terms
that matter most and bind the build to the default. ``firm_capacity_mw``
carried one for the same reason and no longer needs the fallback at all --
since the endogenous fleet layer landed it is derived, so it is not settable
and the fallback cannot reach it.

WHY a term the walker cannot linearise makes the whole equation unbound rather
than partially bound. A constraint missing one of its terms is not a weaker
constraint, it is a different one -- and it would be added to the model, solved
under, and reported as enforced. ``Pow``, a function call, and a summation
containing a network variable are all refused here, by name, in the route.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from alea.prg.dsl import (
	Add,
	Const,
	DslError,
	Expr,
	Mul,
	Symbol,
	evaluate,
	parse,
	parse_side,
)
from alea.registry.technologies import get_technology, is_known_carrier

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"HOURS_PER_YEAR",
	"ConstraintReport",
	"ConstraintRoute",
	"NetworkSource",
	"SOURCES",
	"add_constraints",
	"bound_parameter_names",
	"bound_routes",
	"constraint_function",
	"coverage",
	"routes",
]


HOURS_PER_YEAR = 8760.0
"""Hours in a year.

A dispatch sum weighted by snapshot hours is a total over the modelled horizon,
which on a two-hour test fixture is two hours and on a planning network is
decades. The carbon budget is stated per year, so the horizon total has to be
annualised, and 8,760 is the year the graph's own ``capacity_factor`` is
defined against -- one year, not one modelled period.
"""


@dataclass(frozen=True)
class NetworkSource:
	"""A PRG symbol the network carries a value for, and how it is read."""

	symbol: str
	kind: str
	"""Which network quantity the symbol names. One of :data:`_READERS`."""
	note: str
	"""What the mapping assumes, stated where the mapping is declared.

	Read by whoever is deciding whether to trust a constrained solve. A
	mapping that counts storage at nameplate, or that assumes one fleet-wide
	intensity, is only as good as the assumption, and an unstated assumption
	is one nobody can check.
	"""


#: The declared routes from a PRG symbol into a network quantity.
#:
#: Short, and each entry is a modelling decision rather than a lookup. The
#: library states its inequalities over the quantities the physics is written
#: in; the network carries capacities, dispatch and load, and the two sets
#: overlap only where a person draws the line.
SOURCES: tuple[NetworkSource, ...] = (
	NetworkSource(
		symbol="firm_capacity_mw",
		kind="dispatchable_capacity",
		note=(
			"Summed over every Generator whose carrier the registry calls "
			"dispatchable, extendable units as the optimiser's own p_nom "
			"variable and fixed units as the constant they are. Two things "
			"this assumes. Storage is not a Generator, so a storage unit's "
			"power rating is not counted, and counting it at full nameplate "
			"toward firm capacity is a modelling choice the graph's node does "
			"not make either. And 'dispatchable' is the registry's "
			"classification, not an availability guarantee -- a dispatchable "
			"unit that is out for maintenance still counts here, which is what "
			"a nameplate reserve margin has always meant."
		),
	),
	NetworkSource(
		symbol="vre_capacity_mw",
		kind="vre_capacity",
		note=(
			"Summed over every Generator the registry calls variable, at "
			"nameplate. The equation derates it by ``capacity_factor`` "
			"afterwards, so the derating happens once, in the equation, where "
			"the graph states it."
		),
	),
	NetworkSource(
		symbol="peak_demand_mw",
		kind="peak_demand",
		note=(
			"The highest coincident load the network carries, summed across "
			"loads at each snapshot and maximised over snapshots. Coincident "
			"because a reserve margin is about the instant the system is "
			"tightest, and a sum of per-load peaks would be a peak no hour "
			"reaches."
		),
	),
	NetworkSource(
		symbol="emissions_mtco2_per_year",
		kind="annual_emissions",
		note=(
			"Dispatch times the registry's intensity per carrier, summed over "
			"the horizon and annualised. The same fleet-average stand-in the "
			"graph's own emissions identity makes: the registry carries one "
			"intensity per carrier, so a fleet whose units differ within a "
			"carrier is represented by the carrier's number. "
			"``audit.fleet_intensity_gap`` measures that difference after the "
			"solve rather than pretending it away."
		),
	),
)

_SOURCE_BY_SYMBOL: dict[str, NetworkSource] = {s.symbol: s for s in SOURCES}


@dataclass(frozen=True)
class ConstraintRoute:
	"""What happened to one constraint-shaped equation."""

	equation_id: str
	status: str
	"""``bound`` (a linopy constraint was added) or ``unbound`` (it was not,
	and ``reason`` says why)."""

	reason: str
	unresolved: tuple[str, ...] = ()
	"""Symbols the network cannot supply and the graph does not declare
	settable -- quantities it derives, which only exist after a solve."""

	assumed: tuple[str, ...] = ()
	"""Symbols read from the parameter set rather than from the network.

	Recorded because a constraint whose terms are half read off the fleet and
	half read off a default is a weaker claim than one read entirely off the
	fleet, and the route is the only place a reader can see which."""


@dataclass(frozen=True)
class ConstraintReport:
	"""What :func:`add_constraints` added to a model, and what it did not."""

	added: tuple[str, ...] = ()
	"""Equation ids a linopy constraint was added under."""

	skipped: tuple[ConstraintRoute, ...] = ()
	"""Routes that produced no constraint, each with its reason."""

	assumed: tuple[str, ...] = field(default=())
	"""Every parameter-set symbol any added constraint read, deduplicated."""

	def summary(self) -> str:
		assert isinstance(self.added, tuple)
		if not self.added:
			return (
				f"no constraint added; {len(self.skipped)} equation(s) "
				f"constrained nothing and each says why"
			)
		extra = (
			f"; {len(self.assumed)} term(s) read from the parameter set rather "
			f"than the network"
			if self.assumed
			else ""
		)
		return (
			f"{len(self.added)} constraint(s) added "
			f"({', '.join(self.added)}){extra}"
		)


# ----------------------------------------------------------------------
# Classification
# ----------------------------------------------------------------------


def _constraint_shaped(graph: ParameterGraph) -> tuple[Any, ...]:
	"""The equations that could become a constraint on a solve.

	Every inequality, and only inequalities. An equality says what a number
	*is*: the graph computes it from its inputs, and the optimiser has nothing
	to add. ``energy_balance`` is the tempting exception and it is not one --
	its terms are annual TWh over the whole system, while the optimiser's nodal
	balance is per-unit dispatch at every node and hour, and a constraint in
	the graph's resolution would state a different law, not the same one twice.
	``energy_demand`` compounds a growth rate and is a derivation outright.

	Derived from the graph rather than transcribed: an inequality added to the
	YAML appears here on the next load. A hand-written list of which equations
	are constraints would go stale in the direction that looks like coverage.
	"""
	return tuple(
		sorted(
			(e for e in graph.equations.values() if e.relation != "eq"),
			key=lambda e: e.id,
		)
	)


def _symbols(equation: Any) -> tuple[str, ...]:
	names: set[str] = set()
	for side in (equation.lhs, equation.rhs):
		names |= set(parse_side(side).symbols)
	return tuple(sorted(names))


def _classify(equation: Any, graph: ParameterGraph) -> ConstraintRoute:
	"""Which route an equation takes, decided without a network.

	No network is needed to say that ``dscr_requirement`` cannot bind: its
	terms are ``project_gearing_dscr``, which the graph derives, and a derived
	parameter has no network column by construction. Deciding this from the
	graph is what lets the register ride in ``prg summary``, where no network
	exists.
	"""
	unresolved: list[str] = []
	assumed: list[str] = []
	for name in _symbols(equation):
		if name in _SOURCE_BY_SYMBOL:
			continue
		node = graph.nodes.get(name)
		if node is None:
			unresolved.append(name)
			continue
		if graph.is_settable(name) and node.default is not None:
			assumed.append(name)
			continue
		# Derived by the graph, or settable with nothing to read: either way
		# the network has no column for it and no default stands in for it.
		unresolved.append(name)

	if unresolved:
		return ConstraintRoute(
			equation_id=equation.id,
			status="unbound",
			reason=(
				f"stated over {list(sorted(unresolved))}, which the graph "
				f"derives from a solved result; the network has no column for "
				f"them, so this is a post-solve check the audit runs rather "
				f"than a constraint on the solve"
			),
			unresolved=tuple(sorted(unresolved)),
			assumed=tuple(sorted(assumed)),
		)

	return ConstraintRoute(
		equation_id=equation.id,
		status="bound",
		reason="every term is a declared network quantity or a settable scalar",
		assumed=tuple(sorted(assumed)),
	)


def routes(graph: ParameterGraph) -> tuple[ConstraintRoute, ...]:
	"""Every constraint-shaped equation and the route it takes.

	No network, no solve: this is the register, and it is what the summary
	serves.
	"""
	return tuple(_classify(equation, graph) for equation in _constraint_shaped(graph))


def bound_routes(graph: ParameterGraph) -> tuple[str, ...]:
	"""The equations that can bind, by id."""
	return tuple(r.equation_id for r in routes(graph) if r.status == "bound")


def bound_parameter_names(graph: ParameterGraph | None = None) -> tuple[str, ...]:
	"""The settable scalars the bindable inequalities read, by name.

	These are graph parameters with no engine knob, and they are not things a
	scenario moves *about the network* -- they are the terms of the
	constraints. A caller that sets one is not perturbing the fleet, it is
	tightening or loosening a bound, and the difference matters to a register:
	counting one as "reached no knob" reports the constraint's own terms as
	dropped while the constraint reads them.

	A symbol with a declared network source is excluded, deliberately.
	``peak_demand_mw`` is a settable scalar too, but the constraint reads it off
	the fleet, so a scenario value for it is ignored by the constraint and is
	honestly a dropped parameter. ``firm_capacity_mw`` is excluded on two
	counts now: it has a source, and since the endogenous fleet layer landed it
	is *derived* -- from ``thermal_capacity_mw`` and
	``dispatchable_re_capacity_mw`` -- so it is not settable at all and cannot
	appear in a set of settable scalars. This is the same set :func:`_symbol`
	reads from ``ctx.params``, derived the same way rather than transcribed.
	"""
	if graph is None:
		from alea.prg.graph import load_graph

		g = load_graph()
	else:
		g = graph

	names: set[str] = set()
	for equation in _constraint_shaped(g):
		if _classify(equation, g).status != "bound":
			continue
		for name in _symbols(equation):
			if name in _SOURCE_BY_SYMBOL:
				continue
			node = g.nodes.get(name)
			if node is not None and g.is_settable(name) and node.default is not None:
				names.add(name)
	return tuple(sorted(names))


def coverage(graph: ParameterGraph) -> dict[str, Any]:
	"""How much of the equation library reaches a constraint, counted both ways.

	``identities`` is the other direction and a different finding: an equation
	that derives a value is not a constraint anybody forgot to add, it is a
	definition the graph evaluates. Folding the two into one number would make
	the register read as 2 of 38 when the honest denominator is 6.
	"""
	classified = routes(graph)
	bound = [r.equation_id for r in classified if r.status == "bound"]
	unbound = [r.equation_id for r in classified if r.status == "unbound"]
	total = len(graph.equations)
	shaped = len(classified)
	return {
		"bound": bound,
		"unbound": unbound,
		"count": len(bound),
		"constraint_shaped": shaped,
		"identities": total - shaped,
		"total": total,
		"fraction": (len(bound) / shaped) if shaped else 0.0,
		"routes": [
			{
				"equation_id": r.equation_id,
				"status": r.status,
				"reason": r.reason,
				"unresolved": list(r.unresolved),
				"assumed": list(r.assumed),
			}
			for r in classified
		],
	}


# ----------------------------------------------------------------------
# Reading the network
# ----------------------------------------------------------------------


def _extendable(network: Any) -> set[str]:
	frame = network.generators
	if "p_nom_extendable" not in frame.columns:
		return set()
	flags = frame["p_nom_extendable"].fillna(False).astype(bool)
	return {str(name) for name, flag in flags.items() if flag}


def _generator_capacity(network: Any, model: Any, *, variable: bool) -> Any:
	"""Summed nameplate over one class of generator, as an expression plus a constant.

	An extendable unit's nameplate is the optimiser's decision, so it enters
	the constraint as the ``p_nom`` variable. A fixed unit's is data, so it
	enters as a number. A constraint that treated both as variables would
	leave the fixed fleet free to move.
	"""
	generators = network.generators
	if generators.empty:
		return 0.0

	extendable = _extendable(network)
	total: Any = 0.0
	decided: list[str] = []
	for name in generators.index:
		carrier = str(generators.at[name, "carrier"])
		if not is_known_carrier(carrier):
			# An unmapped carrier is a plant the registry cannot classify, and
			# guessing which side of the reserve margin it belongs on is how a
			# constraint silently drops capacity. It is left out of both sums,
			# which understates the margin rather than overstating it.
			continue
		if get_technology(carrier).variable is not variable:
			continue
		if str(name) in extendable:
			decided.append(str(name))
		else:
			total = total + float(generators.at[name, "p_nom"])

	if decided:
		try:
			nameplate = model["Generator-p_nom"].sel(name=decided).sum("name")
		except KeyError:
			# No extendable generators reached the model, so there is no
			# variable to read. Not an error: a fully-fixed fleet is a fleet.
			nameplate = None
		if nameplate is not None:
			total = total + nameplate
	return total


def _peak_demand(network: Any) -> float:
	"""The highest coincident load, in MW."""
	loads = network.loads
	if loads.empty:
		return 0.0
	dynamic = getattr(network, "loads_t", None)
	p_set = getattr(dynamic, "p_set", None) if dynamic is not None else None
	if p_set is not None and not p_set.empty:
		return float(p_set.sum(axis=1).max())
	if "p_set" in loads.columns:
		return float(loads["p_set"].fillna(0.0).sum())
	return 0.0


def _annual_emissions(network: Any, model: Any) -> Any:
	"""Dispatch times intensity, summed over the horizon and annualised to Mt/yr.

	The unit chain, written out because it is where this can go wrong by a
	factor of a thousand: MW x hours = MWh; MWh x tonne/MWh = tonne; tonne /
	1e6 = Mt. The horizon total is then scaled by 8,760 over the modelled
	hours, which is 1 on a network that already spans a full year and is what
	makes a two-hour fixture comparable to the graph's per-year node.
	"""
	weights = network.snapshot_weightings["generators"].to_numpy()
	horizon_hours = float(weights.sum())
	if horizon_hours <= 0.0:
		return 0.0

	try:
		dispatch_var = model["Generator-p"]
	except KeyError:
		return 0.0

	total: Any = 0.0
	for name in network.generators.index:
		carrier = str(network.generators.at[name, "carrier"])
		if not is_known_carrier(carrier):
			continue
		intensity = get_technology(carrier).co2_t_per_mwh
		if intensity <= 0.0:
			continue
		try:
			dispatch = dispatch_var.sel(name=[str(name)]).sum("name")
		except KeyError:
			continue
		total = total + (dispatch * weights).sum() * intensity

	return total / 1e6 * (HOURS_PER_YEAR / horizon_hours)


_READERS = {
	"dispatchable_capacity": lambda ctx, _src: _generator_capacity(
		ctx.network, ctx.model, variable=False
	),
	"vre_capacity": lambda ctx, _src: _generator_capacity(
		ctx.network, ctx.model, variable=True
	),
	"peak_demand": lambda ctx, _src: _peak_demand(ctx.network),
	"annual_emissions": lambda ctx, _src: _annual_emissions(ctx.network, ctx.model),
}


@dataclass
class _Context:
	graph: ParameterGraph
	params: Mapping[str, float]
	network: Any
	model: Any
	assumed: set[str] = field(default_factory=set)
	unresolved: set[str] = field(default_factory=set)
	nonlinear: set[str] = field(default_factory=set)


def _is_constant(value: Any) -> bool:
	return isinstance(value, (int, float))


def _symbol(name: str, ctx: _Context) -> Any:
	source = _SOURCE_BY_SYMBOL.get(name)
	if source is not None:
		return _READERS[source.kind](ctx, source)

	node = ctx.graph.nodes.get(name)
	if node is None:
		ctx.unresolved.add(name)
		return None
	if ctx.graph.is_settable(name):
		if name in ctx.params:
			ctx.assumed.add(name)
			# A level name has no arithmetic, so it cannot enter a constraint
			# expression; it is reported unresolved, which is the same answer
			# the DSL gives any symbol it cannot evaluate.
			value = ctx.params[name]
			return None if isinstance(value, str) else float(value)
		if node.default is not None and not isinstance(node.default, str):
			ctx.assumed.add(name)
			return float(node.default)
	ctx.unresolved.add(name)
	return None


def _evaluate(expr: Expr, ctx: _Context) -> Any:
	"""A DSL subtree as a float or a linopy expression, or ``None``.

	``None`` means the walker could not produce a term, and every caller
	propagates it: a sum with an unreadable term is unreadable, not the sum of
	the rest.
	"""
	if isinstance(expr, Const):
		return float(expr.value)

	if isinstance(expr, Symbol):
		return _symbol(expr.name, ctx)

	if isinstance(expr, Add):
		total: Any = 0.0
		for term in expr.terms:
			value = _evaluate(term, ctx)
			if value is None:
				return None
			total = total + value
		return total

	if isinstance(expr, Mul):
		scalar = 1.0
		expression: Any = None
		for factor in expr.factors:
			value = _evaluate(factor, ctx)
			if value is None:
				return None
			if _is_constant(value):
				scalar *= float(value)
			elif expression is None:
				expression = value
			else:
				# Two optimiser expressions in a product is a bilinear term.
				# It is not linear, and a linear model given it either refuses
				# or linearises it silently; both are worse than saying so.
				ctx.nonlinear.add(expr.source())
				return None
		return scalar if expression is None else expression * scalar

	# Pow, Func, Subscript, Sum. Constant-fold where the whole subtree is
	# data, and refuse where it is not: a power of a decision variable is
	# nonlinear, and this module builds linear constraints.
	try:
		return float(evaluate(expr, {}))
	except DslError:
		ctx.nonlinear.add(expr.source())
		return None


def _relation_holds(lhs: Any, rhs: Any, relation: str) -> Any:
	if relation == "leq":
		return lhs <= rhs
	if relation == "geq":
		return lhs >= rhs
	return lhs == rhs


def _why_unbound(lhs: Any, rhs: Any, blockers: list[str]) -> str:
	"""Why a walk produced no constraint, with the numbers where there are any.

	A constraint with no decision variable in it is a *checked* quantity, not a
	constraint: on a fleet with no extendable unit the reserve margin folds to
	``200 >= 115``, which either holds trivially or makes the model infeasible
	with nothing to say the infeasibility came from arithmetic rather than from
	the optimiser. Naming the two sides in the reason is what lets a reader see
	which, without re-deriving it.
	"""
	if _is_constant(lhs) and _is_constant(rhs):
		return (
			f"every term is data ({float(lhs)} against {float(rhs)}), so there "
			f"is no decision variable for the optimiser to move; this is a "
			f"consistency check the graph already runs, not a constraint"
		)
	return f"the walker could not linearise {blockers}"


def add_constraints(
	network: Any,
	params: Mapping[str, float] | None = None,
	*,
	graph: ParameterGraph | None = None,
	model: Any | None = None,
) -> ConstraintReport:
	"""Add every bindable PRG inequality to a model as a linopy constraint.

	Callable from PyPSA's ``extra_functionality`` hook, where the model exists
	and the network has not yet been solved. Returns the register of what it
	did, because a caller that only saw the constraints it got would have no
	way to learn that four equations constrained nothing.

	``params`` supplies the settable scalars the equations read -- the reserve
	requirement, the capacity factor, the carbon budget and its horizon. A
	parameter absent from it falls back to the node's declared default, and
	the route records that it did.
	"""
	if graph is None:
		from alea.prg.graph import load_graph

		graph = load_graph()

	model = model if model is not None else getattr(network, "model", None)
	if model is None:
		raise ValueError(
			"the network carries no optimiser model; add_constraints runs "
			"inside the model build, where the decision variables exist and "
			"the constraint can name them"
		)

	ctx = _Context(graph=graph, params=params or {}, network=network, model=model)
	added: list[str] = []
	skipped: list[ConstraintRoute] = []
	assumed: set[str] = set()

	for equation in _constraint_shaped(graph):
		route = _classify(equation, graph)
		if route.status != "bound":
			skipped.append(route)
			continue

		ctx.assumed = set()
		ctx.unresolved = set()
		ctx.nonlinear = set()
		lhs = _evaluate(parse_side(equation.lhs), ctx)
		rhs = _evaluate(parse_side(equation.rhs), ctx)

		if lhs is None or rhs is None or (_is_constant(lhs) and _is_constant(rhs)):
			blockers = sorted(ctx.nonlinear) or sorted(ctx.unresolved)
			skipped.append(
				ConstraintRoute(
					equation_id=equation.id,
					status="unbound",
					reason=_why_unbound(lhs, rhs, blockers),
					unresolved=tuple(sorted(ctx.unresolved)),
					assumed=tuple(sorted(ctx.assumed)),
				)
			)
			continue

		model.add_constraints(
			_relation_holds(lhs, rhs, equation.relation), name=equation.id
		)
		added.append(equation.id)
		assumed |= ctx.assumed

	return ConstraintReport(
		added=tuple(added), skipped=tuple(skipped), assumed=tuple(sorted(assumed))
	)


def constraint_function(
	graph: ParameterGraph | None = None,
	params: Mapping[str, float] | None = None,
) -> Any:
	"""An ``extra_functionality`` callable that adds the PRG's inequalities.

	PyPSA calls this with the network and the snapshot subset after the model
	is built and before it is solved, which is exactly the window a constraint
	has to be added in. Returning a closure rather than a class keeps the
	engine's seam a plain callable -- the same shape the what-if solver seam
	takes, and for the same reason: a seam that is a function can be counted.
	"""

	def extra_functionality(network: Any, _snapshots: Any = None) -> None:
		add_constraints(network, params, graph=graph)

	return extra_functionality
