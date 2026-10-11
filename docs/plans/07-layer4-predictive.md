# 07 — Layer 4: Predictive Operations, Losses, and Resilience

**Track B.** VIIRS outage detection, weather-driven forecasting, predictive
maintenance, loss decomposition, TLENS, resilience metrics. Budget: **nine
weeks**, independent of Track A after the VIIRS data pipeline lands.

Track B is independent of Layers 1–3. It starts as soon as
`02-data-pipeline.md`'s VIIRS ingestion is done, and it is where the Rust
kernels earn their place.

---

## 1. What Layer 4 owns

| Concern | Module | Backed by |
|---|---|---|
| VIIRS outage detection | `outages.viirs` | `alea_rasters` |
| Weather-driven outage forecasting | `outages.weather` | xgboost/lightgbm |
| Predictive maintenance | `outages.maintenance` | `lifelines` |
| Ensemble combination | `outages.ensemble` | — |
| Loss decomposition | `losses.decompose` | `alea_losses` |
| DC power flow | `losses.flow` | `alea_losses` |
| N-1 contingency / TLENS | `losses.contingency` | `alea_losses` |
| Mitigation ranking | `losses.mitigation` | — |
| Resilience metrics | `resilience.metrics` | — |

---

## 2. VIIRS outage detection

### 2.1 The algorithm, pinned

```
For each pixel:
  bin observations by VZA (Viewing Zenith Angle), 5° bins to 70°
  for each (VZA bin, calendar month):
      baseline = first quartile of DNB_BRDF_Corrected_NTL over all years
  for each observation:
      if QF_Cloud_Mask bits 0-1 != 0b00:  -> NaN (cloudy, unknown)
      else if radiance < baseline × 0.6:  -> flagged (outage)
      else                                -> 0 (normal)
aggregate flagged fraction to grid zones
```

**Three parameters, all config, all recorded:** VZA bin size (5°), baseline
quantile (0.25), detection threshold (0.6). The specification uses these values;
they are the defaults and they are recorded in provenance so a result states
which parameters produced it.

### 2.2 The cloud-flag contradiction, resolved

`spec4-base.md` §12.2 writes:

```python
cloud = (ds["QF_Cloud_Mask"] & 0b11) != 0
anomaly = anomaly.where(~cloud)
```

and `spec4-data-collection.md` writes `& 0b11 == 0` in another place. **These are
opposite.** The `!= 0` form masks out *every* non-confident-clear pixel, which is
the conservative reading; the `== 0` form is the same condition written as a
positive test. Both of these happen to agree with each other — `~cloud` where
`cloud = bits != 0` is `bits == 0`.

The defect is not the polarity but the **conflation of "cloudy" with "not an
outage"**. A cloudy pixel is *unknown*, not *lit*. The Rust kernel
(`03-rust-core.md` §3.4) returns NaN for cloudy pixels and a test asserts it,
because NaN and 0 aggregate differently: NaN is excluded from the mean, 0 pulls
it down.

```python
# src/alea/outages/viirs.py
MAX_CLOUD_CONFIDENCE = 0
"""Keep only confident-clear (bits 0-1 == 0b00).

The spec writes both `& 0b11 == 0` and `& 0b11 != 0` in different places. The
correct reading is: bits 0-1 encode cloud confidence (00 confident clear,
01 probably clear, 10 probably cloudy, 11 confident cloudy), and only 00 is
safe. This constant is the pinned answer and a synthetic-flag test locks it.
"""
```

### 2.3 Band selection

Use `DNB_BRDF_Corrected_NTL` — the observed, BRDF-corrected band. **Never** the
gap-filled band: it interpolates across cloudy observations, so a cloud becomes
a plausible-looking radiance value and the detector sees "no outage" wherever it
is cloudy. A test asserts the gap-filled band name appears nowhere in the
detection path.

### 2.4 The Rust boundary

The three kernels are `vza_baseline`, `detect_outages`, `aggregate_to_zones`
(`03-rust-core.md` §3). The Python layer streams granules, calls the kernels per
tile, and writes the zone-level result. **Granule rasters never accumulate in
memory** — a country-year is thousands of ~100 MB granules and the working set
is one tile plus the running baseline.

### 2.5 Validation

