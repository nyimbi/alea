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
import shutil
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
	"capacity_update",
	"costs",
	"critical_lines",
	"cutout",
	"demand_hourly",
	"demand_national",
	"fleet",
	"fuel_prices",
	"generation_mix",
	"hydro_profiles",
	"loss_decomposition",
	"market_capture_rates",
	"market_outlook",
	"market_prices",
	"market_report",
	"market_summary",
	"network_arrays",
	"outage_forecast",
	"outage_history",
	"outage_truth",
	"policy_tracker",
	"price_forecast",
	"renewable_forecast",
	"renewable_profiles",
	"resilience_contingency",
	"sector_coupling",
	"system_alerts",
	"tlens",
	"topology",
	"week_ahead",
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
	"outage_forecast": ".parquet",
	"outage_history": ".parquet",
	"outage_truth": ".parquet",
	"network_arrays": ".json",
	"tlens": ".json",
	"critical_lines": ".parquet",
	"loss_decomposition": ".parquet",
	"capacity_update": ".parquet",
	"market_outlook": ".parquet",
	"market_report": ".parquet",
	"market_summary": ".parquet",
	"generation_mix": ".parquet",
	"policy_tracker": ".parquet",
	"price_forecast": ".parquet",
	"renewable_forecast": ".parquet",
	"sector_coupling": ".json",
	"system_alerts": ".parquet",
	"week_ahead": ".parquet",
}

#: The report projections: a stage's processed artefact, landed at the dated
#: path a report section reads. Keyed by rule name to the section slug.
#:
#: A distinct set from `STAGES` because the two answer different questions.
#: `STAGES` are datasets under `paths.processed`; a projection is a *delivery*,
#: and its output is a dated path under `paths.results` that moves with the
#: cadence's period. Nothing wrote one until this set existed, which is why
#: `alea report monthly` raised "no artefact" while the producing rule exited 0.
PROJECTIONS = {
	"project_capacity_update": "capacity_update",
	"project_critical_lines": "critical_lines",
	"project_market_report": "market_report",
	"project_market_outlook": "market_outlook",
	"project_market_summary": "market_summary",
	"project_generation_mix": "generation_mix",
	"project_loss_decomposition": "loss_decomposition",
	"project_loss_statistics": "loss_statistics",
	"project_policy_tracker": "policy_tracker",
	"project_price_forecast": "price_forecast",
	"project_renewable_forecast": "renewable_forecast",
	"project_outage_forecast": "outage_forecast",
	"project_system_alerts": "system_alerts",
	"project_week_ahead": "week_ahead",
}

