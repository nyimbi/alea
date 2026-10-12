# SPDX-License-Identifier: MIT
"""Canaries for the serving-projection gates (`tests/ci/test_serving_projection.py`).

The gates that need canaries, and the defect each exists to catch:

* ``test_every_path_the_repository_reads_is_accounted_for`` -- the repository
  reads a path no register names. Planted by adding a read to `repository.py`.
* ``test_the_unwired_set_is_exactly_what_is_recorded`` -- a table declared as
  served with nothing writing it and no reason recorded, or a wiring claim whose
  stage does not exist. Planted in `PUBLISHED_TABLES` and in `PROJECTION_STAGES`.
* ``test_every_projected_table_is_read_by_the_repository`` -- a projection writes
  a path no route reads. Planted by adding a table to `PUBLISHED_TABLES`.
* ``test_every_path_produced_elsewhere_names_a_registered_stage`` -- an
  exemption whose stage no longer exists. Planted by renaming the claimed stage.
* ``test_every_unprojectable_path_is_still_a_gap`` -- a path with no producer
  that the gap register does not name. Planted by adding a read to
  `repository.py` for a path nothing writes and nothing records.
* ``test_the_schema_columns_match_what_the_repository_reads`` -- the repository
  reads a column the serving schema does not declare. Planted by removing a
  column from a schema.

**The gate runs as the real gate.** Each canary shells out to
``pytest tests/ci/test_serving_projection.py -k <name>`` in a fresh interpreter.
An inline probe that re-derived the path sets would assert the canary's own
reading and say nothing about whether the gate notices -- and the gate is the
artefact the register counts.

The first two are the ones that matter. They are the two directions of the same
crossing, and a gate that only checked one would pass on a tree where every
projection wrote to a path no route reads -- which is a stage that runs for
nobody, indistinguishable from a working one by the projection's own tests.
"""

from __future__ import annotations

import subprocess
import sys

from tests.ci.canaries import REPO, planted

REPOSITORY_PY = REPO / "src" / "alea" / "api" / "repository.py"
PUBLISH_VIEWS_PY = REPO / "src" / "alea" / "publish" / "views.py"

GATE_FILE = "tests/ci/test_serving_projection.py"


