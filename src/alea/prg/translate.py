# SPDX-License-Identifier: MIT
"""Translating PRG parameters into the knobs the what-if engine applies.

WHY this module exists at all, and why its main output is a *register*. The
PRG knows 53 parameters it can set; ``ScenarioParameters`` exposes 9 knobs, and
the two sets were built for different purposes. The graph states what the
physics and the accounts require; the engine states what a PyPSA network can be
perturbed by. Where the two name the same quantity the translation is real
arithmetic, and where they do not, a parameter set the graph accepts will be
*silently dropped* by the engine -- which is the failure this module is built
to make countable. So :func:`untranslated` is not a diagnostic bolted on the
side; it is the answer to the question the layer exists to ask.

WHY the mappings are declared and not inferred. Nothing in the graph records
"this parameter is the network's gas price"; the relation is between a PRG
parameter and a PyPSA table column, and only a person can state it. Inferring
it from name similarity would map ``fuel_price_usd_per_mwh`` onto whatever
column shares the most characters, which is a mapping that is right by
accident or wrong by accident and gives no way to tell which.

WHY an absolute parameter maps onto a ratio knob through the base, and never
through a bare number. ``fuel_price_usd_per_mwh`` is USD/MWh; the engine's
``gas_price_multiplier`` is a factor over each gas unit's *base* marginal cost.
Translating the first to the second needs the base, so the function that does
it takes the network and refuses when it has none -- defaulting the ratio to
1.0 would produce a scenario that runs, reports a fuel price, and applies
nothing.

WHY a mapping is checked against the model it names. A ``Translation`` carrying
an engine field that ``ScenarioParameters`` does not have is a mapping that
would raise at use and be read as "the engine cannot do this" rather than "the
name is wrong". :func:`translations` validates every declared field against the
model, so a rename in the engine breaks this loudly at the point of the
declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from alea.whatif.params import ScenarioParameters

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"Translation",
	"TRANSLATIONS",
	"coverage",
	"engine_fields_unreached",
	"from_scenario_parameters",
	"to_scenario_parameters",
	"translated",
	"translations",
	"untranslated",
]


@dataclass(frozen=True)
class Translation:
	"""One PRG parameter's route into the engine, and what it costs."""

	prg_parameter: str
	engine_field: str
	kind: str
	"""``absolute`` when the two name the same quantity in the same unit, and
	``ratio`` when the PRG parameter is an absolute value the engine can only
	apply relative to the network's own base."""

	note: str
	"""What the mapping assumes, stated where the mapping is declared.

	Read by whoever is deciding whether to trust a translated scenario: an
	``absolute`` mapping that is really a stand-in for a fleet, or a ``ratio``
	mapping whose base is one unit's cost, is only as good as the assumption.
	"""


#: The declared routes from a PRG parameter into a ``ScenarioParameters`` knob.
#:
#: Short, and the shortness is the finding. Three of the graph's 53 settable
#: parameters reach the engine; the rest are quantities the PRG states and the
#: PyPSA layer has no column for. Recording that here is what keeps it from
#: being rediscovered as a surprise every time a scenario runs flat.
TRANSLATIONS: tuple[Translation, ...] = (
	Translation(
		prg_parameter="carbon_price_usd_per_tco2",
		engine_field="carbon_price_usd_per_tco2",
		kind="absolute",
		note=(
			"Same quantity, same unit. The engine applies it per carrier as "
			"intensity x price, reading each carrier's intensity from the "
			"technology registry; the PRG states one fleet-wide factor, so the "
			"two agree exactly when the fleet's weighted intensity equals the "
			"graph's single number."
		),
	),
	Translation(
		prg_parameter="demand_growth",
		engine_field="demand_growth",
		kind="absolute",
		note=(
			"Same quantity, same unit, and the same compounding the engine "
			"applies against the network's own years. Meaningful only on a "
			"multi-period network: the exponent is zero everywhere on a "
			"single-period one and the parameter does nothing."
		),
	),
	Translation(
		prg_parameter="fuel_price_usd_per_mwh",
		engine_field="gas_price_multiplier",
		kind="ratio",
		note=(
			"The PRG states an absolute fuel price; the engine scales each gas "
			"unit's base marginal cost. The ratio is the PRG price over the "
			"base gas cost, so it needs the network and refuses without one. "
			"It assumes every gas unit shares one base price, which is the same "
			"fleet-average stand-in the graph's single factor makes."
		),
	),
)


