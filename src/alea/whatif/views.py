# SPDX-License-Identifier: MIT
"""What-if result models.

WHY every field carries its units in its name: the what-if engine produces the
numbers a decision-maker reads directly, and a frontier axis labelled "cost"
with no unit is a number two people can read as two different things. ALEA's
own history has a document that converted $1M at one rate while stating its
target at another — a self-contradiction no lint could see, because each line
was internally consistent. Units in the field name are the cheapest defence.

WHY ``renewable_share`` is ``float | None`` and never ``0.0`` on empty
generation: zero renewable generation and no generation at all are different
facts, and collapsing them reports a fully-renewable system for a network that
produced nothing.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alea.config.base import AleaConfig
from alea.provenance.models import Basis
from alea.whatif.params import ScenarioParameters


class WhatIfConfig(AleaConfig):
	"""Which sweep the quarterly `scenario_update` section reports.

	The section is a *range across the scenario set*, so it needs to know which
	parameter was swept and over what values. Both are config rather than
	constants because a frontier over carbon price answers a different question
	from one over demand growth, and a reader cannot tell which they are looking
	at from the shape of the table.

	``sweep_values`` is a tuple, not a (start, stop, points) triple. A triple
	implies a uniform grid, and the interesting sweeps are not uniform -- a
	carbon price frontier wants 0 in it, because the no-policy point is the
	baseline the others are read against, and an arithmetic sequence from 0 to
	200 in four steps does not include the values a policy reader asks for.
	"""

	parameter: str = "carbon_price_usd_per_tco2"
	"""The `ScenarioParameters` field the frontier sweeps.

	Validated against the model's own fields at load rather than at solve time:
	a typo here is a `KeyError` from `sweep_parameter` several minutes into a
	sweep, and `extra="forbid"` already refuses an unknown *key* -- this refuses
	an unknown *value*.
	"""

	sweep_values: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0)
	"""Parameter values, in the order the frontier's rows are reported."""

	workers: int = Field(default=1, ge=1)
	"""Parallel solves. Each worker writes its own cache entry, so there is no
	lock contention; 1 keeps a report generation reproducible by default."""

	cache_root: str = ""
	"""Where solved scenarios are cached. Empty means the layer's own default,
	which `WhatIfEngine` resolves -- a path spelled here would be a second
	answer to a question the cache already answers."""

	@field_validator("parameter")
	@classmethod
	def _parameter_must_be_sweepable(cls, value: str) -> str:
		known = ScenarioParameters.model_fields
		if value not in known:
			raise ValueError(
				f"unknown scenario parameter {value!r}; a frontier over a "
				f"parameter the engine cannot apply is flat in every row and "
				f"reads as 'this does not matter' rather than as a typo. "
				f"Known: {', '.join(sorted(known))}"
			)
		return value

	@field_validator("sweep_values")
	@classmethod
	def _sweep_needs_points(cls, value: tuple[float, ...]) -> tuple[float, ...]:
		if len(value) < 2:
			raise ValueError(
				f"a sweep of {len(value)} point(s) is not a range; a frontier "
				f"needs at least two values or it reports a scenario set of one"
			)
		return value


