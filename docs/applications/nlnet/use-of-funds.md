# NLnet use of funds

Request: **EUR 37,500**. Rate: **EUR 50 per hour, an assumption** [APPLICANT: replace with your rate and re-add]. 720 hours, plus EUR 1,500 expenses.

## 1. Data acquisition: EUR 7,500

| Task | Hours | EUR |
|---|---|---|
| Archive the 43 unarchived cited works, record SHA-256, add to `sources/INDEX.md` | 40 | 2,000 |
| Kenya hourly weather-year profiles (wind, solar, hydro inflow proxy) from ERA5 via atlite, with provenance record | 50 | 2,500 |
| Kenya transmission topology from OpenStreetMap, checked against published line lists, with provenance | 30 | 1,500 |
| Cloud compute for atlite processing (expense) | | 1,000 |
| Access to paywalled cited sources (expense) | | 500 |
| **Subtotal** | **120** | **7,500** |

Output: versioned datasets on Zenodo (CC BY, ERA5 and OSM terms recorded), 43 archived sources.

## 2. System development: EUR 20,000

| Task (plan ref `docs/plans/15-completion.md`) | Hours | EUR |
|---|---|---|
| T1 refuse hand-set derived values and unknown names in `propagate` (D1, D2) | 60 | 3,000 |
| T2 intervention operator, with the two feedback loops handled (D5) | 80 | 4,000 |
| T3 default scenario passes `alea prg check` (D3) | 40 | 2,000 |
| T4 solver coupling above the 7.4% baseline, each added parameter behind an optimality test (D4) | 160 | 8,000 |
| T5 pyright and ruff clean (D8, D9) | 60 | 3,000 |
| **Subtotal** | **400** | **20,000** |

Gates: the probe in D1 now raises; `alea prg check` exits 0; the coupling script prints a higher count than 81 of 1,095; pyright and ruff exit 0; each gate has a canary.

## 3. Research: EUR 10,000

| Task | Hours | EUR |
|---|---|---|
| T6 full-year Kenya solve: decomposition or aggregation, solve time and optimality gap reported (D7) | 100 | 5,000 |
| T6 the 10 unverified claims: source or re-run each, publish pass or fail (D6) | 60 | 3,000 |
| Sensitivity report: which parameters move the solve | 40 | 2,000 |
| **Subtotal** | **200** | **10,000** |

## Total

| | EUR |
|---|---|
| Labour, 720 h at 50 | 36,000 |
| Expenses | 1,500 |
| **Total** | **37,500** |

Not funded here: the documentation debt and honest closeout items (T7, T8), unless time remains.
