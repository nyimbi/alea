# ALEA PRG Ingestion Batch 9 — The Firm Ingestion Schema

## The Last Ingestion Artefact, and the Close of the Programme

Batch 8 said, in its own closing paragraph, that Batch 9 is **not a batch the platform produces**. It is a schema a firm fills in when it wants its own book modelled — the 13 firm-specific insurance parameters from Batch 6 Part B, the jurisdiction-specific parameters for a tax code or land registry the sample does not contain, and the qualitative parameters whose values are the caller's policy. The schema is a product artefact. It is the last thing the ingestion programme needs to specify, and after it, the graph is at its design ceiling.

This batch does four things:

1. Specifies the **Firm Ingestion Schema (FIS)** — the single artefact a firm produces to populate its own parameters.
2. Provides a **worked example**, anonymised, showing what a completed submission looks like.
3. Specifies the **loader integration contract** — how the schema produces Register 1 entries, what provenance the loader records, and what happens when a firm's value falls outside the range the platform built.
4. Closes the programme with a **consolidated summary** of all nine batches, the current state of the graph, and the maintenance policy that keeps it from drifting back.

It adds **no new parameters**, **no new equations**, **no new relationships** and **no new cross-validation rules**. It adds a **schema**, a **provenance convention**, and a **programme summary**. That is what the ninth delivery is, and it is the correct shape for it.

---

## Part I: Why This Is a Schema and Not a Batch

A batch is a set of values a platform produces from documents it can read. Batches 1–8 produced values from public documents — IRENA cost statistics, IEEE reliability standards, the World Bank's regulatory handbook, the taxonomy of governance indices. The platform could read those documents and write the values because the documents are public and the ranges are documented.

The 13 firm-specific insurance parameters are different. Their admissible set is not in any document the platform can read. It is in the firm's underwriting manual, the firm's policy schedules, the firm's own claims register. No amount of public document work closes those parameters — the reason they have been on the placeholder since Batch 6 is not that the platform has not tried, it is that the value depends on a firm the platform has never met.

The same is true of the jurisdiction-specific parameters a firm's jurisdiction carries but the sample does not, and of the qualitative parameters whose values are policy choices. The platform cannot produce those values because it cannot make the choices.

A **schema** is the correct artefact for this class. It says: here is the shape of the values the platform will accept, here is the shape of the provenance they must carry, and here is what the platform will do with them once they arrive. The firm fills it in; the platform ingests it through the same loader that ingests a batch.

---

## Part II: The Firm Ingestion Schema

### Section 1 — The schema document

