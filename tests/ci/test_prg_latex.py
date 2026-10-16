# SPDX-License-Identifier: MIT
"""The stored LaTeX rendering, and the check that keeps it honest.

WHAT THESE TESTS ARE FOR. ``Equation.latex`` exists so a relation can be
*explained* later, not merely displayed: the DSL's own renderer folds constants
while typesetting, so the learning curve's ``log(1 - rate) / log(2)`` renders
with the literal ``0.693147`` where the base-2 doubling convention belongs. A
stored string lets an author write ``\\log_2`` and say what they meant.

That makes the field a *claim*, and a claim nothing reads is the defect this
repository keeps paying for. So the tests come in two groups:

1. **Does a declared rendering win, and does the fallback still work?** The
   fallback is what most of the library uses, and a `latex_of` that returned
   ``None`` for an undeclared equation would break every report.
2. **Does `check_latex` catch a rendering that describes a different equation?**
   Canaried against a planted defect, because a check that has never been
   watched failing is not a check -- and the failure mode here is subtle: a
   rendering with the wrong *notation* is correct and must pass, while one with
   the wrong *operand set* is a different equation and must fail.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from alea.prg.dsl import parse
from alea.prg.graph import ParameterGraph, load_graph
from alea.prg.service import (
	_latex_symbols,
	check_latex,
	describe,
	generated_latex,
	latex_of,
)
from alea.prg.views import Equation

#: A relation with a logarithm, which is the case the field exists for: the
#: renderer turns its `log(2)` into a decimal and a reader cannot recover the
#: base from the output.
LEARNING_CURVE = "learning_curve"


def _equation(**overrides: object) -> Equation:
	"""The shipped learning curve, with fields overridden."""
	base = load_graph().equations[LEARNING_CURVE]
	return Equation(**{**base.model_dump(), **overrides})


# --------------------------------------------------------------------------
# The rendering: declared wins, generated is the fallback.
# --------------------------------------------------------------------------


def test_a_declared_rendering_is_what_renders():
	"""The point of the field. An author who wrote `\\log_2` must get `\\log_2`,
	not the renderer's folded `0.693147`."""
	declared = r"\mathrm{x} = \log_2\left(1 - \mathrm{learning}_{rate}\right)"
	equation = _equation(latex=declared)
	assert latex_of(equation) == declared
	assert r"\log_2" in latex_of(equation)
	# And the generated form really is different, so the assertion above is not
	# passing against a renderer that happened to agree.
	assert "0.693147" in generated_latex(equation)


def test_an_undeclared_rendering_falls_back_to_the_dsl():
	"""Most of the library declares nothing. A fallback that returned ``None``
	would put the string 'None' in a report."""
	equation = _equation(latex=None)
	rendered = latex_of(equation)
	assert rendered == generated_latex(equation)
	assert rendered  # not empty, not the string "None"
	assert "=" in rendered


def test_describe_uses_the_declared_rendering():
	"""`describe` is the door a report goes through, so the field has to reach
	it. A field only `latex_of` reads is a field a report never shows."""
	declared = r"\mathrm{a} = \mathrm{b}"
	assert describe(_equation(latex=declared), as_="latex") == declared


def test_the_other_renditions_ignore_the_latex_field():
	"""`latex` is one of three renditions. A field that leaked into `source`
	would put markup in the text a reviewer reads in the YAML."""
	equation = _equation(latex=r"\mathrm{deliberately}_{wrong}")
	assert "deliberately" not in describe(equation, as_="source")
	assert "deliberately" not in describe(equation, as_="unicode")


# --------------------------------------------------------------------------
# The model refuses a rendering that cannot be typeset at all.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
	("label", "text"),
	[
		("unclosed brace", r"\frac{a}{b"),
		("stray close brace", r"a} = b"),
		("math delimiter", r"$a = b$"),
	],
)
def test_a_rendering_that_cannot_be_typeset_is_refused(label: str, text: str):
	"""A malformed rendering is silent until a report is typeset, which may be
	never. Refused at construction, where the failure names the equation."""
	with pytest.raises(ValidationError):
		_equation(latex=text)


