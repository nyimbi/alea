# SPDX-License-Identifier: MIT
"""The ALEA mathematical DSL: create, render, evaluate, differentiate, solve.

An equation is not a string that happens to produce a number. It is an object
with three lives, and this module exists because all three have to be the *same*
object:

* **created** -- by an author in the equation library, as text; or by code, as
  an expression built from operators. ``parse("a * (1 + b)")`` and
  ``sym("a") * (1 + sym("b"))`` yield the same tree, so a formula written in a
  YAML file and one written in a test are compared rather than eyeballed.
* **rendered** -- as LaTeX for a report, as Unicode for a terminal, as MathML
  for a browser, and back to source text. Rendering is the half that makes the
  library reviewable: a reader who owns the physics can check
  ``\\frac{E}{\\eta}`` where a serialised AST is opaque.
* **evaluated** -- numerically at a point, over arrays, symbolically
  differentiated, simplified, and solved for a variable.

WHY a tree of our own and not SymPy. SymPy is the right tool for algebra this
code does not do: it factors, integrates, and solves systems. What ALEA needs
is a closed, inspectable, serialisable formula object whose derivative and
rendering are known to agree with its evaluation, and which refuses an
operation it does not implement rather than returning an unevaluated
``Derivative`` that looks like an answer. The whitelist is the feature: this
DSL cannot silently do something the engine does not model.

WHY the parser is Python's ``ast`` and not a grammar. The accepted language is
arithmetic over named parameters with a fixed function set and a summation
operator -- exactly the expression grammar Python already implements, in the
standard library, maintained by people who do nothing else, with real error
messages. Every node type not named in ``_ALLOWED`` is refused by name, which
is the property that matters, because the alternative to a whitelist is
``eval``. A hand-written grammar would add a parser dependency and a second set
of error messages to learn.

WHAT IS DELIBERATELY ABSENT. No integration, no factoring, no general
equation-system solving, no LaTeX *input*. Each is a real feature with a real
cost, and none is on the path from a parameter change to a consistent
parameter set. :meth:`Expr.diff` raises ``DslError`` naming the function it
cannot differentiate rather than returning something that renders plausibly
and is wrong.
"""

from __future__ import annotations

import ast
import functools
import math
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.special as scipy_special
from scipy.optimize import brentq

__all__ = [
	"Add",
	"Const",
	"DslError",
	"Expr",
	"Expression",
	"Func",
	"LINEAR",
	"NONLINEAR",
	"Mul",
	"Pow",
	"Subscript",
	"Sum",
	"Symbol",
	"const",
	"evaluate",
	"evaluate_array",
	"linear_coefficients",
	"linearity_in",
	"parse",
	"parse_side",
	"simplify",
	"solve_affine",
	"solve_for",
	"symbols_of",
	"sym",
]


class DslError(ValueError):
	"""An expression is malformed, unsupported, or names what does not exist."""


# ---------------------------------------------------------------------------
# The function library
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MathFunction:
	"""One callable in the DSL, with everything the other lives need.

	``derivative`` returns the derivative of ``f(u)`` with respect to the
	*argument*, so the chain rule is applied once by :func:`diff` and not
	repeated in every rule. A function with no ``derivative`` is refused by
	:meth:`Expr.diff` -- ``min`` has a derivative almost everywhere and an
	undefined one where it matters, and returning a step function that renders
	as a formula would be a wrong answer wearing the right shape.
	"""

	impl: Callable[..., float]
	latex: str
	arity: int | None  # None is variadic
	derivative: Callable[[Expr], Expr] | None = None
	#: The array-valued implementation. ``impl`` is a :mod:`math` callable, and
	#: ``math.exp(array([1, 2]))`` raises rather than broadcasting, so the array
	#: path cannot reuse it. Where no NumPy equivalent exists (``min``/``max``
	#: are the reductions, not the elementwise pair) the field stays ``None``
	#: and :meth:`Func._eval` refuses the array by name instead of guessing.
	vectorised: Callable[..., Any] | None = None


def _f_abs(x: float) -> float:
	return abs(x)


def _f_min(*xs: float) -> float:
	return min(xs)


def _f_max(*xs: float) -> float:
	return max(xs)


def _f_floor(x: float) -> float:
	return float(math.floor(x))


def _v_min(*xs: Any) -> Any:
	return functools.reduce(np.minimum, xs)


def _v_max(*xs: Any) -> Any:
	return functools.reduce(np.maximum, xs)


_FUNCTIONS: dict[str, MathFunction] = {
	"exp": MathFunction(
		math.exp, r"\exp", 1, lambda u: Func("exp", (u,)), vectorised=np.exp
	),
	"ln": MathFunction(
		math.log, r"\ln", 1, lambda u: Pow(u, Const(-1.0)), vectorised=np.log
	),
	"log": MathFunction(
		math.log, r"\ln", 1, lambda u: Pow(u, Const(-1.0)), vectorised=np.log
	),
	"log10": MathFunction(
		math.log10,
		r"\log_{10}",
		1,
		lambda u: Pow(Mul.of(Const(math.log(10.0)), u), Const(-1.0)),
		vectorised=np.log10,
	),
	"log2": MathFunction(
		math.log2,
		r"\log_{2}",
		1,
		lambda u: Pow(Mul.of(Const(math.log(2.0)), u), Const(-1.0)),
		vectorised=np.log2,
	),
	"sqrt": MathFunction(
		math.sqrt,
		r"\sqrt",
		1,
		lambda u: Pow(Mul.of(Const(2.0), Func("sqrt", (u,))), Const(-1.0)),
		vectorised=np.sqrt,
	),
	"sin": MathFunction(
		math.sin, r"\sin", 1, lambda u: Func("cos", (u,)), vectorised=np.sin
	),
	"cos": MathFunction(
		math.cos,
		r"\cos",
		1,
		lambda u: Mul.of(Const(-1.0), Func("sin", (u,))),
		vectorised=np.cos,
	),
	"tan": MathFunction(
		math.tan,
		r"\tan",
		1,
		lambda u: Pow(Func("cos", (u,)), Const(-2.0)),
		vectorised=np.tan,
	),
	"asin": MathFunction(
		math.asin,
		r"\arcsin",
		1,
		lambda u: Pow(
			Pow(Add.of(Const(1.0), Mul.of(Const(-1.0), Pow(u, Const(2.0)))), Const(0.5)),
			Const(-1.0),
		),
		vectorised=np.arcsin,
	),
	"acos": MathFunction(
		math.acos,
		r"\arccos",
		1,
		lambda u: Mul.of(
			Const(-1.0),
			Pow(
				Pow(
					Add.of(Const(1.0), Mul.of(Const(-1.0), Pow(u, Const(2.0)))),
					Const(0.5),
				),
				Const(-1.0),
			),
		),
		vectorised=np.arccos,
	),
	"atan": MathFunction(
		math.atan,
		r"\arctan",
		1,
		lambda u: Pow(Add.of(Const(1.0), Pow(u, Const(2.0))), Const(-1.0)),
		vectorised=np.arctan,
	),
	"sinh": MathFunction(
		math.sinh, r"\sinh", 1, lambda u: Func("cosh", (u,)), vectorised=np.sinh
	),
	"cosh": MathFunction(
		math.cosh, r"\cosh", 1, lambda u: Func("sinh", (u,)), vectorised=np.cosh
	),
	"tanh": MathFunction(
		math.tanh,
		r"\tanh",
		1,
		lambda u: Add.of(
			Const(1.0), Mul.of(Const(-1.0), Pow(Func("tanh", (u,)), Const(2.0)))
		),
		vectorised=np.tanh,
	),
	"erf": MathFunction(
		math.erf,
		r"\operatorname{erf}",
		1,
		lambda u: Mul.of(
			Const(2.0 / math.sqrt(math.pi)),
			Func("exp", (Mul.of(Const(-1.0), Pow(u, Const(2.0))),)),
		),
		vectorised=scipy_special.erf,
	),
	# Non-differentiable on purpose. `abs` has a kink at zero and `min`/`max`
	# have a discontinuity in the derivative where the arguments cross; a
	# formula that hides that is worse than a refusal.
	"abs": MathFunction(_f_abs, r"\left|", 1, vectorised=np.abs),
	"min": MathFunction(_f_min, r"\min", None, vectorised=_v_min),
	"max": MathFunction(_f_max, r"\max", None, vectorised=_v_max),
	"floor": MathFunction(_f_floor, r"\lfloor", 1, vectorised=np.floor),
	"ceil": MathFunction(
		lambda x: float(math.ceil(x)), r"\lceil", 1, vectorised=np.ceil
	),
}

