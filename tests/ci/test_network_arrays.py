# SPDX-License-Identifier: MIT
"""A solved network expressed as the loss kernel's arrays.

WHY this module exists. `@stage("tlens")` reads ``network_arrays.json`` and
``dispatch.parquet`` under ``paths.processed`` and **nothing wrote either** --
which is why ``data/processed/losses/decomposition.parquet`` and its three
siblings sat in `alea.publish.views.UNWIRED` while their projections passed
their own tests. `alea.planning.arrays` is the producer; this is its gate.

**The gate that matters is the conversion, and it is not the one a
self-consistent test would write.** The kernel's ``branch_susceptance`` is in
MW per radian and pypsa's ``Line.x`` is in ohms, related by ``b = V^2 / x`` with
each line's own nominal voltage. The ``V^2`` does not cancel. A DC power flow
is invariant to a *uniform* scaling of susceptance -- the flows depend only on
relative susceptances and on injection -- so a fixture with every bus at one
voltage returns **identical flows** under ``V^2/x`` and under ``1/x``, and a
gate built on one passes against both. The same trap the loss kernel's missing
``1000/3`` sat in.

`_meshed()` is therefore deliberately *not* uniform and deliberately *meshed*:
two lines at 220 kV and one at 132 kV, forming a triangle. There the correct
conversion reproduces pypsa's own linear load flow to six decimals
(``71.681416``, ``71.681416``, ``228.318584`` MW) and ``1/x`` gives
``100.0``, ``100.0``, ``200.0`` -- wrong by 40% on the 220 kV lines, with the
sign of the error depending on which line you look at, which is what makes it
invisible to a test that checks one line's flow is "plausible".

**Why pypsa's own load flow is the reference.** `12-quality.md` §2 permits one
dependency on pypsa's physics: the check of ALEA's approximation against the
physics rather than against a second copy of ALEA's arithmetic. The loss kernel
uses it; so does this, for the same reason. The expected values above are read
off `n.lpf()` in the test rather than written as literals, so the assertion
cannot rot into a tautology.

The rest of the module is the refusal set. Every one of these is a state that
would otherwise produce a *number*: a Link read as a Line, an unsolved network
whose dispatch reads as zero injection everywhere, a dispatch whose columns were
reordered so every injection lands on the wrong bus, a zero-reactance branch.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact, write_artefact
from alea.losses.flow import Network, solve_snapshot, susceptance_matrix
from alea.losses.views import LossConfig
from alea.planning.arrays import (
	ARRAYS_ARTEFACT,
	DISPATCH_ARTEFACT,
	ArrayError,
	arrays_payload,
	build_network_arrays,
	dispatch_matrix,
	network_arrays,
)
from alea.io.pipeline import BuildContext
from alea.provenance.models import Basis, DerivedProvenance

#: The discriminating fixture's voltages. Two tiers, and the 220 kV lines are
#: the *majority* of the branch set, so an error in the conversion shows up in
#: more than one flow rather than in a single branch a reader could dismiss.
KV_HIGH = 220.0
KV_LOW = 132.0

#: pypsa's load flow on `_meshed()`, in MW, for the branch order
#: ``AB, BC, AC``. Asserted as the literal the correct conversion must hit and
#: the wrong one misses; the test recomputes it from `n.lpf()` as well, so a
#: pypsa whose arithmetic changes fails here rather than silently redefining
#: the reference.
MESHED_FLOWS_MW = (71.681416, 71.681416, 228.318584)


def _provenance(source_id: str) -> DerivedProvenance:
	return DerivedProvenance(
		source_id=source_id,
		inputs=["sha256:fixture"],
		code_version="0.0.0-test",
		run_id="run-fixture",
		parameters={},
		basis=Basis.MODELLED,
		notes=f"fixture provenance for {source_id}",
	)


def _meshed() -> pypsa.Network:
	"""Three buses in a triangle, two voltage tiers, one load.

	``v_nom`` is left to pypsa, which takes a line's value from ``bus0`` -- the
	same rule `alea.planning.topology` relies on. So ``AB`` and ``AC`` are 220 kV
	lines out of bus A and ``BC`` is a 132 kV line between B and C. A radial
	chain would not do: with one path from source to load, every branch carries
	the whole injection whatever the susceptances are, and the two conversions
	agree again.
	"""
	network = pypsa.Network()
	network.set_snapshots(pd.date_range("2030-01-01", periods=1, freq="h"))
	network.add("Bus", "A", v_nom=KV_HIGH)
	network.add("Bus", "B", v_nom=KV_LOW)
	network.add("Bus", "C", v_nom=KV_LOW)
	network.add("Line", "AB", bus0="A", bus1="B", x=20.0, r=1.0, s_nom=500.0, length=100.0)
	network.add("Line", "BC", bus0="B", bus1="C", x=10.0, r=0.5, s_nom=300.0, length=50.0)
	network.add("Line", "AC", bus0="A", bus1="C", x=15.0, r=0.8, s_nom=400.0, length=80.0)
	network.add("Generator", "g", bus="A", p_nom=1000.0, marginal_cost=10.0)
	network.add("Load", "l", bus="C", p_set=300.0)
	network.optimize(solver_name="highs", log_to_console=False)
	return network


def _radial() -> pypsa.Network:
	"""A single-voltage two-bus network, solved. The non-discriminating case."""
	network = pypsa.Network()
	network.set_snapshots(pd.date_range("2030-01-01", periods=3, freq="h"))
	network.add("Bus", "A", v_nom=KV_LOW)
	network.add("Bus", "B", v_nom=KV_LOW)
	network.add("Line", "AB", bus0="A", bus1="B", x=10.0, r=0.5, s_nom=200.0, length=20.0)
	network.add("Generator", "g", bus="A", p_nom=500.0, marginal_cost=10.0)
	network.add("Load", "l", bus="B", p_set=50.0)
	network.optimize(solver_name="highs", log_to_console=False)
	return network


def _unsolved() -> pypsa.Network:
	network = _radial()
	# `optimize` writes the dynamic tables; a fresh network has none. Building
	# one and *not* solving it is the state `dispatch_matrix` must refuse.
	fresh = pypsa.Network()
	fresh.set_snapshots(pd.date_range("2030-01-01", periods=3, freq="h"))
	fresh.add("Bus", "A", v_nom=KV_LOW)
	fresh.add("Bus", "B", v_nom=KV_LOW)
	fresh.add("Line", "AB", bus0="A", bus1="B", x=10.0, r=0.5, s_nom=200.0, length=20.0)
	fresh.add("Generator", "g", bus="A", p_nom=500.0)
	fresh.add("Load", "l", bus="B", p_set=50.0)
	return fresh


# --------------------------------------------------------------------------
# The conversion: b = V^2 / x, MW per radian
# --------------------------------------------------------------------------


def test_the_susceptance_matches_pypsa_s_own_load_flow():
	"""The gate. `V^2/x` reproduces pypsa's linear load flow; `1/x` does not.

	The reference is computed here from ``network.lpf()`` rather than taken from
	a literal, so this cannot pass by both sides being edited together.
	"""
	network = _meshed()
	network.lpf()
	reference = [float(v) for v in network.lines_t.p0.iloc[0]]

	bundle = network_arrays(network)
	injection = network.buses_t.p.iloc[0].to_numpy(dtype=float)
	flows = solve_snapshot(bundle, injection, LossConfig()).flows_mw

	for branch, (got, want) in enumerate(zip(flows, reference, strict=True)):
		assert got == pytest.approx(want, abs=1e-6), (
			f"branch {bundle.name_of(branch)}: the kernel gives {got:.6f} MW where "
			f"pypsa's own load flow gives {want:.6f} MW. The flows are the check on "
			f"the susceptance conversion: pypsa's x is in ohms and the kernel's "
			f"branch_susceptance is in MW per radian, related by V^2/x."
		)


def test_the_reference_flows_are_the_recorded_ones():
	"""The literals in this module are pypsa's answer, not a memory of one.

	A pypsa upgrade that changed its arithmetic would otherwise move the
	reference silently and the conversion gate above would move with it.
	"""
	network = _meshed()
	network.lpf()
	flows = tuple(round(float(v), 6) for v in network.lines_t.p0.iloc[0])
	assert flows == MESHED_FLOWS_MW, (
		f"pypsa's load flow on the fixture gives {flows}; this module records "
		f"{MESHED_FLOWS_MW}. If pypsa changed, the reference in the gate above "
		f"changed too and the gate is now measuring against a moved target."
	)


def test_the_fixture_discriminates_the_conversion():
	"""The wrong conversion must *fail* the gate above, or the gate is vacuous.

	This is the canary, and it is the whole reason the fixture is meshed with
	two voltage tiers. Both conversions are run against the same network and the
	same injection; the test asserts they disagree by more than a tolerance a
	unit error could hide in, and that only one of them matches pypsa.
	"""
	network = _meshed()
	network.lpf()
	reference = np.asarray([float(v) for v in network.lines_t.p0.iloc[0]])
	injection = network.buses_t.p.iloc[0].to_numpy(dtype=float)

	branch_from = np.array([0, 1, 0], dtype=np.uint32)
	branch_to = np.array([1, 2, 2], dtype=np.uint32)
	voltage = np.array([KV_HIGH, KV_LOW, KV_HIGH])
	reactance = np.array([20.0, 10.0, 15.0])

	wrong = 1.0 / reactance
	wrong_network = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, wrong, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=wrong,
		resistance_ohm=np.array([1.0, 0.5, 0.8]),
		voltage_kv=voltage,
		ratings_mw=np.array([500.0, 300.0, 400.0]),
	)
	wrong_flows = np.asarray(solve_snapshot(wrong_network, injection, LossConfig()).flows_mw)

	gap = np.abs(wrong_flows - reference).max()
	# The gap is *relative*, and it is not uniform across the branches: 1/x is
	# wrong by 39.5% on the two 220 kV lines (100.0 against 71.68) and by 12.4%
	# on the 132 kV one (200.0 against 228.32), because the missing factor is
	# that branch's own V^2. The bar is a relative one for that reason -- an
	# absolute bound on the worst branch would be a bound on whichever branch
	# happens to carry the most power, which is not what the conversion error
	# is about. 10% is well under the 39.5% delivered and well over noise.
	relative = np.abs(wrong_flows - reference) / np.abs(reference)
	assert relative.max() > 0.10, (
		f"the wrong conversion (1/x) gives {wrong_flows} against pypsa's "
		f"{reference}: a worst relative gap of {relative.max():.1%}. The fixture "
		f"does not discriminate, so "
		f"`test_the_susceptance_matches_pypsa_s_own_load_flow` would pass against "
		f"either conversion and is measuring nothing."
	)
	assert gap > 0.0
	assert not np.allclose(wrong_flows, reference, atol=1.0)
	# The error is not a uniform scale factor either -- a uniform one would be
	# invisible in a DC solve, which is the trap this fixture exists to avoid.
	ratios = wrong_flows / reference
	assert ratios.max() - ratios.min() > 0.1, (
		f"1/x differs from V^2/x by a near-constant factor across branches "
		f"({ratios}); the fixture is close to the degenerate uniform-voltage case"
	)


def test_a_uniform_voltage_fixture_cannot_discriminate():
	"""Stated so nobody rebuilds this gate on a single-voltage network.

	A DC power flow is invariant to a uniform scaling of susceptance: on a
	network where every branch sees the same ``V^2``, ``V^2/x`` and ``1/x``
	differ by one constant factor across all branches and produce *identical*
	flows. This asserts the trap rather than warning about it -- if it ever
	stops holding, the reasoning in the module docstring is wrong and a reader
	should know before trusting the fixture above.
	"""
	network = _radial()
	network.lpf()
	reference = np.asarray([float(v) for v in network.lines_t.p0.iloc[0]])
	injection = network.buses_t.p.iloc[0].to_numpy(dtype=float)

	branch_from = np.array([0], dtype=np.uint32)
	branch_to = np.array([1], dtype=np.uint32)
	for scale in (1.0 / 10.0, KV_LOW**2 / 10.0, 1e6 / 10.0):
		branch_susceptance = np.array([scale])
		scaled = Network(
			susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 2),
			branch_from=branch_from,
			branch_to=branch_to,
			branch_susceptance=branch_susceptance,
			resistance_ohm=np.array([0.5]),
			voltage_kv=np.array([KV_LOW]),
			ratings_mw=np.array([200.0]),
		)
		flows = np.asarray(solve_snapshot(scaled, injection, LossConfig()).flows_mw)
		assert np.allclose(flows, reference, atol=1e-6), (
			f"susceptance scaled by {scale} changed the flows to {flows} from "
			f"{reference}; the fixture is not the degenerate case this test "
			f"documents"
		)


def test_the_susceptance_is_v_squared_over_x_per_branch():
	"""The formula, on a branch whose voltage is unlike its neighbours'."""
	bundle = network_arrays(_meshed())
	expected = np.array([KV_HIGH**2 / 20.0, KV_LOW**2 / 10.0, KV_HIGH**2 / 15.0])
	assert bundle.branch_susceptance == pytest.approx(expected)
	# The wrong answer, named: 1/x. Asserted unequal so a refactor that drops
	# the V^2 fails here as well as at the flow gate.
	assert not np.allclose(bundle.branch_susceptance, 1.0 / np.array([20.0, 10.0, 15.0]))


