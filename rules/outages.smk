# SPDX-License-Identifier: MIT
"""Outage evidence (Track B): VIIRS detections and GridWatch ground truth.

Both stages read raw payloads the register says exist but for which no fetcher
is implemented -- `viirs_vnp46a2` and `gridwatch` are credentialed, and
`alea fetch` raises for them. So neither rule declares a `fetch_*` input: the
granules and the GridWatch export arrive out of band, and the rules declare the
artefacts a human places in the lake.

That is a stated gap, not an oversight. `tests/ci/test_io_registry.py` names the
same two sources in `UNIMPLEMENTED_FETCHERS`, and implementing a fetcher fails
that test until the list shrinks -- so the gap cannot grow quietly in either
place.

`outage_truth` requires `GRIDWATCH_TOKEN` in the environment and refuses without
it. That refusal is deliberate and is not worked around here: the validation
stage records its own skip, and a ground-truth artefact built with no ground
truth would validate every detector against nothing.
"""

rule outage_history:
	"""VIIRS-detected outage evidence per grid zone."""
	output:
		processed("outage_history")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "outage_history",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				*params.flags,
			)
		)


rule outage_truth:
	"""GridWatch ground truth, from the committed sensor export."""
	input:
		manual_export("gridwatch")
	output:
		processed("outage_truth")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "outage_truth",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("gridwatch_export", MANUAL_EXPORTS["gridwatch"]),
				*params.flags,
			)
		)


rule outage_forecast:
	"""The daily 24-hour outage probability, per grid zone.

	The producer the daily cadence's required section was waiting for. The
	register recorded the gap as two: `forecast_to_artefact` writes the model's
	*metrics*, and nothing turned a fitted `Forecaster` into a probability per
	zone -- `predict_proba` existed with no caller. The interval was the second
	gap and the harder one: the section declares an `Interval` column and
	`assemble.py` reads a band from `interval_low`/`interval_high`, while
	`ForecastMetrics` had no interval field and the module had no calibration
	function.

	So this rule runs a stage that predicts forward and bands the result by the
	model's own held-out error. That band is a *residual quantile*, not a
	calibrated predictive interval, and the artefact's provenance says so in
	those words -- the two print the same two numbers and mean different things.

	The input is `outage_history` because the forecast is a function of the
	detector's observations and of nothing else: the features are calendar plus
	the lagged outage rate, and the calendar needs no observation.
	"""
	input:
		processed("outage_history")
	output:
		processed("outage_forecast")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "outage_forecast",
				"--out", output[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


rule project_outage_forecast:
	"""`outage_forecast` at the dated path the daily report reads.

	The section declares ``outages/forecast/{date}.parquet``. A daily report
	generated at 06:00 covers *yesterday*, which `period_for` resolves inside the
	projection -- a literal date here would name a file no daily report opens,
	and the symptom would be an absent section rather than an error. This is the
	daily cadence's one `required=True` section, so "absent" means the report
	raises rather than warns.
	"""
	input:
		processed("outage_forecast")
	output:
		report_artefact("daily", "outages/forecast/{date}.parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"project", "daily", "outage_forecast",
				"--source", input[0],
				"--config", CONFIG,
				*params.flags,
			)
		)
