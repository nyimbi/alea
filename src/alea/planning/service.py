# SPDX-License-Identifier: MIT
"""Layer 1 entry points.

The orchestration the CLI and the Snakemake rules call. Each function is one
unit of work with a name, so a rule reads as a step in a plan rather than as a
sequence of library calls.

``solve_scenario`` is the one the CLI names. It builds a network from the
processed artefacts if it is not handed one, which is the path that must work
without PyPSA-Earth present (AD-1, exit criterion 10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pypsa

from alea.config.models import Config
from alea.io.artefacts import artefact_exists, read_artefact, write_artefact
from alea.logging import get_logger
from alea.planning.aggregation import (
	AggregationValidation,
	network_id,
	require_aggregation_validation,
)
from alea.planning.demand import attach_loads, demand_provenance
from alea.planning.dispatch import DispatchResult, dispatch_provenance, solve_dispatch
from alea.planning.expansion import (
	ExpansionError,
	SolveResult,
	capacity_mix_table,
	loss_share,
	solve_expansion,
	solve_result_provenance,
)
from alea.planning.fleet import attach_generators, fleet_provenance
from alea.planning.renewables import attach_renewables, renewable_provenance
from alea.planning.topology import build_topology
from alea.provenance.models import DerivedProvenance

_log = get_logger(__name__)


class PlanningError(RuntimeError):
	"""A Layer 1 entry point cannot complete."""


@dataclass
class BuildReport:
	"""What a network build did, stage by stage."""

	topology: dict[str, Any]
	fleet: dict[str, Any]
	demand: dict[str, Any] | None = None
	renewables: dict[str, Any] | None = None
	notes: list[str] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		return {
			"topology": self.topology,
			"fleet": self.fleet,
			"demand": self.demand,
			"renewables": self.renewables,
			"notes": list(self.notes),
		}


def build_network(
	config: Config,
	*,
	root: str | Path = "data/processed",
	demand_profiles: pd.DataFrame | None = None,
	renewable_profiles: dict[str, pd.DataFrame] | None = None,
	capital_costs: dict[str, float] | None = None,
	logger_: Any = None,
) -> tuple[pypsa.Network, BuildReport, list[DerivedProvenance]]:
	"""Build a Layer 1 network from processed artefacts.

	Every input is optional and its absence is recorded. A network built from
	topology alone is a legitimate intermediate state -- it is what the
	connectivity gate runs against -- and a build that refused to proceed
	without demand would make that gate unrunnable.
	"""
	assert config is not None, "config must not be None"
	log = logger_ or _log
	base = Path(root)
	provenances: list[DerivedProvenance] = []
	notes: list[str] = []

	topology_frame = _read_frame(base / "topology.parquet")
	network, topology_prov, topology_report = build_topology(
		topology_frame,
		voltage_kv_min=float(config.solve.solver_options.get("voltage_kv_min", 66.0)),
		snap_tolerance_m=float(config.solve.solver_options.get("snap_tolerance_m", 500.0)),
	)
	provenances.append(topology_prov)

	fleet_frame = _read_frame(base / "fleet.parquet")
	fleet_report = attach_generators(network, fleet_frame)
	provenances.append(fleet_provenance(fleet_report))

	demand_report: dict[str, Any] | None = None
	if demand_profiles is not None:
		attach_loads(network, demand_profiles)
		demand_report = {"buses": int(demand_profiles.shape[1]), "hours": int(demand_profiles.shape[0])}
		provenances.append(demand_provenance(None))
	else:
		notes.append(
			"no demand profiles attached; the network has generation and topology "
			"but no load, so it can be checked for connectivity and not solved"
		)

	renewable_report: dict[str, Any] | None = None
	if renewable_profiles:
		stats = attach_renewables(
			network,
			renewable_profiles,
			capital_cost_usd_per_mw=capital_costs,
			extendable=capital_costs is not None,
		)
		renewable_report = {carrier: s.as_dict() for carrier, s in stats.items()}
		provenances.append(renewable_provenance(stats))
	else:
		notes.append("no renewable profiles attached")

	report = BuildReport(
		topology=topology_report.as_dict(),
		fleet=fleet_report.as_dict(),
		demand=demand_report,
		renewables=renewable_report,
		notes=notes,
	)
	log.info(
		"network_built",
		buses=topology_report.n_buses,
		lines=topology_report.n_lines,
		generators=int(len(network.generators)),
		notes=len(notes),
	)
	return network, report, provenances


def solve_scenario(
	config: Config,
	*,
	network: str | Path | pypsa.Network | None = None,
	out: str | Path = "results/networks",
	horizon: int | None = None,
	scenario_id: str | None = None,
	publish: bool = True,
	logger_: Any = None,
) -> SolveResult:
	"""Solve a capacity-expansion problem.

	``network`` may be a path to a saved NetCDF, an in-memory network, or None,
	in which case one is built from the processed artefacts. The aggregation gate
	runs before the solve, not after: a config that selects a fast path nobody
	has measured is refused here, where nothing has been spent yet.

	``publish`` writes the solved scenario into the API's catalogue
	(``alea.planning.catalogue``). It is on by default because a solved scenario
	that is not in the catalogue is invisible to every scenario route and cannot
	be used as a what-if base -- which is how the API shipped reading an empty
	directory. Set it off for a throwaway solve. ``scenario_id`` names the entry;
	it defaults to the network's own id, which is stable across rebuilds.
	"""
	assert config is not None, "config must not be None"
	log = logger_ or _log
	out_path = Path(out)
	out_path.mkdir(parents=True, exist_ok=True)

	network_source: Path | None = None
	if isinstance(network, pypsa.Network):
		built = network
		inputs = ["sha256:network:in-memory"]
	elif network is not None:
		path = Path(network)
		if not path.exists():
			raise PlanningError(f"network {path} does not exist")
		built = pypsa.Network(str(path))
		network_source = path
		from alea.io.artefacts import sha256_file

		inputs = [f"sha256:{sha256_file(path)}"]
	else:
		built, report, provenances = build_network(config, logger_=log)
		inputs = [p.inputs[0] for p in provenances if p.inputs]

	if config.solve.time_aggregation > 1:
		require_aggregation_validation(built, config.solve.time_aggregation)
		log.info("aggregation_gate_passed", network=network_id(built), periods=config.solve.time_aggregation)

	horizons = [horizon] if horizon is not None else None
	result = solve_expansion(built, config, horizons=horizons, logger_=log)

	target = out_path / f"{network_id(built)}-{horizon or 'all'}.nc"
	result.network.export_to_netcdf(str(target))
	mix = capacity_mix_table(result.network).to_dict(orient="records")
	provenance = solve_result_provenance(result, config, inputs=inputs)
	write_artefact(
		out_path / f"{network_id(built)}-{horizon or 'all'}.json",
		{**result.as_dict(), "capacity_mix": mix},
		provenance,
		format="json",
	)
	log.info("scenario_solved", path=str(target), objective=result.objective)

	if publish:
		# The catalogue entry is what makes the solve visible to the API. Its
		# failure must not discard a solve that took forty minutes, so it is
		# logged and not raised: the artefacts above are already on disk and the
		# operator can publish separately.
		from alea.planning.catalogue import publish_scenario

		try:
			publish_scenario(
				scenario_id or network_id(built),
				config,
				result.network,
				result,
				capacity_mix=mix,
				network_path=network_source or target,
				code_version=config.api.version,
			)
		except (ValueError, KeyError) as exc:
			log.warning("scenario_publish_failed", error=str(exc))
	return result


def dispatch_scenario(
	config: Config,
	*,
	network: str | Path | pypsa.Network,
	out: str | Path = "results/dispatch",
	logger_: Any = None,
) -> DispatchResult:
	"""Solve hourly dispatch on a network with fixed capacity."""
	assert config is not None, "config must not be None"
	log = logger_ or _log
	out_path = Path(out)
	out_path.mkdir(parents=True, exist_ok=True)

	built = network if isinstance(network, pypsa.Network) else _load_network(network)
	result = solve_dispatch(built, config)
	write_artefact(
		out_path / f"{network_id(built)}-dispatch.json",
		result.as_dict(),
		dispatch_provenance(result, config),
		format="json",
	)
	log.info("dispatch_done", objective=result.objective, curtailment=result.curtailment_share)
	return result


def network_summary(network: pypsa.Network) -> dict[str, Any]:
	"""The facts about a network a report or an API response needs.

	One function, so a bus count quoted in a report and a bus count quoted by
	the API are the same count.
	"""
	from alea.planning.topology import connectivity_report, orphan_buses

	assert network is not None, "network must not be None"
	summary: dict[str, Any] = {
		"network_id": network_id(network),
		"n_buses": int(len(network.buses)),
		"n_lines": int(len(network.lines)),
		"n_generators": int(len(network.generators)),
		"n_loads": int(len(network.loads)),
		"n_snapshots": int(len(network.snapshots)),
		"connectivity": connectivity_report(network),
		"orphan_buses": len(orphan_buses(network)),
		"capacity_mix": capacity_mix_table(network).to_dict(orient="records"),
	}
	# Bound to a local so the None check narrows the type; `getattr` in the
	# condition alone does not narrow the attribute access below it.
	objective = getattr(network, "objective", None)
	if objective is not None:
		try:
			summary["objective"] = float(objective)
			summary["loss_share"] = loss_share(network)
		except ExpansionError:
			pass
	return summary


def load_validation_artefact(
	network_id_value: str,
	*,
	root: str | Path = "results/aggregation",
) -> AggregationValidation | None:
	"""Read a network's aggregation validation, if one exists."""
	from alea.planning.aggregation import load_validation

	return load_validation(network_id_value, root=root)


def _read_frame(path: Path) -> pd.DataFrame:
	"""Read a processed table, with a message that names the file."""
	assert path is not None, "path must not be None"
	if not artefact_exists(path):
		raise PlanningError(
			f"{path} does not exist; build it first (see docs/plans/02-data-pipeline.md)"
		)
	payload, _ = read_artefact(path, verify=False)
	if isinstance(payload, pd.DataFrame):
		return payload
	return pd.DataFrame(payload)


def _load_network(network: str | Path) -> pypsa.Network:
	path = Path(network)
	if not path.exists():
		raise PlanningError(f"network {path} does not exist")
	return pypsa.Network(str(path))


__all__ = [
	"BuildReport",
	"PlanningError",
	"build_network",
	"dispatch_scenario",
	"load_validation_artefact",
	"network_summary",
	"solve_scenario",
]
