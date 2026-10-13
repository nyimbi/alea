# SPDX-License-Identifier: MIT
"""The monthly capacity section, read back through the real reader.

WHY this module exists. `reporting/producers.py` recorded `capacity_update` as
unproduced, and the blocker was exact: `planning.capacity_mix_table` computed the
mix and `solve_scenario` wrote it into the solve's JSON summary, which is a *run
record* -- a reader who wants the monthly capacity table cannot open a solve
summary and find it, and no artefact carried the mix at a dated path. The stage
`alea.planning.arrays.build_capacity_update` is that artefact.

**Two numeric columns, so the binding refuses.** The section declares
``["Carrier", "Capacity", "Change", "Basis"]``. `_rows_for` binds each numeric
header to the row column naming it and does **not** take its one-numeric-column
escape hatch here, so each row must carry both a ``capacity`` extra and a
``change`` extra. A producer that wrote one number into both columns renders,
passes every schema check, and prints a capacity under the header "Change" --
the same failure `test_market_report_sections.py` pins for "Volume", and the one
a fixture that hand-wrote the artefact cannot see.

**The section's quantity is a difference, which needs two artefacts.** Every
other section this pipeline produces is a function of one solve. "The change
since the previous month" is a function of two, and the pipeline writes one
solve per invocation. So the stage resolves the directory twice and the two
cases are different enough to be tested separately: a directory with one solve
must omit the column, and a directory with two must carry the real delta. The
tempting shortcut -- write ``0.0`` for the change when there is no earlier
network -- asserts the strongest claim available (capacity did not move) from no
evidence at all, and it is the defect the second gate exists to catch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import read_artefact, read_provenance
from alea.io.pipeline import registered_stages
from alea.planning.arrays import build_capacity_update
from alea.planning.service import capacity_update_rows
from alea.reporting.schemas import ReportCadence, ReportValue
from alea.reporting.service import SectionSpec, _section_from_spec, cadence_specs

SNAPSHOTS = pd.date_range("2030-01-01", periods=24, freq="h")
AS_OF = date(2030, 1, 31)
"""The monthly cadence's period end for a report dated the last day of January."""


def _network(coal_mw: float, solar_mw: float) -> pypsa.Network:
	"""A two-carrier network with named capacities, no solve needed.

	`capacity_mix_table` reads ``p_nom`` for a non-extendable component, so a
	capacity update is a function of the *built* network and does not need an
	optimiser run. That is what makes this fixture cheap enough to have two of.
	"""
	network = pypsa.Network()
	network.set_snapshots(list(SNAPSHOTS))
	network.add("Bus", "north", v_nom=220.0)
	network.add("Bus", "south", v_nom=132.0)
	network.add("Line", "north-south", bus0="north", bus1="south", r=0.5, x=10.0, s_nom=400.0)
	network.add(
		"Generator", "coal", bus="north", carrier="coal", p_nom=coal_mw, marginal_cost=45.0
	)
	network.add(
		"Generator", "solar", bus="south", carrier="solar", p_nom=solar_mw, marginal_cost=0.0
	)
	network.add("Load", "load", bus="south", p_set=120.0)
	return network


def _write(directory: Path, name: str, network: pypsa.Network) -> Path:
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / name
	network.export_to_netcdf(str(path))
	return path


def _config(tmp_path: Path) -> Config:
	return load_config(
		overrides=[
			f"paths.processed={tmp_path / 'processed'}",
			f"paths.results={tmp_path / 'results'}",
			f"paths.reports={tmp_path / 'reports'}",
			"reporting.pdf_enabled=false",
		]
	)


class _Context:
	"""A minimal `BuildContext`, as the serving and market tests define one."""

	def __init__(self, parameters: dict[str, object] | None = None) -> None:
		self.out: Path | None = None
		self.inputs: list[str] = []
		self.logger = None
		self.parameters = dict(parameters or {})


def _spec() -> SectionSpec:
	"""The section's declaration as it is written, refused if the slug moved."""
	specs, _ = cadence_specs(ReportCadence.MONTHLY)
	by_slug = {spec.slug: spec for spec in specs}
	assert "capacity_update" in by_slug, "the monthly cadence no longer declares capacity_update"
	return by_slug["capacity_update"]


def _as_value(cell: ReportValue | str) -> ReportValue:
	assert isinstance(cell, ReportValue), f"expected a numeric cell, got {cell!r}"
	return cell


def _column(spec: SectionSpec, index: int) -> str:
	return spec.columns[index]


# --------------------------------------------------------------------------
# The stage registers, and it is reachable through `alea build`
# --------------------------------------------------------------------------