#: Names that render as a Greek letter. A parameter called ``beta`` is the
#: Greek letter in every paper that defines it, and rendering it as
#: ``\mathrm{beta}`` makes a reader translate.
_GREEK: dict[str, str] = {
	"alpha": r"\alpha",
	"beta": r"\beta",
	"gamma": r"\gamma",
	"delta": r"\delta",
	"epsilon": r"\epsilon",
	"zeta": r"\zeta",
	"eta": r"\eta",
	"theta": r"\theta",
	"kappa": r"\kappa",
	"lambda": r"\lambda",
	"mu": r"\mu",
	"nu": r"\nu",
	"xi": r"\xi",
	"pi": r"\pi",
	"rho": r"\rho",
	"sigma": r"\sigma",
	"tau": r"\tau",
	"phi": r"\phi",
	"chi": r"\chi",
	"psi": r"\psi",
	"omega": r"\omega",
}

#: Precedence, for parenthesisation. Higher binds tighter.
_PRECEDENCE = {"add": 1, "mul": 2, "pow": 3, "func": 4, "atom": 5, "sum": 1}


# ---------------------------------------------------------------------------
# The expression tree
# ---------------------------------------------------------------------------


class Expr(ABC):
	"""A formula. Immutable, hashable, and comparable by structure.

	Equality is structural -- ``parse("a + a") != parse("2 * a")`` -- because
	the two are different formulas that :func:`simplify` relates. A value-based
	equality would make the test of a simplification rule unable to state which
	side it expected.
	"""

	@property
	@abstractmethod
	def symbols(self) -> frozenset[str]:
		"""Every parameter this formula names."""

	@abstractmethod
	def _eval(self, values: Mapping[str, Any]) -> Any:
		"""Evaluate, without the float coercion, so arrays pass through."""

	@abstractmethod
	def _latex(self, parent: int) -> str:
		"""Render to LaTeX, parenthesising below ``parent``."""

	@abstractmethod
	def _unicode(self, parent: int) -> str: ...

	@abstractmethod
	def _source(self, parent: int) -> str:
		"""Render back to text :func:`parse` accepts."""

	@abstractmethod
	def _mathml(self) -> str: ...

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["atom"]

	# -- creation, by operator ------------------------------------------

	def __add__(self, other: object) -> Expr:
		return Add.of(self, _as_expr(other))

	def __radd__(self, other: object) -> Expr:
		return Add.of(_as_expr(other), self)

	def __sub__(self, other: object) -> Expr:
		return Add.of(self, Mul.of(Const(-1.0), _as_expr(other)))

	def __rsub__(self, other: object) -> Expr:
		return Add.of(_as_expr(other), Mul.of(Const(-1.0), self))

	def __mul__(self, other: object) -> Expr:
		return Mul.of(self, _as_expr(other))

	def __rmul__(self, other: object) -> Expr:
		return Mul.of(_as_expr(other), self)

	def __truediv__(self, other: object) -> Expr:
		return Mul.of(self, Pow(_as_expr(other), Const(-1.0)))

	def __rtruediv__(self, other: object) -> Expr:
		return Mul.of(_as_expr(other), Pow(self, Const(-1.0)))

	def __pow__(self, other: object) -> Expr:
		return Pow(self, _as_expr(other))

	def __rpow__(self, other: object) -> Expr:
		return Pow(_as_expr(other), self)

	def __neg__(self) -> Expr:
		return Mul.of(Const(-1.0), self)

	def __pos__(self) -> Expr:
		return self

	# -- the three lives -------------------------------------------------

	def eval(self, values: Mapping[str, Any]) -> float:
		"""The value at ``values``.

		``values`` may hold sequences as well as scalars: ``sum(x[i] for i in
		range(0, 3))`` is the shape the equation library needs over a fleet, and
		it *reduces* an array to a scalar, so the result of this call is a float
		even when its inputs are not. The signature says ``Any`` for that
		reason -- typing the inputs as floats described a narrower function than
		the one that runs, and the array case is a supported one, not an
		accident.
		"""
		return float(self._eval(values))

	def eval_array(self, values: Mapping[str, Any]) -> np.ndarray:
		"""The value at ``values``, where a symbol may hold an array.

		Broadcasting is NumPy's, so ``a * b`` with a scalar ``a`` and a
		time-series ``b`` yields a time series -- which is the shape a
		parameters-times-profile equation needs and the reason evaluation is
		not simply a float.

		Sequences are coerced on the way *in*, not on the way out. A caller
		holding a list of hourly values -- which is what a CSV column is --
		would otherwise reach ``2.0 * [1.0, 2.0]`` and be told a float cannot
		multiply a sequence, from inside the evaluator, about a value the
		caller was told to pass. Coercing here makes the signature's ``Any``
		mean what a reader takes it to mean.
		"""
		coerced = {
			name: np.asarray(value, dtype=float)
			if isinstance(value, (list, tuple, range))
			else value
			for name, value in values.items()
		}
		return np.asarray(self._eval(coerced), dtype=float)

	def subs(self, mapping: Mapping[str, Expr | float]) -> Expr:
		"""Replace named parameters by expressions or numbers."""
		return _subs(self, {k: _as_expr(v) for k, v in mapping.items()})

	def diff(self, symbol: str) -> Expr:
		"""The symbolic derivative with respect to ``symbol``."""
		return simplify(diff(self, symbol))

	def simplify(self) -> Expr:
		return simplify(self)

	def gradient(self, values: Mapping[str, float]) -> dict[str, float]:
		"""Partial derivatives at ``values``, symbolically then evaluated.

		Symbolic rather than finite-difference: the feedback solver uses these
		to accelerate a fixed point, and a difference quotient carries a
		truncation error that shows up as a limit cycle in a loop that should
		have converged.
		"""
		out: dict[str, float] = {}
		for name in sorted(self.symbols):
			out[name] = float(diff(self, name)._eval(values))
		return out

	def solve(self, symbol: str, *, bracket: tuple[float, float], residual: float = 0.0) -> float:
		"""Solve ``self == residual`` for ``symbol`` inside ``bracket``."""
		return solve_for(self, symbol, {}, bracket=bracket, residual=residual)

	# -- rendering -------------------------------------------------------

	def latex(self) -> str:
		"""LaTeX for a report, without the surrounding ``$``."""
		return self._latex(0)

	def unicode(self) -> str:
		"""A terminal rendering, using Unicode operators and superscripts."""
		return self._unicode(0)

	def source(self) -> str:
		"""Text that :func:`parse` accepts, so rendering round-trips."""
		return self._source(0)

	def mathml(self) -> str:
		"""Presentation MathML for a browser."""
		return f"<math xmlns='http://www.w3.org/1998/Math/MathML'>{self._mathml()}</math>"

	def __str__(self) -> str:
		return self.unicode()

	def __repr__(self) -> str:
		return f"Expr({self.source()!r})"


