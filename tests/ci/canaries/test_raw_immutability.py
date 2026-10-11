# SPDX-License-Identifier: MIT
"""Canary: the raw layer must refuse a payload that contradicts its address.

Raw is content-addressed: the directory name is the sha256 of the bytes it
holds. That makes the store idempotent, and it makes tampering detectable --
but only if something checks. If `store_raw` trusted the directory name instead
of re-hashing the file, an edited payload would be served forever under the
checksum the provenance record attests to, and every number derived from it
would be unreproducible with no indication why.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alea.io.artefacts import ArtefactError, raw_path, sha256_bytes, store_raw
from alea.provenance.models import Basis, Provenance
from tests.ci.canaries import REPO, planted

PAYLOAD = b"observed capacity, 2026-01-01\n"


def _provenance() -> Provenance:
	return Provenance(
		source_id="canary",
		source_url="https://example.org/canary",
		licence="CC-BY-4.0",
		basis=Basis.MEASURED,
		uncertainty=0.0,
		notes="canary",
	)


def test_a_stored_payload_is_addressed_by_its_content(tmp_path: Path):
	path = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	assert path.parent.name == sha256_bytes(PAYLOAD)
	assert path.read_bytes() == PAYLOAD


def test_storing_the_same_bytes_twice_is_idempotent(tmp_path: Path):
	first = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	second = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	assert first == second


def test_edited_bytes_under_a_checksum_directory_are_refused(tmp_path: Path):
	"""Plant the defect: change the payload, keep the address."""
	path = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	path.write_bytes(b"a different payload entirely\n")
	# The address still exists, so `store_raw` takes the early-return branch --
	# and that branch is where the re-hash has to happen.
	with pytest.raises(ArtefactError, match="tampered"):
		store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)


def test_the_rehash_is_the_gate():
	"""Canary proper: remove the re-hash and watch the tamper check go blind."""
	artefacts = REPO / "src" / "alea" / "io" / "artefacts.py"
	target = 'existing = payload_path.exists() and sha256_file(payload_path) == checksum'
	assert target in artefacts.read_text(), "canary target not found"

	import importlib
	import tempfile

	import alea.io.artefacts as artefacts_module

	with planted(artefacts, target, "existing = payload_path.exists()"):
		importlib.reload(artefacts_module)
		root = Path(tempfile.mkdtemp(prefix="canary-raw-"))
		stored = artefacts_module.store_raw("canary", PAYLOAD, _provenance(), root=root)
		stored.write_bytes(b"tampered\n")
		# With the re-hash gone the tampered payload is accepted silently. This
		# is the blindness the canary asserts; if it still raised, the re-hash
		# was not what the test above was measuring.
		returned = artefacts_module.store_raw("canary", PAYLOAD, _provenance(), root=root)
		assert returned == stored

	# Reloaded *after* `planted` has restored the file. Reloading inside the
	# context manager re-reads the mutated source and leaves the module blind
	# for every test that follows.
	importlib.reload(artefacts_module)

	# Restored: the gate works again.
	root = Path(tempfile.mkdtemp(prefix="canary-raw-"))
	stored = artefacts_module.store_raw("canary", PAYLOAD, _provenance(), root=root)
	stored.write_bytes(b"tampered\n")
	with pytest.raises(artefacts_module.ArtefactError, match="tampered"):
		artefacts_module.store_raw("canary", PAYLOAD, _provenance(), root=root)


def test_raw_path_is_a_function_of_the_checksum(tmp_path: Path):
	assert raw_path("canary", "abc123", tmp_path) == raw_path("canary", "abc123", tmp_path)
	assert raw_path("canary", "abc123", tmp_path) != raw_path("canary", "def456", tmp_path)