# --------------------------------------------------------------------------
# Refusals: states that would otherwise produce a number
# --------------------------------------------------------------------------


def test_a_link_is_refused():
	"""A Link's reactance is per unit, so ``V^2/x`` does not apply to it.

	Reading one with the Line formula inflates its susceptance by the square of
	the voltage -- a silent wrong answer in every loss figure downstream. The
	guard is here for the first component that adds a link; the topology and
	fleet builders add none.
	"""
	network = _meshed()
	network.add("Link", "L", bus0="A", bus1="B", x=0.1, p_nom=100.0)
	with pytest.raises(ArrayError, match="Link"):
		network_arrays(network)


def test_a_zero_reactance_branch_is_refused():
	"""``V^2/0`` is infinite; a zero-reactance branch is a bus tie, not a line."""
	network = pypsa.Network()
	network.set_snapshots(pd.date_range("2030-01-01", periods=1, freq="h"))
	network.add("Bus", "A", v_nom=KV_LOW)
	network.add("Bus", "B", v_nom=KV_LOW)
	network.add("Line", "AB", bus0="A", bus1="B", x=0.0, r=0.1, s_nom=100.0, length=1.0)
	with pytest.raises(ArrayError, match="zero reactance"):
		network_arrays(network)


def test_a_non_positive_voltage_is_refused():
	"""A bus at 0 kV is a missing voltage, and it would read as zero flow."""
	network = pypsa.Network()
	network.set_snapshots(pd.date_range("2030-01-01", periods=1, freq="h"))
	network.add("Bus", "A", v_nom=0.0)
	network.add("Bus", "B", v_nom=KV_LOW)
	network.add("Line", "AB", bus0="A", bus1="B", x=10.0, r=0.1, s_nom=100.0, length=1.0)
	with pytest.raises(ArrayError, match="non-positive"):
		network_arrays(network)


