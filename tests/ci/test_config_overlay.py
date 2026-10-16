# SPDX-License-Identifier: MIT
"""`01-foundations` §8 criterion 2: a scenario overlay deep-merges.

`deep_merge` merges mappings recursively. The defect it prevents is stated in
its own docstring: a shallow merge makes a scenario that sets one key silently
discard its siblings, "which is the failure mode that produces a solve with the
right carbon price and the default planning horizons". The test asserts the
sibling-preservation property directly on `deep_merge` and again through
`load_config(..., overrides=[...])`, because the override path is the one a user
actually types and it is a different caller of the same function.

The sequence rule is asserted too: a list *replaces*. Element-wise concatenation
has no defensible meaning for a config (`clusters: [55]` over `[10, 20]` is a
prefix, an append, or an override?), so the overlay wins wholesale, and a test
that only checked the mapping case would leave the sequence rule to be
rediscovered by whoever next merges two configs.
"""

from __future__ import annotations

from alea.config.loader import deep_merge, load_config


def test_a_scenario_overlay_deep_merges_without_discarding_siblings():
	"""The sibling keys survive a merge that touches one of them.

	`scenario.base_year` is the key the overlay sets. Its four siblings --
	`countries`, `clusters`, `planning_horizons` and the nested `predictive.viirs`
	block -- must come through the merge unchanged. A shallow merge returns
	`{"base_year": 2026}` and drops all four, which is exactly the silent
	failure: the run solves with the right base year and the default horizons.
	"""
	base = {
		"scenario": {
			"countries": ["KE"],
			"clusters": [55],
			"planning_horizons": [2030, 2040],
			"base_year": 2025,
		},
		"predictive": {
			"viirs": {
				"bin_size_deg": 5.0,
				"detection_threshold": 0.6,
				"max_cloud_confidence": 0,
			}
		},
	}
	overlay = {"scenario": {"base_year": 2026}}

	merged = deep_merge(base, overlay)

	# The key the overlay set is the overlay's value...
	assert merged["scenario"]["base_year"] == 2026
	# ...and every sibling is still there, with the base's value.
	assert merged["scenario"]["countries"] == ["KE"]
	assert merged["scenario"]["clusters"] == [55]
	assert merged["scenario"]["planning_horizons"] == [2030, 2040]

	# The merge is recursive, not two-level: a nested block the overlay never
	# mentions keeps *all* of its fields, not just the branch that was touched.
	merged_nested = deep_merge(
		base,
		{"predictive": {"viirs": {"detection_threshold": 0.42}}},
	)
	assert merged_nested["predictive"]["viirs"]["detection_threshold"] == 0.42
	assert merged_nested["predictive"]["viirs"]["bin_size_deg"] == 5.0
	assert merged_nested["predictive"]["viirs"]["max_cloud_confidence"] == 0


def test_a_sequence_in_an_overlay_replaces_rather_than_concatenates():
	"""Lists replace wholesale. `[2035]` over `[2030, 2040]` is `[2035]`.

	A concatenating merge gives `[2030, 2040, 2035]`, which is not ascending and
	not the scenario the caller wrote. The rule is the overlay wins.
	"""
	base = {"scenario": {"clusters": [10, 20], "planning_horizons": [2030, 2040]}}
	merged = deep_merge(base, {"scenario": {"clusters": [55]}})

	assert merged["scenario"]["clusters"] == [55]
	# The untouched list is the base's, unchanged -- replacement is per key.
	assert merged["scenario"]["planning_horizons"] == [2030, 2040]


def test_an_override_keeps_the_default_horizons_through_load_config():
	"""The user-facing path: `--set scenario.base_year=2026` on the real config.

	`load_config` merges the default file, the environment file, the scenario
	overlay and the overrides through the same `deep_merge`. Setting one scenario
	key must leave the rest of `scenario:` at its file value -- the failure mode
	is a solve whose horizons are the defaults while the base year is the
	override's, with no error to say so.
	"""
	defaults = load_config()
	assert defaults.scenario.planning_horizons == [2030, 2040, 2050, 2060]
	assert defaults.scenario.clusters == [55]
	assert defaults.scenario.countries == ["KE"]
	assert defaults.predictive.viirs.detection_threshold == 0.6

	config = load_config(overrides=["scenario.base_year=2026"])

	assert config.scenario.base_year == 2026
	# The siblings are the default file's, not dropped and not defaulted.
	assert config.scenario.planning_horizons == [2030, 2040, 2050, 2060]
	assert config.scenario.clusters == [55]
	assert config.scenario.countries == ["KE"]

	# And the rule holds one level deeper on the same call: an override that
	# moves one VIIRS parameter leaves its siblings at their file values.
	nested = load_config(overrides=["predictive.viirs.detection_threshold=0.42"])
	assert nested.predictive.viirs.detection_threshold == 0.42
	assert nested.predictive.viirs.bin_size_deg == 5.0
	assert nested.predictive.viirs.baseline_quantile == 0.25


def test_an_override_sequence_replaces_the_default_through_load_config():
	"""The sequence rule through the user-facing path.

	`--set scenario.planning_horizons=[2035, 2045]` parses the value as YAML, so
	the list arrives as a list and replaces the file's four horizons. The
	scenario config's own `min_length=1` is the only guard; a concatenating merge
	would pass it with the wrong horizons.
	"""
	config = load_config(overrides=["scenario.planning_horizons=[2035, 2045]"])
	assert config.scenario.planning_horizons == [2035, 2045]
	# The untouched scenario keys survive the list replacement.
	assert config.scenario.clusters == [55]
	assert config.scenario.base_year == 2025
