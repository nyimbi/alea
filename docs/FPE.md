# The ALEA Financial and Risk Model

## What It Is, Where It Sits, and Why It Is Not Optional

The PyPSA-Earth solve produces a least-cost physical system: capacity, dispatch, prices, emissions, cross-border flows, unserved energy. It does not produce cash flows, returns, coverage ratios, tax liabilities, insurance premiums, regulatory accounts, or default probabilities. Those are the quantities every stakeholder who is not a power engineer actually cares about. A regulator wants to know whether a tariff recovers cost, a lender wants to know whether the DSCR clears its floor, a sponsor wants to know the equity IRR, an insurer wants to know the loss ratio, a carbon trader wants to know the additionality of an offset. None of these are computed anywhere in the current stack.

The Financial and Risk Model (FRM) is the **post-processing layer** that turns a physical solution into a financial and risk-bearing object. It is post-processing in the strict sense: **it consumes solved results and does not drive the optimisation**. Its inputs are PyPSA's outputs plus the parameters the PRG has already validated; its outputs are the numbers the twenty archetypes from the platform specification actually use.

It is a **two-tier model**, because the deterministic projection and the stochastic risk model answer different questions and must not be merged:

- The **Financial Projection Engine (FPE)** is deterministic. Given a solved result and a parameter set, it produces annual cash flows, debt schedules, tax returns, coverage ratios, and returns. It is arithmetic — no sampling, no scenarios.
- The **Risk Engine (RE)** is stochastic. It draws from the parameter uncertainties the PRG has declared, re-runs the FPE for each draw, and reports the distribution of outcomes. It is Monte Carlo, correlation-aware, and stress-tested.

The RE cannot exist without the FPE. The FPE cannot exist without PyPSA. Both sit above the PRG, which validates the parameters they consume.

```
PyPSA-Earth solve
        │
        ▼  capacity, dispatch, prices, emissions, unserved energy
Financial Projection Engine (deterministic)
        │
        ▼  cash flow, debt, tax, returns, coverage
Risk Engine (Monte Carlo over PRG uncertainties)
        │
        ▼  distributions, VaR, CVaR, default probability
Insurance / Regulatory / Contract / Carbon / Tax sub-models
        │
        ▼  premiums, RAB, PPA settlements, credit issuance
Portfolio Risk Aggregator
        │
        ▼  portfolio VaR, concentration, correlated default
PRG Consistency Audit
        │
        ▼  findings where the FPE disagrees with the graph's identities
Reports / API / Dashboard
```

The architecture matters because each tier's failure mode is different. The FPE's failure is a wrong number from a wrong formula; the RE's failure is a distribution that assumes the wrong distribution; the insurance model's failure is a premium that doesn't price the cat risk; the portfolio aggregator's failure is a correlation that is assumed rather than estimated. Keeping them separate makes each one auditable.

---

## Part I: The Financial Projection Engine

### 1.1 What it consumes

From PyPSA:

- Capacity by technology by year: `p_nom_opt`
- Dispatch by technology by year: `p`
- Marginal prices by node by year
- Renewable curtailment
- Unserved energy
- Emissions
- Cross-border flows

From the PRG (validated parameters):

- Capital costs per technology
- Fixed and variable O&M
- Fuel costs
- Carbon prices
- Discount rates and cost of capital
- Debt terms (fraction, tenor, rate, coverage floors)
- Tax terms (rates, allowances, depreciation, carryforward)
- Contract terms (PPA price, indexation, availability)
- Insurance terms (premium share, retention, deductible)
- Regulatory terms (RAB opening, allowed returns, X-factor)
- Carbon finance terms (credit price, buffer, vintage)

The FPE does not re-validate the parameters — that is the PRG's job. It consumes them as given and computes the projection.

### 1.2 The core output: the annual cash flow

Everything else in the FPE is either a component of the cash flow or a metric computed from it. The FPE produces a multi-sheet annual projection over the asset's economic life (20–30 years), per asset, per year:

**Revenue sheet**

- PPA revenue: `PPA_price × energy_sold × availability × indexation_factor`
- Merchant revenue: `market_price × energy_sold` where the asset sells into the market
- Capacity payments: if the jurisdiction has a capacity market
- Ancillary service revenue: if the asset provides regulation or reserve
- Carbon revenue: `credits_issued × credit_price × (1 − buffer_contribution)`
- Subsidy revenue: if the jurisdiction has a feed-in premium or CfD top-up
- Cross-subsidy transfers: if the asset is in a regulated utility with cross-subsidy

**Operating cost sheet**

- Fuel cost: `dispatch × heat_rate × fuel_price` for thermal
- Variable O&M: `dispatch × opex_variable`
- Fixed O&M: `capacity × opex_fixed`
- Insurance premium: `capacity × premium_share_of_asset` or `capex × premium_rate`
- Land lease / community benefit share
- Grid connection charges
- Regulatory fees and licence fees
- Local content premiums where mandated

**Capital cost sheet**

- Construction capex: by year, from the capacity trajectory
- Contingency: `capex × contingency_rate`
- Financing fees: `debt_size × arrangement_fee`
- Development costs: pre-construction
- Interest during construction: on drawn debt
- Working capital: positive or negative
- Decommissioning: at end of life, discounted

**Tax sheet**

- Depreciation: by the tax code's schedule (straight-line, declining, accelerated, with investment allowance)
- Taxable income: `EBITDA − depreciation − interest − tax_allowances`
- Loss carryforward: if taxable income is negative
- Corporate income tax: `taxable_income × rate`
- Withholding tax: on dividends and interest actually paid
- Deferred tax: from accelerated vs book depreciation
- Carbon tax: if the jurisdiction has one and it is not already in marginal cost
- Resource rent tax: for mining-adjacent energy assets
- VAT: on revenue, offset by input VAT (a cash timing, not an expense)

