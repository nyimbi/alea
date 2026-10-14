# SPDX-License-Identifier: MIT
"""Layer 4b orchestration — loss decomposition, TLENS, mitigation.

Each stage reads versioned files and writes one artefact with provenance that
records the network, the snapshot count, and the solver parameters the result
depends on. A TLENS ranking without the snapshot set it was computed over is
not reproducible: the ranking is a function of the dispatch, and a dispatch
from a different year gives a different critical-line list.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from alea.config.models import Config
from alea.io.artefacts import sha256_file
from alea.io.pipeline import BuildContext, stage, write_stage
from alea.logging import get_logger, new_run_id
from alea.losses.contingency import summary, tlens, tlens_payload
from alea.losses.decompose import losses_by_component
from alea.losses.flow import Network, loading_series, solve_series
from alea.losses.mitigation import rank_options, rank_payload
from alea.losses.switching import optimal_switching
from alea.losses.views import LossComponents, LossConfig, MitigationOption
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)


def _code_version() -> str:
	from alea import __version__

	return __version__


def _provenance(
	inputs: Sequence[str],
	parameters: dict[str, Any],
	*,
	source_id: str,
	notes: str,
	basis: Basis = Basis.MODELLED,
) -> DerivedProvenance:
	return DerivedProvenance(
		source_id=source_id,
		inputs=list(inputs) or ["<none-recorded>"],
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters=parameters,
		basis=basis,
		notes=notes,
	)


def _network_parameters(network: Network, config: LossConfig) -> dict[str, Any]:
	return {
		"n_buses": network.n_buses,
		"n_branches": network.n_branches,
		"slack_bus": config.slack_bus,
		"price_usd_per_mwh": config.price_usd_per_mwh,
		"snapshot_hours": config.snapshot_hours,
	}


def decomposition_to_artefact(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
	reference_dispatch_mw: NDArray[np.float64] | None = None,
	reference_network: Network | None = None,
	topology_network: Network | None = None,
) -> tuple[str, dict[str, float]]:
	"""Decompose losses and write the components.

	The components sum to the total by construction; a result that did not
	would fail :class:`LossComponents`'s validator rather than reaching the
	artefact.

	``reference_network`` defaults to the loss-optimal topology
	:func:`alea.losses.switching.optimal_switching` finds, which is what makes
	the topology-driven component a measurement. Under the old default -- the
	actual network, and a ``topology_network`` equal to it -- ``T - R`` was zero
	for every network, so the payload read ``load driven == total`` and the
	section built from it rendered a constant. A caller who wants that
	degenerate case back sets ``config.switching_max_openings = 0``, which
	returns the actual network and records the choice.
	"""
	cfg = config or LossConfig()
	switching = None
	if reference_network is None:
		reference_network, switching = optimal_switching(network, dispatch_mw, cfg)
	payload = losses_by_component(
		network,
		dispatch_mw,
		cfg,
		reference_dispatch_mw=reference_dispatch_mw,
		reference_network=reference_network,
		topology_network=topology_network,
	)
	parameters: dict[str, Any] = {
		**_network_parameters(network, cfg),
		"n_snapshots": int(np.asarray(dispatch_mw).shape[0]),
	}
	if switching is not None:
		# The search is a parameter of the result, not an implementation detail:
		# a decomposition whose reference topology came from a truncated search
		# is a different claim from one whose search was exhaustive, and a reader
		# of the artefact has no other way to tell them apart.
		parameters["switching"] = switching.model_dump(mode="json")
	provenance = _provenance(
		inputs if inputs is not None else [],
		parameters,
		source_id="loss_decomposition",
		notes=(
			"components sum to the total by construction (07-layer4 §6.2); the "
			"reference topology is the loss-optimal switching the plan names, and "
			"the search that found it is recorded under `switching`"
		),
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


def decomposition_section_rows(components: LossComponents) -> list[dict[str, Any]]:
	"""A decomposition as the rows the weekly and monthly sections read.

	Both sections are ``["Component", <one numeric column>, "Basis"]`` with unit
	``%``, so both read this one frame: `weekly.py`'s ``loss_decomposition``
	under the header "Share of input" and `monthly.py`'s ``loss_statistics``
	under "Loss share". The values are the shares **times 100**, because the
	sections declare ``%`` and a fraction rendered under a percent header is
	off by two orders of magnitude in a published report.

	**Every component is written, including a zero one.** The register's whole
	complaint about this section was a table reading ``load driven, 100.0`` for
	every network, and the temptation is to drop the components that are zero --
	which would make the defect invisible in exactly the case it was reported in.
	A zero topology-driven share beside two real ones says "the topology is
	already loss-optimal", which is a finding; its absence says nothing.

	**The label map is asserted complete.** ``LossComponents.component_names``
	is the model's list and this is the report's spelling of it; a component
	added to the model and not here would be silently missing from every
	published decomposition, which is the shape of defect that put a hardcoded
	zero in the specification.
	"""
	shares = components.shares
	labels = {
		"load_driven": "Load-driven",
		"generation_driven": "Generation-driven",
		"topology_driven": "Topology-driven",
	}
	missing = sorted(set(components.component_names()) - set(labels))
	if missing:
		raise ValueError(
			f"the decomposition carries {missing} and this producer has no report "
			f"label for them; a component with no row is a driver the report does "
			f"not show"
		)
	rows: list[dict[str, Any]] = []
	for name in components.component_names():
		share = shares[name]
		rows.append(
			{
				"label": labels[name],
				"value": float(share) * 100.0,
				"unit": "%",
				# Carried as its own column so a reader can check the share
				# against the energy it came from without re-deriving either.
				"loss_mwh": float(getattr(components, f"{name}_mwh")),
				"component": name,
			}
		)
	rows.append(
		{
			"label": "Total",
			"value": 100.0 if abs(components.total_mwh) >= 1e-12 else float("nan"),
			"unit": "%",
			"loss_mwh": float(components.total_mwh),
			"component": "total",
		}
	)
	return rows


def losses_components(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	config: LossConfig | None = None,
) -> LossComponents:
	"""The decomposed components, with the loss-optimal reference topology.

	The one place the reference topology is resolved for a caller that wants the
	:class:`LossComponents` rather than a payload, so the section frame and the
	serving row cannot attribute against two different searches.
	"""
	from alea.losses.decompose import decompose, measure
	from alea.losses.switching import optimal_switching

	cfg = config or LossConfig()
	reference, _ = optimal_switching(network, dispatch_mw, cfg)
	return decompose(measure(network, dispatch_mw, cfg, reference_network=reference), cfg)


def tlens_to_artefact(
	network: Network,
	injections_mw: NDArray[np.float64],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
	"""Rank branches by TLENS and write the ranking.

	The ranking is deterministic across runs; ``test_tlens_rank_stable``
	canaries that unseeding it makes the order differ.
	"""
	cfg = config or LossConfig()
	ranking = tlens(network, injections_mw, cfg)
	payload = tlens_payload(ranking)
	provenance = _provenance(
		inputs if inputs is not None else [],
		_network_parameters(network, cfg),
		source_id="tlens",
		notes=(
			"branch contribution to energy not supplied; a branch whose outages "
			"all island the network is ranked by severity, not by a zero ENS"
		),
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


def contingency_to_artefact(
	network: Network,
	injections_mw: NDArray[np.float64],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
	"""Write an N-1 contingency summary."""
	cfg = config or LossConfig()
	record = summary(network, injections_mw, cfg)
	payload = record.model_dump(mode="json")
	provenance = _provenance(
		inputs if inputs is not None else [],
		_network_parameters(network, cfg),
		source_id="contingency",
		notes="N-1 sweep; a diverged contingency is recorded, never propagated",
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


def losses_to_artefact(
	network: Network,
	injections_mw: NDArray[np.float64],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
	"""Write the per-snapshot loss series and its fraction of generation."""
	cfg = config or LossConfig()
	losses, fractions = solve_series(network, injections_mw, cfg)
	payload = {
		"losses_mw": [float(value) for value in losses],
		"loss_fraction": [float(value) if np.isfinite(value) else None for value in fractions],
		"total_losses_mwh": float(np.sum(losses) * cfg.snapshot_hours),
		"mean_loss_fraction": float(np.nanmean(fractions)) if np.any(np.isfinite(fractions)) else None,
		"n_snapshots": int(losses.shape[0]),
		**_network_parameters(network, cfg),
	}
	provenance = _provenance(
		inputs if inputs is not None else [],
		_network_parameters(network, cfg),
		source_id="transmission_losses",
		notes="per-snapshot losses from I^2 R on the DC flows",
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


def critical_lines_to_artefact(
	network: Network,
	injections_mw: NDArray[np.float64],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
	threshold: float = 1.0,
) -> tuple[str, list[dict[str, Any]]]:
	"""Write the branches loaded at or above rating, in the report's shape.

	The frame is what `reporting/weekly.py`'s ``critical_lines`` section reads:
	one row per line with ``value`` (the peak loading), a ``peak_loading``
	column the section's "Peak loading" header binds to, and an ``hours``
	column its "Hours" header binds to. Both extra columns are load-bearing --
	``_rows_for`` refuses to fill a numeric column whose quantity the row does
	not carry, and before that refusal existed the reader printed the loading
	under "Hours" in a published report.

	``hours`` is hours, not a snapshot count: `loading_series` multiplies by
	``LossConfig.snapshot_hours``, so a 15-minute dispatch reports a quarter of
	the count it took. The unit the section declares is ``loading``, which is
	dimensionless -- 1.0 is at rating -- so the frame carries no ``MW``.
	"""
	cfg = config or LossConfig()
	ranking = loading_series(network, injections_mw, cfg, threshold=threshold)
	rows = [
		{
			"label": entry.branch_name,
			"value": entry.peak_loading,
			"unit": "loading",
			"peak_loading": entry.peak_loading,
			"hours": entry.hours_at_or_above,
			"rating_mw": entry.rating_mw,
			"peak_flow_mw": entry.peak_flow_mw,
		}
		for entry in ranking.entries
	]
	import pandas as pd

	frame = pd.DataFrame(
		rows,
		columns=[
			"label",
			"value",
			"unit",
			"peak_loading",
			"hours",
			"rating_mw",
			"peak_flow_mw",
		],
	)
	provenance = _provenance(
		inputs if inputs is not None else [],
		{
			**_network_parameters(network, cfg),
			"n_snapshots": ranking.n_snapshots,
			"threshold": threshold,
			"n_rated": ranking.n_rated,
			"n_above": len(ranking.entries),
		},
		source_id="critical_lines",
		notes=(
			"branch loading |p0| / s_nom per branch per snapshot; the peak is over "
			"the series and `hours` is the snapshot count times the snapshot "
			"length, so a sub-hourly dispatch does not report its count as hours. "
			"Branches with no finite rating are excluded and counted, never "
			"reported as zero loading."
		),
	)
	checksum = write_stage(Path(out), frame, provenance, format="parquet")
	return checksum, rows


def mitigation_to_artefact(
	network: Network,
	injections_mw: NDArray[np.float64],
	options: Sequence[MitigationOption],
	out: str | Path,
	config: LossConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, list[dict[str, object]]]:
	"""Rank mitigation options and write the ranking.

	Savings are summed over the actual hourly series, not extrapolated from one
	snapshot (07-layer4 §7.1).
	"""
	cfg = config or LossConfig()
	results = rank_options(network, injections_mw, options, cfg)
	payload = rank_payload(results)
	provenance = _provenance(
		inputs if inputs is not None else [],
		{**_network_parameters(network, cfg), "options": [option.name for option in options]},
		source_id="loss_mitigation",
		notes=(
			"annual savings summed over the hourly series; unmeasurable paybacks "
			"reported as null, never infinite"
		),
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


# --------------------------------------------------------------------------
# Stage registration
# --------------------------------------------------------------------------


@stage("tlens")
def _stage_tlens(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: TLENS over a network and dispatch artefact.

	Reads the network and dispatch from conventional paths under
	``paths.processed``. A missing input raises rather than producing an empty
	ranking, which would read as "no critical lines".
	"""
	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact

	processed = resolve(config.paths.processed)
	network_path = processed / "network_arrays.json"
	dispatch_path = processed / "dispatch.parquet"

	if not network_path.exists():
		raise ArtefactError(f"no network arrays at {network_path}")
	if not dispatch_path.exists():
		raise ArtefactError(f"no dispatch series at {dispatch_path}")

	network = _network_from_payload(read_artefact(network_path)[0])
	dispatch, _ = read_artefact(dispatch_path)
	import pandas as pd

	matrix = pd.DataFrame(dispatch).select_dtypes("number").to_numpy(dtype=float)
	if matrix.shape[1] != network.n_buses:
		raise ArtefactError(
			f"dispatch has {matrix.shape[1]} columns but the network has "
			f"{network.n_buses} buses"
		)
	# The configured section, with the reference bus taken from the solve options
	# when the loss config does not name one. `slack_bus` is a property of the
	# network the solve used, so the solve's option wins over a loss-section
	# default; everything else -- the price a mitigation payback divides by, the
	# snapshot length that keeps MW from being printed as MWh -- is the operator's
	# and comes from the section.
	losses = config.losses
	if "slack_bus" not in losses.model_fields_set and "slack_bus" in config.solve.solver_options:
		losses = losses.model_copy(update={"slack_bus": config.solve.solver_options["slack_bus"]})
	_, payload = tlens_to_artefact(
		network,
		matrix,
		out,
		losses,
		inputs=context.inputs,
	)
	logger.info("losses.stage.tlens", branches=payload["n_branches"], checksum_prefix="")
	return _provenance(
		context.inputs,
		{"n_branches": payload["n_branches"], "n_snapshots": payload["n_snapshots"]},
		source_id="tlens",
		notes="TLENS ranking written by the registered stage",
	)


