# 16. Making ALEA a causal model

2026-11-25. Builds on `docs/plans/15-completion.md` (T1 and T2 are done) and `docs/research/alea-causal-model/README.md` (classification of the 841 equations). The concepts are in `docs/dependency-graph-vs-causal-model.md`.

This is a plan, so it is exempt from the humanizer pass. Every task has a probe, a gate, and a canary.

## 0. What "causal model" will mean here

A structural causal model is a set of mechanisms, one per endogenous variable, each of which keeps holding when other mechanisms are replaced, plus a distribution over what the mechanisms leave out. ALEA cannot honestly claim all of that for 841 equations at once, and most of them are accounting. So the target is graded, per equation and per query, not a label on the whole project.

| Level | Name | What it licenses | Where ALEA is |
|---|---|---|---|
| L0 | Dependency graph | "These quantities are computed from those" | Reached |
| L1 | Structural model | Every equation typed by what it claims; `do` returns the mechanisms it crossed; identification stated as an assumption | Partly: `intervene` exists, no typing |
| L2 | Calibrated causal model | The behavioural and empirical edges on the paths policy questions use are estimated from data, with an identification design and an interval, and survive an out-of-sample intervention check | None |
| L3 | Counterfactual model | Per-case questions, with a noise term per estimated mechanism | None, and not planned before L2 holds |

**Non-negotiable:** the README keeps "dependency graph" until L1 gates pass and a reviewer who is not the author agrees. "Causal model" is then allowed only with a scope sentence ("L1 for all equations; L2 for the edges listed in the register"). A project-wide claim of L2 is not allowed while any edge on a path used by a published answer is unevidenced.

**Scope decision, stated so it can be challenged:** causal content is concentrated in a small part of the graph. The earlier audit found two feedback loops (five equations) and a handful of behavioural edges among 841. Most of the work below is therefore labelling and gating the 588 arithmetic equations (cheap per equation, large in number) and evidencing the few edges that carry behaviour (expensive per edge, few in number).

## 1. Defects this plan closes

| ID | Gap | Measured | Closed by |
|---|---|---|---|
| C1 | No equation says what it claims | 0 of 841 have a `claim`; 44 functional forms and a 40-equation sample hand-labelled | P2 |
| C2 | A cut equation may determine more than one variable, aliases may be pinned by either name, a pin may break an inequality | Not handled in `intervene` | P1 |
| C3 | An intervention result does not say whether it reached the optimiser | 9 of 1,095 settable parameters reach it | P1, P7 |
| C4 | No evidence record on any behavioural edge | 301 of 841 equations have no `reference`; the references that exist are citations, not estimands | P5 |
| C5 | Direction of causation is read from `determined_variables` and never audited | An inverted shipped equation was found earlier | P3 |
| C6 | Loops are solved, not characterised | Existence and uniqueness of the fixed points unstated | P3 |
| C7 | Uncertainty covers parameters, not mechanisms | Ranges only | P4 |
| C8 | No test against a real intervention | None | P6 |
| C9 | Query answers carry no statement of how far to trust them | None | P8 |
| C10 | No causal claim has been reviewed by anyone but the author | None | P9 |

## 2. Phases

### P1. Finish interventional semantics (T2a)

The operator exists. These cases are not covered.

1. **Equations that determine more than one variable.** Cutting such an equation removes the source of every variable it determines. Rule: refuse a pin on a name whose equation determines others, and name them, unless the caller pins all of them in one `do`. Probe: list equations with `len(determined_variables) > 1`; each gets a test.
2. **Aliases (95 of them).** Pinning `a` where `a = b` should pin the canonical name and report the alias. Decide the canonical side from the generator, not from alphabetical order. Test: pin by either spelling gives the same result and the same `cut`.
3. **Inequalities (74).** After a pin, report every inequality the pinned world violates. Return them in the result, do not refuse: an intervention that breaks a constraint is an informative answer.
4. **`reaches_solver`.** For each pinned name and each changed descendant, say whether `translated(name)` or a constraint term reaches the optimiser. Reuse `translate.TRANSLATIONS` and `constraints.optimiser_parameter_names`. A result where nothing changed reaches the plan carries the text "moved in the graph, not in the plan".
5. **Non-descendant invariance.** Property test: for every derived node `n` pinned, every node that is not a descendant of `n` is bit-identical to the unpinned run. Use a fixed table of 30 nodes, chosen to include both loops, an alias, a multi-determined equation, and a leaf.

