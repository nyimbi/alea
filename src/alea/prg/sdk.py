# SPDX-License-Identifier: MIT
"""A client for the PRG service, for callers who are not the service.

The specification's §45 names a ``PRGClient`` and shows three calls. This is
that, plus the eleven endpoints the table in §43 also names, because a client
that covers a fifth of a service is a client whose users write the other four
fifths by hand -- and the hand-written part is where the auth header and the
error handling get spelled differently every time.

WHY THIS IS ASYNC AND NOT A THIN ``requests`` WRAPPER. The rest of the tree is
async, and the platform runs one event loop per worker: a synchronous client
would either block that loop or force every caller to reach for
``asyncio.to_thread`` around it. ``httpx.AsyncClient`` is already a dependency
of the scanning layer, so this adds no weight.

WHY IT DOES NOT IMPORT THE API'S VIEW MODELS. It returns the JSON the service
served, parsed. Importing ``alea.api.views`` here would make a client
installation depend on FastAPI and the whole application -- and would make a
response-model rename a breaking change for a client that never cared about
the model. The client is a transport; the payloads are documented by the
OpenAPI document the service publishes.

WHY THE PATHS ARE RELATIVE TO A BASE URL. The service is mounted under
``/api/v1`` in this tree and the specification writes ``/v1/prg/...``. Neither
is hard-coded: ``base_url`` carries whatever prefix the deployment uses, and
``PRG_PATH`` is appended to it, so the same client works against a local
``TestClient``-backed server and against a gateway that rewrites the prefix.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

#: Where the PRG routes live under a deployment's base URL.
PRG_PATH = "/prg"

#: The header the service authenticates on. Named here rather than spelled
#: inline at thirteen call sites, so a service that changes it changes one
#: line in the client.
API_KEY_HEADER = "X-API-Key"

DEFAULT_TIMEOUT_S = 30.0


class PrgClientError(RuntimeError):
	"""A call could not be completed, or was refused by the service.

	Carries ``status`` and ``detail`` when the service answered with an error
	body, because "the request failed" is not something a caller can act on and
	the service already said what was wrong -- a 422 names the parameters that
	are not in the graph, a 403 names the tier the route needs.
	"""

	def __init__(
		self,
		message: str,
		*,
		status: int | None = None,
		detail: str | None = None,
	) -> None:
		super().__init__(message)
		self.status = status
		self.detail = detail


class PRGClient:
	"""An async client for the Parameter Relationship Graph service.

	Thirteen methods, one per operation the specification's §43 table names.
	Every one returns the decoded JSON; nothing is re-modelled, so a caller
	reads the same field names the API documents.

	The client owns its ``httpx.AsyncClient`` unless one is injected, and
	:meth:`aclose` releases it. Use it as an async context manager, or call
	``aclose`` -- an unreleased pool is a leaked socket per client.
	"""

	def __init__(
		self,
		*,
		base_url: str | None = None,
		api_key: str | None = None,
		client: httpx.AsyncClient | None = None,
		timeout_s: float = DEFAULT_TIMEOUT_S,
	) -> None:
		resolved = base_url or os.environ.get("ALEA_PRG_BASE_URL", "")
		if not resolved:
			raise ValueError(
				"no base URL: pass base_url or set ALEA_PRG_BASE_URL. The PRG "
				"service is mounted wherever the deployment puts it, so the "
				"client cannot guess one."
			)
		self.base_url = resolved.rstrip("/")
		self.api_key = api_key if api_key is not None else os.environ.get("ALEA_API_KEY", "")
		self.timeout_s = timeout_s
		self._http = client
		self._owns_client = client is None

	# -- lifecycle ---------------------------------------------------------

	async def _client(self) -> httpx.AsyncClient:
		if self._http is None:
			self._http = httpx.AsyncClient(timeout=self.timeout_s)
		return self._http

	async def aclose(self) -> None:
		"""Release the connection pool, if this client owns one."""
		if self._http is not None and self._owns_client:
			await self._http.aclose()
			self._http = None

	async def __aenter__(self) -> PRGClient:
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.aclose()

	# -- transport ---------------------------------------------------------

	def _headers(self) -> dict[str, str]:
		"""The auth header, or an empty dict when no key is configured.

		Not an error here: the read routes are public, and a client that
		refused to construct without a key could not fetch the graph at all.
		The write routes answer 401 with the reason, which is the service's
		call to make and not the client's to pre-empt.
		"""
		return {API_KEY_HEADER: self.api_key} if self.api_key else {}

	def _url(self, path: str) -> str:
		return f"{self.base_url}{PRG_PATH}{path}"

	async def _request(
		self,
		method: str,
		path: str,
		*,
		params: dict[str, Any] | None = None,
		json: Any = None,
	) -> Any:
		"""One request, with the service's own error body carried through.

		The response is parsed before the status is checked, because the
		service answers its errors as JSON with a ``detail`` naming the cause
		and a bare ``raise_for_status`` would discard exactly that.

		Transport failures are wrapped too. A caller of this client should not
		have to import ``httpx`` to write ``except`` -- a refused connection, a
		timeout and a 422 are all "the call did not happen", and the only
		useful difference is what the message says. ``status`` stays ``None``
		for the ones that never reached the service, which is the distinction a
		caller retrying on 5xx needs and a caller retrying on a bad request
		must not make.
		"""
		client = await self._client()
		url = self._url(path)
		try:
			response = await client.request(
				method, url, params=params, json=json, headers=self._headers()
			)
		except httpx.HTTPError as exc:
			# ``status`` stays None: every HTTPError reachable here is raised by
			# the transport, before a response exists. ``raise_for_status`` is
			# never called -- the status is read from the response above -- so a
			# ``HTTPStatusError`` cannot arrive by this path.
			raise PrgClientError(
				f"{method} {url} could not be completed: "
				f"{type(exc).__name__}: {exc}",
				status=None,
			) from exc
		try:
			payload = response.json()
		except ValueError:
			# A gateway that answers 502 with an HTML page is the common case,
			# and "not JSON" says nothing about which call it was.
			raise PrgClientError(
				f"{method} {url} answered {response.status_code} with "
				f"{len(response.content)} bytes that are not JSON; first 120 "
				f"bytes: {response.content[:120]!r}",
				status=response.status_code,
			) from None
		if response.status_code >= 400:
			detail = payload.get("detail") if isinstance(payload, dict) else None
			raise PrgClientError(
				f"{method} {url} answered {response.status_code}: {detail or payload}",
				status=response.status_code,
				detail=str(detail) if detail is not None else None,
			)
		return payload

	async def _get(self, path: str, **params: Any) -> Any:
		# Drop unset filters rather than sending `?role=None`: the service
		# validates the value against a pattern, and a literal "None" is a 422
		# on a call the caller made correctly.
		return await self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

	async def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
		return await self._request("POST", path, json=body if body is not None else {})

	# -- the graph ---------------------------------------------------------

	async def get_graph(self) -> dict[str, Any]:
		"""Every parameter, every edge, every equation, and the registers."""
		return await self._get("/graph")

	async def export_graphml(self) -> str:
		"""The graph as GraphML, for a viewer.

		Returns text rather than parsed JSON: the whole point of this endpoint
		is a document another tool reads, and decoding it into Python objects
		here would throw away the thing the caller asked for.
		"""
		client = await self._client()
		response = await client.get(self._url("/graph/export"), headers=self._headers())
		if response.status_code >= 400:
			raise PrgClientError(
				f"GET /graph/export answered {response.status_code}",
				status=response.status_code,
			)
		return response.text

	async def list_parameters(
		self, *, category: str | None = None, role: str | None = None
	) -> list[dict[str, Any]]:
		"""Every parameter, optionally filtered by category or role."""
		return await self._get("/parameters", category=category, role=role)

	async def get_parameter(self, parameter_id: str) -> dict[str, Any]:
		"""One parameter node, with its couplings read from the equations."""
		return await self._get(f"/parameters/{parameter_id}")

	async def get_dependents(
		self, parameter_id: str, *, direct_only: bool = False
	) -> list[dict[str, Any]]:
		"""What a parameter moves, transitively, ordered by distance."""
		return await self._get(
			f"/parameters/{parameter_id}/dependents",
			direct_only="true" if direct_only else None,
		)

	async def list_equations(self, *, system: str | None = None) -> list[dict[str, Any]]:
		"""Every equation, rendered."""
		return await self._get("/equations", system=system)

	async def get_equation(self, equation_id: str) -> dict[str, Any]:
		"""One equation, with the system it belongs to."""
		return await self._get(f"/equations/{equation_id}")

	# -- the computations --------------------------------------------------

	async def check_consistency(
		self, parameters: dict[str, float] | None = None
	) -> dict[str, Any]:
		"""Whether a parameter set holds, after propagating the derived values.

		``consistent`` is the gate and ``violations`` the record: an
		``informational`` equation that fails is reported and does not make the
		set inconsistent, which is the distinction the service draws and a
		client that read ``violations`` as truth would lose.
		"""
		return await self._post("/consistency/check", {"set": parameters or {}})

	async def consistency_report(self) -> dict[str, Any]:
		"""The shipped default scenario, checked.

		Fetch this first: a caller who has it knows whether a violation it
		later sees came from its own parameters or was already there.
		"""
		return await self._get("/consistency/report")

	async def propagate(
		self,
		changes: dict[str, float],
		*,
		current_values: dict[str, float] | None = None,
	) -> dict[str, Any]:
		"""Apply ``changes`` and report every parameter that moved.

		``changed`` is the delta per parameter, not the new value -- a caller
		that added it to the old value would double-count.
		"""
		return await self._post(
			"/propagate", {"set": current_values or {}, "changes": changes}
		)

	async def detect_conflicts(
		self, parameters: dict[str, float] | None = None
	) -> dict[str, Any]:
		"""Why a parameter set is inconsistent, and what to move."""
		return await self._post("/conflicts", {"set": parameters or {}})

	async def resolve_conflicts(
		self, parameters: dict[str, float] | None = None, *, rank: int = 1
	) -> list[dict[str, Any]]:
		"""Apply the highest-ranked corrections, and report the set after each."""
		return await self._post(
			"/conflicts/resolve", {"set": parameters or {}, "rank": rank}
		)

	async def solve_feedback(
		self, parameters: dict[str, float] | None = None
	) -> dict[str, Any]:
		"""Solve every feedback loop, with the turns each one took."""
		return await self._post("/feedback/solve", {"set": parameters or {}})

	async def translate(
		self, parameters: dict[str, float] | None = None
	) -> dict[str, Any]:
		"""The engine knobs a scenario reaches, and what did not go.

		Read ``untranslated``: most of the graph's settable parameters reach no
		what-if knob, and a caller that read only ``parameters`` would believe
		the whole scenario reached the engine. ``deferred`` is the third case
		and not a second spelling of the first: a parameter a knob *does*
		carry, whose ratio this route could not form for want of a network.
		"""
		return await self._post("/translate", {"set": parameters or {}})


__all__ = ["API_KEY_HEADER", "PRG_PATH", "PRGClient", "PrgClientError"]
