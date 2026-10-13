# SPDX-License-Identifier: MIT
"""Canaries for the config-reachability gates (`tests/ci/test_config_reachability.py`).

* ``test_the_root_config_composes_every_layer_section`` -- a section re-declared
  in `config.models` rather than imported from the layer, so the root carries a
  copy that drifts from the model the stage reads;
* ``test_the_losses_section_reaches_the_tlens_stage`` -- `_stage_tlens` made to
  construct a bare ``LossConfig()``, the defect as it shipped;
* ``test_the_resilience_section_reaches_the_stage`` -- `_stage_resilience` made
  to construct a bare ``ResilienceConfig()``, likewise;
* ``test_the_logging_section_reaches_the_configured_logger`` and
  ``test_the_logging_level_reaches_the_configured_logger`` -- ``cli.main`` made
  to call ``configure()`` bare, the third instance of the class and the one
  whose setting configures the process rather than a stage;
* and the root field removed outright, which is the weaker half the other three
  exist to go beyond.

The gate's own docstring says the defect has three instances and that the
stronger half is the stage, not the root model. So the canaries are ordered the
same way: the first three plant the defect *in the stage* -- a stage that reads
the section replaced by one that constructs the class defaults, which is what
actually shipped -- and only the last removes the root field.

That ordering matters because the two failures are not the same test. A
field-existence assertion catches the last one and is blind to the first three;
a gate that only ever saw its root field removed would look identical to one
that reads the section.

**The gate runs as the real gate.** Each canary shells out to
``pytest tests/ci/test_config_reachability.py -k <name>`` in a fresh
interpreter. An inline probe that re-read the config would assert the canary's
own reading and say nothing about whether the gate notices -- and the gate is
the artefact the register counts.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

CONFIG_MODELS_PY = REPO / "src" / "alea" / "config" / "models.py"
LOSSES_SERVICE_PY = REPO / "src" / "alea" / "losses" / "service.py"
RESILIENCE_SERVICE_PY = REPO / "src" / "alea" / "resilience" / "service.py"

GATE_FILE = "tests/ci/test_config_reachability.py"


def _gate_exit_code(test: str) -> int:
	"""Exit code of the named gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def _assert_canary(target, old: str, new: str, test: str, reason: str) -> None:
	"""Plant, watch the gate fail, restore, and prove the restore.

	The target assertion is not incidental. A patch that does not apply leaves
	the file untouched, the gate passes against working code, and the canary
	reports a blind gate -- a false alarm about a gate that was never pointed
	anywhere. `planted` asserts it too; this one names the *line* in the message,
	which is what a reader needs when the source has moved.
	"""
	assert old in target.read_text(), (
		f"canary target not found in {target.name}: {old!r}. The gate may already "
		f"be testing a source that has moved, in which case this canary is a no-op."
	)
	assert _gate_exit_code(test) == 0, f"{test} does not pass on the shipped tree"
	with planted(target, old, new):
		assert _gate_exit_code(test) != 0, reason
	assert _gate_exit_code(test) == 0, "the restore was not proven"


# --------------------------------------------------------------------------
# The shipped defect: the stage constructs the defaults
# --------------------------------------------------------------------------


def test_the_gate_catches_a_resilience_stage_that_builds_the_default_section():
	"""`_stage_resilience` passed ``config.resilience``; plant ``ResilienceConfig()``.

	This is the defect as it shipped. §8 calls the interruption threshold config
	"recorded, and reported with the metric", and the stage recorded it -- from
	a freshly constructed default, so the number in the provenance was a
	constant the operator could not move. The root field was *present* for part
	of this: a gate asserting ``hasattr(Config, "resilience")`` passes here and
	is worth nothing.
	"""
	_assert_canary(
		RESILIENCE_SERVICE_PY,
		"\t\tconfig.resilience,\n",
		"\t\tResilienceConfig(),\n",
		"resilience_section",
		"a stage that constructs ResilienceConfig() instead of reading the "
		"configured section still passed the gate, so the gate cannot tell a "
		"reachable parameter from a recorded constant",
	)


