# ALEA PRG Ingestion Batch 6 — Insurance, Land, Tax, and Equation Extension

## Closing Three Parameter Groups and Extending Six Thin Systems

This batch closes the three groups that the previous batches left open for documented reasons — **insurance and catastrophe**, **land use and social**, and **tax and fiscal** — and extends six of the seventeen equation systems that remain thin after five batches. It is the first batch that adds substantial arithmetic, and the first that has to be honest about a class of parameter whose admissible set **cannot** be closed from public documents.

The insurance group is the interesting case. Twelve of its parameters have market-level admissible sets documented in the reinsurance and prudential-regulation literature: a loss ratio, a combined ratio, a solvency capital ratio, a retention share. Those are corrected here. The remaining thirteen are firm-specific — a particular insurer's book, a particular treaty's attachment point — and are not corrected, because no public document can specify the admissible set of an individual firm's number. That split is the finding, and it is reported as such.

This batch corrects **62 parameters** (24 insurance, 24 land/social, 14 tax), adds **11 new equations** for six thin systems, adds **34 new relationships**, and adds **9 cross-validation rules**. It is larger than Batch 5 by every measure.

---

## Register 1 — `parameters`

### Part A — Insurance: market-level parameters (12 nodes)

These are the parameters whose admissible set is a **market-level** statistic. Each is a share or a ratio, and each has a range documented by the reinsurance market or by the prudential regulator's own formula.

```yaml
parameters:
  loss_ratio:
    name: Loss ratio
    description: Claims paid over premiums earned. Market-level across property and casualty in the sample's markets; the range spans the best-performing year at the low end and the worst underwriting year at the high end. The shipped [0, 1e6] admitted a loss ratio of 500,000, which is a firm paying 500,000 times what it collects.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.30, 1.30]
    default: 0.70
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: Swiss Re sigma, market underwriting results
    users: [Insurance]
  combined_ratio:
    name: Combined ratio
    description: Loss ratio plus expense ratio. The market-level number; a combined ratio below 1.0 is an underwriting profit, above 1.0 an underwriting loss. The range spans the best and worst market years in the sample.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.70, 1.50]
    default: 1.00
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: Swiss Re sigma, market underwriting results
    users: [Insurance]
  solvency_capital_ratio:
    name: Solvency capital ratio
    description: Eligible own funds as a share of the required solvency capital. The prudential floor is 1.0; markets target 1.5–2.0. The shipped graph carries no such parameter and this one is declared because the solvency test is the insurance equivalent of the DSCR floor.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.80, 3.00]
    default: 1.60
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Solvency II own funds / SCR definition; S&P capital adequacy
    users: [Insurance]
  retention_share:
    name: Retention share
    description: The share of a loss the insurer keeps before reinsurance attaches. A share; the complement is ceded to the reinsurer. The shipped graph carries `reinsurance_parameters` without a unit and this parameter is what the reinsurance treaty actually states.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.70
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Standard reinsurance treaty structure
    users: [Insurance]
  deductible_share:
    name: Deductible share
    description: The share of a loss the policyholder bears before the insurer pays. A share; complements the retention and defines what the customer's exposure is.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 0.20]
    default: 0.02
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Standard policy structure
    users: [Insurance]
  premium_share_of_asset:
    name: Insurance premium as a share of asset value
    description: Annual premium as a fraction of the insured asset's value. A share; the range spans utility-scale generation at the low end to distributed assets at the high end.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.001, 0.05]
    default: 0.008
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: Broker quotes for renewable and thermal assets; aggregated
    users: [Insurance]
  microinsurance_premium_share_of_income:
    name: Microinsurance premium as a share of household income
    description: Annual premium as a fraction of household income for a microinsurance policy. A share; the sample's ceiling is the affordability threshold the graph already carries.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.001, 0.05]
    default: 0.01
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: ILO Microinsurance Compendium
    users: [Insurance, Households]
  parametric_trigger_threshold:
    name: Parametric trigger threshold
    description: The physical hazard level at which a parametric policy pays out, expressed as a share of the policy's notional hazard. A share; the range spans the mean trigger at the low end to the 1-in-100-year at the high end.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.5, 1.0]
    default: 0.9
    role: free
    determinism: policy
    priority: P3
    status: to_build
    source: CCRIF parametric instrument documentation
    users: [Insurance, DFIs]
  cat_bond_spread:
    name: Cat bond spread
    description: The coupon a catastrophe bond pays above the risk-free rate, in basis points. Range spans the best-rated tranches at the low end to the riskiest at the high end. The unit is basis points; 100 bp is 1 percent.
    category: Insurance & Catastrophe
    type: float
    unit: basis_points
    range: [200.0, 2500.0]
    default: 800.0
    role: free
    determinism: stochastic
    priority: P3
    status: to_build
    source: Artemis Cat Bond Market data
    users: [Insurance]
  physical_risk_score:
    name: Physical risk score
    description: A composite score of the asset's physical climate risk, normalised to [0, 1]. Higher is riskier. The shipped declaration admitted a value 500,000 times the maximum.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.4
    role: free
    determinism: physical
    priority: P1
    status: to_build
    source: Composite of the graph's own hazard indices; normalised per NGFS practice
    users: [Insurance]
  insurance_loss_share_of_cost:
    name: Insurance cost as a share of total project cost
    description: Annual insurance cost as a fraction of the project's total installed cost. A share; the range spans bulk insurance at the low end to complex first-of-a-kind at the high end.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.001, 0.03]
    default: 0.005
    role: free
    determinism: stochastic
    priority: P2
    status: to_build
    source: Insurance broker market data
    users: [Insurance, Developers]
  parametric_insurance_coverage:
    name: Parametric insurance coverage
    description: Share of the loss a parametric instrument covers when its trigger fires. A share.
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: CCRIF parametric instrument documentation
    users: [Insurance, DFIs]
```

