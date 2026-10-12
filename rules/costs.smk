# SPDX-License-Identifier: MIT
"""Technology costs and fuel prices.

Both feed expansion, not dispatch. The two currency conversions -- IRENA's USD
costs and a local-currency pump price -- are done by the builders at the rate in
`config.costs`, whose date is recorded alongside it; the rule passes no rate,
because a rate in a rule is a rate that is not in the config the artefact's
provenance cites.
"""

rule costs:
	"""Technology capital and operating costs from the committed IRENA export."""
	input:
		manual_export("irena_costs")
	output:
		processed("costs")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "costs",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("irena_export", MANUAL_EXPORTS["irena_costs"]),
				*params.flags,
			)
		)


rule fuel_prices:
	"""Fuel prices in USD/MWh, from the fetched Global Petrol Prices payload."""
	input:
		f"{RAW}/global_petrol_prices/{FETCH_MARKER}"
	output:
		processed("fuel_prices")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "fuel_prices",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				*params.flags,
			)
		)