def translations() -> tuple[Translation, ...]:
	"""Every declared translation, with its engine field checked to exist.

	A field that ``ScenarioParameters`` does not define is a mapping that would
	raise ``ValidationError`` at use, which reads as "the engine cannot apply
	this" rather than "this mapping is stale". Checking here puts the failure at
	the declaration, where the name is.
	"""
	fields = set(ScenarioParameters.model_fields)
	for translation in TRANSLATIONS:
		if translation.engine_field not in fields:
			raise ValueError(
				f"translation {translation.prg_parameter!r} names engine field "
				f"{translation.engine_field!r}, which ScenarioParameters does not "
				f"define; the engine's knob was renamed and this mapping is stale"
			)
	return TRANSLATIONS


def _by_prg() -> dict[str, Translation]:
	return {t.prg_parameter: t for t in translations()}


def translated(graph: ParameterGraph) -> tuple[str, ...]:
	"""Settable PRG parameters that reach an engine knob, by name."""
	return tuple(
		sorted(
			name
			for name in graph.nodes
			if graph.is_settable(name) and name in _by_prg()
		)
	)


def untranslated(graph: ParameterGraph) -> tuple[str, ...]:
	"""Settable PRG parameters the engine cannot be told about.

	The register. A scenario that sets one of these and then solves will get a
	result computed as though it had not been set, and no part of the engine
	reports that: the parameter is accepted by the graph, absent from the
	network, and the answer looks like an answer.
	"""
	reached = set(translated(graph))
	return tuple(
		sorted(
			name for name in graph.nodes if graph.is_settable(name) and name not in reached
		)
	)


def coverage(graph: ParameterGraph) -> dict[str, Any]:
	"""How much of the graph's settable surface the engine can be driven from.

	Reported as a fraction with the names behind it, because "3 of 53" and the
	list of the other 50 are the same finding and the second is actionable.
	"""
	reachable = translated(graph)
	missing = untranslated(graph)
	total = len(reachable) + len(missing)
	return {
		"translated": reachable,
		"untranslated": missing,
		"count": len(reachable),
		"total": total,
		"fraction": (len(reachable) / total) if total else 0.0,
		"engine_unreached": engine_fields_unreached(),
	}


def engine_fields_unreached() -> tuple[str, ...]:
	"""Engine knobs no PRG parameter names, by field.

	The other half of the register. :func:`untranslated` counts PRG parameters
	the engine cannot be told about; this counts engine knobs the graph cannot
	speak to, and the two are not the same finding. A knob in this list is a
	lever a what-if scenario can pull that the graph will never see -- so a
	result solved from one cannot be audited against the graph's identities,
	because the graph does not know the quantity moved. ``from_scenario_parameters``
	already states this in prose; this is the same claim, counted.

	Derived from the declared translations rather than listed by hand: a
	hand-written list of what is missing is a second copy that goes stale the
	moment a translation is added, and it would then report a reached knob as
	unreached -- the register lying in the direction that looks like progress.
	"""
	reached = {translation.engine_field for translation in translations()}
	return tuple(
		sorted(name for name in ScenarioParameters.model_fields if name not in reached)
	)


