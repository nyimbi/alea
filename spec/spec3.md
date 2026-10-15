# Alea: Comprehensive Product Specification

## An Open-Source, Extensible Platform for Continental Energy System Modelling, Market Simulation, and Investment Analytics

**Version**: 1.0
**Status**: Draft for Developer Implementation
**Audience**: Intermediate Python developers with energy system modelling experience
**Base Platform**: PyPSA-Earth v0.7.0+ (PyPSA v1.0+)

---

## Part I: Architecture and Project Structure

### 1. Why This Architecture

PyPSA-Earth already provides a validated, global data pipeline and optimisation workflow. Building on it rather than starting from scratch means we inherit: (1) OSM-based grid topology extraction, (2) powerplantmatching for generation asset consolidation, (3) atlite integration for renewable profiles, and (4) validated African continental coverage. The PyPSA-Earth workflow structure is built as a Snakemake pipeline with five stages: download and filter data, populate data, create network model, solve network, and summarise/plot results. Every rule in the pipeline is a Snakemake rule, and the entire execution follows an input-output chain managed by Snakemake.

Our extension adds four new layers on top of this foundation: sector coupling (energy carriers beyond electricity), market simulation (agent-based bidding and price formation), stochastic optimisation (multi-stage CVaR), and a delivery layer (API, dashboard, reporting).

### 2. Repository Structure

The repository shall follow this structure:

```
pypsa-x-pan-african/
├── Snakefile                          # Main workflow entry point
├── config/
│   ├── config.default.yaml            # Base configuration (inherited from PyPSA-Earth)
│   ├── config.africa.yaml             # Africa-specific overrides
│   ├── config.sector.yaml             # Sector-coupling configuration
│   ├── config.stochastic.yaml         # Stochastic optimisation configuration
│   └── scenarios/                     # Named scenario configurations
├── rules/                             # Snakemake rule modules
│   ├── download.smk                   # Data retrieval rules
│   ├── build_africa.smk               # Africa-specific preprocessing
│   ├── build_sector.smk               # Sector-coupling rules
│   ├── solve.smk                      # Optimisation rules
│   ├── market.smk                     # Market simulation rules
│   └── delivery.smk                   # API, dashboard, reporting rules
├── scripts/                           # Python scripts called by Snakemake rules
│   ├── download_africa_data.py
│   ├── build_africa_topology.py
│   ├── build_renewable_profiles.py
│   ├── build_sector_network.py
│   ├── solve_network.py
│   ├── solve_market.py
│   ├── solve_stochastic.py
│   └── ...
├── data/                              # Downloaded and processed data
├── resources/                         # Intermediate workflow outputs
├── results/                           # Final results
├── envs/                              # Conda environments
├── docs/                              # Documentation
└── tests/                             # Unit and integration tests
```

**Why this structure**: Snakemake rules are modularised by function, enabling independent development and testing. The `config/` directory uses inheritance: `config.africa.yaml` overrides `config.default.yaml`, which extends PyPSA-Earth's base configuration. Scenario-specific configs override both.

### 3. Dependencies and Environment

The environment shall be defined in `envs/environment.yaml`:

```yaml
name: pypsa-x
channels:
  - conda-forge
  - bioconda
dependencies:
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
  - powerplantmatching>=0.5
  - tsam>=1.0
  - mesa>=2.0                    # For agent-based modelling
  - scikit-learn>=1.4            # For ML components
  - tensorflow>=2.15             # For LSTM forecasting
  - fastapi>=0.110               # For REST API
  - uvicorn>=0.29                # ASGI server
  - plotly>=5.20                 # For dashboard
  - dash>=2.16                   # For dashboard
  - jinja2>=3.1                  # For report templates
  - weasyprint>=61               # For PDF generation
  - dvc>=3.0                     # For data version control
  - pytest>=8.0                  # For testing
```

**Why**: PyPSA v1.0 is required for stochastic optimisation with CVaR and chance constraints. MESA is required for agent-based market simulation. All other dependencies are inherited from PyPSA-Earth.

---

## Part II: Data Pipeline

### 4. Africa-Specific Data Acquisition

#### 4.1 Grid Topology

**What**: Build the African transmission network topology from OpenStreetMap (OSM) and the World Bank Africa Electricity Grid Map.