def test_the_gate_catches_a_losses_stage_that_builds_the_default_section():
	"""`_stage_tlens` read ``config.losses``; plant a bare ``LossConfig()``.

	The price a mitigation payback divides by and the snapshot length that keeps
	a MW loss from printing as MWh were both unreachable, while the provenance
	recorded them as the run's parameters.
	"""
	_assert_canary(
		LOSSES_SERVICE_PY,
		"\tlosses = config.losses\n",
		"\tlosses = LossConfig()\n",
		"losses_section",
		"a stage that constructs LossConfig() instead of reading the configured "
		"section still passed the gate",
	)


def test_the_gate_catches_a_stage_that_reads_a_section_the_root_does_not_reach():
	"""The other direction: the stage reads ``config.predictive``, root loses it.

	Removing the root field makes the section unreachable, and the stage's
	``getattr`` fallback would hand back the class defaults without saying so.
	The gate must fail on the load, which is the same defect to the operator.
	"""
	_assert_canary(
		CONFIG_MODELS_PY,
		"\tpredictive: PredictiveConfig = Field(default_factory=PredictiveConfig)\n",
		"",
		"predictive_section",
		"a root Config without a `predictive` field still passed the gate, so a "
		"`predictive:` block in YAML would be a load error and nothing noticed",
	)


def test_the_gate_catches_a_root_field_re_declared_instead_of_imported():
	"""A section present but pointing at a *copy* of the layer's model.

	This is the subtle one, and it is why the gate asserts identity rather than
	presence: a second definition of ``ResilienceConfig`` in
	``alea.config.models`` satisfies ``hasattr(Config, "resilience")``, accepts
	the YAML, and drifts from the model the stage imports the moment either is
	edited. Two files that agree today are not one source of truth.
	"""
	original = "\tresilience: ResilienceConfig = Field(default_factory=ResilienceConfig)\n"
	copied = (
		"\tclass ResilienceConfig(AleaConfig):\n"
		"\t\t\"\"\"A second definition, drifted from the layer's.\"\"\"\n"
		"\n"
		"\t\tinterruption_threshold_minutes: float = 5.0\n"
		"\n"
		"\tresilience: ResilienceConfig = Field(default_factory=ResilienceConfig)\n"
	)
	_assert_canary(
		CONFIG_MODELS_PY,
		original,
		copied,
		"root_config_composes",
		"a root Config carrying its own copy of the layer's section model still "
		"passed the gate; the gate checks presence, not identity",
	)


# --------------------------------------------------------------------------
# The logging section: a config that configures the process, not a stage
# --------------------------------------------------------------------------

CLI_PY = REPO / "src" / "alea" / "cli.py"

_MAIN_LOGGING = """	provisional = None
	try:
		provisional = _provisional_config()
	except Exception:  # noqa: BLE001 - a broken config is reported by the command, not here
		provisional = None
	if provisional is not None:
		configure_from(provisional)
	else:
		configure()"""

_BARE_CONFIGURE = "\tconfigure()"


def test_the_gate_catches_a_main_that_ignores_the_config_logging_section():
	"""``main`` called ``configure()`` bare, so the config's logging reached nothing.

	The defect as it shipped. Every config file declares ``logging.level`` and
	``logging.json_output``; ``main`` configured the process from its own
	defaults instead, so a config asking for DEBUG produced an INFO run and the
	only route to a debug log was an environment variable no config file
	mentions.

	Both gates that read this section fail here, which is why they are two
	gates: one watches the renderer, one watches the level, and the pre-fix code
	was wrong about both.
	"""
	_assert_canary(
		CLI_PY,
		_MAIN_LOGGING,
		_BARE_CONFIGURE,
		"logging",
		"a main that configures logging from its own defaults instead of the "
		"config's logging section still passed the gate",
	)


def test_the_gate_catches_a_config_that_is_never_read_from_the_command_line():
	"""``--config`` named a file the logging setup never saw.

	The subtler half, and the one a fix that stopped at ``configure_from`` would
	have shipped: reading ``load_config()`` bare picks up
	``config.default.yaml`` and nothing else, so the flag a user typed had no
	effect on the log level even once ``configure_from`` existed. The gate
	passes the file through ``--config``, so it fails here.
	"""
	_assert_canary(
		CLI_PY,
		"\treturn load_config(config, scenario=scenario, overrides=overrides, require=False)",
		"\treturn load_config(None, scenario=None, overrides=None, require=False)",
		"logging",
		"a main that reads the default config rather than the one --config names "
		"still passed the gate",
	)
