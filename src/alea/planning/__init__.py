# SPDX-License-Identifier: MIT
"""Layer 1: the planning core.

Topology, fleet, demand, renewables, expansion, dispatch, aggregation. Every
other analytical layer reads a network this package built, so the modules here
are the ones whose mistakes are inherited.

The PyPSA-Earth seam is files (AD-1). Nothing in this package imports
``pypsa_earth``; the seam's artefacts are read through ``schemas`` and validated
on the way in.
"""

from alea.planning.aggregation import (
	TOLERANCE_COST_PCT,
	TOLERANCE_MIX_PCT,
	AggregationError,
	AggregationValidation,
	capacity_mix,
	cluster_buses,
	l1_mix_distance,
	load_validation,
	mix_shares,
	network_id,
	require_aggregation_validation,
	validate_aggregation_artefact,
	write_validation,
)
from alea.planning.demand import (
	NATIONAL_TOLERANCE_PCT,
	DemandError,
	NationalCheck,
	attach_loads,
	disaggregate_to_buses,
	scale_to_national,
	validate_national_total,
)
from alea.planning.dispatch import (
	DispatchError,
	DispatchResult,
	balance_measurement,
	check_energy_balance,
	curtailment_mwh,
	generation_by_carrier,
	solve_dispatch,
)
from alea.planning.expansion import (
	ExpansionError,
	SolveResult,
	build_multi_period_snapshots,
	capacity_mix_table,
	check_no_free_capacity,
	check_solver_available,
	loss_share,
	set_multi_period,
	solve_expansion,
)
from alea.planning.fleet import (
	FLEET_COVERAGE_TOLERANCE_PCT,
	AttachmentReport,
	FleetCoverage,
	FleetError,
	attach_extendable_candidates,
	attach_generators,
	validate_fleet_coverage,
)
from alea.planning.renewables import (
	RenewableError,
	attach_renewables,
	validate_capacity_factors,
)
from alea.planning.schemas import (
	DEMAND,
	FLEET,
	PROFILE,
	TOPOLOGY,
	ArtefactSchema,
	SchemaError,
	check_carriers,
	schema_by_name,
)
from alea.planning.service import (
	BuildReport,
	PlanningError,
	build_network,
	dispatch_scenario,
	network_summary,
	solve_scenario,
)
from alea.planning.topology import (
	TopologyError,
	TopologyReport,
	build_topology,
	cluster_points,
	connectivity_report,
	orphan_buses,
)

__all__ = [
	"DEMAND",
	"FLEET",
	"NATIONAL_TOLERANCE_PCT",
	"PROFILE",
	"TOLERANCE_COST_PCT",
	"TOLERANCE_MIX_PCT",
	"TOPOLOGY",
	"AggregationError",
	"AggregationValidation",
	"ArtefactSchema",
	"AttachmentReport",
	"BuildReport",
	"DemandError",
	"DispatchError",
	"DispatchResult",
	"ExpansionError",
	"FLEET_COVERAGE_TOLERANCE_PCT",
	"FleetCoverage",
	"FleetError",
	"NationalCheck",
	"PlanningError",
	"RenewableError",
	"SchemaError",
	"SolveResult",
	"TopologyError",
	"TopologyReport",
	"attach_extendable_candidates",
	"attach_generators",
	"attach_loads",
	"attach_renewables",
	"build_multi_period_snapshots",
	"build_network",
	"build_topology",
	"capacity_mix",
	"capacity_mix_table",
	"check_carriers",
	"balance_measurement",
	"check_energy_balance",
	"check_no_free_capacity",
	"check_solver_available",
	"cluster_buses",
	"cluster_points",
	"connectivity_report",
	"curtailment_mwh",
	"disaggregate_to_buses",
	"dispatch_scenario",
	"generation_by_carrier",
	"l1_mix_distance",
	"load_validation",
	"loss_share",
	"mix_shares",
	"network_id",
	"network_summary",
	"orphan_buses",
	"require_aggregation_validation",
	"scale_to_national",
	"schema_by_name",
	"set_multi_period",
	"solve_dispatch",
	"solve_expansion",
	"solve_scenario",
	"validate_aggregation_artefact",
	"validate_fleet_coverage",
	"validate_capacity_factors",
	"validate_national_total",
	"write_validation",
]
