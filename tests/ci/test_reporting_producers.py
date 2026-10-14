# SPDX-License-Identifier: MIT
"""Every declared report section is produced by something, or is a named gap.

The Layer 8 defect one layer up. `alea.publish.views` holds four registers and a
bidirectional gate over its eleven serving tables, so a serving table with no
producer is a recorded fact. Layer 6 declared 31 sections across five cadences
and held no register at all, and the render tests pass anyway -- because
`tests/fixtures/reporting` writes every declared path by hand. A fixture that
manufactures a section's input cannot see that no layer produces it: the section
renders perfectly in CI and warns "no artefact at ..." in production.

These tests are the gate for the class, not for one section. The first asserts
the register covers every declared slug and nothing else, so a section that
gains a producer must move between the two mappings in the same change.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED, UNPROJECTED
from alea.reporting.schemas import ReportCadence
from alea.reporting.service import cadence_specs

REPO = Path(__file__).resolve().parents[2]


def _declared_slugs() -> set[str]:
	"""Every section slug the five cadence modules declare."""
	slugs: set[str] = set()
	for cadence in ReportCadence:
		specs, _ = cadence_specs(cadence)
		slugs.update(spec.slug for spec in specs)
	return slugs


def test_the_two_registers_partition_the_declared_sections():
	"""Produced and unproduced are disjoint, and together are the whole set.

	The bidirectional half. A section that gains a producer must leave
	``UNPRODUCED`` and enter ``PRODUCERS``; one that loses a producer moves the
	other way. If only one moved, the register would overstate or understate the
	gap and this fails.
	"""
	declared = _declared_slugs()
	recorded = set(PRODUCERS) | set(UNPRODUCED)

	unrecorded = sorted(declared - recorded)
	assert not unrecorded, (
		f"{len(unrecorded)} declared report section(s) are in no register: "
		f"{unrecorded}. A section nothing produces renders in CI (the fixture "
		f"writes its path by hand) and warns 'no artefact' in production, which "
		f"is indistinguishable from a working section until a report is "
		f"generated from the pipeline. Record it in `UNPRODUCED` with the "
		f"measured blocker, or produce it and record it in `PRODUCERS`."
	)

	stale = sorted(recorded - declared)
	assert not stale, (
		f"the register names {len(stale)} section(s) no cadence declares: "
		f"{stale}. A renamed or removed section leaves a stale entry that makes "
		f"the gap look larger than it is."
	)

	overlap = sorted(set(PRODUCERS) & set(UNPRODUCED))
	assert not overlap, (
		f"{overlap} are recorded as both produced and unproduced; the two "
		f"registers must partition the set"
	)


def test_every_unproduced_section_names_a_blocker():
	"""An unproduced section with no reason is an omission in a register's clothes."""
	for slug, reason in UNPRODUCED.items():
		assert reason.strip(), f"{slug!r} has no recorded blocker"
		assert len(reason) > 80, (
			f"{slug!r} has a reason too short to name a blocker: {reason!r}. "
			f"'needs a rule' and 'needs a model that does not exist' are "
			f"different amounts of work, and the register's job is to say which."
		)


def test_every_producer_names_something_that_exists():
	"""A producer name is a claim, and the claim is checkable.

	Reads the source text rather than importing, because the point is to catch a
	name that no module defines -- importing the module it claims to live in
	would only tell us the module parses.
	"""
	source = "\n".join(
		path.read_text(encoding="utf-8")
		for path in (REPO / "src" / "alea").rglob("*.py")
	)
	for slug, producer in PRODUCERS.items():
		assert producer.strip(), f"{slug!r} names an empty producer"
		# The producer is spelled `module.function` or a bare function name.
		leaf = producer.rsplit(".", 1)[-1]
		assert re.search(rf"\bdef {re.escape(leaf)}\b", source), (
			f"{slug!r} names the producer {producer!r}, and no module in "
			f"`src/alea` defines `{leaf}`. A producer that does not exist is a "
			f"gap wearing a register's clothes."
		)


