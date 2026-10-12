# SPDX-License-Identifier: MIT
"""Canary: watch each Layer 8 gate in `11-layer8-api.md` §8 fail on its defect.

Two gates are watched here -- `test_openapi_valid` and `test_ussd_never_truncates`.
The rest of §8's table already has canaries in ``test_api_gates.py`` (the GET-body
and bare-quantity gates, the inline-solve scan, the checksum key, the rate
limiter, the revoked-key codes, the durable job store).

WHY the OpenAPI defect is planted in a *copy of the document* rather than in
source. The gate reads the generated document, so the defect is a property of
that document -- a dangling ``$ref``, a duplicate ``operationId`` -- and building
it directly exercises the gate's own predicate against a document that genuinely
contains the defect. Mutating a route's source would prove a model was removed,
not that the check fires, and would need a file to restore.

WHY the USSD defect is a real file mutation. The gate asserts the *formatter*
never truncates a zone name, and the formatter is package code, so the only way
to plant "a message that cuts a zone name" is to change the formatter and reload
it. The module is reloaded rather than imported through the gate's binding: the
gate module is already in ``sys.modules`` with the original function bound, and a
canary that called that binding would test working code.
"""

from __future__ import annotations

import copy
import importlib
from pathlib import Path

import pytest

from alea.api.app import create_app
from alea.api.views import USSD_MAX_CHARS
from alea.config.loader import load_config
from alea.config.models import Config
from tests.ci.canaries import REPO, planted
from tests.ci.test_api_layer8 import ADMIN_KEY

USSD_PY = REPO / "src" / "alea" / "api" / "adapters" / "ussd.py"

ussd_module = importlib.import_module("alea.api.adapters.ussd")


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
	"""A loaded config whose relative paths resolve under ``tmp_path``.

	``create_app`` reads the route table and the OpenAPI document, neither of
	which touches the filesystem, so the scratch root is only there to keep the
	config's own path resolution off the real tree.
	"""
	loaded = load_config()
	monkeypatch.setenv("ALEA_API_ADMIN_KEY", ADMIN_KEY)
	import alea.config.paths as paths

	monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
	return loaded


# --------------------------------------------------------------------------
# test_openapi_valid -- a dangling $ref and a duplicate operationId
# --------------------------------------------------------------------------


def _refs(node: object) -> list[str]:
	"""Every ``$ref`` in a document, the walk the gate performs."""
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


def _dangling_refs(spec: dict) -> list[str]:
	"""Local ``$ref`` values that name a component the document does not define."""
	components = spec["components"]["schemas"]
	return [
		ref
		for ref in _refs(spec)
		if ref.startswith("#/") and ref.split("/")[-1] not in components
	]


def _duplicate_operation_ids(spec: dict) -> list[str]:
	"""Operation ids that appear on more than one operation."""
	seen: list[str] = []
	for operations in spec["paths"].values():
		for method, operation in operations.items():
			if method not in ("get", "post", "put", "patch", "delete"):
				continue
			seen.append(operation["operationId"])
	return sorted({name for name in seen if seen.count(name) > 1})


def test_the_openapi_gate_catches_a_dangling_ref(config: Config) -> None:
	"""``test_openapi_valid`` must fail when a ``$ref`` resolves to nothing.

	A dangling reference is the document claiming a schema it does not carry: a
	client generating from the spec produces a model for a type that is not
	there. The gate walks every ``$ref`` and asserts it names a defined
	component; planting one that does not must be reported.
	"""
	spec = create_app(config).openapi()
	assert not _dangling_refs(spec), "the OpenAPI gate already fails on a clean document"

	broken = copy.deepcopy(spec)
	path = next(p for p, ops in broken["paths"].items() if "get" in ops)
	broken["paths"][path]["get"]["responses"]["200"] = {
		"description": "planted",
		"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DoesNotExist"}}},
	}
	dangling = _dangling_refs(broken)
	assert "#/components/schemas/DoesNotExist" in dangling, (
		f"the OpenAPI gate is blind to a dangling $ref: {dangling}"
	)


