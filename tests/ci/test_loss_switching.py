# SPDX-License-Identifier: MIT
"""Loss-optimal line switching, and the decomposition it exists to make measurable.

`docs/plans/07-layer4-predictive.md` §6.2 names the kernel and states the
invariant -- ``load_driven + generation_driven + topology_driven == total``,
asserted to 1e-9 relative tolerance -- and this module is the gate for both
halves: that the search finds a topology, and that the decomposition built on it
attributes to more than one driver.

**Why the four-bus meshed fixture is not the discriminating one.** It is the
fixture `test_predictive_layer4.py` uses and it is meshed and mixed-voltage for a
good reason, but *every* single opening on it increases loss (measured: 526 /
108 / 17.5 / 67 MW against a base of 16.3). A switching gate written on it would
assert ``opened == []`` for ever and read as a passing search. The discriminating
fixture is two buses with two parallel branches -- one a good conductor
(``b = 132^2/1.0``, ``R = 50``), one a bad one (``b = 132^2/10.0``, ``R = 1``) --
where DC splits the flow by susceptance, so most of it rides the bad conductor.
Measured: 213.48 MW in with both, 5.17 MW with the good branch open. One opening,
a 41x reduction, and the search has to find it.

**The phantom-flow gate is the one that took a measurement to find.** The
standard stamp subtracts a branch from ``B`` and leaves ``branch_susceptance``
alone, and ``branch_flows`` then computes ``b * (theta_i - theta_j)`` across a
branch that is open. Measured on the two-bus fixture: the stamped-B-only network
carries 2000 MW on the opened branch and charges 11,480 MW of loss for it.
``open_branches`` zeroes the susceptance *and* rebuilds the matrix, and the gate
below asserts both halves rather than the loss alone.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from alea.config.paths import resolve
from alea.io.artefacts import read_artefact
from alea.io.pipeline import build_stage
from alea.losses.decompose import measure, reference_injection
from alea.losses.flow import Network, solve_snapshot, susceptance_matrix
from alea.losses.service import losses_components
from alea.losses.switching import open_branches, optimal_switching, switching_candidates
from alea.losses.views import LossConfig
from alea.reporting.schemas import ReportCadence
from tests.ci.test_market_report_sections import _config

ISSUE_DATE = date(2030, 1, 15)
"""A Wednesday; the weekly report it belongs to reads the period ending the
Friday before. Spelled here so the projection and the assertion agree."""

PERIOD_END = {ReportCadence.WEEKLY: date(2030, 1, 14), ReportCadence.MONTHLY: date(2029, 12, 31)}
"""The period end each cadence's reader resolves from ``ISSUE_DATE``.