# -- leaf and operator nodes -------------------------------------------------


@dataclass(frozen=True)
class Const(Expr):
	"""A number."""

	value: float

	@property
	def symbols(self) -> frozenset[str]:
		return frozenset()

	def _eval(self, values: Mapping[str, Any]) -> Any:
		return self.value

	def _format(self) -> str:
		if self.value == int(self.value) and abs(self.value) < 1e16:
			return str(int(self.value))
		return f"{self.value:g}"

	def _latex(self, parent: int) -> str:
		return self._format()

	def _unicode(self, parent: int) -> str:
		return self._format()

	def _source(self, parent: int) -> str:
		# A negative literal has to be parenthesised as a base, or
		# `(-2) ** x` re-parses as `-(2 ** x)`.
		if self.value < 0:
			return f"({self._format()})"
		return self._format()

	def _mathml(self) -> str:
		return f"<mn>{self._format()}</mn>"


@dataclass(frozen=True)
class Symbol(Expr):
	"""A named parameter."""

	name: str

	def __post_init__(self) -> None:
		# Enforced here and not only in :func:`sym`: the factory is a
		# convenience, not a gate, and a Symbol built directly -- by a caller,
		# or by a parser path that let a name through -- would otherwise shadow
		# a DSL function. A parameter named ``exp`` is indistinguishable from
		# the exponential in every rendering, so it is refused at construction
		# rather than at the first wrong answer.
		if not self.name.isidentifier():
			raise DslError(f"{self.name!r} is not a valid parameter name")
		if self.name in _RESERVED:
			raise DslError(
				f"{self.name!r} is reserved: it names a DSL function, and a "
				f"parameter that shadows one cannot be told from it in the "
				f"arithmetic"
			)

	@property
	def symbols(self) -> frozenset[str]:
		return frozenset({self.name})

	def _eval(self, values: Mapping[str, Any]) -> Any:
		if self.name not in values:
			raise DslError(
				f"{self.name!r} has no value; the parameter set does not carry it"
			)
		return values[self.name]

	def _latex(self, parent: int) -> str:
		if self.name in _GREEK:
			return _GREEK[self.name]
		if "_" in self.name:
			head, _, tail = self.name.partition("_")
			return rf"\mathrm{{{head}}}_{{{tail.replace('_', r'\_')}}}"
		return rf"\mathrm{{{self.name}}}"

	def _unicode(self, parent: int) -> str:
		return self.name

	def _source(self, parent: int) -> str:
		return self.name

	def _mathml(self) -> str:
		return f"<mi>{self.name}</mi>"


@dataclass(frozen=True)
class Add(Expr):
	"""A sum of terms, flattened. ``a + b - c`` is ``Add(a, b, -c)``."""

	terms: tuple[Expr, ...]

	@staticmethod
	def of(*terms: Expr) -> Expr:
		flat: list[Expr] = []
		for term in terms:
			if isinstance(term, Add):
				flat.extend(term.terms)
			else:
				flat.append(term)
		if not flat:
			return Const(0.0)
		if len(flat) == 1:
			return flat[0]
		return Add(tuple(flat))

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["add"]

	@property
	def symbols(self) -> frozenset[str]:
		out: frozenset[str] = frozenset()
		for term in self.terms:
			out |= term.symbols
		return out

	def _eval(self, values: Mapping[str, Any]) -> Any:
		total = self.terms[0]._eval(values)
		for term in self.terms[1:]:
			total = total + term._eval(values)
		return total

	def _latex(self, parent: int) -> str:
		parts: list[str] = []
		for index, term in enumerate(self.terms):
			negated = _negation(term)
			if negated is not None:
				body = negated._latex(self.precedence)
				parts.append(f"- {body}" if index else f"-{body}")
			else:
				body = term._latex(self.precedence)
				parts.append(f"+ {body}" if index else body)
		text = " ".join(parts)
		return f"\\left({text}\\right)" if parent > self.precedence else text

	def _unicode(self, parent: int) -> str:
		parts: list[str] = []
		for index, term in enumerate(self.terms):
			negated = _negation(term)
			if negated is not None:
				parts.append(f"- {negated._unicode(self.precedence)}" if index else f"-{negated._unicode(self.precedence)}")
			else:
				parts.append(f"+ {term._unicode(self.precedence)}" if index else term._unicode(self.precedence))
		text = " ".join(parts)
		return f"({text})" if parent > self.precedence else text

	def _source(self, parent: int) -> str:
		text = " + ".join(term._source(self.precedence) for term in self.terms)
		return f"({text})" if parent > self.precedence else text

	def _mathml(self) -> str:
		body = "".join(term._mathml() for term in self.terms)
		return f"<mrow>{body}</mrow>"


@dataclass(frozen=True)
class Mul(Expr):
	"""A product, flattened, with numeric coefficients collected."""

	factors: tuple[Expr, ...]

	@staticmethod
	def of(*factors: Expr) -> Expr:
		flat: list[Expr] = []
		coefficient = 1.0
		for factor in factors:
			items = factor.factors if isinstance(factor, Mul) else (factor,)
			for item in items:
				if isinstance(item, Const):
					coefficient *= item.value
				else:
					flat.append(item)
		if coefficient == 0.0:
			return Const(0.0)
		if not flat:
			return Const(coefficient)
		if coefficient != 1.0:
			flat.insert(0, Const(coefficient))
		if len(flat) == 1:
			return flat[0]
		return Mul(tuple(flat))

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["mul"]

	@property
	def symbols(self) -> frozenset[str]:
		out: frozenset[str] = frozenset()
		for factor in self.factors:
			out |= factor.symbols
		return out

	def _eval(self, values: Mapping[str, Any]) -> Any:
		total = self.factors[0]._eval(values)
		for factor in self.factors[1:]:
			total = total * factor._eval(values)
		return total

	def _numerator_denominator(self) -> tuple[list[Expr], list[Expr]]:
		"""Split into what multiplies and what divides.

		``a / b`` is stored as ``a * b**-1``, so rendering it as a fraction
		means recognising the negative powers. Doing it here rather than at
		render time keeps the three renderers agreeing about what is a
		denominator.
		"""
		numerator: list[Expr] = []
		denominator: list[Expr] = []
		for factor in self.factors:
			if isinstance(factor, Pow):
				exponent = _negation(factor.exponent)
				if exponent is not None:
					denominator.append(simplify(Pow(factor.base, exponent)))
					continue
			numerator.append(factor)
		return numerator, denominator

	def _latex(self, parent: int) -> str:
		negated = _negation(self)
		if negated is not None:
			text = f"-{negated._latex(self.precedence)}"
			return f"\\left({text}\\right)" if parent > self.precedence else text
		numerator, denominator = self._numerator_denominator()
		if denominator:
			top = Mul.of(*numerator) if numerator else Const(1.0)
			bottom = Mul.of(*denominator)
			text = f"\\frac{{{top._latex(0)}}}{{{bottom._latex(0)}}}"
			return f"\\left({text}\\right)" if parent > self.precedence else text
		text = " ".join(factor._latex(self.precedence) for factor in self.factors)
		return f"\\left({text}\\right)" if parent > self.precedence else text

	def _unicode(self, parent: int) -> str:
		negated = _negation(self)
		if negated is not None:
			text = f"-{negated._unicode(self.precedence)}"
			return f"({text})" if parent > self.precedence else text
		numerator, denominator = self._numerator_denominator()
		if denominator:
			top = Mul.of(*numerator) if numerator else Const(1.0)
			bottom = Mul.of(*denominator)
			text = f"{top._unicode(self.precedence + 1)}/{bottom._unicode(self.precedence + 1)}"
		else:
			text = "·".join(factor._unicode(self.precedence) for factor in self.factors)
		return f"({text})" if parent > self.precedence else text

	def _source(self, parent: int) -> str:
		text = " * ".join(factor._source(self.precedence) for factor in self.factors)
		return f"({text})" if parent > self.precedence else text

	def _mathml(self) -> str:
		numerator, denominator = self._numerator_denominator()
		if denominator:
			top = Mul.of(*numerator) if numerator else Const(1.0)
			bottom = Mul.of(*denominator)
			return f"<mfrac>{top._mathml()}{bottom._mathml()}</mfrac>"
		body = "".join(factor._mathml() for factor in self.factors)
		return f"<mrow>{body}</mrow>"