**Why**: OSM is the primary source for PyPSA-Earth grid topology, but Africa's OSM coverage is sparse. The World Bank dataset provides 1,818 transmission line inputs (>110 kV) with a total length of 4,204 km, derived from AICD, OSM, and WAPP GIS database.

**How**:

1. Download the Africa OSM extract from Geofabrik: `https://download.geofabrik.de/africa-latest.osm.pbf`
2. Download the World Bank Africa Electricity Grid Map: `http://purl.stanford.edu/vv645gd4791`
3. Run PyPSA-Earth's `build_shapes` rule to download GADM administrative boundaries and generate GeoJSON files.
4. Run `build_osm_network` to extract power lines, substations, and generators from the OSM extract.
5. Merge World Bank lines with OSM lines, using World Bank as authoritative for voltage and capacity where OSM is missing attributes.
6. Flag all lines with `data_confidence` scores (High/Medium/Low).

**Configuration** (`config.africa.yaml`):

```yaml
countries: ["DZ","AO","BJ","BW","BF","BI","CM","CV","CF","TD","KM","CG",
            "CD","CI","DJ","EG","GQ","ER","SZ","ET","GA","GM","GH","GN",
            "GW","KE","LS","LR","LY","MG","MW","ML","MR","MU","MA","MZ",
            "NA","NE","NG","RW","ST","SN","SC","SL","SO","ZA","SS","SD",
            "TZ","TG","TN","UG","EH","ZM","ZW"]
build_osm_network:
  force: false
  source: "geofabrik"
  world_bank_grid: true
```

#### 4.2 Power Plants

**What**: Consolidate generation assets using `powerplantmatching`.

**Why**: The tool has been successfully employed in Africa for fetching multiple datasets and inferring ground truth. It consolidates OSM, GEM, IRENA, GEO, and GPD into a single dataset.

**How**:

1. Install `powerplantmatching` in the environment.
2. Run the `build_powerplants` rule, which calls `powerplantmatching` with `target_countries="Africa"`.
3. Supplement with RePP Africa data (1,074 hydro, 1,128 solar, 276 wind records) from Figshare.
4. Cross-validate with Global Energy Monitor's Africa Energy Tracker.

**Output**: `resources/africa/powerplants.csv` with columns: `name`, `fueltype`, `technology`, `capacity`, `lon`, `lat`, `date_in`, `date_out`, `data_source`.

#### 4.3 Renewable Resource Data

**What**: Generate hourly renewable generation profiles using `atlite`.

**Why**: `atlite` is the standard tool for converting meteorological data into renewable generation time series. It uses ERA5 reanalysis as the primary weather dataset.

**How**:

1. Register for a Copernicus CDS API key and set it in `~/.cdsapirc`.
2. Run `build_cutout` to download ERA5 data for the African continent. The cutout defines the spatio-temporal boundaries of the simulation.
3. Run `build_renewable_profiles` for each technology: solar PV, onshore wind, offshore wind, and hydro. This calculates for each network node the installable capacity (based on land-use) and the available generation time series (based on weather data).
4. For solar: use Global Solar Atlas PVOUT data for validation. Data period 1994–2025 for most of Africa.
5. For wind: use Global Wind Atlas 3.0 for validation. GIS data downloadable as JSON and CSV.
6. For hydro: use African Hydropower Atlas (Sterl et al., 2021) for seasonal generation profiles. The atlas builds on continental-scale hydrological modelling with detailed plant characteristics.

**Configuration**:

```yaml
atlite:
  nprocesses: 4
  cutouts:
    africa-2013-era5:
      module: era5
      dx: 0.25
      dy: 0.25
      time: ["2013-01-01", "2013-12-31"]
      x: [ -19, 55 ]
      y: [ -36, 38 ]
renewable:
  solar:
    cutout: africa-2013-era5
    resource:
      method: pv
      panel: CSi
      orientation: latitude_optimal
  onwind:
    cutout: africa-2013-era5
    resource:
      method: wind
      turbine: Vestas_V112_3MW
  offwind:
    cutout: africa-2013-era5
    resource:
      method: wind
      turbine: NREL_ReferenceTurbine_2020ATB_12MW
  hydro:
    cutout: africa-2013-era5
    resource:
      method: hydro
      hydrobasins: data/hydrobasins/africa.shp
```

#### 4.4 Demand Data

**What**: Construct hourly electricity demand profiles for each country.

