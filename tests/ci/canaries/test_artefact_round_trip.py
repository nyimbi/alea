# SPDX-License-Identifier: MIT
"""Canary: blind `read_raw`'s re-hash and watch §4.3's round-trip gate fail.

The gate is ``test_artefact_round_trip`` in `tests/ci/test_io_artefacts.py`. It
asserts three things about the read side of the raw layer, and one of them is
the load-bearing one: a payload sitting under an address it does not hash to is
**refused**. That is what makes the address a verification rather than a label.

**This blinds the read side, which the sibling canary does not.**
`test_raw_immutability.py` removes the re-hash in `store_raw` -- the *write*
side, which catches a tamper on the next store. `read_raw` re-hashes on the way
out, so a payload edited after it was stored is refused by every reader even if
nothing ever stores again. They are two different lines in two different
functions, and removing either leaves the other's gate passing. A canary that
blinds the wrong one would report the round-trip gate as watched while the read
path stayed unverified -- which is the state this gate was written to fix, since
`read_raw` had **zero callers** before it.

**Why a subprocess.** `planted` rewrites the source; the interpreter running
this test already holds `alea.io.artefacts`, so an in-process call would exercise
the *unmutated* module and the canary would pass against a defect it never
reached. The gate is therefore run by name in a fresh interpreter, which is also
what makes this a canary of the gate rather than of a copy: nothing here
reimplements the round trip.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

#: Runs the gate by name in a fresh interpreter. `-p no:randomly` because a
#: canary asserting on one node's exit code should not depend on collection
#: order, and the gate is selected by node id anyway.
_GATE = """
import sys
import pytest

sys.exit(pytest.main(["-q", "-p", "no:randomly",
                      "tests/ci/test_io_artefacts.py::test_artefact_round_trip"]))
"""


def test_the_address_check_on_read_is_the_gate():
	"""Remove `read_raw`'s re-hash and the round-trip gate stops refusing.

	The mutation is `if actual != checksum:` -> `if False:`, which is disjoint
	from what the gate's assertion looks for: the gate matches the *message*
	``"does not match its address"``, and the mutation removes the branch that
	raises it rather than rewording it. A mutation that merely reworded the
	message would leave the branch standing and the gate would still fail --
	for the wrong reason -- so the canary would prove nothing about the check.

	The restore is proven by the third run. The first run is the control: a gate
	that does not pass on the shipped tree cannot be canaried, because the
	mutated run would fail for whatever reason the clean one did.
	"""
	artefacts = REPO / "src" / "alea" / "io" / "artefacts.py"
	target = "if actual != checksum:"
	assert target in artefacts.read_text(), "canary target not found: no re-hash in read_raw"

	assert probe_exit_code(_GATE) == 0, (
		"the round-trip gate does not pass on the shipped tree, so the canary "
		"below would prove nothing about the re-hash"
	)

	with planted(artefacts, target, "if False:  # canary"):
		assert probe_exit_code(_GATE) != 0, (
			"the round-trip gate passed with `read_raw`'s re-hash removed; the "
			"gate is not measuring the address check, and a tampered payload "
			"would be served under the checksum its provenance attests to"
		)

	# Restored: the gate refuses again.
	assert probe_exit_code(_GATE) == 0, "the restore did not put the address check back"