class RiskMetrics(BaseModel):
	"""Portfolio risk of a scenario's cost distribution.

	Sign convention follows ``alea._core.kernels.var_cvar``: both values are
	**positive loss magnitudes**. A CVaR of 120 means "in the worst 5% of years
	this portfolio loses 120 units"; a negative number quoted as a loss flips
	the meaning of everything downstream.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	confidence: float = Field(ge=0.0, le=1.0)
	"""The tail probability the two figures below describe. 0.95 is the default."""

	value_at_risk: float = Field(ge=0.0)
	"""The loss that is exceeded with probability ``1 - confidence``."""

	conditional_value_at_risk: float = Field(ge=0.0)
	"""Mean loss in the tail beyond VaR. This is the frontier's risk axis."""

	exceedance_probability: float | None = Field(default=None, ge=0.0, le=1.0)
	"""Empirical probability of exceeding the template's expected cost, when
	a threshold is supplied. ``None`` means no threshold was given."""

	@classmethod
	def from_costs(
		cls,
		costs: list[float],
		*,
		confidence: float = 0.95,
		threshold: float | None = None,
	) -> RiskMetrics:
		"""Risk metrics from a sample of system costs.

		``costs`` are **positive loss magnitudes** (a system cost is a loss). The
		kernel works in *returns*, where positive is a gain, so the sample is
		negated on the way in and both the VaR/CVaR and the exceedance threshold
		come back as positive losses. Passing costs to the kernel unnegated
		measures the right tail of a gain distribution and reports it as a loss —
		verified on this build: ``var_cvar([10..100], 0.9)`` returns ``-10``, a
		negative "loss", which is the sign defect the kernel's own docstring
		warns about, arriving from the caller's side.

		The kernel is imported lazily so that the what-if package imports without
		the compiled extension present; a reporting or API process that only
		reads stored scenarios never needs it.
		"""
		import numpy as np

		from alea._core.kernels import exceedance_probability, var_cvar

		if not costs:
			raise ValueError("risk metrics need at least one cost sample")
		returns = -np.asarray(costs, dtype=np.float64)
		var, cvar = var_cvar(returns, confidence)
		return cls(
			confidence=confidence,
			value_at_risk=max(0.0, var),
			conditional_value_at_risk=max(0.0, cvar),
			exceedance_probability=(
				None
				if threshold is None
				else exceedance_probability(returns, -float(threshold))
			),
		)


class ScenarioResult(BaseModel):
	"""The summary of one solved network.

	This is what gets cached and what a frontier point is built from. It holds
	no network object: a result that carried a live PyPSA network could not be
	serialised into a content-addressed entry, and a result that is not
	serialisable is a result that cannot be reproduced from its artefact.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	scenario_id: str
	"""UUID7. Time-ordered, so a directory listing of results is a chronology."""

	params: ScenarioParameters
	network_checksum: str
	code_version: str

	total_cost_usd: float
	"""The objective: total system cost over the horizon, undiscounted nominal."""

	total_emissions_tco2: float = Field(ge=0.0)
	capacity_mix_mw: dict[str, float]
	"""Carrier -> installed MW at the final horizon. Extendable capacity is the
	optimiser's ``p_nom_opt``; fixed capacity is ``p_nom``."""

	generation_mwh: dict[str, float]
	"""Carrier -> generated MWh over the horizon. Load shedding is a carrier and
	appears here, because energy that was not served is a fact about the system."""

	renewable_share: float | None = Field(default=None, ge=0.0, le=1.0)
	"""Fraction of generation from renewable carriers. ``None`` when total
	generation is zero — never 0, which would read as "fully fossil"."""

	unserved_energy_mwh: float = Field(default=0.0, ge=0.0)
	curtailment_mwh: float = Field(default=0.0, ge=0.0)
	energy_balance_error_mwh: float | None = None
	"""Generation minus load minus branch retention. Zero on a balanced solve.

	``None`` when there was no dispatch to measure — the same distinction
	``price_mean_usd_per_mwh`` draws, and for the same reason: ``0.0`` is a
	*claim* that the balance was checked and closed, and an unsolved network
	makes no such claim. An unsolved ``ScenarioResult`` is a legal object here
	(``extract`` reports ``None`` prices for one), so the field has to be able
	to say "not measured" rather than defaulting to a passing value.

	Carried rather than only *checked*, because the what-if path never checked
	it: `check_energy_balance` is live on the planning path (`solve_dispatch`
	calls it, and `planning/service.py` and `publish/stages.py` reach that), but
	the engine's own `_default_solve` calls `network.optimize` directly and
	never goes through `solve_dispatch`. So a `ScenarioResult` was the one
	result in the tree asserting a balance no code had verified. The solve still
	refuses a residual over the tolerance where `solve_dispatch` runs it, and
	this records the number on the result so a report can show how close the
	solve came rather than say nothing because it happened to clear the bar.

	Signed, and not an absolute value: a negative residual is energy created (a
	heat-pump link, or a bus the model double-counts), which is as much a
	finding as a positive one.
	"""

	price_mean_usd_per_mwh: float | None = None
	price_volatility_usd_per_mwh: float | None = None
	risk: RiskMetrics | None = None
	"""The cost-risk frontier's risk axis. ``None`` when no price/cost
	distribution was available for this scenario."""

	basis: Basis = Basis.MODELLED
	uncertainty: float = Field(default=0.0, ge=0.0)
	"""Maximum relative uncertainty of the inputs (the conservative combination
	rule from ``ProvenanceRecord``). 0.0 means exact."""

	notes: str = ""

	def to_cache_payload(self) -> dict[str, Any]:
		"""The JSON-safe body stored in the cache entry."""
		return self.model_dump(mode="json")

	@classmethod
	def from_cache_payload(cls, payload: dict[str, Any]) -> ScenarioResult:
		return cls.model_validate(payload)