Gate: the five tests pass, and a canary that lets `intervene` also mutate one non-descendant fails the invariance test.

### P2. Type every equation by what it claims (T2b)

1. Add `claim: Claim = Claim.UNREVIEWED` to `Equation` in `src/alea/prg/views.py`. Enum: `definition`, `identity`, `physical`, `empirical`, `behavioural`, `assumption`, `unreviewed`. Also `direction_source: str | None` for behavioural and empirical ones (why the arrow points this way, a sentence, not a citation).
2. Add `manipulable: bool | None` to `ParameterNode`: can an actor set this quantity independently of the others? Policy levers true, outcomes false. This matters because `do` on an outcome is a thought experiment, and the result should say so.
3. Seed `claim` from `docs/research/alea-causal-model/equation-classes.csv` through the **generator or fragments**, not by editing `config/prg.yaml`. Regenerate. Check first which side owns equation fields; the generator owns catalog-sourced node fields and a fragment merge replaces rather than deep-merges.
4. Consistency gate, run in CI: a `definition` or `identity` equation has no elasticity, rate-of-response, or random parameter among its inputs; a `physical` equation has a `reference`; a `behavioural` equation has a `direction_source`. Each rule needs a canary that plants a violation.
5. Count gate: the number of `unreviewed` equations is pinned in a test and may only fall. This is the register that makes progress visible and stops regression.

### P3. Audit structure, direction and loops

1. **Direction audit (C5).** Every equation has exactly one determined variable or is an inequality. Add the test. For each `behavioural` or `empirical` equation, a reviewer who is not the author confirms the direction in a ledger row (`docs/research/alea-causal-model/direction-ledger.csv`: equation id, reviewer, date, decision). The earlier inverted equation shows this has found real errors.
2. **Missing mechanisms register.** A causal graph is wrong by omission as often as by commission. Keep `missing-mechanisms.md`: arrows a domain expert says should exist and do not (for example a tariff response in investment, or price feedback on demand growth beyond `loop_2`). Each entry is a decision: add, or state why not. A policy answer that crosses a node with a registered missing parent carries a flag.
3. **Loops (C6).** For `loop_1` (capture price, VRE build, VRE share) and `loop_2` (equilibrium demand, regulated tariff): state whether each is an equilibrium condition or a dynamic process. If an equilibrium, give the existence and uniqueness conditions on the parameters (for a fixed point, a contraction condition on the loop map) and test that the solver's termination agrees with them across the parameter range, including the corners where it should fail. If a dynamic process, unroll it over time indices and say what the time step is. State which reading the equations support, from the equations, not from the loop's name.
4. Confounding: with every mechanism written down and every exogenous input independent, identification inside the model is by construction, and the assumption is "no omitted common cause". P3.2 is where that assumption is audited. Write the sentence into every `do` result's provenance.

### P4. Uncertainty on mechanisms and a noise layer (C7)

1. **Interventional distributions.** Promote default values to distributions where ranges exist, sample, and report `P(Y | do(X = x))` as an interval, not a point. Use the existing ranges as the support; do not invent shapes. Where a range has no stated distribution, use uniform and say so in the output.
2. **Structural uncertainty.** For each behavioural or empirical node, allow a named set of alternative mechanisms (for example linear and constant-elasticity demand). `do` reports the spread across them. This is the cheapest honest answer to "is the functional form right?".
3. **Sensitivity.** Add a variance decomposition (Sobol indices or a cheaper screening method) restricted to the intervention's descendants. Gate: indices sum to near 1 on a known additive test function.
4. **Noise terms for L3.** Only for equations that P5 has estimated, store the residual spread and the assumed form (additive, so a residual can be recovered by inversion). Counterfactuals are available only for these. Do not give every equation a noise term; an unestimated one would be invented.

### P5. Evidence for the behavioural and empirical edges (C4)

