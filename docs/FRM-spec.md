# Product Specification: ALEA Post-Processing Financial & Risk Model (FRM)

**Version**: 1.0
**Status**: Implementation-ready specification
**Audience**: Intermediate Python developers with energy-modelling or project-finance experience
**Companion modules**: `alea.prg` (Parameter Relationship Graph), `alea.audit` (consistency audit), PyPSA-Earth (optimisation engine)

---

## 1. Purpose and Scope

The Financial & Risk Model (FRM) is the **post-processing layer** that converts a solved PyPSA-Earth network into the financial and risk quantities that lenders, investors, regulators, insurers, and carbon-market participants require. It does **not** re-optimise the physical system. It consumes:

1. **Solved PyPSA network** — a NetCDF file containing optimised capacities, dispatch, marginal prices, storage operation, cross-border flows, emissions, and unserved energy.
2. **Validated parameter set** — the ~900 parameters the PRG has checked for internal consistency.
3. **Asset metadata** — construction schedule, jurisdiction, currency, contract structure, insurance terms.

It produces:

- **Financial projection**: annual cash flows, debt schedules, tax returns, coverage ratios, returns.
- **Risk distributions**: Monte Carlo distributions of IRR, DSCR, NPV, and VaR/CVaR.
- **Sector sub-models**: insurance/catastrophe, regulatory finance, contract mechanics, carbon finance, tax.
- **Portfolio aggregation**: correlated portfolio VaR, concentration metrics.
- **Audit findings**: disagreements between FRM results and PRG identities.

The FRM is **deterministic-first**: the Financial Projection Engine (FPE) computes a single cash-flow projection. The Risk Engine (RE) wraps the FPE in Monte Carlo to produce distributions. Sub-models extend the FPE for sector-specific economics.

---

## 2. Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ALEA PRG                                                                   │
│  • Validates parameter set                                                  │
│  • Refuses over-determination                                               │
│  • Propagates derived values                                                │
│  • Provides: capex, opex, fuel costs, tax rates, debt terms, PPA terms,    │
│    insurance terms, regulatory terms, carbon-finance terms                  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ validated parameters
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PyPSA-Earth (external engine)                                              │
│  • Solves LOPF / CEP / UC                                                   │
│  • Produces solved NetCDF: p_nom_opt, p, marginal_price, storage, flows,   │
│    emissions, unserved energy, curtailment                                 │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ solved network
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM: Financial Projection Engine (FPE)                                     │
│  • Extracts physical quantities                                            │
│  • Builds annual cash flow                                                 │
│  • Sizes debt against DSCR floor                                           │
│  • Computes tax with carryforward and depreciation                         │
│  • Applies contracts (PPA, CfD), insurance, carbon finance, regulation    │
│  • Produces: CashFlow, DebtSchedule, TaxReturn, Metrics                    │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ deterministic results
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM: Risk Engine (RE)                                                     │
│  • Draws from PRG uncertainty declarations                                 │
│  • Applies Gaussian/t copula correlations                                  │
│  • Re-runs FPE for each draw                                               │
│  • Computes VaR, CVaR, tornado diagrams, stress tests                     │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ distributions
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM: Sector Sub-Models                                                    │
│  • Insurance / catastrophe (CLIMADA integration)                           │
│  • Regulatory finance (RAB, allowed revenue, tariff)                       │
│  • Contract mechanics (PPA, CfD, termination)                             │
│  • Carbon finance (baseline, additionality, issuance, MRV)                 │
│  • Tax (multi-jurisdiction, group structure)                              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ sector results
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM: Portfolio Risk Aggregator                                            │
│  • Correlation matrix across assets                                        │
│  • Portfolio VaR / CVaR                                                    │
│  • Concentration (HHI, top-N, sector, geography, currency)                │
│  • Correlated default                                                      │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ portfolio results
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRM: Consistency Auditor & Delivery                                       │
│  • Compares FPE values to PRG identities                                   │
│  • Reports disagreements                                                   │
│  • Serves API, dashboards, reports                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Design principle**: each layer is a pure function of its inputs. The FPE is deterministic and testable without the RE. The RE is a wrapper. The sub-models are optional extensions. The auditor is separate from all of them.

---

## 3. Data Contracts

### 3.1 Input from PyPSA-Earth

The FRM consumes a **solved PyPSA network** exported to NetCDF. The required fields are:

