# SPDX-License-Identifier: MIT
"""Canaries for Layer 4's exit-criteria gates (`07-layer4-predictive.md` §10).

Each test here watches one gate fail on the defect it exists to catch. The gates
themselves live in `tests/ci/test_predictive_layer4.py` and, for the two already
written, in `test_temporal_leakage.py` and `test_cloud_flag_polarity.py`. This
module supplies the canaries the register was missing:

* ``test_no_temporal_leakage`` -- the module's own builder with its ``shift(1)``
  removed, and an unshifted feature built by hand;
* ``test_gapfilled_band_unused`` -- the gap-filled band injected into a granule,
  so the detection path must refuse it;
* ``test_month_encoding_hemisphere_free`` -- the default encoding switched to
  the specification's integer season, which is latitude-dependent;
* ``test_class_imbalance_not_double_corrected`` -- the shipped source required
  to import no synthetic oversampler;
* ``test_base_rate_reported`` -- the base rate made optional on the metrics
  model, so an accuracy figure can travel without it;
* ``test_maintenance_requires_dga`` -- the availability guard removed, so an
  age-only table is accepted and would fit as "transformer age";
* ``test_contingency_input_immutable`` -- a kernel that mutates its input, with
  the re-read guard both present (detects it) and removed (blind);
* ``test_decomposition_sums_to_total`` -- the sum validator disabled, so parts
  that miss their total instantiate;
* ``test_tlens_rank_stable`` -- the branch-index tie-break reversed, so the tied
  pair's order is no longer the one the gate pins;
* ``test_saidi_proxy_flagged`` -- the basis property made to always report
  measured, so a population proxy prints as a metered count.

**No reload.** Every source-mutating canary runs its probe in a subprocess that
imports the planted file fresh. An ``importlib.reload`` inside this interpreter
rebinds the module's exception classes, and a sibling test that imported the
class *before* the reload then holds a stale object its own ``pytest.raises``
misses -- which is exactly what a first version of this file did to
``test_temporal_leakage``. A subprocess leaves no mutated module behind.
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from alea.outages.maintenance import MaintenanceDataError, simulate_survival_data
from alea.outages.weather import LeakageError, assert_causal_features
from tests.ci.canaries import REPO, assert_raises, planted
from tests.ci.canaries.test_temporal_leakage import ZONE, _frame

WEATHER_PY = REPO / "src" / "alea" / "outages" / "weather.py"
OUTAGE_VIEWS_PY = REPO / "src" / "alea" / "outages" / "views.py"
VIIRS_PY = REPO / "src" / "alea" / "outages" / "viirs.py"
MAINTENANCE_PY = REPO / "src" / "alea" / "outages" / "maintenance.py"
CONTINGENCY_PY = REPO / "src" / "alea" / "losses" / "contingency.py"
LOSS_VIEWS_PY = REPO / "src" / "alea" / "losses" / "views.py"
RESILIENCE_VIEWS_PY = REPO / "src" / "alea" / "resilience" / "views.py"

LAGGED = ["outage_rate_lag", "outage_count_lag", "outage_max_lag"]


def _run(program: str) -> str:
	"""Run a probe in a fresh interpreter and return its **last** stdout line.

	Last line, not the whole output: the platform's logger writes to stdout, so
	the probe prints its answer after any log line the call emits.
	"""
	completed = subprocess.run(
		[sys.executable, "-c", program], capture_output=True, text=True, check=False
	)
	assert completed.returncode == 0, completed.stderr
	return completed.stdout.strip().splitlines()[-1]


# --------------------------------------------------------------------------
# §2.3 test_gapfilled_band_unused -- inject it; must fail
# --------------------------------------------------------------------------

_GAPFILLED_PROGRAM = (
	"import numpy as np, xarray as xr\n"
	"from alea.outages.viirs import extract_tile, RADIANCE_BAND\n"
	"shape = (1, 2, 2)\n"
	"ds = xr.Dataset(\n"
	"  {RADIANCE_BAND: (('time', 'y', 'x'), np.ones(shape, np.float32)),\n"
	"   'DNB_BRDF_Corrected_NTL_Gap_Filled': (('time', 'y', 'x'), np.ones(shape, np.float32)),\n"
	"   'QF_Cloud_Mask': (('time', 'y', 'x'), np.zeros(shape, np.uint8)),\n"
	"   'Sensor_Zenith': (('time', 'y', 'x'), np.zeros(shape, np.float32))},\n"
	"  coords={'time': np.array(['2030-01-01T00:00:00'], dtype='datetime64[ns]')})\n"
	"try:\n"
	"  extract_tile(ds)\n"
	"  print('accepted')\n"
	"except ValueError:\n"
	"  print('refused')\n"
)


def test_the_gate_refuses_a_granule_carrying_the_gap_filled_band():
	"""Canary proper: inject the band and watch ``extract_tile`` refuse.

	The gap-filled band interpolates across cloudy observations, so a cloud
	reads as a plausible radiance and the detector sees "no outage" exactly
	where it is blind. The check is a substring over the variable names, so a
	renamed-but-equivalent band is still caught -- which the injection here
	exercises through the real extraction path.
	"""
	assert _run(_GAPFILLED_PROGRAM) == "refused"
	# And the gate is the scan itself: disable it and the band is read.
	with planted(VIIRS_PY, "if offenders:", "if False and offenders:"):
		assert _run(_GAPFILLED_PROGRAM) == "accepted", (
			"the band was refused without the scan; the canary is a no-op"
		)
	# Restored.
	assert _run(_GAPFILLED_PROGRAM) == "refused"


# --------------------------------------------------------------------------
# §3.2 test_no_temporal_leakage -- remove shift(1); must fail
# --------------------------------------------------------------------------

_LEAK_PROGRAM = (
	"import numpy as np, pandas as pd\n"
	"from alea.outages.weather import build_features, assert_causal_features, LeakageError\n"
	"N = 96\n"
	"hours = pd.date_range('2030-01-01', periods=N, freq='h')\n"
	"frame = pd.DataFrame({'timestamp': hours, 'grid_zone': 'z1',\n"
	"  'outage': ((np.arange(N) % 13) == 0).astype(float),\n"
	"  'load_mw': 1000.0 + 50.0 * np.sin(np.arange(N) * 2 * np.pi / 24),\n"
	"  'temp_c': 25.0 + 3.0 * np.cos(np.arange(N) * 2 * np.pi / 24)})\n"
	"try:\n"
	"  assert_causal_features(lambda f: build_features(f, group_column='grid_zone'), frame,\n"
	"    ['outage_rate_lag', 'outage_count_lag', 'outage_max_lag'],\n"
	"    target_column='outage', group_column='grid_zone')\n"
	"  print('causal')\n"
	"except LeakageError:\n"
	"  print('leak')\n"
)


def _unshifted_builder(frame):
	"""The defect: a rolling mean that includes the hour it predicts."""
	out = frame.copy()
	out["outage_rate_lag"] = out.groupby(ZONE)["outage"].transform(
		lambda x: x.rolling(5, min_periods=1).mean()
	)
	return out


def test_the_gate_refuses_an_unshifted_feature():
	"""A leak built by hand, caught by the perturbation probe rather than a name."""
	error = assert_raises(
		LeakageError,
		assert_causal_features,
		_unshifted_builder,
		_frame(),
		["outage_rate_lag"],
		target_column="outage",
		group_column=ZONE,
	)
	assert "outage_rate_lag" in str(error)


def test_the_gate_refuses_the_module_builder_with_its_shift_removed():
	"""Canary proper: remove the module's own ``shift(1)`` and watch it fail.

	The probe runs the real ``build_features`` from a freshly imported module, so
	the leak is the one the module would have, not a copy of it. The subprocess
	reads the planted file; no reloaded module survives for the next test.
	"""
	# Control: the shipped builder is causal.
	assert _run(_LEAK_PROGRAM) == "causal"
	with planted(WEATHER_PY, "shifted = grouped.shift(lag)", "shifted = grouped.shift(0)"):
		assert _run(_LEAK_PROGRAM) == "leak", (
			"the unshifted builder was not caught; the gate is blind to the leak "
			"this canary planted"
		)
	# Restored.
	assert _run(_LEAK_PROGRAM) == "causal"


# --------------------------------------------------------------------------
# §3.1 test_month_encoding_hemisphere_free -- use integer season; must fail
# --------------------------------------------------------------------------

_MONTH_PROGRAM = (
	"from alea.outages.views import WeatherConfig\n"
	"from alea.outages.weather import add_month_encoding\n"
	"import pandas as pd\n"
	"f = pd.DataFrame({'month': [1, 7], 'latitude': [10.0, 10.0]})\n"
	"c = add_month_encoding(f, WeatherConfig())\n"
	"cols = sorted(k for k in c.columns if k.startswith('month_') or k.startswith('season'))\n"
	"print(','.join(cols))\n"
)


def test_the_default_encoding_is_the_cyclical_pair():
	"""The hemisphere-free pair is what a caller gets by default."""
	assert _run(_MONTH_PROGRAM) == "month_cos,month_sin"


def test_the_gate_refuses_a_latitude_dependent_default():
	"""Canary proper: make the default the specification's integer season.

	The integer season is a northern-hemisphere DJF/MAM/JJA/SON encoding, so the
	default feature becomes latitude-dependent and the gate must fail. The defect
	is a one-token change to a default the gate reads, planted and read in a
	subprocess so no mutated model class is left in this interpreter.
	"""
	original = 'month_encoding: Literal["cyclical", "hemisphere", "integer"] = "cyclical"'
	planted_default = 'month_encoding: Literal["cyclical", "hemisphere", "integer"] = "integer"'
	with planted(OUTAGE_VIEWS_PY, original, planted_default):
		columns = _run(_MONTH_PROGRAM)
		assert columns == "season", (
			f"the integer season did not become the default: {columns!r}. The "
			f"canary did not reproduce the defect."
		)
	# Restored.
	assert _run(_MONTH_PROGRAM) == "month_cos,month_sin"


# --------------------------------------------------------------------------
# §2.1 the detection parameters are reachable -- pin them; must fail
# --------------------------------------------------------------------------

CONFIG_MODELS_PY = REPO / "src" / "alea" / "config" / "models.py"

#: The root model's `predictive` field, and the absence of it. The defect is an
#: *absent field*, so the canary removes the line rather than changing a value:
#: a `predictive` section that the root model does not declare is rejected by
#: `extra="forbid"`, and `predictive_config` then falls back to the class
#: defaults -- which is precisely the shipped state this gate exists for.
PREDICTIVE_FIELD = '\tpredictive: PredictiveConfig = Field(default_factory=PredictiveConfig)\n'

GATE = "test_the_detection_parameters_are_reachable_from_the_root_config"


def _gate_exit_code() -> int:
	"""Run the real gate in a fresh interpreter and return its exit code.

	The gate itself, not a probe that reimplements it. A canary that asserts its
	own reading of the config proves the *mechanism* is load-bearing and says
	nothing about whether the gate would notice -- and the gate is the artefact
	the register counts. A pytest subprocess is slower than an inline probe and
	is the only form that answers the question the canary asks.
	"""
	completed = subprocess.run(
		[
			sys.executable,
			"-m",
			"pytest",
			"tests/ci/test_predictive_layer4.py",
			"-q",
			"-x",
			"-k",
			"reachable",
		],
		capture_output=True,
		text=True,
		check=False,
		cwd=REPO,
	)
	return completed.returncode


def test_the_reachability_gate_catches_a_root_config_without_the_section():
	"""``test_the_detection_parameters_are_reachable_from_the_root_config`` must fail.

	The gate is what stands between "the field exists" and "the field is read":
	the shipped defect had neither, and the weaker version of this gate -- assert
	``hasattr(Config, "predictive")`` -- would have passed a root model that
	declared the section and a service that ignored it. The canary therefore
	removes the field and runs the gate.

	The planted defect surfaces as a load error rather than a wrong number,
	because ``extra="forbid"`` rejects the override once the field is gone. Both
	are failures and the gate does not distinguish them, which is correct: an
	unreachable parameter and a rejected one are the same defect to the operator.
	"""
	assert PREDICTIVE_FIELD in CONFIG_MODELS_PY.read_text(), (
		"canary target not found: the root Config no longer declares `predictive`, "
		"so this canary would be planting a defect that is already present"
	)
	assert _gate_exit_code() == 0, "the gate does not pass on the shipped tree"

	with planted(CONFIG_MODELS_PY, PREDICTIVE_FIELD, ""):
		assert _gate_exit_code() != 0, (
			"a root Config without a `predictive` field still passed the gate, so "
			"the gate cannot tell a reachable parameter from an unreachable one"
		)

	assert _gate_exit_code() == 0, "the restore was not proven"


# --------------------------------------------------------------------------
# §3.3 test_class_imbalance_not_double_corrected -- apply both; must fail
# --------------------------------------------------------------------------


def test_the_config_refuses_a_smote_key():
	"""The double-correction is refused structurally: there is no field to set."""
	from pydantic import ValidationError

	from alea.outages.views import WeatherConfig

	with pytest.raises(ValidationError, match="extra_forbidden"):
		WeatherConfig(use_smote=True)


def test_no_synthetic_oversampler_is_imported_or_constructed():
	"""Canary proper: the moment SMOTE enters the module, this fails.

	The defect is not a wrong value but an *import*: the specification applies
	SMOTE and ``scale_pos_weight`` together, and the correction is that the
	oversampler is absent. A source check is the only way to see an import that
	would otherwise be exercised only when a training path is taken.
	"""
	source = WEATHER_PY.read_text()
	assert "imblearn" not in source, "an imblearn (SMOTE) import has entered the forecaster"
	assert "SMOTE(" not in source, "a SMOTE instance is constructed in the forecaster"
	# The correction is present and singular: the weight is applied, alone.
	assert "scale_pos_weight" in source, "the class-imbalance correction is gone entirely"


# --------------------------------------------------------------------------
# §3.3 test_base_rate_reported -- remove base rate; must fail
# --------------------------------------------------------------------------

_BASE_RATE_PROGRAM = (
	"from alea.outages.views import DetectionMetrics\n"
	"try:\n"
	"  DetectionMetrics.model_validate({'auc': 0.9, 'pr_auc': 0.5, 'accuracy': 0.99,\n"
	"    'precision': 0.5, 'recall': 0.5, 'f1': 0.5, 'threshold': 0.5,\n"
	"    'n_total': 100, 'n_positive': 1})\n"
	"  print('accepted')\n"
	"except Exception:\n"
	"  print('refused')\n"
)


def test_the_gate_refuses_an_accuracy_without_a_base_rate():
	"""The gate, exercised: a metric set missing ``base_rate`` cannot be built."""
	from pydantic import ValidationError as PydanticValidationError

	from alea.outages.views import DetectionMetrics

	with pytest.raises(PydanticValidationError):
		DetectionMetrics.model_validate(
			{
				"auc": 0.9,
				"pr_auc": 0.5,
				"accuracy": 0.99,
				"precision": 0.5,
				"recall": 0.5,
				"f1": 0.5,
				"threshold": 0.5,
				"n_total": 100,
				"n_positive": 1,
			}
		)


def test_the_gate_is_the_required_field():
	"""Canary proper: make ``base_rate`` optional and watch it travel alone.

	The gate exists because 99% accuracy at a 1% positive rate is what a
	constant "no outage" prediction gets for free. With the field defaulted, a
	producer that forgot the base rate constructs a metric set anyway -- the
	defect, an accuracy figure with no context. The canary makes that reachable.
	"""
	field = "base_rate: float = Field(ge=0.0, le=1.0)"
	defaulted = "base_rate: float = Field(default=0.0, ge=0.0, le=1.0)"
	# Two fields carry this line (DetectionMetrics and ForecastMetrics); both are
	# part of the same gate, so both are planted.
	assert OUTAGE_VIEWS_PY.read_text().count(field) == 2, "the base-rate fields moved"
	with planted(OUTAGE_VIEWS_PY, field, defaulted, count=2):
		assert _run(_BASE_RATE_PROGRAM) == "accepted", (
			"the base rate was still required; the canary is a no-op"
		)
	# Restored.
	assert _run(_BASE_RATE_PROGRAM) == "refused"


# --------------------------------------------------------------------------
# §4 test_maintenance_requires_dga -- drop a column; must fail
# --------------------------------------------------------------------------

_MAINTENANCE_PROGRAM = (
	"from alea.outages.maintenance import (\n"
	"  assert_feature_availability, MaintenanceDataError, simulate_survival_data)\n"
	"frame = simulate_survival_data(400, seed=2).drop(columns=['oil_dga_h2'])\n"
	"try:\n"
	"  assert_feature_availability(frame)\n"
	"  print('accepted')\n"
	"except MaintenanceDataError:\n"
	"  print('refused')\n"
)


def test_the_gate_refuses_a_fit_without_dga():
	"""The gate, exercised: a missing DGA column stops the fit."""
	from alea.outages.maintenance import assert_feature_availability

	frame = simulate_survival_data(400, seed=2).drop(columns=["oil_dga_h2"])
	error = assert_raises(MaintenanceDataError, assert_feature_availability, frame)
	assert "oil_dga_h2" in str(error)


def test_the_gate_is_the_availability_guard():
	"""Canary proper: disable the guard and watch the age-only table pass.

	With the guard removed the same table is accepted and the availability map
	shows ``oil_dga_h2`` absent -- a fit that would proceed labelled predictive
	maintenance and be transformer age. The guard is asserted directly rather
	than through ``fit_cox``: ``lifelines`` trips the repo's
	``filterwarnings = error`` on a ``datetime.utcnow`` deprecation, so a real
	fit cannot run in-process.
	"""
	assert _run(_MAINTENANCE_PROGRAM) == "refused"
	with planted(MAINTENANCE_PY, "if cfg.require_dga:", "if False and cfg.require_dga:"):
		assert _run(_MAINTENANCE_PROGRAM) == "accepted", (
			"the guard's removal did not let the fit degrade; the canary is a no-op"
		)
	# Restored.
	assert _run(_MAINTENANCE_PROGRAM) == "refused"


# --------------------------------------------------------------------------
# §6.1 test_contingency_input_immutable -- inject failure; must fail
# --------------------------------------------------------------------------

_CONTINGENCY_PROGRAM = (
	"import numpy as np\n"
	"import alea.losses.contingency as C\n"
	"from alea.losses.flow import Network, susceptance_matrix\n"
	"from alea._core import contingency_sweep as real_kernel\n"
	"bf = np.array([0, 1], dtype=np.uint32); bt = np.array([1, 2], dtype=np.uint32)\n"
	"bs = np.array([10.0, 10.0])\n"
	"net = Network(susceptance=susceptance_matrix(bf, bt, bs, 3), branch_from=bf,\n"
	"  branch_to=bt, branch_susceptance=bs, resistance_ohm=np.array([0.5, 0.5]),\n"
	"  voltage_kv=np.array([132.0, 132.0]), ratings_mw=np.array([100.0, 100.0]),\n"
	"  branch_names=('L0', 'L1'))\n"
	"inj = np.tile(np.array([50.0, 0.0, -50.0]), (4, 1))\n"
	"def mutating(susceptance, *a, **k):\n"
	"  r = real_kernel(susceptance, *a, **k)\n"
	"  susceptance[:] = susceptance + 999.0\n"
	"  return r\n"
	"C.contingency_sweep = mutating\n"
	"try:\n"
	"  C.sweep(net, inj)\n"
	"  print('blind')\n"
	"except RuntimeError:\n"
	"  print('caught')\n"
)


def test_the_gate_refuses_a_mutating_kernel():
	"""The gate with a mutating kernel plugged in: it must raise."""
	from alea._core import contingency_sweep as real_kernel
	from alea.losses import contingency

	network = _two_branch()
	contingency.contingency_sweep = _mutating_kernel(real_kernel)
	try:
		error = assert_raises(RuntimeError, contingency.sweep, network, _dispatch())
		assert "mutated" in str(error)
	finally:
		contingency.contingency_sweep = real_kernel


def test_the_gate_is_the_after_the_call_reread():
	"""Canary proper: remove the re-read and the same mutation goes unnoticed.

	The kernel takes branch status as an immutable input, but the guard is what
	proves it stayed immutable. With the guard removed, ``sweep`` returns
	normally on a network it has just corrupted -- the specification's defect,
	where every later contingency is computed on a network that no longer exists.
	"""
	guard = "if not np.array_equal(current, original):"
	with planted(CONTINGENCY_PY, guard, "if False and not np.array_equal(current, original):"):
		assert _run(_CONTINGENCY_PROGRAM) == "blind", (
			"the corruption was caught without the guard; the canary is a no-op"
		)
	# Restored.
	assert _run(_CONTINGENCY_PROGRAM) == "caught"


def _two_branch():
	"""Bus 0 -- bus 1 -- bus 2, equal susceptance: either branch strands bus 2."""
	from alea.losses.flow import Network, susceptance_matrix

	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([100.0, 100.0]),
		branch_names=("L0", "L1"),
	)


def _dispatch(n_snapshots: int = 4) -> np.ndarray:
	"""50 MW stranded at bus 2 under either outage; ENS is real, not zero."""
	return np.tile(np.array([50.0, 0.0, -50.0]), (n_snapshots, 1))


def _mutating_kernel(real):
	"""A kernel that corrupts the caller's array the way the spec's does."""

	def fake(susceptance, *args, **kwargs):
		result = real(susceptance, *args, **kwargs)
		susceptance[:] = susceptance + 999.0
		return result

	return fake


# --------------------------------------------------------------------------
# §6.2 test_decomposition_sums_to_total -- inject a component error; must fail
# --------------------------------------------------------------------------

_DECOMPOSITION_PROGRAM = (
	"from alea.losses.views import LossComponents\n"
	"try:\n"
	"  LossComponents(load_driven_mwh=120.0, generation_driven_mwh=80.0,\n"
	"    topology_driven_mwh=20.0, total_mwh=220.001)\n"
	"  print('accepted')\n"
	"except ValueError:\n"
	"  print('refused')\n"
)


def test_the_gate_refuses_parts_that_miss_their_total():
	"""The gate, exercised: a 0.1% miss is refused."""
	from alea.losses.views import LossComponents

	error = assert_raises(
		ValueError,
		LossComponents,
		load_driven_mwh=1.0,
		generation_driven_mwh=0.0,
		topology_driven_mwh=0.0,
		total_mwh=1.001,
	)
	assert "do not sum" in str(error)


def test_the_gate_is_the_sum_validator():
	"""Canary proper: disable the validator and watch the miss instantiate."""
	check = "if abs(parts - self.total_mwh) / scale > self.tolerance:"
	off = "if False and abs(parts - self.total_mwh) / scale > self.tolerance:"
	with planted(LOSS_VIEWS_PY, check, off):
		assert _run(_DECOMPOSITION_PROGRAM) == "accepted", (
			"the miss was refused without the validator; the canary is a no-op"
		)
	# Restored.
	assert _run(_DECOMPOSITION_PROGRAM) == "refused"


# --------------------------------------------------------------------------
# §6.4 test_tlens_rank_stable -- unseed; must fail
# --------------------------------------------------------------------------

_TLENS_PROGRAM = (
	"import numpy as np\n"
	"from alea.losses.flow import Network, susceptance_matrix\n"
	"from alea.losses.contingency import tlens\n"
	"from alea.losses.views import LossConfig\n"
	"bf = np.array([0, 1, 1], dtype=np.uint32); bt = np.array([1, 2, 2], dtype=np.uint32)\n"
	"bs = np.array([10.0, 10.0, 10.0])\n"
	"net = Network(susceptance=susceptance_matrix(bf, bt, bs, 3), branch_from=bf,\n"
	"  branch_to=bt, branch_susceptance=bs, resistance_ohm=np.array([0.5, 0.5, 0.5]),\n"
	"  voltage_kv=np.array([132.0, 132.0, 132.0]),\n"
	"  ratings_mw=np.array([1000.0, 1000.0, 1000.0]), branch_names=('L0', 'L1', 'L2'))\n"
	"inj = np.tile(np.array([50.0, 0.0, -50.0]), (4, 1))\n"
	"r = tlens(net, inj, LossConfig(snapshot_hours=1.0))\n"
	"print(','.join(str(e.branch) for e in r.entries))\n"
)


def test_the_ranking_is_stable_across_runs():
	"""The gate, exercised: the same network ranks the same way twice."""
	from alea.losses.contingency import tlens

	network = _parallel_pair()
	first = [e.branch for e in tlens(network, _dispatch()).entries]
	second = [e.branch for e in tlens(network, _dispatch()).entries]
	assert first == second == [0, 1, 2]
	# The fixture must actually tie, or the stability is trivial.
	tied = {e.branch: e.ens_increase_mwh for e in tlens(network, _dispatch()).entries if e.branch in (1, 2)}
	assert tied[1] == pytest.approx(tied[2]), "the parallel branches did not tie"


def test_the_gate_is_the_branch_index_tie_break():
	"""Canary proper: reverse the tie-break and watch the pinned order move.

	The tied branches are ordered by index, so the ranking is a deterministic
	function of the network rather than of whatever order the sort happened to
	leave them in (AD-8). Reversing the tie-break reorders the tied pair -- which
	is the observation that the ordering comes from the key and not from chance,
	the property the plan's "unseed" canary is asking after.
	"""
	key = "return (-diverged_fraction, -finite, entry.branch)"
	reversed_key = "return (-diverged_fraction, -finite, -entry.branch)"

	assert _run(_TLENS_PROGRAM) == "0,1,2"
	with planted(CONTINGENCY_PY, key, reversed_key):
		assert _run(_TLENS_PROGRAM) == "0,2,1", (
			"the tie-break did not order the tied pair; the canary is a no-op"
		)
	# Restored.
	assert _run(_TLENS_PROGRAM) == "0,1,2"


def _parallel_pair():
	"""A radial line with two interchangeable parallel branches (L1, L2)."""
	from alea.losses.flow import Network, susceptance_matrix

	branch_from = np.array([0, 1, 1], dtype=np.uint32)
	branch_to = np.array([1, 2, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0, 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0, 132.0]),
		ratings_mw=np.array([1000.0, 1000.0, 1000.0]),
		branch_names=("L0", "L1", "L2"),
	)


# --------------------------------------------------------------------------
# §8 test_saidi_proxy_flagged -- remove flag; must fail
# --------------------------------------------------------------------------

_PROXY_PROGRAM = (
	"from datetime import UTC, datetime\n"
	"from alea.resilience.metrics import compute_metrics, customers_from_population\n"
	"from alea.resilience.views import InterruptionEvent, ResilienceConfig\n"
	"c = customers_from_population('nairobi', 4_400_000.0, source='WorldPop')\n"
	"e = InterruptionEvent(zone='nairobi', started_at=datetime(2030, 1, 1, tzinfo=UTC),\n"
	"  duration_minutes=120.0, load_mw=50.0)\n"
	"m = compute_metrics([e], {'nairobi': c}, ResilienceConfig())\n"
	"print('proxy' if m.customers_are_proxy else 'measured')\n"
)


def test_a_population_derived_saidi_is_flagged():
	assert _run(_PROXY_PROGRAM) == "proxy"


def test_the_gate_is_the_basis_property():
	"""Canary proper: make the basis property always report measured.

	A SAIDI computed from a WorldPop denominator is a proxy index: comparable
	across zones, not comparable to a utility's own figure. With the property
	hardwired to False the same metric prints as metered -- the laundering the
	gate prevents -- so the gate is blind and the canary has reproduced it.
	"""
	prop = "return self.customers_basis is Basis.PROXY"
	with planted(RESILIENCE_VIEWS_PY, prop, "return False"):
		assert _run(_PROXY_PROGRAM) == "measured", (
			"a proxy still reported as a proxy under a basis that always returns "
			"measured; the canary did not reproduce the laundering"
		)
	# Restored.
	assert _run(_PROXY_PROGRAM) == "proxy"


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