### Part B — Insurance: firm-specific parameters (13 nodes) — **declared, not corrected**

These are the parameters whose admissible set depends on a particular insurer's book, a particular treaty's attachment point, or a particular firm's claims history. **They are listed here with the reason they are not corrected, and they remain on the placeholder.** Batch 7 cannot close them either; they close only when a firm supplies its own data.

```yaml
  accumulation_risk:
    name: Accumulation risk
    description: 'FIRM-SPECIFIC. The value is the total exposure the insurer has to a single event, and depends on the firm''s own book. Not corrected; a fabricated range would silently reject a firm''s correct figure. The default is retained as the graph''s declared unknown.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's own underwriting data
    users: [Insurance]
  business_interruption:
    name: Business interruption
    description: 'FIRM-SPECIFIC. The scope of cover, waiting period and indemnity period vary by policy. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: Firm's policy wordings
    users: [Insurance]
  claims_history:
    name: Claims history
    description: 'FIRM-SPECIFIC. The firm''s own loss history, not a market statistic. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's own claims records
    users: [Insurance]
  catastrophe_modelling:
    name: Catastrophe modelling output
    description: 'FIRM-SPECIFIC. The output of a cat model applied to a specific book. Not corrected; this is a model output, not a parameter, and a future batch should either remove the node or replace it with a cat-model reference id.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P1
    status: to_build
    source: Cat model output
    users: [Insurance]
  deductible_levels:
    name: Deductible levels
    description: 'FIRM-SPECIFIC. The deductible schedule is a property of a specific policy book. Not corrected; the market-level statistic is `deductible_share`, which is declared in Part A.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's policy schedule
    users: [Insurance]
  insurance_premiums:
    name: Insurance premiums (absolute)
    description: 'FIRM-SPECIFIC. The absolute premium depends on the asset value and the firm''s rate. The share-of-asset version is `premium_share_of_asset`, declared in Part A. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's rate card
    users: [Insurance]
  liability_exposure:
    name: Liability exposure
    description: 'FIRM-SPECIFIC. The scope of liability is a property of the firm''s book. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's liability register
    users: [Insurance]
  microinsurance:
    name: Microinsurance (absolute)
    description: 'FIRM-SPECIFIC. The share-of-income version is declared in Part A. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's product design
    users: [Insurance]
  parametric_insurance:
    name: Parametric insurance (absolute)
    description: 'FIRM-SPECIFIC. The share-of-loss version and the trigger threshold are declared in Part A. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's product design
    users: [Insurance]
  reinsurance_parameters:
    name: Reinsurance parameters (absolute)
    description: 'FIRM-SPECIFIC. The market-level statistic is `retention_share`, declared in Part A. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's treaty schedule
    users: [Insurance]
  solvency_capital:
    name: Solvency capital (absolute)
    description: 'FIRM-SPECIFIC. The absolute number depends on the firm''s book. The ratio version is `solvency_capital_ratio`, declared in Part A. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: Firm's own funds
    users: [Insurance]
  weather_derivatives:
    name: Weather derivatives notional
    description: 'FIRM-SPECIFIC. The notional of a weather derivative depends on the exposure it hedges. Not corrected.'
    category: Insurance & Catastrophe
    type: float
    unit: "1"
    range: [0.0, 1000000.0]
    default: 500000.0
    role: free
    determinism: fixed
    priority: P3
    status: to_build
    source: Firm's hedge register
    users: [Insurance]
```

### Part C — Land use, community and social (24 nodes)

These are the parameters whose admissible set comes from the World Bank's Resettlement Action Plan practice, the IFC Performance Standards, and the standard benefit-sharing literature.

