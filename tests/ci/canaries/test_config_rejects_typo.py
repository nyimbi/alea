# SPDX-License-Identifier: MIT
"""Canary: a misspelled config key must be refused, not silently defaulted.

`extra="forbid"` is the gate. Without it pydantic ignores an unknown key, so
`planning_horizons` typed as `planning_horizonss` loads clean, the default
horizons are used, and the run produces a plausible model of the wrong scenario.
That is a defect with no symptom, which is why the key it lives in is canaried
rather than the config loader as a whole.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from alea.config.loader import ConfigError, load_config
from alea.config.models import ScenarioConfig
from tests.ci.canaries import REPO, planted

BASE = {
	"name": "canary",
	"countries": ["KE"],
	"base_year": 2025,
	"planning_horizons": [2030],
}


def test_a_typo_in_a_config_key_is_refused():
	with pytest.raises(ValidationError, match="extra_forbidden"):
		ScenarioConfig(**{**BASE, "planning_horizonss": [2030]})


def test_a_typo_in_a_config_file_is_refused(tmp_path: Path):
	config = REPO / "config" / "config.default.yaml"
	original = config.read_text()
	assert "scenario:" in original, "canary target not found"
	# The mutation is on a copy, not the tracked file: a config is an input, and
	# corrupting it in place would race every other test reading it.
	broken = tmp_path / "config.typo.yaml"
	broken.write_text(original.replace("scenario:", "scenariio:", 1))
	with pytest.raises(ConfigError):
		load_config(broken)


def test_forbidding_extra_keys_is_the_gate():
	"""Plant the defect: relax the model, then watch the gate go blind.

	The canary proper. `extra="forbid"` is asserted to be the thing doing the
	work: with it the typo raises, without it the typo is silently swallowed.
	If both branches behaved the same, the first test would be passing for a
	reason other than the one it names.
	"""
	import importlib

	import alea.config.models as models_module

	models = REPO / "src" / "alea" / "config" / "models.py"
	typo = {**BASE, "planning_horizonss": [2030]}

	# The gate, as shipped: the typo is refused.
	with pytest.raises(ValidationError, match="extra_forbidden"):
		models_module.ScenarioConfig(**typo)

	with planted(models, 'extra="forbid"', 'extra="ignore"'):
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
	importlib.reload(models_module)
	with pytest.raises(ValidationError, match="extra_forbidden"):
		models_module.ScenarioConfig(**typo)