def to_scenario_parameters(
	graph: ParameterGraph,
	values: Mapping[str, float],
	network: Any | None = None,
	*,
	base: ScenarioParameters | None = None,
	strict: bool = True,
) -> ScenarioParameters:
	"""A ``ScenarioParameters`` carrying what ``values`` can express.

	``network`` is required by any ``ratio`` mapping, because an absolute PRG
	value becomes a factor over the network's own base and there is no factor
	without the base. A ratio mapping with no network raises rather than
	defaulting to 1.0: a defaulted factor runs, reports the parameter as
	applied, and applies nothing.

	``strict`` refuses when ``values`` sets a parameter the engine cannot carry.
	A non-strict call drops it, which is what a caller building a partial
	scenario wants -- and the drop is what :func:`untranslated` exists to make
	visible, so the non-strict path is the one that needs the register read.
	"""
	fields: dict[str, Any] = {}
	skipped: list[str] = []
	for name, value in sorted(values.items()):
		if name not in graph.nodes or not graph.is_settable(name):
			continue
		translation = _by_prg().get(name)
		if translation is None:
			skipped.append(name)
			continue
		if translation.kind == "absolute":
			fields[translation.engine_field] = float(value)
			continue
		if network is None:
			raise ValueError(
				f"{name!r} is an absolute value the engine applies as a ratio over "
				f"the network's own base, so translating it needs the network; "
				f"there is no ratio without a base"
			)
		base_value = _base_level(network, name)
		if base_value in (None, 0.0):
			raise ValueError(
				f"the network carries no base level for {name!r}, so the ratio the "
				f"engine needs cannot be formed; the engine would apply a factor of "
				f"one and report the parameter as applied"
			)
		fields[translation.engine_field] = float(value) / float(base_value)
	if strict and skipped:
		raise ValueError(
			f"the engine cannot carry {sorted(skipped)}; pass strict=False to drop "
			f"them, and read `untranslated()` for what that drop costs"
		)
	merged = base.model_dump() if base is not None else {}
	merged.update(fields)
	return ScenarioParameters(**merged)


def _base_level(network: Any, prg_parameter: str) -> float | None:
	"""The network's own base value a ratio translation divides by.

	Read from the snapshot ``apply.py`` records, because that is the value the
	engine's own scaling reads: dividing by the *current* marginal cost instead
	would make the translation depend on how many times it had already been
	applied, which is the compounding defect the snapshot exists to prevent.
	"""
	from alea.whatif.apply import _ensure_base_snapshot, _read_base_snapshot

	# Recorded if absent, a no-op if present -- the same idempotent call
	# `apply_parameters` makes. On a network no scenario has touched, the
	# current values *are* the base, and this is what puts them in the record;
	# reading an empty snapshot instead made the translation refuse a network
	# the engine would have been happy to scale.
	_ensure_base_snapshot(network)
	snapshot = _read_base_snapshot(network)
	if prg_parameter != "fuel_price_usd_per_mwh":
		return None
	costs = snapshot.get("marginal_cost", {})
	carriers = getattr(network, "generators", None)
	if carriers is None or carriers.empty:
		return None
	gas = [
		costs[str(name)]
		for name in carriers.index
		if str(carriers.loc[name, "carrier"]).lower() == "gas" and str(name) in costs
	]
	if not gas:
		return None
	# The mean, because the engine applies one factor to every gas unit: a
	# factor that matched one unit would misprice the rest.
	return sum(gas) / len(gas)


def from_scenario_parameters(
	params: ScenarioParameters,
) -> dict[str, float]:
	"""The PRG parameters a ``ScenarioParameters`` carries, for the graph.

	The inverse direction, and partial by construction: the engine's knobs that
	no PRG parameter names have no route back, and a caller that wants a graph
	check on a scenario built from them should read this as "these are the ones
	the graph can speak to" rather than as the scenario's whole parameter set.
	:func:`engine_fields_unreached` names the knobs this drops -- computed from
	the declared translations, not transcribed, because a transcribed list of
	what is missing drifts the moment a translation is added.
	"""
	out: dict[str, float] = {}
	for translation in translations():
		if translation.kind != "absolute":
			continue
		value = getattr(params, translation.engine_field, None)
		if value is not None:
			out[translation.prg_parameter] = float(value)
	return out
