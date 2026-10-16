# SPDX-License-Identifier: MIT
"""Reading ``docs/params.md``: the master parameter catalog, as data.

WHY this exists. Three fields on ``ParameterNode`` -- ``status``, ``users`` and
``source`` -- have their referent in this document and nowhere else. The
specification's own example node carries all three, the model accepts them, and
until this module nothing in ``src/`` had ever opened the file: the catalog was
cited in prose by ``prg-status.md`` and read by no code at all. That is the
recurring defect in this tree in its purest form -- a declaration with no
reader -- applied to the document the declarations were copied from.

WHY the document is parsed rather than transcribed. ``library.py`` makes the
argument for its own registers and it holds here unchanged: a transcribed count
is a second copy that drifts from the first, and it drifts in the direction
that reads as coverage. So the catalog's own claims -- the title's parameter
count, each category heading's row count -- are read out of the file and
compared against what the file actually contains, and the comparison is the
register.

WHY the three claims are checked separately. They are three different
statements and they disagree with each other:

* the title says 784 parameters;
* the category headings declare per-category counts summing to 824;
* the table holds 824 numbered rows but only 787 distinct parameter names,
  because 35 names appear on more than one row.

A reader that counted rows and compared to 784 would report a 40-row surplus
and stop. A reader that counted distinct names would report a 3-name surplus.
Neither is the finding on its own: the finding is that one document states a
number, states a second number 40 higher in its own headings, and contains a
third, and nothing reconciles them because nothing read the file.

WHY a duplicate name is not automatically a defect. The catalog is organised by
*concern* rather than by quantity, so a parameter genuinely relevant to two
categories is listed under both -- ``heat_pump_adoption`` under Demand and under
Sector Coupling, ``equity_return_target`` under Macroeconomic and under
Investment & Finance. Listing one quantity twice is a defensible editorial
choice for a document whose purpose is "find the parameter relevant to your
concern". What is *not* defensible is that nothing counts them, because a
duplicate that has drifted -- two rows stating different defaults, units or
statuses for one name -- is a contradiction inside a single document and reads
exactly like a deliberate cross-listing. :func:`contradictions` is the check
that separates the two.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alea.config import paths

__all__ = [
	"CATALOG_PATH",
	"CATALOG_STATUS_LEGEND",
	"CATALOG_TITLE_COUNT",
	"CLASSIFICATION_FIELDS",
	"PROSE_FIELDS",
	"CatalogRow",
	"CatalogSummary",
	"NameConflict",
	"StatusJoin",
	"catalog_report",
	"category_counts",
	"contradictions",
	"graph_join",
	"read_catalog",
	"status_join",
	"summary",
	"title_count",
]

#: Where the catalog lives, relative to the repository root.
CATALOG_PATH = Path("docs") / "params.md"

#: How many parameters the document's *title* claims.
#:
#: Deliberately a literal, and not ``len(rows)``. This is the claim;
#: :func:`read_catalog` is the witness, and the test asserts the two agree.
#: Deriving the expected count from the document would make the check vacuous
#: -- it would pass on a catalog of three parameters or three thousand, which
#: is exactly the failure ``library.SPEC_SYSTEM_COUNT`` exists to avoid.
#:
#: It is *also* not what :func:`summary` reports. The register serves
#: :func:`title_count`, which reads the number out of the document, so editing
#: the title moves the register; this constant is what the test asserts that
#: reading equals. Serving the constant instead would have made the title
#: unread -- the register would report ``784`` against a document claiming
#: ``900`` and every test would still pass.
CATALOG_TITLE_COUNT = 784

#: The catalog's Status column legend, exactly as the document states it.
#:
#: The three glyphs and their meanings, transcribed once because the document
#: is where a reader of a row learns what a row's glyph means. Kept here rather
#: than in ``views.py`` because it is the *catalog's* vocabulary and not the
#: graph's: the graph's ``ParameterNode.status`` uses the words
#: (``existing``/``to_build``/``integrate``) and this is the mapping between
#: the two spellings, which is the join :func:`graph_join` performs.
CATALOG_STATUS_LEGEND: dict[str, str] = {
	"✅": "existing",
	"🔨": "to_build",
	"🔗": "integrate",
}

_ROW = re.compile(r"^\|\s*(?P<id>\d+\.\d+)\s*\|")
_NAMED = re.compile(r"^`(?P<name>[A-Za-z0-9_]+)`$")
_CATEGORY = re.compile(r"^##\s+CATEGORY\s+(?P<number>\d+):\s*(?P<name>.+?)\s*\((?P<count>\d+)\)\s*$")
_TITLE = re.compile(r"^##\s+.*?\b(?P<count>\d+)\s+Parameters\b")


@dataclass(frozen=True)
class CatalogRow:
	"""One catalog row: a parameter, its concern, and what it declares."""

	id: str
	"""The catalog's own id, ``9.25``. Not a graph id -- the two are unrelated
	numbering schemes and joining on this would be joining on nothing."""

	category: str
	"""The category *name* from the row, e.g. ``Macro``. The document spells
	these in full in the headings (``MACROECONOMIC``) and abbreviated in the
	rows (``Macro``); this is the row's spelling, because the row is what a
	reader joins on."""

	name: str
	"""The parameter identifier, from the backticked cell."""

	description: str
	algorithm: str
	implementation: str
	status: str
	"""The raw glyph, one of :data:`CATALOG_STATUS_LEGEND`'s keys."""

	users: str
	"""The Users cell as written. Kept as the raw string rather than split: the
	document uses commas inside a cell and the separator is not reliably
	distinguishable from a comma inside a user's name."""

	priority: str


