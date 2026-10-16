# SPDX-License-Identifier: MIT
"""Every load-bearing citation resolves to a registered work.

The gate for ``alea.provenance.citations``. It exists because the library's nine
equation citations were prose and nothing else: parsed, validated, served at
four doors, and joined to nothing. A citation naming a work the register does
not hold is a load-bearing claim pointing at a URL, which is the thing the
archive rule forbids -- and until this file there was no way to tell such a
citation from one naming a real work.
"""

from __future__ import annotations

from pathlib import Path

from alea.provenance.citations import (
	INDEX_PATH,
	CitationGap,
	citation_report,
	read_index,
)


def test_every_citation_resolves_to_a_registered_work():
	"""The forward direction: no citation points at nothing.

	``unregistered`` is the gap this test is named for. The other three kinds
	are asserted by their own tests below, and separating them matters: this one
	fails when someone writes a new equation citing a paper and does not add the
	row, which is a different mistake from a row whose copy is missing.
	"""
	report = citation_report()
	unregistered = [g for g in report.gaps if g.kind == "unregistered"]
	assert not unregistered, (
		"citation(s) resolving to no register row: "
		+ "; ".join(g.detail for g in unregistered)
	)


def test_every_registered_work_is_reached_by_a_citation():
	"""The reverse direction: no row is dead weight.

	An entry no citation reaches is either a work the tree stopped citing -- and
	the row should go -- or a row someone added and never wired. Both are
	findings, and the reverse check is the half a register usually omits, which
	is how a register grows rows nobody reads.
	"""
	report = citation_report()
	unreachable = [g for g in report.gaps if g.kind == "unreachable"]
	assert not unreachable, (
		"register row(s) cited by nothing: "
		+ "; ".join(g.detail for g in unreachable)
	)


def test_a_row_claiming_a_copy_holds_one():
	"""``missing_file``: a register claiming a copy it does not hold.

	This is the one gap kind that is always a defect rather than a state of the
	world. A row saying ``sources/archive/x.pdf`` is a claim that a clean clone
	carries the evidence; if the file is absent the claim is false, and a false
	claim is worse than an honest ``""``.
	"""
	report = citation_report()
	missing = [g for g in report.gaps if g.kind == "missing_file"]
	assert not missing, (
		"register claims copies that are not on disk: "
		+ "; ".join(g.detail for g in missing)
	)


def test_the_archived_count_is_not_zero():
	"""A register that archives nothing is a bibliography.

	Stated as its own gate because ``0 archived, 0 defects`` passes every check
	above: with no ``archived`` path in any row there is no ``missing_file`` to
	find, and a register of twelve unarchived works would report clean. The
	assertion is that the mechanism has been exercised at least once, so a
	regression that silently emptied the archive column fails here.

	It is deliberately weak -- *at least one*, not a count. Pinning the exact
	number would make adding a second archive a test edit, and the property
	worth holding is that the column is live, not how many rows carry it.
	"""
	report = citation_report()
	assert report.archived, (
		f"no citation in {INDEX_PATH.name} is archived on disk; a register with "
		f"no copies is a bibliography, and the empty state would then be "
		f"indistinguishable from a broken one"
	)


def test_every_archived_copy_has_a_recorded_digest():
	"""A digest is what makes an archived row evidence rather than a pointer.

	A re-download of the same URL is not necessarily the same bytes -- a
	publisher reissues a report under the same filename -- so a register that
	records only a path cannot tell a replaced copy from the original. The
	document tells the reader to record the digest; this is the gate that makes
	the instruction real, because an instruction nothing checks is a comment.

	**The digest is recomputed, not compared to a constant.** Pinning
	``b04c0d…`` in this file would make the test fail the day a publisher
	reissues the report *and* the copy is deliberately refreshed -- a test
	that forbids legitimate work. What it asserts is that the row and the file
	agree, which is the property that matters.
	"""
	import hashlib

	text = INDEX_PATH.read_text()
	digests: dict[str, str] = {}
	for line in text.splitlines():
		if not line.startswith("| sources/archive/"):
			continue
		cells = [cell.strip() for cell in line.strip("|").split("|")]
		if len(cells) == 2:
			digests[cells[0]] = cells[1]

	archived = [c for c in read_index() if c.archive_path is not None]
	assert archived, "no archived rows; this test asserts their digests"
	for citation in archived:
		assert citation.archive_path is not None
		path = citation.archive_path
		relative = citation.archived
		assert relative in digests, (
			f"{citation.key} is archived at {relative} with no digest row; a "
			f"copy whose bytes are not recorded cannot be told from a replaced one"
		)
		actual = hashlib.sha256(path.read_bytes()).hexdigest()
		assert digests[relative] == actual, (
			f"{relative}: recorded digest {digests[relative]} does not match the "
			f"file's {actual}"
		)


