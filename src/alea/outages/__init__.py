# SPDX-License-Identifier: MIT
"""Layer 4a — predictive operations.

VIIRS nighttime-lights outage detection, weather-driven outage forecasting,
predictive maintenance, ensemble combination, and ground-truth validation. See
``docs/plans/07-layer4-predictive.md``.

The package fixes three specification defects in the detection path
(cloud-flag polarity, cloud-as-unknown, the gap-filled band), two in the
forecasting path (hemisphere-free season encoding, temporal leakage), and two
in the maintenance path (the DGA availability guard, post-hoc feature leakage).
Each is documented where it lives and each has a gate in the plan's §10 table.

Heavy imports are deferred: ``import alea.outages`` must succeed without
lightgbm, lifelines or sklearn present, so a caller that only needs the models
pays nothing for them.
"""

from __future__ import annotations

from alea.outages.views import (
	DetectionMetrics,
	EnsembleConfig,
	EnsembleResult,
	ForecastMetrics,
	MaintenanceConfig,
	MaintenanceFit,
	PredictiveConfig,
	ValidationOutcome,
	ViirsConfig,
	WeatherConfig,
)

__all__ = [
	"DetectionMetrics",
	"EnsembleConfig",
	"EnsembleResult",
	"ForecastMetrics",
	"MaintenanceConfig",
	"MaintenanceFit",
	"PredictiveConfig",
	"ValidationOutcome",
	"ViirsConfig",
	"WeatherConfig",
]


def __getattr__(name: str):
	"""Lazy submodule access.

	``alea.outages.viirs`` needs numpy and the compiled kernels;
	``alea.outages.weather`` needs pandas and a gradient-boosting backend. A
	caller importing the package for its models should not need either, and a
	missing optional backend should fail at the call site that needs it rather
	than at package import.
	"""
	import importlib

	_lazy = {
		"viirs": "alea.outages.viirs",
		"weather": "alea.outages.weather",
		"maintenance": "alea.outages.maintenance",
		"ensemble": "alea.outages.ensemble",
		"validate": "alea.outages.validate",
		"service": "alea.outages.service",
	}
	if name in _lazy:
		return importlib.import_module(_lazy[name])
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