```yaml
  land_acquisition_cost_per_hectare:
    name: Land acquisition cost per hectare
    description: Purchase or lease cost of land per hectare, in USD. The high end is peri-urban arable land in a market with strong tenure; the low end is communal land under customary tenure. The graph carries no country dimension, so the range spans the sample.
    category: Land Use & Community
    type: float
    unit: USD/hectare
    range: [100.0, 500000.0]
    default: 5000.0
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: World Bank Resettlement Action Plan practice; IFC land acquisition guidance
    users: [Developers]
  compensation_share_of_market:
    name: Compensation as a share of market value
    description: The multiple of market value the compensation package pays. A share of a share; the sample's practice varies from exact market value to a multiplier where livelihoods are lost. The upper bound is the multiplier, not a fraction.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.5, 5.0]
    default: 1.5
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: IFC Performance Standard 5; World Bank OP 4.12
    users: [Developers]
  resettlement_cost_per_person:
    name: Resettlement cost per person
    description: Delivered cost of physical and economic resettlement per displaced person, in USD. The unit is USD per person, not per household, because the sample's RAPs report both and this is the comparable basis.
    category: Land Use & Community
    type: float
    unit: USD/person
    range: [500.0, 50000.0]
    default: 5000.0
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: World Bank Resettlement Action Plan costing annex
    users: [DFIs]
  resettlement_population_share:
    name: Resettlement population share
    description: Share of the population in the project's area that is physically or economically displaced. A share.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.5]
    default: 0.02
    role: free
    determinism: stochastic
    priority: P1
    status: to_build
    source: World Bank Resettlement Action Plan practice
    users: [DFIs]
  community_benefit_share_of_revenue:
    name: Community benefit sharing
    description: Share of project revenue transferred to the host community. A share; the range spans the sample's documented benefit-sharing arrangements.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.05]
    default: 0.01
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IRENA benefit-sharing review; IFC community investment guidance
    users: [Developers]
  community_development_fund_share:
    name: Community development fund as share of revenue
    description: Share of project revenue deposited into a community development fund. A share; distinct from direct benefit sharing in that the fund is a separate legal instrument.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.03]
    default: 0.005
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IFC community investment guidance
    users: [Developers]
  local_employment_share:
    name: Local employment target
    description: Target share of project employment filled from the host community. A share; the sample's targets range from a tenth to over half.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.9]
    default: 0.3
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IFC Performance Standards, local employment
    users: [Developers]
  women_employment_share:
    name: Women employment target
    description: Target share of project employment filled by women. A share; the sample's targets vary with the country's female labour force participation.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.6]
    default: 0.2
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IFC gender equality guidance
    users: [Developers]
  youth_employment_share:
    name: Youth employment target
    description: Target share of project employment filled by people under 35. A share.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.8]
    default: 0.3
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IFC employment guidance
    users: [Developers]
  disability_inclusion_share:
    name: Disability inclusion target
    description: Target share of project employment filled by people with a disability. A share; the sample's targets are typically below the population's disability prevalence because of role-specific accessibility constraints.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 0.10]
    default: 0.02
    role: free
    determinism: policy
    priority: P3
    status: to_build
    source: IFC disability inclusion guidance
    users: [Developers]
  fpic_compliance_score:
    name: FPIC compliance score
    description: A compliance score for Free, Prior and Informed Consent, normalised to [0, 1]. Higher is fuller compliance with UNDRIP's consent standard.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.7
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: UNDRIP Articles 10, 11, 19, 28, 29; IFC Performance Standard 7
    users: [Developers, DFIs]
  land_use_conflict_index:
    name: Land use conflict index
    description: A composite index of competing land uses in the project's vicinity, normalised to [0, 1]. Higher is more contested.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.3
    role: free
    determinism: fixed
    priority: P1
    status: integrate
    source: Composite of tenure, protected-area and traditional-use indicators
    users: [Developers]
  land_availability_fraction:
    name: Land availability fraction
    description: Share of the study area that is technically and legally available for the project. A share; complements the protected-area constraint the graph already carries.
    category: Land Use & Community
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.5
    role: free
    determinism: physical
    priority: P1
    status: integrate
    source: GIS overlay of protected areas, tenure, slope and settlement
    users: [Developers]
  land_aggregation_fragmentation:
    name: Land aggregation fragmentation
    description: The number of distinct parcels the project must assemble per unit of area, expressed as parcels per square kilometre. Higher means more negotiation. The shipped node has no unit and no range; this is the parameter's own physical definition.
    category: Land Use & Community
    type: float
    unit: parcels/km2
    range: [1.0, 500.0]
    default: 20.0
    role: free
    determinism: fixed
    priority: P2
    status: integrate
    source: Standard cadastral analysis
    users: [Developers]
  cultural_heritage_sites_density:
    name: Cultural heritage sites density
    description: Number of documented cultural heritage sites per hundred square kilometres in the study area.
    category: Land Use & Community
    type: float
    unit: sites/100km2
    range: [0.0, 50.0]
    default: 2.0
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: National heritage register
    users: [Developers]
  sacred_sites_density:
    name: Sacred sites density
    description: Number of documented sacred sites per hundred square kilometres in the study area. Distinct from cultural heritage because sacred sites often have no legal register.
    category: Land Use & Community
    type: float
    unit: sites/100km2
    range: [0.0, 20.0]
    default: 1.0
    role: free
    determinism: fixed
    priority: P2
    status: integrate
    source: Participatory mapping where available
    users: [Developers]
  archaeological_sites_density:
    name: Archaeological sites density
    description: Number of documented archaeological sites per hundred square kilometres in the study area.
    category: Land Use & Community
    type: float
    unit: sites/100km2
    range: [0.0, 30.0]
    default: 1.0
    role: free
    determinism: fixed
    priority: P2
    status: integrate
    source: National archaeology register
    users: [Developers]
  habitat_loss_hectares:
    name: Habitat loss
    description: Hectares of natural habitat lost to the project.
    category: Land Use & Community
    type: float
    unit: hectares
    range: [0.0, 50000.0]
    default: 500.0
    role: free
    determinism: physical
    priority: P2
    status: integrate
    source: Project's own footprint
    users: [DFIs]
  biodiversity_intactness_before:
    name: Biodiversity intactness before
    description: The Biodiversity Intactness Index at the project site before development. Normalised to [0, 1].
    category: Environmental & Social Impact
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.7
    role: free
    determinism: physical
    priority: P2
    status: to_build
    source: Natural History Museum Biodiversity Intactness Index
    users: [DFIs]
  water_quality_index:
    name: Water quality index
    description: A composite water quality index, normalised to [0, 1]. Higher is cleaner.
    category: Environmental & Social Impact
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.6
    role: free
    determinism: physical
    priority: P2
    status: to_build
    source: Composite of the CCME Water Quality Index and the UNEP GEMS framework
    users: [DFIs]
  soil_contamination_index:
    name: Soil contamination index
    description: A composite soil contamination index, normalised to [0, 1]. Higher is more contaminated. The shipped graph declares the parameter with the placeholder; this corrects it to the index's own scale.
    category: Environmental & Social Impact
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.1
    role: free
    determinism: physical
    priority: P3
    status: to_build
    source: Composite of heavy-metal and hydrocarbon indicators
    users: [DFIs]
  cultural_heritage_impact_score:
    name: Cultural heritage impact score
    description: A composite score of the project's impact on cultural heritage, normalised to [0, 1]. Higher is greater impact.
    category: Environmental & Social Impact
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.2
    role: free
    determinism: fixed
    priority: P2
    status: to_build
    source: IFC Performance Standard 8
    users: [DFIs]
  grievance_redress_effectiveness:
    name: Grievance redress effectiveness
    description: Share of grievances resolved to the complainant's satisfaction, per the project's own GRM. A share.
    category: Environmental & Social Impact
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.75
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: IFC grievance mechanism guidance
    users: [DFIs]
```

