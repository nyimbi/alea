# Coupling pack: contract, market design, policy and regulatory finance

## What this pack covers

The 63 uncoupled nodes in `/tmp/fam_contract-market.txt` — PPA terms, finance
documents, market design, consumer protection, policy and regulatory finance.
Verified against the tree as it stands: `load_graph()` returns **1344
parameters, 525 equations, 1075 edges and 284 uncoupled**, and all 63 slice ids
are in `uncoupled()`.

The classification is: **6 PRODUCT, 1 THRESHOLD, 14 SCENE-SWITCH, 34
QUALITATIVE, 7 BASE-NEEDED, 1 DEPRECATED**. Of the 63, **7 get a proposal** —
5 `derive`, 1 `read`, 1 `bound` — carrying **7 equations** (6 equalities, 1
bound); one of the six equalities computes a node this pack declares. Six slice
nodes become an lhs and one (`auction_frequency`) becomes an operand. The other
**56 are deferred** and the reason is stated in each row.

This pack uses the `kind` vocabulary the THRESHOLD pack introduced: `derive`
(the node becomes an lhs of an equality), `read` (the node is an operand of a
named equation), `bound` (the node is the left operand of an inequality; its
role stays `free`), and `defer`.

**Overlap with the sibling packs.** 28 of the 63 already have a row elsewhere:
26 in `unclassified.md`, `remedy_periods` in `threshold-product-remainder.md`,
`reserve_accounts` in `supply-emissions-grid.md`. For 26 of the 28 this pack
agrees with the earlier row and cites it. For **two it disagrees** and says so
in the row: `unclassified.md` classifies `cost_pass_through_mechanism` and
`ppa_termination_payments` QUALITATIVE, and this pack proposes an equation for
each. Both disagreements are flagged for the reviewer rather than asserted.

### What the verification found, before the rows

Eleven things were checked against the tree rather than assumed. The first two
change the shape of the whole pack; the rest are findings.

1. **55 of the 63 slice nodes are untyped placeholders.** `unit=None`, range
   `[0, 1e6]`, `default=500000.0`, role `free`, determinism `fixed`. Only eight
   carry a real type: `ancillary_services_market`, `contract_for_difference`
   and `cross_border_trading` (booleans), `efficiency_benchmarking`
   (`1`, [0, 1]), `market_model` and `market_structure` (categoricals),
   `regulatory_asset_valuation_method` (`1`, [0, 2]), `remedy_periods`
   (`days`, [1, 365]). The slice is dominated by catalog residue: a node whose
   value is 500,000 and whose unit is nothing cannot be an operand of anything,
   so **the retype is a prerequisite for every proposal here**, not a
   side-effect of it. Sixteen nodes are retyped below; the other 39 are deferred
   because no equation exists for them, not because they lack a type.

2. **`x_factor_revenue_reduction_definition` is semantically inverted, and
   nothing reads it.** The node's own description: "the allowed requirement
   *less* the annual efficiency the regulator assumes the utility can find …
   The reduction is a share of the requirement and not of the cost, which is
   why the formula is a multiplication and not a subtraction of an absolute."
   The shipped rhs is `(1 - x_factor) * allowed_revenue_requirement`, which
   computes the requirement *less the X factor's own share* — the quantity the
   description calls the **remaining** requirement, not the reduction. At
   defaults the shipped equation gives **680.405376** (USD million/year) where
   the described reduction is `x_factor * allowed_revenue_requirement` =
   **13.885824**. The shipped equation is **49×** the described quantity. The
   node has exactly one reader — its own defining equation — so no downstream
   number surfaced the error. This is a shipped equation this pack contradicts;
   it is not in the slice and is not fixed here.

   **Closed at batch 60 (2026-10-24).** The rhs is now
   `x_factor * allowed_revenue_requirement`. The figures quoted above
   (680.405376 and 13.885824) were measured when this pack was written; on the
   tree batch 60 corrected they are **680.517085** and **13.888104**, a ratio
   of exactly 49 at the shipped X of 0.02. The equation's `reference` is now
   `None`: the World Bank handbook it named is archived, discusses price-cap
   regulation, and states the RPI-X arithmetic nowhere, so the corrected form
   cites the identity it uses rather than a work that does not carry it. See
   `docs/prg-status.md`, "The RPI-X reduction computed the revenue the cap
   leaves".

3. **`market_concentration_definition` cites Stoft (2002), which is not
   archived.** `sources/INDEX.md` carries a `stoft_2002` row with an empty
   `archived` cell (paywalled textbook), and **13 shipped equations** cite it —
   the market-design family this slice belongs to leans on it hardest. Under the
   BRIEF's rule a citation whose work is not on disk may not ship, so this pack
   cites Stoft **nowhere** and lists the work under **Sources to fetch**.