| PyPSA table | Required columns | Use in FRM |
|---|---|---|
| `generators` | `p_nom_opt`, `carrier`, `bus`, `marginal_cost`, `capital_cost`, `efficiency` | Capacity, dispatch, revenue, cost |
| `generators_t` | `p` (dispatch time series) | Annual energy, fuel consumption, emissions |
| `loads` | `p_set` (demand) | Served energy, unserved energy |
| `loads_t` | `p` (actual served) | Unserved energy calculation |
| `storage_units` | `p_nom_opt`, `max_hours`, `efficiency_store`, `efficiency_dispatch` | Storage revenue, cost |
| `stores` | `e_nom_opt`, `efficiency` | Thermal/hydrogen storage |
| `lines` | `s_nom_opt`, `capital_cost` | Transmission capex |
| `links` | `p_nom_opt`, `efficiency` | Cross-border flows, sector coupling |
| `buses_t` | `marginal_price` | Market revenue for merchant assets |
| `global_constraints` | `constant` (if used) | Carbon budget compliance |

If the network is multi-period (`n.investment_periods`), each period carries its own capacities and dispatch. The FRM annualises over the modelled period.

**Extraction procedure**:

```python
import pypsa
import pandas as pd

def extract_physical_results(network_path: str) -> dict:
    n = pypsa.Network(network_path)
    # Annual energy per generator
    energy = n.generators_t.p.sum() * n.snapshot_weightings["generators"].sum()
    # Annual revenue at marginal price (if merchant)
    revenue = (n.generators_t.p * n.buses_t.marginal_price[n.generators.bus].T).sum()
    # Fuel consumption
    fuel = energy / n.generators.efficiency
    # Emissions
    emissions = energy * n.generators.carrier.map(n.carriers.co2_emissions)
    # Unserved energy
    served = n.loads_t.p.sum()
    demand = n.loads_t.p_set.sum()
    unserved = demand - served
    return {
        "energy_mwh": energy,
        "revenue_usd": revenue,
        "fuel_mwh": fuel,
        "emissions_tco2": emissions,
        "unserved_mwh": unserved,
        "capacity_mw": n.generators.p_nom_opt,
        "storage_capacity_mwh": n.storage_units.p_nom_opt * n.storage_units.max_hours,
    }
```

### 3.2 Input from the PRG

The FRM requires the validated parameter set. The following PRG parameters are **mandatory** for the FPE:

| Category | Parameters |
|---|---|
| **Capital costs** | `capex_solar_pv`, `capex_wind_onshore`, `capex_battery`, `capex_coal`, `capex_gas_ccgt`, `capex_transmission`, … |
| **O&M** | `opex_fixed_solar`, `opex_variable_coal`, … |
| **Fuel** | `fuel_cost_coal`, `fuel_cost_gas`, `fuel_cost_hydrogen`, … |
| **Carbon** | `carbon_price_usd_per_tco2`, `carbon_price_coverage`, `carbon_price_escalation` |
| **Financial** | `discount_rate`, `cost_of_debt`, `cost_of_equity`, `debt_fraction`, `dscr_min`, `tax_rate`, `asset_life` |
| **Tax** | `corporate_income_tax_rate`, `depreciation_schedule_*`, `loss_carryforward_years`, `thin_capitalisation_limit` |
| **Contract** | `ppa_price_usd_per_mwh`, `ppa_duration`, `ppa_indexation`, `offtake_risk_premium`, `ppa_availability` |
| **Insurance** | `premium_share_of_asset`, `retention_share`, `deductible_share`, `loss_ratio`, `combined_ratio`, `solvency_capital_ratio` |
| **Regulatory** | `regulatory_asset_base`, `allowed_return_on_equity`, `allowed_return_on_debt`, `x_factor`, `regulatory_period_length` |
| **Carbon finance** | `carbon_credit_prices`, `buffer_pool_contribution`, `mrv_parameters` |
| **Currency** | `exchange_rate_usd_local`, `currency_risk_premium`, `currency_hedge_cost` |

The FRM does **not** re-validate these; it assumes the PRG has done so. If a required parameter is missing, the FRM raises `MissingParameterError` naming the parameter and the asset.

### 3.3 Asset Metadata

The FRM requires a per-asset metadata record:

```python
@dataclass(frozen=True)
class AssetMetadata:
    asset_id: str
    name: str
    country_iso: str                 # ISO 3166-1 alpha-2
    technology: str                  # "solar_pv", "wind_onshore", "coal", …
    capacity_mw: float
    construction_start_year: int
    commercial_operation_year: int
    asset_life_years: int
    currency_local: str              # "ZAR", "NGN", "KES", …
    currency_debt: str               # "USD", "EUR", …
    debt_fraction: float
    ppa_contract: Optional[PPAContract]
    merchant_share: float            # 0.0–1.0
    carbon_credit_eligible: bool
    insurance_required: bool
    regulatory_regime: str           # "regulated", "merchant", "single_buyer"
```

