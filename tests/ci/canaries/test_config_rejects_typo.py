# SPDX-License-Identifier: MIT
"""Canary: a misspelled config key must be refused, not silently defaulted.

The gate is ``test_a_typo_in_a_config_key_is_refused``, in
`tests/ci/test_config_typo.py`. ``extra="forbid"`` is what implements it.

Without it pydantic ignores an unknown key, so `planning_horizons` typed as
`planning_horizonss` loads clean, the default horizons are used, and the run
produces a plausible model of the wrong scenario. That is a defect with no
symptom, which is why the key it lives in is canaried rather than the config
loader as a whole.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

from tests.ci.canaries import REPO, planted

LOADER_PY = REPO / "src" / "alea" / "config" / "loader.py"

BASE = {
	"name": "canary",
	"countries": ["KE"],
	"base_year": 2025,
	"planning_horizons": [2030],
}


def test_forbidding_extra_keys_is_the_gate():
	"""Plant the defect: relax the model, then watch the gate go blind.

	The canary proper. `extra="forbid"` is asserted to be the thing doing the
	work: with it the typo raises, without it the typo is silently swallowed.
	If both branches behaved the same, the first test would be passing for a
	reason other than the one it names.
	"""
	import importlib

	import alea.config.base as base_module
	import alea.config.models as models_module

	# The mutation is on the **base**, not on `models`. `AleaConfig` moved to
	# `alea.config.base` so the root model could compose the layer models without
	# closing an import cycle, and every config model inherits the setting from
	# there -- so a canary that patched `models.py` would find no `extra=` to
	# plant, or worse, plant one on a class nobody validates against and report a
	# gate that is blind when the gate is fine. The target is the file that
	# defines the behaviour, not the file that happens to hold the subclass.
	base = REPO / "src" / "alea" / "config" / "base.py"
	typo = {**BASE, "planning_horizonss": [2030]}

	# The gate, as shipped: the typo is refused.
	with pytest.raises(ValidationError, match="extra_forbidden"):
		models_module.ScenarioConfig(**typo)

	with planted(base, 'extra="forbid"', 'extra="ignore"'):
		# Both modules reload: `models` imported `AleaConfig` by name, so
		# reloading the base alone leaves `ScenarioConfig` bound to the old class
		# with the old config.
		importlib.reload(base_module)
		importlib.reload(models_module)
		# With `extra="ignore"` the same construction succeeds: the gate is
		# blind. This is the observation the canary exists to make.
		swallowed = models_module.ScenarioConfig(**typo)
		assert not hasattr(swallowed, "planning_horizonss"), (
			"the mutation did not take effect; the canary is a no-op"
		)
		# And the shipped defaults are used in place of the typo'd key, which is
		# the silent-wrong-scenario defect the gate prevents.
		assert list(swallowed.planning_horizons) == [2030]

	# Reloaded *after* `planted` has restored the file. A reload inside the
	# context manager would re-read the mutated source and leave the module
	# holding `ignore` for every test that follows.
	importlib.reload(base_module)
	importlib.reload(models_module)
	with pytest.raises(ValidationError, match="extra_forbidden"):
		models_module.ScenarioConfig(**typo)


def test_the_overlay_gate_notices_a_merge_that_replaces_a_sibling():
	"""``test_a_scenario_overlay_deep_merges_without_discarding_siblings`` must notice.

	The gate asserts a scenario overlay preserves its siblings -- the failure
	mode `deep_merge`'s own docstring names: "a solve with the right carbon price
	and the default planning horizons". Making the recursive branch shallow is
	exactly that defect, and it is the one a `dict.update` would produce, so the
	canary plants the thing a hurried implementation would have written rather
	than a corruption of the real one.
	"""
	from alea.config import loader

	base = {"scenario": {"base_year": 2025, "countries": ["KE"]}, "solve": {"solver": "highs"}}
	overlay = {"scenario": {"base_year": 2030}}
	assert loader.deep_merge(base, overlay)["scenario"]["countries"] == ["KE"], (
		"the premise failed: the shipped merge already discards siblings"
	)

	with planted(
		LOADER_PY,
		"\t\t\tout[key] = deep_merge(existing, value)",
		"\t\t\tout[key] = value  # canary: a shallow merge",
	):
		importlib.reload(loader)
		merged = loader.deep_merge(base, overlay)
		assert "countries" not in merged["scenario"], (
			"the planted shallow merge did not take effect; the canary is a no-op"
		)

	# Reloaded after `planted` restores, so the module every later test imports
	# is the real one.
	importlib.reload(loader)
	assert loader.deep_merge(base, overlay)["scenario"]["countries"] == ["KE"], (
		"the module did not recover after the canary"
	)
