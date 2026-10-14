# SPDX-License-Identifier: MIT
"""Canaries for the loss-switching gates (`tests/ci/test_loss_switching.py`).

Four gates in that module carry a claim no other test makes, and each is watched
failing on the defect it exists to catch:

* ``test_an_opened_branch_carries_no_flow_and_charges_no_loss`` -- the phantom
  flow. Stamping B alone while leaving ``branch_susceptance`` intact makes
  ``branch_flows`` compute ``b*(theta_i - theta_j)`` across an open branch, so
  the network is charged for a line that is out. Measured on the two-bus
  fixture: 2000 MW carried and 11,480 MW of loss on the opened branch.
* ``test_a_reference_network_alone_attributes_the_topology`` -- the *second*
  degeneracy. ``measure`` defaulting ``topology_network`` to the reference made
  ``T - R`` zero for every caller who supplied a reference and no topology, so
  the first stage to resolve a loss-optimal network would have published
  ``topology_driven == 0.0`` and looked correct while measuring nothing.
* ``test_the_stage_writes_both_artefacts_from_one_search`` -- the serving table
  is written at the path ``PUBLISHED_TABLES`` declares, under the config's
  processed directory rather than the repository root.
* ``test_the_section_leaves_the_missing_list_and_renders`` -- the projection
  lands the frame where the *reader* looks, which is the period end and not the
  issue date.

**Why the subprocess.** Every mutation here is a source edit, so the gate must
run in a fresh interpreter that reads the mutated file. An ``importlib.reload``
inside this interpreter leaves a stale class object in any sibling test that
imported it first -- the failure mode `tests/ci/canaries/test_predictive_gates.py`
documents at length.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

SWITCHING_PY = REPO / "src" / "alea" / "losses" / "switching.py"
DECOMPOSE_PY = REPO / "src" / "alea" / "losses" / "decompose.py"
LOSSES_SERVICE_PY = REPO / "src" / "alea" / "losses" / "service.py"
ARTEFACTS_PY = REPO / "src" / "alea" / "io" / "artefacts.py"
GATE = "tests/ci/test_loss_switching.py"
GATE_PY = REPO / GATE
ARRAYS_GATE = "tests/ci/test_network_arrays.py"


def _gate_exit_code(*selection: str, gate: str = GATE) -> int:
	"""Exit code of the loss-switching gate, run in a fresh interpreter.

	``selection`` narrows the run to the tests a mutation is supposed to break,
	as bare test names qualified onto :data:`GATE`. A canary that ran the whole
	module would take seconds per mutation and would also report a *different*
	test's failure as evidence, which is how a canary comes to certify a gate it
	never pointed anywhere.

	The name is appended to the file as a node id rather than passed as a second
	positional argument: ``pytest GATE test_name`` reads the bare name as a
	*path*, finds nothing, and exits 4 -- a usage error whose exit code is
	non-zero, so the canary would have read "the gate failed" for a selection
	that never ran. It did exactly that on the first spelling here.
	"""
	node_ids = [f"{gate}::{name}" for name in selection] or [gate]
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", "-q", "-x", *node_ids],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def _assert_target(path, text: str) -> None:
	"""The mutation must apply, or the canary is a no-op that reports a blind gate."""
	assert text in path.read_text(encoding="utf-8"), (
		f"canary target not found in {path.name}: {text!r}. The gate may already "
		f"be reading a source that has moved, in which case this canary proves "
		f"nothing."
	)


# --------------------------------------------------------------------------
# The phantom flow
# --------------------------------------------------------------------------

_ZERO_SUSCEPTANCE = "\tbranch_susceptance[opened] = 0.0\n"
"""The line whose removal reintroduces the phantom."""

_STAMP_ONLY = "\t# branch_susceptance[opened] = 0.0  # canary: stamp-only\n"

PHANTOM_TEST = "test_an_opened_branch_carries_no_flow_and_charges_no_loss"


def test_the_gate_catches_an_opened_branch_that_keeps_its_susceptance():
	"""The shipped defect: B rebuilt, susceptance left intact.

	This is the *first* spelling of `open_branches`, and it is the one the plan's
	own text invites -- "computed with the DC flow the crate already provides"
	reads as a matrix edit. The kernel's ``branch_flows`` reads
	``branch_susceptance``, so the opened line keeps carrying a flow derived from
	the bus angles and the network is charged for a line that is open.

	Measured on the two-bus parallel pair: flows ``[2000.0, 200.0]`` and a loss
	of 11,480.7 MW against a base of 94.9 MW. A search over that kernel would
	rank topologies by a loss the network cannot produce.
	"""
	_assert_target(SWITCHING_PY, _ZERO_SUSCEPTANCE)
	assert _gate_exit_code(PHANTOM_TEST) == 0, f"{GATE} does not pass on the shipped tree"
	with planted(SWITCHING_PY, _ZERO_SUSCEPTANCE, _STAMP_ONLY):
		assert _gate_exit_code(PHANTOM_TEST) != 0, (
			"an opened branch that kept its susceptance still passed the gate, so "
			"a phantom flow on an open line is invisible"
		)
	assert _gate_exit_code(PHANTOM_TEST) == 0, "the restore was not proven"


def test_the_phantom_gate_is_not_vacuous_on_a_clean_tree():
	"""A gate that fails on everything is not a gate either.

	Stated separately so a reader sees the two-sided claim, and so a gate that
	raised on import cannot satisfy the canary above.
	"""
	assert _gate_exit_code(PHANTOM_TEST) == 0, (
		f"{GATE} does not pass on the shipped tree, so the canary above proves "
		f"nothing about the susceptance"
	)


# --------------------------------------------------------------------------
# The unrecorded second default
# --------------------------------------------------------------------------

_TOPOLOGY_DEFAULT = "\ttopology_net = topology_network or network\n"
"""The repaired default."""

_TOPOLOGY_OLD = "\ttopology_net = topology_network or reference_net\n"
"""Its old value, which made ``T - R`` zero for every caller who supplied a
reference and no topology. Recorded nowhere until it was found by probe."""

TOPOLOGY_TEST = "test_a_reference_network_alone_attributes_the_topology"


def test_the_gate_catches_the_topology_default_that_swallows_the_component():
	"""The *second* default, and the one the gate pins rather than the register.

	Two defaults made ``T - R`` zero by construction, and `losses/decompose.py`'s
	docstring named only the first (``reference_network``). The second --
	``topology_network`` defaulting to the *reference* -- was recorded, but in
	`reporting/producers.py`'s deleted ``UNPRODUCED`` entry rather than in the
	code it describes, and it swallows the component even when a caller supplies
	a loss-optimal reference: the degeneracy again, one signature further along.

	What this canary adds is not the finding but the *gate*: the register entry
	is gone with the gap it recorded, so the only thing keeping the repaired
	default repaired is the test below. A gate that passed under both spellings
	would certify a decomposition reading ``load driven == total`` for every
	network.
	"""
	_assert_target(DECOMPOSE_PY, _TOPOLOGY_DEFAULT)
	assert _gate_exit_code(TOPOLOGY_TEST) == 0, f"{GATE} does not pass on the shipped tree"
	with planted(DECOMPOSE_PY, _TOPOLOGY_DEFAULT, _TOPOLOGY_OLD):
		assert _gate_exit_code(TOPOLOGY_TEST) != 0, (
			"`topology_network` defaulting to the reference network still passed "
			"the gate, so the decomposition can publish topology_driven == 0.0 "
			"while appearing to measure it"
		)
	assert _gate_exit_code(TOPOLOGY_TEST) == 0, "the restore was not proven"


# --------------------------------------------------------------------------
# The serving path, and the period
# --------------------------------------------------------------------------

_SERVING_PATH = '\ttarget = table_path("losses_decomposition", processed=config.paths.processed)\n'
"""The stage's serving path, resolved against the config."""

