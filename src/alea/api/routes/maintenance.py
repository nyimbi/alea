# SPDX-License-Identifier: MIT
"""Predictive maintenance.

Restricted tier, per the plan's endpoint table (11-layer8 §3.1). A failure
prediction for a named asset is an operational claim about a specific piece of
equipment; it is not public information, and it is not something a
public-tier key should be able to enumerate across a national fleet.

``failure_probability`` is a probability with its basis and uncertainty, like
every other value the API serves. The plan's own ``[UNVERIFIED]`` benchmark for
this layer (87% critical-failure detection, Nigeria) is not reproducible from
this endpoint until ``alea.outages`` publishes a validation artefact; the
prediction rows carry their model version so the benchmark can be attached to
the right model when it is measured.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from alea.api.deps import PaginationDep, RestrictedDep, StateDep
from alea.api.views import MaintenancePredictionRowOut, Page

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/predict", response_model=Page[MaintenancePredictionRowOut], summary="Failure predictions")
async def predict(
	state: StateDep,
	principal: RestrictedDep,
	page: PaginationDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
	asset_type: str | None = Query(default=None, min_length=1),
) -> Page[MaintenancePredictionRowOut]:
	"""Predicted failures, most probable first.

	A GET with scalar parameters, as every read route is.
	"""
	assert state is not None, "predict needs application state"
	rows = state.repository.maintenance_predictions(country=country, asset_type=asset_type)
	window = rows[page.offset : page.offset + page.limit]
	return Page[MaintenancePredictionRowOut](
		items=window, total=len(rows), limit=page.limit, offset=page.offset
	)
