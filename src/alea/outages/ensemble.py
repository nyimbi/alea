# SPDX-License-Identifier: MIT
"""Ensemble combination of satellite, weather and maintenance signals.

The specification's architecture shows a "stacked classifier". A stacker needs
labelled data in the overlap of all three modalities, and that overlap is
nearly empty: VIIRS covers everywhere, weather covers everywhere, maintenance
covers almost nowhere. A stacker trained on the handful of assets with all
three produces a model whose weights are noise.

The combination here is a **calibrated weighted average with weights chosen by
Brier score on a validation set** (07-layer4 §5). Two consequences the caller
must respect:

* Each component is calibrated before it is averaged. An uncalibrated
  probability averaged with calibrated ones is dominated by the miscalibrated
  one, whatever weights are chosen.
* Availability is tracked. If maintenance is absent its weight is zero and it
  is **not** listed among the modalities, so a consumer can see the ensemble
  was built from two components rather than silently assuming three.

A stacked classifier remains a documented extension for the point at which
overlapping labels exist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.outages.views import EnsembleConfig, EnsembleResult

logger = get_logger(__name__)

MODALITIES = ("satellite", "weather", "maintenance")


class EnsembleError(RuntimeError):
	"""The ensemble cannot be built from the inputs supplied."""


@dataclass
class Component:
	"""One calibrated probability series and the modality it came from."""

	name: str
	probability: NDArray[np.float64]

	def __post_init__(self) -> None:
		values = np.asarray(self.probability, dtype=float)
		if values.ndim != 1:
			raise ValueError(f"{self.name}: probability must be 1-D, got {values.shape}")
		if np.any(~np.isfinite(values)):
			raise ValueError(f"{self.name}: probability has non-finite values")
		if np.any((values < 0.0) | (values > 1.0)):
			raise ValueError(f"{self.name}: probability outside [0, 1]")


def brier_score(probability: NDArray[np.float64], outcome: NDArray[np.float64]) -> float:
	"""Mean squared error of a probability against a 0/1 outcome."""
	p = np.asarray(probability, dtype=float)
	y = np.asarray(outcome, dtype=float)
	if p.shape != y.shape:
		raise ValueError(f"probability {p.shape} and outcome {y.shape} must align")
	return float(np.mean((p - y) ** 2))


def calibrate_isotonic(
	probability: NDArray[np.float64],
	outcome: NDArray[np.float64],
) -> NDArray[np.float64]:
	"""Isotonic-calibrate a probability series against outcomes.

	Falls back to the raw probability when the outcome has a single class — a
	calibrator fitted on one class is a constant, which is worse than the
	uncalibrated input.
	"""
	from sklearn.isotonic import IsotonicRegression

	p = np.asarray(probability, dtype=float)
	y = np.asarray(outcome, dtype=float)
	if len(np.unique(y)) < 2:
		return p
	calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
	return np.asarray(calibrator.fit_transform(p, y), dtype=np.float64)


def select_weights(
	components: Mapping[str, NDArray[np.float64]],
	outcome: NDArray[np.float64],
	config: EnsembleConfig | None = None,
	*,
	grid_step: float = 0.05,
) -> dict[str, float]:
	"""Weights on the probability simplex minimising the Brier score.

	A grid search, not a fit: with three components and a 0.05 step there are
	231 points, the objective is cheap, and the grid is deterministic — a
	gradient fit would depend on an initialisation and AD-8 forbids that.

	Components with zero weight are dropped from the result, so the caller can
	tell "maintenance was available but uninformative" from "maintenance was
	unavailable".
	"""
	cfg = config or EnsembleConfig()
	names = sorted(components)
	if not names:
		raise EnsembleError("no components supplied")
	stack = np.vstack([np.asarray(components[name], dtype=float) for name in names])
	y = np.asarray(outcome, dtype=float)
	if stack.shape[1] != y.shape[0]:
		raise EnsembleError(
			f"components cover {stack.shape[1]} rows but the outcome has {y.shape[0]}"
		)
	if len(names) == 1:
		return {names[0]: 1.0}

	step = int(round(1.0 / grid_step))
	best: tuple[float, tuple[float, ...]] | None = None
	for weights in _simplex_grid(len(names), step):
		combined = np.tensordot(np.asarray(weights), stack, axes=1)
		score = brier_score(combined, y)
		if best is None or score < best[0] - 1e-15:
			best = (score, weights)
	assert best is not None, "the simplex grid is never empty for a positive step"
	raw = dict(zip(names, best[1], strict=True))
	weights = {name: value for name, value in raw.items() if value > cfg.min_weight}
	total = sum(weights.values())
	if total <= 0:
		# Every weight fell below the floor. Keep the best single component
		# rather than returning an all-zero ensemble, which would predict zero
		# for every row and read as "no outages anywhere".
		best_name = min(
			names, key=lambda name: brier_score(np.asarray(components[name], dtype=float), y)
		)
		logger.warning("ensemble.all_below_floor", fallback=best_name)
		return {best_name: 1.0}
	return {name: value / total for name, value in weights.items()}


def _simplex_grid(n: int, step: int):
	"""Integer points on the ``n``-simplex, scaled by ``step``."""

	def walk(remaining: int, slots: int):
		if slots == 1:
			yield (remaining,)
			return
		for value in range(remaining + 1):
			for tail in walk(remaining - value, slots - 1):
				yield (value, *tail)

	for point in walk(step, n):
		yield tuple(value / step for value in point)


def combine(
	components: Mapping[str, NDArray[np.float64]],
	outcome: NDArray[np.float64] | None = None,
	config: EnsembleConfig | None = None,
	*,
	weights: Mapping[str, float] | None = None,
	calibrate: bool | None = None,
) -> EnsembleResult:
	"""Combine component probabilities into one ensemble probability.

	``outcome`` is required when the weights are not supplied: the weights are
	chosen by Brier score, which needs an answer. Supplying precomputed
	``weights`` skips both calibration and selection, for scoring a held-out
	set against weights fitted elsewhere — the only way to avoid choosing
	weights and reporting the score on the same rows.
	"""
	cfg = config or EnsembleConfig()
	if not components:
		raise EnsembleError("no components supplied")
	do_calibrate = cfg.calibrate if calibrate is None else calibrate

	names = sorted(components)
	series = {name: np.asarray(components[name], dtype=float) for name in names}
	lengths = {len(series[name]) for name in names}
	if len(lengths) != 1:
		raise EnsembleError(f"components have different lengths: {lengths}")

	if weights is None:
		if outcome is None:
			raise EnsembleError(
				"choosing weights by Brier score needs the outcome; supply "
				"weights to score a set without refitting them on it"
			)
		y = np.asarray(outcome, dtype=float)
		working = (
			{name: calibrate_isotonic(series[name], y) for name in names}
			if do_calibrate
			else series
		)
		weights = select_weights(working, y, cfg)
	else:
		working = series

	missing = [name for name in weights if name not in working]
	if missing:
		raise EnsembleError(f"weights name unknown components: {missing}")
	total = sum(weights.values())
	if total <= 0:
		raise EnsembleError("weights sum to zero")

	combined = np.zeros(next(iter(lengths)), dtype=np.float64)
	for name, weight in weights.items():
		combined += (weight / total) * working[name]

	brier = brier_score(combined, np.asarray(outcome, dtype=float)) if outcome is not None else None
	modalities = [name for name in names if weights.get(name, 0.0) > 0.0]
	result = EnsembleResult(
		probability=[float(value) for value in combined],
		weights={name: float(weight / total) for name, weight in weights.items()},
		modalities=modalities,
		brier=brier,
	)
	logger.info(
		"ensemble.combine",
		modalities=modalities,
		weights=result.weights,
		brier=brier,
		calibrated=do_calibrate,
	)
	return result


def availability(components: Mapping[str, NDArray[np.float64]]) -> dict[str, bool]:
	"""Which modalities are present. A component with no rows is unavailable.

	Recorded in the result's provenance so a two-modality ensemble is visible
	as such (07-layer4 §5).
	"""
	return {name: name in components and len(components[name]) > 0 for name in MODALITIES}


__all__ = [
	"MODALITIES",
	"Component",
	"EnsembleError",
	"availability",
	"brier_score",
	"calibrate_isotonic",
	"combine",
	"select_weights",
]
