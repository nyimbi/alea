# SPDX-License-Identifier: MIT
"""Scenario parameters.

WHY this is a frozen Pydantic value and not a dict: the cache key is a content
hash of the parameters (``alea.whatif.cache``). A parameter set that is not a
value cannot be hashed stably, so two identical scenarios would land in two
cache entries and the cache would grow without ever being hit. ``frozen=True``
makes a scenario a value; ``extra="forbid"`` turns a mistyped knob into a
construction error rather than a scenario that silently runs at the default.

Bounds are load-bearing for the same reason. ``demand_growth`` above 15%/year is
not a scenario, it is a typo, and catching it at construction costs a
millisecond where catching it after a forty-minute solve costs the frontier.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The SSP pathways that carry a climate story strong enough to justify a
# hydrological perturbation. See the validator below.
_HIGH_EMISSIONS_PATHWAYS: frozenset[str] = frozenset({"SSP3-7.0", "SSP5-8.5"})


class ScenarioParameters(BaseModel):
	"""Every knob the what-if engine exposes.

	The set is deliberately small. Each parameter must change the answer
	visibly, because a parameter that does nothing produces a flat frontier, and
	a flat frontier reads as "this does not matter" rather than "this was never
	applied".
	"""

	model_config = ConfigDict(
		extra="forbid",
		frozen=True,
		validate_by_name=True,
		validate_by_alias=True,
	)

	demand_growth: float = Field(default=0.04, ge=-0.05, le=0.15)
	"""Compound annual demand growth. Applied against the network's own years."""

	coal_eaf: float = Field(default=1.0, ge=0.0, le=2.0)
	"""Multiplier over per-unit coal availability, not an absolute override.

	The specification applies one ``coal_eaf`` to every coal unit. Availability
	is unit-specific and age-dependent, so a global override erases the fleet's
	real structure. This parameter scales each unit's own base availability
	instead, which is why it is a multiplier and why its effect is recorded as
	relative.
	"""

	carbon_price_usd_per_tco2: float = Field(default=50.0, ge=0.0, le=1000.0)
	"""Added to the marginal cost of every emitting carrier, per tonne of CO2."""

	gas_price_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
	renewable_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
	"""Multiplier over each renewable carrier's buildable potential (``p_nom_max``)."""

	hydrogen_export_twh_per_year: float = Field(default=0.0, ge=0.0)
	battery_cost_multiplier: float = Field(default=1.0, gt=0.0, le=5.0)
	ssp_pathway: str = "SSP2-4.5"
	drought_multiplier: float = Field(default=1.0, gt=0.0, le=3.0)
	"""Hydrological stress. Divides hydro availability; > 1 is a drier year."""

	@model_validator(mode="after")
	def _drought_needs_a_climate_scenario(self) -> ScenarioParameters:
		# A drought multiplier applied to a non-climate pathway is a
		# hydrological change with no climate story behind it. The result is
		# reportable as a sensitivity but not as a scenario, and the difference
		# matters when it reaches a report.
		if self.drought_multiplier != 1.0 and self.ssp_pathway not in _HIGH_EMISSIONS_PATHWAYS:
			raise ValueError(
				f"drought_multiplier={self.drought_multiplier} requires a "
				f"high-emissions SSP pathway, got {self.ssp_pathway!r}; a drought "
				f"with no climate scenario behind it is a sensitivity, not a scenario"
			)
		return self

	# ------------------------------------------------------------------
	# Value semantics
	# ------------------------------------------------------------------

	def canonical(self) -> dict[str, Any]:
		"""The parameter set as a JSON-safe mapping with stable key order."""
		return self.model_dump(mode="json")

	def canonical_json(self) -> str:
		"""Canonical serialisation of the parameter set alone.

		``sort_keys`` and the compact separators are what make the string a
		function of the values alone: without them the same parameters could
		serialise differently and hash to two keys.

		``whatif.cache.cache_key`` embeds this string in the solve key it
		hashes, so this is the one place the parameter half of that key is
		spelled. A second copy of the ``json.dumps`` call in ``cache_key`` would
		be a copy that can drift, and a key that hashes a different string than
		the one this documents is a cache that misses for reasons nobody can
		read off either file.
		"""
		payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"), default=str)
		assert payload.startswith("{"), payload
		return payload

	def with_value(self, name: str, value: Any) -> ScenarioParameters:
		"""A copy carrying one changed parameter, re-validated.

		``model_copy(update=...)`` skips validation, so a sweep value outside a
		field's bounds would sail through and produce a frontier point from an
		impossible scenario. Round-tripping through ``model_validate`` re-runs
		the bounds and the cross-field validators.
		"""
		if name not in type(self).model_fields:
			raise KeyError(
				f"unknown scenario parameter {name!r}; known: "
				f"{', '.join(sorted(type(self).model_fields))}"
			)
		updated = {**self.canonical(), name: value}
		return type(self).model_validate(updated)

	def changed_from(self, other: ScenarioParameters) -> dict[str, Any]:
		"""The parameters that differ from ``other``, as ``{name: value}``.

		Used by the sweep to name what it varied, and by the store to describe a
		scenario relative to its template.
		"""
		assert isinstance(other, ScenarioParameters)
		return {
			name: getattr(self, name)
			for name in type(self).model_fields
			if getattr(self, name) != getattr(other, name)
		}

	@classmethod
	def parameter_names(cls) -> list[str]:
		"""The sweepable parameter names, sorted for deterministic iteration."""
		return sorted(cls.model_fields)


__all__ = ["ScenarioParameters"]
