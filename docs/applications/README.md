# Grant applications for ALEA

Drafted 2026-11-25 from `docs/research/alea-funding-global/` (third sweep). One directory per call.

| Directory | Call | Value | Deadline | Applicant |
|---|---|---|---|---|
| `nlnet/` | NLnet open call | EUR 5k to 50k (request: EUR 37,500) | 3 Jan 2027, 12:00 CET | Individual |
| `research-software-catalyst-fund/` | Research Software Catalyst Fund, exploratory | up to US$50k (request: US$45,000) | 31 Dec 2026 | Individual or informal team. Not Datacraft: the fund excludes companies |
| `mozilla-fellowship/` | Mozilla Foundation Fellowship 2027, Track II Independent | up to US$125k over 12 months (as reported, see below) | letter of intent 17 Dec 2026, 11:59 PM PST | Individual |

Each directory holds `README.md` (the grant, value, dates, eligibility, fit, checklist), `application.md` (introduction, concept note and the answers in the funder's own form order) and `use-of-funds.md` (budget by data acquisition, system development and research).

## Read this before submitting anything

1. **The answers are written to be pasted, then amended.** NLnet requires proposals "made by humans, not AI" and asks for a disclosure; Mozilla warns that heavily AI-generated applications get further review and asks for a disclosure. The facts, numbers and structure are checked against the repository. Read each answer once and change what you would say differently. The disclosure text in each file says an AI assistant drafted the answers and you reviewed and amended them; that is true as written, so change it only if you change how you worked.
2. **Every `[ ]` or `[APPLICANT: ...]` marker is a fact only you can supply** (email, experience band, examples, outcomes). None has been guessed. Run `python3 docs/applications/check_limits.py docs/applications/nlnet/application.md` after amending: it fails if an NLnet answer exceeds its limit.
3. **Budget rates and unit prices are assumptions**, labelled as such in each `use-of-funds.md`. Replace them with your own rate and real quotes. Totals are arithmetic on those assumptions and re-add when you change one.
4. **The three calls do not stack.** Mozilla asks which other programmes you applied to; the Catalyst Fund asks you to disclose related proposals. List all three in each. The work packages overlap on purpose (the same graph hardening is the core of each) so that one award completes the work and the others extend it. If two are awarded, split the scope; do not bill one task twice.
5. **State what is not done.** Each draft says that only 7.4% of the graph's settable parameters reach the solver, that no full-year Kenya solve exists, and that the ten claims in the unverified register are unverified. A reviewer who checks the repository will find them; a draft that hides them fails the first check.

## Facts used, and where they come from (measured 2026-11-25)

| Fact | Source |
|---|---|
| 1,881 parameters, 841 equations, 17 systems, 1,993 edges, 57 cross-validation rules, 43 bound inequality routes, 2 feedback loops | `uv run alea prg summary` |
| 841 of 841 equations dimensionally consistent, 3 exempt by declaration | `uv run alea prg units` |
| 108 citations registered, 39 archived on disk, 43 unarchived works | `uv run alea prg citations` |
| 81 of 1,095 settable parameters reach the solver (7.4%); 7 of 10 engine fields named by no parameter | `scripts/measure_prg_engine_coupling.py` |
| 1,656 tests; 142 of 142 promised gates have a test and a canary; 68 canary test files | `pytest --collect-only`, `scripts/gate_register.py`, `tests/ci/canaries/` |
| Default scenario fails its own check (frequency nadir 43.6 Hz against a 45 to 50 range) | `uv run alea prg check` |
| A hand-set derived parameter is silently discarded | probe in `docs/plans/15-completion.md` D1 |
| Kenya model solves to optimality on windows up to 91 days; full year not done | `docs/research/alea-funding/enaccess-email.md`, `docs/plans/14-roadmap.md` M1 |
| Ten claims on the unverified register, all unverified | `uv run alea quality claims` |
| Licence MIT; 371 commits since 2026-10-11 | `pyproject.toml`, `git log` |
| The codebase contains a large amount of AI-generated code (built with Claude Code) | disclose this on every form that asks |

The plan these applications fund is `docs/plans/15-completion.md`.
