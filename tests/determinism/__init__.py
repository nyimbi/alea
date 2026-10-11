# SPDX-License-Identifier: MIT
"""The determinism harness.

Run in two separate processes by CI and diffed. Separate processes is the whole
point: every defect this catches -- a cache keyed on `hash()`, an unseeded
MinHash, iteration over an unordered set -- produces the *same* answer twice
inside one interpreter and different answers across two. A same-process test
passes against all of them.
"""

from tests.determinism.run import main

__all__ = ["main"]
