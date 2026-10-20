# Coupling pack: macro-fiscal, land-heritage, and insurance notional

## What this pack covers

Twenty nodes: the macro block (`balance_of_payments`, `current_account_balance`,
`external_debt`, `debt_sustainability`, `foreign_direct_investment`,
`official_development_assistance`, `foreign_exchange_reserves`,
`remittance_flows`, `remittance_dependency`, `exchange_rate_volatility`,
`currency_hedge_cost`), the fiscal and subsidy pair (`capital_gains_tax`,
`lpg_subsidies`), the land-heritage triple (`archaeological_sites`,
`sacred_sites`, `protected_areas`), the insurance pair
(`parametric_insurance`, `parametric_insurance_coverage`) plus
`weather_derivatives`, and the geopol stock `strategic_reserves`.

Ten of the twenty close: seven become an equation's `lhs`, three become a named
rhs operand of a new equation. Ten defer, and seven of those ten defer on the
same two absent levels — a GDP level and an import bill in currency. That is the
pack's headline finding and it is not a modelling choice: no formula inside this
slice can produce either, so the macro block cannot close until those bases are
declared elsewhere.

The second finding is about citation. Eight of the nine proposed equations carry
`reference: None`, and that is correct rather than lazy: every one of them is a
*definitional* identity — a share times its base, a density times an area, a rate
times a volume. The literature this slice needs is behind the *bases*, not behind
the products, and none of the base works is archived. `## Sources to fetch`
names them. A batch that cited a paper for `share × base` would be dressing a
unit conversion as a measurement.

## Rows

`kind` is `derive` (the node becomes an `lhs`) or `read` (the node becomes an rhs
operand of a named new equation). `role`/`det` is the role and determinism the
batch should ship. Range is `[low, high]`.