def _call_sites(name: str) -> int:
	"""Call-shaped references to ``name`` in `src/alea`, outside its own definition.

	A function the register names as the *missing piece* of a gap is not the
	same as one that is wired: `clear_scenario` is defined, exported and called
	by nothing but its own tests, so "the producer is a rule over a cleared
	scenario" named a thing that does not happen.

	Counting *mentions* would not measure that -- the name appears in `__all__`
	and in `logger.info("clear_scenario", ...)` event labels, and a logger's
	event name is not a call. So this counts lines where the name is followed by
	an open paren and is not the definition or the class statement: the shape a
	call or a construction has.
	"""
	pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
	count = 0
	for path in (REPO / "src" / "alea").rglob("*.py"):
		for line in path.read_text(encoding="utf-8").splitlines():
			if line.lstrip().startswith(("def ", "class ")):
				continue
			if pattern.search(line):
				count += 1
	return count


def test_the_market_entries_named_a_piece_that_has_now_arrived():
	"""The claim these entries made was checkable, and it has been discharged.

	The `market_report` entry said the missing piece was *the fleet*, not the
	rule: "no module builds a market fleet from a solved network, so
	`clear_scenario` has no caller and `BiddingUnit` is constructed nowhere
	outside tests". That was measured, and it was right. `market/fleet.py` is
	that module now and `market/stages.py` runs it, so the count moved -- and
	the move is the prompt this gate exists to give.

	The two assertions below are the *inverse* of the ones they replace. Before,
	they pinned zero call sites and the entry's prose; a fleet builder is
	exactly what makes them non-zero, so pinning zero now would fail on the
	shipped tree. What they check instead is that the piece is genuinely wired
	and not merely written: a `BiddingUnit` constructed in a module no stage
	imports is the same defect one level down, and `build_fleet_series` having a
	caller in `market/service.py` is what distinguishes the two.

	This pins the measurement, not the wording. When the *next* entry's blocker
	is closed, this fails again, which is the prompt to rewrite it -- the same
	discipline as the required-section map.
	"""
	assert "market_report" not in UNPRODUCED, (
		"`market_report` is back in `UNPRODUCED` after being produced; a section "
		"that lost its producer is a cadence that can no longer be generated, and "
		"this gate must say which piece went missing again rather than passing"
	)
	assert _call_sites("BiddingUnit") > 0, (
		"no module in `src/alea` constructs a `BiddingUnit`, so the market fleet "
		"the entries named as the missing piece is not being built -- and the two "
		"slugs in `PRODUCERS` would be naming a producer that reads an empty fleet"
	)
	assert _call_sites("build_fleet_series") > 0, (
		"`build_fleet_series` has no caller in `src/alea`, so `market/fleet.py` "
		"exists and nothing runs it. The monthly and quarterly producers clear "
		"`build_fleet_series`'s output; a fleet module with no caller is the "
		"written-but-unwired shape this register exists to tell apart from a "
		"produced section"
	)


def test_the_projected_registers_partition_the_produced_sections():
	"""Produced is not delivered, and the second pair of registers says which.

	``PRODUCERS`` names the function that computes a section's rows; every stage
	writes ``data/processed/`` and every section reads
	``results/<dir>/{date}.parquet``. Naming a producer therefore says nothing
	about whether a report can open the section -- which is exactly what was
	measured: `capacity_update` was in ``PRODUCERS``, its rule exited 0, and
	`alea report monthly` exited 1 with ``ReportDataError: no artefact``.

	So the produced set is partitioned again, and the partition is the gate. A
	slug in neither register is a produced section nobody has asked the delivery
	question about; a slug in both is a claim that contradicts itself; a
	``PROJECTED`` entry whose rule no rule file declares is the original defect
	restated one level down -- the register says a projection exists and nothing
	runs it.
	"""
	unrecorded = sorted(set(PRODUCERS) - set(PROJECTED) - set(UNPROJECTED))
	assert not unrecorded, (
		f"{unrecorded} are recorded as produced and in neither projection "
		f"register. `PRODUCERS` names the function that writes the rows; the "
		f"section reads a dated path under `results/`, and until a rule lands the "
		f"artefact there the section is absent at report time. Add the rule and "
		f"record it in `PROJECTED`, or record the blocker in `UNPROJECTED`."
	)
	stale = sorted((set(PROJECTED) | set(UNPROJECTED)) - set(PRODUCERS))
	assert not stale, (
		f"{stale} are in a projection register and in no `PRODUCERS` entry. An "
		f"unproduced section has no artefact to project, so this is an entry that "
		f"outlived its producer."
	)
	overlap = sorted(set(PROJECTED) & set(UNPROJECTED))
	assert not overlap, (
		f"{overlap} are recorded as both projected and unprojected; the two "
		f"registers must partition the produced set"
	)
	for slug, reason in UNPROJECTED.items():
		assert len(reason) > 80, (
			f"{slug!r} has a reason too short to name what closes it: {reason!r}"
		)