**Debt sheet**

- Debt sizing: `min(CFADS_t / DSCR_min) × annuity_factor` — the maximum debt the cash flows can support
- Debt drawdown: over the construction period
- Interest: on outstanding balance
- Principal repayment: annuity, sculpted, or bullet
- DSCR: `CFADS_t / debt_service_t`
- LLCR: `PV(CFADS over remaining life) / debt_outstanding`
- Cash sweep: any excess after coverage and reserve movements goes to prepayment

**Equity sheet**

- Equity invested: construction-period equity
- Dividends: after debt service and reserve movements
- Return of capital: at end of life (if terminal value assumed)

**Balance sheet** (from the cash flow)

- Assets: PP&E net of depreciation, cash, reserves
- Liabilities: debt outstanding, deferred tax, provisions
- Equity: paid-in capital + retained earnings

**Reserve accounts**

- Debt service reserve: `6 months of next year's debt service` (typical)
- Maintenance reserve: `next year's major maintenance`
- Cash sweep: excess to prepayment or to shareholder distribution

### 1.3 The metrics

From the cash flow, the FPE computes:

| Metric | Formula | Used by |
|---|---|---|
| **Project IRR** | `IRR(unlevered cash flow)` | Sponsor, lender |
| **Equity IRR** | `IRR(equity cash flow)` | Sponsor, equity investor |
| **NPV** | `Σ CF_t / (1+r)^t − initial_investment` | Sponsor, lender |
| **Payback** | `initial_investment / average_annual_CF` | Sponsor |
| **DSCR (annual)** | `CFADS_t / debt_service_t` | Lender |
| **DSCR (minimum)** | `min(DSCR_t)` | Lender |
| **LLCR** | `PV(CFADS) / debt_outstanding` | Lender |
| **PLCR** | `PV(CFADS over loan life) / debt_outstanding` | Lender |
| **ICR** | `EBIT_t / interest_t` | Lender |
| **LCOE** | `Σ discounted costs / Σ discounted energy` | Regulator, investor |
| **Levelised revenue** | `Σ discounted revenues / Σ discounted energy` | Investor |

The FPE reports all of these per asset, per country, per portfolio. The minimum DSCR is the value a lender actually cares about — the annual DSCR being above 1.3 in average years but 0.8 in one bad year is a covenant breach, not a pass.

### 1.4 Debt sizing as an iterative problem

Debt sizing is not a closed-form calculation when the debt schedule interacts with the tax and the cash flow, because interest depends on the debt balance, which depends on principal repayment, which depends on the debt size. The FPE solves this with a simple fixed-point iteration:

```
debt_size = initial_estimate
repeat:
    compute debt schedule (interest, principal) on debt_size
    compute CFADS from revenue − opex − tax (tax depends on interest)
    compute DSCR_t from CFADS_t and debt_service_t
    if min(DSCR_t) >= DSCR_min:
        break
    debt_size = debt_size × (min(DSCR_t) / DSCR_min) × 0.99
until converged
```

The iteration converges in 5–15 iterations for typical structures. For sculpted debt (principal shaped to equalize DSCR across years), the sizing can be done in closed form by solving for the principal profile that meets DSCR_min exactly in every year.

### 1.5 The bankability loop back to PyPSA

Some financial outcomes should feed back into the optimisation. A project whose DSCR never clears the lender's floor is not financeable at the assumed PPA price, and the optimiser should know this because otherwise it builds a fleet no one will pay for.

The loop is:

1. PyPSA solves for the optimal fleet.
2. The FPE computes the financials for each asset.
3. If any asset has `min(DSCR) < DSCR_min` or `equity_IRR < hurdle`, the asset is marked **not financeable**.
4. PyPSA is re-run with a **financeability constraint**: only assets that pass the financial test can be built, or the PPA price is raised to the level that makes them financeable.
5. Repeat until all built assets are financeable.

This is standard practice in project finance — it is the reason the "bankability" of a build programme is a live question in every African power procurement. The loop should be **opt-in** in the model configuration, because it roughly triples the solve time, but it is what makes the model's output an **actual build programme** rather than a theoretical one.

### 1.6 Multi-currency

Africa is a continent of forty-plus currencies, and the financial model must handle at least:

- Local currency revenue and cost
- USD-denominated debt (the standard for DFIs and international lenders)
- EUR-denominated debt (some European DFIs)
- Currency mismatch: revenue in local currency, debt in USD

The FPE maintains a **currency ledger** per asset, with each cash flow tagged to its currency, and applies:

- Spot exchange rate (for current-year conversion)
- Forward curve (for projected conversion)
- Hedging instruments (if any)
- Currency-adjusted metrics (IRR in USD, DSCR in local currency but measured in USD)

The **currency risk premium** (`currency_risk_premium` in the PRG) is applied to the cost of debt. But the actual FX exposure in the cash flow is more granular: a 30% devaluation of the ZAR against the USD has a different effect on a ZAR-revenue, USD-debt asset than a 30% depreciation of the NGN has on an NGN-revenue, USD-debt asset, because the two currencies have different volatility profiles and different correlations with the underlying commodity prices.

### 1.7 Multi-jurisdiction tax

Each country has its own tax code, and the FPE must model each one. The parameters are the ones in the PRG's Tax & Fiscal category — corporate rate, withholding rates, investment allowance, depreciation schedule, loss carryforward, thin-cap limit, transfer pricing rules. The FPE applies them per asset per jurisdiction.

The complexity is:

