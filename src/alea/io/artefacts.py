# SPDX-License-Identifier: MIT
"""Artefact I/O.

Every stage writes a versioned file and reads versioned files (AD-4). Two
storage regimes:

* ``raw/`` is immutable and content-addressed. Nothing writes to a checksum
  directory that already exists; a re-download producing the same bytes is a
  no-op, and one producing different bytes creates a *new* directory, so the
  old bytes stay addressable.
* ``processed/`` is versioned and carries a provenance sidecar.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import xarray as xr

from alea.config.paths import resolve
from alea.provenance.models import DerivedProvenance, Provenance

Format = Literal["parquet", "netcdf", "geojson", "csv", "json"]

_EXTENSIONS: dict[Format, str] = {
	"parquet": ".parquet",
	"netcdf": ".nc",
	"geojson": ".geojson",
	"csv": ".csv",
	"json": ".json",
}


class ArtefactError(Exception):
	"""An artefact could not be written, read, or verified."""


def sha256_bytes(payload: bytes) -> str:
	"""Content hash of a payload."""
	return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
	"""Content hash of a file, streamed so a multi-gigabyte cutout is fine."""
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1 << 20), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _infer_format(path: Path) -> Format:
	suffix = path.suffix.lower()
	for fmt, ext in _EXTENSIONS.items():
		if suffix == ext:
			return fmt
	if suffix in (".tif", ".tiff"):
		raise ArtefactError(
			f"{path}: GeoTIFF is not an artefact format; convert to NetCDF or "
			f"GeoJSON at ingestion so provenance covers the converted payload"
		)
	raise ArtefactError(f"{path}: cannot infer artefact format from suffix {suffix!r}")


# --------------------------------------------------------------------------
# Raw layer: immutable, content-addressed
# --------------------------------------------------------------------------


def raw_path(source_id: str, checksum: str, root: str | Path = "data/raw") -> Path:
	"""The content-addressed directory for one raw payload."""
	return resolve(root) / source_id / checksum


def store_raw(
	source_id: str,
	payload: bytes,
	provenance: Provenance,
	*,
	root: str | Path = "data/raw",
	filename: str = "payload",
) -> Path:
	"""Store a raw payload, addressed by its content.

	Idempotent by construction: if the checksum directory exists the payload is
	already held, and writing again would either be a no-op (same bytes) or a
	contradiction (the address is the hash). The provenance file records the
	retrieval; the payload's checksum covers the payload only.
	"""
	checksum = sha256_bytes(payload)
	directory = raw_path(source_id, checksum, root)
	payload_path = directory / filename

	if directory.exists():
		existing = payload_path.exists() and sha256_file(payload_path) == checksum
		if not existing:
			raise ArtefactError(
				f"{directory} exists but does not hold the payload its address "
				f"claims; the raw layer has been tampered with"
			)
		return payload_path

	directory.mkdir(parents=True, exist_ok=False)
	payload_path.write_bytes(payload)
	(directory / "provenance.json").write_text(
		json.dumps(
			{**provenance.model_dump(mode="json"), "checksum": checksum},
			indent=2,
			sort_keys=True,
		),
		encoding="utf-8",
	)
	return payload_path


def read_raw(
	source_id: str,
	checksum: str,
	*,
	root: str | Path = "data/raw",
	filename: str = "payload",
) -> bytes:
	"""Read a raw payload, verifying its address on the way out."""
	path = raw_path(source_id, checksum, root) / filename
	if not path.exists():
		raise ArtefactError(f"no raw payload at {path}")
	payload = path.read_bytes()
	actual = sha256_bytes(payload)
	if actual != checksum:
		raise ArtefactError(
			f"{path}: content hash {actual[:12]} does not match its address "
			f"{checksum[:12]}; the payload changed after it was stored"
		)
	return payload


# --------------------------------------------------------------------------
# Processed layer: versioned, provenance sidecar
# --------------------------------------------------------------------------


def _write_payload(path: Path, data: Any, fmt: Format) -> None:
	if fmt == "parquet":
		if not isinstance(data, pd.DataFrame):
			raise ArtefactError("parquet payloads must be a pandas DataFrame")
		data.to_parquet(path, index=False)
	elif fmt == "csv":
		if not isinstance(data, pd.DataFrame):
			raise ArtefactError("csv payloads must be a pandas DataFrame")
		data.to_csv(path, index=False)
	elif fmt == "netcdf":
		if not isinstance(data, xr.Dataset):
			raise ArtefactError("netcdf payloads must be an xarray Dataset")
		data.to_netcdf(path)
	elif fmt == "geojson":
		if not hasattr(data, "to_file"):
			raise ArtefactError("geojson payloads must be a GeoDataFrame")
		data.to_file(path, driver="GeoJSON")
	else:
		path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _read_payload(path: Path, fmt: Format) -> Any:
	if fmt == "parquet":
		return pd.read_parquet(path)
	if fmt == "csv":
		return pd.read_csv(path)
	if fmt == "netcdf":
		return xr.open_dataset(path)
	if fmt == "geojson":
		import geopandas as gpd

		return gpd.read_file(path)
	return json.loads(path.read_text(encoding="utf-8"))


def write_artefact(
	path: str | Path,
	data: Any,
	provenance: DerivedProvenance,
	*,
	format: Format | None = None,
) -> str:
	"""Write data plus its provenance. Returns the payload checksum.

	The provenance sidecar is written *after* the payload, and its own checksum
	covers the payload only, so the pair is verifiable: read the payload, hash
	it, compare against the sidecar.
	"""
	target = resolve(path)
	fmt = format or _infer_format(target)
	target.parent.mkdir(parents=True, exist_ok=True)
	_write_payload(target, data, fmt)

	checksum = sha256_file(target)
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	sidecar.write_text(
		json.dumps(
			{**provenance.model_dump(mode="json"), "checksum": checksum},
			indent=2,
			sort_keys=True,
		),
		encoding="utf-8",
	)
	return checksum


def read_artefact(
	path: str | Path,
	*,
	verify: bool = True,
) -> tuple[Any, DerivedProvenance]:
	"""Read data and its provenance, verifying the payload checksum.

	Verification is on by default: an artefact whose bytes changed since it was
	written is an artefact whose result cannot be reproduced, and reading it
	without noticing is how a stale intermediate becomes a published number.
	"""
	target = resolve(path)
	if not target.exists():
		raise ArtefactError(f"no artefact at {target}")
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	if not sidecar.exists():
		raise ArtefactError(
			f"{target}: no provenance sidecar; an artefact without provenance "
			f"cannot be traced to what produced it"
		)
	record = json.loads(sidecar.read_text(encoding="utf-8"))
	recorded_checksum = record.pop("checksum", "")
	if verify:
		actual = sha256_file(target)
		if actual != recorded_checksum:
			raise ArtefactError(
				f"{target}: content hash {actual[:12]} does not match the "
				f"recorded {recorded_checksum[:12]}; the artefact changed after "
				f"it was written"
			)
	return _read_payload(target, _infer_format(target)), DerivedProvenance.model_validate(record)


def read_provenance(path: str | Path) -> DerivedProvenance:
	"""Read only an artefact's provenance."""
	target = resolve(path)
	sidecar = target.with_suffix(target.suffix + ".provenance.json")
	if not sidecar.exists():
		raise ArtefactError(f"{target}: no provenance sidecar")
	record = json.loads(sidecar.read_text(encoding="utf-8"))
	record.pop("checksum", None)
	return DerivedProvenance.model_validate(record)


