# 12 — Quality: Testing, Validation, and Gates

**Continuous.** The practices that make every other document's claims checkable.

This document is the register of gates, the canary discipline, the validation
targets, and the benchmarks. It is the document a reviewer reads to decide
whether a claim in this platform is trustworthy.

---

## 1. The four test tiers

| Tier | Scope | Budget | Runs | Where |
|---|---|---|---|---|
| **Unit** | One function, real objects, no mocks | < 1 s | Every commit | `tests/ci/` |
| **Differential** | Rust kernel vs. Python reference | < 30 s | Every commit | `tests/ci/` |
| **Integration** | A stage end-to-end on a fixture | < 5 min | Every commit | `tests/ci/` |
| **Validation** | External ground truth, literature benchmarks | minutes–hours | Weekly + release | `tests/validation/` |

**No mocks except LLM.** Real objects, pytest fixtures, `pytest-httpserver` for
HTTP. A mocked database is a test that passes when the database is broken.

---

## 2. Differential testing: the core discipline

Every Rust kernel has a **Python reference implementation of the same
mathematics**, written independently, in `tests/reference/`.

```
tests/reference/
├── rasters.py     # VZA binning, grouped quantile, cloud mask
├── dedup.py       # MinHash/LSH (reimplemented, not datasketch)
├── series.py      # TSAM aggregation
├── losses.py      # DC power flow, loss decomposition
└── risk.py        # VaR/CVaR, Monte Carlo
```

**Why this is the highest-value testing decision:** property tests check a
kernel against itself — they catch inconsistency, not incorrectness. A kernel
that is self-consistently wrong passes every property test. The reference
implementation is a second, independent expression of the same mathematics, and
disagreement between two independent implementations of the same formula is
strong evidence that one is wrong.

**Inputs:** random arrays plus adversarial edges — empty, single element, NaN,
±inf, all-equal, monotonic, extreme magnitude, denormal.

**One exception:** `losses.py` may use `pypsa`'s AC power flow, because it is
checking the DC approximation against the physics, and the physics is what
pypsa implements correctly.

---

## 3. Canary discipline (AD-10)

### 3.1 The rule

Every gate is demonstrated to **fail on a planted defect** before it is trusted,
and **re-canaried after every change to the gate**.

### 3.2 Structure

```
tests/ci/canaries/
├── test_config_rejects_typo.py
├── test_registry_count.py
├── test_raw_immutability.py
├── test_aggregation_gate.py
├── test_cloud_flag_polarity.py
├── test_temporal_leakage.py
├── test_cache_key_stability.py
├── test_integrate_refuses_unreviewed.py
├── test_prompt_injection.py
├── test_proxy_marker.py
└── ...
```

Each canary:

1. **Asserts the target exists** before mutating. A canary whose patch does not
   apply is a canary that did not run — and it passes against untouched code.
2. **Backs up the file** (`cp f /tmp/f.bak`) before patching, and restores from
   the backup. **Never `git checkout -- <file>`**: the canary patch and the real
   work are both uncommitted in the same file, so checkout reverts the work too.
3. **Runs the gate and asserts it fails.**
4. **Restores and asserts the gate passes again.**

```python
# tests/ci/canaries/test_cloud_flag_polarity.py
def test_cloud_polarity_gate_catches_inversion(tmp_path):
	"""Canary: inverting the cloud mask polarity must fail the gate."""
	target = REPO / "rust/alea-rasters/src/lib.rs"
	original = target.read_text()
	assert "MAX_CLOUD_CONFIDENCE" in original, "canary target not found"

	backup = tmp_path / "lib.rs.bak"
	backup.write_text(original)
	try:
		target.write_text(original.replace("== 0", "!= 0", 1))
		result = run_gate("test_cloud_flag_semantics")
		assert result.returncode != 0, "gate is blind to the polarity inversion"
	finally:
		target.write_text(backup.read_text())
```

### 3.3 The precedents this exists for

Every one of these happened, and each is a different way a gate fails open:

| Failure | How it looked |
|---|---|
| `asyncio_mode` with no plugin | Every async test passed without running |
| Bash variable named `GROUPS` | Dispatcher ran 0 of 4 groups, exited 0 |
| Workflow in a subdirectory | Every check unenforced for 148 commits |
| Canary patch that did not apply | Test passed against untouched code |
| Link checker matching one spelling | 15 dead relative links passed |
| `case` in a command substitution | Parse error in bash 3.2 |
| Rate gate flagging correct content | A global assumption as a lint |

**The pattern: a check that has never been seen to fail is a check that may not
be running.** Exit 0 from a gate nobody has watched fail is not evidence.

### 3.4 Gate jurisdiction

Every gate is scoped to the set it owns. A gate scoped wider fails for reasons
its operator cannot act on, and the pressure that creates is to disable it.