def _gate_exit_code(test: str) -> int:
	"""Exit code of the named gate, run in a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-m", "pytest", GATE_FILE, "-q", "-x", "-k", test],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def _assert_canary(target, old: str, new: str, test: str, reason: str) -> None:
	"""Plant, watch the gate fail, restore, and prove the restore.

	The target assertion is not incidental. A patch that does not apply leaves the
	file untouched, the gate passes against working code, and the canary reports a
	blind gate -- a false alarm about a gate that was never pointed anywhere.
	"""
	assert old in target.read_text(), (
		f"canary target not found in {target.name}: {old!r}. The gate may already "
		f"be testing a source that has moved, in which case this canary is a no-op."
	)
	assert _gate_exit_code(test) == 0, f"{test} does not pass on the shipped tree"
	with planted(target, old, new):
		assert _gate_exit_code(test) != 0, reason
	assert _gate_exit_code(test) == 0, "the restore was not proven"


# --------------------------------------------------------------------------
# Direction 1: a read path with no producer
# --------------------------------------------------------------------------


def test_the_gate_catches_a_repository_read_with_no_producer():
	"""The shipped defect: the repository reads a path nothing writes.

	All eleven paths were in exactly this state, and the Layer 8 suite passed
	because its fixtures wrote them. The canary plants one more read and asserts
	the gate refuses it -- the same defect, one path smaller.
	"""
	_assert_canary(
		REPOSITORY_PY,
		'\t\tread = self._table("data/processed/market/prices.parquet")\n',
		'\t\tread = self._table("data/processed/market/prices.parquet")\n'
		'\t\t_ = self._table("data/processed/market/nothing_writes_this.parquet")\n',
		"reads_is_accounted_for",
		"the repository was given a read for a path no projection writes and the "
		"gate still passed, so it cannot tell a produced table from a phantom",
	)


# --------------------------------------------------------------------------
# Direction 2: a projection with no reader
# --------------------------------------------------------------------------


def test_the_gate_catches_a_projection_no_route_reads():
	"""The other direction: a table written to a path nothing serves.

	A projection to a path no route reads is a stage that runs for nobody. It
	looks identical to a working projection from that projection's own tests.
	"""
	_assert_canary(
		PUBLISH_VIEWS_PY,
		'\t\t"market_prices": "data/processed/market/prices.parquet",\n',
		'\t\t"market_prices": "data/processed/market/prices.parquet",\n'
		'\t\t"market_nobody_reads": "data/processed/market/nobody_reads.parquet",\n',
		"read_by_the_repository",
		"a projection to a path no repository read names still passed the gate, so "
		"a stage that runs for nobody is invisible",
	)


# --------------------------------------------------------------------------
# The gap register
# --------------------------------------------------------------------------


def test_the_gate_catches_an_unnamed_gap():
	"""A path with no producer that the register does not name.

	`UNPROJECTABLE` is what stops the gap growing silently: an unnamed gap is
	indistinguishable from coverage, so a path that becomes unprojectable must
	fail here rather than join the pile quietly.
	"""
	_assert_canary(
		REPOSITORY_PY,
		'\t\tread = self._table("data/processed/market/prices.parquet")\n',
		'\t\tread = self._table("data/processed/market/prices.parquet")\n'
		'\t\t_ = self._table("data/processed/losses/unnamed_gap.parquet")\n',
		"unprojectable_path_is_still_a_gap",
		"a path with no producer and no entry in the gap register still passed, so "
		"the register cannot notice a gap it does not already know about",
	)


# --------------------------------------------------------------------------
# The wiring register
# --------------------------------------------------------------------------


def test_the_gate_catches_a_table_declared_with_no_producer_and_no_reason():
	"""A table added to the served set with nothing writing it and no reason.

	This is the shipped defect exactly: eleven paths declared in the served set
	with no producer. The register that names them is what makes the gap a
	number in the source; a table that joins the declared set without joining
	the register is a gap nobody counted.
	"""
	_assert_canary(
		PUBLISH_VIEWS_PY,
		'\t\t"market_prices": "data/processed/market/prices.parquet",\n',
		'\t\t"market_prices": "data/processed/market/prices.parquet",\n'
		'\t\t"market_declared_not_wired": "data/processed/market/declared.parquet",\n',
		"unwired_set_is_exactly_what_is_recorded",
		"a table declared as served with no stage and no `UNWIRED` reason still "
		"passed, so the gap can grow without being counted",
	)


def test_the_gate_catches_a_wiring_claim_whose_stage_does_not_exist():
	"""A table recorded as written by a stage that is not registered.

	The claim is what the gate reads instead of inferring production from a name
	match. A claim that outlives its stage is the exemption failure in a
	different register: the table reads as produced by something that is gone.
	"""
	# The entry is *added to* rather than replacing the shipped one, so the
	# planted tree differs from the shipped tree in exactly one way: an
	# unregistered producer. Replacing the dict would also move
	# `resilience_contingency` out of the produced set, and the gate would fail
	# on that instead -- a canary that fails for the right reason and the wrong
	# one at once proves neither.
	_assert_canary(
		PUBLISH_VIEWS_PY,
		'\t\t"resilience_contingency": "resilience_contingency",\n',
		'\t\t"resilience_contingency": "resilience_contingency",\n'
		'\t\t"market_prices": "a_stage_that_was_never_registered",\n',
		"unwired_set_is_exactly_what_is_recorded",
		"a wiring claim naming a stage that is not registered still passed, so a "
		"table can read as produced by a producer that does not exist",
	)


# --------------------------------------------------------------------------
# The exemption register
# --------------------------------------------------------------------------


def test_the_gate_catches_an_exemption_whose_stage_vanished():
	"""A path claimed as produced elsewhere, by a stage that does not exist.

	The exemption is granted so a layer-written artefact is not projected twice.
	It stops being true the moment the stage is renamed or removed, and the
	exemption then hides the very defect it was granted to distinguish.
	"""
	_assert_canary(
		PUBLISH_VIEWS_PY,
		'\t\t"data/processed/topology.parquet": "topology",\n',
		'\t\t"data/processed/topology.parquet": "topology_that_was_renamed",\n',
		"produced_elsewhere_names_a_registered_stage",
		"an exemption naming a stage that is not registered still passed, so a "
		"path with no producer can be exempted by a claim nobody checks",
	)


# --------------------------------------------------------------------------
# The schema contract
# --------------------------------------------------------------------------


def test_the_gate_catches_a_schema_missing_a_column_the_repository_reads():
	"""A column the repository reads and the schema does not declare.

	The table would serve zeros for that column -- a route that looks like it
	works, which is the failure mode this whole package exists to end.
	"""
	_assert_canary(
		PUBLISH_VIEWS_PY,
		'\t\t\tname="payback_years",\n',
		'\t\t\tname="payback_years_renamed",\n',
		"schema_columns_match",
		"a serving schema missing a column the repository reads still passed, so "
		"the two sides can drift while both look correct",
	)


# --------------------------------------------------------------------------
# The declared-field contract
# --------------------------------------------------------------------------


PUBLISH_SERVICE_PY = REPO / "src" / "alea" / "publish" / "service.py"


def test_the_gate_catches_a_renamed_field_read_through_a_getattr_default():
	"""The shipped defect, restored: a getattr whose name no model declares.

	`project_capture_rates` read `capture_price_usd_per_mwh` through a `getattr`
	with a `None` default, and `CaptureCurvePoint` declared no such field. This
	plants the shape of that defect -- a read of a name that exists nowhere as a
	declared field -- and asserts the gate refuses it.
	"""
	_assert_canary(
		PUBLISH_SERVICE_PY,
		'\t\t\t"capture_rate": _nan(point.capture_rate),\n',
		'\t\t\t"capture_rate": _nan(getattr(point, "capture_rate_that_was_renamed", None)),\n',
		"read_fields_that_are_declared",
		"a projection reading a field name no model declares still passed, so a "
		"rename in the model can serve a column of NaN while looking correct",
	)


def test_the_gate_still_accepts_a_getattr_on_a_declared_optional_field():
	"""The gate's jurisdiction: a *name*, not the presence of a ``getattr``.

	A gate that banned `getattr` outright would fail on the three call sites that
	read an optional field and default it -- which is documented behaviour, not a
	defect -- and the pressure that creates is to disable the gate. This canary
	proves the rule is scoped to names: the shipped tree, with its three
	legitimate reads, passes.
	"""
	assert _gate_exit_code("read_fields_that_are_declared") == 0, (
		"the declared-field gate fails on the shipped tree, so it is scoped wider "
		"than the defect it exists to catch"
	)
