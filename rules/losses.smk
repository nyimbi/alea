# SPDX-License-Identifier: MIT
"""Layer 4b: a solved network as the arrays the loss kernel takes.

`@stage("tlens")` reads ``network_arrays.json`` and ``dispatch.parquet`` under
``paths.processed`` and, until this rule existed, **nothing wrote either** --
which is why four serving tables sat in `alea.publish.views.UNWIRED` while their
projections passed their own tests. `alea.planning.arrays` is the producer and
this is its rule.

**Why the input is a directory and not a file.** `alea solve` writes
``{network_id}-{horizon}.nc`` and the id is a content hash of the buses and
lines, so the filename is not knowable at parse time. A rule cannot declare a
dependency on a path it cannot spell, and declaring the whole directory is the
honest form of that: Snakemake re-runs this stage when anything in
``results/networks`` changes, which is exactly when the newest solve might have
become a different one. The stage records the file it actually resolved in its
provenance, so a reader sees which network the arrays came from.

**Why this is not `sector_coupling`'s problem repeated.** That stage's reason for
having no rule is that the workflow sequences no solve. This stage does not
solve: it converts a network an operator has already solved, the same way
`fleet` reads a powerplantmatching export a human produced once. A missing
``results/networks`` fails at dependency resolution with the directory named,
rather than inside the builder after the scheduler has committed to the job --
and the message the operator needs is "run `alea solve`", which
``ABSENT_MESSAGES`` supplies.
"""

rule network_arrays:
	"""A solved network as the loss kernel's arrays and dispatch series."""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("network_arrays"),
		# Written by the same stage from the same solve. Declared so a change to
		# it is visible to `dvc status` rather than only to `tlens`'s reader, and
		# because the two are positional partners: the arrays number the buses
		# and the dispatch's columns are in that order.
		processed("dispatch", ".parquet"),
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "network_arrays",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)


rule tlens:
	"""Rank branches by the energy their outage would leave unserved.

	`@stage("tlens")` reads the two artefacts the rule above writes, from
	``paths.processed`` and by their conventional names -- so the inputs here are
	the *same paths the rule above declares as outputs*, and Snakemake orders the
	two without either naming the other's stage.
	"""
	input:
		processed("network_arrays"),
		processed("dispatch", ".parquet")
	output:
		processed("tlens")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "tlens",
				"--out", output[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


rule critical_lines:
	"""Every branch's loading against its own rating, over the dispatch series.

	The *second* reader of the two artefacts `network_arrays` writes, and the
	reason `dispatch.parquet` is declared as that rule's second output: the
	arrays number the buses and the dispatch's columns are in that order, so a
	dispatch from a different solve is a different measurement, not a stale one.

	The section this feeds is `weekly.py`'s ``critical_lines``, which reads
	``results/outages/critical/{date}.parquet``. This rule writes the processed
	form; the dated path under ``results/`` is the projection's `--out` and is
	not this rule's business -- one artefact, one path, and the report's date is
	the cadence's, not the workflow's.
	"""
	input:
		processed("network_arrays"),
		processed("dispatch", ".parquet")
	output:
		processed("critical_lines")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "critical_lines",
				"--out", output[0],
				"--config", CONFIG,
				*params.flags,
			)
		)
