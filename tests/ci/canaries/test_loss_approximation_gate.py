# SPDX-License-Identifier: MIT
"""Canary for the DC-loss-against-AC gate.

`tests/ci/test_loss_approximation.py` exists because the kernel, its Python
reference and the differential test all carried the same wrong unit constant
(`1000/3`), so the differential test agreed with itself and disagreed with the
physics. It reported a three-bus fixture losing 138% of its generation.

One planted defect fails all four of that file's gates, because they are four
views of one quantity: ``test_the_kernel_agrees_with_the_closed_form``,
``test_the_kernel_agrees_with_ac_power_flow``,
``test_a_line_never_loses_more_than_it_carries`` and
``test_a_realistic_line_loses_a_few_percent_not_a_multiple``.

The canary plants a wrong constant **at the gate's own boundary** -- the Python
wrapper the gate imports -- and asserts the gate notices. That is the defect
class the gate is for: a value that is wrong by a unit factor and looks
plausible. It is planted in `kernels.py` rather than in the Rust source because
a rebuild of the extension inside a canary swaps a shared `.so` under every
other test in the run, which is a canary that damages the suite it is checking.
The wrapper is a real seam -- the gate imports through it -- so a wrong factor
there reaches the gate exactly as the Rust one did.

This canary documents its own limit: it proves the gate observes a wrong
*value*, not that it would catch a Rust-side regression specifically. The
Rust-side check is `cargo test -p alea-losses`, whose
`transmission_losses_matches_the_three_phase_formula` pins the value in the
crate.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, pytest

KERNELS = REPO / "src" / "alea" / "_core" / "kernels.py"
GATE = "tests/ci/test_loss_approximation.py"

ANCHOR = """	return float(
		_rust.transmission_losses(
			_f64(flows, "flows"), _f64(resistance, "resistance"), _f64(voltage_kv, "voltage_kv")
		)
	)"""

#: The shipped bug, exactly: a factor of 1000/3 too large.
PLANTED = """	return float(
		_rust.transmission_losses(
			_f64(flows, "flows"), _f64(resistance, "resistance"), _f64(voltage_kv, "voltage_kv")
		)
		* 1000.0
		/ 3.0
	)"""


def _gate_exit_code() -> int:
	"""Exit code of the loss gate, run in a fresh interpreter.

	A fresh interpreter matters here: the gate imports the wrapper at module
	import, so an in-process canary that patched the function object would be
	asserting its own monkeypatch rather than what the shipped import resolves
	to.
	"""
	import subprocess
	import sys

	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE, "-q", "-x"],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_gate_catches_a_wrong_loss_constant():
	"""The shipped defect: a loss 333x the physics.

	The gate must fail on it. A kernel returning 1000/3 times the true loss
	reported a 138% loss fraction, and no property or differential test saw it
	because every one of them compared the kernel against a reference carrying
	the same constant.
	"""
	assert ANCHOR in KERNELS.read_text(encoding="utf-8"), (
		f"canary target not found in {KERNELS.name}. The gate may already be "
		f"reading a source that has moved, in which case this canary is a no-op "
		f"that reports a blind gate."
	)
	assert _gate_exit_code() == 0, f"{GATE} does not pass on the shipped tree"
	with planted(KERNELS, ANCHOR, PLANTED):
		assert _gate_exit_code() != 0, (
			"a loss 1000/3 times the physics still passed the gate, so a unit "
			"error in the loss kernel is invisible"
		)
	assert _gate_exit_code() == 0, "the restore was not proven"


def test_the_gate_is_not_vacuous_on_a_clean_tree():
	"""A gate that fails on everything is not a gate either.

	Stated as its own test so a reader sees the two-sided claim: the gate passes
	when the constant is right and fails when it is wrong. Without this, a gate
	that raised on import would satisfy the canary above.
	"""
	assert _gate_exit_code() == 0, (
		f"{GATE} does not pass on the shipped tree, so the canary above proves "
		f"nothing about the constant"
	)


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