def test_the_register_header_is_the_schema():
	"""A changed column order fails rather than shifting every value.

	A row is parsed by position, so a reordered or misspelled heading moves
	values between fields silently -- a URL read as a licence, an archive path
	read as a citation. The parser raises on it, and this test asserts the
	shipped file parses.
	"""
	citations = read_index()
	assert citations, f"{INDEX_PATH} parsed to zero rows"


def test_every_work_names_a_custodian_or_declares_itself_a_derivation():
	"""A row is either attributed or explicitly a textbook result.

	The distinction is the register's honest half. Five citations name a
	*derivation* -- the annuity formula, the WACC identity, the swing equation
	-- and recording them as unattributed works would read as five missing
	citations. Recording them as ``n/a`` says what they are.
	"""
	for citation in read_index():
		if citation.archived == "n/a":
			assert not citation.custodian, (
				f"{citation.key} is a derivation and names a custodian "
				f"({citation.custodian!r}); a textbook result attributed to an "
				f"institution is a fabricated source"
			)
			continue
		assert citation.custodian, (
			f"{citation.key} names no custodian and is not marked 'n/a'; a work "
			f"with no attributable source is either a derivation or a row that "
			f"is not finished"
		)


def test_an_unregistered_citation_is_reported():
	"""The predicate, against a constructed pair rather than the shipped one.

	Driven directly so the test cannot be satisfied by the tree happening to
	have no gap: it hands ``citation_report`` a reference no row resolves and
	asserts the gap comes back. Without this, every test above passes on a
	version of the report that returns no gaps at all -- the gate would be
	green against a function that never looks.
	"""
	report = citation_report(
		references=(("planted_equation", "cf. Nonexistent Working Paper 1999"),)
	)
	kinds = {g.kind for g in report.gaps}
	assert "unregistered" in kinds, (
		"a reference resolving to no row was not reported; the forward check "
		"is not looking"
	)
	assert any(
		g.subject == "planted_equation" for g in report.gaps
	), "the gap did not name the equation that made the unresolvable citation"


def test_an_unreachable_row_is_reported():
	"""The reverse predicate, driven the same way.

	Hands the report a reference set that reaches nothing and asserts every
	registered row comes back unreachable. This is the direction a register
	usually omits, so it is the one most likely to be written as a no-op.
	"""
	report = citation_report(references=(("planted_equation", "nothing at all"),))
	unreachable = [g for g in report.gaps if g.kind == "unreachable"]
	assert len(unreachable) == report.registered, (
		f"a reference set reaching nothing should mark all "
		f"{report.registered} row(s) unreachable, got {len(unreachable)}"
	)


def test_a_claimed_copy_that_is_absent_is_reported(tmp_path: Path):
	"""``missing_file`` driven through the report, not through the dataclass.

	The shipped register has no missing file, so this gap kind has no live
	instance to observe and the branch would never run. A scratch index with a
	ghost row drives it -- and driving ``citation_report`` rather than asserting
	the dataclass's own property is the difference between testing the gate and
	testing a getter. The first version of this test did the latter and would
	have passed against a report that never checked the file at all.
	"""
	index = tmp_path / "INDEX.md"
	index.write_text(
		"## Works\n\n"
		"| key | work | custodian | year | url | licence | archived | cites |\n"
		"|---|---|---|---|---|---|---|---|\n"
		"| ghost | A Work Whose Copy Is Not Here | Nobody | 2000 | "
		"https://example.invalid/ | unknown | "
		"sources/archive/definitely-not-a-file.pdf | Ghost |\n"
	)
	report = citation_report(path=index, references=(("planted", "cf. Ghost"),))
	missing = [g for g in report.gaps if g.kind == "missing_file"]
	assert missing, (
		"a row claiming an archive path that is not a file was not reported; "
		"the register can claim a copy it does not hold"
	)
	assert missing[0].subject == "ghost"
	# And the same row with an honest empty cell is *not* a missing file, so the
	# branch is discriminating rather than firing on every unarchived row.
	index.write_text(index.read_text().replace(
		"sources/archive/definitely-not-a-file.pdf", ""
	))
	honest = citation_report(path=index, references=(("planted", "cf. Ghost"),))
	assert not [g for g in honest.gaps if g.kind == "missing_file"], (
		"an empty archived cell was reported as a missing file"
	)
	assert [g for g in honest.gaps if g.kind == "unarchived"], (
		"an empty archived cell should be reported as unarchived"
	)


