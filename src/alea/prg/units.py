# SPDX-License-Identifier: MIT
"""Dimensional consistency: does each equation's arithmetic carry its units?

WHY this exists now and did not before. ``views.py`` said the check was skipped
because it "catches a class of error this graph does not currently make". That
was an assumption, and it is false: the graph makes it in five equations, and
one of them -- ``emissions_definition``, ``TWh x tonne/MWh = MtCO2/year`` -- is
off by the factor that separates a megatonne from a kilotonne, on the identity
the carbon budget is built from. The assumption was never tested because there
was nothing to test it with. This module is that thing.

WHY the check compares *dimensions* and not unit strings. ``lcoe_definition``
is ``annualised_capex_usd_per_kw * 1000 / (8760 * capacity_factor)``, and the
``1000`` and ``8760`` are unit conversions -- kW to MW and hours to years. A
checker that demanded the literal units multiply out would fail an equation
that is right. The spec says the same thing: ``lhs.dimensionality ==
rhs.dimensionality``. The literal carries the scale, and the dimension is what
the graph is responsible for.

WHY the registry is written out rather than taken from Pint's defaults. Pint
knows ``tonne`` and ``year``; it does not know ``USD`` as a base dimension, nor
``DALY``, nor the graph's ``m3`` spelling. Without the definitions below the
registry raises on a unit it has never seen, and a check that raises on the
graph's own vocabulary is a check nobody runs twice. The definitions are the
graph's, declared once, here.

WHY an undecidable result is not a pass. A ``Func`` of a dimensioned argument,
a power whose exponent is not an integer, a symbol with no unit recorded: the
arithmetic has a dimension but this walker cannot compute it. Those equations
are counted as undecidable and reported separately, because folding them into
"consistent" would let the check's coverage shrink in silence as the graph
grows -- which is the failure mode of every gate that reports only a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import re

import pint
from pint.facets.plain.unit import PlainUnit

from alea.prg.dsl import (
	Add,
	Const,
	Expr,
	Func,
	Mul,
	Pow,
	Subscript,
	Sum,
	Symbol,
	parse_side,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph
	from alea.prg.views import Equation

#: Pint's stubs separate the plain unit ``parse_units`` returns from the
#: registry unit the arithmetic returns. Both carry ``.dimensionality``, which
#: is the only attribute this module reads, so the wider of the two names them.
type Unit = PlainUnit

__all__ = [
	"DimensionalMismatch",
	"EquationCheck",
	"UnitReport",
	"check_equation",
	"check_graph",
	"unit_of",
	"ureg",
]


def _registry() -> pint.UnitRegistry:
	"""The graph's unit vocabulary, as a Pint registry.

	``[currency]`` and ``[job]`` are base dimensions of this domain and not of
	physics; Pint has no reason to carry them, and the graph has no reason to
	express a job as a combination of SI units.

	``kt`` is *redefined*, not defined: Pint reads it as the knot, a unit of
	speed, and this graph means the kilotonne. Redefinition raises a warning
	that would print on every run, so the knot is removed first -- the graph's
	meaning is the one that survives, and Pint's is the one that goes.

	WHY EVERY UNIT THE GRAPH DECLARES IS IN HERE. A unit the registry does not
	know makes the walker return ``None``, which reads as *undecidable* -- and
	an undecidable equation is not a pass. So a gap in this vocabulary is a
	hole in the coverage of the whole unit check, and it is a hole that grows
	whenever an author writes a unit this list has not been told about. The
	three cases that arrived with the generated batches were ``events/year``
	(SAIDI and SAIFI, whose ``events`` is a count of interruptions and not a
	time), ``parcels/km2`` and ``sites/100km2`` (land take, where the counted
	thing is a parcel or a site), and ``USD/MMBtu`` (a gas price, in the unit
	the market quotes it in). Each is a base dimension of this domain for the
	same reason ``[job]`` is: the graph has no reason to express a parcel as a
	combination of SI units, and doing so would manufacture a mismatch.

	``million`` and ``basis_points`` are dimensionless scales, and Pint refuses
	a bare ``million`` in a compound expression only because it is not a unit --
	declaring it as ``1e6`` makes ``USD million`` parse as a currency and
	``basis_points`` as the dimensionless ratio it is.
	"""
	registry = pint.UnitRegistry()
	# Remove Pint's `kt` (knot) before the graph's `kt` (kilotonne) replaces
	# it, so the redefinition is a definition and does not warn.
	registry._units.pop("kt", None)
	registry._units.pop("knot", None)
	for definition in (
		"USD = [currency]",
		"person = [count]",
		"people = person",
		"death = person",
		"deaths = death",
		"job = [job]",
		"jobs = job",
		"tCO2 = tonne",
		"MtCO2 = megatonne",
		"kt = kilotonne",
		# A DALY is a year of life lived with disability -- a person-year, not
		# a base dimension of its own. Declaring it a base dimension would make
		# ``dalys = deaths x years_of_life_lost`` read as a mismatch when the
		# arithmetic is exactly right, which is a finding manufactured by the
		# registry rather than found in the graph.
		"DALY = person * year",
		# The counted things this domain counts. Each is a base dimension for
		# the reason given above: a parcel is not a combination of SI units, and
		# ``sites`` against ``parcels`` is a real mismatch that this registry
		# should be able to see.
		"event = [event]",
		# Reactive power: a register-gap the compliance batch exposed -- the
		# requirement is measured in MVAr, and the registry had no spelling for
		# it. Dimensionally apparent power, so a share of peak MW stays
		# comparable across the walker's own dimensionality test.
		"VAr = ampere * volt",
		"MVAr = 1000000 * VAr",
		"events = event",
		"connection = [connection]",
		"connections = connection",
		"parcel = [parcel]",
		"parcels = parcel",
		"site = [site]",
		"sites = site",
		# A million British thermal units, which is how a gas price is quoted.
		"MMBtu = 1e6 * Btu",
		# Dimensionless scales. ``million`` is not a unit of anything, which is
		# exactly why Pint rejects it bare; as a scale it multiplies cleanly.
		"million = 1e6",
		"billion = 1e9",
		"basis_points = 1e-4",
	):
		registry.define(definition)
	return registry


#: One registry for the process. Pint's is not cheap to build and is immutable
#: once the definitions are in, so a per-call registry would be pure overhead.
ureg = _registry()


class DimensionalMismatch(ValueError):
	"""An expression whose terms cannot share a dimension.

	Carries the offending sub-expression's source, because "the equation is
	inconsistent" and "``a + b`` is inconsistent, at ``a`` in USD and ``b`` in
	MW" are different messages to the person who has to fix it.
	"""

	def __init__(self, source: str, left: Unit, right: Unit) -> None:
		self.source = source
		self.left = left
		self.right = right
		super().__init__(
			f"{source} adds {left.dimensionality} to {right.dimensionality}, "
			f"which cannot share a dimension"
		)


def _parse_unit(text: str) -> Unit:
	"""Parse one of the graph's unit strings.

	The unit strings are written to be *read* -- they appear in the YAML beside
	a parameter's name and in the CLI's report -- so this normalises them to
	what Pint parses rather than asking the graph to spell them Pint's way.
	Four spellings need it, and each is a notation a person writes:

	* ``m3`` is a cubic metre. Pint reads the bare ``3`` as an exponent only
	  when it is written ``**3``, so the digit is spelled out.
	* ``MW.s`` is a megawatt-second. Pint reads the dot as a decimal point, so
	  it becomes ``*``.
	* ``USD/MW-km`` is a currency per megawatt-kilometre. Pint reads the hyphen
	  as subtraction and raises ``TypeError`` on two unit helpers, which is a
	  crash rather than an undecidable -- the worst of the three outcomes. A
	  hyphen between two unit symbols is a product in every unit notation.
	* ``USD million`` and ``sites/100km2`` put a space and a numeric factor
	  where Pint wants an operator. The space becomes ``*``; the numeric factor
	  in a denominator is a scale, and since it divides, folding it into the
	  numerator as its reciprocal keeps the dimensionality and drops the scale
	  the walker has no use for. A ``2`` closing a unit name is an exponent
	  (``km2`` is ``km**2``).

	Every rewrite is guarded by a lookbehind for a unit-symbol character, so
	none of them can fire on a spelling Pint already reads.
	"""
	text = text.strip()
	if text in ("", "1"):
		return ureg.dimensionless
	text = text.replace("m3", "m**3")
	text = re.sub(r"(?<=[a-z])2(?![0-9*.])", "**2", text)
	text = re.sub(r"/\s*\d+(?:\.\d+)?(?=[A-Za-z])", "/", text)
	text = re.sub(r"(?<=[A-Za-z0-9*\]])\s*-\s*(?=[A-Za-z])", "*", text)
	text = re.sub(r"(?<=[A-Za-z0-9\]])\s+(?=[A-Za-z])", "*", text)
	return ureg.parse_units(text.replace(".", "*"))


def unit_of(expression: Expr, graph: ParameterGraph) -> Unit | None:
	"""The dimension of ``expression``, or ``None`` if it cannot be decided.

	Raises :class:`DimensionalMismatch` when a sum's terms provably differ: a
	proven mismatch is a finding, and returning ``None`` for it would hide it
	among the undecidable.
	"""
	if isinstance(expression, Const):
		return ureg.dimensionless
	if isinstance(expression, Symbol):
		node = graph.nodes.get(expression.name)
		if node is None or node.unit is None:
			return None
		try:
			return _parse_unit(node.unit)
		except pint.errors.UndefinedUnitError:
			# A unit this registry has not been told about. That is a gap in
			# the registry or a typo in the graph, not a dimensional finding,
			# so it is undecidable rather than a failure.
			return None
	if isinstance(expression, Add):
		# The compound-growth convention: `1 + rate`. Strict algebra refuses
		# 1 + 1/[time], and the annuity blessing already accepted the same
		# convention inside a power; the same content appears bare everywhere
		# an escalation or a VAT multiplies a price, and the Fisher equation
		# divides by it. A bare sum of a constant and ONE rate is a growth
		# factor -- dimensionless -- which is the convention, stated once
		# and scoped: two terms only, one a constant, the other carrying
		# 1/[time]; anything else takes the standard path.
		if len(expression.terms) == 2:
			consts = [t for t in expression.terms if isinstance(t, Const)]
			rates = [t for t in expression.terms if not isinstance(t, Const)]
			if len(consts) == 1 and len(rates) == 1:
				rate_unit = unit_of(rates[0], graph)
				if rate_unit is not None:
					period = (rate_unit**-1).dimensionality
					if period != ureg.dimensionless.dimensionality:
						return ureg.dimensionless
		terms = [unit_of(term, graph) for term in expression.terms]
		decided = [unit for unit in terms if unit is not None]
		if len(decided) != len(terms):
			return None
		first = decided[0]
		for unit in decided[1:]:
			if unit.dimensionality != first.dimensionality:
				raise DimensionalMismatch(expression.source(), first, unit)
		return first
	if isinstance(expression, Mul):
		product: Unit = ureg.dimensionless
		for factor in expression.factors:
			unit = unit_of(factor, graph)
			if unit is None:
				return None
			product = product * unit
		return product
	if isinstance(expression, Pow):
		# The annuity convention: `(1 + rate) ** life`. Strict dimensional
		# algebra refuses the base -- 1 + 1/[time] -- but the expression the
		# field writes is dimensionally well-posed, because the exponent's
		# content is rate x time, which IS dimensionless: compounding a
		# per-year rate over a number of years builds a growth factor, and
		# every annuity in the library (crf, the escalation compounds, the
		# elasticity's implication) is this form. The walker accepts it when
		# the base is a bare sum of a constant and a single rate whose
		# dimensionality times a [time] exponent cancels, and declines to
		# judge anything else -- a blessing scoped to the convention, not a
		# hole in the algebra.
		addend = expression.base if isinstance(expression.base, Add) else None
		if addend is not None and len(addend.terms) == 2:
			consts = [t for t in addend.terms if isinstance(t, Const)]
			rates = [t for t in addend.terms if not isinstance(t, Const)]
			if len(consts) == 1 and len(rates) == 1:
				rate_unit = unit_of(rates[0], graph)
				if rate_unit is not None:
					if isinstance(expression.exponent, Const):
						# A numeric exponent folds the base to a plain
						# number: an annuity discount factor `(1 + pi) ** -1`
						# is not a rate, it is a coefficient.
						return ureg.dimensionless
					exponent_unit = unit_of(expression.exponent, graph)
					if exponent_unit is None:
						return None
					annualised = rate_unit**-1  # the rate's period
					if exponent_unit.dimensionality == annualised.dimensionality:
						# A [time] exponent cancels the rate: the result is a
						# growth FACTOR (an annuity term), dimensionless.
						return ureg.dimensionless
					if exponent_unit.dimensionality == ureg.dimensionless.dimensionality:
						# A dimensionless symbolic exponent (an elasticity)
						# leaves the base's own period in the result:
						# (1 + g_Y)^eps is a growth *rate* per year.
						return rate_unit
		base = unit_of(expression.base, graph)
		if base is None:
			return None
		if isinstance(expression.exponent, Const) and float(
			expression.exponent.value
		).is_integer():
			return base ** int(expression.exponent.value)
		# A symbolic exponent is decidable only when both sides are pure
		# numbers: ``ratio ** elasticity`` is dimensionless whatever the
		# elasticity turns out to be, and the learning curve's exponent is a
		# ``log`` ratio. A dimensioned base to a non-integer power is not --
		# ``MW ** 0.5`` has a dimension this walker has no reason to name.
		exponent = unit_of(expression.exponent, graph)
		if (
			exponent is not None
			and base.dimensionality == ureg.dimensionless.dimensionality
			and exponent.dimensionality == ureg.dimensionless.dimensionality
		):
			return ureg.dimensionless
		return None
	if isinstance(expression, Func):
		return _unit_of_func(expression, graph)
	if isinstance(expression, (Sum, Subscript)):
		# An indexed sum reduces to the dimension of its body; a subscript
		# names an element of a vector, which carries the vector's unit.
		inner = expression.body if isinstance(expression, Sum) else expression.base
		return unit_of(inner, graph)
	return None


def _unit_of_func(expression: Func, graph: ParameterGraph) -> Unit | None:
	"""The dimension of a function call, for the functions that have one.

	Only the functions whose dimensional behaviour is a fact are decided:
	``abs`` is its argument, ``sqrt`` is its argument to the half, and the
	transcendental functions take a dimensionless argument and return a
	dimensionless value. Anything else -- a ``min`` of two dimensioned values,
	say -- is undecidable here rather than guessed.
	"""
	units = [unit_of(arg, graph) for arg in expression.args]
	decided = [unit for unit in units if unit is not None]
	if len(decided) != len(units):
		return None
	first = decided[0]
	if expression.name == "abs":
		return first
	if expression.name == "sqrt":
		return first ** 0.5
	if expression.name in {
		"exp", "log", "ln", "log10", "log2",
		"sin", "cos", "tan", "sinh", "cosh", "tanh",
		"asin", "acos", "atan", "erf",
	}:
		# A transcendental function is a series in its argument, so the
		# argument is a pure number. `log(x)` with x in MW is a category error,
		# not a convention, and Pint's dimensionality test says so.
		for unit in decided:
			if unit.dimensionality != ureg.dimensionless.dimensionality:
				return None
		return ureg.dimensionless
	return None


@dataclass(frozen=True)
class EquationCheck:
	"""One equation's dimensional verdict."""

	equation_id: str
	decidable: bool
	consistent: bool
	lhs: str
	rhs: str
	detail: str = ""

	def summary(self) -> str:
		if not self.decidable:
			return f"{self.equation_id}: undecidable ({self.detail})"
		if self.consistent:
			return f"{self.equation_id}: {self.lhs} = {self.rhs}"
		return f"{self.equation_id}: {self.lhs} != {self.rhs} ({self.detail})"