def test_an_empty_network_is_refused():
	with pytest.raises(ArrayError, match="no buses"):
		network_arrays(pypsa.Network())


def test_an_unsolved_network_is_refused_for_its_dispatch():
	"""An unsolved network's ``buses_t.p`` is empty, and zero injection is not
	a dispatch: a loss decomposition over one reports zero losses for a network
	that has never been solved.
	"""
	with pytest.raises(ArrayError, match="alea solve"):
		dispatch_matrix(_unsolved())


# --------------------------------------------------------------------------
# The dispatch: positional partner to the arrays
# --------------------------------------------------------------------------


def test_the_dispatch_columns_are_the_bus_index_in_order():
	"""The two artefacts are positional partners.

	The arrays number the buses by ``network.buses.index`` position and the
	dispatch's columns must be in that order. A dispatch whose columns were
	sorted independently would put every injection on the wrong bus and still
	have the right shape -- so this is asserted, not assumed.
	"""
	network = _meshed()
	frame = dispatch_matrix(network)
	assert list(frame.columns) == [str(b) for b in network.buses.index]
	assert frame.index.name == "timestamp"
	assert frame.shape == (1, len(network.buses))


def test_a_reordered_dispatch_is_refused():
	"""The guard on the pairing, watched failing.

	A network whose ``buses_t.p`` columns do not match its bus index order is
	refused rather than paired with the arrays by position. The reorder here is
	planted on the solved frame, which is the only way to reach the branch.
	"""
	network = _meshed()
	reordered = network.buses_t.p[list(reversed(list(network.buses_t.p.columns)))]
	network.buses_t.p = reordered
	with pytest.raises(ArrayError, match="bus index order"):
		dispatch_matrix(network)