_SERVING_ROOT = '\ttarget = table_path("losses_decomposition")\n'
"""The old spelling: resolved against the repository root, so a run configured
to write elsewhere lands its table in ``data/processed`` -- where its own test
finds it and the API, reading the configured directory, does not."""

STAGE_TEST = "test_the_stage_writes_both_artefacts_from_one_search"


def test_the_gate_catches_a_serving_table_written_outside_the_configured_tree():
	"""The stage must write where *its config* says the API reads.

	`table_path` defaults to the repository root, which is right for a caller
	that has no config and wrong for every stage. Measured while writing this
	unit: the stage passed its own assertions by writing
	``data/processed/losses/decomposition.parquet`` in the repository while the
	test's scratch config named a different processed directory -- the artefact
	it asserted on was not the one its config would serve.
	"""
	_assert_target(LOSSES_SERVICE_PY, _SERVING_PATH)
	assert _gate_exit_code(STAGE_TEST) == 0, f"{GATE} does not pass on the shipped tree"
	with planted(LOSSES_SERVICE_PY, _SERVING_PATH, _SERVING_ROOT):
		assert _gate_exit_code(STAGE_TEST) != 0, (
			"a serving table written to the repository root still passed the gate, "
			"so a run configured elsewhere would serve nothing while its tests "
			"passed"
		)
	assert _gate_exit_code(STAGE_TEST) == 0, "the restore was not proven"


