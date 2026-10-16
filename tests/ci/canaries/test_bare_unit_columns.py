# SPDX-License-Identifier: MIT
"""Canary: plant a bare-unit numeric column and watch §2.3's gate fail.

The gate is ``test_no_bare_unit_columns`` in `tests/ci/test_units_columns.py`,
which asserts §2.3's pattern against every numeric column of every declared
schema. This plants the defect the gate exists for -- a column named
``capacity`` where the schema holds ``capacity_mw`` -- and asserts the gate
catches it.

**It runs the gate's own predicate, not a copy.** ``_bare_unit_offenders`` is
imported from the gate's module and called here. The version that lived inside
the gate's file rebuilt the loop by hand, which makes it a canary of its own
copy: widen the gate and the canary keeps passing against the old rule while
reporting that the gate is watched. A canary and the gate it guards have to
share the function that decides.

**In-process, and that is sound here.** The other canaries in this directory
mostly mutate a source file and re-run in a subprocess, because a module the
interpreter already holds cannot see a source change. Nothing on disk is
mutated in this one: `ArtefactSchema` is frozen and `extra="forbid"`, so the
defect is planted by rebuilding the object under test with one column renamed.
There is no already-imported module for a change to fail to reach, so a fresh
interpreter would buy nothing.

Both halves are asserted: the planted column is caught, and the shipped schema
is clean. Without the second, a real defect already present in `FLEET` would
satisfy the first assertion for the wrong reason and the canary would pass
while the gate was failing.
"""

from __future__ import annotations

from alea.planning.schemas import FLEET, ArtefactSchema, ColumnSpec
from tests.ci.test_units_columns import (
	BARE_UNIT,
	_bare_unit_offenders,
	_declares_unit,
	_has_row_unit,
	_states_a_unit,
)


def _with_column(name: str, *, unit: str = "MW") -> ArtefactSchema:
	"""`FLEET` with ``capacity_mw`` renamed to ``name``."""
	return ArtefactSchema(
		name="fleet",
		columns=tuple(
			ColumnSpec(name=name, dtype="float", unit=unit, description="")
			if spec.name == "capacity_mw"
			else spec
			for spec in FLEET.columns
		),
	)


def test_the_bare_unit_gate_fails_on_a_planted_column():
	"""The defect a contributor adding a ``capacity`` column would produce."""
	caught = _bare_unit_offenders({"FLEET": _with_column("capacity")})
	assert caught == ["FLEET.capacity"], (
		f"the planted bare-unit column was not caught; the gate is blind to the "
		f"defect it exists for. Caught: {caught}"
	)

	# The control: the shipped schema is clean. Otherwise a real defect already
	# present would satisfy the assertion above for the wrong reason.
	clean = _bare_unit_offenders({"FLEET": FLEET})
	assert not clean, f"the shipped FLEET schema already carries bare-unit column(s): {clean}"


def test_the_declared_unit_does_not_exempt_a_bare_name():
	"""A column named ``capacity`` with a declared ``unit="MW"`` is still caught.

	The whole reason `_declares_unit` is not consulted by §2.3's pattern rule: a
	reader of the column *list* has to learn the unit without opening the
	schema, and a declared unit on a bare name does not do that.
	"""
	declared_only = _with_column("capacity")
	assert _declares_unit(declared_only, "capacity"), "the planted column does not declare a unit"
	assert BARE_UNIT.match("capacity"), "the planted name does not match §2.3's pattern"
	assert not _has_row_unit(declared_only), (
		"FLEET carries a per-row unit column, so the pattern rule would skip it "
		"entirely and this canary would prove nothing"
	)
	assert _bare_unit_offenders({"FLEET": declared_only}) == ["FLEET.capacity"]


def test_a_blank_declaration_does_not_count_as_stating_a_unit():
	"""The assertion that keeps the wider rule honest.

	`test_every_numeric_column_declares_a_unit_or_spells_one` accepts a declared
	unit as one of the three ways a column states what it is measured in. A
	*blank* string satisfies the field and states nothing, so `_states_a_unit`
	must revoke it -- otherwise the wider rule passes on a schema that declares
	an empty unit.
	"""
	blanked = _with_column("capacity", unit="")
	assert not _states_a_unit(blanked, "capacity"), (
		"a column named `capacity` with a blank declared unit was read as stating "
		"its unit, so the wider rule is blind to it"
	)
