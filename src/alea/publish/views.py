# SPDX-License-Identifier: MIT
"""The serving tables: one declared schema per artefact the API reads.

Each schema here is the contract between two modules that must not drift: the
projection that writes the table and the repository that reads it. A column in
the repository's row builder and not in the schema is a column nothing writes --
the defect class this whole package exists to close -- and a column in the schema
and not in the repository is a table with a field no consumer wants. Declaring
them in one place is what makes the mismatch a test failure rather than a
missing-column `KeyError` twelve frames into a request.

The units are the layer's units, not the API's. A loss is MWh here and the API
labels it MWh; a rate is a fraction here and the API labels it "fraction". A
projection that converts units is a second place a unit can be wrong, and the
repository already carries the unit string each row is served with.

**What is deliberately absent.** `TlensRowOut` serves `transmission_loss_pct`,
`distribution_loss_pct` and `collection_loss_pct` -- T&D loss percentages by
country-year. No layer computes those, no source provides them, and the
specification does not ask for them: `spec4-base.md` §22 lists
``/api/v1/losses/tlens`` as "Critical line ranking", which is what
:class:`alea.losses.views.TlensEntry` computes. The view invented a product and
the route serves it, so the table cannot be projected from anything real. That
gap is named in :data:`UNPROJECTABLE` rather than filled with a fabricated
number, and it is a decision for the spec owner, not for this module.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from alea.planning.schemas import ArtefactSchema, ColumnSpec

# --------------------------------------------------------------------------
# Market
# --------------------------------------------------------------------------

MARKET_PRICES = ArtefactSchema(
	name="market_prices",
	columns=(
		ColumnSpec(name="at", dtype="str", unit="ISO 8601", description="Interval start."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="price", dtype="float", unit="USD/MWh", description="Clearing price."),
		ColumnSpec(name="unit", dtype="str", description="The unit the price is stated in."),
	),
)

MARKET_CAPTURE_RATES = ArtefactSchema(
	name="market_capture_rates",
	columns=(
		ColumnSpec(name="technology", dtype="str", description="Carrier name."),
		ColumnSpec(
			name="vre_penetration",
			dtype="float",
			unit="fraction",
			description="VRE share of generation the point is measured at.",
		),
		ColumnSpec(
			name="capture_rate",
			dtype="float",
			unit="fraction",
			description="Revenue-weighted price over the time-weighted price.",
		),
		ColumnSpec(
			name="capture_price",
			dtype="float",
			unit="USD/MWh",
			description="The carrier's own realised price.",
		),
	),
)

MARKET_PPA_BENCHMARKS = ArtefactSchema(
	name="market_ppa_benchmarks",
	columns=(
		ColumnSpec(name="technology", dtype="str", description="Carrier name."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="ppa_price", dtype="float", unit="USD/MWh", description="Benchmark price."),
		ColumnSpec(name="tenor_years", dtype="int", unit="year", description="Contract tenor."),
		ColumnSpec(
			name="benchmark_source",
			dtype="str",
			description="Where the benchmark came from, or the modelled basis.",
		),
	),
)

# --------------------------------------------------------------------------
# Outages and maintenance
# --------------------------------------------------------------------------

OUTAGE_FORECAST = ArtefactSchema(
	name="outage_forecast",
	columns=(
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="grid_zone", dtype="str", description="Zone identifier."),
		ColumnSpec(
			name="probability",
			dtype="float",
			unit="probability",
			description="Probability the zone loses supply in the horizon.",
		),
		ColumnSpec(name="horizon_hours", dtype="int", unit="h", description="Forecast horizon."),
		ColumnSpec(name="issued_at", dtype="str", unit="ISO 8601", description="Issue time."),
		ColumnSpec(name="model_version", dtype="str", description="Model that produced it."),
	),
)

OUTAGE_HISTORY = ArtefactSchema(
	name="outage_history",
	columns=(
		ColumnSpec(name="event_id", dtype="str", description="Stable event identifier."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="grid_zone", dtype="str", description="Zone identifier."),
		ColumnSpec(name="started_at", dtype="str", unit="ISO 8601", description="Event start."),
		ColumnSpec(
			name="duration_minutes",
			dtype="float",
			unit="minutes",
			description="Event duration.",
		),
		ColumnSpec(
			name="customers_affected",
			dtype="float",
			unit="customers",
			description="Customers interrupted.",
		),
		ColumnSpec(name="cause", dtype="str", description="Recorded cause, or unknown."),
	),
)

OUTAGE_VALIDATION = ArtefactSchema(
	name="outage_validation",
	columns=(
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="grid_zone", dtype="str", description="Zone identifier."),
		ColumnSpec(name="period_start", dtype="str", unit="ISO 8601", description="Period start."),
		ColumnSpec(name="period_end", dtype="str", unit="ISO 8601", description="Period end."),
		ColumnSpec(name="auc", dtype="float", unit="AUC", description="ROC AUC."),
		ColumnSpec(name="precision", dtype="float", unit="fraction", description="Precision."),
		ColumnSpec(name="recall", dtype="float", unit="fraction", description="Recall."),
		ColumnSpec(name="sample_size", dtype="int", description="Rows scored."),
	),
)

MAINTENANCE_PREDICTIONS = ArtefactSchema(
	name="maintenance_predictions",
	columns=(
		ColumnSpec(name="asset_id", dtype="str", description="Stable asset identifier."),
		ColumnSpec(name="asset_type", dtype="str", description="Asset class."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(
			name="failure_probability",
			dtype="float",
			unit="probability",
			description="Probability of failure in the window.",
		),
		ColumnSpec(name="window_days", dtype="int", unit="day", description="Prediction window."),
		ColumnSpec(
			name="recommended_action",
			dtype="str",
			description="The action the hazard implies.",
		),
		ColumnSpec(name="model_version", dtype="str", description="Model that produced it."),
	),
)

# --------------------------------------------------------------------------
# Losses
# --------------------------------------------------------------------------

LOSSES_DECOMPOSITION = ArtefactSchema(
	name="losses_decomposition",
	columns=(
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="period_start", dtype="str", unit="ISO 8601", description="Period start."),
		ColumnSpec(name="period_end", dtype="str", unit="ISO 8601", description="Period end."),
		ColumnSpec(name="total_loss", dtype="float", unit="MWh", description="Total losses."),
		ColumnSpec(
			name="components",
			dtype="str",
			description=(
				"JSON array of {component, loss, share}. A string column rather than "
				"three more columns because the component set is the model's, not "
				"the table's: a decomposition that gains a component must not "
				"require a schema change here."
			),
		),
	),
)

LOSSES_MITIGATION = ArtefactSchema(
	name="losses_mitigation",
	columns=(
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="option", dtype="str", description="Intervention name."),
		ColumnSpec(
			name="loss_reduction",
			dtype="float",
			unit="MWh",
			description="Annual loss reduction, summed over the series.",
		),
		ColumnSpec(name="capex", dtype="float", unit="USD", description="Capital cost."),
		ColumnSpec(
			name="payback_years",
			dtype="float",
			unit="years",
			description="Payback, or NaN where savings are below the measurement floor.",
		),
	),
)

# --------------------------------------------------------------------------
# Resilience
# --------------------------------------------------------------------------

RESILIENCE_METRICS = ArtefactSchema(
	name="resilience_metrics",
	columns=(
		ColumnSpec(name="metric", dtype="str", description="Index name, e.g. SAIDI."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(name="value", dtype="float", description="The index value."),
		ColumnSpec(name="unit", dtype="str", description="The unit the value is stated in."),
		ColumnSpec(name="period", dtype="str", description="Period the index covers."),
	),
)

RESILIENCE_CONTINGENCY = ArtefactSchema(
	name="resilience_contingency",
	columns=(
		ColumnSpec(name="element_id", dtype="str", description="Contingency element."),
		ColumnSpec(name="element_type", dtype="str", description="line or transformer."),
		ColumnSpec(name="country_iso", dtype="str", description="ISO 3166-1 alpha-2."),
		ColumnSpec(
			name="load_shed_mw",
			dtype="float",
			unit="MW",
			description="Unserved load with the element out.",
		),
		ColumnSpec(
			name="overloaded_elements",
			dtype="int",
			description="Elements overloaded in the post-contingency state.",
		),
		ColumnSpec(name="severity", dtype="str", description="Severity band."),
	),
)

# --------------------------------------------------------------------------
# The register
# --------------------------------------------------------------------------

SERVING_SCHEMAS: Final[MappingProxyType[str, ArtefactSchema]] = MappingProxyType(
	{
		"market_prices": MARKET_PRICES,
		"market_capture_rates": MARKET_CAPTURE_RATES,
		"market_ppa_benchmarks": MARKET_PPA_BENCHMARKS,
		"outage_forecast": OUTAGE_FORECAST,
		"outage_history": OUTAGE_HISTORY,
		"outage_validation": OUTAGE_VALIDATION,
		"maintenance_predictions": MAINTENANCE_PREDICTIONS,
		"losses_decomposition": LOSSES_DECOMPOSITION,
		"losses_mitigation": LOSSES_MITIGATION,
		"resilience_metrics": RESILIENCE_METRICS,
		"resilience_contingency": RESILIENCE_CONTINGENCY,
	}
)
"""Every serving table, by projection name."""


PUBLISHED_TABLES: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		"market_prices": "data/processed/market/prices.parquet",
		"market_capture_rates": "data/processed/market/capture_rates.parquet",
		"market_ppa_benchmarks": "data/processed/market/ppa_benchmarks.parquet",
		"outage_forecast": "data/processed/outages/forecast.parquet",
		"outage_history": "data/processed/outages/history.parquet",
		"outage_validation": "data/processed/outages/validation.parquet",
		"maintenance_predictions": "data/processed/maintenance/predictions.parquet",
		"losses_decomposition": "data/processed/losses/decomposition.parquet",
		"losses_mitigation": "data/processed/losses/mitigation.parquet",
		"resilience_metrics": "data/processed/resilience/metrics.parquet",
		"resilience_contingency": "data/processed/resilience/contingency.parquet",
	}
)
"""Each projection name to the path the API reads it from.

