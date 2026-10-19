# Citation index

Every work this repository leans on, and where the local copy is.

The rule this file exists to enforce: **a load-bearing citation points at a copy
we hold, not at a URL.** Links rot; a file does not. `00-architecture.md` §6
declares this directory, and `alea.provenance.citations` is the reader that
joins these rows to the citations the tree actually makes.

## The `archived` column

Three states, and the difference between them is the point.

| Value | Means | What the gate does |
|---|---|---|
| `sources/archive/<file>` | A copy is on disk | **Fails** if the file is absent |
| *(empty)* | The work exists and is not archived | Reported and counted, not failed |
| `n/a` | A standard derivation with no single work behind it | Ignored |

The empty state is not a failure because a work behind a paywall or served as a
JavaScript shell cannot be archived by a script, and a gate that refused those
would be a gate nobody could pass. The count is the finding: a register of
twelve works with one archived is a bibliography, not an archive, and nothing
would say so if the register did not.

`n/a` exists so that the five textbook results in the library — the annuity
formula, the WACC identity, the swing equation, average-cost pricing, and the
N-1 criterion — are not recorded as *unarchived works*. There is no paper to
archive. Naming one as their source would fabricate a citation, which is worse
than recording that they have none: a fabricated source is a claim a reader
cannot check, wearing the shape of one they can.

## The `cites` column

Every spelling a citation in the tree uses to reach this row, separated by `;`.
An equation's `reference` is prose written by whoever wrote the equation, so the
join is a substring match rather than a key lookup — demanding an exact match
would mean editing the physics library to satisfy a bibliography.

`alea.provenance.citations.citation_report()` checks the join in **both**
directions: a citation that resolves to no row is a load-bearing claim pointing
at a URL, and a row that no citation reaches is either a work the tree stopped
citing or a row added and never wired.

## Works

