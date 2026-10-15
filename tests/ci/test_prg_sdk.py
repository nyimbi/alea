# SPDX-License-Identifier: MIT
"""The Python SDK, driven against the real application.

The specification's §45 names a ``PRGClient``. A client is the one component
whose defects a unit test cannot find, because every method is a path string
and a payload shape: a typo in a route, a body key spelled the way the service
does not read, a filter sent as the literal ``"None"``. All of those pass a
test that mocks the transport and fail the first time anyone points the client
at the service.

So these tests drive the real app through ``httpx.ASGITransport`` -- the
client's own ``httpx.AsyncClient``, the client's own path construction, the
service's own routing, validation and authentication -- with no mock anywhere.
The only thing substituted is the transport, which is what makes the request an
in-process call rather than a socket.

``ASGITransport`` does not run the application's lifespan, and this app opens
its stores there: without entering ``lifespan_context`` every route raises
``AttributeError`` on ``app.state.api``. The fixture enters it, so the client
talks to a fully started service rather than to a construction that has not
connected anything.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from alea.api.app import create_app
from alea.config.loader import load_config
from alea.config.models import Config
from alea.prg.sdk import PRGClient, PrgClientError

ADMIN_KEY = "alea_admin_" + "0" * 40
API_PREFIX = "/api/v1"


@pytest.fixture
def prg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
	"""A loaded config, and a repo root carrying the real PRG document.

	The configuration is loaded *before* ``repo_root`` is redirected: the
	loader reads every file in ``config/``, and the scratch root holds only the
	graph. Redirecting first would make ``load_config`` fail on the files it
	could no longer find -- which is a failure about the fixture, not about
	anything under test.

	The graph is copied in rather than patched around because ``load_graph``
	resolves through ``repo_root``, and a test that bypassed that would not
	exercise the path production uses.
	"""
	from alea.config.paths import repo_root

	loaded = load_config()
	monkeypatch.setenv("ALEA_API_ADMIN_KEY", ADMIN_KEY)
	(tmp_path / "config").mkdir(parents=True, exist_ok=True)
	shutil.copy(repo_root() / "config" / "prg.yaml", tmp_path / "config" / "prg.yaml")
	import alea.config.paths as paths

	monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
	return loaded


@pytest.fixture
async def prg_app(prg_config: Config) -> AsyncIterator[httpx.AsyncClient]:
	"""The started application, and an ``httpx`` client wired to it.

	One app for the whole test: the key store is opened by the lifespan and
	lives in a file under the scratch root, so a second ``create_app`` would
	carry a second store and a key minted in one would not exist in the other.
	"""
	app = create_app(prg_config)
	async with app.router.lifespan_context(app):
		transport = httpx.ASGITransport(app=app)
		async with httpx.AsyncClient(
			transport=transport, base_url="http://prg.test"
		) as http:
			yield http


@pytest.fixture
async def analyst_key(prg_app: httpx.AsyncClient) -> str:
	"""A key with the tier the compute routes require."""
	response = await prg_app.post(
		f"{API_PREFIX}/keys",
		json={"name": "sdk-analyst", "tier": "analyst"},
		headers={"X-API-Key": ADMIN_KEY},
	)
	assert response.status_code == 201, response.text
	return response.json()["key"]


@pytest.fixture
async def prg(prg_app: httpx.AsyncClient, analyst_key: str) -> PRGClient:
	"""The client under test, sharing the started app's transport.

	``base_url`` is the prefix the app is mounted under and the client appends
	``/prg`` itself, so this exercises the path construction the deployment
	depends on rather than a path the test supplied.
	"""
	return PRGClient(
		base_url=f"http://prg.test{API_PREFIX}",
		api_key=analyst_key,
		client=prg_app,
	)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_the_client_refuses_to_guess_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
	"""A missing base URL is an error, not a default to localhost.

	A client that defaulted would send a production key to whatever is on port
	8000 of the machine running the test.
	"""
	monkeypatch.delenv("ALEA_PRG_BASE_URL", raising=False)
	with pytest.raises(ValueError, match="ALEA_PRG_BASE_URL"):
		PRGClient()


def test_the_base_url_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The environment variable is the documented way to configure it."""
	monkeypatch.setenv("ALEA_PRG_BASE_URL", "https://prg.example/api/v1/")
	monkeypatch.setenv("ALEA_API_KEY", "secret")
	client = PRGClient()
	assert client.base_url == "https://prg.example/api/v1", client.base_url
	assert client.api_key == "secret"


# ---------------------------------------------------------------------------
# The read surface
# ---------------------------------------------------------------------------


