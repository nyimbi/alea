# Alea Implementation Plan

**Status**: Draft for execution
**Companion to**: `spec/spec4-base.md`, `spec/spec4-data-collection.md`
**Verified against**: the working tree at `b3f43dc`, 2026-10-11

This plan turns the specification into a build order. It is deliberately
opinionated about *sequence* — the specification says what the platform is, not
what to do on Monday — and it flags the places where the specification is wrong
or assumes resources this machine does not have.

---

## 1. Constraints discovered, not assumed

Everything in this section was checked against the machine and the upstream
projects. They are the inputs the plan is built on, so they are stated before
the plan rather than buried in it.

| Finding | Evidence | Consequence |
|---|---|---|
| The stack installs on Python 3.14 | `uv sync --extra dev` exits 0; 115 packages resolved | Keep 3.14 |
| TensorFlow cannot install on 3.14 | No `cp314` wheel; ABI tags stop at `cp313` | Dropped from `pyproject.toml`. Outage models use xgboost/lightgbm |
| `pypsa-earth` is **not on PyPI** | PyPI returns 404 for the project | It cannot be a `dependencies` entry. See §3.1 |
| PyPSA-Earth is a Snakemake workflow | GitHub repo, 33.5 MB, v0.9.0 (2026-09-03), pushed 2026-10-10 | Consume its *artefacts*, not its code |
| `pypsa` 1.4.0 works with pandas 3.0.5 | Imported and constructed successfully | No pin fight |
| HiGHS is available in-process | `pypsa` 1.4 declares `highspy` as a **direct dependency**, so it arrives with the planning core | Solver cost is zero up to ~500k variables, and a dev-only install can already solve |
| This machine is **12 cores / 96 GB / 173 GB free** | `sysctl`, `df` | The spec's continental tier (128 cores / 512 GB / 10 TB) is **out of reach locally** |

The hardware finding is the one that most changes the plan. A continental
capacity-expansion problem over 55 nodes and 8760 hourly snapshots, across four
planning horizons, is not solvable here — and probably not on any single machine
the project has. The plan therefore treats **continental scale as a
deployment-time concern, not a development-time one**, and builds every
capability so that it is correct at one-country scale and *deployable* at
continental scale.

---

## 2. The organising insight: the layers are not a chain

The specification draws the seven layers as a stack and implies you build the
bottom first. Read the actual data dependencies and three tracks emerge, which
can be built concurrently by different people:

```
                    ┌──────────────────────────────────────────┐
                    │  Stage 0: Foundations                    │
                    │  config · provenance · data lake · CI    │
                    └────────────────┬─────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
┌───────────────────┐   ┌────────────────────────┐   ┌────────────────────┐
│ TRACK A           │   │ TRACK B                │   │ TRACK C            │
│ Physical          │   │ Predictive             │   │ Intelligence       │
│                   │   │                        │   │                    │
│ data pipeline     │   │ VIIRS + weather +      │   │ Layer 7 scanning   │
│   ↓               │   │ GridWatch ingestion    │   │   ↓                │
│ Layer 1 planning  │   │   ↓                    │   │ signal contract    │
│   ↓               │   │ Layer 4a outage ML     │   │   ↓                │
│ Layer 2 sector    │   │   ↓                    │   │ review queue       │
│   ↓               │   │ (Layer 4b resilience   │   │   ↓                │
│ Layer 3 market    │   │  needs Track A)        │   │ model integration  │
│   ↓               │   │                        │   │                    │
│ Layer 5 what-if   │   │                        │   │                    │
└─────────┬─────────┘   └───────────┬────────────┘   └─────────┬──────────┘
          │                         │                          │
          └─────────────────────────┼──────────────────────────┘
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │  Layer 6 reporting · Layer 8 API         │
                    └──────────────────────────────────────────┘
```

**Why this matters.** Layer 4's outage prediction needs satellite radiance,
weather reanalysis, and ground-truth labels. It does *not* need a solved
capacity-expansion network. Layer 7 needs nothing at all except the signal
contract, which already exists. Only three things in the whole platform actually
require Track A to finish first: Layer 4b (contingency/TLENS — needs a network
to fail lines in), Layer 5 (re-solve — needs a base network), and Layer 6's
market and planning sections.

The specification's own roadmap serialises all thirteen phases. Three tracks
built concurrently is roughly a 2.5× wall-clock saving, and more importantly it
puts the three genuinely risky capabilities — continental data assembly, VIIRS
detection, and LLM extraction — on parallel critical paths instead of one
queue, so a failure in one does not idle the other two.