@dataclass(frozen=True)
class Pow(Expr):
	"""A power. ``a ** b``."""

	base: Expr
	exponent: Expr

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["pow"]

	@property
	def symbols(self) -> frozenset[str]:
		return self.base.symbols | self.exponent.symbols

	def _eval(self, values: Mapping[str, Any]) -> Any:
		base = self.base._eval(values)
		exponent = self.exponent._eval(values)
		if (
			not isinstance(base, np.ndarray)
			and not isinstance(exponent, np.ndarray)
			and base < 0
			and not float(exponent).is_integer()
		):
			raise DslError(
				f"({base}) ** {exponent} is not real; a fractional power of a "
				f"negative base has no real value"
			)
		return base**exponent

	def _latex(self, parent: int) -> str:
		# The base is rendered one precedence tighter than a power, so a nested
		# power is parenthesised: `(x ** y) ** -1` is not `x ** (y ** -1)`, and
		# a renderer that cannot tell them apart produces LaTeX a reader
		# misreads.
		text = f"{{{self.base._latex(self.precedence + 1)}}}^{{{self.exponent._latex(0)}}}"
		return f"\\left({text}\\right)" if parent > self.precedence else text

	def _unicode(self, parent: int) -> str:
		if isinstance(self.exponent, Const):
			super = _superscript(self.exponent.value)
			if super is not None:
				text = f"{self.base._unicode(self.precedence + 1)}{super}"
				return f"({text})" if parent > self.precedence else text
		text = f"{self.base._unicode(self.precedence + 1)}^{self.exponent._unicode(0)}"
		return f"({text})" if parent > self.precedence else text

	def _source(self, parent: int) -> str:
		text = (
			f"{self.base._source(self.precedence + 1)} ** "
			f"{self.exponent._source(0)}"
		)
		return f"({text})" if parent > self.precedence else text

	def _mathml(self) -> str:
		return f"<msup>{self.base._mathml()}{self.exponent._mathml()}</msup>"


@dataclass(frozen=True)
class Subscript(Expr):
	"""An element of an array-valued parameter: ``capacity[3]``.

	Array parameters are how a sum over a fleet is written. The equation
	library's energy balance sums generation across units, and without a
	subscript the only sum expressible is over the index's own value -- which
	cannot reach a parameter at all.
	"""

	base: Symbol
	index: Expr

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["atom"]

	@property
	def symbols(self) -> frozenset[str]:
		return self.base.symbols | self.index.symbols

	def _eval(self, values: Mapping[str, Any]) -> Any:
		container = self.base._eval(values)
		position = int(self.index._eval(values))
		try:
			return container[position]
		except (IndexError, TypeError) as exc:
			raise DslError(
				f"{self.base.name}[{position}] is out of range for a parameter "
				f"holding {type(container).__name__}"
			) from exc

	def _latex(self, parent: int) -> str:
		# A base whose own name carries an underscore already renders with a
		# subscript; wrapping it in braces stops the index's subscript colliding
		# with it -- `emission_factor[i]` is not `emission_{factor_i}`.
		base = self.base._latex(0)
		if "_{" in base:
			base = f"{{{base}}}"
		return f"{base}_{{{self.index._latex(0)}}}"

	def _unicode(self, parent: int) -> str:
		return f"{self.base.name}[{self.index._unicode(0)}]"

	def _source(self, parent: int) -> str:
		return f"{self.base.name}[{self.index._source(0)}]"

	def _mathml(self) -> str:
		return f"<msub>{self.base._mathml()}{self.index._mathml()}</msub>"


@dataclass(frozen=True)
class Func(Expr):
	"""A call to one of :data:`_FUNCTIONS`."""

	name: str
	args: tuple[Expr, ...]

	def __post_init__(self) -> None:
		spec = _FUNCTIONS.get(self.name)
		if spec is None:
			raise DslError(
				f"{self.name!r} is not a DSL function; allowed: "
				f"{sorted(_FUNCTIONS)}"
			)
		if spec.arity is not None and len(self.args) != spec.arity:
			raise DslError(
				f"{self.name} takes {spec.arity} argument(s), got {len(self.args)}"
			)
		if not self.args:
			raise DslError(f"{self.name} needs at least one argument")

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["func"]

	@property
	def symbols(self) -> frozenset[str]:
		out: frozenset[str] = frozenset()
		for arg in self.args:
			out |= arg.symbols
		return out

	def _eval(self, values: Mapping[str, Any]) -> Any:
		spec = _FUNCTIONS[self.name]
		evaluated = [arg._eval(values) for arg in self.args]
		if any(isinstance(v, np.ndarray) for v in evaluated):
			if spec.vectorised is None:
				raise DslError(
					f"{self.name} has no array-valued form; the scalar "
					f"implementation is a math callable and would raise on an "
					f"array rather than broadcasting"
				)
			return spec.vectorised(*evaluated)
		return spec.impl(*evaluated)

	def _latex(self, parent: int) -> str:
		if self.name == "exp":
			return f"e^{{{self.args[0]._latex(0)}}}"
		if self.name == "sqrt":
			return f"\\sqrt{{{self.args[0]._latex(0)}}}"
		if self.name == "abs":
			return f"\\left|{self.args[0]._latex(0)}\\right|"
		rendered = ", ".join(arg._latex(0) for arg in self.args)
		return f"{_FUNCTIONS[self.name].latex}\\left({rendered}\\right)"

	def _unicode(self, parent: int) -> str:
		if self.name == "sqrt":
			return f"√({self.args[0]._unicode(0)})"
		if self.name == "abs":
			return f"|{self.args[0]._unicode(0)}|"
		rendered = ", ".join(arg._unicode(0) for arg in self.args)
		return f"{self.name}({rendered})"

	def _source(self, parent: int) -> str:
		rendered = ", ".join(arg._source(0) for arg in self.args)
		return f"{self.name}({rendered})"

	def _mathml(self) -> str:
		body = "".join(arg._mathml() for arg in self.args)
		if self.name == "sqrt":
			return f"<msqrt>{body}</msqrt>"
		if self.name == "abs":
			return f"<mrow><mo>|</mo>{body}<mo>|</mo></mrow>"
		if self.name == "exp":
			return f"<msup><mi>e</mi>{self.args[0]._mathml()}</msup>"
		return f"<mrow><mi>{self.name}</mi><mo>(</mo>{body}<mo>)</mo></mrow>"


