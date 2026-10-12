# SPDX-License-Identifier: MIT
"""Canary: watch each Layer 5 gate in `08-layer5-whatif.md` §9 fail on its defect.

Every gate in §9's table is promised a canary that plants the defect the gate
exists to catch and shows the gate noticing. Seven are watched here --
`test_cache_actually_hits`, `test_cache_key_includes_network`,
`test_cache_key_includes_code_version`, `test_apply_does_not_mutate_base`,
`test_renewable_share_nan_on_zero_gen`, `test_frontier_deterministic` and
`test_scenario_records_network`. The remaining §9 rows already have canaries:
`test_cache_key_stable_across_processes` in ``test_cache_key_stability.py``,
`test_renewable_multiplier_absolute` in ``test_whatif_renewable_gate.py``, and
`test_demand_growth_requires_multi_period` plus the static/dynamic reads in
``test_whatif_static_tables.py``.

WHY each mutation is read by a *fresh* module. The gates live in
``tests/ci/test_whatif_layer5.py``, which binds ``WhatIfEngine``, ``cache_key``
and ``apply_parameters`` at import. A canary that patched the file and then
called those names would call the *old* code -- the module is already in
``sys.modules`` and the binding is unchanged -- and would pass against working
code while reporting a blind gate. So every canary here reloads the module that
owns the function under test, and builds the engine through the reloaded
``WhatIfEngine`` rather than through the gate's stale import. ``cache.py`` and
``service.py`` are reloaded together: the engine holds no bound reference to
``cache_key`` -- it calls the module global -- so the two must move as a unit.

The first canary runs in a subprocess instead. It plants a defect in ``cache.py``
and solves twice through a real engine, and a file patch is only visible to an
interpreter that reads the file fresh; reloading would work too, but the
subprocess also proves the gate is not satisfiable by anything this session
holds in memory.

The gate's own file is never mutated. Only ``src/`` is, and ``planted`` restores
it byte-for-byte and proves it.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from alea.whatif import ScenarioParameters
from tests.ci.canaries import REPO, planted
from tests.ci.test_whatif_layer5 import _CountingSolve, _network, _solved

CACHE_PY = REPO / "src" / "alea" / "whatif" / "cache.py"
SERVICE_PY = REPO / "src" / "alea" / "whatif" / "service.py"
APPLY_PY = REPO / "src" / "alea" / "whatif" / "apply.py"
SWEEP_PY = REPO / "src" / "alea" / "whatif" / "sweep.py"
VIEWS_PY = REPO / "src" / "alea" / "whatif" / "views.py"
STORE_PY = REPO / "src" / "alea" / "whatif" / "store.py"

cache_module = importlib.import_module("alea.whatif.cache")
service_module = importlib.import_module("alea.whatif.service")
apply_module = importlib.import_module("alea.whatif.apply")
sweep_module = importlib.import_module("alea.whatif.sweep")
store_module = importlib.import_module("alea.whatif.store")

NETWORK_A = "sha256:" + "ab" * 32
NETWORK_B = "sha256:" + "cd" * 32
CODE = "0.1.0"


def _params() -> ScenarioParameters:
	return ScenarioParameters()


def _fresh_cache_and_service() -> None:
	"""Reload the two modules the engine reads ``cache_key`` and ``SolveCache`` from.

	Order matters: ``service`` imports the two names from ``cache`` at module
	scope, so ``cache`` must be reloaded first for ``service`` to rebind them.
	"""
	importlib.reload(cache_module)
	importlib.reload(service_module)


# --------------------------------------------------------------------------
# test_cache_actually_hits -- blind the cache read; the second solve must re-solve
# --------------------------------------------------------------------------

_CACHE_HITS_PROGRAM = """
import tempfile
from pathlib import Path

import pandas as pd
import pypsa

from alea.whatif.params import ScenarioParameters
from alea.whatif.service import WhatIfEngine


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, network):
        self.calls += 1


def network():
    n = pypsa.Network()
    n.add("Bus", "b1", carrier="AC")
    snapshots = [ts for year in (2030, 2040) for ts in pd.date_range(f"{year}-01-01", periods=2, freq="h")]
    n.set_snapshots(list(snapshots))
    n.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
    n.add("Load", "load", bus="b1", p_set=120.0)
    n.optimize(solver_name="highs", log_to_console=False)
    n.model.solver_model = None
    return n