def test_a_derivation_is_not_counted_as_unarchived():
	"""``n/a`` is excluded from the unarchived count, and that is the point.

	Five of the register's ten rows are textbook results. Counting them as
	unarchived works would inflate the register's own gap count by five entries
	nobody can ever close -- a report that cannot reach zero is a report a
	reader stops reading.
	"""
	derivations = [c for c in read_index() if c.archived == "n/a"]
	assert derivations, "no derivation rows; this test asserts their treatment"
	for citation in derivations:
		assert not citation.needs_archive, (
			f"{citation.key} is marked 'n/a' and reported as needing an archive"
		)
	report = citation_report()
	unarchived = {g.subject for g in report.gaps if g.kind == "unarchived"}
	assert not unarchived & {c.key for c in derivations}, (
		f"derivation(s) counted as unarchived: {unarchived & {c.key for c in derivations}}"
	)


def test_the_gap_kinds_are_the_ones_the_report_can_emit():
	"""The kind vocabulary is closed.

	A gap kind nobody handles is a finding that reaches no reader. Asserting
	the set against the module's own literal keeps a new kind from being added
	to the emitter without a reader noticing.
	"""
	report = citation_report(
		references=(("planted", "nothing resolves this"),)
	)
	kinds = {g.kind for g in report.gaps}
	assert kinds <= {"unregistered", "unarchived", "unreachable", "missing_file"}, (
		f"unexpected gap kind(s): {kinds}"
	)
	assert isinstance(report.gaps[0], CitationGap)


def test_the_register_reaches_a_door():
	"""The register is served, not only gated.

	A register a client cannot read is the declared-is-not-produced class this
	repository keeps recording: ``GET /prg/equations`` serves each equation's
	``reference`` as prose, and a client rendering it cannot tell a citation
	naming a real work from one naming a work nobody archived. The route is the
	difference, so it is asserted at the door rather than at the function.

	Driven through the real application over ``httpx.ASGITransport`` rather than
	a mock, because a route's defects are path strings and payload shapes -- the
	exact things a mock cannot see.
	"""
	from fastapi.testclient import TestClient

	from alea.api.app import API_PREFIX, create_app
	from alea.config.loader import load_config

	# The prefix is read from the app rather than written here. The first
	# version of this test hardcoded `/prg/citations` and got a 404, because
	# every router is mounted under `API_PREFIX` -- a defect the door test found
	# and a mock would not have.
	url = f"{API_PREFIX}/prg/citations"

	# `with TestClient(...)` enters the lifespan, which connects the stores.
	# Without it the route answers 503 rather than 404 -- a second finding the
	# first version of this test produced, and the reason it drives the real app
	# instead of calling the route function.
	with TestClient(create_app(load_config())) as client:
		response = client.get(url)
	assert response.status_code == 200, (
		f"GET {url} returned {response.status_code}: {response.text[:300]}"
	)
	payload = response.json()
	assert payload["registered"] == len(read_index()), (
		"the route's registered count disagrees with the register's own rows"
	)
	assert payload["archived"] >= 1, (
		"the route reports no archived copies; the field is not reading the "
		"report's archived property"
	)
	# The gaps travel with the payload, because the counts alone cannot tell a
	# client *which* citation is unresolved.
	assert isinstance(payload["gaps"], list)
	assert payload["summary"], "the route serves no summary line"
