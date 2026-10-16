# SPDX-License-Identifier: MIT
"""`00-architecture.md` §6's repository layout, read as a claim rather than a sketch.

§6 draws the tree the repository is meant to have. It is labelled a *layout*
rather than a contract, and that label is exactly why it drifted: no gate reads a
directory tree in a fenced code block, so a path can be declared, never built,
and stay declared for as long as nobody looks. Measured on 2026-10-16, **eight
of the thirty-four declared paths were absent** and nothing had noticed.

The cost is not the eight paths. It is that a reader who follows the document
creates files nothing reads: `config/config.sector.yaml` is declared here and
again in `05-layer2-sector.md` §1 and §4 -- including a YAML sample headed
``# config/config.sector.yaml — extends, does not replace`` -- while the loader
opens no such file and every sector module reads the ``sector`` *section* of
`config.default.yaml`. A reader following either document writes a config the
pipeline ignores.

So the tree is parsed and every declared path is classified. A path that exists
is fine. A path that does not must be named in :data:`ABSENT`, with the reason
and what would close it -- the same discipline as `UNPRODUCED` in
`alea.reporting.producers` and `UNWIRED` in `alea.publish.views`, and for the
same reason: a named gap fails a test when it changes, so it can neither grow
silently nor be closed without the test being updated.

**A path in the tree is not always a path on disk.** ``data/{raw,interim,
processed}/`` is a brace expansion, and ``docs/`` carries two children while the
entry itself is a directory that exists. The parser expands braces and treats a
parent entry as satisfied by its own existence, so the register counts what the
document declares rather than what a glob happens to return.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

ARCHITECTURE = "docs/plans/00-architecture.md"
"""The document holding §6's tree."""

SECTION_HEADING = "## 6. Repository layout"
"""The heading the tree follows. Parsed by name, not by line number."""

ABSENT: Final[MappingProxyType[str, str]] = MappingProxyType(
	{
		"data/interim": (
			"Declared here and as `paths.interim` in `alea.config.models`, with "
			"`data/interim` in `config.default.yaml` beside it -- and read by "
			"nothing. No stage writes an intermediate and no stage reads one, "
			"because every stage writes its output to `paths.processed` and reads "
			"its inputs from `data/raw` or from another stage's processed "
			"artefact. The directory is a third tier the pipeline never adopted, "
			"so creating it would make an empty directory look like a place "
			"something lands -- and `paths.interim` would still have no reader. "
			"Closing it is a choice: drop the tier and the config key, or name the "
			"stage that needs a non-processed intermediate."
		),
	}
)
"""Declared paths that do not exist, and what would close each.

One of forty-two. The five `config/config.*.yaml` files this register first
found are *not* here, because they were never a build task: `sector`,
`predictive`, `whatif` and `reporting` are sections of `config.default.yaml`
(lines 111, 18, 70 and 153), the loader opens that file plus one environment
file, and `05-layer2-sector.md` §4's YAML sample headed
``# config/config.sector.yaml -- extends, does not replace`` documents a file
that is a section. So the tree was corrected rather than the directory created,
and the correction is in §6 where the claim was made.
"""


@dataclass(frozen=True)
class DeclaredPath:
	"""One path the layout declares, and whether the tree holds it."""

	path: str
	comment: str
	exists: bool

	@property
	def registered(self) -> bool:
		"""Whether an absent path is a named gap rather than an unnoticed one."""
		return self.path in ABSENT


@dataclass(frozen=True)
class LayoutGap:
	"""A declared path that is absent and unregistered, or registered and present."""

	path: str
	kind: str
	detail: str


