# SPDX-License-Identifier: MIT
"""Canary for the one gate the system-alerts producer adds.

`system_alerts_rows` drops a branch whose ``load_shed_mw`` is not finite and
counts it, and the reason is arithmetic rather than taste: every comparison
against NaN is ``False``, so ``project_resilience_contingency``'s banding
expression falls through to ``"low"`` for a branch whose contingency could not
be computed. ``low`` is a claim about the element -- that it does not matter --
and the sweep did not make it. A producer that carried the row through would
publish a table asserting no impact for an element nobody measured, and the
table would look exactly like a correct one.

So the gate is `test_the_section_s_columns_are_the_serving_table_s_renamed`, and
this plants the defect it exists for: the finiteness guard removed, so the NaN
row reaches the frame.

**The assertion is on the failing test's name, not on the exit code.** A
mutation that breaks the import also exits non-zero, and a canary that accepted
that would be reporting a gate it never pointed anywhere. The output is checked
for the gate's own id, so a failure for any other reason is a failure of this
canary.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

GATE_FILE = "tests/ci/test_system_alerts.py"
GATE = "test_the_section_s_columns_are_the_serving_table_s_renamed"
SERVICE = REPO / "src" / "alea" / "resilience" / "service.py"

#: The guard, as it is written. Two lines: the count and the skip. Replacing both
#: with nothing lets the NaN row through, which is the defect.
GUARD = "\t\tif not math.isfinite(shed):\n\t\t\tuncomputable += 1\n\t\t\tcontinue\n"


def _run_gate() -> tuple[int, str]:
	"""The gate's exit code and output, run in a fresh interpreter.

	A subprocess because the mutation is a source edit: the module is imported at
	collection, so an in-process canary would run the gate against the file as it
	was when pytest started.
	"""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-k", GATE],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode, completed.stdout + completed.stderr


def test_the_gate_notices_a_branch_whose_load_shed_could_not_be_computed():
	"""The defect: the finiteness guard removed, so NaN is banded ``"low"``.

	The section's ``State`` is a claim about the element and ``low`` is the
	strongest form of the claim the sweep did not earn. The gate counts the
	dropped rows, so removing the drop moves the count and the gate fails.
	"""
	assert GUARD in SERVICE.read_text(encoding="utf-8"), (
		"the canary target moved; the finiteness guard is no longer spelled this "
		"way, and a patch that does not apply is a canary that did not run"
	)

	code, output = _run_gate()
	assert code == 0, (
		f"the gate does not pass on the shipped tree, so this canary cannot tell "
		f"a broken gate from a tree that is already broken:\n{output[-3000:]}"
	)

	with planted(SERVICE, GUARD, ""):
		code, output = _run_gate()
		assert code != 0, (
			"the gate passed with the finiteness guard removed: a branch whose "
			"every snapshot diverged carries a NaN load shed, and the serving "
			"projection bands it `low` -- so the section would report no impact "
			"for an element nobody measured"
		)
		assert GATE in output, (
			f"the gate failed for a reason other than the dropped branch:\n"
			f"{output[-3000:]}"
		)

	code, output = _run_gate()
	assert code == 0, (
		f"the gate did not pass again after the mutation was restored, so the "
		f"restore is not proven:\n{output[-3000:]}"
	)
