# 14 — Roadmap and Delivery

**Sequencing.** Three tracks, ten milestones, checkable gates. The milestones in
this document are the ones referenced throughout the plan set — M1 through M8
plus M0 and M9.

---

## 1. The decomposition the specification misses

`spec4-base.md` §28 lists thirteen phases in a chain:

```
Data → Electricity → Sector → Renewables → Market → Outage → Losses →
Resilience → What-If → API → Reporting → Validation → Release
```

Every phase depends on the previous. Total: ~41 months. The chain is serial by
construction, and three of its dependencies are artificial:

1. **Outage prediction does not depend on the electricity model.** It needs VIIRS
   data and a grid-zone geometry. Neither comes from Layer 1.
2. **Loss mitigation needs a network, but not the sector-coupled one.** It can
   start as soon as Layer 1 produces a Kenya network.
3. **Intelligence scanning depends on nothing.** It is a source of data, not a
   consumer.

**The correct decomposition is three tracks that share Stage 0 and nothing
else:**

| Track | Contents | Depends on | Can start |
|---|---|---|---|
| **A — Physical** | Data pipeline → Layers 1, 2, 3 | Stage 0 | Week 2 |
| **B — Predictive** | VIIRS → Layer 4 → resilience | Stage 0 + VIIRS ingestion | Week 2 |
| **C — Intelligence** | Layer 7 | Stage 0 | Week 2 |

Layers 5 (what-if), 6 (reporting), and 8 (API) **join** the tracks once their
inputs exist. They are not phases.

**The saving is real but modest:** the critical path becomes A's length rather
than the sum, but A is still the longest. The larger gain is that B and C are
productive during A's long solves, and that B and C are independently
demonstrable to stakeholders months earlier.

---

## 2. Stage 0 — Foundations (1 week)

**Both/all tracks.** `01-foundations.md`.

Deliverable: config, provenance, registry, data lake, CI with canaries, DVC, CLI.

| Exit gate | Check |
|---|---|
| Config typo fails at load | Canary |
| Registry has 55 countries | Unit test |
| Artefacts round-trip provenance | Unit test |
| `raw/` immutable | Canary |
| CI run history non-empty | `gh api` |
| Every gate canaried | Canary job green |
| Determinism job passes | Two runs byte-identical |
| `dvc repro` reproduces fixture | Checksum |
| `make setup` installs the toolchain | Manual, once |

**Nothing starts until all nine pass.** They are one week and they are what makes
everything after trustworthy.

---

## 3. Milestones

### M0 — Foundations (end of week 1)

Stage 0 complete. **Gate:** all nine exit criteria above.

---

### M1 — Kenya solves (end of month 4)

**Track A.** `02-data-pipeline.md`, `03-rust-core.md` (partial),
`04-layer1-planning.md`.

Deliverable: a Kenya network that builds from artefacts, solves under HiGHS, and
reproduces (or refutes) the specification's own case study.

| Gate | Check |
|---|---|
| Kenya network connected, no orphans | Integration test |
| Demand within 2% of AFREC | `test_demand_matches_national` |
| Expansion solve completes | Integration test |
| **Losses on vs. off difference recorded** | Artefact |
| **Kenya geothermal case study reproduced or refuted** | Artefact |
| Aggregation validated and recorded | Validation artefact |
| ALEA solves with PyPSA-Earth absent | CI job |