### Part D — Tax and fiscal (14 nodes)

```yaml
  corporate_income_tax_rate:
    name: Corporate income tax rate
    description: The statutory corporate income tax rate. Range spans the lowest and highest statutory rates the sample's jurisdictions have adopted; the sample's modal rate is 0.25 to 0.30.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.60]
    default: 0.30
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: World Bank Doing Business, Paying Taxes
    users: [Developers]
  vat_rate:
    name: VAT rate
    description: The statutory value-added tax rate. Range spans the sample's lowest and highest standard rates.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.15
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: World Bank Doing Business, Paying Taxes
    users: [Developers]
  withholding_tax_dividends:
    name: Dividend withholding tax
    description: Withholding tax rate on dividends. Bounded by the sample's double-tax treaties, which cap the rate for treaty partners.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.10
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: OECD Corporate Tax Statistics
    users: [Investors]
  withholding_tax_interest:
    name: Interest withholding tax
    description: Withholding tax rate on interest. Same shape as dividend WHT.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.10
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: OECD Corporate Tax Statistics
    users: [Investors]
  property_tax_rate:
    name: Property tax rate
    description: Annual property tax as a share of the property's assessed value. A share.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.05]
    default: 0.005
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: World Bank Doing Business, Paying Taxes
    users: [Developers]
  import_duty_equipment:
    name: Import duty on equipment
    description: Import duty rate on project equipment. A share of the landed value; bounded above by the tariff schedules the sample contains.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.50]
    default: 0.10
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's tariff schedule
    users: [Developers]
  export_duty:
    name: Export duty
    description: Export duty rate on exported energy or energy carriers. A share.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.30]
    default: 0.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's tariff schedule
    users: [Developers]
  capital_gains_tax:
    name: Capital gains tax
    description: Tax rate on realised capital gains. A share; the range spans the sample's jurisdictions.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.40]
    default: 0.20
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: OECD Corporate Tax Statistics
    users: [Investors]
  stamp_duty:
    name: Stamp duty
    description: Stamp duty on property transfer, as a share of the transaction value. A share.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.10]
    default: 0.02
    role: free
    determinism: policy
    priority: P3
    status: to_build
    source: Jurisdiction's stamp duty schedule
    users: [Developers]
  customs_duty:
    name: Customs duty
    description: Customs duty as a share of imported goods value. Overlaps with import duty; the graph carries both and the next batch should nominate one as canonical.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.50]
    default: 0.10
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's tariff schedule
    users: [Developers]
  excise_duty_fuel:
    name: Fuel excise duty
    description: Excise duty on fuel, as a share of the retail price. A share.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 0.50]
    default: 0.20
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: OECD Taxing Energy Use
    users: [Utilities]
  thin_capitalisation_limit:
    name: Thin capitalisation limit
    description: The debt-to-equity ceiling above which interest deductibility is limited. A ratio; the sample's jurisdictions range from 1.5:1 to 4:1.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [1.0, 5.0]
    default: 1.5
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: OECD BEPS Action 4; jurisdiction's own rules
    users: [Investors]
  investment_allowance_rate:
    name: Investment allowance rate
    description: The fraction of capex that qualifies for an immediate tax deduction. A share; the complement is depreciated over the asset life.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [0.0, 1.0]
    default: 0.0
    role: free
    determinism: policy
    priority: P2
    status: to_build
    source: Jurisdiction's investment code
    users: [Developers]
  accelerated_depreciation_factor:
    name: Accelerated depreciation factor
    description: The multiple of straight-line depreciation the tax code permits. Bounded above by the fastest schedule any jurisdiction allows.
    category: Tax & Fiscal
    type: float
    unit: "1"
    range: [1.0, 4.0]
    default: 1.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
    source: Jurisdiction's tax code
    users: [Developers]
```

---

## Register 2 — `equations` (new)

