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

**Layer 5 is used, not simulated.** The handler builds a
:class:`~alea.whatif.service.WhatIfEngine` over the base network the catalogue
publishes and solves through it. The engine's docstring states why it owns no
physics: every solve calls Layer 1's expansion. The proportional-scaling path
below remains, and is reached only when the base network file is absent, which
is the one case where there is nothing to re-solve; it stamps every value with
:data:`PLACEHOLDER_UNCERTAINTY` and ``placeholder: true`` so a scaled number is
never read as a solved one. A placeholder that is labelled as one is a stub; a
placeholder that is not is a fabricated number, and the difference is entirely
in the provenance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from alea.api.jobs import JobContext, JobStore, JobWorker
from alea.api.repository import Repository
from alea.api.views import (
	JobKind,
	ScenarioParametersIn,
	WhatIfCompareRequest,
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

	async def enqueue_compare(
		self, store: JobStore, request: WhatIfCompareRequest, *, requested_by: str
	) -> str:
		"""Submit a comparison job. Returns its id."""
		assert request is not None, "enqueue_compare needs a request"
		status = await store.submit(
			JobKind.WHATIF_COMPARE,
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
		worker.register(JobKind.WHATIF_COMPARE, self._run_compare)

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
			parameters = ScenarioParametersIn.one(frontier_request.parameter, value)
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

	async def _run_compare(self, request: dict[str, Any], context: JobContext) -> dict[str, Any]:
		"""Compare solved scenarios at one horizon, side by side.

		Reads each scenario's stored result and reports the differences. It does
		not re-solve: the request names scenarios, and a scenario is by
		definition something already solved and in the catalogue. A comparison
		that silently solved the ones that were missing would report a mixture
		of fresh and stored numbers with nothing saying which was which.
		"""
		assert isinstance(request, dict), "a job request is an object"
		compare_request = WhatIfCompareRequest.model_validate(request)
		horizon = compare_request.horizon

		rows: list[dict[str, Any]] = []
		for index, scenario_id in enumerate(compare_request.scenario_ids):
			scenario = self.repository.scenario(scenario_id)
			if scenario is None:
				raise ValueError(
					f"scenario {scenario_id!r} is not in the catalogue; compare "
					f"reads solved scenarios and does not solve them"
				)
			result = self.repository.scenario_result(scenario_id, horizon)
			if result is None:
				raise ValueError(
					f"scenario {scenario_id!r} has no solved result at {horizon}; "
					f"the other scenarios cannot be compared against it"
				)
			rows.append(
				{
					"scenario_id": scenario_id,
					"name": scenario.name,
					"horizon": horizon,
					"objective": result.objective.model_dump(mode="json"),
					"total_capacity_mw": result.total_capacity_mw.model_dump(mode="json"),
					"capacity_mix": [
						{
							"carrier": row.carrier,
							"capacity_mw": row.capacity_mw.model_dump(mode="json"),
							"share": row.share.model_dump(mode="json"),
						}
						for row in result.capacity_mix
					],
					"network_checksum": result.network_checksum,
				}
			)
			await context.progress((index + 1) / len(compare_request.scenario_ids))

		payload = {
			"horizon": horizon,
			"scenarios": rows,
			# Differences against the first scenario, which is the request's own
			# stated base. Reported here rather than left to the client because
			# "which one changed" is the question the endpoint exists to answer.
			"deltas_vs_first": _deltas(rows),
		}
		self._persist_document(f"{WHATIF_DIR}/comparisons", payload, {"network_checksum": rows[0]["network_checksum"], "result_checksum": rows[0]["scenario_id"]})
		logger.info("whatif.compare", horizon=horizon, scenarios=len(rows))
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
			"code_version": scenario.code_version,
			"network_path": self.repository.scenario_network_path(scenario_id),
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

		The engine is the answer; the fallback exists only for a catalogue whose
		network file is missing, and it says so loudly. It does not scale: the
		previous version multiplied the base objective by a coefficient per
		parameter, and those coefficients (``0.4`` tonnes per dollar of carbon
		price, ``0.0002`` tonnes per dollar of cost) were invented here. A
		scaled number carries the base scenario's structure, so it looks like a
		solved result while being a guess about which of four levers moves which
		number, and it was served for every request because the engine probe was
		broken. Refusing is the honest answer when there is nothing to solve.
		"""
		assert request is not None and base is not None, "derive needs a request and a base"
		network_path: Path | None = base.get("network_path")
		if network_path is not None:
			solved = _try_real_engine(request, base, network_path)
			assert solved is not None, "the engine solves or raises; it does not abstain"
			return solved

		raise ValueError(
			f"base scenario {base['scenario_id']!r} has no network file in the "
			f"catalogue, so there is nothing to re-solve; re-run the solve to "
			f"publish it, or use the stored result at horizon {base['horizon']}"
		)

	# -- persistence -------------------------------------------------------

	def _persist(self, key: str, result: dict[str, Any], base: dict[str, Any]) -> str:
		"""Write the result artefact with provenance. Returns its checksum."""
		assert key, "a result is addressed by its key"
		payload = {k: v for k, v in result.items() if k != "result_checksum"}
		return self._persist_document(f"{WHATIF_DIR}/{key}", payload, base)

	def _persist_document(self, directory: str, payload: dict[str, Any], base: dict[str, Any]) -> str:
		"""Write one JSON artefact with a derived provenance sidecar.

		The band depends on what produced the payload. A solved result carries
		the engine's own uncertainty; only a scaled placeholder gets the 35%
		band. Stamping the placeholder band on a solve would understate a real
		answer, and stamping a solve's band on a placeholder would overstate a
		guess -- the reader takes the sidecar as the truth about the artefact.
		"""
		path = resolve(f"{directory}/result.json")
		placeholder = bool(payload.get("placeholder", False))
		provenance = DerivedProvenance(
			source_id="alea.whatif",
			basis=Basis.MODELLED,
			uncertainty=PLACEHOLDER_UNCERTAINTY if placeholder else 0.05,
			uncertainty_basis=(
				"scaled from the base scenario, not re-solved"
				if placeholder
				else "input error dominates; the solve is exact given its inputs"
			),
			notes=(
				"what-if result scaled by the API worker; Layer 5 did not solve it"
				if placeholder
				else "what-if result solved by alea.whatif.WhatIfEngine"
			),
			inputs=[base["network_checksum"], base["result_checksum"]],
			code_version=self.config.api.version,
		)
		return write_artefact(path, payload, provenance)


def _modelled(
	value: float, unit: str, note: str, *, uncertainty: float = PLACEHOLDER_UNCERTAINTY
) -> dict[str, Any]:
	"""A value payload stamped as modelled, with the uncertainty it actually has.

	The default is the placeholder band because that is what a scaled number
	deserves. A solved result passes its own uncertainty through, so the API
	does not widen a solved number's band to the placeholder's -- which would
	be a lie in the safe direction, and still a lie.
	"""
	return {
		"value": float(value),
		"unit": unit,
		"basis": Basis.MODELLED.value,
		"uncertainty": float(uncertainty),
		"source_id": "alea.whatif",
		"note": note,
	}


def _deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Each scenario's objective and capacity difference against the first.

	Only the two headline numbers. A per-carrier delta table is the report
	layer's job (Layer 6), and duplicating it here would give two places that
	disagree the first time one of them changes.
	"""
	base = rows[0]
	out: list[dict[str, Any]] = []
	for row in rows[1:]:
		out.append(
			{
				"scenario_id": row["scenario_id"],
				"objective_delta_usd": row["objective"]["value"] - base["objective"]["value"],
				"capacity_delta_mw": (
					row["total_capacity_mw"]["value"] - base["total_capacity_mw"]["value"]
				),
			}
		)
	return out


def _expansion_solver() -> Any:
	"""Layer 1's expansion as the engine's solve function.

	``WhatIfEngine``'s default is ``network.optimize()``, which is PyPSA's
	optimiser with PyPSA's defaults. Layer 1's is not that: it applies the
	configured solver, the solver options (single-threaded HiGHS, a seed, a
	time limit), the transmission-loss treatment and the multi-period
	structure. A what-if answer computed with different solver settings from
	the base scenario is not comparable to it, and the difference would show up
	as a scenario that "changed the answer" when only the solver did.

	Returns a callable because the engine takes one, and the config is loaded
	here rather than at import so the API package imports without a config.
	"""
	from alea.config.loader import load_config
	from alea.planning.expansion import solve_expansion

	config = load_config()

	def solve(network: Any, extra_functionality: Any = None) -> Any:
		# The hook is passed through to `solve_expansion`, which hands it to
		# `network.optimize`. Dropping it here would solve a constrained scenario
		# unconstrained while the cache key said otherwise -- and the answer would
		# look like a valid result for a build the graph had rejected.
		return solve_expansion(network, config, extra_functionality=extra_functionality)

	return solve


def _try_real_engine(
	request: WhatIfSolveRequest, base: dict[str, Any], network_path: Path
) -> dict[str, Any] | None:
	"""Solve through Layer 5's engine, or ``None`` when there is no base network.

	The base network is a file the catalogue publishes beside each scenario
	(``network.nc``). When it is absent there is nothing to re-solve and the
	caller falls back to scaling -- the one case where a placeholder is the
	honest answer.

	The previous version of this function imported ``solve_what_if`` from this
	module's own package, a symbol that has never existed. The ``ImportError``
	guard therefore caught a typo on every call and returned ``None``, so the
	real engine was unreachable and every what-if answer in the API was a scaled
	placeholder wearing a solved result's shape. The engine is a class,
	``WhatIfEngine``; the import below names it.
	"""
	from alea.whatif.cache import DEFAULT_CACHE_ROOT
	from alea.whatif.params import ScenarioParameters
	from alea.whatif.service import DEFAULT_CODE_VERSION, WhatIfEngine

	engine = WhatIfEngine(
		network_path,
		# `DEFAULT_CACHE_ROOT`, not `f"{WHATIF_DIR}/solves"`. The literal and the
		# constant agree today, and two spellings of one path is how `alea whatif
		# gc` comes to collect from a directory no engine writes: the command
		# removes nothing, prints "removed 0", and reads as a clean cache. The
		# two modules are asserted to share this constant by
		# `test_whatif_gc_cli.py`.
		cache_root=resolve(DEFAULT_CACHE_ROOT),
		solve_fn=_expansion_solver(),
		code_version=str(base.get("code_version") or "") or DEFAULT_CODE_VERSION,
	)
	params = request.parameters.to_engine()
	assert isinstance(params, ScenarioParameters)

	# ``solve_expansion`` calls ``network.optimize`` on the network it is handed,
	# so the engine is given a copy: a solve that mutated the base network would
	# make every later scenario in the same worker depend on the order they ran.
	outcome = engine.solve_with_outcome(params.copy(deep=True))
	result = outcome.result
	logger.info(
		"whatif.engine.solved",
		scenario_id=request.base_scenario_id,
		cache_key=outcome.cache_key[:12],
		from_cache=outcome.from_cache,
		seconds=round(outcome.solve_seconds, 3),
	)

	capacity = result.capacity_mix_mw
	total = math.fsum(capacity.values())
	note = (
		"solved by alea.whatif.WhatIfEngine: parameters applied to the base "
		"network, re-solved through Layer 1's expansion"
	)
	return {
		"job_id": "",
		"scenario_id": request.base_scenario_id,
		"name": request.name or f"{request.base_scenario_id} +{outcome.cache_key[:8]}",
		"objective": _modelled(result.total_cost_usd, "USD", note, uncertainty=result.uncertainty),
		"total_capacity_mw": _modelled(total, "MW", note, uncertainty=result.uncertainty),
		"capacity_mix": [
			{
				"carrier": carrier,
				"capacity_mw": _modelled(mw, "MW", note, uncertainty=result.uncertainty),
				"share": _modelled(
					mw / total if total else 0.0, "fraction", note, uncertainty=result.uncertainty
				),
			}
			for carrier, mw in sorted(capacity.items())
		],
		"emissions": _modelled(
			result.total_emissions_tco2, "tCO2", note, uncertainty=result.uncertainty
		),
		"parameters": params.model_dump(mode="json"),
		"network_checksum": result.network_checksum,
		"result_checksum": "",
		"cache_key": outcome.cache_key,
		"from_cache": outcome.from_cache,
		"renewable_share": result.renewable_share,
		"placeholder": False,
	}


__all__ = [
	"PLACEHOLDER_UNCERTAINTY",
	"WHATIF_DIR",
	"WhatIfService",
	"solve_cache_key",
]
