# SPDX-License-Identifier: MIT
"""`topology` and `fleet`: the two datasets everything else is placed against.

Both are one `alea build` call. `topology` writes the Parquet the pipeline
tracks and a GeoJSON beside it for a GIS; the rule declares the Parquet, which
is the artefact a network builder reads.

`fleet` declares the powerplantmatching export as an input rather than a
parameter, so a run against a tree without the export fails at dependency
resolution with the path in the message instead of failing inside the builder
after the scheduler has committed to the job.
"""

rule topology:
	"""Transmission lines from the World Bank grid map."""
	input:
		f"{RAW}/worldbank_grid_map/{FETCH_MARKER}"
	output:
		processed("topology")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "topology",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				*params.flags,
			)
		)


rule fleet:
	"""The generation fleet from the committed powerplantmatching export."""
	input:
		manual_export("powerplantmatching")
	output:
		processed("fleet")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "fleet",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("powerplant_export", MANUAL_EXPORTS["powerplantmatching"]),
				*params.flags,
			)
		)