Do this for the edges on paths that published questions travel, in this order: `loop_2` (demand and tariff), `loop_1` (capture price and VRE), learning curves, degradation, then climate sensitivity. About 10 edges (the earlier audit's 9 empirical, 1 behavioural, plus the loop equations).

1. **Evidence record per edge**, stored with the equation: estimand (what quantity, for whom, under what change), design (instrument, difference in differences, regression discontinuity, structural estimate, or "literature value, not identified here"), data and years, estimate, interval, date, and the identification assumption in one sentence. Fields in `views.py`; content in the generator or fragments.
2. **Honest grades.** `literature_value` (copied from a paper whose setting may differ), `estimated_here` (fit on data in this repo), `identified_here` (with a design that argues the estimate is causal). Most will start as the first.
3. **Kenya first.** Single-country-first still holds. Use demand, tariff and generation series already ingested; a source not yet archived is archived before it is cited (`docs/sources/` with an INDEX row).
4. **Gate.** An equation may carry `claim: empirical` or `behavioural` at level L2 only with an evidence record at `identified_here`. Canary: delete the record from one edge and the gate must fail.

### P6. Validate against real interventions (T10, C8)

The identity test shows internal consistency. It does not show the model is right. Three checks, in rising strength:

1. **Placebo.** Intervene on a node that should not affect an outcome (a downstream quantity, or a node with no path to it) and require no change. Cheap, and it catches graph errors.
2. **Invariance across settings.** A mechanism that is truly autonomous should hold in more than one setting. Fit an edge in Kenya and test it in a second country's data when one exists; a failure means the edge is not autonomous, which is a finding about the model and not a defect in the test. Keep the single-country-first rule: this check waits until Kenya is complete.
3. **Out-of-sample intervention.** Choose past interventions from data the repo actually holds (a tariff change, a plant outage, a fuel price move), pre-register the prediction before fitting on the post period, run `do`, compare to what happened. Report sign agreement, interval coverage, and mean absolute error relative to a no-model baseline. The event list is chosen from available data; do not name events here that have not been checked.

Gate: at least one behavioural edge passes check 3 with the prediction file committed before the data it is scored on, or the edge is downgraded to `assumption` in the register. A model that cannot be scored does not get to keep `empirical`.

### P7. Couple to the optimiser where causal questions live (extends T4)

1. Reach is measured, today, over all 1,095 settable parameters (9 reach the optimiser). Re-measure it over **policy levers** (`manipulable: true`) and over the nodes on the P5 edges. That is the number that matters for causal answers, and it may be smaller or larger than 0.8 percent. Report it with the denominator.
2. For levers that do not reach the plan, add a translation or a constraint route, in order of how many published questions use them, or record why not.
3. **Interventions on the plan itself.** "What if we build 1 GW of solar here" is a constraint on a decision variable, not a parameter. Add `do` on decision variables as a fixed-capacity constraint (`p_nom` pinned), and report objective, emissions and cost deltas against the free solve. State that the optimiser's answer is an argmin of a stated objective, so the effect of a pin is the effect conditional on everyone else re-optimising.
4. Gate: for each lever claimed to reach the optimiser, a test that moves it and checks the objective moved in the stated direction, and a test that a lever claimed not to reach it leaves the objective bit-identical.

### P8. Surface it: provenance on every answer (C9)

1. Every `do` result (CLI, API, UI) returns: the pinned names, the equations cut, the mechanisms crossed grouped by `claim`, the evidence grade of each crossed empirical or behavioural edge, any missing-mechanism flag, `reaches_solver`, the interval (P4), and the one-line identification assumption.
2. **A grade per answer**, derived and never typed: `A` if every crossed mechanism is `definition`, `identity`, `physical`, or evidenced `identified_here`; `B` if it crosses a `literature_value` or `assumption`; `C` if it crosses an `unreviewed` equation or a flagged missing parent. Reports print the grade next to the number. A report that omits the grade fails a docs-qa style check.
3. UI: show the path and the grade in the adjust panel; dim the answer on grade C.
4. Docs: replace the paragraph in `docs/how_prg_works.md` that says what `intervene` identifies with the P8 fields.

### P9. External review and falsification (C10)

1. A reviewer who is not the author reads the `claim` assignments for the behavioural and empirical equations, the direction ledger, and the missing-mechanisms register, and either signs each row or changes it. Their changes are recorded, not smoothed.
2. Publish the falsification conditions (section 6) and a date to re-test them.
3. Only after P2 gates pass and this review is signed may the README change "dependency graph". Wording is a scope sentence, per section 0.

## 3. Order of work and gates

| Step | Phases | Gate before moving on |
|---|---|---|
| 1 | P1 | five tests green; invariance canary fails when it should |
| 2 | P2 | claim gates green with a canary per rule; `unreviewed` count pinned |
| 3 | P3 | direction test green; loop conditions tested at the corners; missing-mechanism register exists and is read by `do` |
| 4 | P7.1 | policy-lever reach measured and published |
| 5 | P5 on `loop_2`, then `loop_1` | evidence record gate with canary |
| 6 | P6.1 and P6.3 on one edge | pre-registered prediction scored |
| 7 | P4 | interval and structural spread in results; Sobol check on a test function |
| 8 | P8 | grade shown on every surface; check that omitting it fails |
| 9 | P9 | reviewer sign-off |

P1 and P2 are mechanical and can be done in one session each. P5 and P6 need data and are the long pole; they should start once P2 is in, because P5 needs the typed equations to know which edges to evidence. P7.1 is cheap and informs where P5 starts. L3 (the noise layer in P4.4) waits for P5.

## 4. Before and after

Fill in at each gate. Counts as of 2026-11-25.

| Quantity | Command or source | Before | Target |
|---|---|---|---|
| Equations with a `claim` | `alea prg summary` after P2 | 0 of 841 | all 841 assigned; `unreviewed` falling to the 588 arithmetic minus those reviewed |
| Equations without a `reference` | `alea prg citations` | 301 | each behavioural and empirical one has a reference or an evidence record |
| Behavioural or empirical edges at `identified_here` | evidence register | 0 | the P5 list |
| Settable parameters reaching the optimiser | `measure_prg_engine_coupling.py` | 9 of 1,095 | reported over policy levers, with the denominator |
| Intervention checks scored out of sample | P6 | 0 | at least 1, pre-registered |
| Answers carrying a grade | P8 | 0% | 100% on every surface |
| Loops with existence and uniqueness stated | P3.3 | 0 of 2 | 2 of 2 |

## 5. Risks

- **Labelling drift.** A `claim` is a judgement. Two reviewers will disagree on the boundary between `assumption` and `behavioural`. The ledger records both; do not force agreement.
- **Evidence that looks like proof.** A `literature_value` can be cited from a setting that does not match. The grade, not the citation, is what carries. Never promote a grade because a paper exists.
- **Goodhart on the gates.** A gate that counts `claim != unreviewed` can be satisfied by mass-assigning `definition`. The consistency rules in P2.4 and the reviewer sample in P9 are the counter, and the sample must be drawn by someone other than the labeller.
- **Scope creep into the optimiser.** The optimiser is not a mechanism to be validated here. P7.3 treats it as an argmin of a stated objective, and says so.
- **Time.** P5 and P6 depend on data access and on how many past interventions the repo's data covers. If none qualifies, P6.3 is blocked and the edges stay at `assumption` or `literature_value`. That is a legitimate end state and should be reported as such.

## 6. What would show this plan is wrong

- If a hand audit of all 588 arithmetic equations finds many more behavioural mechanisms than the 1 in 40 sampled, the work is larger than P5 allows and the "handful" claim in the scope decision fails.
- If the optimiser carries most of the behavioural response (price-responsive demand inside PyPSA), then the graph's causal content matters less, and P7 becomes the main phase.
- If no pre-registered prediction can be scored on the data in hand, L2 is not reachable for this repo, and the honest top level is L1.
- If the reviewer in P9 reassigns a large share of `behavioural` equations to `assumption`, the graph's causal content is smaller than this plan supposes. Report that and move the README claim the other way.

## 7. Mapping to earlier task numbers

| Earlier | Here |
|---|---|
| T2a | P1 |
| T2b | P2 |
| T9 | P2 (seeding) and P3.1 (direction review), then ongoing |
| T10 | P6 |
| T4 (reach) | P7 |
