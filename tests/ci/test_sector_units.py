# SPDX-License-Identifier: MIT
"""The six confirmed Layer 2 sector defects, each with the test that pins it.

Every one of these is a unit error or an unreachable code path, which is the
class of defect a solve cannot show you: the network stays feasible, the result
looks plausible, and the number is wrong by a factor nobody can see in the
output. So each test asserts the *conversion*, not the presence of a parameter.
"""

from __future__ import annotations

import pandas as pd
import pypsa
import pytest

from alea.config.models import Config, RenewableConfig, ScenarioConfig, SectorConfig
from alea.sector.coupling import couple
from alea.sector.renewables import biomass_view
from alea.sector.service import assert_kenya_portfolio, assert_v2g_has_degradation_cost
from alea.sector.transport import v2g_view
from alea.sector.views import CouplingReport, LinkRow, Sector, SectorBuild
from alea.sector.water import M3_PER_MWH_AT_1_KWH_PER_M3, pumping_view, water_demand_view

SNAPSHOTS = pd.date_range("2030-01-01", periods=4, freq="h")


def _network() -> pypsa.Network:
	network = pypsa.Network()
	network.add("Bus", "KE_elec", carrier="AC")
	network.set_snapshots(list(SNAPSHOTS))
	return network


def _kenya_config(**renewables: RenewableConfig) -> Config:
	return Config(
		scenario=ScenarioConfig(countries=["KE"]),
		renewables=renewables,
	)


def _profiles() -> dict[str, pd.Series]:
	return {
		"solar": pd.Series([0.2, 0.3, 0.25, 0.1], index=SNAPSHOTS),
		"onwind": pd.Series([0.4, 0.5, 0.3, 0.2], index=SNAPSHOTS),
	}


def _full_portfolio_options() -> dict[str, object]:
	return {
		"capacity_factors": _profiles(),
		"capacity_factor_sources": {
			"solar": "Global Solar Atlas",
			"onwind": "Global Wind Atlas 3.0",
		},
		"geothermal": {
			"potential_mw": 3000.0,
			"potential_source": "Geothermal Atlas for Africa",
		},
	}


# --- Defect 1: build_renewables had no caller, so the sector never coupled. ---


def test_couple_builds_the_renewable_portfolio_on_the_electricity_bus():
	"""The renewable sector reaches the coupled network, on the elec bus.

	``SECTOR_BUS_SUFFIX["renewables"]`` creates a bus named for the electricity
	bus, but a bus with no generator attached is not a sector. This asserts the
	generators are on the network and attached to the electricity bus -- Kenya's
	decisive technology, geothermal, among them.
	"""
	config = _kenya_config(
		solar=RenewableConfig(enabled=True),
		onwind=RenewableConfig(enabled=True),
		geothermal=RenewableConfig(enabled=True),
		hydro=RenewableConfig(enabled=True),
	)
	coupled, report = couple(config, _network(), renewables=_full_portfolio_options())

	assert "geothermal" in coupled.generators.index
	assert set(coupled.generators.loc[["geothermal"], "bus"]) == {"KE_elec"}
	assert Sector.RENEWABLES in report.sectors
	assert report.asset_counts["renewables"] == 4


def test_a_kenya_portfolio_missing_geothermal_is_refused_through_couple():
	"""The Kenya gate is live: dropping geothermal fails the coupled build."""
	config = _kenya_config(
		solar=RenewableConfig(enabled=True),
		onwind=RenewableConfig(enabled=True),
		hydro=RenewableConfig(enabled=True),
	)
	with pytest.raises(ValueError, match="missing geothermal"):
		couple(config, _network(), renewables=_full_portfolio_options())


def test_kenya_gate_is_blind_when_the_portfolio_is_not_built(monkeypatch):
	"""Canary: the gate fires only because ``couple`` builds the portfolio.

	``assert_kenya_portfolio`` returns early when no renewable row exists, so if
	``couple`` did not call ``build_renewables`` there would be no row and the
	gate would pass on a portfolio that was never built. That is exactly the
	defect: a gate that reads as green because its subject is absent.
	"""
	from alea.sector import coupling as coupling_module

	def no_portfolio(config: Config, **kwargs: object) -> SectorBuild:
		return SectorBuild(sector=Sector.RENEWABLES, enabled=False, reason="canary")

	monkeypatch.setattr(coupling_module.renewables, "build_renewables", no_portfolio)

	# The same config that refuses above, with the build removed.
	config = _kenya_config(solar=RenewableConfig(enabled=True))
	_, report = couple(config, _network(), renewables=_full_portfolio_options())
	assert not [row for row in report.rows if row.sector is Sector.RENEWABLES]
	# Passes vacuously -- which is the blindness the real build removes.
	assert_kenya_portfolio(report)