---

## 4. Financial Projection Engine (FPE)

### 4.1 Cash Flow Structure

The FPE produces a **multi-sheet annual projection** over `asset_life_years`:

| Sheet | Purpose |
|---|---|
| `revenue` | PPA, merchant, capacity, ancillary, carbon, subsidy |
| `operating_cost` | Fuel, variable O&M, fixed O&M, insurance, land lease, grid charges |
| `capital_cost` | Construction capex, contingency, financing fees, IDC |
| `tax` | Depreciation, taxable income, tax payable, deferred tax |
| `debt` | Drawdown, interest, principal, DSCR, LLCR |
| `equity` | Equity invested, dividends, return of capital |
| `balance_sheet` | Assets, liabilities, equity |
| `reserve_accounts` | DSRA, MRA, cash sweep |

The annual projection is computed **year by year**, with each year’s values depending on prior years (debt balance, tax carryforward, reserve balances).

### 4.2 Revenue Computation

**PPA revenue**:

```python
def ppa_revenue(energy_mwh, ppa: PPAContract, year: int) -> float:
    indexation = (1 + ppa.indexation_rate) ** (year - ppa.start_year)
    price = ppa.base_price_usd_per_mwh * indexation
    availability = ppa.availability
    curtailed = ppa.curtailment_compensation * energy_mwh * (1 - availability)
    return energy_mwh * price * availability + curtailed
```

**Merchant revenue**:

```python
def merchant_revenue(energy_mwh, market_price_usd_per_mwh, merchant_share: float) -> float:
    return energy_mwh * market_price_usd_per_mwh * merchant_share
```

**Carbon revenue**:

```python
def carbon_revenue(credits_issued, credit_price, buffer_contribution, vintage_discount, rating_discount) -> float:
    net_credits = credits_issued * (1 - buffer_contribution)
    return net_credits * credit_price * (1 - vintage_discount) * (1 - rating_discount)
```

**Capacity revenue** (if a capacity market exists):

```python
def capacity_revenue(capacity_mw, capacity_price_usd_per_mw_year) -> float:
    return capacity_mw * capacity_price_usd_per_mw_year
```

### 4.3 Operating Cost Computation

```python
def fuel_cost(dispatch_mwh, heat_rate_gj_per_mwh, fuel_price_usd_per_gj) -> float:
    return dispatch_mwh * heat_rate_gj_per_mwh * fuel_price_usd_per_gj

def variable_om(dispatch_mwh, opex_variable_usd_per_mwh) -> float:
    return dispatch_mwh * opex_variable_usd_per_mwh

def fixed_om(capacity_mw, opex_fixed_usd_per_mw_year) -> float:
    return capacity_mw * opex_fixed_usd_per_mw_year

def insurance_premium(capacity_mw, premium_share_of_asset: float, asset_value_usd: float) -> float:
    return asset_value_usd * premium_share_of_asset
```

### 4.4 Debt Sizing

Debt is sized to meet the **minimum DSCR** constraint. The algorithm is an **iterative fixed-point**:

```python
def size_debt(
    cfads: list[float],
    debt_service_fn: Callable[[float], list[float]],
    dscr_min: float,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> float:
    # Initial estimate: 70% of capex
    debt = 0.70 * capex
    for _ in range(max_iter):
        ds = debt_service_fn(debt)
        dscr = [cfads[t] / ds[t] for t in range(len(cfads)) if ds[t] > 0]
        if min(dscr) >= dscr_min:
            return debt
        # Reduce debt proportionally to the shortfall
        debt *= (min(dscr) / dscr_min) * 0.99
        if debt < tol:
            raise DebtSizingError("debt cannot be sized to meet DSCR floor")
    raise DebtSizingError("debt sizing did not converge")
```

`debt_service_fn` returns the annual debt service (principal + interest) for a given debt size, tenor, rate, and amortisation profile. It uses `numpy_financial.pmt` or `ipmt`/`ppmt` for annuity schedules, or a custom sculpted schedule.

### 4.5 Tax Computation

The tax calculation must handle:

- **Depreciation**: book vs. tax schedules (straight-line, declining, accelerated)
- **Interest deduction**: limited by thin-cap rules
- **Loss carryforward**: with expiry year
- **Investment allowance**: immediate deduction on capex
- **Withholding tax**: on dividends and interest
- **Deferred tax**: from book vs. tax depreciation differences

