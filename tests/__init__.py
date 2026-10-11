# SPDX-License-Identifier: MIT
"""ALEA's test tree as a package.

`tests` is a package so the canaries can import their shared harness
(`tests.ci.canaries.planted`) by its full path rather than by whatever directory
pytest happened to prepend. Without it, pytest inserts the *nearest* directory
lacking `__init__.py` -- `tests/ci` -- and the same import resolves differently
depending on where pytest was invoked from.
"""
