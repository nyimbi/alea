# SPDX-License-Identifier: MIT
"""Layer 2 — sector coupling.

Extends Layer 1's electricity network into a multi-energy system: hydrogen,
heat, transport, industry, water, and the full renewable portfolio. The layer is
**additive**. The electricity-only network stays valid and stays reproducible,
and it is the fallback if sector coupling is misconfigured.

The governing rule (05-layer2 §1) is that sector coupling is a config layer over
Layer 1, not a separate pipeline. ``config.sector.yaml`` extends
``config.kenya.yaml``; it does not replace it. Two consequences follow and are
enforced in code rather than documented and forgotten:

* ``couple`` copies the base network and refuses to return a report in which the
  base digest moved. A coupling bug therefore cannot be reported as a modelling
  difference.
* Every efficiency, COP and degradation figure carries a ``_source``. A view
  whose physical parameter has no source cannot be constructed, so the
  requirement holds at the type level and not only at the config validator.

Entry points:

* ``couple`` — extend a network with the sectors a config enables.
* ``build_*`` — one sector's views, for a caller composing its own network.
* ``*_mass_balance`` / ``*_energy_balance`` — the conservation gates.
* ``crosscheck_geothermal`` — Kenya's decisive resource, cross-checked.
"""

from __future__ import annotations

from alea.sector.coupling import (
	BASE_COMPONENTS,
	SECTOR_BUS_SUFFIX,
	add_sector_buses,
	apply_view,
	apply_views,
	base_digest,
	couple,
	energy_balance_report,
	generic_balance,
	sector_buses,
)
from alea.sector.heat import (
	build_heat,
	cop_from_temperature,
	heat_energy_balance,
	heat_pump_view,
	heat_pump_view_from_temperature,
	thermal_storage_view,
)
from alea.sector.hydrogen import (
	build_hydrogen,
	electrolysis_view,
	export_view,
	h2_kg_to_mwh,
	h2_mass_balance,
	storage_view,
)
from alea.sector.industry import (
	ammonia_view,
	build_industry,
	cement_ccus_view,
	methanol_view,
	steel_h2_dri_view,
	steel_scrap_eaf_view,
)
from alea.sector.renewables import (
	CONTINENTAL_ONLY,
	KENYA_CRITICAL,
	QUALITY,
	GeothermalCrossCheck,
	ResourceQuality,
	biomass_view,
	build_renewables,
	crosscheck_geothermal,
	csp_view,
	geothermal_view,
	hydro_phs_view,
	hydro_reservoir_view,
	hydro_ror_view,
	kenya_portfolio_gate,
	marine_view,
	offshore_wind_view,
	onshore_wind_view,
	solar_pv_view,
)
from alea.sector.service import (
	CouplingResult,
	assert_efficiency_has_source,
	assert_kenya_portfolio,
	assert_sector_is_additive,
	assert_v2g_has_degradation_cost,
	couple_network,
	coupling_rows,
	sector_provenance,
	source_pairs,
	write_coupling_artefact,
)
from alea.sector.transport import (
	build_transport,
	ev_driving_load_view,
	ev_fleet_view,
	h2_vehicle_demand_view,
	smart_charging_view,
	v2g_cycles,
	v2g_view,
)
from alea.sector.views import (
	CouplingReport,
	CouplingView,
	EnergyBalance,
	LinkRow,
	MassBalance,
	Parameter,
	Sector,
	SectorBuild,
)
from alea.sector.water import (
	CoolingType,
	WaterType,
	build_water,
	cooling_view,
	desalination_flexibility,
	desalination_view,
	pumping_view,
	water_demand_view,
	water_storage_view,
)

__all__ = [
	"BASE_COMPONENTS",
	"CONTINENTAL_ONLY",
	"KENYA_CRITICAL",
	"QUALITY",
	"SECTOR_BUS_SUFFIX",
	"CoolingType",
	"CouplingReport",
	"CouplingResult",
	"CouplingView",
	"EnergyBalance",
	"GeothermalCrossCheck",
	"LinkRow",
	"MassBalance",
	"Parameter",
	"ResourceQuality",
	"Sector",
	"SectorBuild",
	"WaterType",
	"add_sector_buses",
	"ammonia_view",
	"apply_view",
	"apply_views",
	"assert_efficiency_has_source",
	"assert_kenya_portfolio",
	"assert_sector_is_additive",
	"assert_v2g_has_degradation_cost",
	"base_digest",
	"biomass_view",
	"build_heat",
	"build_hydrogen",
	"build_industry",
	"build_renewables",
	"build_transport",
	"build_water",
	"cement_ccus_view",
	"cooling_view",
	"cop_from_temperature",
	"couple",
	"couple_network",
	"coupling_rows",
	"crosscheck_geothermal",
	"csp_view",
	"desalination_flexibility",
	"desalination_view",
	"electrolysis_view",
	"energy_balance_report",
	"generic_balance",
	"ev_driving_load_view",
	"ev_fleet_view",
	"export_view",
	"geothermal_view",
	"h2_kg_to_mwh",
	"h2_mass_balance",
	"h2_vehicle_demand_view",
	"heat_energy_balance",
	"heat_pump_view",
	"heat_pump_view_from_temperature",
	"hydro_phs_view",
	"hydro_reservoir_view",
	"hydro_ror_view",
	"kenya_portfolio_gate",
	"marine_view",
	"methanol_view",
	"offshore_wind_view",
	"onshore_wind_view",
	"pumping_view",
	"sector_buses",
	"sector_provenance",
	"smart_charging_view",
	"solar_pv_view",
	"source_pairs",
	"steel_h2_dri_view",
	"steel_scrap_eaf_view",
	"thermal_storage_view",
	"storage_view",
	"v2g_cycles",
	"v2g_view",
	"water_demand_view",
	"water_storage_view",
	"write_coupling_artefact",
]
