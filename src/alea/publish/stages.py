# SPDX-License-Identifier: MIT
"""Serving stages: the pipeline step that turns a layer result into a table.

`alea.publish.service` holds the projections and `alea.publish.views` the
schemas; neither writes a stage. This module is the third piece, and it is the
one `PROJECTION_STAGES` names -- the register that makes "wired" a claim
someone makes rather than an inference the gate draws from a name match.

**Why a stage and not a call inside a layer stage.** AD-4 puts the seam at the
artefact: the layer writes its result, and the serving table is a different
shape of the same quantity (`__init__` records why). A layer stage that wrote
its own serving table would put a consumer's row layout inside the layer, which
is how a model acquires a field it cannot explain.

**The country problem, and why it is refused rather than guessed.** A serving
row carries ``country_iso`` and a solved network does not: buses have lon/lat
and no country. `project_prices` refuses for the same reason. Here the country
comes from the run's own scenario config, and a solve spanning more than one
country is refused outright -- a continental solve's contingencies are spread
across five power pools, and labelling every element with the first country in
``scenario.countries`` would serve a Kenyan contingency list for a Nigerian
network. One country is a fact about the run; several is a fact the artefact
does not carry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import BuildContext, stage
from alea.logging import get_logger
from alea.provenance.models import DerivedProvenance
from alea.registry.technologies import get_technology, is_known_carrier

logger = get_logger(__name__)

#: The arrays and dispatch `@stage("network_arrays")` writes, by the names
#: `alea.planning.arrays` declares. Named here rather than spelled inline so the
#: producer and this reader cannot come to disagree about where the file is.
ARRAYS_ARTEFACT = "network_arrays.json"
DISPATCH_ARTEFACT = "dispatch.parquet"


def _single_country(config: Config) -> str:
	"""The one country this run models, or a refusal.

	A serving row is per country and a solved network does not record one. The
	scenario does, and it may name several -- so this returns the single country
	when there is exactly one and raises otherwise, rather than taking the first
	and serving a list of contingencies under a country the network may not
	cover.
	"""
	countries = [str(iso) for iso in config.scenario.countries if iso]
	if len(countries) != 1:
		raise ArtefactError(
			f"the scenario models {len(countries)} countries ({', '.join(countries) or 'none'}); "
			f"a contingency table is per country and the solved network carries no "
			f"bus-to-country mapping. Run one country at a time, or add the mapping "
			f"the projection needs -- labelling every element with the first country "
			f"serves a wrong list that looks correct"
		)
	return countries[0]


def _read_arrays_and_dispatch(config: Config) -> tuple[Any, pd.DataFrame, list[str]]:
	"""The solved network's arrays and dispatch, from ``paths.processed``."""
	processed = resolve(config.paths.processed)
	arrays_path = processed / ARRAYS_ARTEFACT
	dispatch_path = processed / DISPATCH_ARTEFACT

	if not arrays_path.exists():
		raise ArtefactError(
			f"no network arrays at {arrays_path}; run `alea build network_arrays` "
			f"first. A contingency sweep needs the branch table and the dispatch it "
			f"carries"
		)
	if not dispatch_path.exists():
		raise ArtefactError(
			f"no dispatch series at {dispatch_path}; run `alea build network_arrays` "
			f"first"
		)

	from alea.io.artefacts import sha256_file
	from alea.losses.service import _network_from_payload

	payload, _ = read_artefact(arrays_path)
	network = _network_from_payload(payload)
	dispatch, _ = read_artefact(dispatch_path)
	matrix = pd.DataFrame(dispatch).select_dtypes("number")
	if matrix.shape[1] != network.n_buses:
		raise ArtefactError(
			f"the dispatch has {matrix.shape[1]} columns but the arrays name "
			f"{network.n_buses} buses; the two artefacts are positional partners and a "
			f"mismatch means they came from different solves"
		)
	inputs = [sha256_file(arrays_path), sha256_file(dispatch_path)]
	return network, matrix, inputs


