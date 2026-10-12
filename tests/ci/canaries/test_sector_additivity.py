# SPDX-License-Identifier: MIT
"""Canaries: the six Layer 2 gates, each watched failing on its defect.

``test_sector_is_additive`` is the structural gate (05-layer2 §6): a sector
layer that changed the electricity network has a coupling bug, and the gate's
job is to tell a coupling bug from a modelling difference. It does that by
comparing a digest of the base network before the layer ran with a digest of the
network the layer returned.

That gate was a tautology. ``after`` was computed as ``base_digest(network)`` --
the *original*, which the layer never writes to -- so ``before == after`` held
no matter what the coupling layer did to the copy it returned. A gate that
cannot fail is indistinguishable from no gate, and this one read as green on
every run while proving nothing. The first two functions below are the wrong and
right computations, written out so the canary asserts the difference rather than
trusting it.

The rest of the file canaries the other five gates the plan promises:
``test_efficiency_has_source``, ``test_v2g_has_degradation_cost``,
``test_hydrogen_mass_balance``, ``test_energy_balance_closes`` and
``test_geothermal_potential_crosscheck``. Each plants its defect and asserts the
gate notices -- by mutating the source with ``planted`` where the defect is a
line of code, and by calling the real function with the bad input where the
defect is a code path.

The mutations are reverted from the file backup ``planted`` keeps, never with
``git checkout``: the canary's edit and the layer's own uncommitted work live in
the same file.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pypsa

from alea.config.models import Config, ScenarioConfig, SectorConfig
from alea.sector.coupling import base_digest
from alea.sector.service import assert_efficiency_has_source, assert_v2g_has_degradation_cost
from alea.sector.transport import v2g_view
from alea.sector.views import CouplingReport, LinkRow, Sector
from tests.ci.canaries import REPO, assert_raises, planted

SNAPSHOTS = pd.date_range("2030-01-01", periods=4, freq="h")
SRC = REPO / "src" / "alea" / "sector"


def _reload(name: str):
	"""Reload a sector module so a planted edit is what the gate reads."""
	return importlib.reload(importlib.import_module(name))


def _base_network() -> pypsa.Network:
	network = pypsa.Network()
	network.add("Bus", "KE_elec", carrier="AC")
	network.add("Generator", "base_gen", bus="KE_elec", p_nom=100.0, carrier="AC")
	network.set_snapshots(list(SNAPSHOTS))
	return network


def _mutated_coupled_copy(base: pypsa.Network) -> pypsa.Network:
	"""What a coupling bug looks like: the layer moved a base asset's value."""
	coupled = base.copy()
	coupled.generators.loc["base_gen", "p_nom"] = 999.0
	return coupled


def tautological_after(base: pypsa.Network, coupled: pypsa.Network) -> str:
	"""The defect: digest the original, which the layer never writes to."""
	return base_digest(base)


def correct_after(base: pypsa.Network, coupled: pypsa.Network) -> str:
	"""The fix: digest the coupled copy, restricted to the base's own assets."""
	return base_digest(coupled, restrict_to=base)


def test_the_correct_computation_notices_a_mutated_base_asset():
	base = _base_network()
	coupled = _mutated_coupled_copy(base)
	assert correct_after(base, coupled) != base_digest(base)


def test_the_tautology_is_blind_to_the_same_mutation():
	"""Canary proper. If this ever fails, the original defect has returned."""
	base = _base_network()
	coupled = _mutated_coupled_copy(base)
	before = base_digest(base)
	assert tautological_after(base, coupled) == before, (
		"the old computation now moves on a mutation; the canary no longer "
		"demonstrates the defect it exists to catch"
	)
	assert correct_after(base, coupled) != before, "the fix is blind to the mutation"


def test_the_correct_computation_ignores_assets_the_layer_added():
	"""The gate distinguishes a mutation from a legitimate addition.

	A sector asset on a base table (a generator, a store) is the layer doing its
	job, not a coupling bug, and must not move the restricted digest.
	"""
	base = _base_network()
	coupled = base.copy()
	coupled.add("Generator", "solar_pv", bus="KE_elec", p_nom=5.0, carrier="solar")
	coupled.add("Store", "h2_storage", bus="KE_elec", e_nom=10.0)
	assert correct_after(base, coupled) == base_digest(base)