**Why**: AFREC provides the most comprehensive country-level energy statistics for all 55 AU member states. WorldPop provides population data for spatial disaggregation.

**How**:

1. Download AFREC Africa Energy Database 2024 from `https://au-afrec.org/publications`.
2. Download WorldPop population data for Africa at 1km resolution: `https://data.worldpop.org/GIS/Population/Whole_Continent/Africa_1km_Population.7z`
3. Download Global Electrification Platform (GEP) country datasets for all 58 covered countries from `https://energydata.info`.
4. Use the `build_demand_profiles` rule to construct hourly profiles by:
   - Using measured demand where available (South Africa, Egypt, Morocco, Nigeria, Kenya).
   - Using GDP and population rasters to disaggregate national demand to sub-national resolution.
   - Applying country-specific load shapes from the CCG Starter Kits where available.

**Configuration**:

```yaml
demand_data:
  scenario: "AB"  # Base scenario
  base_year: 2020
  growth_scenario: "CMP"  # Align with Continental Power System Masterplan
  source: "afrec"
  disaggregation:
    method: "gdp_pop"
    gdp_raster: "data/gdp/africa_gdp_1km.tif"
    pop_raster: "data/pop/africa_pop_1km.tif"
```

---

## Part III: Electricity-Only Model (Base Layer)

### 5. Network Construction

**What**: Build a PyPSA network for the African power system with country-level nodes, generators, storage, and transmission lines.

**Why**: PyPSA-Earth's `create_network` rule constructs the network from pre-processed inputs. It uses a Voronoi cell approach to split areas into nodes, with buses representing regions.

**How**:

1. Run `build_shapes` to generate GeoJSON files for country boundaries, exclusive economic zones, and administrative zones.
2. Run `build_bus_regions` to create Voronoi cells for each country. The number of nodes per country is configurable (default: 1 for continental studies, up to 10 for large countries).
3. Run `build_powerplants` to attach generators to buses.
4. Run `add_electricity` to attach renewable profiles, demand, and storage.
5. Run `add_extra_components` to add transmission lines, transformers, and interconnectors.

**Configuration**:

```yaml
clustering:
  mode: "custom_busmap"  # Use country boundaries as clusters
  alternative_clustering: false
  simplification: 0.0  # Use full-resolution country boundaries

scenario:
  clusters: [55]  # One node per AU member state
  opts: [""]
  planning_horizons: [2030, 2040, 2050]
```

### 6. Optimisation

**What**: Solve the network for dispatch and capacity expansion.

**Why**: PyPSA's optimisation engine minimises total system cost subject to technical and policy constraints.

**How**:

1. Run `solve_all_networks` or `solve_sector_networks` via Snakemake.
2. The solve rule calls PyPSA's `n.optimize()` with solver specified in config.
3. For multi-horizon: use `n.multi_invest` with perfect foresight.

**Solver Selection**:

| Problem Size | Recommended Solver | License |
|---|---|---|
| < 500,000 variables | HiGHS (open) | MIT |
| 500K–5M variables | Gurobi (commercial) | Commercial |
| > 5M variables | Gurobi or CPLEX | Commercial |

**Configuration**:

```yaml
solver:
  name: "gurobi"
  options: "Method=2 Crossover=0 BarConvTol=1e-6"
  threads: 8

solving:
  options:
    load_shedding: false
    noisy_costs: true
    min_iterations: 4
    max_iterations: 6
    clip_p_max_pu: 1.e-2
```

---

## Part IV: Sector Coupling

### 7. Why Sector Coupling

Electricity-only models cannot capture the full energy system. Sector coupling enables modelling of hydrogen, heat, transport, and industry, which are essential for decarbonisation scenarios. PyPSA-Earth sector-coupled has been validated for hydrogen applications in Egypt, demonstrating PV exceeding 35 GW and electrolysis in Suez and Damietta for meeting 16% of EU hydrogen demand.

### 8. Sector-Coupled Network Construction

**What**: Extend the electricity network with hydrogen, heat, transport, and industry carriers.

**How**:

1. Set `foresight: sector` in config to enable sector coupling.
2. Run `prepare_sector_network` rule.
3. Add hydrogen buses, electrolysers, fuel cells, and storage.
4. Add heat buses, heat pumps, and thermal storage.
5. Add transport demand (EVs, hydrogen vehicles).
6. Add industry demand (steel, cement, chemicals).
7. Add gas network and hydrogen export infrastructure.

