# PyPSA-X Pan-African: Comprehensive Product Specification

## An Open-Source, Extensible Platform for Continental Energy System Planning, Predictive Operations, Market Simulation, and Periodic Intelligence Reporting

**Version**: 2.0
**Status**: Draft for Developer Implementation
**Audience**: Intermediate Python developers with energy system modelling experience
**Base Platform**: PyPSA-Earth v0.7.0+ (PyPSA v1.0+)
**Supersedes**: Version 1.0 (Planning-Only Specification)

---

## Part I: Vision, Scope, and Architectural Shift

### 1. Why This Specification Was Rewritten

Version 1.0 of this specification defined a **planning model** — a platform for capacity expansion, market simulation, and investment analytics over multi-year horizons. That scope is necessary but insufficient. The platform must also:

1. **Predict outages** before they happen, using satellite data (NASA VIIRS Black Marble), weather forecasts, and machine learning, because African grid operators and their customers need early warning, not just long-term plans.
2. **Mitigate transmission losses** by decomposing losses, identifying critical corridors (TLENS), and ranking mitigation options, because losses consume 15–25% of generated energy in many African systems.
3. **Enable what-if scenario planning** through interactive parameter adjustment, rapid re-solve, and efficient frontiers, because decision-makers need to explore futures, not accept a single projection.
4. **Produce periodic intelligence reports** (daily, weekly, monthly, quarterly, annual) that translate model outputs into actionable briefings for utilities, regulators, investors, and policymakers.

The platform is therefore repositioned as a **full lifecycle decision-support system**: from long-term planning through operational forecasting to periodic reporting.

### 2. The Six Analytical Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 6: Periodic Reporting & Intelligence                         │
│  (Daily/weekly/monthly/quarterly/annual reports, alerts, digests)   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 5: What-If Scenario Engine                                   │
│  (Interactive parameters, rapid re-solve, efficient frontiers)      │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 4: Outage Prediction & Resilience Analytics                  │
│  (VIIRS/Black Marble, ML models, contingency analysis, TLENS)       │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: Market Simulation & Commercial Analytics                  │
│  (Agent-based bidding, capture prices, PPA curves, risk metrics)    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Sector-Coupled Optimisation                               │
│  (Electricity, hydrogen, heat, transport, industry, water)          │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: PyPSA-Earth Planning Core                                 │
│  (Capacity expansion, multi-horizon, all renewable technologies)    │
└─────────────────────────────────────────────────────────────────────┘
```

**Why this layering**: Each layer depends only on the layers below it. Layer 1 provides the physical network. Layer 2 adds sector coupling. Layer 3 adds market dynamics. Layer 4 adds predictive and resilience analytics. Layer 5 adds interactivity. Layer 6 adds delivery. This separation ensures independent development, testing, and deployment.

---

## Part II: Repository and Development Environment

### 3. Repository Structure

```
pypsa-x-pan-african/
├── Snakefile
├── config/
│   ├── config.default.yaml
│   ├── config.africa.yaml
│   ├── config.sector.yaml
│   ├── config.predictive.yaml          # NEW: outage + loss + resilience
│   ├── config.whatif.yaml              # NEW: scenario engine
│   ├── config.reporting.yaml           # NEW: periodic reports
│   └── scenarios/
├── rules/
│   ├── download.smk
│   ├── build_africa.smk
│   ├── build_sector.smk
│   ├── build_predictive.smk            # NEW
│   ├── solve.smk
│   ├── solve_market.smk
│   ├── solve_stochastic.smk
│   ├── solve_resilience.smk            # NEW
│   ├── whatif.smk                      # NEW
│   ├── delivery.smk
│   └── reporting.smk                   # NEW
├── scripts/
│   ├── download/
│   │   ├── download_africa_data.py
│   │   ├── download_viirs.py           # NEW
│   │   ├── download_era5.py
│   │   └── download_gridwatch.py       # NEW
│   ├── build/
│   │   ├── build_topology.py
│   │   ├── build_powerplants.py
│   │   ├── build_renewables.py
│   │   ├── build_demand.py
│   │   ├── build_outage_history.py     # NEW
│   │   └── build_sector_network.py
│   ├── predict/
│   │   ├── train_outage_model.py       # NEW
│   │   ├── predict_outages.py          # NEW
│   │   ├── detect_viirs_outages.py     # NEW
│   │   └── predictive_maintenance.py   # NEW
│   ├── analyse/
│   │   ├── decompose_losses.py         # NEW
│   │   ├── rank_mitigations.py         # NEW
│   │   ├── contingency_analysis.py     # NEW
│   │   └── resilience_metrics.py       # NEW
│   ├── solve/
│   │   ├── solve_network.py
│   │   ├── solve_market.py
│   │   ├── solve_stochastic.py
│   │   └── solve_whatif.py             # NEW
│   ├── report/
│   │   ├── generate_daily.py           # NEW
│   │   ├── generate_weekly.py          # NEW
│   │   ├── generate_monthly.py         # NEW
│   │   ├── generate_quarterly.py       # NEW
│   │   └── generate_annual.py          # NEW
│   └── api/
│       ├── main.py
│       └── routers/
├── data/
├── resources/
├── results/
├── reports/                             # NEW: generated reports
├── envs/
├── docs/
└── tests/
```

### 4. Dependencies

```yaml
name: pypsa-x
channels: [conda-forge, bioconda]
dependencies:
  # Core
  - python>=3.11
  - pypsa>=1.0.0
  - pypsa-earth>=0.7.0
  - atlite>=0.2.13
  - snakemake>=7.32
  - pandas>=2.0
  - numpy>=1.26
  - xarray>=2024.0
  - geopandas>=0.14
  - rasterio>=1.3
  # Data
  - powerplantmatching>=0.5
  - tsam>=1.0
  - dvc>=3.0
  # Machine learning
  - scikit-learn>=1.4
  - xgboost>=2.0
  - lightgbm>=4.0
  - tensorflow>=2.15
  - shap>=0.44                    # Feature importance
  - imbalanced-learn>=0.12        # For rare outage events
  # Satellite
  - earthaccess>=0.9              # NASA Earthdata access
  - blackmarble-utils>=0.2        # Black Marble toolkit
  - h5py>=3.10                    # HDF5 for VIIRS
  - pyproj>=3.6
  # Market simulation
  - mesa>=2.0
  - gymnasium>=0.29               # RL environment
  - stable-baselines3>=2.2        # RL algorithms
  # API and dashboard
  - fastapi>=0.110
  - uvicorn>=0.29
  - plotly>=5.20
  - dash>=2.16
  - jinja2>=3.1
  - weasyprint>=61
  # Scheduling
  - apscheduler>=3.10             # Periodic reports
  - airflow>=2.9                  # Optional orchestration
  # Testing
  - pytest>=8.0
  - pytest-cov>=5.0
```

**Why each addition**:

- `earthaccess` and `blackmarble-utils` are required for NASA VIIRS/Black Marble access and processing.
- `xgboost`, `lightgbm`, `shap`, `imbalanced-learn` are required for robust outage prediction (rare events require imbalanced learning).
- `gymnasium` and `stable-baselines3` are required for reinforcement learning agents in market simulation.
- `apscheduler` enables scheduled periodic reports without requiring full Airflow deployment.

---

## Part III: Data Pipeline

### 5. Data Acquisition

#### 5.1 Grid Topology

**What**: African transmission network from OSM and World Bank.

**Why**: OSM is PyPSA-Earth's primary source, but African coverage is sparse. The World Bank dataset provides 1,818 transmission line inputs (>110 kV), 4,204 km total length.

**How**:

```python
# scripts/download/download_africa_data.py
from snakemake.script import snakemake
import requests
import os

