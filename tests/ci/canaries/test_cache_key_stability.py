# SPDX-License-Identifier: MIT
"""Canary: the what-if cache key must be stable across processes.

The specification's key is `hash(tuple(sorted(params.items())))`. `hash()` of a
string is salted per interpreter, so that key differs after every restart: the
cache never hits across a run boundary and every re-solve is a full solve.

The defect is **invisible in-process**. Computing the key twice in one
interpreter returns the same value whether the key is a content hash or a
string hash, so a test written the obvious way passes against the broken
implementation. The check has to cross a process boundary with a different
`PYTHONHASHSEED`, which is why `key_is_process_stable` ships in the package
rather than living only here.

The canary reverts `cache_key` to the string hash and asserts the cross-process
check notices -- and, separately, that an in-process comparison does *not*,
which is the whole reason the gate is shaped this way.

The gate is the plan's `test_cache_key_stable_across_processes` (08-layer5 §9).
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys

import pytest

from alea.whatif.cache import cache_key, key_is_process_stable
from alea.whatif.params import ScenarioParameters
from tests.ci.canaries import REPO, planted

CACHE_PY = REPO / "src" / "alea" / "whatif" / "cache.py"
NETWORK = "sha256:" + "ab" * 32
CODE = "0.1.0"


def _params() -> ScenarioParameters:
	return ScenarioParameters()


def test_the_key_is_a_function_of_the_values_alone():
	a = cache_key(_params(), NETWORK, CODE)
	b = cache_key(_params(), NETWORK, CODE)
	assert a == b
	assert cache_key(_params().with_value("demand_growth", 0.05), NETWORK, CODE) != a
	assert cache_key(_params(), "sha256:" + "cd" * 32, CODE) != a
	assert cache_key(_params(), NETWORK, "0.1.1") != a


def test_the_key_is_stable_across_processes():
	"""The real gate. Two interpreters with different hash seeds must agree."""
	assert key_is_process_stable(_params(), NETWORK, CODE)


def test_a_string_hash_key_is_invisible_in_process():
	"""The reason the gate crosses a process boundary.

	Both a content hash and a string hash return the same value twice within one
	interpreter. This asserts that the naive check -- compute it twice, compare
	-- cannot tell them apart, so a same-process test would be no gate at all.
	"""
	in_process = {hash(tuple(sorted(_params().canonical().items()))) for _ in range(2)}
	assert len(in_process) == 1, (
		"a string hash disagreed with itself in one process, which it does not "
		"do; the in-process blindness argument no longer holds"
	)


def test_the_gate_catches_a_string_hash_key():
	"""Canary proper: revert the key to `hash()` and watch the gate fail."""
	import alea.whatif.cache as cache_module

	source = CACHE_PY.read_text()
	assert "def cache_key" in source, "canary target not found"
	# The mutation is on the returned value, which is the narrowest edit that
	# reproduces the specification's defect.
	target = '\treturn sha256_bytes(payload.encode("utf-8"))'
	assert target in source, "canary target not found: the sha256 return line moved"

	with planted(CACHE_PY, target, "\treturn str(hash(payload))"):
		importlib.reload(cache_module)
		# In-process the reverted key still agrees with itself: the defect is
		# invisible here, which is the point.
		assert cache_module.cache_key(_params(), NETWORK, CODE) == cache_module.cache_key(
			_params(), NETWORK, CODE
		)
		# Across processes it does not. This is the observation the gate makes.
		seeds = []
		for seed in ("1", "4242"):
			result = subprocess.run(
				[
					sys.executable,
					"-c",
					"import json,sys;from alea.whatif.cache import cache_key;"
					"from alea.whatif.params import ScenarioParameters;"
					"print(cache_key(ScenarioParameters.model_validate(json.loads(sys.argv[1])),"
					"sys.argv[2],sys.argv[3]))",
					json.dumps(_params().canonical()),
					NETWORK,
					CODE,
				],
				capture_output=True,
				text=True,
				env={**os.environ, "PYTHONHASHSEED": seed},
				check=False,
			)
			assert result.returncode == 0, result.stderr
			seeds.append(result.stdout.strip())
		assert seeds[0] != seeds[1], (
			"the reverted key agreed across hash seeds; the canary did not "
			"reproduce the defect it plants"
		)

	# Restored: the gate works again.
	importlib.reload(cache_module)
	assert cache_module.key_is_process_stable(_params(), NETWORK, CODE)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
