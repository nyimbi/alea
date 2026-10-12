# SPDX-License-Identifier: MIT
"""The workflow layer and the Python layer must agree about the stages.

Two files describe the same pipeline: `rules/*.smk` is what Snakemake runs and
`dvc.yaml` is what `dvc repro` runs, and both are hand-written. `00-architecture`
is explicit that two files which agree today are not one source of truth, so
these tests read both and assert they name the same eleven stages with the same
inputs and outputs.

The tests are deliberately about *agreement*, not about either file being right:
if both are wrong in the same way, no test here catches it, and that is stated
rather than papered over. What is caught is the drift that happens when someone
adds a stage to one file.

Parsing `.smk` with a regex is a real limitation: a rule that is restructured
into a form the regex does not match would silently drop out of the comparison,
and a missing rule would then read as "not in Snakemake", which fails the test --
loudly, in the safe direction. The alternative, importing Snakemake and building
the DAG, needs a workflow that resolves, and this suite must run without raw
data.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES = REPO_ROOT / "rules"
SNAKEFILE = REPO_ROOT / "Snakefile"

# The processed datasets the workflow produces, from
# `alea.io.stages.REGISTERED_STAGE_NAMES` plus the two layer-4b stages.
# Listed here rather than imported so that a stage silently disappearing from
# the registry fails the comparison instead of shrinking both sides.
STAGES = (
	"costs",
	"cutout",
	"demand_hourly",
	"demand_national",
	"fleet",
	"fuel_prices",
	"hydro_profiles",
	"market_prices",
	"network_arrays",
	"outage_history",
	"outage_truth",
	"renewable_profiles",
	"resilience_contingency",
	"tlens",
	"topology",
)

# `demand_hourly` is the only stage whose rule needs a helper-supplied input
# rather than a literal one, so its rule text is compared by stage name and not
# by dependency string.
RULE_NAMES = STAGES

# The suffix each stage's tracked artefact carries, mirroring `SUFFIXES` in
# `rules/common.smk`. A literal here rather than an import of that file: a
# `.smk` is not importable Python, and the point of the comparison is that the
# two spellings agree.
SUFFIXES = {
	"topology": ".parquet",
	"fleet": ".parquet",
	"demand_national": ".parquet",
	"demand_hourly": ".parquet",
	"cutout": ".nc",
	"renewable_profiles": ".nc",
	"hydro_profiles": ".parquet",
	"costs": ".parquet",
	"fuel_prices": ".parquet",
	"outage_history": ".parquet",
	"outage_truth": ".parquet",
	"network_arrays": ".json",
	"tlens": ".json",
}


def _smk_text() -> str:
	"""Every rule file, concatenated.

	`common.smk` is included: it holds the `missing_input` rule and the helpers
	the other files call, and a stage's rule body is not self-contained without
	it.
	"""
	return "\n".join(
		path.read_text(encoding="utf-8") for path in sorted(RULES.glob("*.smk"))
	)


def _declared_rules(text: str) -> set[str]:
	"""Rule names declared with `rule <name>:` at the start of a line."""
	return set(re.findall(r"^rule\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", text, re.MULTILINE))


def _rule_blocks(text: str) -> dict[str, str]:
	"""``{rule_name: block_text}``, one entry per `rule <name>:` declaration.

	Line-oriented rather than one regex per field: a `.smk` rule is a block of
	tab-indented lines under a header, and matching fields with a single regex
	means the `.*?` has to cross newlines, which either needs `DOTALL` (and then
	overruns into the next rule) or silently matches nothing. Splitting on the
	headers is what the file actually is.

	The header pattern requires an identifier and a colon, so the word "rule"
	inside a docstring -- "the rule declares that file as the profiles' input" --
	is not mistaken for a declaration.
	"""
	blocks: dict[str, str] = {}
	parts = re.split(
		r"^rule\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$", text, flags=re.MULTILINE
	)
	# `re.split` with a capture group interleaves the captured names.
	for index in range(1, len(parts), 2):
		blocks[parts[index]] = parts[index + 1] if index + 1 < len(parts) else ""
	return blocks


def test_the_snakefile_includes_every_rule_file_and_no_missing_one():
	"""An include that does not resolve is a parse error; this names it first."""
	snakefile = SNAKEFILE.read_text(encoding="utf-8")
	included = set(re.findall(r'^include:\s*"([^"]+)"', snakefile, re.MULTILINE))
	assert included, "the Snakefile includes no rule files"
	missing = sorted(path for path in included if not (REPO_ROOT / path).exists())
	assert not missing, f"the Snakefile includes files that do not exist: {missing}"
	on_disk = {
		str(path.relative_to(REPO_ROOT)) for path in sorted(RULES.glob("*.smk"))
	}
	unincluded = sorted(on_disk - included)
	assert not unincluded, (
		f"rule files exist but no `include:` names them: {unincluded}. A rule file "
		f"that is not included is a rule that never runs."
	)


def test_every_stage_has_a_snakemake_rule():
	"""A dataset with no rule is a dataset the workflow cannot produce."""
	declared = _declared_rules(_smk_text())
	missing = sorted(set(STAGES) - declared)
	assert not missing, f"no Snakemake rule declares these stages: {missing}"


def test_every_stage_has_a_dvc_stage():
	"""`dvc repro` must be able to rebuild every dataset Snakemake can."""
	stages = yaml.safe_load((REPO_ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
	missing = sorted(set(STAGES) - set(stages))
	assert not missing, f"no DVC stage declares these datasets: {missing}"
	extra = sorted(set(stages) - set(STAGES))
	assert not extra, (
		f"dvc.yaml declares stages the registry does not hold: {extra}. `dvc repro` "
		f"would run a command the CLI refuses."
	)


def test_snakemake_and_dvc_agree_on_each_stage_s_output():
	"""The two workflow files must name the same artefact for a stage.

	The output is the contract between them: if Snakemake writes
	`data/processed/topology.parquet` and DVC watches something else, `dvc status`
	reports a stage that never rebuilds because its output never appears to
	change.
	"""
	dvc_stages = yaml.safe_load((REPO_ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
	blocks = _rule_blocks(_smk_text())
	disagreements = []
	for stage in STAGES:
		dvc_outs = {str(out) for out in dvc_stages[stage].get("outs", [])}
		block = blocks.get(stage)
		if block is None:
			disagreements.append(f"{stage}: no rule block")
			continue
		# The output entries are double-tab-indented and the block ends at the
		# next single-tab keyword. Matching `output:\n` then `(?:\t+.*\n)+`
		# swallows the whole rest of the rule -- every line in a `.smk` rule is
		# tab-indented -- so `processed(...)` calls from the run body were being
		# read as outputs.
		output_block = re.search(r"^\toutput:\n((?:\t\t.*\n)+)", block, re.MULTILINE)
		if output_block is None:
			disagreements.append(f"{stage}: no output block")
			continue
		body = output_block.group(1)
		# Both spellings of `processed`: one argument, resolved through
		# `SUFFIXES`, and two, where the rule names the suffix itself because the
		# stage's *second* output is not a stage name (`dispatch.parquet` beside
		# `network_arrays.json`). Reading only the first argument silently
		# resolved `processed("dispatch", ".parquet")` to
		# `SUFFIXES["dispatch"]` -- a KeyError, which is at least loud, but the
		# same omission on a name that *was* in `SUFFIXES` would have compared
		# the wrong path and passed.
		pairs = re.findall(
			r'processed\(\s*"([a-z_]+(?:/[a-z_]+)*)"\s*(?:,\s*"([^"]+)")?\s*\)', body
		)
		if not pairs:
			# `cutout` names the `CUTOUT` constant, which is
			# `processed("cutout")` resolved at parse time.
			if "CUTOUT" in body:
				pairs = [(stage, None)]
			else:
				disagreements.append(f"{stage}: rule output names no stage")
				continue
		# An exact artefact, not a prefix. `startswith("data/processed/topology")`
		# is satisfied by `topology.geojson`, and the stem `topology.` is
		# satisfied by it too -- both were tried and both left this gate green
		# when the Parquet was renamed to a typo. The rule's declaration is
		# resolved to an exact path and the DVC outs must name it.
		expected = {
			f"data/processed/{name}{suffix or SUFFIXES[name]}" for name, suffix in pairs
		}
		if stage == "cutout":
			# atlite writes its sidecar beside the NetCDF.
			expected |= {f"{path}.aux" for path in expected}
		unmatched = sorted(expected - dvc_outs)
		if unmatched:
			disagreements.append(
				f"{stage}: the rule declares {sorted(expected)} but dvc.yaml outs "
				f"{sorted(dvc_outs)} do not name {unmatched}"
			)
	assert not disagreements, "; ".join(disagreements)


def test_no_rule_imports_python_from_the_package():
	"""AD-5: a rule shells out to the CLI and never imports `alea`.

	A `from alea... import ...` in a rule body puts Python in the workflow layer
	and makes the rule unrunnable against a different environment -- the exact
	failure AD-5 exists to prevent. `import alea` at parse time is forbidden for
	the same reason.

	The check is on the rule files only. Snakemake's own helpers (`Path`,
	`shlex`) are fine; what is refused is the package under test.
	"""
	offenders = []
	for path in sorted(RULES.glob("*.smk")):
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
			stripped = line.strip()
			if re.match(r"(from|import)\s+alea\b", stripped):
				offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {stripped}")
	assert not offenders, (
		"a rule imports the package it is supposed to call: " + "; ".join(offenders)
	)


def test_every_rule_shells_out_to_the_cli():
	"""Every rule body that does work runs `alea`.

	A rule with a `run:` block but no `shell(alea(...))` is logic in the workflow
	layer, which is what AD-5 forbids. The `missing_input` rule is the exception
	and is named: it raises, and the raise *is* its purpose.
	"""
	text = _smk_text()
	blocks = _rule_blocks(text)
	# `fetch_all` aggregates the per-source rules and has no body of its own;
	# `missing_input` raises, and the raise is its purpose.
	EXEMPT = {"fetch_all", "missing_input"}
	offenders = []
	for name, block in blocks.items():
		if name in EXEMPT:
			continue
		if "run:" not in block:
			offenders.append(f"{name}: no run block")
			continue
		if "alea(" not in block and "shell(" not in block:
			offenders.append(f"{name}: run block calls neither alea() nor shell()")
	assert not offenders, "; ".join(offenders)


def test_the_fetchable_list_matches_the_register():
	"""The literals in `rules/fetch.smk` are the register's fetchable set.

	The rules cannot import `alea` to enumerate this (AD-5), so the list is
	literal and this test is what keeps it true. Both directions are checked: a
	new fetcher that never reaches the workflow, and a rule for a source that
	`alea fetch` would refuse.
	"""
	program = (
		"from alea.io.sources import sources, registered_fetchers, Access;"
		"import json;"
		"print(json.dumps(sorted("
		"  s for s in registered_fetchers()"
		"  if sources()[s].access is not Access.MANUAL and not sources()[s].unavailable"
		")))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO_ROOT,
	)
	import json

	expected = set(json.loads(result.stdout))
	declared = set(
		re.findall(
			r'^\t"([a-z0-9_]+)",$',
			(RULES / "fetch.smk").read_text(encoding="utf-8"),
			re.MULTILINE,
		)
	)
	assert declared == expected, (
		f"rules/fetch.smk declares {sorted(declared)}; the register's "
		f"fetchable-and-implemented set is {sorted(expected)}"
	)


@pytest.mark.parametrize("config_name", ["config/config.kenya.yaml"])
def test_the_default_config_is_one_the_cli_can_load(config_name: str):
	"""The config a rule passes must be a config the CLI accepts.

	A rule that names a config the loader rejects fails every job with a
	configuration error, which reads as a broken pipeline rather than a typo.
	"""
	program = (
		"from alea.config.loader import load_config;"
		f"cfg = load_config('{config_name}', require=True);"
		"print(cfg.scenario.countries)"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO_ROOT,
	)
	assert result.stdout.strip(), "the default config loaded with no countries"


# Stages that register a builder but have no rule, and the reason each is not in
# the workflow. A stage in this set is reachable through `alea build <name>` and
# from no rule; naming it here is what stops the set growing unnoticed.
#
# The distinction from `STAGES` is the one this whole suite is about: `STAGES` is
# what the workflow produces, and a registered stage outside it is a builder the
# pipeline never runs. That is not automatically a defect -- a stage can be
# deliberately manual, or read inputs no producer writes -- but it is a fact that
# must be stated, because an unrun stage and a run one look identical from the
# registry.
STAGES_WITHOUT_RULES: dict[str, str] = {
	"outage_validation": (
		"reads the detector's zone series and the GridWatch truth. Both exist as "
		"artefacts (`outage_history`, `outage_truth`) but the validation writes a "
		"JSON skip-or-metrics document that no rule declares; wiring it needs a "
		"rule and a tracked output, not just an invocation."
	),
	"quality_validation": (
		"reports validation coverage, which is a claim about the tree rather than "
		"a dataset in it. `12-quality.md` §9 criterion 4 reads it directly; making "
		"it a Snakemake target would put a self-referential artefact in `rule all`."
	),
	"resilience": (
		"reads `interruptions.parquet` and `zone_population.parquet`, neither of "
		"which anything writes. A rule for it would fail on its first input, and "
		"the missing producers are a Layer 4 task."
	),
	"sector_coupling": (
		"reads a solved network from `paths.results`, which is produced by "
		"`alea solve` rather than by a stage. Its input is a solved scenario, so "
		"the rule depends on a solve the workflow does not yet sequence."
	),
}


def test_every_registered_stage_is_a_rule_or_a_named_exception():
	"""A stage the workflow never runs is a fact, not an omission.

	`test_every_stage_has_a_snakemake_rule` checks the eleven declared stages
	have rules. It does not check the converse, so a builder can register, be
	reachable from `alea build`, and be run by nothing -- which is
	indistinguishable from a working stage when you read the registry.

	This asserts the two sets agree: every registered stage is either a declared
	workflow stage or named in `STAGES_WITHOUT_RULES` with the reason. The
	registry is read in a fresh interpreter, so a stage that fails to register
	does not silently drop out of the comparison.
	"""
	program = (
		"from alea.io.pipeline import registered_stages;"
		"import json;"
		"print(json.dumps(registered_stages()))"
	)
	result = subprocess.run(
		[sys.executable, "-c", program],
		capture_output=True,
		text=True,
		check=True,
		cwd=REPO_ROOT,
	)
	import json

	registered = set(json.loads(result.stdout))
	assert registered, "no stages registered; the registry import list is broken"

	unnamed = sorted(registered - set(STAGES) - set(STAGES_WITHOUT_RULES))
	assert not unnamed, (
		f"these stages register but are in no rule and in no named exception: "
		f"{unnamed}. `alea build` accepts them and the workflow never runs them, "
		f"which reads as a working stage. Add a rule, or record it in "
		f"`STAGES_WITHOUT_RULES` with the reason."
	)
	stale = sorted(set(STAGES_WITHOUT_RULES) - registered)
	assert not stale, (
		f"`STAGES_WITHOUT_RULES` names stages that do not register: {stale}. The "
		f"exception outlived the stage it excused."
	)
	overlap = sorted(set(STAGES_WITHOUT_RULES) & set(STAGES))
	assert not overlap, (
		f"{overlap} are recorded as having no rule and as workflow stages; the two "
		f"sets must not overlap."
	)
	for stage, reason in STAGES_WITHOUT_RULES.items():
		assert len(reason) > 80, (
			f"the exception for {stage!r} has a reason too short to be one: {reason!r}"
		)
