# SPDX-License-Identifier: MIT
"""The citation register: which load-bearing claims trace to which work.

WHY this exists. ``docs/plans/00-architecture.md`` §6 declares a ``sources/``
directory holding "archived citations + INDEX.md", and the global rule is
blunter: *never leave a load-bearing citation pointing at a URL you did not
archive, because links rot*. Nine equations in ``config/prg.yaml`` cite
literature by name -- IEA/NEA on ``lcoe_definition``, Wright's law on
``learning_curve``, WHO AirQ+ on ``premature_deaths_definition`` -- and until
this module nothing joined those strings to anything. A citation that is prose
and nothing else is the "declared is not produced" defect this repository keeps
recording, on the library's own provenance: the field is parsed, validated,
served at four doors, and no gate can tell a citation naming a real work from
one naming a work that does not exist.

WHY the register is a Markdown table and not YAML. The plan says
``sources/INDEX.md``, and a person maintains this file -- adding a row is
reading a paper, deciding its licence and writing down where the copy is. A
table in the file the plan names is what that person will actually edit. The
parser below is strict about the columns for the same reason a schema is: a
row with a typo'd column is a row that silently drops a citation, which is
worse than one that fails to parse.

WHY the join is by *name* and the check runs both ways. An equation's
``reference`` is free prose ("Wright's law; cf. IRENA renewable cost
statistics"), not a key, so the register carries the exact spellings a citation
may use and resolves them to one entry. The reverse direction is the one that
catches the register's own decay: an entry no citation reaches is either a work
that was cited and no longer is, or a row someone added and never wired -- and
both are findings, because a register that only grows is a register nobody
reads.

WHY ``archived`` is a field rather than an assumption. A citation whose work is
listed but not on disk is *not* archived, and the distinction is the whole
point of the directory: a URL is a promise and a file is evidence. The gate
refuses an entry marked ``archived`` whose path does not exist, and reports --
without failing -- the entries that are not, because a landing page behind a
paywall or a JavaScript shell cannot be archived by a script and a gate that
refused them would be a gate nobody could pass. The count is the finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: Where the register lives. Declared in `00-architecture.md` §6, and the path
#: is fixed there rather than chosen here.
INDEX_PATH = REPO / "sources" / "INDEX.md"

#: Where an archived copy sits, relative to the repository root.
ARCHIVE_DIR = "sources/archive"

__all__ = [
	"ARCHIVE_DIR",
	"INDEX_PATH",
	"Citation",
	"CitationGap",
	"CitationReport",
	"citation_report",
	"read_index",
]

#: The table's columns, in order. A row is parsed by position and the header is
#: asserted against this tuple, so inserting a column in the document fails the
#: parse instead of shifting every value one cell to the left.
_COLUMNS = ("key", "work", "custodian", "year", "url", "licence", "archived", "cites")

_ROW = re.compile(r"^\|(?!\s*-)(?P<cells>.+)\|\s*$", re.MULTILINE)

_SECTION = re.compile(r"^## Works\s*$", re.MULTILINE)
_ANY_HEADING = re.compile(r"^## ", re.MULTILINE)
"""The register's own table, and only it.

Two tables in the document would otherwise be read as one register: a
three-row example explaining the `archived` column sits before the register,
and a digest table sits after it. A parser that took every row-shaped line
read the example as the header and refused the file, and read the digest table
as rows with two cells instead of eight.

