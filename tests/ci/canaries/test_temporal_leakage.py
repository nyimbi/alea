# SPDX-License-Identifier: MIT
"""Canary: a feature carrying the target's own hour must be refused.

The outage forecaster's whole value is that it predicts *before* the outage. A
feature built from the target -- `outage` itself, its lag, or a window centred
on the current hour -- makes the model look excellent on a random split and
useless in service. The leak is invisible in a metric and obvious in a probe.

`assert_causal_features` takes a *builder*, not a frame: it perturbs the target
at row *c*, rebuilds through the same builder, and asserts no feature at row
≤ *c* changed. That is what makes it catch a leak spelled innocently, where a
name screen would not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alea.outages.weather import LeakageError, assert_causal_features
from tests.ci.canaries import REPO, assert_raises

N = 96
TARGET = "outage"
ZONE = "zone"


def _frame() -> pd.DataFrame:
	hours = pd.date_range("2030-01-01", periods=N, freq="h")
	return pd.DataFrame(
		{
			"timestamp": hours,
			ZONE: "z1",
			TARGET: ((np.arange(N) % 13) == 0).astype(float),
			"load_mw": 1000.0 + 50.0 * np.sin(np.arange(N) * 2 * np.pi / 24),
			"temp_c": 25.0 + 3.0 * np.cos(np.arange(N) * 2 * np.pi / 24),
		}
	)


def _causal_builder(frame: pd.DataFrame) -> pd.DataFrame:
	"""A builder whose features read strictly earlier rows. The control."""
	out = frame.copy()
	out["load_lag1"] = out["load_mw"].shift(1)
	out["temp_lag1"] = out["temp_c"].shift(1)
	return out


def _contemporaneous_builder(frame: pd.DataFrame) -> pd.DataFrame:
	"""The defect: the feature reads the target's own hour."""
	out = frame.copy()
	out["leak"] = out[TARGET]
	return out


def _forward_builder(frame: pd.DataFrame) -> pd.DataFrame:
	"""The same defect one hour out."""
	out = frame.copy()
	out["leak"] = out[TARGET].shift(-1).fillna(0.0)
	return out


def test_causal_features_pass():
	assert_causal_features(_causal_builder, _frame(), ["load_lag1", "temp_lag1"], target_column=TARGET, group_column=ZONE)


def test_a_contemporaneous_feature_is_refused():
	error = assert_raises(
		LeakageError,
		assert_causal_features,
		_contemporaneous_builder,
		_frame(),
		["leak"],
		target_column=TARGET,
		group_column=ZONE,
	)
	assert "leak" in str(error)


def test_a_forward_looking_feature_is_refused():
	assert_raises(
		LeakageError,
		assert_causal_features,
		_forward_builder,
		_frame(),
		["leak"],
		target_column=TARGET,
		group_column=ZONE,
	)


def test_a_disguised_leak_is_caught_by_the_probe_not_by_its_name():
	"""Canary proper: the leak's name says nothing, and it is still refused.

	A name screen would let `system_pressure` through. The probe catches it
	because perturbing the target changes the feature at its own row.
	"""

	def disguised(frame: pd.DataFrame) -> pd.DataFrame:
		out = frame.copy()
		out["system_pressure"] = out[TARGET] * 3.0 + 1.0
		return out

	error = assert_raises(
		LeakageError,
		assert_causal_features,
		disguised,
		_frame(),
		["system_pressure"],
		target_column=TARGET,
		group_column=ZONE,
	)
	assert "system_pressure" in str(error), (
		"the gate named the wrong feature, or screened by name rather than by "
		"perturbation"
	)


def test_an_unprobeable_frame_is_refused():
	"""Two rows cannot be probed, and a silent pass would be a false all-clear."""
	short = _frame().head(2)
	assert_raises(
		LeakageError,
		assert_causal_features,
		_causal_builder,
		short,
		["load_lag1"],
		target_column=TARGET,
		group_column=ZONE,
	)


def test_the_gate_is_a_perturbation_probe():
	"""Guard against the probe being rewritten as a name screen.

	If the mechanism changes, every test above starts passing for a different
	reason at once, and none of them would say so. This asserts the mechanism.
	"""
	source = (REPO / "src" / "alea" / "outages" / "weather.py").read_text()
	assert "def assert_causal_features" in source, "the gate has moved"
	body = source.split("def assert_causal_features", 1)[1].split("\ndef ", 1)[0]
	assert "perturb" in body.lower(), (
		"assert_causal_features no longer perturbs; confirm it is still a probe "
		"rather than a name screen"
	)
	assert "sentinel" in body.lower(), "the perturbation sentinel is gone from the probe"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
