# SPDX-License-Identifier: MIT
"""Canary: the three market section gates, each watched failing on its defect.

`06-layer3-market.md` §9 promises three gates beyond the original nine, and
`tests/ci/test_market_report_sections.py` implements them. Each is watched here
against the defect it exists to catch, because an implemented gate that has
never been seen to fail is not evidence (AD-10) -- and one of these three was
written *because* a defect got through a suite that had no gate there.

The three, and the defect each is watched against:

* ``test_the_fleet_excludes_load_shedding_and_sums_the_network_capacity`` --
  empty the ``LOAD_SHEDDING_CARRIERS`` set, so the shedding unit enters the fleet
  and the clearing prices the shortage instead of reporting it.
* ``test_the_fleet_carries_the_network_s_own_marginal_cost`` -- return zeros from
  ``_marginal_cost``, so every unit bids the same number and the section's
  average price becomes a constant that looks plausible.
* ``test_the_monthly_section_reads_back_with_both_numbers_distinct`` -- write the
  average price into the ``volume`` column as well, which is the defect the
  two-numeric-column binding in `_rows_for` exists to prevent: the section
  renders, the schema matches, and the header "Volume" prints a price.

**Each mutation is a superstring-free, disjoint change to the asserted text.**
The lesson from the heading canary is that renaming `## Debt` to `## Debt spend`
still contains `## Debt`, so the check was satisfied and the canary proved
nothing. The mutations here remove or replace what the gate reads rather than
re-spelling it: an emptied set, a returned zero array, a swapped column.

Each runs in a **subprocess**, as `test_market_gates.py` does: the gates solve a
`pypsa` network and the modules are imported at collection, so an in-process
reload would rebind classes the gate compares against and the failure would have
nothing to do with the gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.ci.canaries import REPO, planted

FLEET_PY = REPO / "src" / "alea" / "market" / "fleet.py"
SERVICE_PY = REPO / "src" / "alea" / "market" / "service.py"

GATES = REPO / "tests" / "ci" / "test_market_report_sections.py"

GATE_LOAD_SHEDDING = "test_the_fleet_excludes_load_shedding_and_sums_the_network_capacity"
GATE_MARGINAL_COST = "test_the_fleet_carries_the_network_s_own_marginal_cost"
GATE_BOTH_NUMBERS = "test_the_monthly_section_reads_back_with_both_numbers_distinct"


def _run_gate(gate: str) -> int:
	"""Exit code of one gate, run by pytest in a fresh interpreter.

	Under pytest rather than by calling the function: these gates take
	``tmp_path``, because they solve a network and write an artefact, so a bare
	call raises `TypeError` and the canary would be measuring the wrong failure.
	The subprocess is what makes the mutation visible -- the modules are imported
	at collection, so an in-process reload would rebind classes the gate compares
	against.
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
	for gate in (GATE_LOAD_SHEDDING, GATE_MARGINAL_COST, GATE_BOTH_NUMBERS):
		assert f"def {gate}(" in text, f"gate {gate} is not defined in {GATES.name}"


def test_the_load_shedding_gate_notices_a_unit_that_is_not_skipped():
	"""Empty the carrier set: the shedding unit enters the fleet.

	The gate asserts the fleet is exactly the network's real generators. A
	``skip_carriers`` default that nothing exercises is a comment, and this is the
	mutation that turns it back into one -- the shedding unit has a positive
	capacity and a VoLL-sized bid, so it changes both the identifier set and the
	capacity sum the gate reads.
	"""
	_assert_gate_notices(
		GATE_LOAD_SHEDDING,
		FLEET_PY,
		'LOAD_SHEDDING_CARRIERS = frozenset({"load shedding", "load_shedding", "load-shedding"})',
		"LOAD_SHEDDING_CARRIERS: frozenset[str] = frozenset()",
	)


def test_the_marginal_cost_gate_notices_a_flattened_bid():
	"""Return zeros: every unit bids the same, and the average price is a constant.

	The gate asserts coal bids the network's own 45.0 and solar its 0.0. Returning
	a zero array is the defect the gate exists to catch -- it is also the shape a
	producer reaches for when the network's cost column is missing, which is why
	the fallback is asserted rather than assumed.
	"""
	target = (
		"\tif \"marginal_cost\" not in generators.columns:\n"
		"\t\treturn np.zeros(len(generators), dtype=np.float64)\n"
	)
	replacement = "\treturn np.zeros(len(generators), dtype=np.float64)\n"
	assert target in FLEET_PY.read_text(), (
		"the canary target moved; `_marginal_cost`'s column check is no longer in "
		"the form this canary expects, so the canary would be a no-op"
	)
	_assert_gate_notices(GATE_MARGINAL_COST, FLEET_PY, target, replacement)


def test_the_both_numbers_gate_notices_the_primary_written_into_both_columns():
	"""Write the average price into ``volume``: the section renders and lies.

	`market_report` declares two numeric columns, so `_rows_for` requires a
	``volume`` extra and an ``average_price`` extra and does *not* fall back to
	the primary. A producer that wrote the same number into both satisfies every
	schema check the artefact has and prints a price under the header "Volume".
	The gate's last assertion is the one this mutation targets, and the mutation
	is the defect itself rather than a re-spelling of it.
	"""
	target = '\t\t\t\t"volume": mwh,\n'
	replacement = '\t\t\t\t"volume": average,\n'
	assert target in SERVICE_PY.read_text(), (
		"the canary target moved; the monthly producer's `volume` column is no "
		"longer in the form this canary expects, so the canary would be a no-op"
	)
	_assert_gate_notices(GATE_BOTH_NUMBERS, SERVICE_PY, target, replacement)
