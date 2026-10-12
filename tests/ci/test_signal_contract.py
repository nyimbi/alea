# SPDX-License-Identifier: MIT
"""The signal contract's invariants.

The coordinate guard earns a test because its first implementation was inverted
and ineffective: a ``field_validator`` on ``latitude`` ran before ``longitude``
was populated, so it rejected every fully-geolocated signal and accepted a
longitude on its own. Both directions are asserted here so the guard cannot be
half-fixed again.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from alea.signals.models import Signal

BASE = {
	"signal_type": "outage_event",
	"confidence": 0.9,
	"source_document_id": "doc-1",
	"source_url": "https://example.org/a",
	"source_name": "example",
}


def make(**overrides) -> Signal:
	return Signal(**{**BASE, **overrides})


def test_neither_coordinate_is_allowed():
	signal = make()
	assert signal.latitude is None
	assert signal.longitude is None
	assert not signal.is_geolocated


def test_both_coordinates_are_allowed():
	signal = make(latitude=-1.2921, longitude=36.8219)
	assert signal.is_geolocated


@pytest.mark.parametrize(
	"half",
	[{"latitude": -1.2921}, {"longitude": 36.8219}],
	ids=["latitude alone", "longitude alone"],
)
def test_half_a_coordinate_is_rejected(half):
	with pytest.raises(ValidationError, match="must be given together"):
		make(**half)


def test_out_of_range_coordinates_are_rejected():
	with pytest.raises(ValidationError):
		make(latitude=91.0, longitude=36.8)
	with pytest.raises(ValidationError):
		make(latitude=-1.0, longitude=181.0)


def test_country_iso_is_validated_and_upper_cased():
	assert make(country_iso="ke").country_iso == "KE"
	with pytest.raises(ValidationError, match="ISO 3166-1 alpha-2"):
		make(country_iso="Kenya")


def test_signal_is_not_anonymous_or_unqualified():
	with pytest.raises(ValidationError):
		Signal(signal_type="outage_event")  # type: ignore[call-arg]  # no provenance, no confidence
	with pytest.raises(ValidationError):
		make(confidence=1.5)


def test_unknown_fields_are_rejected():
	with pytest.raises(ValidationError):
		make(unexpected_field="x")


def test_signals_require_review_by_default():
	assert make().requires_review is True


def test_the_default_extraction_time_is_timezone_aware_utc():
	"""§2's provenance row lists ``extracted_at`` as auditable, so it must mean one instant.

	The default was ``datetime.now()``: naive, so silently the host's local
	time. This value is written to SQLite as ``isoformat()`` and ordered as a
	string, so two hosts in different zones sort the same corpus differently,
	and a reviewer reading it cannot tell what instant it names.
	"""
	from datetime import UTC, datetime

	extracted = make().extracted_at
	assert extracted.tzinfo is not None, f"extracted_at is naive: {extracted!r}"
	assert extracted.utcoffset() == timedelta(0), (
		f"extracted_at carries offset {extracted.utcoffset()}, not UTC"
	)
	assert abs((datetime.now(UTC) - extracted).total_seconds()) < 60


def test_a_naive_extraction_time_is_refused_not_assumed_utc():
	"""The same defect arriving from the caller, which is where it does arrive.

	``alea.api.signals`` reads rows back with ``datetime.fromisoformat`` and
	passes the result straight into ``Signal``. A stored value written before
	the default was fixed is naive, and assuming it was UTC would be a silent
	offset applied to real data rather than a loud failure at the boundary.
	"""
	from datetime import datetime

	with pytest.raises(ValidationError) as raised:
		make(extracted_at=datetime(2026, 1, 1, 12, 0, 0))
	assert "timezone-aware" in str(raised.value)


def test_an_aware_extraction_time_is_accepted_in_any_zone():
	"""Awareness is the requirement, not UTC specifically: ``isoformat`` keeps the offset."""
	from datetime import UTC, datetime, timedelta, timezone

	nairobi = make(extracted_at=datetime(2026, 1, 1, 15, 0, tzinfo=timezone(timedelta(hours=3))))
	assert nairobi.extracted_at.utcoffset() == timedelta(hours=3)
	assert make(extracted_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)).extracted_at.tzinfo is UTC