def test_the_gate_notices_a_coupling_layer_that_mutates_the_base_in_place():
	"""Canary proper: the shipped ``couple`` copies the base, and the gate sees it if not.

	``couple`` is handed a network and must never write to it. The defect is a
	single line -- ``coupled = network`` instead of ``coupled = network.copy()``
	-- after which every sector asset lands on the caller's electricity network
	and the digest of the base moves. The gate refuses such a report, which is
	why the mutation is a defect the gate catches rather than a modelling choice.
	"""
	import alea.sector.coupling as coupling_module

	base = _base_network()
	before = base_digest(base)
	source = (SRC / "coupling.py").read_text()
	target = "\tcoupled = network.copy()"
	assert target in source, "canary target not found: the base copy moved"

	with planted(SRC / "coupling.py", target, "\tcoupled = network"):
		coupling = _reload("alea.sector.coupling")
		# The defect wrote the sector buses onto the caller's network, so the
		# base digest moved and ``CouplingReport`` refuses to be constructed --
		# ``couple`` raises before it can return a coupled network.
		exc = assert_raises(
			ValueError, coupling.couple, Config(scenario=ScenarioConfig(countries=["KE"])), base
		)
		assert "changed the base" in str(exc), str(exc)
		assert base_digest(base) != before, "the mutation did not reach the base network"

	coupling = _reload("alea.sector.coupling")
	assert coupling_module is coupling


# --- ``test_efficiency_has_source`` -----------------------------------------


def _unsourced_row() -> LinkRow:
	"""A row that bypassed the validator, with an efficiency and no source."""
	return LinkRow.model_construct(
		asset="Link",
		name="cement_ccus",
		sector=Sector.INDUSTRY,
		carrier="cement",
		bus0="",
		bus1="",
		bus2="",
		bus3="",
		values={"efficiency": 0.5},
		time_series_keys=[],
		parameter_sources={},
		source="a citation",
		provenance_id="p",
		notes="",
	)


def _report_of(row: LinkRow) -> CouplingReport:
	return CouplingReport.model_construct(
		builds=[], base_digest_before="d", base_digest_after="d", rows=[row]
	)


def test_the_efficiency_gate_notices_an_unsourced_efficiency():
	"""Canary: a row with an efficiency and no source is refused.

	The defect is a code path, not file text: a row that bypassed the
	``LinkRow`` validator (``model_construct``) carries ``values["efficiency"]``
	with an empty ``parameter_sources``. The service gate exists for exactly this
	row, so it must raise.
	"""
	assert_raises(ValueError, assert_efficiency_has_source, _report_of(_unsourced_row()))


def test_the_efficiency_gate_is_blind_when_its_column_set_is_narrowed():
	"""Canary proper: the gate's column set is what makes it a gate.

	Narrowing ``assert_efficiency_has_source`` to name no efficiency column
	would let the unsourced row through -- the gate would be a function that
	exists and checks nothing. The mutation is the same shape as the historical
	defect, where the gate's column set was narrower than the validator's.
	"""
	report = _report_of(_unsourced_row())
	assert_raises(ValueError, assert_efficiency_has_source, report)

	source = (SRC / "service.py").read_text()
	target = '\t\t\t\t"efficiency",\n\t\t\t\t"efficiency2",'
	assert target in source, "canary target not found: the column set moved"

	with planted(SRC / "service.py", target, '\t\t\t\t"efficiency2",', count=1):
		service = _reload("alea.sector.service")
		# With ``efficiency`` no longer named, the same row passes: the gate is
		# blind to the column it was narrowed past.
		service.assert_efficiency_has_source(report)

	_reload("alea.sector.service")


# --- ``test_v2g_has_degradation_cost`` --------------------------------------


def _v2g_row(*, degradation: float) -> LinkRow:
	return v2g_view(
		"elec",
		"ev",
		discharge_power_mw=100.0,
		inverter_efficiency=0.92,
		inverter_efficiency_source="inverter datasheet",
		degradation_usd_per_mwh=degradation,
		availability=pd.Series([1.0, 1.0, 1.0, 1.0], index=SNAPSHOTS),
		availability_source="fleet telemetry",
	).as_row()


def test_v2g_without_a_degradation_cost_is_refused_by_the_view():
	"""Canary: the builder refuses free storage at the point the asset is made."""
	assert_raises(
		ValueError,
		v2g_view,
		"elec",
		"ev",
		discharge_power_mw=100.0,
		inverter_efficiency=0.92,
		inverter_efficiency_source="inverter datasheet",
		degradation_usd_per_mwh=0.0,
		availability=pd.Series([1.0, 1.0, 1.0, 1.0], index=SNAPSHOTS),
		availability_source="fleet telemetry",
	)