**M1 resolves three `[UNVERIFIED]` claims:** the ~20% loss overestimate (#6), the
Kenya geothermal case study (#9), and the DC-vs-AC loss error. Each is either
reproduced with ALEA's numbers or recorded as a discrepancy.

**M1 is the first real milestone.** Everything before it is infrastructure;
everything after it depends on the Kenya network being right.

---

### M2 — Outages validated (end of month 5)

**Track B.** `07-layer4-predictive.md` §2–3, `03-rust-core.md` §3.

Deliverable: VIIRS detection and weather forecasting, validated against
independently obtained ground truth.

| Gate | Check |
|---|---|
| VIIRS runs a Kenya year without OOM | Integration test |
| Cloud semantics pinned and canaried | `test_cloud_flag_semantics` |
| Ghana AUC measured | Artefact |
| Weather PR-AUC **and base rate** reported | Artefact |
| No temporal leakage | `test_no_temporal_leakage` |

**M2 resolves claims #1, #2, #3.** The weather accuracy claim (#3) is the one to
watch: 99% accuracy on a 1%-positive-rate problem is what a constant predictor
achieves. M2 reports the base rate beside it.

**If GridWatch is unavailable**, M2 records the skip explicitly and the VIIRS
model is **not** reported as validated.

---

### M3 — Scanning extracts (end of month 6)

**Track C.** `10-layer7-scanning.md`.

Deliverable: five connector categories, deterministic + LLM extraction, review
queue, integration refusal.

| Gate | Check |
|---|---|
| Every connector rate-limited | `test_connector_rate_limit` |
| Dedup deterministic across processes | `test_dedup_deterministic` |
| Prompt injection ignored | `test_prompt_injection_ignored` |
| Unreviewed signals refused | `test_integrate_refuses_unreviewed` |
| Extraction accuracy measured per type | Artefact |

**M3 resolves claim #7** (Mixtral 91%): measured as precision against human
review, not success rate.

---

### M4 — Losses and resilience (end of month 7)

**Track B.** `07-layer4-predictive.md` §6–8, `03-rust-core.md` §6.

| Gate | Check |
|---|---|
| Decomposition sums to total | Property test |
| Contingency input immutable | Canary |
| TLENS top-N vs. expert ranking | M4 artefact |
| Resilience metrics carry proxy flags | `test_saidi_proxy_flagged` |
| TLENS on 200 lines under 2 hours | Recorded timing |

**M4 resolves the Malawi TLENS target.** Where ALEA's ranking differs from the
experts', the difference is reported, not tuned away.

---

### M5 — Sector coupling (end of month 9)

**Track A.** `05-layer2-sector.md`.

| Gate | Check |
|---|---|
| Sector coupling is additive | `test_sector_is_additive` |
| Hydrogen mass balance closes | Property test |
| Every efficiency traceable to a source | `test_efficiency_has_source` |
| Kenya geothermal cross-checked | Artefact |
| **Egypt hydrogen claim reproduced or withdrawn** | M5 artefact |

**M5 resolves claim #10.**

---

### M6 — Maintenance and markets (end of month 11)

**Tracks A and B.** `06-layer3-market.md`, `07-layer4-predictive.md` §4.

| Gate | Check |
|---|---|
| Clearing deterministic | Canary |
| Capture price NaN on no generation | Canary |
| VaR sign convention | Canary |
| Cholesky checked | Canary |
| Maintenance refuses without DGA | Canary |
| **Maintenance ROI claim reproduced or withdrawn** | M6 artefact |

**M6 resolves claim #4.** The 260% ROI is a business-case figure; M6 either
reproduces it from a stated cost model or drops it.

---

### M7 — Continental scale (end of month 14)

**Track A.** `13-deployment.md`.

| Gate | Check |
|---|---|
| Continental config builds | Integration test |
| Aggregated continental solve completes on available hardware | Recorded |
| Local core-hours scaled to the spec's 6 h target | M7 artefact |
| Determinism holds at continental scale | Determinism job |

**M7 resolves claim #8.** The specification's "< 6 hours on 128 cores" is scaled
from measured local core-hours. If the extrapolation says 30 hours, that is the
number reported.

**M7 is where the hardware constraint bites hardest.** The deliverable is not
"continental solves" — it is "continental solves at a *stated* aggregation with a
*measured* error", which is a different and more useful claim.

---

### M8 — Market validation and delivery (end of month 17)

**All tracks.** `08-layer5-whatif.md`, `09-layer6-reporting.md`,
`11-layer8-api.md`.

| Gate | Check |
|---|---|
| Cache hits across processes | Subprocess test |
| Every report value carries provenance | Canary |
| No unverified benchmark in a report | Canary |
| API: no GET with body, no blocking route | Canary |
| Long jobs survive restart | Canary |
| **South Africa capture prices vs. COMPASS** | M8 artefact |
| **AMIRIS/ASSUME MAE reproduced or withdrawn** | M8 artefact |

**M8 resolves claims #5 and closes the register except #4 and #7 if unresolved.**
It is the milestone at which the platform first has an API and a report, which is
the point at which it becomes usable by someone other than its authors.

---

### M9 — Production (end of month 20)

**All tracks.** `13-deployment.md`.

| Gate | Check |
|---|---|
| ALEA image builds and runs clean | CI |
| PyPSA-Earth image separate, no shared interpreter | Build test |
| Every long job durable | Canary |
| Review queue restore tested | Restore drill |
| Alerting fires on a planted failure | Production canary |
| **Zero `[UNVERIFIED]` claims in any published output** | Register review |

---

## 4. Timeline

```
Month:  1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20
        │
Stage 0 ██
        │
Track A    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
           data ──────▶ M1 ─────────────────▶ M5 ──────────▶ M6 ─────────▶ M7 ─────────────────────▶ M8
Track B    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
           VIIRS ────▶ M2 ──────▶ M4 ──────────────────────▶ M6 ──────────────────────────────────▶ M8
Track C    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
           scan ─────▶ M3 ────────────────────────────────────────────────────────────────────────▶ M8
                                                                                                    │
                                                                                                   M9
```

**Twenty months**, against the specification's ~41. The difference is the
three-track decomposition plus the fact that Layers 5, 6, and 8 are thin over
what they consume rather than standalone phases.

**The estimate assumes one competent developer.** It is not a promise; it is a
plan with checkable gates, which means the estimate is *falsifiable* — if M1 is
not reached by month 4, the schedule is wrong and that is knowable then rather
than at month 20.

---

## 5. Staffing

| Role | Track A | Track B | Track C |
|---|---|---|---|
| Energy systems modeller | **Critical** | — | — |
| Geospatial/data engineer | Critical (data pipeline) | Critical (VIIRS) | — |
| Rust engineer | Moderate (crates) | Moderate | Light (dedup) |
| ML engineer | — | **Critical** | Moderate |
| Backend engineer | — | — | Moderate |
| Frontend engineer | — | — | M8+ |

**One person can do this**, in the order above, because the tracks are
independent. Two people (one on A, one on B/C) compress it to roughly 12–14
months. The critical path is Track A regardless.

---

## 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Kenya fleet coverage below 90% | Medium | **High** | M1 gate names the missing capacity; manual resolution |
| Continental CEP exceeds budget | High | Medium | Aggregation (AD-9), validated; state the configuration |
| GridWatch access denied | Medium | Medium | M2 records the skip; no unvalidated claim |
| Solver licensing (Gurobi) | Medium | Medium | HiGHS + aggregation; academic negotiation |
| VIIRS volume exceeds storage | Medium | Low | Stream granules, keep checksums only |
| Ground truth for maintenance never arrives | High | Low | Module ships; claims withdrawn |
| PyPSA-Earth artefact schema insufficient | Low | **High** | M1 falsifies it; `alea.planning` owns more |
| An `[UNVERIFIED]` claim is published | Medium | **High** | Layer 6 gate + M9 register review |

**Two risks are High-impact and both are honesty risks**, not technical ones:
publishing an unverified number, and a fleet that covers 60% of capacity and
looks plausible. Both have gates. Both gates have canaries. That is the
mitigation.

---

## 7. What "done" means

The platform is complete when:

1. **Kenya is reproducible from a clean clone** — `dvc repro` produces the same
   network checksum.
2. **Every published number carries its basis** — measured, modelled, or proxy.
3. **No `[UNVERIFIED]` claim is published** — the register is empty or every
   remaining entry is printed with its status.
4. **Every gate has been seen to fail** — the canary register has no unverified
   rows.
5. **Continental scale is achievable at a stated aggregation with a measured
   error** — not "it solves", but "it solves at 12 periods with a 1.8% cost
   error".
6. **A stranger can read a report and know which numbers to trust.**

Item 6 is the one that matters. The other five exist to make it true.