# --- Defect 2: biomass marginal cost was the fuel price, not the output cost. ---


def test_biomass_marginal_cost_divides_the_fuel_price_by_efficiency():
	view = biomass_view(
		"elec",
		fuel_cost_usd_per_mwh=30.0,
		fuel_cost_source="JRC Bioenergy Atlas",
		efficiency=0.35,
		efficiency_source="JRC Bioenergy Atlas",
		potential_mw=500.0,
		potential_source="JRC Bioenergy Atlas",
	)
	# 30 USD/MWh_fuel at 0.35 efficiency is 30/0.35 = 85.71 USD/MWh_el.
	assert view.attributes["marginal_cost"] == pytest.approx(30.0 / 0.35)
	assert view.attributes["marginal_cost"] != pytest.approx(30.0)
	# The source must travel on the column PyPSA actually charges.
	assert view.parameters["marginal_cost"].source == "JRC Bioenergy Atlas"
	assert view.parameters["fuel_cost"].value == 30.0


def test_biomass_row_carries_a_marginal_cost_source():
	view = biomass_view(
		"elec",
		fuel_cost_usd_per_mwh=30.0,
		fuel_cost_source="JRC Bioenergy Atlas",
		efficiency=0.35,
		efficiency_source="JRC Bioenergy Atlas",
		potential_mw=500.0,
		potential_source="JRC Bioenergy Atlas",
	)
	row = view.as_row()
	assert row.parameter_sources["marginal_cost"] == "JRC Bioenergy Atlas"


def test_biomass_refuses_a_zero_efficiency():
	with pytest.raises(AssertionError, match="efficiency must be in"):
		biomass_view(
			"elec",
			fuel_cost_usd_per_mwh=30.0,
			fuel_cost_source="JRC Bioenergy Atlas",
			efficiency=0.0,
			efficiency_source="JRC Bioenergy Atlas",
			potential_mw=500.0,
			potential_source="JRC Bioenergy Atlas",
		)


# --- Defect 3: pumping p_nom was m3/h read as MW, ~1000x too large. ---


def test_pumping_p_nom_is_input_power_not_volumetric_capacity():
	view = pumping_view(
		"elec",
		"water",
		head_m=400.0,
		efficiency=0.75,
		efficiency_source="pump curve",
		capacity_m3_per_hour=1000.0,
	)
	# 400 m head at 0.75 pump efficiency is ~1.45 kWh/m3, so ~688 m3/MWh and a
	# 1000 m3/h pump is ~1.45 MW of electrical draw.
	efficiency = view.parameters["efficiency"].value
	assert view.attributes["p_nom"] == pytest.approx(1000.0 / efficiency)
	assert view.attributes["p_nom"] < 10.0
	assert view.attributes["p_nom"] != pytest.approx(1000.0)


def test_pumping_p_nom_matches_the_desalination_convention():
	"""Both links carry ``bus0=electricity``; both must rate p_nom in MW."""
	view = pumping_view(
		"elec",
		"water",
		head_m=100.0,
		efficiency=1.0,
		efficiency_source="ideal pump",
		capacity_m3_per_hour=M3_PER_MWH_AT_1_KWH_PER_M3,
	)
	# At unit efficiency and 100 m, specific energy is 0.272 kWh/m3, so 1000 m3/h
	# is 0.272 MW -- the same order as the desalination link, not 1000.
	assert 0.0 < view.attributes["p_nom"] < 1.0


# --- Defect 4: V2G degradation cost was sourced under a name PyPSA ignores. ---


def _v2g_row() -> LinkRow:
	view = v2g_view(
		"elec",
		"ev",
		discharge_power_mw=100.0,
		inverter_efficiency=0.92,
		inverter_efficiency_source="inverter datasheet",
		degradation_usd_per_mwh=15.0,
		availability=pd.Series([1.0, 1.0, 1.0, 1.0], index=SNAPSHOTS),
		availability_source="fleet telemetry",
	)
	return view.as_row()


