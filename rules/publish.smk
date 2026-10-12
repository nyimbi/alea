# SPDX-License-Identifier: MIT
"""Layer 8: the serving tables the API reads.

`alea.publish.views` classifies every path `api.repository` reads, and until
`@stage("resilience_contingency")` existed the `UNWIRED` register held all
eleven: a projection declared and no stage ran it. `resilience_contingency` was
the first rule that runs one and `market_prices` the second, and the register
shrinks with each -- `PROJECTION_STAGES` gains the entry, `UNWIRED` loses one,
and `test_the_unwired_set_is_exactly_what_is_recorded` fails if only one moves.

**Why the output is a nested path.** Every other rule writes
``data/processed/<stage>.<suffix>``. A serving table is not a stage's dataset:
it is the shape a *route* reads, and `PUBLISHED_TABLES` names it at
``data/processed/resilience/contingency.parquet``. The rule declares that path
rather than a stage-shaped one, because the path is what the API reads and a
producer that wrote elsewhere would serve nothing while its own tests passed.
"""

rule resilience_contingency:
	"""The N-1 sweep as per-element rows, at the path the API reads."""
	input:
		processed("network_arrays"),
		processed("dispatch", ".parquet")
	output:
		# The published path, spelled as `PUBLISHED_TABLES` spells it. The gate
		# reads this and compares it against `dvc.yaml`'s outs, so the two cannot
		# come to disagree about where the API's table is.
		processed("resilience/contingency", ".parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "resilience_contingency",
				"--out", output[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


rule market_prices:
	"""The solved network's marginal prices, at the path the API reads.

	The stage resolves the network itself -- newest-first in
	``results/networks``, the same way `@stage("network_arrays")` does -- because
	a price is not in the arrays bundle and the filename carries a content hash
	no rule can know at parse time. So the rule declares the directory, and a
	new solve re-runs the stage, which is exactly when the prices change.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("market/prices", ".parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "market_prices",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)
