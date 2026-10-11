# SPDX-License-Identifier: MIT
"""Artefact schemas for the PyPSA-Earth seam.

AD-1: PyPSA-Earth is a Snakemake workflow, not a library, so what crosses the
seam is files. A file that arrives without a declared schema carries whatever
columns the producing workflow happened to write that week, and the failure mode
is silent: a `capacity_mw` column read as `p_nom` in kW understates a fleet by
1000x and produces a plausible-looking capacity mix.

Every artefact ALEA reads from the seam is validated against a model here
*before* it reaches a network builder. Validation names the missing column and
the artefact, because "KeyError: 'bus'" twelve frames deep in PyPSA is a bug
report nobody can act on.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from alea.registry import Carrier

Dtype = Literal["float", "int", "str", "bool"]


class SchemaError(ValueError):
	"""An artefact does not match its declared schema."""


class ColumnSpec(BaseModel):
	"""One column: its name, its type, and its unit.

	The unit is not decoration. It is the only place a reader learns that
	`capacity` is MW and not GW, and a unit that lives only in a notebook is a
	unit that will be lost.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	name: str
	dtype: Dtype
	unit: str = ""
	description: str = ""


class ArtefactSchema(BaseModel):
	"""A named set of columns an artefact must carry."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	name: str
	columns: tuple[ColumnSpec, ...]
	allow_extra_columns: bool = True
	"""Extra columns are allowed by default.

	The seam's producer writes more than ALEA reads, and refusing the extras
	would break on every upstream release. What is refused is a *missing*
	column, and a column whose values cannot be read as its declared type.
	"""

	def column(self, name: str) -> ColumnSpec:
		for spec in self.columns:
			if spec.name == name:
				return spec
		raise SchemaError(f"{self.name}: no column {name!r} in schema")

	@property
	def names(self) -> tuple[str, ...]:
		return tuple(spec.name for spec in self.columns)

	def check(self, frame: pd.DataFrame, *, artefact: str = "") -> pd.DataFrame:
		"""Check a frame against the schema and return it unchanged.

		Returns the frame rather than a copy so a caller can chain the call into
		a read without paying for a duplicate of a continental table.

		Named ``check`` rather than ``validate`` because ``BaseModel.validate``
		is a Pydantic classmethod and shadowing it with an instance method makes
		the model unusable as a model.
		"""
		assert isinstance(frame, pd.DataFrame), f"expected a DataFrame, got {type(frame).__name__}"
		where = artefact or self.name

		missing = [name for name in self.names if name not in frame.columns]
		if missing:
			raise SchemaError(
				f"{where}: missing required column(s) {', '.join(missing)}; "
				f"schema {self.name!r} requires {', '.join(self.names)}"
			)

		if not self.allow_extra_columns:
			extra = [str(c) for c in frame.columns if c not in self.names]
			if extra:
				raise SchemaError(f"{where}: unexpected column(s) {', '.join(extra)}")

		for spec in self.columns:
			series = frame[spec.name]
			if spec.dtype in ("float", "int"):
				# Refused rather than coerced: a string in a numeric column means
				# the producer wrote a sentinel ("n/a", "-") and coercing it turns
				# the sentinel into NaN in some rows and a crash in others.
				if not bool(pd.api.types.is_numeric_dtype(series)):
					try:
						pd.to_numeric(series, errors="raise")
					except (ValueError, TypeError) as exc:
						raise SchemaError(
							f"{where}.{spec.name}: declared {spec.dtype} but is not "
							f"numeric ({exc})"
						) from exc
				if spec.dtype == "int" and bool(series.isna().any()):
					raise SchemaError(
						f"{where}.{spec.name}: declared int but has "
						f"{int(series.isna().sum())} missing value(s)"
					)
			elif spec.dtype == "bool" and not bool(pd.api.types.is_bool_dtype(series)):
				raise SchemaError(f"{where}.{spec.name}: declared bool but is {series.dtype}")

		return frame

	def empty_frame(self) -> pd.DataFrame:
		"""An empty frame with the schema's columns, for building from nothing."""
		return pd.DataFrame({spec.name: pd.Series(dtype="float64") for spec in self.columns})


