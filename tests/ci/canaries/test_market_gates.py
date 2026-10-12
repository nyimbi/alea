# SPDX-License-Identifier: MIT
"""Canary: each Layer 3 market gate must be watched failing on its own defect.

`06-layer3-market.md` §9 promises nine gates. `tests/ci/test_market_layer3.py`
implements all nine, but an implemented gate that has never been seen to fail is
not evidence of anything (AD-10): it may be scoped to the wrong fixture, may
assert a property the code cannot violate, or may never have run at all. This
module plants each gate's defect and asserts the gate notices.

The nine gates and the defect each is watched against:

* ``test_clearing_deterministic`` -- drop ``unit_id`` from the merit-order sort
  key, so a price tie dispatches in list order (AD-8's non-determinism).
* ``test_clearing_meets_demand`` -- report no shortfall from a short stack, so
  dispatched MW no longer account for demand.
* ``test_shortage_priced_at_voll`` -- remove the VoLL override, so a short stack
  quotes its marginal bid as the clearing price.
* ``test_competitive_matches_merit_order`` -- bid a markup from the competitive
  strategy, so the clearing price no longer equals the marginal unit's cost.
* ``test_alpha_calibration`` -- ignore the conduct parameter, so alpha no longer
  moves the price between the competitive and monopoly benchmarks.
* ``test_capture_nan_on_no_generation`` -- return 0.0 where the capture price is
  undefined, the specification's own defect (06-layer3 §5.1).
* ``test_var_sign_convention`` -- negate VaR, so the reported loss magnitude
  carries the wrong sign.
* ``test_cholesky_checked`` -- swap the checked kernel Cholesky for numpy's
  unchecked one, so a non-PSD correlation raises the wrong error instead of the
  named one.
* ``test_fx_rate_recorded`` -- remove the local-price-needs-an-FX-rate check, so
  a PPA price can be built with no rate and no date.

Each mutation is run in a **subprocess**, not by reloading the module in-process.
Reloading rebinds the classes the gate compares against -- a reloaded
``views.PpaBenchmark`` is not the one the imported test module validates -- and
the failure that follows has nothing to do with the gate. A subprocess reads the
mutated source fresh, exactly as CI would.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.ci.canaries import REPO, planted

CLEARING_PY = REPO / "src" / "alea" / "market" / "clearing.py"
STRATEGY_PY = REPO / "src" / "alea" / "market" / "strategy.py"
CAPTURE_PY = REPO / "src" / "alea" / "market" / "capture.py"
RISK_PY = REPO / "src" / "alea" / "market" / "risk.py"
VIEWS_PY = REPO / "src" / "alea" / "market" / "views.py"

GATES = REPO / "tests" / "ci" / "test_market_layer3.py"

# The gate functions the canary drives. Named here rather than typed inline so a
# rename in the test module is a single edit, and a rename that misses is a loud
# ImportError in the subprocess rather than a silently-passing canary.
GATE_DETERMINISTIC = "test_a_price_tie_breaks_on_unit_id_not_list_order"
GATE_MEETS_DEMAND = "test_clearing_meets_demand"
GATE_VOLL = "test_a_short_stack_clears_at_voll_and_reports_the_shortfall"
GATE_COMPETITIVE = "test_a_competitive_clearing_reproduces_the_marginal_units_cost"
GATE_ALPHA = "test_alpha_calibration"
GATE_CAPTURE_NAN = "test_capture_nan_on_no_generation"
GATE_VAR_SIGN = "test_var_matches_the_analytic_normal_quantile"
GATE_CHOLESKY = "test_a_non_positive_definite_correlation_raises"
GATE_FX = "test_a_ppa_price_records_its_fx_rate_and_date"


def _run_gate(gate: str) -> subprocess.CompletedProcess[str]:
	"""Run one gate function in a fresh interpreter, reading the tree from disk."""
	program = f"from tests.ci.test_market_layer3 import {gate}\n{gate}()\n"
	env = {
		**os.environ,
		"PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)]),
	}
	return subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		cwd=REPO,
		env=env,
		check=False,
	)


def _assert_gate_notices(gate: str, path: Path, old: str, new: str) -> None:
	"""Assert the gate passes, fails under the planted defect, then passes again.

	The premise (passing before the mutation) is asserted first: a gate that is
	already red cannot tell a broken canary from a broken gate, and the failure
	would be attributed to the mutation it did not cause.
	"""
	before = _run_gate(gate)
	assert before.returncode == 0, (
		f"{gate} does not pass on the untouched tree, so this canary cannot show "
		f"the defect caused the failure:\n{before.stderr}"
	)

	with planted(path, old, new):
		during = _run_gate(gate)
		assert during.returncode != 0, (
			f"{gate} still passes with the defect planted in {path.name}; the gate "
			f"is blind to the class it exists to catch"
		)

	# Restored by `planted`, and the gate must recover -- otherwise the canary
	# proves the gate can fail but not that it clears, and a permanently-red gate
	# is one nobody reads.
	after = _run_gate(gate)
	assert after.returncode == 0, (
		f"{gate} did not recover after the canary was restored:\n{after.stderr}"
	)


def test_the_canary_targets_are_the_gates_the_register_promises():
	"""A canary on a renamed gate is a canary on nothing."""
	text = GATES.read_text()
	for gate in (
		GATE_DETERMINISTIC,
		GATE_MEETS_DEMAND,
		GATE_VOLL,
		GATE_COMPETITIVE,
		GATE_ALPHA,
		GATE_CAPTURE_NAN,
		GATE_VAR_SIGN,
		GATE_CHOLESKY,
		GATE_FX,
	):
		assert f"def {gate}(" in text, f"gate {gate} is not defined in {GATES.name}"


def test_the_clearing_deterministic_gate_notices_list_order_ties():
	"""Drop ``unit_id`` from the sort key; a price tie then follows list order."""
	_assert_gate_notices(
		GATE_DETERMINISTIC,
		CLEARING_PY,
		"\treturn sorted(available, key=lambda b: (b.price_usd_per_mwh, b.unit_id))",
		"\treturn sorted(available, key=lambda b: b.price_usd_per_mwh)",
	)


def test_the_clearing_meets_demand_gate_notices_a_dropped_shortfall():
	"""Report no unserved energy from a short stack; the balance no longer closes."""
	_assert_gate_notices(
		GATE_MEETS_DEMAND,
		CLEARING_PY,
		"\tunserved = max(remaining, 0.0)",
		"\tunserved = 0.0",
	)


def test_the_shortage_priced_at_voll_gate_notices_a_removed_override():
	"""Remove the VoLL override; a short stack quotes its marginal bid instead."""
	_assert_gate_notices(
		GATE_VOLL,
		CLEARING_PY,
		"\tif unserved > 0.0:\n\t\tclearing_price = value_of_lost_load_usd_per_mwh",
		"\tif False:  # canary\n\t\tclearing_price = value_of_lost_load_usd_per_mwh",
	)


def test_the_competitive_gate_notices_a_markup_in_the_competitive_strategy():
	"""Bid a markup from the competitive strategy; the merit-order price moves."""
	_assert_gate_notices(
		GATE_COMPETITIVE,
		STRATEGY_PY,
		"\t\t\tcase StrategyKind.COMPETITIVE:\n\t\t\t\treturn marginal_cost_usd_per_mwh",
		"\t\t\tcase StrategyKind.COMPETITIVE:\n\t\t\t\treturn marginal_cost_usd_per_mwh * 1.5",
	)


def test_the_alpha_calibration_gate_notices_an_ignored_conduct_parameter():
	"""Return the cost regardless of alpha; alpha no longer moves the price."""
	_assert_gate_notices(
		GATE_ALPHA,
		STRATEGY_PY,
		"\t\t\t\treturn marginal_cost_usd_per_mwh * (1.0 + self.supply_function_alpha)",
		"\t\t\t\treturn marginal_cost_usd_per_mwh",
	)


def test_the_capture_nan_gate_notices_a_zero_written_for_no_generation():
	"""Return 0.0 where the capture price is undefined, the spec's own defect."""
	_assert_gate_notices(
		GATE_CAPTURE_NAN,
		CAPTURE_PY,
		"\tif not np.isfinite(total) or total <= 0.0:\n\t\treturn _NAN",
		"\tif not np.isfinite(total) or total <= 0.0:\n\t\treturn 0.0",
	)