Scoping is by heading, and the stop is the *next* h2 rather than the end of
the text -- a section that ran to EOF would swallow every table added below it,
which is the same defect one table later. The strict header check is what
caught both, which is the argument for the check rather than against the
tables."""


@dataclass(frozen=True)
class Citation:
	"""One work the tree leans on, and where its copy is."""

	key: str
	"""Stable slug, e.g. ``iea_nea_lcoe``. This is what ``Provenance.source_id``
	would carry if a parameter were wired to it."""

	work: str
	custodian: str
	year: str
	url: str
	licence: str

	archived: str
	"""Where the copy is, in one of three states.

	* a repository-relative path -- the copy must exist, and the gate fails if
	  it does not;
	* ``""`` -- a work that is *not* archived, reported and counted but not
	  failed, because a paywall or a JavaScript shell cannot be archived by a
	  script;
	* ``n/a`` -- a standard derivation with no single work behind it. The
	  annuity formula, the WACC identity and the swing equation are textbook
	  results; naming a paper as their source would fabricate a citation, which
	  is worse than recording that they have none.
	"""

	cites: tuple[str, ...]
	"""Every spelling a citation uses to reach this entry.

	An equation's ``reference`` is prose, so the register holds the literal
	substrings that resolve to it. A citation may reach an entry by more than one
	spelling -- ``crf_definition`` says "IEA/NEA Projected Costs of Generating
	Electricity" where ``lcoe_definition`` says "IEA/NEA, Projected Costs of
	Generating Electricity" -- and both are the same work, so both are listed
	rather than the citation being rewritten to fit a key.
	"""

	def resolves(self, reference: str) -> bool:
		"""Whether ``reference`` names this work.

		Case-insensitive and substring-based: the citation is prose written by
		whoever wrote the equation, and demanding it match a key exactly would
		mean editing the physics library to satisfy a bibliography.

		**The key is one of the spellings.** An equation may cite a row by its
		register key -- ``reference: entsoe_adequacy`` -- and that is not a
		weaker citation than prose, it is the row's primary identifier. The
		predicate did not read it, so eight equations citing a bare key were
		reported as resolving to nothing while the row they named sat in the
		register. None of the 51 rows lists its own key in ``cites``, which is
		what let the gap survive: the join looked only at the spellings the
		column happened to carry. The key is appended here rather than to 51
		rows, because a register that has to restate its own identifier in a
		second column is a register with two sources of truth for one name.
		"""
		haystack = reference.casefold()
		needles = (*self.cites, self.key)
		return any(needle.casefold() in haystack for needle in needles)

	@property
	def archive_path(self) -> Path | None:
		"""The archived copy's absolute path, or ``None``.

		``None`` for both ``""`` and ``n/a``: neither names a file. The two are
		kept apart by :attr:`needs_archive`, which is what the report counts.
		"""
		if not self.archived or self.archived == "n/a":
			return None
		return REPO / self.archived

	@property
	def needs_archive(self) -> bool:
		"""Whether a copy of this work *should* exist and does not.

		``n/a`` is excluded: a standard derivation is not an unarchived work, and
		counting it as one would inflate the register's own gap count with five
		entries nobody can close.
		"""
		return self.archived == ""


@dataclass(frozen=True)
class CitationGap:
	"""One way the register and the tree disagree."""

	kind: str
	"""``unregistered`` | ``unarchived`` | ``unreachable`` | ``missing_file``."""

	subject: str
	detail: str

	def summary(self) -> str:
		return f"{self.kind}: {self.subject} -- {self.detail}"


@dataclass(frozen=True)
class CitationReport:
	"""The register's verdict: what resolves, what does not, and what is on disk."""

	citations: tuple[Citation, ...]
	gaps: tuple[CitationGap, ...]

	@property
	def registered(self) -> int:
		return len(self.citations)

	@property
	def archived(self) -> tuple[Citation, ...]:
		"""Entries whose copy is on disk.

		The count that matters. A register of twelve works with two archived is
		a bibliography, not an archive, and the difference is invisible unless
		something states it.
		"""
		return tuple(
			c for c in self.citations if c.archive_path and c.archive_path.is_file()
		)

	@property
	def failures(self) -> tuple[CitationGap, ...]:
		"""Gaps that are defects rather than states of the world.

		``unarchived`` is excluded deliberately: a work behind a paywall or
		served as a JavaScript shell cannot be archived by a script, and
		refusing it would make the gate unpassable. It is reported and counted.
		"""
		return tuple(g for g in self.gaps if g.kind != "unarchived")

	def summary(self) -> str:
		return (
			f"{self.registered} citation(s) registered, "
			f"{len(self.archived)} archived on disk; "
			f"{len(self.failures)} defect(s), "
			f"{len(self.gaps) - len(self.failures)} unarchived work(s)."
		)


