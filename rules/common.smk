# SPDX-License-Identifier: MIT
"""Shared helpers for the ALEA rules.

Every rule in `rules/` calls `alea` and nothing else (AD-5). What lives here is
the handful of decisions that would otherwise be copied into nine files and
drift apart: which config, where the lake is, and the one place that knows how
to invoke the CLI.

Deliberately absent: any import of `alea`. A helper that imports the package
puts Python in the workflow layer and makes a rule unrunnable against a
different environment, which is the whole thing AD-5 forbids. Snakemake itself
is the only Python that runs here, and it runs at parse time.
"""

import shlex
from pathlib import Path

# The environment config. `--config env=...` overrides it. Kenya is the default
# because it is the development target and the country the aggregation
# validation is run against; a workflow whose default is continental tries to
# solve a problem no development machine can hold.
CONFIG = config.get("env", "config/config.kenya.yaml")

# The repository root, for `uv run --directory`, so a rule resolves the same
# interpreter and the same locked dependency set from any working directory.
#
# `workflow.basedir` is the directory holding the Snakefile, which is the
# repository root -- not something to take `.parent` of. It did, and every rule
# ran `uv run --directory /Users/.../src/pjs alea ...`, one level above the
# project, where `uv` finds no `pyproject.toml`. A dry run cannot see this: the
# path is used only when a job executes.
ROOT = Path(workflow.basedir)

# Lake roots, mirroring `PathsConfig` in `src/alea/config/models.py`. Literals
# here rather than read from the config: reading it means importing the loader,
# and a Snakemake output path has to be a string at parse time.
RAW = "data/raw"
PROCESSED = "data/processed"
RESULTS = "results"

# The suffix each processed dataset is written with. `topology` writes a Parquet
# file and a GeoJSON beside it and the Parquet is the tracked one, so the
# extension is declared here rather than inferred from the stage name.
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
	"critical_lines": ".parquet",
	"capacity_update": ".parquet",
	"market_report": ".parquet",
	"market_outlook": ".parquet",
	"generation_mix": ".parquet",
	"price_forecast": ".parquet",
	"sector_coupling": ".json",
}

# The bus weight table `demand_hourly` disaggregates against: population and GDP
# per bus (`02-data-pipeline.md` §3.1). It is not a registered source -- there is
# no fetcher for "the share of Kenya's population at each bus" -- so it is a
# human artefact and lives under `resources/`.
WEIGHTS = "resources/weights/bus_weights.parquet"

# The manual exports, at the paths `_require_raw` resolves a `Access.MANUAL`
# source to. Each is a file a human produces once and commits
# (`02-data-pipeline.md` §1.1); the rule declares it as an input so Snakemake
# refuses to build from a stage whose export is absent rather than letting the
# stage raise after the scheduler has started.
MANUAL_EXPORTS = {
	"powerplantmatching": f"{RAW}/powerplantmatching/manual/powerplants.parquet",
	"afrec_demand": f"{RAW}/afrec_demand/manual/afrec_demand.xlsx",
	"hydro_atlas": f"{RAW}/hydro_atlas/manual/hydro_profiles.parquet",
	"gridwatch": f"{RAW}/gridwatch/manual/gridwatch.csv",
	"irena_costs": f"{RAW}/irena_costs/manual/irena_costs.json",
}

# The solved network the layer-4 stages read. `alea solve` writes
# `{network_id}-{horizon}.nc` here and `@stage("network_arrays")` converts the
# newest one. The id is a content hash, so the filename is not knowable at parse
# time -- hence a directory rather than a path, and `--set network_dir=` rather
# than a declared input. A rule cannot name the file it will read, so the stage
# resolves it and records what it resolved; that is the one place a stage's
# inputs are not a Snakemake dependency.
NETWORKS = f"{RESULTS}/networks"

# The fetch marker `rules/fetch.smk` writes.
FETCH_MARKER = ".fetched"

# Inputs a human supplies, and what to say when one is absent.
#
# `02-data-pipeline.md` §1.1 makes the powerplantmatching and AFREC exports a
# reviewed manual step, so a clean clone does not have them. Declaring a missing
# path as an input would make *every* target unbuildable at dependency
# resolution -- including `--dry-run` -- which turns "the export has not been
# made yet" into "the workflow is broken". So an absent input is replaced by a
# sentinel whose rule raises with the path and the way to produce it.
#
# This is not a skip. The job runs and fails; it fails with a message that names
# the file instead of an exception from inside a builder.
MISSING_INPUT = "MISSING_INPUT"