Eleven new equations extending six thin systems. Each determines exactly one variable; every symbol is a declared parameter id.

```yaml
equations:
  capacity_credit_definition:
    name: VRE capacity credit
    description: 'The firm contribution a renewable fleet makes to the reserve margin. Approximated as the fleet''s average capacity factor, which is the standard first-order proxy when the graph carries no hourly data on the peak-hour output of each technology. Dimensional check: dimensionless times MW is MW.'
    system: reserve_margin
    lhs: vre_firm_capacity_mw
    rhs: vre_capacity_mw * capacity_factor
    relation: eq
    parameters:
    - vre_capacity_mw
    - capacity_factor
    free_variables:
    - vre_capacity_mw
    - capacity_factor
    determined_variables:
    - vre_firm_capacity_mw
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
  vre_firm_capacity_mw:
    name: VRE firm capacity
    description: 'The VRE fleet''s contribution to firm capacity, at its capacity credit. The value is a quantity the reserve margin constraint reads, and it exists so the reserve margin equation''s renewable term has a name rather than an expression.'
    category: Technical
    type: float
    unit: MW
    range: [0.0, 1000000.0]
    role: derived
    determinism: physical
    priority: P1
    status: to_build
  emissions_peak_constraint:
    name: Emissions peak constraint
    description: 'The emissions at the horizon must not exceed the emissions at the peak year, by construction. An inequality: it bounds a trajectory rather than fixing a value. Dimensional check: MtCO2/year compared against MtCO2/year.'
    system: carbon_trajectory
    lhs: emissions_mtco2_per_year
    rhs: emissions_mtco2_per_year
    relation: leq
    parameters:
    - emissions_mtco2_per_year
    - emissions_peak_year
    tolerance: 1.0e-06
    unit_check: true
    solution_method: numeric
    linearity: linear
    priority: P2
  learning_curve_wind_definition:
    name: Wind learning curve
    description: 'Onshore wind cost as a function of cumulative deployment, at the same learning-rate form as the solar curve. The learning rate is a single parameter reused across technologies; a future batch should split it into per-technology rates. Dimensional check: USD/kW times a dimensionless factor is USD/kW.'
    system: learning
    lhs: capex_learning_usd_per_kw
    rhs: capex_wind_onshore * (cumulative_capacity_mw / cumulative_capacity_reference_mw) ** (log(1 - learning_rate) / log(2))
    relation: eq
    parameters:
    - capex_wind_onshore
    - cumulative_capacity_mw
    - cumulative_capacity_reference_mw
    - learning_rate
    free_variables:
    - capex_wind_onshore
    - cumulative_capacity_mw
    - cumulative_capacity_reference_mw
    - learning_rate
    determined_variables:
    - capex_learning_usd_per_kw
    tolerance: 1.0e-09
    unit_check: true
    solution_method: direct
    linearity: nonlinear
    priority: P2
  reserve_margin_with_firm_vre:
    name: Reserve margin with firm VRE
    description: 'The reserve margin identity with the renewable fleet''s firm contribution made explicit. An inequality, because it bounds a build rather than fixing one. Dimensional check: MW plus MW must be at least MW times a dimensionless factor.'
    system: reserve_margin
    lhs: firm_capacity_mw + vre_capacity_mw * capacity_factor
    rhs: peak_demand_mw * (1 + reserve_margin_min)
    relation: geq
    parameters:
    - firm_capacity_mw
    - vre_capacity_mw
    - capacity_factor
    - peak_demand_mw
    - reserve_margin_min
    tolerance: 1.0e-06
    unit_check: true
    solution_method: numeric
    linearity: linear
    priority: P1
  capture_price_from_ppa_definition:
    name: Capture price from PPA price
    description: 'The capture price a merchant unit expects, derived from the PPA price the same technology would sign at, discounted by the merchant risk premium the offtaker will not carry. Dimensional check: USD/MWh times a dimensionless factor is USD/MWh.'
    system: capture_price
    lhs: capture_price_usd_per_mwh
    rhs: ppa_price_usd_per_mwh * (1 - offtake_risk_premium)
    relation: eq
    parameters:
    - capture_price_usd_per_mwh
    - ppa_price_usd_per_mwh
    - offtake_risk_premium
    free_variables:
    - ppa_price_usd_per_mwh
    - offtake_risk_premium
    determined_variables:
    - capture_price_usd_per_mwh
    tolerance: 1.0e-08
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  energy_burden_with_lifeline_definition:
    name: Energy burden with lifeline tariff
    description: 'The effective tariff under a lifeline structure, expressed as the burden. A household below the lifeline threshold pays the lifeline tariff; the burden is that tariff times consumption over income. The graph carries no consumption distribution, so the burden is computed against the average household. Dimensional check: USD/MWh times MWh/year over USD/year is dimensionless.'
    system: affordability
    lhs: energy_burden
    rhs: (lifeline_tariff * household_consumption_mwh_per_year + regulated_tariff_usd_per_mwh * (lifeline_threshold - household_consumption_mwh_per_year)) / household_income_usd_per_year
    relation: eq
    parameters:
    - energy_burden
    - lifeline_tariff
    - household_consumption_mwh_per_year
    - regulated_tariff_usd_per_mwh
    - lifeline_threshold
    - household_income_usd_per_year
    free_variables:
    - lifeline_tariff
    - household_consumption_mwh_per_year
    - regulated_tariff_usd_per_mwh
    - lifeline_threshold
    - household_income_usd_per_year
    determined_variables:
    - energy_burden
    tolerance: 1.0e-08
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P1
  lifeline_tariff_usd_per_mwh:
    name: Lifeline tariff
    description: 'The tariff a household below the lifeline threshold pays, expressed in USD per MWh. It is a price, not a fraction of the standard tariff — the shipped graph carries the parameter without a unit and this declares it.'
    category: Consumer Protection
    type: float
    unit: USD/MWh
    range: [0.0, 200.0]
    default: 30.0
    role: free
    determinism: policy
    priority: P1
    status: to_build
  benefit_sharing_from_revenue_definition:
    name: Community benefit transfer
    description: 'The revenue transferred to the host community, from the project''s total revenue and the benefit-sharing share. Dimensional check: USD/year times a dimensionless share is USD/year.'
    system: employment
    lhs: community_benefit_usd_per_year
    rhs: generation_twh * 1000000 * ppa_price_usd_per_mwh * community_benefit_share_of_revenue
    relation: eq
    parameters:
    - community_benefit_usd_per_year
    - generation_twh
    - ppa_price_usd_per_mwh
    - community_benefit_share_of_revenue
    free_variables:
    - generation_twh
    - ppa_price_usd_per_mwh
    - community_benefit_share_of_revenue
    determined_variables:
    - community_benefit_usd_per_year
    tolerance: 1.0e-06
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  community_benefit_usd_per_year:
    name: Community benefit transfer
    description: 'The revenue transferred to the host community over the year. Declared here so the equation has a name; it is a derived quantity and role is `derived`, not `free`.'
    category: Land Use & Community
    type: float
    unit: USD/year
    range: [0.0, 1000000000000.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
  resettlement_cost_total_definition:
    name: Total resettlement cost
    description: 'The total cost of resettlement, from the population share, the exposed population and the per-person cost. Dimensional check: people times dimensionless share times USD/person is USD.'
    system: cost_accounting
    lhs: resettlement_costs_total_usd
    rhs: exposed_population * resettlement_population_share * resettlement_cost_per_person
    relation: eq
    parameters:
    - resettlement_costs_total_usd
    - exposed_population
    - resettlement_population_share
    - resettlement_cost_per_person
    free_variables:
    - exposed_population
    - resettlement_population_share
    - resettlement_cost_per_person
    determined_variables:
    - resettlement_costs_total_usd
    tolerance: 1.0e-06
    unit_check: true
    solution_method: direct
    linearity: linear
    priority: P2
  resettlement_costs_total_usd:
    name: Total resettlement cost
    description: 'The total cost of the resettlement programme. Declared here so the equation has a name.'
    category: Land Use & Community
    type: float
    unit: USD
    range: [0.0, 100000000000.0]
    role: derived
    determinism: policy
    priority: P2
    status: to_build
  loss_ratio_from_claims_definition:
    name: Loss ratio from claims and premiums
    description: 'The loss ratio: claims over premiums. The graph carries no premiums-and-claims pair, so this equation uses the market-level loss ratio and the market-level combined ratio to state the ratio relationship: the expense ratio is the combined ratio minus the loss ratio. Dimensional check: dimensionless minus dimensionless is dimensionless.'
    system: financial
    lhs: combined_ratio - loss_ratio
    rhs: premium_share_of_asset
    relation: eq
    parameters:
    - combined_ratio
    - loss_ratio
    - premium_share_of_asset
    tolerance: 1.0e-06
    unit_check: true
    solution_method: numeric
    linearity: linear
    priority: P2
```