- **Deferred tax** from accelerated depreciation: the balance sheet carries a deferred tax liability that reverses over time.
- **Loss carryforward** with expiry: a loss in year 3 can offset income in year 5, but not year 15.
- **Transfer pricing**: if the asset is part of a group, the pricing of intra-group services must be at arm's length, which affects the taxable income.
- **Thin capitalisation**: if the debt/equity ratio exceeds the limit, the excess interest is non-deductible.
- **Treaty network**: if the parent is in a treaty jurisdiction, the withholding rate on dividends is the treaty rate, not the statutory rate.
- **CFC rules**: if the parent is in a jurisdiction with controlled foreign company rules, the subsidiary's income may be taxed at the parent level before repatriation.

This is genuinely complex, and the FPE should handle the common cases (single-jurisdiction, no group, standard depreciation) natively, and defer to a specialist tax model for the group and treaty cases.

---

## Part II: The Risk Engine

### 2.1 Why a separate engine

The FPE is deterministic. Given the same inputs, it produces the same cash flow. But the inputs are not certain. Fuel prices move, demand grows or doesn't, carbon prices rise or fall, exchange rates devalue, technology costs fall, outages happen, weather varies. A DSCR computed at base-case assumptions is a point estimate of a distribution that the lender cares about in the tail.

The RE runs the FPE many times, each time with a different draw from the parameter distributions, and reports the resulting distribution of outcomes. It answers questions the FPE cannot: "What is the probability that DSCR falls below 1.2 in any year?" "What is the 5% VaR of equity IRR?" "What is the probability that the tariff exceeds the affordability threshold?"

### 2.2 The uncertainty sources

The PRG already declares `determinism: stochastic` on 21 parameters and `relationship: stochastic` on one edge. The RE consumes these declarations plus additional sources that the FPE uses internally (FX, outages, weather). The full list for Africa:

| Category | Sources | Typical distribution |
|---|---|---|
| Fuel prices | Gas, coal, diesel, HFO | Lognormal (fat right tail) |
| Demand growth | Annual growth rate | Normal or truncated normal |
| Carbon prices | Domestic carbon tax, EU CBAM, voluntary | Mixture (policy-driven steps + noise) |
| Exchange rates | ZAR/USD, NGN/USD, KES/USD, etc. | Jump-diffusion (devaluations are fat-tailed) |
| Technology costs | Solar, wind, battery, electrolyser | Lognormal (experience curve noise) |
| Renewable resource | Solar irradiance, wind, hydro inflow | Block bootstrap from historical years |
| Outage rates | Forced outage probability | Beta (bounded in [0,1]) |
| Weather events | Cyclone, flood, drought | Extreme value (GPD, GEV) |
| Regulatory changes | Tariff rebalancing, X-factor | Discrete event with probability |
| Political risk | Sovereign default, contract breach | Low-probability jump |
| Construction delays | Months to COD | Gamma or lognormal |

The distributions are specified per parameter in the PRG (adding a `distribution` field to `ParameterNode`), or by default derived from the parameter's `range` (uniform between bounds, or lognormal if the parameter is positive and skewed).

### 2.3 Correlation

The sources are not independent. A demand shock and a fuel price shock may be correlated (both driven by a global recession). An exchange rate devaluation and a political crisis are correlated. A drought reduces hydro output and raises fuel prices for the thermal backfill.

The RE models correlation with a **Gaussian copula** for the bulk of the distribution and a **t-copula** for the tail (tail dependence between fuel prices and exchange rates, for example). The correlation matrix is estimated from:

- Historical data where available (fuel prices, exchange rates)
- Expert elicitation where not (demand growth, political risk)
- Scenario analysis to stress-test the assumed correlations

The correlation assumption matters more for the tail than for the mean. Two parameters that are 20% correlated in normal times may be 80% correlated during a crisis, which is precisely when the risk model is asked the hard questions.

### 2.4 Sampling

The RE uses **Latin Hypercube Sampling** for the bulk of the distribution (efficient coverage of the probability space) and **Sobol sequences** for the sensitivity analysis (low-discrepancy, better convergence). The number of samples is:

- 1,000 for a first-pass risk estimate (converges to within 5% on the mean)
- 5,000 for a VaR at 95% (converges to within 10% on the 5% quantile)
- 10,000 for a VaR at 99% (converges to within 15% on the 1% quantile)
- 50,000 for a coherent CVaR at 99% (rare events, tail-sensitive)

The convergence is checked via the **Gelman-Rubin diagnostic** on the tail metrics, not just the mean. A Monte Carlo that looks converged on the mean can be far from converged on the 99th percentile.

### 2.5 Stress testing

Monte Carlo answers "what might happen?" Stress testing answers "what happens in the specific scenario where X and Y both go wrong?" The RE includes a set of **predefined stress scenarios**:

| Scenario | Assumption |
|---|---|
| **Fuel price spike** | Gas price 3× base for two years |
| **Currency crisis** | 40% devaluation, 6-month duration |
| **Demand collapse** | 20% below base for three years |
| **Carbon price shock** | $150/tCO₂ from year 5 |
| **Drought** | Hydro inflow at 5th percentile for three years |
| **Regulatory reset** | X-factor reset to 0, tariff frozen for two years |
| **Sovereign default** | Debt restructuring, 30% haircut |
| **Combined shock** | Currency + fuel + demand simultaneously |

The stress scenarios are the events a sponsor's board or a lender's credit committee actually discusses, and they are not well-summarised by a probability-weighted distribution.

### 2.6 Risk metrics

The RE produces:

| Metric | Meaning |
|---|---|
| **Mean** | Expected value across draws |
| **Standard deviation** | Dispersion |
| **VaR (95%, 99%)** | Loss threshold exceeded with 5% / 1% probability |
| **CVaR / Expected shortfall** | Average loss in the tail beyond VaR |
| **P(DSCR < 1.0)** | Probability of covenant breach |
| **P(equity IRR < hurdle)** | Probability the equity return is unacceptable |
| **P(tariff > affordability threshold)** | Probability of political unacceptability |
| **Distribution of each metric** | Full histogram, not just the moments |
| **Tornado diagram** | Sensitivity of each metric to each uncertainty source |
| **Sobol indices** | Share of variance attributable to each source |