| Claim | Source | Status | Milestone |
|---|---|---|---|
| AUC 0.8346 (Ghana) | spec4-base §5.5 | `[UNVERIFIED]` | **M2** |
| 89.41% accuracy (Johannesburg) | spec4-base §12.2 | `[UNVERIFIED]` | **M2** |

Both are validated against **independently obtained** ground truth, not against
the specification's numbers. Ghana uses GridWatch (147 sensors, Greater Accra,
2019–mid-2023). If the AUC comes out at 0.72, that is the finding — and it is
published with the parameters that produced it, because a detection AUC without
its VZA bin size, quantile, and threshold is not reproducible.

**If GridWatch is unavailable** (no token), the validation stage skips with an
explicit recorded message. It does **not** report a model as validated.

---

## 3. Weather-driven outage forecasting

### 3.1 Features

The specification's `build_features` is largely sound; the corrections are:

```python
df["season"] = (df["month"] % 12 + 3) // 3
```

This is wrong. For `month=12`: `(12 % 12 + 3) // 3 = 3 // 3 = 1`, so December is
season 1, same as January — correct for the northern hemisphere, backwards for
the southern. And `month=11` gives `(11+3)//3 = 4`, `month=1` gives `1`. The
formula is a northern-hemisphere DJF/MAM/JJA/SON encoding applied to a continent
that straddles the equator.

**Decision:** season is derived from **latitude and hemisphere** via a
documented rule, or replaced by a cyclical month encoding
(`sin(2πm/12), cos(2πm/12)`) which has no hemisphere assumption. The cyclical
encoding is the default; it is also better for a tree model, which cannot
extrapolate from a wrapped integer.

```python
df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
```

### 3.2 The rolling-feature leakage check

```python
df["outage_rate_30d"] = df.groupby("grid_zone")["outage"].transform(
    lambda x: x.shift(1).rolling(30 * 24, min_periods=1).mean()
)
```

The `shift(1)` is correct and load-bearing — without it the feature includes the
current hour's outage and the model reads the answer. **A test asserts no
feature at time *t* is a function of any value at or after *t*.** This is the
single most common way a time-series model reports a 99% AUC that evaporates in
production.

### 3.3 Class imbalance

Outages are rare. The specification uses `SMOTE` plus `scale_pos_weight=10` —
**both at once**, which double-corrects. `SMOTE` oversamples the minority class;
`scale_pos_weight` reweights it. Applying both makes the effective positive
weight roughly 10× what SMOTE alone gives.

**Decision:** use `scale_pos_weight` alone (no synthetic samples — SMOTE
interpolates between real outages and creates physically impossible feature
combinations in a weather context), and select the weight by cross-validated
PR-AUC. Record the chosen weight. **Report PR-AUC and recall at a fixed
precision, not accuracy** — with a 1% positive rate, 99% accuracy is what a
model that predicts "no outage" always achieves.

The specification's own headline — "99% accuracy" (Adrar, Algeria) — is
`[UNVERIFIED]` and is exactly the number that class imbalance produces for free.
M2 reproduces it *and* reports the base rate beside it. A 99% accuracy claim
without a base rate is not a result.

### 3.4 Validation

| Claim | Status | Milestone |
|---|---|---|
| 99% accuracy, >98% P/R/F1 (Adrar) | `[UNVERIFIED]` | M2 |
| AUC 0.8346 (Ghana) | `[UNVERIFIED]` | M2 |

---

## 4. Predictive maintenance

The specification uses `lifelines`' `CoxPHFitter` on oil-DGA and age features,
citing Uganda (132 kV transformers) and Nigeria (87% critical failure detection,
64% false-alarm reduction, 260% ROI).

**The features require data the platform does not have.** Oil dissolved-gas
analysis (`oil_dga_h2`, `oil_dga_ch4`, `oil_moisture_ppm`) comes from utility
condition-monitoring programmes, not open data. `maintenance_interval_days`
comes from a utility's work-order system.

**Decision.** The maintenance module ships with:

1. The Cox PH implementation, tested on synthetic survival data with a known
   hazard ratio (recovered within tolerance).
2. A **feature-availability guard**: if the asset table lacks the DGA columns,
   the model refuses to fit rather than silently dropping to age-only, which
   would produce a number labelled "predictive maintenance" that is actually
   "transformer age".