def parse_layout(text: str) -> list[tuple[str, str]]:
	"""Every ``(path, comment)`` the §6 tree declares, in document order.

	The tree is drawn with box-drawing prefixes and two-space indentation. Depth
	is the indentation divided by four, because that is the width the document
	uses for one level; the last entry at a given depth is prefixed with ``└──``
	and the others with ``├──``, and both are stripped the same way.

	Brace expansions are expanded rather than returned as written: a reader of
	``data/{raw,interim,processed}/`` is being told about three directories, and
	a register that counted the string would be checking the document's
	punctuation instead of its claim.
	"""
	lines = text.splitlines()
	try:
		start = next(i for i, line in enumerate(lines) if line.strip() == SECTION_HEADING)
	except StopIteration:  # pragma: no cover - the heading is the register's anchor
		raise ValueError(f"{SECTION_HEADING!r} is not in the document; the layout moved") from None

	fence_open = None
	for index in range(start, len(lines)):
		if lines[index].startswith("```"):
			fence_open = index
			break
	if fence_open is None:  # pragma: no cover - the tree is a fenced block
		raise ValueError("§6 has no fenced block after its heading")

	declared: list[tuple[str, str]] = []
	# (depth, path) for every ancestor still open, so a nested entry composes
	# its full path from the ones above it.
	stack: list[tuple[int, str]] = []
	for line in lines[fence_open + 1 :]:
		if line.startswith("```"):
			break
		if not line.strip():
			continue
		branch = _branch_at(line)
		if branch is None:
			# The root line (`alea/`) carries no branch character. It names the
			# repository, which is the working directory, so it seeds the stack
			# with an empty prefix -- seeding it with the name would make every
			# declared path `alea/...` and every one of them absent.
			stack = [(-1, "")]
			continue
		# Depth is the width of the prefix before the branch character divided
		# by four, because each level is drawn as one four-character column --
		# either `│   ` for a level with a sibling below it or `    ` for the
		# last one. Counting leading *spaces* instead would read `│   ├──` as
		# depth 0 and collapse the whole tree onto one level.
		depth = branch // 4
		entry, _, comment = line[branch + 3 :].partition("#")
		entry = entry.strip()
		comment = comment.strip()
		if not entry:
			continue
		# A trailing `/` marks a directory. It does not change the path -- the
		# check asks whether the path exists, and a directory is a path -- but
		# it is dropped so `rust/` and `rust` are one entry rather than two.
		entry = entry.rstrip("/")
		while stack and stack[-1][0] >= depth:
			stack.pop()
		prefix = stack[-1][1] if stack else ""
		for expanded in _expand_braces(entry):
			full = f"{prefix}/{expanded}" if prefix else expanded
			declared.append((full, comment))
		stack.append((depth, f"{prefix}/{entry}" if prefix else entry))
	return declared


def _branch_at(line: str) -> int | None:
	"""Index of the ``├──``/``└──`` prefix, or ``None`` for the root line.

	``find``, and the *first* hit: a deeper level's continuation is drawn with
	``│``, which is not a branch character, so an entry line carries exactly one
	-- at its own position. Taking the last instead would follow a comment that
	happens to quote a tree.
	"""
	indexes = [i for i in (line.find("├──"), line.find("└──")) if i >= 0]
	return min(indexes) if indexes else None


def _expand_braces(entry: str) -> list[str]:
	"""``data/{raw,interim,processed}/`` becomes the three paths it names."""
	if "{" not in entry or "}" not in entry:
		return [entry]
	head, _, rest = entry.partition("{")
	body, _, tail = rest.partition("}")
	return [f"{head}{option}{tail}" for option in body.split(",")]


def layout_gaps(
	declared: list[tuple[str, str]],
	exists,
) -> list[LayoutGap]:
	"""The two ways a layout drifts: an unregistered absence, a stale registration.

	``exists`` is a predicate rather than a root, so the check can be driven from
	a fixture without a repository. Both directions matter: an absence nobody
	registered is the defect the gate exists for, and a registration for a path
	that has since been built is a register that would report a closed gap
	forever -- the state in which a reader stops believing it.
	"""
	gaps: list[LayoutGap] = []
	for path, _ in declared:
		present = bool(exists(path))
		if not present and path not in ABSENT:
			gaps.append(
				LayoutGap(
					path=path,
					kind="absent",
					detail=(
						f"§6 declares {path!r} and the tree does not hold it, and "
						f"it is not in ABSENT; either build it or name why not"
					),
				)
			)
		elif present and path in ABSENT:
			gaps.append(
				LayoutGap(
					path=path,
					kind="stale",
					detail=(
						f"§6 declares {path!r} and it now exists, so its ABSENT "
						f"entry is stale and would report a closed gap forever"
					),
				)
			)
	for path in ABSENT:
		if path not in {p for p, _ in declared}:
			gaps.append(
				LayoutGap(
					path=path,
					kind="orphan",
					detail=(
						f"{path!r} is in ABSENT and §6 no longer declares it; the "
						f"registration outlived the declaration"
					),
				)
			)
	return sorted(gaps, key=lambda gap: (gap.kind, gap.path))


__all__ = [
	"ABSENT",
	"ARCHITECTURE",
	"SECTION_HEADING",
	"DeclaredPath",
	"LayoutGap",
	"layout_gaps",
	"parse_layout",
]
