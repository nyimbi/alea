# SPDX-License-Identifier: MIT
"""Canary: a "has this been solved?" guard must ask ``.empty``, not ``len()``.

A PyPSA dynamic table is indexed by snapshots and has one column per component.
An *unsolved* network therefore reports ``len(n.generators_t.p) == 3`` on a
three-snapshot network — one placeholder row per snapshot, zero columns. Every
guard written as ``if not len(network.generators_t.p)`` passed on exactly the
input it was written to refuse, and the function then read an empty frame:

* ``loss_share`` divided 0.0 losses by an empty generation total and returned a
  loss share of 0.0 for a network that had never been solved.
* ``check_energy_balance``, ``total_emissions``, ``marginal_prices``,
  ``generation_by_carrier``, ``curtailment_mwh`` and ``peak_mw`` all took the
  same shape.

Nine call sites had it. The predicate is now one function,
``alea.planning.expansion.has_dispatch``.

WHY this canary runs in a subprocess rather than reloading in-process: the
mutation is to a module that defines an exception class, and ``importlib.reload``
re-executes the ``class`` statement, minting a *new* ``ExpansionError`` object.
Every module that bound the old one — including the gate module this canary
exists to watch — then catches a class the reverted code no longer raises, and
the gate fails for a reason that has nothing to do with the defect. A child
process contains the reload; the parent's module identity is never touched.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.ci.canaries import REPO
from tests.ci.test_planning_layer1 import _network, _solvable

EXPANSION_PY = REPO / "src" / "alea" / "planning" / "expansion.py"
DISPATCH_PY = REPO / "src" / "alea" / "planning" / "dispatch.py"

HAVE_DISPATCH_EXPANSION = (
	'\tif not has_dispatch(network):\n'
	'\t\traise ExpansionError("network has no dispatch; solve it first")'
)
LEN_FORM_EXPANSION = (
	'\tif not len(network.generators_t.p):\n'
	'\t\traise ExpansionError("network has no dispatch; solve it first")'
)
HAVE_DISPATCH_DISPATCH = (
	'\tif not has_dispatch(network):\n'
	'\t\traise DispatchError("network has no dispatch; solve it first")'
)
LEN_FORM_DISPATCH = (
	'\tif not len(network.generators_t.p):\n'
	'\t\traise DispatchError("network has no dispatch; solve it first")'
)

_PROGRAM = """
import importlib, sys
from pathlib import Path

import pandas as pd
import pypsa

from tests.ci.canaries import REPO, planted

path = Path(sys.argv[1])
target, revert, module_name = sys.argv[2], sys.argv[3], sys.argv[4]
function_name, error_name = sys.argv[5], sys.argv[6]

if target not in path.read_text():
    print("TARGET-MISSING")
    raise SystemExit(0)

module = importlib.import_module(module_name)

def unsolved():
    network = pypsa.Network()
    network.add("Bus", "b1", carrier="AC")
    network.set_snapshots(list(pd.date_range("2030-01-01", periods=3, freq="h")))
    network.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
    network.add("Load", "load", bus="b1", p_set=120.0)
    return network

with planted(path, target, revert):
    importlib.reload(module)
    error = getattr(module, error_name)
    try:
        getattr(module, function_name)(unsolved())
    except error as exc:
        print("RAISED:" + str(exc))
    else:
        print("PASSED-THROUGH")
"""


def _run(path, target, revert, module_name, function_name: str, error_name: str) -> str:
	"""Plant the defect in a child process and report what the function did."""
	result = subprocess.run(
		[sys.executable, "-c", _PROGRAM, str(path), target, revert, module_name, function_name, error_name],
		capture_output=True,
		text=True,
		cwd=REPO,
	)
	assert result.returncode == 0, f"the canary subprocess failed:\n{result.stderr}"
	line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
	assert line != "TARGET-MISSING", f"canary target not found in {path.name}: {target!r}"
	return line


def test_the_fixture_is_snapshot_indexed_but_unsolved():
	"""The canaries below are vacuous unless ``len()`` and ``.empty`` disagree.

	If a future PyPSA stops pre-sizing dynamic tables to the snapshot index, the
	``len()`` form would become correct, the revert would raise as it should,
	and every canary here would pass against a defect it did not plant.
	"""
	unsolved = _solvable()
	assert len(unsolved.snapshots) > 1, "a one-snapshot network cannot distinguish the two forms"
	assert len(unsolved.generators_t.p) == len(unsolved.snapshots)
	assert unsolved.generators_t.p.empty, "the table is not empty on an unsolved network"


def test_the_gate_catches_the_len_guard_in_loss_share():
	"""Revert ``loss_share`` to the ``len()`` guard and watch it pass through.

	Under the revert the guard passes on an unsolved network, generation is the
	sum of an empty frame (0.0), and the function returns 0.0 instead of raising.
	The gate it blinds is
	``test_loss_share_refuses_a_network_with_no_dispatch``.
	"""
	outcome = _run(
		EXPANSION_PY,
		HAVE_DISPATCH_EXPANSION,
		LEN_FORM_EXPANSION,
		"alea.planning.expansion",
		"loss_share",
		"ExpansionError",
	)
	assert outcome == "PASSED-THROUGH", (
		f"the reverted guard still refused an unsolved network ({outcome!r}); the "
		f"len() form did not reproduce the silent pass"
	)

	# Restored: the gate's own assertion holds again. Asserted in the parent,
	# whose module identity the child never touched.
	from alea.planning.expansion import ExpansionError, loss_share

	with pytest.raises(ExpansionError, match="solve it first"):
		loss_share(_network())


def test_the_gate_catches_the_len_guard_in_the_energy_balance():
	"""Revert ``check_energy_balance``'s dispatch guard the same way.

	The reverted guard lets an unsolved network reach the balance check, where
	the error is the whole generation figure — a wrong diagnosis for a network
	that was never solved. The gate is
	``test_the_energy_balance_reads_a_static_load``'s sibling assertion.
	"""
	outcome = _run(
		DISPATCH_PY,
		HAVE_DISPATCH_DISPATCH,
		LEN_FORM_DISPATCH,
		"alea.planning.dispatch",
		"check_energy_balance",
		"DispatchError",
	)
	assert outcome.startswith("RAISED:"), (
		f"the reverted guard did not reach the balance check ({outcome!r}); the "
		f"defect did not reproduce"
	)
	assert "energy balance fails" in outcome, (
		f"the reverted guard raised something other than the balance failure: {outcome}"
	)
	assert "solve it first" not in outcome

	from alea.planning.dispatch import DispatchError, check_energy_balance

	with pytest.raises(DispatchError, match="solve it first"):
		check_energy_balance(_solvable())


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
