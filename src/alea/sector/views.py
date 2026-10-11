# SPDX-License-Identifier: MIT
"""Sector-coupling models.

Two families live here. The ``views`` are what the Python sector modules return:
they carry a component specification *and* the source of every physical
parameter on it. The ``rows`` are the flattened table those views are written
as, so a whole coupled network has one addressable, provenance-carrying
artefact (AD-4).

The split matters because Layer 2's most common failure is not a wrong number
but an untraceable one. A ``LinkRow`` cannot be constructed without naming where
its efficiency came from, which makes ``test_efficiency_has_source`` a property
of the type rather than a test someone has to remember to write.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from alea._uuid7 import uuid7str


def _non_empty(value: str) -> str:
	"""A source is a citation, not a placeholder.

	An empty string, ``"TBD"`` or ``"assumed"`` is a source field that exists and
	carries nothing -- exactly the untraceable number the plan forbids, wearing
	the shape of a traceable one. Whitespace-only values are refused for the same
	reason.
	"""
	stripped = value.strip()
	if not stripped:
		raise ValueError("a source is required and may not be blank")
	if stripped.lower() in {"tbd", "todo", "n/a", "na", "assumed", "default"}:
		raise ValueError(
			f"{value!r} is a placeholder, not a source; name the citation that "
			f"fixes the number"
		)
	return stripped


Source = Annotated[str, AfterValidator(_non_empty)]
"""A citation for one physical parameter. Non-empty, never a placeholder."""


class Parameter(BaseModel):
	"""One physical constant, with its value and where the value came from.

	``uncertainty`` is required with its basis for the same reason
	``Provenance`` requires it (AD-6): a number quoted in a report with no error
	bar is a number that cannot be argued with.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	value: float
	unit: str
	source: Source
	uncertainty: float = Field(default=0.0, ge=0.0)
	uncertainty_basis: str = ""
	notes: str = ""

	@model_validator(mode="after")
	def _uncertainty_is_justified(self) -> Parameter:
		if self.uncertainty > 0 and not self.uncertainty_basis:
			raise ValueError(
				f"non-zero uncertainty ({self.uncertainty}) on {self.source!r} "
				f"requires uncertainty_basis saying what it measures"
			)
		return self


class Sector(StrEnum):
	"""The six sectors Layer 2 couples to the electricity network."""

	HYDROGEN = "hydrogen"
	HEAT = "heat"
	TRANSPORT = "transport"
	INDUSTRY = "industry"
	WATER = "water"
	RENEWABLES = "renewables"


class CouplingView(BaseModel):
	"""A sector asset that would be added to the network.

	Returned by every ``add_*``/``build_*`` function and never mutated: the
	network is assembled from these, and a view that changes after the network
	was built makes the network unreproducible from the views that claim to
	describe it.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	asset: str
	"""The PyPSA component name this becomes: ``Bus``, ``Link``, ``Store``,
	``Load``, ``Generator``, ``StorageUnit``."""

	name: str
	sector: Sector
	carrier: str
	bus0: str = ""
	bus1: str = ""
	bus2: str = ""
	bus3: str = ""

	parameters: dict[str, Parameter] = Field(default_factory=dict)
	"""Every physical parameter, keyed by the network column it lands in.

	Efficiency, COP, standing loss, and degradation all live here so that no
	caller can add a link with an efficiency whose source was dropped in a
	function signature.
	"""

	attributes: dict[str, Any] = Field(default_factory=dict)
	"""Non-physical network columns: ``p_nom``, ``p_nom_extendable``, ``e_nom``,
	``capital_cost``, ``bus``, ``carrier``, and so on.

	Kept separate from ``parameters`` because a capacity is an assumption about
	the scenario while an efficiency is a property of the technology, and only
	the second needs a literature citation.
	"""

	time_series: dict[str, list[float]] = Field(default_factory=dict)
	"""Per-snapshot overrides, keyed by the network column they replace.

	A temperature-dependent COP and an EV availability profile are the two
	places the plan insists on a series rather than a constant (05-layer2 §2.2,
	§2.3). Held as plain lists so a view stays JSON-serialisable and the
	artefact needs no pandas to read back.
	"""

	source: Source
	"""The pathway or configuration this asset as a whole comes from."""

	provenance_id: str = Field(default_factory=uuid7str)
	notes: str = ""

	@property
	def physical(self) -> dict[str, float]:
		"""The parameter values, ready for the network's static table."""
		return {key: parameter.value for key, parameter in self.parameters.items()}

	@property
	def parameter_sources(self) -> dict[str, str]:
		"""``column -> citation``, for the artefact's provenance record."""
		return {key: parameter.source for key, parameter in self.parameters.items()}

	def as_row(self) -> LinkRow:
		"""Flatten to one artefact row."""
		return LinkRow(
			asset=self.asset,
			name=self.name,
			sector=self.sector,
			carrier=self.carrier,
			bus0=self.bus0,
			bus1=self.bus1,
			bus2=self.bus2,
			bus3=self.bus3,
			values={**self.attributes, **self.physical},
			time_series_keys=sorted(self.time_series),
			parameter_sources=self.parameter_sources,
			source=self.source,
			provenance_id=self.provenance_id,
			notes=self.notes,
		)