def download_osm():
    url = "https://download.geofabrik.de/africa-latest.osm.pbf"
    target = snakemake.output.osm
    if not os.path.exists(target):
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(target, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

def download_world_bank_grid():
    url = "http://purl.stanford.edu/vv645gd4791"
    # Follow redirect to actual shapefile
    target = snakemake.output.wb_grid
    # ... download logic
```

#### 5.2 Power Plants

**What**: Consolidated generation assets from `powerplantmatching`.

**Why**: The tool has been validated for Africa, consolidating OSM, GEM, IRENA, GEO, and GPD.

**How**:

```python
# scripts/build/build_powerplants.py
import powerplantmatching as ppm

def build_powerplants():
    df = ppm.powerplants(
        config=ppm.Config(
            countries=snakemake.params.countries,
            target_date=snakemake.params.target_year
        ),
        mock_snakemake=False
    )
    df = ppm.clean(df)
    df.to_csv(snakemake.output.powerplants)
```

#### 5.3 Renewable Profiles

**What**: Hourly generation profiles for all renewable technologies.

**Why**: `atlite` converts ERA5 meteorological data into generation time series. Validated for Africa through PyPSA-Earth.

**How**:

```python
# scripts/build/build_renewables.py
import atlite
import xarray as xr

def build_renewable_profiles(technology):
    cutout = atlite.Cutout(
        path=snakemake.input.cutout,
        module="era5"
    )
    if technology == "solar":
        profile = cutout.pv(
            panel="CSi",
            orientation="latitude_optimal",
            shapes=snakemake.input.regions,
            aggregate=True
        )
    elif technology == "onwind":
        profile = cutout.wind(
            turbine="Vestas_V112_3MW",
            shapes=snakemake.input.regions,
            aggregate=True
        )
    elif technology == "offwind":
        profile = cutout.wind(
            turbine="NREL_ReferenceTurbine_2020ATB_12MW",
            shapes=snakemake.input.offshore_regions,
            aggregate=True
        )
    elif technology == "hydro":
        profile = cutout.hydro(
            plants=snakemake.input.hydro_plants,
            hydrobasins=snakemake.input.hydrobasins
        )
    profile.to_netcdf(snakemake.output.profile)
```

#### 5.4 Demand Profiles

**What**: Hourly country-level demand.

**Why**: AFREC provides the most comprehensive country-level statistics. WorldPop enables spatial disaggregation.

**How**:

```python
# scripts/build/build_demand.py
import pandas as pd
import rioxarray

def build_demand_profiles():
    # Load AFREC national totals
    afrec = pd.read_csv(snakemake.input.afrec)
    # Load population raster for disaggregation
    pop = rioxarray.open_rasterio(snakemake.input.worldpop)
    # Load GDP raster
    gdp = rioxarray.open_rasterio(snakemake.input.gdp)
    # Disaggregate national demand to sub-national nodes
    # ... disaggregation logic
    demand.to_csv(snakemake.output.demand)
```

#### 5.5 NASA VIIRS / Black Marble Outage Data (NEW)

**What**: Daily nighttime radiance data for outage detection across all 55 AU member states.

**Why**: VIIRS Black Marble provides a continuous daily record from 2012 to present at 500m resolution. Angular-effect-corrected radiance allows detection of widespread outages where ground truth is unavailable. Validated in South Africa (89.41% accuracy), Ghana (AUC 0.8346), and Mozambique (Cyclone Idai response).

**How**:

```python
# scripts/download/download_viirs.py
import earthaccess
import xarray as xr
import numpy as np
from blackmarble import BlackMarble
import geopandas as gpd

def download_viirs(country_iso, start_date, end_date):
    """Download VIIRS VNP46A2 tiles for a country and date range."""
    earthaccess.login(strategy="netrc")
    # Find granules
    results = earthaccess.search_data(
        short_name="VNP46A2",
        temporal=(start_date, end_date),
        bounding_box=get_country_bbox(country_iso)
    )
    # Download
    files = earthaccess.download(results, snakemake.output.viirs_dir)
    return files

def get_country_bbox(iso):
    """Get bounding box from GADM boundaries."""
    gdf = gpd.read_file(f"data/gadm/gadm41_{iso}_0.shp")
    return tuple(gdf.total_bounds)
```

```python
# scripts/build/build_outage_history.py
import numpy as np
import xarray as xr
from blackmarble import BlackMarble
import pandas as pd

def build_outage_history():
    """
    Process VIIRS radiance into outage events using VZA-grouped baseline.
    
    Method (validated in Johannesburg, South Africa):
    1. Group observations by Viewing Zenith Angle (VZA) to correct angular effect.
    2. Establish baseline as first quartile of radiance per (pixel, VZA bin).
    3. Flag outage when radiance drops below threshold for the pixel and time.
    """
    ds = xr.open_mfdataset(snakemake.input.viirs_files, combine="by_coords")
    
    # Step 1: Angular effect correction via VZA grouping
    vza_bins = np.arange(0, 70, 5)
    ds["vza_bin"] = np.digitize(ds["Sensor_Zenith"], vza_bins)
    
    # Step 2: Establish baseline per (pixel, VZA bin, month)
    baseline = ds.groupby(["vza_bin", "month"]).quantile(0.25, dim="time")
    
    # Step 3: Detect anomalies
    anomaly = ds["DNB_BRDF_Corrected_NTL"] < (baseline * snakemake.params.threshold)
    
    # Step 4: Aggregate to grid zones
    outage_events = anomaly.groupby("grid_zone").mean(dim=["x", "y"])
    
    # Step 5: Cloud masking
    cloud_mask = ds["QF_Cloud_Mask"] & 0b11 == 0  # Clear-sky only
    outage_events = outage_events.where(cloud_mask, drop=True)
    
    outage_events.to_netcdf(snakemake.output.outage_history)
```

**Why VZA grouping**: The raw daily data fluctuates due to the satellite's changing viewing angle. Grouping by VZA to establish a normal radiance baseline for each location is a significant methodological improvement that reduces false positives.

**Why first quartile baseline**: The first quartile is robust to occasional bright events (lunar reflection, fires) while preserving sensitivity to darkening (outages).

**Limitations to document in config**:

```yaml
viirs:
  enabled: true
  product: "VNP46A2"
  temporal_resolution: "daily"
  spatial_resolution: 500  # metres
  start_date: "2012-01-01"
  cloud_mask: true
  vza_correction: true
  vza_bin_size: 5  # degrees
  baseline_quantile: 0.25
  outage_threshold: 0.6  # radiance drop below 60% of baseline
  aggregation_grid: "0.01_degree"  # Ghana study: largest improvement
  limitations:
    - "One observation per day (~01:30 local); cannot detect short outages"
    - "Cloud cover in tropical regions blocks detection"
    - "Best for large-scale outages affecting multiple pixels"
```

#### 5.6 GridWatch Ground-Truth Data (NEW)

**What**: Ground-truth outage labels from GridWatch sensors.

**Why**: To validate VIIRS-derived outage events and train supervised models. The Ghana study used 147 GridWatch sensors across Greater Accra (2019–mid-2023).

**How**:

```python
# scripts/download/download_gridwatch.py
import requests
import pandas as pd

def download_gridwatch():
    """
    Download GridWatch sensor data.
    Access via https://gridwatch.org/ (registration required).
    Data format: (sensor_id, timestamp, event_type, duration_minutes)
    """
    # GridWatch requires authenticated access; use API token
    headers = {"Authorization": f"Bearer {os.environ['GRIDWATCH_TOKEN']}"}
    response = requests.get(
        "https://api.gridwatch.org/v1/outages",
        headers=headers,
        params={"country": snakemake.params.country_iso}
    )
    df = pd.DataFrame(response.json())
    df.to_csv(snakemake.output.gridwatch)
```

#### 5.7 Weather Data for Outage Prediction

**What**: Historical and forecast weather features.

**Why**: The Ghana study demonstrated that meteorological covariates (temperature, wind speed, precipitation, humidity) support outage detection in data-scarce systems.

**How**:

```python
# scripts/download/download_weather.py
import cdsapi

def download_era5_weather():
    client = cdsapi.Client()
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": [
                "2m_temperature", "10m_wind_speed",
                "total_precipitation", "2m_dewpoint_temperature"
            ],
            "year": snakemake.params.years,
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": snakemake.params.bbox,
            "format": "netcdf"
        },
        snakemake.output.weather
    )
