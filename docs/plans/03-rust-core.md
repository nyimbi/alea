# 03 — Rust Core

**Track A/B/C shared.** The five kernels, their APIs, and the PyO3 boundary.
Budget: **five weeks** across all five crates.

Read `00-architecture.md` §4 first. This document assumes AD-2 (Rust for
computation over large arrays, Python for orchestration) and does not re-argue
it.

---

## 1. Workspace

```toml
# Cargo.toml
[workspace]
resolver = "2"
members = [
	"rust/alea-rasters",
	"rust/alea-dedup",
	"rust/alea-series",
	"rust/alea-losses",
	"rust/alea-risk",
]

[workspace.package]
version = "0.1.0"
edition = "2021"
rust-version = "1.90"
license = "MIT"

[workspace.dependencies]
pyo3 = { version = "0.23", features = ["extension-module", "abi3-py312"] }
numpy = "0.23"
ndarray = { version = "0.16", features = ["rayon"] }
rayon = "1.10"
thiserror = "2.0"
```

```toml
# rust-toolchain.toml
[toolchain]
channel = "1.90.0"
components = ["rustfmt", "clippy"]
```

**Pin the toolchain.** The `stable` toolchain on the development machine has no
binaries, so a bare `cargo` invocation fails with "the 'cargo' binary … is not
applicable to the 'stable-aarch64-apple-darwin' toolchain". The pin makes the
build reproducible and sidesteps the broken toolchain entirely.

**`abi3-py312` on every crate.** Verified during planning: a
`cp312-abi3-macosx_11_0_arm64` wheel built with maturin imports and runs under
Python 3.14.8. One wheel per platform, not one per Python version.

**`maturin`, never bare `cargo build`.** A bare `cargo build` of an
`extension-module` crate fails on macOS with
`ld: symbol(s) not found for architecture arm64` — the platform needs
`-undefined dynamic_lookup`, which maturin sets.

---

## 2. Crate conventions

Every crate follows these. They are not negotiable per-crate.

```rust
#![forbid(unsafe_code)]
#![warn(missing_docs)]
```

- **No `unwrap()`/`expect()` outside `#[cfg(test)]`.** Errors are typed via
  `thiserror` and converted to Python exceptions at the boundary.
- **Errors carry context.** `AleaError::ShapeMismatch { expected: Vec<usize>, got: Vec<usize> }`,
  not `"bad shape"`.
- **Every public function has a doc comment stating units.** A function
  returning `f64` whose doc does not say whether it is MW or MWh is a bug
  waiting for a report.
- **`rayon` for parallelism, never threads by hand.** Parallelism is a
  `.par_iter()` on the outer dimension only — nested rayon is how you get a
  thread-per-pixel explosion.
- **No `pandas`, `xarray`, or `pypsa` dependency.** Takes arrays, returns
  arrays.
- **Property tests (`proptest`) plus a golden-file test** against the Python
  reference implementation in `tests/reference/`.

---

## 3. `alea-rasters` — VIIRS and raster algebra

The highest-value crate. VIIRS VNP46A2 at 500 m over Africa is ~10⁹ pixels per
day; the VZA-binned grouped quantile is a reduction over that, which is where
Python loses.

### 3.1 API

```rust
/// Per-(pixel, VZA bin, month) baseline radiance.
///
/// `radiance` and `sensor_zenith` are flat C-order arrays of identical shape
/// `[time, y, x]`. `month` is `[time]` as 1..=12. Radiance is
/// `DNB_BRDF_Corrected_NTL`, nW·cm⁻²·sr⁻¹.
///
/// Returns an array of shape `[12, n_bins, y, x]`. Cells with no observation
/// in a bin are NaN.
pub fn vza_baseline(
	radiance: ArrayView3<f32>,
	sensor_zenith: ArrayView3<f32>,
	month: ArrayView1<u8>,
	bin_size_deg: f32,
	quantile: f32,
) -> Result<Array4<f32>, AleaError>;

/// Flag pixels whose radiance falls below `threshold × baseline`.
///
/// `cloud_bits` is `QF_Cloud_Mask`; bits 0-1 are cloud confidence and the
/// caller passes `max_cloud_confidence` (0 = confident clear only).
/// Cloudy pixels are returned as NaN, never as "not an outage" — the
/// distinction matters because the two are aggregated differently.
pub fn detect_outages(
	radiance: ArrayView3<f32>,
	baseline: ArrayView4<f32>,
	month: ArrayView1<u8>,
	sensor_zenith: ArrayView3<f32>,
	cloud_bits: ArrayView3<u8>,
	bin_size_deg: f32,
	threshold: f32,
	max_cloud_confidence: u8,
) -> Result<Array3<f32>, AleaError>;

/// Aggregate pixel anomalies to grid zones.
///
/// `zone_ids` is `[y, x]` of zone indices. Returns `[time, n_zones]` of the
/// *fraction of clear pixels flagged*, in [0, 1], NaN where a zone had no
/// clear pixels at that time.
pub fn aggregate_to_zones(
	anomaly: ArrayView3<f32>,
	zone_ids: ArrayView2<u32>,
	n_zones: usize,
) -> Result<Array2<f32>, AleaError>;
```

