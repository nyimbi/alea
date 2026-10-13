# SPDX-License-Identifier: MIT
"""The system-alerts producer: the rename, the band, and the round trip.

The register recorded this section's blocker as a missing producer and named the
one it needed -- "a `project_system_alerts` that renames the serving table's
columns to the section's". The reading half of that entry was closed first: the
section declares ``["Element", "State", "Basis"]`` and `State` is a *category*,
which the reader had no path for, so a frame carrying a band rendered its load
shed under a header promising a state. `ReportValue.categories`,
`SectionSpec.categorical` and the projection guard's category refusal are that
half.

This module is the other half, and the claim it discharges is the round trip: a
frame of the right shape and a stage that writes it are not a deliverable
section. `capacity_update` was recorded as produced, its rule exited 0, and
`alea report daily` raised ``ReportDataError: no artefact`` -- which is why the
last test here measures ``unprojected_sections`` before and after rather than
trusting the register.

**The band is the gate that a self-consistent test would miss.** ``severity`` is
banded in the *serving* projection against thresholds that live there, so a
producer that re-banded here would agree with it today and drift the moment
either threshold moved. The fixture writes a serving table whose bands are the
ones the serving projection produced, and the assertion is that the section's
``State`` cell is that word -- not one this module computed.

**And the row the band cannot describe.** ``load_shed_mw`` is NaN for a branch
whose every snapshot diverged, and every comparison against NaN is ``False``, so
the serving projection calls such a branch ``"low"``. That is a claim about the
element which the sweep did not make, so the producer drops the row and counts
it into the provenance. The fixture's third element is exactly that branch, and
the gate is that it is absent from the table *and* present in the count.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alea.config.paths import resolve
from alea.io.artefacts import read_artefact, read_provenance
from alea.io.pipeline import build_stage
from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED
from alea.reporting.schemas import ReportCadence
from alea.resilience.service import system_alerts_rows, system_alerts_to_artefact
from tests.ci.test_market_report_sections import _config

ISSUE_DATE = date(2030, 1, 15)
PERIOD_END = date(2030, 1, 14)
"""``period_for(DAILY, ISSUE_DATE)``'s end: a daily report generated at 06:00
covers yesterday. Spelled once so the projection and the assertion cannot
disagree about which day the section reads."""

#: The three elements the serving fixture carries: one above the high band's
#: 100 MW threshold, one inside the medium band, and one whose every snapshot
#: diverged so its load shed is NaN.
SERVING_ROWS = [
	{
		"element_id": "C-spur",
		"element_type": "line",
		"country_iso": "KE",
		"load_shed_mw": 300.0,
		"overloaded_elements": 2,
		"severity": "high",
	},
	{
		"element_id": "BC",
		"element_type": "line",
		"country_iso": "KE",
		"load_shed_mw": 25.0,
		"overloaded_elements": 1,
		"severity": "medium",
	},
	{
		"element_id": "AB",
		"element_type": "line",
		"country_iso": "KE",
		"load_shed_mw": float("nan"),
		"overloaded_elements": 0,
		"severity": "low",
	},
]
"""The serving table's rows, by hand.

