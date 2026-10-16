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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from alea.prg.views import Role
from alea.whatif.params import ScenarioParameters

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"CROSS_LAYER_QUANTITIES",
	"CrossLayerQuantity",
	"Translation",
	"TRANSLATIONS",
	"coverage",
	"cross_layer_disagreements",
	"cross_layer_report",
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
#: Short, and the shortness is the finding. Three of the graph's 52 settable
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

	Reported as a fraction with the names behind it, because "3 of 52" and the
	list of the other 49 are the same finding and the second is actionable.

	``endogenous`` is carried beside the fraction and not folded into it. The
	three fleet nodes the optimiser chooses are not settable, so they left this
	denominator -- and a register that shrank from 53 to 52 without saying
	where the three went reads as three parameters that vanished. They did not:
	they are what the *solve* produces, and ``audit.fleet_parameters`` is what
	reads them back out of a result. That is the direction this layer does not
	cover, and naming it here is the difference between a register and a
	subtraction.
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
		"endogenous": graph.endogenous(),
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

	``strict`` also refuses three keys that are not translatable, each with its
	own message, because one message would send an author to the wrong fix. A
	key the graph does not declare is a typo. A key the graph declares but
	*computes* is derived: setting it changes nothing, because ``propagate``
	overwrites it. A key the optimiser *chooses* is endogenous: nothing the
	author sets determines it, and "set what determines it instead" -- the
	derived case's advice -- sends them looking for a lever that does not exist.
	:func:`untranslated` enumerates the graph's own settable parameters, so it
	can name none of the three, and a register built from either direction is
	blind to all of them -- which is how a typo came to solve and apply nothing.
	"""
	fields: dict[str, Any] = {}
	skipped: list[str] = []
	unknown: list[str] = []
	derived: list[str] = []
	endogenous: list[str] = []
	for name, value in sorted(values.items()):
		if name not in graph.nodes:
			# Three findings, not two, and each needs its own message or the
			# advice is wrong. This one is a string the graph does not declare,
			# which is almost always a typo. ``derived`` below is a real graph
			# parameter the graph computes -- setting it is meaningless, because
			# ``propagate`` overwrites it. ``skipped`` is a settable graph
			# parameter the engine has no knob for, which is a real quantity this
			# translation cannot carry. Telling an author to widen the engine for
			# a parameter that does not exist, or to spell-check one that is
			# simply derived, both send them to the wrong fix.
			unknown.append(name)
			continue
		if not graph.is_settable(name):
			# A fourth bucket, because the advice differs. A derived value is
			# overwritten by `propagate`, so the fix is to set what determines
			# it. An endogenous value is chosen by the optimiser: nothing the
			# author sets determines it, and "set what determines it instead"
			# sends them looking for a lever that does not exist.
			if graph.role(name) is Role.ENDOGENOUS:
				endogenous.append(name)
			else:
				derived.append(name)
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
	if strict and unknown:
		raise ValueError(
			f"not graph parameters: {sorted(unknown)}; the graph declares "
			f"{len(graph.nodes)} and none of these is one, which is usually a "
			f"typo. `untranslated()` names the parameters the engine cannot carry"
		)
	if strict and derived:
		raise ValueError(
			f"the graph computes {sorted(derived)}, so setting them changes "
			f"nothing: `propagate` overwrites a derived value. A scenario that "
			f"wants one of these moved sets what determines it instead"
		)
	if strict and endogenous:
		# The levers named here are the ones that *reach* a solve, checked
		# against the translation table and the constraint register rather than
		# written from memory. An earlier version of this message offered "the
		# build target" as well -- and `vre_capacity_target_mw` reaches neither
		# an engine knob nor an inequality, so it is a lever a reader would pull
		# and see nothing move. Naming a fix that does not work is worse than
		# naming none: it costs the reader the round trip that proves it.
		from alea.prg.constraints import bound_parameter_names

		levers = sorted(set(translated(graph)) | set(bound_parameter_names(graph)))
		raise ValueError(
			f"{sorted(endogenous)} are chosen by the optimisation, so setting "
			f"them states an input where the graph states a decision: the solve "
			f"determines them and would overwrite whatever was passed. A "
			f"scenario that wants a different fleet moves what the solve is "
			f"given -- {', '.join(levers)} -- not the fleet it produces"
		)
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


@dataclass(frozen=True)
class CrossLayerQuantity:
	"""One quantity declared in more than one layer, and what disagrees.

	A quantity is *cross-layer* when the deployment's settings
	(``config/config.default.yaml``) and the relation library
	(``config/prg.yaml``) each declare it. The two are different kinds of file
	on purpose -- one is what a deployment chose, the other is what the physics
	and the policy require -- and that is exactly why a quantity appearing in
	both is a finding rather than a convenience: two layers can hold different
	values for the same thing and nothing compares them.
	"""

	config_path: str
	"""Dotted path in ``config.default.yaml``, e.g. ``market.value_of_lost_load``."""

	prg_parameter: str
	"""The graph node that declares the same quantity."""

	unit: str
	"""The unit both sides are in, asserted equal rather than assumed: a match
	on the name with a mismatch on the unit is a different finding."""

	note: str
	"""Which layers consume each side, and what would diverge if they differ."""


#: Quantities the deployment config and the relation library both declare.
#:
#: Declared rather than derived, and that is a deliberate choice with a cost.
#: A name-identical sweep of the two files' numeric leaves finds **zero**
#: overlaps -- the config says ``value_of_lost_load_usd_per_mwh`` where the
#: graph says ``voll_usd_per_mwh`` -- so no mechanical join exists to derive
#: from, and a fuzzy one (shared unit tokens, say) matches dozens of unrelated
#: nodes. The declared list is the honest form: it is a claim about which
#: quantities are the same thing, made by a person, in one place, and it is
#: *checkable* -- the test that reads it asserts each entry resolves on both
#: sides, so a rename in either file breaks the register rather than silently
#: dropping an entry. A derived list that could not be derived would be worse
#: than none.
CROSS_LAYER_QUANTITIES: tuple[CrossLayerQuantity, ...] = (
	CrossLayerQuantity(
		config_path="market.value_of_lost_load_usd_per_mwh",
		prg_parameter="voll_usd_per_mwh",
		unit="USD/MWh",
		note=(
			"Config feeds `market/stages.py`, which prices every hour the system "
			"sheds load; the graph's node feeds `reliability_cost_usd` by "
			"`unserved_energy_gwh * 1000 * voll_usd_per_mwh`. Shipped values "
			"disagree: config is 2000.0 and the graph is 5000.0, so the market "
			"layer and the reliability accounting price an unserved MWh at 2.5x "
			"different rates. Each is internally consistent and nothing compares "
			"them."
		),
	),
	CrossLayerQuantity(
		config_path="sector.hydrogen_export_twh_per_year",
		prg_parameter="",
		unit="TWh/year",
		note=(
			"Declared in config and again as a `ScenarioParameters` field, with "
			"two consumers that build the same load into different networks: "
			"`sector.hydrogen` reads the config value into the sector-coupled "
			"build, and `whatif/apply.py` reads its own param into the network a "
			"scenario perturbs. Both default to 0.0, so nothing diverges today; "
			"moving one and not the other makes the two exports disagree. No PRG "
			"node names this quantity -- `hydrogen_production_kt_per_year` is the "
			"related but distinct production figure -- which is why the graph "
			"column is empty here rather than wrong."
		),
	),
)


def cross_layer_disagreements(
	entries: tuple[CrossLayerQuantity, ...] | None = None,
	*,
	config: Any | None = None,
	graph_values: Mapping[str, float | None] | None = None,
) -> tuple[CrossLayerQuantity, ...]:
	"""Cross-layer quantities whose shipped values differ, with both values.

	The register's live half. Reported rather than raised: a deployment may
	legitimately override the config value, and a check that refused would
	forbid the override it is meant to make visible. What it must not do is
	stay silent -- two layers holding different rates for one quantity is the
	defect this module exists to name, and it is invisible to every other
	check in the tree because each layer is self-consistent.

	``entries``, ``config`` and ``graph_values`` exist so the *predicate* can be
	tested against a constructed pair. Without them the only way to exercise
	the comparison is to change one of the shipped numbers, and a test that
	asserted ``abs(2000.0 - 2000.0) <= 1e-12`` in its own body would be
	checking arithmetic rather than checking this function -- it would pass
	against a version that reported every entry and a version that reported
	none.

	**Reads the config *file*, not a ``Config`` object.** The first version
	called ``load_config()``, which validates the whole deployment config -- so
	every caller inherited a requirement that a scenario section and every
	other layer field be present. Three API route tests build a scratch repo
	root holding only ``prg.yaml`` and immediately raised
	``ValidationError: scenario / Field required``, which is a real coupling
	and not a test that needed widening: this register compares two numbers
	declared in two files and needs neither file validated to do it. A missing
	or unreadable config file is reported by the caller as *unavailable*
	rather than as agreement.
	"""
	config = _read_default_config() if config is None else config
	if config is None:
		return ()
	out: list[CrossLayerQuantity] = []
	for entry in CROSS_LAYER_QUANTITIES if entries is None else entries:
		if not entry.prg_parameter:
			continue
		config_value = _dig(config, entry.config_path)
		if graph_values is None:
			graph_value = _graph_value(entry.prg_parameter)
		else:
			graph_value = graph_values.get(entry.prg_parameter)
		if config_value is None or graph_value is None:
			continue
		if abs(float(config_value) - float(graph_value)) > 1e-12:
			out.append(entry)
	return tuple(out)


def cross_layer_report() -> dict[str, Any]:
	"""The register as a payload: what it compared, and what it found.

	``compared`` is carried because an empty disagreement list and a register
	that could not run are the same JSON otherwise, and only one of them is
	good news. ``reason`` names why when it could not -- a scratch tree with no
	``config.default.yaml`` is a legitimate state (several tests build one) and
	must not read as "the layers agree".
	"""
	from alea.config.paths import default_config_path

	path = default_config_path()
	if not path.exists():
		return {
			"compared": False,
			"reason": f"no deployment config at {path}; nothing to compare against",
			"disagreements": [],
		}
	return {
		"compared": True,
		"reason": "",
		"disagreements": [
			{
				"config_path": entry.config_path,
				"prg_parameter": entry.prg_parameter,
				"unit": entry.unit,
				"note": entry.note,
			}
			for entry in cross_layer_disagreements()
		],
	}


def _read_default_config() -> dict[str, Any] | None:
	"""``config.default.yaml`` as a plain mapping, or None when unreadable.

	The *shipped* defaults, which is the referent this register compares
	against: a deployment that overlays a scenario legitimately moves its own
	value, and comparing against the overlay would report every override as a
	disagreement with the library.
	"""
	import yaml

	from alea.config.paths import default_config_path

	path = default_config_path()
	if not path.exists():
		return None
	try:
		loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
	except (OSError, yaml.YAMLError):
		return None
	return loaded if isinstance(loaded, dict) else None


def _dig(config: Any, dotted: str) -> Any:
	"""``market.value_of_lost_load_usd_per_mwh`` -> the float, or None.

	Walks either a mapping or an object, because the shipped path hands it a
	parsed YAML document and a test may hand it a ``Config``. A missing segment
	returns None rather than raising: an entry naming a path that no longer
	exists is caught by the register's own test, and raising here would turn a
	stale entry into a 500 on the summary route.
	"""
	current: Any = config
	for part in dotted.split("."):
		current = (
			current.get(part)
			if isinstance(current, dict)
			else getattr(current, part, None)
		)
		if current is None:
			return None
	return current


def _graph_value(parameter: str) -> float | None:
	"""The declared default of a graph node, or None when it has none."""
	from alea.prg.graph import load_graph

	graph = load_graph()
	node = graph.nodes.get(parameter)
	return None if node is None or node.default is None else float(node.default)
