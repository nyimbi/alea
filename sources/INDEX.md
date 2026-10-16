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