#: The section pattern each projection writes, mirrored from the cadence module
#: that declares it. A literal here for the same reason `SUFFIXES` is: the
#: comparison is that the two spellings agree.
PROJECTION_PATTERNS = {
	"project_capacity_update": "planning/capacity/{date}.parquet",
	"project_critical_lines": "outages/critical/{date}.parquet",
	"project_market_report": "market/monthly/{date}.parquet",
	"project_market_outlook": "market/outlook/{date}.parquet",
	"project_market_summary": "market/summary/{date}.parquet",
	"project_generation_mix": "planning/dispatch/{date}.parquet",
	"project_loss_decomposition": "losses/decomposition/{date}.parquet",
	"project_loss_statistics": "losses/monthly/{date}.parquet",
	"project_policy_tracker": "scanning/policy/{date}.parquet",
	"project_price_forecast": "market/prices/{date}.parquet",
	"project_renewable_forecast": "weather/renewables/{date}.parquet",
	"project_outage_forecast": "outages/forecast/{date}.parquet",
	"project_system_alerts": "outages/contingency/{date}.parquet",
	"project_week_ahead": "planning/outlook/{date}.parquet",
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


def test_the_workflow_parses():
	"""The Snakefile builds a DAG, which is a stronger claim than "a rule exists".

	Every other gate here reads the ``.smk`` files as *text*: `_declared_rules`
	regexes the rule names out, and `SUFFIXES` is a literal copy of
	`rules/common.smk`'s. So a stage whose suffix is missing from
	``common.smk``'s map parses fine in the test and raises ``KeyError`` inside
	``processed()`` when Snakemake actually loads the file -- and because the
	test's own copy drifted in step, both agreed with each other and neither
	agreed with the workflow.

	That is not hypothetical. `week_ahead` shipped without a ``SUFFIXES`` entry,
	`market_summary` was added beside it, and `snakemake -n` exited on
	``KeyError: 'market_summary'`` in `rules/common.smk` line 168 while every
	gate in this file passed. A gate that reads a file's text is not a gate that
	the file works, so this one runs the parser.

	``-n`` (dry run) so nothing executes: the claim is that the workflow
	*loads* and resolves its DAG, not that its jobs succeed.
	"""
	snakemake = shutil.which("snakemake")
	if snakemake is None:  # pragma: no cover - depends on the environment
		pytest.skip("snakemake is not on PATH")
	result = subprocess.run(
		[snakemake, "-n", "--quiet"],
		capture_output=True,
		text=True,
		cwd=REPO_ROOT,
		timeout=600,
	)
	assert result.returncode == 0, (
		"the workflow does not parse; `snakemake -n` exited "
		f"{result.returncode}.\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
	)


def test_every_stage_has_a_dvc_stage():
	"""`dvc repro` must be able to rebuild every dataset Snakemake can."""
	stages = yaml.safe_load((REPO_ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
	missing = sorted(set(STAGES) - set(stages))
	assert not missing, f"no DVC stage declares these datasets: {missing}"
	extra = sorted(set(stages) - set[str](STAGES) - set[str](PROJECTIONS))
	assert not extra, (
		f"dvc.yaml declares stages the registry does not hold: {extra}. `dvc repro` "
		f"would run a command the CLI refuses."
	)


def test_every_projection_has_a_snakemake_rule_and_a_dvc_stage():
	"""A projection with no rule delivers nothing, and nothing says so.

	The whole defect this set exists for: `reporting.producers.PRODUCERS` named
	a producer, the producer's rule ran and exited 0, and the section's dated
	path was still absent -- so the report raised. A projection is the missing
	step, and one that exists in only one of the two workflow files is a
	delivery that happens under `snakemake` and not under `dvc repro`.
	"""
	declared = _declared_rules(_smk_text())
	missing_rules = sorted(set(PROJECTIONS) - declared)
	assert not missing_rules, f"no Snakemake rule declares these projections: {missing_rules}"
	stages = yaml.safe_load((REPO_ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
	missing_dvc = sorted(set(PROJECTIONS) - set(stages))
	assert not missing_dvc, f"no DVC stage declares these projections: {missing_dvc}"


def test_a_projection_writes_the_pattern_its_section_declares():
	"""The projection's destination is the section's own declaration.

	The rule writes a directory (the filename is the cadence's period end, which
	moves with the clock) and `alea project` resolves the file inside it from the
	section's ``artefact``. So the directory the rule declares must be the one
	the cadence module's pattern lives in -- a projection writing elsewhere is a
	file no report reads, which is the defect and not a variant of it.
	"""
	from alea.reporting.schemas import ReportCadence
	from alea.reporting.service import cadence_specs

	by_slug: dict[str, str] = {}
	for cadence in ReportCadence:
		specs, _ = cadence_specs(cadence)
		by_slug.update({spec.slug: spec.artefact for spec in specs})

	for rule, slug in PROJECTIONS.items():
		assert slug in by_slug, (
			f"{rule} projects {slug!r}, which no cadence declares"
		)
		declared = by_slug[slug]
		mirrored = PROJECTION_PATTERNS[rule]
		assert declared == mirrored, (
			f"{rule}: the cadence declares {declared!r} and this test mirrors "
			f"{mirrored!r}; the projection would write where no reader looks"
		)
		directory = declared.rsplit("/", 1)[0]
		# The rule declares the *directory* through `report_artefact`, which
		# builds it from the section's own pattern -- so the rule body must carry
		# that pattern, and `results/<dir>` is what `report_artefact` evaluates
		# it to. Both halves are asserted: a rule that spelled the directory by
		# hand would agree today and drift the moment the cadence moves a section.
		block = _rule_blocks(_smk_text()).get(rule, "")
		assert "report_artefact(" in block and f'"{declared}"' in block, (
			f"{rule}: the rule must declare its output through "
			f"`report_artefact` with the section's pattern {declared!r}; it "
			f"declares {block.strip()[:200]!r}"
		)
		expected = f"results/{directory}"
		dvc_outs = yaml.safe_load(
			(REPO_ROOT / "dvc.yaml").read_text(encoding="utf-8")
		)["stages"][rule]["outs"]
		assert expected in {str(out) for out in dvc_outs}, (
			f"{rule}: dvc.yaml outs {dvc_outs} do not name {expected}"
		)


def test_the_projection_register_and_the_workflow_declare_the_same_set():
	"""Both directions, because a projection is a delivery in two places at once.

	The register answers "is this section delivered"; the rule files answer
	"does anything deliver it". If the register named a projection no rule
	declares, the register would overstate coverage -- which is the original
	defect, restated. If a rule declared a projection the register does not
	name, the register would understate it and a reader would go looking for a
	gap that is closed.

	**Read against the rule files, not against `PROJECTIONS`.** The first
	version of this gate compared the register to the dict above, and both are
	literals in this repository -- so it agreed by construction and the canary
	that renames a rule in `rules/reporting.smk` left it green. That is the
	"two files that agree today are not one source of truth" failure, and it is
	why the left-hand side here is scraped from the `.smk` files: a rule that is
	renamed, deleted, or added must move the register or fail this.
	"""
	from alea.reporting.producers import PRODUCERS, PROJECTED, UNPROJECTED

	declared = _declared_rules(_smk_text())
	# The convention the rule names follow, and the only way to enumerate
	# projections from the workflow side: `PROJECTIONS` maps them, but a rule
	# added to a `.smk` file and not to that map is exactly what this catches.
	declared_projections = {name for name in declared if name.startswith("project_")}
	register_rules = set(PROJECTED.values())

	assert declared_projections == register_rules, (
		f"the workflow declares the projection rules {sorted(declared_projections)} "
		f"and `PROJECTED` names {sorted(register_rules)}. A rule in one and not "
		f"the other is either a section recorded as delivered with nothing "
		f"delivering it, or a delivery nothing records"
	)
	assert set(PROJECTIONS) == declared_projections, (
		f"this file's `PROJECTIONS` mirror names {sorted(set(PROJECTIONS))} and "
		f"the rule files declare {sorted(declared_projections)}; the mirror is "
		f"what the pattern check below reads, so a rule it does not name has its "
		f"output unchecked"
	)
	for slug, rule in PROJECTED.items():
		assert PROJECTIONS.get(rule) == slug, (
			f"`PROJECTED` pairs {slug!r} with {rule!r} and this file pairs it "
			f"with {PROJECTIONS.get(rule)!r}; the two must agree on what a rule "
			f"projects or the pattern check below is checking the wrong section"
		)
	assert set(PROJECTED) | set(UNPROJECTED) == set(PRODUCERS), (
		"the projection registers do not partition `PRODUCERS`; a produced "
		"section is either recorded as delivered or has its blocker named"
	)


def test_every_projection_names_the_cadence_that_declares_its_section():
	"""The cadence in the rule's command is the one that declares the section.

	A projection rule carries the cadence twice, and only one of the two is
	load-bearing. ``report_artefact(cadence, pattern)`` builds the output
	directory from ``pattern`` alone -- its first argument is documentation --
	while ``alea project <cadence> <slug>`` passes the cadence to
	`project_section`, which resolves the section by slug *within that cadence*
	and raises if the cadence does not declare it.

	So a rule naming the wrong cadence has a correct-looking output and a command
	that fails at report time. For a required section that is a loud failure; for
	an optional one it is a section that warns "no artefact" in every published
	report while its rule exits 0 -- which is precisely how `generation_mix` and
	`price_forecast` stayed absent. This gate makes the pairing static: the
	cadence in the command must be one whose module declares the slug the
	register pairs the rule with.
	"""
	from alea.reporting.schemas import ReportCadence
	from alea.reporting.service import cadence_specs

	declares: dict[str, set[str]] = {}
	for cadence in ReportCadence:
		specs, _ = cadence_specs(cadence)
		declares[cadence.value] = {spec.slug for spec in specs}

	blocks = _rule_blocks(_smk_text())
	for rule, slug in PROJECTIONS.items():
		block = blocks.get(rule, "")
		match = re.search(r'"project",\s*"([a-z]+)",\s*"([a-z_]+)"', block)
		assert match, (
			f"{rule}: no `alea project <cadence> <slug>` command in the rule block; "
			f"the projection cannot run and the register says it does"
		)
		named_cadence, named_slug = match.group(1), match.group(2)
		assert named_slug == slug, (
			f"{rule}: the command projects {named_slug!r} and the register pairs "
			f"the rule with {slug!r}; the pattern check would pass either way, "
			f"because `report_artefact` builds its directory from the pattern "
			f"alone"
		)
		assert named_cadence in declares, (
			f"{rule}: the command names cadence {named_cadence!r}, which is not "
			f"one of {sorted(declares)}"
		)
		assert slug in declares[named_cadence], (
			f"{rule}: `alea project {named_cadence} {slug}` would raise, because "
			f"the {named_cadence} cadence does not declare {slug!r} -- it declares "
			f"{sorted(declares[named_cadence])}. The rule's output would still "
			f"look correct, since `report_artefact` builds it from the pattern "
			f"and ignores its cadence argument"
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
		"reads the detector's zone series and the GridWatch truth and writes a "
		"JSON skip-or-metrics document to a caller-chosen path, so no rule "
		"declares it and no tracked output carries it. It is not a rule away: "
		"`validate_detector` returns one aggregate `DetectionMetrics`, the "
		"serving table is per zone, and the truth artefact is per sensor with no "
		"zone column. The served granularity is a product decision first."
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
}


def test_every_registered_stage_is_a_rule_or_a_named_exception():
	"""A stage the workflow never runs is a fact, not an omission.

	`test_every_stage_has_a_snakemake_rule` checks the declared stages have
	rules. It does not check the converse, so a builder can register, be reachable
	from `alea build`, and be run by nothing -- which is
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
