# SPDX-License-Identifier: MIT
"""Layer 8 exit criteria, asserted through a real test client.

The plan's ten criteria (docs/plans/11-layer8-api.md §9) are claims about what
the *served* application does, and the plan is explicit about why a claim read
off the source is not enough: a route that is registered is not a route that
works. An inventory of routes read from source is not an inventory of routes the
app serves (a wrapper around ``include_router`` once hid 1,074 of 1,080), a
handler that never resolves its repository raises at call time rather than
import time, and a response model that forbids extras 422s on the payload the
store actually holds.

So every test here drives ``fastapi.testclient.TestClient`` against an
application built from a scratch repository root, with real artefacts written by
``alea.io.artefacts.write_artefact`` and real keys minted through the API. No
mocks: the whole point is that the dependency resolves rather than raising.

Two defects this module found and now guards, both of which returned a 200-shaped
route that could not answer:

* ``GET /signals/{id}`` validated the stored ``Signal`` payload directly against
  ``SignalOut``, which forbids extras, so every read of a real signal was a 422.
* ``GET /losses/decompose`` iterated ``_nested(...)`` as ``(_, component)`` pairs
  while ``_nested`` returns dicts, so it raised ``ValueError`` on any country
  with a published decomposition.

The scratch root is installed by monkeypatching ``alea.config.paths.repo_root``
after the config is loaded, because ``load_config`` reads the real default file
but every artefact path resolves through ``repo_root``. Patching first would
make the default file unfindable, which is why the order matters and why it is
written down here.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from alea.api.app import create_app
from alea.api.views import SMS_MAX_CHARS, USSD_MAX_CHARS
from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.artefacts import write_artefact
from alea.provenance.models import Basis, DerivedProvenance

ADMIN_KEY = "alea_admin_" + "0" * 40
"""A valid-shaped bootstrap key. The id is ``admin`` and the secret is the rest."""

# The spec's §3.1 endpoint table, as (method, path) with the API prefix. A route
# is "implemented" only if it is served *and* answers a real request -- the
# served-ness is checked against the inventory and the answering is checked by
# the smoke test below, which calls each one.
SPEC_ENDPOINTS: tuple[tuple[str, str], ...] = (
	("GET", "/api/v1/scenarios"),
	("GET", "/api/v1/scenarios/{scenario_id}"),
	("GET", "/api/v1/scenarios/{scenario_id}/results"),
	("GET", "/api/v1/prices"),
	("GET", "/api/v1/capture-rates"),
	("GET", "/api/v1/ppa-benchmarks"),
	("GET", "/api/v1/outages/forecast"),
	("GET", "/api/v1/outages/history"),
	("GET", "/api/v1/outages/validate"),
	("GET", "/api/v1/maintenance/predict"),
	("GET", "/api/v1/losses/decompose"),
	("GET", "/api/v1/losses/tlens"),
	("GET", "/api/v1/losses/mitigate"),
	("GET", "/api/v1/resilience/metrics"),
	("GET", "/api/v1/resilience/contingency"),
	("POST", "/api/v1/whatif/solve"),
	("POST", "/api/v1/whatif/compare"),
	("POST", "/api/v1/whatif/frontier"),
	("GET", "/api/v1/reports/{cadence}"),
	("GET", "/api/v1/reports/{cadence}/{report_date}"),
	("GET", "/api/v1/signals"),
	("GET", "/api/v1/signals/{signal_id}"),
	("POST", "/api/v1/signals/review"),
	("GET", "/api/v1/health"),
	("GET", "/api/v1/version"),
	("GET", "/api/v1/runs/{run_id}"),
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _provenance(**overrides: object) -> DerivedProvenance:
	"""A derived provenance with the fields every artefact must carry."""
	fields: dict[str, object] = {
		"source_id": "test_fixture",
		"basis": Basis.MEASURED,
		"uncertainty": 0.0,
		"inputs": ["fixture-input"],
		"code_version": "0.1.0",
	}
	fields.update(overrides)
	return DerivedProvenance(**fields)  # type: ignore[arg-type]


def _write(root: Path, relative: str, data: object, **prov: object) -> str:
	"""Write one artefact under the scratch root. Returns its checksum."""
	return write_artefact(root / relative, data, _provenance(**prov))


def _population_artefacts(root: Path) -> None:
	"""Every tabular artefact the API serves, so each route has data to read.

	Written as real artefacts with provenance sidecars: a route that reads a
	missing artefact returns an empty page, which would let a broken read path
	pass the smoke test. The values are deliberately unremarkable; what is
	under test is that the route resolves its dependency and serialises the row.
	"""
	_write(
		root,
		"data/processed/market/prices.parquet",
		pd.DataFrame(
			{
				"at": pd.to_datetime(["2026-01-01T00:00:00Z"]),
				"country_iso": ["KE"],
				"price": [80.0],
				"unit": ["USD/MWh"],
			}
		),
	)
	_write(
		root,
		"data/processed/market/capture_rates.parquet",
		pd.DataFrame(
			{
				"technology": ["solar"],
				"vre_penetration": [0.1],
				"capture_rate": [0.95],
				"capture_price": [76.0],
			}
		),
	)
	_write(
		root,
		"data/processed/market/ppa_benchmarks.parquet",
		pd.DataFrame(
			{
				"technology": ["solar"],
				"country_iso": ["KE"],
				"ppa_price": [60.0],
				"tenor_years": [20],
				"benchmark_source": ["IRENA"],
			}
		),
	)
	_write(
		root,
		"data/processed/outages/forecast.parquet",
		pd.DataFrame(
			{
				"country_iso": ["KE"],
				"grid_zone": ["Nairobi"],
				"probability": [0.72],
				"horizon_hours": [24],
				"issued_at": pd.to_datetime(["2026-01-01T00:00:00Z"]),
				"model_version": ["v1"],
			}
		),
	)
	_write(
		root,
		"data/processed/outages/history.parquet",
		pd.DataFrame(
			{
				"event_id": ["e1"],
				"country_iso": ["KE"],
				"grid_zone": ["Nairobi"],
				"started_at": pd.to_datetime(["2026-01-01T00:00:00Z"]),
				"duration_minutes": [60.0],
				"customers_affected": [1000.0],
				"cause": ["line fault"],
			}
		),
	)
	_write(
		root,
		"data/processed/outages/validation.parquet",
		pd.DataFrame(
			{
				"country_iso": ["KE"],
				"grid_zone": ["Nairobi"],
				"period_start": pd.to_datetime(["2026-01-01"]),
				"period_end": pd.to_datetime(["2026-02-01"]),
				"auc": [0.8],
				"precision": [0.7],
				"recall": [0.6],
				"sample_size": [100],
			}
		),
	)
	_write(
		root,
		"data/processed/maintenance/predictions.parquet",
		pd.DataFrame(
			{
				"asset_id": ["a1"],
				"asset_type": ["transformer"],
				"country_iso": ["KE"],
				"failure_probability": [0.3],
				"window_days": [30],
				"recommended_action": ["inspect"],
				"model_version": ["v1"],
			}
		),
	)
	_write(
		root,
		"data/processed/losses/decomposition.parquet",
		pd.DataFrame(
			{
				"country_iso": ["KE"],
				"period_start": pd.to_datetime(["2023-01-01"]),
				"period_end": pd.to_datetime(["2023-12-31"]),
				"total_loss": [1000.0],
				"components": [
					json.dumps(
						[
							{"component": "technical", "loss": 600.0, "share": 0.6},
							{"component": "non_technical", "loss": 400.0, "share": 0.4},
						]
					)
				],
			}
		),
	)
	_write(
		root,
		"data/processed/losses/tlens.parquet",
		pd.DataFrame(
			{
				"country_iso": ["KE"],
				"year": [2023],
				"transmission_loss_pct": [3.0],
				"distribution_loss_pct": [8.0],
				"collection_loss_pct": [1.0],
				"basis_note": ["regional proxy"],
			}
		),
	)
	_write(
		root,
		"data/processed/losses/mitigation.parquet",
		pd.DataFrame(
			{
				"country_iso": ["KE"],
				"option": ["reconductor"],
				"loss_reduction": [100.0],
				"capex": [1.0e6],
				"payback_years": [5.0],
			}
		),
	)
	_write(
		root,
		"data/processed/resilience/metrics.parquet",
		pd.DataFrame(
			{
				"metric": ["SAIDI"],
				"country_iso": ["KE"],
				"value": [12.0],
				"unit": ["hours"],
				"period": ["2023"],
			}
		),
	)
	_write(
		root,
		"data/processed/resilience/contingency.parquet",
		pd.DataFrame(
			{
				"element_id": ["L1"],
				"element_type": ["line"],
				"country_iso": ["KE"],
				"load_shed_mw": [50.0],
				"overloaded_elements": [1],
				"severity": ["high"],
			}
		),
	)


def _catalogue_artefacts(root: Path) -> None:
	"""The scenario catalogue, its solved result, and a report."""
	index = root / "results/scenarios/index.json"
	index.parent.mkdir(parents=True, exist_ok=True)
	index.write_text(
		json.dumps(
			{
				"scenarios": [
					{
						"scenario_id": "base",
						"name": "Base",
						"countries": ["KE"],
						"planning_horizons": [2030],
						"clusters": [55],
						"created_at": "2026-01-01T00:00:00+00:00",
					}
				]
			}
		),
		encoding="utf-8",
	)
	_write(
		root,
		"results/scenarios/base/scenario.json",
		{
			"scenario_id": "base",
			"name": "Base",
			"countries": ["KE"],
			"planning_horizons": [2030],
			"clusters": [55],
			"created_at": "2026-01-01T00:00:00+00:00",
			"network_checksum": "abc",
			"code_version": "0.1.0",
		},
	)
	_write(
		root,
		"results/scenarios/base/results/2030.json",
		{
			"objective": 1.0e9,
			"total_capacity_mw": 2100.0,
			"capacity_mix": [{"carrier": "solar", "capacity_mw": 1000.0, "share": 0.5}],
			"solved_at": "2026-01-01T00:00:00+00:00",
			"network_checksum": "abc",
		},
	)
	report_dir = root / "reports/daily"
	report_dir.mkdir(parents=True, exist_ok=True)
	(report_dir / "index.json").write_text(
		json.dumps(
			{
				"reports": [
					{
						"report_date": "2026-10-11",
						"title": "Daily",
						"generated_at": "2026-10-11T06:00:00+00:00",
						"cadence": "daily",
						"formats": ["pdf"],
					}
				]
			}
		),
		encoding="utf-8",
	)
	_write(
		root,
		"reports/daily/2026-10-11.json",
		{
			"report_date": "2026-10-11",
			"title": "Daily",
			"generated_at": "2026-10-11T06:00:00+00:00",
			"cadence": "daily",
			"formats": ["pdf"],
		},
	)


def _run_log(root: Path) -> None:
	(root / "results").mkdir(parents=True, exist_ok=True)
	(root / "results/runs.jsonl").write_text(
		json.dumps(
			{
				"run_id": "run-1",
				"component": "solve",
				"started_at": "2026-01-01T00:00:00+00:00",
				"status": "succeeded",
				"artefacts": ["a"],
			}
		)
		+ "\n",
		encoding="utf-8",
	)


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
	"""A loaded config whose every relative path resolves under ``tmp_path``.

	The config is loaded first (from the real default file) and ``repo_root`` is
	patched after, because ``load_config`` reads ``config/config.default.yaml``
	through ``repo_root`` -- patch first and the default file is not found.
	"""
	loaded = load_config()
	monkeypatch.setenv("ALEA_API_ADMIN_KEY", ADMIN_KEY)
	# Patch the module attribute, not the name imported into ``alea.config``:
	# every artefact path resolves through ``alea.config.paths.resolve``, which
	# calls ``repo_root`` as a module global, so patching the function object in
	# its own module is what redirects every relative path to ``tmp_path``.
	import alea.config.paths as paths

	monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
	return loaded


@pytest.fixture
def scratch(config: Config, tmp_path: Path) -> Path:
	"""A repository root populated with every artefact the routes read."""
	_population_artefacts(tmp_path)
	_catalogue_artefacts(tmp_path)
	_run_log(tmp_path)
	return tmp_path


@pytest.fixture
def client(config: Config, scratch: Path) -> Iterator[TestClient]:
	"""A running application over the scratch root, with the lifespan entered."""
	app = create_app(config)
	with TestClient(app) as test_client:
		yield test_client


def _key(client: TestClient, tier: str) -> dict[str, str]:
	"""Mint a key of ``tier`` through the API and return its auth header."""
	response = client.post(
		"/api/v1/keys",
		json={"name": f"fixture-{tier}", "tier": tier},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert response.status_code == 201, response.text
	return {"X-API-Key": response.json()["key"]}


@pytest.fixture
def keys(client: TestClient) -> dict[str, dict[str, str]]:
	"""One key per tier, minted through the admin bootstrap key."""
	return {tier: _key(client, tier) for tier in ("public", "analyst", "restricted", "internal")}


# --------------------------------------------------------------------------
# Criterion 1 -- every endpoint in §3.1 is implemented
# --------------------------------------------------------------------------


def test_the_route_inventory_sees_every_spec_endpoint(config: Config) -> None:
	"""Each §3.1 endpoint is served, read from the running application.

	Read from ``route_inventory`` (the unwrapping walk), not from ``app.routes``:
	an included router's entry has ``path=None``, so a naive walk undercounts by
	everything the routers carry and its total is internally consistent and
	wrong (11-layer8 §9).

	The table names endpoints, not path templates -- ``/scenarios/{id}`` is one
	route whose id the router spells ``{scenario_id}``. So the served paths are
	compared by shape, and a spec template matches when some served path has the
	same literal segments with a parameter in each of its own.
	"""
	from alea.api.inventory import route_inventory

	app = create_app(config)
	served = {(method, route.path) for route in route_inventory(app) for method in route.methods}
	missing = [
		endpoint
		for endpoint in SPEC_ENDPOINTS
		if not any(
			method == endpoint[0] and _same_shape(path, endpoint[1]) for method, path in served
		)
	]
	assert not missing, f"the application does not serve: {missing}"


def test_every_spec_endpoint_answers_a_real_request(client: TestClient, keys: dict) -> None:
	"""Every §3.1 endpoint answers, through the client, against real data.

	This is the criterion the plan cares about: registered is not working. A
	route whose repository read raises, whose response model rejects the stored
	payload, or whose dependency does not resolve fails here and nowhere else.
	"""
	requests: list[tuple[str, str, str, dict | None]] = [
		("GET", "/api/v1/scenarios", "public", None),
		("GET", "/api/v1/scenarios/base", "public", None),
		("GET", "/api/v1/scenarios/base/results?horizon=2030", "public", None),
		("GET", "/api/v1/prices", "public", None),
		("GET", "/api/v1/capture-rates", "public", None),
		("GET", "/api/v1/ppa-benchmarks", "public", None),
		("GET", "/api/v1/outages/forecast?country=KE", "public", None),
		("GET", "/api/v1/outages/history", "public", None),
		("GET", "/api/v1/outages/validate", "analyst", None),
		("GET", "/api/v1/maintenance/predict", "restricted", None),
		("GET", "/api/v1/losses/decompose?country=KE", "analyst", None),
		("GET", "/api/v1/losses/tlens", "analyst", None),
		("GET", "/api/v1/losses/mitigate?country=KE", "analyst", None),
		("GET", "/api/v1/resilience/metrics", "analyst", None),
		("GET", "/api/v1/resilience/contingency", "analyst", None),
		("GET", "/api/v1/reports/daily", "public", None),
		("GET", "/api/v1/reports/daily/2026-10-11", "public", None),
		("GET", "/api/v1/signals", "restricted", None),
		("GET", "/api/v1/health", "public", None),
		("GET", "/api/v1/version", "public", None),
		("GET", "/api/v1/runs/run-1", "public", None),
	]
	for method, path, tier, body in requests:
		response = client.request(method, path, headers=keys[tier], json=body)
		assert response.status_code == 200, f"{method} {path} -> {response.status_code}: {response.text}"

	# The three what-if POSTs take a body and answer 202 with a job.
	for path, body in (
		(
			"/api/v1/whatif/solve",
			{"base_scenario_id": "base", "parameters": {"demand_growth": 0.05}},
		),
		("/api/v1/whatif/compare", {"scenario_ids": ["base", "base"], "horizon": 2030}),
		(
			"/api/v1/whatif/frontier",
			{"base_scenario_id": "base", "parameter": "demand_growth", "start": 0.0, "stop": 0.05},
		),
	):
		response = client.post(path, headers=keys["analyst"], json=body)
		assert response.status_code == 202, f"POST {path} -> {response.status_code}: {response.text}"
		assert response.json()["job_id"], f"POST {path} returned no job id"


def test_the_signal_route_serves_a_stored_signal(client: TestClient, keys: dict) -> None:
	"""``GET /signals/{id}`` reads back a signal the store holds.

	The stored payload is a full ``Signal``; ``SignalOut`` forbids extras. A read
	that validates the payload against the wire model directly raises a 422 on
	every real signal, which is the defect this asserts is gone.
	"""
	from alea.signals.models import Signal, SignalType

	signal = Signal(
		signal_type=SignalType.GENERATION_INVESTMENT,
		confidence=0.8,
		source_document_id="d1",
		source_url="https://example.org/a",
		source_name="example",
		country_iso="KE",
		capacity_mw=2100.0,
		investment_usd=5.0e8,
		description="a plant",
	)
	client.portal.call(client.app.state.api.signal_store.add, signal)  # type: ignore[attr-defined]

	response = client.get(f"/api/v1/signals/{signal.signal_id}", headers=keys["restricted"])
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["signal_id"] == signal.signal_id
	assert body["capacity_mw"]["value"] == 2100.0
	assert body["capacity_mw"]["unit"] == "MW"
	assert body["investment_usd"]["value"] == 5.0e8


# --------------------------------------------------------------------------
# Criterion 2 -- no GET takes a body; no route blocks on a solver
# --------------------------------------------------------------------------


def _get_operations(spec: dict) -> list[tuple[str, dict]]:
	return [
		(path, operations["get"])
		for path, operations in spec["paths"].items()
		if "get" in operations
	]


def _get_with_body_offenders(spec: dict) -> list[str]:
	"""GET operations that declare a ``requestBody``."""
	return [path for path, operation in _get_operations(spec) if "requestBody" in operation]


def test_no_get_with_body(config: Config) -> None:
	"""No GET operation declares a ``requestBody``.

	A GET with a body is not cacheable, not linkable, and dropped silently by
	many clients -- so the endpoint looks like it works and returns the wrong
	answer (11-layer8 §2.1). A GET handler with a plain Pydantic parameter emits
	a ``requestBody``; the check reads the generated document, not the source.
	"""
	app = create_app(config)
	offenders = _get_with_body_offenders(app.openapi())
	assert not offenders, f"GET operations that declare a request body: {offenders}"


SOLVER_PATTERN = re.compile(r"\b(?:solve_expansion|solve_what_if|network\.optimize|optimize\()")
"""A call to a solve entry point, which is the shape the inline-solve defect takes."""


def _inline_solver_offenders(package: Path) -> list[str]:
	"""Route source files that call a solver outside the worker."""
	offenders: list[str] = []
	for module in sorted(package.rglob("*.py")):
		if module.name == "whatif.py":
			# The what-if *handler* legitimately solves: it runs in the worker,
			# outside the request path, which is exactly the design.
			continue
		for number, line in enumerate(module.read_text(encoding="utf-8").splitlines(), start=1):
			code = line.split("#", 1)[0]
			if SOLVER_PATTERN.search(code):
				offenders.append(f"{module.relative_to(package)}:{number}")
	return offenders


def test_no_blocking_solve_in_route() -> None:
	"""No route module calls a solver inline.

	A solve inside a route blocks the event loop for minutes to hours
	(11-layer8 §2.3). Every slow path is a job: the route enqueues and the
	worker runs. The scan is over the route and adapter source for a call to a
	solve entry point, which is the shape the defect takes.
	"""
	import alea.api

	offenders = _inline_solver_offenders(Path(alea.api.__file__).parent)
	assert not offenders, f"a solver is called inline in a route: {offenders}"


# --------------------------------------------------------------------------
# Criterion 3 -- keys hashed, tiered, revocable
# --------------------------------------------------------------------------


def test_keys_stored_hashed(client: TestClient) -> None:
	"""No plaintext key appears in the key store; a revoked key is distinct.

	The specification's ``VALID_KEYS`` is a list of plaintext keys. Here the
	store holds only scrypt hashes, and revocation is a state rather than a
	delete, so a revoked key and a nonexistent one are told apart by their code --
	§8 ``test_revoked_key_distinguishable``. The canary in
	``tests/ci/canaries/test_api_gates.py`` collapses the two failure codes and
	watches this fail.
	"""
	minted = client.post(
		"/api/v1/keys",
		json={"name": "leak-check", "tier": "analyst"},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert minted.status_code == 201
	plaintext = minted.json()["key"]

	database = client.app.state.api.key_store.database.path  # type: ignore[attr-defined]
	raw = database.read_bytes()
	# ``split_presented``, not ``rsplit("_", 1)``: the secret is base64url, whose
	# alphabet includes ``_``, so splitting on the last underscore yields a
	# one-character fragment and the check passes against a plaintext store.
	from alea.api.auth import split_presented

	_, secret = split_presented(plaintext) or ("", "")
	assert len(secret) > 20, "the presented key did not split into id and secret"
	assert secret.encode() not in raw, "the key's secret is stored in plaintext"
	assert b"scrypt$" in raw, "no scrypt hash is present; keys may not be hashed"

	# Revoke, then assert the revoked key and an unknown key carry different codes.
	key_id = minted.json()["key_id"]
	assert (
		client.delete(f"/api/v1/keys/{key_id}", headers={"X-API-Key": ADMIN_KEY}).status_code == 204
	)
	revoked = client.get("/api/v1/health", headers={"X-API-Key": plaintext})
	assert revoked.status_code == 403
	assert revoked.json()["code"] == "revoked_key"
	unknown = client.get("/api/v1/health", headers={"X-API-Key": f"alea_{'9' * 36}_{'z' * 8}"})
	assert unknown.status_code == 401
	assert unknown.json()["code"] == "unknown_key"


def test_keys_are_tiered(client: TestClient, keys: dict) -> None:
	"""A key reaches exactly its tier and no further."""
	assert client.get("/api/v1/prices", headers=keys["public"]).status_code == 200
	assert client.get("/api/v1/losses/tlens", headers=keys["public"]).status_code == 403
	assert client.get("/api/v1/losses/tlens", headers=keys["analyst"]).status_code == 200
	assert client.get("/api/v1/signals", headers=keys["analyst"]).status_code == 403
	assert client.get("/api/v1/signals", headers=keys["restricted"]).status_code == 200
	assert client.get("/api/v1/keys", headers=keys["restricted"]).status_code == 403
	assert client.get("/api/v1/keys", headers=keys["internal"]).status_code == 200


# --------------------------------------------------------------------------
# The cache key covers the artefact checksum (11-layer8 §6)
# --------------------------------------------------------------------------


def test_cache_key_includes_checksum() -> None:
	"""§8 ``test_cache_key_includes_checksum``: a different artefact is a different key.

	The plan's cache rule (§6): a key over the URL alone serves a result
	computed against a previous network -- the same defect as Layer 5's
	``hash()``-based key. The checksum is the component that makes that
	impossible, so the key must move when the artefact does. The canary in
	``tests/ci/canaries/test_api_gates.py`` drops the checksum from the key and
	watches this fail.
	"""
	from alea.api.middleware import cache_key

	params: dict[str, object] = {"country": "KE", "horizon_hours": 24}
	one = cache_key("outages.forecast", checksum="sha256:" + "ab" * 32, params=params)
	two = cache_key("outages.forecast", checksum="sha256:" + "cd" * 32, params=params)
	assert one != two, "the key ignored the artefact checksum"

	# The checksum is not the only component. An endpoint- or parameter-only
	# key would collide the other way -- two different requests sharing an entry
	# -- so both must move the key too.
	assert cache_key("prices", checksum="sha256:" + "ab" * 32, params=params) != one
	assert (
		cache_key("outages.forecast", checksum="sha256:" + "ab" * 32, params={"country": "TZ"}) != one
	)


# --------------------------------------------------------------------------
# Criterion 4 -- rate limiting per key and tier
# --------------------------------------------------------------------------


def _with_rate_limit(config: Config, per_minute: int) -> Config:
	"""A copy of the config with a lower base rate limit.

	``ApiConfig`` is frozen, so the base limit cannot be monkeypatched onto the
	loaded config -- pydantic refuses the assignment. Rebuilding the two models
	the limit flows through (``config.api`` and ``config``) is the honest way to
	change a value the contract says is immutable.
	"""
	api = config.api.model_copy(update={"rate_limit_per_minute": per_minute})
	return config.model_copy(update={"api": api})


def test_rate_limit_enforced(config: Config, scratch: Path) -> None:
	"""Exceeding the limit returns 429 with the rate headers.

	The limit is lowered to three so the refusal is reached without sixty
	requests. The headers are asserted on the successful responses too: a client
	that only learns it is over the limit by being refused cannot back off.
	"""
	app = create_app(_with_rate_limit(config, 3))
	with TestClient(app) as client:
		headers = _key(client, "public")
		seen: list[str] = []
		for _ in range(3):
			response = client.get("/api/v1/health", headers=headers)
			assert response.status_code == 200
			seen.append(response.headers["X-RateLimit-Remaining"])
		assert seen == ["2", "1", "0"], f"remaining did not count down: {seen}"

		refused = client.get("/api/v1/health", headers=headers)
		assert refused.status_code == 429
		assert refused.headers["X-RateLimit-Limit"] == "3"
		assert refused.headers["X-RateLimit-Remaining"] == "0"
		assert int(refused.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_key(config: Config, scratch: Path) -> None:
	"""One key exhausting its allowance does not affect another.

	"Per key and per tier" is the plan's wording; a limiter keyed on the
	address would collapse every key behind one gateway into one bucket.
	"""
	app = create_app(_with_rate_limit(config, 2))
	with TestClient(app) as client:
		first = _key(client, "public")
		second = _key(client, "public")
		for _ in range(2):
			assert client.get("/api/v1/health", headers=first).status_code == 200
		assert client.get("/api/v1/health", headers=first).status_code == 429
		# The second key has spent nothing.
		assert client.get("/api/v1/health", headers=second).status_code == 200


# --------------------------------------------------------------------------
# Criterion 5 -- every value carries its basis
# --------------------------------------------------------------------------

# Numeric fields that are identifiers, counts, confidences, probabilities,
# coordinates, years or durations -- not quantities that carry a unit and a
# basis. The value contract is about measured and modelled quantities, and the
# names here are the ones the plan's own models use for the non-quantities.
NON_QUANTITY_FIELDS = frozenset(
	{
		"attempts",
		"clusters",
		"confidence",
		"horizon",
		"horizon_hours",
		"jobs_queued",
		"jobs_running",
		"lat",
		"limit",
		"lon",
		"offset",
		"overloaded_elements",
		"planning_horizons",
		"points",
		"progress",
		"sample_size",
		"tenor_years",
		"total",
		"uncertainty",
		"uptime_seconds",
		"value",
		"window_days",
		"year",
	}
)

REGISTRY_REFERENCE_FIELDS: dict[str, frozenset[str]] = {
	"CountryOut": frozenset({"population"}),
	"TechnologyOut": frozenset({"co2_intensity_t_per_mwh"}),
}
"""Registry reference numbers, exempt from the value contract, per model.