@dataclass(frozen=True)
class CatalogSummary:
	"""What the catalog claims, and what it contains."""

	path: Path
	title_count: int
	"""The count in the document's title. The claim."""

	declared_total: int
	"""The sum of the per-category counts in the headings. The second claim."""

	row_count: int
	"""Numbered rows the table actually holds. The witness."""

	distinct_names: int
	"""Distinct parameter names among those rows."""

	repeated_names: tuple[tuple[str, int], ...]
	"""``(name, occurrences)`` for every name on more than one row."""

	def surplus_over_title(self) -> int:
		"""Rows the table holds beyond the count the title states.

		Positive means the document contains more rows than its own title
		claims. This is the number that makes the discrepancy a fact rather
		than an impression.
		"""
		return self.row_count - self.title_count


def _read(path: Path | None = None) -> str:
	document = path or (paths.repo_root() / CATALOG_PATH)
	if not document.exists():
		raise FileNotFoundError(
			f"no parameter catalog at {document}; `read_catalog` reads the "
			f"master table from that document and cannot check a graph against "
			f"a file that is not there"
		)
	return document.read_text()


def _cells(line: str) -> list[str]:
	return [cell.strip() for cell in line.strip().strip("|").split("|")]


def title_count(path: Path | None = None) -> int:
	"""How many parameters the document's *title* claims.

	Read out of the heading rather than served from :data:`CATALOG_TITLE_COUNT`,
	which is the difference between a register and a second copy of the number
	it is supposed to be checking. The constant is the *expected* value and the
	test's assertion; this is the *observed* one. If the two were the same
	object, editing the document's title would move nothing and the register
	would report a claim the document no longer makes.

	Raises when the title is absent or unnumbered: a document whose heading no
	longer states a count is one where the 784-vs-824 finding cannot be stated
	at all, and returning a default would invent it.
	"""
	for line in _read(path).splitlines():
		title = _TITLE.match(line)
		if title:
			return int(title.group("count"))
	raise ValueError(
		"the catalog's title does not state a parameter count; the heading "
		"reading '<N> Parameters' is what this reader takes the claim from, and "
		"without it there is no claim to check the table against"
	)