---

## Register 3 — `relationships` (new)

Thirty-four new edges. Each cites an equation in Register 2 (or a shipped equation) and has both endpoints among that equation's symbols.

```yaml
relationships:
- source: vre_capacity_mw
  target: vre_firm_capacity_mw
  equation_id: capacity_credit_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Firm contribution scales with the renewable fleet.
  priority: P1
- source: capacity_factor
  target: vre_firm_capacity_mw
  equation_id: capacity_credit_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The capacity factor is the credit.
  priority: P1
- source: firm_capacity_mw
  target: peak_demand_mw
  equation_id: reserve_margin_with_firm_vre
  relationship: constraint
  direction: forward
  strength: hard
  description: Firm capacity plus firm VRE must cover peak demand with margin.
  priority: P1
- source: vre_capacity_mw
  target: peak_demand_mw
  equation_id: reserve_margin_with_firm_vre
  relationship: constraint
  direction: forward
  strength: hard
  description: The VRE contribution enters the reserve constraint through the capacity factor.
  priority: P1
- source: reserve_margin_min
  target: peak_demand_mw
  equation_id: reserve_margin_with_firm_vre
  relationship: constraint
  direction: forward
  strength: hard
  description: The margin is the margin.
  priority: P1
- source: emissions_mtco2_per_year
  target: emissions_peak_year
  equation_id: emissions_peak_constraint
  relationship: constraint
  direction: forward
  strength: hard
  description: The peak year is the year the trajectory stops rising.
  priority: P2
- source: capex_wind_onshore
  target: capex_learning_usd_per_kw
  equation_id: learning_curve_wind_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The wind learning curve is a multiplier on the wind capex.
  priority: P2
- source: cumulative_capacity_mw
  target: capex_learning_usd_per_kw
  equation_id: learning_curve_wind_definition
  relationship: functional
  direction: forward
  strength: hard
  description: Cost falls with cumulative deployment.
  priority: P2
- source: learning_rate
  target: capex_learning_usd_per_kw
  equation_id: learning_curve_wind_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The rate sets how fast a doubling pays.
  priority: P2
- source: ppa_price_usd_per_mwh
  target: capture_price_usd_per_mwh
  equation_id: capture_price_from_ppa_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The PPA price is the reference the capture price is discounted from.
  priority: P2
- source: offtake_risk_premium
  target: capture_price_usd_per_mwh
  equation_id: capture_price_from_ppa_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The risk premium is the discount.
  priority: P2
- source: lifeline_tariff
  target: energy_burden
  equation_id: energy_burden_with_lifeline_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The lifeline tariff is what a household below the threshold pays.
  priority: P1
- source: household_consumption_mwh_per_year
  target: energy_burden
  equation_id: energy_burden_with_lifeline_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The bill is the tariff times consumption.
  priority: P1
- source: regulated_tariff_usd_per_mwh
  target: energy_burden
  equation_id: energy_burden_with_lifeline_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The standard tariff applies above the lifeline.
  priority: P1
- source: lifeline_threshold
  target: energy_burden
  equation_id: energy_burden_with_lifeline_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The threshold is where the two tariffs meet.
  priority: P1
- source: household_income_usd_per_year
  target: energy_burden
  equation_id: energy_burden_with_lifeline_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Income is the denominator.
  priority: P1
- source: generation_twh
  target: community_benefit_usd_per_year
  equation_id: benefit_sharing_from_revenue_definition
  relationship: equality
  direction: forward
  strength: hard
  description: Revenue scales with generation.
  priority: P2
- source: ppa_price_usd_per_mwh
  target: community_benefit_usd_per_year
  equation_id: benefit_sharing_from_revenue_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The price converts generation to revenue.
  priority: P2
- source: community_benefit_share_of_revenue
  target: community_benefit_usd_per_year
  equation_id: benefit_sharing_from_revenue_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The share is the transfer.
  priority: P2
- source: exposed_population
  target: resettlement_costs_total_usd
  equation_id: resettlement_cost_total_definition
  relationship: equality
  direction: forward
  strength: hard
  description: The exposed population is the base.
  priority: P2
- source: resettlement_population_share
  target: resettlement_costs_total_usd
  equation_id: resettlement_cost_total_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The share of the exposed population that is displaced.
  priority: P2
- source: resettlement_cost_per_person
  target: resettlement_costs_total_usd
  equation_id: resettlement_cost_total_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The per-person cost is the multiplier.
  priority: P2
- source: loss_ratio
  target: combined_ratio
  equation_id: loss_ratio_from_claims_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The combined ratio is loss plus expense.
  priority: P2
- source: premium_share_of_asset
  target: combined_ratio
  equation_id: loss_ratio_from_claims_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The share-of-asset premium is the expense side.
  priority: P2
- source: corporate_income_tax_rate
  target: discount_rate
  equation_id: wacc_definition
  relationship: functional
  direction: forward
  strength: hard
  description: The tax rate is the shield on the debt leg of the WACC.
  priority: P1
- source: investment_allowance_rate
  target: annualised_capex_usd_per_kw
  equation_id: annualised_capex
  relationship: functional
  direction: forward
  strength: soft
  description: The investment allowance reduces the effective capex; the current equation does not express the reduction and a future batch should write it.
  priority: P2
- source: accelerated_depreciation_factor
  target: discount_rate
  equation_id: wacc_definition
  relationship: functional
  direction: forward
  strength: soft
  description: Accelerated depreciation raises the effective tax shield; same future-batch caveat.
  priority: P2
- source: thin_capitalisation_limit
  target: debt_equity_ratio
  equation_id: wacc_definition
  relationship: constraint
  direction: forward
  strength: hard
  description: The thin-cap limit bounds the gearing.
  priority: P2
- source: premium_share_of_asset
  target: total_capacity_mw
  equation_id: annualised_capex
  relationship: functional
  direction: forward
  strength: soft
  description: Insurance premium scales with the insured capacity.
  priority: P2
- source: insurance_loss_share_of_cost
  target: annualised_capex_usd_per_kw
  equation_id: annualised_capex
  relationship: functional
  direction: forward
  strength: soft
  description: Insurance is a fraction of the same capex the annualisation is over.
  priority: P2
- source: land_acquisition_cost_per_hectare
  target: annualised_capex_usd_per_kw
  equation_id: annualised_capex
  relationship: functional
  direction: forward
  strength: soft
  description: Land cost is a component of the installed capex.
  priority: P2
- source: fpic_compliance_score
  target: land_use_conflict_index
  equation_id: land_availability_fraction
  relationship: functional
  direction: forward
  strength: soft
  description: Higher FPIC compliance lowers the conflict index; the graph carries no equation for this and a future batch should write it.
  priority: P2
- source: habitat_loss_hectares
  target: biodiversity_intactness_before
  equation_id: land_availability_fraction
  relationship: functional
  direction: forward
  strength: soft
  description: Habitat loss reduces biodiversity intactness; a documentation claim, not yet an equation.
  priority: P2
- source: grievance_redress_effectiveness
  target: fpic_compliance_score
  equation_id: land_availability_fraction
  relationship: functional
  direction: forward
  strength: soft
  description: A functioning grievance mechanism raises FPIC compliance; same caveat.
  priority: P2
```

