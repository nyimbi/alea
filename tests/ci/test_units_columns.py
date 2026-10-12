# SPDX-License-Identifier: MIT
"""`02-data-pipeline.md` §2.3: no numeric column carries a bare unit.

§2.3 states the rule and names the gate: *"Every numeric column carries its unit
in the name. A test asserts that no column in a processed artefact matches
``^(capacity|cost|price|energy|power)$`` without a unit suffix."*

**Scoped to numeric columns, because the rule is about quantities.** A first
draft asserted it against every column and the check was wrong: `plant_id`,
`country_iso` and `model_version` are strings, have no unit and need none, and a
gate that demands a unit of an ISO code is a gate whose operator learns to skip
it. §2.3's own words are "every *numeric* column".

**A unit can be declared rather than spelled into the name, and that is
checked.** `ColumnSpec.unit` exists for exactly this, and three columns rely on
it: `capacity_factor` and `auc` are `p.u.` and `AUC`, which have no spelling a
name can carry. So a numeric column passes if its name ends in a unit, or if its
schema declares a non-empty ``unit``, or if the schema carries a per-row ``unit``
column that the projection fills. Every one of those three is asserted to be
non-empty, because "the schema declares a unit" is worth nothing if the string
is blank.

**The gate is on the frames, not only on the schema objects.** A schema is a
declaration, and a declaration is not the thing it declares: `project_prices`
builds its frame from a ``value_name="price"`` melt, so a rule enforced only by
reading `MARKET_PRICES.columns` would pass while the frame carried the bare name
with a null unit. Both are checked -- and the frame is checked by running the
projection, because that is the only way to see what it writes.
"""

from __future__ import annotations

import re

import pandas as pd

import alea.planning.schemas as planning_schemas
import alea.publish.views as publish_views
from alea.planning.schemas import ArtefactSchema

#: §2.3's own pattern, verbatim.
BARE_UNIT = re.compile(r"^(capacity|cost|price|energy|power)$")

#: Quantities §2.3 gives a required spelling for. A numeric column carrying one
#: of these words must carry the unit too, whether or not the whole name matches
#: above -- ``price_local`` is a bare unit with a qualifier glued on, and a
#: pattern anchored at both ends is blind to it. Nobody writes ``price`` twice in
#: one frame; they write ``price_local`` and ``price_usd``, and one of those
#: names a unit while the other names a market.
QUANTITY_WORDS = ("capacity", "cost", "price", "energy", "power")

#: Unit spellings this repository uses as the trailing token of a column name.
UNIT_TOKENS = frozenset(
	{
		"mw", "mwh", "mva", "mvah", "kv", "km", "kw", "kwh", "gwh", "twh", "gw",
		"usd", "eur", "kes", "pct", "pct_yr", "h", "hr", "hrs", "hour", "hours",
		"min", "minutes", "day", "days", "year", "years", "yr", "yrs", "kg", "t",
		"tonnes", "tco2", "pu", "fraction", "probability", "deg", "m", "m2", "ha",
		"persons", "people", "customers", "count", "n", "seconds", "s", "index", "auc",
	}
)


def _declared() -> dict[str, ArtefactSchema]:
	"""Every declared schema in the package, by ``module.name``."""
	found: dict[str, ArtefactSchema] = {}
	for module in (planning_schemas, publish_views):
		for attribute in dir(module):
			value = getattr(module, attribute)
			if isinstance(value, ArtefactSchema):
				found[f"{module.__name__}.{attribute}"] = value
	return found


def _numeric(schema: ArtefactSchema) -> list:
	"""The columns of a schema that hold a quantity."""
	return [spec for spec in schema.columns if spec.dtype in ("float", "int")]


def _name_carries_a_unit(name: str) -> bool:
	"""Whether a column name spells its unit, as a trailing token or ``_per_``.

	``capacity_mw`` yes; ``lifetime_years`` yes; ``price_local`` no -- ``local``
	is a market, not a unit. ``usd_per_kw_yr`` yes, as a ratio of units.
	"""
	tokens = name.split("_")
	if len(tokens) < 2:
		return False
	tail = tokens[1:]
	joined = "_".join(tail)
	if "_per_" in joined:
		head, _, rest = joined.partition("_per_")
		return head in UNIT_TOKENS and all(p in UNIT_TOKENS for p in rest.split("_"))
	return tokens[-1] in UNIT_TOKENS


