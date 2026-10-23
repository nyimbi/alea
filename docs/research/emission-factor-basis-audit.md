# Emission-factor basis audit

The seven `emission_factor_<tech>_t_per_mwh` nodes decide the headline. Batch 47
(commit `b875027`) replaced one generic factor with a generation-weighted mean
over these seven, so `fleet_emission_intensity_t_per_mwh` and everything derived
from it now inherits whatever basis each node is on. This audit reads each
shipped number against the two bases it could plausibly be on -- lifecycle
(gCO2e/kWh, LCA) and direct combustion (IPCC 2006 stationary-combustion carbon
content divided by a heat rate) -- and states which one it matches.

**Verdict in one line: the seven are not on one basis, but the mixture is not
the one suspected. The three fossil factors are direct combustion; the four
low-carbon factors are lifecycle. The biomass factor is lifecycle in kind but
not in magnitude. The headline moves by at most 1.24% from fixing the category
error, so batch 47 survives; the larger exposure is that the fossil factors sit
~10% above what the graph's own `efficiency_*` nodes imply.**

## What is shipped

| node | default (t/MWh) | unit | source field |
|---|---|---|---|
| `emission_factor_coal_t_per_mwh` | 0.92 | tonne/MWh | IPCC lifecycle emission factors, 2014; fuel carbon contents |
| `emission_factor_gas_t_per_mwh` | 0.45 | tonne/MWh | same |
| `emission_factor_oil_t_per_mwh` | 0.78 | tonne/MWh | same |
| `emission_factor_biomass_t_per_mwh` | 0.04 | tonne/MWh | same |
| `emission_factor_nuclear_t_per_mwh` | 0.006 | tonne/MWh | same |
| `emission_factor_hydro_t_per_mwh` | 0.01 | tonne/MWh | same |
| `emission_factor_geothermal_t_per_mwh` | 0.03 | tonne/MWh | same |

Every description carries the same sentence: *"stack factor from the fuel's
carbon content; lifecycle additions folded in for the low-carbon technologies,
whose stack term is zero."* That sentence is the basis claim under audit. It
describes a **hybrid**: direct stack for the fossil fuels, lifecycle for the
low-carbon four. The question is whether the numbers match the sentence.

## The per-fuel table

Lifecycle ranges are from IPCC AR5 WG3 (2014) Annex III, Table A.III.2
(`sources/archive/ipcc_ar5_wg3_annex3.pdf`, printed p. 1335), and IPCC SRREN
(2011) Annex II, Table A.II.4 (`sources/archive/ipcc_srren_2011_excerpt.pdf`,
printed p. 982). Combustion ranges are computed from the IPCC 2006 default
carbon contents already archived at
`sources/archive/ipcc_2006_gl_vol2_ch2.txt` (Table 2.2: coal 94 600, natural gas
56 100, residual fuel oil 77 400, wood/wood waste 112 000 kg CO2/TJ), divided by
a plausible net efficiency. The graph's own `efficiency_coal` = 0.40,
`efficiency_gas` = 0.58, `efficiency_oil` = 0.38 are the heat rates it already
carries, and are the ones used where a graph-consistent number is wanted.

| fuel | shipped | lifecycle range (g/kWh) | combustion range (g/kWh) | verdict |
|---|---|---|---|---|
| coal | 0.920 | AR5 740-820-910; SRREN 675-1001-1689 | 851 @ 40% eff (graph), 973 @ 35% | **combustion**, +8% above the graph's own heat rate |
| gas | 0.450 | AR5 410-490-650; SRREN 290-469-930 | 348 @ 58% eff (graph), 449 @ 45% | **combustion**, +29% above the graph's own heat rate |
| oil | 0.780 | AR5 has no oil row; SRREN 510-840-1170 | 733 @ 38% eff (graph), 796 @ 35% | **combustion**, +6% above the graph's own heat rate |
| biomass | 0.040 | AR5 130-230-420 (dedicated); SRREN biopower median 18 | 1 152 @ 35% (biogenic CO2); ~6 @ CH4+N2O only | **neither**; lifecycle in kind, ~10x low in magnitude |
| nuclear | 0.006 | AR5 3.7-12-110; SRREN 1-16-220 | 0 (no combustion) | **lifecycle**, below the AR5 median |
| hydro | 0.010 | AR5 1.0-24-2200; SRREN 0-4-43 | 0 (no combustion) | **lifecycle**, below the AR5 median |
| geothermal | 0.030 | AR5 6.0-38-79; SRREN 6-45-79 | 0 (no combustion) | **lifecycle**, below the AR5 median |

