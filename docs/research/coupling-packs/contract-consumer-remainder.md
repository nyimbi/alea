# Coupling pack: the contract and consumer-protection remainder

## What this pack covers

The 31 nodes I was given: 23 contract clauses, 8 consumer-protection
mechanisms. Verified against the tree as it stands: `load_graph()` returns
**1352 parameters, 552 equations and 240 uncoupled**, and all 31 slice ids are
in `uncoupled()`.

> **Re-verified 2026-10-24, at batch 58.** The counts above were read at 1352 /
> 552 / 240; the graph is now **1429 / 607 / 235**, and every figure in this
> document that cites the old ones is a record of the tree it was written
> against, not a claim about today's. The *verdicts* were re-checked and hold:
> all 31 slice ids are still in `uncoupled()`, and **none of the 31 is read by
> any equation** — measured, not carried forward. That is what makes "this pack
> closes nothing" true, and it is true at the current tree as it was at the old
> one.

The classification is: **29 QUALITATIVE, 1 BASE-NEEDED, 1 THRESHOLD**. Of the
31, **one gets a proposal** — 0 `derive`, 0 `read`, 1 `bound`. **30 are
deferred**, and the reason for each is in its row.

**The premise this pack was commissioned on is false, and that is its headline
finding.** The brief says these 31 are "named by no existing pack". They are
named by `contract-market.md`, **31 of 31**, with a verdict this pack agrees
with on every one. `unclassified.md` names 14 of them and
`threshold-product-remainder.md` names `remedy_periods`; all three agree with
each other. Checked rather than assumed:

```
contract-market.md:            31/31
unclassified.md:               14/31
threshold-product-remainder.md: 1/31
```

So this is not a pack that closes a gap. It is a **confirmation pass with one
addition**: the slice is finished work, and the one node the siblings left open
(`remedy_periods`) is closed here because this pack supplies the base
`threshold-product-remainder.md` said it was waiting for, and canaries the bound
in both directions.

### The second finding: the consumer-protection bases exist, and nothing reads them

The task asked me to check whether the graph ships `vulnerable_population`,
`electricity_subsidy_spend_usd_per_year`, `cross_subsidy_usd_per_year`,
`smart_metered_population`, and the arrears/collection/bad-debt family. It ships
the first four, all **derived**, and they have **zero equation readers**. The
second family is absent outright.

```
vulnerable_population                          derived   readers=[]
smart_metered_population                       derived   readers=[]
vulnerable_customer_protection_spend_usd_per_year derived readers=[]
cross_subsidy_usd_per_year                     derived   readers=[]
electricity_subsidy_spend_usd_per_year         derived   readers=[]
force_majeure_cover_usd_per_year               derived   readers=[]
payment_security_required                      derived   readers=[]
arrears_rate, collection_rate, bad_debt        absent
curtailed_twh, curtailment_share               absent
max_remedy_period_days                         absent
take_or_pay_volume_mwh, minimum_offtake_mwh    absent
```

This **does not make the mechanisms closable**, and it is worth being precise
about why. `bill_shock_protection`, `disconnection_protection` and
`compensation_mechanisms` are *rules* — a notice period, a disconnection
safeguard, a compensation schedule. A rule is not a rate, and multiplying a
procedure by a spend base yields a number with no referent. The bases being
present removes the siblings' stated reason for deferring them ("no base in the
graph it could multiply") but not the actual one: the node is not a quantity.
The siblings' **verdict** is right and their **reason** is wrong on these three,
and the reason is what a later batch would reuse.

### What this pack found that the siblings did not

Three things, all measured:

1. **`ppa_curtailment_compensation` cannot be closed by any shipped volume.**
   `unclassified.md` and `contract-market.md` both say "needs a curtailed
   volume and a compensation rate". The sharper statement is that the graph
   **cannot derive one**: `vre_capacity_mw × capacity_factor × 8760` gives
   8.286 TWh of VRE potential against 30.933 TWh of
   `renewable_generation_twh`, so the difference is negative — the renewable
   total includes hydro and biomass, and the graph carries no VRE-only energy
   series. A curtailment volume is not merely absent, it is not recoverable
   from what is there.

2. **`renewable_curtailment_limit`, the node a careless reader would use as the
   volume, is itself an untyped placeholder** (`unit=None`, `[0, 1e6]`,
   `500000.0`) and is a *ceiling*, not a volume. Using it as the base would put
   a ceiling in the multiplicand position.