| key | work | custodian | year | url | licence | archived | cites |
|---|---|---|---|---|---|---|---|
| irena_power_costs | Renewable Power Generation Costs in 2022 (Executive Summary) | IRENA | 2023 | https://www.irena.org/publications/2023/Aug/Renewable-Power-Generation-Costs-in-2022 | IRENA terms (free to distribute with attribution) | sources/archive/irena_costs_2022_summary.pdf | IRENA renewable cost statistics |
| iea_nea_egc | Projected Costs of Generating Electricity | IEA / NEA | 2020 | https://www.iea.org/reports/projected-costs-of-generating-electricity-2020 | Proprietary (paid report) | | IEA/NEA Projected Costs of Generating Electricity; IEA/NEA, Projected Costs of Generating Electricity |
| entsoe_adequacy | Adequacy studies and the N-1 planning criterion | ENTSO-E | 2023 | https://www.entsoe.eu/outlooks/adequacy/ | ENTSO-E terms (free to distribute with attribution) | | ENTSO-E adequacy studies; N-1 planning criterion |
| who_airq | AirQ+: software tool for health risk assessment of air pollution | WHO | 2023 | https://www.who.int/tools/airq | CC BY-NC-SA 3.0 IGO | | WHO AirQ+ methodology |
| wrights_law | Wright's law: factors affecting the cost of airplanes | Journal of the Aeronautical Sciences | 1936 | https://doi.org/10.2514/8.155 | Proprietary (publisher paywall) | | Wright's law |
| crf_annuity | Capital recovery factor (standard annuity formula) | | | | | n/a | Standard annuity formula |
| wacc_identity | Weighted average cost of capital with the interest tax shield | | | | | n/a | Standard WACC with the interest tax shield |
| average_cost_pricing | Average-cost pricing: fixed cost over units sold, plus short-run marginal cost | | | | | n/a | Average-cost pricing |
| swing_equation | Swing equation at t=0 (df/dt = -P_loss / (2 H S)) | | | | | n/a | Swing equation |
| n1_criterion | N-1 planning criterion | | | | | n/a | Standard N-1 planning criterion |
| nrel_atb_2025 | Annual Technology Baseline 2025, Equations & Variables | NREL | 2025 | https://atb.nlr.gov/electricity/2025/equations_&_variables | Public domain (US govt) | sources/archive/nrel_atb_2025_equations.html | NREL ATB 2025 Equations & Variables; NREL ATB battery equations |
| eia_lcoe_methodology | Levelized Cost of Electricity Methodology (AEO supplement) | EIA | 2024 | https://www.eia.gov/outlooks/aeo/electricity_generation/pdf/LCOE_methodology.pdf | Public domain (US govt) | sources/archive/eia_lcoe_methodology.pdf | EIA AEO LCOE methodology |
| short_1995 | A Manual for the Economic Evaluation of Energy Efficiency and Renewable Energy Technologies, NREL/TP-462-5173 | Short, Packey & Holt | 1995 | https://www.nrel.gov/docs/legosti/old/5173.pdf | Public domain (US govt) | sources/archive/short_packey_holt_1995.pdf | Short, Packey & Holt (1995), NREL/TP-462-5173 |
| ukrn_cost_of_capital | Guidance for regulators on the methodology for setting the cost of capital | UK Regulators Network | 2023 | https://ukrn.org.uk/app/uploads/2023/03/CoC-guidance_22.03.23.pdf | UKRN terms (free) | sources/archive/ukrn_cost_of_capital_2023.pdf | UKRN cost of capital guidance (2023), §allowed returns; UKRN cost of capital guidance (2023), §overall framework; Ofwat PR24 Appendix 11, allowed return on capital |
| eia_demand_elasticities | Review of Key International Demand Elasticities | EIA / Stanford EMF | 2017 | https://www.eia.gov/workingpapers/pdf/key_international_demand_elasticities.pdf | Public domain (US govt) | sources/archive/eia_international_demand_elasticities.pdf | EIA/Stanford EMF demand elasticities |
| burke_csereklyei_2016 | Understanding the energy-GDP elasticity: a sectoral approach | Burke & Csereklyei, ANU CAMA | 2016 | https://crawford.anu.edu.au/sites/default/files/2025-03/45_2016_burke_csereklyei_word.pdf | Author preprint | sources/archive/burke_csereklyei_2016.pdf | Burke & Csereklyei 2016 |
| world_bank_regulation | Regulation of Utilities handbook (revenue caps, pass-through) | World Bank | | https://elibrary.worldbank.org | World Bank terms | | World Bank Regulation of Utilities handbook, revenue caps; Pass-through pricing |
| fuel_tables | Standard fuel properties: LHV of ammonia 18.6 GJ/t, hydrogen 33.33 kWh/kg, 5.8 MMBtu/barrel crude, 0.29307 MWh/MMBtu HHV | | | | | n/a | LHV of NH3: 18.6 GJ/t (standard fuel tables); LHV of H2: 33.33 kWh/kg (standard fuel tables); EIA conversion basis (5.8 MMBtu/barrel); Physical constant: 1 MMBtu = 0.29307 MWh (HHV); EIA conversion basis (5.8 MMBtu/barrel); physical constant 0.29307 MWh/MMBtu |
| catalog_method_cells | The catalog's own method cells as coupling provenance (bottom-up synthesis, rate-of-return) | | | | | n/a | Bottom-up load synthesis (catalog method cell) |
| fragments_alias_register | The generated fragments' alias register, applied as equality equations | | | | | n/a | The fragments' alias register (docs/param_batch7.md and successors), applied |
| leontief_multipliers | Input-output employment multipliers (the demand-pull chain) | | | | | n/a | Leontief input-output employment multipliers |
| lazar_lcos | Levelized Cost of Storage methodology | Lazard | | | Proprietary (free to distribute) | | Lazard LCOS |
| standard_fiscal | Rate-based levy and allowance definitions | | | | | n/a | Rate-based levy and allowance definitions (standard fiscal accounting) |
| composition_shares | Composition-target shares in employment planning | | | | | n/a | Composition-target shares (planning policy) |
| marginal_cost_split | The shipped marginal-cost definition, restated as its variable part | | | | | n/a | The shipped marginal-cost definition, split |
| catalog_duplicate_resolutions | The catalog's own duplicate rows, resolved by equality (the coupling batches' alias equations) | | | | | n/a | The catalog's own duplicate rows, resolved |
| bis_credit_spread | Credit-spread decomposition: borrower rate = policy rate + borrower premium | | | | | n/a | Credit-spread decomposition (BIS) |
| fisher_equation | The Fisher equation: nominal = (1 + real)(1 + inflation) | | | | | n/a | The Fisher equation |
| vat_tariffs | VAT applied to electricity tariffs | | | | | n/a | VAT applied to electricity tariffs |
| stoft_2002 | Power System Economics: Designing Markets for Electricity | Steven Stoft | 2002 | | Proprietary (textbook) | | Stoft 2002, Power System Economics, ch. 5 |
| cbam_regulation | EU Carbon Border Adjustment Mechanism; EU ETS allowance levels | European Commission | 2026 | | EU terms | | EU CBAM regulation; EU ETS allowance level 2026 |
| benefit_sharing_shares | Benefit-sharing programme shares, applied through the graph's own revenue identity | | | | | n/a | Benefit-sharing programmes (the graph's own revenue identity) |
| guarantee_risk_pricing | Guaranteed-offtake risk pricing in PPA markets | | | | | n/a | Guaranteed-offtake risk pricing (PPA market practice) |
| fiscal_definitions | Rate-based levy, allowance and composition-share definitions | | | | | n/a | Rate-based levy and allowance definitions (standard fiscal accounting); Composition-target shares (planning policy) |
| pass_through_pricing | Pass-through pricing rules in utility tariff design | | | | | n/a | Pass-through pricing |
| irena_jobs_2024 | Renewable energy and jobs: Annual review 2024 | IRENA / ILO | 2024 | https://www.irena.org/Publications/2024/Oct/Renewable-energy-and-jobs-Annual-review-2024 | IRENA terms (free) | sources/archive/irena_jobs_2024.pdf | Leontief input-output employment multipliers; IRENA employment factors |
| ieee_1366_tutorial | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck; IEEE Std 1366 (distribution reliability) | IEEE Boston PES | 2019 | https://site.ieee.org/boston-pes/files/2019/03/IEEE-1366-Reliability-Indices-2-2019.pdf | IEEE (c) | sources/archive/ieee_1366_reliability_tutorial.pdf | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck; IEEE Std 1366 (distribution reliability) |
| hou_2008_china | Electricity Consumption and Economic Growth in China: Multivariable Cointegration Analysis | Hou & Tan, North China Electric Power University | 2008 | https://doi.org/10.1109/wicom.2008.1932 | Proprietary (IEEE paywall) | | Hou & Tan 2008; Electricity Consumption and Economic Growth in China |
| shan_baoguo_2017 | 经济转型时期电力弹性系数应用 (Electricity elasticity coefficient in the transition period) | 单葆国 et al., 中国电力 | 2017 | https://www.electricpower.com.cn/CN/volumn/volumn_1202.shtml | Proprietary (CNKI) | | 单葆国 2017 |
| tejada_2023 | Multi-year Investment Modelling in Energy Systems | Tejada-Arango, JRC | 2023 | https://arxiv.org/abs/2307.16842 | arXiv (open) | sources/archive/tejada_multiyear_investment_2023.html | Tejada-Arango (2023), arXiv:2307.16842 |
| gep_review_2017 | Generation expansion planning optimisation with renewable energy integration: a review | Oree, Sayed Hassen & Fleming | 2017 | https://eprints.whiterose.ac.uk/id/eprint/111487/1/Generation%20expansion%20planning%20optimisation%20with%20renewable%20energy%20integration%20a%20review-1.pdf | Author accepted MS | sources/archive/whiterose_gep_review_2017.pdf | Oree et al. (2017), RSER 69:790-803 |
| damodaran_ctryprem_2026 | Country Default Spreads and Risk Premiums (table last updated 2026-01-05) | Aswath Damodaran, NYU Stern | 2026 | https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html | Author terms (free) | sources/archive/damodaran_ctryprem_2026-01.html | Damodaran (2026), Country Default Spreads and Risk Premiums |

