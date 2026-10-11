# 13 — Deployment and Operations

**Before production.** Hardware, containers, orchestration, and the operational
practices that keep a continental model reproducible.

---

## 1. The hardware reality

**Development machine (verified): 12 cores, 96 GB RAM, 173 GB free disk.**

The specification's tiers assume far more:

| Tier | Spec CPU | Spec RAM | Spec storage |
|---|---|---|---|
| National | 32 | 128 GB | 2 TB SSD |
| Power pool | 64 | 256 GB | 4 TB NVMe |
| Continental | 128 | 512 GB | 10 TB NVMe |
| Training | 32 + A100 | 128 GB | 2 TB SSD |
| Reporting | 16 | 64 GB | 1 TB SSD |

**Consequence, stated plainly: continental scale is a deployment concern, not a
development one.** Everything is built correct at Kenya scale and made
deployable at continental scale through configuration. The local loop must never
require a continental solve (`00-architecture.md` §2).

---

## 2. What runs where

| Workload | Where | Why |
|---|---|---|
| Development, tests, Kenya solves | Laptop (12 cores) | Must stay under minutes |
| Sector-coupled Kenya | Laptop, aggregated | Validated aggregation (AD-9) |
| Continental preprocessing | 64+ core node | PyPSA-Earth, Voronoi, ERA5 |
| Continental CEP | 128 cores / 512 GB | The specification's own target |
| VIIRS archive processing | 32+ cores, high I/O | 10⁹ pixels/day |
| ML training | GPU node | xgboost/lightgbm |
| Scanning | Small always-on node | Continuous, low CPU |
| API, reporting | Small node | Latency-sensitive, low CPU |
| Storage | 10 TB NVMe + object store | Raw archives + artefacts |

**One machine cannot do all of it.** The scanning layer is always-on and
low-resource; the continental solve is bursty and huge. Co-locating them means
either an idle 128-core machine or a scanning service that starves.

---

## 3. Containers

### 3.1 Two images, because there are two toolchains (AD-1)

```dockerfile
# Dockerfile.alea — the platform
FROM python:3.14-slim AS build
RUN pip install maturin
COPY rust/ /build/rust/
COPY Cargo.toml rust-toolchain.toml /build/
RUN cd /build && maturin build --release --out /wheels

FROM python:3.14-slim
COPY --from=build /wheels/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl
COPY src/ /app/src/
COPY config/ /app/config/
ENTRYPOINT ["alea"]
```

```dockerfile
# Dockerfile.pypsa-earth — the external workflow (AD-1)
FROM condaforge/mambaforge
RUN mamba create -n pypsa-earth -c conda-forge python=3.11 pypsa-earth
# pinned to v0.9.0
```

**They never share an interpreter.** The seam is files: PyPSA-Earth writes
NetCDF/GeoJSON/Parquet into a mounted volume; ALEA reads them. This is AD-1
enforced by construction — there is no import path between the images.

### 3.2 Why the ALEA image installs a wheel, not a source tree

The wheel is built with `abi3-py312`, so one wheel serves every supported Python
(`03-rust-core.md` §1). Installing from source in the runtime image would need
the Rust toolchain in production, which is 1.5 GB of image for a build that
happened once.

### 3.3 Pinned base images

`python:3.14-slim` is pinned by digest, not tag. A tag moves; a digest does not.
The same applies to `condaforge/mambaforge`. A deployment whose base image
changed between two builds is a deployment that cannot reproduce its own output.

---

## 4. Orchestration

### 4.1 The pipeline

Snakemake schedules the batch pipeline; every rule shells out to `alea` (AD-5).
Snakemake's value here is dependency resolution and re-run-on-change, not logic.

```
fetch_*  →  build_*  →  solve_*  →  analyse_*  →  report_*
```

### 4.2 The always-on services

| Service | Cadence | Restart policy |
|---|---|---|
| Scanning scheduler | Continuous | Always |
| Report scheduler | Cron (5 cadences) | Always |
| API | Continuous | Always |
| Job worker | Continuous | Always |
| Pipeline (Snakemake) | On trigger | On failure, bounded |

**Bounded restart on the pipeline.** An unbounded restart of a failing
continental solve is a machine that spins for a week. Three attempts, then
alert.

### 4.3 Job durability

Long solves run as **jobs with durable state** (`11-layer8-api.md` §3.2), not
inline. A two-hour solve that dies with its process is a solve whose result
nobody learns about.

---

## 5. Data

### 5.1 Storage tiers

| Tier | Contents | Medium |
|---|---|---|
| Raw archive | VIIRS granules (streamed, not kept), ERA5 cutouts | Object store |
| Processed | Versioned artefacts | NVMe |
| Results | Solved networks, reports | NVMe + object store |
| Scratch | Intermediates | Local NVMe, purgeable |

**VIIRS granules are streamed and discarded** (`02-data-pipeline.md` §1.1). Only
their checksums and the extracted statistics are retained. Keeping a
country-year of VNP46A2 is thousands of ~100 MB files for data that has already
been reduced.

### 5.2 DVC

`data/raw`, `data/processed`, and `resources` are DVC-tracked. `dvc repro` on a
clean clone reproduces the Kenya fixture network checksum exactly.

**Gate:** a canary perturbs an input and asserts the checksum changes. A
reproducibility gate that passes on a perturbed input is a gate that is not
checking anything.

### 5.3 Backup