def read_catalog(path: Path | None = None) -> tuple[CatalogRow, ...]:
	"""Every numbered row of the catalog, in document order.

	A row is numbered when its first cell matches ``N.M`` and it carries the
	nine columns the header declares. Anything else -- the header itself, the
	separator, prose, the per-category summary table at the end of the document
	-- is not a row.

	The column count is asserted rather than assumed. A cell containing an
	unescaped ``|`` would shift every later column by one and turn the Status
	cell into the Users cell, and a reader that indexed blindly would then
	report a status vocabulary of user names. The document has no such cell
	today; the check is what keeps that a fact rather than an assumption.
	"""
	rows: list[CatalogRow] = []
	for line in _read(path).splitlines():
		if not line.startswith("|") or not _ROW.match(line):
			continue
		cells = _cells(line)
		if len(cells) != 9:
			raise ValueError(
				f"a catalog row has {len(cells)} cells where the header declares "
				f"9: {line[:120]!r}. An unescaped pipe in a cell shifts every "
				f"column after it, which would make the Status column read as "
				f"the Users column"
			)
		name = _NAMED.match(cells[2])
		if name is None:
			raise ValueError(
				f"catalog row {cells[0]} names {cells[2]!r}, which is not a "
				f"single backticked identifier; the parameter column was "
				f"restructured and this reader no longer parses it"
			)
		rows.append(
			CatalogRow(
				id=cells[0],
				category=cells[1],
				name=name.group("name"),
				description=cells[3],
				algorithm=cells[4],
				implementation=cells[5],
				status=cells[6],
				users=cells[7],
				priority=cells[8],
			)
		)
	if not rows:
		raise ValueError(
			f"no numbered rows found in {path or CATALOG_PATH}; the table was "
			f"restructured and this reader no longer parses it"
		)
	return tuple(rows)


def category_counts(path: Path | None = None) -> dict[str, tuple[int, int]]:
	"""Per category heading: ``(declared, actual)`` row counts.

	``declared`` is the number in the heading's own parentheses, ``actual`` is
	how many numbered rows follow it before the next heading. They are equal
	throughout the shipped document, which is why the total is 824 rather than
	784: the discrepancy is between the headings and the *title*, not between
	the headings and their rows.

	Returned as a mapping rather than a total because a heading that disagrees
	with its own rows is a different finding from a document that disagrees
	with its title, and a caller reporting one number cannot tell them apart.
	"""
	lines = _read(path).splitlines()
	out: dict[str, tuple[int, int]] = {}
	current: str | None = None
	seen = 0
	for line in lines:
		heading = _CATEGORY.match(line)
		if heading:
			if current is not None:
				out[current] = (out[current][0], seen)
			current = f"{heading.group('number')}. {heading.group('name')}"
			out[current] = (int(heading.group("count")), 0)
			seen = 0
			continue
		if current is not None and _ROW.match(line):
			seen += 1
	if current is not None:
		out[current] = (out[current][0], seen)
	return out


#: The columns that classify a parameter rather than describe it.
#:
#: The split matters because the two kinds of disagreement mean different
#: things. A *classification* column (status, users, priority) is an assertion
#: about the parameter: ``status`` says whether it is built, ``priority`` says
#: when it is needed, ``users`` says who needs it. Two rows disagreeing there
#: is one document making two incompatible assertions about one parameter.
#: The prose columns (description, algorithm, implementation) are written *for
#: a concern*, so the same quantity described under Outage and again under
#: Operational differs by design -- ``forced_outage_rate``'s algorithm reads
#: "Stochastic outage model" in one section and "Forced outage rate" in the
#: other, and both are correct statements about where a reader will find it.
#: Folding the two classes together would report 11 findings where 2 are real,
#: and a register that cries wolf nine times is one a reader stops reading.
CLASSIFICATION_FIELDS: tuple[str, ...] = ("status", "users", "priority")

#: The columns written for a concern rather than asserted about the parameter.
PROSE_FIELDS: tuple[str, ...] = ("description", "algorithm", "implementation")


@dataclass(frozen=True)
class NameConflict:
	"""One name on more than one row, and which columns disagree."""

	name: str
	rows: tuple[CatalogRow, ...]
	classification: tuple[str, ...]
	"""Classification columns the rows disagree on. Empty for a cross-listing
	whose rows are consistent about what the parameter *is*."""

	prose: tuple[str, ...]
	"""Prose columns the rows word differently. Expected on most duplicates."""

	@property
	def is_classification_conflict(self) -> bool:
		"""Whether this is one document contradicting itself.

		The register's predicate, and the only one worth failing a build on.
		"""
		return bool(self.classification)


