# SPDX-License-Identifier: MIT
"""Canaries for the Layer 8 API gates (11-layer8 §8, criterion 10).

Each test plants the exact defect its gate exists to catch, asserts the gate
notices, restores the file from a backup, and asserts the gate passes again.
``planted`` enforces the first half: it refuses to write anything unless the
target text is present, because a patch that does not apply leaves the gate
passing against working code -- a false alarm about a gate that was never
pointed anywhere.

The gates are split in two by where the defect lives:

* **Spec-shaped gates** (no GET body, no bare quantity) read the generated
  OpenAPI document, so the defect can be planted in a *copy* of that document
  rather than in source. That is strictly better than editing a route: it
  exercises the gate's own predicate (``_get_with_body_offenders``,
  ``_bare_quantity_offenders``) against a document that genuinely contains the
  defect, with no file mutation to restore.
* **Behavioural gates** (rate limit, revoked key, plaintext key, durable jobs)
  assert what the running application does, and are canaried by inverting the
  dependency that makes them true -- an in-memory job store, a limiter that
  never refuses -- and showing the assertion fails.

``test_the_source_scan_catches_a_planted_solve`` and
``test_the_cache_key_gate_catches_a_dropped_checksum`` are the source canaries:
the inline-solve gate reads files and the cache key is computed in the package,
so each needs a real file to read or reload.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alea.api.app import create_app
from alea.api.middleware import RateLimiter
from alea.config.loader import load_config
from alea.config.models import Config
from tests.ci.canaries import REPO, planted
from tests.ci.test_api_layer8 import (
	ADMIN_KEY,
	_bare_quantity_offenders,
	_catalogue_artefacts,
	_get_with_body_offenders,
	_inline_solver_offenders,
	_population_artefacts,
	_run_log,
)

MIDDLEWARE_PY = REPO / "src" / "alea" / "api" / "middleware.py"

# --------------------------------------------------------------------------
# A scratch application, matching the layer-8 test fixtures.
# --------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
	"""A loaded config whose relative paths resolve under ``tmp_path``."""
	loaded = load_config()
	monkeypatch.setenv("ALEA_API_ADMIN_KEY", ADMIN_KEY)
	import alea.config.paths as paths

	monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
	return loaded


@pytest.fixture
def scratch(config: Config, tmp_path: Path) -> Path:
	_population_artefacts(tmp_path)
	_catalogue_artefacts(tmp_path)
	_run_log(tmp_path)
	return tmp_path


def _key(client: TestClient, tier: str = "public") -> dict[str, str]:
	response = client.post(
		"/api/v1/keys",
		json={"name": f"canary-{tier}", "tier": tier},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert response.status_code == 201, response.text
	return {"X-API-Key": response.json()["key"]}


# --------------------------------------------------------------------------
# Spec-shaped gates: plant the defect in the document, not the source.
# --------------------------------------------------------------------------


def test_the_get_body_gate_catches_a_planted_body(config: Config) -> None:
	"""``test_no_get_with_body`` must fail when a GET declares a request body.

	The defect is a GET handler with a plain Pydantic parameter, which is exactly
	the specification's §22 sketch. Planting a ``requestBody`` on a real GET
	operation reproduces the document that defect produces.
	"""
	spec = create_app(config).openapi()
	assert not _get_with_body_offenders(spec), "the gate already fails on a clean document"

	broken = copy.deepcopy(spec)
	path = next(p for p, ops in broken["paths"].items() if "get" in ops)
	broken["paths"][path]["get"]["requestBody"] = {
		"content": {"application/json": {"schema": {"type": "object"}}},
		"required": True,
	}
	offenders = _get_with_body_offenders(broken)
	assert offenders, "the GET-body gate is blind to a planted requestBody"


def test_the_bare_quantity_gate_catches_a_planted_float(config: Config) -> None:
	"""``test_values_carry_basis`` must fail when a response serves a float.

	The defect is a quantity served as a bare number instead of a ``ValueOut`` --
	``{"capacity_mw": 2100}``. It is planted on a response-reachable model, which
	is the set the gate owns: a request knob is a caller's input, not a claim the
	API makes.
	"""
	spec = create_app(config).openapi()
	assert not _bare_quantity_offenders(spec), "the gate already fails on a clean document"

	broken = copy.deepcopy(spec)
	# ``PriceRowOut`` is response-reachable and carries a real quantity.
	broken["components"]["schemas"]["PriceRowOut"]["properties"]["capacity_mw"] = {"type": "number"}
	offenders = _bare_quantity_offenders(broken)
	assert "PriceRowOut" in offenders, (
		f"the value-contract gate is blind to a bare float: {offenders}"
	)
	assert "capacity_mw" in offenders["PriceRowOut"], offenders


def test_the_source_scan_catches_a_planted_solve() -> None:
	"""``test_no_blocking_solve_in_route`` must fail on an inline solver call.

	The gate reads route source, so this canary mutates a real file: it plants
	``solve_what_if(...)`` in a route module and asserts the scan reports it.
	"""
	import alea.api

	package = Path(alea.api.__file__).parent
	target = package / "routes" / "planning.py"
	source = target.read_text()
	# The anchor is a real line in the file, so the canary cannot be a no-op.
	assert "\tassert state is not None, \"get_scenario_results needs application state\"" in source, (
		"canary target not found in planning.py; the anchor line moved"
	)
	planted_line = "\tresult = solve_what_if(scenario_id)  # canary\n"
	anchor = "\tassert state is not None, \"get_scenario_results needs application state\"\n"
	assert not _inline_solver_offenders(package), "the gate already fails on clean source"

	with planted(target, anchor, anchor + planted_line):
		offenders = _inline_solver_offenders(package)
		assert any("planning.py" in offender for offender in offenders), (
			f"the inline-solve gate is blind to a planted call: {offenders}"
		)


def test_the_cache_key_gate_catches_a_dropped_checksum() -> None:
	"""``test_cache_key_includes_checksum`` must fail when the checksum is dropped.

	The defect is the specification's key: the endpoint and parameters, without
	the artefact checksum. Dropping ``checksum`` from the canonical payload is
	exactly that key -- two requests against different networks then collide --
	and the gate's assertion that a different checksum gives a different key
	fails. A real file is mutated because the key is computed in the package, not
	handed to it.
	"""
	import importlib

	import alea.api.middleware as middleware_module

	source = MIDDLEWARE_PY.read_text()
	target = '\t\t{"namespace": namespace, "checksum": checksum, "params": params},'
	assert target in source, "canary target not found: the canonical payload line moved"

	with planted(
		MIDDLEWARE_PY,
		target,
		'\t\t{"namespace": namespace, "params": params},',
	):
		importlib.reload(middleware_module)
		one = middleware_module.cache_key("outages.forecast", checksum="sha256:" + "ab" * 32, params={})
		two = middleware_module.cache_key("outages.forecast", checksum="sha256:" + "cd" * 32, params={})
		assert one == two, (
			"the checksum-dropped key still distinguished two artefacts; the canary "
			"did not reproduce the defect"
		)

	importlib.reload(middleware_module)
	restored = middleware_module.cache_key
	assert restored("outages.forecast", checksum="sha256:" + "ab" * 32, params={}) != restored(
		"outages.forecast", checksum="sha256:" + "cd" * 32, params={}
	)


# --------------------------------------------------------------------------
# Behavioural gates: invert the dependency and show the assertion fails.
# --------------------------------------------------------------------------


def test_the_rate_limit_gate_catches_a_disabled_limiter(
	config: Config, scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""``test_rate_limit_enforced`` must fail when the limiter never refuses.

	A limiter that always allows is the defect the gate exists for. Patching
	``RateLimiter.check`` to allow everything reproduces it, and the gate's
	central assertion -- the fourth request is a 429 -- then fails.
	"""
	monkeypatch.setattr(RateLimiter, "check", lambda self, subject, limit: (True, limit, 60))
	app = create_app(config.model_copy(update={"api": config.api.model_copy(update={"rate_limit_per_minute": 3})}))
	with TestClient(app) as client:
		headers = _key(client)
		for _ in range(3):
			assert client.get("/api/v1/health", headers=headers).status_code == 200
		# With the limiter disabled the fourth request is served, not refused:
		# the gate's assertion would fail here, which is the canary.
		assert client.get("/api/v1/health", headers=headers).status_code == 200, (
			"the limiter refused despite being patched to allow everything"
		)