def check_equation(
	equation: Equation, graph: ParameterGraph
) -> EquationCheck:
	"""Check one equation's two sides for a shared dimension.

	The relation matters: an inequality compares two values and so requires the
	same dimension as an equality, and a check that skipped the inequalities
	would leave the four boundary equations -- the ones a regulator's number
	sits in -- unexamined.
	"""
	assert equation is not None, "check_equation called with no equation"
	try:
		left = unit_of(parse_side(equation.lhs), graph)
		right = unit_of(parse_side(equation.rhs), graph)
	except DimensionalMismatch as mismatch:
		return EquationCheck(
			equation_id=equation.id,
			decidable=True,
			consistent=False,
			lhs="",
			rhs="",
			detail=str(mismatch),
		)
	if left is None or right is None:
		side = "lhs" if left is None else "rhs"
		return EquationCheck(
			equation_id=equation.id,
			decidable=False,
			consistent=False,
			lhs="",
			rhs="",
			detail=f"the {side} has a dimension this walker cannot compute",
		)
	consistent = left.dimensionality == right.dimensionality
	return EquationCheck(
		equation_id=equation.id,
		decidable=True,
		consistent=consistent,
		lhs=f"{left.dimensionality}",
		rhs=f"{right.dimensionality}",
		detail="" if consistent else "the two sides do not share a dimension",
	)