@dataclass(frozen=True)
class Sum(Expr):
	"""A summation: ``sum(body for index in range(lower, upper + 1))``.

	An explicit index with integer bounds, not a symbolic set. Every sum in the
	equation library is over a horizon, a set of technologies, or a set of
	regions, and all three are finite and known when the equation runs. A
	symbolic index would render more generally and evaluate nowhere.
	"""

	index: str
	lower: int
	upper: int
	body: Expr

	def __post_init__(self) -> None:
		if self.lower > self.upper:
			raise DslError(
				f"sum over {self.index} from {self.lower} to {self.upper} is empty; "
				f"an empty sum is zero and would hide a bounds error"
			)
		if self.index in self.body.symbols and self.index in _RESERVED:
			raise DslError(f"{self.index!r} is a reserved name and cannot index a sum")

	@property
	def precedence(self) -> int:
		return _PRECEDENCE["sum"]

	@property
	def symbols(self) -> frozenset[str]:
		return self.body.symbols - {self.index}

	def _eval(self, values: Mapping[str, Any]) -> Any:
		scoped = dict(values)
		total: Any = 0.0
		for position in range(self.lower, self.upper + 1):
			scoped[self.index] = float(position)
			total = total + self.body._eval(scoped)
		return total

	def _latex(self, parent: int) -> str:
		index = _GREEK.get(self.index, rf"\mathrm{{{self.index}}}")
		return (
			f"\\sum_{{{index}={self.lower}}}^{{{self.upper}}} "
			f"{self.body._latex(self.precedence)}"
		)

	def _unicode(self, parent: int) -> str:
		return (
			f"Σ[{self.index}={self.lower}..{self.upper}] "
			f"{self.body._unicode(self.precedence)}"
		)

	def _source(self, parent: int) -> str:
		return (
			f"sum({self.body._source(0)} for {self.index} in "
			f"range({self.lower}, {self.upper + 1}))"
		)

	def _mathml(self) -> str:
		return (
			"<mrow><munderover><mo>∑</mo>"
			f"<mrow><mi>{self.index}</mi><mo>=</mo><mn>{self.lower}</mn></mrow>"
			f"<mn>{self.upper}</mn></munderover>{self.body._mathml()}</mrow>"
		)


#: Names the DSL reserves: the function set and the summation keyword.
_RESERVED = frozenset(_FUNCTIONS) | {"sum", "for", "in", "range", "and", "or", "not"}


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def _as_expr(value: object) -> Expr:
	if isinstance(value, Expr):
		return value
	if isinstance(value, bool):
		raise DslError("a boolean is not a number in this DSL")
	if isinstance(value, (int, float)):
		return Const(float(value))
	raise DslError(
		f"{value!r} is not an expression or a number; a formula is built from "
		f"Expr objects and numeric literals"
	)


def sym(name: str) -> Symbol:
	"""A named parameter, for building a formula in code."""
	# The validity and reserved-name rules live in ``Symbol.__post_init__``, so
	# this is a spelling of the constructor and not a second gate that can
	# drift from it.
	return Symbol(name)


def const(value: float) -> Const:
	return Const(float(value))


def symbols_of(expression: Expr) -> frozenset[str]:
	"""Every parameter ``expression`` names, in sorted order as a frozenset."""
	return expression.symbols


# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------


def _subs(expression: Expr, mapping: Mapping[str, Expr]) -> Expr:
	if isinstance(expression, Symbol):
		return mapping.get(expression.name, expression)
	if isinstance(expression, Const):
		return expression
	if isinstance(expression, Add):
		return Add.of(*(_subs(term, mapping) for term in expression.terms))
	if isinstance(expression, Mul):
		return Mul.of(*(_subs(factor, mapping) for factor in expression.factors))
	if isinstance(expression, Pow):
		return Pow(_subs(expression.base, mapping), _subs(expression.exponent, mapping))
	if isinstance(expression, Subscript):
		return Subscript(
			_subs(expression.base, mapping),  # type: ignore[arg-type]
			_subs(expression.index, mapping),
		)
	if isinstance(expression, Func):
		return Func(expression.name, tuple(_subs(arg, mapping) for arg in expression.args))
	if isinstance(expression, Sum):
		# The index is bound: substituting it would capture. Removing it from
		# the mapping is the difference between `sum(i for i in 0..3)` and
		# `sum(7 for i in 0..3)`, and only one of those is what was written.
		inner = {k: v for k, v in mapping.items() if k != expression.index}
		return Sum(
			expression.index,
			expression.lower,
			expression.upper,
			_subs(expression.body, inner),
		)
	raise DslError(f"cannot substitute into {type(expression).__name__}")


# ---------------------------------------------------------------------------
# Simplification
# ---------------------------------------------------------------------------


def simplify(expression: Expr) -> Expr:
	"""A cheaper, equivalent formula.

	Deliberately conservative. It folds constants, flattens, drops identity
	elements, combines like terms, and merges powers of the same base. It does
	not expand products, factor, or rationalise -- each of which can turn a
	readable formula into an unreadable one, and the library is read by people
	who own the physics. A simplifier that renames the variables in a formula a
	reviewer approved is a simplifier that gets turned off.
	"""
	if isinstance(expression, Const):
		return expression
	if isinstance(expression, Symbol):
		return expression
	if isinstance(expression, Add):
		terms = [simplify(term) for term in expression.terms]
		folded = Add.of(*terms)
		if isinstance(folded, Add):
			return _collect_like(folded)
		return folded
	if isinstance(expression, Mul):
		factors = [simplify(factor) for factor in expression.factors]
		folded = Mul.of(*factors)
		if isinstance(folded, Mul):
			return _merge_powers(folded)
		return folded
	if isinstance(expression, Pow):
		base = simplify(expression.base)
		exponent = simplify(expression.exponent)
		if isinstance(exponent, Const):
			if exponent.value == 0.0:
				return Const(1.0)
			if exponent.value == 1.0:
				return base
		if isinstance(base, Const) and isinstance(exponent, Const):
			return Const(float(base.value**exponent.value))
		return Pow(base, exponent)
	if isinstance(expression, Subscript):
		return Subscript(expression.base, simplify(expression.index))
	if isinstance(expression, Func):
		args = tuple(simplify(arg) for arg in expression.args)
		if all(isinstance(arg, Const) for arg in args):
			values = [arg.value for arg in args if isinstance(arg, Const)]
			try:
				return Const(float(_FUNCTIONS[expression.name].impl(*values)))
			except (ValueError, OverflowError):
				# A constant that has no value -- `ln(0)` -- stays symbolic.
				# Folding it to an error would make `simplify` raise on a
				# formula that evaluates fine over the range it is used on.
				pass
		return Func(expression.name, args)
	if isinstance(expression, Sum):
		body = simplify(expression.body)
		if isinstance(body, Const):
			return Const(body.value * (expression.upper - expression.lower + 1))
		return Sum(expression.index, expression.lower, expression.upper, body)
	return expression


def _collect_like(expression: Add) -> Expr:
	"""Combine terms that differ only by a numeric coefficient."""
	coefficients: dict[Expr, float] = {}
	constant = 0.0
	order: list[Expr] = []
	for term in expression.terms:
		if isinstance(term, Const):
			constant += term.value
			continue
		if isinstance(term, Mul) and isinstance(term.factors[0], Const):
			key = Mul.of(*term.factors[1:])
			coefficient = term.factors[0].value
		else:
			key = term
			coefficient = 1.0
		if key not in coefficients:
			coefficients[key] = 0.0
			order.append(key)
		coefficients[key] += coefficient
	terms: list[Expr] = []
	for key in order:
		coefficient = coefficients[key]
		if coefficient == 0.0:
			continue
		terms.append(Mul.of(Const(coefficient), key))
	if constant != 0.0 or not terms:
		terms.append(Const(constant))
	return Add.of(*terms)