```

---

## Part IV: Layer 1 — PyPSA-Earth Planning Core

### 6. Network Construction

**What**: Build the African power system network.

**Why**: PyPSA-Earth's `create_network` constructs a PyPSA network from pre-processed inputs using Voronoi cells.

**How**:

```yaml
# config/config.africa.yaml
countries: ["DZ","AO","BJ","BW","BF","BI","CM","CV","CF","TD","KM","CG",
            "CD","CI","DJ","EG","GQ","ER","SZ","ET","GA","GM","GH","GN",
            "GW","KE","LS","LR","LY","MG","MW","ML","MR","MU","MA","MZ",
            "NA","NE","NG","RW","ST","SN","SC","SL","SO","ZA","SS","SD",
            "TZ","TG","TN","UG","EH","ZM","ZW"]
clustering:
  mode: "custom_busmap"
  alternative_clustering: false
scenario:
  clusters: [55]
  planning_horizons: [2030, 2040, 2050, 2060]
```

### 7. Optimisation

**What**: Solve for least-cost capacity expansion and dispatch.

**Why**: PyPSA minimises total system cost subject to technical and policy constraints.

**How**:

```python
# scripts/solve/solve_network.py
import pypsa
from snakemake.script import snakemake

def solve_network():
    n = pypsa.Network(snakemake.input.network)
    n.optimize(
        solver_name=snakemake.params.solver,
        multi_investment_periods=True,
        transmission_losses=snakemake.params.transmission_losses,
        linearized_unit_commitment=snakemake.params.linearized_uc
    )
    n.export_to_netcdf(snakemake.output.network)
```

**Solver selection**:

| Problem size | Solver | License |
|---|---|---|
| < 500k vars | HiGHS | MIT |
| 500k–5M vars | Gurobi | Commercial |
| > 5M vars | Gurobi/CPLEX | Commercial |

---

## Part V: Layer 2 — Sector Coupling and All Renewables

### 8. Sector Coupling

**What**: Extend with hydrogen, heat, transport, industry, water.

**Why**: Electricity-only models cannot capture the full energy system. PyPSA-Earth sector-coupled has been validated for hydrogen applications in Egypt.

**How**:

```yaml
# config/config.sector.yaml
sector:
  hydrogen:
    production: true
    export: true
    h2export: 100  # TWh/year
    underground_storage: true
    salt_cavern: true
  heat:
    heat_pump: true
    thermal_storage: true
  transport:
    ev_smart_charging: true
    v2g: true
    hydrogen_vehicles: true
  industry:
    steel: {h2_dri: true, scrap_eaf: true}
    cement: {ccus: true}
    chemicals: {green_ammonia: true, green_methanol: true}
```

### 9. All Renewable Technologies

**What**: Solar PV, CSP, onshore wind, offshore wind, geothermal, hydropower (RoR, reservoir, PHS, small hydro), biomass (solid, biogas, liquid), marine (wave, tidal, OTEC), green hydrogen.

**Why**: Africa's renewable portfolio extends beyond solar and wind. Kenya's geothermal (950 MW installed) and Ethiopia's hydropower (>4 GW) are major resources.

**How**: Each technology requires a dedicated config block and, where applicable, a data source.

```yaml
# config/config.renewables.yaml
renewable:
  solar:
    cutout: africa-2013-era5
    resource: {method: pv, panel: CSi, orientation: latitude_optimal}
    capacity_per_sqkm: 1.7
  csp:
    cutout: africa-2013-era5
    resource: {method: csp, technology: parabolic_trough, storage_hours: 6}
  onwind:
    cutout: africa-2013-era5
    resource: {method: wind, turbine: Vestas_V112_3MW}
    capacity_per_sqkm: 3.0
  offwind:
    cutout: africa-2013-era5
    resource: {method: wind, turbine: NREL_ReferenceTurbine_2020ATB_12MW}
    platform: floating
  geothermal:
    source: geothermal_atlas_africa
    resource: {method: flash_steam, binary_cycle: true}
    cost: {capex: 4000, opex: 100}
  hydro:
    cutout: africa-2013-era5
    resource:
      method: hydro
      hydrobasins: data/hydrobasins/africa.shp
      hydro_capacities: data/hydro_capacities_africa.csv
    carriers: [ror, PHS, reservoir]
  biomass:
    potential: true
    source: jrc_bioenergy_atlas
    crops: [agricultural_residues, forestry_residues, energy_crops]
    conversion: {combustion: true, gasification: true, anaerobic_digestion: true, pyrolysis: true}
  marine:
    wave: true
    tidal: true
    otec: true
    source: global_wave_statistics
    coastal_countries: [ZA, NA, SN, CV, MA, MZ, MG, MU]
```

**Data sources** (direct links):

| Technology | Data source | Direct link |
|---|---|---|
| Solar PV | Global Solar Atlas | `https://globalsolaratlas.info/download` |
| CSP | Global Solar Atlas (DNI) | `https://globalsolaratlas.info/download` |
| Onshore wind | Global Wind Atlas 3.0 | `https://globalwindatlas.info/en/download/gis-files` |
| Offshore wind | GEBCO + Marine Regions | `https://www.gebco.net/data_and_products/gridded_bathymetry_data/` |
| Geothermal | Geothermal Atlas for Africa | `https://geothermalatlasforafrica.org` |
| Hydropower | African Hydropower Atlas | `https://www.hydroshare.org/resource/19eab83ae424be3804ee154ed98aea8/` |
| Biomass | JRC Bioenergy Atlas | `https://data.jrc.ec.europa.eu/` |
| Marine | Global Wave Statistics | `https://www.oceanenergy-europe.eu/` |

---

## Part VI: Layer 3 — Market Simulation and Commercial Analytics

### 10. Agent-Based Market Simulation

**What**: Multi-agent market clearing with strategic bidding.

**Why**: Optimisation models minimise cost but do not produce market prices. AMIRIS and ASSUME achieve MAE of 5.6–6.4 €/MWh against benchmarks.

**How**:

```python
# scripts/solve/solve_market.py
import mesa
import numpy as np
from stable_baselines3 import PPO
import gymnasium as gym

class GeneratorAgent(mesa.Agent):
    def __init__(self, uid, model, capacity, marginal_cost, co2_intensity):
        super().__init__(uid, model)
        self.capacity = capacity
        self.marginal_cost = marginal_cost
        self.co2_intensity = co2_intensity
        self.strategy = self._init_strategy()

    def _init_strategy(self):
        """Initialize bidding strategy. RL agent learns optimal markup."""
        return PPO("MlpPolicy", BiddingEnv(self), verbose=0)

    def bid(self, carbon_price, demand_forecast):
        obs = np.array([carbon_price, demand_forecast, self.capacity])
        markup, _ = self.strategy.predict(obs, deterministic=True)
        return self.marginal_cost + carbon_price * self.co2_intensity + markup[0]

class MarketModel(mesa.Model):
    def __init__(self, network, carbon_price):
        self.network = network
        self.carbon_price = carbon_price
        self.schedule = mesa.time.RandomActivation(self)
        for gen in network.generators.itertuples():
            self.schedule.add(GeneratorAgent(
                gen.Index, self, gen.p_nom, gen.marginal_cost, gen.co2_emissions
            ))

    def clear_market(self, demand):
        """Clear day-ahead market at intersection of supply and demand curves."""
        bids = sorted(
            [(a.bid(self.carbon_price, demand), a.capacity, a)
             for a in self.schedule.agents],
            key=lambda x: x[0]
        )
        cum_capacity = 0
        dispatched = []
        for price, cap, agent in bids:
            cum_capacity += cap
            dispatched.append((price, min(cap, demand)))
            if cum_capacity >= demand:
                break
        clearing_price = dispatched[-1][0]
        return clearing_price, dispatched

    def step(self):
        demand = self.network.loads_t.p_set.iloc[0].sum()
        price, dispatched = self.clear_market(demand)
        # Reward RL agents
        for price, qty in dispatched:
            # ... reward logic
        return price
```

### 11. Capture Prices and PPA Benchmarks

**What**: Revenue-weighted capture prices and PPA curves.

**Why**: COMPASS provides these for South Africa. We provide them for all 55 countries.

**How**:

