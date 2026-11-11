# SPDX-License-Identifier: MIT
"""A local, read-mostly explorer for the PRG: `alea prg ui`.

Stdlib only, bound to 127.0.0.1. It serves one page and two JSON routes. The
adjust panel calls `propagate_change`, the same function `alea prg propagate`
uses, so the page cannot disagree with the CLI about what a change moves: the
equations are evaluated by the DSL, not re-implemented in JavaScript.

The server never writes the graph. `config/prg.yaml` is a baked artefact and
hand-editing is forbidden, so "adjust" means *what-if on the values*, not a
change to the graph.
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from alea.prg import load_graph
from alea.prg.service import propagate_change

PAGE = Path(__file__).with_name("index.html")
MAX_BODY = 1_000_000
DEFAULT_STORE = Path("data/processed/prg_whatifs.json")
NAME = re.compile(r"^[\w .,+()-]{1,80}$")


def read_sets(store: Path) -> dict[str, dict[str, Any]]:
	if not store.exists():
		return {}
	data = json.loads(store.read_text())
	assert isinstance(data, dict), f"{store} is not a JSON object"
	return data


def save_set(store: Path, name: str, changes: dict[str, Any]) -> None:
	"""Validate against the graph, then write atomically. Refuses what propagate refuses."""
	if not NAME.match(name):
		raise ValueError("name must be 1-80 letters, digits, spaces or .,+()-_")
	graph = load_graph()
	unknown = sorted(set(changes) - set(graph.nodes))
	if unknown:
		raise ValueError(f"{unknown} are not parameters in the graph")
	computed = sorted(k for k in changes if not graph.is_settable(k))
	if computed:
		raise ValueError(f"{computed} are computed by the graph and cannot be saved as settings")
	if not changes:
		raise ValueError("a set with no changes is not worth saving")
	sets = read_sets(store)
	sets[name] = changes
	store.parent.mkdir(parents=True, exist_ok=True)
	tmp = store.with_suffix(".tmp")
	tmp.write_text(json.dumps(sets, indent=1, sort_keys=True))
	os.replace(tmp, store)


def delete_set(store: Path, name: str) -> bool:
	sets = read_sets(store)
	if name not in sets:
		return False
	del sets[name]
	tmp = store.with_suffix(".tmp")
	tmp.write_text(json.dumps(sets, indent=1, sort_keys=True))
	os.replace(tmp, store)
	return True


def _plain(value: Any) -> Any:
	"""Enums and tuples as JSON values."""
	if hasattr(value, "value"):
		return value.value
	if isinstance(value, tuple):
		return [_plain(v) for v in value]
	return value


def graph_payload() -> dict[str, Any]:
	"""Nodes, equations and edges, slimmed to what the page renders."""
	graph = load_graph()
	nodes = []
	for key, node in graph.nodes.items():
		nodes.append(
			{
				"id": key,
				"name": node.name,
				"description": node.description,
				"category": node.category,
				"subcategory": node.subcategory,
				"type": _plain(node.type),
				"unit": node.unit,
				"range": _plain(node.range),
				"default": node.default,
				"role": _plain(node.role),
				"determinism": _plain(node.determinism),
				"categories": list(node.categories),
				"source": node.source,
				"status": _plain(getattr(node, "status", None)),
				"settable": bool(graph.is_settable(key)),
			}
		)
	equations = []
	for eq in graph.equations.values():
		equations.append(
			{
				"id": eq.id,
				"name": eq.name,
				"description": eq.description,
				"system": eq.system,
				"lhs": eq.lhs,
				"rhs": eq.rhs,
				"relation": _plain(eq.relation),
				"parameters": list(eq.parameters),
				"determined": list(eq.determined_variables),
				"free": list(eq.free_variables),
				"reference": eq.reference,
				"unit_check": _plain(eq.unit_check),
			}
		)
	edges = [
		{
			"source": e.source,
			"target": e.target,
			"equation": e.equation_id,
			"strength": _plain(e.strength),
			"description": e.description,
		}
		for e in graph.edges
	]
	return {"nodes": nodes, "equations": equations, "edges": edges}


def run_propagate(changes: dict[str, Any]) -> dict[str, Any]:
	graph = load_graph()
	values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
	result = propagate_change(values, changes, graph)
	baseline = {k: values.get(k) for k in result["values"]}
	return {**result, "baseline": baseline}


class _Handler(BaseHTTPRequestHandler):
	server_version = "alea-prg-ui"

	def _send(self, status: int, body: bytes, kind: str) -> None:
		self.send_response(status)
		self.send_header("Content-Type", kind)
		self.send_header("Content-Length", str(len(body)))
		self.send_header("Cache-Control", "no-store")
		self.end_headers()
		self.wfile.write(body)

	def _json(self, status: int, payload: Any) -> None:
		self._send(status, json.dumps(payload, default=str).encode(), "application/json")

	def do_GET(self) -> None:  # noqa: N802
		if self.path in ("/", "/index.html"):
			self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
		elif self.path == "/api/sets":
			self._json(200, read_sets(self.server.store))  # type: ignore[attr-defined]
		elif self.path == "/api/graph":
			self._json(200, self.server.payload)  # type: ignore[attr-defined]
		else:
			self._json(404, {"error": "not found"})

	def do_DELETE(self) -> None:  # noqa: N802
		from urllib.parse import unquote

		if not self.path.startswith("/api/sets/"):
			self._json(404, {"error": "not found"})
			return
		found = delete_set(self.server.store, unquote(self.path[len("/api/sets/") :]))  # type: ignore[attr-defined]
		self._json(200 if found else 404, {"deleted": found})

	def do_POST(self) -> None:  # noqa: N802
		if self.path == "/api/sets":
			length = int(self.headers.get("Content-Length", "0"))
			if length <= 0 or length > MAX_BODY:
				self._json(400, {"error": "body missing or too large"})
				return
			try:
				body = json.loads(self.rfile.read(length))
				save_set(self.server.store, body["name"], body["changes"])  # type: ignore[attr-defined]
				self._json(200, read_sets(self.server.store))  # type: ignore[attr-defined]
			except Exception as exc:  # noqa: BLE001
				self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
			return
		if self.path != "/api/propagate":
			self._json(404, {"error": "not found"})
			return
		length = int(self.headers.get("Content-Length", "0"))
		if length <= 0 or length > MAX_BODY:
			self._json(400, {"error": "body missing or too large"})
			return
		try:
			body = json.loads(self.rfile.read(length))
			changes = body["changes"]
			if not isinstance(changes, dict):
				raise TypeError("changes must be an object")
			self._json(200, run_propagate(changes))
		except Exception as exc:  # noqa: BLE001 - the page shows the graph's own refusal text
			self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

	def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
		return


def make_server(port: int = 8765, store: Path = DEFAULT_STORE) -> ThreadingHTTPServer:
	server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
	server.store = store  # type: ignore[attr-defined]
	server.payload = graph_payload()  # type: ignore[attr-defined]
	return server


def serve(port: int = 8765) -> None:
	server = make_server(port)
	print(f"PRG explorer on http://127.0.0.1:{server.server_address[1]}/  (Ctrl-C to stop)")
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.server_close()