**Track B is the fastest to a defensible result.** VIIRS and ERA5 are open,
global, and do not depend on any African utility's cooperation. A validated
outage-detection AUC against the published Ghana benchmark is achievable without
a single data-sharing agreement.

---

## 3. Architecture decisions

### 3.1 PyPSA-Earth is a peer workflow, not a dependency

`pypsa-earth` is not installable from PyPI. It is a Snakemake workflow you
clone, with a conda environment carrying the geospatial stack. The
specification's `pypsa-earth>=0.7.0` line is therefore not implementable as
written.

**Decision.** Alea depends on **PyPSA the library** directly, and treats
PyPSA-Earth as an *external producer of network artefacts*. The seam between
them is **files** — NetCDF networks, GeoJSON topology, CSV profiles — never
Python imports.

**Consequences.**

- Alea stays pip-installable and unit-testable on 3.14. PyPSA-Earth stays on
  whatever Python its conda env needs. The two never share an interpreter.
- Every artefact crossing the seam is versioned and checksummed, so a result can
  always be traced to the network it came from.
- The seam is also where a *replacement* for PyPSA-Earth would go. Nothing in
  Tracks A/B/C above Layer 1 assumes PyPSA-Earth specifically — only that a
  PyPSA network with the documented schema appears.
- Cost: Alea cannot call PyPSA-Earth internals. Where the spec's example code
  reaches into `pypsa_earth.*`, that code must be reimplemented or the artefact
  must carry the data. This is the right trade — internals are where the
  coupling would hurt.

### 3.2 The signal contract is the only Layer 7 boundary

Already true in `src/alea/signals/models.py`. The scanning layer hands
`Signal` objects to everything else and nothing more. This is what makes Track C
independent, and it should be defended: any proposal to have a connector write
directly to a model is a proposal to delete the audit trail.

### 3.3 Artefacts over objects, everywhere

Every stage writes a versioned file and reads versioned files. No stage holds a
live Python object across a boundary. This is what allows Snakemake to schedule
the pipeline, DVC to version it, and any stage to be re-run in isolation — and
it is what makes the "reproducibility to machine precision" validation target
achievable rather than aspirational.

### 3.4 Orchestration: Snakemake calls a library

The specification wants Snakemake rules. The project wants testable code.

**Decision.** `alea` is a library with a CLI. Snakemake rules are thin — they
declare inputs, outputs, and parameters, and shell out to `alea`. No logic lives
in a `.smk` file.

### 3.5 Uncertainty is a field, not a caveat

The specification requires uncertainty-quantified proxy estimates. That is only
honest if uncertainty travels with the datum. Every artefact schema carries
`value`, `uncertainty`, and `provenance` — including for measured data, where
`uncertainty` may be zero. Retrofitting this later means re-deriving every
downstream number.

---

## 4. Stage 0 — Foundations

Nothing in the platform can be trusted until these exist, and every one of them
is cheaper to build now than to retrofit.

| # | Deliverable | Contents | Exit criterion |
|---|---|---|---|
| 0.1 | Config system | Pydantic models over `config/*.yaml`; `extra="forbid"`; scenario overlays in `config/scenarios/` | A typo in a config key fails at load, not at hour 5 of a solve |
| 0.2 | Provenance | `Provenance` model: source, url, retrieved_at, checksum, licence, uncertainty | Every artefact on disk round-trips its provenance |
| 0.3 | Data lake layout | `data/{raw,interim,processed}/<source>/<version>/`; content-addressed; `sources/INDEX.md` | Re-running a download is a no-op when the checksum matches |
| 0.4 | Country registry | ISO-3166 alpha-2 → name, power pool, completeness tier, currency, timezone | Registry count is asserted to equal 55 in a test |
| 0.5 | CI | pytest + ruff + pyright on push; the three gates already pass locally | CI runs the same three commands, and a canary proves the workflow executes |
| 0.6 | DVC | Version `data/` and `resources/`; remotes configured | `dvc repro` on a clean clone reproduces a fixture network |

**On 0.5.** This project's own history is the argument: the `asyncio_mode`
setting was configured with no plugin installed, so it was inert, and on an
async-throughout codebase that means every async test silently passes without
running. A gate that has never been seen to fail is not a gate. Each CI check
gets a canary — a deliberately planted defect that must turn it red — before it
is trusted.

**On 0.4.** The specification's `data-completeness.md` summary table contradicts
its own per-country tables. The tables sum to 55, one row per member state; the
summary undercounts HIGH and MEDIUM and misplaces Eritrea and Equatorial Guinea.
The registry is generated from the tables, and a test asserts the total.