The path is declared once, here, and the repository's literals are checked
against it. A projection that wrote somewhere else would pass every test that
reads its return value and serve nothing.
"""


UNPROJECTABLE: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		"data/processed/losses/tlens.parquet": (
			"`TlensRowOut` serves transmission/distribution/collection loss "
			"percentages by country-year. No layer computes those and no source "
			"provides them; `spec4-base.md` §22 lists `/api/v1/losses/tlens` as a "
			"'Critical line ranking', which is `TlensEntry`. The served view is a "
			"product the specification does not ask for, so there is nothing to "
			"project from. Either the view changes to the ranking the spec names "
			"or a T&D loss source is registered; inventing a percentage is not an "
			"option."
		),
	}
)
"""Serving paths with **no producer at all**, and why.

Named explicitly rather than left implicit, following
``UNIMPLEMENTED_FETCHERS`` in `tests/ci/test_io_registry.py`: a named gap
fails a test when it changes, so it cannot grow silently and cannot be closed
without the test being updated. An unnamed gap is indistinguishable from
coverage.

This is not the same as :data:`PRODUCED_ELSEWHERE`. A path here is one the API
serves and nothing writes; a path there is one a layer stage writes directly,
with its own schema, and for which a serving projection would be a second
definition of the same artefact.
"""


PRODUCED_ELSEWHERE: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		"data/processed/topology.parquet": "topology",
	}
)
"""Paths the API reads that a **layer stage** writes, keyed by path to stage.

