# SPDX-License-Identifier: MIT
"""Hydro profiles, from the atlas export.

The register marks `hydro_atlas` unavailable -- the specification cites a
placeholder record -- and the builder refuses rather than writing a flat
profile, because a hydro profile of constant 1.0 makes every reservoir a
baseload plant and looks like a result. The rule declares the committed export
as an input, so an un-resolved atlas is a dependency Snakemake cannot satisfy,
which is the same refusal one step earlier and with the path in the message.
"""

rule hydro_profiles:
	"""Monthly capacity factors per hydro plant."""
	input:
		manual_export("hydro_atlas")
	output:
		processed("hydro_profiles")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "hydro_profiles",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("hydro_export", MANUAL_EXPORTS["hydro_atlas"]),
				*params.flags,
			)
		)
