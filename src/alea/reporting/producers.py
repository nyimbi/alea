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
and a test checks. Layer 6 held thirty-one sections, zero producers and no
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
#: One entry, and the first. Every other section below is reachable from a
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
	}
)


#: Sections with no producer, keyed by slug to why, and what would close it.
#:
#: Named explicitly rather than left implicit, following ``UNWIRED`` in
#: `alea.publish.views` and ``UNIMPLEMENTED_FETCHERS`` in
#: `tests/ci/test_io_registry.py`: a named gap fails a test when it changes, so
#: it cannot grow silently and cannot be closed without the test being updated.
UNPRODUCED: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		# ---- daily ----
		"outage_forecast": (
			"`outages.forecast_to_artefact` trains the forecaster and writes its "
			"metrics to a caller-chosen path; no rule runs it against "
			"`results/outages/forecast/{date}.parquet`, and the daily section's "
			"per-region probability rows are a different shape from the metrics "
			"the function returns. Needs a rule, and a projection from the "
			"forecaster's output to the section's columns."
		),
		"weather_alerts": (
			"No weather layer exists. `weather/alerts/{date}.parquet` is declared "
			"by the daily cadence and produced by nothing: ERA5 is a *fetch* "
			"(`alea.io.sources`, source id `era5_cutout`) with no fetcher "
			"implemented, and no code thresholds it by severity. The section's "
			"own prose says the threshold is config, so the config key has no "
			"reader either."
		),
		"generation_mix": (
			"`alea dispatch` now writes this one -- `planning/dispatch/{date}"
			".parquet` with value/unit/label columns -- but only when a caller "
			"passes an `--out` that resolves there, and no rule does. The gap is "
			"the rule, not the writer: a daily dispatch needs a solved day-ahead "
			"network at `results/networks`, which `alea solve` produces on "
			"request and no schedule runs."
		),
		"price_forecast": (
			"`market.clear_market` computes a `ClearingResult`; nothing runs it "
			"and nothing writes `market/prices/{date}.parquet`. `rules/market.smk` "
			"is empty by design (`06-layer3-market.md`: Layer 3 runs off the "
			"planning layer's artefacts), so the wiring is a rule and a "
			"projection, not a solver."
		),
		"system_alerts": (
			"Needs a solved network's N-1 sweep as *events above a severity "
			"threshold*. `losses.contingency_to_artefact` writes the sweep's "
			"summary to `data/processed/resilience/contingency.parquet`, which "
			"the API serves -- a different path, a different shape, and one "
			"aggregate rather than the per-element rows the section's columns "
			"expect."
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
		"week_ahead": (
			"A required weekly section with no producer at all: `planning/"
			"outlook/{date}.parquet` is declared by `reporting/weekly.py` and "
			"written by nothing. A required section whose artefact is absent "
			"raises `ReportDataError`, so the weekly report cannot currently be "
			"generated from the pipeline at all."
		),
		"market_summary": (
			"Needs the market layer's weekly aggregates. `market.capture_by_"
			"technology` and `market.build_stack` exist and write to caller-chosen "
			"paths; no rule runs them, so `market/summary/{date}.parquet` has no "
			"writer."
		),
		"renewable_forecast": (
			"`weather/renewables/{date}.parquet`. `planning.renewable_profiles` "
			"writes capacity factors to `data/processed/`, which the network "
			"builder reads -- not a dated forecast under `results/`. A "
			"*forecast* is a different quantity from a *profile*: the profile is "
			"a typical-year series and the section asks for the week ahead."
		),
		"loss_decomposition": (
			"`losses.decomposition_to_artefact` writes the decomposition and is "
			"exercised by `test_network_arrays.py`, but to a test's temporary "
			"path. No rule runs it against `results/losses/decomposition/{date}"
			".parquet`. The stage `@stage(\"losses\")` is not registered; the "
			"wired loss stage is `tlens`."
		),
		"outage_events": (
			"Needs detected outage *events* with start and end times. "
			"`outages.detect_to_artefact` writes per-tile detections; grouping "
			"them into events is not implemented anywhere, and the section's "
			"columns are event-shaped."
		),
		"mitigation": (
			"Needs a candidate-measure list. `losses.mitigation_to_artefact` and "
			"`losses.rank_options` exist and refuse without one -- "
			"`docs/plans/05-layer4-outages.md` names loss-optimal line switching "
			"as the reference, and no switching solver exists. This is the same "
			"blocker `data/processed/losses/mitigation.parquet` carries in "
			"`UNWIRED`."
		),
		# ---- monthly ----
		"market_report": (
			"A required monthly section with no producer. `market/monthly/"
			"{date}.parquet` is declared by `reporting/monthly.py` and written by "
			"nothing, so the monthly report cannot be generated from the pipeline "
			"either. This entry used to say the producer was 'a rule over a "
			"cleared scenario, not a new model', and that understated it: there "
			"is no cleared scenario to be a rule over. `clear_scenario` is "
			"defined and exported and called by nothing but its own tests, and "
			"`BiddingUnit` is constructed nowhere outside them -- no module builds "
			"a market fleet from a solved network, so the missing piece is the "
			"fleet, and the rule and the volume/average-price projection come "
			"after it. The projection itself is clearing arithmetic; the fleet is "
			"not."
		),
		"capacity_update": (
			"`planning/capacity/{date}.parquet`. `planning.capacity_mix_table` "
			"computes the mix from a solved network and `solve_scenario` writes "
			"it into the solve's JSON summary; no artefact carries it as its own "
			"dated table."
		),
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
		"loss_statistics": (
			"`losses/monthly/{date}.parquet`. `losses.losses_to_artefact` writes "
			"per-component losses; nothing aggregates them by month at the "
			"declared path."
		),
		"resilience_metrics": (
			"`resilience.resilience_to_artefact` exists and writes to a "
			"caller-chosen path; no rule runs it against `resilience/monthly/"
			"{date}.parquet`. The same function backs "
			"`data/processed/resilience/metrics.parquet` in `UNWIRED`, which is "
			"unwired for a second reason: it needs `interruptions.parquet` and "
			"`zone_population.parquet`, neither of which any stage writes."
		),
		"policy_tracker": (
			"Needs the scanning layer's policy extractions. `scanning.ingest` "
			"and `scanning.score_signals` exist; `scanning/integrate.py` writes "
			"proposals to a review queue rather than to a dated artefact, which "
			"is deliberate -- a proposal is not a fact until a human accepts it "
			"-- so the section reads a path the design does not write."
		),
		# ---- quarterly ----
		"market_outlook": (
			"A required quarterly section with no producer. Same missing rule as "
			"`market_report`."
		),
		"investment_pipeline": (
			"`scanning/pipeline/{date}.parquet`. `planning.catalogue` writes a "
			"project catalogue under `data/processed/`; the quarterly section "
			"wants it dated under `results/`, and nothing projects one to the "
			"other."
		),
		"scenario_update": (
			"`whatif/frontier/{date}.parquet`. `alea.whatif` solves scenarios "
			"through a cache and returns `ScenarioResult`s; no layer writes the "
			"frontier as an artefact, and `alea.api.whatif` writes one to a "
			"caller-chosen path from the API surface rather than a rule."
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
			"No weather layer exists. `weather/scenarios/{date}.parquet` would "
			"carry the CMIP scenario set, and the register holds no climate "
			"projection source."
		),
	}
)
"""Every declared section with no producer, and the measured blocker for each.

The reasons are longer than a sentence because the *blocker* is the useful
fact: "needs a rule" and "needs a model that does not exist" are different
amounts of work, and a register that says only "unwired" hides which one it is.
Five sections are `required=True` -- one per cadence: `outage_forecast`,
`week_ahead`, `market_report`, `market_outlook`, `continental_outlook` -- and
for those the report raises rather than warns. Every cadence's single required
section is unproduced, so *no* cadence can currently be generated from the
pipeline. The count was four here, and the daily cadence was the one it dropped;
`test_reporting_producers.py` pins one-required-per-cadence so the prose cannot
drift from the set it describes again.
"""


__all__ = [
	"PRODUCERS",
	"UNPRODUCED",
]