**Key Configuration**:

```yaml
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
    steel:
      h2_dri: true
      scrap_eaf: true
    cement:
      ccus: true
    chemicals:
      green_ammonia: true
      green_methanol: true
```

**Why these choices**: Hydrogen export is configured as a single scalar (`export.h2export` in TWh/year), as per PyPSA-Earth's design. The model includes geological storage and sequestration potentials, gas networks, and hydrogen export modelling capabilities.

### 9. All-Renewable Technology Integration

**What**: Model all renewable technologies: solar PV, CSP, onshore wind, offshore wind, geothermal, hydropower (including small hydro and pumped storage), biomass (solid, biogas, liquid), marine energy (wave, tidal, OTEC), and green hydrogen.

**How**: Each technology requires a dedicated Snakemake rule and configuration block.

#### 9.1 Solar PV and CSP

```yaml
renewable:
  solar:
    cutout: africa-2013-era5
    resource:
      method: pv
      panel: CSi
      orientation: latitude_optimal
    capacity_per_sqkm: 1.7  # MW/km²
  csp:
    cutout: africa-2013-era5
    resource:
      method: csp
      technology: "parabolic_trough"
      storage_hours: 6
```

#### 9.2 Wind (Onshore and Offshore)

```yaml
renewable:
  onwind:
    cutout: africa-2013-era5
    resource:
      method: wind
      turbine: Vestas_V112_3MW
    capacity_per_sqkm: 3.0
  offwind:
    cutout: africa-2013-era5
    resource:
      method: wind
      turbine: NREL_ReferenceTurbine_2020ATB_12MW
    capacity_per_sqkm: 4.0
    platform: "floating"  # Default for Africa (deep waters)
```

#### 9.3 Geothermal

```yaml
renewable:
  geothermal:
    source: "geothermal_atlas_africa"
    resource:
      method: "flash_steam"  # For >180°C
      binary_cycle: true      # For 100-180°C
    cost:
      capex: 4000  # USD/kW
      opex: 100    # USD/kW/year
```

**Data source**: Geothermal Atlas for Africa, available at `https://geothermalatlasforafrica.org`. Temperature models at 1km, 2km, 3km, and 4km depth are part of a 3D conductive thermal model of the African lithosphere.

#### 9.4 Hydropower

```yaml
renewable:
  hydro:
    cutout: africa-2013-era5
    resource:
      method: hydro
      hydrobasins: data/hydrobasins/africa.shp
      hydro_capacities: data/hydro_capacities_africa.csv
    carriers: ["ror", "PHS", "reservoir"]
```

**Data source**: African Hydropower Atlas (Sterl et al., 2021), available at `https://www.hydroshare.org/resource/19eab83ae424be3804ee154ed98aea8/`. The atlas contains seasonal hydropower generation profiles for nearly all existing and several hundred future hydropower plants on the African continent.

#### 9.5 Biomass

```yaml
biomass:
  potential: true
  source: "jrc_bioenergy_atlas"
  crops: ["agricultural_residues", "forestry_residues", "energy_crops"]
  conversion:
    combustion: true
    gasification: true
    anaerobic_digestion: true
    pyrolysis: true
```

**Data source**: JRC Bioenergy Atlas and COMPETE Interactive Maps. The sustainable biomass potential of Africa is estimated at 1,911 TWh, with Nigeria (256.5 TWh), Egypt (163.6 TWh), Ethiopia (128.7 TWh), South Africa (118.1 TWh), and Tanzania (115.5 TWh) having the highest potential.

#### 9.6 Marine Energy

```yaml
renewable:
  marine:
    wave: true
    tidal: true
    otec: true
    source: "global_wave_statistics"
    coastal_countries: ["ZA", "NA", "SN", "CV", "MA", "MZ", "MG", "MU"]
```

**Data source**: Global Wave Statistics and NOAA WaveWatch III. High wave power (≥25 kW/m) in Southern Mozambique, Southern Madagascar, Réunion, Mauritius, and parts of Eastern Madagascar.

#### 9.7 Green Hydrogen

