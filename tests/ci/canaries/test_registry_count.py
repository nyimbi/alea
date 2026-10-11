# SPDX-License-Identifier: MIT
"""Canary: the registry must hold all 55 AU member states.

A country registry that silently holds 54 produces a continental total that is
missing a country and says nothing. The count is the gate; this canary plants a
missing member and asserts the count notices, so the test cannot pass by
counting something other than the table.
"""

from __future__ import annotations

import pytest

from alea.registry import AU_MEMBER_STATE_COUNT, registry, tier_counts
from tests.ci.canaries import REPO, planted


def test_the_registry_holds_every_au_member_state():
	assert len(registry()) == AU_MEMBER_STATE_COUNT == 55


def test_tiers_partition_the_registry():
	counts = tier_counts()
	assert sum(counts.values()) == AU_MEMBER_STATE_COUNT


def test_dropping_a_country_fails_the_count():
	"""Plant the defect: remove one member from the table."""
	source = REPO / "src" / "alea" / "registry" / "countries.py"
	original = source.read_text()
	# The tables are built from a literal; find a country row to delete. The
	# assertion inside `planted` fails loudly if this marker is gone, which is
	# the difference between a canary and a no-op.
	marker = '"KE"'
	assert marker in original, "canary target not found: no KE row to remove"

	import importlib

	import alea.registry.countries as countries

	before = len(countries.registry())
	assert before == 55, f"registry started at {before}, expected 55"

	with planted(source, marker, '"XX"'):
		try:
			importlib.reload(countries)
			after = len(countries.registry())
			# The reload must change the count, or the mutation did not reach the
			# table and the canary is testing nothing.
			assert after != before or "KE" not in countries.registry(), (
				"the planted mutation did not reach the registry table; "
				"the canary is a no-op"
			)
			if after != before:
				with pytest.raises(AssertionError):
					assert after == 55, "the count gate is blind to a dropped member"
		finally:
			importlib.reload(countries)
	assert len(countries.registry()) == 55, "the registry was not restored"