```python
# scripts/analyse/capture_prices.py
import pandas as pd
import pypsa

def compute_capture_prices(network_path):
    n = pypsa.Network(network_path)
    results = []
    for gen in n.generators.index:
        carrier = n.generators.loc[gen, "carrier"]
        p = n.generators_t.p[gen]
        price = n.buses_t.marginal_price[n.generators.loc[gen, "bus"]]
        revenue = (p * price).sum()
        generation = p.sum()
        capture = revenue / generation if generation > 0 else 0
        results.append({
            "generator": gen, "carrier": carrier,
            "capture_price": capture,
            "time_weighted_price": price.mean(),
            "capture_rate": capture / price.mean() if price.mean() > 0 else 0
        })
    return pd.DataFrame(results)
```

---

## Part VII: Layer 4 — Outage Prediction, Loss Mitigation, and Resilience

### 12. Outage Prediction Module

#### 12.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Outage Prediction Module                                   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Satellite  │  │  Weather    │  │  Predictive         │  │
│  │  Detection  │  │  Forecasting│  │  Maintenance        │  │
│  │  (VIIRS)    │  │  (RF/XGB)   │  │  (Survival)         │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                    │              │
│         └────────────────┼────────────────────┘              │
│                          ▼                                   │
│              ┌───────────────────────┐                       │
│              │  Ensemble Combiner    │                       │
│              │  (Stacked Classifier) │                       │
│              └──────────┬────────────┘                       │
│                         ▼                                    │
│              ┌───────────────────────┐                       │
│              │  Probabilistic Output │                       │
│              │  (p_outage, CI)       │                       │
│              └───────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

#### 12.2 Satellite-Based Outage Detection

```python
# scripts/predict/detect_viirs_outages.py
import numpy as np
import xarray as xr
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

class VIIRSOutageDetector:
    """
    Detect historical outages from VIIRS Black Marble data.

    Validated in Johannesburg: 89.41% overall accuracy.
    Validated in Ghana: AUC 0.8346.
    """
    def __init__(self, viirs_dir, grid_zones, config):
        self.viirs_dir = viirs_dir
        self.grid_zones = grid_zones
        self.config = config

    def load_viirs(self, date_range):
        """Load VIIRS tiles for date range."""
        ds = xr.open_mfdataset(
            f"{self.viirs_dir}/*.nc", combine="by_coords"
        )
        return ds.sel(time=slice(*date_range))

    def angular_correct(self, ds):
        """
        Correct angular effect via VZA grouping.
        This is the single most important methodological step.
        """
        bins = np.arange(0, 70, self.config["vza_bin_size"])
        ds["vza_bin"] = np.digitize(ds["Sensor_Zenith"], bins)
        return ds

    def establish_baseline(self, ds, quantile=0.25):
        """Establish per-(pixel, VZA bin, month) baseline."""
        return ds.groupby(["vza_bin", "month"]).quantile(
            quantile, dim="time"
        )

    def detect_outages(self, ds, baseline, threshold=0.6):
        """Flag outages where radiance drops below threshold."""
        radiance = ds["DNB_BRDF_Corrected_NTL"]
        anomaly = radiance < (baseline * threshold)
        # Cloud mask
        cloud = (ds["QF_Cloud_Mask"] & 0b11) != 0
        anomaly = anomaly.where(~cloud)
        return anomaly

    def aggregate_to_zones(self, anomaly, resolution="0.01_degree"):
        """
        Aggregate pixel anomalies to grid zones.
        0.01-degree aggregation gave the largest improvement in Ghana study.
        """
        return anomaly.groupby("grid_zone").mean(dim=["x", "y"])

    def validate(self, detected_outages, ground_truth):
        """Validate against GridWatch or utility records."""
        y_true = ground_truth.reindex_like(detected_outages).values.flatten()
        y_pred = detected_outages.values.flatten()
        mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
        auc = roc_auc_score(y_true[mask], y_pred[mask])
        return {"auc": auc, "n_samples": mask.sum()}
```

#### 12.3 Weather-Driven Forecasting

```python
# scripts/predict/train_outage_model.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support

class OutageForecaster:
    """
    Supervised outage forecasting with weather features.

    Validated in Adrar, Algeria: 99% accuracy, >98% precision/recall/F1.
    Validated in Ghana: AUC 0.8346.
    """
    def __init__(self, model_type="xgboost"):
        self.model_type = model_type
        self.model = None
        self.features = []

    def build_features(self, outages, weather):
        """Engineer temporal, meteorological, and historical features."""
        df = outages.merge(weather, on=["timestamp", "grid_zone"])
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["month"] = df["timestamp"].dt.month
        df["season"] = (df["month"] % 12 + 3) // 3
        # Historical features
        df = df.sort_values(["grid_zone", "timestamp"])
        df["outage_rate_30d"] = df.groupby("grid_zone")["outage"].transform(
            lambda x: x.shift(1).rolling(30 * 24, min_periods=1).mean()
        )
        df["outage_rate_90d"] = df.groupby("grid_zone")["outage"].transform(
            lambda x: x.shift(1).rolling(90 * 24, min_periods=1).mean()
        )
        # Interaction features (from Algeria study)
        df["temp_wind"] = df["temperature"] * df["wind_speed"]
        df["heat_index"] = df["temperature"] + 0.5 * df["humidity"]
        self.features = [
            "hour", "day_of_week", "month", "season",
            "outage_rate_30d", "outage_rate_90d",
            "temperature", "wind_speed", "precipitation", "humidity",
            "temp_wind", "heat_index"
        ]
        return df

    def train(self, df):
        X = df[self.features]
        y = df["outage"]
        # Handle class imbalance (outages are rare events)
        X_bal, y_bal = SMOTE().fit_resample(X, y)
        if self.model_type == "xgboost":
            self.model = XGBClassifier(
                n_estimators=500, max_depth=8, learning_rate=0.05,
                scale_pos_weight=10, use_label_encoder=False,
                eval_metric="auc", random_state=42, n_jobs=-1
            )
        elif self.model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=500, max_depth=15, min_samples_leaf=10,
                class_weight="balanced", random_state=42, n_jobs=-1
            )
        self.model.fit(X_bal, y_bal)
        return self._evaluate(X, y)

    def _evaluate(self, X, y):
        proba = self.model.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, proba)
        precision, recall, f1, _ = precision_recall_fscore_support(
            y, (proba > 0.5).astype(int), average="binary"
        )
        return {"auc": auc, "precision": precision, "recall": recall, "f1": f1}

    def predict(self, forecast_df):
        X = forecast_df[self.features]
        proba = self.model.predict_proba(X)[:, 1]
        return pd.DataFrame({
            "timestamp": forecast_df["timestamp"],
            "grid_zone": forecast_df["grid_zone"],
            "outage_probability": proba,
            "confidence_lower": np.maximum(proba - 0.1, 0),
            "confidence_upper": np.minimum(proba + 0.1, 1)
        })
```

#### 12.4 Predictive Maintenance

```python
# scripts/predict/predictive_maintenance.py
import pandas as pd
from lifelines import CoxPHFitter

class PredictiveMaintenance:
    """
    Survival analysis for critical assets.

    Validated in Uganda (132 kV transformers) and Nigeria
    (distribution transformers: 87% of critical failures detected,
    64% false alarm reduction, 260% ROI).
    """
    def __init__(self):
        self.model = CoxPHFitter()

    def build_features(self, asset_df):
        """Build survival features from asset metadata."""
        return asset_df[[
            "age_years", "loading_factor", "oil_dga_h2",
            "oil_dga_ch4", "oil_moisture_ppm", "maintenance_interval_days"
        ]]

    def fit(self, asset_df):
        features = self.build_features(asset_df)
        features["duration"] = asset_df["time_to_failure_days"]
        features["event"] = asset_df["failed"]
        self.model.fit(features, duration_col="duration", event_col="event")
        return self.model

    def predict_failure_probability(self, assets, horizon_days=90):
        """Predict failure probability within horizon."""
        features = self.build_features(assets)
        survival = self.model.predict_survival_function(features)
        return 1 - survival.loc[horizon_days].values
```

### 13. Transmission Loss Mitigation

#### 13.1 Loss Decomposition

