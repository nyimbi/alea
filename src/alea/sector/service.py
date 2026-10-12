# SPDX-License-Identifier: MIT
"""Layer 2 orchestration.

The entry points here are what the CLI and the workflow layer call. They do
three things the sector modules do not: they turn a ``Config`` into a coupled
network, they write the coupling artefact with its provenance, and they run the
gates the plan defines (05-layer2 §6) so a caller gets a result only if the
result is one the gates would accept.

**What this layer deliberately does not do.** It does not solve. Layer 1 owns
the solve, and a sector-coupled solve is the same solve with more components --
running it here would duplicate the solver selection, the aggregation gate and
the determinism discipline that belong to ``alea.planning``. ``couple_network``
hands back a network that ``alea.planning`` solves.

**Why the gates run at build time and not only in tests.** The plan's gates are
the acceptance criteria for the layer, and a caller that couples a network,
solves it and publishes a number without them has published a number nobody
checked. They are cheap next to a solve, so they run here, and a failure raises
before the artefact is written.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError, DerivedProvenance, write_artefact
from alea.io.pipeline import stage
from alea.logging import get_logger, new_run_id
from alea.provenance.models import Basis, Licence, Provenance
from alea.registry import technologies
from alea.sector._util import as_index
from alea.sector.coupling import base_digest, couple
from alea.sector.views import CouplingReport, Sector

if TYPE_CHECKING:
	import pypsa

logger = get_logger(__name__)

CODE_VERSION = "0.1.0"
"""Recorded on every derived artefact so a result names the code that made it."""


class CouplingResult(BaseModel):
	"""What one sector-coupled build produced."""

	model_config = ConfigDict(extra="forbid", frozen=True)

	network: Any
	"""The coupled ``pypsa.Network``. Excluded from serialisation: it is not
	JSON, and the artefact carries its checksum instead."""

	report: CouplingReport
	run_id: str
	source_pairs: dict[str, str] = Field(default_factory=dict)
	"""``asset.parameter -> citation`` for every physical parameter in the build.

	Lifted out of the rows so the efficiency/source pairs are readable in one
	place, which is what ``test_efficiency_has_source`` and a human reviewer both
	want (05-layer2 §4).
	"""

	@property
	def assets(self) -> int:
		return len(self.report.rows)

	@property
	def base_unchanged(self) -> bool:
		return self.report.base_unchanged


def source_pairs(report: CouplingReport) -> dict[str, str]:
	"""Every physical parameter's source, keyed ``asset.parameter``.

	Duplicate keys are an error rather than a last-write-wins: two assets with
	the same name means one of them silently replaced the other on the network,
	which is a coupling defect that would otherwise surface as a missing sector.
	"""
	pairs: dict[str, str] = {}
	for row in report.rows:
		for parameter, source in row.parameter_sources.items():
			key = f"{row.name}.{parameter}"
			if key in pairs:
				raise ValueError(
					f"duplicate asset parameter {key!r}; two assets share a name "
					f"and one replaced the other on the network"
				)
			pairs[key] = source
	return pairs


def assert_efficiency_has_source(report: CouplingReport) -> None:
	"""Gate: every efficiency and COP is traceable to a source (05-layer2 §6).

	The ``LinkRow`` validator already refuses an unsourced physical parameter, so
	this asserts the property survives the artefact boundary rather than
	re-deriving it. It is not redundant: a row can be constructed by a path that
	bypasses the validator (``model_construct``, or a row read back from a
	file), and this is the check that catches it.
	"""
	for row in report.rows:
		for column, value in row.values.items():
			# The same column set and the same matching the ``LinkRow`` validator
			# uses -- every ``efficiency``/``efficiency2``/... port and every
			# other physical column. This check exists precisely for a row that
			# bypassed that validator (``model_construct``, or a row read back
			# from a file), so a narrower set here than there leaves the bypass
			# open for the ports it omits: an industrial link's co-product
			# efficiency or a methanol link's negative CO2 coefficient would pass
			# unsourced. There is deliberately no ``cop``: a heat pump's COP lands
			# on ``efficiency`` (heat.py), so ``cop`` would name a column no view
			# emits. The degradation cost is a ``marginal_cost`` parameter and is
			# checked by ``assert_v2g_has_degradation_cost`` instead.
			if column.split("_")[0] not in {
				"efficiency",
				"efficiency2",
				"efficiency3",
				"efficiency4",
				"standing_loss",
				"specific_energy",
				"p_max_pu",
				"p_min_pu",
			}:
				continue
			if not isinstance(value, int | float):
				continue
			if column not in row.parameter_sources:
				raise ValueError(
					f"{row.name!r}.{column}={value} has no source; an efficiency "
					f"nobody can trace is how a sector result becomes "
					f"indefensible (05-layer2 §4)"
				)
		# A physical column carried as a series is gated the same way. The row
		# validator covers both; a bypassed row that named its series keys but
		# dropped their sources would otherwise pass here.
		for column in row.time_series_keys:
			if column.split("_")[0] not in {
				"efficiency",
				"efficiency2",
				"efficiency3",
				"efficiency4",
				"standing_loss",
				"specific_energy",
				"p_max_pu",
				"p_min_pu",
			}:
				continue
			if column not in row.parameter_sources:
				raise ValueError(
					f"{row.name!r}.{column} is carried as a series with no source; "
					f"every efficiency and COP is traceable (05-layer2 §4)"
				)


def assert_v2g_has_degradation_cost(config: Config, report: CouplingReport) -> None:
	"""Gate: V2G without a degradation cost fails (05-layer2 §6).

	Checked against the built links rather than only the config, because the
	config validator can be bypassed by a caller that constructs a
	``SectorConfig`` with ``model_construct`` or that adds a V2G link by hand.
	"""
	if not config.sector.v2g_enabled:
		return
	v2g_rows = [row for row in report.rows if row.name.startswith("ev_v2g")]
	if not v2g_rows:
		raise ValueError(
			"v2g_enabled is set but no V2G link was built; the config and the "
			"network disagree about whether the fleet can export"
		)
	for row in v2g_rows:
		# The degradation cost is recorded under ``marginal_cost`` -- the column
		# PyPSA actually charges the link on -- so the source and the value come
		# from the same key. Reading the source from a ``degradation_cost``
		# parameter while the value lived in ``marginal_cost`` was a bridge
		# between two names, and a row that renamed either one would have passed
		# this gate while carrying an unsourced cost.
		cost = row.parameter_sources.get("marginal_cost")
		value = row.values.get("marginal_cost", 0.0)
		if not cost or not isinstance(value, int | float) or value <= 0.0:
			raise ValueError(
				f"{row.name!r} has no positive degradation cost; free storage is "
				f"not a modelling result (05-layer2 §2.3)"
			)


def assert_sector_is_additive(report: CouplingReport) -> None:
	"""Gate: the coupling layer left the base electricity network unchanged.

	``CouplingReport`` refuses to be constructed with mismatched digests, so this
	is a second, explicit statement of the same invariant at the service
	boundary -- where a caller looking for the gate will find it.
	"""
	if not report.base_unchanged:
		raise ValueError(
			"the coupling layer changed the base network; the electricity-only "
			"result is no longer reproducible and the comparison between the two "
			"models is meaningless (05-layer2 §1)"
		)


def assert_kenya_portfolio(report: CouplingReport) -> None:
	"""Gate: all four Kenya-critical technologies are present.

	Only asserted when the renewable sector was actually built. A caller who
	built a portfolio elsewhere and passed it in has already run the check.
	"""
	from alea.sector.renewables import kenya_portfolio_gate

	renewable_rows = [row for row in report.rows if row.sector is Sector.RENEWABLES]
	if renewable_rows:
		kenya_portfolio_gate(renewable_rows)


def geothermal_crosscheck(report: CouplingReport) -> Any | None:
	"""The Kenya geothermal cross-check the renewable build carried, if any.

	``crosscheck_geothermal`` was exported and its ``require`` gate existed, but
	nothing called it -- so criterion 5 held as a definition rather than as an
	artefact. It is now computed in ``build_renewables`` and read back here for
	the provenance and the coupling artefact.
	"""
	for build in report.builds:
		if build.sector is Sector.RENEWABLES and build.geothermal_crosscheck is not None:
			return build.geothermal_crosscheck
	return None


def couple_network(
	config: Config,
	network: pypsa.Network,
	*,
	weights: list[float] | None = None,
	water_enabled: bool = False,
	run_gates: bool = True,
	**sector_options: Any,
) -> CouplingResult:
	"""Extend an electricity network with the sectors ``config`` enables.

	The gates run before the result is returned, so a caller cannot hold a
	coupled network that fails them without having asked not to check.
	"""
	assert network is not None, "couple_network needs a base network"
	assert config is not None, "couple_network needs a config"
	run_id = new_run_id()
	index = as_index(pd.DatetimeIndex(network.snapshots))
	before = base_digest(network)

	coupled, report = couple(
		config,
		network,
		snapshots=index,
		weights=weights,
		water_enabled=water_enabled,
		**sector_options,
	)
	pairs = source_pairs(report)
	result = CouplingResult(network=coupled, report=report, run_id=run_id, source_pairs=pairs)

	if run_gates:
		assert_sector_is_additive(report)
		assert_efficiency_has_source(report)
		assert_v2g_has_degradation_cost(config, report)
		assert_kenya_portfolio(report)

	logger.info(
		"sector.coupled",
		run_id=run_id,
		assets=result.assets,
		sectors=[sector.value for sector in report.sectors],
		parameters_sourced=len(pairs),
		base_digest_before=before[:12],
		base_digest_after=report.base_digest_after[:12],
	)
	assert result.base_unchanged, "the coupling layer mutated the base network"
	return result


def sector_provenance(
	config: Config,
	result: CouplingResult,
	*,
	inputs: list[str],
	base_checksum: str = "",
) -> DerivedProvenance:
	"""Provenance for the coupling artefact.

	The efficiency/source pairs live in ``parameters`` because that is the field
	the plan asks for them in: an efficiency recorded only in the config that
	produced the run is an efficiency that cannot be read back from the result
	(05-layer2 §4, AD-6).

	The worst basis among the contributing sources is taken, never the best. A
	sector-coupled result built partly from proxy geothermal potential is at best
	a proxy result, whatever else went into it, and ``ProvenanceRecord``'s rule
	is the one applied here.
	"""
	assert inputs, "a derived artefact must record the checksums of its inputs"
	entries: list[Provenance] = []
	for source_id, basis in (
		("sector_coupling", Basis.MODELLED),
		("geothermal_atlas", Basis.PROXY),
		("irena_costs", Basis.MEASURED),
	):
		entries.append(
			Provenance(
				source_id=source_id,
				licence=Licence.CC_BY_4_0 if source_id != "irena_costs" else Licence.PROPRIETARY,
				basis=basis,
				uncertainty=0.25 if basis is Basis.PROXY else 0.0,
				uncertainty_basis=(
					"per-field potential depends on reservoir conditions not "
					"measured at depth"
					if basis is Basis.PROXY
					else ""
				),
			)
		)
	from alea.provenance.models import ProvenanceRecord

	record = ProvenanceRecord(entries=entries)
	crosscheck = geothermal_crosscheck(result.report)
	return DerivedProvenance(
		source_id="sector_coupling",
		licence=Licence.CC_BY_4_0,
		basis=record.basis,
		uncertainty=record.uncertainty,
		uncertainty_basis=record.uncertainty_basis or "worst basis among contributing sources",
		inputs=inputs,
		code_version=CODE_VERSION,
		run_id=result.run_id,
		parameters={
			"efficiency_sources": result.source_pairs,
			"sectors": [sector.value for sector in result.report.sectors],
			"assets": result.assets,
			"base_digest": result.report.base_digest_before,
			"base_checksum": base_checksum,
			"hydrogen_enabled": config.sector.hydrogen_enabled,
			"heat_pumps_enabled": config.sector.heat_pumps_enabled,
			"v2g_enabled": config.sector.v2g_enabled,
			"v2g_degradation_usd_per_mwh": config.sector.v2g_degradation_usd_per_mwh,
			"industry_steel": config.sector.industry_steel,
			"industry_cement": config.sector.industry_cement,
			"industry_chemicals": config.sector.industry_chemicals,
			"geothermal_crosscheck": (
				{
					"modelled_mw": crosscheck.modelled_mw,
					"kenya_installed_mw": crosscheck.kenya_installed_mw,
					"atlas_potential_mw": crosscheck.atlas_potential_mw,
					"within_tolerance": crosscheck.within_tolerance,
					"relative_error": crosscheck.relative_error,
					"source": crosscheck.source,
				}
				if crosscheck is not None
				else None
			),
		},
		notes=(
			"Every physical parameter's source is recorded in "
			"parameters.efficiency_sources; the base network digest is recorded "
			"so the electricity-only result can be shown unchanged."
		),
	)


def coupling_rows(result: CouplingResult) -> list[dict[str, Any]]:
	"""The report's rows as a JSON-serialisable table.

	The parameter sources are embedded per row rather than referenced, so a row
	read from the artefact is self-describing and does not need the provenance
	sidecar to be interpretable.
	"""
	out: list[dict[str, Any]] = []
	for row in result.report.rows:
		out.append(
			{
				"asset": row.asset,
				"name": row.name,
				"sector": row.sector.value,
				"carrier": row.carrier,
				"bus0": row.bus0,
				"bus1": row.bus1,
				"bus2": row.bus2,
				"bus3": row.bus3,
				"values": {key: _jsonable(value) for key, value in row.values.items()},
				"parameter_sources": row.parameter_sources,
				"time_series_keys": row.time_series_keys,
				"source": row.source,
				"provenance_id": row.provenance_id,
				"notes": row.notes,
			}
		)
	assert len(out) == len(result.report.rows)
	return out


def _jsonable(value: Any) -> Any:
	"""Coerce a network column value to something JSON can hold."""
	if isinstance(value, bool | int | float | str | type(None)):
		return value
	if isinstance(value, list | tuple):
		return [_jsonable(item) for item in value]
	return str(value)


def write_coupling_artefact(
	path: str | Path,
	result: CouplingResult,
	provenance: DerivedProvenance,
) -> str:
	"""Write the coupling artefact and return its checksum.

	JSON rather than parquet: the table is heterogeneous -- a ``Link`` row and a
	``Store`` row share only four columns -- and a wide parquet with eighty
	mostly-null columns is harder to read and no smaller at this size.
	"""
	assert result.report.rows, "a coupling artefact with no assets is not a result"
	crosscheck = geothermal_crosscheck(result.report)
	payload = {
		"assets": coupling_rows(result),
		"base_digest_before": result.report.base_digest_before,
		"base_digest_after": result.report.base_digest_after,
		"base_unchanged": result.base_unchanged,
		"sectors": [sector.value for sector in result.report.sectors],
		"skipped": [
			{"sector": build.sector.value, "reason": build.reason}
			for build in result.report.builds
			if not build.enabled
		],
		"geothermal_crosscheck": (
			{
				"modelled_mw": crosscheck.modelled_mw,
				"kenya_installed_mw": crosscheck.kenya_installed_mw,
				"atlas_potential_mw": crosscheck.atlas_potential_mw,
				"tolerance_frac": crosscheck.tolerance_frac,
				"relative_error": crosscheck.relative_error,
				"within_tolerance": crosscheck.within_tolerance,
				"source": crosscheck.source,
			}
			if crosscheck is not None
			else None
		),
		"efficiency_sources": result.source_pairs,
		"technologies_known": len(technologies()),
		"run_id": result.run_id,
	}
	checksum = write_artefact(path, payload, provenance, format="json")
	logger.info(
		"sector.artefact",
		path=str(path),
		assets=len(result.report.rows),
		checksum=checksum[:12],
	)
	return checksum


@stage("sector_coupling")
def build_sector_coupling(
	config: Config,
	out: Path,
	context: Any,
) -> DerivedProvenance:
	"""The registered stage builder for the coupling artefact.

	Reads a solved electricity network, adds the sectors, writes the artefact. It
	does not solve: the network it reads is already solved, and the coupled
	network is written beside the artefact for Layer 1 to solve under its own
	gates.

	**The network is resolved the way `@stage("network_arrays")` resolves it**,
	from ``parameters["network_dir"]`` newest-first, or from an explicit
	``parameters["network_path"]``. It used to read
	``getattr(context, "network_path", None) or config.paths.results``, and both
	arms were wrong: a `BuildContext` carries ``parameters``, not a
	``network_path`` attribute, so the first arm was always ``None``; and
	``config.paths.results`` is the results *directory*, not a network file, so
	``pypsa.Network(<directory>)`` would raise on the fallback. The stage was
	registered and unrunnable, which is why the register recorded it as "its
	input is a solved scenario, so the rule depends on a solve the workflow does
	not yet sequence" -- but the workflow *does* sequence one: `rules/losses.smk`
	declares ``provided("solved_network", NETWORKS)`` for the same input, and
	``--set network_dir=`` is how a rule points a stage at it. This now reads the
	same parameter, so the rule is an ordinary one.

	The resolved digest is recorded as an input, as in `network_arrays`: the
	network is the artefact this stage actually read, and "the newest solved
	network in this directory" is a runtime fact a rule cannot write down.
	"""
	import pypsa

	from alea.io.artefacts import sha256_file
	from alea.planning.arrays import NETWORK_DIR, _newest_network

	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	base = pypsa.Network(str(path))
	weights = context.parameters.get("weights")
	options = context.parameters.get("sector_options") or {}
	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	result = couple_network(config, base, weights=weights, **options)
	if not result.report.rows:
		# Every sector is off, so the coupling is a no-op on a copy of the base
		# network. `write_coupling_artefact` refuses this too, but its assertion
		# says only that an assetless artefact is not a result -- it does not say
		# *why* there are no assets or what turns them on. The shipped config has
		# `sector.enabled: false` and every sector flag false, so this is the
		# default path, not an edge case: a caller who wired the rule and ran it
		# would otherwise read a bare assertion.
		raise ArtefactError(
			"the coupling produced no assets: every sector is disabled. Set "
			"`sector.enabled` and at least one sector flag (hydrogen, heat pumps, "
			"EV/V2G, or an industry vector) in the config. A coupling artefact "
			"with no assets would assert a coupled result for an electricity-only "
			"network."
		)
	provenance = sector_provenance(config, result, inputs=inputs)
	write_coupling_artefact(out, result, provenance)
	coupled_path = Path(out).with_suffix(".coupled.nc")
	result.network.export_to_netcdf(coupled_path)
	logger.info("sector.coupled_network", path=str(coupled_path), network=path.name)
	return provenance


__all__ = [
	"CODE_VERSION",
	"CouplingResult",
	"assert_efficiency_has_source",
	"assert_kenya_portfolio",
	"assert_sector_is_additive",
	"assert_v2g_has_degradation_cost",
	"build_sector_coupling",
	"couple_network",
	"coupling_rows",
	"geothermal_crosscheck",
	"sector_provenance",
	"source_pairs",
	"write_coupling_artefact",
]
