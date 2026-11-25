# The default frequency nadir (T3), investigated 2026-11-25

Status: **diagnosed, not fixed.** Changing a default is a modelling decision that earlier sessions held open on purpose, and the evidence below changes what the decision is.

## Measured at the shipped defaults

| Quantity | Value | Source |
|---|---|---|
| `nominal_frequency_hz` | 50 Hz | default |
| `largest_loss_mw` | 1,000 MW | default |
| `system_inertia_mws` | 39,200 MW.s | derived, `inertia_from_capacity_definition` (firm 9,800 MW at H = 4 s) |
| `rocof_df_dt_hz_per_s` | 0.6378 Hz/s | derived, `rocof_definition` |
| `frequency_response_time_s` | 10 s | default, exogenous |
| `frequency_nadir_hz` | 43.6224 Hz | derived, `frequency_nadir_definition` |

Hand recomputation with units: 50 Hz x 1,000 MW / (2 x 39,200 MW.s) = 0.6378 Hz/s; 50 - 0.6378 x 10 = 43.62 Hz. The arithmetic and the units are right. `range_excursions()` at defaults lists exactly one parameter, `frequency_nadir_hz`, and `consistency()` lists exactly one violation, `frequency_nadir_hz_out_of_range`. So the class scan finds one excursion, not a family.

A nadir at or above the 48 Hz protection threshold needs a response time of 3.14 s or less. At or above the 45 Hz floor it needs 7.84 s.

## What is wrong

The equation is not. `frequency_nadir_definition` holds the initial slope for the whole response time and reports the frequency at the moment response *begins*. Its own description calls this an upper bound on the nadir used as a screen.

The input is. The node `frequency_response_time_s` is defined as "the time between the loss of generation and the start of primary frequency response". The shipped default of 10 s is a delivery time, not a start time:

- EU network code (Regulation 2016/1447, RfG): maximum initial delay 0.5 s, full activation within 30 s unless the TSO specifies longer.
- GB: primary response delivered within 10 s of the event; a modelling paper on the GB specification reads it as injection starting within 2 s, full power by 10 s.
- Shams (2017), already archived at `docs/sources/archive/shams_2017_frequency_low_inertia.pdf`: time to nadir in a low-inertia system is of the order of 2 to 3 s; fast frequency response is within 0.5 s of triggering.

So 10 s applies the end of the arrest window as if it were the start. No source in hand supports 10 s as a start-of-response time. The 45 Hz floor is the UFLS setting it claims to be, so it is not the number to move.

## Decision needed

Replace the default with a cited start-of-response time. 2 s is the GB initial-delay reading and gives a nadir of 48.72 Hz; the EU 0.5 s gives 49.68 Hz. Either passes the 48 Hz rule, and the choice is from the source, not from the threshold. A default chosen because it passes is the failure this repo's earlier notes name, so the source must be archived before the number moves.

Not done, and why:

1. The GB and EU texts are not archived under `docs/sources/`. The figures above come from a web search summary, which `docs/prg-status.md` records as unreliable for exact figures. Archive the Regulation 2016/1447 text and the GB Grid Code section first.
2. The Kenya Grid Code was not found. If Kenya is the first-country target, its figure governs.
3. The edit belongs in the generator or fragment that owns `frequency_response_time_s` (not `config/prg.yaml`), followed by a regeneration. Tests that pin 10 s (`tests/ci/test_prg.py` near lines 2276, 6184) move with it, and `KNOWN_DEFAULT_FINDINGS` empties.

After that, the gate in the plan applies: `alea prg check` at defaults exits 0 (it exits 1 today) and CI runs it, with a canary setting `largest_loss_mw` to a value that must violate.
