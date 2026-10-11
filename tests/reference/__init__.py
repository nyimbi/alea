# SPDX-License-Identifier: MIT
"""Independent Python references for the compiled kernels.

Each module here reimplements one kernel group the obvious, slow way — nested
loops over small inputs — so that a differential test against the Rust kernel
tests the kernel rather than a second copy of the same misunderstanding.

These modules are deliberately **not** the production path. They exist only for
`tests/ci/test_kernels_differential.py`. They were written from the kernel
contracts (the wrapper docstrings in `alea._core.kernels` and
`docs/plans/03-rust-core.md`), never from the Rust source: two copies of one
misreading agree with each other and prove nothing.

Where the wrapper pins a semantic (cloudy pixels are NaN and not zero; VaR and
CVaR are positive loss magnitudes; aggregation weights sum exactly to
`n_timesteps`), the reference encodes the pinned version and the docstring says
so.
"""

from __future__ import annotations

__all__: list[str] = []