AR5 rows are quoted min/median/max as printed. SRREN rows are quoted
min/50th-percentile/max from Table A.II.4.

## The basis test, fuel by fuel

The decisive arithmetic is the *implied heat rate*: take the IPCC 2006 default
carbon content, convert to t/MWh at 100% efficiency, and divide by the shipped
factor. A number that lands on a plausible thermal efficiency is a
direct-combustion figure. A number near 100% is a stack term with the biogenic
or zero-carbon assumption baked in; a number far above 100% means the factor is
smaller than any stack term could be.

| fuel | carbon content (tCO2/TJ) | t/MWh @ 100% | shipped | implied efficiency |
|---|---|---|---|---|
| coal | 94.6 | 0.34056 | 0.92 | **37.0%** |
| gas | 56.1 | 0.20196 | 0.45 | **44.9%** |
| oil | 77.4 | 0.27864 | 0.78 | **35.7%** |
| biomass | 112.0 | 0.40320 | 0.04 | **1008%** (impossible as a stack term) |

Coal, gas and oil land in the 35-45% band, which is exactly where pulverised
coal, CCGT and oil-fired steam plants sit. They are direct-combustion figures.
Biomass at 1 008% is arithmetically impossible for a stack term: 0.04 is not
"the stack factor from the fuel's carbon content", it is roughly a tenth of
what the fuel's carbon content implies even before any heat rate is applied.
The description's own claim about biomass is therefore false on its face.

### Coal, gas, oil: direct combustion, but not at the graph's heat rates

The three fossil factors are direct combustion. They are also *inconsistent
with the graph's own efficiency nodes*, which is a second, separate defect from
the basis mixture:

| fuel | shipped | stack at `efficiency_*` | shipped / stack |
|---|---|---|---|
| coal | 0.920 | 0.8514 | 1.081 |
| gas | 0.450 | 0.3482 | 1.292 |
| oil | 0.780 | 0.7333 | 1.064 |

The gas factor is the outlier: 0.45 implies a 44.9% efficient plant, while the
graph ships `efficiency_gas` = 0.58. Whichever number is right, the pair is not
self-consistent. This matters beyond the emissions headline: the same factors
enter every `lcoe_<tech>_definition` as `emission_factor_<tech> *
carbon_price_usd_per_tco2`, so a fossil factor that is 8-29% high overstates the
carbon cost of that technology by the same margin.

### Biomass: lifecycle in kind, not in magnitude

This is the fuel the suspicion named, and the suspicion was half right. The
shipped 0.04 is **not** a direct-combustion figure -- a biomass stack term is
about 1.15 t/MWh at 35% efficiency, and the biogenic CO2 is normally excluded
from reported totals entirely, which is what makes a "combustion basis" number
for biomass ambiguous in the first place. 0.04 is far closer to the lifecycle
family than to the stack family, so the basis mixture is *not* "biomass on
combustion, everything else on lifecycle".

But 0.04 does not match the lifecycle literature either:

- AR5 WG3 Table A.III.2 gives dedicated biomass at **130 / 230 / 420** g/kWh
  (min / median / max).
- SRREN Table A.II.4 gives biopower a 50th percentile of **18** g/kWh, with a
  25th percentile of 360 and a maximum of 75.