``data/processed/topology.parquet`` is written by ``@stage("topology")`` against
``alea.planning.schemas.TOPOLOGY`` -- the same artefact the network builder reads
and the same rows the GeoJSON beside it carries. Projecting it here would be a
second definition of one artefact, which is how two files that agree today stop
being one source of truth.

The stage name is recorded so the gate can check it is *registered*. A path
claimed as produced elsewhere, whose stage no longer exists, is a path with no
producer wearing an exemption -- the failure this register exists to catch.
"""


PROJECTION_STAGES: Final[MappingProxyType[str, str]] = MappingProxyType({})
"""Tables a projection **stage** writes, keyed by table name to stage name.

Empty, and deliberately so: no projection has a stage yet. This is the register
that makes "wired" a claim someone makes rather than an inference the gate
draws, and the inference is why it exists.

The gate cannot decide a table is produced from a *name match* against the stage
registry. `outage_history` is both a serving table (`data/processed/outages/
history.parquet`) and a layer stage, and the layer stage writes
`data/processed/outage_history.parquet` -- a different path holding a different
quantity. Inferring production from the shared name marked the serving table
produced while nothing wrote it, which is the defect this whole package closes,
reproduced inside its own gate.

So a table is produced only when this register names the stage that writes it,
and `test_every_projection_stage_is_registered` checks that stage exists. Adding
the first projection stage adds the entry here in the same change.
"""


UNWIRED: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		"data/processed/market/prices.parquet": (
			"Needs a solved network's marginal prices keyed by bus and a bus-to-"
			"country mapping. `project_prices` refuses without the mapping, and no "
			"artefact carries one: buses have lon/lat and no country, and neither "
			"the topology nor the fleet schema has a country column. A price row "
			"labelled 'Nairobi' where the model says ISO 3166-1 alpha-2 filters to "
			"nothing while looking correct."
		),
		"data/processed/market/capture_rates.parquet": (
			"Needs `market.capture.cannibalisation_curve` over a price series. No "
			"stage invokes the market layer at all -- `rules/market.smk` is empty "
			"by design (`06-layer3-market.md`: Layer 3 runs off the planning "
			"layer's artefacts) and nothing has wired that step yet."
		),
		"data/processed/market/ppa_benchmarks.parquet": (
			"Needs `market.ppa.ppa_curve`. Same missing invocation as the capture "
			"curve: the market layer is a library with no stage and no rule."
		),
		"data/processed/outages/forecast.parquet": (
			"Needs the weather feature frame `forecast_to_artefact` trains on. No "
			"stage builds that frame; the forecaster is reachable only from a test."
		),
		"data/processed/outages/history.parquet": (
			"Needs an interruption-event table -- `resilience.events_from_frame` "
			"requires zone, started_at and duration_minutes. Nothing writes one. "
			"The VIIRS detector writes `data/processed/outage_history.parquet`, a "
			"zone-flagged-fraction series, which is a different quantity: serving "
			"a detection probability where the API documents a customer "
			"interruption is a wrong number, not a missing one."
		),
		"data/processed/outages/validation.parquet": (
			"`@stage(\"outage_validation\")` reads the detector's zone series and "
			"the GridWatch truth and writes a JSON skip-or-metrics document, not "
			"this table, and it has no rule. Projecting it needs that stage's "
			"output reshaped and the stage invoked."
		),
		"data/processed/maintenance/predictions.parquet": (
			"Needs a DGA/work-order frame `maintenance_to_artefact` fits. That data "
			"is credentialed and the model refuses to fit without it, so this table "
			"is empty until a utility supplies the export -- a data arrival, not a "
			"wiring task."
		),
		"data/processed/losses/decomposition.parquet": (
			"Needs `network_arrays.json` and `dispatch.parquet` under "
			"`paths.processed`. `@stage(\"tlens\")` reads both and **nothing writes "
			"either**; no rule invokes that stage. The decomposition has the same "
			"missing inputs."
		),
		"data/processed/losses/mitigation.parquet": (
			"Needs the same dispatch series and network arrays as the "
			"decomposition: `mitigation_to_artefact` ranks options against the "
			"losses each avoids, so it needs the decomposition's inputs before it "
			"can have an output. Same missing producer."
		),
		"data/processed/resilience/metrics.parquet": (
			"Needs `interruptions.parquet` and `zone_population.parquet`. "
			"`@stage(\"resilience\")` reads both, nothing writes either, and the "
			"stage has no rule. The population denominator is a proxy quantity that "
			"must arrive with its own provenance, so inventing it is not an option."
		),
		"data/processed/resilience/contingency.parquet": (
			"Needs the N-1 sweep over a solved network's arrays. Same missing "
			"`network_arrays.json` and dispatch as the loss tables."
		),
	}
)
"""Serving paths a projection declares but **no registered stage writes**.

