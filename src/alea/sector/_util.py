# SPDX-License-Identifier: MIT
"""Small shared helpers for the sector modules.

Not a public module. It exists because three of the sector builders need the
same two things -- a validated snapshot index and the conversion from an annual
energy to a per-snapshot series -- and a copy of that arithmetic in each of them
is a copy that drifts.

The energy conversions live here because the alternative is a bare ``0.03333``
in four files, and a magic number in four places is a number nobody can change.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

H2_LHV_MWH_PER_KG = 0.03333
"""Lower heating value of hydrogen.

33.33 kWh/kg. This is the unit every electrolyser efficiency in the plan is
expressed against (``efficiency_lhv``), so the constant appears wherever a mass
and an energy are reconciled. Source: IEA Global Hydrogen Review 2026, Annex
(spec/data2.md §10.1.1).
"""

HOURS_PER_YEAR = 8760.0
"""Non-leap hours. Planning snapshots are a representative year, not a calendar."""


def as_index(snapshots: pd.DatetimeIndex | Sequence[pd.Timestamp] | None) -> pd.DatetimeIndex:
	"""Coerce snapshots to a ``DatetimeIndex``, or raise.

	A sector builder that invents its own snapshots produces a time series that
	does not align with the network it is added to, and PyPSA aligns on the
	index -- so a mismatched index is silently reindexed to NaNs and the sector
	becomes an empty constraint rather than an error.
	"""
	if snapshots is None:
		raise ValueError(
			"sector coupling needs the network's snapshots; a builder without "
			"them cannot produce a series that aligns with the network"
		)
	index = pd.DatetimeIndex(snapshots)
	if index.empty:
		raise ValueError("snapshots is empty")
	if not index.is_monotonic_increasing:
		raise ValueError("snapshots must be sorted ascending")
	if index.has_duplicates:
		raise ValueError("snapshots must not contain duplicates")
	return index


def total_hours(snapshots: pd.DatetimeIndex, weights: Sequence[float] | None = None) -> float:
	"""The number of hours the snapshots represent.

	On a full hourly year this is 8760. On a TSAM-aggregated network the
	representative periods carry weights that sum to 8760 (AD-9), so an annual
	volume converts to the same per-snapshot series at either resolution --
	which is what makes an aggregated sector-coupled solve comparable to a
	full-resolution one.
	"""
	index = as_index(snapshots)
	if weights is None:
		return float(len(index))
	values = np.asarray(weights, dtype=np.float64)
	if values.shape != (len(index),):
		raise ValueError(f"weights has {values.shape[0]} entries for {len(index)} snapshots")
	if np.any(values < 0):
		raise ValueError("snapshot weights must be non-negative")
	return float(values.sum())


def annual_series(
	total_mwh: float,
	snapshots: pd.DatetimeIndex,
	weights: Sequence[float] | None = None,
) -> pd.Series:
	"""Spread an annual energy uniformly across the snapshots.

	Uniform is the honest default: the plan gives an export volume in TWh/year
	and no shape, so a shape invented here would be an unsourced assumption. A
	caller with a real profile passes ``p_set`` directly instead.
	"""
	index = as_index(snapshots)
	hours = total_hours(index, weights)
	if hours <= 0:
		raise ValueError("snapshot weights sum to zero; no energy can be placed")
	return pd.Series(float(total_mwh) / hours, index=index, dtype=np.float64)


def twh_per_year_to_mwh(volume_twh: float, hours: float) -> float:
	"""A TWh/year volume, over ``hours`` of modelled horizon, in MWh.

	Scaling by the modelled horizon is what lets a two-week representative
	period carry a 100 TWh/year export obligation: the obligation is annual, the
	network is not.
	"""
	if volume_twh < 0:
		raise ValueError(f"volume_twh must be non-negative, got {volume_twh}")
	return float(volume_twh) * 1e6 * (hours / HOURS_PER_YEAR)


def series_over(
	values: Sequence[float] | pd.Series,
	index: pd.DatetimeIndex,
	name: str,
) -> pd.Series:
	"""Coerce a per-snapshot series, checking length and finiteness."""
	series = (
		values.astype(np.float64).copy()
		if isinstance(values, pd.Series)
		else pd.Series(np.asarray(values, dtype=np.float64), index=index)
	)
	if len(series) != len(index):
		raise ValueError(f"{name}: {len(series)} values for {len(index)} snapshots")
	if not np.all(np.isfinite(series.to_numpy())):
		raise ValueError(f"{name}: contains non-finite values")
	out = pd.Series(series.to_numpy(), index=index, name=name, dtype=np.float64)
	return out


def weighted_energy(frame: pd.DataFrame, weights: Sequence[float] | np.ndarray) -> float:
	"""Sum a snapshot-indexed frame of powers to energy, weighted per snapshot.

	The weights run along the *rows* (snapshots), so the multiplication must be
	along ``axis=0``. ``frame * weights`` with a 1-D array makes pandas align the
	array against the frame's *columns* instead, which either raises
	``Unable to coerce to Series`` or -- worse, when the lengths happen to match
	-- multiplies the wrong axis and returns a plausible wrong number. Both
	failures are silent in a balance whose residual is small by construction.
	"""
	values = np.asarray(weights, dtype=np.float64)
	if values.shape != (len(frame.index),):
		raise ValueError(
			f"weights has {values.shape[0]} entries for {len(frame.index)} snapshots"
		)
	return float((frame.to_numpy(dtype=np.float64) * values[:, None]).sum())


__all__ = [
	"H2_LHV_MWH_PER_KG",
	"HOURS_PER_YEAR",
	"annual_series",
	"as_index",
	"series_over",
	"total_hours",
	"twh_per_year_to_mwh",
	"weighted_energy",
]
