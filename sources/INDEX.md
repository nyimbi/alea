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
| iea_nea_egc | Projected Costs of Generating Electricity, 2020 Edition | IEA / NEA | 2020 | https://iea.blob.core.windows.net/assets/ae17da3d-e8a5-4163-a3ec-2e6fb0b5677d/Projected-Costs-of-Generating-Electricity-2020.pdf | Proprietary (free download; IEA withholds reproduction rights) | sources/archive/iea_nea_egc_2020.pdf | IEA/NEA Projected Costs of Generating Electricity; IEA/NEA, Projected Costs of Generating Electricity |
| entsoe_adequacy | Mid-term Adequacy Forecast 2019: Appendix 2 -- Methodology | ENTSO-E | 2019 | https://eepublicdownloads.blob.core.windows.net/public-cdn-container/clean-documents/sdc-documents/MAF/2019/MAF%202019%20Appendix%202%20-%20Methodology.pdf | ENTSO-E terms (free to distribute with attribution) | sources/archive/entsoe_maf_2019_methodology.pdf | ENTSO-E adequacy studies; N-1 planning criterion; ENTSO-E adequacy methodology |
| who_airq | AirQ+: burden of disease due to air pollution manual | WHO Regional Office for Europe | 2020 | https://iris.who.int/handle/10665/337684 | CC BY-NC-SA 3.0 IGO | sources/archive/who_airq_manual.pdf | WHO AirQ+ methodology; WHO AirQ+ manual |
| who_hrapie_2013 | Health risks of air pollution in Europe -- HRAPIE project: recommendations for concentration-response functions for cost-benefit analysis of particulate matter, ozone and nitrogen dioxide | WHO Regional Office for Europe | 2013 | https://iris.who.int/handle/10665/153692 | Proprietary (free download; WHO withholds reproduction rights) | sources/archive/who_hrapie_2013.pdf | WHO Regional Office for Europe, Health risks of air pollution in Europe -- HRAPIE project |
| emep_eea_2023_1a1a | EMEP/EEA air pollutant emission inventory guidebook 2023, chapter 1.A.1.a (combustion in energy industries) | European Environment Agency | 2023 | https://www.eea.europa.eu/publications/emep-eea-guidebook-2023/part-b-sectoral-guidance-chapters/1-energy/1-a-combustion/1-a-1-a-public-electricity-and-heat-production | EEA terms (free to distribute with attribution) | sources/archive/emep_eea_guidebook_2023_1a1a.pdf | EMEP/EEA Guidebook 2023, NFR 1.A.1.a |
| who_aqg_2021 | WHO global air quality guidelines: particulate matter (PM2.5 and PM10), ozone, nitrogen dioxide, sulfur dioxide and carbon monoxide | WHO Regional Office for Europe | 2021 | https://iris.who.int/handle/10665/345329 | CC BY-NC-SA 3.0 IGO | sources/archive/who_aqg_2021.pdf | WHO global air quality guidelines (2021) |
| hanna_briggs_hosker_1982 | Handbook on atmospheric diffusion | US Department of Energy (DOE/TIC-11223) | 1982 | https://www.osti.gov/biblio/5591108 | Public domain (US government work) | sources/archive/hanna_briggs_hosker_1982.pdf | Hanna, Briggs & Hosker (1982), Handbook on Atmospheric Diffusion |
| ipcc_2006_gl_vol2 | 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 2 (Energy), Chapters 1-2 | Intergovernmental Panel on Climate Change | 2006 | https://www.ipcc-nggip.iges.or.jp/public/2006gl/vol2.html | IPCC terms (free to distribute with attribution) | sources/archive/ipcc_2006_gl_vol2_ch2.pdf | IPCC Guidelines for National Greenhouse Gas Inventories; IPCC 2006 Guidelines, Volume 2 |
| ipcc_ar5_wg3_annex3 | Climate Change 2014: Mitigation of Climate Change, Annex III: Technology-specific cost and performance parameters, Table A.III.2 (Emissions of selected electricity supply technologies, gCO2eq/kWh) | Intergovernmental Panel on Climate Change | 2014 | https://www.ipcc.ch/report/ar5/wg3/ | IPCC terms (free to distribute with attribution) | sources/archive/ipcc_ar5_wg3_annex3.pdf | IPCC (2014) Climate Change 2014: Mitigation of Climate Change, Annex III; IPCC AR5 WG3 Annex III Table A.III.2 |
| ipcc_srren_2011 | IPCC Special Report on Renewable Energy Sources and Climate Change Mitigation, Annex II, Table A.II.4 (aggregated LCA results, gCO2eq/kWh) | Intergovernmental Panel on Climate Change | 2011 | https://www.ipcc.ch/report/renewable-energy-sources-and-climate-change-mitigation/ | IPCC terms (free to distribute with attribution) | sources/archive/ipcc_srren_2011_excerpt.pdf | IPCC-SRREN (2011) Table A.II.4; IPCC Special Report on Renewable Energy Sources, Annex II |
| placeholder_survey | The placeholder survey (docs/research/placeholder-survey.md): classification of the 181 rows that shipped the 500,000 sentinel, by what the catalog's description and algorithm cells say each one is | | 2026 | | Repository document | n/a | The placeholder survey (docs/research/placeholder-survey.md) |
| planning_reserve_margin_identity | The planning reserve margin identity: required capacity = forecast peak demand x (1 + margin), the standard conversion between a reserve-margin fraction and a capacity requirement | | | | | n/a | The planning reserve margin is one requirement with one value |
| wrights_law | Wright's law: factors affecting the cost of airplanes | Journal of the Aeronautical Sciences | 1936 | https://doi.org/10.2514/8.155 | Proprietary (publisher paywall) | | Wright's law |
| crf_annuity | Capital recovery factor (standard annuity formula) | | | | | n/a | Standard annuity formula |
| wacc_identity | Weighted average cost of capital with the interest tax shield | | | | | n/a | Standard WACC with the interest tax shield |
| average_cost_pricing | Average-cost pricing: fixed cost over units sold, plus short-run marginal cost | | | | | n/a | Average-cost pricing |
| swing_equation | Swing equation at t=0 (df/dt = -P_loss / (2 H S)) | | | | | n/a | Swing equation |
| n1_criterion | N-1 planning criterion | | | | | n/a | Standard N-1 planning criterion |
| nrel_atb_2025 | Annual Technology Baseline 2025, Equations & Variables | NREL | 2025 | https://atb.nlr.gov/electricity/2025/equations_&_variables | Public domain (US govt) | sources/archive/nrel_atb_2025_equations.html | NREL ATB 2025 Equations & Variables; NREL ATB battery equations |
| eia_lcoe_methodology | Levelized Cost of Electricity Methodology (AEO supplement) | EIA | 2024 | https://www.eia.gov/outlooks/aeo/electricity_generation/pdf/LCOE_methodology.pdf | Public domain (US govt) | sources/archive/eia_lcoe_methodology.pdf | EIA AEO LCOE methodology; EIA AEO Levelized Cost of Electricity Methodology |
| short_1995 | A Manual for the Economic Evaluation of Energy Efficiency and Renewable Energy Technologies, NREL/TP-462-5173 | Short, Packey & Holt | 1995 | https://www.nrel.gov/docs/legosti/old/5173.pdf | Public domain (US govt) | sources/archive/short_packey_holt_1995.pdf | Short, Packey & Holt (1995), NREL/TP-462-5173 |
| ukrn_cost_of_capital | Guidance for regulators on the methodology for setting the cost of capital | UK Regulators Network | 2023 | https://ukrn.org.uk/app/uploads/2023/03/CoC-guidance_22.03.23.pdf | UKRN terms (free) | sources/archive/ukrn_cost_of_capital_2023.pdf | UKRN cost of capital guidance (2023), §allowed returns; UKRN cost of capital guidance (2023), §overall framework; Ofwat PR24 Appendix 11, allowed return on capital |
| eia_demand_elasticities | Review of Key International Demand Elasticities | EIA / Stanford EMF | 2017 | https://www.eia.gov/workingpapers/pdf/key_international_demand_elasticities.pdf | Public domain (US govt) | sources/archive/eia_international_demand_elasticities.pdf | EIA/Stanford EMF demand elasticities |
| burke_csereklyei_2016 | Understanding the energy-GDP elasticity: a sectoral approach | Burke & Csereklyei, ANU CAMA | 2016 | https://crawford.anu.edu.au/sites/default/files/2025-03/45_2016_burke_csereklyei_word.pdf | Author preprint | sources/archive/burke_csereklyei_2016.pdf | Burke & Csereklyei 2016 |
| world_bank_regulation | Handbook for Evaluating Infrastructure Regulatory Systems | Brown, Stern & Tenenbaum, World Bank | 2006 | https://openknowledge.worldbank.org/handle/10986/7030 | World Bank copyright (free download; permission normally granted) | sources/archive/world_bank_regulating_utilities_handbook.pdf | World Bank Regulation of Utilities handbook, revenue caps; Pass-through pricing; World Bank, Regulation of Utilities handbook |
| fuel_tables | Standard fuel properties: LHV of ammonia 18.6 GJ/t, hydrogen 33.33 kWh/kg, 5.8 MMBtu/barrel crude, 0.29307 MWh/MMBtu HHV | | | | | n/a | LHV of NH3: 18.6 GJ/t (standard fuel tables); LHV of H2: 33.33 kWh/kg (standard fuel tables); EIA conversion basis (5.8 MMBtu/barrel); Physical constant: 1 MMBtu = 0.29307 MWh (HHV); EIA conversion basis (5.8 MMBtu/barrel); physical constant 0.29307 MWh/MMBtu |
| catalog_method_cells | The catalog's own method cells as coupling provenance (bottom-up synthesis, rate-of-return) | | | | | n/a | Bottom-up load synthesis (catalog method cell) |
| fleet_generation_identity | Additive over the generation identity, and the headroom ratio against the energy balance — arithmetic on quantities the tree already declares | | | | | n/a | Additive over the generation identity; Ratio of the generation identity to the energy balance |
| energy_level_adequacy | Energy-level adequacy: the generation identity against the energy balance, the energy analogue of ENTSO-E's capacity-level practice | | | | | n/a | Energy-level adequacy: the generation identity against the energy balance |
| fragments_alias_register | The generated fragments' alias register, applied as equality equations | | | | | n/a | The fragments' alias register (docs/param_batch7.md and successors), applied |
| leontief_multipliers | Input-output employment multipliers (the demand-pull chain) | | | | | n/a | Leontief input-output employment multipliers |
| lazar_lcos | Lazard's Levelized Cost of Storage Analysis -- Version 7.0 | Lazard | 2021 | https://www.lazard.com/research-insights/levelized-cost-of-energy-levelized-cost-of-storage-and-levelized-cost-of-hydrogen-2021/ | Proprietary (free download from Lazard) | sources/archive/lazard_lcos_v7.pdf | Lazard LCOS |
| standard_fiscal | Rate-based levy and allowance definitions | | | | | n/a | Rate-based levy and allowance definitions (standard fiscal accounting) |
| composition_shares | Composition-target shares in employment planning | | | | | n/a | Composition-target shares (planning policy) |
| marginal_cost_split | The shipped marginal-cost definition, restated as its variable part | | | | | n/a | The shipped marginal-cost definition, split |
| catalog_duplicate_resolutions | The catalog's own duplicate rows, resolved by equality (the coupling batches' alias equations) | | | | | n/a | The catalog's own duplicate rows, resolved |
| bis_credit_spread | Credit-spread decomposition: borrower rate = policy rate + borrower premium | | | | | n/a | Credit-spread decomposition (BIS) |
| fisher_equation | The Fisher equation: nominal = (1 + real)(1 + inflation) | | | | | n/a | The Fisher equation |
| vat_tariffs | VAT applied to electricity tariffs | | | | | n/a | VAT applied to electricity tariffs |
| stoft_2002 | Power System Economics: Designing Markets for Electricity | Steven Stoft | 2002 | | Proprietary (textbook) | | Stoft 2002, Power System Economics, ch. 5 |
| cbam_regulation | Regulation (EU) 2023/956 establishing a carbon border adjustment mechanism; EU ETS allowance levels | European Parliament and Council | 2023 | https://eur-lex.europa.eu/eli/reg/2023/956/oj | EU terms (reusable with attribution, Decision 2011/833/EU) | sources/archive/cbam_regulation_2023_956.pdf | EU CBAM regulation; EU ETS allowance level 2026 |
| benefit_sharing_shares | Benefit-sharing programme shares, applied through the graph's own revenue identity | | | | | n/a | Benefit-sharing programmes (the graph's own revenue identity) |
| guarantee_risk_pricing | Guaranteed-offtake risk pricing in PPA markets | | | | | n/a | Guaranteed-offtake risk pricing (PPA market practice) |
| fiscal_definitions | Rate-based levy, allowance and composition-share definitions | | | | | n/a | Rate-based levy and allowance definitions (standard fiscal accounting); Composition-target shares (planning policy) |
| pass_through_pricing | Pass-through pricing rules in utility tariff design | | | | | n/a | Pass-through pricing |
| irena_jobs_2024 | Renewable energy and jobs: Annual review 2024 | IRENA / ILO | 2024 | https://www.irena.org/Publications/2024/Oct/Renewable-energy-and-jobs-Annual-review-2024 | IRENA terms (free) | sources/archive/irena_jobs_2024.pdf | Leontief input-output employment multipliers; IRENA employment factors |
| ieee_1366_tutorial | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck; IEEE Std 1366 (distribution reliability) | IEEE Boston PES | 2019 | https://site.ieee.org/boston-pes/files/2019/03/IEEE-1366-Reliability-Indices-2-2019.pdf | IEEE (c) | sources/archive/ieee_1366_reliability_tutorial.pdf | IEEE Guide for Electric Power Distribution Reliability Indices (1366), tutorial deck; IEEE Std 1366 (distribution reliability) |
| eu_ets_2023_959 | Directive (EU) 2023/959 amending Directive 2003/87/EC -- Art. 21 auction platform and price formation | European Parliament and Council | 2023 | https://eur-lex.europa.eu/eli/dir/2023/959/oj | EU terms (reusable with attribution, Decision 2011/833/EU) | | EU ETS Directive 2023/959, Art. 21 (auction platform and price formation) |
| verra_gold_standard | Verified Carbon Standard and Gold Standard avoided-emissions accounting (project methodologies and the buffer-pool permanence rules) | Verra / Gold Standard Foundation | | https://verra.org/methodologies/ | Verra and Gold Standard terms (methodologies free to read) | | Verra/Gold Standard avoided-emissions accounting |
| verra_afolu_npt | AFOLU Non-Permanence Risk Tool v4.2 (risk rating to buffer-pool contribution) | Verra | 2023 | https://verra.org/wp-content/uploads/2023/10/AFOLU-Non-Permanence-Risk-Tool-v4.2-FINAL.pdf | Verra terms (methodologies free to read) | sources/archive/verra_afolu_npt_v42.pdf | Verra AFOLU Non-Permanence Risk Tool v4.2, 2.5.4 (risk rating converted to a percentage and multiplied by the net change in carbon stocks); 2.5.2 (minimum rating 12) |
| cambridge_buffer_pool_2024 | Cambridge Permanence and Durability Workshop: Resources and Summary (cross-program buffer-pool contributions: ACR 10% flat for CCS, Gold Standard and Plan Vivo 20%, Isometric 2%) | Cambridge Centre for Carbon Credits / Cambridge University Press | 2024 | https://doi.org/10.33774/coe-2024-lq0q7 | CC BY (workshop report; not peer reviewed) | sources/archive/cambridge_buffer_pool_workshop_2024.pdf | Cambridge Permanence and Durability Workshop 2024 |
| mtf_energy_access | Beyond Connections: Energy Access Redefined — ESMAP Technical Report 008/15 (the Multi-Tier Framework's tier definitions) | ESMAP, World Bank | 2015 | https://openknowledge.worldbank.org/handle/10986/24368 | World Bank copyright (free download) | sources/archive/mtf_energy_access.pdf | Multi-Tier Framework (MTF) energy access measurement |
| oecd_action4_2015 | Limiting Base Erosion Involving Interest Deductions and Other Financial Payments, Action 4 (2015 Final Report) | OECD / G20 | 2015 | https://www.oecd.org/tax/beps/limiting-base-erosion-involving-interest-deductions-and-other-financial-payments-action-4-2015.pdf | OECD terms (free to read) | | OECD, Limiting Base Erosion Involving Interest Deductions and Other Financial Payments, Action 4 (2015) |
| inventory_carrying_cost | Standard inventory carrying-cost accounting: holding cost as a rate on average inventory value | | | | | n/a | Standard inventory carrying-cost accounting |
| hou_2008_china | Electricity Consumption and Economic Growth in China: Multivariable Cointegration Analysis | Hou & Tan, North China Electric Power University | 2008 | https://doi.org/10.1109/wicom.2008.1932 | Proprietary (IEEE paywall) | | Hou & Tan 2008; Electricity Consumption and Economic Growth in China |
| shan_baoguo_2017 | 经济转型时期电力弹性系数应用 (Electricity elasticity coefficient in the transition period) | 单葆国 et al., 中国电力 | 2017 | https://www.electricpower.com.cn/CN/volumn/volumn_1202.shtml | Proprietary (CNKI) | | 单葆国 2017 |
| tejada_2023 | Multi-year Investment Modelling in Energy Systems | Tejada-Arango, JRC | 2023 | https://arxiv.org/abs/2307.16842 | arXiv (open) | sources/archive/tejada_multiyear_investment_2023.html | Tejada-Arango (2023), arXiv:2307.16842 |
| gep_review_2017 | Generation expansion planning optimisation with renewable energy integration: a review | Oree, Sayed Hassen & Fleming | 2017 | https://eprints.whiterose.ac.uk/id/eprint/111487/1/Generation%20expansion%20planning%20optimisation%20with%20renewable%20energy%20integration%20a%20review-1.pdf | Author accepted MS | sources/archive/whiterose_gep_review_2017.pdf | Oree et al. (2017), RSER 69:790-803 |
| damodaran_ctryprem_2026 | Country Default Spreads and Risk Premiums (table last updated 2026-01-05) | Aswath Damodaran, NYU Stern | 2026 | https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html | Author terms (free) | sources/archive/damodaran_ctryprem_2026-01.html | Damodaran (2026), Country Default Spreads and Risk Premiums |

| shams_2017_frequency_low_inertia | Analysis and Response Management of Frequency Events in Low Inertia Power Systems (PhD thesis) | Negar Shams, University of Manchester | 2017 | https://pure.manchester.ac.uk/ws/files/87763588/FULL_TEXT.PDF | Author thesis, institutional repository (open access) | sources/archive/shams_2017_frequency_low_inertia.pdf | Shams 2017, time to nadir in low-inertia systems; fast frequency response defined as response within 0.5 s of triggering |
| sharif_2019_wds_energy | Water Energy Nexus for Water Distribution Systems: A Literature Review | Sharif, Haider, Farahat & Hewage, *Environmental Reviews* | 2019 | https://utoronto.scholaris.ca/bitstreams/ee38eb33-caeb-42de-9ba5-6756c312538e/download | Author accepted manuscript, institutional repository (open access) | sources/archive/sharif_2019_water_distribution_energy.pdf | Sharif et al. (2019), energy intensity of water distribution systems |

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
| sources/archive/iea_nea_egc_2020.pdf | 7471000f732fb256bb9c2ebfbaa74285ea4736e980983b10201e0fdbf71d0b7a |
| sources/archive/entsoe_maf_2019_methodology.pdf | cadddb273133a7a419f17144354705aa5a550be0bb44f65e28878df115cb964b |
| sources/archive/who_airq_manual.pdf | f77f77b5d39cf74da362b0c9bb56d5a70770acf0415830a68f7d7e9e77ee7d59 |
| sources/archive/who_hrapie_2013.pdf | 8b2e337aba8b984b6c175d2f7668cc757be7a4e5c9969a3df8e226970f3abd8f |
| sources/archive/who_aqg_2021.pdf | 32f3bf1470e20803decb63ab1ee5babf289b4182bc8af94d62b7a5b998642353 |
| sources/archive/hanna_briggs_hosker_1982.pdf | c44eb11b802a5c8f50482a5c0797081a2aee8fd35fb27bf62a9c1579ac050801 |
| sources/archive/ipcc_2006_gl_vol2_ch2.pdf | a25d9f96d7672df391b328de79d4cfd812c07fe79d5cf4a30d23d82d8f02985b |
| sources/archive/emep_eea_guidebook_2023_1a1a.pdf | cae33cf0bb79858c6fed58f38fa139149d27b0116fd1355812b65a11333b6ce5 |
| sources/archive/world_bank_regulating_utilities_handbook.pdf | 4f65e2264a5d6b815f5e0603b56b53bd8a66c8c7573c77cd4199e8a361d25926 |
| sources/archive/lazard_lcos_v7.pdf | 61b0adf3ab51a30131b1b0a0dfecb0bb76df9a5e55cae8d5e416a7f0d772fd58 |
| sources/archive/cbam_regulation_2023_956.pdf | 5cd8fa27cb441333e20a93ec9f1d86bac29d5740f76c8d82a55aa292d721d8ca |
| sources/archive/mtf_energy_access.pdf | 9d23881ad861edf38f409cb3ed4a600c6b295b3ffb78261c6ed42ee278d1c26b |
| sources/archive/ipcc_ar5_wg3_annex3.pdf | dec39383e03caf843f833ad8f4b373f72be3b86ada6d826bd172e8955ffe24c2 |
| sources/archive/ipcc_srren_2011_excerpt.pdf | bd3803f18574eba68eb32980df1a63fe7de2cb7307725134980bf6fece500dfe |
| sources/archive/shams_2017_frequency_low_inertia.pdf | 1abfcb4bbf785f39a0290013ca46a08d72dfb9b0ee934d4999378beb2a49693a |
| sources/archive/verra_afolu_npt_v42.pdf | 8cc1e20543b0f37a59ce195fb890c2852d6818d057a2aafb6e4307d1abab29d8 |
| sources/archive/cambridge_buffer_pool_workshop_2024.pdf | 237809102fe2ea6fee1b22d229118d9f69683a61bccd9b2f9e912995259e6d8c |
| sources/archive/sharif_2019_water_distribution_energy.pdf | d0bf1f4c362cc0c89696a5bb42ee8c375b7794819cd67986741c81bced0f08ba |

## Why some rows are `n/a`

Twenty-three of the register's rows carry `n/a` in the archived column, and it is
worth being explicit, because a reader who sees them with no custodian will assume
the register is incomplete rather than that the citations are a different kind of
claim.

Five are textbook derivations: `crf_definition` cites "the standard annuity
formula", `wacc_definition` cites "the standard WACC with the interest tax
shield", `rocof_definition` cites "the swing equation at t=0",
`tariff_cost_recovery` cites "average-cost pricing", and `reserve_margin` cites
"the standard N-1 planning criterion". Each names a *derivation*, not a work.
They are in every power-systems textbook and no one of them is the source: the
equation is correct because the algebra is, and the citation is telling the reader
which textbook result is being used rather than attributing a number to a
measurement. An entry with a plausible-looking paper attached would be the more
comfortable row and the less honest one.

The rest are the same kind of claim one level down: an identity the tree states
about its *own* quantities (`fleet_generation_identity`,
`catalog_duplicate_resolutions`, `marginal_cost_split`, `standard_fiscal`,
`fisher_equation`, `bis_credit_spread`, `vat_tariffs`, `pass_through_pricing`,
`inventory_carrying_cost`, `fuel_tables`, `leontief_multipliers`,
`composition_shares`, `benefit_sharing_shares`, `guarantee_risk_pricing`,
`fiscal_definitions`, `catalog_method_cells`, `fragments_alias_register`) or an
adequacy criterion applied at the energy level rather than the capacity level
(`energy_level_adequacy`). There is no work to archive for "the generation
identity is additive"; archiving a paper would imply the identity needed one.

The rows that *do* name a custodian are the ones where a specific institution's
figure or method is being adopted — IRENA's cost statistics for the learning
curve, WHO's concentration-response function for premature deaths, ENTSO-E's
adequacy practice for the reserve margin, and IEA/NEA's LCOE definition.

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

## Unarchived works

Four rows carry an empty `archived` cell. Each was checked for an open copy on
2026-10-20 and none exists; the row is left empty rather than pointing at a file
this repository does not hold.

| key | checked | why no copy |
|---|---|---|
| wrights_law | 2026-10-20 | AIAA paywall. The DOI resolves only to `arc.aiaa.org/doi/pdf/10.2514/8.155`, which returns 403; Crossref lists that same URL as the sole full-text link, and OpenAlex reports `oa_status: closed` with no repository copy. The 1936 *Journal of the Aeronautical Sciences* volume is not in any open repository checked (OpenAlex, CORE, NTRS, HathiTrust). |
| stoft_2002 | 2026-10-20 | Print-only textbook, Wiley/IEEE Press, in copyright. No publisher open copy. A third-party scan circulates at `jackkarisch.com`, but it is an unauthorised reproduction with no custodian behind it, so it is not archived here: a copy of unknown provenance is not evidence that the cited work says what the equation claims. |
| hou_2008_china | 2026-10-20 | IEEE conference paper behind the IEEE Xplore paywall (DOI 10.1109/wicom.2008.1932). Crossref's only full-text link is `xplorestaging.ieee.org`, which returns 418; OpenAlex reports `oa_status: closed` and no repository copy. |
| shan_baoguo_2017 | 2026-10-20 | CNKI / Wanfang subscription only. `electricpower.com.cn` (中国电力, the publishing journal) serves the volume index as an empty 200 and every article path tried returns a 404 shell; the article is not on an open repository. |

A replacement citation would close `hou_2008_china` and `shan_baoguo_2017` in
principle, since both support the same 0.85 China electricity-GDP elasticity in
`demand_growth_implied_definition`, but the two published works already archived
for that equation (Burke & Csereklyei 2016, EIA/Stanford EMF 2017) carry the
same identity for other countries and neither states the China figure. Recording
that as a substitution is a change to `config/prg.yaml`, which this register does
not own.