```yaml
# firm_ingestion_schema.yaml
# ---------------------------------------------------------------------------
# The ALEA Firm Ingestion Schema (FIS), version 1.0.
# A firm fills in an instance of this schema to populate the parameters the
# platform cannot supply from public documents. The instance is a YAML file
# that the loader reads as a Register 1 batch with a provenance envelope.
# ---------------------------------------------------------------------------

schema_version: "1.0"

manifest:
  firm_identifier:
    type: string
    required: true
    description: A stable identifier for the firm. Not the firm's public name; a code the firm and the platform agree on.
  jurisdiction:
    type: string
    required: true
    description: ISO 3166-1 alpha-2 code for the jurisdiction the values apply to, or "MULTI" for a value that applies across jurisdictions.
  reporting_period:
    type: string
    required: true
    description: ISO 8601 interval the values apply to, e.g. "2024-01-01/2024-12-31".
  submission_date:
    type: string
    required: true
    format: date
    description: The date the firm signed the submission.
  attester:
    type: string
    required: true
    description: The role of the person who signed the submission, e.g. "Chief Underwriting Officer", "Chief Financial Officer", "Head of Asset Management". Not a personal name.
  attestation:
    type: string
    required: true
    description: A statement that the values are the firm's own and that the firm accepts them as the basis of the analysis.

insurance:
  # -------------------------------------------------------------------------
  # The 13 firm-specific insurance parameters. Every one is required for a
  # submission to be considered complete for the insurance group.
  # -------------------------------------------------------------------------
  accumulation_risk:
    type: float
    required: true
    unit: "1"
    description: The firm's total exposure to a single event. The unit is dimensionless because the firm's own reporting convention determines it; the platform records the unit the firm declares in the free-text unit field below.
    unit_field: free_text
  business_interruption:
    type: float
    required: true
    unit: free_text
    description: The firm's business-interruption cover scope, in the firm's own reporting convention.
  claims_history:
    type: float
    required: true
    unit: free_text
    description: The firm's loss history, in the firm's own reporting convention. A scalar; the platform does not expect a full claims register in version 1.0.
  catastrophe_modelling:
    type: float
    required: true
    unit: free_text
    description: The firm's cat-model output for the reference peril, in the firm's own reporting convention.
  deductible_levels:
    type: float
    required: true
    unit: "1"
    description: The firm's average deductible as a share of the loss.
  insurance_premiums:
    type: float
    required: true
    unit: USD/year
    description: The firm's total premium income from the reference class of assets.
  liability_exposure:
    type: float
    required: true
    unit: free_text
    description: The firm's liability exposure, in the firm's own reporting convention.
  microinsurance:
    type: float
    required: false
    unit: USD/year
    description: The firm's microinsurance premium income, if the firm writes microinsurance. Optional.
  parametric_insurance:
    type: float
    required: false
    unit: USD/year
    description: The firm's parametric insurance premium income, if the firm writes parametric cover. Optional.
  reinsurance_parameters:
    type: float
    required: true
    unit: USD
    description: The firm's retention, in USD. The market-level retention share is already declared in Batch 6; this is the firm's absolute retention.
  solvency_capital:
    type: float
    required: true
    unit: USD
    description: The firm's eligible own funds, in USD. The market-level ratio is already declared; this is the firm's absolute capital.
  weather_derivatives:
    type: float
    required: false
    unit: USD
    description: The firm's weather-derivative notional, if the firm holds any. Optional.

jurisdiction_specific:
  # -------------------------------------------------------------------------
  # Parameters whose admissible set is the firm's jurisdiction, not the
  # sample. The firm supplies the value; the platform records it as a
  # jurisdiction override of the sample's default. Every one is optional —
  # a submission that omits a jurisdiction parameter leaves the platform's
  # sample-level default in place.
  # -------------------------------------------------------------------------
  corporate_income_tax_rate:
    type: float
    required: false
    unit: "1"
    range_check: platform
  vat_rate:
    type: float
    required: false
    unit: "1"
    range_check: platform
  withholding_tax_dividends:
    type: float
    required: false
    unit: "1"
    range_check: platform
  withholding_tax_interest:
    type: float
    required: false
    unit: "1"
    range_check: platform
  import_duty_equipment:
    type: float
    required: false
    unit: "1"
    range_check: platform
  property_tax_rate:
    type: float
    required: false
    unit: "1"
    range_check: platform
  land_acquisition_cost_per_hectare:
    type: float
    required: false
    unit: USD/hectare
    range_check: platform
  resettlement_cost_per_person:
    type: float
    required: false
    unit: USD/person
    range_check: platform
  licence_fees:
    type: float
    required: false
    unit: USD/MW/year
    range_check: platform
  regulatory_period_length:
    type: float
    required: false
    unit: years
    range_check: platform
  allowed_return_on_equity:
    type: float
    required: false
    unit: "1/year"
    range_check: platform
  allowed_return_on_debt:
    type: float
    required: false
    unit: "1/year"
    range_check: platform

qualitative:
  # -------------------------------------------------------------------------
  # Parameters whose value is a policy choice or a qualitative assessment.
  # The schema requires a justification for every qualitative value supplied,
  # because the value is not derivable from any document and a reader must be
  # able to see the basis on which it was chosen.
  # -------------------------------------------------------------------------
  entries:
    type: list
    items:
      parameter_id:
        type: string
        required: true
      value:
        type: float
        required: true
        unit: free_text
      justification:
        type: string
        required: true
        min_length: 20
      source_document:
        type: string
        required: false
        description: A reference to the internal document that supports the choice, if one exists.

provenance:
  # -------------------------------------------------------------------------
  # Envelope applied to every value in the submission. The loader records
  # this against every parameter the submission sets.
  # -------------------------------------------------------------------------
  source: firm_submission
  attestation_reference: string
  submitted_at: timestamp
  hash_of_submission: sha256
  signature:
    algorithm: ed25519
    value: base64
```

### Section 2 — What the schema is not