def test_v2g_degradation_cost_lands_on_marginal_cost_with_its_source():
	row = _v2g_row()
	assert row.values["marginal_cost"] == 15.0
	assert row.parameter_sources["marginal_cost"] == "05-layer2 §2.3 (V2G degradation cost)"
	# The old name carried the source in a column nothing read.
	assert "degradation_cost" not in row.parameter_sources


def test_v2g_gate_reads_the_same_key_as_the_column():
	config = Config(
		scenario=ScenarioConfig(countries=["KE"]),
		sector=SectorConfig(v2g_enabled=True, v2g_degradation_usd_per_mwh=15.0),
	)
	report = CouplingReport(
		builds=[],
		base_digest_before="d",
		base_digest_after="d",
		rows=[_v2g_row()],
	)
	assert_v2g_has_degradation_cost(config, report)


def test_v2g_gate_fails_when_only_the_old_name_carries_the_source():
	"""The bridge between the two names is gone: a renamed source is caught."""
	row = _v2g_row()
	# Move the source back to the old, ignored name, keeping the value column.
	broken = row.model_copy(
		update={
			"parameter_sources": {
				"efficiency": row.parameter_sources["efficiency"],
				"p_max_pu": row.parameter_sources["p_max_pu"],
				"degradation_cost": row.parameter_sources["marginal_cost"],
			}
		}
	)
	config = Config(
		scenario=ScenarioConfig(countries=["KE"]),
		sector=SectorConfig(v2g_enabled=True, v2g_degradation_usd_per_mwh=15.0),
	)
	report = CouplingReport(
		builds=[],
		base_digest_before="d",
		base_digest_after="d",
		rows=[broken],
	)
	with pytest.raises(ValueError, match="no positive degradation cost"):
		assert_v2g_has_degradation_cost(config, report)


# --- Defect 5: the physical name set named "cop", which no view emits. ---


def _is_gated(name: str) -> bool:
	"""Whether an unsourced value under ``name`` is refused by the row validator."""
	from pydantic import ValidationError

	try:
		LinkRow(
			asset="Link",
			name="probe",
			sector=Sector.HEAT,
			carrier="heat_pump",
			values={name: 1.0},
			source="a real citation",
			provenance_id="probe",
		)
	except ValidationError as exc:
		assert "no source" in str(exc), str(exc)
		return True
	return False


def test_an_unsourced_efficiency_is_refused_and_the_dead_cop_name_is_gone():
	"""The two sides agree: efficiency is gated, the dead ``cop`` name is not.

	A heat pump's COP is emitted as ``efficiency`` (heat.py), so a ``cop`` entry
	in the name set gated a column no view ever produces. The row validator and
	``assert_efficiency_has_source`` now name the same columns.
	"""
	assert _is_gated("efficiency")
	assert _is_gated("efficiency2")
	assert not _is_gated("cop")


def test_a_heat_pump_records_its_cop_as_a_sourced_efficiency():
	from alea.sector.heat import heat_pump_view

	row = heat_pump_view(
		"elec", "heat", cop=3.2, cop_source="ERA5 temperature series", p_nom=0.0
	).as_row()
	assert row.values["efficiency"] == 3.2
	assert row.parameter_sources["efficiency"] == "ERA5 temperature series"


# --- Defect 6: a supplied demand profile discarded the annual total. ---


def test_a_water_demand_profile_is_scaled_to_the_annual_total():
	annual = 8_760_000.0
	# A shape whose weighted integral is 4.0, i.e. a factor of ~1e6 off the
	# annual figure; scaling must bring it to the annual volume.
	profile = pd.Series([1.0, 1.0, 1.0, 1.0], index=SNAPSHOTS)
	view = water_demand_view(
		"water",
		annual_demand_m3=annual,
		snapshots=SNAPSHOTS,
		profile=profile,
	)
	# 4 hours of a representative year -> 8760000 * 4/8760 = 4000 m3 total.
	assert sum(view.time_series["p_set"]) == pytest.approx(4000.0)
	assert "8,760,000 m3/year" in view.notes
	assert "scaled to the annual total" in view.notes


def test_a_water_demand_profile_keeps_its_shape():
	annual = 8_760_000.0
	profile = pd.Series([1.0, 3.0, 1.0, 1.0], index=SNAPSHOTS)
	view = water_demand_view(
		"water",
		annual_demand_m3=annual,
		snapshots=SNAPSHOTS,
		profile=profile,
	)
	series = view.time_series["p_set"]
	# The profile's relative shape survives the scaling.
	assert series[1] == pytest.approx(3.0 * series[0])
	assert sum(series) == pytest.approx(4000.0)


