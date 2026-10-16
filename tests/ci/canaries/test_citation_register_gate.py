# SPDX-License-Identifier: MIT
"""Canary: the citation register must notice a citation resolving to nothing.

`tests/ci/test_citation_register.py` is the gate. It asserts that every
citation the tree makes resolves to a row in `sources/INDEX.md` and that every
row is reached by a citation, which is the join `alea.provenance.citations`
exists to make. A join is the easiest kind of gate to write as a no-op -- a
report that returns no gaps satisfies every "no gaps" assertion in the file --
so this canary blinds the comparison and watches the gate go red.

**The mutation blinds the forward join, and the forward join is the half that
matters.** The reverse check ("no row is unreachable") and the archive check
("no row claims a copy it lacks") both still pass under this mutation, because
neither reads the citation list. So a canary that planted a defect in the wrong
place would look like a gate that cannot fail. The line blinded here is the one
`test_every_citation_resolves_to_a_registered_work` measures: the `any(...)`
that decides whether a citation reaches a row.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

MODULE = REPO / "src" / "alea" / "provenance" / "citations.py"

#: The gate, run in a subprocess so the mutation is read by a fresh interpreter.
#: `-p no:randomly` because a canary asserts on one node's verdict and test
#: order is irrelevant to it; the suite's own ordering plugin would make the
#: subprocess slower without making the assertion stronger.
_GATE = """
import sys
import pytest

sys.exit(pytest.main(["-q", "-p", "no:randomly",
                      "tests/ci/test_citation_register.py"]))
"""

#: The forward join. `resolves` is called once per citation per row, and
#: returning `False` unconditionally is the smallest edit that makes *every*
#: citation unresolvable -- so the gate must report every citation as
#: unregistered rather than reporting none.
TARGET = "return any(needle.casefold() in haystack for needle in self.cites)"


def test_the_citation_gate_fails_when_the_join_is_blinded():
	"""Blind `Citation.resolves`; the gate must go red and then green again."""
	assert MODULE.is_file(), f"canary target is not a file: {MODULE}"
	before = MODULE.read_text()
	assert TARGET in before, (
		"canary target not found: `resolves` no longer returns the substring "
		"match this canary blinds, so the mutation would be a no-op"
	)

	# Premise: the gate passes on the untouched tree. Without this the canary
	# cannot tell a blinded join from a gate that was already failing.
	assert probe_exit_code(_GATE) == 0, (
		"the citation gate does not pass on the untouched tree, so this canary "
		"cannot attribute a failure to its own mutation"
	)

	with planted(MODULE, TARGET, "return False  # canary: join blinded"):
		assert probe_exit_code(_GATE) != 0, (
			"the gate still passes with every citation unresolvable; it is not "
			"reading the join it claims to check"
		)

	# And it recovers, or the canary proves the gate can fail but not that it
	# tracks the code -- a permanently-red gate is one nobody reads.
	assert probe_exit_code(_GATE) == 0, (
		"the gate did not recover after the mutation was restored"
	)


def test_the_digest_gate_fails_when_a_recorded_digest_is_wrong():
	"""A second, disjoint mutation: the archive's digest row.

	Blinding the join proves the *citation* half of the gate works. This plants
	a defect the join never sees -- a digest that does not match the file it
	names -- so the archive half is watched failing too. One canary that blinded
	one line would leave half the gate unexercised, which is the "gate scoped to
	the bug you found, not the class it belongs to" failure.

	The mutation is to `sources/INDEX.md`, a different file from the join
	canary's, so the two cannot interfere if they ever run concurrently.
	"""
	index = REPO / "sources" / "INDEX.md"
	assert index.is_file(), f"canary target is not a file: {index}"
	before = index.read_text()
	# The shipped digest's first eight hex characters. Mutating the *recorded*
	# value rather than the file keeps the mutation inside the document the
	# gate reads, so no large binary is touched and the restore is exact.
	target = "b04c0d5234e2d2bfeb38960e76b6409741f3e478cd7a71a772d924b8e70ced0e"
	assert target in before, (
		"canary target not found: the digest row for the archived IRENA copy is "
		"no longer in INDEX.md, so this mutation would be a no-op"
	)

	assert probe_exit_code(_GATE) == 0, "premise: the gate passes untouched"

	with planted(index, target, "0" * 64):
		assert probe_exit_code(_GATE) != 0, (
			"the gate passes with a recorded digest that does not match the "
			"file; the archive half of the register is not being checked"
		)

	assert probe_exit_code(_GATE) == 0, (
		"the gate did not recover after the digest was restored"
	)
