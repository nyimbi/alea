"""The PRG explorer serves the real graph and runs the real propagation."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from alea.prg import load_graph
from alea.prg.service import propagate_change
from alea.prg.ui.server import make_server


def _call(base: str, path: str, body: dict | None = None):
	data = None if body is None else json.dumps(body).encode()
	try:
		with urllib.request.urlopen(urllib.request.Request(base + path, data)) as r:
			return r.status, json.loads(r.read()) if path.startswith("/api") else r.read()
	except urllib.error.HTTPError as exc:
		return exc.code, json.loads(exc.read())


def test_explorer_serves_every_node_and_equation_and_propagates_like_the_service():
	graph = load_graph()
	server = make_server(0)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	base = f"http://127.0.0.1:{server.server_address[1]}"
	try:
		status, page = _call(base, "/")
		assert status == 200 and b"PRG explorer" in page
		status, payload = _call(base, "/api/graph")
		assert status == 200
		assert len(payload["nodes"]) == len(graph.nodes)
		assert len(payload["equations"]) == len(graph.equations)
		assert len(payload["edges"]) == len(graph.edges)

		values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
		expected = propagate_change(values, {"total_capacity_mw": 11000.0}, graph)
		status, got = _call(base, "/api/propagate", {"changes": {"total_capacity_mw": 11000.0}})
		assert status == 200
		assert got["changed"].keys() == expected["changed"].keys()
		assert len(got["changed"]) > 1

		status, err = _call(base, "/api/propagate", {"changes": {"discount_rate": 0.1}})
		assert status == 400 and "computed by the graph" in err["error"]
		status, _ = _call(base, "/api/propagate", {"changes": {"no_such_node": 1.0}})
		assert status == 400
	finally:
		server.shutdown()
		server.server_close()
