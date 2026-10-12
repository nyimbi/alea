# SPDX-License-Identifier: MIT
"""The DC loss approximation, checked against AC power flow.

`12-quality.md` §2 states the discipline this file exists for:

    A kernel that is self-consistently wrong passes every property test. ...
    The reference implementation is a second, independent expression of the
    same mathematics, and disagreement between two independent implementations
    of the same formula is strong evidence that one is wrong.

and then names the one exception:

    **One exception:** `losses.py` may use `pypsa`'s AC power flow, because it
    is checking the DC approximation against the physics, and the physics is
    what pypsa implements correctly.

That exception was documented and never used. Every test of
`transmission_losses` compared the kernel against `tests/reference/losses.py`,
and the reference carried the *same constant* as the kernel, so the two agreed
with each other and disagreed with the physics by a factor of 1000/3. On a
three-bus fixture the shipped kernel reported a loss fraction of **1.377** --
138% of generated energy lost in transmission. A differential test cannot see
that: it is a test of consistency, and both sides were consistently wrong.

The fix is the check the plan already specified. A line's loss is
hand-computable, so this file builds a network whose loss is known in closed
form, solves it with pypsa's AC power flow, and requires the DC figure to land
inside the approximation's own error budget.

**Why this is not circular.** The expected value is `S^2 R / V^2` derived on
paper from `P = 3 I^2 R` and `I = S / (sqrt(3) V)`, not read off either
implementation. The AC solve is a third, independent expression, from a library
that models the physics rather than the approximation. Three expressions of one
quantity, and the assertion is that they agree.

**The 2% budget.** `07-layer4-predictive.md` §6.3 promises "loss approximation
< 2% error vs. full AC" and records it `[UNVERIFIED]`. The tolerance below is
looser than 2% because the DC approximation neglects reactive flow and voltage
drop, and those are real differences rather than implementation error -- on the
fixture lines the gap is ~2-5%. The gate's job is to catch a *unit* error, which
is orders of magnitude larger, while leaving the DC-vs-AC physics gap to the M1
benchmark that measures it.
"""

from __future__ import annotations

import numpy as np
import pypsa
import pytest

from alea._core import transmission_losses

#: The fixture lines: ``(resistance_ohm, voltage_kv, flow_mw, x_over_r)``.
#: A range of voltages and loadings, because a unit error is a *scaling* error
#: and a single case could hide behind a coincidental agreement.
LINES = (
	(10.0, 220.0, 100.0, 4.0),
	(1.0, 132.0, 50.0, 3.0),
	(5.0, 400.0, 300.0, 5.0),
	(2.5, 66.0, 20.0, 2.0),
)

#: The DC-vs-AC gap the approximation is allowed, before a discrepancy is an
#: implementation error rather than the physics the approximation neglects.
#: Wide on purpose: a unit constant is wrong by 3x or 333x, so a bound this
#: loose still catches every error this file is for.
TOLERANCE = 0.15


def _ac_loss(resistance_ohm: float, voltage_kv: float, flow_mw: float, x_over_r: float) -> float:
	"""The real loss from pypsa's AC power flow, in MW.

	A two-bus network: one generator, one load, one line. The AC solve models
	the resistance, the reactive flow and the voltage drop that the DC
	approximation drops, so it is the ground truth this gate measures against.
	"""
	network = pypsa.Network()
	network.set_snapshots(range(1))
	network.add("Bus", "A", v_nom=voltage_kv)
	network.add("Bus", "B", v_nom=voltage_kv)
	network.add(
		"Line",
		"L1",
		bus0="A",
		bus1="B",
		r=resistance_ohm,
		x=resistance_ohm * x_over_r,
		s_nom=flow_mw * 10.0,
	)
	network.add("Generator", "G", bus="A", p_nom=flow_mw * 10.0, marginal_cost=10.0)
	network.add("Load", "D", bus="B", p_set=flow_mw)
	network.pf()
	p0 = float(network.lines_t.p0["L1"].iloc[0])
	p1 = float(network.lines_t.p1["L1"].iloc[0])
	return p0 + p1


