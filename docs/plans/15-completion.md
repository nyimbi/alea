# 15 - Defect register and completion plan

Measured 2026-11-25 against `main` at `974a559`. Every number below was printed by a command shown beside it. An agent executing this plan runs the command again before acting and quotes the value it gets, not the value here.

Rules for the executing agent (from the repo and the owner's standing instructions):

- Tabs in Python. Modern typing. Pydantic v2 models with `extra='forbid'`.
- TDD: a failing test first, then the fix, then `uv run pytest -x -q -k <name>`, then `uv run pyright src`. Full suite only at the checkpoints named here.
- Canary every new gate: plant a known-positive, watch it fail, restore from a backup taken in the same shell call, confirm the clean run. Never `git checkout -- <file>` to revert a canary.
- Commit and push after each completed unit with explicit paths (`git commit -- <paths>`). Never `git add -A`. Read `git diff --cached --stat` first. No AI attribution lines in any commit or doc.
- No em or en dashes. Run `python3 ~/.claude/scripts/docs_qa.py --root . --errors-only` on every doc touched.
- Cite sources by archiving a copy under `docs/research/` or `docs/sources/` and indexing it.

## 1. Defect register

Severity: **S1** returns a wrong answer or loses a user's input silently. **S2** a stated capability does not do what it states. **S3** hygiene.

### S1: wrong answers and silent input loss

**D1. A hand-set derived parameter is silently discarded.**
`graph.propagate({..., "additional_abatement_mtco2": 136.0})` returns 45.0 and raises nothing. Probe: build `vals = {n: g.node(n).default for n in g.nodes if n not in g.computed()}`, add the override, call `propagate`. The same entry points are `cli.py:487` (`prg propagate`), `cli.py:1857`, `api/routes/prg.py:658,725,757,815,983,1018,1046`, `prg/ui/server.py:136`, `prg/service.py:220,276`, `prg/sdk.py:274`, `prg/audit.py:420`. `is_settable()` exists and is False for the node, but `propagate` never consults it.
Cause: `propagate` (`prg/graph.py:1300`) coerces and range-checks every key in `values`, then overwrites each computed name with `_derive`. Nothing compares the supplied value of a computed name against the result.

**D2. An unknown parameter name is accepted and carried through.**
`propagate({..., "no_such_param_xyz": 1.0})` returns it in `values` unchanged. A typo in a scenario therefore does nothing and says nothing. `changed=` already refuses unknown names (graph.py:1316); `values=` does not.

**D3. The graph's own defaults fail its own check.**
`uv run alea prg check` exits non-zero at defaults: `frequency_nadir_hz = 43.6224`, declared range `(45.0, 50.0)`, rule `frequency_nadir_below_protection`. A baseline scenario is inconsistent before anyone edits it, so every "what moved" report starts from a violated state. `uv run alea prg conflicts` reports the same single `out_of_range`. Either a default input or the nadir equation is wrong; the proposal output suggests `largest_loss_mw` and `inertia_constant_s`. Find which by recomputing the equation by hand from its cited source (the loss-kernel unit error in memory is the precedent: a 333x error survived because nobody ran the physics check).

### S2: capability stated, not delivered

**D4. 7.4% of the settable surface reaches the solver.**
`uv run python scripts/measure_prg_engine_coupling.py`: 81 of 1,095 settable parameters (3 knobs, 78 constraint terms), 1,014 reach none, 7 of 10 engine fields are named by no PRG parameter (`battery_cost_multiplier`, `coal_eaf`, `drought_multiplier`, and four more; the script prints them). `planning/` imports nothing from `prg/`. The README and kernels now say this plainly; the fix is to make it smaller, in the order D4a to D4c.

**D5. The graph has no intervention semantics.**
This is the root of D1. Without it, "causal" cannot be claimed and a scenario author cannot ask "what if this derived quantity were X". See task T2.

**D6. The ten claims in the `[UNVERIFIED]` register are all still unverified.**
`uv run alea quality claims`: #1 to #3 (M2), #4 (M6), #5 (M8), #6 and #9 (M1), #7 (M3), #8 (M7), #10 (M5). A claim published while unverified is the highest-severity release risk in `14-roadmap.md` §6. Do not clear one by editing the register; clear it by producing the milestone artefact.

**D7. The Kenya model is not solved for a full year.**
Solves to optimality on windows up to 91 days (M1 clause open). The EnAccess email says so; it stays true until T6 lands.

### S3: hygiene

**D8. 16 pyright errors, 1 warning** (`uv run pyright src`):
- `api/routes/prg.py:725,985` and `cli.py:1859`: `dict[str, ParameterValue]` passed where `Mapping[str, float]` is declared on `detect_conflicts`. The annotation is too narrow; categoricals are legal values. Widen `detect_conflicts(values, supplied)` to `Mapping[str, ParameterValue]` and fix the body to skip non-numeric entries explicitly.
- `outages/viirs_h5.py:61,78,79,85`: h5py `Datatype` indexing. Narrow with `isinstance(obj, h5py.Dataset)` and fail loudly otherwise.
- `config/__init__.py:49`: `__all__ +=` is unsupported by the checker; build the list in one literal.

**D9. 4 ruff findings** (`uv run ruff check src tests scripts`): unused imports in `scripts/quality/kenya_m1.py:13`, `milestone_artefacts.py:25`, `viirs_ghana_validation.py:17`; `E741` ambiguous `l` at `scripts/download/viirs_vnp46_ghana.py:42`. Do not run `ruff --fix` on `__init__` or facade modules.

**D10. 138 "status drift" lines** in `uv run alea prg summary` (graph says `existing`, catalog says `to_build`). Unexamined. Decide which side is authoritative per the generator-ownership rule (the generator owns catalog-sourced node fields), then regenerate rather than hand-edit.

**D11. 43 of 108 citations have no local copy** (`uv run alea prg citations`: 39 archived, 43 unarchived works, 0 defects). Archive each under `docs/sources/` and add it to `docs/sources/INDEX.md`.

**D12. README carries older em dashes** (docs-qa `TY001` at lines 1, 7, 14, 46, 59 and more). Fix them; this is the owner's standing rule.

**D13. Three of the 4 cited unit-exempt equations** (`consumer_surplus_definition`, `gas_price_per_mwh_definition`, `llcr_definition`) skip the dimension check by declaration. Confirm each exemption has a written reason in the YAML; if the reason is "units not recorded", record them and remove the exemption.

## 2. Tasks

Order is dependency order. Do not start T4 before T1 to T3 land, because T4 builds on a graph that refuses bad input.

### T1. Refuse what the door cannot honour (fixes D1, D2)

Goal: `propagate` never silently drops or ignores an input.

1. Write failing tests in `tests/ci/prg/test_propagate_refuses.py` (create the directory if absent; mirror the style of the existing PRG tests):
   - an unknown key raises `GraphError` naming the key and suggesting the closest valid name (`difflib.get_close_matches`);
   - a supplied value for a computed name that differs from the derived result raises `GraphError` naming the parameter, the supplied value, the derived value, and the equation id;
   - a supplied value for a computed name that equals the derived result (within `1e-9` relative) is accepted. This is the case the "convenience paths pass every default" comment in `propagate` describes, and it must keep working;
   - an endogenous name supplied is refused with the existing endogenous message;
   - **vary one dimension per negative test** (name only, then value only), so each predicate has its own canary.
2. Implement in `ParameterGraph.propagate`, directly after `_refuse_out_of_range` (`graph.py` near line 1337): reject `set(scoped) - set(self._nodes)`. After the derivation passes, compare each caller-supplied computed name against `scoped[name]` using the same tolerance as `moved`. Raise one `GraphError` listing every offender, not the first.
3. Fix the callers that pass every default plus overrides. Run `rg -n "propagate\(" src` and confirm each call site either builds its mapping from non-computed defaults or tolerates the new refusal. `prg/service.py:220,276`, `api/routes/prg.py` and `prg/ui/server.py:136` must turn the `GraphError` into the existing 4xx or CLI exit-2 path, with the message verbatim.
4. Canary: comment out the new comparison by line number, run the new tests, confirm the "differs" test fails and the "equals" test passes, restore from a same-shell backup.
5. Update `docs/how_prg_works.md` and the README graph section: the sentence about a hand-set derived node is now a refusal. Re-run `scripts/measure_prg_engine_coupling.py` and quote its output.

Done when: the probe from D1 raises; `uv run alea prg propagate --set additional_abatement_mtco2=136` exits non-zero with the message; the UI shows the message instead of a number.

### T2. Intervention, the `do` operator (fixes D5)

Decision already made by T1: a bare override is refused. T2 adds the explicit way to ask the question, so the refusal is not a dead end.

1. Add `ParameterGraph.intervene(values, do: Mapping[str, ParameterValue]) -> PropagationResult`. Semantics (Pearl's `do`): each name in `do` has its determining equation removed from the evaluation for this call, the value is pinned, and every descendant is recomputed from it. Equations that take the pinned name as an input still run; the equation that would have produced it is skipped and reported as `cut`.
2. A pinned name inside a feedback loop breaks the loop; the SCC must be re-solved without that variable. Test it on `loop_1` and `loop_2` from `alea prg summary`.
3. The result carries `cut: tuple[str, ...]` (equations skipped) and `pinned: dict[str, ParameterValue]`. The range check applies to the pinned value.
4. Never let `intervene` mutate the stored graph; it is a pure function of its inputs.
5. Tests: pin `additional_abatement_mtco2` to 136; assert descendants move and the producing equation is in `cut`; assert `propagate` on the same values still refuses. Add one test per loop. Add a property test (hypothesis, if already a dependency, else a fixed table of 20 cases) that `intervene(values, do={n: derived_value_of_n})` reproduces `propagate(values)` for every derived `n`: pinning a node to the value it would have had changes nothing.
6. Expose it as `alea prg propagate --do name=value` (CLI), `do` on the API request model, and a "pin" control in `prg/ui/index.html` that is shown only on derived nodes. Read the existing UI file in slices; do not load it whole.
7. Docs: in `docs/how_prg_works.md` state exactly what `intervene` identifies and what it does not. It answers "what if this quantity were X within this model's equations". It does not identify a real-world causal effect, because the equations are documented relationships and not estimated from interventional data. Keep the README phrase "dependency graph" until a reviewer who is not the author agrees otherwise.

Done when: the probe returns 136 for the pinned node with its producing equation named as cut, and the identity property test passes.

### T3. Make the defaults consistent (fixes D3)

1. Run `uv run alea prg conflicts` and `uv run alea prg sensitivity frequency_nadir_hz`. Print the equation, its inputs at default, and its cited source.
2. Recompute the nadir by hand with units. Decide whether the equation, an input default, or the declared range is wrong. Do not widen the range to pass; a threshold chosen to pass is not a test.
3. Fix at the generator or fragment that owns the node (see `docs/research/` generator-ownership note and the memory entry "A bake rewrites the whole file"); regenerate, do not hand-edit `config/prg.yaml`.
4. Add a gate: `uv run alea prg check` at defaults exits 0, run in CI. Canary by setting `largest_loss_mw` to a value that must violate, and confirm exit non-zero.
5. Scan for the same class: loop over every derived node at defaults and list any outside its declared range (`g.range_excursions()` after a default propagate). Report the count before and after.

### T4. Couple the graph to the solver (fixes D4)

Order by value; do each as its own commit.

- **T4a. Name the seven unreached engine fields.** For each of the seven printed by `engine_fields_unreached()`, either add a PRG parameter and a `TRANSLATIONS` entry (`alea/prg/translate.py`) or record in the translation register why the field is engine-internal. A silent gap is the defect, not the absence.
- **T4b. Widen knob coverage by class.** Take the 1,014 reaching-none list from the measurement script, group by system (17), and for the three systems with the most settable parameters decide knob versus audit-only. Audit-only is legitimate if the post-solve audit (`prg/audit.py`) checks it. Add a `reach` column to the measurement output: `knob`, `constraint`, `audit`, `none`. The target is `none == 0` or a written reason per remaining parameter, not a percentage.
- **T4c. Make `planning/` consume the graph.** Today only `whatif/service.py` does. Add one entry point in `planning/` that takes a propagated parameter set and returns `ScenarioParameters`, so a plain `alea solve` honours the same translations the what-if path does. Test: the same scenario through `solve` and through `whatif` yields identical `ScenarioParameters` (equality, not closeness).
- **T4d. Constraint terms.** The 43 bound routes carry 78 terms. For each bound route, assert in a test that the constraint is binding or slack in a known case, so a route that silently never binds is visible. A constraint that is never tight in any scenario is a candidate for removal or for a mis-scaled bound.

Gate after T4: `scripts/measure_prg_engine_coupling.py` output is recorded in `docs/research/alea-prior-art/README.md` with the date, and the README and kernel numbers are updated to match.

### T5. Type and lint clean (fixes D8, D9)

1. Widen `detect_conflicts` annotations; skip non-numeric values explicitly with a comment. Re-run `uv run pyright src` and require 0 errors.
2. `viirs_h5.py`: narrow h5py objects with `isinstance`, raise `ValueError` with the dataset path otherwise. Test with the real fixture under `tests/data`, not a mock.
3. `config/__init__.py`: one literal `__all__`.
4. Remove the four ruff findings by hand. Rename `l` to `line`.
5. Add `uv run pyright src` and `uv run ruff check src tests scripts` to `make check-quick` if absent. Canary each by planting one error.

### T6. Close the milestones and the claims register (fixes D6, D7)

Each item produces an artefact; none edits the register by hand. Use `scripts/quality/` and `docs/research/milestone-data/`.

1. **M1 full year.** `uv run python scripts/quality/kenya_m1.py 0 2030` (0 means all 8,760 hours). Expected hurdle: memory and wall time. Use the rolling-window decomposition already used for 91 days; record solver, gap, wall time, peak RSS. Clauses: optimal, two runs agree to 1e-6, losses non-zero, fleet coverage at or above 90% (name the missing capacity if not). Resolves claims #6 and #9: report the measured loss overestimate and the geothermal substitution result against the claim, and withdraw the claim if it does not reproduce.
2. **M2.** Reproduce claims #1 to #3 from `docs/research/milestone-data/viirs-ghana-2022-findings.md` and the Open-Meteo Kenya data. Report the base rate beside every accuracy figure.
3. **M3, M4, M5, M6, M7, M8.** Follow `14-roadmap.md` §3 per milestone. For M5 (EAPP and Egypt hydrogen, claim #10) and M7 (scale, claim #8), write the failure case first: what measurement would withdraw the claim.
4. Hydro energy limit and atlite profiles: both are listed open. Archive the ERA5 cutout provenance under `docs/research/milestone-data/era5/` and test that a hydro plant's annual energy never exceeds its stated limit in a solved year.
5. After each milestone, `uv run alea quality claims` must change. If the register output did not change, the artefact did not land (the "producer is not a delivery" rule): use `alea project` to land it at the dated path its report section reads, and check the section renders it.

### T7. Data and documentation debt (fixes D10, D11, D12, D13)

1. D10: print the 138 drift pairs grouped by system. Decide the authority per the generator rule, regenerate, and show the count at 0 or each remainder justified.
2. D11: archive the 43 missing works. For paywalled ones, archive the landing page and the abstract, mark `access: abstract-only` in the index, and do not claim the content was read.
3. D12: replace the em dashes in `README.md` and any other docs-qa errors, then run docs-qa to zero errors across the repo.
4. D13: confirm or retire the three unit exemptions.

### T8. Honest closeout

1. Re-run every command in §1 and record before and after counts in this file's §4.
2. `uv run pytest -x -q tests` as the checkpoint, `uv run python scripts/gate_register.py` (142 promised, 142 verified today; it must stay 142 or rise with the new gates, each with a canary).
3. Update the README status table, `docs/capability_matrix.md`, and the llocal and datacraft pages only with numbers printed by T8.1.
4. Update `docs/research/alea-funding/enaccess-email.md` status from "draft, not sent" to "sent" with the date the owner gives. The email's claim "full-year solve is not finished yet" must be revised if T6.1 lands.

## 3. Order of work and gates

| Step | Tasks | Gate before moving on |
|---|---|---|
| 1 | T1, T5 | new refusal tests green; pyright and ruff at 0 |
| 2 | T3 | `alea prg check` exits 0 at defaults |
| 3 | T2 | identity property test green; loops covered |
| 4 | T4a to T4d | coupling script reports `none` justified or 0 |
| 5 | T6 | each claim's register row changes or is withdrawn with evidence |
| 6 | T7, T8 | docs-qa 0 errors; full suite; gate register 100% |

T6 is the long pole (months, per the roadmap) and is independent of T1 to T5 apart from T3; it can start in parallel once step 2 is done. Keep the single-country-first rule: Kenya completes before any second country.

## 4. Before and after

Fill in at T8. Columns: defect, command, before (2026-11-25), after.

| Defect | Command | Before | After |
|---|---|---|---|
| D1 | the D1 probe | accepted, value kept 45.0 | |
| D2 | the D2 probe | accepted | |
| D3 | `alea prg check` | 1 violation | |
| D4 | `measure_prg_engine_coupling.py` | 81 of 1,095 (7.4%) | |
| D6 | `alea quality claims` | 10 unverified | |
| D8 | `pyright src` | 16 errors, 1 warning | |
| D9 | `ruff check` | 4 findings | |
| D10 | `alea prg summary` drift lines | 138 | |
| D11 | `alea prg citations` | 43 unarchived | |