def contradictions(
	rows: tuple[CatalogRow, ...] | None = None,
	*,
	classification_only: bool = False,
) -> dict[str, NameConflict]:
	"""Names on more than one row whose rows disagree, and about what.

	Compared field by field rather than as a whole row, because the catalog id
	and the category differ by construction on every duplicate -- the two rows
	are in different sections -- so a whole-row comparison would report all 35
	duplicates and the register would be noise.

	``classification_only`` keeps just the conflicts in
	:data:`CLASSIFICATION_FIELDS`, which are the ones that mean the document
	contradicts itself. The default returns every conflict with the two classes
	kept apart, so a caller reporting "11 duplicates disagree" cannot do so
	without also being able to see that 9 of them disagree only about wording.
	"""
	by_name: dict[str, list[CatalogRow]] = defaultdict(list)
	for row in rows if rows is not None else read_catalog():
		by_name[row.name].append(row)
	out: dict[str, NameConflict] = {}
	for name, group in sorted(by_name.items()):
		if len(group) < 2:
			continue
		classification = tuple(
			field
			for field in CLASSIFICATION_FIELDS
			if len({getattr(row, field) for row in group}) > 1
		)
		prose = tuple(
			field
			for field in PROSE_FIELDS
			if len({getattr(row, field) for row in group}) > 1
		)
		if not classification and not prose:
			continue
		if classification_only and not classification:
			continue
		out[name] = NameConflict(
			name=name,
			rows=tuple(group),
			classification=classification,
			prose=prose,
		)
	return out


def graph_join(
	rows: tuple[CatalogRow, ...] | None = None,
	*,
	graph: object | None = None,
) -> dict[str, tuple[CatalogRow, ...]]:
	"""Catalog rows for every graph node whose name the catalog also uses.

	The join ``status``, ``users`` and ``source`` all rest on, and the reason
	those three fields are populated on almost nothing: the catalog is
	*technology- and concern-specific* (``peak_demand_multiplier``,
	``rooftop_solar_adoption``) while the graph is a *country aggregate*
	(``peak_demand_mw``, ``vre_share``), so the two name the same quantity
	rarely and the same *string* six times.

	Returned name-keyed with the graph node as the key, so a caller asking
	"what does the catalog say about this node" gets every row that answers
	and not just the first -- the duplicate rows are precisely where the two
	documents can disagree.

	A name match is not a quantity match. ``discount_rate`` joins on the string
	and both are a rate; ``total_jobs`` joins on the string and the catalog's
	row counts jobs while the graph's node counts them too. Nothing here
	verifies that, and nothing can: the join is on the identifier, and the
	identifier is all the two documents share.
	"""
	if graph is None:
		from alea.prg.graph import load_graph

		graph = load_graph()
	names = set(getattr(graph, "nodes", {}))
	by_name: dict[str, list[CatalogRow]] = defaultdict(list)
	for row in rows if rows is not None else read_catalog():
		if row.name in names:
			by_name[row.name].append(row)
	return {name: tuple(group) for name, group in sorted(by_name.items())}


@dataclass(frozen=True)
class StatusJoin:
	"""One graph node the catalog also names, and whether the two agree."""

	parameter: str
	catalog_status: str
	"""The catalog's word, already translated through
	:data:`CATALOG_STATUS_LEGEND`. Kept as the graph's vocabulary so a caller
	compares two of the same kind; the raw glyph is on the rows."""

	graph_status: str
	agrees: bool
	rows: tuple[CatalogRow, ...]

	def describe(self) -> str:
		if self.agrees:
			return f"{self.parameter}: both say {self.graph_status}"
		return (
			f"{self.parameter}: the graph says {self.graph_status} and the "
			f"catalog says {self.catalog_status}"
		)


def status_join(
	rows: tuple[CatalogRow, ...] | None = None,
	*,
	graph: object | None = None,
) -> tuple[StatusJoin, ...]:
	"""Every graph node the catalog names, with the two statuses reconciled.

	The reader ``ParameterNode.status`` never had. The field was on all 88
	shipped nodes and, until this, was read by no gate, no register and no
	solve -- it reached two API doors and decided nothing, which is why it could
	drift from the catalog the labels were copied from. The catalog join then
	took the field to all 869 nodes, so the register this function serves grew
	with the graph: the six-name join it once reconciled is now every node the
	catalog and the graph both name.

	A node whose catalog rows *disagree with each other* is reported against
	the first row and is a finding of its own (:func:`contradictions` names
	it): the two documents can only be reconciled where the catalog is
	self-consistent, and picking a row silently would be the join inventing an
	answer. ``equity_return_target`` is the live case -- the graph says
	``to_build`` and both catalog rows say ``integrate``, so that one is a real
	disagreement rather than an artefact of which row was read.
	"""
	if graph is None:
		from alea.prg.graph import load_graph

		graph = load_graph()
	joined = graph_join(rows, graph=graph)
	out: list[StatusJoin] = []
	for parameter, group in sorted(joined.items()):
		node = getattr(graph, "nodes", {}).get(parameter)
		if node is None:  # pragma: no cover - graph_join filtered on this
			continue
		glyph = group[0].status
		catalog_status = CATALOG_STATUS_LEGEND.get(glyph, "")
		graph_status = str(getattr(node, "status", ""))
		out.append(
			StatusJoin(
				parameter=parameter,
				catalog_status=catalog_status,
				graph_status=graph_status,
				agrees=bool(catalog_status) and catalog_status == graph_status,
				rows=group,
			)
		)
	return tuple(out)


