# SPDX-License-Identifier: MIT
"""Provenance and uncertainty models.

Every artefact on disk carries provenance. ``uncertainty`` is required even
when it is zero, because a schema that makes it optional produces artefacts
that cannot answer "is this measured or modelled?" -- and that answer matters
most for the seven CRITICAL-tier countries whose values are proxies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alea._uuid7 import uuid7str


class Licence(StrEnum):
	"""How an artefact may be redistributed."""

	CC_BY_4_0 = "CC-BY-4.0"
	ODBL = "ODbL-1.0"
	CC0 = "CC0-1.0"
	COPERNICUS = "Copernicus"
	PUBLIC_DOMAIN = "public-domain"
	PROPRIETARY = "proprietary"
	UNKNOWN = "unknown"


class Basis(StrEnum):
	"""How a number came to exist.

	This is the field that keeps a proxy estimate visually distinct from a
	metered value all the way to a published report. See 09-layer6 §2.
	"""

	MEASURED = "measured"
	MODELLED = "modelled"
	PROXY = "proxy"
	FORECAST = "forecast"


class Provenance(BaseModel):
	"""Where a datum came from, and how much to trust it."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	source_id: str
	"""Registry key, e.g. ``worldbank_grid_map``."""
	source_url: str = ""
	retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
	checksum: str = ""
	"""sha256 of the raw payload. Empty only for a hand-entered constant."""
	licence: Licence = Licence.UNKNOWN
	uncertainty: float = Field(default=0.0, ge=0.0)
	"""Relative uncertainty. 0.0 means exact."""
	uncertainty_basis: str = ""
	"""``measured`` | ``published RMSE`` | ``proxy`` | a citation."""
	basis: Basis = Basis.MEASURED
	notes: str = ""

	@model_validator(mode="after")
	def _uncertainty_is_justified(self) -> Provenance:
		# Non-zero uncertainty with no stated basis is an uninterpretable
		# number. It will be quoted in a report and nobody will know what it
		# means.
		if self.uncertainty > 0 and not self.uncertainty_basis:
			raise ValueError(
				f"non-zero uncertainty ({self.uncertainty}) requires "
				f"uncertainty_basis explaining what the number measures"
			)
		return self

	@model_validator(mode="after")
	def _proxy_is_flagged(self) -> Provenance:
		# A proxy with zero uncertainty is a claim that the substitute is exact,
		# which is never true. Proxy values carry uncertainty.
		if self.basis is Basis.PROXY and self.uncertainty <= 0:
			raise ValueError(
				"basis='proxy' requires uncertainty > 0; a proxy is not exact"
			)
		return self


class DerivedProvenance(Provenance):
	"""Provenance of a computed artefact.

	Records the checksums of what it was computed from, so a result traces to
	the exact bytes that produced it.
	"""

	inputs: list[str] = Field(default_factory=list)
	code_version: str = ""
	run_id: str = Field(default_factory=uuid7str)
	parameters: dict[str, Any] = Field(default_factory=dict)

	@model_validator(mode="after")
	def _derived_records_its_inputs(self) -> DerivedProvenance:
		if not self.inputs:
			raise ValueError(
				"a derived artefact must record the checksums of its inputs; "
				"without them the result cannot be traced to what produced it"
			)
		return self


class ProvenanceRecord(BaseModel):
	"""A set of provenance entries, one per contributing source.

	An artefact built from several inputs has several provenances. The
	aggregate uncertainty is the maximum of the parts, which is conservative
	and is the only combination rule that needs no independence assumption --
	inputs derived from the same upstream dataset are not independent, so
	root-sum-square would understate the error.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	entries: list[Provenance] = Field(min_length=1)

	@property
	def uncertainty(self) -> float:
		return max(entry.uncertainty for entry in self.entries)

	@property
	def basis(self) -> Basis:
		"""The weakest basis among the inputs.

		A result computed from a proxy is at best a proxy, whatever else went
		into it. Taking the strongest basis would let one measured input launder
		a proxied one.
		"""
		order = [Basis.MEASURED, Basis.FORECAST, Basis.MODELLED, Basis.PROXY]
		return max(self.entries, key=lambda e: order.index(e.basis)).basis

	@property
	def uncertainty_basis(self) -> str:
		worst = max(self.entries, key=lambda e: e.uncertainty)
		return worst.uncertainty_basis


__all__ = [
	"Basis",
	"DerivedProvenance",
	"Licence",
	"Provenance",
	"ProvenanceRecord",
]
