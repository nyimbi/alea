# SPDX-License-Identifier: MIT
"""Canary: watch `test_the_route_inventory_sees_every_spec_endpoint` fail.

Exit criterion 9 of Layer 8 (``11-layer8-api.md`` §9) is the one criterion in the
plan with a *history* rather than a rationale. A wrapper class around
``include_router`` once hid 1,074 of 1,080 routes from a static extractor, and
three different wrong counts were each internally consistent -- so the plan's own
text says the inventory must be read from the running application and canaried
against a route known to exist.

The gate under test lives in ``tests/ci/test_api_layer8.py`` and compares the
served path set against §3.1's endpoint table. It has two halves, and they fail
for different reasons:

* **The walk.** ``alea.api.inventory.route_inventory`` descends into FastAPI's
  ``_IncludedRouter`` wrapper. A naive walk over ``app.routes`` reads the
  wrapper's ``path``, which is ``None``, so it reports a small internally
  consistent number and every router's routes are invisible.
* **The comparison.** The gate maps each spec template onto served paths by
  shape. A comparison that matched everything would report an application that
  serves an endpoint it does not.

One canary blinding one line would leave the other half unexercised, which is
the "a gate scoped to the bug you found, not the class it belongs to" failure.
So there are two, on disjoint files, with disjoint mutations.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

INVENTORY = REPO / "src" / "alea" / "api" / "inventory.py"
MARKET = REPO / "src" / "alea" / "api" / "routes" / "market.py"

#: The gate, run in a subprocess so the mutation is read by a fresh interpreter.
#: One node rather than the file: the criterion-9 gate is what is being watched,
#: and the rest of `test_api_layer8.py` builds fixtures this canary does not need.
_GATE = """
import sys
import pytest

sys.exit(pytest.main(["-q", "-p", "no:randomly",
                      "tests/ci/test_api_layer8.py"
                      "::test_the_route_inventory_sees_every_spec_endpoint"]))
"""

#: The unwrap. ``_walk`` reads ``include_context`` only when ``original_router``
#: is present -- that is the branch that descends into a wrapper -- so returning
#: early from it is the smallest edit that makes the walk see the wrappers and
#: nothing they carry.
TARGET = '\t\tcontext = getattr(entry, "include_context", None)'


def test_the_inventory_gate_fails_when_the_walk_stops_unwrapping():
	"""Blind the unwrap; the gate must go red and then green again.

	This is §9's own defect: ``app.routes`` read without the unwrap. The failure
	is raised by ``assert_inventory`` inside ``create_app`` rather than by the
	gate's own comparison, and that is the designed order -- the guard runs
	first precisely so a broken walk is caught before its total is trusted. What
	the canary proves is that a naive walk *is* caught, rather than reporting 5
	routes as a plausible answer.
	"""
	assert INVENTORY.is_file(), f"canary target is not a file: {INVENTORY}"
	before = INVENTORY.read_text()
	assert TARGET in before, (
		"canary target not found: `_walk` no longer reads `include_context`, so "
		"the unwrap this canary blinds has moved and the mutation would be a no-op"
	)

	# Premise: the gate passes on the untouched tree. Without this the canary
	# cannot tell a blinded walk from a gate that was already failing.
	assert probe_exit_code(_GATE) == 0, (
		"the route-inventory gate does not pass on the untouched tree, so this "
		"canary cannot attribute a failure to its own mutation"
	)

	blinded = TARGET.replace(
		"\t\tcontext =", "\t\treturn []  # canary: the unwrap is blinded\n\t\tcontext ="
	)
	with planted(INVENTORY, TARGET, blinded):
		assert probe_exit_code(_GATE) != 0, (
			"the gate still passes with the unwrap removed; the inventory is "
			"reading the wrappers and reporting a total with nothing behind it"
		)

	# And it recovers, or the canary proves the gate can fail but not that it
	# tracks the code -- a permanently-red gate is one nobody reads.
	assert probe_exit_code(_GATE) == 0, (
		"the gate did not recover after the mutation was restored"
	)


def test_the_inventory_gate_fails_when_a_spec_endpoint_is_not_served():
	"""A second, disjoint mutation: a route the spec names is not served.

	Blinding the walk proves the inventory half. This plants a defect the walk
	never sees -- the walk is intact and still reports every route it is given,
	but one of them is no longer at the path §3.1 names -- so the gate's own
	comparison is watched failing too.

	The rename is the smallest edit that makes an endpoint unserved while
	leaving every other guard satisfied: the route count is unchanged, so
	``assert_inventory``'s minimum still holds, and the path is still served, so
	``assert_every_router_mounted`` still finds it. The only thing that can
	notice is the comparison this canary is about.

	The mutation is to a different file from the walk canary's, so the two
	cannot interfere if they ever run concurrently.
	"""
	assert MARKET.is_file(), f"canary target is not a file: {MARKET}"
	before = MARKET.read_text()
	target = '@router.get("/capture-rates"'
	assert target in before, (
		"canary target not found: the capture-rates route is no longer spelled "
		"this way, so this mutation would be a no-op"
	)

	assert probe_exit_code(_GATE) == 0, "premise: the gate passes untouched"

	with planted(MARKET, target, '@router.get("/capture_rate"'):
		assert probe_exit_code(_GATE) != 0, (
			"the gate passes with a §3.1 endpoint no longer served; its "
			"comparison against the spec table is not reading what it claims to"
		)

	assert probe_exit_code(_GATE) == 0, (
		"the gate did not recover after the route path was restored"
	)