``Country.population`` and ``Technology.co2_t_per_mwh`` are static reference
metadata read from ``alea.registry``. The registry records no basis and no
uncertainty for either, so wrapping them in a :class:`ValueOut` would force an
uncertainty to be invented -- the one thing the contract exists to prevent -- or
assert ``basis='measured'`` about a UN population round figure and an IPCC
emissions factor. They are exempted by name and per model, not added to
:data:`NON_QUANTITY_FIELDS`: exempting the *field name* would also exempt a
genuinely modelled ``population`` on any future response model, which is exactly
the regression this gate exists to catch. The list is asserted live in the test,
so a rename cannot make it absorb a new field.
"""

FRAMEWORK_COMPONENTS: frozenset[str] = frozenset({"HTTPValidationError", "ValidationError"})
"""FastAPI's own error models. Not this API's to wrap."""


def _exempt_fields(component: str) -> frozenset[str]:
	"""The reference fields exempt for ``component``, plus its framework bases.

	``Page[CountryOut]`` reaches ``population`` through ``items``; the field is
	declared on ``CountryOut``, so the exemption is resolved through the ``Page_``
	wrapper's inner model rather than duplicated on every page type.
	"""
	assert component, "an exemption lookup needs a component name"
	if component in REGISTRY_REFERENCE_FIELDS:
		return REGISTRY_REFERENCE_FIELDS[component]
	inner = re.fullmatch(r"Page_(\w+)_", component)
	if inner and inner.group(1) in REGISTRY_REFERENCE_FIELDS:
		return REGISTRY_REFERENCE_FIELDS[inner.group(1)]
	return frozenset()


def _numeric_response_fields(spec: dict, name: str, *, trace: str = "") -> list[str]:
	"""Bare numeric property names reachable from a named component's schema.

	Resolves ``$ref`` chains (depth-bounded) and unions, so a quantity nested
	inside a row model is found. ``ValueOut``'s own ``value``/``uncertainty``
	are skipped: the contract is that a quantity is *wrapped* in a ValueOut, and
	the wrapper's members are numbers by design. ``ProvenanceOut.uncertainty`` is
	skipped for the same reason -- provenance *is* the basis, so the number on it
	is the basis's own magnitude, not a quantity that lacks one.

	``trace`` carries the dotted path of the property currently being walked, so
	a bare number under a ``provenance`` property is exempted while the same
	field name elsewhere is not.
	"""
	components = spec["components"]["schemas"]
	found: list[str] = []

	def walk(schema: object, seen: frozenset[str], trace: str) -> None:
		if not isinstance(schema, dict):
			return
		if "$ref" in schema:
			target = schema["$ref"].split("/")[-1]
			if target in ("ValueOut", "ProvenanceOut") or target in seen:
				return
			walk(components.get(target, {}), seen | {target}, trace)
			return
		if schema.get("type") in ("number", "integer"):
			# Name the bare number after the property it is under, so a failure
			# says which field to wrap rather than a bare "(bare)".
			found.append(trace.rsplit(".", 1)[-1] or "(bare)")
		for prop, sub in (schema.get("properties") or {}).items():
			under_provenance = trace.endswith("provenance") or prop == "provenance"
			if isinstance(sub, dict) and sub.get("type") in ("number", "integer"):
				if under_provenance:
					continue
				found.append(prop)
			else:
				walk(sub, seen, f"{trace}.{prop}")
		for sub in schema.get("anyOf") or []:
			walk(sub, seen, trace)
		if "items" in schema:
			walk(schema["items"], seen, trace)

	walk({"$ref": f"#/components/schemas/{name}"}, frozenset(), trace)
	return found


def _response_components(spec: dict) -> set[str]:
	"""Every component reachable from a documented operation's response.

	The value contract is a claim about what a client receives, so the check is
	scoped to response schemas and their transitive ``$ref`` closure. Request
	models (``ScenarioParametersIn`` and the like) are inputs: a demand-growth
	scalar is a knob a caller turns, not a quantity the API asserts, and flagging
	it would make the gate fail for a reason its operator cannot act on.
	"""
	components = spec["components"]["schemas"]
	roots: set[str] = set()

	def refs(node: object) -> list[str]:
		out: list[str] = []
		if isinstance(node, dict):
			for key, value in node.items():
				if key == "$ref":
					out.append(value.split("/")[-1])
				else:
					out.extend(refs(value))
		elif isinstance(node, list):
			for value in node:
				out.extend(refs(value))
		return out

	for operations in spec["paths"].values():
		for method, operation in operations.items():
			if method not in ("get", "post", "put", "patch", "delete"):
				continue
			for response in (operation.get("responses") or {}).values():
				roots.update(refs(response))

	reachable = set(roots)
	frontier = list(roots)
	while frontier:
		for ref in refs(components.get(frontier.pop(), {})):
			if ref not in reachable:
				reachable.add(ref)
				frontier.append(ref)
	return reachable


def _bare_quantity_offenders(spec: dict) -> dict[str, list[str]]:
	"""Response models that expose a bare quantity where a ValueOut belongs."""
	offenders: dict[str, list[str]] = {}
	for name in sorted(_response_components(spec)):
		if name in FRAMEWORK_COMPONENTS:
			continue
		exempt = _exempt_fields(name)
		bare = [
			f
			for f in _numeric_response_fields(spec, name)
			if f not in NON_QUANTITY_FIELDS and f not in exempt
		]
		if bare:
			offenders[name] = sorted(set(bare))
	return offenders


def test_values_carry_basis(config: Config) -> None:
	"""No response model exposes a bare quantity where a ValueOut belongs.

	Every quantity in the spec's models is a ``ValueOut`` (11-layer8 §3.3). The
	check enumerates the numeric fields of every response-reachable schema and
	asserts the only bare numbers are the non-quantities named above -- so a new
	field like ``capacity_mw: float`` fails here rather than shipping.

	Two exemptions, each asserted live below so a rename cannot make it silently
	absorb a new field:

	* the registry reference fields (``population``, ``co2_intensity_t_per_mwh``)
	  -- see :data:`REGISTRY_REFERENCE_FIELDS`;
	* the framework's own error models, which this API does not define.
	"""
	app = create_app(config)
	spec = app.openapi()
	offenders = _bare_quantity_offenders(spec)
	assert not offenders, f"response models with bare quantities: {offenders}"

	# The exemptions are live, not stale: each named field still appears in the
	# response it exempts. A rename that emptied the exemption would otherwise
	# leave the gate passing while the reason for the exemption no longer held.
	present = {
		field
		for name in _response_components(spec)
		for field in _numeric_response_fields(spec, name)
	}
	for inner, fields in REGISTRY_REFERENCE_FIELDS.items():
		for field in fields:
			assert field in present, (
				f"the exemption for {inner}.{field} is stale: no response exposes "
				f"{field!r} any more"
			)


def test_signal_quantities_are_values(client: TestClient, keys: dict) -> None:
	"""A signal's capacity and investment are served as ValueOut, not floats.

	An extracted quantity is unconfirmed by construction, so serving it as
	``{"capacity_mw": 2100}`` invites a dashboard to render it as measured.
	"""
	from alea.signals.models import Signal, SignalType

	signal = Signal(
		signal_type=SignalType.GENERATION_INVESTMENT,
		confidence=0.75,
		source_document_id="d1",
		source_url="https://example.org/a",
		source_name="example",
		country_iso="KE",
		capacity_mw=2100.0,
	)
	client.portal.call(client.app.state.api.signal_store.add, signal)  # type: ignore[attr-defined]
	body = client.get(f"/api/v1/signals/{signal.signal_id}", headers=keys["restricted"]).json()
	capacity = body["capacity_mw"]
	assert isinstance(capacity, dict), f"capacity_mw is not a value object: {capacity!r}"
	assert capacity["unit"] == "MW"
	assert capacity["basis"] == "modelled", "an extraction is modelled, not measured"
	assert capacity["uncertainty"] > 0, "an extracted value must state its uncertainty"


# --------------------------------------------------------------------------
# Criterion 6 -- long jobs durable across restart
# --------------------------------------------------------------------------


def test_job_survives_restart(config: Config, scratch: Path, keys: dict) -> None:
	"""A job submitted before a restart is readable after it.

	The store is a file, not a dict: a job that dies with the process is a job
	whose result the caller never learns (11-layer8 §3.2). This submits through
	one application, closes it, opens a second over the same root, and reads the
	job back.
	"""
	body = {"base_scenario_id": "base", "parameters": {"demand_growth": 0.05}}
	first = create_app(config)
	with TestClient(first) as client:
		submitted = client.post("/api/v1/whatif/solve", headers=keys["analyst"], json=body)
		assert submitted.status_code == 202, submitted.text
		job_id = submitted.json()["job_id"]
		assert submitted.json()["status_url"] == f"/api/v1/jobs/{job_id}"

	second = create_app(config)
	with TestClient(second) as client:
		status = client.get(f"/api/v1/jobs/{job_id}", headers=keys["public"])
		assert status.status_code == 200, status.text
		assert status.json()["job_id"] == job_id


def test_an_unfinished_job_result_is_a_conflict(config: Config, scratch: Path, keys: dict) -> None:
	"""A result requested before the job finishes is a 409, not a 404.

	The job exists and the caller should keep polling; conflating that with
	"no such job" makes a two-hour solve look lost.
	"""
	app = create_app(config)
	with TestClient(app) as client:
		submitted = client.post(
			"/api/v1/whatif/compare",
			headers=keys["analyst"],
			json={"scenario_ids": ["base", "base"], "horizon": 2030},
		)
		job_id = submitted.json()["job_id"]
		# Freeze the worker so the job cannot complete between the two calls: with
		# no handler registered the claim fails the job rather than finishing it,
		# and a job that is not ``succeeded`` -- queued, running or failed -- is a
		# 409 from the result route, never a 404.
		client.app.state.api.worker._handlers.clear()  # type: ignore[attr-defined]
		result = client.get(f"/api/v1/jobs/{job_id}/result", headers=keys["public"])
		assert result.status_code == 409, result.text


# --------------------------------------------------------------------------
# Criterion 7 -- USSD and SMS adapters complete and bounded
# --------------------------------------------------------------------------


def ussd_gate_holds(message: str, *, omitted: int = 0) -> bool:
	"""The properties `test_ussd_never_truncates` asserts about a message.

	Extracted so the canary can drive the gate's own predicate against a
	truncated message. A gate whose logic exists only inline, over a live client,
	is a gate that cannot be shown failing -- and a gate nobody has watched fail
	is not evidence (AD-10).

	``omitted`` is the number of zones the renderer dropped, which the message
	alone cannot tell us: a forecast that fits every zone legitimately carries no
	omission marker, so requiring one unconditionally would fail on a short feed
	and the gate would be switched off. When zones *were* dropped the marker is
	mandatory -- an unmarked omission reads as though nothing else was at risk,
	which is the failure §5.1 names.
	"""
	if len(message) > USSD_MAX_CHARS:
		return False
	if omitted and not ("+" in message and "more" in message):
		return False
	# Every named zone must be a complete name, never a cut one.
	for token in message.split(": ", 1)[-1].split(", "):
		name = token.rsplit(" ", 1)[0].rstrip("+0123456789 ")
		if name and name != "+" and name.endswith("-"):
			return False
	return True


def test_ussd_never_truncates(client: TestClient, keys: dict) -> None:
	"""USSD output is at most 182 characters and never cuts a zone name.

	A truncated forecast is a wrong one: it drops the zones that did not fit and
	reads as though they were not at risk (11-layer8 §5.1). The adapter selects
	a prefix and states how many it omitted, so the message is complete at its
	own resolution.
	"""
	from alea.api.adapters.ussd import format_ussd_forecast
	from alea.api.views import OutageForecastRowOut, ValueOut

	rows = [
		OutageForecastRowOut(
			country_iso="KE",
			grid_zone=f"Zone-{index:02d}-long-name",
			probability=ValueOut.measured(0.9 - index * 0.01, "probability"),
			horizon_hours=24,
			issued_at=datetime(2026, 1, 1, tzinfo=UTC),
		)
		for index in range(30)
	]
	message = format_ussd_forecast(rows, country="KE")
	# 30 rows are more than any screen holds, so zones were dropped and the
	# marker is required.
	assert ussd_gate_holds(message, omitted=len(rows)), (
		f"the rendered message is not a complete one: {message!r}"
	)

	# And through the route, against the scratch forecast.
	response = client.post(
		"/api/v1/adapters/ussd",
		headers=keys["public"],
		json={"session_id": "s1", "phone_number": "+254700000000", "text": "1"},
	)
	assert response.status_code == 200, response.text
	assert ussd_gate_holds(response.json()["text"]), response.text


def test_sms_is_bounded_and_reserves_its_link(client: TestClient, keys: dict) -> None:
	"""SMS output fits 160 characters with the link reserved first."""
	response = client.post(
		"/api/v1/adapters/sms",
		headers=keys["public"],
		json={"session_id": "s1", "phone_number": "+254700000000"},
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert len(body["text"]) <= SMS_MAX_CHARS
	if body["link"]:
		assert len(body["text"]) + 1 + len(body["link"]) <= SMS_MAX_CHARS


# --------------------------------------------------------------------------
# Criterion 8 -- OpenAPI generated and valid
# --------------------------------------------------------------------------


def _refs(node: object) -> list[str]:
	"""Every ``$ref`` string anywhere in a document node."""
	found: list[str] = []
	if isinstance(node, dict):
		for key, value in node.items():
			if key == "$ref":
				found.append(value)
			else:
				found.extend(_refs(value))
	elif isinstance(node, list):
		for value in node:
			found.extend(_refs(value))
	return found


def openapi_gate_holds(spec: dict) -> bool:
	"""The document properties `test_openapi_valid` asserts, as a predicate.

	Extracted for the same reason as `ussd_gate_holds`: a gate that can only run
	against the live app cannot be handed a broken document, so it can never be
	watched failing. Every branch here is one the canary plants a defect for.

	The route-inventory half stays in the test: it needs the app, not the
	document, and a served route missing from the document is a different defect
	from a malformed one.
	"""
	if not str(spec.get("openapi", "")).startswith("3."):
		return False
	if not spec.get("info", {}).get("title"):
		return False
	components = spec.get("components", {}).get("schemas", {})
	for ref in _refs(spec):
		if ref.startswith("#/") and ref.split("/")[-1] not in components:
			return False
	operation_ids: list[str] = []
	for operations in spec.get("paths", {}).values():
		for method, operation in operations.items():
			if method not in ("get", "post", "put", "patch", "delete"):
				continue
			if not operation.get("responses"):
				return False
			if "operationId" not in operation:
				return False
			operation_ids.append(operation["operationId"])
	return len(operation_ids) == len(set(operation_ids))


def test_openapi_valid(config: Config) -> None:
	"""The generated document is structurally sound and self-consistent.

	``jsonschema``/``openapi_spec_validator`` are not installed, so the checks
	are hand-rolled and cover the properties that matter: every ``$ref``
	resolves, every operation has a response, every operation names a unique
	``operationId``, and the served document matches the route inventory.
	"""
	from alea.api.inventory import route_inventory

	app = create_app(config)
	spec = app.openapi()
	assert openapi_gate_holds(spec), "the generated document is not self-consistent"

	# The document covers exactly the served routes (modulo path params).
	documented = set(spec["paths"])
	served = {route.path for route in route_inventory(app) if route.path.startswith("/api/v1")}
	undocumented = {
		path for path in served if not any(_same_shape(path, doc) for doc in documented)
	}
	assert not undocumented, f"served routes missing from the document: {sorted(undocumented)}"


def _same_shape(served: str, documented: str) -> bool:
	"""Whether a served path matches a documented template's shape."""
	pattern = re.sub(r"\{[^}]+\}", r"[^/]+", documented)
	return re.fullmatch(pattern, served) is not None