```python
def compute_tax(
    ebitda: list[float],
    book_depreciation: list[float],
    tax_depreciation: list[float],
    interest: list[float],
    tax_rate: float,
    carryforward_years: int,
    thin_cap_limit: float,
) -> list[float]:
    taxable = []
    carryforward = [0.0] * (len(ebitda) + carryforward_years + 1)
    tax = []
    for t in range(len(ebitda)):
        # Interest deduction limited by thin cap
        interest_deduction = min(interest[t], thin_cap_limit * ebitda[t])
        # Taxable income before loss offset
        ti = ebitda[t] - tax_depreciation[t] - interest_deduction
        if ti < 0:
            # Add to carryforward
            carryforward[t + carryforward_years] += -ti
            taxable.append(0.0)
            tax.append(0.0)
        else:
            # Offset with available carryforward
            offset = min(ti, sum(carryforward[t:t + carryforward_years]))
            ti -= offset
            taxable.append(ti)
            tax.append(ti * tax_rate)
    return tax
```

### 4.6 Currency Handling

Each cash flow is tagged to a currency. The FPE maintains:

- **Local-currency ledger**: revenue, opex, tax paid in local currency
- **Debt-currency ledger**: debt service in USD/EUR
- **Equity-currency ledger**: dividends repatriated in parent currency

The conversion uses:

- **Spot rate** for current-year reporting
- **Forward curve** for projected years (from `exchange_rate_usd_local` and `currency_risk_premium`)
- **Hedging instruments** if the asset has any (cost from `currency_hedge_cost`)

```python
def convert_to_usd(amount_local: float, year: int, fx_spot: float, fx_forward: dict[int, float], hedge: Optional[Hedge]) -> float:
    rate = fx_forward.get(year, fx_spot)
    amount_usd = amount_local / rate
    if hedge:
        amount_usd += hedge.cost_usd(year)
    return amount_usd
```

### 4.7 Metrics

From the cash flow, the FPE computes:

```python
import numpy_financial as npf

def compute_metrics(cash_flow: list[float], discount_rate: float) -> dict:
    return {
        "npv": npf.npv(discount_rate, cash_flow),
        "irr": npf.irr(cash_flow),
        "payback": payback_period(cash_flow),
        "lcoe": lcoe(cash_flow, energy_mwh, discount_rate),
    }

def dscr(cfads: list[float], debt_service: list[float]) -> list[float]:
    return [c / d if d > 0 else float("inf") for c, d in zip(cfads, debt_service)]

def llcr(cfads: list[float], debt_outstanding: list[float], discount_rate: float) -> float:
    pv = sum(c / (1 + discount_rate) ** t for t, c in enumerate(cfads))
    return pv / debt_outstanding[0]
```

### 4.8 Cash Flow Waterfall

The FPE assembles the full waterfall in a fixed order:

1. Revenue
2. Operating costs
3. **EBITDA** = Revenue − Operating costs
4. Depreciation and interest deduction
5. Taxable income
6. Tax paid
7. **CFADS** = EBITDA − Tax paid
8. Debt service (interest + principal)
9. Cash available for reserves
10. Reserve account movements
11. Cash available for distribution
12. Dividends
13. Retained cash

The order matters: tax is paid after interest but before debt service, and CFADS is the quantity the DSCR is computed against.

---

## 5. Risk Engine (RE)

### 5.1 Uncertainty Sources

The RE reads the PRG’s `determinism: stochastic` declarations. For each uncertain parameter, it requires a distribution specification:

```yaml
# In PRG, extended for FRM
parameters:
  fuel_cost_gas:
    determinism: stochastic
    distribution:
      type: lognormal
      mean: 35.0
      sigma: 0.25
      unit: USD/MWh
  exchange_rate_usd_local:
    determinism: stochastic
    distribution:
      type: jump_diffusion
      mu: 0.02
      sigma: 0.10
      jump_intensity: 0.05
      jump_mean: 0.15
      jump_std: 0.10
```

If a distribution is not specified, the RE defaults to a **uniform distribution** over the PRG’s declared range.

### 5.2 Correlation

The RE models correlation via a **Gaussian copula** for the bulk and a **t-copula** for tail dependence. The correlation matrix is estimated from:

- Historical data where available (fuel prices, FX)
- Expert elicitation where not (demand growth, political risk)
- Scenario analysis for stress correlation