---

## 5. Track A — Physical

### 5.1 Data pipeline (Stage A1)

Ordered by *dependency*, not by the specification's section order — the point is
to reach a solvable network with the fewest sources.

| Step | Source | Why it is at this position |
|---|---|---|
| 1 | World Bank Grid Map | Smallest, most complete topology source; enough for a first network |
| 2 | `powerplantmatching` | One call yields a consolidated fleet; validates the plant schema |
| 3 | AFREC demand | National totals; the denominator for everything |
| 4 | ERA5 cutout + atlite | Renewable profiles; the heaviest download, and the one that gates solar/wind |
| 5 | OSM topology | Replaces/refines the World Bank lines once the network builds |
| 6 | Hydro atlas, geothermal, biomass | Fill the carrier set after the core solves |

**First target: Kenya.** HIGH completeness, the specification's own case study,
and a plausible network size. A Kenya network that solves is the milestone that
de-risks Track A; continental scale is a configuration change applied later.

**The loss decision is not deferrable.** PyPSA-Eur found that neglecting
transmission losses overestimates optimal expansion by ~20%, and losses consume
15–25% of generated energy in many African systems. `transmission_losses` is on
from the first solve. Discovering this after a capacity mix has been published
means republishing it.

### 5.2 Layer 1 — Planning core (Stage A2)

```
alea/planning/
├── network.py        # build a PyPSA network from versioned artefacts
├── topology.py       # Voronoi clustering, bus mapping
├── expansion.py      # multi-horizon CEP
├── dispatch.py       # hourly LOPF
└── schema.py         # the network contract other layers rely on
```

Exit criteria, each checkable:

- A Kenya network solves to optimality with HiGHS.
- Total system cost is reproducible to machine precision across two runs.
- Losses are enabled and non-zero.
- Every component traces to a versioned input artefact.
- Solve time is recorded and compared against the spec's target, scaled for
  hardware — the 6-hour continental target assumes 128 cores; this machine has
  12, so the honest comparison is core-hours, not wall-clock.

**Scale strategy**, since the target tier is unavailable: TSAM time-series
aggregation to representative periods (the spec names this mitigation), spatial
clustering to a 55-bus minimum, and decomposition by planning horizon. Each is
a config switch, and each must be validated by comparing the aggregated result
against a full-resolution solve on a small network — an unvalidated aggregation
is a silent change to the answer.

### 5.3 Layer 2 — Sector coupling (Stage A3)

Hydrogen, heat, transport, industry, water. Deferred until Layer 1 is stable,
because sector coupling multiplies the component count and the debugging
surface. Water is the one to watch: it is where the climate scenarios and the
hydro profiles meet the thermal fleet's cooling demand.

### 5.4 Layer 3 — Market simulation (Stage A4)

```
alea/market/
├── agents.py         # mesa GeneratorAgent
├── clearing.py       # day-ahead market clearing
├── capture.py        # capture prices, capture rates
├── ppa.py            # PPA benchmark curves
└── risk.py           # VaR, CVaR
```

Three sub-decisions, in increasing order of risk:

1. **Capture prices** are arithmetic on a solved network — `(p × price).sum() /
   p.sum()`. Build first; it validates the network schema against a real use.
2. **PPA curves** add tenor, currency, and counterparty adjustments. These are
   financial conventions, not physics, and belong in config with citations.
3. **Agent-based bidding with RL** (mesa + PPO) is the risky one. The
   specification cites AMIRIS/ASSUME achieving 5.6–6.4 €/MWh MAE. That is the
   benchmark: an RL bidding agent that does not beat a naive markup rule on a
   known network is not an improvement, and should be reported as such rather
   than shipped. **Build the naive rule first and keep it as the baseline.**

### 5.5 Layer 5 — What-if engine (Stage A5)

Parameterised re-solve with caching and efficient frontiers. Depends on A2 and
A4. The spec's `_cache_key` uses `hash(tuple(sorted(...)))`, which is not stable
across processes — Python randomises string hashing per interpreter. Use a
content hash of the parameter dict, or cached results silently miss and, worse,
the reproducibility test passes for the wrong reason.

---

## 6. Track B — Predictive

### 6.1 Layer 4a — Outage prediction (Stage B1)

Independent of Track A. This is the track that can produce a validated,
publishable result soonest.

```
alea/outages/
├── viirs.py          # VIIRSOutageDetector
├── baseline.py       # VZA-grouped, per-(pixel, bin, month) baseline
├── forecaster.py     # OutageForecaster (weather-driven)
├── maintenance.py    # Cox survival
└── validate.py       # AUC, precision/recall against ground truth
```