```python
# scripts/analyse/decompose_losses.py
import pypsa
import pandas as pd
import numpy as np

class LossDecomposer:
    """
    Decompose total system losses into four drivers.
    """
    def __init__(self, network):
        self.n = network

    def compute_total(self, snapshot):
        self.n.lpf(snapshot)
        return self.n.lines_t.p0.loc[snapshot].abs().sum()

    def decompose(self, snapshot):
        base = self.compute_total(snapshot)
        return {
            "total": base,
            "load_driven": self._load_driven(snapshot, base),
            "generation_driven": self._generation_driven(snapshot, base),
            "topology_driven": self._topology_driven(snapshot, base)
        }

    def _load_driven(self, snapshot, base):
        """Losses with generation held at uniform dispatch."""
        n = self.n.copy()
        n.generators_t.p.loc[snapshot] = n.generators.p_nom * 0.5
        n.lpf(snapshot)
        return n.lines_t.p0.loc[snapshot].abs().sum() - base

    def _generation_driven(self, snapshot, base):
        """Losses with load held at uniform profile."""
        n = self.n.copy()
        n.loads_t.p_set.loc[snapshot] = n.loads.p_set * 0.5
        n.lpf(snapshot)
        return n.lines_t.p0.loc[snapshot].abs().sum() - base

    def _topology_driven(self, snapshot, base):
        """Difference from optimal topology."""
        # Use PyPSA's topology optimisation
        return 0  # Placeholder; see PyPSA's network optimisation
```

#### 13.2 Critical Line Identification (TLENS)

```python
# scripts/analyse/contingency_analysis.py
import pypsa
import pandas as pd

class ContingencyAnalyser:
    """
    N-1 contingency analysis with TLENS.

    TLENS (Transmission Lines' contribution to Energy Not Supplied)
    identifies how specific line failures impact overall ENS.

    Validated in Malawi: identified Nanjoka-Nkhotakota, Nkhotakota-
    Dwangwa, Dwangwa-Chintheche, Kapichila-Mlambe as critical.
    """
    def __init__(self, network):
        self.n = network

    def compute_tlens(self, snapshot, n_contingencies=None):
        """Compute TLENS for each line."""
        self.n.lpf(snapshot)
        base_ens = self._compute_ens(snapshot)
        results = []
        lines = self.n.lines.index
        if n_contingencies:
            lines = lines[:n_contingencies]
        for line in lines:
            self.n.lines.loc[line, "active"] = False
            self.n.lpf(snapshot)
            post_ens = self._compute_ens(snapshot)
            results.append({
                "line": line,
                "tlens": post_ens - base_ens,
                "base_flow": self.n.lines_t.p0.loc[snapshot, line]
            })
            self.n.lines.loc[line, "active"] = True
        return pd.DataFrame(results).sort_values("tlens", ascending=False)

    def _compute_ens(self, snapshot):
        """Compute energy not served."""
        load = self.n.loads_t.p_set.loc[snapshot].sum().sum()
        served = self.n.loads_t.p.loc[snapshot].sum().sum()
        return load - served
```

#### 13.3 Mitigation Option Ranking

```python
# scripts/analyse/rank_mitigations.py
import pandas as pd
import numpy as np

class MitigationRanker:
    """
    Rank loss mitigation options by cost-benefit.
    """
    OPTION_TYPES = [
        "topology_switching", "phase_shifting", "voltage_optimisation",
        "dg_placement", "storage_dispatch", "line_upgrades", "new_substations"
    ]

    def __init__(self, network, base_losses):
        self.n = network
        self.base_losses = base_losses

    def evaluate_option(self, option, snapshot):
        n = self.n.copy()
        self._apply(n, option)
        n.lpf(snapshot)
        new_losses = n.lines_t.p0.loc[snapshot].abs().sum()
        loss_reduction = self.base_losses - new_losses
        annual_savings = loss_reduction * 8760 * option["price_per_mwh"]
        return {
            "option": option["name"],
            "type": option["type"],
            "loss_reduction_mw": loss_reduction,
            "annual_savings_usd": annual_savings,
            "capex_usd": option["capex"],
            "payback_years": option["capex"] / annual_savings if annual_savings > 0 else np.inf
        }

    def rank_all(self, options, snapshot):
        return pd.DataFrame([
            self.evaluate_option(o, snapshot) for o in options
        ]).sort_values("payback_years")
```

### 14. Resilience Metrics

```python
# scripts/analyse/resilience_metrics.py
import pandas as pd

class ResilienceMetrics:
    """Compute standard resilience metrics."""
    def compute(self, network, outage_scenarios):
        results = []
        for scenario in outage_scenarios:
            ens = scenario["unserved_energy_mwh"]
            n_customers = scenario["n_customers"]
            duration = scenario["duration_hours"]
            results.append({
                "scenario": scenario["name"],
                "ENS": ens,
                "EENS": ens * scenario["probability"],
                "SAIDI": duration * scenario["n_interrupted"] / n_customers,
                "SAIFI": scenario["n_interrupted"] / n_customers,
                "LNS": scenario["peak_unserved_mw"]
            })
        return pd.DataFrame(results)
```

---

## Part VIII: Layer 5 — What-If Scenario Engine

### 15. Interactive Scenario Planning

**What**: Parameter-driven simulation with rapid re-solve.

**Why**: Decision-makers need to explore futures, not accept single projections.

**How**:

```python
# scripts/solve/solve_whatif.py
import pypsa
from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
import pandas as pd
from joblib import Memory

memory = Memory("cache/whatif", verbose=0)

@dataclass
class ScenarioParameters:
    demand_growth: float = 0.04
    coal_eaf: float = 0.55
    carbon_price: float = 50.0
    gas_price_multiplier: float = 1.0
    renewable_multiplier: float = 1.0
    hydrogen_export: float = 0.0
    battery_cost_multiplier: float = 1.0
    ssp_pathway: str = "SSP2-4.5"
    drought_multiplier: float = 1.0

class WhatIfEngine:
    def __init__(self, base_network_path):
        self.base = pypsa.Network(base_network_path)
        self.cache = {}

    def _cache_key(self, params):
        return hash(tuple(sorted(params.__dict__.items())))

    def solve(self, params: ScenarioParameters) -> Dict:
        key = self._cache_key(params)
        if key in self.cache:
            return self.cache[key]
        n = self._apply(params)
        n.optimize(solver_name="gurobi", multi_investment_periods=True)
        results = self._extract(n)
        self.cache[key] = results
        return results

    def _apply(self, params):
        n = self.base.copy()
        years = n.snapshots.get_level_values("period").year.values
        n.loads_t.p_set *= (1 + params.demand_growth) ** (years - years.min())
        coal = n.generators.carrier == "coal"
        n.generators.loc[coal, "p_max_pu"] = params.coal_eaf
        n.generators.loc[coal, "marginal_cost"] += (
            params.carbon_price * n.generators.loc[coal, "co2_emissions"]
        )
        gas = n.generators.carrier == "gas"
        n.generators.loc[gas, "marginal_cost"] *= params.gas_price_multiplier
        for carrier in ["solar", "onwind", "offwind", "geothermal", "hydro"]:
            mask = n.generators.carrier == carrier
            n.generators.loc[mask, "p_nom_max"] *= params.renewable_multiplier
        n.storage_units["capital_cost"] *= params.battery_cost_multiplier
        return n

    def _extract(self, n):
        return {
            "total_cost": n.objective,
            "capacity_mix": n.generators.groupby("carrier")["p_nom_opt"].sum().to_dict(),
            "emissions": (n.generators_t.p * n.generators.co2_emissions).sum().sum(),
            "prices": n.buses_t.marginal_price.mean().to_dict(),
            "renewable_share": self._renewable_share(n)
        }

    def _renewable_share(self, n):
        gen = n.generators_t.p.sum()
        carriers = n.generators.carrier
        renewable = gen[carriers.isin(
            ["solar", "onwind", "offwind", "geothermal", "hydro", "biomass"]
        )].sum()
        return renewable / gen.sum() if gen.sum() > 0 else 0

    def compare(self, scenarios: List[ScenarioParameters]) -> pd.DataFrame:
        return pd.DataFrame([
            {"scenario": i, **self.solve(s)} for i, s in enumerate(scenarios)
        ])

    def efficient_frontier(self, param_name: str, values: np.ndarray,
                           template: ScenarioParameters) -> pd.DataFrame:
        results = []
        for v in values:
            params = ScenarioParameters(**{**template.__dict__, param_name: v})
            r = self.solve(params)
            results.append({param_name: v, "total_cost": r["total_cost"],
                            "emissions": r["emissions"],
                            "renewable_share": r["renewable_share"]})
        return pd.DataFrame(results)
```

