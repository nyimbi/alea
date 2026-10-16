# SPDX-License-Identifier: MIT
"""`02-data-pipeline.md` §4.2's stage gates, against the real builders.

§4.2 names five gates. Two of them are about a *stage's own output* and are the
ones that were absent:

* ``test_topology_schema`` -- "all required columns present, dtypes correct."
* ``test_fleet_carriers_known`` -- "every `carrier` is in the technology
  registry."

Both read the frame the stage writes, through the schema its consumer reads.
That is the seam that broke: `build_fleet` wrote ``commission_year`` while
`FLEET` -- and `attach_generators`, which checks it first -- required
``commissioning_year``, and the pipeline could not build a network from its own
output. A gate that writes the *consumer's* spelling by hand, as the fixtures
did, cannot see that; these run the producer.

§4.2's canary is stated in the plan's own words: "inject a row with an unknown
carrier; the schema gate must fail."
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from alea.config.loader import load_config
from alea.io.artefacts import ArtefactError, read_artefact, store_raw
from alea.io.pipeline import build_stage
from alea.planning.fleet import FleetError, validate_fleet_coverage
from alea.planning.schemas import FLEET, TOPOLOGY
from alea.provenance.models import Basis, Licence, Provenance
from alea.registry import Carrier
from tests.ci.canaries import REPO, planted, probe_exit_code


def _raw_provenance(source_id: str) -> Provenance:
	return Provenance(
		source_id=source_id,
		source_url="https://energydata.info/",
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		uncertainty=0.0,
		notes="§4.2 gate fixture",
	)


def _feature_collection(n_lines: int = 2) -> dict:
	"""A World Bank grid payload with ``n_lines`` corridors."""
	corridors = [
		("L1", [36.8219, -1.2921], [39.6682, -4.0435], 400.0, 490.0, 1200.0),
		("L2", [39.6682, -4.0435], [35.2698, -0.0917], 220.0, 330.0, 600.0),
	]
	return {
		"type": "FeatureCollection",
		"features": [
			{
				"type": "Feature",
				"geometry": {"type": "LineString", "coordinates": [start, end]},
				"properties": {
					"id": line_id,
					"voltage": voltage,
					"length_km": length,
					"capacity_mva": capacity,
				},
			}
			for line_id, start, end, voltage, length, capacity in corridors[:n_lines]
		],
	}


def _build_topology(tmp_path: Path, payload: dict) -> tuple[pd.DataFrame, Path]:
	"""Store ``payload`` as raw and run the real ``topology`` stage over it."""
	root = tmp_path / "raw"
	import json

	stored = store_raw(
		"worldbank_grid_map",
		json.dumps(payload).encode(),
		_raw_provenance("worldbank_grid_map"),
		root=root,
	)
	out = tmp_path / "processed" / "topology.parquet"
	config = load_config(
		overrides=[f"paths.raw={root}", f"paths.processed={tmp_path / 'processed'}"]
	)
	build_stage("topology", config, out, inputs=[stored.parent.name], parameters={"raw_root": str(root)})
	frame, _ = read_artefact(out)
	return frame, out


def _write_fleet_export(tmp_path: Path, *, carrier: str = "coal") -> Path:
	raw = tmp_path / "raw" / "powerplantmatching" / "manual"
	raw.mkdir(parents=True, exist_ok=True)
	pd.DataFrame(
		{
			"plant_id": ["p0", "p1"],
			"name": ["plant 0", "plant 1"],
			"country_iso": ["KE", "KE"],
			"lat": [0.0, 0.0],
			"lon": [0.0, 0.1],
			"capacity_mw": [500.0, 500.0],
			"carrier": [carrier, carrier],
			"Commissioned": [1990, 1990],
			"Lifetime": [40, 40],
		}
	).to_parquet(raw / "powerplants.parquet")
	return raw.parent.parent


def _fleet_config(tmp_path: Path):
	processed = tmp_path / "processed"
	processed.mkdir(parents=True, exist_ok=True)
	return load_config(
		overrides=[f"paths.raw={tmp_path / 'raw'}", f"paths.processed={processed}"]
	)


def test_topology_schema(tmp_path: Path):
	"""§4.2: "all required columns present, dtypes correct", on the stage's output.

	Read from the artefact the stage wrote, not from a fixture that spells the
	columns itself. `TOPOLOGY.check` is what the network builder runs, so the
	assertion is the consumer's own schema -- and the dtypes are asserted
	separately because `check` coerces a numeric-looking string column rather
	than refusing it, which is right for a seam and insufficient for a gate on
	the producer.
	"""
	frame, _ = _build_topology(tmp_path, _feature_collection(2))
	TOPOLOGY.check(frame, artefact="topology")
	assert set(TOPOLOGY.names) <= set(frame.columns)
	for spec in TOPOLOGY.columns:
		actual = frame[spec.name].dtype.kind
		if spec.dtype == "float":
			assert actual == "f", f"{spec.name} is {frame[spec.name].dtype}, schema says float"
		elif spec.dtype == "str":
			assert actual in ("O", "U", "T"), f"{spec.name} is {frame[spec.name].dtype}, schema says str"
	# The two coordinates a network builder needs to place a line, and the
	# endpoint columns are not interchangeable: a from/to swap reverses every
	# flow in the DC model and leaves the length unchanged.
	assert bool((frame["from_lon"] != frame["to_lon"]).any()) or bool(
		(frame["from_lat"] != frame["to_lat"]).any()
	), "every line has identical endpoints; the fixture cannot discriminate"
	assert bool(frame["length_km"].notna().all()), "a line with no length cannot be priced"
	assert bool((frame["voltage_kv"] > 0).all()), "the stage kept a line with no voltage"


def test_fleet_carriers_known(tmp_path: Path):
	"""§4.2: "every `carrier` is in the technology registry", on the stage's output.

	The stage maps upstream fuel strings through `_carrier_name` and refuses an
	unmapped one. This asserts the set it wrote is the registry's, so a carrier
	added to the alias table but not to `Carrier` -- which would have no
	emissions factor and no variability -- fails here rather than in a report.
	"""
	_write_fleet_export(tmp_path)
	out = tmp_path / "processed" / "fleet.parquet"
	build_stage("fleet", _fleet_config(tmp_path), out)
	frame, _ = read_artefact(out)

	FLEET.check(frame, artefact="fleet")
	known = {c.value for c in Carrier}
	assert set(frame["carrier"]) <= known, (
		f"the stage wrote carrier(s) the registry does not hold: "
		f"{sorted(set(frame['carrier']) - known)}"
	)
	assert frame["carrier"].notna().all(), "a plant with no carrier has no place in a mix"


def test_an_unknown_carrier_is_refused(tmp_path: Path):
	"""§4.2's own canary: "inject a row with an unknown carrier; the schema gate must fail."

	Run through `build_stage`, so the gate asserted is the one the workflow
	runs rather than a direct call to the validator.
	"""
	_write_fleet_export(tmp_path, carrier="unobtainium")
	out = tmp_path / "processed" / "fleet.parquet"
	with pytest.raises(ArtefactError, match="unknown carrier"):
		build_stage("fleet", _fleet_config(tmp_path), out)
	assert not out.exists(), "the stage wrote an artefact it refused"


def test_the_carrier_alias_table_maps_into_the_registry():
	"""Every upstream alias resolves to a registered carrier.

	The alias table is what turns an upstream fuel string into a carrier, so an
	alias pointing at a name the registry lacks is a mapping that produces an
	unknown carrier on a real export -- and the refusal would name the *export*,
	not the alias table.

	This is also the gate on the *duplicate* table. `_carrier_name` carried its
	own copy of the registry's aliases and the two had drifted: 13 of the
	registry's 49 keys mapped differently or not at all, including
	``hydroelectric``, ``reservoir``, ``photovoltaic`` and ``pumped storage``.
	An export holding a hydro plant named ``Hydroelectric`` -- powerplantmatching's
	own spelling -- therefore failed the unknown-carrier gate on a carrier the
	registry had held all along. The mapping is asserted from the registry, so a
	second copy that disagrees fails here.
	"""
	from alea.io.stages import _carrier_name
	from alea.registry.technologies import _ALIASES

	divergent = {
		alias: (carrier.value, _carrier_name(alias))
		for alias, carrier in _ALIASES.items()
		if _carrier_name(alias) != carrier.value
	}
	assert not divergent, (
		f"the fleet stage maps these upstream aliases differently from the "
		f"registry: {divergent}. One mapping, one table."
	)
	assert len(_ALIASES) > 40, (
		f"the registry holds {len(_ALIASES)} aliases; the table this gate reads "
		f"is not the one the platform maps through"
	)
	# A string that is neither an alias nor a carrier is passed through, so the
	# unknown-carrier gate can name it rather than it being folded into a default.
	assert _carrier_name("unobtainium") == "unobtainium"


def test_the_fleet_stage_refuses_an_unknown_carrier_end_to_end(tmp_path: Path):
	"""The canary for `test_fleet_carriers_known`, run in a subprocess.

	Plants the defect the gate exists for: the stage stops mapping upstream fuel
	strings, so ``Hard Coal`` reaches the frame as itself and the registry has no
	such carrier. That is the shipped defect in its general form -- the stage
	writing a carrier nothing downstream can interpret -- and the assertion is
	that the unknown-carrier gate refuses it rather than writing a fleet one row
	of which has no emissions factor and no variability.

	In a subprocess because a source mutation cannot reach a module this
	interpreter already holds, and asserting the *message* because "something
	raised" would pass against a stage failing for an unrelated reason.
	"""
	stages = REPO / "src" / "alea" / "io" / "stages.py"
	shipped = "\t\treturn get_technology(text).carrier.value"
	broken = "\t\treturn text  # canary: the mapping is bypassed"
	assert shipped in stages.read_text(), "canary target not found: no carrier mapping to bypass"

	program = """
