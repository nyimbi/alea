# SPDX-License-Identifier: MIT
"""Canaries for the gates the exit-criteria cells name.

These six gates were cited by a cell reading "Integration test" or "Property
test" -- a description, not a name. Naming them in the plan made them visible to
the register, which is what surfaced that none of them had a canary: the rows
had been satisfied by tests nobody had watched fail.

Each mutation is the defect its gate exists to catch, and each is run in a fresh
interpreter because the mutation is a source edit -- this process holds the
mutated module in `sys.modules` and would execute the original.

The three "solves something" gates are the interesting ones. An expansion solve
that returns a result for a network it never solved, a sector coupling that
silently couples nothing, and a report builder that renders no format all
produce a plausible object with no symptom; the gates assert on the *content*,
so the mutations remove the content rather than the call.
"""

from __future__ import annotations

from tests.ci.canaries import REPO, planted, probe_exit_code

KERNELS_PY = REPO / "tests" / "reference" / "losses.py"
AGGREGATION_PY = REPO / "src" / "alea" / "planning" / "aggregation.py"
EXPANSION_PY = REPO / "src" / "alea" / "planning" / "expansion.py"
REGISTRY_PY = REPO / "src" / "alea" / "registry" / "countries.py"
RENDER_PY = REPO / "src" / "alea" / "reporting" / "render.py"
LOADER_PY = REPO / "src" / "alea" / "config" / "loader.py"

GATE_LOSSES = "tests/ci/test_kernels_differential.py::test_decompose_losses_components_sum_to_total"
GATE_WEIGHTS = (
	"tests/ci/test_planning_layer1.py"
	"::test_the_aggregation_weights_are_the_hours_each_period_stands_for"
)
GATE_EXPANSION = "tests/ci/test_planning_layer1.py::test_the_expansion_solve_completes"
GATE_CONTINENTAL = (
	"tests/ci/test_planning_layer1.py::test_the_continental_config_builds_without_solving"
)
GATE_SECTOR = (
	"tests/ci/test_sector_units.py"
	"::test_the_sector_layer_extends_a_layer_one_config_without_replacing_it"
)
GATE_CADENCE = (
	"tests/ci/test_reporting_cadences.py::test_each_cadence_renders_end_to_end_on_fixtures"
)


def _gate(node: str) -> str:
	"""One pytest node, run where it can read the mutated source."""
	return (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)


def _assert_gate_notices(node: str, path, old: str, new: str, why: str) -> None:
	"""The whole canary shape, so six of them do not restate it.

	Assert the gate passes, plant, assert it fails, restore, assert it passes.
	The last step is not ceremony: a gate that reports a defect it cannot clear
	is a gate whose next run is ignored.
	"""
	assert probe_exit_code(_gate(node)) == 0, f"the gate was already failing: {node}"
	with planted(path, old, new):
		assert probe_exit_code(_gate(node)) != 0, why
	assert probe_exit_code(_gate(node)) == 0, f"the gate did not recover: {node}"


def test_the_loss_decomposition_gate_notices_parts_that_do_not_sum():
	"""`test_decompose_losses_components_sum_to_total` must notice a bad part.

	The gate asserts the three parts sum to the total *and* that both
	implementations agree. A shared misreading passes the second; only the sum
	is independent of it. Breaking the reference's generation term by one
	percent leaves the differential comparison satisfied on neither side but
	the sum intact -- so the mutation drops a part outright, which is the defect
	that survives agreement.
	"""
	_assert_gate_notices(
		GATE_LOSSES,
		KERNELS_PY,
		"\tgeneration_driven = float(actual_losses) - load_driven - topology_driven",
		"\tgeneration_driven = 0.0  # canary: a part that is not there",
		"a decomposition whose parts do not sum to its total still passes",
	)


def test_the_aggregation_weight_gate_notices_weights_that_are_not_the_hours():
	"""`test_the_aggregation_weights_are_the_hours_each_period_stands_for` must notice a decoupling.

	The measured defect: weights distributed near-uniformly *independently* of
	the assignment, so the sum still held at 8760 while a period stood in for
	8352 hours carrying a weight of 744 -- every annual total wrong by 10x, with
	the plan's invariant green. The mutation restores exactly that decoupling,
	which the sum-only assertion cannot see.
	"""
	_assert_gate_notices(
		GATE_WEIGHTS,
		AGGREGATION_PY,
		'"weights": weights,',
		'"weights": np.full_like(weights, series.shape[0] / n_periods),',
		"weights decoupled from the assignment still pass the sum invariant",
	)


def test_the_expansion_gate_notices_a_solve_that_reports_nothing():
	"""`test_the_expansion_solve_completes` must notice an objective of zero.

	The gate asserts `objective > 0.0` and a positive duration. An objective of
	zero is what the free-capacity defect produced -- 8 GW of solar built at no
	cost -- and it is the number a caller reads. Zeroing it is the mutation that
	separates "the solver ran" from "the solve meant something".
	"""
	_assert_gate_notices(
		GATE_EXPANSION,
		EXPANSION_PY,
		"\tobjective = float(network.objective)",
		"\tobjective = 0.0  # canary: a solve that reports no cost",
		"an expansion that reports a zero objective still passes",
	)


def test_the_continental_gate_notices_a_truncated_registry():
	"""`test_the_continental_config_builds_without_solving` must notice fewer members.

	The criterion is "builds, not solves", and the thing that can regress
	cheaply is the registry: the gate asserts the code count equals
	`AU_MEMBER_STATE_COUNT` and that the config carries more than forty
	countries. One country moved out of the registry is a continental run that
	models 54 states and reports on Africa.
	"""
	_assert_gate_notices(
		GATE_CONTINENTAL,
		REGISTRY_PY,
		"AU_MEMBER_STATE_COUNT = 55",
		"AU_MEMBER_STATE_COUNT = 54  # canary: a member state dropped",
		"a registry short of the AU membership still passes the continental gate",
	)


def test_the_cadence_gate_notices_a_render_that_produces_no_format():
	"""`test_each_cadence_renders_end_to_end_on_fixtures` must notice empty output.

	The gate asserts `built.paths` is non-empty, the HTML exists and has bytes,
	and the context carries values. A renderer that returns an empty mapping --
	the shape a `formats` bug produces -- satisfies "it returned" and nothing
	else. `assert produced` is the shipped guard; the mutation removes the
	production, not the assertion.
	"""
	_assert_gate_notices(
		GATE_CADENCE,
		RENDER_PY,
		'\t\tproduced["html"] = html_path',
		"\t\tpass  # canary: the HTML is rendered and never recorded",
		"a report that records no format still passes the cadence gate",
	)


def test_the_sector_gate_notices_a_coupling_that_replaces_layer_one():
	"""`test_the_sector_layer_extends_a_layer_one_config_without_replacing_it` must notice a swap.

	§1's rule is that sector coupling is a config layer *over* Layer 1. The gate
	asserts scenario, solve, costs and paths are identical after the sector block
	is enabled, so the defect it exists to catch is a merge that replaces a
	sibling rather than recursing into it -- and `deep_merge` is where that
	happens. A shallow merge is invisible in every count: the sectors are all
	present and the electricity model underneath them is a different one.
	"""
	_assert_gate_notices(
		GATE_SECTOR,
		LOADER_PY,
		"\t\t\tout[key] = deep_merge(existing, value)",
		"\t\t\tout[key] = value  # canary: a shallow merge",
		"a sector config that replaced Layer 1 instead of extending it still passes",
	)
