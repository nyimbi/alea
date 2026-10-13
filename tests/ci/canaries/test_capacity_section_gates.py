# SPDX-License-Identifier: MIT
"""Canary: the two capacity-section gates, each watched failing on its defect.

`04-layer1-planning.md` §7 promises two gates beyond the original eight, and
`tests/ci/test_capacity_section.py` implements them. Each is watched here
against the defect it exists to catch, because an implemented gate that has never
been seen to fail is not evidence (AD-10).

The two, and the defect each is watched against:

* ``test_the_capacity_section_carries_both_numbers_per_row`` -- write the
  capacity into the ``change`` column as well. The section declares two numeric
  columns, so `_rows_for` binds each header to the row column naming it and does
  *not* fall back to the primary. The producer satisfies every schema check and
  prints a capacity under the header "Change".
* ``test_the_capacity_section_refuses_to_invent_a_change`` -- write ``0.0`` into
  a ``change`` column when the directory holds one solve. A first capacity
  update has nothing to difference against, and a zero asserts the strongest
  claim the column can make -- capacity did not move -- from no evidence.

**Each mutation is a disjoint change to the asserted text, not a re-spelling.**
The lesson from the heading canary is that renaming `## Debt` to `## Debt spend`
still contains `## Debt`, so the check was satisfied and the canary proved
nothing. The first mutation swaps which variable fills the column -- the two are
different arrays, so the gate's inequality is what it targets. The second adds a
column that was absent, which is the defect itself.

**Both run in a subprocess**, as `test_market_section_gates.py` does. The gates
import `pypsa` and export a network, so an in-process reload would rebind modules
the gate compares against and the failure would have nothing to do with the gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.ci.canaries import REPO, planted

SERVICE_PY = REPO / "src" / "alea" / "planning" / "service.py"
ARRAYS_PY = REPO / "src" / "alea" / "planning" / "arrays.py"

GATES = REPO / "tests" / "ci" / "test_capacity_section.py"

GATE_BOTH_NUMBERS = "test_the_capacity_section_carries_both_numbers_per_row"
GATE_NO_INVENTED_CHANGE = "test_the_capacity_section_refuses_to_invent_a_change"


def _run_gate(gate: str) -> int:
	"""Exit code of one gate, run by pytest in a fresh interpreter.

	Under pytest rather than by calling the function: these gates take
	``tmp_path``, because they export a network and write an artefact, so a bare
	call raises `TypeError` and the canary would be measuring the wrong failure.
	"""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", str(GATES), "-q", "-x", "-k", gate],
		capture_output=True,
		text=True,
		cwd=REPO,
		check=False,
	)
	return completed.returncode


def _assert_gate_notices(gate: str, path: Path, old: str, new: str) -> None:
	"""Assert the gate passes, fails under the planted defect, then passes again.

	The premise is asserted first: a gate already red cannot tell a broken canary
	from a broken gate, and the failure would be blamed on a mutation that did not
	cause it.
	"""
	assert _run_gate(gate) == 0, (
		f"{gate} does not pass on the untouched tree, so this canary cannot show "
		f"the defect caused the failure"
	)

	with planted(path, old, new):
		assert _run_gate(gate) != 0, (
			f"{gate} still passes with the defect planted in {path.name}; the gate "
			f"is blind to the class it exists to catch"
		)

	assert _run_gate(gate) == 0, (
		f"{gate} did not recover after the canary was restored, so the canary "
		f"proves the gate can fail but not that it clears"
	)


def test_the_canary_targets_are_the_gates_the_register_promises():
	"""A canary on a renamed gate is a canary on nothing."""
	text = GATES.read_text()
	for gate in (GATE_BOTH_NUMBERS, GATE_NO_INVENTED_CHANGE):
		assert f"def {gate}(" in text, f"gate {gate} is not defined in {GATES.name}"


def test_the_both_numbers_gate_notices_the_capacity_written_into_the_change_column():
	"""Fill ``change`` with the capacity: the section renders and lies.

	`capacity_update` declares ``["Carrier", "Capacity", "Change", "Basis"]`` --
	two numeric columns -- so the reader requires a ``capacity`` extra and a
	``change`` extra and does not fall back to the primary. A producer that wrote
	the same array into both satisfies every schema check the artefact has and
	prints a capacity under the header "Change". The gate's last assertion is the
	one this mutation targets, and the two variables are different arrays, so the
	mutation is disjoint from what the gate reads.
	"""
	target = '\t\tframe["change"] = [value - before.get(carrier, 0.0) for carrier, value in zip(carriers, capacity, strict=True)]\n'
	replacement = '\t\tframe["change"] = list(capacity)\n'
	assert target in SERVICE_PY.read_text(), (
		"the canary target moved; `capacity_update_rows`'s change column is no "
		"longer in the form this canary expects, so the canary would be a no-op"
	)
	_assert_gate_notices(GATE_BOTH_NUMBERS, SERVICE_PY, target, replacement)


def test_the_no_invented_change_gate_notices_a_zero_where_the_column_was_absent():
	"""Write a ``change`` column of zeros with one solve in the directory.

	The gate asserts the column is *absent* when there is no earlier network to
	difference against, and the provenance says why. A producer that wrote zeros
	instead would render a real-looking measurement asserting that capacity did
	not move, which is the strongest claim the column can make and is made here
	from the absence of an input.
	"""
	target = "\tif previous is not None:\n\t\tframe[\"change\"] = [value - before.get(carrier, 0.0) for carrier, value in zip(carriers, capacity, strict=True)]\n"
	replacement = "\tframe[\"change\"] = [value - before.get(carrier, 0.0) for carrier, value in zip(carriers, capacity, strict=True)]\n"
	assert target in SERVICE_PY.read_text(), (
		"the canary target moved; the `previous is not None` guard around the "
		"change column is no longer in the form this canary expects, so the "
		"canary would be a no-op"
	)
	_assert_gate_notices(GATE_NO_INVENTED_CHANGE, SERVICE_PY, target, replacement)
