# SPDX-License-Identifier: MIT
"""Routers, one per endpoint group.

Each module exposes ``router: APIRouter`` and nothing else the application needs
to know about. ``alea.api.app`` mounts them; the route inventory test reads them
back off ``app.routes`` at runtime rather than from this source tree, because a
static read of the source is not a read of what the application serves.
"""

from __future__ import annotations

from fastapi import APIRouter

from alea.api.routes import (
	losses,
	maintenance,
	market,
	outages,
	planning,
	prg,
	reports,
	resilience,
	signals,
	system,
	topology,
	whatif,
)

# Every module in this package must appear here. A router that exists but is
# never mounted is a capability nobody can reach, and nothing fails when it goes
# missing: the module imports, its tests (if they call it directly) pass, and the
# endpoint is simply absent from the application. That is the shape of the defect
# the plan's criterion 9 records, one level up from the route walk.
ROUTERS: tuple[APIRouter, ...] = (
	system.router,
	topology.router,
	planning.router,
	market.router,
	outages.router,
	losses.router,
	maintenance.router,
	resilience.router,
	whatif.router,
	reports.router,
	signals.router,
	prg.router,
)

__all__ = ["ROUTERS"]