Spelled as literals rather than read from ``period_for``: the reader calls that
function itself, so a test that called it too would assert only that the reader
agrees with itself. The first spelling of these two tests passed ``ISSUE_DATE``
to ``_section_from_spec`` and both sections came back absent -- the reader
looked for ``2030-01-14`` and the test had told it ``2030-01-15``, which is a
file nothing writes.
"""


def _parallel_pair() -> Network:
	"""Two buses, two parallel branches, one good conductor and one bad.

	The discriminating fixture, and the reason is DC's own flow split: with no
	series impedance between the buses, the flow divides by susceptance, so
	``b = 132^2/1.0`` takes 10/11 of it and ``b = 132^2/10.0`` takes 1/11. The
	bad conductor carries little current and has ``R = 1``; the good one carries
	most of it and has ``R = 50``, so ``I^2 R`` is dominated by the branch with
	the large resistance. Opening *that* one is the loss-minimising single
	switching, and it is not the branch a "highest flow" heuristic would pick.
	"""
	branch_from = np.array([0, 0], dtype=np.uint32)
	branch_to = np.array([1, 1], dtype=np.uint32)
	susceptance = np.array([132.0**2 / 1.0, 132.0**2 / 10.0])
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 2),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([50.0, 1.0]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([200.0, 200.0]),
		branch_names=("A", "B"),
	)


def _four_bus_meshed() -> Network:
	"""The meshed mixed-voltage fixture, for the gates about *no* improvement."""
	from tests.ci.test_predictive_layer4 import _four_bus_meshed as fixture

	return fixture()[0]


def _config_for(**overrides: object) -> LossConfig:
	return LossConfig(slack_bus=0, snapshot_hours=1.0, **overrides)  # type: ignore[arg-type]


def _random_network(rng: np.random.Generator) -> Network:
	"""A connected random network: a spanning path, then chords and parallels.

	The spanning path is what makes it *connected*, and connectedness is the
	property the sweep needs rather than a convenience: ``optimal_switching``
	skips an islanding opening as infeasible, so a generator that emitted
	disconnected networks would spend most of its budget in the branch that
	proves nothing about the decomposition.

	Susceptance is drawn as ``V^2 / x`` rather than as a bare number, because
	that is the relation the fixture's own constants spell (``132^2/1.0``) and a
	bare draw over the same range would mean an impedance no voltage supports --
	which is a network whose losses are enormous for a reason the test would then
	be attributing to the kernel.
	"""
	n_buses = int(rng.integers(2, 7))
	pairs = [(index, index + 1) for index in range(n_buses - 1)]
	for _ in range(int(rng.integers(1, 5))):
		head = int(rng.integers(0, n_buses))
		tail = int(rng.integers(0, n_buses))
		if head != tail:
			pairs.append((min(head, tail), max(head, tail)))
	branch_from = np.array([pair[0] for pair in pairs], dtype=np.uint32)
	branch_to = np.array([pair[1] for pair in pairs], dtype=np.uint32)
	voltage = float(rng.choice([66.0, 132.0, 220.0]))
	reactance = rng.uniform(0.1, 20.0, size=len(pairs))
	susceptance = voltage**2 / reactance
	return Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, n_buses),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=rng.uniform(0.05, 20.0, size=len(pairs)),
		voltage_kv=np.full(len(pairs), voltage),
		ratings_mw=np.full(len(pairs), 500.0),
		branch_names=tuple(f"L{index}" for index in range(len(pairs))),
	)


def _random_dispatch(
	rng: np.random.Generator, n_buses: int, n_snapshots: int
) -> NDArray[np.float64]:
	"""Random injections, demeaned so each snapshot's generation meets its load.

	The demeaning is not tidiness: a snapshot whose injections do not sum to
	zero puts the mismatch on the slack bus, which is a generation the dispatch
	never named, and the reference injection would then be the mean of a series
	that carries it.
	"""
	raw = rng.uniform(-300.0, 300.0, size=(n_snapshots, n_buses))
	return raw - raw.mean(axis=1, keepdims=True)


# --------------------------------------------------------------------------
# The search
# --------------------------------------------------------------------------


def test_the_search_finds_the_loss_reducing_opening():
	"""One opening, found, and it is the branch with the large resistance.

	The assertion on *which* branch matters as much as the reduction: the
	loss-minimising single switching here is the high-susceptance branch, which
	carries most of the flow, and a search that returned the low-susceptance one
	would have reduced loss by less while still reporting a reduction.
	"""
	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0]])
	_, result = optimal_switching(network, dispatch, _config_for())

	assert result.opened == [0], (
		f"the search opened {result.opened_names} and the loss-minimising single "
		f"switching on this fixture is branch A (b=132^2/1.0, R=50); opening B "
		f"instead raises the loss"
	)
	assert result.truncated is False, (
		"one opening over two candidates fits any budget, so a truncated result "
		"here means the budget is not what this test thinks it is"
	)
	assert result.n_candidates == 2
	assert result.n_evaluated == 2, (
		f"the search evaluated {result.n_evaluated} topologies; an exhaustive "
		f"single-switching search over two candidates evaluates exactly two"
	)
	# The reduction is 41x, which is what makes this fixture discriminating: a
	# fixture with no loss-reducing opening would pass every other assertion.
	assert result.reduction_mw > 0.9 * result.reference_loss_mw, (
		f"the opening reduced loss by {result.reduction_mw} of "
		f"{result.reference_loss_mw}; on this fixture it is 92.59 of 94.88"
	)


def test_an_opened_branch_carries_no_flow_and_charges_no_loss():
	"""The phantom-flow gate, asserted on both halves.

	Zeroing the susceptance without rebuilding ``B`` leaves the branch in the
	matrix, and ``branch_flows`` computes ``b * (theta_i - theta_j)`` across it
	-- so the opened branch carries a flow and the network is charged for it.
	Measured on this fixture, that is 2000 MW and 11,480 MW of loss. Asserting
	the *loss* alone would pass a network that zeroed the susceptance and left a
	flow of zero by coincidence; asserting the flow alone would pass one that
	zeroed the flow but kept the stamp. Both, and against the same object.
	"""
	network = _parallel_pair()
	config = _config_for()
	injection = np.array([200.0, -200.0])

	opened = open_branches(network, [0])
	assert opened.branch_susceptance[0] == 0.0, (
		"the opened branch kept its susceptance, so `branch_flows` will compute a "
		"flow across a line that is out"
	)
	assert opened.susceptance[0, 1] == pytest.approx(
		network.susceptance[0, 1] + float(network.branch_susceptance[0])
	), (
		"the matrix still carries the opened branch's stamp; it must be rebuilt "
		"from the zeroed susceptances rather than edited"
	)

	solved = solve_snapshot(opened, injection, config)
	assert solved.flows_mw[0] == pytest.approx(0.0, abs=1e-9), (
		f"the opened branch carries {solved.flows_mw[0]} MW; an open line carries "
		f"no flow, and a phantom one charges the network for a line that is out"
	)
	# The whole flow rides the remaining branch, which is the physical statement
	# the zero above is the other half of.
	assert solved.flows_mw[1] == pytest.approx(200.0, rel=1e-9)
	assert solved.losses_mw < network_loss(network, injection, config), (
		"the opened topology must lose less than the closed one on this fixture"
	)


def network_loss(network: Network, injection: np.ndarray, config: LossConfig) -> float:
	"""The loss on a network at one injection, spelled once for the comparison."""
	return solve_snapshot(network, injection, config).losses_mw


def test_an_islanding_opening_is_counted_not_raised():
	"""A topology that cannot serve is skipped and counted, never propagated.

	Removing the only path to a bus makes the susceptance matrix singular, and
	the kernel raises rather than returning a zero angle -- a zero angle reads as
	"no flow" instead of "no path". The search catches it because an islanded
	topology serves nothing and so cannot be loss-optimal; a search that let the
	exception out would fail on a network where the honest answer is "one of the
	candidates is infeasible".
	"""
	# A radial three-bus network: opening the middle branch islands bus 2.
	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	susceptance = np.array([132.0**2 / 10.0, 132.0**2 / 10.0])
	network = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=susceptance,
		resistance_ohm=np.array([1.0, 1.0]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([200.0, 200.0]),
		branch_names=("AB", "BC"),
	)
	dispatch = np.array([[100.0, 0.0, -100.0]])
	_, result = optimal_switching(network, dispatch, _config_for())

	assert result.n_infeasible == 2, (
		f"opening either branch of a radial two-branch chain islands a bus, so "
		f"both candidates are infeasible; the search counted "
		f"{result.n_infeasible} and opened {result.opened_names}"
	)
	assert result.opened == [], (
		"an islanded topology was chosen as the optimum, which means it was "
		"compared on a loss the network cannot produce"
	)
	assert result.n_evaluated == 2, (
		"an infeasible candidate is still an evaluated one; counting it as "
		"unevaluated would understate the search's own scope"
	)


def test_a_binding_budget_records_itself_as_truncated():
	"""A partial enumeration is recorded, not passed off as an optimum.

	``switching_max_evaluations`` is a solve *budget* rather than a timeout
	because the enumeration is deterministic: a wall-clock limit would make the
	chosen topology depend on the machine, and two runs of one network would
	disagree. The cost is that a budget can bind, which is why ``truncated``
	exists -- a report reading a switching decision from a partial search has no
	other way to know.
	"""
	network = _four_bus_meshed()
	dispatch = np.array([[900.0, -300.0, -250.0, -350.0], [450.0, -150.0, -125.0, -175.0]])
	_, result = optimal_switching(
		network, dispatch, _config_for(switching_max_openings=2, switching_max_evaluations=3)
	)

	assert result.truncated is True, (
		"four single openings plus six pairs over four candidates cannot fit a "
		"budget of three solves, and the search reported a complete enumeration"
	)
	assert result.n_evaluated == 3, (
		f"the budget was three and the search evaluated {result.n_evaluated}"
	)
	assert result.max_openings == 2

	# The same network with a budget it fits is *not* truncated, which is what
	# makes the flag a measurement rather than a constant.
	_, complete = optimal_switching(
		network, dispatch, _config_for(switching_max_openings=1, switching_max_evaluations=512)
	)
	assert complete.truncated is False
	assert complete.n_evaluated == complete.n_candidates


def test_disabling_the_search_returns_the_network_unchanged():
	"""``switching_max_openings = 0`` is a recorded choice, not a silent no-op.

	The object identity is the assertion: a search that found nothing hands back
	a *copy* of the network, and a caller comparing topologies would see two
	objects where there is one topology. It also keeps the degenerate
	decomposition reachable for a caller who has decided no reconfiguration is
	available, which is why `measure`'s own default is left alone.
	"""
	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0]])
	returned, result = optimal_switching(network, dispatch, _config_for(switching_max_openings=0))

	assert returned is network, (
		"a disabled search returned a different object; the caller's network is "
		"already the answer and a copy invites a comparison that means nothing"
	)
	assert result.n_evaluated == 0, (
		"zero evaluated topologies is what distinguishes a disabled search from "
		"one that ran and found nothing"
	)
	assert result.opened == []
	assert result.reduction_mw == pytest.approx(0.0)


def test_a_candidate_carrying_no_susceptance_is_not_offered():
	"""A branch already out is not a switching candidate.

	Offering it would report "opening this line reduces loss by 0.0 MW" for a
	line that is already open -- a finding about the candidate list presented as
	a finding about the network.
	"""
	network = _parallel_pair()
	already_out = open_branches(network, [1])
	assert switching_candidates(already_out).tolist() == [0], (
		"a branch whose susceptance is zero was offered as a candidate; it "
		"carries no flow, so opening it changes nothing"
	)


def test_the_search_uses_the_series_mean_and_not_the_peak():
	"""The topology is chosen at the reference case's own loading.

	``measure`` attributes against a flat dispatch carrying the series mean, so a
	search run at the peak would choose a topology the reference case never sees
	-- and the topology-driven component would carry a switching decision taken
	under a loading the report does not show.
	"""
	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0], [400.0, -400.0]])
	_, result = optimal_switching(network, dispatch, _config_for())
	assert result.search_dispatch == "flat_mean"
	mean = reference_injection(dispatch)
	assert mean.tolist() == [300.0, -300.0], f"the series mean is {mean.tolist()}"

	# And the caller can override it, which is recorded rather than inferred.
	_, at_peak = optimal_switching(
		network, dispatch, _config_for(), search_dispatch_mw=np.array([400.0, -400.0])
	)
	assert at_peak.search_dispatch == "caller"


# --------------------------------------------------------------------------
# The decomposition the search exists to make measurable
# --------------------------------------------------------------------------


def test_the_components_sum_and_attribute_to_more_than_one_driver():
	"""The invariant §6.2 states, on the fixture where it is reachable.

	The sum is guaranteed by the model's validator, so asserting it alone would
	be a tautology -- what this adds is that the fixture produces a *non-zero
	topology component*, which is the number the specification hardcoded to zero.
	"""
	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0]])
	components = losses_components(network, dispatch, _config_for())

	assert components.sum_of_parts_mwh == pytest.approx(components.total_mwh, rel=1e-9)
	assert components.topology_driven_mwh > 0.0, (
		"the topology-driven component is zero on a fixture with a 41x "
		"loss-reducing opening, which is the specification's placeholder returned"
	)
	assert components.load_driven_mwh > 0.0
	shares = components.shares
	assert shares["topology_driven"] == pytest.approx(
		components.topology_driven_mwh / components.total_mwh
	)
	# The claim the published table carries, and the one the register's entry was
	# about: it is no longer `load driven == 1.0` for every network.
	assert shares["load_driven"] < 1.0


def test_the_sum_invariant_holds_as_a_property_over_random_networks():
	"""§6.2 states the invariant as a *property*, and this is that claim.

	The fixture above asserts the sum on one network where every term is
	non-zero. That is a stronger statement than the sum alone -- it shows the
	decomposition attributes to three drivers rather than one -- but it is one
	point. A property test is a different claim: the identity survives a
	network and a dispatch the author did not choose.

	**What can actually fail here, and what cannot.** The identity is algebraic
	in the four measurements and is enforced twice over -- by
	``decompose_losses`` and again by :class:`LossComponents`'s validator -- so
	the sum is not the part under test. The parts are: that ``measure`` resolves
	a loss-optimal reference network for a shape it has not seen, that the
	switching search returns a *connected* topology (an islanding choice would
	make the reference loss the sum of two islands' worth of nothing), and that
	the whole path survives buses with no load, parallel branches, and a
	single-snapshot series.

	**Why a fixed seed rather than hypothesis.** The plan asks for a property
	test and hypothesis is the usual spelling, but a drawn network is not a
	shrinkable object here -- the failure a reader needs to see is the *network*,
	and a seed makes it reproducible in a bug report. 40 draws is chosen to keep
	the module under a few seconds; the assertion is exact rather than
	approximate at 1e-9 relative, which is the tolerance §6.2 names.
	"""
	rng = np.random.default_rng(20261014)
	for draw in range(40):
		network = _random_network(rng)
		dispatch = _random_dispatch(rng, network.n_buses, int(rng.integers(1, 4)))
		config = _config_for(switching_max_evaluations=64)
		components = losses_components(network, dispatch, config)
		relative = abs(components.sum_of_parts_mwh - components.total_mwh) / max(
			abs(components.total_mwh), 1e-12
		)
		assert relative <= 1e-9, (
			f"draw {draw}: the components sum to {components.sum_of_parts_mwh} against "
			f"a total of {components.total_mwh}, a relative error of {relative:.3e} "
			f"on a {network.n_buses}-bus {network.n_branches}-branch network"
		)
		# The reference topology is the search's, so a topology that islanded
		# would make the reference loss the sum over disconnected islands and the
		# identity would still hold while measuring nothing.
		reference, result = optimal_switching(network, dispatch, config)
		assert result.n_evaluated > 0, (
			f"draw {draw}: the search evaluated no topology, so the reference the "
			f"components attribute against is the unreconfigured network"
		)
		assert np.isfinite(reference.susceptance).all(), (
			f"draw {draw}: the reference network carries a non-finite susceptance"
		)


def test_a_reference_network_alone_attributes_the_topology():
	"""The default that used to swallow the component, pinned in the repaired direction.

	``measure``'s ``topology_network`` defaulted to the *reference* network, so a
	caller who supplied a loss-optimal reference and no topology got
	``T - R == 0`` -- the degeneracy relocated into the signature that was
	supposed to fix it. It defaults to the actual network now, because the
	component is defined as what the actual topology adds over the reference and
	the actual network is the only one that can measure that.
	"""
	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0]])
	config = _config_for()
	reference, _ = optimal_switching(network, dispatch, config)

	inputs = measure(network, dispatch, config, reference_network=reference)
	# The reference case loses what the switched topology loses, and the actual
	# case loses the closed-network figure -- so `T - R` is the 92.59 MW saving
	# rather than zero.
	assert inputs.losses_with_actual_topology_only_mwh == pytest.approx(
		inputs.actual_losses_mwh, rel=1e-9
	)
	assert inputs.losses_with_actual_topology_only_mwh > inputs.reference_losses_mwh


def test_a_reference_dispatch_alone_still_changes_nothing():
	"""The half of the degeneracy that is *not* a default, kept pinned.

	``reference_dispatch_mw`` enters ``reference_losses`` and
	``losses_with_actual_topology_only`` identically and the kernel takes their
	difference, so it cancels. A repair that plumbed only a reference dispatch
	would leave the decomposition single-driver while looking like a fix; this is
	the canary that says so.
	"""
	from alea.losses.decompose import decompose

	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0]])
	config = _config_for()
	reference = np.array([[300.0, -300.0]])

	with_reference = decompose(measure(network, dispatch, config, reference_dispatch_mw=reference), config)
	without = decompose(measure(network, dispatch, config), config)
	assert with_reference.topology_driven_mwh == pytest.approx(0.0)
	assert without.topology_driven_mwh == pytest.approx(0.0)


# --------------------------------------------------------------------------
# The round trip: a frame, a stage, and a section a report can open
# --------------------------------------------------------------------------


def _write_inputs(tmp_path: Path, network: Network, dispatch: np.ndarray) -> None:
	"""The two artefacts the stage reads, written the way `network_arrays` writes them."""
	import pandas as pd

	from alea.io.pipeline import write_stage
	from alea.losses.service import network_to_payload
	from alea.provenance.models import DerivedProvenance

	processed = tmp_path / "processed"
	processed.mkdir(parents=True, exist_ok=True)
	provenance = DerivedProvenance(
		source_id="network_arrays",
		inputs=["<fixture>"],
		code_version="0.0.0",
		run_id="fixture",
		parameters={},
		notes="the switching module's own fixture",
	)
	write_stage(processed / "network_arrays.json", network_to_payload(network), provenance, format="json")
	frame = pd.DataFrame(
		dispatch,
		columns=[f"bus_{index}" for index in range(network.n_buses)],
		index=pd.date_range("2030-01-08", periods=dispatch.shape[0], freq="h", name="timestamp"),
	)
	write_stage(processed / "dispatch.parquet", frame, provenance, format="parquet")


def test_the_stage_writes_both_artefacts_from_one_search(tmp_path: Path):
	"""One stage, two artefacts: the report frame and the API's serving table.

	Both come from one decomposition, which is the point -- a second search for
	the serving table could choose a different reference topology, and the weekly
	report and the losses route would then disagree about the same network.
	"""
	import pandas as pd

	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0], [220.0, -220.0]])
	_write_inputs(tmp_path, network, dispatch)
	config = _config(tmp_path)
	out = resolve(config.paths.processed) / "loss_decomposition.parquet"

	build_stage("loss_decomposition", config, out)

	frame, provenance = read_artefact(out)
	frame = pd.DataFrame(frame)
	assert list(frame.columns) == ["label", "value", "unit", "loss_mwh", "component"], (
		f"the stage wrote {list(frame.columns)}; the sections bind their first "
		f"column to the label, their one numeric column to `value`, and `Basis` "
		f"to the row's basis"
	)
	# Shares in percent, because both sections declare unit `%`: a fraction under
	# a percent header is off by two orders of magnitude in a published report.
	assert set(frame["unit"]) == {"%"}, f"the frame's units are {set(frame['unit'])}"
	components = set(frame["component"])
	assert components == {"load_driven", "generation_driven", "topology_driven", "total"}, (
		f"the frame carries {sorted(components)}; every component is written, "
		f"including a zero one -- dropping it would make the defect invisible in "
		f"exactly the case it was reported in"
	)
	total = frame.loc[frame["component"] == "total", "value"].iloc[0]
	assert total == pytest.approx(100.0)
	shares = frame.loc[frame["component"] != "total", "value"].sum()
	assert shares == pytest.approx(100.0, rel=1e-9), (
		f"the component shares sum to {shares}%, and the parts are of the total by "
		f"construction"
	)
	assert provenance.parameters["switching_max_openings"] == 1

	# The serving table, from the same stage.
	serving = resolve(config.paths.processed) / "losses" / "decomposition.parquet"
	assert serving.exists(), (
		"the stage wrote the report frame and not the API's serving table; "
		"`publish.views.UNWIRED` held this path and the kernel is what closed it"
	)
	table, _ = read_artefact(serving)
	table = pd.DataFrame(table)
	assert list(table.columns) == [
		"country_iso",
		"period_start",
		"period_end",
		"total_loss",
		"components",
	], f"the serving table's columns are {list(table.columns)}"
	assert table["country_iso"].iloc[0] == "KE"
	assert table["period_start"].iloc[0].date() == date(2030, 1, 8)


def test_the_section_leaves_the_missing_list_and_renders(tmp_path: Path):
	"""The round trip, measured with `unprojected_sections` rather than inferred.

	The register said a producer exists; that is not the same as a report being
	able to open the section, and `capacity_update` is the case that proved it --
	recorded as produced, its rule exited 0, and `alea report monthly` raised
	``ReportDataError: no artefact``. So the section's absence is measured before
	and after, and the section is then assembled through the reader's own path.
	"""
	from alea.reporting.projection import project_section, unprojected_sections
	from alea.reporting.schemas import ReportCadence
	from alea.reporting.service import _section_from_spec, section_by_slug

	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0], [220.0, -220.0]])
	_write_inputs(tmp_path, network, dispatch)
	config = _config(tmp_path)

	before = unprojected_sections(ReportCadence.WEEKLY, config, as_of=ISSUE_DATE)
	assert "loss_decomposition" in before, (
		f"the section's dated artefact already exists before anything wrote it: {before}"
	)

	stage_out = resolve(config.paths.processed) / "loss_decomposition.parquet"
	build_stage("loss_decomposition", config, stage_out)
	project_section(
		ReportCadence.WEEKLY, "loss_decomposition", stage_out, config, as_of=ISSUE_DATE
	)

	after = unprojected_sections(ReportCadence.WEEKLY, config, as_of=ISSUE_DATE)
	assert "loss_decomposition" not in after, (
		f"the projection did not land the artefact where the section reads it; "
		f"still missing: {after}"
	)

	spec = section_by_slug(ReportCadence.WEEKLY, "loss_decomposition")
	warnings: list[str] = []
	rendered = _section_from_spec(spec, config, PERIOD_END[ReportCadence.WEEKLY], warnings)
	assert rendered is not None, f"the section did not assemble: {warnings}"
	assert len(rendered.tables) == 1, (
		f"the section rendered {len(rendered.tables)} tables; its spec declares one"
	)
	table = rendered.tables[0]
	assert table.columns == ["Component", "Share of input", "Basis"]
	labels = [row[0] for row in table.rows]
	assert labels == ["Load-driven", "Generation-driven", "Topology-driven", "Total"], (
		f"the section rendered {labels}; every component needs a row, and the "
		f"register's whole complaint was a table reading `load driven, 100.0`"
	)


def test_the_monthly_section_reads_the_same_frame(tmp_path: Path):
	"""The second cadence, from the one stage artefact.

	Both loss sections declare one numeric column at unit ``%`` and differ only
	in the header, so `decomposition_section_rows` writes one frame for both.
	This is the gate that the monthly one is not left absent: a projection per
	section is needed even where one producer feeds both.
	"""
	from alea.reporting.projection import project_section, unprojected_sections
	from alea.reporting.schemas import ReportCadence
	from alea.reporting.service import _section_from_spec, section_by_slug

	network = _parallel_pair()
	dispatch = np.array([[200.0, -200.0], [220.0, -220.0]])
	_write_inputs(tmp_path, network, dispatch)
	config = _config(tmp_path)

	before = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "loss_statistics" in before

	stage_out = resolve(config.paths.processed) / "loss_decomposition.parquet"
	build_stage("loss_decomposition", config, stage_out)
	project_section(
		ReportCadence.MONTHLY, "loss_statistics", stage_out, config, as_of=ISSUE_DATE
	)

	after = unprojected_sections(ReportCadence.MONTHLY, config, as_of=ISSUE_DATE)
	assert "loss_statistics" not in after, f"still missing: {after}"

	spec = section_by_slug(ReportCadence.MONTHLY, "loss_statistics")
	warnings: list[str] = []
	rendered = _section_from_spec(spec, config, PERIOD_END[ReportCadence.MONTHLY], warnings)
	assert rendered is not None, f"the section did not assemble: {warnings}"
	assert rendered.tables[0].columns == ["Component", "Loss share", "Basis"]


def test_a_missing_input_is_refused_rather_than_written_empty(tmp_path: Path):
	"""An absent input raises; an empty decomposition reads as "no losses".

	That is a claim about the network, and the truth is that no dispatch was
	read.
	"""
	from alea.io.artefacts import ArtefactError

	config = _config(tmp_path)
	out = resolve(config.paths.processed) / "loss_decomposition.parquet"
	with pytest.raises(ArtefactError, match="no network arrays"):
		build_stage("loss_decomposition", config, out)


def test_the_registers_moved_with_the_kernel():
	"""Both registers, both directions: the section is produced and the table wired.

	The entry for this section recorded the *symptom* -- a missing rule -- and
	the blocker was the switching kernel. Closing it had to move three
	registers in the same change, and this asserts all three rather than the
	one a reader would look at.
	"""
	from alea.publish.views import PROJECTION_STAGES, PUBLISHED_TABLES, UNWIRED
	from alea.reporting.producers import PRODUCERS, PROJECTED, UNPRODUCED

	assert "loss_decomposition" not in UNPRODUCED
	assert "loss_statistics" not in UNPRODUCED
	assert PRODUCERS["loss_decomposition"] == "losses.service._stage_loss_decomposition"
	assert PRODUCERS["loss_statistics"] == "losses.service._stage_loss_decomposition"
	assert PROJECTED["loss_decomposition"] == "project_loss_decomposition"
	assert PROJECTED["loss_statistics"] == "project_loss_statistics"

	path = PUBLISHED_TABLES["losses_decomposition"]
	assert path not in UNWIRED, (
		"the serving table is still recorded as unwired after the stage that "
		"writes it landed; the register would overstate a gap that is closed"
	)
	assert PROJECTION_STAGES["losses_decomposition"] == "loss_decomposition"
	# `mitigation` stays unproduced, and for a different reason: a mitigation
	# ranking is over capital measures, and no artefact records which measures
	# are candidates. The switching kernel ranks nothing.
	assert "mitigation" in UNPRODUCED