```python
from scipy.stats import norm, t
from scipy.linalg import cholesky

def draw_correlated_uniforms(n_draws: int, correlation_matrix: np.ndarray, tail_df: float = 4) -> np.ndarray:
    L = cholesky(correlation_matrix, lower=True)
    z = np.random.randn(n_draws, correlation_matrix.shape[0]) @ L.T
    # Convert to uniforms via t-copula for tail dependence
    u = t.cdf(z, df=tail_df)
    return u
```

### 5.3 Sampling

The RE uses **Latin Hypercube Sampling** for efficiency:

```python
from pyDOE2 import lhs

def draw_lhs(n_draws: int, n_dims: int) -> np.ndarray:
    return lhs(n_dims, samples=n_draws, criterion="maximin")
```

For each draw, the RE:

1. Converts the uniform draw to the parameter’s marginal distribution via inverse CDF.
2. Overrides the parameter values in the FPE.
3. Re-runs the FPE.
4. Records the metrics (IRR, DSCR, NPV, etc.).

```python
def run_monte_carlo(fpe: FinancialProjectionEngine, n_draws: int, correlation_matrix: np.ndarray) -> pd.DataFrame:
    uniforms = draw_lhs(n_draws, len(uncertain_params))
    correlated = gaussian_copula(uniforms, correlation_matrix)
    results = []
    for i in range(n_draws):
        params = inverse_cdf(correlated[i], uncertain_params)
        metrics = fpe.run(params)
        results.append(metrics)
    return pd.DataFrame(results)
```

### 5.4 Risk Metrics

```python
def compute_var_cvar(distribution: np.ndarray, confidence: float = 0.95) -> tuple[float, float]:
    var = np.percentile(distribution, (1 - confidence) * 100)
    cvar = distribution[distribution <= var].mean()
    return var, cvar

def probability_below(distribution: np.ndarray, threshold: float) -> float:
    return (distribution < threshold).mean()
```

The RE reports:

| Metric | Definition |
|---|---|
| **VaR(95%)** | 5th percentile of the metric distribution |
| **CVaR(95%)** | Mean of the worst 5% of outcomes |
| **P(DSCR < 1.0)** | Probability of covenant breach |
| **P(IRR < hurdle)** | Probability of unacceptable return |
| **Tornado** | Variance contribution of each uncertainty source |
| **Sobol indices** | Share of variance attributable to each source |

### 5.5 Stress Testing

Predefined stress scenarios are applied deterministically:

| Scenario | Assumption |
|---|---|
| **Fuel spike** | Gas price 3× for 2 years |
| **Currency crisis** | 40% devaluation |
| **Demand collapse** | 20% below base for 3 years |
| **Carbon shock** | $150/tCO₂ from year 5 |
| **Drought** | Hydro inflow 5th percentile for 3 years |
| **Regulatory reset** | X-factor reset to 0 |
| **Sovereign default** | 30% debt haircut |
| **Combined** | Currency + fuel + demand |

Each stress scenario produces a single cash flow and metric set, reported alongside the Monte Carlo distribution.

---

## 6. Insurance and Catastrophe Sub-Model

### 6.1 Cat Model Integration

The FRM integrates **CLIMADA** via its Python API for hazard, exposure, and vulnerability:

```python
from climada.entity import Exposures, ImpactFuncSet
from climada.hazard import Hazard
from climada.engine import Impact

def compute_cat_loss(asset_lat: float, asset_lon: float, asset_value_usd: float, hazard_type: str, return_periods: list[int]) -> dict:
    hazard = Hazard.from_hdf5(f"hazard_{hazard_type}.hdf5")
    exposures = Exposures.from_csv(f"exposure_{asset_id}.csv")
    impact_funcs = ImpactFuncSet.from_excel("impact_functions.xlsx")
    impact = Impact()
    impact.calc(exposures, impact_funcs, hazard)
    return {
        "aal": impact.aai_agg,
        "pml_100": impact.calc_freq_curve([100]).impact,
        "pml_250": impact.calc_freq_curve([250]).impact,
        "loss_exceedance_curve": impact.calc_freq_curve(),
    }
```

### 6.2 Premium Pricing

```python
def price_premium(aal: float, expense_loading: float, capital_loading: float, profit_margin: float) -> float:
    return aal * (1 + expense_loading + capital_loading + profit_margin)
```

### 6.3 Solvency Capital

```python
def solvency_capital(pml_99_5: float, aal: float) -> float:
    return pml_99_5 - aal
```

### 6.4 Insurance Structures

The FRM models:

- **Bulk insurance**: premium = `asset_value × premium_share_of_asset`
- **Parametric insurance**: payout triggered by hazard threshold
- **Cat bond**: coupon = risk-free + spread, principal at risk
- **Reinsurance**: excess-of-loss, quota share, stop-loss