def test_every_projected_section_has_a_rule_and_a_dvc_stage():
	"""A projection recorded as delivered must be one the workflows run.

	The canary-shaped half of the register: the source text is what is checked,
	so a ``PROJECTED`` entry naming a rule that was renamed, deleted, or never
	written fails here rather than at the next report run. Both workflow files,
	because `snakemake` and `dvc repro` are two ways to build the same pipeline
	and a projection in only one of them is a delivery that happens under one
	and not the other.
	"""
	rules_text = "\n".join(
		path.read_text(encoding="utf-8")
		for path in sorted((REPO / "rules").glob("*.smk"))
	)
	declared_rules = set(
		re.findall(r"^rule\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", rules_text, re.MULTILINE)
	)
	dvc_stages = set(
		yaml.safe_load((REPO / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
	)
	for slug, rule in PROJECTED.items():
		assert rule in declared_rules, (
			f"{slug!r} is recorded as projected by `{rule}`, and no `.smk` file "
			f"declares that rule. `PROJECTED` means a workflow rule lands the "
			f"section's dated artefact; a name with no rule behind it is the "
			f"original defect -- a function that exists and nothing that runs it"
		)
		assert rule in dvc_stages, (
			f"{slug!r} is projected by `{rule}` under Snakemake, and `dvc.yaml` "
			f"has no such stage -- so `dvc repro` builds a pipeline in which the "
			f"section is never delivered"
		)


#: The required section each cadence cannot generate without, while it has no
#: producer. Pinned rather than derived, because the derived form -- intersect
#: the required set with `UNPRODUCED` -- is a tautology: every slug in it is in
#: `UNPRODUCED` by construction, so the assertion cannot fail and would keep
#: passing if a cadence gained a second unproduced required section or lost its
#: only one. The map is what makes closing a gap, or opening one, move a test.
REQUIRED_WITHOUT_A_PRODUCER: dict[str, str] = {
	"annual": "continental_outlook",
}
"""One per cadence that cannot be generated from the pipeline, and that is the
measured state: one of the five cadences has a required section with no
producer. The map started with all five, lost the monthly and quarterly sections
in one change -- their shared blocker was the market fleet -- lost the weekly one
when `planning/balance.py` produced its outlook, and lost the daily one when
`outages.service._stage_outage_forecast` predicted forward and banded the
result.

A cadence whose required section *has* a producer is absent from this map rather
than mapped to `None`: the assertion below compares against `.get(cadence)`, so
absence is the state that means "generatable", and an entry saying so would be a
second way to spell the same thing."""


def test_the_prose_count_of_unproduced_required_sections_matches_the_mapping():
	"""The register's docstring states a count, and the count must be the set's.

	`UNPRODUCED`'s docstring said "Two of the five are unproduced, so two
	cadences -- daily and annual" while `week_ahead` sat in the mapping three
	lines below it: the true count was three, and the sentence named two. Nothing
	caught it, because `test_a_required_section_with_no_producer_is_recorded`
	pins *which* section belongs to each cadence and never reads the number the
	prose reports -- so the summary was free to describe a set it did not match.

	This is the module's own lesson applied to itself. Its docstring already
	warns that "the prose is a *summary of this set*, and a summary that is not
	checked drifts"; the drift then happened in the sentence making the warning.
	The count is derived here rather than restated, and the weekly gap is the
	proof: closing it edited the sentence's number in the same change, which is
	the gate doing the job it was written for rather than a later reader finding
	a stale figure.

	The source is read as *text*, not through `UNPRODUCED.__doc__`: the sentence
	lives in a string literal that follows the assignment rather than being the
	module's first statement, so it is a bare expression with no runtime
	accessor. Reading the file is also what the sibling gates over
	`rules/reporting.smk` and `dvc.yaml` do, for the same reason -- the artefact
	the claim is written in is the thing to check.
	"""
	source = (REPO / "src" / "alea" / "reporting" / "producers.py").read_text()
	# ``are|is``, because the count is now one and the sentence had to become
	# singular with it. A pattern written only for the plural would have stopped
	# matching the moment the register shrank past one -- and a gate that stops
	# matching fails loudly here (the `assert stated` below), which is the right
	# failure, but the pattern should carry both forms rather than force a
	# sentence to stay ungrammatical to stay checked.
	stated = re.search(r"(\w+) of the five (?:are|is) unproduced", source)
	assert stated, (
		"the docstring no longer states an unproduced count in the form this gate "
		"reads; if the sentence was reworded, reword this pattern with it rather "
		"than deleting the gate -- an unchecked summary is how the count was "
		"wrong by one"
	)

	words = {
		"one": 1,
		"two": 2,
		"three": 3,
		"four": 4,
		"five": 5,
	}
	claim = words.get(stated.group(1).lower())
	assert claim is not None, f"unreadable count word {stated.group(1)!r}"

	required = {
		spec.slug
		for cadence in ReportCadence
		for spec in cadence_specs(cadence)[0]
		if spec.required
	}
	measured = required & set(UNPRODUCED)
	assert claim == len(measured), (
		f"the docstring says {claim} of the five required sections are unproduced "
		f"({stated.group(0)!r}); the register holds {len(measured)} ({sorted(measured)}). "
		f"The prose is a summary of the mapping below it, and a summary that is "
		f"not checked drifts -- which is how this sentence came to name two "
		f"cadences while the mapping held three"
	)


@pytest.mark.parametrize("cadence", list(ReportCadence), ids=lambda c: c.value)
def test_each_cadence_declares_exactly_one_required_section(cadence: ReportCadence):
	"""The structural fact the register's prose paraphrases, pinned as a check.

	`UNPRODUCED`'s module docstring said "Four sections are `required=True`" and
	named four, dropping the daily cadence's `outage_forecast` -- so it also said
	"four of the five cadences cannot be generated" where the measured state is
	five of five. The prose is a *summary of this set*, and a summary that is not
	checked drifts the way that one did. This pins the shape the summary rests
	on: exactly one required section per cadence, so "one per cadence" is a fact
	a reader can rely on and the count is `len(ReportCadence)`, not a number
	someone retypes.
	"""
	specs, _ = cadence_specs(cadence)
	required = [spec.slug for spec in specs if spec.required]
	assert len(required) == 1, (
		f"{cadence.value} declares {len(required)} required sections ({required}); "
		f"the register's summary and the pinned required-section map both assume "
		f"exactly one per cadence. A cadence with two is a cadence whose "
		f"generatability depends on both, and a cadence with none is one the "
		f"summary overstates."
	)


@pytest.mark.parametrize("cadence", list(ReportCadence), ids=lambda c: c.value)
def test_a_required_section_with_no_producer_is_recorded(cadence: ReportCadence):
	"""A required section that is absent raises; that must not be a surprise.

	A required section's artefact being missing is a hard `ReportDataError`, not
	a warning -- so a cadence whose required section has no producer cannot be
	generated from the pipeline at all. The pinned map states which section that
	is per cadence, so this fails when the set changes in either direction: a
	cadence that gains a second unproduced required section is a cadence further
	from generating, and one that gains a producer is a line to delete.
	"""
	specs, _ = cadence_specs(cadence)
	required = {spec.slug for spec in specs if spec.required}
	unproduced = sorted(required & set(UNPRODUCED))

	expected = REQUIRED_WITHOUT_A_PRODUCER.get(cadence.value)
	assert unproduced == ([expected] if expected else []), (
		f"{cadence.value}'s required-and-unproduced set is {unproduced}, and the "
		f"pinned register says {expected!r}. A section that gained a producer "
		f"moves out of `UNPRODUCED` and this map must drop it; a required section "
		f"that lost its producer is a cadence that can no longer be generated, "
		f"and the map must gain it."
	)

#: The shapes a blocker uses to say a source is not there. Regexes rather than
#: substrings, because the natural phrasings put words in between: "no climate
#: projection source exists" does not contain the substring "no source", and a
#: substring list is a subset predicate -- it matches some of the ways to write
#: the denial and passes over the rest. The canary
#: `test_source_claim_gates.py` plants exactly that phrasing, and the first
#: draft of this list let it through.
_ABSENCE_PATTERNS = (
	re.compile(r"\bno\b[^.]{0,40}?\bsources?\b", re.IGNORECASE),
	re.compile(r"\bholds no\b", re.IGNORECASE),
	re.compile(r"\bnot registered\b", re.IGNORECASE),
	re.compile(r"\bregistered nowhere\b", re.IGNORECASE),
)

#: Source ids whose fetcher is deliberately absent, each with the reason the
#: blocker may therefore say so. Mirrors `UNIMPLEMENTED_FETCHERS` in
#: `tests/ci/test_io_registry.py`, which is the register for this fact.
UNFETCHED_SOURCES = frozenset({"era5_cutout", "gridwatch", "viirs_vnp46a2"})


def test_no_blocker_claims_a_source_is_absent_when_the_register_holds_it():
	"""A blocker that denies a source exists is a claim the source register refutes.

	**The defect, measured.** `climate_scenarios` recorded "the register holds
	no climate projection source". `cmip6` is registered, its declared
	``target`` is ``climate_scenarios`` itself, and `alea.io.fetchers` carries a
	working fetcher for it -- so the entry sent the next reader to look for a
	source that was already there, and the real gap (naming a dataset per
	scenario, downloading it, downscaling it, re-solving) went unrecorded. It is
	the fourth entry this arc has found naming the wrong missing thing, after
	`investment_pipeline`, `outage_events` and `renewable_forecast`.

	**Why the check is keyed on the source's own ``target``.** The first draft
	looked for a registered source id spelled in the blocker and skipped any
	blocker that named none -- which is every blocker that *denies* a source
	exists, including the one this gate was written for. A gate whose trigger is
	the defect's own wording passes over the defect. The register already
	carries the link: a ``Source``'s ``target`` names the artefact or stage it
	feeds, and ``cmip6``'s is literally this slug. So the check is "does a
	registered source declare this section as its target", which no wording can
	evade, and the phrase list only decides whether the blocker *contradicts*
	it.

	**What is deliberately not checked.** A blocker may say "no fetcher" of a
	source that is registered and unfetched -- `era5_cutout` and
	`viirs_vnp46a2` are exactly that, and both entries are true. Only the two
	denials the register can settle are gated: that a source is absent, and that
	a source with a *registered* fetcher has none. The general prose -- "no
	switching solver exists" -- stays unchecked, because a keyword search over
	it would be a proof-shaped guess and this module has already been wrong once
	by trusting a claim it could have measured.
	"""
	from alea.io.sources import registered_fetchers, sources

	register = sources()
	fetched = set(registered_fetchers())
	targeting: dict[str, list[str]] = {}
	for source_id, source in register.items():
		targeting.setdefault(source.target, []).append(source_id)

	for slug, reason in UNPRODUCED.items():
		named = sorted(targeting.get(slug, ()))
		if not named:
			continue
		denials = [pattern.pattern for pattern in _ABSENCE_PATTERNS if pattern.search(reason)]
		assert not denials, (
			f"{slug!r}'s blocker says {denials}, and {named} declare "
			f"{slug!r} as their ``target`` in `alea.io.sources`. The sentence "
			f"sends the next reader to look for a source that is already there, "
			f"which is how this entry came to deny a climate projection source "
			f"while `cmip6` sat in the register with a working fetcher. Name what "
			f"is actually missing -- the model, the stage, the rule: {reason!r}"
		)
		unfetched = sorted(source_id for source_id in named if source_id in fetched)
		if not unfetched:
			continue
		assert "no fetcher" not in reason, (
			f"{slug!r}'s blocker says 'no fetcher' while `registered_fetchers()` "
			f"holds one for {unfetched}. A source with a fetcher is not the "
			f"blocker; name the stage or the model that is: {reason!r}"
		)


def test_the_unfetched_source_register_matches_the_io_registry():
	"""One list of unfetched sources, not two that agree today.

	`UNFETCHED_SOURCES` above exists so a blocker may say "no fetcher" of a
	source that has none. The authoritative list is `tests/ci/test_io_registry.py`'s
	``UNIMPLEMENTED_FETCHERS``, which asserts itself against the register; this
	pins the copy here to it, so a source that gains a fetcher cannot leave this
	file permitting a sentence that is no longer true.
	"""
	from tests.ci.test_io_registry import UNIMPLEMENTED_FETCHERS

	assert set(UNFETCHED_SOURCES) == set(UNIMPLEMENTED_FETCHERS), (
		"this file's unfetched-source set is "
		f"{sorted(UNFETCHED_SOURCES)} and `test_io_registry.py` holds "
		f"{sorted(UNIMPLEMENTED_FETCHERS)}; the two must be one list, or a "
		f"blocker may keep saying 'no fetcher' of a source that has one"
	)
