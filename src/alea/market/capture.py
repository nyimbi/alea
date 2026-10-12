# SPDX-License-Identifier: MIT
"""Capture prices and cannibalisation.

A technology's **capture price** is the revenue-weighted average price it
actually realised, which is lower than the time-weighted system price whenever
its output is correlated with low prices. That gap is why capture prices matter:
as VRE share rises, a technology's own output depresses the price it receives.

The specification's example writes ``capture = revenue / generation if
generation > 0 else 0``. That zero is a defect (06-layer3 §5.1). A technology
that generated nothing in a period has an *undefined* capture price, not a zero
one; writing zero asserts it sold its output at zero, which is false and drags
every portfolio average toward it. The correct value is NaN, and the artefact
encodes NaN as ``None`` so it is never confused with a real zero.

A second defect: ``price.mean() > 0`` as a guard for the capture *rate*
silently zeroes the rate whenever the mean price is negative or zero. Negative
prices are real (curtailment pricing), so the guard is removed and the rate is
NaN whenever the time-weighted price is zero, which is the only case in which
the ratio is genuinely undefined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.market.views import CaptureCurvePoint, CapturePrice

logger = get_logger(__name__)

_NAN = float("nan")


def capture_price(
	generation_mw: NDArray[np.float64],
	price_usd_per_mwh: NDArray[np.float64],
) -> float:
	"""Revenue-weighted capture price. NaN when there is no generation.

	NaN, not zero. A technology that generated nothing has an undefined capture
	price; reporting zero is a specific claim (it sold its output at zero) that
	is not true and that propagates into every portfolio average.
	"""
	generation = np.asarray(generation_mw, dtype=np.float64)
	price = np.asarray(price_usd_per_mwh, dtype=np.float64)
	assert generation.shape == price.shape, (
		f"generation {generation.shape} and price {price.shape} must align"
	)
	assert np.all(generation[~np.isnan(generation)] >= 0.0), "generation cannot be negative"

	total = float(np.nansum(generation))
	if not np.isfinite(total) or total <= 0.0:
		return _NAN
	revenue = float(np.nansum(generation * price))
	return revenue / total


def time_weighted_price(price_usd_per_mwh: NDArray[np.float64]) -> float:
	"""The simple mean price over the period, ignoring generation.

	This is the denominator of the capture rate. Computed with ``nanmean`` so a
	missing price is dropped rather than poisoning the mean.
	"""
	price = np.asarray(price_usd_per_mwh, dtype=np.float64)
	if price.size == 0 or np.all(np.isnan(price)):
		return _NAN
	return float(np.nanmean(price))


def capture_rate(
	generation_mw: NDArray[np.float64],
	price_usd_per_mwh: NDArray[np.float64],
) -> tuple[float, float, float]:
	"""``(capture_price, time_weighted_price, capture_rate)`` for one period.

	The capture rate is ``capture / time_weighted`` and is NaN whenever the
	time-weighted price is zero or the capture price is undefined. It is *not*
	guarded on ``mean > 0``: a negative mean price is a real market outcome and
	zeroing the rate there would hide it.
	"""
	time_weighted = time_weighted_price(price_usd_per_mwh)
	capture = capture_price(generation_mw, price_usd_per_mwh)
	if not np.isfinite(time_weighted) or time_weighted == 0.0 or not np.isfinite(capture):
		return capture, time_weighted, _NAN
	return capture, time_weighted, capture / time_weighted


def _period_positions(index: pd.Index, period: str | None) -> list[NDArray[np.intp]]:
	"""Row positions for each period, in ascending period order.

	Without ``period`` the whole index is a single period. With a pandas offset
	alias the index is bucketed by that alias. Positions come back as arrays
	rather than contiguous ranges, so an unsorted index still groups correctly.
	"""
	rows = np.arange(len(index), dtype=np.intp)
	if period is None:
		return [rows]
	assert isinstance(index, pd.DatetimeIndex), (
		f"period={period!r} needs a DatetimeIndex, got {type(index).__name__}"
	)
	grouped = pd.Series(rows, index=index)
	return [group.to_numpy(dtype=np.intp) for _, group in grouped.groupby(pd.Grouper(freq=period))]


def capture_by_technology(
	generation_mw: pd.DataFrame,
	price_usd_per_mwh: pd.Series | NDArray[np.float64],
	*,
	period: str | None = None,
) -> dict[str, list[CapturePrice]]:
	"""Capture prices for every column of a generation frame.

	``generation_mw`` is ``(time, carrier)``; ``price`` is ``(time,)``. Each
	carrier maps to one ``CapturePrice`` per period, ordered by period start;
	without ``period`` there is a single period spanning the whole series.

	``period`` is a pandas offset alias such as ``"YE"``. The index is grouped
	by that alias and capture is computed *within* each period, so a capture
	rate can be read as a time series rather than one number for the study. The
	parameter is not decorative: a caller that asks for periods gets periods.

	The per-carrier aggregation uses ``nansum`` over time so a NaN hour does not
	vanish the carrier's whole period, while the capture price itself stays NaN
	when the carrier generated nothing.
	"""
	price = np.asarray(price_usd_per_mwh, dtype=np.float64)
	assert len(generation_mw) == len(price), (
		f"{len(generation_mw)} generation rows for {len(price)} prices"
	)

	index = generation_mw.index
	windows = _period_positions(index, period)
	out: dict[str, list[CapturePrice]] = {}
	for carrier in generation_mw.columns:
		generation = np.asarray(generation_mw[carrier], dtype=np.float64)
		periods: list[CapturePrice] = []
		for positions in windows:
			window_generation = generation[positions]
			window_price = price[positions]
			capture, time_weighted, rate = capture_rate(window_generation, window_price)
			observations = int(np.count_nonzero(np.nan_to_num(window_generation) > 0.0))
			period_start = period_end = None
			if isinstance(index, pd.DatetimeIndex) and positions.size > 0:
				period_start = index[int(positions[0])].to_pydatetime()
				period_end = index[int(positions[-1])].to_pydatetime()
			periods.append(
				CapturePrice.from_float(
					carrier=str(carrier),
					generation_mwh=float(np.nansum(window_generation)),
					capture_price_usd_per_mwh=capture,
					time_weighted_price_usd_per_mwh=time_weighted,
					capture_rate=rate,
					n_observations=observations,
					period_start=period_start,
					period_end=period_end,
				)
			)
		out[str(carrier)] = periods

	logger.info(
		"capture_by_technology",
		carriers=len(out),
		periods=len(windows),
		with_observation=sum(
			1
			for periods in out.values()
			if any(p.capture_price_usd_per_mwh is not None for p in periods)
		),
	)
	return out


def cannibalisation_curve(
	points: list[tuple[float, float, float]],
) -> list[CaptureCurvePoint]:
	"""Build a cannibalisation curve from ``(vre_share, capture, time_weighted)``.

	The capture-rate curve — capture rate against VRE penetration — is the Layer
	3 deliverable a developer needs to size a project and a lender needs to
	stress a PPA. Points whose capture price is undefined are kept with a NaN
	rate rather than dropped, so a gap in the curve is visible.

	``capture`` is carried onto the point, not merely divided by the
	time-weighted price to make the rate. The rate is a ratio; the price is the
	quantity a developer sizes against and the serving table serves, so a point
	that kept the ratio and dropped the price would leave the served column
	empty for a curve whose price was known all along.
	"""
	assert points, "a curve needs at least one point"
	curve: list[CaptureCurvePoint] = []
	for share, capture, time_weighted in sorted(points, key=lambda p: p[0]):
		if not np.isfinite(time_weighted) or time_weighted == 0.0 or not np.isfinite(capture):
			rate = _NAN
		else:
			rate = capture / time_weighted
		curve.append(
			CaptureCurvePoint(
				vre_share=share,
				capture_price_usd_per_mwh=None if not np.isfinite(capture) else capture,
				capture_rate=None if not np.isfinite(rate) else rate,
				cannibalisation=None if not np.isfinite(rate) else 1.0 - rate,
			)
		)
	return curve


def portfolio_capture(
	captures: dict[str, CapturePrice],
	generation_weights: dict[str, float] | None = None,
) -> float:
	"""Fleet-average capture price, NaN-aware.

	Technologies with no generation are excluded, not counted as zero. That is
	the whole point of returning NaN from ``capture_price``: the fleet average
	is over the technologies that actually generated.
	"""
	weights = generation_weights or {
		carrier: capture.generation_mwh for carrier, capture in captures.items()
	}
	numerator = 0.0
	denominator = 0.0
	for carrier, capture in captures.items():
		if capture.capture_price_usd_per_mwh is None:
			continue
		weight = weights.get(carrier, 0.0)
		numerator += weight * capture.capture_price_usd_per_mwh
		denominator += weight
	if denominator <= 0.0:
		return _NAN
	return numerator / denominator


__all__ = [
	"cannibalisation_curve",
	"capture_by_technology",
	"capture_price",
	"capture_rate",
	"portfolio_capture",
	"time_weighted_price",
]