| node | class | kind | unit | range | role / det | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `archaeological_sites` | BASE-NEEDED | derive | `sites` (retyped from `None`) | `[0, 1500]` — image of density ≤30/100 km² over a land take ≤500,000 ha | derived / stochastic | `archaeological_sites = archaeological_sites_density * land_area_hectares / 10000` | Expected count of recorded archaeological sites inside the project footprint: the measured site density per 100 km² times the land take converted to the density's own denominator. A fractional value is the expectation, not a count of objects, which is what a survey budget needs. | `None` — definitional | A count over a `study_area_km2` (that base does not exist); a count of *known* sites from a heritage register (no register in the graph) |
| `sacred_sites` | BASE-NEEDED | derive | `sites` (retyped from `None`) | `[0, 1000]` — image of density ≤20/100 km² over the same land take | derived / stochastic | `sacred_sites = sacred_sites_density * land_area_hectares / 10000` | Expected count of sacred and culturally significant sites inside the project footprint. Same construction as `archaeological_sites`, on the sacred-site density layer, so a siting decision can compare the two exposures directly. | `None` — definitional | A count over a regional study area; a single combined heritage count (the two layers are separate measurements and must stay separable) |
| `protected_areas` | BASE-NEEDED | derive | `hectare` (retyped from `None`) | `[0, 500000]` — a fraction ≤1 of a land take ≤500,000 ha | derived / policy | `protected_areas = protected_area_fraction * land_area_hectares` | Hectares of the project footprint falling inside a protected area: the overlap share times the land take. An area rather than a count, because what a protected-area designation constrains is the ground you may disturb, not the number of sites. | `None` — definitional | A count of protected areas intersecting the site (an area is what the constraint binds); a national coverage share applied to the project (that is a different object and would overstate the overlap) |
| `parametric_insurance` | BASE-NEEDED | derive | `USD million` (retyped from `1`) | `[0, 500000]` — coverage ≤1 × AAL ≤500,000 USD million | derived / policy | `parametric_insurance = parametric_insurance_coverage * aal_usd_million` | The loss a parametric instrument pays out in an average year: the share of the loss its trigger covers times the expected annual loss. Priced against `aal_usd_million`, the base the finance batch already ships, so the payout and the premium that covers it sit on one base. | `None` — definitional | `expected_annual_loss_usd` (absent, and `aal_usd_million` is the same quantity already declared); a payout capped by the sum insured (a `min`, which the DSL cannot differentiate) |
| `parametric_insurance_coverage` | BASE-NEEDED | read | `1` (unchanged) | `[0, 1]` — a share | free / policy | `--` (rhs of `parametric_insurance`) | Unchanged. The share of the loss the instrument covers when its trigger fires; already correctly typed and defaulted at 0.5. It closes by being named in the payout identity. | no equation, so no `reference`. The node's `source` field reads "CCRIF parametric instrument documentation", which matches no `INDEX.md` row and must not be promoted into a citation. | Retyping it as a USD payout (it is a share, and the payout is the other node) |
| `remittance_flows` | BASE-NEEDED | derive | `USD/year` (retyped from `None`) | `[0, 50000000000000]` — image of share ≤0.5 × income ≤1,000,000 USD/yr × households ≤100,000,000 | derived / stochastic | `remittance_flows = remittance_income_share * household_income_usd_per_year * households_total` | Remittances received per year: the share of household income arriving as transfers, times household income, times the number of households. Measured against the household income base rather than GDP, because remittances are a household transfer and the household base is the one the graph carries. | `None` — definitional | A GDP share (no GDP level exists — this is the pack's one genuine escape from the classification pack's verdict); a per-migrant transfer × migrant stock (no migrant count) |
| `strategic_reserves` | BASE-NEEDED | derive | `TWh` (retyped from `None`) | `[0, 20000]` — days ≤365 × demand ≤20,000 TWh / 365 | derived / policy | `strategic_reserves = strategic_reserve_days * demand_twh / 365` | The strategic stock held, as a volume of energy: the days of cover the policy declares, times annual demand, over the days in a year. **Days of total demand, not days of net imports** — the IEA convention is import cover, and the import-based version is rejected below. | `None` — definitional | `strategic_reserve_days * net_imports_twh / 365` (net imports are 0.0 at defaults, so the stock is zero, and the flow is signed so the product is signed — the `abs` that would fix it has no derivative rule); a stock in days with no volume (the node is consumed as a volume by anything that compares it to demand) |
| `weather_derivatives` | BASE-NEEDED | derive | `USD/year` (retyped from `1`) | `[0, 1000000000000]` — share ≤1 × revenue ≤1e12 USD/yr | derived / policy | `weather_derivatives = weather_derivative_notional_share * total_revenue_usd_per_year` | The notional of the weather hedge carried, in currency per year: the share of revenue the firm hedges, times revenue. A notional against revenue rather than a "weather-sensitive revenue" base, because the revenue the derivative protects is the revenue the firm actually books. | `None` — definitional | `weather_sensitive_revenue_usd` (absent, and splitting revenue by weather sensitivity would invent a coefficient); a payout expectation (that is the parametric instrument's job, not the derivative's) |
| `currency_hedge_cost` | BASE-NEEDED | read | `1/year` (retyped from `None`) | `[0, 0.2]` — an annual cost as a share of the hedged notional | free / policy | `--` (rhs of `currency_hedge_cost_usd_per_year`) | The annual cost of hedging currency exposure, as a share of the notional hedged: the forward premium plus the dealer spread. A rate, so the charge is `rate × notional` and the notional is built from the debt the project actually carries. | `None` — definitional | The node as a `USD/year` charge (the catalog's own `_usd_per_year` convention puts the charge on a suffixed id, as `transaction_costs` → `transaction_cost_usd_per_year`); `rate × fx_denominated_debt_usd` (that base is absent) |
| `lpg_subsidies` | BASE-NEEDED | read | `USD/kg` (retyped from `None`) | `[0, 5]` — a per-kg subsidy up to the full retail price | free / policy | `--` (rhs of `lpg_subsidy_spend_usd_per_year`) | The subsidy per kilogram of LPG, in currency. A per-unit rate, matching the three electricity subsidy siblings (`electricity_subsidies`, `fossil_fuel_subsidies`, `renewable_subsidies`, all `USD/MWh`), so the spend is `rate × volume` across the whole subsidy family. | `None` — definitional | A share of cost (the sibling subsidies are per-unit rates, and a share would need an LPG retail price the graph does not carry) |
| `capital_gains_tax` | BASE-NEEDED | defer | `1` (already correct) | `[0, 0.4]` — already correct | free / policy | `--` | Already well-typed and well-ranged: a rate on realised gains, defaulted at 20%. It cannot close because the graph holds no realised-gain line to apply it to, and inventing one would fabricate the base the rate is defined against. | no equation, so no `reference`. The node's `source` field reads "OECD Corporate Tax Statistics", which matches no `INDEX.md` row and is a data custodian, not a citation — it must not be promoted into one. | `capital_gains_tax * total_revenue_usd_per_year` (revenue is not a capital gain — it would tax the whole turnover at the CGT rate); `capital_gains_tax * (capex × capacity × 1000)` (asset value is not a realised gain) |
| `balance_of_payments` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred. A balance of payments is an accounting statement whose balance is identically zero once every credit and debit is counted, so a single non-negative number named "balance of payments" is a category error before it is a missing base. The quantity worth coupling is the current-account balance or the overall balance, and both need a GDP level. | — | `current_account_share_of_gdp * gdp_usd_per_year` (no GDP level; and it would make this node a synonym of `current_account_balance`, coupling one node to a duplicate of another) |
| `current_account_balance` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred on `gdp_usd_per_year`. Also needs a signed range: a current-account balance is negative in a deficit year, and the node's `[0, 1e6]` cannot represent one. Retyping to a signed `USD/year` range is a prerequisite for any formula. | — | `current_account_share_of_gdp * gdp_usd_per_year` (correct in form, blocked on the base); a trade-balance proxy from `net_imports_twh` (a quantity, not a value, and signed) |
| `external_debt` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred on `gdp_usd_per_year`. The project's own debt stock is computable (`debt_fraction × capex × capacity × 1000` = 8.4e9 USD at defaults) but it is the project tranche, not the sovereign's external debt — a different object with a different owner. | — | The project tranche as external debt (wrong object); `external_debt_share_of_gdp × gdp` (correct in form, blocked) |
| `debt_sustainability` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred. The node's name is a *verdict*, not a quantity: sustainability is a threshold test on a debt ratio, and the graph's arithmetic produces quantities. The honest quantity is `external_debt / gdp_usd_per_year` (a ratio in years), which needs the GDP level; the verdict belongs in a cross-validation rule once the ratio exists. | — | `external_debt / gdp_usd_per_year` (blocked, and it is a debt ratio, not a sustainability verdict — shipping it under this name would state more than it measures) |
| `foreign_direct_investment` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred on `gdp_usd_per_year`. | — | `fdi_share_of_gdp × gdp` (correct in form, blocked) |
| `foreign_exchange_reserves` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred on `imports_usd_per_year` *and* `reserve_cover_months`. Reserve adequacy is measured as months of import cover, so both the cover dial and the import bill in currency are needed; the graph carries neither, and `net_imports_twh` is a quantity. | — | `reserve_cover_months * imports_usd_per_year / 12` (correct in form, blocked on both operands); a reserves figure derived from the project's own revenue (wrong object entirely) |
| `official_development_assistance` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred on `gdp_usd_per_year`. | — | `oda_share_of_gdp × gdp` (correct in form, blocked) |
| `remittance_dependency` | BASE-NEEDED | defer | — | — | free / — | `--` | Deferred, and this one is a definitional choice rather than a missing operand. `remittance_flows / (household_income_usd_per_year × households_total)` is dimensionally sound and computable today, but it measures remittances as a share of *household income* — not the quantity the name denotes in the literature, which is a share of GDP. Shipping it under this name would put a true number behind a false label. | — | The household-income ratio (computable, wrong quantity — see prose); `remittance_flows / gdp_usd_per_year` (the right quantity, blocked) |
| `exchange_rate_volatility` | BASE-NEEDED | defer | — | — | free / stochastic | `--` | Deferred. A volatility is a second moment of a return series; the graph holds a single exchange-rate level and the DSL has no operator over a series. The catalog's own method cell is `arch` (GARCH), which is an external fit, not a graph identity. | — | `stdev(exchange_rate_usd_local)` (a single level has no deviation, and `stdev` over a series is outside the grammar); a proxy from `currency_risk_premium` (a priced premium is not a measured volatility) |

## New nodes this pack proposes

Each is an operand or a product the equations above require. All are new ids; none
collides with the 1,296 shipped nodes.

| node | unit | range | default | role / det | why |
|---|---|---|---|---|---|
| `protected_area_fraction` | `1` | `[0, 1]` | `0.0` | free / policy | The overlap share. Default 0 because no protected-area layer is in the graph: a default of 0.17 would claim a sixth of every project sits inside a designation, which is a fabricated measurement. The range admits any measured overlap. |
| `remittance_income_share` | `1` | `[0, 0.5]` | `0.05` | free / policy | Share of household income arriving as transfers. 5% is the order remittance-receiving economies show; the range admits up to half, which is the ceiling for a household that is mostly transfer-funded. |
| `strategic_reserve_days` | `day` | `[0, 365]` | `90.0` | free / policy | The cover the policy declares. 90 days is the IEA emergency-stockholding convention; the range runs to a full year so a policy that declares more is expressible rather than clipped. |
| `foreign_currency_debt_share` | `1` | `[0, 1]` | `0.6` | free / policy | Share of the debt stock denominated in foreign currency — the notional that needs hedging. 60% is the order for an EM project financed in hard currency. |
| `lpg_use_kg_per_household_year` | `kg/year` | `[0, 1000]` | `150.0` | free / policy | LPG burnt by a household that uses it: roughly a 12.5 kg cylinder every five weeks. A mass balance, not a measurement. |
| `weather_derivative_notional_share` | `1` | `[0, 1]` | `0.1` | free / policy | Share of revenue hedged with weather derivatives. |
| `currency_hedge_cost_usd_per_year` | `USD/year` | `[0, 1000000000000]` | — (derived) | derived / policy | The charge. Image of the operands: 0.2 × 1 × 0.95 × 5000 × 1,000,000 × 1000 = 9.5e11. |
| `lpg_subsidy_spend_usd_per_year` | `USD/year` | `[0, 500000000000]` | — (derived) | derived / policy | The spend. Image: 5 USD/kg × 1 × 1e8 × 1000 kg = 5e11. |

## Equation ids, systems, and the measured gates

| equation id | system | lhs = rhs |
|---|---|---|
| `archaeological_sites_definition` | `financial` | `archaeological_sites = archaeological_sites_density * land_area_hectares / 10000` |
| `sacred_sites_definition` | `financial` | `sacred_sites = sacred_sites_density * land_area_hectares / 10000` |
| `protected_areas_definition` | `financial` | `protected_areas = protected_area_fraction * land_area_hectares` |
| `parametric_insurance_definition` | `financial` | `parametric_insurance = parametric_insurance_coverage * aal_usd_million` |
| `remittance_flows_definition` | `financial` | `remittance_flows = remittance_income_share * household_income_usd_per_year * households_total` |
| `strategic_reserves_definition` | `energy_balance` | `strategic_reserves = strategic_reserve_days * demand_twh / 365` |
| `weather_derivatives_definition` | `financial` | `weather_derivatives = weather_derivative_notional_share * total_revenue_usd_per_year` |
| `currency_hedge_cost_usd_per_year_definition` | `financial` | `currency_hedge_cost_usd_per_year = currency_hedge_cost * foreign_currency_debt_share * debt_fraction * capex_usd_per_kw * total_capacity_mw * 1000` |
| `lpg_subsidy_spend_usd_per_year_definition` | `financial` | `lpg_subsidy_spend_usd_per_year = lpg_subsidies * cooking_lpg_penetration * households_total * lpg_use_kg_per_household_year` |

`lpg_subsidy_spend_usd_per_year` cites the `standard_fiscal` / `fiscal_definitions`
row (`archived: n/a`), whose citation string is exactly:

    Rate-based levy and allowance definitions (standard fiscal accounting)

Author it on **one line**: the join is a substring test, so a reference broken
across a newline resolves to nothing. A per-unit subsidy is a rate-based levy with
the sign flipped, which is the same identity `withholding_tax_interest_usd_per_year`
uses.

Run against a copy of `config/prg.yaml` with these nodes and equations applied
(the shipped file is untouched):

- **Symbol check** over all nine right-hand sides: every symbol resolves to a
  declared node. No invented operands.
- **Unit check** (`check_equation`): 9 of 9 decidable and consistent —
  `[site] = [site]`, `[length]² = [length]²`, `[currency] = [currency]`,
  `[currency]/[time] = [currency]/[time]`, `[mass][length]²/[time]²` both sides.
- **`lhs` on rhs**: none. All nine solve on the affine path (`solve_paths` returns
  `affine` for every one), so no bracket search runs.
- **Defaults gate**: `range_excursions()` empty, `consistency()` zero violations,
  `propagate()` at defaults clean. No `abs`/`min`/`max`/`floor`/`ceil` anywhere.
- **Values at defaults**: `archaeological_sites` 0.5 sites, `sacred_sites` 0.5
  sites, `protected_areas` 0.0 ha (the overlap share defaults to 0 — see the
  `protected_area_fraction` row), `parametric_insurance` 25.0 USD million,
  `remittance_flows` 2.0e9 USD/yr, `strategic_reserves` 11.475 TWh,
  `weather_derivatives` 6.487e8 USD/yr, `currency_hedge_cost_usd_per_year`
  1.512e8 USD/yr, `lpg_subsidy_spend_usd_per_year` 6.0e7 USD/yr.
- **Uncoupled after the batch**: 10 of the 20 remain, all in the `defer` rows.

Two arithmetic notes a reviewer will want:

The `/ 10000` in the site counts is exact, not a fudge. The density unit is
`sites/100km2`; the graph normalises that string to `sites/km²` (the numeric
denominator is dropped by `_parse_unit`), and one hectare is 0.01 km², so
`hectares / 10000` is hectares expressed in units of 100 km². `unit_of` reports
the walker's residual as `hectare * sites / kilometer**2`, which reduces to
`[site]` — the ratio is dimensionless, which is why the check passes. The same
trap the carbon pack records for TWh↔MWh applies: the constant carries the scale,
the dimension carries the check.

The `1000` in the hedge charge is the kW→MW conversion, exactly as in
`sovereign_risk_charge_usd_per_year` and `technology_risk_charge_usd_per_year`,
which this equation is deliberately shaped after.

## Dependencies

Operands the pack needs that belong to no slice here. None is proposed above.

| operand | unit | blocks | why this pack cannot declare it |
|---|---|---|---|
| `gdp_usd_per_year` | `USD/year` | `balance_of_payments`, `current_account_balance`, `external_debt`, `debt_sustainability`, `foreign_direct_investment`, `official_development_assistance`, `remittance_dependency` | A level, not a rate. `gdp_growth` and `gdp_growth_rate` exist but a growth rate cannot produce a level without a base year's level, which is the same absent node. |
| `imports_usd_per_year` | `USD/year` | `foreign_exchange_reserves` | No import value in currency. `net_imports_twh` is a quantity, `import_duty_cost_usd` is a duty on equipment, not a bill. |
| `reserve_cover_months` | `month` | `foreign_exchange_reserves` | The cover dial. Absent, and it is the other half of the identity. |
| `realised_capital_gain_usd_per_year` | `USD/year` | `capital_gains_tax` | No disposal or gain line exists anywhere in the graph; there is no salvage, terminal-value or divestment node to build one from. |
| a foreign-exchange return series | `USD/local` over time | `exchange_rate_volatility` | The graph holds one level (`exchange_rate_usd_local`, `unit=None`, default 500000). A series is a different node type and the DSL has no second-moment operator. |
| `exports_usd_per_year` | `USD/year` | `debt_sustainability` (alternative denominator) | The DSA framework offers PV-of-debt-to-exports as well as debt-to-GDP. Both denominators are absent; naming the second is what makes the defer a finding about the graph rather than about one missing node. |

Operands this pack *consumes*, all already declared: `land_area_hectares`,
`archaeological_sites_density`, `sacred_sites_density`,
`household_income_usd_per_year`, `households_total`, `aal_usd_million`,
`demand_twh`, `total_revenue_usd_per_year`, `debt_fraction`, `capex_usd_per_kw`,
`total_capacity_mw`, `cooking_lpg_penetration`. Three of them gain their first
reader from this batch: `archaeological_sites_density` and
`sacred_sites_density` currently have none, and `cooking_lpg_penetration` has
none — the LPG spend identity is its first use.

## Rejected

- **`strategic_reserve_days * net_imports_twh / 365`** (the classification pack's
  proposal). `net_imports_twh` is 0.0 at defaults, so the stock is exactly zero —
  a strategic reserve of nothing, at the default scenario, from a correct formula.
  It is also signed, so a net-exporting scenario yields a negative stock, and the
  `abs` that would fix the sign has no derivative rule. The demand basis is used
  instead, and the prose says it is days of demand rather than days of import
  cover. That is a *different, larger* object than the IEA convention and the
  pack does not pretend otherwise.
- **`expected_annual_loss_usd` for the parametric pair.** The classification pack
  blocked both nodes on it. The base does not exist and does not need to:
  `aal_usd_million` is the same quantity, already declared and already read by
  `insurance_premium_usd_million` and `solvency_capital`. Coupling the payout to
  the premium's own base is strictly better than declaring a second spelling of
  one quantity, which is the duplicate-row defect the alias register exists to
  remove.
- **A GDP-denominated `remittance_dependency`.** The right quantity, blocked on
  the base. The computable alternative — a share of household income — is
  rejected because it would put a true number behind a false label. Recorded in
  the row, not silently shipped.
- **`remittance_flows` on a GDP share.** The classification pack's verdict that
  this node needs `gdp_usd_per_year` is wrong. Remittances are a household
  transfer; the household income base exists and the product is exact. This is
  the pack's one genuine escape from a classification verdict.
- **`capital_gains_tax * total_revenue_usd_per_year`** and **`× asset value`.**
  Both close the node and both are wrong: revenue is not a realised gain and
  asset value is not one either. A rate whose base does not exist should not be
  given a fabricated base to make a coverage count go up.
- **`external_debt / gdp_usd_per_year` as `debt_sustainability`.** Blocked, and
  even unblocked it is a debt ratio in years, not a sustainability verdict.
  Shipping it under this name would answer a question the arithmetic does not
  ask.
- **A `min` cap on the parametric payout at the sum insured.** The DSL cannot
  differentiate `min`; the range on `parametric_insurance` is widened to admit
  the uncapped image instead, and the prose says the payout is the covered
  expected loss rather than the lesser of that and a limit.
- **`rate × fx_denominated_debt_usd` for the hedge.** Correct in form, blocked on
  the base. The project's own debt stock is computable from `debt_fraction`,
  `capex_usd_per_kw` and `total_capacity_mw`, so the hedge notional is built from
  the debt the project actually carries, scaled by the foreign-currency share.
- **A `study_area_km2` base for the land-heritage triple.** The classification
  pack blocks all three on it, and it does not exist. `land_area_hectares` does,
  and it is the *better* base for a developer's question: the sites that matter
  for a survey budget are the ones inside the footprint, not the ones in the
  region. The pack states the object plainly rather than substituting silently —
  these are expected counts inside the project boundary, and a regional density
  applied to a project footprint will understate the regional total by
  construction.
- **`current_account_balance` as a synonym of `balance_of_payments`.** A balance
  of payments is identically zero once all components are counted; coupling both
  nodes to one identity would create two ids for one quantity and a coverage
  count that claims two closures for one equation.
- **`cooking_lpg_penetration × population_total / 5`** as the LPG household
  count. `households_total` is already derived as `population_total /
  persons_per_household`; re-deriving it with a hardcoded 5 would be a second
  spelling of a shipped identity.

## Sources to fetch

The nine identities above need no paper. The *bases* do, and none of the works
below is archived — `sources/INDEX.md` carries nothing on national accounts,
remittance measurement, emergency stockholding, protected-area extent, FX
hedging, or parametric insurance design. Each must be fetched and archived before
a batch cites it; until then the equations ship `reference: None` and this
section is the record of why.

| work | what it would source | nodes |
|---|---|---|
| IMF, *Balance of Payments and International Investment Position Manual* (BPM6) | the current-account and overall-balance definitions, and the fact that the BoP balance is identically zero | `balance_of_payments`, `current_account_balance` |
| World Bank / IMF, *Debt Sustainability Framework for Low-Income Countries* | the PV-of-debt-to-GDP and PV-of-debt-to-exports ratios, and the thresholds that turn a ratio into a verdict | `debt_sustainability`, `external_debt` |
| World Bank, *Migration and Development Brief* | the remittance definition, the household-survey basis, and remittances-to-GDP as the standard dependency measure | `remittance_flows`, `remittance_dependency` |
| IEA, *Oil Stocks of IEA Countries* (or the IEA emergency-response mechanism) | the 90-day net-import stockholding convention, and why the basis is net imports rather than demand | `strategic_reserves` |
| UNEP-WCMC / IUCN, *World Database on Protected Areas* | the protected-area extent layer that `protected_area_fraction` is measured from | `protected_areas` |
| A heritage-site register (UNESCO WHC, or a national antiquities register) | the site-density layers' provenance, and the survey-radius convention that turns a density into an expected count | `archaeological_sites`, `sacred_sites` |
| BIS or an EM central-bank working paper on FX hedging costs | the forward-premium-plus-spread decomposition, and the order of the annual cost as a share of notional | `currency_hedge_cost`, `currency_hedge_cost_usd_per_year` |
| World Bank / IFC or CCRIF, *parametric insurance design* | the coverage-share identity and the trigger-to-payout structure | `parametric_insurance`, `parametric_insurance_coverage` |
| A catastrophe-modelling or weather-derivative text | the notional-versus-exposure relation for a weather hedge | `weather_derivatives` |
| OECD, *Corporate Tax Statistics* (already the node's `source`, not its citation) | the realised-gain base the CGT rate applies to — which is a data question, not a paper | `capital_gains_tax` |

One note on the citation rule for whoever authors the batch: `standard_fiscal`
and `fiscal_definitions` are `n/a` rows, so citing them adds no archive
obligation. Everything else in the table above does.
