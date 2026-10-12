# SPDX-License-Identifier: MIT
"""Canary: the renewable multiplier must be absolute, not compound.

The specification's ``_apply`` scales buildable potential with
``n.generators.loc[mask, "p_nom_max"] *= multiplier``. That is a *relative*
operation on an *absolute* quantity: applied twice it squares the potential
rather than repeating the same scenario. A sweep that re-applies a template to
the previous point's output then reports a frontier that is an artefact of the
bookkeeping, not of the parameter.

The gate is ``test_apply_is_idempotent`` in ``tests/ci/test_whatif_layer5.py``:
it applies the same parameters twice and asserts the result equals a single
application, and -- separately -- that a single application of 2.5 on a base of
200 MW is exactly 500 MW. The second assertion is what makes the first
meaningful: a pair of applications that agree on a *wrong* number would pass a
bare equality check. The plan's name for this gate is
``test_renewable_multiplier_absolute`` (08-layer5 §9).

This canary reverts ``_apply_renewable_potential`` to the compound form and
asserts the gate's equality fails. It reloads the module around the mutation
because the scaling is done by the package, not handed to it.
"""

from __future__ import annotations

import importlib

import pytest

from alea.whatif import ScenarioParameters
from tests.ci.canaries import REPO, planted
from tests.ci.test_whatif_layer5 import _network

APPLY_PY = REPO / "src" / "alea" / "whatif" / "apply.py"

# The absolute form: read the base from the recorded snapshot, scale that.
ABSOLUTE = (
	'\tbase = _restore(generators["p_nom_max"], snapshot.get("p_nom_max", {}))\n'
	'\tscaled = base.where(~pd.Series(mask, index=generators.index), base * params.renewable_multiplier)\n'
	'\tnetwork.generators["p_nom_max"] = scaled'
)

# The specification's form: scale whatever value is currently there.
COMPOUND = (
	"\tmask_series = pd.Series(mask, index=generators.index)\n"
	'\tnetwork.generators.loc[mask_series, "p_nom_max"] *= params.renewable_multiplier'
)


def test_the_gate_catches_a_compound_multiplier() -> None:
	"""Revert to ``p_nom_max *= multiplier`` and watch the idempotence gate fail.

	The gate applies ``renewable_multiplier=2.5`` twice and asserts the result
	equals a single application. Under the compound form the second application
	squares the potential (500 -> 1250), so the two disagree -- which is exactly
	the failure the gate exists to catch.
	"""
	source = APPLY_PY.read_text()
	assert ABSOLUTE in source, "canary target not found: the absolute scaling moved"

	apply_module = importlib.import_module("alea.whatif.apply")
	params = ScenarioParameters(renewable_multiplier=2.5)

	with planted(APPLY_PY, ABSOLUTE, COMPOUND):
		importlib.reload(apply_module)
		base = _network()
		once = apply_module.apply_parameters(base, params)
		twice = apply_module.apply_parameters(once, params)
		once_value = float(once.generators.loc["solar", "p_nom_max"])
		twice_value = float(twice.generators.loc["solar", "p_nom_max"])
		# The gate asserts these are equal; under the compound form they are not.
		assert once_value != twice_value, (
			"the compound multiplier did not compound; the canary did not reproduce "
			"the defect"
		)
		assert twice_value == pytest.approx(once_value * 2.5)

	importlib.reload(apply_module)
	# Restored: the gate's own assertions hold again.
	restored_once = apply_module.apply_parameters(_network(), params)
	restored_twice = apply_module.apply_parameters(restored_once, params)
	assert float(restored_once.generators.loc["solar", "p_nom_max"]) == pytest.approx(500.0)
	assert float(restored_twice.generators.loc["solar", "p_nom_max"]) == pytest.approx(500.0)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
