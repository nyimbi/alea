# SPDX-License-Identifier: MIT
"""The `scenario_update` producer: a parameter sweep as the section's rows.

`reporting/quarterly.py`'s ``scenario_update`` reads
``whatif/frontier/{date}.parquet`` and declares the columns
``["Scenario", "Capacity", "Cost", "Basis"]``. `alea.whatif` could already
sweep a parameter (`sweep_parameter`, `efficient_frontier`) and
`alea.api.whatif` could write a frontier -- as a *document* to a caller-chosen
path, from an HTTP job, which is a route's shape and not a report's. Nothing
ran a sweep from a rule and landed the section's frame at the section's own
path, which `reporting/producers.py` recorded as "no layer writes the frontier
as an artefact".

**Why the sweep goes through `sweep_parameter` and not `efficient_frontier`.**
The frontier frame carries cost, emissions and renewable share, and the section
asks for capacity -- which the *result* carries (`capacity_mix_mw`) and the
frontier frame drops. Re-deriving capacity from the frontier's cost would be
inventing it; reading it off the outcome is not. So the sweep is taken one
level down, where each point still has its `ScenarioResult`, and the two frames
differ because they answer different questions: the frontier plots a trade-off,
the section tabulates what each scenario builds.

**One row per scenario, not per carrier.** The section's first column is
``Scenario`` and its prose is "capacity and cost ranges across the scenario
set", so a row is one sweep point and ``capacity`` is the system total at that
point. A per-carrier breakdown would need a carrier column the section does not
declare, and summing into a total is the quantity the range is *over* -- the
range is what the section reports, and a reader asking which carrier moved is
asking a different section's question.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError, read_provenance, sha256_file
from alea.io.pipeline import BuildContext, skip_if_current, stage, write_stage
from alea.logging import get_logger, new_run_id
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

#: Where a solved network lives, relative to the results root.
#:
#: The same directory `alea.planning.arrays` resolves its networks from, spelled
#: here rather than imported so this module does not depend on a layer above it.
#: A second constant is a drift risk, and the alternative -- importing Layer 1's
#: private constant into Layer 5 -- is a coupling that outlives its reason.
NETWORK_DIR = "results/networks"


def _code_version() -> str:
	from alea import __version__

	return __version__


def _newest_network(directory: Path) -> Path:
	"""The most recently written solved network in ``directory``.

	Newest by mtime rather than alphabetically: the filenames are
	``<content-hash>-<horizon>.nc``, so alphabetical order is the order of a
	hash and means nothing.
	"""
	candidates = sorted(
		(path for path in directory.glob("*.nc") if path.is_file()),
		key=lambda path: path.stat().st_mtime,
		reverse=True,
	)
	if not candidates:
		raise ArtefactError(
			f"no solved network in {directory}; `scenario_update` sweeps a base "
			f"network, and a frontier over nothing is not a scenario set. Solve "
			f"one first, or point `network_dir` at the directory holding it."
		)
	return candidates[0]


def frontier_rows(outcomes: list[Any], parameter: str) -> pd.DataFrame:
	"""The `scenario_update` frame: one row per sweep point.

	The frame `reporting/quarterly.py`'s ``scenario_update`` section reads, whose
	columns are ``["Scenario", "Capacity", "Cost", "Basis"]``. Two of those are
	numeric, so `_rows_for` binds each header to the row column naming it:
	``capacity`` and ``cost`` are written as columns of their own rather than
	folded together, because a row carrying one number under two headers is the
	duplication `_rows_for` refuses.

	``label`` is the parameter value and not the scenario's UUID. A UUID7 is
	stable and tells a reader nothing about where the point sits on the sweep;
	the value is what distinguishes one row from the next, and the section's
	first column is ``Scenario`` in the sense of "a point in the scenario set".
	The parameter's own name travels in the label too, because a table of
	numbers under one header is unreadable without it.
	"""
	assert outcomes, "a frontier needs at least one outcome"
	assert parameter, "a frontier must name the parameter it swept"

	labels: list[str] = []
	capacity: list[float] = []
	cost: list[float] = []
	for outcome in outcomes:
		result = outcome.result
		params = result.params
		value = getattr(params, parameter)
		labels.append(f"{parameter}={value:g}")
		# The system total at this point. `capacity_mix_mw` is carrier -> MW and
		# is empty for a network with no generators, which is a real state and
		# sums to 0.0 rather than raising.
		capacity.append(float(sum(result.capacity_mix_mw.values())))
		cost.append(float(result.total_cost_usd))

	return pd.DataFrame(
		{
			"label": labels,
			"value": capacity,
			"unit": ["MW"] * len(labels),
			"capacity": capacity,
			"cost": cost,
		}
	)


def scenario_update_to_artefact(
	config: Config,
	out: str | Path,
	*,
	inputs: list[str] | None = None,
	engine: Any | None = None,
	network_path: str | Path | None = None,
) -> tuple[DerivedProvenance, pd.DataFrame]:
	"""Sweep the configured parameter and write the section's frame.

	``engine`` is a seam: a test hands one over a fixture network, and the stage
	builds one from the newest solve. It is the same seam `WhatIfEngine` exposes
	for its solver, one level up -- without it a test of this function would have
	to place a solved network on disk, which tests the directory walk instead of
	the frame.

	``network_path`` is the second half of that seam. The stage resolves the
	network itself (a rule cannot name "the newest solve in this directory") and
	passes the resolved path down, so the file the provenance records and the file
	that was solved are the same one by construction rather than by two walks that
	agree today.
	"""
	from alea.whatif.service import WhatIfEngine
	from alea.whatif.sweep import sweep_parameter

	cfg = config.whatif
	parameter = cfg.parameter
	destination = Path(out)

	# Bound to a local so the engine is non-optional for the provenance read
	# below. A caller passing `engine=None` and a caller passing one are the
	# same shape from here on; the only difference is which network was solved.
	solver: Any = engine
	if solver is None:
		base = Path(network_path) if network_path else _newest_network(resolve(NETWORK_DIR))
		solver = WhatIfEngine(base, cache_root=cfg.cache_root or None)

	outcomes = sweep_parameter(
		solver,
		parameter,
		list(cfg.sweep_values),
		workers=cfg.workers,
	)
	frame = frontier_rows(outcomes, parameter)

	parameters: dict[str, Any] = {
		"parameter": parameter,
		"sweep_values": list(cfg.sweep_values),
		"points": int(len(frame)),
		"workers": cfg.workers,
		"network_checksum": solver.network_checksum,
		"code_version": solver.code_version,
	}
	# The base network is this artefact's input whether or not a caller declared
	# it, and `DerivedProvenance` refuses an empty input list for exactly that
	# reason: a derived artefact whose sidecar names nothing cannot be traced to
	# what produced it. The engine's checksum is the network file's own hash, so
	# this is the same value a rule's `--input` would carry, derived rather than
	# declared.
	declared = list(inputs) if inputs is not None else []
	if solver.network_checksum not in declared:
		declared.insert(0, solver.network_checksum)
	provenance = DerivedProvenance(
		source_id="scenario_update",
		inputs=declared,
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters=parameters,
		basis=Basis.MODELLED,
		notes=(
			f"A {len(frame)}-point sweep of {parameter} over the base network "
			f"{solver.network_checksum[:12]}. Each row is one solved scenario: its "
			f"system capacity and its total cost. The values are a range across "
			f"the scenario set and are not a forecast of any single future -- the "
			f"parameter is the only thing that moved between rows, and every other "
			f"parameter is the engine's default for this run."
		),
	)
	write_stage(destination, frame, provenance, format="parquet")
	logger.info(
		"whatif.stage.scenario_update",
		parameter=parameter,
		points=int(len(frame)),
		network=solver.network_checksum[:12],
		out=str(destination),
	)
	return read_provenance(destination), frame


@stage("scenario_update")
def build_scenario_update(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: the quarterly scenario range, from a parameter sweep.

	Reads the newest solved network rather than taking one from the context, so
	two callers cannot sweep different base networks under one provenance.

	A missing network raises. A frontier over no base network is not a scenario
	set, and an empty frame would render as a section that legitimately found no
	scenarios -- which is a claim about the model rather than about the
	directory.
	"""
	directory = resolve(str(context.parameters.get("network_dir") or NETWORK_DIR))
	path = _newest_network(directory)

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="scenario_update", logger=context.logger)
	if existing is not None:
		return existing

	_, frame = scenario_update_to_artefact(config, out, inputs=inputs, network_path=path)
	logger.info(
		"whatif.stage.scenario_update",
		rows=int(len(frame)),
		parameter=config.whatif.parameter,
		out=str(out),
	)
	return read_provenance(out)


__all__ = [
	"NETWORK_DIR",
	"build_scenario_update",
	"frontier_rows",
	"scenario_update_to_artefact",
]