def test_the_stage_is_registered():
	"""A `@stage` in a module `_REGISTRATION_MODULES` omits registers nothing."""
	assert "capacity_update" in registered_stages(), (
		"`capacity_update` did not register; `alea.planning.arrays` is missing from "
		"`_REGISTRATION_MODULES`, so the stage is written, decorated and unreachable"
	)


# --------------------------------------------------------------------------
# The rows the producer writes
# --------------------------------------------------------------------------


def test_the_capacity_section_carries_both_numbers_per_row():
	"""Two columns, two numbers, and they must not be the same number.

	A producer that wrote the capacity into both columns would satisfy every
	check the artefact has and print a capacity under the header "Change". This
	asserts the two differ, which is what makes the binding meaningful.
	"""
	frame = capacity_update_rows(_network(400.0, 200.0), _network(300.0, 200.0))
	assert {"capacity", "change"} <= set(frame.columns), (
		"the frame does not carry both numbers the section's two numeric columns "
		f"bind; it carries {sorted(frame.columns)}"
	)
	by_carrier = {str(row["label"]): row for _, row in frame.iterrows()}
	assert set(by_carrier) == {"coal", "solar"}, "the frame is not one row per carrier"
	assert float(by_carrier["coal"]["capacity"]) == pytest.approx(400.0)
	assert float(by_carrier["coal"]["change"]) == pytest.approx(100.0)
	assert float(by_carrier["solar"]["change"]) == pytest.approx(0.0)
	assert float(by_carrier["coal"]["change"]) != float(by_carrier["coal"]["capacity"]), (
		"the change equals the capacity, which is the signature of a producer that "
		"wrote the primary into the second column"
	)


def test_a_carrier_that_shrank_reports_a_negative_change():
	"""The ordinary month-on-month case."""
	frame = capacity_update_rows(_network(400.0, 150.0), _network(400.0, 200.0))
	by_carrier = {str(row["label"]): row for _, row in frame.iterrows()}
	assert float(by_carrier["solar"]["change"]) == pytest.approx(-50.0)
	assert float(by_carrier["solar"]["capacity"]) == pytest.approx(150.0)


def test_a_carrier_that_was_retired_reports_a_negative_change_not_a_positive_one():
	"""The sign of a retirement, which is where a naive difference goes wrong.

	`capacity_mix_table` is a *mix*: it carries only positive capacity, so a
	carrier that was 200 MW and is now nothing is **absent** from this month's
	table rather than present as zero. A producer that differenced over this
	month's carriers alone would look it up, find nothing, read the absence as
	``0.0``, and report the retirement as a **200 MW addition** -- a sign error
	in the one column whose whole purpose is its sign. It renders, it passes
	every schema check, and it says the opposite of what happened.

	The union of both mixes' carriers is what makes the sign right, and the row
	has to be *present* for a reader to see the retirement at all: dropping it
	would hide a plant closing.
	"""
	frame = capacity_update_rows(_network(400.0, 0.0), _network(400.0, 200.0))
	by_carrier = {str(row["label"]): row for _, row in frame.iterrows()}
	assert "solar" in by_carrier, (
		"the retired carrier is absent from the frame; a reader cannot see a plant "
		"close if its row is gone"
	)
	assert float(by_carrier["solar"]["capacity"]) == pytest.approx(0.0)
	assert float(by_carrier["solar"]["change"]) == pytest.approx(-200.0), (
		"a retired carrier reports a positive change; the previous mix has no row "
		"for it, so its absence was read as zero"
	)


def test_a_carrier_that_was_commissioned_reports_a_positive_change():
	"""The mirror: absent last month, present now, and the sign is positive."""
	frame = capacity_update_rows(_network(400.0, 200.0), _network(400.0, 0.0))
	by_carrier = {str(row["label"]): row for _, row in frame.iterrows()}
	assert float(by_carrier["solar"]["change"]) == pytest.approx(200.0)


# --------------------------------------------------------------------------
# The stage, writing the artefact the section reads
# --------------------------------------------------------------------------