def artefact_exists(path: str | Path) -> bool:
	"""Whether a payload and its sidecar are both present."""
	target = resolve(path)
	return target.exists() and target.with_suffix(target.suffix + ".provenance.json").exists()


# --------------------------------------------------------------------------
# Idempotence
# --------------------------------------------------------------------------


def stage_is_current(path: str | Path, inputs: list[str]) -> bool:
	"""Whether an artefact was built from exactly these input checksums.

	Every stage checks this and exits without work when it holds. ``--force``
	overrides at the CLI.
	"""
	target = resolve(path)
	if not artefact_exists(target):
		return False
	try:
		provenance = read_provenance(target)
	except ArtefactError:
		return False
	return sorted(provenance.inputs) == sorted(inputs)


def copy_artefact(src: str | Path, dst: str | Path) -> Path:
	"""Copy a payload and its sidecar together.

	Copying the payload alone produces an artefact with no provenance, which
	``read_artefact`` then refuses -- correctly, but at a confusing moment.
	"""
	source = resolve(src)
	target = resolve(dst)
	if not source.exists():
		raise ArtefactError(f"no artefact at {source}")
	target.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(source, target)
	sidecar = source.with_suffix(source.suffix + ".provenance.json")
	if sidecar.exists():
		shutil.copy2(sidecar, target.with_suffix(target.suffix + ".provenance.json"))
	return target


def utcnow() -> datetime:
	"""Timezone-aware UTC now. Naive datetimes are not permitted anywhere."""
	return datetime.now(UTC)


__all__ = [
	"ArtefactError",
	"Format",
	"artefact_exists",
	"copy_artefact",
	"raw_path",
	"read_artefact",
	"read_provenance",
	"read_raw",
	"sha256_bytes",
	"sha256_file",
	"stage_is_current",
	"store_raw",
	"utcnow",
	"write_artefact",
]
