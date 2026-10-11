# SPDX-License-Identifier: MIT
"""Layer 4b — loss decomposition, DC flow, N-1 contingency and TLENS.

See ``docs/plans/07-layer4-predictive.md`` §6-7. The package fixes two
specification defects: the hardcoded-zero ``_topology_driven`` placeholder
(the components must sum to the total) and the single-snapshot mitigation
payback (savings are summed over the actual hourly series).

``import alea.losses`` succeeds without the compiled kernels loaded; the flow,
contingency and decomposition submodules import them lazily so a caller that
only needs the models pays nothing.
"""

from __future__ import annotations

from alea.losses.views import (
	DECOMPOSITION_TOLERANCE,
	ContingencySummary,
	FlowResult,
	LossComponents,
	LossConfig,
	MitigationOption,
	MitigationResult,
	TlensEntry,
	TlensRanking,
)

__all__ = [
	"DECOMPOSITION_TOLERANCE",
	"ContingencySummary",
	"FlowResult",
	"LossComponents",
	"LossConfig",
	"MitigationOption",
	"MitigationResult",
	"TlensEntry",
	"TlensRanking",
]


def __getattr__(name: str):
	"""Lazy submodule access, so importing the models does not pull the kernels."""
	import importlib

	_lazy = {
		"flow": "alea.losses.flow",
		"decompose": "alea.losses.decompose",
		"contingency": "alea.losses.contingency",
		"mitigation": "alea.losses.mitigation",
		"service": "alea.losses.service",
	}
	if name in _lazy:
		return importlib.import_module(_lazy[name])
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
