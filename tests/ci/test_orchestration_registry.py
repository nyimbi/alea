# SPDX-License-Identifier: MIT
"""The stage registry is populated, and every stage is reachable from the CLI.

Three gates, each for a defect that is invisible until it is not:

1. **The registry is non-empty after a bare `import alea`.** A registry filled by
   decorators is filled only when the declaring module is imported, and
   ``_REGISTRATION_MODULES`` is a hand-maintained list. The defect this closes
   is on the record: ``alea.io.stages`` declared eleven stages and the CLI
   reported ``unknown stage 'tlens'; registered: none``, because nothing
   imported the module. Run in a subprocess, so the assertion is about a fresh
   interpreter rather than about whatever the test session already imported.

2. **Every registered stage is buildable through the CLI.** A stage the CLI
   cannot reach is a stage no rule can run, and AD-5 makes the CLI the only
   entry point the workflow layer has. This test drives ``alea build <stage>``
   with ``--help``-equivalent introspection rather than by building: building
   needs raw payloads this suite does not have, and the question here is
   reachability, not correctness.

3. **The workflow layer names the same stages the registry does.** A rule for a
   stage that does not exist fails at run time; a stage with no rule is a
   dataset the pipeline cannot produce. Both are silent in a dry run.

Nothing here mocks a stage or a builder. A test that patched ``build_stage``
would prove the patch works.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The eleven processed datasets of `02-data-pipeline.md` §3, plus `cutout` from
# §4's DAG. Literal, not imported from `alea.io.stages`: a test that imports the
# declaring module to learn what it should contain populates the registry as a
# side effect and then asserts against its own import. That is exactly the
# vacuous fixture this file exists to avoid, and it was here -- removing
# `alea.io.stages` from `_REGISTRATION_MODULES` left this test passing, because
# `from alea.io.stages import REGISTERED_STAGE_NAMES` ran the decorators.
EXPECTED_STAGES = (
	"costs",
	"cutout",
	"demand_hourly",
	"demand_national",
	"fleet",
	"fuel_prices",
	"hydro_profiles",
	"outage_history",
	"outage_truth",
	"renewable_profiles",
	"topology",
)


def _run(program: str) -> str:
	"""Run a program in a fresh interpreter and return its stdout.

	``-I`` is not used: the point is to import the *installed* ``alea``, which is
	the editable one from this checkout. A fresh process is enough to make the
	import assertion meaningful.
	"""
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO_ROOT,
	)
	return result.stdout


def test_the_stage_registry_is_non_empty_after_a_bare_import():
	"""The gate: importing the package is enough to populate the registry."""
	output = _run(
		"import alea;"
		"from alea.io.pipeline import registered_stages;"
		"print('\\n'.join(registered_stages()))"
	)
	names = [line for line in output.splitlines() if line.strip()]
	assert names, (
		"a bare `import alea` left the stage registry empty; the @stage "
		"decorators ran only because some other module was imported"
	)


def test_the_quality_stage_is_reachable_from_a_bare_import():
	"""`12-quality.md` §9 criterion 4's stage must register like any other.

	A `@stage` in a module `_REGISTRATION_MODULES` does not name is written,
	decorated and unreachable -- the CLI reports ``unknown stage`` for a function
	whose own file says ``@stage(...)``. The validation-coverage stage is the
	observable for criterion 4, so its reachability is the difference between a
	criterion that is met and one that only looks met.
	"""
	output = _run(
		"from alea.io.pipeline import registered_stages;"
		"import json;"
		"print(json.dumps(registered_stages()))"
	)
	import json

	assert "quality_validation" in set(json.loads(output)), (
		"the quality validation stage did not register; `alea.quality.service` "
		"is missing from `_REGISTRATION_MODULES`"
	)


def test_the_registry_holds_exactly_the_declared_stages():
	"""The registry is the eleven datasets, discovered in a fresh interpreter.

	``EXPECTED_STAGES`` is a literal rather than an import of
	``alea.io.stages.REGISTERED_STAGE_NAMES``. Importing it would run the
	``@stage`` decorators as a side effect and make this assertion circular --
	the check would pass against its own import, not against
	``_REGISTRATION_MODULES``.
	"""
	output = _run(
		"from alea.io.pipeline import registered_stages;"
		"import json;"
		"print(json.dumps(registered_stages()))"
	)
	import json

	registered = set(json.loads(output))
	missing = sorted(set(EXPECTED_STAGES) - registered)
	assert not missing, (
		f"these stages are declared but did not register after a bare "
		f"`import alea`: {missing}. A stage whose module is not in "
		f"`_REGISTRATION_MODULES` registers nothing."
	)


@pytest.mark.parametrize(
	"stage",
	[
		"topology",
		"fleet",
		"demand_national",
		"demand_hourly",
		"cutout",
		"renewable_profiles",
		"hydro_profiles",
		"costs",
		"fuel_prices",
		"outage_history",
		"outage_truth",
	],
)
def test_each_stage_names_a_real_cli_subcommand(stage: str):
	"""``alea build <stage>`` is a command the CLI accepts.

	Driven through Typer's own runner, so the assertion is about the parsed
	command rather than about a string appearing in ``cli.py``. The build is
	expected to fail -- there is no raw payload for it here -- and what is
	asserted is that the failure is *not* "unknown stage", which is the error
	the CLI raises for a name no builder registered.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	runner = CliRunner()
	result = runner.invoke(app, ["build", stage, "--out", f"/tmp/alea-test-{stage}"])
	combined = f"{result.stdout}\n{result.output}"
	assert "unknown stage" not in combined.lower(), (
		f"`alea build {stage}` reported an unknown stage: {combined.strip()[:400]}"
	)


def test_the_cli_rejects_a_stage_no_builder_registered():
	"""The negative half of the gate above.

	Without this, the parametrised test passes for any stage name at all if the
	CLI ever stops validating, and the suite would be asserting that a typo is
	reachable.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	runner = CliRunner()
	result = runner.invoke(app, ["build", "not_a_stage", "--out", "/tmp/alea-test-nope"])
	assert result.exit_code != 0, "the CLI accepted a stage that has no builder"
	assert "unknown stage" in f"{result.stdout}\n{result.output}".lower()
