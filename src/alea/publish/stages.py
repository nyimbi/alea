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

import pandas as pd

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError, read_artefact
from alea.io.pipeline import BuildContext, stage
from alea.logging import get_logger
from alea.provenance.models import DerivedProvenance

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
	from alea.losses.contingency import element_records
	from alea.losses.views import LossConfig
	from alea.publish.service import project, project_resilience_contingency

	from alea.io.pipeline import skip_if_current

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


__all__ = [
	"ARRAYS_ARTEFACT",
	"DISPATCH_ARTEFACT",
	"build_market_prices",
	"build_resilience_contingency",
]
