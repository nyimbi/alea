"""The PRG explorer serves the real graph and runs the real propagation."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from alea.prg import load_graph
from alea.prg.service import propagate_change
from alea.prg.ui.server import make_server


def _call(base: str, path: str, body: dict | None = None, method: str | None = None):
	data = None if body is None else json.dumps(body).encode()
	try:
		with urllib.request.urlopen(urllib.request.Request(base + path, data, method=method)) as r:
			return r.status, json.loads(r.read()) if path.startswith("/api") else r.read()
	except urllib.error.HTTPError as exc:
		return exc.code, json.loads(exc.read())


def test_explorer_serves_every_node_and_equation_and_propagates_like_the_service(tmp_path):
	graph = load_graph()
	server = make_server(0, tmp_path / 'sets.json')
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


def test_saved_sets_round_trip_persist_and_refuse_what_propagate_refuses(tmp_path):
	store = tmp_path / "sets.json"
	server = make_server(0, store)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	base = f"http://127.0.0.1:{server.server_address[1]}"
	try:
		assert _call(base, "/api/sets") == (200, {})
		status, sets = _call(base, "/api/sets", {"name": "bigger", "changes": {"total_capacity_mw": 11000.0}})
		assert status == 200 and sets == {"bigger": {"total_capacity_mw": 11000.0}}
		# Persisted on disk, not held in the handler: a second server reads it.
		assert json.loads(store.read_text()) == sets
		# One dimension per refusal: a computed node, an unknown node, an empty set, a bad name.
		for body in (
			{"name": "x", "changes": {"discount_rate": 0.1}},
			{"name": "x", "changes": {"no_such_node": 1.0}},
			{"name": "x", "changes": {}},
			{"name": "../x", "changes": {"total_capacity_mw": 1.0}},
		):
			assert _call(base, "/api/sets", body)[0] == 400, body
		assert json.loads(store.read_text()) == sets
		assert _call(base, "/api/sets/bigger", method="DELETE")[0] == 200
		assert _call(base, "/api/sets/bigger", method="DELETE")[0] == 404
		assert _call(base, "/api/sets") == (200, {})
	finally:
		server.shutdown()
		server.server_close()
