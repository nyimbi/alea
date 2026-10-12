# SPDX-License-Identifier: MIT
"""Market data: nothing yet, and the reason is in the plan.

`06-layer3-market.md` runs Layer 3 off the solved networks and the demand and
generation artefacts, not off a source of its own -- the market layer's inputs
are the planning layer's outputs. A `market.smk` with no rules in it is the
honest shape for that today.

The file exists so that `Snakefile`'s include list names every rules module a
reader would look for, and so that adding the first market rule does not mean
editing the include list. `tests/ci/test_orchestration_workflow.py` asserts
every include in the `Snakefile` resolves to a file that exists, which is what
makes an empty module different from a missing one.
"""
