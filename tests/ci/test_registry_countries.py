# SPDX-License-Identifier: MIT
"""`01-foundations.md` §3.3's registry gates, against the plan's own table.

The registry is generated from the *per-country tables* in
``spec/data-completeness.md``, because that file's summary table contradicts its
own body: the summary reports HIGH 5 / MEDIUM 32 / LOW 7 and puts Equatorial
Guinea in MEDIUM where the tables put it in LOW (twice, which is where the
miscount comes from). The plan verified the tables and recorded the result:

| Tier | Count | ISO codes |
|---|---|---|
| HIGH | 6 | EG, GH, KE, MA, NG, ZA |
| MEDIUM | 34 | AO BF BJ BW CD CG CI CM DZ ET GA GM GN LR LS LY MG ML MU MW MZ NA NE RW SD SL SN SZ TG TN TZ UG ZM ZW |
| LOW | 8 | CF EH ER GQ GW SO SS TD |
| CRITICAL | 7 | BI CV DJ KM MR SC ST |

The gates below assert that table, by membership rather than by count. A count
is satisfied by two compensating errors -- one country moved out of MEDIUM and
another moved in leaves 34 -- and the whole reason this registry exists is that
a summary and a body disagreed about *which* countries, not about how many.
"""

from __future__ import annotations

import pytest

from alea.registry import (
	AU_MEMBER_STATE_COUNT,
	CompletenessTier,
	PowerPool,
	by_power_pool,
	by_tier,
	get_country,
	proxy_countries,
	registry,
	tier_counts,
)

# The plan's §3.1 table, verbatim.
EXPECTED_TIERS: dict[CompletenessTier, set[str]] = {
	CompletenessTier.HIGH: {"EG", "GH", "KE", "MA", "NG", "ZA"},
	CompletenessTier.MEDIUM: {
		"AO", "BF", "BJ", "BW", "CD", "CG", "CI", "CM", "DZ", "ET", "GA", "GM",
		"GN", "LR", "LS", "LY", "MG", "ML", "MU", "MW", "MZ", "NA", "NE", "RW",
		"SD", "SL", "SN", "SZ", "TG", "TN", "TZ", "UG", "ZM", "ZW",
	},
	CompletenessTier.LOW: {"CF", "EH", "ER", "GQ", "GW", "SO", "SS", "TD"},
	CompletenessTier.CRITICAL: {"BI", "CV", "DJ", "KM", "MR", "SC", "ST"},
}


def test_registry_covers_all_au_members():
	"""``len(registry) == 55``, and every code is distinct.

	The count is `_build`'s own invariant and raises rather than returning a
	short registry, so this asserts the number a caller sees as well.
	"""
	assert len(registry()) == AU_MEMBER_STATE_COUNT == 55
	assert len({c.iso3 for c in registry().values()}) == 55, "two countries share an ISO3"
	assert len({c.name for c in registry().values()}) == 55, "two countries share a name"


def test_registry_tier_counts_match_tables():
	"""The plan's §3.1 table, by membership and by count.

	Both, because they fail differently: a membership assertion says *which*
	country moved and a count assertion says the table is the right size. A
	tier that gained one country and lost another satisfies the count alone.
	"""
	for tier, expected in EXPECTED_TIERS.items():
		actual = {c.iso2 for c in by_tier(tier)}
		assert actual == expected, (
			f"{tier.value}: missing {sorted(expected - actual)}, "
			f"unexpected {sorted(actual - expected)}"
		)
		assert tier_counts()[tier] == len(expected), (
			f"{tier.value} counts {tier_counts()[tier]}, the table holds {len(expected)}"
		)
	assert sum(tier_counts().values()) == AU_MEMBER_STATE_COUNT


def test_the_tier_sets_partition_the_registry():
	"""Every country is in exactly one tier, and the tiers are the four of §3.2."""
	union: set[str] = set()
	for tier in CompletenessTier:
		codes = {c.iso2 for c in by_tier(tier)}
		assert not (union & codes), f"{tier.value} overlaps another tier: {sorted(union & codes)}"
		union |= codes
	assert union == set(registry()), (
		f"the tiers do not cover the registry: {sorted(set(registry()) - union)}"
	)


def test_every_country_has_a_power_pool():
	"""`power_pool` is never unset, and `none` is a decision with a reason.

	The field is a non-optional enum, so "unset" is not reachable through the
	model -- but ``none`` is, and it is the value that means *nothing* rather
	than *not recorded*. §3.3 names the case: the Sahrawi Arab Democratic
	Republic is ``none`` "with a note". The note is the gate, because a country
	with no pool and no reason is a country the continental model silently
	drops.
	"""
	for country in registry().values():
		assert isinstance(country.power_pool, PowerPool), (
			f"{country.iso2} has no power pool"
		)
		if country.power_pool is PowerPool.NONE:
			assert country.notes, (
				f"{country.iso2} is in no power pool and carries no note saying why"
			)
	# The three island and disputed cases, named so a fourth has to be argued
	# for rather than appearing.
	assert {c.iso2 for c in by_power_pool(PowerPool.NONE)} == {"KM", "SC", "EH"}, (
		"the set of countries in no power pool changed; each is an island grid or "
		"a disputed territory, and a new one is a modelling decision"
	)


def test_every_pool_holds_the_countries_its_membership_lists():
	"""The five pools partition the pool-carrying countries, and none is empty.

	An empty pool is a regional model with no members, which reads as a pool
	the platform supports and is a pool it cannot build.
	"""
	for pool in (PowerPool.COMELEC, PowerPool.WAPP, PowerPool.CAPP, PowerPool.EAPP, PowerPool.SAPP):
		members = by_power_pool(pool)
		assert members, f"{pool.value} holds no country"
		assert members == sorted(members, key=lambda c: c.iso2), "by_power_pool is not sorted"
	pooled = sum(
		len(by_power_pool(p))
		for p in (
			PowerPool.COMELEC,
			PowerPool.WAPP,
			PowerPool.CAPP,
			PowerPool.EAPP,
			PowerPool.SAPP,
		)
	)
	assert pooled + len(by_power_pool(PowerPool.NONE)) == AU_MEMBER_STATE_COUNT, (
		"the pools and the unpooled countries do not partition the registry"
	)


def test_proxy_countries_are_exactly_the_critical_tier():
	"""AD-6: the seven countries absent from the continental datasets.

	`needs_proxy_data` is what routes a value to ``basis='proxy'`` all the way
	to a report, so the set it selects and the CRITICAL tier must be the same
	set -- two ways of naming one thing, and a country that is CRITICAL but not
	flagged is a proxy value published as measured.
	"""
	proxy = proxy_countries()
	assert len(proxy) == 7, f"§3.1 names seven proxy countries, found {len(proxy)}"
	assert {c.iso2 for c in proxy} == {c.iso2 for c in by_tier(CompletenessTier.CRITICAL)}
	assert all(c.needs_proxy_data for c in proxy)
	assert not any(c.needs_proxy_data for c in registry().values() if c not in proxy)


def test_an_unknown_country_code_is_refused_not_defaulted():
	"""A silent default routes a signal into the wrong national model."""
	with pytest.raises(KeyError, match="not a registered AU member state"):
		get_country("XX")
	with pytest.raises(KeyError):
		get_country("")
	# Lower case is a spelling, not a different country.
	assert get_country("ke").iso2 == "KE"