def _merge_powers(expression: Mul) -> Expr:
	"""Combine ``a**m * a**n`` into ``a**(m+n)``."""
	powers: dict[Expr, list[Expr]] = {}
	order: list[Expr] = []
	for factor in expression.factors:
		if isinstance(factor, Pow):
			base, exponent = factor.base, factor.exponent
		else:
			base, exponent = factor, Const(1.0)
		if base not in powers:
			powers[base] = []
			order.append(base)
		powers[base].append(exponent)
	factors: list[Expr] = []
	for base in order:
		exponents = powers[base]
		total = Add.of(*exponents)
		if isinstance(total, Const) and total.value == 0.0:
			continue
		if isinstance(total, Const) and total.value == 1.0:
			factors.append(base)
			continue
		factors.append(Pow(base, simplify(total)))
	return Mul.of(*factors)


# ---------------------------------------------------------------------------
# Differentiation
# ---------------------------------------------------------------------------


def diff(expression: Expr, symbol: str) -> Expr:
	"""The derivative of ``expression`` with respect to ``symbol``.

	Refuses rather than approximates. A function with no derivative rule raises
	:class:`DslError` naming itself, because the failure this prevents is a
	``min`` that differentiates to a step function, renders as a formula, and
	is used to accelerate a solver that then oscillates.
	"""
	if isinstance(expression, Const):
		return Const(0.0)
	if isinstance(expression, Symbol):
		return Const(1.0 if expression.name == symbol else 0.0)
	if isinstance(expression, Add):
		return Add.of(*(diff(term, symbol) for term in expression.terms))
	if isinstance(expression, Mul):
		# The product rule, one term per factor.
		terms: list[Expr] = []
		for index, factor in enumerate(expression.factors):
			derivative = diff(factor, symbol)
			if isinstance(derivative, Const) and derivative.value == 0.0:
				continue
			product: list[Expr] = []
			for position, other in enumerate(expression.factors):
				product.append(derivative if position == index else other)
			terms.append(Mul.of(*product))
		return Add.of(*terms) if terms else Const(0.0)
	if isinstance(expression, Pow):
		base, exponent = expression.base, expression.exponent
		if symbol not in exponent.symbols:
			# d/dx u**c = c * u**(c-1) * u'
			return Mul.of(
				exponent,
				Pow(base, Add.of(exponent, Const(-1.0))),
				diff(base, symbol),
			)
		if symbol not in base.symbols:
			# d/dx c**u = c**u * ln(c) * u'
			return Mul.of(
				expression,
				Func("ln", (base,)),
				diff(exponent, symbol),
			)
		# Both sides move: u**v = exp(v ln u), differentiated as such.
		return Mul.of(
			expression,
			Add.of(
				Mul.of(diff(exponent, symbol), Func("ln", (base,))),
				Mul.of(exponent, diff(base, symbol), Pow(base, Const(-1.0))),
			),
		)
	if isinstance(expression, Subscript):
		# d/dx h[i] is zero unless the index itself moves, and an index that
		# names the differentiation variable is refused by Sum's rule below.
		if symbol in expression.index.symbols:
			raise DslError(
				f"{symbol!r} is the index of {expression.source()!r}; "
				f"differentiating with respect to an index is not the derivative "
				f"of the element"
			)
		return Const(0.0)
	if isinstance(expression, Func):
		spec = _FUNCTIONS[expression.name]
		if spec.derivative is None:
			raise DslError(
				f"{expression.name!r} has no derivative rule; it is "
				f"non-differentiable where its arguments cross, and a formula "
				f"that hid that would be used in a solver that then oscillates"
			)
		inner = expression.args[0]
		outer = spec.derivative(inner)
		return Mul.of(outer, diff(inner, symbol))
	if isinstance(expression, Sum):
		if expression.index == symbol:
			raise DslError(
				f"{symbol!r} is the summation index of {expression.source()!r}; "
				f"differentiating with respect to a bound variable is not the "
				f"derivative of the sum"
			)
		return Sum(
			expression.index,
			expression.lower,
			expression.upper,
			diff(expression.body, symbol),
		)
	raise DslError(f"cannot differentiate {type(expression).__name__}")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(expression: Expr, values: Mapping[str, float | str]) -> float:
	"""The value of ``expression`` at ``values``.

	``values`` may carry a *level name* for a categorical parameter, which this
	expression does not read: an equation is arithmetic and a categorical has no
	arithmetic, so a symbol bound to a name raises the same ``TypeError`` a
	missing operator would. The annotation admits it because the parameter set
	the graph passes is one mapping for the whole graph, and a categorical's
	value lives in it beside every number.
	"""
	missing = expression.symbols - values.keys()
	if missing:
		raise DslError(
			f"{expression.source()!r} needs {sorted(missing)}, which the "
			f"parameter set does not carry"
		)
	return float(expression._eval(values))


def evaluate_array(expression: Expr, values: Mapping[str, Any]) -> np.ndarray:
	"""The value of ``expression`` where a symbol may hold an array."""
	return expression.eval_array(values)


# ---------------------------------------------------------------------------
# Solving
# ---------------------------------------------------------------------------


def solve_for(
	expression: Expr,
	symbol: str,
	values: Mapping[str, float | str],
	*,
	bracket: tuple[float, float],
	residual: float = 0.0,
) -> float:
	"""Solve ``expression == residual`` for ``symbol`` within ``bracket``.

	The caller supplies the bracket because only the caller knows the physical
	range: a capacity factor lives in ``[0, 1]`` and a carbon price does not,
	and a solver handed ``[-1e9, 1e9]`` finds whichever root it meets first.
	That is how a learning curve yields a negative cost.

	The solve is numeric. A closed form would be nicer and is available in a
	symbolic-algebra package, but it fails on the equations that actually need
	solving -- a learning curve against a cost, a capture price against a build
	-- in ways that are hard to tell from "no solution". A bracket that fails
	says which bracket failed.
	"""
	if symbol not in expression.symbols:
		raise DslError(
			f"{symbol!r} does not appear in {expression.source()!r}, so the "
			f"equation does not determine it"
		)
	low, high = bracket
	if low >= high:
		raise DslError(f"bracket ({low}, {high}) is not an interval")

	def at(point: float) -> float:
		scoped = dict(values)
		scoped[symbol] = point
		return evaluate(expression, scoped) - residual

	f_low, f_high = at(low), at(high)
	if f_low == 0.0:
		return low
	if f_high == 0.0:
		return high
	if f_low * f_high > 0.0:
		raise DslError(
			f"{expression.source()!r} = {residual} has no root in ({low}, {high}): "
			f"the residual is {f_low:.6g} at {low} and {f_high:.6g} at {high}, so "
			f"it does not change sign there"
		)
	return float(brentq(at, low, high))  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------
# Linearity, as a fact about a variable rather than a label on an equation
# ---------------------------------------------------------------------------

#: How ``symbol`` enters ``expression``. Ordered by increasing severity, so the
#: worst occurrence in a sum or a product is the one that decides it.
_ABSENT = 0
"""``symbol`` does not appear in this subexpression."""

_AFFINE = 1
"""``symbol`` appears to the first power, in no product with itself."""

_NONLINEAR = 2
"""``symbol`` appears as a power, inside a function, or multiplied by itself."""

LINEAR = "linear"
NONLINEAR = "nonlinear"
LINEAR_IN_ITS_OWN_UNKNOWN = "linear_in_its_own_unknown"
NONLINEAR_IN_ITS_OWN_UNKNOWN = "nonlinear_in_its_own_unknown"