**The method is the deliverable.** Group observations by Viewing Zenith Angle
bin; establish the baseline as the first quartile of radiance per (pixel, VZA
bin, month); flag when radiance falls below a fraction of baseline. The first
quartile is robust to bright transient events (lunar reflection, fires) while
preserving sensitivity to darkening. This is the single largest accuracy lever
in the literature the specification cites, and it is also the step most likely
to be skipped by someone reaching for a simpler threshold. It gets a dedicated
test with synthetic data of known VZA dependence.

**Honest limits, to be recorded in config and in every output:** one observation
per day at ~01:30 local, so short outages are invisible; tropical cloud cover
blocks detection; the method works best for large outages spanning multiple
pixels. These are not caveats to bury — an outage forecast that cannot see
six-hour outages must say so on the report that carries it.

**Ground truth is the binding constraint.** GridWatch covers Greater Accra with
147 sensors; the specification's other validations (Johannesburg, Adrar) are
single studies. A model validated only on Ghana is a model validated on Ghana.
The validation module must report *which* ground-truth set produced any given
metric, and the report layer must not generalise it.

### 6.2 Layer 4b — Losses, TLENS, resilience (Stage B2)

Needs Track A. Loss decomposition, N-1 contingency, TLENS ranking, mitigation
ranking, and the resilience metrics (ENS, EENS, SAIDI, SAIFI).

Two traps in the specification's own sample code:

- `ContingencyAnalyser.compute_tlens` mutates `self.n.lines` in place and
  restores it in the same loop. An exception mid-loop leaves a line permanently
  deactivated. Use a copy per contingency.
- `LossDecomposer._topology_driven` returns a hardcoded `0` placeholder. A
  decomposition whose components do not sum to the total is worse than no
  decomposition; either implement it or raise.

### 6.3 Layer 6 — Reporting (Stage B3, extends to all tracks)

Depends on whatever it reports on, so it lands last but is built as a framework
early: a report is a template plus a data contract, and the contract can be
written and tested against fixtures before the data exists.

The daily report's outage section is the first real one, because Track B
finishes first. That gives a working end-to-end delivery channel — generate,
render to PDF, distribute — while Track A is still solving.

---

## 7. Track C — Intelligence scanning

Independent of everything. The signal contract already exists.

```
alea/scanning/
├── connectors/       # base + news, tender, social, institutional
├── ingestion/        # scheduler, exact-hash dedup, MinHash/LSH near-dup
├── extraction/       # LLM signal extraction, scoring
├── review/           # review queue
└── integration/      # signal → model update handlers
```

Build order is the reverse of the data flow: **review queue first**, then
integration, then extraction, then connectors. Reason: the review queue and the
integration handlers are the parts with real invariants (a signal is confirmed
exactly once; a model update is idempotent; a rejected signal never reaches a
model), and they can be built and tested entirely against synthetic signals.
Connectors are the least risky and the most numerous, and they are the part
that rots fastest as upstream sites change — so they go last, behind a stable
interface, and each one is cheap to replace.

**Non-negotiables, because they are the difference between an intelligence
system and a rumour engine:**

- Every signal carries `evidence_quotes`. An extraction with no supporting quote
  is rejected at construction, not reviewed.
- `requires_review=True` by default and the default is not overridable by a
  connector.
- Model updates are idempotent and logged with the signal that caused them.
- The review queue records *rejections* with reasons. Precision and recall are
  both measured against human decisions; without rejection reasons, recall is
  unmeasurable.

---

## 8. Layer 8 — API and delivery

REST API plus dashboard. Built last for the analytical layers, but the API
*schema* is derived from the layer contracts, so it can be drafted as each layer
lands rather than retrofitted.

Two specification issues:

- `GET /api/v1/outages/forecast` takes a Pydantic model as a GET parameter. That
  is not how FastAPI binds query parameters; it needs `Depends()` or individual
  query params.
- The spec's `verify_key` is defined but the endpoints in the example reference
  `VALID_KEYS` and `os` without imports. Treat the API section as a sketch.

Beyond REST, the strategy specification lists seventeen more channels
(WhatsApp, USSD, SMS, widgets, Excel, QGIS, Zapier…). These are **delivery
adapters over one API**, not separate systems. Building the API so that a USSD
menu and a Bloomberg-style terminal read the same endpoints is the whole
architecture; anything else produces seventeen codebases.

---

## 9. Milestones with checkable gates

