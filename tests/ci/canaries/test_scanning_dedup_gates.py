# SPDX-License-Identifier: MIT
"""Canaries for the dedup gates: determinism and ordered shingles.

* ``test_dedup_deterministic`` — the signature is a function of the text and the
  seed, not of the interpreter. The defect is AD-8: a MinHash seeded from
  Python's ``hash()``, which is randomised per process, so two runs of the same
  pipeline deduplicate differently and an artefact built from one is not
  reproducible from the other. The canary replaces the explicit ``seed`` the
  kernel is given with ``hash(...)``, which is exactly the defect, and asserts
  the gate's two-subprocess probe diverges.
* ``test_shingles_ordered`` — shingles are a generator over an ordered token
  sequence. The specification shingled into a ``set``; the canary restores that
  and asserts the gate notices the returned object is a set.

Both probes run in a subprocess so the mutated module is read fresh.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

INGEST_PY = REPO / "src" / "alea" / "scanning" / "ingest.py"

# The gate's own corpus and signature, reproduced so the canary fails for the
# same reason the gate would.
_SIG_PROBE = textwrap.dedent(
	"""
	import json, sys
	from alea.scanning.ingest import deduplicate_documents
	from alea.scanning.connectors.base import make_document

	def pair(shared, tag):
		base = [f"tok{i}" for i in range(100)]
		a = base[:shared] + [f"u{tag}a{i}" for i in range(100 - shared)]
		b = base[:shared] + [f"u{tag}b{i}" for i in range(100 - shared)]
		return [(f"s{tag}a", f"u{tag}a", " ".join(a)), (f"s{tag}b", f"u{tag}b", " ".join(b))]

	rows = []
	for tag, shared in enumerate(range(78, 96)):
		rows += pair(shared, tag)
	docs = [make_document(source_name=s, url=u, title=t[:20], text=t) for s, u, t in rows]
	_, report = deduplicate_documents(docs, seed=0)
	sys.stderr.write("SIG " + json.dumps(sorted(sorted(g.member_ids) for g in report.groups)) + "\\n")
	"""
)


def _signature(hash_seed: str) -> str:
	import os

	env = {**os.environ, "PYTHONHASHSEED": hash_seed, "ALEA_OFFLINE": "1"}
	completed = subprocess.run(
		[sys.executable, "-c", _SIG_PROBE], capture_output=True, text=True, check=False, env=env
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stderr.splitlines() if line.startswith("SIG ")]
	assert marked, f"the signature probe printed nothing:\n{completed.stderr}"
	return marked[-1][4:]


def test_the_dedup_gate_notices_a_process_randomised_seed():
	"""Seed the kernel from ``hash()`` and watch two interpreters diverge.

	The mutation replaces the ``seed`` argument to the kernel with
	``hash("alea-dedup") % 1000``. Both interpreters pass ``seed=0`` to
	``deduplicate_documents``, so the only thing that can differ is the hash —
	which is the AD-8 defect stated exactly.
	"""
	assert _signature("0") == _signature("12345"), "the probe diverged before any mutation"

	target = "\t\t\tthreshold,\n\t\t\tseed,\n"
	replacement = '\t\t\tthreshold,\n\t\t\thash("alea-dedup") % 1000,\n'
	with planted(INGEST_PY, target, replacement):
		first = _signature("0")
		second = _signature("12345")
		assert first != second, (
			"with a hash-derived seed the two interpreters still agreed; the gate "
			"does not detect a process-randomised seed"
		)

	# Restored.
	assert _signature("0") == _signature("12345")


_SHINGLE_PROBE = textwrap.dedent(
	"""
	from alea.scanning.ingest import shingles
	s = shingles("Kenya added one hundred megawatts of solar capacity near Nairobi in 2026")
	print("KIND", "set" if isinstance(s, (set, frozenset)) else type(s).__name__)
	"""
)


def _shingle_kind() -> str:
	completed = subprocess.run(
		[sys.executable, "-c", _SHINGLE_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("KIND ")]
	assert marked, f"the shingle probe printed nothing:\n{completed.stdout}"
	return marked[-1].split()[1]


def test_the_shingles_gate_notices_a_set():
	"""Return a set and watch the gate refuse it.

	The mutation replaces the generator body with a set comprehension, which is
	the specification's original form. The gate asserts the returned object is
	not a set; with the mutation it is.
	"""
	assert _shingle_kind() == "generator", "the shingles probe was already a set"

	target = (
		'\ttokens = [t for t in re.split(r"\\W+", text.lower()) if t and t not in _STOPWORDS]\n'
		"\tfor i in range(len(tokens) - k + 1):\n"
		'\t\tyield " ".join(tokens[i : i + k])\n'
	)
	replacement = (
		'\ttokens = [t for t in re.split(r"\\W+", text.lower()) if t and t not in _STOPWORDS]\n'
		'\treturn {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}\n'
	)
	with planted(INGEST_PY, target, replacement):
		assert _shingle_kind() == "set", (
			"with the generator replaced by a set the probe still reported a "
			"generator; the gate cannot see the defect"
		)

	# Restored.
	assert _shingle_kind() == "generator"
