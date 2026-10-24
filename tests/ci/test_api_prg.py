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
def prg_client_with_registers(
	tmp_path: Path, prg_config: Config, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
	"""A client whose scratch root also carries the two files the registers read.

	`prg_config` copies only `prg.yaml`, which is the right minimal fixture for
	the routes that serve the graph. Two registers on the summary read *other*
	files -- `cross_layer` compares `config/config.default.yaml` and `catalog`
	parses `docs/params.md` -- so against the minimal root they report
	`compared: false` / `readable: false`, which is the correct behaviour and
	the reason this fixture exists rather than a widened shared one: the
	minimal root is what makes `test_a_register_that_cannot_run_says_so`
	meaningful, and widening it would take that case away.
	"""
	source = repo_root()
	(tmp_path / "docs").mkdir(parents=True, exist_ok=True)
	shutil.copy(
		source / "config" / "config.default.yaml",
		tmp_path / "config" / "config.default.yaml",
	)
	shutil.copy(source / "docs" / "params.md", tmp_path / "docs" / "params.md")
	app = create_app(prg_config)
	with TestClient(app) as client:
		yield client


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
	# The partition's honest arithmetic: a *declared exemption* is neither a
	# consistent nor an inconsistent verdict -- that is the register's whole
	# point -- so an exempt equation whose own walk could not decide it is
	# outside the three lists, and the count the equality needs is the three
	# lists plus the exempt-and-undecidable remainder. Four equations declare
	# the exemption; the ones whose walk decided them stayed in their lists.
	# The payload's own partition, which is how it is built: the three
	# verdict lists exclude the declared exemptions, so the four sets close
	# over the equations exactly. An exemption is neither a pass nor a
	# finding -- that is the register's whole point -- and it is named, which
	# is what lets a reader tell the two apart.
	assert (
		len(body["units"]["consistent"])
		+ len(body["units"]["inconsistent"])
		+ len(body["units"]["undecidable"])
		+ len(body["units"]["exempt"])
		== body["equations"]
	)


def test_the_summary_serves_the_constraint_register(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""The constraint register, with the denominator that makes it honest.

	A client reading ``count`` against ``total`` would compute 2 of 38 and
	conclude the layer reaches almost nothing; the six inequalities are the set
	that could constrain a solve, and the other 32 equations are identities the
	graph evaluates. Both numbers are served so the client cannot make that
	mistake, and the four unbound routes carry their reasons because "unbound"
	alone does not distinguish a post-solve check from a failure to build.
	"""
	response = prg_client.get("/api/v1/prg/summary", headers=public_key)
	assert response.status_code == 200, response.text
	constraints = response.json()["constraints"]
	assert constraints["count"] == len(constraints["bound"])
	assert constraints["constraint_shaped"] < constraints["total"]
	assert (
		constraints["count"] + len(constraints["unbound"])
		== constraints["constraint_shaped"]
	)
	assert constraints["constraint_shaped"] + constraints["identities"] == constraints[
		"total"
	]
	# Every route is served, and the unbound ones say why.
	routes = {route["equation_id"]: route for route in constraints["routes"]}
	assert len(routes) == constraints["constraint_shaped"]
	for equation_id in constraints["unbound"]:
		assert routes[equation_id]["status"] == "unbound"
		assert routes[equation_id]["reason"]
		assert routes[equation_id]["unresolved"]


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


def test_the_cross_validation_route_serves_every_rule_and_its_verdict(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""The rules are served with the denominator, not just the findings.

	A payload carrying only the findings would let a client render "no
	violations" for a rule set it never saw. ``rules`` is every rule considered
	and ``undecided`` counts the ones the scenario could not run, so the
	response says how much of the rule set it actually checked.
	"""
	response = prg_client.post(
		"/api/v1/prg/cross-validation", json={}, headers=analyst_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["rules"], "the shipped graph declares rules, so this is not vacuous"
	assert body["violations"] == 0, body["summary"]
	assert body["blocks"] is False
	assert all(rule["condition"] for rule in body["rules"])
	assert all("parameters" in rule for rule in body["rules"])


def test_the_cross_validation_route_fires_on_a_scenario_that_breaks_a_rule(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A scenario past an ``error`` threshold is reported, and blocks.

	The route is only a check if it can be watched failing: a rule that fired
	on nothing would pass this test's first assertion and mean nothing.
	"""
	response = prg_client.post(
		"/api/v1/prg/cross-validation",
		json={
			"set": {
				"reserve_margin_min": 0.05,
				"vre_capacity_target_mw": 25000.0,
				# The VRE build target is also the loop's own variable's driver,
				# and a 25 GW target against a 10 GW total pushes `vre_share`
				# outside its (0, 1) bracket -- the loop then has no root and
				# the whole request 500s. Total capacity is raised so the
				# scenario is one the graph can actually solve; the rule under
				# test is about the margin and the target, not the fleet size.
				"total_capacity_mw": 100000.0,
			}
		},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["violations"] >= 1, body["summary"]
	assert body["blocks"] is True
	assert any(
		finding["severity"] == "error" and finding["evaluated"]
		for finding in body["findings"]
	)


def test_the_cross_validation_route_422s_an_unknown_parameter(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	response = prg_client.post(
		"/api/v1/prg/cross-validation",
		json={"set": {"nope": 1.0}},
		headers=analyst_key,
	)
	assert response.status_code == 422


def test_the_summary_carries_the_rule_register(
	prg_client: TestClient,
) -> None:
	"""``/prg/summary`` names the declared rules, so a reader sees the check.

	The register is the point: a summary with only the graph's counts would
	leave a client assuming the rules are enforced, and until the loader was
	fixed a declared rule was silently discarded -- so the list is new
	information rather than a restatement of the file.
	"""
	body = prg_client.get("/api/v1/prg/summary").json()
	assert body["cross_validation_rules"], "no rule register on the summary"


def test_the_summary_serves_the_strength_register(
	prg_client: TestClient,
) -> None:
	"""The tiers are on the payload, so a client does not have to guess them.

	A client that assumed the spec's three strengths were all in use would read
	this graph as one where ``soft`` edges exist. The count says which tiers the
	model actually declares.
	"""
	body = prg_client.get("/api/v1/prg/summary").json()
	assert body["edge_strength"], "no strength register on the summary"
	assert sum(body["edge_strength"].values()) == body["equations"]
	assert set(body["edge_strength"]) <= {"hard", "soft", "informational"}


def test_the_conflicts_route_says_which_findings_block(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A conflict carries its tier and the verdict the CLI would reach.

	``blocks`` is on the payload rather than left for the client to derive from
	``strength``: a client that reimplemented the rule would drift from the
	CLI, and the two would disagree about whether a scenario passes.
	"""
	response = prg_client.post(
		"/api/v1/prg/conflicts",
		json={"set": {"demand_twh": 1.0}},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	conflicts = response.json()["conflicts"]
	assert conflicts
	assert all(c["strength"] in {"hard", "soft", "informational"} for c in conflicts)
	assert all(c["blocks"] is (c["strength"] != "informational") for c in conflicts)


def test_the_summary_serves_the_endogenous_layer(
	prg_client: TestClient,
) -> None:
	"""The optimiser's own layer is on the payload, and it is not the derived one.

	WHY THIS IS ASSERTED SEPARATELY FROM THE DERIVED COUNT. The two are the
	halves of "not settable", and a client that saw only ``derived`` would read
	the graph as one where every unsettable parameter is computed by an
	equation -- which is what the graph *was* until 2026-10-15, when
	``Role.ENDOGENOUS`` was declared, validated, exported, and carried by no
	node. A fleet is not computed by an equation and is not something a user
	sets; without this field the API could not say so.
	"""
	body = prg_client.get("/api/v1/prg/summary").json()
	assert body["endogenous"] == len(body["endogenous_parameters"])
	assert body["endogenous"] == 19, body["endogenous_parameters"]
	# The fleet nodes, by name: a count a client cannot act on is half a
	# register, and these are the names a scenario's result is read back into.
	assert "thermal_capacity_mw" in body["endogenous_parameters"]
	# Disjoint from the derived count, which is the claim the field exists to
	# make: a parameter the optimiser chooses is not one the graph computes.
	# Asserted as an exact closure rather than an inequality, because a client
	# reading the three counts has to be able to add them up: ``<`` passed
	# while ``derived`` was undercounting by five, and an undercount that still
	# leaves room under the total is exactly what an inequality cannot catch.
	assert body["derived"] + body["endogenous"] <= body["parameters"]
	# The partition is four-way, not three. `free` is the schema's fourth role
	# -- a node unconstrained within its range, carrying a declared range and no
	# arithmetic -- and the catalog join made it the majority: 781 of 869 nodes
	# have no equation, so computing `exogenous` as the remainder would fold
	# every one of them into a role that claims a modelling decision the
	# document does not make. Asserted by listing each role and summing, which
	# is what makes this a partition rather than three numbers that happen to
	# fit under the total.
	listed = prg_client.get("/api/v1/prg/parameters?role=exogenous").json()
	free = prg_client.get("/api/v1/prg/parameters?role=free").json()
	derived_listed = prg_client.get("/api/v1/prg/parameters?role=derived").json()
	endo_listed = prg_client.get("/api/v1/prg/parameters?role=endogenous").json()
	assert len(listed) == body["exogenous"], (len(listed), body["exogenous"])
	assert (
		len(listed) + len(free) + len(derived_listed) + len(endo_listed)
		== body["parameters"]
	), (
		len(listed),
		len(free),
		len(derived_listed),
		len(endo_listed),
		body["parameters"],
	)
	# 759 of 1312: the coupling batches converted free knobs into derived
	# quantities and named many of the rest as equation inputs. Batch 28's
	# product layer took this count 800 to 763 -- twenty-three placeholders
	# became derived and the rest of the batch's nodes were already free.
	# Batch 29 took it to 759: seven macro nodes flipped from free to derived
	# when the equations that determine them shipped, and four more free bases
	# arrived with the demand products.
	# Batch 31 took it to 739: six aliases moved a duplicate id from free to
	# derived, and twenty-two more free bases became derived under the
	# product equations.
	# Batch 33 took it to 724: fifteen of its twenty retypes became derived,
	# and the five that stayed free are the operands and policy dials a
	# scenario still sets -- `accelerated_depreciation_factor`,
	# `willingness_to_pay`, `electrolyser_capacity`, `fit_capacity_cap` and
	# `renewable_penetration_limit`.
	# Batch 38 took it 714 to 712: two of its eleven retypes became derived
	# (`payment_security_required`, `asset_age_distribution`), its nine free
	# retypes kept the role they shipped with, and its four new nodes were
	# created derived, so they never entered this count.
	# Batch 40 took it 712 to 713: `max_remedy_period_days` ships as a free
	# policy dial, and the batch's other new node -- `mwh_per_coal_unit` --
	# is exogenous, so it is counted under `exogenous` and not here. The
	# batch's ten retypes did not change a role, so they moved nothing.
	# Batch 44 took it 713 to 706: seven free nodes became derived when the
	# pollutant ledgers shipped -- `nox_emissions`, `sox_emissions`,
	# `pm10_emissions`, `pm25_annual_mean_ug_per_m3`, `voc_emissions`,
	# `mercury_emissions` and `co_emissions`. The batch's eighth retype,
	# `pm25_kt_per_year`, moved from exogenous to derived, so it left the
	# exogenous count rather than this one, and its four new derived nodes
	# (`coal_fuel_energy_gj`, `gas_fuel_energy_gj`, `oil_fuel_energy_gj` and
	# `pm25_fleet_contribution_ug_per_m3`) never entered this count. Twelve
	# is the net move in `derived`; seven is the move here.
	# The pin reads 704 rather than the 706 above because it went stale in an
	# earlier batch: measured on `HEAD:config/prg.yaml` before batch 62 the
	# count was already 704, so those two are not this batch's. Batch 62 itself
	# moved nothing here -- `energy_burden_limit` was `exogenous`, so it left
	# the exogenous register and never appeared in this one.
	assert len(free) == 704, len(free)


# ---------------------------------------------------------------------------
# The graph surface: the twelve routes that made the API match its spec
# ---------------------------------------------------------------------------
#
# These are the endpoints `alea_prg.md` §43 names and the service did not
# serve until 2026-10-15 -- five routes existed, fourteen were specified. A
# route that is registered but never requested is a capability nobody can
# reach, and the only evidence it is reachable is a request through the front
# door, so every one of them is exercised here.


def test_the_graph_route_serves_nodes_edges_equations_and_registers(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""One payload, and the three parts are each non-empty and consistent.

	A client that fetched nodes and then edges would render a graph from two
	states of a file that can change between the calls, which is why this is
	one route. The counts are cross-checked against each other: the edges must
	name parameters the node list holds, or the payload is not a graph.
	"""
	response = prg_client.get("/api/v1/prg/graph", headers=public_key)
	assert response.status_code == 200, response.text
	body = response.json()

	ids = {p["parameter_id"] for p in body["parameters"]}
	assert ids, "no parameters served"
	assert body["edges"], "no edges served"
	assert body["equations"], "no equations served"
	for edge in body["edges"]:
		assert edge["source"] in ids, edge
		assert edge["target"] in ids, edge
		assert edge["strength"] in {"hard", "soft", "informational"}, edge
	# The summary rides along, so a client needs one call and not two.
	assert body["summary"]["parameters"] == len(ids)


def test_the_graph_export_is_graphml_and_parses(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""A viewer reads GraphML, so the response has to be well-formed GraphML.

	``xml.etree`` parses it rather than a string comparison: the defect this
	guards is a payload that looks like GraphML and is not -- an undeclared
	``<key>`` reference is the common one, and it makes a viewer reject the
	whole file rather than degrade.
	"""
	from xml.etree import ElementTree

	response = prg_client.get("/api/v1/prg/graph/export", headers=public_key)
	assert response.status_code == 200, response.text
	assert "graphml" in response.headers["content-type"]
	root = ElementTree.fromstring(response.text)
	namespace = "{http://graphml.graphdrawing.org/xmlns}"
	assert root.tag == f"{namespace}graphml", root.tag
	# Every `key` an attribute cites must be declared, or the file is invalid
	# to a strict reader even though ElementTree parses it.
	declared = {key.get("id") for key in root.findall(f"{namespace}key")}
	assert declared, "no keys declared"
	graph = root.find(f"{namespace}graph")
	assert graph is not None
	for element in list(graph):
		for attribute in element.attrib:
			if attribute.startswith("d"):
				assert attribute in declared, (attribute, declared)
	# The node count matches the graph route's, so the two views agree.
	assert len(graph.findall(f"{namespace}node")) == len(
		prg_client.get("/api/v1/prg/graph", headers=public_key).json()["parameters"]
	)


def test_the_parameters_route_filters_by_category_and_role(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""The two filters a client actually wants, and they compose.

	A filter that silently returned everything would pass a test that only
	checked the unfiltered call, so the filtered set is asserted to be a strict
	subset and every member is checked against the filter.
	"""
	everything = prg_client.get("/api/v1/prg/parameters", headers=public_key).json()
	assert everything

	role = prg_client.get(
		"/api/v1/prg/parameters", params={"role": "exogenous"}, headers=public_key
	)
	assert role.status_code == 200, role.text
	exogenous = role.json()
	assert 0 < len(exogenous) < len(everything), len(exogenous)
	assert all(p["role"] == "exogenous" for p in exogenous)

	category = everything[0]["category"]
	by_category = prg_client.get(
		"/api/v1/prg/parameters", params={"category": category}, headers=public_key
	).json()
	assert 0 < len(by_category) < len(everything), len(by_category)
	assert all(p["category"] == category for p in by_category)

	# An unknown role is refused by the pattern rather than served as empty,
	# because an empty list reads as "the graph has none of these".
	assert (
		prg_client.get(
			"/api/v1/prg/parameters", params={"role": "nonsense"}, headers=public_key
		).status_code
		== 422
	)


def test_one_parameter_route_serves_it_and_404s_an_unknown_one(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""A named parameter comes back whole; an unnamed one is a 404.

	The couplings are served from the equations rather than the YAML's declared
	lists, and the two are compared by ``structure_issues`` -- so a payload
	whose ``affects`` disagreed with the equations would be serving a document
	that had drifted from the graph the engine walks.
	"""
	response = prg_client.get(
		"/api/v1/prg/parameters/equilibrium_demand_twh", headers=public_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["parameter_id"] == "equilibrium_demand_twh"
	# A demand is a flow, and the unit says so: the node was `TWh` until batch
	# 24 restated the demand family per year, and this pin outlived the change
	# because nothing between then and batch 28 read the route's unit field.
	assert body["unit"] == "TWh/year"
	assert body["role"] == "derived"
	# A loop variable is derived and carries an `initial` rather than a
	# `default`: it is where the iteration starts, not a value standing in for
	# the equation, and the payload has to say so. Both halves are asserted --
	# the absent `default` *and* the present `initial` -- because asserting only
	# the absence left the payload free to serve neither, which is what it did
	# until 2026-10-16: a client rebuilding the declared graph from this route
	# could not tell a loop variable with a starting point from one falling back
	# to its range midpoint.
	assert body.get("default") is None
	assert body["initial"] == 45.0

	# And a parameter outside every loop declares neither, so `initial` is
	# `None` rather than a value invented to fill the field.
	plain = prg_client.get("/api/v1/prg/parameters/asset_life", headers=public_key).json()
	assert plain["initial"] is None

	missing = prg_client.get("/api/v1/prg/parameters/not_a_parameter", headers=public_key)
	assert missing.status_code == 404, missing.text
	assert "not_a_parameter" in missing.json()["detail"]


def test_the_dependents_route_serves_the_closure_and_can_stop_at_one_hop(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""The closure is what a caller wants; one hop is a different question.

	Both are served, and the test asserts the relationship between them rather
	than either count: the closure contains the one-hop set and is strictly
	larger, because a parameter with a single dependent would make the two
	equal and the test vacuous.
	"""
	full = prg_client.get(
		"/api/v1/prg/parameters/demand_growth/dependents", headers=public_key
	)
	assert full.status_code == 200, full.text
	closure = full.json()
	assert closure, "demand_growth moves nothing, which cannot be right"

	direct = prg_client.get(
		"/api/v1/prg/parameters/demand_growth/dependents",
		params={"direct_only": True},
		headers=public_key,
	).json()
	assert 0 < len(direct) < len(closure), (len(direct), len(closure))
	# Ordered by distance, so a client can re-check the nearest first.
	distances = [entry["distance"] for entry in closure]
	assert distances == sorted(distances), distances
	assert all(entry["distance"] >= 1 for entry in direct), direct

	# The one-hop set is the `affects` field the parameter route already
	# serves, and the closure is its transitive extension -- so the two agree
	# on the first hop and the closure is the strictly larger of the pair. A
	# test asserting they were *equal* would be asserting the route is the
	# one-hop view it was written to be distinct from.
	one = prg_client.get(
		"/api/v1/prg/parameters/demand_growth", headers=public_key
	).json()
	assert {entry["parameter_id"] for entry in direct} == set(one["affects"])
	assert set(one["affects"]) <= {entry["parameter_id"] for entry in closure}


def test_the_equation_route_serves_one_equation_and_404s_an_unknown_one(
	prg_client: TestClient, public_key: dict[str, str]
) -> None:
	"""One equation, rendered, with the system it belongs to."""
	response = prg_client.get(
		"/api/v1/prg/equations/crf_definition", headers=public_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["equation_id"] == "crf_definition"
	assert body["system"] == "cost_accounting"
	assert body["rendered"], "an equation with no rendering"

	missing = prg_client.get("/api/v1/prg/equations/not_an_equation", headers=public_key)
	assert missing.status_code == 404, missing.text


def test_the_consistency_route_checks_a_set_it_was_handed(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""The graph's own defaults hold, and a forced contradiction does not.

	Both directions, because a route that always answered "consistent" would
	pass a test that only checked the happy path. The contradiction is the one
	the graph exists to catch: ``marginal_cost`` is computed as fuel plus
	carbon, so setting it to a value that arithmetic does not give is a
	scenario nobody described.
	"""
	clean = prg_client.post(
		"/api/v1/prg/consistency/check", json={"set": {}}, headers=analyst_key
	)
	assert clean.status_code == 200, clean.text
	assert clean.json()["consistent"] is True
	assert clean.json()["violations"] == []
	assert clean.json()["checked"] > 0

	# A five-year asset life cannot carry the debt schedule: the DSCR the
	# annuity implies falls below the covenant, and the graph reports it. The
	# parameter is settable, so the scenario is one a caller can describe --
	# which is the difference between a check that fires and a check that
	# refuses the input as malformed.
	dirty = prg_client.post(
		"/api/v1/prg/consistency/check",
		json={"set": {"asset_life": 5.0}},
		headers=analyst_key,
	)
	assert dirty.status_code == 200, dirty.text
	body = dirty.json()
	assert body["consistent"] is False
	assert body["violations"], "an unfinanceable scenario produced no violation"
	violation = body["violations"][0]
	assert violation["detail"], "a violation with no detail is not actionable"
	# Batch 47 corrected `fleet_emission_intensity_t_per_mwh` from 0.5000 to
	# 0.3271, which cut emissions 35% and with them carbon revenue. At a
	# five-year life the revenue share now falls to 4.21% against the 5%
	# `carbon_finance_share` floor, so `carbon_finance_bound` fires alongside
	# the DSCR covenant and sorts first. That second violation is a real
	# consequence of the repair, not noise: this test is about the DSCR
	# scenario, so it asserts the DSCR is among the violations rather than
	# that it heads the list.
	fired = {v["equation_id"] for v in body["violations"]}
	assert "dscr_requirement" in fired, fired


def test_the_consistency_report_is_the_shipped_default_scenario(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""The baseline a client fetches first, and it agrees with the check route.

	The spec calls this "last consistency report", which presumes per-caller
	session state this service does not keep. It answers the question the name
	is *for* -- is the scenario the graph ships consistent -- and the test pins
	that the two routes agree on it, so a client cannot get different answers
	from the baseline and from an empty set.
	"""
	baseline = prg_client.get("/api/v1/prg/consistency/report", headers=analyst_key)
	assert baseline.status_code == 200, baseline.text
	body = baseline.json()
	assert body["consistent"] is True
	assert body["checked"] > 0

	empty_set = prg_client.post(
		"/api/v1/prg/consistency/check", json={"set": {}}, headers=analyst_key
	).json()
	assert body["consistent"] == empty_set["consistent"]
	assert body["checked"] == empty_set["checked"]


def test_the_propagate_route_reports_what_moved(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A change to a settable parameter moves its dependents and nothing else.

	``changed`` is the point: a client that received only ``values`` could not
	tell what its edit did without diffing two large dictionaries itself.
	"""
	response = prg_client.post(
		"/api/v1/prg/propagate",
		json={"set": {}, "changes": {"carbon_price_usd_per_tco2": 100.0}},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["changed"], "a carbon price moved nothing"
	assert "marginal_cost_usd_per_mwh" in body["changed"]
	# `changed` is the *delta*, not the new value -- a payload serving the
	# absolute under a key called "changed" would make a client that added it
	# to the old value double-count. The identity is what pins it: the price
	# moves 50 -> 100 USD/tCO2, which at 0.5 t/MWh adds 25 USD/MWh to a
	# marginal cost of 40 + 50*0.5 = 65.
	assert body["changed"]["marginal_cost_usd_per_mwh"] == pytest.approx(25.0)
	assert body["values"]["marginal_cost_usd_per_mwh"] == pytest.approx(90.0)
	# The loops are reported, because a propagation that crossed a fixed point
	# without saying so would hide the iteration from the caller.
	assert body["loops"], "the propagation crossed no loop"
	assert all(loop["converged"] for loop in body["loops"])

	# An empty change set is refused rather than served as a no-op report.
	empty = prg_client.post(
		"/api/v1/prg/propagate", json={"set": {}, "changes": {}}, headers=analyst_key
	)
	assert empty.status_code == 422, empty.text

	# A derived parameter cannot be changed: setting it alongside the parameter
	# it depends on is exactly the inconsistency the graph refuses.
	derived = prg_client.post(
		"/api/v1/prg/propagate",
		json={"set": {}, "changes": {"marginal_cost_usd_per_mwh": 70.0}},
		headers=analyst_key,
	)
	assert derived.status_code == 422, derived.text
	assert "marginal_cost_usd_per_mwh" in derived.json()["detail"]


def test_the_resolve_route_applies_a_correction_and_rechecks(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""A contradiction is resolved, and the report says the set now holds.

	The correction is the smallest real-world change that clears the residual,
	so the test asserts the *outcome* -- the set is consistent after -- rather
	than the delta, which is a number the ranking is free to change.
	"""
	response = prg_client.post(
		"/api/v1/prg/conflicts/resolve",
		json={"set": {"marginal_cost_usd_per_mwh": 70.0}},
		headers=analyst_key,
	)
	assert response.status_code == 200, response.text
	resolutions = response.json()
	assert resolutions, "a contradiction produced no resolution"
	# The over-determination of `marginal_cost` is the conflict under test; the
	# report also carries the under-determined parameters, which have no
	# correction to apply and are reported as such rather than omitted.
	over = [r for r in resolutions if r["conflict"]["kind"] == "over_determined"]
	assert over, [r["conflict"]["kind"] for r in resolutions]
	first = over[0]
	assert first["applied"] is not None, first
	assert first["conflict"]["subject"] == "marginal_cost_usd_per_mwh"
	# The correction is one that *stays inside its declared range*. Every
	# candidate for a large residual leaves it -- the smallest proportional
	# move is still negative fuel -- and applying one of those would resolve
	# this contradiction by producing a scenario the graph refuses.
	assert first["applied"]["within_range"] is True, first["applied"]
	assert first["resolved"] is True, first
	# What the correction *does*: it moves a term the equation is computed
	# from, so the identity now agrees with the value that was supplied. The
	# supplied 70 is unchanged -- a correction that instead overwrote the
	# caller's number would be answering a different question.
	assert first["applied"]["parameter"] == "fuel_price_usd_per_mwh"
	assert first["values_after"]["fuel_price_usd_per_mwh"] != pytest.approx(40.0)
	assert first["values_after"]["marginal_cost_usd_per_mwh"] == pytest.approx(70.0)

	# A consistent set has nothing to resolve, and an empty list is the honest
	# answer rather than a manufactured conflict.
	clean = prg_client.post(
		"/api/v1/prg/conflicts/resolve", json={"set": {}}, headers=analyst_key
	)
	assert clean.status_code == 200, clean.text
	assert clean.json() == []


def test_the_feedback_route_solves_every_loop_and_reports_the_iteration(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""Both loops, each with the turns it took and what it settled on.

	"Converged" alone is not a result a reader can weigh -- a loop that settled
	in four turns and one that needed 180 both report success -- so the
	iteration count is asserted to be present and positive, and the values to
	be the loop's own variables.
	"""
	response = prg_client.post(
		"/api/v1/prg/feedback/solve", json={"set": {}}, headers=analyst_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert len(body["loops"]) == 2, [loop["loop"] for loop in body["loops"]]
	# Named, not counted: a solver that reported the same loop twice would pass
	# a length check.
	assert len({loop["loop"] for loop in body["loops"]}) == 2
	for loop in body["loops"]:
		assert loop["converged"] is True, loop
		assert loop["iterations"] > 0, loop
		assert loop["variables"], loop
		assert loop["equations"], loop
		# The solved values are the loop's variables and nothing else: a
		# payload carrying the whole graph here would hide which numbers the
		# iteration actually determined.
		assert set(loop["values"]) == set(loop["variables"]), loop


def test_the_translate_route_names_what_did_not_reach_the_engine(
	prg_client: TestClient, analyst_key: dict[str, str]
) -> None:
	"""The register is the point: most parameters reach no engine knob.

	A client that received only ``parameters`` would believe the whole scenario
	reached the engine, and a scenario that sets one of the others solves as
	though it had not been set. So the untranslated list is asserted to be
	non-empty and to be the complement of what did translate.
	"""
	response = prg_client.post(
		"/api/v1/prg/translate", json={"set": {}}, headers=analyst_key
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["parameters"], "nothing translated at all"
	assert body["untranslated"], "everything reached the engine, which is not the case"
	assert body["coverage"], "no coverage register"
	# Disjoint: a parameter cannot both reach a knob and be named as not
	# reaching one.
	routed = {route["parameter"] for route in body["routes"]}
	assert not (routed & set(body["untranslated"])), routed & set(body["untranslated"])
	# Ratio translations need a network this route does not have, and they are
	# named rather than dropped: a modelling gap and an API limitation are
	# different findings.
	assert any(route["kind"] == "absolute" for route in body["routes"])
	assert body["deferred"], "the ratio translation was dropped, not deferred"
	# The three registers must not contradict each other. ``coverage`` is
	# computed from the graph, so a parameter it counts as reaching a knob may
	# not appear in ``untranslated`` -- but it *may* appear in ``deferred``,
	# because a deferred parameter does reach one; this route just could not
	# form the ratio. Merging the two lists made the payload assert both, and
	# a client reading either register got the opposite answer.
	graph_routed = set(body["coverage"]["translated"])
	assert not (graph_routed & set(body["untranslated"])), graph_routed & set(
		body["untranslated"]
	)
	assert set(body["deferred"]) <= graph_routed, set(body["deferred"]) - graph_routed
	assert set(body["deferred"]).isdisjoint(body["untranslated"])
	# And the union is the whole settable surface: a parameter in neither list
	# and in neither payload is one no register accounts for.
	accounted = graph_routed | set(body["untranslated"]) | set(body["deferred"])
	assert accounted == set(body["coverage"]["translated"]) | set(
		body["coverage"]["untranslated"]
	), accounted.symmetric_difference(
		set(body["coverage"]["translated"]) | set(body["coverage"]["untranslated"])
	)


def test_the_summary_serves_the_cross_layer_register(
	prg_client_with_registers: TestClient,
) -> None:
	"""The register that compares `config/` against the graph reaches a door.

	It was computed on the summary and served by neither the API nor the CLI
	for as long as it existed -- `declared is not produced`, on the register
	built to catch that class. The payload carries both measured values and
	their ratio, not only the prose that describes them, because a sentence is
	not a measurement and nothing parses one.
	"""
	body = prg_client_with_registers.get("/api/v1/prg/summary").json()
	cross = body["cross_layer"]
	assert cross["compared"] is True, cross["reason"]
	assert cross["disagreements"], (
		"the VoLL disagreement is no longer reported; either the layers agree "
		"now or the register went blind"
	)
	row = next(
		r for r in cross["disagreements"] if r["prg_parameter"] == "voll_usd_per_mwh"
	)
	assert row["config_value"] == 2000.0, row
	assert row["graph_value"] == 5000.0, row
	assert row["ratio"] == pytest.approx(2.5), row
	assert row["unit"] == "USD/MWh"


def test_the_summary_serves_the_catalog_join(
	prg_client_with_registers: TestClient,
) -> None:
	"""`docs/params.md` as data, with the one drifted node named.

	The status join is the half that matters: the graph's `status` was
	hand-copied from the catalog's column, so a disagreement is a transcription
	with no diff -- a defect no other check can see. Serving only the counts
	would let a client render the catalog as a document rather than a register
	with a live disagreement in it.
	"""
	body = prg_client_with_registers.get("/api/v1/prg/summary").json()
	catalog = body["catalog"]
	assert catalog["readable"] is True, catalog["reason"]
	assert catalog["row_count"] > 0
	assert catalog["status_join"], "no status join on the summary"
	joined = {row["parameter"]: row for row in catalog["status_join"]}
	assert "equity_return_target" in joined, sorted(joined)
	assert joined["equity_return_target"]["agrees"] is False
	assert catalog["status_disagreements"], "the drift is not named"