## Digests of the archived copies

A re-download of the same URL is not necessarily the same bytes — a publisher
reissues a report under the same filename — so a register that records only a
path cannot tell a replaced copy from the original. The digest is what makes
the row evidence rather than a pointer.

| file | sha256 |
|---|---|
| sources/archive/nrel_atb_2025_equations.html | bb6a1ef14523205ea38935f654a860af9724a7fa117beb5d86960dc4ca8e8014 |
| sources/archive/eia_lcoe_methodology.pdf | 6c0d95f5b76d8a43446ac7e81305ab94d4f74cb025df9f6e116211d7c1d3bde1 |
| sources/archive/ukrn_cost_of_capital_2023.pdf | a250cb9e98e7eb5e6be610593816d18ee65a834a703ec32b20be5a236bde096b |
| sources/archive/eia_international_demand_elasticities.pdf | b6ef533ba00b951b86b14adaa9dfb11584908d707717091aae0729f4d915f5b8 |
| sources/archive/burke_csereklyei_2016.pdf | 98618ca1b20ae0ac1effbe87920ff74b8f3ba06b55dd4b4a1093ade3720de73a |
| sources/archive/short_packey_holt_1995.pdf | 12c7c9d00d137c31a16bbff1cdc8fe560de1ebabbf6dff13d3e033686ac3e799 |
| sources/archive/irena_jobs_2024.pdf | 876b4131d0d3a35fe3c2159faf0ff34828ac6d3b19f4ada8b29653f0da4c24a5 |
| sources/archive/ieee_1366_reliability_tutorial.pdf | 0150dcf4ba808c0c767b7106ce3a0e100c0edc46bb5972bf9bd4cff29e4d639b |
| sources/archive/tejada_multiyear_investment_2023.html | d94fefb0630a98f09f8082af4e893faa4551ff1ef580bcc55a9d9ebe0e6b991b |
| sources/archive/whiterose_gep_review_2017.pdf | 6af91da2cc10681dc2e58301546d4026005edf4e4df7b3a43bc57e6c5c70b036 |
| sources/archive/irena_costs_2022_summary.pdf | b04c0d5234e2d2bfeb38960e76b6409741f3e478cd7a71a772d924b8e70ced0e |
| sources/archive/damodaran_ctryprem_2026-01.html | ea30d57fc0858072c520930e2e5b8a5e5affdce81f7f2e1f9054efab79959dbc |

