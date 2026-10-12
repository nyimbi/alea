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
