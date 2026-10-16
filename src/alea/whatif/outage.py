# SPDX-License-Identifier: MIT
"""Line outages as a what-if scenario dimension.

WHY this is a parameter and not a second engine. An outage is not a quantity
the graph computes; it is a change to the *network's topology* that a scenario
applies, exactly like a carbon price is a change to a marginal cost. The spec
states it as one (`docs/what-if-line-loss.md` §1.1: ``line_active``,
``line_capacity_factor``, ``line_outage_start``/``_end``), and the reason it
belongs here rather than in Layer 4's contingency sweep is that Layer 4 answers
"which branch is worth reinforcing" over a whole year of snapshots, while this
answers "what does the system cost if this line is gone next June" — one
scenario, one solve, one row on the frontier.

WHY the mechanism is ``s_max_pu`` and **not** ``lines.active``. Both spellings
appear in the tree — ``docs/modelling-alg-3.md`` names ``n.lines.active =
False`` as the implementation — and on this stack they are not equivalent.
Probed on pypsa 1.4.0, two snapshots of a four-snapshot window:

* ``lines_t.active = [T, T, F, F]`` optimises ``ok`` and sends **50 MW through
  the line on the snapshots marked inactive**. The component schema declares
  ``active`` as a *static* attribute, so the dynamic table is accepted, stored,
  and never read — a silent no-op, which is the worst of the three possible
  behaviours because the solve returns and the answer looks like an answer.
* ``lines_t.s_max_pu = [1, 1, 0, 0]`` is honoured exactly: the line carries
  0 MW across the window and the load is served by shedding instead.

So the windowed form is stated as a rating, and the static form of a permanent
outage is the same expression with no window. A capacity *factor* is then the
same field again (``0.5`` is a line derated to half), which is why one
mechanism covers all three of the spec's parameters.

WHY the islanding check is a refusal here rather than a solve that fails. With
no injector on an islanded bus, the optimiser returns ``status='warning'
(infeasible)`` — verified on this stack — which the engine's ``_default_solve``
turns into a ``SolveError`` reading "an infeasible or unbounded scenario is a
result about the scenario". That is true and it is useless: the message names
neither the line nor the bus, and an outage that strands load is a *named*
finding, not an anonymous infeasibility among the several ways a scenario can
fail to solve. (The ``ValueError: Empty LHS with non-zero RHS in nodal balance
constraint`` that an earlier draft of this docstring attributed to this path
belongs to the *static* ``lines.active`` mechanism, where the branch leaves the
balance outright. A rating of zero keeps the variable and forces it, so the
failure is infeasibility instead — which is why the mechanism was probed rather
than assumed.) The check runs *before* the solve, because after it the network
carries the optimiser's own model and the bus graph is no longer the thing to
ask.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pypsa

from alea.logging import get_logger

logger = get_logger(__name__)

__all__ = [
	"LineOutage",
	"OutageError",
	"OutageSet",
	"apply_outages",
	"islands_without_generation",
	"outage_mask",
]


class OutageError(ValueError):
	"""An outage the network cannot express, or cannot survive.

	Raised for a line the network does not carry, a window that matches no
	snapshot, and an outage that islands load with no local generation. Each is
	a finding about the scenario, and each is legible where a linopy
	``ValueError`` from an infeasible nodal balance is not.
	"""


@dataclass(frozen=True)
class LineOutage:
	"""One line taken out, or derated, over an optional window.

	``factor`` is the share of the line's rating that remains: ``0.0`` is a
	full outage, ``1.0`` is a line in service, and anything between is the
	spec's ``line_capacity_factor``.

	``1.0`` is *allowed*, and deliberately. It is a stated no-op, which is not
	the silent-no-op class this module refuses elsewhere: a sweep over
	``[1.0, 0.5, 0.0]`` is the frontier ``docs/what-if-line-loss.md`` describes
	— line in, line derated, line out — and the first point is the baseline the
	other two are read against. Refusing it would make that frontier
	unbuildable from one sweep. A *window that matches no snapshot* is refused,
	because that is a no-op the caller did not intend.

	``start``/``end`` are snapshot *labels*, inclusive, matched against the
	network's own index. ``None`` on either side means the outage runs to the
	edge of the horizon, so a permanent outage is ``LineOutage("L1")`` with no
	window and needs no timestamp to state.
	"""

	line: str
	factor: float = 0.0
	"""The share of the line's rating that remains: 0.0 out, 1.0 in service.

	A **fraction**, not a percentage. The spec states
	``line_capacity_factor`` in percent (``docs/what-if-line-loss.md`` §1.1,
	example ``50``); this field is that number divided by 100, so the same
	scenario is ``factor=0.5`` here. The conversion is named because a caller
	carrying the spec's own ``50`` across would be refused by the bound below
	rather than silently derating the line by a factor of fifty — the refusal
	is what makes the unit mismatch loud instead of a wrong answer.
	"""

	start: str | None = None
	end: str | None = None

	def __post_init__(self) -> None:
		if not self.line:
			raise OutageError("an outage must name a line")
		if not 0.0 <= self.factor <= 1.0:
			raise OutageError(
				f"factor={self.factor} is outside [0, 1]; it is the share of the "
				f"line's rating that remains, so 0 is out and 1 is in service. A "
				f"value above 1 is a *reinforcement*, which is a different scenario "
				f"and would be silently clamped by the rating it scales"
			)
		if self.start is not None and self.end is not None and self.start > self.end:
			raise OutageError(
				f"outage window starts at {self.start!r} and ends at {self.end!r}; "
				f"an inverted window matches no snapshot and would apply an outage "
				f"of zero length -- a scenario that runs and changes nothing"
			)

	def canonical(self) -> dict[str, Any]:
		"""The outage as a JSON-safe mapping, for the cache key."""
		return {"line": self.line, "factor": self.factor, "start": self.start, "end": self.end}


@dataclass(frozen=True)
class OutageSet:
	"""A scenario's outages, as one value.

	A tuple rather than a list so the set is hashable and comparable, and
	ordered by ``(line, start, end)`` in :meth:`canonical` so two spellings of
	the same outage set serialise identically. The cache key is a hash of that
	serialisation, so an unordered set would key one scenario under two keys
	depending on the order the caller happened to build it in.
	"""

	outages: tuple[LineOutage, ...] = ()

	def __post_init__(self) -> None:
		lines = [outage.line for outage in self.outages]
		duplicates = sorted({name for name in lines if lines.count(name) > 1})
		if duplicates:
			# Two outages on one line is not a richer scenario, it is an
			# ambiguous one: the second silently overwrites the first, so which
			# window applied would depend on iteration order. The caller wants
			# either one window covering both, or a derate, and both are
			# expressible in one record.
			raise OutageError(
				f"more than one outage on {duplicates}; a second record on the "
				f"same line overwrites the first, so the scenario that ran would "
				f"depend on the order they were listed in"
			)

	def __bool__(self) -> bool:
		return bool(self.outages)

	def __len__(self) -> int:
		return len(self.outages)

	def __iter__(self) -> Iterable[LineOutage]:
		return iter(self.outages)

	def canonical(self) -> list[dict[str, Any]]:
		"""The set as a sorted list of mappings, for the cache key.

		Sorted by the serialised record rather than by ``line`` alone: two
		outages on *different* lines with the same name order are already
		distinct, but sorting on the whole record makes the ordering a function
		of the content, which is the property the key needs.

		This is what the parameter serialises to, and it is *flat* — a bare list,
		not ``{"outages": [...]}``. The nesting is what the dataclass field name
		would produce by default, and it is not cosmetic: ``canonical_json`` is
		hashed into the cache key, so a wrapper key would be one more name that
		has to agree between the writer and any reader of a stored entry.
		"""
		return sorted(
			(outage.canonical() for outage in self.outages),
			key=lambda record: (record["line"], str(record["start"]), str(record["end"])),
		)

	@classmethod
	def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
		"""Teach Pydantic the type, so the field is a value and not a blob.

		Without this the field would be a plain dataclass attribute that Pydantic
		cannot validate or serialise: a scenario restored from a stored payload
		would carry a dict where an ``OutageSet`` belongs, ``canonical_json``
		would fall back to ``default=str`` and hash the ``repr`` of the object —
		including its memory-adjacent field order — and two runs of one scenario
		could key differently.

		Validation accepts the dataclass, a list of records, or a list of
		mappings, because those are the three forms that legitimately arrive: a
		caller building a scenario, a stored payload read back, and a CLI that
		parsed a flag into dicts. Serialisation is the flat sorted list, so the
		key is a function of the content and not of the order the caller listed
		the outages in.
		"""
		from pydantic_core import core_schema

		def _validate(value: Any) -> OutageSet:
			if isinstance(value, OutageSet):
				return value
			if isinstance(value, (list, tuple)):
				records: list[LineOutage] = []
				for item in value:
					if isinstance(item, LineOutage):
						records.append(item)
					elif isinstance(item, dict):
						records.append(LineOutage(**item))
					else:
						raise OutageError(
							f"an outage is a LineOutage or a mapping of its fields, got "
							f"{type(item).__name__}"
						)
				return OutageSet(tuple(records))
			raise OutageError(
				f"an outage set is an OutageSet, or a list of LineOutage/mappings, got "
				f"{type(value).__name__}"
			)

		return core_schema.no_info_plain_validator_function(
			_validate,
			serialization=core_schema.plain_serializer_function_ser_schema(
				lambda value: value.canonical(), when_used="always"
			),
		)

	def summary(self) -> str:
		"""One line for a CLI or a report. Names what was out, and when."""
		if not self.outages:
			return "no line outages"
		parts = []
		for outage in self.outages:
			window = (
				"always"
				if outage.start is None and outage.end is None
				else f"{outage.start or 'start'}..{outage.end or 'end'}"
			)
			verb = "out" if outage.factor == 0.0 else f"at {outage.factor:.0%} rating"
			parts.append(f"{outage.line} {verb} ({window})")
		return "; ".join(parts)


def _iso(value: str) -> str:
	"""A timestamp label with its date/time separator normalised to a space.

	Pandas labels a snapshot ``2030-01-01 02:00:00``; ISO-8601 -- which is what
	a user types, what the CLI's grammar documents, and what ``datetime``
	prints -- writes ``2030-01-01T02:00:00``. Compared as raw strings the two
	never match, and the failure is the worst kind: a *correct* window is
	refused as matching no snapshot, so the feature reads as broken rather than
	as mis-typed. Both sides go through here, so the comparison is on the
	instant and not on the spelling.

	Only the first ``T`` is touched. A label can carry a ``T`` inside a
	timezone or a period name and rewriting every occurrence would corrupt it;
	the date/time boundary is the one that is unambiguous, because a date is
	always the first ten characters.
	"""
	if len(value) > 10 and value[10] == "T":
		return f"{value[:10]} {value[11:]}"
	return value


def outage_mask(network: pypsa.Network, outage: LineOutage) -> np.ndarray:
	"""Which snapshots ``outage`` covers, as a boolean array over the index.

	Window bounds are compared as *strings* against the snapshot labels, which
	is what makes the same record work on a flat ``DatetimeIndex`` and on a
	multi-period ``MultiIndex`` without the caller knowing which they have. Both
	sides are normalised by :func:`_iso` first, so ``2030-06-01T00:00`` and
	``2030-06-01 00:00`` are the same bound — see that function for why the
	normalisation is not optional. The comparison is on the label's own textual
	form, so ``"2030-06-01"`` matches every snapshot on that day and
	``"2030-06-01 00:00:00"`` matches one — an ISO-8601 prefix comparison, which
	is the ordering the labels already carry and not one this function imposes.

	A window that matches nothing raises. It is the silent-no-op class: a
	scenario with a mistyped date would solve identically to the base case, be
	reported as an outage scenario, and plot a frontier point that says the
	line does not matter.
	"""
	snapshots = network.snapshots
	# The timestamp level, whatever the index shape. A multi-period index is
	# (period, timestamp) and an outage is stated in wall-clock time; matching
	# the period level instead would need the caller to know the horizon's
	# internal numbering.
	if snapshots.nlevels > 1:
		raw = [str(value[-1]) for value in snapshots]
	else:
		raw = [str(value) for value in snapshots]
	labels = np.asarray([_iso(value) for value in raw], dtype=object)

	start = None if outage.start is None else _iso(outage.start)
	end = None if outage.end is None else _iso(outage.end)

	mask = np.ones(len(labels), dtype=bool)
	if start is not None:
		mask &= np.array([label >= start for label in labels], dtype=bool)
	if end is not None:
		# Inclusive, because a window stated as a single day should cover that
		# day. A label equal to `end` on the nose is the only case where an
		# exclusive bound would differ, and it is the common one.
		mask &= np.array([label <= end or label.startswith(end) for label in labels], dtype=bool)

	if not mask.any():
		raise OutageError(
			f"the window {outage.start!r}..{outage.end!r} for line {outage.line!r} "
			f"matches none of the network's {len(labels)} snapshots "
			f"(first {raw[0]!r}, last {raw[-1]!r}); an outage that covers no "
			f"snapshot solves identically to the base case and is reported as a "
			f"scenario in which the line does not matter"
		)
	return mask


def apply_outages(network: pypsa.Network, outages: OutageSet | Sequence[LineOutage]) -> pypsa.Network:
	"""Derate or remove the named lines on ``network``, in place.

	Returns the same network for call chaining; the caller passes a scenario
	copy, never the engine's base — the same contract :func:`apply_parameters`
	has, and for the same reason.

	**Idempotent by construction.** Each line's per-snapshot rating is built
	from its *static* ``s_max_pu`` and assigned, never multiplied into the
	current dynamic frame. Multiplying would compound: applying the same outage
	twice would square the factor, and a sweep that re-applied a scenario to a
	network already carrying one would derate the wrong base — the exact defect
	``apply.py``'s snapshot exists to prevent for generators, expressed here as
	an assignment rather than a snapshot because the static column is never
	written by anything in this module.
	"""
	assert isinstance(network, pypsa.Network)
	records = outages.outages if isinstance(outages, OutageSet) else tuple(outages)
	if not records:
		return network

	unknown = sorted({record.line for record in records if record.line not in network.lines.index})
	if unknown:
		raise OutageError(
			f"the network carries no line(s) {unknown}; it has "
			f"{len(network.lines)} ({', '.join(str(n) for n in network.lines.index[:5])}"
			f"{', ...' if len(network.lines) > 5 else ''}). An outage on a line that "
			f"does not exist applies nothing and reads as a scenario in which the "
			f"named line was lost"
		)

	# Built from the static rating, which is the base this module promises to
	# scale. A network whose static column is absent gets the schema default of
	# 1.0, which is what pypsa would have read anyway.
	static = (
		network.lines["s_max_pu"].astype(float)
		if "s_max_pu" in network.lines.columns
		else pd.Series(1.0, index=network.lines.index, dtype=float)
	)

	# One dynamic frame covering every line, so a line with no outage keeps its
	# static value explicitly rather than by absence. Assigning only the
	# outaged columns would leave the frame sparse, and pypsa reads an absent
	# column as the static value — true today, but it makes the frame's meaning
	# depend on which lines a scenario happened to name.
	frame = pd.DataFrame(
		np.repeat(static.to_numpy()[None, :], len(network.snapshots), axis=0),
		index=network.snapshots,
		columns=network.lines.index,
		dtype=float,
	)

	for record in records:
		mask = outage_mask(network, record)
		position = network.lines.index.get_loc(record.line)
		# A full outage is stated as a rating of zero rather than as a removal,
		# which is what the probe showed the optimiser honours per snapshot.
		frame.iloc[mask, position] = static.iloc[position] * record.factor

	network.lines_t.s_max_pu = frame
	logger.info(
		"whatif.outage.applied",
		lines=[record.line for record in records],
		snapshots=int(sum(outage_mask(network, r).sum() for r in records)),
	)
	return network


def islands_without_generation(
	network: pypsa.Network, outages: OutageSet | Sequence[LineOutage]
) -> list[list[str]]:
	"""Bus groups the outage cuts off from any generation at all, carrying load.

	The check that turns an anonymous infeasibility into a named refusal, and
	its jurisdiction is exactly the solver's own condition. With no injector on
	an islanded bus, the optimiser returns ``status='warning' (infeasible)`` —
	verified on this stack — and the engine reports that as a ``SolveError``
	reading "an infeasible or unbounded scenario is a result about the
	scenario". True, and it names neither the line nor the bus. An island that
	*can* be balanced is not this function's business.

	**Load shedding counts as generation, deliberately.** It is a generator with
	a VoLL marginal cost, which is how the spec measures islanding at all
	(``docs/what-if-line-loss.md`` §2.3: "Load shedding is modelled as a
	generator ... so the optimisation naturally minimises unserved energy"). A
	check that excluded it would refuse every island, and an islanded line is
	the case this whole module exists to model — the refusal would forbid the
	measurement and call it a validation.

	Lines the outage removes *entirely* (factor 0, covering every snapshot) are
	dropped from the bus graph. A derated line is not dropped — it still
	connects — and a windowed outage leaves the line in service for the rest of
	the horizon, so neither can island anything.

	Returned as a list of bus-name lists rather than a bool because the finding
	is *which* buses were stranded, and that is what a reader acts on.
	"""
	assert isinstance(network, pypsa.Network)
	records = outages.outages if isinstance(outages, OutageSet) else tuple(outages)
	if not records:
		return []

	import networkx as nx

	removed: set[str] = set()
	for record in records:
		if record.factor == 0.0 and outage_mask(network, record).all():
			removed.add(record.line)

	if not removed:
		return []

	graph = nx.Graph()
	graph.add_nodes_from(str(bus) for bus in network.buses.index)
	for name, row in network.lines.iterrows():
		if str(name) in removed:
			continue
		graph.add_edge(str(row["bus0"]), str(row["bus1"]))

	load_by_bus: dict[str, float] = {}
	if len(network.loads):
		for bus, value in network.loads.groupby("bus")["p_set"].sum().items():
			load_by_bus[str(bus)] = float(value) if pd.notna(value) else 0.0

	# Any injector counts: a generator, a storage unit, or an extendable unit
	# whose capacity is still zero. The last is not pedantry -- an extendable
	# generator with `p_nom=0` has a variable in the balance and therefore a
	# non-empty left-hand side, which is precisely what the solver error is
	# about.
	supply_by_bus: dict[str, float] = {}
	for table, column in (("generators", "p_nom"), ("storage_units", "p_nom")):
		frame = getattr(network, table, None)
		if frame is None or not len(frame):
			continue
		for _, row in frame.iterrows():
			capacity = float(row.get(column, 0.0) or 0.0)
			extendable = bool(row.get("p_nom_extendable", False))
			if capacity > 0.0 or extendable:
				bus = str(row["bus"])
				supply_by_bus[bus] = supply_by_bus.get(bus, 0.0) + 1.0

	stranded: list[list[str]] = []
	for component in nx.connected_components(graph):
		buses = sorted(str(bus) for bus in component)
		demand = sum(load_by_bus.get(bus, 0.0) for bus in buses)
		supply = sum(supply_by_bus.get(bus, 0.0) for bus in buses)
		if demand > 0.0 and supply <= 0.0:
			stranded.append(buses)
	return sorted(stranded)