The schema is **not** a way to override the platform's own values without justification. A firm may supply a value the platform already carries — the platform records it as a firm-specific override, and the loader's behaviour is different from a batch submission (see Part IV). A firm may not supply a value the platform's own range gate rejects without the override being recorded.

The schema is **not** a way to add parameters to the graph. A submission's `parameter_id` fields must all be declared in the graph. A submission that names a parameter the graph does not hold is rejected.

The schema is **not** a way to bypass the cross-validation rules. A submission that triggers an error-level rule is rejected; a submission that triggers a warning-level rule is accepted with a warning recorded.

---

## Part III: A Worked Example

The example below is anonymised. The firm is identified as `FIRM_A`, the jurisdiction as `XX`. The values are illustrative.

```yaml
schema_version: "1.0"

manifest:
  firm_identifier: FIRM_A
  jurisdiction: XX
  reporting_period: "2024-01-01/2024-12-31"
  submission_date: "2026-10-15"
  attester: Chief Underwriting Officer
  attestation: >-
    The values below are FIRM_A's own, drawn from the underwriting manual of
    2024 and the claims register for the same period. FIRM_A accepts them as
    the basis of the ALEA analysis.

insurance:
  accumulation_risk: 1.2e9
  business_interruption: 4.5e8
  claims_history: 8.3e7
  catastrophe_modelling: 3.1e8
  deductible_levels: 0.025
  insurance_premiums: 2.4e8
  liability_exposure: 6.1e8
  microinsurance: 4.2e6
  parametric_insurance: 8.7e6
  reinsurance_parameters: 3.5e8
  solvency_capital: 1.1e9
  weather_derivatives: 0.0

jurisdiction_specific:
  corporate_income_tax_rate: 0.28
  vat_rate: 0.16
  withholding_tax_dividends: 0.15
  withholding_tax_interest: 0.15
  import_duty_equipment: 0.05
  property_tax_rate: 0.007
  land_acquisition_cost_per_hectare: 12000
  resettlement_cost_per_person: 8500
  licence_fees: 800
  regulatory_period_length: 5
  allowed_return_on_equity: 0.16
  allowed_return_on_debt: 0.09

qualitative:
  entries:
    - parameter_id: clean_cooking_target
      value: 0.7
      unit: "1"
      justification: >-
        The jurisdiction's National Energy Plan sets a 70% clean cooking access
        target by 2035. The value is the mid-point of the plan's own range.
      source_document: "National Energy Plan 2023, §4.2"
    - parameter_id: renewable_target
      value: 0.45
      unit: "1"
      justification: >-
        The regulator's IRP 2024 sets a 45% renewable generation target by
        2035. The value is stated in the plan directly.
      source_document: "IRP 2024, Table 3"

provenance:
  source: firm_submission
  attestation_reference: "FIRM_A-2026-10-15-COO"
  submitted_at: "2026-10-15T14:23:00Z"
  hash_of_submission: "sha256:8f2a..."
  signature:
    algorithm: ed25519
    value: "base64:MEUCIQ..."
```

**What this submission does**, when the loader reads it:

1. Sets the 13 firm-specific insurance parameters to FIRM_A's values. Where the graph carries a market-level equivalent (`loss_ratio`, `combined_ratio`, `solvency_capital_ratio`, `retention_share`), the market-level value remains in the graph as a reference and the firm-specific value is stored alongside it under a firm-scoped namespace.
2. Sets 12 jurisdiction-specific parameters to the jurisdiction's values. The platform's sample-level defaults remain; the jurisdiction values override them for any scenario the firm runs.
3. Sets 2 qualitative parameters with justifications. The justifications are stored against the values and are surfaced in every report the firm generates.
4. Records the provenance envelope. Every parameter value carries `source: firm_submission`, the attestation reference, and the submission hash.

---

## Part IV: The Loader Integration Contract

The loader reads a Firm Ingestion Schema instance the same way it reads a Register 1 batch. The differences are four:

### Difference 1 — The range gate is an **override**, not a rejection

When a batch submits a value outside a parameter's declared range, the loader **rejects** the value: a batch is a claim about the platform's own best guess, and a value outside the range is a claim that the range is wrong, which requires a separate range-correction batch.