def test_the_v2g_gate_notices_a_zero_degradation_cost():
	"""Canary: the service gate refuses a V2G link carrying no cost.

	The defect is a row whose ``marginal_cost`` is zero -- the value the optimiser
	charges the link on -- so the fleet is free storage. ``v2g_view`` refuses to
	build one, so the row is reached the way a bypassed path would reach it, and
	the service gate must refuse the mismatch the config already forbids.
	"""
	config = Config(
		scenario=ScenarioConfig(countries=["KE"]),
		sector=SectorConfig(v2g_enabled=True, v2g_degradation_usd_per_mwh=15.0),
	)
	row = _v2g_row(degradation=15.0)
	zero = row.model_copy(update={"values": {**row.values, "marginal_cost": 0.0}})
	assert_raises(ValueError, assert_v2g_has_degradation_cost, config, _report_of(zero))


def test_the_v2g_gate_notices_the_cost_sourced_under_an_ignored_name():
	"""Canary proper: the gate reads ``marginal_cost``, not a parallel name.

	Moving the source back to the old ``degradation_cost`` key while the value
	stays in ``marginal_cost`` leaves the charged column unsourced. If the gate
	read the old name it would pass, which is the bridge between two names that
	made it blind.
	"""
	row = _v2g_row(degradation=15.0)
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
	assert_raises(ValueError, assert_v2g_has_degradation_cost, config, _report_of(broken))


# --- ``test_hydrogen_mass_balance`` -----------------------------------------


def _solved_h2_network(*, with_export: bool = False) -> pypsa.Network:
	from alea.sector.coupling import add_sector_buses, apply_views
	from alea.sector.hydrogen import demand_view, electrolysis_view, export_view

	network = pypsa.Network()
	network.add("Bus", "KE_elec", carrier="AC")
	network.add("Generator", "grid", bus="KE_elec", p_nom=1e5, marginal_cost=10.0, carrier="AC")
	network.set_snapshots(list(SNAPSHOTS))
	add_sector_buses(network, "KE", electricity_bus="KE_elec")
	views = [
		electrolysis_view(
			"KE_elec",
			"KE_h2",
			efficiency_lhv=0.65,
			efficiency_source="IRENA 2024",
			p_nom=0.0,
			extendable=True,
		),
		demand_view(
			"KE_h2",
			annual_demand_twh=0.5,
			snapshots=SNAPSHOTS,
			source="industry",
			name="h2_industry",
		),
	]
	if with_export:
		views.append(
			export_view("KE_h2", volume_twh_per_year=1.0, snapshots=SNAPSHOTS, name="h2_export")
		)
	apply_views(network, views)
	network.optimize(solver_name="highs", log_to_console=False)
	return network


def test_the_hydrogen_balance_notices_a_planted_leak():
	"""Canary: a leak in the H₂ account moves the residual past tolerance.

	A domestic load drawing more hydrogen than the electrolyser delivered is
	energy that left the bus without a producer; the balance must report it.
	"""
	from alea.sector.hydrogen import h2_mass_balance

	network = _solved_h2_network()
	assert h2_mass_balance(network, bus_hydrogen="KE_h2").closes

	network.loads_t.p["h2_industry"] *= 1.1
	assert not h2_mass_balance(network, bus_hydrogen="KE_h2").closes


def test_the_hydrogen_balance_notices_a_double_counted_export():
	"""Canary proper: exports are their own term, not part of ``consumed``.

	The original defect subtracted an export load twice -- once inside
	``consumed`` and once as ``exported`` -- which read as a leak equal to the
	export volume. Reverting ``domestic`` to every load reintroduces it, and the
	balance must stop closing.
	"""
	from alea.sector.hydrogen import h2_mass_balance

	network = _solved_h2_network(with_export=True)
	assert h2_mass_balance(network, bus_hydrogen="KE_h2", export_loads=["h2_export"]).closes

	source = (SRC / "hydrogen.py").read_text()
	target = "\t\t\tdomestic = [name for name in loads if name not in export_names]"
	assert target in source, "canary target not found: the export split moved"

	with planted(SRC / "hydrogen.py", target, "\t\t\tdomestic = list(loads)"):
		hydrogen = _reload("alea.sector.hydrogen")
		leaked = hydrogen.h2_mass_balance(
			network, bus_hydrogen="KE_h2", export_loads=["h2_export"]
		)
		assert not leaked.closes, "the double-counted export no longer leaks; the canary is stale"

	_reload("alea.sector.hydrogen")


# --- ``test_energy_balance_closes`` -----------------------------------------


