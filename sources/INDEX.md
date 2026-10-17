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
| nrel_atb_2025 | Annual Technology Baseline 2025, Equations & Variables | NREL | 2025 | https://atb.nlr.gov/electricity/2025/equations_&_variables | Public domain (US govt) | sources/archive/nrel_atb_2025_equations.html | The LCOE/FCR/CRF equation set the technology LCOE family implements |
| eia_lcoe_methodology | Levelized Cost of Electricity Methodology (AEO supplement) | EIA | 2024 | https://www.eia.gov/outlooks/aeo/electricity_generation/pdf/LCOE_methodology.pdf | Public domain (US govt) | sources/archive/eia_lcoe_methodology.pdf | The fixed-charge-annuity LCOE form: (FCF·CAPEX + FOM)/hours + VOM + fuel − credits |
| short_1995 | A Manual for the Economic Evaluation of Energy Efficiency and Renewable Energy Technologies, NREL/TP-462-5173 | Short, Packey & Holt | 1995 | https://www.nrel.gov/docs/legosti/old/5173.pdf | Public domain (US govt) | | The origin of the FCR/CRF LCOE method every later guide restates |
| ukrn_cost_of_capital | Guidance for regulators on the methodology for setting the cost of capital | UK Regulators Network | 2023 | https://ukrn.org.uk/app/uploads/2023/03/CoC-guidance_22.03.23.pdf | UKRN terms (free) | sources/archive/ukrn_cost_of_capital_2023.pdf | Regulatory WACC = gearing·Kd + (1−gearing)·Ke over notional gearing, applied to RAB |
| eia_demand_elasticities | Review of Key International Demand Elasticities | EIA / Stanford EMF | 2017 | https://www.eia.gov/workingpapers/pdf/key_international_demand_elasticities.pdf | Public domain (US govt) | sources/archive/eia_international_demand_elasticities.pdf | Long-run income elasticity of electricity demand ≈ 0.59 (res. 0.53, ind. 0.76) |
| burke_csereklyei_2016 | Understanding the energy-GDP elasticity: a sectoral approach | Burke & Csereklyei, ANU CAMA | 2016 | https://crawford.anu.edu.au/sites/default/files/2025-03/45_2016_burke_csereklyei_word.pdf | Author preprint | sources/archive/burke_csereklyei_2016.pdf | Electricity-GDP elasticity ≈ 0.88–0.95; elasticity = Σ sector share × sector elasticity |
| irena_jobs_2024 | Renewable energy and jobs: Annual review 2024 | IRENA / ILO | 2024 | https://www.irena.org/Publications/2024/Oct/Renewable-energy-and-jobs-Annual-review-2024 | IRENA terms (free) | | 16.2M renewables jobs 2023; employment factors per MW by technology |
| ieee_1366_tutorial | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck | IEEE Boston PES | 2019 | https://site.ieee.org/boston-pes/files/2019/03/IEEE-1366-Reliability-Indices-2-2019.pdf | IEEE (c) | sources/archive/ieee_1366_reliability_tutorial.pdf | SAIFI = ΣCI/NT, SAIDI = ΣCMI/NT sustained-interruption definitions |
| hou_2008_china | Electricity Consumption and Economic Growth in China: Multivariable Cointegration Analysis | Hou & Tan, North China Electric Power University | 2008 | https://doi.org/10.1109/wicom.2008.1932 | Proprietary (IEEE paywall) | | China long-run income elasticity 0.85, price elasticity -0.13 |
| shan_baoguo_2017 | 经济转型时期电力弹性系数应用 (Electricity elasticity coefficient in the transition period) | 单葆国 et al., 中国电力 | 2017 | https://www.electricpower.com.cn/CN/volumn/volumn_1202.shtml | Proprietary (CNKI) | | China's electricity elasticity 0.38-1.88 over 1980-2017, forecast-coherence use |
| tejada_2023 | Multi-year Investment Modelling in Energy Systems | Tejada-Arango, JRC | 2023 | https://arxiv.org/abs/2307.16842 | arXiv (open) | sources/archive/tejada_multiyear_investment_2023.html | Annualised vs overnight capital cost in GEP; the annuity/WACC derivations Eqs 2-3 |
| gep_review_2017 | Generation expansion planning optimisation with renewable energy integration: a review | Oree, Sayed Hassen & Fleming | 2017 | https://eprints.whiterose.ac.uk/id/eprint/111487/1/Generation%20expansion%20planning%20optimisation%20with%20renewable%20energy%20integration%20a%20review-1.pdf | Author accepted MS | sources/archive/whiterose_gep_review_2017.pdf | Least-cost GEP, capacity credit/ELCC for variable renewables |

## Digests of the archived copies

A re-download of the same URL is not necessarily the same bytes — a publisher
reissues a report under the same filename — so a register that records only a
path cannot tell a replaced copy from the original. The digest is what makes
the row evidence rather than a pointer.

| file | sha256 |
|---|---|
| sources/archive/irena_costs_2022_summary.pdf | b04c0d5234e2d2bfeb38960e76b6409741f3e478cd7a71a772d924b8e70ced0e |

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
