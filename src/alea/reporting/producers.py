# SPDX-License-Identifier: MIT
"""Which layer writes each report section's artefact, and which writes nothing.

`reporting/service.py` declares 31 sections across five cadences and reads each
one's artefact from ``paths.results``. Nothing else in the repository named
those paths: no rule, no stage, no layer service. The declared paths are a
*convention* -- a producer is expected to be run with an ``--out`` that lands
the file at ``results/<dir>/<date>.parquet`` -- and a convention that no file
records is indistinguishable from coverage.

That is the defect this module closes, and it is the Layer 8 defect one layer
up. `alea.publish.views` holds four registers and a bidirectional gate over its
eleven serving tables, so "this table has a producer" is a claim someone made
and a test checks. Layer 6 held thirty-one sections, one producer and no
register at all: the render tests pass because `tests/fixtures/reporting`
writes every declared path by hand, so a section that no layer produces renders
perfectly in CI and warns "no artefact" in production. The fixture is the
measurement, and a fixture that manufactures the input cannot see a missing
producer.

**Why a register and not a name match.** The gate cannot decide a section is
produced by matching its directory against a stage name. `market/prices` is a
section and `market` is a layer; the layer's `clear_market` writes a
`ClearingResult` at a caller-chosen path, which is not the section's artefact
and carries a different schema. Inferring production from the shared word
marked the section produced while nothing wrote it -- the same failure
`PROJECTION_STAGES` documents for `outage_history`, which is both a serving
table and a stage writing a different quantity at a different path.

So a section is produced only when this register names the thing that writes
it, and ``PRODUCERS`` is checked against the cadence modules in both
directions: a section with no entry fails, and an entry naming a section no
cadence declares fails.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

#: Sections with a producer, keyed by slug to the producer's name.
#:
#: Three entries, and the first was the one that proved the register had to
#: exist before it could shrink. Every other section below is reachable from a
#: *reader* and from no writer: the layer services exist
#: (`market.clear_market`, `outages.forecast_to_artefact`,
#: `losses.decomposition_to_artefact`, `resilience.resilience_to_artefact`,
#: `sector.couple_network`) but none of them writes a dated artefact under
#: ``paths.results``, and no Snakemake rule or DVC stage runs one to do so.
#: Adding a producer moves its slug here in the same change, which is what
#: makes the register shrink as the gap closes.
PRODUCERS: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		# The first section to leave `UNPRODUCED`, and the reason the register
		# had to be built before it could shrink: the blocker was recorded as
		# "needs a loading kernel, and there is none", the kernel was written
		# (`losses.flow.loading_series`), and the slug moved here with it.
		"critical_lines": "losses.service.critical_lines_to_artefact",
		# Recorded as "no artefact carries the mix as its own dated table", and
		# that was exact: `capacity_mix_table` computed it and the solve's JSON
		# summary carried it, which is a run record rather than a report input.
		# The stage is `alea.planning.arrays.build_capacity_update` and the
		# section's two numeric columns are why it writes `change` as a column
		# of its own rather than folding it into the capacity.
		"capacity_update": "planning.arrays.build_capacity_update",
		# The two required sections whose absence meant *no* cadence could be
		# generated from the pipeline. The blocker recorded here was measured
		# and correct: no module built a market fleet from a solved network, so
		# `clear_scenario` had no caller and `BiddingUnit` was constructed
		# nowhere outside tests. `market/fleet.py` is that module,
		# `market/stages.py` registers the two stages that run it, and the
		# register's own gate measured the move.
		"market_outlook": "market.service.quarterly_market_to_artefact",
		"market_report": "market.service.monthly_market_to_artefact",
		# The two daily sections a solved network closes. Both were recorded as
		# blocked on something that does not exist -- `generation_mix` on "a rule,
		# not the writer" and `price_forecast` on "nothing runs
		# `market.clear_market`" -- and both were right about the *section's* own
		# shape. The quantity for each was already computed: dispatch for the mix,
		# marginal prices for the API's serving table. A serving table is what a
		# route reads, not what a report section reads, so `price_forecast` clears
		# the network again into the report's columns rather than reshaping one.
		"generation_mix": "planning.arrays.build_generation_mix",
		"price_forecast": "market.service.daily_price_to_artefact",
		# The daily forecast, and the last section whose absence meant a cadence
		# could not be generated at all. Its register entry named two gaps and was
		# right about both, which is worth recording: `forecast_to_artefact`
		# writes `Forecaster.metrics` -- a statement about the *model* -- while
		# the section asks for a probability per zone, and `predict_proba` existed
		# with no caller. The interval was the second gap and the harder one,
		# because it needed a *method* rather than a caller: the section declares
		# an `Interval` column, `assemble.py` reads a band from
		# `interval_low`/`interval_high`, and `ForecastMetrics` had no interval
		# field. `outages.weather.residual_band` is that method, and the entry
		# said it would be "a modelling decision to be made and recorded" --
		# which is what it is, recorded in `WeatherConfig.interval_level` and
		# stated in provenance as a residual quantile rather than a calibrated
		# predictive interval, because the two print the same two numbers.
		"outage_forecast": "outages.service._stage_outage_forecast",
		# The weekly cadence's only required section, and the last of the three
		# that kept a cadence from being generatable at all. Its blocker was
		# recorded as "no producer at all" and was exact -- nothing wrote
		# `planning/outlook/{date}.parquet`. `planning/balance.py` is the
		# producer, and it is in Layer 1 rather than Layer 3 because all three
		# quantities the section names are network facts.
		"week_ahead": "planning.arrays.build_week_ahead",
		# The weekly cadence's *optional* section, and the first entry here whose
		# absence was invisible: an optional section with no artefact warns
		# rather than raises, so `market_summary` stayed missing through every
		# green suite while a reader was promised a table. The blocker recorded
		# above was exact -- `market.capture_by_technology` existed and no rule
		# ran it. The weekly producer writes a ``capture_price`` column rather
		# than the monthly section's ``average_price`` because the reader binds a
		# header to the column naming it, and ``Capture price`` is not
		# ``Average price``.
		"market_summary": "market.service.weekly_market_to_artefact",
		# The scanning layer's one report section, and the first entry here whose
		# input is a *reviewed queue* rather than a file a stage produced. The
		# blocker recorded above was right that `scanning.integrate` writes
		# proposals to a review queue deliberately -- a proposal is not a fact
		# until a human accepts it. What it missed is that the *confirmed* set is
		# readable: `ReviewQueue.confirmed_signals()` returns exactly the signals
		# a human or a recorded auto-acceptance has accepted, which is a fact and
		# is what the section asks for.
		"policy_tracker": "scanning.service.policy_tracker_to_artefact",
		# The weekly weather section. The blocker recorded above said a
		# *forecast* is a different quantity from a *profile*, and the
		# distinction is real while the conclusion did not follow: the network's
		# own ``p_max_pu`` **is** the weather model's output, because
		# `planning.renewables.attach_renewable_profiles` writes the
		# atlite-derived capacity factor there. So the stage reads it back
		# rather than re-running atlite, and records basis ``modelled`` -- which
		# is what it is, and what `week_ahead` recorded for the same quantity one
		# section over. The register entry named the artefact's *directory*
		# (`data/processed/`) as the defect when the defect was that no rule
		# projected it.
		"renewable_forecast": "planning.arrays.build_renewable_forecast",
		# The daily contingency section, and the first entry here whose producer
		# *reads* another consumer's table rather than a layer's result. The
		# per-element rows already existed: `@stage("resilience_contingency")`
		# sweeps the solved network and writes the serving table the API's
		# contingency route reads. The section wants the same rows under
		# different headers, so `resilience.service.system_alerts_to_artefact`
		# renames them -- `element_id` to the label, `severity` to `state` -- and
		# re-sweeping would be a second computation of the same numbers.
		"system_alerts": "resilience.service.system_alerts_to_artefact",
		# The weekly loss decomposition and the monthly loss statistics, and the
		# first pair here that one producer feeds. The blocker both entries
		# recorded was the *same* one and it was measured rather than guessed:
		# `losses.decompose.measure`'s reference network was the actual network,
		# so `T - R` was zero by construction and the decomposition published
		# `load driven == total` for every network -- the specification's
		# `_topology_driven = 0 # Placeholder` relocated rather than repaired. The
		# missing piece was the reference topology the plan names, loss-optimal
		# line switching, and `alea.losses.switching` is that kernel now. The
		# stage resolves the reference through it and writes one frame, because
		# both sections declare one numeric column at unit `%` and differ only in
		# the header.
		"loss_decomposition": "losses.service._stage_loss_decomposition",
		"loss_statistics": "losses.service._stage_loss_decomposition",
		# The quarterly scenario range. Recorded here as blocked on "no layer
		# writes the frontier as an artefact", and that was exact: the engine
		# solved and cached, the API wrote a document to whatever path its caller
		# named, and no rule landed the section's frame where the section reads
		# it. `whatif/stages.py` is that rule's stage.
		"scenario_update": "whatif.stages.build_scenario_update",
	}
)


#: Produced sections whose *dated* artefact a workflow rule writes.
#:
#: A separate register because ``PRODUCERS`` answers a weaker question than it
#: looks like it answers. Every stage writes ``data/processed/<stage>.<suffix>``
#: and every section reads ``results/<dir>/{date}.parquet``; naming the function
#: that computes a section's rows is not naming the rule that lands them where
#: the reader looks. Measured 2026-10-13: `capacity_update` was in ``PRODUCERS``,
#: its rule ran and exited 0, and `alea report monthly` exited 1 with
#: ``ReportDataError: no artefact`` -- so the register recorded that a function
#: exists rather than that a section is deliverable, and 918 tests passed over a
#: pipeline that could not deliver one section.
#:
#: ``PROJECTED`` and ``UNPROJECTED`` partition ``PRODUCERS``, so a slug cannot be
#: recorded as produced and left unexamined, and closing a gap means moving a
#: slug between these two rather than editing a claim.
#: `alea.reporting.projection` is the step they name.
PROJECTED: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		# The first, and the one that measured the defect. `rules/reporting.smk`
		# declares the rule and `dvc.yaml` a stage beside it, both writing
		# `results/planning/capacity` -- the directory the section's own
		# ``artefact`` pattern lives in, asserted by
		# `test_orchestration_workflow.py::test_a_projection_writes_the_pattern_its_section_declares`.
		"capacity_update": "project_capacity_update",
		# `rules/losses.smk` writes the processed form and says in its own
		# docstring that the dated path "is the projection's ``--out`` and is not
		# this rule's business". That sentence described this register's whole gap
		# before anything closed it; `rules/reporting.smk`'s
		# ``project_critical_lines`` is the projection it named.
		"critical_lines": "project_critical_lines",
		# The two required market sections, and the reason neither the monthly nor
		# the quarterly cadence could be generated from the pipeline: a required
		# section whose artefact is absent raises rather than warns.
		# `market_outlook`'s date is the quarter that *ended* --
		# `reporting.schemas.period_for` decides which day that is, and a
		# projection stamped with its own run date would write a file no quarterly
		# report opens.
		"market_outlook": "project_market_outlook",
		"market_report": "project_market_report",
		# The daily mix. `alea dispatch` already wrote this frame and no rule ran
		# it -- the register recorded the gap as "the rule, not the writer", and
		# `@stage("generation_mix")` is the rule. The stamp is the network's first
		# snapshot, so the projection's date and the file's date are the same fact
		# reached two ways; a daily report covers yesterday, and a file stamped
		# with the run date would be read by no report at all.
		"generation_mix": "project_generation_mix",
		# Optional, so its absence warned rather than raised -- which is why it
		# stayed absent through every green suite. The quantity was already being
		# computed for the API's serving table at a different shape; the section
		# reads a report's columns, not a route's.
		"price_forecast": "project_price_forecast",
		# The weekly balance, and with it the last cadence whose *required*
		# section was undeliverable. A weekly report issued on Monday covers the
		# week that ended, which `reporting.schemas.period_for` resolves -- a
		# projection stamped with its own run date would write a file no weekly
		# report opens.
		"week_ahead": "project_week_ahead",
		# The weekly summary, projected to `market/summary/{date}.parquet`. The
		# weekly cadence issues on Monday for the week that ended, which
		# `reporting.schemas.period_for` resolves -- a projection stamped with
		# its own run date would write a file no weekly report opens.
		"market_summary": "project_market_summary",
		# The monthly tracker, projected to `scanning/policy/{date}.parquet`.
		"policy_tracker": "project_policy_tracker",
		# The weekly weather section, projected to
		# `weather/renewables/{date}.parquet`. The weekly cadence issues on
		# Monday for the week that ended, so the projection resolves the period
		# rather than stamping its own run date.
		"renewable_forecast": "project_renewable_forecast",
		# The daily forecast, projected to `outages/forecast/{date}.parquet`. The
		# daily cadence's one required section: a daily report generated at 06:00
		# covers *yesterday*, which `period_for` resolves, so a projection stamped
		# with its own run date would write a file no daily report opens -- and
		# because the section is required, the symptom is a raise rather than a
		# warning.
		"outage_forecast": "project_outage_forecast",
		# The daily contingency section, projected to
		# `outages/contingency/{date}.parquet`. A daily report generated at 06:00
		# covers *yesterday*, so the projection resolves the cadence's period
		# rather than stamping its own run date -- a literal here would name a
		# file no daily report opens.
		"system_alerts": "project_system_alerts",
		# The two loss sections, and the pair that makes the case for one stage
		# writing one frame. Both declare a single numeric column at unit `%` --
		# `["Component", "Share of input", "Basis"]` weekly and `["Component",
		# "Loss share", "Basis"]` monthly -- so `@stage("loss_decomposition")`
		# writes the rows once and these two rules land them where each cadence
		# looks. The `UNPRODUCED` entries for both named the *same* missing
		# kernel, which is why they move together rather than one at a time.
		"loss_decomposition": "project_loss_decomposition",
		"loss_statistics": "project_loss_statistics",
		# The quarterly range, and the last section whose recorded blocker was a
		# *wiring* gap rather than a data arrival. `alea.whatif` could sweep a
		# parameter and `alea.api.whatif` could write a frontier -- to a
		# caller-chosen path, from an HTTP job, which is a route's shape and not a
		# report's. Nothing ran a sweep from a rule and landed the section's frame
		# at the section's own dated path.
		#
		# The sweep goes through `sweep_parameter` rather than
		# `efficient_frontier` because the section asks for capacity, which the
		# *result* carries (`capacity_mix_mw`) and the frontier frame drops:
		# re-deriving it from the frontier's cost would be inventing it.
		"scenario_update": "project_scenario_update",
	}
)


#: Produced sections whose dated path no rule writes, and what closes each.
#:
#: Empty, and that is the measurement rather than a placeholder: every section
#: ``PRODUCERS`` names now has a rule that lands its artefact where the report
#: reads it. The register is kept because it is the *question* -- it is what
#: fails when a new producer is recorded without its delivery, which is how
#: `capacity_update` came to be recorded as produced while `alea report monthly`
#: exited 1. Deleting it would restore the state in which ``PRODUCERS`` means
#: "a function exists" and nothing says otherwise.
UNPROJECTED: Final[MappingProxyType[str, str]] = MappingProxyType({})


#: Sections with no producer, keyed by slug to why, and what would close it.
#:
#: Named explicitly rather than left implicit, following ``UNWIRED`` in
#: `alea.publish.views` and ``UNIMPLEMENTED_FETCHERS`` in
#: `tests/ci/test_io_registry.py`: a named gap fails a test when it changes, so
#: it cannot grow silently and cannot be closed without the test being updated.
UNPRODUCED: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		# ---- daily ----
		"weather_alerts": (
			"No weather layer exists. `weather/alerts/{date}.parquet` is declared "
			"by the daily cadence and produced by nothing: ERA5 is a *fetch* "
			"(`alea.io.sources`, source id `era5_cutout`) with no fetcher "
			"implemented, and no code thresholds it by severity. The section's "
			"own prose says the threshold is config, so the config key has no "
			"reader either."
		),
		"outage_summary": (
			"VIIRS outage detection at `outages/viirs/{date}.parquet`. "
			"`outages.detect_to_artefact` writes detections, but the source is "
			"`viirs_vnp46a2`, which is in the register as automated and has no "
			"fetcher (`UNIMPLEMENTED_FETCHERS`). The section also declares the "
			"satellite's 24-48 h latency as a data window, so the producer must "
			"write the coverage window alongside the rows."
		),
		# ---- weekly ----
		"outage_events": (
			"Needs a *cause* per detected outage, which is what the section's "
			"columns ask for -- `[\"Cause\", \"Events\", \"Basis\"]`, a count "
			"grouped by cause, not the event rows this entry used to describe. "
			"`outages.detect_to_artefact` writes per-tile detections and a "
			"detection carries no cause; `scanning.extract.extract_causes` reads "
			"causes out of prose. Nothing joins a dark tile to a published cause, "
			"and grouping detections into events is not implemented either -- so "
			"this needs a cause-attribution model, and the grouping is the smaller "
			"half of it."
		),
		"mitigation": (
			"Needs a candidate-measure list. `losses.mitigation_to_artefact` and "
			"`losses.rank_options` exist and refuse without one -- a mitigation "
			"ranking is over *candidate measures* (reconductoring a branch, "
			"upgrading a voltage, adding a parallel circuit) and nothing records "
			"which measures are candidates for which branch. This entry used to "
			"name loss-optimal line switching as the blocker and cite "
			"`docs/plans/05-layer4-outages.md`, which does not exist -- the "
			"switching kernel is `alea.losses.switching` now and it ranks nothing, "
			"because a *switching* decision is a topology and a mitigation ranking "
			"is a capital measure. Synthesising one option per branch would "
			"fabricate engineering options with capex figures nobody supplied, so "
			"this waits on a data arrival, not a wiring task -- the same blocker "
			"`data/processed/losses/mitigation.parquet` carries in `UNWIRED`."
		),
		# ---- monthly ----
		"generation_actual_vs_forecast": (
			"Needs the previous month's forecast retained, which "
			"`09-layer6-reporting.md` §3.3 calls out: a comparison against a "
			"forecast that was not saved is a comparison against a "
			"reconstruction. No producer retains a monthly forecast, so both "
			"sides of the comparison are missing."
		),
		"outage_statistics": (
			"SAIDI/SAIFI with proxy flags. `resilience.compute_metrics` computes "
			"them from an interruption frame and writes to a caller-chosen path; "
			"the monthly section declares `outages/reliability/{date}.parquet`, "
			"and the proxy basis the section requires has to travel with each "
			"row."
		),
		"resilience_metrics": (
			"`resilience.resilience_to_artefact` exists and writes to a "
			"caller-chosen path; no rule runs it against `resilience/monthly/"
			"{date}.parquet`. The same function backs "
			"`data/processed/resilience/metrics.parquet` in `UNWIRED`, which is "
			"unwired for a second reason: it needs `interruptions.parquet` and "
			"`zone_population.parquet`, neither of which any stage writes."
		),
		# ---- quarterly ----
		"investment_pipeline": (
			"Needs committed and proposed *projects*, which is what the section's "
			"columns ask for -- `[\"Stage\", \"Capacity\", \"Basis\"]`, "
			"generation and transmission capacity grouped by development stage. "
			"This entry used to name `planning.catalogue` as the producer missing "
			"only a projection, and that was wrong: the catalogue holds solved "
			"*scenarios* (`carrier` / `capacity_mw` / `share` per horizon), which "
			"carry no development stage and no country. The quantity does exist "
			"one layer over -- `scanning.extract` reads `capacity_mw`, "
			"`investment_usd` and `SignalType.GENERATION_INVESTMENT` out of "
			"documents, and `guess_signal_type` routes them -- but a signal is a "
			"proposal in a review queue, not a committed project, so the producer "
			"waits on a review-queue reader and a project-stage model."
		),
		"climate_risk": (
			"No weather layer exists. `weather/climate_risk/{date}.parquet` has "
			"no producer and no model: the hazards the section names are not "
			"computed anywhere in the repository."
		),
		"resilience_scorecard": (
			"`resilience/scorecard/{date}.parquet`. `resilience.compute_metrics` "
			"produces the inputs; the scorecard's own aggregation across zones "
			"and hazards is not implemented."
		),
		# ---- annual ----
		"continental_outlook": (
			"A required annual section with no producer. `planning/continental/"
			"{date}.parquet` would need a continental solve; "
			"`test_the_continental_config_builds_without_solving` asserts the "
			"config builds and deliberately does not solve, because a "
			"continental solve is hours of compute."
		),
		"investment_requirements": (
			"`planning/investment/{date}.parquet`. The expansion solve's "
			"objective and per-component `capital_cost` carry this; nothing "
			"writes it as a dated table, and the section's rows are per-"
			"technology requirements rather than the solve's summary."
		),
		"cmp_alignment": (
			"Needs the CMP's published targets as an ingested source. No source "
			"in the register holds them and no code compares a scenario against "
			"them, so the section has neither a reader nor a writer."
		),
		"afsem_progress": (
			"Needs the AfSEM indicator set as an ingested source, on the same "
			"footing as `cmp_alignment`: declared by the cadence, registered "
			"nowhere, produced by nothing."
		),
		"just_transition": (
			"`sector/just_transition/{date}.parquet`. `sector.couple_network` "
			"produces the coupling; the employment and access indicators the "
			"section names are not computed in `alea.sector`, which models "
			"energy vectors rather than labour."
		),
		"climate_scenarios": (
			"A modelling gap, not a fetch one. `cmip6` is registered, its declared "
			"``target`` is this slug, and `alea.io.fetchers` fetches its ESGF "
			"dataset inventory -- so the source the entry above used to say was "
			"missing has been there all along. What does not exist is everything "
			"between that inventory and the section: a producer must name a "
			"dataset per scenario, download it (terabytes, which the fetcher's own "
			"docstring puts deliberately outside the pipeline), downscale it to "
			"the network's snapshots, and re-solve for each. The section's "
			"`Scenario`, `System cost` and `Reliability` columns come from the "
			"last step and nothing runs it."
		),
	}
)
"""Every declared section with no producer, and the measured blocker for each.

