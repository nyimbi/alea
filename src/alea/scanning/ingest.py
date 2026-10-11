# SPDX-License-Identifier: MIT
"""Ingestion: two-level deduplication and raw-text retention (10-layer7 §4).

Two levels, because they catch different things and have different costs:

1. **Exact** — the document identity hash. Free, and prevents reprocessing the
   same document, which is what makes a re-run idempotent.
2. **Near-duplicate** — MinHash/LSH over ordered word shingles, via the Rust
   kernel. This is the expensive one and it detects the same *event* reported
   by several outlets, which is the normal case for an energy announcement.

Two specification defects are corrected here rather than reproduced:

* The spec's ``MinHash`` has no seed, so Python's per-process randomised string
  hash makes yesterday's duplicate set differ from today's (AD-8). The seed is
  required and comes from ``scanning.dedup_seed``.
* The spec shingles into a ``set``, whose iteration order is arbitrary. Shingles
  here are a generator over an ordered token sequence, so the signature is a
  function of the text and nothing else.

Keeping the best document is a rule, not a judgement call: longest text, then
most entity-bearing tokens, then earliest publication, then lowest
``document_id``. The last term is not in the specification and is there because
without it two documents that tie on the first three are ordered by whatever
order the fetch happened to produce, which is the AD-8 failure class again.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from alea._core.kernels import deduplicate
from alea.config.paths import resolve
from alea.io.artefacts import utcnow
from alea.logging import get_logger
from alea.scanning.connectors.base import RawDocument
from alea.scanning.views import DedupGroup, DedupReport, IngestionReport, RetentionReport

logger = get_logger(__name__)

#: Word-shingle width. Five is the specification's value and the value the
#: kernel's differential tests use; changing it changes the duplicate set.
SHINGLE_K = 5

#: Coarse entity pattern used only as a deduplication tiebreak. It is
#: deliberately not the extractor's patterns: importing extraction here would
#: make ingestion depend on extraction, and the tiebreak would then change
#: whenever an extractor rule changed, silently reordering which document of a
#: duplicate group is kept.
_ENTITY_PATTERN = re.compile(
	r"""
	\d[\d,.]*\s*(?:MW|GW|kW|MWh|GWh|kWh|MWp|GWh/a)   # capacity or energy
	| (?:USD|US\$|\$|EUR|€|KES|NGN|ZAR|GHS|EGP|MAD)\s?\d[\d,.]*   # money
	| \b[A-Z]{2}\b                                     # a country code
	| \d{4}-\d{2}-\d{2}                                # an ISO date
	| \b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|
		September|October|November|December)\s+\d{4}\b
	""",
	re.VERBOSE,
)

#: Tokens that carry no discriminative information for shingling.
#: Removing them before shingling is what makes "the 100 MW plant in Kenya"
#: and "a 100 MW plant in Kenya" the same shingle set.
_STOPWORDS = frozenset(
	["a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for", "from", "with", "by", "as", "is", "are", "was", "were", "be", "been", "this", "that", "these", "those", "it", "its", "has", "have", "had", "will", "would", "could", "should", "says", "said"]
)


def shingles(text: str, k: int = SHINGLE_K) -> Iterator[str]:
	"""Ordered word shingles.

	A generator, never a set: ``set`` iteration order varies between processes
	for strings, and the MinHash permutation depends on the order the shingles
	are hashed. The gate ``test_shingles_ordered`` exists because a set here
	produces a signature that is not a function of the text alone.

	Fewer than ``k`` tokens yields nothing rather than a padded shingle: a
	one-word document has no shingle, and inventing one would make every short
	document a near-duplicate of every other.
	"""
	assert k >= 1, f"shingle width must be positive, got {k}"
	tokens = [t for t in re.split(r"\W+", text.lower()) if t and t not in _STOPWORDS]
	for i in range(len(tokens) - k + 1):
		yield " ".join(tokens[i : i + k])


def shingle_count(text: str, k: int = SHINGLE_K) -> int:
	"""How many shingles a text produces, without materialising them."""
	return sum(1 for _ in shingles(text, k))


def entity_count(text: str) -> int:
	"""How many entity-bearing tokens a text contains.

	The second term of the detail rule. Cheap, deterministic, and independent of
	whether extraction has run.
	"""
	return len(_ENTITY_PATTERN.findall(text))


def detail_key(document: RawDocument) -> tuple[int, int, float, str]:
	"""The rule that picks the document kept from a duplicate group.

	Longest text, then most entities, then earliest publication, then lowest
	document id. Returned as a tuple so ``max`` and ``min`` agree with it by
	construction; the id term is inverted through ``_sort_key`` below, which is
	why this returns positive quantities for the first three.
	"""
	assert document.document_id, "a document without an identity cannot be ranked"
	return (
		len(document.text),
		entity_count(document.text),
		-(
			document.published_at.timestamp()
			if document.published_at is not None
			# An undated document sorts as if published now: it is neither
			# preferred nor discarded on the strength of a missing field.
			else float("inf")
		),
		document.document_id,
	)


def _best(documents: list[RawDocument]) -> RawDocument:
	"""The document the detail rule keeps.

	``max`` over ``detail_key`` prefers the longest text and then the most
	entities. The publication term is negated so an *earlier* publication wins,
	and the id term is a plain string so the lowest id wins a total tie —
	which is the only term that makes the choice deterministic when the
	documents are otherwise indistinguishable.
	"""
	assert documents, "cannot choose from an empty group"
	ranked = max(documents, key=detail_key)
	# Tie-break on the id alone, because ``max`` returns the first maximal
	# element in input order and input order is not deterministic across runs.
	best_key = detail_key(ranked)
	ties = [d for d in documents if detail_key(d) == best_key]
	return min(ties, key=lambda d: d.document_id)


def exact_deduplicate(documents: Iterable[RawDocument]) -> tuple[list[RawDocument], int]:
	"""Remove documents already seen in this batch by identity.

	Returns the survivors in input order and the number removed. Identity is
	``document_id`` (source, url, title, published); two outlets carrying the
	same wire copy share a ``content_hash`` but are *near* duplicates, and
	collapsing them here would lose the corroboration count.
	"""
	seen: set[str] = set()
	survivors: list[RawDocument] = []
	removed = 0
	for document in documents:
		if document.document_id in seen:
			removed += 1
			continue
		seen.add(document.document_id)
		survivors.append(document)
	return survivors, removed


def near_duplicate_groups(
	documents: list[RawDocument],
	*,
	k: int = SHINGLE_K,
	num_perm: int = 128,
	threshold: float = 0.7,
	seed: int = 0,
) -> list[list[RawDocument]]:
	"""Group near-duplicates using the Rust kernel.

	Input is sorted by ``document_id`` before the call. The kernel's grouping is
	a function of its input order, and the fetch order of a batch of feeds is
	not reproducible — so without this sort, two processes ingesting the same
	corpus in different orders would produce different groups, which is exactly
	the determinism the gate asserts.

	Documents with no shingle (too short) are each their own group: they cannot
	be compared, and the kernel is not given a chance to merge them by accident.
	"""
	assert threshold > 0.0 and threshold < 1.0, f"threshold must be in (0,1), got {threshold}"
	assert num_perm > 0
	ordered = sorted(documents, key=lambda d: d.document_id)
	by_id = {d.document_id: d for d in ordered}
	comparable = [d for d in ordered if shingle_count(d.text, k) > 0]
	trivial = [d for d in ordered if shingle_count(d.text, k) == 0]

	groups: list[list[RawDocument]] = []
	if comparable:
		raw_groups = deduplicate(
			[(d.document_id, d.text) for d in comparable],
			k,
			num_perm,
			threshold,
			seed,
		)
		for group in raw_groups:
			groups.append([by_id[doc_id] for doc_id in group])
	groups.extend([d] for d in trivial)
	return groups


def deduplicate_documents(
	documents: list[RawDocument],
	*,
	k: int = SHINGLE_K,
	num_perm: int = 128,
	threshold: float = 0.7,
	seed: int = 0,
) -> tuple[list[RawDocument], DedupReport]:
	"""Two-level deduplication. Returns the kept documents and a report.

	The report carries the corroboration structure, which the scoring stage
	consumes and the reviewer reads: a signal carried by four outlets is a
	different signal from one carried by one, and the difference is only visible
	if the group membership is recorded rather than discarded.
	"""
	assert documents, "nothing to deduplicate"
	survivors, exact_removed = exact_deduplicate(documents)
	groups = near_duplicate_groups(
		survivors, k=k, num_perm=num_perm, threshold=threshold, seed=seed
	)

	kept: list[RawDocument] = []
	report_groups: list[DedupGroup] = []
	near_duplicates = 0
	for group in groups:
		representative = _best(group)
		others = sorted(
			d.document_id for d in group if d.document_id != representative.document_id
		)
		near_duplicates += len(others)
		kept.append(representative)
		report_groups.append(
			DedupGroup(
				group_id=representative.document_id,
				representative_id=representative.document_id,
				member_ids=sorted(d.document_id for d in group),
				corroborating_ids=others,
			)
		)

	# Kept documents are returned in a deterministic order for the same reason
	# the kernel input is sorted: a downstream stage that iterates them must
	# produce the same artefacts on two runs.
	kept.sort(key=lambda d: d.document_id)
	report_groups.sort(key=lambda g: g.group_id)
	report = DedupReport(
		input_count=len(documents),
		exact_duplicates=exact_removed,
		near_duplicates=near_duplicates,
		groups=report_groups,
		kept_ids=[d.document_id for d in kept],
		seed=seed,
		threshold=threshold,
	)
	logger.info(
		"deduplicated",
		input=len(documents),
		exact=exact_removed,
		near=near_duplicates,
		kept=len(kept),
		seed=seed,
	)
	return kept, report


def ingest(
	documents: list[RawDocument],
	*,
	k: int = SHINGLE_K,
	num_perm: int = 128,
	threshold: float = 0.7,
	seed: int = 0,
	connector_health: list[dict[str, object]] | None = None,
) -> tuple[list[RawDocument], IngestionReport, DedupReport]:
	"""The ingestion stage: deduplicate and summarise.

	Returns the kept documents, a run summary, and the deduplication report.
	The dedup report is returned rather than discarded because its groups are
	the corroboration structure the scoring stage needs — recomputing them
	downstream would be a second call to the kernel whose result could differ
	if the seed ever diverged, which is the failure the seed exists to prevent.

	Health travels with the ingestion report because "we found nothing today"
	and "the scraper broke last Tuesday" are the same observation until the
	health record separates them.
	"""
	kept, dedup = deduplicate_documents(
		documents, k=k, num_perm=num_perm, threshold=threshold, seed=seed
	)
	source_counts: dict[str, int] = {}
	for document in kept:
		source_counts[document.source_name] = source_counts.get(document.source_name, 0) + 1
	report = IngestionReport(
		input_count=dedup.input_count,
		exact_duplicates=dedup.exact_duplicates,
		near_duplicates=dedup.near_duplicates,
		kept_count=dedup.kept_count,
		source_counts=dict(sorted(source_counts.items())),
		connector_health=list(connector_health or []),
	)
	return kept, report, dedup


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------


def _retrieved_at(directory: Path) -> datetime | None:
	"""When a raw payload was retrieved, from its provenance sidecar.

	The sidecar's ``retrieved_at`` is authoritative; the file mtime is a
	fallback for a payload whose sidecar is unreadable. Age is measured from
	retrieval, not from publication: a 2019 gazette fetched yesterday is a new
	retrieval and its retention clock starts yesterday.
	"""
	sidecar = directory / "provenance.json"
	if sidecar.exists():
		try:
			record = json.loads(sidecar.read_text(encoding="utf-8"))
			value = record.get("retrieved_at")
			if value:
				parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
				return parsed if parsed.tzinfo is not None else None
		except (json.JSONDecodeError, ValueError):
			pass
	try:
		return datetime.fromtimestamp(directory.stat().st_mtime, tz=utcnow().tzinfo)
	except OSError:
		return None


def expired_raw_payloads(
	root: str | Path = "data/raw",
	*,
	retention_days: int = 90,
	now: datetime | None = None,
	source_ids: list[str] | None = None,
) -> list[tuple[str, str, Path, int]]:
	"""Raw payload directories past their retention limit.

	Returns ``(source_id, checksum, directory, bytes)`` for each expired
	payload, sorted, so a purge is deterministic and its report is reproducible.
	"""
	assert retention_days >= 1, "a retention policy of zero days would purge the run's own fetches"
	base = resolve(root)
	if not base.exists():
		return []
	moment = now or utcnow()
	cutoff = moment - timedelta(days=retention_days)
	out: list[tuple[str, str, Path, int]] = []
	for source_dir in sorted(p for p in base.iterdir() if p.is_dir()):
		if source_ids is not None and source_dir.name not in source_ids:
			continue
		for checksum_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
			retrieved = _retrieved_at(checksum_dir)
			if retrieved is None or retrieved >= cutoff:
				continue
			size = sum(f.stat().st_size for f in checksum_dir.rglob("*") if f.is_file())
			out.append((source_dir.name, checksum_dir.name, checksum_dir, size))
	return out


def purge_expired_raw(
	root: str | Path = "data/raw",
	*,
	retention_days: int = 90,
	now: datetime | None = None,
	source_ids: list[str] | None = None,
	dry_run: bool = False,
) -> RetentionReport:
	"""Delete raw source text older than the retention policy.

	The whole content-addressed directory goes, provenance sidecar included.
	Removing the payload alone would leave ``store_raw`` unable to re-store the
	same bytes — it refuses a directory whose payload is missing, correctly,
	because that is its tamper check — so a re-fetch after a partial purge would
	raise. The audit trail the sidecar held is preserved instead in this
	report, which records source, checksum and size for every removal; the
	signal-level extraction and its source URL live in the review queue and are
	not touched.

	Returns the report either way. ``dry_run`` measures without deleting, which
	is what a scheduled job's first run should do.
	"""
	moment = now or utcnow()
	cutoff = moment - timedelta(days=retention_days)
	expired = expired_raw_payloads(
		root, retention_days=retention_days, now=moment, source_ids=source_ids
	)
	removed_bytes = 0
	removed = 0
	for _source_id, _checksum, directory, size in expired:
		if not dry_run:
			for child in sorted(directory.rglob("*"), reverse=True):
				if child.is_file():
					child.unlink()
				elif child.is_dir():
					child.rmdir()
			directory.rmdir()
		removed += 1
		removed_bytes += size

	total = len(expired_raw_payloads(root, retention_days=1, now=moment, source_ids=source_ids))
	report = RetentionReport(
		root=str(resolve(root)),
		retention_days=retention_days,
		cutoff=cutoff,
		removed_payloads=removed,
		removed_bytes=removed_bytes,
		kept_payloads=max(total - removed, 0),
	)
	logger.info(
		"retention_purge",
		root=report.root,
		retention_days=retention_days,
		removed=removed,
		removed_bytes=removed_bytes,
		dry_run=dry_run,
	)
	return report


def retention_report_payload(report: RetentionReport) -> dict[str, Any]:
	"""The report as a JSON-serialisable dict for the artefact layer."""
	return report.model_dump(mode="json")


__all__ = [
	"SHINGLE_K",
	"deduplicate_documents",
	"detail_key",
	"entity_count",
	"exact_deduplicate",
	"expired_raw_payloads",
	"ingest",
	"near_duplicate_groups",
	"purge_expired_raw",
	"retention_report_payload",
	"shingle_count",
	"shingles",
]