def _severity(expression: Expr, symbol: str) -> int:
	"""The worst way ``symbol`` enters ``expression``.

	Structural, not symbolic: it reads the tree rather than differentiating,
	so ``a * a / a`` counts as nonlinear even though it equals ``a``. A
	simplify-then-classify would be exact and would also change the answer
	under a rewrite rule, which is the property that made the declared
	``linearity`` column unreproducible in the first place -- four defensible
	readings gave four disjoint disagreement sets against it. A structural
	answer is one a reader can check against the formula they can see.
	"""
	if isinstance(expression, Const):
		return _ABSENT
	if isinstance(expression, (Symbol, Subscript)):
		# A subscript's index may mention the symbol (``a[a]``), but the
		# index is an element selector rather than a value the formula
		# computes with; every subscript in this library indexes a sum.
		return _AFFINE if getattr(expression, "name", None) == symbol else _ABSENT
	if isinstance(expression, Add):
		return max((_severity(term, symbol) for term in expression.terms), default=_ABSENT)
	if isinstance(expression, Sum):
		# The body is summed over an index, so a symbol entering it linearly
		# enters the sum linearly.
		return _severity(expression.body, symbol)
	if isinstance(expression, Mul):
		children = [_severity(factor, symbol) for factor in expression.factors]
		if _NONLINEAR in children:
			return _NONLINEAR
		# Two affine factors make a quadratic: ``a * a`` and ``a * b`` with
		# both named ``a`` are the same tree after flattening.
		return _NONLINEAR if children.count(_AFFINE) >= 2 else (
			_AFFINE if _AFFINE in children else _ABSENT
		)
	if isinstance(expression, Pow):
		base = _severity(expression.base, symbol)
		exponent = _severity(expression.exponent, symbol)
		if exponent != _ABSENT:
			# ``symbol`` in the exponent is nonlinear in it whatever the base
			# is -- ``a ** x`` is exponential in ``x``, and ``x ** x`` is not
			# even a power. This is checked *before* the base, because
			# ``a ** x`` has a symbol-free base and would otherwise fall
			# through the ``_ABSENT`` branch below as though the symbol were
			# not there at all.
			return _NONLINEAR
		if base == _NONLINEAR:
			return _NONLINEAR
		if base == _ABSENT:
			return _ABSENT
		# ``a ** 1`` is affine; every other constant power is not.
		if isinstance(expression.exponent, Const) and float(expression.exponent.value) == 1.0:
			return _AFFINE
		return _NONLINEAR
	if isinstance(expression, Func):
		# A function of the symbol is nonlinear in it whatever the function
		# is. ``abs`` is linear on each side of zero and not on any interval
		# containing it, and the solver cannot know which side it is on.
		return _NONLINEAR if any(_severity(arg, symbol) != _ABSENT for arg in expression.args) else _ABSENT
	return _NONLINEAR


def linearity_in(expression: Expr, symbol: str) -> str:
	"""Whether ``expression`` is linear or nonlinear **in one variable**.

	``LINEAR`` when ``symbol`` enters to the first power, ``NONLINEAR`` when it
	enters as a power, inside a function, or multiplied by itself.

	This is a different question from "is this equation linear", and the
	difference is the whole reason the model's equation-level ``linearity``
	field could not be reconciled with any reading of the formulas. ``x ** 2``
	is nonlinear in ``x`` and constant in ``y``; ``crf_definition`` is
	nonlinear in ``discount_rate`` (which appears as a power) and *affine in
	``crf``*, the variable it solves for. An equation has no linearity of its
	own -- only a variable has, and only relative to an expression.

	The distinction is not academic: it is what decides whether the solve can
	be exact. See :func:`linear_coefficients`.
	"""
	return NONLINEAR if _severity(expression, symbol) == _NONLINEAR else LINEAR


def linear_coefficients(expression: Expr, symbol: str) -> tuple[Expr, Expr] | None:
	"""``(a, b)`` with ``expression == a * symbol + b``, or ``None``.

	``None`` means ``expression`` is not affine in ``symbol``, which is a
	statement about this variable and not about the formula: an expression
	that is a cubic in ``x`` may still be affine in ``y``.

	``a`` and ``b`` are expressions, not floats -- a coefficient is routinely
	another parameter (``debt_fraction * capex_usd_per_kw`` is the coefficient
	on the solved variable in ``debt_service_definition``), so folding them to
	numbers here would need values this function does not have. The caller
	evaluates them.

	Raises ``DslError`` if ``symbol`` does not appear at all: a caller asking
	for the coefficients of a variable the expression never names has a bug,
	and returning ``(0, expression)`` would let it divide by zero one step
	later with nothing pointing at the cause.
	"""
	if symbol not in expression.symbols:
		raise DslError(
			f"{symbol!r} does not appear in {expression.source()!r}, so it has "
			f"no coefficient here"
		)
	if _severity(expression, symbol) == _NONLINEAR:
		return None

	def split(node: Expr) -> tuple[Expr, Expr]:
		"""``(coefficient_on_symbol, rest)`` for an affine subexpression."""
		if isinstance(node, Add):
			pairs = [split(term) for term in node.terms]
			return (
				Add.of(*(coefficient for coefficient, _ in pairs)),
				Add.of(*(rest for _, rest in pairs)),
			)
		if isinstance(node, Mul):
			# At most one factor carries the symbol -- two affine factors would
			# have been caught as nonlinear before ``split`` was reached -- so
			# the product is that factor's ``(c*x + r)`` scaled by every other
			# factor. Dropping the scale is the bug this shape exists to
			# avoid: ``2 * (x + a)`` has coefficient ``2`` and rest ``2 * a``,
			# and returning ``1`` and ``0`` would solve it as though it were
			# ``x + a``.
			carrier: tuple[Expr, Expr] | None = None
			others: list[Expr] = []
			for factor in node.factors:
				if _severity(factor, symbol) == _AFFINE:
					carrier = split(factor)
				else:
					others.append(factor)
			if carrier is None:
				return Const(0.0), node
			scale = Mul.of(*others) if others else Const(1.0)
			coefficient, rest = carrier
			return Mul.of(coefficient, scale), Mul.of(rest, scale)
		if isinstance(node, Pow) and _severity(node, symbol) == _AFFINE:
			# ``symbol ** 1``. The parser folds this to the symbol, but a tree
			# built by hand need not have.
			return Const(1.0), Const(0.0)
		if isinstance(node, (Symbol, Subscript)) and getattr(node, "name", None) == symbol:
			return Const(1.0), Const(0.0)
		return Const(0.0), node

	coefficient, rest = split(expression)
	return coefficient, rest


def solve_affine(
	expression: Expr,
	symbol: str,
	values: Mapping[str, float | str],
	*,
	residual: float = 0.0,
) -> float | None:
	"""The root of ``expression == residual`` when it is affine in ``symbol``.

	``None`` when ``expression`` is not affine in ``symbol``, or when the
	coefficient evaluates to zero -- ``0 * p + b == 0`` fixes nothing about
	``p``, so there is no root to return and ``None`` is the honest answer
	rather than an infinity a caller would divide by.

	The counterpart to :func:`solve_for`, and the two answer different
	questions. ``solve_for`` finds *a* root in a bracket and needs the bracket
	to contain one; this finds *the* root arithmetically and cannot miss. For
	an affine residual the two agree -- checked across the shipped library's
	33 determined variables, agreeing to 1e-9 relative -- so a caller that can
	take this path should, and a caller that cannot has a bracket to choose.
	"""
	coefficients = linear_coefficients(expression, symbol)
	if coefficients is None:
		return None
	coefficient, rest = coefficients
	a = evaluate(coefficient, values)
	if a == 0.0:
		return None
	return (residual - float(evaluate(rest, values))) / float(a)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


_ALLOWED = (
	ast.Expression,
	ast.BinOp,
	ast.UnaryOp,
	ast.Call,
	ast.Name,
	ast.Constant,
	ast.Add,
	ast.Sub,
	ast.Mult,
	ast.Div,
	ast.Pow,
	ast.USub,
	ast.UAdd,
	ast.Load,
	ast.Store,
	ast.GeneratorExp,
	ast.comprehension,
	ast.keyword,
	ast.Subscript,
	ast.Slice,
)


