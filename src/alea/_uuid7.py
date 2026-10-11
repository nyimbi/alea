# SPDX-License-Identifier: MIT
"""Identifier helpers.

All entity identifiers in ALEA are UUID7 strings. UUID7 is time-ordered, so
sorting by identifier sorts by creation time and identifiers cluster in B-tree
indexes the way an auto-increment would, without leaking a sequence.

``uuid6.uuid7`` is the reference implementation; this shim keeps the call sites
short and gives one place to change if the identifier scheme ever moves.
"""

from __future__ import annotations

from uuid6 import uuid7


def uuid7str() -> str:
	"""Return a new UUID7 as a string."""
	return str(uuid7())


__all__ = ["uuid7str"]
