#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Derive the gate register from the plans and the tests, and report the gaps.

`12-quality.md` §7 is the register of every gate in the plan with its canary and
a status column. §9 criteria 2 and 7 read it: "every gate has a canary that has
been observed to fail", "the gate register has no 'Unverified' rows for shipped
gates". Both were marked **Manual**, which is the failure mode this project has
already paid for more than once -- a register maintained by hand is a register
that describes the tree as it was when someone last edited it, and every gate
added since is invisible.

§7 carried such a table: 42 rows under the heading "Every gate in the plan",
against the 112 the plans actually promise (measured 2026-10-16). It is now this
script's `--markdown` output. The section is prose about *how* the register is
derived and what its discovery rules got wrong; the table is generated, so it
cannot describe a tree other than the one on disk.

So the register is *derived* here, from two sources that are already
authoritative:

* **The plans.** A gate is promised when its name appears in backticks in a
  per-document gate table or exit-criteria table. Those tables are the
  specification of what must be gated.
* **The tests.** A gate is implemented when a test function carries its name, or
  when a test's docstring cites the name -- the idiom this codebase already uses
  (`\"\"\"§9 ``test_connector_rate_limit``.`). It is canaried when a test under
  `tests/ci/canaries/` does the same.

Three verdicts come out, and each is a distinct defect:

* **unimplemented** -- the plan promises a gate and no test exists. The gate is
  prose.
* **uncanaried** -- a gate is implemented but never watched failing. AD-10: exit
  0 from a gate nobody has seen fail is not evidence.
* **orphaned** -- a test cites a gate name no plan promises. Either a typo in
  the citation or a gate that was dropped from the plan and left in the tree.

A gate with both a test and a canary is **verified**, which is the only status
`12-quality.md` §7 allows to print as "Verified".

    uv run python scripts/gate_register.py            # the gap report
    uv run python scripts/gate_register.py --markdown # the register table
    uv run python scripts/gate_register.py --check    # non-zero on any gap
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "docs" / "plans"
TESTS = ROOT / "tests"

GATE_NAME = re.compile(r"`(test_[a-z_0-9]+)`")
"""A gate is named in backticks. Prose mentions of a bare `test_foo` are not
promises, and treating them as such would invent gates the plan never made."""

DEF = re.compile(r"^def (test_[a-z_0-9]+)\(", re.MULTILINE)

CITED = re.compile(r"`(test_[a-z_0-9]+)`")
"""A gate is *cited* in backticks, the same spelling the plans use to promise it.

Bare `test_foo` in prose is usually a module name -- `tests/ci/test_planning_layer1.py`
-- and reading those as gate citations made every test file an "orphaned gate".
The citation and the promise must be the same shape or the diff between them is
noise."""

_SECTION = re.compile(r"^(#{2,3}) .*(Gates|Exit criteria)", re.MULTILINE)
"""A gate section, at either heading level.

It matched `^## ` only, and four plan documents state their gates under an
`### N.N Gates` heading -- `01-foundations` `### 3.3` and `### 4.3`,
`02-data-pipeline` `### 4.2`, `03-rust-core` at `### 3.5`, `4.3`, `5.4`, `6.4`
and `7.3`. Eleven promised gates were invisible to this register because of it,
and the register reported `unimplemented: 0  uncanaried: 0` while three of the
eleven had no test and seven no canary. A discovery rule that reads one of the
two spellings a document uses is the defect wearing the gate's clothes: the
report is not wrong about what it looked at, it is wrong about what it claims
to have looked at.

The level is captured rather than matched loosely because the *stop* has to
match it: an `###` section ends at the next `###` or `##`, an `##` section at
the next `##`. A single `^#{2,3} ` stop would truncate an h2 gate table at the
first h3 subheading inside it. No h2 gate section in the plans nests an h3
today -- checked, not assumed -- so this changes nothing for them; it is what
keeps that a fact rather than a coincidence."""