@stage("resilience_contingency")
def build_resilience_contingency(
	config: Config, out: Path, context: BuildContext
) -> DerivedProvenance:
	"""Registered stage: the N-1 sweep as per-element serving rows.

	The per-element form. `contingency_to_artefact` writes ``summary()``, one
	aggregate for the whole sweep, and the serving schema is one row per
	element -- so this stage reads the sweep rather than the summary, which is
	why it is a serving stage and not a projection of the layer's artefact.
	"""
	from alea.io.pipeline import skip_if_current
	from alea.losses.contingency import element_records
	from alea.publish.service import project, project_resilience_contingency

	country_iso = _single_country(config)
	network, matrix, inputs = _read_arrays_and_dispatch(config)

	# This stage resolves its own inputs -- the arrays and dispatch at their
	# conventional paths -- so no rule can declare them and `build_stage`'s own
	# check can never fire. Without this call every `alea build
	# resilience_contingency` re-sweeps, which is the state every stage in the
	# workflow was in before `--input` existed.
	existing = skip_if_current(
		out, inputs, stage_name="resilience_contingency", logger=context.logger
	)
	if existing is not None:
		return existing

	# The configured loss section, with the reference bus taken from the solve
	# options when the section does not name one -- the same precedence
	# `@stage("tlens")` applies, because the slack bus is a property of the
	# network the solve used rather than a loss default.
	losses = config.losses
	if "slack_bus" not in losses.model_fields_set and "slack_bus" in config.solve.solver_options:
		losses = losses.model_copy(update={"slack_bus": config.solve.solver_options["slack_bus"]})

	records = element_records(network, matrix.to_numpy(dtype=float), losses)
	frame = project_resilience_contingency(records, country_iso=country_iso)
	# `project` checks the frame against the schema, writes it *and* its
	# provenance, and returns the checksum. Building a `DerivedProvenance` here
	# and passing it would be discarded -- `project` writes its own -- so the
	# provenance the stage returns is read back from what was written. One
	# writer, so the sidecar cannot disagree with the payload it describes.
	project(
		"resilience_contingency",
		frame,
		out,
		inputs=inputs,
		parameters={
			"country_iso": country_iso,
			"n_elements": len(records),
			"n_snapshots": int(matrix.shape[0]),
			"slack_bus": losses.slack_bus,
			"snapshot_hours": losses.snapshot_hours,
		},
		notes=(
			"N-1 contingency sweep as per-element rows. `load_shed_mw` is the peak "
			"unserved load over the snapshot series, not its sum: the kernel returns "
			"MW per snapshot and only a peak is MW, while a sum would be MWh printed "
			"under a unit that says MW."
		),
	)
	from alea.io.artefacts import read_provenance

	provenance = read_provenance(out)
	logger.info(
		"publish.stage.resilience_contingency",
		country=country_iso,
		elements=len(records),
		out=str(out),
	)
	return provenance


