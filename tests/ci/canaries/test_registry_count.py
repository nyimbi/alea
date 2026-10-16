# SPDX-License-Identifier: MIT
"""Canaries for the country registry: the count, and the tiers behind it.

A country registry that silently holds 54 produces a continental total missing a
country and says nothing. The count is the gate; the first canary plants a
missing member and asserts the count notices.

The second canary is the one this registry exists for. The registry is generated
from the *per-country tables* of ``spec/data-completeness.md`` because that
file's summary table contradicts its own body -- it reports HIGH 5 / MEDIUM 32 /
LOW 7 against tables holding 6/34/8, and places Equatorial Guinea in MEDIUM where
its own tables put it in LOW. Every one of those defects preserves the total, so
a count is blind to all of them, and the tier gate is asserted by membership
against the plan's §3.1 table.

**Every mutation here runs in a subprocess.** An earlier version called
`importlib.reload` in-process, which re-executes the module and builds *new*
``CompletenessTier`` and ``PowerPool`` enum classes -- while ``alea.registry``,
which re-exports them, keeps the old bindings. ``by_tier`` compares with ``is``,
so every lookup afterwards matched nothing: five tests in a different file
failed with `by_tier(HIGH) == set()` and the registry looked empty while
``registry()`` plainly held 55 countries. It is the same class-identity split
that an in-process reload caused in `test_raw_immutability.py`, and the same
fix: the process that mutates the source is not the process that reads it.
"""

from __future__ import annotations

import os
import subprocess
import sys

from alea.registry import AU_MEMBER_STATE_COUNT, registry, tier_counts
from tests.ci.canaries import REPO, planted

#: Prints the registry's shape as JSON. Run in a **fresh interpreter**, because
#: a mutation to a source file cannot reach a module the current one already
#: holds: `planted` rewrites the file and purges the `.pyc`, but `sys.modules`
#: still carries the object the mutation never touched.
_PROBE = """
import json, sys
from alea.registry.countries import registry, tier_counts
from alea.registry.countries import by_power_pool, PowerPool
try:
    counts = {getattr(k, "value", k): v for k, v in tier_counts().items()}
    pools = {pool.value: sorted(c.iso2 for c in by_power_pool(pool)) for pool in PowerPool}
    print(json.dumps({
        "n": len(registry()),
        "tiers": counts,
        "pools": pools,
    }))
except Exception as exc:
    print(f"refused:{type(exc).__name__}:{exc}")
"""


def _probe() -> dict:
	"""The registry's shape, read in a subprocess. Raises if it refused to build."""
	import json

	completed = subprocess.run(
		[sys.executable, "-c", _PROBE],
		capture_output=True,
		text=True,
		check=False,
		env={**os.environ, "PYTHONPATH": str(REPO)},
		cwd=str(REPO),
	)
	assert completed.returncode == 0, completed.stderr
	line = [ln for ln in completed.stdout.splitlines() if ln.strip()][-1].strip()
	assert not line.startswith("refused:"), f"the registry refused to build: {line}"
	return json.loads(line)


def _run_gate(test: str) -> subprocess.CompletedProcess[str]:
	"""Run one gate from `tests/ci/test_registry_countries.py` in a subprocess."""
	return subprocess.run(
		[
			sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
			f"tests/ci/test_registry_countries.py::{test}",
		],
		capture_output=True,
		text=True,
		check=False,
		env={**os.environ, "PYTHONPATH": str(REPO)},
		cwd=str(REPO),
	)


def test_the_registry_holds_every_au_member_state():
	"""The gate's own premise: the shipped registry is the complete set.

	Named for the state of the tree rather than for the plan's gate, because
	this is the control the canaries below measure their defect against. The
	plan's ``test_registry_covers_all_au_members`` is the gate; this asserts the
	tree it passes on.
	"""
	assert len(registry()) == AU_MEMBER_STATE_COUNT == 55


def test_tiers_partition_the_registry():
	"""The premise for ``test_registry_tier_counts_match_tables``."""
	counts = tier_counts()
	assert sum(counts.values()) == AU_MEMBER_STATE_COUNT


def test_dropping_a_country_fails_the_count():
	"""Plant the defect: delete one member row from the table.

	A *deletion*, not a rename. The first version of this canary replaced the
	``"KE"`` row's ISO code with ``"XX"``, which leaves the count at 55 -- so
	the branch that asserted the gate notices a dropped member was never
	entered, and the test passed for a reason unrelated to the count. The gate
	is `_build`'s own check, which raises rather than returning a short
	registry, so the canary has to remove a row and watch it raise.

	The gate this canaries is ``test_registry_covers_all_au_members``, run by
	name below rather than re-measured: a canary that recomputes the count
	itself is a canary of its own arithmetic, not of the gate.
	"""
	source = REPO / "src" / "alea" / "registry" / "countries.py"
	row = '\t("KE", "KEN", "Kenya", PowerPool.EAPP, CompletenessTier.HIGH, 56_433_000),\n'
	assert row in source.read_text(), "canary target not found: no KE row to remove"
	assert _probe()["n"] == 55, "the registry did not start complete"

	with planted(source, row, ""):
		completed = subprocess.run(
			[sys.executable, "-c", _PROBE],
			capture_output=True,
			text=True,
			check=False,
			env={**os.environ, "PYTHONPATH": str(REPO)},
			cwd=str(REPO),
		)
		assert completed.returncode == 0, completed.stderr
		assert "holds 54 countries" in completed.stdout, (
			f"the registry built with a member missing and said nothing: "
			f"{completed.stdout.strip()}"
		)
	assert _probe()["n"] == 55, "the registry was not restored"