### 16. What-If Dashboard

```python
# scripts/api/whatif_dashboard.py
from dash import Dash, dcc, html, Input, Output
import plotly.express as px
from pypsa_x.whatif import WhatIfEngine, ScenarioParameters

app = Dash(__name__)
engine = WhatIfEngine("results/base_network.nc")

app.layout = html.Div([
    html.H1("PyPSA-X What-If Scenario Explorer"),
    html.Div([
        html.Label("Demand Growth"),
        dcc.Slider(id="demand", min=0, max=0.08, value=0.04, step=0.01),
        html.Label("Coal EAF"),
        dcc.Slider(id="coal", min=0.3, max=0.8, value=0.55, step=0.05),
        html.Label("Carbon Price ($/tCO2)"),
        dcc.Slider(id="carbon", min=0, max=200, value=50, step=10),
        html.Label("Gas Price Multiplier"),
        dcc.Slider(id="gas", min=0.5, max=3.0, value=1.0, step=0.1),
        html.Label("Renewable Multiplier"),
        dcc.Slider(id="renew", min=0.5, max=3.0, value=1.0, step=0.1),
    ]),
    dcc.Graph(id="results"),
    dcc.Graph(id="frontier")
])

@app.callback(
    [Output("results", "figure"), Output("frontier", "figure")],
    [Input("demand", "value"), Input("coal", "value"),
     Input("carbon", "value"), Input("gas", "value"),
     Input("renew", "value")]
)
def update(demand, coal, carbon, gas, renew):
    params = ScenarioParameters(
        demand_growth=demand, coal_eaf=coal, carbon_price=carbon,
        gas_price_multiplier=gas, renewable_multiplier=renew
    )
    result = engine.solve(params)
    fig1 = px.bar(
        x=list(result["capacity_mix"].keys()),
        y=list(result["capacity_mix"].values()),
        title="Capacity Mix (MW)"
    )
    # Efficient frontier over carbon price
    frontier = engine.efficient_frontier(
        "carbon_price", np.arange(0, 210, 20), params
    )
    fig2 = px.line(frontier, x="carbon_price", y="emissions",
                   title="Emissions vs Carbon Price")
    return fig1, fig2
```

---

## Part IX: Layer 6 — Periodic Reporting and Intelligence

### 17. Reporting Architecture

**What**: Scheduled generation of daily, weekly, monthly, quarterly, and annual reports.

**Why**: Different stakeholders need different cadences. A utility operator needs daily outage forecasts; a regulator needs quarterly market reports; an investor needs annual investment briefings.

**How**:

```
┌─────────────────────────────────────────────────────────────┐
│  Reporting Orchestrator (APScheduler)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │  Daily   │ │  Weekly  │ │ Monthly  │ │Quarterly │        │
│  │  06:00   │ │  Mon 06  │ │  1st 06  │ │  1st 06  │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘        │
│       │            │            │            │              │
│       └────────────┼────────────┼────────────┘              │
│                    ▼            ▼                            │
│         ┌──────────────────────────────┐                    │
│         │  Report Generator (Jinja2)   │                    │
│         │  → HTML → PDF (WeasyPrint)   │                    │
│         └──────────────┬───────────────┘                    │
│                        ▼                                     │
│         ┌──────────────────────────────┐                    │
│         │  Distribution                │                    │
│         │  (Email, API, Dashboard)     │                    │
│         └──────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### 18. Report Types and Content

#### 18.1 Daily Report (06:00 local time)

| Section | Content | Source |
|---|---|---|
| **Outage Forecast** | 24-hour outage probability by grid zone, with confidence intervals | VIIRS + weather ML model |
| **Weather Alerts** | Extreme weather warnings affecting generation or transmission | ERA5 forecast |
| **Generation Mix** | Day-ahead generation forecast by technology | PyPSA dispatch |
| **Price Forecast** | Day-ahead wholesale price for each market | Market simulation |
| **System Alerts** | High-risk lines, low reserve margins | Contingency analysis |
| **Outage Summary** | Previous day's actual outages (from VIIRS) | VIIRS detection |

#### 18.2 Weekly Report (Monday 06:00)

| Section | Content | Source |
|---|---|---|
| **Week-Ahead Outage Outlook** | 7-day outage probability by country | ML model |
| **Market Summary** | Week-ahead price forecast and comparison to previous week | Market simulation |
| **Renewable Forecast** | Week-ahead solar, wind, hydro generation outlook | atlite + ERA5 |
| **Transmission Losses** | Weekly loss decomposition and trends | Loss analysis |
| **Critical Line Watch** | Lines with elevated TLENS or loading | Contingency analysis |
| **Outage Events** | Summary of previous week's outages from VIIRS | VIIRS detection |
| **Mitigation Update** | Progress on ranked mitigation options | Loss mitigation |

#### 18.3 Monthly Report (1st of month, 06:00)

| Section | Content | Source |
|---|---|---|
| **Monthly Market Report** | Wholesale prices, capture prices, PPA benchmarks | Market simulation |
| **Capacity Update** | Installed capacity by technology and country | Planning model |
| **Generation Statistics** | Actual vs. forecast generation, curtailment | PyPSA + VIIRS |
| **Outage Statistics** | Monthly outage frequency, duration, SAIDI/SAIFI | VIIRS + GridWatch |
| **Loss Statistics** | Monthly losses by country and corridor | Loss analysis |
| **Resilience Metrics** | ENS, EENS, TLENS trends | Contingency analysis |
| **Policy Tracker** | New policies, regulations, carbon prices | AUDA-NEPAD, AFREC |

#### 18.4 Quarterly Report

| Section | Content | Source |
|---|---|---|
| **Market Outlook** | Quarterly price projections for all countries | Market simulation |
| **Investment Pipeline** | New projects, financial close, commissioning | AID, PIDA |
| **Scenario Update** | What-if scenario comparison and efficient frontiers | What-if engine |
| **Climate Risk** | CMIP6 updates, drought, flood outlook | CMIP6 |
| **Resilience Assessment** | Quarterly resilience scorecard by country | Resilience metrics |

#### 18.5 Annual Report

| Section | Content | Source |
|---|---|---|
| **Continental Energy Outlook** | 30-year capacity expansion plan for all countries | Planning model |
| **Investment Requirements** | Capex by country, technology, and year | Planning model |
| **CMP Alignment** | Progress against CMP targets | CMP data |
| **AfSEM Progress** | Market integration milestones | AfSEM data |
| **Just Transition** | Employment, access, and equity metrics | Socioeconomic model |
| **Climate Scenarios** | SSP1-2.6 to SSP5-8.5 comparison | CMIP6 |

### 19. Report Generation Implementation

```python
# scripts/report/generate_daily.py
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from datetime import datetime, timedelta
import pandas as pd
import pypsa

