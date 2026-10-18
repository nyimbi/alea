# SPDX-License-Identifier: MIT
"""The parameter catalog as data, and the graph's join onto it.

WHAT THESE TESTS ARE FOR. ``docs/params.md`` is the document three
``ParameterNode`` fields were copied from, and until this reader existed no
code in ``src/`` had opened it. So the tests come in three groups and they
answer three different questions:

1. **Does the reader still parse the document?** A markdown table is a format
   nobody versioned, and a reader that silently returns zero rows is a register
   reporting a clean catalog.
2. **What does the catalog claim, and does it agree with itself?** The title,
   the category headings and the table state three different numbers, and each
   is consistent with the line it sits on -- which is exactly why nothing
   caught it. These tests pin all three so a document edit has to move them
   together.
3. **Does the graph agree with the catalog where the two name the same
   parameter?** Five of the six agree and one has drifted. That drift is the
   finding, and pinning it by name is what stops it being rediscovered as a
   surprise.

WHY THE CLAIMS ARE PINNED AS LITERALS. ``CATALOG_TITLE_COUNT`` is 784 and the
rows number 824. A test asserting ``summary.title_count == summary.row_count``
would fail -- which is the point -- but a test asserting ``row_count ==
len(read_catalog())`` would pass against any document, including one that lost
half its rows. The two numbers are pinned as the *claim* and the *witness*
separately, so an edit to the document fails here and names which of the two it
moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alea.config.paths import repo_root
from alea.prg.catalog import (
	CATALOG_PATH,
	CATALOG_STATUS_LEGEND,
	CATALOG_TITLE_COUNT,
	CLASSIFICATION_FIELDS,
	catalog_report,
	category_counts,
	contradictions,
	graph_join,
	read_catalog,
	status_join,
	summary,
	title_count,
)
from alea.prg.graph import ParameterGraph, load_graph

PRG_PATH = repo_root() / "config" / "prg.yaml"


@pytest.fixture
def graph() -> ParameterGraph:
	return load_graph(PRG_PATH)


# ---------------------------------------------------------------------------
# The reader: does it still parse the document?
# ---------------------------------------------------------------------------


def test_the_catalog_is_where_the_register_says_it_is():
	"""A moved document must break the reader, not empty the register.

	The register degrades to ``readable: false`` when the file is absent, which
	is right for a scratch tree and wrong for the shipped one: a catalog that
	moved would report "not readable" on every summary and a reader would learn
	to ignore the line. Asserted on the path rather than through the report, so
	the failure names the file.
	"""
	assert (repo_root() / CATALOG_PATH).exists(), (
		f"{CATALOG_PATH} is not in the tree; the graph's `status`, `users` and "
		f"`source` fields take their referent from it"
	)


def test_every_row_parses_with_all_nine_columns():
	"""Nine cells per row, and the parameter cell is one identifier.

	A cell containing an unescaped pipe shifts every column after it, which
	would make the Status column read as the Users column and the register
	report a vocabulary of user names as statuses. The reader refuses that;
	this asserts it never has to on the shipped document.
	"""
	rows = read_catalog()
	assert len(rows) > 700, len(rows)
	for row in rows:
		assert row.name, row
		assert row.status in CATALOG_STATUS_LEGEND, (
			f"row {row.id} ({row.name}) carries status {row.status!r}, which is "
			f"not one of the legend's {sorted(CATALOG_STATUS_LEGEND)}"
		)
		assert row.priority in {"P1", "P2", "P3"}, (row.id, row.priority)


def test_the_legend_covers_every_status_the_document_uses():
	"""The mapping is total over what the table actually contains.

	A glyph the legend does not carry is a row whose status cannot be
	translated, and ``status_join`` would report it as disagreeing with the
	graph when the truth is that the catalog added a fourth state. Asserted
	against the rows rather than against the legend's own keys.
	"""
	used = {row.status for row in read_catalog()}
	assert used == set(CATALOG_STATUS_LEGEND), (
		f"the table uses {sorted(used)} and the legend declares "
		f"{sorted(CATALOG_STATUS_LEGEND)}"
	)


def test_a_row_with_a_shifted_column_is_refused(tmp_path: Path):
	"""The guard, exercised: an unescaped pipe is a hard failure.

	The document has no such cell, so the guard has never fired on real input
	and a check that has never run is not a check. This plants one.
	"""
	document = tmp_path / "params.md"
	document.write_text(
		"| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |\n"
		"|---|---|---|---|---|---|---|---|---|\n"
		"| 1.1 | Demand | `demand_growth_rate` | Growth | a | b | c | d | P1 |\n"
		"| 1.2 | Demand | `peak_demand_multiplier` | a | b | c | d | P1 |\n"
	)
	with pytest.raises(ValueError, match="cells where the header declares"):
		read_catalog(document)


def test_a_row_whose_parameter_cell_is_not_an_identifier_is_refused(tmp_path: Path):
	"""The other guard: the parameter column was restructured.

	A cell like ``"demand growth rate"`` -- prose rather than a backticked
	identifier -- means the table's shape changed, and indexing it as a name
	would join on a sentence.
	"""
	document = tmp_path / "params.md"
	document.write_text(
		"| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |\n"
		"|---|---|---|---|---|---|---|---|---|\n"
		"| 1.1 | Demand | demand growth rate | Growth | a | b | 🔨 | All | P1 |\n"
	)
	with pytest.raises(ValueError, match=r"single backticked identifier"):
		read_catalog(document)


# ---------------------------------------------------------------------------
# The catalog's own claims, and whether it agrees with itself
# ---------------------------------------------------------------------------


def test_the_three_counts_the_document_states():
	"""784 in the title, 824 in the headings, 824 rows over 787 names.

	The finding, pinned. Each number is correct about the thing it describes --
	the headings sum to the rows exactly, so the table is internally tidy --
	and the title disagrees with both by 40. A test that asserted only the
	first would pass on a document that had lost its table; one that asserted
	only the rows would pass on a title of any value.
	"""
	result = summary()
	assert result.title_count == CATALOG_TITLE_COUNT == 784
	assert result.declared_total == 824, result.declared_total
	assert result.row_count == 824, result.row_count
	assert result.distinct_names == 787, result.distinct_names
	assert result.surplus_over_title() == 40, result.surplus_over_title()


def test_the_category_headings_agree_with_their_own_rows():
	"""28 headings, each declaring the number of rows that follow it.

	This is the half of the document that *is* consistent, and asserting it
	separates two findings a single total would merge: the table is tidy, and
	the title is wrong. A heading disagreeing with its rows would be a third
	problem, and it would show up here rather than inside the 40.
	"""
	counts = category_counts()
	assert len(counts) == 28, len(counts)
	disagreeing = {
		name: pair for name, pair in counts.items() if pair[0] != pair[1]
	}
	assert not disagreeing, (
		f"these headings declare a row count their section does not hold: "
		f"{disagreeing}"
	)
	assert sum(declared for declared, _ in counts.values()) == 824


def test_the_repeated_names_are_counted_and_mostly_benign():
	"""35 names on more than one row, and 11 of those differ somewhere.

	Duplicates are expected: the catalog is organised by *concern*, so a
	quantity relevant to two concerns is listed under both. What the register
	must not do is call all 35 a defect -- that would be noise -- or call all
	35 benign, which would hide the two that contradict each other.
	"""
	result = summary()
	assert len(result.repeated_names) == 35, result.repeated_names
	assert all(n > 1 for _, n in result.repeated_names)
	# The most-repeated name is a genuine four-way cross-listing, and its rows
	# agree on every classification column.
	assert dict(result.repeated_names)["carbon_finance_share"] == 4


def test_only_two_duplicates_contradict_each_other():
	"""``planned_outage_rate`` on priority and ``resettlement_costs`` on users.

	The register's predicate, and the distinction that keeps it useful. Nine
	further duplicates differ only in their *prose* columns, which is by design:
	``forced_outage_rate``'s algorithm reads "Stochastic outage model" under
	Outage and "Forced outage rate" under Operational, and both are true
	statements about where a reader finds it. A classification column is an
	assertion about the parameter instead -- what state it is in, who needs it,
	when -- and two rows disagreeing there is one document contradicting
	itself.
	"""
	conflicts = contradictions(classification_only=True)
	assert set(conflicts) == {"planned_outage_rate", "resettlement_costs"}, sorted(
		conflicts
	)
	assert conflicts["planned_outage_rate"].classification == ("priority",)
	assert conflicts["resettlement_costs"].classification == ("users",)

	# And the wider register is strictly larger, so the split is doing work
	# rather than being a rename of the same set.
	all_conflicts = contradictions()
	assert len(all_conflicts) == 11, sorted(all_conflicts)
	assert set(conflicts) < set(all_conflicts)


def test_the_prose_only_conflicts_are_kept_apart_from_the_classification_ones():
	"""A prose-only disagreement is reported and is not a conflict.

	``heat_pump_adoption``'s algorithm cell differs between its two rows and
	its status, users and priority do not. That row must appear in the wide
	register -- it is a real difference a reader might want -- and must not
	appear in the narrow one, or the narrow one is just the wide one with a
	shorter name.
	"""
	all_conflicts = contradictions()
	conflicts = contradictions(classification_only=True)
	prose_only = {
		name: conflict
		for name, conflict in all_conflicts.items()
		if not conflict.is_classification_conflict
	}
	assert prose_only, "no prose-only disagreement; the split is untested"
	assert "heat_pump_adoption" in prose_only
	assert prose_only["heat_pump_adoption"].prose == ("algorithm",)
	assert not set(prose_only) & set(conflicts)
	# Every classification field a conflict names is one of the three.
	for conflict in all_conflicts.values():
		assert set(conflict.classification) <= set(CLASSIFICATION_FIELDS)


# ---------------------------------------------------------------------------
# The join onto the graph, and the one node that has drifted
# ---------------------------------------------------------------------------


def test_the_join_is_every_node_the_catalog_names(graph: ParameterGraph):
	"""787 nodes joined, and the join is on the identifier.

	This was six nodes before the catalog join, and the six *were* the finding:
	the catalog is technology- and concern-specific and the graph was a
	country aggregate, so the two named the same quantity rarely and the same
	*string* six times. The expansion inverted that -- the graph's node names
	are now the catalog's own -- so the register covers all 787 distinct names,
	and the six are a subset rather than the whole.

	The register still does not claim the 787 are the same *quantity* as their
	catalog rows; nothing here could verify that. It claims the same string,
	which is what a join on the identifier can honestly report.
	"""
	joined = graph_join(graph=graph)
	assert len(joined) == 787, len(joined)
	# The six the register was built on are still in it, by name. Pinned so a
	# join that quietly stopped matching them is a failure rather than a
	# smaller number.
	assert {
		"cost_of_debt",
		"cost_of_equity",
		"direct_jobs",
		"discount_rate",
		"equity_return_target",
		"offtake_risk_premium",
	} <= set(joined)
	for name, rows in joined.items():
		assert name in graph.nodes
		assert rows, name


def test_five_nodes_agree_with_the_catalog_and_one_has_drifted(
	graph: ParameterGraph,
):
	"""``equity_return_target``: the graph says ``to_build``, the catalog ``🔗``.

	The live finding, and the reason the reader was worth building. The graph's
	labels were copied from the catalog's legend, and on the one node where the
	two documents name the same parameter *and* the catalog is self-consistent
	about it, they disagree: the catalog says the capability exists externally
	and needs integrating, the graph says it needs building. Those are different
	pieces of work.

	Both catalog rows for this name say ``🔗``, so this is not an artefact of
	which row the join read -- which is the failure mode a first-row join would
	have. Pinned by name so a fix has to move this test.

	WHY THE PROMOTION LEFT THREE DISAGREEING RATHER THAN ONE. The generated
	batches corrected two nodes into their canonical forms and the catalog
	cannot follow them: ``cross_border_trading`` is a duplicate of
	``cross_border_trade_allowed`` and ``demand_growth_rate`` of
	``demand_growth``, and the graph marks each ``deprecated`` with the
	replacement named on the node -- which is the field's own contract. The
	catalog's legend has three glyphs (✅ 🔨 🔗) and no way to say a row should
	not exist, so these two disagreements are the register doing its job on a
	drift the catalog format cannot absorb. Batch 20's coupling then promoted
	twenty more parameters onto the graph as ``existing`` -- the finance,
	outage and degradation batches landed them as defined -- while the
	catalog still marks them ``to_build`` (``integrate`` for
	``capacity_price``, ``cbam_price``, ``steel_production``), taking the
	register to 23 disagreements, each one the register doing its job on a
	catalog the generator has outpaced. Pinned beside
	``equity_return_target`` with the reason, so the next landed batch moves
	this test rather than passing silently.
	"""
	joins = {join.parameter: join for join in status_join(graph=graph)}
	assert len(joins) == 787, len(joins)
	disagreeing = {name: join for name, join in joins.items() if not join.agrees}
	assert set(disagreeing) == {
		"blended_finance_share",
		"bond_share",
		"capacity_price",
		"carbon_finance_share",
		"cbam_price",
		"cement_production",
		"chemicals_ammonia_production",
		"commercial_bank_share",
		"construction_period",
		"cost_of_debt",
		"cross_border_trading",
		"demand_growth_rate",
		"dfi_share",
		"equity_return_target",
		"green_bond_share",
		"line_outage_duration",
		"line_outage_probability",
		"maintenance_duration",
		"net_zero_year",
		"retraining_duration",
		"solar_degradation",
		"steel_production",
		"wind_degradation",
	}, sorted(disagreeing)

	drifted = disagreeing["equity_return_target"]
	assert drifted.graph_status == "to_build", drifted.graph_status
	assert drifted.catalog_status == "integrate", drifted.catalog_status
	assert drifted.rows[0].status == "🔗"
	assert len(drifted.rows) == 2, drifted.rows
	assert {row.status for row in drifted.rows} == {"🔗"}, (
		"the two catalog rows disagree with each other about this parameter, so "
		"this test cannot say which one the graph drifted from"
	)
	assert "catalog says integrate" in drifted.describe()
	# The two deprecations carry their replacements on the node, which is what
	# makes the graph's claim actionable -- a caller can migrate.
	for name in ("cross_border_trading", "demand_growth_rate"):
		node = graph.nodes[name]
		assert node.status == "deprecated", node.status
		assert node.deprecated_by in graph.nodes, node.deprecated_by

	# The other 764 are the control: a join that reported every node as
	# disagreeing would pass the assertion above and mean nothing. The
	# expansion took the agreeing count to 786, the promotion left it at 784
	# for the two deprecations above, and batch 20 took it to 764 for the
	# twenty promotions the set above names.
	assert sum(1 for join in joins.values() if join.agrees) == 764


def test_a_node_the_catalog_does_not_name_is_absent_rather_than_guessed(
	graph: ParameterGraph,
):
	"""``peak_demand_mw`` is not ``peak_demand_multiplier``.

	The catalog carries a node by the second name; the graph by the first. A
	fuzzy join would pair them and the register would report agreement about
	two different quantities -- a false finding, which costs more than a
	missing one because it sends a reader to fix something that is not broken.
	"""
	joined = graph_join(graph=graph)
	assert "peak_demand_mw" in graph.nodes
	assert "peak_demand_mw" not in joined


# ---------------------------------------------------------------------------
# The payload, and the degraded path
# ---------------------------------------------------------------------------


def test_the_report_carries_all_three_claims_together(graph: ParameterGraph):
	"""Serving either count alone would read as a fact, not a disagreement.

	The whole reason the register is one object: ``784`` on its own is a
	specification, ``824`` on its own is a table, and the two together are the
	finding.
	"""
	report = catalog_report(graph=graph)
	assert report["readable"] is True
	assert report["title_count"] == 784
	assert report["row_count"] == 824
	assert report["declared_total"] == 824
	assert report["distinct_names"] == 787
	assert report["surplus_over_title"] == 40
	assert report["repeated_names"] == 35
	assert set(report["classification_conflicts"]) == {
		"planned_outage_rate",
		"resettlement_costs",
	}
	# Pinned to the shipped graph's own list, alphabetical as catalog_report
	# emits it: the two deprecations, equity_return_target, and the twenty
	# parameters batch 20 promoted to ``existing`` while the catalog still
	# says to_build or integrate.
	assert report["status_disagreements"] == [
		"blended_finance_share: the graph says existing and the catalog says to_build",
		"bond_share: the graph says existing and the catalog says to_build",
		"capacity_price: the graph says existing and the catalog says integrate",
		"carbon_finance_share: the graph says existing and the catalog says to_build",
		"cbam_price: the graph says existing and the catalog says integrate",
		"cement_production: the graph says existing and the catalog says to_build",
		"chemicals_ammonia_production: the graph says existing and the catalog says to_build",
		"commercial_bank_share: the graph says existing and the catalog says to_build",
		"construction_period: the graph says existing and the catalog says to_build",
		"cost_of_debt: the graph says existing and the catalog says to_build",
		"cross_border_trading: the graph says deprecated and the catalog says existing",
		"demand_growth_rate: the graph says deprecated and the catalog says to_build",
		"dfi_share: the graph says existing and the catalog says to_build",
		"equity_return_target: the graph says to_build and the catalog says integrate",
		"green_bond_share: the graph says existing and the catalog says to_build",
		"line_outage_duration: the graph says existing and the catalog says to_build",
		"line_outage_probability: the graph says existing and the catalog says to_build",
		"maintenance_duration: the graph says existing and the catalog says to_build",
		"net_zero_year: the graph says existing and the catalog says to_build",
		"retraining_duration: the graph says existing and the catalog says to_build",
		"solar_degradation: the graph says existing and the catalog says to_build",
		"steel_production: the graph says existing and the catalog says integrate",
		"wind_degradation: the graph says existing and the catalog says to_build",
	]
	assert len(report["status_join"]) == 787


def test_a_tree_with_no_catalog_says_so_rather_than_reporting_agreement(
	tmp_path: Path, graph: ParameterGraph
):
	"""``readable: false`` with a reason, because the two are the same JSON.

	An empty conflict list and a catalog nobody opened are byte-identical
	otherwise, and only one of them is good news. The same shape
	``translate.cross_layer_report`` uses for the same reason.
	"""
	report = catalog_report(path=tmp_path / "absent.md", graph=graph)
	assert report["readable"] is False
	assert "no parameter catalog" in str(report["reason"])
	assert report["classification_conflicts"] == {}
	assert report["status_disagreements"] == []
	assert report["row_count"] == 0
	# The claim is *not* served. It lives in the document, so a report that
	# could not open the document has no claim to state; serving the module's
	# expectation here would have the register asserting the contents of a file
	# it could not read, and the same key would mean two different things on
	# the two paths.
	assert report["title_count"] == 0


def test_the_title_is_read_out_of_the_document_not_served_from_the_constant(
	tmp_path: Path,
):
	"""The register's own blind spot, closed.

	``summary()`` originally returned ``CATALOG_TITLE_COUNT`` as
	``title_count``, which made the constant both the claim *and* the reported
	value: editing the document's title to any number would move nothing, and
	the 784-vs-824 finding would have been hardcoded rather than observed. This
	plants a document whose title disagrees and asserts the reader follows it.
	"""
	document = tmp_path / "params.md"
	document.write_text(
		"## Complete Single-Table Reference of All 900 Parameters, Algorithms, and Implementations\n"
		"\n"
		"| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |\n"
		"|---|---|---|---|---|---|---|---|---|\n"
		"| 1.1 | Demand | `demand_growth_rate` | Growth | a | b | 🔨 | All | P1 |\n"
	)
	assert title_count(document) == 900
	assert summary(document).title_count == 900
	assert summary(document).surplus_over_title() == 1 - 900
	# And the constant is unmoved, which is what makes it an assertion rather
	# than a copy: the test above this one compares the two.
	assert CATALOG_TITLE_COUNT == 784


def test_a_title_with_no_count_is_refused_rather_than_defaulted(tmp_path: Path):
	"""A heading that no longer states a number cannot state the finding.

	Returning 784 here would have the register report a claim the document does
	not make -- the defect class this module exists to catch, committed by the
	module itself.
	"""
	document = tmp_path / "params.md"
	document.write_text(
		"## Parameter Reference\n"
		"\n"
		"| ID | Category | Parameter | Description | Algorithm | Python Implementation | Status | Users | Priority |\n"
		"|---|---|---|---|---|---|---|---|---|\n"
		"| 1.1 | Demand | `demand_growth_rate` | Growth | a | b | 🔨 | All | P1 |\n"
	)
	with pytest.raises(ValueError, match="does not state a parameter count"):
		title_count(document)


def test_the_summary_carries_the_catalog_register(graph: ParameterGraph):
	"""The register rides on ``prg summary``, so no door can miss it."""
	from alea.prg.service import graph_summary

	register = graph_summary(graph)["catalog"]
	assert register["readable"] is True
	assert register["surplus_over_title"] == 40
	assert register["status_disagreements"]


# ---------------------------------------------------------------------------
# The generator, and the gate it did not have
# ---------------------------------------------------------------------------


def test_the_generator_reproduces_the_shipped_graph():
	"""``config/prg.yaml`` is exactly what the generator writes from the catalog.

	The generator is the only thing that can put 787 catalog names into the
	graph, and until this test nothing ran it: ``--check`` existed, was
	documented in the module's own CLI help, and had no caller in ``tests/``.
	A drift mode no test invokes is a drift mode that cannot fail, which is the
	class of defect this repository has paid for most -- so this is the caller.

	Run as a subprocess rather than by importing the module. The generator
	reads the catalog and the shipped graph at import time and holds both in
	module-level tables, so an in-process call would test whatever the first
	import bound and not what the script does when a person runs it.
	"""
	import subprocess
	import sys

	script = repo_root() / "scripts" / "build" / "prg_from_catalog.py"
	assert script.exists(), script
	done = subprocess.run(
		[sys.executable, str(script), "--check"],
		capture_output=True,
		text=True,
		cwd=str(repo_root()),
	)
	assert done.returncode == 0, (
		f"the graph is not what the generator writes:\n{done.stdout}\n{done.stderr}"
	)
	assert "is current" in done.stdout, done.stdout
