# SPDX-License-Identifier: MIT
"""`00-architecture.md` §6's repository layout, checked against the tree.

§6 draws the layout and labels it a sketch, which is why it drifted: **no gate
reads a directory tree in a fenced code block**, so a path can be declared, never
built, and stay declared indefinitely. Measured 2026-10-16, seven of the declared
paths were absent and nothing had noticed.

The cost is not the seven paths. It is that a reader who follows the document
builds something nothing reads. `config/config.sector.yaml` was declared in §6
*and* in `05-layer2-sector.md` §1 and §4 -- the latter with a YAML sample headed
`# config/config.sector.yaml — extends, does not replace` -- while `sector` is a
*section* of `config.default.yaml` at line 111 and the loader opens exactly two
files. A reader following either document wrote a config the pipeline ignored.

Four things are checked:

1. **The parser reads the document it claims to read.** The count, the brace
   expansion, and the nested composition are asserted against the real §6, so a
   parser that silently returns nothing fails here rather than passing every
   absence check vacuously.

2. **Every declared path exists or is a named gap.** `ABSENT` is a register in
   the shape of `UNPRODUCED` and `UNWIRED`: a gap with a reason and a closer, so
   the set can neither grow silently nor be closed without this file changing.

3. **A registration cannot go stale.** A path in `ABSENT` that now exists is a
   failure too -- a register that reports a closed gap forever is one a reader
   stops believing, which is worse than no register.

4. **The gate is watched failing.** The canary plants a declared path that does
   not exist into the *document*, which is the input the gate reads, and asserts
   the gate notices.
"""

from __future__ import annotations

import pytest

from alea.quality.layout import (
	ABSENT,
	ARCHITECTURE,
	SECTION_HEADING,
	layout_gaps,
	parse_layout,
)
from tests.ci.canaries import REPO, planted, probe_exit_code

PLAN = REPO / ARCHITECTURE


def _declared() -> list[tuple[str, str]]:
	return parse_layout(PLAN.read_text())


def _exists(path: str) -> bool:
	return (REPO / path).exists()


def test_the_parser_reads_the_tree_the_document_draws():
	"""The anchor. A parser that returns nothing passes every absence check.

	§6 declares 37 paths once braces are expanded. The count is pinned as a
	literal rather than derived from the parse, because a count computed from the
	thing it counts moves with it -- and it did: this read 42 while the tree still
	declared the five `config.*.yaml` files, and caught their removal.
	"""
	declared = _declared()
	assert len(declared) == 37, f"§6 declares {len(declared)} paths, not 37"
	paths = {path for path, _ in declared}
	for expected in (
		"Cargo.toml",
		"config/config.default.yaml",
		"config/scenarios",
		"data/raw",
		"data/interim",
		"data/processed",
		"reports/annual",
		"docs/plans",
		"docs/research",
		"spec",
	):
		assert expected in paths, f"the parser lost {expected!r} from §6"


def test_the_root_line_is_the_repository_not_a_path():
	"""`alea/` is the working directory; prefixing with it makes all 42 absent."""
	paths = {path for path, _ in _declared()}
	assert not any(p.startswith("alea/") for p in paths), (
		"the root line leaked into the paths, so every declared path would be "
		"absent and the gate would fail for its own reason"
	)


def test_every_declared_path_exists_or_is_a_named_gap():
	"""The gate. One direction: an absence nobody registered."""
	gaps = [g for g in layout_gaps(_declared(), _exists) if g.kind == "absent"]
	assert not gaps, "\n".join(g.detail for g in gaps)


def test_no_registration_outlived_the_gap_it_names():
	"""The other direction: a path that was built but is still registered."""
	stale = [g for g in layout_gaps(_declared(), _exists) if g.kind != "absent"]
	assert not stale, "\n".join(g.detail for g in stale)


def test_the_absent_register_names_what_would_close_each_gap():
	"""A gap with no closer is a shrug. The register is checked for the closer."""
	assert ABSENT, "the register is empty; §6 declares at least one absent path"
	for path, reason in ABSENT.items():
		assert reason.strip(), f"{path!r} is registered with no reason"
		assert "Clos" in reason or "clos" in reason, (
			f"{path!r} does not say what would close it, so the next reader "
			f"cannot act on the registration"
		)


