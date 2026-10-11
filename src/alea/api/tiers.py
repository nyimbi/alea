# SPDX-License-Identifier: MIT
"""Access tiers.

Four tiers, ordered. Ordering is the whole point: a route declares the tier it
needs and the dependency compares ranks, so adding a route cannot accidentally
grant access by naming a tier string that happens to sort late.

The tier also sets the rate limit (11-layer8 §4.1: "rate limits are per key and
per tier"). A public key on a shared adapter credential and an internal key
running the pipeline should not share a ceiling, and the multiplier table below
is the one place that decision lives.
"""

from __future__ import annotations

from enum import StrEnum


class Tier(StrEnum):
	"""What a principal is allowed to reach.

	The wire values are the strings that appear in a stored key record, so they
	are stable: changing one invalidates every key carrying it.
	"""

	PUBLIC = "public"
	"""Reports, forecasts, prices at national resolution. Generous limit."""

	ANALYST = "analyst"
	"""Losses, resilience, what-if, signals. A registered, accountable user."""

	RESTRICTED = "restricted"
	"""Maintenance, raw signals, review actions. Key plus role."""

	INTERNAL = "internal"
	"""Pipeline triggers and administration. mTLS or network, never a public key."""


_RANK: dict[Tier, int] = {
	Tier.PUBLIC: 0,
	Tier.ANALYST: 1,
	Tier.RESTRICTED: 2,
	Tier.INTERNAL: 3,
}

_MULTIPLIER: dict[Tier, int] = {
	Tier.PUBLIC: 1,
	Tier.ANALYST: 2,
	Tier.RESTRICTED: 4,
	Tier.INTERNAL: 8,
}


def rank(tier: Tier) -> int:
	"""The tier's position in the ordering. Higher reaches more."""
	assert tier in _RANK, f"unranked tier {tier!r}"
	return _RANK[tier]


def satisfies(held: Tier, required: Tier) -> bool:
	"""Whether a principal holding ``held`` may reach a route requiring ``required``.

	A tier that is not in the table is a programming error, not a denial: a
	silent ``False`` here would look like a permissions bug at 2am. The lookup
	raises instead.
	"""
	assert held in _RANK and required in _RANK, f"unknown tier: {held!r} / {required!r}"
	return _RANK[held] >= _RANK[required]


def rate_multiplier(tier: Tier) -> int:
	"""How many times the configured base limit this tier receives."""
	assert tier in _MULTIPLIER, f"unrated tier {tier!r}"
	return _MULTIPLIER[tier]


__all__ = ["Tier", "rank", "rate_multiplier", "satisfies"]
