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
		# Layer-neutral, because seven stages across four layers resolve their
		# network here and only two of them are the loss stages. The message used
		# to name the loss layer's reason -- "an unsolved one has no dispatch to
		# decompose" -- which was true of `tlens` and `critical_lines` and false
		# of the other five: a reader of `alea build capacity_update` was told to
		# go looking for a dispatch artefact that stage never reads.
		raise ArtefactError(
			f"no solved network in {directory}; run `alea solve` first. The stages "
			f"that read a solved network -- the loss kernel's arrays, the market, "
			f"the sector coupling and the report sections built from them -- all "
			f"read one, and none of them can read a network that was never solved"
		)
	return candidates[0]


def _previous_network(directory: Path, current: Path) -> Path | None:
	"""The solved network written before ``current``, or ``None`` if it is the first.

	The same ordering ``_newest_network`` uses, read one place further down. A
	caller that wants "the change since the previous month" has to be handed a
	*second* network, and which one that is cannot be a judgement the caller
	makes from a filename: the names carry a content hash, so the only ordering
	the directory has is the write order.

	``None`` rather than an exception, because one solve in the directory is the
	ordinary state of a fresh clone and a *first* capacity update has nothing to
	difference against. The caller decides whether that is a refusal or an
	omitted column; this function only answers the question it was asked.
	"""
	if not directory.is_dir():
		return None
	candidates = sorted(
		(path for path in directory.glob("*.nc") if path.is_file()),
		key=lambda path: path.stat().st_mtime,
		reverse=True,
	)
	for candidate in candidates:
		if candidate != current:
			return candidate
	return None


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


