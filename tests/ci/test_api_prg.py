# SPDX-License-Identifier: MIT
"""The PRG routes, driven through the application.

These are read-only computations over a graph that loads from a file, so the
tests go through ``TestClient`` rather than calling the route functions: a
route that is registered but never reached is a capability nobody can use, and
the only evidence it is reachable is a request through the front door.

The graph is copied into the scratch root the ``config`` fixture redirects
``repo_root`` to, so ``load_graph`` resolves the real file through the same
path resolution production uses.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alea.api.app import create_app
from alea.config.loader import load_config
from alea.config.models import Config
from alea.config.paths import repo_root

ADMIN_KEY = "alea_admin_" + "0" * 40


@pytest.fixture
def prg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
	"""A config whose repo root carries the real PRG file."""
	loaded = load_config()
	monkeypatch.setenv("ALEA_API_ADMIN_KEY", ADMIN_KEY)
	# The graph is copied in, not patched around: load_graph resolves through
	# repo_root, and a test that bypassed that would not exercise the path
	# production uses.
	source = repo_root() / "config" / "prg.yaml"
	(tmp_path / "config").mkdir(parents=True, exist_ok=True)
	shutil.copy(source, tmp_path / "config" / "prg.yaml")
	import alea.config.paths as paths

	monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
	return loaded


@pytest.fixture
def prg_client(prg_config: Config) -> Iterator[TestClient]:
	app = create_app(prg_config)
	with TestClient(app) as client:
		yield client


@pytest.fixture
def public_key(prg_client: TestClient) -> dict[str, str]:
	response = prg_client.post(
		"/api/v1/keys",
		json={"name": "prg-public", "tier": "public"},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert response.status_code == 201, response.text
	return {"X-API-Key": response.json()["key"]}


@pytest.fixture
def analyst_key(prg_client: TestClient) -> dict[str, str]:
	response = prg_client.post(
		"/api/v1/keys",
		json={"name": "prg-analyst", "tier": "analyst"},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert response.status_code == 201, response.text
	return {"X-API-Key": response.json()["key"]}


def test_the_summary_route_serves_the_registers(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""The summary carries the three registers, not just the counts."""
	response = prg_client.get("/api/v1/prg/summary", headers=public_key)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["parameters"] > 0
	assert body["equations"] > 0
	# The registers are the finding: a client that reads only the counts will
	# assume the engine is driven by all of them.
	assert 0.0 <= body["engine_translation"]["fraction"] <= 1.0
	# Both directions of the engine register, because they are different
	# findings: PRG parameters the engine cannot carry, and engine knobs no PRG
	# parameter names. A payload carrying only the first lets a client read the
	# coverage as one number and miss that a scenario can pull a lever the
	# graph never sees.
	assert body["engine_translation"]["untranslated"]
	assert body["engine_translation"]["engine_unreached"]
	assert body["units"]["summary"]
	assert body["uncertainty"]["summary"]
	assert len(body["units"]["consistent"]) + len(body["units"]["inconsistent"]) + len(
		body["units"]["undecidable"]
	) == body["equations"]


def test_the_equations_route_renders_them(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	response = prg_client.get("/api/v1/prg/equations", headers=public_key)
	assert response.status_code == 200, response.text
	rows = response.json()
	assert rows, "the equation library is empty"
	assert all(row["rendered"] for row in rows)


def test_the_equations_route_honours_the_notation(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	latex = prg_client.get(
		"/api/v1/prg/equations", params={"as": "latex"}, headers=public_key
	)
	assert latex.status_code == 200, latex.text
	assert any("\\" in row["rendered"] for row in latex.json())


def test_the_equations_route_rejects_an_unknown_notation(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	response = prg_client.get(
		"/api/v1/prg/equations", params={"as": "klingon"}, headers=public_key
	)
	assert response.status_code == 422


def test_the_sensitivity_route_differentiates(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A derived parameter's derivatives, at the defaults."""
	response = prg_client.post(
		"/api/v1/prg/sensitivity",
		json={"parameter": "lcoe_usd_per_mwh", "top": 5},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["parameter"] == "lcoe_usd_per_mwh"
	assert body["method"] in {"input", "symbolic", "implicit"}
	assert body["derivatives"], "no derivatives were returned"


def test_the_sensitivity_route_404s_an_unknown_parameter(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	response = prg_client.post(
		"/api/v1/prg/sensitivity",
		json={"parameter": "not_a_parameter"},
		headers=analyst_key,
	)
	assert response.status_code == 404


def test_the_sensitivity_route_422s_an_unknown_override(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	response = prg_client.post(
		"/api/v1/prg/sensitivity",
		json={"parameter": "lcoe_usd_per_mwh", "set": {"nope": 1.0}},
		headers=analyst_key,
	)
	assert response.status_code == 422


def test_the_conflicts_route_reports_and_ranks(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A consistent default set reports no conflicts, and says what it checked."""
	response = prg_client.post(
		"/api/v1/prg/conflicts", json={}, headers=analyst_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["consistent"] is True
	assert body["conflicts"] == []
	assert body["checked"], "the report does not say what it examined"


def test_the_conflicts_route_finds_an_over_determination(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""Setting a derived parameter is the conflict this endpoint exists for."""
	response = prg_client.post(
		"/api/v1/prg/conflicts",
		json={"set": {"demand_twh": 1.0}},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["consistent"] is False
	assert body["conflicts"]
	assert any(c["corrections"] for c in body["conflicts"])


def test_the_conflicts_route_422s_an_unknown_parameter(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	response = prg_client.post(
		"/api/v1/prg/conflicts",
		json={"set": {"nope": 1.0}},
		headers=analyst_key,
	)
	assert response.status_code == 422


def test_the_read_routes_are_public_and_the_compute_routes_are_not(
	prg_client: TestClient,
) -> None:
	"""The graph's own description is public; a differentiation is not.

	``PublicDep`` is unauthenticated-allowed on purpose -- the same policy that
	lets ``/health`` be probed -- so the read routes answer without a key. The
	two POSTs take a parameter set and run the graph, so they require the
	analyst tier, and an anonymous caller is refused.
	"""
	assert prg_client.get("/api/v1/prg/summary").status_code == 200
	assert prg_client.get("/api/v1/prg/equations").status_code == 200
	assert prg_client.post("/api/v1/prg/sensitivity", json={"parameter": "lcoe_usd_per_mwh"}).status_code == 401
	assert prg_client.post("/api/v1/prg/conflicts", json={}).status_code == 401