import sys
from pathlib import Path
import pandas as pd
from alea.config.loader import load_config
from alea.io.pipeline import build_stage

root = Path(sys.argv[1])
raw = root / "raw" / "powerplantmatching" / "manual"
raw.mkdir(parents=True, exist_ok=True)
pd.DataFrame({
    "plant_id": ["p0"], "name": ["plant 0"], "country_iso": ["KE"],
    "lat": [0.0], "lon": [0.0], "capacity_mw": [500.0],
    "carrier": ["Hard Coal"], "Commissioned": [1990], "Lifetime": [40],
}).to_parquet(raw / "powerplants.parquet")
config = load_config(overrides=[
    f"paths.raw={root / 'raw'}", f"paths.processed={root / 'processed'}"
])
try:
    build_stage("fleet", config, root / "processed" / "fleet.parquet")
except Exception as exc:
    print(f"refused:{type(exc).__name__}:{exc}")
else:
    print("accepted")
"""
	env = {**os.environ, "PYTHONPATH": str(REPO)}

	def outcome() -> str:
		completed = subprocess.run(
			[sys.executable, "-c", program, str(tmp_path)],
			capture_output=True, text=True, check=False, env=env, cwd=str(REPO),
		)
		assert completed.returncode == 0, completed.stderr
		lines = [line for line in completed.stdout.splitlines() if line.strip()]
		return lines[-1].strip()

	assert outcome().startswith("accepted"), (
		"the shipped mapping refused a real upstream fuel string, so the canary "
		"below would pass for a reason unrelated to the bypass"
	)
	with planted(stages, shipped, broken):
		result = outcome()
		assert result.startswith("refused"), (
			"an unmapped upstream fuel string was written through to the fleet "
			"artefact; `test_fleet_carriers_known` would fail on a real export"
		)
		assert "unknown carrier" in result, (
			f"the refusal did not come from the carrier gate: {result}"
		)
	assert outcome().startswith("accepted"), "the restore did not put it back"


# --------------------------------------------------------------------------
# 02-data-pipeline §6 criterion 2 -- fleet coverage
# --------------------------------------------------------------------------


def test_fleet_coverage_passes_against_a_matching_reference():
	"""§6 criterion 2's content: a fleet that covers the reference passes.

	The gate the plan calls "the one to watch". It was promised in the exit
	criteria and had no implementation and no test, so a fleet covering 60% of
	national capacity would have produced a plausible, wrong capacity mix with
	nothing to catch it.
	"""
	check = validate_fleet_coverage(
		{"geothermal": 900.0, "hydro": 800.0, "coal": 300.0},
		{"geothermal": 900.0, "hydro": 800.0, "coal": 300.0},
		country="KE",
		source="repp_africa",
	)
	assert check.passes
	assert check.coverage_pct == pytest.approx(100.0)
	assert check.missing_mw == {}
	assert check.missing_carriers == []


def test_fleet_coverage_notices_a_missing_carrier():
	"""The gate's canary: drop a carrier and the check must fail, naming it.

	A total that is 10% low can be an aggregate of ten right numbers and one
	hole. The carrier breakdown is what turns "the fleet is short" into "the
	fleet has no geothermal", which is the finding an operator can act on.
	"""
	check = validate_fleet_coverage(
		{"geothermal": 900.0, "hydro": 800.0},
		{"geothermal": 900.0, "hydro": 800.0, "coal": 300.0},
		country="KE",
		source="repp_africa",
	)
	assert not check.passes
	assert check.coverage_pct == pytest.approx(85.0)
	assert check.missing_mw == {"coal": 300.0}
	assert check.missing_carriers == ["coal"]


def test_fleet_coverage_refuses_a_scalar_reference_it_cannot_break_down():
	"""A scalar total answers "how much", not "which". The check reports the
	miss without inventing a carrier mix the source never stated."""
	check = validate_fleet_coverage({"geothermal": 500.0}, 1000.0, country="KE")
	assert not check.passes
	assert check.coverage_pct == pytest.approx(50.0)
	assert check.missing_mw == {}, "a scalar reference must not fabricate a carrier gap"


def test_fleet_coverage_refuses_an_empty_fleet():
	"""A national total cannot be reconciled against a fleet with nothing in it,
	the same refusal the demand analogue makes for a zero series."""
	with pytest.raises(FleetError, match="no capacity"):
		validate_fleet_coverage({}, {"coal": 100.0})
	with pytest.raises(FleetError, match="nothing in it"):
		validate_fleet_coverage({"coal": 0.0}, {"coal": 100.0})


def test_the_fleet_stage_records_that_the_coverage_check_did_not_run(tmp_path: Path):
	"""A missing reference is recorded as *not run*, never as a pass.

	The fail-open this project keeps hitting: absence treated as a green light.
	RePP is SCENARIO-priority and its fetcher reaches a live DOI, so a run
	without a committed export must say the check did not run rather than leave
	a reader to assume full coverage.
	"""
	_write_fleet_export(tmp_path)
	out = tmp_path / "processed" / "fleet.parquet"
	build_stage("fleet", _fleet_config(tmp_path), out)
	_, provenance = read_artefact(out)
	coverage = provenance.parameters["coverage"]
	assert coverage["ran"] is False
	assert "did not run" in str(coverage["reason"])


def test_the_fleet_stage_runs_the_coverage_check_against_a_repp_export(tmp_path: Path):
	"""With a committed cross-check export the stage runs the check and records
	the verdict, so the criterion is a check the workflow performs rather than a
	function nobody calls."""
	_write_fleet_export(tmp_path)
	reference = tmp_path / "raw" / "repp_africa" / "manual"
	reference.mkdir(parents=True, exist_ok=True)
	pd.DataFrame(
		{
			"Country": ["Kenya", "Kenya"],
			"Carrier": ["coal", "geothermal"],
			"Capacity": [600.0, 400.0],
		}
	).to_parquet(reference / "repp.parquet")

	out = tmp_path / "processed" / "fleet.parquet"
	build_stage(
		"fleet",
		_fleet_config(tmp_path),
		out,
		parameters={"repp_export": str(reference / "repp.parquet")},
	)
	_, provenance = read_artefact(out)
	coverage = provenance.parameters["coverage"]
	assert coverage["ran"] is True
	# The built fleet is 1000 MW of coal against a 600 coal / 400 geothermal
	# reference: total coverage is 100%, and the carrier mix is still wrong.
	# That is exactly the failure a total-only check cannot see, and why the
	# carrier breakdown is carried.
	assert coverage["coverage_pct"] == pytest.approx(100.0)
	assert coverage["missing_mw"] == {"geothermal": 400.0}
	assert coverage["excess_mw"] == {"coal": 400.0}
	assert coverage["passes"] is True


def test_the_fleet_coverage_gate_notices_a_fleet_that_lost_a_carrier():
	"""The canary for ``test_fleet_coverage_notices_a_missing_carrier``.

	The mutation keeps the total and drops the per-carrier breakdown, which is
	the defect the gate exists for and the one a total-only check cannot see:
	1000 MW of coal against a 600 coal / 400 geothermal reference covers 100% of
	the megawatts and none of the mix.

	The mutation is *disjoint* from what the gate asserts: it changes which
	numbers are compared, not the threshold. A gate that read only
	``coverage_pct`` would pass both ways and this canary would prove nothing --
	which is exactly the flattened-grouping defect, so it is the right mutation
	to prove the gate is not the total-only check it could have been.

	Run in a fresh interpreter: the mutation is a source edit and this process
	holds the unmutated module in ``sys.modules``.
	"""
	fleet_py = REPO / "src" / "alea" / "planning" / "fleet.py"
	node = "tests/ci/test_stage_output_gates.py::test_fleet_coverage_notices_a_missing_carrier"
	program = (
		"import sys\n"
		"import pytest\n\n"
		f"sys.exit(pytest.main(['-q', '-p', 'no:randomly', {node!r}]))\n"
	)

	shipped = "\t\t\tif gap > 0.0:\n\t\t\t\tmissing[carrier] = gap"
	broken = "\t\t\tif gap > 0.0:\n\t\t\t\tpass  # canary: the carrier gap is dropped"

	assert probe_exit_code(program) == 0, "the gate was already failing"
	with planted(fleet_py, shipped, broken):
		assert probe_exit_code(program) != 0, (
			"a check that drops the per-carrier gap still passed; the gate is "
			"reading the total, not the mix"
		)
	assert probe_exit_code(program) == 0, "the gate did not recover"