def parse(source: str) -> Expr:
	"""Parse a formula written in the DSL.

	The language is arithmetic over named parameters, the functions in
	:data:`_FUNCTIONS`, and ``sum(body for i in range(a, b))``. Every AST node
	not in ``_ALLOWED`` is refused by name, which is what makes this safe
	without ``eval``: the whitelist is the security boundary, and it is also
	the modelling boundary, because an expression that cannot be written cannot
	be silently ignored by the engine.

	A *whole* relation's arithmetic must name a parameter -- see
	:func:`parse_side` for why one side of one need not.
	"""
	return _parse(source, require_symbols=True)


def parse_side(source: str) -> Expr:
	"""Parse one side of a relation, where a constant is legitimate.

	``parse`` refuses an expression naming no parameter, on the grounds that it
	"relates nothing and would pass every consistency check vacuously". That
	argument is about a **relation**, and it was being applied to a **side**.

	The distinction matters because a bound equation's right-hand side *is* a
	constant: ``residential_demand_share + commercial_demand_share + ... <= 1.0``
	relates four parameters to a ceiling, and the ceiling is the point. Parsing
	the two sides separately to read their symbols -- which is what the loader,
	the constraint router, the loop scaler and the unit checker all do -- met
	the constant side and refused the whole equation. The residual the solver
	actually evaluates, ``(lhs) - (rhs)``, parsed and evaluated correctly all
	along, so the equation was expressible to every consumer except the checks
	that guarded it.

	The vacuity guard is not lost, it is **moved to where it can be stated**:
	:func:`alea.prg.graph.ParameterGraph.from_mapping` requires the combined
	arithmetic to name at least one parameter, which is the claim the original
	message was making. A fully-constant equation is still refused; a constant
	*side* is not.

	A bare constant is also the one expression ``solve_affine`` cannot solve for
	anything, so callers that derive a value must keep checking that their
	variable actually appears -- ``solve_affine`` raises ``DslError`` saying so,
	which is the right place for that check rather than here.
	"""
	return _parse(source, require_symbols=False)


def _parse(source: str, *, require_symbols: bool) -> Expr:
	"""The shared body of :func:`parse` and :func:`parse_side`."""
	if not source or not source.strip():
		raise DslError("an expression must not be empty")
	try:
		tree = ast.parse(source.strip(), mode="eval")
	except SyntaxError as exc:
		raise DslError(f"{source!r} is not a valid expression: {exc.msg}") from exc
	for node in ast.walk(tree):
		if not isinstance(node, _ALLOWED):
			raise DslError(
				f"{type(node).__name__} is not part of the DSL; an expression is "
				f"arithmetic over named parameters, the functions "
				f"{sorted(_FUNCTIONS)}, and sum(... for i in range(a, b))"
			)
	expression = _from_ast(tree.body)
	if require_symbols and not expression.symbols:
		raise DslError(
			f"{source!r} names no parameter; a constant expression relates "
			f"nothing and would pass every consistency check vacuously"
		)
	return expression


def _from_ast(node: ast.AST) -> Expr:
	if isinstance(node, ast.Constant):
		if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
			raise DslError(f"{node.value!r} is not a number")
		return Const(float(node.value))
	if isinstance(node, ast.Name):
		return sym(node.id)
	if isinstance(node, ast.BinOp):
		left, right = _from_ast(node.left), _from_ast(node.right)
		if isinstance(node.op, ast.Add):
			return Add.of(left, right)
		if isinstance(node.op, ast.Sub):
			return Add.of(left, Mul.of(Const(-1.0), right))
		if isinstance(node.op, ast.Mult):
			return Mul.of(left, right)
		if isinstance(node.op, ast.Div):
			return Mul.of(left, Pow(right, Const(-1.0)))
		if isinstance(node.op, ast.Pow):
			return Pow(left, right)
		raise DslError(f"unsupported operator {type(node.op).__name__}")
	if isinstance(node, ast.UnaryOp):
		operand = _from_ast(node.operand)
		if isinstance(node.op, ast.USub):
			return Mul.of(Const(-1.0), operand)
		if isinstance(node.op, ast.UAdd):
			return operand
		raise DslError(f"unsupported unary operator {type(node.op).__name__}")
	if isinstance(node, ast.Call):
		if not isinstance(node.func, ast.Name):
			raise DslError("only a direct call to a named function is allowed")
		if node.func.id == "sum":
			return _from_sum(node)
		if node.keywords:
			raise DslError("DSL functions take positional arguments only")
		return Func(node.func.id, tuple(_from_ast(arg) for arg in node.args))
	if isinstance(node, ast.Subscript):
		if not isinstance(node.value, ast.Name):
			raise DslError("only a named parameter may be subscripted")
		if isinstance(node.slice, ast.Slice):
			raise DslError("a slice is not in the DSL; sum over a range instead")
		return Subscript(sym(node.value.id), _from_ast(node.slice))
	if isinstance(node, ast.GeneratorExp):
		raise DslError(
			"a generator is only meaningful inside sum(...); write "
			"sum(expr for i in range(a, b))"
		)
	raise DslError(f"cannot parse {type(node).__name__}")


def _from_sum(node: ast.Call) -> Sum:
	if len(node.args) != 1 or not isinstance(node.args[0], ast.GeneratorExp):
		raise DslError(
			"sum takes one generator: sum(expr for i in range(a, b))"
		)
	generator = node.args[0]
	if len(generator.generators) != 1:
		raise DslError("sum takes one index; nest the sums instead")
	comprehension = generator.generators[0]
	if comprehension.ifs:
		raise DslError(
			"a conditional sum is not in the DSL; a sum over a filtered set is "
			"a sum over the set, and the filter belongs in the parameter"
		)
	if not isinstance(comprehension.target, ast.Name):
		raise DslError("sum's index must be a plain name")
	if not isinstance(comprehension.iter, ast.Call):
		raise DslError("sum's index must range over range(a, b)")
	if not isinstance(comprehension.iter.func, ast.Name) or comprehension.iter.func.id != "range":
		raise DslError("sum's index must range over range(a, b)")
	bounds = comprehension.iter.args
	if len(bounds) != 2 or not all(
		isinstance(bound, ast.Constant) and isinstance(bound.value, int)
		for bound in bounds
	):
		raise DslError("range's bounds must be integer literals")
	lower = int(bounds[0].value)  # type: ignore[arg-type]
	upper = int(bounds[1].value)  # type: ignore[arg-type]
	return Sum(
		comprehension.target.id,
		lower,
		upper - 1,
		_from_ast(generator.elt),
	)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _negation(expression: Expr) -> Expr | None:
	"""``-expression`` if the expression is a negative term, else ``None``.

	Used by the renderers to print ``a - b`` where the tree holds
	``a + (-1 * b)``. Storing subtraction as a negative term is what keeps
	``Add`` n-ary and associative; printing it as subtraction is what keeps the
	output readable.
	"""
	if isinstance(expression, Const) and expression.value < 0:
		return Const(-expression.value)
	if isinstance(expression, Mul) and expression.factors:
		head = expression.factors[0]
		if isinstance(head, Const) and head.value < 0:
			rest = Mul.of(Const(-head.value), *expression.factors[1:])
			return rest
	return None


_SUPERSCRIPTS = str.maketrans("0123456789+-.()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻·⁽⁾")


def _superscript(value: float) -> str | None:
	"""A Unicode superscript for a small integer exponent, else ``None``."""
	if value != int(value) or abs(value) > 99:
		return None
	return str(int(value)).translate(_SUPERSCRIPTS)


#: The public alias. ``Expression`` reads better at a call site that means "a
#: parsed formula"; the class is ``Expr`` because it is used in arithmetic.
Expression = Expr
