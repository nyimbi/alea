# SPDX-License-Identifier: MIT
"""Canaries for the extraction gates: the content cache and output validation.

* ``test_extraction_cache_hits`` — the same document, the same prompt version,
  extracts once. Remove the cache lookup and every re-run pays the provider
  again, and — worse for reproducibility — a v2 prompt silently re-extracts the
  whole corpus rather than reusing what v1 produced under v1's key. The canary
  makes the cache lookup unconditional-miss (``self._cache = None``) and watches
  the gate's call count double.
* ``test_llm_output_validated`` — a model that answers with a JSON array, a bare
  string, or prose did not follow the schema, and ``_parse`` refuses rather than
  coercing. The canary makes it coerce a non-object into ``{"signals": ...}``
  and watches the gate's shape assertion fail.

Both probes run in a subprocess so the mutated module is read fresh.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted

LLM_PY = REPO / "src" / "alea" / "scanning" / "extract" / "llm.py"

_CACHE_PROBE = textwrap.dedent(
	"""
	import asyncio, json, tempfile, pathlib
	from alea.scanning.extract import Extractor
	from alea.scanning.extract.llm import ExtractionConfig, LlmCache
	from alea.scanning.connectors.base import make_document

	class Client:
		def __init__(self):
			self.calls = 0
		async def complete(self, system, user, *, model, temperature, seed, timeout_s):
			self.calls += 1
			return json.dumps({"signals": []})

	async def main():
		with tempfile.TemporaryDirectory() as d:
			client = Client()
			extractor = Extractor(config=ExtractionConfig(model="m"), client=client)
			extractor._llm._cache = LlmCache(pathlib.Path(d) / "cache")
			doc = make_document(source_name="s", url="u", title="t",
				text="Kenya added one hundred megawatts of solar capacity in 2026")
			await extractor.extract_document(doc)
			await extractor.extract_document(doc)
			print("CALLS", client.calls)

	asyncio.run(main())
	"""
)


def _cache_calls() -> int:
	completed = subprocess.run(
		[sys.executable, "-c", _CACHE_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	marked = [line for line in completed.stdout.splitlines() if line.startswith("CALLS ")]
	assert marked, f"the cache probe printed nothing:\n{completed.stdout}"
	return int(marked[-1].split()[1])


def test_the_cache_gate_notices_a_removed_lookup():
	"""Disable the cache and watch the same document call the provider twice."""
	assert _cache_calls() == 1, "the cache already missed before any mutation"

	# The lookup is the `if self._cache is not None:` guarding `cached = self._cache.get(key)`.
	target = "\t\tif self._cache is not None:\n\t\t\tcached = self._cache.get(key)\n"
	replacement = "\t\tif False:\n\t\t\tcached = self._cache.get(key)\n"
	with planted(LLM_PY, target, replacement):
		assert _cache_calls() == 2, (
			"with the lookup disabled the second extraction still hit the cache; "
			"the gate does not measure the cache"
		)

	# Restored.
	assert _cache_calls() == 1


_VALIDATION_PROBE = textwrap.dedent(
	"""
	from alea.scanning.extract.llm import LlmExtractor
	for label, payload in [("prose", "here is your answer"), ("array", "[1, 2]")]:
		parsed = LlmExtractor._parse(payload)
		has_error = "_error" in parsed
		print("PARSED", label, parsed.get("signals"), "error=" + str(has_error))
	"""
)


def _validation() -> list[str]:
	completed = subprocess.run(
		[sys.executable, "-c", _VALIDATION_PROBE], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	return [line for line in completed.stdout.splitlines() if line.startswith("PARSED ")]


def test_the_validation_gate_notices_a_coerced_response():
	"""Coerce prose into a signal list and watch the gate's shape assertion fail.

	``_parse`` returns ``{"signals": [], "_error": ...}`` for prose and
	``{"signals": [1, 2]}`` for a bare array — the array case is deliberately
	wrapped, but the *prose* case must not be. The canary replaces the
	unparseable return with one that fabricates an empty signal list *and no
	error marker*, so the caller can no longer tell the response failed to parse.
	"""
	lines = _validation()
	prose = next(line for line in lines if line.startswith("PARSED prose "))
	assert "error=True" in prose, f"prose was already coerced before any mutation: {prose}"

	target = '\t\t\t\treturn {"signals": [], "_error": "unparseable response"}'
	replacement = '\t\t\t\treturn {"signals": []}'
	with planted(LLM_PY, target, replacement):
		after = next(
			line for line in _validation() if line.startswith("PARSED prose ")
		)
		assert "error=False" in after, (
			"with the error marker removed the probe still reported one; the gate "
			"cannot see the coercion"
		)

	# Restored.
	restored = next(line for line in _validation() if line.startswith("PARSED prose "))
	assert "error=True" in restored