### 3.2 Why the quantile is a separate call

The specification's example inlines baseline construction and detection. Splitting
them means the baseline can be computed once per (pixel, bin, month) and reused
across detection runs, and — more importantly — it means the baseline is a
*reviewable artefact*. A reviewer can look at the baseline raster and see whether
it is plausible. Inlined, it is invisible.

### 3.3 The first-quartile choice, pinned

`quantile` is a parameter defaulting to `0.25`. The reason it is the first
quartile rather than the mean: the first quartile is robust to occasional bright
events (lunar reflection, fires) while preserving sensitivity to darkening, which
is the signal. A test asserts that adding a 10% bright outlier population shifts
the mean baseline by > 5% and the first-quartile baseline by < 1%.

### 3.4 Cloud semantics, pinned

VNP46A2 `QF_Cloud_Mask` bits 0–1:

| Value | Meaning |
|---|---|
| `00` | Confident clear |
| `01` | Probably clear |
| `10` | Probably cloudy |
| `11` | Confident cloudy |

The specification writes both `& 0b11 == 0` and `& 0b11 != 0` in different
places — **opposite meanings**. This crate pins the correct reading
(`== 0` keeps clear pixels) and a test with a synthetic flag array asserts it.
The inversion is the kind of defect that produces a detector which reports
outages wherever it is cloudy.

### 3.5 Gates

- Differential vs. `tests/reference/rasters.py` on random arrays.
- Property: baseline is monotone in `quantile`.
- Property: `detect_outages` output is NaN wherever cloud exceeds the threshold.
- Property: `aggregate_to_zones` output is in [0, 1] or NaN.
- Edge: all-NaN input, single pixel, all-equal input, empty time axis.
- Performance: 10⁹ pixels in < 60 s on 12 cores (measured, recorded).

---

## 4. `alea-dedup` — MinHash / LSH

Replaces `datasketch` for the scanning layer's near-duplicate detection. The
specification's example shingles at k=5 over documents and inserts into an LSH
index; at 10⁶–10⁷ shingles per ingestion run, the hashing dominates.

### 4.1 API

```rust
/// MinHash signature of a document.
///
/// Shingles at `k` words, lowercased. Returns `num_perm` u64 hashes.
pub fn minhash(text: &str, k: usize, num_perm: usize, seed: u64) -> Result<Vec<u64>, AleaError>;

/// LSH index over MinHash signatures.
pub struct LshIndex { /* ... */ }

impl LshIndex {
	/// `threshold` in (0, 1); band/row counts are derived, not passed.
	pub fn new(threshold: f64, num_perm: usize, seed: u64) -> Self;

	/// Insert and return ids of near-duplicates already present.
	pub fn insert(&mut self, id: &str, signature: &[u64]) -> Vec<String>;

	pub fn query(&self, signature: &[u64]) -> Vec<String>;
}
```

### 4.2 Determinism is the requirement

`seed` is explicit and required — no default. The specification's example uses
`MinHash(num_perm=128)` with no seed, which makes deduplication
non-deterministic across runs (AD-8). A test runs the same corpus twice in
separate processes and asserts identical duplicate sets.

### 4.3 Gates

- Differential vs. `tests/reference/dedup.py` (a reimplementation of the
  datasketch algorithm, not a call to datasketch).
- Property: identical documents always collide.
- Property: Jaccard estimate error decreases with `num_perm`.
- Determinism: two processes, identical output.

---