def _has_row_unit(schema: ArtefactSchema) -> bool:
	"""Whether the schema carries a per-row ``unit`` column.

	§2.3's mechanism for a quantity whose unit varies by row: *"Currency -- never
	converted silently; a rate and its date are recorded."* `MARKET_PRICES.price`
	is the one column that relies on it, and the exemption is only valid while
	the projection fills the column -- asserted by
	`test_the_market_price_unit_column_is_filled_not_null`, because a per-row
	unit column that is null is a bare column with extra steps.
	"""
	return "unit" in schema.names


def _declares_unit(schema: ArtefactSchema, name: str) -> bool:
	"""Whether the column's own `ColumnSpec` names a unit.

	For a quantity with no spelling a name can carry: ``p.u.``, ``AUC``,
	``fraction``. It does **not** excuse §2.3's own pattern -- a column called
	``capacity`` is still named ``capacity`` -- which is why the pattern rule
	below consults `_has_row_unit` and not this.
	"""
	return bool(schema.column(name).unit.strip())


def _states_a_unit(schema: ArtefactSchema, name: str) -> bool:
	"""Every way a numeric column can say what it is measured in."""
	return (
		_name_carries_a_unit(name)
		or _declares_unit(schema, name)
		or _has_row_unit(schema)
	)


def test_the_gate_reads_the_declarations_it_claims_to():
	"""A gate over an empty set of schemas is a gate that cannot fail.

	`isinstance(value, ArtefactSchema)` finds nothing if the classes are ever
	split -- the same class-identity trap an in-process `importlib.reload` set
	for the country registry -- and the loop below would then pass over zero
	objects while reporting success.
	"""
	declared = _declared()
	assert len(declared) >= 15, (
		f"only {len(declared)} schema(s) found; the discovery is not reading the "
		f"package's declarations: {sorted(declared)}"
	)
	assert any(name.endswith("FLEET") for name in declared), "FLEET was not discovered"
	assert any(name.endswith("MARKET_PRICES") for name in declared), "MARKET_PRICES was not discovered"
	quantities = [spec for schema in declared.values() for spec in _numeric(schema)]
	assert len(quantities) >= 37, (
		f"the schemas hold only {len(quantities)} numeric column(s); the numeric "
		f"filter is not selecting the columns the rule is about"
	)


def test_no_numeric_column_carries_a_bare_unit():
	"""§2.3's own pattern, verbatim, against every numeric column.

	**One exemption, and §2.3 states it.** A schema carrying a per-row ``unit``
	column satisfies the rule by a different mechanism -- the reader of a row
	learns the unit from the row, which is what the section's currency paragraph
	asks for. `MARKET_PRICES.price` is the only column that relies on it, and the
	exemption is asserted to be *filled* rather than merely declared.

	A column's own `ColumnSpec.unit` does **not** exempt it here: a column called
	``capacity`` with a declared ``unit="MW"`` is still named ``capacity``, and
	the rule is that a reader of the column list learns the unit without opening
	the schema.
	"""
	offenders: list[str] = []
	for where, schema in sorted(_declared().items()):
		if _has_row_unit(schema):
			continue
		for spec in _numeric(schema):
			if BARE_UNIT.match(spec.name):
				offenders.append(f"{where}.{spec.name}")
	assert not offenders, (
		f"numeric column(s) match §2.3's forbidden pattern: {offenders}. Every "
		f"numeric column carries its unit in its name, or its table carries a "
		f"per-row unit column that the projection fills."
	)


def test_a_qualified_quantity_still_carries_its_unit():
	"""``price_local`` is ``price`` with a qualifier, not with a unit.

	The anchored pattern §2.3 states cannot see this shape, and it is the shape a
	bare unit actually takes once a producer needs two of them: nobody writes
	``price`` twice in one frame, they write ``price_local`` and ``price_usd``.
	Split from the test above because it fails for a different reason and a
	reader diagnosing it needs to know which: this one is about a qualifier
	standing in for a unit, and here a declared unit *does* answer, because
	``capacity_factor`` is genuinely in p.u. and has no name-spellable unit.
	"""
	offenders: list[str] = []
	for where, schema in sorted(_declared().items()):
		for spec in _numeric(schema):
			if spec.name.split("_")[0] not in QUANTITY_WORDS:
				continue
			if _states_a_unit(schema, spec.name):
				continue
			offenders.append(f"{where}.{spec.name}")
	assert not offenders, (
		f"numeric column(s) name a quantity and a qualifier but no unit: "
		f"{offenders}. A qualifier distinguishes two values of one quantity; it "
		f"does not say what either is measured in."
	)