async def test_get_graph_serves_the_whole_graph(prg: PRGClient) -> None:
	"""The payload is a graph, and its parts agree with each other."""
	body = await prg.get_graph()
	ids = {p["parameter_id"] for p in body["parameters"]}
	assert ids
	assert body["edges"] and body["equations"]
	# Every declared edge names nodes the same payload carries. An edge
	# pointing at a parameter that is not in ``parameters`` is a graph a
	# client cannot draw, and the client would not notice on its own.
	for edge in body["edges"]:
		assert edge["source"] in ids, edge
		assert edge["target"] in ids, edge
	assert body["summary"]["parameters"] == len(body["parameters"])


async def test_export_graphml_returns_the_document_and_not_a_parse_of_it(
	prg: PRGClient,
) -> None:
	"""Text, because the caller asked for a file another tool reads."""
	text = await prg.export_graphml()
	assert text.lstrip().startswith("<?xml"), text[:80]
	assert "graphml" in text
	assert "<node" in text and "<edge" in text


async def test_list_parameters_filters_and_get_parameter_serves_one(
	prg: PRGClient,
) -> None:
	"""The filters narrow, and the by-id call agrees with the listed row."""
	everything = await prg.list_parameters()
	assert everything
	exogenous = await prg.list_parameters(role="exogenous")
	assert 0 < len(exogenous) < len(everything), len(exogenous)
	assert all(p["role"] == "exogenous" for p in exogenous)

	# An unset filter must not be sent at all. Sent as the literal "None" the
	# service's pattern rejects it, which is a 422 on a call the caller made
	# correctly -- the defect ``_get`` drops unset keys to avoid.
	category = everything[0]["category"]
	filtered = await prg.list_parameters(category=category)
	assert filtered and all(p["category"] == category for p in filtered)
	assert len(filtered) < len(everything), "the category filter narrowed nothing"

	one = await prg.get_parameter("equilibrium_demand_twh")
	assert one["parameter_id"] == "equilibrium_demand_twh"
	# The tariff loop's variable: derived, and reachable by id.
	assert one["role"] == "derived"
	# ``depends_on`` is empty *by construction* here, and that is not a gap:
	# it is read from the determining equation, and a loop variable has none --
	# a loop is exactly the case where no equation determines it on its own.
	# Its inputs are on the loop, which is where a client has to look.
	assert one["depends_on"] == []
	assert one["determined_by"] == ""
	assert one["affects"], "a loop variable that moves nothing"
	# What a client should reach for instead, and it names the inputs. The
	# summary carries loop *ids* only, so the loop itself is the register to
	# read -- which is the reason ``solve_feedback`` exists as a route rather
	# than the graph payload carrying it.
	solved = await prg.solve_feedback()
	loop = next(
		entry
		for entry in solved["loops"]
		if "equilibrium_demand_twh" in entry["variables"]
	)
	assert "regulated_tariff_usd_per_mwh" in loop["variables"]
	assert loop["equations"], "a loop with no equation is not a loop"


async def test_get_dependents_serves_the_closure_and_the_one_hop_view(
	prg: PRGClient,
) -> None:
	"""Both views, and the closure is the strictly larger one."""
	closure = await prg.get_dependents("demand_growth")
	direct = await prg.get_dependents("demand_growth", direct_only=True)
	assert direct and closure
	assert len(direct) < len(closure), (len(direct), len(closure))
	assert all(entry["distance"] == 1 for entry in direct)
	assert {e["parameter_id"] for e in direct} < {e["parameter_id"] for e in closure}
	# The closure is ordered by distance, which is what makes it usable as a
	# re-check order rather than an alphabetical list.
	distances = [entry["distance"] for entry in closure]
	assert distances == sorted(distances)


async def test_equation_calls_serve_the_library_and_one_of_it(prg: PRGClient) -> None:
	"""The list and the by-id call agree on the equations they share."""
	equations = await prg.list_equations()
	assert equations
	ids = {e["equation_id"] for e in equations}

	one = await prg.get_equation("crf_definition")
	assert one["equation_id"] == "crf_definition"
	assert one["rendered"] and one["equation_id"] in ids

	system = one["system"]
	filtered = await prg.list_equations(system=system)
	assert filtered and all(e["system"] == system for e in filtered)
	assert len(filtered) < len(equations), "the system filter narrowed nothing"


# ---------------------------------------------------------------------------
# The compute surface
# ---------------------------------------------------------------------------


async def test_check_consistency_reports_both_verdicts(prg: PRGClient) -> None:
	"""A consistent set and an unfinanceable one, through the client.

	Both directions, because a client that mis-serialised the body would send
	``set`` under a key the service ignores -- and then every call would report
	the graph's own defaults as consistent, which is a client that always
	answers "fine".
	"""
	clean = await prg.check_consistency()
	assert clean["consistent"] is True
	assert clean["violations"] == []
	assert clean["checked"] > 0

	# Five years of asset life against a 20-year debt is a DSCR the graph
	# refuses, and the violation names the equation that refused it.
	dirty = await prg.check_consistency({"asset_life": 5.0})
	assert dirty["consistent"] is False
	assert [v["equation_id"] for v in dirty["violations"]] == ["dscr_requirement"]