class FrontierPoint(BaseModel):
	"""One point on the efficient frontier.

	WHY cost and risk are both required: a point with cost alone is not a
	frontier point, it is a cost. The frontier that answers a lender's question
	is cost against CVaR — whether the portfolio survives a bad year — and a
	frontier that plots only cost against emissions answers a policy question
	instead. Both are computed; neither is reported alone.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	param_name: str
	param_value: float
	total_cost_usd: float
	total_emissions_tco2: float = Field(ge=0.0)
	renewable_share: float | None = None
	conditional_value_at_risk: float | None = Field(default=None, ge=0.0)
	"""The risk axis. ``None`` only when the scenario's risk was not computed;
	a frontier with ``None`` here is a cost-emissions frontier and is reported
	as such."""

	value_at_risk: float | None = Field(default=None, ge=0.0)
	capacity_mix_mw: dict[str, float] = Field(default_factory=dict)
	scenario_id: str = ""
	cache_key: str = ""
	from_cache: bool = False
	"""Whether this point was served from the cache. Recorded so a resumed
	sweep can be distinguished from a fresh one in the provenance."""

	@property
	def is_cost_risk(self) -> bool:
		"""Whether this point carries the risk axis."""
		return self.conditional_value_at_risk is not None


class SolveOutcome(BaseModel):
	"""One solve and how it was served.

	``from_cache`` is recorded rather than inferred. A run whose points were
	mostly cached and one that re-solved everything produce the same frontier
	but are different facts about the system, and the exit criterion for a
	resumed sweep depends on telling them apart.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	result: ScenarioResult
	cache_key: str
	from_cache: bool
	solve_seconds: float = Field(default=0.0, ge=0.0)


class ScenarioRecord(BaseModel):
	"""A scenario persisted as a named, versioned artefact.

	WHY the network checksum is part of the record and not just the cache key:
	a scenario without it is not reproducible. Two engines built on different
	networks would otherwise produce incomparable results under the same
	scenario name, and nothing in the stored artefact would say so.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	name: str
	version: str
	"""Content-addressed version = the solve's cache key. Saving the same
	scenario twice is idempotent; changing anything produces a new version."""

	params: ScenarioParameters
	network_checksum: str
	code_version: str
	result: ScenarioResult
	created_at: str
	tags: list[str] = Field(default_factory=list)
	notes: str = ""

	def summary(self) -> str:
		"""One line for a CLI listing. No units are guessed here; the fields
		already carry theirs."""
		risk = (
			""
			if self.result.risk is None
			else f" cvar={self.result.risk.conditional_value_at_risk:.1f}"
		)
		return (
			f"{self.name}@{self.version[:12]} "
			f"cost={self.result.total_cost_usd:.1f} "
			f"co2={self.result.total_emissions_tco2:.1f}{risk}"
		)


def renewable_share(generation_mwh: dict[str, float]) -> float | None:
	"""Renewable fraction of generation, or ``None`` when nothing was generated.

	``None`` is the correct answer for an empty system. Returning 0.0 asserts
	"no renewable generation", which is a different and false claim.
	"""
	total = math.fsum(generation_mwh.values())
	if total <= 0.0:
		return None

	from alea.registry.technologies import get_technology

	def _is_renewable(carrier: str) -> bool:
		# Carriers in a network may be upstream aliases ("wind" for "onwind"),
		# so resolve through the registry rather than string-matching. An
		# unregistered carrier is not renewable by default: counting an unknown
		# carrier as renewable would inflate the share silently.
		try:
			return get_technology(carrier).renewable
		except KeyError:
			return False

	renewable_mwh = math.fsum(mwh for carrier, mwh in generation_mwh.items() if _is_renewable(carrier))
	return min(1.0, max(0.0, renewable_mwh / total))


__all__ = [
	"FrontierPoint",
	"RiskMetrics",
	"ScenarioRecord",
	"ScenarioResult",
	"SolveOutcome",
	"WhatIfConfig",
	"renewable_share",
]