Each structure’s net cost to the asset is computed and compared.

---

## 7. Regulatory Finance Sub-Model

### 7.1 RAB Roll-Forward

```python
def rab_roll_forward(
    rab_opening: float,
    capex: list[float],
    regulatory_depreciation: list[float],
    disposals: list[float],
) -> list[float]:
    rab = [rab_opening]
    for t in range(len(capex)):
        rab.append(rab[t] + capex[t] - regulatory_depreciation[t] - disposals[t])
    return rab
```

### 7.2 Allowed Revenue

```python
def allowed_revenue(
    rab: list[float],
    wacc: float,
    opex: list[float],
    depreciation: list[float],
    tax: list[float],
    x_factor: float,
    pass_through: list[float],
) -> list[float]:
    return [
        rab[t] * wacc + opex[t] + depreciation[t] + tax[t] - x_factor * rab[t] * wacc + pass_through[t]
        for t in range(len(rab))
    ]
```

### 7.3 Tariff Design

```python
def allowed_tariff(allowed_revenue: float, forecast_demand_mwh: float) -> float:
    return allowed_revenue / forecast_demand_mwh
```

If the tariff is rebalanced across customer classes, the FRM applies the PRG’s `tariff_structure` parameter.

### 7.4 Benchmarking

The FRM computes the utility’s cost per unit and compares it to a benchmark (frontier, average, or regression). The gap determines the X-factor for the next regulatory period.

---

## 8. Contract Mechanics Sub-Model

### 8.1 PPA

The PPA model computes:

- Base price
- Indexation (CPI, USD, EUR)
- Availability adjustment
- Curtailment compensation
- Change-in-law adjustment
- Force majeure
- Termination payment

```python
def ppa_termination_payment(remaining_cash_flows: list[float], discount_rate: float, break_fee: float) -> float:
    pv = sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(remaining_cash_flows))
    return pv + break_fee
```

### 8.2 CfD

```python
def cfd_settlement(strike_price: float, market_price: float, volume_mwh: float, two_sided: bool) -> float:
    if two_sided:
        return (strike_price - market_price) * volume_mwh
    return max(0, strike_price - market_price) * volume_mwh
```

### 8.3 Contract Effect on Finance

The contract affects:

- **DSCR**: contracted revenue is more predictable, so debt sizing can be larger
- **Cost of debt**: lower risk premium
- **Cost of equity**: lower required return
- **Equity IRR**: revenue profile is stabilised

The FPE applies these effects through the PRG’s `offtake_risk_premium`, `debt_service_coverage_ratio`, and `equity_return_target` parameters.

---

## 9. Carbon Finance Sub-Model

### 9.1 Baseline and Project Emissions

```python
def emissions_reductions(baseline_emissions: float, project_emissions: float, leakage: float) -> float:
    return baseline_emissions - project_emissions - leakage
```

### 9.2 Additionality

Financial additionality is tested by comparing the project IRR **without** carbon revenue to the hurdle rate:

```python
def is_additional(irr_without_carbon: float, hurdle_rate: float) -> bool:
    return irr_without_carbon < hurdle_rate
```

### 9.3 Credit Issuance

```python
def credits_issued(reductions_tco2: float, buffer_contribution: float, mrv_delay_years: int) -> float:
    return reductions_tco2 * (1 - buffer_contribution)
```

### 9.4 MRV Cost

MRV costs are added to operating costs:

```python
def mrv_cost(monitoring: float, reporting: float, verification: float, verification_frequency_years: int) -> list[float]:
    costs = [monitoring + reporting] * years
    for t in range(0, years, verification_frequency_years):
        costs[t] += verification
    return costs
```

### 9.5 Carbon Revenue

```python
def carbon_revenue(credits: float, price: float, vintage_discount: float, rating_discount: float) -> float:
    return credits * price * (1 - vintage_discount) * (1 - rating_discount)
```

---

## 10. Tax Sub-Model

### 10.1 Multi-Jurisdiction

The FRM supports per-jurisdiction tax parameters. For each asset, the applicable jurisdiction’s parameters are applied:

```python
def jurisdiction_tax_params(country_iso: str) -> TaxParams:
    return TAX_PARAMS[country_iso]  # from PRG, keyed by country
```

### 10.2 Group Structure

If the asset is part of a group:

- **Consolidation**: group tax on consolidated income
- **Treaty network**: withholding rates from treaty, not statutory
- **CFC rules**: parent-level tax on subsidiary income
- **Transfer pricing**: intra-group pricing at arm’s length

