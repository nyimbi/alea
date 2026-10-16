# SPDX-License-Identifier: MIT
"""Canary: the gate register must notice a gate that loses its canary.

`scripts/gate_register.py` is itself a gate -- `12-quality.md` §9 criteria 2 and
7 are "every gate has a canary that has been observed to fail" and "the gate
register has no Unverified rows for shipped gates", and this is the thing that
decides both. A register that has never been seen to change its verdict is a
register that may be reading the wrong set, the wrong spelling, or nothing at
all, which is the exact class of failure the register exists to catch.

The mutation is to a real canary module: its citation of the gate it guards is
removed, and the register must move that gate from **Verified** to
**Uncanaried**. Restoring the citation must move it back. Both halves are
asserted, because a register that reports a defect it cannot clear is as useless
as one that reports nothing.
"""

from __future__ import annotations

import importlib.util
import sys

from tests.ci.canaries import REPO, planted

REGISTER = REPO / "scripts" / "gate_register.py"
CANARY = REPO / "tests" / "ci" / "canaries" / "test_scanning_retention_gate.py"

# The citation the canary module carries for the gate it guards. Both the module
# docstring and the gate function name it; removing one occurrence is enough to
# break the link the register reads.
#
# Assembled from backticks rather than written literally: the register scans for
# backticked names, so a literal here would make *this* file a canary for the
# gate and the canary would pass no matter what the real canary module said.
GATE = "test_retention_policy_applied"
CITATION = "`" * 2 + GATE + "`" * 2


def _load():
	"""Import the register script by path; it is not part of the package."""
	spec = importlib.util.spec_from_file_location("_gate_register_canary", REGISTER)
	assert spec and spec.loader, f"cannot load {REGISTER}"
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def test_the_register_reports_the_gate_verified_to_begin_with():
	"""The premise: the gate is cited, so the register trusts it."""
	register = _load()
	_, found, _ = register.report()
	assert found[GATE].canaries, (
		f"{GATE} has no citing canary in the untouched tree, so this canary "
		f"cannot tell a broken register from a gate that was never canaried"
	)


def test_the_register_notices_a_gate_that_lost_its_canary():
	"""Remove the citation; the gate must fall out of the verified set."""
	before = CANARY.read_text()
	assert CITATION in before, "canary target not found"

	register = _load()
	_, trusted, _ = register.report()
	assert trusted[GATE].canaries, "premise failed: gate was not canaried"

	with planted(CANARY, CITATION, "``the retention gate``"):
		register = _load()
		_, found, _ = register.report()
		assert not found.get(GATE, register.Implementation()).canaries, (
			"the register still reports a canary for a gate whose citation was "
			"removed; it is reading something other than the citation"
		)

	# Restored by `planted`, and the register must agree again -- otherwise the
	# canary proves the register can fail but not that it recovers, and a
	# permanently-red register is one nobody reads.
	register = _load()
	_, found, _ = register.report()
	assert found[GATE].canaries, "the register did not recover after the restore"


def test_the_unnamed_verdict_reads_both_spellings_of_a_gate_cell():
	"""The fourth verdict, canaried on its own boundary.

	``cell_describes_a_test`` reports an exit-criteria cell that *describes* a
	test without naming one -- the 32 cells the other three verdicts cannot see
	at all, because ``promised_gates`` reads backticked names and "Integration
	test" contains none. A verdict added without watching it classify anything is
	the same defect the register exists to catch, one level up.

	**It calls the predicate rather than restating it.** The first version of
	this canary reimplemented the three conditions inline, and a probe that
	disabled the real predicate left the copy intact: the canary passed and
	watched nothing. A canary whose logic is disjoint from its target's cannot
	see the target change.

	**Both sides of the boundary, and the instrument cases in between.** A check
	is only as good as its default on known-good text: flagging a named gate
	would make every named criterion a false positive, and flagging `CI` or `M8`
	would demand a ``test_`` name from a criterion no test can satisfy.
	"""
	register = _load()
	describes = register.cell_describes_a_test

	# Flagged: the cell says a test exists and not which one.
	assert describes("Integration test")
	assert describes("Canary")
	assert describes("Property test")
	# Not flagged: the cell names its gate.
	assert not describes("`test_kenya_solves`")
	assert not describes("`test_a`, `test_b`")
	# Not flagged: it names its gate *and* says "test". No cell in the corpus
	# carries both, so without this line the `GATE_NAME` guard is unexercised and
	# deleting it changes nothing a reader would see -- a condition kept for a
	# case the plans happen not to contain yet.
	assert not describes("Integration test `test_kenya_solves`")
	assert not describes("Canary: `test_var_matches_the_analytic_normal_quantile`")
	# Not flagged: not a test at all. Each of these is a criterion a `test_` name
	# cannot satisfy, and demanding one would redden the register for good.
	assert not describes("M8")
	assert not describes("CI")
	assert not describes("Determinism job")
	assert not describes("M2 artefact")
	# A backticked *path* is a named instrument, not a described test.
	assert not describes("`tests/ci/canaries`")
	assert not describes("`gh api .../actions/runs`")


def test_the_unnamed_verdict_notices_a_disabled_predicate():
	"""Disable the vocabulary test; the boundary cases must go red.

	The canary proper. Without this the cases above could be passing because the
	predicate is right *or* because nothing reads it -- and the mutation has to
	be one the predicate's own logic cannot absorb: ``if False and ...`` makes
	every cell classify as unnamed, which the "not flagged" assertions catch.
	"""
	register = _load()
	assert register.cell_describes_a_test("Integration test"), "premise failed"

	with planted(REGISTER, "return bool(_TEST_VOCABULARY.search", "return bool(True or _TEST_VOCABULARY.search"):
		register = _load()
		assert register.cell_describes_a_test("CI"), (
			"a cell that names no test at all was classified as describing one, so "
			"the vocabulary check is not what decides the verdict"
		)

	register = _load()
	assert not register.cell_describes_a_test("CI"), "the register did not recover"


