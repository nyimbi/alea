# SPDX-License-Identifier: MIT
"""Layer 6: the report sections that are not a layer's own workflow stage.

`reporting/producers.py` records which layer writes each declared section, and
the sections that had no producer were the register's largest gap. Most of them
are blocked on something that does not exist -- a weather layer, a demand
forecast, a CMP target set -- and `UNPRODUCED` names each one. The rest are
*wiring*: the quantity is already computed and no artefact carries it at the
dated path a section reads.

This file holds the wired ones. A section lands here rather than in its own
layer's rule file when it advances no layer: `capacity_update` is not a planning
step, it is the monthly report reading the planning layer's solved network, and
filing it under `rules/losses.smk` beside `network_arrays` would say it is part
of Layer 4b.

**Why the network is a directory input.** The solved network's filename carries
a content hash no rule can know at parse time, so the rule declares
``results/networks`` and the stage resolves it -- the same declaration
`rules/market.smk` and `rules/publish.smk` make, and for the same reason.

**Why these write the processed form.** `rules/losses.smk`'s ``critical_lines``
states the precedent: the dated path under ``results/`` is the projection's
``--out`` and is not the rule's business. One artefact, one path, and the
report's date is the cadence's, not the workflow's.
"""

rule capacity_update:
	"""Installed capacity by carrier, differenced against the previous solve.

	Reads the directory twice -- newest, and newest-but-one -- because the
	section asks for the change since the previous month and one solved network
	contains no previous month. A directory holding a single solve writes the
	capacity with no ``change`` column at all, which is a refusal to invent a
	zero dressed as a column.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("capacity_update")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "capacity_update",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)


# --------------------------------------------------------------------------
# The projection: a stage's output, at the dated path its section reads
# --------------------------------------------------------------------------
#
# Every rule above writes ``data/processed/<stage>.<suffix>``; a section reads
# ``results/<dir>/{date}.parquet``. The two docstrings in this repository that
# describe the bridge -- `rules/losses.smk`'s ``critical_lines`` and this file's
# own header -- say the dated path "is the projection's ``--out`` and is not
# this rule's business". No such projection existed: no subcommand, no rule, no
# test. So `alea report monthly` failed with "no artefact" while the producing
# rule exited 0, and ``reporting.producers.PRODUCERS`` recorded that a *function*
# exists rather than that a section is deliverable.
#
# This rule is that projection. `alea project` resolves the date from the
# cadence's own period -- a monthly report issued on the 1st covers the month
# that just ended -- and takes the destination from the section's own declared
# ``artefact``, so neither can drift from where the reader looks. The source is
# the processed artefact the rule above declares, so Snakemake orders the two
# without either naming the other's stage.

rule project_capacity_update:
	"""`capacity_update` at the dated path the monthly report reads."""
	input:
		processed("capacity_update")
	output:
		report_artefact("monthly", "planning/capacity/{date}.parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"project", "monthly", "capacity_update",
				"--source", input[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


# --------------------------------------------------------------------------
# The projections that belong to another layer's rule file
# --------------------------------------------------------------------------
#
# `critical_lines` and the two market sections are produced by
# `rules/losses.smk` and `rules/market.smk`, and their projections live here
# rather than beside them for the reason this file's header gives: a projection
# advances no layer. `project_critical_lines` is not a loss computation and
# `project_market_report` is not a market computation -- each moves an artefact
# its own layer already wrote to the dated path Layer 6 reads, so filing either
# under its producer's rule file would say the delivery is part of that layer.
#
# Their *sources* are still that layer's, declared here by the processed path
# rather than by importing the producer's rule: Snakemake resolves the
# dependency from the filename, so this file needs no knowledge of which rule
# wrote it.
#
# The two market ones matter more than the third. `market_report` and
# `market_outlook` are `required=True`, so the monthly and quarterly cadences
# *raise* without them -- and `market_outlook`'s date is the quarter that ended,
# not the day the rule ran, which `reporting.schemas.period_for` resolves and a
# projection stamped with its own run date would get wrong silently.

rule project_critical_lines:
	"""`critical_lines` at the dated path the weekly report reads."""
	input:
		processed("critical_lines")
	output:
		report_artefact("weekly", "outages/critical/{date}.parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"project", "weekly", "critical_lines",
				"--source", input[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


rule project_market_report:
	"""`market_report` at the dated path the monthly report reads.

	Required to the monthly cadence, so without this rule `alea report monthly`
	raises rather than warning -- and the section is the one a reader opens the
	report for.
	"""
	input:
		processed("market_report")
	output:
		report_artefact("monthly", "market/monthly/{date}.parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"project", "monthly", "market_report",
				"--source", input[0],
				"--config", CONFIG,
				*params.flags,
			)
		)


rule project_market_outlook:
	"""`market_outlook` at the dated path the quarterly report reads.

	The date is the interesting part: a quarterly report issued on the 1st
	covers the quarter that just ended, and the projection asks the cadence for
	that day rather than stamping the run date. A literal here would be a file
	no quarterly report opens, and the symptom would be an absent section.
	"""
	input:
		processed("market_outlook")
	output:
		report_artefact("quarterly", "market/outlook/{date}.parquet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"project", "quarterly", "market_outlook",
				"--source", input[0],
				"--config", CONFIG,
				*params.flags,
			)
		)
