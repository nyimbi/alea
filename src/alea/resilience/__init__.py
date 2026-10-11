# SPDX-License-Identifier: MIT
"""Layer 4c — resilience metrics.

ENS, EENS, SAIDI, SAIFI and LNS. The customer denominator is a WorldPop proxy
and the interruption threshold is config; both travel with every index so a
proxy-derived SAIDI cannot be read as a utility's own (07-layer4 §8, AD-6).
"""

from __future__ import annotations

from alea.resilience.views import (
	DEFAULT_INTERRUPTION_THRESHOLD_MINUTES,
	EensResult,
	InterruptionEvent,
	ResilienceConfig,
	ResilienceMetrics,
	ScenarioEns,
	ZoneCustomers,
)

__all__ = [
	"DEFAULT_INTERRUPTION_THRESHOLD_MINUTES",
	"EensResult",
	"InterruptionEvent",
	"ResilienceConfig",
	"ResilienceMetrics",
	"ScenarioEns",
	"ZoneCustomers",
]


def __getattr__(name: str):
	"""Lazy submodule access."""
	import importlib

	_lazy = {"metrics": "alea.resilience.metrics", "service": "alea.resilience.service"}
	if name in _lazy:
		return importlib.import_module(_lazy[name])
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
