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

`rules/market.smk` was included and held no rules while Layer 3 ran off the
planning layer's artefacts rather than a source of its own. It holds two now:
the monthly and quarterly sections whose artefacts were `required=True` and
written by nothing, so neither cadence could be generated from the pipeline.
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
include: "rules/sector.smk"
include: "rules/publish.smk"
include: "rules/reporting.smk"

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
		# The daily cadence's one `required=True` section, and the last cadence
		# that could not be generated from the pipeline. `outage_forecast` was
		# recorded as two gaps -- no forward-prediction producer, and no interval
		# method -- and the second was the harder one: the section declares an
		# `Interval` column that nothing could fill. Its band is a residual
		# quantile of the model's own held-out error, which the artefact's
		# provenance states in those words rather than letting a reader assume a
		# calibrated interval.
		processed("outage_forecast"),
		processed("network_arrays"),
		processed("tlens"),
		processed("critical_lines"),
		# The loss decomposition, and with it the API's losses route: the stage
		# writes the report frame at `data/processed/loss_decomposition.parquet`
		# and the serving table at `data/processed/losses/decomposition.parquet`
		# from one search for the loss-optimal reference topology. Both were
		# recorded as gaps -- the section in `reporting.producers.UNPRODUCED`, the
		# table in `publish.views.UNWIRED` -- and the blocker both named was the
		# missing switching kernel rather than the missing rule.
		processed("loss_decomposition"),
		processed("losses/decomposition", ".parquet"),
		# `sector_coupling` is deliberately absent, like the fetch rules above.
		# It refuses when every sector is disabled -- the shipped config's state
		# (`sector.enabled: false`) -- so an unconditional entry here would make
		# `snakemake all` fail on a default clone. Run it by name once a config
		# enables a sector: `snakemake -c1 sector_coupling`.
		processed("resilience/contingency", ".parquet"),
		processed("market/prices", ".parquet"),
		processed("market/capture_rates", ".parquet"),
		# The two report sections Layer 3 produces. They are in `rule all`
		# because they are not optional: the monthly and quarterly reports
		# declare them `required=True`, so a workflow that skipped them would
		# leave two cadences unbuildable.
		processed("market_report"),
		processed("market_outlook"),
		# The monthly capacity section. Optional to the report, so its absence
		# warns rather than raises -- but it is a section a reader opens the
		# monthly report for, and it costs one read of a network already solved.
		processed("capacity_update"),
		# The daily contingency section's rows, renamed from the serving table
		# above rather than re-swept: the report and the API's contingency route
		# read the same sweep, so they cannot disagree about what is critical.
		processed("system_alerts"),
		# The projections, not the builds. A stage's artefact under
		# `data/processed` is not the section's: the report reads
		# `results/<dir>/{date}.parquet`, and until these rules existed nothing
		# wrote one -- so the build succeeded, the report raised "no artefact",
		# and `reporting.producers.PRODUCERS` recorded a function rather than a
		# deliverable section. The first is the one that measured the defect; the
		# other three are the sections `PROJECTED`/`UNPROJECTED` names, and two
		# of them are required, so their cadences raise without them.
		report_artefact("monthly", "planning/capacity/{date}.parquet"),
		report_artefact("weekly", "outages/critical/{date}.parquet"),
		report_artefact("monthly", "market/monthly/{date}.parquet"),
		report_artefact("quarterly", "market/outlook/{date}.parquet"),
		report_artefact("daily", "planning/dispatch/{date}.parquet"),
		report_artefact("daily", "market/prices/{date}.parquet"),
		report_artefact("daily", "outages/contingency/{date}.parquet"),
		report_artefact("daily", "outages/forecast/{date}.parquet"),
		# The two loss sections, projected from the one decomposition above. The
		# weekly one is the section whose register entry recorded the degeneracy
		# rather than the missing rule; the monthly one reads the same frame under
		# a different header, so a single projection would have left it absent.
		report_artefact("weekly", "losses/decomposition/{date}.parquet"),
		report_artefact("monthly", "losses/monthly/{date}.parquet"),
