# SPDX-License-Identifier: MIT
"""The transmission network, as one GeoJSON-shaped payload.

This route is not in the specification's endpoint table. It is in the plan's
adapter table (11-layer8 §5): the QGIS plugin is listed as "Adapter over
`/topology`", and §6 gives topology its own cache lifetime -- one day, because
the network changes on a rebuild rather than on a clock. A lifetime declared for
a route that does not exist is a config field read by nothing, which is how the
other four lifetimes in that table started.

**Not paginated**, unlike every other collection route. The adapter draws the
network as one layer, and a paginated geometry is a partially drawn grid: a
client that renders page one shows a connected-looking network with its
interconnectors missing, and nothing in the response says so. The line count
travels with the payload so a client can refuse one too large for it rather
than truncating one it cannot tell is truncated.

**Public tier.** The lines are the World Bank's published existing-and-planned
grid map; there is nothing here that is not already on a public GIS server. What
the route adds is the network's *identity* -- its checksum -- so a plugin
drawing these lines and a solve running on them can be shown to be the same
artefact rather than two files that happen to agree today.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from alea.api.cache import read_through
from alea.api.deps import PublicKeyDep, StateDep
from alea.api.views import TopologyOut

router = APIRouter(prefix="/topology", tags=["planning"])


@router.get("", response_model=TopologyOut, summary="Transmission network")
async def topology(
	state: StateDep,
	principal: PublicKeyDep,
	country: str | None = Query(default=None, min_length=2, max_length=2),
) -> TopologyOut:
	"""Every transmission line, with the extent they cover.

	A 404 rather than an empty network when the artefact is absent: an empty
	FeatureCollection is a valid answer to "what lines are there" and a wrong
	one to "has the network been built", and a GIS cannot tell them apart.
	"""
	assert state is not None, "topology needs application state"
	network = state.repository.topology(country=country)
	if network is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="no topology artefact has been built; run `alea build topology` first",
		)

	# Read through the cache so §6's day-long lifetime for topology is applied by
	# the route that declares it. The key carries the artefact checksum, so a
	# rebuilt network is a new key rather than a stale entry.
	cached = await read_through(
		state,
		namespace="planning.topology",
		checksum=network.checksum,
		params={"country": country.upper() if country else None},
		ttl_seconds=state.config.api.cache_ttl_topology_seconds,
		producer=lambda: _produce(state, country),
		from_payload=TopologyOut.model_validate,
	)
	# The producer returns the network it read; on a hit the payload is rebuilt
	# from the cached document. Either way there is exactly one.
	assert len(cached) == 1, f"a topology response is one object, got {len(cached)}"
	return cached[0]


async def _produce(state, country: str | None) -> list[TopologyOut]:
	assert state is not None, "a producer needs application state"
	network = state.repository.topology(country=country)
	if network is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="the topology artefact disappeared between the check and the read",
		)
	return [network]


__all__ = ["router"]