def test_the_config_sections_are_sections_not_files():
	"""The correction §6 needed, asserted so the tree cannot drift back.

	`predictive`, `whatif`, `sector` and `reporting` are top-level keys of
	`config.default.yaml`. Declaring them as separate files -- which §6 did, and
	which `05-layer2-sector.md` §4 still samples -- tells a reader to create a
	config the loader never opens.
	"""
	import yaml

	sections = set(yaml.safe_load((REPO / "config" / "config.default.yaml").read_text()))
	for name in ("sector", "predictive", "whatif", "reporting"):
		assert name in sections, f"{name!r} is not a section of config.default.yaml"
		declared = (REPO / "config" / f"config.{name}.yaml")
		assert not declared.exists(), (
			f"config/config.{name}.yaml now exists; either the loader reads it or "
			f"the tree should not declare it"
		)


def test_the_loader_opens_only_the_files_the_tree_declares():
	"""The claim the correction rests on, checked at its source.

	Two entry points: the default config and a named scenario. There is no
	`config.sector.yaml` path to build, because `sector` is a key inside the
	default file.
	"""
	from alea.config import paths

	assert paths.default_config_path().name == "config.default.yaml"
	assert paths.scenario_path("continental").name == "continental.yaml"
	assert paths.scenario_path("continental").parent.name == "scenarios"


def test_a_layout_gap_is_reported_for_a_path_the_tree_lacks():
	"""`layout_gaps` driven from a literal, not from the repository.

	The gate above reads the real tree, so it passes for the real reason and for
	no other. This one pins the *logic*: an unregistered absence is an `absent`
	gap, a registration that has been built is a `stale` one. `data/interim` is
	the live registration, so it is the one the fixture names.
	"""
	declared = [("here", ""), ("gone", ""), ("data/interim", "")]
	gaps = layout_gaps(declared, lambda p: p != "gone")
	kinds = {g.path: g.kind for g in gaps}
	assert kinds["gone"] == "absent"
	assert "here" not in kinds
	assert kinds["data/interim"] == "stale", (
		"a registered path that now exists must be reported stale; otherwise the "
		"register reports a closed gap forever"
	)


def test_the_gate_notices_a_path_the_document_declares_and_the_tree_lacks():
	"""The canary for ``test_every_declared_path_exists_or_is_a_named_gap``.

	The mutation is in the *document*, which is the gate's input, rather than in
	the register the gate reads -- so it is disjoint from what the predicate
	looks for: the predicate compares the tree against the document, and the
	mutation changes the document. A canary that added an `ABSENT` entry instead
	would be testing the register's spelling, not the gate's reading.
	"""
	shipped = "└── spec/                       # the specification (authoritative for intent)"
	broken = (
		"├── phantom/                    # canary: declared, never built\n"
		"└── spec/                       # the specification (authoritative for intent)"
	)
	node = "tests/ci/test_layout_register.py::test_every_declared_path_exists_or_is_a_named_gap"
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)

	assert probe_exit_code(program) == 0, "the gate was already failing"
	with planted(PLAN, shipped, broken):
		assert probe_exit_code(program) != 0, (
			"§6 declares a directory that does not exist and the gate passed; it "
			"is not reading the tree"
		)
	assert probe_exit_code(program) == 0, "the gate did not recover"


def test_the_parser_refuses_a_document_that_moved_its_heading():
	"""A parser that cannot find §6 must raise, not return an empty list.

	Returning `[]` would make every absence check pass on a document whose
	heading was renamed -- the failure mode that reads as success.
	"""
	with pytest.raises(ValueError, match="is not in the document"):
		parse_layout("# Some other document\n\nno layout here\n")
	with pytest.raises(ValueError, match="no fenced block"):
		parse_layout(f"{SECTION_HEADING}\n\nno fence follows\n")


def test_the_brace_expansion_names_three_data_tiers():
	"""`data/{raw,interim,processed}/` is three paths, not one string."""
	text = (
		f"{SECTION_HEADING}\n\n```\nalea/\n├── data/{{raw,interim,processed}}/\n```\n"
	)
	assert [p for p, _ in parse_layout(text)] == [
		"data/raw",
		"data/interim",
		"data/processed",
	]


def test_a_nested_entry_composes_its_path_from_its_ancestors():
	"""`tests/ci/canaries` is one path, drawn across two levels of indentation."""
	text = (
		f"{SECTION_HEADING}\n\n```\nalea/\n"
		"├── tests/\n"
		"│   ├── ci/          # autodiscovery path\n"
		"│   │   └── canaries/   # AD-10\n"
		"│   └── data/        # fixtures\n"
		"└── spec/\n"
		"```\n"
	)
	assert [p for p, _ in parse_layout(text)] == [
		"tests",
		"tests/ci",
		"tests/ci/canaries",
		"tests/data",
		"spec",
	]