def test_a_zero_volume_water_profile_is_refused():
	view_profile = pd.Series([0.0, 0.0, 0.0, 0.0], index=SNAPSHOTS)
	with pytest.raises(ValueError, match="integrates to zero"):
		water_demand_view(
			"water",
			annual_demand_m3=1000.0,
			snapshots=SNAPSHOTS,
			profile=view_profile,
		)


def test_the_unprofiled_water_demand_path_is_unchanged():
	view = water_demand_view("water", annual_demand_m3=8_760_000.0, snapshots=SNAPSHOTS)
	assert sum(view.time_series["p_set"]) == pytest.approx(4000.0)
	assert "m3/year over the modelled horizon" in view.notes


# --- Defect 7: the additivity gate hashed the untouched original, not the copy. ---


def _network_with_base_generator() -> pypsa.Network:
	network = _network()
	network.add("Generator", "base_gen", bus="KE_elec", p_nom=100.0, carrier="AC")
	return network


def test_the_additivity_gate_notices_a_mutated_base_asset():
	"""``base_digest`` restricted to the base's assets must move on a mutation.

	The gate was a tautology: ``after`` was the digest of the untouched original
	network, so it could never differ from ``before`` however the coupling layer
	changed the copy it returned. This pins the comparison that makes the gate
	real -- a base asset whose value moved is detected.
	"""
	from alea.sector.coupling import base_digest

	network = _network_with_base_generator()
	before = base_digest(network)
	coupled = network.copy()
	coupled.generators.loc["base_gen", "p_nom"] = 999.0
	assert base_digest(coupled, restrict_to=network) != before


def test_a_coupling_layer_that_dropped_a_base_asset_is_refused():
	from alea.sector.coupling import base_digest

	network = _network_with_base_generator()
	before = base_digest(network)
	coupled = network.copy()
	coupled.remove("Generator", "base_gen")
	after = base_digest(coupled, restrict_to=network)
	with pytest.raises(ValueError, match="changed the base"):
		CouplingReport(builds=[], base_digest_before=before, base_digest_after=after, rows=[])


def test_the_additivity_gate_ignores_the_assets_the_layer_added():
	"""A sector asset on a base table is not a mutation of the base."""
	from alea.sector.coupling import base_digest

	network = _network_with_base_generator()
	before = base_digest(network)
	coupled = network.copy()
	coupled.add("Generator", "solar_pv", bus="KE_elec", p_nom=5.0, carrier="solar")
	assert base_digest(coupled, restrict_to=network) == before


# --- Defect 8: the hydrogen and heat balances did not close. ---


def _solved_hydrogen_network() -> pypsa.Network:
	from alea.sector.coupling import add_sector_buses, apply_views
	from alea.sector.hydrogen import demand_view, electrolysis_view, export_view, storage_view

	network = _network()
	network.add("Generator", "grid", bus="KE_elec", p_nom=1e5, marginal_cost=10.0, carrier="AC")
	add_sector_buses(network, "KE", electricity_bus="KE_elec")
	apply_views(
		network,
		[
			electrolysis_view(
				"KE_elec",
				"KE_h2",
				efficiency_lhv=0.65,
				efficiency_source="IRENA 2024",
				p_nom=0.0,
				extendable=True,
			),
			export_view("KE_h2", volume_twh_per_year=1.0, snapshots=SNAPSHOTS, name="h2_export"),
			demand_view(
				"KE_h2",
				annual_demand_twh=0.5,
				snapshots=SNAPSHOTS,
				source="industry",
				name="h2_industry",
			),
			storage_view(
				"KE_h2",
				e_nom=0.0,
				standing_loss_per_hour=0.0,
				standing_loss_source="vessel",
				extendable=True,
				name="h2_storage",
			),
		],
	)
	network.optimize(solver_name="highs", log_to_console=False)
	return network


def test_the_hydrogen_balance_closes_with_export_and_storage():
	"""Exports are their own term and storage is net energy into the store.

	The balance subtracted the export load twice (once in ``consumed``, once as
	``exported``) and computed ``storage_delta`` as ``e.iloc[-1] - e.iloc[0]``,
	which counts a store's initial stock as a horizon charge. Together they left
	a residual that read as a leak; this pins the closing balance.
	"""
	from alea.sector.hydrogen import h2_mass_balance

	network = _solved_hydrogen_network()
	balance = h2_mass_balance(network, bus_hydrogen="KE_h2", export_loads=["h2_export"])
	assert balance.exported_mwh > 0.0
	assert balance.consumed_mwh > 0.0
	assert balance.closes, balance


