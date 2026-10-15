# SPDX-License-Identifier: MIT
"""Layer 5 — the what-if scenario engine.

Parameter-driven re-solve, content-addressed caching, and efficient frontiers.
The engine owns no physics: every solve calls Layer 1/2, every price calls
Layer 3's market model, every risk metric calls Layer 3's risk kernel. What it
owns is the thing that makes a scenario engine trustworthy — a cache key that
is a function of the scenario's content, so a restart does not silently
re-solve everything, and a frontier that reports cost and risk together, so a
reader cannot mistake a cost curve for an answer to the investment question.

Two defects in the specification are corrected here rather than reproduced:

* the cache key is a sha256 of the canonical parameters, network checksum, and
  code version, never ``hash()`` of a tuple (randomised per interpreter);
* ``renewable_share`` is ``None`` on zero generation, never ``0``.
"""

from __future__ import annotations

from alea.whatif.apply import apply_parameters
from alea.whatif.cache import (
	CACHE_VERSION,
	SolveCache,
	cache_key,
	key_is_process_stable,
	solve_fingerprint,
)
from alea.whatif.extract import extract
from alea.whatif.outage import (
	LineOutage,
	OutageError,
	OutageSet,
	apply_outages,
	islands_without_generation,
	outage_mask,
)
from alea.whatif.params import ScenarioParameters
from alea.whatif.pricemodel import DEFAULT_PRICE_PATHS, price_model_from_network
from alea.whatif.service import DEFAULT_CODE_VERSION, PrgSolve, WhatIfEngine
from alea.whatif.store import (
	ScenarioStoreError,
	latest_version,
	list_scenarios,
	load_scenario,
	save_scenario,
	scenario_dir,
)
from alea.whatif.sweep import (
	FRONTIER_COLUMNS,
	FRONTIER_VALUE_COLUMNS,
	cost_risk_frontier,
	efficient_frontier,
	frontier_points,
	sweep_parameter,
)
from alea.whatif.views import (
	FrontierPoint,
	RiskMetrics,
	ScenarioRecord,
	ScenarioResult,
	SolveOutcome,
	renewable_share,
)

__all__ = [
	"CACHE_VERSION",
	"DEFAULT_CODE_VERSION",
	"FRONTIER_COLUMNS",
	"FRONTIER_VALUE_COLUMNS",
	"FrontierPoint",
	"LineOutage",
	"OutageError",
	"OutageSet",
	"PrgSolve",
	"RiskMetrics",
	"ScenarioParameters",
	"ScenarioRecord",
	"ScenarioResult",
	"ScenarioStoreError",
	"SolveCache",
	"SolveOutcome",
	"WhatIfEngine",
	"apply_parameters",
	"apply_outages",
	"cache_key",
	"cost_risk_frontier",
	"efficient_frontier",
	"DEFAULT_PRICE_PATHS",
	"extract",
	"price_model_from_network",
	"frontier_points",
	"key_is_process_stable",
	"latest_version",
	"list_scenarios",
	"load_scenario",
	"renewable_share",
	"save_scenario",
	"scenario_dir",
	"solve_fingerprint",
	"sweep_parameter",
	"islands_without_generation",
	"outage_mask",
]
