# SPDX-License-Identifier: MIT
"""National demand, and its disaggregation to buses.

`demand_hourly` needs the `demand_national` artefact, so the national rule's
output is the hourly rule's input and Snakemake orders them. It also needs a bus
weight vector -- population and GDP per bus, `02-data-pipeline.md` §3.1 -- which
is not a registered source and therefore is declared as a human artefact under
`resources/`.

`alpha`, the population/GDP blend, is passed explicitly rather than left to the
builder's default. §3.1 requires it be recorded in the provenance because an
unrecorded blend produces a map nobody can defend; passing it from the workflow
means the workflow is where the value is chosen and the artefact is where it is
proved.
"""

# The blend §3.1 defaults to, stated here so a run's parameters are visible in
# the workflow rather than only in a builder's signature.
DEFAULT_ALPHA = 0.5


rule demand_national:
	"""Annual national totals from the committed AFREC export."""
	input:
		manual_export("afrec_demand")
	output:
		processed("demand_national")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "demand_national",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("afrec_export", MANUAL_EXPORTS["afrec_demand"]),
				*params.flags,
			)
		)


rule demand_hourly:
	"""National demand split across buses at `alpha` population share."""
	input:
		processed("demand_national"),
		provided("bus_weights", WEIGHTS),
	output:
		processed("demand_hourly")
	params:
		alpha=config.get("alpha", DEFAULT_ALPHA),
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "demand_hourly",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("demand_national", processed("demand_national")),
				"--set", set_arg("bus_weights", WEIGHTS),
				"--set", set_arg("alpha", params.alpha),
				*params.flags,
			)
		)