Those two sources disagree by an order of magnitude at the median, and the
SRREN column is internally non-monotonic (25th percentile 360 exceeds the
median 18 and the maximum 75), which is a defect in the printed table rather
than a fact about biomass. The spread is real and it is the point: biomass
lifecycle emissions are dominated by feedstock, land-use change and whether
biogenic carbon is counted, so a single number for "biomass" is a modelling
choice, not a measurement. The graph does not record which choice 0.04 encodes.

0.04 is also not reproducible from the CH4/N2O-only path: wood boiler defaults
of 11 kg CH4/TJ and 7 kg N2O/TJ at GWP100 (CH4 28, N2O 265) give about 0.006
t/MWh, an order of magnitude below the shipped figure. So 0.04 is not "the
non-CO2 combustion term" either.

**The honest statement is that 0.04 is a lifecycle-order figure of unknown
provenance.** It is not on a combustion basis, so it does not create the
incoherence the suspicion feared, but it is not traceable to either archived
table and should not be presented as an IPCC 2014 value.

### Nuclear, hydro, geothermal: lifecycle, and deliberately low

These three carry no stack term -- there is no combustion -- so lifecycle is the
only basis available and the shipped numbers are lifecycle. They sit below the
AR5 medians (0.006 vs 0.012; 0.010 vs 0.024; 0.030 vs 0.038) but inside the
published min-max ranges (3.7-110, 1.0-2200, 6.0-79 g/kWh). Being low within a
very wide range is a defensible choice for a fleet-average model; it is not a
basis error. Their combined weight in the numerator is 1.13%, so the choice is
also immaterial to the headline.

## The citation gap, confirmed