ABSENT_MESSAGES = {
	"powerplantmatching": (
		"The powerplantmatching export is not committed. It is a manual, reviewed "
		"step (`02-data-pipeline.md` §1.1): `ppm.powerplants()` hits live "
		"upstreams, so a per-run call makes every result depend on when it ran. "
		"Export it once and commit it at "
		f"{MANUAL_EXPORTS['powerplantmatching']}."
	),
	"afrec_demand": (
		"The AFREC demand export is not committed. Produce it once and commit it "
		f"at {MANUAL_EXPORTS['afrec_demand']}."
	),
	"hydro_atlas": (
		"The hydro atlas export is not committed, and the register marks the "
		"source unavailable: the specification cites a placeholder record. "
		"Resolve the record and register its DOI, or supply an export at "
		f"{MANUAL_EXPORTS['hydro_atlas']}."
	),
	"gridwatch": (
		"The GridWatch export is not committed. Produce it once and commit it at "
		f"{MANUAL_EXPORTS['gridwatch']}. GRIDWATCH_TOKEN must also be in the "
		"environment; the stage refuses without it rather than writing an empty "
		"ground truth."
	),
	"irena_costs": (
		"The IRENA cost export is not committed. Produce it once and commit it at "
		f"{MANUAL_EXPORTS['irena_costs']}."
	),
	"bus_weights": (
		"The bus weight table is not committed. `demand_hourly` disaggregates the "
		"national total against population and GDP shares per bus "
		"(`02-data-pipeline.md` §3.1), and there is no fetcher for that share "
		f"vector, so it is a human artefact. Write it at {WEIGHTS} with columns "
		"bus_id, population and gdp."
	),
	"solved_network": (
		"No solved network is in results/networks. The layer-4 stages read a "
		"*solved* network -- `@stage(\"network_arrays\")` converts one into the "
		"loss kernel's arrays and dispatch series, and `tlens` decomposes those. "
		"Run `alea solve --out results/networks` first; it needs the processed "
		"lake, so `snakemake -c1` for the upstream targets is the step before it."
	),
}


def provided(label, path):
	"""`path` when it exists, otherwise the sentinel that explains its absence."""
	return path if Path(path).exists() else f"{MISSING_INPUT}/{label}"


def manual_export(source_id):
	"""The committed export for a manual source, or a sentinel naming it."""
	return provided(source_id, MANUAL_EXPORTS[source_id])


def processed(stage, suffix=None):
	"""The tracked artefact path for a stage."""
	return f"{PROCESSED}/{stage}{suffix or SUFFIXES[stage]}"


def report_artefact(cadence, pattern):
	"""The dated path a report section reads, for a projection to write.

	``pattern`` is the section's own ``artefact`` string, with its ``{date}``
	unexpanded: the date is the *cadence's* period end and not the day the rule
	runs, so a literal here would be a file no report ever looks for. Snakemake
	needs a concrete path at parse time and the period end moves with the clock,
	which is why the projection resolves it and this declares the directory.

	Spelled here rather than at the rule so the one place that knows how a dated
	report path is built is beside the one place that knows how a processed path
	is built -- the same reason ``processed`` exists.
	"""
	directory = pattern.rsplit("/", 1)[0]
	return f"{RESULTS}/{directory}"


def alea(*arguments):
	"""An `alea` invocation, as a command prefix.

	`uv run --directory` rather than a bare `alea`: a rule must resolve the same
	interpreter and the same locked dependency set no matter where Snakemake was
	started from, and `--directory` is how `uv` is told that.
	"""
	return " ".join(["uv", "run", "--directory", shlex.quote(str(ROOT)), "alea", *arguments])


def set_arg(key, value):
	"""One `--set KEY=VALUE` argument, shell-quoted.

	A path with a space in it is the reason this exists: an unquoted
	`--set bus_weights=/my dir/x.parquet` is two arguments, and the second is a
	stage parameter the builder never sees.
	"""
	return shlex.quote(f"{key}={value}")


def force_flags():
	"""`--force` when the run asked for one.

	`--config force=true`, not Snakemake's own `--forceall`: `--forceall` is not
	visible to a rule, and a rule that silently ignored it would leave a stage
	Snakemake decided to rerun still short-circuiting on its own idempotence
	check -- a rerun that reports success and writes nothing.
	"""
	return ["--force"] if config.get("force", False) else []


rule missing_input:
	"""Fail with an explanation when a human-supplied input is absent.

	`provided()` substitutes the sentinel for an absent path so the DAG still
	builds; this rule is what turns the sentinel back into a failure, at the
	point Snakemake would have run the job that needed it.
	"""
	output:
		f"{MISSING_INPUT}/{{label}}"
	run:
		label = wildcards.label
		message = ABSENT_MESSAGES.get(label, f"the input {label!r} is missing")
		raise FileNotFoundError(message)