def test_the_var_sign_gate_notices_a_negated_loss_magnitude():
	"""Negate VaR; the model refuses the sign, so the gate fails on the defect."""
	_assert_gate_notices(
		GATE_VAR_SIGN,
		RISK_PY,
		"\t\tvalue_at_risk_usd=abs(float(value)),",
		"\t\tvalue_at_risk_usd=-abs(float(value)),",
	)


def test_the_cholesky_gate_notices_an_unchecked_factor():
	"""Swap the checked kernel for numpy's; a non-PSD matrix raises the wrong error."""
	_assert_gate_notices(
		GATE_CHOLESKY,
		RISK_PY,
		"\tfactor = cholesky(matrix)",
		"\tfactor = np.linalg.cholesky(matrix)",
	)


def test_the_fx_rate_gate_notices_a_removed_local_price_check():
	"""Remove the check; a local-currency price can be built with no rate or date."""
	_assert_gate_notices(
		GATE_FX,
		VIEWS_PY,
		"\t\tif self.price_local_per_mwh is not None and self.fx is None:",
		"\t\tif False:  # canary",
	)


def test_the_subprocess_runner_can_actually_fail():
	"""The runner is the instrument; a runner that cannot fail proves nothing.

	Pointed at a gate that does not exist, the subprocess must exit non-zero --
	if it exited 0 here, every canary above would pass against an interpreter that
	never ran the gate.
	"""
	result = _run_gate("test_this_gate_does_not_exist")
	assert result.returncode != 0, "the subprocess runner reported success for a missing gate"
	assert "ImportError" in result.stderr or "cannot import name" in result.stderr


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