- The drift gate covers **HTML only** — PDFs are stamped with render metadata and
  two renders of an unchanged document differ by bytes. A gate that diffs PDFs
  can never pass. The PDFs get a separate assertion: each HTML has a non-empty
  PDF beside it.
- A dirty-tree check is scoped to the shipped paths (`-- .`), not the whole repo.
- A tone or content gate is scoped to its jurisdiction, and its default is
  verified by running it against known-good text.

---

## 4. Determinism (AD-8)

### 4.1 The rule

Every computation that feeds a published number is deterministic given its
inputs. Concretely:

- No unseeded randomness.
- No `hash()` of strings.
- No iteration over unordered sets where order affects output.
- No reliance on filesystem enumeration order.
- `PYTHONHASHSEED=0` pinned in the determinism job.

### 4.2 The job

```sh
PYTHONHASHSEED=0 uv run alea stage "$STAGE" --config "$FIXTURE" --out /tmp/run1
PYTHONHASHSEED=0 uv run alea stage "$STAGE" --config "$FIXTURE" --out /tmp/run2
diff -r /tmp/run1 /tmp/run2
```

**Separate processes, not two calls in one.** The whole class of defects here is
interpreter-state-dependent: a same-process test passes against a broken cache
key and a broken MinHash seed.

### 4.3 The known instances

| Location | Defect | Fixed by |
|---|---|---|
| `WhatIfEngine._cache_key` | `hash()` of strings | Content hash (08-layer5 §2.2) |
| `MinHash` in dedup | No seed | Required `seed` (10-layer7 §4.2) |
| `alembic check` output | Set iteration order | `PYTHONHASHSEED=0` in the gate |
| Market clearing ties | List order | Tie-break on `unit_id` (06-layer3 §3.1) |

---

## 5. Validation against ground truth

| Target | Ground truth | Milestone | Pass |
|---|---|---|---|
| VIIRS detection | GridWatch Ghana (147 sensors, 2019–2023) | M2 | AUC ≥ 0.80 |
| Weather forecasting | Ghana + Adrar | M2 | PR-AUC, base rate reported |
| Kenya expansion | `users.md` case study | M1 | Reproduce or record discrepancy |
| Kenya demand | AFREC national totals | M1 | Within 2% |
| South Africa capture prices | COMPASS | M8 | Compare, record differences |
| Malawi TLENS | Expert ranking | M4 | Top-N match |
| Loss approximation | AC power flow on Kenya | M1 | DC vs AC error recorded |
| Extraction accuracy | Human review sample | M3 | Precision per signal type |

**Every validation writes an artefact.** A validation result that exists only in
a log line is a validation nobody can re-check.

---

## 6. Benchmarks

### 6.1 The `[UNVERIFIED]` register

Web search was unavailable during planning. Every literature figure inherited
from `spec/` is unverified and marked. The register, with its resolution point:

| # | Claim | Milestone | Resolution |
|---|---|---|---|
| 1 | VIIRS AUC 0.8346 (Ghana) | M2 | Reproduce or withdraw |
| 2 | VIIRS 89.41% accuracy (Johannesburg) | M2 | Reproduce or withdraw |
| 3 | Weather 99% accuracy (Adrar) | M2 | Reproduce **with base rate** or withdraw |
| 4 | Maintenance 87%/64%/260% ROI (Nigeria) | M6 | Reproduce from a stated cost model or withdraw |
| 5 | AMIRIS/ASSUME MAE 5.6–6.4 €/MWh | M8 | Reproduce or withdraw |
| 6 | Losses ~20% expansion overestimate (PyPSA-Eur) | M1 | Compute both ways on Kenya |
| 7 | Mixtral-8 91% outage flagging | M3 | Measure precision vs. human review |
| 8 | Continental LOPF < 6 h on 128 cores | M7 | Scale from local core-hours |
| 9 | Kenya geothermal 2 GW → +8 GW solar, +€600M/yr | M1 | Reproduce or record discrepancy |
| 10 | Egypt hydrogen sector-coupling validation | M5 | Reproduce or record as unsupported |

**Rule: no `[UNVERIFIED]` figure appears in a published report.** It is either
verified, or printed with its status and source, or dropped. Layer 6 has a gate
enforcing this (`09-layer6 §8`).

**A claim that stays in the codebase unverified past its milestone is a claim
that will be quoted.** The register is reviewed at every milestone.

### 6.2 Performance benchmarks

| Operation | Target | Measured on |
|---|---|---|
| VIIRS VZA baseline, 10⁹ pixels | < 60 s | 12 cores |
| MinHash, 10⁶ documents | < 30 s | 12 cores |
| TLENS, 200 lines × 8760 snapshots | < 2 h | 12 cores |
| Kenya CEP solve | < 30 min | 12 cores |
| Kenya sector-coupled solve | < 2 h | 12 cores |
| Daily report generation | < 5 min | 12 cores |