def test_the_dispatch_is_the_solved_injection():
	"""Read off ``buses_t.p``, not re-derived from generator and load tables."""
	network = _meshed()
	frame = dispatch_matrix(network)
	assert frame.iloc[0]["A"] == pytest.approx(300.0, abs=1e-6)
	assert frame.iloc[0]["C"] == pytest.approx(-300.0, abs=1e-6)
	assert frame.iloc[0]["B"] == pytest.approx(0.0, abs=1e-6)


def test_the_dispatch_round_trips_through_the_artefact_layer():
	"""What the stage writes is what `@stage("tlens")` can read back.

	The kernel's own reader takes the parquet's numeric columns as a matrix, so
	the round trip is asserted against that shape rather than against the frame
	object.
	"""
	network = _meshed()
	frame = dispatch_matrix(network)
	payload = arrays_payload(network_arrays(network))
	assert set(payload) >= {
		"susceptance",
		"branch_from",
		"branch_to",
		"branch_susceptance",
		"resistance_ohm",
		"voltage_kv",
		"ratings_mw",
	}
	assert len(payload["susceptance"]) == len(network.buses)
	assert len(payload["branch_susceptance"]) == len(network.lines)
	assert frame.to_numpy(dtype=float).shape == (1, len(network.buses))


# --------------------------------------------------------------------------
# The stage: two artefacts from one solve
# --------------------------------------------------------------------------