def catalog_report(
	*,
	path: Path | None = None,
	graph: object | None = None,
) -> dict[str, Any]:
	"""The catalog register as a payload: its claims, and the joins.

	Keyword-only, because both arguments are optional and neither is guessable
	from position: ``catalog_report(graph)`` reads a ``ParameterGraph`` as a
	path and raises ``AttributeError: 'ParameterGraph' object has no attribute
	'exists'``, which names neither the argument nor the mistake. The caller
	that made it was this module's own summary wiring.

	Carried as one object rather than three top-level keys because the three
	numbers only mean something together -- ``784`` in the title against ``824``
	in the rows is the finding, and a payload that served either alone would
	read as a fact rather than as a disagreement.

	Degrades honestly: a tree with no ``docs/params.md`` reports
	``readable: false`` with a reason rather than an empty register, because an
	empty conflict list and a catalog nobody opened are the same JSON
	otherwise and only one of them is good news. Every count is zero there,
	including ``title_count``: the claim lives *in* the document, so a report
	that cannot read the document has no claim to state, and serving
	:data:`CATALOG_TITLE_COUNT` would have the register asserting the contents
	of a file it could not open.
	"""
	document = path or (paths.repo_root() / CATALOG_PATH)
	if not document.exists():
		return {
			"readable": False,
			"reason": f"no parameter catalog at {document}",
			"title_count": 0,
			"row_count": 0,
			"distinct_names": 0,
			"declared_total": 0,
			"surplus_over_title": 0,
			"repeated_names": 0,
			"classification_conflicts": {},
			"status_join": [],
			"status_disagreements": [],
		}
	rows = read_catalog(document)
	summary_ = summary(document)
	conflicts = contradictions(rows, classification_only=True)
	joins = status_join(rows, graph=graph)
	return {
		"readable": True,
		"reason": "",
		"title_count": summary_.title_count,
		"row_count": summary_.row_count,
		"distinct_names": summary_.distinct_names,
		"declared_total": summary_.declared_total,
		"surplus_over_title": summary_.surplus_over_title(),
		"repeated_names": len(summary_.repeated_names),
		"classification_conflicts": {
			name: {
				"fields": list(conflict.classification),
				"rows": [
					{
						"id": row.id,
						"category": row.category,
						**{field: getattr(row, field) for field in conflict.classification},
					}
					for row in conflict.rows
				],
			}
			for name, conflict in conflicts.items()
		},
		"status_join": [
			{
				"parameter": join.parameter,
				"graph_status": join.graph_status,
				"catalog_status": join.catalog_status,
				"agrees": join.agrees,
			}
			for join in joins
		],
		"status_disagreements": [
			join.describe() for join in joins if not join.agrees
		],
	}


def summary(path: Path | None = None) -> CatalogSummary:
	"""The catalog's claims and its contents, side by side.

	The register. Three numbers that should be one, read from one document, so
	a reader can see the disagreement without parsing markdown by hand.
	"""
	rows = read_catalog(path)
	counts = category_counts(path)
	counts_by_name = Counter(row.name for row in rows)
	return CatalogSummary(
		path=path or (paths.repo_root() / CATALOG_PATH),
		title_count=title_count(path),
		declared_total=sum(declared for declared, _ in counts.values()),
		row_count=len(rows),
		distinct_names=len(counts_by_name),
		repeated_names=tuple(
			sorted((name, n) for name, n in counts_by_name.items() if n > 1)
		),
	)
