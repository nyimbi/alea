# SPDX-License-Identifier: MIT
"""Portfolio risk: VaR, CVaR, and correlated Monte Carlo.

Two hazards, both of which produce a plausible number rather than an error, are
handled explicitly (03-rust-core §7.2):

* **Sign convention.** VaR and CVaR are reported as **positive loss
  magnitudes**. A negative VaR quoted as a loss flips the meaning of every
  number downstream, so the kernel guarantees ``CVaR >= VaR >= 0`` and the
  ``RiskResult`` model enforces it. A test asserts the ordering.
* **Cholesky must be checked.** A correlation matrix that is not
  positive-definite — easy to assemble from expert elicitation — makes Cholesky
  fail. The Rust kernel raises and names the failing pivot, rather than
  producing NaNs that propagate silently into a VaR. This module calls that
  kernel; it does not re-implement a Cholesky that would not be checked.

The Monte Carlo is a Cholesky-correlated draw over the *inputs* (fuel price,
demand, carbon price), passed through a caller-supplied model to a P&L, and the
resulting loss distribution is summarised by the same ``var_cvar`` kernel.
Deterministic given a seed (AD-8).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from alea._core import (
	cholesky,
	correlation_from_covariance,
	exceedance_probability,
	portfolio_returns,
	var_cvar,
)
from alea.logging import get_logger
from alea.market.views import RiskResult

logger = get_logger(__name__)

Model = Callable[[NDArray[np.float64]], NDArray[np.float64]]
"""Maps a draw of standardised input shocks ``[n_inputs]`` to a P&L vector
``[n_outputs]``. The risk layer knows nothing about the model."""


def value_at_risk(returns: NDArray[np.float64], confidence: float = 0.95) -> RiskResult:
	"""VaR and CVaR from a sample of *returns*, as positive loss magnitudes.

	``returns`` is a P&L or return series where a loss is negative. The kernel
	computes the alpha-quantile magnitude and the mean of the tail at or below
	it.
	"""
	sample = np.asarray(returns, dtype=np.float64)
	assert sample.ndim == 1, f"returns must be one-dimensional, got {sample.shape}"
	assert 0.0 < confidence < 1.0, f"confidence must be in (0, 1), got {confidence}"

	value, conditional = var_cvar(sample, confidence)
	result = RiskResult(
		confidence=confidence,
		value_at_risk_usd=abs(float(value)),
		conditional_value_at_risk_usd=abs(float(conditional)),
		expected_shortfall_usd=abs(float(conditional)),
		n_paths=int(sample.size),
	)
	logger.info(
		"value_at_risk",
		confidence=confidence,
		var=round(result.value_at_risk_usd, 4),
		cvar=round(result.conditional_value_at_risk_usd, 4),
		n_paths=result.n_paths,
	)
	return result


def exceedance(returns: NDArray[np.float64], threshold: float) -> float:
	"""Empirical probability that a loss exceeds ``threshold``.

	``threshold`` is a loss magnitude, so it is negated before the kernel, which
	counts returns at or below it.
	"""
	sample = np.asarray(returns, dtype=np.float64)
	assert sample.ndim == 1, "returns must be one-dimensional"
	return exceedance_probability(sample, -abs(float(threshold)))


def checked_cholesky(correlation: NDArray[np.float64]) -> NDArray[np.float64]:
	"""Lower-triangular Cholesky factor of a correlation matrix, checked.

	The kernel raises on a non-positive-definite matrix rather than returning
	NaNs. That is the whole reason this is a wrapper and not an inline call: an
	unchecked Cholesky is the failure mode the plan calls out, and a correlation
	matrix from expert elicitation is frequently not positive-definite.
	"""
	matrix = np.asarray(correlation, dtype=np.float64)
	assert matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1], (
		f"correlation must be square, got {matrix.shape}"
	)
	assert np.allclose(matrix, matrix.T, atol=1e-9), "correlation matrix must be symmetric"
	factor = cholesky(matrix)
	logger.info("checked_cholesky", n_inputs=matrix.shape[0])
	return factor


def correlated_shocks(
	factor: NDArray[np.float64],
	n_paths: int,
	*,
	seed: int = 0,
) -> NDArray[np.float64]:
	"""Standardised correlated draws ``[n_paths, n_inputs]``.

	Deterministic given ``seed``: the same seed produces identical paths in this
	process and another (AD-8). The RNG is a numpy ``Generator`` seeded
	explicitly, never the global state.
	"""
	factor = np.asarray(factor, dtype=np.float64)
	assert factor.ndim == 2 and factor.shape[0] == factor.shape[1], "factor must be square"
	assert n_paths > 0, "n_paths must be positive"
	n_inputs = factor.shape[0]
	rng = np.random.default_rng(seed)
	independent = rng.standard_normal((n_paths, n_inputs))
	return independent @ factor.T


def monte_carlo_risk(
	means: NDArray[np.float64],
	stds: NDArray[np.float64],
	correlation: NDArray[np.float64],
	model: Model,
	*,
	n_paths: int = 100_000,
	seed: int = 0,
	confidence: float = 0.95,
) -> RiskResult:
	"""VaR and CVaR of a model's P&L over correlated input draws.

	``means`` and ``stds`` describe the inputs (e.g. fuel price, demand, carbon
	price); ``correlation`` is their correlation matrix, checked for
	positive-definiteness before any draw. ``model`` maps a standardised shock
	vector to a P&L; the P&L is negated to a *loss* series before the kernel, so
	the returned magnitudes are losses.

	Because the model is called once per path, keep it vectorised or cheap: at
	10^5 paths the Python overhead of a non-vectorised model dominates.
	"""
	mean = np.asarray(means, dtype=np.float64)
	std = np.asarray(stds, dtype=np.float64)
	assert mean.shape == std.shape, f"means {mean.shape} and stds {std.shape} must align"
	assert np.all(std >= 0.0), "standard deviations cannot be negative"

	factor = checked_cholesky(correlation)
	shocks = correlated_shocks(factor, n_paths, seed=seed)
	draws = mean + shocks * std

	pnl = np.empty(n_paths, dtype=np.float64)
	for path in range(n_paths):
		pnl[path] = float(np.asarray(model(draws[path])).ravel()[0])

	losses = -pnl
	result = value_at_risk(losses, confidence)
	logger.info("monte_carlo_risk", n_paths=n_paths, seed=seed, cvar=round(result.conditional_value_at_risk_usd, 4))
	return result


def portfolio_risk(
	returns: NDArray[np.float64],
	weights: NDArray[np.float64],
	*,
	confidence: float = 0.95,
) -> RiskResult:
	"""VaR and CVaR of a weighted portfolio of per-asset return series.

	``returns`` is ``[n_periods, n_assets]``; ``weights`` is ``[n_assets]``. The
	portfolio series is formed by the ``portfolio_returns`` kernel, which does
	not normalise weights (an under-invested portfolio is a real portfolio), and
	the risk is measured on that series.
	"""
	matrix = np.asarray(returns, dtype=np.float64)
	weight = np.asarray(weights, dtype=np.float64)
	assert matrix.ndim == 2, f"returns must be two-dimensional, got {matrix.shape}"
	assert weight.shape == (matrix.shape[1],), (
		f"weights {weight.shape} must match {matrix.shape[1]} assets"
	)
	series = portfolio_returns(matrix, weight)
	result = value_at_risk(series, confidence)
	logger.info("portfolio_risk", assets=matrix.shape[1], n_paths=result.n_paths)
	return result


def correlation_matrix(
	covariance: NDArray[np.float64],
	stds: NDArray[np.float64],
) -> NDArray[np.float64]:
	"""Correlation matrix from a covariance matrix and standard deviations."""
	cov = np.asarray(covariance, dtype=np.float64)
	std = np.asarray(stds, dtype=np.float64)
	assert cov.ndim == 2 and cov.shape[0] == cov.shape[1], "covariance must be square"
	assert std.shape == (cov.shape[0],), "stds must match the covariance dimension"
	return correlation_from_covariance(cov, std)


def normal_var_check(sigma: float, confidence: float = 0.95) -> float:
	"""The analytic normal VaR magnitude at a confidence, for a cross-check.

	For a zero-mean normal, VaR at 95% is ``1.6449 * sigma``. Provided so a test
	can compare a large-sample Monte Carlo against a closed form rather than
	against itself.
	"""
	from scipy.stats import norm

	assert sigma >= 0.0, "sigma cannot be negative"
	return float(norm.ppf(confidence) * sigma)


__all__ = [
	"Model",
	"checked_cholesky",
	"correlated_shocks",
	"correlation_matrix",
	"exceedance",
	"monte_carlo_risk",
	"normal_var_check",
	"portfolio_risk",
	"value_at_risk",
]