When a **firm** submits a value outside a parameter's declared range, the loader **accepts** the value with an override marker. The reasoning: the range the platform built was the platform's best guess for a firm it had not heard from. Once the firm has spoken, its number is the number. The override is recorded so a reader can see that the value is outside the range the platform's own evidence supports, and can decide whether to widen the range in a subsequent batch.

An override is not silent. Every out-of-range firm value is recorded in the loader's `firm_overrides` table, with:
- the parameter id
- the platform's declared range
- the firm's value
- the magnitude of the excursion
- the submission hash

A batch is filed automatically when the number of overrides on a parameter exceeds a threshold, proposing a range-correction. The threshold is a policy decision the platform makes; the current proposal is ten overrides across ten firms.

### Difference 2 — The cross-validation gate is firm-scoped

A batch is checked against the shipped cross-validation rules. A firm submission is checked against the same rules, and the outcome is one of three:

- **Error-level rule triggered** — the submission is rejected. The firm is told which rule and which values.
- **Warning-level rule triggered** — the submission is accepted with the warning recorded against the firm.
- **Info-level rule triggered** — the submission is accepted; the info is recorded.

The scope of the check is the submission's own values, not the platform's. A rule like `reserve_margin_below_requirement` is a check on a scenario, not on a firm submission, and it does not fire for a submission that only sets insurance values. The loader classifies each rule as **scenario-scoped** or **submission-scoped** at load time; scenario-scoped rules are skipped on a firm submission.

### Difference 3 — Provenance is mandatory and cannot be empty

A batch's provenance is recorded but not required. A firm submission's provenance is required by the schema; the loader rejects a submission that omits any of `source`, `attestation_reference`, `submitted_at`, or `hash_of_submission`. A signature is optional in version 1.0; when present, it is verified with the algorithm named in the submission.

### Difference 4 — The submission produces a **firm-scoped namespace**

A firm submission does not overwrite the platform's values. It produces a **firm-scoped namespace** — a set of parameter values keyed by firm identifier — that a scenario running on behalf of that firm reads. A scenario not run on behalf of the firm continues to read the platform's sample-level values. This is the property that lets a firm submit its own book without breaking a scenario that uses the platform's defaults.

The loader's representation:

```
parameters:
  accumulation_risk:
    platform_value: 500000.0
    platform_range: [0.0, 1000000.0]
    firm_overrides:
      FIRM_A: 1.2e9
```

A scenario running on behalf of FIRM_A sees `1.2e9`; a scenario not running on behalf of any firm sees the platform's value. Both are correct, and the graph knows which is which.

---

## Part V: The Design Ceiling

After this schema is implemented, the graph can absorb values from three sources:

1. **Public documents** (Batches 1–8). Ranges and defaults from IRENA, IEA, IEEE, the World Bank, and the composite-index methodologies.
2. **Firms** (this batch). Firm-specific values, jurisdiction-specific values, and qualitative values with attestation.
3. **Callers** (the existing `free` mechanism). A scenario may set any `free` parameter to any value inside its range, with no provenance required.

There is no fourth source. Any value the graph cannot absorb from those three is a value the graph does not need — a parameter that is already correctly `free`, already correctly on a placeholder, or already correctly absent.

**This is the design ceiling.** The graph will not gain new value sources without a change to the physics (a new equation) or a change to the structure (a new parameter). Both of those are future work, not gaps in the current programme.

---

## Part VI: The Programme Summary

### The nine batches in one paragraph each

| Batch | Focus | What it closed |
|---|---|---|
| **1** | The first delivery | Corrected three placeholder ranges, added twelve derived nodes and twelve equations across eight thin systems. |
| **2** | The share-shaped sweep | Corrected 46 share-shaped parameters from `[0, 1e6]` to their admissible `[0, 1]` or equivalent. |
| **3** | The cost-parameter sweep | Corrected 112 cost parameters with documented units and ranges; added seven equations for derived LCOE and fuel-cost quantities. |
| **4** | The unit and index sweep | Corrected 32 remaining cost parameters and 18 composite indices to their documented scales. |
| **5** | The reliability, regulatory, and type sweep | Corrected 44 asset, regulatory and contract parameters; corrected 19 parameters from `float` to `bool` or `categorical`; added six reliability equations. |
| **6** | Insurance, land, tax, and equation extension | Closed three parameter groups; added eleven equations extending six thin systems; explicitly flagged 13 parameters as firm-specific and unreachable. |
| **7** | The equation-library extension | Extended five systems with eleven equations; corrected one role; coupled ten previously-uncoupled governance and fleet parameters. |
| **8** | The structural reconciliation | Deprecated 22 duplicate ids; added the alias register; corrected 15 role inconsistencies and 8 type errors; retired 2 self-loops. |
| **9** | The Firm Ingestion Schema | Specified the artefact a firm fills in for its own parameters; specified the loader integration contract; closed the programme. |