The seven nodes cite "IPCC lifecycle emission factors, 2014". Before this audit
`sources/INDEX.md` held no row for any IPCC 2014 lifecycle document -- the only
IPCC row was `ipcc_2006_gl_vol2` (2006 Guidelines Vol. 2), whose `cites`
spellings ("IPCC Guidelines for National Greenhouse Gas Inventories", "IPCC 2006
Guidelines, Volume 2") do not match the string on these nodes. The citation
pointed at nothing archived, and the string did not even resolve to the 2006
row. **Confirmed.**

The source has now been archived:

- `sources/archive/ipcc_ar5_wg3_annex3.pdf` (+ `.txt`) -- AR5 WG3 Annex III,
  the document carrying Table A.III.2.
- `sources/archive/ipcc_srren_2011_excerpt.pdf` (+ `.txt`) -- the SRREN pages
  carrying Figure SPM.8 and Annex II Table A.II.4. An excerpt rather than the
  46 MB full report: the cited pages are the evidence, and a labelled five-page
  extract is checkable where a blob is not.
- Both digests are recorded in the `## Digests of the archived copies` table.

### Why the rows are not in the register yet

Adding rows to the Works table **fails a hard test**. `citation_report()` joins
the register against equation `reference` fields only
(`_equation_references()` reads `document["equations"][id]["reference"]`). A
node's `source` field is never read. So a row cited only from a node source is
reported `unreachable`, and
`tests/ci/test_citation_register.py::test_every_registered_work_is_reached_by_a_citation`
asserts no row is unreachable. Adding the two rows without also wiring an
equation reference failed that test, verified by running it.

This is a structural finding in its own right, not a workaround. Of 1 330
parameters carrying a `source` string, **1 262 resolve to no register row** --
the register cannot see node-level citations at all, so the rule it exists to
enforce is applied to roughly one channel of the tree and not the other. The
seven nodes under audit are a single instance of a class. Fixing it means
teaching `citation_report()` to read parameter sources, which changes what the
gate asserts and is a decision for the owner of that gate, not a side effect of
this audit. Until then the archives and their digests are in place and the
register rows are withheld deliberately.

## What this does to the headline

Measured on the loaded graph at defaults. The weights are the batch-46
generation nodes: coal 19.710, gas 7.884, oil 0.3942, biomass 0.6132, nuclear
0.0, hydro 7.227, geothermal 5.9568 TWh; `fleet_generation_twh` = 68.0652;
`emissions_mtco2_per_year` uses `generation_twh` = 51.5544.

Shipped: **0.327098 t/MWh**, **16.8633 MtCO2/yr**.

| scenario | intensity | MtCO2 | change |
|---|---|---|---|
| shipped (mixed basis) | 0.327098 | 16.8633 | -- |
| fossil as shipped, low-carbon zeroed | 0.323050 | 16.6547 | **-1.24%** |
| fossil at graph `efficiency_*`, low-carbon zeroed | 0.291124 | 15.0087 | **-11.00%** |
| direct incl. biogenic biomass stack | 0.301502 | 15.5438 | -7.83% |
| lifecycle: AR5 medians throughout | 0.307019 | 15.8282 | -6.14% |

Single-fuel sensitivity, to show where the mass is:

| change | intensity | change |
|---|---|---|
| coal 0.92 -> 0.82 (AR5 median) | 0.298140 | -8.85% |
| coal 0.92 -> 1.001 (SRREN median) | 0.350553 | +7.17% |
| gas 0.45 -> 0.348 (stack at graph eff) | 0.315306 | -3.60% |
| biomass 0.04 -> 0.23 (AR5 median) | 0.328810 | **+0.52%** |
| biomass 0.04 -> 0.018 (SRREN median) | 0.326900 | -0.06% |
| nuclear, hydro, geothermal to AR5 medians | 0.329284 | +0.67% combined |

**The batch-47 repair survives.** The repair's substance was weighting by
generation rather than capacity and splitting the single generic factor into
per-fuel factors. Neither is touched by a basis correction. The suspected
incoherence -- biomass on combustion beside six lifecycle figures -- does not
exist: biomass is lifecycle-order, and its entire contribution to the numerator
is 0.11%. Correcting it to either published median moves the headline by less
than 0.6%.

What does *not* survive cleanly is the claim that these are "IPCC lifecycle
emission factors, 2014" applied uniformly:

1. The fossil three are **direct combustion**, not lifecycle. Using them beside
   lifecycle figures for the low-carbon four is the hybrid the description
   describes, so the *equation* is coherent with its own stated intent -- but
   the source label "lifecycle emission factors" is wrong for three of seven.
2. The fossil three are **8-29% above the stack term implied by the graph's own
   `efficiency_*` nodes**. That is a ~11% exposure on the headline and an
   equivalent overstatement in every `lcoe_<tech>` carbon-cost term. It is the
   largest single number in this audit and it is not a basis question -- it is
   an internal-consistency question between two sets of shipped parameters.
3. Biomass 0.04 is **untraceable** to either archived table and should not
   carry an IPCC attribution it cannot support.

## Recommended corrections

Ordered by materiality. **Recommendations 1, 2 and 4 are applied as of batch
51** (2026-10-23); 3 and 5 are still open, and the status of each is stated
below rather than left for a reader to diff against the graph.

1. **Reconcile the fossil factors with `efficiency_*`.** Either the factors
   move to 0.851 / 0.348 / 0.733, or the efficiencies move to 0.37 / 0.449 /
   0.357. Pick one direction and make the other derived. ~11% on the headline.

   **APPLIED (batch 51).** The second direction: the efficiencies stay, because
   they are the better-sourced pair (IEA/NEA 2020 net efficiencies, with 0.58
   the CCGT median of that table), and the three factors became derived as
   `carbon_content_<fuel>_t_per_gj * gj_per_mwh / efficiency_<fuel>`. Three new
   exogenous nodes carry the carbon contents in the unit the IPCC table prints.
   Measured on the loaded graph: the factors are now **0.851400 / 0.348207 /
   0.733263**; `fleet_emission_intensity_t_per_mwh` **0.327098 -> 0.295172**
   (**-9.76%**, matching this audit's scenario table); `emissions_mtco2_per_year`
   **16.8633 -> 15.2174**. The three thermal LCOEs move with them -- coal
   119.810 -> 116.380, gas 113.17 -> 108.077, oil 344.03 -> 341.697 -- because
   each carries `emission_factor_<tech> * carbon_price_usd_per_tco2`.

   The direction was chosen on sourcing, not on convenience: moving the
   *efficiencies* to 0.37 / 0.449 / 0.357 would have left the factors as
   unbacked dials and kept the false lifecycle label.
2. **Relabel the source.** "IPCC lifecycle emission factors, 2014" is false for
   coal, gas and oil. The defensible string for those three is "IPCC 2006
   Guidelines Vol. 2 Ch. 2 default carbon contents (Table 2.2), divided by the
   graph's `efficiency_<tech>`" -- which is also the fix that makes (1)
   automatic.

   **APPLIED (batch 51).** Both the three carbon-content nodes and the three
   derived factors now carry that string, and the three values (94 600,
   56 100, 77 400 kg CO2/TJ) were verified against the archived
   `sources/archive/ipcc_2006_gl_vol2_ch2.txt` rather than quoted from memory.
3. **Restate biomass.** Choose a published value with a stated basis and cite
   the table it comes from (AR5 Table A.III.2 median 0.23, or SRREN A.II.4
   median 0.018, or state the feedstock assumption). 0.04 should not remain an
   unattributed number. Effect on headline: <0.6%.
4. **Leave nuclear, hydro and geothermal alone.** Lifecycle, inside published
   ranges, 1.13% of the numerator combined. **APPLIED** in the sense that batch
   51 did not touch them: only the three fossil factors were derived, and the
   four low-carbon factors remain exogenous lifecycle dials.
5. **Give the register a node-source channel — but not as stated above.**
   `citation_report()` reads equations only, and 1 262 of 1 330 parameter
   sources resolve to nothing because of it. Measured since this audit was
   written (2026-10-23, on the tree at batch 49): the blocker is not only the
   missing channel, it is that most of what the channel would carry is not a
   citation. Of 1 332 node sources, **709 (53.2%) are batch provenance markers**
   ("The product coupling (batch 28)"), **216 (16.2%) are the catalog pointer
   `docs/params.md`**, and only **407 (30.6%) name a work**. Widening the gate
   to read node sources as they stand would demand the register resolve 925
   strings that are not citations, and the gate would be red until every one was
   either rewritten or exempted — which is how a gate gets a filter written to
   quiet it.

   The repair is two steps, in this order: separate provenance from citation in
   the node schema (a `provenance` field for the batch marker, leaving `source`
   for the work), *then* teach `citation_report()` to read the `source` channel.
   Done in the other order it fails open or fails red. The two IPCC rows this
   audit archived belong in the register once the first step lands.

## Sources

Archived in this repository, digests in `sources/INDEX.md`:

- IPCC AR5 WG3 (2014), *Annex III: Technology-specific cost and performance
  parameters*, Table A.III.2, printed p. 1335 --
  `sources/archive/ipcc_ar5_wg3_annex3.pdf`.
- IPCC SRREN (2011), Figure SPM.8 (pp. 18-19) and Annex II Table A.II.4
  (pp. 981-983) -- `sources/archive/ipcc_srren_2011_excerpt.pdf`.
- IPCC (2006), *Guidelines for National Greenhouse Gas Inventories*, Vol. 2
  Ch. 2, Tables 2.2 and 2.4 -- already held at
  `sources/archive/ipcc_2006_gl_vol2_ch2.pdf`.

Two caveats on the evidence. First, AR5 Table A.III.2 has **no oil row**; the
oil lifecycle range above is SRREN's only. Second, SRREN Table A.II.4's
biopower column is internally non-monotonic as printed, so its median is quoted
with that defect stated rather than used as a point estimate. Where neither
table resolves a fuel's basis, this audit says so rather than interpolating.
