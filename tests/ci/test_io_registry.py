# SPDX-License-Identifier: MIT
"""The source register and its fetchers are reachable from a bare ``import alea``.

A registry populated by decorators is populated only when the declaring module
is imported. The stage registry had exactly this defect -- a stage file saying
``@stage("tlens")`` while the CLI reported ``registered: none`` -- and the
fetcher registry had it too: ten ``@fetcher`` functions in ``alea.io.fetchers``
and ``registered_fetchers()`` returning ``[]``, because nothing imported the
module. These tests are the gate for the class, not for one instance: they
assert the registry is non-empty after a bare import, so a refactor that moves
the import list cannot silently empty it again.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from alea.io.sources import (
	Access,
	fetchable,
	get_fetcher,
	registered_fetchers,
	sources,
)

# The sources the register lists as automated but for which no fetcher is
# implemented yet. Named explicitly rather than discovered, so that implementing
# one fails this test and forces the list to shrink -- an unlisted gap would
# otherwise grow silently.
UNIMPLEMENTED_FETCHERS = {"era5_cutout", "gridwatch", "viirs_vnp46a2"}


def test_the_fetcher_registry_is_non_empty_after_a_bare_import():
	"""The gate: importing the package is enough to populate the registry.

	Run in a subprocess so the assertion is about a *fresh* interpreter, not
	about whatever this test session already imported. A test that passes
	because another test imported the module is the vacuous fixture again.
	"""
	program = (
		"import alea;"
		"from alea.io.sources import registered_fetchers;"
		"print(len(registered_fetchers()))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
	)
	assert int(result.stdout.strip()) > 0, (
		"a bare `import alea` left the fetcher registry empty; the "
		"@fetcher decorators ran only because some other module was imported"
	)


def test_every_registered_fetcher_names_a_registered_source():
	"""A fetcher for an id the register does not hold is a typo that ran."""
	known = set(sources())
	for source_id in registered_fetchers():
		assert source_id in known, f"{source_id!r} has a fetcher but is not registered"


def test_no_registered_fetcher_is_unavailable():
	"""A fetcher for an unavailable source would fetch something withdrawn."""
	for source_id in registered_fetchers():
		assert not sources()[source_id].unavailable


def test_the_unimplemented_fetchers_are_exactly_the_credentialed_and_open_gap():
	"""The register advertises these as automated; they have no fetcher yet.

	``powerplantmatching`` is not in this set: the register marks it
	``Access.MANUAL`` and ``get_fetcher`` refuses a manual source by design, so
	its absence is the contract rather than a gap.
	"""
	registered = set(registered_fetchers())
	missing = {
		source.id
		for source in fetchable()
		if source.id not in registered and source.access is not Access.MANUAL
	}
	assert missing == UNIMPLEMENTED_FETCHERS, (
		f"the fetchable-but-unimplemented set changed: {sorted(missing)}"
	)


def test_get_fetcher_refuses_a_manual_source_by_name():
	"""A manual export has no automated fetcher, and the error says so."""
	manual = [s.id for s in sources().values() if s.access is Access.MANUAL]
	assert manual, "the register no longer marks any source manual; the contract changed"
	with pytest.raises(KeyError, match="manual"):
		get_fetcher(manual[0])


def test_get_fetcher_refuses_an_unknown_source():
	with pytest.raises(KeyError, match="unknown source"):
		get_fetcher("no_such_source")
