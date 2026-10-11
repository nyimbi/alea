# SPDX-License-Identifier: MIT
"""Planning routes: scenarios and their solved results.

All three are GETs over the scenario catalogue and the solved results under it.
None of them takes a request body -- the plan's rule (11-layer8 §2.1) is
mechanical: a GET takes scalar query parameters and anything with a complex body
is a POST. A GET with a body is not cacheable, not linkable, and many clients
drop the body silently, so the endpoint looks like it works and returns the
wrong answer.

The scenario id is a path component and is validated as one in the repository
before it reaches the filesystem.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from alea.api.deps import PaginationDep, PublicKeyDep, StateDep
from alea.api.views import Page, ScenarioOut, ScenarioResultOut, ScenarioSummaryOut

router = APIRouter(prefix="/scenarios", tags=["planning"])


@router.get("", response_model=Page[ScenarioSummaryOut], summary="List scenarios")
async def list_scenarios(
	state: StateDep,
	principal: PublicKeyDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> Page[ScenarioSummaryOut]:
	"""Every scenario in the catalogue, newest first.

	An empty catalogue is an empty page, not a 404: no scenario having been
	built yet is a normal state of a young deployment.
	"""
	assert state is not None, "list_scenarios needs application state"
	scenarios = state.repository.scenarios()
	if country is not None:
		wanted = country.upper()
		scenarios = [s for s in scenarios if wanted in [c.upper() for c in s.countries]]
	window = scenarios[page.offset : page.offset + page.limit]
	return Page[ScenarioSummaryOut](
		items=window, total=len(scenarios), limit=page.limit, offset=page.offset
	)


@router.get("/{scenario_id}", response_model=ScenarioOut, summary="One scenario")
async def get_scenario(
	state: StateDep, principal: PublicKeyDep, scenario_id: str = Path(min_length=1)
) -> ScenarioOut:
	"""A scenario's parameters, the network it was solved against, and its provenance."""
	assert state is not None, "get_scenario needs application state"
	try:
		scenario = state.repository.scenario(scenario_id)
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
	if scenario is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"no scenario {scenario_id!r} in the catalogue",
		)
	return scenario


@router.get(
	"/{scenario_id}/results", response_model=ScenarioResultOut, summary="A scenario's solved result"
)
async def get_scenario_results(
	state: StateDep,
	principal: PublicKeyDep,
	scenario_id: str = Path(min_length=1),
	horizon: int = Query(ge=2000, le=2200, description="Planning horizon year."),
) -> ScenarioResultOut:
	"""The solved result at one horizon.

	``horizon`` is a query parameter rather than a body, and it is required: a
	default horizon would serve the wrong year's capacity mix to a caller who
	forgot to name one, and a capacity mix is a number people publish.
	"""
	assert state is not None, "get_scenario_results needs application state"
	try:
		result = state.repository.scenario_result(scenario_id, horizon)
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
	if result is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"scenario {scenario_id!r} has no solved result at {horizon}",
		)
	return result