def test_a_well_formed_rendering_is_accepted():
	"""The control for the three refusals above: without it they pass against a
	validator that refuses every string."""
	assert _equation(latex=r"\frac{\mathrm{a}}{\mathrm{b}} = \mathrm{c}").latex


# --------------------------------------------------------------------------
# The check. Canaried against a planted defect.
# --------------------------------------------------------------------------


def _with_latex(equation_id: str, rendering: str) -> ParameterGraph:
	"""The shipped graph with one equation's rendering replaced.

	``ParameterGraph`` is frozen, so the substitution goes through the private
	mapping. That is deliberate here: the alternative is building a whole
	document to test one field, which would put the document's validity between
	the test and the thing it is testing.
	"""
	graph = load_graph()
	replaced = Equation(**{**graph.equations[equation_id].model_dump(), "latex": rendering})
	object.__setattr__(graph, "_equations", {**graph.equations, equation_id: replaced})
	return graph


def test_the_symbol_recovery_round_trips_the_renderer():
	"""`check_latex` compares operand *sets*, so it is only as good as the
	recovery of a name from its LaTeX. If this drifts, every equation reads as
	disagreeing and the check becomes noise nobody reads."""
	equation = load_graph().equations[LEARNING_CURVE]
	held = parse(equation.lhs).symbols | parse(equation.rhs).symbols
	assert _latex_symbols(generated_latex(equation)) == held


def test_a_rendering_that_omits_an_operand_is_reported():
	"""The canary. A rendering of a *different* equation -- here the same
	subject with its exponent dropped -- typesets fine and describes other
	physics, which is exactly what the check is for."""
	graph = _with_latex(LEARNING_CURVE, r"\mathrm{capex}_{learning\_usd\_per\_kw} = \mathrm{capex}_{usd\_per\_kw}")
	findings = check_latex(graph)
	assert len(findings) == 1
	assert findings[0].equation_id == LEARNING_CURVE
	assert "omits" in findings[0].detail


def test_a_rendering_naming_a_parameter_the_arithmetic_lacks_is_reported():
	"""The other direction. A rendering that invents an operand is a rendering
	of an equation the graph does not have."""
	generated = generated_latex(load_graph().equations[LEARNING_CURVE])
	present = r"\mathrm{cumulative}_{capacity\_mw}"
	# The canary's own patch must apply, or the test passes against a graph it
	# never changed and reports the check as blind when it is not.
	assert present in generated
	alien = generated.replace(present, r"\mathrm{widget}_{count}")
	assert alien != generated
	findings = check_latex(_with_latex(LEARNING_CURVE, alien))
	assert len(findings) == 1
	assert "does not hold" in findings[0].detail


def test_a_rendering_that_differs_only_in_notation_passes():
	"""The control that keeps the check from being a string comparison. A
	declared rendering is *allowed* to differ -- that is why it exists -- so
	replacing the folded `0.693147` with `\\log_2` must be accepted."""
	equation = load_graph().equations[LEARNING_CURVE]
	generated = generated_latex(equation)
	held = parse(equation.lhs).symbols | parse(equation.rhs).symbols
	# Rebuild the same relation by hand, in a different but equivalent style:
	# every operand present, the constants written differently.
	hand = (
		r"\mathrm{capex}_{learning\_usd\_per\_kw} = "
		r"\mathrm{capex}_{usd\_per\_kw} \cdot "
		r"\left(\frac{\mathrm{cumulative}_{capacity\_mw}}"
		r"{\mathrm{cumulative}_{capacity\_reference\_mw}}\right)"
		r"^{\log_2\left(1 - \mathrm{learning}_{rate}\right)}"
	)
	assert _latex_symbols(hand) == held
	assert hand != generated
	assert check_latex(_with_latex(LEARNING_CURVE, hand)) == []


def test_the_shipped_library_declares_renderings_that_agree():
	"""The integration assertion. Every declared rendering in the merged graph
	must describe its own arithmetic -- this is the check running over the
	batches that declare one, and it is where a hand-written `latex` that
	drifted from its `rhs` would be caught."""
	assert check_latex(load_graph()) == []