# --------------------------------------------------------------------------
# Criterion 9 -- the route inventory matches the spec endpoint table
# --------------------------------------------------------------------------


def test_the_configured_cache_ttl_reaches_the_response_store(
	config: Config, scratch: Path
) -> None:
	"""§6's lifetimes come from the config, so a config change must move them.

	``ApiConfig.cache_ttl_seconds`` was declared, documented, present in
	``config.default.yaml``, validated by Pydantic -- and read by nothing. The
	routes carried their own ``3600.0`` constants, so an operator editing the
	config changed nothing, and §6's four lifetimes were two hard-coded numbers
	and two absent ones.

	Asserted against the row the store actually wrote, not against the argument
	the route passed: a route that reads the config and then ignores it would
	pass any check made at the call site.
	"""
	# A lifetime nothing else in the suite uses, so the value read back can only
	# have come from this config.
	api = config.api.model_copy(update={"cache_ttl_seconds": 7, "cache_ttl_history_seconds": 11})
	patched = config.model_copy(update={"api": api})

	app = create_app(patched)
	with TestClient(app) as test_client:
		minted = _key(test_client, "public")
		for path in ("/api/v1/prices", "/api/v1/outages/history"):
			response = test_client.get(path, headers=minted)
			assert response.status_code == 200, f"{path}: {response.text}"

		database = app.state.api.job_store.database
		rows = asyncio.run(
			database.fetchall("SELECT namespace, stored_at, expires_at FROM response_cache")
		)

	assert rows, "the routes wrote no cache row, so there is no lifetime to check"
	observed = {
		row["namespace"]: float(row["expires_at"]) - float(row["stored_at"]) for row in rows
	}

	# The market route takes the default, the history route its own declared
	# lifetime. Checking both is what distinguishes "reads the config" from
	# "reads one field of it".
	assert observed.get("market.prices") == pytest.approx(7.0, abs=0.5), (
		f"the store recorded {observed.get('market.prices')}s for a config "
		f"declaring 7s; the route is not reading cache_ttl_seconds"
	)
	assert observed.get("outages.history") == pytest.approx(11.0, abs=0.5), (
		f"the store recorded {observed.get('outages.history')}s for a config "
		f"declaring 11s; the history route is not reading "
		f"cache_ttl_history_seconds"
	)


def test_the_inventory_canaries_against_a_known_route(config: Config) -> None:
	"""The inventory walk is canaried before its total is trusted.

	An inventory never pointed at a route known to exist has nothing behind its
	count. ``assert_inventory`` raises if it cannot see ``GET /api/v1/health``,
	which is the route that must always exist.
	"""
	from alea.api.inventory import KNOWN_ROUTE, assert_inventory, route_inventory

	app = create_app(config)
	# A broken walk must fail, not report a plausible total: removing the
	# unwrap would hide every route the routers carry.
	inventory = assert_inventory(app)
	assert KNOWN_ROUTE in {(method, route.path) for route in inventory for method in route.methods}
	assert len(inventory) >= 30, f"the inventory reports only {len(inventory)} routes"
	# The count is not zero-shaped: it sees the routes the spec table names.
	served = {route.path for route in route_inventory(app)}
	assert "/api/v1/health" in served
