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
