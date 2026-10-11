# SPDX-License-Identifier: MIT
"""Canary: the what-if layer must read PyPSA's *static* columns, not only its dynamic tables.

Three gates in `tests/ci/test_whatif_layer5.py` rest on the same claim: a
quantity may live in a static column (``loads.p_set``, ``generators.p_max_pu``)
or in a dynamic table (``loads_t.p_set``, ``generators_t.p_max_pu``), and the
static form is PyPSA's default. Reading only the dynamic table is not an error
that raises — it is an error that returns the wrong *number*, or that returns
early and does nothing at all.

Three live defects had this shape, each in a different function:

* ``_apply_demand_growth`` returned early on the empty dynamic table, *before*
  the multi-period assertion that exists to refuse the parameter. The silent
  no-op the assertion was written to prevent was reachable through the guard
  that preceded it.
* ``_apply_demand_growth`` then scaled only the dynamic table, so the growth
  reached no load on a network whose demand is static.
* ``_extract_curtailment`` read availability from ``generators_t.p_max_pu``
  only, so every generator carrying a static ``p_max_pu`` reported zero
  curtailment — the docstring's "a network with no potential recorded reports
  zero" applied to networks that had recorded one.

A gate that only ever ran against a fixture with dynamic tables would pass
against all three. So this canary reverts each function to its dynamic-only
form and asserts the corresponding gate notices. It also asserts the fixture
*is* static, because a fixture that grew a dynamic table would make the canary
vacuous while leaving it green.
"""

from __future__ import annotations

import importlib

import pypsa
import pytest

from alea.whatif import ScenarioParameters
from tests.ci.canaries import REPO, planted
from tests.ci.test_whatif_layer5 import SNAPSHOTS, _network, _solved

APPLY_PY = REPO / "src" / "alea" / "whatif" / "apply.py"
EXTRACT_PY = REPO / "src" / "alea" / "whatif" / "extract.py"


def _static_single_period() -> pypsa.Network:
	network = pypsa.Network()
	network.add("Bus", "b1", carrier="AC")
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Generator", "coal", bus="b1", carrier="coal", p_nom=200.0, marginal_cost=30.0)
	network.add("Load", "load", bus="b1", p_set=120.0)
	return network


def test_the_fixture_uses_static_tables():
	"""The canaries below are vacuous unless the fixture is static.

	If a future change gives the fixture a dynamic ``p_set`` or ``p_max_pu``,
	the reverts would no longer reproduce anything and every canary here would
	pass against working code. Asserted first, so that failure is loud.
	"""
	single = _static_single_period()
	assert single.loads_t.p_set.empty, "the fixture gained a dynamic demand table"
	solved = _solved()
	assert solved.generators_t.p_max_pu.empty, "the fixture gained a dynamic availability table"


def test_the_gate_catches_a_dynamic_only_demand_scaling():
	"""Revert ``_apply_demand_growth`` to scale only ``loads_t.p_set``.

	On a static network that is an empty frame, so the load keeps its base
	value and the growth is applied to nothing. The gate asserts the 2040 load
	is 120 * 1.05**10; under the revert it stays 120.
	"""
	target = "\tdemand = _demand_series(network)\n\tnetwork.loads_t.p_set = demand.mul(factors, axis=0)"
	assert target in APPLY_PY.read_text(), "canary target not found: the demand scaling moved"

	import alea.whatif.apply as apply_module

	with planted(
		APPLY_PY,
		target,
		"\tnetwork.loads_t.p_set = network.loads_t.p_set.mul(factors, axis=0)",
	):
		importlib.reload(apply_module)
		base = _network(multi_period=True)
		scenario = apply_module.apply_parameters(base, ScenarioParameters(demand_growth=0.05))
		demand = scenario.loads_t.p_set
		# Either the column is absent (nothing was written) or it did not grow.
		grew = (
			"load" in demand.columns
			and float(demand.loc[demand.index.year == 2040, "load"].iloc[0]) > 120.0
		)
		assert not grew, "the reverted implementation still applied demand growth to a static load"

	importlib.reload(apply_module)
	# Restored: the gate's own assertion holds again.
	restored = apply_module.apply_parameters(
		_network(multi_period=True), ScenarioParameters(demand_growth=0.05)
	)
	assert float(restored.loads_t.p_set["load"].iloc[0]) == pytest.approx(120.0)
	assert float(
		restored.loads_t.p_set.loc[restored.loads_t.p_set.index.year == 2040, "load"].iloc[0]
	) == pytest.approx(120.0 * 1.05**10)