def _solved_steel_network() -> pypsa.Network:
	from alea.sector.coupling import add_sector_buses, apply_views
	from alea.sector.industry import steel_scrap_eaf_view

	network = pypsa.Network()
	network.add("Bus", "KE_elec", carrier="AC")
	network.add("Generator", "grid", bus="KE_elec", p_nom=1e5, marginal_cost=10.0, carrier="AC")
	network.set_snapshots(list(SNAPSHOTS))
	add_sector_buses(network, "KE", electricity_bus="KE_elec")
	apply_views(
		network,
		[
			steel_scrap_eaf_view(
				"KE_elec",
				"KE_steel",
				efficiency=0.9,
				efficiency_source="IEA 2024",
				pathway_source="IEA steel roadmap",
				extendable=True,
			),
		],
	)
	network.add("Load", "steel_demand", bus="KE_steel", p_set=50.0)
	network.optimize(solver_name="highs", log_to_console=False)
	return network


def test_a_carrier_balance_notices_a_planted_loss():
	"""Canary: a generic carrier balance closes, and a loss moves the residual.

	``generic_balance`` sweeps steel, cement, chemicals and water. A demand
	drawing more product than the link delivered is energy that vanished, and the
	balance must report it rather than closing by construction.
	"""
	from alea.sector.coupling import generic_balance

	network = _solved_steel_network()
	assert generic_balance(network, bus="KE_steel", carrier="steel").closes

	network.loads_t.p["steel_demand"] *= 1.2
	assert not generic_balance(network, bus="KE_steel", carrier="steel").closes


def test_the_carrier_balance_is_blind_when_a_link_port_is_dropped():
	"""Canary proper: the port loop is what lets a product bus balance.

	Omitting port 1 -- the primary output -- reports every product bus as
	consuming with nothing producing, so the residual is the whole delivery. The
	loop once ran over ``("", "2", "3")``, which is that defect; a balance that
	named only the ports someone remembered is a gate with a hole in it.
	"""
	from alea.sector.coupling import generic_balance

	network = _solved_steel_network()
	assert generic_balance(network, bus="KE_steel", carrier="steel").closes

	source = (SRC / "coupling.py").read_text()
	target = '\t\tfor port in ("", "1", "2", "3"):'
	assert target in source, "canary target not found: the port loop moved"

	with planted(SRC / "coupling.py", target, '\t\tfor port in ("", "2", "3"):'):
		coupling = _reload("alea.sector.coupling")
		broken = coupling.generic_balance(network, bus="KE_steel", carrier="steel")
		assert not broken.closes, "dropping port 1 no longer breaks the balance; the canary is stale"

	_reload("alea.sector.coupling")


# --- ``test_geothermal_potential_crosscheck`` -------------------------------


def test_the_geothermal_crosscheck_notices_a_perturbed_potential():
	"""Canary: a modelled potential far from the atlas is refused.

	Kenya's whole result turns on this number (05-layer2 §3.1), so a potential
	that sits outside the tolerance of the Geothermal Atlas must fail the gate
	rather than be reported as a result.
	"""
	from alea.sector.renewables import crosscheck_geothermal

	# 3000 modelled against a 1000 atlas figure is +200%, far outside the 25% band.
	check = crosscheck_geothermal(modelled_mw=3000.0, atlas_potential_mw=1000.0)
	assert not check.within_tolerance
	assert_raises(ValueError, check.require)


def test_the_geothermal_crosscheck_notices_a_potential_below_installed():
	"""Canary: the installed-capacity floor is not subject to tolerance.

	A modelled potential below what KenGen already generates is wrong by
	definition, so it fails even with no atlas figure to compare against.
	"""
	from alea.sector.renewables import crosscheck_geothermal

	check = crosscheck_geothermal(modelled_mw=500.0, kenya_installed_mw=950.0)
	assert not check.within_tolerance
	assert_raises(ValueError, check.require)


def test_the_crosscheck_is_blind_when_its_tolerance_check_is_relaxed():
	"""Canary proper: the tolerance comparison is what refuses the perturbation.

	``within_tolerance`` returning ``True`` unconditionally is the defect -- a
	gate that exists and refuses nothing. With it, the same +200% potential
	passes ``require``.
	"""
	from alea.sector.renewables import crosscheck_geothermal

	check = crosscheck_geothermal(modelled_mw=3000.0, atlas_potential_mw=1000.0)
	assert_raises(ValueError, check.require)

	source = (SRC / "renewables.py").read_text()
	target = "\t\treturn abs(self.relative_error) <= self.tolerance_frac"
	assert target in source, "canary target not found: the tolerance comparison moved"

	with planted(SRC / "renewables.py", target, "\t\treturn True"):
		renewables = _reload("alea.sector.renewables")
		blind = renewables.crosscheck_geothermal(modelled_mw=3000.0, atlas_potential_mw=1000.0)
		assert blind.within_tolerance, "the relaxed tolerance did not go blind; the canary is a no-op"
		blind.require()

	_reload("alea.sector.renewables")