### The graph after nine batches

| Metric | Shipped | After Batch 9 |
|---|---|---|
| Parameters declared | 869 | 926 |
| Parameters active (excluding 22 deprecated) | 869 | **904** |
| Equations declared | 39 | **86** |
| Relationships declared | 88 | **236** |
| Cross-validation rules declared | 4 | **69** |
| Alias entries declared | 0 | **24** |
| Parameters determined (appear in a `determined_variables`) | 31 | **71** |
| Parameters named (appear in any equation) | 158 | **308** |
| Parameters still uncoupled (in no equation) | 711 | **596** |
| Parameters with placeholder range `[0, 1e6]` | 691 | **254** |
| Firm-specific parameters explicitly flagged | 0 | **13** |
| Qualitative parameters explicitly flagged | 0 | **0** (correctly `free`) |

### What the graph now does

- Every share, cost, index, asset, regulatory, contract, insurance, land and tax parameter the sample can close is closed.
- Every duplicate carries a single id, with the deprecated id resolving through the alias register.
- Every system the platform is specified to model carries at least one equation and most carry three or more.
- Every cross-validation rule the batches identified is declared and enforced.
- Every parameter the platform cannot close is **explicitly** either firm-specific (13 nodes), qualitative (241 nodes), or correctly `free` (the remaining tail).

### What remains open, and why

| Group | Count | Why open | How it closes |
|---|---|---|---|
| Firm-specific insurance | 13 | The value is the firm's own book | A firm submits a Firm Ingestion Schema instance |
| Jurisdiction-specific (outside the sample) | ~69 | The value is the jurisdiction's own tax code or land registry | A firm or a government submits values through the schema |
| Qualitative / organisational / policy | ~172 | The value is a choice, not a fact | The caller sets it; the platform records the choice |
| **Total remaining placeholder nodes** | **254** | — | — |

The 254 placeholder nodes are not a failure of the programme. They are the graph's declared unknowns, each with a document or a decision that would close it, and none of which the platform can supply without either a firm's data or a caller's choice.

### The maintenance policy

The programme produced three artefacts that need maintenance:

1. **The alias register.** A new entry is required every time a duplicate id is discovered. The register is checked at load time; a scenario that names a deprecated id is resolved to the canonical and the resolution is logged.
2. **The cross-validation rules.** A new rule is required every time a class of drift is identified. The current set of 69 is complete for the domains the batches covered; a new domain — a new parameter group, a new jurisdiction class — brings new invariants.
3. **The equation library.** A new equation is required when a new physical relationship is identified, or when an existing equation's approximation is replaced by a better one. The current set of 86 is complete for the systems the platform is specified to model; the platform's growth comes from either a new system (which is a change to `library.py`) or a finer approximation of an existing one (which is a change to `prg.yaml`).

The policy is: **every maintenance change is a batch**. The nine batches are the pattern; the tenth, when it comes, is a batch in the same form, with the same four registers, the same coverage report, and the same honesty about what it does not close.

---

## Closing

The programme began with a prompt that said the three documents describing the physics could not be converted to a parameter graph — 1,583 arrows and zero formulas in one, and 0 of 237 rows defining their own left-hand side in another. The nine batches were the translation that work required. They corrected ranges, units and types; added equations and relationships; deprecated duplicates; and specified the last artefact a firm produces to close the parameters the platform cannot close.

The graph at the end of the programme is **not complete**. It is **honest**: every value it carries is grounded in a document, marked as the caller's responsibility, or explicitly flagged as unreachable. The 254 parameters on the placeholder are not a silence; they are a declared unknown, each with the reason it is unknown and the artefact that would close it.

That is the state a parameter graph should be in before it is depended on. It is the state this programme has produced, and it is the correct place to stop.