3. **`ppa_indexed_price_usd_per_mwh` is derived and read by nothing.**
   `ppa_indexed_price_definition` applies `tariff_indexation` over
   `ppa_duration`, and no equation and no rule consumes the result. The PPA's
   indexation therefore never reaches a revenue line:
   `total_revenue_usd_per_year` uses the base-year `ppa_price_usd_per_mwh`. I am
   **not** claiming this is a 2.65× revenue error — the indexed figure is the
   horizon price, not an annual average, and which of the two a revenue line
   should use is a convention question. The defect is the narrower, checkable
   one: a derived node with no consumer.

## Rows

`kind` uses the vocabulary the sibling packs established: `derive`, `read`,
`bound` (the node is the left operand of an inequality; its role stays `free`
and the equation computes no value for it), `defer`.

### The one proposal

| node | class | kind | unit | range | role / det | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `remedy_periods` | THRESHOLD | bound | `days` (already typed) | [1, 365] — unchanged | free / policy | `remedy_periods <= max_remedy_period_days` (`leq`) | The cure window a contract offers must not exceed the ceiling its licence sets, or the licence's own limit is breached by the contract it authorises. 60 days under a 90-day ceiling at defaults. Routes **`bound`** — both sides are settable scalars, so this reaches the optimiser as a linopy constraint rather than a post-solve audit. | `reference: None` — **definitional ordering**: a ceiling cannot sit below the value it ceilings. No archived work states a cure-period figure; see **Sources to fetch**. | `remedy_periods <= 365` — rejected as a **tautology**, the same argument `threshold-product-remainder.md` made: the declared range is already [1, 365], so the bound restates the range and can never fail. An equality (`remedy_periods = max_remedy_period_days`) — **refused by the loader** for the opposite reason: `GraphError: relation 'leq' cannot determine ['remedy_periods']; an inequality bounds a value, and only an equality fixes one` — a cure window is a negotiated term, not a computed one. |

**Why this is not a duplicate of the sibling row.**
`threshold-product-remainder.md` deferred `remedy_periods` pending
`max_remedy_period_days`, and `contract-market.md` cited that deferral. This
pack does what neither did: declares the base, loads it, measures the route,
and canaries the bound in both directions. The canary is the part that matters —
`60 ≤ 90` passes, `120 ≤ 90` fails, `90 ≤ 90` passes, `1 ≤ 365` passes. A bound
that has never been seen to fail is not a bound.

### The 29 QUALITATIVE rows

One reason covers the class, stated once: **a contract clause with no numeric
content has no correct coupling, and its `unit=None, [0, 1e6], 500000.0`
declaration is a catalog import that never got a type, not a quantity waiting
for an equation.** The class exists so this is recorded rather than
manufactured. Each row below names its own clause, so the table is not 29
copies of one sentence.

