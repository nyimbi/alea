# SPDX-License-Identifier: MIT
"""Layer 4a orchestration.

The stages here are thin: they load inputs, call one of the modules beside
them, and write an artefact whose provenance records **every parameter the
result is a function of**. That last part is the point. An outage-detection AUC
without its VZA bin size, quantile and threshold is not reproducible
(07-layer4 §2.5), and a forecast PR-AUC without its base rate is a number that
will be quoted out of context.

Nothing here holds a live object across a stage boundary (AD-4). A stage reads
versioned files and writes one.

The predictive parameters come from ``Config.predictive``, a
:class:`PredictiveConfig`. The section exists on the root model, so a
``predictive:`` block in YAML, in a scenario overlay, or in a ``--set`` override
reaches the detection path and is recorded in provenance. It did not always: the
root model had no such field and ``extra="forbid"`` turned the block into a load
error, so every parameter below was pinned to its class default while 07-layer4
§2.1 claimed they were all config.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from alea.config.models import Config
from alea.io.artefacts import sha256_file
from alea.io.pipeline import BuildContext, stage, write_stage
from alea.logging import get_logger, new_run_id
from alea.outages.ensemble import combine
from alea.outages.maintenance import fit_cox
from alea.outages.validate import skip_outcome, validate_detector
from alea.outages.views import PredictiveConfig, ValidationOutcome
from alea.outages.viirs import (
	build_baseline,
	detect_tiles,
	detection_parameters,
	read_granule,
)
from alea.outages.weather import Forecaster, train_forecaster
from alea.provenance.models import Basis, DerivedProvenance

logger = get_logger(__name__)


def predictive_config(config: Config | None = None) -> PredictiveConfig:
	"""Layer 4a parameters from the root config, or the pinned defaults.

	``config`` is optional so a caller with no loaded configuration -- a unit
	test, a notebook -- gets the pinned defaults rather than an error. What it
	must not do is *pretend* to read a section that is not there: the
	``isinstance`` guard used to fall through silently for every ``Config`` ever
	loaded, so a detection run recorded the defaults and the caller had no way to
	tell that its override had been dropped. ``Config.predictive`` is now a
	declared field, and a non-``PredictiveConfig`` in its place is a validation
	error at load rather than a silent default at use.
	"""
	if config is None:
		return PredictiveConfig()
	section = config.predictive
	assert isinstance(section, PredictiveConfig), (
		f"Config.predictive is {type(section).__name__}, not a PredictiveConfig; "
		f"the section's parameters would be silently discarded"
	)
	return section


def _code_version() -> str:
	from alea import __version__

	return __version__


def _input_checksums(paths: Iterable[str | Path]) -> list[str]:
	"""Checksums of the files a stage read. A missing file fails loudly."""
	return [sha256_file(Path(path)) for path in paths]


def frame_digest(frame: pd.DataFrame) -> str:
	"""A deterministic content hash of a dataframe.

	Used as the input checksum when a stage's input is an in-memory frame
	rather than a file on disk. Column names, dtypes and bytes are hashed in
	sorted order, so two frames with the same content hash the same regardless
	of how pandas laid them out — and an artefact built from a frame still
	records what it was built from.
	"""
	digest = hashlib.sha256()
	for column in sorted(frame.columns):
		series = frame[column]
		digest.update(str(column).encode())
		digest.update(str(series.dtype).encode())
		digest.update(np.ascontiguousarray(series.to_numpy()).tobytes())
	return digest.hexdigest()


def _provenance(
	inputs: Sequence[str],
	parameters: dict[str, Any],
	*,
	source_id: str,
	notes: str,
	basis: Basis = Basis.MODELLED,
	uncertainty: float = 0.0,
	uncertainty_basis: str = "",
) -> DerivedProvenance:
	return DerivedProvenance(
		source_id=source_id,
		inputs=list(inputs) or ["<none-recorded>"],
		code_version=_code_version(),
		run_id=new_run_id(),
		parameters=parameters,
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis=uncertainty_basis,
		notes=notes,
	)


# --------------------------------------------------------------------------
# VIIRS detection
# --------------------------------------------------------------------------


def detect_to_artefact(
	tile_paths: Sequence[str | Path],
	baseline_paths: Sequence[str | Path],
	zone_ids: NDArray[np.uint32],
	n_zones: int,
	out: str | Path,
	config: PredictiveConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, list[Any]]:
	"""Detect outages across a granule sequence and write the zone series.

	``baseline_paths`` are the granules forming the reference period; the
	baseline is built once and reused, which is why the kernel splits it from
	detection (03-rust-core §3.2). The working set is the reference-period stack
	plus one tile at a time.

	Returns ``(checksum, times)``. The times are the observation instants, so
	the result can be joined to ground truth without a second read.
	"""
	cfg = config or PredictiveConfig()
	if not tile_paths:
		raise ValueError("no detection granules supplied")
	if not baseline_paths:
		raise ValueError(
			"a detection run needs a baseline reference period; a detector with "
			"no baseline cannot tell a dark pixel from a dark region"
		)

	baseline_tiles = [read_granule(path, band=cfg.viirs.radiance_band) for path in baseline_paths]
	baseline = build_baseline(baseline_tiles, cfg.viirs)
	del baseline_tiles

	tiles = [read_granule(path, band=cfg.viirs.radiance_band) for path in tile_paths]
	series, times = detect_tiles(tiles, baseline, zone_ids, n_zones, cfg.viirs)

	frame = pd.DataFrame(series, columns=[f"zone_{index}" for index in range(n_zones)])
	frame.insert(0, "timestamp", pd.to_datetime(list(times), utc=True))

	parameters = {
		**cfg.parameters(),
		"n_zones": n_zones,
		"n_granules": len(tile_paths),
		"n_baseline_granules": len(baseline_paths),
	}
	provenance = _provenance(
		inputs if inputs is not None else _input_checksums([*baseline_paths, *tile_paths]),
		parameters,
		source_id="viirs_vnp46a2",
		notes=(
			"zone flagged fraction of clear pixels; NaN where a zone-hour had no "
			"clear pixels (cloud is unknown, not lit)"
		),
	)
	checksum = write_stage(Path(out), frame, provenance, format="parquet")
	return checksum, times


# --------------------------------------------------------------------------
# Weather forecasting
# --------------------------------------------------------------------------


def forecast_to_artefact(
	frame: pd.DataFrame,
	out: str | Path,
	config: PredictiveConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
	seed: int = 0,
) -> tuple[str, Forecaster]:
	"""Train the outage forecaster and write its metrics.

	The artefact carries PR-AUC, recall at a fixed precision, and the base rate.
	Accuracy is present only so the specification's headline can be reproduced
	beside the base rate that explains it.
	"""
	cfg = config or PredictiveConfig()
	forecaster = train_forecaster(frame, cfg.weather, seed=seed)
	provenance = _provenance(
		inputs if inputs is not None else [frame_digest(frame)],
		{**cfg.parameters(), "seed": seed, "backend": forecaster.backend},
		source_id="outage_forecast",
		notes="; ".join(forecaster.notes) or "weather-driven outage forecaster",
	)
	checksum = write_stage(
		Path(out), forecaster.metrics.model_dump(mode="json"), provenance, format="json"
	)
	return checksum, forecaster


# --------------------------------------------------------------------------
# Maintenance
# --------------------------------------------------------------------------


def maintenance_to_artefact(
	frame: pd.DataFrame,
	out: str | Path,
	config: PredictiveConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, Any]:
	"""Fit the Cox model and write its summary. Refuses without DGA columns."""
	cfg = config or PredictiveConfig()
	fit = fit_cox(frame, cfg.maintenance)
	provenance = _provenance(
		inputs if inputs is not None else [frame_digest(frame)],
		{**cfg.parameters(), "features": fit.features},
		source_id="predictive_maintenance",
		notes=(
			"inputs are credentialed utility data (DGA, work orders); the model "
			"refuses to fit without them"
		),
	)
	checksum = write_stage(Path(out), fit.model_dump(mode="json"), provenance, format="json")
	return checksum, fit


# --------------------------------------------------------------------------
# Ensemble
# --------------------------------------------------------------------------


def ensemble_to_artefact(
	components: dict[str, NDArray[np.float64]],
	outcome: NDArray[np.float64],
	out: str | Path,
	config: PredictiveConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
) -> tuple[str, Any]:
	"""Combine components and write the ensemble probability and its weights."""
	cfg = config or PredictiveConfig()
	result = combine(components, outcome, cfg.ensemble)
	provenance = _provenance(
		inputs if inputs is not None else sorted(components),
		{**cfg.parameters(), "weights": result.weights, "modalities": result.modalities},
		source_id="outage_ensemble",
		notes=(
			f"calibrated weighted average over {len(result.modalities)} modalities; "
			f"unavailable modalities carry zero weight and are not listed"
		),
	)
	checksum = write_stage(Path(out), result.model_dump(mode="json"), provenance, format="json")
	return checksum, result


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validation_to_artefact(
	predicted: NDArray[np.float64] | None,
	truth: NDArray[np.float64] | None,
	out: str | Path,
	config: PredictiveConfig | None = None,
	*,
	inputs: Sequence[str] | None = None,
	reason: str = "",
) -> tuple[str, ValidationOutcome]:
	"""Write a validation outcome — including an explicit skip.

	When the ground truth is unavailable the artefact records the skip. It never
	records a model as validated (07-layer4 §2.5).
	"""
	cfg = config or PredictiveConfig()
	if predicted is None or truth is None:
		outcome = skip_outcome(
			reason or "ground truth unavailable; validation skipped, model NOT validated"
		)
	else:
		outcome = validate_detector(predicted, truth, cfg.viirs)
	provenance = _provenance(
		inputs if inputs is not None else ["<no-ground-truth-checksum>"],
		{**cfg.parameters(), "skipped": outcome.skipped, "ground_truth": outcome.ground_truth},
		source_id="outage_validation",
		notes=outcome.reason or f"validated against {outcome.ground_truth}",
	)
	checksum = write_stage(Path(out), outcome.model_dump(mode="json"), provenance, format="json")
	return checksum, outcome


# --------------------------------------------------------------------------
# Stage registration
# --------------------------------------------------------------------------


@stage("outage_validation")
def _stage_outage_validation(config: Config, out: Path, context: BuildContext) -> DerivedProvenance:
	"""Registered stage: score a detector against ground truth, or record a skip.

	Reads the prediction and truth series from conventional paths under
	``paths.processed``. When the truth artefact is absent — GridWatch needs a
	token the run may not have — the stage writes a **skip** outcome rather than
	failing or, worse, writing a validation with no measurement.
	"""
	from alea.config.paths import resolve
	from alea.io.artefacts import ArtefactError, read_artefact

	processed = resolve(config.paths.processed)
	# The detector's own artefact, at the path `processed("outage_history")`
	# resolves to. This read used to name `outage_detection.parquet`, which
	# nothing writes: the stage that runs the detector is `outage_history`, and
	# its output is the zone series this validator scores. The name mismatch made
	# the validator raise "no detection artefact" on every tree where the
	# detector had in fact run -- a stage reporting a missing input that was
	# sitting right beside it under another name.
	prediction_path = processed / "outage_history.parquet"
	truth_path = processed / "outage_truth.parquet"

	if not truth_path.exists():
		checksum, outcome = validation_to_artefact(
			None,
			None,
			out,
			predictive_config(config),
			reason=(
				"no ground-truth artefact at "
				f"{truth_path}; GridWatch is credentialed and the validation "
				"skipped — the model is NOT validated"
			),
		)
		logger.info("outages.stage.validation", skipped=outcome.skipped, checksum=checksum[:12])
		return _provenance(
			context.inputs,
			{"skipped": True},
			source_id="outage_validation",
			notes=outcome.reason,
		)

	if not prediction_path.exists():
		raise ArtefactError(
			f"no detection artefact at {prediction_path}; validate the detector "
			f"before there is a detector to validate"
		)
	predictions, _ = read_artefact(prediction_path)
	truth, _ = read_artefact(truth_path)
	columns = [c for c in predictions.columns if c.startswith("zone_")]
	if not columns:
		raise ArtefactError(f"{prediction_path} has no zone columns to score")
	checksum, outcome = validation_to_artefact(
		predictions[columns[0]].to_numpy(dtype=float),
		truth.iloc[:, -1].to_numpy(dtype=float),
		out,
		predictive_config(config),
		inputs=context.inputs,
	)
	logger.info(
		"outages.stage.validation",
		skipped=outcome.skipped,
		auc=outcome.metrics.auc if outcome.metrics else None,
	)
	return _provenance(
		context.inputs,
		{"skipped": outcome.skipped},
		source_id="outage_validation",
		notes=outcome.reason or f"validated against {outcome.ground_truth}",
	)


def detection_parameters_for(config: Config | None = None) -> dict[str, Any]:
	"""The detection parameters that would be recorded for this config."""
	return detection_parameters(predictive_config(config).viirs)


__all__ = [
	"detect_to_artefact",
	"detection_parameters_for",
	"ensemble_to_artefact",
	"forecast_to_artefact",
	"frame_digest",
	"maintenance_to_artefact",
	"predictive_config",
	"validation_to_artefact",
]