3. A documented path to the data: the model is real, its inputs are credentialed,
   and the module states which.

| Claim | Status | Milestone |
|---|---|---|
| 87% critical detection, 64% FAR reduction, 260% ROI (Nigeria) | `[UNVERIFIED]` | M6 |

**260% ROI is not a model output.** It is a business-case figure dependent on
failure costs, maintenance costs, and outage costs specific to an operator. M6
either reproduces it from a stated cost model or the claim is dropped from any
ALEA output.

---

## 5. Ensemble combination

The specification's architecture diagram shows a "stacked classifier" combining
satellite, weather, and maintenance outputs. A stacker needs labelled data in
the overlap of all three modalities, which is rare: VIIRS covers everywhere,
weather covers everywhere, maintenance covers almost nowhere.

**Decision.** The ensemble is a **calibrated weighted average with weights
selected by Brier score on the validation set**, and each component's
availability is tracked. If maintenance is unavailable, its weight is zero and
the ensemble reports the reduced modality set in its provenance. A stacked
classifier is an extension once overlapping labels exist.

---

## 6. Loss decomposition and TLENS

### 6.1 The in-place mutation bug

`spec4-base.md` §13.2:

```python
for line in lines:
    self.n.lines.loc[line, "active"] = False
    self.n.lpf(snapshot)
    post_ens = self._compute_ens(snapshot)
    ...
    self.n.lines.loc[line, "active"] = True
```

If `lpf` raises for any contingency, the line stays `active = False` and every
*subsequent* contingency is computed on a network that is progressively losing
lines. The results look plausible and are computed against a network that no
longer exists.

**Decision.** `alea_losses::contingency_sweep` (`03-rust-core.md` §6) takes
branch status as an **immutable input**. There is no mutable network to corrupt.
The Python wrapper asserts the input network is unchanged after the call, and a
canary injects a failing contingency and asserts the input is untouched.

### 6.2 The `_topology_driven` placeholder

```python
def _topology_driven(self, snapshot, base):
    """Difference from optimal topology."""
    return 0  # Placeholder
```

A decomposition whose components do not sum to the total is worse than no
decomposition — it looks like an analysis. **Decision: implement it.** The
topology-driven component is the loss difference between the current network and
a loss-optimal topology (optimal line switching), computed with the DC flow the
crate already provides.

**Invariant:** `load_driven + generation_driven + topology_driven == total`,
asserted as a property test to 1e-9 relative tolerance.

### 6.3 The loss-approximation benchmark

| Claim | Status | Milestone |
|---|---|---|
| Neglecting losses overestimates expansion ~20% (PyPSA-Eur) | `[UNVERIFIED]` | **M1** |
| Loss approximation < 2% error vs. full AC | `[UNVERIFIED]` | M1 |

The first is confirmed by solving Kenya with and without losses (Layer 1). The
second compares ALEA's DC-flow losses against an AC solve on the Kenya fixture —
this is the one place a reference implementation may depend on pypsa's `pf`
(AC power flow), because it is checking the DC approximation against the physics.

### 6.4 TLENS

Transmission Lines' contribution to Energy Not Supplied: for each line, the
increase in ENS when that line is out. The specification's Malawi result
(identifying Nanjoka–Nkhotakota, Nkhotakota–Dwangwa, Dwangwa–Chintheche,
Kapichila–Mlambe as critical) is `[UNVERIFIED]` and is the M1/M4 validation
target: ALEA's top-N TLENS lines must match the expert ranking, and where they
differ the difference is reported rather than tuned away.

**TLENS is where the Rust crate is decisive.** 200 lines × 8760 snapshots, each
an independent DC solve, is 1.75M solves per year analysed. In Python that is
hours; in Rust with rayon it is minutes.

---

## 7. Mitigation ranking

`MitigationRanker.evaluate_option` computes loss reduction, annual savings,
capex, and payback. Two corrections:

1. **`annual_savings = loss_reduction × 8760 × price`** treats a single-snapshot
   loss reduction as representative of all 8760 hours. It is not: losses vary
   with load and dispatch. The correct computation applies the option to
   **all** snapshots (or a validated representative set) and sums. A single-
   snapshot payback is a number with no error bar that will be believed.