The FRM handles the single-jurisdiction case natively. Group cases require an external tax model; the FRM consumes its output via an interface.

### 10.3 Deferred Tax

```python
def deferred_tax_liability(book_depreciation: float, tax_depreciation: float, tax_rate: float) -> float:
    return (book_depreciation - tax_depreciation) * tax_rate
```

The deferred tax balance is tracked on the balance sheet and reverses over the asset’s life.

---

## 11. Portfolio Risk Aggregator

### 11.1 Correlation Matrix

The correlation between assets is estimated from:

- **Geographic**: same country or region
- **Technological**: same technology
- **Currency**: same currency exposure
- **Commodity**: same fuel price exposure
- **Regulatory**: same regulator

The matrix is a **block structure** with high within-block and low between-block correlations.

### 11.2 Portfolio VaR

```python
def portfolio_var(asset_distributions: list[np.ndarray], correlation_matrix: np.ndarray, weights: np.ndarray, confidence: float = 0.95) -> float:
    # Variance-covariance approximation
    cov = np.cov(np.vstack(asset_distributions))
    portfolio_std = np.sqrt(weights @ cov @ weights)
    portfolio_mean = weights @ np.mean(asset_distributions, axis=1)
    z = norm.ppf(1 - confidence)
    return portfolio_mean + z * portfolio_std
```

For a more accurate tail, the FRM uses **Monte Carlo with correlated draws**.

### 11.3 Concentration

```python
def hhi(values: np.ndarray) -> float:
    shares = values / values.sum()
    return np.sum(shares ** 2) * 10000  # HHI scale 0–10000

def top_n_share(values: np.ndarray, n: int) -> float:
    return np.sort(values)[-n:].sum() / values.sum()
```

### 11.4 Correlated Default

If the portfolio is a lender’s book, the FRM uses the **Vasicek one-factor model**:

```python
def portfolio_default_probability(pd: np.ndarray, correlation: float, confidence: float = 0.99) -> float:
    # Conditional default probability given systemic factor
    z = norm.ppf(confidence)
    conditional_pd = norm.cdf((norm.ppf(pd) - np.sqrt(correlation) * z) / np.sqrt(1 - correlation))
    return conditional_pd.mean()
```

---

## 12. Consistency Auditor

The auditor compares FPE results to PRG identities:

| PRG identity | FPE computation | Finding if different |
|---|---|---|
| `equity_irr_estimate` | Actual equity IRR | The PRG’s simplified formula is wrong, or the FPE misses a cash flow |
| `project_gearing_dscr` | Actual minimum DSCR | The PRG’s ratio is wrong, or the FPE’s debt schedule is wrong |
| `llcr_estimate` | Actual LLCR | The PRG’s formula is wrong, or the FPE’s cash flow is wrong |
| `carbon_revenue_usd_per_year` | Actual carbon revenue | The PRG’s formula is wrong, or the FPE’s credit issuance is wrong |
| `lcoe_usd_per_mwh` | Actual LCOE | The PRG’s formula is wrong, or the FPE’s discounted costs are wrong |

```python
@dataclass(frozen=True)
class AuditFinding:
    parameter: str
    prg_value: float
    fpe_value: float
    relative_error: float
    severity: str  # "error" if > 5%, "warning" if > 1%, "info" otherwise
```

The auditor runs after every FPE execution. Findings are reported in the API and the dashboard.

---

## 13. API and Delivery

### 13.1 Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/frm/financial/{asset_id}` | GET | Full cash flow projection |
| `/frm/financial/{asset_id}/metrics` | GET | IRR, NPV, DSCR, LLCR, payback |
| `/frm/financial/portfolio/{portfolio_id}` | GET | Aggregated portfolio projection |
| `/frm/risk/{asset_id}/var` | GET | VaR and CVaR |
| `/frm/risk/{asset_id}/stress` | GET | Stress test results |
| `/frm/risk/{asset_id}/tornado` | GET | Sensitivity ranking |
| `/frm/insurance/{asset_id}/premium` | GET | Premium, AAL, combined ratio |
| `/frm/insurance/{asset_id}/solvency` | GET | Solvency capital |
| `/frm/regulatory/{asset_id}/rab` | GET | RAB roll-forward, allowed revenue |
| `/frm/tax/{asset_id}/liability` | GET | Annual tax, deferred tax |
| `/frm/carbon/{asset_id}/issuance` | GET | Credit issuance, buffer |
| `/frm/portfolio/{portfolio_id}/var` | GET | Portfolio VaR |
| `/frm/portfolio/{portfolio_id}/concentration` | GET | HHI, top-N, sector/geo/currency |
| `/frm/audit/{asset_id}` | GET | PRG consistency findings |