---

## Register 4 — `cross_validation` (new)

Nine new rules.

```yaml
cross_validation:
- id: insurance_combined_below_loss
  condition: combined_ratio < loss_ratio
  severity: error
  message: The combined ratio is below the loss ratio, which would imply a negative expense ratio
  suggestion: Reconcile the two, or check the market-level assumption
- id: solvency_below_regulatory_floor
  condition: solvency_capital_ratio < 1.0
  severity: error
  message: A solvency capital ratio below 1.0 is below the regulatory floor in every prudential regime the sample contains
  suggestion: Raise solvency_capital_ratio, or record that the scenario models an insurer in breach
- id: retention_plus_deductible_above_unity
  condition: retention_share + deductible_share > 1.0
  severity: warning
  message: Retention plus deductible above unity means the insurer keeps more than the whole loss
  suggestion: Confirm the two shares are on the same basis
- id: resettlement_population_exceeds_exposed
  condition: resettlement_population_share > 1.0
  severity: error
  message: A resettlement population share above 1.0 is impossible
  suggestion: Confirm whether the share is of the exposed population or of the whole population
- id: compensation_below_market
  condition: compensation_share_of_market < 1.0
  severity: info
  message: A compensation package below market value is possible where only economic displacement applies, but under IFC Performance Standard 5 physical displacement requires replacement cost at minimum
  suggestion: Confirm the displacement category
- id: local_employment_exceeds_total
  condition: local_employment_share + women_employment_share + youth_employment_share > 2.0
  severity: warning
  message: Local, women and youth employment targets cannot all be met from the same headcount if their sum exceeds twice the workforce; they overlap and one constrains the others
  suggestion: Reconcile the targets against the workforce composition
- id: investment_allowance_with_thin_cap_conflict
  condition: investment_allowance_rate > 0.5 and thin_capitalisation_limit > 3.0
  severity: info
  message: A generous investment allowance with a permissive thin-cap limit is a tax regime that subsidises debt-financed capex
  suggestion: Confirm the two are intended to coexist
- id: vat_on_equipment_with_import_exemption
  condition: vat_rate > 0.10 and import_duty_equipment == 0
  severity: info
  message: Zero import duty with a positive VAT is a jurisdiction that exempts the tariff but not the consumption tax; worth flagging as a specific tax structure
  suggestion: Confirm the exemption structure
- id: accelerated_depreciation_exceeds_allowable
  condition: accelerated_depreciation_factor > 1.0 and investment_allowance_rate > 0.0
  severity: warning
  message: Accelerated depreciation and investment allowance stacking is a tax shield the sample's tax codes do not allow
  suggestion: Confirm the tax code permits both
```