Each gate is a command with an expected outcome, and each is canaried once
against a known-bad input before it is trusted.

| # | Milestone | Gate |
|---|---|---|
| M0 | Foundations | `uv run pytest` green; CI red on a planted defect |
| M1 | Kenya network solves | Optimality asserted; two runs agree to 1e-6; losses non-zero |
| M2 | VIIRS detection validated | AUC > 0.80 on held-out ground truth; VZA correction demonstrably reduces false positives vs. uncorrected baseline |
| M3 | Signal pipeline end-to-end | Synthetic document → connector → extraction → review → one model update, with provenance intact |
| M4 | Capture prices | Capture rate in (0, 1] for every generator; revenue-weighted price below time-weighted for VRE |
| M5 | Power-pool scale | EAPP (~5 countries) solves within the recorded budget |
| M6 | First daily report | PDF generated from real Track B output and distributed |
| M7 | Continental CEP | Runs on deployment hardware; local core-hour estimate recorded |
| M8 | Market simulation | RL bidding agent compared against the naive-rule baseline, and the comparison published whichever way it falls |

**M2's second clause matters more than the first.** An AUC above 0.80 proves the
model works. Only the A/B against an uncorrected baseline proves the *VZA
correction* is why — and that is the claim the specification makes.

**M8 is written to allow a negative result.** The specification assumes RL
beats naive bidding. If it does not on real networks, that is the finding.

---

## 10. Cross-cutting work

**Testing.** `tests/ci/` is the autodiscovery path. No mocks except LLM calls;
`pytest-httpserver` for HTTP. Every gate needs a canary. The project's own
history has five separate instances of a check that passed because it never ran
— a `case` inside a command substitution, a bash variable named `GROUPS`
shadowing the shell's, a workflow in a directory GitHub does not read, an
inert `asyncio_mode`. Assume any new gate is broken until it has been seen to
fail.

**Data versioning.** DVC over `data/` and `resources/`. Raw data is immutable
and content-addressed; nothing writes to `data/raw/` twice.

**Provenance.** Every artefact carries source, retrieval timestamp, checksum,
licence, and uncertainty. `sources/INDEX.md` records citations, per the project
convention that a load-bearing citation gets an archived local copy — the
specification's own data inventory contains several placeholder links
(`zenodo.org/records/` with "search for AfREP-Hydro") that will rot.

**Uncertainty.** CRITICAL-tier countries (Burundi, Cabo Verde, Comoros,
Djibouti, Mauritania, Seychelles, São Tomé) are absent from continental
datasets. Proxy estimates for them are labelled as proxies in the output, not
silently blended with measured data — otherwise a report cannot distinguish
"modelled from WorldPop" from "reported by the utility".

**Licensing.** The strategy specification proposes CC BY 4.0 / ODbL for outputs.
The inputs have their own licences (OSM is ODbL, GEM is CC BY 4.0, ERA5 has
Copernicus terms). Output licensing must be checked against input licensing
before anything is published as open data.

---

## 11. What would falsify this plan

Stated so it can be checked rather than assumed:

1. **If PyPSA-Earth's artefact schema cannot carry what Layer 3 needs** (e.g.
   marginal prices at the resolution capture-price analysis requires), the
   file seam is wrong and Layer 1 must own more of the network construction.
   *Check at M1.*
2. **If VIIRS detection does not reproduce the published AUC** on data obtained
   independently, the method may not transfer, and Track B's fastest path is
   gone. *Check at M2.*
3. **If a Kenya network cannot solve on 12 cores / 96 GB** at hourly resolution
   for four horizons, then the local development loop is broken and the plan
   needs a remote-HPC story from Stage 0 rather than from M7. *Check at M1.*
4. **If LLM extraction precision lands below 90%** against human review, the
   human review queue becomes the bottleneck rather than the safety net, and the
   auto-confirm threshold in the specification's risk table has to be designed
   rather than deferred. *Check at M3.*

---

## 12. Recommended first three weeks

1. **Stage 0** in full — config, provenance, registry, CI with canaries, DVC.
   Nothing else is trustworthy without it, and it is days, not weeks.
2. **Track C's review queue and integration handlers**, against synthetic
   signals. They are pure logic with real invariants and no external
   dependencies, so they can be finished while data downloads run.
3. **Track B's VIIRS ingestion and the VZA baseline**, on a single country, with
   the A/B against an uncorrected baseline built in from the start.

That sequence produces, in three weeks, a tested signal pipeline and a
validated outage detector on one country — two of the platform's three riskiest
capabilities — without waiting on a single data-sharing agreement or a
continental solve.
