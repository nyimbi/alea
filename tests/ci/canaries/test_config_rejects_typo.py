# SPDX-License-Identifier: MIT
"""Canary: a misspelled config key must be refused, not silently defaulted.

The gate is ``test_a_typo_in_a_config_key_is_refused``, in
`tests/ci/test_config_typo.py`. ``extra="forbid"`` is what implements it.

Without it pydantic ignores an unknown key, so `planning_horizons` typed as
`planning_horizonss` loads clean, the default horizons are used, and the run
produces a plausible model of the wrong scenario. That is a defect with no
symptom, which is why the key it lives in is canaried rather than the config
loader as a whole.

Both canaries here run their gate in a **subprocess** rather than mutating the
module in-process and calling `importlib.reload`. A reload re-executes the
module body, so every class it defines becomes a new object: the
`ConfigError` this file's gate catches, and the `ScenarioConfig` it constructs,
would both be rebound, while every other test module keeps the class it bound
at import time. That is a live leak -- it made `test_config_typo.py` and
`test_reporting_gates.py::test_config_validated_at_load` fail in the full suite
while passing alone, because `pytest.raises(ConfigError)` then catches the
*old* class while `load_config` raises the new one, and the failure reads
`expected ConfigError, got ConfigError`. `probe_exit_code` exists for exactly
this ("the mutation is a source edit, so the gate has to execute in a fresh
interpreter that reads the mutated file") and leaves nothing behind.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

LOADER_PY = REPO / "src" / "alea" / "config" / "loader.py"
BASE_PY = REPO / "src" / "alea" / "config" / "base.py"

BASE = {
	"name": "canary",
	"countries": ["KE"],
	"base_year": 2025,
	"planning_horizons": [2030],
}

#: The gate, as a fresh interpreter sees it. `ScenarioConfig` is resolved
#: through its module at call time rather than imported by name, so the probe
#: reads whatever the tree on disk defines -- which is the whole point when the
#: canary has just rewritten that tree.
_TYPO_GATE = (
	"import sys\n"
	"from pydantic import ValidationError\n"
	"from alea.config import models as models_module\n\n"
	f"typo = {BASE!r} | {{'planning_horizonss': [2030]}}\n"
	"try:\n"
	"	models_module.ScenarioConfig(**typo)\n"
	"except ValidationError:\n"
	"	sys.exit(0)\n"
	"sys.exit(1)\n"
)

_OVERLAY_GATE = (
	"import sys\n"
	"from alea.config import loader\n\n"
	"base = {'scenario': {'base_year': 2025, 'countries': ['KE']}, 'solve': {'solver': 'highs'}}\n"
	"overlay = {'scenario': {'base_year': 2030}}\n"
	"merged = loader.deep_merge(base, overlay)\n"
	"sys.exit(0 if merged['scenario'].get('countries') == ['KE'] else 1)\n"
)


def test_forbidding_extra_keys_is_the_gate():
	"""Plant the defect: relax the model, then watch the gate go blind.

	The canary proper. `extra="forbid"` is asserted to be the thing doing the
	work: with it the typo raises, without it the typo is silently swallowed.
	If both branches behaved the same, the first test would be passing for a
	reason other than the one it names.

	The mutation is on the **base**, not on `models`. `AleaConfig` moved to
	`alea.config.base` so the root model could compose the layer models without
	closing an import cycle, and every config model inherits the setting from
	there -- so a canary that patched `models.py` would find no `extra=` to
	plant, or worse, plant one on a class nobody validates against and report a
	gate that is blind when the gate is fine. The target is the file that
	defines the behaviour, not the file that happens to hold the subclass.
	"""
	# Premise: the gate passes on the untouched tree, so a later non-zero exit
	# is attributable to the mutation rather than to a gate already failing.
	assert probe_exit_code(_TYPO_GATE) == 0, (
		"the typo gate does not pass on the untouched tree, so this canary "
		"cannot attribute a failure to its own mutation"
	)

	with planted(BASE_PY, 'extra="forbid"', 'extra="ignore"'):
		# With `extra="ignore"` the same construction succeeds: the gate is
		# blind. This is the observation the canary exists to make.
		assert probe_exit_code(_TYPO_GATE) != 0, (
			"the gate still refuses the typo with `extra=\"ignore\"` planted; "
			"it is passing for a reason other than the setting it names"
		)

	# And it recovers, or the canary proves the gate can fail but not that it
	# tracks the code -- a permanently-red gate is one nobody reads.
	assert probe_exit_code(_TYPO_GATE) == 0, (
		"the gate did not recover after the mutation was restored"
	)


def test_the_overlay_gate_notices_a_merge_that_replaces_a_sibling():
	"""``test_a_scenario_overlay_deep_merges_without_discarding_siblings`` must notice.

	The gate asserts a scenario overlay preserves its siblings -- the failure
	mode `deep_merge`'s own docstring names: "a solve with the right carbon price
	and the default planning horizons". Making the recursive branch shallow is
	exactly that defect, and it is the one a `dict.update` would produce, so the
	canary plants the thing a hurried implementation would have written rather
	than a corruption of the real one.
	"""
	assert probe_exit_code(_OVERLAY_GATE) == 0, (
		"the overlay gate does not pass on the untouched tree, so this canary "
		"cannot attribute a failure to its own mutation"
	)

	with planted(
		LOADER_PY,
		"\t\t\tout[key] = deep_merge(existing, value)",
		"\t\t\tout[key] = value  # canary: a shallow merge",
	):
		assert probe_exit_code(_OVERLAY_GATE) != 0, (
			"the gate still passes with a shallow merge planted; the overlay is "
			"discarding siblings and the gate is not noticing"
		)

	assert probe_exit_code(_OVERLAY_GATE) == 0, (
		"the gate did not recover after the mutation was restored"
	)