# --------------------------------------------------------------------------
# The four artefacts that cross the seam
# --------------------------------------------------------------------------

TOPOLOGY = ArtefactSchema(
	name="topology",
	columns=(
		ColumnSpec(name="line_id", dtype="str", description="Stable line identifier."),
		ColumnSpec(name="from_lon", dtype="float", unit="deg", description="Endpoint A longitude."),
		ColumnSpec(name="from_lat", dtype="float", unit="deg", description="Endpoint A latitude."),
		ColumnSpec(name="to_lon", dtype="float", unit="deg", description="Endpoint B longitude."),
		ColumnSpec(name="to_lat", dtype="float", unit="deg", description="Endpoint B latitude."),
		ColumnSpec(name="voltage_kv", dtype="float", unit="kV", description="Nominal voltage."),
		ColumnSpec(name="length_km", dtype="float", unit="km", description="Route length."),
		ColumnSpec(
			name="capacity_mva",
			dtype="float",
			unit="MVA",
			description="Thermal rating. May be NaN where the source omits it.",
		),
	),
)

FLEET = ArtefactSchema(
	name="fleet",
	columns=(
		ColumnSpec(name="plant_id", dtype="str", description="Stable plant identifier."),
		ColumnSpec(name="name", dtype="str", description="Human-readable plant name."),
		ColumnSpec(name="carrier", dtype="str", description="Registry carrier name."),
		ColumnSpec(name="capacity_mw", dtype="float", unit="MW", description="Installed capacity."),
		ColumnSpec(name="lon", dtype="float", unit="deg", description="Plant longitude."),
		ColumnSpec(name="lat", dtype="float", unit="deg", description="Plant latitude."),
		ColumnSpec(name="commissioning_year", dtype="int", unit="year", description="COD."),
		ColumnSpec(
			name="lifetime_years",
			dtype="int",
			unit="year",
			description="Technical lifetime. Defaults applied upstream.",
		),
	),
)

DEMAND = ArtefactSchema(
	name="demand",
	columns=(
		ColumnSpec(name="bus_id", dtype="str", description="Bus the load attaches to."),
		ColumnSpec(name="timestamp", dtype="str", unit="ISO 8601", description="Hour beginning."),
		ColumnSpec(name="load_mw", dtype="float", unit="MW", description="Hourly demand."),
	),
)

PROFILE = ArtefactSchema(
	name="profile",
	columns=(
		ColumnSpec(name="bus_id", dtype="str", description="Bus the profile attaches to."),
		ColumnSpec(name="carrier", dtype="str", description="Registry carrier name."),
		ColumnSpec(name="timestamp", dtype="str", unit="ISO 8601", description="Hour beginning."),
		ColumnSpec(
			name="capacity_factor",
			dtype="float",
			unit="p.u.",
			description="Output per unit of installed capacity, in [0, 1].",
		),
	),
)


def check_carriers(frame: pd.DataFrame, column: str, *, artefact: str = "") -> None:
	"""Refuse a carrier name the registry does not know.

	A carrier that is not in the registry is a typo or a new technology that
	needs a decision about its emissions, its variability and whether it counts
	as renewable. Silently accepting it produces a fleet with one plant in a
	carrier nothing else in the platform can interpret.
	"""
	known = {c.value for c in Carrier}
	unknown = sorted({str(v) for v in frame[column].dropna().unique()} - known)
	if unknown:
		raise SchemaError(
			f"{artefact or 'artefact'}: unknown carrier(s) {', '.join(unknown)}; "
			f"add them to alea.registry.technologies before using them"
		)


def schema_by_name(name: str) -> ArtefactSchema:
	"""Look a schema up by its artefact name."""
	registry: dict[str, ArtefactSchema] = {
		"topology": TOPOLOGY,
		"fleet": FLEET,
		"demand": DEMAND,
		"profile": PROFILE,
	}
	try:
		return registry[name]
	except KeyError as exc:
		raise SchemaError(f"no schema named {name!r}; have {sorted(registry)}") from exc


__all__ = [
	"DEMAND",
	"FLEET",
	"PROFILE",
	"TOPOLOGY",
	"ArtefactSchema",
	"ColumnSpec",
	"SchemaError",
	"check_carriers",
	"schema_by_name",
]
