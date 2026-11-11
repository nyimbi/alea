# What the M1/M2/M8 validation targets need, and what blocks each (probed 2026-11-11)

`scripts/quality/milestone_artefacts.py` records a skip for seven targets. This
is what unblocks each. Nothing below was downloaded; the search results were not
archived, so treat the pointers as leads, not citations.

| Target | Needs | Blocker found |
|---|---|---|
| `kenya_expansion`, `kenya_demand`, `loss_approximation` | A Kenya network `.nc` from the PyPSA-Earth workflow (AD-1 file seam) | No conda/mamba/micromamba/pixi on this host; ERA5 cutout needs a CDS API key (`~/.cdsapirc` absent). Snakemake 9.27.0 and `cbc` are present. A build is a multi-hour, multi-GB run. |
| `viirs_detection`, `weather_forecasting` | GridWatch Ghana sensor data | nLine's public-data page issues an API key through a signup form; the key has to come from the account owner. ICPSR/MCC also hosts site-level GridWatch sensor sets (Ghana Power Compact baseline/endline, line bifurcation), reachable through its catalogue. VIIRS granules need NASA Earthdata credentials, also absent. |
| `south_africa_capture_prices` | "COMPASS" capture-price series | Search found no dataset or model with that name. Until the plan says who publishes it, there is nothing to fetch. Meridian Economic's annual South Africa power market report carries capture prices but is a commercial report. |
| `malawi_tlens` | Expert line ranking | Not searched; not public as far as the plan says. |

Leads: https://nline-7adlglt9b-nline.vercel.app/public-data (a Vercel preview, not the canonical host), https://mcc.icpsr.umich.edu/evaluations/index.php/catalog/28952, https://github.com/pypsa-meets-earth/pypsa-earth.

Credentials needed from the account owner: nLine API key, Copernicus CDS key, NASA Earthdata login. Decision needed: what COMPASS is.

Saved pages: `downloads/` (SHA256SUMS inside). Fetched 2026-11-11; the nLine preview-host and Zenodo API URLs failed (410/403) and were replaced by nline.io/public-data and the Zenodo record page. nLine says the API key is issued on first `fetch_data()` run via a signup prompt.

## Kenya input lake (M1)

Built by `scripts/build/kenya_{topology,inputs,profiles}.py`; checked by `scripts/quality/kenya_m1.py`.

| Input | Source | Archived at | Licence | Caveat |
|---|---|---|---|---|
| Topology | OSM `power=line` ways via Overpass, 66 kV and up, largest component | `osm-kenya/lines.json` | ODbL | OSM completeness; 110 lines, 6,944 km |
| Fleet | WRI GPPD v1.3, KEN rows | `gppd/` | CC BY 4.0 | 23 plants, 2,486 MW = 77 % of the 3,243.6 MW KNBS 2023 installed capacity; the plan asks for over 90 % |
| Demand | KNBS 2024 Economic Survey, 10,320.6 GWh (2023), read from a press summary | not archived | Publisher | Town populations are from memory and unverified; the hourly shape is stylised |
| Costs | PyPSA technology-data 2030/2040/2050 | `technology-data/` | per file | EUR to USD at 1.14; no geothermal-electricity capex row, so no geothermal candidate |
| Profiles | Open-Meteo archive (ERA5-derived), 95 points, 2023 | regenerable, git-ignored | CC BY 4.0 | Stand-in for the atlite cutout, which the CDS queue blocks; generic cubic wind curve and temperature-derated solar |

### Kenya M1 result (`scripts/quality/kenya_m1.py`)

| Window | Snapshots | Status | Two-run objective diff | Solve | Core-hours |
|---|---|---|---|---|---|
| 14 days, no gas candidates | 336 | optimal | 0.0 | 10 s | 0.003 |
| 91 days, gas candidates at every bus | 2,184 | optimal | 0.0 | 370 s | 0.103 |
| 365 days, dual simplex | 8,760 | stopped at the 3,600 s time limit; not optimal (reported objective 140,899 against 17,561,408 recomputed from dispatch) | n/a | 3,672 s | 1.02 (not a solution) |
| 365 days, interior point | 8,760 | stopped by hand after 6 iterations in 2,400 s (about 300 s each) | n/a | | |

The 14-day run balanced dispatch against load plus losses (losses 32,961 MWh against 405,380 MWh load, 8.1 %).
The first full-year attempt was infeasible: 2,007 MW firm capacity against a peak of about 1,920 MW with losses, and only variable candidates.
Caveats: annualised capex is charged against a sub-year window, so the objective is not an annual cost; hydro has no energy limit; fleet coverage is 77 %, below the plan's 90 %.
M1 is met on a 91-day window; the full-year clause stays open until that solve returns.

### Kenya capture rates, 30-day window (M4 probe)

Nodal `marginal_price` from the solved expansion network, capture rate per generator that dispatched (`alea.market.capture.capture_rate`):

| Carrier | Generators | Capture rate min / median / max |
|---|---|---|
| hydro | 8 | 1.000 / 1.005 / 1.139 |
| geothermal | 5 | 1.414 / 2.387 / 6.479 |
| oil | 3 | 3.211 / 6.365 / 6.504 |
| gas (new candidates) | 5 | 1.237 / 1.237 / 1.237 |
| onwind | 2 | 1.000 / 1.000 / 1.000 |
| solar | 1 | 1.000 / 1.000 / 1.000 |

Price range: min -5.06, median 7.17, mean 26.6, max 47,091.6 USD/MWh.

Two findings. (1) M4 as worded ("capture rate in (0, 1] for every generator") cannot hold: peakers and firm plant sell into scarcity hours, so their capture rate exceeds 1 by construction. The defensible clause is a VRE-only one, capture rate at most 1 (revenue-weighted below time-weighted). (2) The VRE rates here are exactly 1.000, not below 1: those plants sit at buses whose price is flat while they run, so the model shows no cannibalisation yet. A strict "below" clause would fail on this network. The 47,091 USD/MWh maximum is a shadow price on a binding capacity or line constraint with no load-shedding cost to cap it; it is a model artefact, not a market price, and it dominates the mean.

The full-year clause of M1 is open. On one thread, HiGHS does not reach optimality on 8,760 snapshots within the 1 h limit, by simplex or interior point. The remaining routes are the AD-9 time aggregation (needs its validation artefact for Kenya) or the Rust core on more cores; the plan's 6 h target assumes 128 cores and this machine has 12.
The earlier 'M1 PASS' lines for the full year were wrong: `solve_expansion` accepted a time-limit stop as optimal until commit 6f2d576.
