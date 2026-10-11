# SPDX-License-Identifier: MIT
"""The Rust boundary.

This package is the only place in ALEA that touches the compiled extension
(AD-2). `alea._core._rust` is the raw PyO3 module; `alea._core.kernels` is the
wrapper layer every other module imports.
"""

from alea._core.kernels import (
	KernelError,
	KernelInputError,
	aggregate,
	aggregate_to_zones,
	available,
	block_sum,
	branch_flows,
	cholesky,
	contingency_sweep,
	correlation_from_covariance,
	dc_power_flow,
	decompose_losses,
	deduplicate,
	detect_outages,
	exceedance_probability,
	jaccard_estimate,
	load_duration_curve,
	minhash,
	normalise_weights,
	optimal_bands_rows,
	portfolio_returns,
	transmission_losses,
	validate_aggregation,
	var_cvar,
	vza_baseline,
)

__all__ = [
	"KernelError",
	"KernelInputError",
	"aggregate",
	"aggregate_to_zones",
	"available",
	"block_sum",
	"branch_flows",
	"cholesky",
	"contingency_sweep",
	"correlation_from_covariance",
	"dc_power_flow",
	"decompose_losses",
	"deduplicate",
	"detect_outages",
	"exceedance_probability",
	"jaccard_estimate",
	"load_duration_curve",
	"minhash",
	"normalise_weights",
	"optimal_bands_rows",
	"portfolio_returns",
	"transmission_losses",
	"validate_aggregation",
	"var_cvar",
	"vza_baseline",
]
