# SPDX-License-Identifier: MIT
"""Canary: watch the cache-lifetime gate fail when a route stops reading the config.

``test_the_configured_cache_ttl_reaches_the_response_store`` exists because
``ApiConfig.cache_ttl_seconds`` was declared, documented, in the default config,
validated by Pydantic -- and read by nothing. The routes carried their own
constants, so §6's four lifetimes were numbers an operator could not move.

A gate over a config field is easy to write in a way that cannot fail: assert
the field exists, assert the route's call site names it, assert the config
parses. All three pass against a route that reads the field and then ignores it.
This canary is what proves the gate reads the *stored* lifetime instead: it
plants a route that passes a constant, and the gate must notice.

**A subprocess, not a reload.** ``middleware``, ``cache`` and the route module
are all in ``sys.modules`` with their bindings already made by the time this
test runs, and the app under test is built from them. A fresh interpreter is
also the honest shape: the defect is a file on disk, and a file patch is only
visible to an interpreter that reads the file.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.ci.canaries import REPO, planted

MARKET_PY = REPO / "src" / "alea" / "api" / "routes" / "market.py"

#: The route's read of the configured default, and the constant that replaces
#: it. The replacement is a *plausible* value -- one hour, §6's own number --
#: because a canary that planted something absurd would be caught by a much
#: weaker gate than the one under test.
TARGET = "\t\tttl_seconds=state.config.api.cache_ttl_seconds,\n"
CONSTANT = "\t\tttl_seconds=3600.0,\n"

_PROBE = """
import asyncio
from fastapi.testclient import TestClient
from alea.api.app import create_app
from alea.config.loader import load_config
from alea.config.paths import repo_root
import alea.config.paths as paths
from pathlib import Path
import os, tempfile
from tests.ci.test_api_layer8 import (
    ADMIN_KEY, _catalogue_artefacts, _population_artefacts, _run_log,
)

# The config is loaded *first*, from the real default file, and the root is
# patched after: `load_config` reads `config/config.default.yaml` through
# `repo_root`, so patching first makes the default file unfindable and the load
# fails on a missing `scenario`. Artefact reads happen after the patch, which is
# the order the layer-8 fixture documents.
os.environ["ALEA_API_ADMIN_KEY"] = ADMIN_KEY
config = load_config()

root = Path(tempfile.mkdtemp())
paths.repo_root = lambda: root
_population_artefacts(root)
_catalogue_artefacts(root)
_run_log(root)

api = config.api.model_copy(update={"cache_ttl_seconds": 7})
app = create_app(config.model_copy(update={"api": api}))
with TestClient(app) as client:
    key = client.post(
        "/api/v1/keys",
        json={"name": "canary", "tier": "public"},
        headers={"X-API-Key": ADMIN_KEY},
    ).json()["key"]
    response = client.get("/api/v1/prices", headers={"X-API-Key": key})
    assert response.status_code == 200, response.text
    database = app.state.api.job_store.database
    rows = asyncio.run(
        database.fetchall("SELECT namespace, stored_at, expires_at FROM response_cache")
    )
observed = {
    row["namespace"]: float(row["expires_at"]) - float(row["stored_at"]) for row in rows
}
print("TTL", observed.get("market.prices"))
"""


def _market_ttl() -> float | None:
	"""The lifetime the store recorded for ``market.prices``, from a fresh interpreter."""
	completed = subprocess.run(
		[sys.executable, "-c", _PROBE],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	assert completed.returncode == 0, completed.stderr
	line = next(
		(line for line in completed.stdout.splitlines() if line.startswith("TTL ")),
		None,
	)
	assert line is not None, f"the probe printed no lifetime:\n{completed.stdout}"
	text = line[len("TTL ") :].strip()
	return None if text == "None" else float(text)


def test_the_ttl_gate_catches_a_route_that_ignores_the_config() -> None:
	"""``test_the_configured_cache_ttl_reaches_the_response_store`` must fail on a constant.

	The defect is exactly the one that was live: the route resolves, the response
	validates, the cache is written -- and the lifetime is a number the operator
	cannot move. Nothing about the response changes, which is why the gate has to
	read the store rather than the response.
	"""
	clean = _market_ttl()
	assert clean is not None, "the clean run wrote no cache row, so there is nothing to canary"
	assert abs(clean - 7.0) < 0.5, (
		f"the clean run recorded {clean}s for a config declaring 7s; the canary "
		f"would be measuring a defect that is already present"
	)

	assert TARGET in MARKET_PY.read_text(), (
		"canary target not found: the route no longer reads cache_ttl_seconds, "
		"so this canary would be planting a defect that is already there"
	)

	with planted(MARKET_PY, TARGET, CONSTANT):
		broken = _market_ttl()

	assert broken is not None, "the planted run wrote no cache row"
	# The gate's own predicate: does the recorded lifetime equal the configured
	# one? A constant 3600 against a config declaring 7 is the gate failing.
	assert abs(broken - 7.0) >= 0.5, (
		f"the constant-ttl route still recorded {broken}s, so the gate cannot "
		f"distinguish a configured lifetime from a hard-coded one"
	)

	restored = _market_ttl()
	assert restored == clean, "the restore was not proven"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
