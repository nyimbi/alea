# SPDX-License-Identifier: MIT
"""A solved network as the arrays the loss kernel takes.

`@stage("tlens")` reads ``network_arrays.json`` and ``dispatch.parquet`` from
``paths.processed`` and **nothing wrote either** -- the register in
`alea.publish.views` records that as the reason two serving tables have no
producer, and `02-data-pipeline.md` §4 names the missing producers a Layer 4
task. This module is that producer.

**The one conversion that matters.** The kernel's ``branch_susceptance`` is in
MW per radian; pypsa's ``Line.x`` is in ohms. They are related by

    b = V^2 / x        (V in kV, x in ohm, b in MW/rad)

and the ``V^2`` is not a scale factor that cancels. It was nearly lost: a
first check ran a fixture with every bus at 132 kV, where a DC solve is
invariant to a uniform scaling of susceptance, so ``1/x`` and ``V^2/x``
produce **identical flows** and the check passed against both. The fixture that
discriminates puts one line at 220 kV and the others at 132 kV, and there the
two answers differ by 59% on the 220 kV line. The derivation: pypsa converts
``x`` to per unit as ``x_pu = x * s_nom / V^2``, the DC susceptance is
``1/x_pu`` in per unit, and a per-unit susceptance times ``s_nom`` is the MW
per radian the kernel wants -- ``s_nom`` cancels and ``V^2/x`` is what is left.

This is the same class of defect as the loss kernel's missing ``1000/3``: a
dimensional constant that a self-consistent test cannot see. The gate is
`tests/ci/test_network_arrays.py`, and its discriminating fixture is the one
above rather than a uniform-voltage one.

**Why arrays and not the network.** AD-2 puts the boundary at the artefact: the
kernel takes arrays and returns arrays, and passing a live ``pypsa.Network``
across it would throw away the reason the kernel is separable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError
from alea.io.pipeline import BuildContext, stage, write_stage
from alea.logging import get_logger, new_run_id
from alea.losses.flow import Network, susceptance_matrix
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)


class ArrayError(ValueError):
	"""A network cannot be expressed as the arrays the kernel takes."""


def _susceptance_mw_per_rad(voltage_kv: Any, reactance_ohm: Any) -> np.ndarray:
	"""``V^2 / x``, per branch, in MW per radian.

	Written as a named function because it is the one place the conversion
	lives. A ``V**2`` inlined at the call site is a constant a later refactor
	can drop without any test noticing -- which is exactly what happened to the
	loss kernel's unit factor.
	"""
	v = np.asarray(voltage_kv, dtype=np.float64)
	x = np.asarray(reactance_ohm, dtype=np.float64)
	if np.any(x == 0.0):
		raise ArrayError(
			"a branch has zero reactance; V^2/x is infinite and the DC solve "
			"cannot place it. A zero-reactance branch is a bus tie, not a line."
		)
	if np.any(v <= 0.0):
		raise ArrayError(f"a branch has non-positive nominal voltage: {v[v <= 0.0]}")
	return v * v / x


def network_arrays(network: pypsa.Network) -> Network:
	"""A solved (or unsolved) pypsa network as the kernel's array bundle.

	Only ``Line`` components are converted. A ``Link`` carries ``x`` in per
	unit, not in ohms, so reading one with the formula above would apply
	``V^2`` to a quantity that is already per unit and inflate its susceptance
	by the square of the voltage -- a silent wrong answer in every loss figure
	downstream. The fleet and topology builders add no links, so the guard is
	here for the first component that does.
	"""
	assert network is not None, "network must not be None"
	if len(network.links) > 0:
		raise ArrayError(
			f"the network has {len(network.links)} Link(s); a Link's reactance is "
			f"per unit, not ohms, so V^2/x does not apply to it. Convert links "
			f"explicitly or model the branch as a Line."
		)
	buses = [str(b) for b in network.buses.index]
	if not buses:
		raise ArrayError("the network has no buses")
	index = {name: position for position, name in enumerate(buses)}

	lines = network.lines
	branch_from = np.asarray([index[str(b)] for b in lines["bus0"]], dtype=np.uint32)
	branch_to = np.asarray([index[str(b)] for b in lines["bus1"]], dtype=np.uint32)

	# Each line's own nominal voltage. `lines.v_nom` is the line's, which pypsa
	# takes from bus0 at build time; falling back to the bus would disagree for
	# a line whose ends are at different voltages, which is the case the
	# discriminating fixture in the gate exercises.
	voltage = (
		lines["v_nom"].to_numpy(dtype=np.float64)
		if "v_nom" in lines.columns
		else network.buses.loc[lines["bus0"], "v_nom"].to_numpy(dtype=np.float64)
	)
	reactance = lines["x"].to_numpy(dtype=np.float64)
	resistance = (
		lines["r"].to_numpy(dtype=np.float64)
		if "r" in lines.columns
		else np.zeros(len(lines), dtype=np.float64)
	)
	rating = (
		lines["s_nom"].to_numpy(dtype=np.float64)
		if "s_nom" in lines.columns
		else np.full(len(lines), np.inf, dtype=np.float64)
	)
	branch_susceptance = _susceptance_mw_per_rad(voltage, reactance)

	bundle = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, len(buses)),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=resistance,
		voltage_kv=voltage,
		ratings_mw=rating,
		branch_names=tuple(str(name) for name in lines.index),
	)
	logger.info(
		"network.arrays",
		buses=bundle.n_buses,
		branches=bundle.n_branches,
		mean_susceptance_mw_per_rad=float(np.mean(branch_susceptance)),
	)
	return bundle


def dispatch_matrix(network: pypsa.Network) -> pd.DataFrame:
	"""Bus net injection per snapshot, as ``[time, bus]`` in MW.

	``buses_t.p`` is pypsa's own net injection: positive where the bus generates
	more than it consumes, negative where it consumes more. That is the vector
	`alea.losses.flow.solve_snapshot` takes, and it is read off the solved
	network rather than re-derived from the generator and load tables -- two
	derivations of one quantity is how they come to disagree.

	The columns are the buses in index order, which is the order
	`network_arrays` numbered them in. The two artefacts are positional
	partners, so a dispatch whose columns were sorted independently would shift
	every injection onto the wrong bus and still have the right shape.
	"""
	assert network is not None, "network must not be None"
	if len(network.buses) == 0:
		raise ArrayError("the network has no buses")
	if network.buses_t.p.empty:
		raise ArrayError(
			"the network has no solved bus injections; run `alea solve` first. An "
			"empty dispatch series is not a dispatch, and a loss decomposition "
			"over one reports zero losses for a network that has not been solved"
		)
	frame = network.buses_t.p.copy()
	frame.columns = [str(b) for b in frame.columns]
	frame.index = pd.DatetimeIndex(frame.index)
	frame.index.name = "timestamp"
	# pypsa returns the buses in its own index order; the arrays artefact
	# numbered them in `network.buses.index` order. Sorting the columns would
	# break that pairing, so the order is asserted rather than assumed.
	expected = [str(b) for b in network.buses.index]
	if list(frame.columns) != expected:
		raise ArrayError(
			"the solved injection columns are not in bus index order; the arrays "
			"artefact numbers its branches against that order, so a reordered "
			"dispatch puts every injection on the wrong bus"
		)
	return frame


def arrays_payload(network: Network) -> dict[str, Any]:
	"""The kernel bundle as the JSON payload ``network_arrays.json`` holds."""
	from alea.losses.service import network_to_payload

	return network_to_payload(network)


#: The default directory a solved network is read from. `solve_scenario` writes
#: ``{network_id}-{horizon}.nc`` here, and `alea.api.repository` reads the same
#: directory for its network routes.
NETWORK_DIR = "results/networks"

#: The names the loss stages read under ``paths.processed``. Declared here, and
#: imported by the stage that consumes them, so the producer and the consumer
#: cannot come to disagree about where the file is -- the same rule
#: `alea.planning.inputs` follows for the demand and profile artefacts.
ARRAYS_ARTEFACT = "network_arrays.json"
DISPATCH_ARTEFACT = "dispatch.parquet"


def _newest_network(directory: Path) -> Path:
	"""The most recently written solved network in ``directory``.

	Newest rather than alphabetically first: the filenames are ``<id>-<horizon>.nc``
	and the id is a content hash, so alphabetical order is order of nothing.
	"""
	candidates = sorted(
		(path for path in directory.glob("*.nc") if path.is_file()),
		key=lambda path: path.stat().st_mtime,
		reverse=True,
	)
	if not candidates:
		raise ArtefactError(
			f"no solved network in {directory}; run `alea solve` first. The loss "
			f"stages read a solved network, and an unsolved one has no dispatch to "
			f"decompose"
		)
	return candidates[0]


@stage("network_arrays")
def build_network_arrays(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: a solved network as the loss kernel's arrays.

	Writes two artefacts: ``network_arrays.json`` at ``out``, and the dispatch
	series beside it. Both are read by `@stage("tlens")`, which names them under
	``paths.processed`` -- so the rule passes ``--out data/processed/network_arrays.json``
	and the dispatch lands at ``data/processed/dispatch.parquet`` from the same
	call. One stage rather than two because the two are positional partners: the
	arrays number the buses and the dispatch's columns are in that order, and a
	reader that fetched one without the other would pair a network with another
	run's dispatch.
	"""
	import pypsa

	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	network = pypsa.Network(str(path))
	bundle = network_arrays(network)
	dispatch = dispatch_matrix(network)

	# The recorded inputs are *the network this stage resolved*, plus whatever
	# the caller declared. The network has to be among them -- it is the artefact
	# the stage actually read -- and the caller cannot always name it, because
	# "the newest solved network in this directory" is a runtime fact rather than
	# a path a rule can write down. So the stage declares it and checks itself
	# through `skip_if_current`, which compares the resolved list against the
	# sidecar. A stage that recorded an input its caller never declared and had
	# no way to check would be stale on every second run: the idempotence check
	# would be dead rather than merely unexercised.
	from alea.io.artefacts import sha256_file
	from alea.io.pipeline import skip_if_current

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="network_arrays", logger=context.logger)
	if existing is not None:
		return existing
	parameters = {
		"n_buses": bundle.n_buses,
		"n_branches": bundle.n_branches,
		"n_snapshots": int(len(dispatch)),
		"network_file": path.name,
		"susceptance_conversion": (
			"b = V^2 / x, MW per radian, per branch's own v_nom. pypsa's x is in "
			"ohms and the kernel's branch_susceptance is in MW/rad; the V^2 does "
			"not cancel. See alea.planning.arrays for the derivation and the "
			"fixture that discriminates it."
		),
	}
	provenance = DerivedProvenance(
		source_id="network_arrays",
		inputs=inputs,
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters=parameters,
		basis=Basis.MODELLED,
		notes=(
			"Solved-network arrays for the loss kernel. The dispatch is pypsa's own "
			"buses_t.p, read rather than re-derived from the generator and load "
			"tables, so the two cannot disagree."
		),
	)
	write_stage(out, arrays_payload(bundle), provenance, format="json")

	# The dispatch, beside the arrays. Its provenance names the same network, so
	# a reader that has one can see the other was written from the same solve.
	dispatch_prov = DerivedProvenance(
		source_id="dispatch",
		inputs=inputs,
		code_version=_code_version(),
		run_id=provenance.run_id,
		parameters={**parameters, "columns": list(dispatch.columns)},
		basis=Basis.MODELLED,
		notes="Bus net injection per snapshot, from the solved network's buses_t.p.",
	)
	write_stage(Path(out).parent / DISPATCH_ARTEFACT, dispatch, dispatch_prov, format="parquet")
	logger.info(
		"stage.network_arrays",
		buses=bundle.n_buses,
		branches=bundle.n_branches,
		snapshots=int(len(dispatch)),
	)
	return provenance


def _code_version() -> str:
	from alea import __version__

	return __version__


__all__ = [
	"ARRAYS_ARTEFACT",
	"DISPATCH_ARTEFACT",
	"NETWORK_DIR",
	"ArrayError",
	"arrays_payload",
	"build_network_arrays",
	"dispatch_matrix",
	"network_arrays",
]