def test_every_numeric_column_declares_a_unit_or_spells_one():
	"""The wider rule: a numeric column says what it is in, one way or another.

	§2.3's pattern catches five names; this catches the column that names no
	quantity at all -- ``sample_size``, ``overloaded_elements``, ``auc`` -- where
	there is no bare-unit pattern to match and yet a reader still needs to know
	whether a number is a count, a fraction or an index. This is the gate that
	found two: both are counts, and both were declared with no unit at all.
	"""
	offenders: list[str] = []
	for where, schema in sorted(_declared().items()):
		if _has_row_unit(schema):
			continue
		for spec in _numeric(schema):
			if _states_a_unit(schema, spec.name):
				continue
			offenders.append(f"{where}.{spec.name}")
	assert not offenders, (
		f"numeric column(s) state no unit and spell none in the name: {offenders}. "
		f"Add `unit=` to the ColumnSpec -- ``count``, ``fraction``, ``index`` -- or "
		f"rename the column to carry it."
	)


def test_the_exemptions_are_declared_units_and_not_blanks():
	"""An exemption resting on a blank string is not an exemption.

	Every column that passes the quantity-word rule only because its
	`ColumnSpec.unit` is set is enumerated and its unit read. This is what keeps
	the non-spellable units honest: `capacity_factor` is ``p.u.`` and `auc` is
	``AUC``, and if either declaration were emptied the rule above would go on
	passing while a reader learned nothing.
	"""
	exempt: dict[str, str] = {}
	for where, schema in sorted(_declared().items()):
		if _has_row_unit(schema):
			continue
		for spec in _numeric(schema):
			if spec.name.split("_")[0] not in QUANTITY_WORDS:
				continue
			if _name_carries_a_unit(spec.name):
				continue
			exempt[f"{where}.{spec.name}"] = spec.unit
	assert exempt, (
		"no column relies on a declared unit for a quantity word; either every "
		"such column spells its unit in its name -- in which case delete this "
		"test rather than leaving it vacuous -- or the exemption path is dead"
	)
	blank = sorted(name for name, unit in exempt.items() if not unit.strip())
	assert not blank, f"column(s) exempted by a blank unit: {blank}"
	for name, unit in sorted(exempt.items()):
		assert unit == unit.strip() and unit, f"{name} declares unit {unit!r}, which is not clean"


def test_the_unit_token_reader_recognises_the_units_this_repo_uses():
	"""Canary for the helper above: a reader that recognises nothing is a gate.

	``_name_carries_a_unit`` is the whole of the gate's discrimination. Returning
	False for everything makes every numeric column an offender and the gate
	noise; returning True for everything makes it silent. Both directions are
	asserted here against names this repository actually uses, so the helper is
	canaried rather than assumed.
	"""
	for spelled in ("capacity_mw", "energy_mwh", "capex_usd", "opex_usd_per_kw_yr",
					"price_usd_per_mwh", "length_km", "voltage_kv", "lifetime_years",
					"horizon_hours", "duration_min", "capture_rate_fraction",
					"capacity_mva", "tenor_years"):
		assert _name_carries_a_unit(spelled), f"{spelled} spells a unit and was not read as one"
	for bare in ("price", "capacity", "cost", "energy", "power", "price_local",
				 "capacity_nominal", "cost_total", "power_peak", "id", "value"):
		assert not _name_carries_a_unit(bare), (
			f"{bare!r} does not spell a unit and was read as one"
		)


def test_every_publish_projection_writes_the_columns_its_schema_declares():
	"""The schema is a claim about the frame; this reads the frame.

	A projection that renames a column after `check` -- or never calls it -- is a
	table whose declared schema describes something else. The empty frame is the
	one whose column names can be read without real inputs, and the names are
	what §2.3 constrains.
	"""
	import alea.publish.service as service

	projections = [
		name
		for name in dir(service)
		if name.startswith("project_") and callable(getattr(service, name))
	]
	assert len(projections) >= 8, f"found {len(projections)} projections: {projections}"

	frame = service._empty("market_prices")
	assert list(frame.columns) == list(publish_views.MARKET_PRICES.names), (
		f"the empty market_prices frame carries {list(frame.columns)}, the schema "
		f"declares {list(publish_views.MARKET_PRICES.names)}"
	)
	assert "unit" in frame.columns, (
		"the market_prices frame lost its unit column, which is the only thing "
		"telling a reader what `price` is stated in"
	)