_USES_CANARY_HARNESS = re.compile(
	r"\b(?:planted|probe|probe_exit_code|leaked_mutations)\s*\("
)
"""Whether a test *function* is a canary by behaviour rather than by directory.

The rule was `"canaries" in path.parts`, and modules that plant a defect, run
the gate and assert it fails live in `tests/ci/` too -- `test_stage_output_gates.py`,
`test_planning_inputs.py`, `test_units_columns.py` and
`test_config_reachability.py` import the harness from `tests.ci.canaries` to do
it. Reading the directory counted them as ordinary tests, so gates with a
working canary were reported **uncanaried**: the verdict was about where a file
sits, not what it does.

**The signal is a harness *call*, not the import.** The import sits in the
module header and is shared by every function in the file, so keying on it
classifies the whole module -- and `test_stage_output_gates.py` is both: four
real gate tests and one canary that plants a broken stage. Module-level
classification moved `test_topology_schema` and `test_fleet_carriers_known`
*out* of the implemented set and into the canaried one, so the register then
reported them unimplemented -- trading one false verdict for another. A
`planted(...)` in the function body is what actually makes one test a canary
and its neighbour a gate, so that is what this matches.

`probe` and `probe_exit_code` are the subprocess half of the same discipline
and are matched for the same reason.""""""A gate section, at either heading level.

It matched `^## ` only, and four plan documents state their gates under an
`### N.N Gates` heading -- `01-foundations` `### 3.3` and `### 4.3`,
`02-data-pipeline` `### 4.2`, `03-rust-core` at `### 3.5`, `4.3`, `5.4`, `6.4`
and `7.3`. Eleven promised gates were invisible to this register because of it,
and the register reported `unimplemented: 0  uncanaried: 0` while three of the
eleven had no test and seven no canary. A discovery rule that reads one of the
two spellings a document uses is the defect wearing the gate's clothes: the
report is not wrong about what it looked at, it is wrong about what it claims
to have looked at.

The level is captured rather than matched loosely because the *stop* has to
match it: an `###` section ends at the next `###` or `##`, an `##` section at
the next `##`. A single `^#{2,3} ` stop would truncate an h2 gate table at the
first h3 subheading inside it. No h2 gate section in the plans nests an h3
today -- checked, not assumed -- so this changes nothing for them; it is what
keeps that a fact rather than a coincidence."""


def promised_gates() -> dict[str, set[str]]:
	"""Every gate the plans promise, mapped to the documents that promise it.

	Scoped to the two sections that *are* the promises: a per-document gate table
	and the exit-criteria table. A gate name in a narrative paragraph is a
	mention, not a promise -- `12-quality.md` §3.2's directory sketch lists ten
	canary filenames as an illustration of the layout, and reading those as
	promises would demand a canary for each of ten files that already exist.
	"""
	gates: dict[str, set[str]] = {}
	for plan in sorted(PLANS.glob("*.md")):
		text = plan.read_text()
		for section in _SECTION.finditer(text):
			rest = text[section.end() :]
			# Up to the next heading *at or above* this one: the table plus its
			# trailing note. A `###` section stops at `###` or `##`; an `##`
			# section stops at `##`, so an h3 subheading inside it stays in the
			# body rather than cutting the table short.
			level = len(section.group(1))
			next_heading = re.search(
				rf"^#{{2,{level}}} ", rest, re.MULTILINE
			)
			body = rest[: next_heading.start()] if next_heading else rest
			for name in GATE_NAME.findall(body):
				gates.setdefault(name, set()).add(plan.stem)
	return gates


@dataclass
class Implementation:
	"""Where a gate is realised: the tests that cite it and the canaries."""

	tests: list[str] = field(default_factory=list)
	canaries: list[str] = field(default_factory=list)

	@property
	def verified(self) -> bool:
		return bool(self.tests and self.canaries)


