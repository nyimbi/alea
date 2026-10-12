# SPDX-License-Identifier: MIT
"""Sector coupling: the solved electricity network extended with the sectors.

`08-layer5-whatif.md` and `05-layer4-outages.md`'s DAG place the coupling off the
solved network, the same input `network_arrays` reads. The rule declares it the
same way -- `provided("solved_network", NETWORKS)` plus `--set network_dir=`,
because the solved network's filename is a content hash and is not knowable at
parse time (see the comment on `NETWORKS` in `rules/common.smk`).

The stage writes two artefacts from one coupling: the JSON table of coupled
assets, and the coupled network beside it. Only the JSON is declared as this
rule's output; the coupled network is the artefact `@stage("sector_coupling")`
writes for Layer 1 to solve under its own gates, and its path is derived from
the output rather than being a second stage output (there is no stage that reads
it back by a conventional name yet).

The coupled network carries the same `.coupled.nc` suffix `write_coupling_artefact`
derives, so `dvc status` sees it. It is declared below the JSON for the same
reason `network_arrays` declares `dispatch.parquet`: a change to it should be
visible to DVC rather than only to a reader.
"""

rule sector_coupling:
	"""A solved network extended with the sectors the config enables."""
	input:
		provided("solved_network", NETWORKS)
	output:
		processed("sector_coupling"),
		# Written by the same coupling from the same solve, at the path
		# `write_coupling_artefact` derives with `.with_suffix(".coupled.nc")`.
		# Declared for the same reason `network_arrays` declares `dispatch.parquet`:
		# a change to it should be visible to `dvc status`, not only to Layer 1.
		processed("sector_coupling", ".coupled.nc"),
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "sector_coupling",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("network_dir", NETWORKS),
				*params.flags,
			)
		)