def test_the_market_price_unit_column_is_filled_not_null():
	"""The exemption is only valid while the unit is actually written.

	A per-row unit column that is empty is a bare column with extra steps. The
	projection is run over a two-bus frame and the unit column read, because the
	projection -- not the schema -- is what writes it.
	"""
	import alea.publish.service as service

	prices = pd.DataFrame(
		{"bus_a": [40.0, 55.0], "bus_b": [42.0, 57.0]},
		index=pd.to_datetime(["2030-01-01 00:00", "2030-01-01 01:00"], utc=True),
	)
	frame = service.project_prices(prices, countries={"bus_a": "KE", "bus_b": "KE"})
	assert "price" in frame.columns, f"project_prices did not write `price`: {list(frame.columns)}"
	assert frame["unit"].notna().all(), "the unit column is null; the exemption does not hold"
	assert (frame["unit"] == "USD/MWh").all(), (
		f"the unit is not the one the schema declares: {frame['unit'].unique()}"
	)


def test_the_bare_unit_gate_fails_on_a_planted_column():
	"""The canary: plant a bare-unit numeric column and watch the gate fail.

	`ArtefactSchema` is frozen and `extra="forbid"`, so the defect is planted by
	rebuilding a schema with one column renamed -- which is exactly what a
	contributor adding a ``capacity`` column would produce. In-process because
	nothing on disk is mutated: the object under test is built here, so there is
	no already-imported module for a source change to fail to reach.

	Both halves are asserted: the planted column is caught, and the shipped
	schema is clean -- otherwise a real defect already present would satisfy the
	first assertion for the wrong reason.
	"""
	from alea.planning.schemas import ColumnSpec, FLEET

	planted = ArtefactSchema(
		name="fleet",
		columns=tuple(
			ColumnSpec(name="capacity", dtype="float", unit="MW", description="")
			if spec.name == "capacity_mw"
			else spec
			for spec in FLEET.columns
		),
	)
	caught = [
		spec.name
		for spec in _numeric(planted)
		if BARE_UNIT.match(spec.name) and not _has_row_unit(planted)
	]
	assert caught == ["capacity"], (
		f"the planted bare-unit column was not caught; the gate is blind to the "
		f"defect it exists for. Caught: {caught}"
	)
	clean = [
		spec.name
		for spec in _numeric(FLEET)
		if BARE_UNIT.match(spec.name) and not _has_row_unit(FLEET)
	]
	assert not clean, f"the shipped FLEET schema already carries bare-unit column(s): {clean}"
	# And the *other* exemption is asserted not to reach this rule: a column that
	# declares its unit in the spec is still caught by §2.3's pattern, which is
	# the whole reason `_declares_unit` is not consulted there.
	declared_only = ArtefactSchema(
		name="fleet",
		columns=tuple(
			ColumnSpec(name="capacity", dtype="float", unit="MW", description="")
			if spec.name == "capacity_mw"
			else spec
			for spec in FLEET.columns
		),
	)
	assert _declares_unit(declared_only, "capacity"), "the planted column does not declare a unit"
	assert BARE_UNIT.match("capacity"), "the planted name does not match §2.3's pattern"
	assert not _has_row_unit(declared_only), (
		"FLEET carries a per-row unit column, so the pattern rule would skip it "
		"entirely and this canary would prove nothing"
	)
	# The wider rule does revoke a blank declaration, which is the assertion that
	# keeps `test_every_numeric_column_declares_a_unit_or_spells_one` honest.
	blanked = ArtefactSchema(
		name="fleet",
		columns=tuple(
			ColumnSpec(name="capacity", dtype="float", unit="", description="")
			if spec.name == "capacity_mw"
			else spec
			for spec in FLEET.columns
		),
	)
	assert not _states_a_unit(blanked, "capacity"), (
		"a column named `capacity` with a blank declared unit was read as stating "
		"its unit, so the wider rule is blind to it"
	)
