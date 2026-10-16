# SPDX-License-Identifier: MIT
"""`02-data-pipeline.md` §6 criterion 5: every processed artefact carries provenance.

**WHY this module exists.** The criterion -- "Every processed artefact has
provenance with a checksum" -- is a claim about *every* artefact a stage writes,
and it was unverifiable because nothing enumerated what a stage actually wrote.
The gate that named it said "Provenance test", which the register reads as no
gate at all: no promise, no gap, no row.

The enumeration is the point. `build_topology` writes **two** artefacts -- a
Parquet a network builder reads and a GeoJSON a GIS reads (§3 lists the dataset
as "GeoJSON + Parquet") -- and a test written against a hardcoded list would go
stale the day a stage grows a third output, which is exactly how the GeoJSON
went unnoticed. So the artefacts are found by what the stage left on disk.

The second half is the one the plan's own canary describes: a checksum that is
not a function of the payload is reproducible and worthless. `write_artefact`
recomputes the hash on every read, so a sidecar whose `checksum` is a constant
would still pass a reproducibility check and fail a reader. Only the pair means
anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alea.config.loader import load_config
from alea.io.artefacts import sha256_file, store_raw
from alea.io.pipeline import build_stage
from alea.provenance.models import Basis, Licence, Provenance

SIDECAR_SUFFIX = ".provenance.json"


def _raw_provenance() -> Provenance:
	return Provenance(
		source_id="worldbank_grid_map",
		source_url="https://energydata.info/",
		licence=Licence.CC_BY_4_0,
		basis=Basis.MEASURED,
		uncertainty=0.0,
		notes="§6 criterion 5 fixture",
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


def _build(tmp_path: Path, tag: str, payload: dict) -> Path:
	"""Run the shipped ``topology`` stage into a fresh scratch tree.

	``tag`` names the run, so two calls with different tags are two independent
	runs and two calls with the same tag share a raw lake -- the same shape
	`tests/ci/test_deployment_gates.py` uses, and for the same reason: a
	comparison of two directories that could not have collided proves nothing.
	"""
	root = tmp_path / tag / "raw"
	processed = tmp_path / tag / "processed"
	stored = store_raw(
		"worldbank_grid_map",
		json.dumps(payload).encode(),
		_raw_provenance(),
		root=root,
	)
	out = processed / "topology.parquet"
	config = load_config(overrides=[f"paths.raw={root}", f"paths.processed={processed}"])
	result = build_stage(
		"topology",
		config,
		out,
		inputs=[stored.parent.name],
		parameters={"raw_root": str(root)},
	)
	assert not result.skipped, "the fixture stage built nothing; nothing to enumerate"
	return processed


def _payloads(processed: Path) -> list[Path]:
	"""Every artefact the stage wrote, found by what is on disk.

	Not a hardcoded list: a stage that grows a third output must be covered by
	this gate the day it writes one, and a list written here would go stale the
	way ``topology.geojson`` did.
	"""
	return sorted(p for p in processed.iterdir() if not p.name.endswith(SIDECAR_SUFFIX))


def _checksum(processed: Path, payload: Path) -> str:
	"""The checksum a payload's sidecar records, asserting the sidecar exists.

	An assertion rather than a KeyError: the sensitivity half of this gate must
	fail for the same reason the existence half does when a sidecar is missing,
	not for a reason of its own.
	"""
	sidecar = payload.with_suffix(payload.suffix + SIDECAR_SUFFIX)
	assert sidecar.exists(), (
		f"{payload.name} was written with no provenance sidecar; §6 criterion 5 "
		f"is about every processed artefact, and the ones on disk are "
		f"{[p.name for p in _payloads(processed)]}"
	)
	return json.loads(sidecar.read_text(encoding="utf-8")).get("checksum", "")


def test_every_artefact_a_stage_writes_has_provenance_with_a_checksum(tmp_path: Path):
	"""§6 criterion 5, on the artefacts the shipped stage actually produced.

	The checksum is asserted against the payload's own hash, not merely for
	being non-empty: a sidecar carrying a checksum of something else is
	provenance that reads as verification and is not one.
	"""
	processed = _build(tmp_path, "criterion-5", _feature_collection(2))
	written = _payloads(processed)
	assert written, f"the stage wrote no artefact into {processed}"

	observed: dict[str, str] = {}
	for payload in written:
		recorded = _checksum(processed, payload)
		assert recorded, f"{payload.name}: sidecar carries no checksum"
		assert recorded == sha256_file(payload), (
			f"{payload.name}: the recorded checksum does not cover the payload"
		)
		observed[payload.name] = recorded[:12]
	assert len(observed) >= 2, (
		f"the topology stage wrote {sorted(observed)}; §3 declares it as GeoJSON "
		f"+ Parquet, and a gate over one artefact cannot see the other"
	)


def test_the_provenance_checksum_moves_with_the_payload(tmp_path: Path):
	"""The sidecar's checksum is a function of the payload, not a constant.

	A checksum that does not move when the data does is a checksum that verifies
	nothing -- and it is perfectly reproducible, which is why the sensitivity
	half has to be asserted separately from the reproducibility half.
	"""
	whole = _build(tmp_path, "whole", _feature_collection(2))
	perturbed = _build(tmp_path, "perturbed", _feature_collection(1))

	before = {p.name: _checksum(whole, p) for p in _payloads(whole)}
	after = {p.name: _checksum(perturbed, p) for p in _payloads(perturbed)}
	assert set(before) == set(after), (
		f"the same stage wrote different artefact names for the same shape: "
		f"{sorted(before)} vs {sorted(after)}"
	)
	for name in sorted(before):
		assert before[name], f"{name}: an empty checksum on the first run"
		assert before[name] != after[name], (
			f"dropping a transmission corridor left {name}'s recorded checksum "
			f"unchanged; the checksum does not cover the data"
		)


# --------------------------------------------------------------------------
# §6 criterion 7: CRITICAL-tier proxies carry uncertainty_basis="proxy"
# --------------------------------------------------------------------------


def _demand_national(tmp_path: Path, tag: str, countries: list[str]) -> Path:
	"""Run the shipped ``demand_national`` stage over a two-country export."""
	root = tmp_path / tag / "raw"
	processed = tmp_path / tag / "processed"
	export = root / "afdb.csv"
	export.parent.mkdir(parents=True, exist_ok=True)
	pd.DataFrame(
		{
			"country_iso": countries,
			"year": [2020] * len(countries),
			"demand_twh": [0.4 + index for index in range(len(countries))],
		}
	).to_csv(export, index=False)

	out = processed / "demand_national.parquet"
	config = load_config(
		overrides=[
			f"paths.processed={processed}",
			f"scenario.countries={json.dumps(countries)}",
		]
	)
	result = build_stage(
		"demand_national",
		config,
		out,
		inputs=["0" * 64],
		parameters={"afrec_export": str(export)},
	)
	assert not result.skipped, "the fixture stage built nothing"
	return out


def test_a_critical_tier_national_total_carries_a_proxy_basis(tmp_path: Path):
	"""§3.1: "For the seven CRITICAL-tier countries, the national total is
	itself a proxy ... Those artefacts carry ``uncertainty_basis="proxy"`` and
	``uncertainty > 0``."

	Burundi is CRITICAL in the registry; Kenya is HIGH. The stage's own notes
	claimed this behaviour and no code branched on the tier, so the assertion
	is against the provenance a run actually writes rather than against the
	prose describing it.
	"""
	from alea.io.artefacts import read_provenance
	from alea.registry import get_country

	assert get_country("BI").needs_proxy_data, "the fixture's CRITICAL country moved tier"
	assert not get_country("KE").needs_proxy_data, "the fixture's control country moved tier"

	out = _demand_national(tmp_path, "proxy", ["BI", "KE"])
	provenance = read_provenance(out)
	assert provenance.basis is Basis.PROXY, (
		f"a national total covering Burundi was written basis={provenance.basis}; "
		f"§3.1 makes a CRITICAL-tier total a proxy"
	)
	assert provenance.uncertainty > 0.0, (
		"a proxy with zero uncertainty is a claim that the substitute is exact"
	)
	assert provenance.uncertainty_basis == "proxy", (
		f"the artefact records uncertainty_basis={provenance.uncertainty_basis!r}; "
		f"§3.1 names the literal 'proxy'"
	)
	assert provenance.parameters.get("proxy_countries") == ["BI"], (
		f"the artefact does not name which country made it a proxy: "
		f"{provenance.parameters.get('proxy_countries')}"
	)


def test_a_high_tier_national_total_stays_measured(tmp_path: Path):
	"""The gate's other direction.

	A basis that is always ``proxy`` carries no information and would caveat
	every Kenyan number the same way it caveats a Burundian one. Kenya is HIGH,
	so its total is the measured constraint §3.1 says it is.
	"""
	from alea.io.artefacts import read_provenance

	provenance = read_provenance(_demand_national(tmp_path, "measured", ["KE"]))
	assert provenance.basis is Basis.MEASURED, (
		f"a Kenya-only national total was written basis={provenance.basis}; a "
		f"flag that is always on carries no information"
	)
	assert provenance.uncertainty == 0.0
	assert provenance.uncertainty_basis == ""
	assert "proxy_countries" not in provenance.parameters

