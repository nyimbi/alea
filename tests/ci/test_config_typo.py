# SPDX-License-Identifier: MIT
"""A misspelled config key is refused at load, not silently defaulted.

`01-foundations` §8 criterion 1. The gate is `extra="forbid"` on the config
models: without it pydantic ignores an unknown key, so `planning_horizons`
typed as `planning_horizonss` loads clean, the default horizons are used, and
the run produces a plausible model of the wrong scenario -- a defect with no
symptom, which is why it is gated.

The canary that watches this gate fail lives in
`tests/ci/canaries/test_config_rejects_typo.py`, where it relaxes the model and
asserts the typo is then swallowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from alea.config.loader import ConfigError, load_config
from alea.config.models import ScenarioConfig
from tests.ci.canaries import REPO

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