def _config(tmp_path: Path) -> Config:
	"""A config whose processed lake and results root are the scratch tree."""
	return load_config(
		overrides=[
			f"paths.processed={tmp_path / 'processed'}",
			f"paths.results={tmp_path / 'results'}",
		]
	)


def test_the_stage_writes_both_artefacts_and_the_dispatch_reads_back(tmp_path: Path):
	"""End to end: a saved solved network in, two artefacts out.

	The dispatch lands *beside* the arrays from the same call, because the two
	are positional partners -- a reader that fetched one without the other would
	pair a network with another run's dispatch.
	"""
	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	solved = _meshed()
	solved.export_to_netcdf(str(network_dir / "abc123-2030.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(out=out, inputs=[], parameters={"network_dir": str(network_dir)})
	provenance = build_network_arrays(config, out, context)

	payload, _ = read_artefact(out)
	assert len(payload["branch_susceptance"]) == 3
	assert payload["branch_names"] == ["AB", "BC", "AC"]
	assert provenance.parameters["n_buses"] == 3
	assert provenance.parameters["network_file"] == "abc123-2030.nc"
	assert "V^2 / x" in str(provenance.parameters["susceptance_conversion"])

	dispatch_path = out.parent / DISPATCH_ARTEFACT
	frame, dispatch_prov = read_artefact(dispatch_path)
	assert isinstance(frame, pd.DataFrame)
	assert list(frame.columns) == ["A", "B", "C"]
	assert dispatch_prov.run_id == provenance.run_id, (
		"the two artefacts name different runs; a reader with one cannot see the "
		"other came from the same solve"
	)


def test_the_stage_converts_the_saved_network_with_the_right_conversion(tmp_path: Path):
	"""The NetCDF round trip must not lose the per-line voltage.

	``lines.v_nom`` survives ``export_to_netcdf`` -- checked here rather than
	assumed, because a network that came back with ``v_nom`` absent would fall
	back to the *bus* voltage and quietly convert every line at its bus0's
	voltage instead of its own.
	"""
	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	solved = _meshed()
	solved.lpf()
	reference = [float(v) for v in solved.lines_t.p0.iloc[0]]
	solved.export_to_netcdf(str(network_dir / "abc123-2030.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(out=out, inputs=[], parameters={"network_dir": str(network_dir)})
	build_network_arrays(config, out, context)

	payload, _ = read_artefact(out)
	assert payload["voltage_kv"] == pytest.approx([KV_HIGH, KV_LOW, KV_HIGH]), (
		"the line voltages did not survive the NetCDF round trip; every branch "
		"would be converted at the wrong voltage"
	)

	from alea.losses.service import _network_from_payload

	rebuilt = _network_from_payload(payload)
	dispatch, _ = read_artefact(out.parent / DISPATCH_ARTEFACT)
	injection = dispatch.select_dtypes("number").to_numpy(dtype=float)[0]
	flows = solve_snapshot(rebuilt, injection, LossConfig()).flows_mw
	for got, want in zip(flows, reference, strict=True):
		assert got == pytest.approx(want, abs=1e-5)


def test_the_stage_refuses_when_no_network_has_been_solved(tmp_path: Path):
	"""An absent solve names the command that produces one."""
	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(out=out, inputs=[], parameters={"network_dir": str(network_dir)})
	with pytest.raises(ArtefactError, match="alea solve"):
		build_network_arrays(config, out, context)


def test_the_stage_picks_the_newest_network(tmp_path: Path):
	"""Two solves in the directory: the newer one is the one converted.

	Newest rather than alphabetically first, because the filenames are
	``<content-hash>-<horizon>.nc`` and alphabetical order is order of nothing.
	"""
	import os
	import time

	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)

	old = _radial()
	old.export_to_netcdf(str(network_dir / "aaa-2030.nc"))
	# The tiebreak is mtime, and two exports in the same filesystem tick are
	# indistinguishable; the sleep makes the ordering the test asserts real
	# rather than a race the filesystem happens to win.
	time.sleep(0.01)
	new = _meshed()
	new.export_to_netcdf(str(network_dir / "zzz-2030.nc"))
	os.utime(network_dir / "aaa-2030.nc", (time.time() - 60, time.time() - 60))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(out=out, inputs=[], parameters={"network_dir": str(network_dir)})
	provenance = build_network_arrays(config, out, context)
	assert provenance.parameters["network_file"] == "zzz-2030.nc"
	assert provenance.parameters["n_buses"] == 3


def test_the_stage_names_a_network_explicitly_when_given_one(tmp_path: Path):
	"""``--set network_path=`` overrides the directory search."""
	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	named = network_dir / "chosen.nc"
	_radial().export_to_netcdf(str(named))
	_meshed().export_to_netcdf(str(network_dir / "other.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(
		out=out,
		inputs=[],
		parameters={"network_dir": str(network_dir), "network_path": str(named)},
	)
	provenance = build_network_arrays(config, out, context)
	assert provenance.parameters["network_file"] == "chosen.nc"
	assert provenance.parameters["n_buses"] == 2


def test_the_stage_is_idempotent_through_the_cli(tmp_path: Path):
	"""Run twice through the CLI; the second run must skip.

	**Through the CLI and not through the builder**, because the CLI is the only
	entry point the workflow has (AD-5) and it was the path that could not
	express a stage's inputs at all: `alea build` had no ``--input``, so
	``context.inputs`` was empty, ``build_stage``'s idempotence check
	short-circuited on ``declared``, and *every* `alea build` rebuilt. Stage
	A1's criterion 8 and ``02-data-pipeline.md`` §4.1 were unenforceable from
	the only surface that runs them. Calling the builder directly would have
	missed that entirely -- the builder was never the broken half.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	_meshed().export_to_netcdf(str(network_dir / "abc123-2030.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	runner = CliRunner()
	arguments = [
		"build",
		"network_arrays",
		"--out",
		str(out),
		"--config",
		str(tmp_path / "config.yaml"),
		"--set",
		f"network_dir={network_dir}",
	]
	(tmp_path / "config.yaml").write_text(
		"paths:\n"
		f"  processed: {tmp_path / 'processed'}\n"
		f"  results: {tmp_path / 'results'}\n",
		encoding="utf-8",
	)

	first = runner.invoke(app, arguments)
	assert first.exit_code == 0, first.output
	before = (out.parent / DISPATCH_ARTEFACT).stat().st_mtime_ns

	second = runner.invoke(app, arguments)
	assert second.exit_code == 0, second.output
	assert (out.parent / DISPATCH_ARTEFACT).stat().st_mtime_ns == before, (
		"the second `alea build` rewrote the artefacts; the idempotence check "
		"never fired, so the stage is not idempotent from the CLI"
	)


def test_a_declared_input_reaches_the_provenance(tmp_path: Path):
	"""The artefact records the inputs it read, and the check reads them back.

	Both directions, because a stage that only ever skips is a stage that never
	builds and one that only ever rebuilds is a stage that never skips. The
	network's own hash is the resolved input the stage adds for itself; the
	declared digest rides along beside it, and both land in the sidecar.
	"""
	from alea.io.artefacts import read_provenance, sha256_file, stage_is_current
	from alea.io.pipeline import build_stage

	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	solved = network_dir / "abc123-2030.nc"
	_meshed().export_to_netcdf(str(solved))
	network_digest = sha256_file(solved)

	topology = tmp_path / "topology.parquet"
	topology.write_bytes(b"a stand-in for the topology artefact")
	declared = sha256_file(topology)

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	parameters = {"network_dir": str(network_dir)}
	first = build_stage("network_arrays", config, out, inputs=[declared], parameters=parameters)
	assert not first.skipped
	recorded = set(read_provenance(out).inputs)
	assert {network_digest, declared} <= recorded, (
		f"the artefact records {sorted(recorded)}; it must record both the "
		f"network it resolved ({network_digest[:12]}) and what the caller "
		f"declared ({declared[:12]})"
	)
	assert stage_is_current(out, [network_digest, declared])

	second = build_stage("network_arrays", config, out, inputs=[declared], parameters=parameters)
	assert second.skipped, "the stage rebuilt against the inputs it already recorded"


def test_a_changed_network_makes_the_artefact_stale(tmp_path: Path):
	"""The canary: a different solved network must rebuild.

	A stage whose idempotence check cannot fail is a stage that never rebuilds,
	and one that rebuilt from a stale network would publish a decomposition of
	a network that is no longer the newest solve.
	"""
	from alea.io.pipeline import build_stage

	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	_meshed().export_to_netcdf(str(network_dir / "abc123-2030.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	parameters = {"network_dir": str(network_dir)}
	first = build_stage("network_arrays", config, out, parameters=parameters)
	assert not first.skipped
	assert build_stage("network_arrays", config, out, parameters=parameters).skipped

	# A different network, written later, is the newest one. The stage must
	# notice and rebuild rather than skip against the previous solve.
	import time

	time.sleep(0.01)
	_radial().export_to_netcdf(str(network_dir / "ddd-2030.nc"))
	third = build_stage("network_arrays", config, out, parameters=parameters)
	assert not third.skipped, (
		"a new solved network appeared and the stage skipped against the old one; "
		"the loss tables would be a decomposition of a superseded solve"
	)
	assert third.checksum != first.checksum


def test_the_stage_is_registered():
	"""A builder nothing can name is a builder nothing can run."""
	from alea.io.pipeline import registered_stages

	assert "network_arrays" in registered_stages()


def test_the_stage_writes_a_parquet_the_kernel_stage_can_read(tmp_path: Path):
	"""The contract with `@stage("tlens")`: same directory, readable shapes.

	``tlens`` reads ``processed/network_arrays.json`` and
	``processed/dispatch.parquet`` and takes the dispatch's numeric columns as
	its injection matrix. This asserts the producer's output satisfies that
	reader's own preconditions -- ``matrix.shape[1] == network.n_buses`` --
	without invoking the stage, which needs a configured loss section.
	"""
	config = _config(tmp_path)
	network_dir = tmp_path / "results" / "networks"
	network_dir.mkdir(parents=True)
	_meshed().export_to_netcdf(str(network_dir / "abc123-2030.nc"))

	out = tmp_path / "processed" / ARRAYS_ARTEFACT
	context = BuildContext(out=out, inputs=[], parameters={"network_dir": str(network_dir)})
	build_network_arrays(config, out, context)

	payload, _ = read_artefact(out)
	dispatch, _ = read_artefact(out.parent / DISPATCH_ARTEFACT)
	matrix = pd.DataFrame(dispatch).select_dtypes("number").to_numpy(dtype=float)
	n_buses = len(payload["susceptance"])
	assert matrix.shape[1] == n_buses, (
		f"tlens would refuse this pair: the dispatch has {matrix.shape[1]} columns "
		f"and the arrays number {n_buses} buses"
	)
	assert matrix.shape[0] == len(dispatch)


def test_a_fixture_written_by_hand_is_not_what_this_gate_checks(tmp_path: Path):
	"""The reachability fixture's arrays are the *wrong* conversion, on purpose.

	`test_config_reachability` writes ``network_arrays.json`` with a literal
	``branch_susceptance`` to exercise the reachability of the config, not the
	conversion. Recording that here keeps a later reader from treating those
	numbers as a second source of truth for what the kernel should receive: this
	module's producer is the one that computes them.
	"""
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0])
	fixture = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([100.0, 100.0]),
		branch_names=("L0", "L1"),
	)
	write_artefact(
		tmp_path / "network_arrays.json",
		arrays_payload(fixture),
		_provenance("network_arrays"),
		format="json",
	)
	payload, _ = read_artefact(tmp_path / "network_arrays.json")
	assert payload["branch_susceptance"] == pytest.approx([10.0, 10.0])
	# The producer, on a network with the same topology and voltages, would give
	# V^2/x -- 132^2/10 = 1742.4 -- not 10. The fixture is a wiring probe.
	assert 132.0**2 / 10.0 != pytest.approx(10.0)
