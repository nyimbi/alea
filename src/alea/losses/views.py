# SPDX-License-Identifier: MIT
"""Models for Layer 4b — loss decomposition, flow, contingency, mitigation.

Two specification defects shape these models.

1. The specification's `_topology_driven` returns a hardcoded ``0``, so its
   components do not sum to the total. :class:`LossComponents` makes the sum
   invariant structural: it is validated on construction to 1e-9 relative
   tolerance, and a decomposition whose parts do not add up cannot be
   instantiated. A decomposition that does not sum is worse than no
   decomposition, because it looks like an analysis (07-layer4 §6.2).

2. ``payback = capex / annual_savings`` returns ``inf`` for zero savings, which
   sorts to the bottom but reads in a report as "never" when it may mean
   "below measurement resolution". :class:`MitigationResult` reports NaN with a
   note for a zero-saving option, never ``inf`` (07-layer4 §7.2).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from alea.config.base import AleaConfig

DECOMPOSITION_TOLERANCE = 1e-9
"""Relative tolerance the parts must sum to the total within. The Rust kernel
guarantees exactness by construction (the generation component is the
residual); this tolerance only catches a future change that breaks it."""


class LossConfig(AleaConfig):
	"""How losses are measured."""

	price_usd_per_mwh: float = Field(default=0.0, ge=0.0)
	"""Value of a lost MWh. Used for mitigation payback, not for the loss
	itself: a loss is a physical quantity and does not need a price."""

	slack_bus: int = Field(default=0, ge=0)
	"""Reference bus for the DC solve. Pinned rather than chosen, so two runs
	of the same network produce the same angles."""

	min_savings_usd_per_year: float = Field(default=1.0, gt=0.0)
	"""Floor below which annual savings are treated as unmeasurable. Below it a
	payback is reported as NaN, not as an enormous number."""

	decomposition_tolerance: float = Field(default=DECOMPOSITION_TOLERANCE, gt=0.0)

	snapshot_hours: float = Field(default=1.0, gt=0.0)
	"""Hours each snapshot represents.

	The DC solve returns a loss in **MW** for one snapshot. Every field here
	named ``*_mwh`` is that MW summed over snapshots, which is MWh only when a
	snapshot is exactly one hour. Nothing in the payload used to record the
	timestep, so a 15-minute or 3-hourly dispatch silently scaled every loss by
	4 or by a third while the field name kept asserting MWh. Defaulting to 1.0
	keeps an hourly series unchanged and makes any other resolution an explicit,
	recorded choice rather than an accident of the caller's index."""


class LossComponents(AleaConfig):
	"""A three-component loss decomposition that sums to its total.

	The attribution is sequential and its order is fixed, so the result is
	reproducible: a decomposition whose order is unspecified is one whose parts
	differ between runs (03-rust-core §6.3).
	"""

	load_driven_mwh: float
	"""The loss the actual load causes, measured from the no-load case."""

	generation_driven_mwh: float
	"""The residual attributable to the actual dispatch pattern."""

	topology_driven_mwh: float
	"""What the actual topology adds over the reference topology."""

	total_mwh: float
	tolerance: float = DECOMPOSITION_TOLERANCE

	@model_validator(mode="after")
	def _parts_sum_to_total(self) -> LossComponents:
		parts = self.load_driven_mwh + self.generation_driven_mwh + self.topology_driven_mwh
		scale = max(abs(self.total_mwh), 1e-12)
		if abs(parts - self.total_mwh) / scale > self.tolerance:
			raise ValueError(
				f"loss components sum to {parts} but the total is {self.total_mwh} "
				f"(relative error {abs(parts - self.total_mwh) / scale:.3e}); a "
				f"decomposition whose parts do not sum is worse than none "
				f"(07-layer4 §6.2)"
			)
		return self

	@property
	def sum_of_parts_mwh(self) -> float:
		return self.load_driven_mwh + self.generation_driven_mwh + self.topology_driven_mwh

	@property
	def shares(self) -> dict[str, float]:
		"""Each component as a fraction of the total, or NaN for a zero total."""
		if abs(self.total_mwh) < 1e-12:
			return {name: float("nan") for name in self.component_names()}
		return {
			"load_driven": self.load_driven_mwh / self.total_mwh,
			"generation_driven": self.generation_driven_mwh / self.total_mwh,
			"topology_driven": self.topology_driven_mwh / self.total_mwh,
		}

	@staticmethod
	def component_names() -> tuple[str, str, str]:
		return ("load_driven", "generation_driven", "topology_driven")