def test_the_revoked_key_gate_catches_collapsed_codes(
	config: Config, scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""``test_revoked_key_distinguishable`` must fail if revoked and unknown collapse.

	The plan requires a revoked key (403) to be distinguishable from one that
	never existed (401) -- §8 ``test_revoked_key_distinguishable``, asserted by
	``test_keys_stored_hashed`` in the suite. Collapsing them -- here by making
	the store report every missing or revoked key as ``unknown_key`` with a 401 --
	must break the gate.
	"""
	from alea.api import auth

	original = auth.ApiKeyStore.authenticate

	async def _collapsed(self: object, presented: str) -> object:
		# Preserve success (the admin key must still work) and preserve the
		# status, but collapse every failure code onto ``unknown_key``. That is
		# the defect: a revoked credential reads as one that never existed.
		try:
			return await original(self, presented)  # type: ignore[arg-type]
		except auth.AuthenticationError as exc:
			raise auth.AuthenticationError("unknown_key", exc.detail, status=exc.status) from exc

	monkeypatch.setattr(auth.ApiKeyStore, "authenticate", _collapsed)
	app = create_app(config)
	with TestClient(app) as client:
		minted = client.post(
			"/api/v1/keys",
			json={"name": "collapse", "tier": "analyst"},
			headers={"X-API-Key": ADMIN_KEY},
		)
		plaintext = minted.json()["key"]
		key_id = minted.json()["key_id"]
		client.delete(f"/api/v1/keys/{key_id}", headers={"X-API-Key": ADMIN_KEY})

		# Under the collapse both a revoked and an unknown key carry the same
		# code, which is precisely what the gate asserts is not the case.
		revoked = client.get("/api/v1/health", headers={"X-API-Key": plaintext})
		unknown = client.get("/api/v1/health", headers={"X-API-Key": f"alea_{'9' * 36}_{'z' * 8}"})
		assert revoked.json()["code"] == unknown.json()["code"] == "unknown_key", (
			"the collapse did not take; the canary did not reproduce the defect"
		)


def test_the_durable_job_gate_catches_an_in_memory_store(
	config: Config, scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""``test_job_survives_restart`` must fail on a store that forgets.

	A job whose result lives in a dict dies with the process. Pointing the store
	at a fresh in-memory database on every ``connect`` reproduces it: the job
	submitted by one application is gone in the next, and the gate's read of
	``GET /jobs/{id}`` is a 404.
	"""
	import alea.api.jobs as jobs_module

	original_connect = jobs_module.JobStore.connect

	async def _forgetful(self: jobs_module.JobStore) -> None:
		# A store that does not survive a restart. SQLite's ``:memory:`` cannot
		# reproduce it here -- the database is opened per operation, so every
		# statement would land on a fresh empty database and even the first
		# submission would fail. Emptying the durable table on connect is the
		# same defect at the level the gate observes: a second process sees no
		# row for a job the first one accepted.
		await original_connect(self)
		await self._database.execute("DELETE FROM jobs")

	monkeypatch.setattr(jobs_module.JobStore, "connect", _forgetful)
	body = {"base_scenario_id": "base", "parameters": {"demand_growth": 0.05}}

	first = create_app(config)
	with TestClient(first) as client:
		submitted = client.post("/api/v1/whatif/solve", headers=_key(client, "analyst"), json=body)
		assert submitted.status_code == 202, submitted.text
		job_id = submitted.json()["job_id"]

	second = create_app(config)
	with TestClient(second) as client:
		status = client.get(f"/api/v1/jobs/{job_id}", headers=_key(client))
		assert status.status_code == 404, (
			f"the forgetful store remembered the job ({status.status_code}); the "
			f"canary did not reproduce the defect"
		)


# --------------------------------------------------------------------------
# The two Layer 8 gates the register found uncanaried.
#
# Both are canaried against the gate's own predicate rather than the live app:
# a gate that can only run against the running service cannot be handed the
# broken artefact it exists to reject, so it can never be watched failing. The
# predicates are `ussd_gate_holds` and `openapi_gate_holds`, and each branch of
# them is one of these canaries.
# --------------------------------------------------------------------------


def _long_forecast_rows(count: int) -> list:
	from datetime import UTC, datetime

	from alea.api.views import OutageForecastRowOut, ValueOut

	return [
		OutageForecastRowOut(
			country_iso="KE",
			grid_zone=f"Zone-{index:02d}-long-name",
			probability=ValueOut.measured(0.9 - index * 0.01, "probability"),
			horizon_hours=24,
			issued_at=datetime(2026, 1, 1, tzinfo=UTC),
		)
		for index in range(count)
	]


def test_the_ussd_gate_catches_a_silent_omission() -> None:
	"""``test_ussd_never_truncates`` must fail when dropped zones go unmentioned.

	The defect is the naive renderer: take the prefix that fits the screen and
	say nothing about the rest. The message is then silent about the omission --
	it reads as though nothing else was at risk, which is the failure 11-layer8
	§5.1 names.
	"""
	from alea.api.adapters.ussd import format_ussd_forecast
	from tests.ci.test_api_layer8 import ussd_gate_holds

	rows = _long_forecast_rows(30)
	good = format_ussd_forecast(rows, country="KE")
	assert ussd_gate_holds(good, omitted=len(rows)), (
		"the gate rejects the shipped renderer; the canary is moot"
	)

	# The defect: the same prefix, with the omission marker stripped.
	assert "+" in good, "the shipped renderer dropped zones without a marker"
	silent = good.split(" +")[0]
	assert len(silent) <= len(good), "the planted message is not the defect"
	assert not ussd_gate_holds(silent, omitted=len(rows)), (
		"the USSD gate accepted a message that dropped zones without saying so"
	)
	# And it is only the marker the gate is reacting to: the same text is fine
	# when nothing was omitted, which is what keeps the gate from failing a
	# short feed and being switched off.
	assert ussd_gate_holds(silent, omitted=0)


def test_the_ussd_gate_catches_a_cut_zone_name() -> None:
	"""The other half: a message inside the width that ends a name mid-word.

	A cut name is a zone the operator cannot act on, and it is the failure a
	length check alone misses.
	"""
	from tests.ci.test_api_layer8 import ussd_gate_holds

	assert not ussd_gate_holds("KE risk 24h: Zone-01-long- 90%, Zone-02 89% +2 more"), (
		"the USSD gate accepted a message ending a zone name mid-word"
	)


def test_the_openapi_gate_catches_a_dangling_ref(config: Config) -> None:
	"""``test_openapi_valid`` must fail on a ``$ref`` that resolves to nothing.

	The defect is planted in a *copy* of the generated document: a dangling
	reference is the class the gate's first loop exists to catch, and it is the
	one a schema rename leaves behind. Editing the copy rather than the source
	exercises the gate's own predicate with no file to restore.
	"""
	from tests.ci.test_api_layer8 import openapi_gate_holds

	spec = create_app(config).openapi()
	assert openapi_gate_holds(spec), "the gate rejects the shipped document; the canary is moot"

	broken = copy.deepcopy(spec)
	first = next(iter(broken["components"]["schemas"]))
	# Rename a component and leave every reference to it in place.
	broken["components"]["schemas"][f"{first}_renamed"] = broken["components"]["schemas"].pop(first)
	assert not openapi_gate_holds(broken), (
		"the OpenAPI gate accepted a document with a dangling $ref; a renamed "
		"schema would ship undetected"
	)


def test_the_openapi_gate_catches_an_operation_without_responses(config: Config) -> None:
	"""The other half of the same gate: an operation with no ``responses``.

	A document that omits responses still parses, so nothing but the gate catches
	it -- and a client generated from it has no return type.
	"""
	from tests.ci.test_api_layer8 import openapi_gate_holds

	spec = create_app(config).openapi()
	assert openapi_gate_holds(spec), "the gate rejects the shipped document; the canary is moot"

	broken = copy.deepcopy(spec)
	path = next(iter(broken["paths"]))
	method = next(m for m in broken["paths"][path] if m in ("get", "post", "put", "patch", "delete"))
	del broken["paths"][path][method]["responses"]
	assert not openapi_gate_holds(broken), (
		"the OpenAPI gate accepted an operation with no responses"
	)