## 5. `alea-series` — time-series aggregation

TSAM aggregation is what makes continental scale reachable (AD-9). It is also
the largest silent-error risk in the platform, so it gets the strictest
validation.

### 5.1 API

```rust
/// Aggregate a time series into representative periods.
///
/// `series` is `[n_timesteps, n_columns]`. Returns period assignments, the
/// representative period indices, and per-period weights, such that
/// `sum(weights) == n_timesteps` exactly.
pub struct AggregationResult {
	pub assignments: Vec<u32>,       // [n_timesteps]
	pub representatives: Vec<u32>,   // [n_periods]
	pub weights: Vec<f64>,           // [n_periods], sums to n_timesteps
}

pub fn aggregate(
	series: ArrayView2<f32>,
	n_periods: usize,
	period_length: usize,
	seed: u64,
) -> Result<AggregationResult, AleaError>;

/// Load-duration curve. Returns sorted-descending values per column.
pub fn load_duration_curve(series: ArrayView2<f32>) -> Result<Array2<f32>, AleaError>;
```

### 5.2 The invariant that matters

`sum(weights) == n_timesteps` **exactly**, not approximately. A weighting that
sums to 8758 instead of 8760 shifts every annual total by 0.02% — invisible
individually, systematic across a study. Asserted with exact integer comparison
on a scaled representation, and canaried.

### 5.3 Validation harness (AD-9)

`alea-series` ships with the harness that makes aggregation trustworthy:

```rust
/// Compare an aggregated solve against a full-resolution solve.
pub struct AggregationValidation {
	pub total_cost_error_pct: f64,
	pub capacity_mix_l1_error_pct: f64,
	pub emissions_error_pct: f64,
	pub peak_price_error_pct: f64,
}
```

**The acceptance rule:** on the Kenya fixture, aggregation to 12 periods must
keep total system cost within **2%** and capacity mix within **5%** of the
full-resolution solve. A config that selects a higher aggregation without a
passing validation artefact for that network is refused at load (AD-9). The
thresholds are starting points; if Kenya cannot meet 2%, the honest response is
to record the achievable number and use it as the gate, not to relax the gate
silently.

### 5.4 Gates

- Property: weights sum exactly to `n_timesteps`.
- Property: every timestep is assigned exactly once.
- Differential vs. `tests/reference/series.py`.
- Validation harness on Kenya, result recorded as an artefact.

---

## 6. `alea-losses` — loss decomposition and contingency

### 6.1 API

```rust
/// DC power flow over a network. Returns flows per branch.
pub fn dc_power_flow(
	susceptance: ArrayView2<f64>,
	injection: ArrayView1<f64>,
	slack: usize,
) -> Result<Array1<f64>, AleaError>;

/// N-1 contingency sweep: one branch out at a time.
///
/// `base_injection` is `[n_snapshots, n_buses]`. Returns, per (contingency,
/// snapshot), the energy not served and the overloaded branch count.
pub fn contingency_sweep(
	susceptance: ArrayView2<f64>,
	base_injection: ArrayView2<f64>,
	branch_from: ArrayView1<u32>,
	branch_to: ArrayView1<u32>,
	ratings: ArrayView1<f64>,
	slack: usize,
) -> Result<ContingencyResult, AleaError>;
```

### 6.2 The specification's in-place mutation bug, avoided

`spec4-base.md` §13.2 `compute_tlens` mutates `self.n.lines` in place and
restores it inside the same loop:

```python
self.n.lines.loc[line, "active"] = False
...
self.n.lines.loc[line, "active"] = True   # never reached if lpf raises
```

An exception mid-loop leaves a line **permanently deactivated** and every
subsequent contingency is computed on a degraded network. This crate takes
branch status as an immutable input and returns results; there is no mutable
network to corrupt. A test asserts that a failing contingency leaves the input
untouched.

### 6.3 The `_topology_driven` placeholder

The specification's `LossDecomposer._topology_driven` returns a hardcoded `0`.
A decomposition whose components do not sum to the total is worse than no
decomposition — it looks like an analysis. This crate either implements it
properly or the Python layer raises `NotImplementedError`; the plan's choice is
**implement it**, since the DC flow it needs is already here.

**Invariant:** `load_driven + generation_driven + topology_driven == total`,
within floating-point tolerance, asserted as a property test.

### 6.4 Gates