class FlowResult(AleaConfig):
	"""A DC solve's output for one snapshot."""

	angles_rad: list[float]
	flows_mw: list[float]
	losses_mw: float
	loss_fraction: float
	"""Losses as a fraction of generation. NaN when generation is zero, because
	a loss fraction with no generation is undefined and zero would read as
	"no losses"."""

	slack_bus: int
	n_buses: int
	n_branches: int


class LoadingEntry(AleaConfig):
	"""One branch's loading against its own rating, over a snapshot series.

	``peak_loading`` is ``max_t |p0(t)| / s_nom`` and is **dimensionless**: 1.0
	is at rating. It is not a power, which is why it has no unit suffix -- the
	weekly section prints it under the unit ``loading``.
	"""

	branch: int
	branch_name: str = ""
	from_bus: int
	to_bus: int
	peak_loading: float
	hours_at_or_above: float
	"""Hours at or above rating: ``snapshots_at_or_above * snapshot_hours``.

	Never the snapshot *count*. A count printed under a column headed "Hours"
	overstates by the series resolution -- 4x for a 15-minute dispatch, 8760x
	for a year read as a count of hours -- and the two agree only for an hourly
	series, which is exactly the case a test written on one cannot tell apart.
	"""

	peak_flow_mw: float
	"""The flow magnitude at the peak-loading snapshot, ``peak_loading * s_nom``."""

	rating_mw: float
	snapshots_at_or_above: int
	diverged_snapshots: int = 0
	"""Snapshots whose solve did not return a finite flow. Recorded, never
	propagated: a diverged snapshot is excluded from the peak and the count
	rather than making both NaN."""


class LoadingRanking(AleaConfig):
	"""Every branch at or above its rating, worst first.

	Deterministic (AD-8): entries sort by peak loading descending and, on ties,
	by branch index ascending, so two runs of the same dispatch produce the same
	critical-line list.

	**An empty list means nothing was above rating, and the model is built so it
	cannot mean anything else.** A branch with no finite rating -- what
	`alea.planning.arrays` gives a line whose ``s_nom`` is absent -- is not in
	``entries`` at all, and a run where *no* branch is rated raises rather than
	returning an empty list: "no critical lines" and "no ratings to compare
	against" are different findings and only one of them is good news.
	"""

	entries: list[LoadingEntry]
	n_snapshots: int
	n_branches: int
	n_rated: int
	"""Branches carrying a finite, positive rating."""

	threshold: float = 1.0
	parameters: dict[str, Any] = Field(default_factory=dict)

	@property
	def n_unrated(self) -> int:
		"""Branches excluded for want of a rating."""
		return self.n_branches - self.n_rated

	@property
	def worst_loading(self) -> float:
		"""The highest peak loading in the ranking, or 0.0 when it is empty."""
		return max((entry.peak_loading for entry in self.entries), default=0.0)


class TlensEntry(AleaConfig):
	"""One branch's contribution to energy not supplied."""

	branch: int
	branch_name: str = ""
	from_bus: int
	to_bus: int
	ens_with_out_mwh: float
	ens_increase_mwh: float
	"""ENS with this branch out minus ENS in the base case. The branch's
	contribution to unserved energy."""

	share: float = 0.0
	diverged_snapshots: int = 0
	"""Snapshots where the branch's outage islanded the network. A diverged
	solve is recorded, not propagated."""

	overloaded_snapshots: int = 0


