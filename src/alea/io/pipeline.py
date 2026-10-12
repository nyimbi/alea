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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alea.config.models import Config
from alea.io.artefacts import (
	ArtefactError,
	artefact_exists,
	read_provenance,
	stage_is_current,
	store_raw,
	write_artefact,
)
from alea.io.sources import Access, get_fetcher, get_source
from alea.logging import get_logger
from alea.provenance.models import DerivedProvenance, Provenance

_log = get_logger(__name__)


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
	parameters: dict[str, Any] = field(default_factory=dict)
	"""Extra values a builder may read, from the CLI's repeatable ``--set``.

	A stage parameter is not a config key. The config is validated against a
	model with ``extra="forbid"``, so a key added for one stage's convenience is
	a key every config must then carry -- and the alternative, reading it off the
	environment, is a run whose behaviour is not in its own command line.
	``build_stage`` forwards its ``parameters`` argument here and the builder
	reads what it needs, defaulting when it is absent. The values reach the
	artefact's provenance either way, which is what makes the run reproducible.
	"""


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
	parameters: dict[str, Any] | None = None,
) -> BuildResult:
	"""Build one processed dataset.

	The idempotence check is on the output's recorded inputs, not on a
	timestamp: a stage that ran yesterday against different inputs is stale even
	though it is newer than everything else, and a stage that ran today against
	the same inputs is current even though a clock says otherwise.
	"""
	_register_all()
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

	context = BuildContext(out=target, inputs=declared, logger=logger, parameters=dict(parameters or {}))
	recorded_before = _recorded_run_id(target)
	provenance = _BUILDERS[stage_name](config, target, context)
	if provenance is None:
		raise ArtefactError(f"stage {stage_name!r} returned no provenance")

	if not artefact_exists(target):
		raise ArtefactError(
			f"stage {stage_name!r} returned without writing {target}; a stage "
			f"that reports success without an artefact is a stage that did nothing"
		)
	# A builder whose inputs it resolves itself -- the newest solved network, a
	# file named at runtime -- cannot be declared by the caller and so cannot be
	# checked above. It calls `skip_if_current` and returns the provenance it
	# found; the run id is what says so, and it is a value rather than a clock.
	# `mtime` would call a stage that rewrote identical bytes current, and a
	# stage that wrote different bytes stale, which is the wrong way round.
	return BuildResult(
		stage=stage_name,
		checksum=_sidecar_checksum(target),
		path=target,
		skipped=recorded_before is not None and provenance.run_id == recorded_before,
	)


def _recorded_run_id(target: Path) -> str | None:
	"""The run id in an artefact's sidecar, or None when there is no sidecar."""
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	if not sidecar.exists():
		return None
	import json

	try:
		return json.loads(sidecar.read_text(encoding="utf-8")).get("run_id")
	except (OSError, ValueError):  # pragma: no cover - a corrupt sidecar
		return None


def skip_if_current(
	out: Path,
	inputs: list[str],
	*,
	stage_name: str,
	logger: Any = None,
) -> DerivedProvenance | None:
	"""The existing provenance when ``out`` already records exactly ``inputs``.

	For a stage whose inputs it resolves itself. The CLI cannot declare "the
	newest solved network in this directory" -- that is a runtime fact, not a
	path a rule can name -- so ``build_stage``'s own check, which compares a
	caller's declaration against the sidecar, can never fire for such a stage.
	The builder calls this first and returns what it gets, and ``build_stage``
	reports the run as skipped because the run id is the one already recorded.

	Every stage in the workflow was in this position: no rule passed ``--input``,
	so ``declared`` was empty, the check short-circuited on it, and *every*
	``alea build`` rebuilt. ``02-data-pipeline.md`` §4.1 asks every stage to
	"check its output checksum against a recorded manifest and exit without work
	if unchanged", and that was true of no stage the workflow runs.
	"""
	assert out is not None, "out must not be None"
	if not inputs:
		return None
	if not stage_is_current(out, list(inputs)):
		return None
	existing = read_provenance(out)
	if logger is not None:
		logger.info("build.skip", stage=stage_name, out=str(out), resolved_inputs=len(inputs))
	return existing


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


_REGISTRATION_MODULES = (
	"alea.io.stages",
	"alea.losses.service",
	"alea.outages.service",
	"alea.planning.arrays",
	"alea.publish.stages",
	"alea.quality.service",
	"alea.resilience.service",
	"alea.sector.service",
)
"""Modules that declare stage builders with ``@stage``.

A registry populated by decorators is populated only when the declaring module
is imported, and ``build_stage`` imports none of them: the CLI reported
``unknown stage 'tlens'; registered: none`` for a stage whose own file says
``@stage("tlens")``. The stage was written, decorated and unreachable. This
tuple is the import list that closes the gap, kept beside the registry it fills
so a new stage module is added in the one place a reader looks for it.
"""


def _register_all() -> None:
	"""Import every stage-declaring module, so their decorators run.

	Import failures are swallowed: a stage module that cannot import (a missing
	optional dependency) must not make every *other* stage undiscoverable, which
	would be the same failure this function exists to fix. ``registered_stages``
	is the observable that says what actually registered.
	"""
	import importlib

	for module in _REGISTRATION_MODULES:
		try:
			importlib.import_module(module)
		except ImportError as exc:  # pragma: no cover - depends on the environment
			_log.warning("stage_registration_failed", module=module, error=str(exc))


def registered_stages() -> list[str]:
	"""Stage names with a builder, after importing the declaring modules."""
	_register_all()
	return sorted(_BUILDERS)


__all__ = [
	"BuildContext",
	"BuildResult",
	"FetchResult",
	"build_stage",
	"fetch_source",
	"registered_stages",
	"skip_if_current",
	"stage",
	"write_stage",
]
