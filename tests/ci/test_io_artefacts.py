# SPDX-License-Identifier: MIT
"""The raw layer's gates, from `01-foundations.md` §4.3.

§4.3 names two gates and both were missing from the tree as *gates* -- the
behaviour existed, under names the register could not join to the plan, or not
at all:

* ``test_artefact_round_trip`` -- "write, read, compare data and provenance."
  This one was genuinely unbuilt: ``read_raw`` is exported from ``alea.io`` and
  called by **nothing**, so the read side of the raw layer was a function with
  no caller. The write side had tests; the read side had none, and a store
  nobody reads from is a store whose read path is unverified.
* ``test_raw_is_immutable`` -- "a second write to an existing checksum dir
  raises." The tree does something narrower and better: a second write of the
  *same* bytes is idempotent, and it is a second write of *different* bytes
  that raises. That is the case that matters, and it is asserted here.

**Why this is not in `tests/ci/canaries/`.** `12-quality.md` §3.2 puts the gate
in `tests/ci/` and its canary in `tests/ci/canaries/`, and the register reads
that layout: a module under `canaries/` counts as a canary, so a gate whose only
test lives there is reported **unimplemented**. `test_raw_immutability.py` held
both halves -- the gate tests and the subprocess canary that blinds the re-hash
-- which made the register's question unanswerable from the file's location.
The canary stayed where the plan puts it; these are the gates it guards.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alea.io.artefacts import ArtefactError, raw_path, read_raw, sha256_bytes, store_raw
from alea.provenance.models import Basis, Licence, Provenance

PAYLOAD = b"observed capacity, 2026-01-01\n"


def _provenance() -> Provenance:
	return Provenance(
		source_id="canary",
		source_url="https://example.org/canary",
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		uncertainty=0.0,
		notes="gate fixture",
	)


def test_a_stored_payload_is_addressed_by_its_content(tmp_path: Path):
	"""The premise both gates below rest on: the address is the hash."""
	path = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	assert path.parent.name == sha256_bytes(PAYLOAD)
	assert path.read_bytes() == PAYLOAD


def test_artefact_round_trip(tmp_path: Path):
	"""``01-foundations.md`` §4.3: "write, read, compare data and provenance."

	Both halves are compared because they fail differently. A payload that
	round-trips but loses its provenance is an unreproducible number: the bytes
	verify against their address and nothing records where they came from. A
	provenance that survives while the bytes change is the tamper case
	`test_raw_is_immutable` covers. This asserts the pair, which is what the
	plan asks for and what nothing asserted.
	"""
	path = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)

	# Read back through the reader, by address rather than by path -- the
	# function's whole contract is that the address is the checksum.
	restored = read_raw("canary", path.parent.name, root=tmp_path)
	assert restored == PAYLOAD, "the payload did not survive the round trip"

	# The provenance is the sidecar `store_raw` writes beside it. Read as JSON
	# rather than through a model, because there is no reader for the raw
	# sidecar and inventing one here would be testing a function this change
	# did not write.
	sidecar = json.loads((path.parent / "provenance.json").read_text())
	assert sidecar["source_id"] == "canary"
	assert sidecar["checksum"] == path.parent.name, (
		"the sidecar records a checksum other than the directory it sits in, so "
		"the provenance and the address disagree"
	)
	assert sidecar["basis"] == Basis.MEASURED.value, sidecar["basis"]

	# And the reader refuses bytes that do not hash to the address they sit
	# under. Asking for an address that does not exist is a different branch --
	# it raises "no raw payload" -- so the mismatch has to be *planted*: write
	# the payload into a directory named for a checksum it does not have.
	# `store_raw` refuses to create that state, which is why this writes it by
	# hand; the point is that the *reader* also refuses it.
	wrong = raw_path("canary", "0" * 64, tmp_path)
	wrong.mkdir(parents=True)
	(wrong / "payload").write_bytes(PAYLOAD)
	with pytest.raises(ArtefactError, match="does not match its address"):
		read_raw("canary", "0" * 64, root=tmp_path)

	# And a nonexistent address is its own error, named as such rather than
	# reported as a mismatch: a caller asking for a payload nobody stored has
	# made a different mistake from one whose payload was edited.
	with pytest.raises(ArtefactError, match="no raw payload at"):
		read_raw("canary", "1" * 64, root=tmp_path)


def test_storing_the_same_bytes_twice_is_idempotent(tmp_path: Path):
	"""The half of §4.3's immutability rule that is a *return*, not a raise.

	The plan says "a second write to an existing checksum dir raises", which
	predates content addressing: under an address that *is* the hash, storing
	the same bytes again is the same artefact, and refusing it would make every
	retry of a fetch an error. It is the second write of *different* bytes that
	must raise, and `test_raw_is_immutable` below is that half.
	"""
	first = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	second = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	assert first == second


def test_raw_is_immutable(tmp_path: Path):
	"""``01-foundations.md`` §4.3: a contradicting second write must raise.

	The defect this guards: if `store_raw` trusted the directory name instead of
	re-hashing the file, an edited payload would be served forever under the
	checksum the provenance record attests to, and every number derived from it
	would be unreproducible with no indication why. The canary that blinds the
	re-hash lives in `tests/ci/canaries/test_raw_immutability.py`; this is the
	gate it guards.
	"""
	path = store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
	path.write_bytes(b"a different payload entirely\n")

	# The address still exists, so `store_raw` takes the early-return branch --
	# and that branch is where the re-hash has to happen.
	with pytest.raises(ArtefactError, match="tampered"):
		store_raw("canary", PAYLOAD, _provenance(), root=tmp_path)