Written directly rather than by running the sweep: this module gates the
*consumer*, and pairing it to the sweep's own test would make one failure look
like two. The shape is `RESILIENCE_CONTINGENCY`'s and is asserted in
`tests/ci/test_serving_contingency.py`.
"""


def _serving() -> pd.DataFrame:
	return pd.DataFrame(SERVING_ROWS)


def _write_serving(tmp_path: Path) -> Path:
	"""The serving table at the path ``PUBLISHED_TABLES`` declares, under the
	scratch tree -- written through `write_artefact`, because the artefact layer
	requires a provenance sidecar and `read_artefact` refuses a payload without
	one.
	"""
	from alea.io.artefacts import write_artefact
	from alea.logging import new_run_id
	from alea.provenance.models import Basis, DerivedProvenance

	target = tmp_path / "processed" / "resilience" / "contingency.parquet"
	target.parent.mkdir(parents=True, exist_ok=True)
	write_artefact(
		target,
		_serving(),
		DerivedProvenance(
			source_id="resilience_contingency",
			inputs=["<fixture>"],
			code_version="test",
			run_id=new_run_id(),
			parameters={},
			basis=Basis.MODELLED,
			notes="written by tests/ci/test_system_alerts.py",
		),
		format="parquet",
	)
	return target


# --------------------------------------------------------------------------
# The rename
# --------------------------------------------------------------------------


def test_the_section_s_columns_are_the_serving_table_s_renamed():
	"""The whole producer: ``element_id`` to the label, ``severity`` to ``state``.

	Asserted as an identity rather than as a shape, because the defect this
	replaces was a frame that *looked* right: a serving table carrying
	``load_shed_mw`` and a band, projected unchanged, rendered its load shed
	under the section's ``State`` header. The two cells must be the serving
	table's own values, and the band must be the one the serving projection
	chose -- not one this module recomputed.
	"""
	rows, uncomputable = system_alerts_rows(_serving())

	assert uncomputable == 1, (
		f"the fixture carries one branch whose load shed is not finite and the "
		f"reader counted {uncomputable}; a NaN compared against a threshold is "
		f"False for every band, so the serving table calls it `low`"
	)
	by_label = {row["label"]: row for row in rows}
	assert set(by_label) == {"C-spur", "BC"}, (
		f"the rows are {sorted(by_label)}; the diverged branch must not appear, "
		f"because its band is a claim the sweep did not make"
	)
	assert by_label["C-spur"]["value"] == pytest.approx(300.0)
	assert by_label["C-spur"]["unit"] == "MW", (
		f"the row's unit is {by_label['C-spur']['unit']!r}; the section declares "
		f"no unit of its own, so the reader takes the row's"
	)
	assert by_label["C-spur"]["state"] == "high"
	assert by_label["BC"]["state"] == "medium", (
		"the band is not the serving table's; a producer that re-banded here "
		"would agree today and drift the moment either threshold moved"
	)


def test_a_serving_table_without_the_band_is_refused():
	"""The section's ``State`` is declared a category and the frame must carry it.

	Without this the producer would write a frame whose category column is
	absent, `project_section`'s guard would refuse it, and the failure would
	surface as a report that cannot open a section the register calls delivered.
	"""
	bare = _serving().drop(columns=["severity"])
	with pytest.raises(ValueError, match="severity"):
		system_alerts_rows(bare)


def test_the_provenance_counts_the_rows_it_could_not_band(tmp_path: Path):
	"""The dropped row is a finding, so it is recorded rather than discarded.

	A producer that silently dropped it would publish a table of two alerts for
	a sweep that could not compute a third, and nothing would say so.
	"""
	target = tmp_path / "system_alerts.parquet"
	system_alerts_to_artefact(_serving(), target, inputs=["sha256:fixture"])

	provenance = read_provenance(target)
	assert provenance.parameters["n_uncomputable"] == 1
	assert provenance.parameters["n_elements"] == 2


# --------------------------------------------------------------------------
# The stage and the register
# --------------------------------------------------------------------------


def test_the_stage_writes_the_frame_and_the_register_names_it():
	"""A slug in ``PRODUCERS`` claims a function computes the section's rows, and
	a slug in ``PROJECTED`` that a rule lands them where the report reads. Both
	are asserted because closing this gap meant moving both.
	"""
	assert PRODUCERS["system_alerts"] == "resilience.service.system_alerts_to_artefact"
	assert PROJECTED["system_alerts"] == "project_system_alerts"
	assert "system_alerts" not in UNPRODUCED


def test_a_missing_serving_table_is_refused(tmp_path: Path):
	"""An absent input raises rather than writing an empty table.

	An empty alerts table reads as "no element is critical", which is a claim
	about the network; the truth is that no sweep ran.
	"""
	from alea.io.artefacts import ArtefactError

	config = _config(tmp_path)
	out = resolve(config.paths.processed) / "system_alerts.parquet"

	with pytest.raises(ArtefactError, match="no contingency serving table"):
		build_stage("system_alerts", config, out)


def test_the_stage_reads_the_serving_table_rather_than_re_sweeping(tmp_path: Path):
	"""The stage's input is the API's table, and its output is the section's rows.

	A stage that re-swept would be a second computation of the same numbers, and
	the report and the contingency route could come to disagree about which
	elements are critical.
	"""
	_write_serving(tmp_path)
	config = _config(tmp_path)
	out = resolve(config.paths.processed) / "system_alerts.parquet"

	build_stage("system_alerts", config, out)

	frame, provenance = read_artefact(out)
	frame = pd.DataFrame(frame)
	assert list(frame.columns) == ["label", "value", "unit", "state"], (
		f"the stage wrote {list(frame.columns)}; the section binds its first "
		f"column to the label, its primary to `value`, and its category to `state`"
	)
	assert sorted(frame["label"]) == ["BC", "C-spur"]
	assert set(frame["state"]) == {"high", "medium"}
	# The digest of the table it read, not a network's: the source is
	# `PUBLISHED_TABLES`'s path, so a re-sweep that changed the serving table
	# re-runs this stage and one that did not does not.
	assert len(provenance.inputs) == 1
	assert provenance.parameters["n_uncomputable"] == 1


# --------------------------------------------------------------------------
# The round trip
# --------------------------------------------------------------------------


def test_the_section_leaves_the_missing_list_and_renders(tmp_path: Path):
	"""The round trip, asserted on the measurement the register entry is about.

	``unprojected_sections`` is the one measurement that separates "a producer
	exists" from "a report can read one", so it is taken before and after rather
	than inferred from the register. The section is then assembled through the
	reader's own path, which is the only check that the *band* survives: the
	projection guard refuses a declared category the frame does not carry, and a
	reader that dropped the text column would render the load shed under
	``State``.
	"""
	from alea.reporting.projection import project_section, unprojected_sections
	from alea.reporting.service import _section_from_spec, section_by_slug

	_write_serving(tmp_path)
	config = _config(tmp_path)

	before = unprojected_sections(ReportCadence.DAILY, config, as_of=ISSUE_DATE)
	assert "system_alerts" in before, (
		f"the section's dated artefact already exists before anything wrote it: "
		f"{before}"
	)

	stage_out = resolve(config.paths.processed) / "system_alerts.parquet"
	build_stage("system_alerts", config, stage_out)

	project_section(ReportCadence.DAILY, "system_alerts", stage_out, config, as_of=ISSUE_DATE)

	after = unprojected_sections(ReportCadence.DAILY, config, as_of=ISSUE_DATE)
	assert "system_alerts" not in after, (
		f"the projection did not land the artefact where the section reads it; "
		f"still missing: {after}"
	)

	spec = section_by_slug(ReportCadence.DAILY, "system_alerts")
	warnings: list[str] = []
	rendered = _section_from_spec(spec, config, PERIOD_END, warnings)
	assert rendered is not None, (
		f"the section did not assemble from the artefact it declares: {warnings}"
	)
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one"
	)
	table = rendered.tables[0]
	assert table.columns == ["Element", "State", "Basis"], (
		f"the table's headers are {table.columns}, not the section's declared columns"
	)
	assert len(table.rows) == 2, f"the section rendered {len(table.rows)} rows, not two"

	by_element = {str(row[0]): row for row in table.rows}
	assert by_element["C-spur"][1] == "high", (
		f"the State cell is {by_element['C-spur'][1]!r}; the band did not reach the "
		f"column the section declares a category, which is the defect the reader "
		f"half of this entry closed"
	)
	assert by_element["BC"][1] == "medium"
	assert by_element["C-spur"][2] == "modelled", (
		f"the Basis cell is {by_element['C-spur'][2]!r}; the states come from the "
		f"N-1 sweep of a solved network, so the basis is modelled"
	)