---

## Coverage update

| Metric | After Batch 5 | After Batch 6 |
|---|---|---|
| Parameters declared | 889 | **913** |
| Equations declared | 64 | **75** |
| Relationships declared | 171 | **205** |
| Cross-validation rules declared | 46 | **55** |
| Parameters **determined** | 56 | **61** |
| Parameters **named** | 232 | **279** |
| Parameters **still uncoupled** | 657 | **634** |
| **Insurance — market-level** on the placeholder | ~15 | **0** |
| **Insurance — firm-specific** (declared unreachable) | 0 | **13 (permanently firm-specific)** |
| **Land/social** on the placeholder | ~40 | **0** |
| **Tax** on the placeholder | ~20 | **0** |
| `free` nodes with placeholder range `[0, 1e6]` | 349 | **262** |

**The remaining 262 placeholder nodes** are now concentrated in three groups:

1. **The 13 firm-specific insurance parameters** declared in Part B. These are not on the placeholder because the batch could not close them; they are on the placeholder because **no public document can specify them**. They will remain so until a firm supplies its own underwriting data, at which point the batch that closes them is a data-ingestion step, not a modelling step.

2. **The long tail of composite indices, organisational measures and qualitative scores** whose admissible set is genuinely undefined by any document. Approximately **180 nodes**. These include political targets, capability maturity scores, standard-and-protocol references, and private financing structures.

3. **The tax and land parameters of jurisdictions the sample does not contain**. Approximately **69 nodes**. Each needs the jurisdiction's own tax code or land registry.

**The next batch (7)** is the equation-library extension for the systems that remain thin after six batches: `energy_balance` (still one equation), `demand_supply` (still two), `inertia` (still two), `ppa_pricing` (still one), and `reliability` (now four but still without an explicit LOLP). Each is a substantive arithmetic addition, not a range sweep.

**The honest state of the graph after six batches:**

- 913 declared parameters
- 75 declared equations
- 205 declared relationships
- 55 cross-validation rules
- 61 parameters determined (6.7%)
- 279 parameters named (30.6%)
- 634 parameters still uncoupled (69.4%)
- 262 parameters still on the placeholder (28.7%)

The graph is more honest than it was after Batch 5: three of the four remaining groups are closed, the equation library has grown by a sixth, and the firm-specific class of parameter has been **explicitly named** rather than silently left on the placeholder. The remaining work is concentrated in the long tail and in the equation-library extension, and neither is a sweep — each is a case-by-case decision.