The **tornado diagram** is often more useful than the VaR itself, because it tells the analyst which source to investigate. If 60% of the variance in DSCR comes from exchange rate uncertainty, the analyst should spend their time on FX hedging, not on fuel price forecasting.

---

## Part III: The Insurance and Catastrophe Model

### 3.1 Why it is separate

Insurance is not a financial projection. An insurer's economics are driven by a loss distribution, not a revenue stream. The premium that covers a project is priced against the expected loss plus a loading for capital and expenses, not the project's cash flows. The two models share the asset, but they answer different questions.

### 3.2 Inputs

From the PRG:

- `physical_risk_score` (composite of hazard indices)
- `exposure_index` (asset value at risk)
- `vulnerability_index` (asset's susceptibility to damage)
- `parametric_trigger_threshold` (if parametric)
- `retention_share` (insurer's retention)
- `deductible_share` (policyholder's deductible)
- `loss_ratio` (market-level)
- `combined_ratio` (market-level)
- `premium_share_of_asset` (market-level)

From external cat models:

- Hazard intensity (wind speed, flood depth, seismic magnitude) at the asset's location, by return period
- Damage curves (asset damage as a function of hazard intensity)

### 3.3 The frequency-severity model

For each hazard:

- **Frequency**: `λ` events per year, from historical frequency or modelled frequency
- **Severity**: `f(damage | intensity)` from damage curves
- **Loss**: `severity × asset_value × (1 − deductible) × retention_share`

The **aggregate loss distribution** is the convolution of the frequency and severity distributions. For rare events (frequency < 1/year), it can be modelled with a Poisson or Negative Binomial for frequency, a Lognormal or Beta for severity, and computed analytically (Panjer recursion) or by Monte Carlo.

### 3.4 Cat model integration

The cat model is external — OASIS or CLIMADA, both open-source. It takes the asset's location, the hazard, and the asset's vulnerability, and produces:

- **Loss exceedance curve** (LEC): the loss at each return period
- **Average annual loss** (AAL): the expected loss per year
- **Probable maximum loss** (PML): the loss at the 100-year, 250-year, or 500-year return period

The FPE consumes the LEC, the AAL, and the PML, and computes:

- **Premium**: `AAL + loading_for_expenses + loading_for_capital + profit_margin`
- **Solvency capital**: `PML_99.5% − AAL`, or `VaR_99.5% − expected_loss` if the cat model produces VaR
- **Combined ratio**: `(loss_ratio + expense_ratio) / 1` (from PRG)
- **Retained loss distribution**: the distribution of what the insurer keeps after reinsurance

### 3.5 Insurance products

The FPE models several insurance structures:

- **Bulk insurance**: a single policy over the project's assets, with a deductible and a limit
- **Parametric insurance**: a policy that pays when a hazard index exceeds a threshold, regardless of actual loss
- **Cat bonds**: a bond whose principal is at risk if a catastrophe occurs, priced at `risk-free + spread`
- **Reinsurance**: excess-of-loss, quota share, or stop-loss
- **Microinsurance**: small-ticket policies for households (relevant for distributed assets)

Each has its own pricing and structure. The FPE computes the net cost to the project for each option and compares them, so the analyst can recommend the structure.

### 3.6 The insurer's balance sheet

If ALEA is used by an insurer, the model produces the insurer's economics:

- Premium income
- Claims expense
- Reinsurance expense
- Operating expenses
- Underwriting result
- Investment income
- Tax
- Profit

The insurer's **solvency ratio** is `(assets − liabilities) / required_solvency_capital`, where `required_solvency_capital` is `PML_99.5% − AAL` (or the regulatory formula).

---

## Part IV: The Regulatory Finance Model

### 4.1 What it produces

If the asset is a regulated utility (transmission, distribution, or a single-buyer generation fleet), the FPE produces the regulated utility's economics:

- **Regulatory asset base (RAB)** roll-forward: opening + capex − depreciation − disposals = closing
- **Allowed revenue**: `RAB × WACC + operating_costs − X_factor × (RAB × WACC)` or the equivalent revenue-cap formula
- **Allowed tariff**: `allowed_revenue / forecast_demand` (or by tariff class if rebalanced)
- **Regulatory accounts**: the accounts the regulator requires, which typically differ from the financial accounts
- **Performance against benchmark**: the utility's cost per unit compared to the regulator's benchmark, which determines the X-factor in the next period

### 4.2 The RAB roll-forward

The regulatory asset base is the value on which the allowed return is earned. It is not the book value (which is depreciated on the tax code's schedule) or the fair value (which is revalued); it is the accumulated capex less regulatory depreciation, plus or minus adjustments for disposals, revaluations, and pass-through items.

```
RAB_{t+1} = RAB_t + capex_t − regulatory_depreciation_t − disposals_t + revaluation_t
```

The regulatory depreciation is not the tax depreciation — it is the regulator's schedule, which is typically straight-line over the asset's economic life. The difference between the two creates the **deferred tax** the FPE tracks.

### 4.3 The allowed revenue formula

The standard formula (used by NERSA in South Africa, the AER in Australia, Ofgem in the UK, and the African regulators that follow them):

```
Allowed revenue_t = (RAB_t × WACC) + opex_t + depreciation_t + tax_t − X_t + pass_through_t
```

where:

- `RAB_t × WACC` is the return on capital
- `opex_t` is the regulator's allowance for operating costs (or the utility's actual opex, if it is a cost-pass-through regime)
- `depreciation_t` is the regulator's depreciation
- `tax_t` is the tax the regulator allows the utility to recover
- `X_t` is the efficiency factor, which reduces the allowed revenue by a percentage per year
- `pass_through_t` is for costs the regulator passes through directly (fuel costs, purchased power)

The formula varies by jurisdiction, and the FPE parameterises it so that each regulator's specific formula can be modelled.

### 4.4 Tariff design

The tariff the regulator sets is not the same as the allowed revenue. The revenue is the total the utility may collect; the tariff is the per-unit price that collects it. The two are linked by:

```
tariff_t × forecast_demand_t = allowed_revenue_t
```

If the forecast is wrong, the utility either over-collects (and refunds) or under-collects (and carries a regulatory asset). The FPE models both.

The tariff has a **structure** — flat, time-of-use, critical-peak, inclining-block — which determines how much of the revenue comes from which customer class. The PRG's `tariff_structure` parameter selects the structure, and the FPE computes the revenue from each class under that structure.

### 4.5 Benchmarking

The X-factor is set by comparing the utility's costs to a benchmark. The benchmark is typically:

- **Frontier benchmarking**: the cost of the most efficient peer utility
- **Average benchmarking**: the average cost of peers
- **Regression benchmarking**: predicted cost from a regression on output, scale, and customer density

The FPE computes the utility's cost per unit and compares to the benchmark. The gap determines the X-factor the regulator is likely to set — which then affects the next period's allowed revenue — which then affects the utility's finances.

---

## Part V: The Contract Mechanics Model

### 5.1 PPA

A Power Purchase Agreement is a long-term contract between a generator and an offtaker. The FPE models:

- **Price**: fixed or indexed, with floor and cap
- **Indexation**: CPI, USD, EUR, or a bespoke index
- **Volume**: take-or-pay, or availability-based
- **Curtailment compensation**: how much the generator is paid if the offtaker curtails
- **Force majeure**: what happens if the plant cannot generate
- **Termination**: what the offtaker pays if the contract is terminated early
- **Change in law**: how the price adjusts if the law changes

The FPE computes the PPA revenue year by year and compares it to the merchant alternative, so the analyst can see the value of the contract.

### 5.2 CfD

A Contract for Difference pays the generator the difference between the market price and a strike price:

```
CfD settlement = (strike_price − market_price) × volume
```

If the market price is above the strike, the generator pays the difference back. The CfD can be one-sided (only pays when market < strike) or two-sided (both directions).

### 5.3 Termination

If the contract is terminated (by offtaker default, by generator default, or by mutual agreement), the terminating party pays a termination payment, which is typically the NPV of the remaining contract cash flow plus or minus a break fee. The FPE computes this for the scenarios:

- **Offtaker default**: the generator receives the termination payment, but has to find a new offtaker at the merchant price
- **Generator default**: the offtaker receives the termination payment, but has to find a new generator
- **Force majeure**: the contract may be suspended or terminated, with no termination payment

### 5.4 The contract's effect on the FPE

The contract is not just a revenue line. It affects:

- The **DSCR**, because the contract's revenue is more predictable than merchant revenue, which means the debt sizing can be larger
- The **cost of debt**, because contracted cash flow is less risky than merchant cash flow
- The **cost of equity**, for the same reason
- The **equity IRR**, because the contract determines the revenue profile

The FPE captures all four effects.

---

## Part VI: The Tax Model

### 6.1 Why it is separate from the financial projection

The FPE cannot compute the tax line without a separate model, because tax depends on:

- The depreciation schedule (which depends on the tax code, not the financial accounts)
- The interest deduction (which depends on the debt schedule, which depends on the tax, which depends on the debt...)
- The loss carryforward (which depends on prior years' taxable income)
- The withholding tax on repatriation (which depends on the parent's jurisdiction)
- The tax incentives (which depend on the project's characteristics)
- The carbon tax (which depends on the emissions and the tax coverage)

The tax model solves this iterative problem.

### 6.2 The core tax calculation

For each year:

```
EBITDA = revenue − opex
depreciation = book_depreciation OR tax_depreciation (depending on the regime)
interest = debt_schedule[t].interest
taxable_income = EBITDA − depreciation − interest + non_deductible_items − tax_allowances
if taxable_income < 0:
    carryforward[t] = carryforward[t-1] + |taxable_income|
    taxable_income = 0
else:
    offset = min(carryforward[t-1], taxable_income)
    taxable_income -= offset
    carryforward[t] = carryforward[t-1] − offset
corporate_tax = taxable_income × corporate_rate
```

Plus:

- **Investment allowance**: reduces taxable income by a percentage of capex in the year of expenditure
- **Accelerated depreciation**: allows faster write-off than the book rate, creating deferred tax
- **Thin capitalisation**: limits the interest deduction if debt/equity > threshold
- **Transfer pricing**: affects the taxable income if intra-group transactions are not at arm's length
- **Withholding tax**: on dividends and interest when repatriated
- **Carbon tax**: additional tax on emissions, with coverage rules
- **Resource rent tax**: if the asset is mining-adjacent

### 6.3 The deferred tax balance sheet

The difference between book and tax depreciation creates a **deferred tax liability** (or asset) on the balance sheet:

```
DTL_t = (book_accumulated_depreciation_t − tax_accumulated_depreciation_t) × tax_rate
```

This reverses over the asset's life, and the FPE tracks the balance.

### 6.4 The group structure

If the asset is part of a group, the FPE must model:

- **Consolidation**: the group's tax is computed on consolidated income, with intra-group dividends eliminated
- **Treaty network**: the withholding rate on dividends from the subsidiary to the parent depends on the treaty between the two jurisdictions
- **CFC rules**: if the parent is in a CFC jurisdiction, the subsidiary's income may be taxed at the parent level
- **Transfer pricing**: the intra-group pricing must be at arm's length

This is genuinely complex, and the FPE should handle the single-jurisdiction case natively and defer to a specialist tax model for the group case.

---

## Part VII: The Carbon Finance Model

### 7.1 What it produces

If the asset generates carbon credits (from reduced emissions, avoided deforestation, or carbon removal), the FPE produces:

- **Baseline emissions**: what would have happened without the project
- **Project emissions**: what the project actually emits
- **Emissions reductions**: baseline − project − leakage
- **Credits issued**: reductions × issuance_rate × (1 − buffer_contribution)
- **Credit price**: from the market or the contract
- **Carbon revenue**: credits issued × price × (1 − vintage_discount) × (1 − rating_discount)

### 7.2 The methodology

The methodology is jurisdiction-specific and standard-specific:

- **CDM**: Clean Development Mechanism, the original UNFCCC methodology
- **VCS**: Verra Carbon Standard, the largest voluntary standard
- **Gold Standard**: the second-largest voluntary standard
- **Article 6**: the Paris Agreement's cooperative mechanisms (6.2 and 6.4)
- **CORSIA**: the aviation industry's offset scheme

Each has its own baseline methodology, additionality test, leakage calculation, and buffer pool rules. The FPE parameterises the methodology so that a user can model any of them.

### 7.3 Additionality

The additionality test asks: would the emissions reductions have happened without the carbon revenue? If yes, the project is not additional and does not generate credits. The standard tests are:

- **Financial additionality**: the project IRR without carbon revenue is below the hurdle
- **Barrier additionality**: there are non-financial barriers (regulatory, technological, institutional) that prevent the project without carbon revenue
- **Common practice additionality**: the project's technology or practice is not common in the jurisdiction

The FPE runs the financial test automatically, using the FPE's own IRR. The other two are qualitative and require a flag on the project.

### 7.4 Buffer pool

Most standards require a share of credits to be held in a buffer pool, as insurance against reversal (the project's reductions being reversed by fire, disease, or land-use change). The buffer contribution is typically 10–20% of credits. The credits in the buffer are not sold and do not generate revenue unless the project is verified to have not reversed.

The FPE deducts the buffer contribution from the credit issuance, tracks the buffer balance, and reports the reversals if the project is assumed to reverse in a scenario.

### 7.5 MRV

Measurement, Reporting, and Verification (MRV) is the process by which credits are issued. The FPE models:

- **Measurement**: the monitoring cost per year
- **Reporting**: the reporting cost per year
- **Verification**: the verification cost per verification event (every 1–5 years)
- **Time lag**: the credits are issued 6–24 months after the reductions occur

The MRV cost is an operating cost of the project. The time lag affects the cash flow timing.

---

## Part VIII: Portfolio Risk

### 8.1 Why it is separate

A portfolio of assets is not the sum of its assets. Two assets in the same country with the same technology are more correlated than two assets in different countries with different technologies. Two assets exposed to the same currency are more correlated than two assets in different currencies. Two assets whose cash flows depend on the same commodity price are more correlated than two assets that do not.

The portfolio risk aggregator captures this.

### 8.2 The correlation matrix

The aggregator estimates the correlation between assets from:

- **Geographic**: assets in the same country or region
- **Technological**: assets of the same technology
- **Currency**: assets exposed to the same currency
- **Commodity**: assets whose cash flows depend on the same commodity
- **Regulatory**: assets under the same regulator

The correlation matrix is typically a **block structure** — high within blocks, low between — with the blocks defined by the above factors and the off-diagonal correlations estimated from historical data or expert elicitation.

### 8.3 Portfolio VaR

The portfolio VaR is computed from the asset-level distributions and the correlation matrix:

- **Variance-covariance**: `σ_portfolio = √(w' Σ w)` where `w` is the weight vector and `Σ` is the covariance matrix
- **Historical simulation**: apply the historical shocks to the current portfolio
- **Monte Carlo**: draw correlated scenarios and compute the portfolio loss in each

The variance-covariance method is fast but assumes a normal distribution (underestimates tail risk). Historical simulation captures empirical tails but requires historical data. Monte Carlo is the most flexible and captures the tail if the distributions are right.

### 8.4 Concentration

The aggregator computes concentration metrics:

- **HHI** on asset values
- **Top-N exposure**: the share of the portfolio in the top 5, 10, or 20 assets
- **Sector concentration**: the share in each technology
- **Geographic concentration**: the share in each country
- **Currency concentration**: the share exposed to each currency

The concentration is a **risk factor independent of the individual assets**. A portfolio with 10 assets in 10 countries is more diversified than a portfolio with 10 assets in one country, even if the individual assets have identical risk profiles.

### 8.5 Correlated default

If the portfolio is a lender's book, the correlated default probability is:

```
P(portfolio loss > L) = P(k defaults such that Σ L_i > L)
```

where defaults are correlated through a factor model (e.g., the Merton model, where default occurs when the asset value falls below a threshold). The aggregator uses:

- **Vasicek one-factor model**: default correlation through a single systemic factor
- **CreditMetrics**: default correlation through a ratings transition matrix
- **Merton structural model**: default correlation through the correlation of asset returns

The choice depends on the data available and the regulator's standard.

---

## Part IX: Consistency with the PRG

### 9.1 Which parameters are recomputed

The FPE recomputes, from actual cash flow, several parameters the PRG currently derives from declared values:

| PRG parameter | PRG derivation | FPE computation |
|---|---|---|
| `equity_irr_estimate` | `(cfads − debt_service) / capex / (1 − debt_fraction)` | Actual IRR from equity cash flow |
| `project_gearing_dscr` | `cfads / debt_service` | Actual DSCR from CFADS and debt service schedule |
| `llcr_estimate` | `PV(cfads) / debt` | Actual LLCR from the debt schedule |
| `carbon_revenue_usd_per_year` | `emissions × price × coverage` | Actual carbon revenue from credit issuance |
| `health_cost_usd_per_year` | `dalys × healthcare_cost_per_case` | Actual health cost with dose-response |
| `total_jobs` | `direct_jobs × (1 + multipliers)` | Actual jobs from the capacity trajectory |
| `lcoe_usd_per_mwh` | `annualised_capex / (cf × 8760) + marginal_cost` | Actual LCOE from discounted cash flow |
| `regulated_tariff_usd_per_mwh` | `annualised_capex × capacity / demand + marginal_cost` | Actual tariff from RAB roll-forward |

### 9.2 The audit

The FPE's output should be compared to the PRG's derivation. If they disagree, that is a finding:

- **PRG says DSCR is 1.3, FPE says 1.1** — either the PRG's simplified formula is wrong (it doesn't account for tax) or the FPE's cash flow is wrong (it doesn't account for a revenue stream)
- **PRG says equity IRR is 12%, FPE says 8%** — the same, at the level of the equity cash flow
- **PRG says LCOE is $80, FPE says $95** — the PRG doesn't account for the tax shield, or the FPE doesn't account for the capacity factor correctly

Each disagreement is a finding, and the audit reports it. This is the same discipline as the energy audit: two independent implementations of the same identity, and the disagreement is the finding.

### 9.3 The reconciled parameter set

After the FPE runs, the PRG's financial parameters should be **reconciled** to the FPE's actual values. This means:

- `equity_irr_estimate` is set to the FPE's actual equity IRR
- `project_gearing_dscr` is set to the FPE's actual DSCR
- `llcr_estimate` is set to the FPE's actual LLCR
- `total_jobs` is set to the FPE's actual jobs

This is not the FPE overwriting the PRG; it is the PRG's **derived** values being replaced by the FPE's **measured** values, which is exactly what the audit is designed to make possible. The next `check_scenario` call uses the FPE's values and checks them against the graph's other identities. If they fail, the disagreement is a finding.

---

## Part X: Delivery

### 10.1 API endpoints

The FPE and RE expose:

| Endpoint | Purpose |
|---|---|
| `/financial/project/{id}` | Full cash flow projection for one asset |
| `/financial/portfolio/{id}` | Aggregated projection for a portfolio |
| `/financial/metrics/{id}` | IRR, NPV, DSCR, LLCR, payback |
| `/risk/var/{id}` | VaR and CVaR for one asset or portfolio |
| `/risk/stress/{id}` | Stress test results |
| `/risk/tornado/{id}` | Sensitivity of each metric to each source |
| `/insurance/premium/{id}` | Premium, expected loss, combined ratio |
| `/insurance/solvency/{id}` | Solvency capital, coverage ratio |
| `/regulatory/rab/{id}` | RAB roll-forward, allowed revenue, tariff |
| `/tax/liability/{id}` | Annual tax, deferred tax, WHT |
| `/carbon/issuance/{id}` | Credit issuance, buffer, revenue |
| `/portfolio/var` | Portfolio-level VaR |
| `/portfolio/concentration` | HHI, top-N, sector/geo/currency concentration |

### 10.2 Reports

The FPE and RE produce:

- **Asset brief**: 2-page summary for one asset, with cash flow, DSCR, IRR, key risks
- **Portfolio brief**: 10-page summary for the portfolio, with correlations, concentration, VaR
- **Lender pack**: DSCR, LLCR, covenant tests, debt schedule
- **Investor pack**: IRR, NPV, sensitivity, exit analysis
- **Regulator pack**: RAB, allowed revenue, tariff, benchmark, X-factor
- **Insurer pack**: premium, loss ratio, solvency, cat model output
- **Carbon pack**: baseline, additionality, issuance, MRV, buffer

### 10.3 Dashboards

The FPE and RE feed interactive dashboards:

- **Cash flow dashboard**: the full projection, with drill-downs by year and by asset
- **Risk dashboard**: the VaR, CVaR, and tornado diagram, with scenario selection
- **Portfolio dashboard**: the portfolio composition, concentration, and VaR
- **Regulatory dashboard**: the RAB roll-forward, allowed revenue, and tariff
- **Insurance dashboard**: the premium, solvency, and cat model output

---

## Part XI: The Algorithm Stack

### 11.1 Deterministic FPE

| Algorithm | Library | Use |
|---|---|---|
| Cash flow projection | `pandas` | Annual multi-sheet projection |
| Debt sizing | `scipy.optimize` | Fixed-point iteration on DSCR constraint |
| IRR, NPV, PMT | `numpy_financial` | Standard financial functions |
| Depreciation | `numpy` | Straight-line, declining, accelerated |
| Tax calculation | custom | Carryforward, allowance, thin-cap |
| Currency conversion | `forex-python` + custom forward curve | FX conversion and hedging |
| Contract mechanics | custom | PPA, CfD, termination |

### 11.2 Risk engine

| Algorithm | Library | Use |
|---|---|---|
| Monte Carlo | `numpy` | Sampling |
| Latin Hypercube | `pyDOE2` | Stratified sampling |
| Sobol sequences | `scipy.stats.qmc` | Low-discrepancy sampling |
| Copulas | `copulas` | Gaussian, t-copula |
| Convergence diagnostics | custom | Gelman-Rubin on tail metrics |
| VaR, CVaR | `scipy.stats` + custom | Historical, parametric, Monte Carlo |
| Tornado diagram | custom | Sensitivity ranking |

### 11.3 Insurance / catastrophe

| Algorithm | Library | Use |
|---|---|---|
| Cat model | `climada` or `oasis` | Hazard, vulnerability, loss |
| Frequency-severity | `scipy.stats` | Poisson, Negative Binomial, Lognormal |
| Panjer recursion | `scipy` | Aggregate loss distribution |
| Extreme value theory | `scipy.stats.genextreme` | Tail estimation |
| Solvency capital | custom | SCR from VaR |
| Premium pricing | custom | AAL + loading |

### 11.4 Regulatory finance

| Algorithm | Library | Use |
|---|---|---|
| RAB roll-forward | `pandas` | Annual projection |
| Revenue cap | custom | Allowed revenue formula |
| Tariff design | custom | Structure, rebalancing |
| Benchmarking | `scipy.optimize` | DEA or SFA |

### 11.5 Portfolio risk

| Algorithm | Library | Use |
|---|---|---|
| Correlation estimation | `numpy` | From historical returns or scenarios |
| Variance-covariance VaR | `numpy` | Fast approximate VaR |
| Historical simulation | `numpy` | Empirical VaR |
| Monte Carlo VaR | `numpy` | Correlated draws |
| Correlated default | `pyRisk` or `creditrisk` | Vasicek, CreditMetrics, Merton |
| Concentration metrics | custom | HHI, top-N |

---

## Part XII: Implementation Roadmap

### 12.1 Phase 1: Single-asset deterministic FPE (3 months)

- Cash flow projection engine
- Debt sizing iteration
- Tax calculation with carryforward
- Depreciation schedules
- Coverage ratios
- Returns metrics
- Single-currency, single-jurisdiction

**Deliverable:** A single-asset financial model that produces a cash flow and metrics from a PyPSA result.

### 12.2 Phase 2: Multi-asset, multi-currency, multi-jurisdiction (3 months)

- Multiple assets in one portfolio
- Currency ledger and FX conversion
- Multi-jurisdiction tax
- Consolidated reporting

**Deliverable:** A portfolio financial model that handles the complexity of a real African portfolio.

### 12.3 Phase 3: Risk engine (3 months)

- Monte Carlo with Latin Hypercube Sampling
- Correlation copulas
- Stress tests
- VaR and CVaR
- Tornado diagrams

**Deliverable:** A risk model that produces distributions, not just point estimates.

### 12.4 Phase 4: Insurance and catastrophe (4 months)

- Cat model integration (CLIMADA)
- Frequency-severity
- Premium pricing
- Solvency capital
- Reinsurance structures

**Deliverable:** A catastrophe model that prices insurance and computes solvency.

### 12.5 Phase 5: Regulatory finance (3 months)

- RAB roll-forward
- Allowed revenue
- Tariff design
- Benchmarking

**Deliverable:** A regulatory model that computes the utility's regulated economics.

### 12.6 Phase 6: Contract mechanics and carbon finance (2 months)

- PPA, CfD, termination
- Baseline, additionality, issuance
- MRV, buffer

**Deliverable:** The contract and carbon models.

### 12.7 Phase 7: Portfolio risk (2 months)

- Correlation matrix
- Portfolio VaR
- Concentration
- Correlated default

**Deliverable:** The portfolio aggregator.

### 12.8 Phase 8: Integration with PRG and API (2 months)

- Audit of FPE against PRG identities
- Reconciliation of financial parameters
- API endpoints
- Dashboards
- Reports

**Deliverable:** The full integration with the rest of ALEA.

**Total: 20–22 months for a full build, or 12 months for a minimum viable version covering Phases 1–3 and 8.**

---

## Part XIII: What Makes This Model Africa-Specific

A European financial model would not need:

- **Multi-currency** with soft currencies and devaluation risk
- **DFI financing** with concessional terms, blended finance, and grant components
- **Political risk insurance** (MIGA, ATI, private PRI)
- **Sovereign guarantees** on PPAs
- **Off-grid / mini-grid economics** with different cost structures and revenue models
- **Carbon finance** under Article 6 and the voluntary market
- **Debt sustainability constraints** (IMF programme limits)
- **Regulatory reset risk** (the X-factor can be reset, the RAB can be adjusted, the tariff can be frozen)
- **Currency mismatch** between local revenue and USD debt
- **Prepayment metering** and consumer credit risk
- **Community benefit sharing** and local content requirements
- **Just transition funding** and reskilling costs

These are not edge cases in Africa. They are the standard case. The FPE and RE must handle all of them.

---

## Part XIV: What This Model Completes in ALEA

The platform currently has four layers:

1. **PRG** — consistency checker for ~900 parameters
2. **PyPSA-Earth** — physical optimisation engine
3. **Audit** — comparison of solved result to PRG identities
4. **What-if and delivery** — the analytical and delivery surfaces

The FPE and RE complete the chain:

5. **Financial Projection Engine** — turns the physical solution into cash flows
6. **Risk Engine** — turns the cash flows into distributions
7. **Insurance / Regulatory / Contract / Carbon / Tax** — the sub-models that answer the industry-specific questions
8. **Portfolio Risk** — aggregation across assets
9. **Consistency with PRG** — the audit that ties the financial model back to the parameter graph

The result is that ALEA becomes a **full lifecycle decision-support system**: from parameter consistency, through physical optimisation, to financial feasibility, to risk quantification, to the reports that the twenty archetypes actually need.

Without the FPE and RE, ALEA is a planning tool. With them, it is the **continental energy intelligence platform** the specification described.

---

## The Honest Summary

The Financial and Risk Model is the single largest missing piece in the ALEA stack. It is **larger than the PRG**, **larger than the audit**, and **comparable to PyPSA-Earth itself** in scale and importance. It cannot be built in a sprint, and it cannot be built without a small team with financial modelling experience, tax expertise, and risk analytics expertise.

But it is **buildable**, it is **buildable in phases**, and the phases are **independently useful**. A Phase 1 FPE that produces cash flows and IRR for a single asset is already more useful than no financial model at all. A Phase 3 risk engine that produces VaR and stress tests is already more useful than point estimates. A Phase 8 integration that ties the financial model to the PRG is already more useful than a financial model that lives in a spreadsheet.

The choice is not "build it or don't". The choice is **which phase to start with**, and the answer is Phase 1, because everything else depends on it.