def test_the_stage_writes_the_section_and_the_reader_binds_both_columns(tmp_path: Path):
	"""The round trip: stage -> artefact -> `_section_from_spec` -> two numbers.

	The assertion is on the *rendered cells*, not on the frame: a producer whose
	frame is right and whose column names do not match the section's headers
	raises inside `_rows_for`, and that is the failure this catches.
	"""
	directory = tmp_path / "results" / "networks"
	_write(directory, "aaaa1111-2030.nc", _network(300.0, 200.0))
	_write(directory, "bbbb2222-2030.nc", _network(400.0, 200.0))

	config = _config(tmp_path)
	spec = _spec()
	# At the section's own declared path, not a scratch name. The reader refuses
	# an artefact with no provenance sidecar and resolves `{date}` from the
	# report's date, so a stage output written anywhere else would be read by no
	# report at all -- and the round trip is the claim under test.
	out = resolve(Path(config.paths.results) / f"planning/capacity/{AS_OF:%Y-%m-%d}.parquet")
	build_capacity_update(
		config, out, _Context({"network_dir": str(directory)})  # type: ignore[arg-type]
	)
	frame, _ = read_artefact(out)
	assert {"label", "value", "unit", "capacity", "change"} <= set(frame.columns), (
		f"the written artefact is missing a column the section binds: {sorted(frame.columns)}"
	)

	section = _section_from_spec(spec, config, AS_OF, [])
	assert section is not None, "the section did not assemble from the artefact it declares"
	assert len(section.tables) == 1
	table = section.tables[0]
	header = {name: index for index, name in enumerate(table.columns)}
	rows = {str(row[0]): row for row in table.rows}
	assert set(rows) == {"coal", "solar"}, f"the table is not one row per carrier: {sorted(rows)}"

	coal = rows["coal"]
	capacity = _as_value(coal[header["Capacity"]])
	change = _as_value(coal[header["Change"]])
	assert capacity.value == pytest.approx(400.0), "the Capacity cell is not the capacity"
	assert change.value == pytest.approx(100.0), "the Change cell is not the change"
	assert capacity.value != change.value, (
		"Capacity and Change render the same number; the reader bound the primary "
		"into a column that names a quantity the row also carries"
	)


def test_the_capacity_section_refuses_to_invent_a_change(tmp_path: Path):
	"""One solve in the directory: no change column, and no zero standing in for one.

	A first capacity update has nothing to difference against. Writing ``0.0``
	would assert that capacity did not move -- the strongest claim the column can
	make -- from the absence of an earlier network, and it would render as a real
	measurement in a published report.
	"""
	directory = tmp_path / "results" / "networks"
	_write(directory, "aaaa1111-2030.nc", _network(400.0, 200.0))

	out = tmp_path / "capacity_update.parquet"
	build_capacity_update(
		_config(tmp_path), out, _Context({"network_dir": str(directory)})  # type: ignore[arg-type]
	)
	frame, _ = read_artefact(out)
	assert "change" not in frame.columns, (
		"the artefact carries a change column with only one solve in the directory; "
		"there is no previous month to difference against, so any number in it is "
		"invented"
	)
	assert {"label", "value", "capacity"} <= set(frame.columns), (
		f"the capacity itself is missing: {sorted(frame.columns)}"
	)

	provenance = read_provenance(out)
	assert provenance.parameters["has_change"] is False
	assert provenance.parameters["previous_network_file"] == "", (
		"the provenance names a previous network the directory does not hold"
	)
	assert "absent rather than zero" in provenance.notes, (
		"the provenance does not record why the change is missing; a reader who "
		f"sees the column gone has nothing to distinguish it from a bug: {provenance.notes!r}"
	)


def test_the_stage_records_the_earlier_network_it_differenced_against(tmp_path: Path):
	"""A change is a function of two networks, so both are recorded inputs.

	A reader given only the new network cannot reproduce the delta, and the
	inputs list is the record a reader consults.
	"""
	directory = tmp_path / "results" / "networks"
	older = _write(directory, "aaaa1111-2030.nc", _network(300.0, 200.0))
	newer = _write(directory, "bbbb2222-2030.nc", _network(400.0, 200.0))

	out = tmp_path / "capacity_update.parquet"
	build_capacity_update(
		_config(tmp_path), out, _Context({"network_dir": str(directory)})  # type: ignore[arg-type]
	)
	provenance = read_provenance(out)
	assert provenance.parameters["previous_network_file"] == older.name, (
		f"the stage differenced against {provenance.parameters['previous_network_file']!r} "
		f"but the earlier solve is {older.name!r}"
	)
	assert provenance.parameters["network_file"] == newer.name
	assert len(provenance.inputs) == 2, (
		f"the provenance records {len(provenance.inputs)} input(s); a delta needs both "
		f"networks' digests"
	)


def test_the_stage_refuses_when_the_directory_holds_no_solve(tmp_path: Path):
	"""No network is a refusal, not an empty table.

	An empty capacity table is a *finding* -- nothing is installed -- and a stage
	that wrote one because its input was absent would publish that finding for a
	directory it never read.
	"""
	from alea.io.artefacts import ArtefactError

	directory = tmp_path / "results" / "networks"
	directory.mkdir(parents=True, exist_ok=True)
	with pytest.raises(ArtefactError, match="no solved network"):
		build_capacity_update(
			_config(tmp_path),
			tmp_path / "capacity_update.parquet",
			_Context({"network_dir": str(directory)}),  # type: ignore[arg-type]
		)
