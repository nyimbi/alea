# SPDX-License-Identifier: MIT
"""What-if job handlers.

A what-if solve is the canonical long job: the specification runs one for up to
two hours inside a route (11-layer8 §2.3), which blocks the event loop and loses
the answer if the process dies. Here it is a job -- enqueued by the route,
claimed by the worker, written to a content-addressed artefact, and readable
after a restart.

**The cache key is deterministic.** It is a SHA-256 over canonical JSON of the
parameters, the base network checksum and the base result checksum. The
specification's engine keys on ``hash(tuple(sorted(params.__dict__.items())))``,
and Python randomises string hashing per interpreter, so the key differs between
runs: the cache silently misses and the reproducibility test passes for the
wrong reason (AD-8, 08-layer5 §2.2). Nothing here touches ``hash()``.

**The result is an artefact with provenance**, because AD-4 says every stage
writes a versioned file and no stage holds a live object across a boundary. The
handler returns a JSON-serialisable dict to the job store; the artefact is what
a later report reads.

**Honesty about the placeholder.** ``alea.whatif`` (Layer 5) is not built yet.
Where the real engine is importable the handler uses it; where it is not, the
handler derives a result from the base scenario by proportional scaling and
records that fact in the artefact's provenance and in the value's ``basis`` and
``uncertainty``. A placeholder that is labelled as one is a stub; a placeholder
that is not is a fabricated number, and the difference is entirely in the
provenance.
"""

from __future__ import annotations

import json
from typing import Any

from alea.api.jobs import JobContext, JobStore, JobWorker
from alea.api.repository import Repository
from alea.api.views import (
	JobKind,
	ScenarioParametersIn,
	WhatIfFrontierRequest,
	WhatIfSolveRequest,
)
from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import write_artefact
from alea.logging import get_logger
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)

WHATIF_DIR = "results/whatif"

PLACEHOLDER_UNCERTAINTY = 0.35
"""Relative uncertainty stamped on a placeholder derivation.

Deliberately large. The number is not a model output and must not be read as
one; a 35% band on every value is the strongest signal the API can carry short
of refusing to answer.
"""


