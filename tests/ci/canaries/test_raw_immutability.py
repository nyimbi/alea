# SPDX-License-Identifier: MIT
"""Canary: the raw layer must refuse a payload that contradicts its address.

Raw is content-addressed: the directory name is the sha256 of the bytes it
holds. That makes the store idempotent, and it makes tampering detectable --
but only if something checks. If `store_raw` trusted the directory name instead
of re-hashing the file, an edited payload would be served forever under the
checksum the provenance record attests to, and every number derived from it
would be unreproducible with no indication why.

**A canary must not `importlib.reload` the module it blinds.** The canary here
did, in the parent process, and a reload builds new class objects: the
``ArtefactError`` every other module imported became a stale binding, so
`pytest.raises(ArtefactError)` stopped catching a genuine one and the failure
surfaced in an unrelated test that ran later. It mutates the source and
exercises it in a **subprocess** instead, which imports the mutated source
cleanly and cannot leak a class identity into the suite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from alea.io.artefacts import ArtefactError, raw_path, sha256_bytes, store_raw
from alea.provenance.models import Basis, Licence, Provenance
from tests.ci.canaries import REPO, planted

PAYLOAD = b"observed capacity, 2026-01-01\n"


def _provenance() -> Provenance:
	return Provenance(
		source_id="canary",
		source_url="https://example.org/canary",
		licence=Licence.CC_BY_4_0,
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


#: Runs the tamper check against the tree as it stands on disk and prints the
#: outcome. A **subprocess**, not an in-process `importlib.reload`, and that is
#: the whole point of this canary's shape -- see the module docstring.
_TAMPER_PROGRAM = """
import tempfile
from pathlib import Path
from alea.io.artefacts import ArtefactError, store_raw
from alea.provenance.models import Basis, Licence, Provenance

payload = b"observed capacity, 2026-01-01\\n"
prov = Provenance(
    source_id="canary",
    source_url="https://example.org/canary",
    licence=Licence.CC_BY_4_0,
    basis=Basis.MEASURED,
    uncertainty=0.0,
    notes="canary",
)
root = Path(tempfile.mkdtemp(prefix="canary-raw-"))
stored = store_raw("canary", payload, prov, root=root)
stored.write_bytes(b"tampered\\n")
try:
    store_raw("canary", payload, prov, root=root)
except ArtefactError:
    print("refused")
else:
    print("accepted")
"""


def _tamper_outcome() -> str:
	"""``"refused"`` or ``"accepted"``, from a subprocess against the on-disk tree."""
	env = {**os.environ, "PYTHONPATH": str(REPO)}
	completed = subprocess.run(
		[sys.executable, "-c", _TAMPER_PROGRAM],
		capture_output=True,
		text=True,
		check=False,
		env=env,
	)
	assert completed.returncode == 0, completed.stderr
	return completed.stdout.strip()


def test_the_rehash_is_the_gate():
	"""Canary proper: remove the re-hash and watch the tamper check go blind.

	**Why a subprocess rather than an in-process `importlib.reload`.** This test
	used to reload `alea.io.artefacts` in the parent process, twice. A reload
	re-executes the module and builds **new class objects**, so the
	``ArtefactError`` every other module bound at import time becomes a stale
	one: `pytest.raises(ArtefactError)` then fails to catch an exception whose
	type and message both look right, and the failure lands in whichever
	unrelated test runs next. It did -- `test_planning_inputs.py` failed after
	the canaries in every full-suite run, and passed in isolation, which reads
	as a flake in a file the change never touched. The reload bought nothing
	that a fresh interpreter does not: `planted` mutates the source, and a
	subprocess imports the mutated source from scratch.
	"""
	artefacts = REPO / "src" / "alea" / "io" / "artefacts.py"
	target = 'existing = payload_path.exists() and sha256_file(payload_path) == checksum'
	assert target in artefacts.read_text(), "canary target not found"

	# The gate, as shipped.
	assert _tamper_outcome() == "refused", "the shipped re-hash accepted a tampered payload"

	with planted(artefacts, target, "existing = payload_path.exists()"):
		# With the re-hash gone the tampered payload is accepted silently. This
		# is the blindness the canary asserts; if it still refused, the re-hash
		# was not what the test above was measuring.
		assert _tamper_outcome() == "accepted", (
			"the tamper check still refused with the re-hash removed, so the "
			"re-hash is not the gate this canary claims to watch"
		)

	# Restored: the gate works again.
	assert _tamper_outcome() == "refused", "the restore did not put the gate back"


def test_raw_path_is_a_function_of_the_checksum(tmp_path: Path):
	assert raw_path("canary", "abc123", tmp_path) == raw_path("canary", "abc123", tmp_path)
	assert raw_path("canary", "abc123", tmp_path) != raw_path("canary", "def456", tmp_path)