def test_the_gate_catches_the_early_return_that_preceded_the_assertion():
	"""Revert the guard order so the empty check precedes the multi-period check.

	This is the defect that made the assertion unreachable: the parameter is a
	silent no-op on a single-period network because the function returns before
	it can refuse. The gate is ``test_demand_growth_requires_multi_period``,
	which asserts ``ValueError``.
	"""
	source = APPLY_PY.read_text()
	target = "\tif network.loads.empty:\n\t\treturn\n"
	assert target in source, "canary target not found: the guard order moved"

	import alea.whatif.apply as apply_module

	with planted(
		APPLY_PY,
		target,
		"\tif network.loads.empty or network.loads_t.p_set.empty:\n\t\treturn\n",
	):
		importlib.reload(apply_module)
		raised = False
		try:
			apply_module.apply_parameters(
				_static_single_period(), ScenarioParameters(demand_growth=0.05)
			)
		except ValueError:
			raised = True
		assert not raised, (
			"the reverted guard still refused a single-period network; the early "
			"return did not reproduce the silent no-op"
		)

	importlib.reload(apply_module)
	with pytest.raises(ValueError, match="multi-period"):
		apply_module.apply_parameters(
			_static_single_period(), ScenarioParameters(demand_growth=0.05)
		)


def test_the_gate_catches_a_dynamic_only_availability_read():
	"""Revert ``_availability`` to read ``generators_t.p_max_pu`` only.

	Every generator on a static network then has no recorded availability, so
	curtailment is zero. The gate asserts 20 MW built at 0.25 availability over
	four snapshots is 20 MWh curtailed; under the revert it is 0.
	"""
	source = EXTRACT_PY.read_text()
	target = '\tprofile = getattr(dynamic, "p_max_pu", None) if dynamic is not None else None\n\tif profile is not None and not profile.empty:\n\t\treturn profile.astype(float)\n\tstatic = generators["p_max_pu"].astype(float)\n\treturn pd.DataFrame(\n\t\t{name: static[name] for name in generators.index},\n\t\tindex=network.snapshots,\n\t\tdtype=float,\n\t)'
	assert target in source, "canary target not found: the availability helper moved"

	# `import alea.whatif.extract as extract_module` would bind the *function*:
	# the package's `__init__` re-exports `extract` under that name, and the
	# attribute wins over the submodule. The module has to be fetched by name.
	extract_module = importlib.import_module("alea.whatif.extract")

	with planted(
		EXTRACT_PY,
		target,
		"\tprofile = getattr(dynamic, \"p_max_pu\", None) if dynamic is not None else None\n"
		"\treturn profile if profile is not None else pd.DataFrame()",
	):
		importlib.reload(extract_module)
		network = _solved()
		network.generators.loc["solar", "p_nom_opt"] = 20.0
		network.generators.loc["solar", "p_max_pu"] = 0.25
		network.generators_t.p["solar"] = 0.0
		result = extract_module.extract(
			network,
			ScenarioParameters(),
			network_checksum="sha256:" + "ab" * 32,
			code_version="0.1.0",
		)
		assert result.curtailment_mwh == pytest.approx(0.0), (
			"the reverted availability read still found the static column"
		)

	importlib.reload(extract_module)
	restored = extract_module.extract(
		network,
		ScenarioParameters(),
		network_checksum="sha256:" + "ab" * 32,
		code_version="0.1.0",
	)
	assert restored.curtailment_mwh == pytest.approx(20.0)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