class LinkRow(BaseModel):
	"""One sector asset as a table row.

	``values`` is heterogeneous on purpose: the column set differs by component
	type, and a wide schema with eighty mostly-null columns is harder to read
	than a narrow one whose keys are the network's own column names.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	asset: str
	name: str
	sector: Sector
	carrier: str
	bus0: str = ""
	bus1: str = ""
	bus2: str = ""
	bus3: str = ""
	values: dict[str, Any] = Field(default_factory=dict)
	time_series_keys: list[str] = Field(default_factory=list)
	"""Columns carried as a per-snapshot series rather than a constant.

	Recorded so a reader of the artefact can tell a link with a fixed
	efficiency from one whose efficiency is a series, without opening the
	network -- and so a series whose source was dropped is visible here.
	"""

	parameter_sources: dict[str, str] = Field(default_factory=dict)
	source: Source
	provenance_id: str
	notes: str = ""

	@model_validator(mode="after")
	def _physical_parameters_are_sourced(self) -> LinkRow:
		# Every physical column -- constant or series -- carries a citation. A
		# capacity is a scenario choice and is exempt; an efficiency is not. There
		# is deliberately no ``cop`` here: a heat pump's COP is emitted as
		# ``efficiency`` (the PyPSA column it lands in), so a ``cop`` name would
		# gate a column no view ever produces.
		physical = {
			"efficiency",
			"efficiency2",
			"efficiency3",
			"efficiency4",
			"standing_loss",
			"specific_energy",
			"p_max_pu",
			"p_min_pu",
		}
		unsourced = sorted(
			key
			for key in (*self.values, *self.time_series_keys)
			if key.split("_")[0] in physical and key not in self.parameter_sources
		)
		if unsourced:
			raise ValueError(
				f"{self.name!r} carries physical parameters with no source: "
				f"{', '.join(unsourced)}; every efficiency and COP is traceable "
				f"(05-layer2 §4)"
			)
		return self


class SectorBuild(BaseModel):
	"""The result of adding one sector to a network."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	sector: Sector
	rows: list[LinkRow] = Field(default_factory=list)
	views: list[CouplingView] = Field(default_factory=list)
	"""The views the rows were flattened from.

	Held alongside the rows because a row drops the per-snapshot series -- a COP
	profile, an EV availability curve, an export obligation -- and reconstructing
	a network from rows alone would therefore produce a sector that looks
	complete and behaves differently. The rows are what goes to the artefact; the
	views are what goes onto the network.
	"""

	enabled: bool = True
	reason: str = ""
	"""Why the sector was skipped, when it was. An empty result is recorded with
	its reason, never silently: a sector that produced nothing because it was
	disabled and one that produced nothing because it is broken look identical
	in the output otherwise."""

	@model_validator(mode="after")
	def _skips_are_explained(self) -> SectorBuild:
		if not self.enabled and not self.reason:
			raise ValueError(
				f"sector {self.sector} is disabled with no reason; a skip without "
				f"a stated cause is indistinguishable from a failure"
			)
		return self

	@property
	def names(self) -> list[str]:
		return [row.name for row in self.rows]


class CouplingReport(BaseModel):
	"""What a whole sector-coupled build did.

	``base_unchanged`` is the structural gate's input (05-layer2 §6): the base
	electricity network's digest before and after the coupling layer ran. If the
	coupling layer mutated the base, the electricity-only result is no longer
	reproducible and the comparison between the two models is meaningless.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	builds: list[SectorBuild] = Field(default_factory=list)
	base_digest_before: str
	base_digest_after: str
	rows: list[LinkRow] = Field(default_factory=list)

	@model_validator(mode="after")
	def _coupling_is_additive(self) -> CouplingReport:
		if self.base_digest_before != self.base_digest_after:
			raise ValueError(
				"the coupling layer changed the base electricity network; sector "
				"coupling extends Layer 1 and must leave its result reproducible "
				"(05-layer2 §1)"
			)
		return self

	@property
	def base_unchanged(self) -> bool:
		return self.base_digest_before == self.base_digest_after

	@property
	def sectors(self) -> list[Sector]:
		return [build.sector for build in self.builds if build.enabled]

	@property
	def asset_counts(self) -> dict[str, int]:
		counts: dict[str, int] = {}
		for row in self.rows:
			counts[row.sector.value] = counts.get(row.sector.value, 0) + 1
		return counts


class MassBalance(BaseModel):
	"""A carrier's conservation check: produced = consumed + stored + exported.

	``residual`` is signed, and its sign is the diagnosis. A negative residual
	means the network lost carrier somewhere -- a leak. A positive one means a
	balance term is missing from the accounting, which is a modelling defect of
	the same severity even though no energy disappeared.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	carrier: str
	produced_mwh: float
	consumed_mwh: float
	storage_delta_mwh: float
	exported_mwh: float
	residual_mwh: float
	tolerance_mwh: float
	unit: Literal["MWh"] = "MWh"

	@model_validator(mode="after")
	def _residual_is_consistent(self) -> MassBalance:
		expected = (
			self.produced_mwh
			- self.consumed_mwh
			- self.storage_delta_mwh
			- self.exported_mwh
		)
		if abs(expected - self.residual_mwh) > 1e-6:
			raise ValueError(
				f"residual {self.residual_mwh} does not equal the balance terms "
				f"({expected}); a balance whose own arithmetic is wrong is worse "
				f"than no balance"
			)
		return self

	@property
	def closes(self) -> bool:
		return abs(self.residual_mwh) <= self.tolerance_mwh


class EnergyBalance(MassBalance):
	"""Alias with the energy framing used in the gate table (05-layer2 §6).

	Identical fields: for every carrier except hydrogen the balance is already in
	MWh, and for hydrogen MWh(LHV) is the unit the electrolyser efficiency is
	defined in, so the two gates are the same computation on different carriers.
	"""


__all__ = [
	"CouplingReport",
	"CouplingView",
	"EnergyBalance",
	"LinkRow",
	"MassBalance",
	"Parameter",
	"Sector",
	"SectorBuild",
	"Source",
]