class DailyReportGenerator:
    def __init__(self, date=None):
        self.date = date or datetime.now().date()
        self.env = Environment(loader=FileSystemLoader("templates/daily"))

    def gather_data(self):
        """Collect all data for the report."""
        return {
            "date": self.date,
            "outage_forecast": self._outage_forecast(),
            "weather_alerts": self._weather_alerts(),
            "generation_mix": self._generation_mix(),
            "price_forecast": self._price_forecast(),
            "system_alerts": self._system_alerts(),
            "outage_summary": self._outage_summary()
        }

    def _outage_forecast(self):
        """Load forecast from outage prediction module."""
        df = pd.read_csv(f"results/outages/forecast_{self.date}.csv")
        return df.to_dict("records")

    def _weather_alerts(self):
        df = pd.read_csv(f"results/weather/alerts_{self.date}.csv")
        return df[df["severity"] >= 3].to_dict("records")

    def _generation_mix(self):
        n = pypsa.Network(f"results/networks/day_ahead_{self.date}.nc")
        return n.generators_t.p.mean().groupby(n.generators.carrier).sum().to_dict()

    def _price_forecast(self):
        n = pypsa.Network(f"results/markets/day_ahead_{self.date}.nc")
        return n.buses_t.marginal_price.mean().to_dict()

    def _system_alerts(self):
        return pd.read_csv(f"results/resilience/alerts_{self.date}.csv").to_dict("records")

    def _outage_summary(self):
        return pd.read_csv(f"results/outages/actual_{self.date - timedelta(days=1)}.csv").to_dict("records")

    def render(self):
        data = self.gather_data()
        template = self.env.get_template("report.html")
        html = template.render(**data)
        output = f"reports/daily/report_{self.date}.pdf"
        HTML(string=html).write_pdf(output)
        return output
```

```python
# scripts/report/scheduler.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from scripts.report.generate_daily import DailyReportGenerator
from scripts.report.generate_weekly import WeeklyReportGenerator
from scripts.report.generate_monthly import MonthlyReportGenerator
from scripts.report.generate_quarterly import QuarterlyReportGenerator
from scripts.report.generate_annual import AnnualReportGenerator

scheduler = BlockingScheduler()

scheduler.add_job(
    lambda: DailyReportGenerator().render(),
    CronTrigger(hour=6, minute=0)
)
scheduler.add_job(
    lambda: WeeklyReportGenerator().render(),
    CronTrigger(day_of_week="mon", hour=6, minute=0)
)
scheduler.add_job(
    lambda: MonthlyReportGenerator().render(),
    CronTrigger(day=1, hour=6, minute=0)
)
scheduler.add_job(
    lambda: QuarterlyReportGenerator().render(),
    CronTrigger(month="1,4,7,10", day=1, hour=6, minute=0)
)
scheduler.add_job(
    lambda: AnnualReportGenerator().render(),
    CronTrigger(month=1, day=1, hour=6, minute=0)
)

if __name__ == "__main__":
    scheduler.start()
