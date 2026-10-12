# SPDX-License-Identifier: MIT
"""Canaries for `04-layer1-planning.md` §7: watch each Layer 1 gate fail.

The eight gates in §7 assert properties of a *built network* -- one connected
component, no orphan buses, capacity factors in range, a demand total within 2%
of AFREC, an aggregated config carrying its validation, a mix within tolerance,
losses on by default, two solves byte-identical. A network that violates any of
them still solves: it answers a different question than the one asked, and the
defect is visible only in the structure. That is why each needs a canary -- a
gate nobody has watched fail is not evidence that the property holds.

WHY every code-path canary here runs in a **subprocess**: the mutation is to a
module the test session has already imported, so patching the file on disk
changes nothing that runs and the canary would report a blind gate that is only
blind to its own patch. Each child is a fresh interpreter that reads the mutated
source. The child prints its verdict on a ``CANARY``-prefixed line and nothing
else is read back, because the package's own structured logger writes to stdout
and would otherwise be parsed as the verdict.

The one gate that cannot be canaried by a file mutation is
``test_reproducible_solve``: its defect is a *non-deterministic solve*, and an
unseeded solver is unseeded in the library, not in this package. The canary
emulates the defect at runtime -- the objective drifts by a micro-unit per read
-- and watches the gate's own assertion fail on the disagreement. That is the
"plant the bad object" case the canaries' README anticipates.

Restoration is always from the file backup ``planted`` keeps, never with
``git checkout``: the canary's edit and the layer's own uncommitted work live in
the same file.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
import textwrap

import pypsa
import pytest

from tests.ci.canaries import REPO, planted
from tests.ci.test_planning_layer1 import SNAPSHOTS, _network  # noqa: F401 - fixture reuse

TOPOLOGY_PY = REPO / "src" / "alea" / "planning" / "topology.py"
RENEWABLES_PY = REPO / "src" / "alea" / "planning" / "renewables.py"
DEMAND_PY = REPO / "src" / "alea" / "planning" / "demand.py"
AGGREGATION_PY = REPO / "src" / "alea" / "planning" / "aggregation.py"
MODELS_PY = REPO / "src" / "alea" / "config" / "models.py"


def _run(program: str) -> str:
	"""Run a snippet in a fresh interpreter and return its ``CANARY`` verdict.

	``PYTHONPATH`` carries the repo root so the child can import the fixtures in
	``tests.ci`` -- ``tests`` is not part of the installed package. Only the
	``CANARY``-prefixed line is returned: the package's logger writes to stdout,
	so reading the whole stream would fold log lines into the verdict.
	"""
	env = {**os.environ, "PYTHONPATH": str(REPO)}
	completed = subprocess.run(
		[sys.executable, "-c", textwrap.dedent(program)],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
		env=env,
	)
	assert completed.returncode == 0, f"the canary subprocess failed:\n{completed.stderr}"
	marked = [line for line in completed.stdout.splitlines() if line.startswith("CANARY ")]
	assert marked, f"the canary subprocess printed no verdict:\n{completed.stdout}\n{completed.stderr}"
	return marked[-1]


# --------------------------------------------------------------------------
# test_network_connected -- drop a bus from the graph; must fail
# --------------------------------------------------------------------------

# The fixture is a chain 0-1-2-3-4. Dropping the last line isolates bus 4, so
# the component count moves from 1 to 2 -- the exact failure a dropped line
# produces, and one the network still solves with.
_CONNECTED_PROGRAM = """
	from alea.planning.topology import connectivity_report
	from tests.ci.test_planning_layer1 import _network

	report = connectivity_report(_network())
	print("CANARY components", report["n_components"], "buses", report["n_buses"])
	"""


def test_the_connectivity_gate_notices_a_dropped_line():
	"""Plant a dropped line and watch the component count move off one.

	The gate is `test_network_connected`. The mutation is a real defect, not a
	flag: ``build_topology`` omits the last
	line from the network it returns. The gate asserts
	``n_components == 1``; the built network now reports two.

	The drop is inserted at the ``TopologyReport`` construction, after the line
	loop. Anchoring it at ``network.name = ...`` earlier in the function would
	drop from an *empty* table -- the mutation would be a no-op and the canary
	would pass against a defect it never planted.
	"""
	assert _run(_CONNECTED_PROGRAM).startswith("CANARY components 1 "), (
		"the fixture is not one connected component"
	)

	target = "\treport = TopologyReport("
	replacement = (
		"\tif len(network.lines):\n"
		"\t\tnetwork.lines = network.lines.drop(network.lines.index[-1])\n"
		"\treport = TopologyReport("
	)
	with planted(TOPOLOGY_PY, target, replacement):
		cut = _run(_CONNECTED_PROGRAM)
	assert not cut.startswith("CANARY components 1 "), (
		f"the connectivity report still called the cut network connected: {cut!r}"
	)

	# Restored from the backup: the gate's assertion holds again.
	assert _run(_CONNECTED_PROGRAM).startswith("CANARY components 1 ")


# --------------------------------------------------------------------------
# test_no_orphan_buses -- add a bus with nothing attached; must fail
# --------------------------------------------------------------------------


_ORPHAN_PROGRAM = """
	from alea.planning.topology import orphan_buses
	from tests.ci.test_planning_layer1 import _network

	print("CANARY orphans", orphan_buses(_network()))
	"""


def test_the_orphan_gate_notices_a_bus_with_nothing_attached():
	"""Plant an orphan bus and watch the report name it.

	The gate is `test_no_orphan_buses`. ``build_topology`` adds a bus no line and
	no generator references. The gate
	asserts ``orphan_buses(...) == []``; the built network now reports one, which
	is what a snapping artefact looks like downstream.
	"""
	assert _run(_ORPHAN_PROGRAM) == "CANARY orphans []", "the fixture already has an orphan bus"

	target = '\tnetwork.name = "alea-topology"'
	replacement = (
		'\tnetwork.name = "alea-topology"\n\tnetwork.add("Bus", "orphan_canary", carrier="AC")'
	)
	with planted(TOPOLOGY_PY, target, replacement):
		with_orphan = _run(_ORPHAN_PROGRAM)
	assert "orphan_canary" in with_orphan, (
		f"the orphan report did not name the planted bus: {with_orphan!r}"
	)

	assert _run(_ORPHAN_PROGRAM) == "CANARY orphans []"


# --------------------------------------------------------------------------
# test_capacity_factors_in_range -- inject CF=1.2; must fail
# --------------------------------------------------------------------------


_CF_PROGRAM = """
	import pandas as pd

	from alea.planning.renewables import validate_capacity_factors
	from tests.ci.test_planning_layer1 import SNAPSHOTS

	valid = pd.DataFrame({"bus_0": [0.2, 0.4, 0.3], "bus_1": [0.1, 0.15, 0.0]}, index=SNAPSHOTS[:3])
	stats = validate_capacity_factors(valid, carrier="solar")
	gate_passes = 0.0 <= stats.minimum <= stats.maximum <= 1.0
	above = pd.DataFrame({"bus_0": [0.2, 1.2, 0.3]}, index=SNAPSHOTS[:3])
	try:
		validate_capacity_factors(above, carrier="solar")
		print("CANARY gate_passes", gate_passes, "cf_1_2 ACCEPTED")
	except Exception as exc:
		print("CANARY gate_passes", gate_passes, "cf_1_2 REFUSED", type(exc).__name__)
	"""


def test_the_capacity_factor_gate_notices_a_factor_above_one():
	"""Remove the range check and watch a CF of 1.2 be accepted.

	The gate is `test_capacity_factors_in_range`. The plan's canary is "inject
	CF=1.2; must fail". The range comparison is the
	only thing standing between a profile that is already in MW (or a layout
	applied twice) and a generator that produces energy it cannot; with the
	comparison gone the profile validates clean.
	"""
	baseline = _run(_CF_PROGRAM)
	assert "gate_passes True" in baseline, f"the gate does not pass its own fixture: {baseline!r}"
	assert "cf_1_2 REFUSED" in baseline, f"the shipped gate accepted CF=1.2: {baseline!r}"

	target = "\tif lo < CF_MIN - 1e-9 or hi > CF_MAX + 1e-9:"
	with planted(RENEWABLES_PY, target, "\tif False:"):
		blinded = _run(_CF_PROGRAM)
	assert "cf_1_2 ACCEPTED" in blinded, (
		f"with the range check disabled the CF=1.2 profile was still refused: {blinded!r}"
	)

	assert "cf_1_2 REFUSED" in _run(_CF_PROGRAM)


# --------------------------------------------------------------------------
# test_demand_matches_national -- scale demand 0.8x; must fail
# --------------------------------------------------------------------------


_DEMAND_PROGRAM = """
	import numpy as np
	import pandas as pd

	from alea.planning.demand import scale_to_national, validate_national_total

	series = pd.Series(np.full(8760, 150.0), index=pd.date_range("2030-01-01", periods=8760, freq="h"))
	scaled, _ = scale_to_national(series, 10.0, country="KE")
	gate_passes = validate_national_total(scaled, 10.0, country="KE").passes
	missed = validate_national_total(scaled * 0.8, 10.0, country="KE")
	print("CANARY gate_passes", gate_passes, "missed_passes", missed.passes, "error_pct", round(missed.error_pct, 4))
	"""


def test_the_national_total_gate_notices_an_0_8x_scaled_series():
	"""Loosen the tolerance to 30% and watch an 0.8x series pass.

	The gate is `test_demand_matches_national`. The plan's canary is "scale
	demand 0.8x; must fail". The tolerance is the
	whole gate: at 2% the 20% miss is refused, at 30% it is inside the band and a
	series 20% low reports as reconciled with AFREC.

	The widened value is 30, not 20, on purpose. ``scaled * 0.8`` is exactly
	-20%, and ``abs(-20.000000000000004) <= 20.0`` is ``False`` only because of
	the float's last bit -- a tie decided by rounding, not by the tolerance. At
	30 the miss is unambiguously inside the band, so the canary demonstrates the
	tolerance rather than a coincidence of binary arithmetic.
	"""
	baseline = _run(_DEMAND_PROGRAM)
	assert "gate_passes True" in baseline, f"the scaled series did not land: {baseline!r}"
	assert "missed_passes False" in baseline, f"the shipped tolerance hid an 0.8x scale: {baseline!r}"

	target = "NATIONAL_TOLERANCE_PCT = 2.0"
	with planted(DEMAND_PY, target, "NATIONAL_TOLERANCE_PCT = 30.0"):
		blinded = _run(_DEMAND_PROGRAM)
	assert "missed_passes True" in blinded, (
		f"the widened tolerance still refused the 0.8x series: {blinded!r}"
	)

	assert "missed_passes False" in _run(_DEMAND_PROGRAM)


# --------------------------------------------------------------------------
# test_aggregation_requires_validation -- no artefact; must fail
# --------------------------------------------------------------------------

# The defect is the fail-open the gate exists to prevent: absence treated as a
# pass. The fabricated validation carries zero error, so an unmeasured
# aggregation is accepted as a measured-and-fine one.
_AGG_REQUIRED_PROGRAM = """
	import tempfile
	from pathlib import Path

	from alea.planning.aggregation import require_aggregation_validation
	from tests.ci.test_planning_layer1 import _network

	root = Path(tempfile.mkdtemp()) / "aggregation"
	try:
		require_aggregation_validation(_network(), 4, root=root)
		print("CANARY ACCEPTED")
	except Exception as exc:
		print("CANARY REFUSED", type(exc).__name__)
	"""

_AGG_MISSING_ARTEFACT = (
	"\tif validation is None:\n"
	"\t\traise AggregationError(\n"
	'\t\t\tf"time_aggregation={n_periods} selected for network {identifier!r} "\n'
	'\t\t\tf"but no validation artefact exists. Run `alea validate aggregation` "\n'
	'\t\t\tf"first."\n'
	"\t\t)"
)

_AGG_FABRICATE_A_PASS = (
	"\tif validation is None:\n"
	"\t\tvalidation = AggregationValidation(\n"
	"\t\t\tnetwork_id=identifier,\n"
	"\t\t\tn_periods=n_periods,\n"
	"\t\t\tperiod_length=1,\n"
	"\t\t\tn_clusters=1,\n"
	"\t\t\tcost_error_pct=0.0,\n"
	"\t\t\tcapacity_mix_l1_error_pct=0.0,\n"
	"\t\t\temissions_error_pct=0.0,\n"
	"\t\t\tpeak_price_error_pct=0.0,\n"
	"\t\t\tfull_cost=0.0,\n"
	"\t\t\taggregated_cost=0.0,\n"
	"\t\t\tn_snapshots_full=0,\n"
	"\t\t\tn_snapshots_aggregated=0,\n"
	"\t\t)"
)


def test_the_aggregation_gate_notices_a_missing_validation():
	"""Treat absence as a pass and watch the unmeasured aggregation be accepted.

	The gate is `test_aggregation_requires_validation`.
	``require_aggregation_validation`` is "the single most important gate in
	Layer 1": without it a config selecting ``time_aggregation=4`` runs on a
	capacity mix nobody measured. The mutation replaces the refusal with a
	fabricated passing validation, which is the fail-open the gate exists to
	prevent.
	"""
	baseline = _run(_AGG_REQUIRED_PROGRAM)
	assert baseline == "CANARY REFUSED AggregationError", f"the shipped gate did not refuse: {baseline!r}"

	with planted(AGGREGATION_PY, _AGG_MISSING_ARTEFACT, _AGG_FABRICATE_A_PASS):
		blinded = _run(_AGG_REQUIRED_PROGRAM)
	assert blinded == "CANARY ACCEPTED", (
		f"with absence treated as a pass the aggregation was still refused: {blinded!r}"
	)

	assert _run(_AGG_REQUIRED_PROGRAM) == "CANARY REFUSED AggregationError"


# --------------------------------------------------------------------------
# test_aggregation_accuracy -- inject a bad aggregation; must fail
# --------------------------------------------------------------------------


_AGG_ACCURACY_PROGRAM = """
	from alea.planning.aggregation import l1_mix_distance

	full = {"coal": 100.0, "solar": 50.0, "hydro": 50.0}
	degraded = {"coal": 100.0, "solar": 100.0}
	print("CANARY distance", l1_mix_distance(full, degraded))
	"""


def test_the_aggregation_accuracy_gate_notices_a_degraded_mix():
	"""Break the mix normalisation and watch the injected degradation vanish.

	The gate is `test_aggregation_accuracy`. The plan's canary is "inject a bad
	aggregation; must fail". The distance is
	measured on *shares*, so ``mix_shares`` is the channel the tolerance reads;
	with it returning zeros the degraded mix and the full mix are identical and
	a cluster that lost its hydro half reports a 0% mix error.
	"""
	baseline = _run(_AGG_ACCURACY_PROGRAM)
	assert baseline == "CANARY distance 50.0", f"the injected degradation is not measurable: {baseline!r}"
	assert float(baseline.split()[2]) > 5.0, "the degradation is inside the 5% tolerance"

	target = "\treturn {k: v / total for k, v in mix.items()}"
	with planted(AGGREGATION_PY, target, "\treturn {k: 0.0 for k in mix}"):
		blinded = _run(_AGG_ACCURACY_PROGRAM)
	assert blinded == "CANARY distance 0.0", (
		f"with the shares zeroed the degraded mix was still measured: {blinded!r}"
	)

	assert _run(_AGG_ACCURACY_PROGRAM) == "CANARY distance 50.0"


# --------------------------------------------------------------------------
# test_losses_default_on -- flip the default; must fail
# --------------------------------------------------------------------------


_LOSSES_PROGRAM = """
	from alea.config.models import SolveConfig

	print("CANARY transmission_losses", SolveConfig().transmission_losses)
	"""


def test_the_losses_gate_notices_a_flipped_default():
	"""Flip ``transmission_losses`` to ``False`` and watch the default move.

	The gate is `test_losses_default_on`. The plan's canary is "flip default;
	must fail". A model that neglects losses
	understates system cost and overstates how much energy reaches the far end;
	the default has to be the physical one, and the gate reads exactly that bit.
	"""
	baseline = _run(_LOSSES_PROGRAM)
	assert baseline == "CANARY transmission_losses True", f"the shipped default is not True: {baseline!r}"

	target = "\ttransmission_losses: bool = True"
	with planted(MODELS_PY, target, "\ttransmission_losses: bool = False"):
		flipped = _run(_LOSSES_PROGRAM)
	assert flipped == "CANARY transmission_losses False", (
		f"the flipped default did not reach the config: {flipped!r}"
	)

	assert _run(_LOSSES_PROGRAM) == "CANARY transmission_losses True"


# --------------------------------------------------------------------------
# test_reproducible_solve -- unseed the solver; must fail
# --------------------------------------------------------------------------

_REPRODUCIBLE_PROGRAM = """
	import pypsa

	from tests.ci.test_planning_layer1 import SNAPSHOTS

	def solve():
		network = pypsa.Network()
		network.add("Bus", "b1", carrier="AC")
		network.set_snapshots(list(SNAPSHOTS))
		network.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
		network.add(
			"Generator", "solar", bus="b1", carrier="solar", p_nom=20.0, p_nom_max=200.0,
			p_nom_extendable=True, capital_cost=50_000.0,
		)
		network.add("Load", "load", bus="b1", p_set=120.0)
		network.optimize(solver_name="highs", log_to_console=False)
		return float(network.objective or 0.0)

	print("CANARY objectives", solve(), solve())
	"""


def test_the_reproducibility_gate_notices_a_non_deterministic_objective():
	"""Make the objective non-reproducible and watch the gate's equality fail.

	AD-8's defect is not a line in this package -- an unseeded solver is unseeded
	in the library -- so it cannot be planted by a file mutation. The canary
	emulates it instead: the objective property is wrapped to drift by one
	micro-unit per read, and the gate's own ``test_reproducible_solve`` is run
	and must raise on the disagreement between its two solves.

	The shipped gate is exercised first and last, so a pass here is the gate
	passing on real code, not a test that never ran.
	"""
	from tests.ci.test_planning_layer1 import test_reproducible_solve

	# The gate, as shipped: two solves of the same network agree.
	baseline = _run(_REPRODUCIBLE_PROGRAM)
	first, second = (float(value) for value in baseline.split()[2:4])
	assert first == second, f"the fixture solves were already non-deterministic: {baseline!r}"
	test_reproducible_solve()

	original = pypsa.Network.objective
	drift = itertools.count()

	def noisy_objective(self: pypsa.Network) -> float | None:
		value = self._objective
		return None if value is None else float(value) + next(drift) * 1e-6

	pypsa.Network.objective = property(noisy_objective)  # type: ignore[assignment]
	try:
		with pytest.raises(AssertionError, match="disagreed on the objective"):
			test_reproducible_solve()
	finally:
		pypsa.Network.objective = original  # type: ignore[assignment]

	# Restored: the gate's assertion holds again.
	test_reproducible_solve()


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