## Why five rows are `n/a`

It is worth being explicit, because a reader who sees five rows with no custodian
will assume the register is incomplete rather than that the citations are a
different kind of claim.

`crf_definition` cites "the standard annuity formula". `wacc_definition` cites
"the standard WACC with the interest tax shield". `rocof_definition` cites "the
swing equation at t=0". `tariff_cost_recovery` cites "average-cost pricing".
`reserve_margin` cites "the standard N-1 planning criterion".

Each names a *derivation*, not a work. They are in every power-systems textbook
and no one of them is the source: the equation is correct because the algebra is,
and the citation is telling the reader which textbook result is being used rather
than attributing a number to a measurement. An entry with a plausible-looking
paper attached would be the more comfortable row and the less honest one.

The four that *do* name a custodian are the ones where a specific institution's
figure or method is being adopted — IRENA's cost statistics for the learning
curve, WHO's concentration-response function for premature deaths, ENTSO-E's
adequacy practice for the reserve margin, and IEA/NEA's LCOE definition.

## Rebuilding a copy

`sources/archive/` is tracked, not ignored, so a clean clone carries the copies
the register claims. To add one:

```bash
curl -L -A "Mozilla/5.0" -o sources/archive/<file> "<url>"
shasum -a 256 sources/archive/<file>
```

Record the path in the `archived` column and the digest in the row's note. The
digest matters because a re-download of the same URL is not necessarily the same
bytes, and a register that cannot tell a replaced copy from the original is a
register that has stopped being evidence.