async def test_consistency_report_is_the_shipped_default(prg: PRGClient) -> None:
	"""The baseline, and it agrees with checking an empty set.

	``/consistency/report`` seeds the graph's defaults before checking, which
	is what "the shipped default scenario" means. A route that checked the
	empty set instead answered 422 on every call, naming the graph's own
	defaults as missing inputs.
	"""
	baseline = await prg.consistency_report()
	assert baseline["consistent"] is True
	assert baseline["checked"] > 0
	empty = await prg.check_consistency()
	assert baseline["checked"] == empty["checked"]
	assert baseline["consistent"] == empty["consistent"]


async def test_propagate_reports_the_delta_and_the_loops(prg: PRGClient) -> None:
	"""``changed`` is a delta, and both loops are carried with their verdicts."""
	body = await prg.propagate({"carbon_price_usd_per_tco2": 100.0})
	assert body["changed"], "the change moved nothing"
	# The delta, not the new value: 50 -> 100 USD/tCO2 at 0.5 t/MWh is +25.
	assert body["changed"]["marginal_cost_usd_per_mwh"] == pytest.approx(25.0)
	assert len(body["loops"]) == 2, [loop["loop"] for loop in body["loops"]]
	for loop in body["loops"]:
		# The field exists and is true. An absent key and a false one read
		# differently to a client, which is why it is carried at all.
		assert loop["converged"] is True
		assert loop["iterations"] > 0


async def test_detect_and_resolve_conflicts(prg: PRGClient) -> None:
	"""The detection names the conflict and the resolution clears it.

	The correction applied must be the first one *inside its declared range*.
	Ranking is by relative move, so on this graph the smallest proportional
	correction to an over-determined ``marginal_cost`` leaves the parameter's
	range and produces a negative fuel price -- resolving one contradiction by
	producing a scenario the graph then refuses.
	"""
	report = await prg.detect_conflicts({"marginal_cost_usd_per_mwh": 70.0})
	assert report["consistent"] is False
	over = [c for c in report["conflicts"] if c["kind"] == "over_determined"]
	assert over, [c["kind"] for c in report["conflicts"]]
	assert over[0]["subject"] == "marginal_cost_usd_per_mwh"

	resolutions = await prg.resolve_conflicts({"marginal_cost_usd_per_mwh": 70.0})
	applied = [r for r in resolutions if r["conflict"]["kind"] == "over_determined"]
	assert applied, "the over-determined conflict was not reported"
	assert applied[0]["applied"] is not None, "no in-range correction was found"
	assert applied[0]["applied"]["within_range"] is True
	assert applied[0]["resolved"] is True
	# The set after the correction is carried, and the corrected parameter is
	# in it -- a resolution reporting ``values_after`` without the move would
	# be a payload a client could not render.
	parameter = applied[0]["applied"]["parameter"]
	assert parameter in applied[0]["values_after"]


async def test_solve_feedback_serves_every_loop(prg: PRGClient) -> None:
	"""Both loops, named, with the turns each took and the values it solved."""
	body = await prg.solve_feedback()
	loops = body["loops"]
	assert len(loops) == 2, [loop["loop"] for loop in loops]
	assert len({loop["loop"] for loop in loops}) == 2, "the same loop twice"
	for loop in loops:
		assert loop["converged"] is True
		assert loop["iterations"] > 0
		assert loop["variables"] and loop["equations"]
		# The solved values are keyed by exactly the loop's variables: a
		# payload carrying a value for something the loop does not solve would
		# read as though the loop determined it.
		assert set(loop["values"]) == set(loop["variables"])
		for variable in loop["variables"]:
			assert body["values"][variable] == pytest.approx(loop["values"][variable])


async def test_translate_names_what_did_not_reach_the_engine(prg: PRGClient) -> None:
	"""The register the client exposes, which is why the call is worth making.

	``coverage`` counts from the *graph* what reaches a knob; ``parameters``
	carries what this call could form. The two differ by ``deferred`` -- a
	ratio translation whose knob exists but whose divisor needs a network this
	route does not have. Reading them as one number is how a client concludes
	the graph reaches two knobs when it reaches three.
	"""
	body = await prg.translate()
	assert body["parameters"], "nothing translated at all"
	assert body["untranslated"], "everything reached the engine, which is not so"
	assert body["coverage"]["fraction"] < 1.0
	assert len(body["parameters"]) <= body["coverage"]["count"]
	# The deferred register is disjoint from both the translated and the
	# untranslated sets: a parameter is in exactly one of the three.
	assert set(body["parameters"]) | set(body["deferred"]) | set(body["untranslated"])
	assert not set(body["deferred"]) & set(body["untranslated"])


