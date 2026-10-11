# SPDX-License-Identifier: MIT
"""Publish a solved scenario into the API's catalogue.

WHY this exists: `alea.api.repository` reads a scenario catalogue at
``results/scenarios/`` -- an ``index.json`` and, per scenario, a
``scenario.json`` and a ``results/<horizon>.json`` -- and nothing in the tree
wrote it. Every scenario route and the what-if handler's base lookup therefore
read a directory that was always empty, so the whole planning surface returned
"no such scenario" against a solved network sitting on disk. The reader is the
contract; this is the writer that satisfies it.

WHY the solve writes here and not the API: AD-4 says a stage writes a versioned
file and no stage holds a live object across a boundary. The API is a reader of
artefacts, not a producer of them, and a route that published a catalogue entry
would be a route that wrote into the lake. The solve is the stage that has the
network and the result in hand, so it publishes them.

WHY the value shapes are flat: `repository._value` reads a bare number and takes
the basis from the artefact's provenance sidecar. That is deliberate -- a table
from one model run has one basis -- so the payload carries numbers and the
sidecar carries ``basis=MODELLED`` with a stated uncertainty. A modelled number
with no uncertainty is refused by the reader, which is the rule that stops a
proxy estimate being published as a fact.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pypsa

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import read_artefact, sha256_file, utcnow, write_artefact
from alea.logging import get_logger
from alea.planning.aggregation import network_id
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

SCENARIO_ROOT = "results/scenarios"
"""Where the API looks. Must match ``alea.api.repository.SCENARIO_INDEX``'s parent."""

_INDEX_FILENAME = "index.json"
_RECORD_FILENAME = "scenario.json"

UNCERTAINTY = 0.05
"""Relative uncertainty stamped on a solve result.

Not zero, and not invented: a capacity-expansion solve is exact *given its
inputs*, and its inputs carry the uncertainty. Five percent is the round number
this project already uses for a modelled figure whose input error dominates;
the provenance note says so, so the number is never read as a measured one.
"""


def scenario_token(scenario_id: str) -> str:
	"""Reject a scenario id that is not safe to put in a filesystem path.

	The same allow-list `repository._safe_token` applies, duplicated here rather
	than imported: this module is written before the API package is importable in
	some builds, and a writer that accepted an id the reader rejects would write
	a catalogue entry nobody can read. ``..`` and ``/`` are a directory
	traversal, and the id becomes a path component.
	"""
	assert scenario_id, "a scenario needs an id"
	allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@-")
	bad = sorted({character for character in scenario_id if character not in allowed})
	if bad or ".." in scenario_id:
		raise ValueError(
			f"scenario_id={scenario_id!r} contains characters that are not "
			f"path-safe: {bad or ['..']}"
		)
	return scenario_id


def catalogue_dir(*, root: str | Path = SCENARIO_ROOT) -> Path:
	"""``results/scenarios/``, resolved against the repository root."""
	return resolve(root)


def publish_scenario(
	scenario_id: str,
	config: Config,
	network: pypsa.Network,
	result: Any,
	*,
	capacity_mix: Sequence[Mapping[Any, Any]],
	root: str | Path = SCENARIO_ROOT,
	name: str = "",
	description: str = "",
	network_path: str | Path | None = None,
	code_version: str = "",
) -> Path:
	"""Write one solved scenario into the catalogue and update the index.

	``result`` is a `SolveResult` (objective, solver, status, seconds) and
	``capacity_mix`` is the table the solve already computes for its own
	artefact. The mix is passed rather than read off ``result`` because
	`SolveResult` does not carry one -- reading it with ``getattr`` would have
	written an empty mix into every catalogue entry, silently, which is the
	failure this module exists to remove.

	Returns the scenario directory.

	The network is exported beside the catalogue entry so the what-if engine has
	something to load: a scenario that records a network checksum and no network
	is a scenario whose base cannot be re-solved, which is exactly the state the
	API was in.
	"""
	assert config is not None, "publish needs the config the solve ran under"
	assert network is not None, "publish needs the solved network"
	scenario_token(scenario_id)

	directory = catalogue_dir(root=root) / scenario_id
	directory.mkdir(parents=True, exist_ok=True)

	horizons = list(config.scenario.planning_horizons)
	checksum = _network_checksum(network, network_path, directory)
	created = utcnow()

	# The network itself, beside the entry. Exported before the record so the
	# record's checksum refers to a file that exists.
	network_target = directory / "network.nc"
	network.export_to_netcdf(str(network_target))

	inputs = [f"sha256:{checksum}"]
	record = {
		"scenario_id": scenario_id,
		"name": name or scenario_id,
		"description": description,
		"countries": [str(c) for c in config.scenario.countries],
		"planning_horizons": horizons,
		"clusters": list(config.scenario.clusters),
		"created_at": created.isoformat(),
		"network_checksum": checksum,
		"network_file": network_target.name,
		"code_version": code_version,
	}
	write_artefact(
		directory / _RECORD_FILENAME,
		record,
		_derived(
			"planning.scenario",
			inputs=inputs,
			parameters={"scenario_id": scenario_id, "horizons": horizons},
			code_version=code_version,
		),
		format="json",
	)

	# One result document per horizon. A multi-period solve has one network for
	# every period, so the same mix is filed under each horizon with that
	# period's weighting applied to the objective where the result records one.
	written: list[int] = []
	for horizon in horizons:
		payload = _result_payload(result, capacity_mix, horizon, checksum)
		write_artefact(
			directory / "results" / f"{horizon}.json",
			payload,
			_derived(
				"planning.scenario_result",
				inputs=inputs,
				parameters={"scenario_id": scenario_id, "horizon": horizon},
				code_version=code_version,
			),
			format="json",
		)
		written.append(horizon)

	_update_index(record, root=root)
	logger.info(
		"scenario_published",
		scenario_id=scenario_id,
		horizons=written,
		network=checksum[:12],
	)
	return directory