- Property: decomposition components sum to the total (tolerance 1e-9 relative).
- Property: a failed contingency leaves input unchanged.
- Differential vs. `tests/reference/losses.py` (which uses pypsa's `lpf` for the
  reference — the one place a reference implementation may depend on pypsa,
  because it is *checking* pypsa's physics).
- Property: DC flow conserves power at every non-slack bus.

---

## 7. `alea-risk` — Monte Carlo and portfolio risk

### 7.1 API

```rust
/// Value-at-Risk and Conditional VaR from a return sample.
///
/// `confidence` in (0, 1). Returns (VaR, CVaR) as positive loss magnitudes.
pub fn var_cvar(returns: ArrayView1<f64>, confidence: f64) -> Result<(f64, f64), AleaError>;

/// Monte Carlo over correlated inputs.
///
/// `cholesky` is the lower-triangular factor of the correlation matrix.
/// Returns `[n_paths, n_outputs]`.
pub fn monte_carlo(
	means: ArrayView1<f64>,
	stds: ArrayView1<f64>,
	cholesky: ArrayView2<f64>,
	transform: &dyn Fn(ArrayView1<f64>) -> Array1<f64>,
	n_paths: usize,
	seed: u64,
) -> Result<Array2<f64>, AleaError>;
```

### 7.2 Two hazards

**Cholesky must be checked.** A correlation matrix that is not positive-definite
— easy to construct from expert elicitation — makes Cholesky fail. The error is
typed and names the matrix, rather than producing NaNs that propagate into a
VaR.

**VaR sign convention.** VaR is reported as a **positive loss magnitude**. The
sign convention is the single most common source of error in risk reporting; a
test asserts VaR ≥ 0 and CVaR ≥ VaR, and the doc comment states it.

### 7.3 Gates

- Property: `CVaR >= VaR >= 0`.
- Property: identical seeds give identical paths (determinism, AD-8).
- Differential vs. `tests/reference/risk.py`.
- Analytic check: for a normal sample, VaR at 95% ≈ 1.645σ (tolerance 2% at
  10⁶ paths).

---

## 8. The Python boundary

### 8.1 Wrapper rules

Every kernel has a wrapper in `src/alea/_core/`, the only place `alea_core` is
imported (AD-2). Wrappers:

- assert shapes and dtypes at entry and exit,
- pass arrays only,
- contain no algorithm.

### 8.2 Build

```toml
# pyproject.toml
[build-system]
requires = ["maturin>=1.15,<2.0"]
build-backend = "maturin"

[tool.maturin]
python-source = "src"
module-name = "alea_core"
manifest-path = "rust/alea-python/Cargo.toml"
features = ["pyo3/extension-module"]
```

A single `alea-python` crate re-exports all five kernels as one extension
module, so `import alea_core` gives the whole Rust surface. Five separate
extension modules would mean five wheels to build, ship, and version.

### 8.3 Development loop

```sh
uv run maturin develop --release   # build and install into .venv
uv run pytest tests/ci -q
```

**Gate:** `maturin develop` succeeds on a clean clone, and
`tests/ci/test_core_import.py` asserts every kernel is present and callable.

---

## 9. Exit criteria for the Rust core

| # | Criterion | Gate |
|---|---|---|
| 1 | All five crates build with `clippy -D warnings` | CI |
| 2 | `maturin develop` works on a clean clone | CI |
| 3 | Every kernel has a Python reference implementation | `tests/reference/` |
| 4 | Every kernel passes differential tests | CI |
| 5 | VIIRS cloud semantics pinned by test | `test_cloud_flag_semantics` |
| 6 | Aggregation weights sum exactly | `test_the_aggregation_weights_are_the_hours_each_period_stands_for` |
| 7 | Loss decomposition sums to the total | `test_decompose_losses_components_sum_to_total` |
| 8 | All seeded functions are deterministic across processes | Determinism job |
| 9 | Performance targets measured and recorded | Benchmark artefact |
| 10 | `abi3` wheel imports under Python 3.14 | CI |

**Criterion 10 is already verified for a probe extension** — a
`cp312-abi3-macosx_11_0_arm64` wheel built with maturin and PyO3 0.23 imports
and runs `sum_sq` correctly under Python 3.14.8. The crates inherit that
configuration; the criterion guards against a crate that adds a feature breaking
abi3.
