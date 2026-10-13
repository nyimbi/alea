# SPDX-License-Identifier: MIT
"""Layer 3: the report sections a solved network's clearing produces.

`06-layer3-market.md` runs Layer 3 off the solved networks rather than a source
of its own, so this file had no rules and said so. It has four now. Two are the
sections `reporting/monthly.py` and `reporting/quarterly.py` declare as
`required=True` -- the two the register recorded as unproduced, and the reason
*neither* cadence could be generated from the pipeline; a required section whose
artefact is absent raises rather than warns. One is the daily price series. The
last is the weekly summary, which is optional and therefore *warned* rather than
raised -- an absence a green suite cannot see, which is why the register's entry
for it was worth more than the warning was.

**These rules write the processed form, not the dated one.** `rules/losses.smk`'s
``critical_lines`` states the precedent: the dated path under ``results/`` is the
projection's ``--out`` and is not the rule's business -- one artefact, one path,
and the report's date is the cadence's, not the workflow's. So these write
``data/processed/market_report.parquet`` and its sibling, and the section's
``market/monthly/{date}.parquet`` is a projection someone passes a date to. The
report-shaped columns are the same in both cases: a row carries ``label``,
``value`` and ``unit`` plus whatever the section declares, which is what
``critical_lines`` writes too.

**Why the network is a directory input.** The solved network's filename carries a
content hash no rule can know at parse time, so the rule declares
``results/networks`` and the stage picks the newest -- the same declaration
`rules/publish.smk`'s ``market_prices`` makes, and for the same reason.
"""

rule market_report:
	"""The monthly market section's clearing rows, per carrier.

	One row per carrier: the MWh it dispatched over the network's snapshots and
	the volume-weighted price it received. Both numbers travel in the row, and
	they have to -- the section declares two numeric columns, and the reader
	refuses a row that carries only the primary.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("market_report")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "market_report",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)


rule market_summary:
	"""The weekly market section's clearing rows, per carrier.

	The third report section read off one clearing. Its columns are
	``["Carrier", "Volume", "Capture price", "Basis"]`` -- not the monthly
	section's ``Average price`` -- and that difference is load-bearing rather
	than cosmetic: the reader binds each numeric header to the row column
	*naming* it, so a frame carrying only ``average_price`` raises instead of
	rendering. The capture price is the volume-weighted price each carrier
	received, which is a different quantity from the system mean on any stack
	that is not flat.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("market_summary")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "market_summary",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)


rule price_forecast:
	"""The daily price section's clearing rows, per hour.

	Writes the processed form and lets the projection land it, the same split
	``market_report`` uses. The section is titled "day-ahead" and the series is
	the solve's own snapshots rather than a forecast -- no price-forecast model
	exists here, and the artefact's provenance says so rather than inventing a
	day ahead.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("price_forecast")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "price_forecast",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)


rule market_outlook:
	"""The quarterly outlook section's clearing prices, per period.

	Same input and same self-resolved network as ``market_report``: the outlook
	is the same clearing read at the horizons the solve supports rather than at
	its snapshots, so the two stages resolve one network and read it two ways.
	The series is the solve's own horizons, not a four-quarter forecast -- no
	price-forecast model exists here, and the artefact's provenance says so.
	"""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("market_outlook")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "market_outlook",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)
