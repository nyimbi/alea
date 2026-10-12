# SPDX-License-Identifier: MIT
"""Models for Layer 4c — resilience metrics.

The input that does not exist: ``n_customers`` per zone. Customer counts are
utility data, not open data. The platform derives them from WorldPop —
population per zone divided by average household size — and **records this as a
proxy** with ``uncertainty_basis="proxy"`` (AD-6, 07-layer4 §8).

That distinction is load-bearing. SAIDI and SAIFI computed from a population
proxy are comparable across zones and are **not** comparable to a utility's own
published SAIDI, because the denominator is a different quantity. The artefact
says which it is, so a report cannot silently present a proxy index beside a
utility's and invite the comparison.

SAIDI and SAIFI also require a **defined interruption threshold**: a 30-second
reclosure is not an interruption. The threshold is config, recorded, and
reported with the metric — an index without its threshold is not reproducible.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from alea.config.base import AleaConfig
from alea.provenance.models import Basis

DEFAULT_INTERRUPTION_THRESHOLD_MINUTES = 5.0
"""Below this an interruption is a reclosure, not an event.

The standard practice in reliability reporting; a distribution recloser that
restores supply in under a minute has not interrupted the customer in any sense
a SAIDI figure should count.
"""


class ResilienceConfig(AleaConfig):
	"""How resilience metrics are computed."""

	interruption_threshold_minutes: float = Field(
		default=DEFAULT_INTERRUPTION_THRESHOLD_MINUTES, gt=0.0
	)
	"""Events shorter than this are not interruptions. Recorded with every
	metric: two SAIDI figures computed at different thresholds are different
	quantities sharing a name."""

	average_household_size: float = Field(default=4.5, gt=0.0)
	"""Persons per household, for the WorldPop customer derivation. A proxy
	parameter and labelled as one."""

	electrification_rate: float = Field(default=1.0, ge=0.0, le=1.0)
	"""Fraction of households connected. Below 1 the customer count is a
	fraction of the population-derived households, which is itself a proxy."""

	customers_basis: Basis = Basis.PROXY
	"""The basis of the customer counts, when derived rather than metered."""

	proxy_uncertainty: float = Field(default=0.15, gt=0.0, le=1.0)
	"""Relative uncertainty on a population-derived customer count.

	Non-zero and explained, because a proxy with zero uncertainty is a claim
	that the substitute is exact, which is never true (``Provenance``).
	"""

	@model_validator(mode="after")
	def _proxy_basis_carries_uncertainty(self) -> ResilienceConfig:
		if self.customers_basis is Basis.PROXY and self.proxy_uncertainty <= 0:
			raise ValueError("a proxy customer count requires non-zero uncertainty")
		return self


class ZoneCustomers(AleaConfig):
	"""Customer count for one zone, with where the number came from."""

	zone: str
	n_customers: float = Field(ge=0.0)
	basis: Basis = Basis.MEASURED
	uncertainty: float = Field(default=0.0, ge=0.0)
	uncertainty_basis: str = ""
	source: str = ""

	@model_validator(mode="after")
	def _provenance_is_consistent(self) -> ZoneCustomers:
		# The same rules ``Provenance`` enforces, applied here because a zone's
		# customer count is the denominator of every resilience index and an
		# unjustified uncertainty on it propagates to all of them.
		if self.basis is Basis.PROXY and self.uncertainty <= 0:
			raise ValueError(
				f"zone {self.zone!r}: a proxy customer count requires "
				f"uncertainty > 0; a proxy is not exact"
			)
		if self.uncertainty > 0 and not self.uncertainty_basis:
			raise ValueError(
				f"zone {self.zone!r}: non-zero uncertainty requires an "
				f"uncertainty_basis saying what it measures"
			)
		return self


class InterruptionEvent(AleaConfig):
	"""One interruption affecting one zone."""

	zone: str
	started_at: datetime
	duration_minutes: float = Field(gt=0.0)
	load_mw: float = Field(default=0.0, ge=0.0)
	"""Unserved load during the event, MW. Zero when unknown, which makes ENS
	zero rather than silently substituting another zone's load."""

	customers_interrupted: float | None = Field(default=None, ge=0.0)
	"""Customers interrupted, when measured. ``None`` means the zone's total is
	used, which is the usual assumption for a zone-level event."""

	cause: str = ""

	@property
	def duration_hours(self) -> float:
		return self.duration_minutes / 60.0

	def is_interruption(self, threshold_minutes: float) -> bool:
		"""Whether this event counts at the given threshold."""
		return self.duration_minutes >= threshold_minutes


class ResilienceMetrics(AleaConfig):
	"""ENS, EENS, SAIDI, SAIFI and LNS for one scenario or one network.

	Every index carries the threshold that produced it and the basis of the
	customer denominator. The gate ``test_saidi_proxy_flagged`` canaries that a
	population-derived SAIDI never loses its ``proxy`` flag.
	"""

	ens_mwh: float = Field(ge=0.0)
	"""Energy not served: sum of unserved load times duration, MWh."""

	eens_mwh: float = Field(ge=0.0)
	"""Probability-weighted ENS across scenarios, MWh."""

	saidi_hours: float = Field(ge=0.0)
	"""System Average Interruption Duration Index, hours per customer."""

	saifi: float = Field(ge=0.0)
	"""System Average Interruption Frequency Index, interruptions per
	customer."""

	lns_mw: float = Field(ge=0.0)
	"""Load not served at peak: the largest unserved load over the events, MW."""

	interruption_threshold_minutes: float = Field(gt=0.0)
	customers_total: float = Field(ge=0.0)
	customers_basis: Basis = Basis.PROXY
	customers_uncertainty: float = Field(default=0.0, ge=0.0)
	n_events: int = Field(ge=0)
	n_events_below_threshold: int = Field(default=0, ge=0)
	"""Events excluded as reclosures. Reported so the threshold's effect is
	visible rather than implied by a count that does not match the input."""

	n_zones: int = Field(ge=0)
	scenario: str = ""
	notes: str = ""

	@property
	def customers_are_proxy(self) -> bool:
		"""Whether the customer denominator is a proxy.

		True means the indices are comparable across zones and **not**
		comparable to a utility's published figures.
		"""
		return self.customers_basis is Basis.PROXY

	@property
	def is_comparable_to_utility_reports(self) -> bool:
		return self.customers_basis is Basis.MEASURED


class ScenarioEns(AleaConfig):
	"""One scenario's ENS, for the probability-weighted EENS."""

	name: str
	probability: float = Field(ge=0.0, le=1.0)
	ens_mwh: float = Field(ge=0.0)


class EensResult(AleaConfig):
	"""Expected energy not supplied across scenarios."""

	eens_mwh: float
	scenarios: list[ScenarioEns]
	total_probability: float
	"""Must be 1.0: probabilities that do not sum to one make EENS a number
	scaled by an arbitrary constant."""

	@model_validator(mode="after")
	def _probabilities_sum_to_one(self) -> EensResult:
		if abs(self.total_probability - 1.0) > 1e-9:
			raise ValueError(
				f"scenario probabilities sum to {self.total_probability}, not 1.0; "
				f"EENS is then scaled by an arbitrary constant"
			)
		return self


__all__ = [
	"DEFAULT_INTERRUPTION_THRESHOLD_MINUTES",
	"EensResult",
	"InterruptionEvent",
	"ResilienceConfig",
	"ResilienceMetrics",
	"ScenarioEns",
	"ZoneCustomers",
]
