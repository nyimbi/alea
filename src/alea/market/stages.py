# SPDX-License-Identifier: MIT
"""Registered stages: the two report sections Layer 3 produces.

`market/service.py` holds the projections and `market/fleet.py` builds the fleet
they clear; neither writes a stage. This module is the third piece, and it is
the one `reporting/producers.py` names -- the register that makes "produced" a
claim someone makes rather than an inference drawn from a name match.

**Why these two stages exist at all.** `reporting/monthly.py` and
`reporting/quarterly.py` each declare one ``required=True`` section, and a
required section whose artefact is absent raises rather than warns -- so while
`market_report` and `market_outlook` had no producer, *neither cadence could be
generated from the pipeline*. That was the measured state and the register said
so. These stages are the closing of it.

**Why the network is resolved here and not declared as a rule input.** The
solved network's filename carries a content hash no rule can know at parse time,
so the rule declares the directory and the stage picks the newest -- exactly what
`@stage("market_prices")` does, and for the same reason.

**Where the value of lost load comes from.** ``config.market``. It is the one
market parameter no layer produces: capacity, marginal cost and availability are
the network's own columns, and the price of unserved energy is not in the
network at all. Both the rate and its recorded basis travel into the artefact's
provenance, because a clearing price from a short stack *is* the rate and a
reader has to be able to tell a defaulted one from a sourced one.
"""

from __future__ import annotations

from pathlib import Path

from alea.config.models import Config
from alea.config.paths import resolve
from alea.io.artefacts import ArtefactError
from alea.io.pipeline import BuildContext, stage
from alea.logging import get_logger
from alea.provenance.models import DerivedProvenance

logger = get_logger(__name__)


def _solved_network(config: Config, context: BuildContext) -> tuple[Path, list[str]]:
	"""The newest solved network and the inputs to record for it.

	Shared by both stages because they clear the same network and a stage that
	resolved it differently would be measuring a different system from its
	neighbour -- the same argument `losses.service`'s ``tlens`` and
	``critical_lines`` stages make for their two artefacts.
	"""
	from alea.io.artefacts import sha256_file
	from alea.planning.arrays import NETWORK_DIR, _newest_network

	network_dir = resolve(context.parameters.get("network_dir", NETWORK_DIR))
	named = context.parameters.get("network_path")
	# Only the *named* case is re-worded. `_newest_network`'s refusal is now
	# layer-neutral and names the market among the stages that read a solved
	# network, so re-wording it here would be a second copy of the same sentence
	# kept in step by hand -- and this one was written when the shared message
	# named the *loss* layer's reason, which is no longer true of it. A named
	# path has no shared message to inherit, and "a market clears a solved
	# network's fleet" is the part a reader of this stage needs.
	if named:
		path = Path(named)
		if not path.exists():
			raise ArtefactError(
				f"no solved network at {path}; run `alea solve` first. A market "
				f"clears a solved network's fleet, and a network that was never "
				f"solved has no generators to bid"
			)
	else:
		path = _newest_network(network_dir)

	digest = sha256_file(path)
	return path, [digest, *(value for value in context.inputs if value != digest)]


def _load_network(path: Path) -> object:
	"""The solved network, imported here so the stage module stays importable.

	``pypsa`` costs seconds to import and this module is imported by
	`alea.io.pipeline`'s registration walk, which runs on every CLI invocation
	that builds *any* stage.
	"""
	import pypsa

	return pypsa.Network(str(path))


def _strategy(context: BuildContext) -> object:
	"""The bidding strategy this run clears with, from the stage parameters.

	Competitive unless a parameter names a markup. The plan's exit criterion is
	that "competitive strategy reproduces Layer 1 marginal prices", so the
	benchmark is the default and a markup is an explicit, recorded departure from
	it -- the strategy kind lands in the artefact's provenance either way.
	"""
	from alea.market.strategy import Strategy

	markup = context.parameters.get("markup")
	if markup is None:
		return Strategy.competitive()
	return Strategy.from_markup(float(markup))


@stage("market_report")
def build_market_report(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: a solved network's clearing as the monthly report's rows.

	Writes one row per carrier with a ``volume`` and an ``average_price`` column
	-- the shape `reporting/monthly.py`'s ``market_report`` section binds, whose
	two numeric columns mean the reader refuses a row that carries only one
	number.
	"""
	from alea.io.artefacts import read_provenance
	from alea.io.pipeline import skip_if_current
	from alea.market.service import monthly_market_to_artefact

	path, inputs = _solved_network(config, context)
	existing = skip_if_current(out, inputs, stage_name="market_report", logger=context.logger)
	if existing is not None:
		return existing

	network = _load_network(path)
	monthly_market_to_artefact(
		network,
		out,
		value_of_lost_load_usd_per_mwh=config.market.value_of_lost_load_usd_per_mwh,
		value_of_lost_load_basis=config.market.value_of_lost_load_basis,
		inputs=inputs,
		strategy=_strategy(context),  # type: ignore[arg-type]
	)
	provenance = read_provenance(out)
	logger.info(
		"market.stage.market_report",
		network_file=path.name,
		voll=config.market.value_of_lost_load_usd_per_mwh,
		out=str(out),
	)
	return provenance


@stage("market_outlook")
def build_market_outlook(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: the quarterly price outlook's rows.

	The series is the clearing prices the solved network's own horizons support,
	not a four-quarter forecast -- no price-forecast model exists in this
	repository, and the projection records that in the provenance rather than
	writing four invented quarters.
	"""
	from alea.io.artefacts import read_provenance
	from alea.io.pipeline import skip_if_current
	from alea.market.service import quarterly_market_to_artefact

	path, inputs = _solved_network(config, context)
	existing = skip_if_current(out, inputs, stage_name="market_outlook", logger=context.logger)
	if existing is not None:
		return existing

	network = _load_network(path)
	quarterly_market_to_artefact(
		network,
		out,
		value_of_lost_load_usd_per_mwh=config.market.value_of_lost_load_usd_per_mwh,
		value_of_lost_load_basis=config.market.value_of_lost_load_basis,
		inputs=inputs,
		strategy=_strategy(context),  # type: ignore[arg-type]
		quarters=int(context.parameters.get("quarters", 4)),
	)
	provenance = read_provenance(out)
	logger.info(
		"market.stage.market_outlook",
		network_file=path.name,
		voll=config.market.value_of_lost_load_usd_per_mwh,
		out=str(out),
	)
	return provenance


__all__ = [
	"build_market_outlook",
	"build_market_report",
]