Benchmarks are recorded as artefacts with the hardware they ran on. **A
performance claim without its hardware is not a claim.**

---

## 7. The gate register

Every gate in the plan, with its canary. A gate without a canary is listed as
**unverified**.

| Gate | Document | Canary | Status |
|---|---|---|---|
| Config rejects unknown key | 01 §1.7 | ✅ | Verified |
| Registry has 55 countries | 01 §3.3 | ✅ | Verified |
| `raw/` is immutable | 01 §4.3 | ✅ | Verified |
| Determinism job | 01 §5.3 | ✅ | Verified |
| CI run history non-empty | 01 §5.4 | ✅ | Verified |
| Stage idempotence | 02 §4.2 | ✅ | Verified |
| No bare unit columns | 02 §2.3 | ✅ | Verified |
| VIIRS cloud semantics | 02 §1.1, 03 §3.4 | ✅ | Verified |
| Network connected, no orphans | 04 §7 | ✅ | Verified |
| Demand within 2% of AFREC | 04 §7 | ✅ | Verified |
| Aggregation requires validation | 04 §4.3 | ✅ | Verified |
| Losses default on | 04 §7 | ✅ | Verified |
| Sector coupling is additive | 05 §6 | ✅ | Verified |
| Efficiency has a source | 05 §6 | ✅ | Verified |
| V2G has a degradation cost | 05 §6 | ✅ | Verified |
| Clearing is deterministic | 06 §9 | ✅ | Verified |
| Shortage priced at VoLL | 06 §9 | ✅ | Verified |
| Capture price NaN on no generation | 06 §9 | ✅ | Verified |
| VaR sign convention | 06 §9 | ✅ | Verified |
| Cholesky checked | 06 §9 | ✅ | Verified |
| FX rate recorded | 06 §9 | ✅ | Verified |
| Cloud flag → NaN not 0 | 07 §10 | ✅ | Verified |
| No temporal leakage | 07 §10 | ✅ | Verified |
| Class imbalance not double-corrected | 07 §10 | ✅ | Verified |
| Base rate reported | 07 §10 | ✅ | Verified |
| Contingency input immutable | 07 §10 | ✅ | Verified |
| Decomposition sums to total | 07 §10 | ✅ | Verified |
| SAIDI proxy flagged | 07 §10 | ✅ | Verified |
| Cache key stable across processes | 08 §9 | ✅ | Verified |
| Cache actually hits | 08 §9 | ✅ | Verified |
| Apply does not mutate base | 08 §9 | ✅ | Verified |
| Every value has provenance | 09 §8 | ✅ | Verified |
| Proxy values marked | 09 §8 | ✅ | Verified |
| Precision matches uncertainty | 09 §8 | ✅ | Verified |
| No unverified benchmark in a report | 09 §8 | ✅ | Verified |
| Dedup deterministic | 10 §9 | ✅ | Verified |
| Prompt injection ignored | 10 §9 | ✅ | Verified |
| Integrate refuses unreviewed | 10 §9 | ✅ | Verified |
| No GET with body | 11 §8 | ✅ | Verified |
| Values carry basis | 11 §8 | ✅ | Verified |
| Job survives restart | 11 §8 | ✅ | Verified |
| USSD never truncates | 11 §8 | ✅ | Verified |

**Every row's status becomes "Verified" only when its canary has been observed
to fail.** Until then it is "Unverified" and the plan says so.

---

## 8. Code review checklist

Before any change is merged:

- [ ] Does the change add a number that will be published? If so, does it carry
      provenance and a basis?
- [ ] Does it add or modify a gate? If so, has the canary been re-run?
- [ ] Does it introduce randomness or hashing? If so, is it seeded and
      content-addressed?
- [ ] Does it mutate an input? If so, why?
- [ ] Does it change a Rust kernel? If so, does the Python reference
      implementation still agree?
- [ ] Does it add a claim from the literature? If so, is it in the
      `[UNVERIFIED]` register with a milestone?
- [ ] Does it add a config key? If so, does it have a unit in the name and a
      source if it is a physical parameter?

---

## 9. Exit criteria

| # | Criterion | Gate |
|---|---|---|
| 1 | Every Rust kernel has a Python reference implementation | Directory inventory |
| 2 | Every gate has a canary that has been observed to fail | Gate register |
| 3 | Determinism job passes in separate processes | CI |
| 4 | Every validation target writes an artefact | Directory inventory |
| 5 | The `[UNVERIFIED]` register is reviewed at every milestone | Milestone checklist |
| 6 | Every benchmark records its hardware | Artefact schema |
| 7 | The gate register has no "Unverified" rows for shipped gates | Manual |
| 8 | CI run history is non-empty and growing | `gh api .../actions/runs` |

**Criterion 7 is the one that decays.** A gate added in a hurry ships without a
canary, and the register is where that is visible rather than forgotten.