def test_the_hydrogen_balance_notices_a_planted_leak():
	"""Canary: the closing balance is not closing by construction."""
	from alea.sector.hydrogen import h2_mass_balance

	network = _solved_hydrogen_network()
	network.loads_t.p["h2_industry"] *= 1.1  # a leak nobody accounted for
	balance = h2_mass_balance(network, bus_hydrogen="KE_h2", export_loads=["h2_export"])
	assert not balance.closes, balance


def test_the_heat_balance_closes_with_thermal_storage():
	from alea.sector.coupling import add_sector_buses, apply_views
	from alea.sector.heat import (
		heat_demand_view,
		heat_energy_balance,
		heat_pump_view,
		thermal_storage_view,
	)

	network = _network()
	network.add("Generator", "grid", bus="KE_elec", p_nom=1e5, marginal_cost=10.0, carrier="AC")
	add_sector_buses(network, "KE", electricity_bus="KE_elec")
	apply_views(
		network,
		[
			heat_pump_view(
				"KE_elec", "KE_heat", cop=3.0, cop_source="ERA5 temperature series", p_nom=0.0, extendable=True
			),
			thermal_storage_view(
				"KE_heat",
				e_nom=0.0,
				standing_loss_per_hour=0.0,
				standing_loss_source="tank",
				extendable=True,
				name="thermal_storage",
			),
			heat_demand_view(
				"KE_heat", annual_demand_twh=1.0, snapshots=SNAPSHOTS, source="municipal"
			),
		],
	)
	network.optimize(solver_name="highs", log_to_console=False)
	balance = heat_energy_balance(network, bus_heat="KE_heat")
	assert balance.exported_mwh == 0.0
	assert balance.closes, balance


# --- Defect 9: the geothermal cross-check had no caller. ---


def _kenya_renewables_config() -> Config:
	return _kenya_config(
		solar=RenewableConfig(enabled=True),
		onwind=RenewableConfig(enabled=True),
		geothermal=RenewableConfig(enabled=True),
		hydro=RenewableConfig(enabled=True),
	)


def test_the_geothermal_cross_check_is_computed_and_carried_by_the_build():
	"""The cross-check function existed but nothing invoked it; now it runs.

	The modelled potential is read from the view that reached the portfolio, so
	the cross-check is against the number on the network, not against the
	argument that produced it.
	"""
	from alea.sector.renewables import build_renewables

	build = build_renewables(_kenya_renewables_config(), bus="KE_elec", snapshots=SNAPSHOTS, **_full_portfolio_options())
	assert build.geothermal_crosscheck is not None
	check = build.geothermal_crosscheck
	assert check.modelled_mw == 3000.0
	assert check.kenya_installed_mw == 950.0
	assert check.within_tolerance


def test_the_geothermal_cross_check_refuses_a_potential_below_installed():
	from alea.sector.renewables import build_renewables

	options = _full_portfolio_options()
	options["geothermal"] = {"potential_mw": 500.0, "potential_source": "Geothermal Atlas for Africa"}
	with pytest.raises(ValueError, match="fails the Kenya cross-check"):
		build_renewables(_kenya_renewables_config(), bus="KE_elec", snapshots=SNAPSHOTS, **options)


def test_the_geothermal_cross_check_refuses_a_potential_far_from_the_atlas():
	from alea.sector.renewables import build_renewables

	options = _full_portfolio_options()
	options["renewables"] = {"geothermal_atlas_potential_mw": 1000.0}
	# 3000 modelled against a 1000 atlas figure is +200%, far outside 25%.
	with pytest.raises(ValueError, match="fails the Kenya cross-check"):
		build_renewables(_kenya_renewables_config(), bus="KE_elec", snapshots=SNAPSHOTS, **options)


def test_the_cross_check_reaches_the_coupling_artefact():
	"""Criterion 5 is an artefact: it must be readable from the result, not only
	computed in passing."""
	from alea.sector.service import geothermal_crosscheck

	config = _kenya_renewables_config()
	_, report = couple(config, _network(), renewables=_full_portfolio_options())
	check = geothermal_crosscheck(report)
	assert check is not None
	assert check.within_tolerance
