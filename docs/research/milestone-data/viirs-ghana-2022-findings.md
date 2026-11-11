# VIIRS vs GridWatch Ghana 2022: what the first measurement says

Run 2026-11-11, tile h17v08, 349 VNP46A2 days, 350 VNP46A1 days, 437 sensors.
Truth: pixel-night outage = share of reporting GridWatch readings unpowered in
00:00-03:00 UTC (>=5 readings). 134,255 pixel-nights, 393 pixels.

| Score | Truth | AUC |
|---|---|---|
| Detector flag (0/1), `viirs_detection` artefact | share >= 0.5 (base rate 5.5%) | 0.504 |
| radiance / q25 baseline, clear obs only (44.8% of pixel-nights) | share >= 0.5 | 0.517 |
| same | share >= 0.9 (837 positives) | 0.539 |

Registration check: the continuous score was recomputed at all 25 pixel offsets
in a 5x5 window. AUC is flat (0.505-0.523 at share >= 0.5; 0.514-0.549 at
>= 0.9) with no peak at (0, 0), so a one-to-two pixel misregistration is not
what hides the signal. Pixels with three or more sensors held no outage
pixel-night at the 0.5 or 0.9 threshold: GridWatch outages in this year are
single-sensor events.

Reading: a household sensor losing power does not move 460 m nightly radiance
enough to rank above noise. This does not reproduce or refute the claimed AUC
0.8346 (different year, truth definition, baseline); claim 1 stays open.
Untested: a multi-year baseline, feeder-level truth (several sensors off at
once), and score restricted to bright (urban) pixels.