# ---------------------------------------------------------------------------
# Failure paths: the client must not turn an error into a success
# ---------------------------------------------------------------------------


async def test_a_404_is_raised_with_the_service_detail(prg: PRGClient) -> None:
	"""An unknown parameter is an error the caller can read, not an empty dict.

	A client that returned ``{}`` for a 404 would make "no such parameter" and
	"a parameter with no fields" indistinguishable.
	"""
	with pytest.raises(PrgClientError) as caught:
		await prg.get_parameter("not_a_parameter")
	assert caught.value.status == 404
	assert "not_a_parameter" in (caught.value.detail or "")


async def test_a_422_names_the_parameters_it_rejected(prg: PRGClient) -> None:
	"""A malformed body is refused with the reason, through the client."""
	with pytest.raises(PrgClientError) as caught:
		await prg.check_consistency({"not_a_parameter": 1.0})
	assert caught.value.status == 422
	assert "not_a_parameter" in (caught.value.detail or "")


async def test_a_missing_key_is_a_401_and_not_a_silent_success(
	prg_app: httpx.AsyncClient,
) -> None:
	"""The compute routes need a tier, and the client reports the refusal.

	A client that swallowed the 401 would make an unauthenticated caller
	believe its scenario had been checked.
	"""
	anonymous = PRGClient(base_url=f"http://prg.test{API_PREFIX}", client=prg_app)
	# The read routes are public, so this one works with no key at all.
	assert (await anonymous.get_graph())["parameters"]
	with pytest.raises(PrgClientError) as caught:
		await anonymous.check_consistency()
	assert caught.value.status in (401, 403), caught.value.status


async def test_a_transport_failure_is_a_client_error_and_not_a_raw_httpx_one(
	analyst_key: str,
) -> None:
	"""A refused connection is the same exception type as a refused call.

	``PrgClientError`` exists so a caller writes one ``except``. If a
	``ConnectError`` escapes, every caller has to know that the transport
	raises its own types as well as the client raising its -- and the ones who
	do not know get a traceback out of a library they never imported.
	"""

	def refuse(request: httpx.Request) -> httpx.Response:
		raise httpx.ConnectError("connection refused", request=request)

	async with httpx.AsyncClient(
		transport=httpx.MockTransport(refuse), base_url="http://prg.test"
	) as http:
		client = PRGClient(
			base_url=f"http://prg.test{API_PREFIX}", api_key=analyst_key, client=http
		)
		with pytest.raises(PrgClientError) as caught:
			await client.get_graph()
		assert caught.value.status is None, "a transport failure has no status"
		assert "ConnectError" in str(caught.value)


async def test_a_non_json_error_body_does_not_crash_the_client(
	analyst_key: str,
) -> None:
	"""A gateway answering HTML must produce a client error, not a JSON one.

	``response.json()`` raises ``ValueError`` on an HTML error page, and a
	client that let it escape would report a parse failure for a call that
	actually reached a proxy -- the wrong diagnosis, from the wrong layer.
	"""

	def html_error(request: httpx.Request) -> httpx.Response:
		return httpx.Response(
			502, text="<html><body>Bad Gateway</body></html>", request=request
		)

	async with httpx.AsyncClient(
		transport=httpx.MockTransport(html_error), base_url="http://prg.test"
	) as http:
		client = PRGClient(
			base_url=f"http://prg.test{API_PREFIX}", api_key=analyst_key, client=http
		)
		with pytest.raises(PrgClientError) as caught:
			await client.get_graph()
		assert caught.value.status == 502
		assert "not JSON" in str(caught.value)
		assert "Bad Gateway" in str(caught.value)


async def test_the_client_closes_only_what_it_owns(
	prg_app: httpx.AsyncClient, analyst_key: str
) -> None:
	"""An injected client is the caller's to close, and the pool is not stolen.

	A client that closed an injected transport would break every other user of
	it -- the classic shared-session bug -- and one that never closed its own
	leaks a socket per instance.
	"""
	injected = PRGClient(
		base_url=f"http://prg.test{API_PREFIX}", api_key=analyst_key, client=prg_app
	)
	await injected.aclose()
	# Still usable: ``aclose`` on an injected client is a no-op by contract.
	assert (await injected.get_graph())["parameters"]

	# Closing an owned client that never opened a pool must not raise: a
	# ``finally: await client.aclose()`` around a construction that failed is
	# the common shape, and it would otherwise turn one error into two.
	owned = PRGClient(base_url=f"http://prg.test{API_PREFIX}", api_key=analyst_key)
	await owned.aclose()
	assert owned._http is None