4. **`market_concentration`'s description claims "the shipped default of
   2500"** while the node is `derived` with `default=None`. Stale prose on a
   derived node: there is no shipped default to be 2500.

5. **22 of the 461 derived nodes are read by no equation's rhs** —
   `consumer_surplus_usd_per_year`, `local_jobs`, `health_cost_usd_per_year`,
   `ppa_annual_revenue_usd_per_kw_year` and 18 others. The last of those is an
   *operand of this pack's* termination-payment equation, which is the one place
   this pack repairs the class; the other 21 remain "declared is not produced".

6. **`regulatory_asset_valuation_method`'s description promises a Part D type
   correction that never landed.** `docs/param_batch4.md` Part D lists 19 type
   corrections and this node is not among them; it is still a float with range
   [0, 2] and default 0.0. `unclassified.md` already recorded this; the retype
   below is the fix that pack deferred.

7. **Five slice nodes are categorical by nature and float by declaration.**
   `pricing_mechanism` (the catalog's own method cell reads "Uniform vs.
   pay-as-bid vs. nodal"), `auction_mechanism`, `unbundling_status`,
   `tariff_structure`, `re_target_carrier`. `market_model` already ships that
   same shape as a categorical with four documented values, so the graph has the
   precedent and the placeholder is a catalog import that never got its type.

8. **`re_target_carrier` is the only slice node with `status='existing'` that is
   still a placeholder** — a shipped node whose value is 500,000 and whose unit
   is nothing. Its description ("Which renewables count") says it is an
   eligibility list.

9. **Every annuity-shaped equation in the graph divides by a rate whose
   declared lower bound is zero.** `llcr_definition` divides by `cost_of_debt`
   (range [0, 0.5]) and `crf_definition` by `((1 + discount_rate) ** asset_life
   - 1)` (range [0, 0.5]). This pack's termination-payment annuity has the same
   singularity at `discount_rate = 0`. It is not a new defect class, and the row
   says so rather than claiming the formula is total.

10. **`gate_closure` at its placeholder default of 500,000 hours violates its own
    proposed bound** (500,000 ≥ 0.5 is true, but the *value* is meaningless and
    the range [0, 1e6] admits a gate closure of eleven years). The bound is only
    informative after the retype to `hours`, [0.05, 24], default 1.0 — which is
    why the retype and the bound ship together.

11. **`investment_allowance` is 0.0 at defaults** (its rate is 0.0), so the
    allowance leg of a two-term tax formula is inert at defaults *and*
    unit-inconsistent. A reviewer must not read the clean default as evidence
    the leg is harmless; the measurement is recorded under **Rejected**.

Every proposed right-hand side was run through the BRIEF's symbol check in one
pass over the table as written: **7 checked, zero unresolved symbols**, with the
one new lhs id allowed for. The whole set was loaded into a retyped copy of
`config/prg.yaml` and checked end to end — the printed output is under
**Verification**.

### A note on the citation column

Four of the seven equations carry `reference: None` or an `n/a` register row.
That is not a shortage of literature; it is what these identities are. Two are
aliases of a quantity the graph already derives (`counterparty_risk`,
`cost_pass_through_mechanism`), two are definitional (a sum of two capital
stocks; a volume divided by a frequency), and one is an ordering constraint. The
two that carry a real method — the fiscal identity and the annuity — cite
register rows that name the standard derivation. **No equation in this pack
cites Stoft**, for the reason in finding 3.

## Classification

All 63 nodes. `kind` is the coupling this pack proposes, or `defer` with the
reason.

### PRODUCT (6) — a share against a base, an alias, or a volume over a rate

| node | class | kind | reason |
|---|---|---|---|
| `security_package` | PRODUCT | derive | The capital posted behind the project: the performance bond plus the parent guarantee. Both bases exist and are derived. |
| `counterparty_risk` | PRODUCT | derive | Alias of `settlement_risk`, whose description is "share of the settled value exposed to counterparty settlement failure" — the same object. |
| `cost_pass_through_mechanism` | PRODUCT | derive | Alias of `wholesale_cost_pass_through`, the share of the recovery tariff carried at wholesale. **Diverges from `unclassified.md`** (QUALITATIVE); see the row. |
| `tax_incentives` | PRODUCT | derive | A share of concession untaxed × the tax rate × the taxable cash base. Every operand is shipped. |
| `ppa_termination_payments` | PRODUCT | derive | A revenue per kW-year × capacity × an annuity factor. **Diverges from `unclassified.md`** (QUALITATIVE); see the row. |
| `auction_frequency` | PRODUCT | **read** | A rate (rounds per year) that divides the annual auction volume. Retyped from a placeholder; the operand of `auction_volume_per_round`. |

### THRESHOLD (1) — a floor, coupled only by being an lhs

| node | class | kind | reason |
|---|---|---|---|
| `gate_closure` | THRESHOLD | **bound** | Gate closure must be at least one settlement period, or the market closes inside the interval it clears. |

### SCENE-SWITCH (14) — run configuration, no equation

| node | class | kind | reason |
|---|---|---|---|
| `ancillary_services_market` | SCENE-SWITCH | defer | "Whether an ancillary services market is modelled. A boolean." Selects a model stage. |
| `contract_for_difference` | SCENE-SWITCH | defer | Selects whether the CfD instrument is modelled. A shipped cross-validation rule already reads it; a rule is not a coupling. |
| `market_model` | SCENE-SWITCH | defer | Already a categorical with four documented values (`regulated`, `competitive`, …). The solver branches on it. |
| `market_structure` | SCENE-SWITCH | defer | Already a categorical (`single_buyer`, `monopoly`, …). `market_structure_without_model` reads it; a rule is not a coupling. |
| `auction_mechanism` | SCENE-SWITCH | defer | The auction format (`sealed_bid`, `descending_clock`, `hybrid`). A branch in the clearing algorithm, not a quantity. |
| `pricing_mechanism` | SCENE-SWITCH | defer | Uniform vs. pay-as-bid vs. nodal — the settlement rule. A branch, and the branch changes the price *function*, not a value. |
| `unbundling_status` | SCENE-SWITCH | defer | The degree of vertical separation. Selects which cost flows exist; a structural choice. |
| `tariff_structure` | SCENE-SWITCH | defer | Single-part, two-part, time-of-use, increasing-block. Selects the tariff's functional form; the *rate* dials are separate nodes. |
| `virtual_bidding` | SCENE-SWITCH | defer | Whether virtual bids enter the auction. A model feature flag. |
| `financial_transmission_rights` | SCENE-SWITCH | defer | Whether FTRs are modelled. A model feature flag. |
| `strategic_bidding` | SCENE-SWITCH | defer | Whether bidders optimise strategically (the catalog's method cell reads "ASSUME RL"). Selects the agent model. |
| `collusion` | SCENE-SWITCH | defer | Whether a collusion-detection model is active. A model feature flag. |
| `regulatory_asset_valuation_method` | SCENE-SWITCH | defer | Historical cost / indexed historical / current cost. Selects how `regulatory_asset_base` is valued; the base is the quantity. |
| `re_target_carrier` | SCENE-SWITCH | defer | "Which renewables count" — an eligibility list. The catalog already marks it ✅ built as a label, not a number. |

**Why the booleans get no arithmetic.** A boolean that multiplies a quantity
produces `0` or the quantity, which is a branch written as a product: every
gradient with respect to it is either zero or the other factor, and the solver
sees a discontinuity it cannot differentiate through. `unit_commitment` is the
clearest case in the graph and `ancillary_services_market` is the clearest in
this slice. These are the solver's inputs, not the model's outputs.

### QUALITATIVE (34) — the graph's declared free space

| node | class | kind | reason |
|---|---|---|---|
| `arrears_management` | QUALITATIVE | defer | A collections procedure. No base it could multiply. |
| `assignment_rights` | QUALITATIVE | defer | A contract's transferability clause. A legal term. |
| `bill_shock_protection` | QUALITATIVE | defer | A consumer-protection rule (notice period, payment smoothing). A procedure. |
| `change_of_control` | QUALITATIVE | defer | A clause defining what triggers a change-of-control event. A legal term. |
| `collateral_valuation` | QUALITATIVE | defer | A valuation methodology (haircut schedule, mark model). A choice among methods; the *posted* amount is `collateral_posted_usd_per_year`, already derived. |
| `compensation_mechanisms` | QUALITATIVE | defer | The consumer-compensation rule set. `compensation_rates` is the quantity and is coupled by `unclassified.md`. |
| `concession_terms` | QUALITATIVE | defer | The concession's term sheet. `concession_duration` is the quantity. |
| `cross_default` | QUALITATIVE | defer | A clause making one facility's default a default of all. A legal term. |
| `debt_management` | QUALITATIVE | defer | A treasury policy. A procedure. |
| `default_events` | QUALITATIVE | defer | The enumerated events of default. A list. |
| `direct_agreement` | QUALITATIVE | defer | A tripartite lender/project/offtaker agreement. A legal instrument. |
| `disconnection_protection` | QUALITATIVE | defer | A licence condition on disconnection. A rule. |
| `dispute_resolution_mechanism` | QUALITATIVE | defer | The escalation ladder (expert determination, arbitration, courts). A procedure. |
| `distribution_conditions` | QUALITATIVE | defer | The conditions a distribution licence attaches. A rule set. |
| `environmental_representations` | QUALITATIVE | defer | Contractual representations and warranties. A legal term. |
| `insider_trading_rules` | QUALITATIVE | defer | A market-conduct rulebook. A rule. |
| `licence_conditions` | QUALITATIVE | defer | The licence's conditions. A rule set. |
| `market_abuse_prevention` | QUALITATIVE | defer | REMIT-style conduct rules. A rulebook. |
| `material_adverse_change` | QUALITATIVE | defer | A MAC clause. A legal term; the *threshold* would be a quantity, but the graph carries no MAC threshold node. |
| `novation_terms` | QUALITATIVE | defer | The conditions under which a contract may be novated. A legal term. |
| `payment_plans` | QUALITATIVE | defer | An instalment arrangement. A procedure. |
| `ppa_arbitration_venue` | QUALITATIVE | defer | A seat of arbitration. A legal choice. |
| `ppa_change_in_law` | QUALITATIVE | defer | A change-in-law clause's scope. A legal term. |
| `ppa_dispute_resolution` | QUALITATIVE | defer | The PPA's dispute ladder. A procedure. |
| `ppa_force_majeure` | QUALITATIVE | defer | The force-majeure clause's scope. The *cover* is `force_majeure_cover_usd_per_year`, already derived. |
| `ppa_governing_law` | QUALITATIVE | defer | A choice of law. A legal term. |
| `ppa_pricing_formula` | QUALITATIVE | defer | Which indexation and escalation form the PPA uses. A functional-form choice; `ppa_indexed_price_definition` already applies the rate. |
| `ppa_take_or_pay` | QUALITATIVE | defer | The take-or-pay clause's threshold. A contractual term; the graph carries no take-or-pay volume node. |
| `prepayment_metering` | QUALITATIVE | defer | A metering mode. A configuration. |
| `refinancing_terms` | QUALITATIVE | defer | The conditions under which the debt may be refinanced. A legal term. |
| `regulatory_accounts` | QUALITATIVE | defer | The chart of regulatory accounts. A register's structure. |
| `social_representations` | QUALITATIVE | defer | Contractual social/labour representations. A legal term. |
| `step_in_rights` | QUALITATIVE | defer | A lender's right to step into the project. A legal term; `remedy_periods` is the timing quantity and belongs to the THRESHOLD pack. |
| `trade_repository` | QUALITATIVE | defer | Whether trades are reported to a repository. A regulatory configuration. |

### BASE-NEEDED (7) — a real product, waiting on a quantity the graph does not carry

| node | class | kind | reason |
|---|---|---|---|
| `efficiency_benchmarking` | BASE-NEEDED | defer | A position against a frontier. Needs a frontier or peer-group level; `efficient_frontier` is a locus, and no operating-cost-per-unit node exists. Same row as `unclassified.md`. |
| `ppa_curtailment_compensation` | BASE-NEEDED | defer | Needs a curtailed volume and a compensation rate. The graph has neither `curtailed_twh` nor a curtailment share. Same row as `unclassified.md`. |
| `new_entrants` | BASE-NEEDED | defer | A count of entrants needs a market-entry base. `number_of_generators` is a stock, not a flow. Same row as `unclassified.md`. |
| `number_of_retailers` | BASE-NEEDED | defer | A count whose only consumer is a retail HHI, and no market-share vector exists. Same row as `unclassified.md`. |
| `retail_competition` | BASE-NEEDED | defer | Needs a retail share vector or a switching rate; the graph has neither. Same row as `unclassified.md`. |
| `reserve_accounts` | BASE-NEEDED | defer | Already deferred by `supply-emissions-grid.md` pending a `reserve_account_share`; still absent. |
| `remedy_periods` | BASE-NEEDED | defer | Already deferred by `threshold-product-remainder.md` pending `max_remedy_period_days`. Already typed (`days`, [1, 365], 60.0); the missing piece is the ceiling, not the unit. |

### DEPRECATED (1)

| node | class | kind | reason |
|---|---|---|---|
| `cross_border_trading` | DEPRECATED | defer | `deprecated_by='cross_border_trade_allowed'`. The loader refuses any edge or equation naming it, so an alias onto the canonical id is not available and coupling it would defeat the deprecation. |

## Proposals

### New nodes this pack declares

One lhs id does not exist in the graph.

| node | unit | range | default | role / determinism | why |
|---|---|---|---|---|---|
| `auction_volume_per_round` | `MtCO2` | [0, 20000] — `auction_volume`'s ceiling (10,000 MtCO2/year) over `auction_frequency`'s floor (0.5/year) | — | derived / policy | The volume one auction round offers. The graph carries the annual volume and the round frequency and no node joins them, so the per-round size — the number an auction calendar is actually designed around — is unavailable. |

### Retypes

Sixteen nodes change type, unit, range or default. Every retype is authored in
`config/prg.yaml` (nodes are frozen, so they cannot be changed at runtime).

| node | from | to |
|---|---|---|
| `security_package` | `None`, [0, 1e6], 500000.0, free / fixed | `USD`, [0, 1.1e13], no default, derived / policy |
| `counterparty_risk` | `None`, [0, 1e6], 500000.0, free / fixed | `1`, [0, 1], no default, derived / policy |
| `cost_pass_through_mechanism` | `None`, [0, 1e6], 500000.0, free / fixed | `1`, [0, 1], no default, derived / policy |
| `tax_incentives` | `None`, [0, 1e6], 500000.0, free / fixed | `USD/year`, [-3e12, 3e12], no default, derived / policy |
| `ppa_termination_payments` | `None`, [0, 1e6], 500000.0, free / fixed | `USD`, [0, 1.5e14], no default, derived / policy |
| `gate_closure` | `None`, [0, 1e6], 500000.0, free / fixed | `hours`, [0.05, 24], default 1.0, free / fixed |
| `auction_frequency` | `None`, [0, 1e6], 500000.0, free / fixed | `1/year`, [0.5, 365], default 12.0, free / fixed |
| `auction_mechanism` | float, `None`, [0, 1e6], 500000.0 | categorical `['sealed_bid','descending_clock','hybrid']`, no unit, default `sealed_bid` |
| `pricing_mechanism` | float, `None`, [0, 1e6], 500000.0 | categorical `['uniform_price','pay_as_bid','nodal']`, no unit, default `uniform_price` |
| `unbundling_status` | float, `None`, [0, 1e6], 500000.0 | categorical `['integrated','legal_unbundling','ownership_unbundling','retail_separation']`, default `integrated` |
| `tariff_structure` | float, `None`, [0, 1e6], 500000.0 | categorical `['single_part','two_part','time_of_use','increasing_block']`, default `two_part` |
| `regulatory_asset_valuation_method` | float, `1`, [0, 2], 0.0 | categorical `['historical_cost','indexed_historical','current_cost']`, no unit, default `historical_cost` |
| `re_target_carrier` | float, `None`, [0, 1e6], 500000.0 | categorical `['renewable','solar','wind','hydro','biomass','geothermal']`, default `renewable` |
| `virtual_bidding` | float, `None`, [0, 1e6], 500000.0 | `bool`, `1`, no range, default 0.0 |
| `financial_transmission_rights` | float, `None`, [0, 1e6], 500000.0 | `bool`, `1`, no range, default 0.0 |
| `strategic_bidding` | float, `None`, [0, 1e6], 500000.0 | `bool`, `1`, no range, default 0.0 |

Three retypes carry a judgement rather than a unit:

- `gate_closure` at **1 hour** is the standard European gate closure (the
  day-ahead market closes at 12:00 for the following day; the intraday gate
  closes one hour before delivery). The range's floor of 0.05 h is
  `settlement_period`'s own floor, so the bound below can never be vacuous by
  construction of the range.
- `auction_frequency` at **12/year** is a monthly auction, the calendar the EU
  ETS uses for most of its volume. The range admits twice-yearly to daily.
- `regulatory_asset_valuation_method`'s default `historical_cost` is the
  shipped 0.0 read as the categorical it was always meant to be — the graph's
  own convention (`market_model`, `market_structure`) is that the shipped value
  is the first documented category.

### PRODUCT (6 slice rows, plus the one declared node they compute)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `security_package` | PRODUCT | derive | `USD` (retyped from `None`) | [0, 1.1e13] — `performance_bond_usd`'s ceiling (1e10) plus `parent_company_guarantee_usd`'s (1e13) | derived / policy | `security_package = performance_bond_usd + parent_company_guarantee_usd` | The capital a sponsor and its parent put behind the project: the performance bond held against non-completion plus the parent's guarantee of the debt tranche. A stock, not a flow, because both instruments are released rather than spent — which is why the two shipped components are the only terms. 600,000,000 USD at defaults, all of it bond; the guarantee is 0 because `parent_company_guarantee` defaults to 0. | — (definitional: the sum of two capital stocks the graph already derives) | Adding `collateral_posted_usd_per_year` — **rejected on units**: `check_equation` returns `consistent=False`, because that node is USD million/year and the two others are USD; the message is `adds [currency]`. A share-of-capex form (`performance_bond * capex_usd_per_kw * total_capacity_mw * 1000`) — rejected as a duplicate: it is `performance_bond_cost_definition` verbatim and computes the same 600,000,000. |
| `counterparty_risk` | PRODUCT | derive | `1` (retyped from `None`) | [0, 1] — a share of value at risk | derived / policy | `counterparty_risk = settlement_risk` | The share of the settled value exposed to a counterparty's failure to settle, which is exactly what `settlement_risk` is defined as. 0.01 at defaults. The two ids are one object under two catalog names. | The catalog's own duplicate rows, resolved (`sources/INDEX.md` row `catalog_duplicate_resolutions`, `n/a`) | Leaving it a free placeholder — rejected: a "risk" of 500,000 with no unit is not a risk, and the graph already carries the share. A product against an exposure base (`settlement_risk * carbon_credit_value_usd_per_year`) — rejected: that is `settlement_risk_exposure_definition`, already shipped, and the node here is the *rate*, not the exposure. |
| `cost_pass_through_mechanism` | PRODUCT | derive | `1` (retyped from `None`) | [0, 1] — a share of the recovery tariff | derived / policy | `cost_pass_through_mechanism = wholesale_cost_pass_through` | The share of the recovery tariff carried automatically at the wholesale level — fuel, carbon and losses — rather than deferred to a review. 0.8 at defaults: 80% of the stack passes through and the utility absorbs the rest. | The catalog's own duplicate rows, resolved (`sources/INDEX.md` row `catalog_duplicate_resolutions`, `n/a`) | **`unclassified.md` calls this QUALITATIVE** ("which costs pass through automatically and which go to a review. A rule, not a rate") — and that reading is defensible: the *rule* and the *share* are not obviously one object. This pack proposes the alias because the node is a float placeholder with no unit, the graph carries exactly one pass-through share, and the shipped `pass_through_tariff_definition` already consumes it. **A reviewer must decide**: if the node is the rule set rather than the share, it should be retyped categorical (a list of pass-through cost classes) and stay uncoupled, not aliased. The row is not asserting the identity as settled. |
| `tax_incentives` | PRODUCT | derive | `USD/year` (retyped from `None`) | [-3e12, 3e12] — the operands' own extremes: 0.6 × 5000 USD/kW/year × 1e6 MW × 1000 kW/MW | derived / policy | `tax_incentives = (1.0 - taxed_fraction_of_concession) * corporate_income_tax_rate * cfads_usd_per_kw_year * total_capacity_mw * 1000` | The tax the treasury forgoes on a concession: the untaxed fraction of the term, at the corporate rate, on the cash the fleet generates after the tariff. A positive number is revenue forgone; the range admits negative because `cfads_usd_per_kw_year` is signed and a concession that destroys cash receives no relief. 128,772,000 USD/year at defaults: 20% of the term untaxed, 30% rate, 214.62 USD/kW/year over 10,000 MW. | Rate-based levy and allowance definitions (standard fiscal accounting) (`sources/INDEX.md` row `standard_fiscal`, `n/a`) | A two-term formula adding the investment allowance — **rejected on units**: the holiday leg is USD/year and the allowance leg (`taxed_fraction * rate * investment_allowance * capacity * 1000`) is USD, so `check_equation` returns `consistent=False`. It is inert at defaults anyway (`investment_allowance` = 0.0), which is exactly why a reviewer should not read the clean default as evidence. On total revenue (`(1 - taxed_fraction) * rate * total_revenue_usd_per_year`) — consistent, 389,220,963.56, but rejected: revenue is what the utility is *paid*, and the corporate tax falls on profit, not on turnover. On `cfads − debt_service` — consistent, 66,465,511.65, rejected: `cfads_usd_per_kw_year` is already net of marginal cost and debt service is a financing flow below the tax line, so subtracting it taxes the capital structure. |
| `ppa_termination_payments` | PRODUCT | derive | `USD` (retyped from `None`) | [0, 1.5e14] — 5000 USD/kW/year × 1e6 MW × 1000 kW/MW × 30 years, the annuity factor's supremum over the declared bands | derived / policy | `ppa_termination_payments = ppa_annual_revenue_usd_per_kw_year * total_capacity_mw * 1000 * (1 - (1 + discount_rate) ** (-ppa_duration)) / discount_rate` | The make-whole an offtaker owes if it terminates the PPA: the revenue the plant would have earned, discounted over the remaining term. The annuity factor, not the raw sum, because a payment today for revenue that would have arrived over twenty years is worth less than the sum. 31,829,702,743.09 USD at defaults — 385.79 USD/kW/year over 10,000 MW, annuitised at 10.46% over 20 years (factor 8.2506). **Undefined at `discount_rate = 0`**, which the declared range admits; the shipped `crf_definition` and `llcr_definition` divide by rates with the same zero lower bound, so this adds no new class of failure. | Standard annuity formula (`sources/INDEX.md` row `crf_annuity`, `n/a`) | The undiscounted sum (`... * ppa_duration`) — consistent, 77,158,023,065.49, rejected: it pays twenty years of revenue as a lump sum today, which no make-whole clause does and which overstates the liability 2.4×. The net book value (`regulatory_asset_base * 1000000`) — consistent, 4,800,000,000, rejected: that is the *asset's* remaining value, not the *contract's*; a PPA termination payment compensates the forgone revenue, and the two numbers differ by 6.6× here. **`unclassified.md` calls this QUALITATIVE** ("the termination payment schedule. A contractual term") — this pack disagrees because the *schedule* is the term and the *payment* is its present value, and the graph carries every operand of the latter. |
| `auction_volume_per_round` | PRODUCT | derive | `MtCO2` (new node) | [0, 20000] — see the new-node table | derived / policy | `auction_volume_per_round = auction_volume / auction_frequency` | The allowances one auction round offers: the year's volume spread over the rounds the calendar holds. 25 / 12 = 2.0833 MtCO2 at defaults. | — (definitional: a volume divided by a frequency, i.e. a unit conversion) | `auction_volume_per_round = auction_volume` — **rejected on units**: `consistent=False` ("the two sides do not share a dimension"), MtCO2 against MtCO2/year. A product (`auction_volume * auction_frequency`) — rejected: it is the annual volume multiplied by the rounds, which is the volume counted twelve times. |
| `auction_frequency` | PRODUCT | **read** | `1/year` (retyped from `None`) | [0.5, 365] — twice a year to daily | free / fixed | `auction_volume_per_round = auction_volume / auction_frequency` (read) | Rounds per calendar year the allowance auction runs. 12 at defaults, i.e. monthly. | — (read as an operand; the conversion is definitional) | Making it an lhs (`= auction_volume / auction_volume_per_round`) — rejected: the frequency is the auction calendar's design choice, and deriving it would let a volume decision set the schedule. |

### THRESHOLD (1 row)

| node | class | kind | unit | range | role / determinism | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `gate_closure` | THRESHOLD | bound | `hours` (retyped from `None`) | [0.05, 24] — one settlement period's floor to one day; default 1.0 | free / fixed | `gate_closure >= settlement_period` (`geq`) | The market must close no later than one settlement period before delivery, or a trade can settle inside the interval it was cleared for. 1.0 hour against the 0.5-hour settlement period at defaults. Routes `bound`: both sides are declared, so this is a linopy constraint rather than a post-solve audit. | — (definitional ordering: a gate is by construction at least one settlement interval) | The equality (`gate_closure = settlement_period`) — consistent, rejected: gate closure is a policy dial the operator sets, and an equality would make every operator run the same gate. The shipped placeholder default of 500,000 hours — rejected as vacuous and meaningless: it is eleven years of gate closure, and the bound holds trivially. **Prerequisite:** the `hours` retype ships with the bound; without it the range [0, 1e6] makes the bound unfalsifiable. |

## Verification

Run against `config/prg.yaml` as it stands, with the 16 retypes and the new node
applied in memory and the 7 equations added:

```
BASE   1344 nodes  525 equations  1075 edges  284 uncoupled
AFTER  1345 nodes  532 equations  1075 edges  277 uncoupled
```

Seven slice nodes leave `uncoupled()`: `auction_frequency`,
`cost_pass_through_mechanism`, `counterparty_risk`, `gate_closure`,
`ppa_termination_payments`, `security_package`, `tax_incentives`. **56 slice
nodes remain uncoupled.**

- Symbol check: **7 of 7 right-hand sides resolve**, zero missing symbols.
- `lhs in parse_side(rhs).symbols`: **False for all 7** — no target appears on
  its own right-hand side.
- `check_equation`: **7/7 decidable, 7/7 consistent**.
- `propagate` at defaults: `range_excursions() == {}`, `detect_conflicts`
  blocking conflicts `[]`, `check_graph` undecidable **0**.
- `constraints._classify`: **6 route `unbound`** (post-solve audit — each has a
  derived symbol on one side), **1 routes `bound`** (`gate_closure_bound`).
- `solve_paths`: all six derived targets are **`affine`**.

The derived values at the propagated defaults, as printed:

```
security_package            = 600000000.0            (range [0, 1.1e13])
counterparty_risk           = 0.01                   (range [0, 1])
cost_pass_through_mechanism = 0.8                    (range [0, 1])
tax_incentives              = 128771999.99999996     (range [-3e12, 3e12])
ppa_termination_payments    = 31829702743.093998     (range [0, 1.5e14])
auction_volume_per_round    = 2.083333333333333      (range [0, 20000])
gate_closure                = 1.0                    (range [0.05, 24])
```

The operands, as printed:

```
performance_bond_usd                 = 600000000.0
parent_company_guarantee_usd         = 0.0
settlement_risk                      = 0.01
wholesale_cost_pass_through          = 0.8
taxed_fraction_of_concession         = 0.8
corporate_income_tax_rate            = 0.3
cfads_usd_per_kw_year                = 214.62
total_capacity_mw                    = 10000.0
ppa_annual_revenue_usd_per_kw_year   = 385.7901153274384
discount_rate                        = 0.10464400000000001
ppa_duration                         = 20.0
auction_volume                       = 25.0
auction_frequency                    = 12.0
settlement_period                    = 0.5
```

The bound holds: **1.0 ≥ 0.5**. The canary for it is the retype itself — at the
shipped placeholder default of 500,000 hours the inequality is true for the
wrong reason, and the range [0, 1e6] admits values that make it true
vacuously. A bound whose range is a superset of the quantity it bounds
constrains nothing; the [0.05, 24] range is what gives it teeth.

Every value sits strictly inside its declared range. The two that sit closest to
a bound are `tax_incentives` (0.0043% of the way up a ±3e12 band) and
`ppa_termination_payments` (0.021% of its ceiling), which is the expected
behaviour of a band drawn from the operands' own extremes rather than from the
reference case.

## Dependencies

Six deferrals wait on a base no pack proposes. They are not this pack's to add:

- `curtailed_twh` (`TWh/year`) — the base `ppa_curtailment_compensation` needs.
  The graph carries no curtailment volume anywhere; `renewable_penetration_limit`
  is a ceiling on a share and cannot stand in for a volume.
- A frontier or peer-group efficiency level (`1`) — the base
  `efficiency_benchmarking` needs to normalise against.
- A retail market-share vector, or a switching rate (`1/year`) — the base
  `retail_competition` and `number_of_retailers` both need. A count alone
  cannot give a concentration index.
- A market-entry flow (`count/year`) — the base `new_entrants` needs.
  `number_of_generators` is a stock.
- `reserve_account_share` (`1`) — recorded by `supply-emissions-grid.md`.
- `max_remedy_period_days` (`days`) — recorded by
  `threshold-product-remainder.md`.

One proposal depends on work outside this pack: **the `hours` retype of
`gate_closure` is a prerequisite for its bound**, not a side-effect. If the
retype does not bake, the bound is vacuous and should not ship.

## Rejected

Approaches considered for the slice as a whole and not taken.

- **An equation for every node with a plausible-looking base.** Thirty-four
  QUALITATIVE nodes and fourteen scene switches have no base, and a collections
  policy times a revenue is a number with no meaning. The class exists so that
  this is recorded rather than manufactured.
- **Multiplying a boolean.** `ancillary_services_market`,
  `contract_for_difference`, `virtual_bidding`, `financial_transmission_rights`,
  `strategic_bidding` and `collusion` are all flags. A product by a flag is a
  branch with a derivative of zero on one side, and the solver reads a
  discontinuity it cannot differentiate through. They stay scene switches.
- **Deriving `market_structure` or `market_model`.** Both are already
  categoricals the solver branches on; there is no quantity to derive. The
  shipped cross-validation rules that read them are the correct coupling and
  already exist.
- **Retyping `cross_border_trading`.** A deprecated node must not be touched.
  The shipped declaration is already correct (`1`, [0, 1], 1.0) and the correct
  coupling is its removal once no scenario names it.
- **A product for `efficiency_benchmarking`, `retail_competition`,
  `number_of_retailers`, `new_entrants` or `ppa_curtailment_compensation`.**
  Each needs a base the graph does not carry; inventing one would be the
  "operand nothing supplies" failure the register exists to stop.
- **Citing Stoft (2002) on any of the seven.** Thirteen shipped equations cite
  it and no archived copy exists. A citation whose work is not on disk is a link
  that will rot, so the market-design rows here carry definitional references
  instead and the work is listed below.

## Sources to fetch

Cited in prose above or by shipped equations in this slice's family, but not
held locally. No equation in this pack leans on them until a copy is archived
and a row added to `sources/INDEX.md`:

- **Stoft, S. (2002), *Power System Economics: Designing Markets for
  Electricity*, Wiley/IEEE Press.** `sources/INDEX.md` carries the `stoft_2002`
  row with an empty `archived` cell (paywall textbook), and **13 shipped
  equations cite it**: `capacity_revenue_usd_per_year_definition`,
  `carbon_revenue_share_of_revenue_definition`, `demand_charge_revenue_definition`,
  `largest_loss_response_bound`, `market_concentration_definition`,
  `non_spinning_reserve_inside_margin`, `operating_reserve_margin_alias`,
  `price_band_lower_definition`, `price_band_upper_definition`,
  `regulation_down_definition`, `regulation_reserve_definition`,
  `regulation_up_definition`, `reserve_margin_required_mw_definition`. This is
  the largest citation gap in the graph and it belongs to this slice's subject
  matter. Either a licensed copy is archived or the 13 citations need an
  archived replacement that states the same identities.
- **A benchmarking-method source (DEA or SFA, e.g. Coelli et al., *An
  Introduction to Efficiency and Productivity Analysis*)** — needed only if
  `efficiency_benchmarking` is ever coupled. The catalog's method cell names
  DEA/SFA and no archived work states either estimator.
- **An ETS auction-calendar source (e.g. the EU ETS Auctioning Regulation,
  Commission Regulation (EU) No 1031/2010)** — the basis for
  `auction_frequency`'s 12/year default and the per-round volume. The default is
  a convention the graph does not currently document; it is defensible as a
  calendar choice but a reviewer may want the rule.
