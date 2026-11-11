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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from alea.prg import load_graph
from alea.prg.service import propagate_change

PAGE = Path(__file__).with_name("index.html")
MAX_BODY = 1_000_000


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
		elif self.path == "/api/graph":
			self._json(200, self.server.payload)  # type: ignore[attr-defined]
		else:
			self._json(404, {"error": "not found"})

	def do_POST(self) -> None:  # noqa: N802
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


def make_server(port: int = 8765) -> ThreadingHTTPServer:
	server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
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