```

### 20. Report Templates

```html
<!-- templates/daily/report.html -->
<!DOCTYPE html>
<html>
<head>
    <title>PyPSA-X Daily Report - {{ date }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { border-bottom: 3px solid #1f77b4; padding-bottom: 10px; }
        .section { margin-top: 30px; page-break-inside: avoid; }
        .alert-high { background: #ffe6e6; padding: 10px; border-left: 4px solid red; }
        .alert-medium { background: #fff4e6; padding: 10px; border-left: 4px solid orange; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>PyPSA-X Pan-African Daily Report</h1>
        <p>{{ date }}</p>
    </div>

    <div class="section">
        <h2>Outage Forecast (24 hours)</h2>
        <table>
            <tr><th>Grid Zone</th><th>Outage Probability</th>
                <th>Confidence Interval</th><th>Risk Level</th></tr>
            {% for row in outage_forecast %}
            <tr>
                <td>{{ row.grid_zone }}</td>
                <td>{{ "%.1f"|format(row.outage_probability * 100) }}%</td>
                <td>[{{ "%.1f"|format(row.confidence_lower * 100) }}%,
                     {{ "%.1f"|format(row.confidence_upper * 100) }}%]</td>
                <td>{% if row.outage_probability > 0.7 %}HIGH
                    {% elif row.outage_probability > 0.4 %}MEDIUM
                    {% else %}LOW{% endif %}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>Weather Alerts</h2>
        {% for alert in weather_alerts %}
        <div class="alert-{{ alert.severity_class }}">
            <strong>{{ alert.region }}:</strong> {{ alert.description }}
        </div>
        {% endfor %}
    </div>

    <div class="section">
        <h2>Generation Mix (Day-Ahead)</h2>
        <table>
            <tr><th>Technology</th><th>Generation (MWh)</th><th>Share</th></tr>
            {% for tech, gen in generation_mix.items() %}
            <tr>
                <td>{{ tech }}</td>
                <td>{{ "%.0f"|format(gen) }}</td>
                <td>{{ "%.1f"|format(gen / generation_mix.values()|sum * 100) }}%</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>System Alerts</h2>
        {% for alert in system_alerts %}
        <div class="alert-{{ alert.severity_class }}">
            <strong>{{ alert.type }}:</strong> {{ alert.message }}
        </div>
        {% endfor %}
    </div>
</body>
</html>
```

### 21. Report Distribution

```python
# scripts/report/distribute.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import boto3

class ReportDistributor:
    def __init__(self, channel="email"):
        self.channel = channel

    def distribute(self, report_path, recipients, subject):
        if self.channel == "email":
            self._send_email(report_path, recipients, subject)
        elif self.channel == "s3":
            self._upload_s3(report_path)
        elif self.channel == "api":
            self._publish_api(report_path)

    def _send_email(self, report_path, recipients, subject):
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = "reports@pypsa-x.africa"
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText("Please find the attached report.", "plain"))
        with open(report_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
            part.add_header("Content-Disposition", "attachment",
                            filename=report_path.split("/")[-1])
            msg.attach(part)
        with smtplib.SMTP("smtp.pypsa-x.africa", 587) as server:
            server.starttls()
            server.login("reports@pypsa-x.africa", os.environ["SMTP_PASSWORD"])
            server.send_message(msg)

    def _upload_s3(self, report_path):
        s3 = boto3.client("s3")
        s3.upload_file(report_path, "pypsa-x-reports", report_path.split("/")[-1])

    def _publish_api(self, report_path):
        # POST to API endpoint for dashboard access
        pass
```

---

## Part X: API Specification

### 22. Complete API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| **Planning** | | |
| `/api/v1/scenarios` | GET/POST | List/create scenarios |
| `/api/v1/scenarios/{id}` | GET | Retrieve scenario |
| `/api/v1/scenarios/{id}/results` | GET | Retrieve results |
| **Market** | | |
| `/api/v1/prices` | GET | Price projections |
| `/api/v1/capture-rates` | GET | Capture rates |
| `/api/v1/ppa-benchmarks` | GET | PPA curves |
| **Outages** | | |
| `/api/v1/outages/forecast` | GET | Outage forecast for country/zone |
| `/api/v1/outages/history` | GET | Historical outages from VIIRS |
| `/api/v1/outages/validate` | POST | Validate model against ground truth |
| `/api/v1/maintenance/predict` | POST | Predict asset failure probability |
| **Losses** | | |
| `/api/v1/losses/decompose` | GET | Decompose losses by driver |
| `/api/v1/losses/tlens` | GET | Critical line ranking |
| `/api/v1/losses/mitigate` | POST | Rank mitigation options |
| **Resilience** | | |
| `/api/v1/resilience/metrics` | GET | ENS, EENS, SAIDI, SAIFI |
| `/api/v1/resilience/contingency` | POST | Run N-1 contingency analysis |
| **What-If** | | |
| `/api/v1/whatif/solve` | POST | Solve a scenario |
| `/api/v1/whatif/compare` | POST | Compare scenarios |
| `/api/v1/whatif/frontier` | POST | Generate efficient frontier |
| **Reports** | | |
| `/api/v1/reports/daily` | GET | Retrieve latest daily report |
| `/api/v1/reports/weekly` | GET | Retrieve latest weekly report |
| `/api/v1/reports/monthly` | GET | Retrieve latest monthly report |
| `/api/v1/reports/{type}/{date}` | GET | Retrieve specific report |

### 23. API Implementation

```python
# scripts/api/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd

app = FastAPI(title="PyPSA-X Pan-African API", version="2.0")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_key(api_key: str = Depends(api_key_header)):
    if api_key not in VALID_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

class OutageForecastRequest(BaseModel):
    country: str
    grid_zone: Optional[str] = None
    horizon_hours: int = 24

class WhatIfRequest(BaseModel):
    demand_growth: float = 0.04
    coal_eaf: float = 0.55
    carbon_price: float = 50.0
    gas_price_multiplier: float = 1.0
    renewable_multiplier: float = 1.0

@app.get("/api/v1/outages/forecast")
async def get_outage_forecast(
    request: OutageForecastRequest,
    key: str = Depends(verify_key)
):
    from pypsa_x.outages import OutageForecaster
    forecaster = OutageForecaster.load(f"models/outages/{request.country}.pkl")
    forecast = forecaster.predict(request.horizon_hours, request.grid_zone)
    return forecast.to_dict("records")

@app.get("/api/v1/losses/tlens")
async def get_tlens(country: str, key: str = Depends(verify_key)):
    from pypsa_x.losses import ContingencyAnalyser
    n = load_network(country)
    analyser = ContingencyAnalyser(n)
    return analyser.compute_tlens(snapshot=0).head(20).to_dict("records")

@app.post("/api/v1/whatif/solve")
async def solve_whatif(request: WhatIfRequest, key: str = Depends(verify_key)):
    from pypsa_x.whatif import WhatIfEngine, ScenarioParameters
    engine = WhatIfEngine("results/base_network.nc")
    params = ScenarioParameters(**request.dict())
    return engine.solve(params)

@app.get("/api/v1/reports/daily")
async def get_daily_report(date: Optional[str] = None, key: str = Depends(verify_key)):
    date = date or pd.Timestamp.now().date().isoformat()
    path = f"reports/daily/report_{date}.pdf"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="application/pdf")
```

---

## Part XI: Computational Requirements

### 24. Hardware Tiers

| Tier | Use case | CPU | RAM | GPU | Storage |
|---|---|---|---|---|---|
| **National** | Single-country modelling | 32 cores | 128 GB | — | 2 TB SSD |
| **Power pool** | Regional modelling | 64 cores | 256 GB | — | 4 TB NVMe |
| **Continental** | All 55 countries | 128 cores | 512 GB | A100 (optional) | 10 TB NVMe |
| **Training (outage ML)** | Model training | 32 cores | 128 GB | A100 (recommended) | 2 TB SSD |
| **Continuous reporting** | Daily/weekly/monthly | 16 cores | 64 GB | — | 1 TB SSD |

### 25. Performance Targets

| Operation | Target | Hardware |
|---|---|---|
| Continental LOPF (55 nodes, 8760h) | < 6 hours | 128 cores, 512 GB |
| Continental CEP (2025–2060) | < 36 hours | 128 cores, 512 GB |
| Outage model training (5 years) | < 30 minutes | 32 cores, 64 GB |
| Outage forecast inference (24h) | < 10 seconds | 8 cores, 16 GB |
| TLENS computation (200 lines) | < 2 hours | 64 cores, 128 GB |
| What-if solve (single) | < 2 hours | 64 cores, 256 GB |
| Daily report generation | < 5 minutes | 8 cores, 16 GB |
| Monthly report generation | < 15 minutes | 16 cores, 32 GB |

---

## Part XII: Validation and Testing

### 26. Validation Requirements

| Module | Target | Benchmark |
|---|---|---|
| **Outage prediction (VIIRS)** | AUC > 0.80 | Ghana: 0.8346; Johannesburg: 89.41% accuracy |
| **Outage prediction (weather)** | Accuracy > 95% | Algeria: 99% |
| **Predictive maintenance** | > 80% critical failure detection | Nigeria: 87% |
| **Loss approximation** | < 2% error vs. full AC | PyPSA-Eur: neglecting losses overestimates expansion by 20% |
| **TLENS identification** | Top 10 lines match expert ranking | Malawi: 4 critical corridors |
| **What-if reproducibility** | Identical to machine precision | Required for audit |
| **Report accuracy** | Zero data errors | Automated regression tests |

### 27. Test Suite

```python
# tests/test_outage_prediction.py
import pytest
import numpy as np
from pypsa_x.outages import VIIRSOutageDetector, OutageForecaster

def test_viirs_angular_correction():
    detector = VIIRSOutageDetector("data/viirs", None, {"vza_bin_size": 5})
    # Create synthetic data with known VZA
    # Assert correction removes VZA dependence
    pass

def test_outage_forecaster_auc():
    forecaster = OutageForecaster("xgboost")
    df = load_synthetic_outage_data()
    metrics = forecaster.train(df)
    assert metrics["auc"] > 0.80, f"AUC too low: {metrics['auc']}"

def test_reproducibility():
    from pypsa_x.whatif import WhatIfEngine, ScenarioParameters
    engine = WhatIfEngine("tests/data/base_network.nc")
    params = ScenarioParameters(carbon_price=100)
    r1 = engine.solve(params)
    engine.cache.clear()
    r2 = engine.solve(params)
    assert abs(r1["total_cost"] - r2["total_cost"]) < 1e-6
```

---

## Part XIII: Roadmap and Delivery

### 28. Phased Delivery

| Phase | Duration | Deliverable | Dependencies |
|---|---|---|---|
| **1. Data pipeline** | 4 months | Africa data repository with quality scores | None |
| **2. Electricity model** | 3 months | Working PyPSA-Earth Africa model | Phase 1 |
| **3. Sector coupling** | 4 months | Hydrogen, heat, transport, industry | Phase 2 |
| **4. All renewables** | 3 months | Geothermal, biomass, marine, CSP | Phase 2 |
| **5. Market simulation** | 4 months | Agent-based market model | Phase 3 |
| **6. Outage prediction** | 4 months | VIIRS + weather + maintenance models | Phase 1 |
| **7. Loss mitigation** | 3 months | Loss decomposition, TLENS, mitigation ranking | Phase 2 |
| **8. Resilience analytics** | 2 months | ENS, EENS, SAIDI, SAIFI | Phase 7 |
| **9. What-if engine** | 3 months | Interactive scenario explorer | Phase 3 |
| **10. API & dashboard** | 4 months | REST API + Plotly Dash dashboard | Phases 5–9 |
| **11. Reporting** | 3 months | Daily/weekly/monthly/quarterly/annual reports | Phase 10 |
| **12. Validation** | 3 months | Backtesting, cross-model comparison | All |
| **13. Production release** | 2 months | Live platform | Phase 12 |

### 29. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| VIIRS cloud cover blocks detection | High | Medium | Use multiple satellites; supplement with weather ML |
| Outage ground truth unavailable | High | High | Use GridWatch where available; validate on South Africa and Ghana |
| Continental CEP exceeds compute budget | High | Medium | TSAM aggregation; decomposition; cloud HPC |
| Solver licensing costs | Medium | Medium | Prioritise HiGHS; negotiate academic Gurobi |
| Report accuracy issues | Medium | High | Automated regression tests; version control |
| Institutional resistance | Medium | Medium | Engage AUDA-NEPAD, IRENA, power pools early |

---

## Part XIV: Conclusion

This specification defines PyPSA-X Pan-African as a **full lifecycle decision-support system** with six analytical layers:

1. **Planning Core** — multi-horizon capacity expansion with all renewable technologies
2. **Sector Coupling** — electricity, hydrogen, heat, transport, industry, water
3. **Market Simulation** — agent-based bidding, capture prices, PPA curves
4. **Predictive Analytics** — VIIRS outage detection, weather-driven forecasting, predictive maintenance, loss decomposition, TLENS, resilience metrics
5. **What-If Engine** — interactive parameter adjustment, rapid re-solve, efficient frontiers
6. **Periodic Reporting** — daily, weekly, monthly, quarterly, annual intelligence briefings

The platform is designed for **intermediate developers** to implement incrementally, with each layer independently testable and deployable. It is grounded in **validated methodologies** (VIIRS outage detection in Ghana and Johannesburg, AMIRIS/ASSUME for market simulation, PyPSA-Earth for Africa planning) and uses **open data** (NASA Black Marble, ERA5, Global Wind Atlas, AFREC, OSM) wherever possible. Where data is unavailable, the platform generates **uncertainty-quantified proxy estimates** validated against data-rich countries.

The result is a platform that not only surpasses COMPASS but redefines what an energy system model can be: **a planning tool, a market simulator, a predictive operations platform, a scenario explorer, and a periodic intelligence service — unified in one open-source, continental-scale system.**