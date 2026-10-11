# SPDX-License-Identifier: MIT
"""Reference implementation of the risk kernels (VaR/CVaR, portfolio risk).

Written from `alea._core.kernels` and `docs/plans/03-rust-core.md` §7. Not
production code.

Pinned semantics encoded here, and why:

* **VaR and CVaR are positive loss magnitudes.** The plan's §7.2 calls the sign
  convention the most common source of error in risk reporting. Losses are
  `-returns`; VaR is the loss at the tail index and CVaR the mean of the
  losses at or beyond it.
* **The tail count is `floor(n * (1 - confidence)) + 1`, clamped to `[1, n]`,
  and both VaR and CVaR come from that tail.** The count is the number of
  exceedances the confidence level implies, plus the boundary point itself;
  computing it in floating point (rather than with an integer `ceil`) is what
  makes `n=8, confidence=0.5` give a tail of 5 and not 4. VaR is the largest
  tail loss and CVaR the mean of the tail. The reference does not clamp VaR to
  be non-negative — a sample whose worst cases are gains has a negative VaR,
  and inventing a floor would hide that.
* **Cholesky is lower-triangular** and refuses a matrix that is not positive
  definite, naming the failing pivot.
* **`exceedance_probability` compares in loss magnitude and is strict.** The
  threshold is taken as `abs(threshold)`, so a loss of 3 exceeds a threshold of
  both +3 and -3; the comparison is `loss > threshold`, so a loss exactly at
  the threshold does not count.
* **`correlation_from_covariance` divides by the supplied standard deviations**,
  so the caller controls them; a zero standard deviation is refused.
* **Weights are not normalised** in `portfolio_returns`: a portfolio that is
  not fully invested is a real portfolio.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray


def var_cvar(returns: NDArray[np.float64], confidence: float = 0.95) -> tuple[float, float]:
	"""Value-at-Risk and Conditional VaR as positive loss magnitudes.

	Losses are `-returns`. The tail is the `floor(n * (1 - confidence)) + 1`
	largest losses; VaR is the largest of those and CVaR their mean.
	"""
	returns = np.asarray(returns, dtype=np.float64)
	n = returns.shape[0]
	if n == 0:
		raise ValueError("var_cvar: empty sample")
	if not 0.0 < confidence < 1.0:
		raise ValueError("var_cvar: confidence must be in (0, 1)")
	losses = sorted((-float(r) for r in returns), reverse=True)
	tail_count = int(math.floor(n * (1.0 - confidence))) + 1
	tail_count = max(1, min(tail_count, n))
	tail = losses[:tail_count]
	var = tail[-1]
	cvar = sum(tail) / len(tail)
	return float(var), float(cvar)


def cholesky(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
	"""The lower-triangular Cholesky factor.

	Raises `ValueError` naming the failing pivot when the matrix is not
	positive definite.
	"""
	matrix = np.asarray(matrix, dtype=np.float64)
	n = matrix.shape[0]
	lower = np.zeros((n, n), dtype=np.float64)
	for i in range(n):
		for j in range(i + 1):
			total = float(matrix[i, j])
			for k in range(j):
				total -= lower[i, k] * lower[j, k]
			if i == j:
				if total <= 0.0:
					raise ValueError(
						f"matrix is not positive-definite at pivot {i}; a correlation "
						"matrix built from expert elicitation often is not"
					)
				lower[i, j] = math.sqrt(total)
			else:
				lower[i, j] = total / lower[j, j]
	return lower


def correlation_from_covariance(
	covariance: NDArray[np.float64], stds: NDArray[np.float64]
) -> NDArray[np.float64]:
	"""Correlation matrix from a covariance matrix and standard deviations.

	`corr[i, j] = cov[i, j] / (stds[i] * stds[j])`, with unit diagonal by
	construction. A zero standard deviation is refused.
	"""
	covariance = np.asarray(covariance, dtype=np.float64)
	stds = np.asarray(stds, dtype=np.float64)
	n = stds.shape[0]
	for i in range(n):
		if stds[i] == 0.0:
			raise ValueError(f"stds = 0 at ({i}, {i}) is outside the valid range non-zero")
	out = np.empty((n, n), dtype=np.float64)
	for i in range(n):
		for j in range(n):
			out[i, j] = covariance[i, j] / (stds[i] * stds[j])
	return out


def exceedance_probability(returns: NDArray[np.float64], threshold: float) -> float:
	"""The empirical probability that a loss exceeds a threshold.

	Losses are `-returns`; the threshold is compared in magnitude, so a loss of
	3 exceeds both +3 and -3, and the comparison is strict.
	"""
	returns = np.asarray(returns, dtype=np.float64)
	n = returns.shape[0]
	if n == 0:
		return 0.0
	magnitude = abs(float(threshold))
	exceed = 0
	for r in returns:
		if -float(r) > magnitude:
			exceed += 1
	return exceed / n


def portfolio_returns(
	returns: NDArray[np.float64], weights: NDArray[np.float64]
) -> NDArray[np.float64]:
	"""Portfolio return series from per-asset returns and weights.

	`out[t] = sum_i returns[t, i] * weights[i]`. Weights are not normalised.
	"""
	returns = np.asarray(returns, dtype=np.float64)
	weights = np.asarray(weights, dtype=np.float64)
	n_time, n_assets = returns.shape
	out = np.empty(n_time, dtype=np.float64)
	for t in range(n_time):
		total = 0.0
		for i in range(n_assets):
			total += returns[t, i] * weights[i]
		out[t] = total
	return out
