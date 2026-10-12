# SPDX-License-Identifier: MIT
"""The ERA5 cutout and the renewable profiles built from it.

§4's DAG is `fetch_era5 -> build_cutout -> build_renewable_profiles`, and the
two are separate rules because they have different costs: the cutout is the
largest artefact in the pipeline (tens of GB for Africa) and is DVC-tracked and
never rebuilt in CI, while the profiles are cheap and change whenever the layout
assumptions do. One rule for both would rebuild a multi-hour download to change
a turbine class.

The cutout is not fetched through `alea fetch`: the register marks `era5_cutout`
as an OPEN source with no implemented fetcher, and the download is atlite's, not
this project's. `alea build cutout` calls atlite and writes the file, and the
rule declares that file as the profiles' input.

Both the `.nc` and its `.nc.aux` sidecar are declared. atlite writes the
sidecar; checksumming the `.nc` alone yields a cutout that verifies and fails to
open (`02-data-pipeline.md` §1.1), and a rule that declared only the `.nc` would
let a stale sidecar pass as current.
"""

# The NetCDF the cutout stage writes, and the sidecar atlite writes beside it.
# Under `data/processed` like every other stage output, so `processed("cutout")`
# in the Snakefile's default target and the rule that produces it cannot name
# two different paths -- which they did while this was a literal here.
CUTOUT = processed("cutout")


rule cutout:
	"""Download the ERA5 cutout covering the topology's own extent.

	The extent comes from the topology artefact rather than a bounding box
	written here: the registry's countries carry no coordinates, and a box typed
	into a rule is a box that disagrees with the network the profiles attach to
	the first time the network changes.
	"""
	input:
		processed("topology")
	output:
		CUTOUT,
		f"{CUTOUT}.aux",
	params:
		flags=lambda wildcards: force_flags(),
	run:
		from pathlib import Path

		Path(output[0]).parent.mkdir(parents=True, exist_ok=True)
		shell(
			alea(
				"build", "cutout",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("raw_root", RAW),
				"--set", set_arg("cutout_path", CUTOUT),
				"--set", set_arg("topology", processed("topology")),
				*params.flags,
			)
		)


rule renewable_profiles:
	"""Capacity factors per bus, from the cutout.

	`buses` and `bus_points` come from the topology artefact: a profile keyed to
	a bus no network contains is a file nothing can attach, and a capacity
	factor with no location is a country average that erases the resource
	gradient the profiles exist to carry.
	"""
	input:
		CUTOUT,
		processed("topology"),
	output:
		processed("renewable_profiles")
	params:
		flags=lambda wildcards: force_flags(),
	run:
		shell(
			alea(
				"build", "renewable_profiles",
				"--out", output[0],
				"--config", CONFIG,
				"--set", set_arg("cutout_path", CUTOUT),
				"--set", set_arg("topology", processed("topology")),
				*params.flags,
			)
		)