The projection functions are correct and tested; what is absent is the pipeline
step that reads a layer result and calls one. Naming each here rather than
leaving it implicit is the same discipline as :data:`UNPROJECTABLE`, and the
distinction it draws is the whole point of this package:

    a path in :data:`PUBLISHED_TABLES` is *declared*; a path here is not
    *produced*.

Treating the declaration as production is exactly how eleven routes served empty
pages while their own test suite passed. `test_every_projected_table_is_produced`
asserts every declared path is either written by a registered stage or named
here, so a table cannot be added to the register and quietly count as served.

**What would close this.** A stage per table that reads the layer's artefact at
a conventional path and calls the projection. That needs the layer stages to
write conventional outputs -- today `tlens`, `resilience` and `outage_validation`
read six input paths nothing writes and no rule invokes -- which is a pipeline
task across Layers 3 and 4, not a Layer 8 one. The gap is recorded so it is
visible and bounded, not closed by inventing the inputs.
"""


def serving_schema(name: str) -> ArtefactSchema:
	"""The schema for a projection, by name.

	Raises rather than returning ``None``: a projection with no declared schema
	is a projection nothing checks, which is the state this package exists to
	end.
	"""
	if name not in SERVING_SCHEMAS:
		raise KeyError(
			f"no serving schema {name!r}; declared: {', '.join(sorted(SERVING_SCHEMAS))}"
		)
	return SERVING_SCHEMAS[name]


__all__ = [
	"LOSSES_DECOMPOSITION",
	"LOSSES_MITIGATION",
	"MAINTENANCE_PREDICTIONS",
	"MARKET_CAPTURE_RATES",
	"MARKET_PPA_BENCHMARKS",
	"MARKET_PRICES",
	"OUTAGE_FORECAST",
	"OUTAGE_HISTORY",
	"OUTAGE_VALIDATION",
	"PRODUCED_ELSEWHERE",
	"PUBLISHED_TABLES",
	"RESILIENCE_CONTINGENCY",
	"PROJECTION_STAGES",
	"RESILIENCE_METRICS",
	"SERVING_SCHEMAS",
	"UNPROJECTABLE",
	"UNWIRED",
	"serving_schema",
]