| Data | Backup | Retention |
|---|---|---|
| Raw archive | Object store, versioned | Permanent |
| Processed artefacts | Object store | Permanent (regenerable but expensive) |
| Results | Object store | Permanent |
| Configuration | Git | Permanent |
| Review queue (SQLite) | Daily snapshot | 90 days |

**The review queue is the only irreplaceable operational state.** Everything else
is either in git or regenerable. Analyst review decisions exist nowhere else, so
they are backed up separately and tested by restore.

---

## 6. Operations

### 6.1 The rules that apply here

These are the operational lessons this project's history has already paid for:

- **Timestamped backup before editing shared production config:**
  `cp f f.bak.$(date +%Y%m%d-%H%M%S)`.
- **Caddy: `caddy validate` before `reload`, never `restart`.**
- **Never gate a deploy on `cmd | tail -N`** — the pipe returns tail's exit code,
  masking build failure. Capture to a log and check the build's own status.
- **Never read a database answer through `| tail -N`** — the summary line is the
  last one.
- **A reconciliation script that measures nothing must fail, not report
  success.** An unset `DATABASE_URL` produced a clean "0 mismatches" report from
  a 4-column default database. Refuse when the variable is unset.
- **Do not kill processes on a shared host because they look like scratch.**
  Check creation time (`ps -o lstart`, `tmux capture-pane`); a process older
  than the session is not yours.
- **Never rewrite an applied database migration** — add a new revision. An
  in-place edit keeps the revision ID, so every database that ran the old body
  stays stamped there and `upgrade head` skips the new DDL.
- **`alembic check` against the deployed database**, not a from-migrations one.
  A drift gate comparing the ORM to a fresh database is blind to a rewritten
  revision.

### 6.2 Health and observability

- **Run ids.** Every invocation generates a UUID7 run id, threaded through logs,
  artefact provenance, and report footers (`00-architecture.md` §8). This is
  what makes "which run produced this number" answerable.
- **Structured logging** via `structlog`; JSON in production.
- **`/health`** reports the API, the job store, the artefact store, and the last
  successful pipeline run.
- **A report that was generated but not delivered is a report that was not
  published** (`09-layer6-reporting.md` §5). Delivery is recorded per channel.

### 6.3 Alerting

| Condition | Severity |
|---|---|
| Pipeline failed after bounded retries | Page |
| Scheduled report not delivered | Page |
| Artefact checksum mismatch | Page |
| Connector `layout_changed` | Ticket |
| GridWatch validation skipped (no token) | Ticket |
| Determinism job failed | Page |

**A skipped validation is a ticket, not a silent pass.** The platform must never
report a model as validated when the ground truth was unavailable.

---

## 7. Security

| Concern | Control |
|---|---|
| API keys | Hashed (argon2), tiered, revocable (`11-layer8-api.md` §4) |
| Credentials | Environment only, validated at load |
| LLM output | Validated against `Signal` constraints (`10-layer7 §5.2`) |
| Document text | Treated as untrusted; prompt injection tested |
| Downloaded archives | Own empty directory, scripts elsewhere, `python -I` |
| Review queue | SQLite, append-only, backed up |
| Social media retention | 90-day default, config |

**Downloaded files are untrusted data.** Extract into a new empty directory, keep
scripts elsewhere, pass paths as arguments, and run any Python that reads them
with `-I` — interpreters load code from the script directory and the current
directory, so a planted `json.py` runs on `import json`.

---

## 8. Cost

| Resource | Configuration | Purpose |
|---|---|---|
| Laptop | 12 cores / 96 GB | Development, Kenya |
| Compute node | 64 cores / 256 GB | Continental preprocessing, sector coupling |
| Large node | 128 cores / 512 GB | Continental CEP (specification's target) |
| GPU node | 1× A100 | ML training |
| Always-on | 8 cores / 32 GB | Scanning, API, reporting |
| Storage | 10 TB NVMe + object store | Archives and artefacts |

**The always-on node is the cheapest and the most important.** Scanning, the
API, and reporting are what make the platform a product rather than a
spreadsheet; the continental solve is what makes it authoritative. Both are
needed and they have nothing in common operationally.

**Solver licensing is a real cost.** HiGHS is the default and is MIT-licensed.
Gurobi is required above ~5M variables, which continental sector-coupled
problems exceed. The plan's position: negotiate academic licensing, and where it
is unavailable, use aggregation (AD-9) to fit HiGHS rather than ship a result
nobody can reproduce.

---

## 9. Exit criteria for deployment

| # | Criterion | Gate |
|---|---|---|
| 1 | ALEA image builds and runs on a clean host | CI build |
| 2 | PyPSA-Earth image builds separately; no shared interpreter | Build test |
| 3 | The seam is files only; ALEA runs with PyPSA-Earth absent | CI job |
| 4 | `dvc repro` reproduces the Kenya fixture | Checksum match |
| 5 | Every long job survives a process restart | `test_job_survives_restart` |
| 6 | Review queue restore tested | Restore drill |
| 7 | Delivery recorded for every channel | `test_delivery_recorded` |
| 8 | Determinism job passes in the deployed image | CI |
| 9 | Base images pinned by digest | Build config review |
| 10 | Alerting fires on a planted failure | Canary |

**Criterion 10 is a canary in production.** Kill the pipeline deliberately in a
staging environment and confirm the alert fires. An alert path that has never
been exercised is an alert path that does not exist.