def solve_cache_key(
	parameters: ScenarioParametersIn, *, network_checksum: str, base_result_checksum: str
) -> str:
	"""A deterministic key over the parameters and both input checksums.

	Both checksums are in the key. A key over the parameters alone serves a
	result computed against a previous network, which is the defect the plan
	names in Layer 5's own cache.
	"""
	assert network_checksum, "a what-if key must include the base network checksum"
	assert base_result_checksum, "a what-if key must include the base result checksum"
	import hashlib

	canonical = json.dumps(
		{
			"parameters": parameters.model_dump(mode="json", exclude_none=True),
			"network_checksum": network_checksum,
			"base_result_checksum": base_result_checksum,
		},
		sort_keys=True,
		separators=(",", ":"),
	)
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WhatIfService:
	"""Enqueues what-if work and runs it.

	The enqueue half is called from a route and returns immediately; the run half
	is registered on the worker and never touches the request path.
	"""

	def __init__(self, config: Config, repository: Repository) -> None:
		assert config is not None and repository is not None, "the service needs config and a repository"
		self.config = config
		self.repository = repository

	# -- enqueue -----------------------------------------------------------

	async def enqueue_solve(
		self, store: JobStore, request: WhatIfSolveRequest, *, requested_by: str
	) -> str:
		"""Submit a solve job. Returns its id."""
		assert request is not None, "enqueue_solve needs a request"
		status = await store.submit(
			JobKind.WHATIF_SOLVE,
			request.model_dump(mode="json"),
			requested_by=requested_by,
		)
		return status.job_id

	async def enqueue_frontier(
		self, store: JobStore, request: WhatIfFrontierRequest, *, requested_by: str
	) -> str:
		"""Submit a frontier sweep job. Returns its id."""
		assert request is not None, "enqueue_frontier needs a request"
		status = await store.submit(
			JobKind.WHATIF_FRONTIER,
			request.model_dump(mode="json"),
			requested_by=requested_by,
		)
		return status.job_id

	# -- handlers ----------------------------------------------------------

	def register(self, worker: JobWorker) -> None:
		"""Bind both handlers to the worker."""
		assert worker is not None, "register needs a worker"
		worker.register(JobKind.WHATIF_SOLVE, self._run_solve)
		worker.register(JobKind.WHATIF_FRONTIER, self._run_frontier)

	async def _run_solve(self, request: dict[str, Any], context: JobContext) -> dict[str, Any]:
		"""Run one what-if solve and write its result artefact."""
		assert isinstance(request, dict), "a job request is an object"
		await context.progress(0.05)
		solve_request = WhatIfSolveRequest.model_validate(request)

		base = self._load_base(solve_request.base_scenario_id)
		await context.progress(0.2)

		key = solve_cache_key(
			solve_request.parameters,
			network_checksum=base["network_checksum"],
			base_result_checksum=base["result_checksum"],
		)
		await context.progress(0.5)

		result = self._derive(solve_request, base, key)
		await context.progress(0.8)

		checksum = self._persist(key, result, base)
		result["result_checksum"] = checksum
		await context.progress(1.0)
		logger.info(
			"whatif.solved",
			scenario_id=solve_request.base_scenario_id,
			cache_key=key,
			checksum=checksum,
		)
		return result

	async def _run_frontier(self, request: dict[str, Any], context: JobContext) -> dict[str, Any]:
		"""Sweep one parameter across a range and write the frontier artefact."""
		assert isinstance(request, dict), "a job request is an object"
		frontier_request = WhatIfFrontierRequest.model_validate(request)
		base = self._load_base(frontier_request.base_scenario_id)

		points: list[dict[str, Any]] = []
		step = (frontier_request.stop - frontier_request.start) / (frontier_request.points - 1)
		for index in range(frontier_request.points):
			value = frontier_request.start + step * index
			parameters = ScenarioParametersIn(**{frontier_request.parameter: value})
			key = solve_cache_key(
				parameters,
				network_checksum=base["network_checksum"],
				base_result_checksum=base["result_checksum"],
			)
			solved = self._derive(
				WhatIfSolveRequest(
					base_scenario_id=frontier_request.base_scenario_id,
					parameters=parameters,
				),
				base,
				key,
			)
			points.append(
				{
					"parameter_value": value,
					"objective": solved["objective"],
					"emissions": solved["emissions"],
				}
			)
			await context.progress((index + 1) / frontier_request.points)

		payload = {
			"parameter": frontier_request.parameter,
			"points": points,
			"base_scenario_id": frontier_request.base_scenario_id,
			"network_checksum": base["network_checksum"],
		}
		self._persist_document(f"{WHATIF_DIR}/frontiers", payload, base)
		logger.info(
			"whatif.frontier",
			scenario_id=frontier_request.base_scenario_id,
			parameter=frontier_request.parameter,
			points=len(points),
		)
		return payload

	# -- derivation --------------------------------------------------------

	def _load_base(self, scenario_id: str) -> dict[str, Any]:
		"""The base scenario's horizon-zero result, or a refusal.

		A solve against a scenario that does not exist is refused here rather than
		against an empty default, because a what-if result computed from nothing
		looks exactly like one computed from a network.
		"""
		assert scenario_id, "a what-if solve needs a base scenario"
		scenario = self.repository.scenario(scenario_id)
		if scenario is None:
			raise ValueError(
				f"base scenario {scenario_id!r} is not in the catalogue; a what-if "
				f"solve needs a solved scenario to vary"
			)
		horizon = scenario.planning_horizons[0] if scenario.planning_horizons else 2030
		result = self.repository.scenario_result(scenario_id, horizon)
		if result is None:
			raise ValueError(
				f"base scenario {scenario_id!r} has no solved result at {horizon}; "
				f"solve it before varying it"
			)
		checksum = self.repository.scenario_result_checksum(scenario_id, horizon) or ""
		return {
			"scenario_id": scenario_id,
			"name": scenario.name,
			"horizon": horizon,
			"network_checksum": scenario.network_checksum or checksum or scenario_id,
			"result_checksum": checksum or scenario_id,
			"objective": result.objective.value,
			"total_capacity_mw": result.total_capacity_mw.value,
			"capacity_mix": [
				{
					"carrier": row.carrier,
					"capacity_mw": row.capacity_mw.value,
					"share": row.share.value,
				}
				for row in result.capacity_mix
			],
		}

	def _derive(
		self, request: WhatIfSolveRequest, base: dict[str, Any], key: str
	) -> dict[str, Any]:
		"""Produce a result from the base scenario and the parameters.

		Uses the real Layer 5 engine when it is importable. Until then, it scales
		the base result by the parameters and stamps every value with a large
		uncertainty and a provenance note saying so.
		"""
		assert request is not None and base is not None, "derive needs a request and a base"
		real = _try_real_engine(request, base)
		if real is not None:
			return real

		parameters = request.parameters
		objective = base["objective"]
		capacity = base["total_capacity_mw"]

		if parameters.carbon_price_usd_per_tco2 is not None:
			objective += parameters.carbon_price_usd_per_tco2 * capacity * 0.4
		if parameters.demand_growth_pct is not None:
			capacity *= 1.0 + parameters.demand_growth_pct / 100.0
			objective *= 1.0 + parameters.demand_growth_pct / 100.0
		if parameters.renewable_multiplier is not None:
			capacity *= parameters.renewable_multiplier
		if parameters.fuel_price_multiplier is not None:
			objective *= parameters.fuel_price_multiplier
		if parameters.battery_capex_multiplier is not None:
			objective *= 0.9 + 0.1 * parameters.battery_capex_multiplier

		mix = []
		for row in base["capacity_mix"]:
			share = row["share"]
			scaled = row["capacity_mw"]
			if parameters.renewable_multiplier is not None and row["carrier"] in (
				"solar",
				"wind",
				"hydro",
			):
				scaled *= parameters.renewable_multiplier
			mix.append({"carrier": row["carrier"], "capacity_mw": scaled, "share": share})
		total = sum(item["capacity_mw"] for item in mix) or capacity

		note = (
			"placeholder derivation: alea.whatif (Layer 5) is not implemented; "
			"values are scaled from the base scenario, not re-solved"
		)
		return {
			"job_id": "",
			"scenario_id": request.base_scenario_id,
			"name": request.name or f"{request.base_scenario_id} +{key[:8]}",
			"objective": _modelled(objective, "USD", note),
			"total_capacity_mw": _modelled(total, "MW", note),
			"capacity_mix": [
				{
					"carrier": item["carrier"],
					"capacity_mw": _modelled(item["capacity_mw"], "MW", note),
					"share": _modelled(
						item["capacity_mw"] / total if total else 0.0, "fraction", note
					),
				}
				for item in mix
			],
			"emissions": _modelled(objective * 0.0002, "tCO2", note),
			"parameters": parameters.model_dump(mode="json", exclude_none=True),
			"network_checksum": base["network_checksum"],
			"result_checksum": "",
			"placeholder": True,
		}

	# -- persistence -------------------------------------------------------

	def _persist(self, key: str, result: dict[str, Any], base: dict[str, Any]) -> str:
		"""Write the result artefact with provenance. Returns its checksum."""
		assert key, "a result is addressed by its key"
		payload = {k: v for k, v in result.items() if k != "result_checksum"}
		return self._persist_document(f"{WHATIF_DIR}/{key}", payload, base)

	def _persist_document(self, directory: str, payload: dict[str, Any], base: dict[str, Any]) -> str:
		"""Write one JSON artefact with a derived provenance sidecar."""
		path = resolve(f"{directory}/result.json")
		provenance = DerivedProvenance(
			source_id="alea.whatif",
			basis=Basis.MODELLED,
			uncertainty=PLACEHOLDER_UNCERTAINTY,
			uncertainty_basis="placeholder derivation pending the Layer 5 engine",
			notes=(
				"what-if result derived by the API worker; see the payload's "
				"placeholder flag for whether Layer 5 solved it"
			),
			inputs=[base["network_checksum"], base["result_checksum"]],
			code_version=self.config.api.version,
		)
		return write_artefact(path, payload, provenance)


def _modelled(value: float, unit: str, note: str) -> dict[str, Any]:
	"""A value payload stamped as a modelled placeholder."""
	return {
		"value": float(value),
		"unit": unit,
		"basis": Basis.MODELLED.value,
		"uncertainty": PLACEHOLDER_UNCERTAINTY,
		"source_id": "alea.whatif",
		"note": note,
	}


def _try_real_engine(request: WhatIfSolveRequest, base: dict[str, Any]) -> dict[str, Any] | None:
	"""Use Layer 5's engine when it exists.

	Imported lazily and guarded: Layer 5 is a separate deliverable and the API
	must construct and serve before it lands. When it lands, this is the one
	line that starts using it.
	"""
	try:
		from alea.whatif.service import solve_what_if  # type: ignore[attr-defined]
	except ImportError:
		return None
	logger.info("whatif.engine.real", scenario_id=request.base_scenario_id)
	result = solve_what_if(request.parameters, base)  # pragma: no cover - Layer 5 absent
	if not isinstance(result, dict):
		raise TypeError("alea.whatif.solve_what_if returned a non-object")
	return result


__all__ = [
	"PLACEHOLDER_UNCERTAINTY",
	"WHATIF_DIR",
	"WhatIfService",
	"solve_cache_key",
]