@stage("capacity_update")
def build_capacity_update(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: installed capacity by carrier, in the monthly report's shape.

	`reporting/producers.py` recorded this section's blocker as "no artefact
	carries the mix as its own dated table": `capacity_mix_table` computed it and
	`solve_scenario` wrote it into the solve's JSON summary, which is a run record
	rather than a report input. This stage is the dated table.

	**Two solves are read, not one.** The section asks for the change since the
	previous month and a single solved network has no previous month in it. So
	the directory is read twice -- newest, and newest-but-one -- and the two are
	differenced by ``capacity_update_rows``. The older one is recorded in the
	provenance as an input, because a change is a function of both networks and a
	reader given only the new one cannot reproduce the delta.

	A directory holding one solve writes the capacity with no ``change`` column at
	all. That is a refusal to invent a zero dressed as a column: the reader reports
	the section's own absence rather than asserting that capacity did not move.
	"""
	import pypsa

	from alea.io.artefacts import read_provenance, sha256_file
	from alea.io.pipeline import skip_if_current
	from alea.planning.service import capacity_update_rows

	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	previous = None if named else _previous_network(network_dir, path)

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	previous_digest = ""
	if previous is not None:
		previous_digest = sha256_file(previous)
		inputs.append(previous_digest)
	existing = skip_if_current(out, inputs, stage_name="capacity_update", logger=context.logger)
	if existing is not None:
		return existing

	frame = capacity_update_rows(
		pypsa.Network(str(path)),
		pypsa.Network(str(previous)) if previous is not None else None,
	)
	provenance = DerivedProvenance(
		source_id="capacity_update",
		inputs=inputs,
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters={
			"network_file": path.name,
			"previous_network_file": previous.name if previous is not None else "",
			"n_carriers": int(len(frame)),
			"has_change": "change" in frame.columns,
		},
		basis=Basis.MODELLED,
		notes=(
			"Installed capacity by carrier from the newest solved network, "
			"differenced against the solve written before it. Existing capacity "
			"where a component is not extendable and the optimiser's chosen "
			"capacity where it is, which is `capacity_mix_table`'s one definition "
			"of installed capacity."
			if previous is not None
			else "Installed capacity by carrier from the newest solved network. No "
			"earlier solve is in the directory, so the change against a previous "
			"month is absent rather than zero -- a zero would assert capacity did "
			"not move, from no evidence."
		),
	)
	write_stage(out, frame, provenance, format="parquet")
	logger.info(
		"planning.stage.capacity_update",
		carriers=int(len(frame)),
		previous=previous.name if previous is not None else "",
		out=str(out),
	)
	return read_provenance(out)


@stage("generation_mix")
def build_generation_mix(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: a solved network's dispatch as the daily mix section's rows.

	`reporting/daily.py`'s ``generation_mix`` reads
	``planning/dispatch/{date}.parquet`` with ``value``/``unit``/``label``
	columns. `alea dispatch` writes exactly that frame -- ``generation_mix_rows``
	-- but only to the ``--out`` its caller names, and it also re-solves dispatch
	on fixed capacity. No rule ran it, so the section had a writer and no
	delivery, which the register recorded as "the gap is the rule, not the
	writer".

	**Why this reads the solve rather than re-dispatching.** A solved network
	already carries its dispatch in ``generators_t.p``, and
	``generation_mix_rows`` reads that table. Re-solving would discard the
	capacity the solve chose, which `solve_dispatch`'s ``freeze`` documents as
	deleting capacity rather than fixing it -- and it would make the report's mix
	a *different* solve from the network the other sections read. So the stage
	converts a network an operator has already solved, the same way
	``@stage("network_arrays")`` does.

	The stamp is the network's first snapshot, not the day the rule ran: the
	daily cadence resolves ``{date}`` from the report's own ``as_of`` and reports
	on the day *before*, so a file stamped with today is read by no report. The
	stamp is written into the frame's own index rather than into the filename --
	the rule declares the directory and the projection resolves the date, which is
	the one place the cadence's arithmetic lives.
	"""
	import pypsa

	from alea.io.artefacts import read_provenance, sha256_file
	from alea.io.pipeline import skip_if_current
	from alea.planning.service import generation_mix_rows

	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="generation_mix", logger=context.logger)
	if existing is not None:
		return existing

	network = pypsa.Network(str(path))
	frame = generation_mix_rows(network)
	if frame.empty:
		raise ArtefactError(
			"generation_mix: the solved network dispatched nothing, so the mix has "
			"no carriers. An empty frame renders as a day in which nothing ran, "
			"which is a claim the solve does not support"
		)
	provenance = DerivedProvenance(
		source_id="generation_mix",
		inputs=inputs,
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters={
			"network_file": path.name,
			"n_carriers": int(len(frame)),
			"stamp": _dispatch_stamp_of(network),
		},
		basis=Basis.MODELLED,
		notes=(
			"Mean dispatched MW per carrier over the solved network's snapshots, "
			"read from its own dispatch table rather than re-solved. A day-ahead "
			"mix is an average power, so the mean is reported and not the sum -- "
			"summing it would print MWh under a column headed MW."
		),
	)
	write_stage(out, frame, provenance, format="parquet")
	logger.info(
		"planning.stage.generation_mix",
		carriers=int(len(frame)),
		network_file=path.name,
		out=str(out),
	)
	return read_provenance(out)


def _dispatch_stamp_of(network: Any) -> str:
	"""The date a dispatch artefact is stamped with, from the network itself."""
	snapshots = network.snapshots
	if len(snapshots) == 0:
		raise ArtefactError("generation_mix: the network has no snapshots, so it has no date")
	first = snapshots[0]
	first = first[0] if isinstance(first, tuple) else first
	return f"{pd.Timestamp(first):%Y-%m-%d}"


def _code_version() -> str:
	from alea import __version__

	return __version__


__all__ = [
	"ARRAYS_ARTEFACT",
	"DISPATCH_ARTEFACT",
	"NETWORK_DIR",
	"ArrayError",
	"arrays_payload",
	"build_capacity_update",
	"build_generation_mix",
	"build_network_arrays",
	"dispatch_matrix",
	"network_arrays",
]