```yaml
sector:
  hydrogen:
    electrolysis:
      pem: true
      alkaline: true
      soec: true
    storage:
      salt_cavern: true
      depleted_reservoir: true
    transport:
      pipeline: true
      liquefaction: true
      ammonia: true
    export_terminals:
      - country: "MA"
        port: "Tangier"
      - country: "EG"
        port: "Suez"
      - country: "NA"
        port: "Walvis Bay"
      - country: "ZA"
        port: "Saldanha"
```

**Data source**: IEA Global Hydrogen Review. Hydrogen use in Africa reached 3.1 Mt in 2024, concentrated in Egypt, Algeria, Nigeria, South Africa, Libya, and Equatorial Guinea. Green hydrogen costs start at 1.6 EUR/kg in Mauritania with a total potential of ~259 TWh/a under 2 EUR/kg in 2050.

---

## Part V: Market Simulation

### 10. Why Agent-Based Market Simulation

Optimisation models minimise system cost but do not simulate market prices. Agent-based models simulate the strategic behaviour of market participants, producing price signals that reflect market power, bidding strategies, and regulatory interventions. AMIRIS and ASSUME are the leading open-source frameworks for this, achieving MAE of 5.6–6.4 €/MWh against benchmark data.

### 11. Market Simulation Architecture

**What**: An agent-based market model coupled to PyPSA.

**How**:

1. **Agent types**:
   - **Generators**: Bid their marginal cost, adjusted by strategic markup.
   - **Retailers**: Bid demand based on forecast load and willingness to pay.
   - **Flexibility providers**: Bid demand response and storage capacity.
   - **Market operator**: Clears the day-ahead market at the intersection of supply and demand.

2. **Bidding strategies**:
   - **Marginal cost bidding**: Bid at short-run marginal cost.
   - **Strategic bidding**: Bid above marginal cost using reinforcement learning.
   - **Complex bids**: Block bids, minimum income conditions.

3. **Market clearing**:
   - Day-ahead market with hourly resolution.
   - Cross-border market coupling across power pools.
   - Uniform pricing within zones, nodal pricing where applicable.

**Implementation**:

```python
# scripts/solve_market.py
import mesa
import pypsa
from mesa import Agent, Model

class GeneratorAgent(Agent):
    def __init__(self, unique_id, model, capacity, marginal_cost):
        super().__init__(unique_id, model)
        self.capacity = capacity
        self.marginal_cost = marginal_cost
        self.strategy = "marginal_cost"

    def bid(self, demand_forecast):
        if self.strategy == "marginal_cost":
            return self.marginal_cost
        elif self.strategy == "strategic":
            return self.marginal_cost * self.model.markup_factor

class MarketModel(Model):
    def __init__(self, network):
        self.network = network
        self.schedule = mesa.time.RandomActivation(self)
        # Create agents from PyPSA network
        for gen in network.generators.iterrows():
            agent = GeneratorAgent(gen[0], self, gen[1].p_nom, gen[1].marginal_cost)
            self.schedule.add(agent)

    def clear_market(self):
        bids = [agent.bid(self.demand) for agent in self.schedule.agents]
        # Sort bids, find intersection with demand curve
        return clearing_price, dispatched_quantities
```

---

## Part VI: Stochastic Optimisation

### 12. Why Stochastic Optimisation

Deterministic models ignore uncertainty in fuel prices, demand growth, and technology costs. Stochastic optimisation enables investment decisions that are robust across multiple futures. PyPSA v1.0 supports two-stage stochastic programming with scenario trees, with risk-averse formulation using CVaR.

### 13. Implementation

**What**: Multi-stage stochastic programming with CVaR.

**How**:

1. Define scenarios in a scenario tree. Each scenario has a probability and a set of parameter values.
2. Set risk preference using `n.set_risk_preference(alpha=0.95, omega=0.5)`, where `alpha` is the tail level and `omega` is the weight on CVaR relative to expected cost.
3. Solve using `n.optimize()` with `stochastic=True`.

**Configuration**:

```yaml
stochastic:
  enabled: true
  scenarios:
    - name: "base"
      probability: 0.4
      fuel_price_multiplier: 1.0
      demand_multiplier: 1.0
    - name: "high_fuel"
      probability: 0.3
      fuel_price_multiplier: 1.5
      demand_multiplier: 1.0
    - name: "low_demand"
      probability: 0.3
      fuel_price_multiplier: 1.0
      demand_multiplier: 0.8
  risk:
    alpha: 0.95
    omega: 0.5
```