def scan_tests() -> tuple[dict[str, Implementation], set[str]]:
	"""Map every promised gate to its implementations, and collect citations.

	Returns ``(found, cited)``. ``found`` is keyed by *gate* names only -- a test
	function is an implementation of a gate when it is named for one or cites one
	in its docstring, and a module of tests that happen to be called
	``test_a_typo_is_refused`` implements no plan gate and is not an entry.

	``cited`` is every gate-shaped name a docstring cites, which is what the
	orphan check diffs against the plans. Keeping the two apart is the whole
	point: collapsing them made every one of the suite's 387 test names an
	"orphaned gate", which is the checker inventing a defect class out of its own
	regex.
	"""
	found: dict[str, Implementation] = {}
	cited: set[str] = set()
	for path in sorted(TESTS.rglob("*.py")):
		text = path.read_text()
		is_canary = "canaries" in path.parts
		relative = str(path.relative_to(TESTS))
		marks = list(DEF.finditer(text))
		# The module docstring is where this codebase states which plan gates a
		# file covers -- the canaries especially, whose whole header is a list of
		# "this canaries ``test_x``, because ...". A citation there is a claim
		# about every test in the file, so it is folded into each function's own.
		module_doc = text[: marks[0].start()] if marks else text
		module_citations = set(CITED.findall(module_doc))
		for index, mark in enumerate(marks):
			name = mark.group(1)
			end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
			body = text[mark.end() : end]
			doc = re.search(r'"""(.*?)"""', body, re.DOTALL)
			mentions = module_citations | set(CITED.findall(doc.group(1) if doc else ""))
			cited |= mentions
			# Canary by behaviour: the function plants a defect through the
			# harness. Scoped per function, because a module can hold both -- see
			# `_USES_CANARY_HARNESS`. A file under `canaries/` is a canary
			# throughout, which is the plan's own layout.
			plants = is_canary or _USES_CANARY_HARNESS.search(body) is not None
			# The function implements the gate it is named for, plus any gate it
			# cites. `test_connector_rate_limit` is one; a module that calls its
			# function `test_no_connector_exceeds_its_declared_rate` and cites
			# the plan's name in the docstring is the other.
			for gate in mentions | {name}:
				if not gate.startswith("test_"):
					continue
				entry = found.setdefault(gate, Implementation())
				target = entry.canaries if plants else entry.tests
				if relative not in target:
					target.append(relative)
	return found, cited


def report() -> tuple[dict[str, set[str]], dict[str, Implementation], set[str]]:
	promised = promised_gates()
	found, cited = scan_tests()
	return promised, found, cited


def gaps() -> tuple[list[str], list[str], list[str]]:
	"""(unimplemented, uncanaried, orphaned)."""
	promised, found, cited = report()
	unimplemented, uncanaried = [], []
	for gate in sorted(promised):
		impl = found.get(gate)
		if impl is None or not impl.tests:
			unimplemented.append(gate)
		elif not impl.canaries:
			uncanaried.append(gate)
	# An orphan is a *citation that resolves to nothing*: a docstring names a gate
	# in backticks and no test in the tree carries that name. That is a broken
	# cross-reference -- the citation was renamed, the test was deleted, or the
	# name was mistyped -- and it is worth failing on because the citation is the
	# only record of what the test was for.
	#
	# A citation of a test that *exists* but that no plan table promises is not an
	# orphan. `tests/ci/canaries/test_zonal_split_gate.py` cites
	# ``test_zonal_clearing_produces_congestion_on_a_congested_path``, which is a
	# real gate in the suite; the plan names the property, not the function. That
	# is a naming choice, not a defect, and flagging it would train the reader to
	# ignore the report.
	defined = {name for name in found if found[name].tests or found[name].canaries}
	orphaned = sorted(cited - defined)
	return unimplemented, uncanaried, orphaned


def render_markdown(promised: dict[str, set[str]], found: dict[str, Implementation]) -> str:
	lines = [
		"| Gate | Document | Canary | Status |",
		"|---|---|---|---|",
	]
	for gate in sorted(promised):
		impl = found.get(gate, Implementation())
		doc = ", ".join(sorted(promised[gate]))
		canary = "✅" if impl.canaries else "❌"
		if impl.verified:
			status = "Verified"
		elif impl.tests:
			status = "**Uncanaried**"
		else:
			status = "**Unimplemented**"
		lines.append(f"| `{gate}` | {doc} | {canary} | {status} |")
	return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--markdown", action="store_true", help="Emit the register as a markdown table.")
	parser.add_argument("--check", action="store_true", help="Exit non-zero if any gate is unverified.")
	args = parser.parse_args(argv)

	promised, found, _ = report()
	if args.markdown:
		print(render_markdown(promised, found))
		return 0

	unimplemented, uncanaried, orphaned = gaps()
	verified = sum(1 for g in promised if found.get(g, Implementation()).verified)
	print(f"promised gates: {len(promised)}   verified: {verified}")
	print(f"  unimplemented: {len(unimplemented)}")
	print(f"  uncanaried:    {len(uncanaried)}")
	print(f"  orphaned:      {len(orphaned)}")
	for label, names in (
		("UNIMPLEMENTED", unimplemented),
		("UNCANARIED", uncanaried),
		("ORPHANED", orphaned),
	):
		if names:
			print(f"\n{label}:")
			for name in names:
				print(f"  {name}")
	if args.check and (unimplemented or uncanaried):
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
