# SPDX-License-Identifier: MIT
"""Configuration.

The re-exports are **lazy**, which is not a style choice. ``alea.config.models``
composes the layer models and therefore imports ``alea.outages.views`` for the
``predictive`` section, while ``alea.outages.views`` imports
``alea.config.base``. An eager import here puts ``alea.config.loader`` ->
``alea.config.models`` -> ``alea.outages.views`` on the path of *every*
``import alea.config.something``, including the one that starts inside
``outages.views`` -- and that ordering raises ``ImportError: cannot import name
'PredictiveConfig' from partially initialized module``. A package that imports
cleanly from one entry point and not another is a package whose import graph is
load-bearing, so the eager re-export is removed rather than ordered carefully.

``from alea.config import Config`` still works (PEP 562); ``from
alea.config.models import Config`` was already how every module in this project
imports it.
"""

from __future__ import annotations

from typing import Any

_LAZY = {
	"AleaConfig": "alea.config.base",
	"ConfigError": "alea.config.loader",
	"deep_merge": "alea.config.loader",
	"load_config": "alea.config.loader",
	"parse_override": "alea.config.loader",
	"ApiConfig": "alea.config.models",
	"Config": "alea.config.models",
	"CostsConfig": "alea.config.models",
	"LoggingConfig": "alea.config.models",
	"MarketConfig": "alea.config.models",
	"PathsConfig": "alea.config.models",
	"PredictiveConfig": "alea.config.models",
	"RenewableConfig": "alea.config.models",
	"ReportingConfig": "alea.config.models",
	"ScenarioConfig": "alea.config.models",
	"ScanningConfig": "alea.config.models",
	"SectorConfig": "alea.config.models",
	"SolveConfig": "alea.config.models",
	"config_dir": "alea.config.paths",
	"repo_root": "alea.config.paths",
	"resolve": "alea.config.paths",
	"scenario_path": "alea.config.paths",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
	"""Resolve a re-export on first use, not at package import."""
	module_name = _LAZY.get(name)
	if module_name is None:
		raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
	import importlib

	value = getattr(importlib.import_module(module_name), name)
	globals()[name] = value
	return value


def __dir__() -> list[str]:
	return __all__
