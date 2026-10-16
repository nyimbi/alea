# SPDX-License-Identifier: MIT
"""Canary: the cost-risk frontier's degenerate-axis refusal, and the price model behind it.

Two gates, both about criterion 6 and both about the same failure shape -- an
axis that exists and carries nothing.

**The first is `cost_risk_frontier`'s second refusal.** The function already
refused a *missing* CVaR column. It did not refuse one that is present and
equal to the cost at every point, which is what a network with a flat marginal
price produces: the price model draws its dispersion from the solve's own
hourly prices, so a network that prices every hour the same has no dispersion
to draw from and every point comes back with ``CVaR == total_cost``. That
frontier is the cost-emissions frontier with a risk label, which is precisely
what the function's docstring says it exists to prevent -- arriving by the one
route the NaN check cannot see.

The mutation removes the guard and restores the pre-fix behaviour. It is
*disjoint* from what the predicate reads: it does not touch the NaN branch, the
frame, or any number the test asserts. It deletes the comparison itself.

**The second is the price model's served energy.** A static PyPSA load keeps
its ``p_set`` in ``loads["p_set"]`` and leaves ``loads_t.p_set`` empty, so
summing the static column gives one snapshot's energy on an N-snapshot network.
The risk axis is scaled by that figure, so the error is a unit error of exactly
the kind the loss kernel carried: a number internally consistent with its own
line that answers a different question than the one asked. The mutation sums
the static column without multiplying by the snapshot count -- the pre-fix
behaviour -- and the gate must notice.

Both gates live in code paths rather than value shapes, so both canaries reload
the module that owns the function under test. A canary that patched the file
and then called a name already bound at import would call the *old* code and
pass against a blind gate.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import textwrap

from tests.ci.canaries import REPO, planted, probe

SWEEP_PY = REPO / "src" / "alea" / "whatif" / "sweep.py"
PRICEMODEL_PY = REPO / "src" / "alea" / "whatif" / "pricemodel.py"
API_WHATIF_PY = REPO / "src" / "alea" / "api" / "whatif.py"
API_GATES_PY = REPO / "tests" / "ci" / "test_whatif_layer5.py"

sweep_module = importlib.import_module("alea.whatif.sweep")


#: Sweep a *flat-price* network -- one always-marginal thermal unit -- and
#: report whether the frontier refuses. On this network the price model has no
#: dispersion to draw from, so every point has CVaR equal to its cost.
_FLAT_PROBE = textwrap.dedent(
	"""
	import numpy as np, pandas as pd, pypsa
	from alea.whatif import WhatIfEngine, cost_risk_frontier
	from alea.whatif.pricemodel import price_model_from_network

	def flat_network():
		n = pypsa.Network()
		n.add("Bus", "b1", carrier="AC")
		n.set_snapshots([
			ts for year in (2030, 2040)
			for ts in pd.date_range(f"{year}-01-01", periods=3, freq="h")
		])
		n.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
		n.add("Load", "load", bus="b1", p_set=120.0)
		n.optimize(solver_name="highs", log_to_console=False)
		n.model.solver_model = None
		return n

	# The gate compares with `isclose`, not `==`: a zero-dispersion draw still
	# leaves float noise of order 1e-11 on a cost of order 1e5, so an exact
	# comparison reports "not degenerate" on exactly the frontier the guard
	# exists to refuse. The probe measures what the gate measures.
	def _degenerate(frame):
		risk = frame["conditional_value_at_risk"].to_numpy(dtype=float)
		cost = frame["total_cost_usd"].to_numpy(dtype=float)
		return bool(np.isclose(risk, cost, rtol=1e-9, atol=0.0).all())

	engine = WhatIfEngine(flat_network(), cache_root="/tmp/canary-flat-cache",
						  price_fn=price_model_from_network())
	try:
		frame = cost_risk_frontier(engine, "carbon_price_usd_per_tco2", [0.0, 100.0])
		print("REFUSED", False, "DEGENERATE", _degenerate(frame))
	except ValueError as exc:
		# The refusal is for the *degenerate* axis only when it is not the
		# missing-CVaR message. A probe that reported True for both would pass
		# against a guard that fires on the wrong condition.
		print("REFUSED", "no CVaR" not in str(exc), "DEGENERATE", "unknown")
	"""
)


def _flat() -> tuple[bool, str]:
	"""``(refused, degenerate)`` for a sweep over a flat-price network.

	``degenerate`` is ``"True"``/``"False"`` when the frontier came back and
	``"unknown"`` when it was refused -- the refusal is the whole frame, so
	there is nothing to measure. The two are kept apart deliberately: a probe
	that reported degeneracy from inside the refusal branch would be asserting
	a property of a frame it never saw.
	"""
	completed = probe(_FLAT_PROBE)
	assert completed.returncode == 0, completed.stderr
	lines = [line for line in completed.stdout.splitlines() if line.startswith("REFUSED")]
	assert lines, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	_, refused, _, degenerate = lines[-1].split()
	return refused == "True", degenerate


#: The same sweep through ``efficient_frontier``, which has no risk guard, so
#: the frame the guard would have inspected can be measured directly.
_FLAT_FRAME_PROBE = textwrap.dedent(
	"""
	import numpy as np, pandas as pd, pypsa
	from alea.whatif import WhatIfEngine
	from alea.whatif.pricemodel import price_model_from_network
	from alea.whatif.sweep import efficient_frontier

	n = pypsa.Network()
	n.add("Bus", "b1", carrier="AC")
	n.set_snapshots([
		ts for year in (2030, 2040)
		for ts in pd.date_range(f"{year}-01-01", periods=3, freq="h")
	])
	n.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
	n.add("Load", "load", bus="b1", p_set=120.0)
	n.optimize(solver_name="highs", log_to_console=False)
	n.model.solver_model = None

	engine = WhatIfEngine(n, cache_root="/tmp/canary-flat-frame", price_fn=price_model_from_network())
	frame = efficient_frontier(engine, "carbon_price_usd_per_tco2", [0.0, 100.0])
	risk = frame["conditional_value_at_risk"].to_numpy(dtype=float)
	cost = frame["total_cost_usd"].to_numpy(dtype=float)
	print("FRAME_DEGENERATE", bool(np.isclose(risk, cost, rtol=1e-9, atol=0.0).all()))
	"""
)


def _flat_frame_is_degenerate() -> bool:
	completed = probe(_FLAT_FRAME_PROBE)
	assert completed.returncode == 0, completed.stderr
	lines = [
		line for line in completed.stdout.splitlines() if line.startswith("FRAME_DEGENERATE")
	]
	assert lines, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	return lines[-1].split()[-1] == "True"



def test_the_cost_risk_gate_notices_an_axis_that_is_the_cost_column():
	"""Drop the degenerate-axis refusal and watch the mislabelled frontier through.

	The mutation is the pre-fix body: the NaN check alone, returning the frame
	whatever its risk column contains. Before the mutation the probe's frontier
	is refused for the degenerate axis (not for a missing one -- the probe
	distinguishes the two messages); after it, the frontier comes back with
	CVaR equal to cost at every point, which is the defect.
	"""
	refused, _ = _flat()
	assert refused, "the flat-price sweep was not refused before any mutation"
	# Measured on the frame the guard would have returned, with the guard
	# bypassed -- `efficient_frontier` is the same sweep without the check.
	degenerate = _flat_frame_is_degenerate()
	assert degenerate, (
		"the probe's flat network is not degenerate: its CVaR is not the cost "
		"column, so the guard is refusing for some other reason and the canary "
		"would not be testing the axis check"
	)

	target = """	if all(math.isclose(value, cost_value, rel_tol=1e-9, abs_tol=0.0) for value, cost_value in pairs):
		raise ValueError(
			f"every one of {len(pairs)} points has CVaR equal to its cost, so the "
			f"risk axis carries no information and this is the cost-emissions "
			f"frontier with a risk label. The engine's price model draws its "
			f"dispersion from the solved network's marginal prices, and this "
			f"network prices every hour the same. Use efficient_frontier() for "
			f"the cost-emissions frontier instead."
		)"""
	replacement = "\t# canary: the degenerate-axis refusal is dropped"

	with planted(SWEEP_PY, target, replacement):
		refused_after, degenerate_after = _flat()
		assert degenerate_after == "True", (
			f"under the mutation the frontier came back with degeneracy "
			f"{degenerate_after!r}; the canary is not reaching the code path the "
			f"guard reads"
		)
		assert not refused_after, (
			"with the degenerate-axis guard dropped the mislabelled frontier is "
			"still refused; the gate does not read the axis it claims to check"
		)

	refused, _ = _flat()
	assert refused, "the guard was not restored"


#: Sum the served energy of a network with a static load, two ways.
_ENERGY_PROBE = textwrap.dedent(
	"""
	import pandas as pd, pypsa
	from alea.whatif.pricemodel import _served_energy_mwh

	n = pypsa.Network()
	n.add("Bus", "b1", carrier="AC")
	n.set_snapshots([
		ts for year in (2030, 2040)
		for ts in pd.date_range(f"{year}-01-01", periods=3, freq="h")
	])
	n.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
	n.add("Load", "load", bus="b1", p_set=120.0)
	print("ENERGY", _served_energy_mwh(n), "SNAPSHOTS", len(n.snapshots))
	"""
)


def _energy() -> tuple[float, int]:
	completed = probe(_ENERGY_PROBE)
	assert completed.returncode == 0, completed.stderr
	lines = [line for line in completed.stdout.splitlines() if line.startswith("ENERGY")]
	assert lines, f"the probe printed nothing:\n{completed.stdout}\n{completed.stderr}"
	_, energy, _, snapshots = lines[-1].split()
	return float(energy), int(snapshots)


def test_the_served_energy_gate_notices_a_per_snapshot_sum():
	"""Drop the snapshot multiplier and watch the horizon energy collapse to one hour.

	The mutation returns the static column's sum alone, which is the per-snapshot
	figure. It is disjoint from what the predicate reads: it does not change the
	load, the snapshot count, or the column the probe inspects -- it removes the
	multiplication that turns one of them into a horizon total.
	"""
	energy, snapshots = _energy()
	assert snapshots > 1, "the probe's network has one snapshot; the unit error is unobservable"
	assert energy == 120.0 * snapshots, (
		f"the served energy is {energy} on {snapshots} snapshots, which is not the "
		f"horizon total {120.0 * snapshots} before any mutation"
	)

	target = "\t\t\ttotal += static * snapshots"
	replacement = "\t\t\ttotal += static  # canary: the snapshot multiplier is dropped"

	with planted(PRICEMODEL_PY, target, replacement):
		after, snapshots_after = _energy()
		assert snapshots_after == snapshots, "the mutation changed the snapshot count"
		assert after == 120.0, (
			f"with the snapshot multiplier dropped the served energy is {after}, not "
			f"one snapshot's 120.0; the gate does not read the multiplier"
		)

	energy, snapshots = _energy()
	assert energy == 120.0 * snapshots, "the multiplier was not restored"


def _run_gate(gate: str) -> subprocess.CompletedProcess[str]:
	"""Run one gate by name in a **fresh interpreter**.

	The plant is a source mutation and this session has already imported
	``alea.api.whatif``, so calling the gate in-process would run the module as
	it was at import time -- a canary blind only to its own patch. The child
	reads the mutated source.
	"""
	env = {**os.environ, "PYTHONPATH": str(REPO), "ALEA_OFFLINE": "1"}
	return subprocess.run(
		[
			sys.executable,
			"-m",
			"pytest",
			f"{API_GATES_PY}::{gate}",
			"-q",
			# `--tb=line` and not the default: the canary asserts *how* the gate
			# failed, and a verbose traceback is truncated by pytest's own
			# assertion reporting, so the `DID NOT RAISE` line never reaches the
			# string this test searches.
			"--tb=line",
			"--no-header",
			"-p",
			"no:cacheprovider",
		],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
		env=env,
		timeout=240.0,
	)


def test_the_api_door_notices_a_cost_risk_frontier_it_does_not_check():
	"""Drop the API's call to the shared predicate and watch criterion 6 return mislabelled.

	The API's ``_run_frontier`` and the sweep module's ``cost_risk_frontier``
	are two doors to one artefact, and the guarantee has to hold at both -- a
	guarantee one door enforces and the other routes around is not a guarantee.
	Both now call ``check_cost_risk_axis``, so the mutation deletes the *call*,
	which is the whole difference between the doors.

	It is disjoint from what the predicate reads: it changes no comparison, no
	column and no number. It removes the invocation, which is the only way a
	shared predicate can fail to apply. That is also why it has to be canaried
	separately from the sweep module's: a shared predicate is enforced once per
	call site, and a canary over one call site says nothing about the other.
	"""
	gate = "test_the_api_refuses_a_cost_risk_frontier_with_no_risk_axis"
	before = _run_gate(gate)
	assert before.returncode == 0, (
		f"the API refusal gate does not pass on the shipped code:\n{before.stdout[-3000:]}"
	)

	target = """			check_cost_risk_axis(
				[point["conditional_value_at_risk"] for point in points],
				[float(point["total_cost_usd"]) for point in points],
			)"""
	# The replacement keeps the `if` body non-empty: a bare comment leaves the
	# block with no statement, the module fails to parse, and the gate then
	# fails with an `IndentationError` rather than with a missing refusal --
	# a canary failing for a reason that says nothing about the gate.
	replacement = "\t\t\tpass  # canary: the API door no longer checks the risk axis"

	with planted(API_WHATIF_PY, target, replacement):
		during = _run_gate(gate)
		assert during.returncode != 0, (
			"with the API's axis check dropped the mislabelled cost-risk frontier "
			f"is still refused; the gate does not read the API door:\n{during.stdout[-3000:]}"
		)
		# `DID NOT RAISE` is pytest's own text for a `pytest.raises` block that
		# completed -- which is what the mutation produces, and the only reason
		# this gate may fail. A failure for any other reason (a parse error, an
		# unrelated assertion) says nothing about the API door.
		assert "DID NOT RAISE" in during.stdout, (
			f"the gate failed, but not because the refusal is gone:\n{during.stdout[-3000:]}"
		)

	after = _run_gate(gate)
	assert after.returncode == 0, f"the API's axis check was not restored:\n{after.stdout[-3000:]}"
