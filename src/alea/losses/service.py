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
from alea.losses.flow import Network, solve_series
from alea.losses.mitigation import rank_options, rank_payload
from alea.losses.views import LossConfig, MitigationOption
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
	"""
	cfg = config or LossConfig()
	payload = losses_by_component(
		network,
		dispatch_mw,
		cfg,
		reference_dispatch_mw=reference_dispatch_mw,
		reference_network=reference_network,
		topology_network=topology_network,
	)
	provenance = _provenance(
		inputs if inputs is not None else [],
		{**_network_parameters(network, cfg), "n_snapshots": int(np.asarray(dispatch_mw).shape[0])},
		source_id="loss_decomposition",
		notes="components sum to the total by construction (07-layer4 §6.2)",
	)
	checksum = write_stage(Path(out), payload, provenance, format="json")
	return checksum, payload


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
		"total_losses_mwh": float(np.sum(losses)),
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
	_, payload = tlens_to_artefact(
		network,
		matrix,
		out,
		LossConfig(slack_bus=config.solve.solver_options.get("slack_bus", 0)),
		inputs=context.inputs,
	)
	logger.info("losses.stage.tlens", branches=payload["n_branches"], checksum_prefix="")
	return _provenance(
		context.inputs,
		{"n_branches": payload["n_branches"], "n_snapshots": payload["n_snapshots"]},
		source_id="tlens",
		notes="TLENS ranking written by the registered stage",
	)


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
	"decomposition_to_artefact",
	"file_checksum",
	"losses_to_artefact",
	"mitigation_to_artefact",
	"network_to_payload",
	"tlens_to_artefact",
]