**Mathematical formulation**: The risk-averse stochastic optimisation extends the risk-neutral formulation by including CVaR in the objective:

$$
\min_x \quad c^T x + (1-\omega)\sum_{s \in S} p_s Q(x,\xi_s) + \omega \,\mathrm{CVaR}_\alpha
$$

---

## Part VII: Delivery Layer

### 14. REST API

**What**: A FastAPI-based REST API for programmatic access.

**Endpoints**:

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/scenarios` | GET | List all scenarios |
| `/api/v1/scenarios` | POST | Create a new scenario |
| `/api/v1/scenarios/{id}` | GET | Retrieve scenario details |
| `/api/v1/scenarios/{id}/results` | GET | Retrieve results |
| `/api/v1/prices` | GET | Get price projections |
| `/api/v1/capture-rates` | GET | Get capture rates |
| `/api/v1/ppa-benchmarks` | GET | Get PPA curves |
| `/api/v1/risk-metrics` | GET | Get VaR/CVaR metrics |

**Implementation**:

```python
# scripts/api.py
from fastapi import FastAPI, HTTPException
app = FastAPI()

@app.get("/api/v1/scenarios")
async def list_scenarios():
    return {"scenarios": [...]}

@app.get("/api/v1/prices")
async def get_prices(country: str, scenario: str):
    # Query scenario database
    return {"country": country, "prices": [...]}
```

### 15. Dashboard

**What**: An interactive Plotly Dash dashboard.

**Features**:
- Continental map with generation capacity and transmission lines.
- Country-level drill-down with demand, supply, prices, emissions.
- Power-pool comparison.
- Scenario exploration with parameter sliders.
- Export to CSV, PNG, SVG, PDF.

**Implementation**:

```python
# scripts/dashboard.py
import dash
from dash import dcc, html
import plotly.express as px

app = dash.Dash(__name__)

app.layout = html.Div([
    dcc.Graph(id="africa-map"),
    dcc.Slider(id="carbon-price", min=0, max=200, value=50),
    dcc.Dropdown(id="scenario-selector", options=[...])
])
```

### 16. Automated Reporting

**What**: Jinja2-based report generation.

**How**:

1. Define templates in `templates/report/`.
2. Use Jinja2 to render HTML, then WeasyPrint to generate PDF.
3. Schedule via Airflow or Cron.

---

## Part VIII: Validation

### 17. Backtesting

**What**: Compare model outputs to historical data.

**How**:

1. **Price backtesting**: Compare simulated SAWEM prices to historical data.
2. **Dispatch backtesting**: Compare simulated generation dispatch to Eskom data.
3. **Capacity validation**: Compare installed capacity to EIA and IRENA data.

**Acceptance criteria**:
- MAE < 8 €/MWh for South African wholesale prices by 2027.
- MAE < 5 €/MWh by 2029.

### 18. Cross-Model Comparison

**What**: Run the same African scenario in Alea, PyPSA-Earth, OSeMOSYS, and Calliope.

**Acceptance criteria**: < 10% divergence in total system cost by 2028.

---

## Part IX: Development Roadmap

| Phase | Duration | Deliverable |
|---|---|---|
| **1: Data Pipeline** | 4 months | Africa data repository with quality scores |
| **2: Electricity Model** | 3 months | Working PyPSA-Earth Africa model |
| **3: Sector Coupling** | 4 months | Hydrogen, heat, transport, industry |
| **4: Renewable Technologies** | 3 months | Geothermal, biomass, marine, CSP |
| **5: Market Simulation** | 4 months | Agent-based market model |
| **6: Stochastic Optimisation** | 3 months | Multi-stage CVaR |
| **7: Delivery Layer** | 4 months | API, dashboard, reporting |
| **8: Validation** | 3 months | Backtesting and cross-model comparison |
| **9: Production Release** | 2 months | Live platform |

---

## Part X: Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data scarcity in CAPP and fragile states | High | High | Proxy data generation, uncertainty quantification |
| Computational cost of continental CEP | High | Medium | TSAM, decomposition, cloud HPC |
| Solver licensing costs | Medium | Medium | Prioritise open-source solvers |
| Institutional resistance | Medium | Medium | Engage AUDA-NEPAD, IRENA, power pools early |

---

**End of Specification**