# --------------------------------------------------------------------------
# The period the section is read at
# --------------------------------------------------------------------------

_WEEKLY_PERIOD = "PERIOD_END[ReportCadence.WEEKLY]"
"""The period end the section test hands the reader.

The projection lands the frame at ``period_for(WEEKLY, ISSUE_DATE)[1]`` and the
reader resolves the same date from the same function, so the two agree only
because the test asks for that date. ``period_for`` is what the *reader* calls,
so a test that called it too would assert that the reader agrees with itself.
"""

_MONTHLY_PERIOD = "PERIOD_END[ReportCadence.MONTHLY]"

SECTION_TEST = "test_the_section_leaves_the_missing_list_and_renders"
MONTHLY_TEST = "test_the_monthly_section_reads_the_same_frame"


def test_the_gate_catches_a_section_read_at_the_issue_date():
	"""The wrong date reads exactly like a missing producer.

	This was live while the unit was being written: both section tests passed
	``ISSUE_DATE`` to ``_section_from_spec``, the projection had written
	``2030-01-14``, and the reader looked for ``2030-01-15``. The section came
	back ``None`` with ``no artefact at .../2030-01-15.parquet`` -- a message
	that names the *section* rather than the date, which is why the first reading
	of it was "the projection did not land".

	The mutation is on the gate's own file, and that is the point: the claim
	under test is that the gate would notice if the date it reads at were wrong.
	A canary that mutated the reader instead would be asserting that
	``period_for`` is stable, which is a different and weaker statement.
	"""
	_assert_target(GATE_PY, _WEEKLY_PERIOD)
	assert _gate_exit_code(SECTION_TEST) == 0, f"{GATE} does not pass on the shipped tree"
	with planted(GATE_PY, _WEEKLY_PERIOD, "ISSUE_DATE"):
		assert _gate_exit_code(SECTION_TEST) != 0, (
			"a section test reading at the issue date still passed, so the gate "
			"does not distinguish the period the projection wrote from the date "
			"the report was issued"
		)
	assert _gate_exit_code(SECTION_TEST) == 0, "the restore was not proven"
	# The monthly cadence reads a period that also ends before its issue date,
	# and it is a separate literal because the two do not share one.
	_assert_target(GATE_PY, _MONTHLY_PERIOD)


# --------------------------------------------------------------------------
# The index the artefact layer used to drop
# --------------------------------------------------------------------------

_INDEX_AWARE_WRITE = "\t\tdata.to_parquet(path, index=_index_carries_information(data.index))"
_INDEX_DROPPING_WRITE = "\t\tdata.to_parquet(path, index=False)"

TIMESTAMP_TEST = "test_the_dispatch_keeps_its_timestamps_through_the_artefact_layer"


def test_the_gate_catches_a_parquet_write_that_drops_the_index():
	"""The defect the loss stage hit on the real pipeline, not in a test.

	``_write_payload`` wrote every parquet with ``index=False``, so a
	``DatetimeIndex`` was dropped and a reader got a ``RangeIndex``. The
	checksum still verified and the shape still matched, so nothing failed until
	``@stage("loss_decomposition")`` asked the dispatch what period it covers --
	and then it refused, correctly, on a file the layer had already damaged.

	The gate is in `test_network_arrays.py` because that module owns the
	producer: the dispatch is what the layer is asked to round-trip, and a gate
	written in the loss module would be testing another module's output.
	"""
	_assert_target(ARTEFACTS_PY, _INDEX_AWARE_WRITE)
	assert _gate_exit_code(TIMESTAMP_TEST, gate=ARRAYS_GATE) == 0, (
		f"{ARRAYS_GATE} does not pass on the shipped tree"
	)
	with planted(ARTEFACTS_PY, _INDEX_AWARE_WRITE, _INDEX_DROPPING_WRITE):
		assert _gate_exit_code(TIMESTAMP_TEST, gate=ARRAYS_GATE) != 0, (
			"a parquet written with index=False still passed the gate, so the "
			"dispatch's timestamps can be dropped without anything noticing"
		)
	assert _gate_exit_code(TIMESTAMP_TEST, gate=ARRAYS_GATE) == 0, "the restore was not proven"


if __name__ == "__main__":
	raise SystemExit(
		subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"])
	)
