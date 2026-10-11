# SPDX-License-Identifier: MIT
"""Canary: the additivity gate must read the coupled copy, not the original.

``test_sector_is_additive`` is the structural gate (05-layer2 §6): a sector
layer that changed the electricity network has a coupling bug, and the gate's
job is to tell a coupling bug from a modelling difference. It does that by
comparing a digest of the base network before the layer ran with a digest of the
network the layer returned.

The gate was a tautology. ``after`` was computed as ``base_digest(network)`` --
the *original*, which the layer never writes to -- so ``before == after`` held
no matter what the coupling layer did to the copy it returned. A gate that
cannot fail is indistinguishable from no gate, and this one read as green on
every run while proving nothing.

The two functions below are the wrong and right computations, written out so the
canary asserts the difference rather than trusting it. ``tautological_after`` is
the defect; ``correct_after`` is the fix. A base asset whose value moved must
make ``correct_after`` differ from ``before`` while ``tautological_after`` stays
blind to it.
"""

from __future__ import annotations

import pandas as pd
import pypsa

from alea.sector.coupling import base_digest


def _base_network() -> pypsa.Network:
	network = pypsa.Network()
	network.add("Bus", "KE_elec", carrier="AC")
	network.add("Generator", "base_gen", bus="KE_elec", p_nom=100.0, carrier="AC")
	network.set_snapshots(list(pd.date_range("2030-01-01", periods=4, freq="h")))
	return network


def _mutated_coupled_copy(base: pypsa.Network) -> pypsa.Network:
	"""What a coupling bug looks like: the layer moved a base asset's value."""
	coupled = base.copy()
	coupled.generators.loc["base_gen", "p_nom"] = 999.0
	return coupled


def tautological_after(base: pypsa.Network, coupled: pypsa.Network) -> str:
	"""The defect: digest the original, which the layer never writes to."""
	return base_digest(base)


def correct_after(base: pypsa.Network, coupled: pypsa.Network) -> str:
	"""The fix: digest the coupled copy, restricted to the base's own assets."""
	return base_digest(coupled, restrict_to=base)


def test_the_correct_computation_notices_a_mutated_base_asset():
	base = _base_network()
	coupled = _mutated_coupled_copy(base)
	assert correct_after(base, coupled) != base_digest(base)


def test_the_tautology_is_blind_to_the_same_mutation():
	"""Canary proper. If this ever fails, the original defect has returned."""
	base = _base_network()
	coupled = _mutated_coupled_copy(base)
	before = base_digest(base)
	assert tautological_after(base, coupled) == before, (
		"the old computation now moves on a mutation; the canary no longer "
		"demonstrates the defect it exists to catch"
	)
	assert correct_after(base, coupled) != before, "the fix is blind to the mutation"


def test_the_correct_computation_ignores_assets_the_layer_added():
	"""The gate distinguishes a mutation from a legitimate addition.

	A sector asset on a base table (a generator, a store) is the layer doing its
	job, not a coupling bug, and must not move the restricted digest.
	"""
	base = _base_network()
	coupled = base.copy()
	coupled.add("Generator", "solar_pv", bus="KE_elec", p_nom=5.0, carrier="solar")
	coupled.add("Store", "h2_storage", bus="KE_elec", e_nom=10.0)
	assert correct_after(base, coupled) == base_digest(base)
