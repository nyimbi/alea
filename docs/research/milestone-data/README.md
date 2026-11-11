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
| 365 days | 8,760 | not finished after more than 1 h in simplex | | | |

The 14-day run balanced dispatch against load plus losses (losses 32,961 MWh against 405,380 MWh load, 8.1 %).
The first full-year attempt was infeasible: 2,007 MW firm capacity against a peak of about 1,920 MW with losses, and only variable candidates.
Caveats: annualised capex is charged against a sub-year window, so the objective is not an annual cost; hydro has no energy limit; fleet coverage is 77 %, below the plan's 90 %.
M1 is met on a 91-day window; the full-year clause stays open until that solve returns.
