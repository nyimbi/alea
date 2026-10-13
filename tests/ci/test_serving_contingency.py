# SPDX-License-Identifier: MIT
"""The first wired serving table: an N-1 sweep as per-element API rows.

WHY this module exists. `alea.publish.views` classifies every path
`api.repository` reads, and all eleven sat in `UNWIRED`: a projection declared
and no stage ran it. `@stage("resilience_contingency")` is the first stage that
runs one, so this is the gate on the register's first real movement --
`PROJECTION_STAGES` gains the entry and `UNWIRED` loses one, and
`test_the_unwired_set_is_exactly_what_is_recorded` fails if only one moves.

**The gate that matters is the unit, and it is the one a self-consistent test
would miss.** The kernel's ``energy_not_served`` array holds **MW per snapshot**
despite its Python name carrying ``_mwh``; ``SweepResult.ens_with_out``
multiplies by ``snapshot_hours`` to produce the energy the name claims. The
serving column is ``load_shed_mw``, so the honest per-element MW is the **peak**
over snapshots and a sum there would overstate a contingency by the number of
snapshots -- 8760x for an hourly year, printed under a unit that says MW. The
fixture below has two snapshots, so the peak and the sum differ by exactly 1.5x
and a gate that used the wrong one would be wrong by a factor a reader can see.
A one-snapshot fixture could not discriminate them at all.

**The fixture is a spur on a meshed core, and both halves are load-bearing.**
The meshed core (three buses at mixed voltage) is what makes the sweep compute
anything: a pure ring strands no load for any single outage, so every
``load_shed_mw`` is zero and the peak-vs-sum gate is vacuous. The spur carries
load reachable only through it, so outing it islands 300 MW -- a number that
exists, in a fixture where a wrong conversion or a wrong unit shows up as a
different number rather than as zero.

The rest of the module is the refusal set: a solve spanning more than one
country (the artefact carries no bus-to-country mapping, and labelling every
element with the first would serve a wrong list that looks correct), a missing
arrays artefact, and a dispatch whose column count disagrees with the arrays.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import build_stage, registered_stages
from alea.losses.flow import Network, susceptance_matrix
from alea.losses.views import LossConfig
from alea.planning.arrays import ARRAYS_ARTEFACT, DISPATCH_ARTEFACT
from alea.publish.stages import build_resilience_contingency
from alea.publish.views import PROJECTION_STAGES, PUBLISHED_TABLES, UNWIRED

# The spur's stranded load. The two snapshots carry 300 MW and 150 MW at bus 3,
# so the peak is 300 and the two-snapshot sum is 450 MWh -- different numbers,
# which is the whole point of the fixture.
SPUR_PEAK_MW = 300.0
SPUR_SUM_MWH = 450.0


def _spur_on_a_meshed_core() -> Network:
	"""A meshed, mixed-voltage core with a load-bearing spur.

	Meshed and mixed-voltage for the reason `tests/ci/test_network_arrays.py`
	records: a DC solve cannot see a *uniform* susceptance change, so a fixture
	whose branches all sit at one voltage cannot distinguish a changed network
	from an unchanged one. The spur is the branch whose outage strands load --
	without it every contingency returns zero and the unit gate below is vacuous.
	"""
	branch_from = np.array([0, 1, 2, 2], dtype=np.uint32)
	branch_to = np.array([1, 2, 0, 3], dtype=np.uint32)
	susceptance = np.array(
		[220.0**2 / 20.0, 132.0**2 / 10.0, 132.0**2 / 15.0, 132.0**2 / 8.0]
	)
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 4),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([1.0, 0.5, 0.8, 0.6]),
		voltage_kv=np.array([220.0, 132.0, 132.0, 132.0]),
		ratings_mw=np.array([500.0, 300.0, 400.0, 200.0]),
		branch_names=("AB", "BC", "CA", "C-spur"),
	)


def _dispatch() -> np.ndarray:
	"""Two snapshots; bus 3 consumes 300 MW then 150 MW."""
	return np.array([[600.0, -100.0, -200.0, -300.0], [300.0, -50.0, -100.0, -150.0]])


def _config(tmp_path: Path, *, countries: list[str] | None = None) -> Config:
	"""A config whose processed lake is the scratch tree, one country by default."""
	overrides = [
		f"paths.processed={tmp_path / 'processed'}",
		f"paths.results={tmp_path / 'results'}",
	]
	if countries is not None:
		overrides.append(f"scenario.countries={json.dumps(countries)}")
	return load_config(overrides=overrides)


def _write_inputs(tmp_path: Path, network: Network | None = None) -> Path:
	"""The arrays and dispatch `@stage("network_arrays")` writes, by hand.

	Written through `write_artefact` rather than `to_parquet`, because the
	artefact layer requires a provenance sidecar and `read_artefact` refuses a
	payload without one -- which is the layer doing its job. A fixture that wrote
	the bare files would fail the stage for a reason that is not the stage's.

	Written directly rather than by running the producer stage: this module gates
	the *consumer*, and pairing it to the producer's own test would make one
	failure look like two. The shapes are the producer's contract and are
	asserted in `tests/ci/test_network_arrays.py`.
	"""
	from alea.io.artefacts import write_artefact
	from alea.losses.service import network_to_payload
	from alea.logging import new_run_id
	from alea.provenance.models import Basis, DerivedProvenance

	processed = tmp_path / "processed"
	processed.mkdir(parents=True, exist_ok=True)
	bundle = network if network is not None else _spur_on_a_meshed_core()

	def provenance(source_id: str) -> DerivedProvenance:
		return DerivedProvenance(
			source_id=source_id,
			inputs=["<fixture>"],
			code_version="test",
			run_id=new_run_id(),
			parameters={},
			basis=Basis.MODELLED,
			notes="written by tests/ci/test_serving_contingency.py",
		)

	write_artefact(
		processed / ARRAYS_ARTEFACT,
		network_to_payload(bundle),
		provenance("network_arrays"),
		format="json",
	)
	frame = pd.DataFrame(_dispatch(), columns=[f"bus{b}" for b in range(bundle.n_buses)])
	frame.index = pd.date_range("2030-01-01", periods=len(frame), freq="h")
	frame.index.name = "timestamp"
	write_artefact(
		processed / DISPATCH_ARTEFACT, frame, provenance("dispatch"), format="parquet"
	)
	return processed


# --------------------------------------------------------------------------
# The layer function the stage reads
# --------------------------------------------------------------------------


def test_the_load_shed_is_the_peak_over_snapshots_not_their_sum():
	"""The unit gate: ``load_shed_mw`` is MW, so it is a peak.

	The kernel returns MW per snapshot and ``ens_with_out`` turns it into MWh.
	The serving column claims MW, so a sum would be MWh under a MW label --
	8760x overstated for an hourly year. The two-snapshot fixture makes the
	difference visible: 300 MW peak against 450 MWh summed.
	"""
	from alea.losses.contingency import element_records

	records = element_records(
		_spur_on_a_meshed_core(), _dispatch(), LossConfig(slack_bus=0, snapshot_hours=1.0)
	)
	spur = next(record for record in records if record["element_id"] == "C-spur")
	assert spur["load_shed_mw"] == pytest.approx(SPUR_PEAK_MW)
	assert spur["ens_mwh"] == pytest.approx(SPUR_SUM_MWH)
	assert spur["load_shed_mw"] != pytest.approx(spur["ens_mwh"]), (
		"the fixture cannot discriminate the peak from the sum; a one-snapshot "
		"series makes them equal and the unit gate vacuous"
	)


def test_a_ring_with_no_spur_strands_nothing():
	"""The canary for the fixture: without the spur every contingency is zero.

	This is what makes the gate above non-vacuous. A pure ring is N-1 secure, so
	every ``load_shed_mw`` is zero and a unit error would be invisible -- the
	same trap as a radial network for the susceptance conversion.
	"""
	from alea.losses.contingency import element_records

	branch_from = np.array([0, 1, 2], dtype=np.uint32)
	branch_to = np.array([1, 2, 0], dtype=np.uint32)
	susceptance = np.array([220.0**2 / 20.0, 132.0**2 / 10.0, 132.0**2 / 15.0])
	ring = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([1.0, 0.5, 0.8]),
		voltage_kv=np.array([220.0, 132.0, 132.0]),
		ratings_mw=np.array([500.0, 300.0, 400.0]),
		branch_names=("AB", "BC", "CA"),
	)
	dispatch = np.array([[600.0, -100.0, -500.0], [300.0, -50.0, -250.0]])
	records = element_records(ring, dispatch, LossConfig(slack_bus=0, snapshot_hours=1.0))
	assert all(record["load_shed_mw"] == 0.0 for record in records), (
		"a meshed ring stranded load, which it cannot; the fixture is not the "
		"N-1-secure network this canary assumes"
	)


def test_the_overloaded_count_is_elements_not_snapshots():
	"""``overloaded_elements`` counts elements, from a per-snapshot count array.

	The kernel's ``overloaded_branches`` holds the overloaded-branch *count* per
	(contingency, snapshot), not a flag. Counting snapshots-with-an-overload
	instead would put a number of timestamps under a name that says elements,
	and the two differ as soon as a sweep has more than one snapshot.
	"""
	from alea.losses.contingency import element_records, sweep

	network = _spur_on_a_meshed_core()
	cfg = LossConfig(slack_bus=0, snapshot_hours=1.0)
	result = sweep(network, _dispatch(), cfg)
	records = element_records(network, _dispatch(), cfg)

	for index, record in enumerate(records):
		per_snapshot = result.overloaded_branches[index + 1]
		assert record["overloaded_elements"] == int(np.max(per_snapshot))
		assert record["overloaded_elements"] >= 0


# --------------------------------------------------------------------------
# The stage
# --------------------------------------------------------------------------


def test_the_stage_writes_the_published_path_and_the_api_can_read_it(tmp_path: Path):
	"""End to end: the artefacts in, the API's table out, read back.

	The output path is `PUBLISHED_TABLES`'s, not a stage-shaped one. A producer
	that wrote `data/processed/resilience_contingency.parquet` would pass its own
	tests and serve nothing, because `api.repository` reads the nested path.
	"""
	_write_inputs(tmp_path)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["resilience_contingency"]

	build_resilience_contingency(config, out, BuildContext_stub(out))

	frame, provenance = read_artefact(out)
	frame = pd.DataFrame(frame)
	assert list(frame.columns) == [
		"element_id",
		"element_type",
		"country_iso",
		"load_shed_mw",
		"overloaded_elements",
		"severity",
	]
	assert set(frame["country_iso"]) == {"KE"}
	assert provenance.parameters["n_elements"] == 4
	spur = frame.loc[frame["element_id"] == "C-spur"].iloc[0]
	assert float(spur["load_shed_mw"]) == pytest.approx(SPUR_PEAK_MW)
	# 300 MW is at or above the high band's 100 MW threshold.
	assert spur["severity"] == "high"


def test_a_multi_country_scenario_is_refused_rather_than_labelled(tmp_path: Path):
	"""The refusal that stops a wrong list looking correct.

	A serving row carries ``country_iso`` and a solved network does not record
	one: buses have lon/lat and no country. Taking the first country from a
	multi-country scenario would label a continental solve's contingencies with
	one country, and a consumer filtering on it would get rows that are real
	numbers about the wrong network.
	"""
	_write_inputs(tmp_path)
	config = _config(tmp_path, countries=["KE", "NG", "ZA"])
	out = tmp_path / PUBLISHED_TABLES["resilience_contingency"]

	with pytest.raises(ArtefactError, match="3 countries"):
		build_resilience_contingency(config, out, BuildContext_stub(out))


def test_a_missing_arrays_artefact_is_refused(tmp_path: Path):
	"""An absent input raises rather than writing an empty table.

	An empty contingency table reads as "no element is critical", which is a
	claim about the network; the truth is that no sweep ran.
	"""
	(tmp_path / "processed").mkdir(parents=True, exist_ok=True)
	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["resilience_contingency"]

	with pytest.raises(ArtefactError, match="no network arrays"):
		build_resilience_contingency(config, out, BuildContext_stub(out))


def test_a_dispatch_that_disagrees_with_the_arrays_is_refused(tmp_path: Path):
	"""The two artefacts are positional partners; a shape mismatch is a finding.

	A dispatch with the wrong column count came from a different solve, and
	sweeping the pair would put every injection on the wrong bus while the
	shapes still looked plausible to a reader.
	"""
	from alea.io.artefacts import write_artefact
	from alea.logging import new_run_id
	from alea.losses.service import network_to_payload
	from alea.provenance.models import Basis, DerivedProvenance

	processed = _write_inputs(tmp_path)
	# Rewrite the dispatch with one bus too few -- through `write_artefact`, so
	# the sidecar and the payload agree and the *shape* is the only thing wrong.
	# A bare `to_parquet` here would trip the artefact layer's checksum check
	# first, and the test would pass for a reason that is not the stage's.
	frame = pd.DataFrame(_dispatch()[:, :3], columns=["bus0", "bus1", "bus2"])
	frame.index = pd.date_range("2030-01-01", periods=2, freq="h")
	frame.index.name = "timestamp"
	write_artefact(
		processed / DISPATCH_ARTEFACT,
		frame,
		DerivedProvenance(
			source_id="dispatch",
			inputs=["<fixture>"],
			code_version="test",
			run_id=new_run_id(),
			parameters={},
			basis=Basis.MODELLED,
			notes="a dispatch with one column too few",
		),
		format="parquet",
	)
	assert network_to_payload(_spur_on_a_meshed_core())["susceptance"], "fixture sanity"

	config = _config(tmp_path)
	out = tmp_path / PUBLISHED_TABLES["resilience_contingency"]
	with pytest.raises(ArtefactError, match="positional partners"):
		build_resilience_contingency(config, out, BuildContext_stub(out))


# --------------------------------------------------------------------------
# The register
# --------------------------------------------------------------------------


def test_the_stage_is_registered():
	"""A builder nothing can name is a builder nothing can run."""
	assert "resilience_contingency" in registered_stages()


def test_the_register_moved_with_the_wiring():
	"""`PROJECTION_STAGES` names the stage and `UNWIRED` no longer names the path.

	The two registers are the gate's two halves: a table is produced when this
	register claims a stage, and the gap shrinks when it does. Asserting both
	here means a reader sees the pair move together rather than inferring it
	from two files.
	"""
	path = PUBLISHED_TABLES["resilience_contingency"]
	assert PROJECTION_STAGES["resilience_contingency"] == "resilience_contingency"
	assert path not in UNWIRED, (
		"the path is wired and still recorded as a gap; a register that overstates "
		"its gap is the defect class it exists to close"
	)


def test_the_stage_is_idempotent_through_the_cli(tmp_path: Path):
	"""Run twice through the CLI; the second run must skip.

	Through the CLI and not the builder, because the CLI is the only entry point
	the workflow has (AD-5). The stage resolves its inputs itself -- the arrays
	and dispatch at their conventional paths -- and checks them through
	`skip_if_current`, so a second run against unchanged inputs must not rewrite.

	The evidence is the output file's mtime, not a log line. This gate used to
	assert ``"skip" in result.output``, which worked only because structlog's
	default factory wrote to stdout; once records moved to stderr (they were
	splicing into `alea config show`'s JSON payload) the assertion read an empty
	string. An mtime is the effect the docstring claims -- the artefact was not
	rewritten -- and it does not move when the logging configuration does.
	"""
	from typer.testing import CliRunner

	from alea.cli import app

	_write_inputs(tmp_path)
	config_path = tmp_path / "config.yaml"
	config_path.write_text(
		"\n".join(
			[
				"scenario:",
				"  countries: [KE]",
				"paths:",
				f"  processed: {tmp_path / 'processed'}",
				f"  results: {tmp_path / 'results'}",
			]
		),
		encoding="utf-8",
	)
	out = tmp_path / PUBLISHED_TABLES["resilience_contingency"]
	runner = CliRunner()
	arguments = [
		"build",
		"resilience_contingency",
		"--out",
		str(out),
		"--config",
		str(config_path),
	]
	first = runner.invoke(app, arguments)
	assert first.exit_code == 0, first.output
	assert out.exists(), "the first run published nothing, so the second proves nothing"
	written = out.stat().st_mtime_ns
	second = runner.invoke(app, arguments)
	assert second.exit_code == 0, second.output
	assert out.stat().st_mtime_ns == written, (
		f"the second run rebuilt against unchanged inputs; output was {second.stdout!r} "
		f"and {out} was rewritten"
	)


class BuildContext_stub:
	"""A minimal `BuildContext` for a builder called directly.

	`build_stage` constructs the real one; these tests call the builder to gate
	its own refusals, which are about the *inputs* rather than about the
	dispatch the CLI does.
	"""

	def __init__(self, out: Path) -> None:
		self.out = out
		self.inputs: list[str] = []
		self.logger = None
		self.parameters: dict[str, object] = {}