| node | class | kind | what it is | rejected |
|---|---|---|---|---|
| `assignment_rights` | QUALITATIVE | defer | A transferability clause. | An alias onto any share — rejected: the admissible set is a drafting choice, not a level. |
| `change_of_control` | QUALITATIVE | defer | The clause defining what triggers a change-of-control event. | Multiplying by `total_capacity_mw` — rejected: the clause is a trigger definition, and the capacity it would multiply is unrelated to it. |
| `concession_terms` | QUALITATIVE | defer | The concession's term sheet. | Aliasing `concession_duration` — rejected: the duration is one term *of* the sheet; the sheet is the document. `concession_duration` is already read by two shipped equations. |
| `cross_default` | QUALITATIVE | defer | The clause making one facility's default a default of all. | Any product — rejected: no base, and a cross-default is a linkage between obligations, not a magnitude. |
| `default_events` | QUALITATIVE | defer | The enumerated events of default. | Any product — rejected: an enumerated list. |
| `direct_agreement` | QUALITATIVE | defer | A tripartite lender/project/offtaker agreement. | Any product — rejected: a legal instrument, not a quantity. |
| `distribution_conditions` | QUALITATIVE | defer | The conditions a distribution licence attaches. | Any product — rejected: a rule set. |
| `environmental_representations` | QUALITATIVE | defer | Representations and warranties on environmental matters. | Any product — rejected: a legal term. |
| `licence_conditions` | QUALITATIVE | defer | The licence's conditions. | Aliasing `licence_fee_spend_usd_per_year` — rejected: the fee spend is derived and unread, and the conditions are the obligations the licence imposes, not the fee it charges. |
| `material_adverse_change` | QUALITATIVE | defer | A MAC clause. | Any product — rejected: the *threshold* would be a quantity and the graph carries no MAC threshold node; the clause itself is a legal term. |
| `novation_terms` | QUALITATIVE | defer | The conditions under which a contract may be novated. | Any product — rejected: a legal term. |
| `refinancing_terms` | QUALITATIVE | defer | The conditions under which the debt may be refinanced. | Aliasing `debt_tenor` — rejected: the tenor is a term of the loan; refinancing conditions are the permissions around it. |
| `social_representations` | QUALITATIVE | defer | Representations and warranties on social/labour matters. | Any product — rejected: a legal term. |
| `step_in_rights` | QUALITATIVE | defer | A lender's right to step into the project. | Bounding against `remedy_periods` — rejected: the right is the entitlement and `remedy_periods` is the timing that conditions it; a bound between a right and a duration is undecidable. `remedy_periods` is closed on its own row. |
| `ppa_arbitration_venue` | QUALITATIVE | defer | A seat of arbitration (a city or institution). | Any product — rejected: a legal choice, and `arbitration_seat` does not exist as a node. |
| `ppa_change_in_law` | QUALITATIVE | defer | A change-in-law clause's scope. | Any product — rejected: a legal term. |
| `ppa_dispute_resolution` | QUALITATIVE | defer | The PPA's dispute ladder. | Any product — rejected: a procedure. |
| `ppa_force_majeure` | QUALITATIVE | defer | The force-majeure clause's scope. | Aliasing `force_majeure_cover_usd_per_year` — rejected: the cover is the *indemnity* the clause produces; it is derived, has zero readers, and is a different object from the clause. |
| `ppa_governing_law` | QUALITATIVE | defer | A choice of law. | Any product — rejected: a legal term. |
| `ppa_pricing_formula` | QUALITATIVE | defer | Which indexation and escalation form the PPA uses. | Deriving it from `ppa_indexed_price_usd_per_mwh / ppa_price_usd_per_mwh` — rejected: that ratio is `(1 + tariff_indexation) ** ppa_duration`, a single number that identifies no formula, and `ppa_indexed_price_definition` already applies the rate. A gate on the formula choice — rejected as dishonest: a categorical branch is not a quantity, and the graph has no formula selector node. |
| `ppa_take_or_pay` | QUALITATIVE | defer | The take-or-pay clause's threshold. | `ppa_price_usd_per_mwh * generation_twh` — rejected: that is a revenue identity with no take-or-pay volume in it, and `take_or_pay_volume_mwh` / `minimum_offtake_mwh` do not exist. |
| `arrears_management` | QUALITATIVE | defer | A collections policy. | `arrears_rate * total_revenue_usd_per_year` — rejected: `arrears_rate` does not exist, and the node is a procedure. |
| `bill_shock_protection` | QUALITATIVE | defer | A consumer-protection rule: notice period, payment smoothing. | Aliasing `energy_burden` (0.0506) — rejected: the burden is the affordability ratio the rule responds to, not the rule. A product against `vulnerable_customer_protection_spend_usd_per_year` — rejected: that base is derived and unread, and a procedure times a spend is not a quantity. |
| `compensation_mechanisms` | QUALITATIVE | defer | The consumer-compensation rule set. | Aliasing `vulnerable_customer_protection_spend_usd_per_year` — rejected for the same reason: the spend exists but nothing reads it, and the mechanisms are the schedule that generates a spend, not the spend. **Diverges from the siblings' stated reason only**: they say "no base"; the base exists. |
| `debt_management` | QUALITATIVE | defer | A treasury policy. | Aliasing `debt_fraction` — rejected: the fraction is the capital structure the policy produces, not the policy. |
| `disconnection_protection` | QUALITATIVE | defer | A licence condition on disconnection. | `vulnerable_population / population_total` — rejected: that ratio is the vulnerable share (0.5), not a disconnection rule. The base exists and is unread; the node is still a rule. |
| `dispute_resolution_mechanism` | QUALITATIVE | defer | The escalation ladder (expert determination, arbitration, courts). | Any product — rejected: a procedure. |
| `payment_plans` | QUALITATIVE | defer | An instalment arrangement. | `payment_security_required / total_revenue_usd_per_year` — rejected: that ratio is `settlement_risk` (0.01), a restatement of a shipped quantity, and the node is a procedure. |
| `prepayment_metering` | QUALITATIVE | defer | A metering mode. | `smart_metered_population / population_total` — rejected: that is the metered share (0.45), a configuration's *consequence*, not the mode. |

### The 1 BASE-NEEDED row

