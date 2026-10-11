# SPDX-License-Identifier: MIT
"""Scenario persistence.

WHY a scenario records its network checksum and code version and not just its
parameters: a scenario without its network is not reproducible. The
specification's engine holds a base network path in the constructor and never
records it, so two engines built on different networks write incomparable
results under the same scenario name and nothing in the artefact says so. The
network checksum is the field that makes a stored scenario answerable.

WHY the version is the solve's cache key: saving the same scenario twice is
then idempotent by construction. Changing any parameter, the network, or the
code produces a different key and therefore a new version, so history is kept
without a version counter anyone has to remember to increment.
"""

from __future__ import annotations

import json
from pathlib import Path

from alea.io.artefacts import read_provenance, utcnow
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance, Licence
from alea.whatif.cache import cache_key
from alea.whatif.params import ScenarioParameters
from alea.whatif.views import ScenarioRecord, ScenarioResult

logger = get_logger(__name__)

SCENARIO_ROOT = "results/scenarios"
_RECORD_FILENAME = "scenario.json"


class ScenarioStoreError(Exception):
	"""A scenario could not be saved or read."""


def scenario_dir(name: str, version: str, *, root: str | Path = SCENARIO_ROOT) -> Path:
	"""``results/scenarios/<name>/<version>/``."""
	if not name or "/" in name or name.startswith("."):
		raise ScenarioStoreError(f"scenario name {name!r} is not a plain directory name")
	assert version, "a scenario version is its content address and cannot be empty"
	return Path(root) / name / version


def save_scenario(
	name: str,
	params: ScenarioParameters,
	result: ScenarioResult,
	network_checksum: str,
	code_version: str,
	*,
	root: str | Path = SCENARIO_ROOT,
	tags: list[str] | None = None,
	notes: str = "",
) -> Path:
	"""Persist a scenario with everything needed to reproduce it.

	The version is derived from the parameters, the network, and the code — the
	same three things the cache key covers — so a saved scenario and its cache
	entry can never disagree about which scenario they describe.
	"""
	assert isinstance(params, ScenarioParameters)
	assert network_checksum, "a scenario without its network checksum is not reproducible"
	assert code_version, "a scenario without its code version is not reproducible"

	version = cache_key(params, network_checksum, code_version)
	record = ScenarioRecord(
		name=name,
		version=version,
		params=params,
		network_checksum=network_checksum,
		code_version=code_version,
		result=result,
		created_at=utcnow().isoformat(),
		tags=list(tags or []),
		notes=notes,
	)

	directory = scenario_dir(name, version, root=root)
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / _RECORD_FILENAME

	existing = _read_record(path) if path.exists() else None
	if existing is not None and existing.result == record.result:
		# Idempotent: the same scenario saved twice is the same scenario. Only
		# `created_at` differs, and rewriting it would make the artefact's bytes
		# depend on when someone re-ran the save.
		logger.info("whatif.scenario.exists", name=name, version=version[:12])
		return path

	path.write_text(
		json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
		encoding="utf-8",
	)
	_write_provenance(path, record)
	logger.info("whatif.scenario.saved", name=name, version=version[:12], cost=result.total_cost_usd)
	return path


def load_scenario(
	name: str,
	version: str,
	*,
	root: str | Path = SCENARIO_ROOT,
) -> ScenarioRecord:
	"""Read a stored scenario, verifying its recorded checksum."""
	path = scenario_dir(name, version, root=root) / _RECORD_FILENAME
	if not path.exists():
		raise ScenarioStoreError(f"no scenario {name!r} at version {version!r} ({path})")
	record = _read_record(path)
	_verify_provenance(path, record)
	return record


def list_scenarios(*, root: str | Path = SCENARIO_ROOT) -> list[ScenarioRecord]:
	"""Every stored scenario, newest name first, versions sorted.

	Sorted explicitly: a listing that follows directory enumeration order is not
	reproducible (AD-8), and a "latest scenario" chosen that way changes between
	machines.
	"""
	base = Path(root)
	if not base.is_dir():
		return []

	records: list[ScenarioRecord] = []
	for name_dir in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name):
		for version_dir in sorted(
			(p for p in name_dir.iterdir() if p.is_dir()), key=lambda p: p.name
		):
			path = version_dir / _RECORD_FILENAME
			if path.exists():
				records.append(_read_record(path))
	return records


def latest_version(name: str, *, root: str | Path = SCENARIO_ROOT) -> str | None:
	"""The most recent version of a scenario, by creation time.

	Creation time, not directory order: a version is a content address and
	carries no ordering, so "latest" has to come from the record.
	"""
	versions = [record for record in list_scenarios(root=root) if record.name == name]
	if not versions:
		return None
	return max(versions, key=lambda record: record.created_at).version


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------


def _read_record(path: Path) -> ScenarioRecord:
	return ScenarioRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _write_provenance(path: Path, record: ScenarioRecord) -> None:
	"""Write a provenance sidecar alongside the scenario.

	A stored scenario is a derived artefact, so it carries the same sidecar
	shape every other artefact does. ``inputs`` holds the network checksum,
	which is the thing the scenario was computed *against*; without it the
	record could not be traced to a network.
	"""
	provenance = DerivedProvenance(
		source_id=f"scenario:{record.name}",
		licence=Licence.UNKNOWN,
		basis=Basis.MODELLED,
		uncertainty=record.result.uncertainty,
		uncertainty_basis=(
			"max relative uncertainty of the scenario's inputs"
			if record.result.uncertainty > 0
			else ""
		),
		notes=record.notes,
		inputs=[record.network_checksum],
		code_version=record.code_version,
		parameters=record.params.canonical(),
	)
	sidecar = path.with_suffix(path.suffix + ".provenance.json")
	sidecar.write_text(
		json.dumps(
			{**provenance.model_dump(mode="json"), "checksum": record.version},
			indent=2,
			sort_keys=True,
			default=str,
		),
		encoding="utf-8",
	)


def _verify_provenance(path: Path, record: ScenarioRecord) -> None:
	"""Refuse a scenario whose sidecar names a different scenario.

	The sidecar records the network checksum as its single input. A sidecar
	naming a different network than the record does is a scenario whose two
	halves disagree about what it was computed against, which is the one thing
	a stored scenario exists to make unambiguous.
	"""
	provenance = read_provenance(path)
	if provenance.inputs and provenance.inputs != [record.network_checksum]:
		raise ScenarioStoreError(
			f"{path}: sidecar names network {provenance.inputs[0][:12]} but the "
			f"record names {record.network_checksum[:12]}"
		)


__all__ = [
	"SCENARIO_ROOT",
	"ScenarioStoreError",
	"latest_version",
	"list_scenarios",
	"load_scenario",
	"save_scenario",
	"scenario_dir",
]