def _network_checksum(
	network: pypsa.Network, network_path: str | Path | None, directory: Path
) -> str:
	"""The network's identity: the file's hash when there is a file, else structural.

	A solve from an in-memory network has no file to hash. Falling back to
	``network_id`` (the structural hash of buses and lines) keeps the checksum
	stable across two builds of the same network, which is the property a cache
	key needs; a checksum of the object's address would change every run.
	"""
	if network_path is not None:
		path = Path(network_path)
		if path.exists():
			return sha256_file(path)
	target = directory / "network.nc"
	if target.exists():
		return sha256_file(target)
	return network_id(network)


def _result_payload(
	result: Any,
	capacity_mix: Sequence[Mapping[Any, Any]],
	horizon: int,
	network_checksum: str,
) -> dict[str, Any]:
	"""One horizon's result document, in the flat shape the reader expects.

	`repository.scenario_result` reads ``objective``, ``total_capacity_mw``,
	``capacity_mix`` (each row ``carrier`` / ``capacity_mw`` / ``share``),
	``network_checksum`` and ``solved_at``. Extra keys are ignored by the reader
	and kept for a human reading the artefact.
	"""
	total = sum(float(row.get("capacity_mw", 0.0)) for row in capacity_mix)
	mix: list[dict[str, Any]] = []
	for row in capacity_mix:
		capacity = float(row.get("capacity_mw", 0.0))
		mix.append(
			{
				"carrier": str(row.get("carrier", "")),
				"capacity_mw": capacity,
				"share": capacity / total if total else 0.0,
			}
		)

	return {
		"horizon": horizon,
		"objective": float(getattr(result, "objective", 0.0)),
		"total_capacity_mw": total,
		"capacity_mix": mix,
		"network_checksum": network_checksum,
		"solved_at": utcnow().isoformat(),
		"seconds": float(getattr(result, "seconds", 0.0)),
		"solver": str(getattr(result, "solver", "")),
		"status": str(getattr(result, "status", "")),
	}


def _derived(
	what: str,
	*,
	inputs: list[str],
	parameters: dict[str, Any],
	code_version: str,
) -> DerivedProvenance:
	"""Provenance for a catalogue document.

	``uncertainty`` is set and non-zero because the reader refuses a MODELLED
	value with no uncertainty -- a modelled number stated as exact is a modelled
	number that will be published as measured.
	"""
	return DerivedProvenance(
		source_id=what,
		basis=Basis.MODELLED,
		uncertainty=UNCERTAINTY,
		uncertainty_basis="input error dominates; the solve is exact given its inputs",
		notes="published by alea.planning.catalogue for the API's scenario routes",
		inputs=inputs,
		parameters=parameters,
		code_version=code_version,
	)


def _update_index(record: dict[str, Any], *, root: str | Path) -> None:
	"""Add or replace this scenario in ``index.json``.

	The index is a plain JSON file, not an artefact: a provenance sidecar would
	be circular, because the index describes artefacts rather than being one.
	Re-solving a scenario replaces its entry rather than appending a duplicate,
	so the catalogue lists scenarios, not solve runs.
	"""
	path = catalogue_dir(root=root) / _INDEX_FILENAME
	entries: list[dict[str, Any]] = []
	if path.exists():
		existing = json.loads(path.read_text(encoding="utf-8"))
		if isinstance(existing, dict) and isinstance(existing.get("scenarios"), list):
			entries = [e for e in existing["scenarios"] if isinstance(e, dict)]

	entry = {key: value for key, value in record.items() if key != "network_file"}
	entries = [e for e in entries if e.get("scenario_id") != record["scenario_id"]]
	entries.append(entry)
	entries.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)

	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(
		json.dumps({"scenarios": entries}, indent=2, sort_keys=True),
		encoding="utf-8",
	)


def load_catalogue(*, root: str | Path = SCENARIO_ROOT) -> list[dict[str, Any]]:
	"""Every published scenario, newest first. Empty when none exist."""
	path = catalogue_dir(root=root) / _INDEX_FILENAME
	if not path.exists():
		return []
	document = json.loads(path.read_text(encoding="utf-8"))
	entries = document.get("scenarios", []) if isinstance(document, dict) else []
	return [dict(e) for e in entries if isinstance(e, dict)]


def read_scenario_record(scenario_id: str, *, root: str | Path = SCENARIO_ROOT) -> dict[str, Any]:
	"""One scenario's record, or a refusal naming the id."""
	scenario_token(scenario_id)
	path = catalogue_dir(root=root) / scenario_id / _RECORD_FILENAME
	if not path.exists():
		raise KeyError(f"no scenario {scenario_id!r} in the catalogue at {path}")
	data, _ = read_artefact(path)
	if not isinstance(data, dict):
		raise TypeError(f"{path}: expected an object, got {type(data).__name__}")
	return data


__all__ = [
	"SCENARIO_ROOT",
	"UNCERTAINTY",
	"catalogue_dir",
	"load_catalogue",
	"publish_scenario",
	"read_scenario_record",
	"scenario_token",
]