The reasons are longer than a sentence because the *blocker* is the useful
fact: "needs a rule" and "needs a model that does not exist" are different
amounts of work, and a register that says only "unwired" hides which one it is.
Five sections are `required=True` -- one per cadence: `outage_forecast`,
`week_ahead`, `market_report`, `market_outlook`, `continental_outlook` -- and
for those the report raises rather than warns. One of the five is unproduced, so
one cadence -- annual -- still cannot be generated from the pipeline.

This sentence was wrong twice, in opposite directions, and both are worth
keeping. It first said "two ... daily and annual" while `week_ahead` sat in the
mapping below it, so the count was one short of the set: the count is a
*summary of this set* and nothing checked it. It then said three, correctly,
until `week_ahead` moved to ``PRODUCERS`` -- at which point the sentence and the
mapping would have drifted apart a second time had the gate not failed on the
move. `test_reporting_producers.py` derives the count from the mapping rather
than letting it be retyped, which is why closing the weekly gap edited a number
here instead of silently falsifying it.

The daily cadence left the same way on 2026-10-13, and its two entries are worth
reading as a pair because they were *different kinds* of gap wearing the same
word. `generation_mix` said "the gap is the rule, not the writer" and that was
exact: `alea dispatch` already wrote the section's own frame and no rule ran it.
`price_forecast` said "nothing runs `market.clear_market`" and that was true of
the *section's* shape while the same quantity was already being computed for the
API's serving table -- at a different path and in a different shape, because a
serving table is what a route reads and not what a report reads. One entry needed
a rule; the other needed a producer. A register that recorded both as "unwired"
would have hidden that, which is why the reasons here are sentences and not a
boolean.

`outage_forecast` left last, on 2026-10-14, and it is the third kind: the entry
was *right about both* of its gaps, and the second one needed a decision rather
than a piece of code. Nothing turned a fitted `Forecaster` into a probability
per zone (`predict_proba` existed with no caller), and no interval method
existed at all -- the section declares an `Interval` column and
`ForecastMetrics` had no field to carry one. The first gap was a producer; the
second was a *modelling choice*, and the entry said so in advance ("an interval
method that is a modelling decision to be made and recorded"), which is what
made it closable rather than open-ended. A register whose blockers name the
decision rather than only the artefact is one an engineer can finish.
"""


__all__ = [
	"PRODUCERS",
	"PROJECTED",
	"UNPRODUCED",
	"UNPROJECTED",
]