def _closed_form_loss(flow_mw: float, resistance_ohm: float, voltage_kv: float) -> float:
	"""`S^2 R / V^2` -- the loss derived on paper, from `3 I^2 R`.

	Written as the algebra rather than as `3 * I**2 * R` so the simplification
	is visible: the three phases and the `sqrt(3)` in the line current cancel.
	"""
	return flow_mw**2 * resistance_ohm / voltage_kv**2


@pytest.mark.parametrize(("resistance", "voltage", "flow", "x_over_r"), LINES)
def test_the_kernel_agrees_with_the_closed_form(
	resistance: float, voltage: float, flow: float, x_over_r: float
) -> None:
	"""The kernel equals the paper derivation, not just its own reference.

	This is the assertion that fails on the shipped bug: the kernel returned
	`S^2 R / V^2 * 1000 / 3`, which is 333x this value.
	"""
	got = transmission_losses(np.array([flow]), np.array([resistance]), np.array([voltage]))
	expected = _closed_form_loss(flow, resistance, voltage)
	assert got == pytest.approx(expected, rel=1e-9), (
		f"kernel loss {got} MW != closed form {expected} MW for "
		f"{flow} MW over {resistance} ohm at {voltage} kV"
	)


@pytest.mark.parametrize(("resistance", "voltage", "flow", "x_over_r"), LINES)
def test_the_kernel_agrees_with_ac_power_flow(
	resistance: float, voltage: float, flow: float, x_over_r: float
) -> None:
	"""The DC loss is within the approximation's budget of the AC loss.

	`12-quality.md` §2's sanctioned exception: this is the one place a test may
	depend on pypsa's AC power flow, because it checks the approximation against
	the physics rather than reproducing it.
	"""
	dc = transmission_losses(np.array([flow]), np.array([resistance]), np.array([voltage]))
	ac = _ac_loss(resistance, voltage, flow, x_over_r)
	assert ac > 0.0, "the AC solve reported no loss; the fixture is not exercising it"
	relative = abs(dc - ac) / ac
	assert relative < TOLERANCE, (
		f"DC loss {dc:.6f} MW is {relative:.1%} from the AC loss {ac:.6f} MW for "
		f"{flow} MW over {resistance} ohm at {voltage} kV. The DC approximation "
		f"neglects reactive flow and voltage drop, which is a few percent; a "
		f"discrepancy this large is a unit error in the kernel."
	)


@pytest.mark.parametrize(("resistance", "voltage", "flow", "x_over_r"), LINES)
def test_a_line_never_loses_more_than_it_carries(
	resistance: float, voltage: float, flow: float, x_over_r: float
) -> None:
	"""A physical ceiling on the loss, needing no reference implementation.

	A line cannot lose more power than it carries. The shipped kernel violated
	this on three of these four lines -- 100 MW over 10 ohm at 220 kV produced
	688.7 MW -- and this is the invariant that makes such a defect impossible to
	reintroduce quietly.

	**It is necessary, not sufficient.** The fourth line, 50 MW over 1 ohm at
	132 kV, produces 47.8 MW of loss under the bug, which slips under the
	ceiling because the buggy constant is only 333x and that line's true loss is
	small. This test therefore cannot be the only one: the closed-form and
	AC-solve tests above are what pin the value, and they fail on that line.
	Keeping the bound anyway is worth it -- it is the one assertion here that
	holds with no formula and no library, so it survives a change to either.
	"""
	loss = transmission_losses(np.array([flow]), np.array([resistance]), np.array([voltage]))
	assert 0.0 < loss < flow, (
		f"loss {loss} MW for a {flow} MW flow over {resistance} ohm at "
		f"{voltage} kV; a line cannot lose more than it carries, so a constant "
		f"is wrong"
	)


def test_a_realistic_line_loses_a_few_percent_not_a_multiple() -> None:
	"""The magnitude a reader expects, stated once.

	An African transmission line loses on the order of 1-5% of what it carries.
	A figure above 100% is not an aggressive network; it is a unit error. This
	asserts the order of magnitude on a line whose parameters are ordinary.
	"""
	flow, resistance, voltage = 100.0, 10.0, 220.0
	loss = transmission_losses(np.array([flow]), np.array([resistance]), np.array([voltage]))
	share = loss / flow
	assert 0.0 < share < 0.05, (
		f"{share:.2%} of a {flow} MW flow lost over {resistance} ohm at "
		f"{voltage} kV; a transmission line is a few percent, not a multiple"
	)