@stage("market_prices")
def build_market_prices(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: a solved network's marginal prices as serving rows.

	The register recorded this table's blocker as "needs a bus-to-country
	mapping ... no artefact carries one". That was overstated for the case the
	pipeline actually runs: `_single_country` reads the country from the run's
	own scenario, which is where it has always come from for the one serving
	table that was wired, and a single-country solve is what
	`scenario.countries` names by default. A multi-country run is still refused,
	and for the reason the register gave -- the network carries no per-bus
	country, so labelling every bus with the first country would serve a Kenyan
	price for a Nigerian bus.

	Reads the solved network rather than the `network_arrays` bundle because the
	bundle does not carry `buses_t.marginal_price`: it holds the loss kernel's
	branch and dispatch arrays, and a price is neither. So this stage resolves
	the network the same way `@stage("network_arrays")` does, newest-first, and
	records the digest it read.
	"""
	from alea.io.artefacts import read_provenance, sha256_file
	from alea.io.pipeline import skip_if_current
	from alea.planning.arrays import NETWORK_DIR, _newest_network
	from alea.planning.dispatch import marginal_prices
	from alea.publish.service import project, project_prices

	country_iso = _single_country(config)
	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="market_prices", logger=context.logger)
	if existing is not None:
		return existing

	import pypsa

	network = pypsa.Network(str(path))
	prices = marginal_prices(network)
	# Every bus maps to the run's single country, which is a fact about the
	# scenario rather than an assumption about the geography: a multi-country
	# run never reaches here.
	mapping = {str(bus): country_iso for bus in prices.columns}
	frame = project_prices(prices, countries=mapping)
	project(
		"market_prices",
		frame,
		out,
		inputs=inputs,
		parameters={
			"country_iso": country_iso,
			"n_buses": int(prices.shape[1]),
			"n_snapshots": int(prices.shape[0]),
			"network_file": path.name,
			"currency": config.costs.base_currency,
		},
		notes=(
			"Locational marginal prices from the solved network's duals. Every bus "
			"is labelled with the scenario's single country: the network carries no "
			"per-bus country, so a multi-country run is refused rather than "
			"labelled with the first."
		),
	)
	provenance = read_provenance(out)
	logger.info(
		"publish.stage.market_prices",
		country=country_iso,
		buses=int(prices.shape[1]),
		out=str(out),
	)
	return provenance


@stage("market_capture_rates")
def build_market_capture_rates(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: a solved network's capture prices as serving rows.

	The capture price is ``(p x price).sum() / p.sum()`` per carrier -- the
	arithmetic `IMPLEMENTATION_PLAN.md` §5.4 names as Layer 3's first build,
	because it validates the network schema against a real use.

	**The curve is one point, and that is a fact about the run.** The serving
	table is a *curve* -- capture rate against VRE penetration -- and one solve
	has one renewable mix, hence one penetration. Producing the axis the curve
	needs is a *sweep*: the same network re-solved at several ``renewable_multiplier``
	values, each giving a (penetration, capture) pair. That sweep is
	`whatif.sweep`'s job and the frontier's axis, and this stage serves the point
	the run it is given actually supports rather than inventing a curve.

	The row is a legitimate one-point curve, not a fabricated one: the schema
	declares ``technology`` and ``vre_penetration`` precisely so a consumer can
	tell which point this is. A stage that wrote several rows from one solve
	would be the "gap moved, not closed" failure -- a curve that reads as
	measured and is not.

	**The dispatch is a second solve, not a re-read.** A capture price needs a
	per-snapshot generation and a per-snapshot price, and a capacity-expansion
	solve leaves neither. `solve_dispatch` fixes the capacity the expansion chose
	and re-solves hour by hour, which is what makes the prices marginal prices
	rather than the expansion's period duals.
	"""
	from alea.io.artefacts import read_provenance, sha256_file
	from alea.io.pipeline import skip_if_current
	from alea.market.capture import cannibalisation_curve
	from alea.planning.arrays import NETWORK_DIR, _newest_network
	from alea.planning.dispatch import generation_by_carrier, marginal_prices, solve_dispatch
	from alea.publish.service import project, project_capture_rates

	country_iso = _single_country(config)
	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	path = Path(named) if named else _newest_network(network_dir)
	if not path.exists():
		raise ArtefactError(f"no solved network at {path}")

	digest = sha256_file(path)
	inputs = [digest, *(value for value in context.inputs if value != digest)]
	existing = skip_if_current(out, inputs, stage_name="market_capture_rates", logger=context.logger)
	if existing is not None:
		return existing

	import pypsa

	network = pypsa.Network(str(path))
	solve_dispatch(network, config)

	# One price series for the single-country run: every bus is labelled with the
	# scenario's country, so the locational prices differ only by congestion and
	# the time-weighted reference the capture *rate* divides by is the system
	# price -- each bus weighted by the load it serves. A multi-country run never
	# reaches here (`_single_country` refuses it), so there is one country to
	# weight for.
	prices = marginal_prices(network)
	weights = network.snapshot_weightings.get("objective")
	system_price = _system_price(network, prices)

	generation = generation_by_carrier(network)
	technology = str(context.parameters.get("technology", "")) or _dominant_renewable(generation)
	if not technology:
		raise ArtefactError(
			"the solved network has no renewable carrier to build a capture curve "
			"for; pass `--set technology=<carrier>` to name one explicitly"
		)

	# A carrier that generated nothing anywhere cannot have a capture price, and
	# `cannibalisation_curve` writes NaN for it -- so the curve is one point with
	# an undefined rate, which is a finding rather than a failure.
	column = _carrier_column(generation, technology)
	generated = np.asarray(column, dtype=np.float64) * (
		1.0 if weights is None else np.asarray(weights, dtype=np.float64)
	)
	revenue = float(np.nansum(generated * system_price))
	energy = float(np.nansum(generated))
	capture = revenue / energy if energy > 0.0 else float("nan")
	time_weighted = float(np.nanmean(system_price)) if len(system_price) else float("nan")
	penetration = _vre_penetration(generation, technology)

	curve = cannibalisation_curve([(penetration, capture, time_weighted)])
	frame = project_capture_rates(curve, technology=technology)
	project(
		"market_capture_rates",
		frame,
		out,
		inputs=inputs,
		parameters={
			"country_iso": country_iso,
			"technology": technology,
			"vre_penetration": penetration,
			"capture_price_usd_per_mwh": None if not np.isfinite(capture) else capture,
			"time_weighted_price_usd_per_mwh": None if not np.isfinite(time_weighted) else time_weighted,
			"n_snapshots": int(len(system_price)),
			"network_file": path.name,
		},
		notes=(
			"One curve point from one solve: the run's renewable mix gives one VRE "
			"penetration, so the table holds the point that run supports. The "
			"capture-rate *curve* -- the axis a developer sizes against -- is the "
			"what-if sweep's output, re-solving at several renewable multipliers; "
			"this stage serves the point rather than inventing the curve."
		),
	)
	provenance = read_provenance(out)
	logger.info(
		"publish.stage.market_capture_rates",
		country=country_iso,
		technology=technology,
		vre_penetration=round(penetration, 4),
		out=str(out),
	)
	return provenance


def _system_price(network: Any, prices: pd.DataFrame) -> np.ndarray:
	"""The load-weighted mean price per snapshot.

	The capture *rate* divides the carrier's capture price by the time-weighted
	system price, and the system price is the price the system as a whole paid --
	each bus weighted by the load it served. Weighting by load rather than taking
	the simple mean across buses matters on a congested network, where an
	unloaded bus can carry a wildly different price from the one demand is
	actually paying.

	Loads may be static (a ``p_set`` column) or dynamic (``loads_t.p_set``), and
	a network built without a demand stage uses the static form -- the same trap
	`whatif.extract._availability` records for ``p_max_pu``. Both are read; with
	no load at all the simple mean is returned rather than a zero-weighted
	nonsense, and a snapshot with no load falls back to the mean for that row.
	"""
	values = prices.to_numpy(dtype=np.float64)
	loads = _load_by_bus(network, prices)
	if loads is None:
		return np.asarray(np.nanmean(values, axis=1), dtype=np.float64)

	bus_weights = np.asarray(loads, dtype=np.float64)
	if bus_weights.shape != values.shape:
		raise ArtefactError(
			f"load weights {bus_weights.shape} do not align with prices {values.shape}; "
			f"the two come from different networks"
		)
	row_totals = bus_weights.sum(axis=1)
	# A snapshot with no load has no load-weighted price. The simple mean across
	# buses is the only defined fallback, and it is taken per row rather than
	# substituting a global constant that would be wrong for that hour.
	weighted = np.where(
		row_totals > 0.0,
		np.divide(
			np.nansum(values * bus_weights, axis=1),
			np.where(row_totals > 0.0, row_totals, 1.0),
		),
		np.nanmean(values, axis=1),
	)
	return np.asarray(weighted, dtype=np.float64)


def _load_by_bus(network: Any, prices: pd.DataFrame) -> np.ndarray | None:
	"""Per-snapshot, per-bus load in the price columns' order, or ``None``.

	``None`` means the network carries no load at any bus, so there is nothing to
	weight by. The columns are aligned to ``prices`` rather than assumed to
	match, because a network whose load table and price table name different
	buses would otherwise weight the wrong columns together.
	"""
	loads = getattr(network, "loads", None)
	if loads is None or len(loads) == 0:
		return None

	bus_of = loads["bus"].astype(str)
	static = pd.to_numeric(loads.get("p_set"), errors="coerce")
	dynamic = getattr(getattr(network, "loads_t", None), "p_set", None)

	per_bus = pd.DataFrame(0.0, index=prices.index, columns=[str(b) for b in prices.columns])
	for name in loads.index:
		bus = str(bus_of.loc[name])
		if bus not in per_bus.columns:
			continue
		if dynamic is not None and not dynamic.empty and name in dynamic.columns:
			series = pd.to_numeric(dynamic[name], errors="coerce")
		else:
			value = static.loc[name] if name in static.index else np.nan
			series = pd.Series(float(value) if pd.notna(value) else 0.0, index=prices.index)
		per_bus[bus] = per_bus[bus].add(series.reindex(prices.index).fillna(0.0), fill_value=0.0)

	matrix = per_bus.to_numpy(dtype=np.float64)
	if not np.isfinite(matrix).all() or float(np.nansum(matrix)) <= 0.0:
		return None
	return matrix


def _dominant_renewable(generation: pd.DataFrame) -> str:
	"""The renewable carrier that generated the most, or ``""``.

	The curve is per technology and the stage is given no carrier, so it picks
	the one the run is *about*: the largest renewable generator. Picking the
	largest carrier outright would pick coal on a coal-heavy network and serve a
	capture curve for a fuel with no cannibalisation to measure.
	"""

	totals: dict[str, float] = {}
	for carrier in generation.columns:
		name = str(carrier)
		try:
			renewable = is_known_carrier(name) and get_technology(name).renewable
		except KeyError:
			renewable = False
		if renewable:
			totals[name] = float(pd.to_numeric(generation[carrier], errors="coerce").sum())
	if not totals:
		return ""
	return max(totals, key=lambda name: totals[name])


def _carrier_column(generation: pd.DataFrame, technology: str) -> pd.Series:
	"""The generation series for ``technology``, resolved through the registry.

	A network may name a carrier by an upstream alias ("wind" for "onwind"), so
	an exact column match is not enough. The registry's canonical name is the
	fallback, and an unmatched carrier is a refusal rather than a zero series --
	a zero series would serve a capture curve for a technology that generated
	nothing, which reads as a measurement.
	"""
	if technology in generation.columns:
		return pd.to_numeric(generation[technology], errors="coerce")
	for carrier in generation.columns:
		if str(carrier) == technology:
			return pd.to_numeric(generation[carrier], errors="coerce")
	try:
		canonical = get_technology(technology).name
	except KeyError as exc:
		raise ArtefactError(
			f"technology {technology!r} is not a registered carrier and not a "
			f"column of the dispatch; known columns: {sorted(str(c) for c in generation.columns)}"
		) from exc
	if canonical in generation.columns:
		return pd.to_numeric(generation[canonical], errors="coerce")
	raise ArtefactError(
		f"technology {technology!r} resolves to {canonical!r}, which is not a "
		f"dispatch column: {sorted(str(c) for c in generation.columns)}"
	)


def _vre_penetration(generation: pd.DataFrame, technology: str) -> float:
	"""The renewable share of generation, the curve's x-axis.

	This is the VRE penetration the run is *at*, and it is the share of total
	generation rather than of capacity: the curve's claim is about the price a
	carrier receives per MWh it produces, and a capacity share would put a
	capacity number on a generation axis.
	"""
	total = float(pd.to_numeric(generation.to_numpy().ravel(), errors="coerce").sum())
	if total <= 0.0:
		return 0.0

	renewable = 0.0
	for carrier in generation.columns:
		name = str(carrier)
		try:
			if is_known_carrier(name) and get_technology(name).renewable:
				renewable += float(pd.to_numeric(generation[carrier], errors="coerce").sum())
		except KeyError:
			continue
	return min(1.0, max(0.0, renewable / total))


__all__ = [
	"ARRAYS_ARTEFACT",
	"DISPATCH_ARTEFACT",
	"build_market_capture_rates",
	"build_market_prices",
	"build_resilience_contingency",
]