| node | class | kind | unit | range | role / det | equation | prose | citation | rejected |
|---|---|---|---|---|---|---|---|---|---|
| `ppa_curtailment_compensation` | BASE-NEEDED | defer | `USD/MWh` (retype from `None`, prerequisite) | [0, 500] — the compensation-rate band the graph's other per-MWh rates occupy | free / policy | — | A rate per curtailed MWh, applied to a curtailed volume. The rate half is available; the volume half is not. **The graph cannot derive a curtailment volume**: VRE potential (`vre_capacity_mw × capacity_factor × 8760`) is 8.286 TWh against 30.933 TWh of `renewable_generation_twh`, so potential minus generation is negative and the renewable total is not VRE-only. A `curtailed_twh` node is required and no pack proposes one. | — (no equation, so no citation) | `ppa_curtailment_compensation * renewable_curtailment_limit * 1000000` — **rejected**: `renewable_curtailment_limit` is a *ceiling*, not a volume, and is itself an untyped placeholder. Retyped in memory to `TWh/year` the equation does pass `check_equation` (`decidable=True, consistent=True`, `[currency]/[time]` both sides) and returns 0.0 at defaults — but a unit-consistent equation over a placeholder ceiling is a correct formula reading a wrong node. The retype alone is not a fix. |

## New nodes this pack declares

One. It is the base `threshold-product-remainder.md` named as the blocker for
`remedy_periods` and did not add, because that pack's slice did not own it.

| node | unit | range | default | role / determinism | why |
|---|---|---|---|---|---|
| `max_remedy_period_days` | `days` | [1, 365] — the same band the cure window itself sits in, so the bound cannot be vacuous by construction of the range | 90.0 | free / policy | The ceiling a licence places on a cure window. Without it the only available right-hand side is the constant 365, which restates `remedy_periods`' own range. The 90-day default is a project-finance convention, not a measured figure — see **Sources to fetch**. |

## Verification

Run against `config/prg.yaml` as it stands, with the new node and the one bound
applied to a copy and loaded through `load_graph`:

```
BASE   1352 nodes  552 equations  240 uncoupled
AFTER  1353 nodes  553 equations  239 uncoupled
closed by this pack: ['remedy_periods']
```

- Symbol check: `max_remedy_period_days` resolves; **zero missing symbols**.
- `lhs` on its own right-hand side: **False**.
- Banned operators (`abs`, `min`, `max`, `floor`, `ceil`) in the rhs: **none**.
- `check_equation`: **`decidable=True, consistent=True`**, `[time]` vs `[time]`.
- `constraints._classify`: **`bound`** —
  `reason='every term is a declared network quantity or a settable scalar'`.
  This is a linopy constraint, not a post-solve audit.
- `propagate` at defaults: `range_excursions() == {}`;
  `detect_conflicts` → `no conflicts over 481 checked parameter(s)`;
  `check_graph` → **0 undecidable of 553 equations**.
- Derived node check: no node here is derived, so the "derived carries no
  default" constraint does not apply. Both nodes remain `free` with defaults
  (60.0 and 90.0), which is what a bound requires.

The values at defaults, as printed:

```
remedy_periods          = 60.0    (range [1, 365], default 60.0, role free)
max_remedy_period_days  = 90.0    (range [1, 365], default 90.0, role free)
```

**The canary, both directions** — the bound is only a gate if it can fail:

```
remedy=60  ceiling=90   -> consistent=True   (passes)
remedy=120 ceiling=90   -> consistent=False  (FAILS, 1 direct conflict)
remedy=90  ceiling=90   -> consistent=True   (passes at the boundary)
remedy=1   ceiling=365  -> consistent=True   (passes at the floor)
```

The 120/90 case is the known-positive that makes the other three evidence. The
90/90 case confirms the relation is `leq` and not a strict `<` — a tie is not a
violation.

## Sources to fetch

**No equation in this pack leans on a fetched source.** The one bound carries
`reference: None` on definitional grounds, stated in its row.

If a reviewer wants the cure-period convention cited rather than left as
practice, the work to fetch is a standard project-finance facility agreement or
its commentary — **Loan Market Association recommended form of facility
agreement, or a project-finance textbook stating the customary cure period**.
`sources/INDEX.md` has no row for either, and the archived World Bank handbook
does not mention cure, remedy or grace periods at all:

```
grep -ic "cure period|remedy period|grace period" world_bank_regulating_utilities_handbook.txt
0
```

The 90-day default and the [1, 365] band are therefore conventions this pack
adopts and says it adopts. They are defensible as practice; they are not
sourced, and a batch that ships them should not dress them in a citation.
