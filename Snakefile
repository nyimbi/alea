# SPDX-License-Identifier: MIT
"""The ALEA workflow.

AD-5 is the rule this file exists to obey: **the CLI is the only entry point a
rule calls.** Every `shell:` in `rules/` is `uv run alea ...`. No rule imports a
Python function, because a rule that imports code cannot be rerun against a
different environment and a rule that shells out can -- and because logic in a
`.smk` is logic that cannot be unit-tested, cannot be type-checked and cannot be
imported.

What this file therefore does *not* contain: a disaggregation, a download, a
parse. §4 of `02-data-pipeline.md` names the stages; each has a rule that runs
`alea build <stage>` and nothing more. A rule that needs new behaviour needs a
new CLI subcommand with tests, not a longer shell string.

    snakemake --dry-run                       # what would run
    snakemake -c1 topology fleet              # two named targets
    snakemake -c1 --config force=true         # rebuild even where current

The environment config is `--config env=<path>`, defaulting to
`config/config.kenya.yaml`: Kenya is the development target, and a workflow whose
default config is continental would try to solve a problem the development
machine cannot hold.

Deliberately not imported here: `alea`. Enumerating sources from the register at
parse time would put a Python import in the workflow layer, which AD-5 exists to
prevent. `rules/fetch.smk` declares the fetchable sources as literals and
`tests/ci/test_orchestration_workflow.py` asserts that list is exactly the
register's fetchable-and-implemented set.

`rules/market.smk` is included and holds no rules: Layer 3 runs off the planning
layer's artefacts rather than a source of its own, and an include that resolves
to an empty module is a different thing from a missing file.
"""

include: "rules/common.smk"
include: "rules/fetch.smk"
include: "rules/topology.smk"
include: "rules/demand.smk"
include: "rules/renewables.smk"
include: "rules/hydro.smk"
include: "rules/costs.smk"
include: "rules/market.smk"
include: "rules/outages.smk"
include: "rules/losses.smk"
include: "rules/publish.smk"

# The default target. Snakemake takes the first rule when no target is named,
# and "the first rule" is fragile in a file whose rule order is maintained by
# hand, so it is named.
rule all:
	"""Every processed dataset the pipeline builds.

	Deliberately not the fetch rules: a fetch is a network call, the raw layer is
	content-addressed, and re-fetching to prove it is deterministic is not worth
	the bandwidth. `snakemake -c1 fetch_all` runs them when they are wanted.
	"""
	input:
		processed("topology"),
		processed("fleet"),
		processed("demand_national"),
		processed("demand_hourly"),
		processed("cutout"),
		processed("renewable_profiles"),
		processed("hydro_profiles"),
		processed("costs"),
		processed("fuel_prices"),
		processed("outage_history"),
		processed("outage_truth"),
		processed("network_arrays"),
		processed("tlens"),
		processed("critical_lines"),
		processed("resilience/contingency", ".parquet"),
		processed("market/prices", ".parquet"),
		processed("market/capture_rates", ".parquet"),
