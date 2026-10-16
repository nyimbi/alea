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

Every gate the plans promise, with the test that implements it and the canary
that has watched it fail. **The table is generated, not written.**

    uv run python scripts/gate_register.py --markdown
    uv run python scripts/gate_register.py --check   # non-zero on any gap

This section used to carry a hand-written table of 42 rows headed "Every gate in
the plan". Measured 2026-10-16, the plans promise **113** gates, so the table
described a third of them and every gate added since was invisible to the
criterion that reads it. It was also the *second* copy of a set the register
derives, which is the defect the register exists to remove: two lists that agree
on the day one is written and diverge on the next change, with the stale one
being the one a reader trusts.

**The register is derived from two authoritative sources.**

* **The plans.** A gate is *promised* when its name appears in backticks in a
  per-document gate table or exit-criteria table. Those tables are the
  specification of what must be gated.
* **The tests.** A gate is *implemented* when a test function carries its name,
  or when a test's docstring cites it -- the idiom this codebase already uses
  (`"""§9 ``test_connector_rate_limit``."""`). It is *canaried* when a canary
  does the same.

Three verdicts come out, and each is a distinct defect:

* **unimplemented** -- the plan promises a gate and no test exists. The gate is
  prose.
* **uncanaried** -- a gate is implemented but never watched failing. AD-10: exit
  0 from a gate nobody has seen fail is not evidence.
* **orphaned** -- a test cites a gate name no plan promises. Either a typo in the
  citation or a gate dropped from the plan and left in the tree.

A gate with both a test and a canary is **verified**, which is the only status
criterion 2 below allows.

### 7.1 The two discovery rules this register got wrong

Both were found by canarying the register against its own output, and both are
worth keeping because each is a shape a checker can take.

**A section heading is not always `##`.** Gate sections were matched with
`^## `, and four plan documents state their gates under an `### N.N Gates`
heading. Eleven promised gates were invisible: the register reported
`unimplemented: 0  uncanaried: 0` while three of the eleven had no test and seven
no canary. A checker that reads one of the two spellings a document uses fails
open, and this one failed toward "clean" -- which is the direction that looks
like success.

**A canary is a behaviour, not a directory.** Canary status was decided by
`"canaries" in path.parts`, but `tests/ci/canaries/` is where the *plan* puts
them, not where they all are: a gate's own test can plant a defect in-process,
and a module under `canaries/` can hold four ordinary gate tests beside one
canary. Both directions were wrong at once. The discriminator is now a
per-*function* harness call (`planted(`, `probe(`), not a module-level import --
an import sits in the header and is shared by every function in the file, so
keying on it classifies the whole module and trades one false verdict for
another.

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
| 7 | The gate register has no "Unverified" rows for shipped gates | `gate_register.py --check` |
| 8 | CI run history is non-empty and growing | `gh api .../actions/runs` |

**Criterion 7 is the one that decays.** A gate added in a hurry ships without a
canary, and the register is where that is visible rather than forgotten.