class TlensRanking(AleaConfig):
	"""The ranked TLENS table for a network.

	Deterministic across runs (AD-8): ties are broken by branch index, so the
	ranking does not depend on the order a sort happened to produce.
	"""

	entries: list[TlensEntry]
	base_ens_mwh: float
	n_snapshots: int
	n_branches: int
	total_ens_mwh: float
	"""Sum of every branch's ENS increase. The denominator of ``share``."""

	parameters: dict[str, Any] = Field(default_factory=dict)

	def top(self, n: int) -> list[TlensEntry]:
		"""The ``n`` most critical branches, in rank order."""
		return self.entries[:n]

	def rank_of(self, branch: int) -> int:
		"""The 1-based rank of a branch, or 0 when it is absent."""
		for position, entry in enumerate(self.entries, start=1):
			if entry.branch == branch:
				return position
		return 0


class ContingencySummary(AleaConfig):
	"""Aggregate of an N-1 sweep, small enough to serialise."""

	n_contingencies: int
	n_snapshots: int
	base_ens_mwh: float
	worst_contingency: int
	worst_ens_mwh: float
	diverged_fraction: float
	"""Fraction of (contingency, snapshot) pairs whose DC solve did not
	converge. A high value means the network islands easily under N-1, which
	is a resilience finding rather than a numerical one."""

	overloaded_fraction: float
	parameters: dict[str, Any] = Field(default_factory=dict)


class MitigationOption(AleaConfig):
	"""One loss-reduction measure to be ranked.

	The physical effect is expressed as parameters on the network it edits —
	``resistance_scale`` for reconductoring, ``voltage_scale`` for a voltage
	upgrade, ``added_susceptance_pu`` for a parallel circuit — rather than as an
	opaque callable, so an option is data that can be versioned and reviewed.
	"""

	name: str
	kind: str = "reconductoring"
	capex_usd: float = Field(ge=0.0)
	description: str = ""
	"""What the option physically is. A payback without a description is a
	number with no engineering content."""

	branches: list[int] = Field(default_factory=list)
	"""Branches the option touches, when it is a branch-level measure."""

	resistance_scale: float = Field(default=1.0, gt=0.0)
	"""Factor applied to the touched branches' resistance. Below 1 is a larger
	conductor and lower loss."""

	voltage_scale: float = Field(default=1.0, gt=0.0)
	"""Factor applied to the touched branches' nominal voltage. Above 1 is a
	voltage upgrade, which lowers current and therefore ``I^2 R`` loss."""

	added_susceptance_pu: float = Field(default=0.0, ge=0.0)
	"""Susceptance of a parallel circuit added to each touched branch."""

	@model_validator(mode="after")
	def _an_option_changes_something(self) -> MitigationOption:
		if (
			self.resistance_scale == 1.0
			and self.voltage_scale == 1.0
			and self.added_susceptance_pu == 0.0
		):
			raise ValueError(
				f"option {self.name!r} changes nothing: set resistance_scale, "
				f"voltage_scale or added_susceptance_pu"
			)
		return self


class MitigationResult(AleaConfig):
	"""One option's benefit, computed over the **whole** hourly series.

	``annual_savings_usd`` is the sum of the per-snapshot loss reductions times
	the price at that snapshot — never ``loss_reduction x 8760 x price``, which
	treats one snapshot as representative of every hour. Losses vary with load
	and dispatch, so a single-snapshot figure is a number with no error bar that
	will be believed (07-layer4 §7.1).
	"""

	option: str
	kind: str
	capex_usd: float
	annual_loss_reduction_mwh: float
	annual_savings_usd: float
	payback_years: float | None
	"""None when savings are below the measurement floor. Not ``inf``: ``inf``
	reads as "never", which is a different claim from "unmeasurable"."""

	n_snapshots: int
	notes: str = ""

	@property
	def is_worthwhile(self) -> bool:
		"""Whether a payback exists at all."""
		return self.payback_years is not None


__all__ = [
	"DECOMPOSITION_TOLERANCE",
	"ContingencySummary",
	"FlowResult",
	"LoadingEntry",
	"LoadingRanking",
	"LossComponents",
	"LossConfig",
	"MitigationOption",
	"MitigationResult",
	"TlensEntry",
	"TlensRanking",
]