def read_index(path: Path | None = None) -> tuple[Citation, ...]:
	"""Parse the citation register.

	Raises ``ValueError`` on a malformed table rather than skipping the row: a
	row this parser cannot read is a citation nothing can check, and dropping it
	quietly is how a register stops being one.
	"""
	path = INDEX_PATH if path is None else path
	if not path.is_file():
		return ()
	text = path.read_text()
	section = _SECTION.search(text)
	if section is None:
		return ()
	rest = text[section.end() :]
	stop = _ANY_HEADING.search(rest)
	body = rest[: stop.start()] if stop else rest
	rows = list(_ROW.finditer(body))
	if not rows:
		return ()
	header = tuple(
		cell.strip() for cell in rows[0].group("cells").split("|")
	)
	if header != _COLUMNS:
		raise ValueError(
			f"{path.name}: header is {header}, expected {_COLUMNS}. "
			f"A row is parsed by position, so a changed column order or a "
			f"misspelled heading shifts every value silently."
		)
	citations: list[Citation] = []
	for row in rows[1:]:
		cells = [cell.strip() for cell in row.group("cells").split("|")]
		if len(cells) != len(_COLUMNS):
			raise ValueError(
				f"{path.name}: row {cells!r} has {len(cells)} cells, "
				f"expected {len(_COLUMNS)}"
			)
		key, work, custodian, year, url, licence, archived, cites = cells
		if not key:
			continue
		citations.append(
			Citation(
				key=key,
				work=work,
				custodian=custodian,
				year=year,
				url=url,
				licence=licence,
				archived=archived,
				cites=tuple(
					part.strip() for part in cites.split(";") if part.strip()
				),
			)
		)
	return tuple(citations)


def citation_report(
	*,
	path: Path | None = None,
	references: tuple[tuple[str, str], ...] | None = None,
) -> CitationReport:
	"""Join the register against every citation the tree makes.

	``references`` is ``(owner, reference)`` pairs -- the equation id and its
	citation text -- and defaults to reading them off the graph. It is a
	parameter so the *predicate* can be tested against a constructed pair: a
	test that could only exercise this by editing ``config/prg.yaml`` would have
	to assert against the shipped citations, and would pass against a version
	that resolved everything and one that resolved nothing.
	"""
	assert path is None or isinstance(path, Path), "path must be a Path or None"
	citations = read_index(path)
	if references is None:
		references = _equation_references()

	gaps: list[CitationGap] = []
	for citation in citations:
		archive = citation.archive_path
		if archive is not None and not archive.is_file():
			gaps.append(
				CitationGap(
					kind="missing_file",
					subject=citation.key,
					detail=(
						f"row says archived at {citation.archived!r}, which is not "
						f"a file; a register claiming a copy it does not hold is "
						f"worse than one that admits it holds none"
					),
				)
			)
		if citation.needs_archive:
			gaps.append(
				CitationGap(
					kind="unarchived",
					subject=citation.key,
					detail=f"{citation.work} ({citation.url}) has no local copy",
				)
			)

	# Forward: every citation must reach an entry. A citation naming a work the
	# register does not hold is the finding the register exists to make -- it is
	# a load-bearing claim tracing to a URL, which is exactly what the rule
	# forbids.
	for owner, reference in references:
		if not any(citation.resolves(reference) for citation in citations):
			gaps.append(
				CitationGap(
					kind="unregistered",
					subject=owner,
					detail=f"cites {reference!r}, which no register row resolves",
				)
			)

	# Reverse: every entry must be reached. An entry no citation reaches is
	# either a work the tree stopped citing or a row added and never wired.
	for citation in citations:
		if not any(citation.resolves(reference) for _, reference in references):
			gaps.append(
				CitationGap(
					kind="unreachable",
					subject=citation.key,
					detail=(
						f"{citation.work} is registered and cited by nothing; "
						f"either the citation was removed or the row was never wired"
					),
				)
			)

	return CitationReport(citations=citations, gaps=tuple(gaps))


def _equation_references() -> tuple[tuple[str, str], ...]:
	"""``(equation_id, reference)`` for every equation declaring one.

	Reads the YAML rather than a loaded graph, so the register can be checked
	without validating the whole library -- the same reason
	``translate._read_default_config`` reads its file rather than calling
	``load_config``.
	"""
	import yaml

	path = REPO / "config" / "prg.yaml"
	if not path.is_file():
		return ()
	document = yaml.safe_load(path.read_text()) or {}
	equations = document.get("equations") or {}
	references: list[tuple[str, str]] = []
	for equation_id, body in equations.items():
		if isinstance(body, dict) and body.get("reference"):
			references.append((equation_id, str(body["reference"])))
	return tuple(references)