def test_moving_a_country_between_tiers_fails_the_tier_gate():
	"""Plant the defect a count cannot see: a country in the wrong tier.

	Equatorial Guinea, because the registry's own docstring names it as the
	country the source summary got wrong. The move is LOW -> MEDIUM, so the
	total stays 55 and the two tiers the source file miscounted are the two that
	move -- exactly the shape of the defect, and invisible to every assertion on
	the sum.

	The *gate itself* is run and asserted, not a re-measurement of the tier
	counts: a proxy that re-implements the check is a canary of the proxy.
	"""
	source = REPO / "src" / "alea" / "registry" / "countries.py"
	shipped = '("GQ", "GNQ", "Equatorial Guinea", PowerPool.CAPP, CompletenessTier.LOW, 1_892_000),'
	moved = '("GQ", "GNQ", "Equatorial Guinea", PowerPool.CAPP, CompletenessTier.MEDIUM, 1_892_000),'
	assert shipped in source.read_text(), "canary target not found: no GQ row to move"

	clean = _run_gate("test_registry_tier_counts_match_tables")
	assert clean.returncode == 0, (
		f"the gate does not pass on the shipped tree, so the canary below would "
		f"prove nothing:\n{clean.stdout[-2000:]}"
	)

	with planted(source, shipped, moved):
		# The count is preserved, which is the whole point: it is what makes a
		# count-only gate blind to this defect.
		shape = _probe()
		assert shape["n"] == 55, "the planted move changed the total, so this is not the test"
		assert shape["tiers"]["low"] == 7 and shape["tiers"]["medium"] == 35, (
			f"the move did not apply: {shape['tiers']}"
		)

		mutated = _run_gate("test_registry_tier_counts_match_tables")
		assert mutated.returncode != 0, (
			"the tier gate passed with a country in the wrong tier; a gate that "
			"only counts is satisfied by any compensating pair of moves"
		)
		assert "missing" in mutated.stdout or "unexpected" in mutated.stdout, (
			f"the gate failed for a reason other than the moved country:\n{mutated.stdout[-2000:]}"
		)
	assert _probe()["tiers"]["low"] == 8, "the registry was not restored"


def test_a_country_in_no_power_pool_without_a_reason_fails_the_gate():
	"""Plant the defect ``test_every_country_has_a_power_pool`` exists for.

	The gate has two halves and this exercises the one a count cannot see. A
	country whose ``power_pool`` is ``NONE`` is a country the continental model
	drops, and §3.3 says the value is legitimate only "with a note" -- so the
	gate asserts the note, not just the enum.

	Algeria, because it is in COMELEC and carries no note: moving it to ``NONE``
	leaves the registry at 55 with every tier unchanged, so the count and tier
	gates stay green and only the pool gate can catch it. That is what makes it
	a canary for *this* gate rather than for the registry in general.

	The move is planted in the row, and the gate is run by name and asserted --
	not re-measured here, because a canary that recomputes the pool set is a
	canary of its own arithmetic.
	"""
	source = REPO / "src" / "alea" / "registry" / "countries.py"
	shipped = '\t("DZ", "DZA", "Algeria", PowerPool.COMELEC, CompletenessTier.MEDIUM, 46_164_000),\n'
	dropped = '\t("DZ", "DZA", "Algeria", PowerPool.NONE, CompletenessTier.MEDIUM, 46_164_000),\n'
	assert shipped in source.read_text(), "canary target not found: no DZ row to move"

	clean = _run_gate("test_every_country_has_a_power_pool")
	assert clean.returncode == 0, (
		f"the gate does not pass on the shipped tree, so the canary below would "
		f"prove nothing:\n{clean.stdout[-2000:]}"
	)

	with planted(source, shipped, dropped):
		shape = _probe()
		assert shape["n"] == 55, "the planted move changed the total, so this is not the test"
		assert "DZ" in shape["pools"]["none"], f"the move did not apply: {shape['pools']['none']}"

		mutated = _run_gate("test_every_country_has_a_power_pool")
		assert mutated.returncode != 0, (
			"the pool gate passed with a country in no power pool and no note; a "
			"country the continental model cannot place was accepted silently"
		)
		assert "no note saying why" in mutated.stdout, (
			f"the gate failed for a reason other than the missing note:\n"
			f"{mutated.stdout[-2000:]}"
		)
	assert "DZ" not in _probe()["pools"]["none"], "the registry was not restored"
