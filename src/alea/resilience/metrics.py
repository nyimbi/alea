# SPDX-License-Identifier: MIT
"""Resilience metrics: ENS, EENS, SAIDI, SAIFI, LNS.

The formulas are the specification's, and they are standard:

```
SAIDI = sum(duration_i * customers_interrupted_i) / customers_total
SAIFI = sum(customers_interrupted_i) / customers_total
EENS  = sum_s p_s * ENS_s
LNS   = max over events of unserved load at peak
```

Two inputs need care rather than arithmetic.

**The customer denominator does not exist as open data.** Customer counts are
utility data. The platform derives them from WorldPop (population per zone
divided by average household size) and records the result as a **proxy** with
``uncertainty_basis="proxy"`` (AD-6). A SAIDI from a population proxy is
comparable across zones and is **not** comparable to a utility's own published
SAIDI, because the denominator is a different quantity; the artefact says which
it is, and :attr:`ResilienceMetrics.customers_are_proxy` is that statement.

**SAIDI and SAIFI require a defined interruption threshold.** A 30-second
reclosure is not an interruption. The threshold is config, recorded, and
reported with the metric — two SAIDI figures at different thresholds are
different quantities sharing a name.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from alea.logging import get_logger
from alea.provenance.models import Basis
from alea.resilience.views import (
	EensResult,
	InterruptionEvent,
	ResilienceConfig,
	ResilienceMetrics,
	ScenarioEns,
	ZoneCustomers,
)

logger = get_logger(__name__)


def customers_from_population(
	zone: str,
	population: float,
	config: ResilienceConfig | None = None,
	*,
	source: str = "WorldPop",
) -> ZoneCustomers:
	"""Derive a zone's customer count from population, **as a proxy**.

	``n_customers = population / household_size * electrification_rate``. The
	result carries ``basis=PROXY`` and a non-zero uncertainty, so every index
	computed from it is visibly a proxy index all the way to a report (AD-6).
	"""
	cfg = config or ResilienceConfig()
	if population < 0:
		raise ValueError(f"population must be non-negative, got {population}")
	households = population / cfg.average_household_size
	return ZoneCustomers(
		zone=zone,
		n_customers=households * cfg.electrification_rate,
		basis=Basis.PROXY,
		uncertainty=cfg.proxy_uncertainty,
		uncertainty_basis=(
			f"population proxy: {source} population / {cfg.average_household_size} "
			f"persons per household x {cfg.electrification_rate} electrification"
		),
		source=source,
	)


def ens_mwh(events: Sequence[InterruptionEvent]) -> float:
	"""Energy not served: sum of unserved load times duration, MWh.

	An event with no recorded load contributes zero. That is honest — the
	alternative is substituting a neighbouring zone's load, which AD-8's
	"fail loud on missing data" forbids — but it means an ENS built from events
	with no load data understates the true value, and the caller should record
	how many events carried a load.
	"""
	assert all(event.duration_minutes > 0 for event in events), "an event has non-positive duration"
	return float(sum(event.load_mw * event.duration_hours for event in events))


def load_not_served_mw(events: Sequence[InterruptionEvent]) -> float:
	"""Peak load not served: the largest unserved load over the events, MW."""
	return float(max((event.load_mw for event in events), default=0.0))


def saidi_hours(
	events: Sequence[InterruptionEvent],
	customers: dict[str, float],
	config: ResilienceConfig | None = None,
) -> tuple[float, float, int]:
	"""SAIDI in hours, the customer total, and the count of qualifying events.

	``sum(duration_i * customers_interrupted_i) / customers_total``. An event
	in a zone with no customer count raises: silently dropping it would compute
	SAIDI over a subset of the network and report it as the whole.
	"""
	cfg = config or ResilienceConfig()
	total = _customer_total(customers)
	numerator = 0.0
	qualifying = 0
	for event in events:
		if not event.is_interruption(cfg.interruption_threshold_minutes):
			continue
		interrupted = _interrupted(event, customers)
		numerator += event.duration_hours * interrupted
		qualifying += 1
	if total <= 0:
		raise ValueError(
			"no customers in any zone; SAIDI is undefined and 0 would read as "
			"perfect reliability"
		)
	return numerator / total, total, qualifying


def saifi(
	events: Sequence[InterruptionEvent],
	customers: dict[str, float],
	config: ResilienceConfig | None = None,
) -> tuple[float, int]:
	"""SAIFI: ``sum(customers_interrupted_i) / customers_total``, and the count."""
	cfg = config or ResilienceConfig()
	total = _customer_total(customers)
	numerator = 0.0
	qualifying = 0
	for event in events:
		if not event.is_interruption(cfg.interruption_threshold_minutes):
			continue
		numerator += _interrupted(event, customers)
		qualifying += 1
	if total <= 0:
		raise ValueError("no customers in any zone; SAIFI is undefined")
	return numerator / total, qualifying


def _interrupted(event: InterruptionEvent, customers: dict[str, float]) -> float:
	if event.customers_interrupted is not None:
		return float(event.customers_interrupted)
	if event.zone not in customers:
		raise KeyError(
			f"event in zone {event.zone!r} has no customer count and none is "
			f"recorded on the event; dropping it would compute the index over a "
			f"subset of the network"
		)
	return float(customers[event.zone])


def _customer_total(customers: dict[str, float]) -> float:
	return float(sum(customers.values()))


def expected_ens(scenarios: Sequence[ScenarioEns]) -> EensResult:
	"""Probability-weighted ENS across scenarios.

	The probabilities must sum to 1.0; :class:`EensResult` refuses otherwise,
	because a set that sums to 0.8 scales EENS by an arbitrary constant that
	nothing downstream can detect.
	"""
	if not scenarios:
		raise ValueError("no scenarios supplied; EENS over an empty set is not zero, it is undefined")
	total = float(sum(scenario.probability for scenario in scenarios))
	value = float(sum(scenario.probability * scenario.ens_mwh for scenario in scenarios))
	result = EensResult(
		eens_mwh=value,
		scenarios=list(scenarios),
		total_probability=total,
	)
	logger.info("resilience.eens", eens_mwh=value, n_scenarios=len(scenarios))
	return result


def compute_metrics(
	events: Sequence[InterruptionEvent],
	customers: dict[str, float] | dict[str, ZoneCustomers],
	config: ResilienceConfig | None = None,
	*,
	scenarios: Sequence[ScenarioEns] | None = None,
	scenario: str = "",
) -> ResilienceMetrics:
	"""Compute ENS, EENS, SAIDI, SAIFI and LNS from an event list.

	``customers`` maps a zone to a count or to a :class:`ZoneCustomers`; the
	latter is preferred because it carries the basis. When any zone's count is
	a proxy, the whole metric set is flagged as proxy-derived — the weakest
	input sets the basis, the same rule :class:`ProvenanceRecord` applies.
	"""
	cfg = config or ResilienceConfig()
	normalised, basis, uncertainty = _normalise_customers(customers, cfg)
	if not events:
		logger.warning("resilience.no_events", zones=len(normalised))
		return ResilienceMetrics(
			ens_mwh=0.0,
			eens_mwh=0.0,
			saidi_hours=0.0,
			saifi=0.0,
			lns_mw=0.0,
			interruption_threshold_minutes=cfg.interruption_threshold_minutes,
			customers_total=_customer_total(normalised),
			customers_basis=basis,
			customers_uncertainty=uncertainty,
			n_events=0,
			n_events_below_threshold=0,
			n_zones=len(normalised),
			scenario=scenario,
			notes="no events in the period; every index is zero by absence of data",
		)

	duration_index, total, qualifying = saidi_hours(events, normalised, cfg)
	frequency_index, _ = saifi(events, normalised, cfg)
	eens = (
		expected_ens(scenarios).eens_mwh
		if scenarios is not None
		else ens_mwh(events)
		# With no scenarios, EENS collapses to ENS at probability 1. The
		# artefact says so rather than leaving EENS equal to ENS unexplained.
	)
	below = sum(
		1 for event in events if not event.is_interruption(cfg.interruption_threshold_minutes)
	)

	metrics = ResilienceMetrics(
		ens_mwh=ens_mwh(events),
		eens_mwh=eens,
		saidi_hours=duration_index,
		saifi=frequency_index,
		lns_mw=load_not_served_mw(events),
		interruption_threshold_minutes=cfg.interruption_threshold_minutes,
		customers_total=total,
		customers_basis=basis,
		customers_uncertainty=uncertainty,
		n_events=qualifying,
		n_events_below_threshold=below,
		n_zones=len(normalised),
		scenario=scenario,
		notes=_notes(basis, scenarios, below, cfg),
	)
	logger.info(
		"resilience.metrics",
		ens_mwh=metrics.ens_mwh,
		saidi_hours=metrics.saidi_hours,
		saifi=metrics.saifi,
		customers_basis=basis.value,
		threshold_minutes=cfg.interruption_threshold_minutes,
	)
	return metrics


def _normalise_customers(
	customers: dict[str, float] | dict[str, ZoneCustomers],
	config: ResilienceConfig,
) -> tuple[dict[str, float], Basis, float]:
	"""Flatten the customer mapping and derive the aggregate basis.

	The aggregate basis is the weakest among the zones: a metric computed from
	one proxied denominator is at best a proxy, whatever else went into it.
	Taking the strongest would let one metered zone launder the rest.
	"""
	values: dict[str, float] = {}
	basis = Basis.MEASURED
	uncertainty = 0.0
	for zone, entry in customers.items():
		if isinstance(entry, ZoneCustomers):
			values[zone] = float(entry.n_customers)
			if entry.basis is Basis.PROXY:
				basis = Basis.PROXY
			elif entry.basis is Basis.MODELLED and basis is Basis.MEASURED:
				basis = Basis.MODELLED
			uncertainty = max(uncertainty, entry.uncertainty)
		else:
			values[zone] = float(entry)
	if basis is Basis.PROXY and uncertainty <= 0:
		# A caller passing raw floats cannot state a basis; if the config says
		# the counts are proxies, apply the configured uncertainty so the
		# metric still carries one.
		uncertainty = config.proxy_uncertainty
	return values, basis, uncertainty


def _notes(
	basis: Basis,
	scenarios: Sequence[ScenarioEns] | None,
	below: int,
	config: ResilienceConfig,
) -> str:
	parts = [
		f"interruption threshold {config.interruption_threshold_minutes} min "
		f"({below} shorter events excluded)"
	]
	if basis is Basis.PROXY:
		parts.append(
			"customer denominator is a population proxy: indices are comparable "
			"across zones and NOT comparable to a utility's published SAIDI/SAIFI"
		)
	if scenarios is None:
		parts.append("no scenarios supplied; EENS collapses to ENS at probability 1")
	return "; ".join(parts)


def metrics_payload(metrics: ResilienceMetrics) -> dict[str, object]:
	"""The metrics as a JSON-ready payload for an artefact sidecar."""
	return metrics.model_dump(mode="json")


def sensitivity_to_threshold(
	events: Sequence[InterruptionEvent],
	customers: dict[str, float] | dict[str, ZoneCustomers],
	thresholds: Sequence[float],
	config: ResilienceConfig | None = None,
) -> list[dict[str, float]]:
	"""SAIDI and SAIFI across candidate thresholds.

	Reported so the threshold's effect is measured rather than assumed: a
	network whose SAIDI halves between a 1-minute and a 5-minute threshold is a
	network of reclosures, and the index alone would not say so.
	"""
	cfg = config or ResilienceConfig()
	rows: list[dict[str, float]] = []
	for threshold in thresholds:
		variant = cfg.model_copy(update={"interruption_threshold_minutes": threshold})
		metrics = compute_metrics(events, customers, variant)
		rows.append(
			{
				"threshold_minutes": threshold,
				"saidi_hours": metrics.saidi_hours,
				"saifi": metrics.saifi,
				"n_events": float(metrics.n_events),
				"n_excluded": float(metrics.n_events_below_threshold),
			}
		)
	return rows


__all__ = [
	"compute_metrics",
	"customers_from_population",
	"ens_mwh",
	"expected_ens",
	"load_not_served_mw",
	"metrics_payload",
	"saidi_hours",
	"saifi",
	"sensitivity_to_threshold",
]