### 13.2 Output Schemas

```python
@dataclass
class CashFlowYear:
    year: int
    revenue_usd: float
    operating_cost_usd: float
    ebitda_usd: float
    tax_usd: float
    cfads_usd: float
    debt_service_usd: float
    dscr: float
    equity_cash_flow_usd: float

@dataclass
class FinancialProjection:
    asset_id: str
    years: list[CashFlowYear]
    npv_usd: float
    irr: float
    min_dscr: float
    llcr: float
    lcoe_usd_per_mwh: float
```

### 13.3 Reports

The FRM produces:

| Report | Content | Audience |
|---|---|---|
| **Asset brief** | 2-page summary with cash flow, DSCR, IRR, key risks | Sponsor, lender |
| **Portfolio brief** | 10-page summary with correlations, concentration, VaR | Investor, board |
| **Lender pack** | DSCR, LLCR, covenant tests, debt schedule | Lender |
| **Investor pack** | IRR, NPV, sensitivity, exit analysis | Equity investor |
| **Regulator pack** | RAB, allowed revenue, tariff, benchmark | Regulator |
| **Insurer pack** | Premium, loss ratio, solvency, cat output | Insurer |
| **Carbon pack** | Baseline, additionality, issuance, MRV | Carbon buyer |

### 13.4 Dashboards

- **Cash-flow dashboard**: annual projection with drill-down
- **Risk dashboard**: VaR, CVaR, tornado diagram, stress scenarios
- **Portfolio dashboard**: composition, concentration, portfolio VaR
- **Regulatory dashboard**: RAB roll-forward, allowed revenue, tariff
- **Insurance dashboard**: premium, solvency, cat model output

---

## 14. Implementation Roadmap

| Phase | Duration | Deliverable |
|---|---|---|
| **1. FPE core** | 3 months | Single-asset cash flow, debt sizing, tax, metrics |
| **2. Multi-asset, multi-currency** | 3 months | Portfolio projection, FX ledger, multi-jurisdiction tax |
| **3. Risk Engine** | 3 months | Monte Carlo, copulas, VaR/CVaR, stress tests |
| **4. Insurance & catastrophe** | 4 months | CLIMADA integration, premium pricing, solvency |
| **5. Regulatory finance** | 3 months | RAB roll-forward, allowed revenue, tariff |
| **6. Contracts & carbon** | 2 months | PPA, CfD, termination, carbon issuance |
| **7. Portfolio risk** | 2 months | Correlation matrix, portfolio VaR, concentration |
| **8. Integration & delivery** | 2 months | API, dashboards, reports, PRG audit |

**Total: 20–22 months** for the full build; **12 months** for a minimum viable version covering Phases 1–3 and 8.

---

## 15. Testing and Validation

| Test type | What it checks |
|---|---|
| **Unit tests** | Every formula, every edge case (zero debt, negative taxable income, missing parameter) |
| **Property-based tests** | `hypothesis` over cash-flow inputs: IRR is monotonic in revenue; DSCR is monotonic in debt size |
| **Integration tests** | FPE on a real PyPSA-Earth solved network; DSCR/IRR are within expected ranges |
| **Backtesting** | Compare FPE results to published financial models for known African projects |
| **PRG audit** | Every FPE metric compared to the PRG’s derived value; disagreements reported |
| **Risk validation** | Monte Carlo converges; VaR/CVaR are stable across seeds; stress tests produce expected directions |
| **Cat model validation** | CLIMADA output compared to published loss curves for the asset’s location |

---

## 16. Summary of Design Decisions

| Decision | Rationale |
|---|---|
| **Deterministic FPE first** | Cash flow arithmetic must be correct before sampling it |
| **Separate Risk Engine** | Monte Carlo is a wrapper, not a replacement; each is testable independently |
| **PRG as parameter source** | Parameters are validated once, not re-validated per asset |
| **PyPSA-Earth as physical source** | Physical optimisation is done by the engine; FRM does not re-solve |
| **CLIMADA for cat risk** | Open-source, global coverage, Python API |
| **Gaussian/t copula** | Separates bulk correlation from tail dependence |
| **Latin Hypercube Sampling** | Efficient coverage of the probability space |
| **Debt sizing by fixed-point iteration** | Matches how lenders actually size debt |
| **Multi-currency ledger** | Africa’s currency heterogeneity is the norm, not the exception |
| **PRG consistency audit** | Two independent implementations of every identity; disagreements are findings |

---

**End of Specification**