2. **`payback = capex / annual_savings`** returns `inf` for zero savings, which
   sorts to the bottom — but `inf` in a report reads as "never" when it may mean
   "savings below measurement resolution". Zero-savings options report `NaN`
   with a note, not `inf`.

---

## 8. Resilience metrics

ENS, EENS, SAIDI, SAIFI, LNS. The specification's formulas are standard:

```
SAIDI = Σ(duration_i × customers_interrupted_i) / customers_total
SAIFI = Σ(customers_interrupted_i) / customers_total
EENS  = ENS × probability
```

**The input that does not exist:** `n_customers` per zone. Customer counts are
utility data, not open data. The platform derives them from WorldPop (population
per zone ÷ average household size), and **records this as a proxy** with
`uncertainty_basis="proxy"` (AD-6). SAIDI/SAIFI derived from a population proxy
are comparable across zones and are not comparable to a utility's own published
SAIDI. The artefact says which it is.

**SAIDI and SAIFI require a defined interruption threshold.** A 30-second
reclosure is not an interruption. The threshold is config, recorded, and
reported with the metric.

---

## 9. Module layout

```
src/alea/outages/
├── __init__.py
├── viirs.py          # detection pipeline, streaming granules
├── weather.py        # feature engineering, forecasting
├── maintenance.py    # Cox PH, feature-availability guard
├── ensemble.py       # calibrated weighted average
├── validate.py       # GridWatch comparison, AUC/PR-AUC
└── service.py

src/alea/losses/
├── __init__.py
├── flow.py           # DC power flow wrapper
├── decompose.py      # four-component decomposition
├── contingency.py    # N-1 sweep, TLENS
├── mitigation.py     # option ranking
└── service.py

src/alea/resilience/
├── __init__.py
├── metrics.py        # ENS, EENS, SAIDI, SAIFI, LNS
└── service.py
```

---

## 10. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_cloud_flag_semantics` | Only bits 0-1 == 0 kept; cloudy → NaN not 0 | Flip polarity; must fail |
| `test_gapfilled_band_unused` | Gap-filled band name absent from detection path | Inject it; must fail |
| `test_no_temporal_leakage` | No feature at *t* depends on *t* or later | Remove `shift(1)`; must fail |
| `test_month_encoding_hemisphere_free` | Encoding identical under hemisphere flip | Use integer season; must fail |
| `test_class_imbalance_not_double_corrected` | SMOTE and scale_pos_weight not both applied | Apply both; must fail |
| `test_base_rate_reported` | Any accuracy metric carries its base rate | Remove base rate; must fail |
| `test_maintenance_requires_dga` | Fit without DGA columns raises | Drop a column; must fail |
| `test_contingency_input_immutable` | Failing contingency leaves network unchanged | Inject failure; must fail |
| `test_decomposition_sums_to_total` | Components sum to total (1e-9) | Inject a component error; must fail |
| `test_tlens_rank_stable` | TLENS ranking deterministic across runs | Unseed; must fail |
| `test_saidi_proxy_flagged` | Population-derived SAIDI carries `proxy` basis | Remove flag; must fail |

---

## 11. Exit criteria for Layer 4

| # | Criterion | Gate |
|---|---|---|
| 1 | VIIRS detection runs over a Kenya year without OOM | Integration test |
| 2 | Cloud semantics pinned and canaried | `test_cloud_flag_semantics` |
| 3 | Ghana AUC measured and recorded | M2 artefact |
| 4 | Weather model PR-AUC and base rate reported | M2 artefact |
| 5 | No temporal leakage in any feature | `test_no_temporal_leakage` |
| 6 | Loss decomposition sums to total | `test_decomposition_sums_to_total` |
| 7 | Kenya lossless-vs-lossy difference recorded | M1 artefact |
| 8 | TLENS on a 200-line network under 2 hours | Recorded timing |
| 9 | Resilience metrics carry proxy flags where derived | `test_saidi_proxy_flagged` |
| 10 | Every `[UNVERIFIED]` claim resolved or withdrawn | M2/M6 review |

**Criterion 10 is the honesty gate.** Every claim inherited from the
specification is either reproduced with ALEA's own numbers or explicitly
withdrawn. A claim that stays in the codebase unverified past its milestone is a
claim that will be quoted.