counter = Counter()
engine = WhatIfEngine(network(), cache_root=Path(tempfile.mkdtemp()), solve_fn=counter)
params = ScenarioParameters(carbon_price_usd_per_tco2=80.0)
engine.solve_with_outcome(params)
second = engine.solve_with_outcome(params)
print("CALLS", counter.calls, "SECOND_FROM_CACHE", second.from_cache)
"""


def _cache_hits() -> str:
	completed = subprocess.run(
		[sys.executable, "-c", _CACHE_HITS_PROGRAM],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	assert completed.returncode == 0, completed.stderr
	return completed.stdout.strip().splitlines()[-1]


def test_the_cache_hits_gate_catches_a_cache_that_never_hits():
	"""``test_cache_actually_hits`` must fail when an entry that exists reads as a miss.

	The gate solves the same scenario twice through one engine and asserts the
	solver ran once. A ``get`` that returns ``None`` for an entry that is on disk
	-- the torn-read defect, or a cache that is simply never consulted -- leaves
	the second solve to run the optimiser again, so the count is 2. The
	observable is the solve count: a cache that never hits returns the same
	result as one that hits, which is why the gate counts rather than compares.
	"""
	assert _cache_hits() == "CALLS 1 SECOND_FROM_CACHE True", (
		"the cache-hits gate already fails on clean source"
	)

	target = "\t\treturn payload"
	assert target in CACHE_PY.read_text(), "canary target not found: the cache read return moved"

	with planted(CACHE_PY, target, "\t\treturn None"):
		broken = _cache_hits()
	assert broken == "CALLS 2 SECOND_FROM_CACHE False", (
		f"with the read blinded the second solve did not re-solve: {broken}"
	)

	assert _cache_hits() == "CALLS 1 SECOND_FROM_CACHE True", "the restore was not proven"


# --------------------------------------------------------------------------
# test_cache_key_includes_network / _code_version -- drop a key component
# --------------------------------------------------------------------------


def test_the_network_key_gate_catches_a_dropped_network():
	"""``test_cache_key_includes_network`` must fail when the network leaves the key.

	Dropping ``network`` from the canonical payload is the specification's
	defect: two engines on different networks then collide on one cache entry and
	serve each other's results, and each number is internally consistent and
	answers a question about a different network.
	"""
	_fresh_cache_and_service()
	assert cache_module.cache_key(_params(), NETWORK_A, CODE) != cache_module.cache_key(
		_params(), NETWORK_B, CODE
	), "the network-key gate already fails on clean source"

	# The mutation replaces the *value* rather than deleting the line: the
	# payload is assembled as text, so a deleted line leaves `"network":,` and
	# the canary would be hashing malformed JSON rather than a key that omits
	# the network. A constant value is the same defect with a readable payload.
	target = '\t\t+ json.dumps(network_checksum, separators=(",", ":"))\n'
	assert target in CACHE_PY.read_text(), "canary target not found: the network line moved"

	with planted(CACHE_PY, target, '\t\t+ json.dumps("", separators=(",", ":"))\n'):
		importlib.reload(cache_module)
		assert cache_module.cache_key(_params(), NETWORK_A, CODE) == cache_module.cache_key(
			_params(), NETWORK_B, CODE
		), "the network-dropped key still distinguished two networks"

	_fresh_cache_and_service()
	assert cache_module.cache_key(_params(), NETWORK_A, CODE) != cache_module.cache_key(
		_params(), NETWORK_B, CODE
	), "the restore was not proven"


def test_the_code_version_key_gate_catches_a_dropped_version():
	"""``test_cache_key_includes_code_version`` must fail when the code leaves the key.

	Without the version, a fix ships while the cache keeps serving the old, wrong
	result under an unchanged key -- the failure that makes a scenario engine
	untrustworthy across a deploy.
	"""
	_fresh_cache_and_service()
	assert cache_module.cache_key(_params(), NETWORK_A, "0.1.0") != cache_module.cache_key(
		_params(), NETWORK_A, "0.1.1"
	), "the code-version-key gate already fails on clean source"

	target = '\t\t+ json.dumps(code_version, separators=(",", ":"))\n'
	assert target in CACHE_PY.read_text(), "canary target not found: the code line moved"

	with planted(CACHE_PY, target, '\t\t+ json.dumps("", separators=(",", ":"))\n'):
		importlib.reload(cache_module)
		assert cache_module.cache_key(_params(), NETWORK_A, "0.1.0") == cache_module.cache_key(
			_params(), NETWORK_A, "0.1.1"
		), "the version-dropped key still distinguished two code versions"

	_fresh_cache_and_service()
	assert cache_module.cache_key(_params(), NETWORK_A, "0.1.0") != cache_module.cache_key(
		_params(), NETWORK_A, "0.1.1"
	), "the restore was not proven"


# --------------------------------------------------------------------------
# test_apply_does_not_mutate_base -- apply in place; the base must change
# --------------------------------------------------------------------------

_MUTATING_PARAMS = ScenarioParameters(
	carbon_price_usd_per_tco2=200.0,
	renewable_multiplier=3.0,
	coal_eaf=0.5,
)


def _base_is_untouched() -> bool:
	"""Whether ``apply_parameters`` leaves the base network alone.

	Mirrors the gate: the returned scenario must be a different network, the
	base's tables must be byte-identical, and the base's ``meta`` must not carry
	the scenario snapshot the layer records on the copy.
	"""
	base = _network()
	before = base.generators.copy(deep=True)
	try:
		apply_module.apply_parameters(base, _MUTATING_PARAMS)
	except AssertionError:
		# The engine's own immutability assertion fired. That is the gate failing.
		return False
	if "alea_whatif_base" in base.meta:
		return False
	return base.generators.equals(before)


def test_the_immutability_gate_catches_an_in_place_apply():
	"""``test_apply_does_not_mutate_base`` must fail when the base is mutated.

	The gate asserts ``base`` is byte-identical after apply. Applying to the base
	itself -- dropping the ``.copy()`` -- scales the base's own tables in place
	and stamps the scenario snapshot onto its ``meta``, which is the defect the
	whole snapshot mechanism exists to prevent: a second scenario would then be
	measured against the first scenario's output.
	"""
	importlib.reload(apply_module)
	assert _base_is_untouched(), "the immutability gate already fails on clean source"

	target = "\tnetwork = _detach_solver_model(base).copy()"
	assert target in APPLY_PY.read_text(), "canary target not found: the base copy moved"

	with planted(APPLY_PY, target, "\tnetwork = _detach_solver_model(base)"):
		importlib.reload(apply_module)
		assert not _base_is_untouched(), (
			"the in-place apply left the base untouched; the canary did not "
			"reproduce the mutation"
		)

	importlib.reload(apply_module)
	assert _base_is_untouched(), "the restore was not proven"


# --------------------------------------------------------------------------
# test_renewable_share_nan_on_zero_gen -- return 0 where None belongs
# --------------------------------------------------------------------------

_ZERO_GEN_PROGRAM = (
	"from alea.whatif.views import renewable_share\n"
	"print('EMPTY', renewable_share({}))\n"
	"print('ZERO', renewable_share({'coal': 0.0}))\n"
	"print('COAL', renewable_share({'coal': 100.0}))\n"
)


def _zero_gen() -> dict[str, str]:
	completed = subprocess.run(
		[sys.executable, "-c", _ZERO_GEN_PROGRAM],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	assert completed.returncode == 0, completed.stderr
	return dict(line.split() for line in completed.stdout.strip().splitlines())


def test_the_zero_generation_gate_catches_a_zero_share():
	"""``test_renewable_share_nan_on_zero_gen`` must fail when zero is returned.

	Zero generation is not zero renewable generation. The specification returns
	``0.0``, which asserts "no renewable generation" for a system that produced
	nothing at all -- a report that reads 0% renewable for an idle network is a
	false claim, not a rounding. The gate asserts ``None``; the defect is the
	``0.0`` return.

	Run in a subprocess, not by reloading ``views`` in-process: ``views`` defines
	the result classes every other what-if module binds, so reloading it here
	would mint a second ``ScenarioResult`` and every later test in this session
	would fail on class identity rather than on the gate.
	"""
	clean = _zero_gen()
	assert clean == {"EMPTY": "None", "ZERO": "None", "COAL": "0.0"}, (
		f"the zero-generation gate already fails on clean source: {clean}"
	)

	target = "\t\treturn None"
	assert target in VIEWS_PY.read_text(), "canary target not found: the empty-system return moved"

	with planted(VIEWS_PY, target, "\t\treturn 0.0"):
		broken = _zero_gen()
	assert broken["EMPTY"] == "0.0" and broken["ZERO"] == "0.0", (
		f"with the defect planted zero generation did not read as a zero share: {broken}"
	)

	restored = _zero_gen()
	assert restored == {"EMPTY": "None", "ZERO": "None", "COAL": "0.0"}, "the restore was not proven"


# --------------------------------------------------------------------------
# test_frontier_deterministic -- an order that is not the input's
# --------------------------------------------------------------------------


def test_the_frontier_determinism_gate_catches_an_input_independent_order(tmp_path: Path):
	"""``test_frontier_deterministic`` must fail when row order is not the input's.

	The gate sweeps the same values through two engines and compares the frames
	column for column. The defect it guards is worker completion order reaching
	the frame. A genuinely nondeterministic defect makes a flaky canary, so the
	order is planted *deterministically* as one that depends on the engine rather
	than on the input -- the same observable, an order that is not a function of
	the values, reproduced without a coin flip.
	"""
	_fresh_cache_and_service()
	importlib.reload(sweep_module)
	values = [0.0, 100.0, 200.0]

	def frames(tmp: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
		one = service_module.WhatIfEngine(
			_solved(), cache_root=tmp / "a", solve_fn=_CountingSolve()
		)
		two = service_module.WhatIfEngine(
			_solved(), cache_root=tmp / "b", solve_fn=_CountingSolve()
		)
		return (
			sweep_module.efficient_frontier(one, "carbon_price_usd_per_tco2", values),
			sweep_module.efficient_frontier(two, "carbon_price_usd_per_tco2", values),
		)

	columns = list(sweep_module.FRONTIER_VALUE_COLUMNS)
	first, second = frames(tmp_path / "clean")
	pd.testing.assert_frame_equal(first[columns], second[columns])

	target = (
		'\tframe = frame.sort_values(["param_value", "total_cost_usd"], kind="stable")'
		".reset_index(drop=True)\n"
	)
	assert target in SWEEP_PY.read_text(), "canary target not found: the frontier sort moved"
	# The planted order rotates the rows by a shift derived from the engine's own
	# cache root -- "a" and "b" give different shifts -- so two engines over the
	# same input produce differently ordered frames. That is the shape of
	# completion order reaching the frame.
	planted_order = (
		target
		+ "\t_shift = ord(engine.cache.root.name) % max(1, len(frame))\n"
		+ "\tframe = pd.concat([frame.iloc[_shift:], frame.iloc[:_shift]]).reset_index(drop=True)\n"
	)
	with planted(SWEEP_PY, target, planted_order):
		importlib.reload(sweep_module)
		broken_first, broken_second = frames(tmp_path / "broken")
		with pytest.raises(AssertionError):
			pd.testing.assert_frame_equal(broken_first[columns], broken_second[columns])

	importlib.reload(sweep_module)
	restored_first, restored_second = frames(tmp_path / "restored")
	pd.testing.assert_frame_equal(restored_first[columns], restored_second[columns])


# --------------------------------------------------------------------------
# test_scenario_records_network -- drop the checksum from the record
# --------------------------------------------------------------------------


def _scenario_payload(tmp: Path) -> dict:
	"""Solve, save, and read back the stored scenario payload."""
	engine = service_module.WhatIfEngine(
		_network(), cache_root=tmp / "cache", solve_fn=_CountingSolve()
	)
	params = ScenarioParameters(carbon_price_usd_per_tco2=80.0)
	result = engine.solve(params)
	path = store_module.save_scenario(
		"carbon-80",
		params,
		result,
		engine.network_checksum,
		engine.code_version,
		root=tmp / "scenarios",
	)
	import json

	return json.loads(path.read_text(encoding="utf-8"))


def test_the_scenario_provenance_gate_catches_a_dropped_network(tmp_path: Path):
	"""``test_scenario_records_network`` must fail when the record loses its network.

	The gate reads the saved artefact and asserts it names the network checksum
	it was computed against. Without that field two engines on different networks
	write incomparable results under the same scenario name and nothing in the
	artefact says so -- a stored scenario that cannot answer which network it
	describes is not reproducible.
	"""
	_fresh_cache_and_service()
	importlib.reload(store_module)
	clean = _scenario_payload(tmp_path / "clean")
	assert "network_checksum" in clean and "code_version" in clean, (
		"the scenario-provenance gate already fails on clean source"
	)

	target = "\t\tnetwork_checksum=network_checksum,\n"
	assert target in STORE_PY.read_text(), "canary target not found: the record field moved"

	with planted(STORE_PY, target, ""):
		importlib.reload(store_module)
		# Dropping the field from the record constructor makes the model refuse
		# the record, which is the gate failing: a scenario without its network is
		# not a scenario. Either a refusal or a record missing the field counts.
		try:
			broken = _scenario_payload(tmp_path / "broken")
		except Exception:
			broken = {}
		assert "network_checksum" not in broken, (
			"the network-dropped record still carried its checksum"
		)

	_fresh_cache_and_service()
	importlib.reload(store_module)
	restored = _scenario_payload(tmp_path / "restored")
	assert "network_checksum" in restored, "the restore was not proven"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