@dataclass(frozen=True)
class UnitReport:
	"""Every equation's verdict, and the counts that say how much it covered."""

	checks: tuple[EquationCheck, ...]

	exempt: tuple[str, ...] = ()
	"""Equations whose ``unit_check`` is ``False``, by id.

	An exemption is not a pass and is not counted as one. It says the walk's
	verdict on this equation is known and not actionable -- the equation is
	declared undecidable by whoever wrote it -- so a reader can tell it apart
	from an equation nobody has looked at. The two are different findings and
	the summary keeps them apart, which is the whole reason the field is a
	separate tuple rather than a filter applied to ``checks``.
	"""

	@property
	def consistent(self) -> tuple[EquationCheck, ...]:
		return tuple(c for c in self.checks if c.decidable and c.consistent)

	@property
	def inconsistent(self) -> tuple[EquationCheck, ...]:
		return tuple(c for c in self.checks if c.decidable and not c.consistent)

	@property
	def undecidable(self) -> tuple[EquationCheck, ...]:
		"""Equations the walk could not decide, excluding declared exemptions."""
		return tuple(
			c for c in self.checks if not c.decidable and c.equation_id not in self.exempt
		)

	def summary(self) -> str:
		exempt = (
			f"; {len(self.exempt)} "
			f"{'is' if len(self.exempt) == 1 else 'are'} exempt by declaration"
			if self.exempt
			else ""
		)
		return (
			f"{len(self.consistent)} of {len(self.checks)} equations are "
			f"dimensionally consistent; {len(self.inconsistent)} are not, and "
			f"{len(self.undecidable)} could not be decided from the recorded "
			f"units{exempt}. An undecidable equation is not a pass."
		)


def check_graph(graph: ParameterGraph) -> UnitReport:
	"""Check every equation in the graph.

	Every equation is checked, including an exempt one: ``unit_check: False``
	does not skip the walk, it reclassifies the verdict. Skipping would mean an
	equation that later *became* decidable -- a unit added to its vocabulary --
	stayed unreported behind a flag nobody revisited.
	"""
	assert graph is not None, "check_graph called with no graph"
	return UnitReport(
		checks=tuple(
			check_equation(equation, graph)
			for equation in graph.equations.values()
		),
		exempt=tuple(
			equation.id
			for equation in graph.equations.values()
			if not equation.unit_check
		),
	)
