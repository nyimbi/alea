# SPDX-License-Identifier: MIT
"""Fetch rules: one per source `alea fetch` can retrieve.

Each rule is `alea fetch <id>` and a touch. There is no download logic here and
there cannot be one: AD-5 makes the CLI the only entry point, and the fetch
implementation, its credential handling and its provenance are all in
`alea.io.fetchers` / `alea.io.pipeline`, where they are tested.

The register decides which sources appear. `fetchable()` lists the sources the
pipeline can retrieve, but a source with `Access.MANUAL` has a committed export
rather than a fetch (`02-data-pipeline.md` §1.1) and a source with no
implemented fetcher has nothing for `alea fetch` to call -- both raise inside
the CLI, so a rule for either would be a rule that can only fail. What is left
is the OPEN sources with a fetcher, and they are listed literally because
reading `registered_fetchers()` here would mean importing `alea` at parse time.

`tests/ci/test_orchestration_workflow.py` asserts this list is exactly the
register's fetchable-and-implemented set, so a new fetcher that never reaches
the workflow, or a rule for a source that cannot be fetched, fails the suite.
"""

# The touch target. A rule needs an output; the raw payload's own path carries
# its checksum, which is not knowable before the fetch runs, so the marker is
# what Snakemake orders on and what a second run finds.
FETCH_MARKER = ".fetched"

# Sources `alea fetch` can retrieve. Verified against the register by the
# workflow test named in the module docstring.
FETCHABLE = [
	"cmip6",
	"geothermal_atlas",
	"global_petrol_prices",
	"gwa_gsa",
	"jrc_bioenergy",
	"osm_africa",
	"repp_africa",
	"worldbank_grid_map",
]


rule fetch_all:
	"""Every retrievable source. A network run, so it is not the default target."""
	input:
		expand(f"{RAW}/{{source_id}}/{FETCH_MARKER}", source_id=FETCHABLE)


rule fetch_source:
	"""Retrieve one source into the immutable raw layer.

	A wildcard rule with an explicit membership check rather than one rule per
	source: the check is what makes the wildcard safe, because without it
	`data/raw/anything/.fetched` is a valid target and Snakemake would happily
	order a fetch for a source the register does not hold.

	`--force` is passed only when the run asks for it, so an ordinary run never
	repeats a download: the raw layer is content-addressed and `fetch_source`
	already returns a held payload without calling the fetcher.
	"""
	output:
		touch(f"{RAW}/{{source_id}}/{FETCH_MARKER}")
	params:
		# A lambda, not `force_flags` itself: Snakemake calls a bare callable in
		# `params` with the wildcards, and `force_flags` takes none.
		flags=lambda wildcards: force_flags(),
	run:
		from pathlib import Path

		if wildcards.source_id not in FETCHABLE:
			raise ValueError(
				f"no fetch rule is declared for {wildcards.source_id!r}; the register "
				f"decides what can be fetched and `alea fetch` raises for a manual or "
				f"unimplemented source. Declared: {', '.join(FETCHABLE)}"
			)
		marker = Path(output[0])
		marker.parent.mkdir(parents=True, exist_ok=True)
		shell(alea("fetch", wildcards.source_id, "--config", CONFIG, "--out", RAW, *params.flags))
