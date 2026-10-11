# SPDX-License-Identifier: MIT
"""The route inventory, read from the running application.

Exit criterion 9 of Layer 8 (11-layer8 §9) has a specific history: an inventory
of routes read from source is not an inventory of routes the app serves. A
wrapper class around ``include_router`` once hid 1,074 of 1,080 routes from a
static extractor, and three different wrong counts were each internally
consistent.

**That wrapper is live here.** FastAPI 0.143 wraps an included router in an
``_IncludedRouter`` whose ``path`` is ``None`` and whose real routes live on
``original_router.routes`` under ``include_context.prefix``. Walking
``app.routes`` and reading ``.path`` off each entry yields the wrapper, not the
routes, so a naive inventory undercounts by everything the routers carry -- and
the count it reports is internally consistent and wrong.

This module unwraps that. :func:`route_inventory` is the only supported way to
enumerate what the application serves, and :func:`assert_inventory` canaries it
against a route known to exist before trusting the total.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType

from fastapi import FastAPI
from starlette.routing import Route

KNOWN_ROUTE = ("GET", "/api/v1/health")
"""A route that must always exist. The inventory is canaried against it."""


@dataclass(frozen=True)
class RouteInfo:
	"""One served route."""

	path: str
	methods: tuple[str, ...]
	name: str

	@property
	def key(self) -> tuple[str, str]:
		"""``(method, path)`` for the first method, for a quick lookup."""
		return (self.methods[0] if self.methods else "", self.path)


def route_inventory(app: FastAPI) -> list[RouteInfo]:
	"""Every route the application serves, wrapper unwrapped.

	Descends into an ``_IncludedRouter`` by reading ``original_router`` and
	prefixing with ``include_context.prefix``. The unwrap is duck-typed rather
	than an ``isinstance`` on a private class: the wrapper is a FastAPI internal
	and its name has already changed once, but the two attributes it exposes are
	what the descent needs.
	"""
	assert app is not None, "route_inventory called with no application"
	found: list[RouteInfo] = []
	for entry in app.routes:
		found.extend(_walk(entry, prefix=""))
	return found


def _walk(entry: object, prefix: str) -> list[RouteInfo]:
	"""One route entry, or every route under a wrapper."""
	original = getattr(entry, "original_router", None)
	if original is not None:
		context = getattr(entry, "include_context", None)
		inner_prefix = getattr(context, "prefix", "") or ""
		out: list[RouteInfo] = []
		for inner in getattr(original, "routes", []):
			out.extend(_walk(inner, prefix=f"{prefix}{inner_prefix}"))
		return out

	if isinstance(entry, Route):
		methods = tuple(sorted(getattr(entry, "methods", None) or ()))
		return [
			RouteInfo(
				path=f"{prefix}{entry.path}",
				methods=methods,
				name=getattr(entry, "name", "") or "",
			)
		]
	return []


def route_paths(app: FastAPI) -> set[str]:
	"""The set of served paths, for the route-inventory test."""
	return {route.path for route in route_inventory(app)}


def _mounted_modules() -> set[str]:
	"""The route modules ``alea.api.routes`` actually exposes."""
	import alea.api.routes as package

	return {name for _, name, _ in pkgutil.iter_modules(package.__path__)}


def assert_every_router_mounted(app: FastAPI, *, prefix: str) -> None:
	"""Check that every route module in the package reaches the application.

	The route walk sees what the application serves; this sees what the package
	offers, and the two sets are what has to agree. Without it a new
	``routes/<name>.py`` that nobody added to ``ROUTERS`` is invisible: nothing
	imports it, nothing fails, and the endpoint exists only in the source tree.

	Each router's own paths are compared against the served paths with the
	application prefix removed, rather than against the prefixed paths, so a
	router that is mounted under a different prefix is still checked for the
	routes it carries.
	"""
	assert app is not None, "assert_every_router_mounted called with no application"
	assert prefix, "the application prefix is needed to compare router paths"
	from alea.api.routes import ROUTERS

	served = {
		path[len(prefix):] if path.startswith(prefix) else path
		for path in route_paths(app)
	}
	unmounted: list[str] = []
	for name in sorted(_mounted_modules()):
		module: ModuleType = importlib.import_module(f"alea.api.routes.{name}")
		router = getattr(module, "router", None)
		if router is None:
			continue
		if router not in ROUTERS:
			unmounted.append(f"{name} (module is not in ROUTERS)")
			continue
		# A module can be in ROUTERS and still contribute nothing, if its own
		# router is empty -- which reads as mounted and is not.
		for route in getattr(router, "routes", []):
			path = getattr(route, "path", None)
			if path and path not in served:
				unmounted.append(f"{name} ({path})")
	if unmounted:
		raise AssertionError(
			f"route modules that do not reach the application: {unmounted}; "
			f"add them to ROUTERS in alea/api/routes/__init__.py"
		)


def assert_inventory(app: FastAPI, *, minimum: int = 30) -> list[RouteInfo]:
	"""Canary the inventory against a known route, then check the total.

	A count read off an inventory that was never pointed at a route known to
	exist is a count with nothing behind it. The canary runs first: if the
	unwrap breaks, this raises before the total is trusted.
	"""
	assert app is not None, "assert_inventory called with no application"
	inventory = route_inventory(app)
	paths = {(method, route.path) for route in inventory for method in route.methods}
	if KNOWN_ROUTE not in paths:
		raise AssertionError(
			f"the inventory does not see {KNOWN_ROUTE[0]} {KNOWN_ROUTE[1]}, which the "
			f"application serves; the route walk is broken and its total is meaningless "
			f"(it reported {len(inventory)} routes)"
		)
	if len(inventory) < minimum:
		raise AssertionError(
			f"the inventory reports {len(inventory)} routes, below the expected "
			f"minimum of {minimum}; the router set is incomplete"
		)
	return inventory


__all__ = [
	"KNOWN_ROUTE",
	"RouteInfo",
	"assert_every_router_mounted",
	"assert_inventory",
	"route_inventory",
	"route_paths",
]
