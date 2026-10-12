# SPDX-License-Identifier: MIT
"""The serving projection: every artefact the API reads has a producer.

**The defect this closes.** Layer 8's contract is that no route computes -- every
route reads an artefact. Nothing checked the other half of that sentence:
*something must write them*. All eleven tabular paths `alea.api.repository`
reads were written by nothing outside `alea.api`, and the Layer 8 suite passed
because `tests/ci/test_api_layer8.py` writes every one of them as a fixture. A
test that builds its own inputs cannot detect that no production code builds
them. That is the recorded lesson about Wakili's 24 `/ops/*` endpoints: a green
suite over a surface nothing can reach is the appearance of coverage.

The gates below cross the repository's read paths against the projection's
declared paths, and each projection is run to a real artefact and read back
through `read_artefact` -- a projection that wrote a payload without a sidecar,
or dropped a column, fails here rather than serving zeros.

**What is not covered, and is named.** `TlensRowOut` serves T&D loss
percentages by country-year. No layer computes them and no source provides them,
and `spec4-base.md` §22 lists `/api/v1/losses/tlens` as a *critical line
ranking*, which is what the layer computes. `test_every_unprojectable_path_is_
still_a_gap` asserts that gap is exactly the set recorded in
`alea.publish.views.UNPROJECTABLE`, so it cannot grow silently and cannot be
closed without this file being edited -- the `UNIMPLEMENTED_FETCHERS` pattern.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from alea.api.repository import Repository
from alea.config.models import Config
from alea.io.artefacts import read_artefact
from alea.publish.service import (
	project,
	project_capture_rates,
	project_loss_decomposition,
	project_loss_mitigation,
	project_maintenance_predictions,
	project_outage_forecast,
	project_outage_history,
	project_outage_validation,
	project_ppa_benchmarks,
	project_prices,
	project_resilience_contingency,
	project_resilience_metrics,
	table_path,
)
from alea.publish.views import (
	PRODUCED_ELSEWHERE,
	PROJECTION_STAGES,
	PUBLISHED_TABLES,
	UNPROJECTABLE,
	UNWIRED,
)
from tests.ci.canaries import REPO

REPOSITORY_PY = REPO / "src" / "alea" / "api" / "repository.py"

# The tabular paths the repository reads, as literals in its source. The
# repository names them by string, so the source is the only place they exist --
# reading them off a running Repository would need a populated tree, which is the
# fixture this gate exists to stop trusting.
_READ_PATTERN = re.compile(r'"(data/processed/[^"]+\.parquet)"')


def _repository_read_paths() -> set[str]:
	"""Every ``data/processed/*.parquet`` literal in the repository source."""
	assert REPOSITORY_PY.exists(), f"the repository source moved from {REPOSITORY_PY}"
	source = REPOSITORY_PY.read_text(encoding="utf-8")
	found = set(_READ_PATTERN.findall(source))
	assert found, (
		"no artefact path literals found in repository.py; the gate is reading a "
		"source that no longer holds them and would pass against anything"
	)
	return found


def _produced_paths() -> set[str]:
	"""Serving paths a *registered stage* actually writes.

	Read from `PROJECTION_STAGES`, the explicit claim that a stage writes a
	table, and checked against the registry. It is deliberately not inferred
	from a name match: `outage_history` is both a serving table
	(`data/processed/outages/history.parquet`) and a layer stage, and the layer
	stage writes `data/processed/outage_history.parquet` -- a different path
	holding a different quantity. Inferring production from the shared name
	marked the serving table produced while nothing wrote it, which is the
	defect this package exists to close, reproduced inside its own gate.
	"""
	from alea.io.pipeline import registered_stages

	registered = set(registered_stages())
	assert registered, "no stages registered; the registry import list is broken"
	missing = sorted(
		f"{table}: {stage}"
		for table, stage in PROJECTION_STAGES.items()
		if stage not in registered
	)
	assert not missing, (
		f"a projection stage is recorded that is not registered: {missing}. The "
		f"claim outlived its producer, which is the exemption failure in a "
		f"different register."
	)
	unknown = sorted(set(PROJECTION_STAGES) - set(PUBLISHED_TABLES))
	assert not unknown, (
		f"`PROJECTION_STAGES` names tables `PUBLISHED_TABLES` does not declare: "
		f"{unknown}"
	)
	return {PUBLISHED_TABLES[table] for table in PROJECTION_STAGES}


# --------------------------------------------------------------------------
# The gate: declared paths and read paths are the same set
# --------------------------------------------------------------------------


def test_every_path_the_repository_reads_is_accounted_for():
	"""No route reads a table nothing accounts for.

	This is the gate. Before the projection package, all eleven paths were
	written by nothing outside `alea.api` and the Layer 8 suite passed anyway,
	because its fixtures wrote them.

	*Accounted for* is the honest form of *produced*. A path is accounted for
	when it is written by a registered stage, written by a layer stage
	(`PRODUCED_ELSEWHERE`), has no source to project from (`UNPROJECTABLE`), or
	has a projection but no stage that runs it (`UNWIRED`). The last register is
	a named gap, not coverage -- and `test_the_unwired_set_is_exactly_what_is_
	recorded` is what keeps it from being a place to hide.

	Asserting all eleven are *produced* would be a gate that cannot pass, and a
	gate that cannot pass is indistinguishable from no gate. What this asserts
	is that none of them is silent: every one is in a register with a reason,
	and the size of the gap is a number in the source rather than an absence.
	"""
	read = _repository_read_paths()
	accounted = (
		_produced_paths()
		| set(PRODUCED_ELSEWHERE)
		| set(UNPROJECTABLE)
		| set(UNWIRED)
	)
	unaccounted = sorted(read - accounted)
	assert not unaccounted, (
		f"{len(unaccounted)} artefact(s) the API reads are in no register: "
		f"{unaccounted}. The API serves an empty page for each, and a route serving "
		f"an empty page for a table no pipeline writes is a route that looks like "
		f"it works. Record it in `alea.publish.views.UNWIRED` with the reason, or "
		f"project and wire it."
	)


def test_the_unwired_set_is_exactly_what_is_recorded():
	"""The gap is the recorded set, so wiring a table forces the register to shrink.

	A named gap is only a gate if changing it fails something. If a table gains
	a stage, `PROJECTION_STAGES` gains an entry and `UNWIRED` must lose one --
	this fails until it does, which is what stops the register growing a stale
	entry that overstates the gap, and stops a newly unwired table joining
	quietly.
	"""
	declared = set(PUBLISHED_TABLES.values())
	produced = _produced_paths()
	unwired = declared - produced
	assert unwired == set(UNWIRED), (
		f"the unwired set changed: now {sorted(unwired)}, recorded "
		f"{sorted(UNWIRED)}. A table that gained a stage moves out of `UNWIRED` "
		f"into `PROJECTION_STAGES`; a table that lost one moves the other way."
	)


def test_every_unwired_path_names_a_reason():
	"""An unwired table with no reason is an omission wearing a register's clothes."""
	for path, reason in UNWIRED.items():
		assert reason.strip(), f"the unwired table {path!r} has no recorded reason"
		assert len(reason) > 80, (
			f"the unwired table {path!r} has a reason too short to be one: {reason!r}"
		)


def test_every_projected_table_is_read_by_the_repository():
	"""The other direction: a projection nothing reads is a table nobody wants.

	One-directional coverage hides half the defect. A projection to a path no
	route reads is dead code that runs in the workflow, costs a stage, and
	serves nobody -- and it looks identical to a working one from the
	projection's own tests.
	"""
	read = _repository_read_paths()
	produced = set(PUBLISHED_TABLES.values())
	unread = sorted(produced - read)
	assert not unread, (
		f"{len(unread)} projected table(s) no repository path reads: {unread}. "
		f"A projection to a path nothing serves is a stage that runs for nobody."
	)


def test_every_unprojectable_path_is_still_a_gap():
	"""The named gaps are exactly the paths with no producer at all.

	An explicit register rather than an implicit omission. If a path becomes
	projectable the set changes and this fails, which is what forces the
	register to shrink rather than rot -- and if a *new* path becomes
	unprojectable without being named, this fails too.
	"""
	read = _repository_read_paths()
	covered = set(PUBLISHED_TABLES.values()) | set(PRODUCED_ELSEWHERE)
	uncovered = read - covered
	assert uncovered == set(UNPROJECTABLE), (
		f"the unprojectable set changed: now {sorted(uncovered)}, "
		f"recorded {sorted(UNPROJECTABLE)}. Update "
		f"`alea.publish.views.UNPROJECTABLE` with the reason, or project the path."
	)


def test_every_path_produced_elsewhere_names_a_registered_stage():
	"""An exemption whose stage does not exist is a path with no producer.

	A path claimed as "the layer writes it" is only exempt if the layer still
	does. A stage renamed or removed leaves the claim behind, and the exemption
	then hides exactly the defect it was granted to distinguish.
	"""
	from alea.io.pipeline import registered_stages

	registered = set(registered_stages())
	assert registered, "no stages registered; the registry import list is broken"
	for path, stage_name in PRODUCED_ELSEWHERE.items():
		assert stage_name in registered, (
			f"{path} is recorded as produced by stage {stage_name!r}, which is not "
			f"registered; the exemption outlived its producer. Registered: "
			f"{sorted(registered)}"
		)


def test_the_gap_register_names_a_reason():
	"""A gap with no reason is an omission wearing a register's clothes."""
	for name, reason in UNPROJECTABLE.items():
		assert reason.strip(), f"the gap {name!r} has no recorded reason"
		assert len(reason) > 80, (
			f"the gap {name!r} has a reason too short to be one: {reason!r}"
		)


# --------------------------------------------------------------------------
# Each projection writes a table the repository can read
# --------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
	"""A scratch repository root, so `resolve` writes under the test.

	The config is loaded *before* the redirect and stashed on the module, because
	`load_config` reads ``config/config.default.yaml`` through ``repo_root``: a
	scratch root set first leaves the default file unfound and every test here
	would fail on the load rather than on the projection. Patching the module
	attribute rather than the imported name is what redirects every relative
	path, since `resolve` calls `repo_root` as a module global.
	"""
	from alea.config.loader import load_config
	from alea.config.paths import repo_root

	_LOADED_CONFIG[0] = load_config()
	(tmp_path / "pyproject.toml").write_text("[project]\nname='scratch'\n", encoding="utf-8")
	monkeypatch.setenv("ALEA_ROOT", str(tmp_path))
	repo_root.cache_clear()
	yield tmp_path
	repo_root.cache_clear()
	_LOADED_CONFIG[0] = None


_LOADED_CONFIG: list[Config | None] = [None]


def _cell(frame: pd.DataFrame, column: str, row: int = 0) -> float:
	"""One numeric cell as a float.

	``frame.loc[row, column]`` is typed ``Scalar``, the union of everything a
	cell can hold, so narrowing it at each call site means a cast per assertion.
	The list comprehension is the same narrowing `alea.losses.flow` documents for
	``Series.map``: reading through ``list(...)`` gives a real element type.
	"""
	values = list(frame[column])
	assert values, f"{column}: the table has no rows"
	return float(values[row])


def _text_cell(frame: pd.DataFrame, column: str, row: int = 0) -> str:
	"""One cell as a string, for the same reason as :func:`_cell`."""
	values = list(frame[column])
	assert values, f"{column}: the table has no rows"
	return str(values[row])


def _write(root: Path, name: str, frame: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
	"""Project ``frame`` to ``name``'s declared path and read it back."""
	checksum, checked = project(
		name, frame, table_path(name), inputs=["sha256:fixture-input"], **kwargs  # type: ignore[arg-type]
	)
	assert checksum, f"{name}: the write returned no checksum"
	payload, provenance = read_artefact(table_path(name))
	assert isinstance(payload, pd.DataFrame), f"{name}: wrote {type(payload).__name__}"
	assert provenance.source_id == f"publish.{name}"
	assert provenance.inputs, f"{name}: the provenance records no inputs"
	return payload


def test_market_prices_project_and_read_back(root: Path):
	"""A marginal-price frame becomes servable rows, one per bus-hour."""
	prices = pd.DataFrame(
		{"bus_0": [80.0, 85.0], "bus_1": [79.0, 84.0]},
		index=pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T01:00Z"]),
	)
	frame = project_prices(prices, countries={"bus_0": "KE", "bus_1": "KE"})
	written = _write(root, "market_prices", frame)
	assert len(written) == 4, "two buses over two hours is four rows"
	assert set(written["country_iso"]) == {"KE"}
	assert set(written["unit"]) == {"USD/MWh"}


def test_market_prices_refuses_an_unmapped_bus(root: Path):
	"""A bus with no country is refused, not written as its own name.

	Writing the bus into ``country_iso`` produces a row that filters to nothing
	while looking correct, which is worse than a failure.
	"""
	prices = pd.DataFrame({"bus_0": [80.0]}, index=pd.to_datetime(["2026-01-01T00:00Z"]))
	with pytest.raises(Exception, match="no country mapping"):
		project_prices(prices, countries={"bus_9": "KE"})


def test_capture_rates_keep_a_gap_as_nan(root: Path):
	"""A point with no capture rate is written NaN, not dropped."""
	from alea.market.views import CaptureCurvePoint

	curve = [
		CaptureCurvePoint(vre_share=0.1, capture_rate=0.95, cannibalisation=0.05),
		CaptureCurvePoint(vre_share=0.2, capture_rate=None, cannibalisation=None),
	]
	frame = project_capture_rates(curve, technology="solar")
	assert len(frame) == 2, "a dropped point is a curve that reads as complete"
	written = _write(root, "market_capture_rates", frame)
	assert len(written) == 2
	assert bool(written["capture_rate"].isna().any())


def test_ppa_benchmarks_state_their_source(root: Path):
	"""Every benchmark row names where the price came from."""
	from alea.market.ppa import ppa_benchmark

	benchmark = ppa_benchmark("KE", "solar", 20, 60.0)
	frame = project_ppa_benchmarks([benchmark])
	assert _text_cell(frame, "benchmark_source"), "a benchmark with no source is uncheckable"
	written = _write(root, "market_ppa_benchmarks", frame)
	assert int(_cell(written, "tenor_years")) == 20


def test_outage_forecast_carries_a_probability(root: Path):
	"""The forecast keeps a probability, never a flag."""
	frame = project_outage_forecast(
		{"Nairobi": 0.72},
		country_iso="KE",
		horizon_hours=24,
		issued_at="2026-01-01T00:00:00Z",
		model_version="v1",
	)
	written = _write(root, "outage_forecast", frame)
	assert _cell(written, "probability") == pytest.approx(0.72)
	assert int(_cell(written, "horizon_hours")) == 24


def test_outage_history_reuses_the_resilience_event(root: Path):
	"""One event model: what history serves is what SAIDI is computed from."""
	from datetime import UTC, datetime

	from alea.resilience.views import InterruptionEvent

	event = InterruptionEvent(
		zone="Nairobi",
		started_at=datetime(2026, 1, 1, tzinfo=UTC),
		duration_minutes=60.0,
		customers_interrupted=1000.0,
	)
	frame = project_outage_history([event], country_iso="KE")
	written = _write(root, "outage_history", frame)
	assert _cell(written, "duration_minutes") == pytest.approx(60.0)
	assert _cell(written, "customers_affected") == pytest.approx(1000.0)


def test_outage_validation_writes_auc_with_its_sample_size(root: Path):
	"""An AUC without the rows behind it is a number nobody can weigh."""
	from alea.outages.views import DetectionMetrics

	metrics = DetectionMetrics(
		auc=0.8,
		pr_auc=0.7,
		accuracy=0.75,
		base_rate=0.1,
		precision=0.7,
		recall=0.6,
		f1=0.65,
		threshold=0.5,
		n_total=100,
		n_positive=10,
	)
	frame = project_outage_validation(
		metrics,
		country_iso="KE",
		grid_zone="Nairobi",
		period_start="2026-01-01",
		period_end="2026-02-01",
	)
	written = _write(root, "outage_validation", frame)
	assert _cell(written, "auc") == pytest.approx(0.8)
	assert int(_cell(written, "sample_size")) == 100


def test_maintenance_predictions_are_per_asset(root: Path):
	"""A prediction names an asset, because a hazard ratio names a feature."""
	frame = project_maintenance_predictions(
		[
			{
				"asset_id": "T1",
				"asset_type": "transformer",
				"country_iso": "KE",
				"failure_probability": 0.3,
				"recommended_action": "inspect",
			}
		],
		model_version="v1",
	)
	written = _write(root, "maintenance_predictions", frame)
	assert _text_cell(written, "asset_id") == "T1"
	assert int(_cell(written, "window_days")) == 30


def test_loss_decomposition_parts_sum_to_the_total(root: Path):
	"""The serialised components sum to the row's total, as the model asserts."""
	import json

	from alea.losses.views import LossComponents

	components = LossComponents(
		load_driven_mwh=600.0, generation_driven_mwh=300.0, topology_driven_mwh=100.0, total_mwh=1000.0
	)
	frame = project_loss_decomposition(
		components, country_iso="KE", period_start="2023-01-01", period_end="2023-12-31"
	)
	written = _write(root, "losses_decomposition", frame)
	parts = json.loads(_text_cell(written, "components"))
	assert sum(part["loss"] for part in parts) == pytest.approx(
		_cell(written, "total_loss")
	)


def test_loss_mitigation_reports_an_unmeasurable_payback_as_nan(root: Path):
	"""``inf`` reads as "never"; an unmeasurable payback is a different claim."""
	from alea.losses.views import MitigationResult

	results = [
		MitigationResult(
			option="reconductor",
			kind="reconductoring",
			capex_usd=1.0e6,
			annual_loss_reduction_mwh=100.0,
			annual_savings_usd=0.0,
			payback_years=None,
			n_snapshots=8760,
		)
	]
	frame = project_loss_mitigation(results, country_iso="KE")
	assert bool(frame["payback_years"].isna().all()), "a None payback must be NaN, not zero"
	written = _write(root, "losses_mitigation", frame)
	assert bool(written["payback_years"].isna().all())


def test_resilience_metrics_are_long_form_and_carry_the_threshold(root: Path):
	"""One row per index, and the SAIDI threshold travels with the number."""
	from alea.resilience.views import ResilienceMetrics

	metrics = ResilienceMetrics(
		ens_mwh=10.0,
		eens_mwh=12.0,
		saidi_hours=12.0,
		saifi=1.5,
		lns_mw=5.0,
		interruption_threshold_minutes=5.0,
		customers_total=1000.0,
		n_events=3,
		n_zones=1,
	)
	frame = project_resilience_metrics(metrics, country_iso="KE", period="2023")
	assert len(frame) >= 5, "every index is its own row"
	written = _write(root, "resilience_metrics", frame)
	assert "SAIDI" in set(written["metric"])
	assert "interruption_threshold" in set(written["metric"]), (
		"two SAIDI figures at different thresholds are different quantities "
		"sharing a name; the threshold must travel with the number"
	)


def test_resilience_contingency_is_per_element(root: Path):
	"""The serving row names an element; the layer summary names an index."""
	frame = project_resilience_contingency(
		[{"element_id": "L1", "element_type": "line", "load_shed_mw": 50.0, "overloaded_elements": 1}],
		country_iso="KE",
	)
	written = _write(root, "resilience_contingency", frame)
	assert _text_cell(written, "element_id") == "L1"
	assert _text_cell(written, "severity") == "medium"


# --------------------------------------------------------------------------
# The schema is the contract
# --------------------------------------------------------------------------


def test_a_projection_missing_a_column_is_refused(root: Path):
	"""The schema check runs before the write.

	A projection that dropped a column would write a table the repository reads
	as an empty page for that column, and a route serving zeros is a route that
	looks like it works.
	"""
	frame = pd.DataFrame({"country_iso": ["KE"]})  # no total_loss, no components
	with pytest.raises(Exception, match="missing required column"):
		project("losses_decomposition", frame, table_path("losses_decomposition"), inputs=["x"])


def test_the_schema_columns_match_what_the_repository_reads(root: Path):
	"""Every column the repository's row builders read is in the schema.

	The schema is the contract, so a column the repository reads and the schema
	does not declare is a column the schema is missing -- which is how the two
	drift apart while both look correct.
	"""
	from alea.publish.views import SERVING_SCHEMAS

	# The columns the repository's builders name per table, read from its source.
	# Kept as a literal because the builders are row-by-row and extracting the
	# column names from them would be a parser, not a test.
	read_columns = {
		"market_prices": {"at", "country_iso", "price", "unit"},
		"market_capture_rates": {"technology", "vre_penetration", "capture_rate", "capture_price"},
		"market_ppa_benchmarks": {
			"technology",
			"country_iso",
			"ppa_price",
			"tenor_years",
			"benchmark_source",
		},
		"outage_forecast": {
			"country_iso",
			"grid_zone",
			"probability",
			"horizon_hours",
			"issued_at",
			"model_version",
		},
		"outage_history": {
			"event_id",
			"country_iso",
			"grid_zone",
			"started_at",
			"duration_minutes",
			"customers_affected",
			"cause",
		},
		"outage_validation": {
			"country_iso",
			"grid_zone",
			"period_start",
			"period_end",
			"auc",
			"precision",
			"recall",
			"sample_size",
		},
		"maintenance_predictions": {
			"asset_id",
			"asset_type",
			"country_iso",
			"failure_probability",
			"window_days",
			"recommended_action",
			"model_version",
		},
		"losses_decomposition": {
			"country_iso",
			"period_start",
			"period_end",
			"total_loss",
			"components",
		},
		"losses_mitigation": {
			"country_iso",
			"option",
			"loss_reduction",
			"capex",
			"payback_years",
		},
		"resilience_metrics": {"metric", "country_iso", "value", "unit", "period"},
		"resilience_contingency": {
			"element_id",
			"element_type",
			"country_iso",
			"load_shed_mw",
			"overloaded_elements",
			"severity",
		},
	}
	for name, columns in read_columns.items():
		declared = set(SERVING_SCHEMAS[name].names)
		missing = columns - declared
		assert not missing, (
			f"{name}: the repository reads {sorted(missing)} and the serving schema "
			f"does not declare them; the table would serve zeros for those columns"
		)


# --------------------------------------------------------------------------
# End to end: the repository serves what the projection wrote
# --------------------------------------------------------------------------


def test_the_repository_serves_a_projected_table(root: Path):
	"""A projected table read back through the Repository, not just the schema.

	Reading it through `read_artefact` proves the write; reading it through the
	Repository proves the *row shape* -- that the repository's builders find the
	columns and produce a `ValueOut` rather than raising on a missing one.
	"""
	config = _LOADED_CONFIG[0]
	assert config is not None, "the root fixture did not load a config"
	_write(
		root,
		"market_prices",
		project_prices(
			pd.DataFrame({"bus_0": [80.0]}, index=pd.to_datetime(["2026-01-01T00:00Z"])),
			countries={"bus_0": "KE"},
		),
	)
	repository = Repository(config)
	rows = repository.prices(country="KE")
	assert len(rows) == 1, "the repository served nothing from a projected table"
	assert rows[0].country_iso == "KE"
	assert rows[0].price.value == pytest.approx(80.0)
