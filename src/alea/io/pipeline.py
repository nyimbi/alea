# SPDX-License-Identifier: MIT
"""Stage execution.

Two halves. ``fetch_source`` puts bytes in the immutable raw layer.
``build_stage`` turns raw (and other processed) artefacts into a processed
artefact with provenance.

Every stage is idempotent: it checks whether its output already records exactly
these inputs and exits without writing when it does. ``--force`` overrides.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alea.config.models import Config
from alea.io.artefacts import (
	ArtefactError,
	artefact_exists,
	stage_is_current,
	store_raw,
	write_artefact,
)
from alea.io.sources import Access, get_fetcher, get_source
from alea.provenance.models import DerivedProvenance, Provenance


@dataclass(frozen=True)
class FetchResult:
	"""What one retrieval produced."""

	source_id: str
	checksum: str
	bytes_written: int
	path: Path


@dataclass(frozen=True)
class BuildResult:
	"""What one stage build produced."""

	stage: str
	checksum: str
	path: Path
	skipped: bool = False


def fetch_source(
	source_id: str,
	root: str | Path,
	*,
	force: bool = False,
	logger: Any = None,
) -> FetchResult:
	"""Retrieve one source into the immutable raw layer.

	``force`` is accepted and ignored for the *store*: raw is content-addressed,
	so a re-fetch of identical bytes is a no-op by construction and a re-fetch
	of different bytes is a new address. What ``force`` does control is whether
	the fetcher is called at all when a payload for this source is already held
	-- a fetch is a network call, and repeating it to prove it is deterministic
	is not worth the bandwidth by default.
	"""
	source = get_source(source_id)

	if not force:
		held = _newest_raw(root, source_id)
		if held is not None:
			if logger is not None:
				logger.info("fetch.skip", source=source_id, checksum=held[0][:12])
			return FetchResult(
				source_id=source_id,
				checksum=held[0],
				bytes_written=0,
				path=held[1],
			)

	if source.access is Access.CREDENTIALED and source.credential_env:
		import os

		if not os.environ.get(source.credential_env):
			raise ArtefactError(
				f"{source_id} needs {source.credential_env} in the environment; "
				f"refusing rather than recording a skip as a successful fetch"
			)

	payload = get_fetcher(source_id)(source)

	provenance = Provenance(
		source_id=source.id,
		source_url=source.url,
		licence=source.licence,
		basis=source.basis,
		uncertainty=0.0,
		notes=f"{source.name}. {source.notes}".strip(),
	)
	path = store_raw(source_id, payload, provenance, root=root)
	return FetchResult(
		source_id=source_id,
		checksum=path.parent.name,
		bytes_written=len(payload),
		path=path,
	)


def _newest_raw(root: str | Path, source_id: str) -> tuple[str, Path] | None:
	"""The most recently modified payload held for a source, if any."""
	directory = Path(root) / source_id
	if not directory.is_dir():
		return None
	candidates = sorted(
		(p for p in directory.iterdir() if p.is_dir()),
		key=lambda p: p.stat().st_mtime,
		reverse=True,
	)
	for candidate in candidates:
		payloads = [p for p in candidate.iterdir() if p.is_file() and p.name != "provenance.json"]
		if payloads:
			return candidate.name, payloads[0]
	return None


StageBuilder = Callable[[Config, Path, "BuildContext"], DerivedProvenance]
"""A stage builder writes its artefact and returns its provenance."""


@dataclass
class BuildContext:
	"""What a builder is handed."""

	out: Path
	inputs: list[str]
	"""Checksums of the artefacts this stage read."""

	logger: Any = None


_BUILDERS: dict[str, StageBuilder] = {}


def stage(name: str) -> Callable[[StageBuilder], StageBuilder]:
	"""Register a stage builder."""

	def decorate(function: StageBuilder) -> StageBuilder:
		_BUILDERS[name] = function
		return function

	return decorate


def build_stage(
	stage_name: str,
	config: Config,
	out: str | Path,
	*,
	inputs: list[str] | None = None,
	force: bool = False,
	logger: Any = None,
) -> BuildResult:
	"""Build one processed dataset.

	The idempotence check is on the output's recorded inputs, not on a
	timestamp: a stage that ran yesterday against different inputs is stale even
	though it is newer than everything else, and a stage that ran today against
	the same inputs is current even though a clock says otherwise.
	"""
	target = Path(out)
	if stage_name not in _BUILDERS:
		raise KeyError(
			f"unknown stage {stage_name!r}; registered: {', '.join(sorted(_BUILDERS)) or 'none'}"
		)

	declared = list(inputs or [])
	if not force and declared and stage_is_current(target, declared):
		if logger is not None:
			logger.info("build.skip", stage=stage_name, out=str(target))
		return BuildResult(
			stage=stage_name,
			checksum=_sidecar_checksum(target),
			path=target,
			skipped=True,
		)

	context = BuildContext(out=target, inputs=declared, logger=logger)
	provenance = _BUILDERS[stage_name](config, target, context)
	if provenance is None:
		raise ArtefactError(f"stage {stage_name!r} returned no provenance")

	if not artefact_exists(target):
		raise ArtefactError(
			f"stage {stage_name!r} returned without writing {target}; a stage "
			f"that reports success without an artefact is a stage that did nothing"
		)
	return BuildResult(
		stage=stage_name,
		checksum=_sidecar_checksum(target),
		path=target,
	)


def _sidecar_checksum(target: Path) -> str:
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	if not sidecar.exists():
		return ""
	import json

	return json.loads(sidecar.read_text(encoding="utf-8")).get("checksum", "")


def write_stage(
	path: Path,
	data: Any,
	provenance: DerivedProvenance,
	*,
	format: str | None = None,
) -> str:
	"""Convenience for a builder: write and return the checksum."""
	return write_artefact(path, data, provenance, format=format)  # type: ignore[arg-type]


def registered_stages() -> list[str]:
	"""Stage names with a builder."""
	return sorted(_BUILDERS)


__all__ = [
	"BuildContext",
	"BuildResult",
	"FetchResult",
	"build_stage",
	"fetch_source",
	"registered_stages",
	"stage",
	"write_stage",
]