@stage("critical_lines")
def _stage_critical_lines(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: branch loading over a network and dispatch artefact.

	The same two inputs as ``tlens`` and the same resolution, because the two
	read one solved network: the arrays number the buses and the dispatch's
	columns are in that order, so a stage that resolved either differently would
	be measuring a different network from its neighbour.

	A missing input raises rather than producing an empty table. An empty
	critical-line table is a *finding* -- nothing is above rating -- and a stage
	that wrote one because its dispatch was absent would publish "no line is
	overloaded" for a network it never looked at.
	"""
	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact

	processed = resolve(config.paths.processed)
	network_path = processed / "network_arrays.json"
	dispatch_path = processed / "dispatch.parquet"

	if not network_path.exists():
		raise ArtefactError(f"no network arrays at {network_path}")
	if not dispatch_path.exists():
		raise ArtefactError(f"no dispatch series at {dispatch_path}")

	network = _network_from_payload(read_artefact(network_path)[0])
	dispatch, _ = read_artefact(dispatch_path)
	import pandas as pd

	matrix = pd.DataFrame(dispatch).select_dtypes("number").to_numpy(dtype=float)
	if matrix.shape[1] != network.n_buses:
		raise ArtefactError(
			f"dispatch has {matrix.shape[1]} columns but the network has "
			f"{network.n_buses} buses"
		)
	# Same precedence as `tlens`: the reference bus is a property of the network
	# the solve used, so the solve's option wins over a loss-section default.
	losses = config.losses
	if "slack_bus" not in losses.model_fields_set and "slack_bus" in config.solve.solver_options:
		losses = losses.model_copy(update={"slack_bus": config.solve.solver_options["slack_bus"]})
	_, rows = critical_lines_to_artefact(
		network,
		matrix,
		out,
		losses,
		inputs=context.inputs,
	)
	logger.info(
		"losses.stage.critical_lines",
		branches=network.n_branches,
		above=len(rows),
		snapshots=int(matrix.shape[0]),
	)
	return _provenance(
		context.inputs,
		{
			"n_branches": network.n_branches,
			"n_snapshots": int(matrix.shape[0]),
			"n_above": len(rows),
			"snapshot_hours": losses.snapshot_hours,
		},
		source_id="critical_lines",
		notes="branch loading written by the registered stage",
	)


@stage("loss_decomposition")
def _stage_loss_decomposition(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: the loss decomposition, as a report frame and a serving row.

	Writes two artefacts from one decomposition, the way ``network_arrays``
	writes its arrays and its dispatch:

	* ``out`` -- the weekly and monthly sections' frame, one row per driver with
	  its share of the total in percent. Both sections read
	  ``["Component", <one numeric column>, "Basis"]`` at unit ``%``, so one
	  frame satisfies both and neither can be produced from a different search.
	* the API's serving table at :data:`alea.publish.views.PUBLISHED_TABLES`,
	  through `project_loss_decomposition`, which checks it against
	  ``LOSSES_DECOMPOSITION`` before writing. That register recorded the path as
	  ``UNWIRED`` with this exact blocker -- "a table written from that asserts
	  '100% of losses are load-driven' for every country" -- so closing the
	  kernel and leaving the table unwired would leave the register overstating a
	  gap that no longer exists.

	**Why this is not a rule over the old defaults.** ``decomposition_to_artefact``
	had no pipeline caller, and the register recorded the missing piece as a
	*rule*. A rule is the smaller half: with ``reference_network`` defaulting to
	the actual network, the artefact it would have written reads
	``load_driven == total`` for every network, and the section built from it
	renders a constant. The reference topology is
	:func:`alea.losses.switching.optimal_switching`, and this stage supplies it.

	A missing input raises rather than producing an empty decomposition. An empty
	one reads as "no losses", which is a claim about the network; the truth is
	that no dispatch was read.
	"""
	import pandas as pd

	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact

	processed = resolve(config.paths.processed)
	network_path = processed / "network_arrays.json"
	dispatch_path = processed / "dispatch.parquet"

	if not network_path.exists():
		raise ArtefactError(f"no network arrays at {network_path}")
	if not dispatch_path.exists():
		raise ArtefactError(f"no dispatch series at {dispatch_path}")

	network = _network_from_payload(read_artefact(network_path)[0])
	dispatch, _ = read_artefact(dispatch_path)
	frame = pd.DataFrame(dispatch)
	matrix = frame.select_dtypes("number").to_numpy(dtype=float)
	if matrix.shape[1] != network.n_buses:
		raise ArtefactError(
			f"dispatch has {matrix.shape[1]} columns but the network has "
			f"{network.n_buses} buses"
		)
	losses = _loss_config(config)
	components = losses_components(network, matrix, losses)
	_write_loss_section(out, components, config, losses, context.inputs)
	serving = _write_loss_serving(components, frame, config, losses, context.inputs)
	logger.info(
		"losses.stage.loss_decomposition",
		total_mwh=components.total_mwh,
		load_share=components.shares["load_driven"],
		topology_share=components.shares["topology_driven"],
		serving=str(serving),
	)
	return _provenance(
		context.inputs,
		{
			"n_branches": network.n_branches,
			"n_snapshots": int(matrix.shape[0]),
			"total_mwh": components.total_mwh,
			"shares": components.shares,
			"snapshot_hours": losses.snapshot_hours,
			"switching_max_openings": losses.switching_max_openings,
			"serving_table": str(serving),
		},
		source_id="loss_decomposition",
		notes=(
			"loss decomposition written by the registered stage: the report frame "
			"at `--out` and the API's serving table beside it, both from one "
			"decomposition against the loss-optimal switching topology"
		),
	)


def _write_loss_section(
	out: Path,
	components: LossComponents,
	config: Config,
	losses: LossConfig,
	inputs: Sequence[str],
) -> None:
	"""Write the report frame the two loss sections read."""
	import pandas as pd

	frame = pd.DataFrame(decomposition_section_rows(components))
	write_stage(
		Path(out),
		frame,
		_provenance(
			inputs,
			{
				**_network_parameters_from(losses),
				"total_mwh": components.total_mwh,
				"shares": components.shares,
			},
			source_id="loss_decomposition",
			notes=(
				"the weekly and monthly loss sections' frame: each driver's share "
				"of the total, in percent, against the loss-optimal switching "
				"topology the plan names (07-layer4 §6.2)"
			),
		),
		format="parquet",
	)


def _write_loss_serving(
	components: LossComponents,
	dispatch: Any,
	config: Config,
	losses: LossConfig,
	inputs: Sequence[str],
) -> Path:
	"""Write the API's loss-decomposition serving table.

	The country comes from the run's own scenario and the period from the
	dispatch series' own index, because a serving row carries both and neither
	is in the decomposition. A dispatch whose index is not a timestamp is
	refused rather than stamped with the run date: the period is what the
	numbers are *about*, and a row claiming a window the dispatch does not cover
	is a wrong period on a right number.
	"""
	import pandas as pd

	from alea.io.artefacts import ArtefactError
	from alea.publish.service import project, project_loss_decomposition, table_path
	from alea.publish.stages import _single_country

	country_iso = _single_country(config)
	if not isinstance(dispatch.index, pd.DatetimeIndex):
		raise ArtefactError(
			f"the dispatch series carries a {type(dispatch.index).__name__} index, "
			f"not a timestamp; the serving row declares the period its losses are "
			f"about and there is nothing to read it from"
		)
	if len(dispatch.index) == 0:
		raise ArtefactError("the dispatch series is empty, so it covers no period")
	# Resolved against *this config's* processed directory, not the repository
	# root: the register declares the path the API reads, and a run configured
	# to write elsewhere must land its table there or the API reads a table
	# this run never wrote.
	target = table_path("losses_decomposition", processed=config.paths.processed)
	frame = project_loss_decomposition(
		components,
		country_iso=country_iso,
		period_start=dispatch.index.min(),
		period_end=dispatch.index.max(),
	)
	target.parent.mkdir(parents=True, exist_ok=True)
	project(
		"losses_decomposition",
		frame,
		target,
		inputs=list(inputs),
		parameters={
			"country_iso": country_iso,
			"total_mwh": components.total_mwh,
			"shares": components.shares,
			"switching_max_openings": losses.switching_max_openings,
		},
		notes=(
			"loss decomposition as one serving row. The components sum to the "
			"total by construction and the reference topology is the loss-optimal "
			"switching the plan names, so `share` is a measurement rather than the "
			"specification's hardcoded zero"
		),
	)
	return target


def _loss_config(config: Config) -> LossConfig:
	"""The configured loss section, with the solve's reference bus where it names none.

	One spelling of a rule three stages apply -- `tlens`, `critical_lines` and
	`loss_decomposition` all read the same solved network, and the slack bus is a
	property of the solve rather than a loss default. A stage that resolved it
	differently from its neighbour would be measuring a different network.
	"""
	losses = config.losses
	if "slack_bus" not in losses.model_fields_set and "slack_bus" in config.solve.solver_options:
		losses = losses.model_copy(update={"slack_bus": config.solve.solver_options["slack_bus"]})
	return losses


def _network_parameters_from(losses: LossConfig) -> dict[str, Any]:
	"""The solver parameters a loss artefact's provenance records."""
	return {
		"slack_bus": losses.slack_bus,
		"price_usd_per_mwh": losses.price_usd_per_mwh,
		"snapshot_hours": losses.snapshot_hours,
		"switching_max_openings": losses.switching_max_openings,
	}


def _network_from_payload(payload: Any) -> Network:
	"""Rebuild a :class:`Network` from a serialised array payload."""
	import numpy as np

	if not isinstance(payload, dict):
		raise ValueError(f"network payload must be a mapping, got {type(payload).__name__}")
	required = (
		"susceptance",
		"branch_from",
		"branch_to",
		"branch_susceptance",
		"resistance_ohm",
		"voltage_kv",
		"ratings_mw",
	)
	missing = [key for key in required if key not in payload]
	if missing:
		raise ValueError(f"network payload lacks {missing}")
	return Network(
		susceptance=np.asarray(payload["susceptance"], dtype=np.float64),
		branch_from=np.asarray(payload["branch_from"], dtype=np.uint32),
		branch_to=np.asarray(payload["branch_to"], dtype=np.uint32),
		branch_susceptance=np.asarray(payload["branch_susceptance"], dtype=np.float64),
		resistance_ohm=np.asarray(payload["resistance_ohm"], dtype=np.float64),
		voltage_kv=np.asarray(payload["voltage_kv"], dtype=np.float64),
		ratings_mw=np.asarray(payload["ratings_mw"], dtype=np.float64),
		branch_names=tuple(payload.get("branch_names", ())),
	)


def network_to_payload(network: Network) -> dict[str, Any]:
	"""A :class:`Network` as a JSON-ready payload."""
	return {
		"susceptance": network.susceptance.tolist(),
		"branch_from": network.branch_from.tolist(),
		"branch_to": network.branch_to.tolist(),
		"branch_susceptance": network.branch_susceptance.tolist(),
		"resistance_ohm": network.resistance_ohm.tolist(),
		"voltage_kv": network.voltage_kv.tolist(),
		"ratings_mw": [
			float(value) if np.isfinite(value) else None for value in network.ratings_mw
		],
		"branch_names": list(network.branch_names),
	}


def file_checksum(path: str | Path) -> str:
	"""Checksum of an input file, for a caller assembling provenance inputs."""
	return sha256_file(Path(path))


__all__ = [
	"contingency_to_artefact",
	"critical_lines_to_artefact",
	"decomposition_to_artefact",
	"file_checksum",
	"losses_to_artefact",
	"mitigation_to_artefact",
	"network_to_payload",
	"tlens_to_artefact",
]