def test_the_unnamed_verdict_reads_a_planted_cell():
	"""Plant the defect in a real plan; the report must carry it.

	The unit cases above pin the predicate. This one pins the wiring: a cell that
	describes its gate, written into an actual exit-criteria table, must reach
	``unnamed_criteria`` with its document and row number. Without it the
	predicate could be right and the scan pointed at nothing -- a check that is
	correct and disconnected reports clean forever.
	"""
	register = _load()
	plan = REPO / "docs" / "plans" / "12-quality.md"
	before = plan.read_text()
	target = "| 8 | CI run history is non-empty and growing | `gh api .../actions/runs` |"
	assert target in before, "canary target not found: the quality table moved"

	planted_row = "| 8 | CI run history is non-empty and growing | Integration test |"
	with planted(plan, target, planted_row):
		rows = register.unnamed_criteria()
		hits = [r for r in rows if r[0] == "12-quality" and r[2] == "8"]
		assert hits, (
			"a planted cell that describes its gate did not reach the report; the "
			"scan is correct but pointed at nothing"
		)
		doc, heading, number, criterion, cell = hits[0]
		assert (doc, number) == ("12-quality", "8"), (doc, number)
		assert criterion == "CI run history is non-empty and growing", criterion
		assert cell == "Integration test", cell
		assert "Exit criteria" in heading, heading

	# Restored, and the row must leave the report again -- a verdict that cannot
	# clear is one nobody reads.
	rows = register.unnamed_criteria()
	assert not [r for r in rows if r[0] == "12-quality" and r[2] == "8"], (
		"the planted cell is still reported after the restore"
	)


def test_the_register_reads_the_gate_tables_and_not_the_prose():
	"""A gate named only in a narrative paragraph is not a promise.

	`12-quality.md` §3.2 sketches the canary directory with ten filenames. Read
	as promises they would demand a canary for each of ten files that already
	exist, which is how a register invents work that is already done.
	"""
	register = _load()
	promised = register.promised_gates()
	assert promised, "the register promised no gates at all"
	# `test_every_kernel_is_present_and_callable` is a real test that no gate
	# table names. If the register read prose, some narrative mention would drag
	# it in; it must not.
	assert "test_every_kernel_is_present_and_callable" not in promised


def test_every_promised_gate_names_a_document():
	"""A gate with no document is a promise with no jurisdiction."""
	register = _load()
	promised = register.promised_gates()
	undocumented = [gate for gate, docs in promised.items() if not docs]
	assert not undocumented, f"gates promised by no document: {undocumented}"


def test_the_check_mode_exits_non_zero_while_a_gate_is_unverified():
	"""`--check` is the CI half: a gap must be a non-zero exit, not a report.

	The gap is *planted*, not read off the tree. The register reached zero on
	2026-10-12, and the version of this canary that asserted the tree had a gap
	then failed -- correctly, because the tree no longer did. A canary that needs
	the tree to be broken is a canary that breaks the day the work is finished,
	and the fix is to make the defect rather than wait for one.

	Removing a citation is the smallest defect the register can see: one gate
	falls from Verified to Uncanaried, and `--check` must notice.

	**Scoped to the gate, not the tree.** This asserted
	``main(["--check"]) == 0`` before planting, on the reasoning that a canary
	cannot attribute a failure it did not cause. The premise was true only
	while the register was blind: widening it to the h3 gate sections on
	2026-10-16 moved the tree from 0 gaps to 9, and this assertion then failed
	for a reason that had nothing to do with the citation it plants. A canary
	whose precondition is "the tree has no other defect anywhere" is a canary
	that reddens on every unrelated gap -- and the honest reading of that
	failure is not that this canary broke, but that it was measuring the wrong
	thing. It now measures the *delta*: the planted gate must fall out of the
	verified set and the exit must be non-zero, whatever the rest of the tree
	holds.
	"""
	before = CANARY.read_text()
	assert CITATION in before, "canary target not found"

	register = _load()
	_, trusted_before, _ = register.report()
	assert trusted_before[GATE].canaries, (
		"premise failed: the gate was not canaried before the plant, so a "
		"fall from the verified set cannot be attributed to it"
	)

	with planted(CANARY, CITATION, "``the retention gate``"):
		register = _load()
		_, trusted_after, _ = register.report()
		assert not trusted_after[GATE].canaries, (
			"the planted defect did not move the gate out of the verified set"
		)
		assert register.main(["--check"]) == 1, (
			"--check exited 0 with a gate that lost its canary"
		)

	# Restored, and the gate must be trusted again -- otherwise the canary
	# proves the register can fail but not that it recovers.
	register = _load()
	_, trusted_restored, _ = register.report()
	assert trusted_restored[GATE].canaries, "the register did not recover after the restore"


def test_the_markdown_register_marks_unverified_gates():
	"""The rendered table must not print a gap as Verified.

	Same planting: the table is rendered from the mutated tree so there is a real
	unverified gate in it, rather than trusting the tree to contain one.
	"""
	before = CANARY.read_text()
	assert CITATION in before, "canary target not found"

	with planted(CANARY, CITATION, "``the retention gate``"):
		register = _load()
		promised, found, _ = register.report()
		table = register.render_markdown(promised, found)
		line = next(line for line in table.splitlines() if f"`{GATE}`" in line)
		assert "Uncanaried" in line, f"{GATE} renders as trusted: {line}"