def test_the_openapi_gate_catches_a_duplicate_operation_id(config: Config) -> None:
	"""``test_openapi_valid`` must fail when two operations share an operation id.

	A duplicate ``operationId`` is a generator emitting two methods with one name
	-- the second silently shadows the first in any client built from the spec.
	The gate asserts the ids are unique; planting a collision must be reported.
	"""
	spec = create_app(config).openapi()
	assert not _duplicate_operation_ids(spec), "the OpenAPI gate already fails on a clean document"

	broken = copy.deepcopy(spec)
	operations = [
		operation
		for ops in broken["paths"].values()
		for method, operation in ops.items()
		if method in ("get", "post", "put", "patch", "delete")
	]
	assert len(operations) >= 2, "the document has too few operations to collide"
	operations[0]["operationId"] = "canary_collision"
	operations[1]["operationId"] = "canary_collision"
	duplicates = _duplicate_operation_ids(broken)
	assert "canary_collision" in duplicates, (
		f"the OpenAPI gate is blind to a duplicate operationId: {duplicates}"
	)


# --------------------------------------------------------------------------
# test_ussd_never_truncates -- cut a zone name instead of selecting a prefix
# --------------------------------------------------------------------------

_USSD_PROBE = (
	"from datetime import UTC, datetime\n"
	"from alea.api.adapters.ussd import format_ussd_forecast\n"
	"from alea.api.views import OutageForecastRowOut, ValueOut\n"
	"rows = [OutageForecastRowOut(country_iso='KE', grid_zone=f'Zone-{i:02d}-long-name',\n"
	"    probability=ValueOut.measured(0.9 - i * 0.01, 'probability'), horizon_hours=24,\n"
	"    issued_at=datetime(2026, 1, 1, tzinfo=UTC)) for i in range(30)]\n"
	"message = format_ussd_forecast(rows, country='KE')\n"
	"print('MESSAGE', message)\n"
)


def _ussd_message() -> str:
	"""The USSD rendering, from a fresh interpreter so the file on disk is read."""
	import subprocess
	import sys

	completed = subprocess.run(
		[sys.executable, "-c", _USSD_PROBE],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	assert completed.returncode == 0, completed.stderr
	line = next(
		line for line in completed.stdout.splitlines() if line.startswith("MESSAGE ")
	)
	return line[len("MESSAGE ") :]


def _cuts_a_zone_name(message: str) -> bool:
	"""Whether any named zone is a fragment rather than a whole name.

	The gate's own test: a zone name ending in ``-`` was cut mid-name.
	"""
	for token in message.split(": ", 1)[-1].split(", "):
		name = token.rsplit(" ", 1)[0].rstrip("+0123456789 ")
		if name and name != "+" and name.endswith("-"):
			return True
	return False


def test_the_ussd_gate_catches_a_truncating_formatter():
	"""``test_ussd_never_truncates`` must fail when the formatter cuts a zone name.

	The gate asserts the message fits the screen *and* names no partial zone. A
	truncated forecast drops the zones that did not fit and reads as though they
	were not at risk, and a cut name is the visible edge of that. The formatter
	instead selects the largest whole prefix and states how many it omitted; the
	planted defect is the naive ``[:max_chars]`` cut.
	"""
	clean = _ussd_message()
	assert len(clean) <= USSD_MAX_CHARS, f"the clean message already overflows: {len(clean)}"
	assert not _cuts_a_zone_name(clean), f"the clean message already cuts a name: {clean!r}"

	target = '\t\tmessage = f"{header}{\', \'.join(parts)}{tail}"\n'
	assert target in USSD_PY.read_text(), "canary target not found: the message assembly moved"
	# The naive cut: build the full rendering and slice it to the screen. This is
	# the specification's shape -- a table rendered as a string and truncated.
	truncating = (
		'\t\tmessage = f"{header}{\', \'.join(parts)}{tail}"\n'
		"\t\treturn message[:max_chars]\n"
	)

	with planted(USSD_PY, target, truncating):
		broken = _ussd_message()
	assert _cuts_a_zone_name(broken) or len(broken) > USSD_MAX_CHARS, (
		f"the truncating formatter neither cut a name nor overflowed: {broken!r}"
	)

	restored = _ussd_message()
	assert restored == clean, "the restore was not proven"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
